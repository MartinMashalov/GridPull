import { useState, useEffect, useRef } from 'react'
import { useParams } from 'react-router-dom'
import { Camera, Upload, Check, AlertCircle, Loader2, FileSpreadsheet } from 'lucide-react'
import api from '@/lib/api'

type Status = 'validating' | 'ready' | 'uploading' | 'success' | 'expired' | 'error'

export default function MobileUploadPage() {
  const { token } = useParams<{ token: string }>()
  const [status, setStatus] = useState<Status>('validating')
  const [uploadCount, setUploadCount] = useState(0)
  const [errorMsg, setErrorMsg] = useState('')
  const fileRef = useRef<HTMLInputElement>(null)

  useEffect(() => {
    if (!token) { setStatus('error'); setErrorMsg('No token provided'); return }
    api.get(`/ingest/mobile-session/${token}`)
      .then(() => setStatus('ready'))
      .catch(err => {
        if (err.response?.status === 410) {
          setStatus('expired')
        } else {
          setStatus('error')
          setErrorMsg('Invalid or expired link')
        }
      })
  }, [token])

  const handleFile = async (file: File) => {
    if (!token) return
    setStatus('uploading')
    const fd = new FormData()
    fd.append('file', file)
    try {
      await api.post(`/ingest/mobile-upload/${token}`, fd)
      setUploadCount(c => c + 1)
      setStatus('success')
      setTimeout(() => setStatus('ready'), 2000)
    } catch (err: any) {
      setStatus('error')
      setErrorMsg(err.response?.data?.detail || 'Upload failed')
      setTimeout(() => setStatus('ready'), 3000)
    }
  }

  const handleChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0]
    if (file) handleFile(file)
    e.target.value = ''
  }

  if (status === 'validating') {
    return (
      <div className="min-h-[100dvh] flex items-center justify-center bg-gradient-to-b from-blue-50 to-white">
        <Loader2 size={28} className="animate-spin text-blue-500" />
      </div>
    )
  }

  if (status === 'expired') {
    return (
      <div className="min-h-[100dvh] flex items-center justify-center bg-gradient-to-b from-blue-50 to-white p-6">
        <div className="text-center">
          <AlertCircle size={40} className="mx-auto text-amber-500 mb-3" />
          <h1 className="text-lg font-semibold mb-1">Link Expired</h1>
          <p className="text-sm text-gray-500">Generate a new QR code from the GridPull dashboard.</p>
        </div>
      </div>
    )
  }

  return (
    <div className="min-h-[100dvh] flex flex-col bg-gradient-to-b from-blue-50 to-white">
      {/* Header */}
      <div className="flex items-center justify-center gap-2 py-5">
        <div className="w-8 h-8 bg-blue-600 rounded-lg flex items-center justify-center">
          <FileSpreadsheet size={16} className="text-white" />
        </div>
        <span className="font-semibold text-base">GridPull</span>
      </div>

      {/* Main content */}
      <div className="flex-1 flex flex-col items-center justify-center px-6 pb-12">
        {uploadCount > 0 && (
          <div className="mb-6 bg-emerald-50 border border-emerald-200 rounded-xl px-4 py-2.5 text-sm text-emerald-700 font-medium">
            {uploadCount} file{uploadCount !== 1 ? 's' : ''} uploaded
          </div>
        )}

        {status === 'error' && errorMsg && (
          <div className="mb-6 bg-red-50 border border-red-200 rounded-xl px-4 py-2.5 text-sm text-red-600">
            {errorMsg}
          </div>
        )}

        {status === 'success' && (
          <div className="mb-6">
            <div className="w-16 h-16 rounded-full bg-emerald-100 flex items-center justify-center mx-auto">
              <Check size={28} className="text-emerald-500" />
            </div>
          </div>
        )}

        {status === 'uploading' && (
          <div className="mb-6">
            <Loader2 size={32} className="animate-spin text-blue-500 mx-auto" />
            <p className="text-sm text-gray-500 mt-3">Uploading...</p>
          </div>
        )}

        <input
          ref={fileRef}
          type="file"
          accept="image/*"
          capture="environment"
          onChange={handleChange}
          className="hidden"
        />

        <input
          id="gallery-input"
          type="file"
          accept="image/*,.pdf,.png,.jpg,.jpeg,.webp,.gif,.bmp,.tif,.tiff,.txt,.html,.json,.xml,.eml,.msg"
          onChange={handleChange}
          className="hidden"
        />

        <div className="w-full max-w-xs space-y-3">
          <button
            onClick={() => fileRef.current?.click()}
            disabled={status === 'uploading'}
            className="w-full flex items-center justify-center gap-3 bg-blue-600 hover:bg-blue-700 disabled:opacity-50 text-white font-medium py-4 rounded-2xl shadow-lg shadow-blue-500/25 transition-all active:scale-[0.98]"
          >
            <Camera size={22} />
            Take Photo
          </button>

          <button
            onClick={() => document.getElementById('gallery-input')?.click()}
            disabled={status === 'uploading'}
            className="w-full flex items-center justify-center gap-3 bg-white hover:bg-gray-50 disabled:opacity-50 text-gray-700 font-medium py-4 rounded-2xl border border-gray-200 shadow-sm transition-all active:scale-[0.98]"
          >
            <Upload size={20} />
            Choose File
          </button>
        </div>

        <p className="text-xs text-gray-400 mt-8 text-center">
          Files appear in your GridPull inbox instantly.<br />
          Auto-deleted after 7 days.
        </p>
      </div>
    </div>
  )
}
