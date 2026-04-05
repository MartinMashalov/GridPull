"""
Generate a realistic 3-4 page commercial property schedule PDF for testing AI extraction.
Labels are intentionally varied from standard field names to test semantic mapping.
"""

from reportlab.lib.pagesizes import landscape, letter
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.platypus import (
    SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer,
    HRFlowable, PageBreak
)
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT
from reportlab.platypus.flowables import KeepTogether

OUTPUT_PATH = "/Users/martinmashalov/Downloads/GridPull/test_documents/12_sov_email_examples/complex_property_schedule_8_locations.pdf"

# ---------------------------------------------------------------------------
# COLOR PALETTE
# ---------------------------------------------------------------------------
DARK_NAVY   = colors.HexColor("#1A2B4A")
MID_BLUE    = colors.HexColor("#2E5F8A")
LIGHT_BLUE  = colors.HexColor("#D6E8F5")
ALT_ROW     = colors.HexColor("#EEF4FA")
WHITE       = colors.white
GOLD        = colors.HexColor("#B8942A")
LIGHT_GREY  = colors.HexColor("#F2F2F2")
MED_GREY    = colors.HexColor("#CCCCCC")
DARK_GREY   = colors.HexColor("#444444")
TOTAL_ROW   = colors.HexColor("#C8D8E8")

# ---------------------------------------------------------------------------
# RAW DATA — 8 residential properties
# ---------------------------------------------------------------------------
#  [loc, bldg, prop_name, use_type, address, city, state, zip_, parish,
#   frame_type, iso_code,
#   rc_bldg, bpp, bi_ee, me, other_, tiv,
#   sqft, cost_psf, yr_blt,
#   roof_upd, elec_upd, hvac_yr, plbg_yr,
#   occ_pct, spkl, spkl_pct, ppc, fire_alm, burg_alm, smoke_det,
#   stories, units, wiring,
#   subsid_pct, student_pct, senior_pct,
#   roof_type, roof_shape, flood, eq, coast_dist, own_mgd, maint, bsmt, ext_wall]

PROPERTIES = [
    (1, 1, "Bayou Gardens Apts A", "Residential/Apt",
     "1 Meadows Blvd", "Slidell", "LA", "70460", "St. Tammany",
     "Frame", "F",
     408980, 0, 35952, 0, 0, 444932,
     3718, 110.0, 1985,
     2020, 2004, 2010, 2009,
     100, "N", 0, 2, "N", "N", "Y",
     2, 4, "Copper",
     0, 0, 0,
     "Gable", "G", "X", "0", "60 mi", "O", "G", "N", "Wood Siding"),

    (1, 2, "Bayou Gardens Apts B", "Residential/Apt",
     "9 Meadows Blvd", "Slidell", "LA", "70460", "St. Tammany",
     "Frame", "F",
     387450, 0, 33200, 0, 0, 420650,
     3520, 110.0, 1985,
     2020, 2004, 2010, 2009,
     100, "N", 0, 2, "N", "N", "Y",
     2, 4, "Copper",
     0, 0, 0,
     "Gable", "G", "X", "0", "60 mi", "O", "G", "N", "Wood Siding"),

    (2, 1, "Pinehurst Commons", "Residential/Apt",
     "450 Pine Ridge Dr", "Covington", "LA", "70433", "St. Tammany",
     "Frame", "F",
     892000, 0, 78400, 0, 0, 970400,
     7840, 114.0, 1992,
     2018, 2015, 2018, 2000,
     100, "N", 0, 3, "N", "Y", "Y",
     2, 8, "Copper",
     0, 0, 0,
     "Gable", "G", "X", "0", "55 mi", "O", "G", "N", "Vinyl Siding"),

    (3, 1, "Magnolia Court", "Residential/Apt",
     "1201 Tulane Ave", "New Orleans", "LA", "70112", "Orleans",
     "Masonry", "B",
     1650000, 0, 198000, 0, 0, 1848000,
     11200, 147.0, 1962,
     2016, 2008, 2019, 2008,
     92, "N", 0, 1, "Y", "Y", "Y",
     3, 12, "Mixed",
     35, 0, 15,
     "Flat", "F", "AE", "1", "5 mi", "O", "A", "Y", "Brick"),

    (4, 1, "Gulf Breeze Estates", "Residential/Apt",
     "88 Beachfront Ln", "Bay St. Louis", "MS", "39520", "Hancock",
     "Frame", "F",
     725000, 0, 62500, 0, 0, 787500,
     5400, 134.0, 2005,
     2022, 2005, 2021, 2005,
     100, "N", 0, 4, "N", "N", "Y",
     2, 6, "Copper",
     0, 0, 0,
     "Hip", "H", "VE", "2", "0.2 mi", "O", "G", "N", "Hardboard"),

    (5, 1, "River Oaks Manor", "Residential/Apt",
     "3300 Magazine St", "New Orleans", "LA", "70115", "Orleans",
     "Masonry", "B",
     2200000, 0, 264000, 0, 0, 2464000,
     18000, 122.0, 1948,
     2015, 2012, 2017, 2012,
     88, "Y", 40, 1, "Y", "Y", "Y",
     4, 16, "Mixed",
     20, 0, 45,
     "Flat", "F", "AE", "1", "6 mi", "M", "A", "Y", "Stucco"),

    (6, 1, "Pelican Pointe", "Residential/Apt",
     "720 Canal Rd", "Gulfport", "MS", "39507", "Harrison",
     "Frame", "F",
     2850000, 0, 228000, 0, 0, 3078000,
     22800, 125.0, 1998,
     2020, 2014, 2019, 2010,
     95, "N", 0, 3, "N", "Y", "Y",
     3, 24, "Copper",
     0, 0, 10,
     "Hip", "H", "X", "2", "1.5 mi", "O", "G", "N", "Hardboard"),

    (7, 1, "Sunset Senior Villas", "Residential/Apt",
     "555 Veterans Blvd", "Metairie", "LA", "70005", "Jefferson",
     "Frame", "F",
     1980000, 0, 178200, 0, 0, 2158200,
     15600, 127.0, 2001,
     2023, 2001, 2020, 2015,
     100, "N", 0, 2, "Y", "Y", "Y",
     2, 20, "Copper",
     30, 0, 100,
     "Gable", "G", "X", "1", "12 mi", "O", "G", "N", "Vinyl Siding"),
]

