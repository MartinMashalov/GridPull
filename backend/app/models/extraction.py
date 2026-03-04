from sqlalchemy import Column, String, Integer, Float, JSON, DateTime, ForeignKey, Text, Index
from sqlalchemy.orm import relationship
from datetime import datetime
import uuid
from app.database import Base


class ExtractionJob(Base):
    __tablename__ = "extraction_jobs"
    __table_args__ = (
        # Most critical: every document route filters by (id, user_id) or (user_id, ...)
        Index("ix_extraction_jobs_user_id", "user_id"),
        Index("ix_extraction_jobs_status", "status"),
        # Composite for listing a user's jobs ordered by time
        Index("ix_extraction_jobs_user_created", "user_id", "created_at"),
        # Composite for filtering active jobs per user
        Index("ix_extraction_jobs_user_status", "user_id", "status"),
    )

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String, ForeignKey("users.id"), nullable=False)
    status = Column(String, default="queued")  # queued, processing, extracting, generating, complete, error
    progress = Column(Integer, default=0)
    fields = Column(JSON, nullable=False)  # List of extraction fields
    format = Column(String, default="xlsx")  # xlsx or csv
    file_count = Column(Integer, default=0)
    completed_docs = Column(Integer, default=0)  # Docs finished (for polling progress)
    cost = Column(Float, default=0.0)  # Dollar cost (with markup) deducted from user balance
    error = Column(Text, nullable=True)
    output_path = Column(String, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    user = relationship("User", back_populates="jobs")
    documents = relationship("Document", back_populates="job")


class Document(Base):
    __tablename__ = "documents"
    __table_args__ = (
        # Critical: every result/SSE query fetches documents by job_id
        Index("ix_documents_job_id", "job_id"),
        # For filtering incomplete docs during processing
        Index("ix_documents_job_status", "job_id", "status"),
    )

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    job_id = Column(String, ForeignKey("extraction_jobs.id"), nullable=False)
    filename = Column(String, nullable=False)
    file_path = Column(String, nullable=False)
    page_count = Column(Integer, default=0)
    extracted_data = Column(JSON, nullable=True)
    status = Column(String, default="pending")
    created_at = Column(DateTime, default=datetime.utcnow)

    job = relationship("ExtractionJob", back_populates="documents")
