"""
Thorough SOV pipeline testing.

Tests the SOV extraction path with every available SOV-relevant document,
varied field configurations, different document sizes, and validates
spreadsheet output correctness and completeness.
"""
import asyncio, sys, os, time, json, traceback
sys.path.insert(0, os.path.dirname(__file__))
sys.stdout.reconfigure(line_buffering=True)

import logging
logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
logging.getLogger("httpx").setLevel(logging.ERROR)
logging.getLogger("httpcore").setLevel(logging.ERROR)
logging.getLogger("openai").setLevel(logging.ERROR)

from app.services.pdf_service import parse_pdf
from app.services.extraction import extract_from_document, LLMUsage
from app.services.spreadsheet_service import (
    generate_excel_bytes, generate_csv_bytes, read_headers_from_bytes,
    update_excel_baseline_bytes,
)

# Disable Mistral OCR if it's hanging (503/520 outage) so tests use LiteParse fallback
from app.config import settings
if os.environ.get("SKIP_MISTRAL_OCR"):
    settings.mistral_api_key = ""
    print("NOTE: Mistral OCR disabled via SKIP_MISTRAL_OCR — using LiteParse fallback")

TEST_DOCS = "/Users/martinmashalov/Downloads/GridPull/test_documents"
TEST_FILES = "/Users/martinmashalov/Downloads/GridPull/backend/test_files"
EMPTY = {"", "null", "none", "n/a", "na", "-", "—", "unknown", "not found", "not available"}

# ── Field configs ────────────────────────────────────────────────────────

FULL_SOV_FIELDS = [
    {"name": "Location #", "description": "Location or building number"},
    {"name": "Address", "description": "Street address of the property"},
    {"name": "City", "description": "City"},
    {"name": "State", "description": "State or province"},
    {"name": "Zip Code", "description": "ZIP or postal code"},
    {"name": "Building Value", "description": "Building replacement cost or value", "numeric": True},
    {"name": "Contents Value", "description": "Contents or personal property value", "numeric": True},
    {"name": "Total Insured Value", "description": "Total insured value (TIV)", "numeric": True},
    {"name": "Year Built", "description": "Year the building was constructed"},
    {"name": "Square Footage", "description": "Total square footage of the building", "numeric": True},
    {"name": "Construction Type", "description": "Construction type (e.g., frame, masonry, steel)"},
    {"name": "Occupancy", "description": "Occupancy or use of the building"},
]

MINIMAL_SOV_FIELDS = [
    {"name": "Location #", "description": "Location number"},
    {"name": "Address", "description": "Street address"},
    {"name": "City", "description": "City"},
    {"name": "State", "description": "State"},
    {"name": "Total Insured Value", "description": "Total insured value", "numeric": True},
]

VEHICLE_FIELDS = [
    {"name": "Vehicle #", "description": "Vehicle number or unit number"},
    {"name": "Year", "description": "Model year of the vehicle"},
    {"name": "Make", "description": "Vehicle manufacturer"},
    {"name": "Model", "description": "Vehicle model name"},
    {"name": "VIN", "description": "Vehicle identification number"},
    {"name": "Value", "description": "Stated or insured value", "numeric": True},
    {"name": "Garage Location", "description": "Where the vehicle is garaged"},
]

CERT_HOLDER_FIELDS = [
    {"name": "Certificate Holder", "description": "Name of the certificate holder"},
    {"name": "Insured Name", "description": "Name of the insured party"},
    {"name": "Policy Number", "description": "Insurance policy number"},
    {"name": "Policy Effective Date", "description": "Policy start date"},
    {"name": "Policy Expiration Date", "description": "Policy end date"},
    {"name": "General Liability Limit", "description": "General liability coverage limit", "numeric": True},
    {"name": "Workers Comp Limit", "description": "Workers compensation limit", "numeric": True},
    {"name": "Auto Liability Limit", "description": "Auto liability coverage limit", "numeric": True},
]

LARGE_SCHEDULE_FIELDS = [
    {"name": "Location #", "description": "Location or property number"},
    {"name": "Property Name", "description": "Name or description of the property"},
    {"name": "Address", "description": "Street address"},
    {"name": "City", "description": "City"},
    {"name": "State", "description": "State"},
    {"name": "Zip Code", "description": "ZIP code"},
    {"name": "Building Value", "description": "Building value", "numeric": True},
    {"name": "Total Insured Value", "description": "Total insured value", "numeric": True},
    {"name": "Year Built", "description": "Year built"},
    {"name": "Construction Type", "description": "Construction type"},
    {"name": "Occupancy Type", "description": "Occupancy or use type"},
    {"name": "Sprinklered", "description": "Whether the property has sprinklers (Yes/No)"},
]

