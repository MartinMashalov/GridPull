from __future__ import annotations

import sys
import unittest
from pathlib import Path

_BACKEND = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_BACKEND))

from app.services.extraction.core import (
    _extract_table_headers,
    _field_name_matches_any_header,
    sanitize_unmatched_field_values,
)
from app.services.extraction.llm import finalize_property_schedule_rows
from app.services.pdf_service import ParsedDocument, ParsedPage, ParsedTable
from app.services.sov.pipeline import _estimate_expected_rows


class SovCleanupHelperTests(unittest.TestCase):
    def test_matches_bpp_field_against_row_label_initialism(self) -> None:
        table = ParsedTable(
            page_num=1,
            row_count=6,
            col_count=4,
            markdown=(
                "| Coverage | Limit | Valuation | Deductible |\n"
                "| --- | --- | --- | --- |\n"
                "| Building | $1,000 | RCV | $100 |\n"
                "| Business Personal Property | $250 | RCV | $100 |\n"
                "| Business Income / Extra Expense | $125 | ALS | 72 Hour |\n"
                "| Total Insured Value | $1,375 |  |  |"
            ),
        )

        headers = _extract_table_headers([table])

        self.assertIn("business personal property", headers)
        self.assertTrue(_field_name_matches_any_header("Contents / BPP Value", headers, ""))

    def test_preserves_varying_schedule_values_when_row_labels_exist(self) -> None:
        table = ParsedTable(
            page_num=1,
            row_count=6,
            col_count=4,
            markdown=(
                "| Coverage | Limit | Valuation | Deductible |\n"
                "| --- | --- | --- | --- |\n"
                "| Building | $1,000 | RCV | $100 |\n"
                "| Business Personal Property | $250 | RCV | $100 |\n"
                "| Business Income / Extra Expense | $125 | ALS | 72 Hour |\n"
                "| Total Insured Value | $1,375 |  |  |"
            ),
        )
        rows = [
            {"Contents / BPP Value": "250", "Business Income Value": "125"},
            {"Contents / BPP Value": "500", "Business Income Value": "225"},
            {"Contents / BPP Value": "750", "Business Income Value": "325"},
        ]

        cleaned = sanitize_unmatched_field_values(
            rows,
            ["Contents / BPP Value", "Business Income Value"],
            doc_text=table.markdown,
            tables=[table],
        )

        self.assertEqual([row["Contents / BPP Value"] for row in cleaned], ["250", "500", "750"])
        self.assertEqual([row["Business Income Value"] for row in cleaned], ["125", "225", "325"])

    def test_preserves_zip_values_with_short_document_label(self) -> None:
        rows = [
            {"Zip": "19101"},
            {"Zip": "45201"},
            {"Zip": "08817"},
        ]

        cleaned = sanitize_unmatched_field_values(
            rows,
            ["Zip"],
            doc_text="City, State, Zip:\nPhiladelphia, PA 19101\nCincinnati, OH 45201\nEdison, NJ 08817",
            tables=None,
        )

        self.assertEqual([row["Zip"] for row in cleaned], ["19101", "45201", "08817"])

    def test_estimate_expected_rows_prefers_textual_total_over_table_sum(self) -> None:
        pages = [
            ParsedPage(
                page_num=1,
                text="COMMERCIAL AUTO COVERAGE - SCHEDULE OF COVERED AUTOS\nTotal Vehicles: 35",
                tables=[],
                word_count=10,
                has_numbers=True,
                has_dates=False,
            )
        ]
        tables = [
            ParsedTable(
                page_num=1,
                row_count=22,
                col_count=14,
                markdown=(
                    "| Veh# | Year | Make | Model | VIN | Body | GVW | Cost New | Coverage | Comp Ded | Coll Ded | Garaging Location | Radius | Use |\n"
                    "| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |\n"
                    "| 1 | 2023 | Toyota | Tacoma | A | Pickup | N/A | $1 | Comp/Coll | $500 | $500 | Austin, TX 78701 | 100 | Service |"
                ),
            ),
            ParsedTable(
                page_num=2,
                row_count=16,
                col_count=14,
                markdown=(
                    "| Veh# | Year | Make | Model | VIN | Body | GVW | Cost New | Coverage | Comp Ded | Coll Ded | Garaging Location | Radius | Use |\n"
                    "| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |\n"
                    "| 22 | 2024 | GMC | Savana | B | Van | N/A | $2 | Comp/Coll | $500 | $500 | Phoenix, AZ 85001 | 25 | Service |"
                ),
            ),
        ]
        doc = ParsedDocument(
            filename="vehicle_schedule.pdf",
            file_path="vehicle_schedule.pdf",
            page_count=2,
            pages=pages,
            tables=tables,
            content_text=pages[0].text,
            tables_markdown="\n\n".join(table.markdown for table in tables),
            doc_type_hint="dense_tables",
            has_tables=True,
            is_scanned=False,
        )

        self.assertEqual(_estimate_expected_rows(doc, {1, 2}), 35)

    def test_finalize_rows_merges_using_value_inferred_key_fields(self) -> None:
        rows = [
            {
                "Column A": "1",
                "Column B": "100 Main St",
                "Column C": "Austin",
                "Column D": "2001",
                "Metric X": None,
                "Metric Y": "250000",
            },
            {
                "Column A": "1",
                "Column B": "100 Main St",
                "Column C": "Austin",
                "Column D": "2001",
                "Metric X": "Frame",
                "Metric Y": None,
            },
            {
                "Column A": "2",
                "Column B": "200 Oak Ave",
                "Column C": "Dallas",
                "Column D": "1998",
                "Metric X": "Masonry",
                "Metric Y": "375000",
            },
        ]

        cleaned = finalize_property_schedule_rows(
            rows,
            ["Column A", "Column B", "Column C", "Column D", "Metric X", "Metric Y"],
        )

        self.assertEqual(len(cleaned), 2)
        self.assertEqual(cleaned[0]["Metric X"], "Frame")
        self.assertEqual(cleaned[0]["Metric Y"], "250000")


if __name__ == "__main__":
    unittest.main()
