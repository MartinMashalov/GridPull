"""
Generate a synthetic full-coverage SOV PDF with all 46 fields filled for 20 locations.
This is used to test that extraction fills 100% of the spreadsheet.

Run from backend/:
    python tests/_gen_full_sov_pdf.py
"""
import random
from pathlib import Path
from reportlab.lib import colors
from reportlab.lib.pagesizes import landscape, A3
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
from reportlab.lib.enums import TA_CENTER

random.seed(42)

OUT = Path(__file__).resolve().parent.parent / "test_files" / "06_full_sov_20_locations.pdf"

# ── Synthetic data ─────────────────────────────────────────────────────────────

STREETS = ["Main St", "Oak Ave", "Commerce Blvd", "Industrial Pkwy", "Harbor Dr",
           "Market St", "River Rd", "Pine Ave", "Elm St", "Maple Blvd"]
CITIES  = [("Chicago","IL","60601","Cook"), ("Houston","TX","77001","Harris"),
           ("Phoenix","AZ","85001","Maricopa"), ("Philadelphia","PA","19101","Philadelphia"),
           ("San Antonio","TX","78201","Bexar"), ("San Diego","CA","92101","San Diego"),
           ("Dallas","TX","75201","Dallas"), ("Jacksonville","FL","32099","Duval"),
           ("Austin","TX","78701","Travis"), ("Fort Worth","TX","76101","Tarrant"),
           ("Columbus","OH","43085","Franklin"), ("Charlotte","NC","28201","Mecklenburg"),
           ("Indianapolis","IN","46201","Marion"), ("San Francisco","CA","94101","San Francisco"),
           ("Seattle","WA","98101","King"), ("Denver","CO","80201","Denver"),
           ("Nashville","TN","37201","Davidson"), ("Oklahoma City","OK","73101","Oklahoma"),
           ("El Paso","TX","79901","El Paso"), ("Boston","MA","02101","Suffolk")]
OCCUPANCIES = ["Office","Retail","Warehouse","Manufacturing","Apartment","Mixed Use",
                "Restaurant","Hotel","Medical Office","Church"]
CONSTRUCTION = ["Frame","Joisted Masonry","Non-Combustible","Masonry Non-Combustible",
                "Modified Fire Resistive","Fire Resistive"]
ISO_CODES    = ["1","2","3","4","5","6"]
ROOF_TYPES   = ["Flat","Gable","Hip","Mansard","Shed"]
ROOF_FRAMES  = ["Wood Truss","Steel Truss","Concrete","Metal Deck","Wood Frame"]
FLOOD_ZONES  = ["X","AE","A","X500","VE","AO"]
EQ_ZONES     = ["1","2","3","4","5"]
ALARM_VALS   = ["Yes","No","Partial"]
OWNED_VALS   = ["Owned","Leased","Managed"]
MAINTENANCE  = ["Good","Average","Fair","Poor"]
WIRING_TYPES = ["Copper","Aluminum","Knob & Tube","Mixed"]
EXTERIOR     = ["Brick","Concrete Block","Metal Panel","EIFS/Stucco","Glass Curtain Wall","Wood Siding"]

def rand_addr(i):
    return f"{100 + i * 37} {STREETS[i % len(STREETS)]}"

