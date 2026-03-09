"""
Microsoft Outlook / Exchange email service via Graph API.

Uses the same Microsoft OAuth connection (provider="sharepoint") as SharePoint/OneDrive.
Required additional scopes: Mail.Read, Mail.ReadWrite (already added to sharepoint_service.py).

The Azure App Registration must have these delegated permissions:
  - Mail.Read       (list + read email content)
  - Mail.ReadWrite  (mark emails as read after processing)
  - Files.ReadWrite.All  (already present for SharePoint/OneDrive)
"""

from __future__ import annotations

import base64
import logging
from typing import Any, Dict, List, Optional

import httpx

logger = logging.getLogger(__name__)

_GRAPH_API = "https://graph.microsoft.com/v1.0"

# Well-known mail folder IDs
MAIL_FOLDER_INBOX = "inbox"
MAIL_FOLDER_SENT = "sentitems"


async def list_mail_folders(access_token: str) -> List[Dict[str, Any]]:
    """List the top-level mail folders (Inbox, Sent, etc.)."""
    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.get(
            f"{_GRAPH_API}/me/mailFolders",
            headers={"Authorization": f"Bearer {access_token}"},
            params={"$select": "id,displayName,totalItemCount,unreadItemCount", "$top": 20},
        )
        resp.raise_for_status()
        return resp.json().get("value", [])


async def list_unread_pdf_emails(
    access_token: str,
    folder_id: str = "inbox",
    from_filter: str = "",
    subject_filter: str = "",
) -> List[Dict[str, Any]]:
    """
    List unread emails with supported document/image attachments in the specified folder.

    Returns a list of message dicts with: id, subject, from, receivedDateTime.
    """
    filter_parts = ["isRead eq false", "hasAttachments eq true"]

    # Graph API OData filter for from/subject (simple contains check)
    if from_filter.strip():
        safe = from_filter.strip().replace("'", "''")
        filter_parts.append(f"contains(from/emailAddress/address, '{safe}')")
    if subject_filter.strip():
        safe = subject_filter.strip().replace("'", "''")
        filter_parts.append(f"contains(subject, '{safe}')")

    url = f"{_GRAPH_API}/me/mailFolders/{folder_id}/messages"

    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.get(
            url,
            headers={"Authorization": f"Bearer {access_token}"},
            params={
                "$filter": " and ".join(filter_parts),
                "$select": "id,subject,from,receivedDateTime,hasAttachments",
                "$orderby": "receivedDateTime asc",
                "$top": 50,
            },
        )
        resp.raise_for_status()
        return resp.json().get("value", [])


async def get_pdf_attachments(
    access_token: str,
    message_id: str,
) -> List[Dict[str, Any]]:
    """
    Return metadata for all supported document/image attachments on a message.
    Each item has: id, name, contentType, size.
    """
    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.get(
            f"{_GRAPH_API}/me/messages/{message_id}/attachments",
            headers={"Authorization": f"Bearer {access_token}"},
            params={"$select": "id,name,contentType,size"},
        )
        resp.raise_for_status()
        attachments = resp.json().get("value", [])

    return [
        a for a in attachments
        if a.get("contentType", "").lower() in (
            "application/pdf",
            "image/jpeg",
            "image/png",
            "application/octet-stream",  # some mail clients send PDFs with this MIME
        ) or (a.get("name", "").lower().endswith(".pdf"))
        or (a.get("name", "").lower().endswith((".jpg", ".jpeg", ".png")))
    ]


async def download_attachment(
    access_token: str,
    message_id: str,
    attachment_id: str,
) -> bytes:
    """Download a specific attachment as raw bytes."""
    async with httpx.AsyncClient(timeout=120.0) as client:
        resp = await client.get(
            f"{_GRAPH_API}/me/messages/{message_id}/attachments/{attachment_id}/$value",
            headers={"Authorization": f"Bearer {access_token}"},
        )
        resp.raise_for_status()
        return resp.content


async def get_attachment_bytes_inline(
    access_token: str,
    message_id: str,
    attachment_id: str,
) -> bytes:
    """
    Get attachment bytes via the attachment body (contentBytes field).
    Used as a fallback when the /$value endpoint isn't available.
    """
    async with httpx.AsyncClient(timeout=120.0) as client:
        resp = await client.get(
            f"{_GRAPH_API}/me/messages/{message_id}/attachments/{attachment_id}",
            headers={"Authorization": f"Bearer {access_token}"},
            params={"$select": "contentBytes"},
        )
        resp.raise_for_status()
        content_b64 = resp.json().get("contentBytes", "")
        return base64.b64decode(content_b64)


async def mark_as_read(access_token: str, message_id: str) -> None:
    """Mark an email as read (requires Mail.ReadWrite scope)."""
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            await client.patch(
                f"{_GRAPH_API}/me/messages/{message_id}",
                headers={"Authorization": f"Bearer {access_token}"},
                json={"isRead": True},
            )
    except Exception as exc:
        logger.warning("Could not mark message %s as read: %s", message_id, exc)
