"""Quick smoke test — 3 documents, verify extraction works end-to-end."""
import asyncio, sys, os, time, json
sys.path.insert(0, os.path.dirname(__file__))

# Force unbuffered output
sys.stdout.reconfigure(line_buffering=True)

import logging
logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
logging.getLogger("httpx").setLevel(logging.ERROR)
logging.getLogger("httpcore").setLevel(logging.ERROR)
logging.getLogger("openai").setLevel(logging.ERROR)

from app.services.pdf_service import parse_pdf
from app.services.extraction import extract_from_document, LLMUsage
from app.services.extraction.core import property_schedule_row_cleanup_matches_schema
from app.services.spreadsheet_service import generate_excel_bytes, generate_csv_bytes, read_headers_from_bytes

TEST_DOCS = "/Users/martinmashalov/Downloads/GridPull/test_documents"

INVOICE_FIELDS = [
    {"name": "Invoice Number", "description": "Invoice or order number"},
    {"name": "Invoice Date", "description": "Date of the invoice"},
    {"name": "Customer Name", "description": "Name of the customer"},
    {"name": "Total Amount", "description": "Total amount due", "numeric": True},
]

SOV_FIELDS = [
    {"name": "Location #", "description": "Location number"},
    {"name": "Address", "description": "Street address"},
    {"name": "City", "description": "City"},
    {"name": "State", "description": "State"},
    {"name": "Zip Code", "description": "ZIP code"},
    {"name": "Building Value", "description": "Building value", "numeric": True},
    {"name": "Total Insured Value", "description": "Total insured value", "numeric": True},
]

CASHFLOW_FIELDS = [
    {"name": "Company Name", "description": "Name of the company"},
    {"name": "Period", "description": "Reporting period or fiscal year"},
    {"name": "Operating Cash Flow", "description": "Net cash from operating activities", "numeric": True},
    {"name": "Net Change in Cash", "description": "Net increase/decrease in cash", "numeric": True},
]


async def test_one(label, path, fields, force_sov=False):
    print(f"\n{'='*60}")
    print(f"TEST: {label}")
    print(f"File: {os.path.basename(path)}")
    field_names = [f["name"] for f in fields]
    is_sov = property_schedule_row_cleanup_matches_schema(field_names)
    print(f"Route: {'SOV' if (force_sov or is_sov) else 'General'} (auto_detect_sov={is_sov})")

    t0 = time.time()
    doc = await asyncio.to_thread(parse_pdf, path, os.path.basename(path))
    print(f"Parsed: {doc.page_count} pages, type={doc.doc_type_hint}, scanned={doc.is_scanned}")

    usage = LLMUsage()
    rows = await extract_from_document(doc, fields, usage, force_sov=force_sov)
    elapsed = time.time() - t0

    filled = sum(1 for r in rows for fn in field_names
                 if r.get(fn) is not None and str(r[fn]).strip().lower() not in ("", "null", "none", "n/a"))
    total = len(rows) * len(field_names)
    fill_pct = filled / total * 100 if total else 0

    print(f"Result: {len(rows)} rows, {filled}/{total} filled ({fill_pct:.0f}%), cost=${usage.cost_usd:.5f}, time={elapsed:.1f}s")

    # Show rows
    for i, row in enumerate(rows[:5]):
        vals = {k: v for k, v in row.items() if k not in ("_source_file", "_error") and v is not None and str(v).strip()}
        print(f"  Row {i+1}: {json.dumps(vals, default=str)[:150]}")

    # Validate spreadsheet
    xlsx = generate_excel_bytes(rows, field_names)
    headers = read_headers_from_bytes(xlsx, "xlsx")
    expected = ["Source File"] + field_names
    assert headers == expected, f"XLSX headers mismatch: {headers} vs {expected}"
    print(f"XLSX: valid ({len(xlsx)} bytes, headers match)")

    csv_bytes = generate_csv_bytes(rows, field_names)
    csv_headers = read_headers_from_bytes(csv_bytes, "csv")
    assert csv_headers == expected, f"CSV headers mismatch: {csv_headers} vs {expected}"
    print(f"CSV: valid ({len(csv_bytes)} bytes, headers match)")

    return {"label": label, "rows": len(rows), "fill_pct": fill_pct, "cost": usage.cost_usd, "time": elapsed}


async def main():
    results = []

    # Test 1: Invoice (should NOT go to SOV)
    invoice = f"{TEST_DOCS}/11_multipage_invoices/invoice_001_TechCorp_INV-2024-8515.pdf"
    results.append(await test_one("Invoice", invoice, INVOICE_FIELDS))

    # Test 2: Cash flow (should NOT go to SOV)
    cashflow = f"{TEST_DOCS}/08_cash_flow_statements/cashflow_statement_001.pdf"
    results.append(await test_one("CashFlow", cashflow, CASHFLOW_FIELDS))

    # Test 3: SOV (SHOULD go to SOV)
    sov = f"{TEST_DOCS}/10_sov_samples/01_property_appraisal_report_25_buildings.pdf"
    results.append(await test_one("SOV", sov, SOV_FIELDS, force_sov=True))

    print(f"\n{'='*60}")
    print("SMOKE TEST SUMMARY")
    for r in results:
        status = "PASS" if r["fill_pct"] > 20 else "FAIL"
        print(f"  {status} {r['label']}: {r['rows']} rows, {r['fill_pct']:.0f}% fill, ${r['cost']:.5f}, {r['time']:.1f}s")
    print(f"{'='*60}")


if __name__ == "__main__":
    asyncio.run(main())
