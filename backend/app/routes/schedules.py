"""Schedules route — proxies to Papyra's Claude-backed Schedules extractor.

Exposed endpoints (all JWT-authenticated on the GridPull side):
  POST /api/schedules/prepare        → spreadsheet headers + suggested fields (free)
  POST /api/schedules/extract        → returns the final XLSX bytes (blocking, billed)
  POST /api/schedules/extract-rows   → returns structured JSON rows (billed)
  GET  /api/schedules/types          → list of schedule-type slugs + labels

The caller forwards a GridPull user request (with any combination of PDFs,
images, emails, or a baseline spreadsheet) to Papyra via HTTP Basic auth
against /api/statements/{prepare,extract,extract-rows}-service. GridPull
polls the job for us and returns the finished file in a single response so
existing callers don't need to deal with two round-trips.

Billing mirrors documents.py: per-PDF-page for PDFs, 1 page for everything
else. /prepare is free (metadata only). On any failure after billing, the
debit is refunded.
"""
from __future__ import annotations

import asyncio
import json
import logging
from typing import List, Optional

import fitz
import httpx
from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import get_db
from app.middleware.auth_middleware import get_current_user
from app.models.user import User
from app.services.subscription_tiers import MAX_FILE_SIZE_MB, get_tier

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/schedules", tags=["schedules"])


_SUPPORTED_EXT = (
    ".pdf", ".png", ".jpg", ".jpeg", ".gif", ".webp",
    ".txt", ".md", ".eml", ".msg", ".html", ".htm", ".json", ".xml", ".tsv",
)
_SPREADSHEET_EXT = (".xlsx", ".xls", ".csv")

# Default schedule types — mirrors Papyra's SCHEDULE_TYPE_FIELDS keys so
# frontend callers don't need a round-trip just to populate a picker.
SCHEDULE_TYPES: list[dict[str, str]] = [
    {"value": "property",    "label": "Property / Statement of Values"},
    {"value": "vehicles",    "label": "Vehicles"},
    {"value": "drivers",     "label": "Drivers"},
    {"value": "workers_comp", "label": "Workers Comp (Employees)"},
    {"value": "equipment",   "label": "Contractor's Equipment"},
    {"value": "aircraft",    "label": "Aircraft"},
    {"value": "events",      "label": "Special Events"},
    {"value": "cargo",       "label": "Motor Truck Cargo"},
    {"value": "hazards",     "label": "Catastrophe / Hazards"},
    {"value": "custom",      "label": "Custom"},
]
_VALID_SCHEDULE_TYPES = {t["value"] for t in SCHEDULE_TYPES}


def _require_schedules_creds() -> None:
    missing: list[str] = []
    if not settings.papyra_schedules_username:
        missing.append("PAPYRA_SCHEDULES_USERNAME")
    if not settings.papyra_schedules_password:
        missing.append("PAPYRA_SCHEDULES_PASSWORD")
    if missing:
        logger.error("Schedules creds missing: %s", ", ".join(missing))
        raise HTTPException(
            status_code=503,
            detail=f"Schedules service not configured (missing: {', '.join(missing)})",
        )


def _basic_auth() -> tuple[str, str]:
    return (settings.papyra_schedules_username, settings.papyra_schedules_password)


def _normalize_schedule_type(value: Optional[str], *, default: str = "property") -> str:
    v = (value or default).strip().lower()
    if v not in _VALID_SCHEDULE_TYPES:
        raise HTTPException(
            status_code=400,
            detail=(
                f"Unknown schedule_type {value!r}. Valid: "
                + ", ".join(sorted(_VALID_SCHEDULE_TYPES))
            ),
        )
    return v


def _classify(files: list[UploadFile]) -> tuple[list[UploadFile], list[UploadFile]]:
    spreadsheet: list[UploadFile] = []
    docs: list[UploadFile] = []
    for f in files:
        name = (f.filename or "").lower()
        if any(name.endswith(e) for e in _SPREADSHEET_EXT):
            spreadsheet.append(f)
        elif any(name.endswith(e) for e in _SUPPORTED_EXT):
            docs.append(f)
        else:
            raise HTTPException(
                status_code=400,
                detail=(
                    f"Unsupported file type: {f.filename!r}. Supported: PDF, images, "
                    "text, HTML, emails, plus CSV/XLSX as baseline spreadsheet."
                ),
            )
    return spreadsheet, docs


