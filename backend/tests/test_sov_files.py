"""
Test SOV extraction against files 1 and 4 (and other combinations).

Usage:
    cd backend
    python tests/test_sov_files.py
"""
from __future__ import annotations

import asyncio
import sys
import time
from pathlib import Path

_BACKEND = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_BACKEND))

import os
try:
    from dotenv import load_dotenv
    load_dotenv(_BACKEND / ".env")
except ImportError:
    pass
os.environ.pop("STRIPE_PRODUCT_ID", None)

from app.services.extraction import extract_from_document, LLMUsage
from app.services.pdf_service import parse_pdf

GREEN = "\033[92m"
YELLOW = "\033[93m"
RED = "\033[91m"
BOLD = "\033[1m"
RESET = "\033[0m"

# Standard SOV fields matching what the UI shows
SOV_FIELDS = [
    {"name": "Location Number", "description": "Location or property number/ID"},
    {"name": "Address", "description": "Street address of the property"},
    {"name": "City", "description": "City where the property is located"},
    {"name": "State", "description": "State (2-letter code)"},
    {"name": "Zip", "description": "Zip code"},
    {"name": "Protection Class", "description": "Fire protection class (e.g. 1-10 or district name)"},
    {"name": "Construction Type", "description": "Construction type (e.g. frame, masonry, fire resistive)"},
    {"name": "Year Built", "description": "Year the building was constructed"},
    {"name": "Building Value", "description": "Building insured value in dollars"},
    {"name": "Contents / BPP Value", "description": "Contents or Business Personal Property value in dollars"},
    {"name": "Business Income Value", "description": "Business income or loss of rents value in dollars"},
    {"name": "Total Insured Value", "description": "Total insured value (TIV) in dollars"},
    {"name": "Valuation", "description": "Valuation basis (e.g. RCV, ACV, Agreed Value)"},
]

TEST_FILES = {
    "01": _BACKEND / "test_files" / "01_property_appraisal_report_25_buildings.pdf",
    "02": _BACKEND / "test_files" / "02_carrier_property_schedule_50_locations.pdf",
    "03": _BACKEND / "test_files" / "03_package_policy_dec_pages_15_locations.pdf",
    "04": _BACKEND / "test_files" / "04_vehicle_schedule_35_vehicles.pdf",
    "05": _BACKEND / "test_files" / "05_prior_year_sov_30_locations.pdf",
}

EXPECTED_COUNTS = {
    "01": 25,
    "02": 50,
    "03": 15,
    "04": 35,
    "05": 30,
}


async def test_file(file_key: str) -> None:
    path = TEST_FILES[file_key]
    expected = EXPECTED_COUNTS[file_key]
    if not path.exists():
        print(f"{RED}File not found: {path}{RESET}")
        return

    print(f"\n{BOLD}{'=' * 70}{RESET}")
    print(f"{BOLD}  File {file_key}: {path.name}{RESET}")
    print(f"{BOLD}{'=' * 70}{RESET}")

    print(f"  Parsing PDF...", end="", flush=True)
    parsed = parse_pdf(str(path), path.name)
    print(f" {parsed.page_count} pages, {len(parsed.tables)} tables, hint={parsed.doc_type_hint}, scanned={parsed.is_scanned}")

    usage = LLMUsage()
    t0 = time.perf_counter()
    print(f"  Extracting...", flush=True)
    rows = await extract_from_document(parsed, SOV_FIELDS, usage)
    elapsed = time.perf_counter() - t0

    field_names = [f["name"] for f in SOV_FIELDS]

    print(f"\n  Rows extracted: {BOLD}{len(rows)}{RESET}  (expected {expected})")
    print(f"  Time: {elapsed:.1f}s  Cost: ${usage.cost_usd:.6f}")

    error_rows = [r for r in rows if r.get("_error")]
    if error_rows:
        print(f"  {RED}Error rows: {len(error_rows)}{RESET}")

    filled_count = sum(
        1 for r in rows for fn in field_names
        if r.get(fn) is not None and str(r[fn]).strip().lower() not in {"", "null", "none", "n/a", "-"}
    )
    total_cells = len(rows) * len(field_names)
    ffr = filled_count / total_cells if total_cells else 0
    print(f"  Field fill rate: {ffr:.1%} ({filled_count}/{total_cells})")

    # Per-field fill rates to identify which fields are empty
    print(f"\n  {BOLD}Per-field fill rates:{RESET}")
    for fn in field_names:
        filled = sum(1 for r in rows if r.get(fn) is not None and str(r.get(fn, "")).strip().lower() not in {"", "null", "none", "n/a", "-"})
        pct = filled / len(rows) if rows else 0
        color = GREEN if pct >= 0.8 else (YELLOW if pct >= 0.4 else RED)
        print(f"    {color}{fn}: {pct:.0%} ({filled}/{len(rows)}){RESET}")

    print(f"\n  {BOLD}First 5 rows:{RESET}")
    for i, row in enumerate(rows[:5]):
        vals = {fn: row.get(fn, "-") for fn in field_names}
        print(f"    Row {i+1}: {vals}")

    if len(rows) == expected:
        print(f"\n  {GREEN}PASS: {len(rows)} rows (expected {expected}){RESET}")
    elif abs(len(rows) - expected) <= 3:
        print(f"\n  {YELLOW}CLOSE: {len(rows)} rows (expected {expected}){RESET}")
    else:
        print(f"\n  {RED}FAIL: {len(rows)} rows (expected {expected}){RESET}")


async def main() -> None:
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("files", nargs="*", default=["01", "04"], help="File keys to test (01-05). Default: 01 04")
    args = parser.parse_args()

    for key in args.files:
        if key not in TEST_FILES:
            print(f"{RED}Unknown file key: {key}. Valid keys: {list(TEST_FILES.keys())}{RESET}")
            continue
        await test_file(key)

    print(f"\n{BOLD}Done.{RESET}\n")


if __name__ == "__main__":
    asyncio.run(main())
