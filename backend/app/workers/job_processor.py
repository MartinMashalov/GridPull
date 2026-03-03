"""
Job processor: runs inside the worker pool.

Responsibilities:
1. Read each PDF with PyMuPDF
2. Call OpenAI extraction (model rotation handled by extraction_service)
3. Generate Excel/CSV with openpyxl
4. Deduct credits from the user
5. Broadcast granular progress events for SSE subscribers
"""

import logging
import os
import time
from typing import Any, Callable, Dict, List

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy import select

from app.config import settings
from app.models.extraction import Document, ExtractionJob
from app.models.user import User
from app.services.extraction_service import extract_from_document
from app.services.pdf_service import parse_pdf
from app.services.spreadsheet_service import generate_csv, generate_excel

logger = logging.getLogger(__name__)

# ── Shared engine for worker jobs ─────────────────────────────────────────────
_is_postgres = settings.database_url.startswith("postgresql")

if _is_postgres:
    _worker_engine = create_async_engine(
        settings.database_url,
        pool_size=10,
        max_overflow=20,
        pool_recycle=1800,
        pool_pre_ping=True,
        connect_args={
            "prepared_statement_cache_size": 0,
            "statement_cache_size": 0,
        },
    )
else:
    _worker_engine = create_async_engine(
        settings.database_url,
        connect_args={"check_same_thread": False},
    )

_WorkerSession = async_sessionmaker(
    _worker_engine, class_=AsyncSession, expire_on_commit=False
)


