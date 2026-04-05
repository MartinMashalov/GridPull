"""Extraction router.

Picks the right strategy (individual, multi_record, page_per_row, or SOV)
and applies shared post-processing.
"""
from __future__ import annotations

import json
import logging
from collections import Counter
from typing import Any, Dict, List

from openai import AsyncOpenAI

from app.config import settings
from app.services.pdf_service import ParsedDocument

from .core import (
    _EMPTY_VALUES,
    _TEXT_MODEL,
    _empty,
    _error,
    _fields_block,
    _is_filled_value,
    _maybe_compress_with_bear,
    LLMUsage,
    document_has_wide_data_grid,
    property_schedule_row_cleanup_matches_schema,
    sanitize_duplicate_column_values,
    sanitize_unmatched_field_values,
)
from .llm import (
    _llm_acompletion,
    backfill_missing_row_fields_from_document,
    finalize_property_schedule_rows,
)
from .scan_pipeline import run_ocr_for_document
from . import strategy_individual
from . import strategy_multi_record
from . import strategy_page_per_row

logger = logging.getLogger(__name__)

# ── Strategy names ────────────────────────────────────────────────────────────
STRATEGY_INDIVIDUAL = "individual"
STRATEGY_MULTI_RECORD = "multi_record"
STRATEGY_PAGE_PER_ROW = "page_per_row"


# ── Cerebras routing ──────────────────────────────────────────────────────────

def _pick_cerebras_api_key() -> str | None:
    """Rotate through available Cerebras API keys."""
    for key in (settings.cerebras_api_key, settings.cerebras_api_key2, settings.cerebras_api_key3):
        if key:
            return key
    return None


def _should_extract_multi(doc: ParsedDocument) -> bool:
    """Heuristic: does the document have substantial tables?"""
    if not doc.has_tables:
        return False
    data_tables = [t for t in doc.tables if t.row_count >= 4 and t.col_count >= 2]
    return len(data_tables) >= 1


def _fallback_route(
    doc: ParsedDocument,
    fields: List[Dict[str, str]],
    batch_document_count: int,
) -> str:
    """Heuristic fallback when Cerebras routing is unavailable."""
    has_wide_grid = document_has_wide_data_grid(doc)
    if batch_document_count > 1 and doc.page_count <= 3 and not has_wide_grid:
        return STRATEGY_INDIVIDUAL
    if has_wide_grid or _should_extract_multi(doc):
        return STRATEGY_MULTI_RECORD
    return STRATEGY_INDIVIDUAL


