"""
Pipeline Poller — background asyncio task.

Wakes every 5 minutes and checks every active pipeline for new PDFs.
Each pipeline writes all extracted rows to ONE fixed output file
(named after the pipeline). Subsequent runs append to that file rather
than creating new ones.
"""

from __future__ import annotations

import asyncio
import logging
import os
import re
import tempfile
from datetime import datetime
from typing import List

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.config import settings
from app.models.pipeline import OAuthConnection, Pipeline, PipelineRun
from app.models.user import User
from app.services.extraction_service import LLMUsage, extract_from_document
from app.services.pdf_service import parse_pdf
from app.services.spreadsheet_service import (
    append_to_csv_bytes,
    append_to_excel_bytes,
    generate_csv_bytes,
    generate_excel_bytes,
)

logger = logging.getLogger(__name__)

# ── Shared engine ──────────────────────────────────────────────────────────────
_is_postgres = settings.database_url.startswith("postgresql")

if _is_postgres:
    _poller_engine = create_async_engine(
        settings.database_url,
        pool_size=5,
        max_overflow=5,
        pool_recycle=1800,
        pool_pre_ping=True,
        connect_args={
            "prepared_statement_cache_size": 0,
            "statement_cache_size": 0,
        },
    )
else:
    _poller_engine = create_async_engine(
        settings.database_url,
        connect_args={"check_same_thread": False},
    )

_PollerSession = async_sessionmaker(
    _poller_engine, class_=AsyncSession, expire_on_commit=False
)

_POLL_INTERVAL = 120   # 2 minutes
_STARTUP_DELAY = 10    # 10 second grace at startup


# ── Filename helper ────────────────────────────────────────────────────────────

def _output_filename(pipeline: Pipeline) -> str:
    """Derive a stable output filename from the pipeline name + format.
    e.g.  "My Invoice Pipeline"  →  "My Invoice Pipeline.xlsx"
    """
    safe = re.sub(r'[<>:"/\\|?*]', "_", pipeline.name).strip()
    return f"{safe}.{pipeline.dest_format}"


def _oauth_provider(source_type: str) -> str:
    """Outlook uses the same Microsoft OAuth connection as SharePoint."""
    return "sharepoint" if source_type == "outlook" else source_type


def _storage_provider(source_type: str) -> str:
    """Outlook destinations live in OneDrive — use sharepoint upload helpers."""
    return "sharepoint" if source_type == "outlook" else source_type


# ── Public entry point ─────────────────────────────────────────────────────────

async def start_pipeline_poller() -> None:
    """Long-running coroutine — started once from lifespan."""
    logger.info("Pipeline poller starting (delay=%ds, interval=%ds)", _STARTUP_DELAY, _POLL_INTERVAL)
    await asyncio.sleep(_STARTUP_DELAY)
    while True:
        try:
            await _poll_all()
        except Exception:
            logger.exception("Pipeline poller top-level error — will retry next cycle")
        await asyncio.sleep(_POLL_INTERVAL)


# ── Internal helpers ───────────────────────────────────────────────────────────

async def _poll_all() -> None:
    async with _PollerSession() as db:
        result = await db.execute(select(Pipeline).where(Pipeline.status == "active"))
        pipelines: List[Pipeline] = result.scalars().all()

    logger.debug("Pipeline poller — %d active pipeline(s)", len(pipelines))
    for pipeline in pipelines:
        try:
            await _check_pipeline(pipeline)
        except Exception:
            logger.exception("Pipeline %s check failed — marking error", pipeline.id)
            async with _PollerSession() as db:
                result = await db.execute(select(Pipeline).where(Pipeline.id == pipeline.id))
                p = result.scalar_one_or_none()
                if p:
                    p.status = "error"
                    await db.commit()


async def _check_pipeline(pipeline: Pipeline) -> None:
    async with _PollerSession() as db:
        result = await db.execute(select(Pipeline).where(Pipeline.id == pipeline.id))
        p: Pipeline | None = result.scalar_one_or_none()
        if not p or p.status != "active":
            return

        oauth_prov = _oauth_provider(p.source_type)
        conn_result = await db.execute(
            select(OAuthConnection).where(
                OAuthConnection.user_id == p.user_id,
                OAuthConnection.provider == oauth_prov,
            )
        )
        conn: OAuthConnection | None = conn_result.scalar_one_or_none()
        if not conn:
            logger.warning("Pipeline %s: no OAuth connection for %s", p.id, oauth_prov)
            return

        await _ensure_fresh_token(conn, db, oauth_prov)
        source_config = p.source_config or {}
        pdfs = await _list_pdfs(conn.access_token, p.source_folder_id, p.source_type, source_config)
        processed_ids: list = list(p.processed_file_ids or [])
        new_pdfs = [f for f in pdfs if f["id"] not in processed_ids]

        if not new_pdfs:
            p.last_checked_at = datetime.utcnow()
            await db.commit()
            return

        logger.info("Pipeline %s: %d new PDF(s) to process", p.id, len(new_pdfs))

    for file_info in new_pdfs:
        await _process_file(pipeline.id, file_info)

    async with _PollerSession() as db:
        result = await db.execute(select(Pipeline).where(Pipeline.id == pipeline.id))
        p = result.scalar_one_or_none()
        if p:
            p.last_checked_at = datetime.utcnow()
            await db.commit()


