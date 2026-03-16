import { useState, useCallback, useEffect, useRef } from 'react'
import * as Dialog from '@radix-ui/react-dialog'
import {
  X, ChevronRight, ChevronLeft, FolderOpen,
  Check, Plus, Trash2, StickyNote, Loader2,
} from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { cn } from '@/lib/utils'
import api from '@/lib/api'
import { useAuthStore } from '@/store/authStore'
import toast from 'react-hot-toast'

// ── Types ──────────────────────────────────────────────────────────────────

type Provider = 'google_drive' | 'sharepoint' | 'dropbox' | 'box' | 'outlook'
type FolderProvider = 'google_drive' | 'sharepoint' | 'dropbox' | 'box'
type Format = 'xlsx' | 'csv'

interface DriveFolder {
  id: string
  name: string
}

interface MailFolder {
  id: string
  displayName: string
  unreadItemCount: number
}

interface Field {
  name: string
  description: string
}

interface OutlookConfig {
  folder_id: string
  folder_name: string
  from_filter: string
  subject_filter: string
  mark_as_read: boolean
}

export interface PipelineData {
  id: string
  name: string
  status: string
  source_type: Provider
  source_folder_id: string
  source_folder_name: string
  source_config?: Record<string, any>
  dest_folder_id: string
  dest_folder_name: string
  dest_format: string
  fields: Field[]
  files_processed: number
  last_run_at: string | null
  last_checked_at: string | null
  created_at: string | null
  recent_runs: any[]
}

// ── Preset fields ──────────────────────────────────────────────────────────

const PRESET_FIELDS = [
  'Date', 'Total Amount', 'Company Name', 'Invoice Number',
  'Revenue', 'Net Income', 'Contract Value', 'Effective Date',
  'Address', 'Signatory', 'Description', 'Tax Amount',
]

// ── Shared: Folder Browser ─────────────────────────────────────────────────

interface FolderBrowserProps {
  provider: FolderProvider
  onSelect: (folder: DriveFolder) => void
  selected: DriveFolder | null
}

