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

import random
import time
from openai import AsyncOpenAI

from app.services.llm_router import routed_acompletion
from app.config import settings

logger = logging.getLogger(__name__)

# Minimum characters from pypdf before we consider it "good enough" and skip OCR
_MIN_PYPDF_TEXT_LEN = 200

_OCR_MAX_RETRIES = 3
_OCR_RETRY_BACKOFF = [1, 3, 6]  # seconds


def _extract_text_pypdf(file_bytes: bytes) -> str:
    """Try to extract text from a digital PDF using pypdf (free, no API call)."""
    try:
        reader = PdfReader(io.BytesIO(file_bytes))
        pages_text = []
        for page in reader.pages:
            text = page.extract_text() or ""
            if text.strip():
                pages_text.append(text)
        return "\n\n".join(pages_text)
    except Exception as e:
        logger.debug("[PYPDF] Text extraction failed: %s", e)
        return ""


_OCR_MAX_FILE_SIZE = 1_000_000  # 1 MB — above this, split PDF into per-page chunks for OCR


class MistralOCR:
    """Extract text from PDF using Mistral OCR (for scanned documents)"""

    async def extract_text_async(self, file_bytes: bytes, mime_type: str = "application/pdf") -> str:
        logger.info(f"[OCR] Starting async OCR extraction for file of size {len(file_bytes)} bytes")

        # For large PDFs, split into per-page chunks to avoid Mistral overflow
        if mime_type == "application/pdf" and len(file_bytes) > _OCR_MAX_FILE_SIZE:
            return await self._extract_text_chunked(file_bytes)

        return await self._ocr_with_retry(file_bytes, mime_type)

    async def _extract_text_chunked(self, file_bytes: bytes) -> str:
        """Split large PDF into single-page PDFs and OCR each one."""
        reader = PdfReader(io.BytesIO(file_bytes))
        n_pages = len(reader.pages)
        logger.info(f"[OCR] Large PDF ({len(file_bytes)} bytes, {n_pages} pages) — splitting into per-page chunks")

        page_texts = []
        for i, page in enumerate(reader.pages):
            writer = PdfWriter()
            writer.add_page(page)
            buf = io.BytesIO()
            writer.write(buf)
            chunk_bytes = buf.getvalue()
            try:
                text = await self._ocr_with_retry(chunk_bytes, "application/pdf")
                page_texts.append(text)
                logger.info(f"[OCR] Page {i+1}/{n_pages}: {len(text)} chars")
            except Exception as e:
                logger.warning(f"[OCR] Page {i+1}/{n_pages} failed: {e}")
                page_texts.append("")

        combined = "\n\n".join(t for t in page_texts if t)
        logger.info(f"[OCR] Chunked extraction complete: {len(combined)} chars from {n_pages} pages")
        return combined

    async def _ocr_with_retry(self, file_bytes: bytes, mime_type: str) -> str:
        last_exc = None
        for attempt in range(_OCR_MAX_RETRIES):
            try:
                result = await asyncio.to_thread(self._extract_text_sync, file_bytes, mime_type)
                return result
            except Exception as e:
                last_exc = e
                if attempt < _OCR_MAX_RETRIES - 1:
                    wait = _OCR_RETRY_BACKOFF[attempt]
                    logger.warning("[OCR] Attempt %d failed (%s), retrying in %ds", attempt + 1, str(e)[:80], wait)
                    await asyncio.sleep(wait)
                else:
                    logger.error(f"[OCR] All {_OCR_MAX_RETRIES} attempts failed: {str(e)}", exc_info=True)
        raise last_exc

    def _extract_text_sync(self, file_bytes: bytes, mime_type: str) -> str:
        base64_file = base64.b64encode(file_bytes).decode('utf-8')
        client = Mistral(api_key=settings.mistral_api_key)
        response = client.ocr.process(
            model="mistral-ocr-latest",
            document={"type": "document_url", "document_url": f"data:{mime_type};base64,{base64_file}"},
        )
        extracted_text = "\n".join(page.markdown for page in response.pages)
        logger.info(f"[OCR] Text extraction complete, length: {len(extracted_text)} characters")
        return extracted_text


