from sqlalchemy import Column, String, Integer, Float, DateTime, Boolean
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
    credits = Column(Integer, default=10)  # Start with 10 free credits
    is_active = Column(Boolean, default=True)
    auto_renewal_enabled = Column(Boolean, default=False)
    auto_renewal_threshold = Column(Float, default=5.0)
    auto_renewal_refill = Column(Float, default=20.0)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    jobs = relationship("ExtractionJob", back_populates="user")
    payments = relationship("Payment", back_populates="user")