function FolderBrowser({ provider, onSelect, selected }: FolderBrowserProps) {
  const [path, setPath] = useState<DriveFolder[]>([
    {
      id: provider === 'box' ? '0' : 'root',
      name:
        provider === 'google_drive' ? 'My Drive'
          : provider === 'sharepoint' ? 'OneDrive'
          : provider === 'dropbox' ? 'Dropbox'
          : 'All Files',
    },
  ])
  const [folders, setFolders] = useState<DriveFolder[]>([])
  const [loading, setLoading] = useState(false)

  const currentFolder = path[path.length - 1]

  useEffect(() => {
    setPath([{
      id: provider === 'box' ? '0' : 'root',
      name:
        provider === 'google_drive' ? 'My Drive'
          : provider === 'sharepoint' ? 'OneDrive'
          : provider === 'dropbox' ? 'Dropbox'
          : 'All Files',
    }])
  }, [provider])

  const loadFolders = useCallback(async (folderId: string) => {
    setLoading(true)
    try {
      if (provider === 'google_drive') {
        const r = await api.get('/pipelines/folders/google', { params: { parent_id: folderId } })
        setFolders(r.data.folders)
      } else if (provider === 'sharepoint') {
        const r = await api.get('/pipelines/folders/microsoft', { params: { folder_id: folderId } })
        setFolders(r.data.folders)
      } else if (provider === 'dropbox') {
        const r = await api.get('/pipelines/folders/dropbox', { params: { folder_id: folderId } })
        setFolders(r.data.folders)
      } else {
        const r = await api.get('/pipelines/folders/box', { params: { folder_id: folderId } })
        setFolders(r.data.folders)
      }
    } catch {
      toast.error('Failed to load folders')
    } finally {
      setLoading(false)
    }
  }, [provider])

  useEffect(() => {
    loadFolders(currentFolder.id)
  }, [currentFolder.id, loadFolders])

  const navigate = (folder: DriveFolder) => setPath(prev => [...prev, folder])
  const breadcrumbNav = (idx: number) => setPath(prev => prev.slice(0, idx + 1))

  return (
    <div className="border border-border rounded-lg overflow-hidden">
      {/* Breadcrumb */}
      <div className="flex items-center gap-1 px-3 py-2 bg-secondary/60 border-b border-border flex-wrap">
        {path.map((seg, idx) => (
          <div key={idx} className="flex items-center gap-1">
            {idx > 0 && <ChevronRight size={11} className="text-muted-foreground" />}
            <button
              onClick={() => breadcrumbNav(idx)}
              className={cn(
                'text-xs rounded px-1 py-0.5 hover:bg-background transition-colors',
                idx === path.length - 1 ? 'font-medium text-foreground' : 'text-muted-foreground'
              )}
            >
              {seg.name}
            </button>
          </div>
        ))}
      </div>

      {/* Folder list */}
      <div className="max-h-40 overflow-y-auto">
        {loading ? (
          <div className="flex items-center justify-center h-14">
            <Loader2 size={14} className="animate-spin text-muted-foreground" />
          </div>
        ) : folders.length === 0 ? (
          <p className="text-xs text-muted-foreground text-center py-5">No sub-folders here</p>
        ) : (
          folders.map(folder => (
            <div
              key={folder.id}
              className={cn(
                'flex items-center gap-2 px-3 py-2 text-sm transition-colors',
                selected?.id === folder.id ? 'bg-primary/10 text-primary' : 'hover:bg-secondary/60'
              )}
            >
              <FolderOpen size={13} className={selected?.id === folder.id ? 'text-primary' : 'text-muted-foreground'} />
              <span className="flex-1 truncate cursor-pointer" onClick={() => onSelect(folder)}>
                {folder.name}
              </span>
              <button onClick={() => navigate(folder)} className="text-muted-foreground hover:text-foreground">
                <ChevronRight size={13} />
              </button>
            </div>
          ))
        )}
      </div>

      {/* Select current folder */}
      <div className="border-t border-border px-3 py-2 bg-secondary/40 flex items-center justify-between">
        <span className="text-xs text-muted-foreground truncate max-w-[220px]">
          {selected?.id === currentFolder.id
            ? <><Check size={11} className="inline mr-1 text-green-500" />Selected: <strong>{currentFolder.name}</strong></>
            : `Current: ${currentFolder.name}`}
        </span>
        <button
          onClick={() => onSelect(currentFolder)}
          className={cn(
            'text-xs px-2.5 py-1 rounded transition-colors flex-shrink-0',
            selected?.id === currentFolder.id
              ? 'bg-primary text-white'
              : 'bg-background border border-border hover:border-primary text-foreground'
          )}
        >
          {selected?.id === currentFolder.id ? 'Selected' : 'Select'}
        </button>
      </div>
    </div>
  )
}

// ── Shared: Fields Editor (matches ExtractionFieldsModal design) ───────────

interface FieldsEditorProps {
  fields: Field[]
  onChange: (fields: Field[]) => void
}

