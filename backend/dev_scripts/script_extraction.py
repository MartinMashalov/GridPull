"""
Test extraction on:
  1. CustomerStatementReport.pdf
  2. Invoices from test_documents/01_invoices/
"""
import asyncio, sys, os, time, json
sys.path.insert(0, os.path.dirname(__file__))

import logging
logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(name)s: %(message)s")

from app.services.pdf_service import parse_pdf
from app.services.extraction import (
    extract_single_record,
    extract_multi_record_validated,
    LLMUsage,
)

INVOICE_FIELDS = [
    {"name": "Invoice Number", "description": "Invoice or order number"},
    {"name": "Invoice Date", "description": "Date of the invoice"},
    {"name": "Customer Name", "description": "Name of the customer or bill-to party"},
    {"name": "Customer Address", "description": "Customer billing address"},
    {"name": "Total Amount", "description": "Total amount due including tax"},
    {"name": "Subtotal", "description": "Subtotal before tax"},
    {"name": "Tax Amount", "description": "Tax amount"},
    {"name": "Due Date", "description": "Payment due date"},
    {"name": "Line Items", "description": "Description of items/services billed"},
]

STATEMENT_FIELDS = [
    {"name": "Customer Name", "description": "Name of the customer on the statement"},
    {"name": "Account Number", "description": "Customer account or policy number"},
    {"name": "Statement Date", "description": "Date of the statement"},
    {"name": "Total Balance Due", "description": "Total amount owed"},
    {"name": "Previous Balance", "description": "Balance from previous period"},
    {"name": "Payments Received", "description": "Payments made during period"},
    {"name": "New Charges", "description": "New charges in this period"},
    {"name": "Policy Number", "description": "Insurance policy number if present"},
    {"name": "Due Date", "description": "Payment due date"},
]


async def test_file(path: str, fields: list, label: str):
    print(f"\n{'='*60}")
    print(f"TEST: {label}")
    print(f"File: {os.path.basename(path)} ({os.path.getsize(path)//1024} KB)")
    print(f"{'='*60}")

    t0 = time.time()
    doc = await asyncio.to_thread(parse_pdf, path, os.path.basename(path))
    print(f"Pages: {doc.page_count} | Scanned: {doc.is_scanned} | Type: {doc.doc_type_hint}")

    usage = LLMUsage()
    rows = await extract_single_record(doc, fields, usage)
    elapsed = time.time() - t0

    print(f"\nResults ({elapsed:.1f}s, cost=${usage.cost_usd:.5f}):")
    if rows:
        for field in fields:
            val = rows[0].get(field["name"])
            status = "✓" if val and str(val).strip().lower() not in ("null", "n/a", "none", "") else "✗"
            print(f"  {status}  {field['name']:25s} {str(val)[:60] if val else '[MISSING]'}")
    else:
        print("  No results returned")

    return rows, usage


async def main():
    # ── Test 1: CustomerStatementReport ─────────────────────────────
    csr_path = "/Users/martinmashalov/Downloads/Papyra-renewals/backend/core/activity_automation/tools/reporting/data_storage_temp/CustomerStatementReport.pdf"
    await test_file(csr_path, STATEMENT_FIELDS, "CustomerStatementReport.pdf")

    # ── Test 2: Invoices ────────────────────────────────────────────
    invoice_dir = "/Users/martinmashalov/Downloads/GridPull/test_documents/01_invoices"
    invoice_files = [
        os.path.join(invoice_dir, f)
        for f in os.listdir(invoice_dir)
        if f.endswith(".pdf")
    ]

    costs = []
    for path in invoice_files[:3]:  # test first 3
        rows, usage = await test_file(path, INVOICE_FIELDS, f"Invoice: {os.path.basename(path)}")
        costs.append(usage.cost_usd)

    print(f"\n{'='*60}")
    print(f"SUMMARY — {len(costs)} invoices tested")
    print(f"  Avg cost per doc: ${sum(costs)/len(costs):.5f}")
    print(f"  Total cost:       ${sum(costs):.5f}")
    print(f"{'='*60}")


if __name__ == "__main__":
    asyncio.run(main())
