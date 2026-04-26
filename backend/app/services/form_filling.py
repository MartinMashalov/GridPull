import os
import io
import json
import base64
import logging
import asyncio
import re
import tempfile
from email import policy
from email.parser import BytesParser
from html import unescape
from mistralai import Mistral
from pypdf import PdfReader, PdfWriter
import fitz  # PyMuPDF — used for OCR-free visible-label extraction

from app.services.llm_router import routed_acompletion
from app.config import settings

logger = logging.getLogger(__name__)

_MIN_PYPDF_TEXT_LEN = 200
_OCR_MAX_RETRIES = 3
_OCR_RETRY_BACKOFF = [1, 3, 6]
_OCR_MAX_FILE_SIZE = 1_000_000
_MAX_SOURCE_PAGES = 40  # cap pages read/OCR'd per source PDF


# ─── OCR ───────────────────────────────────────────────────────────────────────

def _extract_text_pypdf(file_bytes: bytes, max_pages: int = _MAX_SOURCE_PAGES) -> str:
    try:
        reader = PdfReader(io.BytesIO(file_bytes))
        pages = []
        for page in reader.pages[:max_pages]:
            t = page.extract_text() or ""
            if t.strip():
                pages.append(t)
        return "\n\n".join(pages)
    except Exception as e:
        logger.debug("[PYPDF] %s", e)
        return ""


class MistralOCR:
    async def extract_text_async(self, file_bytes: bytes, mime_type: str = "application/pdf") -> str:
        if mime_type == "application/pdf" and len(file_bytes) > _OCR_MAX_FILE_SIZE:
            return await self._chunked(file_bytes)
        return await self._retry(file_bytes, mime_type)

    async def _chunked(self, file_bytes: bytes) -> str:
        reader = PdfReader(io.BytesIO(file_bytes))
        pages = reader.pages[:_MAX_SOURCE_PAGES]
        if len(reader.pages) > _MAX_SOURCE_PAGES:
            logger.info("[OCR] Capping OCR at %d/%d pages", _MAX_SOURCE_PAGES, len(reader.pages))
        texts = []
        for i, page in enumerate(pages):
            w = PdfWriter()
            w.add_page(page)
            buf = io.BytesIO()
            w.write(buf)
            try:
                texts.append(await self._retry(buf.getvalue(), "application/pdf"))
            except Exception as e:
                logger.warning("[OCR] page %d failed: %s", i + 1, e)
                texts.append("")
        return "\n\n".join(t for t in texts if t)

    async def _retry(self, file_bytes: bytes, mime_type: str) -> str:
        last = None
        for attempt in range(_OCR_MAX_RETRIES):
            try:
                return await asyncio.to_thread(self._sync, file_bytes, mime_type)
            except Exception as e:
                last = e
                if attempt < _OCR_MAX_RETRIES - 1:
                    await asyncio.sleep(_OCR_RETRY_BACKOFF[attempt])
        raise last

    def _sync(self, file_bytes: bytes, mime_type: str) -> str:
        b64 = base64.b64encode(file_bytes).decode()
        client = Mistral(api_key=settings.mistral_api_key)
        resp = client.ocr.process(
            model="mistral-ocr-latest",
            document={"type": "document_url", "document_url": f"data:{mime_type};base64,{b64}"},
        )
        return "\n".join(p.markdown for p in resp.pages)


# ─── Source extraction ─────────────────────────────────────────────────────────

def _pdf_form_fields_as_text(file_bytes: bytes) -> str:
    """Extract filled source-PDF form fields as 'Label: Value' lines.

    Uses each field's /TU tooltip (the form's own user-readable label, e.g.
    "Named Insured", "Tax ID") as the key. Falls back to a cleaned-up
    deepest-segment of the field name if /TU is absent.

    Without this, every value ships to the LLM keyed by its cryptic
    AcroForm path like "topmostSubform[0].Page1[0].field_42[0]" — the
    model can't tell what each value means, gives up on label-matching,
    and assigns values to target fields by data type / order, which
    produces an off-by-one shift across the whole form.
    """
    try:
        reader = PdfReader(io.BytesIO(file_bytes))
        fields = reader.get_fields() or {}
        lines = []
        for name, field in fields.items():
            val = field.get("/V", "")
            if not val:
                continue
            sval = str(val).strip()
            if sval in ("", " ", "Please Select...", "/Off"):
                continue
            try:
                tu_raw = field.get("/TU")
                label = str(tu_raw).strip() if tu_raw is not None else ""
            except Exception:
                label = ""
            if not label:
                # Parse the AcroForm name into a readable label — picks up
                # ACORD-style names like Producer_FullName_A → "Producer Full
                # Name", Policy_Status_EffectiveDate_A → "Policy Status
                # Effective Date".
                label = _humanize_field_name(name) or name
            lines.append(f"{label}: {sval}")
        return "\n".join(lines)
    except Exception as e:
        logger.debug("[FORM-FIELDS] %s", e)
        return ""


