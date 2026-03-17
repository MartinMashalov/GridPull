"""
Pipelines routes.

GET    /pipelines/oauth/google              → OAuth redirect to Google
GET    /pipelines/oauth/google/callback     → Exchange code, store connection
GET    /pipelines/oauth/microsoft           → OAuth redirect to Microsoft
GET    /pipelines/oauth/microsoft/callback  → Exchange code, store connection
GET    /pipelines/oauth/dropbox             → OAuth redirect to Dropbox
GET    /pipelines/oauth/dropbox/callback    → Exchange code, store connection
GET    /pipelines/oauth/box                 → OAuth redirect to Box
GET    /pipelines/oauth/box/callback        → Exchange code, store connection
DELETE /pipelines/oauth/{provider}          → Disconnect provider

GET    /pipelines/connections               → connected provider emails
GET    /pipelines/folders/google            → List Google Drive folders
GET    /pipelines/folders/microsoft         → List SharePoint folders
GET    /pipelines/folders/dropbox           → List Dropbox folders
GET    /pipelines/folders/box               → List Box folders

GET    /pipelines/                          → List user's pipelines + last 3 runs each
POST   /pipelines/                          → Create pipeline
PATCH  /pipelines/{id}                      → Update (name/status/fields)
DELETE /pipelines/{id}                      → Delete
GET    /pipelines/{id}/runs                 → Last 20 runs
POST   /pipelines/{id}/run                  → Manual trigger
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.responses import RedirectResponse
from pydantic import BaseModel
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import get_db
from app.middleware.auth_middleware import get_current_user, get_current_user_sse
from app.models.pipeline import OAuthConnection, Pipeline, PipelineRun
from app.models.user import User
from app.services.auth_service import verify_token

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/pipelines", tags=["pipelines"])

# ── Helpers ───────────────────────────────────────────────────────────────────

def _backend_url() -> str:
    """Backend public URL for OAuth redirect URIs (from BACKEND_URL env var)."""
    return settings.backend_url.rstrip("/")


def _google_redirect_uri() -> str:
    return f"{_backend_url()}/api/pipelines/oauth/google/callback"


def _microsoft_redirect_uri() -> str:
    return f"{_backend_url()}/api/pipelines/oauth/microsoft/callback"


def _dropbox_redirect_uri() -> str:
    return f"{_backend_url()}/api/pipelines/oauth/dropbox/callback"


def _box_redirect_uri() -> str:
    return f"{_backend_url()}/api/pipelines/oauth/box/callback"


async def _get_connection(db: AsyncSession, user_id: str, provider: str) -> Optional[OAuthConnection]:
    result = await db.execute(
        select(OAuthConnection).where(
            OAuthConnection.user_id == user_id,
            OAuthConnection.provider == provider,
        )
    )
    return result.scalar_one_or_none()


def _run_dict(run: PipelineRun) -> dict:
    return {
        "id": run.id,
        "status": run.status,
        "source_file_name": run.source_file_name,
        "source_file_id": run.source_file_id,
        "dest_file_name": run.dest_file_name,
        "dest_file_url": run.dest_file_url,
        "records_extracted": run.records_extracted,
        "cost_usd": run.cost_usd,
        "error_message": run.error_message,
        "log_lines": run.log_lines or [],
        "started_at": run.started_at.isoformat() if run.started_at else None,
        "completed_at": run.completed_at.isoformat() if run.completed_at else None,
    }


def _pipeline_dict(pipeline: Pipeline, runs: list) -> dict:
    return {
        "id": pipeline.id,
        "name": pipeline.name,
        "status": pipeline.status,
        "source_type": pipeline.source_type,
        "source_folder_id": pipeline.source_folder_id,
        "source_folder_name": pipeline.source_folder_name,
        "source_config": pipeline.source_config or {},
        "dest_folder_id": pipeline.dest_folder_id,
        "dest_folder_name": pipeline.dest_folder_name,
        "dest_format": pipeline.dest_format,
        "fields": pipeline.fields,
        "files_processed": pipeline.files_processed,
        "last_checked_at": pipeline.last_checked_at.isoformat() if pipeline.last_checked_at else None,
        "last_run_at": pipeline.last_run_at.isoformat() if pipeline.last_run_at else None,
        "created_at": pipeline.created_at.isoformat() if pipeline.created_at else None,
        "recent_runs": [_run_dict(r) for r in runs],
    }


# ── OAuth: Google ─────────────────────────────────────────────────────────────

@router.get("/oauth/google")
async def google_oauth_start(
    token: str = Query(..., description="User JWT"),
):
    """Redirect to Google consent screen. JWT passed as ?token= query param."""
    from app.services import gdrive_service
    user_id = verify_token(token)
    if not user_id:
        raise HTTPException(status_code=401, detail="Invalid token")
    url = gdrive_service.get_auth_url(_google_redirect_uri(), state=token)
    return RedirectResponse(url=url)


@router.get("/oauth/google/callback")
async def google_oauth_callback(
    code: str = Query(...),
    state: str = Query(...),
    db: AsyncSession = Depends(get_db),
):
    """Handle Google OAuth callback, store tokens, redirect to frontend."""
    from app.services import gdrive_service
    user_id = verify_token(state)
    if not user_id:
        raise HTTPException(status_code=401, detail="Invalid state token")

    try:
        token_data = await gdrive_service.exchange_code(code, _google_redirect_uri())
        user_info = await gdrive_service.get_user_info(token_data["access_token"])
    except Exception as exc:
        logger.error("Google OAuth callback failed: %s", exc)
        return RedirectResponse(url=f"{settings.frontend_url}/pipelines?error=google_oauth")

    expires_at = datetime.utcnow() + timedelta(seconds=token_data.get("expires_in", 3600) - 60)

    conn = await _get_connection(db, user_id, "google_drive")
    if conn:
        conn.access_token = token_data["access_token"]
        if "refresh_token" in token_data:
            conn.refresh_token = token_data["refresh_token"]
        conn.token_expires_at = expires_at
        conn.account_email = user_info.get("email")
        conn.account_name = user_info.get("name")
        conn.updated_at = datetime.utcnow()
    else:
        conn = OAuthConnection(
            user_id=user_id,
            provider="google_drive",
            access_token=token_data["access_token"],
            refresh_token=token_data.get("refresh_token"),
            token_expires_at=expires_at,
            account_email=user_info.get("email"),
            account_name=user_info.get("name"),
        )
        db.add(conn)

    await db.commit()
    logger.info("Google Drive connected for user_id=%s email=%s", user_id, conn.account_email)
    return RedirectResponse(url=f"{settings.frontend_url}/pipelines?connected=google")


# ── OAuth: Microsoft ──────────────────────────────────────────────────────────

@router.get("/oauth/microsoft")
async def microsoft_oauth_start(
    token: str = Query(..., description="User JWT"),
):
    """Redirect to Microsoft consent screen."""
    from app.services import sharepoint_service
    user_id = verify_token(token)
    if not user_id:
        raise HTTPException(status_code=401, detail="Invalid token")
    url = sharepoint_service.get_auth_url(_microsoft_redirect_uri(), state=token)
    return RedirectResponse(url=url)


@router.get("/oauth/microsoft/callback")
async def microsoft_oauth_callback(
    code: str = Query(...),
    state: str = Query(...),
    db: AsyncSession = Depends(get_db),
):
    """Handle Microsoft OAuth callback, store tokens, redirect to frontend."""
    from app.services import sharepoint_service
    user_id = verify_token(state)
    if not user_id:
        raise HTTPException(status_code=401, detail="Invalid state token")

    try:
        token_data = await sharepoint_service.exchange_code(code, _microsoft_redirect_uri())
        user_info = await sharepoint_service.get_user_info(token_data["access_token"])
    except Exception as exc:
        logger.error("Microsoft OAuth callback failed: %s", exc)
        return RedirectResponse(url=f"{settings.frontend_url}/pipelines?error=microsoft_oauth")

    expires_at = datetime.utcnow() + timedelta(seconds=token_data.get("expires_in", 3600) - 60)
    email = user_info.get("mail") or user_info.get("userPrincipalName", "")
    name = user_info.get("displayName", "")

    conn = await _get_connection(db, user_id, "sharepoint")
    if conn:
        conn.access_token = token_data["access_token"]
        if "refresh_token" in token_data:
            conn.refresh_token = token_data["refresh_token"]
        conn.token_expires_at = expires_at
        conn.account_email = email
        conn.account_name = name
        conn.updated_at = datetime.utcnow()
    else:
        conn = OAuthConnection(
            user_id=user_id,
            provider="sharepoint",
            access_token=token_data["access_token"],
            refresh_token=token_data.get("refresh_token"),
            token_expires_at=expires_at,
            account_email=email,
            account_name=name,
        )
        db.add(conn)

    await db.commit()
    logger.info("SharePoint connected for user_id=%s email=%s", user_id, email)
    return RedirectResponse(url=f"{settings.frontend_url}/pipelines?connected=microsoft")


# ── OAuth: Dropbox ────────────────────────────────────────────────────────────

@router.get("/oauth/dropbox")
async def dropbox_oauth_start(
    token: str = Query(..., description="User JWT"),
):
    from app.services import dropbox_service
    user_id = verify_token(token)
    if not user_id:
        raise HTTPException(status_code=401, detail="Invalid token")
    url = dropbox_service.get_auth_url(_dropbox_redirect_uri(), state=token)
    return RedirectResponse(url=url)


@router.get("/oauth/dropbox/callback")
async def dropbox_oauth_callback(
    code: str = Query(...),
    state: str = Query(...),
    db: AsyncSession = Depends(get_db),
):
    from app.services import dropbox_service
    user_id = verify_token(state)
    if not user_id:
        raise HTTPException(status_code=401, detail="Invalid state token")

    try:
        token_data = await dropbox_service.exchange_code(code, _dropbox_redirect_uri())
        user_info = await dropbox_service.get_user_info(token_data["access_token"])
    except Exception as exc:
        logger.error("Dropbox OAuth callback failed: %s", exc)
        return RedirectResponse(url=f"{settings.frontend_url}/pipelines?error=dropbox_oauth")

    expires_at = datetime.utcnow() + timedelta(seconds=token_data.get("expires_in", 14400) - 60)
    email = user_info.get("email")
    name = user_info.get("name", {}).get("display_name", "")

    conn = await _get_connection(db, user_id, "dropbox")
    if conn:
        conn.access_token = token_data["access_token"]
        if "refresh_token" in token_data:
            conn.refresh_token = token_data["refresh_token"]
        conn.token_expires_at = expires_at
        conn.account_email = email
        conn.account_name = name
        conn.updated_at = datetime.utcnow()
    else:
        conn = OAuthConnection(
            user_id=user_id,
            provider="dropbox",
            access_token=token_data["access_token"],
            refresh_token=token_data.get("refresh_token"),
            token_expires_at=expires_at,
            account_email=email,
            account_name=name,
        )
        db.add(conn)

    await db.commit()
    logger.info("Dropbox connected for user_id=%s email=%s", user_id, email)
    return RedirectResponse(url=f"{settings.frontend_url}/pipelines?connected=dropbox")


# ── OAuth: Box ────────────────────────────────────────────────────────────────

@router.get("/oauth/box")
async def box_oauth_start(
    token: str = Query(..., description="User JWT"),
):
    from app.services import box_service
    user_id = verify_token(token)
    if not user_id:
        raise HTTPException(status_code=401, detail="Invalid token")
    url = box_service.get_auth_url(_box_redirect_uri(), state=token)
    return RedirectResponse(url=url)


@router.get("/oauth/box/callback")
async def box_oauth_callback(
    code: str = Query(...),
    state: str = Query(...),
    db: AsyncSession = Depends(get_db),
):
    from app.services import box_service
    user_id = verify_token(state)
    if not user_id:
        raise HTTPException(status_code=401, detail="Invalid state token")

    try:
        token_data = await box_service.exchange_code(code, _box_redirect_uri())
        user_info = await box_service.get_user_info(token_data["access_token"])
    except Exception as exc:
        logger.error("Box OAuth callback failed: %s", exc)
        return RedirectResponse(url=f"{settings.frontend_url}/pipelines?error=box_oauth")

    expires_at = datetime.utcnow() + timedelta(seconds=token_data.get("expires_in", 3600) - 60)
    email = user_info.get("login", "")
    name = user_info.get("name", "")

    conn = await _get_connection(db, user_id, "box")
    if conn:
        conn.access_token = token_data["access_token"]
        if "refresh_token" in token_data:
            conn.refresh_token = token_data["refresh_token"]
        conn.token_expires_at = expires_at
        conn.account_email = email
        conn.account_name = name
        conn.updated_at = datetime.utcnow()
    else:
        conn = OAuthConnection(
            user_id=user_id,
            provider="box",
            access_token=token_data["access_token"],
            refresh_token=token_data.get("refresh_token"),
            token_expires_at=expires_at,
            account_email=email,
            account_name=name,
        )
        db.add(conn)

    await db.commit()
    logger.info("Box connected for user_id=%s email=%s", user_id, email)
    return RedirectResponse(url=f"{settings.frontend_url}/pipelines?connected=box")


# ── OAuth: Disconnect ─────────────────────────────────────────────────────────

@router.delete("/oauth/{provider}")
async def disconnect_provider(
    provider: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Disconnect a provider (delete stored tokens)."""
    if provider not in ("google_drive", "sharepoint", "dropbox", "box", "outlook"):
        raise HTTPException(status_code=400, detail="Unknown provider")
    # "outlook" uses the same "sharepoint" connection
    if provider == "outlook":
        provider = "sharepoint"
    conn = await _get_connection(db, current_user.id, provider)
    if conn:
        await db.delete(conn)
        await db.commit()
    return {"ok": True}


