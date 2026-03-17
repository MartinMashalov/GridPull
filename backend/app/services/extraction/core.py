from __future__ import annotations

import gzip
import hashlib
import json
import logging
import re
import time
from dataclasses import dataclass, field
from datetime import date
from typing import Any, Dict, List

import httpx
import litellm
from openai import AsyncOpenAI

from app.config import settings
from app.services.pdf_service import ParsedDocument

logger = logging.getLogger(__name__)

# Model names
_TEXT_MODEL = "gpt-4.1-mini"
_VISION_MODEL = "gpt-4.1-mini"
_CLEANUP_MODEL = "gpt-4.1-nano"
_OCR_MODEL = "mistral-ocr-latest"

# Pricing (LiteLLM-backed)
_BEAR_REMOVED_TOKEN_PRICE = 0.05 / 1_000_000
_MARKUP = 1.20

# Extraction routing constants
_CHUNK_THRESHOLD_PAGES = 8
_CHUNK_SIZE = 6
_PLANNER_TEXT_BUDGET_CHARS = 18_000
_PLANNER_TABLE_BUDGET_CHARS = 9_000
_SINGLE_TEXT_BUDGET_CHARS = 100_000
_SINGLE_TABLE_BUDGET_CHARS = 50_000
_SCAN_TEXT_BUDGET_CHARS = 22_000
_SCAN_RETRY_TEXT_BUDGET_CHARS = 26_000
_SINGLE_FINAL_RETRY_TEXT_BUDGET_CHARS = 36_000
_SCAN_FINAL_RETRY_TEXT_BUDGET_CHARS = 52_000
_SINGLE_DOC_MIN_FFR = 0.75
_SINGLE_DOC_RETRY_MIN_MISSING_FIELDS = 1

_openai = AsyncOpenAI(api_key=settings.openai_api_key)


@dataclass
class LLMUsage:
    input_tokens: int = 0
    output_tokens: int = 0
    vision_input_tokens: int = 0
    vision_output_tokens: int = 0
    cleanup_input_tokens: int = 0
    cleanup_output_tokens: int = 0
    ocr_cost_usd: float = 0.0
    bear_removed_tokens: int = 0
    bear_latency_ms: float = 0.0
    bear_cache: Dict[str, str] = field(default_factory=dict)

    def add(self, prompt_tokens: int, completion_tokens: int) -> None:
        self.input_tokens += prompt_tokens
        self.output_tokens += completion_tokens

    def add_vision(self, prompt_tokens: int, completion_tokens: int) -> None:
        self.vision_input_tokens += prompt_tokens
        self.vision_output_tokens += completion_tokens

    def add_cleanup(self, prompt_tokens: int, completion_tokens: int) -> None:
        self.cleanup_input_tokens += prompt_tokens
        self.cleanup_output_tokens += completion_tokens

    def add_ocr_cost(self, cost_usd: float) -> None:
        self.ocr_cost_usd += max(0.0, cost_usd)

    def add_bear(self, original_input_tokens: int, output_tokens: int, latency_ms: float) -> None:
        self.bear_removed_tokens += max(0, original_input_tokens - output_tokens)
        self.bear_latency_ms += latency_ms

    @property
    def cost_usd(self) -> float:
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


def _fields_block(fields: List[Dict[str, str]]) -> str:
    lines = []
    for f in fields:
        name = f["name"]
        desc = f.get("description", "")
        if desc and desc != name:
            lines.append(f"  - {name}\n    description: {desc}")
        else:
            lines.append(
                f"  - {name}\n"
                "    description: use the best semantic match from document context; return null if genuinely not present"
            )
    return "\n".join(lines)


def _doc_context_block(doc: ParsedDocument) -> str:
    parts = [
        f"Filename: {doc.filename}",
        f"Total pages: {doc.page_count}",
        f"Document structure hint: {doc.doc_type_hint}",
        f"Tables detected: {len(doc.tables)}",
    ]
    if doc.is_scanned:
        parts.append("Scan detected: yes")
    return "\n".join(parts)


async def _maybe_compress_with_bear(
    text: str,
    page_count: int,
    usage: LLMUsage,
    label: str,
) -> str:
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

    payload = json.dumps(
        {
            "model": settings.bear_model,
            "input": text,
            "compression_settings": {"aggressiveness": settings.bear_aggressiveness},
        }
    ).encode("utf-8")
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
            "Bear compressed %s: %d -> %d tokens in %.1fms",
            label,
            original_tokens,
            output_tokens,
            latency_ms,
        )
        usage.bear_cache[cache_key] = compressed or text
        return usage.bear_cache[cache_key]
    except Exception as exc:
        logger.warning("Bear compression failed for %s: %s", label, exc)
        return text


