import { useNavigate } from 'react-router-dom'
import { useCallback, useState, useEffect } from 'react'
import { useGoogleLogin } from '@react-oauth/google'
import { PublicClientApplication } from '@azure/msal-browser'
import * as Dialog from '@radix-ui/react-dialog'
import {
  FileSpreadsheet, ArrowRight, ArrowLeft, Lock, Mail,
  CheckCircle2, Receipt, BarChart3, Landmark, Calculator,
  CreditCard, FileText, TrendingUp, DollarSign,
  X,
} from 'lucide-react'
import { trackEvent } from '@/lib/analytics'
import api from '@/lib/api'
import { useAuthStore } from '@/store/authStore'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { Card, CardContent } from '@/components/ui/card'

const msalInstance = new PublicClientApplication({
  auth: {
    clientId: import.meta.env.VITE_MICROSOFT_CLIENT_ID || '',
    authority: 'https://login.microsoftonline.com/common',
    redirectUri: window.location.origin,
  },
  cache: { cacheLocation: 'sessionStorage' },
})
const msalReady = msalInstance.initialize().then(() => msalInstance.handleRedirectPromise()).then((r) => {
  if (window.location.hash.includes('state=') || window.location.search.includes('state=')) window.history.replaceState(null, '', window.location.pathname)
  return r
})

const USE_CASES = [
  {
    icon: Receipt,
    title: 'Accounts Payable — Invoice Processing',
    color: 'bg-blue-500/10 text-blue-600',
    desc: 'Stop manually entering vendor invoices. Upload stacks of invoices from any vendor format — scanned, emailed PDFs, or photos — and extract vendor names, invoice numbers, line items, totals, tax amounts, PO numbers, and payment terms into a single spreadsheet ready for your AP system.',
    fields: ['Vendor Name', 'Invoice Number', 'Invoice Date', 'PO Number', 'Line Items', 'Subtotal', 'Tax Amount', 'Total Due', 'Payment Terms', 'Due Date'],
  },
  {
    icon: DollarSign,
    title: 'Accounts Receivable — Payment & Remittance',
    color: 'bg-emerald-500/10 text-emerald-600',
    desc: 'Extract data from remittance advices, payment stubs, and customer payment records. Capture payment amounts, invoice references, check numbers, and adjustment details to reconcile AR aging reports and reduce days sales outstanding.',
    fields: ['Customer Name', 'Payment Amount', 'Payment Date', 'Check/Reference Number', 'Invoice Numbers Applied', 'Discount Taken', 'Adjustment Amount', 'Balance Remaining'],
  },
  {
    icon: Landmark,
    title: 'Bank Statements to Excel',
    color: 'bg-violet-500/10 text-violet-600',
    desc: 'CPAs and bookkeepers spend hours manually entering bank statement data. Upload bank statements from any institution and extract transaction dates, descriptions, amounts, running balances, and account details into organized spreadsheets ready for reconciliation or import into accounting software.',
    fields: ['Transaction Date', 'Description', 'Debit Amount', 'Credit Amount', 'Running Balance', 'Account Number', 'Statement Period', 'Reference Number'],
  },
  {
    icon: BarChart3,
    title: 'Financial Reports & SEC Filings',
    color: 'bg-pink-500/10 text-pink-600',
    desc: 'Pull key financial metrics from 10-Ks, 10-Qs, annual reports, and quarterly filings. Compare revenue, net income, total assets, cash flow, and equity across multiple companies and periods — without reading hundreds of pages of dense financial tables.',
    fields: ['Company Name', 'Report Period', 'Total Revenue', 'Net Income', 'Total Assets', 'Total Liabilities', 'Shareholders Equity', 'Cash Flow from Operations'],
  },
  {
    icon: Calculator,
    title: 'Tax Documents & 1099s',
    color: 'bg-orange-500/10 text-orange-600',
    desc: 'CPA firms and tax preparers process hundreds of 1099s, W-2s, K-1s, and client-provided tax documents during busy season. Extract payer/payee info, income amounts, withholding, and EINs into spreadsheets for efficient tax preparation and filing.',
    fields: ['Payer Name', 'Payer EIN', 'Recipient Name', 'Recipient TIN', 'Income Type', 'Gross Amount', 'Federal Withholding', 'State Withholding', 'Tax Year'],
  },
  {
    icon: CreditCard,
    title: 'Expense Reports & Receipts',
    color: 'bg-teal-500/10 text-teal-600',
    desc: 'Digitize stacks of expense receipts and corporate card statements. Extract merchant names, dates, amounts, categories, and tax details from any receipt format — including scanned, photographed, and foreign-language receipts — into organized expense spreadsheets.',
    fields: ['Merchant Name', 'Transaction Date', 'Amount', 'Tax/VAT', 'Currency', 'Category', 'Payment Method', 'Receipt Number'],
  },
  {
    icon: TrendingUp,
    title: 'Audit Workpapers & Trial Balances',
    color: 'bg-indigo-500/10 text-indigo-600',
    desc: 'Auditors and accounting firms can extract data from trial balances, general ledger reports, and workpapers. Pull account numbers, descriptions, debit/credit balances, and adjusting entries into standardized spreadsheets for review and analysis.',
    fields: ['Account Number', 'Account Description', 'Debit Balance', 'Credit Balance', 'Adjusting Entry', 'Adjusted Balance', 'Prior Year Balance', 'Variance'],
  },
  {
    icon: FileText,
    title: 'Client Financial Statements',
    color: 'bg-amber-500/10 text-amber-600',
    desc: 'Accounting firms receiving financial statements from clients in various formats can extract balance sheet items, income statement line items, and cash flow data into standardized templates — making compilation, review, and analysis dramatically faster.',
    fields: ['Entity Name', 'Statement Type', 'Period End Date', 'Revenue', 'COGS', 'Operating Expenses', 'Net Income', 'Total Assets', 'Total Liabilities'],
  },
]

