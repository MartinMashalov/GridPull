/**
 * useJobProgress — real-time SSE hook for a GridPull extraction job.
 *
 * Primary: SSE stream /api/documents/progress/:jobId?token=<jwt>
 * Fallback: polls /api/documents/job/:jobId every 4s if SSE is unavailable
 * Automatically closes on "complete" or "error".
 */

import { useEffect, useRef, useState } from 'react'
import { useAuthStore } from '@/store/authStore'

export interface ProgressEvent {
  type: 'progress' | 'complete' | 'error'
  status: string
  progress: number
  message?: string
  completed_docs?: number
  total_docs?: number
  download_url?: string
  results?: Record<string, string>[]
  fields?: string[]
  cost?: number
  error?: string
}

interface UseJobProgressReturn {
  event: ProgressEvent | null
  connected: boolean
  reset: () => void
}

export function useJobProgress(jobId: string | null): UseJobProgressReturn {
  const token = useAuthStore((s) => s.token)
  const [event, setEvent] = useState<ProgressEvent | null>(null)
  const [connected, setConnected] = useState(false)
  const esRef = useRef<EventSource | null>(null)
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null)
  const doneRef = useRef(false)

  const stopPoll = () => {
    if (pollRef.current) { clearInterval(pollRef.current); pollRef.current = null }
  }

  const closeAll = () => {
    esRef.current?.close()
    esRef.current = null
    stopPoll()
    setConnected(false)
  }

  const reset = () => {
    doneRef.current = false
    closeAll()
    setEvent(null)
  }

  useEffect(() => {
    if (!jobId || !token) return
    doneRef.current = false

    // ── Polling fallback ──────────────────────────────────────────────────────
    const startPolling = () => {
      if (pollRef.current || doneRef.current) return
      pollRef.current = setInterval(async () => {
        if (doneRef.current) { stopPoll(); return }
        try {
          const res = await fetch(`/api/documents/job/${jobId}`, {
            headers: { Authorization: `Bearer ${token}` },
          })
          if (!res.ok) return
          const data = await res.json()

          if (data.status === 'complete') {
            doneRef.current = true
            stopPoll()
            // Fetch full results for the viewer
            const rRes = await fetch(`/api/documents/results/${jobId}`, {
              headers: { Authorization: `Bearer ${token}` },
            })
            const rData = rRes.ok ? await rRes.json() : {}
            setEvent({
              type: 'complete',
              status: 'complete',
              progress: 100,
              message: 'Extraction complete!',
              download_url: `/api/documents/download/${jobId}`,
              results: rData.results ?? [],
              fields: rData.fields ?? [],
              cost: data.cost,
            })
            closeAll()
          } else if (data.status === 'error') {
            doneRef.current = true
            stopPoll()
            setEvent({ type: 'error', status: 'error', progress: 0, message: 'Extraction failed', error: data.error })
            closeAll()
          }
        } catch {
          // network blip — keep polling
        }
      }, 4000)
    }

    // ── SSE primary ───────────────────────────────────────────────────────────
    const url = `/api/documents/progress/${jobId}?token=${encodeURIComponent(token)}`
    const es = new EventSource(url)
    esRef.current = es
    setConnected(true)

    es.onmessage = (e: MessageEvent) => {
      try {
        const data = JSON.parse(e.data) as ProgressEvent
        setEvent(data)
        if (data.type === 'complete' || data.type === 'error') {
          doneRef.current = true
          closeAll()
        }
      } catch {
        // malformed frame — ignore
      }
    }

    es.onerror = () => {
      setConnected(false)
      // Do NOT close — let EventSource auto-reconnect.
      // Start polling as a fallback in case reconnect keeps failing.
      startPolling()
    }

    return closeAll
  }, [jobId, token])

  return { event, connected, reset }
}
