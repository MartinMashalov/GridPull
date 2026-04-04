import uuid
from datetime import datetime

from sqlalchemy import Column, DateTime, ForeignKey, Index, Integer, String
from sqlalchemy.orm import relationship

from app.database import Base


def _uuid():
    return str(uuid.uuid4())


def _utcnow():
    return datetime.utcnow()


class IngestAddress(Base):
    __tablename__ = "ingest_addresses"

    id = Column(String, primary_key=True, default=_uuid)
    user_id = Column(String, ForeignKey("users.id"), unique=True, nullable=False)
    address_key = Column(String, unique=True, nullable=False, index=True)
    created_at = Column(DateTime, default=_utcnow)

    user = relationship("User", backref="ingest_address")


class IngestDocument(Base):
    __tablename__ = "ingest_documents"

    id = Column(String, primary_key=True, default=_uuid)
    user_id = Column(String, ForeignKey("users.id"), nullable=False)
    sender_email = Column(String, nullable=False)
    sender_domain = Column(String, nullable=False)
    subject = Column(String, nullable=True)
    message_id = Column(String, nullable=False, index=True)
    filename = Column(String, nullable=False)
    s3_key = Column(String, nullable=False)
    file_size = Column(Integer, nullable=False, default=0)
    content_type = Column(String, nullable=True)
    job_id = Column(String, ForeignKey("extraction_jobs.id"), nullable=True)
    expires_at = Column(DateTime, nullable=False, index=True)
    created_at = Column(DateTime, default=_utcnow)

    user = relationship("User", backref="ingest_documents")

    __table_args__ = (
        Index("ix_ingest_documents_user_domain", "user_id", "sender_domain"),
    )


class MobileUploadSession(Base):
    __tablename__ = "mobile_upload_sessions"

    id = Column(String, primary_key=True, default=_uuid)
    user_id = Column(String, ForeignKey("users.id"), nullable=False)
    token = Column(String, unique=True, nullable=False, index=True)
    group_sender_email = Column(String, nullable=True)
    group_sender_domain = Column(String, nullable=True)
    expires_at = Column(DateTime, nullable=False)
    created_at = Column(DateTime, default=_utcnow)

    user = relationship("User", backref="mobile_upload_sessions")