# ---------------------------------------------------------------------------
# HELPERS
# ---------------------------------------------------------------------------

def fmt_currency(val):
    if val == 0:
        return "$0"
    return "${:,.0f}".format(val)

def fmt_int(val):
    return "{:,}".format(val)

def fmt_pct(val):
    return "{}%".format(val)


# ---------------------------------------------------------------------------
# STYLES
# ---------------------------------------------------------------------------

styles = getSampleStyleSheet()

title_style = ParagraphStyle(
    "TitleStyle",
    parent=styles["Normal"],
    fontName="Helvetica-Bold",
    fontSize=14,
    textColor=WHITE,
    alignment=TA_CENTER,
    spaceAfter=2,
)
subtitle_style = ParagraphStyle(
    "SubtitleStyle",
    parent=styles["Normal"],
    fontName="Helvetica",
    fontSize=9,
    textColor=LIGHT_BLUE,
    alignment=TA_CENTER,
    spaceAfter=0,
)
section_hdr_style = ParagraphStyle(
    "SectionHdr",
    parent=styles["Normal"],
    fontName="Helvetica-Bold",
    fontSize=8,
    textColor=WHITE,
    alignment=TA_LEFT,
    spaceAfter=0,
)
body_style = ParagraphStyle(
    "BodyStyle",
    parent=styles["Normal"],
    fontName="Helvetica",
    fontSize=8,
    textColor=DARK_GREY,
    spaceAfter=4,
)
note_style = ParagraphStyle(
    "NoteStyle",
    parent=styles["Normal"],
    fontName="Helvetica-Oblique",
    fontSize=7,
    textColor=DARK_GREY,
    spaceAfter=2,
)
footer_style = ParagraphStyle(
    "FooterStyle",
    parent=styles["Normal"],
    fontName="Helvetica",
    fontSize=6.5,
    textColor=colors.HexColor("#888888"),
    alignment=TA_CENTER,
)

# ---------------------------------------------------------------------------
# HEADER BUILDER
# ---------------------------------------------------------------------------

def make_header(title_text, subtitle_text, page_label):
    """Return a table that renders a branded page header."""
    header_content = [
        [Paragraph("STERLING COAST INSURANCE BROKERS, LLC", title_style),
         Paragraph(page_label, ParagraphStyle("pg", parent=title_style, alignment=TA_RIGHT, fontSize=8))],
        [Paragraph(title_text, subtitle_style), ""],
        [Paragraph(subtitle_text, subtitle_style), ""],
    ]
    hdr_tbl = Table(header_content, colWidths=["85%", "15%"])
    hdr_tbl.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), DARK_NAVY),
        ("SPAN", (0, 1), (-1, 1)),
        ("SPAN", (0, 2), (-1, 2)),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ("LEFTPADDING", (0, 0), (-1, -1), 10),
        ("RIGHTPADDING", (0, 0), (-1, -1), 10),
        ("ROUNDEDCORNERS", [4, 4, 4, 4]),
    ]))
    return hdr_tbl


def make_sub_header(text):
    """Colored band for section label."""
    tbl = Table([[Paragraph(text, section_hdr_style)]], colWidths=["100%"])
    tbl.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), MID_BLUE),
        ("TOPPADDING", (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
        ("LEFTPADDING", (0, 0), (-1, -1), 8),
    ]))
    return tbl