async def _route_with_cerebras(
    doc: ParsedDocument,
    fields: List[Dict[str, str]],
    usage: LLMUsage,
    instructions: str,
    batch_document_count: int,
) -> str:
    """Use Cerebras (fast + cheap) to pick the extraction strategy."""
    api_key = _pick_cerebras_api_key()
    if not api_key:
        return _fallback_route(doc, fields, batch_document_count)

    # Build compact document preview for routing
    planner_text = doc.content_text or "\n\n".join(
        f"=== Page {p.page_num} ===\n{p.text}" for p in doc.pages
    )
    # Truncate to ~4000 chars for the router (we don't need the full doc)
    if len(planner_text) > 4000:
        planner_text = planner_text[:2000] + "\n...\n" + planner_text[-2000:]

    # Include table summary for routing
    table_summary = ""
    if doc.tables:
        big_tables = [t for t in doc.tables if t.row_count >= 3]
        if big_tables:
            table_summary = f"\nTables found: {len(big_tables)} tables with 3+ rows. "
            table_summary += ", ".join(f"({t.row_count}x{t.col_count})" for t in big_tables[:5])
            # Show first table header
            first = big_tables[0]
            if first.markdown:
                lines = first.markdown.split("\n")
                table_summary += f"\nFirst table header: {lines[0][:200]}"

    planner_prompt = (
        f"File: {doc.filename} | Pages: {doc.page_count} | Tables: {len(doc.tables)} | "
        f"Batch: {batch_document_count} files | Structure: {doc.doc_type_hint}\n"
        f"{table_summary}\n\n"
        f"Text preview:\n{planner_text[:2000]}\n\n"
        "Classify as one of: individual, multi_record, page_per_row\n"
        "- individual = one document, one output row\n"
        "- multi_record = file has many records (table rows, repeated sections, multi-year data, comparative financials)\n"
        "- page_per_row = each page is a separate independent record\n"
        "If batch>1 and pages<=3, prefer individual. If unsure, individual.\n\n"
        'Reply with ONLY: {"strategy":"individual"} or {"strategy":"multi_record"} or {"strategy":"page_per_row"}'
    )

    model_name = settings.cerebras_model.replace("cerebras/", "")
    try:
        client = AsyncOpenAI(
            api_key=api_key,
            base_url="https://api.cerebras.ai/v1",
        )
        resp = await client.chat.completions.create(
            model=model_name,
            messages=[{"role": "user", "content": planner_prompt}],
            temperature=0,
            max_tokens=200,
        )
        if resp.usage:
            usage.add(resp.usage.prompt_tokens, resp.usage.completion_tokens)

        raw_content = resp.choices[0].message.content or ""
        # Extract JSON from response (Cerebras may wrap it in markdown)
        import re
        json_match = re.search(r'\{[^}]+\}', raw_content)
        raw = json.loads(json_match.group() if json_match else "{}")
        strategy = str(raw.get("strategy", "")).strip().lower().replace("-", "_")

        if strategy in (STRATEGY_INDIVIDUAL, STRATEGY_MULTI_RECORD, STRATEGY_PAGE_PER_ROW):
            logger.info("Cerebras routed %s -> %s", doc.filename, strategy)
            return strategy

        logger.warning("Cerebras returned unknown strategy '%s' for %s, using fallback", strategy, doc.filename)
        return _fallback_route(doc, fields, batch_document_count)

    except Exception as exc:
        logger.warning("Cerebras routing failed for %s: %s — using fallback", doc.filename, exc)
        return _fallback_route(doc, fields, batch_document_count)


# ── Main entry point ──────────────────────────────────────────────────────────

