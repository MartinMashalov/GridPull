from __future__ import annotations

import asyncio
import json
import logging
import re
from typing import Any, Dict, List, Optional

from app.config import settings
from app.services.llm_router import routed_acompletion

from .core import (
    _CLEANUP_MODEL,
    _MULTI_SYSTEM,
    _TEXT_MODEL,
    _VISION_MODEL,
    _empty,
    _error,
    _fields_block,
    _is_filled_value,
    _maybe_compress_with_bear,
    _normalise_rows,
    _system_with_date,
    LLMUsage,
    record_llm_usage_cost,
)

_REVIEW_MAX_TOKENS = 32_768

logger = logging.getLogger(__name__)


async def _llm_acompletion(**kwargs: Any) -> Any:
    """All LLM chat calls go through the shared router."""
    return await routed_acompletion(route_profile="extraction", **kwargs)


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
    _RATE_LIMIT_KEYWORDS = ("rate", "429", "quota", "capacity", "overloaded", "tpm", "rpm")
    active_model = model
    for attempt in range(3):
        try:
            resp = await _llm_acompletion(
                model=active_model,
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
                # Log cache hit rate for prompt caching optimization
                details = getattr(resp.usage, "prompt_tokens_details", None)
                cached = getattr(details, "cached_tokens", 0) if details else 0
                if cached > 0:
                    pct = cached / resp.usage.prompt_tokens * 100 if resp.usage.prompt_tokens else 0
                    logger.info(
                        "Cache hit: %d/%d input tokens (%.0f%%) for %s",
                        cached, resp.usage.prompt_tokens, pct, filename,
                    )
            record_llm_usage_cost(usage, resp)
            raw = json.loads(resp.choices[0].message.content)
            result = _normalise_rows(raw, field_names, filename)
            return result if result else _empty([filename], field_names)
        except Exception as exc:
            err_str = str(exc).lower()
            # On first attempt, fall back to the cheaper model on rate-limit / capacity errors
            if attempt == 0 and any(kw in err_str for kw in _RATE_LIMIT_KEYWORDS):
                fallback = settings.llm_openai_fallback_model
                if fallback != active_model:
                    logger.warning(
                        "Extraction rate-limited on %s for %s — falling back to %s",
                        active_model, filename, fallback,
                    )
                    active_model = fallback
                    continue
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


async def _llm_extract_vision(
    system: str,
    user_prompt: str,
    field_names: List[str],
    filename: str,
    usage: LLMUsage,
) -> List[Dict[str, Any]]:
    return await _llm_extract(
        system, user_prompt, field_names, filename, usage, _VISION_MODEL, vision_tokens=True
    )


def _infer_schedule_key_fields(
    rows: List[Dict[str, Any]],
    field_names: List[str],
) -> tuple[str | None, str | None]:
    data_rows = [row for row in rows if not row.get("_error")]
    if not data_rows:
        return (None, None)

    profiles: Dict[str, Dict[str, float]] = {}
    for fn in field_names:
        values = [
            re.sub(r"\s+", " ", str(row.get(fn) or "").strip())
            for row in data_rows
            if _is_filled_value(row.get(fn))
        ]
        if not values:
            continue
        count = len(values)
        unique_ratio = len({value.lower() for value in values}) / count
        avg_len = sum(len(value) for value in values) / count

        def ratio(predicate: Any) -> float:
            return sum(1 for value in values if predicate(value)) / count

        profiles[fn] = {
            "filled_ratio": count / len(data_rows),
            "unique_ratio": unique_ratio,
            "avg_len": avg_len,
            "short_code_ratio": ratio(
                lambda value: len(value) <= 16
                and " " not in value
                and any(ch.isdigit() for ch in value)
                and bool(re.fullmatch(r"[A-Za-z0-9#/_-]+", value))
            ),
            "numeric_only_ratio": ratio(lambda value: bool(re.fullmatch(r"\d+", value))),
            "large_number_ratio": ratio(
                lambda value: bool(re.fullmatch(r"\d+", value)) and int(value) > 999
            ),
            "year_like_ratio": ratio(
                lambda value: bool(re.fullmatch(r"(18|19|20)\d{2}", value))
            ),
            "zip_like_ratio": ratio(
                lambda value: bool(
                    re.fullmatch(r"\d{5}(?:-\d{4})?|[A-Za-z]\d[A-Za-z][ -]?\d[A-Za-z]\d", value)
                )
            ),
            "money_like_ratio": ratio(
                lambda value: bool(re.search(r"\$|\d{1,3}(?:,\d{3})+", value))
            ),
            "address_like_ratio": ratio(
                lambda value: len(value) >= 8
                and any(ch.isdigit() for ch in value)
                and any(ch.isalpha() for ch in value)
                and (" " in value or "," in value)
            ),
        }

    if not profiles:
        return (None, None)

    id_field: str | None = None
    id_score = float("-inf")
    addr_field: str | None = None
    addr_score = float("-inf")
    for fn, profile in profiles.items():
        score = (
            profile["filled_ratio"] * 1.5
            + profile["unique_ratio"] * 4
            + profile["short_code_ratio"] * 3
            + profile["numeric_only_ratio"]
            - profile["zip_like_ratio"] * 6
            - profile["address_like_ratio"] * 4
            - profile["money_like_ratio"] * 3
            - profile["year_like_ratio"] * 4
            - profile["large_number_ratio"] * 4
        )
        if score > id_score:
            id_score = score
            id_field = fn

        score = (
            profile["filled_ratio"] * 1.5
            + profile["unique_ratio"] * 1.5
            + profile["address_like_ratio"] * 4
            - profile["zip_like_ratio"] * 4
            - profile["money_like_ratio"] * 3
            - profile["short_code_ratio"] * 2
        )
        if score > addr_score:
            addr_score = score
            addr_field = fn

    if id_score < 2.5:
        id_field = None
    if addr_score < 2.0:
        addr_field = None
    return (id_field, addr_field)


def _merge_rows_by_identifier(
    rows: List[Dict[str, Any]],
    field_names: List[str],
) -> List[Dict[str, Any]]:
    """Merge rows that share the same entity identifier, combining non-null fields.

    Some documents emit multiple rows for the same entity (a summary row and one or more detail
    rows). This merges them into a single complete row per entity.

    Merging strategy (in order of priority):
    1. Primary key: base numeric ID (e.g. "1" from "1 - Building 1") + address (first 40 chars)
    2. Address-only key when no ID field found
    """
    if len(rows) <= 1:
        return rows

    id_field, addr_field = _infer_schedule_key_fields(rows, field_names)
    if not id_field and not addr_field:
        return rows

    def _norm(v: Any) -> str:
        return str(v or "").strip().lower()

    def _base_num(v: str) -> str:
        """Prefer the first token containing a digit; otherwise use the first token."""
        tokens = re.findall(r"[A-Za-z0-9#/_-]+", v.strip())
        for token in tokens:
            if any(ch.isdigit() for ch in token):
                return token
        return tokens[0] if tokens else v[:20]

    def _merge_key(row: Dict[str, Any]) -> str | None:
        parts = []
        if id_field and _is_filled_value(row.get(id_field)):
            v = _norm(row.get(id_field))
            parts.append(_base_num(v))
        if addr_field and _is_filled_value(row.get(addr_field)):
            v = _norm(row.get(addr_field))
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


def finalize_property_schedule_rows(
    rows: List[Dict[str, Any]],
    field_names: List[str],
) -> List[Dict[str, Any]]:
    """Drop blank/spacer rows, re-merge split location lines, remove exact duplicate records."""
    if not rows:
        return rows
    loc_num_fn, primary_addr = _infer_schedule_key_fields(rows, field_names)
    non_empty: List[Dict[str, Any]] = []
    for row in rows:
        if row.get("_error"):
            non_empty.append(row)
            continue
        filled = sum(1 for fn in field_names if _is_filled_value(row.get(fn)))
        if filled == 0:
            continue
        non_empty.append(row)
    if not non_empty:
        return rows
    merged = _merge_rows_by_identifier(non_empty, field_names)
    kept: List[Dict[str, Any]] = []
    for row in merged:
        if row.get("_error"):
            kept.append(row)
            continue
        loc_filled = bool(loc_num_fn and _is_filled_value(row.get(loc_num_fn)))
        addr_filled = bool(
            primary_addr
            and _is_filled_value(row.get(primary_addr))
        )
        if not (loc_filled or addr_filled):
            continue
        kept.append(row)
    if not kept:
        return rows
    bucket: dict[str, Dict[str, Any]] = {}
    bucket_order: List[str] = []
    for row in kept:
        if row.get("_error"):
            bucket[f"_err_{id(row)}"] = row
            bucket_order.append(f"_err_{id(row)}")
            continue
        loc_part = ""
        if loc_num_fn and _is_filled_value(row.get(loc_num_fn)):
            raw_loc = str(row.get(loc_num_fn)).strip()
            tokens = re.findall(r"[A-Za-z0-9#/_-]+", raw_loc)
            loc_part = next((token for token in tokens if any(ch.isdigit() for ch in token)), raw_loc[:24]).lower()
        addr_part = ""
        if primary_addr and _is_filled_value(row.get(primary_addr)):
            addr_part = re.sub(r"\s+", " ", str(row.get(primary_addr)).strip().lower()[:80])
        ck = f"{loc_part}\x00{addr_part}"
        if ck == "\x00":
            ck = f"row_{id(row)}"
        if ck not in bucket:
            bucket[ck] = dict(row)
            bucket_order.append(ck)
            continue
        base = dict(bucket[ck])
        for fn in field_names:
            if not _is_filled_value(base.get(fn)) and _is_filled_value(row.get(fn)):
                base[fn] = row.get(fn)
        bucket[ck] = base
    merged2 = [bucket[k] for k in bucket_order]
    seen: set[str] = set()
    out: List[Dict[str, Any]] = []
    for row in merged2:
        if row.get("_error"):
            out.append(row)
            continue
        norm_vals = {
            fn: re.sub(r"\s+", " ", str(row.get(fn, "") or "").strip().lower())
            for fn in field_names
        }
        sig = json.dumps(norm_vals, sort_keys=True)
        if sig in seen:
            continue
        seen.add(sig)
        out.append(row)
    if len(out) < len(rows):
        logger.info(
            "Schedule deduplication: %d rows -> %d",
            len(rows), len(out),
        )

    # Post-process: derive Location Name from Loc # when absent
    if "Location Name" in field_names and "Loc #" in field_names:
        for row in out:
            if row.get("_error"):
                continue
            loc_name = row.get("Location Name")
            if loc_name is None or str(loc_name).strip().lower() in ("", "null", "none", "n/a", "na", "-"):
                loc_num = row.get("Loc #")
                if loc_num is not None and str(loc_num).strip().lower() not in ("", "null", "none", "n/a", "na", "-"):
                    row["Location Name"] = f"Location {str(loc_num).strip()}"

    return out


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
        "- remove every completely empty record (all fields null, dash, or n/a) and duplicate rows for the same location\n"
        "- do not invent new values\n\n"
        f"Filename: {filename}\n"
        f"Requested fields:\n" + "\n".join(f"- {name}" for name in field_names) + "\n\n"
        + (f"User instructions:\n{instructions.strip()}\n\n" if instructions.strip() else "")
        + f"Document context:\n{doc_context}\n\n"
        + f"Extracted records to review:\n{json.dumps(rows, ensure_ascii=True)}\n\n"
        + 'Return exactly: {"records": [{"Field": "value"}, ...]}'
    )
    reviewed = await _llm_extract(_MULTI_SYSTEM, review_prompt, field_names, filename, usage, text_model, max_tokens=_REVIEW_MAX_TOKENS)

    # Post-merge: catch any remaining duplicates the LLM review didn't consolidate
    reviewed = _merge_rows_by_identifier(reviewed, field_names)

    deduped: List[Dict[str, Any]] = []
    seen: set[str] = set()
    for row in reviewed:
        key = json.dumps(
            {
                fn: re.sub(r"\s+", " ", str(row.get(fn, "") or "").strip().lower())
                for fn in field_names
            },
            sort_keys=True,
        )
        if key in seen:
            continue
        seen.add(key)
        deduped.append(row)
    return deduped or rows