# ---------------------------------------------------------------------------
# TABLE STYLE BUILDER
# ---------------------------------------------------------------------------

def base_table_style(num_data_rows, header_rows=2):
    """Return a TableStyle with alternating shading."""
    cmds = [
        # Outer border
        ("BOX",        (0, 0), (-1, -1), 0.6, DARK_NAVY),
        # Header rows
        ("BACKGROUND", (0, 0), (-1, header_rows - 1), MID_BLUE),
        ("TEXTCOLOR",  (0, 0), (-1, header_rows - 1), WHITE),
        ("FONTNAME",   (0, 0), (-1, header_rows - 1), "Helvetica-Bold"),
        ("FONTSIZE",   (0, 0), (-1, header_rows - 1), 6.5),
        ("ALIGN",      (0, 0), (-1, header_rows - 1), "CENTER"),
        ("VALIGN",     (0, 0), (-1, header_rows - 1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, header_rows - 1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, header_rows - 1), 3),
        # Data rows default
        ("FONTNAME",   (0, header_rows), (-1, -1), "Helvetica"),
        ("FONTSIZE",   (0, header_rows), (-1, -1), 6.5),
        ("VALIGN",     (0, header_rows), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, header_rows), (-1, -1), 2),
        ("BOTTOMPADDING", (0, header_rows), (-1, -1), 2),
        ("LEFTPADDING",   (0, 0), (-1, -1), 3),
        ("RIGHTPADDING",  (0, 0), (-1, -1), 3),
        # Inner grid
        ("INNERGRID",  (0, 0), (-1, -1), 0.25, MED_GREY),
        # Align numbers right
        ("ALIGN",      (0, header_rows), (-1, -1), "CENTER"),
    ]
    # Alternating row shading
    for i in range(header_rows, header_rows + num_data_rows):
        if (i - header_rows) % 2 == 1:
            cmds.append(("BACKGROUND", (0, i), (-1, i), ALT_ROW))
    return TableStyle(cmds)


def add_totals_style(style, total_row_idx):
    """Highlight totals row."""
    style.add("BACKGROUND", (0, total_row_idx), (-1, total_row_idx), TOTAL_ROW)
    style.add("FONTNAME",   (0, total_row_idx), (-1, total_row_idx), "Helvetica-Bold")
    style.add("FONTSIZE",   (0, total_row_idx), (-1, total_row_idx), 6.5)
    return style


# ---------------------------------------------------------------------------
# PAGE 1 — Property Info + Values (cols 1-15)
# ---------------------------------------------------------------------------

