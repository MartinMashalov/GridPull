import os
import io
import json
import base64
import logging
import asyncio
from litellm import ocr, acompletion
from pypdf import PdfReader, PdfWriter

logger = logging.getLogger(__name__)


class MistralOCR:
    """Extract text from PDF using Mistral OCR"""

    async def extract_text_async(self, pdf_bytes: bytes) -> str:
        logger.info(f"[OCR] Starting async OCR extraction for PDF of size {len(pdf_bytes)} bytes")
        try:
            result = await asyncio.to_thread(self._extract_text_sync, pdf_bytes)
            return result
        except Exception as e:
            logger.error(f"[OCR] Error during OCR extraction: {str(e)}", exc_info=True)
            raise

    def _extract_text_sync(self, pdf_bytes: bytes) -> str:
        base64_pdf = base64.b64encode(pdf_bytes).decode('utf-8')
        document = {
            "type": "document_url",
            "document_url": f"data:application/pdf;base64,{base64_pdf}"
        }
        response = ocr(model="mistral/mistral-ocr-latest", document=document)
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

        max_retries = 10
        for attempt in range(max_retries):
            try:
                response = await acompletion(
                    model="groq/llama-3.3-70b-versatile",
                    messages=[{"role": "user", "content": prompt}],
                    response_format={"type": "json_object"}
                )
                break
            except Exception as e:
                logger.warning(f"[AI] Attempt {attempt + 1} failed: {str(e)}")
                if attempt < max_retries - 1:
                    await asyncio.sleep((attempt + 1) * 2)
                else:
                    raise

        cost = response._hidden_params.get('response_cost', 0.0)
        used_model = getattr(response, "model", "groq/llama-3.3-70b-versatile")

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
                if ext in ('.txt', '.md', '.markdown'):
                    text = file_bytes.decode('utf-8', errors='replace')
                    all_texts.append(text)
                    logger.info(f"[POPULATE] Read text file {filename}: {len(text)} chars")
                elif ext == '.pdf':
                    extracted = await ocr_extractor.extract_text_async(file_bytes)
                    all_texts.append(extracted)
                    logger.info(f"[POPULATE] OCR'd PDF {filename}: {len(extracted)} chars")
                elif ext in ('.png', '.jpg', '.jpeg', '.webp', '.gif'):
                    mime = {'.png': 'image/png', '.jpg': 'image/jpeg', '.jpeg': 'image/jpeg',
                            '.webp': 'image/webp', '.gif': 'image/gif'}.get(ext, 'image/png')
                    b64 = base64.b64encode(file_bytes).decode('utf-8')
                    img_response = await acompletion(
                        model="groq/llama-3.3-70b-versatile",
                        messages=[{
                            "role": "user",
                            "content": [
                                {"type": "text", "text": "Extract ALL text and data from this image. Return everything you can read."},
                                {"type": "image_url", "image_url": {"url": f"data:{mime};base64,{b64}"}}
                            ]
                        }]
                    )
                    img_text = img_response.choices[0].message.content
                    all_texts.append(img_text)
                    img_cost = img_response._hidden_params.get('response_cost', 0.0)
                    total_cost += img_cost
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
