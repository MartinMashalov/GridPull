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

from app.services.llm_router import routed_acompletion
from app.config import settings

logger = logging.getLogger(__name__)

_MIN_PYPDF_TEXT_LEN = 200
_OCR_MAX_RETRIES = 3
_OCR_RETRY_BACKOFF = [1, 3, 6]
_OCR_MAX_FILE_SIZE = 1_000_000


# ─── OCR ───────────────────────────────────────────────────────────────────────

def _extract_text_pypdf(file_bytes: bytes) -> str:
    try:
        reader = PdfReader(io.BytesIO(file_bytes))
        pages = []
        for page in reader.pages:
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
        texts = []
        for i, page in enumerate(reader.pages):
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
    """Extract filled PDF form fields as 'Key: Value' lines — primary data source."""
    try:
        reader = PdfReader(io.BytesIO(file_bytes))
        fields = reader.get_fields() or {}
        lines = []
        for name, field in fields.items():
            val = field.get("/V", "")
            if val and str(val).strip() not in ("", " ", "Please Select...", "/Off"):
                lines.append(f"{name}: {val}")
        return "\n".join(lines)
    except Exception as e:
        logger.debug("[FORM-FIELDS] %s", e)
        return ""


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

        # No form fields — fall back to text/OCR
        pypdf_text = await asyncio.to_thread(_extract_text_pypdf, file_bytes)
        if len(pypdf_text.strip()) >= _MIN_PYPDF_TEXT_LEN:
            # Cap at 8000 chars to keep tokens low
            return pypdf_text[:8000]

        # Scanned PDF — OCR it
        ocr_text = await ocr.extract_text_async(file_bytes, 'application/pdf')
        return ocr_text[:8000] if ocr_text else ""

    if ext in ('.png', '.jpg', '.jpeg', '.webp', '.gif', '.bmp', '.tif', '.tiff'):
        mime = {'.png': 'image/png', '.jpg': 'image/jpeg', '.jpeg': 'image/jpeg',
                '.webp': 'image/webp', '.gif': 'image/gif', '.bmp': 'image/bmp',
                '.tif': 'image/tiff', '.tiff': 'image/tiff'}.get(ext, 'image/png')
        return await ocr.extract_text_async(file_bytes, mime)

    return file_bytes.decode('utf-8', errors='replace')


# ─── Target field schema ───────────────────────────────────────────────────────

def _extract_target_schema(reader: PdfReader) -> dict:
    """
    Returns dict of field_name -> field_meta where field_meta has:
      type: 'text' | 'checkbox' | 'dropdown' | 'radio'
      options: list (for dropdown/radio)
      appearance_states: dict (for checkbox)
    """
    raw = reader.get_fields()
    if not raw:
        raise ValueError("No form fields found in target PDF")

    schema = {}
    for name, fd in raw.items():
        ft = fd.get('/FT', '')
        if ft == '/Tx':
            schema[name] = {"type": "text"}
        elif ft == '/Btn':
            opts = fd.get('/Opt', [])
            if opts and len(opts) > 2:
                schema[name] = {"type": "radio", "options": [str(o) for o in opts]}
            else:
                schema[name] = {"type": "checkbox", "appearance_states": _get_checked_state(fd)}
        elif ft == '/Ch':
            opts = fd.get('/Opt', [])
            clean = [str(o) for o in opts if str(o) not in ('Please Select...', '')]
            schema[name] = {"type": "dropdown", "options": clean}
        elif ft == '/Sig':
            pass  # skip signature fields
        else:
            # unknown type — treat as text
            schema[name] = {"type": "text"}

    return schema


def _get_checked_state(fd) -> dict:
    try:
        kids = fd.get('/Kids', [])
        if kids:
            widget = kids[0].get_object()
            ap = widget.get('/AP', {})
            if ap and '/N' in ap:
                normal = ap['/N']
                if hasattr(normal, 'keys'):
                    states = list(normal.keys())
                    checked = [s for s in states if s != '/Off']
                    return {'checked': checked[0] if checked else '/Yes', 'unchecked': '/Off'}
    except Exception:
        pass
    return {'checked': '/Yes', 'unchecked': '/Off'}


# ─── LLM fill ─────────────────────────────────────────────────────────────────

def _build_field_lines(schema: dict, focus_names: list | None = None) -> str:
    """Build the field descriptions block for the prompt."""
    lines = []
    names = focus_names if focus_names else list(schema.keys())
    for name in names:
        meta = schema.get(name)
        if not meta:
            continue
        t = meta["type"]
        if t == "text":
            lines.append(f'  "{name}": text')
        elif t == "checkbox":
            lines.append(f'  "{name}": checkbox — respond with "Yes" or "No"')
        elif t == "dropdown":
            opts = meta.get("options", [])
            opts_str = " | ".join(opts) if opts else "any value"
            lines.append(f'  "{name}": dropdown — choose one of: {opts_str}')
        elif t == "radio":
            opts = meta.get("options", [])
            opts_str = " | ".join(opts) if opts else "any value"
            lines.append(f'  "{name}": radio — choose one of: {opts_str}')
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
            f"\n\nFOCUS: The {len(focus_names)} fields below were left blank in a prior attempt. "
            "Look harder at the source data — use any reasonable inference or partial match. "
            "Do NOT leave fields blank if there is ANY relevant information available."
        )

    return f"""You are filling out an insurance form. Extract values from the source data below and fill every field.

RULES:
1. Return a single flat JSON object with field names as keys and string values.
2. For checkbox fields: return "Yes" or "No" only.
3. For dropdown fields: return exactly one of the listed options (no "Please Select...").
4. For text fields: fill with the best matching value. Use inference and reasonable defaults:
   - If a field can be inferred from related data, infer it (e.g., expiration date = effective date + 12 months, revenue ≈ gross sales).
   - Leave "" ONLY if truly impossible to determine even with reasonable inference.
5. NEVER return null, None, or "N/A" — use "" for genuinely unknowable fields.
6. CRITICAL — always fill these field types if ANY related data exists: names, addresses, phones, emails, dates, agents, producers, premiums, carriers, coverage limits.
7. For financial/revenue fields: use the closest monetary value from the source (gross sales, total payroll, premium, etc.).
8. For safety/operations text fields: compose a reasonable answer based on the business description in the source.
9. For "yes/no" questions about prior losses, cancellations, etc.: default to "No" unless the source shows otherwise.

SOURCE DATA:
{source_context}{prior_block}{focus_note}

FIELDS TO FILL ({n_fields} total):
{field_block}

Respond with ONLY the JSON object. No markdown, no explanation."""


_FORM_FILL_MODEL = "gpt-4.1-mini"


async def _call_llm(prompt: str) -> tuple[dict, float, str]:
    """Call GPT-4.1-mini with json_object response format. Returns (values_dict, cost, model)."""
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
        # gpt-4.1-mini: $0.40/1M input, $1.60/1M output
        cost = (response.usage.prompt_tokens or 0) * 0.40e-6 + (response.usage.completion_tokens or 0) * 1.60e-6

    raw = response.choices[0].message.content or "{}"
    # Strip markdown fences if present
    if "```json" in raw:
        raw = raw.split("```json")[1].split("```")[0].strip()
    elif "```" in raw:
        raw = raw.split("```")[1].split("```")[0].strip()

    try:
        values = json.loads(raw)
    except json.JSONDecodeError as e:
        logger.error("[FORM-FILL] JSON parse error: %s — raw: %s", e, raw[:200])
        values = {}

    return values, cost, used_model


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
        schema = await asyncio.to_thread(_extract_target_schema, reader)
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

            values, cost, model = await _call_llm(prompt)
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
