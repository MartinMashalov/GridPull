import { useState, useCallback, useRef } from 'react'
import { useDropzone } from 'react-dropzone'
import { Upload, Loader2, CheckCircle2, AlertCircle, X, FileText, Download, ClipboardList, ArrowRight, Lock, Trash2, Eye, File, CreditCard } from 'lucide-react'
import { useAuthStore } from '@/store/authStore'
import { useNavigate } from 'react-router-dom'
import api from '@/lib/api'
import { Button } from '@/components/ui/button'
import { cn } from '@/lib/utils'

type FormFillingStatus = 'idle' | 'uploading' | 'processing' | 'complete' | 'error'

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

function getFileIcon(name: string) {
  const ext = name.split('.').pop()?.toLowerCase() || ''
  if (ext === 'pdf') return <FileText size={14} className="text-red-400" />
  if (['png', 'jpg', 'jpeg', 'webp', 'gif'].includes(ext)) return <File size={14} className="text-blue-400" />
  return <FileText size={14} className="text-muted-foreground" />
}

export default function FormFillingPage() {
  const { user } = useAuthStore()
  const navigate = useNavigate()
  const [targetForm, setTargetForm] = useState<File | null>(null)
  const [sourceFiles, setSourceFiles] = useState<File[]>([])
  const [status, setStatus] = useState<FormFillingStatus>('idle')
  const [errorMsg, setErrorMsg] = useState<string | null>(null)
  const [validationMsg, setValidationMsg] = useState<string | null>(null)
  const [resultBlob, setResultBlob] = useState<Blob | null>(null)
  const [resultName, setResultName] = useState<string>('filled_form.pdf')
  const abortRef = useRef<AbortController | null>(null)

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
    setErrorMsg(null)
    setStatus('uploading')
    setResultBlob(null)

    abortRef.current?.abort()
    const ac = new AbortController()
    abortRef.current = ac

    try {
      const fd = new FormData()
      fd.append('target_form', targetForm)
      sourceFiles.forEach(f => fd.append('source_files', f))

      setStatus('processing')
      const res = await api.post('/form-filling/fill', fd, {
        responseType: 'blob',
        signal: ac.signal,
        timeout: 300000,
      })
      abortRef.current = null

      const disposition = res.headers['content-disposition'] || ''
      const filenameMatch = disposition.match(/filename="?([^";\n]+)"?/)
      const name = filenameMatch?.[1] || `filled_${targetForm.name}`

      setResultBlob(res.data)
      setResultName(name)
      setStatus('complete')
    } catch (err: unknown) {
      abortRef.current = null
      const ae = err as { code?: string; name?: string }
      if (ae?.code === 'ERR_CANCELED' || ae?.name === 'CanceledError') {
        setStatus('idle')
        return
      }
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
      setErrorMsg(msg)
      setStatus('error')
    }
  }

  const handleDownload = () => {
    if (!resultBlob) return
    const url = URL.createObjectURL(resultBlob)
    const a = document.createElement('a')
    a.href = url
    a.download = resultName
    document.body.appendChild(a)
    a.click()
    document.body.removeChild(a)
    URL.revokeObjectURL(url)
  }

  const handleReset = () => {
    abortRef.current?.abort()
    abortRef.current = null
    setTargetForm(null)
    setSourceFiles([])
    setStatus('idle')
    setErrorMsg(null)
    setValidationMsg(null)
    setResultBlob(null)
  }

  const isProcessing = status === 'uploading' || status === 'processing'

  return (
    <div className="relative p-4 sm:p-8 max-w-4xl mx-auto">
      <div className="pointer-events-none absolute inset-x-0 top-0 h-48 bg-gradient-to-b from-primary/[0.03] to-transparent rounded-t-xl" />

      {/* Header */}
      <div className="relative border-b border-border pb-5 mb-6">
        <h1 className="text-xl font-semibold text-foreground">Fill PDF Forms</h1>
        <p className="text-muted-foreground text-sm mt-0.5">
          Upload a PDF form and source documents — each form fill uses 1 credit, with a 5 MB max per file
        </p>
      </div>

      {/* How it works */}
      {status === 'idle' && !targetForm && sourceFiles.length === 0 && (
        <div className="mb-6 hidden sm:block">
          <p className="text-xs font-semibold text-muted-foreground uppercase tracking-wider mb-3">How it works</p>
          <div className="grid grid-cols-3 gap-4">
            <div className="flex flex-col items-center text-center gap-2">
              <div className="w-8 h-8 rounded-lg bg-primary/10 flex items-center justify-center">
                <ClipboardList size={14} className="text-primary" />
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
      {status === 'idle' && (
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
                  <p className="text-sm font-medium text-foreground truncate max-w-[200px]">{targetForm.name}</p>
                  <p className="text-[11px] text-muted-foreground mt-0.5">{(targetForm.size / 1024).toFixed(0)} KB</p>
                </div>
                <button
                  onClick={(e) => { e.stopPropagation(); setTargetForm(null) }}
                  className="text-xs text-muted-foreground hover:text-red-400 transition-colors mt-1"
                >
                  Remove
                </button>
              </div>
            ) : (
              <div className="flex flex-col items-center gap-2">
                <div className={cn(
                  'w-10 h-10 rounded-xl flex items-center justify-center transition-colors',
                  targetDropzone.isDragActive ? 'bg-primary/20 text-primary' : 'bg-primary/10 text-primary'
                )}>
                  <ClipboardList size={18} />
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
                  <p className="text-sm font-medium text-foreground">{sourceFiles.length} file{sourceFiles.length > 1 ? 's' : ''} selected</p>
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

      {/* Source file list */}
      {sourceFiles.length > 0 && (
        <div className="bg-card border border-border rounded-xl px-4 py-3 mb-4">
          <div className="flex items-center justify-between mb-2">
            <span className="text-xs font-medium text-muted-foreground">{sourceFiles.length} source file{sourceFiles.length > 1 ? 's' : ''}</span>
            <button onClick={() => setSourceFiles([])} className="text-xs text-muted-foreground hover:text-red-400 transition-colors">Clear all</button>
          </div>
          <div className="space-y-1 max-h-32 overflow-y-auto scrollbar-thin">
            {sourceFiles.map((f, i) => (
              <div key={`${f.name}-${f.size}-${i}`} className="flex items-center justify-between py-1 group">
                <div className="flex items-center gap-2 min-w-0">
                  {getFileIcon(f.name)}
                  <span className="text-xs text-foreground truncate">{f.name}</span>
                  <span className="text-[10px] text-muted-foreground flex-shrink-0">{(f.size / 1024).toFixed(0)} KB</span>
                </div>
                <button
                  onClick={() => setSourceFiles(prev => prev.filter((_, idx) => idx !== i))}
                  className="opacity-0 group-hover:opacity-100 text-muted-foreground hover:text-red-400 transition-all"
                >
                  <X size={12} />
                </button>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Validation */}
      {validationMsg && (
        <p className="mb-3 text-xs text-red-500">{validationMsg}</p>
      )}

      {/* Mobile security */}
      {status === 'idle' && (
        <p className="mb-3 text-center text-[11px] text-muted-foreground sm:hidden">
          <Lock size={10} className="inline text-emerald-500 mr-1" />
          Encrypted · files deleted after processing · no human access
        </p>
      )}

      {/* CTA */}
      <Button
        onClick={status === 'complete' ? handleReset : handleFill}
        disabled={status === 'complete' ? false : (!targetForm || sourceFiles.length === 0 || isProcessing || !!(user && !user.has_card))}
        size="lg"
        className="w-full shadow-lg shadow-primary/25"
        variant={status === 'complete' ? 'outline' : 'default'}
      >
        {isProcessing ? (
          <>
            <Loader2 size={15} className="animate-spin" />
            {status === 'uploading' ? 'Uploading…' : 'Filling form…'}
          </>
        ) : status === 'complete' ? (
          'Start new form fill'
        ) : targetForm && sourceFiles.length > 0 ? (
          `Fill form using ${sourceFiles.length} source file${sourceFiles.length > 1 ? 's' : ''}`
        ) : (
          'Upload files to get started'
        )}
      </Button>

      {/* Processing indicator */}
      {isProcessing && (
        <div className="mt-4 bg-card border border-border rounded-xl overflow-hidden animate-fade-in">
          <div className="px-5 py-4">
            <div className="flex items-center gap-2 mb-3">
              <Loader2 size={15} className="animate-spin text-primary" />
              <span className="text-sm font-semibold text-foreground">Processing…</span>
            </div>
            <div className="w-full h-1.5 bg-secondary rounded-full overflow-hidden">
              <div className="h-full bg-primary rounded-full animate-pulse" style={{ width: '60%' }} />
            </div>
            <p className="mt-3 text-xs text-muted-foreground">
              Extracting text from source documents and filling form fields with AI. This may take a minute.
            </p>
          </div>
        </div>
      )}

      {/* Success */}
      {status === 'complete' && resultBlob && (
        <div className="mt-4 bg-card border border-emerald-200 rounded-xl overflow-hidden animate-fade-in">
          <div className="px-5 py-4">
            <div className="flex items-center justify-between mb-3">
              <span className="text-sm font-semibold flex items-center gap-2">
                <CheckCircle2 size={15} className="text-emerald-500" />
                Form filled successfully!
              </span>
              <span className="text-xs text-muted-foreground">{(resultBlob.size / 1024).toFixed(0)} KB</span>
            </div>
            <p className="text-xs text-muted-foreground mb-4">Your PDF form has been populated with data from the source documents.</p>
            <Button onClick={handleDownload} className="w-full">
              <Download size={14} className="mr-1.5" />
              Download {resultName}
            </Button>
          </div>
        </div>
      )}

      {/* Error */}
      {status === 'error' && errorMsg && (
        <div className="mt-4 bg-card border border-red-200 rounded-xl overflow-hidden animate-fade-in">
          <div className="px-5 py-4">
            <div className="flex items-center gap-2 mb-2">
              <AlertCircle size={15} className="text-red-400" />
              <span className="text-sm font-semibold text-foreground">Form filling failed</span>
            </div>
            <p className="text-xs text-red-400 bg-red-500/10 border border-red-500/20 rounded-lg px-3 py-2">{errorMsg}</p>
            <Button onClick={handleReset} variant="outline" size="sm" className="mt-3">
              Try again
            </Button>
          </div>
        </div>
      )}
    </div>
  )
}
