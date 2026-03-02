"""
Document routes.

POST /documents/extract          — upload PDFs, queue extraction job
GET  /documents/job/{id}         — poll job status (fallback for non-SSE clients)
GET  /documents/progress/{id}    — SSE stream of real-time progress events
GET  /documents/results/{id}     — fetch extracted data as JSON (for UI table)
GET  /documents/download/{id}    — stream the xlsx/csv file
"""

import asyncio
import json
import logging
import os
from typing import AsyncIterator, List

import aiofiles
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
from fastapi.responses import FileResponse, StreamingResponse
from sqlalchemy import select
from sqlalchemy.orm import joinedload
from sqlalchemy.ext.asyncio import AsyncSession

from app.cache import (
    cache_get_job_status,
    cache_set_job_status,
    cache_get_results,
    cache_set_results,
)
from app.config import settings
from app.database import get_db
from app.middleware.auth_middleware import get_current_user, get_current_user_sse
from app.models.extraction import Document, ExtractionJob
from app.models.user import User
from app.workers.job_processor import process_job
from app.workers.pool import worker_pool

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/documents", tags=["documents"])

# ── In-process result cache — fallback when Redis is unavailable ───────────────
# Job results are immutable once status='complete'. Cache them forever (per-process).
_RESULT_CACHE: dict[str, dict] = {}
_JOB_STATUS_CACHE: dict[str, dict] = {}

# ── Helpers ────────────────────────────────────────────────────────────────────

_SSE_HEADERS = {
    "Cache-Control": "no-cache",
    "Connection": "keep-alive",
    "X-Accel-Buffering": "no",   # disable nginx buffering
    "Access-Control-Allow-Origin": "*",
}

KEEPALIVE_INTERVAL = 15  # seconds between SSE keepalive comments


# ── Routes ─────────────────────────────────────────────────────────────────────

