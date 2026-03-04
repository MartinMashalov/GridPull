import { useState, useEffect, useCallback } from 'react'
import {
  Workflow, Plus, Play, Pause, Trash2, ExternalLink,
  CheckCircle2, XCircle, Loader2, RefreshCw, MoreVertical,
  ChevronRight, FolderOpen, Pencil,
} from 'lucide-react'
import { useSearchParams } from 'react-router-dom'
import { Button } from '@/components/ui/button'
import { Separator } from '@/components/ui/separator'
import { cn } from '@/lib/utils'
import api from '@/lib/api'
import toast from 'react-hot-toast'
import PipelineCreateWizard, { type PipelineData } from '@/components/PipelineCreateWizard'

// ── Types ──────────────────────────────────────────────────────────────────

interface PipelineRun {
  id: string
  status: 'running' | 'completed' | 'failed'
  source_file_name: string | null
  dest_file_url: string | null
  records_extracted: number
  cost_usd: number
  error_message: string | null
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
  return type === 'google_drive' ? 'Google Drive' : 'SharePoint'
}

// ── Run Row ────────────────────────────────────────────────────────────────

function RunRow({ run }: { run: PipelineRun }) {
  const dur = runDuration(run)
  return (
    <div className="flex items-center gap-2 py-1 text-xs">
      {run.status === 'completed' ? (
        <CheckCircle2 size={12} className="text-green-500 flex-shrink-0" />
      ) : run.status === 'failed' ? (
        <XCircle size={12} className="text-red-400 flex-shrink-0" />
      ) : (
        <Loader2 size={12} className="text-blue-400 animate-spin flex-shrink-0" />
      )}
      <span className="truncate flex-1 text-muted-foreground" style={{ maxWidth: 130 }}>
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
              {pipeline.source_type === 'google_drive' ? 'G' : 'MS'}
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
        <FolderOpen size={12} className="text-primary/50 flex-shrink-0" />
        <span className="truncate max-w-[100px]">{pipeline.source_folder_name}</span>
        <ChevronRight size={11} className="flex-shrink-0" />
        <FolderOpen size={12} className="text-primary/50 flex-shrink-0" />
        <span className="truncate max-w-[100px]">{pipeline.dest_folder_name}</span>
        <span className="text-border">·</span>
        <span className="font-mono text-[10px] bg-secondary px-1.5 py-0.5 rounded">.{pipeline.dest_format}</span>
      </div>
      <p className="text-xs text-muted-foreground -mt-2">
        {providerLabel(pipeline.source_type)} · output: <span className="font-medium text-foreground">{outputName}</span>
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
        <>
          <Separator />
          <div>
            <p className="text-xs font-medium text-muted-foreground mb-1">Recent:</p>
            {pipeline.recent_runs.map(run => <RunRow key={run.id} run={run} />)}
          </div>
        </>
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

  // Handle OAuth redirect back
  useEffect(() => {
    const connected = searchParams.get('connected')
    const error = searchParams.get('error')
    if (connected) {
      toast.success(`${connected === 'google' ? 'Google Drive' : 'SharePoint'} connected!`)
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
    toast.success(editingPipeline ? 'Pipeline updated' : `Pipeline "${pipeline.name}" created!`)
  }

  const handleToggle = async (id: string, currentStatus: string) => {
    const newStatus = currentStatus === 'active' ? 'paused' : 'active'
    try {
      const r = await api.patch(`/pipelines/${id}`, { status: newStatus })
      setPipelines(prev => prev.map(p => p.id === id ? { ...p, ...r.data } : p))
      toast.success(newStatus === 'active' ? 'Pipeline resumed' : 'Pipeline paused')
    } catch {
      toast.error('Failed to update pipeline')
    }
  }

  const handleRunNow = async (id: string) => {
    try {
      await api.post(`/pipelines/${id}/run`)
      toast.success('Pipeline check triggered — new PDFs will be processed shortly')
    } catch {
      toast.error('Failed to trigger run')
    }
  }

  const handleDelete = async (id: string) => {
    if (!window.confirm('Delete this pipeline? This cannot be undone.')) return
    try {
      await api.delete(`/pipelines/${id}`)
      setPipelines(prev => prev.filter(p => p.id !== id))
      toast.success('Pipeline deleted')
    } catch {
      toast.error('Failed to delete pipeline')
    }
  }

  return (
    <div className="flex-1 flex flex-col min-h-0 bg-background">
      {/* Header */}
      <div className="px-6 py-4 border-b border-border bg-white">
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-lg font-semibold">Pipelines</h1>
            <p className="text-sm text-muted-foreground mt-0.5">
              Auto-extract PDFs from Google Drive or SharePoint every 5 minutes — results append to one file
            </p>
          </div>
          <Button size="sm" className="gap-1.5" onClick={openCreate}>
            <Plus size={15} /> New Pipeline
          </Button>
        </div>
      </div>

      {/* Body */}
      <div className="flex-1 overflow-y-auto p-6">
        {loading ? (
          <div className="flex items-center justify-center h-40">
            <Loader2 size={20} className="animate-spin text-muted-foreground" />
          </div>
        ) : pipelines.length === 0 ? (
          <div className="flex flex-col items-center justify-center h-64 text-center">
            <div className="w-12 h-12 rounded-2xl bg-primary/10 flex items-center justify-center mb-3">
              <Workflow size={22} className="text-primary" />
            </div>
            <p className="font-medium text-sm mb-1">No pipelines yet</p>
            <p className="text-xs text-muted-foreground mb-4 max-w-xs">
              Connect Google Drive or SharePoint and let GridPull automatically extract data from new PDFs every 5 minutes.
            </p>
            <Button size="sm" className="gap-1.5" onClick={openCreate}>
              <Plus size={14} /> Create your first pipeline
            </Button>
          </div>
        ) : (
          <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4">
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
