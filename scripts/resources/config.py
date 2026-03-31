"""Configuration for the resources SEO cron system."""

import os
from pathlib import Path

# Paths
REPO_ROOT = Path(__file__).resolve().parent.parent.parent
CONTENT_DIR = REPO_ROOT / "content" / "resources"
PUBLISHED_DIR = CONTENT_DIR / "published"
DRAFTS_DIR = CONTENT_DIR / "drafts"
REJECTED_DIR = CONTENT_DIR / "rejected"
LOGS_DIR = CONTENT_DIR / "logs"
FRONTEND_PUBLIC = REPO_ROOT / "frontend" / "public" / "content" / "resources"

# Ensure directories exist
for d in [PUBLISHED_DIR, DRAFTS_DIR, REJECTED_DIR, LOGS_DIR, FRONTEND_PUBLIC]:
    d.mkdir(parents=True, exist_ok=True)

# Environment-based configuration
CLAUDE_API_KEY = os.getenv("CLAUDE_API_KEY", "")
CRON_ENABLED = os.getenv("RESOURCES_CRON_ENABLED", "true").lower() == "true"

MAX_CANDIDATES_PER_RUN = int(os.getenv("RESOURCES_MAX_CANDIDATES_PER_RUN", "10"))
MAX_PUBLISHES_PER_RUN = int(os.getenv("RESOURCES_MAX_PUBLISHES_PER_RUN", "5"))
MAX_INDEXABLE_PUBLISHES_PER_RUN = int(os.getenv("RESOURCES_MAX_INDEXABLE_PUBLISHES_PER_RUN", "3"))

MIN_HELPFULNESS_SCORE = int(os.getenv("RESOURCES_MIN_HELPFULNESS_SCORE", "85"))
MIN_UNIQUENESS_SCORE = int(os.getenv("RESOURCES_MIN_UNIQUENESS_SCORE", "80"))
MAX_DUPLICATION_RISK = int(os.getenv("RESOURCES_MAX_DUPLICATION_RISK", "20"))
MIN_TRUTHFULNESS_SCORE = int(os.getenv("RESOURCES_MIN_TRUTHFULNESS_SCORE", "95"))
MIN_INTENT_MATCH_SCORE = int(os.getenv("RESOURCES_MIN_INTENT_MATCH_SCORE", "80"))
MAX_THIN_CONTENT_RISK = int(os.getenv("RESOURCES_MAX_THIN_CONTENT_RISK", "20"))

ALLOW_NOINDEX_PUBLISH = os.getenv("RESOURCES_ALLOW_NOINDEX_PUBLISH", "true").lower() == "true"
DEFAULT_CANONICAL_BASE_URL = os.getenv("RESOURCES_DEFAULT_CANONICAL_BASE_URL", "https://gridpull.com")
PUBLISHING_MODE = os.getenv("RESOURCES_PUBLISHING_MODE", "AUTOPUBLISH_STRICT")

# Cooldown: minimum hours between cron runs publishing new pages
MIN_HOURS_BETWEEN_RUNS = int(os.getenv("RESOURCES_MIN_HOURS_BETWEEN_RUNS", "4"))

# Max pages per keyword cluster per 24-hour window
MAX_PER_CLUSTER_PER_DAY = int(os.getenv("RESOURCES_MAX_PER_CLUSTER_PER_DAY", "2"))

# Product capabilities - ground truth for content generation
PRODUCT_CAPABILITIES = {
    "core_function": "Convert PDFs and images to structured Excel/CSV spreadsheets using AI",
    "supported_inputs": [
        "Digital PDF files",
        "Scanned PDF documents",
        "PNG images",
        "JPEG images",
        "Photos of documents",
    ],
    "supported_outputs": [
        "Excel (.xlsx) files",
        "CSV files",
        "Structured spreadsheets with one row per document",
    ],
    "key_features": [
        "AI-powered field extraction with custom field selection",
        "Batch processing of multiple documents",
        "OCR for scanned documents and images",
        "Pipeline automation for recurring workflows",
        "Folder-based watch and export",
        "99%+ accuracy on clear documents",
        "Files encrypted and deleted after processing",
        "Free to start, plans from $69/mo",
    ],
    "document_types": [
        "Invoices",
        "Bank statements",
        "Financial reports",
        "Receipts",
        "Purchase orders",
        "Shipping documents",
        "Insurance forms",
        "Contracts",
        "Annual reports",
    ],
    "limitations": [
        "Accuracy depends on document quality and clarity",
        "Very complex multi-page nested tables may need manual review",
        "Handwritten text recognition is limited compared to typed text",
        "Heavily redacted documents may have missing fields",
        "Non-standard layouts may require field customization",
    ],
    "disallowed_claims": [
        "100% accuracy on all documents",
        "Works perfectly on handwritten notes",
        "Free unlimited processing",
        "Replaces all manual data entry",
        "Works offline",
        "Stores documents permanently",
        "Trains on user data",
    ],
}

# Template types and their requirements
TEMPLATE_TYPES = {
    "file_conversion": {
        "required_fields": [
            "supportedInputs", "expectedOutputs", "howItWorksSteps",
            "commonChallenges", "whyPdfExcelAiFits", "limitations", "faq"
        ],
        "min_faq": 4,
        "min_howItWorks": 3,
        "min_challenges": 3,
        "min_limitations": 2,
    },
    "document_type": {
        "required_fields": [
            "whoItsFor", "supportedInputs", "expectedOutputs",
            "commonChallenges", "howItWorksSteps", "whyPdfExcelAiFits",
            "limitations", "faq", "exampleUseCases"
        ],
        "min_faq": 4,
        "min_howItWorks": 3,
        "min_challenges": 3,
        "min_limitations": 2,
    },
    "workflow": {
        "required_fields": [
            "whoItsFor", "whenThisIsRelevant", "howItWorksSteps",
            "whyPdfExcelAiFits", "limitations", "faq"
        ],
        "min_faq": 3,
        "min_howItWorks": 4,
        "min_challenges": 2,
        "min_limitations": 2,
    },
    "use_case": {
        "required_fields": [
            "whoItsFor", "whenThisIsRelevant", "supportedInputs",
            "expectedOutputs", "howItWorksSteps", "whyPdfExcelAiFits",
            "limitations", "faq", "exampleUseCases"
        ],
        "min_faq": 3,
        "min_howItWorks": 3,
        "min_challenges": 2,
        "min_limitations": 2,
    },
    "comparison": {
        "required_fields": [
            "whoItsFor", "commonChallenges", "howItWorksSteps",
            "whyPdfExcelAiFits", "limitations", "faq"
        ],
        "min_faq": 4,
        "min_howItWorks": 3,
        "min_challenges": 3,
        "min_limitations": 3,
    },
    "support_education": {
        "required_fields": [
            "whoItsFor", "howItWorksSteps", "faq", "limitations"
        ],
        "min_faq": 3,
        "min_howItWorks": 4,
        "min_challenges": 1,
        "min_limitations": 1,
    },
    "guide": {
        "required_fields": [
            "whoItsFor", "sections", "faq", "limitations"
        ],
        "min_faq": 4,
        "min_howItWorks": 0,
        "min_challenges": 0,
        "min_limitations": 2,
        "min_sections": 4,
        "is_editorial": True,
    },
    "industry_insight": {
        "required_fields": [
            "whoItsFor", "sections", "faq"
        ],
        "min_faq": 3,
        "min_howItWorks": 0,
        "min_challenges": 0,
        "min_limitations": 0,
        "min_sections": 4,
        "is_editorial": True,
    },
}
