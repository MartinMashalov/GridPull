"""
Stripe webhook handler tests.

The handlers in app/routes/payments.py are the authoritative source for
tier transitions triggered by Stripe events. A bug here means a user who
downgrades on Stripe still reads as pro in the DB, or a failed payment
doesn't mark the account past_due, or an invoice.paid event fails to reset
pages_used at period rollover.

These tests use the helpers directly (not the HTTP route) so we can bypass
signature verification and focus on the state-transition logic.
"""

import asyncio
import types
import unittest
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch


def _fake_user(
    user_id: str = "u1",
    tier: str = "free",
    sub_id: str = None,
    customer_id: str = None,
    pages: int = 0,
    overage: int = 0,
):
    u = types.SimpleNamespace(
        id=user_id,
        subscription_tier=tier,
        subscription_status="active",
        stripe_subscription_id=sub_id,
        stripe_customer_id=customer_id,
        pages_used_this_period=pages,
        overage_pages_this_period=overage,
        current_period_end=None,
        usage_reset_at=None,
    )
    return u


def _db_returning(user):
    """Build an AsyncSession mock whose execute().scalar_one_or_none() returns user."""
    db = MagicMock()
    exec_result = MagicMock()
    exec_result.scalar_one_or_none = MagicMock(return_value=user)
    db.execute = AsyncMock(return_value=exec_result)
    db.commit = AsyncMock()
    db.refresh = AsyncMock()
    return db


class TestSubscriptionCreated(unittest.IsolatedAsyncioTestCase):
    async def test_price_id_resolves_tier(self):
        """The handler must prefer price_id → tier mapping over metadata."""
        from app.routes import payments
        from app.routes.payments import _handle_subscription_created

        user = _fake_user(tier="free", customer_id="cus_123")
        db = _db_returning(user)

        sub_event = {
            "id": "sub_abc",
            "customer": "cus_123",
            "status": "active",
            "current_period_end": int(datetime(2026, 5, 1).timestamp()),
            "items": {"data": [{"price": {"id": "price_pro_test"}}]},
            "metadata": {"tier": "starter"},  # should be ignored because price wins
        }

        with patch.dict(payments._PRICE_ID_TO_TIER, {"price_pro_test": "pro"}, clear=False):
            await _handle_subscription_created(sub_event, db)

        self.assertEqual(user.subscription_tier, "pro")
        self.assertEqual(user.stripe_subscription_id, "sub_abc")
        self.assertEqual(user.subscription_status, "active")
        self.assertEqual(user.pages_used_this_period, 0)
        self.assertEqual(user.overage_pages_this_period, 0)
        db.commit.assert_awaited()

    async def test_falls_back_to_metadata_tier_when_no_price_match(self):
        from app.routes.payments import _handle_subscription_created

        user = _fake_user(customer_id="cus_456")
        db = _db_returning(user)

        sub_event = {
            "id": "sub_xyz",
            "customer": "cus_456",
            "status": "active",
            "items": {"data": [{"price": {"id": "price_unknown"}}]},
            "metadata": {"tier": "starter"},
        }
        await _handle_subscription_created(sub_event, db)
        self.assertEqual(user.subscription_tier, "starter")

    async def test_unknown_customer_is_ignored(self):
        """Don't mutate another user if the Stripe customer_id has no match."""
        from app.routes.payments import _handle_subscription_created

        db = MagicMock()
        exec_result = MagicMock()
        exec_result.scalar_one_or_none = MagicMock(return_value=None)
        db.execute = AsyncMock(return_value=exec_result)
        db.commit = AsyncMock()

        await _handle_subscription_created(
            {"id": "sub_nobody", "customer": "cus_nobody", "items": {"data": []}},
            db,
        )
        db.commit.assert_not_awaited()


class TestSubscriptionUpdated(unittest.IsolatedAsyncioTestCase):
    async def test_price_id_swap_updates_tier(self):
        from app.routes import payments
        from app.routes.payments import _handle_subscription_updated

        user = _fake_user(tier="starter", sub_id="sub_up")
        db = _db_returning(user)
        sub_event = {
            "id": "sub_up",
            "status": "active",
            "items": {"data": [{"price": {"id": "price_business_test"}}]},
            "metadata": {},
        }
        with patch.dict(payments._PRICE_ID_TO_TIER, {"price_business_test": "business"}, clear=False):
            await _handle_subscription_updated(sub_event, db)
        self.assertEqual(user.subscription_tier, "business")

    async def test_cancel_at_period_end_sets_canceled_status(self):
        from app.routes.payments import _handle_subscription_updated

        user = _fake_user(tier="pro", sub_id="sub_cancel")
        db = _db_returning(user)
        sub_event = {
            "id": "sub_cancel",
            "status": "active",
            "cancel_at_period_end": True,
            "items": {"data": []},
        }
        await _handle_subscription_updated(sub_event, db)
        self.assertEqual(user.subscription_status, "canceled")
        # Tier should NOT flip to free yet — it stays until the period ends.
        self.assertEqual(user.subscription_tier, "pro")


class TestSubscriptionDeleted(unittest.IsolatedAsyncioTestCase):
    async def test_reverts_user_to_free_and_clears_sub(self):
        from app.routes.payments import _handle_subscription_deleted

        user = _fake_user(
            tier="pro", sub_id="sub_gone",
            pages=1000, overage=20,
        )
        user.current_period_end = datetime(2026, 4, 1)
        db = _db_returning(user)

        await _handle_subscription_deleted({"id": "sub_gone"}, db)

        self.assertEqual(user.subscription_tier, "free")
        self.assertEqual(user.subscription_status, "active")
        self.assertIsNone(user.stripe_subscription_id)
        self.assertIsNone(user.current_period_end)
        self.assertEqual(user.pages_used_this_period, 0)
        self.assertEqual(user.overage_pages_this_period, 0)


