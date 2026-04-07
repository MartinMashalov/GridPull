from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass
from typing import Any, Dict, List

from app.config import settings
from app.services.llm_router import routed_acompletion
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
_SOV_LITEPARSE_THRESHOLD_PAGES = 0   # always OCR — LiteParse silently drops table rows
_SOV_OCR_MAX_PAGES = 50          # cap at 50 pages; end of long SOVs is usually exceptions/appendices
_TRAILING_COMMA_RE = re.compile(r",\s*([}\]])")
# Max rows to attempt in a single LLM pass (output token budget constraint)
# 32K output tokens / ~650 tokens per row (46 fields) ≈ 50 rows safe limit
_MAX_ROWS_PER_PASS = 50


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


def _content_to_text(content: Any) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for part in content:
            if isinstance(part, str):
                parts.append(part)
                continue
            if isinstance(part, dict):
                text = part.get("text")
                if isinstance(text, str):
                    parts.append(text)
                    continue
            text = getattr(part, "text", None)
            if isinstance(text, str):
                parts.append(text)
        return "".join(parts)
    return ""


def _extract_json_object_fragment(text: str) -> str | None:
    start = text.find("{")
    while start >= 0:
        depth = 0
        in_string = False
        escape = False
        for idx in range(start, len(text)):
            ch = text[idx]
            if in_string:
                if escape:
                    escape = False
                elif ch == "\\":
                    escape = True
                elif ch == '"':
                    in_string = False
                continue
            if ch == '"':
                in_string = True
                continue
            if ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    return text[start : idx + 1]
        start = text.find("{", start + 1)
    return None


def _parse_json_content(content: Any) -> dict[str, Any]:
    cleaned = _content_to_text(content).strip()
    if not cleaned:
        return {}

    candidates = [cleaned]
    for block in re.findall(r"```(?:json)?\s*(.*?)```", cleaned, flags=re.DOTALL | re.IGNORECASE):
        stripped = block.strip()
        if stripped:
            candidates.append(stripped)
    fragment = _extract_json_object_fragment(cleaned)
    if fragment:
        candidates.append(fragment)

    decoder = json.JSONDecoder()
    last_exc: json.JSONDecodeError | None = None
    seen: set[str] = set()

    for candidate in candidates:
        if candidate in seen:
            continue
        seen.add(candidate)
        for variant in (candidate, _TRAILING_COMMA_RE.sub(r"\1", candidate)):
            if not variant:
                continue
            try:
                parsed = json.loads(variant)
            except json.JSONDecodeError as exc:
                last_exc = exc
                try:
                    parsed, _ = decoder.raw_decode(variant)
                except json.JSONDecodeError as raw_exc:
                    last_exc = raw_exc
                    continue
            if isinstance(parsed, dict):
                return parsed

    raise last_exc or json.JSONDecodeError("No JSON object found", cleaned, 0)


async def _acompletion(
    model: str,
    messages: list[dict[str, str]],
    usage: LLMUsage,
    max_tokens: int,
) -> dict[str, Any]:
    backup = settings.sov_backup_model
    models_to_try = [model]
    if backup and backup != model:
        models_to_try.append(backup)

    last_exc: Exception | None = None
    for try_model in models_to_try:
        kwargs: dict[str, Any] = {
            "model": try_model,
            "messages": messages,
            "temperature": 0,
            "max_tokens": max_tokens,
            "response_format": {"type": "json_object"},
        }
        for with_response_format in (True, False):
            for attempt in range(2):
                try:
                    call_kwargs = dict(kwargs)
                    if not with_response_format:
                        call_kwargs.pop("response_format", None)
                    resp = await routed_acompletion(route_profile="extraction", **call_kwargs)
                    if resp.usage:
                        usage.add(resp.usage.prompt_tokens, resp.usage.completion_tokens)
                    record_llm_usage_cost(usage, resp)
                    return _parse_json_content(resp.choices[0].message.content)
                except json.JSONDecodeError as exc:
                    last_exc = exc
                    if attempt == 0:
                        logger.warning(
                            "SOV model %s returned malformed JSON; retrying once (%s response_format)",
                            try_model,
                            "with" if with_response_format else "without",
                        )
                        continue
                except Exception as exc:
                    last_exc = exc
                    if try_model != models_to_try[-1]:
                        logger.warning("SOV model %s failed, trying backup %s: %s", try_model, models_to_try[-1], exc)
                    break

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
        "Pick only the OCR pages worth keeping for repeated-record schedule extraction.\n\n"
        "Keep pages that are likely to contain:\n"
        "- primary data tables with repeated rows matching the requested fields\n"
        "- schedules, listings, or summaries where each row represents one entity (location, vehicle, person, item, etc.)\n"
        "- supplementary notes or detail sections that can fill field gaps for entities already in the schedule\n\n"
        "Drop pages that clearly contain no relevant data: cover pages, table of contents, signature pages, "
        "boilerplate forms, and generic narrative that does not help fill schedule rows.\n\n"
        "Use only the provided OCR headers from Mistral. Do not invent or assume extra headers.\n\n"
        f"Filename: {doc.filename}\n"
        f"Requested fields:\n{_fields_block(fields)}\n\n"
        + (f"User instructions:\n{instructions.strip()}\n\n" if instructions.strip() else "")
        + f"Candidate OCR pages:\n{json.dumps(section_payload, ensure_ascii=True)}\n\n"
        'Return a JSON object with exactly this structure: {"keep_indices": [<page index>, ...]}'
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


