"""
Form filling routes.

POST /form-filling/fill          — upload a target PDF form + source files, returns filled PDF (JWT auth)
POST /form-filling/fill-service  — same, but auth via X-GridPull-Service-Token (no JWT needed)
"""

import logging
import os
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Request, UploadFile, File, Form
from fastapi.responses import Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.middleware.auth_middleware import get_current_user
from app.models.user import User
from app.routes.documents import _assert_valid_service_token, _load_service_account_user
from app.services.form_filling import PDFPopulator
from app.services.subscription_tiers import MAX_FILE_SIZE_MB, get_tier

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/form-filling", tags=["form-filling"])

_ALLOWED_SOURCE_EXTS = {
    ".pdf", ".png", ".jpg", ".jpeg", ".webp", ".gif", ".bmp", ".tif", ".tiff",
    ".txt", ".md", ".markdown", ".html", ".htm", ".json", ".xml", ".eml", ".emlx", ".msg",
}


@router.post("/fill")
async def fill_form(
    target_form: UploadFile = File(...),
    source_files: List[UploadFile] = File(...),
    force_claude: Optional[str] = Form(None),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Upload a target PDF form and source files. Returns the filled PDF."""
    from app.routes.payments import _maybe_reset_usage

    target_name = (target_form.filename or "").lower()
    if not target_name.endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Target form must be a PDF file")

    target_bytes = await target_form.read()
    if not target_bytes:
        raise HTTPException(status_code=400, detail="Target form file is empty")
    if len(target_bytes) > MAX_FILE_SIZE_MB * 1024 * 1024:
        raise HTTPException(status_code=413, detail=f"Target form exceeds the {MAX_FILE_SIZE_MB} MB size limit")

    source_data: list[tuple[str, bytes]] = []
    for sf in source_files:
        fname = sf.filename or "unknown"
        ext = os.path.splitext(fname.lower())[1]
        if ext not in _ALLOWED_SOURCE_EXTS:
            logger.warning("Skipping unsupported source file: %s", fname)
            continue
        content = await sf.read()
        if not content:
            continue
        if len(content) > MAX_FILE_SIZE_MB * 1024 * 1024:
            raise HTTPException(status_code=413, detail=f"File '{fname}' exceeds the {MAX_FILE_SIZE_MB} MB size limit")
        source_data.append((fname, content))

    if not source_data:
        raise HTTPException(status_code=400, detail="No valid source files provided")

    result = await db.execute(select(User).where(User.id == current_user.id))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    tier = get_tier(user.subscription_tier)
    _maybe_reset_usage(user)
    await db.commit()
    await db.refresh(user)

    used = user.pages_used_this_period or 0
    form_fill_cost = 5  # pages per form fill
    if tier.name == "free" and used + form_fill_cost > tier.pages_per_month:
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

    user.pages_used_this_period = used + form_fill_cost
    if user.pages_used_this_period > tier.pages_per_month:
        user.overage_pages_this_period = (user.overage_pages_this_period or 0) + form_fill_cost
    await db.commit()
    try:
        from app.cache import cache_del_user
        await cache_del_user(str(user.id))
    except Exception:
        pass

    logger.info(
        "Form fill request — user_id=%s target=%s sources=%d pages=%d",
        current_user.id, target_form.filename, len(source_data), form_fill_cost,
    )

    try:
        populator = PDFPopulator()
        use_claude = force_claude and force_claude.lower() in ("1", "true", "yes")
        filled_pdf, cost, model_breakdown = await populator.populate_async(
            source_data, target_bytes, force_claude=use_claude,
        )
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    except Exception as e:
        logger.error("Form filling failed: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail="Form filling failed — please try again")

    # Re-fetch user to get the latest balance (populate_async can take many seconds)
    result = await db.execute(select(User).where(User.id == current_user.id))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    # Deduct actual cost from user balance
    balance_before = user.balance or 0.0
    user.balance = max(0.0, balance_before - cost)
    await db.commit()

    logger.info(
        "Form fill complete — user_id=%s cost=$%.6f balance=%.6f→%.6f size=%d bytes",
        current_user.id, cost, balance_before, user.balance, len(filled_pdf),
    )

    output_name = f"filled_{target_form.filename or 'form.pdf'}"
    return Response(
        content=filled_pdf,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{output_name}"'},
    )


@router.post("/fill-service", include_in_schema=False)
async def fill_form_service(
    request: Request,
    target_form: UploadFile = File(...),
    source_files: List[UploadFile] = File(...),
    service_token: Optional[str] = Form(None),
    force_claude: Optional[str] = Form(None),
    db: AsyncSession = Depends(get_db),
):
    """Same as /fill but auth via X-GridPull-Service-Token header or service_token form field.

    Uses the configured SERVICE_EXTRACTION_USER_ID account for billing.
    """
    _assert_valid_service_token(request, form_token=service_token)
    svc_user = await _load_service_account_user(db)

    target_name = (target_form.filename or "").lower()
    if not target_name.endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Target form must be a PDF file")

    target_bytes = await target_form.read()
    if not target_bytes:
        raise HTTPException(status_code=400, detail="Target form file is empty")
    if len(target_bytes) > MAX_FILE_SIZE_MB * 1024 * 1024:
        raise HTTPException(status_code=413, detail=f"Target form exceeds the {MAX_FILE_SIZE_MB} MB size limit")

    source_data: list[tuple[str, bytes]] = []
    for sf in source_files:
        fname = sf.filename or "unknown"
        ext = os.path.splitext(fname.lower())[1]
        if ext not in _ALLOWED_SOURCE_EXTS:
            logger.warning("Skipping unsupported source file: %s", fname)
            continue
        content = await sf.read()
        if not content:
            continue
        if len(content) > MAX_FILE_SIZE_MB * 1024 * 1024:
            raise HTTPException(status_code=413, detail=f"File '{fname}' exceeds the {MAX_FILE_SIZE_MB} MB size limit")
        source_data.append((fname, content))

    if not source_data:
        raise HTTPException(status_code=400, detail="No valid source files provided")

    logger.info(
        "Form fill service request — user_id=%s target=%s sources=%d",
        svc_user.id, target_form.filename, len(source_data),
    )

    try:
        populator = PDFPopulator()
        use_claude = force_claude and force_claude.lower() in ("1", "true", "yes")
        filled_pdf, cost, model_breakdown = await populator.populate_async(
            source_data, target_bytes, force_claude=use_claude,
        )
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    except Exception as e:
        logger.error("Form filling (service) failed: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail="Form filling failed — please try again")

    # Deduct cost from service account balance
    result = await db.execute(select(User).where(User.id == svc_user.id))
    user = result.scalar_one_or_none()
    if user:
        balance_before = user.balance or 0.0
        user.balance = max(0.0, balance_before - cost)
        await db.commit()
        logger.info(
            "Form fill service complete — user_id=%s cost=$%.6f balance=%.6f→%.6f size=%d bytes",
            svc_user.id, cost, balance_before, user.balance, len(filled_pdf),
        )

    output_name = f"filled_{target_form.filename or 'form.pdf'}"
    return Response(
        content=filled_pdf,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{output_name}"'},
    )
