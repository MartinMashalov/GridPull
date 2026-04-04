"""Strategy: Page-per-row extraction.

Each page in the PDF is one independent record. Used for compiled invoices,
multi-statement PDFs, etc.
"""
from __future__ import annotations

import asyncio
import logging
from typing import Any, Dict, List

from app.services.pdf_service import ParsedDocument, ParsedPage

from .core import (
    _EMPTY_VALUES,
    _MISSING_FIELDS_FOCUSED_RETRY_INSTRUCTION,
    _SCAN_SINGLE_SYSTEM,
    _SINGLE_SYSTEM,
    _TEXT_MODEL,
    _empty,
    _fields_block,
    _is_filled_value,
    LLMUsage,
)
from .llm import _cleanup_single_row_with_nano, _llm_extract, _llm_extract_vision

logger = logging.getLogger(__name__)

_PER_PAGE_CONCURRENCY = 4


async def execute(
    doc: ParsedDocument,
    fields: List[Dict[str, str]],
    usage: LLMUsage,
    instructions: str = "",
    ocr_text: str | None = None,
    ocr_pages: list | None = None,
) -> List[Dict[str, Any]]:
    """Extract one record per page, concurrently."""
    field_names = [f["name"] for f in fields]
    fblock = _fields_block(fields)
    is_scan = ocr_text is not None
    system = _SCAN_SINGLE_SYSTEM if is_scan else _SINGLE_SYSTEM
    extract_fn = _llm_extract_vision if is_scan else _llm_extract
    semaphore = asyncio.Semaphore(_PER_PAGE_CONCURRENCY)

    async def _extract_page(page_content: str, page_tables_md: str, page_num: int) -> List[Dict[str, Any]]:
        async with semaphore:
            parts = [
                f"--- Document Info ---\n"
                f"Filename: {doc.filename}\nTotal pages: {doc.page_count}\n"
                f"Extracting from: page {page_num}",
                f"\n--- Fields to Extract ---\n{fblock}",
            ]
            if instructions.strip():
                parts.append(f"\n--- User Instructions ---\n{instructions.strip()}")
            parts.append(f"\n--- Document Text ---\n{page_content}")
            if page_tables_md:
                parts.append(f"\n--- Detected Tables ---\n{page_tables_md}")
            parts.append(
                "\n--- Extraction Mode ---\n"
                "This page is one of many independent records in a compiled PDF. "
                "Extract the single record on this page. If the page has no relevant "
                'data for the requested fields, return: {"records": []}.'
            )
            prompt = "\n".join(parts) + '\n\nReturn exactly: {"records": [{"Field Name": "value", ...}]}'
            rows = await extract_fn(system, prompt, field_names, doc.filename, usage, _TEXT_MODEL)

            # Per-page missing-fields retry
            if rows and len(rows) == 1:
                row = rows[0]
                missing = [
                    fn for fn in field_names
                    if not _is_filled_value(row.get(fn))
                ]
                if missing and len(missing) < len(field_names):
                    missing_fblock = "\n".join(
                        f"  - {f['name']}" + (f"\n    description: {f['description']}" if f.get("description") else "")
                        for f in fields if f["name"] in missing
                    )
                    retry_prompt = (
                        f"The following fields were not found in the first pass. "
                        f"Search the document text more carefully for these missing fields.\n\n"
                        f"--- Missing Fields ---\n{missing_fblock}\n\n"
                        f"--- Document Text ---\n{page_content}\n"
                    )
                    if page_tables_md:
                        retry_prompt += f"\n--- Detected Tables ---\n{page_tables_md}\n"
                    retry_prompt += (
                        f"\n{_MISSING_FIELDS_FOCUSED_RETRY_INSTRUCTION}\n\n"
                        'Return exactly: {"records": [{'
                        + ", ".join(f'"{fn}": "value"' for fn in missing)
                        + "}]}"
                    )
                    retry_rows = await extract_fn(
                        system, retry_prompt, missing, doc.filename, usage, _TEXT_MODEL,
                    )
                    if retry_rows:
                        for fn in missing:
                            val = retry_rows[0].get(fn)
                            if _is_filled_value(val) and not _is_filled_value(row.get(fn)):
                                row[fn] = val
                    rows = [row]

                # Nano cleanup per row
                if rows:
                    rows = [await _cleanup_single_row_with_nano(rows[0], fields, doc.filename, usage)]

            return rows

    # Build page content for each page
    if is_scan and ocr_pages:
        from .scan_pipeline import _ocr_page_text
        page_tasks = []
        for page in ocr_pages:
            page_content = _ocr_page_text(page)
            page_tasks.append(_extract_page(page_content, "", page.page_num))
    else:
        page_tasks = []
        for page in doc.pages:
            page_text = f"=== Page {page.page_num} ===\n{page.text}"
            tables_md = "\n\n".join(
                f"[Table - page {t.page_num}, {t.row_count}x{t.col_count}]\n{t.markdown}"
                for t in page.tables
            )
            page_tasks.append(_extract_page(page_text, tables_md, page.page_num))

    page_results = await asyncio.gather(*page_tasks)

    all_rows: List[Dict[str, Any]] = []
    empty_markers = _EMPTY_VALUES
    for rows in page_results:
        for row in rows:
            filled = sum(
                1 for fn in field_names
                if row.get(fn) is not None
                and str(row[fn]).strip().lower() not in empty_markers
            )
            if filled > 0:
                all_rows.append(row)

    logger.info(
        "Page-per-row extraction for %s: %d pages -> %d records",
        doc.filename, doc.page_count, len(all_rows),
    )
    return all_rows if all_rows else _empty([doc.filename], field_names)
