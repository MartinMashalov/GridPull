import { useState, useEffect, useRef } from 'react'
import { trackEvent } from '@/lib/analytics'
import * as Dialog from '@radix-ui/react-dialog'
import { X, Plus, Trash2, StickyNote } from 'lucide-react'
import { ExtractionField, ExportFormat } from '@/pages/DashboardPage'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { cn } from '@/lib/utils'

const PRESET_FIELDS = [
  'Date', 'Total Amount', 'Company Name', 'Invoice Number',
  'Revenue', 'Net Income', 'Contract Value', 'Effective Date',
  'Address', 'Signatory', 'Description', 'Tax Amount',
]

interface Props {
  open: boolean
  onClose: () => void
  onConfirm: (fields: ExtractionField[], format: ExportFormat) => void
  defaultFormat: ExportFormat
}

export default function ExtractionFieldsModal({ open, onClose, onConfirm, defaultFormat }: Props) {
  const [fields, setFields] = useState<ExtractionField[]>([
    { name: 'Invoice Number', description: '' },
    { name: 'Date', description: '' },
    { name: 'Total Amount', description: '' },
  ])
  const [newFieldName, setNewFieldName] = useState('')
  const [expandedDesc, setExpandedDesc] = useState<number | null>(null)
  const fieldsEndRef = useRef<HTMLDivElement>(null)
  const inputRef = useRef<HTMLInputElement>(null)

  const scrollToBottom = () => {
    setTimeout(() => fieldsEndRef.current?.scrollIntoView({ behavior: 'smooth', block: 'nearest' }), 30)
  }

  const addPreset = (name: string) => {
    if (!fields.find(f => f.name === name)) {
      setFields(prev => [...prev, { name, description: '' }])
      trackEvent('field_added', { field: name, type: 'preset' })
      scrollToBottom()
    }
  }

  const addCustom = () => {
    const trimmed = newFieldName.trim()
    if (!trimmed) return
    setFields(prev => [...prev, { name: trimmed, description: '' }])
    trackEvent('field_added', { field: trimmed, type: 'custom' })
    setNewFieldName('')
    scrollToBottom()
    setTimeout(() => inputRef.current?.focus(), 40)
  }

  const removeField = (index: number) => {
    setFields(prev => prev.filter((_, i) => i !== index))
    if (expandedDesc === index) setExpandedDesc(null)
  }

  const updateDescription = (index: number, desc: string) => {
    setFields(prev => prev.map((f, i) => i === index ? { ...f, description: desc } : f))
  }

  const toggleDesc = (index: number) => {
    setExpandedDesc(prev => prev === index ? null : index)
  }

  const handleSubmit = () => {
    if (fields.length === 0) return
    onConfirm(fields, defaultFormat)
  }

  // Enter outside the input → submit
  // Delay adding the listener by 300ms so the keypress that OPENED the modal
  // doesn't immediately submit it too.
  useEffect(() => {
    if (!open) return
    const onKey = (e: KeyboardEvent) => {
      if (e.key !== 'Enter') return
      const target = e.target as HTMLElement
      if (target === inputRef.current) return
      if (target.tagName === 'TEXTAREA') return
      if (fields.length === 0) return
      e.preventDefault()
      handleSubmit()
    }
    const t = setTimeout(() => window.addEventListener('keydown', onKey), 300)
    return () => { clearTimeout(t); window.removeEventListener('keydown', onKey) }
  }, [open, fields, defaultFormat])

  return (
    <Dialog.Root open={open} onOpenChange={(o) => !o && onClose()}>
      <Dialog.Portal>
        <Dialog.Overlay className="fixed inset-0 bg-black/40 backdrop-blur-sm z-50" />
        <Dialog.Content className="fixed left-1/2 top-1/2 -translate-x-1/2 -translate-y-1/2 z-50 bg-card border border-border rounded-2xl shadow-xl w-[calc(100%-2rem)] max-w-lg max-h-[85vh] overflow-y-auto">
          <div className="p-4 sm:p-5">
            {/* Header */}
            <div className="flex items-center justify-between mb-5">
              <Dialog.Title className="text-sm font-semibold text-foreground">Choose fields to extract</Dialog.Title>
              <button onClick={onClose} className="text-muted-foreground hover:text-foreground transition-colors">
                <X size={16} />
              </button>
            </div>

            {/* Helper text */}
            <p className="text-xs text-muted-foreground mb-3">
              Select the data points you want to pull from each document. Each field becomes a column in your spreadsheet, and each document becomes a row.
            </p>

            {/* Quick Add presets */}
            <div className="flex flex-wrap gap-1.5 mb-4">
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
              <div className="space-y-1 mb-4 max-h-64 overflow-y-auto scrollbar-thin pr-0.5">
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
                        <button onClick={() => removeField(i)} className="p-1 rounded text-muted-foreground hover:text-red-500 transition-colors">
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
                          onChange={e => updateDescription(i, e.target.value)}
                          placeholder="Describe what to look for, or how to calculate (e.g. 'Net Income ÷ Revenue × 100')…"
                          className="w-full text-xs bg-transparent resize-none outline-none text-foreground placeholder:text-muted-foreground/60 leading-relaxed"
                        />
                      </div>
                    )}
                  </div>
                ))}
                <div ref={fieldsEndRef} />
              </div>
            )}

            {/* Custom field input */}
            <div className="flex gap-2 mb-5">
              <Input
                ref={inputRef}
                placeholder="Add custom field…"
                value={newFieldName}
                onChange={e => setNewFieldName(e.target.value)}
                onKeyDown={e => {
                  if (e.key === 'Enter') {
                    e.preventDefault()
                    e.stopPropagation()
                    addCustom()
                  }
                }}
                className="text-sm"
              />
              <Button onClick={addCustom} disabled={!newFieldName.trim()} size="icon" variant="outline">
                <Plus size={14} />
              </Button>
            </div>

            {/* Actions */}
            <div className="flex gap-2">
              <Button onClick={onClose} variant="outline" className="flex-1" size="sm">
                Cancel
              </Button>
              <Button onClick={handleSubmit} disabled={fields.length === 0} className="flex-1" size="sm">
                Extract {fields.length > 0 ? `${fields.length} field${fields.length > 1 ? 's' : ''}` : ''}
              </Button>
            </div>
          </div>
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  )
}
