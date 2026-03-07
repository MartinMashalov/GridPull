"""
Extraction service — two independent pipelines for native and scanned PDFs.

─────────────────────────────────────────────────────────────────────────────
TEXT pipeline  (native / digital PDF — PyMuPDF extracted text)
  model : gpt-4.1-mini  via OpenAI SDK
  cost  : $0.40/1M input · $1.60/1M output · ×1.20 markup

SCAN pipeline  (scanned / image-based PDF — Mistral OCR first)
  step 1 : Mistral OCR  (mistral-ocr-latest) → markdown text
  step 2 : gpt-4.1-mini via litellm → field extraction
  cost   : $0.001/OCR page + $0.40/1M input + $1.60/1M output · ×1.20 markup

─────────────────────────────────────────────────────────────────────────────
Routing  (extract_from_document)

  doc.is_scanned
      └─► SCAN pipeline
            ├─ planner chooses multi + >8 pages → chunked (6 pages/call, concurrent)
            ├─ planner chooses multi            → single gpt-4.1-mini call
            └─ planner chooses single           → single gpt-4.1-mini call

  doc NOT scanned
      ├─ planner chooses multi-record + >8 pages → chunked multi  (6 pages/call, concurrent)
      ├─ planner chooses multi-record            → multi-record   (30k table budget)
      └─ planner chooses single-record           → single-record
─────────────────────────────────────────────────────────────────────────────
"""

from __future__ import annotations

import asyncio
import gzip
import hashlib
import json
import logging
import re
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List

import httpx
import litellm
from openai import AsyncOpenAI

from app.config import settings
from app.services.pdf_service import ParsedDocument

logger = logging.getLogger(__name__)

# ── Model names ───────────────────────────────────────────────────────────────
_TEXT_MODEL   = "gpt-4.1-mini"   # TEXT pipeline
_VISION_MODEL = "gpt-4.1-mini"   # SCAN pipeline (via litellm)
_CLEANUP_MODEL = "gpt-4.1-nano"  # row cleanup retry
_OCR_MODEL    = "mistral-ocr-latest"

# ── Pricing (LiteLLM-backed) ─────────────────────────────────────────────────
# LiteLLM keeps provider pricing aligned with model metadata for both text
# generation and OCR calls, so we avoid hand-maintaining token/page rates here.
_BEAR_REMOVED_TOKEN_PRICE = 0.05 / 1_000_000
_MARKUP = 1.20

# ── Extraction routing constants ──────────────────────────────────────────────
_CHUNK_THRESHOLD_PAGES = 8   # switch to chunked extraction above this
_CHUNK_SIZE            = 6   # pages per extraction chunk
_PLANNER_TEXT_BUDGET_CHARS = 18_000
_PLANNER_TABLE_BUDGET_CHARS = 9_000
_SINGLE_TEXT_BUDGET_CHARS = 100_000
_SINGLE_TABLE_BUDGET_CHARS = 50_000
_SCAN_TEXT_BUDGET_CHARS = 22_000
_SCAN_RETRY_TEXT_BUDGET_CHARS = 26_000
_SINGLE_DOC_MIN_FFR = 0.75
_SINGLE_DOC_RETRY_MIN_MISSING_FIELDS = 1

# ── OpenAI client (TEXT pipeline) ────────────────────────────────────────────
_openai = AsyncOpenAI(api_key=settings.openai_api_key)


# ─────────────────────────────────────────────────────────────────────────────
# Cost tracking
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class LLMUsage:
    """
    Accumulates costs across all LLM + OCR calls for one extraction job.

    TEXT pipeline  → input_tokens / output_tokens        (gpt-4.1-mini)
    SCAN pipeline  → vision_input_tokens / vision_output_tokens  (gpt-4.1-mini)
                   → ocr_cost_usd                         (Mistral OCR via LiteLLM)
    """
    input_tokens:         int = 0
    output_tokens:        int = 0
    vision_input_tokens:  int = 0
    vision_output_tokens: int = 0
    cleanup_input_tokens: int = 0
    cleanup_output_tokens:int = 0
    ocr_cost_usd:         float = 0.0
    bear_removed_tokens:  int = 0
    bear_latency_ms:      float = 0.0
    bear_cache:           Dict[str, str] = field(default_factory=dict)

    def add(self, prompt_tokens: int, completion_tokens: int) -> None:
        """Record gpt-4o-mini token usage."""
        self.input_tokens  += prompt_tokens
        self.output_tokens += completion_tokens

    def add_vision(self, prompt_tokens: int, completion_tokens: int) -> None:
        """Record gpt-4.1-mini token usage."""
        self.vision_input_tokens  += prompt_tokens
        self.vision_output_tokens += completion_tokens

    def add_cleanup(self, prompt_tokens: int, completion_tokens: int) -> None:
        """Record gpt-4.1-nano token usage."""
        self.cleanup_input_tokens += prompt_tokens
        self.cleanup_output_tokens += completion_tokens

    def add_ocr_cost(self, cost_usd: float) -> None:
        """Record OCR cost reported by LiteLLM."""
        self.ocr_cost_usd += max(0.0, cost_usd)

    def add_bear(self, original_input_tokens: int, output_tokens: int, latency_ms: float) -> None:
        """Record Bear compression savings and elapsed latency."""
        self.bear_removed_tokens += max(0, original_input_tokens - output_tokens)
        self.bear_latency_ms += latency_ms

    @property
    def cost_usd(self) -> float:
        """Total cost in USD including the 20% markup."""
        text_in_cost, text_out_cost = litellm.cost_per_token(
            model=_TEXT_MODEL,
            prompt_tokens=self.input_tokens,
            completion_tokens=self.output_tokens,
            call_type="completion",
        )
        vision_in_cost, vision_out_cost = litellm.cost_per_token(
            model=_VISION_MODEL,
            prompt_tokens=self.vision_input_tokens,
            completion_tokens=self.vision_output_tokens,
            call_type="completion",
        )
        cleanup_in_cost, cleanup_out_cost = litellm.cost_per_token(
            model=_CLEANUP_MODEL,
            prompt_tokens=self.cleanup_input_tokens,
            completion_tokens=self.cleanup_output_tokens,
            call_type="completion",
        )
        base = (
            text_in_cost
            + text_out_cost
            + vision_in_cost
            + vision_out_cost
            + cleanup_in_cost
            + cleanup_out_cost
            + self.ocr_cost_usd
            + self.bear_removed_tokens * _BEAR_REMOVED_TOKEN_PRICE
        )
        return round(base * _MARKUP, 6)


# ─────────────────────────────────────────────────────────────────────────────
# Prompt helpers
# ─────────────────────────────────────────────────────────────────────────────

def _fields_block(fields: List[Dict[str, str]]) -> str:
    lines = []
    for f in fields:
        name = f["name"]
        desc = f.get("description", "")
        if desc and desc != name:
            lines.append(f"  - {name}\n    description: {desc}")
        else:
            lines.append(f"  - {name}\n    description: use the best semantic match from document context")
    return "\n".join(lines)


def _doc_context_block(doc: ParsedDocument) -> str:
    parts = [
        f"Filename: {doc.filename}",
        f"Total pages: {doc.page_count}",
    ]
    if doc.has_tables:
        parts.append(f"Tables detected: {len(doc.tables)}")
    return "\n".join(parts)