def _table_header_signature(markdown: str) -> tuple[str, ...]:
    header_lines: list[str] = []
    for line in markdown.split("\n"):
        if re.match(r"^\|\s*-", line):
            break
        header_lines.append(line)
    header_text = " ".join(header_lines).lower()
    return tuple(
        token
        for token in (
            re.sub(r"[^a-z0-9]+", "", cell)
            for cell in header_text.split("|")
        )
        if token and token != "---"
    )


def _expected_rows_from_text(text: str) -> int | None:
    """Extract an explicit row count stated anywhere in the document text.

    Patterns are intentionally generic — they match any 'total N <things>'
    or 'N <thing> X of Y' phrasing so the function works across document
    types without domain-specific keyword lists.
    """
    if not text:
        return None
    patterns = (
        # "Total: 22" / "Total 22" at a table footer
        r"\btotal\s*[:#-]?\s*(\d{1,4})\b",
        # "22 of 22" / "record 3 of 15"
        r"\b\d+\s+of\s+(\d{1,4})\b",
        # "Schedule of 15 ..." / "List of 8 ..."
        r"\b(?:schedule|list|index)\s+of\s+(\d{1,4})\b",
    )
    best: int | None = None
    for pattern in patterns:
        for match in re.finditer(pattern, text, flags=re.IGNORECASE):
            try:
                value = int(match.group(1))
            except (TypeError, ValueError):
                continue
            if 1 < value <= 9999:
                if best is None or value > best:
                    best = value
    return best


def _estimate_expected_rows(doc: ParsedDocument, kept_pages: set[int]) -> int | None:
    selected_pages = [page for page in doc.pages if page.page_num in kept_pages] or doc.pages
    selected_text = "\n".join(page.text for page in selected_pages)
    explicit_count = _expected_rows_from_text(selected_text or doc.content_text)
    if explicit_count:
        return explicit_count

    candidate_tables = [
        table
        for table in doc.tables
        if table.page_num in kept_pages and table.row_count >= 4 and table.col_count >= 3
    ]
    if not candidate_tables:
        candidate_tables = [
            table
            for table in doc.tables
            if table.row_count >= 4 and table.col_count >= 3
        ]
    if not candidate_tables:
        return None

    multi_page_schedule_counts: list[int] = []
    grouped_tables: dict[tuple[str, ...], list] = {}
    for table in candidate_tables:
        signature = _table_header_signature(table.markdown)
        if not signature:
            continue
        grouped_tables.setdefault(signature, []).append(table)
    for tables in grouped_tables.values():
        if len(tables) < 2 or min(table.col_count for table in tables) < 8:
            continue
        multi_page_schedule_counts.append(sum(max(0, table.row_count - 1) for table in tables))

    if multi_page_schedule_counts:
        return max(multi_page_schedule_counts)

    row_counts = [max(0, table.row_count - 1) for table in candidate_tables]
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


def _sov_extract_token_budget(field_count: int, expected_rows: int | None) -> int:
    row_target = max(expected_rows or 8, 8)
    estimated = 2_000 + field_count * row_target * 18
    return min(32_768, max(_SOV_EXTRACT_MAX_TOKENS, estimated))