def _first_n_words(text: str, n: int) -> str:
    """Return text truncated to the first n words (≈ n tokens)."""
    words = text.split()
    if len(words) <= n:
        return text
    return " ".join(words[:n])


async def _extract_source_text(filename: str, file_bytes: bytes, ocr: MistralOCR) -> str:
    """Return a rich text representation of a source file for the LLM."""
    ext = os.path.splitext(filename.lower())[1]

    if ext in ('.txt', '.md', '.markdown', '.json', '.xml'):
        return file_bytes.decode('utf-8', errors='replace')

    if ext in ('.html', '.htm'):
        text = file_bytes.decode('utf-8', errors='replace')
        text = re.sub(r"(?is)<(script|style).*?</\1>", " ", text)
        text = re.sub(r"(?i)<br\s*/?>", "\n", text)
        text = re.sub(r"(?i)</(p|div|li|tr|h[1-6])>", "\n", text)
        text = unescape(re.sub(r"<[^>]+>", " ", text))
        return re.sub(r"[ \t]+", " ", re.sub(r"\n{3,}", "\n\n", text)).strip()

    if ext == '.msg':
        try:
            import extract_msg
            with tempfile.NamedTemporaryFile(suffix='.msg', delete=False) as tmp:
                tmp.write(file_bytes)
                tmp_path = tmp.name
            try:
                msg = extract_msg.Message(tmp_path)
                try:
                    parts = []
                    for label, val in [("Subject", msg.subject), ("From", msg.sender),
                                       ("To", msg.to), ("Date", str(msg.date) if msg.date else None)]:
                        if val:
                            parts.append(f"{label}: {val}")
                    body = str(msg.body or "").strip()
                    if body:
                        parts.append(body)
                    return "\n\n".join(parts)
                finally:
                    msg.close()
            finally:
                os.unlink(tmp_path)
        except Exception:
            return file_bytes.decode('utf-8', errors='replace')

    if ext in ('.eml', '.emlx'):
        email_bytes = file_bytes
        if ext == '.emlx':
            first, _, rest = file_bytes.partition(b"\n")
            if first.strip().isdigit() and rest:
                email_bytes = rest
        try:
            msg = BytesParser(policy=policy.default).parsebytes(email_bytes)
            parts = []
            for label, val in [("Subject", msg.get("subject")), ("From", msg.get("from")),
                                ("To", msg.get("to")), ("Date", msg.get("date"))]:
                if val:
                    parts.append(f"{label}: {val}")
            plain, html_parts = [], []
            for part in (msg.walk() if msg.is_multipart() else [msg]):
                if part.get_content_disposition() == 'attachment':
                    continue
                ct = part.get_content_type()
                try:
                    t = part.get_content()
                except Exception:
                    payload = part.get_payload(decode=True) or b""
                    t = payload.decode(part.get_content_charset() or 'utf-8', errors='replace')
                if not isinstance(t, str) or not t.strip():
                    continue
                if ct == 'text/plain':
                    plain.append(t)
                elif ct == 'text/html':
                    html_parts.append(t)
            body = "\n\n".join(c.strip() for c in plain if c.strip())
            if not body and html_parts:
                h = "\n\n".join(html_parts)
                h = re.sub(r"(?is)<(script|style).*?</\1>", " ", h)
                h = re.sub(r"(?i)<br\s*/?>", "\n", h)
                h = re.sub(r"(?i)</(p|div|li|tr|h[1-6])>", "\n", h)
                body = unescape(re.sub(r"<[^>]+>", " ", h))
                body = re.sub(r"[ \t]+", " ", re.sub(r"\n{3,}", "\n\n", body)).strip()
            if body:
                parts.append(body)
            return "\n\n".join(p for p in parts if p)
        except Exception:
            return file_bytes.decode('utf-8', errors='replace')

    if ext == '.pdf':
        # For PDFs: form field values are the richest source — use them exclusively when available
        field_text = await asyncio.to_thread(_pdf_form_fields_as_text, file_bytes)
        if field_text:
            return f"[PDF Form Fields]\n{field_text}"

        # Check page count for logging
        try:
            page_count = len(PdfReader(io.BytesIO(file_bytes)).pages)
            if page_count > _MAX_SOURCE_PAGES:
                logger.info("[FORM-FILL] Source '%s' has %d pages — capping at %d",
                            filename, page_count, _MAX_SOURCE_PAGES)
        except Exception:
            page_count = 0

        # No form fields — fall back to text/OCR (capped at _MAX_SOURCE_PAGES)
        pypdf_text = await asyncio.to_thread(_extract_text_pypdf, file_bytes)
        if len(pypdf_text.strip()) >= _MIN_PYPDF_TEXT_LEN:
            return _first_n_words(pypdf_text, 15000)

        # Scanned PDF — OCR it (capped at _MAX_SOURCE_PAGES)
        ocr_text = await ocr.extract_text_async(file_bytes, 'application/pdf')
        return _first_n_words(ocr_text, 15000) if ocr_text else ""

    if ext in ('.png', '.jpg', '.jpeg', '.webp', '.gif', '.bmp', '.tif', '.tiff'):
        mime = {'.png': 'image/png', '.jpg': 'image/jpeg', '.jpeg': 'image/jpeg',
                '.webp': 'image/webp', '.gif': 'image/gif', '.bmp': 'image/bmp',
                '.tif': 'image/tiff', '.tiff': 'image/tiff'}.get(ext, 'image/png')
        return await ocr.extract_text_async(file_bytes, mime)

    return file_bytes.decode('utf-8', errors='replace')


