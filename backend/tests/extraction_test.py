"""
Enterprise extraction test suite.

Runs the full extraction pipeline against all test document sets and
reports quality metrics (FFR / NPR / DPR / ERR) per folder and overall.

Test Coverage:
  • 01_invoices: Vendor invoices
  • 02_sec_annual_report: Large financial documents
  • 03_insurance_eob: Insurance claims (original + 30 new synthetic EOBs)
  • 04_sec_10k_filing: SEC 10-K filings
  • 05_purchase_orders: Government procurement forms
  • 06_annual_reports: Diverse annual reports
  • 07_scanned_docs: OCR/scanned documents
  • 08_cash_flow_statements: Corporate cash flow statements (NEW)
  • 09_contracts_agreements: Legal contracts & agreements (NEW)

Usage:
    cd backend
    OPENAI_API_KEY=sk-... python tests/extraction_test.py [--folder <name>] [--verbose]

Target metrics (all figures 0-1):
    FFR  ≥ 0.90 (field fill rate)
    NPR  ≥ 0.95 (numeric parse rate)
    DPR  ≥ 0.95 (date parse rate)
    ERR  = 0.00 (error row rate)

Benchmarking:
    Measures extraction speed, throughput, and quality across all document types.
    Reports per-document and per-folder performance metrics.
"""

from __future__ import annotations

import argparse
import asyncio
import glob
import json
import os
import sys
import time
from pathlib import Path
from typing import Dict, List

# ── Bootstrap path so imports work without installing the package ─────────────
_BACKEND = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_BACKEND))

# Load .env before importing app modules
try:
    from dotenv import load_dotenv
    load_dotenv(_BACKEND / ".env")
except ImportError:
    pass  # python-dotenv optional; rely on env vars already set

from app.models.extraction import Document                               # noqa: E402
from app.services.extraction_service import extract_from_document, LLMUsage  # noqa: E402
from app.services.pdf_service import parse_pdf                      # noqa: E402
from app.services.validator_service import ValidationReport, score_extraction  # noqa: E402

_TEST_DOCS = Path(__file__).resolve().parent.parent.parent / "test_documents"

# ── Targets ───────────────────────────────────────────────────────────────────

FFR_TARGET = 0.90
NPR_TARGET = 0.95
DPR_TARGET = 0.95


# ── Test case definitions ─────────────────────────────────────────────────────

