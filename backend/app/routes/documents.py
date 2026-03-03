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
from fastapi import APIRouter, Depends, HTTPException, Request, UploadFile, File, Form
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
_RESULT_CACHE: dict[str, dict] = {}
_JOB_STATUS_CACHE: dict[str, dict] = {}

_SSE_HEADERS = {
    "Cache-Control": "no-cache",
    "Connection": "keep-alive",
    "X-Accel-Buffering": "no",
    "Access-Control-Allow-Origin": "*",
}

KEEPALIVE_INTERVAL = 15


# ── Routes ─────────────────────────────────────────────────────────────────────

@router.post("/extract")
async def start_extraction(
    request: Request,
    files: List[UploadFile] = File(...),
    fields: str = Form(...),
    format: str = Form("xlsx"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Upload PDFs and enqueue an extraction job."""
    client_ip = request.client.host if request.client else "-"

    if not files:
        logger.warning("Extract request with no files — user_id=%s", current_user.id)
        raise HTTPException(status_code=400, detail="No files provided")

    if format not in ("xlsx", "csv"):
        format = "xlsx"

    fields_data = json.loads(fields)
    if not fields_data:
        logger.warning("Extract request with no fields — user_id=%s", current_user.id)
        raise HTTPException(status_code=400, detail="No extraction fields provided")

    if current_user.balance < 0.001:
        logger.warning(
            "Extract rejected — insufficient balance $%.6f — user_id=%s",
            current_user.balance, current_user.id,
        )
        raise HTTPException(
            status_code=402,
            detail="Insufficient balance — please add funds.",
        )

    filenames = [f.filename for f in files]
    logger.info(
        "Extract request — user_id=%s files=%s fields=%s format=%s ip=%s",
        current_user.id,
        filenames,
        [f["name"] for f in fields_data],
        format,
        client_ip,
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

    logger.info("Job created — job_id=%s user_id=%s", job.id, current_user.id)

    # Persist uploaded files
    upload_dir = os.path.join(settings.upload_dir, job.id)
    os.makedirs(upload_dir, exist_ok=True)
    saved_count = 0

    for upload in files:
        fname = upload.filename or ""
        if not fname.lower().endswith(".pdf"):
            logger.warning("Skipping non-PDF file %s in job %s", fname, job.id)
            continue
        path = os.path.join(upload_dir, fname)
        content = await upload.read()
        async with aiofiles.open(path, "wb") as fh:
            await fh.write(content)
        size_kb = len(content) / 1024
        db.add(Document(job_id=job.id, filename=fname, file_path=path))
        logger.info("Saved %s (%.1f KB) for job %s", fname, size_kb, job.id)
        saved_count += 1

    await db.commit()
    logger.info("Saved %d PDF(s) for job %s — enqueuing…", saved_count, job.id)

    # Enqueue into the worker pool
    await worker_pool.submit(process_job, job.id, worker_pool.broadcast)
    queue_depth = worker_pool._job_queue.qsize()
    logger.info(
        "Job %s enqueued — queue depth: %d — user_id=%s",
        job.id, queue_depth, current_user.id,
    )

    return {"job_id": job.id, "status": "queued"}


@router.get("/job/{job_id}")
async def get_job_status(
    job_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Polling fallback — prefer the SSE endpoint for real-time updates."""
    # ── Fast path 1: Redis ────────────────────────────────────────────────────
    redis_hit = await cache_get_job_status(job_id, current_user.id)
    if redis_hit is not None:
        logger.debug("Job status cache hit (Redis) — job_id=%s", job_id)
        return redis_hit

    # ── Fast path 2: in-process dict ─────────────────────────────────────────
    cache_key = f"{current_user.id}:{job_id}"
    if cache_key in _JOB_STATUS_CACHE:
        logger.debug("Job status cache hit (local) — job_id=%s", job_id)
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
        logger.warning("Job %s not found for user_id=%s", job_id, current_user.id)
        raise HTTPException(status_code=404, detail="Job not found")

    logger.debug("Job status DB lookup — job_id=%s status=%s", job_id, job.status)
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
        await cache_set_job_status(job_id, current_user.id, payload)
        _JOB_STATUS_CACHE[cache_key] = payload
    return payload


@router.get("/progress/{job_id}")
async def job_progress_sse(
    job_id: str,
    current_user: User = Depends(get_current_user_sse),
    db: AsyncSession = Depends(get_db),
):
    """Server-Sent Events stream for a specific job."""
    logger.info("SSE connection opened — job_id=%s user_id=%s", job_id, current_user.id)

    result = await db.execute(
        select(ExtractionJob).where(
            ExtractionJob.id == job_id,
            ExtractionJob.user_id == current_user.id,
        )
    )
    job = result.scalar_one_or_none()
    if not job:
        logger.warning("SSE: job %s not found for user_id=%s", job_id, current_user.id)
        raise HTTPException(status_code=404, detail="Job not found")

    # Already terminal — synthesise event immediately
    if job.status == "complete":
        logger.info("SSE: job %s already complete — sending cached result", job_id)
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
        logger.info("SSE: job %s already errored — sending error event", job_id)

        async def _err_stream() -> AsyncIterator[str]:
            yield f"data: {json.dumps({'type': 'error', 'status': 'error', 'error': job.error or 'Unknown error'})}\n\n"

        return StreamingResponse(_err_stream(), media_type="text/event-stream", headers=_SSE_HEADERS)

    # Subscribe to live events
    queue = await worker_pool.subscribe(job_id)
    logger.info("SSE: subscribed to live events for job %s", job_id)

    async def _live_stream() -> AsyncIterator[str]:
        keepalive_count = 0
        try:
            while True:
                try:
                    event = await asyncio.wait_for(queue.get(), timeout=KEEPALIVE_INTERVAL)
                    yield f"data: {json.dumps(event)}\n\n"
                    if event.get("type") in ("complete", "error"):
                        logger.info(
                            "SSE: job %s finished with type=%s — closing stream",
                            job_id, event.get("type"),
                        )
                        break
                except asyncio.TimeoutError:
                    keepalive_count += 1
                    logger.debug("SSE keepalive #%d — job %s", keepalive_count, job_id)
                    yield ": keepalive\n\n"
        finally:
            await worker_pool.unsubscribe(job_id, queue)
            logger.info("SSE: stream closed for job %s", job_id)

    return StreamingResponse(_live_stream(), media_type="text/event-stream", headers=_SSE_HEADERS)


@router.get("/results/{job_id}")
async def get_results(
    job_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Return extracted data as JSON for the in-browser spreadsheet viewer."""
    redis_hit = await cache_get_results(job_id, current_user.id)
    if redis_hit is not None:
        logger.debug("Results cache hit (Redis) — job_id=%s", job_id)
        return redis_hit

    if job_id in _RESULT_CACHE:
        cached = _RESULT_CACHE[job_id]
        if cached.get("_owner") == current_user.id:
            logger.debug("Results cache hit (local) — job_id=%s", job_id)
            return {k: v for k, v in cached.items() if k != "_owner"}

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
        logger.warning("Results: job %s not found for user_id=%s", job_id, current_user.id)
        raise HTTPException(status_code=404, detail="Job not found")
    if job.status != "complete":
        raise HTTPException(status_code=400, detail="Job not yet complete")

    logger.info("Results DB lookup — job_id=%s docs=%d", job_id, len(job.documents))
    payload = {
        "job_id": job.id,
        "format": job.format,
        "fields": [f["name"] for f in job.fields],
        "results": [d.extracted_data for d in job.documents if d.extracted_data],
        "credits_used": job.credits_used,
    }
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
        logger.warning("Download: job %s not found for user_id=%s", job_id, current_user.id)
        raise HTTPException(status_code=404, detail="Job not found")
    if job.status != "complete":
        raise HTTPException(status_code=400, detail="Job not complete")
    if not job.output_path or not os.path.exists(job.output_path):
        logger.error(
            "Download: output file missing — job_id=%s path=%s",
            job_id, job.output_path,
        )
        raise HTTPException(status_code=404, detail="Output file not found")

    file_size = os.path.getsize(job.output_path)
    logger.info(
        "Download — job_id=%s format=%s size=%.1fKB user_id=%s",
        job_id, job.format, file_size / 1024, current_user.id,
    )

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
