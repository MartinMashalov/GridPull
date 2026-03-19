from __future__ import annotations

import asyncio
import json
import logging
import re
from typing import Any, Dict, List, Optional

import litellm

from app.config import settings

from .core import (
    _CLEANUP_MODEL,
    _METADATA_MODEL,
    _MULTI_SYSTEM,
    _VISION_MODEL,
    _empty,
    _error,
    _fields_block,
    _is_filled_value,
    _normalise_rows,
    _system_with_date,
    LLMUsage,
    record_llm_usage_cost,
)

_REVIEW_MAX_TOKENS = 16_384

logger = logging.getLogger(__name__)


async def _litellm_acompletion(**kwargs: Any) -> Any:
    """All LLM chat calls go through LiteLLM (OpenAI via api_key). Mistral OCR stays in ocr_service only."""
    if not kwargs.get("api_key"):
        kwargs["api_key"] = settings.openai_api_key
    return await litellm.acompletion(**kwargs)


async def _llm_extract(
    system: str,
    user_prompt: str,
    field_names: List[str],
    filename: str,
    usage: LLMUsage,
    model: str,
    max_tokens: int = 4_096,
    vision_tokens: bool = False,
) -> List[Dict[str, Any]]:
    system_prompt = f"{_system_with_date(system)}\n\nReturn a valid JSON object only."
    for attempt in range(3):
        try:
            resp = await _litellm_acompletion(
                model=model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                temperature=0,
                response_format={"type": "json_object"},
                max_tokens=max_tokens,
            )
            if resp.usage:
                if vision_tokens:
                    usage.add_vision(resp.usage.prompt_tokens, resp.usage.completion_tokens)
                else:
                    usage.add(resp.usage.prompt_tokens, resp.usage.completion_tokens)
            record_llm_usage_cost(usage, resp)
            raw = json.loads(resp.choices[0].message.content)
            result = _normalise_rows(raw, field_names, filename)
            return result if result else _empty([filename], field_names)
        except Exception as exc:
            if attempt == 2:
                logger.error(
                    "%s extraction failed for %s: %s",
                    "SCAN" if vision_tokens else "TEXT",
                    filename,
                    exc,
                )
                return _error([filename], field_names, str(exc))
            await asyncio.sleep(1)
    return _empty([filename], field_names)


async def _litellm_extract(
    system: str,
    user_prompt: str,
    field_names: List[str],
    filename: str,
    usage: LLMUsage,
) -> List[Dict[str, Any]]:
    return await _llm_extract(
        system, user_prompt, field_names, filename, usage, _VISION_MODEL, vision_tokens=True
    )


