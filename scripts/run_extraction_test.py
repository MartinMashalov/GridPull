#!/usr/bin/env python3
"""
Extraction test runner — submits files to the live GridPull API and evaluates results.

Usage:
    python scripts/run_extraction_test.py --batch invoices_multi
    python scripts/run_extraction_test.py --batch invoices_single
    python scripts/run_extraction_test.py --batch sov
    python scripts/run_extraction_test.py --batch all
"""
import argparse
import json
import time
import sys
from pathlib import Path

from jose import jwt
import requests

# ── Config ────────────────────────────────────────────────────────────────────
API_BASE       = "https://gridpull.com/api"
JWT_SECRET     = "gridpull-super-secret-jwt-key-change-in-production-2026"
JWT_ALGORITHM  = "HS256"
USER_ID        = "4d9ed3f6-4181-4ea1-85a1-82f733d4ab92"

TEST_DOCS      = Path(__file__).parent.parent / "test_documents"

BATCHES = {
    "invoices_multi": {
        "folder": TEST_DOCS / "11_multipage_invoices",
        "glob": "*.pdf",
        "pipeline": "general",
        "fields": [
            {"name": "Invoice Number"},
            {"name": "Invoice Date"},
            {"name": "Due Date"},
            {"name": "Vendor Name"},
            {"name": "Bill To Company"},
            {"name": "Bill To Address"},
            {"name": "Subtotal"},
            {"name": "Tax"},
            {"name": "Total Amount"},
            {"name": "Currency"},
            {"name": "Payment Terms"},
        ],
        "instructions": "Each file is a single multi-page invoice. Extract one row per file.",
    },
    "invoices_single": {
        "folder": TEST_DOCS / "01_invoices",
        "glob": "*.pdf",
        "pipeline": "general",
        "fields": [
            {"name": "Invoice Number"},
            {"name": "Invoice Date"},
            {"name": "Due Date"},
            {"name": "Vendor Name"},
            {"name": "Bill To Company"},
            {"name": "Subtotal"},
            {"name": "Tax"},
            {"name": "Total Amount"},
        ],
        "instructions": "",
    },
    "sov_apartment": {
        "folder": TEST_DOCS / "12_sov_email_examples",
        "glob": "complex_property_schedule_8_locations.pdf",
        "pipeline": "sov",
        "use_cerebras": True,
        "fields": [
            {"name": "Loc #"},
            {"name": "Bldg #"},
            {"name": "Location Name"},
            {"name": "Occupancy/Exposure"},
            {"name": "Street Address"},
            {"name": "City"},
            {"name": "State"},
            {"name": "Zip"},
            {"name": "County"},
            {"name": "Construction Type"},
            {"name": "ISO Construction Code"},
            {"name": "Building Values"},
            {"name": "Contents/BPP Values"},
            {"name": "Business Income Values"},
            {"name": "Machinery & Equipment Values"},
            {"name": "Other Property Values"},
            {"name": "Total Insurable Value (TIV)"},
            {"name": "Square Ft."},
            {"name": "Cost Per Square Ft."},
            {"name": "Year Built"},
            {"name": "Roof Update"},
            {"name": "Wiring Update"},
            {"name": "HVAC Update"},
            {"name": "Plumbing Update"},
            {"name": "% Occupied"},
            {"name": "Sprinklered"},
            {"name": "% Sprinklered"},
            {"name": "ISO Protection Class"},
            {"name": "Fire Alarm"},
            {"name": "Burglar Alarm"},
            {"name": "Smoke Detectors"},
            {"name": "# of Stories"},
            {"name": "# of Units"},
            {"name": "Type of Wiring"},
            {"name": "% Subsidized"},
            {"name": "% Student Housing"},
            {"name": "% Elderly Housing"},
            {"name": "Roof Type/Frame"},
            {"name": "Roof Shape"},
            {"name": "Flood Zone"},
            {"name": "EQ Zone"},
            {"name": "Distance to Salt Water/Coast"},
            {"name": "Property Owned or Managed"},
            {"name": "Bldg Maintenance"},
            {"name": "Basement"},
            {"name": "Predominant Exterior Wall / Cladding"},
        ],
        "instructions": "Extract all rows from the schedule tables.",
    },
    "sov_retail": {
        "folder": TEST_DOCS / "12_sov_email_examples",
        "glob": "retail_property_schedule_12_locations.pdf",
        "pipeline": "sov",
        "use_cerebras": True,
        "fields": [
            {"name": "Loc #"},
            {"name": "Bldg #"},
            {"name": "Location Name"},
            {"name": "Occupancy/Exposure"},
            {"name": "Street Address"},
            {"name": "City"},
            {"name": "State"},
            {"name": "Zip"},
            {"name": "County"},
            {"name": "Construction Type"},
            {"name": "ISO Construction Code"},
            {"name": "Building Values"},
            {"name": "Contents/BPP Values"},
            {"name": "Business Income Values"},
            {"name": "Machinery & Equipment Values"},
            {"name": "Total Insurable Value (TIV)"},
            {"name": "Square Ft."},
            {"name": "Cost Per Square Ft."},
            {"name": "Year Built"},
            {"name": "Roof Update"},
            {"name": "Wiring Update"},
            {"name": "% Occupied"},
            {"name": "Sprinklered"},
            {"name": "ISO Protection Class"},
            {"name": "# of Stories"},
            {"name": "Roof Type/Frame"},
            {"name": "Flood Zone"},
            {"name": "Property Owned or Managed"},
        ],
        "instructions": "Extract all rows from the schedule tables.",
    },
    "sov_fleet": {
        "folder": TEST_DOCS / "12_sov_email_examples",
        "glob": "fleet_schedule_18_vehicles.pdf",
        "pipeline": "sov",
        "use_cerebras": True,
        "fields": [
            {"name": "Unit #"},
            {"name": "Year"},
            {"name": "Make"},
            {"name": "Model"},
            {"name": "VIN"},
            {"name": "Garaging Address"},
            {"name": "City"},
            {"name": "State"},
            {"name": "Zip"},
            {"name": "GVW"},
            {"name": "Body Type"},
            {"name": "Vehicle Use"},
            {"name": "Scheduled Value"},
            {"name": "Cost New"},
            {"name": "Comp Deductible"},
            {"name": "Collision Deductible"},
        ],
        "instructions": "Extract one row per vehicle.",
    },
    "sov_acme": {
        "folder": TEST_DOCS / "12_sov_email_examples",
        "glob": "sov_acme_manufacturing_15_locations.pdf",
        "pipeline": "sov",
        "use_cerebras": True,
        "fields": [
            {"name": "Loc #"},
            {"name": "Street Address"},
            {"name": "City"},
            {"name": "State"},
            {"name": "Zip"},
            {"name": "Occupancy"},
            {"name": "Construction Type"},
            {"name": "Year Built"},
            {"name": "Square Ft."},
            {"name": "Sprinklered"},
            {"name": "Building Values"},
            {"name": "Contents Values"},
            {"name": "Total Insurable Value (TIV)"},
        ],
        "instructions": "Extract all rows from the schedule tables.",
    },
    "payroll": {
        "folder": TEST_DOCS / "13_payroll_examples",
        "glob": "payroll_schedule_25_employees.pdf",
        "pipeline": "sov",
        "use_cerebras": True,
        "fields": [
            {"name": "Employee ID"},
            {"name": "Last Name"},
            {"name": "First Name"},
            {"name": "Department"},
            {"name": "Job Title"},
            {"name": "Hire Date"},
            {"name": "Employment Status"},
            {"name": "FLSA Classification"},
            {"name": "Pay Type"},
            {"name": "Base Pay"},
            {"name": "Bonus %"},
            {"name": "Benefits Package"},
            {"name": "401k Contribution %"},
            {"name": "Work State"},
            {"name": "Manager ID"},
        ],
        "instructions": "Extract one row per employee.",
    },
}

