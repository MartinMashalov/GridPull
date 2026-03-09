from __future__ import annotations

import asyncio
import json
import logging
from typing import Any, Dict, List

import litellm

from .core import (
    _CLEANUP_MODEL,
    _MULTI_SYSTEM,
    _VISION_MODEL,
    _empty,
    _error,
    _fields_block,
    _normalise_rows,
    _openai,
    _system_with_date,
    LLMUsage,
)

logger = logging.getLogger(__name__)


async def _llm_extract(
    system: str,
    user_prompt: str,
    field_names: List[str],
    filename: str,
    usage: LLMUsage,
    model: str,
) -> List[Dict[str, Any]]:
    for attempt in range(3):
        try:
            resp = await _openai.chat.completions.create(
                model=model,
                messages=[
                    {"role": "system", "content": _system_with_date(system)},
                    {"role": "user", "content": user_prompt},
                ],
                temperature=0,
                response_format={"type": "json_object"},
                max_tokens=4_096,
            )
            if resp.usage:
                usage.add(resp.usage.prompt_tokens, resp.usage.completion_tokens)
            raw = json.loads(resp.choices[0].message.content)
            result = _normalise_rows(raw, field_names, filename)
            return result if result else _empty([filename], field_names)
        except Exception as exc:
            if attempt == 2:
                logger.error("TEXT extraction failed for %s: %s", filename, exc)
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
    for attempt in range(3):
        try:
            resp = await litellm.acompletion(
                model=_VISION_MODEL,
                messages=[
                    {"role": "system", "content": _system_with_date(system)},
                    {"role": "user", "content": user_prompt},
                ],
                temperature=0,
                response_format={"type": "json_object"},
                max_tokens=4_096,
            )
            if resp.usage:
                usage.add_vision(resp.usage.prompt_tokens, resp.usage.completion_tokens)
            raw = json.loads(resp.choices[0].message.content)
            result = _normalise_rows(raw, field_names, filename)
            return result if result else _empty([filename], field_names)
        except Exception as exc:
            if attempt == 2:
                logger.error("SCAN extraction failed for %s: %s", filename, exc)
                return _error([filename], field_names, str(exc))
            await asyncio.sleep(1)
    return _empty([filename], field_names)


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
    reviewed = await _llm_extract(_MULTI_SYSTEM, review_prompt, field_names, filename, usage, text_model)

    deduped: List[Dict[str, Any]] = []
    seen: set[str] = set()
    for row in reviewed:
        key = json.dumps({fn: row.get(fn, "") for fn in field_names}, sort_keys=True)
        if key in seen:
            continue
        seen.add(key)
        deduped.append(row)
    return deduped or rows


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
        resp = await _openai.chat.completions.create(
            model=_CLEANUP_MODEL,
            messages=[{"role": "user", "content": cleanup_prompt}],
            temperature=0,
            response_format={"type": "json_object"},
            max_tokens=1_200,
        )
        if resp.usage:
            usage.add_cleanup(resp.usage.prompt_tokens, resp.usage.completion_tokens)
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