# ─── Target field schema ───────────────────────────────────────────────────────

def _extract_visible_labels(pdf_bytes: bytes) -> dict[str, str]:
    """OCR-free visible-label extraction using PyMuPDF.

    For each AcroForm widget, find the printed label nearby on the page —
    necessary for forms (like AmTrust E&S) whose authors didn't set /TU
    and whose field names are just `Text1`, `Check Box1`, etc. Returns
    {field_name: label} with labels like "Name of Applicant" for text
    fields and "<question stem> — <option>" for checkboxes.

    Strategy:
      • Text-input field: split each text span at every colon (one span
        often holds 'P.O. Box: ___ City: ___ State: ___' on a single
        visual row); each colon is a label boundary. Pick the boundary
        with the smallest x-distance to the field's left edge.
      • Checkbox / radio: combine the question stem (longest non-numeric
        non-option text on the same line) with the option (text directly
        right of the box) — yields "Insured does not occupy more than
        25,000 square feet — True".
    """
    same_line_tol = 4.0
    out: dict[str, str] = {}
    try:
        doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    except Exception as e:
        logger.debug("[VISIBLE-LABELS] open failed: %s", e)
        return out

    try:
        for page in doc:
            try:
                page_dict = page.get_text("dict")
            except Exception:
                continue
            spans: list[tuple[tuple[float, float, float, float], str]] = []
            for block in page_dict.get("blocks", []):
                for line in block.get("lines", []):
                    for span in line.get("spans", []):
                        t = span.get("text") or ""
                        if t.strip():
                            spans.append((span["bbox"], t))

            try:
                widgets = list(page.widgets() or [])
            except Exception:
                widgets = []

            for w in widgets:
                name = w.field_name
                if not name:
                    continue
                ft = w.field_type  # pymupdf: 7 = text, 2 = checkbox, 5 = radio
                fx0, fy0, fx1, fy1 = w.rect.x0, w.rect.y0, w.rect.x1, w.rect.y1
                fcy = (fy0 + fy1) / 2

                same_line = [
                    (b, t) for b, t in spans
                    if abs((b[1] + b[3]) / 2 - fcy) <= same_line_tol
                ]

                label = ""
                if ft == 7 or ft == 0:  # text field (or unknown -> treat as text)
                    # For each span on the line, walk every colon as a label
                    # boundary; pick the boundary nearest the field's left edge.
                    best_seg = None
                    best_dist = float("inf")
                    for (sx0, _, sx1, _), text in same_line:
                        if ":" not in text:
                            continue
                        width = max(sx1 - sx0, 1.0)
                        n = len(text)
                        prev_idx = 0
                        for i, ch in enumerate(text):
                            if ch != ":":
                                continue
                            seg = text[prev_idx:i]
                            seg = re.sub(r"^[_\s\t]+|[_\s\t]+$", "", seg).strip()
                            if seg:
                                colon_x = sx0 + (i + 1) / n * width
                                d = abs(colon_x - fx0)
                                if d < best_dist:
                                    best_dist = d
                                    best_seg = seg
                            prev_idx = i + 1
                    if best_seg:
                        label = best_seg
                elif ft in (2, 5):  # checkbox or radio
                    stem = ""
                    for (sx0, _, _, _), text in same_line:
                        cleaned = re.sub(r"[_\s\t]+", " ", text).strip().rstrip(":")
                        if not cleaned:
                            continue
                        if re.fullmatch(r"\d+\.?", cleaned):
                            continue
                        if cleaned.lower() in ("true", "false", "yes", "no"):
                            continue
                        if len(cleaned) > len(stem):
                            stem = cleaned
                    opt = ""
                    opt_dist = float("inf")
                    for (sx0, _, sx1, _), text in same_line:
                        cleaned = re.sub(r"[_\s\t]+$", "", text).strip().rstrip(":")
                        if not cleaned:
                            continue
                        if sx0 >= fx1 - 2:
                            d = sx0 - fx1
                            if d < opt_dist:
                                opt_dist = d
                                opt = cleaned
                    if stem and opt and stem != opt:
                        label = f"{stem} — {opt}"
                    else:
                        label = opt or stem

                if label:
                    out[name] = label[:200]  # cap to keep prompts reasonable
    finally:
        doc.close()

    return out


