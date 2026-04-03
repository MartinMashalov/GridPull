"""Parse email attachments from .msg and .eml files with recursive extraction."""

import logging
import re
from dataclasses import dataclass
from email import policy
from email.parser import BytesParser
from html import unescape

logger = logging.getLogger(__name__)

CONSUMER_DOMAINS = frozenset({
    "gmail.com", "yahoo.com", "outlook.com", "hotmail.com",
    "aol.com", "icloud.com", "live.com", "msn.com", "me.com",
    "protonmail.com", "ymail.com", "googlemail.com",
})


@dataclass
class Attachment:
    filename: str
    data: bytes
    content_type: str


@dataclass
class ParsedEmail:
    sender_email: str
    sender_domain: str
    subject: str
    body_text: str
    attachments: list[Attachment]


def get_group_key(sender_email: str) -> str:
    """Return full email for consumer domains, domain for business."""
    domain = sender_email.rsplit("@", 1)[-1].lower() if "@" in sender_email else sender_email.lower()
    if domain in CONSUMER_DOMAINS:
        return sender_email.lower()
    return domain


def extract_domain(email_addr: str) -> str:
    if "@" in email_addr:
        return email_addr.rsplit("@", 1)[-1].lower()
    return email_addr.lower()


def _strip_html(html_text: str) -> str:
    """Convert HTML to plain text."""
    html_text = re.sub(r"(?is)<(script|style).*?</\1>", " ", html_text)
    html_text = re.sub(r"(?i)<br\s*/?>", "\n", html_text)
    html_text = re.sub(r"(?i)</(p|div|li|tr|h[1-6])>", "\n", html_text)
    text = unescape(re.sub(r"<[^>]+>", " ", html_text))
    text = re.sub(r"[ \t]+", " ", text)
    return re.sub(r"\n{3,}", "\n\n", text).strip()


def extract_attachments_from_msg(msg_bytes: bytes, depth: int = 0, max_depth: int = 3) -> list[Attachment]:
    """Recursively extract attachments from .msg (Outlook) files."""
    if depth >= max_depth:
        return []

    results: list[Attachment] = []
    try:
        import extract_msg
        import io

        message = extract_msg.Message(io.BytesIO(msg_bytes))
        try:
            for attachment in message.attachments:
                name = (
                    getattr(attachment, "longFilename", None)
                    or getattr(attachment, "shortFilename", None)
                    or getattr(attachment, "displayName", None)
                    or getattr(attachment, "name", None)
                    or "unnamed"
                )
                name = str(name)
                data = getattr(attachment, "data", None)
                if not data or not isinstance(data, bytes):
                    continue

                ext = name.rsplit(".", 1)[-1].lower() if "." in name else ""
                if ext == "msg":
                    results.extend(extract_attachments_from_msg(data, depth + 1, max_depth))
                elif ext in ("eml", "emlx"):
                    results.extend(extract_attachments_from_eml(data, depth + 1, max_depth))
                else:
                    ct = _guess_content_type(name)
                    results.append(Attachment(filename=name, data=data, content_type=ct))
        finally:
            message.close()
    except Exception:
        logger.warning("Failed to parse .msg at depth %d", depth, exc_info=True)

    return results


def extract_attachments_from_eml(eml_bytes: bytes, depth: int = 0, max_depth: int = 3) -> list[Attachment]:
    """Recursively extract attachments from .eml files."""
    if depth >= max_depth:
        return []

    results: list[Attachment] = []
    try:
        message = BytesParser(policy=policy.default).parsebytes(eml_bytes)
        for part in message.walk() if message.is_multipart() else [message]:
            disposition = part.get_content_disposition()
            if disposition != "attachment":
                continue
            name = part.get_filename() or "unnamed"
            payload = part.get_payload(decode=True)
            if not payload:
                continue

            ext = name.rsplit(".", 1)[-1].lower() if "." in name else ""
            if ext == "msg":
                results.extend(extract_attachments_from_msg(payload, depth + 1, max_depth))
            elif ext in ("eml", "emlx"):
                results.extend(extract_attachments_from_eml(payload, depth + 1, max_depth))
            else:
                ct = part.get_content_type() or _guess_content_type(name)
                results.append(Attachment(filename=name, data=payload, content_type=ct))
    except Exception:
        logger.warning("Failed to parse .eml at depth %d", depth, exc_info=True)

    return results


def parse_inbound_email(
    sender: str,
    subject: str,
    body_plain: str,
    body_html: str,
    attachments: list[Attachment],
) -> ParsedEmail:
    """Build a ParsedEmail from webhook data."""
    body_text = body_plain.strip() if body_plain else ""
    if not body_text and body_html:
        body_text = _strip_html(body_html)

    # Recursively expand .msg / .eml attachments
    expanded: list[Attachment] = []
    for att in attachments:
        ext = att.filename.rsplit(".", 1)[-1].lower() if "." in att.filename else ""
        if ext == "msg":
            nested = extract_attachments_from_msg(att.data, depth=0, max_depth=3)
            expanded.extend(nested if nested else [att])
        elif ext in ("eml", "emlx"):
            nested = extract_attachments_from_eml(att.data, depth=0, max_depth=3)
            expanded.extend(nested if nested else [att])
        else:
            expanded.append(att)

    return ParsedEmail(
        sender_email=sender.lower().strip(),
        sender_domain=extract_domain(sender),
        subject=subject or "",
        body_text=body_text,
        attachments=expanded,
    )


_MIME_MAP = {
    "pdf": "application/pdf",
    "png": "image/png",
    "jpg": "image/jpeg",
    "jpeg": "image/jpeg",
    "gif": "image/gif",
    "bmp": "image/bmp",
    "tif": "image/tiff",
    "tiff": "image/tiff",
    "webp": "image/webp",
    "txt": "text/plain",
    "csv": "text/csv",
    "html": "text/html",
    "htm": "text/html",
    "json": "application/json",
    "xml": "application/xml",
    "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "xls": "application/vnd.ms-excel",
    "doc": "application/msword",
    "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "msg": "application/vnd.ms-outlook",
    "eml": "message/rfc822",
}


def _guess_content_type(filename: str) -> str:
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    return _MIME_MAP.get(ext, "application/octet-stream")
