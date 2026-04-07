"""
Comprehensive 20-combination SOV extraction test.

Covers all 15 non-empty subsets of {06, 07, 08, 09} with frontend_defaults fields,
plus 5 key multi-doc combos with abbreviated fields for robustness — 20 total.

Replicates the EXACT production pipeline from job_processor.py:
  - Single-doc: extract_from_document(..., force_sov=True) — OCR handled internally
  - Multi-doc:  OCR each file, replace content_text, combine, then extract

Usage:
    cd backend
    python tests/test_sov_20_combinations.py
"""
from __future__ import annotations

import asyncio
import sys
import time
from pathlib import Path
from typing import Any, Dict, List

_BACKEND = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_BACKEND))

import os
try:
    from dotenv import load_dotenv
    load_dotenv(_BACKEND / ".env")
except ImportError:
    pass
os.environ.pop("STRIPE_PRODUCT_ID", None)

from app.config import settings
from app.services.extraction import extract_from_document, LLMUsage
from app.services.pdf_service import parse_pdf, combine_parsed_documents
from app.services.ocr_service import run_mistral_ocr
from app.services.sov.pipeline import _build_sections_from_ocr_pages

GREEN  = "\033[92m"
YELLOW = "\033[93m"
RED    = "\033[91m"
BOLD   = "\033[1m"
DIM    = "\033[2m"
RESET  = "\033[0m"
CYAN   = "\033[96m"

# ──────────────────────────────────────────────────────────────────────────────
# Files
# ──────────────────────────────────────────────────────────────────────────────

FILES = {
    "06": _BACKEND / "test_files" / "06_full_sov_20_locations.pdf",
    "07": _BACKEND / "test_files" / "07_customer_intake_form.pdf",
    "08": _BACKEND / "test_files" / "08_appraisal_supplement.pdf",
    "09": _BACKEND / "test_files" / "09_email_thread_updates.pdf",
}

# Expected row count for a given set of file keys
def expected_rows(keys: List[str]) -> int:
    return 20 if "06" in keys else 8


# ──────────────────────────────────────────────────────────────────────────────
# Field sets
# ──────────────────────────────────────────────────────────────────────────────