class PDFPopulator:
    """Read PDF fields, generate values with AI, and populate PDF"""

    def extract_field_info(self, reader: PdfReader) -> tuple:
        all_fields = reader.get_fields()
        if not all_fields:
            raise ValueError("No form fields found in target PDF")

        logger.info(f"[FIELDS] Found {len(all_fields)} fields in target PDF")
        field_info = {}
        pydantic_fields = {}

        for field_name, field_data in all_fields.items():
            field_type = field_data.get('/FT', 'unknown')
            current_value = field_data.get('/V', '')

            if field_type == '/Tx':
                field_info[field_name] = {"type": "text", "current": current_value}
            elif field_type == '/Btn':
                options = field_data.get('/Opt', [])
                appearance_states = self._get_appearance_states(field_data)
                if options and len(options) > 2:
                    field_info[field_name] = {"type": "radio", "options": options, "current": current_value}
                else:
                    field_info[field_name] = {
                        "type": "checkbox",
                        "values": "Yes/No",
                        "current": current_value,
                        "appearance_states": appearance_states
                    }
            elif field_type == '/Ch':
                options = field_data.get('/Opt', [])
                field_info[field_name] = {"type": "dropdown", "options": options, "current": current_value}
            else:
                field_info[field_name] = {"type": "text", "current": current_value}

            pydantic_fields[field_name] = (str, ...)

        return field_info, pydantic_fields

    def _get_appearance_states(self, field_data):
        try:
            kids = field_data.get('/Kids', [])
            if kids:
                widget = kids[0].get_object()
                ap = widget.get('/AP', {})
                if ap and '/N' in ap:
                    normal_ap = ap['/N']
                    if hasattr(normal_ap, 'keys'):
                        states = list(normal_ap.keys())
                        checked_states = [s for s in states if s != '/Off']
                        return {
                            'checked': checked_states[0] if checked_states else '/Yes',
                            'unchecked': '/Off'
                        }
        except Exception:
            pass
        return {'checked': '/Yes', 'unchecked': '/Off'}

    async def generate_field_values_async(self, text: str, field_info: dict, pydantic_fields: dict) -> tuple:
        logger.info(f"[AI] Generating field values for {len(field_info)} fields (async)")

        field_descriptions = []
        for fname, finfo in field_info.items():
            current = finfo['current'] if finfo['current'] else '[empty]'
            if finfo["type"] == "text":
                field_descriptions.append(f'  "{fname}": "[TEXT] {current}"')
            elif finfo["type"] == "checkbox":
                field_descriptions.append(f'  "{fname}": "[CHECKBOX - use Yes/No]"')
            elif finfo["type"] == "dropdown":
                options_str = ', '.join([str(opt) for opt in finfo['options']]) if finfo['options'] else 'any value'
                field_descriptions.append(f'  "{fname}": "[DROPDOWN - options: {options_str}]"')
            elif finfo["type"] == "radio":
                options_str = ', '.join([str(opt) for opt in finfo['options']]) if finfo['options'] else 'any value'
                field_descriptions.append(f'  "{fname}": "[RADIO - options: {options_str}]"')

        prompt = f"""You are a PDF form filling assistant. Your task is to extract relevant information from the provided text and fill in ALL available PDF form fields.

        CRITICAL REQUIREMENTS:
        1. Fill in EVERY field - attempt to populate ALL {len(field_info)} fields listed below
        2. Use information from the text to populate fields accurately
        3. For CHECKBOX fields: use ONLY "Yes" or "No"
        4. For DROPDOWN/RADIO fields: use ONLY values from the provided options list, or pick the most appropriate option
        5. For TEXT fields: use any appropriate string value
        6. If exact information is not available, infer reasonable values based on context
        7. For fields where no information exists, use appropriate defaults:
        - Checkboxes: "No"
        - Text fields: "N/A" or contextually appropriate value
        - Dropdowns: first available option or most appropriate from options list
        8. Match field names precisely as listed

        SOURCE TEXT:
        {text}

        FIELDS TO FILL (all required):
        {chr(10).join(field_descriptions)}

        Return a JSON object with ALL field names as keys and appropriate values. Every single field MUST have a value that matches its type constraints."""

        # Try Cerebras oss-120b first, then fall back to OpenAI models
        response = None
        used_model = "unknown"
        cerebras_keys = [k for k in (settings.cerebras_api_key, settings.cerebras_api_key2, settings.cerebras_api_key3) if k]
        if cerebras_keys:
            cerebras_model_raw = settings.cerebras_model.removeprefix("cerebras/")
            for c_attempt in range(3):
                try:
                    api_key = random.choice(cerebras_keys)
                    t0 = time.perf_counter()
                    client = AsyncOpenAI(base_url="https://api.cerebras.ai/v1", api_key=api_key)
                    response = await client.chat.completions.create(
                        model=cerebras_model_raw,
                        messages=[{"role": "user", "content": prompt}],
                        temperature=0,
                        response_format={"type": "json_object"},
                    )
                    elapsed_ms = (time.perf_counter() - t0) * 1000
                    used_model = settings.cerebras_model
                    logger.info("[FORM-FILL] Cerebras %s succeeded in %.0fms (attempt %d/3)", cerebras_model_raw, elapsed_ms, c_attempt + 1)
                    break
                except json.JSONDecodeError:
                    logger.warning("[FORM-FILL] Cerebras returned malformed JSON (attempt %d/3)", c_attempt + 1)
                    response = None
                    continue
                except Exception as exc:
                    err_str = str(exc).lower()
                    is_capacity = any(kw in err_str for kw in ("capacity", "rate", "limit", "overloaded", "503", "529", "too many", "quota"))
                    if is_capacity and c_attempt < 2:
                        wait = 2 ** c_attempt + random.random()
                        logger.warning("[FORM-FILL] Cerebras capacity issue (attempt %d/3), retrying in %.1fs: %s", c_attempt + 1, wait, exc)
                        await asyncio.sleep(wait)
                        continue
                    logger.warning("[FORM-FILL] Cerebras failed (attempt %d/3): %s", c_attempt + 1, exc)
                    response = None
                    break

        # Fallback to OpenAI if Cerebras didn't work
        if response is None:
            logger.info("[FORM-FILL] Falling back to OpenAI models")
            for attempt, model in enumerate([settings.form_fill_model, getattr(settings, 'form_fill_fallback_model', 'gpt-5.4')]):
                try:
                    response = await routed_acompletion(
                        route_profile="form_fill",
                        fallback_model=model,
                        messages=[{"role": "user", "content": prompt}],
                        response_format={"type": "json_object"},
                    )
                    used_model = getattr(response, "model", "unknown") or model
                    break
                except Exception as e:
                    err_str = str(e).lower()
                    if attempt == 0 and any(kw in err_str for kw in ("rate", "429", "quota", "capacity")):
                        logger.warning(f"[FORM-FILL] Rate limit on {model}, retrying with fallback")
                        continue
                    raise

        cost = 0.0
        if response.usage:
            from app.services.extraction.core import _estimate_cost
            cost = _estimate_cost(used_model, response.usage.prompt_tokens or 0, response.usage.completion_tokens or 0)

        response_text = response.choices[0].message.content
        if "```json" in response_text:
            response_text = response_text.split("```json")[1].split("```")[0].strip()
        elif "```" in response_text:
            response_text = response_text.split("```")[1].split("```")[0].strip()

        field_values = json.loads(response_text)

        for field_name, field_data in field_info.items():
            if field_data["type"] == "checkbox" and field_name in field_values:
                val = field_values[field_name].strip().lower()
                appearance_states = field_data.get("appearance_states", {'checked': '/Yes', 'unchecked': '/Off'})
                checked_state = appearance_states['checked']

                if checked_state == '/No':
                    if val in ["no", "n", "false", "0", "n/a"]:
                        field_values[field_name] = checked_state
                    else:
                        field_values[field_name] = appearance_states['unchecked']
                elif checked_state in ['/0', '/Choice1', '/Trust', '/Agent']:
                    if val in ["yes", "y", "true", "1", "checked", "on"]:
                        field_values[field_name] = checked_state
                    else:
                        field_values[field_name] = appearance_states['unchecked']
                else:
                    if val in ["yes", "y", "true", "1", "checked", "on"]:
                        field_values[field_name] = checked_state
                    else:
                        field_values[field_name] = appearance_states['unchecked']

        return field_values, cost, used_model

    async def populate_async(self, source_files_bytes: list[tuple[str, bytes]], target_pdf_bytes: bytes) -> tuple[bytes, float, list]:
        """
        Async PDF population.
        source_files_bytes: list of (filename, bytes) tuples — PDFs, images, or text files.
        Returns (output_pdf_bytes, total_cost, model_breakdown).
        """
        logger.info("=" * 80)
        logger.info("[POPULATE] Starting async PDF population process")
        total_cost = 0.0

        try:
            ocr_extractor = MistralOCR()
            all_texts = []

            for idx, (filename, file_bytes) in enumerate(source_files_bytes):
                ext = os.path.splitext(filename.lower())[1]
                if ext in ('.txt', '.md', '.markdown', '.json', '.xml'):
                    text = file_bytes.decode('utf-8', errors='replace')
                    all_texts.append(text)
                    logger.info(f"[POPULATE] Read text file {filename}: {len(text)} chars")
                elif ext in ('.html', '.htm'):
                    text = file_bytes.decode('utf-8', errors='replace')
                    text = re.sub(r"(?is)<(script|style).*?</\1>", " ", text)
                    text = re.sub(r"(?i)<br\s*/?>", "\n", text)
                    text = re.sub(r"(?i)</(p|div|li|tr|h[1-6])>", "\n", text)
                    text = unescape(re.sub(r"<[^>]+>", " ", text))
                    text = re.sub(r"[ \t]+", " ", text)
                    text = re.sub(r"\n{3,}", "\n\n", text).strip()
                    all_texts.append(text)
                    logger.info(f"[POPULATE] Read HTML file {filename}: {len(text)} chars")
                elif ext == '.msg':
                    try:
                        import extract_msg

                        with tempfile.NamedTemporaryFile(suffix='.msg', delete=False) as tmp:
                            tmp.write(file_bytes)
                            tmp_path = tmp.name
                        try:
                            message = extract_msg.Message(tmp_path)
                            try:
                                text_parts = []
                                header_lines = []
                                for label, value in (
                                    ("Subject", message.subject),
                                    ("From", message.sender),
                                    ("To", message.to),
                                    ("Cc", message.cc),
                                    ("Bcc", message.bcc),
                                    ("Date", str(message.date) if message.date else None),
                                ):
                                    if value:
                                        header_lines.append(f"{label}: {value}")
                                if header_lines:
                                    text_parts.append("\n".join(header_lines))

                                body_text = str(message.body or "").strip()
                                if not body_text and message.htmlBody:
                                    html_text = message.htmlBody
                                    if isinstance(html_text, bytes):
                                        html_text = html_text.decode('utf-8', errors='replace')
                                    html_text = re.sub(r"(?is)<(script|style).*?</\1>", " ", html_text)
                                    html_text = re.sub(r"(?i)<br\s*/?>", "\n", html_text)
                                    html_text = re.sub(r"(?i)</(p|div|li|tr|h[1-6])>", "\n", html_text)
                                    body_text = unescape(re.sub(r"<[^>]+>", " ", html_text))
                                    body_text = re.sub(r"[ \t]+", " ", body_text)
                                    body_text = re.sub(r"\n{3,}", "\n\n", body_text).strip()
                                if body_text:
                                    text_parts.append(body_text)

                                attachment_names = []
                                for attachment in message.attachments:
                                    attachment_name = (
                                        getattr(attachment, 'longFilename', None)
                                        or getattr(attachment, 'shortFilename', None)
                                        or getattr(attachment, 'displayName', None)
                                        or getattr(attachment, 'name', None)
                                    )
                                    if attachment_name:
                                        attachment_names.append(str(attachment_name))
                                if attachment_names:
                                    text_parts.append("Attachments:\n" + "\n".join(f"- {name}" for name in attachment_names))
                                text = "\n\n".join(part for part in text_parts if part).strip() or file_bytes.decode('utf-8', errors='replace')
                            finally:
                                message.close()
                        finally:
                            try:
                                os.unlink(tmp_path)
                            except OSError:
                                pass
                    except Exception:
                        text = file_bytes.decode('utf-8', errors='replace')
                    all_texts.append(text)
                    logger.info(f"[POPULATE] Read Outlook MSG file {filename}: {len(text)} chars")
                elif ext in ('.eml', '.emlx'):
                    email_bytes = file_bytes
                    if ext == '.emlx':
                        first_line, _, remainder = file_bytes.partition(b"\n")
                        if first_line.strip().isdigit() and remainder:
                            email_bytes = remainder
                    try:
                        message = BytesParser(policy=policy.default).parsebytes(email_bytes)
                        text_parts = []
                        header_lines = []
                        for label, value in (
                            ("Subject", message.get("subject")),
                            ("From", message.get("from")),
                            ("To", message.get("to")),
                            ("Cc", message.get("cc")),
                            ("Date", message.get("date")),
                        ):
                            if value:
                                header_lines.append(f"{label}: {value}")
                        if header_lines:
                            text_parts.append("\n".join(header_lines))

                        plain_parts = []
                        html_parts = []
                        attachment_names = []
                        for part in (message.walk() if message.is_multipart() else [message]):
                            disposition = part.get_content_disposition()
                            content_type = part.get_content_type()
                            if disposition == 'attachment':
                                attachment_name = part.get_filename()
                                if attachment_name:
                                    attachment_names.append(attachment_name)
                                continue
                            if not content_type.startswith('text/'):
                                continue
                            try:
                                part_text = part.get_content()
                            except Exception:
                                payload = part.get_payload(decode=True) or b""
                                charset = part.get_content_charset() or 'utf-8'
                                part_text = payload.decode(charset, errors='replace')
                            if not isinstance(part_text, str) or not part_text.strip():
                                continue
                            if content_type == 'text/plain':
                                plain_parts.append(part_text)
                            elif content_type == 'text/html':
                                html_parts.append(part_text)

                        body_text = "\n\n".join(chunk.strip() for chunk in plain_parts if chunk.strip()).strip()
                        if not body_text and html_parts:
                            html_text = "\n\n".join(html_parts)
                            html_text = re.sub(r"(?is)<(script|style).*?</\1>", " ", html_text)
                            html_text = re.sub(r"(?i)<br\s*/?>", "\n", html_text)
                            html_text = re.sub(r"(?i)</(p|div|li|tr|h[1-6])>", "\n", html_text)
                            body_text = unescape(re.sub(r"<[^>]+>", " ", html_text))
                            body_text = re.sub(r"[ \t]+", " ", body_text)
                            body_text = re.sub(r"\n{3,}", "\n\n", body_text).strip()

                        if body_text:
                            text_parts.append(body_text)
                        if attachment_names:
                            text_parts.append("Attachments:\n" + "\n".join(f"- {name}" for name in attachment_names))
                        text = "\n\n".join(part for part in text_parts if part).strip() or file_bytes.decode('utf-8', errors='replace')
                    except Exception:
                        text = file_bytes.decode('utf-8', errors='replace')
                    all_texts.append(text)
                    logger.info(f"[POPULATE] Read email file {filename}: {len(text)} chars")
                elif ext == '.pdf':
                    # Try free pypdf text extraction first (works for digital PDFs)
                    pypdf_text = await asyncio.to_thread(_extract_text_pypdf, file_bytes)
                    if len(pypdf_text.strip()) >= _MIN_PYPDF_TEXT_LEN:
                        all_texts.append(pypdf_text)
                        logger.info(f"[POPULATE] Extracted text from PDF {filename} via pypdf: {len(pypdf_text)} chars")
                    else:
                        # Scanned/image PDF — fall back to OCR
                        logger.info(f"[POPULATE] pypdf got {len(pypdf_text)} chars from {filename}, falling back to OCR")
                        extracted = await ocr_extractor.extract_text_async(file_bytes, 'application/pdf')
                        all_texts.append(extracted)
                        logger.info(f"[POPULATE] OCR'd PDF {filename}: {len(extracted)} chars")
                elif ext in ('.png', '.jpg', '.jpeg', '.webp', '.gif', '.bmp', '.tif', '.tiff'):
                    mime = {'.png': 'image/png', '.jpg': 'image/jpeg', '.jpeg': 'image/jpeg',
                            '.webp': 'image/webp', '.gif': 'image/gif', '.bmp': 'image/bmp',
                            '.tif': 'image/tiff', '.tiff': 'image/tiff'}.get(ext, 'image/png')
                    img_text = await ocr_extractor.extract_text_async(file_bytes, mime)
                    all_texts.append(img_text)
                    logger.info(f"[POPULATE] Extracted text from image {filename}: {len(img_text)} chars")
                else:
                    text = file_bytes.decode('utf-8', errors='replace')
                    all_texts.append(text)

            combined_text = "\n\n--- Next Source Document ---\n\n".join(all_texts)
            logger.info(f"[POPULATE] Combined text: {len(combined_text)} characters from {len(source_files_bytes)} files")

            reader = await asyncio.to_thread(PdfReader, io.BytesIO(target_pdf_bytes))
            field_info, pydantic_fields = await asyncio.to_thread(self.extract_field_info, reader)

            field_values, llm_cost, llm_model = await self.generate_field_values_async(combined_text, field_info, pydantic_fields)
            total_cost += llm_cost

            provider = llm_model.split("/")[0] if "/" in llm_model else llm_model
            model_breakdown = [{
                "model": llm_model,
                "provider": provider,
                "cost_usd": llm_cost,
            }]

            output_bytes = await asyncio.to_thread(self._write_pdf_sync, reader, field_values, field_info)

            logger.info(f"[POPULATE] Output PDF size: {len(output_bytes)} bytes, cost: ${total_cost:.6f}")
            logger.info("=" * 80)
            return output_bytes, total_cost, model_breakdown

        except Exception as e:
            logger.error(f"[POPULATE] ERROR: {str(e)}", exc_info=True)
            raise

    def _write_pdf_sync(self, reader: PdfReader, field_values: dict, field_info: dict) -> bytes:
        writer = PdfWriter()
        writer.append(reader)

        for field_name, field_value in field_values.items():
            try:
                writer.update_page_form_field_values(None, {field_name: field_value})
            except Exception as e:
                logger.warning(f"[POPULATE] Failed to update field '{field_name}': {str(e)[:50]}")

        output = io.BytesIO()
        writer.write(output)
        return output.getvalue()