def make_row(i):
    city, state, zip_, county = CITIES[i]
    constr = CONSTRUCTION[i % len(CONSTRUCTION)]
    iso_c  = ISO_CODES[i % len(ISO_CODES)]
    bldg_val  = random.randint(500_000, 10_000_000)
    cont_val  = random.randint(50_000, 2_000_000)
    bi_val    = random.randint(100_000, 3_000_000)
    mach_val  = random.randint(0, 500_000) if i % 3 == 0 else 0
    other_val = random.randint(0, 200_000) if i % 4 == 0 else 0
    tiv       = bldg_val + cont_val + bi_val + mach_val + other_val
    sqft      = random.randint(2_000, 80_000)
    cost_psf  = round(bldg_val / sqft, 2)
    yr_built  = random.randint(1960, 2020)
    upd_yr    = random.randint(yr_built + 1, 2024)
    stories   = random.randint(1, 20)
    units     = random.randint(0, 200) if OCCUPANCIES[i % len(OCCUPANCIES)] == "Apartment" else 0
    pct_occ   = f"{random.randint(70, 100)}%"
    sprink    = "Yes" if i % 3 != 0 else "No"
    pct_sp    = f"{random.randint(0, 100)}%" if sprink == "Yes" else "0%"
    iso_pc    = str(random.randint(1, 10))
    flood     = FLOOD_ZONES[i % len(FLOOD_ZONES)]
    eq        = EQ_ZONES[i % len(EQ_ZONES)]
    dist_sw   = f"{random.randint(1, 100)} miles"
    pct_sub   = f"{random.randint(0, 30)}%" if i % 5 == 0 else "0%"
    pct_stu   = f"{random.randint(0, 20)}%" if i % 6 == 0 else "0%"
    pct_eld   = f"{random.randint(0, 40)}%" if i % 7 == 0 else "0%"
    basement  = "Yes" if i % 2 == 0 else "No"

    return [
        str(i + 1),                          # Loc #
        str(i + 1),                          # Bldg #
        f"Location {i+1}",                   # Location Name
        OCCUPANCIES[i % len(OCCUPANCIES)],   # Occupancy/Exposure
        rand_addr(i),                        # Street Address
        city, state, zip_, county,           # City, State, Zip, County
        constr, iso_c,                       # Construction Type, ISO Construction Code
        f"${bldg_val:,}",                   # Building Values
        f"${cont_val:,}",                   # Contents/BPP Values
        f"${bi_val:,}",                     # Business Income Values
        f"${mach_val:,}" if mach_val else "N/A",  # Machinery & Equipment Values
        f"${other_val:,}" if other_val else "N/A", # Other Property Values
        f"${tiv:,}",                         # Total Insurable Value (TIV)
        f"{sqft:,}",                         # Square Ft.
        f"${cost_psf:,.2f}",                # Cost Per Square Ft.
        str(yr_built),                       # Year Built
        str(upd_yr),                         # Roof Update
        str(upd_yr),                         # Wiring Update
        str(upd_yr),                         # HVAC Update
        str(upd_yr),                         # Plumbing Update
        pct_occ,                             # % Occupied
        sprink,                              # Sprinklered
        pct_sp,                              # % Sprinklered
        iso_pc,                              # ISO Protection Class
        ALARM_VALS[i % 3],                   # Fire Alarm
        ALARM_VALS[(i+1) % 3],              # Burglar Alarm
        ALARM_VALS[(i+2) % 3],              # Smoke Detectors
        str(stories),                        # # of Stories
        str(units) if units else "N/A",      # # of Units
        WIRING_TYPES[i % len(WIRING_TYPES)],# Type of Wiring
        pct_sub,                             # % Subsidized
        pct_stu,                             # % Student Housing
        pct_eld,                             # % Elderly Housing
        ROOF_FRAMES[i % len(ROOF_FRAMES)],  # Roof Type/Frame
        ROOF_TYPES[i % len(ROOF_TYPES)],    # Roof Shape
        flood,                               # Flood Zone
        eq,                                  # EQ Zone
        dist_sw,                             # Distance to Salt Water/Coast
        OWNED_VALS[i % len(OWNED_VALS)],    # Property Owned or Managed
        MAINTENANCE[i % len(MAINTENANCE)],  # Bldg Maintenance
        basement,                            # Basement
        EXTERIOR[i % len(EXTERIOR)],        # Predominant Exterior Wall / Cladding
    ]