def _merge_rows_by_identifier(
    rows: List[Dict[str, Any]],
    field_names: List[str],
) -> List[Dict[str, Any]]:
    """Merge rows that share the same location identifier, combining non-null fields.

    Documents like appraisal reports emit both a summary row (with financial values) and a
    detail row (with construction attributes) for the same location. This merges them into
    a single complete row per location.

    Merging strategy (in order of priority):
    1. Primary key: base numeric ID (e.g. "1" from "1 - Building 1") + address (first 40 chars)
    2. Address-only key when no ID field found
    """
    if len(rows) <= 1:
        return rows

    id_candidates = [fn for fn in field_names if any(
        kw in fn.lower() for kw in ("number", "no.", "id", "loc", "#")
    )]
    addr_candidates = [fn for fn in field_names if any(
        kw in fn.lower() for kw in ("address", "street")
    )]

    if not id_candidates and not addr_candidates:
        return rows

    id_field = id_candidates[0] if id_candidates else None
    addr_field = addr_candidates[0] if addr_candidates else None

    def _norm(v: Any) -> str:
        return str(v or "").strip().lower()

    def _base_num(v: str) -> str:
        """Extract leading numeric portion: '1 - Building 1' -> '1', 'Loc 0012' -> '0012'"""
        m = re.match(r"^(?:loc(?:ation)?\s*#?\s*)?(\d+)", v.strip(), re.I)
        return m.group(1) if m else v[:20]

    def _merge_key(row: Dict[str, Any]) -> str | None:
        parts = []
        if id_field:
            v = _norm(row.get(id_field))
            if v and v not in {"none", "null", "n/a", "-"}:
                parts.append(_base_num(v))
        if addr_field:
            v = _norm(row.get(addr_field))
            if v and v not in {"none", "null", "n/a", "-"}:
                parts.append(v[:40])
        return "|".join(parts) if parts else None

    groups: dict[str, List[Dict[str, Any]]] = {}
    order: List[str] = []
    no_key_rows: List[Dict[str, Any]] = []

    for row in rows:
        key = _merge_key(row)
        if key is None:
            no_key_rows.append(row)
            continue
        if key not in groups:
            groups[key] = []
            order.append(key)
        groups[key].append(row)

    if all(len(g) == 1 for g in groups.values()):
        return rows

    merged: List[Dict[str, Any]] = []
    any_merged = False
    for key in order:
        group = groups[key]
        if len(group) == 1:
            merged.append(group[0])
            continue
        any_merged = True
        # Use the row with the most filled fields as the base
        group_sorted = sorted(
            group,
            key=lambda r: sum(1 for fn in field_names if _is_filled_value(r.get(fn))),
            reverse=True,
        )
        base = dict(group_sorted[0])
        for other in group_sorted[1:]:
            for fn in field_names:
                if not _is_filled_value(base.get(fn)) and _is_filled_value(other.get(fn)):
                    base[fn] = other.get(fn)
        merged.append(base)

    merged.extend(no_key_rows)
    if any_merged:
        logger.info(
            "Row merge: %d rows -> %d rows (id_field=%s, addr_field=%s)",
            len(rows), len(merged), id_field, addr_field,
        )
    return merged


async def _review_multi_rows(
    rows: List[Dict[str, Any]],
    field_names: List[str],
    filename: str,
    usage: LLMUsage,
    doc_context: str,
    instructions: str = "",
    text_model: str = "gpt-4.1-mini",
) -> List[Dict[str, Any]]:
    if len(rows) <= 1:
        return rows

    review_prompt = (
        "Review these extracted records and return a cleaned records array.\n\n"
        "Goals:\n"
        "- keep only records that match the same natural row unit\n"
        "- remove duplicates and near-duplicates\n"
        "- if the same location or entity appears in multiple records (for example: one summary "
        "row with financial values and one detail row with construction attributes for the same "
        "address), MERGE them into one record by combining all non-null fields — do NOT drop any "
        "non-null value from either row\n"
        "- if the same fact appears in multiple formats, keep the most document-faithful spreadsheet-ready value\n"
        "- remove subtotal, segment, regional, subcategory, or alternate-view rows unless the requested fields clearly ask for them\n"
        "- do not invent new values\n\n"
        f"Filename: {filename}\n"
        f"Requested fields:\n" + "\n".join(f"- {name}" for name in field_names) + "\n\n"
        + (f"User instructions:\n{instructions.strip()}\n\n" if instructions.strip() else "")
        + f"Document context:\n{doc_context[:10_000]}\n\n"
        + f"Extracted records to review:\n{json.dumps(rows, ensure_ascii=True)}\n\n"
        + 'Return exactly: {"records": [{"Field": "value"}, ...]}'
    )
    reviewed = await _llm_extract(_MULTI_SYSTEM, review_prompt, field_names, filename, usage, text_model, max_tokens=_REVIEW_MAX_TOKENS)

    # Post-merge: catch any remaining duplicates the LLM review didn't consolidate
    reviewed = _merge_rows_by_identifier(reviewed, field_names)

    deduped: List[Dict[str, Any]] = []
    seen: set[str] = set()
    for row in reviewed:
        key = json.dumps({fn: row.get(fn, "") for fn in field_names}, sort_keys=True)
        if key in seen:
            continue
        seen.add(key)
        deduped.append(row)
    return deduped or rows


