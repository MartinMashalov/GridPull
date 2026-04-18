"""
Auth middleware.

Two dependency flavours:
  - get_current_user      → standard Bearer header (JSON endpoints)
  - get_current_user_sse  → also accepts ?token= query param (EventSource / SSE)

Optimisation: verified user objects are cached in Redis (shared across all
workers) with a 60-second TTL. Falls back to an in-process dict when Redis
is unavailable.
"""

import logging
import time
from typing import Optional, Tuple

from fastapi import Depends, HTTPException, Query, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.cache import cache_get_user, cache_set_user, get_redis
from app.database import get_db
from app.models.user import User
from app.services.auth_service import verify_token

logger = logging.getLogger(__name__)
security = HTTPBearer()

# ── In-process user cache — fallback when Redis is unavailable ────────────────
# (user_id → (User, expiry_ts))
#
# IMPORTANT: Each uvicorn worker has its OWN copy of this dict. cache_del_user
# in app.cache only clears Redis, so if we populate this dict unconditionally
# we create a coherence bug: worker A's in-process entry can survive a
# "successful" cache invalidation and serve stale data for up to _CACHE_TTL.
# To avoid that, we ONLY populate this dict when Redis is unreachable.
_USER_CACHE: dict[str, Tuple[User, float]] = {}
_CACHE_TTL = 60.0  # seconds


def _local_get(user_id: str) -> Optional[User]:
    entry = _USER_CACHE.get(user_id)
    if entry and time.monotonic() < entry[1]:
        return entry[0]
    _USER_CACHE.pop(user_id, None)
    return None


async def _local_set(user: User) -> None:
    # Only populate when Redis is the fallback path. If Redis is up, the
    # shared Redis cache is authoritative and invalidations reach every
    # worker; populating here would shadow those invalidations on this worker
    # until the 60s TTL expires.
    r = await get_redis()
    if r is not None:
        return
    if len(_USER_CACHE) > 5000:
        cutoff = sorted(_USER_CACHE.values(), key=lambda e: e[1])[len(_USER_CACHE) // 5]
        for uid in [k for k, v in _USER_CACHE.items() if v[1] <= cutoff[1]]:
            _USER_CACHE.pop(uid, None)
    _USER_CACHE[user.id] = (user, time.monotonic() + _CACHE_TTL)


def _cache_invalidate(user_id: str) -> None:
    """Remove the in-process entry (Redis is cleared separately via cache_del_user)."""
    _USER_CACHE.pop(user_id, None)


async def _resolve_user(token: str, db: AsyncSession) -> User:
    user_id = verify_token(token)
    if not user_id:
        logger.warning("Token rejected — invalid JWT")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # ── Fast path 1: Redis cache (shared across workers) ─────────────────────
    cached = await cache_get_user(user_id)
    if cached is not None:
        logger.debug("Auth cache hit (Redis) — user_id=%s", user_id)
        return cached  # type: ignore[return-value]

    # ── Fast path 2: in-process dict (fallback when Redis is down) ───────────
    local = _local_get(user_id)
    if local is not None:
        logger.debug("Auth cache hit (local) — user_id=%s", user_id)
        return local

    # ── Slow path: DB lookup ─────────────────────────────────────────────────
    logger.debug("Auth cache miss — DB lookup for user_id=%s", user_id)
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user or not user.is_active:
        logger.warning(
            "Auth rejected — user_id=%s not found or inactive",
            user_id,
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found or inactive",
        )

    logger.debug(
        "Auth DB lookup OK — user_id=%s email=%s balance=$%.6f",
        user.id, user.email, user.balance,
    )
    await cache_set_user(user)
    await _local_set(user)
    return user


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db: AsyncSession = Depends(get_db),
) -> User:
    """Standard Bearer-header auth for JSON endpoints."""
    return await _resolve_user(credentials.credentials, db)


async def get_current_user_sse(
    request: Request,
    token: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
) -> User:
    """
    Auth for SSE endpoints.
    Accepts both:
      - Authorization: Bearer <token>  (normal fetch)
      - ?token=<token>                 (EventSource — cannot set headers)
    """
    raw = request.headers.get("Authorization", "")
    if raw.startswith("Bearer "):
        jwt_token = raw[7:]
        logger.debug("SSE auth via Bearer header")
    elif token:
        jwt_token = token
        logger.debug("SSE auth via query param")
    else:
        logger.warning("SSE request with no auth from %s", request.client.host if request.client else "-")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required",
        )
    return await _resolve_user(jwt_token, db)
