#!/usr/bin/env python3
"""Main cron entry point for the resources SEO pipeline.

Usage:
    python -m scripts.resources.cron              # Full pipeline
    python -m scripts.resources.cron --discover    # Discovery only
    python -m scripts.resources.cron --generate    # Generate only (requires CLAUDE_API_KEY)
    python -m scripts.resources.cron --publish     # Publish drafted candidates
    python -m scripts.resources.cron --sitemap     # Regenerate sitemap only
    python -m scripts.resources.cron --prerender   # Re-generate all pre-rendered HTML pages
    python -m scripts.resources.cron --seed        # Generate and publish seed content
"""

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from scripts.resources.config import (
    CRON_ENABLED, MAX_CANDIDATES_PER_RUN, LOGS_DIR, DRAFTS_DIR,
)
from scripts.resources.discover import discover_topics
from scripts.resources.generate import generate_resource
from scripts.resources.publish import publish_pipeline, set_related_resources
from scripts.resources.sitemap_generator import generate_sitemap
from scripts.resources.prerender import prerender_all
from scripts.resources.schema import load_resource


def main():
    parser = argparse.ArgumentParser(description="Resources SEO cron pipeline")
    parser.add_argument("--discover", action="store_true", help="Run topic discovery only")
    parser.add_argument("--generate", action="store_true", help="Generate content only")
    parser.add_argument("--publish", action="store_true", help="Publish drafted candidates")
    parser.add_argument("--sitemap", action="store_true", help="Regenerate sitemap only")
    parser.add_argument("--prerender", action="store_true", help="Re-generate all pre-rendered HTML pages")
    parser.add_argument("--seed", action="store_true", help="Generate and publish initial seed content")
    args = parser.parse_args()

    if not CRON_ENABLED and not args.seed:
        print("[cron] Resources cron is disabled (RESOURCES_CRON_ENABLED=false)")
        return

    run_id = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    log = {"run_id": run_id, "started": datetime.now(timezone.utc).isoformat()}

    try:
        if args.discover:
            topics = discover_topics(MAX_CANDIDATES_PER_RUN)
            log["discovered"] = len(topics)
            log["topics"] = [{"slug": t["slug"], "keyword": t["keyword"], "score": t["opportunity_score"]} for t in topics]
            print(f"[cron] Discovered {len(topics)} topic opportunities:")
            for t in topics:
                print(f"  - {t['slug']} ({t['keyword']}) score={t['opportunity_score']}")

        elif args.generate:
            topics = discover_topics(MAX_CANDIDATES_PER_RUN)
            candidates = []
            for topic in topics:
                print(f"[cron] Generating: {topic['slug']}...")
                result = generate_resource(topic)
                if result:
                    candidates.append(result)
                    print(f"  -> Generated successfully")
                else:
                    print(f"  -> Generation failed")
            log["generated"] = len(candidates)
            log["topics_attempted"] = len(topics)

        elif args.publish:
            # Publish existing drafts
            candidates = []
            for path in DRAFTS_DIR.glob("*.json"):
                data = load_resource(path)
                if data:
                    candidates.append(data)

            if not candidates:
                print("[cron] No draft candidates to publish")
                return

            candidates = set_related_resources(candidates)
            results = publish_pipeline(candidates)
            log["publish_results"] = results
            _print_results(results)

        elif args.sitemap:
            path = generate_sitemap()
            print(f"[cron] Sitemap generated: {path}")
            log["sitemap"] = path

        elif args.prerender:
            print("[cron] Pre-rendering all resource pages...")
            results = prerender_all()
            log["prerender_results"] = {
                "hub": results.get("hub", False),
                "pages": len(results.get("resources", [])),
                "errors": results.get("errors", []),
            }
            print(f"[cron] Pre-rendered {len(results.get('resources', []))} resource pages")

        elif args.seed:
            print("[cron] Running seed content pipeline...")
            _run_seed_pipeline(log)

        else:
            # Full pipeline
            print("[cron] Running full pipeline...")

            candidates = []

            # 1. Discover new topics
            topics = discover_topics(MAX_CANDIDATES_PER_RUN)
            print(f"[cron] Discovered {len(topics)} topics")
            log["discovered"] = len(topics)

            if topics:
                # 2. Generate new content
                generation_errors = []
                for topic in topics:
                    print(f"[cron] Generating: {topic['slug']}...")
                    result = generate_resource(topic)
                    if result:
                        candidates.append(result)
                        print(f"  -> Generated successfully")
                    else:
                        generation_errors.append(topic['slug'])
                        print(f"  -> FAILED to generate")
                log["generated"] = len(candidates)
                log["generation_failures"] = generation_errors

                if topics and not candidates:
                    msg = f"[cron] FATAL: All {len(topics)} generations failed. Check CLAUDE_API_KEY and API connectivity."
                    print(msg)
                    log["status"] = "all_generation_failed"
                    log["error"] = msg
                    sys.exit(1)

                print(f"[cron] Generated {len(candidates)}/{len(topics)} candidates")

            # 3. Load existing drafts for publishing
            draft_candidates = []
            for path in DRAFTS_DIR.glob("*.json"):
                data = load_resource(path)
                if data and data.get("slug") not in {c.get("slug") for c in candidates}:
                    draft_candidates.append(data)

            if draft_candidates:
                print(f"[cron] Found {len(draft_candidates)} existing drafts to retry")
                candidates.extend(draft_candidates)
                log["drafts_retried"] = len(draft_candidates)

            if not candidates:
                print("[cron] No new topics and no drafts to publish")
                log["status"] = "no_topics"
                return

            # 4. Set internal links
            candidates = set_related_resources(candidates)

            # 5. Publish
            results = publish_pipeline(candidates)
            log["publish_results"] = results
            _print_results(results)

            # Check if anything was actually published
            total_published = len(results.get("published_index", [])) + len(results.get("published_noindex", []))
            log["total_published"] = total_published
            if total_published == 0:
                print(f"[cron] WARNING: {len(candidates)} candidates generated but 0 published.")
                print(f"[cron] Rejected: {len(results.get('rejected', []))}, Drafted: {len(results.get('drafted', []))}")
                for r in results.get("rejected", []):
                    print(f"  REJECTED {r['slug']}: {r.get('reason', r.get('gate_failures', ''))}")
                for d in results.get("drafted", []):
                    print(f"  DRAFTED {d['slug']}: {d.get('reason', '')}")

    except Exception as e:
        log["error"] = str(e)
        print(f"[cron] Error: {e}")
        import traceback
        traceback.print_exc()

    finally:
        log["completed"] = datetime.now(timezone.utc).isoformat()
        _save_log(log, run_id)


