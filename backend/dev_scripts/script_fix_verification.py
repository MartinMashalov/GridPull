"""Verify all 3 bug fixes with targeted tests."""
import asyncio, sys, os, time, json
sys.path.insert(0, os.path.dirname(__file__))
sys.stdout.reconfigure(line_buffering=True)

import logging
logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
logging.getLogger("httpx").setLevel(logging.ERROR)
logging.getLogger("httpcore").setLevel(logging.ERROR)
logging.getLogger("openai").setLevel(logging.ERROR)

from app.services.pdf_service import parse_pdf
from app.services.extraction import extract_from_document, LLMUsage
from app.services.extraction.core import property_schedule_row_cleanup_matches_schema
from app.services.spreadsheet_service import (
    generate_excel_bytes, generate_csv_bytes, read_headers_from_bytes,
    update_excel_baseline_bytes, update_csv_baseline_bytes,
)

TEST_DOCS = "/Users/martinmashalov/Downloads/GridPull/test_documents"
EMPTY = {"", "null", "none", "n/a", "na", "-", "—", "unknown", "not found", "not available"}
passed = 0
failed = 0


def check(cond, msg):
    global passed, failed
    if cond:
        passed += 1
        print(f"  PASS: {msg}")
    else:
        failed += 1
        print(f"  FAIL: {msg}")


def fill_rate(rows, field_names):
    total = len(rows) * len(field_names)
    filled = sum(1 for r in rows for fn in field_names
                 if r.get(fn) is not None and str(r[fn]).strip().lower() not in EMPTY)
    return (filled / total * 100) if total else 0


