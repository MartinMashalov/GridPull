import { useState, useCallback, useEffect, useRef } from 'react'
import { trackEvent } from '@/lib/analytics'
import { useDropzone, type FileRejection } from 'react-dropzone'
import JSZip from 'jszip'
import { Upload, Loader2, CheckCircle2, AlertCircle, X, FileText, ArrowRight, Lock, Trash2, Eye, AlertTriangle, Crown, FileSpreadsheet } from 'lucide-react'
import { useAuthStore } from '@/store/authStore'
import { useNavigate } from 'react-router-dom'
import ExtractionFieldsModal from '@/components/ExtractionFieldsModal'
import SpreadsheetViewer from '@/components/SpreadsheetViewer'
import api from '@/lib/api'
import { useJobProgress } from '@/hooks/useJobProgress'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { Checkbox } from '@/components/ui/checkbox'
import { Label } from '@/components/ui/label'
import { Progress } from '@/components/ui/progress'
import { cn } from '@/lib/utils'
import InboxModal from '@/components/InboxModal'

interface UsageWarning {
  warning: string | null
  pages_used: number
  pages_limit: number
  overage_pages: number
  overage_rate_cents_per_page: number | null
  usage_percent: number
  tier: string
  next_tier: { name: string; display_name: string; price_monthly: number; pages_per_month: number } | null
}

export type ExportFormat = 'xlsx' | 'csv'
export type DocumentType = 'custom' | 'quickbooks' | 'invoices' | 'sov'

export interface ExtractionField {
  name: string
  description: string
  format?: string
  numeric?: boolean
}

const DOC_TYPE_OPTIONS: { id: DocumentType; label: string }[] = [
  { id: 'sov', label: 'Schedules' },
  { id: 'invoices', label: 'Invoices' },
  { id: 'quickbooks', label: 'QuickBooks' },
  { id: 'custom', label: 'Custom Fields' },
]

const QUICKBOOKS_FIELDS: ExtractionField[] = [
  { name: 'Date', description: 'Transaction date' },
  { name: 'Description', description: 'Payee or transaction description' },
  { name: 'Amount', description: 'Amount as it appears on the document (positive number)' },
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
  baselineUpdateMode?: boolean
  outputFilename?: string
}

const _ACTIVE_JOB_KEY = 'gridpull-active-job'
const _ACCEPTED_TYPES = new Set([
  'application/pdf',
  'image/png',
  'image/jpeg',
  'image/webp',
  'image/gif',
  'image/bmp',
  'image/tiff',
  'text/plain',
  'text/markdown',
  'text/html',
  'application/json',
  'application/xml',
  'text/xml',
  'message/rfc822',
  'application/vnd.ms-outlook',
])
const _SUPPORTED_EXTENSIONS = new Set([
  'pdf', 'png', 'jpg', 'jpeg', 'webp', 'gif', 'bmp', 'tif', 'tiff',
  'txt', 'md', 'markdown', 'html', 'htm', 'json', 'xml', 'eml', 'emlx', 'msg',
])
const _SPREADSHEET_EXTENSIONS = new Set(['xlsx', 'csv'])
const _ZIP_MIME_TYPES = new Set(['application/zip', 'application/x-zip-compressed'])
const _MAX_FILE_SIZE_BYTES = 5 * 1024 * 1024
const _EXTENSION_TO_MIME: Record<string, string> = {
  pdf: 'application/pdf',
  png: 'image/png',
  jpg: 'image/jpeg',
  jpeg: 'image/jpeg',
  webp: 'image/webp',
  gif: 'image/gif',
  bmp: 'image/bmp',
  tif: 'image/tiff',
  tiff: 'image/tiff',
  txt: 'text/plain',
  md: 'text/markdown',
  markdown: 'text/markdown',
  html: 'text/html',
  htm: 'text/html',
  json: 'application/json',
  xml: 'application/xml',
  eml: 'message/rfc822',
  emlx: 'message/rfc822',
  msg: 'application/vnd.ms-outlook',
}
const _DOCUMENT_ACCEPT = {
  'application/pdf': ['.pdf'],
  'image/png': ['.png'],
  'image/jpeg': ['.jpg', '.jpeg'],
  'image/webp': ['.webp'],
  'image/gif': ['.gif'],
  'image/bmp': ['.bmp'],
  'image/tiff': ['.tif', '.tiff'],
  'text/plain': ['.txt'],
  'text/markdown': ['.md', '.markdown'],
  'text/html': ['.html', '.htm'],
  'application/json': ['.json'],
  'application/xml': ['.xml'],
  'message/rfc822': ['.eml', '.emlx'],
  'application/vnd.ms-outlook': ['.msg'],
  'application/octet-stream': ['.msg'],
  'application/zip': ['.zip'],
  'application/x-zip-compressed': ['.zip'],
}
const _BASELINE_ACCEPT = {
  'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet': ['.xlsx'],
  'text/csv': ['.csv'],
  'application/vnd.ms-excel': ['.csv'],
}

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
    <div className="relative z-20 mt-4 bg-card border border-border rounded-xl overflow-hidden animate-fade-in">
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
                type="button"
                onClick={() => onCancel()}
                className="relative z-10 flex items-center gap-1 text-xs font-medium text-red-500 hover:text-red-600 transition-colors"
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
        <p className="text-xs text-red-400 px-5 pt-1 pb-2">
          {job.error}
        </p>
      )}
    </div>
  )
}

