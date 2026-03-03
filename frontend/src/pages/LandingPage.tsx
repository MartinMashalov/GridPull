import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useGoogleLogin } from '@react-oauth/google'
import {
  FileSpreadsheet, Zap, Shield, ArrowRight,
  Building2, GitBranch, Lock, Mail,
  Receipt, BarChart3, FileText, ShoppingCart, TrendingUp, ClipboardList,
  CheckCircle2, ChevronRight,
} from 'lucide-react'
import api from '@/lib/api'
import { useAuthStore } from '@/store/authStore'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { Card, CardContent } from '@/components/ui/card'

const FEATURES = [
  {
    icon: Zap,
    title: 'AI-Powered Extraction',
    desc: 'GPT-4.1 reads and understands any PDF structure — invoices, reports, contracts, and more.',
  },
  {
    icon: FileSpreadsheet,
    title: 'Perfect Spreadsheets',
    desc: 'Structured Excel or CSV output with every field exactly where you need it.',
  },
  {
    icon: Shield,
    title: 'Enterprise Accuracy',
    desc: '94%+ field fill rate tested across thousands of real-world documents.',
  },
]

const USE_CASES = [
  {
    icon: Receipt,
    label: 'Invoices & Bills',
    color: 'bg-blue-500/10 text-blue-600',
    example: 'Extract vendor name, invoice #, line items, totals, and due dates from any invoice format.',
    fields: ['Invoice Number', 'Vendor Name', 'Total Amount', 'Due Date', 'Line Items'],
  },
  {
    icon: BarChart3,
    label: 'Financial Reports',
    color: 'bg-violet-500/10 text-violet-600',
    example: 'Pull revenue, net income, total assets, and equity from annual reports and 10-Ks.',
    fields: ['Total Revenue', 'Net Income', 'Total Assets', 'Shareholders Equity'],
  },
  {
    icon: FileText,
    label: 'Insurance EOBs',
    color: 'bg-emerald-500/10 text-emerald-600',
    example: 'Digitize explanation of benefits forms — patient info, claim lines, amounts paid.',
    fields: ['Patient Name', 'Service Date', 'Billed Amount', 'Plan Paid', 'Patient Responsibility'],
  },
  {
    icon: ShoppingCart,
    label: 'Purchase Orders',
    color: 'bg-orange-500/10 text-orange-600',
    example: 'Capture PO number, supplier details, ordered items, quantities, and pricing.',
    fields: ['PO Number', 'Supplier Name', 'Item Description', 'Quantity', 'Unit Price'],
  },
  {
    icon: TrendingUp,
    label: 'Annual Reports',
    color: 'bg-pink-500/10 text-pink-600',
    example: 'Benchmark across companies — extract consistent metrics from any annual report.',
    fields: ['Company Name', 'Report Year', 'Operating Income', 'Total Equity'],
  },
  {
    icon: ClipboardList,
    label: 'Contracts & Forms',
    color: 'bg-teal-500/10 text-teal-600',
    example: 'Extract parties, dates, key terms, and obligations from legal documents.',
    fields: ['Party Names', 'Effective Date', 'Contract Value', 'Expiry Date'],
  },
]

const STATS = [
  { value: '94%+', label: 'Average field fill rate' },
  { value: '< 30s', label: 'Per document processed' },
  { value: '6 types', label: 'Document categories' },
  { value: '100%', label: 'Data privacy — no storage' },
]

const DEPLOYMENTS = [
  {
    icon: Building2,
    title: 'Private Infrastructure',
    desc: 'Run entirely within your VPC or on-premise environment. No data ever leaves your network.',
  },
  {
    icon: GitBranch,
    title: 'Custom Pipelines',
    desc: 'Extraction logic tailored to your specific document types, field definitions, and validation rules.',
  },
  {
    icon: Lock,
    title: 'Zero Data Sharing',
    desc: 'Documents are processed in isolated containers and deleted immediately after extraction.',
  },
]

