from jose import JWTError, jwt
import time
from typing import Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, or_
from app.config import settings
from app.models.user import User
import requests as http_requests


def create_access_token(user_id: str) -> str:
    """Create JWT token with NO expiration."""
    payload = {
        "sub": user_id,
        "iat": int(time.time()),
    }
    return jwt.encode(payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)


def verify_token(token: str) -> Optional[str]:
    """Verify JWT and return user_id. No expiration check."""
    try:
        payload = jwt.decode(
            token,
            settings.jwt_secret_key,
            algorithms=[settings.jwt_algorithm],
            options={"verify_exp": False},
        )
        return payload.get("sub")
    except JWTError:
        return None


async def get_or_create_user(db: AsyncSession, google_user_info: dict) -> User:
    """Get existing user or create new one from Google user info.

    Uses a single query with OR to avoid two round-trips to the database.
    """
    google_id = google_user_info.get("id") or google_user_info.get("sub")
    email = google_user_info.get("email", "")

    # Single query: match by google_id OR email (both are indexed)
    result = await db.execute(
        select(User)
        .where(or_(User.google_id == google_id, User.email == email))
        .limit(1)
    )
    user = result.scalar_one_or_none()

    if user:
        # Update any stale info
        user.name = google_user_info.get("name", user.name)
        user.picture = google_user_info.get("picture", user.picture)
        if not user.google_id and google_id:
            user.google_id = google_id
        await db.commit()
        await db.refresh(user)
        return user

    # Create new user
    user = User(
        email=email,
        name=google_user_info.get("name", email.split("@")[0]),
        picture=google_user_info.get("picture"),
        google_id=google_id,
        credits=10,  # Free starting credits
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return user


async def verify_google_access_token(access_token: str) -> dict:
    """Verify Google access token and get user info."""
    resp = http_requests.get(
        "https://www.googleapis.com/oauth2/v2/userinfo",
        headers={"Authorization": f"Bearer {access_token}"},
        timeout=10,
    )
    resp.raise_for_status()
    return resp.json()
