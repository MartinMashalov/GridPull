import { useState, useCallback, useEffect, useRef } from 'react'
import { trackEvent } from '@/lib/analytics'
import { useDropzone } from 'react-dropzone'
import JSZip from 'jszip'
import { Upload, Loader2, CheckCircle2, AlertCircle, X, FileText, ArrowRight, Workflow, Lock, Trash2, Eye, AlertTriangle, Crown } from 'lucide-react'
import { useAuthStore } from '@/store/authStore'
import { useNavigate } from 'react-router-dom'
import ExtractionFieldsModal from '@/components/ExtractionFieldsModal'
import SpreadsheetViewer from '@/components/SpreadsheetViewer'
import api from '@/lib/api'
import { useJobProgress } from '@/hooks/useJobProgress'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { Progress } from '@/components/ui/progress'
import { cn } from '@/lib/utils'

interface UsageWarning {
  warning: string | null
  files_used: number
  files_limit: number
  overage_files: number
  overage_rate: number | null
  usage_percent: number
  tier: string
  next_tier: { name: string; display_name: string; price_monthly: number; files_per_month: number } | null
}

export type ExportFormat = 'xlsx' | 'csv'
export type DocumentType = 'custom' | 'quickbooks' | 'invoices' | 'sov'

export interface ExtractionField {
  name: string
  description: string
}

const DOC_TYPE_OPTIONS: { id: DocumentType; label: string }[] = [
  { id: 'custom', label: 'Custom Fields' },
  { id: 'quickbooks', label: 'QuickBooks' },
  { id: 'invoices', label: 'Invoices' },
  { id: 'sov', label: 'Statement of Values' },
]

const QUICKBOOKS_FIELDS: ExtractionField[] = [
  { name: 'Date', description: 'Transaction date' },
  { name: 'Description', description: 'Payee or transaction description' },
  { name: 'Amount', description: 'Positive for deposits/credits, negative for withdrawals/debits' },
]

export interface JobState {
  jobId: string
  status: 'queued' | 'processing' | 'extracting' | 'generating' | 'complete' | 'error'
  progress: number
  message: string
  completed_docs?: number
  total_docs?: number
  downloadUrl?: string
  results?: Record<string, string>[]
  fields?: string[]
  cost?: number
  error?: string
}

const _ACTIVE_JOB_KEY = 'gridpull-active-job'
const _ACCEPTED_TYPES = new Set(['application/pdf', 'image/png', 'image/jpeg'])
const _SUPPORTED_EXTENSIONS = new Set(['pdf', 'png', 'jpg', 'jpeg'])
const _ZIP_MIME_TYPES = new Set(['application/zip', 'application/x-zip-compressed'])
const _ZIP_MAX_SIZE_BYTES = 20 * 1024 * 1024

// ── Progress bar ───────────────────────────────────────────────────────────────
function ProgressBar({ job, onCancel }: { job: JobState; onCancel: () => void }) {
  const isError = job.status === 'error'
  const isComplete = job.status === 'complete'
  const totalDocs = job.total_docs ?? 0
  const completedDocs = job.completed_docs ?? 0

  // Prefer completed-doc progress, but fall back to backend percentage so the UI
  // still moves before the first document finishes or when SSE is unavailable.
  const docPct = totalDocs > 0 ? Math.round((completedDocs / totalDocs) * 100) : 0
  const barPct = isComplete ? 100 : Math.max(docPct, job.progress ?? 0)
  const indeterminate = !isComplete && !isError && barPct === 0

  return (
    <div className="mt-4 bg-card border border-border rounded-xl overflow-hidden animate-fade-in">
      <div className="px-5 py-4 border-b border-border">
        <div className="flex items-center justify-between mb-3">
          <span className="text-sm font-semibold flex items-center gap-2">
            {isComplete && <CheckCircle2 size={15} className="text-emerald-400" />}
            {isError && <AlertCircle size={15} className="text-red-400" />}
            {isError ? 'Extraction Failed' : isComplete ? 'Complete!' : 'Processing…'}
          </span>
          <div className="flex items-center gap-3">
            {!isComplete && !isError && (
              <button
                onClick={onCancel}
                className="flex items-center gap-1 text-xs font-medium text-red-500 hover:text-red-600 transition-colors"
              >
                <X size={11} /> Cancel
              </button>
            )}
          </div>
        </div>
        <Progress
          value={barPct}
          className={cn(
            indeterminate && 'animate-pulse',
            isError && '[&>div]:bg-red-500',
            isComplete && '[&>div]:bg-emerald-500'
          )}
        />
        {!isError && (
          <p className="mt-3 text-xs text-muted-foreground">
            {job.message}
          </p>
        )}
      </div>
      {isError && job.error && (
        <div className="px-5 py-2.5 border-t border-border">
          <p className="text-xs text-red-400 bg-red-500/10 border border-red-500/20 rounded-lg px-3 py-2">
            {job.error}
          </p>
        </div>
      )}
    </div>
  )
}

