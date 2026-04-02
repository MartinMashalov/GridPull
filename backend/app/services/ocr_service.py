"""
Mistral OCR service — converts scanned/image-based PDFs to markdown text.

Hard limits for mistral-ocr-latest (La Plateforme):
  • 1,000 pages per document
  • 50 MB per document

When a PDF exceeds either limit this service automatically splits it into
chunks using PyMuPDF, OCRs each chunk concurrently, and stitches the results
back together with correctly-offset page numbers.

Returns OCRResult:
  text       — full document text with page markers plus extracted headers/footers/tables
  page_count — number of pages actually processed (used for billing)
  cost_usd   — OCR cost reported by LiteLLM
  pages      — structured per-page OCR output
"""

import asyncio
import logging
import os
import tempfile
from dataclasses import dataclass

import fitz  # PyMuPDF — already a project dependency
from mistralai import DocumentURLChunk, File, Mistral

logger = logging.getLogger(__name__)

# ── Mistral OCR safety thresholds (with buffer below hard limits) ─────────────
_MAX_PAGES_PER_CALL = 950     # hard limit: 1,000   — we stay at 950
_MAX_FILE_MB        = 45.0    # hard limit: 50 MB   — we stay at 45 MB
_MISTRAL_OCR_PAGE_PRICE_USD = 0.001


@dataclass
class OCRPage:
    page_num: int
    markdown: str
    header: str | None
    footer: str | None
    tables_markdown: str


@dataclass
class OCRResult:
    text: str
    page_count: int
    cost_usd: float
    pages: list[OCRPage]


# ── Helpers ───────────────────────────────────────────────────────────────────

def _compute_chunk_size(file_path: str, page_count: int) -> int:
    """
    Compute how many pages to send per OCR call so that neither the page-count
    nor the file-size limit is exceeded.

    Uses the average page size of the original file to estimate chunk size.
    Always returns at least 1.
    """
    file_size_mb = os.path.getsize(file_path) / (1024 * 1024)
    avg_page_mb  = file_size_mb / max(page_count, 1)

    if avg_page_mb > 0:
        pages_for_size = int(_MAX_FILE_MB / avg_page_mb)
    else:
        pages_for_size = _MAX_PAGES_PER_CALL

    return max(1, min(_MAX_PAGES_PER_CALL, pages_for_size))


def _extract_chunk_to_tempfile(file_path: str, start_page: int, end_page: int) -> str:
    """
    Write pages [start_page, end_page) (0-indexed) from `file_path` into a
    temporary PDF file and return its path. Caller is responsible for cleanup.
    """
    with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
        tmp_path = tmp.name

    src = fitz.open(file_path)
    out = fitz.open()
    out.insert_pdf(src, from_page=start_page, to_page=end_page - 1)
    out.save(tmp_path)
    src.close()
    out.close()
    return tmp_path


def _table_to_markdown(table: object) -> str:
    if isinstance(table, str):
        return table
    if isinstance(table, dict):
        return str(table.get("markdown") or table.get("content") or "").strip()
    return str(getattr(table, "markdown", "") or getattr(table, "content", "") or "").strip()


def _offset_pages(pages: list[OCRPage], page_offset: int) -> list[OCRPage]:
    return [
        OCRPage(
            page_num=page_offset + idx + 1,
            markdown=page.markdown,
            header=page.header,
            footer=page.footer,
            tables_markdown=page.tables_markdown,
        )
        for idx, page in enumerate(pages)
    ]


def _assemble(pages: list[OCRPage]) -> str:
    parts: list[str] = []
    for page in pages:
        page_parts = [f"=== Page {page.page_num} ==="]
        if page.header:
            page_parts.append(f"--- Header ---\n{page.header}")
        if page.markdown:
            page_parts.append(page.markdown)
        if page.tables_markdown:
            page_parts.append(f"--- Tables ---\n{page.tables_markdown}")
        if page.footer:
            page_parts.append(f"--- Footer ---\n{page.footer}")
        parts.append("\n".join(page_parts))
    return "\n\n".join(parts)