TEST_CASES: List[Dict] = [
    {
        "folder": "01_invoices",
        "description": "Vendor invoices — one row per document",
        # Due Date excluded: most SuperStore sample invoices omit it
        "fields": [
            {"name": "Invoice Number"},
            {"name": "Invoice Date"},
            {"name": "Vendor Name"},
            {"name": "Customer Name"},
            {"name": "Subtotal Amount"},
            {"name": "Tax Amount"},
            {"name": "Total Amount"},
        ],
    },
    {
        "folder": "02_sec_annual_report",
        "description": "Berkshire Hathaway 2023 Annual Report — document-level financial summary",
        "ffr_target": 0.85,  # Complex 152-page document; some metrics use non-standard labels
        "fields": [
            {"name": "Company Name"},
            {"name": "Fiscal Year"},
            {"name": "Total Revenues", "description": "Total revenues from the consolidated statement of earnings"},
            {"name": "Net Earnings", "description": "Net earnings attributable to shareholders from the income statement"},
            {"name": "Total Assets", "description": "Total assets from the consolidated balance sheet"},
            {"name": "Operating Earnings", "description": "Operating earnings as reported by management (often in the shareholder letter)"},
            {"name": "Total Shareholders Equity", "description": "Total shareholders equity or book value from the consolidated balance sheet"},
        ],
    },
    {
        # cms_claims_processing_ch26.pdf is a reference manual (not an EOB form).
        # cms_sbc_sample.pdf is a coverage matrix (not a claim EOB).
        # Only cms_eob_sample.pdf and cms_eob_sample_spanish.pdf are actual EOBs.
        # Note: English EOB uses "XXXXXX" for patient/member (redacted) → Member ID
        # and Provider Name will be absent in the English version — this is correct.
        "folder": "03_insurance_eob",
        "description": "CMS EOB forms — multi-record claim lines (actual EOB PDFs only)",
        "pdf_filter": ["cms_eob_sample.pdf", "cms_eob_sample_spanish.pdf"],
        "ffr_target": 0.85,   # Lower: English EOB has redacted Member ID and Provider
        "fields": [
            {"name": "Patient Name"},
            {"name": "Member ID"},
            {"name": "Service Date"},
            {"name": "Provider Name"},
            {"name": "Billed Amount"},
            {"name": "Allowed Amount"},
            {"name": "Plan Paid"},
            {"name": "Patient Responsibility"},
        ],
    },
    {
        "folder": "04_sec_10k_filing",
        "description": "SEC 10-K filings — document-level financial metrics",
        "ffr_target": 0.80,  # 10-Ks are 100-150 pages; financial statements vary in location
        "fields": [
            {"name": "Company Name"},
            {"name": "Fiscal Year End"},
            {"name": "Total Revenues", "description": "Total revenues or net revenues from the income statement"},
            {"name": "Net Earnings", "description": "Net earnings or net income attributable to shareholders from the income statement"},
            {"name": "Total Assets", "description": "Total assets from the consolidated balance sheet"},
            {"name": "Total Shareholders Equity", "description": "Total shareholders equity or book value from the consolidated balance sheet"},
            {"name": "Operating Income", "description": "Operating income or income from operations before interest and taxes"},
        ],
    },
    {
        "folder": "06_annual_reports",
        "description": "Annual reports & 10-K filings — 20 diverse companies, document-level financial summary",
        "ffr_target": 0.75,  # Diverse formats: glossy ARs, compact 10-Ks, different label conventions
        "fields": [
            {"name": "Company Name"},
            {"name": "Report Year", "description": "Fiscal year or calendar year covered by the report (e.g. 2023)"},
            {"name": "Total Revenue", "description": "Total revenues or net revenues from the income statement"},
            {"name": "Net Income", "description": "Net income or net earnings attributable to shareholders"},
            {"name": "Total Assets", "description": "Total assets from the consolidated balance sheet"},
            {"name": "Total Equity", "description": "Total shareholders equity or stockholders equity from the balance sheet"},
            {"name": "Operating Income", "description": "Operating income or income from operations (before interest and taxes)"},
        ],
    },
    {
        # GSA forms are blank/template forms — operational fields (vendor, contract no,
        # amount) are intentionally empty. Testing form-metadata fields that ARE present.
        "folder": "05_purchase_orders",
        "description": "GSA procurement forms — form metadata (blank templates)",
        "fields": [
            {"name": "Form Title", "description": "Full title of the government form"},
            {"name": "Form Number", "description": "Standard Form number (e.g. SF 1449, SF 26)"},
            {"name": "Revision Date", "description": "Revision date shown on the form (e.g. REV. 12/2022)"},
            {"name": "Form Purpose", "description": "Brief description of what this form is used for"},
        ],
    },
    {
        # Scanned/image-based PDFs — exercises the Mistral OCR → gpt-4.1-mini SCAN pipeline.
        # These are scanned receipts and invoices (not native digital PDFs).
        # Lower FFR target because scanned quality varies and some fields may be partially visible.
        "folder": "07_scanned_docs",
        "description": "Scanned receipts & invoices — tests Mistral OCR → gpt-4.1-mini SCAN pipeline",
        "ffr_target": 0.70,
        "fields": [
            {"name": "Vendor Name", "description": "Name of the store, restaurant, or business on the receipt"},
            {"name": "Total Amount", "description": "Final total amount charged including tax"},
            {"name": "Date", "description": "Date of the transaction or invoice"},
            {"name": "Tax Amount", "description": "Tax amount charged (GST, VAT, sales tax, etc.)"},
        ],
    },
    {
        "folder": "03_insurance_eob",
        "description": "Insurance EOBs (expanded) — synthetic claims with patient responsibility calculations",
        "pdf_filter": ["eob_claim_001.pdf", "eob_claim_002.pdf", "eob_claim_003.pdf", "eob_claim_004.pdf", "eob_claim_005.pdf"],
        "ffr_target": 0.90,
        "fields": [
            {"name": "Member ID", "description": "Insurance member ID (format: EHPxxxxxx)"},
            {"name": "Claim ID", "description": "Unique claim reference number (format: CLMxxxxxxxx)"},
            {"name": "Service Date", "description": "Date service was provided (MM/DD/YYYY format)"},
            {"name": "Provider Name", "description": "Hospital, clinic, or provider name"},
            {"name": "Service Description", "description": "Medical procedure or service description"},
            {"name": "Provider Charge", "description": "Amount provider billed"},
            {"name": "Allowed Amount", "description": "Insurance-allowed amount for the service"},
            {"name": "Your Copay", "description": "Patient copay amount"},
            {"name": "Plan Paid", "description": "Amount insurance plan paid"},
            {"name": "Patient Responsibility", "description": "Total amount patient owes"},
        ],
    },
    {
        "folder": "08_cash_flow_statements",
        "description": "Cash flow statements (new) — corporate financial data extraction",
        "pdf_filter": ["cashflow_statement_001.pdf", "cashflow_statement_002.pdf", "cashflow_statement_003.pdf", "cashflow_statement_004.pdf", "cashflow_statement_005.pdf"],
        "ffr_target": 0.85,
        "fields": [
            {"name": "Company Name", "description": "Name of the company"},
            {"name": "Fiscal Year", "description": "Year ending for the cash flow statement (YYYY format)"},
            {"name": "Net Income", "description": "Net income or earnings from operations"},
            {"name": "Depreciation and Amortization", "description": "Total depreciation and amortization"},
            {"name": "Operating Cash Flow", "description": "Total net cash from operating activities"},
            {"name": "Capital Expenditures", "description": "Capital expenditures or CapEx (typically negative)"},
            {"name": "Investing Cash Flow", "description": "Total net cash from investing activities"},
            {"name": "Debt Repayment", "description": "Amount of debt repaid (typically negative)"},
            {"name": "Dividends Paid", "description": "Dividends paid to shareholders (typically negative)"},
            {"name": "Financing Cash Flow", "description": "Total net cash from financing activities"},
            {"name": "Net Change in Cash", "description": "Overall net change in cash for the period"},
            {"name": "Ending Cash", "description": "Cash balance at end of period"},
        ],
    },
    {
        "folder": "09_contracts_agreements",
        "description": "Contracts & agreements (new) — legal document extraction",
        "pdf_filter": ["contract_001.pdf", "contract_002.pdf", "contract_003.pdf", "contract_004.pdf", "contract_005.pdf"],
        "ffr_target": 0.85,
        "fields": [
            {"name": "Contract Type", "description": "Type of contract (e.g., Service Agreement, NDA, Employment, etc.)"},
            {"name": "Effective Date", "description": "Date when contract becomes effective"},
            {"name": "Provider Name", "description": "Name of service provider or first party"},
            {"name": "Client Name", "description": "Name of client or second party"},
            {"name": "Term Length", "description": "Duration of the contract in years"},
            {"name": "Compensation Amount", "description": "Payment amount (annual, monthly, or hourly)"},
            {"name": "Compensation Type", "description": "Type of compensation (annual fee, monthly retainer, hourly rate)"},
            {"name": "Governing Law", "description": "State or jurisdiction governing the contract"},
            {"name": "Confidentiality Clause", "description": "Whether document contains confidentiality provisions"},
            {"name": "Liability Clause", "description": "Whether document contains liability/indemnification provisions"},
        ],
    },
]


