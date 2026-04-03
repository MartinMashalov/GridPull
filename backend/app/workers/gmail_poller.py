"""
Gmail IMAP poller — checks a Gmail inbox for new emails with attachments
and feeds them into the ingest pipeline (Hetzner SFTP + DB).

Emails are routed by looking for "+intake-{key}" in the TO/Delivered-To
headers (Gmail supports + addressing).  If no key is found, falls back to
looking up any user whose ingest_address_key is set (single-tenant mode).
"""

import asyncio
import email as email_lib
import imaplib
import logging
import re
import uuid
from datetime import datetime, timedelta
from email.header import decode_header

from app.config import settings

logger = logging.getLogger(__name__)

_POLL_INTERVAL = None  # set at start from settings
_STARTUP_DELAY = 10


def _decode_header_value(raw: str | None) -> str:
    """Decode RFC-2047 encoded header into a plain string."""
    if not raw:
        return ""
    parts = decode_header(raw)
    decoded = []
    for part, charset in parts:
        if isinstance(part, bytes):
            decoded.append(part.decode(charset or "utf-8", errors="replace"))
        else:
            decoded.append(part)
    return " ".join(decoded)


def _extract_address_key(msg: email_lib.message.Message) -> str | None:
    """
    Look for '+intake-{key}' in To, Delivered-To, Cc, or Envelope-To headers.
    Returns the key or None.
    """
    pattern = re.compile(r"\+intake-([a-z0-9]+)@", re.IGNORECASE)
    for hdr_name in ("Delivered-To", "To", "Cc", "X-Original-To", "Envelope-To"):
        hdr = msg.get(hdr_name, "")
        m = pattern.search(hdr)
        if m:
            return m.group(1).lower()
    return None


def _extract_sender(msg: email_lib.message.Message) -> str:
    """Return the sender email address (lowercase)."""
    raw = msg.get("From", "")
    # Extract email from "Name <email>" format
    m = re.search(r"<([^>]+)>", raw)
    if m:
        return m.group(1).strip().lower()
    return raw.strip().lower()


def _extract_attachments(msg: email_lib.message.Message) -> list[dict]:
    """Walk the MIME tree and extract attachment parts."""
    attachments = []
    for part in msg.walk():
        disposition = part.get_content_disposition()
        if disposition not in ("attachment", "inline"):
            continue
        filename = part.get_filename()
        if not filename:
            continue
        filename = _decode_header_value(filename)
        payload = part.get_payload(decode=True)
        if not payload:
            continue
        content_type = part.get_content_type() or "application/octet-stream"
        attachments.append({
            "filename": filename,
            "data": payload,
            "content_type": content_type,
        })
    return attachments


async def _process_email(msg: email_lib.message.Message, msg_uid: str):
    """Process a single email: find user, extract attachments, store in S3."""
    from sqlalchemy import select
    from app.database import AsyncSessionLocal
    from app.models.ingest import IngestDocument
    from app.models.user import User
    from app.services.ingest.s3_service import upload_file as upload_to_s3
    from app.services.ingest.email_parser import extract_domain

    sender = _extract_sender(msg)
    subject = _decode_header_value(msg.get("Subject", ""))
    message_id = msg.get("Message-ID", "") or f"gmail-{msg_uid}"

    attachments = _extract_attachments(msg)
    if not attachments:
        logger.debug("Gmail poller: no attachments in email from %s, skipping", sender)
        return 0

    # Route to user
    address_key = _extract_address_key(msg)

    async with AsyncSessionLocal() as db:
        user = None
        if address_key:
            result = await db.execute(
                select(User).where(User.ingest_address_key == address_key)
            )
            user = result.scalar_one_or_none()

        if not user:
            # Fallback: use first user with an ingest address (single-tenant)
            result = await db.execute(
                select(User)
                .where(User.ingest_address_key.isnot(None))
                .order_by(User.created_at)
                .limit(1)
            )
            user = result.scalar_one_or_none()

        if not user:
            logger.warning(
                "Gmail poller: no user found for email from %s (key=%s)",
                sender, address_key,
            )
            return 0

        # Dedup by message_id
        existing = await db.execute(
            select(IngestDocument.id).where(
                IngestDocument.user_id == user.id,
                IngestDocument.message_id == message_id,
            ).limit(1)
        )
        if existing.scalar_one_or_none():
            logger.debug("Gmail poller: duplicate message_id=%s", message_id)
            return 0

        expires_at = datetime.utcnow() + timedelta(days=7)
        doc_count = 0

        for att in attachments:
            doc_id = str(uuid.uuid4())
            try:
                s3_key = await upload_to_s3(
                    user_id=user.id,
                    doc_id=doc_id,
                    filename=att["filename"],
                    data=att["data"],
                    content_type=att["content_type"],
                )
            except Exception:
                logger.error(
                    "Gmail poller: failed to upload %s to S3",
                    att["filename"], exc_info=True,
                )
                continue

            db.add(IngestDocument(
                id=doc_id,
                user_id=user.id,
                sender_email=sender,
                sender_domain=extract_domain(sender),
                subject=subject,
                message_id=message_id,
                filename=att["filename"],
                s3_key=s3_key,
                file_size=len(att["data"]),
                content_type=att["content_type"],
                expires_at=expires_at,
            ))
            doc_count += 1

        if doc_count > 0:
            await db.commit()
            logger.info(
                "Gmail poller: stored %d docs from %s (subject=%s) for user=%s",
                doc_count, sender, subject[:60], user.id,
            )

        return doc_count


