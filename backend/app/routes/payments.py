import asyncio
import logging
from datetime import datetime, timezone

import stripe
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.database import get_db
from app.models.user import User
from app.middleware.auth_middleware import get_current_user
from app.config import settings
from app.services.subscription_tiers import (
    TIERS, TIER_ORDER, get_tier, is_upgrade, tier_info_dict,
)

stripe.api_key = settings.stripe_secret_key
logger = logging.getLogger(__name__)

router = APIRouter(prefix="/payments", tags=["payments"])

STRIPE_PRICE_MAP = {
    "starter": settings.stripe_price_starter,
    "pro": settings.stripe_price_pro,
    "business": settings.stripe_price_business,
}

STRIPE_LOOKUP_KEY_MAP = {
    "starter": "gridpull_starter_monthly",
    "pro": "gridpull_pro_monthly",
    "business": "gridpull_business_monthly",
}

# Reverse map: price_id → tier name.  Built at startup from the same env vars so
# it stays in sync without any manual maintenance.
_PRICE_ID_TO_TIER: dict[str, str] = {
    v: k for k, v in STRIPE_PRICE_MAP.items() if v
}


def _resolve_tier(stripe_obj: dict, fallback: str | None = None) -> str | None:
    """Return the tier name for a Stripe subscription or checkout-session object.

    Resolution order (most → least authoritative):
    1. Price ID on the first subscription item  →  authoritative, no metadata needed
    2. ``metadata.tier`` on the object itself
    3. ``fallback`` argument (caller-supplied, e.g. the current DB value)
    4. None  →  caller should NOT overwrite the existing DB value
    """
    items = stripe_obj.get("items", {}).get("data", []) if isinstance(stripe_obj, dict) else []
    for item in items:
        price_id = item.get("price", {}).get("id") or item.get("price")
        if price_id and price_id in _PRICE_ID_TO_TIER:
            return _PRICE_ID_TO_TIER[price_id]

    meta_tier = (stripe_obj.get("metadata") or {}).get("tier") if isinstance(stripe_obj, dict) else None
    if meta_tier and meta_tier in TIERS:
        return meta_tier

    return fallback


async def _create_stripe_customer(email: str, name: str, user_id: str) -> str:
    customer = await asyncio.to_thread(
        stripe.Customer.create,
        email=email, name=name, metadata={"user_id": user_id},
    )
    return customer.id


async def _ensure_stripe_customer(user: User, db: AsyncSession) -> str:
    result = await db.execute(select(User).where(User.id == user.id))
    db_user = result.scalar_one_or_none()
    if not db_user:
        raise HTTPException(404, "User not found")
    if db_user.stripe_customer_id:
        return db_user.stripe_customer_id
    customer_id = await _create_stripe_customer(db_user.email, db_user.name, db_user.id)
    db_user.stripe_customer_id = customer_id
    await db.commit()
    return customer_id


async def _get_stripe_price_id(tier_name: str) -> str:
    configured_price_id = STRIPE_PRICE_MAP.get(tier_name, "")
    expected_amount = TIERS[tier_name].price_monthly

    if configured_price_id:
        try:
            price = await asyncio.to_thread(stripe.Price.retrieve, configured_price_id)
            recurring = price.get("recurring") or {}
            if (
                price.get("active")
                and price.get("unit_amount") == expected_amount
                and recurring.get("interval") == "month"
            ):
                return configured_price_id
            logger.warning(
                "Configured Stripe price for %s is out of date: id=%s amount=%s expected=%s",
                tier_name,
                configured_price_id,
                price.get("unit_amount"),
                expected_amount,
            )
        except Exception as exc:
            logger.warning("Could not retrieve configured Stripe price %s: %s", configured_price_id, exc)

    lookup_key = STRIPE_LOOKUP_KEY_MAP.get(tier_name)
    if lookup_key:
        try:
            price_list = await asyncio.to_thread(
                stripe.Price.list,
                lookup_keys=[lookup_key],
                active=True,
                limit=10,
            )
            for price in price_list.data:
                recurring = price.get("recurring") or {}
                if price.get("unit_amount") == expected_amount and recurring.get("interval") == "month":
                    return price["id"]
        except Exception as exc:
            logger.warning("Could not list Stripe prices for %s via lookup key %s: %s", tier_name, lookup_key, exc)

    raise HTTPException(500, "Stripe price not configured for this tier")


