"""
Microsoft SharePoint / OneDrive OAuth + Graph API service.

Uses httpx directly against Microsoft's OAuth and Graph REST APIs.
"""

from __future__ import annotations

import asyncio
import logging
import urllib.parse
from datetime import datetime, timedelta
from typing import Any, Dict, List

import httpx

from app.config import settings

logger = logging.getLogger(__name__)

_MS_AUTH_URL = "https://login.microsoftonline.com/common/oauth2/v2.0/authorize"
_MS_TOKEN_URL = "https://login.microsoftonline.com/common/oauth2/v2.0/token"
_GRAPH_API = "https://graph.microsoft.com/v1.0"
_SCOPES = "https://graph.microsoft.com/Files.ReadWrite.All https://graph.microsoft.com/Mail.Read https://graph.microsoft.com/Mail.ReadWrite offline_access User.Read"


def get_auth_url(redirect_uri: str, state: str) -> str:
    """Build Microsoft OAuth authorization URL."""
    params = {
        "client_id": settings.microsoft_client_id,
        "redirect_uri": redirect_uri,
        "response_type": "code",
        "scope": _SCOPES,
        "state": state,
        "response_mode": "query",
    }
    return f"{_MS_AUTH_URL}?{urllib.parse.urlencode(params)}"


async def exchange_code(code: str, redirect_uri: str) -> Dict[str, Any]:
    """Exchange authorization code for access + refresh tokens."""
    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.post(_MS_TOKEN_URL, data={
            "code": code,
            "client_id": settings.microsoft_client_id,
            "client_secret": settings.microsoft_client_secret,
            "redirect_uri": redirect_uri,
            "grant_type": "authorization_code",
            "scope": _SCOPES,
        })
        resp.raise_for_status()
        return resp.json()


async def _refresh_token(conn: Any) -> str:
    """Refresh Microsoft access token in-place on conn object."""
    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.post(_MS_TOKEN_URL, data={
            "refresh_token": conn.refresh_token,
            "client_id": settings.microsoft_client_id,
            "client_secret": settings.microsoft_client_secret,
            "grant_type": "refresh_token",
            "scope": _SCOPES,
        })
        resp.raise_for_status()
        data = resp.json()
    conn.access_token = data["access_token"]
    if "refresh_token" in data:
        conn.refresh_token = data["refresh_token"]
    conn.token_expires_at = datetime.utcnow() + timedelta(
        seconds=data.get("expires_in", 3600) - 60
    )
    return conn.access_token


async def ensure_fresh_token(conn: Any, db: Any) -> str:
    """Return a valid access token, refreshing if near expiry."""
    needs_refresh = (
        conn.token_expires_at is None
        or conn.token_expires_at <= datetime.utcnow() + timedelta(minutes=5)
    )
    if needs_refresh and conn.refresh_token:
        token = await _refresh_token(conn)
        await db.commit()
        return token
    return conn.access_token


async def get_user_info(access_token: str) -> Dict[str, Any]:
    """Fetch Microsoft account email + name."""
    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.get(
            f"{_GRAPH_API}/me",
            headers={"Authorization": f"Bearer {access_token}"},
            params={"$select": "displayName,mail,userPrincipalName"},
        )
        resp.raise_for_status()
        return resp.json()


async def list_folders(
    access_token: str,
    folder_id: str = "root",
    drive_id: str | None = None,
) -> List[Dict[str, Any]]:
    """List sub-folders in a OneDrive/SharePoint folder."""
    if drive_id:
        url = f"{_GRAPH_API}/drives/{drive_id}/items/{folder_id}/children"
    else:
        url = f"{_GRAPH_API}/me/drive/items/{folder_id}/children"

    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.get(
            url,
            headers={"Authorization": f"Bearer {access_token}"},
            params={"$select": "id,name,folder", "$top": 100},
        )
        resp.raise_for_status()
        items = resp.json().get("value", [])

    return [
        {"id": item["id"], "name": item["name"]}
        for item in items
        if "folder" in item
    ]