export function FieldsEditor({ fields, onChange }: FieldsEditorProps) {
  const [newName, setNewName] = useState('')
  const [expandedDesc, setExpandedDesc] = useState<number | null>(null)
  const inputRef = useRef<HTMLInputElement>(null)

  const addPreset = (name: string) => {
    if (!fields.find(f => f.name === name)) {
      onChange([...fields, { name, description: '' }])
    }
  }

  const addCustom = () => {
    const t = newName.trim()
    if (!t) return
    if (!fields.find(f => f.name === t)) {
      onChange([...fields, { name: t, description: '' }])
    }
    setNewName('')
    setTimeout(() => inputRef.current?.focus(), 40)
  }

  const remove = (idx: number) => {
    onChange(fields.filter((_, i) => i !== idx))
    if (expandedDesc === idx) setExpandedDesc(null)
  }

  const updateDesc = (idx: number, desc: string) => {
    onChange(fields.map((f, i) => i === idx ? { ...f, description: desc } : f))
  }

  const toggleDesc = (idx: number) => setExpandedDesc(prev => prev === idx ? null : idx)

  return (
    <div className="space-y-3">
      {/* Preset pills */}
      <div className="flex flex-wrap gap-1.5">
        {PRESET_FIELDS.map(name => {
          const added = !!fields.find(f => f.name === name)
          return (
            <button
              key={name}
              onClick={() => addPreset(name)}
              disabled={added}
              className={cn(
                'px-2.5 py-1 rounded-full text-[11px] font-medium border transition-colors',
                added
                  ? 'bg-primary/10 text-primary border-primary/25 cursor-default'
                  : 'bg-secondary text-muted-foreground border-border hover:border-primary/40 hover:text-foreground'
              )}
            >
              {name}
            </button>
          )
        })}
      </div>

      {/* Selected fields */}
      {fields.length > 0 && (
        <div className="space-y-1 max-h-52 overflow-y-auto scrollbar-thin pr-0.5">
          {fields.map((field, i) => (
            <div key={i} className="rounded-lg border border-border overflow-hidden">
              <div className="flex items-center justify-between px-3 py-2 bg-secondary">
                <span className="text-sm text-foreground flex-1 min-w-0 truncate">{field.name}</span>
                <div className="flex items-center gap-1 ml-2 flex-shrink-0">
                  <button
                    onClick={() => toggleDesc(i)}
                    title="Add description to improve accuracy"
                    className={cn(
                      'p-1 rounded transition-colors',
                      expandedDesc === i
                        ? 'text-primary bg-primary/10'
                        : field.description
                          ? 'text-primary/60 hover:text-primary'
                          : 'text-muted-foreground hover:text-primary'
                    )}
                  >
                    <StickyNote size={13} />
                  </button>
                  <button
                    onClick={() => remove(i)}
                    className="p-1 rounded text-muted-foreground hover:text-red-500 transition-colors"
                  >
                    <Trash2 size={13} />
                  </button>
                </div>
              </div>
              {expandedDesc === i && (
                <div className="px-3 py-2 bg-primary/5 border-t border-border">
                  <textarea
                    autoFocus
                    rows={2}
                    value={field.description}
                    onChange={e => updateDesc(i, e.target.value)}
                    placeholder="Describe what to look for, or how to calculate (e.g. 'Net Income ÷ Revenue × 100')…"
                    className="w-full text-xs bg-transparent resize-none outline-none text-foreground placeholder:text-muted-foreground/60 leading-relaxed"
                  />
                </div>
              )}
            </div>
          ))}
        </div>
      )}

      {/* Custom field input */}
      <div className="flex gap-2">
        <Input
          ref={inputRef}
          placeholder="Add custom field…"
          value={newName}
          onChange={e => setNewName(e.target.value)}
          onKeyDown={e => { if (e.key === 'Enter') { e.preventDefault(); e.stopPropagation(); addCustom() } }}
          className="text-sm"
        />
        <Button onClick={addCustom} disabled={!newName.trim()} size="icon" variant="outline">
          <Plus size={14} />
        </Button>
      </div>
    </div>
  )
}

// ── Step 1: Choose provider ────────────────────────────────────────────────

interface Step1Props {
  connections: Record<string, string | null>
  selected: Provider | null
  onSelect: (p: Provider) => void
}

function Step1({ connections, selected, onSelect }: Step1Props) {
  const providers: { id: Provider; label: string; iconText: string; desc: string }[] = [
    { id: 'google_drive', label: 'Google Drive', iconText: 'G', desc: 'Watch a folder for new PDFs' },
    { id: 'sharepoint', label: 'SharePoint / OneDrive', iconText: 'MS', desc: 'Watch a SharePoint folder for new PDFs' },
    { id: 'dropbox', label: 'Dropbox', iconText: 'DB', desc: 'Watch a Dropbox folder for new PDFs' },
    { id: 'box', label: 'Box', iconText: 'BX', desc: 'Watch a Box folder for new PDFs' },
  ]
  return (
    <div className="space-y-3">
      <p className="text-sm text-muted-foreground">Choose the cloud storage to watch for new PDFs or images.</p>
      <div className="grid grid-cols-2 gap-3">
        {providers.map(p => {
          const connected = connections[p.id]
          const isSelected = selected === p.id
          return (
            <button
              key={p.id}
              onClick={() => onSelect(p.id)}
              className={cn(
                'relative flex flex-col items-start gap-2 p-4 rounded-xl border-2 text-left transition-all',
                isSelected ? 'border-primary bg-primary/5' : 'border-border hover:border-primary/40 bg-white'
              )}
            >
              {connected && (
                <div className="absolute top-2.5 right-2.5 w-4 h-4 rounded-full bg-green-500 flex items-center justify-center">
                  <Check size={9} className="text-white" />
                </div>
              )}
              <div className={cn(
                'w-10 h-10 rounded-xl flex items-center justify-center font-bold text-sm',
                isSelected ? 'bg-primary text-white' : 'bg-secondary text-muted-foreground'
              )}>
                {p.iconText}
              </div>
              <div>
                <p className="font-medium text-sm">{p.label}</p>
                <p className="text-xs text-muted-foreground mt-0.5">{p.desc}</p>
                {connected && <p className="text-xs text-green-600 mt-1">Connected: {connected}</p>}
              </div>
            </button>
          )
        })}
      </div>
    </div>
  )
}