async def process_job(
    job_id: str,
    broadcast: Callable[[str, Dict[str, Any]], Any],
) -> None:
    """
    Full extraction pipeline for one job.
    `broadcast(job_id, event_dict)` fans out SSE events to subscribers.
    """
    job_start = time.monotonic()
    logger.info("=== Job %s started ===", job_id)

    async def emit(status: str, progress: int, message: str) -> None:
        logger.debug("Job %s progress — status=%s pct=%d msg=%r", job_id, status, progress, message)
        await broadcast(
            job_id,
            {
                "type": "progress",
                "status": status,
                "progress": progress,
                "message": message,
            },
        )

    async with _WorkerSession() as db:
        try:
            # ── Fetch job ──────────────────────────────────────────────
            result = await db.execute(
                select(ExtractionJob).where(ExtractionJob.id == job_id)
            )
            job = result.scalar_one_or_none()
            if not job:
                logger.error("Job %s not found in DB — aborting", job_id)
                return

            result = await db.execute(
                select(Document).where(Document.job_id == job_id)
            )
            documents = result.scalars().all()

            fields = job.fields
            field_names = [f["name"] for f in fields]
            total_docs = len(documents)

            logger.info(
                "Job %s — user_id=%s docs=%d fields=%s format=%s",
                job_id, job.user_id, total_docs, field_names, job.format,
            )

            # ── Phase 1: processing ────────────────────────────────────
            job.status = "processing"
            await db.commit()
            await emit("processing", 5, f"Starting extraction of {total_docs} document(s)…")

            all_extracted: List[Dict[str, Any]] = []
            total_pages = 0

            for idx, doc in enumerate(documents):
                base_pct = 5 + int((idx / total_docs) * 65)
                doc_start = time.monotonic()

                logger.info(
                    "Job %s — processing doc %d/%d: %s",
                    job_id, idx + 1, total_docs, doc.filename,
                )

                await emit(
                    "extracting",
                    base_pct,
                    f"Reading {doc.filename} ({idx + 1}/{total_docs})…",
                )
                job.status = "extracting"
                await db.commit()

                try:
                    parsed_doc = parse_pdf(doc.file_path, doc.filename)
                    doc.page_count = parsed_doc.page_count
                    total_pages += parsed_doc.page_count
                    doc.status = "processing"
                    await db.commit()

                    logger.info(
                        "Job %s — parsed %s: %d pages, type=%s",
                        job_id, doc.filename, parsed_doc.page_count,
                        getattr(parsed_doc, "doc_type_hint", "unknown"),
                    )

                    await emit(
                        "extracting",
                        base_pct + int(0.4 * (65 / total_docs)),
                        f"AI extracting {doc.filename} ({parsed_doc.page_count} pages)…",
                    )

                    rows = await extract_from_document(parsed_doc, fields)
                    doc.extracted_data = rows
                    doc.status = "complete"
                    all_extracted.extend(rows)
                    await db.commit()

                    doc_elapsed = (time.monotonic() - doc_start) * 1000
                    logger.info(
                        "Job %s — extracted %s: %d row(s) in %.0fms",
                        job_id, doc.filename, len(rows), doc_elapsed,
                    )

                    await emit(
                        "extracting",
                        base_pct + int(0.8 * (65 / total_docs)),
                        f"✓ {doc.filename} done ({idx + 1}/{total_docs})",
                    )

                except Exception as exc:
                    logger.error(
                        "Job %s — error processing %s: %s",
                        job_id, doc.filename, exc, exc_info=True,
                    )
                    doc.status = "error"
                    row: Dict[str, Any] = {f: "" for f in field_names}
                    row["_source_file"] = doc.filename
                    row["_error"] = str(exc)
                    all_extracted.append(row)
                    await db.commit()

            # ── Phase 2: generate spreadsheet ─────────────────────────
            job.status = "generating"
            await db.commit()
            await emit("generating", 75, "Generating spreadsheet…")

            output_filename = f"gridpull_{job_id}.{job.format}"
            output_path = os.path.join(settings.output_dir, output_filename)

            gen_start = time.monotonic()
            if job.format == "csv":
                generate_csv(all_extracted, output_path, field_names)
            else:
                generate_excel(all_extracted, output_path, field_names)

            file_size_kb = os.path.getsize(output_path) / 1024
            gen_elapsed = (time.monotonic() - gen_start) * 1000
            logger.info(
                "Job %s — spreadsheet generated: %s (%.1f KB) in %.0fms",
                job_id, output_filename, file_size_kb, gen_elapsed,
            )

            await emit("generating", 90, "Spreadsheet ready — updating credits…")

            # ── Phase 3: deduct credits ────────────────────────────────
            result = await db.execute(select(User).where(User.id == job.user_id))
            user = result.scalar_one_or_none()
            credits_used = 0
            if user:
                credits_used = max(1, total_pages)
                credits_before = user.credits
                user.credits = max(0, user.credits - credits_used)
                job.credits_used = credits_used
                await db.commit()
                logger.info(
                    "Job %s — credits deducted: %.2f → %.2f (used=%d pages=%d) user_id=%s",
                    job_id, credits_before, user.credits,
                    credits_used, total_pages, job.user_id,
                )

            # ── Mark complete ──────────────────────────────────────────
            job.status = "complete"
            job.output_path = output_path
            job.progress = 100
            await db.commit()

            total_elapsed = (time.monotonic() - job_start) * 1000
            logger.info(
                "=== Job %s COMPLETE — docs=%d rows=%d credits=%d elapsed=%.0fms ===",
                job_id, total_docs, len(all_extracted), credits_used, total_elapsed,
            )

            await broadcast(
                job_id,
                {
                    "type": "complete",
                    "status": "complete",
                    "progress": 100,
                    "message": "Extraction complete!",
                    "download_url": f"/api/documents/download/{job_id}",
                    "results": all_extracted,
                    "fields": field_names,
                    "credits_used": job.credits_used,
                },
            )

        except Exception as exc:
            total_elapsed = (time.monotonic() - job_start) * 1000
            logger.error(
                "=== Job %s FAILED after %.0fms: %s ===",
                job_id, total_elapsed, exc, exc_info=True,
            )
            result = await db.execute(
                select(ExtractionJob).where(ExtractionJob.id == job_id)
            )
            job = result.scalar_one_or_none()
            if job:
                job.status = "error"
                job.error = str(exc)
                await db.commit()

            await broadcast(
                job_id,
                {
                    "type": "error",
                    "status": "error",
                    "progress": 0,
                    "message": "Extraction failed",
                    "error": str(exc),
                },
            )