POLL_INTERVAL = 3   # seconds
POLL_TIMEOUT  = 300 # seconds

# ── Auth ──────────────────────────────────────────────────────────────────────
def make_token() -> str:
    import time as _time
    return jwt.encode({"sub": USER_ID, "iat": int(_time.time())}, JWT_SECRET, algorithm=JWT_ALGORITHM)

# ── Submission ────────────────────────────────────────────────────────────────
def submit_batch(batch_name: str, cfg: dict, token: str) -> str:
    folder   = cfg["folder"]
    pdf_files = sorted(folder.glob(cfg["glob"]))
    if not pdf_files:
        print(f"  [!] No files found in {folder}")
        return None

    print(f"\n{'='*60}")
    print(f"BATCH: {batch_name}  ({len(pdf_files)} files, pipeline={cfg['pipeline']})")
    print(f"{'='*60}")

    file_handles = []
    files_payload = []
    try:
        for p in pdf_files:
            fh = open(p, "rb")
            file_handles.append(fh)
            files_payload.append(("files", (p.name, fh, "application/pdf")))

        data = {
            "fields":        json.dumps(cfg["fields"]),
            "pipeline":      cfg["pipeline"],
            "instructions":  cfg.get("instructions", ""),
            "format":        "xlsx",
            "use_cerebras":  "true" if cfg.get("use_cerebras") else "false",
        }
        resp = requests.post(
            f"{API_BASE}/documents/extract",
            headers={"Authorization": f"Bearer {token}"},
            files=files_payload,
            data=data,
            timeout=60,
        )
        if resp.status_code != 200:
            print(f"  [!] Submit failed: {resp.status_code} — {resp.text[:300]}")
            return None

        job_id = resp.json().get("job_id")
        print(f"  Job submitted: {job_id}")
        return job_id
    finally:
        for fh in file_handles:
            fh.close()

