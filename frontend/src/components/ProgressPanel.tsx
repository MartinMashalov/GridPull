import { Download, CheckCircle2, XCircle, Loader2, FileText, Cpu, Table2 } from 'lucide-react'
import { JobState as JobProgress, ExportFormat } from '@/pages/DashboardPage'

interface Props {
  job: JobProgress
  format: ExportFormat
}

const steps = [
  { key: 'processing', label: 'Uploading & reading PDFs', icon: FileText },
  { key: 'extracting', label: 'AI extracting data', icon: Cpu },
  { key: 'generating', label: 'Generating spreadsheet', icon: Table2 },
  { key: 'complete', label: 'Ready to download', icon: CheckCircle2 },
]

function getStepStatus(stepKey: string, currentStatus: string): 'done' | 'active' | 'pending' | 'error' {
  const order = ['queued', 'processing', 'extracting', 'generating', 'complete']
  const stepIdx = steps.findIndex(s => s.key === stepKey)
  const currentIdx = order.indexOf(currentStatus)

  if (currentStatus === 'error') {
    // Mark all after current as error
    if (stepIdx <= currentIdx - 1) return 'done'
    if (stepIdx === currentIdx) return 'error'
    return 'pending'
  }

  const orderMap: Record<string, number> = { processing: 1, extracting: 2, generating: 3, complete: 4 }
  const stepOrder = orderMap[stepKey] || 0
  const curOrder = orderMap[currentStatus] || 0

  if (curOrder > stepOrder) return 'done'
  if (curOrder === stepOrder) return 'active'
  return 'pending'
}

export default function ProgressPanel({ job, format }: Props) {
  const isError = job.status === 'error'
  const isComplete = job.status === 'complete'

  return (
    <div className="mt-6 bg-white rounded-2xl border border-gray-200 overflow-hidden animate-fade-in">
      <div className="px-6 py-4 border-b border-gray-100">
        <div className="flex items-center justify-between mb-3">
          <span className="text-sm font-semibold text-gray-800">
            {isError ? 'Extraction Failed' : isComplete ? 'Extraction Complete!' : 'Processing...'}
          </span>
          <span className="text-sm font-medium text-indigo-600">{job.progress}%</span>
        </div>
        <div className="w-full h-2 bg-gray-100 rounded-full overflow-hidden">
          <div
            className={`h-full rounded-full transition-all duration-500 ${
              isError ? 'bg-red-500' : isComplete ? 'bg-emerald-500' : 'bg-indigo-500'
            }`}
            style={{ width: `${job.progress}%` }}
          />
        </div>
      </div>

      <div className="px-6 py-4">
        <div className="space-y-3">
          {steps.map((step) => {
            const status = getStepStatus(step.key, job.status)
            return (
              <div key={step.key} className="flex items-center gap-3">
                <div className={`w-7 h-7 rounded-full flex items-center justify-center flex-shrink-0 ${
                  status === 'done' ? 'bg-emerald-100 text-emerald-600' :
                  status === 'active' ? 'bg-indigo-100 text-indigo-600' :
                  status === 'error' ? 'bg-red-100 text-red-600' :
                  'bg-gray-100 text-gray-400'
                }`}>
                  {status === 'active' ? (
                    <Loader2 size={14} className="animate-spin" />
                  ) : status === 'done' ? (
                    <CheckCircle2 size={14} />
                  ) : status === 'error' ? (
                    <XCircle size={14} />
                  ) : (
                    <step.icon size={14} />
                  )}
                </div>
                <span className={`text-sm ${
                  status === 'done' ? 'text-gray-600' :
                  status === 'active' ? 'text-gray-900 font-medium' :
                  status === 'error' ? 'text-red-600' :
                  'text-gray-400'
                }`}>
                  {step.label}
                </span>
              </div>
            )
          })}
        </div>

        {isError && job.error && (
          <div className="mt-4 p-3 bg-red-50 rounded-lg text-sm text-red-600 border border-red-100">
            {job.error}
          </div>
        )}

        {isComplete && job.downloadUrl && (
          <a
            href={job.downloadUrl}
            download={`gridpull_export.${format}`}
            className="mt-4 flex items-center justify-center gap-2 w-full py-2.5 bg-emerald-600 hover:bg-emerald-700 text-white rounded-xl text-sm font-medium transition-colors"
          >
            <Download size={15} />
            Download {format.toUpperCase()} Again
          </a>
        )}

        {job.message && !isError && (
          <p className="mt-3 text-xs text-gray-400 text-center">{job.message}</p>
        )}
      </div>
    </div>
  )
}