_MAX_EMAILS_PER_POLL = 20  # cap per cycle to avoid overwhelming the system


def _poll_once() -> list[tuple[str, email_lib.message.Message]]:
    """
    Connect to Gmail IMAP, fetch UNSEEN emails from today, return list of (uid, message).
    Runs in a thread (blocking I/O).
    """
    if not settings.gmail_imap_email or not settings.gmail_imap_password:
        return []

    messages = []
    imap = None
    try:
        imap = imaplib.IMAP4_SSL(settings.gmail_imap_host, settings.gmail_imap_port)
        imap.login(settings.gmail_imap_email, settings.gmail_imap_password)
        imap.select("INBOX")

        # Only fetch unseen emails from today (avoid processing years of history)
        from datetime import date
        today = date.today().strftime("%d-%b-%Y")
        status, data = imap.uid("search", None, f'(UNSEEN SINCE {today})')
        if status != "OK" or not data or not data[0]:
            return []

        uids = data[0].split()
        logger.info("Gmail poller: found %d unseen emails since %s", len(uids), today)

        # Only process the most recent N emails per cycle
        if len(uids) > _MAX_EMAILS_PER_POLL:
            logger.info("Gmail poller: capping to %d most recent", _MAX_EMAILS_PER_POLL)
            uids = uids[-_MAX_EMAILS_PER_POLL:]

        for uid in uids:
            uid_str = uid.decode()
            try:
                status, msg_data = imap.uid("fetch", uid, "(RFC822)")
                if status != "OK" or not msg_data or not msg_data[0]:
                    continue
                raw_email = msg_data[0][1]
                msg = email_lib.message_from_bytes(raw_email)
                messages.append((uid_str, msg))

                # Mark as seen
                imap.uid("store", uid, "+FLAGS", "\\Seen")
            except Exception:
                logger.error("Gmail poller: failed to fetch UID %s", uid_str, exc_info=True)

    except imaplib.IMAP4.error as e:
        logger.error("Gmail poller IMAP error: %s", e)
    except Exception:
        logger.error("Gmail poller connection error", exc_info=True)
    finally:
        if imap:
            try:
                imap.close()
            except Exception:
                pass
            try:
                imap.logout()
            except Exception:
                pass

    return messages


async def start_gmail_poller():
    """Background task: poll Gmail for new emails at a regular interval."""
    global _POLL_INTERVAL
    _POLL_INTERVAL = settings.gmail_imap_poll_interval

    if not settings.gmail_imap_email or not settings.gmail_imap_password:
        logger.info("Gmail poller: credentials not configured, skipping")
        return

    logger.info(
        "Gmail poller starting (email=%s, interval=%ds, delay=%ds)",
        settings.gmail_imap_email, _POLL_INTERVAL, _STARTUP_DELAY,
    )
    await asyncio.sleep(_STARTUP_DELAY)

    while True:
        try:
            # IMAP is blocking — run in a thread
            messages = await asyncio.to_thread(_poll_once)

            total_docs = 0
            for uid, msg in messages:
                try:
                    count = await _process_email(msg, uid)
                    total_docs += count
                except Exception:
                    logger.error("Gmail poller: failed to process UID %s", uid, exc_info=True)

            if total_docs > 0:
                logger.info("Gmail poller cycle: ingested %d documents from %d emails", total_docs, len(messages))

        except asyncio.CancelledError:
            logger.info("Gmail poller task cancelled")
            break
        except Exception:
            logger.error("Gmail poller cycle failed", exc_info=True)

        await asyncio.sleep(_POLL_INTERVAL)
