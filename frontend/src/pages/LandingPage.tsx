import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useGoogleLogin } from '@react-oauth/google'
import {
  FileSpreadsheet, Zap, Shield, ArrowRight, Clock,
  Building2, GitBranch, Lock, Mail,
  Receipt, BarChart3, FileText, ShoppingCart, TrendingUp, ClipboardList,
  CheckCircle2, ChevronRight, ChevronDown,
  Upload, MousePointerClick, Download, Eye,
  ShieldCheck, Trash2, ServerCrash, KeyRound,
  HelpCircle,
} from 'lucide-react'
import api from '@/lib/api'
import { useAuthStore } from '@/store/authStore'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { Card, CardContent } from '@/components/ui/card'

/* ─── Feature cards ─────────────────────────────────────────────────────────── */
const FEATURES = [
  {
    icon: Zap,
    title: 'AI That Reads Like a Human',
    desc: 'Our AI understands tables, headers, footers, and irregular layouts — even when every PDF looks different. No templates or setup required.',
  },
  {
    icon: FileSpreadsheet,
    title: 'Clean, Organized Spreadsheets',
    desc: 'You get a ready-to-use Excel or CSV file with your chosen fields in neat columns — one row per document. No reformatting needed.',
  },
  {
    icon: Shield,
    title: 'Tested on Real Documents',
    desc: '94%+ field accuracy across thousands of real invoices, reports, and forms. Built for messy, imperfect documents — not just clean samples.',
  },
  {
    icon: Clock,
    title: 'Results in Under 30 Seconds',
    desc: 'Upload your files and get structured data back in seconds. Process dozens of documents in the time it takes to manually copy one.',
  },
]

/* ─── How it works steps ────────────────────────────────────────────────────── */
const HOW_IT_WORKS = [
  {
    icon: Upload,
    step: '1',
    title: 'Upload Your PDFs',
    desc: 'Drag and drop one or more PDF files. Works with scanned documents, digital PDFs, and even photos of documents (PNG, JPEG).',
  },
  {
    icon: MousePointerClick,
    step: '2',
    title: 'Choose What to Extract',
    desc: 'Pick from common fields like "Invoice Number," "Total Amount," or "Date" — or type in any custom field you need. Add descriptions to guide the AI for tricky fields.',
  },
  {
    icon: Download,
    step: '3',
    title: 'Get Your Spreadsheet',
    desc: 'In seconds, your data is extracted and delivered as a clean Excel or CSV file. One row per document, one column per field. Download it instantly.',
  },
]

/* ─── Use cases ──────────────────────────────────────────────────────────────── */
const USE_CASES = [
  {
    icon: Receipt,
    label: 'Invoices & Bills',
    color: 'bg-blue-500/10 text-blue-600',
    example: 'Stop manually copying invoice details into spreadsheets. Upload a stack of invoices and extract vendor names, invoice numbers, line items, totals, tax amounts, and due dates — all at once, from any format.',
    fields: ['Invoice Number', 'Vendor Name', 'Total Amount', 'Tax Amount', 'Due Date', 'Line Items'],
  },
  {
    icon: BarChart3,
    label: 'Financial Reports',
    color: 'bg-violet-500/10 text-violet-600',
    example: 'Pull key financial metrics from annual reports, 10-Ks, and quarterly filings. Compare revenue, net income, total assets, and equity across multiple companies — without reading hundreds of pages.',
    fields: ['Total Revenue', 'Net Income', 'Total Assets', 'Shareholders Equity', 'Report Period'],
  },
  {
    icon: FileText,
    label: 'Insurance EOBs',
    color: 'bg-emerald-500/10 text-emerald-600',
    example: 'Turn Explanation of Benefits forms into structured data. Extract patient info, service dates, billed amounts, plan payments, and patient responsibility from any insurance provider format.',
    fields: ['Patient Name', 'Service Date', 'Billed Amount', 'Plan Paid', 'Patient Responsibility'],
  },
  {
    icon: ShoppingCart,
    label: 'Purchase Orders',
    color: 'bg-orange-500/10 text-orange-600',
    example: 'Digitize purchase orders from any supplier. Capture PO numbers, supplier details, item descriptions, quantities, unit prices, and order totals into one organized spreadsheet.',
    fields: ['PO Number', 'Supplier Name', 'Item Description', 'Quantity', 'Unit Price', 'Order Total'],
  },
  {
    icon: TrendingUp,
    label: 'Annual Reports',
    color: 'bg-pink-500/10 text-pink-600',
    example: 'Benchmark across companies by extracting consistent metrics from annual reports. Build comparison spreadsheets with operating income, equity, headcount, and more — from any report layout.',
    fields: ['Company Name', 'Report Year', 'Operating Income', 'Total Equity', 'Employees'],
  },
  {
    icon: ClipboardList,
    label: 'Contracts & Legal',
    color: 'bg-teal-500/10 text-teal-600',
    example: 'Extract key terms from contracts, agreements, and legal forms. Pull party names, effective dates, contract values, renewal terms, and expiry dates into a single spreadsheet for easy review.',
    fields: ['Party Names', 'Effective Date', 'Contract Value', 'Renewal Terms', 'Expiry Date'],
  },
]