# ── Formatting helpers ────────────────────────────────────────────────────────

GREEN  = "\033[92m"
YELLOW = "\033[93m"
RED    = "\033[91m"
BOLD   = "\033[1m"
RESET  = "\033[0m"


def _pct(v: float) -> str:
    return f"{v:.1%}"


def _colored(v: float, target: float) -> str:
    pct = _pct(v)
    if v >= target:
        return f"{GREEN}{pct}{RESET}"
    if v >= target * 0.85:
        return f"{YELLOW}{pct}{RESET}"
    return f"{RED}{pct}{RESET}"


def _bar(v: float, width: int = 20) -> str:
    filled = int(v * width)
    return "[" + "█" * filled + "░" * (width - filled) + "]"


# ── Single-folder runner ──────────────────────────────────────────────────────

async def run_folder(
    case: Dict,
    verbose: bool = False,
) -> "tuple[ValidationReport, float, int, List[Dict]]":
    """
    Run extraction on all PDFs in one test folder.

    Returns (ValidationReport, elapsed_seconds, total_rows, per_document_reports).
    """
    folder_path = _TEST_DOCS / case["folder"]
    pdf_filter = case.get("pdf_filter")
    if pdf_filter:
        pdf_files = sorted([folder_path / f for f in pdf_filter if (folder_path / f).exists()])
    else:
        pdf_files = sorted(folder_path.glob("*.pdf"))

    if not pdf_files:
        print(f"  {YELLOW}No PDFs found in {folder_path}{RESET}")
        return (
            ValidationReport(0, 0, 1, 1, 0, 0, 0, 0, 0, 0, 0),
            0.0,
            0,
            [],
        )

    fields = case["fields"]
    field_names = [f["name"] for f in fields]
    all_rows: List[Dict] = []
    t0 = time.perf_counter()
    per_document_reports: List[Dict] = []

    for pdf_path in pdf_files:
        if verbose:
            print(f"    Parsing  {pdf_path.name} ...", end="", flush=True)
        parsed = parse_pdf(str(pdf_path), pdf_path.name)
        if verbose:
            hint = parsed.doc_type_hint
            tables = len(parsed.tables)
            print(f" {parsed.page_count}p  hint={hint}  tables={tables}", end="", flush=True)

        usage = LLMUsage()
        pdf_t0 = time.perf_counter()
        rows = await extract_from_document(parsed, fields, usage)
        pdf_elapsed = time.perf_counter() - pdf_t0
        single_record_fill_rate = None
        single_record_missing_fields: List[str] = []
        if len(rows) == 1:
            doc_result = Document(extracted_data=rows)
            single_record_fill_rate = doc_result.single_record_fill_rate(field_names)
            single_record_missing_fields = doc_result.missing_fields(field_names)

        if verbose:
            print(f"  → {len(rows)} row(s)")

        if verbose and len(rows) > 0:
            for r in rows[:3]:
                for fn in field_names:
                    val = r.get(fn, "")
                    if val:
                        print(f"        {fn}: {val}")
                if len(rows) > 3:
                    print(f"        ... ({len(rows) - 3} more rows)")
                if len(rows) == 1 and single_record_missing_fields:
                    print(f"        Missing: {', '.join(single_record_missing_fields)}")
                    print(f"        Single-row fill rate: {_pct(single_record_fill_rate or 0.0)}")
                print()

        all_rows.extend(rows)
        pdf_report = score_extraction(rows, field_names)
        per_document_reports.append({
            "folder": case["folder"],
            "pdf_name": pdf_path.name,
            "rows": len(rows),
            "elapsed": pdf_elapsed,
            "cost_usd": usage.cost_usd,
            "field_fill_rate": pdf_report.field_fill_rate,
            "numeric_parse_rate": pdf_report.numeric_parse_rate,
            "date_parse_rate": pdf_report.date_parse_rate,
            "error_row_rate": pdf_report.error_row_rate,
            "single_record_fill_rate": single_record_fill_rate,
            "missing_fields": single_record_missing_fields,
            "missing_count": len(single_record_missing_fields),
        })

    elapsed = time.perf_counter() - t0
    report = score_extraction(all_rows, field_names)
    return report, elapsed, len(all_rows), per_document_reports


