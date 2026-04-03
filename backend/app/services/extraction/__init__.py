from __future__ import annotations

import json
import logging
from typing import Any, Dict, List

from app.config import settings
from app.services.pdf_service import ParsedDocument

from .core import (
    _EMPTY_VALUES,
    _TEXT_MODEL,
    _empty,
    _fields_block,
    _maybe_compress_with_bear,
    LLMUsage,
    document_has_wide_data_grid,
    property_schedule_row_cleanup_matches_schema,
    record_llm_usage_cost,
    sanitize_duplicate_column_values,
    sanitize_unmatched_field_values,
)
from .llm import (
    _llm_acompletion,
    backfill_missing_row_fields_from_document,
    finalize_property_schedule_rows,
)
from .scan_pipeline import extract_from_scanned_document
from .text_pipeline import (
    _should_extract_multi,
    extract_multi_record_chunked_validated,
    extract_multi_record_validated,
    extract_per_page,
    extract_single_record,
)

logger = logging.getLogger(__name__)


def _normalise_strategy(value: str) -> str:
    cleaned = (value or "").strip().lower().replace("-", "_").replace(" ", "_")
    if cleaned in {"per_page", "perpage", "page_by_page"}:
        return "per_page"
    if cleaned in {"single_document", "singledocument", "single_file", "small_document"}:
        return "single_document"
    return "full_document"


def _normalise_record_mode(value: str) -> str:
    cleaned = (value or "").strip().lower().replace("-", "_").replace(" ", "_")
    return "multi" if cleaned == "multi" else "single"


def _fallback_general_plan(
    doc: ParsedDocument,
    fields: List[Dict[str, str]],
    batch_document_count: int,
) -> dict[str, str]:
    has_wide_grid = document_has_wide_data_grid(doc)
    if batch_document_count > 1 and doc.page_count <= 3 and not has_wide_grid:
        return {"strategy": "single_document", "record_mode": "single"}
    if has_wide_grid or _should_extract_multi(doc, fields):
        return {"strategy": "full_document", "record_mode": "multi"}
    return {"strategy": "full_document", "record_mode": "single"}


async def _plan_general_extraction(
    doc: ParsedDocument,
    fields: List[Dict[str, str]],
    usage: LLMUsage,
    instructions: str = "",
    batch_document_count: int = 1,
) -> dict[str, str]:
    planner_text = doc.content_text or "\n\n".join(
        f"=== Page {p.page_num} ===\n{p.text}" for p in doc.pages
    )
    planner_tables = doc.tables_markdown or "\n\n".join(
        f"[Table - page {t.page_num}, {t.row_count}x{t.col_count}]\n{t.markdown}"
        for t in doc.tables
    )
    planner_prompt = (
        "Decide the best extraction flow for this file.\n\n"
        "Return exactly this JSON shape:\n"
        '{"strategy":"per_page|full_document|single_document","record_mode":"single|multi"}\n\n'
        "Meaning:\n"
        "- per_page: each page is an independent record, like one invoice or statement per page\n"
        "- full_document: use the whole file because the information is scattered across the document or repeated within one master schedule/table/section\n"
        "- single_document: this file itself is one small standalone document/image and should produce one row for this file only\n\n"
        "Rules:\n"
        "- per_page means one row per page and record_mode must be single\n"
        "- single_document means one row for this file and record_mode must be single\n"
        "- full_document + single means one record may require context from multiple pages\n"
        "- full_document + multi means multiple records come from one large file, one master schedule, repeated sections, or comparative columns/rows\n"
        "- If this upload batch contains multiple files and this file is a short standalone document/image, prefer single_document\n"
        "- Use per_page only when pages are independent records, not when one record continues across multiple pages\n"
        "- If unsure, choose full_document\n\n"
        f"Filename: {doc.filename}\n"
        f"Total pages: {doc.page_count}\n"
        f"Document structure hint: {doc.doc_type_hint}\n"
        f"Upload batch document count: {batch_document_count}\n"
        f"Detected tables: {len(doc.tables)}\n"
        f"Requested fields:\n{_fields_block(fields)}\n\n"
        + (f"User instructions:\n{instructions.strip()}\n\n" if instructions.strip() else "")
        + f"Document text:\n{await _maybe_compress_with_bear(planner_text, doc.page_count, usage, f'{doc.filename} planner text')}\n\n"
        f"Detected tables:\n{await _maybe_compress_with_bear(planner_tables, doc.page_count, usage, f'{doc.filename} planner tables')}"
    )
    try:
        planner_resp = await _llm_acompletion(
            model=_TEXT_MODEL,
            messages=[{"role": "user", "content": planner_prompt}],
            temperature=0,
            response_format={"type": "json_object"},
            max_tokens=80,
        )
        if planner_resp.usage:
            usage.add(planner_resp.usage.prompt_tokens, planner_resp.usage.completion_tokens)
        record_llm_usage_cost(usage, planner_resp)
        raw = json.loads(planner_resp.choices[0].message.content or "{}")
        plan = {
            "strategy": _normalise_strategy(str(raw.get("strategy", ""))),
            "record_mode": _normalise_record_mode(str(raw.get("record_mode", ""))),
        }
        if plan["strategy"] != "full_document":
            plan["record_mode"] = "single"
        return plan
    except Exception as exc:
        fallback = _fallback_general_plan(doc, fields, batch_document_count)
        logger.warning(
            "Routing planner failed for %s: %s - falling back to %s/%s",
            doc.filename,
            exc,
            fallback["strategy"],
            fallback["record_mode"],
        )
        return fallback


