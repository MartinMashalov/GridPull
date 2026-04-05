#!/usr/bin/env python3
"""
Regenerate retail property schedule PDF with all 28 columns fitting cleanly.
Strategy: use very small font + two-row layout per location:
  Row A: Loc, Bldg, DBA, Class, Addr, City, ST, ZIP, Cnty, Const, ISO CC,
          Bldg Val, BPP, BI, M&E, TIV, Sq Ft, $/Sq Ft
  Row B: (same Loc, DBA for identification) Yr Blt, Rf Upd, Wir Upd, Pct Occ,
          Spkl, PPC, Sto, Rf Tp, Fld Zn, Owned
This keeps all fields present and readable.
"""
import os
from reportlab.lib.pagesizes import landscape, letter
from reportlab.lib import colors
from reportlab.lib.units import inch
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, PageBreak
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_CENTER, TA_LEFT

OUT = os.path.join(os.path.dirname(__file__), "retail_property_schedule_12_locations.pdf")

LOCATIONS = [
    # Loc, Bldg, DBA, Class, Addr, City, ST, ZIP, Cnty, Const, ISO_CC,
    # BldgVal, BPP, BI, ME, TIV, SqFt, DolPerSqFt,
    # YrBlt, RfUpd, WirUpd, PctOcc, Spkl, PPC, Sto, RfTp, FldZn, Owned
    (1,1,"Home Goods","Retail Store","1240 Westfield Blvd","Sacramento","CA","95815","Sacramento","Masonry",4,
     1850000,620000,290000,85000,2845000,22500,82.22,
     2001,2018,2010,"100%","Y","5","1","Flat","X","Owned"),
    (2,1,"Electronics","Retail Store","8800 Pacific Ave, Ste 101","Tacoma","WA","98444","Pierce","Steel",5,
     2100000,980000,440000,120000,3640000,28000,75.00,
     2008,2019,2008,"100%","Y","4","2","Flat","X","Owned"),
    (3,1,"Clothing","Retail Store","320 Main St","Boise","ID","83702","Ada","Frame",1,
     1050000,380000,195000,42000,1667000,14800,70.95,
     1988,2015,2006,"95%","N","6","1","Gable","X","Owned"),
    (4,1,"Sporting Goods","Retail Store","4700 Commerce Dr","Las Vegas","NV","89103","Clark","Masonry",4,
     1620000,740000,310000,68000,2738000,19500,83.08,
     1999,2016,2012,"100%","Y","5","1","Flat","X","Owned"),
    (5,1,"Home Goods","Retail Store","150 Industrial Pkwy","Tempe","AZ","85281","Maricopa","Steel",5,
     2450000,820000,395000,95000,3760000,31000,79.03,
     2005,2020,2005,"100%","Y","4","1","Flat","X","Managed"),
    (6,1,"Furniture","Retail Store","9001 N Freeway","Houston","TX","77037","Harris","Masonry",4,
     1780000,560000,265000,72000,2677000,21000,84.76,
     2003,2017,2009,"100%","Y","5","1","Flat","X","Owned"),
    (7,1,"Electronics","Retail Store","5500 Leetsdale Dr","Denver","CO","80224","Denver","Steel",5,
     2200000,950000,420000,105000,3675000,27500,80.00,
     2007,2021,2007,"100%","Y","4","2","Flat","X","Owned"),
    (8,1,"Clothing","Retail Store","1800 Nicholasville Rd","Lexington","KY","40503","Fayette","Frame",1,
     890000,310000,165000,38000,1403000,12500,71.20,
     1992,2014,2005,"90%","N","7","1","Gable","X","Managed"),
    (9,1,"Auto Parts","Retail Store","3355 Airport Rd","Charlotte","NC","28208","Mecklenburg","Steel",5,
     1400000,610000,280000,78000,2368000,18000,77.78,
     2003,2018,2003,"100%","Y","5","1","Flat","X","Owned"),
    (10,1,"Pet Supplies","Retail Store","7722 Broad St","Houston","TX","77061","Harris","Masonry",4,
     1230000,490000,220000,55000,1995000,16000,76.88,
     2000,2015,2008,"100%","Y","5","1","Flat","X","Owned"),
    (11,1,"Garden Center","Retail Store","640 Rivergate Pkwy","Goodlettsville","TN","37072","Davidson","Frame",1,
     980000,350000,175000,40000,1545000,13500,72.59,
     1997,2016,2004,"85%","N","7","1","Gable","AE","Owned"),
    (12,1,"Sporting Goods","Retail Store","4500 SE 82nd Ave","Portland","OR","97266","Multnomah","Steel",5,
     1920000,710000,345000,88000,3063000,24000,80.00,
     2006,2022,2006,"100%","Y","4","2","Flat","X","Owned"),
]

def fmt_dollar(v):
    return f"${v:,.0f}"