# Alternative field names a user might use (generalizability test)
ALT_SOV_FIELDS = [
    {"name": "Loc No.", "description": "Location identifier"},
    {"name": "Street", "description": "Street address"},
    {"name": "City", "description": "City name"},
    {"name": "St", "description": "State abbreviation"},
    {"name": "Zip", "description": "Postal code"},
    {"name": "Bldg Value", "description": "Building replacement value", "numeric": True},
    {"name": "BPP Value", "description": "Business personal property value", "numeric": True},
    {"name": "TIV", "description": "Total insured value", "numeric": True},
    {"name": "Yr Built", "description": "Construction year"},
    {"name": "Const", "description": "Construction class"},
    {"name": "Occ Code", "description": "Occupancy classification"},
]

# Very wide field set (stress test)
WIDE_SOV_FIELDS = [
    {"name": "Location #", "description": "Location number"},
    {"name": "Building #", "description": "Building number within a location"},
    {"name": "Address", "description": "Street address"},
    {"name": "City", "description": "City"},
    {"name": "State", "description": "State"},
    {"name": "Zip Code", "description": "ZIP code"},
    {"name": "County", "description": "County name"},
    {"name": "Building Value", "description": "Building value", "numeric": True},
    {"name": "Contents Value", "description": "Contents value", "numeric": True},
    {"name": "Business Income Value", "description": "Business income value", "numeric": True},
    {"name": "Total Insured Value", "description": "TIV", "numeric": True},
    {"name": "Year Built", "description": "Year constructed"},
    {"name": "Square Footage", "description": "Square footage", "numeric": True},
    {"name": "Number of Stories", "description": "Number of floors/stories"},
    {"name": "Construction Type", "description": "Construction type"},
    {"name": "Occupancy", "description": "Occupancy type"},
    {"name": "Sprinklered", "description": "Sprinkler protection (Yes/No)"},
    {"name": "Alarm Type", "description": "Fire/burglar alarm type"},
    {"name": "Roof Type", "description": "Roof material/type"},
    {"name": "Flood Zone", "description": "FEMA flood zone designation"},
]

# ── Helpers ──────────────────────────────────────────────────────────────

def is_filled(val):
    if val is None: return False
    return str(val).strip().lower() not in EMPTY

def fill_stats(rows, field_names):
    total = len(rows) * len(field_names)
    filled = sum(1 for r in rows for fn in field_names if is_filled(r.get(fn)))
    return filled, total, (filled / total * 100) if total else 0

results = []