# ── Polling ───────────────────────────────────────────────────────────────────
def poll_job(job_id: str, token: str) -> dict | None:
    deadline = time.time() + POLL_TIMEOUT
    last_msg = ""
    while time.time() < deadline:
        resp = requests.get(
            f"{API_BASE}/documents/job/{job_id}",
            headers={"Authorization": f"Bearer {token}"},
            timeout=15,
        )
        if resp.status_code != 200:
            print(f"  [!] Poll error: {resp.status_code}")
            time.sleep(POLL_INTERVAL)
            continue

        job = resp.json()
        status   = job.get("status", "")
        progress = job.get("progress", 0)
        msg      = job.get("message", "")
        if msg != last_msg:
            print(f"  [{progress:3d}%] {status} — {msg}")
            last_msg = msg

        if status == "complete":
            return job
        if status == "error":
            print(f"  [!] Job failed: {job.get('error')}")
            return None

        time.sleep(POLL_INTERVAL)

    print(f"  [!] Timed out after {POLL_TIMEOUT}s")
    return None

# ── Results ───────────────────────────────────────────────────────────────────
def fetch_results(job_id: str, token: str) -> list[dict]:
    resp = requests.get(
        f"{API_BASE}/documents/results/{job_id}",
        headers={"Authorization": f"Bearer {token}"},
        timeout=15,
    )
    if resp.status_code != 200:
        print(f"  [!] Results fetch failed: {resp.status_code}")
        return []
    return resp.json().get("results", [])

# ── Evaluation ────────────────────────────────────────────────────────────────
EMPTY_VALUES = {"", "none", "null", "n/a", "na", "-"}

