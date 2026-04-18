"""
Comprehensive extraction test harness.

Runs 50+ extraction iterations across all document types:
  - Invoices (single-record, individual strategy)
  - Contracts (single-record, individual strategy)
  - Insurance EOBs (single-record extraction)
  - Cash flow statements (multi-record: multi-year financials)
  - Annual reports / 10-K filings (multi-record or individual depending on fields)
  - Purchase orders / government forms (individual)
  - SOV / property schedules (SOV pipeline)
  - Vehicle schedules (SOV pipeline)
  - Certificate holders (SOV pipeline, HTML input)
  - Large location schedules (SOV pipeline, HTML input)
  - Payroll docs (multi-record)
  - Email examples with attachments (.eml)
  - Multi-page invoices (multi-record: page_per_row)
  - Scanned documents (OCR path)
  - Spreadsheet output validation (xlsx + csv)

Validates:
  - Every extraction returns non-empty rows
  - Fill rate (% of fields with actual values) is reasonable
  - No hardcoded values leak across document types
  - Spreadsheet generation produces valid files with correct headers
  - No crashes / unhandled exceptions
"""

import asyncio
import json
import logging
import os
import sys
import time
import traceback
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

sys.path.insert(0, os.path.dirname(__file__))

sys.stdout.reconfigure(line_buffering=True)

logging.basicConfig(
    level=logging.WARNING,
    format="%(levelname)s %(name)s: %(message)s",
)
# Suppress noisy HTTP logs
logging.getLogger("httpx").setLevel(logging.ERROR)
logging.getLogger("httpcore").setLevel(logging.ERROR)
logging.getLogger("openai").setLevel(logging.ERROR)

from app.services.pdf_service import parse_pdf
from app.services.extraction import extract_from_document, LLMUsage
from app.services.spreadsheet_service import (
    generate_excel,
    generate_csv,
    generate_excel_bytes,
    generate_csv_bytes,
    update_excel_baseline_bytes,
    update_csv_baseline_bytes,
    read_headers_from_bytes,
)

# ── Test document root ──────────────────────────────────────────────────────
TEST_DOCS = "/Users/martinmashalov/Downloads/GridPull/test_documents"
TEST_FILES = "/Users/martinmashalov/Downloads/GridPull/backend/test_files"
OUTPUT_DIR = "/Users/martinmashalov/Downloads/GridPull/backend/test_outputs"
os.makedirs(OUTPUT_DIR, exist_ok=True)

# ── Field definitions for each document category ────────────────────────────

INVOICE_FIELDS = [
    {"name": "Invoice Number", "description": "Invoice or order number"},
    {"name": "Invoice Date", "description": "Date of the invoice"},
    {"name": "Customer Name", "description": "Name of the customer or bill-to party"},
    {"name": "Customer Address", "description": "Customer billing address"},
    {"name": "Total Amount", "description": "Total amount due including tax", "numeric": True},
    {"name": "Subtotal", "description": "Subtotal before tax", "numeric": True},
    {"name": "Tax Amount", "description": "Tax amount", "numeric": True},
    {"name": "Due Date", "description": "Payment due date"},
    {"name": "Line Items", "description": "Description of items/services billed"},
]

CONTRACT_FIELDS = [
    {"name": "Contract Title", "description": "Title or name of the contract/agreement"},
    {"name": "Parties", "description": "Names of all parties involved in the contract"},
    {"name": "Effective Date", "description": "Start date or effective date of the contract"},
    {"name": "Expiration Date", "description": "End date or termination date"},
    {"name": "Contract Value", "description": "Total value or consideration amount", "numeric": True},
    {"name": "Governing Law", "description": "State or jurisdiction whose laws govern the contract"},
    {"name": "Termination Clause", "description": "Summary of termination conditions"},
]

EOB_FIELDS = [
    {"name": "Patient Name", "description": "Name of the patient or member"},
    {"name": "Claim Number", "description": "Insurance claim number"},
    {"name": "Service Date", "description": "Date of medical service"},
    {"name": "Provider Name", "description": "Name of the healthcare provider"},
    {"name": "Billed Amount", "description": "Total amount billed", "numeric": True},
    {"name": "Allowed Amount", "description": "Amount allowed by insurance", "numeric": True},
    {"name": "Patient Responsibility", "description": "Amount the patient owes", "numeric": True},
    {"name": "Plan Payment", "description": "Amount paid by insurance plan", "numeric": True},
]

