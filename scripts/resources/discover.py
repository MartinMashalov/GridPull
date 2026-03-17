"""Topic discovery pipeline for resource content generation."""

from typing import Any

from .duplicate_checker import get_existing_slugs

# Seed topics organized by page family
SEED_TOPICS = [
    # A. File conversion pages
    {
        "keyword": "pdf to excel",
        "slug": "pdf-to-excel",
        "template": "file_conversion",
        "cluster": "file_conversion",
        "intent": "transactional",
        "priority": 10,
        "angle": "Core conversion - how to convert any PDF into a structured Excel spreadsheet",
    },
    {
        "keyword": "pdf to csv",
        "slug": "pdf-to-csv",
        "template": "file_conversion",
        "cluster": "file_conversion",
        "intent": "transactional",
        "priority": 9,
        "angle": "CSV-specific output for data pipelines and imports",
    },
    {
        "keyword": "scanned pdf to excel",
        "slug": "scanned-pdf-to-excel",
        "template": "file_conversion",
        "cluster": "file_conversion",
        "intent": "transactional",
        "priority": 9,
        "angle": "Handling scanned/photographed documents with OCR-based extraction",
    },
    {
        "keyword": "ocr pdf to excel",
        "slug": "ocr-pdf-to-excel",
        "template": "file_conversion",
        "cluster": "file_conversion",
        "intent": "transactional",
        "priority": 8,
        "angle": "OCR-specific conversion for non-digital PDFs",
    },
    {
        "keyword": "image table to excel",
        "slug": "image-table-to-excel",
        "template": "file_conversion",
        "cluster": "file_conversion",
        "intent": "transactional",
        "priority": 7,
        "angle": "Extracting tabular data from photos/screenshots of tables",
    },
    {
        "keyword": "extract tables from pdf to excel",
        "slug": "extract-tables-from-pdf",
        "template": "file_conversion",
        "cluster": "file_conversion",
        "intent": "transactional",
        "priority": 9,
        "angle": "Focused on table extraction specifically from PDF documents",
    },
    {
        "keyword": "statement to spreadsheet",
        "slug": "statement-to-spreadsheet",
        "template": "file_conversion",
        "cluster": "file_conversion",
        "intent": "transactional",
        "priority": 7,
        "angle": "Converting financial/bank statements into spreadsheet format",
    },

    # B. Document-type pages
    {
        "keyword": "invoice pdf to excel",
        "slug": "invoice-pdf-to-excel",
        "template": "document_type",
        "cluster": "document_type",
        "intent": "transactional",
        "priority": 10,
        "angle": "Invoice-specific extraction including fields like invoice number, line items, totals",
    },
    {
        "keyword": "bank statement pdf to excel",
        "slug": "bank-statement-pdf-to-excel",
        "template": "document_type",
        "cluster": "document_type",
        "intent": "transactional",
        "priority": 9,
        "angle": "Bank statement extraction with transaction details, dates, amounts",
    },
    {
        "keyword": "receipt pdf to excel",
        "slug": "receipt-pdf-to-excel",
        "template": "document_type",
        "cluster": "document_type",
        "intent": "transactional",
        "priority": 8,
        "angle": "Receipt extraction for expense tracking and accounting",
    },
    {
        "keyword": "purchase order pdf to excel",
        "slug": "purchase-order-pdf-to-excel",
        "template": "document_type",
        "cluster": "document_type",
        "intent": "transactional",
        "priority": 8,
        "angle": "PO extraction with vendor, item, quantity, price fields",
    },
    {
        "keyword": "financial statement pdf to excel",
        "slug": "financial-statement-pdf-to-excel",
        "template": "document_type",
        "cluster": "document_type",
        "intent": "transactional",
        "priority": 8,
        "angle": "Financial report extraction for analysis and auditing",
    },
    {
        "keyword": "shipping document pdf to excel",
        "slug": "shipping-document-pdf-to-excel",
        "template": "document_type",
        "cluster": "document_type",
        "intent": "transactional",
        "priority": 6,
        "angle": "Shipping/logistics document extraction for supply chain tracking",
    },
    {
        "keyword": "supplier pdf to excel",
        "slug": "supplier-pdf-to-excel",
        "template": "document_type",
        "cluster": "document_type",
        "intent": "transactional",
        "priority": 7,
        "angle": "Supplier document processing for procurement and vendor management",
    },

    # C. Workflow pages
    {
        "keyword": "batch convert pdf to excel",
        "slug": "batch-convert-pdf-to-excel",
        "template": "workflow",
        "cluster": "workflow",
        "intent": "transactional",
        "priority": 9,
        "angle": "Processing multiple PDFs at once into a single or multiple spreadsheets",
    },
    {
        "keyword": "automate pdf to excel workflow",
        "slug": "automate-pdf-to-excel-workflow",
        "template": "workflow",
        "cluster": "workflow",
        "intent": "commercial",
        "priority": 8,
        "angle": "Setting up automated recurring PDF-to-Excel pipelines",
    },
    {
        "keyword": "folder pipeline pdf to excel",
        "slug": "folder-pipeline-pdf-to-excel",
        "template": "workflow",
        "cluster": "workflow",
        "intent": "commercial",
        "priority": 7,
        "angle": "Watch-folder automation that processes PDFs automatically",
    },
    {
        "keyword": "recurring pdf extraction workflow",
        "slug": "recurring-pdf-extraction-workflow",
        "template": "workflow",
        "cluster": "workflow",
        "intent": "commercial",
        "priority": 7,
        "angle": "Setting up repeated/scheduled PDF extraction jobs",
    },

    # D. Use-case pages
    {
        "keyword": "convert invoices to excel for accounting",
        "slug": "convert-invoices-to-excel-for-accounting",
        "template": "use_case",
        "cluster": "use_case",
        "intent": "commercial",
        "priority": 8,
        "angle": "Accounting-specific workflow for processing invoice PDFs",
    },
    {
        "keyword": "convert statements to spreadsheet for bookkeeping",
        "slug": "convert-statements-to-spreadsheet-for-bookkeeping",
        "template": "use_case",
        "cluster": "use_case",
        "intent": "commercial",
        "priority": 7,
        "angle": "Bookkeeping use case for bank/financial statement extraction",
    },
    {
        "keyword": "extract supplier tables from pdfs",
        "slug": "extract-supplier-tables-from-pdfs",
        "template": "use_case",
        "cluster": "use_case",
        "intent": "commercial",
        "priority": 6,
        "angle": "Procurement/supplier data extraction use case",
    },
    {
        "keyword": "automate document entry into spreadsheets",
        "slug": "automate-document-entry-into-spreadsheets",
        "template": "use_case",
        "cluster": "use_case",
        "intent": "commercial",
        "priority": 7,
        "angle": "General automation of manual document-to-spreadsheet data entry",
    },

    # E. Comparison pages
    {
        "keyword": "pdfexcel ai vs manual data entry",
        "slug": "pdfexcel-ai-vs-manual-data-entry",
        "template": "comparison",
        "cluster": "comparison",
        "intent": "commercial",
        "priority": 8,
        "angle": "Honest comparison of AI extraction vs manual copy-paste workflows",
    },
    {
        "keyword": "pdfexcel ai vs copy paste from pdf",
        "slug": "pdfexcel-ai-vs-copy-paste-from-pdf",
        "template": "comparison",
        "cluster": "comparison",
        "intent": "commercial",
        "priority": 7,
        "angle": "Comparison with the common copy-paste approach and its limitations",
    },

    # =========================================================================
    # EDITORIAL CONTENT — Original articles for SEO authority
    # These are educational, genuinely useful articles that build topical
    # authority. Product mentions are minimal and natural.
    # =========================================================================

    # F. Guides — practical how-to articles
    {
        "keyword": "how to extract data from pdf",
        "slug": "how-to-extract-data-from-pdf",
        "template": "guide",
        "cluster": "editorial_guide",
        "intent": "informational",
        "priority": 10,
        "angle": "Comprehensive guide covering all methods: copy-paste, Python libraries, online tools, AI extraction. Honest pros/cons of each.",
    },
    {
        "keyword": "pdf table extraction methods",
        "slug": "pdf-table-extraction-methods-compared",
        "template": "guide",
        "cluster": "editorial_guide",
        "intent": "informational",
        "priority": 9,
        "angle": "Technical comparison of extraction approaches: regex, coordinate-based, ML-based, template-based. When each works best.",
    },
    {
        "keyword": "how ocr works",
        "slug": "how-ocr-works-explained",
        "template": "guide",
        "cluster": "editorial_guide",
        "intent": "informational",
        "priority": 9,
        "angle": "Plain-language explanation of OCR technology: from image preprocessing to character recognition to modern neural approaches.",
    },
    {
        "keyword": "why copying from pdf is so hard",
        "slug": "why-copying-from-pdf-is-so-hard",
        "template": "guide",
        "cluster": "editorial_guide",
        "intent": "informational",
        "priority": 9,
        "angle": "Explains PDF internals — why PDFs store visual layout not data structure, and why table boundaries get lost. Technical but accessible.",
    },
    {
        "keyword": "how to digitize paper documents",
        "slug": "how-to-digitize-paper-documents",
        "template": "guide",
        "cluster": "editorial_guide",
        "intent": "informational",
        "priority": 8,
        "angle": "Practical guide to scanning, OCR, and organizing paper documents. Covers equipment, software, workflows, and common mistakes.",
    },
    {
        "keyword": "pdf format explained",
        "slug": "understanding-the-pdf-file-format",
        "template": "guide",
        "cluster": "editorial_guide",
        "intent": "informational",
        "priority": 8,
        "angle": "How PDFs actually store data internally — objects, streams, fonts, content streams. Why this makes extraction challenging.",
    },
    {
        "keyword": "data entry automation guide",
        "slug": "data-entry-automation-guide",
        "template": "guide",
        "cluster": "editorial_guide",
        "intent": "informational",
        "priority": 8,
        "angle": "Complete guide to automating manual data entry: OCR, RPA, AI extraction, APIs. Includes decision framework for choosing approach.",
    },
    {
        "keyword": "spreadsheet data cleaning tips",
        "slug": "spreadsheet-data-cleaning-tips",
        "template": "guide",
        "cluster": "editorial_guide",
        "intent": "informational",
        "priority": 7,
        "angle": "Practical techniques for cleaning messy spreadsheet data: deduplication, formatting, validation, formulas. Tool-agnostic advice.",
    },
    {
        "keyword": "how to organize financial documents",
        "slug": "how-to-organize-financial-documents",
        "template": "guide",
        "cluster": "editorial_guide",
        "intent": "informational",
        "priority": 7,
        "angle": "Guide to organizing invoices, receipts, statements, and tax documents. Digital filing systems, naming conventions, retention policies.",
    },
    {
        "keyword": "invoice processing best practices",
        "slug": "invoice-processing-best-practices",
        "template": "guide",
        "cluster": "editorial_guide",
        "intent": "informational",
        "priority": 8,
        "angle": "Best practices for accounts payable: intake, validation, approval workflows, error reduction. Industry-standard advice.",
    },
    {
        "keyword": "bank statement reconciliation guide",
        "slug": "bank-statement-reconciliation-guide",
        "template": "guide",
        "cluster": "editorial_guide",
        "intent": "informational",
        "priority": 8,
        "angle": "Step-by-step guide to reconciling bank statements with accounting records. Manual vs automated approaches, common discrepancies.",
    },
    {
        "keyword": "common pdf extraction mistakes",
        "slug": "common-pdf-extraction-mistakes",
        "template": "guide",
        "cluster": "editorial_guide",
        "intent": "informational",
        "priority": 8,
        "angle": "Real-world mistakes people make when extracting data from PDFs: wrong tool choice, ignoring encoding, skipping validation. How to avoid each.",
    },
    {
        "keyword": "structured vs unstructured data explained",
        "slug": "structured-vs-unstructured-data-explained",
        "template": "guide",
        "cluster": "editorial_guide",
        "intent": "informational",
        "priority": 7,
        "angle": "Clear explanation of structured, semi-structured, and unstructured data with real examples. Why it matters for document processing.",
    },
    {
        "keyword": "how ai reads documents",
        "slug": "how-ai-reads-documents",
        "template": "guide",
        "cluster": "editorial_guide",
        "intent": "informational",
        "priority": 9,
        "angle": "How modern AI systems process documents: vision models, layout analysis, field extraction. Real capabilities vs marketing hype.",
    },
    {
        "keyword": "excel vs csv when to use which",
        "slug": "excel-vs-csv-when-to-use-which",
        "template": "guide",
        "cluster": "editorial_guide",
        "intent": "informational",
        "priority": 7,
        "angle": "Practical comparison of Excel and CSV formats: compatibility, size limits, formulas, encoding pitfalls. Decision guide for each use case.",
    },

    # G. Industry insights — thought leadership and original analysis
    {
        "keyword": "state of document processing",
        "slug": "state-of-document-processing-2026",
        "template": "industry_insight",
        "cluster": "editorial_insight",
        "intent": "informational",
        "priority": 9,
        "angle": "Analysis of where document processing stands: adoption rates, technology shifts, remaining challenges. Based on observable industry trends.",
    },
    {
        "keyword": "why manual data entry persists",
        "slug": "why-manual-data-entry-persists",
        "template": "industry_insight",
        "cluster": "editorial_insight",
        "intent": "informational",
        "priority": 9,
        "angle": "Honest analysis of why businesses still rely on manual data entry despite automation tools. Trust gaps, edge cases, organizational inertia.",
    },
    {
        "keyword": "future of ocr technology",
        "slug": "future-of-ocr-technology",
        "template": "industry_insight",
        "cluster": "editorial_insight",
        "intent": "informational",
        "priority": 8,
        "angle": "Where OCR is heading: multimodal AI, layout-aware models, domain-specific fine-tuning. Honest assessment of progress and remaining gaps.",
    },
    {
        "keyword": "small business document automation",
        "slug": "small-business-document-automation-guide",
        "template": "industry_insight",
        "cluster": "editorial_insight",
        "intent": "informational",
        "priority": 8,
        "angle": "Realistic guide for small businesses: where to start, what to automate first, common pitfalls, ROI expectations. Not vendor-specific.",
    },
    {
        "keyword": "hidden costs of manual document processing",
        "slug": "hidden-costs-of-manual-document-processing",
        "template": "industry_insight",
        "cluster": "editorial_insight",
        "intent": "informational",
        "priority": 8,
        "angle": "Analysis of real costs beyond labor: error rates, compliance risk, opportunity cost, employee burnout. Framework for calculating true cost.",
    },
    {
        "keyword": "accounting automation trends",
        "slug": "accounting-automation-trends",
        "template": "industry_insight",
        "cluster": "editorial_insight",
        "intent": "informational",
        "priority": 7,
        "angle": "How accounting workflows are evolving: from manual ledgers to AI-assisted processing. What's working, what's overhyped, what's next.",
    },
    {
        "keyword": "ai document processing accuracy benchmarks",
        "slug": "ai-document-processing-accuracy-benchmarks",
        "template": "industry_insight",
        "cluster": "editorial_insight",
        "intent": "informational",
        "priority": 9,
        "angle": "Honest look at accuracy claims in document AI: what 99% really means, how to measure correctly, where systems still fail.",
    },
    {
        "keyword": "document processing security best practices",
        "slug": "document-processing-security-best-practices",
        "template": "industry_insight",
        "cluster": "editorial_insight",
        "intent": "informational",
        "priority": 8,
        "angle": "Security considerations when processing sensitive documents: data residency, encryption, access controls, compliance (GDPR, HIPAA).",
    },
]


