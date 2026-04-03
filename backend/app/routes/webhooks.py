"""
Webhook routes.

POST /webhooks/email-ingest  — Receive inbound email, extract attachments, store in S3
"""

import base64
import logging
import uuid
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import AsyncSessionLocal
from app.models.ingest import IngestDocument
from app.models.user import User
from app.services.ingest.email_parser import (
    Attachment,
    extract_domain,
    parse_inbound_email,
)
from app.services.ingest.s3_service import upload_file as upload_to_s3

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/webhooks", tags=["webhooks"])


class AttachmentPayload(BaseModel):
    filename: str
    content_type: str = "application/octet-stream"
    data_base64: str


class EmailIngestPayload(BaseModel):
    recipient: str
    sender: str
    subject: str = ""
    body_plain: str = ""
    body_html: str = ""
    message_id: str = ""
    attachments: list[AttachmentPayload] = []


@router.post("/email-ingest")
async def email_ingest(payload: EmailIngestPayload):
    """Receive an inbound email, extract attachments, store in S3."""
    # Extract address_key from recipient (intake-{key}@domain)
    local_part = payload.recipient.split("@")[0] if "@" in payload.recipient else payload.recipient
    if not local_part.startswith("intake-"):
        return {"status": "ignored", "reason": "unknown recipient format"}
    address_key = local_part[len("intake-"):]

    if not address_key:
        return {"status": "ignored", "reason": "empty address key"}

    async with AsyncSessionLocal() as db:
        # Look up user by ingest_address_key
        result = await db.execute(
            select(User).where(User.ingest_address_key == address_key)
        )
        user = result.scalar_one_or_none()
        if not user:
            logger.info("Email ingest: no user for address_key=%s", address_key)
            return {"status": "ignored", "reason": "unknown recipient"}

        # Dedup by message_id
        msg_id = payload.message_id or str(uuid.uuid4())
        existing = await db.execute(
            select(IngestDocument.id).where(
                IngestDocument.user_id == user.id,
                IngestDocument.message_id == msg_id,
            ).limit(1)
        )
        if existing.scalar_one_or_none():
            logger.info("Email ingest: duplicate message_id=%s for user=%s", msg_id, user.id)
            return {"status": "duplicate"}

        # Decode attachments
        raw_attachments = []
        for att in payload.attachments:
            try:
                data = base64.b64decode(att.data_base64)
            except Exception:
                logger.warning("Failed to decode attachment %s", att.filename)
                continue
            raw_attachments.append(Attachment(
                filename=att.filename,
                data=data,
                content_type=att.content_type,
            ))

        # Parse and expand nested .msg/.eml
        parsed = parse_inbound_email(
            sender=payload.sender,
            subject=payload.subject,
            body_plain=payload.body_plain,
            body_html=payload.body_html,
            attachments=raw_attachments,
        )

        if not parsed.attachments:
            logger.info("Email ingest: no attachments from %s", parsed.sender_email)
            return {"status": "ok", "documents": 0}

        expires_at = datetime.now(timezone.utc) + timedelta(days=7)
        doc_count = 0

        for att in parsed.attachments:
            doc_id = str(uuid.uuid4())
            s3_key = await upload_to_s3(
                user_id=user.id,
                doc_id=doc_id,
                filename=att.filename,
                data=att.data,
                content_type=att.content_type,
            )
            db.add(IngestDocument(
                id=doc_id,
                user_id=user.id,
                sender_email=parsed.sender_email,
                sender_domain=parsed.sender_domain,
                subject=parsed.subject,
                message_id=msg_id,
                filename=att.filename,
                s3_key=s3_key,
                file_size=len(att.data),
                content_type=att.content_type,
                expires_at=expires_at,
            ))
            doc_count += 1

        await db.commit()
        logger.info(
            "Email ingest: stored %d docs from %s for user=%s",
            doc_count, parsed.sender_email, user.id,
        )
        return {"status": "ok", "documents": doc_count}