CASHFLOW_FIELDS = [
    {"name": "Company Name", "description": "Name of the company"},
    {"name": "Period", "description": "Reporting period or fiscal year"},
    {"name": "Operating Cash Flow", "description": "Net cash from operating activities", "numeric": True},
    {"name": "Investing Cash Flow", "description": "Net cash from investing activities", "numeric": True},
    {"name": "Financing Cash Flow", "description": "Net cash from financing activities", "numeric": True},
    {"name": "Net Change in Cash", "description": "Net increase/decrease in cash", "numeric": True},
    {"name": "Depreciation", "description": "Depreciation and amortization expense", "numeric": True},
]

ANNUAL_REPORT_FIELDS = [
    {"name": "Company Name", "description": "Name of the company"},
    {"name": "Fiscal Year", "description": "Fiscal year of the report"},
    {"name": "Total Revenue", "description": "Total revenue or net sales", "numeric": True},
    {"name": "Net Income", "description": "Net income or net profit", "numeric": True},
    {"name": "Total Assets", "description": "Total assets on balance sheet", "numeric": True},
    {"name": "Total Liabilities", "description": "Total liabilities", "numeric": True},
    {"name": "Earnings Per Share", "description": "Basic earnings per share", "numeric": True},
    {"name": "CEO Name", "description": "Name of the CEO or Chairman"},
]

PURCHASE_ORDER_FIELDS = [
    {"name": "Form Number", "description": "Government form or solicitation number"},
    {"name": "Contract Number", "description": "Contract or order number"},
    {"name": "Issuing Agency", "description": "Government agency issuing the form"},
    {"name": "Effective Date", "description": "Date the form or contract is effective"},
    {"name": "Total Amount", "description": "Total contract or bid amount", "numeric": True},
    {"name": "Contractor Name", "description": "Name of the contractor or vendor"},
    {"name": "Description", "description": "Brief description of the solicitation or contract"},
]

