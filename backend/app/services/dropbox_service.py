"""
Dropbox OAuth + REST API service.
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

_DROPBOX_AUTH_URL = "https://www.dropbox.com/oauth2/authorize"
_DROPBOX_TOKEN_URL = "https://api.dropboxapi.com/oauth2/token"
_DROPBOX_API = "https://api.dropboxapi.com/2"
_DROPBOX_CONTENT_API = "https://content.dropboxapi.com/2"
_SCOPES = "files.metadata.read files.content.read files.content.write sharing.write account_info.read"


def _folder_path(folder_id: str) -> str:
    return "" if folder_id in ("", "root", "/") else folder_id


def _join_path(folder_id: str, filename: str) -> str:
    folder_path = _folder_path(folder_id).rstrip("/")
    return f"/{filename}" if not folder_path else f"{folder_path}/{filename}"


def get_auth_url(redirect_uri: str, state: str) -> str:
    params = {
        "client_id": settings.dropbox_client_id,
        "redirect_uri": redirect_uri,
        "response_type": "code",
        "state": state,
        "token_access_type": "offline",
        "scope": _SCOPES,
    }
    return f"{_DROPBOX_AUTH_URL}?{urllib.parse.urlencode(params)}"


async def exchange_code(code: str, redirect_uri: str) -> Dict[str, Any]:
    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.post(_DROPBOX_TOKEN_URL, data={
            "code": code,
            "client_id": settings.dropbox_client_id,
            "client_secret": settings.dropbox_client_secret,
            "redirect_uri": redirect_uri,
            "grant_type": "authorization_code",
        })
        resp.raise_for_status()
        return resp.json()


async def _refresh_token(conn: Any) -> str:
    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.post(_DROPBOX_TOKEN_URL, data={
            "refresh_token": conn.refresh_token,
            "client_id": settings.dropbox_client_id,
            "client_secret": settings.dropbox_client_secret,
            "grant_type": "refresh_token",
        })
        resp.raise_for_status()
        data = resp.json()
    conn.access_token = data["access_token"]
    conn.token_expires_at = datetime.utcnow() + timedelta(
        seconds=data.get("expires_in", 14400) - 60
    )
    return conn.access_token


async def ensure_fresh_token(conn: Any, db: Any) -> str:
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
    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.post(
            f"{_DROPBOX_API}/users/get_current_account",
            headers={"Authorization": f"Bearer {access_token}"},
        )
        resp.raise_for_status()
        return resp.json()


async def _list_folder_entries(access_token: str, folder_id: str) -> List[Dict[str, Any]]:
    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.post(
            f"{_DROPBOX_API}/files/list_folder",
            headers={"Authorization": f"Bearer {access_token}"},
            json={"path": _folder_path(folder_id), "recursive": False},
        )
        resp.raise_for_status()
        return resp.json().get("entries", [])


async def list_folders(access_token: str, folder_id: str = "root") -> List[Dict[str, Any]]:
    entries = await _list_folder_entries(access_token, folder_id)
    return [
        {
            "id": item.get("path_lower") or item.get("path_display") or "",
            "name": item["name"],
        }
        for item in entries
        if item.get(".tag") == "folder"
    ]


async def list_pdfs(access_token: str, folder_id: str) -> List[Dict[str, Any]]:
    entries = await _list_folder_entries(access_token, folder_id)
    return [
        {
            "id": item["id"],
            "name": item["name"],
            "path": item.get("path_lower") or item.get("path_display") or item["id"],
        }
        for item in entries
        if item.get(".tag") == "file" and item.get("name", "").lower().endswith((".pdf", ".jpg", ".jpeg", ".png"))
    ]


async def download_file(access_token: str, file_ref: str) -> bytes:
    async with httpx.AsyncClient(timeout=120.0) as client:
        resp = await client.post(
            f"{_DROPBOX_CONTENT_API}/files/download",
            headers={
                "Authorization": f"Bearer {access_token}",
                "Dropbox-API-Arg": json.dumps({"path": file_ref}),
            },
        )
        resp.raise_for_status()
        return resp.content


async def find_file_by_name(access_token: str, folder_id: str, filename: str) -> str | None:
    entries = await _list_folder_entries(access_token, folder_id)
    for item in entries:
        if item.get(".tag") == "file" and item.get("name") == filename:
            return item.get("path_lower") or item.get("path_display") or item.get("id")
    return None


async def _shared_link_for_path(access_token: str, path: str) -> str:
    async with httpx.AsyncClient(timeout=30.0) as client:
        existing = await client.post(
            f"{_DROPBOX_API}/sharing/list_shared_links",
            headers={"Authorization": f"Bearer {access_token}"},
            json={"path": path, "direct_only": True},
        )
        existing.raise_for_status()
        links = existing.json().get("links", [])
        if links:
            return links[0]["url"]

        created = await client.post(
            f"{_DROPBOX_API}/sharing/create_shared_link_with_settings",
            headers={"Authorization": f"Bearer {access_token}"},
            json={"path": path},
        )
        created.raise_for_status()
        return created.json()["url"]


async def upload_file(
    access_token: str,
    folder_id: str,
    filename: str,
    content: bytes,
) -> str:
    path = _join_path(folder_id, filename)
    async with httpx.AsyncClient(timeout=120.0) as client:
        resp = await client.post(
            f"{_DROPBOX_CONTENT_API}/files/upload",
            headers={
                "Authorization": f"Bearer {access_token}",
                "Content-Type": "application/octet-stream",
                "Dropbox-API-Arg": json.dumps({
                    "path": path,
                    "mode": "overwrite",
                    "autorename": False,
                    "mute": True,
                }),
            },
            content=content,
        )
        resp.raise_for_status()
        meta = resp.json()
    return await _shared_link_for_path(access_token, meta.get("path_display") or path)
