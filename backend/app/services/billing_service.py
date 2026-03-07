"""
Auto-renewal: charge the user's saved card when balance drops below threshold.

Called after every balance deduction (job_processor, pipeline_poller).
Fire-and-forget — failures are logged but never raise.
"""

from __future__ import annotations

import asyncio
import logging

import stripe
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.user import User

stripe.api_key = settings.stripe_secret_key
logger = logging.getLogger(__name__)


async def maybe_auto_renew(user: User, db: AsyncSession) -> None:
    """
    If auto-renewal is enabled and the user's balance is below the threshold,
    charge their saved card for the configured refill amount and credit balance.

    Silently no-ops if:
    - auto_renewal_enabled is False
    - balance is still at or above threshold
    - no saved payment method / Stripe customer
    """
    if not user.auto_renewal_enabled:
        return
    if (user.balance or 0.0) >= (user.auto_renewal_threshold or 5.0):
        return
    if not user.stripe_payment_method_id or not user.stripe_customer_id:
        logger.info(
            "Auto-renewal skipped for user %s — no saved payment method", user.id
        )
        return

    refill = float(user.auto_renewal_refill or 20.0)
    amount_cents = round(refill * 100)

    logger.info(
        "Auto-renewal: charging $%.2f for user %s (balance=$%.4f threshold=$%.2f)",
        refill, user.id, user.balance, user.auto_renewal_threshold,
    )

    try:
        intent = await asyncio.to_thread(
            stripe.PaymentIntent.create,
            amount=amount_cents,
            currency="usd",
            customer=user.stripe_customer_id,
            payment_method=user.stripe_payment_method_id,
            off_session=True,
            confirm=True,
            metadata={"user_id": user.id, "reason": "auto_renewal"},
        )

        if intent.status == "succeeded":
            user.balance = (user.balance or 0.0) + refill
            await db.commit()
            logger.info(
                "Auto-renewal succeeded: +$%.2f → balance=$%.4f for user %s",
                refill, user.balance, user.id,
            )
        else:
            logger.warning(
                "Auto-renewal PaymentIntent status=%s for user %s — not crediting",
                intent.status, user.id,
            )

    except stripe.error.CardError as e:
        logger.warning("Auto-renewal card declined for user %s: %s", user.id, e)
    except Exception as e:
        logger.error("Auto-renewal failed for user %s: %s", user.id, e)
