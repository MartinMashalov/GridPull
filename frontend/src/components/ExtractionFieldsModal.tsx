import { useState } from 'react'
import * as Dialog from '@radix-ui/react-dialog'
import { X, Plus, Trash2 } from 'lucide-react'
import { ExtractionField, ExportFormat } from '@/pages/DashboardPage'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { cn } from '@/lib/utils'

const PRESET_FIELDS = [
  { name: 'Invoice Number', description: 'Invoice or document number' },
  { name: 'Date', description: 'Invoice or document date' },
  { name: 'Total Amount', description: 'Total amount or sum' },
  { name: 'Vendor Name', description: 'Seller or vendor company name' },
  { name: 'Customer Name', description: 'Buyer or customer name' },
  { name: 'Description', description: 'Item or service description' },
  { name: 'Quantity', description: 'Quantity of items' },
  { name: 'Unit Price', description: 'Price per unit' },
  { name: 'Tax Amount', description: 'Tax or VAT amount' },
  { name: 'Due Date', description: 'Payment due date' },
]

interface Props {
  open: boolean
  onClose: () => void
  onConfirm: (fields: ExtractionField[], format: ExportFormat) => void
  defaultFormat: ExportFormat
}

export default function ExtractionFieldsModal({ open, onClose, onConfirm, defaultFormat }: Props) {
  const [fields, setFields] = useState<ExtractionField[]>([
    { name: 'Invoice Number', description: 'Invoice or document number' },
    { name: 'Date', description: 'Invoice or document date' },
    { name: 'Total Amount', description: 'Total amount or sum' },
  ])
  const [format, setFormat] = useState<ExportFormat>(defaultFormat)
  const [newFieldName, setNewFieldName] = useState('')
  const [newFieldDesc, setNewFieldDesc] = useState('')

  const addField = () => {
    if (!newFieldName.trim()) return
    setFields(prev => [...prev, { name: newFieldName.trim(), description: newFieldDesc.trim() }])
    setNewFieldName('')
    setNewFieldDesc('')
  }

  const addPreset = (preset: ExtractionField) => {
    if (!fields.find(f => f.name === preset.name)) {
      setFields(prev => [...prev, preset])
    }
  }

  const removeField = (index: number) => {
    setFields(prev => prev.filter((_, i) => i !== index))
  }

  return (
    <Dialog.Root open={open} onOpenChange={(o) => !o && onClose()}>
      <Dialog.Portal>
        <Dialog.Overlay className="fixed inset-0 bg-black/60 backdrop-blur-sm z-50 animate-fade-in" />
        <Dialog.Content className="fixed left-1/2 top-1/2 -translate-x-1/2 -translate-y-1/2 z-50 bg-card border border-border rounded-2xl shadow-2xl w-full max-w-2xl max-h-[88vh] overflow-y-auto animate-fade-in">
          <div className="p-6">
            {/* Header */}
            <div className="flex items-center justify-between mb-6">
              <div>
                <Dialog.Title className="text-base font-semibold text-foreground">Extraction Fields</Dialog.Title>
                <Dialog.Description className="text-xs text-muted-foreground mt-0.5">
                  Define what data to extract from your PDFs
                </Dialog.Description>
              </div>
              <button onClick={onClose} className="text-muted-foreground hover:text-foreground transition-colors p-1 rounded-md hover:bg-secondary">
                <X size={18} />
              </button>
            </div>

            {/* Format */}
            <div className="mb-5">
              <p className="text-xs font-medium text-muted-foreground mb-2 uppercase tracking-wider">Export Format</p>
              <div className="flex gap-2">
                {(['xlsx', 'csv'] as ExportFormat[]).map(f => (
                  <button
                    key={f}
                    onClick={() => setFormat(f)}
                    className={cn(
                      'flex-1 py-2 rounded-lg text-sm font-medium border transition-colors',
                      format === f
                        ? 'bg-primary text-primary-foreground border-primary'
                        : 'bg-secondary text-muted-foreground border-border hover:border-primary/40 hover:text-foreground'
                    )}
                  >
                    {f === 'xlsx' ? 'Excel (.xlsx)' : 'CSV (.csv)'}
                  </button>
                ))}
              </div>
            </div>

            {/* Quick Add */}
            <div className="mb-5">
              <p className="text-xs font-medium text-muted-foreground mb-2 uppercase tracking-wider">Quick Add</p>
              <div className="flex flex-wrap gap-1.5">
                {PRESET_FIELDS.map(preset => {
                  const added = !!fields.find(f => f.name === preset.name)
                  return (
                    <button
                      key={preset.name}
                      onClick={() => addPreset(preset)}
                      disabled={added}
                      className={cn(
                        'px-2.5 py-1 rounded-full text-[11px] font-medium border transition-colors',
                        added
                          ? 'bg-primary/15 text-primary border-primary/30 cursor-default'
                          : 'bg-secondary text-muted-foreground border-border hover:border-primary/40 hover:text-foreground'
                      )}
                    >
                      {added ? '✓ ' : '+ '}{preset.name}
                    </button>
                  )
                })}
              </div>
            </div>

            {/* Selected fields */}
            <div className="mb-5">
              <p className="text-xs font-medium text-muted-foreground mb-2 uppercase tracking-wider">
                Selected Fields ({fields.length})
              </p>
              {fields.length === 0 ? (
                <div className="text-center py-8 text-muted-foreground text-sm border border-dashed border-border rounded-xl">
                  No fields selected. Add fields above.
                </div>
              ) : (
                <div className="space-y-1.5 max-h-44 overflow-y-auto pr-1 scrollbar-thin">
                  {fields.map((field, i) => (
                    <div key={i} className="flex items-center gap-3 p-2.5 bg-secondary border border-border rounded-lg">
                      <div className="flex-1 min-w-0">
                        <p className="text-sm font-medium text-foreground">{field.name}</p>
                        {field.description && (
                          <p className="text-[11px] text-muted-foreground truncate">{field.description}</p>
                        )}
                      </div>
                      <button onClick={() => removeField(i)} className="text-muted-foreground hover:text-red-400 transition-colors flex-shrink-0">
                        <Trash2 size={13} />
                      </button>
                    </div>
                  ))}
                </div>
              )}
            </div>

            {/* Custom field */}
            <div className="mb-6 p-4 bg-secondary border border-border rounded-xl">
              <p className="text-xs font-medium text-muted-foreground mb-2 uppercase tracking-wider">Custom Field</p>
              <div className="flex gap-2">
                <Input
                  placeholder="Field name (e.g. Contract ID)"
                  value={newFieldName}
                  onChange={e => setNewFieldName(e.target.value)}
                  onKeyDown={e => e.key === 'Enter' && addField()}
                />
                <Input
                  placeholder="Description (optional)"
                  value={newFieldDesc}
                  onChange={e => setNewFieldDesc(e.target.value)}
                  onKeyDown={e => e.key === 'Enter' && addField()}
                />
                <Button onClick={addField} disabled={!newFieldName.trim()} size="icon" variant="outline">
                  <Plus size={15} />
                </Button>
              </div>
            </div>

            {/* Actions */}
            <div className="flex gap-3">
              <Button onClick={onClose} variant="outline" className="flex-1">
                Cancel
              </Button>
              <Button onClick={() => fields.length && onConfirm(fields, format)} disabled={fields.length === 0} className="flex-1">
                Start Extraction
              </Button>
            </div>
          </div>
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  )
}
