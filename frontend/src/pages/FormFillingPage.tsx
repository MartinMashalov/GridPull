import { useState, useCallback, useEffect, useRef } from 'react'
import { useDropzone } from 'react-dropzone'
import {
  Upload, Loader2, CheckCircle2, AlertCircle, X, FileText,
  Download, Lock, Trash2, Eye,
  Sparkles, FilePlus2, Clipboard,
} from 'lucide-react'
import { useFormJobStore, type FormJob } from '@/store/formJobStore'
import api from '@/lib/api'
import { SAFE_FILE_INPUT_PROPS } from '@/lib/fileInput'
import { Button } from '@/components/ui/button'
import { Separator } from '@/components/ui/separator'
import UsagePill from '@/components/UsagePill'
import { cn } from '@/lib/utils'


const MAX_TARGET_FORMS = 10

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

function base64ToBlob(b64: string, mime = 'application/pdf'): Blob {
  const binary = atob(b64)
  const len = binary.length
  const bytes = new Uint8Array(len)
  for (let i = 0; i < len; i++) bytes[i] = binary.charCodeAt(i)
  return new Blob([bytes], { type: mime })
}

interface FillResult {
  target_filename: string
  success: boolean
  filled_pdf_base64?: string
  filled_filename?: string
  cost_usd?: number
  model?: string
  size_bytes?: number
  error?: string
}

interface FillResponse {
  results: FillResult[]
  summary?: { total: number; succeeded: number; failed: number; total_cost_usd: number }
}

