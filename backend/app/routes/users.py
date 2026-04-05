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
    return {
        "id": current_user.id,
        "email": current_user.email,
        "name": current_user.name,
        "picture": current_user.picture,
        "balance": current_user.balance,
        "subscription_tier": current_user.subscription_tier or "free",
        "subscription_status": current_user.subscription_status or "active",
        "credits_used_this_period": current_user.credits_used_this_period or 0,
        "current_period_end": current_user.current_period_end.isoformat() if current_user.current_period_end else None,
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