async def _maybe_compress_with_bear(
    text: str,
    page_count: int,
    usage: LLMUsage,
    label: str,
) -> str:
    # Only compress large-document payloads. Short prompts are cheaper and faster
    # to send through directly than to route through an extra network hop.
    if (
        not text.strip()
        or not settings.bear_api_key
        or page_count <= settings.bear_min_page_count
        or len(text) < 2_000
    ):
        return text

    cache_key = hashlib.sha1(text.encode("utf-8")).hexdigest()
    if cache_key in usage.bear_cache:
        return usage.bear_cache[cache_key]

    payload = json.dumps({
        "model": settings.bear_model,
        "input": text,
        "compression_settings": {"aggressiveness": settings.bear_aggressiveness},
    }).encode("utf-8")
    headers = {
        "Authorization": f"Bearer {settings.bear_api_key}",
        "Content-Type": "application/json",
        "Content-Encoding": "gzip",
    }

    started_at = time.perf_counter()
    try:
        async with httpx.AsyncClient(timeout=settings.bear_timeout_seconds) as client:
            response = await client.post(
                "https://api.thetokencompany.com/v1/compress",
                headers=headers,
                content=gzip.compress(payload),
            )
            response.raise_for_status()
        data = response.json()
        compressed = str(data.get("output", "") or "")
        original_tokens = int(data.get("original_input_tokens", 0) or 0)
        output_tokens = int(data.get("output_tokens", 0) or 0)
        latency_ms = (time.perf_counter() - started_at) * 1000
        usage.add_bear(original_tokens, output_tokens, latency_ms)
        logger.info(
            "Bear compressed %s: %d → %d tokens in %.1fms",
            label, original_tokens, output_tokens, latency_ms,
        )
        usage.bear_cache[cache_key] = compressed or text
        return usage.bear_cache[cache_key]
    except Exception as exc:
        logger.warning("Bear compression failed for %s: %s", label, exc)
        return text


# ─────────────────────────────────────────────────────────────────────────────
# System prompts
# ─────────────────────────────────────────────────────────────────────────────

_SINGLE_SYSTEM = (
    "You are a precise data extraction assistant for enterprise document processing.\n"
    "Extract the requested fields and return a JSON object with key \"records\" "
    "containing an array of extracted objects.\n"
    "Rules:\n"
    "- records array has exactly ONE object for single-document extraction\n"
    "- Use null for fields genuinely not present and cannot be computed\n"
    "- For money: report the value EXACTLY as it appears in the table cell. "
    "Do NOT append unit words (million/billion/thousand) from table headers or footnotes — "
    "only include the unit if it is literally written inside the cell itself. "
    "Example: cell says '37,531' in a table headed 'in millions' → output '$37,531'; "
    "cell says '$37.5 billion' → output '$37.5 billion'.\n"
    "- For dates: use the format as written in the document\n"
    "- Treat each field description as the primary extraction intent and expected output shape. "
    "If a field clearly asks for a spreadsheet scalar such as a number, date, year, or revision date, "
    "return only that value with no extra labels, currency codes, or commentary unless the description requires them\n"
    "- If a field description explains how to compute the value (e.g. a ratio or margin), "
    "calculate it from the available data in the document and return the computed result\n"
    "- Do not hallucinate values that cannot be found or computed from the document\n"
    "- Return spreadsheet-ready values only. Do not include explanations, equations, citations, or reasoning text inside field values\n"
    "- Field labels may vary across documents; use the field description and nearby context "
    "to match semantically equivalent labels instead of relying on exact string matches\n"
    "- Treat each field description as the primary extraction intent when mapping values\n"
    "- Response format: {\"records\": [{\"Field Name\": \"value\", ...}]}"
)

_MULTI_SYSTEM = (
    "You are a precise data extraction assistant for enterprise document processing.\n"
    "This document contains repeated record structures. Extract ALL matching records "
    "and return a JSON object with key \"records\" containing an array.\n"
    "Rules:\n"
    "- Emit one object per natural repeated record that matches the requested fields\n"
    "- Repeated records may appear across table rows, table columns, repeated sections, or repeated line-item blocks\n"
    "- Skip pure headers and decorative content that are not actual records\n"
    "- Use null for fields not present in a given record\n"
    "- For money: report the value exactly as it appears in the cell; do NOT append "
    "unit words (million/billion) from table headers — only include units literally in the cell\n"
    "- For dates: use the format as written in the document\n"
    "- Treat each field description as the primary extraction intent and expected output shape. "
    "If a field clearly asks for a spreadsheet scalar such as a number, date, year, or revision date, "
    "return only that value with no extra labels, currency codes, or commentary unless the description requires them\n"
    "- Extract ALL records (no truncation)\n"
    "- Do not infer or hallucinate values\n"
    "- Return spreadsheet-ready values only. Do not include explanations, equations, citations, or reasoning text inside field values\n"
    "- Treat each field description as the primary extraction intent when mapping values\n"
    "- Response format: {\"records\": [{\"Field\": \"value\"}, ...]}"
)

_SCAN_SINGLE_SYSTEM = (
    "You are a precise data extraction assistant working with OCR-processed text.\n"
    "The input text was extracted from a scanned document by Mistral OCR — "
    "it may contain minor OCR artefacts (spacing, punctuation). Apply judgment "
    "to recover the correct value despite noise.\n"
    "Extract the requested fields and return a JSON object with key \"records\" "
    "containing an array with exactly ONE object.\n"
    "Rules:\n"
    "- Use null for fields genuinely not found\n"
    "- For money: report the value EXACTLY as it appears in the table cell. "
    "Do NOT append unit words (million/billion/thousand) from table headers or footnotes — "
    "only include the unit if it is literally written inside the cell itself.\n"
    "- For dates: use the format as written\n"
    "- Treat each field description as the primary extraction intent and expected output shape. "
    "If a field clearly asks for a spreadsheet scalar such as a number, date, year, or revision date, "
    "return only that value with no extra labels, currency codes, or commentary unless the description requires them\n"
    "- If a field description explains how to compute the value (e.g. a ratio or margin), "
    "calculate it from the available data and return the computed result\n"
    "- Do not hallucinate — only extract what is present\n"
    "- Return spreadsheet-ready values only. Do not include explanations, equations, citations, or reasoning text inside field values\n"
    "- Field labels may vary across documents; use the field description and nearby context "
    "to match semantically equivalent labels instead of relying on exact string matches\n"
    "- Treat each field description as the primary extraction intent when mapping values\n"
    "- Response format: {\"records\": [{\"Field Name\": \"value\", ...}]}"
)