def build_pdf():
    doc = SimpleDocTemplate(
        OUT,
        pagesize=landscape(letter),
        leftMargin=0.4*inch, rightMargin=0.4*inch,
        topMargin=0.5*inch, bottomMargin=0.5*inch,
    )

    styles = getSampleStyleSheet()
    title_style = ParagraphStyle("title", fontSize=11, fontName="Helvetica-Bold", alignment=TA_CENTER, spaceAfter=4)
    sub_style   = ParagraphStyle("sub",   fontSize=8,  fontName="Helvetica",      alignment=TA_CENTER, spaceAfter=8)
    note_style  = ParagraphStyle("note",  fontSize=6,  fontName="Helvetica",      alignment=TA_LEFT)

    # ── Primary table: identification + values + size ──────────────────────────
    # Columns: Loc | Bldg | DBA | Class | Addr | City | ST | ZIP | Cnty | Const | ISO CC | Bldg Val | BPP | BI | M&E | TIV | Sq Ft | $/Sq Ft
    PRIMARY_HEADERS = ["Loc","Bldg","DBA","Class","Addr","City","ST","ZIP","Cnty","Const","ISO CC",
                        "Bldg Val","BPP","BI","M&E","TIV","Sq Ft","$/Sq Ft"]
    PRIMARY_WIDTHS  = [0.3,0.3,0.8,0.7,1.4,0.7,0.25,0.45,0.7,0.6,0.45,
                       0.7,0.6,0.55,0.45,0.7,0.45,0.45]   # inches

    # ── Attribute table: year/update/protection/structure info ─────────────────
    # Columns: Loc | DBA | Yr Blt | Rf Upd | Wir Upd | Pct Occ | Spkl | PPC | Sto | Rf Tp | Fld Zn | Owned
    ATTR_HEADERS = ["Loc","DBA","Yr Blt","Rf Upd","Wir Upd","Pct Occ","Spkl","PPC","Sto","Rf Tp","Fld Zn","Owned"]
    ATTR_WIDTHS  = [0.3,0.95,0.45,0.45,0.5,0.5,0.35,0.35,0.3,0.45,0.45,0.55]   # inches

    FONT_SZ   = 6.5
    HDR_FONT  = 6.5
    ROW_H     = 0.2*inch
    HDR_H     = 0.22*inch

    def cell(txt, bold=False):
        f = "Helvetica-Bold" if bold else "Helvetica"
        return Paragraph(f'<font name="{f}" size="{FONT_SZ}">{txt}</font>',
                         ParagraphStyle("c", alignment=TA_CENTER, leading=8))

    def lcell(txt):
        return Paragraph(f'<font name="Helvetica" size="{FONT_SZ}">{txt}</font>',
                         ParagraphStyle("lc", alignment=TA_LEFT, leading=8))

    def make_table(headers, widths_in, rows_data, title_row=None):
        col_w = [w*inch for w in widths_in]
        data = [[cell(h, bold=True) for h in headers]]
        for rd in rows_data:
            data.append([lcell(str(v)) for v in rd])

        ts = TableStyle([
            ("BACKGROUND",  (0,0), (-1,0), colors.HexColor("#1F4E79")),
            ("TEXTCOLOR",   (0,0), (-1,0), colors.white),
            ("ROWBACKGROUNDS", (0,1), (-1,-1), [colors.white, colors.HexColor("#EAF2FB")]),
            ("GRID",        (0,0), (-1,-1), 0.3, colors.HexColor("#AAAAAA")),
            ("FONTSIZE",    (0,0), (-1,-1), FONT_SZ),
            ("TOPPADDING",  (0,0), (-1,-1), 1),
            ("BOTTOMPADDING",(0,0),(-1,-1),1),
            ("LEFTPADDING", (0,0), (-1,-1), 2),
            ("RIGHTPADDING",(0,0),(-1,-1),2),
            ("ROWHEIGHT",   (0,0), (0,0),  HDR_H),
        ])
        for i in range(1, len(data)):
            ts.add("ROWHEIGHT", (0,i), (-1,i), ROW_H)

        return Table(data, colWidths=col_w, style=ts, repeatRows=1)

    # build primary rows
    primary_rows, attr_rows = [], []
    for loc in LOCATIONS:
        (l,b,dba,cls,addr,city,st,zipc,cnty,const,iso,
         bv,bpp,bi,me,tiv,sqft,dpsf,
         yrb,rfupd,wirupd,pctocc,spkl,ppc,sto,rftp,fldzn,owned) = loc
        primary_rows.append([l,b,dba,cls,addr,city,st,zipc,cnty,const,iso,
                              fmt_dollar(bv),fmt_dollar(bpp),fmt_dollar(bi),
                              fmt_dollar(me),fmt_dollar(tiv),f"{sqft:,}",f"${dpsf:.2f}"])
        attr_rows.append([l,dba,yrb,rfupd,wirupd,pctocc,spkl,ppc,sto,rftp,fldzn,owned])

    story = []
    story.append(Paragraph("CASCADE RETAIL GROUP", title_style))
    story.append(Paragraph(
        "Commercial Property Insurance Schedule  |  Policy Period: 07/01/2026 – 07/01/2027  |  All 12 Locations",
        sub_style))

    story.append(Paragraph("SECTION A — Location Identification & Values",
                            ParagraphStyle("sh", fontSize=7.5, fontName="Helvetica-Bold", spaceAfter=3, spaceBefore=4)))
    story.append(make_table(PRIMARY_HEADERS, PRIMARY_WIDTHS, primary_rows))
    story.append(Spacer(1, 0.15*inch))

    story.append(Paragraph("SECTION B — Building Attributes & Protection",
                            ParagraphStyle("sh2", fontSize=7.5, fontName="Helvetica-Bold", spaceAfter=3, spaceBefore=4)))
    story.append(make_table(ATTR_HEADERS, ATTR_WIDTHS, attr_rows))
    story.append(Spacer(1, 0.1*inch))

    legend = (
        "BPP = Business Personal Property  |  BI = Business Income  |  M&E = Machinery & Equipment  |  "
        "TIV = Bldg Val + BPP + BI + M&E  |  $/Sq Ft = Building Value ÷ Square Footage  |  "
        "Spkl = Sprinklered (Y/N)  |  PPC = ISO Protection Class  |  Sto = # of Stories  |  "
        "Rf Tp = Roof Type  |  Fld Zn = Flood Zone  |  ISO CC: 1=Frame, 4=Masonry, 5=Steel"
    )
    story.append(Paragraph(legend, note_style))

    doc.build(story)
    print(f"Generated: {OUT}")


if __name__ == "__main__":
    build_pdf()
