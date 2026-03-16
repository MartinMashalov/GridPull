import logging
import time
from typing import Optional

import httpx
from jose import JWTError, jwt
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, or_

from app.config import settings
from app.models.user import User

logger = logging.getLogger(__name__)


def create_access_token(user_id: str) -> str:
    """Create JWT token with NO expiration."""
    payload = {
        "sub": user_id,
        "iat": int(time.time()),
    }
    token = jwt.encode(payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)
    logger.debug("JWT created for user_id=%s", user_id)
    return token


def verify_token(token: str) -> Optional[str]:
    """Verify JWT and return user_id. No expiration check."""
    try:
        payload = jwt.decode(
            token,
            settings.jwt_secret_key,
            algorithms=[settings.jwt_algorithm],
            options={"verify_exp": False},
        )
        user_id = payload.get("sub")
        logger.debug("JWT verified — user_id=%s", user_id)
        return user_id
    except JWTError as exc:
        logger.warning("JWT verification failed: %s", exc)
        return None


async def get_or_create_user(db: AsyncSession, user_info: dict, provider: str = "google") -> User:
    """Get existing user or create new one from OAuth user info."""
    email = user_info.get("email", "")

    if provider == "microsoft":
        provider_id = user_info.get("id")
        id_column = User.microsoft_id
    else:
        provider_id = user_info.get("id") or user_info.get("sub")
        id_column = User.google_id

    result = await db.execute(
        select(User)
        .where(or_(id_column == provider_id, User.email == email))
        .limit(1)
    )
    user = result.scalar_one_or_none()

    if user:
        user.name = user_info.get("name") or user_info.get("displayName") or user.name
        user.picture = user_info.get("picture") or user.picture
        if provider == "microsoft" and not user.microsoft_id and provider_id:
            user.microsoft_id = provider_id
        elif provider == "google" and not user.google_id and provider_id:
            user.google_id = provider_id
        await db.commit()
        await db.refresh(user)
        logger.info("Existing user logged in — user_id=%s email=%s provider=%s", user.id, user.email, provider)
        return user

    kwargs = {
        "email": email,
        "name": user_info.get("name") or user_info.get("displayName") or email.split("@")[0],
        "picture": user_info.get("picture"),
        "balance": 1.0,
    }
    if provider == "microsoft":
        kwargs["microsoft_id"] = provider_id
    else:
        kwargs["google_id"] = provider_id

    user = User(**kwargs)
    db.add(user)
    await db.commit()
    await db.refresh(user)
    logger.info("New user created — user_id=%s email=%s provider=%s starting_balance=$1.00", user.id, user.email, provider)
    return user


async def verify_google_access_token(access_token: str) -> dict:
    """Verify Google access token and get user info."""
    logger.debug("Calling Google userinfo endpoint…")
    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.get(
            "https://www.googleapis.com/oauth2/v2/userinfo",
            headers={"Authorization": f"Bearer {access_token}"},
        )
        resp.raise_for_status()
        data = resp.json()
        logger.debug("Google userinfo OK — email=%s google_id=%s", data.get("email"), data.get("id"))
        return data


async def verify_microsoft_access_token(access_token: str) -> dict:
    """Verify Microsoft access token by calling Microsoft Graph /me endpoint."""
    logger.debug("Calling Microsoft Graph /me endpoint…")
    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.get(
            "https://graph.microsoft.com/v1.0/me",
            headers={"Authorization": f"Bearer {access_token}"},
        )
        resp.raise_for_status()
        data = resp.json()
        if not data.get("mail") and data.get("userPrincipalName"):
            data["email"] = data["userPrincipalName"]
        else:
            data["email"] = data.get("mail", "")
        data["name"] = data.get("displayName", "")
        logger.debug("Microsoft Graph OK — email=%s microsoft_id=%s", data.get("email"), data.get("id"))
        return data
