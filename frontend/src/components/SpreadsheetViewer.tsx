import { useMemo, useState } from 'react'
import {
  ChevronUp,
  ChevronDown,
  ChevronsUpDown,
  Download,
  Search,
  X,
  FileSpreadsheet,
  AlertTriangle,
} from 'lucide-react'

export interface SpreadsheetViewerProps {
  results: Record<string, string>[]
  fields: string[]
  jobId: string
  format: 'xlsx' | 'csv'
  creditsUsed?: number
}

type SortDir = 'asc' | 'desc'

function SortIcon({ field, sortField, dir }: { field: string; sortField: string | null; dir: SortDir }) {
  if (sortField !== field) return <ChevronsUpDown size={13} className="text-blue-300 flex-shrink-0" />
  return dir === 'asc'
    ? <ChevronUp size={13} className="text-white flex-shrink-0" />
    : <ChevronDown size={13} className="text-white flex-shrink-0" />
}

export default function SpreadsheetViewer({
  results,
  fields,
  jobId,
  format,
  creditsUsed,
}: SpreadsheetViewerProps) {
  const [sortField, setSortField] = useState<string | null>(null)
  const [sortDir, setSortDir] = useState<SortDir>('asc')
  const [search, setSearch] = useState('')

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
      rows = rows.filter((r) =>
        Object.values(r).some((v) => String(v ?? '').toLowerCase().includes(q))
      )
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
    <div className="mt-8 bg-white rounded-2xl border border-blue-100 overflow-hidden shadow-sm animate-fade-in">
      {/* Toolbar */}
      <div className="px-5 py-4 border-b border-blue-50 flex items-center justify-between gap-4 flex-wrap">
        <div className="flex items-center gap-3">
          <div className="w-8 h-8 bg-emerald-100 rounded-lg flex items-center justify-center">
            <FileSpreadsheet size={16} className="text-emerald-600" />
          </div>
          <div>
            <span className="text-sm font-semibold text-slate-900">
              Extracted Results
            </span>
            <span className="ml-2 text-xs text-slate-400 bg-blue-50 px-2 py-0.5 rounded-full">
              {displayRows.length} / {results.length} rows
            </span>
            {creditsUsed != null && (
              <span className="ml-1.5 text-xs text-blue-500 bg-blue-50 px-2 py-0.5 rounded-full">
                {creditsUsed} credits used
              </span>
            )}
          </div>
        </div>

        <div className="flex items-center gap-3">
          {/* Search */}
          <div className="relative">
            <Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-400" />
            <input
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder="Search results…"
              className="pl-8 pr-8 py-1.5 text-sm border border-blue-200 rounded-lg focus:outline-none focus:border-blue-400 w-48 bg-white"
            />
            {search && (
              <button
                onClick={() => setSearch('')}
                className="absolute right-2 top-1/2 -translate-y-1/2 text-slate-300 hover:text-slate-500"
              >
                <X size={13} />
              </button>
            )}
          </div>

          {/* Download */}
          <a
            href={`/api/documents/download/${jobId}`}
            download={`gridpull_export.${format}`}
            className="flex items-center gap-1.5 px-3 py-1.5 bg-blue-600 hover:bg-blue-700 text-white text-sm font-medium rounded-lg transition-colors"
          >
            <Download size={13} />
            {format.toUpperCase()}
          </a>
        </div>
      </div>

      {/* Error notice */}
      {hasErrors && (
        <div className="mx-5 mt-3 p-3 bg-amber-50 border border-amber-200 rounded-lg flex items-center gap-2 text-sm text-amber-700">
          <AlertTriangle size={14} className="flex-shrink-0" />
          Some rows had extraction errors (shown in the table).
        </div>
      )}

      {/* Table */}
      <div className="overflow-auto max-h-[520px] scrollbar-thin">
        <table className="w-full text-sm border-collapse min-w-max">
          <thead className="sticky top-0 z-10">
            <tr>
              {columns.map((col) => (
                <th
                  key={col}
                  onClick={() => toggleSort(col)}
                  className="group px-4 py-3 text-left text-xs font-semibold bg-blue-600 text-white cursor-pointer select-none whitespace-nowrap border-r border-blue-500/40 last:border-r-0 hover:bg-blue-700 transition-colors"
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
                <td colSpan={columns.length} className="px-4 py-12 text-center text-slate-400 text-sm">
                  No results match your search.
                </td>
              </tr>
            ) : (
              displayRows.map((row, ri) => {
                const hasError = !!row['_error']
                return (
                  <tr
                    key={ri}
                    className={`border-b border-blue-50 transition-colors ${
                      hasError
                        ? 'bg-red-50 hover:bg-red-100'
                        : ri % 2 === 0
                        ? 'bg-white hover:bg-blue-50/40'
                        : 'bg-[#EFF6FF] hover:bg-blue-50/60'
                    }`}
                  >
                    {columns.map((col) => {
                      const key = col === 'Source File' ? '_source_file' : col
                      const val = row[key] ?? ''
                      return (
                        <td
                          key={col}
                          className="px-4 py-2.5 text-slate-700 border-r border-blue-50 last:border-r-0 max-w-xs"
                          title={val}
                        >
                          <div className="truncate max-w-[240px]">
                            {hasError && col === 'Source File' ? (
                              <span className="flex items-center gap-1 text-red-600">
                                <AlertTriangle size={12} />
                                {val}
                              </span>
                            ) : (
                              val || <span className="text-slate-300 italic text-xs">—</span>
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
      <div className="px-5 py-3 bg-blue-50 border-t border-blue-100 flex items-center justify-between text-xs text-slate-400">
        <span>{fields.length} field{fields.length !== 1 ? 's' : ''} extracted</span>
        <span>{results.length} document{results.length !== 1 ? 's' : ''} processed</span>
      </div>
    </div>
  )
}