async def extract_from_document(
    doc: ParsedDocument,
    fields: List[Dict[str, str]],
    usage: LLMUsage,
    instructions: str = "",
    batch_document_count: int = 1,
    use_cerebras: bool = False,
    force_sov: bool = False,
    force_general: bool = False,
) -> List[Dict[str, Any]]:
    """Main extraction entry point. Routes to the right strategy."""
    field_names = [f["name"] for f in fields]

    # ── SOV pipeline ──────────────────────────────────────────────────────
    is_sov_schema = property_schedule_row_cleanup_matches_schema(field_names)
    use_sov_pipeline = force_sov or (not force_general and is_sov_schema)

    if use_sov_pipeline:
        from app.services.sov import extract_sov_from_document

        logger.info(
            "Routing %s -> SOV pipeline (pages=%d, tables=%d, scanned=%s)",
            doc.filename, doc.page_count, len(doc.tables), doc.is_scanned,
        )
        rows = await extract_sov_from_document(doc, fields, usage, instructions)
        doc_full_text = doc.content_text or ""
        rows = sanitize_duplicate_column_values(rows, field_names, doc.tables)
        rows = sanitize_unmatched_field_values(rows, field_names, doc_full_text, doc.tables)
        if rows:
            rows = finalize_property_schedule_rows(rows, field_names)
        if not rows:
            rows = _empty([doc.filename], field_names)
        logger.info(
            "extract_from_document done: filename=%s rows=%d cost=%.6f",
            doc.filename, len(rows), usage.cost_usd,
        )
        return rows

    # ── Route strategy ────────────────────────────────────────────────────
    strategy = await _route_with_cerebras(
        doc, fields, usage, instructions, batch_document_count,
    )

    logger.info(
        "Routing %s -> %s (pages=%d, scanned=%s, hint=%s)",
        doc.filename, strategy, doc.page_count, doc.is_scanned, doc.doc_type_hint,
    )

    # ── OCR for scanned documents ─────────────────────────────────────────
    ocr_text = None
    ocr_pages = None

    if doc.is_scanned:
        ocr_result = await run_ocr_for_document(doc, usage)
        if ocr_result is None:
            return _error([doc.filename], field_names, "OCR failed or unavailable")
        ocr_text, ocr_pages = ocr_result

    # ── Dispatch to strategy ──────────────────────────────────────────────
    if strategy == STRATEGY_PAGE_PER_ROW:
        rows = await strategy_page_per_row.execute(
            doc, fields, usage, instructions, ocr_text, ocr_pages,
        )
    elif strategy == STRATEGY_MULTI_RECORD:
        rows = await strategy_multi_record.execute(
            doc, fields, usage, instructions, ocr_text, ocr_pages,
        )
    else:  # STRATEGY_INDIVIDUAL
        rows = await strategy_individual.execute(
            doc, fields, usage, instructions, ocr_text, ocr_pages,
        )

    # ── Fallback: text pipeline returned nothing, try OCR ─────────────────
    if not doc.is_scanned and settings.mistral_api_key and doc.file_path:
        filled = sum(
            1 for row in rows for fn in field_names
            if row.get(fn) is not None
            and str(row[fn]).strip().lower() not in _EMPTY_VALUES
        )
        if filled == 0:
            logger.info("Text pipeline returned 0%% fill for %s — falling back to OCR", doc.filename)
            ocr_result = await run_ocr_for_document(doc, usage)
            if ocr_result:
                ocr_text, ocr_pages = ocr_result
                if strategy == STRATEGY_PAGE_PER_ROW:
                    rows = await strategy_page_per_row.execute(doc, fields, usage, instructions, ocr_text, ocr_pages)
                elif strategy == STRATEGY_MULTI_RECORD:
                    rows = await strategy_multi_record.execute(doc, fields, usage, instructions, ocr_text, ocr_pages)
                else:
                    rows = await strategy_individual.execute(doc, fields, usage, instructions, ocr_text, ocr_pages)

    # ── Post-processing ───────────────────────────────────────────────────
    doc_full_text = doc.content_text or ""
    rows = sanitize_duplicate_column_values(rows, field_names, doc.tables)
    rows = sanitize_unmatched_field_values(rows, field_names, doc_full_text, doc.tables)

    # Schedule-specific finalization (if field schema matches)
    run_schedule_cleanup = property_schedule_row_cleanup_matches_schema(field_names)
    if rows and run_schedule_cleanup:
        rows = finalize_property_schedule_rows(rows, field_names)

    # ── Propagate constant document-level values across rows ────────────
    #   If a field has the same non-empty value in most rows but is null in
    #   some, fill those gaps (e.g. Vendor Name appears in header, LLM puts
    #   it in some rows but not others).  Pure heuristic — no LLM cost.
    if len(rows) >= 2:
        for fn in field_names:
            filled_vals = [
                str(r[fn]).strip()
                for r in rows
                if not r.get("_error") and _is_filled_value(r.get(fn))
            ]
            if not filled_vals:
                continue
            # Find the dominant value
            counts = Counter(filled_vals)
            dominant_val, dominant_count = counts.most_common(1)[0]
            # Propagate only if: one value dominates AND there are gaps to fill
            missing_count = sum(
                1 for r in rows
                if not r.get("_error") and not _is_filled_value(r.get(fn))
            )
            if missing_count > 0 and dominant_count >= max(2, len(filled_vals) * 0.5):
                for r in rows:
                    if not r.get("_error") and not _is_filled_value(r.get(fn)):
                        r[fn] = dominant_val
                logger.info(
                    "Propagated '%s' = '%s' to %d rows (was in %d/%d)",
                    fn, dominant_val[:40], missing_count, dominant_count, len(rows),
                )

    # ── Backfill missing fields (no threshold — always try) ───────────────
    if rows and len(rows) >= 1:
        text_for_backfill = (doc_full_text or ocr_text or "").strip()
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
                rows, fields, text_for_backfill, doc.page_count,
                doc.filename, usage, instructions,
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

    cache_pct = (usage.cached_input_tokens / usage.input_tokens * 100) if usage.input_tokens else 0
    logger.info(
        "extract_from_document done: filename=%s rows=%d cost=%.6f input_tokens=%d output_tokens=%d cached=%d (%.0f%%)",
        doc.filename, len(rows), usage.cost_usd, usage.input_tokens, usage.output_tokens,
        usage.cached_input_tokens, cache_pct,
    )
    return rows


__all__ = ["LLMUsage", "extract_from_document"]
