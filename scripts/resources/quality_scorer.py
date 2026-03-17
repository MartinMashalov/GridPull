"""Quality scoring engine for resource content."""

from typing import Any

from .config import (
    PRODUCT_CAPABILITIES, TEMPLATE_TYPES,
    MIN_HELPFULNESS_SCORE, MIN_UNIQUENESS_SCORE, MAX_DUPLICATION_RISK,
    MIN_TRUTHFULNESS_SCORE, MIN_INTENT_MATCH_SCORE, MAX_THIN_CONTENT_RISK,
)


def score_resource(data: dict[str, Any]) -> dict[str, Any]:
    """Score a resource for quality. Returns the qualityReview object."""
    reasons = []
    template_type = data.get("templateType", "")
    template_config = TEMPLATE_TYPES.get(template_type, {})

    # 1. Intent match score
    intent_score = _score_intent_match(data, reasons)

    # 2. Uniqueness score (content quality, not duplication - that's separate)
    uniqueness_score = _score_uniqueness(data, reasons)

    # 3. Thin content risk
    thin_risk = _score_thin_content_risk(data, template_config, reasons)

    # 4. Product truthfulness
    truthfulness_score = _score_truthfulness(data, reasons)

    # 5. Helpfulness
    helpfulness_score = _score_helpfulness(data, template_config, reasons)

    # Determine index recommendation
    passes_all = (
        intent_score >= MIN_INTENT_MATCH_SCORE
        and uniqueness_score >= MIN_UNIQUENESS_SCORE
        and thin_risk <= MAX_THIN_CONTENT_RISK
        and truthfulness_score >= MIN_TRUTHFULNESS_SCORE
        and helpfulness_score >= MIN_HELPFULNESS_SCORE
    )

    return {
        "intentMatchScore": intent_score,
        "uniquenessScore": uniqueness_score,
        "thinContentRisk": thin_risk,
        "duplicationRisk": 0,  # Set by duplicate_checker separately
        "productTruthfulnessScore": truthfulness_score,
        "helpfulnessScore": helpfulness_score,
        "indexRecommendation": "index" if passes_all else "noindex",
        "reasons": reasons,
    }


def _score_intent_match(data: dict[str, Any], reasons: list[str]) -> int:
    """Score how well the content matches the stated search intent."""
    score = 100
    keyword = data.get("primaryKeyword", "").lower()
    title = data.get("title", "").lower()
    h1 = data.get("h1", "").lower()
    summary = data.get("summary", "").lower()

    # Check keyword presence using word-level matching (handles plurals/variants)
    def _keyword_present(keyword: str, text: str) -> bool:
        """Check if all significant keyword words appear in text."""
        import re
        stop = {"to", "a", "the", "and", "or", "for", "from", "with", "in", "of", "vs"}
        kw_words = [w for w in re.findall(r'[a-z0-9]+', keyword) if w not in stop and len(w) > 1]
        text_words = set(re.findall(r'[a-z0-9]+', text))
        # Allow plural/singular variants
        matched = sum(1 for w in kw_words if w in text_words or w + 's' in text_words or w.rstrip('s') in text_words)
        return matched >= len(kw_words) * 0.8  # 80% of keyword words must be present

    # Keyword should appear in title
    if keyword and not _keyword_present(keyword, title):
        score -= 15
        reasons.append("Primary keyword not in title")

    # Keyword should appear in h1
    if keyword and not _keyword_present(keyword, h1):
        score -= 10
        reasons.append("Primary keyword not in H1")

    # Keyword should appear in summary
    if keyword and not _keyword_present(keyword, summary):
        score -= 10
        reasons.append("Primary keyword not in summary")

    # Meta description should mention the keyword
    meta_desc = data.get("metaDescription", "").lower()
    if keyword and not _keyword_present(keyword, meta_desc):
        score -= 10
        reasons.append("Primary keyword not in meta description")

    # Search intent alignment
    intent = data.get("searchIntent", "")
    template = data.get("templateType", "")
    intent_template_map = {
        "transactional": ["file_conversion", "document_type"],
        "commercial": ["comparison", "use_case"],
        "informational": ["support_education", "workflow"],
    }
    expected_templates = intent_template_map.get(intent, [])
    if expected_templates and template not in expected_templates:
        score -= 5  # Minor penalty, not always wrong

    return max(0, min(100, score))


