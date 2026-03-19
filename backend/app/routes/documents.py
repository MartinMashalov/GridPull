"""
Document routes.

POST /documents/extract          — upload PDFs, queue extraction job
GET  /documents/job/{id}         — poll job status (fallback for non-SSE clients)
GET  /documents/progress/{id}    — SSE stream of real-time progress events
GET  /documents/results/{id}     — fetch extracted data as JSON (for UI table)
GET  /documents/download/{id}    — stream the xlsx/csv file
GET  /documents/history          — paginated job history for current user
"""

import asyncio
import json
import logging
import os
from typing import AsyncIterator, List

import aiofiles
from fastapi import APIRouter, Depends, HTTPException, Request, UploadFile, File, Form
from fastapi.responses import FileResponse, StreamingResponse
from sqlalchemy import select, func, desc
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
from app.services.spreadsheet_service import generate_quickbooks_csv_bytes, generate_qbo_bytes, read_headers_from_bytes
from app.services.subscription_tiers import get_tier
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

KEEPALIVE_INTERVAL = 20


# ── Routes ─────────────────────────────────────────────────────────────────────

@router.post("/spreadsheet-headers")
async def parse_spreadsheet_headers(
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
):
    """Return the header row from an uploaded xlsx or csv file."""
    fname = (file.filename or "").lower()
    if fname.endswith(".xlsx"):
        fmt = "xlsx"
    elif fname.endswith(".csv"):
        fmt = "csv"
    else:
        raise HTTPException(status_code=400, detail="Only .xlsx or .csv files are supported")

    content = await file.read()
    try:
        headers = read_headers_from_bytes(content, fmt)
    except Exception as exc:
        logger.error("Failed to read spreadsheet headers from %s: %s", file.filename, exc)
        raise HTTPException(status_code=422, detail=f"Could not parse spreadsheet: {exc}")

    # Strip empty/None headers and the leading "Source File" column if present
    cleaned = [h for h in headers if h and h.strip() and h.strip().lower() != "source file"]
    return {"headers": cleaned, "filename": file.filename}


