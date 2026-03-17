import { useEffect, useState } from 'react'
import { useParams, Link, useNavigate } from 'react-router-dom'
import { Helmet } from 'react-helmet-async'
import {
  FileSpreadsheet, ChevronRight, ArrowRight, CheckCircle2, AlertTriangle,
  Users, Clock, FileInput, FileOutput, Zap, HelpCircle, Target, Shield
} from 'lucide-react'
import type { ResourceContent } from './types'
import { TEMPLATE_LABELS, EDITORIAL_TEMPLATES } from './types'

function Section({ icon: Icon, title, children }: { icon: React.ElementType; title: string; children: React.ReactNode }) {
  return (
    <section className="mb-8">
      <div className="flex items-center gap-2 mb-3">
        <Icon size={16} className="text-primary" />
        <h2 className="text-base font-semibold text-foreground">{title}</h2>
      </div>
      {children}
    </section>
  )
}

function BulletList({ items, icon }: { items: string[]; icon?: 'check' | 'alert' }) {
  return (
    <ul className="space-y-1.5">
      {items.map((item, i) => (
        <li key={i} className="flex items-start gap-2 text-sm text-muted-foreground">
          {icon === 'check' && <CheckCircle2 size={13} className="text-green-500 shrink-0 mt-0.5" />}
          {icon === 'alert' && <AlertTriangle size={13} className="text-amber-500 shrink-0 mt-0.5" />}
          {!icon && <span className="w-1 h-1 rounded-full bg-muted-foreground/40 shrink-0 mt-2" />}
          <span>{item}</span>
        </li>
      ))}
    </ul>
  )
}

function ArticleBody({ sections }: { sections: { heading: string; body: string }[] }) {
  return (
    <div className="space-y-8">
      {sections.map((section, i) => (
        <section key={i}>
          <h2 className="text-lg font-semibold text-foreground mb-3">{section.heading}</h2>
          <div className="text-sm text-muted-foreground leading-relaxed whitespace-pre-line">
            {section.body}
          </div>
        </section>
      ))}
    </div>
  )
}

function estimateReadTime(resource: ResourceContent): number {
  let totalWords = 0
  const countWords = (text: string) => text.split(/\s+/).filter(Boolean).length
  totalWords += countWords(resource.summary || '')
  for (const s of resource.sections || []) {
    totalWords += countWords(s.body || '')
  }
  for (const f of resource.faq || []) {
    totalWords += countWords(f.answer || '')
  }
  for (const field of ['whoItsFor', 'commonChallenges', 'howItWorksSteps', 'whyPdfExcelAiFits', 'limitations', 'exampleUseCases'] as const) {
    for (const item of (resource as unknown as Record<string, string[]>)[field] || []) {
      totalWords += countWords(item || '')
    }
  }
  return Math.max(1, Math.round(totalWords / 230))
}

function NumberedList({ items }: { items: string[] }) {
  return (
    <ol className="space-y-2">
      {items.map((item, i) => (
        <li key={i} className="flex items-start gap-3 text-sm text-muted-foreground">
          <span className="flex items-center justify-center w-5 h-5 rounded-full bg-primary/10 text-primary text-[10px] font-semibold shrink-0 mt-0.5">
            {i + 1}
          </span>
          <span>{item}</span>
        </li>
      ))}
    </ol>
  )
}

