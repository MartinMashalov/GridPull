import stripe
from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from pydantic import BaseModel

from app.database import get_db
from app.models.user import User
from app.models.payment import Payment
from app.middleware.auth_middleware import get_current_user
from app.config import settings

stripe.api_key = settings.stripe_secret_key

router = APIRouter(prefix="/payments", tags=["payments"])


class CheckoutRequest(BaseModel):
    amount: float  # dollars (e.g. 10.00 → add $10.00 to balance)


@router.post("/create-checkout")
async def create_checkout(
    request: CheckoutRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Create a Stripe checkout session to add funds to the user's balance."""
    if request.amount < 1.0:
        raise HTTPException(status_code=400, detail="Minimum top-up is $1.00")

    amount_cents = round(request.amount * 100)

    try:
        session = stripe.checkout.Session.create(
            payment_method_types=["card"],
            line_items=[
                {
                    "price_data": {
                        "currency": "usd",
                        "product_data": {
                            "name": "GridPull Balance Top-Up",
                            "description": f"Add ${request.amount:.2f} to your GridPull balance",
                        },
                        "unit_amount": amount_cents,
                    },
                    "quantity": 1,
                }
            ],
            mode="payment",
            success_url=f"{settings.frontend_url}/settings?payment=success&amount={request.amount:.2f}",
            cancel_url=f"{settings.frontend_url}/settings?payment=cancelled",
            metadata={
                "user_id": current_user.id,
                "amount_cents": amount_cents,
            },
        )

        # Record pending payment
        payment = Payment(
            user_id=current_user.id,
            stripe_session_id=session.id,
            amount=amount_cents,
            credits=0,  # no credit concept — kept for schema compatibility
            status="pending",
        )
        db.add(payment)
        await db.commit()

        return {"checkout_url": session.url}

    except stripe.error.StripeError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/webhook")
async def stripe_webhook(request: Request, db: AsyncSession = Depends(get_db)):
    """Handle Stripe webhooks — credit the user's dollar balance on successful payment."""
    payload = await request.body()
    sig_header = request.headers.get("stripe-signature", "")

    try:
        event = stripe.Webhook.construct_event(
            payload, sig_header, settings.stripe_webhook_secret
        )
    except (stripe.error.SignatureVerificationError, ValueError):
        raise HTTPException(status_code=400, detail="Invalid webhook")

    if event["type"] == "checkout.session.completed":
        session = event["data"]["object"]
        user_id = session["metadata"].get("user_id")
        # Use amount_total from Stripe (authoritative) converted from cents to dollars
        amount_dollars = (session.get("amount_total") or 0) / 100.0

        if user_id and amount_dollars > 0:
            result = await db.execute(select(User).where(User.id == user_id))
            user = result.scalar_one_or_none()
            if user:
                user.balance += amount_dollars
                await db.commit()

            # Update payment record
            result = await db.execute(
                select(Payment).where(Payment.stripe_session_id == session["id"])
            )
            payment = result.scalar_one_or_none()
            if payment:
                payment.status = "complete"
                payment.stripe_payment_intent = session.get("payment_intent")
                await db.commit()

    return {"status": "ok"}


@router.get("/me")
async def get_balance(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get current user's dollar balance."""
    return {"balance": current_user.balance}
