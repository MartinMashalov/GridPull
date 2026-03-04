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
            ├─ multi-record cues in OCR output + >8 pages → chunked (6 pages/call, concurrent)
            ├─ multi-record cues                          → single gpt-4.1-mini call
            └─ single-record                              → single gpt-4.1-mini call

  doc NOT scanned
      ├─ doc_type in _SINGLE_RECORD_TYPES   → single-record  (gpt-4.1-mini)
      ├─ data table + ≤8 pages              → multi-record   (gpt-4.1-mini, 30k table budget)
      ├─ data table + >8 pages              → chunked multi  (gpt-4.1-mini, 6 pages/call, concurrent)
      └─ else                               → single-record  (gpt-4.1-mini)
─────────────────────────────────────────────────────────────────────────────
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
from dataclasses import dataclass, field
from typing import Any, Dict, List

from openai import AsyncOpenAI

from app.config import settings
from app.services.pdf_service import ParsedDocument

logger = logging.getLogger(__name__)

# ── Model names ───────────────────────────────────────────────────────────────
_TEXT_MODEL   = "gpt-4.1-mini"   # TEXT pipeline
_VISION_MODEL = "gpt-4.1-mini"   # SCAN pipeline (via litellm)
_OCR_MODEL    = "mistral-ocr-latest"

# ── Pricing (USD per token / per page) ───────────────────────────────────────
_TEXT_IN_PRICE    = 0.40  / 1_000_000   # gpt-4.1-mini input
_TEXT_OUT_PRICE   = 1.60  / 1_000_000   # gpt-4.1-mini output
_VISION_IN_PRICE  = 0.40  / 1_000_000   # gpt-4.1-mini input
_VISION_OUT_PRICE = 1.60  / 1_000_000   # gpt-4.1-mini output
_OCR_PAGE_PRICE   = 0.001               # Mistral OCR per page
_MARKUP           = 1.20                # 20% markup applied to all costs