// ── Main page ──────────────────────────────────────────────────────────────────
export default function DashboardPage() {
  const { user, updateBalance, updateSubscription } = useAuthStore()
  const [files, setFiles] = useState<File[]>([])
  const [showModal, setShowModal] = useState(false)
  const [exportFormat, setExportFormat] = useState<ExportFormat>('xlsx')
  const [documentType, setDocumentType] = useState<DocumentType>('custom')
  const [activeJobId, setActiveJobId] = useState<string | null>(null)
  const [job, setJob] = useState<JobState | null>(null)
  const [validationMsg, setValidationMsg] = useState<string | null>(null)
  const [usageWarning, setUsageWarning] = useState<UsageWarning | null>(null)
  const [isPaywalled, setIsPaywalled] = useState(false)

  const { event } = useJobProgress(activeJobId)

  useEffect(() => {
    api.get('/payments/usage-warning').then(r => setUsageWarning(r.data)).catch(() => {})
  }, [])

  // ── Restore active job on page reload ──────────────────────────────────────
  useEffect(() => {
    const stored = localStorage.getItem(_ACTIVE_JOB_KEY)
    if (!stored) return
    try {
      const { jobId, format } = JSON.parse(stored)
      setExportFormat(format as ExportFormat)
      setJob({ jobId, status: 'processing', progress: 0, message: 'Reconnecting…' })
      setActiveJobId(jobId)
    } catch {
      localStorage.removeItem(_ACTIVE_JOB_KEY)
    }
  }, [])

  useEffect(() => {
    if (!event) return

    if (event.type === 'progress') {
      setJob((prev) =>
        prev ? {
          ...prev,
          status: event.status as JobState['status'],
          progress: event.progress,
          message: event.message ?? prev.message,
          ...(event.completed_docs != null && { completed_docs: event.completed_docs }),
          ...(event.total_docs != null && { total_docs: event.total_docs }),
        } : null
      )
    }

    if (event.type === 'complete') {
      localStorage.removeItem(_ACTIVE_JOB_KEY)
      setActiveJobId(null)
      trackEvent('extraction_complete', { cost: event.cost ?? 0, file_count: event.results?.length ?? 0 })
      setJob((prev) =>
        prev ? { ...prev, status: 'complete', progress: 100, message: 'Extraction complete!', downloadUrl: event.download_url, results: event.results, fields: event.fields, cost: event.cost } : null
      )
      if (event.cost != null && user) {
        updateBalance(Math.max(0, (user.balance ?? 0) - event.cost))
      }
    }

    if (event.type === 'error') {
      localStorage.removeItem(_ACTIVE_JOB_KEY)
      setActiveJobId(null)
      setJob((prev) =>
        prev ? { ...prev, status: 'error', message: 'Extraction failed', error: event.error } : null
      )
    }
  }, [event])

  const onDrop = useCallback(async (acceptedFiles: File[]) => {
    const valid: File[] = []
    let unsupportedDirectCount = 0
    let oversizedZipCount = 0
    let unreadableZipCount = 0
    let ignoredZipEntryCount = 0
    let zipWithNoSupportedFilesCount = 0

    for (const droppedFile of acceptedFiles) {
      const fileName = droppedFile.name.toLowerCase()
      const ext = fileName.includes('.') ? fileName.split('.').pop() ?? '' : ''
      const isZip = _ZIP_MIME_TYPES.has(droppedFile.type) || ext === 'zip'

      if (!isZip) {
        const isSupported = _ACCEPTED_TYPES.has(droppedFile.type) || _SUPPORTED_EXTENSIONS.has(ext)
        if (isSupported) valid.push(droppedFile)
        else unsupportedDirectCount += 1
        continue
      }

      if (droppedFile.size > _ZIP_MAX_SIZE_BYTES) {
        oversizedZipCount += 1
        continue
      }

      try {
        const zip = await JSZip.loadAsync(droppedFile)
        let extractedFromThisZip = 0

        for (const entry of Object.values(zip.files)) {
          if (entry.dir) continue
          const entryFileName = entry.name.split('/').pop() ?? ''
          const entryExt = entryFileName.includes('.') ? (entryFileName.split('.').pop() ?? '').toLowerCase() : ''

          if (!_SUPPORTED_EXTENSIONS.has(entryExt)) {
            ignoredZipEntryCount += 1
            continue
          }

          const blob = await entry.async('blob')
          const type = entryExt === 'pdf'
            ? 'application/pdf'
            : entryExt === 'png'
              ? 'image/png'
              : 'image/jpeg'
          valid.push(new File([blob], entryFileName, { type, lastModified: Date.now() }))
          extractedFromThisZip += 1
        }

        if (extractedFromThisZip === 0) zipWithNoSupportedFilesCount += 1
      } catch {
        unreadableZipCount += 1
      }
    }

    const issues: string[] = []
    if (unsupportedDirectCount > 0) {
      issues.push(`${unsupportedDirectCount} unsupported file${unsupportedDirectCount > 1 ? 's' : ''} skipped`)
    }
    if (oversizedZipCount > 0) {
      issues.push(`${oversizedZipCount} ZIP file${oversizedZipCount > 1 ? 's' : ''} exceeded 20 MB`)
    }
    if (unreadableZipCount > 0) {
      issues.push(`${unreadableZipCount} ZIP file${unreadableZipCount > 1 ? 's' : ''} could not be read`)
    }
    if (zipWithNoSupportedFilesCount > 0) {
      issues.push(`${zipWithNoSupportedFilesCount} ZIP file${zipWithNoSupportedFilesCount > 1 ? 's' : ''} had no supported files`)
    }
    if (ignoredZipEntryCount > 0) {
      issues.push(`${ignoredZipEntryCount} unsupported ZIP entr${ignoredZipEntryCount === 1 ? 'y' : 'ies'} ignored`)
    }

    setValidationMsg(issues.length ? issues.join(' · ') : null)

    trackEvent('files_uploaded', { count: valid.length })
    setFiles((prev) => {
      const seen = new Set(prev.map((f) => f.name + f.size))
      return [...prev, ...valid.filter((f) => !seen.has(f.name + f.size))]
    })
  }, [])

  const { getRootProps, getInputProps, isDragActive } = useDropzone({
    onDrop,
    accept: {
      'application/pdf': ['.pdf'],
      'image/png': ['.png'],
      'image/jpeg': ['.jpg', '.jpeg'],
      'application/zip': ['.zip'],
      'application/x-zip-compressed': ['.zip'],
    },
    multiple: true,
    noKeyboard: true,
  })

  const handleProcess = () => {
    if (!files.length) { setValidationMsg('Upload at least one supported file.'); return }
    setValidationMsg(null)
    if (documentType === 'quickbooks') {
      handleExtract(
        QUICKBOOKS_FIELDS,
        exportFormat,
        'Extract accounting-ready transaction fields from each document. Return Date, Description, and Amount. For invoices, use invoice date, vendor or purpose as Description, and total due as a negative Amount. For statements, use transaction date, payee, and amount with positive values for credits and negative values for debits. If a field is not present in the source, leave it blank.',
      )
    } else {
      setShowModal(true)
    }
  }

  const handleExtract = async (fields: ExtractionField[], format: ExportFormat, instructions: string) => {
    trackEvent('extraction_start', { field_count: fields.length, format, file_count: files.length, has_instructions: !!instructions.trim() })
    setShowModal(false)
    setExportFormat(format)
    setActiveJobId(null)
    setJob({ jobId: '', status: 'queued', progress: 0, message: 'Uploading files…', total_docs: files.length, completed_docs: 0 })

    try {
      const fd = new FormData()
      files.forEach((f) => fd.append('files', f))
      fd.append('fields', JSON.stringify(fields))
      fd.append('instructions', instructions.trim())
      fd.append('format', format)

      const res = await api.post('/documents/extract', fd)

      const jobId = res.data.job_id
      localStorage.setItem(_ACTIVE_JOB_KEY, JSON.stringify({ jobId, format: exportFormat }))
      setJob((p) => p ? { ...p, jobId, status: 'processing' } : null)
      setActiveJobId(jobId)

      if (res.data.usage) {
        updateSubscription({ files_used_this_period: res.data.usage.files_used })
        api.get('/payments/usage-warning').then(r => setUsageWarning(r.data)).catch(() => {})
      }
    } catch (err: any) {
      const detail = err.response?.data?.detail
      const status = err.response?.status

      if (status === 402 && typeof detail === 'object' && detail?.type === 'file_limit_reached') {
        setJob((p) => p ? { ...p, status: 'error', message: 'File limit reached', error: detail.message } : null)
        setIsPaywalled(true)
        api.get('/payments/usage-warning').then(r => setUsageWarning(r.data)).catch(() => {})
        return
      }

      const msg = typeof detail === 'string'
        ? detail
        : status
          ? `Upload failed (HTTP ${status})`
          : 'Upload failed — check your connection'
      setJob((p) => p ? { ...p, status: 'error', message: 'Error', error: msg } : null)
    }
  }

  const handleCancel = async () => {
    if (!job?.jobId) return
    try { await api.delete(`/documents/job/${job.jobId}`) } catch {}
    localStorage.removeItem(_ACTIVE_JOB_KEY)
    setJob(null)
    setActiveJobId(null)
    setFiles([])
  }

  const handleNew = () => {
    localStorage.removeItem(_ACTIVE_JOB_KEY)
    setJob(null)
    setActiveJobId(null)
    setFiles([])
    setValidationMsg(null)
    setIsPaywalled(false)
  }

  const isProcessing = job !== null && job.status !== 'complete' && job.status !== 'error'

  const submitBtnRef = useRef<HTMLButtonElement>(null)
  const showModalRef = useRef(showModal)
  showModalRef.current = showModal
  const filesLengthRef = useRef(files.length)
  filesLengthRef.current = files.length
  const isProcessingRef = useRef(isProcessing)
  isProcessingRef.current = isProcessing
  const documentTypeRef = useRef(documentType)
  documentTypeRef.current = documentType

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') { setFiles([]); return }
      if (e.key === 'Enter' && !showModalRef.current && filesLengthRef.current > 0 && !isProcessingRef.current) {
        e.preventDefault()
        submitBtnRef.current?.click()
      }
    }
    document.addEventListener('keydown', onKey, true)
    return () => document.removeEventListener('keydown', onKey, true)
  }, [])

  const navigate = useNavigate()

  return (
    <div className="relative p-4 sm:p-8 max-w-4xl mx-auto">
      {/* Subtle gradient wash at the top */}
      <div className="pointer-events-none absolute inset-x-0 top-0 h-48 bg-gradient-to-b from-primary/[0.03] to-transparent rounded-t-xl" />

      {/* Header */}
      <div className="relative border-b border-border pb-5 mb-6 flex flex-col sm:flex-row sm:items-start justify-between gap-2">
        <div>
          <h1 className="text-xl font-semibold text-foreground">Extract Data from PDFs & Images</h1>
          <p className="text-muted-foreground text-sm mt-0.5">Upload PDFs, PNGs, JPEGs, or ZIPs (up to 20 MB each) — choose fields and download a clean spreadsheet</p>
        </div>
        <div className="flex items-center gap-2">
          {usageWarning && (
            <>
              <span className="text-xs text-muted-foreground">{usageWarning.files_used}/{usageWarning.files_limit} files</span>
              <Badge
                variant={usageWarning.usage_percent >= 80 ? 'destructive' : 'blue'}
                className="font-mono text-[11px]"
              >
                {user?.subscription_tier === 'free' ? 'Free' : (user?.subscription_tier || 'Free')}
              </Badge>
            </>
          )}
        </div>
      </div>

      {/* Usage warning banner */}
      {usageWarning?.warning === 'near_limit' && usageWarning.next_tier && (
        <div className="relative mb-4 rounded-xl border border-amber-500/30 bg-amber-500/5 p-4 flex items-center gap-3">
          <div className="w-8 h-8 rounded-lg bg-amber-500/15 flex items-center justify-center flex-shrink-0">
            <AlertTriangle size={15} className="text-amber-500" />
          </div>
          <div className="flex-1 min-w-0">
            <p className="text-sm font-medium text-foreground">
              You've used {usageWarning.files_used} of {usageWarning.files_limit} files this month
            </p>
            <p className="text-xs text-muted-foreground mt-0.5">
              {usageWarning.overage_rate
                ? `Extra files cost $${(usageWarning.overage_rate / 100).toFixed(2)} each.`
                : 'You\'ll be blocked when you hit the limit.'
              }
              {' '}Upgrade to {usageWarning.next_tier.display_name} for {usageWarning.next_tier.files_per_month.toLocaleString()} files at ${(usageWarning.next_tier.price_monthly / 100).toFixed(0)}/mo.
            </p>
          </div>
          <Button size="sm" variant="outline" onClick={() => navigate('/settings')} className="flex-shrink-0">
            <Crown size={12} className="mr-1" /> Upgrade
          </Button>
        </div>
      )}

      {usageWarning?.warning === 'limit_reached_free' && (
        <div className="relative mb-4 rounded-xl border border-red-500/30 bg-red-500/5 p-4 flex items-center gap-3">
          <div className="w-8 h-8 rounded-lg bg-red-500/15 flex items-center justify-center flex-shrink-0">
            <Lock size={15} className="text-red-500" />
          </div>
          <div className="flex-1 min-w-0">
            <p className="text-sm font-medium text-foreground">
              Free limit reached ({usageWarning.files_limit} files/month)
            </p>
            <p className="text-xs text-muted-foreground mt-0.5">
              Upgrade to Starter for 200 files/month — just $9.50 for your first month.
            </p>
          </div>
          <Button size="sm" onClick={() => navigate('/settings')} className="flex-shrink-0">
            Upgrade <ArrowRight size={12} className="ml-1" />
          </Button>
        </div>
      )}

      {/* How it works — inline guide (hidden on mobile to reduce clutter) */}
      {!job && files.length === 0 && (
        <div className="mb-6 hidden sm:block">
          <p className="text-xs font-semibold text-muted-foreground uppercase tracking-wider mb-3">How it works</p>
          <div className="grid grid-cols-3 gap-4">
            <div className="flex flex-col items-center text-center gap-2">
              <div className="w-8 h-8 rounded-lg bg-primary/10 flex items-center justify-center">
                <Upload size={14} className="text-primary" />
              </div>
              <div>
                <p className="text-xs font-medium text-foreground">1. Upload your documents</p>
                <p className="text-[11px] text-muted-foreground mt-0.5">PDF, PNG, JPEG, or ZIP (up to 20 MB)</p>
              </div>
            </div>
            <div className="flex flex-col items-center text-center gap-2">
              <div className="w-8 h-8 rounded-lg bg-primary/10 flex items-center justify-center">
                <FileText size={14} className="text-primary" />
              </div>
              <div>
                <p className="text-xs font-medium text-foreground">2. Pick the fields to extract</p>
                <p className="text-[11px] text-muted-foreground mt-0.5">e.g. Invoice #, Date, Total — or any custom field</p>
              </div>
            </div>
            <div className="flex flex-col items-center text-center gap-2">
              <div className="w-8 h-8 rounded-lg bg-primary/10 flex items-center justify-center">
                <ArrowRight size={14} className="text-primary" />
              </div>
              <div>
                <p className="text-xs font-medium text-foreground">3. Get your spreadsheet</p>
                <p className="text-[11px] text-muted-foreground mt-0.5">One row per document, one column per field — download instantly</p>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Security trust strip — hidden on mobile, shown on sm+ */}
      {!job && (
        <div className="mb-5 hidden sm:flex flex-wrap items-center justify-center gap-x-5 gap-y-1.5 text-[11px] text-muted-foreground">
          <span className="flex items-center gap-1.5"><Lock size={11} className="text-emerald-500" /> Encrypted in transit</span>
          <span className="flex items-center gap-1.5"><Trash2 size={11} className="text-emerald-500" /> Files deleted after processing</span>
          <span className="flex items-center gap-1.5"><Eye size={11} className="text-emerald-500" /> No human access to your documents</span>
        </div>
      )}

      {/* Document type selector */}
      <div className="mb-4">
        <span className="text-xs text-muted-foreground block mb-2">Document type</span>
        <div className="flex bg-secondary border border-border rounded-lg overflow-hidden">
          {DOC_TYPE_OPTIONS.map((dt) => (
            <button
              key={dt.id}
              onClick={() => {
                if (documentType === dt.id) return
                setDocumentType(dt.id)
                setFiles([])
                setValidationMsg(null)
              }}
              className={cn(
                'flex-1 px-3 py-2 text-xs font-medium transition-colors whitespace-nowrap',
                documentType === dt.id
                  ? 'bg-primary text-primary-foreground'
                  : 'text-muted-foreground hover:text-foreground'
              )}
            >
              {dt.label}
            </button>
          ))}
        </div>
      </div>

      {/* Format toggle */}
      <div className="flex items-center gap-3 mb-4">
        <span className="text-xs text-muted-foreground">Output format</span>
        <div className="flex bg-secondary border border-border rounded-lg overflow-hidden">
          {(['xlsx', 'csv'] as ExportFormat[]).map((fmt) => (
            <button
              key={fmt}
              onClick={() => setExportFormat(fmt)}
              className={cn(
                'px-3 py-1.5 text-xs font-medium transition-colors',
                exportFormat === fmt
                  ? 'bg-primary text-primary-foreground'
                  : 'text-muted-foreground hover:text-foreground'
              )}
            >
              {fmt.toUpperCase()}
            </button>
          ))}
        </div>
        <span className="text-[11px] text-muted-foreground hidden sm:inline">
          {exportFormat === 'xlsx' ? 'Excel spreadsheet — opens in Excel, Google Sheets, etc.' : 'Comma-separated values — universal format for any spreadsheet app'}
        </span>
      </div>

      {/* Drop zone */}
      <div
        {...getRootProps()}
        className={cn(
          'border-2 border-dashed rounded-xl p-5 sm:p-14 text-center cursor-pointer transition-all duration-200',
          'bg-white',
          isDragActive
            ? 'border-primary bg-primary/5'
            : 'border-border hover:border-primary/40 hover:bg-accent/30'
        )}
      >
        <input {...getInputProps()} />
        <div className="flex flex-col items-center gap-3">
          <div className={cn(
            'w-12 h-12 rounded-xl flex items-center justify-center transition-colors',
            isDragActive ? 'bg-primary/20 text-primary' : 'bg-primary/10 text-primary'
          )}>
            <Upload size={22} />
          </div>
          {isDragActive ? (
            <p className="text-primary font-medium">Drop your files here</p>
          ) : (
            <div>
              <p className="text-foreground font-medium">Drag and drop your files here, or click to browse</p>
              <p className="text-muted-foreground text-sm mt-1">Supports PDF, PNG, JPEG, and ZIP (max 20 MB ZIP) — upload multiple files at once</p>
            </div>
          )}
        </div>
      </div>

      {/* Mobile-only compact security line */}
      {!job && (
        <p className="mt-2 text-center text-[11px] text-muted-foreground sm:hidden">
          <Lock size={10} className="inline text-emerald-500 mr-1" />
          Encrypted · files deleted after processing · no human access
        </p>
      )}

      {/* Validation message */}
      {validationMsg && (
        <p className="mt-2 text-xs text-red-500">{validationMsg}</p>
      )}

      {/* File count */}
      {files.length > 0 && (
        <div className="mt-3 bg-card border border-border rounded-xl px-4 py-3 flex items-center justify-between">
          <span className="text-sm font-medium text-foreground">
            {files.length} file{files.length > 1 ? 's' : ''} selected
          </span>
          <button onClick={() => setFiles([])} className="text-xs text-muted-foreground hover:text-red-400 transition-colors">
            Clear all
          </button>
        </div>
      )}

      {/* CTA */}
      <Button
        ref={submitBtnRef}
        onClick={handleProcess}
        disabled={!files.length || isProcessing}
        size="lg"
        className="mt-4 w-full shadow-lg shadow-primary/25"
      >
        {isProcessing ? (
          <>
            <Loader2 size={15} className="animate-spin" />
            Processing…
          </>
        ) : files.length > 0 ? (
          documentType === 'quickbooks'
            ? `Extract ${files.length} file${files.length > 1 ? 's' : ''} for QuickBooks`
            : `Choose fields & extract ${files.length} file${files.length > 1 ? 's' : ''}`
        ) : (
          'Upload files to get started'
        )}
      </Button>

      {/* Progress */}
      {job && job.status !== 'complete' && <ProgressBar job={job} onCancel={handleCancel} />}

      {/* Results */}
      {job?.status === 'complete' && job.results && job.fields && (
        <SpreadsheetViewer
          results={job.results}
          fields={job.fields}
          jobId={job.jobId}
          format={exportFormat}
          onNew={handleNew}
          paywalled={isPaywalled}
          documentType={documentType}
        />
      )}

      {/* Pipeline nudge — show when no active job */}
      {!job && files.length === 0 && (
        <div className="mt-8 bg-card border border-border rounded-xl p-4 flex items-start gap-3">
          <div className="w-8 h-8 rounded-lg bg-primary/10 flex items-center justify-center flex-shrink-0 mt-0.5">
            <Workflow size={15} className="text-primary" />
          </div>
          <div className="flex-1 min-w-0">
            <p className="text-sm font-medium text-foreground">Process documents automatically?</p>
            <p className="text-xs text-muted-foreground mt-0.5">
              Set up a Pipeline to connect a Google Drive or SharePoint folder. New documents added to that folder will be extracted automatically — no manual uploads needed.
            </p>
            <button
              onClick={() => navigate('/pipelines')}
              className="mt-2 text-xs font-medium text-primary hover:underline flex items-center gap-1"
            >
              Set up a Pipeline <ArrowRight size={11} />
            </button>
          </div>
        </div>
      )}

      <ExtractionFieldsModal
        open={showModal}
        onClose={() => setShowModal(false)}
        onConfirm={handleExtract}
        defaultFormat={exportFormat}
        documentType={documentType}
      />
    </div>
  )
}
