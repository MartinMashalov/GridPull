import { useState, useCallback, useEffect, useRef } from 'react'
import { useDropzone } from 'react-dropzone'
import {
  Upload, Loader2, CheckCircle2, AlertCircle, X, FileText,
  Download, ArrowRight, Lock, Trash2, Eye, CreditCard,
  Sparkles, FilePlus2,
} from 'lucide-react'
import { useAuthStore } from '@/store/authStore'
import { useFormJobStore } from '@/store/formJobStore'
import { useNavigate } from 'react-router-dom'
import api from '@/lib/api'
import { Button } from '@/components/ui/button'
import { Separator } from '@/components/ui/separator'
import { cn } from '@/lib/utils'


const _SOURCE_TYPES = new Set([
  'application/pdf', 'image/png', 'image/jpeg', 'image/webp', 'image/gif', 'image/bmp', 'image/tiff',
  'text/plain', 'text/markdown', 'text/html', 'application/json', 'application/xml', 'text/xml',
  'message/rfc822', 'application/vnd.ms-outlook',
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

function formatBytes(bytes: number) {
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(0)} KB`
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`
}

export default function FormFillingPage() {
  const { user } = useAuthStore()
  const { jobs, addJob, updateJob, dismissJob } = useFormJobStore()
  const navigate = useNavigate()
  const [targetForm, setTargetForm] = useState<File | null>(null)
  const [sourceFiles, setSourceFiles] = useState<File[]>([])
  const [validationMsg, setValidationMsg] = useState<string | null>(null)

  const onDropTarget = useCallback((accepted: File[]) => {
    const f = accepted[0]
    if (!f) return
    const ext = f.name.split('.').pop()?.toLowerCase()
    if (ext !== 'pdf') { setValidationMsg('Target form must be a PDF file.'); return }
    setValidationMsg(null)
    setTargetForm(f)
  }, [])

  const onDropSource = useCallback((accepted: File[]) => {
    const valid: File[] = []
    let skipped = 0
    for (const f of accepted) {
      const ext = f.name.split('.').pop()?.toLowerCase() || ''
      if (_SOURCE_TYPES.has(f.type) || _SOURCE_EXTENSIONS.has(ext)) valid.push(f)
      else skipped++
    }
    if (skipped > 0) setValidationMsg(`${skipped} unsupported file${skipped > 1 ? 's' : ''} skipped.`)
    else setValidationMsg(null)
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
      'application/pdf': ['.pdf'], 'image/png': ['.png'], 'image/jpeg': ['.jpg', '.jpeg'],
      'image/webp': ['.webp'], 'image/gif': ['.gif'], 'image/bmp': ['.bmp'],
      'image/tiff': ['.tif', '.tiff'], 'text/plain': ['.txt'], 'text/markdown': ['.md', '.markdown'],
      'text/html': ['.html', '.htm'], 'application/json': ['.json'], 'application/xml': ['.xml'],
      'message/rfc822': ['.eml', '.emlx'], 'application/vnd.ms-outlook': ['.msg'],
      'application/octet-stream': ['.msg'],
    },
    multiple: true,
    noKeyboard: true,
  })

  const handleFormSubmit = async (e: React.FormEvent<HTMLFormElement>) => {
    e.preventDefault()
    if (!targetForm || sourceFiles.length === 0) {
      setValidationMsg('Upload both a target form and at least one source file.')
      return
    }
    setValidationMsg(null)
    const jobId = `form-job-${++_jobCounter}`
    addJob({ id: jobId, targetName: targetForm.name, sourceCount: sourceFiles.length, status: 'processing' })
    const capturedTarget = targetForm
    const capturedSources = [...sourceFiles]
    setTargetForm(null)
    setSourceFiles([])
    const fd = new FormData()
    fd.append('target_form', capturedTarget)
    capturedSources.forEach(f => fd.append('source_files', f))
    try {
      const res = await api.post('/form-filling/fill', fd, { responseType: 'blob', timeout: 300000 })
      const disposition = res.headers['content-disposition'] || ''
      const filenameMatch = disposition.match(/filename="?([^";\n]+)"?/)
      const name = filenameMatch?.[1] || `filled_${capturedTarget.name}`
      triggerDownload(res.data, name)
      useFormJobStore.getState().updateJob(jobId, { status: 'complete', resultBlob: res.data, resultName: name })
    } catch (err: unknown) {
      const e = err as { response?: { data?: Blob; status?: number } }
      let msg = 'Form filling failed — please try again'
      if (e.response?.data instanceof Blob && e.response.data.type === 'application/json') {
        try { const text = await e.response.data.text(); const json = JSON.parse(text); msg = json.detail?.message || json.detail || msg } catch { /* ignore */ }
      } else if (e.response?.status) msg = `Form filling failed (HTTP ${e.response.status})`
      useFormJobStore.getState().updateJob(jobId, { status: 'error', errorMsg: msg })
    }
  }

  useEffect(() => {
    const timers = jobs
      .filter(j => j.status === 'complete')
      .map(j => setTimeout(() => useFormJobStore.getState().dismissJob(j.id), 2000))
    return () => timers.forEach(clearTimeout)
  }, [jobs.map(j => `${j.id}:${j.status}`).join(',')])

  const hasProcessing = jobs.some(j => j.status === 'processing')
  const isReady = !!(targetForm && sourceFiles.length > 0)
  const isFormDisabled = !isReady || hasProcessing || !!(user && !user.has_card)

  const submitRef = useRef<HTMLButtonElement>(null)
  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if (e.key === 'Enter' && !e.shiftKey && !isFormDisabled) {
        e.preventDefault()
        submitRef.current?.click()
      }
    }
    window.addEventListener('keydown', handler)
    return () => window.removeEventListener('keydown', handler)
  }, [isFormDisabled])

  return (
    <form className="relative p-4 sm:p-8 max-w-4xl mx-auto" onSubmit={handleFormSubmit}>
      <div className="pointer-events-none absolute inset-x-0 top-0 h-48 bg-gradient-to-b from-primary/[0.03] to-transparent rounded-t-xl" />

      {/* ── Header ───────────────────────────────────────────────── */}
      <div className="relative border-b border-border pb-5 mb-6 flex flex-col sm:flex-row sm:items-start justify-between gap-2">
        <div>
          <h1 className="text-xl font-semibold text-foreground">Form Filling</h1>
          <p className="text-muted-foreground text-sm mt-1 max-w-2xl leading-relaxed">
            Fill carrier intake forms and supplemental applications automatically.
            Upload a blank PDF form on the left, then add your source documents (intake forms, prior policies, loss runs) on the right.
            AI reads your source docs and fills every field on the carrier's form. Supports ACORD forms, carrier-specific apps, and any fillable PDF.
          </p>
        </div>
      </div>

      {/* ── Security strip ───────────────────────────────────────── */}
      <div className="mb-5 hidden sm:flex flex-wrap items-center justify-center gap-x-5 gap-y-1.5 text-[11px] text-muted-foreground">
        <span className="flex items-center gap-1.5"><Lock size={11} className="text-emerald-500" /> Encrypted in transit</span>
        <span className="flex items-center gap-1.5"><Trash2 size={11} className="text-emerald-500" /> Files deleted after processing</span>
        <span className="flex items-center gap-1.5"><Eye size={11} className="text-emerald-500" /> No human access to your documents</span>
      </div>

      {/* ── Card required banner ─────────────────────────────────── */}
      {user && !user.has_card && (
        <div className="relative mb-4 rounded-xl border border-primary/30 bg-primary/5 p-4 flex items-center gap-3">
          <div className="w-8 h-8 rounded-lg bg-primary/15 flex items-center justify-center flex-shrink-0">
            <CreditCard size={15} className="text-primary" />
          </div>
          <div className="flex-1 min-w-0">
            <p className="text-sm font-medium text-foreground">Credit card required</p>
            <p className="text-xs text-muted-foreground mt-0.5">
              Add a credit card to fill forms. You won't be charged on the free plan.
            </p>
          </div>
          <Button size="sm" type="button" onClick={() => navigate('/settings?tab=payment')} className="flex-shrink-0">
            Add Card <ArrowRight size={12} className="ml-1" />
          </Button>
        </div>
      )}

      {/* ── Drop zones ───────────────────────────────────────────── */}
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-4 mb-4">

        {/* Left — Target form */}
        <div>
          <p className="text-xs text-muted-foreground mb-2">Target form (PDF)</p>
          <div
            {...targetDropzone.getRootProps()}
            className={cn(
              'border-2 border-dashed rounded-xl p-6 text-center cursor-pointer transition-colors bg-white h-[200px] flex items-center justify-center',
              targetDropzone.isDragActive
                ? 'border-primary bg-primary/5'
                : targetForm
                  ? 'border-border bg-card hover:bg-muted/40'
                  : 'border-border hover:border-primary/40 hover:bg-accent/30'
            )}
          >
            <input {...targetDropzone.getInputProps()} />
            {targetForm ? (
              <div className="flex flex-col items-center gap-3 w-full">
                <div className="w-12 h-12 rounded-xl bg-primary/10 flex items-center justify-center">
                  <FileText size={22} className="text-primary" />
                </div>
                <div>
                  <p className="text-sm font-medium text-foreground truncate max-w-[200px]">{targetForm.name}</p>
                  <p className="text-[11px] text-muted-foreground mt-0.5">{formatBytes(targetForm.size)}</p>
                </div>
                <button
                  type="button"
                  onClick={e => { e.stopPropagation(); setTargetForm(null) }}
                  className="text-xs text-muted-foreground hover:text-red-400 transition-colors flex items-center gap-1 mt-1"
                >
                  <X size={12} /> Remove
                </button>
              </div>
            ) : (
              <div className="flex flex-col items-center gap-3">
                <div className={cn(
                  'w-12 h-12 rounded-xl flex items-center justify-center',
                  targetDropzone.isDragActive ? 'bg-primary/20' : 'bg-primary/10'
                )}>
                  <FilePlus2 size={22} className="text-primary" />
                </div>
                {targetDropzone.isDragActive ? (
                  <p className="text-primary font-medium">Drop your form here</p>
                ) : (
                  <div>
                    <p className="text-foreground font-medium">Drop a PDF form here</p>
                    <p className="text-muted-foreground text-sm mt-1">or click to browse</p>
                  </div>
                )}
              </div>
            )}
          </div>
        </div>

        {/* Right — Source documents */}
        <div>
          <p className="text-xs text-muted-foreground mb-2">Source documents</p>
          <div
            {...sourceDropzone.getRootProps()}
            className={cn(
              'border-2 border-dashed rounded-xl p-6 text-center cursor-pointer transition-colors bg-white h-[200px] flex items-center justify-center',
              sourceDropzone.isDragActive
                ? 'border-primary bg-primary/5'
                : sourceFiles.length > 0
                  ? 'border-border bg-card hover:bg-muted/40'
                  : 'border-border hover:border-primary/40 hover:bg-accent/30'
            )}
          >
            <input {...sourceDropzone.getInputProps()} />
            {sourceFiles.length > 0 ? (
              <div className="flex flex-col items-center gap-2 w-full overflow-hidden">
                <div className="w-12 h-12 rounded-xl bg-primary/10 flex items-center justify-center flex-shrink-0">
                  <Upload size={22} className="text-primary" />
                </div>
                <div className="flex-shrink-0">
                  <p className="text-sm font-medium text-foreground">{sourceFiles.length} file{sourceFiles.length > 1 ? 's' : ''}</p>
                  <p className="text-[11px] text-muted-foreground mt-0.5">Click or drop to add more</p>
                </div>
                <div className="w-full space-y-1 max-h-[52px] overflow-y-auto text-left">
                  {sourceFiles.map((f, i) => (
                    <div key={`${f.name}-${f.size}-${i}`} className="flex items-center justify-between text-xs px-2 py-1 bg-muted rounded group">
                      <span className="truncate text-muted-foreground flex-1">{f.name}</span>
                      <button
                        type="button"
                        onClick={e => { e.stopPropagation(); setSourceFiles(prev => prev.filter((_, idx) => idx !== i)) }}
                        className="opacity-0 group-hover:opacity-100 text-muted-foreground hover:text-red-400 transition-all ml-1 flex-shrink-0"
                      >
                        <X size={12} />
                      </button>
                    </div>
                  ))}
                </div>
              </div>
            ) : (
              <div className="flex flex-col items-center gap-3">
                <div className={cn(
                  'w-12 h-12 rounded-xl flex items-center justify-center',
                  sourceDropzone.isDragActive ? 'bg-primary/20' : 'bg-primary/10'
                )}>
                  <Upload size={22} className="text-primary" />
                </div>
                {sourceDropzone.isDragActive ? (
                  <p className="text-primary font-medium">Drop files here</p>
                ) : (
                  <div>
                    <p className="text-foreground font-medium">Drop source files here</p>
                    <p className="text-muted-foreground text-sm mt-1">PDFs, images, TXT, or Markdown</p>
                  </div>
                )}
              </div>
            )}
          </div>
        </div>
      </div>

      {/* ── Validation ───────────────────────────────────────────── */}
      {validationMsg && (
        <p className="mb-3 text-xs text-red-500 flex items-center gap-1.5">
          <AlertCircle size={12} /> {validationMsg}
        </p>
      )}

      {/* ── Submit — only when files are ready ───────────────────── */}
      {(isReady || hasProcessing) && (
        <Button
          ref={submitRef}
          type="submit"
          disabled={isFormDisabled}
          size="lg"
          className="w-full shadow-lg shadow-primary/25 gap-2"
        >
          {hasProcessing ? (
            <><Loader2 size={15} className="animate-spin" /> Processing…</>
          ) : (
            <><Sparkles size={15} /> Fill form using {sourceFiles.length} source file{sourceFiles.length > 1 ? 's' : ''}</>
          )}
        </Button>
      )}

      {/* ── Jobs queue ───────────────────────────────────────────── */}
      {jobs.length > 0 && (
        <div className="mt-6 space-y-3">
          <Separator />
          <div className="flex items-center justify-between pt-1">
            <p className="text-xs font-semibold text-muted-foreground uppercase tracking-wider">Processing Queue</p>
            <p className="text-[11px] text-muted-foreground">{jobs.length} job{jobs.length > 1 ? 's' : ''}</p>
          </div>
          <div className="space-y-2">
            {jobs.map(job => (
              <div
                key={job.id}
                className={cn(
                  'flex items-center gap-3 rounded-xl border p-3.5 transition-colors',
                  job.status === 'processing' && 'bg-card border-border',
                  job.status === 'complete' && 'bg-emerald-50/60 border-emerald-200',
                  job.status === 'error' && 'bg-red-50/60 border-red-200',
                )}
              >
                <div className={cn(
                  'w-8 h-8 rounded-lg flex items-center justify-center flex-shrink-0',
                  job.status === 'processing' && 'bg-primary/10',
                  job.status === 'complete' && 'bg-emerald-100',
                  job.status === 'error' && 'bg-red-100',
                )}>
                  {job.status === 'processing' && <Loader2 size={14} className="animate-spin text-primary" />}
                  {job.status === 'complete' && <CheckCircle2 size={14} className="text-emerald-600" />}
                  {job.status === 'error' && <AlertCircle size={14} className="text-red-500" />}
                </div>

                <div className="flex-1 min-w-0">
                  <p className="text-sm font-medium text-foreground truncate">{job.targetName}</p>
                  <p className="text-[11px] text-muted-foreground mt-0.5">
                    {job.status === 'processing' && `Filling from ${job.sourceCount} source file${job.sourceCount > 1 ? 's' : ''}…`}
                    {job.status === 'complete' && (
                      <span className="text-emerald-600 font-medium flex items-center gap-1">
                        <Download size={10} /> Downloaded successfully
                      </span>
                    )}
                    {job.status === 'error' && job.errorMsg}
                  </p>
                </div>

                {job.status === 'complete' && job.resultBlob && (
                  <Button
                    type="button"
                    size="sm"
                    variant="outline"
                    className="flex-shrink-0 h-7 text-xs gap-1 border-emerald-300 text-emerald-700 hover:bg-emerald-50"
                    onClick={() => triggerDownload(job.resultBlob!, job.resultName!)}
                  >
                    <Download size={11} /> Save again
                  </Button>
                )}

                <button
                  type="button"
                  onClick={() => dismissJob(job.id)}
                  className="flex-shrink-0 w-6 h-6 rounded-md flex items-center justify-center text-muted-foreground hover:bg-muted hover:text-foreground transition-colors"
                >
                  <X size={13} />
                </button>
              </div>
            ))}
          </div>
        </div>
      )}
    </form>
  )
}
