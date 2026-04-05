"""
Generate payroll_schedule_25_employees.pdf
Horizon Analytics LLC — Payroll Register
3-page PORTRAIT PDF, ~9-10 employees per page.
"""

from reportlab.lib.pagesizes import letter
from reportlab.lib import colors
from reportlab.lib.units import inch
from reportlab.platypus import (
    SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, PageBreak
)
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT
from reportlab.pdfgen import canvas
import os

OUTPUT = os.path.join(os.path.dirname(__file__), "payroll_schedule_25_employees.pdf")

HDR_BG   = colors.HexColor("#5C2D91")
HDR_FG   = colors.white
ROW_ALT  = colors.HexColor("#F3EEF9")
ROW_NORM = colors.white
BORDER   = colors.HexColor("#C4A8E8")
TITLE_C  = colors.HexColor("#5C2D91")
SUB_C    = colors.HexColor("#4A5568")
ACCENT   = colors.HexColor("#7B3FB5")

PAGE_W, PAGE_H = letter
MARGIN = 0.5 * inch


# ── 25 employees ─────────────────────────────────────────────────────────────
# Columns: Emp ID | Last Name | First Name | Dept | Title | Start Dt | Status | FLSA | Pay Type | Base Pay | Bonus% | Benefits | 401k% | State | Manager ID

employees = [
    # --- Engineering (8 employees) ---
    ["E-1001","Okonkwo",    "Chukwuemeka","Engineering","VP of Engineering",       "03/15/2018","FT",      "Exempt",    "Salary",  "$185,000","15%","Executive","6%", "CA","E-0500"],
    ["E-1002","Nakashima",  "Hiroko",     "Engineering","Principal Engineer",       "06/01/2019","FT",      "Exempt",    "Salary",  "$162,000","12%","Enhanced", "5%", "CA","E-1001"],
    ["E-1003","Vasquez",    "Rodrigo",    "Engineering","Senior Software Engineer", "11/12/2020","FT",      "Exempt",    "Salary",  "$138,500","10%","Enhanced", "5%", "WA","E-1001"],
    ["E-1004","Brennan",    "Siobhan",    "Engineering","Software Engineer II",     "02/28/2021","FT",      "Exempt",    "Salary",  "$118,000","8%", "Standard", "4%", "WA","E-1002"],
    ["E-1005","Gupta",      "Priya",      "Engineering","Software Engineer I",      "08/09/2022","FT",      "Exempt",    "Salary",  "$98,500", "6%", "Standard", "4%", "TX","E-1002"],
    ["E-1006","Marchetti",  "Luca",       "Engineering","DevOps Engineer",          "05/17/2021","FT",      "Exempt",    "Salary",  "$125,000","8%", "Enhanced", "5%", "TX","E-1003"],
    ["E-1007","Osei",       "Kwame",      "Engineering","QA Engineer",              "01/10/2023","FT",      "Non-Exempt","Hourly",  "$42.50/h","5%", "Standard", "3%", "GA","E-1003"],
    ["E-1008","Lindqvist",  "Astrid",     "Engineering","Contract Dev",             "09/01/2023","Contract","Exempt",    "Hourly",  "$55.00/h","0%", "Standard", "0%", "NY","E-1001"],

    # --- Sales (6 employees) ---
    ["E-2001","Fontaine",   "Isabelle",   "Sales",      "VP of Sales",              "07/22/2017","FT",      "Exempt",    "Salary",  "$175,000","20%","Executive","6%", "IL","E-0500"],
    ["E-2002","Oduya",      "Taiwo",      "Sales",      "Regional Sales Manager",   "03/05/2019","FT",      "Exempt",    "Salary",  "$132,000","18%","Enhanced", "5%", "IL","E-2001"],
    ["E-2003","Peralta",    "Marco",      "Sales",      "Account Executive",        "10/14/2020","FT",      "Exempt",    "Salary",  "$88,000", "22%","Standard", "4%", "FL","E-2002"],
    ["E-2004","Johansson",  "Britta",     "Sales",      "Account Executive",        "04/19/2021","FT",      "Exempt",    "Salary",  "$85,000", "22%","Standard", "4%", "FL","E-2002"],
    ["E-2005","Kaur",       "Parveen",    "Sales",      "Sales Development Rep",    "06/27/2022","FT",      "Non-Exempt","Hourly",  "$28.00/h","10%","Standard", "3%", "TX","E-2002"],
    ["E-2006","Thornton",   "Beau",       "Sales",      "Sales Operations Analyst", "11/01/2022","FT",      "Non-Exempt","Hourly",  "$26.50/h","5%", "Standard", "3%", "TX","E-2001"],

    # --- Marketing (4 employees) ---
    ["E-3001","Delacroix",  "Celine",     "Marketing",  "Director of Marketing",    "08/30/2018","FT",      "Exempt",    "Salary",  "$145,000","12%","Enhanced", "5%", "NY","E-0500"],
    ["E-3002","Achebe",     "Nnamdi",     "Marketing",  "Content Marketing Manager","05/11/2020","FT",      "Exempt",    "Salary",  "$98,000", "8%", "Standard", "4%", "NY","E-3001"],
    ["E-3003","Stein",      "Rebecca",    "Marketing",  "Digital Marketing Spec.",  "03/22/2021","FT",      "Non-Exempt","Hourly",  "$32.00/h","5%", "Standard", "3%", "CA","E-3001"],
    ["E-3004","Nguyen",     "Thanh",      "Marketing",  "Graphic Designer",         "09/05/2022","FT",      "Non-Exempt","Hourly",  "$29.50/h","5%", "Standard", "3%", "CA","E-3001"],

    # --- Finance (4 employees) ---
    ["E-4001","Mbeki",      "Thabo",      "Finance",    "CFO",                      "01/15/2016","FT",      "Exempt",    "Salary",  "$195,000","15%","Executive","6%", "IL","E-0500"],
    ["E-4002","Kowalczyk",  "Agnieszka",  "Finance",    "Controller",               "04/08/2018","FT",      "Exempt",    "Salary",  "$148,000","10%","Enhanced", "5%", "IL","E-4001"],
    ["E-4003","Sullivan",   "Declan",     "Finance",    "Senior Accountant",        "07/14/2020","FT",      "Exempt",    "Salary",  "$92,000", "7%", "Standard", "4%", "IL","E-4002"],
    ["E-4004","Pham",       "Linh",       "Finance",    "Accounts Payable Spec.",   "02/01/2023","FT",      "Non-Exempt","Hourly",  "$24.00/h","0%", "Standard", "3%", "IL","E-4002"],

    # --- Operations (3 employees) ---
    ["E-5001","Abramowitz", "Moshe",      "Operations", "Director of Operations",   "06/01/2017","FT",      "Exempt",    "Salary",  "$155,000","10%","Enhanced", "5%", "OH","E-0500"],
    ["E-5002","Guerrero",   "Esperanza",  "Operations", "Operations Manager",       "09/23/2019","FT",      "Exempt",    "Salary",  "$112,000","8%", "Standard", "4%", "OH","E-5001"],
    ["E-5003","Park",       "Jin-ho",     "Operations", "Facilities Coordinator",   "04/12/2022","FT",      "Non-Exempt","Hourly",  "$22.00/h","3%", "Standard", "3%", "OH","E-5001"],
]

