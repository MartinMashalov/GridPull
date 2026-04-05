"""
generate_sov_samples.py
-----------------------
Generates three sample insurance SOV / property schedule PDF files
for use as test documents in the GridPull SOV email workflow test suite.

Requirements: reportlab
    pip install reportlab

Output files (same directory as this script):
    sov_acme_manufacturing_15_locations.pdf
    sov_westfield_retail_8_locations.pdf
    vehicle_schedule_abc_logistics_22_vehicles.pdf
"""

import os
from datetime import date

from reportlab.lib import colors
from reportlab.lib.pagesizes import letter, landscape
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.platypus import (
    SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer,
    HRFlowable, PageBreak
)
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))

HEADER_BG   = colors.HexColor("#1a3a5c")   # dark navy
SUBHEAD_BG  = colors.HexColor("#2e6da4")   # medium blue
ALT_ROW     = colors.HexColor("#eef4fb")   # light blue-grey
WHITE       = colors.white
BLACK       = colors.black
LIGHT_GREY  = colors.HexColor("#f5f5f5")
BORDER      = colors.HexColor("#c0c8d4")

def currency(n):
    return "${:,.0f}".format(n)

def make_styles():
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        "SOVTitle",
        parent=styles["Title"],
        fontSize=16,
        textColor=HEADER_BG,
        spaceAfter=4,
    )
    subtitle_style = ParagraphStyle(
        "SOVSubtitle",
        parent=styles["Normal"],
        fontSize=10,
        textColor=colors.HexColor("#444444"),
        spaceAfter=2,
    )
    meta_style = ParagraphStyle(
        "SOVMeta",
        parent=styles["Normal"],
        fontSize=8.5,
        textColor=colors.HexColor("#555555"),
        spaceAfter=1,
    )
    footer_style = ParagraphStyle(
        "SOVFooter",
        parent=styles["Normal"],
        fontSize=7,
        textColor=colors.HexColor("#888888"),
        alignment=TA_CENTER,
    )
    return styles, title_style, subtitle_style, meta_style, footer_style