def _score_uniqueness(data: dict[str, Any], reasons: list[str]) -> int:
    """Score content uniqueness based on specificity and differentiation."""
    score = 100

    # Check if FAQ answers are substantive
    faq = data.get("faq", [])
    if faq:
        short_answers = sum(1 for f in faq if len(f.get("answer", "")) < 50)
        if short_answers > len(faq) / 2:
            score -= 20
            reasons.append("Many FAQ answers are too short to be useful")

    # Check for generic/boilerplate content signals
    summary = data.get("summary", "")
    generic_phrases = [
        "in today's digital world",
        "in this day and age",
        "it goes without saying",
        "as we all know",
        "game changer",
        "revolutionary",
        "cutting-edge",
        "state-of-the-art",
        "best-in-class",
        "world-class",
        "paradigm shift",
    ]
    for phrase in generic_phrases:
        if phrase in summary.lower():
            score -= 10
            reasons.append(f"Generic filler phrase detected: '{phrase}'")

    # Check that content sections have sufficient depth
    for field in ["whyPdfExcelAiFits", "commonChallenges", "howItWorksSteps"]:
        items = data.get(field, [])
        if items:
            avg_len = sum(len(str(item)) for item in items) / len(items)
            if avg_len < 30:
                score -= 10
                reasons.append(f"{field} items are too short (avg {avg_len:.0f} chars)")

    return max(0, min(100, score))


def _score_thin_content_risk(data: dict[str, Any], template_config: dict, reasons: list[str]) -> int:
    """Score thin content risk (higher = worse). 0 = no risk, 100 = very thin."""
    risk = 0

    # Check minimum section requirements
    min_faq = template_config.get("min_faq", 3)
    min_how = template_config.get("min_howItWorks", 3)
    min_challenges = template_config.get("min_challenges", 2)
    min_limitations = template_config.get("min_limitations", 2)

    faq_count = len(data.get("faq", []))
    how_count = len(data.get("howItWorksSteps", []))
    challenge_count = len(data.get("commonChallenges", []))
    limitation_count = len(data.get("limitations", []))

    if faq_count < min_faq:
        risk += 15
        reasons.append(f"Too few FAQ items ({faq_count} < {min_faq})")
    if how_count < min_how:
        risk += 15
        reasons.append(f"Too few how-it-works steps ({how_count} < {min_how})")
    if challenge_count < min_challenges:
        risk += 10
        reasons.append(f"Too few challenges ({challenge_count} < {min_challenges})")
    if limitation_count < min_limitations:
        risk += 15
        reasons.append(f"Too few limitations ({limitation_count} < {min_limitations})")

    # Check required fields for template type
    required = template_config.get("required_fields", [])
    for field in required:
        val = data.get(field)
        if not val or (isinstance(val, list) and len(val) == 0):
            risk += 10
            reasons.append(f"Required field '{field}' is empty for template type")

    # Summary length check
    summary = data.get("summary", "")
    if len(summary) < 100:
        risk += 15
        reasons.append("Summary too short (< 100 chars)")

    # Total content volume check
    total_items = sum(
        len(data.get(f, []))
        for f in ["whoItsFor", "whenThisIsRelevant", "supportedInputs",
                   "expectedOutputs", "commonChallenges", "howItWorksSteps",
                   "whyPdfExcelAiFits", "limitations", "faq", "exampleUseCases"]
    )
    if total_items < 15:
        risk += 15
        reasons.append(f"Total content items too low ({total_items})")

    return max(0, min(100, risk))


def _score_truthfulness(data: dict[str, Any], reasons: list[str]) -> int:
    """Score product truthfulness. How accurately does content represent the product?"""
    score = 100

    # Check for disallowed claims
    all_text = _get_all_text(data).lower()
    for claim in PRODUCT_CAPABILITIES["disallowed_claims"]:
        if claim.lower() in all_text:
            score -= 20
            reasons.append(f"Disallowed claim detected: '{claim}'")

    # Check for exaggerated promises
    exaggeration_signals = [
        "100% accurate", "100% accuracy",
        "never fails", "always perfect",
        "guaranteed results", "zero errors",
        "unlimited free", "completely free forever",
        "replaces all human",
        "no limitations",
    ]
    for signal in exaggeration_signals:
        if signal in all_text:
            score -= 15
            reasons.append(f"Exaggeration detected: '{signal}'")

    # Check for fake testimonials or stats
    fake_signals = [
        "customers say", "users report",
        "studies show", "research proves",
        "according to our data",
        "our customers love",
    ]
    for signal in fake_signals:
        if signal in all_text:
            score -= 10
            reasons.append(f"Potential fake social proof: '{signal}'")

    # Must include limitations
    limitations = data.get("limitations", [])
    if len(limitations) < 1:
        score -= 15
        reasons.append("No limitations mentioned - likely not truthful")

    return max(0, min(100, score))


