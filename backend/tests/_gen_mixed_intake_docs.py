"""
Generate a realistic multi-document intake package:
  07_customer_intake_form.pdf   — property questionnaire / intake form (8 locations)
  08_appraisal_supplement.pdf   — third-party appraisal with building specs
  09_email_thread_updates.pdf   — forwarded email chain with scattered corrections

Run from backend/:
    python tests/_gen_mixed_intake_docs.py
"""
from pathlib import Path
from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.platypus import (SimpleDocTemplate, Table, TableStyle, Paragraph,
                                 Spacer, HRFlowable, KeepTogether)
from reportlab.lib.enums import TA_LEFT, TA_CENTER, TA_RIGHT

OUT = Path(__file__).resolve().parent.parent / "test_files"
HEADER_COLOR = colors.HexColor("#1F4E79")
LIGHT_BLUE   = colors.HexColor("#EBF3FB")
ORANGE       = colors.HexColor("#C55A11")
GRAY         = colors.HexColor("#595959")

styles = getSampleStyleSheet()

def h1(text):   return Paragraph(f"<b>{text}</b>", ParagraphStyle("h1", fontSize=14, textColor=HEADER_COLOR, spaceAfter=4))
def h2(text):   return Paragraph(f"<b>{text}</b>", ParagraphStyle("h2", fontSize=10, textColor=HEADER_COLOR, spaceAfter=2))
def body(text): return Paragraph(text, ParagraphStyle("body", fontSize=8, leading=11, spaceAfter=2))
def small(text):return Paragraph(text, ParagraphStyle("small", fontSize=7, leading=10, textColor=GRAY))
def bold(text): return Paragraph(f"<b>{text}</b>", ParagraphStyle("bold", fontSize=8, leading=11))
def hr():       return HRFlowable(width="100%", thickness=0.5, color=colors.HexColor("#AAAAAA"), spaceAfter=4, spaceBefore=4)

# ─── Doc 07: Customer Property Intake / Questionnaire ────────────────────────

