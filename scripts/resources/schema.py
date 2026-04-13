"""JSON schema validation for resource content."""

import json
from pathlib import Path
from typing import Any

RESOURCE_SCHEMA = {
    "type": "object",
    "required": [
        "slug", "title", "metaTitle", "metaDescription", "h1",
        "primaryKeyword", "secondaryKeywords", "searchIntent",
        "templateType", "indexationStatus", "canonicalUrl",
        "hero", "summary", "whoItsFor", "whenThisIsRelevant",
        "supportedInputs", "expectedOutputs", "commonChallenges",
        "howItWorksSteps", "whyPdfExcelAiFits", "limitations",
        "faq", "relatedResources", "relatedProductLinks",
        "trustSignals", "exampleUseCases", "qualityReview"
    ],
    "properties": {
        "slug": {"type": "string", "minLength": 3, "maxLength": 80},
        "title": {"type": "string", "minLength": 10, "maxLength": 120},
        "metaTitle": {"type": "string", "minLength": 10, "maxLength": 80},
        "metaDescription": {"type": "string", "minLength": 50, "maxLength": 170},
        "h1": {"type": "string", "minLength": 10, "maxLength": 100},
        "primaryKeyword": {"type": "string", "minLength": 3},
        "secondaryKeywords": {"type": "array", "items": {"type": "string"}, "minItems": 2},
        "searchIntent": {"type": "string", "enum": [
            "informational", "transactional", "commercial", "navigational"
        ]},
        "templateType": {"type": "string", "enum": [
            "file_conversion", "document_type", "workflow",
            "use_case", "comparison", "support_education"
        ]},
        "indexationStatus": {"type": "string", "enum": [
            "draft", "published", "noindex", "rejected"
        ]},
        "canonicalUrl": {"type": "string"},
        "hero": {
            "type": "object",
            "required": ["headline", "subheadline", "primaryCta"],
            "properties": {
                "headline": {"type": "string", "minLength": 10},
                "subheadline": {"type": "string", "minLength": 20},
                "primaryCta": {"type": "string"},
                "secondaryCta": {"type": "string"},
            },
        },
        "summary": {"type": "string", "minLength": 80},
        "whoItsFor": {"type": "array", "items": {"type": "string"}},
        "whenThisIsRelevant": {"type": "array", "items": {"type": "string"}},
        "supportedInputs": {"type": "array", "items": {"type": "string"}},
        "expectedOutputs": {"type": "array", "items": {"type": "string"}},
        "commonChallenges": {"type": "array", "items": {"type": "string"}},
        "howItWorksSteps": {"type": "array", "items": {"type": "string"}},
        "whyPdfExcelAiFits": {"type": "array", "items": {"type": "string"}},
        "limitations": {"type": "array", "items": {"type": "string"}},
        "faq": {
            "type": "array",
            "items": {
                "type": "object",
                "required": ["question", "answer"],
                "properties": {
                    "question": {"type": "string", "minLength": 10},
                    "answer": {"type": "string", "minLength": 20},
                },
            },
        },
        "relatedResources": {"type": "array", "items": {"type": "string"}},
        "relatedProductLinks": {
            "type": "array",
            "items": {
                "type": "object",
                "required": ["label", "url"],
                "properties": {
                    "label": {"type": "string"},
                    "url": {"type": "string"},
                },
            },
        },
        "trustSignals": {"type": "array", "items": {"type": "string"}},
        "exampleUseCases": {"type": "array", "items": {"type": "string"}},
        "sections": {
            "type": "array",
            "items": {
                "type": "object",
                "required": ["heading", "body"],
                "properties": {
                    "heading": {"type": "string", "minLength": 5},
                    "body": {"type": "string", "minLength": 100},
                },
            },
        },
        "qualityReview": {
            "type": "object",
            "required": [
                "intentMatchScore", "uniquenessScore", "thinContentRisk",
                "duplicationRisk", "productTruthfulnessScore",
                "helpfulnessScore", "indexRecommendation", "reasons"
            ],
        },
    },
}


EDITORIAL_REQUIRED = [
    "slug", "title", "metaTitle", "metaDescription", "h1",
    "primaryKeyword", "secondaryKeywords", "searchIntent",
    "templateType", "indexationStatus", "canonicalUrl",
    "hero", "summary", "whoItsFor", "sections",
    "faq", "relatedResources", "qualityReview"
]

EDITORIAL_TEMPLATES = {"guide", "industry_insight"}