// ── Step 2 (Drive): Connect + source folder ────────────────────────────────

interface Step2DriveProps {
  provider: FolderProvider
  connected: boolean
  onConnect: () => void
  sourceFolder: DriveFolder | null
  onSelectSource: (f: DriveFolder) => void
}

function Step2Drive({ provider, connected, onConnect, sourceFolder, onSelectSource }: Step2DriveProps) {
  const providerLabel = provider === 'google_drive'
    ? 'Google Drive'
    : provider === 'sharepoint'
      ? 'SharePoint'
      : provider === 'dropbox'
        ? 'Dropbox'
        : 'Box'

  return (
    <div className="space-y-4">
      {!connected ? (
        <div className="flex flex-col items-center justify-center py-8 gap-3 border border-dashed border-border rounded-xl bg-secondary/30">
          <p className="text-sm text-muted-foreground">
            Connect {providerLabel} to continue
          </p>
          <Button size="sm" onClick={onConnect} className="gap-1.5">
            Connect {providerLabel}
          </Button>
        </div>
      ) : (
        <>
          <div>
            <p className="text-sm font-medium mb-1">Source folder</p>
            <p className="text-xs text-muted-foreground mb-2">
              New PDFs or images placed in this folder will be automatically extracted.
            </p>
            <FolderBrowser provider={provider} onSelect={onSelectSource} selected={sourceFolder} />
          </div>
          {sourceFolder && (
            <div className="flex items-center gap-2 p-2.5 rounded-lg bg-green-50 border border-green-200">
              <Check size={13} className="text-green-600 flex-shrink-0" />
              <span className="text-xs text-green-700">Watching: <strong>{sourceFolder.name}</strong></span>
            </div>
          )}
        </>
      )}
    </div>
  )
}

// ── Step 2 (Outlook): Mail folder + filters ────────────────────────────────

interface Step2OutlookProps {
  connected: boolean
  onConnect: () => void
  config: OutlookConfig
  onChange: (c: OutlookConfig) => void
}