# ── Extraction routing constants ──────────────────────────────────────────────
_CHUNK_THRESHOLD_PAGES = 8   # switch to chunked extraction above this
_CHUNK_SIZE            = 6   # pages per extraction chunk

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
                   → ocr_pages                            (Mistral OCR)
    """
    input_tokens:         int = 0
    output_tokens:        int = 0
    vision_input_tokens:  int = 0
    vision_output_tokens: int = 0
    ocr_pages:            int = 0

    def add(self, prompt_tokens: int, completion_tokens: int) -> None:
        """Record gpt-4o-mini token usage."""
        self.input_tokens  += prompt_tokens
        self.output_tokens += completion_tokens

    def add_vision(self, prompt_tokens: int, completion_tokens: int) -> None:
        """Record gpt-4.1-mini token usage."""
        self.vision_input_tokens  += prompt_tokens
        self.vision_output_tokens += completion_tokens

    @property
    def cost_usd(self) -> float:
        """Total cost in USD including the 20% markup."""
        base = (
            self.input_tokens         * _TEXT_IN_PRICE
            + self.output_tokens      * _TEXT_OUT_PRICE
            + self.vision_input_tokens  * _VISION_IN_PRICE
            + self.vision_output_tokens * _VISION_OUT_PRICE
            + self.ocr_pages          * _OCR_PAGE_PRICE
        )
        return round(base * _MARKUP, 6)


# ─────────────────────────────────────────────────────────────────────────────
# Document type catalogue & classification
# ─────────────────────────────────────────────────────────────────────────────

_DOC_TYPE_DESCRIPTIONS: Dict[str, str] = {
    "invoice":          "invoice, bill, or vendor statement with line items and payment details",
    "purchase_order":   "purchase order, solicitation, contract award, or government procurement form",
    "financial_report": "annual report, quarterly report, shareholder letter, or earnings release",
    "sec_10k":          "SEC 10-K annual filing with MD&A, financial statements, and risk factors",
    "insurance_eob":    "insurance Explanation of Benefits (EOB), Summary of Benefits, or claims document",
    "tax_form":         "tax return, W-2, 1099, or government tax document",
    "contract":         "legal contract, service agreement, or lease",
    "generic":          "general document not matching the above categories",
}

_FAST_RULES: List[tuple] = [
    (r'invoice|bill\s+to|amount\s+due|remit\s+to|invoice\s+#',              "invoice"),
    (r'purchase\s+order|solicitation|contract\s+award|bid\s+bond|sf\s*-?\s*\d{2,4}', "purchase_order"),
    (r'\b10-?k\b|form\s+10-?k',                                             "sec_10k"),
    (r'annual\s+report|quarterly\s+report|shareholder|earnings\s+release',  "financial_report"),
    (r'explanation\s+of\s+benefits|eob\b|summary\s+of\s+benefits|claim[s]?\s+number|member\s+id', "insurance_eob"),
    (r'\bw-?2\b|\b1099\b|form\s+\d{4}|tax\s+return',                       "tax_form"),
]


def _fast_classify(filename: str, first_page_text: str) -> str | None:
    combined = (filename + "\n" + first_page_text[:2_000]).lower()
    for pattern, doc_type in _FAST_RULES:
        if re.search(pattern, combined, re.I):
            return doc_type
    return None


async def _llm_classify(filename: str, first_page_text: str, usage: LLMUsage) -> str:
    types_block = "\n".join(f"  {k}: {v}" for k, v in _DOC_TYPE_DESCRIPTIONS.items())
    prompt = (
        f"Classify this document. Reply with ONLY the type key, nothing else.\n\n"
        f"Filename: {filename}\nFirst page:\n{first_page_text[:1_500]}\n\nTypes:\n{types_block}"
    )
    try:
        resp = await _openai.chat.completions.create(
            model=_TEXT_MODEL,
            messages=[{"role": "user", "content": prompt}],
            temperature=0,
            max_tokens=10,
        )
        if resp.usage:
            usage.add(resp.usage.prompt_tokens, resp.usage.completion_tokens)
        raw = resp.choices[0].message.content.strip().strip('"').lower()
        return raw if raw in _DOC_TYPE_DESCRIPTIONS else "generic"
    except Exception:
        return "generic"


async def classify_document(doc: ParsedDocument, usage: LLMUsage) -> str:
    first_text = doc.pages[0].text if doc.pages else ""
    fast = _fast_classify(doc.filename, first_text)
    if fast:
        return fast
    return await _llm_classify(doc.filename, first_text, usage)


# ─────────────────────────────────────────────────────────────────────────────
# Prompt helpers
# ─────────────────────────────────────────────────────────────────────────────

def _fields_block(fields: List[Dict[str, str]]) -> str:
    lines = []
    for f in fields:
        name = f["name"]
        desc = f.get("description", "")
        lines.append(f"  - {name}: {desc}" if desc and desc != name else f"  - {name}")
    return "\n".join(lines)


def _doc_context_block(doc: ParsedDocument, doc_type: str) -> str:
    parts = [
        f"Filename: {doc.filename}",
        f"Document type: {_DOC_TYPE_DESCRIPTIONS.get(doc_type, 'general document')}",
        f"Total pages: {doc.page_count}",
    ]
    if doc.has_tables:
        parts.append(f"Tables detected: {len(doc.tables)}")
    return "\n".join(parts)


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
    "- If a field description explains how to compute the value (e.g. a ratio or margin), "
    "calculate it from the available data in the document and return the computed result\n"
    "- Do not hallucinate values that cannot be found or computed from the document\n"
    "- Financial terminology synonyms — match these even if the label differs:\n"
    "  * Revenue = Sales = Net Sales = Total Sales = Sales to customers = Net revenues = "
    "Total revenues = Net Revenue = Total Net Revenue = "
    "Net interest income + Noninterest revenue (for banks)\n"
    "  * Net Income = Net Earnings = Net profit = Profit for the year = Net income attributable to common stockholders\n"
    "  * Operating Income = Operating Earnings = Operating profit = Income from operations\n"
    "  * Total Assets = Total assets\n"
    "  * Equity = Shareholders equity = Stockholders equity = Total equity = Common equity\n"
    "  * Debt = Total Debt = Long-term debt = Long-term borrowings = Total borrowings = "
    "Notes payable = Senior notes = Subordinated notes = Bonds payable = "
    "Short-term borrowings + Long-term debt (sum both if no single 'Total debt' line exists)\n"
    "- Response format: {\"records\": [{\"Field Name\": \"value\", ...}]}"
)

_MULTI_SYSTEM = (
    "You are a precise data extraction assistant for enterprise document processing.\n"
    "This document contains tabular data. Extract ALL data rows and return a JSON "
    "object with key \"records\" containing an array — one object per data row.\n"
    "Rules:\n"
    "- Skip header rows; only include data rows\n"
    "- Use null for fields not present in a given row\n"
    "- For money: report the value exactly as it appears in the cell; do NOT append "
    "unit words (million/billion) from table headers — only include units literally in the cell\n"
    "- For dates: use the format as written in the document\n"
    "- Extract ALL rows (no truncation)\n"
    "- Do not infer or hallucinate values\n"
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
    "- If a field description explains how to compute the value (e.g. a ratio or margin), "
    "calculate it from the available data and return the computed result\n"
    "- Do not hallucinate — only extract what is present\n"
    "- Financial terminology synonyms — match these even if the label differs:\n"
    "  * Revenue = Sales = Net Sales = Total Sales = Net revenues = Total revenues = "
    "Net interest income + Noninterest revenue (for banks)\n"
    "  * Net Income = Net Earnings = Net profit = Profit for the year\n"
    "  * Operating Income = Operating Earnings = Operating profit = Income from operations\n"
    "  * Total Assets = Total assets\n"
    "  * Equity = Shareholders equity = Stockholders equity = Total equity = Common equity\n"
    "  * Debt = Total Debt = Long-term debt = Long-term borrowings = Total borrowings = "
    "Notes payable = Senior notes = Bonds payable = "
    "Short-term borrowings + Long-term debt (sum both if no single 'Total debt' line exists)\n"
    "- Response format: {\"records\": [{\"Field Name\": \"value\", ...}]}"
)

_SCAN_MULTI_SYSTEM = (
    "You are a precise data extraction assistant working with OCR-processed text.\n"
    "The input text was extracted from a scanned document by Mistral OCR — "
    "it may contain minor OCR artefacts. Apply judgment to recover correct values.\n"
    "This document contains tabular data. Extract ALL data rows.\n"
    "Rules:\n"
    "- Skip header rows; only include data rows\n"
    "- Use null for fields not present in a given row\n"
    "- Extract ALL rows (no truncation)\n"
    "- Do not hallucinate values\n"
    "- Response format: {\"records\": [{\"Field\": \"value\"}, ...]}"
)


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
    import litellm  # lazy import — only used for scanned docs

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


# ─────────────────────────────────────────────────────────────────────────────
# Financial page targeting (TEXT pipeline, single-record)
# ─────────────────────────────────────────────────────────────────────────────

_FINANCIAL_KEYWORDS = [
    "balance sheet", "statement of earnings", "income statement",
    "statement of operations", "total assets", "total revenues",
    "total revenue", "shareholders' equity", "shareholders equity",
    "stockholders' equity", "stockholders equity", "total equity",
    "net income", "net earnings", "operating earnings", "operating income",
    "total liabilities", "net revenues",
    # Sales-based revenue terminology (J&J, P&G, consumer companies)
    "sales to customers", "net sales", "total sales", "sales and revenues",
    "revenues and sales", "product sales", "service revenues",
    # Additional financial statement headers
    "consolidated statements", "statement of income", "statement of profit",
    "profit and loss", "earnings per share", "diluted earnings",
    # Bank-specific terminology
    "net interest income", "noninterest income", "noninterest revenue",
    "interest expense", "provision for credit losses", "net charge-offs",
    "long-term debt", "short-term borrowings", "federal funds",
    "loans and leases", "total deposits", "tier 1 capital",
    # Insurance-specific terminology
    "premiums earned", "net premiums", "claims and benefits",
    "policyholder benefits", "loss ratio", "combined ratio",
    "underwriting income", "net investment income",
    # REIT-specific
    "funds from operations", "net operating income", "same-store",
]

_MAX_FINANCIAL_PAGES   = 14   # 2 cover + up to 12 financial statement pages
_TOP_KEYWORD_PAGES     = 10   # top-N keyword-scored pages (up from 5)
_FINANCIAL_PAGE_CHARS  = 1_800
_FINANCIAL_CONTENT_BUDGET = 28_000
_FINANCIAL_TABLE_BUDGET   = 12_000


def _build_financial_content(doc: ParsedDocument) -> tuple[str, str]:
    """
    For financial documents: select pages by keyword density + first 2 pages.

    Pages ranked by total _FINANCIAL_KEYWORDS density, capped at _TOP_KEYWORD_PAGES.
    Always include the first 2 pages (cover / shareholder letter summary).

    Total budget: max 14 pages × 1800 chars = 25k text + 12k tables ≈ 9k tokens.
    """
    keyword_scored: list[tuple[int, "ParsedPage"]] = []

    for p in doc.pages:
        text_lower = p.text.lower()
        kw_count   = sum(1 for kw in _FINANCIAL_KEYWORDS if kw in text_lower)
        if kw_count > 0:
            keyword_scored.append((kw_count, p))

    keyword_scored.sort(key=lambda x: x[0], reverse=True)

    first_two   = {p.page_num: p for p in doc.pages[:2]}
    top_keyword = {p.page_num: p for _, p in keyword_scored[:_TOP_KEYWORD_PAGES]}
    combined    = {**first_two, **top_keyword}
    selected    = sorted(combined.values(), key=lambda p: p.page_num)[:_MAX_FINANCIAL_PAGES]

    content_parts: list[str] = []
    budget = _FINANCIAL_CONTENT_BUDGET
    for p in selected:
        if budget <= 0:
            break
        chunk = f"=== Page {p.page_num} ===\n{p.text}"[:_FINANCIAL_PAGE_CHARS]
        content_parts.append(chunk)
        budget -= len(chunk)

    content_text = "\n\n".join(content_parts)[:_FINANCIAL_CONTENT_BUDGET]

    # Include ALL detected tables (not just from selected pages) so balance-sheet
    # tables on pages just outside the text window are still visible to the LLM.
    page_nums  = {p.page_num for p in selected}
    # Sort: selected-page tables first (most relevant), then extras
    fin_tables = (
        [t for t in doc.tables if t.page_num in page_nums]
        + [t for t in doc.tables if t.page_num not in page_nums]
    )
    table_parts: list[str] = []
    tbudget = _FINANCIAL_TABLE_BUDGET
    for t in fin_tables:
        if tbudget <= 0:
            break
        entry = f"[Table — page {t.page_num}]\n{t.markdown}"
        table_parts.append(entry[:2_500])
        tbudget -= len(entry)

    return content_text, "\n\n".join(table_parts)[:_FINANCIAL_TABLE_BUDGET]


# ─────────────────────────────────────────────────────────────────────────────
# TEXT pipeline — extractors
# ─────────────────────────────────────────────────────────────────────────────

async def extract_single_record(
    doc: ParsedDocument,
    fields: List[Dict[str, str]],
    doc_type: str,
    usage: LLMUsage,
) -> List[Dict[str, Any]]:
    """Extract one record per document (invoice header, contract, annual report…)."""
    field_names = [f["name"] for f in fields]
    ctx   = _doc_context_block(doc, doc_type)
    fblock = _fields_block(fields)

    is_financial = doc_type in ("financial_report", "sec_10k")
    if is_financial and doc.page_count > 20:
        content_text, tables_markdown = _build_financial_content(doc)
    else:
        content_text, tables_markdown = doc.content_text, doc.tables_markdown

    reporting_unit = _detect_reporting_unit(doc) if is_financial else None

    parts = [
        f"--- Document Info ---\n{ctx}",
        f"\n--- Fields to Extract ---\n{fblock}",
    ]
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
    return await _llm_extract(_SINGLE_SYSTEM, user_prompt, field_names, doc.filename, usage)


async def extract_multi_record(
    doc: ParsedDocument,
    fields: List[Dict[str, str]],
    doc_type: str,
    usage: LLMUsage,
) -> List[Dict[str, Any]]:
    """
    Extract multiple records from a short multi-record document (≤ _CHUNK_THRESHOLD_PAGES).
    Uses full 30k table budget instead of the 8k-capped doc.tables_markdown.
    """
    field_names = [f["name"] for f in fields]
    ctx    = _doc_context_block(doc, doc_type)
    fblock = _fields_block(fields)

    # Rebuild table markdown at full budget — tables are the primary data source
    table_parts, tbudget = [], 30_000
    for t in doc.tables:
        entry = f"[Table — page {t.page_num}, {t.row_count}×{t.col_count}]\n{t.markdown}"
        table_parts.append(entry[:3_000])
        tbudget -= len(entry)
        if tbudget <= 0:
            break
    full_tables_md = "\n\n".join(table_parts)

    parts = [
        f"--- Document Info ---\n{ctx}",
        f"\n--- Fields to Extract (one object per data row) ---\n{fblock}",
    ]
    if full_tables_md:
        parts.append(f"\n--- Detected Tables ---\n{full_tables_md}")
    parts.append(f"\n--- Document Text ---\n{doc.content_text}")

    user_prompt = (
        "\n".join(parts)
        + '\n\nReturn: {"records": [{"Field": "value"}, ...]}'
    )
    return await _llm_extract(_MULTI_SYSTEM, user_prompt, field_names, doc.filename, usage)


async def extract_multi_record_chunked(
    doc: ParsedDocument,
    fields: List[Dict[str, str]],
    doc_type: str,
    usage: LLMUsage,
) -> List[Dict[str, Any]]:
    """
    Page-by-page extraction for long multi-record documents (> _CHUNK_THRESHOLD_PAGES).
    Splits pages into chunks of _CHUNK_SIZE and runs all chunks concurrently.
    Prevents row truncation on bank statements, payroll reports, etc.
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
        )[:20_000]
        tables_md = "\n\n".join(
            f"[Table — page {t.page_num}, {t.row_count}×{t.col_count}]\n{t.markdown}"
            for t in doc.tables if t.page_num in page_nums
        )[:10_000]

        parts = [
            f"--- Document Info ---\n"
            f"Filename: {doc.filename}\nTotal pages: {doc.page_count}\n"
            f"Extracting: pages {first_pg}–{last_pg}",
            f"\n--- Fields (one object per data row) ---\n{fblock}",
        ]
        if tables_md:
            parts.append(f"\n--- Tables (pages {first_pg}–{last_pg}) ---\n{tables_md}")
        parts.append(f"\n--- Text (pages {first_pg}–{last_pg}) ---\n{chunk_text}")

        prompt = (
            "\n".join(parts)
            + "\n\nExtract ALL data rows on these pages only. "
            + 'Return: {"records": [...]}. No rows here → {"records": []}.'
        )
        return await _llm_extract(_MULTI_SYSTEM, prompt, field_names, doc.filename, usage)

    chunk_results = await asyncio.gather(*[_extract_chunk(c) for c in page_chunks])

    all_rows: List[Dict[str, Any]] = []
    for rows in chunk_results:
        all_rows.extend(r for r in rows if any(r.get(fn) for fn in field_names))

    return all_rows if all_rows else _empty([doc.filename], field_names)