def _extract_target_schema(reader: PdfReader, pdf_bytes: bytes | None = None) -> dict:
    """
    Returns dict of field_name -> field_meta where field_meta has:
      type: 'text' | 'checkbox' | 'dropdown' | 'radio'
      label: human-readable label — /TU tooltip first, falling back to
             OCR-free visible-label extraction (PyMuPDF positional text
             matching), and finally None
      options: list (for dropdown/radio)
      appearance_states: dict (for checkbox)
    """
    raw = reader.get_fields()
    if not raw:
        raise ValueError("No form fields found in target PDF")

    # Pull visible labels once per form — used as fallback when /TU is unset.
    visible_labels: dict[str, str] = {}
    if pdf_bytes:
        visible_labels = _extract_visible_labels(pdf_bytes)
        logger.info(
            "[FORM-FILL] Visible-label extraction: %d/%d fields got a printed label",
            len(visible_labels), len(raw),
        )

    schema = {}
    for name, fd in raw.items():
        ft = fd.get('/FT', '')
        # Resolve a label for this field. Priority:
        #   1. /TU tooltip (the form's own user-readable label)
        #   2. visible printed text near the field (PyMuPDF position match)
        #   3. None — let _label_hint fall back to a humanized field name
        try:
            tu_raw = fd.get('/TU')
            label = str(tu_raw).strip() if tu_raw is not None else None
        except Exception:
            label = None
        if not label and visible_labels:
            label = visible_labels.get(name) or None
        if ft == '/Tx':
            schema[name] = {"type": "text", "label": label}
        elif ft == '/Btn':
            opts = fd.get('/Opt', [])
            if opts and len(opts) > 2:
                schema[name] = {"type": "radio", "options": [str(o) for o in opts], "label": label}
            else:
                schema[name] = {
                    "type": "checkbox",
                    "appearance_states": _get_checked_state(fd),
                    "label": label,
                }
        elif ft == '/Ch':
            opts = fd.get('/Opt', [])
            clean = [str(o) for o in opts if str(o) not in ('Please Select...', '')]
            schema[name] = {"type": "dropdown", "options": clean, "label": label}
        elif ft == '/Sig':
            pass  # skip signature fields
        else:
            # unknown type — treat as text
            schema[name] = {"type": "text", "label": label}

    return schema