function Step2Outlook({ connected, onConnect, config, onChange }: Step2OutlookProps) {
  const [mailFolders, setMailFolders] = useState<MailFolder[]>([])
  const [loading, setLoading] = useState(false)

  useEffect(() => {
    if (!connected) return
    setLoading(true)
    api.get('/pipelines/mail-folders')
      .then(r => setMailFolders(r.data.folders || []))
      .catch(() => {})
      .finally(() => setLoading(false))
  }, [connected])

  if (!connected) {
    return (
      <div className="flex flex-col items-center justify-center py-8 gap-3 border border-dashed border-border rounded-xl bg-secondary/30">
        <p className="text-sm text-muted-foreground">
          Connect your Microsoft account to access Outlook
        </p>
        <Button size="sm" onClick={onConnect} className="gap-1.5">
          Connect Microsoft Account
        </Button>
      </div>
    )
  }

  // Merge API folders with a guaranteed Inbox entry
  const allFolders: MailFolder[] = [
    { id: 'inbox', displayName: 'Inbox', unreadItemCount: 0 },
    ...mailFolders.filter(f => f.id !== 'inbox' && f.displayName.toLowerCase() !== 'inbox'),
  ]

  return (
    <div className="space-y-4">
      {/* Mail folder selector */}
      <div>
        <p className="text-sm font-medium mb-1">Watch folder</p>
        <p className="text-xs text-muted-foreground mb-2">
          New emails with PDF or image attachments in this folder will be processed.
        </p>
        {loading ? (
          <div className="flex items-center gap-2 py-3">
            <Loader2 size={13} className="animate-spin text-muted-foreground" />
            <span className="text-xs text-muted-foreground">Loading folders…</span>
          </div>
        ) : (
          <div className="grid gap-1.5 max-h-36 overflow-y-auto">
            {allFolders.map(folder => (
              <button
                key={folder.id}
                onClick={() => onChange({ ...config, folder_id: folder.id, folder_name: folder.displayName })}
                className={cn(
                  'flex items-center justify-between px-3 py-2 rounded-lg border text-left transition-colors text-sm',
                  config.folder_id === folder.id
                    ? 'border-primary bg-primary/5 text-primary'
                    : 'border-border hover:border-primary/40 bg-white'
                )}
              >
                <span>{folder.displayName}</span>
                {config.folder_id === folder.id && <Check size={13} className="text-primary" />}
              </button>
            ))}
          </div>
        )}
      </div>

      {/* Email filters */}
      <div className="grid grid-cols-2 gap-3">
        <div>
          <p className="text-xs font-medium mb-1 text-muted-foreground">
            From filter <span className="text-muted-foreground/50">(optional)</span>
          </p>
          <Input
            placeholder="sender@example.com"
            value={config.from_filter}
            onChange={e => onChange({ ...config, from_filter: e.target.value })}
            className="h-8 text-xs"
          />
        </div>
        <div>
          <p className="text-xs font-medium mb-1 text-muted-foreground">
            Subject filter <span className="text-muted-foreground/50">(optional)</span>
          </p>
          <Input
            placeholder="e.g. Invoice"
            value={config.subject_filter}
            onChange={e => onChange({ ...config, subject_filter: e.target.value })}
            className="h-8 text-xs"
          />
        </div>
      </div>

      {/* Mark as read toggle */}
      <div className="flex items-center gap-3 p-3 rounded-lg bg-secondary/40 border border-border">
        <button
          onClick={() => onChange({ ...config, mark_as_read: !config.mark_as_read })}
          className={cn(
            'relative w-9 h-5 rounded-full transition-colors flex-shrink-0',
            config.mark_as_read ? 'bg-primary' : 'bg-border'
          )}
        >
          <span className={cn(
            'absolute top-0.5 left-0.5 w-4 h-4 rounded-full bg-white shadow transition-transform',
            config.mark_as_read ? 'translate-x-4' : 'translate-x-0'
          )} />
        </button>
        <div>
          <p className="text-xs font-medium">Mark emails as read after processing</p>
          <p className="text-[11px] text-muted-foreground">Requires Mail.ReadWrite permission</p>
        </div>
      </div>
    </div>
  )
}

// ── Step 3: Extraction fields ──────────────────────────────────────────────

function Step3({ fields, onChange }: { fields: Field[]; onChange: (f: Field[]) => void }) {
  return (
    <div className="space-y-3">
      <p className="text-xs text-muted-foreground">
        Choose which fields to extract from each PDF. Add descriptions to improve accuracy.
      </p>
      <FieldsEditor fields={fields} onChange={onChange} />
    </div>
  )
}

// ── Step 4: Destination + confirm ─────────────────────────────────────────

interface Step4Props {
  provider: Provider
  destFolder: DriveFolder | null
  onSelectDest: (f: DriveFolder) => void
  format: Format
  onFormatChange: (f: Format) => void
  name: string
  onNameChange: (n: string) => void
  sourceName: string
  fields: Field[]
}

