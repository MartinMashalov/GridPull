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

from app.config import settings
from app.services.pdf_service import ParsedDocument

logger = logging.getLogger(__name__)

# Model names
_TEXT_MODEL = settings.llm_extraction_model          # Primary: gpt-4.1-mini
_VISION_MODEL = settings.llm_extraction_model        # Primary: gpt-4.1-mini
# Post-extraction single-row polish uses the lighter fallback model.
_CLEANUP_MODEL = settings.llm_openai_fallback_model  # Fallback: gpt-5.4-mini
_OCR_MODEL = "mistral-ocr-latest"

_BEAR_REMOVED_TOKEN_PRICE = 0.05 / 1_000_000
_MARKUP = 1.20

# (Thresholds removed — strategies always retry for any missing fields)

# Per-token pricing (USD per token) for cost estimation without litellm
# Tuple: (input_price, cached_input_price, output_price)
# OpenAI prompt caching gives 75% discount on cached input tokens (automatic, ≥1024 token prefix)
_MODEL_PRICING: Dict[str, tuple[float, float, float]] = {
    "gpt-5.4": (10.00e-6, 2.50e-6, 40.00e-6),       # GPT-5.4 flagship
    "gpt-5.4-pro": (15.00e-6, 3.75e-6, 60.00e-6),   # GPT-5.4 Pro (max performance)
    "gpt-5.4-mini": (1.00e-6, 0.25e-6, 4.00e-6),    # GPT-5.4 mini (efficient)
    "gpt-5.4-nano": (0.30e-6, 0.075e-6, 1.20e-6),   # GPT-5.4 nano (speed/cost)
    "gpt-4.1-mini": (0.40e-6, 0.10e-6, 1.60e-6),    # GPT-4.1 mini (primary extraction)
    "gpt-4.1-nano": (0.10e-6, 0.025e-6, 0.40e-6),   # GPT-4.1 nano
    "gpt-4o-mini": (0.15e-6, 0.0375e-6, 0.60e-6),   # Legacy
    "gpt-4o": (2.50e-6, 0.625e-6, 10.00e-6),        # Legacy
    # Cerebras (no caching — cached price = full price)
    "gpt-oss-120b": (0.35e-6, 0.35e-6, 0.75e-6),    # Cerebras OpenAI GPT OSS 120B
}


def _estimate_cost(model: str, prompt_tokens: int, completion_tokens: int, cached_tokens: int = 0) -> float:
    """Estimate cost from token counts and model name, accounting for cached input tokens."""
    # Sort keys longest-first so "gpt-5.4-mini" matches before "gpt-5.4"
    for key in sorted(_MODEL_PRICING, key=len, reverse=True):
        if key in model:
            inp, cached_inp, out = _MODEL_PRICING[key]
            uncached = max(0, prompt_tokens - cached_tokens)
            return uncached * inp + cached_tokens * cached_inp + completion_tokens * out
    # Unknown model — use gpt-4.1-mini pricing as conservative default
    inp, cached_inp, out = _MODEL_PRICING["gpt-4.1-mini"]
    uncached = max(0, prompt_tokens - cached_tokens)
    return uncached * inp + cached_tokens * cached_inp + completion_tokens * out


@dataclass
class LLMUsage:
    llm_cost_usd: float = 0.0
    input_tokens: int = 0
    output_tokens: int = 0
    cached_input_tokens: int = 0
    vision_input_tokens: int = 0
    vision_output_tokens: int = 0
    cleanup_input_tokens: int = 0
    cleanup_output_tokens: int = 0
    ocr_cost_usd: float = 0.0
    bear_removed_tokens: int = 0
    bear_latency_ms: float = 0.0
    bear_cache: Dict[str, str] = field(default_factory=dict)

    # Backward compat alias
    @property
    def litellm_cost_usd(self) -> float:
        return self.llm_cost_usd

    @litellm_cost_usd.setter
    def litellm_cost_usd(self, value: float) -> None:
        self.llm_cost_usd = value

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
        return round(
            (self.llm_cost_usd + self.ocr_cost_usd + self.bear_removed_tokens * _BEAR_REMOVED_TOKEN_PRICE)
            * _MARKUP,
            6,
        )