def _system_with_date(system: str) -> str:
    return date.today().strftime("%d-%m-%Y") + "\n\n" + system


_SINGLE_SYSTEM = (
    "You are a precise data extraction assistant for enterprise document processing.\n"
    "Extract the requested fields and return a JSON object with key \"records\" "
    "containing an array of extracted objects.\n"
    "Rules:\n"
    "- records array has exactly ONE object for single-document extraction\n"
    "- Use null for fields genuinely not present and cannot be computed\n"
    "- For money: report the value EXACTLY as it appears in the table cell. "
    "Do NOT append unit words (million/billion/thousand) from table headers or footnotes - "
    "only include the unit if it is literally written inside the cell itself. "
    "Example: cell says '37,531' in a table headed 'in millions' -> output '$37,531'; "
    "cell says '$37.5 billion' -> output '$37.5 billion'.\n"
    "- For dates: use American format (MM/DD/YYYY, e.g. 03/15/2024). Convert from other formats if needed.\n"
    "- Treat each field description as the primary extraction intent and expected output shape. "
    "If a field clearly asks for a spreadsheet scalar such as a number, date, year, or revision date, "
    "return only that value with no extra labels, currency codes, or commentary unless the description requires them\n"
    "- If a field description explains how to compute the value (e.g. a ratio or margin), "
    "calculate it from the available data in the document and return the computed result\n"
    "- For long annual reports, filings, and financial statements, prioritize consolidated statement pages, "
    "financial statement notes, and detected tables over cover pages, letters, and general narrative sections\n"
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
    "unit words (million/billion) from table headers - only include units literally in the cell\n"
    "- For dates: use American format (MM/DD/YYYY, e.g. 03/15/2024). Convert from other formats if needed.\n"
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
    "The input text was extracted from a scanned document by Mistral OCR - "
    "it may contain minor OCR artefacts (spacing, punctuation). Apply judgment "
    "to recover the correct value despite noise.\n"
    "Extract the requested fields and return a JSON object with key \"records\" "
    "containing an array with exactly ONE object.\n"
    "Rules:\n"
    "- Use null for fields genuinely not found\n"
    "- For money: report the value EXACTLY as it appears in the table cell. "
    "Do NOT append unit words (million/billion/thousand) from table headers or footnotes - "
    "only include the unit if it is literally written inside the cell itself.\n"
    "- For dates: use American format (MM/DD/YYYY, e.g. 03/15/2024). Convert from other formats if needed.\n"
    "- Treat each field description as the primary extraction intent and expected output shape. "
    "If a field clearly asks for a spreadsheet scalar such as a number, date, year, or revision date, "
    "return only that value with no extra labels, currency codes, or commentary unless the description requires them\n"
    "- If a field description explains how to compute the value (e.g. a ratio or margin), "
    "calculate it from the available data and return the computed result\n"
    "- Do not hallucinate - only extract what is present\n"
    "- Return spreadsheet-ready values only. Do not include explanations, equations, citations, or reasoning text inside field values\n"
    "- Field labels may vary across documents; use the field description and nearby context "
    "to match semantically equivalent labels instead of relying on exact string matches\n"
    "- Treat each field description as the primary extraction intent when mapping values\n"
    "- Response format: {\"records\": [{\"Field Name\": \"value\", ...}]}"
)

_SCAN_MULTI_SYSTEM = (
    "You are a precise data extraction assistant working with OCR-processed text.\n"
    "The input text was extracted from a scanned document by Mistral OCR - "
    "it may contain minor OCR artefacts. Apply judgment to recover correct values.\n"
    "This document may contain repeated records. Extract ALL matching records.\n"
    "Rules:\n"
    "- Emit one object per natural repeated record that matches the requested fields\n"
    "- Repeated records may appear across table rows, table columns, repeated sections, or repeated line-item blocks\n"
    "- Skip pure headers and decorative content that are not actual records\n"
    "- Use null for fields not present in a given record\n"
    "- For dates: use American format (MM/DD/YYYY, e.g. 03/15/2024). Convert from other formats if needed.\n"
    "- Treat each field description as the primary extraction intent and expected output shape. "
    "If a field clearly asks for a spreadsheet scalar such as a number, date, year, or revision date, "
    "return only that value with no extra labels, currency codes, or commentary unless the description requires them\n"
    "- Extract ALL records (no truncation)\n"
    "- Do not hallucinate values\n"
    "- Return spreadsheet-ready values only. Do not include explanations, equations, citations, or reasoning text inside field values\n"
    "- Treat each field description as the primary extraction intent when mapping values\n"
    "- Response format: {\"records\": [{\"Field\": \"value\"}, ...]}"
)