// ── Main page ──────────────────────────────────────────────────────────────────
export default function DashboardPage() {
  const { user, updateBalance, updateSubscription } = useAuthStore()
  const [files, setFiles] = useState<File[]>([])
  const [baselineSpreadsheet, setBaselineSpreadsheet] = useState<File | null>(null)
  const [baselineHeaders, setBaselineHeaders] = useState<string[] | null>(null)
  const [allowEditPastValues, setAllowEditPastValues] = useState(false)
  const [showModal, setShowModal] = useState(false)
  const [documentType, setDocumentType] = useState<DocumentType>('sov')
  const [activeJobId, setActiveJobId] = useState<string | null>(null)
  const [job, setJob] = useState<JobState | null>(null)
  const [validationMsg, setValidationMsg] = useState<string | null>(null)
  const [usageWarning, setUsageWarning] = useState<UsageWarning | null>(null)
  const [isPaywalled, setIsPaywalled] = useState(false)
  const [showInbox, setShowInbox] = useState(false)
  const [inboxDocIds, setInboxDocIds] = useState<string[]>([])  // selected ingest doc IDs for extraction

  const { event, reset: resetJobProgress } = useJobProgress(activeJobId)

  useEffect(() => {
    api.get('/payments/usage-warning').then(r => setUsageWarning(r.data)).catch(() => {})
  }, [])

  // ── Restore active job on page reload ──────────────────────────────────────
  useEffect(() => {
    const stored = localStorage.getItem(_ACTIVE_JOB_KEY)
    if (!stored) return
    try {
      const { jobId } = JSON.parse(stored)
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
        prev ? {
          ...prev,
          status: 'complete',
          progress: 100,
          message: 'Extraction complete!',
          downloadUrl: event.download_url,
          results: event.results,
          fields: event.fields,
          cost: event.cost,
          baselineUpdateMode: !!event.baseline_update_mode,
          outputFilename: event.output_filename,
        } : null
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

  const onDocumentDrop = useCallback(async (acceptedFiles: File[], fileRejections: FileRejection[]) => {
    const valid: File[] = []
    let unsupportedDirectCount = 0
    let spreadsheetInWrongBoxCount = 0
    let oversizedZipCount = 0
    let unreadableZipCount = 0
    let ignoredZipEntryCount = 0
    let zipWithNoSupportedFilesCount = 0

    for (const rejection of fileRejections) {
      const rejectedName = rejection.file.name.toLowerCase()
      const rejectedExt = rejectedName.includes('.') ? rejectedName.split('.').pop() ?? '' : ''
      if (_SPREADSHEET_EXTENSIONS.has(rejectedExt)) spreadsheetInWrongBoxCount += 1
      else unsupportedDirectCount += 1
    }

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

      if (droppedFile.size > _MAX_FILE_SIZE_BYTES) {
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
          const type = _EXTENSION_TO_MIME[entryExt] || 'application/octet-stream'
          valid.push(new File([blob], entryFileName, { type, lastModified: Date.now() }))
          extractedFromThisZip += 1
        }

        if (extractedFromThisZip === 0) zipWithNoSupportedFilesCount += 1
      } catch {
        unreadableZipCount += 1
      }
    }

    const issues: string[] = []
    if (spreadsheetInWrongBoxCount > 0) {
      issues.push(`${spreadsheetInWrongBoxCount} spreadsheet${spreadsheetInWrongBoxCount > 1 ? 's belong' : ' belongs'} in the existing spreadsheet box`)
    }
    if (unsupportedDirectCount > 0) {
      issues.push(`${unsupportedDirectCount} unsupported file${unsupportedDirectCount > 1 ? 's' : ''} skipped`)
    }
    if (oversizedZipCount > 0) {
      issues.push(`${oversizedZipCount} file${oversizedZipCount > 1 ? 's' : ''} exceeded 5 MB`)
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

  const onBaselineDrop = useCallback(async (acceptedFiles: File[], fileRejections: FileRejection[]) => {
    if (fileRejections.length > 0) {
      setValidationMsg('Existing spreadsheet must be a valid .xlsx or .csv file.')
      return
    }

    const newSpreadsheet = acceptedFiles[0]
    if (!newSpreadsheet) return

    setValidationMsg(null)
    setBaselineSpreadsheet(newSpreadsheet)
    setBaselineHeaders(null)
    setAllowEditPastValues(false)

    try {
      const fd = new FormData()
      fd.append('file', newSpreadsheet)
      const res = await api.post('/documents/spreadsheet-headers', fd)
      setBaselineHeaders(res.data.headers)
    } catch {
      setValidationMsg('Could not read spreadsheet headers — make sure the file is a valid .xlsx or .csv')
      setBaselineSpreadsheet(null)
      setBaselineHeaders(null)
      setAllowEditPastValues(false)
    }
  }, [])

  const {
    getRootProps: getDocumentRootProps,
    getInputProps: getDocumentInputProps,
    isDragActive: isDocumentDragActive,
  } = useDropzone({
    onDrop: onDocumentDrop,
    accept: _DOCUMENT_ACCEPT,
    multiple: true,
    noKeyboard: true,
  })

  const {
    getRootProps: getBaselineRootProps,
    getInputProps: getBaselineInputProps,
    isDragActive: isBaselineDragActive,
  } = useDropzone({
    onDrop: onBaselineDrop,
    accept: _BASELINE_ACCEPT,
    multiple: false,
    noKeyboard: true,
  })

  const handleProcess = () => {
    if (!files.length && !baselineSpreadsheet && !inboxDocIds.length) { setValidationMsg('Upload at least one supported file.'); return }
    if (documentType === 'sov' && baselineHeaders && baselineHeaders.length > 0) {
      if (!files.length && !inboxDocIds.length) { setValidationMsg('Upload at least one source file to update the spreadsheet.'); return }
      setValidationMsg(null)
      const fields: ExtractionField[] = baselineHeaders.map(h => ({ name: h, description: '' }))
      handleExtract(fields, 'xlsx', '')
      return
    }
    if (!files.length && !inboxDocIds.length) { setValidationMsg('Upload at least one supported file.'); return }
    setValidationMsg(null)
    if (documentType === 'quickbooks') {
      handleExtract(
        QUICKBOOKS_FIELDS,
        'xlsx',
        'Extract accounting-ready transaction fields from each document. Return Date, Description, and Amount. Use the invoice or transaction date as Date, the vendor name or payee as Description, and the total amount due or transaction amount as a positive number in Amount. If a field is not present in the source, leave it blank.',
      )
    } else {
      setShowModal(true)
    }
  }

  // ── Ingest inbox handlers ──────────────────────────────────────────────────
  const handleInboxSelect = (docs: { id: string; filename: string }[]) => {
    setInboxDocIds(docs.map(d => d.id))
    setFiles([])  // clear regular uploads when using inbox
    setShowModal(true)  // open extraction fields modal
  }

  const handleIngestExtract = async (fields: ExtractionField[], _format: ExportFormat, instructions: string) => {
    if (inboxDocIds.length === 0) return
    setShowModal(false)
    setActiveJobId(null)
    setJob({ jobId: '', status: 'queued', progress: 0, message: 'Processing inbox documents…', total_docs: inboxDocIds.length, completed_docs: 0 })

    try {
      const res = await api.post('/ingest/inbox/extract', {
        document_ids: inboxDocIds,
        fields: fields.map(f => ({ name: f.name, description: f.description })),
        instructions: instructions.trim(),
        format: 'xlsx',
        pipeline: documentType === 'sov' ? 'sov' : 'auto',
      })

      const jobId = res.data.job_id
      localStorage.setItem(_ACTIVE_JOB_KEY, JSON.stringify({ jobId }))
      setJob((p) => p ? { ...p, jobId, status: 'processing' } : null)
      setActiveJobId(jobId)
      setInboxDocIds([])

      if (res.data.usage) {
        updateSubscription({ pages_used_this_period: res.data.usage.pages_used })
        api.get('/payments/usage-warning').then(r => setUsageWarning(r.data)).catch(() => {})
      }
    } catch (err: any) {
      const detail = err.response?.data?.detail
      const msg = typeof detail === 'string' ? detail : 'Failed to start extraction'
      setJob((p) => p ? { ...p, status: 'error', message: 'Error', error: msg } : null)
      setInboxDocIds([])
    }
  }

  const handleExtract = async (fields: ExtractionField[], format: ExportFormat, instructions: string) => {
    // If we have inbox docs selected, use the ingest extraction path
    if (inboxDocIds.length > 0) {
      return handleIngestExtract(fields, format, instructions)
    }

    trackEvent('extraction_start', {
      field_count: fields.length,
      format,
      file_count: files.length,
      has_instructions: !!instructions.trim(),
      baseline_update_mode: !!baselineSpreadsheet,
      allow_edit_past_values: !!baselineSpreadsheet && allowEditPastValues,
    })
    setShowModal(false)
    setActiveJobId(null)
    setJob({ jobId: '', status: 'queued', progress: 0, message: 'Uploading files…', total_docs: files.length, completed_docs: 0 })

    extractAbortRef.current?.abort()
    const ac = new AbortController()
    extractAbortRef.current = ac

    try {
      const fd = new FormData()
      files.forEach((f) => fd.append('files', f))
      if (baselineSpreadsheet) {
        fd.append('baseline_spreadsheet', baselineSpreadsheet)
        fd.append('baseline_update_mode', 'true')
        fd.append('allow_edit_past_values', allowEditPastValues ? 'true' : 'false')
      } else {
        fd.append('baseline_update_mode', 'false')
        fd.append('allow_edit_past_values', 'false')
      }
      fd.append('pipeline', documentType === 'sov' ? 'sov' : 'general')
      fd.append('fields', JSON.stringify(fields))
      fd.append('instructions', instructions.trim())
      fd.append('format', 'xlsx')

      const res = await api.post('/documents/extract', fd, { signal: ac.signal })
      extractAbortRef.current = null

      const jobId = res.data.job_id
      localStorage.setItem(_ACTIVE_JOB_KEY, JSON.stringify({ jobId }))
      setJob((p) => p ? { ...p, jobId, status: 'processing' } : null)
      setActiveJobId(jobId)

      if (res.data.usage) {
        updateSubscription({ pages_used_this_period: res.data.usage.pages_used })
        api.get('/payments/usage-warning').then(r => setUsageWarning(r.data)).catch(() => {})
      }
    } catch (err: unknown) {
      extractAbortRef.current = null
      const ae = err as { code?: string; name?: string }
      if (ae?.code === 'ERR_CANCELED' || ae?.name === 'CanceledError') {
        return
      }
      const e = err as { response?: { data?: { detail?: unknown }; status?: number } }
      const detail = e.response?.data?.detail
      const status = e.response?.status
      const paywallDetail =
        detail && typeof detail === 'object' && detail !== null && 'type' in detail
          ? (detail as { type?: string; message?: string })
          : null

      if (status === 402 && (paywallDetail?.type === 'page_limit_reached' || paywallDetail?.type === 'credit_limit_reached')) {
        setJob((p) => p ? { ...p, status: 'error', message: 'Page limit reached', error: paywallDetail.message } : null)
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

  const handleCancel = () => {
    const id = job?.jobId
    extractAbortRef.current?.abort()
    extractAbortRef.current = null
    resetJobProgress()
    localStorage.removeItem(_ACTIVE_JOB_KEY)
    setJob(null)
    setActiveJobId(null)
    setFiles([])
    setBaselineSpreadsheet(null)
    setBaselineHeaders(null)
    setAllowEditPastValues(false)
    if (id) {
      void api.delete(`/documents/job/${id}`).catch(() => {})
    }
  }

  const handleNew = () => {
    localStorage.removeItem(_ACTIVE_JOB_KEY)
    setJob(null)
    setActiveJobId(null)
    setFiles([])
    setBaselineSpreadsheet(null)
    setBaselineHeaders(null)
    setAllowEditPastValues(false)
    setValidationMsg(null)
    setIsPaywalled(false)
  }

  const isProcessing = job !== null && job.status !== 'complete' && job.status !== 'error'

  const extractAbortRef = useRef<AbortController | null>(null)
  const submitBtnRef = useRef<HTMLButtonElement>(null)
  const showModalRef = useRef(showModal)
  showModalRef.current = showModal
  const filesLengthRef = useRef(files.length)
  filesLengthRef.current = files.length
  const isProcessingRef = useRef(isProcessing)
  isProcessingRef.current = isProcessing

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
          <h1 className="text-xl font-semibold text-foreground">Upload Data from any File</h1>
          <p className="text-muted-foreground text-sm mt-0.5">Upload PDFs, PNGs, JPEGs, or ZIPs (up to 5 MB each) — each page counts toward your monthly limit</p>
        </div>
        <div className="flex items-center gap-2">
          {usageWarning && (
            <>
              <span className="text-xs text-muted-foreground">{usageWarning.pages_used.toLocaleString()}/{usageWarning.pages_limit.toLocaleString()} pages</span>
              <Badge
                variant={usageWarning.usage_percent >= 80 ? 'destructive' : 'blue'}
                className="font-mono text-[11px]"
              >
                {(usageWarning.tier || user?.subscription_tier || 'free').charAt(0).toUpperCase() + (usageWarning.tier || user?.subscription_tier || 'free').slice(1)}
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
              You've used {usageWarning.pages_used.toLocaleString()} of {usageWarning.pages_limit.toLocaleString()} pages this month
            </p>
            <p className="text-xs text-muted-foreground mt-0.5">
              {usageWarning.overage_rate_cents_per_page
                ? `Extra pages cost $${(usageWarning.overage_rate_cents_per_page / 100).toFixed(3)} each.`
                : 'You\'ll be blocked when you hit the limit.'
              }
              {' '}Upgrade to {usageWarning.next_tier.display_name} for {usageWarning.next_tier.pages_per_month.toLocaleString()} pages at ${(usageWarning.next_tier.price_monthly / 100).toFixed(0)}/mo.
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
              Free limit reached ({usageWarning.pages_limit.toLocaleString()} pages/month)
            </p>
            <p className="text-xs text-muted-foreground mt-0.5">
              Upgrade to Starter for 7,500 pages/month starting at $69/mo.
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
                <p className="text-[11px] text-muted-foreground mt-0.5">PDF, PNG, JPEG, or ZIP (up to 5 MB)</p>
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
                setBaselineSpreadsheet(null)
                setBaselineHeaders(null)
                setAllowEditPastValues(false)
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

      {/* Drop zones — stable grid; baseline col hidden via CSS (not unmount) to keep doc zone mounted */}
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-4 mb-4">

        {/* Baseline spreadsheet — always in DOM, hidden for non-SOV tabs */}
        <div className={cn(documentType !== 'sov' && 'hidden')}>
          <p className="text-xs text-muted-foreground mb-2">Existing spreadsheet</p>
          <div
            {...getBaselineRootProps()}
            className={cn(
              'border-2 border-dashed rounded-xl p-6 text-center cursor-pointer transition-colors bg-white h-[200px] flex items-center justify-center',
              isBaselineDragActive
                ? 'border-emerald-500 bg-emerald-500/5'
                : 'border-emerald-500/30 hover:border-emerald-500 hover:bg-emerald-500/5'
            )}
          >
            <input {...getBaselineInputProps()} />
            <div className="flex flex-col items-center gap-3">
              <div className={cn(
                'w-12 h-12 rounded-xl flex items-center justify-center transition-colors',
                isBaselineDragActive ? 'bg-emerald-500/20 text-emerald-600' : 'bg-emerald-500/10 text-emerald-600'
              )}>
                <FileSpreadsheet size={22} />
              </div>
              {isBaselineDragActive ? (
                <p className="text-emerald-600 font-medium">Drop the spreadsheet here</p>
              ) : (
                <div>
                  <p className="text-foreground font-medium">Upload the existing spreadsheet</p>
                  <p className="text-muted-foreground text-sm mt-1">
                    XLSX or CSV only. We use this as the workbook to update or append to.
                  </p>
                </div>
              )}
            </div>
          </div>
        </div>

        {/* Source documents — always mounted; full-width when baseline is hidden */}
        <div className={cn(documentType !== 'sov' && 'sm:col-span-2')}>
          <p className="text-xs text-muted-foreground mb-2">
            {documentType === 'sov' ? 'Source documents' : 'Documents to extract from'}
          </p>
          <div
            {...getDocumentRootProps({
              onClick: documentType === 'sov' ? (e: React.MouseEvent) => {
                e.stopPropagation()
                setShowInbox(true)
              } : undefined,
            } as any)}
            className={cn(
              'border-2 border-dashed rounded-xl p-6 text-center cursor-pointer transition-colors bg-white h-[200px] flex items-center justify-center',
              isDocumentDragActive
                ? 'border-primary bg-primary/5'
                : 'border-border hover:border-primary/40 hover:bg-accent/30'
            )}
          >
            <input {...getDocumentInputProps()} data-doc-input />
            <div className="flex flex-col items-center gap-3">
              <div className={cn(
                'w-12 h-12 rounded-xl flex items-center justify-center transition-colors',
                isDocumentDragActive ? 'bg-primary/20 text-primary' : 'bg-primary/10 text-primary'
              )}>
                <Upload size={22} />
              </div>
              {isDocumentDragActive ? (
                <p className="text-primary font-medium">Drop files here</p>
              ) : (
                <div>
                  <p className="text-foreground font-medium">
                    {documentType === 'sov' ? 'Upload the documents to extract from' : 'Drag and drop your files here'}
                  </p>
                  <p className="text-muted-foreground text-sm mt-1">
                    PDFs, images, Outlook emails, text, HTML, JSON, XML, and ZIP are supported.
                  </p>
                </div>
              )}
            </div>
          </div>
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

      {/* Baseline spreadsheet indicator (SOV mode) */}
      {documentType === 'sov' && baselineSpreadsheet && (
        <div className="mt-3 bg-emerald-500/5 border border-emerald-500/25 rounded-xl px-4 py-3">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2 min-w-0">
              <FileSpreadsheet size={14} className="text-emerald-500 flex-shrink-0" />
              <div className="min-w-0">
                <p className="text-sm font-medium text-foreground truncate">{baselineSpreadsheet.name}</p>
                {baselineHeaders && baselineHeaders.length > 0 ? (
                  <p className="text-[11px] text-emerald-600 mt-0.5">
                    Baseline — {baselineHeaders.length} column{baselineHeaders.length !== 1 ? 's' : ''} detected: {baselineHeaders.slice(0, 4).join(', ')}{baselineHeaders.length > 4 ? ` +${baselineHeaders.length - 4} more` : ''}
                  </p>
                ) : (
                  <p className="text-[11px] text-muted-foreground mt-0.5">Reading headers…</p>
                )}
              </div>
            </div>
            <button
              onClick={() => {
                setBaselineSpreadsheet(null)
                setBaselineHeaders(null)
                setAllowEditPastValues(false)
              }}
              className="text-xs text-muted-foreground hover:text-red-400 transition-colors ml-2 flex-shrink-0"
            >
              <X size={13} />
            </button>
          </div>
          {baselineHeaders && baselineHeaders.length > 0 && (
            <div className="mt-3 border-t border-emerald-500/15 pt-3">
              <div className="flex items-start gap-3">
                <Checkbox
                  id="allow-edit-past-values"
                  checked={allowEditPastValues}
                  disabled={isProcessing}
                  onCheckedChange={(checked) => setAllowEditPastValues(checked === true)}
                  className="mt-0.5"
                />
                <div className="space-y-1">
                  <Label htmlFor="allow-edit-past-values" className="text-sm text-foreground cursor-pointer">
                    Allow editing past values
                  </Label>
                  <p className="text-[11px] text-muted-foreground">
                    When enabled, matched rows overwrite the mapped spreadsheet columns. When disabled, matched rows stay unchanged, new rows still append, and missing old rows are flagged.
                  </p>
                </div>
              </div>
            </div>
          )}
        </div>
      )}

      {/* File count */}
      {files.length > 0 && (
        <div className="mt-3 bg-card border border-border rounded-xl px-4 py-3 flex items-center justify-between">
          <span className="text-sm font-medium text-foreground">
            {documentType === 'sov' ? 'Source documents' : 'Files'}: {files.length} file{files.length > 1 ? 's' : ''} selected
          </span>
          <button onClick={() => setFiles([])} className="text-xs text-muted-foreground hover:text-red-400 transition-colors">
            Clear all
          </button>
        </div>
      )}

      {/* CTA — only render when there is something to act on or a job is active */}
      {(files.length > 0 || baselineSpreadsheet || isProcessing) && (
        <Button
          ref={submitBtnRef}
          onClick={handleProcess}
          disabled={isProcessing || (documentType === 'sov' && baselineSpreadsheet !== null && baselineHeaders === null)}
          size="lg"
          className="mt-4 w-full shadow-lg shadow-primary/25"
        >
          {isProcessing ? (
            <>
              <Loader2 size={15} className="animate-spin" />
              Processing…
            </>
          ) : documentType === 'sov' && baselineSpreadsheet && baselineHeaders ? (
            files.length > 0
              ? `Update ${baselineSpreadsheet.name} from ${files.length} file${files.length > 1 ? 's' : ''}`
              : 'Upload source files to update the workbook'
          ) : files.length > 0 ? (
            documentType === 'quickbooks'
              ? `Extract ${files.length} file${files.length > 1 ? 's' : ''} for QuickBooks`
              : `Choose fields & extract ${files.length} file${files.length > 1 ? 's' : ''}`
          ) : (
            'Upload files to get started'
          )}
        </Button>
      )}

      {/* Progress */}
      {job && job.status !== 'complete' && <ProgressBar job={job} onCancel={handleCancel} />}

      {/* Results */}
      {job?.status === 'complete' && job.results && job.fields && (
        <SpreadsheetViewer
          results={job.results}
          fields={job.fields}
          jobId={job.jobId}
          format={'xlsx'}
          outputFilename={job.outputFilename}
          onNew={handleNew}
          paywalled={isPaywalled}
          documentType={documentType}
          baselineUpdateMode={job.baselineUpdateMode}
        />
      )}

      <ExtractionFieldsModal
        open={showModal}
        onClose={() => { setShowModal(false); setInboxDocIds([]) }}
        onConfirm={handleExtract}
        defaultFormat={'xlsx'}
        documentType={documentType}
      />

      <InboxModal
        open={showInbox}
        onClose={() => setShowInbox(false)}
        onSelectDocuments={handleInboxSelect}
        onUploadDirect={() => {
          // Trigger the document file picker after a short delay
          setTimeout(() => {
            const input = document.querySelector<HTMLInputElement>('input[data-doc-input]')
            input?.click()
          }, 100)
        }}
      />
    </div>
  )
}
