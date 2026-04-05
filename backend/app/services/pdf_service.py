"""
PDF parsing service — enterprise-grade structured extraction.

Extracts rich content from PDFs using PyMuPDF 1.24+:
  - Plain text with layout preservation
  - Tables detected via find_tables() → rendered as Markdown
  - Smart page selection for large documents (>20 pages)
  - Document structure hint classification
"""

from __future__ import annotations

import logging
import os
import re
import tempfile
from dataclasses import dataclass
from email import policy
from email.parser import BytesParser
from html import unescape
from typing import List
import fitz  # PyMuPDF >= 1.23

logger = logging.getLogger(__name__)


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
    content_text: str           # LLM-ready text from the selected pages
    tables_markdown: str        # all detected tables as Markdown
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

def _detect_scan(pages: List[ParsedPage], file_path: str = "") -> bool:
    """
    Return True if the PDF is image-based (scanned), not native text.

    Heuristics (any match → scanned):
    1. Classic: near-zero text + images on most pages.
    2. OCR-layer: images on most pages + moderate text + large file size.
    3. Invisible-image: no detected image objects but very large file size
       per page with little text — some renderers embed the scan directly
       in the content stream without a separate image XObject.
    """
    if not pages:
        return False
    avg_chars = sum(len(p.text) for p in pages) / len(pages)
    image_pages = sum(1 for p in pages if p.image_count > 0)
    image_fraction = image_pages / len(pages)
    if avg_chars < 150 and image_fraction >= 0.5:
        return True
    if not file_path:
        return False
    try:
        kb_per_page = os.path.getsize(file_path) / 1024 / len(pages)
    except OSError:
        return False
    if image_fraction >= 0.5 and avg_chars < 800 and kb_per_page > 150:
        return True
    if kb_per_page > 200 and avg_chars < 500:
        return True
    return False


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

_MAX_SELECTED_PAGES = 25
_LONG_DOC_HEADER_THRESHOLD = 20
_LONG_DOC_HEADER_TARGETS   = 5

# Two-pass table detection: for large documents only run find_tables() on the
# pages that will actually be used, rather than every page in the file.
# Benchmark: find_tables on 152-page Berkshire PDF = 38 s all pages vs a much
# smaller focused subset on likely financial-statement pages.
_TABLE_SCAN_ALL_THRESHOLD = 30   # pages — docs ≤ this get find_tables on every page
_MAX_TABLE_DETECT_PAGES   = 40   # for larger docs, run find_tables on at most this many pages

# Keywords used to score pages for table-detection priority in the fast pass
_TABLE_SCORE_KEYWORDS = [
    "balance", "revenue", "assets", "earnings", "income", "equity",
    "cash", "statement", "liabilities", "operations", "total", "net",
]


# ── Public API ────────────────────────────────────────────────────────────────

_TEXT_EXTENSIONS = {".txt", ".md", ".markdown", ".html", ".htm", ".json", ".xml"}
_EMAIL_EXTENSIONS = {".eml", ".emlx"}
_OUTLOOK_EXTENSIONS = {".msg"}
_IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".gif", ".tif", ".tiff", ".bmp", ".webp"}

_DOCUMENT_ATTACHMENT_EXTS = {".pdf", ".txt", ".csv", ".md", ".xlsx", ".xls", ".xlsm"}


def _parse_attachment(att_name: str, att_data: bytes) -> "ParsedDocument | None":
    """Write attachment bytes to a temp file and parse through the full parse_pdf pipeline."""
    ext = os.path.splitext(att_name.lower())[1]
    if ext not in _DOCUMENT_ATTACHMENT_EXTS:
        return None
    tmp_path = None
    try:
        fd, tmp_path = tempfile.mkstemp(suffix=ext)
        with os.fdopen(fd, "wb") as f:
            f.write(att_data)
        return parse_pdf(tmp_path, att_name)
    except Exception as e:
        logger.warning("Failed to parse email attachment %s: %s", att_name, e)
        return None


