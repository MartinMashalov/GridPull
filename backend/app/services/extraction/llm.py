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

def _review_max_tokens(n_fields: int) -> int:
    return min(65_536, max(16_384, n_fields * 400))

logger = logging.getLogger(__name__)

_MONEYISH_RE = re.compile(r"^[\(\-]?\$?\d[\d,]*(?:\.\d+)?\)?$")
_PERCENTISH_RE = re.compile(r"^[\(\-]?\d[\d,]*(?:\.\d+)?%$")
_COLLAPSE_WS_RE = re.compile(r"\s+")


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


def _normalise_cell_value(value: Any) -> str:
    return _COLLAPSE_WS_RE.sub(" ", str(value or "").strip().lower())


def _value_merge_score(value: str, occurrences: int) -> float:
    if not value or len(value) > 120:
        return -10.0
    score = 0.0
    if any(c.isalpha() for c in value):
        score += 2.0
    if any(c.isdigit() for c in value):
        score += 1.0
    if len(value) >= 6:
        score += 1.0
    if re.fullmatch(r"[a-z]{1,3}", value):
        score -= 2.0
    if _MONEYISH_RE.fullmatch(value) and any(ch in value for ch in "$,"):
        score -= 4.0
    if _PERCENTISH_RE.fullmatch(value):
        score -= 3.0
    if re.fullmatch(r"\d{4}", value):
        score -= 1.5
    elif re.fullmatch(r"\d+(?:\.\d+)?", value):
        score -= 0.5
    if occurrences == 2:
        score += 3.0
    elif occurrences == 3:
        score += 2.0
    elif occurrences == 4:
        score += 1.0
    elif occurrences > 4:
        score -= min(4.0, float(occurrences - 4))
    return score


def _row_pair_relation(
    row_a: Dict[str, Any],
    row_b: Dict[str, Any],
    field_names: List[str],
) -> tuple[int, int, int]:
    shared_equal = 0
    conflicts = 0
    complement = 0
    for fn in field_names:
        a_filled = _is_filled_value(row_a.get(fn))
        b_filled = _is_filled_value(row_b.get(fn))
        if a_filled and b_filled:
            if _normalise_cell_value(row_a.get(fn)) == _normalise_cell_value(row_b.get(fn)):
                shared_equal += 1
            else:
                conflicts += 1
        elif a_filled != b_filled:
            complement += 1
    return shared_equal, conflicts, complement


def _candidate_merge_groups(
    rows: List[Dict[str, Any]],
    field_name: str,
) -> tuple[Dict[str, List[int]], float, int]:
    raw_groups: Dict[str, List[int]] = {}
    for idx, row in enumerate(rows):
        if row.get("_error") or not _is_filled_value(row.get(field_name)):
            continue
        norm = _normalise_cell_value(row.get(field_name))
        if not norm:
            continue
        raw_groups.setdefault(norm, []).append(idx)

    non_empty_count = sum(len(idxs) for idxs in raw_groups.values())
    unique_ratio = (len(raw_groups) / non_empty_count) if non_empty_count else 0.0
    groups = {
        value: idxs
        for value, idxs in raw_groups.items()
        if 2 <= len(idxs) <= 4 and _value_merge_score(value, len(idxs)) >= 3.0
    }
    duplicated_rows = sum(len(idxs) for idxs in groups.values())
    return groups, unique_ratio, duplicated_rows


def _infer_merge_fields(
    rows: List[Dict[str, Any]],
    field_names: List[str],
) -> List[tuple[str, Dict[str, List[int]]]]:
    candidates: List[tuple[float, str, Dict[str, List[int]]]] = []
    for fn in field_names:
        groups, unique_ratio, duplicated_rows = _candidate_merge_groups(rows, fn)
        if not groups or unique_ratio < 0.35:
            continue
        shared_total = 0
        conflicts_total = 0
        complement_total = 0
        pair_count = 0
        for idxs in groups.values():
            for pos, idx_a in enumerate(idxs):
                for idx_b in idxs[pos + 1 :]:
                    shared, conflicts, complement = _row_pair_relation(rows[idx_a], rows[idx_b], field_names)
                    shared_total += shared
                    conflicts_total += conflicts
                    complement_total += complement
                    pair_count += 1
        if pair_count == 0:
            continue
        score = (
            duplicated_rows * (1.0 + unique_ratio)
            + shared_total * 2.0
            + complement_total * 0.25
            - conflicts_total * 1.5
        )
        if score > 0 and conflicts_total <= shared_total + 1:
            candidates.append((score, fn, groups))
    candidates.sort(key=lambda item: item[0], reverse=True)
    return [(fn, groups) for _, fn, groups in candidates[:3]]


