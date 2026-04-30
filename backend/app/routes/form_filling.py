"""
Form filling routes.

POST /form-filling/fill          — upload one or more target PDF forms + source files (JWT auth)
POST /form-filling/fill-service  — same, but auth via X-GridPull-Service-Token (no JWT needed)

Multi-target: both endpoints accept up to 10 target forms (`target_forms`)
that are processed concurrently against the same source files. The legacy
single-file `target_form` field remains accepted for backward compatibility.
"""

import asyncio
import base64
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
from app.services.subscription_tiers import FORM_FILL_PAGE_COST, MAX_FILE_SIZE_MB, get_tier

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/form-filling", tags=["form-filling"])

_ALLOWED_SOURCE_EXTS = {
    ".pdf", ".png", ".jpg", ".jpeg", ".webp", ".gif", ".bmp", ".tif", ".tiff",
    ".txt", ".md", ".markdown", ".html", ".htm", ".json", ".xml", ".eml", ".emlx", ".msg",
}

MAX_TARGET_FORMS = 10


async def _read_target_forms(
    target_forms: Optional[List[UploadFile]],
    target_form: Optional[UploadFile],
) -> list[tuple[str, bytes]]:
    """Collect target PDFs from either the new (multi) or legacy (single) field.

    Returns list of (filename, bytes). Raises HTTPException on validation errors.
    """
    forms: list[UploadFile] = []
    if target_forms:
        forms.extend([f for f in target_forms if f is not None])
    if target_form is not None:
        forms.append(target_form)

    if not forms:
        raise HTTPException(status_code=400, detail="At least one target form is required")
    if len(forms) > MAX_TARGET_FORMS:
        raise HTTPException(
            status_code=400,
            detail=f"Up to {MAX_TARGET_FORMS} target forms allowed per request (got {len(forms)})",
        )

    out: list[tuple[str, bytes]] = []
    for tf in forms:
        name = (tf.filename or "").strip() or "form.pdf"
        if not name.lower().endswith(".pdf"):
            raise HTTPException(status_code=400, detail=f"Target form '{name}' must be a PDF file")
        data = await tf.read()
        if not data:
            raise HTTPException(status_code=400, detail=f"Target form '{name}' is empty")
        if len(data) > MAX_FILE_SIZE_MB * 1024 * 1024:
            raise HTTPException(
                status_code=413,
                detail=f"Target form '{name}' exceeds the {MAX_FILE_SIZE_MB} MB size limit",
            )
        out.append((name, data))
    return out


async def _read_source_files(source_files: List[UploadFile]) -> list[tuple[str, bytes]]:
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
            raise HTTPException(
                status_code=413,
                detail=f"File '{fname}' exceeds the {MAX_FILE_SIZE_MB} MB size limit",
            )
        source_data.append((fname, content))

    if not source_data:
        raise HTTPException(status_code=400, detail="No valid source files provided")
    return source_data


async def _populate_one(
    populator: PDFPopulator,
    source_data: list[tuple[str, bytes]],
    target_name: str,
    target_bytes: bytes,
    force_claude: bool,
) -> dict:
    """Run populate_async for a single target. Never raises — returns a result dict."""
    try:
        filled_pdf, cost, model_breakdown = await populator.populate_async(
            source_data, target_bytes, force_claude=force_claude,
        )
        # model_breakdown is a list — pick the first model name if available
        model = "unknown"
        if isinstance(model_breakdown, list) and model_breakdown:
            first = model_breakdown[0]
            if isinstance(first, dict):
                model = str(first.get("model") or first.get("name") or "unknown")
            else:
                model = str(first)
        return {
            "target_filename": target_name,
            "success": True,
            "filled_pdf_base64": base64.b64encode(filled_pdf).decode("ascii"),
            "filled_filename": f"filled_{target_name}",
            "cost_usd": float(cost),
            "model": model,
            "size_bytes": len(filled_pdf),
        }
    except ValueError as e:
        logger.warning("Form fill validation error for %s: %s", target_name, e)
        return {"target_filename": target_name, "success": False, "error": str(e)}
    except Exception as e:
        logger.error("Form fill failed for %s: %s", target_name, e, exc_info=True)
        return {
            "target_filename": target_name,
            "success": False,
            "error": "Form filling failed — please try again",
        }


