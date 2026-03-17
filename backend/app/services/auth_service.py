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


async def get_or_create_user(db: AsyncSession, google_user_info: dict) -> User:
    """Get existing user or create new one from Google user info."""
    google_id = google_user_info.get("id") or google_user_info.get("sub")
    email = google_user_info.get("email", "")

    result = await db.execute(
        select(User)
        .where(or_(User.google_id == google_id, User.email == email))
        .limit(1)
    )
    user = result.scalar_one_or_none()

    if user:
        # Update stale profile info
        user.name = google_user_info.get("name", user.name)
        user.picture = google_user_info.get("picture", user.picture)
        if not user.google_id and google_id:
            user.google_id = google_id
        await db.commit()
        await db.refresh(user)
        logger.info("Existing user logged in — user_id=%s email=%s", user.id, user.email)
        return user

    # New user
    user = User(
        email=email,
        name=google_user_info.get("name", email.split("@")[0]),
        picture=google_user_info.get("picture"),
        google_id=google_id,
        balance=1.0,  # $1.00 free starting balance
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    logger.info(
        "New user created — user_id=%s email=%s starting_balance=$1.00",
        user.id, user.email,
    )
    return user


async def verify_google_access_token(access_token: str) -> dict:
    """Verify Google access token and get user info (non-blocking async)."""
    logger.debug("Calling Google userinfo endpoint…")
    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.get(
            "https://www.googleapis.com/oauth2/v2/userinfo",
            headers={"Authorization": f"Bearer {access_token}"},
        )
        resp.raise_for_status()
        data = resp.json()
        logger.debug(
            "Google userinfo OK — email=%s google_id=%s",
            data.get("email"), data.get("id"),
        )
        return data