def _merge_rows_by_identifier(
    rows: List[Dict[str, Any]],
    field_names: List[str],
) -> List[Dict[str, Any]]:
    if len(rows) <= 1:
        return rows

    merge_fields = _infer_merge_fields(rows, field_names)
    if not merge_fields:
        return rows

    parent = list(range(len(rows)))

    def find(idx: int) -> int:
        while parent[idx] != idx:
            parent[idx] = parent[parent[idx]]
            idx = parent[idx]
        return idx

    def union(left: int, right: int) -> None:
        root_left = find(left)
        root_right = find(right)
        if root_left != root_right:
            parent[root_right] = root_left

    for _, groups in merge_fields:
        for idxs in groups.values():
            for pos, idx_a in enumerate(idxs):
                for idx_b in idxs[pos + 1 :]:
                    shared, conflicts, complement = _row_pair_relation(rows[idx_a], rows[idx_b], field_names)
                    if conflicts == 0 and complement >= 1:
                        union(idx_a, idx_b)
                    elif conflicts <= 1 and shared >= 2 and complement >= 3:
                        union(idx_a, idx_b)

    buckets: Dict[int, List[Dict[str, Any]]] = {}
    order: List[int] = []
    for idx, row in enumerate(rows):
        root = find(idx)
        if root not in buckets:
            buckets[root] = []
            order.append(root)
        buckets[root].append(row)

    if all(len(group) == 1 for group in buckets.values()):
        return rows

    merged: List[Dict[str, Any]] = []
    for root in order:
        group = buckets[root]
        if len(group) == 1:
            merged.append(group[0])
            continue
        group_sorted = sorted(
            group,
            key=lambda row: sum(1 for fn in field_names if _is_filled_value(row.get(fn))),
            reverse=True,
        )
        base = dict(group_sorted[0])
        for other in group_sorted[1:]:
            for fn in field_names:
                if not _is_filled_value(base.get(fn)) and _is_filled_value(other.get(fn)):
                    base[fn] = other.get(fn)
        merged.append(base)

    logger.info(
        "Row merge: %d rows -> %d rows (merge_fields=%s)",
        len(rows),
        len(merged),
        ", ".join(fn for fn, _ in merge_fields),
    )
    return merged


