import io
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


def generate_excel_bytes(
    data: List[Dict[str, Any]],
    fields: List[str],
) -> bytes:
    """Generate Excel workbook and return raw bytes (for in-memory upload)."""
    buf = io.BytesIO()
    # Reuse generate_excel logic by saving to a BytesIO buffer
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Extracted Data"

    header_fill = PatternFill(start_color="4F46E5", end_color="4F46E5", fill_type="solid")
    header_font = Font(color="FFFFFF", bold=True, size=11)
    header_alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)

    headers = ["Source File"] + fields
    for col_idx, header in enumerate(headers, 1):
        cell = ws.cell(row=1, column=col_idx, value=header)
        cell.fill = header_fill
        cell.font = header_font
        cell.alignment = header_alignment

    alt_fill = PatternFill(start_color="F3F4F6", end_color="F3F4F6", fill_type="solid")
    for row_idx, row_data in enumerate(data, 2):
        fill = alt_fill if row_idx % 2 == 0 else None
        cell = ws.cell(row=row_idx, column=1, value=row_data.get("_source_file", ""))
        cell.alignment = Alignment(vertical="center")
        if fill:
            cell.fill = fill
        for col_idx, field in enumerate(fields, 2):
            cell = ws.cell(row=row_idx, column=col_idx, value=row_data.get(field, ""))
            cell.alignment = Alignment(vertical="center", wrap_text=True)
            if fill:
                cell.fill = fill

    for col_idx, header in enumerate(headers, 1):
        col_letter = get_column_letter(col_idx)
        max_length = len(str(header))
        for row in ws.iter_rows(min_row=2, min_col=col_idx, max_col=col_idx):
            for cell in row:
                if cell.value:
                    max_length = max(max_length, min(len(str(cell.value)), 50))
        ws.column_dimensions[col_letter].width = max_length + 4

    ws.freeze_panes = "A2"
    ws.row_dimensions[1].height = 30

    wb.save(buf)
    return buf.getvalue()


def append_to_excel_bytes(
    existing_bytes: bytes,
    new_rows: List[Dict[str, Any]],
    fields: List[str],
) -> bytes:
    """Load an existing Excel workbook from bytes, append new data rows, return bytes."""
    buf = io.BytesIO(existing_bytes)
    wb = openpyxl.load_workbook(buf)
    ws = wb.active

    # Read existing header row → column index map
    existing_headers = [ws.cell(row=1, column=c).value for c in range(1, ws.max_column + 1)]
    header_map = {str(h): idx + 1 for idx, h in enumerate(existing_headers) if h}

    alt_fill = PatternFill(start_color="F3F4F6", end_color="F3F4F6", fill_type="solid")

    for row_data in new_rows:
        next_row = ws.max_row + 1
        fill = alt_fill if next_row % 2 == 0 else None

        cell = ws.cell(row=next_row, column=1, value=row_data.get("_source_file", ""))
        cell.alignment = Alignment(vertical="center")
        if fill:
            cell.fill = fill

        for field in fields:
            col_idx = header_map.get(field)
            if col_idx is None:
                continue
            cell = ws.cell(row=next_row, column=col_idx, value=row_data.get(field, ""))
            cell.alignment = Alignment(vertical="center", wrap_text=True)
            if fill:
                cell.fill = fill

    out_buf = io.BytesIO()
    wb.save(out_buf)
    return out_buf.getvalue()


def append_to_csv_bytes(
    existing_bytes: bytes,
    new_rows: List[Dict[str, Any]],
    fields: List[str],
) -> bytes:
    """Append new data rows to existing CSV bytes."""
    existing_text = existing_bytes.decode("utf-8-sig").rstrip("\n")
    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=["Source File"] + fields, extrasaction="ignore")
    for row_data in new_rows:
        row = {"Source File": row_data.get("_source_file", "")}
        for field in fields:
            row[field] = row_data.get(field, "")
        writer.writerow(row)
    return (existing_text + "\n" + buf.getvalue()).encode("utf-8")


def generate_csv_bytes(
    data: List[Dict[str, Any]],
    fields: List[str],
) -> bytes:
    """Generate CSV and return raw bytes (for in-memory upload)."""
    headers = ["Source File"] + fields
    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=headers, extrasaction="ignore")
    writer.writeheader()
    for row_data in data:
        row = {"Source File": row_data.get("_source_file", "")}
        for field in fields:
            row[field] = row_data.get(field, "")
        writer.writerow(row)
    return buf.getvalue().encode("utf-8")


def read_headers_from_bytes(data: bytes, fmt: str) -> List[str]:
    """Return the header row (first row) from an existing xlsx or csv spreadsheet."""
    if fmt == "csv":
        text = data.decode("utf-8-sig")
        reader = csv.reader(io.StringIO(text))
        try:
            return next(reader)
        except StopIteration:
            return []
    else:
        buf = io.BytesIO(data)
        wb = openpyxl.load_workbook(buf, read_only=True)
        ws = wb.active
        for row in ws.iter_rows(min_row=1, max_row=1, values_only=True):
            return [str(c) if c is not None else "" for c in row]
        return []


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
