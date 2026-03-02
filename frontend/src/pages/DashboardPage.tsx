import { useState, useCallback, useEffect } from 'react'
import { useDropzone } from 'react-dropzone'
import { Upload, FileText, X, Loader2 } from 'lucide-react'
import { useAuthStore } from '@/store/authStore'
import ExtractionFieldsModal from '@/components/ExtractionFieldsModal'
import SpreadsheetViewer from '@/components/SpreadsheetViewer'
import api from '@/lib/api'
import toast from 'react-hot-toast'
import { formatFileSize } from '@/lib/utils'
import { useJobProgress } from '@/hooks/useJobProgress'

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

// ── Progress bar sub-component ────────────────────────────────────────────────
function ProgressBar({ job }: { job: JobState }) {
  const isError = job.status === 'error'
  const isComplete = job.status === 'complete'

  const steps = [
    { key: 'processing', label: 'Upload & read' },
    { key: 'extracting', label: 'AI extract' },
    { key: 'generating', label: 'Build sheet' },
    { key: 'complete', label: 'Done' },
  ]
  const order = ['queued', 'processing', 'extracting', 'generating', 'complete']
  const curIdx = order.indexOf(job.status)

  return (
    <div className="mt-6 bg-white rounded-2xl border border-blue-100 overflow-hidden animate-fade-in">
      {/* Header row */}
      <div className="px-6 py-4 border-b border-blue-50">
        <div className="flex items-center justify-between mb-2.5">
          <span className="text-sm font-semibold text-slate-800">
            {isError ? 'Extraction Failed' : isComplete ? 'Extraction Complete!' : 'Processing…'}
          </span>
          <span className="text-xs font-semibold text-blue-600 tabular-nums">{job.progress}%</span>
        </div>
        {/* Bar */}
        <div className="w-full h-2.5 bg-blue-50 rounded-full overflow-hidden">
          <div
            className={`h-full rounded-full transition-all duration-700 ease-out ${
              isError ? 'bg-red-500' : isComplete ? 'bg-emerald-500' : 'bg-blue-500'
            }`}
            style={{ width: `${job.progress}%` }}
          />
        </div>
        {/* Step indicators */}
        <div className="mt-3 flex items-center gap-0">
          {steps.map((step, i) => {
            const stepIdx = order.indexOf(step.key)
            const isDone = !isError && curIdx > stepIdx
            const isActive = !isError && curIdx === stepIdx
            const isErr = isError && stepIdx === curIdx
            return (
              <div key={step.key} className="flex items-center flex-1 last:flex-none">
                <div className="flex flex-col items-center gap-1 flex-1">
                  <div
                    className={`w-2 h-2 rounded-full transition-colors ${
                      isDone ? 'bg-emerald-500' :
                      isActive ? 'bg-blue-500 ring-2 ring-blue-200' :
                      isErr ? 'bg-red-500' : 'bg-blue-100'
                    }`}
                  />
                  <span className={`text-[10px] font-medium whitespace-nowrap ${
                    isDone ? 'text-emerald-600' :
                    isActive ? 'text-blue-600' :
                    isErr ? 'text-red-500' : 'text-slate-400'
                  }`}>
                    {step.label}
                  </span>
                </div>
                {i < steps.length - 1 && (
                  <div className={`h-px flex-1 mx-1 mt-[-8px] transition-colors ${isDone ? 'bg-emerald-300' : 'bg-blue-100'}`} />
                )}
              </div>
            )
          })}
        </div>
      </div>

      {/* Status message */}
      <div className="px-6 py-3">
        {isError && job.error ? (
          <p className="text-sm text-red-600 bg-red-50 border border-red-100 rounded-lg px-3 py-2">
            {job.error}
          </p>
        ) : (
          <p className="text-xs text-slate-400 text-center">{job.message}</p>
        )}
      </div>
    </div>
  )
}

