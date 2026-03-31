#!/usr/bin/env node
/**
 * Pre-render resource pages as static HTML for SEO.
 *
 * Generates individual HTML files for each published resource so that
 * search engine crawlers get fully-formed HTML with meta tags, structured
 * data, and article content — no JavaScript execution required.
 *
 * Usage:
 *   node scripts/prerender.mjs                     # Pre-render all
 *   node scripts/prerender.mjs --slug xyz           # Single resource
 *   node scripts/prerender.mjs --dist ./dist        # Custom dist dir
 */

import { readFileSync, writeFileSync, mkdirSync, readdirSync, existsSync } from 'fs'
import { join, resolve, dirname } from 'path'
import { fileURLToPath } from 'url'

const __dirname = dirname(fileURLToPath(import.meta.url))
const FRONTEND_DIR = resolve(__dirname, '..')
const DIST_DIR = join(FRONTEND_DIR, 'dist')
const CONTENT_DIR = join(FRONTEND_DIR, 'public', 'content', 'resources')
const BASE_URL = 'https://gridpull.com'

const EDITORIAL_TEMPLATES = new Set(['guide', 'industry_insight'])

const TEMPLATE_LABELS = {
  file_conversion: 'Conversion Guide',
  document_type: 'Document Guide',
  workflow: 'Workflow Guide',
  use_case: 'Use Case Guide',
  comparison: 'Comparison',
  support_education: 'Tutorial',
  guide: 'In-Depth Guide',
  industry_insight: 'Industry Insight',
}

const CATEGORY_MAP = {
  guide: 'Guides &amp; How-Tos',
  industry_insight: 'Industry Insights',
  file_conversion: 'Conversion Guides',
  document_type: 'Document-Specific Guides',
  workflow: 'Workflow Automation',
  use_case: 'Use Cases',
  comparison: 'Comparisons',
  support_education: 'Tutorials',
}

function e(text) {
  return String(text)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#x27;')
}

function jsonLd(obj) {
  return `<script type="application/ld+json">${JSON.stringify(obj)}</script>`
}

function estimateReadTime(resource) {
  let total = (resource.summary || '').split(/\s+/).length
  for (const s of resource.sections || []) total += (s.body || '').split(/\s+/).length
  for (const f of resource.faq || []) total += (f.answer || '').split(/\s+/).length
  for (const key of ['whoItsFor', 'commonChallenges', 'howItWorksSteps', 'whyPdfExcelAiFits', 'limitations', 'exampleUseCases']) {
    for (const item of resource[key] || []) total += String(item).split(/\s+/).length
  }
  return Math.max(1, Math.round(total / 230))
}

function getAssetTags(indexHtml) {
  const cssMatches = indexHtml.match(/<link[^>]+rel="stylesheet"[^>]*\/?>/g) || []
  let jsMatches = indexHtml.match(/<script[^>]+type="module"[^>]*src="[^"]*"[^>]*>.*?<\/script>/gs) || []
  if (!jsMatches.length) {
    jsMatches = indexHtml.match(/<script\b[^>]*\btype="module"[^>]*>.*?<\/script>/gs) || []
  }
  return { css: cssMatches.join('\n    '), js: jsMatches.join('\n    ') }
}

