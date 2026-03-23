"""Pre-render resource pages as static HTML for SEO.

Generates individual HTML files for each published resource page so that
search engine crawlers receive fully-formed HTML with meta tags, structured
data, and article content — no JavaScript execution required.

Usage:
    python -m scripts.resources.prerender              # Pre-render all resources
    python -m scripts.resources.prerender --slug xyz    # Pre-render a single resource
"""

import json
import re
import sys
from html import escape
from pathlib import Path
from typing import Any

from .config import FRONTEND_PUBLIC, PUBLISHED_DIR, DEFAULT_CANONICAL_BASE_URL

# Paths
REPO_ROOT = Path(__file__).resolve().parent.parent.parent
FRONTEND_DIR = REPO_ROOT / "frontend"
DIST_DIR = FRONTEND_DIR / "dist"

EDITORIAL_TEMPLATES = {"guide", "industry_insight"}

TEMPLATE_LABELS = {
    "file_conversion": "Conversion Guide",
    "document_type": "Document Guide",
    "workflow": "Workflow Guide",
    "use_case": "Use Case Guide",
    "comparison": "Comparison",
    "support_education": "Tutorial",
    "guide": "In-Depth Guide",
    "industry_insight": "Industry Insight",
}

CATEGORY_MAP = {
    "guide": "Guides &amp; How-Tos",
    "industry_insight": "Industry Insights",
    "file_conversion": "Conversion Guides",
    "document_type": "Document-Specific Guides",
    "workflow": "Workflow Automation",
    "use_case": "Use Cases",
    "comparison": "Comparisons",
    "support_education": "Tutorials",
}


def _e(text: str) -> str:
    """HTML-escape a string."""
    return escape(str(text), quote=True)


def _json_ld(obj: dict) -> str:
    """Render a JSON-LD script tag."""
    return f'<script type="application/ld+json">{json.dumps(obj, ensure_ascii=False)}</script>'


def _estimate_read_time(resource: dict) -> int:
    """Estimate read time in minutes."""
    total = 0
    for key in ["summary"]:
        total += len(str(resource.get(key, "")).split())
    for section in resource.get("sections", []):
        total += len(str(section.get("body", "")).split())
    for faq in resource.get("faq", []):
        total += len(str(faq.get("answer", "")).split())
    for key in ["whoItsFor", "commonChallenges", "howItWorksSteps",
                "whyPdfExcelAiFits", "limitations", "exampleUseCases"]:
        for item in resource.get(key, []):
            total += len(str(item).split())
    return max(1, round(total / 230))


