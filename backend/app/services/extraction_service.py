"""
Extraction service — enterprise-grade LLM-powered field extraction.

Strategy:
  1. Classify document type from filename + first-page text (rule-based fast path,
     LLM fallback).
  2. Route to single-record or multi-record extraction based on doc type + table
     content.
  3. Always return List[Dict] so the pipeline is uniform.
       Single-record:  [one dict per document]
       Multi-record:   [one dict per table row / line item]

Model: gpt-4o-mini exclusively — fastest, cheapest, capable with good prompts.
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Tuple

from openai import AsyncOpenAI

from app.config import settings
from app.services.pdf_service import ParsedDocument

logger = logging.getLogger(__name__)
client = AsyncOpenAI(api_key=settings.openai_api_key)

_MODEL = "gpt-4o-mini"

# GPT-4o-mini pricing (USD per token) — matches litellm / OpenAI published rates
_INPUT_PRICE_PER_TOKEN = 0.15 / 1_000_000   # $0.15 / 1M input tokens
_OUTPUT_PRICE_PER_TOKEN = 0.60 / 1_000_000  # $0.60 / 1M output tokens
_MARKUP = 1.20  # 20% markup


@dataclass
class LLMUsage:
    """Accumulates token usage across all LLM calls in one extraction job."""
    input_tokens: int = 0
    output_tokens: int = 0

    def add(self, prompt_tokens: int, completion_tokens: int) -> None:
        self.input_tokens += prompt_tokens
        self.output_tokens += completion_tokens

    @property
    def cost_usd(self) -> float:
        """Total cost in USD including the 20% markup."""
        base = (self.input_tokens * _INPUT_PRICE_PER_TOKEN +
                self.output_tokens * _OUTPUT_PRICE_PER_TOKEN)
        return round(base * _MARKUP, 6)


# ── Document type catalogue ───────────────────────────────────────────────────

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

# Fast rule-based pre-classification patterns  (pattern, doc_type)
_FAST_RULES: List[tuple] = [
    (r'invoice|bill\s+to|amount\s+due|remit\s+to|invoice\s+#', "invoice"),
    (r'purchase\s+order|solicitation|contract\s+award|bid\s+bond|sf\s*-?\s*\d{2,4}', "purchase_order"),
    (r'\b10-?k\b|form\s+10-?k', "sec_10k"),
    (r'annual\s+report|quarterly\s+report|shareholder|earnings\s+release', "financial_report"),
    (r'explanation\s+of\s+benefits|eob\b|summary\s+of\s+benefits|claim[s]?\s+number|member\s+id', "insurance_eob"),
    (r'\bw-?2\b|\b1099\b|form\s+\d{4}|tax\s+return', "tax_form"),
]


def _fast_classify(filename: str, first_page_text: str) -> str | None:
    """Rule-based classification — returns None if inconclusive."""
    combined = (filename + "\n" + first_page_text[:2_000]).lower()
    for pattern, doc_type in _FAST_RULES:
        if re.search(pattern, combined, re.I):
            return doc_type
    return None


async def _llm_classify(filename: str, first_page_text: str, usage: LLMUsage) -> str:
    """LLM fallback classifier."""
    types_block = "\n".join(f"  {k}: {v}" for k, v in _DOC_TYPE_DESCRIPTIONS.items())
    prompt = (
        f"Classify this document. Reply with ONLY the type key, nothing else.\n\n"
        f"Filename: {filename}\n"
        f"First page:\n{first_page_text[:1_500]}\n\n"
        f"Types:\n{types_block}"
    )
    try:
        resp = await client.chat.completions.create(
            model=_MODEL,
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
    """Classify document type — rule-based first, LLM fallback."""
    first_text = doc.pages[0].text if doc.pages else ""
    fast = _fast_classify(doc.filename, first_text)
    if fast:
        return fast
    return await _llm_classify(doc.filename, first_text, usage)


# ── Prompt building helpers ───────────────────────────────────────────────────

def _fields_block(fields: List[Dict[str, str]]) -> str:
    lines = []
    for f in fields:
        name = f["name"]
        desc = f.get("description", "")
        if desc and desc != name:
            lines.append(f"  - {name}: {desc}")
        else:
            lines.append(f"  - {name}")
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


# ── LLM call with JSON parsing ────────────────────────────────────────────────

_SINGLE_SYSTEM = (
    "You are a precise data extraction assistant for enterprise document processing.\n"
    "Extract the requested fields and return a JSON object with key \"records\" "
    "containing an array of extracted objects.\n"
    "Rules:\n"
    "- records array has exactly ONE object for single-document extraction\n"
    "- Use null for fields genuinely not present in the document\n"
    "- For money: keep currency symbol and original formatting (e.g. \"$1,234.56\")\n"
    "- For dates: use the format as written in the document\n"
    "- Do not infer or hallucinate — only extract what is explicitly stated\n"
    "- Response format: {\"records\": [{\"Field Name\": \"value\", ...}]}"
)

_MULTI_SYSTEM = (
    "You are a precise data extraction assistant for enterprise document processing.\n"
    "This document contains tabular data. Extract ALL data rows and return a JSON "
    "object with key \"records\" containing an array — one object per data row.\n"
    "Rules:\n"
    "- Skip header rows; only include data rows\n"
    "- Use null for fields not present in a given row\n"
    "- For money: keep original formatting (e.g. \"$1,234.56\")\n"
    "- For dates: use the format as written in the document\n"
    "- Extract ALL rows (no truncation)\n"
    "- Do not infer or hallucinate values\n"
    "- Response format: {\"records\": [{\"Field\": \"value\"}, ...]}"
)


async def _llm_extract(
    system: str,
    user_prompt: str,
    field_names: List[str],
    filename: str,
    usage: LLMUsage,
) -> List[Dict[str, Any]]:
    """Call the LLM, track token usage, and parse the JSON response."""
    for attempt in range(3):
        try:
            resp = await client.chat.completions.create(
                model=_MODEL,
                messages=[
                    {"role": "system", "content": system},
                    {"role": "user", "content": user_prompt},
                ],
                temperature=0,
                response_format={"type": "json_object"},
                max_tokens=4_096,
            )
            if resp.usage:
                usage.add(resp.usage.prompt_tokens, resp.usage.completion_tokens)
            raw = json.loads(resp.choices[0].message.content)

            # Accept {"records": [...]}, {"rows": [...]}, or bare dict
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
                    norm[fn] = str(val).strip() if val is not None else ""
                norm["_source_file"] = filename
                result.append(norm)

            return result if result else _empty([filename], field_names)

        except Exception as exc:
            if attempt == 2:
                logger.error("Extraction failed for %s: %s", filename, exc)
                return _error([filename], field_names, str(exc))
            await asyncio.sleep(1)

    return _empty([filename], field_names)


def _empty(filenames: List[str], field_names: List[str]) -> List[Dict]:
    return [{fn: "" for fn in field_names} | {"_source_file": filenames[0]}]


def _error(filenames: List[str], field_names: List[str], msg: str) -> List[Dict]:
    return [{fn: "" for fn in field_names} | {"_source_file": filenames[0], "_error": msg}]


# ── Financial document content builder ───────────────────────────────────────

_FINANCIAL_KEYWORDS = [
    "balance sheet", "statement of earnings", "income statement",
    "statement of operations", "total assets", "total revenues",
    "total revenue", "shareholders' equity", "shareholders equity",
    "net income", "net earnings", "operating earnings", "operating income",
    "total liabilities",
]


def _build_financial_content(doc: "ParsedDocument") -> tuple[str, str]:
    """
    For financial documents: scan all pages for financial statement keywords and
    prioritize those pages in the content sent to the LLM.
    Returns (content_text, tables_markdown).
    """
    # Score each page by financial keyword hits
    scored: list[tuple[int, "ParsedPage"]] = []
    for page in doc.pages:
        text_lower = page.text.lower()
        hits = sum(1 for kw in _FINANCIAL_KEYWORDS if kw in text_lower)
        scored.append((hits, page))

    # Sort by financial keyword density (descending)
    scored.sort(key=lambda x: x[0], reverse=True)

    # Take top 15 financial-content pages + first 3 pages (cover/summary)
    first_three = {p.page_num: p for p in doc.pages[:3]}
    top_financial = {p.page_num: p for _, p in scored[:15]}
    combined = {**first_three, **top_financial}
    selected = sorted(combined.values(), key=lambda p: p.page_num)

    content_parts = []
    budget = 32_000
    for p in selected:
        if budget <= 0:
            break
        chunk = f"=== Page {p.page_num} ===\n{p.text}"[:2_000]
        content_parts.append(chunk)
        budget -= len(chunk)

    content_text = "\n\n".join(content_parts)[:32_000]

    # Tables from these pages
    page_nums = {p.page_num for p in selected}
    financial_tables = [t for t in doc.tables if t.page_num in page_nums]
    table_parts = []
    tbudget = 10_000
    for t in financial_tables:
        if tbudget <= 0:
            break
        entry = f"[Table — page {t.page_num}]\n{t.markdown}"
        table_parts.append(entry[:2_000])
        tbudget -= len(entry)

    tables_markdown = "\n\n".join(table_parts)[:10_000]
    return content_text, tables_markdown


# ── Single-record extraction ──────────────────────────────────────────────────

async def extract_single_record(
    doc: ParsedDocument,
    fields: List[Dict[str, str]],
    doc_type: str,
    usage: LLMUsage,
) -> List[Dict[str, Any]]:
    """Extract one record per document (invoice, contract, annual report, etc.)."""
    field_names = [f["name"] for f in fields]
    ctx = _doc_context_block(doc, doc_type)
    fblock = _fields_block(fields)

    # For financial documents: use targeted financial page selection
    if doc_type in ("financial_report", "sec_10k") and doc.page_count > 20:
        content_text, tables_markdown = _build_financial_content(doc)
    else:
        content_text, tables_markdown = doc.content_text, doc.tables_markdown

    parts = [
        f"--- Document Info ---\n{ctx}",
        f"\n--- Fields to Extract ---\n{fblock}",
        f"\n--- Document Text ---\n{content_text}",
    ]
    if tables_markdown:
        parts.append(f"\n--- Detected Tables ---\n{tables_markdown}")

    user_prompt = (
        "\n".join(parts)
        + '\n\nReturn exactly: {"records": [{"Field Name": "value", ...}]}'
    )

    return await _llm_extract(_SINGLE_SYSTEM, user_prompt, field_names, doc.filename, usage)


# ── Multi-record extraction ───────────────────────────────────────────────────

async def extract_multi_record(
    doc: ParsedDocument,
    fields: List[Dict[str, str]],
    doc_type: str,
    usage: LLMUsage,
) -> List[Dict[str, Any]]:
    """Extract multiple records from a document with tabular data."""
    field_names = [f["name"] for f in fields]
    ctx = _doc_context_block(doc, doc_type)
    fblock = _fields_block(fields)

    parts = [
        f"--- Document Info ---\n{ctx}",
        f"\n--- Fields to Extract (one object per data row) ---\n{fblock}",
    ]
    if doc.tables_markdown:
        parts.append(f"\n--- Detected Tables ---\n{doc.tables_markdown}")
    parts.append(f"\n--- Document Text ---\n{doc.content_text}")

    user_prompt = (
        "\n".join(parts)
        + '\n\nReturn: {"records": [{"Field": "value"}, {"Field": "value"}, ...]}'
    )

    return await _llm_extract(_MULTI_SYSTEM, user_prompt, field_names, doc.filename, usage)


# ── Routing logic ─────────────────────────────────────────────────────────────

# Doc types that always use single-record strategy (they have tables but
# the user wants document-level fields, not row-per-line-item)
_SINGLE_RECORD_TYPES = {"financial_report", "sec_10k", "tax_form", "contract"}


def _should_extract_multi(doc: ParsedDocument, doc_type: str) -> bool:
    """Return True if this document should yield multiple rows."""
    if doc_type in _SINGLE_RECORD_TYPES:
        return False
    # Only treat as multi-record if doc has "data tables":
    #   - ≥4 rows (real data rows, not just a form label)
    #   - ≥3 columns (distinguishes data grids from 1-2 col form layouts)
    data_tables = [t for t in doc.tables if t.row_count >= 4 and t.col_count >= 3]
    return len(data_tables) >= 1


# ── Main entry point ──────────────────────────────────────────────────────────

async def extract_from_document(
    doc: ParsedDocument,
    fields: List[Dict[str, str]],
    usage: LLMUsage,
) -> List[Dict[str, Any]]:
    """
    Full extraction pipeline for one document.

    Accumulates token usage into `usage` (caller-owned LLMUsage instance).
    Returns List[Dict] — always.
      Single-record docs → list with 1 element.
      Multi-record docs  → list with N elements (one per table row / line item).
    """
    doc_type = await classify_document(doc, usage)
    logger.info("Classified %s as %s (hint: %s)", doc.filename, doc_type, doc.doc_type_hint)

    if _should_extract_multi(doc, doc_type):
        rows = await extract_multi_record(doc, fields, doc_type, usage)
    else:
        rows = await extract_single_record(doc, fields, doc_type, usage)

    if not rows:
        field_names = [f["name"] for f in fields]
        rows = _empty([doc.filename], field_names)

    return rows
