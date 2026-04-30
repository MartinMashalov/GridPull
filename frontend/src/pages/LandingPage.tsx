import { useState, useCallback, useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import { useGoogleLogin } from '@react-oauth/google'
import { PublicClientApplication } from '@azure/msal-browser'
import * as Dialog from '@radix-ui/react-dialog'
import {
  FileSpreadsheet, ArrowRight,
  Lock,
  CheckCircle2,
  HelpCircle,
  X,
  FileEdit, Table2, FileBarChart, Inbox, Workflow,
} from 'lucide-react'
import { trackEvent } from '@/lib/analytics'
import api from '@/lib/api'
import { useAuthStore } from '@/store/authStore'
import { Button } from '@/components/ui/button'
import { Accordion, AccordionItem, AccordionTrigger, AccordionContent } from '@/components/ui/accordion'

const msalInstance = new PublicClientApplication({
  auth: {
    clientId: import.meta.env.VITE_MICROSOFT_CLIENT_ID || '',
    authority: 'https://login.microsoftonline.com/common',
    redirectUri: window.location.origin,
  },
  cache: { cacheLocation: 'sessionStorage' },
})
const msalRedirectResult = msalInstance.initialize()
  .then(() => msalInstance.handleRedirectPromise())
  .then((result) => {
    if (window.location.hash.includes('state=') || window.location.search.includes('state=')) {
      window.history.replaceState(null, '', `${window.location.pathname}`)
    }
    return result
  })

/* ─── Tool sections ────────────────────────────────────────────────────────── */
const TOOLS = [
  {
    icon: FileEdit,
    title: 'Fill Applications',
    desc: 'Fill carrier intake forms and supplemental apps in seconds. Upload your agency\'s intake form and source documents — AI fills every field on the carrier\'s form automatically. Works with ACORD forms, carrier-specific applications, and any fillable PDF. No more retyping the same data across multiple carriers.',
    bullets: [
      'ACORD forms, carrier apps, and any fillable PDF',
      'Pulls data from your intake forms and source docs automatically',
      'Fill the same submission across multiple carriers in minutes',
      'Handles supplemental applications and carrier forms',
    ],
  },
  {
    icon: Table2,
    title: 'Schedules',
    desc: 'Build every schedule a commercial submission needs — locations, equipment, vehicles, drivers, employees, and more — directly from your source documents and emails. Upload last year\'s schedule as a baseline and GridPull updates it with new information automatically.',
    bullets: [
      'Locations, equipment, vehicles, drivers, employee schedules, and more',
      'Upload last year\'s schedule as a baseline and update it',
      'Extracts data from loss runs, emails, and client documents',
      'Clean Excel output ready to attach to your submission',
    ],
  },
  {
    icon: FileBarChart,
    title: 'Proposals',
    desc: 'Win more renewals with polished, client-ready proposals. Upload carrier quotes and GridPull assembles a branded PDF — complete with coverage analysis, quote comparison tables, and plain-English recommendations — in your agency\'s own colors and logo, ready to send to your insured.',
    bullets: [
      'Upload your logo and brand colors so every proposal looks like it came from your agency',
      'Side-by-side carrier comparisons that make renewal conversations easy',
      'Coverage analysis and recommendations pre-written for your client',
      'Templates sized from small commercial all the way to enterprise accounts',
    ],
  },
  {
    icon: Inbox,
    title: 'Document Inbox',
    desc: 'One private inbox for your whole agency to consolidate the files scattered across your email. Every organization gets its own secure @gridpull.com address — forward any client email or carrier attachment and GridPull automatically organizes the documents by sender, ready to pull into Fill Applications, Schedules, or Proposals in one click. Your inbox is visible only to your team — never to any other GridPull user.',
    bullets: [
      'Your own private inbox address — never shared with another customer',
      'Forward emails from anywhere and attachments land organized by sender',
      'Every teammate in your organization shares the same inbox',
      'Use any file directly inside Fill Applications, Schedules, Proposals, or Pipelines',
    ],
  },
  {
    icon: Workflow,
    title: 'Pipelines',
    desc: 'Automate the recurring document work that eats your week. Connect a folder in Outlook, Box, or Dropbox and GridPull extracts the data from every new file — carrier invoices, loss runs, and claims documents — straight into an Excel file that keeps updating itself.',
    bullets: [
      'Connect any Outlook, Box, or Dropbox folder you already use',
      'New files are processed automatically the moment they arrive',
      'Results accumulate in a single live spreadsheet — no re-uploading',
      'Built for recurring carrier invoices, loss runs, and claims intake',
    ],
  },
]

/* ─── Pricing tiers ────────────────────────────────────────────────────────── */
const PRICING_TIERS = [
  {
    name: 'Free',
    price: '$0',
    period: '',
    desc: 'Try GridPull end-to-end, no commitment',
    features: [
      'No credit card required',
      '100 pages/month',
      'All 5 tools unlocked',
      'Form fill 5 pages · Proposal 25 pages',
    ],
    cta: 'Start free',
    highlight: false,
  },
  {
    name: 'Starter',
    price: '$69',
    period: '/mo',
    desc: 'For solo agents & small agencies',
    features: [
      '800 pages/month',
      'Fill Applications, Schedules, and Document Inbox',
      'Form fill 5 pages each (no proposals)',
      '$0.05/page overage',
    ],
    cta: 'Get started',
    highlight: false,
  },
  {
    name: 'Pro',
    price: '$199',
    period: '/mo',
    desc: 'For growing agencies & teams',
    features: [
      '3,000 pages/month',
      'All 5 tools',
      'Form fill 5 pages · Proposal 25 pages',
      '$0.03/page overage',
    ],
    cta: 'Go Pro',
    highlight: true,
  },
  {
    name: 'Business',
    price: '$699',
    period: '/mo',
    desc: 'For large brokerages & enterprises',
    features: [
      '10,000 pages/month',
      'All 5 tools for your entire team',
      'Form fill 5 pages · Proposal 25 pages',
      '$0.015/page overage',
    ],
    cta: 'Contact us',
    highlight: false,
  },
]

/* ─── FAQ ──────────────────────────────────────────────────────────────────── */
const FAQ_ITEMS = [
  {
    q: 'How much does it cost?',
    a: 'GridPull is free to start with 100 pages per month — no credit card required. When you need more, paid plans start at $69/month for 800 pages. Page costs: each page of an uploaded document is 1 page; each form fill costs 5 pages; each generated proposal costs 25 pages. Every paid plan includes on-demand overage so you\'re never blocked during a busy submission cycle.',
  },
  {
    q: 'Are my files secure?',
    a: 'Yes. Your files are encrypted during upload, processed by AI only (no human ever sees them), and permanently deleted after processing. Your documents are never stored on our servers and are never used to train AI models. We do not share your data with any third party.',
  },
  {
    q: 'What file types are supported?',
    a: 'GridPull works with PDFs (digital and scanned), images (PNG, JPEG), spreadsheets (Excel, CSV), and email files (.eml, .msg). Scanned documents and photos of documents are processed with built-in OCR. If your file contains readable content, GridPull can handle it.',
  },
  {
    q: 'Which types of schedules can GridPull build?',
    a: 'All of them. Schedules of values (locations and buildings), equipment and contractors\' equipment, vehicles, drivers, employees and payroll, property, watercraft, aircraft, leased premises, scheduled personal property — if a carrier asks for it as a supplemental spreadsheet, GridPull can extract it from your source documents and build it.',
  },
  {
    q: 'Can I update last year\'s schedule?',
    a: 'Yes. Upload your existing schedule as a baseline, then add new source documents with updated information. GridPull will merge the new data into your existing schedule — updating values, adding new rows, and keeping everything organized.',
  },
  {
    q: 'My documents are scattered across email threads — how does GridPull help me organize them?',
    a: 'That\'s exactly what the Document Inbox is for. Your organization gets its own private @gridpull.com address — only you and your teammates can see anything that lands there, never any other GridPull user. Forward client emails, carrier attachments, or loss runs to that address and GridPull automatically groups every file by sender so you can pull them straight into Fill Applications, Schedules, Proposals, or Pipelines without digging through Outlook.',
  },
  {
    q: 'How do Pipelines work and how do I set one up?',
    a: 'Pipelines automate repeating document work. Step 1: connect a source folder in Outlook, Box, or Dropbox — the folder where new files (like carrier invoices, loss runs, or claims documents) show up. Step 2: tell GridPull which fields to extract. Step 3: pick a destination folder where GridPull will create or update an Excel file. From then on, whenever a new file lands in the source folder, GridPull extracts the data and appends a row to the Excel file automatically — no uploads, no manual work.',
  },
  {
    q: 'How does the proposal tool work?',
    a: 'Upload one or more carrier quotes, select the line of business and template size, upload your agency\'s logo and brand colors, and GridPull generates a professional, branded PDF proposal. It includes coverage analysis, quote comparison tables across carriers, and customizable recommendations. Each generated proposal counts as 25 pages against your monthly limit.',
  },
  {
    q: 'What forms can be filled?',
    a: 'Any fillable PDF — including ACORD forms, carrier-specific intake forms, supplemental applications, and endorsement forms. Upload the blank form along with your source documents (your agency\'s intake form, prior policies, loss runs, etc.) and GridPull fills every field automatically.',
  },
]

/* ═══════════════════════════════════════════════════════════════════════════════ */
export default function LandingPage() {
  const navigate = useNavigate()
  const { setUser, user } = useAuthStore()
  const [loading, setLoading] = useState(false)
  const [loginError, setLoginError] = useState<string | null>(null)
  const [showProviderDialog, setShowProviderDialog] = useState(false)

  useEffect(() => {
    let cancelled = false
    msalRedirectResult
      .then(async (result) => {
        if (cancelled || !result) return
        setLoading(true)
        trackEvent('login_start', { method: 'microsoft' })
        try {
          const res = await api.post('/auth/microsoft', {
            access_token: result.accessToken,
          })
          setUser(res.data.user, res.data.access_token)
          trackEvent('login_success', { method: 'microsoft' })
          navigate('/form-filling')
        } catch (err: any) {
          const detail = err.response?.data?.detail
          setLoginError(typeof detail === 'string' ? detail : 'Microsoft login failed. Please try again.')
          trackEvent('login_error', { method: 'microsoft', error: 'backend' })
        } finally {
          setLoading(false)
        }
      })
      .catch((err) => {
        if (cancelled) return
        if (err.errorCode === 'no_auth_response') return
        console.error('MSAL redirect error:', err)
        setLoginError(err.errorMessage || 'Microsoft login failed. Please try again.')
        trackEvent('login_error', { method: 'microsoft', error: err.errorCode || 'unknown' })
      })
    return () => { cancelled = true }
  }, [setUser, navigate])

  const googleLogin = useGoogleLogin({
    onSuccess: async (tokenResponse) => {
      setShowProviderDialog(false)
      setLoading(true)
      setLoginError(null)
      trackEvent('login_start', { method: 'google' })
      try {
        const res = await api.post('/auth/google', {
          access_token: tokenResponse.access_token,
        })
        setUser(res.data.user, res.data.access_token)
        trackEvent('login_success', { method: 'google' })
        navigate('/form-filling')
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

  const microsoftLogin = useCallback(async () => {
    setShowProviderDialog(false)
    setLoginError(null)
    trackEvent('login_start', { method: 'microsoft' })
    try {
      await msalRedirectResult
      await msalInstance.loginRedirect({
        scopes: ['User.Read', 'openid', 'profile', 'email'],
      })
    } catch (err: any) {
      console.error('Microsoft login error:', err)
      if (err.errorCode === 'interaction_in_progress') {
        sessionStorage.clear()
        window.location.reload()
        return
      }
      setLoginError('Microsoft login failed. Please try again.')
      trackEvent('login_error', { method: 'microsoft', error: err.errorCode || 'unknown' })
    }
  }, [])

  const openSignIn = useCallback(() => {
    setShowProviderDialog(true)
  }, [])

  if (user) {
    navigate('/form-filling')
    return null
  }

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
      <rect x="1" y="1" width="9" height="9" fill="#F25022"/>
      <rect x="11" y="1" width="9" height="9" fill="#7FBA00"/>
      <rect x="1" y="11" width="9" height="9" fill="#00A4EF"/>
      <rect x="11" y="11" width="9" height="9" fill="#FFB900"/>
    </svg>
  )

  const SignInButton = ({ size = 'xl', label = 'Get started', className = '' }: { size?: 'default' | 'sm' | 'lg' | 'xl' | 'icon'; label?: string; className?: string }) => (
    <Button
      size={size}
      onClick={() => { trackEvent('cta_click', { label, location: 'landing' }); openSignIn() }}
      disabled={loading}
      className={`gap-3 shadow-lg shadow-primary/20 ${className}`}
    >
      {loading ? (
        <div className="w-4 h-4 border-2 border-primary-foreground/30 border-t-white rounded-full animate-spin" />
      ) : (
        label
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
            <span className="font-semibold text-sm tracking-tight">GridPull</span>
          </div>
          <div className="flex items-center gap-4">
            <a href="#tools" className="text-xs text-muted-foreground hover:text-foreground transition-colors hidden sm:block">
              Tools
            </a>
            <a href="#pricing" className="text-xs text-muted-foreground hover:text-foreground transition-colors hidden sm:block">
              Pricing
            </a>
            <a href="#faq" className="text-xs text-muted-foreground hover:text-foreground transition-colors hidden sm:block">
              FAQ
            </a>
            <a href="mailto:info@gridpull.com" className="text-xs text-muted-foreground hover:text-foreground transition-colors hidden md:block">
              Contact
            </a>
            <Button
              variant="outline"
              size="sm"
              onClick={() => { trackEvent('cta_click', { label: 'navbar_sign_in', location: 'header' }); openSignIn() }}
              disabled={loading}
            >
              {loading ? (
                <span className="flex items-center gap-2">
                  <div className="w-3.5 h-3.5 border-2 border-border border-t-foreground rounded-full animate-spin" />
                  Signing in...
                </span>
              ) : (
                <>Try for free <ArrowRight size={13} /></>
              )}
            </Button>
          </div>
        </div>
      </header>

      {/* ── Hero ──────────────────────────────────────────────────────────── */}
      <section className="flex flex-col items-center justify-center px-4 sm:px-6 py-8 sm:pt-4 sm:pb-20 text-center relative overflow-hidden">
        <div className="absolute inset-0 flex items-center justify-center pointer-events-none">
          <div className="w-[700px] h-[500px] bg-primary/5 rounded-full blur-3xl" />
        </div>
        <div className="absolute top-0 right-0 w-[400px] h-[300px] bg-blue-200/20 rounded-full blur-3xl pointer-events-none" />
        <div className="absolute bottom-0 left-0 w-[300px] h-[300px] bg-violet-200/10 rounded-full blur-3xl pointer-events-none" />

        <div className="relative max-w-3xl mx-auto">
          <h1 className="text-3xl sm:text-5xl md:text-6xl font-bold tracking-tight mb-6 leading-[1.1]">
            Everything your agency and brokerage needs to{' '}
            <br className="hidden sm:block" />
            <span className="text-primary">move submissions and renewals faster</span>
          </h1>

          <p className="text-muted-foreground text-base sm:text-lg mb-4 max-w-2xl mx-auto leading-relaxed">
            Stop retyping carrier forms, building schedules by hand, and formatting proposals from scratch.
            GridPull's five AI-powered tools turn hours of manual work into seconds.
          </p>

          <p className="text-muted-foreground text-sm mb-6 sm:mb-10 max-w-xl mx-auto">
            Doc Extraction and Automated Pipelines for Fill Applications, Schedules, Proposals, and a Document Inbox.
          </p>

          <div className="flex flex-col items-center gap-3">
            <SignInButton label="Start free" className="min-w-0 sm:min-w-[280px] w-full sm:w-auto" />
            {loginError && (
              <p className="text-sm text-red-500 bg-red-50 border border-red-200 rounded-lg px-4 py-2 max-w-sm text-center">
                {loginError}
              </p>
            )}
            <p className="text-sm font-medium text-foreground flex items-center justify-center gap-1.5">
              <CheckCircle2 size={14} className="text-emerald-500" />
              No credit card required
            </p>
            <p className="text-xs text-muted-foreground max-w-xl mx-auto leading-relaxed">
              100 free pages/month  ·  Sign in and start uploading in seconds.
            </p>
            <p className="text-xs text-muted-foreground flex items-center justify-center gap-1.5">
              <Lock size={10} />
              Your files are encrypted and deleted after processing
            </p>
          </div>
        </div>
      </section>

      {/* ── Stats strip ───────────────────────────────────────────────────── */}
      <section className="border-y border-border/50 bg-card/50 py-6 sm:py-8 px-4 sm:px-6">
        <div className="max-w-4xl mx-auto grid grid-cols-2 sm:grid-cols-4 gap-6 sm:gap-8">
          <div className="text-center">
            <div className="text-2xl sm:text-3xl font-bold text-primary mb-1">28</div>
            <div className="text-xs text-muted-foreground">Lines of business</div>
          </div>
          <div className="text-center">
            <div className="text-2xl sm:text-3xl font-bold text-primary mb-1">5 Tools</div>
            <div className="text-xs text-muted-foreground">One platform for submissions</div>
          </div>
          <div className="text-center">
            <div className="text-2xl sm:text-3xl font-bold text-primary mb-1">Any File</div>
            <div className="text-xs text-muted-foreground">PDFs, scans, images, emails</div>
          </div>
          <div className="text-center">
            <div className="text-2xl sm:text-3xl font-bold text-primary mb-1">Seconds</div>
            <div className="text-xs text-muted-foreground">Not hours of data entry</div>
          </div>
        </div>
      </section>

      {/* ── Use cases strip ──────────────────────────────────────────────── */}
      <section className="py-8 sm:py-10 px-4 sm:px-6 bg-primary/[0.02]">
        <div className="max-w-4xl mx-auto">
          <p className="text-center text-xs font-semibold uppercase tracking-widest text-muted-foreground mb-5">
            Built for the way agencies actually work
          </p>
          <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
            <div className="bg-white border border-border/60 rounded-lg px-4 py-3 text-center">
              <p className="text-sm font-medium text-foreground mb-0.5">Renewal processing</p>
              <p className="text-xs text-muted-foreground">Update last year's schedules and re-fill applications automatically</p>
            </div>
            <div className="bg-white border border-border/60 rounded-lg px-4 py-3 text-center">
              <p className="text-sm font-medium text-foreground mb-0.5">New business submissions</p>
              <p className="text-xs text-muted-foreground">Fill carrier forms and build schedules from your intake data</p>
            </div>
            <div className="bg-white border border-border/60 rounded-lg px-4 py-3 text-center">
              <p className="text-sm font-medium text-foreground mb-0.5">Client presentations</p>
              <p className="text-xs text-muted-foreground">Generate branded proposals with coverage analysis and comparisons</p>
            </div>
          </div>
        </div>
      </section>

      {/* ── Tools ─────────────────────────────────────────────────────────── */}
      <section id="tools" className="py-12 sm:py-20 px-4 sm:px-6 scroll-mt-16">
        <div className="max-w-5xl mx-auto">
          <p className="text-center text-xs font-semibold uppercase tracking-widest text-muted-foreground mb-3">
            Five tools, one platform
          </p>
          <h2 className="text-2xl sm:text-3xl font-bold text-center tracking-tight mb-4">
            Everything your agency and brokerage needs to move faster
          </h2>
          <p className="text-center text-muted-foreground text-sm mb-12 max-w-lg mx-auto">
            Each tool is purpose-built for insurance workflows. Upload your documents and let AI handle the repetitive work.
          </p>

          <div className="space-y-6">
            {TOOLS.map((tool, i) => (
              <div
                key={tool.title}
                className={`bg-card border border-border rounded-xl p-6 sm:p-8 hover:border-primary/30 hover:shadow-sm transition-all ${
                  i % 2 === 0 ? '' : ''
                }`}
              >
                <div className="flex flex-col sm:flex-row gap-6">
                  <div className="flex-shrink-0">
                    <div className="w-11 h-11 bg-primary/10 rounded-lg flex items-center justify-center">
                      <tool.icon size={20} className="text-primary" />
                    </div>
                  </div>
                  <div className="flex-1">
                    <h3 className="font-semibold text-lg mb-2">{tool.title}</h3>
                    <p className="text-muted-foreground text-sm leading-relaxed mb-4">{tool.desc}</p>
                    <ul className="grid sm:grid-cols-2 gap-2">
                      {tool.bullets.map((bullet) => (
                        <li key={bullet} className="flex items-start gap-2 text-sm text-muted-foreground">
                          <CheckCircle2 size={14} className="text-emerald-500 flex-shrink-0 mt-0.5" />
                          {bullet}
                        </li>
                      ))}
                    </ul>
                  </div>
                </div>
              </div>
            ))}
          </div>

          <div className="flex flex-col items-center gap-2 mt-10">
            <SignInButton size="xl" label="Try all 5 tools free" className="min-w-0 sm:min-w-[260px] w-full sm:w-auto" />
            <p className="text-sm font-medium text-foreground flex items-center justify-center gap-1.5">
              <CheckCircle2 size={14} className="text-emerald-500" />
              No credit card required
            </p>
          </div>
        </div>
      </section>

      {/* ── Pricing ───────────────────────────────────────────────────────── */}
      <section id="pricing" className="py-12 sm:py-20 px-4 sm:px-6 border-t border-border/50 scroll-mt-16">
        <div className="max-w-5xl mx-auto">
          <p className="text-center text-xs font-semibold uppercase tracking-widest text-muted-foreground mb-3">
            Simple pricing
          </p>
          <h2 className="text-2xl sm:text-3xl font-bold text-center tracking-tight mb-4">
            Plans that scale with your agency
          </h2>
          <p className="text-center text-muted-foreground text-sm mb-4 max-w-lg mx-auto">
            Start free with 100 pages/month. From solo agents to large brokerages, scale with your business.
          </p>
          <p className="text-center text-primary text-sm font-semibold mb-4">
            Process thousands of pages for a fraction of the cost of manual data entry.
          </p>
          <div className="flex items-center justify-center mb-12">
            <span className="inline-flex items-center gap-1.5 text-sm font-medium text-foreground bg-emerald-50 border border-emerald-200 rounded-full px-3 py-1">
              <CheckCircle2 size={14} className="text-emerald-500" />
              No credit card required to start
            </span>
          </div>

          <div className="grid sm:grid-cols-2 lg:grid-cols-4 gap-5 mb-10 items-stretch">
            {PRICING_TIERS.map((tier) => (
              <div key={tier.name} className="flex flex-col">
                <div className="h-6 mb-1 flex items-center justify-center">
                  {tier.highlight && (
                    <span className="text-[10px] font-semibold uppercase tracking-wider text-primary bg-primary/10 border border-primary/30 rounded-full px-2.5 py-0.5">
                      Most popular
                    </span>
                  )}
                </div>
                <div
                  className={`flex-1 bg-card border rounded-xl p-5 text-center transition-all hover:shadow-sm flex flex-col ${
                    tier.highlight
                      ? 'border-primary shadow-md ring-1 ring-primary/20'
                      : 'border-border hover:border-primary/30'
                  }`}
                >
                  <p className="text-sm font-semibold mb-1">{tier.name}</p>
                  <p className="text-3xl font-bold text-primary mb-0.5">
                    {tier.price}
                    <span className="text-sm font-normal text-muted-foreground">{tier.period}</span>
                  </p>
                  <p className="text-xs text-muted-foreground mb-4">{tier.desc}</p>
                  <div className="border-t border-border/50 pt-3 space-y-2 text-left flex-1">
                    {tier.features.map((f) => (
                      <div key={f} className="flex items-start gap-2 text-xs">
                        <CheckCircle2 size={13} className="text-primary mt-0.5 flex-shrink-0" />
                        <span>{f}</span>
                      </div>
                    ))}
                  </div>
                </div>
              </div>
            ))}
          </div>

          <div className="flex flex-col items-center text-center">
            <p className="text-xs text-muted-foreground mb-2">
              Each page of your document counts toward your monthly limit. Form fills cost 5 pages; proposals cost 25 pages. Max upload size is 5 MB per file.
            </p>
            <p className="text-xs text-muted-foreground mb-5">
              Every plan is purpose-built for insurance workflows — ACORD forms, commercial schedules, loss runs, carrier quotes, and claims documents, all in one platform. No contracts — cancel anytime.
            </p>
            <SignInButton size="xl" label="Start free — 100 pages/month" className="min-w-0 sm:min-w-[280px] w-full sm:w-auto" />
            <p className="mt-2 text-sm font-medium text-foreground flex items-center justify-center gap-1.5">
              <CheckCircle2 size={14} className="text-emerald-500" />
              No credit card required
            </p>
          </div>
        </div>
      </section>

      {/* ── FAQ ───────────────────────────────────────────────────────────── */}
      <section id="faq" className="py-12 sm:py-20 px-4 sm:px-6 border-t border-border/50 bg-card/30 scroll-mt-16">
        <div className="max-w-3xl mx-auto">
          <p className="text-center text-xs font-semibold uppercase tracking-widest text-muted-foreground mb-3">
            Frequently asked questions
          </p>
          <h2 className="text-2xl sm:text-3xl font-bold text-center tracking-tight mb-12">
            Common questions from agencies and brokers
          </h2>

          <Accordion
            type="single"
            collapsible
            className="space-y-2"
            onValueChange={(value) => {
              if (!value) return
              const idx = Number(value.replace('faq-', ''))
              const item = FAQ_ITEMS[idx]
              if (item) trackEvent('faq_expand', { question: item.q })
            }}
          >
            {FAQ_ITEMS.map((item, i) => (
              <AccordionItem key={i} value={`faq-${i}`}>
                <AccordionTrigger>
                  <span className="flex items-center gap-2.5 pr-4">
                    <HelpCircle size={14} className="text-primary flex-shrink-0" />
                    {item.q}
                  </span>
                </AccordionTrigger>
                <AccordionContent>
                  <p className="text-sm text-muted-foreground leading-relaxed pl-[26px]">
                    {item.a}
                  </p>
                </AccordionContent>
              </AccordionItem>
            ))}
          </Accordion>

          <div className="flex flex-col items-center gap-2 mt-10">
            <SignInButton size="xl" label="Get started for free" className="min-w-0 sm:min-w-[240px] w-full sm:w-auto" />
            <p className="text-sm font-medium text-foreground flex items-center justify-center gap-1.5">
              <CheckCircle2 size={14} className="text-emerald-500" />
              No credit card required
            </p>
          </div>
        </div>
      </section>

      {/* ── Footer ────────────────────────────────────────────────────────── */}
      <footer className="border-t border-border/50 py-6 px-4 sm:px-6">
        <div className="max-w-6xl mx-auto flex flex-col items-center gap-3 text-xs text-muted-foreground">
          <div className="flex items-center gap-2">
            <div className="w-5 h-5 bg-primary rounded-md flex items-center justify-center">
              <FileSpreadsheet size={11} className="text-white" />
            </div>
            GridPull
          </div>
          <div className="flex flex-wrap items-center justify-center gap-x-4 gap-y-1">
            <a href="/privacy" className="hover:text-foreground transition-colors">Privacy Policy</a>
            <a href="/terms" className="hover:text-foreground transition-colors">Terms &amp; Conditions</a>
            <a href="/resources" className="hover:text-foreground transition-colors">Resources</a>
            <a href="#faq" className="hover:text-foreground transition-colors">FAQ</a>
            <a href="mailto:info@gridpull.com" className="hover:text-foreground transition-colors">Contact</a>
          </div>
          <span>&copy; 2026 Big Vision Systems LLC. All rights reserved.</span>
        </div>
      </footer>

      {/* ── Sign-in provider chooser ──────────────────────────────────────── */}
      <Dialog.Root open={showProviderDialog} onOpenChange={setShowProviderDialog}>
        <Dialog.Portal>
          <Dialog.Overlay className="fixed inset-0 z-50 bg-black/50 backdrop-blur-sm data-[state=open]:animate-in data-[state=closed]:animate-out data-[state=closed]:fade-out-0 data-[state=open]:fade-in-0" />
          <Dialog.Content className="fixed left-1/2 top-1/2 z-50 w-full max-w-sm -translate-x-1/2 -translate-y-1/2 rounded-xl border border-border bg-background p-6 shadow-2xl data-[state=open]:animate-in data-[state=closed]:animate-out data-[state=closed]:fade-out-0 data-[state=open]:fade-in-0 data-[state=closed]:zoom-out-95 data-[state=open]:zoom-in-95 data-[state=closed]:slide-out-to-left-1/2 data-[state=closed]:slide-out-to-top-[48%] data-[state=open]:slide-in-from-left-1/2 data-[state=open]:slide-in-from-top-[48%]">
            <div className="flex items-center justify-between mb-2">
              <Dialog.Title className="text-lg font-semibold">Sign in to continue</Dialog.Title>
              <Dialog.Close className="rounded-full p-1 hover:bg-muted transition-colors">
                <X size={16} />
              </Dialog.Close>
            </div>
            <p className="mb-5 text-xs font-medium text-foreground flex items-center gap-1.5">
              <CheckCircle2 size={13} className="text-emerald-500" />
              No credit card required — 100 free pages/month
            </p>

            <div className="flex flex-col gap-3">
              <button
                onClick={() => { trackEvent('provider_select', { provider: 'google' }); googleLogin() }}
                disabled={loading}
                className="flex items-center gap-3 w-full rounded-lg border border-border px-4 py-3 text-sm font-medium hover:bg-muted/50 transition-colors disabled:opacity-50"
              >
                <GoogleIcon />
                Continue with Google
              </button>

              <button
                onClick={() => { trackEvent('provider_select', { provider: 'microsoft' }); microsoftLogin() }}
                disabled={loading}
                className="flex items-center gap-3 w-full rounded-lg border border-border px-4 py-3 text-sm font-medium hover:bg-muted/50 transition-colors disabled:opacity-50"
              >
                <MicrosoftIcon />
                Continue with Microsoft
              </button>
            </div>

            {loginError && (
              <p className="mt-4 text-sm text-red-500 text-center">{loginError}</p>
            )}

            <p className="mt-5 text-xs text-muted-foreground text-center">
              By signing in, you agree to our{' '}
              <a href="/terms" className="underline hover:text-foreground">Terms</a> and{' '}
              <a href="/privacy" className="underline hover:text-foreground">Privacy Policy</a>.
            </p>
          </Dialog.Content>
        </Dialog.Portal>
      </Dialog.Root>
    </div>
  )
}
