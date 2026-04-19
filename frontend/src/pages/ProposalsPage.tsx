import { useState, useCallback, useEffect, useRef } from 'react'
import { useNavigate } from 'react-router-dom'
import { useDropzone } from 'react-dropzone'
import {
  FileText, Upload, Loader2, Download, X, Sparkles, Lock, Crown, ArrowRight, CheckCircle2,
  Image as ImageIcon, Save,
} from 'lucide-react'
import api from '@/lib/api'
import { useAuthStore } from '@/store/authStore'
import { Button } from '@/components/ui/button'
import { Label } from '@/components/ui/label'
import UsagePill from '@/components/UsagePill'
import CreditCardBanner from '@/components/CreditCardBanner'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import { cn } from '@/lib/utils'
import toast from 'react-hot-toast'

const LOB_OPTIONS: { value: string; label: string }[] = [
  { value: 'commercial_general_liability', label: 'Commercial General Liability' },
  { value: 'commercial_property', label: 'Commercial Property' },
  { value: 'business_auto', label: 'Business Auto' },
  { value: 'workers_compensation', label: "Workers' Compensation" },
  { value: 'commercial_umbrella', label: 'Commercial Umbrella' },
  { value: 'business_owners', label: 'Business Owners Policy (BOP)' },
  { value: 'cyber', label: 'Cyber Liability' },
  { value: 'directors_officers', label: 'Directors & Officers (D&O)' },
  { value: 'epli', label: 'Employment Practices Liability (EPLI)' },
  { value: 'professional_liability', label: 'Professional Liability (E&O)' },
  { value: 'crime', label: 'Crime' },
  { value: 'commercial_inland_marine', label: 'Commercial Inland Marine' },
  { value: 'builders_risk', label: 'Builders Risk' },
  { value: 'flood', label: 'Flood' },
  { value: 'garage_dealers', label: 'Garage & Dealers' },
  { value: 'transportation', label: 'Transportation' },
  { value: 'motor_truck_cargo', label: 'Motor Truck Cargo' },
  { value: 'installation', label: 'Installation Floater' },
  { value: 'valuable_papers', label: 'Valuable Papers' },
  { value: 'personal_auto', label: 'Personal Auto' },
  { value: 'homeowners', label: 'Homeowners' },
  { value: 'personal_umbrella', label: 'Personal Umbrella' },
  { value: 'personal_inland_marine', label: 'Personal Inland Marine' },
  { value: 'dwelling_fire', label: 'Dwelling Fire' },
  { value: 'mobile_homeowners', label: 'Mobile Homeowners' },
  { value: 'motorcycle', label: 'Motorcycle' },
  { value: 'watercraft', label: 'Watercraft' },
  { value: 'small_farm_ranch', label: 'Small Farm & Ranch' },
  { value: 'accounts_receivable', label: 'Accounts Receivable' },
]

function formatBytes(bytes: number) {
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(0)} KB`
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`
}

const PROPOSAL_TIERS = new Set(['free', 'pro', 'business'])