/* ─── Stats ──────────────────────────────────────────────────────────────────── */
const STATS = [
  { value: '94%+', label: 'Field extraction accuracy' },
  { value: '< 30s', label: 'Average processing time' },
  { value: 'Any PDF', label: 'Scanned, digital, or photo' },
  { value: 'Zero storage', label: 'Files deleted after processing' },
]

/* ─── Security features ──────────────────────────────────────────────────────── */
const SECURITY_FEATURES = [
  {
    icon: Lock,
    title: 'Encrypted in Transit',
    desc: 'All file uploads and downloads are protected with TLS/HTTPS encryption. Your documents are never transmitted in plain text.',
  },
  {
    icon: Trash2,
    title: 'Files Deleted After Processing',
    desc: 'Your documents are processed in memory and permanently deleted as soon as extraction is complete. We do not store your files on our servers.',
  },
  {
    icon: Eye,
    title: 'No Human Access',
    desc: 'Your documents are processed entirely by AI. No person ever views, reads, or accesses your uploaded files.',
  },
  {
    icon: ServerCrash,
    title: 'Not Used to Train AI',
    desc: 'Your documents and extracted data are never used to train, fine-tune, or improve any AI model. Your data stays yours.',
  },
  {
    icon: KeyRound,
    title: 'No Third-Party Sharing',
    desc: 'We never sell, share, or provide your documents or data to any third party. Period.',
  },
  {
    icon: ShieldCheck,
    title: 'You Control Your Data',
    desc: 'Request complete deletion of your account and all associated data at any time. We process deletion requests within 30 days.',
  },
]

/* ─── Enterprise cards ───────────────────────────────────────────────────────── */
const DEPLOYMENTS = [
  {
    icon: Building2,
    title: 'Private Infrastructure',
    desc: 'Run entirely within your VPC or on-premise environment. No data ever leaves your network.',
  },
  {
    icon: GitBranch,
    title: 'Custom Extraction Pipelines',
    desc: 'Extraction rules tailored to your specific document types, field definitions, and validation requirements.',
  },
  {
    icon: Lock,
    title: 'Compliance Ready',
    desc: 'Meet your organization\'s security and compliance requirements with dedicated infrastructure and data isolation.',
  },
]

