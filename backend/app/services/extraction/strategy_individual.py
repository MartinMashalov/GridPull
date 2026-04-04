"""Strategy: Individual file extraction.

Each file produces exactly one row. Used for batches of individual invoices,
COIs, statements, etc. Handles both text-based and scanned (OCR) documents.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List

from app.services.pdf_service import ParsedDocument

from .core import (
    _MISSING_FIELDS_FOCUSED_RETRY_INSTRUCTION,
    _SCAN_SINGLE_SYSTEM,
    _SINGLE_RETRY_INSTRUCTION,
    _SINGLE_SYSTEM,
    _TEXT_MODEL,
    _detect_reporting_unit,
    _doc_context_block,
    _empty,
    _fields_block,
    _is_filled_value,
    _maybe_compress_with_bear,
    _single_record_valid,
    build_table_column_hint,
    LLMUsage,
)
from .llm import _cleanup_single_row_with_nano, _llm_extract, _llm_extract_vision

logger = logging.getLogger(__name__)


def _get_missing(row: Dict[str, Any], field_names: List[str]) -> List[str]:
    """Return field names that have no value."""
    return [fn for fn in field_names if not _is_filled_value(row.get(fn))]


async def execute(
    doc: ParsedDocument,
    fields: List[Dict[str, str]],
    usage: LLMUsage,
    instructions: str = "",
    ocr_text: str | None = None,
    ocr_pages: list | None = None,
) -> List[Dict[str, Any]]:
    """Extract one row from a single document/file.

    If ocr_text is provided, uses the scanned-document prompt and vision
    extraction; otherwise uses the text pipeline.
    """
    field_names = [f["name"] for f in fields]
    is_scan = ocr_text is not None
    system = _SCAN_SINGLE_SYSTEM if is_scan else _SINGLE_SYSTEM
    extract_fn = _llm_extract_vision if is_scan else _llm_extract

    # -- Build content --
    if is_scan:
        content_text = await _maybe_compress_with_bear(
            ocr_text, doc.page_count, usage, f"{doc.filename} individual OCR text",
        )
        tables_markdown = ""
    else:
        raw_text = doc.content_text or "\n\n".join(
            f"=== Page {p.page_num} ===\n{p.text}" for p in doc.pages
        )
        content_text = await _maybe_compress_with_bear(
            raw_text, doc.page_count, usage, f"{doc.filename} individual text",
        )
        table_parts = [
            f"[Table - page {t.page_num}, {t.row_count}x{t.col_count}]\n{t.markdown}"
            for t in doc.tables
        ]
        raw_tables = "\n\n".join(table_parts) if table_parts else (doc.tables_markdown or "")
        tables_markdown = await _maybe_compress_with_bear(
            raw_tables, doc.page_count, usage, f"{doc.filename} individual tables",
        )

    reporting_unit = _detect_reporting_unit(doc) if doc.has_tables and not is_scan else None
    ctx = _doc_context_block(doc)

    # -- Build prompt --
    parts = [
        f"--- Document Info ---\n{ctx}",
        f"\n--- Fields to Extract ---\n{_fields_block(fields)}",
    ]
    if instructions.strip():
        parts.append(f"\n--- User Instructions ---\n{instructions.strip()}")
    if reporting_unit:
        parts.append(
            f"\n--- Reporting Unit ---\n"
            f"Numeric values in this document are expressed in: {reporting_unit}. "
            f"Report values exactly as they appear in the cells - do NOT append "
            f"'{reporting_unit}' or any other unit word to the number."
        )
    parts.append(f"\n--- Document Text ---\n{content_text}")
    if tables_markdown:
        parts.append(f"\n--- Detected Tables ---\n{tables_markdown}")

    user_prompt = "\n".join(parts) + '\n\nReturn exactly: {"records": [{"Field Name": "value", ...}]}'

    # -- Initial extraction --
    rows = await extract_fn(system, user_prompt, field_names, doc.filename, usage, _TEXT_MODEL)

    if not rows:
        return _empty([doc.filename], field_names)

    row = rows[0] if rows else {}

    # -- Validation: retry if response contains formulas/explanations --
    valid, reason = _single_record_valid(row, field_names)
    if not valid:
        logger.info("Individual validation failed for %s: %s; retrying", doc.filename, reason)
        retry_prompt = "\n".join(parts) + "\n\n" + _SINGLE_RETRY_INSTRUCTION + '\n\nReturn exactly: {"records": [{"Field Name": "value", ...}]}'
        retry_rows = await extract_fn(system, retry_prompt, field_names, doc.filename, usage, _TEXT_MODEL)
        if retry_rows:
            row = retry_rows[0]

    # -- Missing-fields retry loop (up to 2 passes) --
    for attempt in range(2):
        missing = _get_missing(row, field_names)
        if not missing:
            break

        logger.info(
            "Individual missing-fields retry %d for %s: %d missing (%s)",
            attempt + 1, doc.filename, len(missing), ", ".join(missing[:5]),
        )

        retry_fields = [f for f in fields if f["name"] in missing]
        retry_fblock = _fields_block(retry_fields)

        if attempt == 0:
            retry_prompt = (
                f"--- Document Info ---\n{ctx}\n\n"
                f"--- Missing Fields Only ---\n{retry_fblock}\n\n"
                + (f"--- User Instructions ---\n{instructions.strip()}\n\n" if instructions.strip() else "")
                + "--- Retry Objective ---\n"
                + "Fill only the listed missing fields from the provided document context. "
                + "Do not rewrite fields that already have values.\n\n"
                + f"--- Document Text ---\n{content_text}\n\n"
                + (f"--- Detected Tables ---\n{tables_markdown}\n\n" if tables_markdown else "")
                + 'Return exactly: {"records": [{"Field Name": "value", ...}]}'
            )
        else:
            retry_prompt = (
                f"--- Document Info ---\n{ctx}\n\n"
                f"--- Missing Fields Only ---\n{retry_fblock}\n\n"
                + (f"--- User Instructions ---\n{instructions.strip()}\n\n" if instructions.strip() else "")
                + "--- Retry Objective ---\n"
                + _MISSING_FIELDS_FOCUSED_RETRY_INSTRUCTION + "\n"
                + f"--- Document Text ---\n{content_text}\n\n"
                + (f"--- Detected Tables ---\n{tables_markdown}\n\n" if tables_markdown else "")
                + 'Return exactly: {"records": [{"Field Name": "value", ...}]}'
            )

        retry_rows = await extract_fn(
            system, retry_prompt, [f["name"] for f in retry_fields],
            doc.filename, usage, _TEXT_MODEL,
        )
        if retry_rows:
            for fn in missing:
                new_val = retry_rows[0].get(fn)
                if _is_filled_value(new_val) and not _is_filled_value(row.get(fn)):
                    row[fn] = new_val

        # Check if we made progress
        new_missing = _get_missing(row, field_names)
        if len(new_missing) >= len(missing):
            break  # No progress, stop retrying

    # -- Nano cleanup --
    row = await _cleanup_single_row_with_nano(row, fields, doc.filename, usage)

    return [row]