def _score_helpfulness(data: dict[str, Any], template_config: dict, reasons: list[str]) -> int:
    """Score how genuinely helpful the content would be to a real user."""
    score = 60  # Start at base, add points for good things

    # Has substantive FAQ
    faq = data.get("faq", [])
    if len(faq) >= 4:
        score += 8
    if faq and all(len(f.get("answer", "")) >= 50 for f in faq):
        score += 5

    # Has clear how-it-works
    how = data.get("howItWorksSteps", [])
    if len(how) >= 3:
        score += 8

    # Has real limitations (honesty = helpful)
    limitations = data.get("limitations", [])
    if len(limitations) >= 2:
        score += 8

    # Has who-its-for (targeting)
    if len(data.get("whoItsFor", [])) >= 2:
        score += 5

    # Has example use cases
    if len(data.get("exampleUseCases", [])) >= 2:
        score += 5

    # Has trust signals
    if len(data.get("trustSignals", [])) >= 2:
        score += 3

    # Has related resources (navigation help)
    if len(data.get("relatedResources", [])) >= 1:
        score += 3

    # Penalize keyword stuffing
    keyword = data.get("primaryKeyword", "").lower()
    if keyword:
        summary = data.get("summary", "").lower()
        keyword_count = summary.count(keyword)
        if keyword_count > 4:
            score -= 15
            reasons.append(f"Keyword stuffing in summary ({keyword_count} occurrences)")

    return max(0, min(100, score))


def _get_all_text(data: dict[str, Any]) -> str:
    """Extract all text content from a resource for analysis."""
    parts = [
        data.get("title", ""),
        data.get("summary", ""),
        data.get("h1", ""),
        data.get("metaDescription", ""),
    ]
    for field in ["whoItsFor", "whenThisIsRelevant", "supportedInputs",
                   "expectedOutputs", "commonChallenges", "howItWorksSteps",
                   "whyPdfExcelAiFits", "limitations", "exampleUseCases",
                   "trustSignals"]:
        parts.extend(data.get(field, []))
    for faq in data.get("faq", []):
        parts.append(faq.get("question", ""))
        parts.append(faq.get("answer", ""))
    return " ".join(str(p) for p in parts)


def passes_quality_gates(quality_review: dict[str, Any]) -> tuple[bool, bool, list[str]]:
    """Check if a resource passes quality gates.

    Returns:
        (passes_index, passes_noindex, failure_reasons)
        - passes_index: True if page can be published as indexable
        - passes_noindex: True if page can be published as noindex
        - failure_reasons: List of reasons for failures
    """
    failures = []

    intent = quality_review.get("intentMatchScore", 0)
    uniqueness = quality_review.get("uniquenessScore", 0)
    thin_risk = quality_review.get("thinContentRisk", 100)
    dup_risk = quality_review.get("duplicationRisk", 100)
    truthfulness = quality_review.get("productTruthfulnessScore", 0)
    helpfulness = quality_review.get("helpfulnessScore", 0)

    if intent < MIN_INTENT_MATCH_SCORE:
        failures.append(f"Intent match too low: {intent} < {MIN_INTENT_MATCH_SCORE}")
    if uniqueness < MIN_UNIQUENESS_SCORE:
        failures.append(f"Uniqueness too low: {uniqueness} < {MIN_UNIQUENESS_SCORE}")
    if thin_risk > MAX_THIN_CONTENT_RISK:
        failures.append(f"Thin content risk too high: {thin_risk} > {MAX_THIN_CONTENT_RISK}")
    if dup_risk > MAX_DUPLICATION_RISK:
        failures.append(f"Duplication risk too high: {dup_risk} > {MAX_DUPLICATION_RISK}")
    if truthfulness < MIN_TRUTHFULNESS_SCORE:
        failures.append(f"Truthfulness too low: {truthfulness} < {MIN_TRUTHFULNESS_SCORE}")
    if helpfulness < MIN_HELPFULNESS_SCORE:
        failures.append(f"Helpfulness too low: {helpfulness} < {MIN_HELPFULNESS_SCORE}")

    passes_index = len(failures) == 0
    # Noindex threshold is more lenient - allow if only minor issues
    passes_noindex = (
        truthfulness >= MIN_TRUTHFULNESS_SCORE - 5
        and helpfulness >= MIN_HELPFULNESS_SCORE - 10
        and dup_risk <= MAX_DUPLICATION_RISK + 10
    )

    return passes_index, passes_noindex, failures
