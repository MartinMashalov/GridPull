"""
Job processor: runs inside the worker pool.

Responsibilities:
1. Read each PDF with PyMuPDF
2. Call OpenAI extraction (model rotation handled by extraction_service)
3. Generate Excel/CSV with openpyxl
4. Deduct credits from the user
5. Broadcast granular progress events for SSE subscribers
"""

import os
import logging
from typing import Any, Callable, Dict, List

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy import select

from app.config import settings
from app.models.extraction import Document, ExtractionJob
from app.models.user import User
from app.services.extraction_service import extract_fields_from_text
from app.services.pdf_service import read_pdf_text
from app.services.spreadsheet_service import generate_csv, generate_excel

logger = logging.getLogger(__name__)

# ── Shared engine for worker jobs (created once at module import) ─────────────
# Re-using a single engine avoids creating a new connection pool for every job.
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

    async def emit(status: str, progress: int, message: str) -> None:
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
                logger.error("Job %s not found in DB", job_id)
                return

            result = await db.execute(
                select(Document).where(Document.job_id == job_id)
            )
            documents = result.scalars().all()

            fields = job.fields  # [{"name": str, "description": str}]
            field_names = [f["name"] for f in fields]
            total_docs = len(documents)

            # ── Phase 1: processing ────────────────────────────────────
            job.status = "processing"
            await db.commit()
            await emit("processing", 5, f"Starting extraction of {total_docs} document(s)…")

            all_extracted: List[Dict[str, Any]] = []
            total_pages = 0

            for idx, doc in enumerate(documents):
                base_pct = 5 + int((idx / total_docs) * 65)

                await emit(
                    "extracting",
                    base_pct,
                    f"Reading {doc.filename} ({idx + 1}/{total_docs})…",
                )
                job.status = "extracting"
                await db.commit()

                try:
                    pdf_data = read_pdf_text(doc.file_path)
                    doc.page_count = pdf_data["page_count"]
                    total_pages += pdf_data["page_count"]
                    doc.status = "processing"
                    await db.commit()

                    await emit(
                        "extracting",
                        base_pct + int(0.4 * (65 / total_docs)),
                        f"AI extracting {doc.filename} ({pdf_data['page_count']} pages)…",
                    )

                    extracted = await extract_fields_from_text(
                        pdf_data["full_text"], fields, doc.filename
                    )
                    doc.extracted_data = extracted
                    doc.status = "complete"
                    all_extracted.append(extracted)
                    await db.commit()

                    await emit(
                        "extracting",
                        base_pct + int(0.8 * (65 / total_docs)),
                        f"✓ {doc.filename} done ({idx + 1}/{total_docs})",
                    )

                except Exception as exc:
                    logger.error("Error processing %s: %s", doc.filename, exc)
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

            if job.format == "csv":
                generate_csv(all_extracted, output_path, field_names)
            else:
                generate_excel(all_extracted, output_path, field_names)

            await emit("generating", 90, "Spreadsheet ready — updating credits…")

            # ── Phase 3: deduct credits ────────────────────────────────
            result = await db.execute(select(User).where(User.id == job.user_id))
            user = result.scalar_one_or_none()
            if user:
                credits_used = max(1, total_pages)
                user.credits = max(0, user.credits - credits_used)
                job.credits_used = credits_used
                await db.commit()

            # ── Mark complete ──────────────────────────────────────────
            job.status = "complete"
            job.output_path = output_path
            job.progress = 100
            await db.commit()

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
            logger.error("Fatal error in job %s: %s", job_id, exc, exc_info=True)
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