def _build_head(resource: dict) -> str:
    """Build the <head> content for a resource page."""
    slug = resource["slug"]
    is_noindex = resource.get("indexationStatus") == "noindex"
    is_editorial = resource.get("templateType") in EDITORIAL_TEMPLATES
    page_url = f"{DEFAULT_CANONICAL_BASE_URL}/resources/{slug}"
    canonical = resource.get("canonicalUrl") or page_url

    # Structured data
    breadcrumb_schema = {
        "@context": "https://schema.org",
        "@type": "BreadcrumbList",
        "itemListElement": [
            {"@type": "ListItem", "position": 1, "name": "Home",
             "item": f"{DEFAULT_CANONICAL_BASE_URL}/"},
            {"@type": "ListItem", "position": 2, "name": "Resources",
             "item": f"{DEFAULT_CANONICAL_BASE_URL}/resources"},
            {"@type": "ListItem", "position": 3, "name": resource["title"],
             "item": page_url},
        ],
    }

    faq_schema = None
    if resource.get("faq"):
        faq_schema = {
            "@context": "https://schema.org",
            "@type": "FAQPage",
            "mainEntity": [
                {
                    "@type": "Question",
                    "name": f["question"],
                    "acceptedAnswer": {"@type": "Answer", "text": f["answer"]},
                }
                for f in resource["faq"]
            ],
        }

    article_schema = None
    if is_editorial:
        article_schema = {
            "@context": "https://schema.org",
            "@type": "Article",
            "headline": resource["h1"],
            "description": resource["metaDescription"],
            "datePublished": resource.get("publishedAt", ""),
            "dateModified": resource.get("updatedAt") or resource.get("publishedAt", ""),
            "publisher": {
                "@type": "Organization",
                "name": "PDFexcel.ai",
                "url": DEFAULT_CANONICAL_BASE_URL,
            },
            "mainEntityOfPage": canonical,
        }

    robots = "noindex, follow" if is_noindex else "index, follow"

    lines = [
        '<meta charset="UTF-8" />',
        '<meta name="viewport" content="width=device-width, initial-scale=1.0" />',
        # Analytics
        '<script async src="https://www.googletagmanager.com/gtag/js?id=G-K714WDYE3B"></script>',
        '<script>window.dataLayer=window.dataLayer||[];function gtag(){dataLayer.push(arguments);}gtag("js",new Date());gtag("config","G-K714WDYE3B");</script>',
        '<script async src="https://www.googletagmanager.com/gtag/js?id=AW-18021101114"></script>',
        '<script>window.dataLayer=window.dataLayer||[];function gtag(){dataLayer.push(arguments);}gtag("js",new Date());gtag("config","AW-18021101114");</script>',
        # Favicon
        '<link rel="icon" type="image/svg+xml" href="/grid-icon.svg" />',
        '<link rel="icon" type="image/png" sizes="192x192" href="/grid-icon.png" />',
        '<link rel="apple-touch-icon" sizes="180x180" href="/apple-touch-icon.png" />',
        '<link rel="manifest" href="/site.webmanifest" />',
        '<meta name="theme-color" content="#2563EB" />',
        # SEO
        f'<title>{_e(resource["metaTitle"])}</title>',
        f'<meta name="description" content="{_e(resource["metaDescription"])}" />',
        f'<meta name="robots" content="{robots}" />',
        f'<link rel="canonical" href="{_e(canonical)}" />',
        # Open Graph
        f'<meta property="og:title" content="{_e(resource["metaTitle"])}" />',
        f'<meta property="og:description" content="{_e(resource["metaDescription"])}" />',
        f'<meta property="og:url" content="{_e(page_url)}" />',
        '<meta property="og:type" content="article" />',
        '<meta property="og:site_name" content="PDFexcel.ai" />',
        f'<meta property="og:image" content="{DEFAULT_CANONICAL_BASE_URL}/og-image.png" />',
        '<meta property="og:image:width" content="1200" />',
        '<meta property="og:image:height" content="630" />',
        f'<meta property="og:image:alt" content="{_e(resource["metaTitle"])}" />',
    ]

    if resource.get("publishedAt"):
        lines.append(f'<meta property="article:published_time" content="{_e(resource["publishedAt"])}" />')
    if resource.get("updatedAt"):
        lines.append(f'<meta property="article:modified_time" content="{_e(resource["updatedAt"])}" />')

    lines.extend([
        # Twitter Card
        '<meta name="twitter:card" content="summary_large_image" />',
        f'<meta name="twitter:title" content="{_e(resource["metaTitle"])}" />',
        f'<meta name="twitter:description" content="{_e(resource["metaDescription"])}" />',
        f'<meta name="twitter:image" content="{DEFAULT_CANONICAL_BASE_URL}/og-image.png" />',
        f'<meta name="twitter:image:alt" content="{_e(resource["metaTitle"])}" />',
        # Structured data
        _json_ld(breadcrumb_schema),
    ])

    if faq_schema:
        lines.append(_json_ld(faq_schema))
    if article_schema:
        lines.append(_json_ld(article_schema))

    return "\n    ".join(lines)


