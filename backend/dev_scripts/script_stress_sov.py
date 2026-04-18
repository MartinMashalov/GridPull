"""
Stress / adversarial SOV tests — try to break the extraction.

Tests:
  - Weird/unconventional field names
  - Very few fields (2-3)
  - Huge field set (25+ fields)
  - Fields that don't exist in the document
  - Mix of real + fake fields
  - Duplicate field names
  - Unicode / special chars in field names
  - Instructions that conflict with field descriptions
  - Empty instructions string
  - Very long instructions
  - Documents with no schedule data forced through SOV
  - Spreadsheet output with edge-case data (nulls, long strings, special chars)
"""
import asyncio, sys, os, time, json, traceback
sys.path.insert(0, os.path.dirname(__file__))
sys.stdout.reconfigure(line_buffering=True)

import logging
logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(name)s: %(message)s")
logging.getLogger("httpx").setLevel(logging.ERROR)
logging.getLogger("httpcore").setLevel(logging.ERROR)
logging.getLogger("openai").setLevel(logging.ERROR)

from app.config import settings
settings.mistral_api_key = ""  # skip OCR to keep tests fast

from app.services.pdf_service import parse_pdf
from app.services.extraction import extract_from_document, LLMUsage
from app.services.spreadsheet_service import (
    generate_excel_bytes, generate_csv_bytes, read_headers_from_bytes,
    update_excel_baseline_bytes,
)

TEST_DOCS = "/Users/martinmashalov/Downloads/GridPull/test_documents"
EMPTY = {"", "null", "none", "n/a", "na", "-", "—", "unknown", "not found", "not available"}
results = []

def is_filled(val):
    if val is None: return False
    return str(val).strip().lower() not in EMPTY

async def run_test(tid, label, path, fields, *, instructions="", force_sov=True, expect_crash=False, min_rows=1):
    fn = [f["name"] for f in fields]
    print(f"\n[T{tid:02d}] {label}")
    t0 = time.time()
    try:
        doc = await asyncio.to_thread(parse_pdf, path, os.path.basename(path))
        usage = LLMUsage()
        rows = await extract_from_document(doc, fields, usage, instructions, force_sov=force_sov)
        elapsed = time.time() - t0
        total = len(rows) * len(fn)
        filled = sum(1 for r in rows for f in fn if is_filled(r.get(f)))
        pct = filled / total * 100 if total else 0

        # Validate spreadsheet generation doesn't crash
        xlsx_ok = csv_ok = True
        try:
            xlsx = generate_excel_bytes(rows, fn)
            read_headers_from_bytes(xlsx, "xlsx")
        except Exception as e:
            xlsx_ok = False
            print(f"  XLSX CRASH: {e}")
        try:
            csv_b = generate_csv_bytes(rows, fn)
            read_headers_from_bytes(csv_b, "csv")
        except Exception as e:
            csv_ok = False
            print(f"  CSV CRASH: {e}")

        status = "PASS" if len(rows) >= min_rows and xlsx_ok and csv_ok else "FAIL"
        print(f"  {status}: {len(rows)} rows, {pct:.0f}% fill, ${usage.cost_usd:.4f}, {elapsed:.1f}s xlsx={'ok' if xlsx_ok else 'FAIL'} csv={'ok' if csv_ok else 'FAIL'}")
        if rows:
            sample = {k: str(v)[:40] for k, v in rows[0].items() if k not in ("_source_file","_error") and is_filled(v)}
            print(f"  Sample: {json.dumps(sample, default=str)[:200]}")
        results.append({"id": tid, "label": label, "status": status, "rows": len(rows), "fill": round(pct,1), "time": round(elapsed,1)})
        return rows
    except Exception as e:
        elapsed = time.time() - t0
        if expect_crash:
            print(f"  EXPECTED CRASH: {e}")
            results.append({"id": tid, "label": label, "status": "EXPECTED_CRASH", "rows": 0, "fill": 0, "time": round(elapsed,1)})
        else:
            print(f"  UNEXPECTED CRASH: {e}")
            traceback.print_exc()
            results.append({"id": tid, "label": label, "status": "CRASH", "rows": 0, "fill": 0, "time": round(elapsed,1)})


