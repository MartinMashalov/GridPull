"""Strategy: Multi-record extraction.

One or more large files that each contain multiple records to extract.
Handles tables with repeated rows, comparative financial statements, etc.
"""
from __future__ import annotations

import asyncio
import logging
from typing import Any, Dict, List

from app.config import settings
from app.services.pdf_service import ParsedDocument

from .core import (
    _MULTI_SYSTEM,
    _SCAN_MULTI_SYSTEM,
    _TEXT_MODEL,
    _doc_context_block,
    _empty,
    _fields_block,
    _maybe_compress_with_bear,
    build_table_column_hint,
    document_has_wide_data_grid,
    LLMUsage,
)
from .llm import (
    _extract_record_count_metadata,
    _llm_extract,
    _llm_extract_vision,
    _review_multi_rows,
)

logger = logging.getLogger(__name__)

_MULTI_MAX_TOKENS = 32_768


async def execute(
    doc: ParsedDocument,
    fields: List[Dict[str, str]],
    usage: LLMUsage,
    instructions: str = "",
    ocr_text: str | None = None,
    ocr_pages: list | None = None,
) -> List[Dict[str, Any]]:
    """Extract multiple records from a single document.

    Automatically chooses chunked vs. full-doc based on page count.
    """
    field_names = [f["name"] for f in fields]
    is_scan = ocr_text is not None
    system = _SCAN_MULTI_SYSTEM if is_scan else _MULTI_SYSTEM
    extract_fn = _llm_extract_vision if is_scan else _llm_extract

    use_chunked = doc.page_count > settings.extraction_chunk_threshold_pages

    if use_chunked:
        logger.info(
            "Multi-record chunked extraction: %s (%d pages)",
            doc.filename, doc.page_count,
        )
        rows = await _extract_chunked(
            doc, fields, field_names, usage, instructions,
            is_scan, ocr_text, ocr_pages, system, extract_fn,
        )
    else:
        logger.info(
            "Multi-record full-doc extraction: %s (%d pages)",
            doc.filename, doc.page_count,
        )
        rows = await _extract_full_doc(
            doc, fields, field_names, usage, instructions,
            is_scan, ocr_text, system, extract_fn,
        )

    if not rows:
        return _empty([doc.filename], field_names)
    return rows


async def _extract_full_doc(
    doc: ParsedDocument,
    fields: List[Dict[str, str]],
    field_names: List[str],
    usage: LLMUsage,
    instructions: str,
    is_scan: bool,
    ocr_text: str | None,
    system: str,
    extract_fn,
) -> List[Dict[str, Any]]:
    """Full-document multi-record extraction with count validation."""
    fblock = _fields_block(fields)
    ctx = _doc_context_block(doc)

    if is_scan:
        content_text = await _maybe_compress_with_bear(
            ocr_text, doc.page_count, usage, f"{doc.filename} multi OCR text",
        )
        full_tables_md = ""
    else:
        raw_text = doc.content_text or "\n\n".join(
            f"=== Page {p.page_num} ===\n{p.text}" for p in doc.pages
        )
        content_text = await _maybe_compress_with_bear(
            raw_text, doc.page_count, usage, f"{doc.filename} multi text",
        )
        table_parts = [
            f"[Table - page {t.page_num}, {t.row_count}x{t.col_count}]\n{t.markdown}"
            for t in doc.tables
        ]
        full_tables_md = await _maybe_compress_with_bear(
            "\n\n".join(table_parts) if table_parts else (doc.tables_markdown or ""),
            doc.page_count, usage, f"{doc.filename} multi tables",
        )

    col_hint = build_table_column_hint(doc.tables) if not is_scan else ""

    cacheable_prefix = _build_cacheable_prefix(
        fblock, ctx, instructions, full_tables_md, content_text, col_hint,
    )

    metadata_context = f"{content_text}\n\n{full_tables_md}" if full_tables_md else content_text

    user_prompt = (
        cacheable_prefix
        + '\n\nExtract ALL records. Return: {"records": [{"Field": "value"}, ...]}'
    )

    # Run count metadata and extraction in parallel
    count_task = _extract_record_count_metadata(
        metadata_context, fblock, doc.filename, usage, instructions,
    )
    extract_task = extract_fn(
        system, user_prompt, field_names, doc.filename, usage,
        _TEXT_MODEL, max_tokens=_MULTI_MAX_TOKENS,
    )
    expected_count, rows = await asyncio.gather(count_task, extract_task)

    rows = await _review_multi_rows(
        rows, field_names, doc.filename, usage, cacheable_prefix, instructions, _TEXT_MODEL,
    )

    # Count validation retry
    if expected_count is not None and len(rows) != expected_count:
        logger.info(
            "Row count mismatch for %s: extracted=%d expected=%d; retrying",
            doc.filename, len(rows), expected_count,
        )
        retry_prompt = (
            cacheable_prefix
            + f"\n\nIMPORTANT: This document contains exactly {expected_count} data records. "
            f"You previously returned {len(rows)} — extract ALL {expected_count} records. "
            f"Do not skip any. Do not include subtotals or headers as records.\n"
            'Return: {"records": [{"Field": "value"}, ...]}'
        )
        retry_rows = await extract_fn(
            system, retry_prompt, field_names, doc.filename, usage,
            _TEXT_MODEL, max_tokens=_MULTI_MAX_TOKENS,
        )
        retry_rows = await _review_multi_rows(
            retry_rows, field_names, doc.filename, usage, cacheable_prefix, instructions, _TEXT_MODEL,
        )
        if abs(len(retry_rows) - expected_count) < abs(len(rows) - expected_count):
            logger.info("Retry improved count: %d -> %d (expected %d)", len(rows), len(retry_rows), expected_count)
            rows = retry_rows

    return rows