_SCAN_MULTI_SYSTEM = (
    "You are a precise data extraction assistant working with OCR-processed text.\n"
    "The input text was extracted from a scanned document by Mistral OCR — "
    "it may contain minor OCR artefacts. Apply judgment to recover correct values.\n"
    "This document may contain repeated records. Extract ALL matching records.\n"
    "Rules:\n"
    "- Emit one object per natural repeated record that matches the requested fields\n"
    "- Repeated records may appear across table rows, table columns, repeated sections, or repeated line-item blocks\n"
    "- Skip pure headers and decorative content that are not actual records\n"
    "- Use null for fields not present in a given record\n"
    "- Treat each field description as the primary extraction intent and expected output shape. "
    "If a field clearly asks for a spreadsheet scalar such as a number, date, year, or revision date, "
    "return only that value with no extra labels, currency codes, or commentary unless the description requires them\n"
    "- Extract ALL records (no truncation)\n"
    "- Do not hallucinate values\n"
    "- Return spreadsheet-ready values only. Do not include explanations, equations, citations, or reasoning text inside field values\n"
    "- Treat each field description as the primary extraction intent when mapping values\n"
    "- Response format: {\"records\": [{\"Field\": \"value\"}, ...]}"
)

# Single-record retry: stronger guidance when initial output has formulas/explanations or missing required fields
_SINGLE_RETRY_INSTRUCTION = (
    "IMPORTANT (retry — previous output was invalid): Extract only from the main consolidated "
    "statement or primary source. Each field must be a single scalar value (e.g. one number like "
    "$123,456 or a year). Do NOT output formulas (e.g. '$35,879 + $26,684'), equations, or "
    "explanatory text. If the value appears as a sum of line items in the document, report the "
    "consolidated total only."
)


# ─────────────────────────────────────────────────────────────────────────────
# Single-record validation (reject formula/explanation, require filled scalars)
# ─────────────────────────────────────────────────────────────────────────────

# Formula-like: number + number, $n + $n, or equation-style
_FORMULA_RE = re.compile(r"[\d,$.]+\s*\+\s*[\d,$.]|\d[\d,.]*\s*=\s*|sum\s+of|total\s+of\s+", re.I)
# Explanation-like: long value with explanatory phrases
_EXPLANATION_MARKERS = ("which is", "that is", "calculated as", "derived from", "i.e.", " e.g.", " because ", " equals ")
_EMPTY_VALUES = {"", "null", "none", "n/a", "na", "-", "unknown", "not found", "not available"}


def _is_formula_or_explanation(value: str) -> bool:
    """True if the value looks like a formula (e.g. $35,879 + $26,684) or explanatory text."""
    if not value or not isinstance(value, str):
        return False
    s = value.strip()
    if not s:
        return False
    if _FORMULA_RE.search(s):
        return True
    if len(s) > 80 and any(m in s.lower() for m in _EXPLANATION_MARKERS):
        return True
    return False


def _single_record_valid(row: Dict[str, Any], field_names: List[str]) -> tuple[bool, str]:
    """
    Returns (valid, reason). Valid is False if any scalar field contains formula/explanation
    or if no requested field is filled.
    """
    filled = [fn for fn in field_names if row.get(fn) is not None and str(row.get(fn)).strip()]
    if not filled:
        return (False, "no fields filled")
    for fn in field_names:
        val = row.get(fn)
        if val is None:
            continue
        if _is_formula_or_explanation(str(val)):
            return (False, f"field '{fn}' contains formula or explanation")
    return (True, "")


def _is_filled_value(value: Any) -> bool:
    if value is None:
        return False
    return str(value).strip().lower() not in _EMPTY_VALUES


def _single_fill_rate(row: Dict[str, Any], field_names: List[str]) -> float:
    if not field_names:
        return 0.0
    filled = sum(1 for fn in field_names if _is_filled_value(row.get(fn)))
    return filled / len(field_names)


def _single_quality_gate(
    row: Dict[str, Any],
    field_names: List[str],
    min_ffr: float,
) -> tuple[bool, float, List[str]]:
    fill_rate = _single_fill_rate(row, field_names)
    missing = [fn for fn in field_names if not _is_filled_value(row.get(fn))]
    passed = fill_rate >= min_ffr
    return passed, fill_rate, missing


# ─────────────────────────────────────────────────────────────────────────────
# Result helpers
# ─────────────────────────────────────────────────────────────────────────────

def _empty(filenames: List[str], field_names: List[str]) -> List[Dict]:
    return [{fn: "" for fn in field_names} | {"_source_file": filenames[0]}]


def _error(filenames: List[str], field_names: List[str], msg: str) -> List[Dict]:
    return [{fn: "" for fn in field_names} | {"_source_file": filenames[0], "_error": msg}]


# ─────────────────────────────────────────────────────────────────────────────
# Value post-processing
# ─────────────────────────────────────────────────────────────────────────────

# Matches a unit word (million/billion/thousand) appended at the end of a value
_UNIT_SUFFIX_RE    = re.compile(r'^(.*?)(\s+(?:million|billion|thousand)s?)$', re.I)
# Detects comma-grouped numbers like 37,531 or 3,822,224 (already in document units)
_HAS_COMMA_NUM_RE  = re.compile(r'\d{1,3}(?:,\d{3})+')
# Matches reporting-unit declarations in document text
_PAREN_UNIT_RE     = re.compile(
    r'\(\s*(?:in\s+)?(millions?\s+(?:of\s+)?(?:US\s+)?(?:dollars?)?'
    r'|billions?\s+(?:of\s+)?(?:US\s+)?(?:dollars?)?'
    r'|thousands?)\s*(?:,?\s*except[^)]{0,60})?\)',
    re.I,
)
_INLINE_UNIT_RE    = re.compile(
    r'(?:amounts?\s+(?:are\s+)?(?:in|expressed\s+in)|expressed\s+in|'
    r'reported\s+in|stated\s+in|in)\s+'
    r'(millions?\s+of\s+(?:US\s+)?dollars?|billions?\s+of\s+(?:US\s+)?dollars?'
    r'|thousands?\s+of\s+(?:US\s+)?dollars?|millions?|billions?|thousands?)',
    re.I,
)


def _clean_monetary_value(value: str) -> str:
    """
    Strip unit words (million/billion/thousand) that were erroneously appended
    by the LLM from a table header rather than being literally in the cell.

    Heuristic: if the numeric part already uses comma-grouping (e.g. 37,531 or
    3,822,224) then the value is already expressed in the document's native unit
    and any appended unit word is a duplication error — strip it.
    If the number is small with no commas (e.g. "37.5 billion"), the unit word
    is genuine and should be kept.
    """
    if not value:
        return value
    m = _UNIT_SUFFIX_RE.match(value.strip())
    if not m:
        return value
    base = m.group(1).strip()
    if _HAS_COMMA_NUM_RE.search(base):
        return base  # large comma-grouped number → strip the appended unit
    return value    # small decimal number → keep the unit


def _detect_reporting_unit(doc: "ParsedDocument") -> str | None:
    """
    Scan the first 5 pages for a reporting-unit declaration such as
    "(in millions, except per share data)" or "amounts in millions of dollars".
    Returns a human-readable string or None.
    """
    search_text = " ".join(p.text for p in doc.pages[:5])[:12_000]
    m = _PAREN_UNIT_RE.search(search_text)
    if m:
        inner = m.group(1).strip() if m.lastindex and m.lastindex >= 1 else m.group(0)
        return inner.rstrip("s").lower() + "s"  # normalise → "millions"
    m = _INLINE_UNIT_RE.search(search_text)
    if m:
        return m.group(1).strip().lower()
    return None