function Step4({ provider, destFolder, onSelectDest, format, onFormatChange, name, onNameChange, sourceName, fields }: Step4Props) {
  const folderProvider: FolderProvider = provider === 'outlook' ? 'sharepoint' : provider as FolderProvider
  return (
    <div className="space-y-4">
      <div>
        <p className="text-sm font-medium mb-1">Destination folder</p>
        <p className="text-xs text-muted-foreground mb-2">
          Extracted data will be saved here as <strong>{name || 'Pipeline'}.{format}</strong> — new runs append to the same file.
        </p>
        <FolderBrowser provider={folderProvider} onSelect={onSelectDest} selected={destFolder} />
      </div>

      <div>
        <p className="text-sm font-medium mb-2">Output format</p>
        <div className="flex rounded-lg border border-border overflow-hidden w-fit">
          {(['xlsx', 'csv'] as Format[]).map(f => (
            <button
              key={f}
              onClick={() => onFormatChange(f)}
              className={cn(
                'px-4 py-1.5 text-xs font-medium transition-colors',
                format === f ? 'bg-primary text-white' : 'bg-background text-muted-foreground hover:bg-secondary'
              )}
            >
              .{f.toUpperCase()}
            </button>
          ))}
        </div>
      </div>

      <div>
        <p className="text-sm font-medium mb-1">Pipeline name</p>
        <Input value={name} onChange={e => onNameChange(e.target.value)} placeholder="e.g. Invoice Pipeline" className="h-8 text-sm" />
      </div>

      {sourceName && destFolder && (
        <div className="rounded-lg border border-border bg-secondary/40 p-3 space-y-1.5 text-xs">
          <div className="flex items-center gap-1.5 text-muted-foreground">
            <FolderOpen size={11} />
            <span>Source → </span>
            <span className="font-medium text-foreground">{sourceName}</span>
          </div>
          <div className="flex items-center gap-1.5 text-muted-foreground">
            <FolderOpen size={11} />
            <span>Output → </span>
            <span className="font-medium text-foreground">{destFolder.name}/{name || '…'}.{format}</span>
          </div>
          <div className="flex items-center gap-1.5 text-muted-foreground">
            <Check size={11} />
            <span>{fields.length} field{fields.length !== 1 ? 's' : ''}: </span>
            <span className="font-medium text-foreground truncate">{fields.map(f => f.name).join(', ')}</span>
          </div>
        </div>
      )}
    </div>
  )
}

// ── Wizard (create + edit) ─────────────────────────────────────────────────

interface Props {
  open: boolean
  onClose: () => void
  onCreated: (pipeline: PipelineData) => void
  /** When provided, wizard runs in edit mode (PATCH instead of POST) */
  pipeline?: PipelineData
}

const STEP_LABELS = ['Provider', 'Source', 'Fields', 'Destination']

const DEFAULT_OUTLOOK_CONFIG: OutlookConfig = {
  folder_id: 'inbox',
  folder_name: 'Inbox',
  from_filter: '',
  subject_filter: '',
  mark_as_read: true,
}

