import { useState, useEffect, useCallback } from 'react'
import { trackEvent } from '@/lib/analytics'
import {
  Workflow, Plus, Play, Pause, Trash2, ExternalLink,
  CheckCircle2, XCircle, Loader2, RefreshCw, MoreVertical,
  FolderOpen, Pencil,
  ArrowRight, FolderInput, Settings2, Zap,
} from 'lucide-react'
import { useSearchParams } from 'react-router-dom'
import { Button } from '@/components/ui/button'
import { cn } from '@/lib/utils'
import api from '@/lib/api'
import toast from 'react-hot-toast'
import PipelineCreateWizard, { type PipelineData } from '@/components/PipelineCreateWizard'

// ── Types ──────────────────────────────────────────────────────────────────

interface LogLine {
  ts: string
  msg: string
}

interface PipelineRun {
  id: string
  status: 'running' | 'completed' | 'failed'
  source_file_name: string | null
  dest_file_url: string | null
  records_extracted: number
  cost_usd: number
  error_message: string | null
  log_lines: LogLine[]
  started_at: string | null
  completed_at: string | null
}

// ── Helpers ────────────────────────────────────────────────────────────────

function relativeTime(iso: string | null): string {
  if (!iso) return 'never'
  const diff = Date.now() - new Date(iso).getTime()
  const mins = Math.floor(diff / 60000)
  if (mins < 1) return 'just now'
  if (mins < 60) return `${mins}m ago`
  const hrs = Math.floor(mins / 60)
  if (hrs < 24) return `${hrs}h ago`
  return `${Math.floor(hrs / 24)}d ago`
}

function runDuration(run: PipelineRun): string {
  if (!run.started_at || !run.completed_at) return ''
  const ms = new Date(run.completed_at).getTime() - new Date(run.started_at).getTime()
  if (ms < 1000) return '<1s'
  return `${Math.round(ms / 1000)}s`
}

function providerLabel(type: string): string {
  if (type === 'google_drive') return 'Google Drive'
  if (type === 'dropbox') return 'Dropbox'
  if (type === 'box') return 'Box'
  if (type === 'outlook') return 'Outlook'
  return 'SharePoint'
}

function providerBadge(type: string): string {
  if (type === 'google_drive') return 'G'
  if (type === 'dropbox') return 'DB'
  if (type === 'box') return 'BX'
  return 'MS'
}

// ── Run Row ────────────────────────────────────────────────────────────────

function RunRow({ run }: { run: PipelineRun }) {
  const dur = runDuration(run)

  return (
    <div className="w-full flex items-center gap-2 py-1 text-xs -mx-1 px-1 rounded">
      {run.status === 'completed' ? (
        <CheckCircle2 size={12} className="text-green-500 flex-shrink-0" />
      ) : run.status === 'failed' ? (
        <XCircle size={12} className="text-red-400 flex-shrink-0" />
      ) : (
        <Loader2 size={12} className="text-blue-400 animate-spin flex-shrink-0" />
      )}
      <span className="truncate flex-1 text-muted-foreground text-left" style={{ maxWidth: 130 }}>
        {run.source_file_name || '—'}
      </span>
      {dur && <span className="text-muted-foreground">{dur}</span>}
      {run.status === 'completed' && run.cost_usd > 0 && (
        <span className="text-muted-foreground">${run.cost_usd.toFixed(3)}</span>
      )}
      {run.status === 'completed' && run.dest_file_url && (
        <a
          href={run.dest_file_url}
          target="_blank"
          rel="noopener noreferrer"
          className="text-primary hover:underline flex items-center gap-0.5"
          onClick={e => e.stopPropagation()}
        >
          open <ExternalLink size={10} />
        </a>
      )}
      {run.status === 'failed' && <span className="text-red-400">failed</span>}
    </div>
  )
}

// ── Pipeline Card ──────────────────────────────────────────────────────────

interface PipelineCardProps {
  pipeline: PipelineData
  onEdit: (p: PipelineData) => void
  onToggle: (id: string, status: string) => void
  onRunNow: (id: string) => void
  onDelete: (id: string) => void
}