@router.post("/extract")
async def start_extraction(
    files: List[UploadFile] = File(...),
    fields: str = Form(...),
    format: str = Form("xlsx"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Upload PDFs and enqueue an extraction job."""
    if not files:
        raise HTTPException(status_code=400, detail="No files provided")

    if format not in ("xlsx", "csv"):
        format = "xlsx"

    fields_data = json.loads(fields)
    if not fields_data:
        raise HTTPException(status_code=400, detail="No extraction fields provided")

    if current_user.credits < 1:
        raise HTTPException(
            status_code=402,
            detail="Insufficient credits — please purchase more.",
        )

    # Create job record
    job = ExtractionJob(
        user_id=current_user.id,
        status="queued",
        fields=fields_data,
        format=format,
        file_count=len(files),
    )
    db.add(job)
    await db.commit()
    await db.refresh(job)

    # Persist uploaded files
    upload_dir = os.path.join(settings.upload_dir, job.id)
    os.makedirs(upload_dir, exist_ok=True)

    for upload in files:
        if not (upload.filename or "").lower().endswith(".pdf"):
            continue
        path = os.path.join(upload_dir, upload.filename)
        async with aiofiles.open(path, "wb") as fh:
            await fh.write(await upload.read())
        db.add(Document(job_id=job.id, filename=upload.filename, file_path=path))

    await db.commit()

    # Enqueue into the worker pool
    await worker_pool.submit(process_job, job.id, worker_pool.broadcast)
    logger.info("Job %s enqueued (queue depth: %d)", job.id, worker_pool._job_queue.qsize())

    return {"job_id": job.id, "status": "queued"}


@router.get("/job/{job_id}")
async def get_job_status(
    job_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Polling fallback — prefer the SSE endpoint for real-time updates."""
    # ── Fast path 1: Redis (shared across workers) ────────────────────────────
    redis_hit = await cache_get_job_status(job_id, current_user.id)
    if redis_hit is not None:
        return redis_hit

    # ── Fast path 2: in-process dict (Redis fallback) ────────────────────────
    cache_key = f"{current_user.id}:{job_id}"
    if cache_key in _JOB_STATUS_CACHE:
        return _JOB_STATUS_CACHE[cache_key]

    # ── Slow path: DB ─────────────────────────────────────────────────────────
    result = await db.execute(
        select(ExtractionJob).where(
            ExtractionJob.id == job_id,
            ExtractionJob.user_id == current_user.id,
        )
    )
    job = result.scalar_one_or_none()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    payload = {
        "job_id": job.id,
        "status": job.status,
        "progress": job.progress,
        "error": job.error,
        "format": job.format,
        "file_count": job.file_count,
        "credits_used": job.credits_used,
    }
    if job.status in ("complete", "error"):
        # Terminal — cache forever in Redis and in-process
        await cache_set_job_status(job_id, current_user.id, payload)
        _JOB_STATUS_CACHE[cache_key] = payload
    return payload


@router.get("/progress/{job_id}")
async def job_progress_sse(
    job_id: str,
    current_user: User = Depends(get_current_user_sse),
    db: AsyncSession = Depends(get_db),
):
    """
    Server-Sent Events stream for a specific job.

    Events emitted:
      data: {"type": "progress", "status": "...", "progress": 0-100, "message": "..."}
      data: {"type": "complete", "progress": 100, "results": [...], "fields": [...], "download_url": "..."}
      data: {"type": "error",    "error": "..."}

    Connect via EventSource:
      new EventSource(`/api/documents/progress/${jobId}?token=${jwt}`)
    """
    # Verify job ownership
    result = await db.execute(
        select(ExtractionJob).where(
            ExtractionJob.id == job_id,
            ExtractionJob.user_id == current_user.id,
        )
    )
    job = result.scalar_one_or_none()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    # If already terminal, synthesise the event immediately
    if job.status == "complete":
        docs_res = await db.execute(select(Document).where(Document.job_id == job_id))
        docs = docs_res.scalars().all()
        results = [d.extracted_data for d in docs if d.extracted_data]
        field_names = [f["name"] for f in job.fields]

        async def _done_stream() -> AsyncIterator[str]:
            event = {
                "type": "complete",
                "status": "complete",
                "progress": 100,
                "message": "Extraction complete!",
                "download_url": f"/api/documents/download/{job_id}",
                "results": results,
                "fields": field_names,
                "credits_used": job.credits_used,
            }
            yield f"data: {json.dumps(event)}\n\n"

        return StreamingResponse(_done_stream(), media_type="text/event-stream", headers=_SSE_HEADERS)

    if job.status == "error":
        async def _err_stream() -> AsyncIterator[str]:
            yield f"data: {json.dumps({'type': 'error', 'status': 'error', 'error': job.error or 'Unknown error'})}\n\n"
        return StreamingResponse(_err_stream(), media_type="text/event-stream", headers=_SSE_HEADERS)

    # Subscribe to live events from the worker pool
    queue = await worker_pool.subscribe(job_id)

    async def _live_stream() -> AsyncIterator[str]:
        try:
            while True:
                try:
                    event = await asyncio.wait_for(queue.get(), timeout=KEEPALIVE_INTERVAL)
                    yield f"data: {json.dumps(event)}\n\n"
                    if event.get("type") in ("complete", "error"):
                        break
                except asyncio.TimeoutError:
                    # Keep connection alive
                    yield ": keepalive\n\n"
        finally:
            await worker_pool.unsubscribe(job_id, queue)

    return StreamingResponse(_live_stream(), media_type="text/event-stream", headers=_SSE_HEADERS)


@router.get("/results/{job_id}")
async def get_results(
    job_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Return extracted data as JSON for the in-browser spreadsheet viewer."""
    # ── Fast path 1: Redis (shared across workers) ────────────────────────────
    redis_hit = await cache_get_results(job_id, current_user.id)
    if redis_hit is not None:
        return redis_hit

    # ── Fast path 2: in-process dict (Redis fallback) ────────────────────────
    if job_id in _RESULT_CACHE:
        cached = _RESULT_CACHE[job_id]
        if cached.get("_owner") == current_user.id:
            return {k: v for k, v in cached.items() if k != "_owner"}

    # ── Slow path: single query fetching job + documents in one JOIN ──────────
    result = await db.execute(
        select(ExtractionJob)
        .options(joinedload(ExtractionJob.documents))
        .where(
            ExtractionJob.id == job_id,
            ExtractionJob.user_id == current_user.id,
        )
    )
    job = result.unique().scalar_one_or_none()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    if job.status != "complete":
        raise HTTPException(status_code=400, detail="Job not yet complete")

    payload = {
        "job_id": job.id,
        "format": job.format,
        "fields": [f["name"] for f in job.fields],
        "results": [d.extracted_data for d in job.documents if d.extracted_data],
        "credits_used": job.credits_used,
    }
    # Terminal — cache forever in Redis and in-process
    await cache_set_results(job_id, current_user.id, payload)
    _RESULT_CACHE[job_id] = {**payload, "_owner": current_user.id}
    return payload


@router.get("/download/{job_id}")
async def download_result(
    job_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Stream the completed xlsx/csv file."""
    result = await db.execute(
        select(ExtractionJob).where(
            ExtractionJob.id == job_id,
            ExtractionJob.user_id == current_user.id,
        )
    )
    job = result.scalar_one_or_none()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    if job.status != "complete":
        raise HTTPException(status_code=400, detail="Job not complete")
    if not job.output_path or not os.path.exists(job.output_path):
        raise HTTPException(status_code=404, detail="Output file not found")

    media_type = (
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        if job.format == "xlsx"
        else "text/csv"
    )
    return FileResponse(
        path=job.output_path,
        media_type=media_type,
        filename=f"gridpull_export.{job.format}",
    )
