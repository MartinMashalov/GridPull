"""
Job processor: runs inside the worker pool.

Responsibilities:
1. Read each PDF with PyMuPDF
2. Call OpenAI extraction (model rotation handled by extraction_service)
3. Generate Excel/CSV with openpyxl
4. Deduct credits from the user
5. Broadcast granular progress events for SSE subscribers
"""

import asyncio
import logging
import os
import time
from typing import Any, Callable, Dict, List

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy import select

from app.config import settings
from app.models.extraction import Document, ExtractionJob
from app.models.user import User
from app.services.extraction_service import LLMUsage, extract_from_document
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

    async def emit(status: str, progress: int, message: str, completed_docs: int = 0, total_docs_count: int = 0) -> None:
        logger.debug("Job %s progress — status=%s pct=%d msg=%r", job_id, status, progress, message)
        await broadcast(
            job_id,
            {
                "type": "progress",
                "status": status,
                "progress": progress,
                "message": message,
                "completed_docs": completed_docs,
                "total_docs": total_docs_count,
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
            await emit("processing", 5, f"Starting extraction of {total_docs} document(s)…", 0, total_docs)

            all_extracted: List[Dict[str, Any]] = []
            total_pages = 0
            job_usage = LLMUsage()  # Accumulates token cost across all docs (safe: asyncio is single-threaded)
            completed_count = 0
            results_ordered: List[List[Dict[str, Any]]] = [[] for _ in range(total_docs)]
            sem = asyncio.Semaphore(8)  # Up to 8 docs extracted concurrently

            async def _process_doc(idx: int, doc_id: str, filename: str, file_path: str) -> None:
                nonlocal total_pages, completed_count
                async with sem:
                    doc_start = time.monotonic()
                    logger.info(
                        "Job %s — processing doc %d/%d: %s",
                        job_id, idx + 1, total_docs, filename,
                    )
                    async with _WorkerSession() as doc_db:
                        doc_res = await doc_db.execute(select(Document).where(Document.id == doc_id))
                        doc_obj = doc_res.scalar_one()
                        try:
                            parsed_doc = await asyncio.to_thread(parse_pdf, file_path, filename)
                            doc_obj.page_count = parsed_doc.page_count
                            total_pages += parsed_doc.page_count
                            doc_obj.status = "processing"
                            await doc_db.commit()

                            logger.info(
                                "Job %s — parsed %s: %d pages, type=%s",
                                job_id, filename, parsed_doc.page_count,
                                getattr(parsed_doc, "doc_type_hint", "unknown"),
                            )

                            rows = await extract_from_document(parsed_doc, fields, job_usage)
                            doc_obj.extracted_data = rows
                            doc_obj.status = "complete"
                            results_ordered[idx] = rows
                            await doc_db.commit()

                            completed_count += 1
                            doc_elapsed = (time.monotonic() - doc_start) * 1000
                            logger.info(
                                "Job %s — extracted %s: %d row(s) in %.0fms",
                                job_id, filename, len(rows), doc_elapsed,
                            )
                            # Persist completed_docs so polling endpoint shows real progress
                            job_res2 = await doc_db.execute(select(ExtractionJob).where(ExtractionJob.id == job_id))
                            job_rec = job_res2.scalar_one_or_none()
                            if job_rec:
                                job_rec.completed_docs = completed_count
                                await doc_db.commit()
                            pct = 5 + int((completed_count / total_docs) * 65)
                            await emit(
                                "extracting", pct,
                                f"✓ {filename} done ({completed_count}/{total_docs})",
                                completed_count, total_docs,
                            )

                        except Exception as exc:
                            logger.error(
                                "Job %s — error processing %s: %s",
                                job_id, filename, exc, exc_info=True,
                            )
                            doc_obj.status = "error"
                            row: Dict[str, Any] = {f: "" for f in field_names}
                            row["_source_file"] = filename
                            row["_error"] = str(exc)
                            results_ordered[idx] = [row]
                            completed_count += 1
                            # Also persist on error
                            job_res2 = await doc_db.execute(select(ExtractionJob).where(ExtractionJob.id == job_id))
                            job_rec = job_res2.scalar_one_or_none()
                            if job_rec:
                                job_rec.completed_docs = completed_count
                            await doc_db.commit()

            # Kick off all docs in parallel (semaphore caps at 8 concurrent)
            job.status = "extracting"
            await db.commit()
            await emit("extracting", 5, f"Extracting {total_docs} document(s) in parallel…", 0, total_docs)

            await asyncio.gather(*[
                _process_doc(i, doc.id, doc.filename, doc.file_path)
                for i, doc in enumerate(documents)
            ])

            # Flatten results preserving original document order
            for slot in results_ordered:
                all_extracted.extend(slot)

            # ── Phase 2: generate spreadsheet ─────────────────────────
            job.status = "generating"
            await db.commit()
            await emit("generating", 75, "Generating spreadsheet…", total_docs, total_docs)

            output_filename = f"gridpull_{job_id}.{job.format}"
            output_path = os.path.join(settings.output_dir, output_filename)

            gen_start = time.monotonic()
            if job.format == "csv":
                await asyncio.to_thread(generate_csv, all_extracted, output_path, field_names)
            else:
                await asyncio.to_thread(generate_excel, all_extracted, output_path, field_names)

            file_size_kb = os.path.getsize(output_path) / 1024
            gen_elapsed = (time.monotonic() - gen_start) * 1000
            logger.info(
                "Job %s — spreadsheet generated: %s (%.1f KB) in %.0fms",
                job_id, output_filename, file_size_kb, gen_elapsed,
            )

            await emit("generating", 90, "Spreadsheet ready — updating balance…", total_docs, total_docs)

            # ── Phase 3: deduct balance (actual token cost + 20% markup) ──
            result = await db.execute(select(User).where(User.id == job.user_id))
            user = result.scalar_one_or_none()
            job_cost = job_usage.cost_usd
            if user:
                balance_before = user.balance
                user.balance = max(0.0, user.balance - job_cost)
                job.cost = job_cost
                await db.commit()
                logger.info(
                    "Job %s — balance deducted: $%.6f → $%.6f "
                    "(cost=$%.6f in=%d out=%d tokens pages=%d) user_id=%s",
                    job_id, balance_before, user.balance,
                    job_cost, job_usage.input_tokens, job_usage.output_tokens,
                    total_pages, job.user_id,
                )

            # ── Mark complete ──────────────────────────────────────────
            job.status = "complete"
            job.output_path = output_path
            job.progress = 100
            await db.commit()

            total_elapsed = (time.monotonic() - job_start) * 1000
            logger.info(
                "=== Job %s COMPLETE — docs=%d rows=%d cost=$%.6f elapsed=%.0fms ===",
                job_id, total_docs, len(all_extracted), job_cost, total_elapsed,
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
                    "cost": job.cost,
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
