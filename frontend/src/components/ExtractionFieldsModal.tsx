import { useState, useEffect, useRef } from 'react'
import { trackEvent } from '@/lib/analytics'
import * as Dialog from '@radix-ui/react-dialog'
import { X, Plus, Trash2, Pencil } from 'lucide-react'
import { ExtractionField, ExportFormat, DocumentType } from '@/pages/DashboardPage'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { cn } from '@/lib/utils'

const PRESET_FIELDS = [
  'Date', 'Total Amount', 'Company Name', 'Invoice Number',
  'Revenue', 'Net Income', 'Contract Value', 'Effective Date',
  'Address', 'Signatory', 'Description', 'Tax Amount',
]

const INVOICE_DEFAULTS: ExtractionField[] = [
  { name: 'Invoice Number', description: 'Unique identifier assigned to the invoice, often labeled Invoice #, Invoice No., or Inv #. Return the exact value as shown.' },
  { name: 'Date', description: 'Invoice issue date, labeled Invoice Date or Date. Return in MM/DD/YYYY format when possible.' },
  { name: 'Vendor Name', description: 'Company or vendor issuing the invoice' },
  { name: 'Description', description: 'Brief summary of the goods or services billed. If multiple line items are present, combine them into a short comma-separated summary.' },
  { name: 'Amount', description: 'Total invoice amount including taxes and fees, labeled Total, Invoice Total, or Amount Due. Return the numeric value.' },
  { name: 'Tax Amount', description: 'Tax charged on the invoice, labeled Tax, VAT, GST, or Sales Tax. Return the numeric value, or leave blank if not present.' },
  { name: 'Due Date', description: 'Payment due date, labeled Due Date, Pay By, or Payment Due. Return in MM/DD/YYYY format when possible.' },
]

const SOV_DEFAULTS: ExtractionField[] = [
  { name: 'Loc #', description: `Extract the location identifier exactly as shown for each schedule row (for example: 1, 01, A1). Keep letters, symbols, and leading zeros exactly as printed.` },
  { name: 'Bldg #', description: `Extract the building number for the location exactly as shown in the schedule. Do not infer or renumber buildings; copy the literal value from the row.` },
  { name: 'Location Name', description: `Extract the site or building name used by underwriting (for example: MB1, North Warehouse). Keep abbreviations and naming conventions exactly as shown.` },
  { name: 'Occupancy/Exposure', description: `Extract the occupancy/exposure classification text exactly as presented (for example: 4 Unit Apartment, Retail Strip, Light Manufacturing). Do not summarize or rewrite.` },
  { name: 'Street Address', description: `Extract the street address line for the insured premises. Keep suite/unit/building details when present, but do not include city/state/zip in this field unless the source combines them into one cell.` },
  { name: 'City', description: `Extract the city for the insured location exactly as listed in the schedule row.` },
  { name: 'State', description: `Extract the state value exactly as shown (postal abbreviation preferred when the document uses it). Do not expand or normalize unless already shown that way.` },
  { name: 'Zip', description: `Extract the ZIP/postal code exactly as shown, including ZIP+4 when present.` },
  { name: 'County', description: `Extract the county value exactly as shown (for example: St Tam, Cook, Orange). Do not expand abbreviations unless the schedule already expands them.` },
  { name: 'Construction Type', description: `Extract the construction class/type used in underwriting (for example: Frame, Joisted Masonry, Non-Combustible). Keep the schedule wording as-is.` },
  { name: 'ISO Construction Code', description: `Extract the ISO construction code exactly as shown (for example: F, JM, NC, 1-6). Preserve code formatting and symbols.` },
  { name: 'Building Values', description: `Extract the building limit/value amount for the row. Keep the currency format shown in the source unless the source is plain numeric.` },
  { name: 'Contents/BPP Values', description: `Extract the contents/business personal property value for the row. Use the exact value shown for that coverage bucket.` },
  { name: 'Business Income Values', description: `Extract the business income/time element value exactly as shown for the location row.` },
  { name: 'Machinery & Equipment Values', description: `Extract the machinery and equipment value exactly as shown for the row. Do not merge this into contents unless the source itself combines them.` },
  { name: 'Other Property Values', description: `Extract the other property value exactly as presented for the row.` },
  { name: 'Total Insurable Value (TIV)', description: `Extract the explicit total insurable value shown for the row. Only calculate from component values if the total is truly absent and all needed components are clearly present in the same row.` },
  { name: 'Square Ft.', description: `Extract the insured area in square feet exactly as shown. Keep separators and decimals when present.` },
  { name: 'Cost Per Square Ft.', description: `Extract cost per square foot exactly as shown (for example: $89, 89.25). Keep currency symbol if present in the schedule.` },
  { name: 'Year Built', description: `Extract original year built for the building row. Return the year value shown in the schedule.` },
  { name: 'Roof Update', description: `Extract the roof update year or indicator exactly as shown for the location. Map from the row or column whose label expresses roof age or replacement (for example labels containing roof and year or update).` },
  { name: 'Wiring Update', description: `Extract the wiring update year or indicator exactly as shown for the location.` },
  { name: 'HVAC Update', description: `Extract the HVAC update year or indicator exactly as shown for the location.` },
  { name: 'Plumbing Update', description: `Extract the plumbing update year or indicator exactly as shown for the location.` },
  { name: '% Occupied', description: `Extract occupancy percentage exactly as shown (for example: 100%, 85%). Keep percent signs and formatting.` },
  { name: 'Sprinklered', description: `Extract sprinkler status exactly as shown (for example: Y/N, Yes/No, Partial). Do not reinterpret unless the value is obviously equivalent in the same row.` },
  { name: '% Sprinklered', description: `Extract sprinkler percentage exactly as shown (for example: 0%, 50%, 100%).` },
  { name: 'ISO Protection Class', description: `Extract ISO protection class exactly as shown in the row (for example: 2, 3/9X). Keep slashes, letters, and symbols. If the schedule uses a district or zone label instead of a numeric class, copy that printed text.` },
  { name: 'Fire Alarm', description: `Extract fire alarm indicator exactly as shown (for example: Y/N, Central Station, Local). Map from the alarm system or security alarm row/column when that is how the document labels it.` },
  { name: 'Burglar Alarm', description: `Extract burglar alarm indicator exactly as shown (for example: Y/N, Central Station, Local).` },
  { name: 'Smoke Detectors', description: `Extract smoke detector indicator/status exactly as shown for the row.` },
  { name: '# of Stories', description: `Extract number of stories exactly as shown (for example: 1, 2, 1.5).` },
  { name: '# of Units', description: `Extract number of units exactly as shown in the row.` },
  { name: 'Type of Wiring', description: `Extract type of wiring code or text exactly as shown (for example: C, Copper, Aluminum).` },
  { name: '% Subsidized', description: `Extract subsidized occupancy percentage exactly as shown, including percent sign when present.` },
  { name: '% Student Housing', description: `Extract student housing percentage exactly as shown, including percent sign when present.` },
  { name: '% Elderly Housing', description: `Extract elderly housing percentage exactly as shown, including percent sign when present.` },
  { name: 'Roof Type/Frame', description: `Extract roof type/frame value exactly as shown (for example: Frame, Truss, Metal Deck).` },
  { name: 'Roof Shape', description: `Extract roof shape code/text exactly as shown (for example: H, Gable, Flat).` },
  { name: 'Flood Zone', description: `Extract FEMA flood zone exactly as shown (for example: X, AE, VE, A). Preserve code formatting.` },
  { name: 'EQ Zone', description: `Extract earthquake zone code/classification exactly as shown in the schedule row (for example: 0, 1, 2, A, B, C, X). Copy the literal code from the document and do not translate, interpret, or recode it.` },
  { name: 'Distance to Salt Water/Coast', description: `Extract the distance-to-coast value exactly as shown, including unit/format if present (for example: 60, 60 mi, 2.5 miles).` },
  { name: 'Property Owned or Managed', description: `Extract owned/managed indicator exactly as shown (for example: O, M, Owned, Managed).` },
  { name: 'Bldg Maintenance', description: `Extract building maintenance indicator/class exactly as shown (for example: G, Average, Good).` },
  { name: 'Basement', description: `Extract basement indicator exactly as shown (for example: Y/N, None, Partial, Full).` },
  { name: 'Predominant Exterior Wall / Cladding', description: `Extract predominant exterior wall/cladding material exactly as shown (for example: Wood Siding, Brick Veneer, EIFS).` },
]