@router.post("/extract")
async def start_extraction(
    request: Request,
    files: List[UploadFile] = File(...),
    fields: str = Form(...),
    instructions: str = Form(""),
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

    # ── Subscription-based usage enforcement ──────────────────────────────────
    tier = get_tier(getattr(current_user, "subscription_tier", "free") or "free")
    _SPREADSHEET_EXTS = {".xlsx", ".csv"}
    num_files = sum(1 for f in files if os.path.splitext((f.filename or "").lower())[1] not in _SPREADSHEET_EXTS)

    # Reset usage if period rolled over
    from app.routes.payments import _maybe_reset_usage
    result_u = await db.execute(select(User).where(User.id == current_user.id))
    db_user = result_u.scalar_one_or_none()
    if db_user:
        _maybe_reset_usage(db_user)
        await db.commit()
        await db.refresh(db_user)
        used = db_user.files_used_this_period or 0
    else:
        used = current_user.files_used_this_period or 0

    remaining = max(0, tier.files_per_month - used)

    if tier.name == "free" and used + num_files > tier.files_per_month:
        raise HTTPException(
            status_code=402,
            detail={
                "type": "file_limit_reached",
                "message": f"Free plan allows {tier.files_per_month} files/month. You've used {used}.",
                "files_used": used,
                "files_limit": tier.files_per_month,
                "tier": tier.name,
            },
        )

    # Paid tiers: allow overages
    overage_count = max(0, (used + num_files) - tier.files_per_month)

    filenames = [f.filename for f in files]
    logger.info(
        "Extract request — user_id=%s files=%s fields=%s format=%s instructions=%d chars ip=%s",
        current_user.id,
        filenames,
        [f["name"] for f in fields_data],
        format,
        len(instructions.strip()),
        client_ip,
    )

    # Create job record
    job = ExtractionJob(
        user_id=current_user.id,
        status="queued",
        fields=fields_data,
        instructions=instructions.strip() or None,
        format=format,
        file_count=len(files),
    )
    db.add(job)
    await db.commit()
    await db.refresh(job)

    # Increment usage counters
    if db_user:
        db_user.files_used_this_period = (db_user.files_used_this_period or 0) + num_files
        if overage_count > 0:
            db_user.overage_files_this_period = (db_user.overage_files_this_period or 0) + overage_count
        await db.commit()

    logger.info("Job created — job_id=%s user_id=%s files_used=%d", job.id, current_user.id, (db_user.files_used_this_period if db_user else 0))

    # Persist uploaded files
    upload_dir = os.path.join(settings.upload_dir, job.id)
    os.makedirs(upload_dir, exist_ok=True)
    saved_count = 0

    _ALLOWED_EXT = {".pdf", ".png", ".jpg", ".jpeg"}
    _SPREADSHEET_EXT = {".xlsx", ".csv"}

    for upload in files:
        fname = upload.filename or ""
        ext = os.path.splitext(fname.lower())[1]
        if ext in _SPREADSHEET_EXT:
            # Spreadsheet files are baseline references — skip them from extraction
            logger.info("Skipping baseline spreadsheet %s in job %s", fname, job.id)
            continue
        if ext not in _ALLOWED_EXT:
            logger.warning("Skipping unsupported file %s in job %s", fname, job.id)
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
    logger.info("Saved %d file(s) for job %s — enqueuing…", saved_count, job.id)

    # Enqueue into the worker pool
    await worker_pool.submit(process_job, job.id, worker_pool.broadcast)
    queue_depth = worker_pool._job_queue.qsize()
    logger.info(
        "Job %s enqueued — queue depth: %d — user_id=%s",
        job.id, queue_depth, current_user.id,
    )

    new_used = (db_user.files_used_this_period if db_user else used + num_files)
    usage_pct = (new_used / tier.files_per_month * 100) if tier.files_per_month else 0

    return {
        "job_id": job.id,
        "status": "queued",
        "usage": {
            "files_used": new_used,
            "files_limit": tier.files_per_month,
            "usage_percent": min(usage_pct, 100),
            "overage_files": overage_count,
            "tier": tier.name,
        },
    }


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
        "completed_docs": job.completed_docs,
        "total_docs": job.file_count,
        "error": job.error,
        "format": job.format,
        "file_count": job.file_count,
        "cost": job.cost,
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
        results = []
        for d in docs:
            if d.extracted_data:
                results.extend(d.extracted_data if isinstance(d.extracted_data, list) else [d.extracted_data])
        field_names = (
            [f["name"] if isinstance(f, dict) else str(f) for f in job.fields]
            if isinstance(job.fields, list)
            else []
        )

        async def _done_stream() -> AsyncIterator[str]:
            event = {
                "type": "complete",
                "status": "complete",
                "progress": 100,
                "message": "Extraction complete!",
                "download_url": f"/api/documents/download/{job_id}",
                "results": results,
                "fields": field_names,
                "cost": job.cost,
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
        # Tell the browser to reconnect after 3s if connection drops
        yield "retry: 3000\n\n"
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
                    yield f"data: {json.dumps({'type': 'keepalive'})}\n\n"
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
    flat_results = []
    for d in job.documents:
        if d.extracted_data:
            flat_results.extend(d.extracted_data if isinstance(d.extracted_data, list) else [d.extracted_data])
    payload = {
        "job_id": job.id,
        "format": job.format,
        "fields": (
            [f["name"] if isinstance(f, dict) else str(f) for f in job.fields]
            if isinstance(job.fields, list)
            else []
        ),
        "results": flat_results,
        "cost": job.cost,
    }
    await cache_set_results(job_id, current_user.id, payload)
    _RESULT_CACHE[job_id] = {**payload, "_owner": current_user.id}
    return payload


@router.delete("/job/{job_id}")
async def cancel_job(
    job_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Cancel a queued or in-progress job."""
    result = await db.execute(
        select(ExtractionJob).where(
            ExtractionJob.id == job_id,
            ExtractionJob.user_id == current_user.id,
        )
    )
    job = result.scalar_one_or_none()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    if job.status not in ("complete", "error", "cancelled"):
        job.status = "cancelled"
        await db.commit()
        await worker_pool.broadcast(
            job_id,
            {"type": "error", "status": "cancelled", "progress": 0, "message": "Job cancelled"},
        )
        logger.info("Job %s cancelled by user_id=%s", job_id, current_user.id)

    return {"ok": True}


@router.get("/history")
async def get_job_history(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    limit: int = 50,
    offset: int = 0,
):
    """Return the user's extraction job history, newest first."""
    # Total count
    count_q = await db.execute(
        select(func.count(ExtractionJob.id)).where(ExtractionJob.user_id == current_user.id)
    )
    total = count_q.scalar() or 0

    # Jobs with document filenames
    result = await db.execute(
        select(ExtractionJob)
        .options(joinedload(ExtractionJob.documents))
        .where(ExtractionJob.user_id == current_user.id)
        .order_by(desc(ExtractionJob.created_at))
        .offset(offset)
        .limit(min(limit, 100))
    )
    jobs = result.unique().scalars().all()

    items = []
    for j in jobs:
        filenames = [d.filename for d in j.documents] if j.documents else []
        items.append({
            "job_id": j.id,
            "status": j.status,
            "file_count": j.file_count,
            "filenames": filenames,
            "fields": (
                [f["name"] if isinstance(f, dict) else str(f) for f in j.fields]
                if isinstance(j.fields, list)
                else []
            ),
            "format": j.format,
            "cost": j.cost,
            "created_at": j.created_at.isoformat() if j.created_at else None,
        })

    # Current-period count
    tier = get_tier(getattr(current_user, "subscription_tier", "free") or "free")
    from app.routes.payments import _maybe_reset_usage
    result_u = await db.execute(select(User).where(User.id == current_user.id))
    db_user = result_u.scalar_one_or_none()
    if db_user:
        _maybe_reset_usage(db_user)
        await db.commit()

    files_used = db_user.files_used_this_period if db_user else 0
    files_limit = tier.files_per_month

    return {
        "jobs": items,
        "total": total,
        "files_used_this_period": files_used,
        "files_limit": files_limit,
        "usage_percent": min((files_used / files_limit * 100) if files_limit else 0, 100),
        "tier": tier.name,
    }


@router.get("/download/{job_id}")
async def download_result(
    job_id: str,
    current_user: User = Depends(get_current_user_sse),
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

    # Block download for free-tier users who have exceeded their limit
    tier = get_tier(getattr(current_user, "subscription_tier", "free") or "free")
    if tier.name == "free":
        r2 = await db.execute(select(User).where(User.id == current_user.id))
        u = r2.scalar_one_or_none()
        if u and (u.files_used_this_period or 0) > tier.files_per_month:
            raise HTTPException(
                status_code=402,
                detail={
                    "type": "paywall",
                    "message": "Upgrade to download your results",
                    "tier": "free",
                },
            )

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


@router.get("/download/{job_id}/accounting")
async def download_accounting_format(
    job_id: str,
    fmt: str = "qb_csv",
    current_user: User = Depends(get_current_user_sse),
    db: AsyncSession = Depends(get_db),
):
    """Generate and stream QuickBooks CSV, QBO, or OFX file from extracted results."""
    if fmt not in ("qb_csv", "qbo", "ofx"):
        raise HTTPException(status_code=400, detail="fmt must be qb_csv, qbo, or ofx")

    result = await db.execute(
        select(ExtractionJob)
        .options(joinedload(ExtractionJob.documents))
        .where(ExtractionJob.id == job_id, ExtractionJob.user_id == current_user.id)
    )
    job = result.unique().scalar_one_or_none()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    if job.status != "complete":
        raise HTTPException(status_code=400, detail="Job not complete")

    tier = get_tier(getattr(current_user, "subscription_tier", "free") or "free")
    if tier.name == "free":
        r2 = await db.execute(select(User).where(User.id == current_user.id))
        u = r2.scalar_one_or_none()
        if u and (u.files_used_this_period or 0) > tier.files_per_month:
            raise HTTPException(status_code=402, detail={"type": "paywall", "message": "Upgrade to download"})

    flat_results: list[dict] = []
    for d in job.documents:
        if d.extracted_data:
            flat_results.extend(d.extracted_data if isinstance(d.extracted_data, list) else [d.extracted_data])

    if fmt == "qb_csv":
        content = generate_quickbooks_csv_bytes(flat_results)
        return StreamingResponse(
            iter([content]),
            media_type="text/csv",
            headers={"Content-Disposition": "attachment; filename=quickbooks_online.csv"},
        )
    else:
        content = generate_qbo_bytes(flat_results)
        ext = "qbo" if fmt == "qbo" else "ofx"
        label = "quickbooks_desktop" if fmt == "qbo" else "xero_import"
        return StreamingResponse(
            iter([content]),
            media_type="application/x-ofx",
            headers={"Content-Disposition": f"attachment; filename={label}.{ext}"},
        )
