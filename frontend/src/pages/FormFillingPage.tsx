import { useState, useCallback, useRef, useEffect } from 'react'
import { useDropzone } from 'react-dropzone'
import { Upload, Loader2, CheckCircle2, AlertCircle, X, FileText, Download, Clipboard, ArrowRight, Lock, Trash2, Eye, File, CreditCard } from 'lucide-react'
import { useAuthStore } from '@/store/authStore'
import { useNavigate } from 'react-router-dom'
import api from '@/lib/api'
import { Button } from '@/components/ui/button'
import { cn } from '@/lib/utils'

type FormJobStatus = 'processing' | 'complete' | 'error'

interface FormJob {
  id: string
  targetName: string
  sourceCount: number
  status: FormJobStatus
  resultBlob?: Blob
  resultName?: string
  errorMsg?: string
}

const _SOURCE_TYPES = new Set([
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
const _SOURCE_EXTENSIONS = new Set([
  'pdf', 'png', 'jpg', 'jpeg', 'webp', 'gif', 'bmp', 'tif', 'tiff',
  'txt', 'md', 'markdown', 'html', 'htm', 'json', 'xml', 'eml', 'emlx', 'msg',
])

let _jobCounter = 0

function triggerDownload(blob: Blob, name: string) {
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = name
  document.body.appendChild(a)
  a.click()
  document.body.removeChild(a)
  URL.revokeObjectURL(url)
}

export default function FormFillingPage() {
  const { user } = useAuthStore()
  const navigate = useNavigate()
  const [targetForm, setTargetForm] = useState<File | null>(null)
  const [sourceFiles, setSourceFiles] = useState<File[]>([])
  const [validationMsg, setValidationMsg] = useState<string | null>(null)
  const [jobs, setJobs] = useState<FormJob[]>([])

  const onDropTarget = useCallback((accepted: File[]) => {
    const f = accepted[0]
    if (!f) return
    const ext = f.name.split('.').pop()?.toLowerCase()
    if (ext !== 'pdf') {
      setValidationMsg('Target form must be a PDF file.')
      return
    }
    setValidationMsg(null)
    setTargetForm(f)
  }, [])

  const onDropSource = useCallback((accepted: File[]) => {
    const valid: File[] = []
    let skipped = 0
    for (const f of accepted) {
      const ext = f.name.split('.').pop()?.toLowerCase() || ''
      if (_SOURCE_TYPES.has(f.type) || _SOURCE_EXTENSIONS.has(ext)) {
        valid.push(f)
      } else {
        skipped++
      }
    }
    if (skipped > 0) {
      setValidationMsg(`${skipped} unsupported file${skipped > 1 ? 's' : ''} skipped. Supported: PDFs, images, Outlook emails, TXT, Markdown, HTML, JSON, and XML.`)
    } else {
      setValidationMsg(null)
    }
    setSourceFiles(prev => {
      const seen = new Set(prev.map(f => f.name + f.size))
      return [...prev, ...valid.filter(f => !seen.has(f.name + f.size))]
    })
  }, [])

  const targetDropzone = useDropzone({
    onDrop: onDropTarget,
    accept: { 'application/pdf': ['.pdf'] },
    multiple: false,
    noKeyboard: true,
  })

  const sourceDropzone = useDropzone({
    onDrop: onDropSource,
    accept: {
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
    },
    multiple: true,
    noKeyboard: true,
  })

  const handleFill = async () => {
    if (!targetForm || sourceFiles.length === 0) {
      setValidationMsg('Upload both a target form and at least one source file.')
      return
    }
    setValidationMsg(null)

    const jobId = `form-job-${++_jobCounter}`
    const job: FormJob = {
      id: jobId,
      targetName: targetForm.name,
      sourceCount: sourceFiles.length,
      status: 'processing',
    }
    setJobs(prev => [job, ...prev])

    // Capture files and clear the form for next upload
    const capturedTarget = targetForm
    const capturedSources = [...sourceFiles]
    setTargetForm(null)
    setSourceFiles([])

    const fd = new FormData()
    fd.append('target_form', capturedTarget)
    capturedSources.forEach(f => fd.append('source_files', f))

    try {
      const res = await api.post('/form-filling/fill', fd, {
        responseType: 'blob',
        timeout: 300000,
      })

      const disposition = res.headers['content-disposition'] || ''
      const filenameMatch = disposition.match(/filename="?([^";\n]+)"?/)
      const name = filenameMatch?.[1] || `filled_${capturedTarget.name}`

      // Auto-download
      triggerDownload(res.data, name)

      setJobs(prev => prev.map(j =>
        j.id === jobId ? { ...j, status: 'complete' as const, resultBlob: res.data, resultName: name } : j
      ))
    } catch (err: unknown) {
      const e = err as { response?: { data?: Blob; status?: number } }
      let msg = 'Form filling failed — please try again'
      if (e.response?.data instanceof Blob && e.response.data.type === 'application/json') {
        try {
          const text = await e.response.data.text()
          const json = JSON.parse(text)
          msg = json.detail?.message || json.detail || msg
        } catch { /* ignore */ }
      } else if (e.response?.status) {
        msg = `Form filling failed (HTTP ${e.response.status})`
      }
      setJobs(prev => prev.map(j =>
        j.id === jobId ? { ...j, status: 'error' as const, errorMsg: msg } : j
      ))
    }
  }

  const dismissJob = (jobId: string) => {
    setJobs(prev => prev.filter(j => j.id !== jobId))
  }

  const hasProcessing = jobs.some(j => j.status === 'processing')

  const handleFormSubmit = (e: React.FormEvent<HTMLFormElement>) => {
    e.preventDefault()
    if (targetForm && sourceFiles.length > 0 && !(user && !user.has_card)) {
      handleFill()
    }
  }

  return (
    <form className="relative p-4 sm:p-8 max-w-4xl mx-auto" onSubmit={handleFormSubmit}>
      <div className="pointer-events-none absolute inset-x-0 top-0 h-48 bg-gradient-to-b from-primary/[0.03] to-transparent rounded-t-xl" />

      {/* Header */}
      <div className="relative border-b border-border pb-5 mb-6">
        <h1 className="text-xl font-semibold text-foreground">Fill PDF Forms</h1>
        <p className="text-muted-foreground text-sm mt-0.5">
          Upload a PDF form and source documents — each form fill uses 1 credit, with a 5 MB max per file
        </p>
      </div>

      {/* How it works */}
      {!targetForm && sourceFiles.length === 0 && jobs.length === 0 && (
        <div className="mb-6 hidden sm:block">
          <p className="text-xs font-semibold text-muted-foreground uppercase tracking-wider mb-3">How it works</p>
          <div className="grid grid-cols-3 gap-4">
            <div className="flex flex-col items-center text-center gap-2">
              <div className="w-8 h-8 rounded-lg bg-primary/10 flex items-center justify-center">
                <Clipboard size={14} className="text-primary" />
              </div>
              <div>
                <p className="text-xs font-medium text-foreground">1. Upload a PDF form</p>
                <p className="text-[11px] text-muted-foreground mt-0.5">Any fillable PDF with form fields</p>
              </div>
            </div>
            <div className="flex flex-col items-center text-center gap-2">
              <div className="w-8 h-8 rounded-lg bg-primary/10 flex items-center justify-center">
                <Upload size={14} className="text-primary" />
              </div>
              <div>
                <p className="text-xs font-medium text-foreground">2. Add source documents</p>
                <p className="text-[11px] text-muted-foreground mt-0.5">PDFs, images, or text files with the data</p>
              </div>
            </div>
            <div className="flex flex-col items-center text-center gap-2">
              <div className="w-8 h-8 rounded-lg bg-primary/10 flex items-center justify-center">
                <Download size={14} className="text-primary" />
              </div>
              <div>
                <p className="text-xs font-medium text-foreground">3. Download filled form</p>
                <p className="text-[11px] text-muted-foreground mt-0.5">Every field populated with extracted data</p>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Security strip */}
      {jobs.length === 0 && (
        <div className="mb-5 hidden sm:flex flex-wrap items-center justify-center gap-x-5 gap-y-1.5 text-[11px] text-muted-foreground">
          <span className="flex items-center gap-1.5"><Lock size={11} className="text-emerald-500" /> Encrypted in transit</span>
          <span className="flex items-center gap-1.5"><Trash2 size={11} className="text-emerald-500" /> Files deleted after processing</span>
          <span className="flex items-center gap-1.5"><Eye size={11} className="text-emerald-500" /> No human access to your documents</span>
        </div>
      )}

      {/* Card required banner */}
      {user && !user.has_card && (
        <div className="relative mb-4 rounded-xl border border-primary/30 bg-primary/5 p-4 flex items-center gap-3">
          <div className="w-8 h-8 rounded-lg bg-primary/15 flex items-center justify-center flex-shrink-0">
            <CreditCard size={15} className="text-primary" />
          </div>
          <div className="flex-1 min-w-0">
            <p className="text-sm font-medium text-foreground">Credit card required</p>
            <p className="text-xs text-muted-foreground mt-0.5">
              Add a credit card to start filling forms. You won't be charged on the free plan.
            </p>
          </div>
          <Button size="sm" onClick={() => navigate('/settings?tab=payment')} className="flex-shrink-0">
            Add Card <ArrowRight size={12} className="ml-1" />
          </Button>
        </div>
      )}

      {/* Two-column drop zones */}
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-4 mb-4">
        {/* Target form drop zone */}
        <div>
          <span className="text-xs text-muted-foreground block mb-2">Target form (PDF)</span>
          <div
            {...targetDropzone.getRootProps()}
            className={cn(
              'border-2 border-dashed rounded-xl p-6 text-center cursor-pointer transition-all duration-200 min-h-[160px] flex flex-col items-center justify-center',
              'bg-white',
              targetDropzone.isDragActive
                ? 'border-primary bg-primary/5'
                : targetForm
                  ? 'border-emerald-300 bg-emerald-50/50'
                  : 'border-border hover:border-primary/40 hover:bg-accent/30'
            )}
          >
            <input {...targetDropzone.getInputProps()} />
            {targetForm ? (
              <div className="flex flex-col items-center gap-2">
                <div className="w-10 h-10 rounded-xl bg-emerald-100 flex items-center justify-center">
                  <CheckCircle2 size={18} className="text-emerald-500" />
                </div>
                <div>
                  <p className="text-sm font-medium text-foreground">1 file uploaded</p>
                  <p className="text-[11px] text-muted-foreground mt-0.5">Click or drop to replace</p>
                </div>
              </div>
            ) : (
              <div className="flex flex-col items-center gap-2">
                <div className={cn(
                  'w-10 h-10 rounded-xl flex items-center justify-center transition-colors',
                  targetDropzone.isDragActive ? 'bg-primary/20 text-primary' : 'bg-primary/10 text-primary'
                )}>
                  <Clipboard size={18} />
                </div>
                {targetDropzone.isDragActive ? (
                  <p className="text-primary font-medium text-sm">Drop your form here</p>
                ) : (
                  <div>
                    <p className="text-foreground font-medium text-sm">Drop a PDF form here</p>
                    <p className="text-muted-foreground text-[11px] mt-0.5">or click to browse</p>
                  </div>
                )}
              </div>
            )}
          </div>
        </div>

        {/* Source files drop zone */}
        <div>
          <span className="text-xs text-muted-foreground block mb-2">Source documents</span>
          <div
            {...sourceDropzone.getRootProps()}
            className={cn(
              'border-2 border-dashed rounded-xl p-6 text-center cursor-pointer transition-all duration-200 min-h-[160px] flex flex-col items-center justify-center',
              'bg-white',
              sourceDropzone.isDragActive
                ? 'border-primary bg-primary/5'
                : sourceFiles.length > 0
                  ? 'border-blue-300 bg-blue-50/50'
                  : 'border-border hover:border-primary/40 hover:bg-accent/30'
            )}
          >
            <input {...sourceDropzone.getInputProps()} />
            {sourceFiles.length > 0 ? (
              <div className="flex flex-col items-center gap-2">
                <div className="w-10 h-10 rounded-xl bg-blue-100 flex items-center justify-center">
                  <Upload size={18} className="text-blue-500" />
                </div>
                <div>
                  <p className="text-sm font-medium text-foreground">{sourceFiles.length} file{sourceFiles.length > 1 ? 's' : ''} uploaded</p>
                  <p className="text-[11px] text-muted-foreground mt-0.5">Click or drop to add more</p>
                </div>
              </div>
            ) : (
              <div className="flex flex-col items-center gap-2">
                <div className={cn(
                  'w-10 h-10 rounded-xl flex items-center justify-center transition-colors',
                  sourceDropzone.isDragActive ? 'bg-primary/20 text-primary' : 'bg-primary/10 text-primary'
                )}>
                  <Upload size={18} />
                </div>
                {sourceDropzone.isDragActive ? (
                  <p className="text-primary font-medium text-sm">Drop files here</p>
                ) : (
                  <div>
                    <p className="text-foreground font-medium text-sm">Drop source files here</p>
                    <p className="text-muted-foreground text-[11px] mt-0.5">PDF, images, TXT, or Markdown</p>
                  </div>
                )}
              </div>
            )}
          </div>
        </div>
      </div>

      {/* Validation */}
      {validationMsg && (
        <p className="mb-3 text-xs text-red-500">{validationMsg}</p>
      )}

      {/* Mobile security */}
      {jobs.length === 0 && (
        <p className="mb-3 text-center text-[11px] text-muted-foreground sm:hidden">
          <Lock size={10} className="inline text-emerald-500 mr-1" />
          Encrypted · files deleted after processing · no human access
        </p>
      )}

      {/* CTA */}
      <Button
        type="submit"
        disabled={!targetForm || sourceFiles.length === 0 || !!(user && !user.has_card)}
        size="lg"
        className="w-full shadow-lg shadow-primary/25"
      >
        {targetForm && sourceFiles.length > 0 ? (
          `Fill form using ${sourceFiles.length} source file${sourceFiles.length > 1 ? 's' : ''}`
        ) : (
          'Upload files to get started'
        )}
      </Button>

      {/* Background jobs */}
      {jobs.length > 0 && (
        <div className="mt-5 space-y-3">
          {jobs.map(job => (
            <div
              key={job.id}
              className={cn(
                'bg-card border rounded-xl overflow-hidden animate-fade-in',
                job.status === 'processing' && 'border-border',
                job.status === 'complete' && 'border-emerald-200',
                job.status === 'error' && 'border-red-200',
              )}
            >
              <div className="px-5 py-4">
                {job.status === 'processing' && (
                  <>
                    <div className="flex items-center justify-between mb-2">
                      <div className="flex items-center gap-3">
                        <div className="relative">
                          <div className="w-8 h-8 rounded-full border-2 border-primary/20 border-t-primary animate-spin" />
                        </div>
                        <div>
                          <p className="text-sm font-medium text-foreground">Filling form...</p>
                          <p className="text-xs text-muted-foreground mt-0.5">{job.targetName}</p>
                        </div>
                      </div>
                    </div>
                    <p className="text-xs text-muted-foreground mt-2">
                      Extracting text and filling fields with AI. You can upload another form while this one processes.
                    </p>
                  </>
                )}

                {job.status === 'complete' && (
                  <div className="flex items-center justify-between">
                    <div className="flex items-center gap-3">
                      <div className="w-8 h-8 rounded-full bg-emerald-100 flex items-center justify-center flex-shrink-0">
                        <CheckCircle2 size={16} className="text-emerald-500" />
                      </div>
                      <div>
                        <p className="text-sm font-medium text-foreground">Form filled successfully</p>
                        <p className="text-xs text-muted-foreground mt-0.5">
                          {job.resultName} — {job.resultBlob ? `${(job.resultBlob.size / 1024).toFixed(0)} KB` : ''}
                        </p>
                      </div>
                    </div>
                    <div className="flex items-center gap-2">
                      {job.resultBlob && job.resultName && (
                        <Button size="sm" variant="outline" onClick={() => triggerDownload(job.resultBlob!, job.resultName!)}>
                          <Download size={13} className="mr-1.5" />
                          Download
                        </Button>
                      )}
                      <button onClick={() => dismissJob(job.id)} className="p-1.5 rounded-lg hover:bg-muted transition-colors">
                        <X size={14} className="text-muted-foreground" />
                      </button>
                    </div>
                  </div>
                )}

                {job.status === 'error' && (
                  <div className="flex items-center justify-between">
                    <div className="flex items-center gap-3">
                      <div className="w-8 h-8 rounded-full bg-red-100 flex items-center justify-center flex-shrink-0">
                        <AlertCircle size={16} className="text-red-400" />
                      </div>
                      <div>
                        <p className="text-sm font-medium text-foreground">Form filling failed</p>
                        <p className="text-xs text-red-400 mt-0.5">{job.errorMsg}</p>
                      </div>
                    </div>
                    <button onClick={() => dismissJob(job.id)} className="p-1.5 rounded-lg hover:bg-muted transition-colors">
                      <X size={14} className="text-muted-foreground" />
                    </button>
                  </div>
                )}
              </div>
            </div>
          ))}
        </div>
      )}
    </form>
  )
}