FRONTEND_DEFAULTS = [
    {"name": "Loc #",                       "description": "Location identifier (e.g. 1, 01, A1). Copy exactly."},
    {"name": "Bldg #",                      "description": "Building number — copy exactly from the row."},
    {"name": "Location Name",               "description": "Site or building name used by underwriting."},
    {"name": "Occupancy/Exposure",          "description": "Occupancy/exposure classification text exactly as presented."},
    {"name": "Street Address",              "description": "Street address line for the insured premises."},
    {"name": "City",                        "description": "City for the insured location."},
    {"name": "State",                       "description": "State (postal abbreviation preferred)."},
    {"name": "Zip",                         "description": "ZIP/postal code exactly as shown."},
    {"name": "County",                      "description": "County value exactly as shown."},
    {"name": "Construction Type",           "description": "Construction class/type (e.g. Frame, Joisted Masonry)."},
    {"name": "ISO Construction Code",       "description": "ISO construction code exactly as shown (e.g. F, JM, NC)."},
    {"name": "Building Values",             "description": "Building limit/value amount for the row."},
    {"name": "Contents/BPP Values",         "description": "Contents/BPP value for the row."},
    {"name": "Business Income Values",      "description": "Business income/time element value."},
    {"name": "Machinery & Equipment Values","description": "Machinery and equipment value."},
    {"name": "Other Property Values",       "description": "Other property value."},
    {"name": "Total Insurable Value (TIV)", "description": "Total insurable value. Map 'TIV' column directly."},
    {"name": "Square Ft.",                  "description": "Insured area in square feet."},
    {"name": "Cost Per Square Ft.",         "description": "Cost per square foot (e.g. $89, 89.25)."},
    {"name": "Year Built",                  "description": "Original year built for the building row."},
    {"name": "Roof Update",                 "description": "Roof update year or indicator."},
    {"name": "Wiring Update",               "description": "Wiring update year or indicator."},
    {"name": "HVAC Update",                 "description": "HVAC update year or indicator."},
    {"name": "Plumbing Update",             "description": "Plumbing update year or indicator."},
    {"name": "% Occupied",                  "description": "Occupancy percentage (e.g. 100%, 85%)."},
    {"name": "Sprinklered",                 "description": "Sprinkler status (e.g. Y/N, Yes/No, Partial)."},
    {"name": "% Sprinklered",               "description": "Sprinkler percentage (e.g. 0%, 50%, 100%)."},
    {"name": "ISO Protection Class",        "description": "ISO protection class (e.g. 2, 3/9X)."},
    {"name": "Fire Alarm",                  "description": "Fire alarm indicator (e.g. Y/N, Central Station)."},
    {"name": "Burglar Alarm",               "description": "Burglar alarm indicator (e.g. Y/N, Central Station)."},
    {"name": "Smoke Detectors",             "description": "Smoke detector indicator/status."},
    {"name": "# of Stories",               "description": "Number of stories (e.g. 1, 2, 1.5)."},
    {"name": "# of Units",                 "description": "Number of units."},
    {"name": "Type of Wiring",             "description": "Type of wiring code or text (e.g. C, Copper, Aluminum)."},
    {"name": "% Subsidized",               "description": "Subsidized occupancy percentage."},
    {"name": "% Student Housing",          "description": "Student housing percentage."},
    {"name": "% Elderly Housing",          "description": "Elderly housing percentage."},
    {"name": "Roof Type/Frame",            "description": "Roof type/frame value (e.g. Frame, Truss, Metal Deck)."},
    {"name": "Roof Shape",                 "description": "Roof shape code/text (e.g. H, Gable, Flat)."},
    {"name": "Flood Zone",                 "description": "FEMA flood zone (e.g. X, AE, VE, A)."},
    {"name": "EQ Zone",                    "description": "Earthquake zone code/classification (e.g. 0, 1, A, B)."},
    {"name": "Distance to Salt Water/Coast","description": "Distance-to-coast value with unit (e.g. 60 mi)."},
    {"name": "Property Owned or Managed",  "description": "Owned/managed indicator (e.g. O, M, Owned, Managed)."},
    {"name": "Bldg Maintenance",           "description": "Building maintenance indicator/class (e.g. G, Average, Good)."},
    {"name": "Basement",                   "description": "Basement indicator (e.g. Y/N, None, Partial, Full)."},
    {"name": "Predominant Exterior Wall / Cladding", "description": "Exterior wall/cladding material."},
]

ABBREVIATED = [
    {"name": "Loc #",         "description": "Location or property number/ID"},
    {"name": "Bldg #",        "description": "Building number"},
    {"name": "Street Address","description": "Street address of the property"},
    {"name": "City",          "description": "City"},
    {"name": "State",         "description": "State (2-letter code)"},
    {"name": "Zip",           "description": "Zip code"},
    {"name": "Construction Type", "description": "Construction type (e.g. frame, masonry)"},
    {"name": "Year Built",    "description": "Year the building was constructed"},
    {"name": "Building Values","description": "Building insured value in dollars"},
    {"name": "Contents/BPP Values", "description": "Contents or BPP value in dollars"},
    {"name": "Total Insurable Value (TIV)", "description": "Total insured value in dollars"},
]

FIELD_SETS = {
    "frontend_defaults": FRONTEND_DEFAULTS,
    "abbreviated":       ABBREVIATED,
}

_EMPTY_VALUES = {"", "null", "none", "n/a", "na", "-", "—", "unknown", "not found", "not available"}

# ──────────────────────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────────────────────

