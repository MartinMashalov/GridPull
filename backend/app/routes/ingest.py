"""
Ingest routes.

POST   /ingest/address              — Create or return user's ingest email
GET    /ingest/address              — Get ingest address
GET    /ingest/inbox                — List documents grouped by sender
POST   /ingest/inbox/extract        — Process selected docs through extraction pipeline
DELETE /ingest/inbox/{document_id}  — Delete a single ingest document
POST   /ingest/mobile-session       — Create mobile upload session (QR code)
GET    /ingest/mobile-session/{token} — Validate mobile session token
POST   /ingest/mobile-upload/{token}  — Upload file via mobile session
"""

import logging
import os
import secrets
import uuid
from collections import defaultdict
from datetime import datetime, timedelta
from typing import List, Optional

import aiofiles
from fastapi import APIRouter, Depends, Form, HTTPException, UploadFile, File
from pydantic import BaseModel
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import get_db
from app.middleware.auth_middleware import get_current_user
from app.models.extraction import Document, ExtractionJob
from app.models.ingest import IngestAddress, IngestDocument, MobileUploadSession
from app.models.user import User
from app.services.ingest.email_parser import get_group_key
from app.services.ingest.s3_service import (
    delete_file as delete_from_s3,
    download_file as download_from_s3,
    upload_file as upload_to_s3,
)
from app.services.subscription_tiers import MAX_PAGES_PER_CREDIT, get_tier
from app.workers.job_processor import process_job
from app.workers.pool import worker_pool

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/ingest", tags=["ingest"])


# ── Schemas ────────────────────────────────────────────────────────────────────

class ExtractRequest(BaseModel):
    document_ids: List[str]
    fields: List[dict]
    instructions: str = ""
    format: str = "xlsx"


# ── Address Management ─────────────────────────────────────────────────────────

