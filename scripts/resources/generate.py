"""Content generation using Claude API in constrained schema-first mode."""

import json
import os
import sys
from typing import Any

from .config import PRODUCT_CAPABILITIES, DEFAULT_CANONICAL_BASE_URL, CLAUDE_API_KEY
from .schema import validate_schema, EDITORIAL_TEMPLATES


def generate_resource(topic: dict[str, Any]) -> dict[str, Any] | None:
    """Generate a resource page using Claude API in constrained schema mode.

    Returns the generated resource data, or None if generation fails.
    """
    api_key = CLAUDE_API_KEY or os.getenv("CLAUDE_API_KEY", "")
    if not api_key:
        print("[generate] No CLAUDE_API_KEY set, skipping AI generation")
        return None

    is_editorial = topic.get("template") in EDITORIAL_TEMPLATES
    prompt = _build_editorial_prompt(topic) if is_editorial else _build_generation_prompt(topic)
    max_tokens = 8192 if is_editorial else 4096

    try:
        import anthropic
        client = anthropic.Anthropic(api_key=api_key)
        response = client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=max_tokens,
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
    return f"""You are generating structured content for a resource page on gridpull.com.

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


def _build_editorial_prompt(topic: dict[str, Any]) -> str:
    """Build generation prompt for editorial content (guides, insights).

    These are genuinely educational articles — NOT product pitches. The content
    must be valuable on its own, establishing topical authority for SEO.
    """
    return f"""You are an expert technical writer creating an original, in-depth article
for the resources section of gridpull.com — a tool that converts PDFs to Excel.

CRITICAL: This is an EDUCATIONAL ARTICLE, not a product page. Write as a subject
matter expert teaching something genuinely useful. The article must be valuable
even if the reader never uses our product.

TARGET:
- Primary keyword: {topic['keyword']}
- Slug: {topic['slug']}
- Template type: {topic['template']}
- Search intent: {topic['intent']}
- Article angle: {topic['angle']}

WRITING GUIDELINES:
1. Write like an expert explaining to a colleague — authoritative but accessible
2. Include specific, concrete details that demonstrate real expertise
3. Explain the "why" behind things, not just the "what"
4. Acknowledge trade-offs and nuance — avoid absolutist claims
5. Use real-world examples and scenarios throughout
6. When discussing techniques, explain how they actually work (not just what they do)
7. Be honest about limitations of ALL approaches, including AI-based ones
8. Include practical tips that readers can apply immediately

WHAT TO AVOID:
- Do NOT write marketing copy or sales language
- Do NOT use phrases like "in today's digital world", "game-changer", "revolutionary"
- Do NOT invent statistics, studies, or benchmarks — only reference generally known facts
- Do NOT make the article about gridpull.com — the product is mentioned ONLY in a
  brief note at the end, naturally, as one option among approaches discussed
- Do NOT use "we" or "our" when referring to the product in the article body
- Do NOT keyword-stuff — use the keyword naturally, not in every paragraph

PRODUCT CONTEXT (for the brief mention only):
gridpull.com uses AI to extract fields from PDFs/images into structured Excel/CSV.
It supports digital PDFs, scanned docs, and images. Free to start.

ARTICLE STRUCTURE — Each "sections" entry must be a substantial paragraph (150-400 words)
that teaches something real. Aim for 4-6 sections total that build on each other logically.

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
    "primaryCta": "Read the Guide",
    "secondaryCta": "Browse Resources"
  }},
  "summary": "A 2-3 sentence overview of what this article covers and why it matters. 100-250 chars.",
  "whoItsFor": ["Audience 1", "Audience 2", "Audience 3"],
  "sections": [
    {{
      "heading": "Clear, descriptive section heading",
      "body": "Substantial paragraph (150-400 words) that teaches something real. Use concrete examples. Explain concepts thoroughly. This should read like expert-written prose, not bullet points converted to sentences."
    }},
    {{
      "heading": "Another section heading",
      "body": "Another substantial section..."
    }},
    {{
      "heading": "Another section heading",
      "body": "Another substantial section..."
    }},
    {{
      "heading": "Another section heading",
      "body": "Another substantial section..."
    }}
  ],
  "faq": [
    {{"question": "A question a real person would ask about this topic?", "answer": "A thorough, expert answer (100+ chars). Be specific and practical."}},
    {{"question": "...", "answer": "..."}},
    {{"question": "...", "answer": "..."}},
    {{"question": "...", "answer": "..."}}
  ],
  "limitations": ["Honest limitation or caveat about the topic discussed"],
  "relatedResources": [],
  "relatedProductLinks": [{{"label": "Try PDF to Excel", "url": "/"}}],
  "trustSignals": [],
  "whoItsFor": ["...", "...", "..."],
  "whenThisIsRelevant": [],
  "supportedInputs": [],
  "expectedOutputs": [],
  "commonChallenges": [],
  "howItWorksSteps": [],
  "whyPdfExcelAiFits": [],
  "exampleUseCases": [],
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