# ─────────────────────────────────────────────────────────────────────────────
# SCAN pipeline — OCR + gpt-4.1-mini extractors
# ─────────────────────────────────────────────────────────────────────────────

# Markdown table line regex — Mistral OCR renders tables as markdown
_MD_TABLE_ROW_RE = re.compile(r"^\|.+\|", re.M)


def _ocr_is_multi_record(ocr_text: str) -> bool:
    """
    Return True if the OCR output contains enough markdown table rows to
    suggest the document has multiple data records to extract.
    Threshold: ≥6 pipe-delimited lines (1 header + 1 separator + 4 data rows).
    """
    return len(_MD_TABLE_ROW_RE.findall(ocr_text)) >= 6


async def _extract_scanned_chunked(
    ocr_text: str,
    doc: ParsedDocument,
    fields: List[Dict[str, str]],
    field_names: List[str],
    fblock: str,
    usage: LLMUsage,
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
        chunk_text = "\n\n".join(chunk_pages)[:20_000]
        prompt = (
            f"--- Document Info ---\n"
            f"Filename: {doc.filename}\nTotal pages: {doc.page_count}\n"
            f"Source: Scanned document (OCR by Mistral)\n\n"
            f"--- Fields (one object per data row) ---\n{fblock}\n\n"
            f"--- OCR Text (this chunk) ---\n{chunk_text}\n\n"
            'Extract ALL data rows in this chunk. '
            'Return: {"records": [...]}. No rows here → {"records": []}.'
        )
        return await _litellm_extract(_SCAN_MULTI_SYSTEM, prompt, field_names, doc.filename, usage)

    chunk_results = await asyncio.gather(*[_chunk_task(c) for c in chunks])

    all_rows: List[Dict[str, Any]] = []
    for rows in chunk_results:
        all_rows.extend(r for r in rows if any(r.get(fn) for fn in field_names))

    return all_rows if all_rows else _empty([doc.filename], field_names)


async def extract_from_scanned_document(
    doc: ParsedDocument,
    fields: List[Dict[str, str]],
    usage: LLMUsage,
) -> List[Dict[str, Any]]:
    """
    SCAN pipeline entry point.

    Step 1 — Mistral OCR: converts the scanned PDF to full markdown text,
              preserving tables, columns, and layout.
    Step 2 — Route: detect multi-record (markdown tables in OCR output) vs
              single-record.
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
        return await extract_single_record(doc, fields, "generic", usage)

    logger.info(
        "SCAN pipeline — Mistral OCR starting: %s (%d pages)",
        doc.filename, doc.page_count,
    )

    try:
        ocr_text, ocr_page_count = await run_mistral_ocr(doc.file_path, settings.mistral_api_key)
        usage.ocr_pages += ocr_page_count
        logger.info(
            "SCAN pipeline — OCR complete: %s — %d pages, %d chars",
            doc.filename, ocr_page_count, len(ocr_text),
        )
    except Exception as exc:
        logger.error(
            "SCAN pipeline — OCR failed for %s: %s — falling back to TEXT pipeline",
            doc.filename, exc,
        )
        return await extract_single_record(doc, fields, "generic", usage)

    field_names = [f["name"] for f in fields]
    fblock      = _fields_block(fields)
    is_multi    = _ocr_is_multi_record(ocr_text)

    if is_multi and doc.page_count > _CHUNK_THRESHOLD_PAGES:
        logger.info("SCAN pipeline — chunked multi-record: %s", doc.filename)
        return await _extract_scanned_chunked(
            ocr_text, doc, fields, field_names, fblock, usage
        )

    ctx = (
        f"Filename: {doc.filename}\n"
        f"Total pages: {doc.page_count}\n"
        f"Source: Scanned document (OCR by Mistral)"
    )

    if is_multi:
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
        f"--- OCR Text (Mistral OCR) ---\n{ocr_text[:30_000]}\n\n"
        + instruction
    )

    return await _litellm_extract(system, user_prompt, field_names, doc.filename, usage)


# ─────────────────────────────────────────────────────────────────────────────
# TEXT pipeline routing
# ─────────────────────────────────────────────────────────────────────────────

# Doc types where the user wants document-level fields, not per-row extraction,
# even when the document contains tables.
_SINGLE_RECORD_TYPES = {"financial_report", "sec_10k", "tax_form", "contract"}


def _should_extract_multi(doc: ParsedDocument, doc_type: str) -> bool:
    """
    Return True if this native (non-scanned) document should produce multiple rows.

    Triggers when:
    - doc_type is NOT in _SINGLE_RECORD_TYPES (those always want one row)
    - At least one table has ≥4 rows AND ≥2 cols
      (≥4 rows rules out single-row summary cells; ≥2 cols rules out bare lists)
    """
    if doc_type in _SINGLE_RECORD_TYPES:
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
          ├─ _SINGLE_RECORD_TYPES        → single-record
          ├─ data table + ≤8 pages       → multi-record   (30k table budget)
          ├─ data table + >8 pages       → chunked multi  (6 pages/call, concurrent)
          └─ else                        → single-record
    """
    if doc.is_scanned:
        logger.info(
            "Routing %s → SCAN pipeline (avg_chars_per_page=%.0f)",
            doc.filename,
            sum(len(p.text) for p in doc.pages) / max(len(doc.pages), 1),
        )
        rows = await extract_from_scanned_document(doc, fields, usage)

    else:
        doc_type = await classify_document(doc, usage)
        logger.info(
            "Routing %s → TEXT pipeline (type=%s hint=%s)",
            doc.filename, doc_type, doc.doc_type_hint,
        )

        if _should_extract_multi(doc, doc_type):
            if doc.page_count > _CHUNK_THRESHOLD_PAGES:
                n_chunks = -(-doc.page_count // _CHUNK_SIZE)  # ceiling division
                logger.info(
                    "TEXT chunked multi-record: %s (%d pages, %d chunks)",
                    doc.filename, doc.page_count, n_chunks,
                )
                rows = await extract_multi_record_chunked(doc, fields, doc_type, usage)
            else:
                rows = await extract_multi_record(doc, fields, doc_type, usage)
        else:
            rows = await extract_single_record(doc, fields, doc_type, usage)

    if not rows:
        field_names = [f["name"] for f in fields]
        rows = _empty([doc.filename], field_names)

    return rows