def _maybe_reset_usage(user: User) -> bool:
    """Reset credits_used if the billing period has rolled over. Returns True if reset."""
    if not user.usage_reset_at:
        return False
    now = datetime.now(timezone.utc)
    reset_at = user.usage_reset_at
    if reset_at.tzinfo is None:
        reset_at = reset_at.replace(tzinfo=timezone.utc)
    if now >= reset_at:
        user.credits_used_this_period = 0
        user.overage_credits_this_period = 0
        if user.current_period_end:
            pe = user.current_period_end
            if pe.tzinfo is None:
                pe = pe.replace(tzinfo=timezone.utc)
            user.usage_reset_at = pe
        return True
    return False


# ── Subscription info ──────────────────────────────────────────────────────────

@router.get("/subscription")
async def get_subscription(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(User).where(User.id == current_user.id))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(404)
    _maybe_reset_usage(user)
    await db.commit()

    tier = get_tier(user.subscription_tier)
    usage_pct = (user.credits_used_this_period / tier.credits_per_month * 100) if tier.credits_per_month else 0

    return {
        "tier": tier_info_dict(tier),
        "status": user.subscription_status,
        "credits_used": user.credits_used_this_period,
        "overage_credits": user.overage_credits_this_period,
        "credits_limit": tier.credits_per_month,
        "usage_percent": min(usage_pct, 100),
        "current_period_end": user.current_period_end.isoformat() if user.current_period_end else None,
        "all_tiers": [tier_info_dict(TIERS[t]) for t in TIER_ORDER],
        "has_card": bool(user.stripe_payment_method_id),
    }


@router.get("/tiers")
async def get_tiers():
    return {"tiers": [tier_info_dict(TIERS[t]) for t in TIER_ORDER]}


# ── Create / change / cancel subscription ──────────────────────────────────────

class SubscribeRequest(BaseModel):
    tier: str


