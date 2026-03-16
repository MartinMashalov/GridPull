"""
Google Drive OAuth + REST API service.

Uses httpx directly against Google's REST APIs — no additional SDK required.
"""

from __future__ import annotations

import json
import logging
import urllib.parse
from datetime import datetime, timedelta
from typing import Any, Dict, List

import httpx

from app.config import settings

logger = logging.getLogger(__name__)

_GOOGLE_AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
_GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
_DRIVE_API = "https://www.googleapis.com/drive/v3"
_DRIVE_UPLOAD_API = "https://www.googleapis.com/upload/drive/v3"
_SCOPE = "https://www.googleapis.com/auth/drive"


def get_auth_url(redirect_uri: str, state: str) -> str:
    """Build Google OAuth authorization URL."""
    client_id = (settings.google_drive_client_id or "").strip().strip("'").strip('"')
    if client_id.lower() in {"none", "null"}:
        client_id = ""
    if not client_id:
        raise ValueError("Google Drive client ID is not configured")
    params = {
        "client_id": client_id,
        "redirect_uri": redirect_uri,
        "response_type": "code",
        "scope": _SCOPE,
        "state": state,
        "access_type": "offline",
        "prompt": "consent",
    }
    return f"{_GOOGLE_AUTH_URL}?{urllib.parse.urlencode(params)}"


async def exchange_code(code: str, redirect_uri: str) -> Dict[str, Any]:
    """Exchange authorization code for access + refresh tokens."""
    client_id = (settings.google_drive_client_id or "").strip().strip("'").strip('"')
    client_secret = (settings.google_drive_client_secret or "").strip().strip("'").strip('"')
    if client_id.lower() in {"none", "null"}:
        client_id = ""
    if client_secret.lower() in {"none", "null"}:
        client_secret = ""
    if not client_id or not client_secret:
        raise ValueError("Google Drive OAuth credentials are not configured")
    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.post(_GOOGLE_TOKEN_URL, data={
            "code": code,
            "client_id": client_id,
            "client_secret": client_secret,
            "redirect_uri": redirect_uri,
            "grant_type": "authorization_code",
        })
        resp.raise_for_status()
        return resp.json()


async def _refresh_token(conn: Any) -> str:
    """Refresh Google access token in-place on conn object."""
    client_id = (settings.google_drive_client_id or "").strip().strip("'").strip('"')
    client_secret = (settings.google_drive_client_secret or "").strip().strip("'").strip('"')
    if client_id.lower() in {"none", "null"}:
        client_id = ""
    if client_secret.lower() in {"none", "null"}:
        client_secret = ""
    if not client_id or not client_secret:
        raise ValueError("Google Drive OAuth credentials are not configured")
    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.post(_GOOGLE_TOKEN_URL, data={
            "refresh_token": conn.refresh_token,
            "client_id": client_id,
            "client_secret": client_secret,
            "grant_type": "refresh_token",
        })
        resp.raise_for_status()
        data = resp.json()
    conn.access_token = data["access_token"]
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
    """Fetch Google account email + name."""
    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.get(
            f"{_DRIVE_API}/about",
            headers={"Authorization": f"Bearer {access_token}"},
            params={"fields": "user(displayName,emailAddress)"},
        )
        resp.raise_for_status()
        user = (resp.json() or {}).get("user", {})
        return {
            "email": user.get("emailAddress"),
            "name": user.get("displayName"),
        }


async def list_folders(access_token: str, parent_id: str = "root") -> List[Dict[str, Any]]:
    """List sub-folders inside a Google Drive folder."""
    query = (
        f"'{parent_id}' in parents "
        "and mimeType = 'application/vnd.google-apps.folder' "
        "and trashed = false"
    )
    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.get(
            f"{_DRIVE_API}/files",
            headers={"Authorization": f"Bearer {access_token}"},
            params={
                "q": query,
                "fields": "files(id,name)",
                "pageSize": 100,
                "orderBy": "name",
            },
        )
        resp.raise_for_status()
        return resp.json().get("files", [])


async def list_pdfs(access_token: str, folder_id: str) -> List[Dict[str, Any]]:
    """List supported source files in a Google Drive folder."""
    query = (
        f"'{folder_id}' in parents "
        "and ("
        "mimeType = 'application/pdf' "
        "or mimeType = 'image/jpeg' "
        "or mimeType = 'image/png'"
        ") "
        "and trashed = false"
    )
    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.get(
            f"{_DRIVE_API}/files",
            headers={"Authorization": f"Bearer {access_token}"},
            params={
                "q": query,
                "fields": "files(id,name,createdTime,modifiedTime,md5Checksum)",
                "pageSize": 100,
                "orderBy": "createdTime desc",
            },
        )
        resp.raise_for_status()
        return resp.json().get("files", [])


async def download_file(access_token: str, file_id: str) -> bytes:
    """Download a file from Google Drive as bytes."""
    async with httpx.AsyncClient(timeout=120.0) as client:
        resp = await client.get(
            f"{_DRIVE_API}/files/{file_id}",
            headers={"Authorization": f"Bearer {access_token}"},
            params={"alt": "media"},
        )
        resp.raise_for_status()
        return resp.content


async def find_file_by_name(access_token: str, folder_id: str, filename: str) -> str | None:
    """Find a file by exact name in a Google Drive folder. Returns file_id or None."""
    safe = filename.replace("'", "\\'")
    query = f"'{folder_id}' in parents and name = '{safe}' and trashed = false"
    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.get(
            f"{_DRIVE_API}/files",
            headers={"Authorization": f"Bearer {access_token}"},
            params={"q": query, "fields": "files(id)", "pageSize": 1},
        )
        resp.raise_for_status()
        files = resp.json().get("files", [])
        return files[0]["id"] if files else None


async def update_file_content(
    access_token: str,
    file_id: str,
    content: bytes,
    mime_type: str = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
) -> str:
    """Update the content of an existing Google Drive file. Returns webViewLink."""
    async with httpx.AsyncClient(timeout=120.0) as client:
        resp = await client.patch(
            f"{_DRIVE_UPLOAD_API}/files/{file_id}",
            headers={
                "Authorization": f"Bearer {access_token}",
                "Content-Type": mime_type,
            },
            params={"uploadType": "media", "fields": "id,webViewLink"},
            content=content,
        )
        resp.raise_for_status()
        data = resp.json()
        return data.get("webViewLink", f"https://drive.google.com/file/d/{data['id']}/view")


async def upload_file(
    access_token: str,
    folder_id: str,
    filename: str,
    content: bytes,
    mime_type: str = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
) -> str:
    """Upload a file to Google Drive and return its webViewLink."""
    boundary = "GridPullBoundary_abc123XyZ"
    metadata = json.dumps({"name": filename, "parents": [folder_id]}).encode()
    body = (
        f"--{boundary}\r\nContent-Type: application/json; charset=UTF-8\r\n\r\n".encode()
        + metadata
        + f"\r\n--{boundary}\r\nContent-Type: {mime_type}\r\n\r\n".encode()
        + content
        + f"\r\n--{boundary}--".encode()
    )
    async with httpx.AsyncClient(timeout=120.0) as client:
        resp = await client.post(
            f"{_DRIVE_UPLOAD_API}/files",
            headers={
                "Authorization": f"Bearer {access_token}",
                "Content-Type": f"multipart/related; boundary={boundary}",
            },
            params={"uploadType": "multipart", "fields": "id,webViewLink"},
            content=body,
        )
        resp.raise_for_status()
        data = resp.json()
        return data.get("webViewLink", f"https://drive.google.com/file/d/{data['id']}/view")