# ── Column headers (exactly matching the 46 extraction field names) ────────────
HEADERS = [
    "Loc #", "Bldg #", "Location Name", "Occupancy/Exposure",
    "Street Address", "City", "State", "Zip", "County",
    "Construction Type", "ISO Construction Code",
    "Building Values", "Contents/BPP Values", "Business Income Values",
    "Machinery & Equipment Values", "Other Property Values",
    "Total Insurable Value (TIV)",
    "Square Ft.", "Cost Per Square Ft.", "Year Built",
    "Roof Update", "Wiring Update", "HVAC Update", "Plumbing Update",
    "% Occupied", "Sprinklered", "% Sprinklered", "ISO Protection Class",
    "Fire Alarm", "Burglar Alarm", "Smoke Detectors",
    "# of Stories", "# of Units", "Type of Wiring",
    "% Subsidized", "% Student Housing", "% Elderly Housing",
    "Roof Type/Frame", "Roof Shape", "Flood Zone", "EQ Zone",
    "Distance to Salt Water/Coast", "Property Owned or Managed",
    "Bldg Maintenance", "Basement", "Predominant Exterior Wall / Cladding",
]

N_LOCS = 20
rows = [make_row(i) for i in range(N_LOCS)]

# ── PDF layout — split columns across two pages for readability ────────────────

def build_pdf():
    doc = SimpleDocTemplate(
        str(OUT),
        pagesize=landscape(A3),
        leftMargin=0.4*inch, rightMargin=0.4*inch,
        topMargin=0.5*inch, bottomMargin=0.5*inch,
    )
    styles = getSampleStyleSheet()
    title_style = styles["Title"]
    title_style.fontSize = 14

    story = []

    # Title page header
    story.append(Paragraph("Complete Property Schedule of Values — 20 Locations", title_style))
    story.append(Paragraph("Acme Commercial Property Group | Policy Year 2026 | All 46 Fields", styles["Normal"]))
    story.append(Spacer(1, 0.2*inch))

    # Split into two column groups for readability
    col_splits = [
        list(range(0, 23)),   # first 23 fields
        list(range(23, 46)),  # remaining 23 fields — always include Loc # (col 0) as anchor
    ]

    HEADER_COLOR = colors.HexColor("#1F4E79")
    ALT_COLOR    = colors.HexColor("#EBF3FB")

    for split_idx, col_indices in enumerate(col_splits):
        # Always prepend Loc # as anchor column for second half
        if split_idx == 1:
            col_indices = [0] + col_indices

        sub_headers = [HEADERS[c] for c in col_indices]
        sub_rows    = [[r[c] for c in col_indices] for r in rows]

        table_data = [sub_headers] + sub_rows
        n_cols = len(col_indices)
        col_width = (11.5 * inch) / n_cols

        tbl = Table(table_data, colWidths=[col_width] * n_cols, repeatRows=1)
        tbl.setStyle(TableStyle([
            ("BACKGROUND",   (0, 0), (-1, 0),  HEADER_COLOR),
            ("TEXTCOLOR",    (0, 0), (-1, 0),  colors.white),
            ("FONTNAME",     (0, 0), (-1, 0),  "Helvetica-Bold"),
            ("FONTSIZE",     (0, 0), (-1, 0),  6),
            ("FONTNAME",     (0, 1), (-1, -1), "Helvetica"),
            ("FONTSIZE",     (0, 1), (-1, -1), 6),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, ALT_COLOR]),
            ("GRID",         (0, 0), (-1, -1), 0.25, colors.HexColor("#AAAAAA")),
            ("ALIGN",        (0, 0), (-1, -1), "LEFT"),
            ("VALIGN",       (0, 0), (-1, -1), "MIDDLE"),
            ("PADDING",      (0, 0), (-1, -1), 2),
            ("WORDWRAP",     (0, 0), (-1, -1), True),
        ]))

        label = "Fields 1–23" if split_idx == 0 else "Fields 24–46 (with Loc # anchor)"
        story.append(Paragraph(f"<b>{label}</b>", styles["Normal"]))
        story.append(Spacer(1, 0.05*inch))
        story.append(tbl)
        story.append(Spacer(1, 0.3*inch))

    doc.build(story)
    print(f"Generated: {OUT}")
    print(f"  {N_LOCS} locations × {len(HEADERS)} fields")

if __name__ == "__main__":
    build_pdf()
