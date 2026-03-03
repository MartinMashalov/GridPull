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
    image_count: int = 0  # number of embedded images on this page


@dataclass
class ParsedDocument:
    filename: str
    file_path: str
    page_count: int
    pages: List[ParsedPage]
    tables: List[ParsedTable]   # all tables across all pages
    content_text: str           # LLM-ready text (smart-selected, ≤32 000 chars)
    tables_markdown: str        # all tables as Markdown (≤8 000 chars)
    doc_type_hint: str          # 'dense_tables' | 'form' | 'narrative' | 'mixed'
    has_tables: bool
    is_scanned: bool = False    # True if PDF appears to be a scan (image-based)


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

def _detect_scan(pages: List[ParsedPage]) -> bool:
    """
    Return True if the PDF is image-based (scanned), not native text.

    Scanned PDFs produce near-zero extractable text via PyMuPDF but have
    embedded image objects on most pages.
    """
    if not pages:
        return False
    avg_chars = sum(len(p.text) for p in pages) / len(pages)
    image_pages = sum(1 for p in pages if p.image_count > 0)
    image_fraction = image_pages / len(pages)
    return avg_chars < 150 and image_fraction >= 0.5


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

_MAX_CONTENT_CHARS  = 32_000
_MAX_TABLE_CHARS    = 8_000
_CHARS_PER_PAGE     = 1_200   # per-page budget when building content_text
_MAX_SELECTED_PAGES = 25

# Two-pass table detection: for large documents only run find_tables() on the
# pages that will actually be used, rather than every page in the file.
# Benchmark: find_tables on 152-page Berkshire PDF = 38 s all pages vs 2 s × 20 pages.
_TABLE_SCAN_ALL_THRESHOLD = 30   # pages — docs ≤ this get find_tables on every page
_MAX_TABLE_DETECT_PAGES   = 20   # for larger docs, run find_tables on at most this many pages

# Keywords used to score pages for table-detection priority in the fast pass
_TABLE_SCORE_KEYWORDS = [
    "balance", "revenue", "assets", "earnings", "income", "equity",
    "cash", "statement", "liabilities", "operations", "total", "net",
]


# ── Public API ────────────────────────────────────────────────────────────────

_IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".gif", ".tiff", ".bmp", ".webp"}


def parse_pdf(file_path: str, filename: str = "") -> ParsedDocument:
    """
    Parse a PDF or image file into a structured ParsedDocument ready for LLM extraction.

    Supports PDFs and raster images (PNG, JPEG, etc.).  Images are always
    treated as scanned documents and routed to the OCR pipeline.

    Performance optimisation — two-pass table detection for large documents:
      Pass 1  text + image extraction on ALL pages        (always fast, ~0.6s/150 pages)
      Pass 2  find_tables() only on high-value pages      (≤20 pages → ~2-4 s vs 38 s)

    This is 8-10× faster than running find_tables() on every page for large docs
    while maintaining full accuracy because we target the pages the LLM will actually see.
    """
    if not filename:
        filename = os.path.basename(file_path)

    ext = os.path.splitext(filename.lower())[1]
    force_scanned = ext in _IMAGE_EXTENSIONS

    doc = fitz.open(file_path)
    page_count_raw = len(doc)

    # ── Pass 1: fast text + image count for every page ────────────────────────
    raw: list[dict] = []
    for i in range(page_count_raw):
        p = doc[i]
        text = p.get_text("text").strip()
        try:
            image_count = len(p.get_images(full=False))
        except Exception:
            image_count = 0
        raw.append({
            "idx":         i,
            "text":        text,
            "image_count": image_count,
            "word_count":  len(text.split()),
            "has_numbers": bool(_NUM_RE.search(text)),
            "has_dates":   bool(_DATE_RE.search(text)),
        })

    # ── Determine which page indices get find_tables() ────────────────────────
    if page_count_raw <= _TABLE_SCAN_ALL_THRESHOLD:
        table_detect_indices: set[int] = set(range(page_count_raw))
    else:
        # Always include first 3 pages; supplement with highest-scoring pages.
        kw_scored = sorted(
            range(page_count_raw),
            key=lambda i: sum(1 for kw in _TABLE_SCORE_KEYWORDS
                              if kw in raw[i]["text"].lower()),
            reverse=True,
        )
        table_detect_indices = set(range(min(3, page_count_raw)))
        for idx in kw_scored:
            if len(table_detect_indices) >= _MAX_TABLE_DETECT_PAGES:
                break
            table_detect_indices.add(idx)

    # ── Pass 2: find_tables() only on selected indices ────────────────────────
    page_table_map: dict[int, List[ParsedTable]] = {}  # 0-indexed → tables
    all_tables: List[ParsedTable] = []

    for i in sorted(table_detect_indices):
        p = doc[i]
        tbls: List[ParsedTable] = []
        try:
            tab_finder = p.find_tables()
            for tab in tab_finder.tables:
                cells = tab.extract()
                if not cells or len(cells) < 2:
                    continue
                md = _table_to_markdown(cells)
                pt = ParsedTable(
                    page_num=i + 1,
                    row_count=len(cells),
                    col_count=len(cells[0]) if cells else 0,
                    markdown=md,
                )
                tbls.append(pt)
                all_tables.append(pt)
        except Exception:
            pass
        page_table_map[i] = tbls

    doc.close()

    # ── Build ParsedPage list ─────────────────────────────────────────────────
    pages: List[ParsedPage] = []
    for r in raw:
        i = r["idx"]
        pages.append(ParsedPage(
            page_num=i + 1,
            text=r["text"],
            tables=page_table_map.get(i, []),
            word_count=r["word_count"],
            has_numbers=r["has_numbers"],
            has_dates=r["has_dates"],
            image_count=r["image_count"],
        ))

    page_count = len(pages)

    # ── Smart page selection for content_text ─────────────────────────────────
    if page_count <= 20:
        selected = pages
    else:
        first_three = pages[:3]
        remainder   = pages[3:]

        # Uniform sampling — guarantees every section of the doc is represented
        n_uniform = 12
        step    = max(1, len(remainder) // n_uniform)
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
    is_scanned    = force_scanned or _detect_scan(pages)

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
        is_scanned=is_scanned,
    )


def get_pdf_page_count(file_path: str) -> int:
    """Get number of pages in a PDF."""
    doc = fitz.open(file_path)
    count = len(doc)
    doc.close()
    return count