_SINGLE_RETRY_INSTRUCTION = (
    "IMPORTANT (retry - previous output was invalid): Extract only from the main consolidated "
    "statement or primary source. Each field must be a single scalar value (e.g. one number like "
    "$123,456 or a year). Do NOT output formulas (e.g. '$35,879 + $26,684'), equations, or "
    "explanatory text. If the value appears as a sum of line items in the document, report the "
    "consolidated total only."
)

_MISSING_FIELDS_FOCUSED_RETRY_INSTRUCTION = (
    "FINAL RETRY (focused missing fields): Fill only the listed missing fields.\n"
    "Search the provided text carefully for semantically equivalent labels, OCR-noisy variants, and nearby values.\n"
    "For identifier-like fields (for example fields asking for an id, number, code, reference, or document no),\n"
    "prefer the exact short alphanumeric token that appears near the matching label.\n"
    "Do not rewrite already-filled fields. Do not invent values.\n"
)

_FORMULA_RE = re.compile(r"[\d,$.]+\s*\+\s*[\d,$.]|\d[\d,.]*\s*=\s*|sum\s+of|total\s+of\s+", re.I)
_EXPLANATION_MARKERS = (
    "which is",
    "that is",
    "calculated as",
    "derived from",
    "i.e.",
    " e.g.",
    " because ",
    " equals ",
)
_EMPTY_VALUES = {"", "null", "none", "n/a", "na", "-", "unknown", "not found", "not available"}


def _is_formula_or_explanation(value: str) -> bool:
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
    filled = [fn for fn in field_names if _is_filled_value(row.get(fn))]
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


def _empty(filenames: List[str], field_names: List[str]) -> List[Dict]:
    return [{fn: None for fn in field_names} | {"_source_file": filenames[0]}]


def _error(filenames: List[str], field_names: List[str], msg: str) -> List[Dict]:
    return [{fn: None for fn in field_names} | {"_source_file": filenames[0], "_error": msg}]


_UNIT_SUFFIX_RE = re.compile(r"^(.*?)(\s+(?:million|billion|thousand)s?)$", re.I)
_HAS_COMMA_NUM_RE = re.compile(r"\d{1,3}(?:,\d{3})+")
_PAREN_UNIT_RE = re.compile(
    r"\(\s*(?:in\s+)?(millions?\s+(?:of\s+)?(?:US\s+)?(?:dollars?)?"
    r"|billions?\s+(?:of\s+)?(?:US\s+)?(?:dollars?)?"
    r"|thousands?)\s*(?:,?\s*except[^)]{0,60})?\)",
    re.I,
)
_INLINE_UNIT_RE = re.compile(
    r"(?:amounts?\s+(?:are\s+)?(?:in|expressed\s+in)|expressed\s+in|"
    r"reported\s+in|stated\s+in|in)\s+"
    r"(millions?\s+of\s+(?:US\s+)?dollars?|billions?\s+of\s+(?:US\s+)?dollars?"
    r"|thousands?\s+of\s+(?:US\s+)?dollars?|millions?|billions?|thousands?)",
    re.I,
)


def _clean_monetary_value(value: str) -> str:
    if not value:
        return value
    match = _UNIT_SUFFIX_RE.match(value.strip())
    if not match:
        return value
    base = match.group(1).strip()
    if _HAS_COMMA_NUM_RE.search(base):
        return base
    return value


def _detect_reporting_unit(doc: ParsedDocument) -> str | None:
    search_text = " ".join(p.text for p in doc.pages[:5])[:12_000]
    match = _PAREN_UNIT_RE.search(search_text)
    if match:
        inner = match.group(1).strip() if match.lastindex and match.lastindex >= 1 else match.group(0)
        return inner.rstrip("s").lower() + "s"
    match = _INLINE_UNIT_RE.search(search_text)
    if match:
        return match.group(1).strip().lower()
    return None


def _normalise_rows(raw: Any, field_names: List[str], filename: str) -> List[Dict[str, Any]]:
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
            if val is None:
                norm[fn] = None
                continue
            raw_str = str(val).strip()
            norm[fn] = None if raw_str.lower() in _EMPTY_VALUES else _clean_monetary_value(raw_str)
        norm["_source_file"] = filename
        result.append(norm)
    return result