def is_filled(v: Any) -> bool:
    if v is None:
        return False
    return str(v).strip().lower() not in _EMPTY_VALUES


def fill_rate(rows: List[Dict], field_names: List[str]) -> float:
    total = len(rows) * len(field_names)
    if total == 0:
        return 0.0
    return sum(1 for r in rows for fn in field_names if is_filled(r.get(fn))) / total


def find_duplicates(rows: List[Dict]) -> List[str]:
    """Return duplicate Loc # values."""
    seen: Dict[str, int] = {}
    for r in rows:
        loc = str(r.get("Loc #", "") or "").strip()
        if loc:
            seen[loc] = seen.get(loc, 0) + 1
    return [k for k, v in seen.items() if v > 1]


def check_garbled(rows: List[Dict], field_names: List[str]) -> List[str]:
    """Look for known PyMuPDF OCR artifacts in text fields."""
    BAD_PATTERNS = ["Dban", "Maysdby", "Harb or", "St ree t"]
    issues: List[str] = []
    for r in rows:
        for fn in field_names:
            val = str(r.get(fn) or "")
            for pat in BAD_PATTERNS:
                if pat.lower() in val.lower():
                    issues.append(f"Row Loc#{r.get('Loc #','?')} field '{fn}': {val!r}")
    return issues


# ──────────────────────────────────────────────────────────────────────────────
# OCR enrichment (mirrors job_processor._parse_only)
# ──────────────────────────────────────────────────────────────────────────────

_NO_OCR_EXTS  = {".eml", ".emlx", ".msg", ".html", ".htm"}
_SHEET_EXTS   = {".xlsx", ".xls", ".xlsm", ".csv"}


async def parse_with_ocr(file_path: str, filename: str) -> Any:
    """Parse + replace content_text with Mistral OCR, exactly like job_processor._parse_only."""
    parsed = await asyncio.to_thread(parse_pdf, file_path, filename)

    fname_lower = filename.lower()
    can_ocr = (
        settings.mistral_api_key
        and not any(fname_lower.endswith(e) for e in _NO_OCR_EXTS)
        and not any(fname_lower.endswith(e) for e in _SHEET_EXTS)
    )
    if can_ocr:
        try:
            ocr_res = await run_mistral_ocr(file_path, settings.mistral_api_key, max_pages=50)
            sections = _build_sections_from_ocr_pages(ocr_res.pages)
            ocr_text = "\n\n".join(s.content for s in sections).strip()
            if ocr_text:
                parsed.content_text = ocr_text
                print(f"    [OCR] {filename}: {ocr_res.page_count} pages → {len(ocr_text):,} chars")
        except Exception as exc:
            print(f"    {YELLOW}[OCR] {filename} failed: {exc} — using liteparse{RESET}")
    return parsed


# ──────────────────────────────────────────────────────────────────────────────
# One combination run
# ──────────────────────────────────────────────────────────────────────────────

