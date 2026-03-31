import { useEffect, useState } from 'react'
import { Helmet } from 'react-helmet-async'
import { Link } from 'react-router-dom'
import { FileSpreadsheet, ArrowRight, Search, ChevronRight } from 'lucide-react'
import type { ResourceRegistry, ResourceRegistryEntry } from './types'
import { CATEGORY_MAP, TEMPLATE_LABELS } from './types'

function ResourceCard({ resource }: { resource: ResourceRegistryEntry }) {
  return (
    <Link
      to={`/resources/${resource.slug}`}
      className="group block rounded-xl border border-border/60 bg-card p-5 hover:border-primary/30 hover:shadow-md transition-all duration-200"
    >
      <div className="flex items-start justify-between gap-3">
        <div className="flex-1 min-w-0">
          <span className="inline-block text-[10px] font-medium uppercase tracking-wider text-primary/70 bg-primary/5 px-2 py-0.5 rounded-full mb-2">
            {TEMPLATE_LABELS[resource.templateType] || resource.templateType}
          </span>
          <h3 className="text-sm font-semibold text-foreground group-hover:text-primary transition-colors line-clamp-2 mb-1.5">
            {resource.title}
          </h3>
          <p className="text-xs text-muted-foreground line-clamp-2">
            {resource.metaDescription}
          </p>
        </div>
        <ArrowRight size={14} className="text-muted-foreground/50 group-hover:text-primary shrink-0 mt-1 transition-colors" />
      </div>
    </Link>
  )
}

function CategorySection({ title, resources }: { title: string; resources: ResourceRegistryEntry[] }) {
  if (resources.length === 0) return null
  return (
    <section className="mb-10">
      <h2 className="text-lg font-semibold text-foreground mb-4">{title}</h2>
      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
        {resources.map((r) => (
          <ResourceCard key={r.slug} resource={r} />
        ))}
      </div>
    </section>
  )
}