async def extract_from_document(
    doc: ParsedDocument,
    fields: List[Dict[str, str]],
    usage: LLMUsage,
    instructions: str = "",
    batch_document_count: int = 1,
    use_cerebras: bool = False,
) -> List[Dict[str, Any]]:
    field_names = [f["name"] for f in fields]
    is_sov_schema = property_schedule_row_cleanup_matches_schema(field_names)
    has_wide_grid = document_has_wide_data_grid(doc)

    if is_sov_schema:
        from app.services.sov import extract_sov_from_document

        logger.info(
            "Routing %s -> dedicated SOV pipeline (pages=%d, tables=%d, scanned=%s, cerebras=%s)",
            doc.filename,
            doc.page_count,
            len(doc.tables),
            doc.is_scanned,
            use_cerebras,
        )
        rows = await extract_sov_from_document(doc, fields, usage, instructions, use_cerebras=use_cerebras)
        doc_full_text = doc.content_text or ""
        rows = sanitize_duplicate_column_values(rows, field_names, doc.tables)
        rows = sanitize_unmatched_field_values(rows, field_names, doc_full_text, doc.tables)
        if rows:
            rows = finalize_property_schedule_rows(rows, field_names)
        if not rows:
            rows = _empty([doc.filename], field_names)
        logger.info(
            "extract_from_document done: filename=%s rows=%d cost_usd=%.6f input_tokens=%d output_tokens=%d",
            doc.filename,
            len(rows),
            usage.cost_usd,
            usage.input_tokens,
            usage.output_tokens,
        )
        return rows

    plan = await _plan_general_extraction(doc, fields, usage, instructions, batch_document_count)
    strategy = plan["strategy"]
    record_mode = plan["record_mode"]
    scan_mode = "multi" if record_mode == "multi" or has_wide_grid else "single"

    logger.info(
        "Routing %s -> general pipeline strategy=%s record_mode=%s scanned=%s hint=%s",
        doc.filename,
        strategy,
        record_mode,
        doc.is_scanned,
        doc.doc_type_hint,
    )

    if doc.is_scanned:
        if strategy == "per_page":
            rows = await extract_from_scanned_document(
                doc, fields, usage, instructions, forced_mode="per_page", enable_retry=False,
            )
        elif strategy == "single_document":
            rows = await extract_from_scanned_document(
                doc, fields, usage, instructions, forced_mode="single", enable_retry=False,
            )
        else:
            rows = await extract_from_scanned_document(
                doc, fields, usage, instructions, forced_mode=scan_mode, enable_retry=True,
            )
    else:
        if strategy == "per_page":
            logger.info("TEXT per-page extraction: %s (%d pages)", doc.filename, doc.page_count)
            rows = await extract_per_page(doc, fields, usage, instructions)
        elif strategy == "single_document":
            logger.info("TEXT single-document extraction: %s", doc.filename)
            rows = await extract_single_record(doc, fields, usage, instructions, enable_retry=False)
        elif scan_mode == "multi":
            if doc.page_count > settings.extraction_chunk_threshold_pages:
                n_chunks = -(-doc.page_count // settings.extraction_chunk_size)
                logger.info("TEXT full-document multi-record: %s (%d pages, %d chunks)", doc.filename, doc.page_count, n_chunks)
                rows = await extract_multi_record_chunked_validated(doc, fields, usage, instructions)
            else:
                rows = await extract_multi_record_validated(doc, fields, usage, instructions)
        else:
            logger.info("TEXT full-document single-record: %s", doc.filename)
            rows = await extract_single_record(doc, fields, usage, instructions, enable_retry=True)

        filled = sum(
            1 for row in rows for fn in field_names
            if row.get(fn) is not None
            and str(row[fn]).strip().lower() not in _EMPTY_VALUES
        )
        if filled == 0 and settings.mistral_api_key and doc.file_path:
            logger.info(
                "TEXT pipeline returned 0%% FFR for %s — falling back to SCAN pipeline (OCR)",
                doc.filename,
            )
            fallback_mode = "per_page" if strategy == "per_page" else ("single" if strategy == "single_document" else scan_mode)
            rows = await extract_from_scanned_document(
                doc,
                fields,
                usage,
                instructions,
                forced_mode=fallback_mode,
                enable_retry=strategy == "full_document",
            )

    field_names = [f["name"] for f in fields]
    doc_full_text = doc.content_text or ""
    rows = sanitize_duplicate_column_values(rows, field_names, doc.tables)
    rows = sanitize_unmatched_field_values(rows, field_names, doc_full_text, doc.tables)

    run_schedule_cleanup = property_schedule_row_cleanup_matches_schema(field_names)
    if rows and run_schedule_cleanup:
        rows = finalize_property_schedule_rows(rows, field_names)

    if rows and (run_schedule_cleanup or has_wide_grid) and len(rows) > 1:
        text_for_backfill = doc_full_text.strip()
        for _ in range(3):
            if not text_for_backfill:
                break
            missing_before = sum(
                1
                for i in range(len(rows))
                if not rows[i].get("_error")
                for fn in field_names
                if rows[i].get(fn) is None
                or str(rows[i].get(fn, "")).strip().lower() in _EMPTY_VALUES
            )
            if missing_before == 0:
                break
            rows = await backfill_missing_row_fields_from_document(
                rows,
                fields,
                doc_full_text,
                doc.page_count,
                doc.filename,
                usage,
                instructions,
            )
            rows = sanitize_duplicate_column_values(rows, field_names, doc.tables)
            rows = sanitize_unmatched_field_values(rows, field_names, doc_full_text, doc.tables)
            missing_after = sum(
                1
                for i in range(len(rows))
                if not rows[i].get("_error")
                for fn in field_names
                if rows[i].get(fn) is None
                or str(rows[i].get(fn, "")).strip().lower() in _EMPTY_VALUES
            )
            if missing_after >= missing_before:
                break

    if not rows:
        rows = _empty([doc.filename], field_names)

    logger.info(
        "extract_from_document done: filename=%s rows=%d cost_usd=%.6f input_tokens=%d output_tokens=%d",
        doc.filename,
        len(rows),
        usage.cost_usd,
        usage.input_tokens,
        usage.output_tokens,
    )
    return rows


__all__ = ["LLMUsage", "extract_from_document"]
