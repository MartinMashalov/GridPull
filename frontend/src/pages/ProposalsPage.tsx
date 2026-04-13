import { useState, useCallback } from 'react'
import { useNavigate } from 'react-router-dom'
import { useDropzone } from 'react-dropzone'
import {
  FileText, Upload, Loader2, Download, X, Sparkles, Lock, Crown, ArrowRight,
} from 'lucide-react'
import api from '@/lib/api'
import { useAuthStore } from '@/store/authStore'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { Label } from '@/components/ui/label'
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

const PRO_TIERS = new Set(['pro', 'business'])

export default function ProposalsPage() {
  const { user } = useAuthStore()
  const navigate = useNavigate()
  const userTier = user?.subscription_tier || 'free'
  const hasAccess = PRO_TIERS.has(userTier)

  const [lob, setLob] = useState(LOB_OPTIONS[0].value)
  const [clientSize, setClientSize] = useState<'small_business' | 'enterprise'>('small_business')
  const [agencyInfo, setAgencyInfo] = useState('')
  const [brandPrimary, setBrandPrimary] = useState('#1A3560')
  const [brandAccent, setBrandAccent] = useState('#C9901E')
  const [files, setFiles] = useState<File[]>([])
  const [generating, setGenerating] = useState(false)
  const [pdfBase64, setPdfBase64] = useState<string | null>(null)
  const [proposalFilename, setProposalFilename] = useState('proposal.pdf')

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
    <div className="relative p-4 sm:p-8 max-w-7xl mx-auto">
      <div className="pointer-events-none absolute inset-x-0 top-0 h-48 bg-gradient-to-b from-primary/[0.03] to-transparent rounded-t-xl" />

      {/* Header */}
      <div className="relative border-b border-border pb-5 mb-6">
        <div className="flex items-center gap-2 mb-1">
          <h1 className="text-xl font-semibold text-foreground">Proposals</h1>
          <Badge variant="secondary" className="text-[10px] px-1.5 py-0">Beta</Badge>
        </div>
        <p className="text-muted-foreground text-sm mt-1 max-w-2xl leading-relaxed">
          Generate professional client-facing proposals with coverage analysis, quote comparison tables, and recommendations.
          Upload carrier quote PDFs, select a line of business and client size (small business or enterprise), customize your brand colors, then generate a polished PDF proposal ready to send to your client.
        </p>
      </div>

      {/* Upgrade gate */}
      {!hasAccess && (
        <div className="relative rounded-xl border border-primary/30 bg-primary/5 p-8 mb-6 text-center">
          <div className="w-12 h-12 rounded-xl bg-primary/15 flex items-center justify-center mx-auto mb-4">
            <Lock size={22} className="text-primary" />
          </div>
          <h2 className="text-lg font-semibold text-foreground mb-2">Proposals require a Pro plan</h2>
          <p className="text-sm text-muted-foreground max-w-md mx-auto mb-1">
            Generate professional, branded proposals with coverage analysis and quote comparison tables across multiple carriers.
          </p>
          <p className="text-sm text-muted-foreground max-w-md mx-auto mb-6">
            Upgrade to Pro to access Proposals along with 25,000 pages/month and automated pipelines.
          </p>
          <Button size="lg" onClick={() => navigate('/settings')} className="gap-2">
            <Crown size={15} />
            Upgrade to Pro — $199/mo
            <ArrowRight size={14} />
          </Button>
        </div>
      )}

      {/* Split layout */}
      <div className={cn("grid grid-cols-1 lg:grid-cols-2 gap-6", !hasAccess && "opacity-40 pointer-events-none select-none")}>

        {/* ── Left panel: Configuration ──────────────────────────── */}
        <div className="space-y-5">

          {/* Line of Business */}
          <div className="space-y-1.5">
            <Label htmlFor="lob" className="text-sm font-medium">Line of Business</Label>
            <select
              id="lob"
              value={lob}
              onChange={e => setLob(e.target.value)}
              className="w-full h-9 rounded-md border border-input bg-background px-3 text-sm shadow-sm focus:outline-none focus:ring-2 focus:ring-ring focus:ring-offset-1"
            >
              {LOB_OPTIONS.map(o => (
                <option key={o.value} value={o.value}>{o.label}</option>
              ))}
            </select>
          </div>

          {/* Client Size */}
          <div className="space-y-1.5">
            <Label htmlFor="client-size" className="text-sm font-medium">Client Size</Label>
            <select
              id="client-size"
              value={clientSize}
              onChange={e => setClientSize(e.target.value as 'small_business' | 'enterprise')}
              className="w-full h-9 rounded-md border border-input bg-background px-3 text-sm shadow-sm focus:outline-none focus:ring-2 focus:ring-ring focus:ring-offset-1"
            >
              <option value="small_business">Small Business</option>
              <option value="enterprise">Enterprise</option>
            </select>
          </div>

          {/* Agency Info */}
          <div className="space-y-1.5">
            <Label htmlFor="agency-info" className="text-sm font-medium">Agency Info <span className="text-muted-foreground font-normal">(optional)</span></Label>
            <textarea
              id="agency-info"
              value={agencyInfo}
              onChange={e => setAgencyInfo(e.target.value)}
              placeholder="Agency name, address, phone..."
              rows={3}
              className="w-full rounded-md border border-input bg-background px-3 py-2 text-sm shadow-sm placeholder:text-muted-foreground focus:outline-none focus:ring-2 focus:ring-ring focus:ring-offset-1 resize-none"
            />
          </div>

          {/* Brand Colors */}
          <div className="space-y-1.5">
            <Label className="text-sm font-medium">Brand Colors</Label>
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
        </div>

        {/* ── Right panel: PDF Preview ───────────────────────────── */}
        <div className="flex flex-col">
          <div className="flex items-center justify-between mb-2">
            <Label className="text-sm font-medium">Preview</Label>
            {pdfBase64 && (
              <Button variant="outline" size="sm" className="gap-1.5 h-7 text-xs" onClick={handleDownload}>
                <Download size={12} /> Download PDF
              </Button>
            )}
          </div>

          <div className="flex-1 min-h-[600px] rounded-xl border border-border bg-muted/30 overflow-hidden">
            {generating ? (
              <div className="flex flex-col items-center justify-center h-full gap-4">
                <div className="w-14 h-14 rounded-xl bg-primary/10 flex items-center justify-center">
                  <Loader2 size={24} className="animate-spin text-primary" />
                </div>
                <div className="text-center">
                  <p className="text-sm font-medium text-foreground">Generating proposal...</p>
                  <p className="text-xs text-muted-foreground mt-1">This may take up to 60 seconds</p>
                </div>
              </div>
            ) : pdfBase64 ? (
              <iframe
                src={`data:application/pdf;base64,${pdfBase64}`}
                className="w-full h-full min-h-[600px]"
                title="Proposal Preview"
              />
            ) : (
              <div className="flex flex-col items-center justify-center h-full gap-3">
                <div className="w-14 h-14 rounded-xl bg-muted/60 flex items-center justify-center">
                  <FileText size={24} className="text-muted-foreground/60" />
                </div>
                <p className="text-sm text-muted-foreground">Your proposal will appear here</p>
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  )
}
