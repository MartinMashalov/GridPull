"""
Mistral OCR service — converts scanned/image-based PDFs to markdown text.

Hard limits for mistral-ocr-latest (La Plateforme):
  • 1,000 pages per document
  • 50 MB per document

When a PDF exceeds either limit this service automatically splits it into
chunks using PyMuPDF, OCRs each chunk concurrently, and stitches the results
back together with correctly-offset page numbers.

Returns: (ocr_text: str, page_count: int)
  ocr_text    — full document text with "=== Page N ===" markers and markdown tables
  page_count  — number of pages actually processed (used for billing)
"""

import asyncio
import base64
import logging
import os
import re
import tempfile

import fitz  # PyMuPDF — already a project dependency

logger = logging.getLogger(__name__)

# ── Mistral OCR safety thresholds (with buffer below hard limits) ─────────────
_MAX_PAGES_PER_CALL = 950     # hard limit: 1,000   — we stay at 950
_MAX_FILE_MB        = 45.0    # hard limit: 50 MB   — we stay at 45 MB


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


_IMAGE_MIME = {
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".gif": "image/gif",
    ".tiff": "image/tiff",
    ".bmp": "image/bmp",
    ".webp": "image/webp",
}


def _sync_ocr_file(file_path: str, api_key: str) -> list[str]:
    """
    Synchronous Mistral OCR call on a single (possibly chunked) PDF or image.
    Returns a list of per-page markdown strings (index = 0-based page in file).
    """
    from mistralai import Mistral

    ext = os.path.splitext(file_path.lower())[1]
    mime = _IMAGE_MIME.get(ext)

    with open(file_path, "rb") as fh:
        b64 = base64.b64encode(fh.read()).decode("utf-8")

    client = Mistral(api_key=api_key)

    if mime:
        # Image file — use image_url type
        response = client.ocr.process(
            model="mistral-ocr-latest",
            document={
                "type": "image_url",
                "image_url": f"data:{mime};base64,{b64}",
            },
        )
    else:
        # PDF file — use document_url type
        response = client.ocr.process(
            model="mistral-ocr-latest",
            document={
                "type": "document_url",
                "document_url": f"data:application/pdf;base64,{b64}",
            },
        )

    pages = []
    for page in response.pages:
        md = getattr(page, "markdown", getattr(page, "text", ""))
        pages.append(md)
    return pages


# ── Public async API ──────────────────────────────────────────────────────────

async def run_mistral_ocr(file_path: str, api_key: str) -> tuple[str, int]:
    """
    Run Mistral OCR on a PDF, automatically splitting if the file exceeds the
    1,000-page or 50 MB limits.

    Returns (ocr_text, page_count):
      ocr_text   — full text with "=== Page N ===" markers (1-indexed, absolute)
      page_count — total number of pages processed (for billing)
    """
    src        = fitz.open(file_path)
    page_count = len(src)
    src.close()

    chunk_size = _compute_chunk_size(file_path, page_count)

    if page_count <= chunk_size:
        # Happy path — single call, no splitting needed
        logger.debug("Mistral OCR: single call, %d pages", page_count)
        pages_md = await asyncio.to_thread(_sync_ocr_file, file_path, api_key)
        ocr_text = _assemble(pages_md, page_offset=0)
        return ocr_text, len(pages_md)

    # Need to split — build chunk ranges
    chunks = [
        (start, min(start + chunk_size, page_count))
        for start in range(0, page_count, chunk_size)
    ]
    logger.info(
        "Mistral OCR: splitting %d-page PDF into %d chunk(s) of ≤%d pages",
        page_count, len(chunks), chunk_size,
    )

    async def _ocr_chunk(start: int, end: int) -> tuple[list[str], int]:
        tmp_path = await asyncio.to_thread(
            _extract_chunk_to_tempfile, file_path, start, end
        )
        try:
            pages_md = await asyncio.to_thread(_sync_ocr_file, tmp_path, api_key)
            return pages_md, start   # return pages + page offset for reassembly
        finally:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass

    results = await asyncio.gather(*[_ocr_chunk(s, e) for s, e in chunks])

    # Reassemble in order with correct absolute page numbers
    all_parts: list[str] = []
    total_pages = 0
    for pages_md, offset in results:
        all_parts.append(_assemble(pages_md, page_offset=offset))
        total_pages += len(pages_md)

    return "\n\n".join(all_parts), total_pages


def _assemble(pages_md: list[str], page_offset: int) -> str:
    """
    Join per-page markdown strings into a single text block with page markers.
    page_offset is the 0-based index of the first page in the original document.
    """
    parts = []
    for i, md in enumerate(pages_md):
        page_num = page_offset + i + 1   # 1-indexed absolute page number
        parts.append(f"=== Page {page_num} ===\n{md}")
    return "\n\n".join(parts)
