"""Test the refactored extraction pipeline with three test cases.

Case 1: Individual invoices (strategy_individual)
Case 2: Annual report with multi-record data (strategy_multi_record)
Case 3: Customer statement PDF - page-per-row (strategy_page_per_row)
"""
import asyncio
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(__file__))
from dotenv import load_dotenv
load_dotenv()

from app.services.pdf_service import parse_pdf
from app.services.extraction import extract_from_document, LLMUsage


# Invoice fields
INVOICE_FIELDS = [
    {"name": "Invoice Number", "description": "Unique identifier assigned to the invoice"},
    {"name": "Date", "description": "Invoice issue date in MM/DD/YYYY format"},
    {"name": "Vendor Name", "description": "Company or vendor issuing the invoice"},
    {"name": "Description", "description": "Brief summary of goods/services billed"},
    {"name": "Amount", "description": "Total invoice amount including taxes"},
    {"name": "Tax Amount", "description": "Tax charged on the invoice"},
    {"name": "Due Date", "description": "Payment due date in MM/DD/YYYY format"},
]

# Annual report fields
ANNUAL_REPORT_FIELDS = [
    {"name": "Year", "description": "Fiscal year or period"},
    {"name": "Revenue", "description": "Total revenue or net sales"},
    {"name": "Net Income", "description": "Net income or net profit"},
    {"name": "Total Assets", "description": "Total assets"},
    {"name": "EPS", "description": "Earnings per share"},
]

# Customer statement fields (page per row)
STATEMENT_FIELDS = [
    {"name": "Customer Name", "description": "Name of the customer or account holder"},
    {"name": "Account Number", "description": "Customer account number or ID"},
    {"name": "Statement Date", "description": "Date of the statement"},
    {"name": "Balance Due", "description": "Total balance due or amount owed"},
    {"name": "Due Date", "description": "Payment due date"},
]


def print_results(label: str, rows: list, fields: list, usage: LLMUsage, elapsed: float):
    field_names = [f["name"] for f in fields]
    print(f"\n{'='*80}")
    print(f"  {label}")
    print(f"{'='*80}")
    print(f"  Rows: {len(rows)}")
    print(f"  Time: {elapsed:.1f}s")
    print(f"  Cost: ${usage.cost_usd:.4f}")
    cache_pct = (usage.cached_input_tokens / usage.input_tokens * 100) if usage.input_tokens else 0
    print(f"  Tokens: {usage.input_tokens + usage.output_tokens:,} "
          f"(in={usage.input_tokens:,} out={usage.output_tokens:,})")
    print(f"  Cached: {usage.cached_input_tokens:,}/{usage.input_tokens:,} input tokens ({cache_pct:.0f}%)")
    if usage.ocr_cost_usd > 0:
        print(f"  OCR cost: ${usage.ocr_cost_usd:.4f}")
    print()

    # Fill rate
    total_cells = len(rows) * len(field_names)
    filled_cells = sum(
        1 for row in rows for fn in field_names
        if row.get(fn) is not None
        and str(row[fn]).strip().lower() not in {"", "null", "none", "n/a", "na", "-", "—"}
    )
    fill_rate = (filled_cells / total_cells * 100) if total_cells > 0 else 0
    print(f"  Fill rate: {filled_cells}/{total_cells} ({fill_rate:.1f}%)")
    print()

    # Print first 10 rows
    for i, row in enumerate(rows[:10]):
        print(f"  Row {i+1}:")
        for fn in field_names:
            val = row.get(fn)
            display = str(val) if val is not None else "—"
            if len(display) > 80:
                display = display[:77] + "..."
            print(f"    {fn}: {display}")
        print()

    if len(rows) > 10:
        print(f"  ... and {len(rows) - 10} more rows")
    print()