def _run_seed_pipeline(log: dict):
    """Run the seed content pipeline using pre-generated content."""
    from scripts.resources.seed_content import generate_seed_content

    print("[seed] Generating seed content...")
    candidates = generate_seed_content()
    print(f"[seed] Generated {len(candidates)} seed candidates")

    # Set related resources
    candidates = set_related_resources(candidates)

    # Publish
    results = publish_pipeline(candidates)
    log["seed_results"] = results
    _print_results(results)


def _print_results(results: dict):
    """Print publish pipeline results."""
    pub_idx = results.get("published_index", [])
    pub_noi = results.get("published_noindex", [])
    drafted = results.get("drafted", [])
    rejected = results.get("rejected", [])

    print(f"\n[cron] Results:")
    print(f"  Published (indexable): {len(pub_idx)}")
    for p in pub_idx:
        print(f"    - {p['slug']} (scores: {p.get('scores', {})})")
    print(f"  Published (noindex): {len(pub_noi)}")
    for p in pub_noi:
        print(f"    - {p['slug']}")
    print(f"  Drafted: {len(drafted)}")
    for d in drafted:
        print(f"    - {d['slug']}: {d.get('reason', '')}")
    print(f"  Rejected: {len(rejected)}")
    for r in rejected:
        print(f"    - {r['slug']}: {r.get('reason', r.get('gate_failures', ''))}")


def _save_log(log: dict, run_id: str):
    """Save cron run log."""
    log_path = LOGS_DIR / f"run_{run_id}.json"
    log_path.write_text(json.dumps(log, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"[cron] Log saved: {log_path}")


if __name__ == "__main__":
    main()