def _merge_attachment_into(base_text_parts: list, attachment_docs: list) -> "tuple[bool, str | None]":
    """
    Return (any_scanned, merged_pdf_path_or_None).
    Appends attachment content_text into base_text_parts in place.
    If any attachment is scanned, merges all scanned PDFs into one temp file for OCR.
    """
    any_scanned = False
    scanned_paths: list[str] = []

    for att_doc in attachment_docs:
        if att_doc.content_text:
            base_text_parts.append(att_doc.content_text)
        if att_doc.is_scanned and att_doc.file_path:
            any_scanned = True
            scanned_paths.append(att_doc.file_path)

    if not any_scanned:
        return False, None

    # Merge all scanned attachment PDFs into one file so the SOV OCR path can process them
    try:
        merged = fitz.open()
        for path in scanned_paths:
            src = fitz.open(path)
            merged.insert_pdf(src)
            src.close()
        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
            merged.save(tmp.name)
            merged_path = tmp.name
        merged.close()
        return True, merged_path
    except Exception as e:
        logger.warning("Failed to merge scanned attachment PDFs: %s", e)
        return True, scanned_paths[0] if scanned_paths else None


def parse_pdf(file_path: str, filename: str = "") -> ParsedDocument:
    """
    Parse a PDF or image file into a structured ParsedDocument ready for LLM extraction.

    Supports PDFs and raster images (PNG, JPEG, etc.).  Images are always
    treated as scanned documents and routed to the OCR pipeline.

    Performance optimisation — two-pass table detection for large documents:
      Pass 1  text + image extraction on ALL pages        (always fast, ~0.6s/150 pages)
      Pass 2  find_tables() only on high-value pages      (focused windows vs 38 s on all pages)

    This is 8-10× faster than running find_tables() on every page for large docs
    while maintaining full accuracy because we target the pages the LLM will actually see.
    """
    if not filename:
        filename = os.path.basename(file_path)

    logger.info("parse_pdf start: filename=%s file_path=%s", filename, file_path)

    ext = os.path.splitext(filename.lower())[1]
    force_scanned = ext in _IMAGE_EXTENSIONS

    if ext in _TEXT_EXTENSIONS or ext in _EMAIL_EXTENSIONS or ext in _OUTLOOK_EXTENSIONS:
        with open(file_path, "rb") as fh:
            raw_bytes = fh.read()

        text = raw_bytes.decode("utf-8", errors="replace")

        if ext in _OUTLOOK_EXTENSIONS:
            try:
                import extract_msg

                message = extract_msg.Message(file_path)
                try:
                    text_parts: list[str] = []
                    header_lines = []
                    for label, value in (
                        ("Subject", message.subject),
                        ("From", message.sender),
                        ("To", message.to),
                        ("Cc", message.cc),
                        ("Bcc", message.bcc),
                        ("Date", str(message.date) if message.date else None),
                    ):
                        if value:
                            header_lines.append(f"{label}: {value}")
                    if header_lines:
                        text_parts.append("\n".join(header_lines))

                    body_text = str(message.body or "").strip()
                    if not body_text and message.htmlBody:
                        html_text = message.htmlBody
                        if isinstance(html_text, bytes):
                            html_text = html_text.decode("utf-8", errors="replace")
                        html_text = re.sub(r"(?is)<(script|style).*?</\1>", " ", html_text)
                        html_text = re.sub(r"(?i)<br\s*/?>", "\n", html_text)
                        html_text = re.sub(r"(?i)</(p|div|li|tr|h[1-6])>", "\n", html_text)
                        body_text = unescape(re.sub(r"<[^>]+>", " ", html_text))
                        body_text = re.sub(r"[ \t]+", " ", body_text)
                        body_text = re.sub(r"\n{3,}", "\n\n", body_text).strip()
                    if body_text:
                        text_parts.append(body_text)

                    attachment_docs: list = []
                    for attachment in message.attachments:
                        att_name = str(
                            getattr(attachment, "longFilename", None)
                            or getattr(attachment, "shortFilename", None)
                            or getattr(attachment, "displayName", None)
                            or getattr(attachment, "name", None)
                            or ""
                        )
                        att_data = getattr(attachment, "data", None)
                        if att_name and att_data:
                            att_doc = _parse_attachment(att_name, att_data)
                            if att_doc:
                                attachment_docs.append(att_doc)
                    any_scanned, merged_path = _merge_attachment_into(text_parts, attachment_docs)
                    if text_parts:
                        text = "\n\n".join(text_parts).strip()
                    if any_scanned and merged_path:
                        # Return early with the scanned merged PDF so the SOV pipeline can OCR it
                        message.close()
                        return parse_pdf(merged_path, filename)
                finally:
                    message.close()
            except Exception:
                logger.warning("Outlook MSG parsing fallback to raw text for %s", filename)
        elif ext in _EMAIL_EXTENSIONS:
            email_bytes = raw_bytes
            if ext == ".emlx":
                first_line, _, remainder = raw_bytes.partition(b"\n")
                if first_line.strip().isdigit() and remainder:
                    email_bytes = remainder

            try:
                message = BytesParser(policy=policy.default).parsebytes(email_bytes)
                text_parts: list[str] = []
                header_lines = []
                for label, value in (
                    ("Subject", message.get("subject")),
                    ("From", message.get("from")),
                    ("To", message.get("to")),
                    ("Cc", message.get("cc")),
                    ("Date", message.get("date")),
                ):
                    if value:
                        header_lines.append(f"{label}: {value}")
                if header_lines:
                    text_parts.append("\n".join(header_lines))

                plain_parts: list[str] = []
                html_parts: list[str] = []
                attachment_docs: list = []
                for part in (message.walk() if message.is_multipart() else [message]):
                    disposition = part.get_content_disposition()
                    content_type = part.get_content_type()
                    if disposition == "attachment":
                        att_name = part.get_filename() or ""
                        att_data = part.get_payload(decode=True)
                        if att_name and att_data:
                            att_doc = _parse_attachment(att_name, att_data)
                            if att_doc:
                                attachment_docs.append(att_doc)
                        continue
                    if not content_type.startswith("text/"):
                        continue
                    try:
                        part_text = part.get_content()
                    except Exception:
                        payload = part.get_payload(decode=True) or b""
                        charset = part.get_content_charset() or "utf-8"
                        part_text = payload.decode(charset, errors="replace")
                    if not isinstance(part_text, str) or not part_text.strip():
                        continue
                    if content_type == "text/plain":
                        plain_parts.append(part_text)
                    elif content_type == "text/html":
                        html_parts.append(part_text)

                body_text = "\n\n".join(chunk.strip() for chunk in plain_parts if chunk.strip()).strip()
                if not body_text and html_parts:
                    html_text = "\n\n".join(html_parts)
                    html_text = re.sub(r"(?is)<(script|style).*?</\1>", " ", html_text)
                    html_text = re.sub(r"(?i)<br\s*/?>", "\n", html_text)
                    html_text = re.sub(r"(?i)</(p|div|li|tr|h[1-6])>", "\n", html_text)
                    body_text = unescape(re.sub(r"<[^>]+>", " ", html_text))
                    body_text = re.sub(r"[ \t]+", " ", body_text)
                    body_text = re.sub(r"\n{3,}", "\n\n", body_text).strip()

                if body_text:
                    text_parts.append(body_text)

                any_scanned, merged_path = _merge_attachment_into(text_parts, attachment_docs)
                if any_scanned and merged_path:
                    return parse_pdf(merged_path, filename)
                if text_parts:
                    text = "\n\n".join(text_parts).strip()
            except Exception:
                logger.warning("Email parsing fallback to raw text for %s", filename)
        elif ext in {".html", ".htm"}:
            html_text = raw_bytes.decode("utf-8", errors="replace")
            html_text = re.sub(r"(?is)<(script|style).*?</\1>", " ", html_text)
            html_text = re.sub(r"(?i)<br\s*/?>", "\n", html_text)
            html_text = re.sub(r"(?i)</(p|div|li|tr|h[1-6])>", "\n", html_text)
            text = unescape(re.sub(r"<[^>]+>", " ", html_text))
            text = re.sub(r"[ \t]+", " ", text)
            text = re.sub(r"\n{3,}", "\n\n", text).strip()

        page = ParsedPage(
            page_num=1,
            text=text.strip(),
            tables=[],
            word_count=len(text.split()),
            has_numbers=bool(_NUM_RE.search(text)),
            has_dates=bool(_DATE_RE.search(text)),
            image_count=0,
        )
        logger.info(
            "parse_pdf done: filename=%s pages=1 tables=0 doc_type_hint=narrative is_scanned=False selected_pages=%s table_scan_pages=%s",
            filename,
            [1],
            [],
        )
        return ParsedDocument(
            filename=filename,
            file_path=file_path,
            page_count=1,
            pages=[page],
            tables=[],
            content_text=f"=== Page 1 ===\n{text.strip()}",
            tables_markdown="",
            doc_type_hint="narrative",
            has_tables=False,
            is_scanned=False,
        )

    doc = fitz.open(file_path)
    page_count_raw = len(doc)

    # ── Pass 1: fast text + image count for every page ────────────────────────
    raw: list[dict] = []
    for i in range(page_count_raw):
        p = doc[i]
        text = p.get_text("text").strip()
        lines = [line.strip() for line in text.splitlines() if line.strip()]
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
            "title_text":  " ".join(lines[:4]),
            "header_text": " ".join(lines[:8]),
            "early_text":  " ".join(lines[:20]),
        })

    long_doc_focus_indices: set[int] = set()
    if page_count_raw > _LONG_DOC_HEADER_THRESHOLD:
        exact_statement_indices: list[int] = []
        header_scored: list[tuple[float, int]] = []
        for i, row in enumerate(raw):
            title_lower = row["title_text"].lower().replace("’", "'")
            header_lower = row["header_text"].lower().replace("’", "'")
            early_lower = row["early_text"].lower().replace("’", "'")
            if not early_lower:
                continue

            exact_statement_hits = sum(
                1
                for phrase in (
                    "consolidated balance sheet",
                    "consolidated balance sheets",
                    "consolidated statements of operations",
                    "consolidated statement of operations",
                    "consolidated statements of income",
                    "consolidated statement of income",
                    "consolidated statements of earnings",
                    "consolidated statement of earnings",
                    "consolidated statements of comprehensive income",
                    "consolidated statement of comprehensive income",
                    "consolidated statements of cash flows",
                    "consolidated statement of cash flows",
                    "consolidated statements of stockholders' equity",
                    "consolidated statement of stockholders' equity",
                    "consolidated statements of shareholders' equity",
                    "consolidated statement of shareholders' equity",
                    "consolidated statements of equity",
                    "consolidated statement of equity",
                )
                if phrase in title_lower
            )
            if exact_statement_hits:
                exact_statement_indices.append(i)

            score = 0.0
            score += 3_000 * exact_statement_hits
            score += 900 * sum(
                1
                for phrase in (
                    "statement of financial position",
                    "income statement",
                    "cash flow statement",
                )
                if phrase in title_lower
            )
            score += 900 * sum(
                1
                for phrase in (
                    "financial statements and supplementary data",
                    "index to consolidated financial statements",
                )
                if phrase in title_lower
            )
            score += 500 * sum(
                1
                for phrase in (
                    "notes to consolidated financial statements",
                    "management's discussion and analysis",
                )
                if phrase in title_lower
            )
            score += 220 * sum(1 for kw in _TABLE_SCORE_KEYWORDS if kw in title_lower)
            score += 120 * sum(1 for kw in _TABLE_SCORE_KEYWORDS if kw in header_lower)
            score += 80 * sum(1 for kw in _TABLE_SCORE_KEYWORDS if kw in early_lower)
            if "table of contents" in title_lower:
                score -= 900
            if "report of independent registered public accounting firm" in title_lower:
                score -= 1_200
            if "exhibits and financial statement schedules" in title_lower:
                score -= 1_200
            if "item 8" in title_lower and "financial statements" in title_lower:
                score += 750
            if row["has_numbers"]:
                score += 140
            if row["has_dates"]:
                score += 60
            score += min(row["word_count"], 1_000) * 0.08

            if score > 0:
                header_scored.append((score, i))

        header_scored.sort(
            key=lambda item: (item[0], raw[item[1]]["word_count"], -item[1]),
            reverse=True,
        )

        anchor_indices: list[int] = []
        for idx in sorted(exact_statement_indices):
            if idx in anchor_indices:
                continue
            anchor_indices.append(idx)
            if len(anchor_indices) >= _LONG_DOC_HEADER_TARGETS:
                break

        for _, idx in header_scored:
            if any(abs(idx - existing) <= 2 for existing in anchor_indices):
                continue
            anchor_indices.append(idx)
            if len(anchor_indices) >= _LONG_DOC_HEADER_TARGETS:
                break

        if len(anchor_indices) < _LONG_DOC_HEADER_TARGETS:
            fallback_scored = sorted(
                range(page_count_raw),
                key=lambda i: (
                    sum(1 for kw in _TABLE_SCORE_KEYWORDS if kw in raw[i]["text"].lower()),
                    raw[i]["has_numbers"],
                    raw[i]["has_dates"],
                    raw[i]["word_count"],
                ),
                reverse=True,
            )
            for idx in fallback_scored:
                if any(abs(idx - existing) <= 2 for existing in anchor_indices):
                    continue
                anchor_indices.append(idx)
                if len(anchor_indices) >= _LONG_DOC_HEADER_TARGETS:
                    break

        for idx in anchor_indices:
            for neighbor in range(max(0, idx - 1), min(page_count_raw, idx + 3)):
                long_doc_focus_indices.add(neighbor)

    # ── Determine which page indices get find_tables() ────────────────────────
    if page_count_raw <= _TABLE_SCAN_ALL_THRESHOLD:
        table_detect_indices: set[int] = set(range(page_count_raw))
    else:
        # Always include first 3 pages; for long docs add the header-focused
        # windows, then supplement with highest-scoring pages.
        kw_scored = sorted(
            range(page_count_raw),
            key=lambda i: sum(1 for kw in _TABLE_SCORE_KEYWORDS
                              if kw in raw[i]["text"].lower()),
            reverse=True,
        )
        table_detect_indices = set(range(min(3, page_count_raw)))
        table_detect_indices.update(long_doc_focus_indices)
        target_table_detect_pages = min(
            page_count_raw,
            max(_MAX_TABLE_DETECT_PAGES, len(long_doc_focus_indices) + 10),
        )
        for idx in kw_scored:
            if len(table_detect_indices) >= target_table_detect_pages:
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
        combined = {p.page_num: p for p in pages[:3]}
        for idx in sorted(long_doc_focus_indices):
            combined[idx + 1] = pages[idx]

        remainder = pages[3:]
        for p in sorted(remainder, key=_score_page, reverse=True):
            if len(combined) >= _MAX_SELECTED_PAGES:
                break
            combined[p.page_num] = p

        if len(combined) < _MAX_SELECTED_PAGES:
            n_uniform = 12
            step = max(1, len(remainder) // n_uniform)
            for p in remainder[::step][:n_uniform]:
                if len(combined) >= _MAX_SELECTED_PAGES:
                    break
                combined[p.page_num] = p

        selected = sorted(combined.values(), key=lambda p: p.page_num)

    # Build content_text from the selected pages without clipping characters.
    content_text = "\n\n".join(f"=== Page {p.page_num} ===\n{p.text}" for p in selected)

    # Build tables_markdown from every detected table without clipping characters.
    tables_markdown = "\n\n".join(
        f"[Table — page {t.page_num}, {t.row_count} rows × {t.col_count} cols]\n{t.markdown}"
        for t in all_tables
    )

    doc_type_hint = _classify_doc_hint(pages, all_tables)
    is_scanned    = force_scanned or _detect_scan(pages, file_path)

    logger.info(
        "parse_pdf done: filename=%s pages=%d tables=%d doc_type_hint=%s is_scanned=%s selected_pages=%s table_scan_pages=%s",
        filename,
        page_count,
        len(all_tables),
        doc_type_hint,
        is_scanned,
        [p.page_num for p in selected],
        [i + 1 for i in sorted(table_detect_indices)],
    )

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