def build_page1():
    elements = []

    hdr = make_header(
        "COMMERCIAL PROPERTY — SCHEDULE OF VALUES",
        "Insured: Gulf Coast Residential Holdings, LLC   |   Policy Period: 04/01/2026 – 04/01/2027   |   Broker: Sterling Coast Insurance Brokers",
        "Page 1 of 4"
    )
    elements.append(hdr)
    elements.append(Spacer(1, 6))
    elements.append(make_sub_header(
        "SECTION 1 — PROPERTY IDENTIFICATION & INSURABLE VALUES   (All dollar amounts are Replacement Cost)"))
    elements.append(Spacer(1, 4))

    # Column headers — two rows for grouping
    grp1 = ["", "", "", "", "", "", "", "", "",
            "—— Replacement Cost Values ——", "", "", "", "", ""]
    hdr1 = ["Loc", "Unit", "Property Name", "Occ Class",
            "Site Address", "City", "St", "Zip", "Parish",
            "Bldg RC", "BPP", "Loss of Rents", "M&E", "Other",
            "Total IV"]

    rows = [grp1, hdr1]
    for p in PROPERTIES:
        (loc, bldg, name, use, addr, city, state, zip_, parish,
         frame, iso,
         rc, bpp, bi, me, other_, tiv,
         *_rest) = p
        rows.append([
            str(loc), str(bldg), name, use,
            addr, city, state, zip_, parish,
            fmt_currency(rc), fmt_currency(bpp), fmt_currency(bi),
            fmt_currency(me), fmt_currency(other_), fmt_currency(tiv),
        ])

    # Totals
    tot_rc  = sum(p[11] for p in PROPERTIES)
    tot_bpp = sum(p[12] for p in PROPERTIES)
    tot_bi  = sum(p[13] for p in PROPERTIES)
    tot_me  = sum(p[14] for p in PROPERTIES)
    tot_oth = sum(p[15] for p in PROPERTIES)
    tot_tiv = sum(p[16] for p in PROPERTIES)
    rows.append([
        "TOTAL", "", "", "", "", "", "", "", "",
        fmt_currency(tot_rc), fmt_currency(tot_bpp), fmt_currency(tot_bi),
        fmt_currency(tot_me), fmt_currency(tot_oth), fmt_currency(tot_tiv),
    ])

    col_widths = [
        0.28*inch, 0.28*inch, 1.20*inch, 0.80*inch,
        1.18*inch, 0.72*inch, 0.24*inch, 0.50*inch, 0.78*inch,
        0.82*inch, 0.52*inch, 0.82*inch, 0.50*inch, 0.50*inch,
        0.92*inch,
    ]

    tbl = Table(rows, colWidths=col_widths, repeatRows=2)
    ts = base_table_style(len(PROPERTIES), header_rows=2)
    # Span the group header
    ts.add("SPAN", (9, 0), (13, 0))
    ts.add("ALIGN", (9, 0), (13, 0), "CENTER")
    ts.add("FONTSIZE", (0, 0), (-1, 0), 6)
    ts.add("BACKGROUND", (0, 0), (-1, 0), DARK_NAVY)
    # Right-align currency columns
    for col in range(9, 15):
        ts.add("ALIGN", (col, 2), (col, -1), "RIGHT")
    # Left-align text columns
    for col in [2, 3, 4, 5]:
        ts.add("ALIGN", (col, 2), (col, -1), "LEFT")
    add_totals_style(ts, len(PROPERTIES) + 2)
    tbl.setStyle(ts)

    elements.append(tbl)
    elements.append(Spacer(1, 10))

    # Construction type legend
    elements.append(Paragraph(
        "<b>Construction Codes:</b>  F = Frame  |  B = Joisted Masonry  |  C = Non-Combustible  |  D = Masonry Non-Combustible  |  E = Modified Fire Resistive  |  A = Fire Resistive",
        note_style))
    elements.append(Paragraph(
        "<b>Values Basis:</b>  All building values reflect 100% Replacement Cost as of policy inception.  "
        "Loss of Rents (BI/EE) based on 12-month indemnity period.  M&E = Machinery & Equipment (residential — $0 typical).",
        note_style))

    elements.append(Spacer(1, 6))

    # Mini construction summary table
    elements.append(make_sub_header("CONSTRUCTION SUMMARY BY LOCATION"))
    elements.append(Spacer(1, 3))

    cons_hdr = ["Loc", "Unit", "Property Name", "Frame Type", "ISO", "Yr Blt", "Stories", "Units", "GLA (SF)"]
    cons_rows = [cons_hdr]
    for p in PROPERTIES:
        (loc, bldg, name, use, addr, city, state, zip_, parish,
         frame, iso,
         rc, bpp, bi, me, other_, tiv,
         sqft, cost_psf, yr_blt,
         *_rest) = p
        cons_rows.append([str(loc), str(bldg), name, frame, iso,
                          str(yr_blt), str(_rest[20 - 20 + 1 - 1 + 1]),  # stories
                          str(_rest[1 + 1]),  # units
                          fmt_int(sqft)])

    # Re-extract correctly
    cons_rows = [cons_hdr]
    for p in PROPERTIES:
        loc, bldg, name = p[0], p[1], p[2]
        frame, iso = p[9], p[10]
        sqft, yr_blt = p[17], p[19]
        stories, units = p[31], p[32]
        cons_rows.append([str(loc), str(bldg), name, frame, iso,
                          str(yr_blt), str(stories), str(units), fmt_int(sqft)])

    cons_col_w = [0.32*inch, 0.32*inch, 1.6*inch, 0.8*inch, 0.35*inch,
                  0.55*inch, 0.55*inch, 0.55*inch, 0.85*inch]
    cons_tbl = Table(cons_rows, colWidths=cons_col_w)
    cons_ts = base_table_style(len(PROPERTIES), header_rows=1)
    cons_ts.add("ALIGN", (2, 1), (2, -1), "LEFT")
    cons_tbl.setStyle(cons_ts)
    elements.append(cons_tbl)

    return elements


# ---------------------------------------------------------------------------
# PAGE 2 — Physical Characteristics (cols 16-30)
# ---------------------------------------------------------------------------

