"""
Job processor: runs inside the worker pool.

Responsibilities:
1. Read each PDF with PyMuPDF
2. Call LiteLLM-backed extraction (extraction_service)
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
from app.services.billing_service import maybe_auto_renew
from app.services.extraction_service import LLMUsage, extract_from_document
from app.services.pdf_service import parse_pdf
from app.services.spreadsheet_service import (
    generate_csv,
    generate_excel,
    update_csv_baseline_bytes,
    update_excel_baseline_bytes,
)

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
        logger.info(
            "Job %s progress — status=%s progress=%d%% completed=%s/%s msg=%s",
            job_id, status, progress, completed_docs, total_docs_count, message,
        )
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
            instructions = (job.instructions or "").strip()
            use_cerebras = bool(getattr(job, "use_cerebras", False))
            pipeline = str(getattr(job, "pipeline", "auto") or "auto")
            force_sov = pipeline == "sov"
            force_general = pipeline == "general"
            field_names = [f["name"] for f in fields]
            total_docs = len(documents)

            logger.info(
                "Job %s — user_id=%s docs=%d fields=%s format=%s instructions=%d chars",
                job_id, job.user_id, total_docs, field_names, job.format, len(instructions),
            )

            # ── Phase 1: processing ────────────────────────────────────
            job.status = "processing"
            job.progress = 5
            await db.commit()
            await emit("processing", 5, f"Starting extraction of {total_docs} document(s)…", 0, total_docs)

            all_extracted: List[Dict[str, Any]] = []
            total_pages = 0
            job_usage = LLMUsage()
            completed_count = 0

            if force_sov and total_docs > 1:
                # ── SOV multi-doc: parse all in parallel, combine into one document,
                #    then run a single extraction pass so the LLM sees all content
                #    at once and naturally produces one unified row per location. ──
                from app.services.pdf_service import combine_parsed_documents

                parsed_by_idx: dict[int, Any] = {}
                parse_sem = asyncio.Semaphore(6)

                async def _parse_only(idx: int, doc_id: str, filename: str, file_path: str) -> None:
                    nonlocal total_pages, completed_count
                    async with parse_sem:
                        async with _WorkerSession() as doc_db:
                            doc_res = await doc_db.execute(select(Document).where(Document.id == doc_id))
                            doc_obj = doc_res.scalar_one()
                            try:
                                pct = 5 + int(((idx + 1) / total_docs) * 30)
                                await emit("extracting", pct, f"Reading {idx + 1}/{total_docs}: {filename}", idx, total_docs)
                                parsed = await asyncio.to_thread(parse_pdf, file_path, filename)
                                doc_obj.page_count = parsed.page_count
                                doc_obj.status = "processing"
                                total_pages += parsed.page_count

                                # Replace PyMuPDF text with Mistral OCR text for each file so
                                # the combined doc gets OCR-quality content, not raw parser text.
                                # Same routing as the single-doc SOV path: skip emails/spreadsheets.
                                _NO_OCR_EXTS = {".eml", ".emlx", ".msg", ".html", ".htm"}
                                _SHEET_EXTS = {".xlsx", ".xls", ".xlsm", ".csv"}
                                fname_lower = filename.lower()
                                if (
                                    settings.mistral_api_key
                                    and file_path
                                    and not any(fname_lower.endswith(e) for e in _NO_OCR_EXTS)
                                    and not any(fname_lower.endswith(e) for e in _SHEET_EXTS)
                                ):
                                    try:
                                        from app.services.ocr_service import run_mistral_ocr
                                        ocr_res = await run_mistral_ocr(
                                            file_path, settings.mistral_api_key, max_pages=50
                                        )
                                        from app.services.sov.pipeline import _build_sections_from_ocr_pages
                                        sections = _build_sections_from_ocr_pages(ocr_res.pages)
                                        ocr_text = "\n\n".join(s.content for s in sections).strip()
                                        if ocr_text:
                                            parsed.content_text = ocr_text
                                            logger.info(
                                                "Job %s — pre-combine OCR %s: %d pages → %d chars",
                                                job_id, filename, ocr_res.page_count, len(ocr_text),
                                            )
                                    except Exception as ocr_exc:
                                        logger.warning(
                                            "Job %s — pre-combine OCR failed for %s: %s (using liteparse text)",
                                            job_id, filename, ocr_exc,
                                        )

                                completed_count += 1
                                parsed_by_idx[idx] = parsed
                                logger.info("Job %s — parsed %s: %d pages type=%s", job_id, filename, parsed.page_count, parsed.doc_type_hint)
                                await doc_db.commit()
                            except Exception as exc:
                                logger.error("Job %s — parse failed %s: %s", job_id, filename, exc)
                                doc_obj.status = "error"
                                await doc_db.commit()
                                parsed_by_idx[idx] = None

                job.status = "extracting"
                job.progress = 5
                await db.commit()
                await emit("extracting", 5, f"Reading {total_docs} documents…", 0, total_docs)
                await asyncio.gather(*[
                    _parse_only(i, doc.id, doc.filename, doc.file_path)
                    for i, doc in enumerate(documents)
                ])

                valid_parsed = [parsed_by_idx[i] for i in range(total_docs) if parsed_by_idx.get(i) is not None]
                if not valid_parsed:
                    raise RuntimeError("All documents failed to parse")

                combined_doc = combine_parsed_documents(valid_parsed)
                logger.info(
                    "Job %s — combined %d docs into one: %d pages %d tables",
                    job_id, len(valid_parsed), combined_doc.page_count, len(combined_doc.tables),
                )

                await emit("extracting", 40, f"Extracting from all {total_docs} documents combined…", total_docs, total_docs)

                doc_usage = LLMUsage()
                all_extracted = await asyncio.wait_for(
                    extract_from_document(
                        combined_doc, fields, doc_usage, instructions,
                        batch_document_count=1,
                        use_cerebras=False,
                        force_sov=True,
                        force_general=False,
                    ),
                    timeout=settings.extraction_timeout_seconds,
                )
                job_usage.litellm_cost_usd += doc_usage.litellm_cost_usd
                job_usage.input_tokens += doc_usage.input_tokens
                job_usage.output_tokens += doc_usage.output_tokens
                job_usage.cleanup_input_tokens += doc_usage.cleanup_input_tokens
                job_usage.cleanup_output_tokens += doc_usage.cleanup_output_tokens
                job_usage.ocr_cost_usd += doc_usage.ocr_cost_usd

                # Mark all docs complete and store the combined rows on each
                for doc in documents:
                    async with _WorkerSession() as doc_db:
                        doc_res = await doc_db.execute(select(Document).where(Document.id == doc.id))
                        doc_obj = doc_res.scalar_one()
                        doc_obj.extracted_data = all_extracted
                        doc_obj.status = "complete"
                        await doc_db.commit()

                filled = sum(1 for r in all_extracted for k, v in r.items() if k not in ("_source_file","_error") and v not in (None,""))
                logger.info(
                    "Job %s — SOV combined extraction: rows=%d filled=%d cost=$%.6f",
                    job_id, len(all_extracted), filled, doc_usage.cost_usd,
                )
                await emit("extracting", 70, f"✓ Extracted {len(all_extracted)} rows from {total_docs} documents", total_docs, total_docs)

            else:
                # ── Standard path: extract each document independently in parallel ──
                results_ordered: List[List[Dict[str, Any]]] = [[] for _ in range(total_docs)]
                sem = asyncio.Semaphore(6)

                async def _process_doc(idx: int, doc_id: str, filename: str, file_path: str) -> None:
                    nonlocal total_pages, completed_count
                    async with sem:
                        doc_start = time.monotonic()
                        logger.info("Job %s — processing doc %d/%d: %s", job_id, idx + 1, total_docs, filename)
                        pct_start = 5 + int((idx / total_docs) * 65)
                        async with _WorkerSession() as doc_db:
                            doc_res = await doc_db.execute(select(Document).where(Document.id == doc_id))
                            doc_obj = doc_res.scalar_one()
                            try:
                                job_res2 = await doc_db.execute(select(ExtractionJob).where(ExtractionJob.id == job_id))
                                job_rec = job_res2.scalar_one_or_none()
                                if job_rec:
                                    job_rec.status = "extracting"
                                    job_rec.progress = pct_start
                                    job_rec.completed_docs = completed_count
                                    await doc_db.commit()
                                await emit("extracting", pct_start, f"Processing {idx + 1}/{total_docs}: {filename}", completed_count, total_docs)

                                parsed_doc = await asyncio.to_thread(parse_pdf, file_path, filename)
                                doc_obj.page_count = parsed_doc.page_count
                                total_pages += parsed_doc.page_count
                                doc_obj.status = "processing"
                                await doc_db.commit()
                                logger.info("Job %s — parsed %s: %d pages, type=%s", job_id, filename, parsed_doc.page_count, getattr(parsed_doc, "doc_type_hint", "unknown"))

                                doc_usage = LLMUsage()
                                rows = await asyncio.wait_for(
                                    extract_from_document(parsed_doc, fields, doc_usage, instructions, batch_document_count=total_docs, use_cerebras=use_cerebras, force_sov=force_sov, force_general=force_general),
                                    timeout=settings.extraction_timeout_seconds,
                                )
                                job_usage.litellm_cost_usd += doc_usage.litellm_cost_usd
                                job_usage.input_tokens += doc_usage.input_tokens
                                job_usage.output_tokens += doc_usage.output_tokens
                                job_usage.vision_input_tokens += doc_usage.vision_input_tokens
                                job_usage.vision_output_tokens += doc_usage.vision_output_tokens
                                job_usage.cleanup_input_tokens += doc_usage.cleanup_input_tokens
                                job_usage.cleanup_output_tokens += doc_usage.cleanup_output_tokens
                                job_usage.ocr_cost_usd += doc_usage.ocr_cost_usd
                                job_usage.bear_removed_tokens += doc_usage.bear_removed_tokens
                                job_usage.bear_latency_ms += doc_usage.bear_latency_ms
                                job_usage.bear_cache.update(doc_usage.bear_cache)
                                doc_obj.extracted_data = rows
                                doc_obj.status = "complete"
                                results_ordered[idx] = rows
                                await doc_db.commit()

                                completed_count += 1
                                doc_elapsed = (time.monotonic() - doc_start) * 1000
                                error_rows = sum(1 for r in rows if r.get("_error"))
                                filled = sum(1 for r in rows for k, v in r.items() if k not in ("_source_file", "_error") and v not in (None, ""))
                                total_cells = len(rows) * len(field_names)
                                logger.info("Job %s — extracted %s: rows=%d filled_cells=%d/%d error_rows=%d in %.0fms doc_cost=$%.6f job_total=$%.6f", job_id, filename, len(rows), filled, total_cells, error_rows, doc_elapsed, doc_usage.cost_usd, job_usage.cost_usd)
                                pct = 5 + int((completed_count / total_docs) * 65)
                                job_res2 = await doc_db.execute(select(ExtractionJob).where(ExtractionJob.id == job_id))
                                job_rec = job_res2.scalar_one_or_none()
                                if job_rec:
                                    job_rec.status = "extracting"
                                    job_rec.progress = pct
                                    job_rec.completed_docs = completed_count
                                    await doc_db.commit()
                                await emit("extracting", pct, f"✓ {filename} done ({completed_count}/{total_docs})", completed_count, total_docs)

                            except asyncio.TimeoutError:
                                exc_msg = f"Extraction timed out after {int(settings.extraction_timeout_seconds)}s"
                                logger.error("Job %s — timeout processing %s", job_id, filename)
                                doc_obj.status = "error"
                                row = {f: "" for f in field_names}
                                row["_source_file"] = filename
                                row["_error"] = exc_msg
                                results_ordered[idx] = [row]
                                completed_count += 1
                                job_res2 = await doc_db.execute(select(ExtractionJob).where(ExtractionJob.id == job_id))
                                job_rec = job_res2.scalar_one_or_none()
                                if job_rec:
                                    pct = 5 + int((completed_count / total_docs) * 65)
                                    job_rec.status = "extracting"
                                    job_rec.progress = pct
                                    job_rec.completed_docs = completed_count
                                await doc_db.commit()
                                await emit("extracting", pct, f"✗ {filename} timed out ({completed_count}/{total_docs})", completed_count, total_docs)
                            except Exception as exc:
                                logger.error("Job %s — error processing %s: %s", job_id, filename, exc, exc_info=True)
                                doc_obj.status = "error"
                                row: Dict[str, Any] = {f: "" for f in field_names}
                                row["_source_file"] = filename
                                row["_error"] = str(exc)
                                results_ordered[idx] = [row]
                                completed_count += 1
                                job_res2 = await doc_db.execute(select(ExtractionJob).where(ExtractionJob.id == job_id))
                                job_rec = job_res2.scalar_one_or_none()
                                if job_rec:
                                    pct = 5 + int((completed_count / total_docs) * 65)
                                    job_rec.status = "extracting"
                                    job_rec.progress = pct
                                    job_rec.completed_docs = completed_count
                                await doc_db.commit()
                                await emit("extracting", pct, f"✗ {filename} failed ({completed_count}/{total_docs})", completed_count, total_docs)

                job.status = "extracting"
                job.progress = 5
                await db.commit()
                await emit("extracting", 5, f"Extracting {total_docs} document(s) in parallel…", 0, total_docs)
                await asyncio.gather(*[_process_doc(i, doc.id, doc.filename, doc.file_path) for i, doc in enumerate(documents)])
                for slot in results_ordered:
                    all_extracted.extend(slot)

            # ── Phase 2: generate spreadsheet ─────────────────────────
            job.status = "generating"
            job.progress = 75
            await db.commit()
            await emit("generating", 75, "Generating spreadsheet…", total_docs, total_docs)

            if job.baseline_update_mode:
                baseline_path = os.path.join(settings.upload_dir, job_id, f"baseline.{job.format}")
                if not os.path.exists(baseline_path):
                    raise RuntimeError("Baseline spreadsheet file not found for editable baseline job")
                output_filename = f"updated_baseline.{job.format}"
            else:
                output_filename = f"gridpull_{job_id}.{job.format}"
            output_path = os.path.join(settings.output_dir, f"{job_id}_{output_filename}")

            gen_start = time.monotonic()
            if job.baseline_update_mode:
                with open(baseline_path, "rb") as fh:
                    baseline_bytes = fh.read()
                if job.format == "csv":
                    output_bytes = await asyncio.to_thread(
                        update_csv_baseline_bytes,
                        baseline_bytes,
                        all_extracted,
                        field_names,
                        bool(job.allow_edit_past_values),
                    )
                else:
                    output_bytes = await asyncio.to_thread(
                        update_excel_baseline_bytes,
                        baseline_bytes,
                        all_extracted,
                        field_names,
                        bool(job.allow_edit_past_values),
                    )
                with open(output_path, "wb") as fh:
                    fh.write(output_bytes)
            elif job.format == "csv":
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
            job.progress = 90
            await db.commit()

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
                await maybe_auto_renew(user, db)

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
                    "baseline_update_mode": bool(job.baseline_update_mode),
                    "output_filename": output_filename,
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
