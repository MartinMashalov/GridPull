import { useState, useCallback, useEffect, useRef } from 'react'
import { useDropzone } from 'react-dropzone'
import { Upload, Loader2, CheckCircle2, AlertCircle, X } from 'lucide-react'
import { useAuthStore } from '@/store/authStore'
import ExtractionFieldsModal from '@/components/ExtractionFieldsModal'
import SpreadsheetViewer from '@/components/SpreadsheetViewer'
import api from '@/lib/api'
import { useJobProgress } from '@/hooks/useJobProgress'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { Progress } from '@/components/ui/progress'
import { cn } from '@/lib/utils'

export type ExportFormat = 'xlsx' | 'csv'

export interface ExtractionField {
  name: string
  description: string
}

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

// ── Progress bar ───────────────────────────────────────────────────────────────
function ProgressBar({ job, onCancel }: { job: JobState; onCancel: () => void }) {
  const isError = job.status === 'error'
  const isComplete = job.status === 'complete'
  const totalDocs = job.total_docs ?? 0
  const completedDocs = job.completed_docs ?? 0

  // Drive bar from doc count so it only moves on real completions.
  // While waiting (no docs counted yet) use an indeterminate pulse.
  const barPct = isComplete ? 100 : totalDocs > 0 ? Math.round((completedDocs / totalDocs) * 100) : 0
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
            {totalDocs > 0 && (
              <span className="text-xs text-muted-foreground tabular-nums">
                {completedDocs}/{totalDocs} file{totalDocs !== 1 ? 's' : ''}
              </span>
            )}
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
  const { user, updateBalance } = useAuthStore()
  const [files, setFiles] = useState<File[]>([])
  const [showModal, setShowModal] = useState(false)
  const [exportFormat, setExportFormat] = useState<ExportFormat>('xlsx')
  const [activeJobId, setActiveJobId] = useState<string | null>(null)
  const [job, setJob] = useState<JobState | null>(null)
  const [validationMsg, setValidationMsg] = useState<string | null>(null)

  const { event } = useJobProgress(activeJobId)

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
      setJob((prev) =>
        prev ? { ...prev, status: 'complete', progress: 100, message: 'Extraction complete!', downloadUrl: event.download_url, results: event.results, fields: event.fields, cost: event.cost } : null
      )
      if (event.cost != null && user) {
        updateBalance(Math.max(0, (user.balance ?? 0) - event.cost))
      }
      if (event.download_url) {
        const token = useAuthStore.getState().token ?? ''
        const a = document.createElement('a')
        a.href = `${event.download_url}?token=${encodeURIComponent(token)}`
        a.download = `export.${exportFormat}`
        document.body.appendChild(a)
        a.click()
        document.body.removeChild(a)
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

  const onDrop = useCallback((acceptedFiles: File[]) => {
    const valid = acceptedFiles.filter((f) => _ACCEPTED_TYPES.has(f.type))
    if (valid.length !== acceptedFiles.length) {
      setValidationMsg('Only PDF, PNG, and JPEG files are accepted.')
    } else {
      setValidationMsg(null)
    }
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
    },
    multiple: true,
    noKeyboard: true,
  })

  const handleProcess = () => {
    if (!files.length) { setValidationMsg('Upload at least one PDF file.'); return }
    setValidationMsg(null)
    setShowModal(true)
  }

  const handleExtract = async (fields: ExtractionField[], format: ExportFormat) => {
    setShowModal(false)
    setExportFormat(format)
    setActiveJobId(null)
    setJob({ jobId: '', status: 'queued', progress: 0, message: 'Uploading files…', total_docs: files.length, completed_docs: 0 })

    try {
      const fd = new FormData()
      files.forEach((f) => fd.append('files', f))
      fd.append('fields', JSON.stringify(fields))
      fd.append('format', format)

      const res = await api.post('/documents/extract', fd)

      const jobId = res.data.job_id
      localStorage.setItem(_ACTIVE_JOB_KEY, JSON.stringify({ jobId, format: exportFormat }))
      setJob((p) => p ? { ...p, jobId, status: 'processing' } : null)
      setActiveJobId(jobId)
    } catch (err: any) {
      const detail = err.response?.data?.detail
      const status = err.response?.status
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
  }

  const isProcessing = job !== null && job.status !== 'complete' && job.status !== 'error'

  // Ref to the submit button so we can programmatically click it on Enter
  const submitBtnRef = useRef<HTMLButtonElement>(null)
  const showModalRef = useRef(showModal)
  showModalRef.current = showModal

  // Use document capture so the event fires before any child handler (dropzone etc.) can block it
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') { setFiles([]); return }
      if (e.key === 'Enter' && !showModalRef.current) {
        submitBtnRef.current?.click()
      }
    }
    document.addEventListener('keydown', onKey, true)
    return () => document.removeEventListener('keydown', onKey, true)
  }, [])

  return (
    <div className="relative p-8 max-w-4xl mx-auto">
      {/* Subtle gradient wash at the top */}
      <div className="pointer-events-none absolute inset-x-0 top-0 h-48 bg-gradient-to-b from-primary/[0.03] to-transparent rounded-t-xl" />

      {/* Header */}
      <div className="relative border-b border-border pb-5 mb-6 flex items-start justify-between">
        <div>
          <h1 className="text-xl font-semibold text-foreground">Extract Data from PDFs</h1>
          <p className="text-muted-foreground text-sm mt-0.5">Upload your files, choose the fields to extract, and download a clean spreadsheet</p>
        </div>
        <div className="flex items-center gap-2">
          <span className="text-xs text-muted-foreground">Balance:</span>
          <Badge variant="blue" className="font-mono">${(user?.balance ?? 0).toFixed(2)}</Badge>
        </div>
      </div>

      {/* Format toggle */}
      <div className="flex items-center gap-3 mb-4">
        <span className="text-xs text-muted-foreground">Format</span>
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
      </div>

      {/* Drop zone */}
      <div
        {...getRootProps()}
        className={cn(
          'border-2 border-dashed rounded-xl p-14 text-center cursor-pointer transition-all duration-200',
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
              <p className="text-muted-foreground text-sm mt-1">Supports PDF, PNG, and JPEG — upload multiple files at once</p>
            </div>
          )}
        </div>
      </div>

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
        ) : (
          'Extract & Export'
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
          cost={job.cost}
          onNew={handleNew}
        />
      )}

      <ExtractionFieldsModal
        open={showModal}
        onClose={() => setShowModal(false)}
        onConfirm={handleExtract}
        defaultFormat={exportFormat}
      />
    </div>
  )
}