def discover_topics(max_topics: int = 10) -> list[dict[str, Any]]:
    """Discover topics for content generation.

    Returns a prioritized list of topic opportunities that haven't been covered yet.
    """
    existing_slugs = get_existing_slugs()

    # Filter out already-covered topics
    available = [
        topic for topic in SEED_TOPICS
        if topic["slug"] not in existing_slugs
    ]

    # Score and rank opportunities
    scored = []
    for topic in available:
        score = _score_opportunity(topic, existing_slugs)
        scored.append({**topic, "opportunity_score": score})

    # Sort by opportunity score (higher = better), then priority
    scored.sort(key=lambda t: (t["opportunity_score"], t["priority"]), reverse=True)

    return scored[:max_topics]


def _score_opportunity(topic: dict[str, Any], existing_slugs: set[str]) -> float:
    """Score a topic opportunity based on relevance, uniqueness, and fit."""
    score = topic["priority"] * 10  # Base from priority (60-100)

    # Bonus for high-intent templates
    if topic["template"] in ("file_conversion", "document_type"):
        score += 10

    # Bonus for editorial content (builds SEO authority)
    if topic["template"] in ("guide", "industry_insight"):
        score += 8

    # Bonus for transactional intent
    if topic["intent"] == "transactional":
        score += 5

    # Bonus for informational intent (editorial SEO value)
    if topic["intent"] == "informational":
        score += 3

    # Check cluster saturation - penalize if too many from same cluster
    cluster = topic["cluster"]
    cluster_count = sum(
        1 for s in existing_slugs
        for t in SEED_TOPICS
        if t["slug"] == s and t.get("cluster") == cluster
    )
    if cluster_count >= 5:
        score -= 15
    elif cluster_count >= 3:
        score -= 5

    return score
