"""
Test the validated multi-record extraction against the SOV test file.

Usage:
    cd backend
    python tests/test_validated_extraction.py
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

from app.services.extraction_service import extract_from_document, LLMUsage  # noqa: E402
from app.services.pdf_service import parse_pdf                               # noqa: E402

GREEN = "\033[92m"
YELLOW = "\033[93m"
RED = "\033[91m"
BOLD = "\033[1m"
RESET = "\033[0m"

SOV_FIELDS = [
    {"name": "Location Number", "description": "Location or property number/ID"},
    {"name": "Address", "description": "Street address of the property"},
    {"name": "City", "description": "City where the property is located"},
    {"name": "State", "description": "State (2-letter code)"},
    {"name": "Zip", "description": "Zip code"},
    {"name": "Construction Type", "description": "Construction type (e.g. frame, masonry, fire resistive)"},
    {"name": "Year Built", "description": "Year the building was constructed"},
    {"name": "Building Value", "description": "Building insured value in dollars"},
    {"name": "BPP Value", "description": "Business personal property value in dollars"},
    {"name": "Total Insured Value", "description": "Total insured value (TIV) in dollars"},
]


async def main() -> None:
    test_file = _BACKEND / "test_files" / "05_prior_year_sov_30_locations.pdf"
    if not test_file.exists():
        print(f"{RED}Test file not found: {test_file}{RESET}")
        sys.exit(1)

    print(f"\n{BOLD}{'=' * 60}{RESET}")
    print(f"{BOLD}  Validated Multi-Record Extraction Test{RESET}")
    print(f"{BOLD}{'=' * 60}{RESET}")
    print(f"  File: {test_file.name}")
    print(f"  Fields: {len(SOV_FIELDS)}")
    print()

    print(f"  Parsing PDF...", end="", flush=True)
    parsed = parse_pdf(str(test_file), test_file.name)
    print(f" {parsed.page_count} pages, {len(parsed.tables)} tables, hint={parsed.doc_type_hint}")
    print(f"  Scanned: {parsed.is_scanned}")
    print()

    usage = LLMUsage()
    t0 = time.perf_counter()
    print(f"  Extracting (validated multi-record)...")
    rows = await extract_from_document(parsed, SOV_FIELDS, usage)
    elapsed = time.perf_counter() - t0

    field_names = [f["name"] for f in SOV_FIELDS]

    print(f"\n{BOLD}  Results{RESET}")
    print(f"  {'─' * 50}")
    print(f"  Rows extracted: {BOLD}{len(rows)}{RESET}")
    print(f"  Time: {elapsed:.1f}s")
    print(f"  Cost: ${usage.cost_usd:.6f}")
    print(f"  Input tokens:  {usage.input_tokens}")
    print(f"  Output tokens: {usage.output_tokens}")
    print()

    error_rows = [r for r in rows if r.get("_error")]
    if error_rows:
        print(f"  {RED}Error rows: {len(error_rows)}{RESET}")
        for r in error_rows:
            print(f"    {r.get('_error')}")
        print()

    filled_count = sum(
        1 for r in rows for fn in field_names
        if r.get(fn) is not None and str(r[fn]).strip().lower() not in {"", "null", "none", "n/a"}
    )
    total_cells = len(rows) * len(field_names)
    ffr = filled_count / total_cells if total_cells else 0
    print(f"  Field fill rate: {ffr:.1%} ({filled_count}/{total_cells})")
    print()

    print(f"  {BOLD}Sample rows:{RESET}")
    for i, row in enumerate(rows[:5]):
        loc = row.get("Location Number", "?")
        addr = row.get("Address", "")
        city = row.get("City", "")
        state = row.get("State", "")
        bldg = row.get("Building Value", "")
        tiv = row.get("Total Insured Value", "")
        print(f"    Loc {loc}: {addr}, {city} {state} | Bldg={bldg} TIV={tiv}")
    if len(rows) > 5:
        print(f"    ... and {len(rows) - 5} more")
    print()

    expected = 30
    if len(rows) == expected:
        print(f"  {GREEN}PASS: Extracted {len(rows)} rows (expected {expected}){RESET}")
    elif abs(len(rows) - expected) <= 2:
        print(f"  {YELLOW}CLOSE: Extracted {len(rows)} rows (expected {expected}){RESET}")
    else:
        print(f"  {RED}FAIL: Extracted {len(rows)} rows (expected {expected}){RESET}")

    print(f"\n{BOLD}{'=' * 60}{RESET}\n")


if __name__ == "__main__":
    asyncio.run(main())