# ── Connections list ──────────────────────────────────────────────────────────

@router.get("/connections")
async def list_connections(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Return which providers are connected."""
    result = await db.execute(
        select(OAuthConnection).where(OAuthConnection.user_id == current_user.id)
    )
    conns = result.scalars().all()
    providers = {c.provider: c for c in conns}
    ms_email = providers["sharepoint"].account_email if "sharepoint" in providers else None
    return {
        "google_drive": providers["google_drive"].account_email if "google_drive" in providers else None,
        "sharepoint": ms_email,
        "dropbox": providers["dropbox"].account_email if "dropbox" in providers else None,
        "box": providers["box"].account_email if "box" in providers else None,
        # Outlook uses the same Microsoft connection as SharePoint
        "outlook": ms_email,
    }


# ── Folder browsing ───────────────────────────────────────────────────────────

@router.get("/folders/google")
async def list_google_folders(
    parent_id: str = Query("root"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    from app.services import gdrive_service
    conn = await _get_connection(db, current_user.id, "google_drive")
    if not conn:
        raise HTTPException(status_code=400, detail="Google Drive not connected")
    token = await gdrive_service.ensure_fresh_token(conn, db)
    folders = await gdrive_service.list_folders(token, parent_id)
    return {"folders": folders, "parent_id": parent_id}


@router.get("/folders/microsoft")
async def list_microsoft_folders(
    folder_id: str = Query("root"),
    drive_id: Optional[str] = Query(None),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    from app.services import sharepoint_service
    conn = await _get_connection(db, current_user.id, "sharepoint")
    if not conn:
        raise HTTPException(status_code=400, detail="SharePoint not connected")
    token = await sharepoint_service.ensure_fresh_token(conn, db)
    folders = await sharepoint_service.list_folders(token, folder_id, drive_id)
    return {"folders": folders, "folder_id": folder_id}


@router.get("/mail-folders")
async def list_outlook_folders(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List Outlook mail folders (Inbox, Sent, etc.) for the connected Microsoft account."""
    from app.services import sharepoint_service, outlook_service
    conn = await _get_connection(db, current_user.id, "sharepoint")
    if not conn:
        raise HTTPException(status_code=400, detail="Microsoft account not connected")
    token = await sharepoint_service.ensure_fresh_token(conn, db)
    folders = await outlook_service.list_mail_folders(token)
    return {"folders": folders}


@router.get("/folders/dropbox")
async def list_dropbox_folders(
    folder_id: str = Query("root"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    from app.services import dropbox_service
    conn = await _get_connection(db, current_user.id, "dropbox")
    if not conn:
        raise HTTPException(status_code=400, detail="Dropbox not connected")
    token = await dropbox_service.ensure_fresh_token(conn, db)
    folders = await dropbox_service.list_folders(token, folder_id)
    return {"folders": folders, "folder_id": folder_id}


@router.get("/folders/box")
async def list_box_folders(
    folder_id: str = Query("0"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    from app.services import box_service
    conn = await _get_connection(db, current_user.id, "box")
    if not conn:
        raise HTTPException(status_code=400, detail="Box not connected")
    token = await box_service.ensure_fresh_token(conn, db)
    folders = await box_service.list_folders(token, folder_id)
    return {"folders": folders, "folder_id": folder_id}


# ── Pipeline CRUD ─────────────────────────────────────────────────────────────

class PipelineCreateRequest(BaseModel):
    name: str
    source_type: str
    source_folder_id: str
    source_folder_name: str
    source_config: Optional[Dict[str, Any]] = None  # Outlook: {from_filter, subject_filter, mark_as_read}
    dest_folder_id: str
    dest_folder_name: str
    dest_format: str = "xlsx"
    fields: List[Dict[str, Any]]


class PipelineUpdateRequest(BaseModel):
    name: Optional[str] = None
    status: Optional[str] = None
    fields: Optional[List[Dict[str, Any]]] = None
    dest_format: Optional[str] = None
    source_folder_id: Optional[str] = None
    source_folder_name: Optional[str] = None
    source_config: Optional[Dict[str, Any]] = None
    dest_folder_id: Optional[str] = None
    dest_folder_name: Optional[str] = None


@router.get("/")
async def list_pipelines(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List all pipelines for the current user, with last 3 runs each."""
    result = await db.execute(
        select(Pipeline)
        .where(Pipeline.user_id == current_user.id)
        .order_by(Pipeline.created_at.desc())
    )
    pipelines = result.scalars().all()

    out = []
    for p in pipelines:
        runs_result = await db.execute(
            select(PipelineRun)
            .where(PipelineRun.pipeline_id == p.id)
            .order_by(PipelineRun.started_at.desc())
            .limit(3)
        )
        runs = runs_result.scalars().all()
        out.append(_pipeline_dict(p, runs))

    return {"pipelines": out}


@router.post("/")
async def create_pipeline(
    body: PipelineCreateRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Create a new pipeline."""
    from app.services.subscription_tiers import get_tier
    tier = get_tier(current_user.subscription_tier or "free")
    if not tier.has_pipeline:
        raise HTTPException(
            status_code=403,
            detail="Pipeline auto-processing requires a Business plan. Upgrade in Settings.",
        )

    cleaned_name = (body.name or "").strip()
    if not cleaned_name:
        raise HTTPException(status_code=400, detail="Pipeline name is required")
    if body.source_type not in ("google_drive", "sharepoint", "dropbox", "box", "outlook"):
        raise HTTPException(status_code=400, detail="Invalid source_type")
    if body.dest_format not in ("xlsx", "csv"):
        raise HTTPException(status_code=400, detail="Invalid dest_format")
    if not body.fields:
        raise HTTPException(status_code=400, detail="At least one extraction field is required")

    # Outlook uses the Microsoft (sharepoint) connection
    oauth_provider = "sharepoint" if body.source_type == "outlook" else body.source_type
    conn = await _get_connection(db, current_user.id, oauth_provider)
    if not conn:
        provider_name = {
            "google_drive": "Google Drive",
            "sharepoint": "SharePoint",
            "dropbox": "Dropbox",
            "box": "Box",
            "outlook": "Microsoft account",
        }[body.source_type]
        raise HTTPException(
            status_code=400,
            detail=f"{provider_name} not connected",
        )

    pipeline = Pipeline(
        user_id=current_user.id,
        name=cleaned_name,
        source_type=body.source_type,
        source_folder_id=body.source_folder_id,
        source_folder_name=body.source_folder_name,
        source_config=body.source_config or {},
        dest_folder_id=body.dest_folder_id,
        dest_folder_name=body.dest_folder_name,
        dest_format=body.dest_format,
        fields=body.fields,
        processed_file_ids=[],
        status="active",
    )
    db.add(pipeline)
    await db.commit()
    await db.refresh(pipeline)

    logger.info("Pipeline created — id=%s user_id=%s name=%r", pipeline.id, current_user.id, pipeline.name)
    return _pipeline_dict(pipeline, [])


@router.patch("/{pipeline_id}")
async def update_pipeline(
    pipeline_id: str,
    body: PipelineUpdateRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Update pipeline name, status, or fields."""
    result = await db.execute(
        select(Pipeline).where(
            Pipeline.id == pipeline_id,
            Pipeline.user_id == current_user.id,
        )
    )
    pipeline = result.scalar_one_or_none()
    if not pipeline:
        raise HTTPException(status_code=404, detail="Pipeline not found")

    if body.name is not None:
        cleaned_name = body.name.strip()
        if not cleaned_name:
            raise HTTPException(status_code=400, detail="Pipeline name is required")
        pipeline.name = cleaned_name
    if body.status is not None:
        if body.status not in ("active", "paused"):
            raise HTTPException(status_code=400, detail="Status must be 'active' or 'paused'")
        pipeline.status = body.status
    if body.fields is not None:
        pipeline.fields = body.fields
    if body.dest_format is not None:
        if body.dest_format not in ("xlsx", "csv"):
            raise HTTPException(status_code=400, detail="dest_format must be 'xlsx' or 'csv'")
        pipeline.dest_format = body.dest_format
    if body.source_folder_id is not None:
        pipeline.source_folder_id = body.source_folder_id
    if body.source_folder_name is not None:
        pipeline.source_folder_name = body.source_folder_name
    if body.dest_folder_id is not None:
        pipeline.dest_folder_id = body.dest_folder_id
    if body.dest_folder_name is not None:
        pipeline.dest_folder_name = body.dest_folder_name
    if body.source_config is not None:
        pipeline.source_config = body.source_config

    pipeline.updated_at = datetime.utcnow()
    await db.commit()

    runs_result = await db.execute(
        select(PipelineRun)
        .where(PipelineRun.pipeline_id == pipeline.id)
        .order_by(PipelineRun.started_at.desc())
        .limit(3)
    )
    runs = runs_result.scalars().all()
    return _pipeline_dict(pipeline, runs)


@router.delete("/{pipeline_id}")
async def delete_pipeline(
    pipeline_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Pipeline).where(
            Pipeline.id == pipeline_id,
            Pipeline.user_id == current_user.id,
        )
    )
    pipeline = result.scalar_one_or_none()
    if not pipeline:
        raise HTTPException(status_code=404, detail="Pipeline not found")

    await db.execute(
        delete(PipelineRun).where(PipelineRun.pipeline_id == pipeline.id)
    )
    await db.delete(pipeline)
    await db.commit()
    return {"ok": True}


@router.get("/{pipeline_id}/runs")
async def list_runs(
    pipeline_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List last 20 runs for a pipeline."""
    # Verify ownership
    result = await db.execute(
        select(Pipeline).where(
            Pipeline.id == pipeline_id,
            Pipeline.user_id == current_user.id,
        )
    )
    if not result.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="Pipeline not found")

    runs_result = await db.execute(
        select(PipelineRun)
        .where(PipelineRun.pipeline_id == pipeline_id)
        .order_by(PipelineRun.started_at.desc())
        .limit(20)
    )
    runs = runs_result.scalars().all()
    return {"runs": [_run_dict(r) for r in runs]}


@router.post("/{pipeline_id}/run")
async def manual_trigger(
    pipeline_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Manually trigger a pipeline check right now."""
    from app.workers.pipeline_poller import _check_pipeline

    result = await db.execute(
        select(Pipeline).where(
            Pipeline.id == pipeline_id,
            Pipeline.user_id == current_user.id,
        )
    )
    pipeline = result.scalar_one_or_none()
    if not pipeline:
        raise HTTPException(status_code=404, detail="Pipeline not found")

    # Run check as a background task (fire-and-forget)
    import asyncio
    asyncio.create_task(_check_pipeline(pipeline))

    return {"ok": True, "message": "Pipeline check triggered"}


@router.get("/runs/{run_id}/logs")
async def get_run_logs(
    run_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Fetch log lines for a specific run (ownership verified via user_id)."""
    result = await db.execute(
        select(PipelineRun).where(
            PipelineRun.id == run_id,
            PipelineRun.user_id == current_user.id,
        )
    )
    run = result.scalar_one_or_none()
    if not run:
        raise HTTPException(status_code=404, detail="Run not found")
    return {
        "run_id": run_id,
        "status": run.status,
        "log_lines": run.log_lines or [],
    }
