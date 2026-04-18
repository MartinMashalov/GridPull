"""Proposals route — proxies to Papyra proposals API."""
import logging
from typing import List, Optional

import httpx
from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.config import settings
from app.database import get_db
from app.middleware.auth_middleware import get_current_user
from app.models.user import User

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/proposals", tags=["proposals"])


def _require_papyra_creds() -> None:
    if not settings.papyra_user_email or not settings.papyra_user_password:
        logger.error("PAPYRA_USER_EMAIL / PAPYRA_USER_PASSWORD not configured")
        raise HTTPException(status_code=503, detail="Proposal service not configured")


@router.post("/generate")
async def generate_proposal(
    lob: str = Form(...),
    documents: List[UploadFile] = File(...),
    agency_info: str = Form(default=""),
    user_context: str = Form(default=""),
    brand_primary: str = Form(default="#1A3560"),
    brand_accent: str = Form(default="#C9901E"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Proxy proposal generation to Papyra's /api/proposals/external/generate."""
    from app.services.subscription_tiers import get_tier, PROPOSAL_PAGE_COST
    from app.routes.payments import _maybe_reset_usage

    # Load a fresh DB-bound user so tier/usage checks see the latest state,
    # not a 60s-stale Redis/in-process cached copy.
    result = await db.execute(select(User).where(User.id == current_user.id))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    tier = get_tier(user.subscription_tier or "free")
    if not tier.has_proposals:
        raise HTTPException(
            status_code=403,
            detail={"type": "upgrade_required", "message": "Proposals require a Pro plan or higher. Upgrade in Settings.", "required_tier": "pro"},
        )

    _maybe_reset_usage(user)
    await db.commit()
    await db.refresh(user)

    used = user.pages_used_this_period or 0
    if tier.name == "free" and used + PROPOSAL_PAGE_COST > tier.pages_per_month:
        raise HTTPException(
            status_code=402,
            detail={
                "type": "page_limit_reached",
                "message": f"Free plan allows {tier.pages_per_month:,} pages/month. You've used {used:,}. A proposal costs {PROPOSAL_PAGE_COST} pages.",
                "pages_used": used,
                "pages_limit": tier.pages_per_month,
                "tier": tier.name,
            },
        )

    _require_papyra_creds()

    files = []
    for doc in documents:
        content = await doc.read()
        files.append(("documents", (doc.filename or "document.pdf", content, "application/pdf")))

    data = {
        "user_email": settings.papyra_user_email,
        "user_password": settings.papyra_user_password,
        "lob": lob,
        "agency_info": agency_info,
        "user_context": user_context,
        "brand_primary": brand_primary,
        "brand_accent": brand_accent,
    }

    try:
        async with httpx.AsyncClient(timeout=600) as client:
            resp = await client.post(
                f"{settings.papyra_api_base_url}/api/proposals/external/generate",
                data=data,
                files=files,
            )
            resp.raise_for_status()
            payload = resp.json()
    except httpx.HTTPStatusError as exc:
        detail = exc.response.text[:500] if exc.response else str(exc)
        raise HTTPException(status_code=exc.response.status_code, detail=detail)
    except Exception as exc:
        logger.error("Papyra proxy failed: %s", exc)
        raise HTTPException(status_code=502, detail="Proposal service unavailable")

    # Charge pages only after Papyra succeeds
    user.pages_used_this_period = used + PROPOSAL_PAGE_COST
    if user.pages_used_this_period > tier.pages_per_month:
        user.overage_pages_this_period = (user.overage_pages_this_period or 0) + PROPOSAL_PAGE_COST
    await db.commit()

    # Bust the Redis user cache so usage endpoints reflect the new count immediately
    try:
        from app.cache import cache_del_user
        await cache_del_user(str(user.id))
    except Exception:
        pass

    logger.info(
        "Proposal generated — user_id=%s lob=%s docs=%d pages_charged=%d",
        current_user.id, lob, len(documents), PROPOSAL_PAGE_COST,
    )
    return payload


@router.get("/agency-info")
async def get_agency_info(current_user: User = Depends(get_current_user)):
    """Fetch agency info + logo from Papyra for this GridPull user's linked Papyra account."""
    _require_papyra_creds()
    data = {
        "user_email": settings.papyra_user_email,
        "user_password": settings.papyra_user_password,
    }
    try:
        async with httpx.AsyncClient(timeout=60) as client:
            resp = await client.post(
                f"{settings.papyra_api_base_url}/api/proposals/external/agency-info",
                data=data,
            )
            resp.raise_for_status()
            return resp.json()
    except httpx.HTTPStatusError as exc:
        detail = exc.response.text[:500] if exc.response else str(exc)
        raise HTTPException(status_code=exc.response.status_code, detail=detail)
    except Exception as exc:
        logger.error("Papyra agency-info GET failed: %s", exc)
        raise HTTPException(status_code=502, detail="Proposal service unavailable")


@router.put("/agency-info")
async def update_agency_info(
    content: str = Form(...),
    logo: Optional[UploadFile] = File(default=None),
    current_user: User = Depends(get_current_user),
):
    """Upsert agency info + optional logo in Papyra for this GridPull user."""
    _require_papyra_creds()
    data = {
        "user_email": settings.papyra_user_email,
        "user_password": settings.papyra_user_password,
        "content": content,
    }
    files = None
    if logo and logo.filename:
        logo_bytes = await logo.read()
        files = {"logo": (logo.filename, logo_bytes, logo.content_type or "image/png")}

    try:
        async with httpx.AsyncClient(timeout=120) as client:
            resp = await client.put(
                f"{settings.papyra_api_base_url}/api/proposals/external/agency-info",
                data=data,
                files=files,
            )
            resp.raise_for_status()
            return resp.json()
    except httpx.HTTPStatusError as exc:
        detail = exc.response.text[:500] if exc.response else str(exc)
        raise HTTPException(status_code=exc.response.status_code, detail=detail)
    except Exception as exc:
        logger.error("Papyra agency-info PUT failed: %s", exc)
        raise HTTPException(status_code=502, detail="Proposal service unavailable")