def record_llm_usage_cost(usage: LLMUsage, response: Any) -> None:
    """Compute cost from OpenAI response usage and model name, accounting for cached tokens."""
    resp_usage = getattr(response, "usage", None)
    model = getattr(response, "model", "") or ""
    if resp_usage:
        prompt_tokens = getattr(resp_usage, "prompt_tokens", 0) or 0
        completion_tokens = getattr(resp_usage, "completion_tokens", 0) or 0
        # Extract cached token count from OpenAI's prompt_tokens_details
        cached_tokens = 0
        details = getattr(resp_usage, "prompt_tokens_details", None)
        if details:
            cached_tokens = getattr(details, "cached_tokens", 0) or 0
        usage.cached_input_tokens += cached_tokens
        usage.llm_cost_usd += _estimate_cost(model, prompt_tokens, completion_tokens, cached_tokens)


def _fields_block(fields: List[Dict[str, str]]) -> str:
    lines = []
    for f in fields:
        name = f["name"]
        desc = f.get("description", "")
        fmt = (f.get("format") or "").strip()
        numeric = bool(f.get("numeric")) or f.get("type") == "float"

        parts = []
        if desc and desc != name:
            parts.append(f"    description: {desc}")
        else:
            parts.append("    description: use the best semantic match from document context; return null if genuinely not present")
        if fmt:
            parts.append(f"    format: {fmt}")
        if numeric:
            parts.append("    type: float — return a bare number with no currency symbols, commas, or units")

        lines.append(f"  - {name}\n" + "\n".join(parts))
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
    "- Use null for fields genuinely not present and cannot be inferred from context\n"
    "- For money: report the value EXACTLY as it appears in the table cell. "
    "Do NOT append unit words (million/billion/thousand) from table headers or footnotes - "
    "only include the unit if it is literally written inside the cell itself. "
    "Example: cell says '37,531' in a table headed 'in millions' -> output '$37,531'; "
    "cell says '$37.5 billion' -> output '$37.5 billion'.\n"
    "- For dates: use American format (MM/DD/YYYY, e.g. 03/15/2024). Convert from other formats if needed.\n"
    "- For a due date not stated explicitly: if payment terms are present (e.g. 'Net 30') and an invoice date is known, compute the due date.\n"
    "- If a field asks for a currency, denomination, or unit that is not labeled per-row but is clearly implied document-wide "
    "(e.g., all amounts use $ symbols, or the document header states a currency), return that value rather than null.\n"
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
    "- For comparative financial statements (income statements, balance sheets, cash flow statements) "
    "that show the same metrics across multiple fiscal years/periods as separate columns: "
    "emit one object per fiscal year/period column. Each object gets the year/date and the "
    "corresponding metric values from that column.\n"
    "- Skip pure headers and decorative content that are not actual records\n"
    "- Never emit blank spacer records (objects where every field is null, empty, or a dash). "
    "Each object must be one real data record.\n"
    "- When multiple detail lines refer to the same logical entity (same ID, name, or address), "
    "merge them into a single object\n"
    "- For document-level metadata that appears once in the document header/letterhead but applies to "
    "all line items (e.g. vendor/company name, invoice number, document date, customer name), "
    "include that value in EVERY output record — do not leave it null just because the table row "
    "doesn't repeat it\n"
    "- Prefer values from the primary structured table over supplementary narrative text "
    "when both are present for the same entity\n"
    "- Use null for fields not present in a given record and not inferable from context\n"
    "- For money: report the value exactly as it appears in the cell; do NOT append "
    "unit words (million/billion) from table headers - only include units literally in the cell\n"
    "- For dates: use American format (MM/DD/YYYY, e.g. 03/15/2024). Convert from other formats if needed.\n"
    "- For a due date not stated explicitly: if payment terms are present (e.g. 'Net 30') and an invoice date is known, compute the due date.\n"
    "- If a field asks for a currency, denomination, or unit not labeled per-row but clearly implied document-wide "
    "(e.g., all amounts use $ symbols, or the document header states a currency), return that inferred value rather than null.\n"
    "- Treat each field description as the primary extraction intent and expected output shape. "
    "If a field clearly asks for a spreadsheet scalar such as a number, date, year, or revision date, "
    "return only that value with no extra labels, currency codes, or commentary unless the description requires them\n"
    "- Extract ALL records (no truncation)\n"
    "- Do not infer or hallucinate values\n"
    "- Return spreadsheet-ready values only. Do not include explanations, equations, citations, or reasoning text inside field values\n"
    "- Treat each field description as the primary extraction intent when mapping values\n"
    "- CRITICAL — column mapping: When extracting from tables, match each requested field to "
    "exactly ONE source column by its header. Each source column maps to at most one output "
    "field. If a requested field has no matching column header or document label, return null — "
    "do NOT fill it from the nearest unrelated column. Two different requested fields must never "
    "draw values from the same source column.\n"
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
    "- For comparative financial statements that show the same metrics across multiple fiscal "
    "years/periods as separate columns: emit one object per fiscal year/period column\n"
    "- Skip pure headers and decorative content that are not actual records\n"
    "- Never emit blank spacer records (all fields empty). One row per real data record.\n"
    "- When multiple detail lines refer to the same logical entity (same ID, name, or address), "
    "merge them into one record.\n"
    "- For document-level metadata that appears once in the document header/letterhead but applies to "
    "all line items (e.g. vendor/company name, invoice number, document date, customer name), "
    "include that value in EVERY output record\n"
    "- Prefer values from the primary structured table over supplementary narrative text "
    "when both are present for the same entity\n"
    "- Use null for fields not present in a given record\n"
    "- For dates: use American format (MM/DD/YYYY, e.g. 03/15/2024). Convert from other formats if needed.\n"
    "- Treat each field description as the primary extraction intent and expected output shape. "
    "If a field clearly asks for a spreadsheet scalar such as a number, date, year, or revision date, "
    "return only that value with no extra labels, currency codes, or commentary unless the description requires them\n"
    "- Extract ALL records (no truncation)\n"
    "- Do not hallucinate values\n"
    "- Return spreadsheet-ready values only. Do not include explanations, equations, citations, or reasoning text inside field values\n"
    "- Treat each field description as the primary extraction intent when mapping values\n"
    "- CRITICAL — column mapping: When extracting from tables, match each requested field to "
    "exactly ONE source column by its header. Each source column maps to at most one output "
    "field. If a requested field has no matching column header or document label, return null — "
    "do NOT fill it from the nearest unrelated column. Two different requested fields must never "
    "draw values from the same source column.\n"
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
_EMPTY_VALUES = {
    "", "null", "none", "n/a", "na", "-", "—", "\u2014", "\u2013",
    "unknown", "not found", "not available",
}


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