def finalize_repeated_record_rows(
    rows: List[Dict[str, Any]],
    field_names: List[str],
) -> List[Dict[str, Any]]:
    """Drop completely empty rows, merge split records using repeated anchor values, and dedupe."""
    if not rows:
        return rows

    non_empty: List[Dict[str, Any]] = []
    for row in rows:
        if row.get("_error"):
            non_empty.append(row)
            continue
        if any(_is_filled_value(row.get(fn)) for fn in field_names):
            non_empty.append(row)
    if not non_empty:
        return rows

    merged = _merge_rows_by_identifier(non_empty, field_names)
    seen: set[str] = set()
    out: List[Dict[str, Any]] = []
    for row in merged:
        if row.get("_error"):
            out.append(row)
            continue
        sig = json.dumps(
            {fn: _normalise_cell_value(row.get(fn)) for fn in field_names},
            sort_keys=True,
        )
        if sig in seen:
            continue
        seen.add(sig)
        out.append(row)

    if len(out) < len(rows):
        logger.info(
            "Repeated-record cleanup: %d rows -> %d",
            len(rows),
            len(out),
        )
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

    # For large result sets the LLM review prompt (full doc context + all rows as JSON)
    # becomes enormous and takes minutes.  Use fast in-code merge/dedup instead.
    _REVIEW_ROW_LIMIT = 20

    def _code_dedup(source: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        merged = _merge_rows_by_identifier(source, field_names)
        deduped: List[Dict[str, Any]] = []
        seen: set[str] = set()
        for row in merged:
            key = json.dumps(
                {fn: re.sub(r"\s+", " ", str(row.get(fn, "") or "").strip().lower()) for fn in field_names},
                sort_keys=True,
            )
            if key in seen:
                continue
            seen.add(key)
            deduped.append(row)
        return deduped or source

    if len(rows) >= _REVIEW_ROW_LIMIT:
        logger.info(
            "Skipping LLM review for %s (%d rows >= %d threshold) — using in-code dedup only",
            filename, len(rows), _REVIEW_ROW_LIMIT,
        )
        return _code_dedup(rows)

    review_prompt = (
        "Review these extracted records and return a cleaned records array.\n\n"
        "Goals:\n"
        "- keep only records that match the same natural row unit\n"
        "- remove duplicates and near-duplicates\n"
        "- if the same entity appears in multiple records (for example: one summary "
        "row with financial values and one detail row with other attributes for the same "
        "identifier), MERGE them into one record by combining all non-null fields — do NOT drop any "
        "non-null value from either row\n"
        "- if the same fact appears in multiple formats, keep the most document-faithful spreadsheet-ready value\n"
        "- remove subtotal, segment, regional, subcategory, or alternate-view rows unless the requested fields clearly ask for them\n"
        "- remove every completely empty record (all fields null, dash, or n/a) and duplicate rows for the same entity\n"
        "- do not invent new values\n\n"
        f"Filename: {filename}\n"
        f"Requested fields:\n" + "\n".join(f"- {name}" for name in field_names) + "\n\n"
        + (f"User instructions:\n{instructions.strip()}\n\n" if instructions.strip() else "")
        + f"Document context:\n{doc_context}\n\n"
        + f"Extracted records to review:\n{json.dumps(rows, ensure_ascii=True)}\n\n"
        + 'Return exactly: {"records": [{"Field": "value"}, ...]}'
    )
    reviewed = await _llm_extract(_MULTI_SYSTEM, review_prompt, field_names, filename, usage, text_model, max_tokens=_review_max_tokens(len(field_names)))

    # Post-merge: catch any remaining duplicates the LLM review didn't consolidate
    return _code_dedup(reviewed)


def _build_row_value_frequencies(
    rows: List[Dict[str, Any]],
    field_names: List[str],
) -> Dict[str, int]:
    counts: Dict[str, int] = {}
    for row in rows:
        if row.get("_error"):
            continue
        seen_in_row: set[str] = set()
        for fn in field_names:
            if not _is_filled_value(row.get(fn)):
                continue
            norm = _normalise_cell_value(row.get(fn))
            if not norm or norm in seen_in_row:
                continue
            counts[norm] = counts.get(norm, 0) + 1
            seen_in_row.add(norm)
    return counts


def _select_row_anchor_text(
    row: Dict[str, Any],
    field_names: List[str],
    value_frequencies: Dict[str, int],
    flat_doc_text_lower: str,
) -> tuple[Optional[int], str]:
    best_score: float | None = None
    best_ix: Optional[int] = None
    best_text = ""

    for fn in field_names:
        if not _is_filled_value(row.get(fn)):
            continue
        raw = _COLLAPSE_WS_RE.sub(" ", str(row.get(fn)).strip())
        if not raw:
            continue
        norm = raw.lower()
        score = _value_merge_score(norm, value_frequencies.get(norm, 1))
        if score < 2.0:
            continue
        ix = flat_doc_text_lower.find(norm)
        if ix < 0 and len(norm) >= 10:
            words = norm.split()
            if len(words) >= 2:
                ix = flat_doc_text_lower.find(" ".join(words[:2]))
        if ix < 0:
            continue
        if best_score is None or score > best_score or (score == best_score and len(raw) > len(best_text)):
            best_score = score
            best_ix = ix
            best_text = raw

    return best_ix, best_text


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
    flat_doc_text = _COLLAPSE_WS_RE.sub(" ", doc_content_text)
    flat_doc_text_lower = flat_doc_text.lower()
    value_frequencies = _build_row_value_frequencies(rows, field_names)
    items: List[Dict[str, Any]] = []
    for i, row in enumerate(rows):
        if row.get("_error"):
            continue
        missing = [fn for fn in field_names if not _is_filled_value(row.get(fn))]
        if not missing:
            continue
        near_text = ""
        ix, anchor_text = _select_row_anchor_text(row, field_names, value_frequencies, flat_doc_text_lower)
        if ix is not None and anchor_text:
            win_after = min(8_000, max(2_800, 400 * len(missing) + len(anchor_text) + 400))
            anchor_lower = anchor_text.lower()
            best_ix = ix
            best_colons = flat_doc_text[max(0, ix - 450) : ix + win_after].count(":")
            search_start = ix + 1
            while True:
                next_ix = flat_doc_text_lower.find(anchor_lower, search_start)
                if next_ix < 0:
                    break
                window = flat_doc_text[max(0, next_ix - 450) : next_ix + win_after]
                colons = window.count(":")
                if colons > best_colons:
                    best_colons = colons
                    best_ix = next_ix
                search_start = next_ix + 1
            near_text = flat_doc_text[max(0, best_ix - 450) : best_ix + win_after]
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
        "(it is anchored to a distinctive value already present in that row).\n"
        "For every item, fill ONLY the missing fields. "
        "Do not overwrite or repeat 'known' values in the patch objects. Use null if absent.\n\n"
        f"--- Fields ---\n{fblock}\n\n"
        + (f"--- User instructions ---\n{instructions.strip()}\n\n" if instructions.strip() else "")
        + f"--- Document ---\n{ctx}\n\n--- Items ---\n{json.dumps(items, ensure_ascii=True)}\n\n"
        'Return exactly: {"patches": [{"index": <int>, "<Field Name>": "<value or null>"}]} '
        "with one patch object per item; each patch uses the exact schema field names that were missing."
    )
    try:
        resp = await _litellm_acompletion(
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
            max_tokens=min(16_384, 5_000 + 220 * len(items)),
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
        resp = await _litellm_acompletion(
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
