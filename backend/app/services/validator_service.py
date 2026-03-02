"""
Extraction validation service — computes quality metrics.

Metrics
-------
FFR  Field Fill Rate      % of expected fields with a non-empty, non-null value
NPR  Numeric Parse Rate   % of numeric-typed fields whose values parse as numbers
DPR  Date Parse Rate      % of date-typed fields whose values parse as dates
ERR  Error Row Rate       % of rows that contain an _error key
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Dict, List, Optional


# ── Result type ───────────────────────────────────────────────────────────────

@dataclass
class ValidationReport:
    row_count: int
    field_fill_rate: float        # 0.0 – 1.0
    numeric_parse_rate: float     # 0.0 – 1.0  (1.0 if no numeric fields)
    date_parse_rate: float        # 0.0 – 1.0  (1.0 if no date fields)
    error_row_rate: float         # rows with _error / total rows
    # Counts for transparency
    filled_fields: int
    total_fields: int
    numeric_hits: int
    numeric_total: int
    date_hits: int
    date_total: int

    def summary(self) -> str:
        return (
            f"Rows={self.row_count}  "
            f"FFR={self.field_fill_rate:.1%}  "
            f"NPR={self.numeric_parse_rate:.1%} ({self.numeric_hits}/{self.numeric_total})  "
            f"DPR={self.date_parse_rate:.1%} ({self.date_hits}/{self.date_total})  "
            f"ERR={self.error_row_rate:.1%}"
        )

    @property
    def overall_score(self) -> float:
        """Weighted composite score (0–1). FFR weighted most."""
        return round(
            self.field_fill_rate * 0.60
            + self.numeric_parse_rate * 0.20
            + self.date_parse_rate * 0.20,
            4,
        )


# ── Field-type heuristics ─────────────────────────────────────────────────────

_NUMERIC_KEYWORDS = {
    "amount", "price", "total", "cost", "fee", "tax", "payment", "balance",
    "subtotal", "charge", "rate", "salary", "revenue", "income", "expense",
    "profit", "loss", "value", "qty", "quantity", "count", "shares", "dollars",
    "cents", "premium", "deductible", "copay", "coinsurance", "billed",
    "allowed", "paid", "covered",
}

_DATE_KEYWORDS = {
    "date", "expiry", "expiration", "effective",
}

# Values considered "empty" / not extracted
_EMPTY_VALUES = {"", "null", "none", "n/a", "na", "-", "unknown", "not found", "not available"}

_NUMERIC_RE = re.compile(r"^\s*[\$£€¥]?\s*-?[\d,]+(\.\d+)?\s*%?\s*$")
_DATE_RE = re.compile(
    r"\b\d{1,2}[/\-\.]\d{1,2}[/\-\.]\d{2,4}\b"           # 03/20/2022 or 3-20-22
    r"|\b\d{4}[/\-\.]\d{1,2}[/\-\.]\d{1,2}\b"             # 2022-03-20
    r"|\b\d{1,2}[/\-]\d{4}\b"                              # 12/2022 (month/year)
    r"|\b(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\.?\s+\d{1,2},?\s+\d{4}\b"
    r"|\b(?:January|February|March|April|May|June|July|August|September|October|November|December)"
    r"\s+\d{1,2},?\s+\d{4}\b",
    re.I,
)


def _is_numeric_field(name: str) -> bool:
    words = set(re.split(r"[\s_\-]+", name.lower()))
    return bool(words & _NUMERIC_KEYWORDS)


def _is_date_field(name: str) -> bool:
    words = set(re.split(r"[\s_\-]+", name.lower()))
    return bool(words & _DATE_KEYWORDS)


def _parses_as_number(value: str) -> bool:
    if not value:
        return False
    cleaned = re.sub(r"[\$£€¥,\s%()]", "", value)
    # Handle parentheses as negative (e.g. accounting format)
    cleaned = cleaned.lstrip("-")
    try:
        float(cleaned)
        return True
    except ValueError:
        return False


def _parses_as_date(value: str) -> bool:
    if not value:
        return False
    return bool(_DATE_RE.search(value))


def _is_empty(value: str) -> bool:
    return value.strip().lower() in _EMPTY_VALUES


# ── Public API ────────────────────────────────────────────────────────────────

def score_extraction(rows: List[Dict], fields: List[str]) -> ValidationReport:
    """
    Compute quality metrics for a set of extracted rows.

    Args:
        rows:   Extracted data (list of dicts from extraction pipeline)
        fields: Expected field names (user-defined, internal _* fields excluded)

    Returns:
        ValidationReport with FFR, NPR, DPR, ERR.
    """
    if not rows:
        return ValidationReport(
            row_count=0,
            field_fill_rate=0.0,
            numeric_parse_rate=1.0,
            date_parse_rate=1.0,
            error_row_rate=0.0,
            filled_fields=0,
            total_fields=0,
            numeric_hits=0,
            numeric_total=0,
            date_hits=0,
            date_total=0,
        )

    numeric_fields = [f for f in fields if _is_numeric_field(f)]
    date_fields    = [f for f in fields if _is_date_field(f)]

    filled        = 0
    total         = len(rows) * len(fields)
    numeric_hits  = 0
    numeric_total = 0
    date_hits     = 0
    date_total    = 0
    error_rows    = 0

    for row in rows:
        if row.get("_error"):
            error_rows += 1

        for fn in fields:
            val = str(row.get(fn, "") or "").strip()
            if not _is_empty(val):
                filled += 1

        for fn in numeric_fields:
            val = str(row.get(fn, "") or "").strip()
            if not _is_empty(val):
                numeric_total += 1
                if _parses_as_number(val):
                    numeric_hits += 1

        for fn in date_fields:
            val = str(row.get(fn, "") or "").strip()
            if not _is_empty(val):
                date_total += 1
                if _parses_as_date(val):
                    date_hits += 1

    ffr = filled / total              if total         > 0 else 0.0
    npr = numeric_hits / numeric_total if numeric_total > 0 else 1.0
    dpr = date_hits / date_total       if date_total    > 0 else 1.0
    err = error_rows / len(rows)       if rows          else 0.0

    return ValidationReport(
        row_count=len(rows),
        field_fill_rate=round(ffr, 4),
        numeric_parse_rate=round(npr, 4),
        date_parse_rate=round(dpr, 4),
        error_row_rate=round(err, 4),
        filled_fields=filled,
        total_fields=total,
        numeric_hits=numeric_hits,
        numeric_total=numeric_total,
        date_hits=date_hits,
        date_total=date_total,
    )