SOV_25 = f"{TEST_DOCS}/10_sov_samples/01_property_appraisal_report_25_buildings.pdf"
SOV_50 = f"{TEST_DOCS}/10_sov_samples/02_carrier_property_schedule_50_locations.pdf"
VEHICLE = f"{TEST_DOCS}/10_sov_samples/04_vehicle_schedule_35_vehicles.pdf"
RETAIL_75 = f"{TEST_DOCS}/15_location_schedule_large/01_retail_chain_75_locations.html"
CONTRACT = f"{TEST_DOCS}/09_contracts_agreements/contract_001.pdf"
INVOICE = f"{TEST_DOCS}/01_invoices/invoice_Aaron Bergman_36258.pdf"


async def main():
    tid = 0

    print("=" * 80)
    print("STRESS / ADVERSARIAL SOV TESTS")
    print("=" * 80)

    # ── 1. Very minimal fields (just 2) ──────────────────────────────────
    tid += 1
    await run_test(tid, "Only 2 fields", SOV_25, [
        {"name": "Address", "description": "Property address"},
        {"name": "City", "description": "City"},
    ], min_rows=20)

    # ── 2. Single field ──────────────────────────────────────────────────
    tid += 1
    await run_test(tid, "Single field only", SOV_25, [
        {"name": "Address", "description": "Property street address"},
    ], min_rows=1)  # might only get 1 row, that's ok

    # ── 3. Huge field set (22 fields) ────────────────────────────────────
    tid += 1
    await run_test(tid, "22 fields (stress)", SOV_25, [
        {"name": "Location #", "description": "Loc number"},
        {"name": "Address", "description": "Street address"},
        {"name": "City", "description": "City"},
        {"name": "State", "description": "State"},
        {"name": "Zip Code", "description": "ZIP"},
        {"name": "County", "description": "County"},
        {"name": "Building Value", "description": "Building value", "numeric": True},
        {"name": "Contents Value", "description": "Contents", "numeric": True},
        {"name": "Business Income", "description": "BI value", "numeric": True},
        {"name": "Total Insured Value", "description": "TIV", "numeric": True},
        {"name": "Year Built", "description": "Year built"},
        {"name": "Square Footage", "description": "Sq ft", "numeric": True},
        {"name": "Stories", "description": "Number of stories"},
        {"name": "Construction Type", "description": "Construction"},
        {"name": "Occupancy", "description": "Occupancy use"},
        {"name": "Sprinklered", "description": "Sprinkler Y/N"},
        {"name": "Roof Type", "description": "Roof material"},
        {"name": "Alarm Type", "description": "Alarm system"},
        {"name": "Flood Zone", "description": "FEMA flood zone"},
        {"name": "Wind Zone", "description": "Wind exposure zone"},
        {"name": "Earthquake Zone", "description": "Seismic zone"},
        {"name": "Distance to Coast", "description": "Miles to nearest coast"},
    ], min_rows=20)

    # ── 4. Fields that don't exist in the document ───────────────────────
    tid += 1
    await run_test(tid, "Nonexistent fields", SOV_25, [
        {"name": "Location #", "description": "Location number"},
        {"name": "Address", "description": "Street address"},
        {"name": "City", "description": "City"},
        {"name": "State", "description": "State"},
        {"name": "CEO Blood Type", "description": "Blood type of the CEO"},
        {"name": "Moon Phase", "description": "Phase of the moon when building was constructed"},
        {"name": "Favorite Color", "description": "Building's favorite color"},
    ], min_rows=20)

    # ── 5. Abbreviated/unconventional field names ────────────────────────
    tid += 1
    await run_test(tid, "Abbreviated field names", SOV_50, [
        {"name": "Loc#", "description": "Location ID"},
        {"name": "Addr", "description": "Address"},
        {"name": "Cty", "description": "City"},
        {"name": "St", "description": "State abbreviation"},
        {"name": "Zp", "description": "Postal code"},
        {"name": "BV", "description": "Building replacement value", "numeric": True},
        {"name": "TIV", "description": "Total insured value", "numeric": True},
    ], min_rows=40)

    # ── 6. All-caps field names ──────────────────────────────────────────
    tid += 1
    await run_test(tid, "ALL CAPS fields", SOV_25, [
        {"name": "LOCATION NUMBER", "description": "Location #"},
        {"name": "STREET ADDRESS", "description": "Address"},
        {"name": "CITY", "description": "City"},
        {"name": "STATE", "description": "State"},
        {"name": "ZIP CODE", "description": "Postal code"},
        {"name": "BUILDING VALUE", "description": "Building value", "numeric": True},
        {"name": "TOTAL INSURED VALUE", "description": "TIV", "numeric": True},
    ], min_rows=20)

    # ── 7. Vehicle schedule with unusual field names ─────────────────────
    tid += 1
    await run_test(tid, "Vehicle alt fields", VEHICLE, [
        {"name": "Unit No.", "description": "Vehicle unit number"},
        {"name": "Model Year", "description": "Year manufactured"},
        {"name": "Manufacturer", "description": "Vehicle manufacturer/make"},
        {"name": "Vehicle Model", "description": "Model name"},
        {"name": "Serial Number (VIN)", "description": "Vehicle identification number"},
        {"name": "Declared Value", "description": "Insured value", "numeric": True},
        {"name": "Primary Garage", "description": "Garage city/state"},
    ], min_rows=25)

    # ── 8. Instructions that add formatting requirements ─────────────────
    tid += 1
    await run_test(tid, "Formatting instructions", SOV_25, [
        {"name": "Location #", "description": "Location number"},
        {"name": "Address", "description": "Street address"},
        {"name": "City", "description": "City"},
        {"name": "State", "description": "State"},
        {"name": "Building Value", "description": "Building value", "numeric": True},
        {"name": "Total Insured Value", "description": "TIV", "numeric": True},
    ], instructions="Format all monetary values with dollar sign and commas (e.g. $1,250,000). State should be the full state name, not abbreviation. Building Value should exclude land value.", min_rows=20)

    # ── 9. Very long instructions ────────────────────────────────────────
    tid += 1
    long_instr = ("Please extract all properties carefully. " * 50) + "Focus on accuracy above all else."
    await run_test(tid, "Very long instructions (2500 chars)", SOV_25, [
        {"name": "Location #", "description": "Location number"},
        {"name": "Address", "description": "Street address"},
        {"name": "City", "description": "City"},
        {"name": "State", "description": "State"},
        {"name": "Total Insured Value", "description": "TIV", "numeric": True},
    ], instructions=long_instr, min_rows=20)

    # ── 10. Non-SOV document forced through SOV ──────────────────────────
    tid += 1
    await run_test(tid, "Contract forced through SOV", CONTRACT, [
        {"name": "Location #", "description": "Location number"},
        {"name": "Address", "description": "Street address"},
        {"name": "City", "description": "City"},
        {"name": "State", "description": "State"},
        {"name": "Building Value", "description": "Building value", "numeric": True},
    ], force_sov=True, min_rows=0)  # should return something without crashing

    # ── 11. Invoice forced through SOV ───────────────────────────────────
    tid += 1
    await run_test(tid, "Invoice forced through SOV", INVOICE, [
        {"name": "Location #", "description": "Location number"},
        {"name": "Address", "description": "Street address"},
        {"name": "City", "description": "City"},
        {"name": "State", "description": "State"},
        {"name": "Total Insured Value", "description": "TIV", "numeric": True},
    ], force_sov=True, min_rows=0)

    # ── 12. Fields with special characters ───────────────────────────────
    tid += 1
    await run_test(tid, "Special chars in field names", SOV_25, [
        {"name": "Location #", "description": "Location number"},
        {"name": "Address (Street)", "description": "Street address"},
        {"name": "City/Town", "description": "City or town"},
        {"name": "State & Province", "description": "State"},
        {"name": "Zip-Code", "description": "Postal code"},
        {"name": "Building Value ($)", "description": "Building value", "numeric": True},
        {"name": "TIV — Total", "description": "Total insured value", "numeric": True},
    ], min_rows=20)

    # ── 13. Large HTML schedule (75 locations) ───────────────────────────
    if os.path.exists(RETAIL_75):
        tid += 1
        await run_test(tid, "75-location HTML with minimal fields", RETAIL_75, [
            {"name": "Address", "description": "Address"},
            {"name": "City", "description": "City"},
            {"name": "State", "description": "State"},
            {"name": "TIV", "description": "Total insured value", "numeric": True},
        ], min_rows=60)

    # ── 14. Baseline update stress: update with mismatched fields ────────
    tid += 1
    print(f"\n[T{tid:02d}] Baseline update with mismatched fields")
    try:
        fn_v1 = ["Address", "City", "State", "Value"]
        rows_v1 = [
            {"_source_file": "a.pdf", "Address": "123 Main St", "City": "Dallas", "State": "TX", "Value": "1000000"},
            {"_source_file": "a.pdf", "Address": "456 Oak Ave", "City": "Houston", "State": "TX", "Value": "2000000"},
        ]
        baseline = generate_excel_bytes(rows_v1, fn_v1)

        # Update with rows that have different field values
        rows_v2 = [
            {"_source_file": "b.pdf", "Address": "789 Pine Rd", "City": "Austin", "State": "TX", "Value": "3000000"},
        ]
        updated = update_excel_baseline_bytes(baseline, rows_v2, fn_v1, allow_edit_past_values=False)
        hdrs = read_headers_from_bytes(updated, "xlsx")
        print(f"  PASS: Baseline update OK, headers={hdrs}")
        results.append({"id": tid, "label": "Baseline mismatch", "status": "PASS", "rows": 0, "fill": 0, "time": 0})
    except Exception as e:
        print(f"  CRASH: {e}")
        results.append({"id": tid, "label": "Baseline mismatch", "status": "CRASH", "rows": 0, "fill": 0, "time": 0})

    # ── 15. Spreadsheet with special chars in data ───────────────────────
    tid += 1
    print(f"\n[T{tid:02d}] Spreadsheet with special chars in data")
    try:
        fn_sp = ["Name", "Address", "Notes"]
        rows_sp = [
            {"_source_file": "test.pdf", "Name": "O'Brien & Associates", "Address": '123 "Main" St, Suite #5', "Notes": "Value: $1,000,000\nLine 2\tTabbed"},
            {"_source_file": "test.pdf", "Name": "Müller GmbH", "Address": "Straße 42, München", "Notes": "Ñoño — em dash – en dash"},
            {"_source_file": "test.pdf", "Name": None, "Address": "", "Notes": "null"},
        ]
        xlsx = generate_excel_bytes(rows_sp, fn_sp)
        csv_b = generate_csv_bytes(rows_sp, fn_sp)
        xlsx_h = read_headers_from_bytes(xlsx, "xlsx")
        csv_h = read_headers_from_bytes(csv_b, "csv")
        ok = xlsx_h == ["Source File"] + fn_sp and csv_h == ["Source File"] + fn_sp
        print(f"  {'PASS' if ok else 'FAIL'}: xlsx_headers={xlsx_h}, csv_headers={csv_h}")
        results.append({"id": tid, "label": "Special chars spreadsheet", "status": "PASS" if ok else "FAIL", "rows": 0, "fill": 0, "time": 0})
    except Exception as e:
        print(f"  CRASH: {e}")
        traceback.print_exc()
        results.append({"id": tid, "label": "Special chars spreadsheet", "status": "CRASH", "rows": 0, "fill": 0, "time": 0})

    # ── 16. Empty field description ──────────────────────────────────────
    tid += 1
    await run_test(tid, "Empty field descriptions", SOV_25, [
        {"name": "Location #", "description": ""},
        {"name": "Address", "description": ""},
        {"name": "City", "description": ""},
        {"name": "State", "description": ""},
        {"name": "Total Insured Value", "description": ""},
    ], min_rows=20)

    # ── FINAL REPORT ─────────────────────────────────────────────────────
    print(f"\n{'='*80}")
    print("STRESS TEST REPORT")
    print(f"{'='*80}")

    passed = sum(1 for r in results if r["status"] == "PASS")
    failed = sum(1 for r in results if r["status"] == "FAIL")
    crashed = sum(1 for r in results if r["status"] == "CRASH")
    expected = sum(1 for r in results if r["status"] == "EXPECTED_CRASH")

    print(f"\nTotal: {len(results)} | PASS: {passed} | FAIL: {failed} | CRASH: {crashed} | EXPECTED_CRASH: {expected}")

    for r in results:
        s = {"PASS": "  ok", "FAIL": "FAIL", "CRASH": "!ERR", "EXPECTED_CRASH": "xpct"}[r["status"]]
        print(f"  T{r['id']:02d} {s} {r['label'][:50]:<50} rows={r['rows']:>3} fill={r['fill']:>5.0f}% {r['time']:>5.1f}s")

    if crashed:
        print(f"\n*** {crashed} UNEXPECTED CRASHES — NEED FIXING ***")
    elif failed:
        print(f"\n{failed} failures (non-crash) — review needed")
    else:
        print(f"\nAll tests passed or expected crashes only")

    print(f"{'='*80}")


if __name__ == "__main__":
    asyncio.run(main())
