from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass
from typing import Any, Dict, List

import litellm

from app.config import settings
from app.services.ocr_service import run_mistral_ocr
from app.services.pdf_service import ParsedDocument
from app.services.extraction.core import (
    _EMPTY_VALUES,
    _empty,
    _error,
    _fields_block,
    _maybe_compress_with_bear,
    _normalise_rows,
    _system_with_date,
    build_table_column_hint,
    LLMUsage,
    record_llm_usage_cost,
)

logger = logging.getLogger(__name__)

_WORD_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9/&().,#:%-]*")
_SECTION_SELECTOR_MAX_TOKENS = 1_200
_SOV_EXTRACT_MAX_TOKENS = 12_000


@dataclass
class SOVSection:
    index: int
    page_num: int
    header: str
    preview: str
    content: str


def _first_words(text: str, limit: int = 50) -> str:
    words = _WORD_RE.findall(text)
    return " ".join(words[:limit]).strip()


def _build_sections_from_ocr_pages(ocr_pages: list[Any]) -> list[SOVSection]:
    sections: list[SOVSection] = []
    for index, page in enumerate(ocr_pages, start=1):
        header = str(getattr(page, "header", "") or "").strip()
        body = str(getattr(page, "markdown", "") or "").strip()
        tables_markdown = str(getattr(page, "tables_markdown", "") or "").strip()
        footer = str(getattr(page, "footer", "") or "").strip()
        content_parts = [f"=== Page {page.page_num} ==="]
        if header:
            content_parts.append(f"--- Header ---\n{header}")
        if body:
            content_parts.append(body)
        if tables_markdown:
            content_parts.append(f"--- Tables ---\n{tables_markdown}")
        if footer:
            content_parts.append(f"--- Footer ---\n{footer}")
        preview = _first_words(" ".join(part for part in (header, body, tables_markdown, footer) if part))
        sections.append(
            SOVSection(
                index=index,
                page_num=page.page_num,
                header=header,
                preview=preview,
                content="\n".join(content_parts).strip(),
            )
        )
    return sections


def _parse_json_content(content: Any) -> dict[str, Any]:
    if isinstance(content, list):
        content = "".join(str(part) for part in content)
    if not isinstance(content, str):
        return {}
    cleaned = content.strip()
    if "```json" in cleaned:
        cleaned = cleaned.split("```json", 1)[1].split("```", 1)[0].strip()
    elif "```" in cleaned:
        cleaned = cleaned.split("```", 1)[1].split("```", 1)[0].strip()
    return json.loads(cleaned)


async def _acompletion(
    model: str,
    messages: list[dict[str, str]],
    usage: LLMUsage,
    max_tokens: int,
) -> dict[str, Any]:
    kwargs: dict[str, Any] = {
        "model": model,
        "messages": messages,
        "temperature": 0,
        "max_tokens": max_tokens,
        "response_format": {"type": "json_object"},
    }
    if "/" not in model and settings.openai_api_key:
        kwargs["api_key"] = settings.openai_api_key

    last_exc: Exception | None = None
    for with_response_format in (True, False):
        try:
            if not with_response_format:
                kwargs.pop("response_format", None)
            resp = await litellm.acompletion(**kwargs)
            if resp.usage:
                usage.add(resp.usage.prompt_tokens, resp.usage.completion_tokens)
            record_llm_usage_cost(usage, resp)
            return _parse_json_content(resp.choices[0].message.content)
        except Exception as exc:
            last_exc = exc

    raise last_exc or RuntimeError("LLM call failed")


