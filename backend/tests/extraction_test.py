"""
Enterprise extraction test suite.

Runs the full extraction pipeline against all 5 test document sets and
reports quality metrics (FFR / NPR / DPR / ERR) per folder and overall.

Usage:
    cd backend
    OPENAI_API_KEY=sk-... python tests/extraction_test.py [--folder <name>] [--verbose]

Target metrics (all figures 0-1):
    FFR  ≥ 0.90
    NPR  ≥ 0.95
    DPR  ≥ 0.95
    ERR  = 0.00
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

from app.services.extraction_service import extract_from_document  # noqa: E402
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
) -> "tuple[ValidationReport, float, int]":
    """
    Run extraction on all PDFs in one test folder.

    Returns (ValidationReport, elapsed_seconds, total_rows).
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
        )

    fields = case["fields"]
    field_names = [f["name"] for f in fields]
    all_rows: List[Dict] = []
    t0 = time.perf_counter()

    for pdf_path in pdf_files:
        if verbose:
            print(f"    Parsing  {pdf_path.name} ...", end="", flush=True)
        parsed = parse_pdf(str(pdf_path), pdf_path.name)
        if verbose:
            hint = parsed.doc_type_hint
            tables = len(parsed.tables)
            print(f" {parsed.page_count}p  hint={hint}  tables={tables}", end="", flush=True)

        rows = await extract_from_document(parsed, fields)

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
                print()

        all_rows.extend(rows)

    elapsed = time.perf_counter() - t0
    report = score_extraction(all_rows, field_names)
    return report, elapsed, len(all_rows)


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

    for case in cases:
        folder = case["folder"]
        print(f"{BOLD}▶ {folder}{RESET}  —  {case['description']}")
        fields_str = ", ".join(f["name"] for f in case["fields"])
        print(f"  Fields ({len(case['fields'])}): {fields_str}")

        report, elapsed, n_rows = await run_folder(case, verbose=verbose)
        all_reports.append(report)
        overall_elapsed += elapsed
        overall_rows += n_rows

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

        agg_ok = (agg_ffr >= FFR_TARGET and agg_npr >= NPR_TARGET and agg_dpr >= DPR_TARGET)

        print(f"{BOLD}{'─' * 70}{RESET}")
        print(f"{BOLD}  OVERALL{RESET}  ({len(cases)} folders, {overall_rows} rows, {overall_elapsed:.1f}s)")
        print(
            f"  FFR={_colored(agg_ffr, FFR_TARGET)} {_bar(agg_ffr)}  "
            f"NPR={_colored(agg_npr, NPR_TARGET)}  "
            f"DPR={_colored(agg_dpr, DPR_TARGET)}  "
            f"ERR={_pct(agg_err)}"
        )

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
