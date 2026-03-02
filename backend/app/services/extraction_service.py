import json
import asyncio
import os
from typing import List, Dict, Any
from openai import AsyncOpenAI
from app.config import settings

client = AsyncOpenAI(api_key=settings.openai_api_key)

_model_index = 0


def _get_next_model() -> str:
    """Rotate through available models."""
    global _model_index
    model = settings.openai_models[_model_index % len(settings.openai_models)]
    _model_index += 1
    return model


async def extract_fields_from_text(
    text: str,
    fields: List[Dict[str, str]],
    filename: str,
) -> Dict[str, Any]:
    """Use OpenAI to extract specified fields from PDF text."""
    model = _get_next_model()

    fields_desc = "\n".join(
        f"- {f['name']}: {f.get('description', f['name'])}"
        for f in fields
    )

    field_names = [f["name"] for f in fields]

    system_prompt = """You are a precise data extraction assistant.
Extract specific fields from document text and return ONLY valid JSON.
If a field is not found, use null as the value.
Do not include explanations, only the JSON object."""

    user_prompt = f"""Extract the following fields from this document:

Fields to extract:
{fields_desc}

Document: {filename}

Document text:
{text[:12000]}

Return a JSON object with exactly these keys: {json.dumps(field_names)}
Values should be strings or null. Extract the most relevant value for each field."""

    for attempt in range(3):
        try:
            response = await client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                temperature=0,
                response_format={"type": "json_object"},
                max_tokens=2000,
            )

            content = response.choices[0].message.content
            data = json.loads(content)

            # Ensure all fields are present
            result = {}
            for field in field_names:
                result[field] = str(data.get(field, "")) if data.get(field) is not None else ""

            result["_source_file"] = filename
            return result

        except Exception as e:
            if attempt == 2:
                # Return empty on final failure
                result = {f["name"]: "" for f in fields}
                result["_source_file"] = filename
                result["_error"] = str(e)
                return result
            # Try next model
            model = _get_next_model()
            await asyncio.sleep(1)

    return {f["name"]: "" for f in fields}