HEADERS = [
    "Emp ID","Last Name","First Name","Dept","Title",
    "Start Dt","Status","FLSA","Pay Type","Base Pay",
    "Bonus %","Benefits","401k %","State","Manager ID"
]

# portrait letter usable ≈ 7.5" = 540 pts (with 0.5" margins)
COL_WIDTHS = [36, 52, 46, 52, 100, 40, 36, 44, 36, 48, 32, 44, 30, 28, 40]
# sum = 664 → too wide; scale down — let reportlab handle with word-wrap
# Actually reduce some
COL_WIDTHS = [34, 48, 44, 48, 96, 38, 34, 42, 34, 46, 30, 44, 28, 26, 38]
# sum = 634 — still a bit wide; we'll use 0.5" margins → 612-72 = 540 usable
# Let's just trim and scale:
COL_WIDTHS = [32, 44, 40, 44, 88, 36, 32, 40, 32, 44, 28, 40, 26, 24, 36]
# sum = 586; fits within 612 pts


def make_table(data_rows):
    table_data = [HEADERS] + data_rows

    style = TableStyle([
        # header
        ("BACKGROUND",   (0, 0),  (-1, 0),  HDR_BG),
        ("TEXTCOLOR",    (0, 0),  (-1, 0),  HDR_FG),
        ("FONTNAME",     (0, 0),  (-1, 0),  "Helvetica-Bold"),
        ("FONTSIZE",     (0, 0),  (-1, 0),  6.5),
        ("ALIGN",        (0, 0),  (-1, 0),  "CENTER"),
        ("VALIGN",       (0, 0),  (-1, 0),  "MIDDLE"),
        ("TOPPADDING",   (0, 0),  (-1, 0),  4),
        ("BOTTOMPADDING",(0, 0),  (-1, 0),  4),
        # data
        ("FONTNAME",     (0, 1),  (-1, -1), "Helvetica"),
        ("FONTSIZE",     (0, 1),  (-1, -1), 6.2),
        ("VALIGN",       (0, 1),  (-1, -1), "MIDDLE"),
        ("TOPPADDING",   (0, 1),  (-1, -1), 3),
        ("BOTTOMPADDING",(0, 1),  (-1, -1), 3),
        # alt rows
        *[("BACKGROUND", (0, r), (-1, r), ROW_ALT if r % 2 == 0 else ROW_NORM)
          for r in range(1, len(table_data))],
        # grid
        ("GRID",         (0, 0),  (-1, -1), 0.35, BORDER),
        ("LINEBELOW",    (0, 0),  (-1, 0),  1.0,  HDR_BG),
        # right-align Base Pay, Bonus%
        ("ALIGN",        (9,  1), (9,  -1), "RIGHT"),
        ("ALIGN",        (10, 1), (10, -1), "CENTER"),
        # center various
        ("ALIGN",        (0,  1), (0,  -1), "CENTER"),
        ("ALIGN",        (5,  1), (8,  -1), "CENTER"),
        ("ALIGN",        (11, 1), (14, -1), "CENTER"),
    ])

    tbl = Table(table_data, colWidths=COL_WIDTHS, repeatRows=0)
    tbl.setStyle(style)
    return tbl


