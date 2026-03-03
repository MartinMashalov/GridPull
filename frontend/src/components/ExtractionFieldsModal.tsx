import { useState, useEffect } from 'react'
import * as Dialog from '@radix-ui/react-dialog'
import { X, Plus, Trash2 } from 'lucide-react'
import { ExtractionField, ExportFormat } from '@/pages/DashboardPage'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { cn } from '@/lib/utils'

const PRESET_FIELDS = [
  'Invoice Number', 'Date', 'Total Amount', 'Vendor Name', 'Customer Name',
  'Description', 'Quantity', 'Unit Price', 'Tax Amount', 'Due Date',
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
  const [format, setFormat] = useState<ExportFormat>(defaultFormat)
  const [newFieldName, setNewFieldName] = useState('')

  const addPreset = (name: string) => {
    if (!fields.find(f => f.name === name)) {
      setFields(prev => [...prev, { name, description: '' }])
    }
  }

  const addCustom = () => {
    if (!newFieldName.trim()) return
    setFields(prev => [...prev, { name: newFieldName.trim(), description: '' }])
    setNewFieldName('')
  }

  const removeField = (index: number) => {
    setFields(prev => prev.filter((_, i) => i !== index))
  }

  // Submit on Enter — fires from anywhere in the modal except when the user
  // is actively typing a custom field name (has text in the input)
  useEffect(() => {
    if (!open) return
    const onKey = (e: KeyboardEvent) => {
      if (e.key !== 'Enter') return
      const target = e.target as HTMLElement
      if (target.tagName === 'INPUT' && newFieldName.trim()) return
      if (fields.length === 0) return
      e.preventDefault()
      onConfirm(fields, format)
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [open, fields, format, newFieldName, onConfirm])

  return (
    <Dialog.Root open={open} onOpenChange={(o) => !o && onClose()}>
      <Dialog.Portal>
        <Dialog.Overlay className="fixed inset-0 bg-black/40 backdrop-blur-sm z-50" />
        <Dialog.Content className="fixed left-1/2 top-1/2 -translate-x-1/2 -translate-y-1/2 z-50 bg-card border border-border rounded-2xl shadow-xl w-full max-w-lg max-h-[85vh] overflow-y-auto">
          <div className="p-5">
            {/* Header */}
            <div className="flex items-center justify-between mb-5">
              <Dialog.Title className="text-sm font-semibold text-foreground">Extraction Fields</Dialog.Title>
              <div className="flex items-center gap-3">
                {/* Format toggle inline with header */}
                <div className="flex bg-secondary border border-border rounded-lg overflow-hidden">
                  {(['xlsx', 'csv'] as ExportFormat[]).map(f => (
                    <button
                      key={f}
                      onClick={() => setFormat(f)}
                      className={cn(
                        'px-3 py-1 text-xs font-medium transition-colors',
                        format === f
                          ? 'bg-primary text-primary-foreground'
                          : 'text-muted-foreground hover:text-foreground'
                      )}
                    >
                      {f.toUpperCase()}
                    </button>
                  ))}
                </div>
                <button onClick={onClose} className="text-muted-foreground hover:text-foreground transition-colors">
                  <X size={16} />
                </button>
              </div>
            </div>

            {/* Quick Add */}
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
              <div className="space-y-1 mb-4 max-h-40 overflow-y-auto scrollbar-thin">
                {fields.map((field, i) => (
                  <div key={i} className="flex items-center justify-between px-3 py-2 bg-secondary border border-border rounded-lg">
                    <span className="text-sm text-foreground">{field.name}</span>
                    <button onClick={() => removeField(i)} className="text-muted-foreground hover:text-red-500 transition-colors ml-2">
                      <Trash2 size={13} />
                    </button>
                  </div>
                ))}
              </div>
            )}

            {/* Custom field */}
            <div className="flex gap-2 mb-5">
              <Input
                placeholder="Add custom field…"
                value={newFieldName}
                onChange={e => setNewFieldName(e.target.value)}
                onKeyDown={e => e.key === 'Enter' && addCustom()}
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
              <Button onClick={() => fields.length && onConfirm(fields, format)} disabled={fields.length === 0} className="flex-1" size="sm">
                Start Extraction
              </Button>
            </div>
          </div>
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  )
}
