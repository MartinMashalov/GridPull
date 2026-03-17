"""
Download 20+ annual report PDFs for the extraction test suite.

Direct PDF URLs sourced from company IR sites and q4cdn.com.

Usage:
    cd backend
    python tests/download_annual_reports.py
"""

from __future__ import annotations

import gzip
import os
import time
import urllib.request
from pathlib import Path

OUTPUT_DIR = Path(__file__).resolve().parent.parent.parent / "test_documents" / "06_annual_reports"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

# (output_filename, direct_pdf_url)
TARGETS = [
    ("apple_2023_10k",
     "https://s2.q4cdn.com/470004039/files/doc_earnings/2023/q4/filing/_10-K-Q4-2023-As-Filed.pdf"),
    ("nvidia_2023_10k",
     "https://s201.q4cdn.com/141608511/files/doc_financials/2023/q4/4e9abe7b-fdc7-4cd2-8487-dc3a99f30e98.pdf"),
    ("amazon_2023_annual_report",
     "https://s2.q4cdn.com/299287126/files/doc_financials/2024/ar/Amazon-com-Inc-2023-Annual-Report.pdf"),
    ("walmart_2023_10k",
     "https://stock.walmart.com/sec-filings/all-sec-filings/content/0000104169-24-000056/0000104169-24-000056.pdf"),
    ("tesla_2023_10k",
     "https://ir.tesla.com/_flysystem/s3/sec/000162828024002390/tsla-20231231-gen.pdf"),
    ("pfizer_2023_10k",
     "https://s206.q4cdn.com/795948973/files/doc_financials/2023/q4/Form-10-K.pdf"),
    ("visa_2023_annual_report",
     "https://s1.q4cdn.com/050606653/files/doc_downloads/2023/12/849d0b35-b550-4d4a-95e3-611146a657f2.pdf"),
    ("delta_2023_10k",
     "https://s2.q4cdn.com/181345880/files/doc_downloads/annual/2024/dal-12-31-2023-10k-2-12-24-filed.pdf"),
    ("starbucks_2023_annual_report",
     "https://s203.q4cdn.com/326826266/files/doc_financials/2024/ar/fy23-annual-report.pdf"),
    ("nike_2023_10k",
     "https://s1.q4cdn.com/806093406/files/doc_downloads/2023/414759-1-_5_Nike-NPS-Combo_Form-10-K_WR.pdf"),
    ("johnson_johnson_2023_10k",
     "https://s203.q4cdn.com/636242992/files/doc_financials/2023/q4/form-10-k-2023-final.pdf"),
    ("unitedhealth_2023_10k",
     "https://www.unitedhealthgroup.com/content/dam/UHG/PDF/investors/2023/UNH-Q4-2023-Form-10-K.pdf"),
    ("costco_2023_annual_report",
     "https://s201.q4cdn.com/287523651/files/doc_financials/2023/ar/cost-annual-report-final-pdf-from-dfin.pdf"),
    ("goldman_sachs_2023_annual_report",
     "https://www.annualreports.com/HostedData/AnnualReportArchive/g/NYSE_GS_2023.pdf"),
    ("microsoft_2023_10k",
     "https://microsoft.gcs-web.com/static-files/e2931fdb-9823-4130-b2a8-f6b8db0b15a9"),
    ("jpmorgan_2023_10k",
     "https://www.jpmorganchase.com/content/dam/jpmc/jpmorgan-chase-and-co/investor-relations/documents/quarterly-earnings/2023/4th-quarter/corp-10k-2023.pdf"),
    ("procter_gamble_2023_10k",
     "https://assets.ctfassets.net/oggad6svuzkv/3dWG1bXokHsV1AoriLeoGl/11d56c8d0af0ae669fc9d92def0ec082/2023_form_10k.pdf"),
    ("chevron_2023_annual_report",
     "https://www.chevron.com/-/media/chevron/annual-report/2023/documents/2023-Annual-Report.pdf"),
    ("mastercard_2023_annual_report",
     "https://s25.q4cdn.com/479285134/files/doc_financials/2023/AR/2023-annual-report.pdf"),
    ("american_eagle_2023_10k",
     "https://s26.q4cdn.com/546305894/files/doc_financials/2024/ar/aeo-10k-2024.pdf"),
    ("netscout_2024_10k",
     "https://s206.q4cdn.com/726993193/files/doc_financials/2024/ar/NetScout-10-K-2024-123048_002_BMK.pdf"),
    ("exxonmobil_2023_10k",
     "https://investor.exxonmobil.com/sec-filings/annual-reports/content/0000034088-24-000018/0000034088-24-000018.pdf"),
]

MAX_FILE_MB = 15


def download_pdf(url: str, out_path: Path, name: str) -> bool:
    """Download a PDF to out_path. Returns True on success."""
    try:
        from urllib.parse import urlparse
        host = urlparse(url).netloc
        headers = {
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept": "application/pdf,*/*",
            "Accept-Encoding": "gzip, deflate",
            "Host": host,
        }
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=90) as r:
            content_length = r.headers.get("Content-Length")
            if content_length:
                size_mb = int(content_length) / (1024 * 1024)
                if size_mb > MAX_FILE_MB:
                    print(f"    [SKIP] File too large: {size_mb:.1f} MB (limit {MAX_FILE_MB} MB)")
                    return False
            raw = r.read()
            encoding = r.headers.get("Content-Encoding", "")

        if encoding == "gzip":
            raw = gzip.decompress(raw)

        size_mb = len(raw) / (1024 * 1024)
        if size_mb > MAX_FILE_MB:
            print(f"    [SKIP] Downloaded file too large: {size_mb:.1f} MB")
            return False

        if not raw.startswith(b"%PDF"):
            print(f"    [SKIP] Not a PDF (got: {raw[:60]!r})")
            return False

        out_path.write_bytes(raw)
        print(f"    [OK] Saved {out_path.name} ({size_mb:.1f} MB)")
        return True
    except Exception as e:
        print(f"    [ERROR] {e}")
        return False


def main() -> None:
    print(f"\nDownloading {len(TARGETS)} annual report PDFs to {OUTPUT_DIR}\n")
    succeeded, skipped = [], []

    for name, url in TARGETS:
        out_path = OUTPUT_DIR / f"{name}.pdf"
        if out_path.exists() and out_path.stat().st_size > 50_000:
            print(f"  {name}: already exists ({out_path.stat().st_size // 1024} KB), skipping")
            succeeded.append(name)
            continue

        print(f"  {name}:")
        ok = download_pdf(url, out_path, name)
        if ok:
            succeeded.append(name)
        else:
            skipped.append(name)
        time.sleep(0.4)

    print(f"\n{'─'*60}")
    print(f"Downloaded: {len(succeeded)}/{len(TARGETS)}")
    if skipped:
        print(f"Skipped/failed: {skipped}")
    print(f"Output dir: {OUTPUT_DIR}")
    files = sorted(OUTPUT_DIR.glob("*.pdf"))
    if files:
        total_mb = sum(f.stat().st_size for f in files) / (1024 * 1024)
        print(f"Total: {len(files)} PDFs, {total_mb:.1f} MB")


if __name__ == "__main__":
    main()
