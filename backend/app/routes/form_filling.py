"""
Form filling routes.

POST /form-filling/fill  — upload a target PDF form + source files, returns filled PDF
"""

import logging
import os
from typing import List

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from fastapi.responses import Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.middleware.auth_middleware import get_current_user
from app.models.user import User
from app.services.form_filling import PDFPopulator
from app.services.subscription_tiers import MAX_FILE_SIZE_MB, get_tier

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/form-filling", tags=["form-filling"])

_ALLOWED_SOURCE_EXTS = {".pdf", ".png", ".jpg", ".jpeg", ".webp", ".gif", ".txt", ".md", ".markdown"}


@router.post("/fill")
async def fill_form(
    target_form: UploadFile = File(...),
    source_files: List[UploadFile] = File(...),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Upload a target PDF form and source files. Returns the filled PDF."""
    from app.routes.payments import _maybe_reset_usage

    if not current_user.stripe_payment_method_id:
        raise HTTPException(
            status_code=402,
            detail={"type": "card_required", "message": "A credit card is required to use this feature. Add one in Settings."},
        )

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

    used = user.credits_used_this_period or 0
    if tier.name == "free" and used + 1 > tier.credits_per_month:
        raise HTTPException(
            status_code=402,
            detail={
                "type": "credit_limit_reached",
                "message": f"Free plan allows {tier.credits_per_month} credits/month. You've used {used}.",
                "credits_used": used,
                "credits_limit": tier.credits_per_month,
                "tier": tier.name,
            },
        )

    user.credits_used_this_period = used + 1
    if user.credits_used_this_period > tier.credits_per_month:
        user.overage_credits_this_period = (user.overage_credits_this_period or 0) + 1
    await db.commit()

    logger.info(
        "Form fill request — user_id=%s target=%s sources=%d credits=%d",
        current_user.id, target_form.filename, len(source_data), 1,
    )

    try:
        populator = PDFPopulator()
        filled_pdf, cost, model_breakdown = await populator.populate_async(source_data, target_bytes)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    except Exception as e:
        logger.error("Form filling failed: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail="Form filling failed — please try again")

    logger.info("Form fill complete — user_id=%s cost=$%.6f size=%d bytes", current_user.id, cost, len(filled_pdf))

    output_name = f"filled_{target_form.filename or 'form.pdf'}"
    return Response(
        content=filled_pdf,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{output_name}"'},
    )
