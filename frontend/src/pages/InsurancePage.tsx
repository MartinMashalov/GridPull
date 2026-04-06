import { useNavigate } from 'react-router-dom'
import { useCallback, useState, useEffect } from 'react'
import { useGoogleLogin } from '@react-oauth/google'
import { PublicClientApplication } from '@azure/msal-browser'
import * as Dialog from '@radix-ui/react-dialog'
import {
  FileSpreadsheet, ArrowRight, ArrowLeft, Lock, Mail,
  CheckCircle2, ShieldCheck, FileText, ClipboardList,
  Building2, Users, Briefcase, FileCheck, FormInput, Layers,
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
    icon: Briefcase,
    title: 'Commercial Submissions',
    color: 'bg-blue-500/10 text-blue-600',
    desc: 'Intake and process commercial insurance submissions at scale. Extract insured names, business descriptions, coverage requests, policy limits, deductibles, and loss history from ACORD forms, broker submissions, and supplemental applications — regardless of format or carrier.',
    fields: ['Insured Name', 'Business Description', 'Coverage Type', 'Requested Limits', 'Deductible', 'Loss History', 'Effective Date', 'Premium Indication'],
  },
  {
    icon: Layers,
    title: 'Statements of Values & Property Schedules',
    color: 'bg-violet-500/10 text-violet-600',
    desc: 'GridPull has a dedicated SOV extraction pipeline — it automatically detects property schedule layouts and routes them to a specialized engine. Upload multi-location SOVs with dozens or hundreds of rows and get every location extracted with address, construction class, occupancy, year built, building value, contents/BPP, business income, TIV, sprinkler status, and protection class.',
    fields: ['Location Number', 'Address', 'City', 'State', 'ZIP Code', 'Construction Class', 'Occupancy', 'Year Built', 'Sq Ft', 'Sprinklered', 'Protection Class', 'Building Value', 'Contents/BPP', 'Business Income', 'Total Insured Value'],
  },
  {
    icon: Users,
    title: 'Retail Insurance Brokers',
    color: 'bg-emerald-500/10 text-emerald-600',
    desc: 'Retail brokers juggle client applications, quotes, and policy documents from multiple carriers. Extract key policy details, premium comparisons, coverage terms, and endorsement data to build side-by-side comparison spreadsheets for clients — in minutes instead of hours.',
    fields: ['Carrier Name', 'Policy Number', 'Coverage Limits', 'Annual Premium', 'Endorsements', 'Exclusions', 'Renewal Date', 'Commission Rate'],
  },
  {
    icon: Building2,
    title: 'Commercial Insurance Brokerages',
    color: 'bg-orange-500/10 text-orange-600',
    desc: 'Large commercial brokerages process hundreds of submissions, quotes, and binders weekly. Automate the extraction of submission data, loss runs, financial statements, and SOVs (Statements of Values) into structured spreadsheets that feed directly into your management system.',
    fields: ['Named Insured', 'TIV (Total Insured Value)', 'Revenue', 'Employee Count', 'Claims History', 'SIC/NAICS Code', 'Broker of Record', 'Binding Authority'],
  },
  {
    icon: FormInput,
    title: 'Supplemental Applications & Form Filling',
    color: 'bg-pink-500/10 text-pink-600',
    desc: 'GridPull has a dedicated form-filling feature built for the commercial applications process. Upload your source documents (submissions, applications, loss runs) alongside a target PDF form — ACORD supplements, carrier-specific questionnaires, or any fillable PDF — and GridPull reads the source data and auto-populates every field in the target form. Supports text fields, checkboxes, dropdowns, and radio buttons.',
    fields: ['Auto-fills text fields from source docs', 'Handles checkboxes (Yes/No)', 'Populates dropdown selections', 'Reads scanned PDFs, images & text files', 'Works with any fillable PDF form', 'Downloads completed PDF instantly'],
  },
  {
    icon: FileCheck,
    title: 'Carrier Intake Forms & ACORD Forms',
    color: 'bg-teal-500/10 text-teal-600',
    desc: 'Use GridPull\'s form-filling feature to auto-populate carrier intake forms and ACORD applications. Upload the blank carrier form as the target, attach your client\'s submission documents as source files, and get a completed PDF back — with every text field, checkbox, and dropdown filled from your source data. No manual re-keying between carrier portals.',
    fields: ['Auto-populates ACORD 125, 126, 130, 140+', 'Fills carrier-specific intake PDFs', 'Reads from any source format (PDF, images, text)', 'Handles multi-source document merging', 'Returns downloadable filled PDF', 'Works with any fillable PDF form'],
  },
]

