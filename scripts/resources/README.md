# Resources SEO Cron System

Automated system for generating, validating, and publishing SEO resource pages on gridpull.com.

## Architecture

```
content/resources/
├── published/        # Published resource JSON files (source of truth)
├── drafts/           # Generated but not yet published
├── rejected/         # Failed quality gates
└── logs/             # Cron run logs

scripts/resources/
├── cron.py           # Main entry point (CLI)
├── config.py         # Configuration & env vars
├── schema.py         # JSON schema validation
├── quality_scorer.py # Quality scoring engine
├── duplicate_checker.py # Duplication detection
├── discover.py       # Topic discovery pipeline
├── generate.py       # AI content generation (Claude API)
├── publish.py        # Publishing pipeline & registry
├── sitemap_generator.py # Resources sitemap XML
└── seed_content.py   # Pre-built seed content

frontend/
├── src/pages/resources/
│   ├── ResourcesHub.tsx   # /resources hub page
│   ├── ResourcePage.tsx   # /resources/[slug] page
│   └── types.ts           # TypeScript types
└── public/content/resources/
    ├── registry.json      # Published resources index
    ├── *.json             # Individual resource files
    └── sitemap-resources.xml
```

## How the Cron Works

The cron pipeline runs in 3 stages:

1. **Discovery** — Identifies uncovered topics from seed list, scores by relevance
2. **Generation** — Uses Claude API (Sonnet) in constrained schema-first mode
3. **Publishing** — Validates, scores, checks duplication, publishes passing pages

### Commands

```bash
# Full pipeline (discover → generate → publish)
python -m scripts.resources.cron

# Individual stages
python -m scripts.resources.cron --discover    # See available topics
python -m scripts.resources.cron --generate    # Generate content (needs API key)
python -m scripts.resources.cron --publish     # Publish existing drafts
python -m scripts.resources.cron --sitemap     # Regenerate sitemap only
python -m scripts.resources.cron --seed        # Publish pre-built seed content
```

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `CLAUDE_API_KEY` | (required for generation) | Anthropic API key |
| `RESOURCES_CRON_ENABLED` | `true` | Enable/disable cron |
| `RESOURCES_MAX_CANDIDATES_PER_RUN` | `10` | Max topics per run |
| `RESOURCES_MAX_PUBLISHES_PER_RUN` | `5` | Max total publishes per run |
| `RESOURCES_MAX_INDEXABLE_PUBLISHES_PER_RUN` | `3` | Max indexable publishes per run |
| `RESOURCES_MIN_HELPFULNESS_SCORE` | `85` | Min helpfulness (0-100) |
| `RESOURCES_MIN_UNIQUENESS_SCORE` | `80` | Min uniqueness (0-100) |
| `RESOURCES_MAX_DUPLICATION_RISK` | `20` | Max duplication risk (0-100) |
| `RESOURCES_MIN_TRUTHFULNESS_SCORE` | `95` | Min truthfulness (0-100) |
| `RESOURCES_ALLOW_NOINDEX_PUBLISH` | `true` | Allow noindex publishing |
| `RESOURCES_DEFAULT_CANONICAL_BASE_URL` | `https://gridpull.com` | Base URL |
| `RESOURCES_PUBLISHING_MODE` | `AUTOPUBLISH_STRICT` | Publishing mode |

## Quality Gates

Every page must pass ALL of these before indexable publishing:

- Schema valid
- Slug unique
- Intent match score ≥ 80
- Uniqueness score ≥ 80
- Thin content risk ≤ 20
- Duplication risk ≤ 20
- Product truthfulness ≥ 95
- Helpfulness score ≥ 85
- Includes realistic limitations
- Includes contextual FAQ
- No exaggerated promises, fake stats, or fake testimonials

## Disable Cron

```bash
export RESOURCES_CRON_ENABLED=false
```

Or remove the cron job entry from your scheduler.

## Inspect Content

```bash
# View all published resources
ls content/resources/published/

# View quality scores for a resource
python -c "import json; d=json.load(open('content/resources/published/pdf-to-excel.json')); print(json.dumps(d['qualityReview'], indent=2))"

# View latest cron log
ls -t content/resources/logs/ | head -1 | xargs -I{} cat content/resources/logs/{}
```

## Edit / Remove Pages

```bash
# Edit: modify the JSON in content/resources/published/<slug>.json
# Then copy to frontend: cp content/resources/published/<slug>.json frontend/public/content/resources/

# Remove: delete from both locations
rm content/resources/published/<slug>.json
rm frontend/public/content/resources/<slug>.json

# Regenerate registry and sitemap
python -m scripts.resources.cron --sitemap
```

## Site Protection

Only one change was made to the existing site: a "Resources" link in the footer of `LandingPage.tsx`. Everything else is isolated:

- New routes: `/resources` and `/resources/:slug` (lazy-loaded)
- New components: `src/pages/resources/` (completely self-contained)
- Content storage: `content/resources/` and `public/content/resources/`
- Cron scripts: `scripts/resources/`
- No changes to dashboard, auth, billing, uploads, pipelines, or any existing pages