async def _select_sections(
    doc: ParsedDocument,
    fields: List[Dict[str, str]],
    sections: list[SOVSection],
    usage: LLMUsage,
    instructions: str = "",
) -> list[SOVSection]:
    if not sections:
        return []

    section_payload = [
        {
            "index": section.index,
            "page": section.page_num,
            "header": section.header,
            "first_50_words": section.preview,
        }
        for section in sections
    ]
    selector_prompt = (
        "Pick only the OCR pages worth keeping for insurance schedule extraction.\n\n"
        "Keep pages that are likely to contain:\n"
        "- statement of values / schedule of values / location or premises schedules\n"
        "- property schedules, appraisal summaries, site listings, building value tables\n"
        "- vehicle schedules, auto schedules, employee or payroll schedules when they appear as repeated rows\n"
        "- underwriting notes that can fill row-level gaps such as occupancy, construction, protection, sprinklers, valuation, year built\n\n"
        "Drop pages like cover pages, table of contents, letters, signatures, policy wording, forms, endorsements, disclaimers, claims language, and generic narrative that does not help fill repeated schedule rows.\n\n"
        "Use only the provided OCR headers from Mistral. Do not invent or assume extra headers.\n\n"
        f"Filename: {doc.filename}\n"
        f"Requested fields:\n{_fields_block(fields)}\n\n"
        + (f"User instructions:\n{instructions.strip()}\n\n" if instructions.strip() else "")
        + f"Candidate OCR pages:\n{json.dumps(section_payload, ensure_ascii=True)}\n\n"
        'Return exactly: {"keep_indices": [<page index>, ...]}'
    )

    keep_indices: set[int] = set()
    try:
        raw = await _acompletion(
            settings.sov_section_selector_model,
            [{"role": "user", "content": selector_prompt}],
            usage,
            _SECTION_SELECTOR_MAX_TOKENS,
        )
        keep_indices = {
            int(idx)
            for idx in raw.get("keep_indices", [])
            if isinstance(idx, int) or (isinstance(idx, str) and idx.isdigit())
        }
    except Exception as exc:
        logger.warning("SOV section selector failed for %s: %s", doc.filename, exc)

    selected = [section for section in sections if section.index in keep_indices]
    if not selected:
        selected = sections

    logger.info(
        "SOV selector kept %d/%d OCR pages for %s",
        len(selected),
        len(sections),
        doc.filename,
    )
    return selected


def _selected_tables_markdown(doc: ParsedDocument, kept_pages: set[int]) -> str:
    tables = [table for table in doc.tables if table.page_num in kept_pages]
    if not tables:
        tables = doc.tables
    return "\n\n".join(
        f"[Table - page {table.page_num}, {table.row_count}x{table.col_count}]\n{table.markdown}"
        for table in tables
    )


def _selected_tables(doc: ParsedDocument, kept_pages: set[int]) -> list:
    tables = [table for table in doc.tables if table.page_num in kept_pages]
    return tables or doc.tables


def _estimate_expected_rows(doc: ParsedDocument, kept_pages: set[int]) -> int | None:
    row_counts = [
        max(0, table.row_count - 1)
        for table in doc.tables
        if table.page_num in kept_pages and table.row_count >= 4 and table.col_count >= 3
    ]
    if not row_counts:
        row_counts = [
            max(0, table.row_count - 1)
            for table in doc.tables
            if table.row_count >= 4 and table.col_count >= 3
        ]
    return max(row_counts) if row_counts else None


def _filled_cell_count(rows: List[Dict[str, Any]], field_names: list[str]) -> int:
    return sum(
        1
        for row in rows
        if not row.get("_error")
        for field_name in field_names
        if row.get(field_name) is not None
        and str(row[field_name]).strip().lower() not in _EMPTY_VALUES
    )


def _row_score(
    rows: List[Dict[str, Any]],
    field_names: list[str],
    expected_rows: int | None,
) -> tuple[float, int, int]:
    real_rows = [row for row in rows if not row.get("_error")]
    filled = _filled_cell_count(real_rows, field_names)
    total_cells = max(1, len(real_rows) * max(1, len(field_names)))
    fill_rate = filled / total_cells
    count_delta = abs(len(real_rows) - expected_rows) if expected_rows else 0
    error_count = sum(1 for row in rows if row.get("_error"))
    return (error_count + count_delta - fill_rate, filled, len(real_rows))


