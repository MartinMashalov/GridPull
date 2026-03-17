/**
 * useJobProgress — bulletproof job tracking for a GridPull extraction job.
 *
 * Architecture:
 *   PRIMARY:   Polling /api/documents/job/:jobId every 2s — always works,
 *              reads directly from DB, never drops.
 *   SECONDARY: SSE stream for real-time per-doc progress events when available.
 *
 * SSE enhances the UX (shows X/Y files in real-time) but the job will ALWAYS
 * complete correctly even if SSE fails entirely, because polling detects it.
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

const POLL_INTERVAL_MS = 2000

export function useJobProgress(jobId: string | null): UseJobProgressReturn {
  const token = useAuthStore((s) => s.token)
  const [event, setEvent] = useState<ProgressEvent | null>(null)
  const [connected, setConnected] = useState(false)

  const esRef = useRef<EventSource | null>(null)
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null)
  const doneRef = useRef(false)
  // Prevent double-firing complete/error if both SSE and poll detect it simultaneously
  const resolvedRef = useRef(false)

  const stopAll = () => {
    esRef.current?.close()
    esRef.current = null
    if (pollRef.current) { clearInterval(pollRef.current); pollRef.current = null }
    setConnected(false)
  }

  const reset = () => {
    doneRef.current = false
    resolvedRef.current = false
    stopAll()
    setEvent(null)
  }

  useEffect(() => {
    if (!jobId || !token) return
    doneRef.current = false
    resolvedRef.current = false

    // ── PRIMARY: Polling every 2s ─────────────────────────────────────────────
    // Runs from the very start. Always reads from DB. Guaranteed delivery.
    const pollOnce = async () => {
      if (resolvedRef.current) return
      try {
        const res = await fetch(`/api/documents/job/${jobId}`, {
          headers: { Authorization: `Bearer ${token}` },
        })
        if (!res.ok) return
        const data = await res.json()

        if (data.status === 'complete' && !resolvedRef.current) {
          resolvedRef.current = true
          // Fetch full results for the spreadsheet viewer
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
          stopAll()
          return
        }

        if (data.status === 'error' && !resolvedRef.current) {
          resolvedRef.current = true
          setEvent({ type: 'error', status: 'error', progress: 0, message: 'Extraction failed', error: data.error })
          stopAll()
          return
        }

        // While in progress, update from DB so the bar moves even if SSE lands on another worker.
        if (!resolvedRef.current) {
          setEvent((prev) => {
            const pollCount = data.completed_docs ?? 0
            const prevCount = prev?.completed_docs ?? 0
            const pollProgress = data.progress ?? 0
            const prevProgress = prev?.progress ?? 0
            const statusChanged = data.status !== prev?.status
            if (pollCount <= prevCount && pollProgress <= prevProgress && !statusChanged) return prev
            return {
              type: 'progress',
              status: data.status,
              progress: pollProgress,
              message: pollCount > 0
                ? `${pollCount}/${data.total_docs} files processed`
                : data.status === 'processing'
                  ? 'Preparing extraction…'
                  : data.status === 'extracting'
                    ? 'Extracting documents…'
                    : data.status === 'generating'
                      ? 'Generating spreadsheet…'
                      : 'Processing…',
              completed_docs: pollCount,
              total_docs: data.total_docs,
            }
          })
        }
      } catch {
        // network blip — keep polling
      }
    }

    void pollOnce()
    pollRef.current = setInterval(() => { void pollOnce() }, POLL_INTERVAL_MS)

    // ── SECONDARY: SSE for real-time per-doc events ───────────────────────────
    // Enhances progress display. If it fails, polling above handles everything.
    const url = `/api/documents/progress/${jobId}?token=${encodeURIComponent(token)}`
    const es = new EventSource(url)
    esRef.current = es
    setConnected(true)

    es.onmessage = (e: MessageEvent) => {
      try {
        const data = JSON.parse(e.data) as ProgressEvent & { type: string }
        if ((data as { type: string }).type === 'keepalive') return  // ignore heartbeats

        if ((data.type === 'complete' || data.type === 'error') && !resolvedRef.current) {
          resolvedRef.current = true
          setEvent(data)
          stopAll()
          return
        }

        if (data.type === 'progress' && !resolvedRef.current) {
          setEvent(data)
        }
      } catch {
        // malformed frame — ignore
      }
    }

    es.onerror = () => {
      // Don't close — let EventSource auto-reconnect every 3s (retry: 3000 set by server).
      // Polling above is already running and will catch completion regardless.
      setConnected(false)
    }

    return stopAll
  }, [jobId, token])

  return { event, connected, reset }
}