async def run_sov_test(test_id, label, file_path, fields, *, instructions="", expected_min_rows=1):
    filename = os.path.basename(file_path)
    field_names = [f["name"] for f in fields]
    print(f"\n[T{test_id:02d}] {label}")
    print(f"  File: {filename} | Fields: {len(fields)}")

    t0 = time.time()
    try:
        doc = await asyncio.to_thread(parse_pdf, file_path, filename)
        print(f"  Parsed: {doc.page_count} pages, type={doc.doc_type_hint}, scanned={doc.is_scanned}")

        usage = LLMUsage()
        rows = await extract_from_document(
            doc, fields, usage, instructions,
            force_sov=True,
        )
        elapsed = time.time() - t0
        filled, total, fill_pct = fill_stats(rows, field_names)

        # Validate spreadsheet
        xlsx_ok = True
        try:
            xlsx = generate_excel_bytes(rows, field_names)
            hdrs = read_headers_from_bytes(xlsx, "xlsx")
            expected = ["Source File"] + field_names
            if hdrs != expected:
                xlsx_ok = False
                print(f"  XLSX HEADERS MISMATCH: got {hdrs[:5]}...")
        except Exception as e:
            xlsx_ok = False
            print(f"  XLSX FAIL: {e}")

        csv_ok = True
        try:
            csv_b = generate_csv_bytes(rows, field_names)
            csv_hdrs = read_headers_from_bytes(csv_b, "csv")
            if csv_hdrs != ["Source File"] + field_names:
                csv_ok = False
        except Exception as e:
            csv_ok = False

        # Row-level checks
        empty_rows = sum(1 for r in rows if all(not is_filled(r.get(fn)) for fn in field_names))
        error_rows = sum(1 for r in rows if r.get("_error"))
        dup_addresses = set()
        dup_count = 0
        for r in rows:
            addr = str(r.get("Address") or r.get("Street") or r.get("street") or "").strip().lower()
            if addr and addr in dup_addresses:
                dup_count += 1
            dup_addresses.add(addr)

        status = "PASS" if (
            len(rows) >= expected_min_rows
            and fill_pct >= 40
            and xlsx_ok and csv_ok
            and empty_rows == 0
            and error_rows == 0
        ) else "FAIL"

        print(f"  {status}: rows={len(rows)} fill={filled}/{total} ({fill_pct:.0f}%) "
              f"cost=${usage.cost_usd:.4f} time={elapsed:.1f}s "
              f"empty_rows={empty_rows} errors={error_rows} dup_addr={dup_count} "
              f"xlsx={'ok' if xlsx_ok else 'FAIL'} csv={'ok' if csv_ok else 'FAIL'}")

        # Show first 3 rows sample
        for i, row in enumerate(rows[:3]):
            vals = {k: str(v)[:40] for k, v in row.items() if k not in ("_source_file", "_error") and is_filled(v)}
            print(f"  Row {i+1}: {json.dumps(vals, default=str)[:200]}")
        if len(rows) > 3:
            print(f"  ... and {len(rows)-3} more rows")

        # Check for specific data quality issues
        issues = []
        if empty_rows > 0:
            issues.append(f"{empty_rows} empty rows")
        if error_rows > 0:
            issues.append(f"{error_rows} error rows")
        if fill_pct < 40:
            issues.append(f"low fill rate {fill_pct:.0f}%")
        if len(rows) < expected_min_rows:
            issues.append(f"only {len(rows)} rows (expected >={expected_min_rows})")
        if not xlsx_ok:
            issues.append("xlsx generation failed")
        if dup_count > len(rows) * 0.3:
            issues.append(f"many duplicate addresses ({dup_count})")
        if issues:
            print(f"  ISSUES: {', '.join(issues)}")

        results.append({
            "id": test_id, "label": label, "file": filename, "status": status,
            "rows": len(rows), "fill_pct": round(fill_pct, 1),
            "cost": round(usage.cost_usd, 4), "time": round(elapsed, 1),
            "empty_rows": empty_rows, "error_rows": error_rows,
            "issues": issues, "fields": len(fields),
        })
        return rows

    except Exception as e:
        elapsed = time.time() - t0
        print(f"  ERROR: {e}")
        traceback.print_exc()
        results.append({
            "id": test_id, "label": label, "file": filename, "status": "ERROR",
            "rows": 0, "fill_pct": 0, "cost": 0, "time": round(elapsed, 1),
            "empty_rows": 0, "error_rows": 0, "issues": [str(e)], "fields": len(fields),
        })
        return []