@router.post("/create-subscription")
async def create_subscription(
    body: SubscribeRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if body.tier not in STRIPE_PRICE_MAP or body.tier == "free":
        raise HTTPException(400, "Invalid tier")

    price_id = await _get_stripe_price_id(body.tier)

    customer_id = await _ensure_stripe_customer(current_user, db)
    result = await db.execute(select(User).where(User.id == current_user.id))
    db_user = result.scalar_one_or_none()
    if not db_user:
        raise HTTPException(404, "User not found")

    session = await asyncio.to_thread(
        stripe.checkout.Session.create,
        customer=customer_id,
        payment_method_types=["card"],
        mode="subscription",
        line_items=[{"price": price_id, "quantity": 1}],
        subscription_data={"metadata": {"tier": body.tier}},
        success_url=f"{settings.frontend_url}/settings?subscription=success&session_id={{CHECKOUT_SESSION_ID}}",
        cancel_url=f"{settings.frontend_url}/settings?subscription=cancelled",
        metadata={"user_id": current_user.id, "tier": body.tier},
    )
    logger.info("Created subscription checkout for user %s tier=%s", current_user.id, body.tier)
    return {"checkout_url": session.url}


@router.post("/change-subscription")
async def change_subscription(
    body: SubscribeRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if body.tier == "free":
        return await cancel_subscription(current_user=current_user, db=db)

    if body.tier not in STRIPE_PRICE_MAP:
        raise HTTPException(400, "Invalid tier")

    stripe_subscription_id = getattr(current_user, "stripe_subscription_id", None)
    if not stripe_subscription_id:
        return await create_subscription(body=body, current_user=current_user, db=db)

    price_id = await _get_stripe_price_id(body.tier)

    sub = await asyncio.to_thread(stripe.Subscription.retrieve, stripe_subscription_id)
    item_id = sub["items"]["data"][0]["id"]

    proration = "always_invoice" if is_upgrade(current_user.subscription_tier, body.tier) else "none"
    await asyncio.to_thread(
        stripe.Subscription.modify,
        stripe_subscription_id,
        items=[{"id": item_id, "price": price_id}],
        proration_behavior=proration,
        metadata={"tier": body.tier},
    )

    result = await db.execute(select(User).where(User.id == current_user.id))
    user = result.scalar_one_or_none()
    if user:
        user.subscription_tier = body.tier
        user.subscription_status = "active"
        await db.commit()

    logger.info("Changed subscription for user %s to %s", current_user.id, body.tier)
    return {"ok": True, "tier": body.tier}


@router.post("/cancel-subscription")
async def cancel_subscription(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    stripe_subscription_id = getattr(current_user, "stripe_subscription_id", None)
    if stripe_subscription_id:
        await asyncio.to_thread(
            stripe.Subscription.modify,
            stripe_subscription_id,
            cancel_at_period_end=True,
        )

    result = await db.execute(select(User).where(User.id == current_user.id))
    user = result.scalar_one_or_none()
    if user:
        user.subscription_status = "canceled"
        await db.commit()

    logger.info("Subscription cancel requested for user %s", current_user.id)
    return {"ok": True}


@router.post("/reactivate-subscription")
async def reactivate_subscription(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    stripe_subscription_id = getattr(current_user, "stripe_subscription_id", None)
    if not stripe_subscription_id:
        raise HTTPException(400, "No active subscription to reactivate")

    await asyncio.to_thread(
        stripe.Subscription.modify,
        stripe_subscription_id,
        cancel_at_period_end=False,
    )

    result = await db.execute(select(User).where(User.id == current_user.id))
    user = result.scalar_one_or_none()
    if user:
        user.subscription_status = "active"
        await db.commit()

    return {"ok": True}


# ── Card management ───────────────────────────────────────────────────────────

@router.post("/setup-card")
async def setup_card(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    customer_id = await _ensure_stripe_customer(current_user, db)
    session = await asyncio.to_thread(
        stripe.checkout.Session.create,
        customer=customer_id,
        payment_method_types=["card"],
        mode="setup",
        success_url=f"{settings.frontend_url}/settings?card=saved",
        cancel_url=f"{settings.frontend_url}/settings",
        metadata={"user_id": current_user.id},
    )
    return {"setup_url": session.url}


@router.get("/saved-card")
async def get_saved_card(current_user: User = Depends(get_current_user)):
    if not current_user.stripe_payment_method_id:
        return {"card": None}
    return {"card": {
        "brand": current_user.stripe_card_brand or "",
        "last4": current_user.stripe_card_last4 or "",
    }}


@router.delete("/saved-card")
async def remove_saved_card(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if current_user.stripe_payment_method_id:
        try:
            await asyncio.to_thread(stripe.PaymentMethod.detach, current_user.stripe_payment_method_id)
        except stripe.error.StripeError:
            pass

    result = await db.execute(select(User).where(User.id == current_user.id))
    user = result.scalar_one_or_none()
    if user:
        user.stripe_payment_method_id = None
        user.stripe_card_brand = None
        user.stripe_card_last4 = None
        await db.commit()
    return {"status": "removed"}


# ── Usage check (called by frontend for warnings) ─────────────────────────────

@router.get("/usage-warning")
async def get_usage_warning(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(User).where(User.id == current_user.id))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(404)
    _maybe_reset_usage(user)
    await db.commit()

    tier = get_tier(user.subscription_tier)
    pct = (user.credits_used_this_period / tier.credits_per_month * 100) if tier.credits_per_month else 0
    at_limit = user.credits_used_this_period >= tier.credits_per_month
    near_limit = pct >= 80 and not at_limit

    warning = None
    if at_limit and tier.name == "free":
        warning = "limit_reached_free"
    elif at_limit and tier.overage_rate:
        warning = "limit_reached_paid"
    elif near_limit:
        warning = "near_limit"

    next_tier = None
    idx = TIER_ORDER.index(tier.name)
    if idx < len(TIER_ORDER) - 1:
        next_tier = tier_info_dict(TIERS[TIER_ORDER[idx + 1]])

    return {
        "warning": warning,
        "credits_used": user.credits_used_this_period,
        "credits_limit": tier.credits_per_month,
        "overage_credits": user.overage_credits_this_period,
        "overage_rate": tier.overage_rate,
        "usage_percent": min(pct, 100),
        "tier": tier.name,
        "next_tier": next_tier,
    }


# ── Legacy balance endpoint (keep for compatibility) ──────────────────────────

@router.get("/me")
async def get_balance(current_user: User = Depends(get_current_user)):
    return {"balance": current_user.balance}


# ── Stripe Webhook ─────────────────────────────────────────────────────────────

async def _save_card_from_payment_method(user_id: str, pm_id: str, db: AsyncSession) -> None:
    try:
        pm = await asyncio.to_thread(stripe.PaymentMethod.retrieve, pm_id)
        card = pm.get("card", {})
        result = await db.execute(select(User).where(User.id == user_id))
        user = result.scalar_one_or_none()
        if user:
            user.stripe_payment_method_id = pm_id
            user.stripe_card_brand = card.get("brand", "")
            user.stripe_card_last4 = card.get("last4", "")
            await db.commit()
    except Exception as e:
        logger.warning("Could not save card for user %s: %s", user_id, e)


@router.post("/webhook")
async def stripe_webhook(request: Request, db: AsyncSession = Depends(get_db)):
    payload = await request.body()
    sig_header = request.headers.get("stripe-signature", "")

    try:
        event = stripe.Webhook.construct_event(payload, sig_header, settings.stripe_webhook_secret)
    except (stripe.error.SignatureVerificationError, ValueError):
        raise HTTPException(status_code=400, detail="Invalid webhook signature")

    event_type = event["type"]
    data = event["data"]["object"]

    # ── Subscription lifecycle events ──────────────────────────────────────────

    if event_type == "customer.subscription.created":
        await _handle_subscription_created(data, db)

    elif event_type == "customer.subscription.updated":
        await _handle_subscription_updated(data, db)

    elif event_type == "customer.subscription.deleted":
        await _handle_subscription_deleted(data, db)

    elif event_type == "invoice.paid":
        await _handle_invoice_paid(data, db)

    elif event_type == "invoice.payment_failed":
        await _handle_invoice_failed(data, db)

    # ── Legacy checkout.session.completed (for card saves / old payments) ──────

    elif event_type == "checkout.session.completed":
        session = data
        user_id = session.get("metadata", {}).get("user_id")
        mode = session.get("mode")

        if mode == "setup" and user_id and session.get("setup_intent"):
            try:
                si = await asyncio.to_thread(stripe.SetupIntent.retrieve, session["setup_intent"])
                pm_id = si.get("payment_method")
                if pm_id:
                    await _save_card_from_payment_method(user_id, pm_id, db)
            except Exception as e:
                logger.warning("Could not save card from setup: %s", e)
        elif mode == "subscription":
            customer_id = session.get("customer")
            sub_id = session.get("subscription")

            user = None
            if user_id:
                result = await db.execute(select(User).where(User.id == user_id))
                user = result.scalar_one_or_none()
            if not user and customer_id:
                result = await db.execute(select(User).where(User.stripe_customer_id == customer_id))
                user = result.scalar_one_or_none()

            if not user:
                logger.warning(
                    "checkout.session.completed(subscription) for unknown user_id=%s customer=%s",
                    user_id, customer_id,
                )
                return {"status": "ok"}

            sub = None
            if sub_id:
                try:
                    sub = await asyncio.to_thread(stripe.Subscription.retrieve, sub_id)
                except Exception as e:
                    logger.warning("Could not retrieve Stripe subscription %s: %s", sub_id, e)

            # Resolve tier: price ID on the subscription beats session metadata
            tier = _resolve_tier(sub or {}, fallback=_resolve_tier(session, fallback=None))
            if not tier:
                logger.warning(
                    "checkout.session.completed: could not resolve tier for sub=%s session_meta=%s — keeping existing tier",
                    sub_id, (session.get("metadata") or {}),
                )
                tier = user.subscription_tier  # keep whatever is already in DB

            user.stripe_customer_id = customer_id or user.stripe_customer_id
            user.stripe_subscription_id = sub_id or user.stripe_subscription_id
            user.subscription_tier = tier
            user.subscription_status = (
                sub.get("status", "active")
                if isinstance(sub, dict)
                else "active"
            )
            if isinstance(sub, dict) and sub.get("current_period_end"):
                user.current_period_end = datetime.utcfromtimestamp(sub["current_period_end"])
                user.usage_reset_at = user.current_period_end
            user.credits_used_this_period = 0
            user.overage_credits_this_period = 0
            await db.commit()
            logger.info(
                "Checkout subscription completed: user=%s tier=%s sub=%s",
                user.id, tier, user.stripe_subscription_id,
            )

    return {"status": "ok"}


async def _handle_subscription_created(sub: dict, db: AsyncSession):
    customer_id = sub.get("customer")
    tier = _resolve_tier(sub, fallback=None)
    if not tier:
        logger.warning(
            "subscription.created: could not resolve tier for customer=%s sub=%s meta=%s — defaulting to free",
            customer_id, sub.get("id"), (sub.get("metadata") or {}),
        )
        tier = "free"
    result = await db.execute(select(User).where(User.stripe_customer_id == customer_id))
    user = result.scalar_one_or_none()
    if not user:
        logger.warning("Subscription created for unknown customer %s", customer_id)
        return

    user.stripe_subscription_id = sub["id"]
    user.subscription_tier = tier
    user.subscription_status = sub.get("status", "active")
    if sub.get("current_period_end"):
        user.current_period_end = datetime.utcfromtimestamp(sub["current_period_end"])
        user.usage_reset_at = user.current_period_end
    user.credits_used_this_period = 0
    user.overage_credits_this_period = 0
    await db.commit()
    logger.info("Subscription created: user=%s tier=%s sub=%s", user.id, tier, sub["id"])


async def _handle_subscription_updated(sub: dict, db: AsyncSession):
    sub_id = sub["id"]
    result = await db.execute(select(User).where(User.stripe_subscription_id == sub_id))
    user = result.scalar_one_or_none()
    if not user:
        logger.warning("Subscription updated for unknown sub %s", sub_id)
        return

    # Prefer price ID → metadata → keep existing DB value (never blindly default)
    tier = _resolve_tier(sub, fallback=user.subscription_tier)
    user.subscription_tier = tier
    user.subscription_status = sub.get("status", "active")
    if sub.get("current_period_end"):
        user.current_period_end = datetime.utcfromtimestamp(sub["current_period_end"])
        user.usage_reset_at = user.current_period_end

    if sub.get("cancel_at_period_end"):
        user.subscription_status = "canceled"

    await db.commit()
    logger.info("Subscription updated: user=%s tier=%s status=%s", user.id, tier, user.subscription_status)


async def _handle_subscription_deleted(sub: dict, db: AsyncSession):
    sub_id = sub["id"]
    result = await db.execute(select(User).where(User.stripe_subscription_id == sub_id))
    user = result.scalar_one_or_none()
    if not user:
        return

    user.subscription_tier = "free"
    user.subscription_status = "active"
    user.stripe_subscription_id = None
    user.current_period_end = None
    user.credits_used_this_period = 0
    user.overage_credits_this_period = 0
    await db.commit()
    logger.info("Subscription deleted — user %s reverted to free", user.id)


async def _handle_invoice_paid(invoice: dict, db: AsyncSession):
    sub_id = invoice.get("subscription")
    if not sub_id:
        return
    result = await db.execute(select(User).where(User.stripe_subscription_id == sub_id))
    user = result.scalar_one_or_none()
    if not user:
        return

    # Reset usage on successful renewal payment
    user.credits_used_this_period = 0
    user.overage_credits_this_period = 0
    user.subscription_status = "active"
    period_end_ts = None
    try:
        lines = invoice.get("lines", {}).get("data", [])
        if lines:
            period_end_ts = lines[0].get("period", {}).get("end")
    except Exception:
        period_end_ts = None

    if not period_end_ts:
        try:
            sub = await asyncio.to_thread(stripe.Subscription.retrieve, sub_id)
            period_end_ts = sub.get("current_period_end")
        except Exception as e:
            logger.warning(
                "Could not fetch current_period_end from Stripe for sub %s: %s",
                sub_id, e,
            )

    if period_end_ts:
        user.current_period_end = datetime.utcfromtimestamp(period_end_ts)
        user.usage_reset_at = user.current_period_end
    await db.commit()
    logger.info("Invoice paid — usage reset for user %s", user.id)


async def _handle_invoice_failed(invoice: dict, db: AsyncSession):
    sub_id = invoice.get("subscription")
    if not sub_id:
        return
    result = await db.execute(select(User).where(User.stripe_subscription_id == sub_id))
    user = result.scalar_one_or_none()
    if not user:
        return
    user.subscription_status = "past_due"
    await db.commit()
    logger.warning("Invoice payment failed — user %s set to past_due", user.id)


@router.post("/admin/audit-tiers")
async def audit_tiers(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Check every user with an active Stripe subscription and verify their DB tier
    matches what Stripe reports via price ID.  Pass ``fix=true`` as a query param
    to apply corrections.  Admin-only (raises 403 for non-admin callers).
    """
    if not getattr(current_user, "is_admin", False):
        raise HTTPException(403, "Admin only")

    result = await db.execute(
        select(User).where(User.stripe_subscription_id.isnot(None))
    )
    users = result.scalars().all()

    mismatches = []
    fixed = []

    for user in users:
        try:
            sub = await asyncio.to_thread(stripe.Subscription.retrieve, user.stripe_subscription_id)
        except Exception as e:
            logger.warning("audit: could not fetch sub %s for user %s: %s", user.stripe_subscription_id, user.id, e)
            continue

        correct_tier = _resolve_tier(sub, fallback=None)
        if correct_tier is None:
            logger.warning(
                "audit: cannot determine tier for user=%s sub=%s price_ids=%s meta=%s",
                user.id, user.stripe_subscription_id,
                [i.get("price", {}).get("id") for i in sub.get("items", {}).get("data", [])],
                sub.get("metadata"),
            )
            continue

        if user.subscription_tier != correct_tier:
            mismatches.append({
                "user_id": user.id,
                "email": user.email,
                "db_tier": user.subscription_tier,
                "correct_tier": correct_tier,
                "sub_id": user.stripe_subscription_id,
            })
            user.subscription_tier = correct_tier
            fixed.append(user.id)

    if fixed:
        await db.commit()
        logger.info("audit-tiers: fixed %d accounts: %s", len(fixed), fixed)

    return {"mismatches_found": len(mismatches), "fixed": fixed, "details": mismatches}