def base_table_style(col_count):
    return TableStyle([
        # Header row
        ("BACKGROUND",   (0, 0), (-1, 0), HEADER_BG),
        ("TEXTCOLOR",    (0, 0), (-1, 0), WHITE),
        ("FONTNAME",     (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE",     (0, 0), (-1, 0), 7.5),
        ("ALIGN",        (0, 0), (-1, 0), "CENTER"),
        ("VALIGN",       (0, 0), (-1, 0), "MIDDLE"),
        ("BOTTOMPADDING",(0, 0), (-1, 0), 5),
        ("TOPPADDING",   (0, 0), (-1, 0), 5),
        # Data rows
        ("FONTNAME",     (0, 1), (-1, -1), "Helvetica"),
        ("FONTSIZE",     (0, 1), (-1, -1), 7),
        ("VALIGN",       (0, 1), (-1, -1), "MIDDLE"),
        ("TOPPADDING",   (0, 1), (-1, -1), 3),
        ("BOTTOMPADDING",(0, 1), (-1, -1), 3),
        # Grid
        ("GRID",         (0, 0), (-1, -1), 0.4, BORDER),
        ("LINEBELOW",    (0, 0), (-1, 0), 1.0, SUBHEAD_BG),
    ])

def add_alternating_rows(style, data_row_count):
    for i in range(1, data_row_count + 1):
        if i % 2 == 0:
            style.add("BACKGROUND", (0, i), (-1, i), ALT_ROW)
    return style

def add_page_number(canvas, doc):
    canvas.saveState()
    canvas.setFont("Helvetica", 7)
    canvas.setFillColor(colors.HexColor("#888888"))
    canvas.drawRightString(
        doc.pagesize[0] - 0.5 * inch,
        0.4 * inch,
        f"Page {canvas.getPageNumber()}"
    )
    canvas.drawString(
        0.5 * inch,
        0.4 * inch,
        "CONFIDENTIAL — FOR UNDERWRITING USE ONLY"
    )
    canvas.restoreState()

# ---------------------------------------------------------------------------
# PDF 1: Acme Manufacturing — 15 locations
# ---------------------------------------------------------------------------

def build_acme_manufacturing():
    out_path = os.path.join(SCRIPT_DIR, "sov_acme_manufacturing_15_locations.pdf")
    doc = SimpleDocTemplate(
        out_path,
        pagesize=landscape(letter),
        leftMargin=0.55 * inch,
        rightMargin=0.55 * inch,
        topMargin=0.65 * inch,
        bottomMargin=0.65 * inch,
    )

    styles, title_s, sub_s, meta_s, footer_s = make_styles()
    story = []

    # Header block
    story.append(Paragraph("STATEMENT OF VALUES", title_s))
    story.append(Paragraph("Acme Manufacturing Group", sub_s))
    story.append(Paragraph(
        "Policy #: PCM-2021-00447 &nbsp;&nbsp;|&nbsp;&nbsp; "
        "Effective: 04/01/2024 – 04/01/2025 &nbsp;&nbsp;|&nbsp;&nbsp; "
        "Prepared by: Meridian Risk Partners &nbsp;&nbsp;|&nbsp;&nbsp; "
        "Prepared: March 11, 2024",
        meta_s
    ))
    story.append(HRFlowable(width="100%", thickness=1.5, color=SUBHEAD_BG, spaceAfter=8))

    # Location data
    # Columns: Loc #, Address, City, State, Zip, Occupancy, Const Type,
    #          Yr Built, Sq Ft, Sprinkler, Bldg Value, Contents Value, TIV
    headers = [
        "Loc\n#", "Street Address", "City", "ST", "ZIP",
        "Occupancy", "Construction\nType", "Yr\nBuilt", "Sq Ft",
        "Spk", "Building\nValue", "Contents\nValue", "TIV"
    ]

    rows = [
        [1,  "1100 Industrial Pkwy",         "Rockford",         "IL", "61101", "Manufacturing",     "Joisted Masonry",   1978, "138,400", "Y", "$3,850,000", "$1,200,000", "$5,050,000"],
        [2,  "4800 Commerce Drive",           "Gary",             "IN", "46406", "Manufacturing",     "Steel Frame",       1991, "95,200",  "Y", "$2,980,000", "$850,000",   "$3,830,000"],
        [3,  "2200 Production Blvd",          "Peoria",           "IL", "61602", "Warehouse",         "Masonry",           1965, "74,000",  "N", "$1,740,000", "$620,000",   "$2,360,000"],
        [4,  "780 Lakeview Industrial Rd",    "Waukegan",         "IL", "60085", "Manufacturing",     "Steel Frame",       2003, "112,500", "Y", "$4,100,000", "$1,400,000", "$5,500,000"],
        [5,  "9301 East River Road",          "Davenport",        "IA", "52802", "Distribution",      "Steel Frame",       2008, "88,000",  "Y", "$2,600,000", "$750,000",   "$3,350,000"],
        [6,  "500 S. Halsted Street",         "Chicago",          "IL", "60607", "Office/Admin",      "Fire Resistive",    1988, "42,000",  "Y", "$3,200,000", "$400,000",   "$3,600,000"],
        [7,  "3120 Blue Island Ave",          "Joliet",           "IL", "60432", "Manufacturing",     "Joisted Masonry",   1972, "67,800",  "N", "$1,920,000", "$580,000",   "$2,500,000"],
        [8,  "7700 Enterprise Drive",         "Madison",          "WI", "53719", "Warehouse",         "Steel Frame",       2011, "54,000",  "Y", "$1,650,000", "$490,000",   "$2,140,000"],
        [9,  "12 Northgate Industrial Blvd",  "Green Bay",        "WI", "54302", "Manufacturing",     "Masonry",           1960, "81,200",  "N", "$2,050,000", "$710,000",   "$2,760,000"],
        [10, "4400 Metro Commerce Park",      "Indianapolis",     "IN", "46235", "Warehouse/Storage", "Steel Frame",       1999, "120,000", "Y", "$2,450,000", "$900,000",   "$3,350,000"],
        [11, "900 S. Meridian St.",           "Muncie",           "IN", "47302", "Manufacturing",     "Joisted Masonry",   1955, "59,600",  "N", "$1,580,000", "$430,000",   "$2,010,000"],
        [12, "2600 River Bend Road",          "Cedar Rapids",     "IA", "52404", "Distribution",      "Steel Frame",       2015, "76,000",  "Y", "$2,820,000", "$680,000",   "$3,500,000"],
        [13, "850 Technology Drive",          "Champaign",        "IL", "61822", "R&D / Lab",         "Fire Resistive",    2017, "38,000",  "Y", "$4,500,000", "$2,200,000", "$6,700,000"],
        [14, "1450 Pelham Rd",               "Spartanburg",      "SC", "29303", "Manufacturing",     "Steel Frame",       2023, "42,000",  "Y", "$5,200,000", "$1,800,000", "$7,000,000"],
        [15, "310 Warehouse Way",             "Decatur",          "IL", "62521", "Warehouse",         "Frame",             1948, "31,500",  "N", "$680,000",   "$210,000",   "$890,000"],
    ]

    # Build totals
    def strip_dollar(s):
        return int(s.replace("$","").replace(",",""))

    total_bldg = sum(strip_dollar(r[10]) for r in rows)
    total_cont = sum(strip_dollar(r[11]) for r in rows)
    total_tiv  = sum(strip_dollar(r[12]) for r in rows)

    table_data = [headers]
    for r in rows:
        table_data.append([str(x) for x in r])
    table_data.append([
        "TOTAL", "", "", "", "", "", "", "", "", "",
        currency(total_bldg), currency(total_cont), currency(total_tiv)
    ])

    col_widths = [0.35, 1.65, 0.95, 0.28, 0.45, 1.0, 1.1, 0.4, 0.58, 0.3, 0.82, 0.82, 0.82]
    col_widths = [w * inch for w in col_widths]

    tbl = Table(table_data, colWidths=col_widths, repeatRows=1)
    ts = base_table_style(len(headers))
    ts = add_alternating_rows(ts, len(rows))

    # Totals row
    ts.add("BACKGROUND",  (0, len(table_data)-1), (-1, len(table_data)-1), HEADER_BG)
    ts.add("TEXTCOLOR",   (0, len(table_data)-1), (-1, len(table_data)-1), WHITE)
    ts.add("FONTNAME",    (0, len(table_data)-1), (-1, len(table_data)-1), "Helvetica-Bold")
    ts.add("FONTSIZE",    (0, len(table_data)-1), (-1, len(table_data)-1), 7.5)
    ts.add("SPAN",        (0, len(table_data)-1), (9, len(table_data)-1))
    ts.add("ALIGN",       (0, len(table_data)-1), (9, len(table_data)-1), "RIGHT")

    # Right-align numeric columns
    for col in [8, 10, 11, 12]:
        ts.add("ALIGN", (col, 1), (col, len(table_data)-1), "RIGHT")

    ts.add("ALIGN", (0, 1), (0, -1), "CENTER")  # Loc #
    ts.add("ALIGN", (3, 1), (3, -1), "CENTER")  # ST
    ts.add("ALIGN", (9, 1), (9, -1), "CENTER")  # Spk

    tbl.setStyle(ts)
    story.append(tbl)
    story.append(Spacer(1, 0.15 * inch))

    # Summary box
    summary_data = [
        ["SCHEDULE SUMMARY", "", ""],
        ["Total Locations:", "15", ""],
        ["Total Building Value:", currency(total_bldg), ""],
        ["Total Contents Value:", currency(total_cont), ""],
        ["Total Insured Value (TIV):", currency(total_tiv), ""],
        ["Coverage Form:", "Special Form (Open Perils)", ""],
        ["Valuation Basis:", "Replacement Cost", ""],
        ["AOP Deductible:", "$250,000 per occurrence", ""],
        ["Wind/Hail Deductible:", "$500,000 per occurrence", ""],
    ]
    summary_tbl = Table(summary_data, colWidths=[2.0*inch, 1.8*inch, 4.0*inch])
    sts = TableStyle([
        ("BACKGROUND",   (0, 0), (-1, 0), SUBHEAD_BG),
        ("TEXTCOLOR",    (0, 0), (-1, 0), WHITE),
        ("FONTNAME",     (0, 0), (-1, 0), "Helvetica-Bold"),
        ("SPAN",         (0, 0), (-1, 0)),
        ("FONTSIZE",     (0, 0), (-1, 0), 8),
        ("FONTNAME",     (0, 1), (0, -1), "Helvetica-Bold"),
        ("FONTSIZE",     (0, 1), (-1, -1), 8),
        ("FONTNAME",     (1, 1), (1, -1), "Helvetica"),
        ("GRID",         (0, 0), (1, -1), 0.4, BORDER),
        ("BACKGROUND",   (0, 1), (1, -1), LIGHT_GREY),
        ("TOPPADDING",   (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING",(0, 0), (-1, -1), 3),
    ])
    summary_tbl.setStyle(sts)
    story.append(summary_tbl)

    story.append(Spacer(1, 0.1 * inch))
    story.append(Paragraph(
        "This Statement of Values is prepared for underwriting purposes only. Values represent replacement cost estimates "
        "based on insured-provided data and internal appraisals. All information is subject to verification. "
        "Broker: Meridian Risk Partners | Underwriter: Pinnacle Commercial Insurance",
        footer_s
    ))

    doc.build(story, onFirstPage=add_page_number, onLaterPages=add_page_number)
    print(f"  Created: {out_path}")


# ---------------------------------------------------------------------------
# PDF 2: Westfield Retail — 8 locations
# ---------------------------------------------------------------------------

def build_westfield_retail():
    out_path = os.path.join(SCRIPT_DIR, "sov_westfield_retail_8_locations.pdf")
    doc = SimpleDocTemplate(
        out_path,
        pagesize=landscape(letter),
        leftMargin=0.55 * inch,
        rightMargin=0.55 * inch,
        topMargin=0.65 * inch,
        bottomMargin=0.65 * inch,
    )

    styles, title_s, sub_s, meta_s, footer_s = make_styles()
    story = []

    story.append(Paragraph("COMMERCIAL PROPERTY SCHEDULE", title_s))
    story.append(Paragraph("Westfield Retail Properties LLC", sub_s))
    story.append(Paragraph(
        "Policy Effective: 05/01/2024 – 05/01/2025 &nbsp;&nbsp;|&nbsp;&nbsp; "
        "NEW ACCOUNT &nbsp;&nbsp;|&nbsp;&nbsp; "
        "Broker: Summit Insurance Group &nbsp;&nbsp;|&nbsp;&nbsp; "
        "Submission Date: March 7, 2024",
        meta_s
    ))
    story.append(HRFlowable(width="100%", thickness=1.5, color=SUBHEAD_BG, spaceAfter=8))

    headers = [
        "Loc\n#", "Property Name", "Street Address", "City", "ST", "ZIP",
        "Const\nType", "Yr\nBuilt", "Stories", "Sq Ft",
        "Sprinkler", "Anchor\nTenant", "Building\nValue", "BPP\nValue",
        "Biz Income\nLimit", "TIV"
    ]

    rows = [
        [1,  "Westfield Plaza – Downers Grove",  "3300 Commerce Park Dr",    "Downers Grove", "IL", "60515", "Masonry",         1998, 1, "68,000", "Wet Pipe", "Jewel-Osco",    "$6,200,000", "$420,000", "$1,800,000", "$8,420,000"],
        [2,  "Westfield Center – Naperville",     "1020 Ogden Ave",           "Naperville",    "IL", "60563", "Steel Frame",     2005, 1, "52,400", "Wet Pipe", "CVS Pharmacy",  "$4,800,000", "$310,000", "$1,200,000", "$6,310,000"],
        [3,  "Westfield Square – Schaumburg",     "700 W. Golf Rd",           "Schaumburg",    "IL", "60194", "Masonry",         1989, 1, "41,200", "Wet Pipe", "Mariano's",     "$3,650,000", "$290,000", "$950,000",   "$4,890,000"],
        [4,  "Westfield Crossing – Oakbrook",     "2100 S. York Rd",          "Oakbrook",      "IL", "60523", "Masonry",         1994, 1, "38,000", "Wet Pipe", "VACANT (37%)",  "$4,200,000", "$180,000", "$800,000",   "$5,180,000"],
        [5,  "Westfield Marketplace – Brookfield","15800 W. Bluemound Rd",    "Brookfield",    "WI", "53005", "Steel Frame",     2010, 1, "72,000", "Wet Pipe", "Pick 'n Save",  "$6,800,000", "$510,000", "$2,100,000", "$9,410,000"],
        [6,  "Westfield Village – Kenosha",       "4500 75th Street",         "Kenosha",       "WI", "53142", "Masonry",         1979, 1, "28,500", "Dry Pipe", "Dollar General","$2,100,000", "$195,000", "$540,000",   "$2,835,000"],
        [7,  "Westfield Commons – Merrillville",  "600 E. Lincoln Hwy",       "Merrillville",  "IN", "46410", "Masonry",         2001, 1, "33,800", "Wet Pipe", "Walgreens",     "$2,950,000", "$240,000", "$720,000",   "$3,910,000"],
        [8,  "Westfield Point – Hammond",         "7200 Indianapolis Blvd",   "Hammond",       "IN", "46324", "Joisted Masonry", 1968, 1, "24,100", "None",     "Family Dollar", "$1,580,000", "$160,000", "$420,000",   "$2,160,000"],
    ]

    def strip_dollar(s):
        return int(s.replace("$","").replace(",",""))

    total_bldg = sum(strip_dollar(r[12]) for r in rows)
    total_bpp  = sum(strip_dollar(r[13]) for r in rows)
    total_bi   = sum(strip_dollar(r[14]) for r in rows)
    total_tiv  = sum(strip_dollar(r[15]) for r in rows)

    table_data = [headers]
    for r in rows:
        table_data.append([str(x) for x in r])
    table_data.append([
        "TOTAL", "", "", "", "", "", "", "", "", "", "", "",
        currency(total_bldg), currency(total_bpp), currency(total_bi), currency(total_tiv)
    ])

    col_widths = [0.30, 1.65, 1.40, 0.95, 0.28, 0.42, 0.88, 0.38, 0.45, 0.55,
                  0.62, 0.82, 0.75, 0.60, 0.80, 0.78]
    col_widths = [w * inch for w in col_widths]

    tbl = Table(table_data, colWidths=col_widths, repeatRows=1)
    ts = base_table_style(len(headers))
    ts = add_alternating_rows(ts, len(rows))

    last = len(table_data) - 1
    ts.add("BACKGROUND",  (0, last), (-1, last), HEADER_BG)
    ts.add("TEXTCOLOR",   (0, last), (-1, last), WHITE)
    ts.add("FONTNAME",    (0, last), (-1, last), "Helvetica-Bold")
    ts.add("FONTSIZE",    (0, last), (-1, last), 7.5)
    ts.add("SPAN",        (0, last), (11, last))
    ts.add("ALIGN",       (0, last), (11, last), "RIGHT")

    for col in [9, 12, 13, 14, 15]:
        ts.add("ALIGN", (col, 1), (col, last), "RIGHT")
    ts.add("ALIGN", (0, 1), (0, -1), "CENTER")
    ts.add("ALIGN", (4, 1), (4, -1), "CENTER")
    ts.add("ALIGN", (7, 1), (8, -1), "CENTER")

    tbl.setStyle(ts)
    story.append(tbl)
    story.append(Spacer(1, 0.15 * inch))

    # Summary
    summary_data = [
        ["SCHEDULE SUMMARY", "", "NOTES", ""],
        ["Total Locations:", "8", "Loc 4 (Oakbrook): 37% vacant — vacancy permit may apply", ""],
        ["Total Building Value:", currency(total_bldg), "Loc 8 (Hammond): No sprinkler — confirm habitancy", ""],
        ["Total BPP Value:", currency(total_bpp), "Loc 6 (Kenosha): Dry pipe — verify maintenance records", ""],
        ["Total Biz Income Limit:", currency(total_bi), "", ""],
        ["Total Insured Value (TIV):", currency(total_tiv), "Blanket limit requested: $35,000,000", ""],
        ["Coverage Form:", "Special Form — RC Basis", "AOP Deductible: $50,000", ""],
        ["Named Storm Deductible:", "$100,000", "BI Extended Period: 18 months ALS", ""],
    ]
    summary_tbl = Table(summary_data, colWidths=[1.9*inch, 1.7*inch, 3.5*inch, 0.5*inch])
    sts = TableStyle([
        ("BACKGROUND",   (0, 0), (-1, 0), SUBHEAD_BG),
        ("TEXTCOLOR",    (0, 0), (-1, 0), WHITE),
        ("FONTNAME",     (0, 0), (-1, 0), "Helvetica-Bold"),
        ("SPAN",         (0, 0), (1, 0)),
        ("SPAN",         (2, 0), (3, 0)),
        ("FONTSIZE",     (0, 0), (-1, 0), 8),
        ("FONTNAME",     (0, 1), (0, -1), "Helvetica-Bold"),
        ("FONTNAME",     (2, 0), (2, 0), "Helvetica-Bold"),
        ("FONTSIZE",     (0, 1), (-1, -1), 8),
        ("GRID",         (0, 0), (1, -1), 0.4, BORDER),
        ("GRID",         (2, 0), (3, -1), 0.4, BORDER),
        ("BACKGROUND",   (0, 1), (1, -1), LIGHT_GREY),
        ("BACKGROUND",   (2, 1), (3, -1), colors.HexColor("#fffbf0")),
        ("TOPPADDING",   (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING",(0, 0), (-1, -1), 3),
    ])
    summary_tbl.setStyle(sts)
    story.append(summary_tbl)

    story.append(Spacer(1, 0.1 * inch))
    story.append(Paragraph(
        "This Property Schedule is submitted for underwriting review on a NEW ACCOUNT basis. "
        "Prior carrier: Hartfield Mutual (non-renewed — carrier exit from retail segment, not loss-related). "
        "Broker: Summit Insurance Group | Underwriter: Pinnacle Commercial Insurance",
        footer_s
    ))

    doc.build(story, onFirstPage=add_page_number, onLaterPages=add_page_number)
    print(f"  Created: {out_path}")


# ---------------------------------------------------------------------------
# PDF 3: ABC Logistics — 22 vehicles
# ---------------------------------------------------------------------------

def build_abc_logistics_vehicles():
    out_path = os.path.join(SCRIPT_DIR, "vehicle_schedule_abc_logistics_22_vehicles.pdf")
    doc = SimpleDocTemplate(
        out_path,
        pagesize=landscape(letter),
        leftMargin=0.50 * inch,
        rightMargin=0.50 * inch,
        topMargin=0.65 * inch,
        bottomMargin=0.65 * inch,
    )

    styles, title_s, sub_s, meta_s, footer_s = make_styles()
    story = []

    story.append(Paragraph("COMMERCIAL VEHICLE SCHEDULE", title_s))
    story.append(Paragraph("ABC Logistics & Transport Inc.", sub_s))
    story.append(Paragraph(
        "Policy #: PCA-2020-00882 &nbsp;&nbsp;|&nbsp;&nbsp; "
        "Renewal Effective: 04/01/2024 – 04/01/2025 &nbsp;&nbsp;|&nbsp;&nbsp; "
        "Broker: Coastal Insurance Advisors &nbsp;&nbsp;|&nbsp;&nbsp; "
        "As of: March 1, 2024",
        meta_s
    ))
    story.append(HRFlowable(width="100%", thickness=1.5, color=SUBHEAD_BG, spaceAfter=8))

    headers = [
        "Unit\n#", "Year", "Make", "Model", "Body\nType",
        "VIN", "GVW\n(lbs)", "Garaging\nLocation",
        "Comp\nDed", "Coll\nDed", "Stated\nValue", "Cargo\nCoverage"
    ]

    rows = [
        # Unit#, Year, Make, Model, Body, VIN, GVW, Garage, CompDed, CollDed, Value, Cargo
        [1,  2022, "Kenworth",    "T680",       "Tractor (Sleeper)", "1XKWDB9X8NJ318204", "80,000", "Memphis, TN 38118",     "$1,000", "$2,500", "$172,000", "Yes"],
        [2,  2022, "Kenworth",    "T680",       "Tractor (Sleeper)", "1XKWDB9X0NJ318205", "80,000", "Memphis, TN 38118",     "$1,000", "$2,500", "$172,000", "Yes"],
        [3,  2021, "Peterbilt",   "579",        "Tractor (Sleeper)", "1XPBD49X9MD621477", "80,000", "Memphis, TN 38118",     "$1,000", "$2,500", "$165,000", "Yes"],
        [4,  2021, "Peterbilt",   "579",        "Tractor (Sleeper)", "1XPBD49X1MD621478", "80,000", "Nashville, TN 37209",   "$1,000", "$2,500", "$165,000", "Yes"],
        [5,  2020, "Freightliner","Cascadia 126","Tractor (Sleeper)", "3AKJGLD57LSLS8829", "80,000", "Memphis, TN 38118",     "$1,000", "$2,500", "$148,000", "Yes"],
        [6,  2020, "Freightliner","Cascadia 126","Tractor (Sleeper)", "3AKJGLD59LSLS8830", "80,000", "Nashville, TN 37209",   "$1,000", "$2,500", "$148,000", "Yes"],
        [7,  2019, "Volvo",       "VNL 760",    "Tractor (Sleeper)", "4V4NC9EJXKN203314", "80,000", "Birmingham, AL 35208",  "$1,000", "$2,500", "$132,000", "Yes"],
        [8,  2019, "Volvo",       "VNL 760",    "Tractor (Sleeper)", "4V4NC9EJ0KN203315", "80,000", "Birmingham, AL 35208",  "$1,000", "$2,500", "$132,000", "Yes"],
        [9,  2018, "Kenworth",    "T680",       "Tractor (Day Cab)", "1XKWDB9X4JJ313892", "80,000", "Atlanta, GA 30318",     "$1,000", "$2,500", "$115,000", "Yes"],
        [10, 2018, "Peterbilt",   "389",        "Tractor (Sleeper)", "1XPXD49X8JD448802", "80,000", "Atlanta, GA 30318",     "$1,000", "$2,500", "$118,000", "Yes"],
        [11, 2017, "Freightliner","Cascadia 125","Tractor (Sleeper)", "3AKJGLD56HSHS9120", "80,000", "Memphis, TN 38118",     "$1,000", "$2,500", "$98,000",  "Yes"],
        [12, 2023, "Wabash Natl", "53' Dry Van","Dry Van Trailer",   "1JJV532D5PL887012", "N/A",    "Memphis, TN 38118",     "$1,000", "$2,500", "$54,000",  "TI"],
        [13, 2023, "Wabash Natl", "53' Dry Van","Dry Van Trailer",   "1JJV532D7PL887013", "N/A",    "Memphis, TN 38118",     "$1,000", "$2,500", "$54,000",  "TI"],
        [14, 2022, "Great Dane",  "53' Dry Van","Dry Van Trailer",   "1GRAA6629NB107441", "N/A",    "Nashville, TN 37209",   "$1,000", "$2,500", "$48,000",  "TI"],
        [15, 2022, "Great Dane",  "53' Dry Van","Dry Van Trailer",   "1GRAA6621NB107442", "N/A",    "Nashville, TN 37209",   "$1,000", "$2,500", "$48,000",  "TI"],
        [16, 2021, "Utility",     "3000R",      "Dry Van Trailer",   "1UYVS2532ML341802", "N/A",    "Birmingham, AL 35208",  "$1,000", "$2,500", "$44,000",  "TI"],
        [17, 2021, "Utility",     "3000R",      "Dry Van Trailer",   "1UYVS2534ML341803", "N/A",    "Birmingham, AL 35208",  "$1,000", "$2,500", "$44,000",  "TI"],
        [18, 2020, "Wabash Natl", "53' Dry Van","Dry Van Trailer",   "1JJV532D8LL854209", "N/A",    "Atlanta, GA 30318",     "$1,000", "$2,500", "$39,000",  "TI"],
        [19, 2019, "Great Dane",  "53' Dry Van","Dry Van Trailer",   "1GRAA6628KN098331", "N/A",    "Atlanta, GA 30318",     "$1,000", "$2,500", "$35,000",  "TI"],
        [20, 2022, "Dorsey",      "48' Flatbed","Flatbed Trailer",   "1DTA4820XN1049882", "N/A",    "Memphis, TN 38118",     "$1,000", "$2,500", "$32,000",  "TI"],
        [21, 2020, "Dorsey",      "48' Flatbed","Flatbed Trailer",   "1DTA4820XL1041290", "N/A",    "Memphis, TN 38118",     "$1,000", "$2,500", "$26,000",  "TI"],
        [22, 2021, "Ford",        "F-250 XLT",  "Pickup Truck",      "1FT7W2BT4MEC48801", "10,000", "Memphis, TN 38118 (HQ)","$1,000", "$2,500", "$38,000",  "No"],
    ]

    def strip_dollar(s):
        return int(s.replace("$","").replace(",",""))

    total_value = sum(strip_dollar(r[10]) for r in rows)

    table_data = [headers]
    for r in rows:
        table_data.append([str(x) for x in r])
    table_data.append([
        "TOTAL", "", "", "", "", "", "", "",
        "", "", currency(total_value), ""
    ])

    col_widths = [0.33, 0.38, 0.85, 0.82, 1.00, 1.40, 0.52, 1.30, 0.45, 0.45, 0.72, 0.62]
    col_widths = [w * inch for w in col_widths]

    tbl = Table(table_data, colWidths=col_widths, repeatRows=1)
    ts = base_table_style(len(headers))
    ts = add_alternating_rows(ts, len(rows))

    last = len(table_data) - 1
    ts.add("BACKGROUND",  (0, last), (-1, last), HEADER_BG)
    ts.add("TEXTCOLOR",   (0, last), (-1, last), WHITE)
    ts.add("FONTNAME",    (0, last), (-1, last), "Helvetica-Bold")
    ts.add("FONTSIZE",    (0, last), (-1, last), 7.5)
    ts.add("SPAN",        (0, last), (9, last))
    ts.add("ALIGN",       (0, last), (9, last), "RIGHT")
    ts.add("ALIGN",       (10, last), (10, last), "RIGHT")

    for col in [6, 10]:
        ts.add("ALIGN", (col, 1), (col, last), "RIGHT")
    ts.add("ALIGN", (0, 1), (0, -1), "CENTER")
    ts.add("ALIGN", (1, 1), (1, -1), "CENTER")
    ts.add("ALIGN", (11, 1), (11, -1), "CENTER")

    tbl.setStyle(ts)
    story.append(tbl)
    story.append(Spacer(1, 0.12 * inch))

    # Summary by vehicle type
    tractors    = [r for r in rows if "Tractor" in str(r[4])]
    dry_vans    = [r for r in rows if "Dry Van Trailer" in str(r[4])]
    flatbeds    = [r for r in rows if "Flatbed" in str(r[4])]
    pickups     = [r for r in rows if "Pickup" in str(r[4])]

    def tiv_group(group):
        return sum(strip_dollar(r[10]) for r in group)

    summary_data = [
        ["FLEET SUMMARY BY TYPE", "", "", "COVERAGE SUMMARY", ""],
        ["Vehicle Type", "Count", "Stated Value", "Coverage", "Limit / Deductible"],
        ["Tractors / Semi-Trucks", str(len(tractors)), currency(tiv_group(tractors)),
         "Liability (CSL)", "$1,000,000"],
        ["53' Dry Van Trailers", str(len(dry_vans)), currency(tiv_group(dry_vans)),
         "UM/UIM", "$1,000,000"],
        ["Flatbed Trailers", str(len(flatbeds)), currency(tiv_group(flatbeds)),
         "Medical Payments", "$5,000 per person"],
        ["Company Pickup", str(len(pickups)), currency(tiv_group(pickups)),
         "Comprehensive", "$1,000 deductible"],
        ["TOTAL", str(len(rows)), currency(total_value),
         "Collision", "$2,500 deductible"],
        ["", "", "",
         "Cargo", "$100,000 occ / $500,000 policy"],
        ["", "", "",
         "Trailer Interchange", "$100,000 blanket"],
    ]

    summary_tbl = Table(summary_data, colWidths=[1.75*inch, 0.55*inch, 1.1*inch, 1.6*inch, 1.8*inch])
    sts = TableStyle([
        ("BACKGROUND",   (0, 0), (2, 0), SUBHEAD_BG),
        ("BACKGROUND",   (3, 0), (4, 0), SUBHEAD_BG),
        ("TEXTCOLOR",    (0, 0), (-1, 0), WHITE),
        ("FONTNAME",     (0, 0), (-1, 0), "Helvetica-Bold"),
        ("SPAN",         (0, 0), (2, 0)),
        ("SPAN",         (3, 0), (4, 0)),
        ("BACKGROUND",   (0, 1), (2, 1), HEADER_BG),
        ("BACKGROUND",   (3, 1), (4, 1), HEADER_BG),
        ("TEXTCOLOR",    (0, 1), (-1, 1), WHITE),
        ("FONTNAME",     (0, 1), (-1, 1), "Helvetica-Bold"),
        ("FONTSIZE",     (0, 0), (-1, 1), 8),
        ("FONTSIZE",     (0, 2), (-1, -1), 8),
        ("BACKGROUND",   (0, 2), (2, -1), LIGHT_GREY),
        ("BACKGROUND",   (3, 2), (4, -1), colors.HexColor("#fffbf0")),
        ("FONTNAME",     (0, len(rows)+2-len(rows)), (2, len(rows)+2-len(rows)), "Helvetica-Bold"),
        ("GRID",         (0, 0), (2, -1), 0.4, BORDER),
        ("GRID",         (3, 0), (4, -1), 0.4, BORDER),
        ("TOPPADDING",   (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING",(0, 0), (-1, -1), 3),
        ("ALIGN",        (1, 2), (2, -1), "RIGHT"),
        ("FONTNAME",     (0, 6), (2, 6), "Helvetica-Bold"),
    ])
    summary_tbl.setStyle(sts)
    story.append(summary_tbl)

    story.append(Spacer(1, 0.1 * inch))
    story.append(Paragraph(
        "Vehicle schedule as of March 1, 2024. TI = Trailer Interchange coverage. "
        "Driver schedule and MVRs to be submitted separately. "
        "Garaging locations: Memphis TN (HQ), Nashville TN, Birmingham AL, Atlanta GA. "
        "Broker: Coastal Insurance Advisors | Underwriter: Pinnacle Commercial Insurance",
        footer_s
    ))

    doc.build(story, onFirstPage=add_page_number, onLaterPages=add_page_number)
    print(f"  Created: {out_path}")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    print("Generating SOV sample PDFs...")
    build_acme_manufacturing()
    build_westfield_retail()
    build_abc_logistics_vehicles()
    print("Done. All PDF files created successfully.")