export default function PipelineCreateWizard({ open, onClose, onCreated, pipeline }: Props) {
  const { token } = useAuthStore()
  const isEdit = !!pipeline

  const [step, setStep] = useState(isEdit ? 1 : 0)
  const [provider, setProvider] = useState<Provider | null>(pipeline?.source_type ?? null)
  const [connections, setConnections] = useState<Record<string, string | null>>({
    google_drive: null, sharepoint: null, dropbox: null, box: null, outlook: null,
  })
  const [sourceFolder, setSourceFolder] = useState<DriveFolder | null>(
    pipeline && pipeline.source_type !== 'outlook'
      ? { id: pipeline.source_folder_id, name: pipeline.source_folder_name }
      : null
  )
  const [outlookConfig, setOutlookConfig] = useState<OutlookConfig>(() => {
    if (pipeline?.source_type === 'outlook') {
      const cfg = pipeline.source_config || {}
      return {
        folder_id: pipeline.source_folder_id || 'inbox',
        folder_name: pipeline.source_folder_name || 'Inbox',
        from_filter: cfg.from_filter || '',
        subject_filter: cfg.subject_filter || '',
        mark_as_read: cfg.mark_as_read ?? true,
      }
    }
    return DEFAULT_OUTLOOK_CONFIG
  })
  const [destFolder, setDestFolder] = useState<DriveFolder | null>(
    pipeline ? { id: pipeline.dest_folder_id, name: pipeline.dest_folder_name } : null
  )
  const [fields, setFields] = useState<Field[]>(
    pipeline ? pipeline.fields : [
      { name: 'Invoice Number', description: '' },
      { name: 'Date', description: '' },
      { name: 'Total Amount', description: '' },
    ]
  )
  const [format, setFormat] = useState<Format>((pipeline?.dest_format as Format) ?? 'xlsx')
  const [pipelineName, setPipelineName] = useState(pipeline?.name ?? '')
  const [submitting, setSubmitting] = useState(false)

  // Load connections when opened
  useEffect(() => {
    if (open) {
      api.get('/pipelines/connections').then(r => setConnections(r.data)).catch(() => {})
    }
  }, [open])

  // Reset on open (only for create mode)
  useEffect(() => {
    if (open && !isEdit) {
      setStep(0)
      setProvider(null)
      setSourceFolder(null)
      setOutlookConfig(DEFAULT_OUTLOOK_CONFIG)
      setDestFolder(null)
      setFields([
        { name: 'Invoice Number', description: '' },
        { name: 'Date', description: '' },
        { name: 'Total Amount', description: '' },
      ])
      setFormat('xlsx')
      setPipelineName('')
    } else if (open && isEdit && pipeline) {
      setStep(1)
      setProvider(pipeline.source_type)
      if (pipeline.source_type === 'outlook') {
        const cfg = pipeline.source_config || {}
        setOutlookConfig({
          folder_id: pipeline.source_folder_id || 'inbox',
          folder_name: pipeline.source_folder_name || 'Inbox',
          from_filter: cfg.from_filter || '',
          subject_filter: cfg.subject_filter || '',
          mark_as_read: cfg.mark_as_read ?? true,
        })
        setSourceFolder(null)
      } else {
        setSourceFolder({ id: pipeline.source_folder_id, name: pipeline.source_folder_name })
      }
      setDestFolder({ id: pipeline.dest_folder_id, name: pipeline.dest_folder_name })
      setFields(pipeline.fields)
      setFormat(pipeline.dest_format as Format)
      setPipelineName(pipeline.name)
    }
  }, [open])

  const handleConnect = () => {
    if (!provider) return
    const endpoint = provider === 'google_drive'
      ? 'google'
      : provider === 'sharepoint' || provider === 'outlook'
        ? 'microsoft'
        : provider
    window.location.href = `/api/pipelines/oauth/${endpoint}?token=${token}`
  }

  const isConnected = provider
    ? provider === 'outlook'
      ? !!(connections['sharepoint'] || connections['outlook'])
      : !!connections[provider]
    : false

  const sourceName = provider === 'outlook'
    ? outlookConfig.folder_name
    : sourceFolder?.name ?? ''

  const canAdvance = (): boolean => {
    if (step === 0) return provider !== null
    if (step === 1) {
      if (!isConnected) return false
      if (provider === 'outlook') return outlookConfig.folder_id !== ''
      return sourceFolder !== null
    }
    if (step === 2) return fields.length > 0
    if (step === 3) return destFolder !== null && pipelineName.trim().length > 0
    return false
  }

  const handleSubmit = async () => {
    if (!provider || !destFolder) return
    setSubmitting(true)
    try {
      const src_folder_id = provider === 'outlook' ? outlookConfig.folder_id : sourceFolder?.id ?? ''
      const src_folder_name = provider === 'outlook' ? outlookConfig.folder_name : sourceFolder?.name ?? ''

      const payload: Record<string, any> = {
        name: pipelineName.trim(),
        source_type: provider,
        source_folder_id: src_folder_id,
        source_folder_name: src_folder_name,
        dest_folder_id: destFolder.id,
        dest_folder_name: destFolder.name,
        dest_format: format,
        fields,
      }

      if (provider === 'outlook') {
        payload.source_config = {
          from_filter: outlookConfig.from_filter,
          subject_filter: outlookConfig.subject_filter,
          mark_as_read: outlookConfig.mark_as_read,
        }
      }

      if (isEdit && pipeline) {
        const r = await api.patch(`/pipelines/${pipeline.id}`, payload)
        onCreated(r.data)
      } else {
        const r = await api.post('/pipelines/', payload)
        onCreated(r.data)
      }
    } catch (err: any) {
      toast.error(err?.response?.data?.detail || 'Failed to save pipeline')
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <Dialog.Root open={open} onOpenChange={v => !v && onClose()}>
      <Dialog.Portal>
        <Dialog.Overlay className="fixed inset-0 bg-black/40 backdrop-blur-sm z-50" />
        <Dialog.Content className="fixed left-1/2 top-1/2 -translate-x-1/2 -translate-y-1/2 z-50 w-[520px] max-w-[95vw] max-h-[90vh] bg-card border border-border rounded-2xl shadow-2xl flex flex-col overflow-hidden">
          {/* Header */}
          <div className="flex items-center justify-between px-4 sm:px-5 py-3 sm:py-4 border-b border-border">
            <div>
              <Dialog.Title className="font-semibold text-base">
                {isEdit ? `Edit: ${pipeline?.name}` : 'New Pipeline'}
              </Dialog.Title>
              <p className="text-xs text-muted-foreground mt-0.5">
                Step {step + 1} of 4 — {STEP_LABELS[step]}
              </p>
            </div>
            <Dialog.Close asChild>
              <button className="w-7 h-7 rounded-md flex items-center justify-center text-muted-foreground hover:bg-accent">
                <X size={15} />
              </button>
            </Dialog.Close>
          </div>

          {/* Progress bar */}
          <div className="h-1 bg-secondary">
            <div className="h-full bg-primary transition-all duration-300" style={{ width: `${((step + 1) / 4) * 100}%` }} />
          </div>

          {/* Step nav pills (edit mode: all clickable) */}
          {isEdit && (
            <div className="flex gap-1 px-3 sm:px-5 py-2.5 border-b border-border bg-secondary/30 overflow-x-auto">
              {STEP_LABELS.map((label, idx) => (
                <button
                  key={idx}
                  onClick={() => setStep(idx < 1 ? 1 : idx)}
                  className={cn(
                    'flex-1 py-1 text-[11px] sm:text-xs rounded-md transition-colors whitespace-nowrap',
                    step === idx
                      ? 'bg-primary text-white font-medium'
                      : 'text-muted-foreground hover:bg-accent'
                  )}
                >
                  {label}
                </button>
              ))}
            </div>
          )}

          {/* Step content */}
          <div className="flex-1 overflow-y-auto px-4 sm:px-5 py-4">
            {step === 0 && (
              <Step1
                connections={connections}
                selected={provider}
                onSelect={(nextProvider) => {
                  setProvider(nextProvider)
                  setSourceFolder(null)
                  setDestFolder(null)
                  if (nextProvider !== 'outlook') setOutlookConfig(DEFAULT_OUTLOOK_CONFIG)
                }}
              />
            )}
            {step === 1 && provider && (
              provider === 'outlook' ? (
                <Step2Outlook
                  connected={isConnected}
                  onConnect={handleConnect}
                  config={outlookConfig}
                  onChange={setOutlookConfig}
                />
              ) : (
                <Step2Drive
                  provider={provider as FolderProvider}
                  connected={isConnected}
                  onConnect={handleConnect}
                  sourceFolder={sourceFolder}
                  onSelectSource={setSourceFolder}
                />
              )
            )}
            {step === 2 && (
              <Step3 fields={fields} onChange={setFields} />
            )}
            {step === 3 && provider && (
              <Step4
                provider={provider}
                destFolder={destFolder}
                onSelectDest={setDestFolder}
                format={format}
                onFormatChange={setFormat}
                name={pipelineName}
                onNameChange={setPipelineName}
                sourceName={sourceName}
                fields={fields}
              />
            )}
          </div>

          {/* Footer */}
          <div className="flex items-center justify-between px-4 sm:px-5 py-3 sm:py-3.5 border-t border-border bg-secondary/20">
            <Button
              variant="ghost"
              size="sm"
              disabled={step === (isEdit ? 1 : 0)}
              onClick={() => setStep(s => s - 1)}
              className="gap-1.5"
            >
              <ChevronLeft size={14} /> Back
            </Button>

            {step < 3 ? (
              <Button
                size="sm"
                disabled={!canAdvance()}
                onClick={() => setStep(s => s + 1)}
                className="gap-1.5"
              >
                Next <ChevronRight size={14} />
              </Button>
            ) : (
              <Button
                size="sm"
                disabled={!canAdvance() || submitting}
                onClick={handleSubmit}
                className="gap-1.5"
              >
                {submitting
                  ? <><Loader2 size={13} className="animate-spin" /> {isEdit ? 'Saving…' : 'Creating…'}</>
                  : isEdit ? 'Save Changes' : 'Create Pipeline'
                }
              </Button>
            )}
          </div>
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  )
}