def _build_body_content(resource: dict) -> str:
    """Build the semantic HTML body content for crawler consumption.

    This content sits inside <div id="root"> and is replaced by React on hydration.
    It provides full article content to search engines without JS execution.
    """
    slug = resource["slug"]
    is_editorial = resource.get("templateType") in EDITORIAL_TEMPLATES
    read_time = _estimate_read_time(resource)
    template_label = TEMPLATE_LABELS.get(resource.get("templateType", ""), resource.get("templateType", ""))

    parts = []
    parts.append('<div style="max-width:896px;margin:0 auto;padding:16px">')

    # Breadcrumbs
    parts.append('<nav aria-label="Breadcrumb">')
    parts.append(f'<a href="/">Home</a> &rsaquo; <a href="/resources">Resources</a> &rsaquo; <span>{_e(resource["title"])}</span>')
    parts.append('</nav>')

    # Article
    parts.append('<article>')

    # Hero
    parts.append(f'<span>{_e(template_label)}</span>')
    parts.append(f'<h1>{_e(resource["h1"])}</h1>')
    parts.append(f'<p>{_e(resource["hero"]["subheadline"])}</p>')

    if resource.get("publishedAt"):
        from datetime import datetime
        try:
            dt = datetime.fromisoformat(resource["publishedAt"].replace("Z", "+00:00"))
            date_str = dt.strftime("%B %d, %Y")
        except (ValueError, AttributeError):
            date_str = resource["publishedAt"]
        meta_parts = [f'<time datetime="{_e(resource["publishedAt"])}">{_e(date_str)}</time>']
        if is_editorial:
            meta_parts.append(f'<span>{read_time} min read</span>')
        parts.append(f'<div>{" &middot; ".join(meta_parts)}</div>')

    # Summary
    parts.append(f'<p><strong>{_e(resource["summary"])}</strong></p>')

    # Content sections for editorial templates
    if is_editorial and resource.get("sections"):
        for section in resource["sections"]:
            parts.append(f'<h2>{_e(section["heading"])}</h2>')
            # Preserve paragraph breaks
            for para in str(section.get("body", "")).split("\n"):
                para = para.strip()
                if para:
                    parts.append(f'<p>{_e(para)}</p>')

    # Standard product content sections
    _render_list_section(parts, resource, "whoItsFor", "Who This Is For")
    _render_list_section(parts, resource, "whenThisIsRelevant", "When This Is Relevant")
    _render_list_section(parts, resource, "supportedInputs", "Supported Inputs")
    _render_list_section(parts, resource, "expectedOutputs", "Expected Outputs")
    _render_list_section(parts, resource, "commonChallenges", "Common Challenges")

    # How it works as numbered list
    if resource.get("howItWorksSteps"):
        parts.append('<h2>How It Works</h2>')
        parts.append('<ol>')
        for step in resource["howItWorksSteps"]:
            parts.append(f'<li>{_e(step)}</li>')
        parts.append('</ol>')

    _render_list_section(parts, resource, "whyPdfExcelAiFits", "Why PDFexcel.ai")
    _render_list_section(parts, resource, "limitations", "Limitations")
    _render_list_section(parts, resource, "exampleUseCases", "Example Use Cases")

    # FAQ
    if resource.get("faq"):
        parts.append('<h2>Frequently Asked Questions</h2>')
        for faq in resource["faq"]:
            parts.append(f'<h3>{_e(faq["question"])}</h3>')
            parts.append(f'<p>{_e(faq["answer"])}</p>')

    # CTA
    parts.append('<h2>Ready to extract data from your PDFs?</h2>')
    parts.append('<p>Upload your first document and see structured results in seconds. Free to start — no setup required.</p>')
    parts.append('<a href="/">Get Started Free</a>')

    # Related resources (internal links for SEO)
    if resource.get("relatedResources"):
        parts.append('<h3>Related Resources</h3>')
        parts.append('<ul>')
        for related_slug in resource["relatedResources"]:
            label = " ".join(w.capitalize() for w in related_slug.split("-"))
            parts.append(f'<li><a href="/resources/{_e(related_slug)}">{_e(label)}</a></li>')
        parts.append('</ul>')

    parts.append('</article>')

    # Footer nav (internal links)
    parts.append('<footer>')
    parts.append('<nav>')
    parts.append('<a href="/">Home</a> | ')
    parts.append('<a href="/resources">Resources</a> | ')
    parts.append('<a href="/privacy">Privacy Policy</a> | ')
    parts.append('<a href="/terms">Terms of Service</a>')
    parts.append('</nav>')
    parts.append('</footer>')

    parts.append('</div>')

    return "\n".join(parts)


def _render_list_section(parts: list, resource: dict, key: str, heading: str) -> None:
    """Render a list section if it has items."""
    items = resource.get(key, [])
    if not items:
        return
    parts.append(f'<h2>{_e(heading)}</h2>')
    parts.append('<ul>')
    for item in items:
        parts.append(f'<li>{_e(item)}</li>')
    parts.append('</ul>')


