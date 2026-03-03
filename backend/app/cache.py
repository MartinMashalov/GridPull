"""
Redis cache layer for GridPull.

Provides a shared cache across all uvicorn workers. Falls back gracefully
to None if Redis is unavailable (callers then use in-process dicts instead).

Keys:
  gp:user:{user_id}              TTL 60s   — serialised CachedUser
  gp:results:{job_id}            no TTL    — immutable job results (JSON)
  gp:job_status:{job_id}:{uid}   no TTL    — immutable terminal job status (JSON)
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from typing import Optional

import redis.asyncio as aioredis

from app.config import settings

logger = logging.getLogger(__name__)

_redis_pool: Optional[aioredis.Redis] = None
_redis_ok: bool = True   # flipped to False on first connection failure

_USER_TTL = 60  # seconds


async def get_redis() -> Optional[aioredis.Redis]:
    """Return the shared Redis client, or None if Redis is unavailable."""
    global _redis_pool, _redis_ok
    if not _redis_ok:
        return None
    if _redis_pool is None:
        try:
            _redis_pool = aioredis.from_url(
                settings.redis_url,
                encoding="utf-8",
                decode_responses=True,
                socket_connect_timeout=1,
                socket_timeout=1,
            )
            await _redis_pool.ping()
        except Exception as exc:
            logger.warning(
                "Redis unavailable (%s) — falling back to in-process cache", exc
            )
            _redis_pool = None
            _redis_ok = False
            return None
    return _redis_pool


# ── CachedUser ────────────────────────────────────────────────────────────────

@dataclass
class CachedUser:
    """Lightweight serialisable representation of a User stored in Redis."""

    id: str
    email: str
    name: str
    picture: Optional[str]
    balance: float
    is_active: bool

    def to_json(self) -> str:
        return json.dumps(
            {
                "id": self.id,
                "email": self.email,
                "name": self.name,
                "picture": self.picture,
                "balance": self.balance,
                "is_active": self.is_active,
            }
        )

    @classmethod
    def from_json(cls, data: str) -> "CachedUser":
        return cls(**json.loads(data))

    @classmethod
    def from_user(cls, user) -> "CachedUser":
        return cls(
            id=user.id,
            email=user.email,
            name=user.name,
            picture=getattr(user, "picture", None),
            balance=user.balance,
            is_active=user.is_active,
        )


# ── User helpers ──────────────────────────────────────────────────────────────

async def cache_get_user(user_id: str) -> Optional[CachedUser]:
    r = await get_redis()
    if r is None:
        return None
    try:
        raw = await r.get(f"gp:user:{user_id}")
        return CachedUser.from_json(raw) if raw else None
    except Exception:
        return None


async def cache_set_user(user) -> None:
    r = await get_redis()
    if r is None:
        return
    try:
        cu = CachedUser.from_user(user)
        await r.setex(f"gp:user:{user.id}", _USER_TTL, cu.to_json())
    except Exception:
        pass


async def cache_del_user(user_id: str) -> None:
    r = await get_redis()
    if r is None:
        return
    try:
        await r.delete(f"gp:user:{user_id}")
    except Exception:
        pass


# ── Job-status helpers ────────────────────────────────────────────────────────

async def cache_get_job_status(job_id: str, user_id: str) -> Optional[dict]:
    r = await get_redis()
    if r is None:
        return None
    try:
        raw = await r.get(f"gp:job_status:{job_id}:{user_id}")
        return json.loads(raw) if raw else None
    except Exception:
        return None


async def cache_set_job_status(job_id: str, user_id: str, payload: dict) -> None:
    r = await get_redis()
    if r is None:
        return
    try:
        await r.set(f"gp:job_status:{job_id}:{user_id}", json.dumps(payload))
    except Exception:
        pass


# ── Results helpers ───────────────────────────────────────────────────────────

async def cache_get_results(job_id: str, owner_id: str) -> Optional[dict]:
    r = await get_redis()
    if r is None:
        return None
    try:
        raw = await r.get(f"gp:results:{job_id}")
        if not raw:
            return None
        data = json.loads(raw)
        # Verify ownership before returning
        if data.get("_owner") != owner_id:
            return None
        return {k: v for k, v in data.items() if k != "_owner"}
    except Exception:
        return None


async def cache_set_results(job_id: str, owner_id: str, payload: dict) -> None:
    r = await get_redis()
    if r is None:
        return
    try:
        await r.set(f"gp:results:{job_id}", json.dumps({**payload, "_owner": owner_id}))
    except Exception:
        pass