const CUSTOM_DEFAULTS: ExtractionField[] = [
  { name: 'Invoice Number', description: '' },
  { name: 'Date', description: '' },
  { name: 'Total Amount', description: '' },
]

function getDefaultFields(dt: DocumentType): ExtractionField[] {
  switch (dt) {
    case 'invoices': return INVOICE_DEFAULTS.map(f => ({ ...f }))
    case 'sov': return SOV_DEFAULTS.map(f => ({ ...f }))
    default: return CUSTOM_DEFAULTS.map(f => ({ ...f }))
  }
}

interface Props {
  open: boolean
  onClose: () => void
  onConfirm: (fields: ExtractionField[], format: ExportFormat, instructions: string) => void
  defaultFormat: ExportFormat
  documentType: DocumentType
}

export default function ExtractionFieldsModal({ open, onClose, onConfirm, defaultFormat, documentType }: Props) {
  const [fields, setFields] = useState<ExtractionField[]>(getDefaultFields(documentType))
  const [newFieldName, setNewFieldName] = useState('')
  const [instructions, setInstructions] = useState('')
  const [expandedDesc, setExpandedDesc] = useState<number | null>(null)
  const fieldsEndRef = useRef<HTMLDivElement>(null)
  const inputRef = useRef<HTMLInputElement>(null)

  useEffect(() => {
    setFields(getDefaultFields(documentType))
  }, [documentType])

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
    onConfirm(fields, defaultFormat, instructions.trim())
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

            <div className="mb-4 rounded-xl border border-border bg-secondary/35 px-3 py-3">
              <label className="block text-[11px] font-semibold uppercase tracking-wide text-muted-foreground mb-2">
                Extraction Instructions
              </label>
              <textarea
                rows={3}
                value={instructions}
                onChange={e => setInstructions(e.target.value)}
                placeholder="Optional guidance for complex documents. Example: 'Extract one row per year from the main financial table and prefer full-year values over quarterly breakdowns.'"
                className="w-full bg-transparent text-sm text-foreground placeholder:text-muted-foreground/60 resize-none outline-none leading-relaxed"
              />
            </div>

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
                          title="Add details to guide the AI for this field"
                          className={cn(
                            'flex items-center gap-1 px-1.5 py-0.5 rounded text-[11px] font-medium transition-colors',
                            expandedDesc === i
                              ? 'text-primary bg-primary/10'
                              : field.description
                                ? 'text-primary/60 hover:text-primary'
                                : 'text-muted-foreground hover:text-primary'
                          )}
                        >
                          <Pencil size={11} />
                          <span>{field.description ? 'Edit' : 'Details'}</span>
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
            <div className="flex items-stretch gap-2 mb-5">
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
                className="text-sm h-10"
              />
              <Button onClick={addCustom} disabled={!newFieldName.trim()} size="icon" variant="outline" className="h-10 w-10 shrink-0">
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