def _get_checked_state(fd) -> dict:
    """Determine the checked/unchecked appearance state values for a checkbox field.

    PDF checkboxes use an arbitrary name for the checked state (often '/Yes', '/On',
    or '/1') that varies per form. pypdf stores the available states in a special
    '/_States_' key on the field dict. We read that first; if absent, we fall back
    to scanning /Kids widgets, then the field's own /AP/N stream.
    """
    try:
        # pypdf exposes all appearance state names via /_States_
        states = fd.get('/_States_')
        if states:
            state_list = list(states)
            checked = [s for s in state_list if s != '/Off']
            if checked:
                return {'checked': checked[0], 'unchecked': '/Off'}
    except Exception:
        pass

    def _from_ap(ap_dict) -> dict | None:
        try:
            if hasattr(ap_dict, 'get_object'):
                ap_dict = ap_dict.get_object()
            n = ap_dict.get('/N')
            if n is None:
                return None
            if hasattr(n, 'get_object'):
                n = n.get_object()
            if hasattr(n, 'keys'):
                states = list(n.keys())
                checked = [s for s in states if s != '/Off']
                return {'checked': checked[0] if checked else '/Yes', 'unchecked': '/Off'}
        except Exception:
            pass
        return None

    try:
        kids = fd.get('/Kids', [])
        if kids:
            widget = kids[0].get_object()
            ap = widget.get('/AP', {})
            if ap:
                result = _from_ap(ap)
                if result:
                    return result
        ap = fd.get('/AP', {})
        if ap:
            result = _from_ap(ap)
            if result:
                return result
    except Exception:
        pass
    return {'checked': '/Yes', 'unchecked': '/Off'}


# ─── LLM fill ─────────────────────────────────────────────────────────────────

def _short_field_name(name: str) -> str:
    """Strip trailing [n] index segments from the last dotted part of a field
    name so 'Page2[0].Loss[0].Year[0]' becomes 'Year' — used as a label hint
    when the PDF didn't supply /TU."""
    short = name.split('.')[-1]
    while short.endswith(']') and '[' in short:
        bracket = short.rfind('[')
        if short[bracket + 1:-1].isdigit():
            short = short[:bracket]
        else:
            break
    return short.strip()


# Patterns for parsing AcroForm field names into readable labels when /TU is
# absent. ACORD-style forms encode the meaning into the name itself —
# `Producer_FullName_A`, `Policy_Status_EffectiveDate_A` — so a tiny parser
# extracts plenty of signal without OCR.
_TRAILING_VARIANT_RE = re.compile(r'_[A-Z]\d?$')        # _A, _B, _C, _A1, _B2 …
_CAMEL_BOUNDARY_RE = re.compile(r'(?<=[a-z0-9])(?=[A-Z])')


def _humanize_field_name(name: str) -> str:
    """Convert a cryptic AcroForm field name into a human-readable label.

    Steps:
      1. Take the deepest dotted segment, strip `[n]` indices.
      2. Drop trailing single-letter variant suffixes like '_A', '_B', '_A1'.
      3. Split on underscores AND camelCase boundaries.
      4. Title-case and join with spaces.
    Returns "" if the resulting label is empty or identical to the original
    fragment (i.e. no useful structure was found)."""
    short = _short_field_name(name)
    if not short:
        return ""
    cleaned = _TRAILING_VARIANT_RE.sub("", short)
    parts: list[str] = []
    for chunk in cleaned.split("_"):
        chunk = chunk.strip()
        if not chunk:
            continue
        # Split CamelCase: "FullName" → ["Full", "Name"]
        sub = _CAMEL_BOUNDARY_RE.split(chunk)
        for s in sub:
            s = s.strip()
            if s:
                parts.append(s)
    if not parts:
        return ""
    label = " ".join(p[:1].upper() + p[1:] if p[:1].islower() else p for p in parts)
    return label if label.lower() != name.lower() else ""


def _label_hint(meta: dict, name: str) -> str:
    """[label: "..."] suffix for a field. Prefers the PDF's /TU tooltip
    (the human-readable form label); falls back to a parsed version of the
    field name when the form author didn't set /TU."""
    label = (meta.get("label") or "").strip()
    if label:
        return f' [label: "{label}"]'
    parsed = _humanize_field_name(name)
    if parsed:
        return f' [name: "{parsed}"]'
    return ''


def _build_field_lines(schema: dict, focus_names: list | None = None) -> str:
    """Build the field descriptions block for the prompt. Every line carries
    a [label: "..."] hint so the model fills by meaning, not by string-type."""
    lines = []
    names = focus_names if focus_names else list(schema.keys())
    for name in names:
        meta = schema.get(name)
        if not meta:
            continue
        t = meta["type"]
        hint = _label_hint(meta, name)
        if t == "text":
            lines.append(f'  "{name}": text{hint}')
        elif t == "checkbox":
            lines.append(f'  "{name}": checkbox{hint} — respond with "Yes" or "No"')
        elif t == "dropdown":
            opts = meta.get("options", [])
            opts_str = " | ".join(opts) if opts else "any value"
            lines.append(f'  "{name}": dropdown{hint} — choose one of: {opts_str}')
        elif t == "radio":
            opts = meta.get("options", [])
            opts_str = " | ".join(opts) if opts else "any value"
            lines.append(f'  "{name}": radio{hint} — choose one of: {opts_str}')
    return "\n".join(lines)