@router.post("/fill")
async def fill_form(
    target_forms: Optional[List[UploadFile]] = File(None),
    target_form: Optional[UploadFile] = File(None),
    source_files: List[UploadFile] = File(...),
    force_claude: Optional[str] = Form(None),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Upload 1-10 target PDF forms and source files.

    Returns JSON `{"results": [...]}` with one entry per target. Each entry
    is `{target_filename, success, filled_pdf_base64?, cost_usd?, model?, error?}`.
    Pages are billed up-front for the total request and refunded for any
    targets that fail.
    """
    from app.routes.payments import _maybe_reset_usage

    targets = await _read_target_forms(target_forms, target_form)
    source_data = await _read_source_files(source_files)

    n_targets = len(targets)
    total_pages = FORM_FILL_PAGE_COST * n_targets

    result = await db.execute(select(User).where(User.id == current_user.id))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    tier = get_tier(user.subscription_tier)
    _maybe_reset_usage(user)
    await db.commit()
    await db.refresh(user)

    used = user.pages_used_this_period or 0
    if tier.name == "free" and used + total_pages > tier.pages_per_month:
        raise HTTPException(
            status_code=402,
            detail={
                "type": "page_limit_reached",
                "message": (
                    f"Free plan allows {tier.pages_per_month:,} pages/month. "
                    f"You've used {used:,}; this request needs {total_pages:,}."
                ),
                "pages_used": used,
                "pages_limit": tier.pages_per_month,
                "pages_required": total_pages,
                "tier": tier.name,
            },
        )

    user.pages_used_this_period = used + total_pages
    over_quota_before = used > tier.pages_per_month
    over_quota_after = user.pages_used_this_period > tier.pages_per_month
    overage_added = max(0, user.pages_used_this_period - max(used, tier.pages_per_month)) if over_quota_after else 0
    if overage_added > 0:
        user.overage_pages_this_period = (user.overage_pages_this_period or 0) + overage_added
    await db.commit()
    try:
        from app.cache import cache_del_user
        await cache_del_user(str(user.id))
    except Exception:
        pass

    logger.info(
        "Form fill request — user_id=%s targets=%d sources=%d pages=%d",
        current_user.id, n_targets, len(source_data), total_pages,
    )

    async def _refund_pages(failed_count: int, reason: str) -> None:
        """Refund pages for `failed_count` targets that didn't complete."""
        if failed_count <= 0:
            return
        refund = FORM_FILL_PAGE_COST * failed_count
        try:
            r = await db.execute(select(User).where(User.id == current_user.id))
            u = r.scalar_one_or_none()
            if not u:
                return
            u.pages_used_this_period = max(0, (u.pages_used_this_period or 0) - refund)
            # Refund overage proportionally — cap at what was added.
            if overage_added > 0:
                refund_overage = min(overage_added, refund)
                u.overage_pages_this_period = max(0, (u.overage_pages_this_period or 0) - refund_overage)
            await db.commit()
            try:
                from app.cache import cache_del_user
                await cache_del_user(str(u.id))
            except Exception:
                pass
            logger.info(
                "Form fill refund — user_id=%s pages=%d targets=%d reason=%s",
                current_user.id, refund, failed_count, reason,
            )
        except Exception:
            logger.exception("Form fill refund failed (user=%s)", current_user.id)
        # silence unused-var warnings
        _ = over_quota_before

    use_claude = bool(force_claude and force_claude.lower() in ("1", "true", "yes"))
    populator = PDFPopulator()

    # Run all targets concurrently (cap is the input limit of 10).
    results = await asyncio.gather(*[
        _populate_one(populator, source_data, name, data, use_claude)
        for (name, data) in targets
    ])

    # Refund pages for any failed targets.
    failed = [r for r in results if not r.get("success")]
    if failed:
        await _refund_pages(len(failed), reason=f"failed_targets={len(failed)}")

    # Deduct actual cost (sum of successes) from the user's balance.
    total_cost = sum(float(r.get("cost_usd") or 0.0) for r in results if r.get("success"))
    result = await db.execute(select(User).where(User.id == current_user.id))
    user = result.scalar_one_or_none()
    if user:
        balance_before = user.balance or 0.0
        user.balance = max(0.0, balance_before - total_cost)
        await db.commit()
        logger.info(
            "Form fill complete — user_id=%s targets=%d succeeded=%d cost=$%.6f balance=%.6f→%.6f",
            current_user.id, n_targets, n_targets - len(failed), total_cost,
            balance_before, user.balance,
        )

    return {
        "results": results,
        "summary": {
            "total": n_targets,
            "succeeded": n_targets - len(failed),
            "failed": len(failed),
            "total_cost_usd": total_cost,
        },
    }


@router.post("/fill-service", include_in_schema=False)
async def fill_form_service(
    request: Request,
    target_forms: Optional[List[UploadFile]] = File(None),
    target_form: Optional[UploadFile] = File(None),
    source_files: List[UploadFile] = File(...),
    service_token: Optional[str] = Form(None),
    force_claude: Optional[str] = Form(None),
    db: AsyncSession = Depends(get_db),
):
    """Same as /fill but auth via X-GridPull-Service-Token header or service_token form field.

    Uses the configured SERVICE_EXTRACTION_USER_ID account for billing.

    For backward compatibility, when a single `target_form` is uploaded and the
    request looks like a legacy caller (no `target_forms`), the response is the
    raw filled PDF bytes (Content-Type: application/pdf). When `target_forms` is
    present, the response is JSON in the same shape as `/fill`.
    """
    _assert_valid_service_token(request, form_token=service_token)
    svc_user = await _load_service_account_user(db)

    targets = await _read_target_forms(target_forms, target_form)
    source_data = await _read_source_files(source_files)

    legacy_single = (target_forms is None or len(target_forms or []) == 0) and target_form is not None and len(targets) == 1

    logger.info(
        "Form fill service request — user_id=%s targets=%d sources=%d legacy=%s",
        svc_user.id, len(targets), len(source_data), legacy_single,
    )

    use_claude = bool(force_claude and force_claude.lower() in ("1", "true", "yes"))
    populator = PDFPopulator()

    if legacy_single:
        # Preserve the original PDF-bytes response for legacy service callers.
        name, data = targets[0]
        try:
            filled_pdf, cost, _model_breakdown = await populator.populate_async(
                source_data, data, force_claude=use_claude,
            )
        except ValueError as e:
            raise HTTPException(status_code=422, detail=str(e))
        except Exception as e:
            logger.error("Form filling (service) failed: %s", e, exc_info=True)
            raise HTTPException(status_code=500, detail="Form filling failed — please try again")

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

        output_name = f"filled_{name}"
        return Response(
            content=filled_pdf,
            media_type="application/pdf",
            headers={"Content-Disposition": f'attachment; filename="{output_name}"'},
        )

    # Multi-target path — JSON response.
    results = await asyncio.gather(*[
        _populate_one(populator, source_data, name, data, use_claude)
        for (name, data) in targets
    ])
    total_cost = sum(float(r.get("cost_usd") or 0.0) for r in results if r.get("success"))
    failed = [r for r in results if not r.get("success")]

    result = await db.execute(select(User).where(User.id == svc_user.id))
    user = result.scalar_one_or_none()
    if user:
        balance_before = user.balance or 0.0
        user.balance = max(0.0, balance_before - total_cost)
        await db.commit()
        logger.info(
            "Form fill service complete — user_id=%s targets=%d succeeded=%d cost=$%.6f balance=%.6f→%.6f",
            svc_user.id, len(targets), len(targets) - len(failed), total_cost,
            balance_before, user.balance,
        )

    return {
        "results": results,
        "summary": {
            "total": len(targets),
            "succeeded": len(targets) - len(failed),
            "failed": len(failed),
            "total_cost_usd": total_cost,
        },
    }