function buildHead(resource) {
  const slug = resource.slug
  const isNoindex = resource.indexationStatus === 'noindex'
  const isEditorial = EDITORIAL_TEMPLATES.has(resource.templateType)
  const pageUrl = `${BASE_URL}/resources/${slug}`
  const canonical = resource.canonicalUrl || pageUrl

  const breadcrumb = {
    '@context': 'https://schema.org', '@type': 'BreadcrumbList',
    itemListElement: [
      { '@type': 'ListItem', position: 1, name: 'Home', item: `${BASE_URL}/` },
      { '@type': 'ListItem', position: 2, name: 'Resources', item: `${BASE_URL}/resources` },
      { '@type': 'ListItem', position: 3, name: resource.title, item: pageUrl },
    ],
  }

  let faqSchema = ''
  if (resource.faq?.length) {
    faqSchema = jsonLd({
      '@context': 'https://schema.org', '@type': 'FAQPage',
      mainEntity: resource.faq.map(f => ({
        '@type': 'Question', name: f.question,
        acceptedAnswer: { '@type': 'Answer', text: f.answer },
      })),
    })
  }

  let articleSchema = ''
  if (isEditorial) {
    articleSchema = jsonLd({
      '@context': 'https://schema.org', '@type': 'Article',
      headline: resource.h1, description: resource.metaDescription,
      datePublished: resource.publishedAt || '',
      dateModified: resource.updatedAt || resource.publishedAt || '',
      publisher: { '@type': 'Organization', name: 'PDFexcel.ai', url: BASE_URL },
      mainEntityOfPage: canonical,
    })
  }

  const robots = isNoindex ? 'noindex, follow' : 'index, follow'

  const lines = [
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
    `<title>${e(resource.metaTitle)}</title>`,
    `<meta name="description" content="${e(resource.metaDescription)}" />`,
    `<meta name="robots" content="${robots}" />`,
    `<link rel="canonical" href="${e(canonical)}" />`,
    `<meta property="og:title" content="${e(resource.metaTitle)}" />`,
    `<meta property="og:description" content="${e(resource.metaDescription)}" />`,
    `<meta property="og:url" content="${e(pageUrl)}" />`,
    '<meta property="og:type" content="article" />',
    '<meta property="og:site_name" content="PDFexcel.ai" />',
    `<meta property="og:image" content="${BASE_URL}/og-image.png" />`,
    '<meta property="og:image:width" content="1200" />',
    '<meta property="og:image:height" content="630" />',
    `<meta property="og:image:alt" content="${e(resource.metaTitle)}" />`,
  ]

  if (resource.publishedAt) lines.push(`<meta property="article:published_time" content="${e(resource.publishedAt)}" />`)
  if (resource.updatedAt) lines.push(`<meta property="article:modified_time" content="${e(resource.updatedAt)}" />`)

  lines.push(
    '<meta name="twitter:card" content="summary_large_image" />',
    `<meta name="twitter:title" content="${e(resource.metaTitle)}" />`,
    `<meta name="twitter:description" content="${e(resource.metaDescription)}" />`,
    `<meta name="twitter:image" content="${BASE_URL}/og-image.png" />`,
    `<meta name="twitter:image:alt" content="${e(resource.metaTitle)}" />`,
    jsonLd(breadcrumb),
  )

  if (faqSchema) lines.push(faqSchema)
  if (articleSchema) lines.push(articleSchema)

  return lines.join('\n    ')
}

function renderListSection(parts, resource, key, heading) {
  const items = resource[key] || []
  if (!items.length) return
  parts.push(`<h2>${e(heading)}</h2>`)
  parts.push('<ul>')
  for (const item of items) parts.push(`<li>${e(item)}</li>`)
  parts.push('</ul>')
}

