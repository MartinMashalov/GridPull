from sqlalchemy import Column, String, Float, DateTime, ForeignKey, Text, JSON, Integer, Index
from sqlalchemy.orm import relationship
from datetime import datetime
import uuid
from app.database import Base


class OAuthConnection(Base):
    __tablename__ = "oauth_connections"
    __table_args__ = (
        Index("ix_oauth_connections_user_provider", "user_id", "provider"),
    )

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String, ForeignKey("users.id"), nullable=False)
    provider = Column(String, nullable=False)  # "google_drive" | "sharepoint" | "dropbox" | "box"
    access_token = Column(Text, nullable=False)
    refresh_token = Column(Text, nullable=True)
    token_expires_at = Column(DateTime, nullable=True)
    account_email = Column(String, nullable=True)
    account_name = Column(String, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class Pipeline(Base):
    __tablename__ = "pipelines"
    __table_args__ = (
        Index("ix_pipelines_user_id", "user_id"),
        Index("ix_pipelines_status", "status"),
    )

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String, ForeignKey("users.id"), nullable=False)
    name = Column(String, nullable=False)
    status = Column(String, default="active")  # active | paused | error

    source_type = Column(String, nullable=False)  # "google_drive" | "sharepoint" | "dropbox" | "box" | "outlook"
    source_folder_id = Column(String, nullable=False)   # folder ID, or "inbox" for Outlook
    source_folder_name = Column(String, nullable=False)  # display name
    # Extra source configuration (e.g. Outlook email filters)
    # outlook: {"from_filter": "...", "subject_filter": "...", "mark_as_read": true}
    source_config = Column(JSON, nullable=True, default=dict)

    dest_folder_id = Column(String, nullable=False)
    dest_folder_name = Column(String, nullable=False)
    dest_format = Column(String, default="xlsx")  # xlsx | csv

    fields = Column(JSON, nullable=False, default=list)   # [{name, description}]
    processed_file_ids = Column(JSON, nullable=False, default=list)  # dedup guard

    last_checked_at = Column(DateTime, nullable=True)
    last_run_at = Column(DateTime, nullable=True)
    files_processed = Column(Integer, default=0)

    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    runs = relationship(
        "PipelineRun",
        back_populates="pipeline",
        order_by="PipelineRun.started_at.desc()",
        lazy="select",
    )


class PipelineRun(Base):
    __tablename__ = "pipeline_runs"
    __table_args__ = (
        Index("ix_pipeline_runs_pipeline_id", "pipeline_id"),
        Index("ix_pipeline_runs_user_id", "user_id"),
    )

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    pipeline_id = Column(String, ForeignKey("pipelines.id"), nullable=False)
    user_id = Column(String, ForeignKey("users.id"), nullable=False)
    status = Column(String, default="running")  # running | completed | failed

    source_file_name = Column(String, nullable=True)
    source_file_id = Column(String, nullable=True)
    dest_file_name = Column(String, nullable=True)
    dest_file_url = Column(String, nullable=True)

    records_extracted = Column(Integer, default=0)
    cost_usd = Column(Float, default=0.0)
    error_message = Column(Text, nullable=True)
    log_lines = Column(JSON, nullable=True, default=list)  # [{ts, msg}, ...]

    started_at = Column(DateTime, default=datetime.utcnow)
    completed_at = Column(DateTime, nullable=True)

    pipeline = relationship("Pipeline", back_populates="runs")
