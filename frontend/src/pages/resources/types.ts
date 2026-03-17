export interface ResourceFAQItem {
  question: string
  answer: string
}

export interface ResourceHero {
  headline: string
  subheadline: string
  primaryCta: string
  secondaryCta: string
}

export interface QualityReview {
  intentMatchScore: number
  uniquenessScore: number
  thinContentRisk: number
  duplicationRisk: number
  productTruthfulnessScore: number
  helpfulnessScore: number
  indexRecommendation: 'index' | 'noindex'
  reasons: string[]
}

export interface ArticleSection {
  heading: string
  body: string
}

export interface ResourceContent {
  slug: string
  title: string
  metaTitle: string
  metaDescription: string
  h1: string
  primaryKeyword: string
  secondaryKeywords: string[]
  searchIntent: string
  templateType: 'file_conversion' | 'document_type' | 'workflow' | 'use_case' | 'comparison' | 'support_education' | 'guide' | 'industry_insight'
  indexationStatus: 'draft' | 'published' | 'noindex' | 'rejected'
  canonicalUrl: string
  hero: ResourceHero
  summary: string
  whoItsFor: string[]
  whenThisIsRelevant: string[]
  supportedInputs: string[]
  expectedOutputs: string[]
  commonChallenges: string[]
  howItWorksSteps: string[]
  whyPdfExcelAiFits: string[]
  limitations: string[]
  sections?: ArticleSection[]
  faq: ResourceFAQItem[]
  relatedResources: string[]
  relatedProductLinks: { label: string; url: string }[]
  trustSignals: string[]
  exampleUseCases: string[]
  qualityReview: QualityReview
  publishedAt?: string
  updatedAt?: string
}

export interface ResourceRegistry {
  lastUpdated: string
  totalPublished: number
  resources: ResourceRegistryEntry[]
}

export interface ResourceRegistryEntry {
  slug: string
  title: string
  metaDescription: string
  templateType: string
  primaryKeyword: string
  indexationStatus: string
  publishedAt: string
  category: string
}

export const TEMPLATE_LABELS: Record<string, string> = {
  file_conversion: 'Conversion Guide',
  document_type: 'Document Guide',
  workflow: 'Workflow Guide',
  use_case: 'Use Case Guide',
  comparison: 'Comparison',
  support_education: 'Tutorial',
  guide: 'In-Depth Guide',
  industry_insight: 'Industry Insight',
}

export const CATEGORY_MAP: Record<string, string> = {
  guide: 'Guides & How-Tos',
  industry_insight: 'Industry Insights',
  file_conversion: 'Conversion Guides',
  document_type: 'Document-Specific Guides',
  workflow: 'Workflow Automation',
  use_case: 'Use Cases',
  comparison: 'Comparisons',
  support_education: 'Tutorials',
}

export const EDITORIAL_TEMPLATES = new Set(['guide', 'industry_insight'])
