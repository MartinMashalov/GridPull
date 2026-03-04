import asyncio
import logging
import stripe
from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import RedirectResponse, HTMLResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from pydantic import BaseModel
from jose import jwt, JWTError

from app.database import get_db
from app.models.user import User
from app.models.payment import Payment
from app.middleware.auth_middleware import get_current_user
from app.config import settings

stripe.api_key = settings.stripe_secret_key
logger = logging.getLogger(__name__)

router = APIRouter(prefix="/payments", tags=["payments"])


class CheckoutRequest(BaseModel):
    amount: float


# ── Async helpers (all Stripe SDK calls are sync — run in thread) ─────────────

async def _create_stripe_customer(email: str, name: str, user_id: str) -> str:
    customer = await asyncio.to_thread(
        stripe.Customer.create,
        email=email,
        name=name,
        metadata={"user_id": user_id},
    )
    return customer.id


async def _create_checkout_session(**kwargs) -> stripe.checkout.Session:
    return await asyncio.to_thread(stripe.checkout.Session.create, **kwargs)


async def _save_card_from_payment_method(user_id: str, pm_id: str, db: AsyncSession) -> None:
    """Retrieve a Stripe PaymentMethod and persist brand/last4 to the user row."""
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
            logger.info("Saved card for user %s: %s ****%s", user_id, card.get("brand"), card.get("last4"))
    except Exception as e:
        logger.warning("Could not save card for user %s: %s", user_id, e)


# ── Routes ────────────────────────────────────────────────────────────────────

@router.post("/checkout-go")
async def checkout_go(
    amount: float = Form(...),
    token: str = Form(...),
    db: AsyncSession = Depends(get_db),
):
    """
    Form-POST endpoint: validate token, create Stripe session, return 302 → Stripe.
    Used by the frontend <form> so no JS redirect is needed — works in any browser.
    """
    # Validate JWT from form field (same logic as auth middleware)
    try:
        payload = jwt.decode(
            token,
            settings.jwt_secret_key,
            algorithms=[settings.jwt_algorithm],
            options={"verify_exp": False},
        )
        user_id = payload.get("sub")
        if not user_id:
            raise ValueError("no sub")
    except (JWTError, ValueError):
        return HTMLResponse("<h1>Invalid session — please log in again</h1>", status_code=401)

    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        return HTMLResponse("<h1>User not found</h1>", status_code=404)

    if amount < 1.0:
        return HTMLResponse("<h1>Minimum top-up is $1.00</h1>", status_code=400)

    amount_cents = round(amount * 100)

    try:
        # Get or create Stripe customer
        customer_id = user.stripe_customer_id
        if not customer_id:
            try:
                customer_id = await _create_stripe_customer(user.email, user.name, user.id)
                result2 = await db.execute(select(User).where(User.id == user.id))
                db_user = result2.scalar_one_or_none()
                if db_user:
                    db_user.stripe_customer_id = customer_id
                    await db.commit()
            except Exception:
                customer_id = None

        session_kwargs = dict(
            payment_method_types=["card"],
            line_items=[{
                "price_data": {
                    "currency": "usd",
                    "product_data": {"name": "PDFExcel.ai Balance Top-Up"},
                    "unit_amount": amount_cents,
                },
                "quantity": 1,
            }],
            mode="payment",
            payment_intent_data={"setup_future_usage": "off_session"},
            success_url=f"{settings.frontend_url}/settings?payment=success&session_id={{CHECKOUT_SESSION_ID}}",
            cancel_url=f"{settings.frontend_url}/settings?payment=cancelled",
            metadata={"user_id": user.id, "amount_cents": str(amount_cents)},
        )
        if customer_id:
            session_kwargs["customer"] = customer_id

        session = await _create_checkout_session(**session_kwargs)

        payment = Payment(
            user_id=user.id,
            stripe_session_id=session.id,
            amount=amount_cents,
            credits=0,
            status="pending",
        )
        db.add(payment)
        await db.commit()

        logger.info("Form checkout: redirecting user %s to Stripe ($%.2f)", user.id, amount)
        return RedirectResponse(url=session.url, status_code=302)

    except stripe.error.StripeError as e:
        logger.error("Stripe error in checkout-go: %s", e)
        return HTMLResponse(f"<h1>Stripe error: {e}</h1>", status_code=400)
    except Exception as e:
        logger.error("Unexpected error in checkout-go: %s", e)
        return HTMLResponse("<h1>Payment error — please try again</h1>", status_code=500)


