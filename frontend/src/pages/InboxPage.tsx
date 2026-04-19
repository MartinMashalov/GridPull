import { useState, useEffect, useCallback, useRef } from 'react'
import {
  Mail, Copy, Check, ChevronDown, ChevronRight, Trash2,
  Loader2, RefreshCw, Upload, Smartphone, Inbox, Table2, Clipboard,
} from 'lucide-react'
import { QRCodeSVG } from 'qrcode.react'
import { useNavigate } from 'react-router-dom'
import api from '@/lib/api'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { Checkbox } from '@/components/ui/checkbox'
import UsagePill from '@/components/UsagePill'
import { cn } from '@/lib/utils'
import toast from 'react-hot-toast'

// ── Types ─────────────────────────────────────────────────────────────────

interface IngestDocument {
  id: string
  filename: string
  sender_email: string
  subject: string | null
  file_size: number
  content_type: string | null
  created_at: string | null
  expires_at: string | null
}

interface InboxGroup {
  key: string
  sender_display: string
  documents: IngestDocument[]
  count: number
  latest_at: string | null
}

interface InboxData {
  groups: InboxGroup[]
  total_documents: number
}

// ── Helpers ───────────────────────────────────────────────────────────────

function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`
}

function formatDate(iso: string | null): string {
  if (!iso) return ''
  const d = new Date(iso)
  const now = new Date()
  const diff = now.getTime() - d.getTime()
  const mins = Math.floor(diff / 60000)
  if (mins < 1) return 'just now'
  if (mins < 60) return `${mins}m ago`
  const hrs = Math.floor(mins / 60)
  if (hrs < 24) return `${hrs}h ago`
  const days = Math.floor(hrs / 24)
  if (days < 7) return `${days}d ago`
  return d.toLocaleDateString('en-US', { month: 'short', day: 'numeric' })
}

function contentTypeLabel(ct: string | null): string {
  if (!ct) return 'file'
  if (ct.includes('pdf')) return 'PDF'
  if (ct.includes('image')) return 'Image'
  if (ct.includes('spreadsheet') || ct.includes('excel') || ct.includes('xlsx')) return 'Excel'
  if (ct.includes('csv')) return 'CSV'
  if (ct.includes('html')) return 'HTML'
  if (ct.includes('json')) return 'JSON'
  if (ct.includes('xml')) return 'XML'
  if (ct.includes('text') || ct.includes('plain')) return 'Text'
  if (ct.includes('rfc822') || ct.includes('outlook') || ct.includes('msg')) return 'Email'
  if (ct.includes('zip')) return 'ZIP'
  return 'File'
}

// ── Component ─────────────────────────────────────────────────────────────

export default function InboxPage() {
  const navigate = useNavigate()

  const [ingestAddress, setIngestAddress] = useState<string | null>(null)
  const [addressLoading, setAddressLoading] = useState(false)
  const [inbox, setInbox] = useState<InboxData | null>(null)
  const [inboxLoading, setInboxLoading] = useState(false)
  const [copied, setCopied] = useState(false)
  const [selected, setSelected] = useState<Set<string>>(new Set())
  const [expandedGroups, setExpandedGroups] = useState<Set<string>>(new Set())
  const [qrUrl, setQrUrl] = useState<string | null>(null)
  const [qrGroupKey, setQrGroupKey] = useState<string | null>(null)
  const [qrLoading, setQrLoading] = useState<string | null>(null)
  const [uploading, setUploading] = useState(false)
  const [deleting, setDeleting] = useState(false)
  const fileInputRef = useRef<HTMLInputElement>(null)
  const groupFileInputRef = useRef<HTMLInputElement>(null)
  const pendingGroupRef = useRef<InboxGroup | null>(null)

  // ── Data fetching ────────────────────────────────────────────────────

  const fetchAddress = useCallback(async () => {
    try {
      const res = await api.get('/ingest/address')
      setIngestAddress(res.data.address)
    } catch {
      setIngestAddress(null)
    }
  }, [])

  const fetchInbox = useCallback(async () => {
    setInboxLoading(true)
    try {
      const res = await api.get('/ingest/inbox')
      setInbox(res.data)
      // Auto-expand all groups on first load
      if (res.data?.groups) {
        setExpandedGroups(prev => {
          if (prev.size > 0) return prev
          return new Set(res.data.groups.map((g: InboxGroup) => g.key))
        })
      }
    } catch {
      setInbox(null)
    } finally {
      setInboxLoading(false)
    }
  }, [])

  useEffect(() => {
    fetchAddress()
    fetchInbox()
  }, [fetchAddress, fetchInbox])

  // ── Actions ──────────────────────────────────────────────────────────

  const generateAddress = async () => {
    setAddressLoading(true)
    try {
      const res = await api.post('/ingest/address')
      setIngestAddress(res.data.address)
      toast.success('Ingest email address created')
    } catch {
      toast.error('Failed to create address')
    } finally {
      setAddressLoading(false)
    }
  }

  const copyAddress = () => {
    if (ingestAddress) {
      navigator.clipboard.writeText(ingestAddress)
      setCopied(true)
      toast.success('Email address copied')
      setTimeout(() => setCopied(false), 2000)
    }
  }

  const generateQrForGroup = async (group: InboxGroup) => {
    setQrLoading(group.key)
    try {
      const firstDoc = group.documents[0]
      const res = await api.post('/ingest/mobile-session', {
        sender_email: firstDoc?.sender_email || '',
        sender_domain: firstDoc?.sender_email?.split('@')[1] || '',
      })
      setQrUrl(res.data.url)
      setQrGroupKey(group.key)
    } catch {
      toast.error('Failed to create mobile session')
    } finally {
      setQrLoading(null)
    }
  }

  const handleFileUpload = async (fileList: FileList | null, group?: InboxGroup) => {
    if (!fileList || fileList.length === 0) return
    setUploading(true)
    try {
      const fd = new FormData()
      for (let i = 0; i < fileList.length; i++) {
        fd.append('files', fileList[i])
      }
      if (group) {
        const firstDoc = group.documents[0]
        if (firstDoc) {
          fd.append('sender_email', firstDoc.sender_email)
          fd.append('sender_domain', firstDoc.sender_email.split('@')[1] || '')
        }
      }
      const res = await api.post('/ingest/inbox/upload', fd)
      const count = res.data.count ?? 0
      if (count > 0) {
        toast.success(`${count} file${count !== 1 ? 's' : ''} uploaded`)
        await fetchInbox()
      } else {
        toast.error('No files were uploaded')
      }
    } catch {
      toast.error('Upload failed')
    } finally {
      setUploading(false)
      if (fileInputRef.current) fileInputRef.current.value = ''
      if (groupFileInputRef.current) groupFileInputRef.current.value = ''
    }
  }

  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault()
    e.stopPropagation()
    handleFileUpload(e.dataTransfer.files)
  }

  const handleDragOver = (e: React.DragEvent) => {
    e.preventDefault()
    e.stopPropagation()
  }

  const deleteSelectedDocuments = async () => {
    if (selected.size === 0) return
    setDeleting(true)
    try {
      await Promise.all(
        Array.from(selected).map(id => api.delete(`/ingest/inbox/${id}`))
      )
      toast.success(`Deleted ${selected.size} document${selected.size !== 1 ? 's' : ''}`)
      setSelected(new Set())
      await fetchInbox()
    } catch {
      toast.error('Failed to delete some documents')
    } finally {
      setDeleting(false)
    }
  }

  const deleteGroup = async (group: InboxGroup) => {
    try {
      await Promise.all(group.documents.map(d => api.delete(`/ingest/inbox/${d.id}`)))
      setSelected(prev => {
        const n = new Set(prev)
        group.documents.forEach(d => n.delete(d.id))
        return n
      })
      toast.success(`Deleted ${group.documents.length} file${group.documents.length !== 1 ? 's' : ''}`)
      await fetchInbox()
    } catch {
      toast.error('Failed to delete group')
    }
  }

  const deleteDoc = async (docId: string) => {
    try {
      await api.delete(`/ingest/inbox/${docId}`)
      setSelected(prev => { const n = new Set(prev); n.delete(docId); return n })
      fetchInbox()
    } catch {
      toast.error('Failed to delete document')
    }
  }

  // ── Selection helpers ────────────────────────────────────────────────

  const toggleGroup = (key: string) => {
    setExpandedGroups(prev => {
      const next = new Set(prev)
      if (next.has(key)) next.delete(key)
      else next.add(key)
      return next
    })
  }

  const toggleDoc = (docId: string) => {
    setSelected(prev => {
      const next = new Set(prev)
      if (next.has(docId)) next.delete(docId)
      else next.add(docId)
      return next
    })
  }

  const toggleGroupDocs = (docs: IngestDocument[]) => {
    const ids = docs.map(d => d.id)
    const allSelected = ids.every(id => selected.has(id))
    setSelected(prev => {
      const next = new Set(prev)
      ids.forEach(id => allSelected ? next.delete(id) : next.add(id))
      return next
    })
  }

  // ── Navigation actions ───────────────────────────────────────────────

  const useInSchedules = () => {
    if (selected.size === 0) { toast.error('Select at least one document'); return }
    const ids = Array.from(selected)
    navigate(`/schedules?inbox_docs=${ids.join(',')}`)
  }

  const useInFormFilling = () => {
    if (selected.size === 0) { toast.error('Select at least one document'); return }
    const ids = Array.from(selected)
    navigate(`/form-filling?inbox_docs=${ids.join(',')}`)
  }

  // ── Render ───────────────────────────────────────────────────────────

  return (
    <div
      className="flex-1 overflow-y-auto"
      onDrop={handleDrop}
      onDragOver={handleDragOver}
    >
      <div className="relative max-w-4xl mx-auto p-4 sm:p-8">
        <div className="pointer-events-none absolute inset-x-0 top-0 h-48 bg-gradient-to-b from-primary/[0.03] to-transparent rounded-t-xl" />

        {/* Hidden file inputs */}
        <input
          ref={fileInputRef}
          type="file"
          multiple
          accept=".pdf,.png,.jpg,.jpeg,.webp,.gif,.bmp,.tif,.tiff,.txt,.md,.html,.htm,.json,.xml,.eml,.msg,.zip"
          className="hidden"
          onChange={e => handleFileUpload(e.target.files)}
        />
        <input
          ref={groupFileInputRef}
          type="file"
          multiple
          accept=".pdf,.png,.jpg,.jpeg,.webp,.gif,.bmp,.tif,.tiff,.txt,.md,.html,.htm,.json,.xml,.eml,.msg,.zip"
          className="hidden"
          onChange={e => {
            handleFileUpload(e.target.files, pendingGroupRef.current ?? undefined)
            pendingGroupRef.current = null
            if (groupFileInputRef.current) groupFileInputRef.current.value = ''
          }}
        />

        {/* ── Page header ──────────────────────────────────────────────── */}
        <div className="relative border-b border-border pb-5 mb-6">
          <div className="flex items-center justify-between gap-2">
            <div className="flex items-center gap-3 mb-2">
              <div className="p-2 rounded-xl bg-primary/10">
                <Inbox size={20} className="text-primary" />
              </div>
              <h1 className="text-xl font-semibold text-foreground">Document Inbox</h1>
            </div>
            <UsagePill />
          </div>
          <p className="text-sm text-muted-foreground mt-1 max-w-2xl leading-relaxed">
            Your own private mailbox for documents. Send emails with attachments to your personal address below, and the files show up here — sorted by who sent them. You can also drag files in from your computer or scan paper documents with your phone.
          </p>
        </div>

        {/* ── Ingest email address card ────────────────────────────────── */}
        <div className="bg-white border border-border rounded-xl p-5 mb-6">
          <div className="flex items-center justify-between gap-4 flex-wrap">
            <div className="flex items-center gap-3 min-w-0">
              <Mail size={16} className="text-muted-foreground flex-shrink-0" />
              <span className="text-sm font-medium text-foreground">Forwarding Address</span>
            </div>
            {ingestAddress ? (
              <div className="flex items-center gap-2">
                <code className="text-sm font-mono bg-muted border border-border rounded-lg px-3 py-1.5 truncate max-w-xs select-all">
                  {ingestAddress}
                </code>
                <Button
                  variant="outline"
                  size="sm"
                  onClick={copyAddress}
                  className="flex-shrink-0"
                >
                  {copied ? <Check size={14} className="text-emerald-500" /> : <Copy size={14} />}
                  {copied ? 'Copied' : 'Copy'}
                </Button>
              </div>
            ) : (
              <Button
                variant="outline"
                size="sm"
                onClick={generateAddress}
                disabled={addressLoading}
              >
                {addressLoading ? <Loader2 size={14} className="animate-spin" /> : <Mail size={14} />}
                Create Forwarding Address
              </Button>
            )}
          </div>
        </div>

        {/* ── Toolbar ──────────────────────────────────────────────────── */}
        <div className="flex items-center justify-between gap-3 mb-4 flex-wrap">
          <div className="flex items-center gap-2">
            <Button
              variant="outline"
              size="sm"
              onClick={() => fileInputRef.current?.click()}
              disabled={uploading}
            >
              {uploading ? <Loader2 size={14} className="animate-spin" /> : <Upload size={14} />}
              Upload Files
            </Button>
            <Button
              variant="outline"
              size="sm"
              onClick={fetchInbox}
              disabled={inboxLoading}
            >
              <RefreshCw size={14} className={cn(inboxLoading && 'animate-spin')} />
              Refresh
            </Button>
            {inbox && inbox.total_documents > 0 && (
              <Badge variant="secondary" className="text-xs">
                {inbox.total_documents} document{inbox.total_documents !== 1 ? 's' : ''}
              </Badge>
            )}
          </div>

          {/* Selection actions */}
          {selected.size > 0 && (
            <div className="flex items-center gap-2">
              <span className="text-xs text-muted-foreground mr-1">
                {selected.size} selected
              </span>
              <Button size="sm" variant="outline" onClick={useInSchedules}>
                <Table2 size={14} />
                Use in Schedules
              </Button>
              <Button size="sm" variant="outline" onClick={useInFormFilling}>
                <Clipboard size={14} />
                Use in Fill Applications
              </Button>
              <Button
                size="sm"
                variant="outline"
                onClick={deleteSelectedDocuments}
                disabled={deleting}
                className="text-red-500 hover:text-red-600 hover:bg-red-50 border-red-200"
              >
                {deleting ? <Loader2 size={14} className="animate-spin" /> : <Trash2 size={14} />}
                Delete
              </Button>
            </div>
          )}
        </div>

        {/* ── Inbox content ────────────────────────────────────────────── */}
        {inboxLoading && !inbox ? (
          <div className="flex items-center justify-center py-20">
            <Loader2 size={24} className="animate-spin text-muted-foreground" />
          </div>
        ) : !inbox || inbox.groups.length === 0 ? (
          <div
            className="text-center py-20 border-2 border-dashed border-border rounded-xl cursor-pointer hover:border-primary/40 hover:bg-accent/30 transition-colors"
            onClick={() => fileInputRef.current?.click()}
          >
            <Upload size={40} className="mx-auto text-muted-foreground/40 mb-4" />
            <p className="text-base font-medium text-muted-foreground">No documents yet</p>
            <p className="text-sm text-muted-foreground/70 mt-2">
              Click to upload files, drag and drop, or forward emails to your ingest address
            </p>
          </div>
        ) : (
          <div className="space-y-3">
            {/* Groups */}
            {inbox.groups.map(group => {
              const isExpanded = expandedGroups.has(group.key)
              const groupIds = group.documents.map(d => d.id)
              const allGroupSelected = groupIds.every(id => selected.has(id))
              const someGroupSelected = groupIds.some(id => selected.has(id))
              const isQrOpen = qrGroupKey === group.key && !!qrUrl

              return (
                <div key={group.key} className="bg-white border border-border rounded-xl overflow-hidden">
                  {/* Group header */}
                  <div
                    className="flex items-center gap-3 px-4 py-3 cursor-pointer hover:bg-muted/40 transition-colors"
                    onClick={() => toggleGroup(group.key)}
                  >
                    <div onClick={e => { e.stopPropagation(); toggleGroupDocs(group.documents) }}>
                      <Checkbox
                        checked={allGroupSelected}
                        className={cn(!allGroupSelected && someGroupSelected && 'opacity-50')}
                      />
                    </div>
                    {isExpanded
                      ? <ChevronDown size={14} className="text-muted-foreground flex-shrink-0" />
                      : <ChevronRight size={14} className="text-muted-foreground flex-shrink-0" />
                    }
                    <div className="flex-1 min-w-0">
                      <span className="text-sm font-medium text-foreground truncate block">
                        {group.sender_display}
                      </span>
                    </div>
                    <Badge variant="secondary" className="text-xs flex-shrink-0">
                      {group.count} file{group.count !== 1 ? 's' : ''}
                    </Badge>
                    {group.latest_at && (
                      <span className="text-xs text-muted-foreground flex-shrink-0">
                        {formatDate(group.latest_at)}
                      </span>
                    )}
                    {/* Group action buttons */}
                    <button
                      onClick={e => {
                        e.stopPropagation()
                        pendingGroupRef.current = group
                        groupFileInputRef.current?.click()
                      }}
                      className="p-1.5 rounded-lg hover:bg-muted text-muted-foreground hover:text-foreground transition-colors flex-shrink-0"
                      title="Upload files to this group"
                    >
                      {uploading ? <Loader2 size={14} className="animate-spin" /> : <Upload size={14} />}
                    </button>
                    <button
                      onClick={e => {
                        e.stopPropagation()
                        if (isQrOpen) {
                          setQrUrl(null)
                          setQrGroupKey(null)
                        } else {
                          generateQrForGroup(group)
                        }
                      }}
                      className={cn(
                        'p-1.5 rounded-lg transition-colors flex-shrink-0',
                        isQrOpen
                          ? 'bg-primary/10 text-primary'
                          : 'hover:bg-muted text-muted-foreground hover:text-foreground'
                      )}
                      title="Mobile upload QR code"
                    >
                      {qrLoading === group.key
                        ? <Loader2 size={14} className="animate-spin" />
                        : <Smartphone size={14} />
                      }
                    </button>
                    <button
                      onClick={e => {
                        e.stopPropagation()
                        deleteGroup(group)
                      }}
                      className="p-1.5 rounded-lg hover:bg-red-50 text-muted-foreground hover:text-red-500 transition-colors flex-shrink-0"
                      title="Delete all files in this group"
                    >
                      <Trash2 size={14} />
                    </button>
                  </div>

                  {/* QR code panel */}
                  {isQrOpen && (
                    <div className="px-5 py-5 bg-primary/5 border-t border-primary/10 flex flex-col items-center gap-3 text-center">
                      <div className="bg-white p-3 rounded-xl border border-border shadow-sm inline-block">
                        <QRCodeSVG value={qrUrl} size={140} level="M" />
                      </div>
                      <div>
                        <p className="text-sm font-medium text-foreground">
                          Scan with your phone camera
                        </p>
                        <p className="text-xs text-muted-foreground mt-1">
                          Take a photo or pick from your gallery. Files will be added to this group automatically.
                        </p>
                        <p className="text-xs text-muted-foreground mt-0.5">Link expires in 1 hour.</p>
                      </div>
                      <button
                        onClick={() => { setQrUrl(null); setQrGroupKey(null) }}
                        className="text-xs text-muted-foreground hover:text-foreground transition-colors underline"
                      >
                        Dismiss
                      </button>
                    </div>
                  )}

                  {/* Expanded documents */}
                  {isExpanded && (
                    <div className="divide-y divide-border border-t border-border">
                      {group.documents.map(doc => (
                        <div
                          key={doc.id}
                          className={cn(
                            'flex items-center gap-3 px-4 py-2.5 pl-12 h-12 hover:bg-muted/20 transition-colors',
                            selected.has(doc.id) && 'bg-primary/5'
                          )}
                        >
                          <div onClick={e => e.stopPropagation()}>
                            <Checkbox
                              checked={selected.has(doc.id)}
                              onCheckedChange={() => toggleDoc(doc.id)}
                            />
                          </div>
                          <div className="flex-1 min-w-0">
                            <p className="text-sm text-foreground truncate">{doc.filename}</p>
                          </div>
                          <Badge variant="outline" className="text-[10px] flex-shrink-0 w-20 justify-center">
                            {contentTypeLabel(doc.content_type)}
                          </Badge>
                          <span className="text-xs text-muted-foreground whitespace-nowrap flex-shrink-0 w-16 text-right">
                            {formatBytes(doc.file_size)}
                          </span>
                          <span className="text-xs text-muted-foreground whitespace-nowrap flex-shrink-0 w-20 text-right">
                            {doc.created_at ? formatDate(doc.created_at) : ''}
                          </span>
                          <button
                            onClick={e => { e.stopPropagation(); deleteDoc(doc.id) }}
                            className="p-1 rounded hover:bg-red-50 hover:text-red-500 transition-colors flex-shrink-0"
                            title="Delete document"
                          >
                            <Trash2 size={13} className="text-muted-foreground" />
                          </button>
                        </div>
                      ))}
                    </div>
                  )}
                </div>
              )
            })}
          </div>
        )}
      </div>
    </div>
  )
}
