"""Duplication detection for resource content."""

import json
import re
from pathlib import Path
from typing import Any

from .config import PUBLISHED_DIR


def check_duplication(data: dict[str, Any], existing_resources: list[dict[str, Any]] | None = None) -> tuple[int, list[str]]:
    """Check for duplication against existing published resources.

    Returns:
        (duplication_risk_score, reasons)
        - duplication_risk_score: 0-100, higher = more duplicate
        - reasons: list of duplication concerns
    """
    if existing_resources is None:
        existing_resources = _load_existing()

    if not existing_resources:
        return 0, ["No existing resources to compare against"]

    reasons = []
    max_risk = 0

    slug = data.get("slug", "")
    keyword = data.get("primaryKeyword", "").lower()
    title = data.get("title", "").lower()
    summary = data.get("summary", "").lower()

    for existing in existing_resources:
        if existing.get("slug") == slug:
            continue

        risk = 0
        ex_keyword = existing.get("primaryKeyword", "").lower()
        ex_title = existing.get("title", "").lower()
        ex_summary = existing.get("summary", "").lower()

        # Exact keyword match
        if keyword and keyword == ex_keyword:
            risk = 90
            reasons.append(f"Exact primary keyword match with '{existing.get('slug')}'")

        # High keyword overlap
        elif keyword and ex_keyword:
            keyword_similarity = _word_overlap(keyword, ex_keyword)
            # Different template types get a subtopic bonus (legitimate specialization)
            is_subtopic = existing.get("templateType") != data.get("templateType")
            if keyword_similarity > 0.85:
                risk = max(risk, 60 if is_subtopic else 70)
                reasons.append(f"Very high keyword overlap ({keyword_similarity:.0%}) with '{existing.get('slug')}'")
            elif keyword_similarity > 0.7:
                risk = max(risk, 30 if is_subtopic else 45)
                reasons.append(f"Moderate keyword overlap ({keyword_similarity:.0%}) with '{existing.get('slug')}'")

        # Title similarity
        if title and ex_title:
            title_similarity = _word_overlap(title, ex_title)
            if title_similarity > 0.8:
                risk = max(risk, 60)
                reasons.append(f"Very similar title to '{existing.get('slug')}'")

        # Summary similarity
        if summary and ex_summary:
            summary_similarity = _word_overlap(summary, ex_summary)
            if summary_similarity > 0.75:
                risk = max(risk, 50)
                reasons.append(f"Similar summary to '{existing.get('slug')}'")

        # Same template type + similar keyword = keyword swap risk
        if (existing.get("templateType") == data.get("templateType")
                and keyword and ex_keyword):
            if _is_keyword_swap(keyword, ex_keyword):
                risk = max(risk, 75)
                reasons.append(f"Possible keyword-swap of '{existing.get('slug')}'")

        max_risk = max(max_risk, risk)

    if not reasons:
        reasons.append("No significant duplication detected")

    return min(100, max_risk), reasons


def _word_overlap(text1: str, text2: str) -> float:
    """Calculate word-level Jaccard similarity between two texts."""
    words1 = set(_normalize_words(text1))
    words2 = set(_normalize_words(text2))
    if not words1 or not words2:
        return 0.0
    intersection = words1 & words2
    union = words1 | words2
    return len(intersection) / len(union)


def _normalize_words(text: str) -> list[str]:
    """Normalize text to word tokens, removing stop words."""
    stop_words = {"the", "a", "an", "to", "for", "and", "or", "in", "of", "on",
                  "with", "from", "by", "is", "are", "was", "were", "it", "its",
                  "this", "that", "your", "how", "what", "why", "when", "where"}
    words = re.findall(r'[a-z0-9]+', text.lower())
    return [w for w in words if w not in stop_words and len(w) > 1]


def _is_keyword_swap(kw1: str, kw2: str) -> bool:
    """Detect if two keywords are just swapped versions of each other.
    E.g., 'pdf to excel' vs 'pdf to csv' - same structure, different output.
    Only flags true swaps, not legitimate subtopics (e.g., 'invoice pdf to excel'
    is a legitimate subtopic of 'pdf to excel', not a swap).
    """
    words1 = _normalize_words(kw1)
    words2 = _normalize_words(kw2)

    if not words1 or not words2:
        return False

    # Keywords must be similar length to be swaps (±1 word)
    if abs(len(words1) - len(words2)) > 1:
        return False

    # If one keyword is a subset of the other (subtopic), it's not a swap
    set1, set2 = set(words1), set(words2)
    if set1.issubset(set2) or set2.issubset(set1):
        return False

    # True swap: same length, differ by exactly 1 word
    diff = set1.symmetric_difference(set2)
    shared = set1 & set2

    if len(diff) == 2 and len(shared) >= 2:
        return True

    return False


def _load_existing() -> list[dict[str, Any]]:
    """Load all published resource files."""
    resources = []
    for path in PUBLISHED_DIR.glob("*.json"):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            resources.append(data)
        except (json.JSONDecodeError, FileNotFoundError):
            continue
    return resources


def get_existing_slugs() -> set[str]:
    """Get set of all existing slugs across published, drafts, rejected."""
    slugs = set()
    for directory in [PUBLISHED_DIR, Path(PUBLISHED_DIR).parent / "drafts",
                      Path(PUBLISHED_DIR).parent / "rejected"]:
        if directory.exists():
            for path in directory.glob("*.json"):
                slugs.add(path.stem)
    return slugs