@router.post("/create-checkout")
async def create_checkout(
    request: CheckoutRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Create a Stripe Checkout session to add funds to the user's balance."""
    if request.amount < 1.0:
        raise HTTPException(status_code=400, detail="Minimum top-up is $1.00")

    amount_cents = round(request.amount * 100)

    try:
        # Get or create Stripe customer (non-critical — skip if it fails)
        customer_id = current_user.stripe_customer_id
        if not customer_id:
            try:
                customer_id = await _create_stripe_customer(
                    current_user.email, current_user.name, current_user.id
                )
                result = await db.execute(select(User).where(User.id == current_user.id))
                db_user = result.scalar_one_or_none()
                if db_user:
                    db_user.stripe_customer_id = customer_id
                    await db.commit()
                logger.info("Created Stripe customer %s for user %s", customer_id, current_user.id)
            except Exception as e:
                logger.warning("Could not create Stripe customer for %s: %s — proceeding without", current_user.id, e)
                customer_id = None

        session_kwargs = dict(
            payment_method_types=["card"],
            line_items=[{
                "price_data": {
                    "currency": "usd",
                    "product_data": {
                        "name": "PDFExcel.ai Balance Top-Up",
                        "description": f"Add ${request.amount:.2f} to your balance",
                    },
                    "unit_amount": amount_cents,
                },
                "quantity": 1,
            }],
            mode="payment",
            payment_intent_data={"setup_future_usage": "off_session"},
            # Include session ID in success URL so frontend can verify immediately
            success_url=f"{settings.frontend_url}/settings?payment=success&session_id={{CHECKOUT_SESSION_ID}}",
            cancel_url=f"{settings.frontend_url}/settings?payment=cancelled",
            metadata={"user_id": current_user.id, "amount_cents": str(amount_cents)},
        )
        if customer_id:
            session_kwargs["customer"] = customer_id

        session = await _create_checkout_session(**session_kwargs)
        logger.info("Created checkout session %s for user %s ($%.2f)", session.id, current_user.id, request.amount)

        payment = Payment(
            user_id=current_user.id,
            stripe_session_id=session.id,
            amount=amount_cents,
            credits=0,
            status="pending",
        )
        db.add(payment)
        await db.commit()

        return {"checkout_url": session.url}

    except stripe.error.StripeError as e:
        logger.error("Stripe error creating checkout for user %s: %s", current_user.id, e)
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error("Unexpected error creating checkout for user %s: %s", current_user.id, e)
        raise HTTPException(status_code=500, detail="Payment service error — please try again")


@router.post("/verify-session/{session_id}")
async def verify_session(
    session_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Called by the frontend on return from Stripe checkout.
    Verifies payment directly with Stripe and credits balance — no webhook needed.
    Idempotent: safe to call multiple times (checks payment record status first).
    """
    try:
        # Check if already credited (idempotency)
        result = await db.execute(select(Payment).where(Payment.stripe_session_id == session_id))
        payment = result.scalar_one_or_none()
        if payment and payment.status == "complete":
            logger.info("Session %s already credited — skipping", session_id)
            result2 = await db.execute(select(User).where(User.id == current_user.id))
            user = result2.scalar_one_or_none()
            return {"balance": user.balance if user else current_user.balance, "credited": False}

        # Retrieve session from Stripe
        session = await asyncio.to_thread(stripe.checkout.Session.retrieve, session_id)

        if session.get("payment_status") != "paid":
            raise HTTPException(status_code=400, detail="Payment not completed")

        # Verify session belongs to this user
        if session.get("metadata", {}).get("user_id") != current_user.id:
            raise HTTPException(status_code=403, detail="Session does not belong to this user")

        amount_dollars = (session.get("amount_total") or 0) / 100.0

        # Credit balance
        result2 = await db.execute(select(User).where(User.id == current_user.id))
        user = result2.scalar_one_or_none()
        if user:
            user.balance += amount_dollars
            await db.commit()
            logger.info("Verified and credited $%.2f to user %s (new balance: $%.2f)", amount_dollars, current_user.id, user.balance)

        # Mark payment complete
        if payment:
            payment.status = "complete"
            payment.stripe_payment_intent = session.get("payment_intent")
            await db.commit()

        # Save card if payment method available
        pi_id = session.get("payment_intent")
        if pi_id:
            try:
                intent = await asyncio.to_thread(stripe.PaymentIntent.retrieve, pi_id)
                pm_id = intent.get("payment_method")
                if pm_id:
                    await _save_card_from_payment_method(current_user.id, pm_id, db)
            except Exception as e:
                logger.warning("Could not save card after verify: %s", e)

        return {"balance": user.balance if user else current_user.balance + amount_dollars, "credited": True, "amount": amount_dollars}

    except HTTPException:
        raise
    except stripe.error.StripeError as e:
        logger.error("Stripe error verifying session %s: %s", session_id, e)
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error("Error verifying session %s: %s", session_id, e)
        raise HTTPException(status_code=500, detail="Verification failed")


@router.post("/setup-card")
async def setup_card(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Create a Stripe Setup session to save a card without charging."""
    try:
        customer_id = current_user.stripe_customer_id
        if not customer_id:
            try:
                customer_id = await _create_stripe_customer(
                    current_user.email, current_user.name, current_user.id
                )
                result = await db.execute(select(User).where(User.id == current_user.id))
                db_user = result.scalar_one_or_none()
                if db_user:
                    db_user.stripe_customer_id = customer_id
                    await db.commit()
            except Exception as e:
                logger.warning("Could not create Stripe customer: %s", e)
                raise HTTPException(status_code=500, detail="Could not initialise payment profile")

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

    except stripe.error.StripeError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/saved-card")
async def get_saved_card(current_user: User = Depends(get_current_user)):
    """Return the user's saved card info, or null if none."""
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
    """Detach and remove the user's saved payment method."""
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


@router.post("/webhook")
async def stripe_webhook(request: Request, db: AsyncSession = Depends(get_db)):
    """Handle Stripe webhooks."""
    payload = await request.body()
    sig_header = request.headers.get("stripe-signature", "")

    try:
        event = stripe.Webhook.construct_event(payload, sig_header, settings.stripe_webhook_secret)
    except (stripe.error.SignatureVerificationError, ValueError):
        raise HTTPException(status_code=400, detail="Invalid webhook signature")

    if event["type"] == "checkout.session.completed":
        session = event["data"]["object"]
        user_id = session["metadata"].get("user_id")
        mode = session.get("mode")

        if mode == "payment":
            amount_dollars = (session.get("amount_total") or 0) / 100.0
            if user_id and amount_dollars > 0:
                result = await db.execute(select(User).where(User.id == user_id))
                user = result.scalar_one_or_none()
                if user:
                    user.balance += amount_dollars
                    await db.commit()
                    logger.info("Credited $%.2f to user %s (new balance: $%.2f)", amount_dollars, user_id, user.balance)

            result = await db.execute(select(Payment).where(Payment.stripe_session_id == session["id"]))
            payment = result.scalar_one_or_none()
            if payment:
                payment.status = "complete"
                payment.stripe_payment_intent = session.get("payment_intent")
                await db.commit()

            # Save card from PaymentIntent
            if user_id and session.get("payment_intent"):
                try:
                    intent = await asyncio.to_thread(stripe.PaymentIntent.retrieve, session["payment_intent"])
                    pm_id = intent.get("payment_method")
                    if pm_id:
                        await _save_card_from_payment_method(user_id, pm_id, db)
                except Exception as e:
                    logger.warning("Could not save card from payment: %s", e)

        elif mode == "setup":
            if user_id and session.get("setup_intent"):
                try:
                    si = await asyncio.to_thread(stripe.SetupIntent.retrieve, session["setup_intent"])
                    pm_id = si.get("payment_method")
                    if pm_id:
                        await _save_card_from_payment_method(user_id, pm_id, db)
                except Exception as e:
                    logger.warning("Could not save card from setup: %s", e)

    return {"status": "ok"}


@router.get("/me")
async def get_balance(current_user: User = Depends(get_current_user)):
    return {"balance": current_user.balance}