/* ─── FAQ ─────────────────────────────────────────────────────────────────────── */
const FAQ_ITEMS = [
  {
    q: 'What types of PDFs does this work on?',
    a: 'It works on virtually any PDF — invoices, financial reports, insurance forms, contracts, purchase orders, annual reports, and more. It handles both digital PDFs (text-based) and scanned documents (image-based) using built-in OCR. Even photos of documents (PNG, JPEG) are supported.',
  },
  {
    q: 'What if my PDFs are messy, scanned, or inconsistently formatted?',
    a: 'That\'s exactly what this tool is built for. Unlike simple PDF converters that break on irregular layouts, our AI reads and understands the content of your documents — even when tables are misaligned, fonts vary, or the scan quality is poor. You\'ll still get structured, usable output.',
  },
  {
    q: 'What does the output look like?',
    a: 'You get a clean Excel (.xlsx) or CSV file. Each row represents one document. Each column represents one of the fields you chose to extract (like "Invoice Number" or "Total Amount"). It\'s ready to use — no reformatting needed.',
  },
  {
    q: 'Can I extract any field I want, or only preset ones?',
    a: 'Both. We offer common presets (Invoice Number, Date, Total Amount, etc.) and you can type in any custom field. You can also add a description to guide the AI — for example, "Net Income ÷ Revenue × 100" for a profit margin calculation.',
  },
  {
    q: 'How accurate is the extraction?',
    a: 'We achieve 94%+ field accuracy across thousands of real-world documents. Accuracy depends on document quality — clear, high-resolution PDFs produce the best results. For scanned or low-quality documents, results are still strong but we recommend reviewing the output.',
  },
  {
    q: 'How much does it cost?',
    a: 'You pay per extraction — no monthly subscription, no commitment. Add funds to your account balance ($5, $10, $20, or any custom amount) and it depletes as you process documents. Your balance never expires.',
  },
  {
    q: 'Are my files secure? Who can see my documents?',
    a: 'Your files are encrypted during upload, processed in memory by AI only (no human ever sees them), and permanently deleted as soon as extraction is complete. We do not store your documents, and they are never used to train AI models or shared with anyone.',
  },
  {
    q: 'Is this safe for sensitive documents like invoices, contracts, or financial statements?',
    a: 'Yes. Documents are encrypted in transit, processed in isolated memory, and deleted immediately after extraction. No human accesses your files, and your data is never stored, shared, or used for AI training. For organizations with strict compliance needs, we offer private deployments.',
  },
  {
    q: 'How is this different from a regular PDF-to-Excel converter?',
    a: 'Regular converters just try to replicate the visual layout of a PDF in a spreadsheet — you get messy tables, merged cells, and broken formatting. This tool actually reads and understands your documents. You tell it what data you need, and it extracts exactly those fields into a clean, structured spreadsheet.',
  },
  {
    q: 'Can I process multiple documents at once?',
    a: 'Yes. Upload as many files as you need in a single batch. Each document becomes one row in your output spreadsheet, with all your chosen fields filled in. This is ideal for processing stacks of invoices, reports, or forms.',
  },
]