function buildBody(resource) {
  const isEditorial = EDITORIAL_TEMPLATES.has(resource.templateType)
  const readTime = estimateReadTime(resource)
  const label = TEMPLATE_LABELS[resource.templateType] || resource.templateType

  const p = []
  p.push('<div style="max-width:896px;margin:0 auto;padding:16px">')
  p.push(`<nav aria-label="Breadcrumb"><a href="/">Home</a> &rsaquo; <a href="/resources">Resources</a> &rsaquo; <span>${e(resource.title)}</span></nav>`)
  p.push('<article>')
  p.push(`<span>${e(label)}</span>`)
  p.push(`<h1>${e(resource.h1)}</h1>`)
  p.push(`<p>${e(resource.hero.subheadline)}</p>`)

  if (resource.publishedAt) {
    const dt = new Date(resource.publishedAt)
    const dateStr = dt.toLocaleDateString('en-US', { month: 'long', day: 'numeric', year: 'numeric' })
    const meta = [`<time datetime="${e(resource.publishedAt)}">${e(dateStr)}</time>`]
    if (isEditorial) meta.push(`<span>${readTime} min read</span>`)
    p.push(`<div>${meta.join(' &middot; ')}</div>`)
  }

  p.push(`<p><strong>${e(resource.summary)}</strong></p>`)

  if (isEditorial && resource.sections?.length) {
    for (const section of resource.sections) {
      p.push(`<h2>${e(section.heading)}</h2>`)
      for (const para of String(section.body || '').split('\n')) {
        const trimmed = para.trim()
        if (trimmed) p.push(`<p>${e(trimmed)}</p>`)
      }
    }
  }

  renderListSection(p, resource, 'whoItsFor', 'Who This Is For')
  renderListSection(p, resource, 'whenThisIsRelevant', 'When This Is Relevant')
  renderListSection(p, resource, 'supportedInputs', 'Supported Inputs')
  renderListSection(p, resource, 'expectedOutputs', 'Expected Outputs')
  renderListSection(p, resource, 'commonChallenges', 'Common Challenges')

  if (resource.howItWorksSteps?.length) {
    p.push('<h2>How It Works</h2><ol>')
    for (const step of resource.howItWorksSteps) p.push(`<li>${e(step)}</li>`)
    p.push('</ol>')
  }

  renderListSection(p, resource, 'whyPdfExcelAiFits', 'Why PDFexcel.ai')
  renderListSection(p, resource, 'limitations', 'Limitations')
  renderListSection(p, resource, 'exampleUseCases', 'Example Use Cases')

  if (resource.faq?.length) {
    p.push('<h2>Frequently Asked Questions</h2>')
    for (const f of resource.faq) {
      p.push(`<h3>${e(f.question)}</h3>`)
      p.push(`<p>${e(f.answer)}</p>`)
    }
  }

  p.push('<h2>Ready to extract data from your PDFs?</h2>')
  p.push('<p>Upload your first document and see structured results in seconds. Free to start — no setup required.</p>')
  p.push('<a href="/">Get Started Free</a>')

  if (resource.relatedResources?.length) {
    p.push('<h3>Related Resources</h3><ul>')
    for (const slug of resource.relatedResources) {
      const label = slug.split('-').map(w => w.charAt(0).toUpperCase() + w.slice(1)).join(' ')
      p.push(`<li><a href="/resources/${e(slug)}">${e(label)}</a></li>`)
    }
    p.push('</ul>')
  }

  p.push('</article>')
  p.push('<footer><nav><a href="/">Home</a> | <a href="/resources">Resources</a> | <a href="/privacy">Privacy Policy</a> | <a href="/terms">Terms of Service</a></nav></footer>')
  p.push('</div>')

  return p.join('\n')
}

function buildHubHead() {
  const title = 'Resources — PDF to Excel Guides, Tutorials & Workflows | PDFexcel.ai'
  const desc = 'Practical guides for converting PDFs to Excel, extracting tables from documents, automating workflows, and getting the most out of PDFexcel.ai.'

  const lines = [
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
    `<title>${e(title)}</title>`,
    `<meta name="description" content="${e(desc)}" />`,
    '<meta name="robots" content="index, follow" />',
    `<link rel="canonical" href="${BASE_URL}/resources" />`,
    `<meta property="og:title" content="Resources — PDF to Excel Guides &amp; Tutorials | PDFexcel.ai" />`,
    `<meta property="og:description" content="${e(desc)}" />`,
    `<meta property="og:url" content="${BASE_URL}/resources" />`,
    '<meta property="og:type" content="website" />',
    '<meta property="og:site_name" content="PDFexcel.ai" />',
    `<meta property="og:image" content="${BASE_URL}/og-image.png" />`,
    '<meta property="og:image:width" content="1200" />',
    '<meta property="og:image:height" content="630" />',
    '<meta name="twitter:card" content="summary_large_image" />',
    `<meta name="twitter:title" content="Resources — PDF to Excel Guides &amp; Tutorials | PDFexcel.ai" />`,
    `<meta name="twitter:description" content="${e(desc)}" />`,
    `<meta name="twitter:image" content="${BASE_URL}/og-image.png" />`,
    jsonLd({ '@context': 'https://schema.org', '@type': 'CollectionPage', name: 'PDF to Excel Resources', description: desc, url: `${BASE_URL}/resources`, publisher: { '@type': 'Organization', name: 'PDFexcel.ai', url: BASE_URL } }),
    jsonLd({ '@context': 'https://schema.org', '@type': 'BreadcrumbList', itemListElement: [{ '@type': 'ListItem', position: 1, name: 'Home', item: `${BASE_URL}/` }, { '@type': 'ListItem', position: 2, name: 'Resources', item: `${BASE_URL}/resources` }] }),
  ]
  return lines.join('\n    ')
}

