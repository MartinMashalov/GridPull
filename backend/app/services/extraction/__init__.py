from __future__ import annotations

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
)
from .llm import (
    _litellm_acompletion,
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


async def extract_from_document(
    doc: ParsedDocument,
    fields: List[Dict[str, str]],
    usage: LLMUsage,
    instructions: str = "",
) -> List[Dict[str, Any]]:
    if doc.is_scanned:
        logger.info(
            "Routing %s -> SCAN pipeline (avg_chars_per_page=%.0f)",
            doc.filename,
            sum(len(p.text) for p in doc.pages) / max(len(doc.pages), 1),
        )
        rows = await extract_from_scanned_document(doc, fields, usage, instructions)
    else:
        extraction_mode = "single"
        planner_text = doc.content_text or "\n\n".join(
            f"=== Page {p.page_num} ===\n{p.text}" for p in doc.pages
        )
        planner_tables = doc.tables_markdown or "\n\n".join(
            f"[Table - page {t.page_num}, {t.row_count}x{t.col_count}]\n{t.markdown}"
            for t in doc.tables
        )
        planner_prompt = (
            "Decide whether this document should produce ONE output object or MANY output objects "
            "for the requested schema.\n\n"
            "Reply with exactly one word:\n"
            "- single: the requested fields describe the document as a whole, so there should be one row per file\n"
            "- multi: the same requested fields can be filled repeatedly from the same file (e.g. rows in a single table)\n"
            "- multi_paged: the file is a compilation of independent documents/invoices/statements where each page "
            "(or small group of pages) is a separate record with its own values for the requested fields. "
            "Examples: a PDF of many invoices concatenated together, monthly statements batched into one file, "
            "multiple unrelated policies or customer accounts printed sequentially with no shared master schedule.\n\n"
            "Rules:\n"
            "- Base the decision on the requested fields plus the document structure\n"
            "- A file can contain tables and still be single if the requested fields are document-level\n"
            "- A file can be multi even when repeated records are arranged across columns instead of rows\n"
            "- Financial reports / annual reports / 10-K filings / earnings reports: when the requested fields "
            "include a date, year, or period field alongside financial metrics (revenue, costs, income, etc.), "
            "classify as multi — these documents contain comparative financial statements with the same metrics "
            "repeated for multiple fiscal years (e.g. 2023, 2022, 2021 as separate columns). "
            "Emit one row per fiscal year/period found in the comparative statements.\n"
            "- Insurance: statement of values (SOV), property schedule, location listing, appraisal reports with a "
            "summary schedule of values followed by per-location narrative sections -> ALWAYS multi (one row per "
            "insured location from the schedule; narrative fills gaps). NEVER multi_paged for that pattern.\n"
            "- Use multi_paged ONLY when pages clearly belong to different independent records, not when a single record spans multiple pages\n"
            "- If unsure, reply single\n\n"
            f"Filename: {doc.filename}\n"
            f"Total pages: {doc.page_count}\n"
            f"Document structure hint: {doc.doc_type_hint}\n"
            f"Requested fields:\n{_fields_block(fields)}\n\n"
            + (f"User instructions:\n{instructions.strip()}\n\n" if instructions.strip() else "")
            + f"Document text:\n{await _maybe_compress_with_bear(planner_text, doc.page_count, usage, f'{doc.filename} planner text')}\n\n"
            f"Detected tables:\n{await _maybe_compress_with_bear(planner_tables, doc.page_count, usage, f'{doc.filename} planner tables')}"
        )
        try:
            planner_resp = await _litellm_acompletion(
                model=_TEXT_MODEL,
                messages=[{"role": "user", "content": planner_prompt}],
                temperature=0,
                max_tokens=8,
            )
            if planner_resp.usage:
                usage.add(planner_resp.usage.prompt_tokens, planner_resp.usage.completion_tokens)
            record_llm_usage_cost(usage, planner_resp)
            planner_raw = (planner_resp.choices[0].message.content or "").strip().lower().replace("_", "")
            if "multipaged" in planner_raw or planner_raw == "multi_paged":
                extraction_mode = "multi_paged"
            elif planner_raw == "multi":
                extraction_mode = "multi"
            else:
                extraction_mode = "single"
            logger.info("Routing %s -> TEXT pipeline (%s, hint=%s)", doc.filename, extraction_mode, doc.doc_type_hint)
        except Exception as exc:
            extraction_mode = "multi" if _should_extract_multi(doc, fields) else "single"
            logger.warning("Routing planner failed for %s: %s - falling back to %s", doc.filename, exc, extraction_mode)

        if extraction_mode == "multi_paged" and document_has_wide_data_grid(doc):
            logger.info(
                "Overriding multi_paged -> multi for %s (parsed wide table grid — avoid per-page split)",
                doc.filename,
            )
            extraction_mode = "multi"

        if extraction_mode == "multi_paged":
            logger.info("TEXT per-page extraction: %s (%d pages)", doc.filename, doc.page_count)
            rows = await extract_per_page(doc, fields, usage, instructions)
        elif extraction_mode == "multi":
            if doc.page_count > settings.extraction_chunk_threshold_pages:
                n_chunks = -(-doc.page_count // settings.extraction_chunk_size)
                logger.info("TEXT chunked multi-record (validated): %s (%d pages, %d chunks)", doc.filename, doc.page_count, n_chunks)
                rows = await extract_multi_record_chunked_validated(doc, fields, usage, instructions)
            else:
                rows = await extract_multi_record_validated(doc, fields, usage, instructions)
        else:
            rows = await extract_single_record(doc, fields, usage, instructions)

        field_names = [f["name"] for f in fields]
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
            rows = await extract_from_scanned_document(doc, fields, usage, instructions)

    field_names = [f["name"] for f in fields]
    if rows and property_schedule_row_cleanup_matches_schema(field_names):
        rows = finalize_property_schedule_rows(rows, field_names)
        text_for_backfill = (doc.content_text or "").strip()
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
                doc.content_text or "",
                doc.page_count,
                doc.filename,
                usage,
                instructions,
            )
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
