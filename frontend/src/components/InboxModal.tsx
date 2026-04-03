import { useState, useEffect, useCallback } from 'react'
import { Mail, Copy, Check, ChevronDown, ChevronRight, Trash2, X, QrCode, Loader2, Smartphone, RefreshCw } from 'lucide-react'
import { QRCodeSVG } from 'qrcode.react'
import api from '@/lib/api'
import { Button } from '@/components/ui/button'
import { Checkbox } from '@/components/ui/checkbox'
import { cn } from '@/lib/utils'
import toast from 'react-hot-toast'

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

interface Props {
  open: boolean
  onClose: () => void
  onSelectDocuments: (docs: IngestDocument[]) => void
}

function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`
}

function timeAgo(dateStr: string | null): string {
  if (!dateStr) return ''
  const d = new Date(dateStr)
  const now = new Date()
  const diff = now.getTime() - d.getTime()
  const mins = Math.floor(diff / 60000)
  if (mins < 1) return 'just now'
  if (mins < 60) return `${mins}m ago`
  const hours = Math.floor(mins / 60)
  if (hours < 24) return `${hours}h ago`
  const days = Math.floor(hours / 24)
  return `${days}d ago`
}

export default function InboxModal({ open, onClose, onSelectDocuments }: Props) {
  const [ingestAddress, setIngestAddress] = useState<string | null>(null)
  const [addressLoading, setAddressLoading] = useState(false)
  const [inbox, setInbox] = useState<InboxData | null>(null)
  const [inboxLoading, setInboxLoading] = useState(false)
  const [copied, setCopied] = useState(false)
  const [selected, setSelected] = useState<Set<string>>(new Set())
  const [expandedGroups, setExpandedGroups] = useState<Set<string>>(new Set())
  const [qrUrl, setQrUrl] = useState<string | null>(null)
  const [qrLoading, setQrLoading] = useState(false)

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
    } catch {
      setInbox(null)
    } finally {
      setInboxLoading(false)
    }
  }, [])

  useEffect(() => {
    if (open) {
      fetchAddress()
      fetchInbox()
      setSelected(new Set())
      setQrUrl(null)
    }
  }, [open, fetchAddress, fetchInbox])

  if (!open) return null

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
      setTimeout(() => setCopied(false), 2000)
    }
  }

  const generateQr = async () => {
    setQrLoading(true)
    try {
      const res = await api.post('/ingest/mobile-session')
      setQrUrl(res.data.url)
    } catch {
      toast.error('Failed to create mobile session')
    } finally {
      setQrLoading(false)
    }
  }

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

  const deleteDoc = async (docId: string) => {
    try {
      await api.delete(`/ingest/inbox/${docId}`)
      setSelected(prev => { const n = new Set(prev); n.delete(docId); return n })
      fetchInbox()
    } catch {
      toast.error('Failed to delete document')
    }
  }

  const handleUseSelected = () => {
    if (!inbox) return
    const allDocs = inbox.groups.flatMap(g => g.documents)
    const selectedDocs = allDocs.filter(d => selected.has(d.id))
    if (selectedDocs.length === 0) {
      toast.error('Select at least one document')
      return
    }
    onSelectDocuments(selectedDocs)
    onClose()
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 backdrop-blur-sm" onClick={onClose}>
      <div
        className="bg-white rounded-2xl shadow-2xl w-full max-w-2xl max-h-[85vh] flex flex-col mx-4"
        onClick={e => e.stopPropagation()}
      >
        {/* Header */}
        <div className="flex items-center justify-between px-6 py-4 border-b border-border">
          <div className="flex items-center gap-2">
            <Mail size={18} className="text-primary" />
            <h2 className="text-lg font-semibold">Email Inbox</h2>
            {inbox && inbox.total_documents > 0 && (
              <span className="text-xs bg-primary/10 text-primary px-2 py-0.5 rounded-full font-medium">
                {inbox.total_documents}
              </span>
            )}
          </div>
          <div className="flex items-center gap-2">
            <button onClick={fetchInbox} className="p-1.5 rounded-lg hover:bg-muted transition-colors" title="Refresh">
              <RefreshCw size={14} className={cn("text-muted-foreground", inboxLoading && "animate-spin")} />
            </button>
            <button onClick={onClose} className="p-1.5 rounded-lg hover:bg-muted transition-colors">
              <X size={16} className="text-muted-foreground" />
            </button>
          </div>
        </div>

        {/* Ingest address + QR */}
        <div className="px-6 py-3 border-b border-border bg-muted/30">
          <div className="flex items-center gap-3 flex-wrap">
            {ingestAddress ? (
              <div className="flex items-center gap-2 flex-1 min-w-0">
                <span className="text-xs text-muted-foreground whitespace-nowrap">Forward emails to:</span>
                <code className="text-xs font-mono bg-white border border-border rounded px-2 py-1 truncate">
                  {ingestAddress}
                </code>
                <button onClick={copyAddress} className="p-1 rounded hover:bg-muted transition-colors flex-shrink-0">
                  {copied ? <Check size={13} className="text-emerald-500" /> : <Copy size={13} className="text-muted-foreground" />}
                </button>
              </div>
            ) : (
              <Button size="sm" variant="outline" onClick={generateAddress} disabled={addressLoading} className="text-xs">
                {addressLoading ? <Loader2 size={12} className="animate-spin" /> : <Mail size={12} />}
                Generate Email Address
              </Button>
            )}
            <Button size="sm" variant="outline" onClick={generateQr} disabled={qrLoading} className="text-xs flex-shrink-0">
              {qrLoading ? <Loader2 size={12} className="animate-spin" /> : <Smartphone size={12} />}
              Mobile Upload
            </Button>
          </div>

          {/* QR code */}
          {qrUrl && (
            <div className="mt-3 flex items-center gap-4 p-3 bg-white rounded-lg border border-border">
              <QRCodeSVG value={qrUrl} size={100} level="M" />
              <div className="flex-1 min-w-0">
                <p className="text-sm font-medium">Scan to upload from phone</p>
                <p className="text-xs text-muted-foreground mt-0.5">No login required. Link expires in 1 hour.</p>
                <code className="text-[10px] text-muted-foreground mt-1 block truncate">{qrUrl}</code>
              </div>
            </div>
          )}
        </div>

        {/* Inbox content */}
        <div className="flex-1 overflow-y-auto px-6 py-4">
          {inboxLoading && !inbox ? (
            <div className="flex items-center justify-center py-12">
              <Loader2 size={20} className="animate-spin text-muted-foreground" />
            </div>
          ) : !inbox || inbox.groups.length === 0 ? (
            <div className="text-center py-12">
              <Mail size={32} className="mx-auto text-muted-foreground/40 mb-3" />
              <p className="text-sm text-muted-foreground">No documents in your inbox</p>
              <p className="text-xs text-muted-foreground/70 mt-1">
                Forward emails to your ingest address or use mobile upload
              </p>
            </div>
          ) : (
            <div className="space-y-2">
              {inbox.groups.map(group => {
                const isExpanded = expandedGroups.has(group.key)
                const groupIds = group.documents.map(d => d.id)
                const allGroupSelected = groupIds.every(id => selected.has(id))
                const someGroupSelected = groupIds.some(id => selected.has(id))

                return (
                  <div key={group.key} className="border border-border rounded-lg overflow-hidden">
                    {/* Group header */}
                    <div
                      className="flex items-center gap-3 px-3 py-2.5 bg-muted/30 cursor-pointer hover:bg-muted/50 transition-colors"
                      onClick={() => toggleGroup(group.key)}
                    >
                      <div onClick={e => { e.stopPropagation(); toggleGroupDocs(group.documents) }}>
                        <Checkbox
                          checked={allGroupSelected}
                          className={cn(!allGroupSelected && someGroupSelected && "opacity-50")}
                        />
                      </div>
                      {isExpanded ? <ChevronDown size={14} className="text-muted-foreground" /> : <ChevronRight size={14} className="text-muted-foreground" />}
                      <span className="text-sm font-medium flex-1 truncate">{group.sender_display}</span>
                      <span className="text-xs text-muted-foreground">
                        {group.count} file{group.count !== 1 ? 's' : ''}
                      </span>
                      <span className="text-xs text-muted-foreground">{timeAgo(group.latest_at)}</span>
                    </div>

                    {/* Expanded documents */}
                    {isExpanded && (
                      <div className="divide-y divide-border">
                        {group.documents.map(doc => (
                          <div key={doc.id} className="flex items-center gap-3 px-3 py-2 pl-10 hover:bg-muted/20 transition-colors">
                            <div onClick={e => e.stopPropagation()}>
                              <Checkbox
                                checked={selected.has(doc.id)}
                                onCheckedChange={() => toggleDoc(doc.id)}
                              />
                            </div>
                            <div className="flex-1 min-w-0">
                              <p className="text-sm truncate">{doc.filename}</p>
                              {doc.subject && <p className="text-xs text-muted-foreground truncate">{doc.subject}</p>}
                            </div>
                            <span className="text-xs text-muted-foreground whitespace-nowrap">{formatBytes(doc.file_size)}</span>
                            <button
                              onClick={e => { e.stopPropagation(); deleteDoc(doc.id) }}
                              className="p-1 rounded hover:bg-red-50 hover:text-red-500 transition-colors"
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

        {/* Footer */}
        <div className="px-6 py-3 border-t border-border flex items-center justify-between">
          <span className="text-xs text-muted-foreground">
            {selected.size > 0 ? `${selected.size} document${selected.size !== 1 ? 's' : ''} selected` : 'Select documents to extract'}
          </span>
          <div className="flex gap-2">
            <Button variant="outline" size="sm" onClick={onClose}>Cancel</Button>
            <Button size="sm" onClick={handleUseSelected} disabled={selected.size === 0}>
              Use Selected ({selected.size})
            </Button>
          </div>
        </div>
      </div>
    </div>
  )
}