async def _process_file(pipeline_id: str, file_info: dict) -> None:
    """Download → extract → append to pipeline output file → upload."""
    # ── Load pipeline + connection ─────────────────────────────────────────
    async with _PollerSession() as db:
        result = await db.execute(select(Pipeline).where(Pipeline.id == pipeline_id))
        pipeline: Pipeline | None = result.scalar_one_or_none()
        if not pipeline:
            return

        oauth_prov = _oauth_provider(pipeline.source_type)
        conn_result = await db.execute(
            select(OAuthConnection).where(
                OAuthConnection.user_id == pipeline.user_id,
                OAuthConnection.provider == oauth_prov,
            )
        )
        conn = conn_result.scalar_one_or_none()
        if not conn:
            return

        run = PipelineRun(
            pipeline_id=pipeline.id,
            user_id=pipeline.user_id,
            status="running",
            source_file_name=file_info["name"],
            source_file_id=file_info["id"],
        )
        db.add(run)
        await db.commit()
        await db.refresh(run)

        run_id = run.id
        fields = pipeline.fields
        dest_folder_id = pipeline.dest_folder_id
        dest_format = pipeline.dest_format
        source_type = pipeline.source_type
        source_config = pipeline.source_config or {}
        access_token = conn.access_token
        output_filename = _output_filename(pipeline)

    storage = _storage_provider(source_type)
    logger.info("Pipeline %s: processing %s → %s (run=%s)", pipeline_id, file_info["name"], output_filename, run_id)

    tmp_path: str | None = None
    try:
        # ── Download source PDF ────────────────────────────────────────────
        pdf_bytes = await _download_file(access_token, file_info["id"], source_type, file_info)
        with tempfile.NamedTemporaryFile(delete=False, suffix=f"_{file_info['name']}") as tmp:
            tmp.write(pdf_bytes)
            tmp_path = tmp.name

        # ── Parse + extract ────────────────────────────────────────────────
        parsed = await asyncio.to_thread(parse_pdf, tmp_path, file_info["name"])
        usage = LLMUsage()
        rows = await extract_from_document(parsed, fields, usage)
        for row in rows:
            row["_source_file"] = file_info["name"]

        field_names = [f["name"] for f in fields]

        # ── Fetch existing output file (for append) ────────────────────────
        existing_file_id, existing_bytes = await _get_existing_output(
            access_token, dest_folder_id, output_filename, storage
        )

        # ── Build output bytes (append or create) ──────────────────────────
        if dest_format == "csv":
            mime = "text/csv"
            out_bytes = (
                append_to_csv_bytes(existing_bytes, rows, field_names)
                if existing_bytes is not None
                else generate_csv_bytes(rows, field_names)
            )
        else:
            mime = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            out_bytes = (
                append_to_excel_bytes(existing_bytes, rows, field_names)
                if existing_bytes is not None
                else generate_excel_bytes(rows, field_names)
            )

        # ── Upload (create or overwrite) ───────────────────────────────────
        dest_url = await _upload_output(
            access_token, dest_folder_id, output_filename, out_bytes, storage, mime, existing_file_id
        )

        # ── Mark email as read (Outlook only) ─────────────────────────────
        if source_type == "outlook" and source_config.get("mark_as_read", True):
            msg_id = file_info.get("message_id") or file_info["id"].split(":")[0]
            try:
                from app.services.outlook_service import mark_as_read
                await mark_as_read(access_token, msg_id)
            except Exception:
                logger.warning("Pipeline %s: could not mark email %s as read", pipeline_id, msg_id)

        # ── Persist results ────────────────────────────────────────────────
        async with _PollerSession() as db:
            r = await db.get(PipelineRun, run_id)
            if r:
                r.status = "completed"
                r.dest_file_name = output_filename
                r.dest_file_url = dest_url
                r.records_extracted = len(rows)
                r.cost_usd = usage.cost_usd
                r.completed_at = datetime.utcnow()

            p_res = await db.execute(select(Pipeline).where(Pipeline.id == pipeline_id))
            p = p_res.scalar_one_or_none()
            if p:
                ids = list(p.processed_file_ids or [])
                ids.append(file_info["id"])
                p.processed_file_ids = ids
                p.files_processed = (p.files_processed or 0) + 1
                p.last_run_at = datetime.utcnow()

            user_res = await db.execute(select(User).where(User.id == pipeline.user_id))
            user = user_res.scalar_one_or_none()
            if user and usage.cost_usd > 0:
                user.balance = max(0.0, (user.balance or 0.0) - usage.cost_usd)

            await db.commit()

        logger.info(
            "Pipeline %s: done %s — %d rows appended to %s, $%.4f",
            pipeline_id, file_info["name"], len(rows), output_filename, usage.cost_usd,
        )

    except Exception as exc:
        logger.exception("Pipeline %s: failed %s", pipeline_id, file_info["name"])
        async with _PollerSession() as db:
            r = await db.get(PipelineRun, run_id)
            if r:
                r.status = "failed"
                r.error_message = str(exc)
                r.completed_at = datetime.utcnow()
            await db.commit()
    finally:
        if tmp_path and os.path.exists(tmp_path):
            os.unlink(tmp_path)