def _normalise_rows(
    raw: Any,
    field_names: List[str],
    filename: str,
) -> List[Dict[str, Any]]:
    """Parse the LLM JSON response into a clean list of row dicts."""
    if isinstance(raw, list):
        rows = raw
    elif isinstance(raw, dict):
        list_val = next((v for v in raw.values() if isinstance(v, list)), None)
        rows = list_val if list_val is not None else [raw]
    else:
        rows = [{}]

    result: List[Dict[str, Any]] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        norm: Dict[str, Any] = {}
        for fn in field_names:
            val = row.get(fn)
            raw_str = str(val).strip() if val is not None else ""
            norm[fn] = _clean_monetary_value(raw_str)
        norm["_source_file"] = filename
        result.append(norm)
    return result


# ─────────────────────────────────────────────────────────────────────────────
# TEXT pipeline — LLM call (gpt-4o-mini, OpenAI SDK)
# ─────────────────────────────────────────────────────────────────────────────

async def _llm_extract(
    system: str,
    user_prompt: str,
    field_names: List[str],
    filename: str,
    usage: LLMUsage,
) -> List[Dict[str, Any]]:
    """TEXT pipeline extraction call (gpt-4o-mini)."""
    for attempt in range(3):
        try:
            resp = await _openai.chat.completions.create(
                model=_TEXT_MODEL,
                messages=[
                    {"role": "system", "content": system},
                    {"role": "user",   "content": user_prompt},
                ],
                temperature=0,
                response_format={"type": "json_object"},
                max_tokens=4_096,
            )
            if resp.usage:
                usage.add(resp.usage.prompt_tokens, resp.usage.completion_tokens)
            raw = json.loads(resp.choices[0].message.content)
            result = _normalise_rows(raw, field_names, filename)
            return result if result else _empty([filename], field_names)

        except Exception as exc:
            if attempt == 2:
                logger.error("TEXT extraction failed for %s: %s", filename, exc)
                return _error([filename], field_names, str(exc))
            await asyncio.sleep(1)

    return _empty([filename], field_names)


async def _review_multi_rows(
    rows: List[Dict[str, Any]],
    field_names: List[str],
    filename: str,
    usage: LLMUsage,
    doc_context: str,
    instructions: str = "",
) -> List[Dict[str, Any]]:
    if len(rows) <= 1:
        return rows

    review_prompt = (
        "Review these extracted records and return a cleaned records array.\n\n"
        "Goals:\n"
        "- keep only records that match the same natural row unit\n"
        "- remove duplicates and near-duplicates\n"
        "- if the same fact appears in multiple formats, keep the most document-faithful spreadsheet-ready value\n"
        "- remove subtotal, segment, regional, subcategory, or alternate-view rows unless the requested fields clearly ask for them\n"
        "- do not invent new values\n\n"
        f"Filename: {filename}\n"
        f"Requested fields:\n" + "\n".join(f"- {name}" for name in field_names) + "\n\n"
        + (f"User instructions:\n{instructions.strip()}\n\n" if instructions.strip() else "")
        + f"Document context:\n{doc_context[:10_000]}\n\n"
        + f"Extracted records to review:\n{json.dumps(rows, ensure_ascii=True)}\n\n"
        + 'Return exactly: {"records": [{"Field": "value"}, ...]}'
    )
    reviewed = await _llm_extract(_MULTI_SYSTEM, review_prompt, field_names, filename, usage)

    deduped: List[Dict[str, Any]] = []
    seen: set[str] = set()
    for row in reviewed:
        key = json.dumps({fn: row.get(fn, "") for fn in field_names}, sort_keys=True)
        if key in seen:
            continue
        seen.add(key)
        deduped.append(row)
    return deduped or rows


# ─────────────────────────────────────────────────────────────────────────────
# SCAN pipeline — LLM call (gpt-4.1-mini, litellm)
# ─────────────────────────────────────────────────────────────────────────────

async def _litellm_extract(
    system: str,
    user_prompt: str,
    field_names: List[str],
    filename: str,
    usage: LLMUsage,
) -> List[Dict[str, Any]]:
    """SCAN pipeline extraction call (gpt-4.1-mini via litellm)."""
    for attempt in range(3):
        try:
            resp = await litellm.acompletion(
                model=_VISION_MODEL,
                messages=[
                    {"role": "system", "content": system},
                    {"role": "user",   "content": user_prompt},
                ],
                temperature=0,
                response_format={"type": "json_object"},
                max_tokens=4_096,
            )
            if resp.usage:
                usage.add_vision(resp.usage.prompt_tokens, resp.usage.completion_tokens)
            raw = json.loads(resp.choices[0].message.content)
            result = _normalise_rows(raw, field_names, filename)
            return result if result else _empty([filename], field_names)

        except Exception as exc:
            if attempt == 2:
                logger.error("SCAN extraction failed for %s: %s", filename, exc)
                return _error([filename], field_names, str(exc))
            await asyncio.sleep(1)

    return _empty([filename], field_names)


async def _cleanup_single_row_with_nano(
    row: Dict[str, Any],
    fields: List[Dict[str, str]],
    filename: str,
    usage: LLMUsage,
) -> Dict[str, Any]:
    field_names = [f["name"] for f in fields]
    payload = {fn: row.get(fn, "") for fn in field_names}
    cleanup_prompt = (
        "Review this extracted single-row record and clean only obvious data-quality issues.\n\n"
        "You must work only from the extracted dictionary plus the field names and descriptions.\n"
        "Do not use any external document context.\n"
        "Return a JSON object only.\n\n"
        "Rules:\n"
        "- Keep the same keys\n"
        "- Preserve values that already match the field intent\n"
        "- Treat each field description as the primary extraction intent and expected output shape\n"
        "- If a field clearly wants a spreadsheet scalar number, return only the numeric value that should appear in the cell\n"
        "- Remove currency codes or short labels like USD, RM, EUR only when they are not part of the requested field itself\n"
        "- If a field clearly wants a date, year, or revision date and the value looks obviously clipped, repair it only when the intended completion is clear from the field description or example; otherwise leave it unchanged\n"
        "- Do not add explanations or new facts\n\n"
        f"Filename: {filename}\n"
        f"Fields:\n{_fields_block(fields)}\n\n"
        f"Extracted row:\n{json.dumps(payload, ensure_ascii=True)}\n\n"
        'Return exactly: {"records": [{"Field Name": "value", ...}]}'
    )
    try:
        resp = await _openai.chat.completions.create(
            model=_CLEANUP_MODEL,
            messages=[
                {"role": "user", "content": cleanup_prompt},
            ],
            temperature=0,
            response_format={"type": "json_object"},
            max_tokens=1_200,
        )
        if resp.usage:
            usage.add_cleanup(resp.usage.prompt_tokens, resp.usage.completion_tokens)
        raw = json.loads(resp.choices[0].message.content)
        cleaned_rows = _normalise_rows(raw, field_names, filename)
        if not cleaned_rows:
            return row
        cleaned = dict(row)
        candidate = cleaned_rows[0]
        for fn in field_names:
            new_val = candidate.get(fn)
            if new_val is not None and str(new_val).strip():
                cleaned[fn] = new_val
        return cleaned
    except Exception as exc:
        logger.warning("Single-row cleanup failed for %s: %s", filename, exc)
        return row


# ─────────────────────────────────────────────────────────────────────────────
# TEXT pipeline — extractors
# ─────────────────────────────────────────────────────────────────────────────

