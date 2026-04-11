from sqlalchemy import Column, String, Integer, Float, DateTime, Boolean, JSON
from sqlalchemy.orm import relationship
from datetime import datetime
import uuid
from app.database import Base


class User(Base):
    __tablename__ = "users"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    email = Column(String, unique=True, nullable=False, index=True)
    name = Column(String, nullable=False)
    picture = Column(String, nullable=True)
    google_id = Column(String, unique=True, nullable=True, index=True)
    microsoft_id = Column(String, unique=True, nullable=True, index=True)
    balance = Column(Float, default=1.0)
    is_active = Column(Boolean, default=True)
    auto_renewal_enabled = Column(Boolean, default=False)
    auto_renewal_threshold = Column(Float, default=5.0)
    auto_renewal_refill = Column(Float, default=20.0)
    stripe_customer_id = Column(String, nullable=True)
    stripe_payment_method_id = Column(String, nullable=True)
    stripe_card_brand = Column(String, nullable=True)
    stripe_card_last4 = Column(String, nullable=True)

    # Subscription fields
    subscription_tier = Column(String, default="free")  # free / starter / pro / business
    stripe_subscription_id = Column(String, nullable=True)
    subscription_status = Column(String, default="active")  # active / canceled / past_due / trialing
    current_period_end = Column(DateTime, nullable=True)
    pages_used_this_period = Column(Integer, default=0)
    overage_pages_this_period = Column(Integer, default=0)
    usage_reset_at = Column(DateTime, nullable=True)

    # Email ingest
    ingest_address_key = Column(String, unique=True, nullable=True, index=True)

    # User default extraction fields (JSON list of {name, description})
    default_fields = Column(JSON, nullable=True)

    # Named extraction presets: [{name: str, fields: [{name, description}]}]
    field_presets = Column(JSON, nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    jobs = relationship("ExtractionJob", back_populates="user")
    payments = relationship("Payment", back_populates="user")