async def _extract_rows(
    doc: ParsedDocument,
    fields: List[Dict[str, str]],
    trimmed_text: str,
    selected_headers: str,
    tables_markdown: str,
    table_hint: str,
    usage: LLMUsage,
    instructions: str = "",
    retry_note: str = "",
) -> List[Dict[str, Any]]:
    field_names = [field["name"] for field in fields]
    prompt_parts = [
        f"--- Document Info ---\nFilename: {doc.filename}\nTotal pages: {doc.page_count}\nPipeline: Dedicated SOV extraction",
        f"\n--- Fields to Extract ---\n{_fields_block(fields)}",
        f"\n--- Kept OCR Pages ---\n{selected_headers}",
    ]
    if instructions.strip():
        prompt_parts.append(f"\n--- User Instructions ---\n{instructions.strip()}")
    if retry_note:
        prompt_parts.append(f"\n--- Retry Guidance ---\n{retry_note}")
    if table_hint:
        prompt_parts.append(f"\n{table_hint}")
    if tables_markdown:
        prompt_parts.append(f"\n--- Parsed Tables From Kept Pages ---\n{tables_markdown}")
    prompt_parts.append(f"\n--- Trimmed OCR Text ---\n{trimmed_text}")
    prompt_parts.append(
        "\n--- Extraction Rules ---\n"
        "Return one object per real repeated schedule row.\n"
        "Prefer master schedules and structured tables over narrative duplicates.\n"
        "Merge detail from the kept OCR pages into the correct row only when the location/entity match is clear.\n"
        "Never emit headers, subtotals, totals, or blank rows.\n"
        "Use null when a field is genuinely absent.\n"
        "Return spreadsheet-ready scalar values only.\n"
        'Return exactly: {"records": [{"Field": "value"}, ...]}'
    )

    system_prompt = (
        "You extract statement-of-values style schedules from trimmed OCR context.\n"
        "Focus on repeated rows for insured locations, premises, vehicles, or employees.\n"
        "Return valid JSON only."
    )
    try:
        raw = await _acompletion(
            settings.sov_extraction_model,
            [
                {"role": "system", "content": _system_with_date(system_prompt)},
                {"role": "user", "content": "\n".join(prompt_parts)},
            ],
            usage,
            _SOV_EXTRACT_MAX_TOKENS,
        )
        rows = _normalise_rows(raw, field_names, doc.filename)
        return rows if rows else _empty([doc.filename], field_names)
    except Exception as exc:
        logger.error("Dedicated SOV extraction failed for %s: %s", doc.filename, exc)
        return _error([doc.filename], field_names, str(exc))


