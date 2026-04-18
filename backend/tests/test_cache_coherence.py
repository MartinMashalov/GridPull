"""
Regression tests for the in-process user cache used as a fallback when
Redis is unavailable. These tests prevent a re-occurrence of the staleness
bug where:

  1. A request populated both Redis and a per-worker in-process dict.
  2. Some state-change (e.g. dev-set-usage) called cache_del_user which
     cleared Redis but NOT the in-process dict.
  3. The next request on that worker hit the stale in-process entry and
     served stale tier / pages_used data for up to 60s.

The fix has two parts, both asserted below:

  A. _local_set is a no-op when Redis is reachable (so the in-process dict
     is never populated alongside Redis — nothing to go stale).
  B. cache_del_user clears the in-process dict on the current worker, so
     even on the Redis-down code path an invalidation is honored.
"""

import asyncio
import time
import types
import unittest
from unittest.mock import AsyncMock, patch


def _fake_user(uid: str = "u-cache"):
    return types.SimpleNamespace(
        id=uid,
        email="a@b.com",
        name="A",
        balance=0.0,
        is_active=True,
        pages_used_this_period=0,
        overage_pages_this_period=0,
    )


class TestLocalSetSkipsWhenRedisUp(unittest.IsolatedAsyncioTestCase):
    """_local_set must NOT populate the in-process dict when Redis is
    reachable — otherwise cache_del_user (which only clears Redis) leaves
    a stale in-process entry behind that survives for up to _CACHE_TTL."""

    async def test_skips_when_redis_reachable(self):
        from app.middleware import auth_middleware as am

        # Pretend Redis is reachable by returning a truthy object from get_redis.
        fake_redis = object()

        # Ensure the dict starts empty
        am._USER_CACHE.clear()

        with patch("app.middleware.auth_middleware.get_redis", AsyncMock(return_value=fake_redis)):
            user = _fake_user("u-redis-up")
            await am._local_set(user)

        self.assertNotIn(
            "u-redis-up",
            am._USER_CACHE,
            "_local_set populated the in-process dict while Redis was up — this "
            "creates an invalidation-coherence bug because cache_del_user only "
            "clears Redis.",
        )

    async def test_populates_when_redis_down(self):
        from app.middleware import auth_middleware as am

        am._USER_CACHE.clear()
        with patch("app.middleware.auth_middleware.get_redis", AsyncMock(return_value=None)):
            user = _fake_user("u-redis-down")
            await am._local_set(user)

        self.assertIn(
            "u-redis-down",
            am._USER_CACHE,
            "_local_set must still populate the in-process dict as a fallback "
            "when Redis is unavailable — otherwise every request would hit the DB.",
        )

        # And _local_get should return it within the TTL
        got = am._local_get("u-redis-down")
        self.assertIsNotNone(got)
        self.assertEqual(got.id, "u-redis-down")

        # Cleanup
        am._USER_CACHE.clear()


class TestCacheDelUserClearsLocal(unittest.IsolatedAsyncioTestCase):
    """cache_del_user must clear the in-process dict on the current worker,
    so an invalidation is honored even on the Redis-down fallback path."""

    async def test_cache_del_user_pops_local_entry(self):
        from app.middleware import auth_middleware as am
        from app.cache import cache_del_user

        # Seed the in-process dict directly
        am._USER_CACHE.clear()
        am._USER_CACHE["u-pop"] = (_fake_user("u-pop"), time.monotonic() + 60.0)
        self.assertIn("u-pop", am._USER_CACHE)

        with patch("app.cache.get_redis", AsyncMock(return_value=None)):
            # Redis is down → cache_del_user's Redis branch is a no-op.
            # The in-process clear must still happen.
            await cache_del_user("u-pop")

        self.assertNotIn(
            "u-pop",
            am._USER_CACHE,
            "cache_del_user left the in-process entry in place — this is the "
            "exact bug that caused cross-test state pollution in Playwright.",
        )

    async def test_cache_del_user_clears_local_even_when_redis_up(self):
        """Belt-and-braces: on the Redis-up path, the in-process dict should
        already be empty thanks to _local_set's guard, but cache_del_user
        should still defensively clear it."""
        from app.middleware import auth_middleware as am
        from app.cache import cache_del_user

        am._USER_CACHE.clear()
        # Manually insert an entry (simulating a pre-fix stale entry)
        am._USER_CACHE["u-legacy"] = (_fake_user("u-legacy"), time.monotonic() + 60.0)

        fake_redis = AsyncMock()
        fake_redis.delete = AsyncMock(return_value=1)
        with patch("app.cache.get_redis", AsyncMock(return_value=fake_redis)):
            await cache_del_user("u-legacy")

        self.assertNotIn("u-legacy", am._USER_CACHE)
        fake_redis.delete.assert_awaited_once_with("gp:user:u-legacy")


if __name__ == "__main__":
    unittest.main(verbosity=2)
