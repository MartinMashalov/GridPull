"""
Generate fleet_schedule_18_vehicles.pdf
Meridian Transport Co. — Fleet/Vehicle Insurance Schedule
3-page landscape PDF, 6 vehicles per page, header repeated each page.
"""

from reportlab.lib.pagesizes import landscape, letter
from reportlab.lib import colors
from reportlab.lib.units import inch
from reportlab.platypus import (
    SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, PageBreak
)
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT
from reportlab.pdfgen import canvas
import os

OUTPUT = os.path.join(os.path.dirname(__file__), "fleet_schedule_18_vehicles.pdf")

# ── palette ──────────────────────────────────────────────────────────────────
HDR_BG   = colors.HexColor("#1B3A6B")
HDR_FG   = colors.white
ROW_ALT  = colors.HexColor("#EDF2FA")
ROW_NORM = colors.white
BORDER   = colors.HexColor("#9EB4D4")
TITLE_C  = colors.HexColor("#1B3A6B")
SUB_C    = colors.HexColor("#4A5568")

PAGE_W, PAGE_H = landscape(letter)

# ── 18 vehicles ──────────────────────────────────────────────────────────────
# Columns (in order):
# Unit# | Yr | Mkr | Mdl | VIN | Gtng Loc | City/St | Zip | Radius | GVW | Body Type | Use | Sched Val | Act Cost New | Comp | Coll | TL

vehicles = [
    # Unit#  Yr    Mkr         Mdl              VIN                   Gtng Loc                      City/St           Zip     Radius  GVW      Body Type   Use          Sched Val    Act Cost New  Comp    Coll    TL
    ["1",   "2021","Freightliner","Cascadia 126","1FUJGHDV8MLBC4501","4821 Industrial Blvd",         "Dallas, TX",    "75247","500",  "80,000","Semi-Tractor","Long Haul", "$142,500", "$165,000",  "$2,500","$5,000","N"],
    ["2",   "2020","Kenworth",   "T680",         "2XKHHD8X5LM523716","4821 Industrial Blvd",         "Dallas, TX",    "75247","500",  "80,000","Semi-Tractor","Long Haul", "$128,000", "$148,000",  "$2,500","$5,000","N"],
    ["3",   "2022","Peterbilt",  "579",          "3BPSCZ9X4NF812034","4821 Industrial Blvd",         "Dallas, TX",    "75247","500",  "80,000","Semi-Tractor","Long Haul", "$155,000", "$172,500",  "$2,500","$5,000","N"],
    ["4",   "2019","International","LT625",      "3HSDJSKR9KN512287","4821 Industrial Blvd",         "Dallas, TX",    "75247","500",  "80,000","Semi-Tractor","Long Haul", "$98,500",  "$138,000",  "$2,500","$5,000","N"],
    ["5",   "2021","Isuzu",      "NPR-HD",       "JALC4B16XM7004923","7200 Warehouse Row",           "Phoenix, AZ",   "85043","150",  "14,500","Box Truck",  "Delivery",  "$58,000",  "$67,500",   "$1,000","$2,500","N"],
    ["6",   "2021","Isuzu",      "NPR-HD",       "JALC4B16XM7004924","7200 Warehouse Row",           "Phoenix, AZ",   "85043","150",  "14,500","Box Truck",  "Delivery",  "$57,500",  "$67,500",   "$1,000","$2,500","N"],

    ["7",   "2020","Hino",       "195",          "5PVNG8JV6L4S30287","7200 Warehouse Row",           "Phoenix, AZ",   "85043","100",  "19,500","Box Truck",  "Delivery",  "$49,000",  "$59,000",   "$1,000","$2,500","N"],
    ["8",   "2022","Ford",       "Transit 350",  "1FTBR3X86NKA24801","302 Commerce Park Dr",         "Atlanta, GA",   "30349","75",   "11,030","Cargo Van",  "Local",     "$38,500",  "$45,000",   "$1,000","$2,000","N"],
    ["9",   "2022","Ford",       "Transit 350",  "1FTBR3X86NKA24802","302 Commerce Park Dr",         "Atlanta, GA",   "30349","75",   "11,030","Cargo Van",  "Local",     "$38,500",  "$45,000",   "$1,000","$2,000","N"],
    ["10",  "2021","Ram",        "ProMaster 2500","3C6TRVBG7ME543901","302 Commerce Park Dr",         "Atlanta, GA",   "30349","75",   "8,550", "Cargo Van",  "Local",     "$34,000",  "$40,500",   "$1,000","$2,000","N"],
    ["11",  "2023","Freightliner","M2 106",      "1FVHG5DY5PHFC8811","9100 Port Access Rd",          "Houston, TX",   "77015","300",  "33,000","Box Truck",  "Delivery",  "$95,000",  "$108,000",  "$2,000","$3,500","N"],
    ["12",  "2023","Freightliner","M2 106",      "1FVHG5DY5PHFC8812","9100 Port Access Rd",          "Houston, TX",   "77015","300",  "33,000","Box Truck",  "Delivery",  "$95,000",  "$108,000",  "$2,000","$3,500","N"],

    ["13",  "2018","Kenworth",   "T270",         "2NKHHM6X7JM301445","9100 Port Access Rd",          "Houston, TX",   "77015","200",  "26,000","Box Truck",  "Local",     "$62,000",  "$95,000",   "$2,000","$3,500","N"],
    ["14",  "2020","Peterbilt",  "337",          "3BPSCZV97LF609321","1500 Distribution Way",        "Denver, CO",    "80239","250",  "33,000","Flatbed",    "Delivery",  "$78,500",  "$92,000",   "$1,500","$3,000","N"],
    ["15",  "2021","Mack",       "LR64",         "1M2AX07Y8MM002715","1500 Distribution Way",        "Denver, CO",    "80239","100",  "66,000","Dump Truck", "Service",   "$185,000", "$205,000",  "$2,500","$5,000","N"],
    ["16",  "2019","Ford",       "F-550",        "1FD0X5HT5KED90034","1500 Distribution Way",        "Denver, CO",    "80239","100",  "17,950","Service Truck","Service",  "$42,000",  "$58,000",   "$1,000","$2,000","N"],
    ["17",  "2022","Mercedes",   "Sprinter 2500","WD3PE7CD6NP608822","88 Logistics Center Pkwy",     "Portland, OR",  "97203","50",   "8,550", "Cargo Van",  "Local",     "$45,500",  "$52,000",   "$500", "$1,500","N"],
    ["18",  "2017","International","4300",        "1HTMKADN7JH512077","88 Logistics Center Pkwy",     "Portland, OR",  "97203","150",  "26,000","Box Truck",  "Delivery",  "$38,000",  "$72,000",   "$1,000","$2,500","Y"],
]