def _build_hub_head(registry: dict) -> str:
    """Build <head> content for the resources hub page."""
    title = "Resources — PDF to Excel Guides, Tutorials & Workflows | PDFexcel.ai"
    description = "Practical guides for converting PDFs to Excel, extracting tables from documents, automating workflows, and getting the most out of PDFexcel.ai."

    collection_schema = {
        "@context": "https://schema.org",
        "@type": "CollectionPage",
        "name": "PDF to Excel Resources",
        "description": description,
        "url": f"{DEFAULT_CANONICAL_BASE_URL}/resources",
        "publisher": {
            "@type": "Organization",
            "name": "PDFexcel.ai",
            "url": DEFAULT_CANONICAL_BASE_URL,
        },
    }

    breadcrumb_schema = {
        "@context": "https://schema.org",
        "@type": "BreadcrumbList",
        "itemListElement": [
            {"@type": "ListItem", "position": 1, "name": "Home",
             "item": f"{DEFAULT_CANONICAL_BASE_URL}/"},
            {"@type": "ListItem", "position": 2, "name": "Resources",
             "item": f"{DEFAULT_CANONICAL_BASE_URL}/resources"},
        ],
    }

    lines = [
        '<meta charset="UTF-8" />',
        '<meta name="viewport" content="width=device-width, initial-scale=1.0" />',
        '<script async src="https://www.googletagmanager.com/gtag/js?id=G-K714WDYE3B"></script>',
        '<script>window.dataLayer=window.dataLayer||[];function gtag(){dataLayer.push(arguments);}gtag("js",new Date());gtag("config","G-K714WDYE3B");</script>',
        '<script async src="https://www.googletagmanager.com/gtag/js?id=AW-18021101114"></script>',
        '<script>window.dataLayer=window.dataLayer||[];function gtag(){dataLayer.push(arguments);}gtag("js",new Date());gtag("config","AW-18021101114");</script>',
        '<link rel="icon" type="image/svg+xml" href="/grid-icon.svg" />',
        '<link rel="icon" type="image/png" sizes="192x192" href="/grid-icon.png" />',
        '<link rel="apple-touch-icon" sizes="180x180" href="/apple-touch-icon.png" />',
        '<link rel="manifest" href="/site.webmanifest" />',
        '<meta name="theme-color" content="#2563EB" />',
        f'<title>{_e(title)}</title>',
        f'<meta name="description" content="{_e(description)}" />',
        '<meta name="robots" content="index, follow" />',
        f'<link rel="canonical" href="{DEFAULT_CANONICAL_BASE_URL}/resources" />',
        f'<meta property="og:title" content="Resources — PDF to Excel Guides &amp; Tutorials | PDFexcel.ai" />',
        f'<meta property="og:description" content="{_e(description)}" />',
        f'<meta property="og:url" content="{DEFAULT_CANONICAL_BASE_URL}/resources" />',
        '<meta property="og:type" content="website" />',
        '<meta property="og:site_name" content="PDFexcel.ai" />',
        f'<meta property="og:image" content="{DEFAULT_CANONICAL_BASE_URL}/og-image.png" />',
        '<meta property="og:image:width" content="1200" />',
        '<meta property="og:image:height" content="630" />',
        '<meta name="twitter:card" content="summary_large_image" />',
        f'<meta name="twitter:title" content="Resources — PDF to Excel Guides &amp; Tutorials | PDFexcel.ai" />',
        f'<meta name="twitter:description" content="{_e(description)}" />',
        f'<meta name="twitter:image" content="{DEFAULT_CANONICAL_BASE_URL}/og-image.png" />',
        _json_ld(collection_schema),
        _json_ld(breadcrumb_schema),
    ]
    return "\n    ".join(lines)