def _build_prompt(source_context: str, schema: dict, focus_names: list | None = None,
                  prior_values: dict | None = None) -> str:
    n_fields = len(focus_names) if focus_names else len(schema)
    field_block = _build_field_lines(schema, focus_names)

    prior_block = ""
    if prior_values:
        prior_lines = [f'  "{k}": {json.dumps(v)}' for k, v in prior_values.items() if v]
        if prior_lines:
            prior_block = (
                "\n\nFIELDS ALREADY FILLED (do not change these, include them in output):\n"
                + "\n".join(prior_lines)
            )

    focus_note = ""
    if focus_names:
        focus_note = (
            f"\n\nFOCUS: The {len(focus_names)} fields below were left blank in a prior pass. "
            "Re-check the source for any value that semantically matches each field's [label]. "
            "If the source genuinely has no value for that label, leave \"\" — do NOT guess to fill it."
        )

    return f"""You are filling out a structured form (ACORD, government, or similar). Each field below shows its machine name plus a [label: "..."] hint pulled from the PDF's own tooltip — that label tells you what the field is for. Match by the meaning of the label, not by string-type alone.

CORE PRINCIPLE — match by meaning, accept synonyms, but never dump data:
A wrong answer is worse than an empty field. Fill a field when the source contains a value that answers the question the label asks (even using different words for the same concept). Leave "" when the source has no value that matches the label's purpose.
- Synonyms ARE the same: "Vendor" / "Supplier" / "Offeror" / "Contractor" / "Company" / "Insured" can all be the same entity if context supports it. "Invoice number" / "PO number" / "Order number" / "Reference number" are interchangeable identifiers if the source has only one. Use sensible mappings.
- BUT do NOT cross-pollinate sections: a property year-built is NOT a Loss Year; a building square-footage is NOT a Description of Loss; a building address is NOT a mortgagee address; a total premium is NOT a per-line premium. The label tells you which section the field belongs to.
- Do NOT invent or fabricate data the source doesn't contain.
- Do NOT compute or derive values unless the math is trivial and the source provides every input (e.g. line totals when quantity and unit price are both given).

RULES:
1. Return a single flat JSON object — keys = field names exactly as listed below, values = strings.
2. Text fields: fill when the source has a value that answers the [label]'s question (synonyms welcome). Otherwise "".
3. Checkbox fields:
   - "Yes" if the source confirms what the [label] describes.
   - "No" if the source denies it OR explicitly says "none" / "no losses" / "no incidents" for that category.
   - "" only when the source is silent AND there's no reasonable default.
4. Dropdown / radio: pick the option whose meaning matches the source. "" if no option clearly applies.
5. Repeated table rows (Loss[0].*, Loss[1].*, Driver[0].*, Vehicle[0].*, line items, etc):
   - Fill row N only if the source contains an Nth distinct record matching that table's purpose.
   - If the source has fewer records than the form has rows, leave the extra rows entirely blank.
   - If the source explicitly says "no losses / no claims / none" or has a "Check here if none" indicator that's selected, leave EVERY row in that table blank.
6. NEVER return null, None, "N/A", "Unknown", "Not provided" — use "" for any unanswered field.
7. Numeric / currency fields: fill from the value the [label] asks for. Don't substitute a different amount just because both are dollars.
8. Names / addresses / dates: the [label] tells you whose name, which address, which date. Map the right entity from the source. The applicant's name is NOT a third-party contact's name; an inspection address is NOT a mailing address; an effective date is NOT an expiration date.

SOURCE DATA:
{source_context}{prior_block}{focus_note}

FIELDS TO FILL ({n_fields} total):
{field_block}

Respond with ONLY the JSON object. No markdown, no explanation."""


_FORM_FILL_MODEL = "gpt-4.1-mini"
_FORM_FILL_HAIKU_MODEL = "claude-haiku-4-5-20251001"
# Always route to Haiku 4.5 — gpt-4.1-mini was string-type-matching values
# into wrong fields (loss table getting building-fact text, etc). Haiku
# follows the [label] hints far more faithfully. gpt-4.1-mini stays as the
# fallback if the Anthropic key is unset.
_HAIKU_FIELD_THRESHOLD = 0

# Lazy-initialised Anthropic client
_anthropic_client = None


