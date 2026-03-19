from __future__ import annotations

import asyncio
import logging
import re
from typing import Any, Dict, List

from app.config import settings
from app.services.pdf_service import ParsedDocument

from .core import (
    _CHUNK_SIZE,
    _CHUNK_THRESHOLD_PAGES,
    _MISSING_FIELDS_FOCUSED_RETRY_INSTRUCTION,
    _SCAN_FINAL_RETRY_TEXT_BUDGET_CHARS,
    _SCAN_MULTI_SYSTEM,
    _SCAN_RETRY_TEXT_BUDGET_CHARS,
    _SCAN_SINGLE_SYSTEM,
    _SCAN_TEXT_BUDGET_CHARS,
    _SINGLE_DOC_MIN_FFR,
    _SINGLE_DOC_RETRY_MIN_MISSING_FIELDS,
    _SINGLE_RETRY_INSTRUCTION,
    _empty,
    _error,
    _fields_block,
    _is_filled_value,
    _maybe_compress_with_bear,
    _single_quality_gate,
    _single_record_valid,
    LLMUsage,
    document_has_wide_data_grid,
)
from .llm import _cleanup_single_row_with_nano, _litellm_extract, _review_multi_rows

logger = logging.getLogger(__name__)


async def _extract_scanned_chunked(
    ocr_text: str,
    doc: ParsedDocument,
    fields: List[Dict[str, str]],
    field_names: List[str],
    fblock: str,
    usage: LLMUsage,
    instructions: str = "",
) -> List[Dict[str, Any]]:
    inject_global_tables = document_has_wide_data_grid(doc)
    table_prefix = ""
    if inject_global_tables and doc.tables:
        table_parts: List[str] = []
        tbudget = 14_000
        for t in doc.tables:
            if tbudget <= 0:
                break
            entry = f"[Table - page {t.page_num}, {t.row_count}x{t.col_count}]\n{t.markdown}"
            clipped = entry[: min(8_000, tbudget)]
            if clipped:
                table_parts.append(clipped)
                tbudget -= len(clipped)
        raw_tables = "\n\n".join(table_parts)[:14_000]
        if raw_tables.strip():
            table_prefix = await _maybe_compress_with_bear(
                raw_tables, doc.page_count, usage, f"{doc.filename} OCR SOV tables",
            )

    parts = re.split(r"(=== Page \d+ ===)", ocr_text)
    pages: List[str] = []
    i = 1
    while i < len(parts) - 1:
        pages.append(parts[i] + "\n" + parts[i + 1])
        i += 2
    if not pages:
        pages = [ocr_text]

    chunks = [pages[i : i + _CHUNK_SIZE] for i in range(0, len(pages), _CHUNK_SIZE)]

    async def _chunk_task(chunk_pages: list) -> List[Dict]:
        chunk_text = await _maybe_compress_with_bear(
            "\n\n".join(chunk_pages)[:20_000],
            doc.page_count,
            usage,
            f"{doc.filename} OCR chunk",
        )
        sov_note = ""
        if inject_global_tables and table_prefix:
            sov_note = (
                "--- Schedule priority ---\n"
                "If parser-detected Tables include a master schedule of values with monetary columns, "
                "emit one record per schedule row with all $ fields from that row; use this OCR chunk text "
                "to fill fields the table omits. Do not use narrative component subtotals as schedule "
                "amounts when the table row already lists building/BPP/BI/TIV for that location.\n\n"
            )
        prompt = (
            f"--- Document Info ---\n"
            f"Filename: {doc.filename}\nTotal pages: {doc.page_count}\n"
            f"Source: Scanned document (OCR by Mistral)\n\n"
            f"--- Fields (one object per repeated record) ---\n{fblock}\n\n"
            + (f"--- User Instructions ---\n{instructions.strip()}\n\n" if instructions.strip() else "")
            + sov_note
            + (f"--- Parser-detected tables (full file) ---\n{table_prefix}\n\n" if table_prefix else "")
            + f"--- OCR Text (this chunk) ---\n{chunk_text}\n\n"
            'Extract ALL repeated records in this chunk. '
            'Return: {"records": [...]}. No records here -> {"records": []}.'
        )
        return await _litellm_extract(_SCAN_MULTI_SYSTEM, prompt, field_names, doc.filename, usage)

    chunk_results = await asyncio.gather(*[_chunk_task(c) for c in chunks])
    all_rows: List[Dict[str, Any]] = []
    for rows in chunk_results:
        all_rows.extend(r for r in rows if any(r.get(fn) for fn in field_names))

    if not all_rows:
        return _empty([doc.filename], field_names)
    return await _review_multi_rows(all_rows, field_names, doc.filename, usage, ocr_text, instructions)


