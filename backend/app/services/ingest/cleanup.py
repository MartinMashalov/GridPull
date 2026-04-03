"""Cleanup expired ingest documents and mobile upload sessions."""

import logging
from datetime import datetime, timezone

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.ingest import IngestDocument, MobileUploadSession
from app.services.ingest.s3_service import delete_many_files as delete_many_from_s3

logger = logging.getLogger(__name__)


async def cleanup_expired_documents(session: AsyncSession) -> int:
    """Delete expired ingest documents from S3 and DB. Returns count deleted."""
    now = datetime.now(timezone.utc)

    # Find expired documents not yet assigned to a job
    result = await session.execute(
        select(IngestDocument).where(
            IngestDocument.expires_at < now,
            IngestDocument.job_id.is_(None),
        )
    )
    expired_docs = result.scalars().all()

    if not expired_docs:
        # Still clean up expired mobile sessions
        await session.execute(
            delete(MobileUploadSession).where(MobileUploadSession.expires_at < now)
        )
        await session.commit()
        return 0

    s3_keys = [doc.s3_key for doc in expired_docs]
    doc_ids = [doc.id for doc in expired_docs]

    # Delete from S3
    try:
        await delete_many_from_s3(s3_keys)
    except Exception:
        logger.error("Failed to batch-delete S3 objects during cleanup", exc_info=True)

    # Delete from DB
    await session.execute(
        delete(IngestDocument).where(IngestDocument.id.in_(doc_ids))
    )

    # Also clean expired mobile sessions
    await session.execute(
        delete(MobileUploadSession).where(MobileUploadSession.expires_at < now)
    )

    await session.commit()
    logger.info("Cleanup: deleted %d expired ingest documents", len(doc_ids))
    return len(doc_ids)