def build_intake_form():
    doc = SimpleDocTemplate(str(OUT / "07_customer_intake_form.pdf"),
                            pagesize=letter,
                            leftMargin=0.75*inch, rightMargin=0.75*inch,
                            topMargin=0.75*inch, bottomMargin=0.75*inch)
    story = []

    story.append(h1("COMMERCIAL PROPERTY — SUPPLEMENTAL INTAKE QUESTIONNAIRE"))
    story.append(body("Named Insured: <b>Harborview Property Management LLC</b>    |    "
                      "Policy Effective: <b>07/01/2026</b>    |    "
                      "Agent: <b>Coastal Risk Partners</b>    |    Date: <b>03/15/2026</b>"))
    story.append(hr())
    story.append(body("Please complete this form for each insured location. "
                      "This information supplements the Schedule of Values and will be used for underwriting."))
    story.append(Spacer(1, 0.1*inch))

    # 8 locations with rich supplemental data
    locations = [
        {
            "loc": "1", "bldg": "1", "name": "Harborview Tower", "address": "100 Main St, Chicago, IL 60601",
            "occupancy": "Office", "flood_zone": "X", "eq_zone": "2",
            "pct_occupied": "92%", "basement": "Yes", "roof_shape": "Flat",
            "fire_alarm": "Yes", "burglar_alarm": "Yes", "smoke_detectors": "Yes",
            "distance_coast": "650 miles", "owned": "Owned",
            "maintenance": "Good", "pct_sub": "0%", "pct_stu": "0%", "pct_eld": "0%",
            "exterior": "Glass Curtain Wall", "iso_pc": "3",
        },
        {
            "loc": "2", "bldg": "2", "name": "Bayfront Retail Center", "address": "137 Oak Ave, Houston, TX 77001",
            "occupancy": "Retail", "flood_zone": "AE", "eq_zone": "1",
            "pct_occupied": "78%", "basement": "No", "roof_shape": "Gable",
            "fire_alarm": "Yes", "burglar_alarm": "Partial", "smoke_detectors": "Yes",
            "distance_coast": "50 miles", "owned": "Leased",
            "maintenance": "Average", "pct_sub": "0%", "pct_stu": "0%", "pct_eld": "0%",
            "exterior": "Brick", "iso_pc": "5",
        },
        {
            "loc": "3", "bldg": "3", "name": "Desert Warehouse Complex", "address": "174 Commerce Blvd, Phoenix, AZ 85001",
            "occupancy": "Warehouse", "flood_zone": "X", "eq_zone": "4",
            "pct_occupied": "100%", "basement": "No", "roof_shape": "Shed",
            "fire_alarm": "Yes", "burglar_alarm": "Yes", "smoke_detectors": "No",
            "distance_coast": "300 miles", "owned": "Owned",
            "maintenance": "Good", "pct_sub": "0%", "pct_stu": "0%", "pct_eld": "0%",
            "exterior": "Metal Panel", "iso_pc": "4",
        },
        {
            "loc": "4", "bldg": "4", "name": "Market Street Office", "address": "211 Market St, Philadelphia, PA 19101",
            "occupancy": "Office", "flood_zone": "A", "eq_zone": "2",
            "pct_occupied": "85%", "basement": "Yes", "roof_shape": "Flat",
            "fire_alarm": "Yes", "burglar_alarm": "Yes", "smoke_detectors": "Yes",
            "distance_coast": "120 miles", "owned": "Owned",
            "maintenance": "Good", "pct_sub": "0%", "pct_stu": "0%", "pct_eld": "15%",
            "exterior": "Concrete Block", "iso_pc": "3",
        },
        {
            "loc": "5", "bldg": "5", "name": "Riverwalk Apartments", "address": "248 Harbor Dr, San Antonio, TX 78201",
            "occupancy": "Apartment", "flood_zone": "AE", "eq_zone": "1",
            "pct_occupied": "95%", "basement": "No", "roof_shape": "Hip",
            "fire_alarm": "Yes", "burglar_alarm": "No", "smoke_detectors": "Yes",
            "distance_coast": "180 miles", "owned": "Owned",
            "maintenance": "Average", "pct_sub": "22%", "pct_stu": "0%", "pct_eld": "8%",
            "exterior": "Brick", "iso_pc": "5",
        },
        {
            "loc": "6", "bldg": "6", "name": "Gaslamp Mixed Use", "address": "285 Industrial Pkwy, San Diego, CA 92101",
            "occupancy": "Mixed Use", "flood_zone": "X500", "eq_zone": "5",
            "pct_occupied": "88%", "basement": "No", "roof_shape": "Flat",
            "fire_alarm": "Yes", "burglar_alarm": "Yes", "smoke_detectors": "Yes",
            "distance_coast": "0.5 miles", "owned": "Owned",
            "maintenance": "Good", "pct_sub": "0%", "pct_stu": "18%", "pct_eld": "0%",
            "exterior": "EIFS/Stucco", "iso_pc": "2",
        },
        {
            "loc": "7", "bldg": "7", "name": "Uptown Restaurant Row", "address": "322 River Rd, Dallas, TX 75201",
            "occupancy": "Restaurant", "flood_zone": "X", "eq_zone": "1",
            "pct_occupied": "100%", "basement": "No", "roof_shape": "Gable",
            "fire_alarm": "Yes", "burglar_alarm": "Partial", "smoke_detectors": "Yes",
            "distance_coast": "400 miles", "owned": "Leased",
            "maintenance": "Average", "pct_sub": "0%", "pct_stu": "0%", "pct_eld": "0%",
            "exterior": "Brick", "iso_pc": "4",
        },
        {
            "loc": "8", "bldg": "8", "name": "Southside Medical Plaza", "address": "359 Market St, Jacksonville, FL 32099",
            "occupancy": "Medical Office", "flood_zone": "VE", "eq_zone": "1",
            "pct_occupied": "90%", "basement": "No", "roof_shape": "Hip",
            "fire_alarm": "Yes", "burglar_alarm": "Yes", "smoke_detectors": "Yes",
            "distance_coast": "2 miles", "owned": "Owned",
            "maintenance": "Good", "pct_sub": "0%", "pct_stu": "0%", "pct_eld": "30%",
            "exterior": "Concrete Block", "iso_pc": "2",
        },
    ]

    for loc in locations:
        story.append(KeepTogether([
            h2(f"Location {loc['loc']} — {loc['name']}"),
            body(f"<b>Address:</b> {loc['address']}    "
                 f"<b>Occupancy:</b> {loc['occupancy']}"),
            Spacer(1, 0.05*inch),
        ]))

        tbl_data = [
            ["Field", "Response", "Field", "Response"],
            ["Flood Zone", loc["flood_zone"], "EQ Zone", loc["eq_zone"]],
            ["% Occupied", loc["pct_occupied"], "Basement", loc["basement"]],
            ["Roof Shape", loc["roof_shape"], "ISO Protection Class", loc["iso_pc"]],
            ["Fire Alarm", loc["fire_alarm"], "Burglar Alarm", loc["burglar_alarm"]],
            ["Smoke Detectors", loc["smoke_detectors"], "Distance to Salt Water/Coast", loc["distance_coast"]],
            ["Property Owned or Managed", loc["owned"], "Bldg Maintenance", loc["maintenance"]],
            ["% Subsidized", loc["pct_sub"], "% Student Housing", loc["pct_stu"]],
            ["% Elderly Housing", loc["pct_eld"], "Predominant Exterior Wall / Cladding", loc["exterior"]],
        ]

        tbl = Table(tbl_data, colWidths=[2.0*inch, 1.6*inch, 2.4*inch, 1.6*inch])
        tbl.setStyle(TableStyle([
            ("BACKGROUND",  (0, 0), (-1, 0),  HEADER_COLOR),
            ("TEXTCOLOR",   (0, 0), (-1, 0),  colors.white),
            ("FONTNAME",    (0, 0), (-1, 0),  "Helvetica-Bold"),
            ("FONTSIZE",    (0, 0), (-1, -1), 7.5),
            ("FONTNAME",    (0, 1), (0, -1),  "Helvetica-Bold"),
            ("FONTNAME",    (2, 1), (2, -1),  "Helvetica-Bold"),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, LIGHT_BLUE]),
            ("GRID",        (0, 0), (-1, -1), 0.3, colors.HexColor("#AAAAAA")),
            ("VALIGN",      (0, 0), (-1, -1), "MIDDLE"),
            ("PADDING",     (0, 0), (-1, -1), 4),
        ]))
        story += [tbl, Spacer(1, 0.12*inch)]

    story.append(hr())
    story.append(small("Signature: ______________________________    Date: ____________    "
                        "Agent License #: CA-2891047"))
    doc.build(story)
    print(f"Generated: 07_customer_intake_form.pdf  ({len(locations)} locations)")