def validate_schema(data: dict[str, Any]) -> list[str]:
    """Validate resource data against the schema. Returns list of error strings."""
    errors = []

    # Check required top-level fields (editorial templates have different requirements)
    template_type = data.get("templateType", "")
    required = EDITORIAL_REQUIRED if template_type in EDITORIAL_TEMPLATES else RESOURCE_SCHEMA["required"]
    for field in required:
        if field not in data:
            errors.append(f"Missing required field: {field}")

    if errors:
        return errors

    props = RESOURCE_SCHEMA["properties"]

    # String validations
    for field_name in ["slug", "title", "metaTitle", "metaDescription", "h1",
                       "primaryKeyword", "summary"]:
        val = data.get(field_name, "")
        spec = props.get(field_name, {})
        if not isinstance(val, str):
            errors.append(f"{field_name} must be a string")
            continue
        min_len = spec.get("minLength", 0)
        max_len = spec.get("maxLength", 10000)
        if len(val) < min_len:
            errors.append(f"{field_name} too short (min {min_len}, got {len(val)})")
        if len(val) > max_len:
            errors.append(f"{field_name} too long (max {max_len}, got {len(val)})")

    # Enum validations
    if data.get("searchIntent") not in ["informational", "transactional", "commercial", "navigational"]:
        errors.append(f"Invalid searchIntent: {data.get('searchIntent')}")
    if data.get("templateType") not in [
        "file_conversion", "document_type", "workflow",
        "use_case", "comparison", "support_education",
        "guide", "industry_insight"
    ]:
        errors.append(f"Invalid templateType: {data.get('templateType')}")
    if data.get("indexationStatus") not in ["draft", "published", "noindex", "rejected"]:
        errors.append(f"Invalid indexationStatus: {data.get('indexationStatus')}")

    # Array validations
    for field_name in ["secondaryKeywords", "whoItsFor", "whenThisIsRelevant",
                       "supportedInputs", "expectedOutputs", "commonChallenges",
                       "howItWorksSteps", "whyPdfExcelAiFits", "limitations",
                       "faq", "relatedResources", "trustSignals", "exampleUseCases"]:
        val = data.get(field_name)
        if not isinstance(val, list):
            errors.append(f"{field_name} must be an array")

    # Hero validation
    hero = data.get("hero", {})
    if not isinstance(hero, dict):
        errors.append("hero must be an object")
    else:
        for field in ["headline", "subheadline", "primaryCta"]:
            if not hero.get(field):
                errors.append(f"hero.{field} is required")

    # FAQ validation
    faq = data.get("faq", [])
    if isinstance(faq, list):
        for i, item in enumerate(faq):
            if not isinstance(item, dict):
                errors.append(f"faq[{i}] must be an object")
            elif not item.get("question") or not item.get("answer"):
                errors.append(f"faq[{i}] missing question or answer")

    # Quality review validation
    qr = data.get("qualityReview", {})
    if isinstance(qr, dict):
        for field in ["intentMatchScore", "uniquenessScore", "thinContentRisk",
                      "duplicationRisk", "productTruthfulnessScore",
                      "helpfulnessScore"]:
            val = qr.get(field)
            if not isinstance(val, (int, float)):
                errors.append(f"qualityReview.{field} must be a number")
            elif not (0 <= val <= 100):
                errors.append(f"qualityReview.{field} must be 0-100")
        if qr.get("indexRecommendation") not in ["index", "noindex"]:
            errors.append(f"qualityReview.indexRecommendation invalid")

    # Sections validation (for editorial content)
    sections = data.get("sections", [])
    if isinstance(sections, list):
        for i, item in enumerate(sections):
            if not isinstance(item, dict):
                errors.append(f"sections[{i}] must be an object")
            elif not item.get("heading") or not item.get("body"):
                errors.append(f"sections[{i}] missing heading or body")
            elif isinstance(item.get("body"), str) and len(item["body"]) < 100:
                errors.append(f"sections[{i}] body too short (min 100 chars, got {len(item['body'])})")

    # Slug format
    slug = data.get("slug", "")
    if isinstance(slug, str) and slug:
        import re
        if not re.match(r'^[a-z0-9][a-z0-9-]*[a-z0-9]$', slug):
            errors.append("slug must be lowercase alphanumeric with hyphens, not starting/ending with hyphen")

    return errors


def load_resource(path: Path) -> dict[str, Any] | None:
    """Load and parse a resource JSON file."""
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, FileNotFoundError, PermissionError):
        return None


def save_resource(data: dict[str, Any], path: Path) -> None:
    """Save resource data as formatted JSON."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