async def _extract_rows(
    doc: ParsedDocument,
    fields: List[Dict[str, str]],
    trimmed_text: str,
    selected_headers: str,
    tables_markdown: str,
    table_hint: str,
    usage: LLMUsage,
    expected_rows: int | None,
    instructions: str = "",
    retry_note: str = "",
) -> List[Dict[str, Any]]:
    field_names = [field["name"] for field in fields]
    prompt_parts = [
        f"--- Document Info ---\nFilename: {doc.filename}\nTotal pages: {doc.page_count}\nPipeline: Dedicated SOV extraction",
        f"\n--- Fields to Extract ---\n{_fields_block(fields)}",
        f"\n--- Selected Source Context ---\n{selected_headers}",
    ]
    if expected_rows:
        prompt_parts.append(
            f"\n--- Expected Row Count ---\nThe document likely contains about {expected_rows} real schedule rows. Return all of them unless a row is clearly a header, total, or blank spacer."
        )
    if instructions.strip():
        prompt_parts.append(f"\n--- User Instructions ---\n{instructions.strip()}")
    if retry_note:
        prompt_parts.append(f"\n--- Retry Guidance ---\n{retry_note}")
    if table_hint:
        prompt_parts.append(f"\n{table_hint}")
    if tables_markdown:
        prompt_parts.append(f"\n--- Parsed Tables From Kept Pages ---\n{tables_markdown}")
    prompt_parts.append(f"\n--- Trimmed OCR Text ---\n{trimmed_text}")
    # In multi-doc mode the trimmed_text starts with the MULTI-DOCUMENT preamble.
    # Address fields must come from the PRIMARY SCHEDULE table only.
    is_multi_doc = "MULTI-DOCUMENT SOV EXTRACTION" in trimmed_text
    address_rule = (
        "ADDRESS FIELDS (Street Address, City, State, Zip): copy these EXACTLY and ONLY from the "
        "[PRIMARY SCHEDULE] tabular data. Narrative text in [SUPPLEMENTAL] documents may reference "
        "location names or cities — those mentions are for row identification only. "
        "NEVER use them to populate or modify address fields. "
        "If a supplemental narrative says 'Harbor location in San Antonio' do not write that into "
        "the Street Address — take the address exclusively from the primary schedule table.\n"
    ) if is_multi_doc else ""
    prompt_parts.append(
        "\n--- Extraction Rules ---\n"
        + address_rule +
        "COMPLETENESS IS CRITICAL — read every page of the OCR text in full before outputting anything.\n"
        "Schedules often continue across pages with the same column headers repeated; include ALL rows from ALL pages.\n"
        "Before writing output: count the data rows visible in the schedule table(s) and return that exact count.\n"
        "Return one object per real repeated schedule row.\n"
        "Prefer master schedules and structured tables over narrative duplicates.\n"
        "Merge detail from the selected source context into the correct row only when the location/entity match is clear.\n"
        "Extract ALL real rows even when many requested fields are null for a given row.\n"
        "If the requested schema is broader than the document, still emit the row and leave unsupported fields null.\n"
        "Never emit headers, subtotals, totals, or blank rows.\n"
        "Use null when a field is genuinely absent.\n"
        "Return spreadsheet-ready scalar values only.\n"
        "CRITICAL — JSON KEYS: Each JSON key MUST be the exact requested field name from the Fields to Extract list above. "
        "Never use the document's column header abbreviation as the key. "
        "Example: if the document column is 'TIV' and the requested field is 'Total Insurable Value (TIV)', the key must be 'Total Insurable Value (TIV)'.\n"
        'Return exactly: {"records": [{"Field": "value"}, ...]}'
    )

    system_prompt = (
        "You extract repeated records from document schedules and tables.\n"
        "Focus on repeated rows for locations, vehicles, employees, or any other entity type present.\n"
        "Column headers are often abbreviated or use domain-specific shorthand. "
        "Match each requested field to the most semantically equivalent column — "
        "do not require an exact label match. Use document footnotes and legend text to resolve abbreviations.\n"
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
            _sov_extract_token_budget(len(field_names), expected_rows),
        )
        rows = _normalise_rows(raw, field_names, doc.filename)
        return rows if rows else _empty([doc.filename], field_names)
    except Exception as exc:
        logger.error("Dedicated SOV extraction failed for %s: %s", doc.filename, exc)
        return _error([doc.filename], field_names, str(exc))


