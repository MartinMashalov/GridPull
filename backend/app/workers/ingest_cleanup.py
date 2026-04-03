"""Hourly background task to clean up expired ingest documents."""

import asyncio
import logging

from app.services.ingest.cleanup import cleanup_expired_documents

logger = logging.getLogger(__name__)

_CLEANUP_INTERVAL = 3600  # 1 hour
_STARTUP_DELAY = 30  # Wait before first run


async def start_ingest_cleanup():
    """Run cleanup every hour. Designed to be started via asyncio.create_task()."""
    logger.info(
        "Ingest cleanup starting (delay=%ds, interval=%ds)",
        _STARTUP_DELAY,
        _CLEANUP_INTERVAL,
    )
    await asyncio.sleep(_STARTUP_DELAY)

    while True:
        try:
            # Import here to get a fresh session each cycle
            from app.database import AsyncSessionLocal

            async with AsyncSessionLocal() as session:
                count = await cleanup_expired_documents(session)
                if count > 0:
                    logger.info("Ingest cleanup cycle: removed %d documents", count)
        except asyncio.CancelledError:
            logger.info("Ingest cleanup task cancelled")
            break
        except Exception:
            logger.error("Ingest cleanup cycle failed", exc_info=True)

        await asyncio.sleep(_CLEANUP_INTERVAL)