async def _extract_chunked(
    doc: ParsedDocument,
    fields: List[Dict[str, str]],
    field_names: List[str],
    usage: LLMUsage,
    instructions: str,
    is_scan: bool,
    ocr_text: str | None,
    ocr_pages: list | None,
    system: str,
    extract_fn,
) -> List[Dict[str, Any]]:
    """Chunked multi-record extraction for long documents."""
    fblock = _fields_block(fields)
    col_hint = build_table_column_hint(doc.tables) if not is_scan else ""
    inject_global_tables = document_has_wide_data_grid(doc) and not is_scan
    cs = settings.extraction_chunk_size

    if is_scan and ocr_pages:
        # Chunk OCR pages
        page_chunks = [ocr_pages[i:i + cs] for i in range(0, len(ocr_pages), cs)]

        async def _extract_scan_chunk(chunk_pages: list) -> List[Dict[str, Any]]:
            from .scan_pipeline import _ocr_page_text
            chunk_text = "\n\n".join(_ocr_page_text(p) for p in chunk_pages)
            chunk_text = await _maybe_compress_with_bear(
                chunk_text, doc.page_count, usage,
                f"{doc.filename} scan chunk text",
            )
            parts = [
                f"--- Document Info ---\n"
                f"Filename: {doc.filename}\nTotal pages: {doc.page_count}\n",
                f"\n--- Fields (one object per repeated record) ---\n{fblock}",
            ]
            if instructions.strip():
                parts.append(f"\n--- User Instructions ---\n{instructions.strip()}")
            parts.append(f"\n--- OCR Text ---\n{chunk_text}")
            prompt = (
                "\n".join(parts)
                + "\n\nExtract ALL repeated records on these pages only. "
                + 'Return: {"records": [...]}. No records here -> {"records": []}.'
            )
            return await extract_fn(system, prompt, field_names, doc.filename, usage, _TEXT_MODEL)

        chunk_results = await asyncio.gather(*[_extract_scan_chunk(c) for c in page_chunks])
    else:
        # Chunk text pages
        page_chunks = [doc.pages[i:i + cs] for i in range(0, len(doc.pages), cs)]

        async def _extract_text_chunk(chunk_pages: list) -> List[Dict[str, Any]]:
            page_nums = {p.page_num for p in chunk_pages}
            first_pg, last_pg = chunk_pages[0].page_num, chunk_pages[-1].page_num
            chunk_text = "\n\n".join(f"=== Page {p.page_num} ===\n{p.text}" for p in chunk_pages)

            if inject_global_tables and doc.tables:
                table_parts = [
                    f"[Table - page {t.page_num}, {t.row_count}x{t.col_count}]\n{t.markdown}"
                    for t in doc.tables
                ]
                tables_md = "\n\n".join(table_parts)
                tables_scope = "all detected tables"
            else:
                tables_md = "\n\n".join(
                    f"[Table - page {t.page_num}, {t.row_count}x{t.col_count}]\n{t.markdown}"
                    for t in doc.tables if t.page_num in page_nums
                )
                tables_scope = f"pages {first_pg}-{last_pg}"

            chunk_text = await _maybe_compress_with_bear(
                chunk_text, doc.page_count, usage, f"{doc.filename} chunk {first_pg}-{last_pg} text",
            )
            tables_md = await _maybe_compress_with_bear(
                tables_md, doc.page_count, usage, f"{doc.filename} chunk {first_pg}-{last_pg} tables",
            )

            parts = [
                f"--- Document Info ---\n"
                f"Filename: {doc.filename}\nTotal pages: {doc.page_count}\n"
                f"Extracting: pages {first_pg}-{last_pg}",
                f"\n--- Fields (one object per repeated record) ---\n{fblock}",
            ]
            if instructions.strip():
                parts.append(f"\n--- User Instructions ---\n{instructions.strip()}")
            if col_hint:
                parts.append(f"\n{col_hint}")
            if inject_global_tables:
                parts.append(
                    "\n--- Table priority ---\n"
                    "If Tables include a primary data table with repeated rows matching the requested fields, "
                    "emit one output record per data row from that table and copy every value from it. "
                    "Use the Text only to fill fields the table omits.\n"
                )
            if tables_md:
                parts.append(f"\n--- Tables ({tables_scope}) ---\n{tables_md}")
            parts.append(f"\n--- Text (pages {first_pg}-{last_pg}) ---\n{chunk_text}")

            prompt = (
                "\n".join(parts)
                + "\n\nExtract ALL repeated records on these pages only. "
                + 'Return: {"records": [...]}. No records here -> {"records": []}.'
            )
            return await _llm_extract(system, prompt, field_names, doc.filename, usage, _TEXT_MODEL)

        chunk_results = await asyncio.gather(*[_extract_text_chunk(c) for c in page_chunks])

    all_rows: List[Dict[str, Any]] = []
    for rows in chunk_results:
        all_rows.extend(r for r in rows if any(r.get(fn) for fn in field_names))

    if not all_rows:
        return _empty([doc.filename], field_names)

    all_rows = await _review_multi_rows(
        all_rows, field_names, doc.filename, usage,
        doc.content_text or ocr_text or "", instructions, _TEXT_MODEL,
    )

    # Count validation
    metadata_context = doc.content_text or ocr_text or ""
    if doc.tables_markdown:
        metadata_context += "\n\n" + doc.tables_markdown
    expected_count = await _extract_record_count_metadata(
        metadata_context, fblock, doc.filename, usage, instructions,
    )

    if expected_count is not None and len(all_rows) != expected_count:
        logger.info(
            "Chunked count mismatch for %s: %d vs expected %d",
            doc.filename, len(all_rows), expected_count,
        )
        # Retry with full-doc approach if count is off
        if not is_scan:
            ctx = _doc_context_block(doc)
            raw_text = doc.content_text or "\n\n".join(
                f"=== Page {p.page_num} ===\n{p.text}" for p in doc.pages
            )
            content_text = await _maybe_compress_with_bear(
                raw_text, doc.page_count, usage, f"{doc.filename} multi retry text",
            )
            table_parts = [
                f"[Table - page {t.page_num}, {t.row_count}x{t.col_count}]\n{t.markdown}"
                for t in doc.tables
            ]
            full_tables_md = await _maybe_compress_with_bear(
                "\n\n".join(table_parts) if table_parts else "",
                doc.page_count, usage, f"{doc.filename} multi retry tables",
            )
            cacheable_prefix = _build_cacheable_prefix(
                fblock, ctx, instructions, full_tables_md, content_text,
                col_hint,
            )
            retry_prompt = (
                cacheable_prefix
                + f"\n\nIMPORTANT: This document contains exactly {expected_count} data records. "
                f"Extract ALL {expected_count} records. Do not skip any.\n"
                'Return: {"records": [{"Field": "value"}, ...]}'
            )
            retry_rows = await _llm_extract(
                system, retry_prompt, field_names, doc.filename, usage,
                _TEXT_MODEL, max_tokens=_MULTI_MAX_TOKENS,
            )
            retry_rows = await _review_multi_rows(
                retry_rows, field_names, doc.filename, usage,
                cacheable_prefix, instructions, _TEXT_MODEL,
            )
            if abs(len(retry_rows) - expected_count) < abs(len(all_rows) - expected_count):
                all_rows = retry_rows

    return all_rows