async def test_case_1_invoices():
    """Test individual invoice extraction."""
    invoice_dir = "/Users/martinmashalov/Downloads/GridPull/test_documents/01_invoices"
    pdf_files = sorted([
        os.path.join(invoice_dir, f)
        for f in os.listdir(invoice_dir)
        if f.endswith(".pdf")
    ])[:5]  # Test with first 5

    print(f"\n[Case 1] Testing {len(pdf_files)} individual invoices...")
    all_rows = []
    total_usage = LLMUsage()
    start = time.time()

    for pdf_path in pdf_files:
        doc = parse_pdf(pdf_path)
        usage = LLMUsage()
        rows = await extract_from_document(
            doc, INVOICE_FIELDS, usage,
            batch_document_count=len(pdf_files),
            force_general=True,
        )
        all_rows.extend(rows)
        total_usage.input_tokens += usage.input_tokens
        total_usage.output_tokens += usage.output_tokens
        total_usage.cached_input_tokens += usage.cached_input_tokens
        total_usage.llm_cost_usd += usage.llm_cost_usd
        total_usage.ocr_cost_usd += usage.ocr_cost_usd

    elapsed = time.time() - start
    print_results("CASE 1: Individual Invoices", all_rows, INVOICE_FIELDS, total_usage, elapsed)
    return all_rows


async def test_case_2_annual_report():
    """Test multi-record extraction from annual report."""
    report_dir = "/Users/martinmashalov/Downloads/GridPull/test_documents/06_annual_reports"
    pdf_files = sorted([
        os.path.join(report_dir, f)
        for f in os.listdir(report_dir)
        if f.endswith(".pdf")
    ])[:1]  # Test with first file

    if not pdf_files:
        print("[Case 2] No PDF files found in annual_reports")
        return []

    print(f"\n[Case 2] Testing multi-record extraction from {os.path.basename(pdf_files[0])}...")
    start = time.time()
    doc = parse_pdf(pdf_files[0])
    usage = LLMUsage()
    rows = await extract_from_document(
        doc, ANNUAL_REPORT_FIELDS, usage,
        batch_document_count=1,
        force_general=True,
    )
    elapsed = time.time() - start
    print_results("CASE 2: Annual Report (multi-record)", rows, ANNUAL_REPORT_FIELDS, usage, elapsed)
    return rows


async def test_case_3_page_per_row():
    """Test page-per-row extraction from customer statement."""
    pdf_path = "/Users/martinmashalov/Downloads/Papyra-renewals/backend/core/activity_automation/tools/reporting/data_storage_temp_backup_20260218_172356/CustomerStatementReport.pdf"

    if not os.path.exists(pdf_path):
        print(f"[Case 3] File not found: {pdf_path}")
        return []

    print(f"\n[Case 3] Testing page-per-row extraction from CustomerStatementReport.pdf...")
    start = time.time()
    doc = parse_pdf(pdf_path)
    print(f"  Pages: {doc.page_count}")
    usage = LLMUsage()
    rows = await extract_from_document(
        doc, STATEMENT_FIELDS, usage,
        batch_document_count=1,
        force_general=True,
    )
    elapsed = time.time() - start
    print_results("CASE 3: Customer Statement (page-per-row)", rows, STATEMENT_FIELDS, usage, elapsed)
    return rows


async def main():
    print("=" * 80)
    print("  EXTRACTION REFACTOR TEST SUITE")
    print("=" * 80)

    results = {}

    try:
        results["invoices"] = await test_case_1_invoices()
    except Exception as e:
        print(f"[Case 1] FAILED: {e}")
        import traceback; traceback.print_exc()

    try:
        results["annual_report"] = await test_case_2_annual_report()
    except Exception as e:
        print(f"[Case 2] FAILED: {e}")
        import traceback; traceback.print_exc()

    try:
        results["page_per_row"] = await test_case_3_page_per_row()
    except Exception as e:
        print(f"[Case 3] FAILED: {e}")
        import traceback; traceback.print_exc()

    # Summary
    print("\n" + "=" * 80)
    print("  SUMMARY")
    print("=" * 80)
    for case, rows in results.items():
        if rows:
            field_count = 7 if case == "invoices" else 5
            total = len(rows) * field_count
            filled = sum(
                1 for row in rows
                for fn in (INVOICE_FIELDS if case == "invoices" else ANNUAL_REPORT_FIELDS if case == "annual_report" else STATEMENT_FIELDS)
                if row.get(fn["name"]) is not None
                and str(row[fn["name"]]).strip().lower() not in {"", "null", "none", "n/a"}
            )
            print(f"  {case}: {len(rows)} rows, fill rate {filled}/{total} ({filled/total*100:.1f}%)")
        else:
            print(f"  {case}: FAILED")


if __name__ == "__main__":
    asyncio.run(main())