async def _two_pass_extract(
    doc: ParsedDocument,
    fields: List[Dict[str, str]],
    trimmed_text: str,
    selected_headers: str,
    tables_markdown: str,
    table_hint: str,
    usage: LLMUsage,
    expected_rows: int | None,
    instructions: str,
) -> List[Dict[str, Any]]:
    """
    Pass 1 — full extraction: get as many rows as possible.
    Pass 2 — enrichment: fill in missing values from the same source.
    Skips Pass 2 if fill rate is already ≥85%.
    """
    field_names = [f["name"] for f in fields]

    # Pass 1: full extraction
    rows = await _extract_rows(
        doc, fields, trimmed_text, selected_headers,
        tables_markdown, table_hint, usage, expected_rows,
        instructions,
    )

    real_rows = [r for r in rows if not r.get("_error")]
    if not real_rows:
        return rows

    total_cells = len(real_rows) * max(1, len(field_names))
    missing = sum(
        1 for row in real_rows for fn in field_names
        if row.get(fn) is None or str(row.get(fn, "")).strip().lower() in _EMPTY_VALUES
    )
    fill_rate = (total_cells - missing) / total_cells

    logger.info(
        "SOV pass 1 for %s: %d rows, fill_rate=%.0f%%, missing=%d/%d cells",
        doc.filename, len(real_rows), fill_rate * 100, missing, total_cells,
    )

    if missing == 0:
        return rows

    # Pass 2: enrichment — fill missing values, do not change existing ones
    current_json = json.dumps(
        [{fn: row.get(fn) for fn in field_names} for row in real_rows],
        ensure_ascii=True,
    )
    enrich_note = (
        f"REVIEW PASS — {len(real_rows)} rows extracted so far but the schedule likely contains more.\n"
        f"{missing} of {total_cells} fields are still empty (fill rate {fill_rate:.0%}).\n"
        "Re-read the ENTIRE source document carefully and:\n"
        "1. Add any rows present in the document that are missing from the current data.\n"
        "2. Fill in empty/null fields in the existing rows.\n"
        "3. Do NOT remove or change values that are already filled in.\n"
        "Return ALL rows ordered as they appear in the document (existing + any newly found).\n\n"
        f"Current extracted rows:\n{current_json}"
    )
    enriched = await _extract_rows(
        doc, fields, trimmed_text, selected_headers,
        tables_markdown, table_hint, usage, expected_rows,
        instructions, retry_note=enrich_note,
    )

    enriched_real = [r for r in enriched if not r.get("_error")]
    if not enriched_real:
        return rows

    # If Pass 2 found more rows, use it as the base and fill any gaps from Pass 1
    if len(enriched_real) >= len(real_rows):
        # Build a lookup from Pass 1 by first non-null identifying value
        def _row_key(row: dict) -> str:
            for fn in field_names:
                v = row.get(fn)
                if v is not None and str(v).strip().lower() not in _EMPTY_VALUES:
                    return str(v).strip().lower()
            return ""

        pass1_by_key = {_row_key(r): r for r in real_rows if _row_key(r)}
        merged = []
        for enriched_row in enriched_real:
            key = _row_key(enriched_row)
            base = pass1_by_key.get(key, {})
            combined = {**enriched_row}
            # Prefer Pass 1 values (they came from a clean extraction, not a review pass)
            for fn in field_names:
                v1 = base.get(fn)
                if v1 is not None and str(v1).strip().lower() not in _EMPTY_VALUES:
                    combined[fn] = v1
            merged.append(combined)
    else:
        # Pass 2 returned fewer rows — just use it to fill gaps in Pass 1
        merged = [{**row} for row in real_rows]
        for i, enriched_row in enumerate(enriched_real[: len(merged)]):
            for fn in field_names:
                if merged[i].get(fn) is None or str(merged[i].get(fn, "")).strip().lower() in _EMPTY_VALUES:
                    val = enriched_row.get(fn)
                    if val is not None and str(val).strip().lower() not in _EMPTY_VALUES:
                        merged[i][fn] = val

    filled_after = sum(
        1 for row in merged for fn in field_names
        if row.get(fn) is not None and str(row.get(fn, "")).strip().lower() not in _EMPTY_VALUES
    )
    total_cells_after = len(merged) * max(1, len(field_names))
    logger.info(
        "SOV pass 2 for %s: rows %d→%d, fill_rate %.0f%%→%.0f%%",
        doc.filename, len(real_rows), len(merged),
        fill_rate * 100, filled_after / total_cells_after * 100,
    )

    return merged


