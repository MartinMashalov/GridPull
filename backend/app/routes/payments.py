import stripe
from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from pydantic import BaseModel

from app.database import get_db
from app.models.user import User
from app.models.payment import Payment
from app.services.auth_service import verify_token
from app.middleware.auth_middleware import get_current_user
from app.config import settings

stripe.api_key = settings.stripe_secret_key

router = APIRouter(prefix="/payments", tags=["payments"])

# Credit packages - map price_id to credits
CREDIT_PACKAGES = {
    "price_10credits": {"credits": 10, "amount": 500},
    "price_50credits": {"credits": 50, "amount": 2000},
    "price_200credits": {"credits": 200, "amount": 6000},
}


class CheckoutRequest(BaseModel):
    price_id: str
    credits: int


@router.post("/create-checkout")
async def create_checkout(
    request: CheckoutRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Create Stripe checkout session."""
    if request.price_id not in CREDIT_PACKAGES:
        raise HTTPException(status_code=400, detail="Invalid package")

    pkg = CREDIT_PACKAGES[request.price_id]

    try:
        session = stripe.checkout.Session.create(
            payment_method_types=["card"],
            line_items=[
                {
                    "price_data": {
                        "currency": "usd",
                        "product_data": {
                            "name": f"GridPull {pkg['credits']} Credits",
                            "description": f"{pkg['credits']} PDF extraction credits",
                        },
                        "unit_amount": pkg["amount"],
                    },
                    "quantity": 1,
                }
            ],
            mode="payment",
            success_url=f"{settings.frontend_url}/settings?payment=success&credits={pkg['credits']}",
            cancel_url=f"{settings.frontend_url}/settings?payment=cancelled",
            metadata={
                "user_id": current_user.id,
                "credits": pkg["credits"],
            },
        )

        # Record pending payment
        payment = Payment(
            user_id=current_user.id,
            stripe_session_id=session.id,
            amount=pkg["amount"],
            credits=pkg["credits"],
            status="pending",
        )
        db.add(payment)
        await db.commit()

        return {"checkout_url": session.url}

    except stripe.error.StripeError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/webhook")
async def stripe_webhook(request: Request, db: AsyncSession = Depends(get_db)):
    """Handle Stripe webhooks."""
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
        credits = int(session["metadata"].get("credits", 0))

        if user_id and credits:
            result = await db.execute(select(User).where(User.id == user_id))
            user = result.scalar_one_or_none()
            if user:
                user.credits += credits
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
async def get_my_credits(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get current user's credit balance."""
    return {"credits": current_user.credits}