async def extract_single_record(
    doc: ParsedDocument,
    fields: List[Dict[str, str]],
    usage: LLMUsage,
    instructions: str = "",
) -> List[Dict[str, Any]]:
    """Extract one record per document (invoice header, contract, annual report…)."""
    field_names = [f["name"] for f in fields]
    ctx   = _doc_context_block(doc)
    fblock = _fields_block(fields)
    single_text_budget = min(_SINGLE_TEXT_BUDGET_CHARS, max(24_000, doc.page_count * 4_000))
    text_parts: List[str] = []
    for p in doc.pages:
        if single_text_budget <= 0:
            break
        part = f"=== Page {p.page_num} ===\n{p.text}"
        text_parts.append(part[:3_500])
        single_text_budget -= len(part)
    raw_single_text = "\n\n".join(text_parts)[:_SINGLE_TEXT_BUDGET_CHARS] or doc.content_text
    content_text = await _maybe_compress_with_bear(
        raw_single_text, doc.page_count, usage, f"{doc.filename} single text"
    )

    single_table_budget = min(_SINGLE_TABLE_BUDGET_CHARS, max(12_000, doc.page_count * 2_000))
    table_parts: List[str] = []
    for t in doc.tables:
        if single_table_budget <= 0:
            break
        part = f"[Table — page {t.page_num}, {t.row_count}×{t.col_count}]\n{t.markdown}"
        table_parts.append(part[:5_000])
        single_table_budget -= len(part)
    raw_single_tables = "\n\n".join(table_parts)[:_SINGLE_TABLE_BUDGET_CHARS] or doc.tables_markdown
    tables_markdown = await _maybe_compress_with_bear(
        raw_single_tables, doc.page_count, usage, f"{doc.filename} single tables"
    )
    # Reporting-unit hints are generic and help any table-heavy document where
    # values are displayed in a shared unit in the header instead of each cell.
    reporting_unit = _detect_reporting_unit(doc) if doc.has_tables else None

    parts = [
        f"--- Document Info ---\n{ctx}",
        f"\n--- Fields to Extract ---\n{fblock}",
    ]
    if instructions.strip():
        # User guidance is treated as an extra constraint layer on top of the
        # field schema, not as a replacement for the document evidence itself.
        parts.append(f"\n--- User Instructions ---\n{instructions.strip()}")
    if reporting_unit:
        parts.append(
            f"\n--- Reporting Unit ---\n"
            f"Numeric values in this document are expressed in: {reporting_unit}. "
            f"Report values exactly as they appear in the cells — do NOT append "
            f"'{reporting_unit}' or any other unit word to the number."
        )
    parts.append(f"\n--- Document Text ---\n{content_text}")
    if tables_markdown:
        parts.append(f"\n--- Detected Tables ---\n{tables_markdown}")

    user_prompt = (
        "\n".join(parts)
        + '\n\nReturn exactly: {"records": [{"Field Name": "value", ...}]}'
    )
    rows = await _llm_extract(_SINGLE_SYSTEM, user_prompt, field_names, doc.filename, usage)
    if len(rows) == 1:
        valid, reason = _single_record_valid(rows[0], field_names)
        if not valid:
            logger.info(
                "Single-record validation failed for %s: %s; retrying with stronger guidance",
                doc.filename, reason,
            )
            retry_prompt = (
                "\n".join(parts) + "\n\n" + _SINGLE_RETRY_INSTRUCTION
                + '\n\nReturn exactly: {"records": [{"Field Name": "value", ...}]}'
            )
            rows = await _llm_extract(_SINGLE_SYSTEM, retry_prompt, field_names, doc.filename, usage)
            if len(rows) == 1:
                valid2, _ = _single_record_valid(rows[0], field_names)
                if not valid2:
                    logger.warning("Single-record retry still invalid for %s", doc.filename)
    if len(rows) == 1:
        gate_ok, fill_rate, missing_fields = _single_quality_gate(rows[0], field_names, _SINGLE_DOC_MIN_FFR)
        if (
            not gate_ok
            and len(missing_fields) >= _SINGLE_DOC_RETRY_MIN_MISSING_FIELDS
        ):
            logger.info(
                "Per-doc gate failed for %s (FFR=%.1f%%, missing=%d); running missing-fields retry",
                doc.filename,
                fill_rate * 100,
                len(missing_fields),
            )
            retry_fields = [f for f in fields if f["name"] in missing_fields]
            retry_fblock = _fields_block(retry_fields)
            retry_prompt = (
                f"--- Document Info ---\n{ctx}\n\n"
                f"--- Missing Fields Only ---\n{retry_fblock}\n\n"
                + (f"--- User Instructions ---\n{instructions.strip()}\n\n" if instructions.strip() else "")
                + "--- Retry Objective ---\n"
                + "Fill only the listed missing fields from the provided document context. "
                + "Do not rewrite fields that already have values.\n\n"
                + f"--- Document Text ---\n{content_text}\n\n"
                + (f"--- Detected Tables ---\n{tables_markdown}\n\n" if tables_markdown else "")
                + 'Return exactly: {"records": [{"Field Name": "value", ...}]}'
            )
            retry_rows = await _llm_extract(
                _SINGLE_SYSTEM,
                retry_prompt,
                [f["name"] for f in retry_fields],
                doc.filename,
                usage,
            )
            if retry_rows:
                merged = dict(rows[0])
                retry_row = retry_rows[0]
                for fn in missing_fields:
                    old = merged.get(fn)
                    new_val = retry_row.get(fn)
                    if not _is_filled_value(old) and _is_filled_value(new_val):
                        merged[fn] = new_val
                rows = [merged]
                gate_ok2, fill_rate2, missing2 = _single_quality_gate(rows[0], field_names, _SINGLE_DOC_MIN_FFR)
                logger.info(
                    "Per-doc gate result for %s after retry: pass=%s FFR=%.1f%% missing=%d",
                    doc.filename,
                    gate_ok2,
                    fill_rate2 * 100,
                    len(missing2),
                )
    if len(rows) == 1:
        rows = [await _cleanup_single_row_with_nano(rows[0], fields, doc.filename, usage)]
    return rows


