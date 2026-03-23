"""Publishing pipeline for resource content."""

import json
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .config import (
    PUBLISHED_DIR, DRAFTS_DIR, REJECTED_DIR, FRONTEND_PUBLIC,
    MAX_PUBLISHES_PER_RUN, MAX_INDEXABLE_PUBLISHES_PER_RUN,
    ALLOW_NOINDEX_PUBLISH, DEFAULT_CANONICAL_BASE_URL,
)
from .schema import validate_schema, save_resource, load_resource
from .quality_scorer import score_resource, passes_quality_gates
from .duplicate_checker import check_duplication
from .sitemap_generator import generate_sitemap
from .prerender import prerender_single


def publish_pipeline(candidates: list[dict[str, Any]]) -> dict[str, Any]:
    """Run the full publish pipeline on a list of candidate resources.

    Returns a summary of what was published, rejected, and drafted.
    """
    results = {
        "published_index": [],
        "published_noindex": [],
        "drafted": [],
        "rejected": [],
        "errors": [],
    }

    published_count = 0
    indexable_count = 0

    # Load existing resources for duplication checking
    existing = _load_all_published()

    for candidate in candidates:
        slug = candidate.get("slug", "unknown")

        # 1. Schema validation
        schema_errors = validate_schema(candidate)
        if schema_errors:
            candidate["qualityReview"] = candidate.get("qualityReview", {})
            candidate["qualityReview"]["reasons"] = schema_errors
            candidate["indexationStatus"] = "rejected"
            save_resource(candidate, REJECTED_DIR / f"{slug}.json")
            results["rejected"].append({"slug": slug, "reason": f"Schema errors: {schema_errors}"})
            continue

        # 2. Quality scoring
        quality = score_resource(candidate)

        # 3. Duplication check
        dup_risk, dup_reasons = check_duplication(candidate, existing)
        quality["duplicationRisk"] = dup_risk
        quality["reasons"].extend(dup_reasons)

        # Re-evaluate index recommendation with duplication
        from .config import MAX_DUPLICATION_RISK
        if dup_risk > MAX_DUPLICATION_RISK:
            quality["indexRecommendation"] = "noindex"
            quality["reasons"].append(f"Duplication risk ({dup_risk}) exceeds threshold ({MAX_DUPLICATION_RISK})")

        candidate["qualityReview"] = quality

        # 4. Check quality gates
        passes_index, passes_noindex, gate_failures = passes_quality_gates(quality)

        # 5. Quota checks
        if published_count >= MAX_PUBLISHES_PER_RUN:
            candidate["indexationStatus"] = "draft"
            save_resource(candidate, DRAFTS_DIR / f"{slug}.json")
            results["drafted"].append({"slug": slug, "reason": "Publish quota reached"})
            continue

        # 6. Publish decision
        now = datetime.now(timezone.utc).isoformat()

        if passes_index and indexable_count < MAX_INDEXABLE_PUBLISHES_PER_RUN:
            candidate["indexationStatus"] = "published"
            candidate["publishedAt"] = now
            candidate["updatedAt"] = now
            candidate["canonicalUrl"] = f"{DEFAULT_CANONICAL_BASE_URL}/resources/{slug}"
            save_resource(candidate, PUBLISHED_DIR / f"{slug}.json")
            _deploy_to_frontend(candidate)
            _remove_draft(slug)
            existing.append(candidate)
            published_count += 1
            indexable_count += 1
            results["published_index"].append({"slug": slug, "scores": _summary_scores(quality)})

        elif passes_noindex and ALLOW_NOINDEX_PUBLISH:
            candidate["indexationStatus"] = "noindex"
            candidate["publishedAt"] = now
            candidate["updatedAt"] = now
            candidate["canonicalUrl"] = f"{DEFAULT_CANONICAL_BASE_URL}/resources/{slug}"
            save_resource(candidate, PUBLISHED_DIR / f"{slug}.json")
            _deploy_to_frontend(candidate)
            _remove_draft(slug)
            existing.append(candidate)
            published_count += 1
            results["published_noindex"].append({
                "slug": slug,
                "scores": _summary_scores(quality),
                "gate_failures": gate_failures,
            })

        elif gate_failures:
            candidate["indexationStatus"] = "rejected"
            save_resource(candidate, REJECTED_DIR / f"{slug}.json")
            results["rejected"].append({"slug": slug, "gate_failures": gate_failures})

        else:
            candidate["indexationStatus"] = "draft"
            save_resource(candidate, DRAFTS_DIR / f"{slug}.json")
            results["drafted"].append({"slug": slug, "reason": "Did not pass quality gates"})

    # Update registry and sitemap
    _update_registry(existing)
    generate_sitemap()

    return results


