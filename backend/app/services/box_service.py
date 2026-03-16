"""
Box OAuth + REST API service.
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

_BOX_AUTH_URL = "https://account.box.com/api/oauth2/authorize"
_BOX_TOKEN_URL = "https://api.box.com/oauth2/token"
_BOX_API = "https://api.box.com/2.0"
_BOX_UPLOAD_API = "https://upload.box.com/api/2.0"


def get_auth_url(redirect_uri: str, state: str) -> str:
    client_id = next(
        (
            value
            for value in (
                settings.box_client_id,
                settings.box_app_key,
            )
            if value
            and value.strip().strip("'").strip('"')
            and value.strip().strip("'").strip('"').lower() not in {"none", "null"}
        ),
        "",
    ).strip().strip("'").strip('"')
    if not client_id:
        raise ValueError("Box client ID is not configured")
    params = {
        "client_id": client_id,
        "redirect_uri": redirect_uri,
        "response_type": "code",
        "state": state,
    }
    return f"{_BOX_AUTH_URL}?{urllib.parse.urlencode(params)}"


async def exchange_code(code: str, redirect_uri: str) -> Dict[str, Any]:
    client_id = next(
        (
            value
            for value in (
                settings.box_client_id,
                settings.box_app_key,
            )
            if value
            and value.strip().strip("'").strip('"')
            and value.strip().strip("'").strip('"').lower() not in {"none", "null"}
        ),
        "",
    ).strip().strip("'").strip('"')
    client_secret = next(
        (
            value
            for value in (
                settings.box_client_secret,
                settings.box_app_secret,
            )
            if value
            and value.strip().strip("'").strip('"')
            and value.strip().strip("'").strip('"').lower() not in {"none", "null"}
        ),
        "",
    ).strip().strip("'").strip('"')
    if not client_id or not client_secret:
        raise ValueError("Box OAuth credentials are not configured")
    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.post(_BOX_TOKEN_URL, data={
            "code": code,
            "client_id": client_id,
            "client_secret": client_secret,
            "redirect_uri": redirect_uri,
            "grant_type": "authorization_code",
        })
        resp.raise_for_status()
        return resp.json()


async def _refresh_token(conn: Any) -> str:
    client_id = next(
        (
            value
            for value in (
                settings.box_client_id,
                settings.box_app_key,
            )
            if value
            and value.strip().strip("'").strip('"')
            and value.strip().strip("'").strip('"').lower() not in {"none", "null"}
        ),
        "",
    ).strip().strip("'").strip('"')
    client_secret = next(
        (
            value
            for value in (
                settings.box_client_secret,
                settings.box_app_secret,
            )
            if value
            and value.strip().strip("'").strip('"')
            and value.strip().strip("'").strip('"').lower() not in {"none", "null"}
        ),
        "",
    ).strip().strip("'").strip('"')
    if not client_id or not client_secret:
        raise ValueError("Box OAuth credentials are not configured")
    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.post(_BOX_TOKEN_URL, data={
            "refresh_token": conn.refresh_token,
            "client_id": client_id,
            "client_secret": client_secret,
            "grant_type": "refresh_token",
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
        resp = await client.get(
            f"{_BOX_API}/users/me",
            headers={"Authorization": f"Bearer {access_token}"},
        )
        resp.raise_for_status()
        return resp.json()


async def _list_folder_items(access_token: str, folder_id: str) -> List[Dict[str, Any]]:
    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.get(
            f"{_BOX_API}/folders/{folder_id}/items",
            headers={"Authorization": f"Bearer {access_token}"},
            params={
                "fields": "id,name,type",
                "limit": 1000,
                "offset": 0,
            },
        )
        resp.raise_for_status()
        return resp.json().get("entries", [])


async def list_folders(access_token: str, folder_id: str = "0") -> List[Dict[str, Any]]:
    items = await _list_folder_items(access_token, folder_id)
    return [
        {"id": item["id"], "name": item["name"]}
        for item in items
        if item.get("type") == "folder"
    ]


async def list_pdfs(access_token: str, folder_id: str) -> List[Dict[str, Any]]:
    items = await _list_folder_items(access_token, folder_id)
    return [
        {"id": item["id"], "name": item["name"]}
        for item in items
        if item.get("type") == "file" and item.get("name", "").lower().endswith((".pdf", ".jpg", ".jpeg", ".png"))
    ]


async def download_file(access_token: str, file_id: str) -> bytes:
    async with httpx.AsyncClient(timeout=120.0, follow_redirects=True) as client:
        resp = await client.get(
            f"{_BOX_API}/files/{file_id}/content",
            headers={"Authorization": f"Bearer {access_token}"},
        )
        resp.raise_for_status()
        return resp.content


async def find_file_by_name(access_token: str, folder_id: str, filename: str) -> str | None:
    items = await _list_folder_items(access_token, folder_id)
    for item in items:
        if item.get("type") == "file" and item.get("name") == filename:
            return item["id"]
    return None


async def upload_file(
    access_token: str,
    folder_id: str,
    filename: str,
    content: bytes,
    existing_file_id: str | None = None,
) -> str:
    url = (
        f"{_BOX_UPLOAD_API}/files/{existing_file_id}/content"
        if existing_file_id
        else f"{_BOX_UPLOAD_API}/files/content"
    )
    attributes = {"name": filename}
    if not existing_file_id:
        attributes["parent"] = {"id": folder_id}

    files = {
        "attributes": (None, json.dumps(attributes), "application/json"),
        "file": (filename, content, "application/octet-stream"),
    }

    async with httpx.AsyncClient(timeout=120.0) as client:
        resp = await client.post(
            url,
            headers={"Authorization": f"Bearer {access_token}"},
            files=files,
        )
        resp.raise_for_status()
        entries = resp.json().get("entries", [])
        file_id = entries[0]["id"] if entries else existing_file_id
    return f"https://app.box.com/file/{file_id}"
