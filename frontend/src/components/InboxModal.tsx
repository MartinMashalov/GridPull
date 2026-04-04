import { useState, useEffect, useCallback, useRef } from 'react'
import { Mail, Copy, Check, ChevronDown, ChevronRight, Trash2, X, Loader2, RefreshCw, Upload, Plus, Smartphone } from 'lucide-react'
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
  onUploadDirect: () => void
}

function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`
}

export default function InboxModal({ open, onClose, onSelectDocuments, onUploadDirect }: Props) {
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
  const fileInputRef = useRef<HTMLInputElement>(null)
  const groupFileInputRef = useRef<HTMLInputElement>(null)
  const pendingGroupRef = useRef<InboxGroup | null>(null)

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
      setQrGroupKey(null)
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
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 backdrop-blur-sm"
      style={{ paddingLeft: 'var(--sidebar-offset, 0px)' }}
      onClick={onClose}
    >
      <div
        className="bg-white rounded-2xl shadow-2xl w-full max-w-2xl max-h-[85vh] flex flex-col mx-4"
        onClick={e => e.stopPropagation()}
        onDrop={handleDrop}
        onDragOver={handleDragOver}
      >
        {/* Header */}
        <div className="flex items-center justify-between px-6 py-4 border-b border-border">
          <div className="flex items-center gap-2">
            <Mail size={18} className="text-primary" />
            <h2 className="text-lg font-semibold">Document Inbox</h2>
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

        {/* Action bar */}
        <div className="px-6 py-2.5 border-b border-border bg-muted/30 flex items-center gap-2 flex-wrap">
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
          <Button
            size="sm"
            onClick={() => { onClose(); onUploadDirect() }}
            className="text-xs"
          >
            <Plus size={12} />
            Upload Files
          </Button>
          <div className="flex-1" />
          {ingestAddress ? (
            <div className="flex items-center gap-1.5">
              <span className="text-xs text-muted-foreground whitespace-nowrap">Email to:</span>
              <code className="text-[11px] font-mono bg-white border border-border rounded px-1.5 py-0.5 truncate max-w-[200px]">
                {ingestAddress}
              </code>
              <button onClick={copyAddress} className="p-0.5 rounded hover:bg-muted transition-colors flex-shrink-0">
                {copied ? <Check size={11} className="text-emerald-500" /> : <Copy size={11} className="text-muted-foreground" />}
              </button>
            </div>
          ) : (
            <button onClick={generateAddress} disabled={addressLoading} className="flex items-center gap-1 text-xs text-muted-foreground hover:text-foreground transition-colors">
              {addressLoading ? <Loader2 size={11} className="animate-spin" /> : <Mail size={11} />}
              Email forwarding
            </button>
          )}
        </div>

        {/* Inbox content */}
        <div className="flex-1 overflow-y-auto px-6 py-4">
          {inboxLoading && !inbox ? (
            <div className="flex items-center justify-center py-12">
              <Loader2 size={20} className="animate-spin text-muted-foreground" />
            </div>
          ) : !inbox || inbox.groups.length === 0 ? (
            <div
              className="text-center py-12 border-2 border-dashed border-border rounded-xl cursor-pointer hover:border-primary/40 hover:bg-accent/30 transition-colors"
              onClick={() => fileInputRef.current?.click()}
            >
              <Upload size={32} className="mx-auto text-muted-foreground/40 mb-3" />
              <p className="text-sm text-muted-foreground">No documents yet</p>
              <p className="text-xs text-muted-foreground/70 mt-1">
                Click to upload files, drag & drop, or forward emails
              </p>
            </div>
          ) : (
            <div className="space-y-2">
              {inbox.groups.map(group => {
                const isExpanded = expandedGroups.has(group.key)
                const groupIds = group.documents.map(d => d.id)
                const allGroupSelected = groupIds.every(id => selected.has(id))
                const someGroupSelected = groupIds.some(id => selected.has(id))
                const isQrOpen = qrGroupKey === group.key && !!qrUrl

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
                          "p-1.5 rounded-lg transition-colors flex-shrink-0",
                          isQrOpen
                            ? "bg-primary/10 text-primary"
                            : "hover:bg-muted text-muted-foreground hover:text-foreground"
                        )}
                        title="Mobile upload to this group"
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

                    {/* QR code for this group */}
                    {isQrOpen && (
                      <div className="px-4 py-4 bg-primary/5 border-b border-primary/10 flex flex-col items-center gap-3 text-center">
                        <div className="bg-white p-3 rounded-xl border border-border shadow-sm inline-block">
                          <QRCodeSVG value={qrUrl} size={120} level="M" />
                        </div>
                        <div>
                          <p className="text-xs font-medium text-foreground">Scan this QR code with your phone camera</p>
                          <p className="text-xs text-muted-foreground mt-1">
                            Take a photo or pick one from your gallery. The file will be added to this group automatically.
                          </p>
                          <p className="text-xs text-muted-foreground mt-0.5">Link expires in 1 hour.</p>
                        </div>
                        <button
                          onClick={() => { setQrUrl(null); setQrGroupKey(null) }}
                          className="text-xs text-muted-foreground hover:text-foreground transition-colors"
                        >
                          Dismiss
                        </button>
                      </div>
                    )}

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
            <Button size="sm" onClick={handleUseSelected} disabled={selected.size === 0}>
              Use Selected ({selected.size})
            </Button>
          </div>
        </div>
      </div>
    </div>
  )
}