function buildHubBody(registry) {
  const published = (registry.resources || []).filter(r => r.indexationStatus === 'published' || r.indexationStatus === 'noindex')
  const grouped = {}
  for (const r of published) {
    const cat = r.templateType || r.category || 'other'
    if (!grouped[cat]) grouped[cat] = []
    grouped[cat].push(r)
  }

  const p = []
  p.push('<div style="max-width:1152px;margin:0 auto;padding:16px">')
  p.push('<nav aria-label="Breadcrumb"><a href="/">Home</a> &rsaquo; <span>Resources</span></nav>')
  p.push('<h1>PDF to Excel Resources</h1>')
  p.push('<p>Practical guides for converting PDFs to spreadsheets, extracting structured data from documents, and automating document-to-Excel workflows.</p>')

  for (const [catKey, catLabel] of Object.entries(CATEGORY_MAP)) {
    const items = grouped[catKey] || []
    if (!items.length) continue
    p.push(`<h2>${catLabel}</h2><ul>`)
    for (const r of items) {
      p.push(`<li><a href="/resources/${e(r.slug)}">${e(r.title)}</a> — ${e(r.metaDescription || '')}</li>`)
    }
    p.push('</ul>')
  }

  p.push('<footer><nav><a href="/">Home</a> | <a href="/resources">Resources</a> | <a href="/privacy">Privacy Policy</a> | <a href="/terms">Terms of Service</a></nav></footer>')
  p.push('</div>')
  return p.join('\n')
}

function buildHtml(headContent, bodyContent, assetCss, assetJs) {
  return `<!doctype html>
<html lang="en">
  <head>
    ${headContent}
    ${assetCss}
  </head>
  <body>
    <div id="root">${bodyContent}</div>
    ${assetJs}
  </body>
</html>
`
}

function main() {
  const args = process.argv.slice(2)
  let distDir = DIST_DIR
  let slugFilter = null

  for (let i = 0; i < args.length; i++) {
    if (args[i] === '--dist' && args[i + 1]) distDir = resolve(args[++i])
    if (args[i] === '--slug' && args[i + 1]) slugFilter = args[++i]
  }

  const indexHtmlPath = join(distDir, 'index.html')
  if (!existsSync(indexHtmlPath)) {
    console.error(`[prerender] ERROR: ${indexHtmlPath} not found. Run 'vite build' first.`)
    process.exit(1)
  }

  const indexHtml = readFileSync(indexHtmlPath, 'utf-8')
  const { css: assetCss, js: assetJs } = getAssetTags(indexHtml)
  if (!assetJs) console.warn('[prerender] WARNING: No JS module script found in index.html')

  // Load registry
  const registryPath = join(CONTENT_DIR, 'registry.json')
  if (!existsSync(registryPath)) {
    console.error(`[prerender] ERROR: registry.json not found at ${registryPath}`)
    process.exit(1)
  }
  const registry = JSON.parse(readFileSync(registryPath, 'utf-8'))

  let count = 0
  let errors = 0

  // Pre-render hub
  if (!slugFilter) {
    try {
      const hubDir = join(distDir, 'resources')
      mkdirSync(hubDir, { recursive: true })
      const hubHtml = buildHtml(buildHubHead(), buildHubBody(registry), assetCss, assetJs)
      writeFileSync(join(hubDir, 'index.html'), hubHtml, 'utf-8')
      count++
      console.log(`[prerender] Hub: ${join(hubDir, 'index.html')}`)
    } catch (err) {
      console.error(`[prerender] ERROR on hub: ${err.message}`)
      errors++
    }
  }

  // Pre-render individual resource pages
  const resourceFiles = readdirSync(CONTENT_DIR).filter(f => f.endsWith('.json') && f !== 'registry.json').sort()

  for (const file of resourceFiles) {
    try {
      const resource = JSON.parse(readFileSync(join(CONTENT_DIR, file), 'utf-8'))
      const slug = resource.slug || file.replace('.json', '')
      const status = resource.indexationStatus || 'draft'

      if (status !== 'published' && status !== 'noindex') continue
      if (slugFilter && slug !== slugFilter) continue

      const pageDir = join(distDir, 'resources', slug)
      mkdirSync(pageDir, { recursive: true })
      const html = buildHtml(buildHead(resource), buildBody(resource), assetCss, assetJs)
      writeFileSync(join(pageDir, 'index.html'), html, 'utf-8')
      count++
    } catch (err) {
      console.error(`[prerender] ERROR on ${file}: ${err.message}`)
      errors++
    }
  }

  console.log(`[prerender] Done: ${count} pages pre-rendered (${errors} errors)`)
  if (errors > 0) process.exit(1)
}

main()