async def _read_and_pack(
    files: list[UploadFile],
) -> tuple[list[tuple[str, tuple[str, bytes, str]]], int]:
    """Read every upload, enforce size cap, and return (httpx-files, billable_pages).

    Billing:
      - PDFs charge max(1, page_count) pages.
      - Everything else (spreadsheet, image, text, html, email) charges 1 page.
    """
    out: list[tuple[str, tuple[str, bytes, str]]] = []
    max_bytes = MAX_FILE_SIZE_MB * 1024 * 1024
    pages = 0
    for f in files:
        data = await f.read()
        if not data:
            continue
        if len(data) > max_bytes:
            raise HTTPException(
                status_code=413,
                detail=f"File '{f.filename}' exceeds the {MAX_FILE_SIZE_MB} MB size limit.",
            )
        mime = f.content_type or "application/octet-stream"
        name = f.filename or "document.bin"
        ext = ("." + name.rsplit(".", 1)[-1].lower()) if "." in name else ""
        if ext == ".pdf":
            try:
                pdf = fitz.open(stream=data, filetype="pdf")
                pages += max(1, len(pdf))
                pdf.close()
            except Exception as exc:
                raise HTTPException(
                    status_code=422, detail=f"Could not read PDF '{name}': {exc.__class__.__name__}",
                )
        else:
            pages += 1
        out.append(("files", (name, data, mime)))
    return out, pages


async def _check_quota_and_charge(
    db: AsyncSession, user: User, num_pages: int
) -> tuple[int, bool]:
    """Reserve `num_pages` against the user's quota. Returns (committed_pages,
    over_quota). Raises 402 for free-tier users that would exceed their cap.
    """
    from app.routes.payments import _maybe_reset_usage

    tier = get_tier(user.subscription_tier)
    _maybe_reset_usage(user)
    await db.commit()
    await db.refresh(user)

    used = user.pages_used_this_period or 0
    if tier.name == "free" and used + num_pages > tier.pages_per_month:
        raise HTTPException(
            status_code=402,
            detail={
                "type": "page_limit_reached",
                "message": f"Free plan allows {tier.pages_per_month:,} pages/month. You've used {used:,}.",
                "pages_used": used,
                "pages_limit": tier.pages_per_month,
                "tier": tier.name,
            },
        )

    user.pages_used_this_period = used + num_pages
    over_quota = user.pages_used_this_period > tier.pages_per_month
    if over_quota:
        user.overage_pages_this_period = (user.overage_pages_this_period or 0) + num_pages
    await db.commit()
    try:
        from app.cache import cache_del_user
        await cache_del_user(str(user.id))
    except Exception:
        pass
    return num_pages, over_quota


async def _refund_pages(
    db: AsyncSession, user_id, num_pages: int, over_quota: bool, reason: str
) -> None:
    if num_pages <= 0:
        return
    try:
        r = await db.execute(select(User).where(User.id == user_id))
        u = r.scalar_one_or_none()
        if not u:
            return
        u.pages_used_this_period = max(0, (u.pages_used_this_period or 0) - num_pages)
        if over_quota:
            u.overage_pages_this_period = max(0, (u.overage_pages_this_period or 0) - num_pages)
        await db.commit()
        try:
            from app.cache import cache_del_user
            await cache_del_user(str(u.id))
        except Exception:
            pass
        logger.info("Schedules refund — user_id=%s pages=%d reason=%s", user_id, num_pages, reason)
    except Exception:
        logger.exception("Schedules refund failed (user=%s)", user_id)


def _papyra_error(resp: httpx.Response) -> HTTPException:
    try:
        detail = resp.json().get("detail", resp.text[:400])
    except Exception:  # noqa: BLE001
        detail = resp.text[:400]
    status = resp.status_code if resp.status_code < 500 else 502
    return HTTPException(status_code=status, detail=str(detail))


@router.get("/types")
async def list_schedule_types(_current_user: User = Depends(get_current_user)):
    """Return the 10 Papyra schedule-type slugs + human labels."""
    return {"types": SCHEDULE_TYPES}


