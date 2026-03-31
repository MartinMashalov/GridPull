import { useMemo, useState } from 'react'
import { ChevronUp, ChevronDown, ChevronsUpDown, Download, FileSpreadsheet, AlertTriangle, Plus, Lock, ArrowRight } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { cn } from '@/lib/utils'
import { useAuthStore } from '@/store/authStore'
import { useNavigate } from 'react-router-dom'
import type { DocumentType } from '@/pages/DashboardPage'

export interface SpreadsheetViewerProps {
  results: Record<string, string>[]
  fields: string[]
  jobId: string
  format: 'xlsx' | 'csv'
  cost?: number
  onNew?: () => void
  paywalled?: boolean
  documentType?: DocumentType
}

type SortDir = 'asc' | 'desc'

function SortIcon({ field, sortField, dir }: { field: string; sortField: string | null; dir: SortDir }) {
  if (sortField !== field) return <ChevronsUpDown size={12} className="text-muted-foreground flex-shrink-0 opacity-50" />
  return dir === 'asc'
    ? <ChevronUp size={12} className="text-primary flex-shrink-0" />
    : <ChevronDown size={12} className="text-primary flex-shrink-0" />
}

export default function SpreadsheetViewer({ results, fields, jobId, format, cost: _cost, onNew, paywalled, documentType }: SpreadsheetViewerProps) {
  const [sortField, setSortField] = useState<string | null>(null)
  const [sortDir, setSortDir] = useState<SortDir>('asc')
  const token = useAuthStore((s) => s.token)
  const navigate = useNavigate()

  const handleDownload = () => {
    const a = document.createElement('a')
    a.href = `/api/documents/download/${jobId}?token=${encodeURIComponent(token ?? '')}`
    a.download = `export.${format}`
    document.body.appendChild(a)
    a.click()
    document.body.removeChild(a)
  }

  const handleAccountingDownload = (fmt: 'qb_csv' | 'qbo' | 'ofx') => {
    const ext = fmt === 'qb_csv' ? 'csv' : fmt
    const label = fmt === 'qb_csv' ? 'quickbooks_online' : fmt === 'qbo' ? 'quickbooks_desktop' : 'xero_import'
    const a = document.createElement('a')
    a.href = `/api/documents/download/${jobId}/accounting?fmt=${fmt}&token=${encodeURIComponent(token ?? '')}`
    a.download = `${label}.${ext}`
    document.body.appendChild(a)
    a.click()
    document.body.removeChild(a)
  }

  const columns = ['Source File', ...fields]

  const toggleSort = (col: string) => {
    if (sortField === col) {
      setSortDir((d) => (d === 'asc' ? 'desc' : 'asc'))
    } else {
      setSortField(col)
      setSortDir('asc')
    }
  }

  const displayRows = useMemo(() => {
    if (!sortField) return results
    const key = sortField === 'Source File' ? '_source_file' : sortField
    return [...results].sort((a, b) => {
      const va = String(a[key] ?? '').toLowerCase()
      const vb = String(b[key] ?? '').toLowerCase()
      const cmp = va.localeCompare(vb, undefined, { numeric: true })
      return sortDir === 'asc' ? cmp : -cmp
    })
  }, [results, sortField, sortDir])

  return (
    <div className="mt-6 bg-card border border-border rounded-xl overflow-hidden animate-fade-in">
      {/* Toolbar */}
      <div className="px-5 py-3.5 border-b border-border flex items-center justify-between gap-4">
        <div className="flex items-center gap-3">
          <div className="w-7 h-7 bg-emerald-500/15 rounded-lg flex items-center justify-center">
            <FileSpreadsheet size={14} className="text-emerald-400" />
          </div>
          <div className="flex items-center gap-2">
            <span className="text-sm font-semibold text-foreground">Extracted Results</span>
          </div>
        </div>

        <div className="flex items-center gap-2">
          <Button
            size="icon"
            variant="outline"
            className="h-8 w-8"
            onClick={paywalled ? () => navigate('/settings') : handleDownload}
            title={paywalled ? 'Upgrade to download' : `Download ${format.toUpperCase()}`}
            disabled={false}
          >
            {paywalled ? <Lock size={14} /> : <Download size={14} />}
          </Button>
          {onNew && (
            <Button size="sm" className="h-8 text-xs gap-1.5" onClick={onNew}>
              <Plus size={13} />
              New
            </Button>
          )}
        </div>
      </div>

      {/* QuickBooks / Xero download buttons */}
      {documentType === 'quickbooks' && !paywalled && (
        <div className="px-5 py-3 border-b border-border bg-secondary/30 flex flex-wrap items-center gap-2">
          <span className="text-xs text-muted-foreground mr-1">Download for:</span>
          <Button size="sm" variant="outline" className="h-7 text-xs gap-1.5" onClick={() => handleAccountingDownload('qb_csv')}>
            <Download size={12} /> QuickBooks Online
          </Button>
          <Button size="sm" variant="outline" className="h-7 text-xs gap-1.5" onClick={() => handleAccountingDownload('qbo')}>
            <Download size={12} /> QuickBooks Desktop
          </Button>
          <Button size="sm" variant="outline" className="h-7 text-xs gap-1.5" onClick={() => handleAccountingDownload('ofx')}>
            <Download size={12} /> Xero
          </Button>
        </div>
      )}

      {/* Table */}
      <div className="relative">
        <div className={cn(
          'overflow-auto max-h-[480px] scrollbar-thin',
          paywalled && 'max-h-[200px] overflow-hidden',
        )}>
          <table className={cn(
            'w-full text-xs border-collapse min-w-max',
            paywalled && 'select-none',
          )}>
            <thead className="sticky top-0 z-10">
              <tr>
                {columns.map((col) => (
                  <th
                    key={col}
                    onClick={() => !paywalled && toggleSort(col)}
                    className="group px-4 py-2.5 text-left font-semibold bg-secondary text-muted-foreground cursor-pointer select-none whitespace-nowrap border-r border-border last:border-r-0 hover:bg-accent hover:text-foreground transition-colors"
                  >
                    <div className="flex items-center gap-1.5">
                      {col}
                      <SortIcon field={col} sortField={sortField} dir={sortDir} />
                    </div>
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {displayRows.map((row, ri) => {
                const hasError = !!row['_error']
                return (
                  <tr
                    key={ri}
                    className={cn(
                      'border-b border-border transition-colors',
                      hasError
                        ? 'bg-red-500/5 hover:bg-red-500/10'
                        : ri % 2 === 0
                        ? 'hover:bg-accent/50'
                        : 'bg-secondary/30 hover:bg-accent/50'
                    )}
                  >
                    {columns.map((col) => {
                      const key = col === 'Source File' ? '_source_file' : col
                      const val = row[key] ?? ''
                      return (
                        <td
                          key={col}
                          className={cn(
                            'px-4 py-2 text-foreground border-r border-border last:border-r-0 max-w-xs',
                            paywalled && ri > 0 && 'blur-sm',
                          )}
                          title={paywalled && ri > 0 ? '' : val}
                        >
                          <div className="truncate max-w-[220px]">
                            {hasError && col === 'Source File' ? (
                              <span className="flex items-center gap-1 text-red-400">
                                <AlertTriangle size={11} />
                                {val}
                              </span>
                            ) : (
                              val || <span className="text-muted-foreground/40 italic">—</span>
                            )}
                          </div>
                        </td>
                      )
                    })}
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>

        {/* Paywall overlay */}
        {paywalled && (
          <div className="absolute inset-x-0 bottom-0 h-full flex items-end">
            <div className="w-full bg-gradient-to-t from-background via-background/95 to-transparent pt-24 pb-6 px-6">
              <div className="text-center max-w-sm mx-auto">
                <div className="w-12 h-12 rounded-full bg-primary/10 flex items-center justify-center mx-auto mb-3">
                  <Lock size={20} className="text-primary" />
                </div>
                <p className="text-base font-semibold mb-1">Upgrade to download your results</p>
                <p className="text-sm text-muted-foreground mb-4">
                  Your extraction is complete! Upgrade to Starter to download your results and get 150 credits/month.
                </p>
                <div className="flex items-center justify-center gap-3">
                  <Button onClick={() => navigate('/settings')} className="gap-1.5">
                    View Plans <ArrowRight size={14} />
                  </Button>
                </div>
                <p className="text-[11px] text-muted-foreground mt-3">
                  Starting at $69/mo
                </p>
              </div>
            </div>
          </div>
        )}
      </div>

      {/* Footer */}
      <div className="px-5 py-2.5 bg-secondary/50 border-t border-border flex items-center justify-between text-[11px] text-muted-foreground">
        <span>{fields.length} field{fields.length !== 1 ? 's' : ''} extracted</span>
        <span>{results.length} row{results.length !== 1 ? 's' : ''} in results</span>
      </div>
    </div>
  )
}
