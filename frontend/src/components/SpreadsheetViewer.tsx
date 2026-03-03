import { useMemo, useState } from 'react'
import { ChevronUp, ChevronDown, ChevronsUpDown, Download, FileSpreadsheet, AlertTriangle, Plus } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { cn } from '@/lib/utils'
import { useAuthStore } from '@/store/authStore'

export interface SpreadsheetViewerProps {
  results: Record<string, string>[]
  fields: string[]
  jobId: string
  format: 'xlsx' | 'csv'
  cost?: number
  onNew?: () => void
}

type SortDir = 'asc' | 'desc'

function SortIcon({ field, sortField, dir }: { field: string; sortField: string | null; dir: SortDir }) {
  if (sortField !== field) return <ChevronsUpDown size={12} className="text-muted-foreground flex-shrink-0 opacity-50" />
  return dir === 'asc'
    ? <ChevronUp size={12} className="text-primary flex-shrink-0" />
    : <ChevronDown size={12} className="text-primary flex-shrink-0" />
}

export default function SpreadsheetViewer({ results, fields, jobId, format, cost, onNew }: SpreadsheetViewerProps) {
  const [sortField, setSortField] = useState<string | null>(null)
  const [sortDir, setSortDir] = useState<SortDir>('asc')
  const token = useAuthStore((s) => s.token)

  const handleDownload = () => {
    const t = token ?? ''
    fetch(`/api/documents/download/${jobId}`, { headers: { Authorization: `Bearer ${t}` } })
      .then((r) => r.blob())
      .then((blob) => {
        const url = URL.createObjectURL(blob)
        const a = document.createElement('a')
        a.href = url
        a.download = `export.${format}`
        a.click()
        URL.revokeObjectURL(url)
      })
      .catch(() => {})
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

  const hasErrors = results.some((r) => r['_error'])

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
            {cost != null && (
              <Badge variant="blue" className="text-[11px]">${cost.toFixed(6)} cost</Badge>
            )}
          </div>
        </div>

        <div className="flex items-center gap-2">
          <Button
            size="icon"
            variant="outline"
            className="h-8 w-8"
            onClick={handleDownload}
            title={`Download ${format.toUpperCase()}`}
          >
            <Download size={14} />
          </Button>
          {onNew && (
            <Button size="sm" className="h-8 text-xs gap-1.5" onClick={onNew}>
              <Plus size={13} />
              New
            </Button>
          )}
        </div>
      </div>

      {/* Error notice */}
      {hasErrors && (
        <div className="mx-4 mt-3 p-2.5 bg-amber-500/10 border border-amber-500/20 rounded-lg flex items-center gap-2 text-xs text-amber-400">
          <AlertTriangle size={13} className="flex-shrink-0" />
          Some rows had extraction errors.
        </div>
      )}

      {/* Table */}
      <div className="overflow-auto max-h-[480px] scrollbar-thin">
        <table className="w-full text-xs border-collapse min-w-max">
          <thead className="sticky top-0 z-10">
            <tr>
              {columns.map((col) => (
                <th
                  key={col}
                  onClick={() => toggleSort(col)}
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
                        className="px-4 py-2 text-foreground border-r border-border last:border-r-0 max-w-xs"
                        title={val}
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

      {/* Footer */}
      <div className="px-5 py-2.5 bg-secondary/50 border-t border-border flex items-center justify-between text-[11px] text-muted-foreground">
        <span>{fields.length} field{fields.length !== 1 ? 's' : ''} extracted</span>
        <span>{results.length} document{results.length !== 1 ? 's' : ''} processed</span>
      </div>
    </div>
  )
}
