"""Debug the fleet_schedule_18_vehicles.pdf dedup issue."""
import asyncio, sys, os, json
sys.path.insert(0, os.path.dirname(__file__))
sys.stdout.reconfigure(line_buffering=True)

import logging
logging.basicConfig(level=logging.DEBUG, format="%(levelname)s %(name)s: %(message)s")
logging.getLogger("httpx").setLevel(logging.ERROR)
logging.getLogger("httpcore").setLevel(logging.ERROR)
logging.getLogger("openai").setLevel(logging.WARNING)

# Only show our extraction/llm logs at DEBUG, everything else at INFO
logging.getLogger("app.services.extraction.llm").setLevel(logging.DEBUG)
logging.getLogger("app.services.extraction").setLevel(logging.INFO)
logging.getLogger("app.services.sov").setLevel(logging.INFO)
logging.getLogger("app.services.llm_router").setLevel(logging.INFO)
logging.getLogger("app.services.pdf_service").setLevel(logging.INFO)

from app.config import settings
settings.mistral_api_key = ""  # skip OCR

from app.services.pdf_service import parse_pdf
from app.services.extraction import extract_from_document, LLMUsage
from app.services.extraction.llm import (
    _infer_schedule_key_fields,
    _merge_rows_by_identifier,
    finalize_property_schedule_rows,
)

VEHICLE_FIELDS = [
    {"name": "Vehicle #", "description": "Vehicle number or unit number"},
    {"name": "Year", "description": "Model year of the vehicle"},
    {"name": "Make", "description": "Vehicle manufacturer"},
    {"name": "Model", "description": "Vehicle model name"},
    {"name": "VIN", "description": "Vehicle identification number"},
    {"name": "Value", "description": "Stated or insured value", "numeric": True},
    {"name": "Garage Location", "description": "Where the vehicle is garaged"},
]

async def main():
    f = "/Users/martinmashalov/Downloads/GridPull/test_documents/12_sov_email_examples/fleet_schedule_18_vehicles.pdf"
    fn = [fld["name"] for fld in VEHICLE_FIELDS]

    doc = await asyncio.to_thread(parse_pdf, f, os.path.basename(f))
    print(f"Parsed: {doc.page_count} pages, tables={len(doc.tables)}")

    # Show what the document text looks like
    print(f"\n--- Document text (first 2000 chars) ---")
    text = doc.content_text or ""
    print(text[:2000])
    print(f"\n--- Tables ---")
    for t in doc.tables:
        print(f"Table page {t.page_num}: {t.row_count}x{t.col_count}")
        print(t.markdown[:500])
        print()

    # Run raw SOV extraction (before finalize)
    from app.services.sov import extract_sov_from_document
    usage = LLMUsage()
    raw_rows = await extract_sov_from_document(doc, VEHICLE_FIELDS, usage, "")
    print(f"\n=== RAW SOV OUTPUT (before any dedup): {len(raw_rows)} rows ===")
    for i, r in enumerate(raw_rows):
        vals = {k: str(v)[:30] for k, v in r.items() if k not in ("_source_file", "_error") and v is not None}
        print(f"  Raw {i+1}: {json.dumps(vals, default=str)[:200]}")

    # Now run full pipeline
    usage2 = LLMUsage()
    rows = await extract_from_document(doc, VEHICLE_FIELDS, usage2, force_sov=True)

    print(f"\n=== FINAL RESULT: {len(rows)} rows ===")
    for i, r in enumerate(rows):
        vals = {k: v for k, v in r.items() if k not in ("_source_file", "_error")}
        print(f"  Row {i+1}: {json.dumps(vals, default=str)}")

    # Now test the dedup steps in isolation
    print(f"\n=== DEDUP ANALYSIS ===")
    id_field, addr_field = _infer_schedule_key_fields(rows, fn)
    print(f"Inferred ID field: {id_field}")
    print(f"Inferred addr field: {addr_field}")

    # Check what merge keys look like
    import re
    def _norm(v): return str(v or "").strip().lower()
    def _base_num(v):
        tokens = re.findall(r"[A-Za-z0-9#/_-]+", v.strip())
        for token in tokens:
            if any(ch.isdigit() for ch in token): return token
        return tokens[0] if tokens else v[:20]

    print(f"\nMerge keys for each row:")
    for i, r in enumerate(rows):
        parts = []
        if id_field and r.get(id_field):
            parts.append(_base_num(_norm(r.get(id_field))))
        if addr_field and r.get(addr_field):
            parts.append(_norm(r.get(addr_field))[:40])
        key = "|".join(parts) if parts else None
        print(f"  Row {i+1}: key={key!r}  Vehicle#={r.get('Vehicle #')!r}  VIN={r.get('VIN')!r}")

if __name__ == "__main__":
    asyncio.run(main())
