/**
 * useJobProgress — real-time SSE hook for a GridPull extraction job.
 *
 * Connects to /api/documents/progress/:jobId?token=<jwt>
 * Emits typed ProgressEvent objects as they arrive.
 * Automatically closes the connection on "complete" or "error".
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

  const reset = () => {
    esRef.current?.close()
    esRef.current = null
    setEvent(null)
    setConnected(false)
  }

  useEffect(() => {
    if (!jobId || !token) return

    // EventSource cannot set headers — pass JWT as query param
    const url = `/api/documents/progress/${jobId}?token=${encodeURIComponent(token)}`
    const es = new EventSource(url)
    esRef.current = es
    setConnected(true)

    es.onmessage = (e: MessageEvent) => {
      try {
        const data = JSON.parse(e.data) as ProgressEvent
        setEvent(data)
        if (data.type === 'complete' || data.type === 'error') {
          es.close()
          setConnected(false)
        }
      } catch {
        // malformed frame — ignore
      }
    }

    es.onerror = () => {
      setConnected(false)
      es.close()
    }

    return () => {
      es.close()
      setConnected(false)
    }
  }, [jobId, token])

  return { event, connected, reset }
}