def build_page2():
    elements = []
    elements.append(make_header(
        "COMMERCIAL PROPERTY — SCHEDULE OF VALUES",
        "Insured: Gulf Coast Residential Holdings, LLC   |   Policy Period: 04/01/2026 – 04/01/2027",
        "Page 2 of 4"
    ))
    elements.append(Spacer(1, 6))
    elements.append(make_sub_header(
        "SECTION 2 — PHYSICAL CHARACTERISTICS, SIZE & UPDATES"))
    elements.append(Spacer(1, 4))

    hdr2a = ["Loc", "Unit", "Property Name",
             "GLA\n(Sq Ft)", "$/SF",
             "Yr Blt",
             "Roof Yr", "Elec Upd", "HVAC Yr", "Plbg Yr",
             "Occ %",
             "Spkl", "Spkl %",
             "PPC",
             "Fire\nAlm", "Burg\nAlm", "Smoke\nDet",
             "Stories"]

    rows = [hdr2a]
    for p in PROPERTIES:
        (loc, bldg, name, use, addr, city, state, zip_, parish,
         frame, iso,
         rc, bpp, bi, me, other_, tiv,
         sqft, cost_psf, yr_blt,
         roof_upd, elec_upd, hvac_yr, plbg_yr,
         occ_pct, spkl, spkl_pct, ppc, fire_alm, burg_alm, smoke_det,
         stories, units, wiring,
         subsid_pct, student_pct, senior_pct,
         roof_type, roof_shape, flood, eq, coast_dist, own_mgd, maint, bsmt, ext_wall) = p

        rows.append([
            str(loc), str(bldg), name,
            fmt_int(sqft), "${:.0f}".format(cost_psf),
            str(yr_blt),
            str(roof_upd), str(elec_upd), str(hvac_yr), str(plbg_yr),
            fmt_pct(occ_pct),
            spkl, fmt_pct(spkl_pct),
            str(ppc),
            fire_alm, burg_alm, smoke_det,
            str(stories),
        ])

    col_widths2 = [
        0.32*inch, 0.32*inch, 1.45*inch,
        0.70*inch, 0.45*inch,
        0.45*inch,
        0.52*inch, 0.52*inch, 0.52*inch, 0.52*inch,
        0.45*inch,
        0.38*inch, 0.42*inch,
        0.38*inch,
        0.38*inch, 0.38*inch, 0.45*inch,
        0.45*inch,
    ]

    tbl2 = Table(rows, colWidths=col_widths2, repeatRows=1)
    ts2 = base_table_style(len(PROPERTIES), header_rows=1)
    ts2.add("ALIGN", (2, 1), (2, -1), "LEFT")
    ts2.add("ALIGN", (3, 1), (3, -1), "RIGHT")
    ts2.add("ALIGN", (4, 1), (4, -1), "RIGHT")
    tbl2.setStyle(ts2)
    elements.append(tbl2)

    elements.append(Spacer(1, 10))
    elements.append(Paragraph(
        "<b>Notes:</b>  PPC = ISO Public Protection Class (1=Best, 10=No Protection).  "
        "Roof Yr / Elec Upd / HVAC Yr / Plbg Yr reflect year of most recent full replacement or major renovation.  "
        "Spkl = Sprinklered (Y/Partial/N).  Occ % = Residential occupancy at time of survey.",
        note_style))

    elements.append(Spacer(1, 10))
    elements.append(make_sub_header(
        "SECTION 2B — YEAR BUILT & UPDATE TIMELINE LEGEND"))
    elements.append(Spacer(1, 4))

    legend_data = [
        ["Abbrev.", "Full Description", "Abbrev.", "Full Description"],
        ["Roof Yr",  "Year roof was fully replaced/re-covered",   "Elec Upd", "Year electrical wiring/panel fully updated"],
        ["HVAC Yr",  "Year heating & cooling system replaced",     "Plbg Yr",  "Year major plumbing updated"],
        ["Yr Blt",   "Original year of construction",              "GLA",      "Gross Leasable Area (total heated square footage)"],
        ["Occ %",    "Percent of units currently occupied",        "$/SF",     "Replacement cost per square foot (RC Bldg ÷ GLA)"],
        ["PPC",      "ISO Public Protection Class",                "Spkl %",   "Percent of building covered by fire suppression"],
    ]
    leg_tbl = Table(legend_data, colWidths=[0.75*inch, 3.2*inch, 0.75*inch, 3.2*inch])
    leg_ts = TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), MID_BLUE),
        ("TEXTCOLOR", (0, 0), (-1, 0), WHITE),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 7),
        ("FONTNAME", (0, 1), (-1, -1), "Helvetica"),
        ("INNERGRID", (0, 0), (-1, -1), 0.25, MED_GREY),
        ("BOX", (0, 0), (-1, -1), 0.5, DARK_NAVY),
        ("ALIGN", (0, 0), (-1, -1), "LEFT"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 2),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
        ("LEFTPADDING", (0, 0), (-1, -1), 4),
        ("BACKGROUND", (0, 1), (-1, 1), ALT_ROW),
        ("BACKGROUND", (0, 3), (-1, 3), ALT_ROW),
        ("BACKGROUND", (0, 5), (-1, 5), ALT_ROW),
    ])
    leg_tbl.setStyle(leg_ts)
    elements.append(leg_tbl)

    return elements


# ---------------------------------------------------------------------------
# PAGE 3 — Demographic, Risk, and Property Characteristics + Totals
# ---------------------------------------------------------------------------