async def extract_sov_from_document(
    doc: ParsedDocument,
    fields: List[Dict[str, str]],
    usage: LLMUsage,
    instructions: str = "",
) -> List[Dict[str, Any]]:
    field_names = [field["name"] for field in fields]
    filename_lower = doc.filename.lower()
    skip_trimming = doc.page_count < 15 or filename_lower.endswith((".xlsx", ".xls", ".xlsm", ".csv"))

    if not settings.mistral_api_key or not doc.file_path:
        logger.warning(
            "SOV pipeline fallback for %s: missing Mistral OCR configuration or file path",
            doc.filename,
        )
        fallback_text = doc.content_text or "\n\n".join(
            f"=== Page {page.page_num} ===\n{page.text}" for page in doc.pages
        )
        kept_pages = {page.page_num for page in doc.pages} or set(range(1, doc.page_count + 1))
        selected_tables = doc.tables
        trimmed_text = fallback_text
        selected_headers = (
            "- full document kept\n"
            "- Mistral OCR headers unavailable, so no page trimming was attempted"
        )

        tables_markdown = _selected_tables_markdown(doc, kept_pages)
        trimmed_text = await _maybe_compress_with_bear(
            trimmed_text,
            doc.page_count,
            usage,
            f"{doc.filename} SOV trimmed text",
        )
        return await _extract_rows(
            doc,
            fields,
            trimmed_text,
            selected_headers,
            tables_markdown,
            build_table_column_hint(selected_tables),
            usage,
            instructions,
        )

    try:
        ocr_result = await run_mistral_ocr(doc.file_path, settings.mistral_api_key)
        usage.add_ocr_cost(ocr_result.cost_usd)
        logger.info(
            "Dedicated SOV OCR complete for %s: %d pages, %d chars, $%.4f",
            doc.filename,
            ocr_result.page_count,
            len(ocr_result.text),
            ocr_result.cost_usd,
        )
    except Exception as exc:
        msg = f"SOV OCR failed: {exc}"
        logger.error("Dedicated SOV OCR failed for %s: %s", doc.filename, exc)
        return _error([doc.filename], field_names, msg)

    all_ocr_pages = ocr_result.pages
    all_page_nums = {page.page_num for page in all_ocr_pages} or {page.page_num for page in doc.pages} or set(range(1, doc.page_count + 1))
    if skip_trimming:
        kept_pages = all_page_nums
        selected_tables = doc.tables
        trimmed_text = ocr_result.text
        selected_headers = (
            "- full document kept\n"
            f"- trimming skipped because page_count={doc.page_count}"
            + (" or spreadsheet-like input was detected" if filename_lower.endswith((".xlsx", ".xls", ".xlsm", ".csv")) else "")
        )
        logger.info("SOV trimming skipped for %s", doc.filename)
    else:
        sections = _build_sections_from_ocr_pages(all_ocr_pages)
        selected_sections = await _select_sections(doc, fields, sections, usage, instructions)
        kept_pages = {section.page_num for section in selected_sections}
        selected_tables = _selected_tables(doc, kept_pages)
        trimmed_text = "\n\n".join(section.content for section in selected_sections).strip()
        if not trimmed_text:
            trimmed_text = ocr_result.text
            kept_pages = all_page_nums

        selected_headers = "\n".join(
            f"- page {section.page_num}: header={json.dumps(section.header or '', ensure_ascii=True)} — {section.preview}"
            for section in selected_sections
        ) or "- no OCR headers were returned; kept pages were selected by page preview only"

    trimmed_text = await _maybe_compress_with_bear(
        trimmed_text,
        doc.page_count,
        usage,
        f"{doc.filename} SOV trimmed text",
    )
    tables_markdown = await _maybe_compress_with_bear(
        _selected_tables_markdown(doc, kept_pages),
        doc.page_count,
        usage,
        f"{doc.filename} SOV kept tables",
    )
    table_hint = build_table_column_hint(selected_tables)
    expected_rows = _estimate_expected_rows(doc, kept_pages)

    rows = await _extract_rows(
        doc,
        fields,
        trimmed_text,
        selected_headers,
        tables_markdown,
        table_hint,
        usage,
        instructions,
    )

    real_rows = [row for row in rows if not row.get("_error")]
    total_cells = max(1, len(real_rows) * max(1, len(field_names)))
    fill_rate = _filled_cell_count(real_rows, field_names) / total_cells
    should_retry = bool(rows and any(row.get("_error") for row in rows))
    if expected_rows and len(real_rows) < expected_rows:
        should_retry = True
    if real_rows and fill_rate < 0.65:
        should_retry = True

    if should_retry:
        retry_note = (
            f"The first pass likely missed content. Extracted {len(real_rows)} rows"
            + (f" while the kept tables suggest about {expected_rows} rows." if expected_rows else ".")
            + f" Current field fill rate is {fill_rate:.0%}. Re-read every kept OCR page and return the fullest complete records you can. This is the only retry."
        )
        retry_rows = await _extract_rows(
            doc,
            fields,
            trimmed_text,
            selected_headers,
            tables_markdown,
            table_hint,
            usage,
            instructions,
            retry_note=retry_note,
        )
        if _row_score(retry_rows, field_names, expected_rows) < _row_score(rows, field_names, expected_rows):
            rows = retry_rows

    return rows if rows else _empty([doc.filename], field_names)
