import logging

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel
from app.database import get_db
from app.services.auth_service import (
    create_access_token,
    get_or_create_user,
    verify_google_access_token,
    verify_microsoft_access_token,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/auth", tags=["auth"])


class GoogleAuthRequest(BaseModel):
    access_token: str


class MicrosoftAuthRequest(BaseModel):
    access_token: str


class AuthResponse(BaseModel):
    access_token: str
    user: dict


@router.post("/google", response_model=AuthResponse)
async def google_auth(request: Request, body: GoogleAuthRequest, db: AsyncSession = Depends(get_db)):
    """Authenticate with Google OAuth access token."""
    client_ip = request.client.host if request.client else "-"
    token_preview = body.access_token[:12] + "…" if len(body.access_token) > 12 else body.access_token

    logger.info("Google login attempt from %s (token: %s)", client_ip, token_preview)

    try:
        google_user = await verify_google_access_token(body.access_token)
    except Exception as e:
        logger.warning("Google token verification failed from %s: %s", client_ip, str(e))
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Invalid Google token: {str(e)}",
        )

    email = google_user.get("email", "<no-email>")
    name = google_user.get("name", "<no-name>")
    logger.info("Google token verified — email=%s name=%s ip=%s", email, name, client_ip)

    user = await get_or_create_user(db, google_user, provider="google")
    token = create_access_token(user.id)

    logger.info("Login successful — user_id=%s email=%s balance=$%.6f ip=%s", user.id, user.email, user.balance, client_ip)

    return {
        "access_token": token,
        "user": {
            "id": user.id,
            "email": user.email,
            "name": user.name,
            "picture": user.picture,
            "balance": user.balance,
        },
    }


@router.post("/microsoft", response_model=AuthResponse)
async def microsoft_auth(request: Request, body: MicrosoftAuthRequest, db: AsyncSession = Depends(get_db)):
    """Authenticate with Microsoft OAuth access token."""
    client_ip = request.client.host if request.client else "-"
    token_preview = body.access_token[:12] + "…" if len(body.access_token) > 12 else body.access_token

    logger.info("Microsoft login attempt from %s (token: %s)", client_ip, token_preview)

    try:
        ms_user = await verify_microsoft_access_token(body.access_token)
    except Exception as e:
        logger.warning("Microsoft token verification failed from %s: %s", client_ip, str(e))
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Invalid Microsoft token: {str(e)}",
        )

    email = ms_user.get("email", "<no-email>")
    name = ms_user.get("name", "<no-name>")
    logger.info("Microsoft token verified — email=%s name=%s ip=%s", email, name, client_ip)

    user = await get_or_create_user(db, ms_user, provider="microsoft")
    token = create_access_token(user.id)

    logger.info("Login successful — user_id=%s email=%s balance=$%.6f ip=%s", user.id, user.email, user.balance, client_ip)

    return {
        "access_token": token,
        "user": {
            "id": user.id,
            "email": user.email,
            "name": user.name,
            "picture": user.picture,
            "balance": user.balance,
        },
    }