@router.post("/prepare")
async def prepare_schedule(
    files: List[UploadFile] = File(...),
    customer_name: Optional[str] = Form(""),
    description: Optional[str] = Form(""),
    schedule_type: Optional[str] = Form("property"),
    current_user: User = Depends(get_current_user),
):
    """Classify uploads and return suggested extraction fields. Free — metadata only.

    Delegates to Papyra /api/statements/prepare-service. When a spreadsheet is
    uploaded alongside a source document, the returned ``suggested_fields`` come
    from the spreadsheet's column headers — use those directly to skip the
    field-review step on the frontend.
    """
    _require_schedules_creds()
    schedule_type = _normalize_schedule_type(schedule_type)
    spreadsheets, docs = _classify(files)
    uploads, _pages = await _read_and_pack(spreadsheets + docs)
    if not uploads:
        raise HTTPException(status_code=400, detail="No files provided.")

    data = {
        "customer_name": customer_name or "",
        "description": description or "",
        "schedule_type": schedule_type,
    }
    try:
        async with httpx.AsyncClient(timeout=120) as client:
            resp = await client.post(
                f"{settings.papyra_schedules_base_url}/api/statements/prepare-service",
                data=data,
                files=uploads,
                auth=_basic_auth(),
            )
    except httpx.HTTPError as exc:
        logger.exception("Papyra prepare-service transport failure (user=%s)", current_user.id)
        raise HTTPException(status_code=502, detail=f"Schedules service unreachable: {exc.__class__.__name__}")

    if resp.status_code >= 400:
        logger.error(
            "Papyra prepare-service %s for user=%s: %s",
            resp.status_code, current_user.id, resp.text[:400],
        )
        raise _papyra_error(resp)
    return resp.json()