export default function InsurancePage() {
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
        setUser(res.data.user, res.data.access_token)
        navigate('/dashboard')
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
    <Button size={size} onClick={() => { trackEvent('cta_click', { label, location: 'insurance' }); setShowProviderDialog(true) }} disabled={loading} className={`gap-3 shadow-lg shadow-primary/20 ${className}`}>
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
          <div className="w-[700px] h-[500px] bg-blue-500/5 rounded-full blur-3xl" />
        </div>

        <div className="relative max-w-3xl mx-auto">
          <Badge variant="outline" className="mb-4 sm:mb-6 gap-1.5 px-3 py-1 text-xs font-medium">
            <ShieldCheck size={10} />
            Insurance Document Processing
          </Badge>

          <h1 className="text-3xl sm:text-5xl md:text-6xl font-bold tracking-tight mb-6 leading-[1.1]">
            Extract data from insurance documents{' '}
            <br className="hidden sm:block" />
            <span className="text-primary">into clean spreadsheets</span>
          </h1>

          <p className="text-muted-foreground text-base sm:text-lg mb-4 max-w-2xl mx-auto leading-relaxed">
            Upload ACORD forms, carrier submissions, loss runs, schedules, supplemental applications, and intake forms.
            GridPull extracts the fields you need into structured Excel files — no templates, no manual entry.
          </p>

          <p className="text-muted-foreground text-sm mb-6 sm:mb-10 max-w-xl mx-auto">
            Built for insurance agencies, brokerages, and MGAs who process hundreds of documents weekly.
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
            Insurance Use Cases
          </p>
          <h2 className="text-2xl sm:text-3xl font-bold text-center tracking-tight mb-4">
            Every document type your agency handles
          </h2>
          <p className="text-center text-muted-foreground text-sm mb-12 max-w-lg mx-auto">
            From commercial submissions to carrier intake forms — GridPull handles the document types
            that insurance professionals deal with every day.
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

      {/* Purpose-built insurance features */}
      <section className="py-12 sm:py-20 px-4 sm:px-6 border-t border-border/50">
        <div className="max-w-5xl mx-auto">
          <p className="text-center text-xs font-semibold uppercase tracking-widest text-muted-foreground mb-3">
            Purpose-built features
          </p>
          <h2 className="text-2xl sm:text-3xl font-bold text-center tracking-tight mb-4">
            Not a generic PDF tool — built for insurance workflows
          </h2>
          <p className="text-center text-muted-foreground text-sm mb-12 max-w-lg mx-auto">
            GridPull includes dedicated features for the document types insurance teams handle every day.
          </p>

          <div className="grid sm:grid-cols-2 gap-5">
            {/* SOV Pipeline */}
            <div className="bg-card border border-border rounded-xl p-6 hover:border-primary/30 hover:shadow-sm transition-all">
              <div className="flex items-center gap-2 mb-4">
                <div className="w-9 h-9 bg-violet-500/10 rounded-lg flex items-center justify-center">
                  <Layers size={17} className="text-violet-600" />
                </div>
                <span className="text-xs font-bold text-violet-600 uppercase tracking-wider">Dedicated Pipeline</span>
              </div>
              <h3 className="font-semibold text-sm mb-2">Statement of Values Extraction</h3>
              <p className="text-muted-foreground text-xs leading-relaxed mb-4">
                GridPull automatically detects SOV-style property schedules and routes them to a specialized extraction engine. It uses Mistral OCR for high-fidelity page reading, then an AI section selector identifies the schedule pages — dropping cover pages, endorsements, and narrative — before extracting every location row with full field coverage.
              </p>
              <div className="space-y-1.5">
                {['Auto-detects SOV field schemas', 'Intelligent page selection (drops non-schedule pages)', 'Handles 100+ location schedules', 'Pre-built fields: Location, Address, Construction, TIV, etc.', 'Automatic retry if fill rate is low'].map((item) => (
                  <div key={item} className="flex items-center gap-2 text-xs text-muted-foreground">
                    <CheckCircle2 size={12} className="text-emerald-500 flex-shrink-0" />
                    {item}
                  </div>
                ))}
              </div>
            </div>

            {/* Form Filling */}
            <div className="bg-card border border-border rounded-xl p-6 hover:border-primary/30 hover:shadow-sm transition-all">
              <div className="flex items-center gap-2 mb-4">
                <div className="w-9 h-9 bg-pink-500/10 rounded-lg flex items-center justify-center">
                  <FormInput size={17} className="text-pink-600" />
                </div>
                <span className="text-xs font-bold text-pink-600 uppercase tracking-wider">Form Filling</span>
              </div>
              <h3 className="font-semibold text-sm mb-2">Auto-Fill ACORD Forms & Carrier PDFs</h3>
              <p className="text-muted-foreground text-xs leading-relaxed mb-4">
                Upload a blank fillable PDF form (ACORD applications, carrier supplements, intake questionnaires) as the target, then attach your source documents — submissions, applications, loss runs, even scanned paperwork or photos. GridPull OCRs the source documents, reads every form field in the target, and auto-populates the completed PDF for download.
              </p>
              <div className="space-y-1.5">
                {['Fills text fields, checkboxes, dropdowns & radio buttons', 'Reads source PDFs, scanned docs, images & text files', 'Multi-source: combine data from multiple documents', 'Works with any fillable PDF (ACORD, carrier-specific, custom)', 'Returns a downloadable filled PDF instantly'].map((item) => (
                  <div key={item} className="flex items-center gap-2 text-xs text-muted-foreground">
                    <CheckCircle2 size={12} className="text-emerald-500 flex-shrink-0" />
                    {item}
                  </div>
                ))}
              </div>
            </div>

            {/* Automated Pipelines */}
            <div className="bg-card border border-border rounded-xl p-6 hover:border-primary/30 hover:shadow-sm transition-all">
              <div className="flex items-center gap-2 mb-4">
                <div className="w-9 h-9 bg-blue-500/10 rounded-lg flex items-center justify-center">
                  <ClipboardList size={17} className="text-blue-600" />
                </div>
                <span className="text-xs font-bold text-blue-600 uppercase tracking-wider">Automation</span>
              </div>
              <h3 className="font-semibold text-sm mb-2">Pipeline Automation for Ongoing Workflows</h3>
              <p className="text-muted-foreground text-xs leading-relaxed mb-4">
                Connect a Google Drive, SharePoint, or Outlook folder where submissions land. Define your extraction fields once, and GridPull automatically processes every new document — delivering structured spreadsheets to your output folder around the clock.
              </p>
              <div className="space-y-1.5">
                {['Google Drive, SharePoint, Outlook, Dropbox, Box', 'Auto-detects new files in watched folders', 'Define extraction fields once, reuse forever', 'Structured output delivered to your destination folder'].map((item) => (
                  <div key={item} className="flex items-center gap-2 text-xs text-muted-foreground">
                    <CheckCircle2 size={12} className="text-emerald-500 flex-shrink-0" />
                    {item}
                  </div>
                ))}
              </div>
            </div>

            {/* Accuracy & OCR */}
            <div className="bg-card border border-border rounded-xl p-6 hover:border-primary/30 hover:shadow-sm transition-all">
              <div className="flex items-center gap-2 mb-4">
                <div className="w-9 h-9 bg-emerald-500/10 rounded-lg flex items-center justify-center">
                  <ShieldCheck size={17} className="text-emerald-600" />
                </div>
                <span className="text-xs font-bold text-emerald-600 uppercase tracking-wider">Accuracy</span>
              </div>
              <h3 className="font-semibold text-sm mb-2">99%+ Accuracy on Real Insurance Documents</h3>
              <p className="text-muted-foreground text-xs leading-relaxed mb-4">
                Multi-stage extraction pipeline: Mistral OCR for page reading, layout analysis for table detection, AI field extraction with validation, and post-processing cleanup. Handles scanned ACORD forms, photographed documents, and inconsistent carrier formats.
              </p>
              <div className="space-y-1.5">
                {['Mistral OCR for scanned & photo documents', 'Table detection across multi-page layouts', 'Field validation and cleanup passes', 'Handles inconsistent carrier formats and layouts'].map((item) => (
                  <div key={item} className="flex items-center gap-2 text-xs text-muted-foreground">
                    <CheckCircle2 size={12} className="text-emerald-500 flex-shrink-0" />
                    {item}
                  </div>
                ))}
              </div>
            </div>
          </div>
        </div>
      </section>

      {/* How it works for insurance */}
      <section className="py-12 sm:py-20 px-4 sm:px-6 border-t border-border/50 bg-card/30">
        <div className="max-w-4xl mx-auto">
          <h2 className="text-2xl sm:text-3xl font-bold text-center tracking-tight mb-4">
            How it works
          </h2>
          <p className="text-center text-muted-foreground text-sm mb-12 max-w-lg mx-auto">
            Two workflows — extract data into spreadsheets, or auto-fill PDF forms.
          </p>

          <div className="grid sm:grid-cols-2 gap-8">
            {/* Extract to Spreadsheet */}
            <div>
              <h3 className="font-semibold text-sm mb-4 flex items-center gap-2">
                <FileSpreadsheet size={16} className="text-primary" /> Extract to Spreadsheet
              </h3>
              <div className="space-y-4">
                {[
                  { step: '1', title: 'Upload insurance documents', desc: 'Drag and drop SOVs, submissions, loss runs, schedules, or any insurance PDF. Handles scanned documents and photos.' },
                  { step: '2', title: 'Pick fields or use SOV preset', desc: 'Select the SOV template for property schedules (15 pre-configured fields), or type any custom fields you need.' },
                  { step: '3', title: 'Download your spreadsheet', desc: 'Get a clean Excel file — one row per location/document, one column per field. Ready for your management system.' },
                ].map((s) => (
                  <div key={s.step} className="flex gap-3">
                    <div className="w-6 h-6 bg-primary/10 rounded-full flex items-center justify-center flex-shrink-0 mt-0.5">
                      <span className="text-[10px] font-bold text-primary">{s.step}</span>
                    </div>
                    <div>
                      <h4 className="text-xs font-semibold mb-0.5">{s.title}</h4>
                      <p className="text-muted-foreground text-xs leading-relaxed">{s.desc}</p>
                    </div>
                  </div>
                ))}
              </div>
            </div>

            {/* Fill PDF Forms */}
            <div>
              <h3 className="font-semibold text-sm mb-4 flex items-center gap-2">
                <FormInput size={16} className="text-pink-600" /> Fill PDF Forms
              </h3>
              <div className="space-y-4">
                {[
                  { step: '1', title: 'Upload the blank target form', desc: 'Drop in an ACORD form, carrier supplement, or any fillable PDF as the target.' },
                  { step: '2', title: 'Attach source documents', desc: 'Add the client\'s submission, application, loss runs, or any supporting docs. PDFs, images, and text files all work.' },
                  { step: '3', title: 'Download the filled PDF', desc: 'GridPull reads the source docs, maps data to every form field, and returns a completed PDF — text fields, checkboxes, and dropdowns all filled.' },
                ].map((s) => (
                  <div key={s.step} className="flex gap-3">
                    <div className="w-6 h-6 bg-pink-500/10 rounded-full flex items-center justify-center flex-shrink-0 mt-0.5">
                      <span className="text-[10px] font-bold text-pink-600">{s.step}</span>
                    </div>
                    <div>
                      <h4 className="text-xs font-semibold mb-0.5">{s.title}</h4>
                      <p className="text-muted-foreground text-xs leading-relaxed">{s.desc}</p>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          </div>

          <div className="text-center mt-10">
            <SignInButton size="xl" label="Try it free with your insurance documents" className="min-w-0 sm:min-w-[340px] w-full sm:w-auto" />
          </div>
        </div>
      </section>

      {/* Testimonial */}
      <section className="py-12 sm:py-20 px-4 sm:px-6 border-t border-border/50 bg-card/30">
        <div className="max-w-3xl mx-auto text-center">
          <p className="text-sm text-muted-foreground italic leading-relaxed mb-4">
            "We process thousands of EOBs monthly from different insurers. The extraction accuracy is remarkable — even on scanned forms with poor print quality. Game changer for our reconciliation workflow."
          </p>
          <p className="text-sm font-semibold">Maria Rodriguez</p>
          <p className="text-xs text-muted-foreground">Insurance Operations Lead · Pacific Health Partners</p>
        </div>
      </section>

      {/* CTA */}
      <section className="py-12 sm:py-16 px-4 sm:px-6 border-t border-border/50 bg-primary/5">
        <div className="max-w-2xl mx-auto text-center">
          <h2 className="text-2xl font-bold tracking-tight mb-3">
            Stop re-keying insurance data by hand
          </h2>
          <p className="text-muted-foreground text-sm mb-3">
            Upload your first insurance document and see structured results in seconds.
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