/* ═══════════════════════════════════════════════════════════════════════════════ */
export default function LandingPage() {
  const navigate = useNavigate()
  const { setUser, user } = useAuthStore()
  const [loading, setLoading] = useState(false)
  const [loginError, setLoginError] = useState<string | null>(null)
  const [activeCase, setActiveCase] = useState(0)
  const [openFaq, setOpenFaq] = useState<number | null>(null)

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

  const GoogleIcon = () => (
    <svg className="w-4 h-4" viewBox="0 0 24 24">
      <path d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92c-.26 1.37-1.04 2.53-2.21 3.31v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.09z" fill="#4285F4"/>
      <path d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z" fill="#34A853"/>
      <path d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.07H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.93l2.85-2.22.81-.62z" fill="#FBBC05"/>
      <path d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.07l3.66 2.84c.87-2.6 3.3-4.53 6.16-4.53z" fill="#EA4335"/>
    </svg>
  )

  const SignInButton = ({ size = 'xl' as const, label = 'Get started free', className = '' }) => (
    <Button
      size={size}
      onClick={() => googleLogin()}
      disabled={loading}
      className={`gap-3 shadow-lg shadow-primary/20 ${className}`}
    >
      {loading ? (
        <div className="w-4 h-4 border-2 border-primary-foreground/30 border-t-white rounded-full animate-spin" />
      ) : (
        <>
          <GoogleIcon />
          {label}
        </>
      )}
    </Button>
  )

  return (
    <div className="min-h-screen bg-background text-foreground flex flex-col">
      {/* ── Navbar ─────────────────────────────────────────────────────────── */}
      <header className="border-b border-border/50 backdrop-blur-sm sticky top-0 z-50 bg-background/80">
        <div className="max-w-6xl mx-auto px-4 sm:px-6 h-14 flex items-center justify-between">
          <div className="flex items-center gap-2.5">
            <div className="w-7 h-7 bg-primary rounded-lg flex items-center justify-center">
              <FileSpreadsheet size={14} className="text-white" />
            </div>
            <span className="font-semibold text-sm tracking-tight">PDF to Excel</span>
          </div>
          <div className="flex items-center gap-4">
            <a href="#how-it-works" className="text-xs text-muted-foreground hover:text-foreground transition-colors hidden sm:block">
              How It Works
            </a>
            <a href="#use-cases" className="text-xs text-muted-foreground hover:text-foreground transition-colors hidden sm:block">
              Use Cases
            </a>
            <a href="#security" className="text-xs text-muted-foreground hover:text-foreground transition-colors hidden sm:block">
              Security
            </a>
            <a href="#faq" className="text-xs text-muted-foreground hover:text-foreground transition-colors hidden sm:block">
              FAQ
            </a>
            <a href="mailto:contact@pdfexcel.ai" className="text-xs text-muted-foreground hover:text-foreground transition-colors hidden md:block">
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

      {/* ── Hero ──────────────────────────────────────────────────────────── */}
      <section className="flex-1 flex flex-col items-center justify-center px-4 sm:px-6 py-12 sm:py-20 text-center relative overflow-hidden">
        <div className="absolute inset-0 flex items-center justify-center pointer-events-none">
          <div className="w-[700px] h-[500px] bg-primary/5 rounded-full blur-3xl" />
        </div>
        <div className="absolute top-0 right-0 w-[400px] h-[300px] bg-blue-200/20 rounded-full blur-3xl pointer-events-none" />
        <div className="absolute bottom-0 left-0 w-[300px] h-[300px] bg-violet-200/10 rounded-full blur-3xl pointer-events-none" />

        <div className="relative max-w-3xl mx-auto">
          <Badge variant="outline" className="mb-6 gap-1.5 px-3 py-1 text-xs font-medium">
            <Lock size={10} />
            Your files are encrypted and deleted after processing
          </Badge>

          <h1 className="text-3xl sm:text-5xl md:text-6xl font-bold tracking-tight mb-6 leading-[1.1]">
            Extract data from any PDF{' '}
            <br className="hidden sm:block" />
            <span className="text-primary">into a clean spreadsheet</span>
          </h1>

          <p className="text-muted-foreground text-base sm:text-lg mb-4 max-w-2xl mx-auto leading-relaxed">
            Upload your PDFs, tell it what data you need, and get a structured Excel file in seconds.
            Works on invoices, financial reports, insurance forms, contracts, and more —
            even messy, scanned, or inconsistently formatted documents.
          </p>

          <p className="text-muted-foreground text-sm mb-10 max-w-xl mx-auto">
            No templates. No manual reformatting. Just the fields you need, organized in rows and columns.
          </p>

          <div className="flex flex-col items-center gap-3">
            <SignInButton label="Start extracting — it's free" className="min-w-0 sm:min-w-[280px] w-full sm:w-auto" />
            {loginError && (
              <p className="text-sm text-red-500 bg-red-50 border border-red-200 rounded-lg px-4 py-2 max-w-sm text-center">
                {loginError}
              </p>
            )}
            <p className="text-xs text-muted-foreground">
              No credit card required · Pay only when you extract · Files deleted after processing
            </p>
          </div>
        </div>
      </section>

      {/* ── Stats strip ───────────────────────────────────────────────────── */}
      <section className="border-y border-border/50 bg-card/50 py-6 sm:py-8 px-4 sm:px-6">
        <div className="max-w-4xl mx-auto grid grid-cols-2 sm:grid-cols-4 gap-6">
          {STATS.map((s) => (
            <div key={s.label} className="text-center">
              <div className="text-2xl font-bold text-primary mb-1">{s.value}</div>
              <div className="text-xs text-muted-foreground">{s.label}</div>
            </div>
          ))}
        </div>
      </section>

      {/* ── How It Works ──────────────────────────────────────────────────── */}
      <section id="how-it-works" className="py-12 sm:py-20 px-4 sm:px-6 scroll-mt-16">
        <div className="max-w-4xl mx-auto">
          <p className="text-center text-xs font-semibold uppercase tracking-widest text-muted-foreground mb-3">
            How it works
          </p>
          <h2 className="text-2xl sm:text-3xl font-bold text-center tracking-tight mb-4">
            Three steps. No learning curve.
          </h2>
          <p className="text-center text-muted-foreground text-sm mb-12 max-w-lg mx-auto">
            You don't need to configure anything, create templates, or learn new software.
            Just upload, pick your fields, and download.
          </p>

          <div className="grid sm:grid-cols-3 gap-6">
            {HOW_IT_WORKS.map((step) => (
              <div
                key={step.step}
                className="bg-card border border-border rounded-xl p-6 hover:border-primary/30 hover:shadow-sm transition-all relative"
              >
                <div className="flex items-center gap-3 mb-4">
                  <div className="w-9 h-9 bg-primary/10 rounded-lg flex items-center justify-center">
                    <step.icon size={17} className="text-primary" />
                  </div>
                  <span className="text-xs font-bold text-primary/60 uppercase tracking-wider">Step {step.step}</span>
                </div>
                <h3 className="font-semibold text-sm mb-2">{step.title}</h3>
                <p className="text-muted-foreground text-xs leading-relaxed">{step.desc}</p>
              </div>
            ))}
          </div>

          <div className="text-center mt-10">
            <SignInButton size="xl" label="Try it now — upload your first PDF" className="min-w-0 sm:min-w-[300px] w-full sm:w-auto" />
          </div>
        </div>
      </section>

      {/* ── Use Cases ─────────────────────────────────────────────────────── */}
      <section id="use-cases" className="py-12 sm:py-20 px-4 sm:px-6 border-t border-border/50 bg-card/30 scroll-mt-16">
        <div className="max-w-5xl mx-auto">
          <p className="text-center text-xs font-semibold uppercase tracking-widest text-muted-foreground mb-3">
            Use cases
          </p>
          <h2 className="text-2xl sm:text-3xl font-bold text-center tracking-tight mb-4">
            Built for the documents you actually work with
          </h2>
          <p className="text-center text-muted-foreground text-sm mb-12 max-w-lg mx-auto">
            Whether you're processing 5 invoices or 500 annual reports, the tool adapts to your document type
            and extracts exactly the fields you need.
          </p>

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
                    <div className="text-xs text-muted-foreground line-clamp-2">{c.example}</div>
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
                  <Badge variant="outline" className="ml-auto text-[10px] px-2 py-0">Excel output preview</Badge>
                </div>
                <CardContent className="p-5">
                  <p className="text-sm text-muted-foreground mb-5 leading-relaxed">{active.example}</p>
                  <div className="space-y-2">
                    <p className="text-xs font-semibold text-muted-foreground uppercase tracking-wider mb-3">Fields you can extract</p>
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

      {/* ── Why This Tool / Features ──────────────────────────────────────── */}
      <section className="py-12 sm:py-20 px-4 sm:px-6 border-t border-border/50 scroll-mt-16">
        <div className="max-w-4xl mx-auto">
          <p className="text-center text-xs font-semibold uppercase tracking-widest text-muted-foreground mb-3">
            Why PDF to Excel
          </p>
          <h2 className="text-2xl sm:text-3xl font-bold text-center tracking-tight mb-4">
            Not a generic PDF converter
          </h2>
          <p className="text-center text-muted-foreground text-sm mb-12 max-w-lg mx-auto">
            Regular converters try to replicate a PDF's layout in Excel — giving you broken tables and merged cells.
            This tool reads your documents, understands the content, and extracts exactly the fields you ask for.
          </p>
          <div className="grid sm:grid-cols-2 gap-5">
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

      {/* ── Security & Privacy ────────────────────────────────────────────── */}
      <section id="security" className="py-12 sm:py-20 px-4 sm:px-6 border-t border-border/50 bg-card/30 scroll-mt-16">
        <div className="max-w-4xl mx-auto">
          <p className="text-center text-xs font-semibold uppercase tracking-widest text-muted-foreground mb-3">
            Security & Privacy
          </p>
          <h2 className="text-2xl sm:text-3xl font-bold text-center tracking-tight mb-4">
            Your documents are private and protected
          </h2>
          <p className="text-center text-muted-foreground text-sm mb-12 max-w-lg mx-auto">
            We know you're uploading sensitive documents. That's why we built this platform with
            privacy-first principles — your files are encrypted, processed in isolation, and permanently deleted after extraction.
          </p>

          <div className="grid sm:grid-cols-2 lg:grid-cols-3 gap-5">
            {SECURITY_FEATURES.map((f) => (
              <div
                key={f.title}
                className="bg-card border border-border rounded-xl p-5 hover:border-primary/30 hover:shadow-sm transition-all"
              >
                <div className="w-9 h-9 bg-emerald-500/10 rounded-lg flex items-center justify-center mb-4">
                  <f.icon size={17} className="text-emerald-600" />
                </div>
                <h3 className="font-semibold text-sm mb-1.5">{f.title}</h3>
                <p className="text-muted-foreground text-xs leading-relaxed">{f.desc}</p>
              </div>
            ))}
          </div>

          <div className="mt-10 text-center">
            <a href="/privacy" className="text-xs text-primary hover:underline">
              Read our full Privacy Policy →
            </a>
          </div>
        </div>
      </section>

      {/* ── FAQ ───────────────────────────────────────────────────────────── */}
      <section id="faq" className="py-12 sm:py-20 px-4 sm:px-6 border-t border-border/50 scroll-mt-16">
        <div className="max-w-3xl mx-auto">
          <p className="text-center text-xs font-semibold uppercase tracking-widest text-muted-foreground mb-3">
            Frequently asked questions
          </p>
          <h2 className="text-2xl sm:text-3xl font-bold text-center tracking-tight mb-12">
            Everything you need to know
          </h2>

          <div className="space-y-2">
            {FAQ_ITEMS.map((item, i) => (
              <div
                key={i}
                className="border border-border rounded-xl overflow-hidden bg-card"
              >
                <button
                  onClick={() => setOpenFaq(openFaq === i ? null : i)}
                  className="w-full flex items-center justify-between p-4 text-left hover:bg-muted/30 transition-colors"
                >
                  <span className="text-sm font-medium pr-4 flex items-center gap-2.5">
                    <HelpCircle size={14} className="text-primary flex-shrink-0" />
                    {item.q}
                  </span>
                  <ChevronDown
                    size={14}
                    className={`text-muted-foreground flex-shrink-0 transition-transform ${
                      openFaq === i ? 'rotate-180' : ''
                    }`}
                  />
                </button>
                {openFaq === i && (
                  <div className="px-4 pb-4 pt-0">
                    <p className="text-sm text-muted-foreground leading-relaxed pl-[26px]">
                      {item.a}
                    </p>
                  </div>
                )}
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* ── Enterprise Deployments ────────────────────────────────────────── */}
      <section className="py-12 sm:py-20 px-4 sm:px-6 border-t border-border/50 bg-card/30">
        <div className="max-w-4xl mx-auto text-center">
          <p className="text-xs font-semibold uppercase tracking-widest text-muted-foreground mb-3">
            Enterprise
          </p>
          <h2 className="text-2xl sm:text-3xl font-bold tracking-tight mb-4">
            Need a private deployment?
          </h2>
          <p className="text-muted-foreground text-sm mb-12 max-w-lg mx-auto leading-relaxed">
            For teams with strict compliance, security, or volume requirements — we build
            dedicated extraction pipelines on your own infrastructure. Your data never leaves your network.
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

      {/* ── CTA banner ────────────────────────────────────────────────────── */}
      <section className="py-12 sm:py-16 px-4 sm:px-6 border-t border-border/50 bg-primary/5">
        <div className="max-w-2xl mx-auto text-center">
          <h2 className="text-2xl font-bold tracking-tight mb-3">
            Stop copying data from PDFs by hand
          </h2>
          <p className="text-muted-foreground text-sm mb-3">
            Upload your first PDF and see structured results in seconds. No credit card, no setup, no commitment.
          </p>
          <p className="text-muted-foreground text-xs mb-8 flex items-center justify-center gap-1.5">
            <Lock size={10} />
            Your files are encrypted and deleted after processing
          </p>
          <SignInButton label="Get started free" className="min-w-0 sm:min-w-[220px] w-full sm:w-auto" />
        </div>
      </section>

      {/* ── Footer ────────────────────────────────────────────────────────── */}
      <footer className="border-t border-border/50 py-6 px-4 sm:px-6">
        <div className="max-w-6xl mx-auto flex flex-col items-center gap-3 text-xs text-muted-foreground">
          <div className="flex items-center gap-2">
            <div className="w-5 h-5 bg-primary rounded-md flex items-center justify-center">
              <FileSpreadsheet size={11} className="text-white" />
            </div>
            PDF to Excel
          </div>
          <div className="flex flex-wrap items-center justify-center gap-x-4 gap-y-1">
            <a href="/privacy" className="hover:text-foreground transition-colors">Privacy Policy</a>
            <a href="#security" className="hover:text-foreground transition-colors">Security</a>
            <a href="#faq" className="hover:text-foreground transition-colors">FAQ</a>
            <a href="mailto:contact@pdfexcel.ai" className="hover:text-foreground transition-colors">Contact</a>
          </div>
          <span>© 2026 PDF to Excel. All rights reserved.</span>
        </div>
      </footer>
    </div>
  )
}