async def main():
    global passed, failed
    print("=" * 70)
    print("FIX VERIFICATION TESTS")
    print("=" * 70)

    # ── FIX 1: SOV routing — verify correct routing for all field types ──
    print("\n[FIX 1] SOV Routing Logic")
    routing_tests = {
        "Invoice": (["Invoice Number", "Date", "Customer Name", "Address", "Total", "Subtotal", "Tax", "Due Date", "Items"], False),
        "Contract": (["Title", "Parties", "Effective Date", "Expiration Date", "Value", "Governing Law", "Termination"], False),
        "EOB": (["Patient Name", "Claim Number", "Service Date", "Provider", "Billed Amount", "Allowed Amount", "Patient Responsibility", "Payment"], False),
        "CashFlow": (["Company Name", "Period", "Operating CF", "Investing CF", "Financing CF", "Net Change", "Depreciation"], False),
        "Annual": (["Company Name", "Fiscal Year", "Revenue", "Net Income", "Total Assets", "Liabilities", "EPS", "CEO"], False),
        "PurchaseOrder": (["Form #", "Contract Number", "Agency", "Date", "Amount", "Contractor", "Description"], False),
        "Payroll": (["Employee Name", "Employee ID", "Department", "Title", "Gross Pay", "Net Pay", "Period"], False),
        "Generic": (["Entity Name", "Document Type", "Date", "Amount", "Reference Number", "Summary"], False),
        "SOV_Property": (["Location #", "Address", "City", "State", "Zip Code", "Building Value", "TIV", "Year Built", "Sq Ft", "Construction Type", "Occupancy"], True),
        "Vehicle": (["Vehicle #", "Year", "Make", "Model", "VIN", "Value", "Garage Location"], True),
        "LargeSchedule": (["Location #", "Name", "Address", "City", "State", "Zip", "Building Value", "TIV", "Year Built", "Type", "Occupancy", "Sprinklered"], True),
        "SOV_NoHash": (["Location Number", "Address", "City", "State", "Zip", "Building Value", "TIV"], True),
        "SOV_Minimal": (["Property", "Street", "City", "State", "Value"], True),
    }
    for name, (fields, expected) in routing_tests.items():
        result = property_schedule_row_cleanup_matches_schema(fields)
        check(result == expected, f"{name}: routes_to_sov={result} (expected={expected})")

    # ── FIX 2: _llm_extract_vision — test scanned doc extraction works ──
    print("\n[FIX 2] Scanned Document Extraction (OCR path)")
    scanned_file = f"{TEST_DOCS}/07_scanned_docs/scanned_invoice_01.pdf"
    if os.path.exists(scanned_file):
        t0 = time.time()
        doc = await asyncio.to_thread(parse_pdf, scanned_file, "scanned_invoice_01.pdf")
        print(f"  Parsed: pages={doc.page_count} scanned={doc.is_scanned}")

        usage = LLMUsage()
        fields = [
            {"name": "Invoice Number", "description": "Invoice number"},
            {"name": "Date", "description": "Invoice date"},
            {"name": "Total", "description": "Total amount", "numeric": True},
            {"name": "Vendor", "description": "Vendor or seller name"},
        ]
        try:
            rows = await extract_from_document(doc, fields, usage)
            elapsed = time.time() - t0
            fr = fill_rate(rows, [f["name"] for f in fields])
            check(len(rows) >= 1, f"Scanned extraction returned {len(rows)} rows")
            check(fr > 0, f"Scanned fill rate = {fr:.0f}%")
            check(usage.cost_usd > 0, f"Cost tracked: ${usage.cost_usd:.5f}")
            print(f"  Result: rows={len(rows)}, fill={fr:.0f}%, cost=${usage.cost_usd:.5f}, time={elapsed:.1f}s")
            if rows:
                print(f"  Data: {json.dumps({k:v for k,v in rows[0].items() if k not in ('_source_file','_error')}, default=str)[:200]}")
        except Exception as e:
            check(False, f"Scanned extraction failed: {e}")
    else:
        print("  SKIP: No scanned test file found")

    # ── FIX 3: Uniform value preservation — test customer name is preserved ──
    print("\n[FIX 3] Uniform Value Preservation")
    invoice_file = f"{TEST_DOCS}/11_multipage_invoices/invoice_003_PrimeMedical_PMS-2024-9318.pdf"
    if os.path.exists(invoice_file):
        doc = await asyncio.to_thread(parse_pdf, invoice_file, os.path.basename(invoice_file))
        usage = LLMUsage()
        fields = [
            {"name": "Invoice Number", "description": "Invoice number"},
            {"name": "Customer Name", "description": "Name of the customer"},
            {"name": "Total Amount", "description": "Total amount", "numeric": True},
        ]
        rows = await extract_from_document(doc, fields, usage)
        has_customer = any(r.get("Customer Name") for r in rows
                         if r.get("Customer Name") and str(r["Customer Name"]).strip().lower() not in EMPTY)
        check(has_customer, f"Customer Name preserved (not nullified)")
        if rows:
            print(f"  Customer Name = {rows[0].get('Customer Name')}")

    # ── Additional: Spreadsheet output validation ────────────────────────
    print("\n[SPREADSHEET] Output Format Validation")
    # Create test data
    test_rows = [
        {"_source_file": "test.pdf", "Name": "Alice", "Amount": "1000.50", "Date": "01/15/2024"},
        {"_source_file": "test.pdf", "Name": "Bob", "Amount": "2500.00", "Date": "02/20/2024"},
        {"_source_file": "test.pdf", "Name": "Charlie", "Amount": "750.25", "Date": "03/10/2024"},
    ]
    field_names = ["Name", "Amount", "Date"]

    # XLSX generation
    xlsx = generate_excel_bytes(test_rows, field_names)
    xlsx_headers = read_headers_from_bytes(xlsx, "xlsx")
    check(xlsx_headers == ["Source File", "Name", "Amount", "Date"], f"XLSX headers correct: {xlsx_headers}")
    check(len(xlsx) > 100, f"XLSX has content ({len(xlsx)} bytes)")

    # CSV generation
    csv_bytes = generate_csv_bytes(test_rows, field_names)
    csv_headers = read_headers_from_bytes(csv_bytes, "csv")
    check(csv_headers == ["Source File", "Name", "Amount", "Date"], f"CSV headers correct: {csv_headers}")

    # Baseline update (XLSX)
    baseline_xlsx = generate_excel_bytes(test_rows[:2], field_names)
    updated = update_excel_baseline_bytes(baseline_xlsx, test_rows[2:], field_names, allow_edit_past_values=False)
    updated_headers = read_headers_from_bytes(updated, "xlsx")
    check("GridPull Status" in updated_headers, f"Baseline update adds status column: {updated_headers}")

    # Baseline update (CSV)
    baseline_csv = generate_csv_bytes(test_rows[:2], field_names)
    updated_csv = update_csv_baseline_bytes(baseline_csv, test_rows[2:], field_names, allow_edit_past_values=True)
    check(len(updated_csv) > len(baseline_csv), f"CSV baseline update adds data ({len(updated_csv)} > {len(baseline_csv)} bytes)")

    # ── Additional: SOV extraction quick test ────────────────────────────
    print("\n[SOV] Quick SOV Pipeline Test")
    sov_file = f"{TEST_DOCS}/10_sov_samples/01_property_appraisal_report_25_buildings.pdf"
    if os.path.exists(sov_file):
        t0 = time.time()
        doc = await asyncio.to_thread(parse_pdf, sov_file, os.path.basename(sov_file))
        usage = LLMUsage()
        sov_fields = [
            {"name": "Location #", "description": "Location number"},
            {"name": "Address", "description": "Street address"},
            {"name": "City", "description": "City"},
            {"name": "State", "description": "State"},
            {"name": "Zip Code", "description": "ZIP code"},
            {"name": "Building Value", "description": "Building value", "numeric": True},
            {"name": "Total Insured Value", "description": "TIV", "numeric": True},
        ]
        rows = await extract_from_document(doc, sov_fields, usage, force_sov=True)
        elapsed = time.time() - t0
        fr = fill_rate(rows, [f["name"] for f in sov_fields])
        check(len(rows) >= 20, f"SOV extracted {len(rows)} rows (expected ~25)")
        check(fr >= 80, f"SOV fill rate = {fr:.0f}% (expected >=80%)")
        print(f"  SOV: {len(rows)} rows, {fr:.0f}% fill, ${usage.cost_usd:.5f}, {elapsed:.1f}s")
    else:
        print("  SKIP: No SOV test file found")

    # ── Additional: General extraction for single-record doc ─────────────
    print("\n[GENERAL] Single-Record Invoice Test")
    invoice_single = f"{TEST_DOCS}/01_invoices/invoice_Aaron Bergman_36258.pdf"
    if os.path.exists(invoice_single):
        doc = await asyncio.to_thread(parse_pdf, invoice_single, os.path.basename(invoice_single))
        usage = LLMUsage()
        inv_fields = [
            {"name": "Invoice Number", "description": "Invoice number"},
            {"name": "Customer Name", "description": "Customer name"},
            {"name": "Total Amount", "description": "Total amount", "numeric": True},
            {"name": "Invoice Date", "description": "Date of invoice"},
        ]
        rows = await extract_from_document(doc, inv_fields, usage, batch_document_count=3)
        fr = fill_rate(rows, [f["name"] for f in inv_fields])
        check(len(rows) == 1, f"Single invoice returned {len(rows)} row(s)")
        check(fr >= 50, f"Single invoice fill = {fr:.0f}%")
        if rows:
            print(f"  Data: {json.dumps({k:v for k,v in rows[0].items() if k not in ('_source_file','_error')}, default=str)[:200]}")

    # ── SUMMARY ──────────────────────────────────────────────────────────
    print(f"\n{'='*70}")
    print(f"VERIFICATION RESULTS: {passed} passed, {failed} failed")
    total = passed + failed
    if failed == 0:
        print("ALL FIXES VERIFIED SUCCESSFULLY")
    else:
        print(f"WARNING: {failed}/{total} checks failed")
    print(f"{'='*70}")


if __name__ == "__main__":
    asyncio.run(main())