@router.post("/extract")
async def extract_schedule(
    files: List[UploadFile] = File(...),
    fields_json: str = Form(""),
    customer_name: Optional[str] = Form(""),
    description: Optional[str] = Form(""),
    schedule_type: Optional[str] = Form("property"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Run the full extraction and return the styled XLSX bytes.

    Papyra's extract-service returns a ``job_id`` immediately; we poll
    ``jobs-service/{id}`` with exponential backoff until complete and then
    fetch the download in one shot so GridPull callers get a single response.
    """
    _require_schedules_creds()
    if not fields_json or not fields_json.strip():
        raise HTTPException(status_code=400, detail="fields_json is required.")
    try:
        parsed_fields = json.loads(fields_json)
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=400, detail=f"fields_json is not valid JSON: {exc.msg}")
    if not isinstance(parsed_fields, list) or not parsed_fields:
        raise HTTPException(status_code=400, detail="fields_json must be a non-empty JSON array of field objects.")
    schedule_type = _normalize_schedule_type(schedule_type)
    spreadsheets, docs = _classify(files)
    uploads, billable_pages = await _read_and_pack(spreadsheets + docs)
    if not uploads:
        raise HTTPException(status_code=400, detail="No files provided.")

    result = await db.execute(select(User).where(User.id == current_user.id))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    charged_pages, over_quota = await _check_quota_and_charge(db, user, billable_pages)

    base = settings.papyra_schedules_base_url
    data = {
        "fields_json": fields_json,
        "customer_name": customer_name or "",
        "description": description or "",
        "schedule_type": schedule_type,
    }

    try:
        async with httpx.AsyncClient(timeout=900) as client:
            try:
                start_resp = await client.post(
                    f"{base}/api/statements/extract-service",
                    data=data,
                    files=uploads,
                    auth=_basic_auth(),
                )
            except httpx.HTTPError as exc:
                logger.exception("Papyra extract-service transport failure (user=%s)", current_user.id)
                raise HTTPException(
                    status_code=502,
                    detail=f"Schedules service unreachable: {exc.__class__.__name__}",
                )
            if start_resp.status_code >= 400:
                logger.error(
                    "Papyra extract-service %s for user=%s: %s",
                    start_resp.status_code, current_user.id, start_resp.text[:400],
                )
                raise _papyra_error(start_resp)

            job_id = (start_resp.json() or {}).get("job_id")
            if not job_id:
                raise HTTPException(status_code=502, detail="Papyra did not return a job_id")

            # Exponential backoff: start at 2s, double up to 30s, cap total wait at 30 min.
            deadline = 60 * 30  # seconds
            waited = 0.0
            backoff = 2.0
            while True:
                if waited >= deadline:
                    raise HTTPException(status_code=504, detail="Schedules extraction timed out")
                status_resp = await client.get(
                    f"{base}/api/statements/extract/jobs-service/{job_id}",
                    auth=_basic_auth(),
                )
                if status_resp.status_code >= 400:
                    raise HTTPException(
                        status_code=502,
                        detail=f"Job status check failed: {status_resp.text[:300]}",
                    )
                meta = status_resp.json() or {}
                state = str(meta.get("status") or "")
                if state == "complete":
                    break
                if state == "error":
                    raise HTTPException(status_code=400, detail=meta.get("error") or "Extraction failed")
                await asyncio.sleep(backoff)
                waited += backoff
                backoff = min(backoff * 1.5, 30.0)

            dl = await client.get(
                f"{base}/api/statements/extract/jobs-service/{job_id}/download",
                auth=_basic_auth(),
            )
            if dl.status_code >= 400:
                raise HTTPException(
                    status_code=502,
                    detail=f"Job download failed: {dl.text[:300]}",
                )
    except HTTPException as exc:
        # 4xx user error — refund. 5xx upstream error — refund too: the user
        # got nothing back, so we can't keep their pages.
        await _refund_pages(db, current_user.id, charged_pages, over_quota,
                            f"extract_failed_{exc.status_code}")
        raise
    except Exception as exc:
        await _refund_pages(db, current_user.id, charged_pages, over_quota,
                            f"extract_internal_{exc.__class__.__name__}")
        raise

    logger.info(
        "Schedules extraction complete — user=%s schedule_type=%s pages=%d xlsx_bytes=%d",
        current_user.id, schedule_type, charged_pages, len(dl.content),
    )
    return Response(
        content=dl.content,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={
            "Content-Disposition": 'attachment; filename="sov_extraction.xlsx"',
        },
    )


@router.post("/extract-rows")
async def extract_schedule_rows(
    schedule_type: str = Form(..., description="One of the SCHEDULE_TYPES slugs"),
    files: List[UploadFile] = File(...),
    customer_name: Optional[str] = Form(""),
    description: Optional[str] = Form(""),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Synchronous JSON-rows variant, for callers that want to render rows
    directly in the UI instead of downloading an XLSX."""
    _require_schedules_creds()
    schedule_type = _normalize_schedule_type(schedule_type)
    spreadsheets, docs = _classify(files)
    uploads, billable_pages = await _read_and_pack(spreadsheets + docs)
    if not uploads:
        raise HTTPException(status_code=400, detail="No files provided.")

    result = await db.execute(select(User).where(User.id == current_user.id))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    charged_pages, over_quota = await _check_quota_and_charge(db, user, billable_pages)

    data = {
        "schedule_type": schedule_type,
        "customer_name": customer_name or "",
        "description": description or "",
    }
    try:
        async with httpx.AsyncClient(timeout=900) as client:
            resp = await client.post(
                f"{settings.papyra_schedules_base_url}/api/statements/extract-rows-service",
                data=data,
                files=uploads,
                auth=_basic_auth(),
            )
    except httpx.HTTPError as exc:
        logger.exception("Papyra extract-rows-service transport failure (user=%s)", current_user.id)
        await _refund_pages(db, current_user.id, charged_pages, over_quota,
                            f"rows_transport_{exc.__class__.__name__}")
        raise HTTPException(
            status_code=502,
            detail=f"Schedules service unreachable: {exc.__class__.__name__}",
        )
    if resp.status_code >= 400:
        logger.error(
            "Papyra extract-rows-service %s for user=%s: %s",
            resp.status_code, current_user.id, resp.text[:400],
        )
        await _refund_pages(db, current_user.id, charged_pages, over_quota,
                            f"rows_failed_{resp.status_code}")
        raise _papyra_error(resp)
    logger.info(
        "Schedules extract-rows complete — user=%s schedule_type=%s pages=%d",
        current_user.id, schedule_type, charged_pages,
    )
    return resp.json()