async def backfill_missing_row_fields_from_document(
    rows: List[Dict[str, Any]],
    fields: List[Dict[str, str]],
    doc_content_text: str,
    page_count: int,
    filename: str,
    usage: LLMUsage,
    instructions: str = "",
) -> List[Dict[str, Any]]:
    """One pass: fill still-empty fields using full document text (schedule + narrative)."""
    field_names = [f["name"] for f in fields]
    _, addr_fn = _infer_schedule_key_fields(rows, field_names)
    items: List[Dict[str, Any]] = []
    for i, row in enumerate(rows):
        if row.get("_error"):
            continue
        missing = [fn for fn in field_names if not _is_filled_value(row.get(fn))]
        if not missing:
            continue
        near_text = ""
        if addr_fn and doc_content_text and _is_filled_value(row.get(addr_fn)):
            frag = str(row.get(addr_fn) or "").split(",")[0].strip()
            if len(frag) >= 6:
                ix = doc_content_text.find(frag)
                if ix >= 0:
                    near_text = doc_content_text[max(0, ix - 300) : ix + 2_200]
        item: Dict[str, Any] = {
            "index": i,
            "missing": missing,
            "known": {fn: row.get(fn) for fn in field_names if _is_filled_value(row.get(fn))},
        }
        if near_text.strip():
            item["near_text"] = near_text
        items.append(item)
    if not items:
        return rows

    ctx = await _maybe_compress_with_bear(
        doc_content_text,
        page_count,
        usage,
        f"{filename} schedule backfill",
    )
    fblock = _fields_block(fields)
    user_prompt = (
        "Each item lists array index, fields still missing, and fields already extracted. "
        "When 'near_text' is present, use it as the primary source for that item's missing fields "
        "(it is anchored to the row's strongest location fragment in the document).\n"
        "For every item, fill ONLY the missing fields. "
        "Do not overwrite or repeat 'known' values in the patch objects. Use null if absent.\n\n"
        f"--- Fields ---\n{fblock}\n\n"
        + (f"--- User instructions ---\n{instructions.strip()}\n\n" if instructions.strip() else "")
        + f"--- Document ---\n{ctx}\n\n--- Items ---\n{json.dumps(items, ensure_ascii=True)}\n\n"
        'Return exactly: {"patches": [{"index": <int>, "<Field Name>": "<value or null>"}]} '
        "with one patch object per item; each patch uses the exact schema field names that were missing."
    )
    try:
        resp = await _llm_acompletion(
            model=_TEXT_MODEL,
            messages=[
                {
                    "role": "system",
                    "content": _system_with_date(
                        "You patch incomplete tabular extractions. Return JSON only."
                    ),
                },
                {"role": "user", "content": user_prompt},
            ],
            temperature=0,
            response_format={"type": "json_object"},
            max_tokens=8_192,
        )
        if resp.usage:
            usage.add(resp.usage.prompt_tokens, resp.usage.completion_tokens)
        record_llm_usage_cost(usage, resp)
        raw = json.loads(resp.choices[0].message.content or "{}")
    except Exception as exc:
        logger.warning("Backfill pass failed for %s: %s", filename, exc)
        return rows

    patches = raw.get("patches")
    if not isinstance(patches, list):
        return rows
    allowed_keys = {item["index"]: set(item["missing"]) for item in items}
    for patch in patches:
        if not isinstance(patch, dict):
            continue
        idx = patch.get("index")
        if not isinstance(idx, int) or idx < 0 or idx >= len(rows):
            continue
        row = rows[idx]
        allow = allowed_keys.get(idx) or set()
        for fn in field_names:
            if fn not in allow or fn not in patch:
                continue
            if _is_filled_value(row.get(fn)):
                continue
            val = patch.get(fn)
            if val is not None and _is_filled_value(val):
                row[fn] = val
    return rows


async def _extract_record_count_metadata(
    doc_context: str,
    fields_block: str,
    filename: str,
    usage: LLMUsage,
    instructions: str = "",
) -> Optional[int]:
    """Ask the main text model how many data records the document contains (same accuracy target, lower $ vs a separate premium counter model)."""
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
        resp = await _llm_acompletion(
            model=_TEXT_MODEL,
            messages=[{"role": "user", "content": user_prompt}],
            response_format={"type": "json_object"},
            temperature=0,
            max_tokens=256,
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
        resp = await _llm_acompletion(
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