# ─── Doc 08: Third-Party Appraisal Supplement ────────────────────────────────

def build_appraisal_supplement():
    doc = SimpleDocTemplate(str(OUT / "08_appraisal_supplement.pdf"),
                            pagesize=letter,
                            leftMargin=0.75*inch, rightMargin=0.75*inch,
                            topMargin=0.75*inch, bottomMargin=0.75*inch)
    story = []

    story.append(h1("PROPERTY APPRAISAL SUPPLEMENT — BUILDING SPECIFICATIONS"))
    story.append(body("Prepared by: <b>National Appraisal Group</b>    |    "
                      "Client: <b>Harborview Property Management LLC</b>    |    "
                      "Inspection Date: <b>February 2026</b>"))
    story.append(hr())
    story.append(body("The following building specifications were gathered during on-site inspection "
                      "and supplement the Schedule of Values for underwriting purposes."))
    story.append(Spacer(1, 0.1*inch))

    story.append(h2("BUILDING SPECIFICATIONS TABLE"))
    story.append(Spacer(1, 0.05*inch))

    headers = ["Loc #", "Location Name", "ISO Construction\nCode", "# of Stories",
               "# of Units", "Type of Wiring", "Roof Type/Frame", "Cost Per\nSq Ft",
               "Machinery &\nEquipment Values", "Other Property\nValues"]

    data = [headers] + [
        ["1", "Harborview Tower",        "6", "22", "N/A",  "Copper",     "Steel Truss",  "$312.50", "$1,250,000", "$180,000"],
        ["2", "Bayfront Retail Center",  "4", "2",  "N/A",  "Copper",     "Metal Deck",   "$195.00", "$320,000",   "N/A"],
        ["3", "Desert Warehouse Complex","3", "1",  "N/A",  "Aluminum",   "Metal Deck",   "$88.00",  "$2,100,000", "$95,000"],
        ["4", "Market Street Office",    "4", "8",  "N/A",  "Copper",     "Wood Truss",   "$245.00", "$410,000",   "N/A"],
        ["5", "Riverwalk Apartments",    "2", "4",  "48",   "Copper",     "Wood Frame",   "$175.00", "N/A",        "N/A"],
        ["6", "Gaslamp Mixed Use",       "3", "6",  "12",   "Copper",     "Concrete",     "$290.00", "$180,000",   "$55,000"],
        ["7", "Uptown Restaurant Row",   "2", "1",  "N/A",  "Knob & Tube","Wood Truss",  "$210.00", "$480,000",   "N/A"],
        ["8", "Southside Medical Plaza", "5", "3",  "N/A",  "Copper",     "Steel Truss",  "$380.00", "$950,000",   "$120,000"],
    ]

    col_w = [0.45*inch, 1.7*inch, 0.8*inch, 0.6*inch, 0.55*inch,
             0.75*inch, 0.85*inch, 0.65*inch, 0.95*inch, 0.85*inch]
    tbl = Table(data, colWidths=col_w, repeatRows=1)
    tbl.setStyle(TableStyle([
        ("BACKGROUND",   (0, 0), (-1, 0),  HEADER_COLOR),
        ("TEXTCOLOR",    (0, 0), (-1, 0),  colors.white),
        ("FONTNAME",     (0, 0), (-1, 0),  "Helvetica-Bold"),
        ("FONTSIZE",     (0, 0), (-1, -1), 7),
        ("FONTNAME",     (0, 1), (-1, -1), "Helvetica"),
        ("ROWBACKGROUNDS",(0,1), (-1,-1),  [colors.white, LIGHT_BLUE]),
        ("GRID",         (0, 0), (-1, -1), 0.3, colors.HexColor("#AAAAAA")),
        ("VALIGN",       (0, 0), (-1, -1), "MIDDLE"),
        ("ALIGN",        (2, 0), (-1, -1), "CENTER"),
        ("PADDING",      (0, 0), (-1, -1), 4),
    ]))
    story += [tbl, Spacer(1, 0.15*inch)]

    story.append(h2("APPRAISER NOTES"))
    story.append(body("• Location 1 (Harborview Tower): 22-story Class A office with full sprinkler system, "
                      "backup generator, and card-access security. Recent lobby renovation completed 2024."))
    story.append(body("• Location 3 (Desert Warehouse): Clear-span steel structure, dock-high loading doors. "
                      "Aluminum wiring documented — recommend upgrading to copper within 24 months."))
    story.append(body("• Location 5 (Riverwalk Apartments): Wood-frame construction, 48 units total. "
                      "Pool and fitness center included in Other Property Values."))
    story.append(body("• Location 7 (Uptown Restaurant Row): Knob-and-tube wiring identified in kitchen area. "
                      "Owner aware; partial replacement estimated for Q3 2026."))
    story.append(body("• Location 8 (Southside Medical Plaza): Specialized medical equipment (MRI, CT scanner) "
                      "accounted for in Machinery & Equipment Values figure above."))

    story.append(Spacer(1, 0.1*inch))
    story.append(hr())
    story.append(small("Report #NAG-2026-0314  |  Appraiser: J. Whitmore, MAI  |  "
                        "Cert #: FL-CGA-001847  |  This report is for insurance underwriting purposes only."))
    doc.build(story)
    print(f"Generated: 08_appraisal_supplement.pdf  (8 locations)")