def _get_anthropic_client():
    global _anthropic_client
    if _anthropic_client is None:
        import anthropic
        _anthropic_client = anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key)
    return _anthropic_client


async def _call_llm_openai(prompt: str) -> tuple[dict, float, str]:
    """Call GPT-4.1-mini via OpenAI. Returns (values_dict, cost, model)."""
    response = await routed_acompletion(
        route_profile="form_fill",
        fallback_model=_FORM_FILL_MODEL,
        messages=[{"role": "user", "content": prompt}],
        response_format={"type": "json_object"},
        temperature=0,
    )

    used_model = getattr(response, "model", None) or _FORM_FILL_MODEL
    cost = 0.0
    if response.usage:
        from app.services.extraction.core import _estimate_cost, _MARKUP
        prompt_tokens = response.usage.prompt_tokens or 0
        completion_tokens = response.usage.completion_tokens or 0
        details = getattr(response.usage, "prompt_tokens_details", None)
        cached_tokens = getattr(details, "cached_tokens", 0) if details else 0
        cost = _estimate_cost(used_model, prompt_tokens, completion_tokens, cached_tokens) * _MARKUP

    raw = response.choices[0].message.content or "{}"
    # Strip markdown fences if present
    if "```json" in raw:
        raw = raw.split("```json")[1].split("```")[0].strip()
    elif "```" in raw:
        raw = raw.split("```")[1].split("```")[0].strip()

    try:
        values = json.loads(raw)
    except json.JSONDecodeError as e:
        logger.error("[FORM-FILL] JSON parse error (OpenAI): %s — raw: %s", e, raw[:200])
        values = {}

    return values, cost, used_model


async def _call_llm_haiku(prompt: str) -> tuple[dict, float, str]:
    """Call Claude Haiku 4.5 via Anthropic. Returns (values_dict, cost, model)."""
    from app.services.extraction.core import _estimate_cost, _MARKUP

    client = _get_anthropic_client()
    response = await client.messages.create(
        model=_FORM_FILL_HAIKU_MODEL,
        max_tokens=16384,
        temperature=0,
        messages=[{"role": "user", "content": prompt}],
    )

    used_model = response.model or _FORM_FILL_HAIKU_MODEL
    cost = 0.0
    if response.usage:
        input_tokens = response.usage.input_tokens or 0
        output_tokens = response.usage.output_tokens or 0
        cache_read = getattr(response.usage, "cache_read_input_tokens", 0) or 0
        cost = _estimate_cost(used_model, input_tokens, output_tokens, cache_read) * _MARKUP

    raw = response.content[0].text if response.content else "{}"
    # Strip markdown fences if present
    if "```json" in raw:
        raw = raw.split("```json")[1].split("```")[0].strip()
    elif "```" in raw:
        raw = raw.split("```")[1].split("```")[0].strip()

    try:
        values = json.loads(raw)
    except json.JSONDecodeError as e:
        logger.error("[FORM-FILL] JSON parse error (Haiku): %s — raw: %s", e, raw[:200])
        values = {}

    return values, cost, used_model


async def _call_llm(prompt: str, n_fields: int = 0, force_claude: bool = False) -> tuple[dict, float, str]:
    """Route to Haiku 4.5 for large forms (100+ fields) or when forced, else GPT-4.1-mini."""
    use_haiku = (
        (force_claude or n_fields >= _HAIKU_FIELD_THRESHOLD)
        and settings.anthropic_api_key
    )
    if use_haiku:
        logger.info("[FORM-FILL] Using Haiku 4.5 (fields=%d, forced=%s, threshold=%d)",
                     n_fields, force_claude, _HAIKU_FIELD_THRESHOLD)
        return await _call_llm_haiku(prompt)
    return await _call_llm_openai(prompt)


def _is_blank(val) -> bool:
    if val is None:
        return True
    s = str(val).strip()
    return s in ("", "Please Select...", "N/A", "n/a", "null", "None")


def _normalize_checkbox(raw_val: str, appearance_states: dict) -> str:
    """Convert Yes/No LLM answer to the correct PDF appearance state."""
    v = str(raw_val).strip().lower()
    checked = appearance_states.get('checked', '/Yes')
    unchecked = appearance_states.get('unchecked', '/Off')
    if v in ("yes", "y", "true", "1", "checked", "on"):
        return checked
    return unchecked


