"""Resources sitemap generator."""

import json
from datetime import datetime, timezone
from pathlib import Path

from .config import PUBLISHED_DIR, FRONTEND_PUBLIC, DEFAULT_CANONICAL_BASE_URL


def generate_sitemap() -> str:
    """Generate a resources sitemap XML file.

    Only includes published (indexable) pages. Noindex pages are excluded.
    Returns the path to the generated sitemap.
    """
    urls = []

    # Add the resources hub
    urls.append({
        "loc": f"{DEFAULT_CANONICAL_BASE_URL}/resources",
        "lastmod": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
        "changefreq": "weekly",
        "priority": "0.7",
    })

    # Add individual resource pages (only indexable ones)
    for path in sorted(PUBLISHED_DIR.glob("*.json")):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, FileNotFoundError):
            continue

        if data.get("indexationStatus") != "published":
            continue

        slug = data.get("slug", path.stem)
        updated = data.get("updatedAt", data.get("publishedAt", ""))
        lastmod = ""
        if updated:
            try:
                dt = datetime.fromisoformat(updated.replace("Z", "+00:00"))
                lastmod = dt.strftime("%Y-%m-%d")
            except ValueError:
                lastmod = datetime.now(timezone.utc).strftime("%Y-%m-%d")

        urls.append({
            "loc": f"{DEFAULT_CANONICAL_BASE_URL}/resources/{slug}",
            "lastmod": lastmod or datetime.now(timezone.utc).strftime("%Y-%m-%d"),
            "changefreq": "monthly",
            "priority": "0.6",
        })

    # Build XML
    xml_parts = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">',
    ]
    for url in urls:
        xml_parts.append("  <url>")
        xml_parts.append(f"    <loc>{url['loc']}</loc>")
        if url.get("lastmod"):
            xml_parts.append(f"    <lastmod>{url['lastmod']}</lastmod>")
        xml_parts.append(f"    <changefreq>{url['changefreq']}</changefreq>")
        xml_parts.append(f"    <priority>{url['priority']}</priority>")
        xml_parts.append("  </url>")
    xml_parts.append("</urlset>")
    xml_parts.append("")

    xml_content = "\n".join(xml_parts)

    # Write to frontend public directory
    sitemap_path = FRONTEND_PUBLIC.parent.parent / "sitemap-resources.xml"
    sitemap_path.write_text(xml_content, encoding="utf-8")

    return str(sitemap_path)