@router.post("/address")
async def create_or_get_address(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Create or return the user's unique ingest email address."""
    result = await db.execute(
        select(IngestAddress).where(IngestAddress.user_id == user.id)
    )
    existing = result.scalar_one_or_none()
    if not existing:
        # Generate unique key (kept for backward compat / future per-user routing)
        for _ in range(20):
            key = secrets.token_urlsafe(4)[:6].lower()
            dup = await db.execute(
                select(IngestAddress.id).where(IngestAddress.address_key == key)
            )
            if not dup.scalar_one_or_none():
                break
        else:
            raise HTTPException(status_code=500, detail="Could not generate unique address")

        existing = IngestAddress(user_id=user.id, address_key=key)
        db.add(existing)
        user.ingest_address_key = key
        await db.commit()

    return {
        "address": settings.ingest_universal_email,
        "address_key": existing.address_key,
    }


@router.get("/address")
async def get_address(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get the user's ingest address."""
    result = await db.execute(
        select(IngestAddress).where(IngestAddress.user_id == user.id)
    )
    existing = result.scalar_one_or_none()
    if not existing:
        raise HTTPException(status_code=404, detail="No ingest address configured")
    return {
        "address": settings.ingest_universal_email,
        "address_key": existing.address_key,
    }


# ── Inbox ──────────────────────────────────────────────────────────────────────

@router.get("/inbox")
async def list_inbox(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List non-expired, unassigned ingest documents grouped by sender."""
    now = datetime.utcnow()
    result = await db.execute(
        select(IngestDocument)
        .where(
            IngestDocument.user_id == user.id,
            IngestDocument.expires_at > now,
            IngestDocument.job_id.is_(None),
        )
        .order_by(IngestDocument.created_at.desc())
    )
    docs = result.scalars().all()

    groups: dict[str, list] = defaultdict(list)
    for doc in docs:
        key = get_group_key(doc.sender_email)
        groups[key].append({
            "id": doc.id,
            "filename": doc.filename,
            "sender_email": doc.sender_email,
            "subject": doc.subject,
            "file_size": doc.file_size,
            "content_type": doc.content_type,
            "created_at": doc.created_at.isoformat() if doc.created_at else None,
            "expires_at": doc.expires_at.isoformat() if doc.expires_at else None,
        })

    group_list = []
    for key, doc_list in groups.items():
        group_list.append({
            "key": key,
            "sender_display": key,
            "documents": doc_list,
            "count": len(doc_list),
            "latest_at": doc_list[0]["created_at"] if doc_list else None,
        })

    # Sort groups by most recent document
    group_list.sort(key=lambda g: g["latest_at"] or "", reverse=True)

    return {"groups": group_list, "total_documents": len(docs)}


# ── Extract from Inbox ─────────────────────────────────────────────────────────

@router.post("/inbox/extract")
async def extract_from_inbox(
    body: ExtractRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Download selected ingest docs from S3, create an extraction job,
    and process through the existing pipeline.
    """
    from app.routes.payments import _maybe_reset_usage

    if not body.document_ids:
        raise HTTPException(status_code=400, detail="No documents selected")
    if not body.fields:
        raise HTTPException(status_code=400, detail="No fields specified")

    # Fetch the ingest documents
    result = await db.execute(
        select(IngestDocument).where(
            IngestDocument.id.in_(body.document_ids),
            IngestDocument.user_id == user.id,
            IngestDocument.job_id.is_(None),
        )
    )
    ingest_docs = result.scalars().all()
    if not ingest_docs:
        raise HTTPException(status_code=404, detail="No available documents found")

    # Credit check
    _maybe_reset_usage(user)
    await db.commit()
    await db.refresh(user)

    tier = get_tier(getattr(user, "subscription_tier", "free") or "free")
    used = user.credits_used_this_period or 0
    num_credits = len(ingest_docs)  # 1 credit per document (simplified)

    if tier.name == "free" and used + num_credits > tier.credits_per_month:
        raise HTTPException(
            status_code=402,
            detail={
                "type": "credit_limit_reached",
                "message": f"Free plan allows {tier.credits_per_month} credits/month. You've used {used}.",
                "credits_used": used,
                "credits_limit": tier.credits_per_month,
                "tier": tier.name,
            },
        )

    overage_count = max(0, (used + num_credits) - tier.credits_per_month)

    # Create extraction job
    job = ExtractionJob(
        user_id=user.id,
        status="queued",
        fields=body.fields,
        instructions=body.instructions.strip() or None,
        format=body.format,
        file_count=len(ingest_docs),
    )
    db.add(job)
    await db.commit()
    await db.refresh(job)

    user.credits_used_this_period = (user.credits_used_this_period or 0) + num_credits
    if overage_count > 0:
        user.overage_credits_this_period = (user.overage_credits_this_period or 0) + overage_count
    await db.commit()

    # Download from S3 and save locally for the extraction pipeline
    upload_dir = os.path.join(settings.upload_dir, job.id)
    os.makedirs(upload_dir, exist_ok=True)
    expires_at = datetime.utcnow() + timedelta(days=7)

    for idoc in ingest_docs:
        try:
            data = await download_from_s3(idoc.s3_key)
        except Exception:
            logger.error("Failed to download S3 key %s", idoc.s3_key, exc_info=True)
            continue

        local_path = os.path.join(upload_dir, idoc.filename)
        async with aiofiles.open(local_path, "wb") as fh:
            await fh.write(data)

        db.add(Document(job_id=job.id, filename=idoc.filename, file_path=local_path))

        # Mark ingest doc as assigned
        idoc.job_id = job.id
        idoc.expires_at = expires_at

    await db.commit()

    # Enqueue for processing
    await worker_pool.submit(process_job, job.id, worker_pool.broadcast)
    logger.info("Ingest extract: job=%s docs=%d user=%s", job.id, len(ingest_docs), user.id)

    return {
        "job_id": job.id,
        "status": "queued",
        "usage": {
            "credits_used": user.credits_used_this_period,
            "credits_limit": tier.credits_per_month,
            "tier": tier.name,
        },
    }


# ── Direct Upload to Inbox ────────────────────────────────────────────────

@router.post("/inbox/upload")
async def upload_to_inbox(
    files: List[UploadFile] = File(...),
    sender_email: str = Form(""),
    sender_domain: str = Form(""),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Upload files directly into the user's inbox, optionally into a specific group."""
    from app.services.ingest.email_parser import extract_domain

    target_sender = sender_email.strip() or "direct-upload"
    target_domain = sender_domain.strip() or (extract_domain(target_sender) if "@" in target_sender else "upload")

    max_bytes = settings.max_file_size_mb * 1024 * 1024
    uploaded = []

    for file in files:
        content = await file.read()
        if not content:
            continue
        if len(content) > max_bytes:
            continue

        doc_id = str(uuid.uuid4())
        filename = file.filename or f"upload-{doc_id}"
        content_type = file.content_type or "application/octet-stream"

        s3_key = await upload_to_s3(
            user_id=user.id,
            doc_id=doc_id,
            filename=filename,
            data=content,
            content_type=content_type,
        )

        expires_at = datetime.utcnow() + timedelta(days=7)
        doc = IngestDocument(
            id=doc_id,
            user_id=user.id,
            sender_email=target_sender,
            sender_domain=target_domain,
            subject="Direct Upload",
            message_id=f"upload-{doc_id}",
            filename=filename,
            s3_key=s3_key,
            file_size=len(content),
            content_type=content_type,
            expires_at=expires_at,
        )
        db.add(doc)
        uploaded.append({"id": doc_id, "filename": filename})

    await db.commit()
    return {"uploaded": uploaded, "count": len(uploaded)}


# ── Delete ─────────────────────────────────────────────────────────────────────

@router.delete("/inbox/{document_id}")
async def delete_ingest_document(
    document_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Delete a single ingest document from S3 and DB."""
    result = await db.execute(
        select(IngestDocument).where(
            IngestDocument.id == document_id,
            IngestDocument.user_id == user.id,
        )
    )
    doc = result.scalar_one_or_none()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")

    try:
        await delete_from_s3(doc.s3_key)
    except Exception:
        logger.error("Failed to delete S3 key %s", doc.s3_key, exc_info=True)

    await db.delete(doc)
    await db.commit()
    return {"status": "deleted"}


# ── Mobile Upload Session ──────────────────────────────────────────────────────

class MobileSessionRequest(BaseModel):
    sender_email: str = ""
    sender_domain: str = ""


@router.post("/mobile-session")
async def create_mobile_session(
    body: MobileSessionRequest = MobileSessionRequest(),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Create a short-lived token for QR code mobile upload, optionally scoped to a group."""
    token = secrets.token_urlsafe(16)
    expires_at = datetime.utcnow() + timedelta(hours=1)

    session = MobileUploadSession(
        user_id=user.id,
        token=token,
        group_sender_email=body.sender_email or None,
        group_sender_domain=body.sender_domain or None,
        expires_at=expires_at,
    )
    db.add(session)
    await db.commit()

    frontend_url = settings.frontend_url.rstrip("/")
    return {
        "token": token,
        "url": f"{frontend_url}/upload/{token}",
        "expires_at": expires_at.isoformat(),
    }


@router.get("/mobile-session/{token}")
async def validate_mobile_session(
    token: str,
    db: AsyncSession = Depends(get_db),
):
    """Validate a mobile upload token (no auth required)."""
    result = await db.execute(
        select(MobileUploadSession).where(MobileUploadSession.token == token)
    )
    session = result.scalar_one_or_none()
    if not session:
        raise HTTPException(status_code=404, detail="Invalid token")

    now = datetime.utcnow()
    expires = session.expires_at
    if expires.tzinfo is None:
        expires = expires.replace(tzinfo=None)
    if expires < now:
        raise HTTPException(status_code=410, detail="Token expired")

    return {"valid": True, "user_id": session.user_id}


@router.post("/mobile-upload/{token}")
async def mobile_upload(
    token: str,
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
):
    """Upload a file via mobile session token (no auth required)."""
    # Validate token
    result = await db.execute(
        select(MobileUploadSession).where(MobileUploadSession.token == token)
    )
    session = result.scalar_one_or_none()
    if not session:
        raise HTTPException(status_code=404, detail="Invalid token")

    now = datetime.utcnow()
    expires = session.expires_at
    if expires.tzinfo is None:
        expires = expires.replace(tzinfo=None)
    if expires < now:
        raise HTTPException(status_code=410, detail="Token expired")

    content = await file.read()
    if not content:
        raise HTTPException(status_code=400, detail="Empty file")

    max_bytes = settings.max_file_size_mb * 1024 * 1024
    if len(content) > max_bytes:
        raise HTTPException(
            status_code=413,
            detail=f"File exceeds {settings.max_file_size_mb} MB limit",
        )

    doc_id = str(uuid.uuid4())
    filename = file.filename or f"mobile-{doc_id}.jpg"
    content_type = file.content_type or "application/octet-stream"

    s3_key = await upload_to_s3(
        user_id=session.user_id,
        doc_id=doc_id,
        filename=filename,
        data=content,
        content_type=content_type,
    )

    expires_at = datetime.utcnow() + timedelta(days=7)
    msg_id = f"mobile-{doc_id}"

    doc = IngestDocument(
        id=doc_id,
        user_id=session.user_id,
        sender_email=session.group_sender_email or "mobile-upload",
        sender_domain=session.group_sender_domain or "mobile",
        subject="Mobile Upload",
        message_id=msg_id,
        filename=filename,
        s3_key=s3_key,
        file_size=len(content),
        content_type=content_type,
        expires_at=expires_at,
    )
    db.add(doc)
    await db.commit()

    return {"id": doc_id, "filename": filename, "status": "uploaded"}