def _build_hub_body(registry: dict) -> str:
    """Build the semantic HTML for the resources hub."""
    resources = registry.get("resources", [])
    published = [r for r in resources if r.get("indexationStatus") in ("published", "noindex")]

    parts = []
    parts.append('<div style="max-width:1152px;margin:0 auto;padding:16px">')

    # Breadcrumb
    parts.append('<nav aria-label="Breadcrumb">')
    parts.append('<a href="/">Home</a> &rsaquo; <span>Resources</span>')
    parts.append('</nav>')

    parts.append('<h1>PDF to Excel Resources</h1>')
    parts.append('<p>Practical guides for converting PDFs to spreadsheets, extracting structured data from documents, and automating document-to-Excel workflows.</p>')

    # Group by category
    grouped: dict[str, list] = {}
    for r in published:
        cat = r.get("templateType", r.get("category", "other"))
        grouped.setdefault(cat, []).append(r)

    for cat_key, cat_label in CATEGORY_MAP.items():
        items = grouped.get(cat_key, [])
        if not items:
            continue
        parts.append(f'<h2>{cat_label}</h2>')
        parts.append('<ul>')
        for r in items:
            parts.append(f'<li><a href="/resources/{_e(r["slug"])}">{_e(r["title"])}</a> — {_e(r.get("metaDescription", ""))}</li>')
        parts.append('</ul>')

    # Footer nav
    parts.append('<footer>')
    parts.append('<nav>')
    parts.append('<a href="/">Home</a> | ')
    parts.append('<a href="/resources">Resources</a> | ')
    parts.append('<a href="/privacy">Privacy Policy</a> | ')
    parts.append('<a href="/terms">Terms of Service</a>')
    parts.append('</nav>')
    parts.append('</footer>')

    parts.append('</div>')
    return "\n".join(parts)


def _get_asset_tags(index_html: str) -> tuple[str, str]:
    """Extract CSS and JS asset tags from the built index.html.

    Returns (css_tags, js_tags) as raw HTML strings.
    """
    css_tags = []
    js_tags = []

    # Find CSS link tags (may or may not be self-closing)
    for match in re.finditer(r'<link[^>]+rel="stylesheet"[^>]*/?>', index_html):
        css_tags.append(match.group(0))

    # Find module script tags
    for match in re.finditer(r'<script[^>]+type="module"[^>]*(?:src="[^"]*")[^>]*>.*?</script>', index_html, re.DOTALL):
        js_tags.append(match.group(0))

    # Also check for crossorigin script tags like <script type="module" crossorigin src="/assets/...">
    if not js_tags:
        for match in re.finditer(r'<script\b[^>]*\btype="module"[^>]*>.*?</script>', index_html, re.DOTALL):
            js_tags.append(match.group(0))

    return ("\n    ".join(css_tags), "\n    ".join(js_tags))


def _build_full_html(head_content: str, body_content: str, asset_css: str, asset_js: str) -> str:
    """Assemble a complete HTML document."""
    return f"""<!doctype html>
<html lang="en">
  <head>
    {head_content}
    {asset_css}
  </head>
  <body>
    <div id="root">{body_content}</div>
    {asset_js}
  </body>
</html>
"""


def prerender_resource(resource: dict, asset_css: str, asset_js: str, output_dir: Path) -> Path:
    """Pre-render a single resource page.

    Returns the path to the generated HTML file.
    """
    slug = resource["slug"]
    page_dir = output_dir / "resources" / slug
    page_dir.mkdir(parents=True, exist_ok=True)

    head = _build_head(resource)
    body = _build_body_content(resource)
    html = _build_full_html(head, body, asset_css, asset_js)

    out_path = page_dir / "index.html"
    out_path.write_text(html, encoding="utf-8")
    return out_path


def prerender_hub(registry: dict, asset_css: str, asset_js: str, output_dir: Path) -> Path:
    """Pre-render the resources hub page."""
    page_dir = output_dir / "resources"
    page_dir.mkdir(parents=True, exist_ok=True)

    head = _build_hub_head(registry)
    body = _build_hub_body(registry)
    html = _build_full_html(head, body, asset_css, asset_js)

    out_path = page_dir / "index.html"
    out_path.write_text(html, encoding="utf-8")
    return out_path


