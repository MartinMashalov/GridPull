from fastapi import APIRouter, Depends
from pydantic import BaseModel
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
        "auto_renewal_enabled": current_user.auto_renewal_enabled,
        "auto_renewal_threshold": current_user.auto_renewal_threshold,
        "auto_renewal_refill": current_user.auto_renewal_refill,
    }


class AutoRenewalRequest(BaseModel):
    enabled: bool
    threshold: float
    refill_amount: float


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