// ── Main page ─────────────────────────────────────────────────────────────────
export default function DashboardPage() {
  const { user, updateCredits } = useAuthStore()
  const [files, setFiles] = useState<File[]>([])
  const [showModal, setShowModal] = useState(false)
  const [exportFormat, setExportFormat] = useState<ExportFormat>('xlsx')
  const [activeJobId, setActiveJobId] = useState<string | null>(null)
  const [job, setJob] = useState<JobState | null>(null)

  // SSE hook — subscribes when activeJobId is set
  const { event } = useJobProgress(activeJobId)

  // React to SSE events
  useEffect(() => {
    if (!event) return

    if (event.type === 'progress') {
      setJob((prev) =>
        prev
          ? {
              ...prev,
              status: event.status as JobState['status'],
              progress: event.progress,
              message: event.message ?? prev.message,
            }
          : null
      )
    }

    if (event.type === 'complete') {
      setJob((prev) =>
        prev
          ? {
              ...prev,
              status: 'complete',
              progress: 100,
              message: 'Extraction complete!',
              downloadUrl: event.download_url,
              results: event.results,
              fields: event.fields,
              creditsUsed: event.credits_used,
            }
          : null
      )

      // Update credits in store
      if (event.credits_used != null && user) {
        updateCredits(Math.max(0, (user.credits ?? 0) - event.credits_used))
      }

      // Auto-download
      if (event.download_url && activeJobId) {
        const token = useAuthStore.getState().token ?? ''
        fetch(event.download_url, {
          headers: { Authorization: `Bearer ${token}` },
        })
          .then((r) => r.blob())
          .then((blob) => {
            const url = URL.createObjectURL(blob)
            const a = document.createElement('a')
            a.href = url
            a.download = `gridpull_export.${exportFormat}`
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
        prev
          ? { ...prev, status: 'error', message: 'Extraction failed', error: event.error }
          : null
      )
      toast.error(event.error ?? 'Extraction failed')
    }
  }, [event])

  // Dropzone
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

      setJob((p) => p ? { ...p, progress: 5, message: 'Uploading…' } : null)

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

      // Activating the SSE connection
      setActiveJobId(jobId)
    } catch (err: any) {
      const msg = err.response?.data?.detail ?? 'Upload failed'
      setJob((p) => p ? { ...p, status: 'error', message: 'Error', error: msg } : null)
      toast.error(msg)
    }
  }

  const isProcessing = job !== null && job.status !== 'complete' && job.status !== 'error'

  return (
    <div className="p-8 max-w-5xl mx-auto">
      {/* Header */}
      <div className="mb-6">
        <h1 className="text-2xl font-bold text-slate-900">PDF Extractor</h1>
        <p className="text-slate-500 mt-1">Upload PDFs, define fields, and export to spreadsheet</p>
      </div>

      {/* Top bar */}
      <div className="flex items-center justify-between mb-5">
        <div className="text-sm text-slate-500">
          Balance: <span className="font-semibold text-slate-800">${(user?.credits ?? 0).toFixed(2)}</span>
        </div>
        <div className="flex items-center gap-3">
          <span className="text-sm text-slate-500">Format:</span>
          <div className="flex bg-white border border-blue-100 rounded-lg overflow-hidden shadow-sm">
            {(['xlsx', 'csv'] as ExportFormat[]).map((fmt) => (
              <button
                key={fmt}
                onClick={() => setExportFormat(fmt)}
                className={`px-4 py-1.5 text-sm font-medium transition-colors ${
                  exportFormat === fmt ? 'bg-blue-600 text-white' : 'text-slate-600 hover:bg-blue-50'
                }`}
              >
                {fmt.toUpperCase()}
              </button>
            ))}
          </div>
        </div>
      </div>

      {/* Drop zone */}
      <div
        {...getRootProps()}
        className={`border-2 border-dashed rounded-2xl p-12 text-center cursor-pointer transition-all duration-200 ${
          isDragActive
            ? 'border-blue-400 bg-blue-100'
            : 'border-blue-200 bg-white hover:border-blue-300 hover:bg-blue-50'
        }`}
      >
        <input {...getInputProps()} />
        <div className="flex flex-col items-center gap-4">
          <div className={`w-16 h-16 rounded-2xl flex items-center justify-center transition-colors ${isDragActive ? 'bg-blue-200' : 'bg-blue-50'}`}>
            <Upload size={28} className={isDragActive ? 'text-blue-600' : 'text-blue-400'} />
          </div>
          {isDragActive ? (
            <p className="text-blue-600 font-medium text-lg">Drop your PDFs here</p>
          ) : (
            <div>
              <p className="text-slate-700 font-medium text-lg">Drop PDF files here</p>
              <p className="text-slate-400 text-sm mt-1">or click to browse — multiple files supported</p>
            </div>
          )}
        </div>
      </div>

      {/* File list */}
      {files.length > 0 && (
        <div className="mt-4 bg-white rounded-xl border border-blue-100 overflow-hidden shadow-sm">
          <div className="px-4 py-3 border-b border-blue-50 flex items-center justify-between">
            <span className="text-sm font-medium text-slate-700">
              {files.length} file{files.length > 1 ? 's' : ''} selected
            </span>
            <button onClick={() => setFiles([])} className="text-xs text-slate-400 hover:text-red-500 transition-colors">
              Clear all
            </button>
          </div>
          <div className="divide-y divide-blue-50 max-h-60 overflow-y-auto scrollbar-thin">
            {files.map((file, i) => (
              <div key={i} className="flex items-center gap-3 px-4 py-2.5">
                <div className="w-8 h-8 bg-red-50 rounded-lg flex items-center justify-center flex-shrink-0">
                  <FileText size={15} className="text-red-500" />
                </div>
                <div className="flex-1 min-w-0">
                  <p className="text-sm font-medium text-slate-800 truncate">{file.name}</p>
                  <p className="text-xs text-slate-400">{formatFileSize(file.size)}</p>
                </div>
                <button onClick={() => setFiles((p) => p.filter((_, j) => j !== i))} className="text-slate-300 hover:text-red-500 transition-colors">
                  <X size={15} />
                </button>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* CTA button */}
      <button
        onClick={handleProcess}
        disabled={!files.length || isProcessing}
        className="mt-5 w-full py-3.5 bg-blue-600 hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed text-white font-semibold rounded-xl transition-colors text-sm shadow-sm"
      >
        {isProcessing ? (
          <span className="flex items-center justify-center gap-2">
            <Loader2 size={16} className="animate-spin" />
            Processing…
          </span>
        ) : (
          'Extract & Export'
        )}
      </button>

      {/* Real-time progress bar */}
      {job && job.status !== 'complete' && <ProgressBar job={job} />}

      {/* Spreadsheet viewer — shown after completion */}
      {job?.status === 'complete' && job.results && job.fields && (
        <SpreadsheetViewer
          results={job.results}
          fields={job.fields}
          jobId={job.jobId}
          format={exportFormat}
          creditsUsed={job.creditsUsed}
        />
      )}

      {/* Error state */}
      {job?.status === 'error' && (
        <ProgressBar job={job} />
      )}

      {/* Modal */}
      <ExtractionFieldsModal
        open={showModal}
        onClose={() => setShowModal(false)}
        onConfirm={handleExtract}
        defaultFormat={exportFormat}
      />
    </div>
  )
}