# ─── Doc 09: Email Thread (forwarded chain) ──────────────────────────────────

def build_email_thread():
    doc = SimpleDocTemplate(str(OUT / "09_email_thread_updates.pdf"),
                            pagesize=letter,
                            leftMargin=0.75*inch, rightMargin=0.75*inch,
                            topMargin=0.75*inch, bottomMargin=0.75*inch)
    story = []

    story.append(h1("FORWARDED EMAIL THREAD — PROPERTY UPDATE CORRESPONDENCE"))
    story.append(small("Printed for file by: Sarah Chen, Coastal Risk Partners  |  03/20/2026"))
    story.append(hr())

    email_style = ParagraphStyle("email", fontSize=8, leading=12, leftIndent=0)
    from_style  = ParagraphStyle("from", fontSize=8, leading=11, textColor=HEADER_COLOR, fontName="Helvetica-Bold")
    quote_style = ParagraphStyle("quote", fontSize=7.5, leading=11, leftIndent=16, textColor=GRAY)

    def email_block(sender, to, date, subject, body_lines, quoted_lines=None):
        blk = []
        blk.append(Paragraph(f"From: {sender}", from_style))
        blk.append(Paragraph(f"To: {to}", email_style))
        blk.append(Paragraph(f"Date: {date}", email_style))
        blk.append(Paragraph(f"Subject: {subject}", email_style))
        blk.append(Spacer(1, 0.04*inch))
        for line in body_lines:
            blk.append(Paragraph(line, email_style))
        if quoted_lines:
            blk.append(Spacer(1, 0.03*inch))
            for line in quoted_lines:
                blk.append(Paragraph(f"> {line}", quote_style))
        blk.append(hr())
        return blk

    # Email 1 — most recent, top of chain
    story += email_block(
        sender="Tom Ruiz <t.ruiz@harborviewpm.com>",
        to="Sarah Chen <s.chen@coastalrisk.com>",
        date="March 20, 2026 — 9:14 AM",
        subject="RE: RE: Harborview portfolio renewal — final corrections",
        body_lines=[
            "Hi Sarah,",
            "",
            "One last thing — I pulled the flood certs this morning. Location 2 (Bayfront Retail) "
            "was incorrectly mapped last year, it's actually Flood Zone AE not X. Our surveyor "
            "confirmed with the updated FEMA panel. Please make sure underwriting has this.",
            "",
            "Also Location 8 (Southside Medical) just passed their sprinkler inspection — "
            "100% sprinklered now, not the 80% we submitted. The % Sprinklered should read 100%.",
            "",
            "Everything else in Mike's email below looks right. The wiring on Location 7 is "
            "still Knob & Tube — the renovation is scheduled but NOT complete yet, so keep it as-is.",
            "",
            "Thanks,",
            "Tom Ruiz | Director of Risk Management | Harborview Property Management",
            "p: 312-555-0192",
        ],
        quoted_lines=[
            "From: Mike Harrington <m.harrington@harborviewpm.com>",
            "Sent: March 19, 2026 4:51 PM",
            "Subject: RE: Harborview portfolio renewal — final corrections",
            "",
            "Sarah — corrections for the submission:",
            "  - Loc 1 (Harborview Tower): % Sprinklered should be 100%, not 90%",
            "  - Loc 3 (Desert Warehouse): Year Built is 1998, not 1995 as previously submitted",
            "  - Loc 5 (Riverwalk): EQ Zone is Zone 2 per our recent seismic study (not Zone 1)",
            "  - Loc 6 (Gaslamp): distance to coast is 0.3 miles, we're right on the harbor",
            "  - Loc 7 (Uptown Restaurant): Roof Update was 2021, Wiring/HVAC/Plumbing Update 2021 as well",
        ]
    )

    # Email 2
    story += email_block(
        sender="Sarah Chen <s.chen@coastalrisk.com>",
        to="Tom Ruiz <t.ruiz@harborviewpm.com>; Mike Harrington <m.harrington@harborviewpm.com>",
        date="March 18, 2026 — 2:30 PM",
        subject="RE: Harborview portfolio renewal — final corrections",
        body_lines=[
            "Tom, Mike,",
            "",
            "Received the updated SOV. A few questions before I submit to underwriting:",
            "",
            "1. Location 4 (Market Street) — the square footage shows 18,500 sq ft but "
            "the appraisal has 19,200. Which is correct for the submission?",
            "2. Location 6 — is the EQ Zone 5 (per appraiser) or Zone 4? The two documents conflict.",
            "3. Loc 8 — you have TIV at $4,850,000 but the breakdown adds to $4,920,000. "
            "Should we use the sum or the stated TIV?",
            "",
            "Please advise by EOD Thursday.",
            "Sarah",
        ]
    )

    # Email 3
    story += email_block(
        sender="Mike Harrington <m.harrington@harborviewpm.com>",
        to="Sarah Chen <s.chen@coastalrisk.com>",
        date="March 18, 2026 — 4:51 PM",
        subject="RE: Harborview portfolio renewal — final corrections",
        body_lines=[
            "Sarah —",
            "",
            "Quick answers:",
            "1. Location 4 square footage: use 19,200 sq ft — the appraisal is the updated figure.",
            "2. Location 6 EQ Zone: Zone 5 per the appraiser is correct. The older doc had an error.",
            "3. Location 8 TIV: use the stated $4,850,000 — the component breakdown "
            "includes some equipment we're insuring separately.",
            "",
            "Also, I forgot to mention — Location 1 (Harborview Tower) roof was last updated 2022, "
            "not 2020. And for Loc 4 (Market Street), the ISO Protection Class is 3.",
            "",
            "Mike",
        ]
    )

    # Email 4 — original
    story += email_block(
        sender="Tom Ruiz <t.ruiz@harborviewpm.com>",
        to="Sarah Chen <s.chen@coastalrisk.com>",
        date="March 15, 2026 — 10:05 AM",
        subject="Harborview portfolio renewal — property details",
        body_lines=[
            "Sarah,",
            "",
            "Attached is our updated property schedule for the 2026 renewal. "
            "A few things I want to flag that aren't in the spreadsheet:",
            "",
            "• Location 2 (Bayfront Retail): There is a basement storage area — "
            "Basement should be Yes, not No.",
            "• Location 5 (Riverwalk): The property is 35% subsidized housing under "
            "the city affordability program.",
            "• Location 8: We added a backup generator last year, included in M&E values. "
            "The burglar alarm is central station monitored.",
            "",
            "Let me know if you need anything else.",
            "Tom",
        ]
    )

    doc.build(story)
    print(f"Generated: 09_email_thread_updates.pdf  (corrections for 8 locations)")


# ─── Run all ──────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    build_intake_form()
    build_appraisal_supplement()
    build_email_thread()
    print("\nAll 3 documents generated in test_files/")
