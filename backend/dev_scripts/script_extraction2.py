"""
Comprehensive extraction test:
  1. CustomerStatementReport.pdf — multi-record (one invoice per page)
  2. 10 digital invoices from test_documents/01_invoices/
  3. Scanned docs from test_documents/07_scanned_docs/ — OCR check
"""
import asyncio, sys, os, time, json
sys.path.insert(0, os.path.dirname(__file__))

import logging
logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
# Silence noisy loggers, keep what matters
for noisy in ("httpx", "httpcore", "openai._base_client", "urllib3"):
    logging.getLogger(noisy).setLevel(logging.WARNING)

from app.services.pdf_service import parse_pdf
from app.services.extraction import (
    extract_single_record,
    LLMUsage,
)
from app.services.extraction.text_pipeline import extract_multi_record_chunked_validated

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


def _field_stats(rows, fields):
    field_names = [f["name"] for f in fields]
    filled = {fn: 0 for fn in field_names}
    errors = sum(1 for r in rows if r.get("_error"))
    data_rows = [r for r in rows if not r.get("_error")]
    for row in data_rows:
        for fn in field_names:
            v = row.get(fn)
            if v and str(v).strip().lower() not in ("null", "n/a", "none", ""):
                filled[fn] += 1
    return data_rows, errors, filled


async def test_single(path, fields, label):
    print(f"\n{'='*65}")
    print(f"SINGLE-RECORD: {label}")
    print(f"File: {os.path.basename(path)} ({os.path.getsize(path)//1024} KB)")
    print(f"{'='*65}")
    t0 = time.time()
    doc = await asyncio.to_thread(parse_pdf, path, os.path.basename(path))
    print(f"Pages: {doc.page_count} | Scanned: {doc.is_scanned} | Type: {doc.doc_type_hint}")
    usage = LLMUsage()
    rows = await extract_single_record(doc, fields, usage)
    elapsed = time.time() - t0
    data_rows, errors, filled = _field_stats(rows, fields)
    total = len(fields)
    hit = sum(1 for v in filled.values() if v > 0)
    print(f"Accuracy: {hit}/{total} fields   Cost: ${usage.cost_usd:.5f}   Time: {elapsed:.1f}s")
    if data_rows:
        for f in fields:
            v = data_rows[0].get(f["name"])
            ok = "✓" if filled[f["name"]] else "✗"
            print(f"  {ok}  {f['name']:25s} {str(v)[:60] if v else '[MISSING]'}")
    return usage.cost_usd, hit, total


async def test_multi(path, fields, label):
    print(f"\n{'='*65}")
    print(f"MULTI-RECORD: {label}")
    print(f"File: {os.path.basename(path)} ({os.path.getsize(path)//1024} KB)")
    print(f"{'='*65}")
    t0 = time.time()
    doc = await asyncio.to_thread(parse_pdf, path, os.path.basename(path))
    print(f"Pages: {doc.page_count} | Scanned: {doc.is_scanned} | Type: {doc.doc_type_hint}")
    usage = LLMUsage()
    rows = await extract_multi_record_chunked_validated(doc, fields, usage)
    elapsed = time.time() - t0
    data_rows, errors, filled = _field_stats(rows, fields)
    field_names = [f["name"] for f in fields]
    print(f"\nRows extracted: {len(data_rows)} data + {errors} errors")
    print(f"Time: {elapsed:.1f}s   Cost: ${usage.cost_usd:.5f}   Cost/row: ${usage.cost_usd/max(len(data_rows),1):.5f}")

    # Per-field fill rate
    print(f"\nField fill rates (across all rows):")
    for f in fields:
        fn = f["name"]
        pct = filled[fn] / max(len(data_rows), 1) * 100
        bar = "█" * int(pct / 5)
        print(f"  {fn:25s} {pct:5.1f}% {bar}")

    # Show first 5 rows
    if data_rows:
        print(f"\nFirst {min(5, len(data_rows))} rows:")
        for i, row in enumerate(data_rows[:5]):
            vals = {fn: str(row.get(fn, ""))[:40] for fn in field_names}
            print(f"  [{i+1}] {vals}")

    return usage.cost_usd, len(data_rows)


async def main():
    # ── 1. CustomerStatementReport: multi-record ────────────────────
    csr_path = "/Users/martinmashalov/Downloads/Papyra-renewals/backend/core/activity_automation/tools/reporting/data_storage_temp/CustomerStatementReport.pdf"
    await test_multi(csr_path, STATEMENT_FIELDS, "CustomerStatementReport.pdf (multi-record)")

    # ── 2. 10 digital invoices ──────────────────────────────────────
    invoice_dir = "/Users/martinmashalov/Downloads/GridPull/test_documents/01_invoices"
    invoice_files = sorted([
        os.path.join(invoice_dir, f)
        for f in os.listdir(invoice_dir)
        if f.endswith(".pdf")
    ])[:10]

    print(f"\n\n{'='*65}")
    print(f"BATCH: {len(invoice_files)} DIGITAL INVOICES")
    print(f"{'='*65}")
    costs, hits, totals = [], [], []
    for path in invoice_files:
        cost, hit, total = await test_single(path, INVOICE_FIELDS, f"Invoice: {os.path.basename(path)}")
        costs.append(cost)
        hits.append(hit)
        totals.append(total)

    print(f"\n{'='*65}")
    print(f"DIGITAL INVOICE SUMMARY ({len(costs)} docs)")
    print(f"  Avg accuracy:   {sum(hits)/len(hits):.1f}/{totals[0]} fields")
    print(f"  Avg cost/doc:   ${sum(costs)/len(costs):.5f}")
    print(f"  Total cost:     ${sum(costs):.5f}")
    print(f"{'='*65}")

    # ── 3. Scanned docs — OCR check ─────────────────────────────────
    scan_dir = "/Users/martinmashalov/Downloads/GridPull/test_documents/07_scanned_docs"
    scan_files = sorted([
        os.path.join(scan_dir, f)
        for f in os.listdir(scan_dir)
        if f.endswith(".pdf")
    ])

    print(f"\n\n{'='*65}")
    print(f"SCANNED DOCS — OCR CHECK ({len(scan_files)} files)")
    print(f"{'='*65}")
    for path in scan_files:
        doc = await asyncio.to_thread(parse_pdf, path, os.path.basename(path))
        pages_with_text = sum(1 for p in doc.pages if len(p.text.strip()) > 50)
        print(f"\n  File: {os.path.basename(path)}")
        print(f"  Pages: {doc.page_count} | Scanned: {doc.is_scanned} | Type: {doc.doc_type_hint}")
        print(f"  Pages with text (post-parse): {pages_with_text}/{doc.page_count}")
        if doc.is_scanned:
            print(f"  → OCR will be triggered for extraction ✓")
        else:
            print(f"  → Detected as digital, pypdf text used ✓")


if __name__ == "__main__":
    asyncio.run(main())
