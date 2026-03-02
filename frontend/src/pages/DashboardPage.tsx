import { useState, useCallback, useEffect } from 'react'
import { useDropzone } from 'react-dropzone'
import { Upload, FileText, X, Loader2, CheckCircle2, AlertCircle } from 'lucide-react'
import { useAuthStore } from '@/store/authStore'
import ExtractionFieldsModal from '@/components/ExtractionFieldsModal'
import SpreadsheetViewer from '@/components/SpreadsheetViewer'
import api from '@/lib/api'
import toast from 'react-hot-toast'
import { formatFileSize } from '@/lib/utils'
import { useJobProgress } from '@/hooks/useJobProgress'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
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
  downloadUrl?: string
  results?: Record<string, string>[]
  fields?: string[]
  creditsUsed?: number
  error?: string
}

// ── Progress bar ───────────────────────────────────────────────────────────────
function ProgressBar({ job }: { job: JobState }) {
  const isError = job.status === 'error'
  const isComplete = job.status === 'complete'

  const steps = [
    { key: 'processing', label: 'Upload' },
    { key: 'extracting', label: 'AI Extract' },
    { key: 'generating', label: 'Build' },
    { key: 'complete', label: 'Done' },
  ]
  const order = ['queued', 'processing', 'extracting', 'generating', 'complete']
  const curIdx = order.indexOf(job.status)

  return (
    <div className="mt-4 bg-card border border-border rounded-xl overflow-hidden animate-fade-in">
      <div className="px-5 py-4 border-b border-border">
        <div className="flex items-center justify-between mb-3">
          <span className="text-sm font-semibold flex items-center gap-2">
            {isComplete && <CheckCircle2 size={15} className="text-emerald-400" />}
            {isError && <AlertCircle size={15} className="text-red-400" />}
            {isError ? 'Extraction Failed' : isComplete ? 'Complete!' : 'Processing…'}
          </span>
          <span className="text-xs font-mono text-primary tabular-nums">{job.progress}%</span>
        </div>
        {/* Bar */}
        <div className="w-full h-1.5 bg-secondary rounded-full overflow-hidden">
          <div
            className={cn(
              'h-full rounded-full transition-all duration-700 ease-out',
              isError ? 'bg-red-500' : isComplete ? 'bg-emerald-500' : 'bg-primary'
            )}
            style={{ width: `${job.progress}%` }}
          />
        </div>
        {/* Steps */}
        <div className="mt-3 flex items-center">
          {steps.map((step, i) => {
            const stepIdx = order.indexOf(step.key)
            const isDone = !isError && curIdx > stepIdx
            const isActive = !isError && curIdx === stepIdx
            return (
              <div key={step.key} className="flex items-center flex-1 last:flex-none">
                <div className="flex flex-col items-center gap-1 flex-1">
                  <div className={cn(
                    'w-1.5 h-1.5 rounded-full transition-colors',
                    isDone ? 'bg-emerald-500' :
                    isActive ? 'bg-primary ring-2 ring-primary/30' :
                    isError && stepIdx === curIdx ? 'bg-red-500' : 'bg-secondary'
                  )} />
                  <span className={cn(
                    'text-[10px] font-medium whitespace-nowrap',
                    isDone ? 'text-emerald-500' :
                    isActive ? 'text-primary' : 'text-muted-foreground'
                  )}>
                    {step.label}
                  </span>
                </div>
                {i < steps.length - 1 && (
                  <div className={cn(
                    'h-px flex-1 mx-1 mt-[-10px] transition-colors',
                    isDone ? 'bg-emerald-500/40' : 'bg-border'
                  )} />
                )}
              </div>
            )
          })}
        </div>
      </div>
      <div className="px-5 py-2.5">
        {isError && job.error ? (
          <p className="text-xs text-red-400 bg-red-500/10 border border-red-500/20 rounded-lg px-3 py-2">
            {job.error}
          </p>
        ) : (
          <p className="text-xs text-muted-foreground text-center">{job.message}</p>
        )}
      </div>
    </div>
  )
}

