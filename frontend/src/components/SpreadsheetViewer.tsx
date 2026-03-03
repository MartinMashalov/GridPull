import { useMemo, useState } from 'react'
import { ChevronUp, ChevronDown, ChevronsUpDown, Download, Search, X, FileSpreadsheet, AlertTriangle } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Badge } from '@/components/ui/badge'
import { cn } from '@/lib/utils'
import { useAuthStore } from '@/store/authStore'

export interface SpreadsheetViewerProps {
  results: Record<string, string>[]
  fields: string[]
  jobId: string
  format: 'xlsx' | 'csv'
  cost?: number
}

type SortDir = 'asc' | 'desc'

function SortIcon({ field, sortField, dir }: { field: string; sortField: string | null; dir: SortDir }) {
  if (sortField !== field) return <ChevronsUpDown size={12} className="text-muted-foreground flex-shrink-0 opacity-50" />
  return dir === 'asc'
    ? <ChevronUp size={12} className="text-primary flex-shrink-0" />
    : <ChevronDown size={12} className="text-primary flex-shrink-0" />
}

export default function SpreadsheetViewer({ results, fields, jobId, format, cost }: SpreadsheetViewerProps) {
  const [sortField, setSortField] = useState<string | null>(null)
  const [sortDir, setSortDir] = useState<SortDir>('asc')
  const [search, setSearch] = useState('')
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
    let rows = results
    if (search.trim()) {
      const q = search.toLowerCase()
      rows = rows.filter((r) => Object.values(r).some((v) => String(v ?? '').toLowerCase().includes(q)))
    }
    if (sortField) {
      const key = sortField === 'Source File' ? '_source_file' : sortField
      rows = [...rows].sort((a, b) => {
        const va = String(a[key] ?? '').toLowerCase()
        const vb = String(b[key] ?? '').toLowerCase()
        const cmp = va.localeCompare(vb, undefined, { numeric: true })
        return sortDir === 'asc' ? cmp : -cmp
      })
    }
    return rows
  }, [results, search, sortField, sortDir])

  const hasErrors = results.some((r) => r['_error'])

  return (
    <div className="mt-6 bg-card border border-border rounded-xl overflow-hidden animate-fade-in">
      {/* Toolbar */}
      <div className="px-5 py-3.5 border-b border-border flex items-center justify-between gap-4 flex-wrap">
        <div className="flex items-center gap-3">
          <div className="w-7 h-7 bg-emerald-500/15 rounded-lg flex items-center justify-center">
            <FileSpreadsheet size={14} className="text-emerald-400" />
          </div>
          <div className="flex items-center gap-2">
            <span className="text-sm font-semibold text-foreground">Extracted Results</span>
            <Badge variant="secondary" className="text-[11px]">{displayRows.length} / {results.length} rows</Badge>
            {cost != null && (
              <Badge variant="blue" className="text-[11px]">${cost.toFixed(6)} cost</Badge>
            )}
          </div>
        </div>

        <div className="flex items-center gap-2">
          <div className="relative">
            <Search size={13} className="absolute left-2.5 top-1/2 -translate-y-1/2 text-muted-foreground" />
            <Input
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder="Search…"
              className="pl-8 pr-7 h-8 text-xs w-40"
            />
            {search && (
              <button onClick={() => setSearch('')} className="absolute right-2 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-foreground">
                <X size={12} />
              </button>
            )}
          </div>
          <Button size="sm" className="h-8 text-xs gap-1.5" onClick={handleDownload}>
            <Download size={12} />
            {format.toUpperCase()}
          </Button>
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
            {displayRows.length === 0 ? (
              <tr>
                <td colSpan={columns.length} className="px-4 py-12 text-center text-muted-foreground">
                  No results match your search.
                </td>
              </tr>
            ) : (
              displayRows.map((row, ri) => {
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
              })
            )}
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