async def _extract_record_count_metadata(
    doc_context: str,
    fields_block: str,
    filename: str,
    usage: LLMUsage,
    instructions: str = "",
) -> Optional[int]:
    """Ask gpt-5.4-mini (low reasoning) how many data records the document contains."""
    user_prompt = (
        "Count the total number of distinct data records in this document that match "
        "the requested fields schema. Count ONLY actual data rows — exclude headers, "
        "footers, subtotals, grand totals, and summary rows.\n\n"
        "Look for explicit counts stated in the document (e.g. '50 Locations', "
        "'Schedule of 30 vehicles'), the highest sequential record/location number, "
        "or count the data rows in the tables.\n\n"
        f"--- Fields ---\n{fields_block}\n\n"
        + (f"--- User Instructions ---\n{instructions.strip()}\n\n" if instructions.strip() else "")
        + f"--- Document Content ---\n{doc_context}\n\n"
        'Return a JSON object exactly as: {"total_records_expected": <integer>}'
    )
    try:
        resp = await _litellm_acompletion(
            model=_METADATA_MODEL,
            messages=[{"role": "user", "content": user_prompt}],
            response_format={"type": "json_object"},
            max_completion_tokens=256,
            reasoning_effort="low",
        )
        if resp.usage:
            usage.add(resp.usage.prompt_tokens, resp.usage.completion_tokens)
        record_llm_usage_cost(usage, resp)
        content = resp.choices[0].message.content
        if isinstance(content, list):
            content = "".join(str(part) for part in content)
        if not isinstance(content, str) or not content.strip():
            logger.info("Metadata count for %s: empty response content", filename)
            return None
        try:
            raw = json.loads(content)
        except json.JSONDecodeError:
            logger.info("Metadata count for %s: non-JSON content returned", filename)
            return None
        count = raw.get("total_records_expected")
        if isinstance(count, int) and count > 0:
            logger.info("Metadata count for %s: %d expected records", filename, count)
            return count
        logger.info("Metadata count for %s: returned %s (unusable)", filename, count)
        return None
    except Exception as exc:
        logger.warning("Metadata count extraction failed for %s: %s", filename, exc)
        return None


async def _cleanup_single_row_with_nano(
    row: Dict[str, Any],
    fields: List[Dict[str, str]],
    filename: str,
    usage: LLMUsage,
) -> Dict[str, Any]:
    field_names = [f["name"] for f in fields]
    payload = {fn: row.get(fn, "") for fn in field_names}
    cleanup_prompt = (
        "Review this extracted single-row record and clean only obvious data-quality issues.\n\n"
        "You must work only from the extracted dictionary plus the field names and descriptions.\n"
        "Do not use any external document context.\n"
        "Return a JSON object only.\n\n"
        "Rules:\n"
        "- Keep the same keys\n"
        "- Preserve values that already match the field intent\n"
        "- Treat each field description as the primary extraction intent and expected output shape\n"
        "- If a field clearly wants a spreadsheet scalar number, return only the numeric value that should appear in the cell\n"
        "- Remove currency codes or short labels like USD, RM, EUR only when they are not part of the requested field itself\n"
        "- If a field clearly wants a date, year, or revision date and the value looks obviously clipped, repair it only when the intended completion is clear from the field description or example; otherwise leave it unchanged\n"
        "- Do not add explanations or new facts\n\n"
        f"Filename: {filename}\n"
        f"Fields:\n{_fields_block(fields)}\n\n"
        f"Extracted row:\n{json.dumps(payload, ensure_ascii=True)}\n\n"
        'Return exactly: {"records": [{"Field Name": "value", ...}]}'
    )
    try:
        resp = await _litellm_acompletion(
            model=_CLEANUP_MODEL,
            messages=[{"role": "user", "content": cleanup_prompt}],
            response_format={"type": "json_object"},
            max_completion_tokens=1_200,
        )
        if resp.usage:
            usage.add_cleanup(resp.usage.prompt_tokens, resp.usage.completion_tokens)
        record_llm_usage_cost(usage, resp)
        raw = json.loads(resp.choices[0].message.content)
        cleaned_rows = _normalise_rows(raw, field_names, filename)
        if not cleaned_rows:
            return row
        cleaned = dict(row)
        candidate = cleaned_rows[0]
        for fn in field_names:
            new_val = candidate.get(fn)
            if new_val is not None and str(new_val).strip():
                cleaned[fn] = new_val
        return cleaned
    except Exception as exc:
        logger.warning("Single-row cleanup failed for %s: %s", filename, exc)
        return row