def _deploy_to_frontend(resource: dict[str, Any]) -> None:
    """Copy resource JSON to the frontend public directory and pre-render for SEO."""
    slug = resource["slug"]
    save_resource(resource, FRONTEND_PUBLIC / f"{slug}.json")
    # Pre-render static HTML so crawlers get full content without JS
    prerender_single(resource)


def _remove_draft(slug: str) -> None:
    """Remove a draft file after successful publishing."""
    draft_path = DRAFTS_DIR / f"{slug}.json"
    if draft_path.exists():
        draft_path.unlink()


def _update_registry(resources: list[dict[str, Any]]) -> None:
    """Update the resources registry file used by the frontend hub."""
    published = [r for r in resources if r.get("indexationStatus") in ("published", "noindex")]

    registry = {
        "lastUpdated": datetime.now(timezone.utc).isoformat(),
        "totalPublished": len(published),
        "resources": [
            {
                "slug": r["slug"],
                "title": r["title"],
                "metaDescription": r["metaDescription"],
                "templateType": r["templateType"],
                "primaryKeyword": r["primaryKeyword"],
                "indexationStatus": r["indexationStatus"],
                "publishedAt": r.get("publishedAt", ""),
                "category": r["templateType"],
            }
            for r in sorted(published, key=lambda x: x.get("publishedAt", ""), reverse=True)
        ],
    }

    registry_path = FRONTEND_PUBLIC / "registry.json"
    registry_path.write_text(json.dumps(registry, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def _load_all_published() -> list[dict[str, Any]]:
    """Load all published resources."""
    resources = []
    for path in PUBLISHED_DIR.glob("*.json"):
        data = load_resource(path)
        if data:
            resources.append(data)
    return resources


def _summary_scores(quality: dict[str, Any]) -> dict[str, Any]:
    """Extract key scores for reporting."""
    return {
        "intent": quality.get("intentMatchScore"),
        "uniqueness": quality.get("uniquenessScore"),
        "thinRisk": quality.get("thinContentRisk"),
        "dupRisk": quality.get("duplicationRisk"),
        "truthfulness": quality.get("productTruthfulnessScore"),
        "helpfulness": quality.get("helpfulnessScore"),
        "recommendation": quality.get("indexRecommendation"),
    }


def set_related_resources(resources: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Set related resources links using ALL published articles plus current candidates.

    This ensures every new article links to existing published content (and vice versa),
    building the internal link graph that Google values for SEO.
    """
    # Combine current candidates with all existing published articles
    existing = _load_all_published()
    existing_slugs = {r["slug"] for r in existing}
    all_resources = list(existing)
    for r in resources:
        if r["slug"] not in existing_slugs:
            all_resources.append(r)

    # Build slug-to-type index for all resources
    slugs_by_type: dict[str, list[str]] = {}
    for r in all_resources:
        t = r.get("templateType", "")
        if t not in slugs_by_type:
            slugs_by_type[t] = []
        slugs_by_type[t].append(r["slug"])

    # Only set related resources on the current candidates (not re-writing existing)
    for r in resources:
        related = []
        own_slug = r["slug"]
        own_type = r.get("templateType", "")

        # Add same-type resources (up to 2)
        same_type = [s for s in slugs_by_type.get(own_type, []) if s != own_slug]
        related.extend(same_type[:2])

        # Add cross-type resources (up to 2)
        for t, slugs in slugs_by_type.items():
            if t != own_type:
                cross = [s for s in slugs if s != own_slug and s not in related]
                related.extend(cross[:1])
            if len(related) >= 4:
                break

        r["relatedResources"] = related[:4]

    return resources