async def run_combination(
    test_id: str,
    keys: List[str],
    field_set_name: str,
) -> Dict[str, Any]:
    fields = FIELD_SETS[field_set_name]
    field_names = [f["name"] for f in fields]
    exp = expected_rows(keys)
    has_primary = "06" in keys
    file_label = "+".join(keys)

    print(f"\n{BOLD}{'═' * 72}{RESET}")
    print(f"{BOLD}  {test_id}  [{file_label}]  fields={field_set_name}  expect={exp}{RESET}")
    print(f"{BOLD}{'═' * 72}{RESET}")

    # Validate files exist
    for k in keys:
        if not FILES[k].exists():
            print(f"  {RED}MISSING: {FILES[k]}{RESET}")
            return {"id": test_id, "keys": keys, "pass": False, "error": "file missing"}

    usage = LLMUsage()
    t0 = time.perf_counter()

    try:
        if len(keys) == 1:
            # Single doc: let pipeline.py handle OCR routing internally
            k = keys[0]
            parsed = await asyncio.to_thread(parse_pdf, str(FILES[k]), FILES[k].name)
            print(f"  Parsed: pages={parsed.page_count} tables={len(parsed.tables)} hint={parsed.doc_type_hint} scanned={parsed.is_scanned}")
            rows = await extract_from_document(parsed, fields, usage, force_sov=True)

        else:
            # Multi-doc: OCR each file first, then combine (mirrors job_processor)
            parseds = []
            for k in keys:
                print(f"  Parsing + OCR: {FILES[k].name}")
                p = await parse_with_ocr(str(FILES[k]), FILES[k].name)
                print(f"    → pages={p.page_count} tables={len(p.tables)} hint={p.doc_type_hint} content_chars={len(p.content_text):,}")
                parseds.append(p)

            combined = combine_parsed_documents(parseds)
            print(f"  Combined: {len(keys)} docs → pages={combined.page_count} tables={len(combined.tables)} content_chars={len(combined.content_text):,}")
            rows = await extract_from_document(combined, fields, usage, force_sov=True)

    except Exception as exc:
        elapsed = time.perf_counter() - t0
        print(f"  {RED}EXCEPTION: {exc}{RESET}")
        return {"id": test_id, "keys": keys, "pass": False, "error": str(exc), "elapsed_s": elapsed}

    elapsed = time.perf_counter() - t0
    real_rows = [r for r in rows if not r.get("_error")]
    error_rows = [r for r in rows if r.get("_error")]
    fr = fill_rate(real_rows, field_names)

    # ── Row count ──────────────────────────────────────────────────────────────
    count_ok = abs(len(real_rows) - exp) <= max(2, int(exp * 0.15))
    # Fill threshold: lower for supplemental-only combos (no financial data)
    fill_threshold = 0.50 if has_primary else 0.25
    fill_ok = fr >= fill_threshold
    passed = count_ok and fill_ok

    print(f"\n  Rows: {BOLD}{len(real_rows)}{RESET}/{exp}  {'✓' if count_ok else '✗'}")
    print(f"  Fill: {fr:.1%}  (threshold≥{fill_threshold:.0%})  {'✓' if fill_ok else '✗'}")
    if error_rows:
        print(f"  {RED}Error rows: {len(error_rows)}{RESET}")
    print(f"  Time: {elapsed:.1f}s   Cost: ${usage.cost_usd:.6f}")

    # ── Duplicate check ────────────────────────────────────────────────────────
    dups = find_duplicates(real_rows)
    if dups:
        print(f"  {RED}DUPLICATES: {dups}{RESET}")
    else:
        print(f"  {GREEN}No duplicate Loc # values{RESET}")

    # ── Garbled text check ─────────────────────────────────────────────────────
    garbled = check_garbled(real_rows, field_names)
    if garbled:
        print(f"  {RED}GARBLED TEXT DETECTED:{RESET}")
        for g in garbled[:5]:
            print(f"    {RED}{g}{RESET}")
    else:
        print(f"  {GREEN}No garbled text artifacts{RESET}")

    # ── Per-field fill breakdown ───────────────────────────────────────────────
    print(f"\n  {DIM}Per-field fill rate:{RESET}")
    for fn in field_names:
        filled = sum(1 for r in real_rows if is_filled(r.get(fn)))
        pct = filled / len(real_rows) if real_rows else 0.0
        bar_filled = "█" * int(pct * 12)
        bar_empty  = "░" * (12 - int(pct * 12))
        color = GREEN if pct >= 0.70 else (YELLOW if pct >= 0.40 else RED)
        print(f"    {color}{bar_filled}{bar_empty} {pct:5.0%}  {fn}{RESET}")

    # ── Sample rows ───────────────────────────────────────────────────────────
    if real_rows:
        print(f"\n  {DIM}Sample rows (first 3):{RESET}")
        core_fields = ["Loc #", "Street Address", "City", "State", "Construction Type",
                       "Building Values", "Total Insurable Value (TIV)", "Year Built"]
        for i, row in enumerate(real_rows[:3]):
            vals = {fn: row.get(fn, "—") for fn in core_fields if fn in field_names}
            print(f"    Row {i+1}: {vals}")

        # Show rows 8-12 if 20-row case to verify middle of table
        if exp == 20 and len(real_rows) >= 12:
            print(f"\n  {DIM}Sample rows (8-12, mid-table check):{RESET}")
            for i, row in enumerate(real_rows[7:12]):
                vals = {fn: row.get(fn, "—") for fn in core_fields if fn in field_names}
                print(f"    Row {i+8}: {vals}")

        # Show last 3 rows
        if len(real_rows) > 3:
            print(f"\n  {DIM}Sample rows (last 3):{RESET}")
            for i, row in enumerate(real_rows[-3:]):
                vals = {fn: row.get(fn, "—") for fn in core_fields if fn in field_names}
                print(f"    Row {len(real_rows)-2+i}: {vals}")

    # ── Verdict ────────────────────────────────────────────────────────────────
    print()
    if passed and not dups and not garbled:
        verdict_str = f"{GREEN}PASS{RESET}"
    elif passed and not dups:
        verdict_str = f"{YELLOW}PASS (garbled text warning){RESET}"
    elif count_ok and dups:
        verdict_str = f"{RED}FAIL — duplicate rows{RESET}"
    elif not count_ok:
        verdict_str = f"{RED}FAIL — rows={len(real_rows)} expected={exp}{RESET}"
    else:
        verdict_str = f"{RED}FAIL — fill={fr:.1%} < {fill_threshold:.0%}{RESET}"

    print(f"  Verdict: {verdict_str}  locs={sorted(str(r.get('Loc #','')).strip() for r in real_rows[:3])} t={elapsed:.0f}s ${usage.cost_usd:.3f}")

    return {
        "id": test_id,
        "keys": keys,
        "field_set": field_set_name,
        "rows": len(real_rows),
        "expected": exp,
        "fill_rate": fr,
        "elapsed_s": elapsed,
        "cost": usage.cost_usd,
        "count_ok": count_ok,
        "fill_ok": fill_ok,
        "dups": dups,
        "garbled": garbled,
        "pass": passed and not dups and not garbled,
    }


