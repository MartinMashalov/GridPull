import { useState, useEffect, useRef } from 'react'
import { trackEvent } from '@/lib/analytics'
import * as Dialog from '@radix-ui/react-dialog'
import { X, Plus, Trash2, Pencil } from 'lucide-react'
import { ExtractionField, ExportFormat, DocumentType } from '@/pages/DashboardPage'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Checkbox } from '@/components/ui/checkbox'
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
  { name: 'Location Number', description: 'Extract the schedule location identifier exactly as shown in the SOV, including letters, dashes, and leading zeros. This is usually labeled as Location, Loc #, or Location Number and should uniquely identify one site. Example: if the table shows "Loc 0012", return "0012" when the prefix is clearly separate, otherwise return "Loc 0012". One-shot answer: if the row says "Location: 105A", return "105A".' },
  { name: 'Address Line 1', description: 'Extract the primary street address for the insured location and keep suite, unit, or building numbers when present. Do not include city, state, or ZIP in this field unless the document combines everything on one line and cannot be separated. Example: "1450 W Commerce St, Suite 300" should return exactly "1450 W Commerce St, Suite 300". One-shot answer: if the row shows "901 Market Ave Bldg 2", return "901 Market Ave Bldg 2".' },
  { name: 'City', description: 'Extract only the city name tied to the location address. Remove commas and avoid including state abbreviations or ZIP codes in this field. Example: from "Dallas, TX 75201", return "Dallas". One-shot answer: if the source line is "City: San Antonio", return "San Antonio".' },
  { name: 'State', description: 'Extract the state or province code associated with the location, preferring the postal abbreviation when available. If the source uses full state names, keep the full name unless another column already contains the abbreviation. Example: from "CA 94105", return "CA", and from "California" return "California" when no abbreviation is shown. One-shot answer: if the row says "State: NY", return "NY".' },
  { name: 'ZIP Code', description: 'Extract the postal code for the location exactly as displayed, including ZIP+4 formats when present. Do not include city or state text in this value. Example: "75201-4412" should remain "75201-4412" and not be shortened unless the source only shows five digits. One-shot answer: if the address line ends with "Chicago, IL 60611", return "60611".' },
  { name: 'Construction Class', description: 'Extract the insurance construction classification used for underwriting, not a generic building description. Normalize obvious variants only when safe, such as mapping "Joist Masonry" to "Joisted Masonry". Example values include Frame, Joisted Masonry, Non-Combustible, Masonry Non-Combustible, and Fire Resistive. One-shot answer: if the schedule says "Constr: NC", return "Non-Combustible" only if the form legend defines NC that way, otherwise return "NC".' },
  { name: 'Occupancy', description: 'Extract the primary occupancy or use type for the location in underwriting language. Keep concise labels like Office, Retail, Warehouse, Manufacturing, Habitational, or Mixed Use. Example: "Light Manufacturing - Plastics" should return "Light Manufacturing" unless the subtype is the only text provided. One-shot answer: if the row says "Occupancy: Retail Store", return "Retail Store".' },
  { name: 'Year Built', description: 'Extract the original year of construction for the building and return only the year value. Do not convert to age or include renovation year unless the schedule explicitly labels it as Year Built. Example: from "Year Built: 1987", return "1987". One-shot answer: if you see "Built 2004 / Renovated 2019", return "2004".' },
  { name: 'Number of Stories', description: 'Extract the count of above-grade stories for the building as shown in the SOV. Return a numeric value and keep half-story notation only when explicitly shown (for example 1.5). Example: "Stories: 3" should return "3". One-shot answer: if the source says "2 Story Masonry", return "2".' },
  { name: 'Total Area (Sq Ft)', description: 'Extract total building area in square feet for the insured location. Remove commas only if needed by downstream numeric parsing, but do not change the magnitude. Example: "45,250 SF" should return "45250" or "45,250" consistently with your sheet style. One-shot answer: if the row says "Area: 12,800 sq ft", return "12800".' },
  { name: 'Sprinklered', description: 'Extract fire sprinkler protection status for the site using clear categories. Preferred outputs are Yes, No, Partial, or Unknown unless the schedule provides a more specific phrase that matters for underwriting. Example: "100% Sprinklered" should map to "Yes", while "Partial Wet System" should map to "Partial". One-shot answer: if the source says "No sprinklers", return "No".' },
  { name: 'Protection Class', description: 'Extract the fire protection class or district designation for the location. Accept any of these label formats: Protection Class, PC, PPC, ISO Class, ISO PPC, Fire District, Fire Protection Class, Prot Class, Prot. Class, Fire Class. The value is often a short number like "3", "5", "10", or a split like "5/9", "3/9X", or a district label like "District 6". It may appear as a standalone column with numeric values and no label on each row — if a column header matches any of these labels, extract the value from that column for each row. If the document states a single protection class or PPC that applies to all locations (e.g. "Protection Class: 5" in a header or notes section), use that value for every row. Leave blank only if genuinely absent from both the row data and the document-level notes. Example: column "PPC" with value "3" → "3"; header says "All locations: Protection Class 5/9" → "5/9".' },
  { name: 'Building Value', description: 'Extract the insured building amount for the location, typically replacement cost, from the property values section. Return only the monetary figure without commentary and avoid mixing it with contents or business income amounts. Example: "$2,500,000 Building" should return "2500000" or "$2,500,000" based on your number format convention. One-shot answer: if the row shows "Building: 1,200,000", return "1200000".' },
  { name: 'Contents / BPP Value', description: 'Extract the insured contents or business personal property amount for that location. Treat BPP, Contents, and Personal Property as the same bucket unless the schedule clearly separates them into different columns. Example: "Contents/BPP $475,000" should return "475000". One-shot answer: if the source says "BPP Limit: $90,000", return "90000".' },
  { name: 'Business Income Value', description: 'Extract the business income or time-element insured amount for the location when provided. Do not infer this value from totals unless the schedule explicitly provides a formula and all components are present. Example: "Business Income: $300,000" should return "300000". One-shot answer: if the row says "Time Element 150,000", return "150000".' },
  { name: 'Total Insured Value', description: 'Extract the total insured value for the location from the explicit total column when available. If a total is not explicitly listed, compute only when building, contents/BPP, and business income values are all clearly present and additive in the same row. Example: Building 2,000,000 plus BPP 500,000 plus BI 250,000 should return "2750000". One-shot answer: if the schedule shows "TIV: $3,400,000", return "3400000".' },
  { name: 'Valuation Method', description: 'Extract the valuation basis for each location. First look for a per-row or per-location column with a label such as "Valuation", "Val", "Basis", "Val Method", "Val Basis", "RCV", "ACV", "RC", "Coinsurance", or similar and return that cell value. If no per-row value exists, scan the entire document — including headers, footers, methodology sections, schedule notes, and page 1 — for a document-wide valuation statement that applies to all locations; common phrases include "replacement cost", "replacement cost new", "RCN", "RCV", "actual cash value", "ACV", "agreed value". If found document-wide, use that value for every row. Normalize only obvious abbreviations: "replacement cost" or "replacement cost value" → "RCV"; "replacement cost new" or "RCN" → "RCN"; "actual cash value" → "ACV". Do NOT leave blank if a valuation basis is stated anywhere in the document. Example: per-row column "Valuation: RCV" → "RCV"; document header "All values expressed as Replacement Cost New (RCN)" → "RCN"; schedule note "Coinsurance: 100% RC" → "RCV".' },
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

  const updateFormat = (index: number, fmt: string) => {
    setFields(prev => prev.map((f, i) => i === index ? { ...f, format: fmt } : f))
  }

  const updateNumeric = (index: number, numeric: boolean) => {
    setFields(prev => prev.map((f, i) => i === index ? { ...f, numeric } : f))
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
                      <div className="px-3 py-2.5 bg-primary/5 border-t border-border space-y-2">
                        <textarea
                          autoFocus
                          rows={2}
                          value={field.description}
                          onChange={e => updateDescription(i, e.target.value)}
                          placeholder="Describe what to look for, or how to calculate (e.g. 'Net Income ÷ Revenue × 100')…"
                          className="w-full text-xs bg-transparent resize-none outline-none text-foreground placeholder:text-muted-foreground/60 leading-relaxed"
                        />
                        <div className="flex items-center gap-2 pt-0.5">
                          <Input
                            value={field.format || ''}
                            onChange={e => updateFormat(i, e.target.value)}
                            placeholder="Format (e.g. MM/DD/YYYY)"
                            className="text-xs h-7 flex-1"
                          />
                          <label className="flex items-center gap-1.5 cursor-pointer select-none shrink-0">
                            <Checkbox
                              checked={!!field.numeric}
                              onCheckedChange={(checked) => updateNumeric(i, !!checked)}
                            />
                            <span className="text-xs text-muted-foreground">Numeric</span>
                          </label>
                        </div>
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
