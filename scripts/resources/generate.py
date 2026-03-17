"""Content generation using Claude API in constrained schema-first mode."""

import json
import os
import sys
from typing import Any

from .config import PRODUCT_CAPABILITIES, DEFAULT_CANONICAL_BASE_URL, CLAUDE_API_KEY
from .schema import validate_schema


def generate_resource(topic: dict[str, Any]) -> dict[str, Any] | None:
    """Generate a resource page using Claude API in constrained schema mode.

    Returns the generated resource data, or None if generation fails.
    """
    api_key = CLAUDE_API_KEY or os.getenv("CLAUDE_API_KEY", "")
    if not api_key:
        print("[generate] No CLAUDE_API_KEY set, skipping AI generation")
        return None

    prompt = _build_generation_prompt(topic)

    try:
        import anthropic
        client = anthropic.Anthropic(api_key=api_key)
        response = client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=4096,
            messages=[{"role": "user", "content": prompt}],
        )
        content = response.content[0].text

        # Extract JSON from response
        json_str = _extract_json(content)
        if not json_str:
            print(f"[generate] Failed to extract JSON for '{topic['slug']}'")
            return None

        data = json.loads(json_str)

        # Validate schema
        errors = validate_schema(data)
        if errors:
            print(f"[generate] Schema errors for '{topic['slug']}': {errors}")
            return None

        return data

    except ImportError:
        print("[generate] FATAL: anthropic package not installed. Run: pip install anthropic")
        return None
    except json.JSONDecodeError as e:
        print(f"[generate] JSON parse error for '{topic['slug']}': {e}")
        # Log the raw content for debugging
        if 'content' in dir():
            print(f"[generate] Raw response (first 500 chars): {content[:500]}")
        return None
    except Exception as e:
        print(f"[generate] Generation error for '{topic['slug']}': {type(e).__name__}: {e}")
        import traceback
        traceback.print_exc()
        return None


def _build_generation_prompt(topic: dict[str, Any]) -> str:
    """Build the constrained generation prompt for Claude."""
    return f"""You are generating structured content for a resource page on pdfexcel.ai.

TARGET:
- Primary keyword: {topic['keyword']}
- Slug: {topic['slug']}
- Template type: {topic['template']}
- Search intent: {topic['intent']}
- Differentiation angle: {topic['angle']}

PRODUCT TRUTH (only make claims supported by these facts):
- Core function: {PRODUCT_CAPABILITIES['core_function']}
- Supported inputs: {', '.join(PRODUCT_CAPABILITIES['supported_inputs'])}
- Supported outputs: {', '.join(PRODUCT_CAPABILITIES['supported_outputs'])}
- Key features: {', '.join(PRODUCT_CAPABILITIES['key_features'])}
- Document types: {', '.join(PRODUCT_CAPABILITIES['document_types'])}
- Known limitations: {', '.join(PRODUCT_CAPABILITIES['limitations'])}

DISALLOWED CLAIMS (never state or imply):
{chr(10).join('- ' + c for c in PRODUCT_CAPABILITIES['disallowed_claims'])}

RULES:
1. Output ONLY valid JSON matching the exact schema below
2. Be practical, specific, and genuinely useful
3. Write for a real person searching for "{topic['keyword']}"
4. Include realistic limitations and edge cases
5. Do NOT use generic filler phrases like "in today's digital world"
6. Do NOT invent statistics, testimonials, or social proof
7. Do NOT keyword-stuff - use the keyword naturally
8. Each FAQ answer must be at least 50 characters with real substance
9. Each section item must be specific, not generic
10. The content must stand on its own as genuinely helpful information
11. Include at least 2 realistic limitations
12. Meta title must be under 70 characters
13. Meta description must be 50-170 characters

CANONICAL URL: {DEFAULT_CANONICAL_BASE_URL}/resources/{topic['slug']}

OUTPUT THE FOLLOWING JSON EXACTLY (no markdown, no explanation, just the JSON object):

{{
  "slug": "{topic['slug']}",
  "title": "...",
  "metaTitle": "...",
  "metaDescription": "...",
  "h1": "...",
  "primaryKeyword": "{topic['keyword']}",
  "secondaryKeywords": ["...", "...", "..."],
  "searchIntent": "{topic['intent']}",
  "templateType": "{topic['template']}",
  "indexationStatus": "draft",
  "canonicalUrl": "{DEFAULT_CANONICAL_BASE_URL}/resources/{topic['slug']}",
  "hero": {{
    "headline": "...",
    "subheadline": "...",
    "primaryCta": "Try It Free",
    "secondaryCta": "Browse Resources"
  }},
  "summary": "...",
  "whoItsFor": ["...", "...", "..."],
  "whenThisIsRelevant": ["...", "...", "..."],
  "supportedInputs": ["...", "...", "..."],
  "expectedOutputs": ["...", "..."],
  "commonChallenges": ["...", "...", "...", "..."],
  "howItWorksSteps": ["...", "...", "...", "..."],
  "whyPdfExcelAiFits": ["...", "...", "...", "..."],
  "limitations": ["...", "...", "..."],
  "faq": [
    {{"question": "...", "answer": "..."}},
    {{"question": "...", "answer": "..."}},
    {{"question": "...", "answer": "..."}},
    {{"question": "...", "answer": "..."}}
  ],
  "relatedResources": [],
  "relatedProductLinks": [{{"label": "Convert PDF to Excel", "url": "/"}}],
  "trustSignals": ["...", "...", "...", "..."],
  "exampleUseCases": ["...", "...", "...", "..."],
  "qualityReview": {{
    "intentMatchScore": 0,
    "uniquenessScore": 0,
    "thinContentRisk": 0,
    "duplicationRisk": 0,
    "productTruthfulnessScore": 0,
    "helpfulnessScore": 0,
    "indexRecommendation": "noindex",
    "reasons": []
  }}
}}"""


def _extract_json(text: str) -> str | None:
    """Extract JSON object from response text."""
    # Try direct parse first
    text = text.strip()
    if text.startswith("{"):
        return text

    # Try to find JSON in markdown code blocks
    import re
    match = re.search(r'```(?:json)?\s*(\{.*?\})\s*```', text, re.DOTALL)
    if match:
        return match.group(1)

    # Try to find any JSON object
    match = re.search(r'\{.*\}', text, re.DOTALL)
    if match:
        return match.group(0)

    return None
