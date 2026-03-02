from sqlalchemy import Column, String, Integer, DateTime, ForeignKey, Index
from sqlalchemy.orm import relationship
from datetime import datetime
import uuid
from app.database import Base


class Payment(Base):
    __tablename__ = "payments"
    __table_args__ = (
        Index("ix_payments_user_id", "user_id"),
        Index("ix_payments_status", "status"),
    )

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String, ForeignKey("users.id"), nullable=False)
    stripe_session_id = Column(String, unique=True, nullable=True)  # unique = implicit index
    stripe_payment_intent = Column(String, nullable=True)
    amount = Column(Integer, nullable=False)  # in cents
    credits = Column(Integer, nullable=False)
    status = Column(String, default="pending")  # pending, complete, failed
    created_at = Column(DateTime, default=datetime.utcnow)

    user = relationship("User", back_populates="payments")
