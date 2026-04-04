"""OCR wrapper for scanned documents.

Runs Mistral OCR and returns the text + pages for use by strategy modules.
The old extraction logic has been moved into strategy_individual, strategy_multi_record,
and strategy_page_per_row.
"""
from __future__ import annotations

import logging
from typing import Any

from app.config import settings
from app.services.pdf_service import ParsedDocument

from .core import _error, LLMUsage

logger = logging.getLogger(__name__)


def _ocr_page_text(page: Any) -> str:
    """Format an OCR page into text with headers/tables."""
    parts = [f"=== Page {page.page_num} ==="]
    if getattr(page, "header", None):
        parts.append(f"--- Header ---\n{page.header}")
    if getattr(page, "markdown", None):
        parts.append(page.markdown)
    if getattr(page, "tables_markdown", None):
        parts.append(f"--- Tables ---\n{page.tables_markdown}")
    if getattr(page, "footer", None):
        parts.append(f"--- Footer ---\n{page.footer}")
    return "\n".join(parts)


async def run_ocr_for_document(
    doc: ParsedDocument,
    usage: LLMUsage,
) -> tuple[str, list] | None:
    """Run Mistral OCR on the document.

    Returns (full_text, ocr_pages) or None on failure.
    """
    from app.services.ocr_service import run_mistral_ocr

    if not settings.mistral_api_key:
        logger.error("Scanned doc detected (%s) but MISTRAL_API_KEY not set", doc.filename)
        return None

    logger.info("OCR starting: %s (%d pages)", doc.filename, doc.page_count)

    try:
        ocr_result = await run_mistral_ocr(doc.file_path, settings.mistral_api_key)
        usage.add_ocr_cost(ocr_result.cost_usd)
        logger.info(
            "OCR complete: %s - %d pages, %d chars, $%.4f",
            doc.filename, ocr_result.page_count, len(ocr_result.text), ocr_result.cost_usd,
        )
    except Exception as exc:
        logger.error("OCR failed for %s: %s", doc.filename, exc)
        return None

    if not ocr_result.text.strip():
        logger.error("OCR returned empty text for %s", doc.filename)
        return None

    return ocr_result.text, ocr_result.pages


# Keep backward compat for SOV pipeline which may import this
async def extract_from_scanned_document(
    doc: ParsedDocument,
    fields: list,
    usage: LLMUsage,
    instructions: str = "",
    forced_mode: str | None = None,
    enable_retry: bool = True,
) -> list:
    """Legacy entry point — routes through the new strategy system."""
    from . import extract_from_document
    return await extract_from_document(
        doc, fields, usage, instructions,
        batch_document_count=1,
        force_general=True,
    )