export default function AccountingFinancePage() {
  const navigate = useNavigate()
  const { setUser, user } = useAuthStore()
  const [loading, setLoading] = useState(false)
  const [loginError, setLoginError] = useState<string | null>(null)
  const [activeCase, setActiveCase] = useState(0)
  const [showProviderDialog, setShowProviderDialog] = useState(false)

  useEffect(() => {
    let cancelled = false
    msalReady.then(async (result) => {
      if (cancelled || !result) return
      setLoading(true)
      try {
        const res = await api.post('/auth/microsoft', { access_token: result.accessToken })
        setUser(res.data.user, res.data.access_token); navigate('/dashboard')
      } catch { setLoading(false) }
    }).catch(() => {})
    return () => { cancelled = true }
  }, [setUser, navigate])

  const googleLogin = useGoogleLogin({
    onSuccess: async (tokenResponse) => {
      setShowProviderDialog(false); setLoading(true); setLoginError(null)
      try {
        const res = await api.post('/auth/google', { access_token: tokenResponse.access_token })
        setUser(res.data.user, res.data.access_token); navigate('/dashboard')
      } catch (err: any) {
        setLoginError(err.response?.data?.detail || 'Login failed.'); setLoading(false)
      }
    },
    onError: () => setLoginError('Google sign-in was cancelled or failed.'),
  })

  const microsoftLogin = useCallback(async () => {
    setShowProviderDialog(false); setLoginError(null)
    try {
      await msalReady
      await msalInstance.loginRedirect({ scopes: ['User.Read', 'openid', 'profile', 'email'] })
    } catch (err: any) {
      setLoginError(err.errorCode === 'interaction_in_progress' ? 'A sign-in is already in progress.' : 'Microsoft login failed.')
    }
  }, [])

  if (user) { navigate('/dashboard'); return null }

  const active = USE_CASES[activeCase]

  const GoogleIcon = () => (
    <svg className="w-4 h-4" viewBox="0 0 24 24">
      <path d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92c-.26 1.37-1.04 2.53-2.21 3.31v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.09z" fill="#4285F4"/>
      <path d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z" fill="#34A853"/>
      <path d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.07H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.93l2.85-2.22.81-.62z" fill="#FBBC05"/>
      <path d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.07l3.66 2.84c.87-2.6 3.3-4.53 6.16-4.53z" fill="#EA4335"/>
    </svg>
  )
  const MicrosoftIcon = () => (
    <svg className="w-4 h-4" viewBox="0 0 21 21">
      <rect x="1" y="1" width="9" height="9" fill="#F25022"/><rect x="11" y="1" width="9" height="9" fill="#7FBA00"/>
      <rect x="1" y="11" width="9" height="9" fill="#00A4EF"/><rect x="11" y="11" width="9" height="9" fill="#FFB900"/>
    </svg>
  )

  const SignInButton = ({ size = 'xl' as const, label = 'Get started', className = '' }) => (
    <Button size={size} onClick={() => { trackEvent('cta_click', { label, location: 'accounting' }); setShowProviderDialog(true) }} disabled={loading} className={`gap-3 shadow-lg shadow-primary/20 ${className}`}>
      {loading ? <div className="w-4 h-4 border-2 border-primary-foreground/30 border-t-white rounded-full animate-spin" /> : label}
    </Button>
  )

  return (
    <div className="min-h-screen bg-background text-foreground flex flex-col">
      {/* Navbar */}
      <header className="border-b border-border/50 backdrop-blur-sm sticky top-0 z-50 bg-background/80">
        <div className="max-w-6xl mx-auto px-4 sm:px-6 h-14 flex items-center justify-between">
          <a href="/" className="flex items-center gap-2.5">
            <div className="w-7 h-7 bg-primary rounded-lg flex items-center justify-center">
              <FileSpreadsheet size={14} className="text-white" />
            </div>
            <span className="font-semibold text-sm tracking-tight">GridPull</span>
          </a>
          <div className="flex items-center gap-4">
            <a href="/" className="text-xs text-muted-foreground hover:text-foreground transition-colors hidden sm:flex items-center gap-1">
              <ArrowLeft size={12} /> Back to Home
            </a>
            <Button variant="outline" size="sm" onClick={() => setShowProviderDialog(true)} disabled={loading}>
              Try for free <ArrowRight size={13} />
            </Button>
          </div>
        </div>
      </header>

      {/* Hero */}
      <section className="flex flex-col items-center justify-center px-4 sm:px-6 py-8 sm:py-20 text-center relative overflow-hidden">
        <div className="absolute inset-0 flex items-center justify-center pointer-events-none">
          <div className="w-[700px] h-[500px] bg-emerald-500/5 rounded-full blur-3xl" />
        </div>

        <div className="relative max-w-3xl mx-auto">
          <Badge variant="outline" className="mb-4 sm:mb-6 gap-1.5 px-3 py-1 text-xs font-medium">
            <Calculator size={10} />
            Accounting & Finance
          </Badge>

          <h1 className="text-3xl sm:text-5xl md:text-6xl font-bold tracking-tight mb-6 leading-[1.1]">
            Turn financial documents{' '}
            <br className="hidden sm:block" />
            <span className="text-primary">into structured spreadsheets</span>
          </h1>

          <p className="text-muted-foreground text-base sm:text-lg mb-4 max-w-2xl mx-auto leading-relaxed">
            Upload invoices, bank statements, tax documents, financial reports, and receipts.
            GridPull extracts the data you need into clean Excel files — ready for your accounting software, reconciliation, or audit.
          </p>

          <p className="text-muted-foreground text-sm mb-6 sm:mb-10 max-w-xl mx-auto">
            Built for CPAs, bookkeepers, AP/AR teams, auditors, and finance professionals.
          </p>

          <div className="flex flex-col items-center gap-3">
            <SignInButton label="Start extracting — it's free" className="min-w-0 sm:min-w-[280px] w-full sm:w-auto" />
            <p className="text-xs text-muted-foreground">
              Free to start · No setup required · Files deleted after processing
            </p>
          </div>
        </div>
      </section>

      {/* Use Cases */}
      <section className="py-12 sm:py-20 px-4 sm:px-6 border-t border-border/50 bg-card/30">
        <div className="max-w-5xl mx-auto">
          <p className="text-center text-xs font-semibold uppercase tracking-widest text-muted-foreground mb-3">
            Accounting & Finance Use Cases
          </p>
          <h2 className="text-2xl sm:text-3xl font-bold text-center tracking-tight mb-4">
            Every financial document, structured in seconds
          </h2>
          <p className="text-center text-muted-foreground text-sm mb-12 max-w-lg mx-auto">
            From AP invoice batches to bank statement reconciliation — GridPull handles
            the document types accounting teams deal with every day.
          </p>

          <div className="grid lg:grid-cols-2 gap-6 items-start">
            <div className="space-y-2">
              {USE_CASES.map((c, i) => (
                <button
                  key={c.title}
                  onClick={() => { setActiveCase(i); trackEvent('use_case_select', { case: c.title }) }}
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
                    <div className="font-medium text-sm">{c.title}</div>
                    <div className="text-xs text-muted-foreground line-clamp-2">{c.desc}</div>
                  </div>
                  {activeCase === i && <ArrowRight size={14} className="text-primary flex-shrink-0" />}
                </button>
              ))}
            </div>

            <div className="sticky top-20">
              <Card className="overflow-hidden border-border/60 shadow-lg">
                <div className="bg-muted/30 border-b border-border/50 px-5 py-3 flex items-center gap-2">
                  <div className={`w-7 h-7 rounded-lg flex items-center justify-center ${active.color}`}>
                    <active.icon size={14} />
                  </div>
                  <span className="text-sm font-semibold">{active.title}</span>
                </div>
                <CardContent className="p-5">
                  <p className="text-sm text-muted-foreground mb-5 leading-relaxed">{active.desc}</p>
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
                      <Button size="sm" variant="ghost" className="h-7 text-xs gap-1 text-primary" onClick={() => setShowProviderDialog(true)}>
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

      {/* How it works */}
      <section className="py-12 sm:py-20 px-4 sm:px-6 border-t border-border/50">
        <div className="max-w-4xl mx-auto">
          <h2 className="text-2xl sm:text-3xl font-bold text-center tracking-tight mb-4">
            How it works for accounting teams
          </h2>
          <p className="text-center text-muted-foreground text-sm mb-12 max-w-lg mx-auto">
            No templates to build. No rules to configure. Just upload and extract.
          </p>

          <div className="grid sm:grid-cols-3 gap-6">
            {[
              { step: '1', title: 'Upload financial documents', desc: 'Drag and drop invoices, bank statements, 1099s, receipts, or any financial PDF. Handles scanned documents and photos too.' },
              { step: '2', title: 'Pick your fields', desc: 'Select from accounting-specific presets like Vendor Name, Invoice Total, Transaction Date — or type any custom field you need.' },
              { step: '3', title: 'Download your spreadsheet', desc: 'Get a clean Excel file with one row per document, one column per field. Import directly into QuickBooks, Xero, or your ERP.' },
            ].map((s) => (
              <div key={s.step} className="bg-card border border-border rounded-xl p-6 hover:border-primary/30 hover:shadow-sm transition-all">
                <span className="text-xs font-bold text-primary/60 uppercase tracking-wider">Step {s.step}</span>
                <h3 className="font-semibold text-sm mt-3 mb-2">{s.title}</h3>
                <p className="text-muted-foreground text-xs leading-relaxed">{s.desc}</p>
              </div>
            ))}
          </div>

          <div className="text-center mt-10">
            <SignInButton size="xl" label="Try it free with your financial documents" className="min-w-0 sm:min-w-[340px] w-full sm:w-auto" />
          </div>
        </div>
      </section>

      {/* Testimonials */}
      <section className="py-12 sm:py-20 px-4 sm:px-6 border-t border-border/50 bg-card/30">
        <div className="max-w-3xl mx-auto">
          <div className="grid sm:grid-cols-2 gap-5">
            <div className="bg-card border border-border rounded-xl p-5">
              <p className="text-sm text-muted-foreground italic leading-relaxed mb-4">
                "We were manually pulling data from 200+ SEC filings per quarter. Now we upload the batch, pick our fields, and get a clean spreadsheet in minutes. It paid for itself on day one."
              </p>
              <p className="text-sm font-semibold">Sarah Chen</p>
              <p className="text-xs text-muted-foreground">Financial Analyst · Meridian Capital</p>
            </div>
            <div className="bg-card border border-border rounded-xl p-5">
              <p className="text-sm text-muted-foreground italic leading-relaxed mb-4">
                "Our invoices come in every format imaginable — scanned, emailed PDFs, photos from the warehouse. This tool handles all of them. We've cut our invoice processing time by 80%."
              </p>
              <p className="text-sm font-semibold">James Okafor</p>
              <p className="text-xs text-muted-foreground">AP Manager · Atlas Logistics</p>
            </div>
          </div>
        </div>
      </section>

      {/* CTA */}
      <section className="py-12 sm:py-16 px-4 sm:px-6 border-t border-border/50 bg-primary/5">
        <div className="max-w-2xl mx-auto text-center">
          <h2 className="text-2xl font-bold tracking-tight mb-3">
            Stop manually entering financial data
          </h2>
          <p className="text-muted-foreground text-sm mb-3">
            Upload your first financial document and see structured results in seconds.
          </p>
          <p className="text-muted-foreground text-xs mb-8 flex items-center justify-center gap-1.5">
            <Lock size={10} /> Files encrypted and deleted after processing
          </p>
          <SignInButton label="Get started for free" className="min-w-0 sm:min-w-[220px] w-full sm:w-auto" />
        </div>
      </section>

      {/* Footer */}
      <footer className="border-t border-border/50 py-6 px-4 sm:px-6">
        <div className="max-w-6xl mx-auto flex flex-col items-center gap-3 text-xs text-muted-foreground">
          <div className="flex items-center gap-2">
            <div className="w-5 h-5 bg-primary rounded-md flex items-center justify-center">
              <FileSpreadsheet size={11} className="text-white" />
            </div>
            GridPull
          </div>
          <div className="flex flex-wrap items-center justify-center gap-x-4 gap-y-1">
            <a href="/" className="hover:text-foreground transition-colors">Home</a>
            <a href="/privacy" className="hover:text-foreground transition-colors">Privacy Policy</a>
            <a href="/terms" className="hover:text-foreground transition-colors">Terms &amp; Conditions</a>
            <a href="#" onClick={(e) => { e.preventDefault(); window.scrollTo({ top: 0, behavior: 'smooth' }) }} className="hover:text-foreground transition-colors">Back to top</a>
            <a href="mailto:bigvisionsystems@gmail.com" className="hover:text-foreground transition-colors">Contact</a>
          </div>
          <span>&copy; 2026 Big Vision Systems LLC. All rights reserved.</span>
        </div>
      </footer>

      {/* Sign-in dialog */}
      <Dialog.Root open={showProviderDialog} onOpenChange={setShowProviderDialog}>
        <Dialog.Portal>
          <Dialog.Overlay className="fixed inset-0 z-50 bg-black/50 backdrop-blur-sm data-[state=open]:animate-in data-[state=closed]:animate-out data-[state=closed]:fade-out-0 data-[state=open]:fade-in-0" />
          <Dialog.Content className="fixed left-1/2 top-1/2 z-50 w-full max-w-sm -translate-x-1/2 -translate-y-1/2 rounded-xl border border-border bg-background p-6 shadow-2xl data-[state=open]:animate-in data-[state=closed]:animate-out data-[state=closed]:fade-out-0 data-[state=open]:fade-in-0 data-[state=closed]:zoom-out-95 data-[state=open]:zoom-in-95">
            <div className="flex items-center justify-between mb-6">
              <Dialog.Title className="text-lg font-semibold">Sign in to continue</Dialog.Title>
              <Dialog.Close className="rounded-full p-1 hover:bg-muted transition-colors"><X size={16} /></Dialog.Close>
            </div>
            <div className="flex flex-col gap-3">
              <button onClick={() => { trackEvent('provider_select', { provider: 'google' }); googleLogin() }} disabled={loading} className="flex items-center gap-3 w-full rounded-lg border border-border px-4 py-3 text-sm font-medium hover:bg-muted/50 transition-colors disabled:opacity-50">
                <GoogleIcon /> Continue with Google
              </button>
              <button onClick={() => { trackEvent('provider_select', { provider: 'microsoft' }); microsoftLogin() }} disabled={loading} className="flex items-center gap-3 w-full rounded-lg border border-border px-4 py-3 text-sm font-medium hover:bg-muted/50 transition-colors disabled:opacity-50">
                <MicrosoftIcon /> Continue with Microsoft
              </button>
            </div>
            {loginError && <p className="mt-4 text-sm text-red-500 text-center">{loginError}</p>}
            <p className="mt-5 text-xs text-muted-foreground text-center">
              By signing in, you agree to our <a href="/terms" className="underline hover:text-foreground">Terms</a> and <a href="/privacy" className="underline hover:text-foreground">Privacy Policy</a>.
            </p>
          </Dialog.Content>
        </Dialog.Portal>
      </Dialog.Root>
    </div>
  )
}
