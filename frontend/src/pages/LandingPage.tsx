import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useGoogleLogin } from '@react-oauth/google'
import {
  FileSpreadsheet, ArrowRight,
  Building2, GitBranch, Lock, Mail,
  Receipt, BarChart3, FileText, ShoppingCart, TrendingUp, ClipboardList,
  CheckCircle2, ChevronRight, ChevronDown,
  Upload, MousePointerClick, Download, Eye,
  ShieldCheck, Trash2, ServerCrash, KeyRound,
  HelpCircle, Star, DollarSign, Brain, Cpu, Target, FlaskConical,
} from 'lucide-react'
import { trackEvent } from '@/lib/analytics'
import api from '@/lib/api'
import { useAuthStore } from '@/store/authStore'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { Card, CardContent } from '@/components/ui/card'

/* ─── Feature cards (Purpose-built AI) ──────────────────────────────────────── */
const FEATURES = [
  {
    icon: Brain,
    title: 'Purpose-Built Extraction Models',
    desc: 'Unlike generic AI wrappers, our models are specifically trained for structured data extraction from financial documents, invoices, and forms. This isn\'t ChatGPT with a PDF plugin — it\'s a dedicated extraction engine.',
  },
  {
    icon: Target,
    title: '94%+ Accuracy on Real Documents',
    desc: 'Tested across thousands of real-world invoices, SEC filings, insurance forms, and scanned receipts — not just clean samples. Our models are fine-tuned on messy, inconsistent, real-world data.',
  },
  {
    icon: FlaskConical,
    title: 'Trained on Document Structure',
    desc: 'Our AI understands table boundaries, multi-page layouts, merged cells, headers vs. data rows, and footnotes. It doesn\'t just OCR text — it comprehends document architecture.',
  },
  {
    icon: Cpu,
    title: 'Enterprise-Grade Pipeline',
    desc: 'Multi-stage processing: intelligent OCR → layout analysis → field extraction → validation. Each stage is purpose-built, not a single generic prompt sent to a chatbot.',
  },
]

/* ─── Testimonials ─────────────────────────────────────────────────────────── */
const TESTIMONIALS = [
  {
    name: 'Sarah Chen',
    role: 'Financial Analyst',
    company: 'Meridian Capital',
    text: 'We were manually pulling data from 200+ SEC filings per quarter. Now we upload the batch, pick our fields, and get a clean spreadsheet in minutes. It paid for itself on day one.',
    stars: 5,
  },
  {
    name: 'James Okafor',
    role: 'AP Manager',
    company: 'Atlas Logistics',
    text: 'Our invoices come in every format imaginable — scanned, emailed PDFs, photos from the warehouse. This tool handles all of them. We\'ve cut our invoice processing time by 80%.',
    stars: 5,
  },
  {
    name: 'Maria Rodriguez',
    role: 'Insurance Operations Lead',
    company: 'Pacific Health Partners',
    text: 'We process thousands of EOBs monthly from different insurers. The extraction accuracy is remarkable — even on scanned forms with poor print quality. Game changer for our reconciliation workflow.',
    stars: 5,
  },
  {
    name: 'David Park',
    role: 'Contracts Administrator',
    company: 'Westfield Legal Group',
    text: 'I extract key terms from 50-100 contracts per week. Used to take two full days of manual work. Now I upload the batch, pick my fields, and have a complete comparison spreadsheet in 10 minutes.',
    stars: 5,
  },
]

/* ─── Pricing examples ─────────────────────────────────────────────────────── */
const PRICING_EXAMPLES = [
  {
    label: '50 invoices',
    pages: 50,
    cost: '$2.50',
    time: '~3 min',
    manual: '4+ hours',
  },
  {
    label: '200 annual reports (avg 80 pages)',
    pages: 16000,
    cost: '$800',
    time: '~45 min',
    manual: '400+ hours',
  },
  {
    label: '500 scanned receipts',
    pages: 500,
    cost: '$25',
    time: '~12 min',
    manual: '20+ hours',
  },
]