def build_page3():
    elements = []
    elements.append(make_header(
        "COMMERCIAL PROPERTY — SCHEDULE OF VALUES",
        "Insured: Gulf Coast Residential Holdings, LLC   |   Policy Period: 04/01/2026 – 04/01/2027",
        "Page 3 of 4"
    ))
    elements.append(Spacer(1, 6))
    elements.append(make_sub_header(
        "SECTION 3 — UNIT MIX, RISK CHARACTERISTICS & PROPERTY DETAILS"))
    elements.append(Spacer(1, 4))

    hdr3 = [
        "Loc", "Unit", "Property Name",
        "Units", "Wiring",
        "Subsid\n%", "Student\n%", "Senior\n%",
        "Roof\nType", "Roof\nShape",
        "Flood\nZone", "EQ",
        "Coast\nDist",
        "Own/\nMgd", "Maint",
        "Bsmt",
        "Ext Wall / Cladding",
    ]

    rows = [hdr3]
    for p in PROPERTIES:
        (loc, bldg, name, use, addr, city, state, zip_, parish,
         frame, iso,
         rc, bpp, bi, me, other_, tiv,
         sqft, cost_psf, yr_blt,
         roof_upd, elec_upd, hvac_yr, plbg_yr,
         occ_pct, spkl, spkl_pct, ppc, fire_alm, burg_alm, smoke_det,
         stories, units, wiring,
         subsid_pct, student_pct, senior_pct,
         roof_type, roof_shape, flood, eq, coast_dist, own_mgd, maint, bsmt, ext_wall) = p

        rows.append([
            str(loc), str(bldg), name,
            str(units), wiring,
            fmt_pct(subsid_pct), fmt_pct(student_pct), fmt_pct(senior_pct),
            roof_type, roof_shape,
            flood, str(eq),
            coast_dist,
            own_mgd, maint,
            bsmt,
            ext_wall,
        ])

    # Totals / summary row
    tot_units = sum(p[32] for p in PROPERTIES)
    tot_sqft  = sum(p[17] for p in PROPERTIES)
    tot_tiv   = sum(p[16] for p in PROPERTIES)
    rows.append([
        "TOTAL", "", "8 Properties",
        str(tot_units), "",
        "", "", "",
        "", "", "", "", "", "", "", "",
        "TIV: {}  |  Total GLA: {} SF".format(fmt_currency(tot_tiv), fmt_int(tot_sqft)),
    ])

    col_widths3 = [
        0.32*inch, 0.32*inch, 1.30*inch,
        0.42*inch, 0.72*inch,
        0.48*inch, 0.52*inch, 0.52*inch,
        0.58*inch, 0.50*inch,
        0.50*inch, 0.35*inch,
        0.60*inch,
        0.42*inch, 0.42*inch,
        0.38*inch,
        1.15*inch,
    ]

    tbl3 = Table(rows, colWidths=col_widths3, repeatRows=1)
    ts3 = base_table_style(len(PROPERTIES), header_rows=1)
    ts3.add("ALIGN", (2, 1), (2, -1), "LEFT")
    ts3.add("ALIGN", (16, 1), (16, -1), "LEFT")
    add_totals_style(ts3, len(PROPERTIES) + 1)
    ts3.add("SPAN", (16, len(PROPERTIES) + 1), (16, len(PROPERTIES) + 1))
    ts3.add("ALIGN", (16, len(PROPERTIES) + 1), (16, len(PROPERTIES) + 1), "LEFT")
    tbl3.setStyle(ts3)
    elements.append(tbl3)

    elements.append(Spacer(1, 8))
    elements.append(Paragraph(
        "<b>Legend:</b>  Own/Mgd: O=Owned, M=Managed  |  Maint: G=Good, A=Average, P=Poor  |  "
        "Bsmt: Y=Basement Present, N=No Basement  |  "
        "Roof Shape: H=Hip, G=Gable, F=Flat  |  "
        "Flood Zone: X=Minimal, AE=100-yr Floodplain, VE=Coastal High Hazard  |  "
        "EQ: Seismic Zone (0=negligible, 1=low, 2=moderate)  |  "
        "Coast Dist: Estimated straight-line distance to nearest saltwater body",
        note_style))

    elements.append(Spacer(1, 10))

    # ---- AGGREGATE VALUE SUMMARY TABLE ----
    elements.append(make_sub_header("AGGREGATE INSURABLE VALUE SUMMARY"))
    elements.append(Spacer(1, 4))

    agg_hdr = ["Value Component", "Total Amount", "% of TIV", "Notes"]
    tot_rc   = sum(p[11] for p in PROPERTIES)
    tot_bi   = sum(p[13] for p in PROPERTIES)
    agg_rows = [
        agg_hdr,
        ["Bldg Replacement Cost (RC Bldg)",  fmt_currency(tot_rc),
         "{:.1f}%".format(tot_rc / tot_tiv * 100),
         "100% RC basis; no coinsurance clause"],
        ["Business Personal Property (BPP)",  "$0",       "0.0%",
         "Residential — tenant contents excluded"],
        ["Loss of Rents / Bus. Income (BI/EE)", fmt_currency(tot_bi),
         "{:.1f}%".format(tot_bi / tot_tiv * 100),
         "12-month indemnity; actual loss sustained"],
        ["Machinery & Equipment (M&E)",       "$0",       "0.0%",
         "Residential properties — not applicable"],
        ["Other Property",                    "$0",       "0.0%",
         ""],
        ["TOTAL INSURABLE VALUE (TIV)",       fmt_currency(tot_tiv), "100.0%",
         "{} locations / {} buildings / {} units".format(
             len(set(p[0] for p in PROPERTIES)),
             len(PROPERTIES),
             sum(p[32] for p in PROPERTIES))],
    ]

    agg_col_w = [2.2*inch, 1.3*inch, 0.75*inch, 3.6*inch]
    agg_tbl = Table(agg_rows, colWidths=agg_col_w)
    agg_ts = TableStyle([
        ("BACKGROUND",    (0, 0), (-1, 0), MID_BLUE),
        ("TEXTCOLOR",     (0, 0), (-1, 0), WHITE),
        ("FONTNAME",      (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE",      (0, 0), (-1, -1), 7.5),
        ("FONTNAME",      (0, 1), (-1, -1), "Helvetica"),
        ("INNERGRID",     (0, 0), (-1, -1), 0.25, MED_GREY),
        ("BOX",           (0, 0), (-1, -1), 0.6, DARK_NAVY),
        ("ALIGN",         (0, 0), (-1, -1), "LEFT"),
        ("ALIGN",         (1, 0), (2, -1), "RIGHT"),
        ("VALIGN",        (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING",    (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
        ("LEFTPADDING",   (0, 0), (-1, -1), 5),
        ("BACKGROUND",    (0, 2), (-1, 2), ALT_ROW),
        ("BACKGROUND",    (0, 4), (-1, 4), ALT_ROW),
        ("BACKGROUND",    (0, 6), (-1, 6), TOTAL_ROW),
        ("FONTNAME",      (0, 6), (-1, 6), "Helvetica-Bold"),
    ])
    agg_tbl.setStyle(agg_ts)
    elements.append(agg_tbl)

    return elements


# ---------------------------------------------------------------------------
# PAGE 4 — Notes, Underwriting Summary, Broker Attestation
# ---------------------------------------------------------------------------

def build_page4():
    elements = []
    elements.append(make_header(
        "COMMERCIAL PROPERTY — SCHEDULE OF VALUES",
        "Insured: Gulf Coast Residential Holdings, LLC   |   Policy Period: 04/01/2026 – 04/01/2027",
        "Page 4 of 4"
    ))
    elements.append(Spacer(1, 8))
    elements.append(make_sub_header("SECTION 4 — UNDERWRITING NOTES & RISK SUMMARY"))
    elements.append(Spacer(1, 6))

    notes = [
        ("<b>Portfolio Overview:</b>  Gulf Coast Residential Holdings, LLC owns and manages a portfolio of 8 apartment buildings "
         "totaling 94 residential units across 7 locations in Louisiana and Mississippi.  The portfolio is concentrated in the "
         "Greater New Orleans metro area and the Mississippi Gulf Coast, with significant coastal and flood exposure."),

        ("<b>Construction &amp; Age:</b>  Two properties (Magnolia Court, River Oaks Manor) are pre-1970 masonry construction "
         "with extensive system updates completed 2008–2019.  Remaining properties are wood-frame construction built 1985–2005.  "
         "All roofs updated within the past 8 years."),

        ("<b>Flood &amp; Coastal Exposure:</b>  Three of 8 buildings are in FEMA Special Flood Hazard Areas (SFHA): "
         "Magnolia Court (AE), River Oaks Manor (AE), and Gulf Breeze Estates (VE — coastal high hazard zone, 0.2 miles from "
         "Gulf of Mexico).  Flood coverage is excluded from this property schedule and is addressed under separate flood policy."),

        ("<b>Subsidized/Affordable Housing:</b>  Magnolia Court (35% subsidized) and River Oaks Manor (20% subsidized) "
         "participate in federal low-income housing tax credit (LIHTC) programs.  Sunset Senior Villas is 100% senior/elderly "
         "housing and 30% subsidized.  These designations affect tenant occupancy restrictions and renovation timelines."),

        ("<b>Sprinkler Systems:</b>  Only River Oaks Manor has partial sprinkler coverage (approximately 40% — common areas and "
         "corridors only).  All other properties rely on smoke detectors and manual suppression only.  Installation of full "
         "sprinkler systems is under consideration for the two New Orleans masonry properties."),

        ("<b>Wiring:</b>  Both pre-1970 masonry properties contain mixed aluminum/copper wiring; all other properties are "
         "all-copper.  Mixed wiring was noted as a concern during the 2023 inspection; River Oaks Manor and Magnolia Court "
         "both received partial rewiring credits for the 2008 and 2012 updates respectively."),

        ("<b>Management:</b>  River Oaks Manor (Loc 5) is professionally managed by a third-party property management company "
         "(Magnolia Property Services, Inc.) and is coded as Managed (M).  All other locations are directly owned and operated "
         "by Gulf Coast Residential Holdings, LLC."),

        ("<b>Valuations Basis:</b>  All replacement cost values were produced by Marshall &amp; Swift / CoreLogic RCT Express "
         "desktop appraisal tool as of March 2026.  Prior year values updated at +4.2% trend factor per carrier worksheet.  "
         "A full appraisal of the two masonry buildings is recommended at next renewal."),
    ]

    for note in notes:
        elements.append(Paragraph(note, body_style))
        elements.append(Spacer(1, 3))

    elements.append(Spacer(1, 8))
    elements.append(HRFlowable(width="100%", thickness=0.5, color=MID_BLUE))
    elements.append(Spacer(1, 6))
    elements.append(make_sub_header("BROKER ATTESTATION"))
    elements.append(Spacer(1, 5))

    attest_text = (
        "I, the undersigned authorized representative of Sterling Coast Insurance Brokers, LLC, hereby attest that the "
        "information contained in this Schedule of Values has been compiled in good faith from data provided by the insured, "
        "Gulf Coast Residential Holdings, LLC, and/or from publicly available records.  Values represent our best estimate "
        "of replacement cost as of the policy inception date.  This schedule is subject to change upon receipt of updated "
        "appraisals or insured-reported corrections."
    )
    elements.append(Paragraph(attest_text, body_style))
    elements.append(Spacer(1, 20))

    sig_data = [
        ["Broker of Record:", "_" * 40, "Date:", "_" * 20],
        ["",                  "J. Thibodaux, CIC, ARM",   "",   "04 / 01 / 2026"],
        ["",                  "Sterling Coast Insurance Brokers, LLC", "", ""],
        ["",                  "License #: LA-998821 / MS-47823", "", ""],
    ]
    sig_tbl = Table(sig_data, colWidths=[1.1*inch, 3.0*inch, 0.55*inch, 1.8*inch])
    sig_ts = TableStyle([
        ("FONTNAME",  (0, 0), (-1, -1), "Helvetica"),
        ("FONTSIZE",  (0, 0), (-1, -1), 8),
        ("FONTNAME",  (0, 0), (0, 0),   "Helvetica-Bold"),
        ("FONTNAME",  (2, 0), (2, 0),   "Helvetica-Bold"),
        ("ALIGN",     (0, 0), (-1, -1), "LEFT"),
        ("VALIGN",    (0, 0), (-1, -1), "BOTTOM"),
        ("TOPPADDING",    (0, 0), (-1, -1), 2),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
    ])
    sig_tbl.setStyle(sig_ts)
    elements.append(sig_tbl)

    return elements


# ---------------------------------------------------------------------------
# PAGE FOOTER — drawn on every page via canvas callback
# ---------------------------------------------------------------------------

FOOTER_TEXT = (
    "CONFIDENTIAL — For insurance underwriting purposes only.  "
    "Not for distribution without written consent of Sterling Coast Insurance Brokers, LLC.  "
    "Sterling Coast Insurance Brokers, LLC  |  1800 Poydras St, Suite 900, New Orleans, LA 70112  |  (504) 555-0190"
)

def draw_page_footer(canvas, doc):
    """Draw a thin rule + confidential footer line in the bottom margin."""
    from reportlab.lib.units import inch as _inch
    page_w, page_h = canvas._pagesize
    left  = 0.45 * _inch
    right = page_w - 0.45 * _inch
    y_rule = 0.42 * _inch
    y_text = 0.22 * _inch

    canvas.saveState()
    canvas.setStrokeColor(MED_GREY)
    canvas.setLineWidth(0.4)
    canvas.line(left, y_rule, right, y_rule)

    canvas.setFont("Helvetica", 6.5)
    canvas.setFillColor(colors.HexColor("#888888"))
    canvas.drawCentredString(page_w / 2.0, y_text, FOOTER_TEXT)
    canvas.restoreState()


# ---------------------------------------------------------------------------
# ASSEMBLE DOCUMENT
# ---------------------------------------------------------------------------

def main():
    doc = SimpleDocTemplate(
        OUTPUT_PATH,
        pagesize=landscape(letter),
        leftMargin=0.45*inch,
        rightMargin=0.45*inch,
        topMargin=0.45*inch,
        bottomMargin=0.55*inch,   # extra room for the canvas footer
        title="Property Schedule of Values — Gulf Coast Residential Holdings",
        author="Sterling Coast Insurance Brokers, LLC",
        subject="Commercial Property SOV 2026-2027",
    )

    story = []
    story.extend(build_page1())
    story.append(PageBreak())
    story.extend(build_page2())
    story.append(PageBreak())
    story.extend(build_page3())
    story.append(PageBreak())
    story.extend(build_page4())

    doc.build(story, onFirstPage=draw_page_footer, onLaterPages=draw_page_footer)
    print("Generated: {}".format(OUTPUT_PATH))


if __name__ == "__main__":
    main()