export default function ProposalsPage() {
  const { user } = useAuthStore()
  const navigate = useNavigate()
  const userTier = user?.subscription_tier || 'free'
  const hasAccess = PROPOSAL_TIERS.has(userTier)

  const [lob, setLob] = useState(LOB_OPTIONS[0].value)
  const [clientSize, setClientSize] = useState<'small_business' | 'enterprise'>('small_business')
  const [agencyInfo, setAgencyInfo] = useState('')
  const [brandPrimary, setBrandPrimary] = useState('#1A3560')
  const [brandAccent, setBrandAccent] = useState('#C9901E')
  const [files, setFiles] = useState<File[]>([])
  const [generating, setGenerating] = useState(false)
  const [pdfBase64, setPdfBase64] = useState<string | null>(null)
  const [proposalFilename, setProposalFilename] = useState('proposal.pdf')

  // Agency logo state (matches Papyra's picker UX)
  const logoInputRef = useRef<HTMLInputElement>(null)
  const [logoFile, setLogoFile] = useState<File | null>(null)
  const [logoPreviewUrl, setLogoPreviewUrl] = useState<string | null>(null)
  const [savedLogoFilename, setSavedLogoFilename] = useState<string | null>(null)
  const [savedLogoDataUrl, setSavedLogoDataUrl] = useState<string | null>(null)
  const [agencyLoading, setAgencyLoading] = useState(false)
  const [agencySaving, setAgencySaving] = useState(false)

  useEffect(() => {
    if (!hasAccess) return
    let cancelled = false
    ;(async () => {
      setAgencyLoading(true)
      try {
        const res = await api.get('/proposals/agency-info')
        if (cancelled) return
        const data = res.data || {}
        if (typeof data.content === 'string') setAgencyInfo(data.content)
        if (data.logo_filename) setSavedLogoFilename(data.logo_filename)
        if (data.logo_base64) {
          const mime = data.logo_mime || 'image/png'
          setSavedLogoDataUrl(`data:${mime};base64,${data.logo_base64}`)
        }
      } catch {
        // first-time users or transient errors shouldn't block the form
      } finally {
        if (!cancelled) setAgencyLoading(false)
      }
    })()
    return () => { cancelled = true }
  }, [hasAccess])

  // Object URL for the just-picked file so the preview shows immediately
  useEffect(() => {
    if (!logoFile) { setLogoPreviewUrl(null); return }
    const url = URL.createObjectURL(logoFile)
    setLogoPreviewUrl(url)
    return () => URL.revokeObjectURL(url)
  }, [logoFile])

  const handlePickLogo = (file: File | null) => {
    if (!file) return
    if (!/^image\/(png|jpe?g)$/.test(file.type)) {
      toast.error('Logo must be PNG or JPG')
      return
    }
    if (file.size > 2 * 1024 * 1024) {
      toast.error('Logo must be under 2 MB')
      return
    }
    setLogoFile(file)
  }

  const handleSaveAgency = async () => {
    setAgencySaving(true)
    try {
      const fd = new FormData()
      fd.append('content', agencyInfo)
      if (logoFile) fd.append('logo', logoFile)
      const putRes = await api.put('/proposals/agency-info', fd)
      if (logoFile) {
        setSavedLogoFilename(logoFile.name)
        const body = putRes?.data || {}
        if (body.logo_base64) {
          const mime = body.logo_mime || logoFile.type || 'image/png'
          setSavedLogoDataUrl(`data:${mime};base64,${body.logo_base64}`)
        }
        setLogoFile(null)
      }
      toast.success('Agency info saved')
    } catch (err: unknown) {
      const e = err as { response?: { data?: { detail?: string }; status?: number } }
      toast.error(e.response?.data?.detail || 'Failed to save agency info')
    } finally {
      setAgencySaving(false)
    }
  }

  const onDrop = useCallback((accepted: File[]) => {
    setFiles(prev => {
      const seen = new Set(prev.map(f => f.name + f.size))
      const added = accepted.filter(f => !seen.has(f.name + f.size))
      const merged = [...prev, ...added]
      if (merged.length > 6) {
        toast.error('Maximum 6 quote documents allowed')
        return merged.slice(0, 6)
      }
      return merged
    })
  }, [])

  const { getRootProps, getInputProps, isDragActive } = useDropzone({
    onDrop,
    accept: { 'application/pdf': ['.pdf'] },
    multiple: true,
    noKeyboard: true,
  })

  const removeFile = (index: number) => {
    setFiles(prev => prev.filter((_, i) => i !== index))
  }

  const handleGenerate = async () => {
    if (files.length === 0) {
      toast.error('Upload at least one quote document')
      return
    }

    setGenerating(true)
    setPdfBase64(null)

    const fd = new FormData()
    fd.append('lob', lob)
    fd.append('user_context', clientSize === 'enterprise' ? 'Enterprise client' : 'Small business client')
    fd.append('agency_info', agencyInfo)
    fd.append('brand_primary', brandPrimary)
    fd.append('brand_accent', brandAccent)
    files.forEach(f => fd.append('documents', f))

    try {
      const res = await api.post('/proposals/generate', fd, { timeout: 600000 })
      const data = res.data

      if (data.pdf_base64) {
        setPdfBase64(data.pdf_base64)
        setProposalFilename(data.filename || 'proposal.pdf')
        toast.success('Proposal generated successfully')
      } else {
        toast.error('No PDF returned from the server')
      }
    } catch (err: unknown) {
      const e = err as { response?: { data?: { detail?: string }; status?: number } }
      const detail = e.response?.data?.detail || `Generation failed (HTTP ${e.response?.status || '?'})`
      toast.error(detail)
    } finally {
      setGenerating(false)
    }
  }

  const handleDownload = () => {
    if (!pdfBase64) return
    const byteChars = atob(pdfBase64)
    const byteNums = new Array(byteChars.length)
    for (let i = 0; i < byteChars.length; i++) byteNums[i] = byteChars.charCodeAt(i)
    const blob = new Blob([new Uint8Array(byteNums)], { type: 'application/pdf' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = proposalFilename
    document.body.appendChild(a)
    a.click()
    document.body.removeChild(a)
    URL.revokeObjectURL(url)
  }

  return (
    <div className="relative p-4 sm:p-8 max-w-4xl mx-auto">
      <div className="pointer-events-none absolute inset-x-0 top-0 h-48 bg-gradient-to-b from-primary/[0.03] to-transparent rounded-t-xl" />

      {/* Header */}
      <div className="relative border-b border-border pb-5 mb-6">
        <div className="flex items-center justify-between gap-2">
          <div className="flex items-center gap-3 mb-2">
            <div className="p-2 rounded-xl bg-primary/10">
              <FileText size={20} className="text-primary" />
            </div>
            <h1 className="text-xl font-semibold text-foreground">Proposals</h1>
          </div>
          <UsagePill />
        </div>
        <p className="text-muted-foreground text-sm mt-1 max-w-2xl leading-relaxed">
          Generate professional client-facing proposals with coverage analysis, quote comparison tables, and recommendations.
          Upload carrier quote PDFs, configure your proposal settings below, then download a polished PDF ready to send to your client.
        </p>
      </div>

      <CreditCardBanner description="Add a credit card to generate proposals. You won't be charged on the free plan." />

      {/* Upgrade gate */}
      {!hasAccess && (
        <div className="relative rounded-xl border border-primary/30 bg-primary/5 p-8 mb-6 text-center">
          <div className="w-12 h-12 rounded-xl bg-primary/15 flex items-center justify-center mx-auto mb-4">
            <Lock size={22} className="text-primary" />
          </div>
          <h2 className="text-lg font-semibold text-foreground mb-2">Upgrade to access Proposals</h2>
          <p className="text-sm text-muted-foreground max-w-md mx-auto mb-1">
            Generate professional, branded proposals with coverage analysis and quote comparison tables across multiple carriers.
          </p>
          <p className="text-sm text-muted-foreground max-w-md mx-auto mb-6">
            Proposals are included on the Free, Pro, and Business plans. Upgrade from Starter to unlock them.
          </p>
          <Button size="lg" onClick={() => navigate('/settings')} className="gap-2">
            <Crown size={15} />
            Upgrade to Pro — $199/mo
            <ArrowRight size={14} />
          </Button>
        </div>
      )}

      {/* Form */}
      <div className={cn("space-y-5", !hasAccess && "opacity-40 pointer-events-none select-none")}>

        {/* Two-column row: Line of Business + Client Size */}
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
          <div className="space-y-1.5">
            <Label htmlFor="lob" className="text-sm font-medium">Line of Business</Label>
            <p className="text-xs text-muted-foreground">The insurance line this proposal covers.</p>
            <Select value={lob} onValueChange={setLob}>
              <SelectTrigger id="lob">
                <SelectValue placeholder="Select a line of business" />
              </SelectTrigger>
              <SelectContent>
                {LOB_OPTIONS.map(o => (
                  <SelectItem key={o.value} value={o.value}>{o.label}</SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="client-size" className="text-sm font-medium">Client Size</Label>
            <p className="text-xs text-muted-foreground">Adjusts language and detail level for the audience.</p>
            <Select value={clientSize} onValueChange={(v) => setClientSize(v as 'small_business' | 'enterprise')}>
              <SelectTrigger id="client-size">
                <SelectValue placeholder="Select client size" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="small_business">Small Business</SelectItem>
                <SelectItem value="enterprise">Enterprise</SelectItem>
              </SelectContent>
            </Select>
          </div>
        </div>

        {/* Agency Info + Logo */}
        <div className="space-y-1.5">
          <Label htmlFor="agency-info" className="text-sm font-medium">Agency Info <span className="text-muted-foreground font-normal">(optional)</span></Label>
          <p className="text-xs text-muted-foreground">Your agency details and logo will appear on the proposal cover page. Saved to your account and reused on future proposals.</p>

          <input
            ref={logoInputRef}
            type="file"
            accept="image/png,image/jpeg"
            data-testid="agency-logo-input"
            style={{ display: 'none' }}
            onChange={(e) => handlePickLogo(e.target.files?.[0] ?? null)}
          />

          {agencyLoading ? (
            <div className="flex items-center justify-center py-5 text-muted-foreground">
              <Loader2 size={18} className="animate-spin" />
            </div>
          ) : (
            <textarea
              id="agency-info"
              value={agencyInfo}
              onChange={e => setAgencyInfo(e.target.value)}
              placeholder={'e.g. ABC Insurance Agency, LLC\n123 Main Street, Suite 200\nNew York, NY 10001\nLicense #: 12345678\nPhone: (555) 123-4567'}
              rows={4}
              className="w-full rounded-md border border-input bg-background px-3 py-2 text-sm shadow-sm placeholder:text-muted-foreground focus:outline-none focus:ring-2 focus:ring-ring focus:ring-offset-1 resize-y"
            />
          )}

          <div className="flex items-center gap-2 pt-0.5">
            <button
              type="button"
              onClick={() => logoInputRef.current?.click()}
              title="Upload agency logo"
              data-testid="agency-logo-trigger"
              className="p-1 text-muted-foreground hover:text-foreground transition-colors"
            >
              <ImageIcon size={16} />
            </button>
            <span className="text-xs text-muted-foreground">Click the image icon to upload your agency logo (PNG/JPG, max 2 MB).</span>
          </div>

          {(logoFile || savedLogoFilename) && (
            <div
              className="flex items-center justify-between gap-3 rounded-md border border-border bg-muted/40 px-3 py-2 text-xs text-foreground"
              data-testid="agency-logo-pill"
            >
              <div className="flex items-center gap-3 min-w-0">
                {(logoPreviewUrl || savedLogoDataUrl) && (
                  <img
                    src={logoPreviewUrl || savedLogoDataUrl || ''}
                    alt="Agency logo preview"
                    data-testid="agency-logo-preview"
                    className="h-10 w-10 object-contain rounded bg-background border border-border flex-shrink-0"
                  />
                )}
                <span className="flex items-center gap-2 min-w-0 truncate">
                  <ImageIcon size={13} className="flex-shrink-0" />
                  <span className="truncate">
                    {logoFile ? logoFile.name : `Current logo: ${savedLogoFilename}`}
                  </span>
                </span>
              </div>
              {logoFile && (
                <button
                  type="button"
                  onClick={() => setLogoFile(null)}
                  className="text-muted-foreground hover:text-foreground flex-shrink-0"
                  title="Remove selected logo"
                  aria-label="Remove selected logo"
                >
                  <X size={13} />
                </button>
              )}
            </div>
          )}

          <Button
            type="button"
            size="sm"
            variant="outline"
            className="gap-1.5"
            onClick={handleSaveAgency}
            disabled={agencySaving}
            data-testid="agency-save-btn"
          >
            {agencySaving ? <Loader2 size={13} className="animate-spin" /> : <Save size={13} />}
            Save agency info
          </Button>
        </div>

        {/* Brand Colors */}
        <div className="space-y-1.5">
          <Label className="text-sm font-medium">Brand Colors</Label>
          <p className="text-xs text-muted-foreground">Customize the proposal's color scheme to match your brand.</p>
          <div className="flex gap-4">
            <div className="flex items-center gap-2 flex-1">
              <div className="w-6 h-6 rounded border border-input flex-shrink-0" style={{ backgroundColor: brandPrimary }} />
              <input
                type="text"
                value={brandPrimary}
                onChange={e => setBrandPrimary(e.target.value)}
                placeholder="#1A3560"
                className="w-full h-9 rounded-md border border-input bg-background px-3 text-sm shadow-sm font-mono focus:outline-none focus:ring-2 focus:ring-ring focus:ring-offset-1"
              />
              <span className="text-[11px] text-muted-foreground flex-shrink-0">Primary</span>
            </div>
            <div className="flex items-center gap-2 flex-1">
              <div className="w-6 h-6 rounded border border-input flex-shrink-0" style={{ backgroundColor: brandAccent }} />
              <input
                type="text"
                value={brandAccent}
                onChange={e => setBrandAccent(e.target.value)}
                placeholder="#C9901E"
                className="w-full h-9 rounded-md border border-input bg-background px-3 text-sm shadow-sm font-mono focus:outline-none focus:ring-2 focus:ring-ring focus:ring-offset-1"
              />
              <span className="text-[11px] text-muted-foreground flex-shrink-0">Accent</span>
            </div>
          </div>
        </div>

        {/* File Upload Dropzone */}
        <div className="space-y-1.5">
          <Label className="text-sm font-medium">Quote Documents <span className="text-muted-foreground font-normal">(1-6 PDFs)</span></Label>
          <p className="text-xs text-muted-foreground">Upload carrier quote PDFs to compare. Each quote will be analyzed and included in the proposal.</p>
          <div
            {...getRootProps()}
            className={cn(
              'border-2 border-dashed rounded-xl p-6 text-center cursor-pointer transition-colors bg-white',
              isDragActive
                ? 'border-primary bg-primary/5'
                : files.length > 0
                  ? 'border-border bg-card hover:bg-muted/40'
                  : 'border-border hover:border-primary/40 hover:bg-accent/30'
            )}
          >
            <input {...getInputProps()} />
            <div className="flex flex-col items-center gap-3">
              <div className={cn(
                'w-12 h-12 rounded-xl flex items-center justify-center',
                isDragActive ? 'bg-primary/20' : 'bg-primary/10'
              )}>
                <Upload size={22} className="text-primary" />
              </div>
              {isDragActive ? (
                <p className="text-primary font-medium">Drop quote PDFs here</p>
              ) : (
                <div>
                  <p className="text-foreground font-medium">Drop quote PDFs here</p>
                  <p className="text-muted-foreground text-sm mt-1">or click to browse</p>
                </div>
              )}
            </div>
          </div>

          {/* File list */}
          {files.length > 0 && (
            <div className="space-y-1.5 mt-2">
              {files.map((f, i) => (
                <div key={`${f.name}-${f.size}-${i}`} className="flex items-center gap-2 rounded-lg border border-border bg-card px-3 py-2 group">
                  <FileText size={14} className="text-muted-foreground flex-shrink-0" />
                  <span className="text-sm text-foreground truncate flex-1">{f.name}</span>
                  <span className="text-[11px] text-muted-foreground flex-shrink-0">{formatBytes(f.size)}</span>
                  <button
                    type="button"
                    onClick={() => removeFile(i)}
                    className="opacity-0 group-hover:opacity-100 text-muted-foreground hover:text-red-400 transition-all flex-shrink-0"
                  >
                    <X size={14} />
                  </button>
                </div>
              ))}
            </div>
          )}
        </div>

        {/* Generate button */}
        <Button
          onClick={handleGenerate}
          disabled={generating || files.length === 0}
          size="lg"
          className="w-full shadow-lg shadow-primary/25 gap-2"
        >
          {generating ? (
            <><Loader2 size={15} className="animate-spin" /> Generating...</>
          ) : (
            <><Sparkles size={15} /> Generate Proposal</>
          )}
        </Button>

        {/* Generation progress */}
        {generating && (
          <div className="rounded-xl border border-border bg-card p-5 flex items-center gap-4">
            <div className="w-10 h-10 rounded-xl bg-primary/10 flex items-center justify-center flex-shrink-0">
              <Loader2 size={20} className="animate-spin text-primary" />
            </div>
            <div>
              <p className="text-sm font-medium text-foreground">Generating your proposal...</p>
              <p className="text-xs text-muted-foreground mt-0.5">This may take up to 60 seconds. Analyzing quotes and building the PDF.</p>
            </div>
          </div>
        )}

        {/* Result card */}
        {pdfBase64 && !generating && (
          <div className="rounded-xl border border-emerald-200 bg-emerald-50/60 p-5 flex items-center gap-4">
            <div className="w-10 h-10 rounded-xl bg-emerald-100 flex items-center justify-center flex-shrink-0">
              <CheckCircle2 size={20} className="text-emerald-600" />
            </div>
            <div className="flex-1 min-w-0">
              <p className="text-sm font-medium text-foreground">Proposal ready</p>
              <p className="text-xs text-muted-foreground mt-0.5">{proposalFilename}</p>
            </div>
            <Button size="sm" className="gap-1.5 flex-shrink-0" onClick={handleDownload}>
              <Download size={14} /> Download PDF
            </Button>
          </div>
        )}
      </div>
    </div>
  )
}