def evaluate(batch_name: str, cfg: dict, results: list[dict], elapsed_s: float, cost_usd: float = 0.0):
    field_names = [f["name"] for f in cfg["fields"]]
    real_rows   = [r for r in results if not r.get("_error")]
    error_rows  = [r for r in results if r.get("_error")]

    total_cells  = len(real_rows) * len(field_names)
    filled_cells = sum(
        1 for row in real_rows for fn in field_names
        if row.get(fn) is not None and str(row.get(fn, "")).strip().lower() not in EMPTY_VALUES
    )
    fill_rate = filled_cells / total_cells if total_cells else 0
    cost_per_row = cost_usd / max(len(real_rows), 1)

    print(f"\n── Results: {batch_name} ──")
    print(f"  Rows extracted : {len(real_rows)}")
    print(f"  Error rows     : {len(error_rows)}")
    print(f"  Fill rate      : {fill_rate:.1%}  ({filled_cells}/{total_cells} cells)")
    print(f"  Elapsed        : {elapsed_s:.0f}s")
    if cost_usd:
        print(f"  Cost           : ${cost_usd:.4f}  (${cost_per_row:.4f}/row)")

    if error_rows:
        print(f"\n  Error rows:")
        for r in error_rows:
            print(f"    {r.get('_source_file','?')} — {r.get('_error','?')[:100]}")

    # Show per-field fill rates for fields with < 100% fill
    field_fills = {}
    for fn in field_names:
        filled = sum(
            1 for row in real_rows
            if row.get(fn) is not None and str(row.get(fn, "")).strip().lower() not in EMPTY_VALUES
        )
        field_fills[fn] = filled
    missing_fields = [(fn, field_fills[fn]) for fn in field_names if field_fills[fn] < len(real_rows)]
    if missing_fields:
        print(f"\n  Fields with gaps (filled/total):")
        for fn, cnt in sorted(missing_fields, key=lambda x: x[1]):
            print(f"    {fn:40s} {cnt}/{len(real_rows)}")

    # Show a sample of extracted rows
    print(f"\n  Sample rows (first 3):")
    for row in real_rows[:3]:
        src = row.get("_source_file", "?")
        fields_preview = {fn: row.get(fn) for fn in field_names if row.get(fn) is not None}
        print(f"    [{src}]")
        for k, v in list(fields_preview.items())[:8]:
            print(f"      {k}: {v}")

    return {
        "batch":          batch_name,
        "rows":           len(real_rows),
        "error_rows":     len(error_rows),
        "fill_rate":      round(fill_rate, 4),
        "filled_cells":   filled_cells,
        "total_cells":    total_cells,
        "elapsed_s":      round(elapsed_s, 1),
        "cost_usd":       round(cost_usd, 4),
        "cost_per_row":   round(cost_per_row, 4),
    }

# ── Main ──────────────────────────────────────────────────────────────────────
def run_batch(batch_name: str, token: str) -> dict | None:
    cfg    = BATCHES[batch_name]
    t0     = time.time()
    job_id = submit_batch(batch_name, cfg, token)
    if not job_id:
        return None

    job = poll_job(job_id, token)
    if not job:
        return None

    results  = fetch_results(job_id, token)
    elapsed  = time.time() - t0
    cost_usd = float(job.get("cost") or 0.0)
    return evaluate(batch_name, cfg, results, elapsed, cost_usd)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--batch", default="all", choices=list(BATCHES) + ["all"])
    args = parser.parse_args()

    token   = make_token()
    batches = list(BATCHES) if args.batch == "all" else [args.batch]

    summaries = []
    for name in batches:
        summary = run_batch(name, token)
        if summary:
            summaries.append(summary)

    if len(summaries) > 1:
        print(f"\n{'='*72}")
        print("SUMMARY")
        print(f"{'='*72}")
        print(f"  {'Batch':<22} {'Rows':>4}  {'Fill':>5}  {'Errors':>6}  {'Cost':>7}  {'$/row':>6}  {'Time':>5}")
        print(f"  {'-'*22} {'-'*4}  {'-'*5}  {'-'*6}  {'-'*7}  {'-'*6}  {'-'*5}")
        for s in summaries:
            cost_str = f"${s['cost_usd']:.4f}" if s['cost_usd'] else "n/a"
            cpr_str  = f"${s['cost_per_row']:.4f}" if s['cost_per_row'] else "n/a"
            print(f"  {s['batch']:<22} {s['rows']:>4}  {s['fill_rate']:>4.0%}  {s['error_rows']:>6}  {cost_str:>7}  {cpr_str:>6}  {s['elapsed_s']:>4}s")
        total_cost = sum(s['cost_usd'] for s in summaries)
        total_rows = sum(s['rows'] for s in summaries)
        print(f"\n  Total cost: ${total_cost:.4f}  |  Total rows: {total_rows}  |  Avg $/row: ${total_cost/max(total_rows,1):.4f}")


if __name__ == "__main__":
    main()