function PipelineCard({ pipeline, onEdit, onToggle, onRunNow, onDelete }: PipelineCardProps) {
  const [menuOpen, setMenuOpen] = useState(false)

  const statusColor = {
    active: 'bg-green-500',
    paused: 'bg-amber-400',
    error: 'bg-red-400',
  }[pipeline.status] ?? 'bg-gray-400'

  const outputName = `${pipeline.name}.${pipeline.dest_format}`

  return (
    <div className="bg-white border border-border rounded-xl p-4 flex flex-col gap-3 shadow-sm">
      {/* Header */}
      <div className="flex items-start justify-between gap-2">
        <div className="flex items-center gap-2 min-w-0">
          <div className="w-7 h-7 rounded-lg bg-primary/10 flex items-center justify-center flex-shrink-0">
            <span className="text-primary text-[10px] font-bold">
              {providerBadge(pipeline.source_type)}
            </span>
          </div>
          <span className="font-semibold text-sm truncate">{pipeline.name}</span>
        </div>
        <div className="flex items-center gap-1.5 flex-shrink-0">
          <div className="flex items-center gap-1">
            <div className={cn('w-1.5 h-1.5 rounded-full', statusColor)} />
            <span className="text-xs text-muted-foreground capitalize">{pipeline.status}</span>
          </div>
          {/* Menu */}
          <div className="relative">
            <button
              onClick={() => setMenuOpen(o => !o)}
              className="w-6 h-6 flex items-center justify-center rounded text-muted-foreground hover:bg-accent"
            >
              <MoreVertical size={14} />
            </button>
            {menuOpen && (
              <>
                <div className="fixed inset-0 z-10" onClick={() => setMenuOpen(false)} />
                <div className="absolute right-0 top-7 z-20 bg-white border border-border rounded-lg shadow-lg py-1 w-36">
                  <button
                    onClick={() => { onEdit(pipeline); setMenuOpen(false) }}
                    className="w-full text-left px-3 py-1.5 text-xs text-foreground hover:bg-accent flex items-center gap-2"
                  >
                    <Pencil size={12} /> Edit pipeline
                  </button>
                  <button
                    onClick={() => { onDelete(pipeline.id); setMenuOpen(false) }}
                    className="w-full text-left px-3 py-1.5 text-xs text-red-500 hover:bg-red-50 flex items-center gap-2"
                  >
                    <Trash2 size={12} /> Delete
                  </button>
                </div>
              </>
            )}
          </div>
        </div>
      </div>

      {/* Folder flow */}
      <div className="flex items-center gap-1.5 text-xs text-muted-foreground flex-wrap">
        <span className="text-[10px] uppercase tracking-wider font-medium">Source</span>
        <FolderOpen size={12} className="text-primary/50 flex-shrink-0" />
        <span className="truncate max-w-[100px]">{pipeline.source_folder_name}</span>
        <ArrowRight size={11} className="flex-shrink-0 text-primary/40" />
        <span className="text-[10px] uppercase tracking-wider font-medium">Output</span>
        <FolderOpen size={12} className="text-primary/50 flex-shrink-0" />
        <span className="truncate max-w-[100px]">{pipeline.dest_folder_name}</span>
        <span className="font-mono text-[10px] bg-secondary px-1.5 py-0.5 rounded">.{pipeline.dest_format}</span>
      </div>
      <p className="text-xs text-muted-foreground -mt-2">
        {providerLabel(pipeline.source_type)} · Spreadsheet saved as <span className="font-medium text-foreground">{outputName}</span>
      </p>

      {/* Stats */}
      <div className="flex items-center gap-3 text-xs text-muted-foreground">
        <span>{pipeline.files_processed} file{pipeline.files_processed !== 1 ? 's' : ''} processed</span>
        {pipeline.last_run_at && (
          <>
            <span>·</span>
            <span>Last run {relativeTime(pipeline.last_run_at)}</span>
          </>
        )}
      </div>

      {/* Recent runs */}
      {pipeline.recent_runs.length > 0 && (
        <div className="pt-1">
            <p className="text-xs font-medium text-muted-foreground mb-1">Recent:</p>
            {pipeline.recent_runs.map(run => <RunRow key={run.id} run={run} />)}
          </div>
      )}

      {/* Actions */}
      <div className="flex items-center gap-2 pt-1">
        <Button
          size="sm"
          variant="outline"
          className="h-7 text-xs gap-1.5"
          onClick={() => onToggle(pipeline.id, pipeline.status)}
        >
          {pipeline.status === 'active' ? <><Pause size={12} /> Pause</> : <><Play size={12} /> Resume</>}
        </Button>
        <Button
          size="sm"
          variant="outline"
          className="h-7 text-xs gap-1.5"
          onClick={() => onRunNow(pipeline.id)}
        >
          <RefreshCw size={12} /> Run Now
        </Button>
        <Button
          size="sm"
          variant="ghost"
          className="h-7 text-xs gap-1 ml-auto text-muted-foreground"
          onClick={() => onEdit(pipeline)}
        >
          <Pencil size={11} /> Edit
        </Button>
      </div>
    </div>
  )
}

