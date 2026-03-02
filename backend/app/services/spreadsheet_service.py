import openpyxl
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.utils import get_column_letter
import csv
import os
from typing import List, Dict, Any


def generate_excel(
    data: List[Dict[str, Any]],
    output_path: str,
    fields: List[str],
) -> str:
    """Generate Excel file from extracted data."""
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Extracted Data"

    # Header styling
    header_fill = PatternFill(start_color="4F46E5", end_color="4F46E5", fill_type="solid")
    header_font = Font(color="FFFFFF", bold=True, size=11)
    header_alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)

    # Build headers (source file + fields)
    headers = ["Source File"] + fields

    for col_idx, header in enumerate(headers, 1):
        cell = ws.cell(row=1, column=col_idx, value=header)
        cell.fill = header_fill
        cell.font = header_font
        cell.alignment = header_alignment

    # Data rows
    alt_fill = PatternFill(start_color="F3F4F6", end_color="F3F4F6", fill_type="solid")

    for row_idx, row_data in enumerate(data, 2):
        fill = alt_fill if row_idx % 2 == 0 else None

        # Source file
        cell = ws.cell(row=row_idx, column=1, value=row_data.get("_source_file", ""))
        cell.alignment = Alignment(vertical="center")
        if fill:
            cell.fill = fill

        for col_idx, field in enumerate(fields, 2):
            cell = ws.cell(row=row_idx, column=col_idx, value=row_data.get(field, ""))
            cell.alignment = Alignment(vertical="center", wrap_text=True)
            if fill:
                cell.fill = fill

    # Auto-fit column widths
    for col_idx, header in enumerate(headers, 1):
        col_letter = get_column_letter(col_idx)
        max_length = len(str(header))
        for row in ws.iter_rows(min_row=2, min_col=col_idx, max_col=col_idx):
            for cell in row:
                if cell.value:
                    max_length = max(max_length, min(len(str(cell.value)), 50))
        ws.column_dimensions[col_letter].width = max_length + 4

    # Freeze header row
    ws.freeze_panes = "A2"

    # Row height for header
    ws.row_dimensions[1].height = 30

    wb.save(output_path)
    return output_path


def generate_csv(
    data: List[Dict[str, Any]],
    output_path: str,
    fields: List[str],
) -> str:
    """Generate CSV file from extracted data."""
    headers = ["Source File"] + fields

    with open(output_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=headers,
            extrasaction="ignore",
        )
        writer.writeheader()

        for row_data in data:
            row = {"Source File": row_data.get("_source_file", "")}
            for field in fields:
                row[field] = row_data.get(field, "")
            writer.writerow(row)

    return output_path
