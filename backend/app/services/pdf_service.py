"""
PDF parsing service — enterprise-grade structured extraction.

Extracts rich content from PDFs using PyMuPDF 1.24+:
  - Plain text with layout preservation
  - Tables detected via find_tables() → rendered as Markdown
  - Smart page selection for large documents (>20 pages)
  - Document structure hint classification
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from typing import List, Optional

import fitz  # PyMuPDF >= 1.23


# ── Data models ───────────────────────────────────────────────────────────────

@dataclass
class ParsedTable:
    page_num: int
    row_count: int
    col_count: int
    markdown: str  # Markdown representation for LLM context


@dataclass
class ParsedPage:
    page_num: int       # 1-indexed
    text: str           # plain text (layout-preserved)
    tables: List[ParsedTable]
    word_count: int
    has_numbers: bool   # contains currency / numeric patterns
    has_dates: bool     # contains date patterns


@dataclass
class ParsedDocument:
    filename: str
    file_path: str
    page_count: int
    pages: List[ParsedPage]
    tables: List[ParsedTable]   # all tables across all pages
    content_text: str           # LLM-ready text (smart-selected, ≤15 000 chars)
    tables_markdown: str        # all tables as Markdown (≤8 000 chars)
    doc_type_hint: str          # 'dense_tables' | 'form' | 'narrative' | 'mixed'
    has_tables: bool


# ── Regex helpers ─────────────────────────────────────────────────────────────

_DATE_RE = re.compile(
    r'\b\d{1,2}[/\-\.]\d{1,2}[/\-\.]\d{2,4}\b'
    r'|\b\d{4}[/\-\.]\d{1,2}[/\-\.]\d{1,2}\b'
    r'|\b(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\.?\s+\d{1,2},?\s+\d{4}\b',
    re.I,
)
_NUM_RE = re.compile(
    r'[\$£€]\s*[\d,]+'
    r'|[\d,]+\.\d{2}\b'
    r'|\b\d{1,3}(?:,\d{3})+\b'
)


# ── Table → Markdown ──────────────────────────────────────────────────────────

def _table_to_markdown(cells: list) -> str:
    """Convert a 2-D list of cells to a Markdown table string."""
    if not cells:
        return ""
    rows = [[str(c or "").strip() for c in row] for row in cells]
    if not rows:
        return ""
    header = rows[0]
    sep = ["---"] * len(header)
    lines = [
        "| " + " | ".join(header) + " |",
        "| " + " | ".join(sep) + " |",
    ]
    for row in rows[1:]:
        padded = row[: len(header)] + [""] * max(0, len(header) - len(row))
        lines.append("| " + " | ".join(padded) + " |")
    return "\n".join(lines)


# ── Page scoring for smart selection ─────────────────────────────────────────

def _score_page(page: ParsedPage) -> float:
    """Higher score = more information dense. Used for large-doc page selection."""
    score = page.word_count * 0.5
    if page.has_numbers:
        score += 40
    if page.has_dates:
        score += 30
    score += len(page.tables) * 60
    return score


# ── Document structure classification ────────────────────────────────────────

def _classify_doc_hint(pages: List[ParsedPage], tables: List[ParsedTable]) -> str:
    table_rows = sum(t.row_count for t in tables)
    if len(tables) >= 3 or table_rows >= 10:
        return "dense_tables"
    # Check for form-like key: value patterns
    form_hits = 0
    for p in pages[:4]:
        form_hits += len(re.findall(r'^\s*[\w\s]{2,30}:\s+\S', p.text, re.M))
    if form_hits >= 6:
        return "form"
    if tables:
        return "mixed"
    return "narrative"


# ── Constants ─────────────────────────────────────────────────────────────────

_MAX_CONTENT_CHARS = 32_000
_MAX_TABLE_CHARS = 8_000
_CHARS_PER_PAGE = 1_200      # per-page budget when building content_text
_MAX_SELECTED_PAGES = 25


# ── Public API ────────────────────────────────────────────────────────────────

def parse_pdf(file_path: str, filename: str = "") -> ParsedDocument:
    """
    Parse a PDF into a structured ParsedDocument ready for LLM extraction.

    Features:
    - Table detection via PyMuPDF find_tables() (PyMuPDF >= 1.23)
    - Smart page selection for docs > 20 pages
    - Document structure hint classification
    """
    if not filename:
        filename = os.path.basename(file_path)

    doc = fitz.open(file_path)
    pages: List[ParsedPage] = []
    all_tables: List[ParsedTable] = []

    for page_num in range(len(doc)):
        page = doc[page_num]
        text = page.get_text("text").strip()

        # Extract tables via PyMuPDF find_tables
        page_tables: List[ParsedTable] = []
        try:
            tab_finder = page.find_tables()
            for tab in tab_finder.tables:
                cells = tab.extract()
                if not cells or len(cells) < 2:  # skip empty / header-only
                    continue
                md = _table_to_markdown(cells)
                pt = ParsedTable(
                    page_num=page_num + 1,
                    row_count=len(cells),
                    col_count=len(cells[0]) if cells else 0,
                    markdown=md,
                )
                page_tables.append(pt)
                all_tables.append(pt)
        except Exception:
            pass  # find_tables unavailable — degrade gracefully

        parsed = ParsedPage(
            page_num=page_num + 1,
            text=text,
            tables=page_tables,
            word_count=len(text.split()),
            has_numbers=bool(_NUM_RE.search(text)),
            has_dates=bool(_DATE_RE.search(text)),
        )
        pages.append(parsed)

    doc.close()

    page_count = len(pages)

    # Smart page selection for large docs
    if page_count <= 20:
        selected = pages
    else:
        first_three = pages[:3]
        remainder = pages[3:]

        # Uniform sampling — guarantees every section of the doc is represented
        # (critical for financial statements that appear mid/late in large filings)
        n_uniform = 12
        step = max(1, len(remainder) // n_uniform)
        uniform = remainder[::step][:n_uniform]

        # Top-scored pages for data-dense content
        top_scored = sorted(remainder, key=_score_page, reverse=True)[:10]

        combined = {p.page_num: p for p in first_three + uniform + top_scored}
        selected = sorted(combined.values(), key=lambda p: p.page_num)
        selected = selected[:_MAX_SELECTED_PAGES]

    # Build content_text within budget
    content_parts: List[str] = []
    budget = _MAX_CONTENT_CHARS
    for p in selected:
        if budget <= 0:
            break
        chunk = f"=== Page {p.page_num} ===\n{p.text}"[:_CHARS_PER_PAGE]
        content_parts.append(chunk)
        budget -= len(chunk)

    content_text = "\n\n".join(content_parts)[:_MAX_CONTENT_CHARS]

    # Build tables_markdown within budget
    table_parts: List[str] = []
    tbudget = _MAX_TABLE_CHARS
    for t in all_tables:
        if tbudget <= 0:
            break
        entry = f"[Table — page {t.page_num}, {t.row_count} rows × {t.col_count} cols]\n{t.markdown}"
        table_parts.append(entry[:2_000])
        tbudget -= len(entry)

    tables_markdown = "\n\n".join(table_parts)[:_MAX_TABLE_CHARS]

    doc_type_hint = _classify_doc_hint(pages, all_tables)

    return ParsedDocument(
        filename=filename,
        file_path=file_path,
        page_count=page_count,
        pages=pages,
        tables=all_tables,
        content_text=content_text,
        tables_markdown=tables_markdown,
        doc_type_hint=doc_type_hint,
        has_tables=len(all_tables) > 0,
    )


def get_pdf_page_count(file_path: str) -> int:
    """Get number of pages in a PDF."""
    doc = fitz.open(file_path)
    count = len(doc)
    doc.close()
    return count
