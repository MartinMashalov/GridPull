"""Quick retest of the 8 docs that were missing Total Equity."""
from __future__ import annotations
import asyncio, sys, time
from pathlib import Path

_BACKEND = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_BACKEND))
try:
    from dotenv import load_dotenv; load_dotenv(_BACKEND / ".env")
except ImportError: pass

from app.services.extraction_service import extract_from_document, LLMUsage
from app.services.pdf_service import parse_pdf

_TEST_DOCS = Path(__file__).resolve().parent.parent.parent / "test_documents"

FIELDS = [
    {"name": "Company Name"},
    {"name": "Total Revenue",    "description": "Total revenues or net revenues from the income statement"},
    {"name": "Total Equity",     "description": "Total shareholders equity or stockholders equity from the balance sheet"},
]
FIELD_NAMES = [f["name"] for f in FIELDS]

TARGETS = [
    "american_eagle_2023_10k.pdf",
    "costco_2023_annual_report.pdf",
    "goldman_sachs_2023_annual_report.pdf",
    "johnson_johnson_2023_10k.pdf",
    "jpmorgan_2023_10k.pdf",
    "mastercard_2023_annual_report.pdf",
    "starbucks_2023_annual_report.pdf",
    "unitedhealth_2023_10k.pdf",
]

GREEN = "\033[92m"; RED = "\033[91m"; BOLD = "\033[1m"; RESET = "\033[0m"

async def main():
    folder = _TEST_DOCS / "06_annual_reports"
    fixed = 0
    print(f"\n{BOLD}Equity retest — 8 previously failing docs{RESET}\n")
    for name in TARGETS:
        pdf = folder / name
        usage = LLMUsage()
        t0 = time.perf_counter()
        parsed = parse_pdf(str(pdf), name)
        rows = await extract_from_document(parsed, FIELDS, usage)
        elapsed = time.perf_counter() - t0
        row = rows[0] if rows else {}
        equity = row.get("Total Equity", "").strip()
        ok = bool(equity)
        mark = f"{GREEN}✓{RESET}" if ok else f"{RED}✗{RESET}"
        if ok: fixed += 1
        print(f"  {mark}  {name}")
        print(f"       Equity: {equity or '—'}   ({elapsed:.1f}s  ${usage.cost_usd:.4f})")
    print(f"\n  Fixed: {fixed}/8\n")

if __name__ == "__main__":
    asyncio.run(main())
