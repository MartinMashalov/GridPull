"""
WorkerPool: 150 concurrent asyncio workers with per-job SSE event broadcasting.

Architecture:
- A single asyncio.Queue acts as the job inbox
- 150 persistent coroutines consume from the queue (true concurrent processing)
- Per-job asyncio.Queue instances allow SSE endpoints to stream real-time events
- Broadcast is fan-out: every SSE subscriber for a job_id receives every event
"""

import asyncio
import logging
from typing import Any, Callable, Dict, List

logger = logging.getLogger(__name__)


class WorkerPool:
    NUM_WORKERS = 150

    def __init__(self) -> None:
        self._job_queue: asyncio.Queue = None          # type: ignore[assignment]
        self._workers: List[asyncio.Task] = []
        self._running = False
        # job_id → list of per-subscriber queues
        self._listeners: Dict[str, List[asyncio.Queue]] = {}
        self._listener_lock: asyncio.Lock = None       # type: ignore[assignment]

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def start(self) -> None:
        """Spawn all worker coroutines. Call once at app startup."""
        self._job_queue = asyncio.Queue()
        self._listener_lock = asyncio.Lock()
        self._running = True

        for idx in range(self.NUM_WORKERS):
            task = asyncio.create_task(self._worker(idx), name=f"gridpull-worker-{idx}")
            self._workers.append(task)

        logger.info("WorkerPool started — %d workers ready", self.NUM_WORKERS)

    async def stop(self) -> None:
        """Cancel all workers gracefully. Call at app shutdown."""
        self._running = False
        for task in self._workers:
            task.cancel()
        await asyncio.gather(*self._workers, return_exceptions=True)
        self._workers.clear()
        logger.info("WorkerPool stopped")

    # ------------------------------------------------------------------
    # Job submission
    # ------------------------------------------------------------------

    async def submit(self, func: Callable[..., Any], *args: Any, **kwargs: Any) -> None:
        """Enqueue a coroutine function with its arguments."""
        await self._job_queue.put((func, args, kwargs))

    # ------------------------------------------------------------------
    # SSE pub/sub
    # ------------------------------------------------------------------

    async def subscribe(self, job_id: str) -> asyncio.Queue:
        """Register a new SSE subscriber for job_id; returns its event queue."""
        q: asyncio.Queue = asyncio.Queue()
        async with self._listener_lock:
            self._listeners.setdefault(job_id, []).append(q)
        return q

    async def unsubscribe(self, job_id: str, queue: asyncio.Queue) -> None:
        """Remove a subscriber queue. Cleans up empty job entries."""
        async with self._listener_lock:
            listeners = self._listeners.get(job_id, [])
            try:
                listeners.remove(queue)
            except ValueError:
                pass
            if not listeners:
                self._listeners.pop(job_id, None)

    async def broadcast(self, job_id: str, event: Dict[str, Any]) -> None:
        """Fan-out an event to every subscriber listening to job_id."""
        async with self._listener_lock:
            listeners = list(self._listeners.get(job_id, []))
        for q in listeners:
            try:
                q.put_nowait(event)
            except asyncio.QueueFull:
                logger.warning("SSE queue full for job %s — dropping event", job_id)

    # ------------------------------------------------------------------
    # Internal worker loop
    # ------------------------------------------------------------------

    async def _worker(self, worker_id: int) -> None:
        while self._running:
            try:
                func, args, kwargs = await asyncio.wait_for(
                    self._job_queue.get(), timeout=1.0
                )
            except asyncio.TimeoutError:
                continue
            except asyncio.CancelledError:
                break

            try:
                await func(*args, **kwargs)
            except Exception as exc:
                logger.error("Worker %d unhandled error: %s", worker_id, exc, exc_info=True)
            finally:
                self._job_queue.task_done()


# Singleton — imported everywhere
worker_pool = WorkerPool()