export default function ResourcesHub() {
  const [registry, setRegistry] = useState<ResourceRegistry | null>(null)
  const [loading, setLoading] = useState(true)
  const [search, setSearch] = useState('')

  useEffect(() => {
    fetch('/content/resources/registry.json')
      .then((r) => r.json())
      .then((data) => { setRegistry(data); setLoading(false) })
      .catch(() => setLoading(false))
  }, [])

  const published = registry?.resources?.filter((r) => r.indexationStatus === 'published' || r.indexationStatus === 'noindex') || []

  const filtered = search.trim()
    ? published.filter((r) =>
        r.title.toLowerCase().includes(search.toLowerCase()) ||
        r.metaDescription.toLowerCase().includes(search.toLowerCase()) ||
        r.primaryKeyword.toLowerCase().includes(search.toLowerCase())
      )
    : published

  const grouped = Object.entries(CATEGORY_MAP).reduce((acc, [type, label]) => {
    const items = filtered.filter((r) => r.templateType === type)
    if (items.length > 0) acc.push({ label, items })
    return acc
  }, [] as { label: string; items: ResourceRegistryEntry[] }[])

  const recent = [...filtered].sort((a, b) => new Date(b.publishedAt).getTime() - new Date(a.publishedAt).getTime()).slice(0, 6)

  return (
    <>
      <Helmet>
        <title>Resources — PDF to Excel Guides, Tutorials & Workflows | PDFexcel.ai</title>
        <meta name="description" content="Practical guides for converting PDFs to Excel, extracting tables from documents, automating workflows, and getting the most out of PDFexcel.ai." />
        <meta name="robots" content="index, follow" />
        <link rel="canonical" href="https://gridpull.com/resources" />
        {/* Open Graph */}
        <meta property="og:title" content="Resources — PDF to Excel Guides & Tutorials | PDFexcel.ai" />
        <meta property="og:description" content="Practical guides for converting PDFs to Excel, extracting tables from documents, automating workflows, and getting the most out of PDFexcel.ai." />
        <meta property="og:url" content="https://gridpull.com/resources" />
        <meta property="og:type" content="website" />
        <meta property="og:site_name" content="PDFexcel.ai" />
        <meta property="og:image" content="https://gridpull.com/og-image.png" />
        <meta property="og:image:width" content="1200" />
        <meta property="og:image:height" content="630" />
        <meta property="og:image:alt" content="PDFexcel.ai Resources — Guides, tutorials, and insights on PDF data extraction" />
        {/* Twitter Card */}
        <meta name="twitter:card" content="summary_large_image" />
        <meta name="twitter:title" content="Resources — PDF to Excel Guides & Tutorials | PDFexcel.ai" />
        <meta name="twitter:description" content="Practical guides for converting PDFs to Excel, extracting tables from documents, and automating workflows." />
        <meta name="twitter:image" content="https://gridpull.com/og-image.png" />
        <meta name="twitter:image:alt" content="PDFexcel.ai Resources — Guides, tutorials, and insights on PDF data extraction" />
        {/* Structured Data */}
        <script type="application/ld+json">{JSON.stringify({
          '@context': 'https://schema.org',
          '@type': 'CollectionPage',
          name: 'PDF to Excel Resources',
          description: 'Practical guides for converting PDFs to Excel, extracting tables from documents, automating workflows, and getting the most out of PDFexcel.ai.',
          url: 'https://gridpull.com/resources',
          publisher: { '@type': 'Organization', name: 'PDFexcel.ai', url: 'https://gridpull.com' },
        })}</script>
        <script type="application/ld+json">{JSON.stringify({
          '@context': 'https://schema.org',
          '@type': 'BreadcrumbList',
          itemListElement: [
            { '@type': 'ListItem', position: 1, name: 'Home', item: 'https://gridpull.com/' },
            { '@type': 'ListItem', position: 2, name: 'Resources', item: 'https://gridpull.com/resources' },
          ],
        })}</script>
      </Helmet>

      <div className="min-h-screen bg-background">
        {/* Nav */}
        <header className="border-b border-border/50 bg-card/80 backdrop-blur-sm sticky top-0 z-30">
          <div className="max-w-6xl mx-auto px-4 sm:px-6 h-14 flex items-center justify-between">
            <Link to="/" className="flex items-center gap-2 text-sm font-semibold text-foreground">
              <div className="w-6 h-6 bg-primary rounded-md flex items-center justify-center">
                <FileSpreadsheet size={14} className="text-white" />
              </div>
              PDFexcel.ai
            </Link>
            <nav className="flex items-center gap-4 text-xs text-muted-foreground">
              <Link to="/resources" className="text-foreground font-medium">Resources</Link>
              <Link to="/" className="hover:text-foreground transition-colors">Product</Link>
            </nav>
          </div>
        </header>

        {/* Hero */}
        <section className="pt-12 pb-8 px-4 sm:px-6">
          <div className="max-w-6xl mx-auto">
            <nav className="flex items-center gap-1.5 text-xs text-muted-foreground mb-6">
              <Link to="/" className="hover:text-foreground transition-colors">Home</Link>
              <ChevronRight size={10} />
              <span className="text-foreground">Resources</span>
            </nav>
            <h1 className="text-2xl sm:text-3xl font-bold text-foreground tracking-tight mb-3">
              PDF to Excel Resources
            </h1>
            <p className="text-sm text-muted-foreground max-w-2xl mb-6">
              Practical guides for converting PDFs to spreadsheets, extracting structured data from documents, and automating document-to-Excel workflows.
            </p>

            {/* Search */}
            <div className="relative max-w-md">
              <Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-muted-foreground/60" />
              <input
                type="text"
                placeholder="Search resources..."
                value={search}
                onChange={(e) => setSearch(e.target.value)}
                className="w-full pl-9 pr-4 py-2.5 text-sm rounded-lg border border-border/60 bg-card focus:outline-none focus:ring-2 focus:ring-primary/20 focus:border-primary/40 transition-all"
              />
            </div>
          </div>
        </section>

        {/* Content */}
        <main className="px-4 sm:px-6 pb-16">
          <div className="max-w-6xl mx-auto">
            {loading ? (
              <div className="flex items-center justify-center py-20">
                <div className="w-6 h-6 border-2 border-primary border-t-transparent rounded-full animate-spin" />
              </div>
            ) : published.length === 0 ? (
              <div className="text-center py-20 text-sm text-muted-foreground">
                Resources are being prepared. Check back soon.
              </div>
            ) : (
              <>
                {/* Recently published */}
                {!search.trim() && recent.length > 0 && (
                  <section className="mb-10">
                    <h2 className="text-lg font-semibold text-foreground mb-4">Recently Published</h2>
                    <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
                      {recent.map((r) => (
                        <ResourceCard key={r.slug} resource={r} />
                      ))}
                    </div>
                  </section>
                )}

                {/* Grouped by category */}
                {grouped.map(({ label, items }) => (
                  <CategorySection key={label} title={label} resources={items} />
                ))}

                {filtered.length === 0 && search.trim() && (
                  <div className="text-center py-12 text-sm text-muted-foreground">
                    No resources match "{search}"
                  </div>
                )}
              </>
            )}
          </div>
        </main>

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