async def extract_multi_record(
    doc: ParsedDocument,
    fields: List[Dict[str, str]],
    usage: LLMUsage,
    instructions: str = "",
) -> List[Dict[str, Any]]:
    """
    Extract multiple records from a short multi-record document (≤ _CHUNK_THRESHOLD_PAGES).
    Uses full 30k table budget instead of the 8k-capped doc.tables_markdown.
    """
    field_names = [f["name"] for f in fields]
    ctx    = _doc_context_block(doc)
    fblock = _fields_block(fields)
    content_text = await _maybe_compress_with_bear(
        doc.content_text, doc.page_count, usage, f"{doc.filename} multi text"
    )
    # For multi-record extraction we give more table context than the default
    # parser summary, but keep the budget bounded for cost control.
    table_parts, tbudget = [], 35_000
    for t in doc.tables:
        entry = f"[Table — page {t.page_num}, {t.row_count}×{t.col_count}]\n{t.markdown}"
        table_parts.append(entry[:3_000])
        tbudget -= len(entry)
        if tbudget <= 0:
            break
    full_tables_md = await _maybe_compress_with_bear(
        "\n\n".join(table_parts), doc.page_count, usage, f"{doc.filename} multi tables"
    )

    parts = [
        f"--- Document Info ---\n{ctx}",
        f"\n--- Fields to Extract (one object per repeated record) ---\n{fblock}",
    ]
    if instructions.strip():
        parts.append(f"\n--- User Instructions ---\n{instructions.strip()}")
    parts.append(
        "\n--- Extraction Mode ---\n"
        "The output should contain one object per natural repeated record that matches the "
        "requested fields. If the schema repeats across table rows, emit one object per row. "
        "If the schema repeats across table columns, emit one object per column. If the "
        "document does not actually contain repeated records that match the requested fields, "
        "return a single best record instead of inventing multiples."
    )
    if full_tables_md:
        parts.append(f"\n--- Detected Tables ---\n{full_tables_md}")
    parts.append(f"\n--- Document Text ---\n{content_text}")

    user_prompt = (
        "\n".join(parts)
        + '\n\nReturn: {"records": [{"Field": "value"}, ...]}'
    )
    rows = await _llm_extract(_MULTI_SYSTEM, user_prompt, field_names, doc.filename, usage)
    return await _review_multi_rows(
        rows,
        field_names,
        doc.filename,
        usage,
        "\n".join(parts),
        instructions,
    )


async def extract_multi_record_chunked(
    doc: ParsedDocument,
    fields: List[Dict[str, str]],
    usage: LLMUsage,
    instructions: str = "",
) -> List[Dict[str, Any]]:
    """
    Page-by-page extraction for long multi-record documents (> _CHUNK_THRESHOLD_PAGES).
    Splits pages into chunks of _CHUNK_SIZE and runs all chunks concurrently.
    Prevents repeated-record truncation in long schedules, logs, and tables.
    """
    field_names = [f["name"] for f in fields]
    fblock      = _fields_block(fields)
    page_chunks = [doc.pages[i: i + _CHUNK_SIZE]
                   for i in range(0, len(doc.pages), _CHUNK_SIZE)]

    async def _extract_chunk(chunk_pages: list) -> List[Dict[str, Any]]:
        page_nums  = {p.page_num for p in chunk_pages}
        first_pg, last_pg = chunk_pages[0].page_num, chunk_pages[-1].page_num
        chunk_text = "\n\n".join(
            f"=== Page {p.page_num} ===\n{p.text}" for p in chunk_pages
        )[:22_000]
        tables_md = "\n\n".join(
            f"[Table — page {t.page_num}, {t.row_count}×{t.col_count}]\n{t.markdown}"
            for t in doc.tables if t.page_num in page_nums
        )[:14_000]
        chunk_text = await _maybe_compress_with_bear(
            chunk_text, doc.page_count, usage, f"{doc.filename} chunk {first_pg}-{last_pg} text"
        )
        tables_md = await _maybe_compress_with_bear(
            tables_md, doc.page_count, usage, f"{doc.filename} chunk {first_pg}-{last_pg} tables"
        )

        parts = [
            f"--- Document Info ---\n"
            f"Filename: {doc.filename}\nTotal pages: {doc.page_count}\n"
            f"Extracting: pages {first_pg}–{last_pg}",
            f"\n--- Fields (one object per repeated record) ---\n{fblock}",
        ]
        if instructions.strip():
            parts.append(f"\n--- User Instructions ---\n{instructions.strip()}")
        if tables_md:
            parts.append(f"\n--- Tables (pages {first_pg}–{last_pg}) ---\n{tables_md}")
        parts.append(f"\n--- Text (pages {first_pg}–{last_pg}) ---\n{chunk_text}")

        prompt = (
            "\n".join(parts)
            + "\n\nExtract ALL repeated records on these pages only. "
            + 'Return: {"records": [...]}. No records here → {"records": []}.'
        )
        return await _llm_extract(_MULTI_SYSTEM, prompt, field_names, doc.filename, usage)

    chunk_results = await asyncio.gather(*[_extract_chunk(c) for c in page_chunks])

    all_rows: List[Dict[str, Any]] = []
    for rows in chunk_results:
        all_rows.extend(r for r in rows if any(r.get(fn) for fn in field_names))

    if not all_rows:
        return _empty([doc.filename], field_names)
    return await _review_multi_rows(
        all_rows,
        field_names,
        doc.filename,
        usage,
        doc.content_text,
        instructions,
    )


# ─────────────────────────────────────────────────────────────────────────────
# SCAN pipeline — OCR + gpt-4.1-mini extractors
# ─────────────────────────────────────────────────────────────────────────────

async def _extract_scanned_chunked(
    ocr_text: str,
    doc: ParsedDocument,
    fields: List[Dict[str, str]],
    field_names: List[str],
    fblock: str,
    usage: LLMUsage,
    instructions: str = "",
) -> List[Dict[str, Any]]:
    """
    Chunked SCAN extraction for long multi-record scanned documents.
    Splits OCR text by page markers and runs chunks concurrently.
    """
    # Split by "=== Page N ===" markers emitted by ocr_service
    parts    = re.split(r"(=== Page \d+ ===)", ocr_text)
    pages: List[str] = []
    i = 1
    while i < len(parts) - 1:
        pages.append(parts[i] + "\n" + parts[i + 1])
        i += 2
    if not pages:
        pages = [ocr_text]

    chunks = [pages[i: i + _CHUNK_SIZE] for i in range(0, len(pages), _CHUNK_SIZE)]

    async def _chunk_task(chunk_pages: list) -> List[Dict]:
        chunk_text = await _maybe_compress_with_bear(
            "\n\n".join(chunk_pages)[:20_000],
            doc.page_count,
            usage,
            f"{doc.filename} OCR chunk",
        )
        prompt = (
            f"--- Document Info ---\n"
            f"Filename: {doc.filename}\nTotal pages: {doc.page_count}\n"
            f"Source: Scanned document (OCR by Mistral)\n\n"
            f"--- Fields (one object per repeated record) ---\n{fblock}\n\n"
            + (f"--- User Instructions ---\n{instructions.strip()}\n\n" if instructions.strip() else "")
            + f"--- OCR Text (this chunk) ---\n{chunk_text}\n\n"
            'Extract ALL repeated records in this chunk. '
            'Return: {"records": [...]}. No records here → {"records": []}.'
        )
        return await _litellm_extract(_SCAN_MULTI_SYSTEM, prompt, field_names, doc.filename, usage)

    chunk_results = await asyncio.gather(*[_chunk_task(c) for c in chunks])

    all_rows: List[Dict[str, Any]] = []
    for rows in chunk_results:
        all_rows.extend(r for r in rows if any(r.get(fn) for fn in field_names))

    if not all_rows:
        return _empty([doc.filename], field_names)
    return await _review_multi_rows(
        all_rows,
        field_names,
        doc.filename,
        usage,
        ocr_text,
        instructions,
    )