export default function ResourcePage() {
  const { slug } = useParams<{ slug: string }>()
  const navigate = useNavigate()
  const [resource, setResource] = useState<ResourceContent | null>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    if (!slug) return
    fetch(`/content/resources/${slug}.json`)
      .then((r) => {
        if (!r.ok) throw new Error('Not found')
        return r.json()
      })
      .then((data: ResourceContent) => {
        if (data.indexationStatus === 'draft' || data.indexationStatus === 'rejected') {
          navigate('/resources', { replace: true })
          return
        }
        setResource(data)
        setLoading(false)
      })
      .catch(() => {
        navigate('/resources', { replace: true })
      })
  }, [slug, navigate])

  if (loading || !resource) {
    return (
      <div className="min-h-screen bg-background flex items-center justify-center">
        <div className="w-6 h-6 border-2 border-primary border-t-transparent rounded-full animate-spin" />
      </div>
    )
  }

  const isNoindex = resource.indexationStatus === 'noindex'
  const isEditorial = EDITORIAL_TEMPLATES.has(resource.templateType)
  const readTime = estimateReadTime(resource)

  const faqSchema = resource.faq.length > 0 ? {
    '@context': 'https://schema.org',
    '@type': 'FAQPage',
    mainEntity: resource.faq.map((f) => ({
      '@type': 'Question',
      name: f.question,
      acceptedAnswer: { '@type': 'Answer', text: f.answer },
    })),
  } : null

  const articleSchema = isEditorial ? {
    '@context': 'https://schema.org',
    '@type': 'Article',
    headline: resource.h1,
    description: resource.metaDescription,
    datePublished: resource.publishedAt,
    dateModified: resource.updatedAt || resource.publishedAt,
    publisher: { '@type': 'Organization', name: 'PDFexcel.ai', url: 'https://pdfexcel.ai' },
    mainEntityOfPage: resource.canonicalUrl || `https://pdfexcel.ai/resources/${resource.slug}`,
  } : null

  return (
    <>
      <Helmet>
        <title>{resource.metaTitle}</title>
        <meta name="description" content={resource.metaDescription} />
        <meta name="robots" content={isNoindex ? 'noindex, follow' : 'index, follow'} />
        <link rel="canonical" href={resource.canonicalUrl || `https://pdfexcel.ai/resources/${resource.slug}`} />
        <meta property="og:title" content={resource.metaTitle} />
        <meta property="og:description" content={resource.metaDescription} />
        <meta property="og:url" content={`https://pdfexcel.ai/resources/${resource.slug}`} />
        <meta property="og:type" content="article" />
        {faqSchema && <script type="application/ld+json">{JSON.stringify(faqSchema)}</script>}
        {articleSchema && <script type="application/ld+json">{JSON.stringify(articleSchema)}</script>}
      </Helmet>

      <div className="min-h-screen bg-background">
        {/* Nav */}
        <header className="border-b border-border/50 bg-card/80 backdrop-blur-sm sticky top-0 z-30">
          <div className="max-w-4xl mx-auto px-4 sm:px-6 h-14 flex items-center justify-between">
            <Link to="/" className="flex items-center gap-2 text-sm font-semibold text-foreground">
              <div className="w-6 h-6 bg-primary rounded-md flex items-center justify-center">
                <FileSpreadsheet size={14} className="text-white" />
              </div>
              PDFexcel.ai
            </Link>
            <nav className="flex items-center gap-4 text-xs text-muted-foreground">
              <Link to="/resources" className="hover:text-foreground transition-colors">Resources</Link>
              <Link to="/" className="hover:text-foreground transition-colors">Product</Link>
            </nav>
          </div>
        </header>

        {/* Article */}
        <article className="px-4 sm:px-6 pt-8 pb-16">
          <div className="max-w-4xl mx-auto">
            {/* Breadcrumbs */}
            <nav className="flex items-center gap-1.5 text-xs text-muted-foreground mb-6">
              <Link to="/" className="hover:text-foreground transition-colors">Home</Link>
              <ChevronRight size={10} />
              <Link to="/resources" className="hover:text-foreground transition-colors">Resources</Link>
              <ChevronRight size={10} />
              <span className="text-foreground/70 truncate max-w-[200px]">{resource.title}</span>
            </nav>

            {/* Hero */}
            <div className="mb-10">
              <span className="inline-block text-[10px] font-medium uppercase tracking-wider text-primary/70 bg-primary/5 px-2 py-0.5 rounded-full mb-3">
                {TEMPLATE_LABELS[resource.templateType] || resource.templateType}
              </span>
              <h1 className="text-2xl sm:text-3xl font-bold text-foreground tracking-tight mb-3">
                {resource.h1}
              </h1>
              <p className="text-sm text-muted-foreground max-w-2xl mb-3">
                {resource.hero.subheadline}
              </p>
              {(isEditorial || resource.publishedAt) && (
                <div className="flex items-center gap-3 text-xs text-muted-foreground/70 mb-4">
                  {resource.publishedAt && (
                    <time dateTime={resource.publishedAt}>
                      {new Date(resource.publishedAt).toLocaleDateString('en-US', { month: 'long', day: 'numeric', year: 'numeric' })}
                    </time>
                  )}
                  {isEditorial && <span>{readTime} min read</span>}
                </div>
              )}
              <div className="flex flex-wrap gap-2">
                <Link
                  to="/"
                  className="inline-flex items-center gap-1.5 px-4 py-2 text-xs font-medium rounded-lg bg-primary text-white hover:bg-primary/90 transition-colors"
                >
                  {resource.hero.primaryCta}
                  <ArrowRight size={12} />
                </Link>
                {resource.hero.secondaryCta && (
                  <Link
                    to="/resources"
                    className="inline-flex items-center gap-1.5 px-4 py-2 text-xs font-medium rounded-lg border border-border/60 text-foreground hover:bg-muted/50 transition-colors"
                  >
                    {resource.hero.secondaryCta}
                  </Link>
                )}
              </div>
            </div>

            {/* Summary */}
            <div className="rounded-xl border border-primary/10 bg-primary/[0.02] p-5 mb-8">
              <p className="text-sm text-foreground leading-relaxed">{resource.summary}</p>
            </div>

            <div className="grid gap-0 lg:grid-cols-[1fr_280px] lg:gap-10">
              <div>
                {isEditorial && resource.sections && resource.sections.length > 0 ? (
                  <>
                    {/* Editorial: Article body sections */}
                    <div className="mb-10">
                      <ArticleBody sections={resource.sections} />
                    </div>

                    {/* Who it's for */}
                    {resource.whoItsFor.length > 0 && (
                      <Section icon={Users} title="Who This Is For">
                        <BulletList items={resource.whoItsFor} />
                      </Section>
                    )}

                    {/* Limitations / Caveats */}
                    {resource.limitations.length > 0 && (
                      <Section icon={Shield} title="Caveats & Limitations">
                        <BulletList items={resource.limitations} icon="alert" />
                      </Section>
                    )}

                    {/* FAQ */}
                    {resource.faq.length > 0 && (
                      <Section icon={HelpCircle} title="Frequently Asked Questions">
                        <div className="space-y-4">
                          {resource.faq.map((f, i) => (
                            <div key={i} className="border border-border/40 rounded-lg p-4">
                              <h3 className="text-sm font-medium text-foreground mb-1.5">{f.question}</h3>
                              <p className="text-xs text-muted-foreground leading-relaxed">{f.answer}</p>
                            </div>
                          ))}
                        </div>
                      </Section>
                    )}
                  </>
                ) : (
                  <>
                    {/* Product content: standard sections */}
                    {resource.whoItsFor.length > 0 && (
                      <Section icon={Users} title="Who This Is For">
                        <BulletList items={resource.whoItsFor} />
                      </Section>
                    )}

                    {resource.whenThisIsRelevant.length > 0 && (
                      <Section icon={Clock} title="When This Is Relevant">
                        <BulletList items={resource.whenThisIsRelevant} />
                      </Section>
                    )}

                    {resource.supportedInputs.length > 0 && (
                      <Section icon={FileInput} title="Supported Inputs">
                        <BulletList items={resource.supportedInputs} icon="check" />
                      </Section>
                    )}

                    {resource.expectedOutputs.length > 0 && (
                      <Section icon={FileOutput} title="Expected Outputs">
                        <BulletList items={resource.expectedOutputs} icon="check" />
                      </Section>
                    )}

                    {resource.commonChallenges.length > 0 && (
                      <Section icon={AlertTriangle} title="Common Challenges">
                        <BulletList items={resource.commonChallenges} />
                      </Section>
                    )}

                    {resource.howItWorksSteps.length > 0 && (
                      <Section icon={Zap} title="How It Works">
                        <NumberedList items={resource.howItWorksSteps} />
                      </Section>
                    )}

                    {resource.whyPdfExcelAiFits.length > 0 && (
                      <Section icon={Target} title="Why PDFexcel.ai">
                        <BulletList items={resource.whyPdfExcelAiFits} icon="check" />
                      </Section>
                    )}

                    {resource.limitations.length > 0 && (
                      <Section icon={Shield} title="Limitations & Edge Cases">
                        <BulletList items={resource.limitations} icon="alert" />
                      </Section>
                    )}

                    {resource.exampleUseCases.length > 0 && (
                      <Section icon={Target} title="Example Use Cases">
                        <BulletList items={resource.exampleUseCases} />
                      </Section>
                    )}

                    {resource.faq.length > 0 && (
                      <Section icon={HelpCircle} title="Frequently Asked Questions">
                        <div className="space-y-4">
                          {resource.faq.map((f, i) => (
                            <div key={i} className="border border-border/40 rounded-lg p-4">
                              <h3 className="text-sm font-medium text-foreground mb-1.5">{f.question}</h3>
                              <p className="text-xs text-muted-foreground leading-relaxed">{f.answer}</p>
                            </div>
                          ))}
                        </div>
                      </Section>
                    )}
                  </>
                )}
              </div>

              {/* Sidebar */}
              <aside className="hidden lg:block">
                <div className="sticky top-20 space-y-5">
                  {/* CTA Card */}
                  <div className="rounded-xl border border-primary/15 bg-primary/[0.02] p-5">
                    <h3 className="text-sm font-semibold text-foreground mb-2">Try it now</h3>
                    <p className="text-xs text-muted-foreground mb-4">
                      Upload your PDF and get a clean spreadsheet in seconds. Free to start.
                    </p>
                    <Link
                      to="/"
                      className="block w-full text-center px-4 py-2.5 text-xs font-medium rounded-lg bg-primary text-white hover:bg-primary/90 transition-colors"
                    >
                      Convert PDF to Excel
                    </Link>
                  </div>

                  {/* Trust Signals */}
                  {resource.trustSignals.length > 0 && (
                    <div className="rounded-xl border border-border/40 p-4">
                      <h3 className="text-xs font-semibold text-foreground mb-2">Why PDFexcel.ai</h3>
                      <ul className="space-y-1.5">
                        {resource.trustSignals.map((s, i) => (
                          <li key={i} className="flex items-start gap-2 text-[11px] text-muted-foreground">
                            <CheckCircle2 size={11} className="text-green-500 shrink-0 mt-0.5" />
                            <span>{s}</span>
                          </li>
                        ))}
                      </ul>
                    </div>
                  )}

                  {/* Related resources */}
                  {resource.relatedResources.length > 0 && (
                    <div className="rounded-xl border border-border/40 p-4">
                      <h3 className="text-xs font-semibold text-foreground mb-2">Related Resources</h3>
                      <ul className="space-y-1.5">
                        {resource.relatedResources.map((slug, i) => (
                          <li key={i}>
                            <Link
                              to={`/resources/${slug}`}
                              className="text-[11px] text-primary hover:underline"
                            >
                              {slug.split('-').map((w) => w.charAt(0).toUpperCase() + w.slice(1)).join(' ')}
                            </Link>
                          </li>
                        ))}
                      </ul>
                    </div>
                  )}
                </div>
              </aside>
            </div>

            {/* Bottom CTA */}
            <div className="mt-12 rounded-xl border border-primary/10 bg-primary/[0.02] p-6 text-center">
              <h2 className="text-lg font-semibold text-foreground mb-2">
                Ready to extract data from your PDFs?
              </h2>
              <p className="text-sm text-muted-foreground mb-4 max-w-md mx-auto">
                Upload your first document and see structured results in seconds. Free to start — no setup required.
              </p>
              <Link
                to="/"
                className="inline-flex items-center gap-1.5 px-5 py-2.5 text-sm font-medium rounded-lg bg-primary text-white hover:bg-primary/90 transition-colors"
              >
                Get Started Free
                <ArrowRight size={14} />
              </Link>
            </div>

            {/* Mobile related resources */}
            {resource.relatedResources.length > 0 && (
              <div className="mt-8 lg:hidden">
                <h3 className="text-sm font-semibold text-foreground mb-3">Related Resources</h3>
                <div className="flex flex-wrap gap-2">
                  {resource.relatedResources.map((slug, i) => (
                    <Link
                      key={i}
                      to={`/resources/${slug}`}
                      className="text-xs text-primary border border-primary/20 rounded-full px-3 py-1 hover:bg-primary/5 transition-colors"
                    >
                      {slug.split('-').map((w) => w.charAt(0).toUpperCase() + w.slice(1)).join(' ')}
                    </Link>
                  ))}
                </div>
              </div>
            )}
          </div>
        </article>

        {/* Footer */}
        <footer className="border-t border-border/50 py-6 px-4 sm:px-6">
          <div className="max-w-6xl mx-auto flex flex-col items-center gap-3 text-xs text-muted-foreground">
            <div className="flex items-center gap-2">
              <div className="w-5 h-5 bg-primary rounded-md flex items-center justify-center">
                <FileSpreadsheet size={11} className="text-white" />
              </div>
              PDF to Excel
            </div>
            <div className="flex flex-wrap items-center justify-center gap-x-4 gap-y-1">
              <Link to="/" className="hover:text-foreground transition-colors">Home</Link>
              <Link to="/resources" className="hover:text-foreground transition-colors">Resources</Link>
              <Link to="/privacy" className="hover:text-foreground transition-colors">Privacy Policy</Link>
              <Link to="/terms" className="hover:text-foreground transition-colors">Terms of Service</Link>
              <a href="mailto:bigvisionsystems@gmail.com" className="hover:text-foreground transition-colors">Contact</a>
            </div>
            <span>© 2026 Big Vision Systems LLC. All rights reserved.</span>
          </div>
        </footer>
      </div>
    </>
  )
}
