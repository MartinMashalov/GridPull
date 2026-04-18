"""Test the LIVE production extraction API end-to-end."""
import requests
import time
import json
import sys
import os

sys.stdout.reconfigure(line_buffering=True)

BASE = "https://gridpull.com/api"
TOKEN = "e0606a338a039fc255b77deaec683d723f1b0841549abe94f9293a68e204544f"
TEST_DOCS = "/Users/martinmashalov/Downloads/GridPull/test_documents"

def test_extraction(label, file_path, fields, pipeline="sov", instructions=""):
    print(f"\n{'='*60}")
    print(f"LIVE TEST: {label}")
    print(f"File: {os.path.basename(file_path)}")
    print(f"Pipeline: {pipeline} | Fields: {len(fields)}")

    with open(file_path, "rb") as f:
        files = [("files", (os.path.basename(file_path), f))]
        data = {
            "fields": json.dumps(fields),
            "instructions": instructions,
            "format": "xlsx",
            "pipeline": pipeline,
            "service_token": TOKEN,
        }
        t0 = time.time()
        resp = requests.post(f"{BASE}/documents/extract-service", files=files, data=data, timeout=30)

    if resp.status_code != 200:
        print(f"  FAIL: HTTP {resp.status_code} — {resp.text[:200]}")
        return None

    job_id = resp.json().get("job_id")
    print(f"  Job created: {job_id}")

    # Poll for completion
    for i in range(120):
        time.sleep(3)
        poll = requests.get(f"{BASE}/documents/service/job/{job_id}",
                          headers={"X-GridPull-Service-Token": TOKEN}, timeout=10)
        if poll.status_code != 200:
            print(f"  Poll error: {poll.status_code}")
            continue
        status = poll.json()
        if status.get("status") == "complete":
            elapsed = time.time() - t0
            print(f"  COMPLETE in {elapsed:.1f}s")

            # Fetch results
            res = requests.get(f"{BASE}/documents/service/results/{job_id}",
                             headers={"X-GridPull-Service-Token": TOKEN}, timeout=10)
            if res.status_code == 200:
                data = res.json()
                rows = data.get("results", [])
                field_names = [f["name"] for f in fields]
                filled = sum(1 for r in rows for fn in field_names
                           if r.get(fn) is not None and str(r[fn]).strip().lower() not in ("","null","none","n/a"))
                total = len(rows) * len(field_names)
                pct = filled / total * 100 if total else 0
                print(f"  Rows: {len(rows)} | Fill: {filled}/{total} ({pct:.0f}%)")
                if rows:
                    sample = {k: str(v)[:40] for k,v in rows[0].items() if k not in ("_source_file","_error") and v is not None and str(v).strip()}
                    print(f"  Sample: {json.dumps(sample)[:200]}")

                # Test download
                dl = requests.get(f"{BASE}/documents/service/download/{job_id}",
                                headers={"X-GridPull-Service-Token": TOKEN}, timeout=10)
                if dl.status_code == 200:
                    print(f"  Download: {len(dl.content)} bytes, content-type={dl.headers.get('content-type','?')}")
                else:
                    print(f"  Download FAIL: {dl.status_code}")

                return {"rows": len(rows), "fill_pct": pct, "time": elapsed}
            else:
                print(f"  Results fetch FAIL: {res.status_code}")
                return None

        elif status.get("status") == "error":
            elapsed = time.time() - t0
            print(f"  ERROR after {elapsed:.1f}s: {status.get('error', '?')}")
            return None

        if i % 10 == 0 and i > 0:
            print(f"  ... waiting ({i*3}s, status={status.get('status')}, progress={status.get('progress')}%)")

    print(f"  TIMEOUT after 360s")
    return None


def main():
    results = []

    # Test 1: SOV property schedule (25 buildings)
    r = test_extraction(
        "25-building SOV (production)",
        f"{TEST_DOCS}/10_sov_samples/01_property_appraisal_report_25_buildings.pdf",
        [
            {"name": "Location #", "description": "Location number"},
            {"name": "Address", "description": "Street address"},
            {"name": "City", "description": "City"},
            {"name": "State", "description": "State"},
            {"name": "Zip Code", "description": "ZIP code"},
            {"name": "Building Value", "description": "Building value"},
            {"name": "Total Insured Value", "description": "TIV"},
        ],
        pipeline="sov",
    )
    results.append(("25-building SOV", r))

    # Test 2: Vehicle schedule (35 vehicles)
    r = test_extraction(
        "35-vehicle schedule (production)",
        f"{TEST_DOCS}/10_sov_samples/04_vehicle_schedule_35_vehicles.pdf",
        [
            {"name": "Vehicle #", "description": "Vehicle number"},
            {"name": "Year", "description": "Model year"},
            {"name": "Make", "description": "Manufacturer"},
            {"name": "Model", "description": "Model name"},
            {"name": "VIN", "description": "Vehicle identification number"},
            {"name": "Value", "description": "Insured value"},
            {"name": "Garage Location", "description": "Garage location"},
        ],
        pipeline="sov",
    )
    results.append(("35-vehicle", r))

    # Test 3: Invoice via general pipeline
    r = test_extraction(
        "Invoice via general pipeline (production)",
        f"{TEST_DOCS}/01_invoices/invoice_Aaron Bergman_36258.pdf",
        [
            {"name": "Invoice Number", "description": "Invoice number"},
            {"name": "Customer Name", "description": "Customer name"},
            {"name": "Total Amount", "description": "Total amount"},
            {"name": "Invoice Date", "description": "Date"},
        ],
        pipeline="general",
    )
    results.append(("Invoice general", r))

    # Test 4: 50-location carrier schedule
    r = test_extraction(
        "50-location carrier schedule (production)",
        f"{TEST_DOCS}/10_sov_samples/02_carrier_property_schedule_50_locations.pdf",
        [
            {"name": "Location #", "description": "Location number"},
            {"name": "Address", "description": "Street address"},
            {"name": "City", "description": "City"},
            {"name": "State", "description": "State"},
            {"name": "Zip Code", "description": "ZIP code"},
            {"name": "Building Value", "description": "Building value"},
            {"name": "Contents Value", "description": "Contents value"},
            {"name": "Total Insured Value", "description": "TIV"},
        ],
        pipeline="sov",
    )
    results.append(("50-location", r))

    print(f"\n{'='*60}")
    print("LIVE API TEST SUMMARY")
    print(f"{'='*60}")
    for label, r in results:
        if r:
            status = "PASS" if r["rows"] >= 1 and r["fill_pct"] > 20 else "FAIL"
            print(f"  {status} {label}: {r['rows']} rows, {r['fill_pct']:.0f}% fill, {r['time']:.1f}s")
        else:
            print(f"  FAIL {label}: no result")
    print(f"{'='*60}")


if __name__ == "__main__":
    main()