# ──────────────────────────────────────────────────────────────────────────────
# 20 test combinations
# ──────────────────────────────────────────────────────────────────────────────

COMBINATIONS: List[tuple[str, List[str], str]] = [
    # ── All 15 subsets of {06,07,08,09} — frontend_defaults ─────────────────
    # Single-doc (4)
    ("C01", ["06"],             "frontend_defaults"),
    ("C02", ["07"],             "frontend_defaults"),
    ("C03", ["08"],             "frontend_defaults"),
    ("C04", ["09"],             "frontend_defaults"),
    # 2-doc (6)
    ("C05", ["06", "07"],       "frontend_defaults"),
    ("C06", ["06", "08"],       "frontend_defaults"),
    ("C07", ["06", "09"],       "frontend_defaults"),
    ("C08", ["07", "08"],       "frontend_defaults"),
    ("C09", ["07", "09"],       "frontend_defaults"),
    ("C10", ["08", "09"],       "frontend_defaults"),
    # 3-doc (4)
    ("C11", ["06", "07", "08"], "frontend_defaults"),
    ("C12", ["06", "07", "09"], "frontend_defaults"),
    ("C13", ["06", "08", "09"], "frontend_defaults"),
    ("C14", ["07", "08", "09"], "frontend_defaults"),
    # 4-doc (1)
    ("C15", ["06", "07", "08", "09"], "frontend_defaults"),
    # ── 5 key combos with abbreviated field set ───────────────────────────────
    ("C16", ["06"],             "abbreviated"),
    ("C17", ["06", "07"],       "abbreviated"),
    ("C18", ["06", "07", "08"], "abbreviated"),
    ("C19", ["06", "07", "08", "09"], "abbreviated"),
    ("C20", ["06", "08", "09"], "abbreviated"),
]