def property_schedule_row_cleanup_matches_schema(field_names: List[str]) -> bool:
    """True when the field set looks like a multi-row schedule (property, vehicle, employee, etc.).

    Detection uses structural cues: explicit row-numbering indicators ("#" in
    field names), separate address-component fields (city/state/zip as distinct
    columns), and entity-level descriptor+value pairings.  Generic words like
    "name" or "number" are intentionally excluded because they appear in almost
    every field set (invoices, EOBs, etc.) and cause false-positive SOV routing.
    """
    if len(field_names) < 4:
        return False

    blob = " ".join(n.lower() for n in field_names)

    # 1. Explicit row-numbering indicator — a "#" literal in a field name
    #    (e.g. "Location #", "Vehicle #", "Unit #") is a strong signal that
    #    the user expects multiple numbered rows.
    has_row_numbering = any("#" in fn for fn in field_names)

    # 2. Separate address/location component fields as individual columns.
    #    Schedules break location into city/state/zip columns; single-record
    #    documents use one composite "Address" field.
    address_components = sum(
        1 for fn in field_names
        if re.search(r"\b(city|state|province|zip|postal|county|country)\b", fn.lower())
    )

    # 3. Entity-level descriptor cues (physical/classification attributes)
    has_entity_descriptor = bool(re.search(
        r"\b(city|state|zip|postal|location|site|type|class|category|county|province|country)\b",
        blob,
    ))

    # 4. Value/quantity cues
    has_value = bool(re.search(
        r"\b(value|amount|cost|total|premium|rate|quantity|count|area|size|sq\s*ft|sq\.?\s*ft|square)\b",
        blob,
    ))

    # Route 1: explicit row numbering + entity descriptor (location/type fields)
    #   Require descriptor to distinguish schedule-like "#" (Location #, Vehicle #)
    #   from document-identifier "#" (Form #, Contract #).
    if has_row_numbering and has_entity_descriptor:
        return True

    # Route 2: ≥2 separate address-component fields → per-entity location data
    if address_components >= 2:
        return True

    # Route 3: entity descriptor + value + at least one address component
    if has_entity_descriptor and has_value and address_components >= 1:
        return True

    return False