async def extract_from_scanned_document(
    doc: ParsedDocument,
    fields: List[Dict[str, str]],
    usage: LLMUsage,
    instructions: str = "",
) -> List[Dict[str, Any]]:
    """
    SCAN pipeline entry point.

    Step 1 — Mistral OCR: converts the scanned PDF to full markdown text,
              preserving tables, columns, and layout.
    Step 2 — Plan cardinality: decide whether the requested schema should
              produce a single record or repeated records.
    Step 3 — gpt-4.1-mini via litellm: extract fields from OCR text.
              Long multi-record docs are chunked and run concurrently.
    """
    from app.services.ocr_service import run_mistral_ocr

    if not settings.mistral_api_key:
        logger.warning(
            "Scanned doc detected (%s) but MISTRAL_API_KEY not set — "
            "falling back to TEXT pipeline",
            doc.filename,
        )
        return await extract_single_record(doc, fields, usage, instructions)

    logger.info(
        "SCAN pipeline — Mistral OCR starting: %s (%d pages)",
        doc.filename, doc.page_count,
    )

    try:
        ocr_text, ocr_page_count, ocr_cost_usd = await run_mistral_ocr(doc.file_path, settings.mistral_api_key)
        usage.add_ocr_cost(ocr_cost_usd)
        logger.info(
            "SCAN pipeline — OCR complete: %s — %d pages, %d chars, $%.4f",
            doc.filename, ocr_page_count, len(ocr_text), ocr_cost_usd,
        )
    except Exception as exc:
        logger.error(
            "SCAN pipeline — OCR failed for %s: %s — falling back to TEXT pipeline",
            doc.filename, exc,
        )
        return await extract_single_record(doc, fields, usage, instructions)

    field_names = [f["name"] for f in fields]
    fblock      = _fields_block(fields)
    extraction_mode = "single"
    planner_prompt = (
        "Decide whether this OCR document should produce ONE output object or MANY output objects "
        "for the requested schema.\n\n"
        "Reply with exactly one word:\n"
        "- single: the requested fields describe the document as a whole, so there should be one row per file\n"
        "- multi: the same requested fields can be filled repeatedly from the same file, so there should be many rows from one file\n\n"
        "Rules:\n"
        "- Base the decision on the requested fields plus the OCR structure\n"
        "- Repeated records may appear across rows, columns, repeated sections, or repeated line items\n"
        "- If unsure, reply single\n\n"
        f"Filename: {doc.filename}\n"
        f"Total pages: {doc.page_count}\n"
        f"Requested fields:\n{fblock}\n\n"
        + (f"User instructions:\n{instructions.strip()}\n\n" if instructions.strip() else "")
        + f"OCR text:\n{await _maybe_compress_with_bear(ocr_text[:20_000], doc.page_count, usage, f'{doc.filename} OCR planner')}"
    )
    try:
        planner_resp = await _litellm_extract(
            _SCAN_SINGLE_SYSTEM,
            planner_prompt + '\n\nReturn: {"records": [{"mode": "single"}]}',
            ["mode"],
            doc.filename,
            usage,
        )
        planner_mode = (planner_resp[0].get("mode", "") if planner_resp else "").strip().lower()
        extraction_mode = "multi" if planner_mode == "multi" else "single"
        logger.info("SCAN pipeline — planned %s extraction: %s", extraction_mode, doc.filename)
    except Exception as exc:
        markdown_table_lines = len(re.findall(r"^\|.+\|", ocr_text, re.M))
        extraction_mode = "multi" if markdown_table_lines >= 6 else "single"
        logger.warning(
            "SCAN planner failed for %s: %s — falling back to %s",
            doc.filename, exc, extraction_mode,
        )

    if extraction_mode == "multi" and doc.page_count > _CHUNK_THRESHOLD_PAGES:
        logger.info("SCAN pipeline — chunked multi-record: %s", doc.filename)
        return await _extract_scanned_chunked(
            ocr_text, doc, fields, field_names, fblock, usage, instructions
        )

    ctx = (
        f"Filename: {doc.filename}\n"
        f"Total pages: {doc.page_count}\n"
        f"Source: Scanned document (OCR by Mistral)"
    )

    if extraction_mode == "multi":
        logger.info("SCAN pipeline — single-call multi-record: %s", doc.filename)
        system      = _SCAN_MULTI_SYSTEM
        instruction = 'Return: {"records": [{"Field": "value"}, ...]}'
    else:
        logger.info("SCAN pipeline — single-record: %s", doc.filename)
        system      = _SCAN_SINGLE_SYSTEM
        instruction = 'Return: {"records": [{"Field Name": "value", ...}]}'

    user_prompt = (
        f"--- Document Info ---\n{ctx}\n\n"
        f"--- Fields to Extract ---\n{fblock}\n\n"
        + (f"--- User Instructions ---\n{instructions.strip()}\n\n" if instructions.strip() else "")
        + f"--- OCR Text (Mistral OCR) ---\n{await _maybe_compress_with_bear(ocr_text[:_SCAN_TEXT_BUDGET_CHARS], doc.page_count, usage, f'{doc.filename} OCR extract')}\n\n"
        + instruction
    )

    rows = await _litellm_extract(system, user_prompt, field_names, doc.filename, usage)
    if extraction_mode != "multi":
        if len(rows) == 1:
            valid, reason = _single_record_valid(rows[0], field_names)
            if not valid:
                logger.info(
                    "SCAN single-record validation failed for %s: %s; retrying with stronger guidance",
                    doc.filename, reason,
                )
                retry_prompt = user_prompt + "\n\n" + _SINGLE_RETRY_INSTRUCTION + "\n\n" + instruction
                rows = await _litellm_extract(system, retry_prompt, field_names, doc.filename, usage)
                if len(rows) == 1:
                    valid2, _ = _single_record_valid(rows[0], field_names)
                    if not valid2:
                        logger.warning("SCAN single-record retry still invalid for %s", doc.filename)
        if len(rows) == 1:
            gate_ok, fill_rate, missing_fields = _single_quality_gate(rows[0], field_names, _SINGLE_DOC_MIN_FFR)
            if (
                not gate_ok
                and len(missing_fields) >= _SINGLE_DOC_RETRY_MIN_MISSING_FIELDS
            ):
                logger.info(
                    "SCAN per-doc gate failed for %s (FFR=%.1f%%, missing=%d); running missing-fields retry",
                    doc.filename,
                    fill_rate * 100,
                    len(missing_fields),
                )
                retry_fields = [f for f in fields if f["name"] in missing_fields]
                retry_fblock = _fields_block(retry_fields)
                retry_prompt = (
                    f"--- Document Info ---\n{ctx}\n\n"
                    f"--- Missing Fields Only ---\n{retry_fblock}\n\n"
                    + (f"--- User Instructions ---\n{instructions.strip()}\n\n" if instructions.strip() else "")
                    + "--- Retry Objective ---\n"
                    + "Fill only the listed missing fields using the OCR text. "
                    + "Do not rewrite fields that already have values.\n\n"
                    + f"--- OCR Text (Mistral OCR) ---\n{await _maybe_compress_with_bear(ocr_text[:_SCAN_RETRY_TEXT_BUDGET_CHARS], doc.page_count, usage, f'{doc.filename} OCR missing-fields')}\n\n"
                    + 'Return exactly: {"records": [{"Field Name": "value", ...}]}'
                )
                retry_rows = await _litellm_extract(
                    _SCAN_SINGLE_SYSTEM,
                    retry_prompt,
                    [f["name"] for f in retry_fields],
                    doc.filename,
                    usage,
                )
                if retry_rows:
                    merged = dict(rows[0])
                    retry_row = retry_rows[0]
                    for fn in missing_fields:
                        old = merged.get(fn)
                        new_val = retry_row.get(fn)
                        if not _is_filled_value(old) and _is_filled_value(new_val):
                            merged[fn] = new_val
                    rows = [merged]
                    gate_ok2, fill_rate2, missing2 = _single_quality_gate(rows[0], field_names, _SINGLE_DOC_MIN_FFR)
                    logger.info(
                        "SCAN per-doc gate result for %s after retry: pass=%s FFR=%.1f%% missing=%d",
                        doc.filename,
                        gate_ok2,
                        fill_rate2 * 100,
                        len(missing2),
                    )
        if len(rows) == 1:
            rows = [await _cleanup_single_row_with_nano(rows[0], fields, doc.filename, usage)]
        return rows
    return await _review_multi_rows(
        rows,
        field_names,
        doc.filename,
        usage,
        ocr_text,
        instructions,
    )