/* ─── Live demo samples ────────────────────────────────────────────────────── */
const DEMO_SAMPLES = [
  {
    id: 'scanned',
    label: 'Scanned Receipts (OCR)',
    desc: 'Low-quality scanned receipts and invoices — handwritten notes, poor scan quality, foreign languages.',
    tag: 'Scanned / OCR',
    files: [
      '/samples/sample_scanned_receipt.pdf',
      '/samples/sample_scanned_invoice.pdf',
      '/samples/sample_scanned_receipt_2.pdf',
    ],
    fields: ['Vendor', 'Company #', 'Doc #', 'Date', 'Cashier', 'Address', 'Subtotal', 'Tax', 'Total', 'Currency'],
    rows: [
      ['Morganfield\'s', '1174703-K', '000039121', '2018-03-23', 'Mizan Genting', 'Lot 50, Floor T2, Sky Avenue Genting Highlands', 'RM 559.53', 'RM 33.57', 'RM 593.10', 'MYR'],
      ['Gin Kee Trading', '001188498-D', 'CS00011955', '2017-12-02', 'CASHIER4', '15, Jalan Desa Bakti, Taman Desa', 'RM 7.00', 'RM 0.42', 'RM 7.42', 'MYR'],
      ['Book Talk Sdn Bhd', '659437-H', 'TD01167104', '2018-12-25', 'Pn. Yati', 'No. 12, Jalan SS 2/64, Petaling Jaya', 'RM 9.00', 'RM 0.00', 'RM 9.00', 'MYR'],
    ],
  },
  {
    id: 'invoices',
    label: 'Invoice Batch (5 invoices)',
    desc: 'Mixed digital invoices — different vendors, formats, and line items extracted into one spreadsheet.',
    tag: 'Digital PDFs',
    files: [
      '/samples/sample_invoice.pdf',
      '/samples/sample_invoice_2.pdf',
      '/samples/sample_invoice_3.pdf',
    ],
    fields: ['Invoice #', 'Date', 'Bill To', 'Ship To', 'Region', 'Items', 'Subtotal', 'Discount', 'Shipping', 'Total'],
    rows: [
      ['36258', 'Mar 06 2012', 'Aaron Bergman', '6 Elm St, New York', 'East', '3', '$45.62', '$9.74', '$14.22', '$50.10'],
      ['36651', 'May 12 2012', 'Aaron Hawkins', '820 Oak Ave, Seattle', 'West', '7', '$1,512.43', '$335.35', '$176.00', '$1,353.08'],
      ['15978', 'Mar 31 2012', 'Aaron Smayling', '44 Pine Rd, Houston', 'Central', '5', '$2,890.15', '$1,191.80', '$212.00', '$1,910.35'],
    ],
  },
  {
    id: 'annual-report',
    label: 'Berkshire Hathaway Annual Report',
    desc: '100+ page SEC annual report — complex multi-page financial tables, dense layouts, footnotes.',
    tag: '100+ pages',
    files: [],
    fields: ['Metric', '2023', '2022', '2021', '2020', '2019'],
    rows: [
      ['Total Revenues', '$364,482M', '$302,089M', '$276,094M', '$245,510M', '$254,616M'],
      ['Net Earnings', '$96,223M', '$(22,819)M', '$89,795M', '$42,521M', '$81,417M'],
      ['Operating Expenses', '$268,259M', '$280,908M', '$243,299M', '$232,989M', '$231,199M'],
      ['Total Assets', '$1,069,846M', '$948,452M', '$958,784M', '$873,729M', '$817,729M'],
      ['Shareholders\' Equity', '$561,199M', '$472,381M', '$500,140M', '$443,164M', '$424,791M'],
      ['Book Value / Share', '$393,194', '$328,078', '$343,890', '$287,237', '$261,417'],
    ],
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
  { value: '~$0.05', label: 'Per page processed' },
  { value: '< 30s', label: 'Average processing time' },
  { value: 'Any PDF', label: 'Scanned, digital, or photo' },
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
    a: 'About $0.05 per page — no monthly subscription, no commitment. Add funds to your account balance ($5, $10, $20, or any custom amount) and it depletes as you process documents. Your balance never expires. For context, 200 annual reports would cost roughly $800 — versus $20,000+ in manual analyst time.',
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
  const [activeSample, setActiveSample] = useState(0)
  const [activePdfFile, setActivePdfFile] = useState(0)

  const googleLogin = useGoogleLogin({
    onSuccess: async (tokenResponse) => {
      setLoading(true)
      setLoginError(null)
      trackEvent('login_start', { method: 'google' })
      try {
        const res = await api.post('/auth/google', {
          access_token: tokenResponse.access_token,
        })
        setUser(res.data.user, res.data.access_token)
        trackEvent('login_success', { method: 'google' })
        navigate('/dashboard')
      } catch (err: any) {
        const detail = err.response?.data?.detail
        setLoginError(typeof detail === 'string' ? detail : 'Login failed. Please try again.')
        trackEvent('login_error', { method: 'google' })
      } finally {
        setLoading(false)
      }
    },
    onError: () => {
      setLoginError('Google sign-in was cancelled or failed. Please try again.')
      trackEvent('login_cancelled', { method: 'google' })
    },
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

  const SignInButton = ({ size = 'xl', label = 'Get started', className = '' }: { size?: 'default' | 'sm' | 'lg' | 'xl' | 'icon'; label?: string; className?: string }) => (
    <Button
      size={size}
      onClick={() => { trackEvent('cta_click', { label, location: 'landing' }); googleLogin() }}
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
            <a href="#pipelines" className="text-xs text-muted-foreground hover:text-foreground transition-colors hidden sm:block">
              Automation
            </a>
            <a href="#demo" className="text-xs text-muted-foreground hover:text-foreground transition-colors hidden sm:block">
              Demo
            </a>
            <a href="#use-cases" className="text-xs text-muted-foreground hover:text-foreground transition-colors hidden sm:block">
              Use Cases
            </a>
            <a href="#pricing" className="text-xs text-muted-foreground hover:text-foreground transition-colors hidden sm:block">
              Pricing
            </a>
            <a href="#security" className="text-xs text-muted-foreground hover:text-foreground transition-colors hidden sm:block">
              Security
            </a>
            <a href="#faq" className="text-xs text-muted-foreground hover:text-foreground transition-colors hidden sm:block">
              FAQ
            </a>
            <a href="mailto:bigvisionsystems@gmail.com" className="text-xs text-muted-foreground hover:text-foreground transition-colors hidden md:block">
              Enterprise
            </a>
            <Button
              variant="outline"
              size="sm"
              onClick={() => { trackEvent('cta_click', { label: 'navbar_sign_in', location: 'header' }); googleLogin() }}
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
      <section className="flex flex-col items-center justify-center px-4 sm:px-6 py-8 sm:py-20 text-center relative overflow-hidden">
        <div className="absolute inset-0 flex items-center justify-center pointer-events-none">
          <div className="w-[700px] h-[500px] bg-primary/5 rounded-full blur-3xl" />
        </div>
        <div className="absolute top-0 right-0 w-[400px] h-[300px] bg-blue-200/20 rounded-full blur-3xl pointer-events-none" />
        <div className="absolute bottom-0 left-0 w-[300px] h-[300px] bg-violet-200/10 rounded-full blur-3xl pointer-events-none" />

        <div className="relative max-w-3xl mx-auto">
          <Badge variant="outline" className="mb-4 sm:mb-6 gap-1.5 px-3 py-1 text-xs font-medium">
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

          <p className="text-muted-foreground text-sm mb-6 sm:mb-10 max-w-xl mx-auto">
            No templates. No manual reformatting. Just the fields you need, organized in rows and columns.
          </p>

          <div className="flex flex-col items-center gap-3">
            <SignInButton label="Start extracting" className="min-w-0 sm:min-w-[280px] w-full sm:w-auto" />
            {loginError && (
              <p className="text-sm text-red-500 bg-red-50 border border-red-200 rounded-lg px-4 py-2 max-w-sm text-center">
                {loginError}
              </p>
            )}
            <p className="text-xs text-muted-foreground">
              No setup required · Pay as you go · Files deleted after processing
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

      {/* ── Pipeline Automation ────────────────────────────────────────── */}
      <section id="pipelines" className="py-14 sm:py-24 px-4 sm:px-6 border-t border-primary/20 scroll-mt-16 relative overflow-hidden">
        {/* Subtle background glow */}
        <div className="absolute inset-0 pointer-events-none">
          <div className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 w-[800px] h-[400px] bg-primary/5 rounded-full blur-3xl" />
        </div>

        <div className="max-w-5xl mx-auto relative">
          <div className="text-center mb-12">
            <p className="text-xs font-semibold uppercase tracking-widest text-muted-foreground mb-3">
              Automation
            </p>
            <h2 className="text-3xl sm:text-4xl font-bold tracking-tight mb-4">
              Set it once, extract forever
            </h2>
            <p className="text-muted-foreground text-sm sm:text-base mb-3 max-w-2xl mx-auto leading-relaxed">
              Most tools make you upload files one by one. Our pipelines connect directly to your cloud storage
              and <span className="text-foreground font-medium">automatically process every new document</span> the moment it arrives — around the clock.
            </p>
            <p className="text-muted-foreground text-xs max-w-lg mx-auto">
              Works with Google Drive, SharePoint, and Outlook. New integrations added regularly.
            </p>
          </div>

          {/* Pipeline flow: numbered steps with connectors */}
          <div className="grid sm:grid-cols-2 lg:grid-cols-4 gap-5 mb-10">
            <div className="bg-card border border-border rounded-xl p-5 hover:border-primary/30 hover:shadow-md transition-all relative">
              <div className="absolute -top-2.5 left-5 bg-primary text-white text-[10px] font-bold px-2 py-0.5 rounded-full">1</div>
              <div className="w-9 h-9 bg-primary/10 rounded-lg flex items-center justify-center mb-4 mt-1">
                <GitBranch size={17} className="text-primary" />
              </div>
              <h3 className="font-semibold text-sm mb-1.5">Connect a source folder</h3>
              <p className="text-muted-foreground text-xs leading-relaxed">Link a folder in Google Drive, SharePoint, or Outlook where invoices, reports, or forms land.</p>
            </div>
            <div className="bg-card border border-border rounded-xl p-5 hover:border-primary/30 hover:shadow-md transition-all relative">
              <div className="absolute -top-2.5 left-5 bg-primary text-white text-[10px] font-bold px-2 py-0.5 rounded-full">2</div>
              <div className="w-9 h-9 bg-primary/10 rounded-lg flex items-center justify-center mb-4 mt-1">
                <ClipboardList size={17} className="text-primary" />
              </div>
              <h3 className="font-semibold text-sm mb-1.5">Define your extraction fields</h3>
              <p className="text-muted-foreground text-xs leading-relaxed">Tell the system exactly what data to pull — vendor name, invoice number, line items, totals, dates, or any custom field.</p>
            </div>
            <div className="bg-card border border-border rounded-xl p-5 hover:border-primary/30 hover:shadow-md transition-all relative">
              <div className="absolute -top-2.5 left-5 bg-primary text-white text-[10px] font-bold px-2 py-0.5 rounded-full">3</div>
              <div className="w-9 h-9 bg-primary/10 rounded-lg flex items-center justify-center mb-4 mt-1">
                <Cpu size={17} className="text-primary" />
              </div>
              <h3 className="font-semibold text-sm mb-1.5">Auto-processing kicks in</h3>
              <p className="text-muted-foreground text-xs leading-relaxed">Every new file that lands in your folder is automatically detected, read, and extracted — no manual upload needed.</p>
            </div>
            <div className="bg-card border border-border rounded-xl p-5 hover:border-primary/30 hover:shadow-md transition-all relative">
              <div className="absolute -top-2.5 left-5 bg-emerald-500 text-white text-[10px] font-bold px-2 py-0.5 rounded-full">4</div>
              <div className="w-9 h-9 bg-emerald-500/10 rounded-lg flex items-center justify-center mb-4 mt-1">
                <Download size={17} className="text-emerald-600" />
              </div>
              <h3 className="font-semibold text-sm mb-1.5">Spreadsheet delivered</h3>
              <p className="text-muted-foreground text-xs leading-relaxed">Clean, structured Excel or CSV output is saved to your destination folder — ready for your team or accounting system.</p>
            </div>
          </div>

          {/* Benefit highlights */}
          <div className="bg-card/60 border border-border/60 rounded-xl p-5 sm:p-6 mb-10">
            <div className="grid sm:grid-cols-3 gap-4 sm:gap-6 text-center">
              <div>
                <p className="text-2xl font-bold text-foreground">Automatic</p>
                <p className="text-xs text-muted-foreground mt-0.5">new files processed the moment they arrive</p>
              </div>
              <div>
                <p className="text-2xl font-bold text-foreground">Always on</p>
                <p className="text-xs text-muted-foreground mt-0.5">monitoring your folders around the clock</p>
              </div>
              <div>
                <p className="text-2xl font-bold text-foreground">Any volume</p>
                <p className="text-xs text-muted-foreground mt-0.5">5 files or 5,000 — same accuracy every time</p>
              </div>
            </div>
          </div>

          <div className="text-center">
            <SignInButton size="lg" label="Set up your first pipeline" className="shadow-none" />
          </div>
        </div>
      </section>

      {/* ── Try Sample PDFs (Live Demo) ────────────────────────────────── */}
      <section id="demo" className="py-12 sm:py-20 px-4 sm:px-6 border-t border-border/50 bg-card/30 scroll-mt-16">
        <div className="max-w-6xl mx-auto">
          <p className="text-center text-xs font-semibold uppercase tracking-widest text-muted-foreground mb-3">
            See it in action
          </p>
          <h2 className="text-2xl sm:text-3xl font-bold text-center tracking-tight mb-4">
            Real documents. Real results.
          </h2>
          <p className="text-center text-muted-foreground text-sm mb-12 max-w-lg mx-auto">
            These aren't mock-ups — this is actual output from our extraction engine.
            Scanned receipts, digital invoices, 100-page SEC filings. Same tool, same accuracy.
          </p>

          {/* Sample selector tabs */}
          <div className="flex flex-wrap justify-center gap-2 mb-8">
            {DEMO_SAMPLES.map((s, i) => (
              <button
                key={s.id}
                onClick={() => { setActiveSample(i); setActivePdfFile(0); trackEvent('demo_sample_select', { sample: s.id }) }}
                className={`px-4 py-2 rounded-lg text-xs font-medium border transition-all ${
                  activeSample === i
                    ? 'bg-primary text-primary-foreground border-primary shadow-sm'
                    : 'bg-card text-muted-foreground border-border hover:border-primary/40 hover:text-foreground'
                }`}
              >
                {s.label}
                <span className={`ml-2 px-1.5 py-0.5 rounded text-[10px] ${
                  activeSample === i ? 'bg-white/20' : 'bg-secondary'
                }`}>
                  {s.tag}
                </span>
              </button>
            ))}
          </div>

          {/* Demo card */}
          {(() => {
            const sample = DEMO_SAMPLES[activeSample]
            return (
              <div className="bg-card border border-border rounded-2xl overflow-hidden shadow-lg">
                {/* Header */}
                <div className="bg-muted/30 border-b border-border/50 px-5 py-4">
                  <h3 className="font-semibold text-sm">{sample.label}</h3>
                  <p className="text-xs text-muted-foreground mt-0.5">{sample.desc}</p>
                </div>

                {/* Stacked: Source PDF on top, Extracted Data below */}
                <div className="flex flex-col">
                  {/* Source PDF panel */}
                  {sample.files.length > 0 && (
                    <div className="border-b border-border/50 flex flex-col">
                      <div className="px-4 py-2 bg-muted/20 border-b border-border/50 flex items-center gap-2">
                        <FileText size={13} className="text-muted-foreground" />
                        <span className="text-xs font-semibold text-muted-foreground uppercase tracking-wider">Source PDF</span>
                        {sample.files.length > 1 && (
                          <div className="flex items-center gap-1 ml-auto">
                            {sample.files.map((_file, fi) => (
                              <button
                                key={fi}
                                onClick={() => setActivePdfFile(fi)}
                                className={`px-2 py-0.5 rounded text-[10px] font-medium transition-all ${
                                  activePdfFile === fi
                                    ? 'bg-primary text-primary-foreground'
                                    : 'bg-secondary text-muted-foreground hover:text-foreground'
                                }`}
                              >
                                Doc {fi + 1}
                              </button>
                            ))}
                          </div>
                        )}
                      </div>
                      <div className="h-[300px] sm:h-[400px]">
                        <iframe
                          key={`${sample.id}-${activePdfFile}`}
                          src={sample.files[activePdfFile]}
                          title={`Source PDF ${activePdfFile + 1}: ${sample.label}`}
                          className="w-full h-full bg-white"
                        />
                      </div>
                    </div>
                  )}

                  {/* Extracted data panel */}
                  <div className="flex flex-col">
                    <div className="px-4 py-2 bg-muted/20 border-b border-border/50 flex items-center gap-2">
                      <ArrowRight size={13} className="text-emerald-500" />
                      <span className="text-xs font-semibold text-muted-foreground uppercase tracking-wider">Extracted Data</span>
                      <CheckCircle2 size={12} className="text-emerald-500 ml-auto" />
                    </div>
                    <div className="overflow-x-auto">
                      <table className="w-full text-[11px] min-w-[600px]">
                        <thead>
                          <tr className="border-b border-border bg-muted/10">
                            <th className="px-2 py-2 text-left font-semibold text-muted-foreground w-6">#</th>
                            {sample.fields.map((f) => (
                              <th key={f} className="px-2 py-2 text-left font-semibold text-muted-foreground whitespace-nowrap">{f}</th>
                            ))}
                          </tr>
                        </thead>
                        <tbody>
                          {sample.rows.map((row, ri) => (
                            <tr key={ri} className="border-b border-border/50 hover:bg-muted/10 transition-colors">
                              <td className="px-2 py-2 text-muted-foreground font-mono">{ri + 1}</td>
                              {row.map((cell, ci) => (
                                <td key={ci} className="px-2 py-2 whitespace-nowrap" title={cell}>{cell}</td>
                              ))}
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  </div>
                </div>

                {/* Footer */}
                <div className="px-5 py-3 bg-muted/10 border-t border-border/50 flex flex-wrap items-center justify-between gap-2">
                  <p className="text-xs text-muted-foreground">
                    <CheckCircle2 size={12} className="text-emerald-500 inline mr-1" />
                    Extracted in &lt;30 seconds · Fields chosen by you · Download as .xlsx or .csv
                  </p>
                  <SignInButton size="sm" label="Try with your own PDFs" className="shadow-none" />
                </div>
              </div>
            )
          })()}
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
                  onClick={() => { setActiveCase(i); trackEvent('use_case_select', { case: c.label }) }}
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
                      <Button size="sm" variant="ghost" className="h-7 text-xs gap-1 text-primary" onClick={() => { trackEvent('cta_click', { label: 'try_it_use_case', location: 'use_cases' }); googleLogin() }}>
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

      {/* ── Why This Tool / Purpose-Built AI ─────────────────────────────── */}
      <section className="py-12 sm:py-20 px-4 sm:px-6 border-t border-border/50 scroll-mt-16">
        <div className="max-w-4xl mx-auto">
          <p className="text-center text-xs font-semibold uppercase tracking-widest text-muted-foreground mb-3">
            Why we're different
          </p>
          <h2 className="text-2xl sm:text-3xl font-bold text-center tracking-tight mb-4">
            This isn't another generic AI tool
          </h2>
          <p className="text-center text-muted-foreground text-sm mb-12 max-w-lg mx-auto">
            Most "AI PDF extractors" just send your document to a chatbot and hope for the best.
            We built a dedicated extraction engine — purpose-trained models that understand document
            structure, not just text. That's why we hit 94%+ accuracy where others fall apart.
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

      {/* ── Pricing Transparency ───────────────────────────────────────── */}
      <section id="pricing" className="py-12 sm:py-20 px-4 sm:px-6 border-t border-border/50 bg-card/30 scroll-mt-16">
        <div className="max-w-4xl mx-auto">
          <p className="text-center text-xs font-semibold uppercase tracking-widest text-muted-foreground mb-3">
            Simple pricing
          </p>
          <h2 className="text-2xl sm:text-3xl font-bold text-center tracking-tight mb-4">
            ~$0.05 per page. No subscriptions.
          </h2>
          <p className="text-center text-muted-foreground text-sm mb-4 max-w-lg mx-auto">
            Pay only for what you process. Add funds to your balance and it depletes as you extract.
            No monthly fees, no commitment, no expiry. Most competitors charge $0.10–$0.50 per page
            or lock you into $99+/month plans.
          </p>
          <p className="text-center text-primary text-sm font-semibold mb-12">
            That's up to 90% cheaper than alternatives like Docparser, Rossum, or Nanonets.
          </p>

          {/* Pricing comparison cards */}
          <div className="grid sm:grid-cols-3 gap-5 mb-10">
            {PRICING_EXAMPLES.map((ex) => (
              <div key={ex.label} className="bg-card border border-border rounded-xl p-5 text-center hover:border-primary/30 hover:shadow-sm transition-all">
                <p className="text-xs text-muted-foreground font-medium mb-3 min-h-[32px]">{ex.label}</p>
                <p className="text-3xl font-bold text-primary mb-1">{ex.cost}</p>
                <p className="text-xs text-muted-foreground mb-4">{ex.pages.toLocaleString()} pages × $0.05</p>
                <div className="border-t border-border/50 pt-3 space-y-1.5">
                  <div className="flex items-center justify-between text-xs">
                    <span className="text-muted-foreground">With PDFExcel.ai</span>
                    <span className="font-semibold text-emerald-600">{ex.time}</span>
                  </div>
                  <div className="flex items-center justify-between text-xs">
                    <span className="text-muted-foreground">Manual copy-paste</span>
                    <span className="text-red-400 line-through">{ex.manual}</span>
                  </div>
                </div>
              </div>
            ))}
          </div>

          <div className="text-center">
            <p className="text-xs text-muted-foreground mb-5">
              <DollarSign size={12} className="inline mr-1 text-primary" />
              Example: 200 annual reports (avg 80 pages each) = 16,000 pages = <strong>$800 total</strong>. Manually, that's 400+ analyst-hours at $50/hr = <strong>$20,000</strong>. You save <strong>96%</strong>.
            </p>
            <SignInButton size="xl" label="Start extracting" className="min-w-0 sm:min-w-[280px] w-full sm:w-auto" />
          </div>
        </div>
      </section>

      {/* ── Testimonials ───────────────────────────────────────────────── */}
      <section className="py-12 sm:py-20 px-4 sm:px-6 border-t border-border/50 scroll-mt-16">
        <div className="max-w-5xl mx-auto">
          <p className="text-center text-xs font-semibold uppercase tracking-widest text-muted-foreground mb-3">
            Trusted by teams
          </p>
          <h2 className="text-2xl sm:text-3xl font-bold text-center tracking-tight mb-12">
            What our users say
          </h2>

          <div className="grid sm:grid-cols-2 gap-5">
            {TESTIMONIALS.map((t) => (
              <div
                key={t.name}
                className="bg-card border border-border rounded-xl p-5 hover:border-primary/30 hover:shadow-sm transition-all"
              >
                <div className="flex items-center gap-0.5 mb-3">
                  {Array.from({ length: t.stars }).map((_, i) => (
                    <Star key={i} size={13} className="text-amber-400 fill-amber-400" />
                  ))}
                </div>
                <p className="text-sm text-muted-foreground leading-relaxed mb-4 italic">
                  "{t.text}"
                </p>
                <div className="border-t border-border/50 pt-3">
                  <p className="text-sm font-semibold">{t.name}</p>
                  <p className="text-xs text-muted-foreground">{t.role} · {t.company}</p>
                </div>
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
                  onClick={() => { const next = openFaq === i ? null : i; setOpenFaq(next); if (next !== null) trackEvent('faq_expand', { question: item.q }) }}
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
            <a href="mailto:bigvisionsystems@gmail.com">
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
            Upload your first PDF and see structured results in seconds. No setup, pay as you go, no commitment.
          </p>
          <p className="text-muted-foreground text-xs mb-8 flex items-center justify-center gap-1.5">
            <Lock size={10} />
            Your files are encrypted and deleted after processing
          </p>
          <SignInButton label="Get started" className="min-w-0 sm:min-w-[220px] w-full sm:w-auto" />
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
            <a href="/terms" className="hover:text-foreground transition-colors">Terms of Service</a>
            <a href="#security" className="hover:text-foreground transition-colors">Security</a>
            <a href="#faq" className="hover:text-foreground transition-colors">FAQ</a>
            <a href="mailto:bigvisionsystems@gmail.com" className="hover:text-foreground transition-colors">Contact</a>
          </div>
          <span>© 2026 Big Vision Systems LLC. All rights reserved.</span>
        </div>
      </footer>
    </div>
  )
}