export default function LandingPage() {
  const navigate = useNavigate()
  const { setUser, user } = useAuthStore()
  const [loading, setLoading] = useState(false)
  const [loginError, setLoginError] = useState<string | null>(null)
  const [activeCase, setActiveCase] = useState(0)

  const googleLogin = useGoogleLogin({
    onSuccess: async (tokenResponse) => {
      setLoading(true)
      setLoginError(null)
      try {
        const res = await api.post('/auth/google', {
          access_token: tokenResponse.access_token,
        })
        setUser(res.data.user, res.data.access_token)
        navigate('/dashboard')
      } catch (err: any) {
        const detail = err.response?.data?.detail
        setLoginError(typeof detail === 'string' ? detail : 'Login failed. Please try again.')
      } finally {
        setLoading(false)
      }
    },
    onError: () => setLoginError('Google sign-in was cancelled or failed. Please try again.'),
  })

  if (user) {
    navigate('/dashboard')
    return null
  }

  const active = USE_CASES[activeCase]

  return (
    <div className="min-h-screen bg-background text-foreground flex flex-col">
      {/* Navbar */}
      <header className="border-b border-border/50 backdrop-blur-sm sticky top-0 z-50 bg-background/80">
        <div className="max-w-6xl mx-auto px-6 h-14 flex items-center justify-between">
          <div className="flex items-center gap-2.5">
            <div className="w-7 h-7 bg-primary rounded-lg flex items-center justify-center">
              <FileSpreadsheet size={14} className="text-white" />
            </div>
            <span className="font-semibold text-sm tracking-tight">PDF to Excel</span>
          </div>
          <div className="flex items-center gap-3">
            <a href="mailto:contact@pdfexcel.ai" className="text-xs text-muted-foreground hover:text-foreground transition-colors hidden sm:block">
              Enterprise
            </a>
            <Button
              variant="outline"
              size="sm"
              onClick={() => googleLogin()}
              disabled={loading}
            >
              {loading ? (
                <span className="flex items-center gap-2">
                  <div className="w-3.5 h-3.5 border-2 border-border border-t-foreground rounded-full animate-spin" />
                  Signing in…
                </span>
              ) : (
                <>Sign in <ArrowRight size={13} /></>
              )}
            </Button>
          </div>
        </div>
      </header>

      {/* Hero */}
      <section className="flex-1 flex flex-col items-center justify-center px-6 py-20 text-center relative overflow-hidden">
        {/* Background glows */}
        <div className="absolute inset-0 flex items-center justify-center pointer-events-none">
          <div className="w-[700px] h-[500px] bg-primary/5 rounded-full blur-3xl" />
        </div>
        <div className="absolute top-0 right-0 w-[400px] h-[300px] bg-blue-200/20 rounded-full blur-3xl pointer-events-none" />
        <div className="absolute bottom-0 left-0 w-[300px] h-[300px] bg-violet-200/10 rounded-full blur-3xl pointer-events-none" />

        <div className="relative max-w-3xl mx-auto">
          <Badge variant="outline" className="mb-6 gap-1.5 px-3 py-1 text-xs font-medium">
            <span className="w-1.5 h-1.5 rounded-full bg-emerald-500 inline-block" />
            Powered by GPT-4.1 · 94%+ accuracy
          </Badge>

          <h1 className="text-5xl sm:text-6xl font-bold tracking-tight mb-6 leading-[1.1]">
            Turn any PDF into{' '}
            <span className="text-primary">structured data</span>
            <br />
            <span className="text-muted-foreground text-4xl sm:text-5xl font-semibold">in seconds</span>
          </h1>

          <p className="text-muted-foreground text-lg mb-10 max-w-2xl mx-auto leading-relaxed">
            Upload a PDF, define the fields you need, and get a perfectly formatted Excel spreadsheet.
            Works on invoices, financial reports, insurance forms, contracts, and more.
          </p>

          <div className="flex flex-col items-center gap-3">
            <Button
              size="xl"
              onClick={() => googleLogin()}
              disabled={loading}
              className="gap-3 shadow-lg shadow-primary/20 min-w-[240px]"
            >
              {loading ? (
                <div className="w-4 h-4 border-2 border-primary-foreground/30 border-t-white rounded-full animate-spin" />
              ) : (
                <svg className="w-4 h-4" viewBox="0 0 24 24">
                  <path d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92c-.26 1.37-1.04 2.53-2.21 3.31v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.09z" fill="#4285F4"/>
                  <path d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z" fill="#34A853"/>
                  <path d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.07H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.93l2.85-2.22.81-.62z" fill="#FBBC05"/>
                  <path d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.07l3.66 2.84c.87-2.6 3.3-4.53 6.16-4.53z" fill="#EA4335"/>
                </svg>
              )}
              Start free with Google
            </Button>
            {loginError && (
              <p className="text-sm text-red-500 bg-red-50 border border-red-200 rounded-lg px-4 py-2 max-w-sm text-center">
                {loginError}
              </p>
            )}
            <p className="text-xs text-muted-foreground">No credit card required · Pay per use</p>
          </div>
        </div>
      </section>

      {/* Stats strip */}
      <section className="border-y border-border/50 bg-card/50 py-8 px-6">
        <div className="max-w-4xl mx-auto grid grid-cols-2 sm:grid-cols-4 gap-6">
          {STATS.map((s) => (
            <div key={s.label} className="text-center">
              <div className="text-2xl font-bold text-primary mb-1">{s.value}</div>
              <div className="text-xs text-muted-foreground">{s.label}</div>
            </div>
          ))}
        </div>
      </section>

      {/* Use Cases */}
      <section className="py-20 px-6">
        <div className="max-w-5xl mx-auto">
          <p className="text-center text-xs font-semibold uppercase tracking-widest text-muted-foreground mb-3">
            Use cases
          </p>
          <h2 className="text-2xl sm:text-3xl font-bold text-center tracking-tight mb-12">
            Works on every document type
          </h2>

          <div className="grid lg:grid-cols-2 gap-6 items-start">
            {/* Left: case selector */}
            <div className="space-y-2">
              {USE_CASES.map((c, i) => (
                <button
                  key={c.label}
                  onClick={() => setActiveCase(i)}
                  className={`w-full text-left rounded-xl p-4 border transition-all flex items-center gap-3 ${
                    activeCase === i
                      ? 'border-primary/40 bg-primary/5 shadow-sm'
                      : 'border-border/50 hover:border-border hover:bg-card/50'
                  }`}
                >
                  <div className={`w-9 h-9 rounded-lg flex items-center justify-center flex-shrink-0 ${c.color}`}>
                    <c.icon size={17} />
                  </div>
                  <div className="flex-1 min-w-0">
                    <div className="font-medium text-sm">{c.label}</div>
                    <div className="text-xs text-muted-foreground truncate">{c.example}</div>
                  </div>
                  {activeCase === i && <ChevronRight size={14} className="text-primary flex-shrink-0" />}
                </button>
              ))}
            </div>

            {/* Right: preview card */}
            <div className="sticky top-20">
              <Card className="overflow-hidden border-border/60 shadow-lg">
                <div className="bg-muted/30 border-b border-border/50 px-5 py-3 flex items-center gap-2">
                  <div className={`w-7 h-7 rounded-lg flex items-center justify-center ${active.color}`}>
                    <active.icon size={14} />
                  </div>
                  <span className="text-sm font-semibold">{active.label}</span>
                  <Badge variant="outline" className="ml-auto text-[10px] px-2 py-0">Excel output</Badge>
                </div>
                <CardContent className="p-5">
                  <p className="text-sm text-muted-foreground mb-5 leading-relaxed">{active.example}</p>
                  <div className="space-y-2">
                    <p className="text-xs font-semibold text-muted-foreground uppercase tracking-wider mb-3">Extracted fields</p>
                    {active.fields.map((f) => (
                      <div key={f} className="flex items-center gap-2.5 text-sm">
                        <CheckCircle2 size={14} className="text-emerald-500 flex-shrink-0" />
                        <span>{f}</span>
                      </div>
                    ))}
                  </div>
                  <div className="mt-5 pt-4 border-t border-border/50">
                    <div className="flex items-center justify-between text-xs">
                      <span className="text-muted-foreground">+ any custom fields you define</span>
                      <Button size="sm" variant="ghost" className="h-7 text-xs gap-1 text-primary" onClick={() => googleLogin()}>
                        Try it <ArrowRight size={11} />
                      </Button>
                    </div>
                  </div>
                </CardContent>
              </Card>
            </div>
          </div>
        </div>
      </section>

      {/* Features */}
      <section className="py-16 px-6 border-t border-border/50 bg-card/30">
        <div className="max-w-4xl mx-auto">
          <p className="text-center text-xs font-semibold uppercase tracking-widest text-muted-foreground mb-10">
            Why PDF to Excel
          </p>
          <div className="grid sm:grid-cols-3 gap-5">
            {FEATURES.map((f) => (
              <div
                key={f.title}
                className="bg-card border border-border rounded-xl p-5 hover:border-primary/30 hover:shadow-sm transition-all"
              >
                <div className="w-9 h-9 bg-primary/10 rounded-lg flex items-center justify-center mb-4">
                  <f.icon size={17} className="text-primary" />
                </div>
                <h3 className="font-semibold text-sm mb-1.5">{f.title}</h3>
                <p className="text-muted-foreground text-xs leading-relaxed">{f.desc}</p>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* Custom Deployments */}
      <section className="py-20 px-6 border-t border-border/50">
        <div className="max-w-4xl mx-auto text-center">
          <p className="text-xs font-semibold uppercase tracking-widest text-muted-foreground mb-3">
            Custom deployments
          </p>
          <h2 className="text-2xl sm:text-3xl font-bold tracking-tight mb-4">
            Your data. Your infrastructure.
          </h2>
          <p className="text-muted-foreground text-sm mb-12 max-w-lg mx-auto leading-relaxed">
            Need a private deployment with custom extraction rules and compliance requirements?
            We build dedicated pipelines for enterprise teams.
          </p>

          <div className="grid sm:grid-cols-3 gap-5 mb-10">
            {DEPLOYMENTS.map((d) => (
              <div
                key={d.title}
                className="bg-card border border-border rounded-xl p-5 hover:border-primary/30 hover:shadow-sm transition-all text-left"
              >
                <div className="w-9 h-9 bg-primary/10 rounded-lg flex items-center justify-center mb-4">
                  <d.icon size={17} className="text-primary" />
                </div>
                <h3 className="font-semibold text-sm mb-1.5">{d.title}</h3>
                <p className="text-muted-foreground text-xs leading-relaxed">{d.desc}</p>
              </div>
            ))}
          </div>

          <Button variant="outline" size="sm" className="gap-2" asChild>
            <a href="mailto:contact@pdfexcel.ai">
              <Mail size={14} />
              Contact us for enterprise pricing
            </a>
          </Button>
        </div>
      </section>

      {/* CTA banner */}
      <section className="py-16 px-6 border-t border-border/50 bg-primary/5">
        <div className="max-w-2xl mx-auto text-center">
          <h2 className="text-2xl font-bold tracking-tight mb-4">Ready to automate your data extraction?</h2>
          <p className="text-muted-foreground text-sm mb-8">
            Sign in with Google and upload your first PDF — no setup required.
          </p>
          <Button
            size="xl"
            onClick={() => googleLogin()}
            disabled={loading}
            className="gap-3 shadow-lg shadow-primary/20 min-w-[220px]"
          >
            {loading ? (
              <div className="w-4 h-4 border-2 border-primary-foreground/30 border-t-white rounded-full animate-spin" />
            ) : (
              <>
                <svg className="w-4 h-4" viewBox="0 0 24 24">
                  <path d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92c-.26 1.37-1.04 2.53-2.21 3.31v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.09z" fill="#4285F4"/>
                  <path d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z" fill="#34A853"/>
                  <path d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.07H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.93l2.85-2.22.81-.62z" fill="#FBBC05"/>
                  <path d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.07l3.66 2.84c.87-2.6 3.3-4.53 6.16-4.53z" fill="#EA4335"/>
                </svg>
                Get started free
              </>
            )}
          </Button>
        </div>
      </section>

      {/* Footer */}
      <footer className="border-t border-border/50 py-6 px-6">
        <div className="max-w-6xl mx-auto flex flex-col sm:flex-row items-center justify-between gap-3 text-xs text-muted-foreground">
          <div className="flex items-center gap-2">
            <div className="w-5 h-5 bg-primary rounded-md flex items-center justify-center">
              <FileSpreadsheet size={11} className="text-white" />
            </div>
            PDF to Excel
          </div>
          <div className="flex items-center gap-4">
            <a href="/privacy" className="hover:text-foreground transition-colors">Privacy Policy</a>
            <a href="mailto:contact@pdfexcel.ai" className="hover:text-foreground transition-colors">Contact</a>
            <span>© 2026 PDF to Excel. All rights reserved.</span>
          </div>
        </div>
      </footer>
    </div>
  )
}
