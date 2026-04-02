from __future__ import annotations

import csv
import io
import sys
import unittest
from pathlib import Path

import openpyxl

_BACKEND = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_BACKEND))

from app.services.spreadsheet_service import update_csv_baseline_bytes, update_excel_baseline_bytes


class SpreadsheetBaselineUpdateTests(unittest.TestCase):
    def test_excel_updates_matched_rows_and_flags_missing_rows(self) -> None:
        wb = openpyxl.Workbook()
        ws = wb.active
        ws.append(["Location Number", "Street Address", "City", "State", "Zip", "Building Values", "Owner Note"])
        ws.append(["100", "100 Main St", "Austin", "TX", "78701", "100000", "keep"])
        ws.append(["200", "200 Main St", "Austin", "TX", "78702", "200000", "keep"])

        buf = io.BytesIO()
        wb.save(buf)

        output = update_excel_baseline_bytes(
            buf.getvalue(),
            [
                {
                    "Location Number": "100",
                    "Street Address": "100 Main St",
                    "City": "Austin",
                    "State": "TX",
                    "Zip": "78701",
                    "Building Values": "150000",
                    "_source_file": "renewal_a.pdf",
                },
                {
                    "Location Number": "300",
                    "Street Address": "300 Main St",
                    "City": "Austin",
                    "State": "TX",
                    "Zip": "78703",
                    "Building Values": "300000",
                    "_source_file": "renewal_b.pdf",
                },
            ],
            ["Location Number", "Street Address", "City", "State", "Zip", "Building Values"],
            True,
        )

        out_wb = openpyxl.load_workbook(io.BytesIO(output))
        out_ws = out_wb.active
        headers = [cell for cell in next(out_ws.iter_rows(min_row=1, max_row=1, values_only=True)) if cell]
        rows = list(out_ws.iter_rows(min_row=2, values_only=True))
        by_location = {str(row[0]): row for row in rows if row[0] is not None}
        status_idx = headers.index("GridPull Status")
        building_idx = headers.index("Building Values")
        owner_note_idx = headers.index("Owner Note")

        self.assertEqual(by_location["100"][building_idx], "150000")
        self.assertEqual(by_location["100"][owner_note_idx], "keep")
        self.assertEqual(by_location["100"][status_idx], "updated")

        self.assertEqual(by_location["200"][building_idx], "200000")
        self.assertEqual(by_location["200"][status_idx], "not_found")

        self.assertEqual(by_location["300"][building_idx], "300000")
        self.assertEqual(by_location["300"][status_idx], "new")

    def test_csv_preserves_matched_rows_when_overwrite_disabled(self) -> None:
        buf = io.StringIO()
        writer = csv.DictWriter(
            buf,
            fieldnames=["Street Address", "City", "State", "Zip", "Building Values", "Owner Note"],
        )
        writer.writeheader()
        writer.writerow(
            {
                "Street Address": "10 Main St",
                "City": "Austin",
                "State": "TX",
                "Zip": "78701",
                "Building Values": "100000",
                "Owner Note": "keep",
            }
        )
        writer.writerow(
            {
                "Street Address": "20 Main St",
                "City": "Austin",
                "State": "TX",
                "Zip": "78702",
                "Building Values": "200000",
                "Owner Note": "keep",
            }
        )

        output = update_csv_baseline_bytes(
            buf.getvalue().encode("utf-8"),
            [
                {
                    "Street Address": "10 Main St",
                    "City": "Austin",
                    "State": "TX",
                    "Zip": "78701",
                    "Building Values": "999999",
                    "_source_file": "renewal_c.pdf",
                },
                {
                    "Street Address": "30 Main St",
                    "City": "Austin",
                    "State": "TX",
                    "Zip": "78703",
                    "Building Values": "300000",
                    "_source_file": "renewal_d.pdf",
                },
            ],
            ["Street Address", "City", "State", "Zip", "Building Values"],
            False,
        )

        reader = csv.DictReader(io.StringIO(output.decode("utf-8")))
        rows = list(reader)
        by_address = {row["Street Address"]: row for row in rows}

        self.assertEqual(by_address["10 Main St"]["Building Values"], "100000")
        self.assertEqual(by_address["10 Main St"]["Owner Note"], "keep")
        self.assertEqual(by_address["10 Main St"]["GridPull Status"], "matched_preserved")

        self.assertEqual(by_address["20 Main St"]["Building Values"], "200000")
        self.assertEqual(by_address["20 Main St"]["GridPull Status"], "not_found")

        self.assertEqual(by_address["30 Main St"]["Building Values"], "300000")
        self.assertEqual(by_address["30 Main St"]["GridPull Status"], "new")


if __name__ == "__main__":
    unittest.main()