# ─────────────────────────────────────────────────────────────────────────────
# TEXT pipeline routing
# ─────────────────────────────────────────────────────────────────────────────

def _should_extract_multi(doc: ParsedDocument, fields: List[Dict[str, str]]) -> bool:
    """
    Conservative structural fallback for deciding whether a native PDF should
    be treated as multi-record.

    The primary decision is made by a generic planner prompt in
    `extract_from_document`. This fallback is only used when that planning call
    fails, so it stays intentionally simple and conservative.
    """
    del fields
    if not doc.has_tables:
        return False
    data_tables = [t for t in doc.tables if t.row_count >= 4 and t.col_count >= 2]
    return len(data_tables) >= 1


# ─────────────────────────────────────────────────────────────────────────────
# Main entry point
# ─────────────────────────────────────────────────────────────────────────────

async def extract_from_document(
    doc: ParsedDocument,
    fields: List[Dict[str, str]],
    usage: LLMUsage,
    instructions: str = "",
) -> List[Dict[str, Any]]:
    """
    Full extraction pipeline for one document.

    Accumulates token + OCR costs into `usage` (caller-owned LLMUsage).
    Always returns List[Dict]:
      single-record → list with 1 element
      multi-record  → list with N elements (one per table row / line item)

    Routing summary:
    ┌─ doc.is_scanned
    │   └─► SCAN pipeline (Mistral OCR + gpt-4.1-mini)
    │         ├─ multi-record + >8 pages → chunked (6 pages/call, concurrent)
    │         ├─ multi-record            → single call
    │         └─ single-record           → single call
    │
    └─ native PDF (TEXT pipeline, gpt-4o-mini)
          ├─ planner says multi + >8 pages → chunked multi
          ├─ planner says multi            → multi-record
          └─ planner says single           → single-record
    """
    if doc.is_scanned:
        logger.info(
            "Routing %s → SCAN pipeline (avg_chars_per_page=%.0f)",
            doc.filename,
            sum(len(p.text) for p in doc.pages) / max(len(doc.pages), 1),
        )
        rows = await extract_from_scanned_document(doc, fields, usage, instructions)

    else:
        extraction_mode = "single"
        planner_text_budget = min(_PLANNER_TEXT_BUDGET_CHARS, max(10_000, doc.page_count * 1_200))
        planner_text_parts: List[str] = []
        for p in doc.pages:
            if planner_text_budget <= 0:
                break
            part = f"=== Page {p.page_num} ===\n{p.text}"
            planner_text_parts.append(part[:1_600])
            planner_text_budget -= len(part)
        planner_text = "\n\n".join(planner_text_parts)[:_PLANNER_TEXT_BUDGET_CHARS] or doc.content_text[:_PLANNER_TEXT_BUDGET_CHARS]

        planner_table_budget = min(_PLANNER_TABLE_BUDGET_CHARS, max(5_000, doc.page_count * 600))
        planner_table_parts: List[str] = []
        for t in doc.tables:
            if planner_table_budget <= 0:
                break
            part = f"[Table — page {t.page_num}, {t.row_count}×{t.col_count}]\n{t.markdown}"
            planner_table_parts.append(part[:2_000])
            planner_table_budget -= len(part)
        planner_tables = "\n\n".join(planner_table_parts)[:_PLANNER_TABLE_BUDGET_CHARS] or doc.tables_markdown[:_PLANNER_TABLE_BUDGET_CHARS]
        planner_prompt = (
            "Decide whether this document should produce ONE output object or MANY output objects "
            "for the requested schema.\n\n"
            "Reply with exactly one word:\n"
            "- single: the requested fields describe the document as a whole, so there should be one row per file\n"
            "- multi: the same requested fields can be filled repeatedly from the same file, so there should be many rows from one file\n\n"
            "Rules:\n"
            "- Base the decision on the requested fields plus the document structure\n"
            "- A file can contain tables and still be single if the requested fields are document-level\n"
            "- A file can be multi even when repeated records are arranged across columns instead of rows\n"
            "- If unsure, reply single\n\n"
            f"Filename: {doc.filename}\n"
            f"Total pages: {doc.page_count}\n"
            f"Document structure hint: {doc.doc_type_hint}\n"
            f"Requested fields:\n{_fields_block(fields)}\n\n"
            + (f"User instructions:\n{instructions.strip()}\n\n" if instructions.strip() else "")
            + f"Document text:\n{await _maybe_compress_with_bear(planner_text, doc.page_count, usage, f'{doc.filename} planner text')}\n\n"
            f"Detected tables:\n{await _maybe_compress_with_bear(planner_tables, doc.page_count, usage, f'{doc.filename} planner tables')}"
        )
        try:
            planner_resp = await _openai.chat.completions.create(
                model=_TEXT_MODEL,
                messages=[{"role": "user", "content": planner_prompt}],
                temperature=0,
                max_tokens=8,
            )
            if planner_resp.usage:
                usage.add(planner_resp.usage.prompt_tokens, planner_resp.usage.completion_tokens)
            planner_raw = (planner_resp.choices[0].message.content or "").strip().lower()
            extraction_mode = "multi" if planner_raw == "multi" else "single"
            logger.info(
                "Routing %s → TEXT pipeline (%s, hint=%s)",
                doc.filename, extraction_mode, doc.doc_type_hint,
            )
        except Exception as exc:
            extraction_mode = "multi" if _should_extract_multi(doc, fields) else "single"
            logger.warning(
                "Routing planner failed for %s: %s — falling back to %s",
                doc.filename, exc, extraction_mode,
            )

        if extraction_mode == "multi":
            if doc.page_count > _CHUNK_THRESHOLD_PAGES:
                n_chunks = -(-doc.page_count // _CHUNK_SIZE)  # ceiling division
                logger.info(
                    "TEXT chunked multi-record: %s (%d pages, %d chunks)",
                    doc.filename, doc.page_count, n_chunks,
                )
                rows = await extract_multi_record_chunked(doc, fields, usage, instructions)
            else:
                rows = await extract_multi_record(doc, fields, usage, instructions)
        else:
            rows = await extract_single_record(doc, fields, usage, instructions)

    if not rows:
        field_names = [f["name"] for f in fields]
        rows = _empty([doc.filename], field_names)

    return rows
