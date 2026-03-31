"""
Test SOV extraction using EXACT field names from the UI SOV_DEFAULTS.

Usage:
    cd backend
    python tests/test_sov_exact_fields.py [01|02|03|04|05]
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

# EXACT fields from the frontend SOV_DEFAULTS
SOV_FIELDS = [
    {"name": "Loc #", "description": "Extract the location identifier exactly as shown for each schedule row (for example: 1, 01, A1). Keep letters, symbols, and leading zeros exactly as printed."},
    {"name": "Bldg #", "description": "Extract the building number for the location exactly as shown in the schedule. Do not infer or renumber buildings; copy the literal value from the row."},
    {"name": "Location Name", "description": "Extract the site or building name used by underwriting (for example: MB1, North Warehouse). Keep abbreviations and naming conventions exactly as shown."},
    {"name": "Occupancy/Exposure", "description": "Extract the occupancy/exposure classification text exactly as presented (for example: 4 Unit Apartment, Retail Strip, Light Manufacturing). Do not summarize or rewrite."},
    {"name": "Street Address", "description": "Extract the street address line for the insured premises. Keep suite/unit/building details when present, but do not include city/state/zip in this field unless the source combines them into one cell."},
    {"name": "City", "description": "Extract the city for the insured location exactly as listed in the schedule row."},
    {"name": "State", "description": "Extract the state value exactly as shown (postal abbreviation preferred when the document uses it). Do not expand or normalize unless already shown that way."},
    {"name": "Zip", "description": "Extract the ZIP/postal code exactly as shown, including ZIP+4 when present."},
    {"name": "County", "description": "Extract the county value exactly as shown (for example: St Tam, Cook, Orange). Do not expand abbreviations unless the schedule already expands them."},
    {"name": "Construction Type", "description": "Extract the construction class/type used in underwriting (for example: Frame, Joisted Masonry, Non-Combustible). Keep the schedule wording as-is."},
    {"name": "ISO Construction Code", "description": "Extract the ISO construction code exactly as shown (for example: F, JM, NC, 1-6). Preserve code formatting and symbols."},
    {"name": "Building Values", "description": "Extract the building limit/value amount for the row. Keep the currency format shown in the source unless the source is plain numeric."},
    {"name": "Contents/BPP Values", "description": "Extract the contents/business personal property value for the row. Use the exact value shown for that coverage bucket."},
    {"name": "Business Income Values", "description": "Extract the business income/time element value exactly as shown for the location row."},
    {"name": "Machinery & Equipment Values", "description": "Extract the machinery and equipment value exactly as shown for the row. Do not merge this into contents unless the source itself combines them."},
    {"name": "Other Property Values", "description": "Extract the other property value exactly as presented for the row."},
    {"name": "Total Insurable Value (TIV)", "description": "Extract the explicit total insurable value shown for the row. Only calculate from component values if the total is truly absent and all needed components are clearly present in the same row."},
    {"name": "Square Ft.", "description": "Extract the insured area in square feet exactly as shown. Keep separators and decimals when present."},
    {"name": "Cost Per Square Ft.", "description": "Extract cost per square foot exactly as shown (for example: $89, 89.25). Keep currency symbol if present in the schedule."},
    {"name": "Year Built", "description": "Extract original year built for the building row. Return the year value shown in the schedule."},
    {"name": "Roof Update", "description": "Extract the roof update year or indicator exactly as shown for the location. Map from the row or column whose label expresses roof age or replacement (for example labels containing roof and year or update)."},
    {"name": "Wiring Update", "description": "Extract the wiring update year or indicator exactly as shown for the location."},
    {"name": "HVAC Update", "description": "Extract the HVAC update year or indicator exactly as shown for the location."},
    {"name": "Plumbing Update", "description": "Extract the plumbing update year or indicator exactly as shown for the location."},
    {"name": "% Occupied", "description": "Extract occupancy percentage exactly as shown (for example: 100%, 85%). Keep percent signs and formatting."},
    {"name": "Sprinklered", "description": "Extract sprinkler status exactly as shown (for example: Y/N, Yes/No, Partial). Do not reinterpret unless the value is obviously equivalent in the same row."},
    {"name": "% Sprinklered", "description": "Extract sprinkler percentage exactly as shown (for example: 0%, 50%, 100%)."},
    {"name": "ISO Protection Class", "description": "Extract ISO protection class exactly as shown in the row (for example: 2, 3/9X). Keep slashes, letters, and symbols. If the schedule uses a district or zone label instead of a numeric class, copy that printed text."},
    {"name": "Fire Alarm", "description": "Extract fire alarm indicator exactly as shown (for example: Y/N, Central Station, Local). Map from the alarm system or security alarm row/column when that is how the document labels it."},
    {"name": "Burglar Alarm", "description": "Extract burglar alarm indicator exactly as shown (for example: Y/N, Central Station, Local)."},
    {"name": "Smoke Detectors", "description": "Extract smoke detector indicator/status exactly as shown for the row."},
    {"name": "# of Stories", "description": "Extract number of stories exactly as shown (for example: 1, 2, 1.5)."},
    {"name": "# of Units", "description": "Extract number of units exactly as shown in the row."},
    {"name": "Type of Wiring", "description": "Extract type of wiring code or text exactly as shown (for example: C, Copper, Aluminum)."},
    {"name": "% Subsidized", "description": "Extract subsidized occupancy percentage exactly as shown, including percent sign when present."},
    {"name": "% Student Housing", "description": "Extract student housing percentage exactly as shown, including percent sign when present."},
    {"name": "% Elderly Housing", "description": "Extract elderly housing percentage exactly as shown, including percent sign when present."},
    {"name": "Roof Type/Frame", "description": "Extract roof type/frame value exactly as shown (for example: Frame, Truss, Metal Deck)."},
    {"name": "Roof Shape", "description": "Extract roof shape code/text exactly as shown (for example: H, Gable, Flat)."},
    {"name": "Flood Zone", "description": "Extract FEMA flood zone exactly as shown (for example: X, AE, VE, A). Preserve code formatting."},
    {"name": "EQ Zone", "description": "Extract earthquake zone code/classification exactly as shown in the schedule row (for example: 0, 1, 2, A, B, C, X). Copy the literal code from the document and do not translate, interpret, or recode it."},
    {"name": "Distance to Salt Water/Coast", "description": "Extract the distance-to-coast value exactly as shown, including unit/format if present (for example: 60, 60 mi, 2.5 miles)."},
    {"name": "Property Owned or Managed", "description": "Extract owned/managed indicator exactly as shown (for example: O, M, Owned, Managed)."},
    {"name": "Bldg Maintenance", "description": "Extract building maintenance indicator/class exactly as shown (for example: G, Average, Good)."},
    {"name": "Basement", "description": "Extract basement indicator exactly as shown (for example: Y/N, None, Partial, Full)."},
    {"name": "Predominant Exterior Wall / Cladding", "description": "Extract predominant exterior wall/cladding material exactly as shown (for example: Wood Siding, Brick Veneer, EIFS)."},
]

TEST_FILES = {
    "01": (_BACKEND / "test_files" / "01_property_appraisal_report_25_buildings.pdf", 25),
    "02": (_BACKEND / "test_files" / "02_carrier_property_schedule_50_locations.pdf", 50),
    "03": (_BACKEND / "test_files" / "03_package_policy_dec_pages_15_locations.pdf", 15),
    "04": (_BACKEND / "test_files" / "04_vehicle_schedule_35_vehicles.pdf", 35),
    "05": (_BACKEND / "test_files" / "05_prior_year_sov_30_locations.pdf", 30),
}


async def test_file(file_key: str) -> None:
    path, expected = TEST_FILES[file_key]
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

    filled_count = sum(
        1 for r in rows for fn in field_names
        if r.get(fn) is not None and str(r[fn]).strip().lower() not in {"", "null", "none", "n/a", "-"}
    )
    total_cells = len(rows) * len(field_names)
    ffr = filled_count / total_cells if total_cells else 0
    print(f"  Field fill rate: {ffr:.1%} ({filled_count}/{total_cells})")

    print(f"\n  {BOLD}Per-field fill rates:{RESET}")
    for fn in field_names:
        filled = sum(1 for r in rows if r.get(fn) is not None and str(r.get(fn, "")).strip().lower() not in {"", "null", "none", "n/a", "-"})
        pct = filled / len(rows) if rows else 0
        color = GREEN if pct >= 0.8 else (YELLOW if pct >= 0.4 else RED)
        print(f"    {color}{fn}: {pct:.0%} ({filled}/{len(rows)}){RESET}")

    print(f"\n  {BOLD}First 3 rows:{RESET}")
    for i, row in enumerate(rows[:3]):
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
    parser.add_argument("files", nargs="*", default=["01"], help="File keys to test (01-05).")
    args = parser.parse_args()

    for key in args.files:
        if key not in TEST_FILES:
            print(f"{RED}Unknown file key: {key}{RESET}")
            continue
        await test_file(key)

    print(f"\n{BOLD}Done.{RESET}\n")


if __name__ == "__main__":
    asyncio.run(main())