# ── Main test runner ──────────────────────────────────────────────────────────

async def main(folder_filter: str | None = None, verbose: bool = False) -> None:
    cases = TEST_CASES
    if folder_filter:
        cases = [c for c in cases if folder_filter.lower() in c["folder"].lower()]
        if not cases:
            print(f"{RED}No test cases match filter '{folder_filter}'{RESET}")
            sys.exit(1)

    print(f"\n{BOLD}{'═' * 70}{RESET}")
    print(f"{BOLD}  GridPull Enterprise Extraction Test Suite{RESET}")
    print(f"{BOLD}{'═' * 70}{RESET}")
    print(f"  Targets: FFR≥{_pct(FFR_TARGET)}  NPR≥{_pct(NPR_TARGET)}  DPR≥{_pct(DPR_TARGET)}\n")

    all_reports: List[ValidationReport] = []
    overall_elapsed = 0.0
    overall_rows = 0
    failures: List[str] = []
    all_document_reports: List[Dict] = []
    benchmark_data: List[Dict] = []

    for case in cases:
        folder = case["folder"]
        print(f"{BOLD}▶ {folder}{RESET}  —  {case['description']}")
        fields_str = ", ".join(f["name"] for f in case["fields"])
        print(f"  Fields ({len(case['fields'])}): {fields_str}")

        report, elapsed, n_rows, document_reports = await run_folder(case, verbose=verbose)
        all_reports.append(report)
        overall_elapsed += elapsed
        overall_rows += n_rows
        all_document_reports.extend(document_reports)

        folder_ffr_target = case.get("ffr_target", FFR_TARGET)
        ffr_ok = report.field_fill_rate >= folder_ffr_target
        npr_ok = report.numeric_parse_rate >= NPR_TARGET
        dpr_ok = report.date_parse_rate >= DPR_TARGET
        passed = ffr_ok and npr_ok and dpr_ok

        status = f"{GREEN}PASS{RESET}" if passed else f"{RED}FAIL{RESET}"
        print(
            f"  {status}  rows={n_rows}  "
            f"FFR={_colored(report.field_fill_rate, FFR_TARGET)} {_bar(report.field_fill_rate)}  "
            f"NPR={_colored(report.numeric_parse_rate, NPR_TARGET)}  "
            f"DPR={_colored(report.date_parse_rate, DPR_TARGET)}  "
            f"ERR={_pct(report.error_row_rate)}  "
            f"⏱ {elapsed:.1f}s"
        )

        if not passed:
            failures.append(folder)
            if not ffr_ok:
                print(f"    {RED}✗ FFR {_pct(report.field_fill_rate)} < target {_pct(folder_ffr_target)}"
                      f"  ({report.filled_fields}/{report.total_fields} fields filled){RESET}")
            if not npr_ok:
                print(f"    {RED}✗ NPR {_pct(report.numeric_parse_rate)} < target {_pct(NPR_TARGET)}"
                      f"  ({report.numeric_hits}/{report.numeric_total} numeric fields){RESET}")
            if not dpr_ok:
                print(f"    {RED}✗ DPR {_pct(report.date_parse_rate)} < target {_pct(DPR_TARGET)}"
                      f"  ({report.date_hits}/{report.date_total} date fields){RESET}")
        print()

        avg_time_per_doc = elapsed / len(document_reports) if document_reports else 0
        throughput = len(document_reports) / elapsed if elapsed > 0 else 0
        benchmark_data.append({
            "folder": folder,
            "documents": len(document_reports),
            "total_time": elapsed,
            "avg_time_per_doc": avg_time_per_doc,
            "throughput_docs_per_sec": throughput,
            "total_rows": n_rows,
            "avg_rows_per_doc": n_rows / len(document_reports) if document_reports else 0,
            "ffr": report.field_fill_rate,
            "npr": report.numeric_parse_rate,
            "dpr": report.date_parse_rate,
            "err": report.error_row_rate,
        })

    # ── Per-document report (all folders) ─────────────────────────────────────
    if all_document_reports:
        print(f"{BOLD}{'─' * 70}{RESET}")
        print(f"{BOLD}  ALL DOCUMENTS{RESET}  ({len(all_document_reports)} files)")
        total_doc_cost = sum(d["cost_usd"] for d in all_document_reports)
        for d in all_document_reports:
            print(
                f"  {d['folder']}/{d['pdf_name']}  "
                f"rows={d['rows']}  "
                f"FFR={_pct(d['field_fill_rate'])}  "
                f"NPR={_pct(d['numeric_parse_rate'])}  "
                f"DPR={_pct(d['date_parse_rate'])}  "
                f"ERR={_pct(d['error_row_rate'])}  "
                f"⏱ {d['elapsed']:.1f}s  "
                f"${d['cost_usd']:.4f}"
                + (
                    f"  missing={d['missing_count']}"
                    if d.get("single_record_fill_rate") is not None
                    else ""
                )
            )
            if d.get("missing_fields"):
                print(f"    Missing fields: {', '.join(d['missing_fields'])}")
        print(f"  Total LLM cost: ${total_doc_cost:.4f}\n")

        missing_field_counts: Dict[str, int] = {}
        for d in all_document_reports:
            for field in d.get("missing_fields", []):
                missing_field_counts[field] = missing_field_counts.get(field, 0) + 1
        if missing_field_counts:
            print(f"{BOLD}  SINGLE-RECORD MISSING FIELDS{RESET}")
            for field, count in sorted(missing_field_counts.items(), key=lambda item: (-item[1], item[0])):
                print(f"  {field}: {count}")
            print()

    # ── Benchmark report ──────────────────────────────────────────────────────
    if benchmark_data:
        print(f"{BOLD}{'─' * 70}{RESET}")
        print(f"{BOLD}  PERFORMANCE BENCHMARKS{RESET}")
        print(f"  {BOLD}Folder{RESET:<30} {BOLD}Docs{RESET:<6} {BOLD}⏱ Total{RESET:<10} {BOLD}⏱ Avg/Doc{RESET:<10} {BOLD}Throughput{RESET:<12}")
        print(f"  {BOLD}{'-' * 68}{RESET}")
        for b in benchmark_data:
            print(
                f"  {b['folder']:<30} {b['documents']:<6} "
                f"{b['total_time']:.1f}s  {b['avg_time_per_doc']:.2f}s  "
                f"{b['throughput_docs_per_sec']:.2f}/s"
            )
        print()
        print(f"  {BOLD}Quality Metrics{RESET}")
        print(f"  {BOLD}Folder{RESET:<30} {BOLD}FFR{RESET:<8} {BOLD}NPR{RESET:<8} {BOLD}DPR{RESET:<8} {BOLD}ERR{RESET:<8}")
        print(f"  {BOLD}{'-' * 62}{RESET}")
        for b in benchmark_data:
            print(
                f"  {b['folder']:<30} {_pct(b['ffr']):<8} {_pct(b['npr']):<8} "
                f"{_pct(b['dpr']):<8} {_pct(b['err']):<8}"
            )
        print()

    # ── Aggregate totals ───────────────────────────────────────────────────────
    if all_reports:
        total_filled  = sum(r.filled_fields  for r in all_reports)
        total_fields  = sum(r.total_fields   for r in all_reports)
        num_hits      = sum(r.numeric_hits   for r in all_reports)
        num_total     = sum(r.numeric_total  for r in all_reports)
        date_hits     = sum(r.date_hits      for r in all_reports)
        date_total    = sum(r.date_total     for r in all_reports)
        err_rows      = sum(r.row_count * r.error_row_rate for r in all_reports)

        agg_ffr = total_filled / total_fields if total_fields else 0
        agg_npr = num_hits  / num_total        if num_total   else 1
        agg_dpr = date_hits / date_total       if date_total  else 1
        agg_err = err_rows  / overall_rows     if overall_rows else 0

        agg_ok = (
            agg_ffr >= FFR_TARGET
            and agg_npr >= NPR_TARGET
            and agg_dpr >= DPR_TARGET
            and not failures
        )

        print(f"{BOLD}{'─' * 70}{RESET}")
        print(f"{BOLD}  OVERALL{RESET}  ({len(cases)} folders, {overall_rows} rows, {overall_elapsed:.1f}s)")
        
        avg_overall_throughput = sum(b['throughput_docs_per_sec'] for b in benchmark_data) / len(benchmark_data) if benchmark_data else 0
        total_docs_in_benchmark = sum(b['documents'] for b in benchmark_data)
        
        print(
            f"  FFR={_colored(agg_ffr, FFR_TARGET)} {_bar(agg_ffr)}  "
            f"NPR={_colored(agg_npr, NPR_TARGET)}  "
            f"DPR={_colored(agg_dpr, DPR_TARGET)}  "
            f"ERR={_pct(agg_err)}"
        )
        print(f"  Performance: {total_docs_in_benchmark} documents, {overall_elapsed:.1f}s total, {overall_elapsed/total_docs_in_benchmark:.2f}s/doc avg")

        overall_status = f"{GREEN}ALL PASS ✓{RESET}" if agg_ok else f"{RED}SOME FAIL ✗{RESET}"
        print(f"\n  {overall_status}")

        if failures:
            print(f"  {RED}Failed folders: {', '.join(failures)}{RESET}")

        print(f"{BOLD}{'═' * 70}{RESET}\n")
        sys.exit(0 if agg_ok else 1)


# ── Entry point ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="GridPull extraction test suite")
    parser.add_argument("--folder", "-f", help="Run only folders matching this string")
    parser.add_argument("--verbose", "-v", action="store_true", help="Print per-file details")
    args = parser.parse_args()

    asyncio.run(main(folder_filter=args.folder, verbose=args.verbose))