HEADERS = [
    "Unit #","Yr","Mkr","Mdl","VIN","Gtng Loc","City / St","Zip",
    "Radius","GVW","Body Type","Use","Sched Val","Act Cost New","Comp","Coll","TL"
]

# column widths (landscape letter = 10" usable at 0.5" margins = 792 - 72 pts wide)
# total must fit ≈ 720 pts
COL_WIDTHS = [28, 24, 54, 54, 88, 102, 68, 32, 34, 42, 56, 44, 54, 58, 34, 34, 18]
# sum = 728  (close enough; we'll use a 0.36" margin each side)

MARGIN = 0.36 * inch

def make_table(data_rows):
    """Build a ReportLab Table for the given data rows (6 rows + header)."""
    table_data = [HEADERS] + data_rows

    small = 6.5
    tiny  = 5.8

    style = TableStyle([
        # header
        ("BACKGROUND",  (0, 0), (-1, 0),  HDR_BG),
        ("TEXTCOLOR",   (0, 0), (-1, 0),  HDR_FG),
        ("FONTNAME",    (0, 0), (-1, 0),  "Helvetica-Bold"),
        ("FONTSIZE",    (0, 0), (-1, 0),  6.5),
        ("ALIGN",       (0, 0), (-1, 0),  "CENTER"),
        ("VALIGN",      (0, 0), (-1, 0),  "MIDDLE"),
        ("TOPPADDING",  (0, 0), (-1, 0),  4),
        ("BOTTOMPADDING",(0,0), (-1, 0),  4),
        # data rows
        ("FONTNAME",    (0, 1), (-1, -1), "Helvetica"),
        ("FONTSIZE",    (0, 1), (-1, -1), tiny),
        ("VALIGN",      (0, 1), (-1, -1), "MIDDLE"),
        ("TOPPADDING",  (0, 1), (-1, -1), 3),
        ("BOTTOMPADDING",(0,1), (-1, -1), 3),
        # alternating rows
        *[("BACKGROUND", (0, r), (-1, r), ROW_ALT if r % 2 == 0 else ROW_NORM)
          for r in range(1, len(table_data))],
        # grid
        ("GRID",        (0, 0), (-1, -1), 0.4, BORDER),
        ("LINEBELOW",   (0, 0), (-1, 0),  1.0, HDR_BG),
        # right-align numeric/dollar columns: Sched Val, Act Cost New, Comp, Coll
        ("ALIGN",       (12, 1), (15, -1), "RIGHT"),
        # center: Unit#, Yr, Zip, Radius, GVW, TL
        ("ALIGN",       (0, 1), (0, -1),  "CENTER"),
        ("ALIGN",       (1, 1), (1, -1),  "CENTER"),
        ("ALIGN",       (7, 1), (7, -1),  "CENTER"),
        ("ALIGN",       (8, 1), (8, -1),  "CENTER"),
        ("ALIGN",       (9, 1), (9, -1),  "CENTER"),
        ("ALIGN",       (16,1), (16,-1),  "CENTER"),
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
            self.draw_page_number(num_pages)
            canvas.Canvas.showPage(self)
        canvas.Canvas.save(self)

    def draw_page_number(self, page_count):
        page = self._saved_page_states.index(
            {k: v for k, v in self.__dict__.items() if k in self._saved_page_states[0]}
        ) if False else self._pageNumber
        self.setFont("Helvetica", 7)
        self.setFillColor(SUB_C)
        txt = f"Page {page} of {page_count}  |  Meridian Transport Co. — Fleet Schedule  |  Confidential"
        self.drawCentredString(PAGE_W / 2, 0.25 * inch, txt)


def build():
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        "FleetTitle", fontName="Helvetica-Bold", fontSize=13,
        textColor=TITLE_C, alignment=TA_LEFT, spaceAfter=2
    )
    sub_style = ParagraphStyle(
        "FleetSub", fontName="Helvetica", fontSize=8,
        textColor=SUB_C, alignment=TA_LEFT, spaceAfter=6
    )
    note_style = ParagraphStyle(
        "FleetNote", fontName="Helvetica-Oblique", fontSize=6.5,
        textColor=SUB_C, alignment=TA_LEFT, spaceAfter=0
    )

    story = []

    pages = [vehicles[0:6], vehicles[6:12], vehicles[12:18]]

    for i, page_vehicles in enumerate(pages):
        start = i * 6 + 1
        end   = start + len(page_vehicles) - 1

        story.append(Paragraph("MERIDIAN TRANSPORT CO.", title_style))
        story.append(Paragraph(
            "Fleet Insurance Schedule &nbsp;|&nbsp; Policy Period: 04/01/2026 – 04/01/2027 &nbsp;|&nbsp; "
            f"Units {start}–{end} of 18",
            sub_style
        ))

        tbl = make_table(page_vehicles)
        story.append(tbl)

        story.append(Spacer(1, 4))
        story.append(Paragraph(
            "Sched Val = Scheduled/Insured Value  |  Act Cost New = Actual Cost New  |  "
            "Comp = Comprehensive Deductible  |  Coll = Collision Deductible  |  TL = Total Loss  |  "
            "GVW = Gross Vehicle Weight  |  Radius in miles",
            note_style
        ))

        if i < 2:
            story.append(PageBreak())

    doc = SimpleDocTemplate(
        OUTPUT,
        pagesize=landscape(letter),
        leftMargin=MARGIN, rightMargin=MARGIN,
        topMargin=0.45 * inch, bottomMargin=0.45 * inch,
    )
    doc.build(story, canvasmaker=NumberedCanvas)
    print(f"Generated: {OUTPUT}")


if __name__ == "__main__":
    build()