class NumberedCanvas(canvas.Canvas):
    def __init__(self, *args, **kwargs):
        canvas.Canvas.__init__(self, *args, **kwargs)
        self._saved_page_states = []

    def showPage(self):
        self._saved_page_states.append(dict(self.__dict__))
        self._startPage()

    def save(self):
        num_pages = len(self._saved_page_states)
        for state in self._saved_page_states:
            self.__dict__.update(state)
            self.draw_footer(num_pages)
            canvas.Canvas.showPage(self)
        canvas.Canvas.save(self)

    def draw_footer(self, page_count):
        self.setFont("Helvetica", 7)
        self.setFillColor(SUB_C)
        txt = (f"Page {self._pageNumber} of {page_count}  |  "
               "Horizon Analytics LLC — Payroll Register  |  Confidential – HR Use Only")
        self.drawCentredString(PAGE_W / 2, 0.28 * inch, txt)


def build():
    title_style = ParagraphStyle(
        "Title", fontName="Helvetica-Bold", fontSize=13,
        textColor=TITLE_C, alignment=TA_LEFT, spaceAfter=2
    )
    sub_style = ParagraphStyle(
        "Sub", fontName="Helvetica", fontSize=8,
        textColor=SUB_C, alignment=TA_LEFT, spaceAfter=5
    )
    dept_style = ParagraphStyle(
        "Dept", fontName="Helvetica-Bold", fontSize=7.5,
        textColor=ACCENT, alignment=TA_LEFT, spaceBefore=6, spaceAfter=2
    )
    note_style = ParagraphStyle(
        "Note", fontName="Helvetica-Oblique", fontSize=6.2,
        textColor=SUB_C, alignment=TA_LEFT
    )

    story = []

    # Page splits: Engineering (8) + Sales start (1) = 9 | Sales (5) + Marketing (4) = 9 | Finance (4) + Ops (3) = 7
    # We'll do: rows 0-8 (9 emp), rows 9-17 (9 emp), rows 18-24 (7 emp)
    pages_data = [employees[0:9], employees[9:18], employees[18:25]]
    page_labels = ["1–9", "10–18", "19–25"]

    for i, page_emps in enumerate(pages_data):
        story.append(Paragraph("HORIZON ANALYTICS LLC", title_style))
        story.append(Paragraph(
            f"Payroll Register &nbsp;|&nbsp; Pay Period: Q1 2026 &nbsp;|&nbsp; "
            f"Employees {page_labels[i]} of 25 &nbsp;|&nbsp; "
            "Effective Date: 04/01/2026",
            sub_style
        ))

        story.append(make_table(page_emps))

        story.append(Spacer(1, 5))
        story.append(Paragraph(
            "Base Pay: Salary = Annual; Hourly rate shown as $/h  |  "
            "Status: FT = Full-Time, PT = Part-Time  |  "
            "FLSA: Exempt / Non-Exempt  |  "
            "Benefits: Standard / Enhanced / Executive  |  "
            "401k% = Employee contribution",
            note_style
        ))

        if i < 2:
            story.append(PageBreak())

    doc = SimpleDocTemplate(
        OUTPUT,
        pagesize=letter,
        leftMargin=MARGIN, rightMargin=MARGIN,
        topMargin=0.50 * inch, bottomMargin=0.50 * inch,
    )
    doc.build(story, canvasmaker=NumberedCanvas)
    print(f"Generated: {OUTPUT}")


if __name__ == "__main__":
    build()