async def _batched_extract(
    doc: ParsedDocument,
    fields: List[Dict[str, str]],
    sections: list[SOVSection],
    pages_text_by_num: dict[int, str],
    table_hint: str,
    usage: LLMUsage,
    total_expected_rows: int,
    instructions: str,
) -> List[Dict[str, Any]]:
    """
    For large documents (>_MAX_ROWS_PER_PASS expected rows), split sections into
    page batches and extract each batch independently, then concatenate.
    """
    field_names = [f["name"] for f in fields]
    # Estimate rows per section (page) and group into batches of ~_MAX_ROWS_PER_PASS rows
    rows_per_section = max(1, total_expected_rows // max(1, len(sections)))
    sections_per_batch = max(1, _MAX_ROWS_PER_PASS // max(1, rows_per_section))

    # Build page batches
    batches: list[list[SOVSection]] = []
    for i in range(0, len(sections), sections_per_batch):
        batches.append(sections[i : i + sections_per_batch])

    logger.info(
        "SOV batched extraction for %s: %d sections → %d batches × ~%d rows/batch",
        doc.filename, len(sections), len(batches), rows_per_section * sections_per_batch,
    )

    all_rows: list[dict] = []
    for batch_idx, batch_sections in enumerate(batches):
        batch_text = "\n\n".join(s.content for s in batch_sections).strip()
        batch_pages = {s.page_num for s in batch_sections}
        batch_tables = [t for t in doc.tables if t.page_num in batch_pages]
        batch_tables_md = "\n\n".join(
            f"[Table - page {t.page_num}, {t.row_count}x{t.col_count}]\n{t.markdown}"
            for t in batch_tables
        )
        batch_headers = "\n".join(
            f"- page {s.page_num}: header={json.dumps(s.header or '', ensure_ascii=True)} — {s.preview}"
            for s in batch_sections
        )
        batch_expected = rows_per_section * len(batch_sections)

        logger.info(
            "SOV batch %d/%d for %s: pages=%s, expected_rows≈%d",
            batch_idx + 1, len(batches), doc.filename,
            sorted(batch_pages), batch_expected,
        )
        batch_rows = await _two_pass_extract(
            doc, fields, batch_text, batch_headers,
            batch_tables_md, table_hint, usage, batch_expected,
            instructions,
        )
        real_batch = [r for r in batch_rows if not r.get("_error")]
        all_rows.extend(real_batch)
        logger.info(
            "SOV batch %d/%d done: %d rows (running total: %d)",
            batch_idx + 1, len(batches), len(real_batch), len(all_rows),
        )

    logger.info(
        "SOV batched extraction complete for %s: %d total rows from %d batches",
        doc.filename, len(all_rows), len(batches),
    )
    return all_rows if all_rows else _empty([doc.filename], field_names)


async def extract_sov_from_document(
    doc: ParsedDocument,
    fields: List[Dict[str, str]],
    usage: LLMUsage,
    instructions: str = "",
) -> List[Dict[str, Any]]:
    field_names = [field["name"] for field in fields]
    filename_lower = doc.filename.lower()
    is_spreadsheet = filename_lower.endswith((".xlsx", ".xls", ".xlsm", ".csv"))

    # ── Routing: OCR for scanned or large docs; LiteParse for small digital docs ──
    # Emails and HTML files are already parsed into text by parse_pdf — never OCR them
    _NO_OCR_EXTS = {".eml", ".emlx", ".msg", ".html", ".htm"}
    is_text_only = any(filename_lower.endswith(ext) for ext in _NO_OCR_EXTS)
    use_ocr = (
        not is_spreadsheet
        and not is_text_only
        and (doc.is_scanned or doc.page_count > _SOV_LITEPARSE_THRESHOLD_PAGES)
        and bool(settings.mistral_api_key and doc.file_path)
    )

    kept_pages: set[int] = set()
    selected_tables = doc.tables
    trimmed_text = ""
    selected_headers = ""
    page_sections: list[SOVSection] = []  # per-page sections for batching

    ocr_succeeded = False
    if use_ocr:
        try:
            ocr_result = await run_mistral_ocr(
                doc.file_path, settings.mistral_api_key, max_pages=_SOV_OCR_MAX_PAGES
            )
            usage.add_ocr_cost(ocr_result.cost_usd)
            logger.info(
                "Dedicated SOV OCR complete for %s: %d pages, %d chars, $%.4f",
                doc.filename, ocr_result.page_count, len(ocr_result.text), ocr_result.cost_usd,
            )
            ocr_succeeded = True
        except Exception as exc:
            logger.warning(
                "Dedicated SOV OCR failed for %s: %s — falling back to LiteParse",
                doc.filename, exc,
            )

    if use_ocr and ocr_succeeded:
        sections = _build_sections_from_ocr_pages(ocr_result.pages)
        # Use all OCR pages up to the cap — no LLM-based section selector.
        # End-of-document pages (appendices, endorsements) are cut off by the
        # _SOV_OCR_MAX_PAGES cap, so selecting a subset adds cost without benefit.
        selected_sections = sections
        kept_pages = {section.page_num for section in selected_sections}

        page_sections = selected_sections
        trimmed_text = "\n\n".join(section.content for section in selected_sections).strip()
        if not trimmed_text:
            trimmed_text = ocr_result.text

        selected_headers = "\n".join(
            f"- page {section.page_num}: header={json.dumps(section.header or '', ensure_ascii=True)} — {section.preview}"
            for section in selected_sections
        ) or "- no OCR headers were returned"
        selected_tables = _selected_tables(doc, kept_pages)

        logger.info(
            "SOV OCR routing for %s: scanned=%s pages=%d → using all %d OCR pages (no selector)",
            doc.filename, doc.is_scanned, doc.page_count, len(sections),
        )
    else:
        # LiteParse: small non-scanned doc (≤15 pages) or spreadsheet
        if doc.is_scanned:
            logger.warning(
                "SOV scanned fallback for %s: Mistral OCR unavailable, using parser text",
                doc.filename,
            )
        else:
            logger.info(
                "SOV LiteParse for %s: page_count=%d (≤%d, not scanned%s)",
                doc.filename, doc.page_count, _SOV_LITEPARSE_THRESHOLD_PAGES,
                ", spreadsheet" if is_spreadsheet else "",
            )
        kept_pages = {page.page_num for page in doc.pages} or set(range(1, doc.page_count + 1))
        trimmed_text = (
            "\n\n".join(f"=== Page {page.page_num} ===\n{page.text}" for page in doc.pages)
            or doc.content_text
            or ""
        )
        selected_headers = (
            "- full document kept\n"
            f"- LiteParse (page_count={doc.page_count}, scanned={doc.is_scanned})"
        )
        # Build pseudo-sections from parsed pages for batching support
        page_sections = [
            SOVSection(
                index=i + 1,
                page_num=page.page_num,
                header="",
                preview=page.text[:100] if page.text else "",
                content=f"=== Page {page.page_num} ===\n{page.text}",
            )
            for i, page in enumerate(doc.pages)
        ]

    # ── Compress + build table context ─────────────────────────────────────────
    table_hint = build_table_column_hint(selected_tables)
    expected_rows = _estimate_expected_rows(doc, kept_pages)

    # ── Route: batched extraction for large documents ──────────────────────────
    if expected_rows is not None and expected_rows > _MAX_ROWS_PER_PASS and page_sections:
        # Use page-batched extraction — avoids output token cap truncating large schedules
        logger.info(
            "SOV switching to batched extraction for %s: expected_rows=%d > %d",
            doc.filename, expected_rows, _MAX_ROWS_PER_PASS,
        )
        rows = await _batched_extract(
            doc, fields, page_sections, {},
            table_hint, usage, expected_rows, instructions,
        )
        return rows if rows else _empty([doc.filename], field_names)

    # ── Standard single-pass for normal-sized documents ────────────────────────
    trimmed_text = await _maybe_compress_with_bear(
        trimmed_text, doc.page_count, usage, f"{doc.filename} SOV trimmed text"
    )
    tables_markdown = await _maybe_compress_with_bear(
        _selected_tables_markdown(doc, kept_pages),
        doc.page_count,
        usage,
        f"{doc.filename} SOV kept tables",
    )

    rows = await _two_pass_extract(
        doc, fields, trimmed_text, selected_headers,
        tables_markdown, table_hint, usage, expected_rows,
        instructions,
    )

    return rows if rows else _empty([doc.filename], field_names)
