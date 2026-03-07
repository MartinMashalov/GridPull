"""
Per-document benchmark for the annual reports test folder.
Prints time, cost, and extracted values for each PDF.

Usage:
    cd backend
    venv/bin/python tests/bench_annual_reports.py
"""
from __future__ import annotations

import asyncio
import sys
import time
from pathlib import Path

_BACKEND = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_BACKEND))

try:
    from dotenv import load_dotenv
    load_dotenv(_BACKEND / ".env")
except ImportError:
    pass

from app.services.extraction_service import extract_from_document, LLMUsage
from app.services.pdf_service import parse_pdf
from app.services.validator_service import score_extraction

_TEST_DOCS = Path(__file__).resolve().parent.parent.parent / "test_documents"

FIELDS = [
    {"name": "Company Name"},
    {"name": "Report Year",      "description": "Fiscal year or calendar year covered by the report (e.g. 2023)"},
    {"name": "Total Revenue",    "description": "Total revenues or net revenues from the income statement"},
    {"name": "Net Income",       "description": "Net income or net earnings attributable to shareholders"},
    {"name": "Total Assets",     "description": "Total assets from the consolidated balance sheet"},
    {"name": "Total Equity",     "description": "Total shareholders equity or stockholders equity from the balance sheet"},
    {"name": "Operating Income", "description": "Operating income or income from operations (before interest and taxes)"},
]
FIELD_NAMES = [f["name"] for f in FIELDS]

GREEN  = "\033[92m"
YELLOW = "\033[93m"
RED    = "\033[91m"
BOLD   = "\033[1m"
RESET  = "\033[0m"


async def main() -> None:
    folder = _TEST_DOCS / "06_annual_reports"
    pdfs   = sorted(folder.glob("*.pdf"))
    if not pdfs:
        print(f"{RED}No PDFs found in {folder}{RESET}")
        sys.exit(1)

    print(f"\n{BOLD}{'═' * 80}{RESET}")
    print(f"{BOLD}  Annual Reports Benchmark  ({len(pdfs)} documents){RESET}")
    print(f"{BOLD}{'═' * 80}{RESET}\n")

    results = []

    for pdf_path in pdfs:
        usage = LLMUsage()
        t0    = time.perf_counter()

        parsed = parse_pdf(str(pdf_path), pdf_path.name)
        rows   = await extract_from_document(parsed, FIELDS, usage)

        elapsed = time.perf_counter() - t0
        cost    = usage.cost_usd

        row = rows[0] if rows else {}
        filled = sum(1 for fn in FIELD_NAMES if row.get(fn, "").strip())
        ffr    = filled / len(FIELD_NAMES)

        color = GREEN if ffr >= 0.75 else (YELLOW if ffr >= 0.5 else RED)
        print(f"{BOLD}{pdf_path.name}{RESET}")
        print(f"  Pages={parsed.page_count}  Time={elapsed:.1f}s  Cost=${cost:.4f}  "
              f"FFR={color}{ffr:.0%}{RESET} ({filled}/{len(FIELD_NAMES)} fields)")
        for fn in FIELD_NAMES:
            val = row.get(fn, "")
            mark = "✓" if val.strip() else f"{RED}✗{RESET}"
            print(f"    {mark}  {fn}: {val or '—'}")
        print()
        results.append({"name": pdf_path.name, "elapsed": elapsed, "cost": cost, "ffr": ffr, "row": row})

    # ── Summary ────────────────────────────────────────────────────────────────
    total_time = sum(r["elapsed"] for r in results)
    total_cost = sum(r["cost"]    for r in results)
    avg_time   = total_time / len(results)
    avg_cost   = total_cost / len(results)
    avg_ffr    = sum(r["ffr"] for r in results) / len(results)

    print(f"{BOLD}{'─' * 80}{RESET}")
    print(f"{BOLD}  SUMMARY  ({len(results)} docs){RESET}")
    print(f"  Avg time per doc : {avg_time:.1f}s  (total: {total_time:.0f}s)")
    print(f"  Avg cost per doc : ${avg_cost:.4f}  (total: ${total_cost:.4f})")
    color = GREEN if avg_ffr >= 0.75 else (YELLOW if avg_ffr >= 0.5 else RED)
    print(f"  Avg FFR          : {color}{avg_ffr:.1%}{RESET}")
    print(f"{BOLD}{'═' * 80}{RESET}\n")


if __name__ == "__main__":
    asyncio.run(main())
