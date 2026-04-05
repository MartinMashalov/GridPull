"""
Generate retail_property_schedule_12_locations.pdf
Cascade Retail Group — Commercial Property Schedule
3-page landscape PDF, 4 locations per page, header repeated each page.
TIV = Bldg Val + BPP + BI + M&E
$/Sq Ft = Bldg Val / Sq Ft
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

OUTPUT = os.path.join(os.path.dirname(__file__), "retail_property_schedule_12_locations.pdf")

HDR_BG   = colors.HexColor("#2D5016")
HDR_FG   = colors.white
ROW_ALT  = colors.HexColor("#EEF4E8")
ROW_NORM = colors.white
BORDER   = colors.HexColor("#A8C882")
TITLE_C  = colors.HexColor("#2D5016")
SUB_C    = colors.HexColor("#4A5568")

PAGE_W, PAGE_H = landscape(letter)
MARGIN = 0.30 * inch


def fmt(n):
    return f"${n:,.0f}"

def pct(p):
    return f"{p}%"


# ── 12 locations ─────────────────────────────────────────────────────────────
# Raw data — TIV and $/SqFt computed below.
# Loc | Bldg | DBA | Class | Addr | City | ST | ZIP | Cnty | Const | ISO CC |
# Bldg Val | BPP | BI | M&E | TIV | Sq Ft | $/Sq Ft |
# Yr Blt | Rf Upd | Wir Upd | Pct Occ | Spkl | PPC | Sto | Rf Tp | Fld Zn | Owned

_raw = [
    # Loc  Bldg  DBA                         Class             Addr                          City         ST   ZIP     Cnty          Const    ISOCC  BldgV    BPP     BI      ME      SqFt  YrBlt RfUpd  WirUpd PctOcc Spkl PPC Sto RfTp   FldZn   Owned
    [1,  1, "Cascade Home & Living",       "Retail – Home Goods",  "1240 Westfield Blvd",       "Sacramento",  "CA","95815","Sacramento",    "Masonry", 4, 1_850_000, 620_000,290_000, 85_000, 22500, 2001, 2018, 2010, 100, "Y", 4, 2, "Flat",  "X",   "Owned"],
    [2,  1, "Cascade Electronics Outlet",  "Retail – Electronics", "8800 Pacific Ave, Ste 101", "Tacoma",      "WA","98444","Pierce",        "Steel",   5, 2_100_000, 980_000,440_000,120_000, 28000, 2008, 2019, 2008, 100, "Y", 3, 1, "Flat",  "X",   "Owned"],
    [3,  1, "Cascade Apparel Co.",         "Retail – Clothing",    "320 Main St",               "Boise",       "ID","83702","Ada",           "Frame",   1, 1_050_000, 380_000,195_000, 42_000, 14800, 1988, 2015, 2006,  95, "N", 5, 1, "Gable", "X",   "Managed"],
    [4,  1, "Cascade Sporting Goods",      "Retail – Sporting",    "4700 Commerce Dr",          "Las Vegas",   "NV","89103","Clark",         "Masonry", 4, 1_620_000, 740_000,310_000, 68_000, 19500, 1999, 2016, 2012, 100, "Y", 4, 1, "Flat",  "X",   "Owned"],

    [5,  1, "Cascade Kitchen & Bath",      "Retail – Home Goods",  "150 Industrial Pkwy",       "Tempe",       "AZ","85281","Maricopa",      "Steel",   5, 2_450_000, 820_000,395_000, 95_000, 31000, 2005, 2020, 2005, 100, "Y", 3, 1, "Flat",  "X",   "Owned"],
    [6,  1, "Cascade Furniture Gallery",   "Retail – Furniture",   "9001 North Fwy, Ste 400",   "Houston",     "TX","77037","Harris",        "Masonry", 4, 3_100_000,1_100_000,520_000,140_000, 38500, 2010, 2021, 2010, 100, "Y", 2, 1, "Flat",  "X",   "Owned"],
    [7,  1, "Cascade Outdoor Supply",      "Retail – Outdoor",     "2200 Mountain View Rd",     "Denver",      "CO","80210","Denver",        "Frame",   1,   980_000, 460_000,215_000, 55_000, 13200, 1992, 2014, 2009,  90, "N", 4, 2, "Gable", "X",   "Managed"],
    [8,  1, "Cascade Baby & Kids",         "Retail – Clothing",    "600 Riverfront Plz",        "Louisville",  "KY","40202","Jefferson",     "Masonry", 3,   870_000, 340_000,165_000, 32_000, 11500, 1979, 2012, 2011, 100, "Y", 5, 2, "Flat",  "AE",  "Managed"],

    [9,  1, "Cascade Auto Accessories",    "Retail – Auto",        "3355 Airport Rd",           "Charlotte",   "NC","28208","Mecklenburg",   "Steel",   5, 1_400_000, 610_000,280_000, 78_000, 18000, 2003, 2018, 2003, 100, "Y", 4, 1, "Flat",  "X",   "Owned"],
    [10, 1, "Cascade Pet Supply",          "Retail – Pet",         "7722 Broad Street Ext",     "Chattanooga", "TN","37421","Hamilton",      "Frame",   1,   760_000, 295_000,142_000, 28_000,  9800, 1986, 2013, 2008,  85, "N", 5, 1, "Hip",   "X",   "Managed"],
    [11, 1, "Cascade Office Depot",        "Retail – Office Sup.", "1800 Tech Campus Blvd",     "Austin",      "TX","78758","Travis",        "Steel",   5, 2_800_000, 950_000,430_000,115_000, 34000, 2012, 2022, 2012, 100, "Y", 3, 1, "Flat",  "X",   "Owned"],
    [12, 1, "Cascade Toy Warehouse",       "Retail – Toy/Hobby",   "400 Harbor Blvd",           "Portland",    "OR","97201","Multnomah",     "Masonry", 4, 1_250_000, 520_000,245_000, 58_000, 16000, 1995, 2017, 2015, 100, "Y", 3, 2, "Gable", "A",   "Managed"],
]

# Compute TIV and $/Sq Ft
locations = []
for r in _raw:
    loc, bldg, dba, cls, addr, city, st, zipc, cnty, const, isocc, bv, bpp, bi, me, sqft, yrblt, rfupd, wirupd, pctocc, spkl, ppc, sto, rftp, fldzn, owned = r
    tiv = bv + bpp + bi + me
    dpsf = round(bv / sqft, 2)
    locations.append([
        str(loc), str(bldg), dba, cls, addr, city, st, zipc, cnty, const, str(isocc),
        fmt(bv), fmt(bpp), fmt(bi), fmt(me), fmt(tiv),
        f"{sqft:,}", f"${dpsf:.2f}",
        str(yrblt), str(rfupd), str(wirupd), pct(pctocc), spkl,
        str(ppc), str(sto), rftp, fldzn, owned
    ])

HEADERS = [
    "Loc","Bldg","DBA","Class","Addr","City","ST","ZIP","Cnty",
    "Const","ISO CC",
    "Bldg Val","BPP","BI","M&E","TIV",
    "Sq Ft","$/Sq Ft",
    "Yr Blt","Rf Upd","Wir Upd","Pct Occ","Spkl","PPC","Sto","Rf Tp","Fld Zn","Owned"
]

# 28 columns  — landscape letter usable ≈ 756 pts (0.27" margins each side)
COL_WIDTHS = [
    18, 24, 90, 68, 100, 58, 16, 28, 52,   # Loc…Cnty
    46, 28,                                  # Const, ISO CC
    54, 48, 42, 42, 60,                      # Bldg Val…TIV
    36, 34,                                  # Sq Ft, $/Sq Ft
    24, 28, 30, 30, 20, 18, 18, 24, 28, 38  # Yr Blt…Owned
]
# sum ≈ 1036; scale to fit — we'll rely on the doc auto-flow but set wrapping


def make_table(data_rows):
    table_data = [HEADERS] + data_rows

    style = TableStyle([
        # header
        ("BACKGROUND",   (0, 0),  (-1, 0),  HDR_BG),
        ("TEXTCOLOR",    (0, 0),  (-1, 0),  HDR_FG),
        ("FONTNAME",     (0, 0),  (-1, 0),  "Helvetica-Bold"),
        ("FONTSIZE",     (0, 0),  (-1, 0),  5.5),
        ("ALIGN",        (0, 0),  (-1, 0),  "CENTER"),
        ("VALIGN",       (0, 0),  (-1, 0),  "MIDDLE"),
        ("TOPPADDING",   (0, 0),  (-1, 0),  4),
        ("BOTTOMPADDING",(0, 0),  (-1, 0),  4),
        ("WORDWRAP",     (0, 0),  (-1, 0),  "CJK"),
        # data
        ("FONTNAME",     (0, 1),  (-1, -1), "Helvetica"),
        ("FONTSIZE",     (0, 1),  (-1, -1), 5.2),
        ("VALIGN",       (0, 1),  (-1, -1), "MIDDLE"),
        ("TOPPADDING",   (0, 1),  (-1, -1), 3),
        ("BOTTOMPADDING",(0, 1),  (-1, -1), 3),
        # alt rows
        *[("BACKGROUND", (0, r), (-1, r), ROW_ALT if r % 2 == 0 else ROW_NORM)
          for r in range(1, len(table_data))],
        # grid
        ("GRID",         (0, 0),  (-1, -1), 0.35, BORDER),
        ("LINEBELOW",    (0, 0),  (-1, 0),  1.0,  HDR_BG),
        # right-align money columns (Bldg Val=11 … TIV=15, $/Sq Ft=17)
        ("ALIGN",        (11, 1), (15, -1), "RIGHT"),
        ("ALIGN",        (17, 1), (17, -1), "RIGHT"),
        # center: Loc, Bldg, ST, ZIP, ISO CC, Spkl, PPC, Sto, Rf Tp, Fld Zn, Owned, Yr Blt, Rf Upd, Wir Upd, Pct Occ
        ("ALIGN",        (0,  1), (1,  -1), "CENTER"),
        ("ALIGN",        (6,  1), (7,  -1), "CENTER"),
        ("ALIGN",        (10, 1), (10, -1), "CENTER"),
        ("ALIGN",        (18, 1), (27, -1), "CENTER"),
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
        self.setFont("Helvetica", 6.5)
        self.setFillColor(SUB_C)
        txt = (f"Page {self._pageNumber} of {page_count}  |  "
               "Cascade Retail Group — Property Schedule  |  Confidential & Proprietary")
        self.drawCentredString(PAGE_W / 2, 0.22 * inch, txt)


def build():
    title_style = ParagraphStyle(
        "Title", fontName="Helvetica-Bold", fontSize=13,
        textColor=TITLE_C, alignment=TA_LEFT, spaceAfter=2
    )
    sub_style = ParagraphStyle(
        "Sub", fontName="Helvetica", fontSize=7.5,
        textColor=SUB_C, alignment=TA_LEFT, spaceAfter=5
    )
    note_style = ParagraphStyle(
        "Note", fontName="Helvetica-Oblique", fontSize=5.8,
        textColor=SUB_C, alignment=TA_LEFT
    )

    story = []
    pages_data = [locations[0:4], locations[4:8], locations[8:12]]

    for i, page_locs in enumerate(pages_data):
        start = i * 4 + 1
        end   = start + len(page_locs) - 1

        story.append(Paragraph("CASCADE RETAIL GROUP", title_style))
        story.append(Paragraph(
            "Commercial Property Insurance Schedule &nbsp;|&nbsp; "
            "Policy Period: 07/01/2026 – 07/01/2027 &nbsp;|&nbsp; "
            f"Locations {start}–{end} of 12",
            sub_style
        ))

        story.append(make_table(page_locs))

        story.append(Spacer(1, 4))
        story.append(Paragraph(
            "TIV = Bldg Val + BPP + BI + M&amp;E  |  BPP = Business Personal Property  |  "
            "BI = Business Income  |  M&amp;E = Machinery &amp; Equipment  |  "
            "$/Sq Ft = Building Value ÷ Square Footage  |  "
            "Const: 1=Frame, 3=Masonry, 5=Steel  |  PPC = ISO Protection Class",
            note_style
        ))

        if i < 2:
            story.append(PageBreak())

    doc = SimpleDocTemplate(
        OUTPUT,
        pagesize=landscape(letter),
        leftMargin=MARGIN, rightMargin=MARGIN,
        topMargin=0.40 * inch, bottomMargin=0.40 * inch,
    )
    doc.build(story, canvasmaker=NumberedCanvas)
    print(f"Generated: {OUTPUT}")


if __name__ == "__main__":
    build()