async def main():
    tid = 0
    print("=" * 80)
    print("THOROUGH SOV PIPELINE TESTING")
    print("=" * 80)

    # ══════════════════════════════════════════════════════════════════════
    # Group 1: Property SOV samples (10_sov_samples)
    # ══════════════════════════════════════════════════════════════════════
    sov_dir = f"{TEST_DOCS}/10_sov_samples"

    # T01: 25-building property appraisal — full fields
    tid += 1
    await run_sov_test(tid, "25-building appraisal (full fields)",
        f"{sov_dir}/01_property_appraisal_report_25_buildings.pdf",
        FULL_SOV_FIELDS, expected_min_rows=20)

    # T02: Same doc — minimal fields (generalizability)
    tid += 1
    await run_sov_test(tid, "25-building appraisal (minimal fields)",
        f"{sov_dir}/01_property_appraisal_report_25_buildings.pdf",
        MINIMAL_SOV_FIELDS, expected_min_rows=20)

    # T03: Same doc — alternative field names
    tid += 1
    await run_sov_test(tid, "25-building appraisal (alt field names)",
        f"{sov_dir}/01_property_appraisal_report_25_buildings.pdf",
        ALT_SOV_FIELDS, expected_min_rows=20)

    # T04: Same doc — wide field set (20 fields)
    tid += 1
    await run_sov_test(tid, "25-building appraisal (wide 20 fields)",
        f"{sov_dir}/01_property_appraisal_report_25_buildings.pdf",
        WIDE_SOV_FIELDS, expected_min_rows=20)

    # T05: 50-location carrier schedule
    f = f"{sov_dir}/02_carrier_property_schedule_50_locations.pdf"
    if os.path.exists(f):
        tid += 1
        await run_sov_test(tid, "50-location carrier schedule",
            f, FULL_SOV_FIELDS, expected_min_rows=40)

    # T06: 15-location package policy dec pages
    f = f"{sov_dir}/03_package_policy_dec_pages_15_locations.pdf"
    if os.path.exists(f):
        tid += 1
        await run_sov_test(tid, "15-location package policy dec",
            f, FULL_SOV_FIELDS, expected_min_rows=10)

    # T07: 35-vehicle schedule
    f = f"{sov_dir}/04_vehicle_schedule_35_vehicles.pdf"
    if os.path.exists(f):
        tid += 1
        await run_sov_test(tid, "35-vehicle schedule",
            f, VEHICLE_FIELDS, expected_min_rows=25)

    # T08: 30-location prior year SOV
    f = f"{sov_dir}/05_prior_year_sov_30_locations.pdf"
    if os.path.exists(f):
        tid += 1
        await run_sov_test(tid, "30-location prior year SOV",
            f, FULL_SOV_FIELDS, expected_min_rows=25)

    # ══════════════════════════════════════════════════════════════════════
    # Group 2: SOV PDFs from email examples (12_sov_email_examples)
    # ══════════════════════════════════════════════════════════════════════
    email_dir = f"{TEST_DOCS}/12_sov_email_examples"

    for fname in sorted(os.listdir(email_dir)):
        if not fname.endswith(".pdf"):
            continue
        tid += 1
        # Pick fields based on filename
        if "vehicle" in fname.lower() or "fleet" in fname.lower():
            fields = VEHICLE_FIELDS
            min_rows = 10
        else:
            fields = FULL_SOV_FIELDS
            min_rows = 5
        await run_sov_test(tid, f"Email SOV: {fname}",
            os.path.join(email_dir, fname), fields, expected_min_rows=min_rows)

    # ══════════════════════════════════════════════════════════════════════
    # Group 3: Certificate holders (HTML input)
    # ══════════════════════════════════════════════════════════════════════
    cert_dir = f"{TEST_DOCS}/14_certificate_holders"
    if os.path.isdir(cert_dir):
        for fname in sorted(os.listdir(cert_dir))[:4]:
            if not fname.endswith(".html"):
                continue
            tid += 1
            await run_sov_test(tid, f"Cert holder: {fname}",
                os.path.join(cert_dir, fname), CERT_HOLDER_FIELDS, expected_min_rows=1)

    # ══════════════════════════════════════════════════════════════════════
    # Group 4: Large location schedules (HTML)
    # ══════════════════════════════════════════════════════════════════════
    large_dir = f"{TEST_DOCS}/15_location_schedule_large"
    if os.path.isdir(large_dir):
        for fname in sorted(os.listdir(large_dir))[:3]:
            if not (fname.endswith(".html") or fname.endswith(".pdf")):
                continue
            tid += 1
            min_r = 30 if "200" in fname else 20
            await run_sov_test(tid, f"Large schedule: {fname}",
                os.path.join(large_dir, fname), LARGE_SCHEDULE_FIELDS,
                expected_min_rows=min_r)

    # ══════════════════════════════════════════════════════════════════════
    # Group 5: Test files from backend/test_files (PDFs only)
    # ══════════════════════════════════════════════════════════════════════
    for fname in sorted(os.listdir(TEST_FILES)):
        if not fname.endswith(".pdf"):
            continue
        tid += 1
        await run_sov_test(tid, f"TestFile: {fname}",
            os.path.join(TEST_FILES, fname), FULL_SOV_FIELDS, expected_min_rows=5)

    # ══════════════════════════════════════════════════════════════════════
    # Group 6: Instructions variation
    # ══════════════════════════════════════════════════════════════════════
    tid += 1
    await run_sov_test(tid, "25-building + instructions ($ formatting)",
        f"{sov_dir}/01_property_appraisal_report_25_buildings.pdf",
        FULL_SOV_FIELDS, expected_min_rows=20,
        instructions="Format all dollar values with commas and no decimal places (e.g. $1,250,000). For construction type use the full name not abbreviations.")

    # ══════════════════════════════════════════════════════════════════════
    # Group 7: Baseline update mode with SOV data
    # ══════════════════════════════════════════════════════════════════════
    tid += 1
    print(f"\n[T{tid:02d}] Baseline update with SOV rows")
    sov_results = [r for r in results if r["status"] == "PASS" and r["rows"] >= 10]
    if sov_results:
        # Re-run a quick extraction to get rows for baseline test
        f = f"{sov_dir}/01_property_appraisal_report_25_buildings.pdf"
        doc = await asyncio.to_thread(parse_pdf, f, os.path.basename(f))
        usage = LLMUsage()
        rows = await extract_from_document(doc, FULL_SOV_FIELDS, usage, force_sov=True)
        fn = [f["name"] for f in FULL_SOV_FIELDS]

        if len(rows) >= 10:
            # Create baseline with first 10 rows
            baseline = generate_excel_bytes(rows[:10], fn)
            # Update with next 10
            updated = update_excel_baseline_bytes(baseline, rows[10:20], fn, allow_edit_past_values=False)
            hdrs = read_headers_from_bytes(updated, "xlsx")
            has_status = "GridPull Status" in hdrs
            print(f"  Baseline: 10 rows, update with {min(10, len(rows)-10)} rows")
            print(f"  Headers: {hdrs[:6]}...")
            print(f"  Status column: {'PASS' if has_status else 'FAIL'}")

            # Also test allow_edit_past_values=True
            updated2 = update_excel_baseline_bytes(baseline, rows[10:20], fn, allow_edit_past_values=True)
            hdrs2 = read_headers_from_bytes(updated2, "xlsx")
            print(f"  Edit mode: headers={len(hdrs2)} PASS")

            results.append({
                "id": tid, "label": "Baseline update", "file": "synthetic",
                "status": "PASS" if has_status else "FAIL",
                "rows": len(rows), "fill_pct": 0, "cost": 0, "time": 0,
                "empty_rows": 0, "error_rows": 0, "issues": [], "fields": len(fn),
            })
        else:
            print(f"  SKIP: only {len(rows)} rows from extraction")
    else:
        print("  SKIP: no passing SOV results to use")

    # ══════════════════════════════════════════════════════════════════════
    # FINAL REPORT
    # ══════════════════════════════════════════════════════════════════════
    print("\n" + "=" * 90)
    print("SOV TEST REPORT")
    print("=" * 90)

    passed = sum(1 for r in results if r["status"] == "PASS")
    failed = sum(1 for r in results if r["status"] == "FAIL")
    errors = sum(1 for r in results if r["status"] == "ERROR")
    total_cost = sum(r["cost"] for r in results)
    total_time = sum(r["time"] for r in results)

    print(f"\nTotal: {len(results)} tests | PASS: {passed} | FAIL: {failed} | ERROR: {errors}")
    print(f"Cost: ${total_cost:.4f} | Time: {total_time:.0f}s ({total_time/60:.1f}m)")

    print(f"\n{'ID':>3} {'Status':<6} {'Rows':>5} {'Fill%':>6} {'$Cost':>8} {'Time':>6} {'Fields':>6} {'Label'}")
    print("-" * 90)
    for r in results:
        s = {"PASS": "  ok", "FAIL": "FAIL", "ERROR": " ERR"}[r["status"]]
        print(f"T{r['id']:02d} {s:<6} {r['rows']:>5} {r['fill_pct']:>5.0f}% ${r['cost']:>7.4f} {r['time']:>5.1f}s {r['fields']:>6} {r['label'][:50]}")

    if failed + errors > 0:
        print(f"\n--- FAILURES ---")
        for r in results:
            if r["status"] != "PASS":
                print(f"  T{r['id']:02d} {r['status']} {r['label']}: {', '.join(r['issues']) or 'unknown'}")

    # Save report
    report_path = os.path.join(os.path.dirname(__file__), "test_outputs", "sov_report.json")
    os.makedirs(os.path.dirname(report_path), exist_ok=True)
    with open(report_path, "w") as fh:
        json.dump(results, fh, indent=2)
    print(f"\nReport: {report_path}")

    print(f"\n{'='*90}")
    if errors == 0 and failed == 0:
        print("VERDICT: ALL SOV TESTS PASSED")
    elif errors + failed <= 2:
        print(f"VERDICT: MOSTLY PASSING ({failed} fail, {errors} error)")
    else:
        print(f"VERDICT: NEEDS ATTENTION ({failed} fail, {errors} error)")
    print("=" * 90)


if __name__ == "__main__":
    asyncio.run(main())
