from __future__ import annotations

import asyncio
import logging
import re
from typing import Any, Dict, List

from app.services.pdf_service import ParsedDocument, ParsedPage

from .core import (
    _CHUNK_SIZE,
    _MISSING_FIELDS_FOCUSED_RETRY_INSTRUCTION,
    _MULTI_SYSTEM,
    _SINGLE_DOC_MIN_FFR,
    _SINGLE_DOC_RETRY_MIN_MISSING_FIELDS,
    _SINGLE_FINAL_RETRY_TEXT_BUDGET_CHARS,
    _SINGLE_RETRY_INSTRUCTION,
    _SINGLE_SYSTEM,
    _SINGLE_TABLE_BUDGET_CHARS,
    _SINGLE_TEXT_BUDGET_CHARS,
    _TEXT_MODEL,
    _detect_reporting_unit,
    _doc_context_block,
    _empty,
    _fields_block,
    _is_filled_value,
    _maybe_compress_with_bear,
    _single_quality_gate,
    _single_record_valid,
    LLMUsage,
    document_has_wide_data_grid,
)
from .llm import (
    _cleanup_single_row_with_nano,
    _extract_record_count_metadata,
    _llm_extract,
    _review_multi_rows,
)

logger = logging.getLogger(__name__)


async def extract_single_record(
    doc: ParsedDocument,
    fields: List[Dict[str, str]],
    usage: LLMUsage,
    instructions: str = "",
) -> List[Dict[str, Any]]:
    field_names = [f["name"] for f in fields]
    ctx = _doc_context_block(doc)
    fblock = _fields_block(fields)
    single_text_budget = min(_SINGLE_TEXT_BUDGET_CHARS, max(36_000, doc.page_count * 4_500))
    field_phrases: List[str] = []
    for f in fields:
        name = str(f["name"]).strip().lower()
        desc = str(f.get("description", "") or "").strip().lower()
        if name:
            field_phrases.append(name)
        if desc and desc != name:
            field_phrases.append(desc)

    ignored_terms = {
        "best",
        "context",
        "description",
        "document",
        "field",
        "fields",
        "from",
        "match",
        "present",
        "primary",
        "report",
        "reported",
        "return",
        "semantic",
        "shown",
        "this",
        "that",
        "use",
        "value",
        "values",
        "with",
    }
    field_terms = {
        term
        for phrase in field_phrases
        for term in re.findall(r"[a-z][a-z0-9]{3,}", phrase)
        if term not in ignored_terms
    }
    priority_keywords = (
        "balance sheet",
        "statement of financial position",
        "statement of operations",
        "statement of income",
        "income statement",
        "statement of earnings",
        "statement of comprehensive income",
        "statement of stockholders",
        "statement of shareholders",
        "statement of equity",
        "statement of cash flows",
        "cash flow",
        "assets",
        "liabilities",
        "equity",
        "revenue",
        "revenues",
        "net income",
        "net earnings",
        "operating income",
        "operating earnings",
        "total assets",
        "total equity",
    )
    scored_pages = []
    for p in doc.pages:
        text_lower = p.text.lower()
        keyword_hits = sum(1 for kw in priority_keywords if kw in text_lower)
        phrase_hits = sum(1 for phrase in field_phrases if phrase and phrase in text_lower)
        term_hits = sum(1 for term in field_terms if term in text_lower)
        score = (
            len(p.tables) * 450
            + (160 if p.has_numbers else 0)
            + (60 if p.has_dates else 0)
            + keyword_hits * 180
            + phrase_hits * 140
            + min(term_hits, 10) * 40
            + min(p.word_count, 1_200) * 0.1
        )
        if p.page_num <= 3:
            score += 20
        if p.page_num >= max(1, doc.page_count - 12):
            score += 20
        scored_pages.append((score, p))
    scored_pages.sort(key=lambda item: (item[0], item[1].page_num), reverse=True)

    priority_pages: List[Any] = []
    priority_page_nums: set[int] = set()
    for _, page in scored_pages[:18]:
        for page_num in (page.page_num - 1, page.page_num, page.page_num + 1):
            if page_num < 1 or page_num > doc.page_count or page_num in priority_page_nums:
                continue
            priority_pages.append(doc.pages[page_num - 1])
            priority_page_nums.add(page_num)
        if len(priority_pages) >= 24:
            break

    text_sections: List[str] = []
    remaining_text_budget = single_text_budget
    priority_text_parts: List[str] = []
    for p in priority_pages:
        if remaining_text_budget <= 0:
            break
        part = f"=== Page {p.page_num} ===\n{p.text}"
        clipped = part[: min(4_500, remaining_text_budget)]
        if not clipped:
            break
        priority_text_parts.append(clipped)
        remaining_text_budget -= len(clipped)
    if priority_text_parts:
        text_sections.append("[Priority pages likely to contain the requested facts]\n" + "\n\n".join(priority_text_parts))

    sampled_text = doc.content_text or ""
    if sampled_text.strip() and remaining_text_budget > 0:
        sampled_text_parts: List[str] = []
        sampled_matches = list(re.finditer(r"=== Page (\d+) ===\n(.*?)(?=\n\n=== Page \d+ ===|\Z)", sampled_text, re.S))
        if sampled_matches:
            for match in sampled_matches:
                page_num = int(match.group(1))
                if page_num in priority_page_nums:
                    continue
                part = f"=== Page {page_num} ===\n{match.group(2).strip()}"
                clipped = part[: min(1_600, remaining_text_budget)]
                if not clipped:
                    break
                sampled_text_parts.append(clipped)
                remaining_text_budget -= len(clipped)
                if remaining_text_budget <= 0:
                    break
        else:
            clipped = sampled_text[:remaining_text_budget]
            if clipped:
                sampled_text_parts.append(clipped)
                remaining_text_budget -= len(clipped)
        if sampled_text_parts:
            text_sections.append("[Parser-selected document sample]\n" + "\n\n".join(sampled_text_parts))

    if not text_sections:
        fallback_text_parts: List[str] = []
        for p in doc.pages:
            if remaining_text_budget <= 0:
                break
            part = f"=== Page {p.page_num} ===\n{p.text}"
            clipped = part[: min(3_500, remaining_text_budget)]
            if not clipped:
                break
            fallback_text_parts.append(clipped)
            remaining_text_budget -= len(clipped)
        if fallback_text_parts:
            text_sections.append("\n\n".join(fallback_text_parts))

    raw_single_text = "\n\n".join(text_sections)[:_SINGLE_TEXT_BUDGET_CHARS] or doc.content_text
    content_text = await _maybe_compress_with_bear(raw_single_text, doc.page_count, usage, f"{doc.filename} single text")

    single_table_budget = min(_SINGLE_TABLE_BUDGET_CHARS, max(18_000, doc.page_count * 2_500))
    table_candidates = []
    for t in doc.tables:
        page_text_lower = doc.pages[t.page_num - 1].text.lower() if 1 <= t.page_num <= len(doc.pages) else ""
        keyword_hits = sum(1 for kw in priority_keywords if kw in page_text_lower)
        phrase_hits = sum(1 for phrase in field_phrases if phrase and phrase in page_text_lower)
        term_hits = sum(1 for term in field_terms if term in page_text_lower)
        score = (
            (600 if t.page_num in priority_page_nums else 0)
            + keyword_hits * 200
            + phrase_hits * 160
            + min(term_hits, 10) * 50
            + t.row_count * 25
            + t.col_count * 15
        )
        table_candidates.append((score, t))
    table_candidates.sort(
        key=lambda item: (item[0], item[1].page_num, item[1].row_count * item[1].col_count),
        reverse=True,
    )

    table_parts: List[str] = []
    selected_table_pages: List[int] = []
    for _, t in table_candidates:
        if single_table_budget <= 0:
            break
        part = f"[Table - page {t.page_num}, {t.row_count}x{t.col_count}]\n{t.markdown}"
        clipped = part[: min(6_000, single_table_budget)]
        if not clipped:
            break
        table_parts.append(clipped)
        single_table_budget -= len(clipped)
        if t.page_num not in selected_table_pages:
            selected_table_pages.append(t.page_num)
    raw_single_tables = "\n\n".join(table_parts)[:_SINGLE_TABLE_BUDGET_CHARS] or doc.tables_markdown
    tables_markdown = await _maybe_compress_with_bear(raw_single_tables, doc.page_count, usage, f"{doc.filename} single tables")
    logger.info(
        "Single-record context for %s: priority_pages=%s selected_table_pages=%s",
        doc.filename,
        sorted(priority_page_nums),
        selected_table_pages,
    )
    reporting_unit = _detect_reporting_unit(doc) if doc.has_tables else None

    parts = [
        f"--- Document Info ---\n{ctx}",
        f"\n--- Fields to Extract ---\n{fblock}",
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
    rows = await _llm_extract(_SINGLE_SYSTEM, user_prompt, field_names, doc.filename, usage, _TEXT_MODEL)
    if len(rows) == 1:
        valid, reason = _single_record_valid(rows[0], field_names)
        if not valid:
            logger.info(
                "Single-record validation failed for %s: %s; retrying with stronger guidance",
                doc.filename,
                reason,
            )
            retry_prompt = "\n".join(parts) + "\n\n" + _SINGLE_RETRY_INSTRUCTION + '\n\nReturn exactly: {"records": [{"Field Name": "value", ...}]}'
            rows = await _llm_extract(_SINGLE_SYSTEM, retry_prompt, field_names, doc.filename, usage, _TEXT_MODEL)
            if len(rows) == 1:
                valid2, _ = _single_record_valid(rows[0], field_names)
                if not valid2:
                    logger.warning("Single-record retry still invalid for %s", doc.filename)
    if len(rows) == 1:
        gate_ok, fill_rate, missing_fields = _single_quality_gate(rows[0], field_names, _SINGLE_DOC_MIN_FFR)
        if not gate_ok and len(missing_fields) >= _SINGLE_DOC_RETRY_MIN_MISSING_FIELDS:
            logger.info(
                "Per-doc gate failed for %s (FFR=%.1f%%, missing=%d); running missing-fields retry",
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
                + "Fill only the listed missing fields from the provided document context. "
                + "Do not rewrite fields that already have values.\n\n"
                + f"--- Document Text ---\n{content_text}\n\n"
                + (f"--- Detected Tables ---\n{tables_markdown}\n\n" if tables_markdown else "")
                + 'Return exactly: {"records": [{"Field Name": "value", ...}]}'
            )
            retry_rows = await _llm_extract(
                _SINGLE_SYSTEM,
                retry_prompt,
                [f["name"] for f in retry_fields],
                doc.filename,
                usage,
                _TEXT_MODEL,
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
                    "Per-doc gate result for %s after retry: pass=%s FFR=%.1f%% missing=%d",
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
                        + "\n--- Document Text ---\n"
                        + await _maybe_compress_with_bear(
                            raw_single_text[:_SINGLE_FINAL_RETRY_TEXT_BUDGET_CHARS],
                            doc.page_count,
                            usage,
                            f"{doc.filename} final missing-fields text",
                        )
                        + "\n\n"
                        + (f"--- Detected Tables ---\n{tables_markdown}\n\n" if tables_markdown else "")
                        + 'Return exactly: {"records": [{"Field Name": "value", ...}]}'
                    )
                    final_retry_rows = await _llm_extract(
                        _SINGLE_SYSTEM,
                        final_retry_prompt,
                        [f["name"] for f in final_retry_fields],
                        doc.filename,
                        usage,
                        _TEXT_MODEL,
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
                            "Per-doc final retry result for %s: pass=%s FFR=%.1f%% missing=%d",
                            doc.filename,
                            gate_ok3,
                            fill_rate3 * 100,
                            len(missing3),
                        )
    if len(rows) == 1:
        rows = [await _cleanup_single_row_with_nano(rows[0], fields, doc.filename, usage)]
    return rows


async def extract_multi_record(
    doc: ParsedDocument,
    fields: List[Dict[str, str]],
    usage: LLMUsage,
    instructions: str = "",
) -> List[Dict[str, Any]]:
    field_names = [f["name"] for f in fields]
    ctx = _doc_context_block(doc)
    fblock = _fields_block(fields)
    content_text = await _maybe_compress_with_bear(doc.content_text, doc.page_count, usage, f"{doc.filename} multi text")

    table_parts, tbudget = [], 35_000
    for t in doc.tables:
        entry = f"[Table - page {t.page_num}, {t.row_count}x{t.col_count}]\n{t.markdown}"
        table_parts.append(entry[:3_000])
        tbudget -= len(entry)
        if tbudget <= 0:
            break
    full_tables_md = await _maybe_compress_with_bear("\n\n".join(table_parts), doc.page_count, usage, f"{doc.filename} multi tables")

    parts = [
        f"--- Document Info ---\n{ctx}",
        f"\n--- Fields to Extract (one object per repeated record) ---\n{fblock}",
    ]
    if instructions.strip():
        parts.append(f"\n--- User Instructions ---\n{instructions.strip()}")
    parts.append(
        "\n--- Extraction Mode ---\n"
        "The output should contain one object per natural repeated record that matches the "
        "requested fields. If the schema repeats across table rows, emit one object per row. "
        "If the schema repeats across table columns, emit one object per column. If the "
        "document does not actually contain repeated records that match the requested fields, "
        "return a single best record instead of inventing multiples.\n"
        "Do NOT output completely empty objects between real rows. For property or appraisal schedules, "
        "exactly one object per insured location; merge fragmented lines for the same location."
    )
    if full_tables_md:
        parts.append(f"\n--- Detected Tables ---\n{full_tables_md}")
    parts.append(f"\n--- Document Text ---\n{content_text}")

    user_prompt = "\n".join(parts) + '\n\nReturn: {"records": [{"Field": "value"}, ...]}'
    rows = await _llm_extract(_MULTI_SYSTEM, user_prompt, field_names, doc.filename, usage, _TEXT_MODEL)
    return await _review_multi_rows(rows, field_names, doc.filename, usage, "\n".join(parts), instructions, _TEXT_MODEL)


async def extract_multi_record_chunked(
    doc: ParsedDocument,
    fields: List[Dict[str, str]],
    usage: LLMUsage,
    instructions: str = "",
) -> List[Dict[str, Any]]:
    field_names = [f["name"] for f in fields]
    fblock = _fields_block(fields)
    inject_global_tables = document_has_wide_data_grid(doc)
    page_chunks = [doc.pages[i : i + _CHUNK_SIZE] for i in range(0, len(doc.pages), _CHUNK_SIZE)]

    async def _extract_chunk(chunk_pages: list) -> List[Dict[str, Any]]:
        page_nums = {p.page_num for p in chunk_pages}
        first_pg, last_pg = chunk_pages[0].page_num, chunk_pages[-1].page_num
        chunk_text = "\n\n".join(f"=== Page {p.page_num} ===\n{p.text}" for p in chunk_pages)[:22_000]
        if inject_global_tables and doc.tables:
            table_parts: List[str] = []
            tbudget = 20_000
            for t in doc.tables:
                if tbudget <= 0:
                    break
                entry = f"[Table - page {t.page_num}, {t.row_count}x{t.col_count}]\n{t.markdown}"
                clipped = entry[: min(10_000, tbudget)]
                if clipped:
                    table_parts.append(clipped)
                    tbudget -= len(clipped)
            tables_md = "\n\n".join(table_parts)[:20_000]
            tables_scope = "all detected tables in this file (master schedule may be on another page range)"
        else:
            tables_md = "\n\n".join(
                f"[Table - page {t.page_num}, {t.row_count}x{t.col_count}]\n{t.markdown}"
                for t in doc.tables if t.page_num in page_nums
            )[:14_000]
            tables_scope = f"pages {first_pg}-{last_pg}"
        chunk_text = await _maybe_compress_with_bear(chunk_text, doc.page_count, usage, f"{doc.filename} chunk {first_pg}-{last_pg} text")
        tables_md = await _maybe_compress_with_bear(tables_md, doc.page_count, usage, f"{doc.filename} chunk {first_pg}-{last_pg} tables")

        parts = [
            f"--- Document Info ---\n"
            f"Filename: {doc.filename}\nTotal pages: {doc.page_count}\n"
            f"Extracting: pages {first_pg}-{last_pg}",
            f"\n--- Fields (one object per repeated record) ---\n{fblock}",
        ]
        if instructions.strip():
            parts.append(f"\n--- User Instructions ---\n{instructions.strip()}")
        if inject_global_tables:
            parts.append(
                "\n--- Schedule priority ---\n"
                "If Tables include a master schedule of values, property schedule, or location listing with monetary "
                "columns (building, BPP/contents, business income, TIV), emit one output record per location row from "
                "that schedule and copy every monetary value from that row. Use the Text on these pages only to fill "
                "fields the schedule omits (e.g. construction class, occupancy, protection class). "
                "Do not use replacement-cost component subtotals from a narrative appraisal page as the schedule "
                "Building value when the master row already lists building/BPP/BI/TIV for that location.\n"
            )
        if tables_md:
            parts.append(f"\n--- Tables ({tables_scope}) ---\n{tables_md}")
        parts.append(f"\n--- Text (pages {first_pg}-{last_pg}) ---\n{chunk_text}")

        prompt = (
            "\n".join(parts)
            + "\n\nExtract ALL repeated records on these pages only. "
            + 'Return: {"records": [...]}. No records here -> {"records": []}.'
        )
        return await _llm_extract(_MULTI_SYSTEM, prompt, field_names, doc.filename, usage, _TEXT_MODEL)

    chunk_results = await asyncio.gather(*[_extract_chunk(c) for c in page_chunks])
    all_rows: List[Dict[str, Any]] = []
    for rows in chunk_results:
        all_rows.extend(r for r in rows if any(r.get(fn) for fn in field_names))

    if not all_rows:
        return _empty([doc.filename], field_names)
    return await _review_multi_rows(all_rows, field_names, doc.filename, usage, doc.content_text, instructions, _TEXT_MODEL)


_MULTI_MAX_TOKENS = 16_384


async def _build_multi_doc_context(
    doc: ParsedDocument,
    usage: LLMUsage,
    label: str = "multi",
) -> tuple[str, str]:
    content_text = await _maybe_compress_with_bear(
        doc.content_text, doc.page_count, usage, f"{doc.filename} {label} text",
    )
    table_parts, tbudget = [], 35_000
    for t in doc.tables:
        entry = f"[Table - page {t.page_num}, {t.row_count}x{t.col_count}]\n{t.markdown}"
        table_parts.append(entry[:3_000])
        tbudget -= len(entry)
        if tbudget <= 0:
            break
    full_tables_md = await _maybe_compress_with_bear(
        "\n\n".join(table_parts), doc.page_count, usage, f"{doc.filename} {label} tables",
    )
    return content_text, full_tables_md


def _build_multi_cacheable_prefix(
    fblock: str,
    ctx: str,
    instructions: str,
    full_tables_md: str,
    content_text: str,
) -> str:
    """Build the prompt prefix with static content first for maximum cache hits.

    Order: fields -> instructions -> mode -> doc info -> tables -> text
    The trailing action instruction is appended by the caller and is the only
    part that changes between the initial call and a validation retry, so the
    entire prefix is an exact match for OpenAI prompt caching.
    """
    parts = [
        f"--- Fields to Extract (one object per repeated record) ---\n{fblock}",
    ]
    if instructions.strip():
        parts.append(f"\n--- User Instructions ---\n{instructions.strip()}")
    parts.append(
        "\n--- Extraction Mode ---\n"
        "The output should contain one object per natural repeated record that matches the "
        "requested fields. If the schema repeats across table rows, emit one object per row. "
        "If the schema repeats across table columns, emit one object per column. If the "
        "document does not actually contain repeated records that match the requested fields, "
        "return a single best record instead of inventing multiples.\n"
        "Do NOT output completely empty objects between real rows. For property or appraisal schedules, "
        "exactly one object per insured location; merge fragmented lines for the same location."
    )
    parts.append(f"\n--- Document Info ---\n{ctx}")
    if full_tables_md:
        parts.append(f"\n--- Detected Tables ---\n{full_tables_md}")
    parts.append(f"\n--- Document Text ---\n{content_text}")
    return "\n".join(parts)


async def extract_multi_record_validated(
    doc: ParsedDocument,
    fields: List[Dict[str, str]],
    usage: LLMUsage,
    instructions: str = "",
) -> List[Dict[str, Any]]:
    field_names = [f["name"] for f in fields]
    ctx = _doc_context_block(doc)
    fblock = _fields_block(fields)
    content_text, full_tables_md = await _build_multi_doc_context(doc, usage)

    cacheable_prefix = _build_multi_cacheable_prefix(
        fblock, ctx, instructions, full_tables_md, content_text,
    )

    metadata_context = f"{content_text}\n\n{full_tables_md}" if full_tables_md else content_text
    expected_count = await _extract_record_count_metadata(
        metadata_context, fblock, doc.filename, usage, instructions,
    )

    user_prompt = (
        cacheable_prefix
        + '\n\nExtract ALL records. Return: {"records": [{"Field": "value"}, ...]}'
    )
    rows = await _llm_extract(
        _MULTI_SYSTEM, user_prompt, field_names, doc.filename, usage,
        _TEXT_MODEL, max_tokens=_MULTI_MAX_TOKENS,
    )
    rows = await _review_multi_rows(
        rows, field_names, doc.filename, usage, cacheable_prefix, instructions, _TEXT_MODEL,
    )

    if expected_count is not None and len(rows) != expected_count:
        logger.info(
            "Row count validation failed for %s: extracted=%d expected=%d; retrying with count hint",
            doc.filename, len(rows), expected_count,
        )
        retry_prompt = (
            cacheable_prefix
            + f"\n\nIMPORTANT: This document contains exactly {expected_count} data records. "
            f"You previously returned {len(rows)} — extract ALL {expected_count} records. "
            f"Do not skip any. Do not include subtotals or headers as records.\n"
            'Return: {"records": [{"Field": "value"}, ...]}'
        )
        retry_rows = await _llm_extract(
            _MULTI_SYSTEM, retry_prompt, field_names, doc.filename, usage,
            _TEXT_MODEL, max_tokens=_MULTI_MAX_TOKENS,
        )
        retry_rows = await _review_multi_rows(
            retry_rows, field_names, doc.filename, usage, cacheable_prefix, instructions, _TEXT_MODEL,
        )

        if abs(len(retry_rows) - expected_count) < abs(len(rows) - expected_count):
            logger.info(
                "Retry improved count for %s: %d -> %d (expected %d)",
                doc.filename, len(rows), len(retry_rows), expected_count,
            )
            rows = retry_rows
        else:
            logger.info(
                "Retry did not improve count for %s: kept %d (retry had %d, expected %d)",
                doc.filename, len(rows), len(retry_rows), expected_count,
            )
    elif expected_count is not None:
        logger.info(
            "Row count validation passed for %s: %d records match expected",
            doc.filename, len(rows),
        )

    return rows


async def extract_multi_record_chunked_validated(
    doc: ParsedDocument,
    fields: List[Dict[str, str]],
    usage: LLMUsage,
    instructions: str = "",
) -> List[Dict[str, Any]]:
    field_names = [f["name"] for f in fields]
    fblock = _fields_block(fields)

    metadata_context = doc.content_text[:20_000]
    if doc.tables_markdown:
        metadata_context += "\n\n" + doc.tables_markdown[:10_000]
    expected_count = await _extract_record_count_metadata(
        metadata_context, fblock, doc.filename, usage, instructions,
    )

    rows = await extract_multi_record_chunked(doc, fields, usage, instructions)

    if expected_count is not None and len(rows) != expected_count:
        logger.info(
            "Chunked row count validation failed for %s: extracted=%d expected=%d; retrying full-doc",
            doc.filename, len(rows), expected_count,
        )
        ctx = _doc_context_block(doc)
        content_text, full_tables_md = await _build_multi_doc_context(doc, usage, "multi retry")

        cacheable_prefix = _build_multi_cacheable_prefix(
            fblock, ctx, instructions, full_tables_md, content_text,
        )
        retry_prompt = (
            cacheable_prefix
            + f"\n\nIMPORTANT: This document contains exactly {expected_count} data records. "
            f"Extract ALL {expected_count} records. Do not skip any. "
            f"Do not include subtotals or headers as records.\n"
            'Return: {"records": [{"Field": "value"}, ...]}'
        )
        retry_rows = await _llm_extract(
            _MULTI_SYSTEM, retry_prompt, field_names, doc.filename, usage,
            _TEXT_MODEL, max_tokens=_MULTI_MAX_TOKENS,
        )
        retry_rows = await _review_multi_rows(
            retry_rows, field_names, doc.filename, usage, cacheable_prefix, instructions, _TEXT_MODEL,
        )

        if abs(len(retry_rows) - expected_count) < abs(len(rows) - expected_count):
            logger.info(
                "Chunked retry improved count for %s: %d -> %d (expected %d)",
                doc.filename, len(rows), len(retry_rows), expected_count,
            )
            rows = retry_rows
        else:
            logger.info(
                "Chunked retry did not improve count for %s: kept %d (retry had %d, expected %d)",
                doc.filename, len(rows), len(retry_rows), expected_count,
            )
    elif expected_count is not None:
        logger.info(
            "Chunked row count validation passed for %s: %d records match expected",
            doc.filename, len(rows),
        )

    return rows


def _should_extract_multi(doc: ParsedDocument, fields: List[Dict[str, str]]) -> bool:
    del fields
    if not doc.has_tables:
        return False
    data_tables = [t for t in doc.tables if t.row_count >= 4 and t.col_count >= 2]
    return len(data_tables) >= 1


_PER_PAGE_CONCURRENCY = 4


async def extract_per_page(
    doc: ParsedDocument,
    fields: List[Dict[str, str]],
    usage: LLMUsage,
    instructions: str = "",
) -> List[Dict[str, Any]]:
    """Split document page-by-page, extract a single record from each page concurrently."""
    field_names = [f["name"] for f in fields]
    fblock = _fields_block(fields)
    semaphore = asyncio.Semaphore(_PER_PAGE_CONCURRENCY)

    async def _extract_page(page: ParsedPage) -> List[Dict[str, Any]]:
        async with semaphore:
            page_text = f"=== Page {page.page_num} ===\n{page.text}"
            tables_md = "\n\n".join(
                f"[Table - page {t.page_num}, {t.row_count}x{t.col_count}]\n{t.markdown}"
                for t in page.tables
            )
            parts = [
                f"--- Document Info ---\n"
                f"Filename: {doc.filename}\nTotal pages: {doc.page_count}\n"
                f"Extracting from: page {page.page_num}",
                f"\n--- Fields to Extract ---\n{fblock}",
            ]
            if instructions.strip():
                parts.append(f"\n--- User Instructions ---\n{instructions.strip()}")
            parts.append(f"\n--- Document Text ---\n{page_text}")
            if tables_md:
                parts.append(f"\n--- Detected Tables ---\n{tables_md}")
            parts.append(
                "\n--- Extraction Mode ---\n"
                "This page is one of many independent records in a compiled PDF. "
                "Extract the single record on this page. If the page has no relevant "
                'data for the requested fields, return: {"records": []}.'
            )
            prompt = "\n".join(parts) + '\n\nReturn exactly: {"records": [{"Field Name": "value", ...}]}'
            return await _llm_extract(_SINGLE_SYSTEM, prompt, field_names, doc.filename, usage, _TEXT_MODEL)

    page_results = await asyncio.gather(*[_extract_page(p) for p in doc.pages])

    all_rows: List[Dict[str, Any]] = []
    empty_markers = {"", "n/a", "na", "none", "null", "-", "—"}
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
        "Per-page extraction for %s: %d pages -> %d non-empty records",
        doc.filename, doc.page_count, len(all_rows),
    )
    return all_rows if all_rows else _empty([doc.filename], field_names)