def _extract_table_headers(tables: list) -> set[str]:
    """Pull normalised label-like cell texts from parsed table markdown.

    Includes classic header rows plus short first-column labels from key/value
    or coverage tables so cleanup can recognise valid fields on declaration
    pages that do not use a single flat table header.
    """
    headers: set[str] = set()
    for t in tables:
        if not t.markdown:
            continue
        lines = t.markdown.split("\n")
        header_lines: list[str] = []
        separator_idx: int | None = None
        for line in lines:
            if re.match(r"^\|\s*-", line):
                separator_idx = len(header_lines)
                break
            header_lines.append(line)
        candidate_blocks = [" ".join(header_lines)]
        if separator_idx is not None:
            for line in lines[separator_idx + 1 :]:
                if not line.startswith("|"):
                    continue
                cells = [re.sub(r"\s+", " ", cell.strip()).lower() for cell in line.split("|")]
                if len(cells) < 2:
                    continue
                first_cell = cells[1]
                if not first_cell or first_cell == "---":
                    continue
                if not re.search(r"[a-z]", first_cell):
                    continue
                if "$" in first_cell or len(first_cell) > 50:
                    continue
                if ":" in first_cell and not first_cell.endswith(":"):
                    continue
                candidate_blocks.append(first_cell)
        for block in candidate_blocks:
            for cell in block.split("|"):
                token = re.sub(r"\s+", " ", cell.strip()).lower().rstrip(":").strip()
                if not token or token == "---":
                    continue
                if not re.search(r"[a-z]", token):
                    continue
                if "$" in token or len(token) > 60:
                    continue
                if ":" in token:
                    continue
                headers.add(token)
    return headers


def build_table_column_hint(tables: list) -> str:
    """Build a prompt section listing detected table column headers.

    Giving the LLM an explicit list of available columns prevents it from
    guessing or mapping fields to wrong columns. Fully general — reads
    actual table structure with no domain knowledge.
    """
    headers = _extract_table_headers(tables)
    if not headers:
        return ""
    sorted_headers = sorted(headers)
    return (
        "--- Detected Table Columns ---\n"
        "The source table(s) contain these column headers (normalised):\n  "
        + ", ".join(sorted_headers)
        + "\nUse this list to map each requested field to its correct source column. "
        "Column headers are often abbreviated — match by meaning, not exact text. "
        "Use any legend, footnote, or key present in the document to resolve abbreviations. "
        "If a requested field has NO plausible column match above AND is not mentioned "
        "elsewhere in the document, return null. "
        "Never map two different requested fields to the same source column."
    )


_VOWELS = set("aeiou")


def _is_consonant_abbrev(abbrev: str, word: str) -> bool:
    """True if abbrev matches the leading consonants of word (e.g. 'yr'→'year', 'blt'→'built')."""
    consonants = "".join(c for c in word if c not in _VOWELS)
    return len(abbrev) >= 2 and consonants.startswith(abbrev)


def _is_initialism_match(h_term: str, fn_terms: list[str]) -> bool:
    """True if h_term equals the first-letter initials of a prefix of fn_terms.

    E.g. 'bi' matches ['business', 'income', ...] because b+i = 'bi'.
    """
    if len(h_term) < 2 or len(fn_terms) < 2:
        return False
    for end in range(2, len(fn_terms) + 1):
        initials = "".join(t[0] for t in fn_terms[:end])
        if h_term == initials:
            return True
    return False


def _field_name_matches_any_header(field_name: str, table_headers: set[str], doc_text_lower: str) -> bool:
    """True if any significant term of the field name can be linked to a table header
    or a label in the document text.

    Matching strategies (all general, no field-specific knowledge):
      1. Prefix: 'spr' matches 'sprinklered', 'loc' matches 'location'
      2. Compact header: 's p r' → 'spr' then prefix-check against field terms
      3. Substring (≥3 chars): 'spr' in 'sprinklered'
      4. Consonant abbreviation: 'yr' matches 'year', 'blt' matches 'built'
      5. Doc text label scan: term appears near a colon/pipe/comma
    """
    fn_terms = [t for t in re.findall(r"[a-z]{2,}", field_name.lower())]
    if not fn_terms:
        return True

    for header in table_headers:
        header_terms = re.findall(r"[a-z]{2,}", header)
        h_terms = set(header_terms)
        h_compact = re.sub(r"[^a-z]", "", header)
        if len(h_compact) >= 2:
            h_terms.add(h_compact)
        if len(header_terms) >= 2:
            header_initials = "".join(term[0] for term in header_terms)
            if len(header_initials) >= 2:
                h_terms.add(header_initials)
        for ft in fn_terms:
            for ht in h_terms:
                if ft.startswith(ht) or ht.startswith(ft):
                    return True
                if min(len(ht), len(ft)) >= 3 and (ht in ft or ft in ht):
                    return True
                if _is_consonant_abbrev(ht, ft):
                    return True
        for ht in h_terms:
            if _is_initialism_match(ht, fn_terms):
                return True

    for term in fn_terms:
        if len(term) < 3:
            continue
        pos = doc_text_lower.find(term)
        if pos >= 0:
            window = doc_text_lower[max(0, pos - 40):pos + len(term) + 40]
            if re.search(r"[:,|]", window):
                return True
    return False