# ── Provider dispatch helpers ──────────────────────────────────────────────────

async def _ensure_fresh_token(conn: OAuthConnection, db: AsyncSession, provider: str) -> None:
    if provider == "google_drive":
        from app.services.gdrive_service import ensure_fresh_token
    else:
        from app.services.sharepoint_service import ensure_fresh_token
    await ensure_fresh_token(conn, db)


async def _list_pdfs(
    access_token: str,
    folder_id: str,
    provider: str,
    source_config: dict | None = None,
) -> list:
    if provider == "google_drive":
        from app.services.gdrive_service import list_pdfs
        return await list_pdfs(access_token, folder_id)
    elif provider == "outlook":
        from app.services.outlook_service import get_pdf_attachments, list_unread_pdf_emails
        cfg = source_config or {}
        messages = await list_unread_pdf_emails(
            access_token,
            folder_id=folder_id,
            from_filter=cfg.get("from_filter", ""),
            subject_filter=cfg.get("subject_filter", ""),
        )
        result = []
        for msg in messages:
            attachments = await get_pdf_attachments(access_token, msg["id"])
            for att in attachments:
                result.append({
                    "id": f"{msg['id']}:{att['id']}",
                    "name": att["name"],
                    "message_id": msg["id"],
                    "attachment_id": att["id"],
                })
        return result
    else:
        from app.services.sharepoint_service import list_pdfs
        return await list_pdfs(access_token, folder_id)


async def _download_file(
    access_token: str,
    file_id: str,
    provider: str,
    file_info: dict | None = None,
) -> bytes:
    if provider == "google_drive":
        from app.services.gdrive_service import download_file
        return await download_file(access_token, file_id)
    elif provider == "outlook":
        from app.services.outlook_service import download_attachment, get_attachment_bytes_inline
        if file_info and "message_id" in file_info and "attachment_id" in file_info:
            msg_id = file_info["message_id"]
            att_id = file_info["attachment_id"]
        else:
            msg_id, att_id = file_id.split(":", 1)
        try:
            return await download_attachment(access_token, msg_id, att_id)
        except Exception:
            logger.warning("Pipeline: /$value download failed, falling back to contentBytes")
            return await get_attachment_bytes_inline(access_token, msg_id, att_id)
    else:
        from app.services.sharepoint_service import download_file
        return await download_file(access_token, file_id)


async def _get_existing_output(
    access_token: str,
    folder_id: str,
    filename: str,
    provider: str,
) -> tuple[str | None, bytes | None]:
    """Return (file_id_or_none, bytes_or_none) for an existing output file."""
    if provider == "google_drive":
        from app.services.gdrive_service import find_file_by_name, download_file
        fid = await find_file_by_name(access_token, folder_id, filename)
        if fid:
            b = await download_file(access_token, fid)
            return fid, b
        return None, None
    else:
        from app.services.sharepoint_service import find_and_download_file
        b = await find_and_download_file(access_token, folder_id, filename)
        return None, b  # SharePoint uses path-based PUT, no file_id needed


async def _upload_output(
    access_token: str,
    folder_id: str,
    filename: str,
    content: bytes,
    provider: str,
    mime: str,
    existing_file_id: str | None,
) -> str:
    """Upload output file — update existing if file_id provided, else create new."""
    if provider == "google_drive":
        if existing_file_id:
            from app.services.gdrive_service import update_file_content
            return await update_file_content(access_token, existing_file_id, content, mime)
        else:
            from app.services.gdrive_service import upload_file
            return await upload_file(access_token, folder_id, filename, content, mime)
    else:
        from app.services.sharepoint_service import upload_file
        return await upload_file(access_token, folder_id, filename, content)  # PUT auto-overwrites