export default function FormFillingPage() {
  const { jobs, addJobs, dismissJob } = useFormJobStore()
  const [targetForms, setTargetForms] = useState<File[]>([])
  const [sourceFiles, setSourceFiles] = useState<File[]>([])
  const [validationMsg, setValidationMsg] = useState<string | null>(null)

  const onDropTarget = useCallback((accepted: File[]) => {
    const valid: File[] = []
    let skipped = 0
    for (const f of accepted) {
      const ext = f.name.split('.').pop()?.toLowerCase()
      if (ext === 'pdf') valid.push(f)
      else skipped++
    }
    setTargetForms(prev => {
      const seen = new Set(prev.map(f => f.name + f.size))
      const merged = [...prev, ...valid.filter(f => !seen.has(f.name + f.size))]
      if (merged.length > MAX_TARGET_FORMS) {
        setValidationMsg(`At most ${MAX_TARGET_FORMS} target forms — extra ones ignored.`)
        return merged.slice(0, MAX_TARGET_FORMS)
      }
      if (skipped > 0) setValidationMsg(`${skipped} non-PDF file${skipped > 1 ? 's' : ''} skipped.`)
      else setValidationMsg(null)
      return merged
    })
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
    multiple: true,
    maxFiles: MAX_TARGET_FORMS,
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
    if (targetForms.length === 0 || sourceFiles.length === 0) {
      setValidationMsg('Upload at least one target form and at least one source file.')
      return
    }
    if (targetForms.length > MAX_TARGET_FORMS) {
      setValidationMsg(`At most ${MAX_TARGET_FORMS} target forms allowed.`)
      return
    }
    setValidationMsg(null)

    // One job pill per target form so users see concurrent progress.
    const jobIds = targetForms.map(() => `form-job-${++_jobCounter}`)
    const newJobs: FormJob[] = targetForms.map((tf, i) => ({
      id: jobIds[i],
      targetName: tf.name,
      sourceCount: sourceFiles.length,
      status: 'processing' as const,
    }))
    addJobs(newJobs)

    const capturedTargets = [...targetForms]
    const capturedSources = [...sourceFiles]
    setTargetForms([])
    setSourceFiles([])

    const fd = new FormData()
    capturedTargets.forEach(f => fd.append('target_forms', f))
    capturedSources.forEach(f => fd.append('source_files', f))

    try {
      const res = await api.post<FillResponse>('/form-filling/fill', fd, { timeout: 600000 })
      const data = res.data
      const results = data?.results || []
      // Map each result back to its job by filename. Keep an index counter
      // for duplicates so we don't double-mark the same job.
      const jobByName = new Map<string, string[]>()
      capturedTargets.forEach((tf, i) => {
        const list = jobByName.get(tf.name) || []
        list.push(jobIds[i])
        jobByName.set(tf.name, list)
      })
      for (const r of results) {
        const queue = jobByName.get(r.target_filename)
        const jid = queue && queue.length > 0 ? queue.shift()! : undefined
        if (!jid) continue
        if (r.success && r.filled_pdf_base64) {
          const blob = base64ToBlob(r.filled_pdf_base64, 'application/pdf')
          const name = r.filled_filename || `filled_${r.target_filename}`
          useFormJobStore.getState().updateJob(jid, {
            status: 'complete', resultBlob: blob, resultName: name,
          })
          // Auto-download each filled PDF.
          triggerDownload(blob, name)
        } else {
          useFormJobStore.getState().updateJob(jid, {
            status: 'error', errorMsg: r.error || 'Form filling failed',
          })
        }
      }
      // Any jobs we didn't get a result for — mark as error.
      for (const list of jobByName.values()) {
        for (const jid of list) {
          useFormJobStore.getState().updateJob(jid, {
            status: 'error', errorMsg: 'No result returned from server',
          })
        }
      }
      window.dispatchEvent(new Event('gridpull:usage-changed'))
    } catch (err: unknown) {
      const e = err as { response?: { data?: { detail?: { message?: string } | string }; status?: number } }
      let msg = 'Form filling failed — please try again'
      const detail = e.response?.data?.detail
      if (typeof detail === 'string') msg = detail
      else if (detail && typeof detail === 'object' && detail.message) msg = detail.message
      else if (e.response?.status) msg = `Form filling failed (HTTP ${e.response.status})`
      // Mark every just-created job as failed.
      for (const jid of jobIds) {
        useFormJobStore.getState().updateJob(jid, { status: 'error', errorMsg: msg })
      }
      window.dispatchEvent(new Event('gridpull:usage-changed'))
    }
  }

  useEffect(() => {
    const timers = jobs
      .filter(j => j.status === 'complete')
      .map(j => setTimeout(() => useFormJobStore.getState().dismissJob(j.id), 4000))
    return () => timers.forEach(clearTimeout)
  }, [jobs.map(j => `${j.id}:${j.status}`).join(',')])

  const hasProcessing = jobs.some(j => j.status === 'processing')
  const isReady = targetForms.length > 0 && targetForms.length <= MAX_TARGET_FORMS && sourceFiles.length > 0
  const isFormDisabled = !isReady || hasProcessing

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
      <div className="relative border-b border-border pb-5 mb-6">
        <div className="flex items-center justify-between gap-2">
          <div className="flex items-center gap-3 mb-2">
            <div className="p-2 rounded-xl bg-primary/10">
              <Clipboard size={20} className="text-primary" />
            </div>
            <h1 className="text-xl font-semibold text-foreground">Fill Applications</h1>
          </div>
          <UsagePill />
        </div>
        <p className="text-muted-foreground text-sm mt-1 max-w-2xl leading-relaxed">
          Fill carrier intake forms and supplemental applications automatically.
          Upload your source documents on the left, then add up to {MAX_TARGET_FORMS} blank PDF forms on the right.
          AI reads your source docs and fills every field on each form. Supports ACORD forms, carrier-specific apps, and any fillable PDF.
        </p>
      </div>

      {/* ── Security strip ───────────────────────────────────────── */}
      <div className="mb-5 hidden sm:flex flex-wrap items-center justify-center gap-x-5 gap-y-1.5 text-[11px] text-muted-foreground">
        <span className="flex items-center gap-1.5"><Lock size={11} className="text-emerald-500" /> Encrypted in transit</span>
        <span className="flex items-center gap-1.5"><Trash2 size={11} className="text-emerald-500" /> Files deleted after processing</span>
        <span className="flex items-center gap-1.5"><Eye size={11} className="text-emerald-500" /> No human access to your documents</span>
      </div>

      {/* ── How it works ────────────────────────────────────────── */}
      {!hasProcessing && targetForms.length === 0 && sourceFiles.length === 0 && (
        <div className="mb-6 hidden sm:block">
          <p className="text-xs font-semibold text-muted-foreground uppercase tracking-wider mb-3">How it works</p>
          <div className="grid grid-cols-3 gap-4">
            <div className="flex flex-col items-center text-center gap-2">
              <div className="w-8 h-8 rounded-lg bg-primary/10 flex items-center justify-center">
                <FileText size={14} className="text-primary" />
              </div>
              <div>
                <p className="text-xs font-medium text-foreground">1. Add your source documents</p>
                <p className="text-[11px] text-muted-foreground mt-0.5">Intake forms, prior policies, loss runs, client documents</p>
              </div>
            </div>
            <div className="flex flex-col items-center text-center gap-2">
              <div className="w-8 h-8 rounded-lg bg-primary/10 flex items-center justify-center">
                <FilePlus2 size={14} className="text-primary" />
              </div>
              <div>
                <p className="text-xs font-medium text-foreground">2. Upload up to {MAX_TARGET_FORMS} blank forms</p>
                <p className="text-[11px] text-muted-foreground mt-0.5">ACORD, carrier apps, or any fillable PDFs — filled in parallel</p>
              </div>
            </div>
            <div className="flex flex-col items-center text-center gap-2">
              <div className="w-8 h-8 rounded-lg bg-primary/10 flex items-center justify-center">
                <Sparkles size={14} className="text-primary" />
              </div>
              <div>
                <p className="text-xs font-medium text-foreground">3. Get every filled form</p>
                <p className="text-[11px] text-muted-foreground mt-0.5">AI fills each form and downloads them automatically</p>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* ── Drop zones ───────────────────────────────────────────── */}
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-4 mb-4">

        {/* Left — Source documents */}
        {/* Both columns wrap the header in a min-h block so the dropzones
            below them stay vertically aligned even when one side carries
            more description text than the other. */}
        <div>
          <div className="min-h-[58px]">
            <p className="text-xs text-muted-foreground mb-1">Source documents</p>
            <p className="text-[11px] text-muted-foreground mb-2 leading-snug">
              Drop the files that contain the data — quote PDFs, prior policies, ACORD forms, intake notes, anything with the values to extract.
            </p>
          </div>
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
            <input {...sourceDropzone.getInputProps(SAFE_FILE_INPUT_PROPS)} />
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

        {/* Right — Target forms (multi) */}
        <div>
          <div className="min-h-[58px]">
            <p className="text-xs text-muted-foreground mb-1">Target forms (1-{MAX_TARGET_FORMS} PDFs)</p>
            <p className="text-[11px] text-muted-foreground mb-2 leading-snug">
              Drop up to {MAX_TARGET_FORMS} fillable PDF forms — they'll be processed in parallel and you'll get all filled PDFs back.
            </p>
          </div>
          <div
            {...targetDropzone.getRootProps()}
            className={cn(
              'border-2 border-dashed rounded-xl p-6 text-center cursor-pointer transition-colors bg-white h-[200px] flex items-center justify-center',
              targetDropzone.isDragActive
                ? 'border-primary bg-primary/5'
                : targetForms.length > 0
                  ? 'border-border bg-card hover:bg-muted/40'
                  : 'border-border hover:border-primary/40 hover:bg-accent/30'
            )}
          >
            <input {...targetDropzone.getInputProps(SAFE_FILE_INPUT_PROPS)} />
            {targetForms.length > 0 ? (
              <div className="flex flex-col items-center gap-2 w-full overflow-hidden">
                <div className="w-12 h-12 rounded-xl bg-primary/10 flex items-center justify-center flex-shrink-0">
                  <FilePlus2 size={22} className="text-primary" />
                </div>
                <div className="flex-shrink-0">
                  <p className="text-sm font-medium text-foreground">
                    {targetForms.length} form{targetForms.length > 1 ? 's' : ''}
                    {targetForms.length >= MAX_TARGET_FORMS && (
                      <span className="text-muted-foreground"> (max)</span>
                    )}
                  </p>
                  <p className="text-[11px] text-muted-foreground mt-0.5">
                    {targetForms.length < MAX_TARGET_FORMS
                      ? 'Click or drop to add more'
                      : `Up to ${MAX_TARGET_FORMS} forms`}
                  </p>
                </div>
                <div className="w-full space-y-1 max-h-[52px] overflow-y-auto text-left">
                  {targetForms.map((f, i) => (
                    <div key={`${f.name}-${f.size}-${i}`} className="flex items-center justify-between text-xs px-2 py-1 bg-muted rounded group">
                      <span className="truncate text-muted-foreground flex-1">{f.name}</span>
                      <span className="text-[10px] text-muted-foreground/70 ml-2 flex-shrink-0">{formatBytes(f.size)}</span>
                      <button
                        type="button"
                        onClick={e => { e.stopPropagation(); setTargetForms(prev => prev.filter((_, idx) => idx !== i)) }}
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
                  targetDropzone.isDragActive ? 'bg-primary/20' : 'bg-primary/10'
                )}>
                  <FilePlus2 size={22} className="text-primary" />
                </div>
                {targetDropzone.isDragActive ? (
                  <p className="text-primary font-medium">Drop your forms here</p>
                ) : (
                  <div>
                    <p className="text-foreground font-medium">Drop 1-{MAX_TARGET_FORMS} PDF forms here</p>
                    <p className="text-muted-foreground text-sm mt-1">or click to browse</p>
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
            <>
              <Sparkles size={15} />
              Fill {targetForms.length} form{targetForms.length > 1 ? 's' : ''} using {sourceFiles.length} source file{sourceFiles.length > 1 ? 's' : ''}
            </>
          )}
        </Button>
      )}

      {/* ── Jobs queue ───────────────────────────────────────────── */}
      {jobs.length > 0 && (
        <div className="mt-6 space-y-3">
          <Separator />
          <div className="flex items-center justify-between pt-1">
            <p className="text-xs font-semibold text-muted-foreground uppercase tracking-wider">Processing Queue</p>
            <p className="text-[11px] text-muted-foreground">
              {(() => {
                const total = jobs.length
                const done = jobs.filter(j => j.status === 'complete').length
                const failed = jobs.filter(j => j.status === 'error').length
                if (failed > 0 && done + failed === total) {
                  return `${done}/${total} forms succeeded — ${failed} failed`
                }
                return `${total} job${total > 1 ? 's' : ''}`
              })()}
            </p>
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
                    {job.status === 'error' && (job.errorMsg || 'Form filling failed')}
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
