import { useState, useCallback } from 'react'
import { useDropzone } from 'react-dropzone'
import {
  Upload, Loader2, CheckCircle2, AlertCircle, X, FileText,
  Download, ArrowRight, Lock, Trash2, Eye, CreditCard,
  Sparkles, FilePlus2, ArrowRightLeft,
} from 'lucide-react'
import { useAuthStore } from '@/store/authStore'
import { useNavigate } from 'react-router-dom'
import api from '@/lib/api'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { Separator } from '@/components/ui/separator'
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
  const navigate = useNavigate()
  const [targetForm, setTargetForm] = useState<File | null>(null)
  const [sourceFiles, setSourceFiles] = useState<File[]>([])
  const [validationMsg, setValidationMsg] = useState<string | null>(null)
  const [jobs, setJobs] = useState<FormJob[]>([])

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
    setJobs(prev => [{ id: jobId, targetName: targetForm.name, sourceCount: sourceFiles.length, status: 'processing' }, ...prev])
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
      setJobs(prev => prev.map(j => j.id === jobId ? { ...j, status: 'complete' as const, resultBlob: res.data, resultName: name } : j))
    } catch (err: unknown) {
      const e = err as { response?: { data?: Blob; status?: number } }
      let msg = 'Form filling failed — please try again'
      if (e.response?.data instanceof Blob && e.response.data.type === 'application/json') {
        try { const text = await e.response.data.text(); const json = JSON.parse(text); msg = json.detail?.message || json.detail || msg } catch { /* ignore */ }
      } else if (e.response?.status) msg = `Form filling failed (HTTP ${e.response.status})`
      setJobs(prev => prev.map(j => j.id === jobId ? { ...j, status: 'error' as const, errorMsg: msg } : j))
    }
  }

  const dismissJob = (jobId: string) => setJobs(prev => prev.filter(j => j.id !== jobId))
  const hasProcessing = jobs.some(j => j.status === 'processing')
  const isFormDisabled = !targetForm || sourceFiles.length === 0 || hasProcessing || !!(user && !user.has_card)
  const isReady = !!(targetForm && sourceFiles.length > 0)

  return (
    <form className="p-4 sm:p-8 max-w-3xl mx-auto space-y-6" onSubmit={handleFormSubmit}>

      {/* ── Header ─────────────────────────────────────────────── */}
      <div>
        <div className="flex items-center gap-2 mb-1">
          <h1 className="text-xl font-semibold tracking-tight text-foreground">Fill PDF Forms</h1>
          <Badge variant="secondary" className="text-[10px] font-medium">1 credit per fill</Badge>
        </div>
        <p className="text-sm text-muted-foreground">
          Drop a blank form and source documents — AI fills every field automatically.
        </p>
      </div>

      {/* ── Card required banner ────────────────────────────────── */}
      {user && !user.has_card && (
        <div className="rounded-xl border border-primary/25 bg-primary/[0.04] p-4 flex items-center gap-3">
          <div className="w-9 h-9 rounded-lg bg-primary/10 flex items-center justify-center flex-shrink-0">
            <CreditCard size={16} className="text-primary" />
          </div>
          <div className="flex-1 min-w-0">
            <p className="text-sm font-semibold text-foreground">Credit card required</p>
            <p className="text-xs text-muted-foreground mt-0.5">Add a card to start — you won't be charged on the free plan.</p>
          </div>
          <Button size="sm" type="button" onClick={() => navigate('/settings?tab=payment')} className="flex-shrink-0 gap-1">
            Add Card <ArrowRight size={12} />
          </Button>
        </div>
      )}

      {/* ── Drop zones ──────────────────────────────────────────── */}
      <div className="grid grid-cols-1 sm:grid-cols-[1fr_auto_1fr] gap-3 items-center">

        {/* Left — Target form */}
        <div className="flex flex-col gap-1.5">
          <div className="flex items-center gap-1.5">
            <span className="text-xs font-medium text-foreground">Target form</span>
            <Badge variant="outline" className="text-[10px] py-0 px-1.5 font-normal text-muted-foreground">PDF only</Badge>
          </div>
          <div
            {...targetDropzone.getRootProps()}
            className={cn(
              'relative h-[168px] rounded-xl border-2 border-dashed cursor-pointer select-none',
              'flex flex-col items-center justify-center gap-3 px-5 text-center',
              'transition-all duration-150',
              targetDropzone.isDragActive
                ? 'border-primary bg-primary/5 scale-[1.01]'
                : targetForm
                  ? 'border-border bg-card hover:bg-muted/40'
                  : 'border-border bg-background hover:border-primary/50 hover:bg-muted/30',
            )}
          >
            <input {...targetDropzone.getInputProps()} />
            {targetForm ? (
              <>
                <div className="w-10 h-10 rounded-xl bg-primary/10 flex items-center justify-center flex-shrink-0">
                  <FileText size={18} className="text-primary" />
                </div>
                <div className="w-full">
                  <p className="text-sm font-medium text-foreground truncate px-2">{targetForm.name}</p>
                  <p className="text-[11px] text-muted-foreground mt-0.5">{formatBytes(targetForm.size)}</p>
                </div>
                <button
                  type="button"
                  onClick={e => { e.stopPropagation(); setTargetForm(null) }}
                  className="absolute top-2.5 right-2.5 w-6 h-6 rounded-md flex items-center justify-center text-muted-foreground hover:text-destructive hover:bg-destructive/10 transition-colors"
                >
                  <X size={13} />
                </button>
              </>
            ) : (
              <>
                <div className={cn(
                  'w-10 h-10 rounded-xl flex items-center justify-center transition-colors',
                  targetDropzone.isDragActive ? 'bg-primary/15' : 'bg-muted',
                )}>
                  <FilePlus2 size={18} className={targetDropzone.isDragActive ? 'text-primary' : 'text-muted-foreground'} />
                </div>
                <div>
                  <p className={cn('text-sm font-medium', targetDropzone.isDragActive ? 'text-primary' : 'text-foreground')}>
                    {targetDropzone.isDragActive ? 'Release to upload' : 'Drop PDF form here'}
                  </p>
                  <p className="text-[11px] text-muted-foreground mt-0.5">or click to browse</p>
                </div>
              </>
            )}
          </div>
        </div>

        {/* Divider arrow */}
        <div className="hidden sm:flex flex-col items-center gap-1 self-center mt-6">
          <div className="w-8 h-8 rounded-full border border-border bg-background flex items-center justify-center">
            <ArrowRightLeft size={13} className="text-muted-foreground" />
          </div>
        </div>

        {/* Right — Source documents */}
        <div className="flex flex-col gap-1.5">
          <div className="flex items-center gap-1.5">
            <span className="text-xs font-medium text-foreground">Source documents</span>
            <Badge variant="outline" className="text-[10px] py-0 px-1.5 font-normal text-muted-foreground">
              {sourceFiles.length > 0 ? `${sourceFiles.length} file${sourceFiles.length > 1 ? 's' : ''}` : 'PDFs, images, text'}
            </Badge>
          </div>
          <div
            {...sourceDropzone.getRootProps()}
            className={cn(
              'relative h-[168px] rounded-xl border-2 border-dashed cursor-pointer select-none',
              'flex flex-col items-center justify-center gap-3 px-5 text-center',
              'transition-all duration-150',
              sourceDropzone.isDragActive
                ? 'border-primary bg-primary/5 scale-[1.01]'
                : sourceFiles.length > 0
                  ? 'border-border bg-card hover:bg-muted/40'
                  : 'border-border bg-background hover:border-primary/50 hover:bg-muted/30',
            )}
          >
            <input {...sourceDropzone.getInputProps()} />
            {sourceFiles.length > 0 ? (
              <>
                <div className="w-10 h-10 rounded-xl bg-primary/10 flex items-center justify-center flex-shrink-0">
                  <Upload size={18} className="text-primary" />
                </div>
                <div className="w-full overflow-hidden">
                  <p className="text-sm font-medium text-foreground">{sourceFiles.length} file{sourceFiles.length > 1 ? 's' : ''} ready</p>
                  <p className="text-[11px] text-muted-foreground mt-0.5">Click or drop to add more</p>
                </div>
                <div className="absolute bottom-0 left-0 right-0 h-[52px] overflow-y-auto px-3 pb-2 space-y-1">
                  {sourceFiles.map((f, i) => (
                    <div key={`${f.name}-${f.size}-${i}`} className="flex items-center gap-1.5 text-[11px] px-2 py-0.5 bg-muted rounded-md group">
                      <span className="truncate text-muted-foreground flex-1">{f.name}</span>
                      <button
                        type="button"
                        onClick={e => { e.stopPropagation(); setSourceFiles(prev => prev.filter((_, idx) => idx !== i)) }}
                        className="opacity-0 group-hover:opacity-100 text-muted-foreground hover:text-destructive transition-all flex-shrink-0"
                      >
                        <X size={11} />
                      </button>
                    </div>
                  ))}
                </div>
              </>
            ) : (
              <>
                <div className={cn(
                  'w-10 h-10 rounded-xl flex items-center justify-center transition-colors',
                  sourceDropzone.isDragActive ? 'bg-primary/15' : 'bg-muted',
                )}>
                  <Upload size={18} className={sourceDropzone.isDragActive ? 'text-primary' : 'text-muted-foreground'} />
                </div>
                <div>
                  <p className={cn('text-sm font-medium', sourceDropzone.isDragActive ? 'text-primary' : 'text-foreground')}>
                    {sourceDropzone.isDragActive ? 'Release to upload' : 'Drop source files here'}
                  </p>
                  <p className="text-[11px] text-muted-foreground mt-0.5">PDFs, images, TXT, Markdown</p>
                </div>
              </>
            )}
          </div>
        </div>
      </div>

      {/* ── Validation ──────────────────────────────────────────── */}
      {validationMsg && (
        <p className="text-xs text-destructive flex items-center gap-1.5">
          <AlertCircle size={12} /> {validationMsg}
        </p>
      )}

      {/* ── Submit ──────────────────────────────────────────────── */}
      <div className="flex gap-2">
        <Button
          type="submit"
          disabled={isFormDisabled}
          size="lg"
          className={cn(
            'flex-1 gap-2 font-medium transition-all',
            isReady && !hasProcessing && 'shadow-md shadow-primary/20',
          )}
        >
          {hasProcessing ? (
            <><Loader2 size={15} className="animate-spin" /> Processing…</>
          ) : isReady ? (
            <><Sparkles size={15} /> Fill form with {sourceFiles.length} source file{sourceFiles.length > 1 ? 's' : ''}</>
          ) : (
            'Upload files to continue'
          )}
        </Button>
        {hasProcessing && (
          <Button type="button" size="lg" variant="outline" onClick={() => { setTargetForm(null); setSourceFiles([]) }}>
            New form
          </Button>
        )}
      </div>

      {/* ── Security ────────────────────────────────────────────── */}
      <div className="flex flex-wrap items-center justify-center gap-x-5 gap-y-1 text-[11px] text-muted-foreground">
        <span className="flex items-center gap-1.5"><Lock size={10} className="text-emerald-500" /> Encrypted in transit</span>
        <span className="flex items-center gap-1.5"><Trash2 size={10} className="text-emerald-500" /> Deleted after processing</span>
        <span className="flex items-center gap-1.5"><Eye size={10} className="text-emerald-500" /> No human review</span>
      </div>

      {/* ── Jobs queue ──────────────────────────────────────────── */}
      {jobs.length > 0 && (
        <div className="space-y-3">
          <Separator />
          <div className="flex items-center justify-between">
            <p className="text-xs font-semibold text-muted-foreground uppercase tracking-wide">Queue</p>
            <p className="text-[11px] text-muted-foreground">{jobs.length} job{jobs.length > 1 ? 's' : ''}</p>
          </div>
          <div className="space-y-2">
            {jobs.map(job => (
              <div
                key={job.id}
                className={cn(
                  'flex items-center gap-3 rounded-xl border p-3.5 transition-colors',
                  job.status === 'processing' && 'bg-card border-border',
                  job.status === 'complete' && 'bg-emerald-50/60 border-emerald-200 dark:bg-emerald-950/20 dark:border-emerald-800',
                  job.status === 'error' && 'bg-red-50/60 border-red-200 dark:bg-red-950/20 dark:border-red-800',
                )}
              >
                <div className={cn(
                  'w-8 h-8 rounded-lg flex items-center justify-center flex-shrink-0',
                  job.status === 'processing' && 'bg-primary/10',
                  job.status === 'complete' && 'bg-emerald-100 dark:bg-emerald-900/40',
                  job.status === 'error' && 'bg-red-100 dark:bg-red-900/40',
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