// ── Main Page ──────────────────────────────────────────────────────────────

export default function PipelinesPage() {
  const [pipelines, setPipelines] = useState<PipelineData[]>([])
  const [loading, setLoading] = useState(true)
  const [wizardOpen, setWizardOpen] = useState(false)
  const [editingPipeline, setEditingPipeline] = useState<PipelineData | undefined>(undefined)
  const [searchParams, setSearchParams] = useSearchParams()

  const fetchPipelines = useCallback(async () => {
    try {
      const r = await api.get('/pipelines/')
      setPipelines(r.data.pipelines)
    } catch {
      toast.error('Failed to load pipelines')
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    fetchPipelines()
  }, [fetchPipelines])

  // Auto-refresh pipelines list while any run is active
  useEffect(() => {
    const hasRunning = pipelines.some(p =>
      p.recent_runs?.some(r => r.status === 'running')
    )
    if (!hasRunning) return
    const interval = setInterval(fetchPipelines, 5000)
    return () => clearInterval(interval)
  }, [pipelines, fetchPipelines])

  // Handle OAuth redirect back
  useEffect(() => {
    const connected = searchParams.get('connected')
    const error = searchParams.get('error')
    if (connected) {
      const providerName = connected === 'google'
        ? 'Google Drive'
        : connected === 'microsoft'
          ? 'SharePoint'
          : connected === 'dropbox'
            ? 'Dropbox'
            : 'Box'
      toast.success(`${providerName} connected!`)
      setSearchParams({})
      setEditingPipeline(undefined)
      setWizardOpen(true)
    }
    if (error) {
      toast.error(`OAuth failed: ${error}`)
      setSearchParams({})
    }
  }, [searchParams, setSearchParams])

  const openEdit = (p: PipelineData) => {
    setEditingPipeline(p)
    setWizardOpen(true)
  }

  const openCreate = () => {
    setEditingPipeline(undefined)
    setWizardOpen(true)
  }

  const handleWizardClose = () => {
    setWizardOpen(false)
    setEditingPipeline(undefined)
  }

  const handleSaved = (pipeline: PipelineData) => {
    setPipelines(prev => {
      const existing = prev.find(p => p.id === pipeline.id)
      if (existing) {
        return prev.map(p => p.id === pipeline.id ? { ...p, ...pipeline } : p)
      }
      return [pipeline, ...prev]
    })
    setWizardOpen(false)
    setEditingPipeline(undefined)
    trackEvent(editingPipeline ? 'pipeline_updated' : 'pipeline_created', { name: pipeline.name })
    toast.success(editingPipeline ? 'Pipeline updated' : `Pipeline "${pipeline.name}" created!`)
  }

  const handleToggle = async (id: string, currentStatus: string) => {
    const newStatus = currentStatus === 'active' ? 'paused' : 'active'
    try {
      const r = await api.patch(`/pipelines/${id}`, { status: newStatus })
      setPipelines(prev => prev.map(p => p.id === id ? { ...p, ...r.data } : p))
      trackEvent('pipeline_toggle', { status: newStatus })
      toast.success(newStatus === 'active' ? 'Pipeline resumed' : 'Pipeline paused')
    } catch {
      toast.error('Failed to update pipeline')
    }
  }

  const handleRunNow = async (id: string) => {
    try {
      await api.post(`/pipelines/${id}/run`)
      trackEvent('pipeline_run_now')
      toast.success('Pipeline check triggered — new PDFs will be processed shortly')
      setTimeout(fetchPipelines, 1500)
    } catch {
      toast.error('Failed to trigger run')
    }
  }

  const handleDelete = async (id: string) => {
    try {
      await api.delete(`/pipelines/${id}`)
      setPipelines(prev => prev.filter(p => p.id !== id))
      toast.success('Pipeline deleted')
    } catch (err: any) {
      toast.error(err?.response?.data?.detail || 'Failed to delete pipeline')
    }
  }

  return (
    <div className="relative p-4 sm:p-8 max-w-4xl mx-auto">
      <div className="pointer-events-none absolute inset-x-0 top-0 h-48 bg-gradient-to-b from-primary/[0.03] to-transparent rounded-t-xl" />

      {/* Header */}
      <div className="relative border-b border-border pb-5 mb-6 flex flex-col sm:flex-row sm:items-start justify-between gap-2">
        <div>
          <h1 className="text-xl font-semibold text-foreground">Pipelines</h1>
          <p className="text-muted-foreground text-sm mt-1 max-w-2xl leading-relaxed">
            Automate repetitive document processing. Connect a folder in Outlook, Box, Dropbox, or Google Drive, define the fields to extract, and new files are processed automatically into a spreadsheet.
          </p>
        </div>
        {pipelines.length > 0 && (
          <Button size="sm" className="gap-1.5 flex-shrink-0" onClick={openCreate}>
            <Plus size={15} /> New Pipeline
          </Button>
        )}
      </div>

      {/* Body */}
      <div>
        {loading ? (
          <div className="flex items-center justify-center py-20">
            <Loader2 size={20} className="animate-spin text-muted-foreground" />
          </div>
        ) : pipelines.length === 0 ? (
          <div className="flex flex-col items-center justify-center py-10">
            <div className="max-w-md w-full">
            <div className="flex flex-col items-center text-center mb-5">
              <div className="w-10 h-10 rounded-xl bg-primary/10 flex items-center justify-center mb-3">
                <Workflow size={20} className="text-primary" />
              </div>
              <h2 className="font-semibold text-lg mb-1">Automate your document processing</h2>
              <p className="text-sm text-muted-foreground max-w-sm">
                Pipelines watch a folder in Google Drive, SharePoint, Dropbox, or Box. When new PDFs or images appear, they're automatically extracted into a spreadsheet.
              </p>
            </div>

            {/* How pipelines work — steps */}
            <div className="space-y-3.5 mb-6">
              <p className="text-xs font-semibold text-muted-foreground uppercase tracking-wider">How it works</p>
              <div className="flex items-start gap-3">
                <div className="w-7 h-7 rounded-lg bg-primary/10 flex items-center justify-center flex-shrink-0 mt-0.5">
                  <FolderInput size={13} className="text-primary" />
                </div>
                <div>
                  <p className="text-sm font-medium text-foreground">1. Connect a source folder</p>
                  <p className="text-xs text-muted-foreground mt-0.5">Google Drive, SharePoint, Dropbox, Box, or Outlook — wherever your PDFs or images arrive.</p>
                </div>
              </div>
              <div className="flex items-start gap-3">
                <div className="w-7 h-7 rounded-lg bg-primary/10 flex items-center justify-center flex-shrink-0 mt-0.5">
                  <Settings2 size={13} className="text-primary" />
                </div>
                <div>
                  <p className="text-sm font-medium text-foreground">2. Define the fields to extract</p>
                  <p className="text-xs text-muted-foreground mt-0.5">e.g. Invoice #, Date, Total, Vendor — or any custom field.</p>
                </div>
              </div>
              <div className="flex items-start gap-3">
                <div className="w-7 h-7 rounded-lg bg-primary/10 flex items-center justify-center flex-shrink-0 mt-0.5">
                  <Zap size={13} className="text-primary" />
                </div>
                <div>
                  <p className="text-sm font-medium text-foreground">3. It runs automatically</p>
                  <p className="text-xs text-muted-foreground mt-0.5">New files get processed and the spreadsheet is saved to your destination folder.</p>
                </div>
              </div>
            </div>

            <Button className="gap-1.5 w-full" onClick={openCreate}>
              <Plus size={14} /> Create your first pipeline
            </Button>
          </div>
          </div>
        ) : (
          <div>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              {pipelines.map(p => (
                <PipelineCard
                  key={p.id}
                  pipeline={p}
                  onEdit={openEdit}
                  onToggle={handleToggle}
                  onRunNow={handleRunNow}
                  onDelete={handleDelete}
                />
              ))}
            </div>
          </div>
        )}
      </div>

      {/* Wizard (create + edit) */}
      <PipelineCreateWizard
        open={wizardOpen}
        onClose={handleWizardClose}
        onCreated={handleSaved}
        pipeline={editingPipeline}
      />
    </div>
  )
}