async def _ocr_file(file_path: str, api_key: str) -> tuple[list[OCRPage], float]:
    """
    Mistral SDK OCR call on a single PDF or image path.
    Returns per-page OCR structure plus the estimated OCR cost for this call.
    """
    client = Mistral(api_key=api_key)
    ext = os.path.splitext(file_path.lower())[1]
    content_type = {
        ".pdf": "application/pdf",
        ".png": "image/png",
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".gif": "image/gif",
        ".webp": "image/webp",
        ".bmp": "image/bmp",
        ".tif": "image/tiff",
        ".tiff": "image/tiff",
    }.get(ext, "application/octet-stream")

    with open(file_path, "rb") as f:
        uploaded = await client.files.upload_async(
            file=File(
                file_name=os.path.basename(file_path),
                content=f.read(),
                content_type=content_type,
            ),
            purpose="ocr",
        )

    try:
        signed = await client.files.get_signed_url_async(file_id=uploaded.id)
        response = await client.ocr.process_async(
            model="mistral-ocr-latest",
            document=DocumentURLChunk(
                document_url=signed.url,
                document_name=os.path.basename(file_path),
            ),
        )
    finally:
        try:
            await client.files.delete_async(file_id=uploaded.id)
        except Exception as exc:
            logger.warning("Mistral OCR cleanup failed for %s: %s", file_path, exc)

    pages: list[OCRPage] = []
    for idx, page in enumerate(response.pages):
        markdown = str(getattr(page, "markdown", getattr(page, "text", "")) or "")
        header = getattr(page, "header", None)
        footer = getattr(page, "footer", None)
        raw_tables = getattr(page, "tables", None) or []
        tables_markdown = "\n\n".join(
            table_md for table_md in (_table_to_markdown(table) for table in raw_tables) if table_md
        )
        pages.append(
            OCRPage(
                page_num=idx + 1,
                markdown=markdown,
                header=str(header).strip() if header else None,
                footer=str(footer).strip() if footer else None,
                tables_markdown=tables_markdown,
            )
        )
    ocr_cost_usd = len(pages) * _MISTRAL_OCR_PAGE_PRICE_USD
    return pages, ocr_cost_usd


# ── Public async API ──────────────────────────────────────────────────────────

async def run_mistral_ocr(file_path: str, api_key: str) -> OCRResult:
    """
    Run Mistral OCR on a PDF, automatically splitting if the file exceeds the
    1,000-page or 50 MB limits.

    Returns OCRResult:
      text      — full text with page markers, plus extracted headers/footers/tables
      page_count — total number of pages processed (for billing)
      cost_usd   — OCR cost
      pages      — structured per-page OCR output
    """
    src        = fitz.open(file_path)
    page_count = len(src)
    src.close()

    chunk_size = _compute_chunk_size(file_path, page_count)

    if page_count <= chunk_size:
        # Happy path — single call, no splitting needed
        logger.debug("Mistral OCR: single call, %d pages", page_count)
        pages, ocr_cost_usd = await _ocr_file(file_path, api_key)
        return OCRResult(
            text=_assemble(pages),
            page_count=len(pages),
            cost_usd=ocr_cost_usd,
            pages=pages,
        )

    # Need to split — build chunk ranges
    chunks = [
        (start, min(start + chunk_size, page_count))
        for start in range(0, page_count, chunk_size)
    ]
    logger.info(
        "Mistral OCR: splitting %d-page PDF into %d chunk(s) of ≤%d pages",
        page_count, len(chunks), chunk_size,
    )

    async def _ocr_chunk(start: int, end: int) -> tuple[list[OCRPage], int, float]:
        tmp_path = await asyncio.to_thread(
            _extract_chunk_to_tempfile, file_path, start, end
        )
        try:
            pages, ocr_cost_usd = await _ocr_file(tmp_path, api_key)
            return pages, start, ocr_cost_usd
        finally:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass

    results = await asyncio.gather(*[_ocr_chunk(s, e) for s, e in chunks])

    # Reassemble in order with correct absolute page numbers
    all_pages: list[OCRPage] = []
    total_pages = 0
    total_cost_usd = 0.0
    for pages, offset, ocr_cost_usd in results:
        adjusted_pages = _offset_pages(pages, offset)
        all_pages.extend(adjusted_pages)
        total_pages += len(adjusted_pages)
        total_cost_usd += ocr_cost_usd

    return OCRResult(
        text=_assemble(all_pages),
        page_count=total_pages,
        cost_usd=total_cost_usd,
        pages=all_pages,
    )