def prerender_all(output_dir: Path | None = None, slug_filter: str | None = None) -> dict:
    """Pre-render all published resource pages.

    Args:
        output_dir: Directory to write HTML files. Defaults to frontend/dist.
        slug_filter: If set, only pre-render this specific slug.

    Returns summary of what was generated.
    """
    if output_dir is None:
        output_dir = DIST_DIR

    # Read the built index.html to extract asset references
    index_html_path = output_dir / "index.html"
    if not index_html_path.exists():
        print(f"[prerender] ERROR: {index_html_path} not found. Run 'vite build' first.")
        return {"error": "index.html not found", "pages": 0}

    index_html = index_html_path.read_text(encoding="utf-8")
    asset_css, asset_js = _get_asset_tags(index_html)

    if not asset_js:
        print("[prerender] WARNING: No JS module script found in index.html")

    results = {"hub": False, "resources": [], "errors": []}

    # Load registry
    registry_path = FRONTEND_PUBLIC / "registry.json"
    if not registry_path.exists():
        print(f"[prerender] ERROR: registry.json not found at {registry_path}")
        return {"error": "registry.json not found", "pages": 0}

    registry = json.loads(registry_path.read_text(encoding="utf-8"))

    # Pre-render hub (unless filtering to a single slug)
    if not slug_filter:
        try:
            hub_path = prerender_hub(registry, asset_css, asset_js, output_dir)
            results["hub"] = True
            print(f"[prerender] Hub: {hub_path}")
        except Exception as e:
            results["errors"].append(f"hub: {e}")
            print(f"[prerender] ERROR on hub: {e}")

    # Pre-render individual resources
    published_dir = PUBLISHED_DIR
    resource_files = sorted(published_dir.glob("*.json"))

    for resource_path in resource_files:
        try:
            resource = json.loads(resource_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, FileNotFoundError) as e:
            results["errors"].append(f"{resource_path.stem}: {e}")
            continue

        slug = resource.get("slug", resource_path.stem)

        # Skip drafts and rejected
        status = resource.get("indexationStatus", "draft")
        if status not in ("published", "noindex"):
            continue

        # Filter if requested
        if slug_filter and slug != slug_filter:
            continue

        try:
            out_path = prerender_resource(resource, asset_css, asset_js, output_dir)
            results["resources"].append(slug)
        except Exception as e:
            results["errors"].append(f"{slug}: {e}")
            print(f"[prerender] ERROR on {slug}: {e}")

    total = len(results["resources"]) + (1 if results["hub"] else 0)
    print(f"[prerender] Done: {total} pages pre-rendered ({len(results['errors'])} errors)")
    return results


def prerender_single(resource: dict, output_dir: Path | None = None) -> Path | None:
    """Pre-render a single resource page. For use in the publish pipeline.

    This is the fast path — pre-renders one page without touching others.
    If the dist directory doesn't exist (no build yet), pre-renders to
    frontend/public as a fallback so the next build picks it up.
    """
    if output_dir is None:
        output_dir = DIST_DIR

    index_html_path = output_dir / "index.html"
    if not index_html_path.exists():
        # No build yet — skip pre-rendering (will happen at next build)
        print(f"[prerender] Skipping (no dist build found at {output_dir})")
        return None

    index_html = index_html_path.read_text(encoding="utf-8")
    asset_css, asset_js = _get_asset_tags(index_html)

    try:
        path = prerender_resource(resource, asset_css, asset_js, output_dir)
        print(f"[prerender] Pre-rendered: {path}")

        # Also regenerate the hub page to include the new resource
        registry_path = FRONTEND_PUBLIC / "registry.json"
        if registry_path.exists():
            registry = json.loads(registry_path.read_text(encoding="utf-8"))
            prerender_hub(registry, asset_css, asset_js, output_dir)
            print("[prerender] Hub page updated")

        return path
    except Exception as e:
        print(f"[prerender] ERROR: {e}")
        return None


def main():
    """CLI entry point."""
    import argparse
    parser = argparse.ArgumentParser(description="Pre-render resource pages for SEO")
    parser.add_argument("--slug", help="Pre-render a single resource by slug")
    parser.add_argument("--output", help="Output directory (defaults to frontend/dist)")
    args = parser.parse_args()

    output_dir = Path(args.output) if args.output else None
    results = prerender_all(output_dir=output_dir, slug_filter=args.slug)

    if results.get("error"):
        sys.exit(1)
    if results.get("errors"):
        sys.exit(1)


if __name__ == "__main__":
    main()
