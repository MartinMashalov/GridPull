from typing import List, Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.user import User
from app.middleware.auth_middleware import get_current_user

router = APIRouter(prefix="/users", tags=["users"])


@router.get("/me")
async def get_me(current_user: User = Depends(get_current_user)):
    """Get current authenticated user."""
    cpe = getattr(current_user, "current_period_end", None)
    return {
        "id": current_user.id,
        "email": current_user.email,
        "name": current_user.name,
        "picture": current_user.picture,
        "balance": current_user.balance,
        "subscription_tier": current_user.subscription_tier or "free",
        "subscription_status": current_user.subscription_status or "active",
        "pages_used_this_period": current_user.pages_used_this_period or 0,
        "current_period_end": cpe.isoformat() if hasattr(cpe, "isoformat") else cpe,
    }


class AutoRenewalRequest(BaseModel):
    enabled: bool
    threshold: float
    refill_amount: float


class DefaultFieldItem(BaseModel):
    name: str
    description: str = ""


class DefaultFieldsRequest(BaseModel):
    fields: List[DefaultFieldItem]


@router.get("/default-fields")
async def get_default_fields(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get the user's saved default extraction fields."""
    result = await db.execute(select(User).where(User.id == current_user.id))
    user = result.scalar_one_or_none()
    return {"fields": user.default_fields or [] if user else []}


@router.post("/default-fields")
async def save_default_fields(
    body: DefaultFieldsRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Save the user's default extraction fields."""
    result = await db.execute(select(User).where(User.id == current_user.id))
    user = result.scalar_one_or_none()
    if not user:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="User not found")
    user.default_fields = [f.model_dump() for f in body.fields]
    await db.commit()
    return {"ok": True, "fields": user.default_fields}


class FieldPresetItem(BaseModel):
    name: str
    fields: List[DefaultFieldItem]


class FieldPresetsRequest(BaseModel):
    presets: List[FieldPresetItem]


@router.get("/field-presets")
async def get_field_presets(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get the user's saved extraction field presets."""
    result = await db.execute(select(User).where(User.id == current_user.id))
    user = result.scalar_one_or_none()
    presets = user.field_presets or [] if user else []
    # Migrate old default_fields to presets if no presets exist yet
    if not presets and user and user.default_fields:
        presets = [{"name": "My Defaults", "fields": user.default_fields}]
    return {"presets": presets}


@router.post("/field-presets")
async def save_field_presets(
    body: FieldPresetsRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Save the user's extraction field presets."""
    result = await db.execute(select(User).where(User.id == current_user.id))
    user = result.scalar_one_or_none()
    if not user:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="User not found")
    user.field_presets = [p.model_dump() for p in body.presets]
    await db.commit()
    return {"ok": True, "presets": user.field_presets}


@router.post("/auto-renewal")
async def set_auto_renewal(
    body: AutoRenewalRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Save auto-renewal settings for the current user."""
    current_user.auto_renewal_enabled = body.enabled
    current_user.auto_renewal_threshold = body.threshold
    current_user.auto_renewal_refill = body.refill_amount
    db.add(current_user)
    await db.commit()
    return {"ok": True}