async def main() -> None:
    # Check required files exist
    print(f"\n{BOLD}{'█' * 72}{RESET}")
    print(f"{BOLD}  SOV 20-Combination Test Suite{RESET}")
    print(f"  Combinations: {len(COMBINATIONS)}")
    print(f"  Mistral OCR: {'✓ available' if settings.mistral_api_key else '✗ NOT SET — multi-doc will use liteparse'}")
    print(f"{BOLD}{'█' * 72}{RESET}")

    for k, path in FILES.items():
        status = "✓" if path.exists() else "✗ MISSING"
        print(f"  File {k}: {path.name}  {status}")

    results: List[Dict[str, Any]] = []
    for test_id, keys, fset in COMBINATIONS:
        result = await run_combination(test_id, keys, fset)
        results.append(result)

    # ──────────────────────────────────────────────────────────────────────────
    # Final summary
    # ──────────────────────────────────────────────────────────────────────────
    print(f"\n\n{BOLD}{'█' * 72}{RESET}")
    print(f"{BOLD}  FINAL RESULTS{RESET}")
    print(f"{BOLD}{'█' * 72}{RESET}")

    passed = [r for r in results if r.get("pass")]
    failed = [r for r in results if not r.get("pass") and not r.get("error")]
    errored = [r for r in results if r.get("error")]

    # Expected-low-fill combos (no 06, standalone supplements) are noted but not penalized
    expected_low = [r for r in results if "06" not in r.get("keys", [])]

    for r in results:
        if r.get("error"):
            color = RED;   sym = "✗ ERR "
        elif r.get("pass"):
            color = GREEN; sym = "PASS "
        elif "06" not in r.get("keys", []):
            color = YELLOW; sym = "LOW  "  # expected low fill for supplement-only
        else:
            color = RED;   sym = "FAIL "

        keys_str  = "+".join(r.get("keys", []))
        fset_str  = "full" if r.get("field_set") == "frontend_defaults" else "abbr"
        rows_str  = f"{r.get('rows','?')}/{r.get('expected','?')}"
        fill_str  = f"{r.get('fill_rate', 0):.1%}"
        dups_str  = f" DUPS:{r.get('dups')}" if r.get("dups") else ""
        garb_str  = f" GARB:{len(r.get('garbled',[]))}" if r.get("garbled") else ""
        t_str     = f"{r.get('elapsed_s', 0):.0f}s"
        cost_str  = f"${r.get('cost', 0):.3f}"
        print(f"  {color}{sym}{RESET} {r.get('id','?'):4s}  [{keys_str:<12s}] {fset_str:4s}  rows={rows_str:7s} fill={fill_str:6s} {t_str:5s} {cost_str:8s}{dups_str}{garb_str}")

    total_cost = sum(r.get("cost", 0) for r in results)
    total_time = sum(r.get("elapsed_s", 0) for r in results)
    primary_results = [r for r in results if "06" in r.get("keys", [])]
    primary_passed  = [r for r in primary_results if r.get("pass")]

    print(f"\n  {BOLD}Primary-SOV combos (with 06): {len(primary_passed)}/{len(primary_results)} passed{RESET}")
    print(f"  All 20 tests: {len(passed)}/{len(results)} passed")
    print(f"  Expected-low (supplement-only, no 06): {len(expected_low)} combos — lower threshold")
    print(f"  Total time: {total_time:.0f}s   Total cost: ${total_cost:.4f}")

    if errored:
        print(f"\n  {RED}ERRORS:{RESET}")
        for r in errored:
            print(f"    {r['id']}: {r.get('error')}")

    print()


if __name__ == "__main__":
    asyncio.run(main())