def _build_cacheable_prefix(
    fblock: str,
    ctx: str,
    instructions: str,
    full_tables_md: str,
    content_text: str,
    col_hint: str = "",
) -> str:
    """Build prompt prefix with static content first for cache hits."""
    parts = [
        f"--- Fields to Extract (one object per repeated record) ---\n{fblock}",
    ]
    if instructions.strip():
        parts.append(f"\n--- User Instructions ---\n{instructions.strip()}")
    if col_hint:
        parts.append(f"\n{col_hint}")
    parts.append(
        "\n--- Extraction Mode ---\n"
        "The output should contain one object per natural repeated record that matches the "
        "requested fields. If the schema repeats across table rows, emit one object per row. "
        "If the schema repeats across table columns, emit one object per column. If the "
        "document does not actually contain repeated records that match the requested fields, "
        "return a single best record instead of inventing multiples.\n"
        "For comparative financial statements that show the same metrics across multiple fiscal "
        "years/periods as separate columns, emit one object per fiscal year/period.\n"
        "Do NOT output completely empty objects between real rows. "
        "When multiple lines refer to the same logical entity, merge them into one object."
    )
    parts.append(f"\n--- Document Info ---\n{ctx}")
    if full_tables_md:
        parts.append(f"\n--- Detected Tables ---\n{full_tables_md}")
    parts.append(f"\n--- Document Text ---\n{content_text}")
    return "\n".join(parts)