// ── Main page ──────────────────────────────────────────────────────────────────
export default function DashboardPage() {
  const { user, updateCredits } = useAuthStore()
  const [files, setFiles] = useState<File[]>([])
  const [showModal, setShowModal] = useState(false)
  const [exportFormat, setExportFormat] = useState<ExportFormat>('xlsx')
  const [activeJobId, setActiveJobId] = useState<string | null>(null)
  const [job, setJob] = useState<JobState | null>(null)

  const { event } = useJobProgress(activeJobId)

  useEffect(() => {
    if (!event) return

    if (event.type === 'progress') {
      setJob((prev) =>
        prev ? { ...prev, status: event.status as JobState['status'], progress: event.progress, message: event.message ?? prev.message } : null
      )
    }

    if (event.type === 'complete') {
      setJob((prev) =>
        prev ? { ...prev, status: 'complete', progress: 100, message: 'Extraction complete!', downloadUrl: event.download_url, results: event.results, fields: event.fields, creditsUsed: event.credits_used } : null
      )
      if (event.credits_used != null && user) {
        updateCredits(Math.max(0, (user.credits ?? 0) - event.credits_used))
      }
      if (event.download_url && activeJobId) {
        const token = useAuthStore.getState().token ?? ''
        fetch(event.download_url, { headers: { Authorization: `Bearer ${token}` } })
          .then((r) => r.blob())
          .then((blob) => {
            const url = URL.createObjectURL(blob)
            const a = document.createElement('a')
            a.href = url
            a.download = `export.${exportFormat}`
            a.click()
            URL.revokeObjectURL(url)
          })
          .catch(() => {})
      }
      toast.success('Spreadsheet ready!')
      setFiles([])
    }

    if (event.type === 'error') {
      setJob((prev) =>
        prev ? { ...prev, status: 'error', message: 'Extraction failed', error: event.error } : null
      )
      toast.error(event.error ?? 'Extraction failed')
    }
  }, [event])

  const onDrop = useCallback((acceptedFiles: File[]) => {
    const pdfs = acceptedFiles.filter((f) => f.type === 'application/pdf')
    if (pdfs.length !== acceptedFiles.length) toast.error('Only PDF files are accepted')
    setFiles((prev) => {
      const seen = new Set(prev.map((f) => f.name + f.size))
      return [...prev, ...pdfs.filter((f) => !seen.has(f.name + f.size))]
    })
  }, [])

  const { getRootProps, getInputProps, isDragActive } = useDropzone({
    onDrop,
    accept: { 'application/pdf': ['.pdf'] },
    multiple: true,
  })

  const handleProcess = () => {
    if (!files.length) { toast.error('Upload at least one PDF'); return }
    setShowModal(true)
  }

  const handleExtract = async (fields: ExtractionField[], format: ExportFormat) => {
    setShowModal(false)
    setExportFormat(format)
    setActiveJobId(null)
    setJob({ jobId: '', status: 'queued', progress: 0, message: 'Uploading files…' })

    try {
      const fd = new FormData()
      files.forEach((f) => fd.append('files', f))
      fd.append('fields', JSON.stringify(fields))
      fd.append('format', format)

      const res = await api.post('/documents/extract', fd, {
        headers: { 'Content-Type': 'multipart/form-data' },
        onUploadProgress: (e) => {
          if (e.total) {
            const pct = Math.round((e.loaded / e.total) * 20)
            setJob((p) => p ? { ...p, progress: 5 + pct, message: 'Uploading files…' } : null)
          }
        },
      })

      const jobId = res.data.job_id
      setJob((p) => p ? { ...p, jobId, status: 'processing', progress: 25, message: 'Job queued — connecting…' } : null)
      setActiveJobId(jobId)
    } catch (err: any) {
      const msg = err.response?.data?.detail ?? 'Upload failed'
      setJob((p) => p ? { ...p, status: 'error', message: 'Error', error: msg } : null)
      toast.error(msg)
    }
  }

  const isProcessing = job !== null && job.status !== 'complete' && job.status !== 'error'

  return (
    <div className="p-8 max-w-4xl mx-auto">
      {/* Header */}
      <div className="mb-6 flex items-start justify-between">
        <div>
          <h1 className="text-xl font-semibold text-foreground">PDF Extractor</h1>
          <p className="text-muted-foreground text-sm mt-0.5">Upload PDFs, define fields, export to spreadsheet</p>
        </div>
        <div className="flex items-center gap-2">
          <span className="text-xs text-muted-foreground">Balance:</span>
          <Badge variant="blue" className="font-mono">${(user?.credits ?? 0).toFixed(2)}</Badge>
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
          isDragActive
            ? 'border-primary bg-primary/5'
            : 'border-border hover:border-primary/50 hover:bg-accent/50'
        )}
      >
        <input {...getInputProps()} />
        <div className="flex flex-col items-center gap-3">
          <div className={cn(
            'w-12 h-12 rounded-xl flex items-center justify-center transition-colors',
            isDragActive ? 'bg-primary/20' : 'bg-secondary'
          )}>
            <Upload size={22} className={isDragActive ? 'text-primary' : 'text-muted-foreground'} />
          </div>
          {isDragActive ? (
            <p className="text-primary font-medium">Drop your PDFs here</p>
          ) : (
            <div>
              <p className="text-foreground font-medium">Drop PDF files here</p>
              <p className="text-muted-foreground text-sm mt-1">or click to browse — multiple files supported</p>
            </div>
          )}
        </div>
      </div>

      {/* File list */}
      {files.length > 0 && (
        <div className="mt-3 bg-card border border-border rounded-xl overflow-hidden">
          <div className="px-4 py-2.5 border-b border-border flex items-center justify-between">
            <span className="text-xs font-medium text-muted-foreground">
              {files.length} file{files.length > 1 ? 's' : ''} selected
            </span>
            <button onClick={() => setFiles([])} className="text-xs text-muted-foreground hover:text-red-400 transition-colors">
              Clear all
            </button>
          </div>
          <div className="divide-y divide-border max-h-52 overflow-y-auto scrollbar-thin">
            {files.map((file, i) => (
              <div key={i} className="flex items-center gap-3 px-4 py-2.5">
                <div className="w-7 h-7 bg-red-500/10 rounded-lg flex items-center justify-center flex-shrink-0">
                  <FileText size={13} className="text-red-400" />
                </div>
                <div className="flex-1 min-w-0">
                  <p className="text-xs font-medium text-foreground truncate">{file.name}</p>
                  <p className="text-[11px] text-muted-foreground">{formatFileSize(file.size)}</p>
                </div>
                <button onClick={() => setFiles((p) => p.filter((_, j) => j !== i))} className="text-muted-foreground hover:text-red-400 transition-colors">
                  <X size={13} />
                </button>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* CTA */}
      <Button
        onClick={handleProcess}
        disabled={!files.length || isProcessing}
        size="lg"
        className="mt-4 w-full shadow-lg shadow-primary/10"
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
      {job && job.status !== 'complete' && <ProgressBar job={job} />}
      {job?.status === 'error' && <ProgressBar job={job} />}

      {/* Results */}
      {job?.status === 'complete' && job.results && job.fields && (
        <SpreadsheetViewer
          results={job.results}
          fields={job.fields}
          jobId={job.jobId}
          format={exportFormat}
          creditsUsed={job.creditsUsed}
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
