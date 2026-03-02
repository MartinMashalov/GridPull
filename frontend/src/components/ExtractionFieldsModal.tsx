import { useState } from 'react'
import * as Dialog from '@radix-ui/react-dialog'
import { X, Plus, Trash2, Info } from 'lucide-react'
import { ExtractionField, ExportFormat } from '@/pages/DashboardPage'

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

  const handleConfirm = () => {
    if (fields.length === 0) return
    onConfirm(fields, format)
  }

  return (
    <Dialog.Root open={open} onOpenChange={(o) => !o && onClose()}>
      <Dialog.Portal>
        <Dialog.Overlay className="fixed inset-0 bg-black/40 backdrop-blur-sm z-50 animate-fade-in" />
        <Dialog.Content className="fixed left-1/2 top-1/2 -translate-x-1/2 -translate-y-1/2 z-50 bg-white rounded-2xl shadow-2xl w-full max-w-2xl max-h-[90vh] overflow-y-auto animate-fade-in border border-blue-100">
          <div className="p-6">
            {/* Header */}
            <div className="flex items-center justify-between mb-6">
              <div>
                <Dialog.Title className="text-xl font-bold text-slate-900">Extraction Fields</Dialog.Title>
                <Dialog.Description className="text-sm text-slate-500 mt-1">
                  Define what data to extract from your PDFs
                </Dialog.Description>
              </div>
              <button onClick={onClose} className="text-slate-400 hover:text-slate-600 transition-colors">
                <X size={20} />
              </button>
            </div>

            {/* Export Format */}
            <div className="mb-6">
              <label className="text-sm font-medium text-slate-700 mb-2 block">Export Format</label>
              <div className="flex gap-3">
                {(['xlsx', 'csv'] as ExportFormat[]).map(f => (
                  <button
                    key={f}
                    onClick={() => setFormat(f)}
                    className={`flex-1 py-2.5 rounded-lg text-sm font-medium border transition-colors ${
                      format === f
                        ? 'bg-blue-600 text-white border-blue-600'
                        : 'bg-white text-slate-600 border-blue-200 hover:border-blue-400 hover:bg-blue-50'
                    }`}
                  >
                    {f === 'xlsx' ? 'Excel (.xlsx)' : 'CSV (.csv)'}
                  </button>
                ))}
              </div>
            </div>

            {/* Preset fields */}
            <div className="mb-6">
              <div className="flex items-center gap-1.5 mb-3">
                <label className="text-sm font-medium text-slate-700">Quick Add</label>
                <Info size={13} className="text-slate-400" />
              </div>
              <div className="flex flex-wrap gap-2">
                {PRESET_FIELDS.map(preset => {
                  const added = !!fields.find(f => f.name === preset.name)
                  return (
                    <button
                      key={preset.name}
                      onClick={() => addPreset(preset)}
                      disabled={added}
                      className={`px-3 py-1.5 rounded-full text-xs font-medium border transition-colors ${
                        added
                          ? 'bg-blue-50 text-blue-600 border-blue-200 cursor-default'
                          : 'bg-[#EFF6FF] text-slate-600 border-blue-100 hover:border-blue-400 hover:bg-blue-50 hover:text-blue-700'
                      }`}
                    >
                      {added ? '✓ ' : '+ '}{preset.name}
                    </button>
                  )
                })}
              </div>
            </div>

            {/* Selected fields */}
            <div className="mb-6">
              <label className="text-sm font-medium text-slate-700 mb-3 block">
                Selected Fields ({fields.length})
              </label>
              {fields.length === 0 ? (
                <div className="text-center py-8 text-slate-400 text-sm border-2 border-dashed border-blue-200 rounded-xl bg-blue-50/50">
                  No fields selected. Add fields above or use quick add.
                </div>
              ) : (
                <div className="space-y-2 max-h-48 overflow-y-auto pr-1">
                  {fields.map((field, i) => (
                    <div key={i} className="flex items-center gap-3 p-3 bg-blue-50 border border-blue-100 rounded-lg">
                      <div className="flex-1 min-w-0">
                        <p className="text-sm font-medium text-slate-800">{field.name}</p>
                        {field.description && (
                          <p className="text-xs text-slate-400 truncate">{field.description}</p>
                        )}
                      </div>
                      <button
                        onClick={() => removeField(i)}
                        className="text-slate-300 hover:text-red-500 transition-colors flex-shrink-0"
                      >
                        <Trash2 size={14} />
                      </button>
                    </div>
                  ))}
                </div>
              )}
            </div>

            {/* Custom field */}
            <div className="mb-6 p-4 bg-blue-50 border border-blue-100 rounded-xl">
              <label className="text-sm font-medium text-slate-700 mb-3 block">Add Custom Field</label>
              <div className="flex gap-2">
                <input
                  type="text"
                  placeholder="Field name (e.g. Contract ID)"
                  value={newFieldName}
                  onChange={e => setNewFieldName(e.target.value)}
                  onKeyDown={e => e.key === 'Enter' && addField()}
                  className="flex-1 px-3 py-2 text-sm border border-blue-200 rounded-lg focus:outline-none focus:border-blue-400 bg-white"
                />
                <input
                  type="text"
                  placeholder="Description (optional)"
                  value={newFieldDesc}
                  onChange={e => setNewFieldDesc(e.target.value)}
                  onKeyDown={e => e.key === 'Enter' && addField()}
                  className="flex-1 px-3 py-2 text-sm border border-blue-200 rounded-lg focus:outline-none focus:border-blue-400 bg-white"
                />
                <button
                  onClick={addField}
                  disabled={!newFieldName.trim()}
                  className="px-3 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 disabled:opacity-50 transition-colors"
                >
                  <Plus size={16} />
                </button>
              </div>
            </div>

            {/* Actions */}
            <div className="flex gap-3">
              <button
                onClick={onClose}
                className="flex-1 py-3 text-sm font-medium text-slate-600 border border-blue-200 rounded-xl hover:bg-blue-50 transition-colors"
              >
                Cancel
              </button>
              <button
                onClick={handleConfirm}
                disabled={fields.length === 0}
                className="flex-1 py-3 text-sm font-medium text-white bg-blue-600 rounded-xl hover:bg-blue-700 disabled:opacity-50 transition-colors"
              >
                Start Extraction
              </button>
            </div>
          </div>
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  )
}