class TestInvoicePaid(unittest.IsolatedAsyncioTestCase):
    async def test_resets_usage_counters_on_renewal(self):
        from app.routes.payments import _handle_invoice_paid

        user = _fake_user(
            tier="pro", sub_id="sub_paid",
            pages=18000, overage=0,
        )
        db = _db_returning(user)

        period_end_ts = int(datetime(2026, 5, 18).timestamp())
        invoice = {
            "subscription": "sub_paid",
            "lines": {"data": [{"period": {"end": period_end_ts}}]},
        }
        await _handle_invoice_paid(invoice, db)

        self.assertEqual(user.pages_used_this_period, 0)
        self.assertEqual(user.overage_pages_this_period, 0)
        self.assertEqual(user.subscription_status, "active")
        self.assertIsNotNone(user.current_period_end)
        self.assertEqual(user.usage_reset_at, user.current_period_end)

    async def test_falls_back_to_subscription_retrieve_when_lines_missing(self):
        """If the invoice payload has no line-item period, the handler must
        fetch the subscription from Stripe to get current_period_end."""
        from app.routes.payments import _handle_invoice_paid

        user = _fake_user(tier="pro", sub_id="sub_fallback", pages=500)
        db = _db_returning(user)

        expected_ts = int(datetime(2026, 6, 1).timestamp())
        retrieve_stub = MagicMock(return_value={"current_period_end": expected_ts})

        with patch("app.routes.payments.stripe.Subscription.retrieve", retrieve_stub):
            await _handle_invoice_paid({"subscription": "sub_fallback"}, db)

        retrieve_stub.assert_called_once_with("sub_fallback")
        self.assertEqual(user.pages_used_this_period, 0)
        self.assertIsNotNone(user.current_period_end)


class TestInvoicePaymentFailed(unittest.IsolatedAsyncioTestCase):
    async def test_marks_user_past_due(self):
        from app.routes.payments import _handle_invoice_failed

        user = _fake_user(tier="pro", sub_id="sub_failed")
        db = _db_returning(user)

        await _handle_invoice_failed({"subscription": "sub_failed"}, db)
        self.assertEqual(user.subscription_status, "past_due")
        # Tier must NOT flip on a failed payment — Stripe will retry.
        self.assertEqual(user.subscription_tier, "pro")
        # Usage counters must NOT be reset on a failed payment.
        self.assertEqual(user.pages_used_this_period, 0)

    async def test_missing_subscription_id_is_ignored(self):
        from app.routes.payments import _handle_invoice_failed

        db = MagicMock()
        db.execute = AsyncMock()
        db.commit = AsyncMock()
        await _handle_invoice_failed({}, db)
        db.execute.assert_not_awaited()
        db.commit.assert_not_awaited()


class TestResolveTierPrecedence(unittest.TestCase):
    """_resolve_tier is the brains of tier detection — price_id beats
    metadata beats fallback. A regression here silently mislabels every
    webhook-driven tier change."""

    def test_price_id_wins_over_metadata(self):
        from app.routes import payments
        from app.routes.payments import _resolve_tier

        obj = {
            "items": {"data": [{"price": {"id": "price_pro_abc"}}]},
            "metadata": {"tier": "starter"},
        }
        with patch.dict(payments._PRICE_ID_TO_TIER, {"price_pro_abc": "pro"}, clear=False):
            self.assertEqual(_resolve_tier(obj, fallback="free"), "pro")

    def test_metadata_used_when_price_unknown(self):
        from app.routes.payments import _resolve_tier
        obj = {
            "items": {"data": [{"price": {"id": "price_unknown"}}]},
            "metadata": {"tier": "business"},
        }
        self.assertEqual(_resolve_tier(obj, fallback="free"), "business")

    def test_fallback_used_when_neither_source_matches(self):
        from app.routes.payments import _resolve_tier
        obj = {"items": {"data": []}, "metadata": {}}
        self.assertEqual(_resolve_tier(obj, fallback="starter"), "starter")

    def test_invalid_metadata_tier_is_rejected(self):
        from app.routes.payments import _resolve_tier
        obj = {"items": {"data": []}, "metadata": {"tier": "premium_gold"}}
        self.assertEqual(_resolve_tier(obj, fallback="pro"), "pro")


class TestWebhookSignatureRejection(unittest.IsolatedAsyncioTestCase):
    """POST /payments/webhook with a bad signature must 400 and NOT mutate DB."""

    async def test_bad_signature_returns_400(self):
        from fastapi import HTTPException
        import stripe
        from app.routes.payments import stripe_webhook

        fake_req = MagicMock()
        fake_req.body = AsyncMock(return_value=b"{}")
        fake_req.headers = {"stripe-signature": "not-a-real-sig"}
        db = MagicMock()
        db.commit = AsyncMock()

        def raise_sig(*_args, **_kwargs):
            raise stripe.error.SignatureVerificationError("bad", "sig_header")

        with patch("app.routes.payments.stripe.Webhook.construct_event", raise_sig):
            with self.assertRaises(HTTPException) as ctx:
                await stripe_webhook(fake_req, db)
        self.assertEqual(ctx.exception.status_code, 400)
        db.commit.assert_not_awaited()


if __name__ == "__main__":
    unittest.main(verbosity=2)