async def extract_from_scanned_document(
    doc: ParsedDocument,
    fields: List[Dict[str, str]],
    usage: LLMUsage,
    instructions: str = "",
) -> List[Dict[str, Any]]:
    from app.services.ocr_service import run_mistral_ocr

    field_names = [f["name"] for f in fields]

    if not settings.mistral_api_key:
        msg = "Scanned OCR unavailable: MISTRAL_API_KEY not set"
        logger.error(
            "Scanned doc detected (%s) but MISTRAL_API_KEY not set - returning error row",
            doc.filename,
        )
        return _error([doc.filename], field_names, msg)

    logger.info("SCAN pipeline - Mistral OCR starting: %s (%d pages)", doc.filename, doc.page_count)

    try:
        ocr_text, ocr_page_count, ocr_cost_usd = await run_mistral_ocr(doc.file_path, settings.mistral_api_key)
        usage.add_ocr_cost(ocr_cost_usd)
        logger.info(
            "SCAN pipeline - OCR complete: %s - %d pages, %d chars, $%.4f",
            doc.filename,
            ocr_page_count,
            len(ocr_text),
            ocr_cost_usd,
        )
    except Exception as exc:
        msg = f"Scanned OCR failed: {exc}"
        logger.error("SCAN pipeline - OCR failed for %s: %s - returning error row", doc.filename, exc)
        return _error([doc.filename], field_names, msg)

    if not ocr_text.strip():
        msg = "Scanned OCR failed: empty OCR text"
        logger.error("SCAN pipeline - OCR returned empty text for %s", doc.filename)
        return _error([doc.filename], field_names, msg)

    fblock = _fields_block(fields)
    extraction_mode = "single"
    planner_prompt = (
        "Decide whether this OCR document should produce ONE output object or MANY output objects "
        "for the requested schema.\n\n"
        "Reply with exactly one word:\n"
        "- single: the requested fields describe the document as a whole, so there should be one row per file\n"
        "- multi: the same requested fields can be filled repeatedly from the same file, so there should be many rows from one file\n\n"
        "Rules:\n"
        "- Base the decision on the requested fields plus the OCR structure\n"
        "- Repeated records may appear across rows, columns, repeated sections, or repeated line items\n"
        "- If unsure, reply single\n\n"
        f"Filename: {doc.filename}\n"
        f"Total pages: {doc.page_count}\n"
        f"Requested fields:\n{fblock}\n\n"
        + (f"User instructions:\n{instructions.strip()}\n\n" if instructions.strip() else "")
        + f"OCR text:\n{await _maybe_compress_with_bear(ocr_text[:20_000], doc.page_count, usage, f'{doc.filename} OCR planner')}"
    )
    try:
        planner_resp = await _litellm_extract(
            _SCAN_SINGLE_SYSTEM,
            planner_prompt + '\n\nReturn: {"records": [{"mode": "single"}]}',
            ["mode"],
            doc.filename,
            usage,
        )
        planner_mode = (planner_resp[0].get("mode", "") if planner_resp else "").strip().lower()
        extraction_mode = "multi" if planner_mode == "multi" else "single"
        logger.info("SCAN pipeline - planned %s extraction: %s", extraction_mode, doc.filename)
    except Exception as exc:
        markdown_table_lines = len(re.findall(r"^\|.+\|", ocr_text, re.M))
        extraction_mode = "multi" if markdown_table_lines >= 6 else "single"
        logger.warning("SCAN planner failed for %s: %s - falling back to %s", doc.filename, exc, extraction_mode)

    if extraction_mode == "single" and document_has_wide_data_grid(doc):
        logger.info(
            "SCAN pipeline - overriding single -> multi for %s (wide parsed table grid)",
            doc.filename,
        )
        extraction_mode = "multi"

    if extraction_mode == "multi" and doc.page_count > _CHUNK_THRESHOLD_PAGES:
        logger.info("SCAN pipeline - chunked multi-record: %s", doc.filename)
        return await _extract_scanned_chunked(ocr_text, doc, fields, field_names, fblock, usage, instructions)

    ctx = (
        f"Filename: {doc.filename}\n"
        f"Total pages: {doc.page_count}\n"
        f"Source: Scanned document (OCR by Mistral)"
    )

    if extraction_mode == "multi":
        logger.info("SCAN pipeline - single-call multi-record: %s", doc.filename)
        system = _SCAN_MULTI_SYSTEM
        instruction = 'Return: {"records": [{"Field": "value"}, ...]}'
    else:
        logger.info("SCAN pipeline - single-record: %s", doc.filename)
        system = _SCAN_SINGLE_SYSTEM
        instruction = 'Return: {"records": [{"Field Name": "value", ...}]}'

    user_prompt = (
        f"--- Document Info ---\n{ctx}\n\n"
        f"--- Fields to Extract ---\n{fblock}\n\n"
        + (f"--- User Instructions ---\n{instructions.strip()}\n\n" if instructions.strip() else "")
        + f"--- OCR Text (Mistral OCR) ---\n{await _maybe_compress_with_bear(ocr_text[:_SCAN_TEXT_BUDGET_CHARS], doc.page_count, usage, f'{doc.filename} OCR extract')}\n\n"
        + instruction
    )

    rows = await _litellm_extract(system, user_prompt, field_names, doc.filename, usage)
    if extraction_mode != "multi":
        if len(rows) == 1:
            valid, reason = _single_record_valid(rows[0], field_names)
            if not valid:
                logger.info(
                    "SCAN single-record validation failed for %s: %s; retrying with stronger guidance",
                    doc.filename,
                    reason,
                )
                retry_prompt = user_prompt + "\n\n" + _SINGLE_RETRY_INSTRUCTION + "\n\n" + instruction
                rows = await _litellm_extract(system, retry_prompt, field_names, doc.filename, usage)
                if len(rows) == 1:
                    valid2, _ = _single_record_valid(rows[0], field_names)
                    if not valid2:
                        logger.warning("SCAN single-record retry still invalid for %s", doc.filename)
        if len(rows) == 1:
            gate_ok, fill_rate, missing_fields = _single_quality_gate(rows[0], field_names, _SINGLE_DOC_MIN_FFR)
            if not gate_ok and len(missing_fields) >= _SINGLE_DOC_RETRY_MIN_MISSING_FIELDS:
                logger.info(
                    "SCAN per-doc gate failed for %s (FFR=%.1f%%, missing=%d); running missing-fields retry",
                    doc.filename,
                    fill_rate * 100,
                    len(missing_fields),
                )
                retry_fields = [f for f in fields if f["name"] in missing_fields]
                retry_fblock = _fields_block(retry_fields)
                retry_prompt = (
                    f"--- Document Info ---\n{ctx}\n\n"
                    f"--- Missing Fields Only ---\n{retry_fblock}\n\n"
                    + (f"--- User Instructions ---\n{instructions.strip()}\n\n" if instructions.strip() else "")
                    + "--- Retry Objective ---\n"
                    + "Fill only the listed missing fields using the OCR text. "
                    + "Do not rewrite fields that already have values.\n\n"
                    + f"--- OCR Text (Mistral OCR) ---\n{await _maybe_compress_with_bear(ocr_text[:_SCAN_RETRY_TEXT_BUDGET_CHARS], doc.page_count, usage, f'{doc.filename} OCR missing-fields')}\n\n"
                    + 'Return exactly: {"records": [{"Field Name": "value", ...}]}'
                )
                retry_rows = await _litellm_extract(
                    _SCAN_SINGLE_SYSTEM,
                    retry_prompt,
                    [f["name"] for f in retry_fields],
                    doc.filename,
                    usage,
                )
                if retry_rows:
                    merged = dict(rows[0])
                    retry_row = retry_rows[0]
                    for fn in missing_fields:
                        old = merged.get(fn)
                        new_val = retry_row.get(fn)
                        if not _is_filled_value(old) and _is_filled_value(new_val):
                            merged[fn] = new_val
                    rows = [merged]
                    gate_ok2, fill_rate2, missing2 = _single_quality_gate(rows[0], field_names, _SINGLE_DOC_MIN_FFR)
                    logger.info(
                        "SCAN per-doc gate result for %s after retry: pass=%s FFR=%.1f%% missing=%d",
                        doc.filename,
                        gate_ok2,
                        fill_rate2 * 100,
                        len(missing2),
                    )
                    if missing2:
                        final_retry_fields = [f for f in fields if f["name"] in missing2]
                        final_retry_fblock = _fields_block(final_retry_fields)
                        final_retry_prompt = (
                            f"--- Document Info ---\n{ctx}\n\n"
                            f"--- Missing Fields Only ---\n{final_retry_fblock}\n\n"
                            + (f"--- User Instructions ---\n{instructions.strip()}\n\n" if instructions.strip() else "")
                            + "--- Retry Objective ---\n"
                            + _MISSING_FIELDS_FOCUSED_RETRY_INSTRUCTION
                            + "\n--- OCR Text (Mistral OCR) ---\n"
                            + await _maybe_compress_with_bear(
                                ocr_text[:_SCAN_FINAL_RETRY_TEXT_BUDGET_CHARS],
                                doc.page_count,
                                usage,
                                f"{doc.filename} OCR final missing-fields",
                            )
                            + "\n\n"
                            + 'Return exactly: {"records": [{"Field Name": "value", ...}]}'
                        )
                        final_retry_rows = await _litellm_extract(
                            _SCAN_SINGLE_SYSTEM,
                            final_retry_prompt,
                            [f["name"] for f in final_retry_fields],
                            doc.filename,
                            usage,
                        )
                        if final_retry_rows:
                            merged2 = dict(rows[0])
                            final_retry_row = final_retry_rows[0]
                            for fn in missing2:
                                old = merged2.get(fn)
                                new_val = final_retry_row.get(fn)
                                if not _is_filled_value(old) and _is_filled_value(new_val):
                                    merged2[fn] = new_val
                            rows = [merged2]
                            gate_ok3, fill_rate3, missing3 = _single_quality_gate(rows[0], field_names, _SINGLE_DOC_MIN_FFR)
                            logger.info(
                                "SCAN per-doc final retry result for %s: pass=%s FFR=%.1f%% missing=%d",
                                doc.filename,
                                gate_ok3,
                                fill_rate3 * 100,
                                len(missing3),
                            )
        if len(rows) == 1:
            rows = [await _cleanup_single_row_with_nano(rows[0], fields, doc.filename, usage)]
        return rows
    return await _review_multi_rows(rows, field_names, doc.filename, usage, ocr_text, instructions)
