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
    stripe_customer_id: Optional[str] = None
    stripe_payment_method_id: Optional[str] = None
    stripe_card_brand: Optional[str] = None
    stripe_card_last4: Optional[str] = None
    subscription_tier: str = "free"
    stripe_subscription_id: Optional[str] = None
    subscription_status: str = "active"
    files_used_this_period: int = 0
    overage_files_this_period: int = 0
    first_month_discount_used: bool = False

    def to_json(self) -> str:
        return json.dumps(
            {
                "id": self.id,
                "email": self.email,
                "name": self.name,
                "picture": self.picture,
                "balance": self.balance,
                "is_active": self.is_active,
                "stripe_customer_id": self.stripe_customer_id,
                "stripe_payment_method_id": self.stripe_payment_method_id,
                "stripe_card_brand": self.stripe_card_brand,
                "stripe_card_last4": self.stripe_card_last4,
                "subscription_tier": self.subscription_tier,
                "stripe_subscription_id": self.stripe_subscription_id,
                "subscription_status": self.subscription_status,
                "files_used_this_period": self.files_used_this_period,
                "overage_files_this_period": self.overage_files_this_period,
                "first_month_discount_used": self.first_month_discount_used,
            }
        )

    @classmethod
    def from_json(cls, data: str) -> "CachedUser":
        d = json.loads(data)
        d.setdefault("stripe_customer_id", None)
        d.setdefault("stripe_payment_method_id", None)
        d.setdefault("stripe_card_brand", None)
        d.setdefault("stripe_card_last4", None)
        d.setdefault("subscription_tier", "free")
        d.setdefault("stripe_subscription_id", None)
        d.setdefault("subscription_status", "active")
        d.setdefault("files_used_this_period", 0)
        d.setdefault("overage_files_this_period", 0)
        d.setdefault("first_month_discount_used", False)
        return cls(**d)

    @classmethod
    def from_user(cls, user) -> "CachedUser":
        return cls(
            id=user.id,
            email=user.email,
            name=user.name,
            picture=getattr(user, "picture", None),
            balance=user.balance,
            is_active=user.is_active,
            stripe_customer_id=getattr(user, "stripe_customer_id", None),
            stripe_payment_method_id=getattr(user, "stripe_payment_method_id", None),
            stripe_card_brand=getattr(user, "stripe_card_brand", None),
            stripe_card_last4=getattr(user, "stripe_card_last4", None),
            subscription_tier=getattr(user, "subscription_tier", "free") or "free",
            stripe_subscription_id=getattr(user, "stripe_subscription_id", None),
            subscription_status=getattr(user, "subscription_status", "active") or "active",
            files_used_this_period=getattr(user, "files_used_this_period", 0) or 0,
            overage_files_this_period=getattr(user, "overage_files_this_period", 0) or 0,
            first_month_discount_used=bool(getattr(user, "first_month_discount_used", False)),
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