async def list_pdfs(
    access_token: str,
    folder_id: str,
    drive_id: str | None = None,
) -> List[Dict[str, Any]]:
    """List supported source files in a OneDrive folder."""
    if drive_id:
        url = f"{_GRAPH_API}/drives/{drive_id}/items/{folder_id}/children"
    else:
        url = f"{_GRAPH_API}/me/drive/items/{folder_id}/children"

    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.get(
            url,
            headers={"Authorization": f"Bearer {access_token}"},
            params={"$select": "id,name,createdDateTime,file", "$top": 100},
        )
        resp.raise_for_status()
        items = resp.json().get("value", [])

    return [
        {"id": item["id"], "name": item["name"]}
        for item in items
        if (
            item.get("file", {}).get("mimeType") == "application/pdf"
            or item.get("file", {}).get("mimeType") == "image/jpeg"
            or item.get("file", {}).get("mimeType") == "image/png"
            or item.get("name", "").lower().endswith((".pdf", ".jpg", ".jpeg", ".png"))
        )
        and "file" in item  # exclude folders
    ]


async def find_and_download_file(
    access_token: str,
    folder_id: str,
    filename: str,
    drive_id: str | None = None,
) -> bytes | None:
    """Try to download a file by name inside a OneDrive folder. Returns bytes or None if not found."""
    if drive_id:
        url = f"{_GRAPH_API}/drives/{drive_id}/items/{folder_id}:/{filename}:/content"
    else:
        url = f"{_GRAPH_API}/me/drive/items/{folder_id}:/{filename}:/content"

    async with httpx.AsyncClient(timeout=120.0, follow_redirects=True) as client:
        resp = await client.get(url, headers={"Authorization": f"Bearer {access_token}"})
        if resp.status_code == 404:
            return None
        resp.raise_for_status()
        return resp.content


async def download_file(
    access_token: str,
    file_id: str,
    drive_id: str | None = None,
) -> bytes:
    """Download a file from OneDrive as bytes."""
    if drive_id:
        url = f"{_GRAPH_API}/drives/{drive_id}/items/{file_id}/content"
    else:
        url = f"{_GRAPH_API}/me/drive/items/{file_id}/content"

    async with httpx.AsyncClient(timeout=120.0, follow_redirects=True) as client:
        resp = await client.get(url, headers={"Authorization": f"Bearer {access_token}"})
        resp.raise_for_status()
        return resp.content


async def upload_file(
    access_token: str,
    folder_id: str,
    filename: str,
    content: bytes,
    drive_id: str | None = None,
) -> str:
    """Upload a file to OneDrive and return its webUrl."""
    if drive_id:
        url = f"{_GRAPH_API}/drives/{drive_id}/items/{folder_id}:/{filename}:/content"
    else:
        url = f"{_GRAPH_API}/me/drive/items/{folder_id}:/{filename}:/content"

    async with httpx.AsyncClient(timeout=120.0) as client:
        for attempt in range(5):
            resp = await client.put(
                url,
                headers={
                    "Authorization": f"Bearer {access_token}",
                    "Content-Type": "application/octet-stream",
                },
                content=content,
            )
            if resp.status_code < 400:
                return resp.json().get("webUrl", "")
            if resp.status_code not in (423, 429, 503):
                resp.raise_for_status()
            if attempt == 4:
                resp.raise_for_status()
            retry_after = resp.headers.get("Retry-After")
            try:
                wait_seconds = float(retry_after) if retry_after else (1.5 * (attempt + 1))
            except ValueError:
                wait_seconds = 1.5 * (attempt + 1)
            logger.warning(
                "SharePoint upload retry %d/5 for %s after HTTP %d (waiting %.1fs)",
                attempt + 1,
                filename,
                resp.status_code,
                wait_seconds,
            )
            await asyncio.sleep(wait_seconds)