def sanitize_unmatched_field_values(
    rows: List[Dict[str, Any]],
    field_names: List[str],
    doc_text: str = "",
    tables: list | None = None,
) -> List[Dict[str, Any]]:
    """General post-processing for multi-record extractions from tables.

    Null only obvious uniform hallucinations for fields whose names do not match
    any detected table/document labels. Varying row values are left alone here
    because schedules often use row labels or per-page key/value blocks rather
    than a single top-row header.
    """
    if not doc_text or len(rows) < 3:
        return rows

    table_headers = _extract_table_headers(tables) if tables else set()
    doc_text_lower = doc_text.lower()

    for fn in field_names:
        filled = [str(row[fn]).strip() for row in rows if row.get(fn) is not None and str(row[fn]).strip()]
        if len(filled) < 3:
            continue
        if _field_name_matches_any_header(fn, table_headers, doc_text_lower):
            continue

        unique_count = len(set(filled))
        if unique_count == 1:
            # Before nulling, check if the uniform value actually appears in
            # the document text.  A real document-level value (e.g. customer
            # name from the letterhead, propagated to every line-item row) will
            # be present in the text — only null if it's truly absent.
            uniform_val = filled[0]
            if uniform_val.lower() in doc_text_lower:
                logger.info(
                    "Kept uniform value '%s' for field '%s' across %d rows "
                    "(field label not in headers but value found in document text)",
                    uniform_val, fn, len(filled),
                )
                continue
            logger.info(
                "Nulled uniform value '%s' for field '%s' across %d rows "
                "(field label not found in table headers or document)",
                uniform_val, fn, len(filled),
            )
            for row in rows:
                row[fn] = None

    return rows


def sanitize_duplicate_column_values(
    rows: List[Dict[str, Any]],
    field_names: List[str],
    tables: list | None = None,
) -> List[Dict[str, Any]]:
    """General post-processing: when two output fields have highly overlapping values
    across rows (>=80% match), the model likely mapped the same source column to both.
    Null out the field whose name is LESS likely to match a table header."""
    if len(rows) < 2 or not tables:
        return rows

    table_headers = _extract_table_headers(tables)

    val_vectors: Dict[str, list] = {}
    for fn in field_names:
        vec = [str(row.get(fn) or "").strip().lower() for row in rows]
        if all(v == "" for v in vec):
            continue
        val_vectors[fn] = vec

    checked: set[tuple[str, str]] = set()
    for fn_a, vec_a in val_vectors.items():
        for fn_b, vec_b in val_vectors.items():
            if fn_a >= fn_b:
                continue
            pair = (fn_a, fn_b)
            if pair in checked:
                continue
            checked.add(pair)
            filled_pairs = [(a, b) for a, b in zip(vec_a, vec_b) if a and b]
            if len(filled_pairs) < 2:
                continue
            matching = sum(1 for a, b in filled_pairs if a == b)
            if matching / len(filled_pairs) < 0.8:
                continue
            # Skip if the overlap is driven by a shared dominant value (e.g. both fields are
            # mostly "n" or "0%" — coincidental similarity, not the same source column).
            match_vals = [a for a, b in filled_pairs if a == b]
            if match_vals:
                top_val = max(set(match_vals), key=match_vals.count)
                if match_vals.count(top_val) / len(filled_pairs) > 0.65:
                    continue
            a_match = _field_name_matches_any_header(fn_a, table_headers, "")
            b_match = _field_name_matches_any_header(fn_b, table_headers, "")
            if a_match and not b_match:
                victim = fn_b
            elif b_match and not a_match:
                victim = fn_a
            elif not a_match and not b_match:
                victim = fn_b
            else:
                continue
            logger.info(
                "Nulled field '%s' (%d/%d values duplicate '%s' which matches a table header)",
                victim, matching, len(filled_pairs),
                fn_a if victim == fn_b else fn_b,
            )
            for row in rows:
                row[victim] = None

    return rows


def document_has_wide_data_grid(doc: ParsedDocument) -> bool:
    """True when the PDF parser found a table shaped like a multi-entity schedule (rows x columns).

    Used to avoid per-page extraction that drops cross-page schedule context. Based on layout
    only, not on requested field names. Thresholds come from settings (env-overridable).
    """
    min_r = settings.extraction_wide_grid_min_rows
    min_c = settings.extraction_wide_grid_min_cols
    for t in doc.tables:
        if t.row_count >= min_r and t.col_count >= min_c:
            return True
    return False


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
    search_text = " ".join(p.text for p in doc.pages)
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