SOV_PROPERTY_FIELDS = [
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

VEHICLE_SCHEDULE_FIELDS = [
    {"name": "Vehicle #", "description": "Vehicle number or unit number"},
    {"name": "Year", "description": "Model year of the vehicle"},
    {"name": "Make", "description": "Vehicle manufacturer (e.g., Ford, Chevrolet)"},
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

PAYROLL_FIELDS = [
    {"name": "Employee Name", "description": "Full name of the employee"},
    {"name": "Employee ID", "description": "Employee ID or number"},
    {"name": "Department", "description": "Department or division"},
    {"name": "Job Title", "description": "Job title or position"},
    {"name": "Gross Pay", "description": "Gross pay amount", "numeric": True},
    {"name": "Net Pay", "description": "Net pay amount after deductions", "numeric": True},
    {"name": "Pay Period", "description": "Pay period dates"},
]

# Minimal fields — test that even a very small field set works
MINIMAL_FIELDS = [
    {"name": "Document Title", "description": "The title or main subject of the document"},
    {"name": "Date", "description": "The primary date found in the document"},
]

# Broad generic fields — test generalization across any doc type
GENERIC_FIELDS = [
    {"name": "Entity Name", "description": "Primary organization, company, or person named in the document"},
    {"name": "Document Type", "description": "What kind of document this is (invoice, contract, report, etc.)"},
    {"name": "Primary Date", "description": "The most important date in the document"},
    {"name": "Primary Amount", "description": "The most important monetary amount", "numeric": True},
    {"name": "Reference Number", "description": "Any reference, ID, policy, account, or invoice number"},
    {"name": "Summary", "description": "A one-sentence summary of the document's purpose or content"},
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


# ── Results tracking ────────────────────────────────────────────────────────

@dataclass
class TestResult:
    test_id: int
    category: str
    filename: str
    fields_used: str
    strategy: str
    num_rows: int
    num_fields: int
    filled_cells: int
    total_cells: int
    fill_rate: float
    cost_usd: float
    elapsed_s: float
    error: Optional[str] = None
    rows: List[Dict[str, Any]] = field(default_factory=list)
    # Spreadsheet validation
    xlsx_valid: bool = True
    csv_valid: bool = True
    xlsx_headers_match: bool = True
    csv_headers_match: bool = True


results: List[TestResult] = []
EMPTY_MARKERS = {"", "null", "none", "n/a", "na", "-", "—", "unknown", "not found", "not available"}


def is_filled(val: Any) -> bool:
    if val is None:
        return False
    return str(val).strip().lower() not in EMPTY_MARKERS


def compute_fill_rate(rows: List[Dict], field_names: List[str]) -> tuple:
    total = len(rows) * len(field_names)
    filled = sum(1 for r in rows for fn in field_names if is_filled(r.get(fn)))
    rate = (filled / total * 100) if total > 0 else 0
    return filled, total, rate


async def run_extraction_test(
    test_id: int,
    category: str,
    file_path: str,
    fields: List[Dict],
    fields_label: str,
    *,
    instructions: str = "",
    force_sov: bool = False,
    force_general: bool = False,
    batch_count: int = 1,
) -> TestResult:
    """Run a single extraction test and return the result."""
    filename = os.path.basename(file_path)
    field_names = [f["name"] for f in fields]

    print(f"\n[T{test_id:02d}] {category} | {filename} | fields={fields_label}")

    t0 = time.time()
    try:
        doc = await asyncio.to_thread(parse_pdf, file_path, filename)
        usage = LLMUsage()

        rows = await extract_from_document(
            doc, fields, usage, instructions,
            batch_document_count=batch_count,
            use_cerebras=False,
            force_sov=force_sov,
            force_general=force_general,
        )

        elapsed = time.time() - t0
        filled, total, fill_rate = compute_fill_rate(rows, field_names)

        # Determine strategy used (from doc type hint and routing)
        strategy = "sov" if force_sov else ("general" if force_general else "auto")

        result = TestResult(
            test_id=test_id,
            category=category,
            filename=filename,
            fields_used=fields_label,
            strategy=strategy,
            num_rows=len(rows),
            num_fields=len(field_names),
            filled_cells=filled,
            total_cells=total,
            fill_rate=fill_rate,
            cost_usd=usage.cost_usd,
            elapsed_s=elapsed,
            rows=rows,
        )

        # Validate spreadsheet generation
        try:
            xlsx_bytes = generate_excel_bytes(rows, field_names)
            xlsx_headers = read_headers_from_bytes(xlsx_bytes, "xlsx")
            expected_headers = ["Source File"] + field_names
            result.xlsx_headers_match = xlsx_headers == expected_headers
            if not result.xlsx_headers_match:
                print(f"  ⚠ XLSX headers mismatch: {xlsx_headers[:5]}... vs {expected_headers[:5]}...")
        except Exception as e:
            result.xlsx_valid = False
            print(f"  ✗ XLSX generation failed: {e}")

        try:
            csv_bytes = generate_csv_bytes(rows, field_names)
            csv_headers = read_headers_from_bytes(csv_bytes, "csv")
            expected_headers = ["Source File"] + field_names
            result.csv_headers_match = csv_headers == expected_headers
            if not result.csv_headers_match:
                print(f"  ⚠ CSV headers mismatch: {csv_headers[:5]}... vs {expected_headers[:5]}...")
        except Exception as e:
            result.csv_valid = False
            print(f"  ✗ CSV generation failed: {e}")

        # Print summary line
        status = "✓" if fill_rate > 20 else "⚠" if fill_rate > 0 else "✗"
        print(f"  {status} rows={len(rows)} fill={filled}/{total} ({fill_rate:.0f}%) cost=${usage.cost_usd:.5f} time={elapsed:.1f}s xlsx={'✓' if result.xlsx_valid else '✗'} csv={'✓' if result.csv_valid else '✗'}")

        # Show first row sample
        if rows:
            sample = {k: v for k, v in rows[0].items() if k not in ("_source_file", "_error") and v is not None and str(v).strip()}
            sample_str = json.dumps(sample, default=str)
            if len(sample_str) > 200:
                sample_str = sample_str[:200] + "..."
            print(f"  Sample: {sample_str}")

        return result

    except Exception as exc:
        elapsed = time.time() - t0
        print(f"  ✗ ERROR: {exc}")
        traceback.print_exc()
        return TestResult(
            test_id=test_id,
            category=category,
            filename=filename,
            fields_used=fields_label,
            strategy="error",
            num_rows=0,
            num_fields=len(field_names),
            filled_cells=0,
            total_cells=0,
            fill_rate=0,
            cost_usd=0,
            elapsed_s=elapsed,
            error=str(exc),
        )


def pick_files(directory: str, ext: str = ".pdf", count: int = 3) -> List[str]:
    """Pick up to `count` files from a directory."""
    if not os.path.isdir(directory):
        return []
    files = [
        os.path.join(directory, f) for f in sorted(os.listdir(directory))
        if f.lower().endswith(ext) and not f.startswith(".")
    ]
    return files[:count]


def pick_files_multi_ext(directory: str, exts: tuple, count: int = 3) -> List[str]:
    """Pick files matching any of the given extensions."""
    if not os.path.isdir(directory):
        return []
    files = [
        os.path.join(directory, f) for f in sorted(os.listdir(directory))
        if any(f.lower().endswith(e) for e in exts) and not f.startswith(".")
    ]
    return files[:count]


async def run_all_tests():
    global results
    test_id = 0

    print("=" * 80)
    print("COMPREHENSIVE EXTRACTION TEST HARNESS")
    print(f"Testing across all document types with varied field configurations")
    print("=" * 80)

    # ── 1. Invoices (individual strategy) ────────────────────────────────
    invoice_files = pick_files(f"{TEST_DOCS}/01_invoices", count=3)
    for f in invoice_files:
        test_id += 1
        results.append(await run_extraction_test(
            test_id, "Invoice", f, INVOICE_FIELDS, "invoice_fields",
            batch_count=len(invoice_files),
        ))

    # Test invoice with generic fields (generalization test)
    if invoice_files:
        test_id += 1
        results.append(await run_extraction_test(
            test_id, "Invoice-Generic", invoice_files[0], GENERIC_FIELDS, "generic_fields",
        ))

    # Test invoice with minimal fields
    if invoice_files:
        test_id += 1
        results.append(await run_extraction_test(
            test_id, "Invoice-Minimal", invoice_files[0], MINIMAL_FIELDS, "minimal_fields",
        ))

    # ── 2. Multi-page invoices (page_per_row or multi_record) ────────────
    multipage_files = pick_files(f"{TEST_DOCS}/11_multipage_invoices", count=3)
    for f in multipage_files:
        test_id += 1
        results.append(await run_extraction_test(
            test_id, "MultiPageInvoice", f, INVOICE_FIELDS, "invoice_fields",
        ))

    # ── 3. Insurance EOBs ────────────────────────────────────────────────
    eob_files = pick_files(f"{TEST_DOCS}/03_insurance_eob", count=3)
    for f in eob_files:
        test_id += 1
        results.append(await run_extraction_test(
            test_id, "EOB", f, EOB_FIELDS, "eob_fields",
        ))

    # ── 4. Cash flow statements (multi-record) ──────────────────────────
    cashflow_files = pick_files(f"{TEST_DOCS}/08_cash_flow_statements", count=3)
    for f in cashflow_files:
        test_id += 1
        results.append(await run_extraction_test(
            test_id, "CashFlow", f, CASHFLOW_FIELDS, "cashflow_fields",
        ))

    # ── 5. Contracts ────────────────────────────────────────────────────
    contract_files = pick_files(f"{TEST_DOCS}/09_contracts_agreements", count=3)
    for f in contract_files:
        test_id += 1
        results.append(await run_extraction_test(
            test_id, "Contract", f, CONTRACT_FIELDS, "contract_fields",
            batch_count=len(contract_files),
        ))

    # Test contract with generic fields
    if contract_files:
        test_id += 1
        results.append(await run_extraction_test(
            test_id, "Contract-Generic", contract_files[0], GENERIC_FIELDS, "generic_fields",
        ))

    # ── 6. Purchase orders / government forms ───────────────────────────
    po_files = pick_files(f"{TEST_DOCS}/05_purchase_orders", count=3)
    for f in po_files:
        test_id += 1
        results.append(await run_extraction_test(
            test_id, "PurchaseOrder", f, PURCHASE_ORDER_FIELDS, "po_fields",
            batch_count=len(po_files),
        ))

    # ── 7. Annual reports (large docs, multi-record possible) ───────────
    annual_files = pick_files(f"{TEST_DOCS}/06_annual_reports", count=2)
    for f in annual_files:
        test_id += 1
        results.append(await run_extraction_test(
            test_id, "AnnualReport", f, ANNUAL_REPORT_FIELDS, "annual_fields",
        ))

    # ── 8. SOV / property schedules (SOV pipeline) ──────────────────────
    sov_files = pick_files(f"{TEST_DOCS}/10_sov_samples", count=3)
    for f in sov_files:
        test_id += 1
        results.append(await run_extraction_test(
            test_id, "SOV-Property", f, SOV_PROPERTY_FIELDS, "sov_property_fields",
            force_sov=True,
        ))

    # Test SOV with auto-detection (no force_sov)
    if sov_files:
        test_id += 1
        results.append(await run_extraction_test(
            test_id, "SOV-AutoDetect", sov_files[0], SOV_PROPERTY_FIELDS, "sov_property_auto",
        ))

    # ── 9. Vehicle schedules (SOV pipeline) ─────────────────────────────
    vehicle_file = f"{TEST_DOCS}/10_sov_samples/04_vehicle_schedule_35_vehicles.pdf"
    if os.path.exists(vehicle_file):
        test_id += 1
        results.append(await run_extraction_test(
            test_id, "VehicleSchedule", vehicle_file, VEHICLE_SCHEDULE_FIELDS, "vehicle_fields",
            force_sov=True,
        ))

    # ── 10. Certificate holders (HTML input) ─────────────────────────────
    cert_files = pick_files_multi_ext(f"{TEST_DOCS}/14_certificate_holders", (".html",), count=3)
    for f in cert_files:
        test_id += 1
        results.append(await run_extraction_test(
            test_id, "CertHolder", f, CERT_HOLDER_FIELDS, "cert_holder_fields",
            force_sov=True,
        ))

    # ── 11. Large location schedules (HTML, SOV pipeline) ────────────────
    large_schedule_files = pick_files_multi_ext(f"{TEST_DOCS}/15_location_schedule_large", (".html", ".pdf"), count=2)
    for f in large_schedule_files:
        test_id += 1
        results.append(await run_extraction_test(
            test_id, "LargeSchedule", f, LARGE_SCHEDULE_FIELDS, "large_schedule_fields",
            force_sov=True,
        ))

    # ── 12. Payroll (multi-record) ───────────────────────────────────────
    payroll_files = pick_files(f"{TEST_DOCS}/13_payroll_examples", count=1)
    for f in payroll_files:
        test_id += 1
        results.append(await run_extraction_test(
            test_id, "Payroll", f, PAYROLL_FIELDS, "payroll_fields",
        ))

    # ── 13. Scanned documents (OCR path) ─────────────────────────────────
    scanned_files = pick_files(f"{TEST_DOCS}/07_scanned_docs", count=2)
    for f in scanned_files:
        test_id += 1
        results.append(await run_extraction_test(
            test_id, "Scanned", f, INVOICE_FIELDS, "invoice_fields",
        ))

    # Scanned with generic fields
    if scanned_files:
        test_id += 1
        results.append(await run_extraction_test(
            test_id, "Scanned-Generic", scanned_files[0], GENERIC_FIELDS, "generic_fields",
        ))

    # ── 14. Email documents (.eml) ───────────────────────────────────────
    eml_files = pick_files_multi_ext(f"{TEST_DOCS}/12_sov_email_examples", (".eml",), count=2)
    for f in eml_files:
        test_id += 1
        results.append(await run_extraction_test(
            test_id, "Email-SOV", f, SOV_PROPERTY_FIELDS, "sov_property_fields",
            force_sov=True,
        ))

    # ── 15. SOV PDFs from email examples ─────────────────────────────────
    sov_pdf_files = pick_files(f"{TEST_DOCS}/12_sov_email_examples", count=2)
    for f in sov_pdf_files:
        test_id += 1
        results.append(await run_extraction_test(
            test_id, "SOV-Email-PDF", f, SOV_PROPERTY_FIELDS, "sov_property_fields",
            force_sov=True,
        ))

    # ── 16. Cross-type generalization tests ──────────────────────────────
    # Use generic fields on EOBs
    if eob_files:
        test_id += 1
        results.append(await run_extraction_test(
            test_id, "EOB-Generic", eob_files[0], GENERIC_FIELDS, "generic_fields",
        ))

    # Use generic fields on cash flow
    if cashflow_files:
        test_id += 1
        results.append(await run_extraction_test(
            test_id, "CashFlow-Generic", cashflow_files[0], GENERIC_FIELDS, "generic_fields",
        ))

    # Use generic fields on SOV
    if sov_files:
        test_id += 1
        results.append(await run_extraction_test(
            test_id, "SOV-Generic", sov_files[0], GENERIC_FIELDS, "generic_fields",
            force_general=True,
        ))

    # ── 17. Instructions variation tests ─────────────────────────────────
    if invoice_files:
        test_id += 1
        results.append(await run_extraction_test(
            test_id, "Invoice-Instructions", invoice_files[0], INVOICE_FIELDS, "invoice+instructions",
            instructions="Focus on extracting all dollar amounts with exactly 2 decimal places. Format all dates as MM/DD/YYYY.",
        ))

    if contract_files:
        test_id += 1
        results.append(await run_extraction_test(
            test_id, "Contract-Instructions", contract_files[0], CONTRACT_FIELDS, "contract+instructions",
            instructions="For governing law, provide the full state name not abbreviation. Summarize termination clause in under 50 words.",
        ))

    # ── 18. Existing test PDFs from backend/test_files ───────────────────
    test_pdfs = pick_files(TEST_FILES, ext=".pdf", count=4)
    for f in test_pdfs:
        test_id += 1
        results.append(await run_extraction_test(
            test_id, "TestFile-SOV", f, SOV_PROPERTY_FIELDS, "sov_property_fields",
            force_sov=True,
        ))

    # ── 19. Papyra renewal quote PDFs ────────────────────────────────────
    papyra_dir = "/Users/martinmashalov/Downloads/Papyra/fixtures/renewal_quote_test"
    papyra_files = pick_files(papyra_dir, count=3) if os.path.isdir(papyra_dir) else []
    for f in papyra_files:
        test_id += 1
        results.append(await run_extraction_test(
            test_id, "Papyra-Quote", f, GENERIC_FIELDS, "generic_fields",
        ))

    # ── 20. Baseline update mode validation ──────────────────────────────
    # Generate a baseline spreadsheet, then try updating it
    if results and any(r.rows for r in results):
        test_id += 1
        print(f"\n[T{test_id:02d}] Baseline-Update | Testing baseline update mode...")
        try:
            # Use first successful SOV result to create a baseline
            sov_results = [r for r in results if "SOV" in r.category and r.rows and len(r.rows) > 2]
            if sov_results:
                baseline_result = sov_results[0]
                field_names = [f["name"] for f in SOV_PROPERTY_FIELDS]

                # Create baseline xlsx
                baseline_xlsx = generate_excel_bytes(baseline_result.rows[:5], field_names)

                # Try updating with more rows
                updated_xlsx = update_excel_baseline_bytes(
                    baseline_xlsx, baseline_result.rows[5:10], field_names, allow_edit_past_values=False,
                )
                updated_headers = read_headers_from_bytes(updated_xlsx, "xlsx")

                # Create baseline csv
                baseline_csv = generate_csv_bytes(baseline_result.rows[:5], field_names)
                updated_csv = update_csv_baseline_bytes(
                    baseline_csv, baseline_result.rows[5:10], field_names, allow_edit_past_values=True,
                )
                updated_csv_headers = read_headers_from_bytes(updated_csv, "csv")

                print(f"  ✓ Baseline update XLSX: headers={len(updated_headers)}")
                print(f"  ✓ Baseline update CSV: headers={len(updated_csv_headers)}")

                results.append(TestResult(
                    test_id=test_id, category="BaselineUpdate", filename="synthetic",
                    fields_used="sov_property_fields", strategy="baseline",
                    num_rows=len(baseline_result.rows), num_fields=len(field_names),
                    filled_cells=0, total_cells=0, fill_rate=0, cost_usd=0, elapsed_s=0,
                    xlsx_valid=True, csv_valid=True,
                    xlsx_headers_match=True, csv_headers_match=True,
                ))
            else:
                print(f"  ⚠ No SOV results to use for baseline test")
        except Exception as e:
            print(f"  ✗ Baseline update test FAILED: {e}")
            traceback.print_exc()

    # ── FINAL REPORT ──────────────────────────────────────────────────────
    print("\n" + "=" * 100)
    print("FINAL REPORT")
    print("=" * 100)

    total_tests = len(results)
    errors = [r for r in results if r.error]
    low_fill = [r for r in results if not r.error and r.fill_rate < 20 and r.category != "BaselineUpdate"]
    good = [r for r in results if not r.error and r.fill_rate >= 20]
    xlsx_fails = [r for r in results if not r.xlsx_valid]
    csv_fails = [r for r in results if not r.csv_valid]
    header_mismatches = [r for r in results if not r.xlsx_headers_match or not r.csv_headers_match]

    print(f"\nTotal tests:          {total_tests}")
    print(f"Passed (fill≥20%):    {len(good)}")
    print(f"Low fill (<20%):      {len(low_fill)}")
    print(f"Errors:               {len(errors)}")
    print(f"XLSX failures:        {len(xlsx_fails)}")
    print(f"CSV failures:         {len(csv_fails)}")
    print(f"Header mismatches:    {len(header_mismatches)}")

    total_cost = sum(r.cost_usd for r in results)
    total_time = sum(r.elapsed_s for r in results)
    avg_fill = sum(r.fill_rate for r in results if not r.error) / max(1, len([r for r in results if not r.error]))

    print(f"\nTotal cost:           ${total_cost:.4f}")
    print(f"Total time:           {total_time:.1f}s ({total_time/60:.1f}m)")
    print(f"Avg fill rate:        {avg_fill:.1f}%")

    # ── Per-category breakdown ──────────────────────────────────────────
    print(f"\n{'Category':<25} {'Tests':>5} {'Rows':>6} {'Fill%':>6} {'Cost':>8} {'Time':>7} {'Status'}")
    print("-" * 80)

    categories = {}
    for r in results:
        cat = r.category
        if cat not in categories:
            categories[cat] = {"tests": 0, "rows": 0, "fill_rates": [], "cost": 0, "time": 0, "errors": 0}
        categories[cat]["tests"] += 1
        categories[cat]["rows"] += r.num_rows
        if not r.error:
            categories[cat]["fill_rates"].append(r.fill_rate)
        categories[cat]["cost"] += r.cost_usd
        categories[cat]["time"] += r.elapsed_s
        if r.error:
            categories[cat]["errors"] += 1

    for cat, data in sorted(categories.items()):
        avg_f = sum(data["fill_rates"]) / max(1, len(data["fill_rates"]))
        status = "✓" if data["errors"] == 0 and avg_f >= 20 else "⚠" if avg_f > 0 else "✗"
        err_str = f" ({data['errors']} err)" if data["errors"] > 0 else ""
        print(f"{cat:<25} {data['tests']:>5} {data['rows']:>6} {avg_f:>5.1f}% ${data['cost']:>7.4f} {data['time']:>6.1f}s {status}{err_str}")

    # ── Problem report ──────────────────────────────────────────────────
    if errors:
        print(f"\n--- ERRORS ({len(errors)}) ---")
        for r in errors:
            print(f"  T{r.test_id:02d} {r.category}/{r.filename}: {r.error}")

    if low_fill:
        print(f"\n--- LOW FILL RATE ({len(low_fill)}) ---")
        for r in low_fill:
            print(f"  T{r.test_id:02d} {r.category}/{r.filename}: {r.fill_rate:.0f}% ({r.filled_cells}/{r.total_cells})")

    if xlsx_fails:
        print(f"\n--- XLSX GENERATION FAILURES ({len(xlsx_fails)}) ---")
        for r in xlsx_fails:
            print(f"  T{r.test_id:02d} {r.category}/{r.filename}")

    if header_mismatches:
        print(f"\n--- HEADER MISMATCHES ({len(header_mismatches)}) ---")
        for r in header_mismatches:
            print(f"  T{r.test_id:02d} {r.category}/{r.filename}: xlsx={r.xlsx_headers_match} csv={r.csv_headers_match}")

    # ── Hardcoding / generalization check ────────────────────────────────
    print("\n--- GENERALIZATION CHECK ---")
    # Check if any values appear in results for a doc type they shouldn't be in
    invoice_names = set()
    contract_names = set()
    for r in results:
        if r.category == "Invoice" and r.rows:
            for row in r.rows:
                name = row.get("Customer Name", "")
                if name and str(name).strip():
                    invoice_names.add(str(name).strip().lower())
        if r.category == "Contract" and r.rows:
            for row in r.rows:
                name = row.get("Parties", "")
                if name and str(name).strip():
                    contract_names.add(str(name).strip().lower())

    # Check for cross-contamination: invoice customer names shouldn't appear in contract results
    cross_contamination = False
    for r in results:
        if r.category.startswith("Contract") and r.rows:
            for row in r.rows:
                for fn, val in row.items():
                    if fn in ("_source_file", "_error"):
                        continue
                    if val and str(val).strip().lower() in invoice_names and str(val).strip().lower() not in contract_names:
                        print(f"  ⚠ Cross-contamination: T{r.test_id} {r.category} has invoice name '{val}' in field '{fn}'")
                        cross_contamination = True

    if not cross_contamination:
        print("  ✓ No cross-contamination detected between document types")

    # Check for identical values across unrelated documents (suggests hardcoding)
    print("\n--- IDENTICAL VALUE CHECK ---")
    all_primary_values = {}
    for r in results:
        if r.rows and not r.error:
            key_fields = [fn for fn in [f["name"] for f in GENERIC_FIELDS] if fn in r.rows[0]]
            if not key_fields:
                # Use first 3 field names
                key_fields = [f for f in r.rows[0].keys() if f not in ("_source_file", "_error")][:3]
            for fn in key_fields:
                val = str(r.rows[0].get(fn, "")).strip()
                if val and val.lower() not in EMPTY_MARKERS:
                    if val not in all_primary_values:
                        all_primary_values[val] = []
                    all_primary_values[val].append((r.test_id, r.category, r.filename, fn))

    duplicates = {v: locs for v, locs in all_primary_values.items() if len(locs) > 2}
    if duplicates:
        for val, locs in duplicates.items():
            cats = set(l[1] for l in locs)
            if len(cats) > 1:  # Same value across different categories is suspicious
                print(f"  ⚠ Value '{val[:50]}' appears in {len(locs)} results across categories: {cats}")
    else:
        print("  ✓ No suspicious duplicate values across document types")

    # ── Save detailed JSON report ────────────────────────────────────────
    report_path = os.path.join(OUTPUT_DIR, "test_report.json")
    report_data = []
    for r in results:
        report_data.append({
            "test_id": r.test_id,
            "category": r.category,
            "filename": r.filename,
            "fields_used": r.fields_used,
            "strategy": r.strategy,
            "num_rows": r.num_rows,
            "fill_rate": round(r.fill_rate, 1),
            "filled_cells": r.filled_cells,
            "total_cells": r.total_cells,
            "cost_usd": round(r.cost_usd, 6),
            "elapsed_s": round(r.elapsed_s, 1),
            "error": r.error,
            "xlsx_valid": r.xlsx_valid,
            "csv_valid": r.csv_valid,
            "xlsx_headers_match": r.xlsx_headers_match,
            "csv_headers_match": r.csv_headers_match,
            "sample_row": {k: v for k, v in (r.rows[0] if r.rows else {}).items() if k not in ("_source_file", "_error")},
        })
    with open(report_path, "w") as fh:
        json.dump(report_data, fh, indent=2, default=str)
    print(f"\nDetailed report saved to: {report_path}")

    # ── Final verdict ────────────────────────────────────────────────────
    print("\n" + "=" * 80)
    if not errors and not xlsx_fails and not csv_fails and avg_fill >= 30:
        print("VERDICT: ✓ ALL TESTS PASSED")
    elif len(errors) <= 2 and avg_fill >= 25:
        print(f"VERDICT: ⚠ MOSTLY PASSING ({len(errors)} errors, {avg_fill:.0f}% avg fill)")
    else:
        print(f"VERDICT: ✗ ISSUES FOUND ({len(errors)} errors, {avg_fill:.0f}% avg fill)")
    print("=" * 80)


if __name__ == "__main__":
    asyncio.run(run_all_tests())