def _normalize_values(raw: dict, schema: dict) -> dict:
    """Convert LLM output to PDF-ready values."""
    out = {}
    for name, meta in schema.items():
        val = raw.get(name, "")
        t = meta["type"]
        if t == "checkbox":
            out[name] = _normalize_checkbox(str(val), meta.get("appearance_states", {}))
        elif t in ("dropdown", "radio"):
            opts = meta.get("options", [])
            # If LLM returned an invalid option, pick the closest or leave blank
            if opts and val not in opts:
                # Case-insensitive match
                val_lower = str(val).strip().lower()
                match = next((o for o in opts if o.lower() == val_lower), None)
                out[name] = match if match else ""
            else:
                out[name] = val if val else ""
        else:
            out[name] = "" if _is_blank(val) else str(val)
    return out


# ─── PDF write ────────────────────────────────────────────────────────────────

def _write_pdf(reader: PdfReader, field_values: dict) -> bytes:
    writer = PdfWriter()
    writer.append(reader)
    for name, val in field_values.items():
        try:
            writer.update_page_form_field_values(None, {name: val})
        except Exception as e:
            logger.debug("[WRITE] field '%s' failed: %s", name, str(e)[:60])
    out = io.BytesIO()
    writer.write(out)
    return out.getvalue()


# ─── Main entry point ─────────────────────────────────────────────────────────

class PDFPopulator:
    async def populate_async(
        self,
        source_files_bytes: list[tuple[str, bytes]],
        target_pdf_bytes: bytes,
        force_claude: bool = False,
    ) -> tuple[bytes, float, list]:
        logger.info("[FORM-FILL] Starting — %d source file(s)", len(source_files_bytes))
        total_cost = 0.0
        ocr = MistralOCR()

        # 1. Extract source data
        source_parts = []
        for filename, file_bytes in source_files_bytes:
            text = await _extract_source_text(filename, file_bytes, ocr)
            if text.strip():
                source_parts.append(f"=== {filename} ===\n{text}")
                logger.info("[FORM-FILL] Source '%s': %d chars", filename, len(text))
        source_context = "\n\n".join(source_parts)
        logger.info("[FORM-FILL] Total source context: %d chars", len(source_context))

        # 2. Extract target schema
        reader = await asyncio.to_thread(PdfReader, io.BytesIO(target_pdf_bytes))
        schema = await asyncio.to_thread(_extract_target_schema, reader, target_pdf_bytes)
        logger.info("[FORM-FILL] Target schema: %d fillable fields", len(schema))

        # 3. Three-pass fill
        filled: dict = {}
        used_model = "unknown"

        for pass_num in range(1, 4):
            # Determine which fields to focus on this pass
            if pass_num == 1:
                focus = None  # all fields
            else:
                focus = [n for n in schema if _is_blank(filled.get(n))]
                if not focus:
                    logger.info("[FORM-FILL] Pass %d: all fields filled, stopping", pass_num)
                    break
                logger.info("[FORM-FILL] Pass %d: %d blank fields remain", pass_num, len(focus))

            prompt = _build_prompt(
                source_context=source_context,
                schema=schema,
                focus_names=focus,
                prior_values={k: v for k, v in filled.items() if not _is_blank(v)} if pass_num > 1 else None,
            )

            n_fields_this_pass = len(focus) if focus else len(schema)
            values, cost, model = await _call_llm(prompt, n_fields=n_fields_this_pass, force_claude=force_claude)
            total_cost += cost
            used_model = model
            logger.info("[FORM-FILL] Pass %d complete — model=%s cost=$%.6f", pass_num, model, cost)

            # Merge: new values fill in blanks, don't overwrite good existing values
            for name in schema:
                existing = filled.get(name)
                new_val = values.get(name)
                if _is_blank(existing) and not _is_blank(new_val):
                    filled[name] = new_val

            # Log fill rate
            n_filled = sum(1 for n in schema if not _is_blank(filled.get(n)))
            logger.info("[FORM-FILL] Pass %d fill rate: %d/%d (%.0f%%)",
                        pass_num, n_filled, len(schema), 100 * n_filled / len(schema) if schema else 0)

        # 4. Normalize to PDF values
        pdf_values = _normalize_values(filled, schema)

        # 5. Write output PDF
        output_bytes = await asyncio.to_thread(_write_pdf, reader, pdf_values)
        logger.info("[FORM-FILL] Done — output %d bytes, cost $%.6f", len(output_bytes), total_cost)

        return output_bytes, total_cost, [{"model": used_model, "provider": used_model.split("/")[0] if "/" in used_model else used_model, "cost_usd": total_cost}]
