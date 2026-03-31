from pydantic import Field
from pydantic_settings import BaseSettings
from typing import List
import os


class Settings(BaseSettings):
    # Google OAuth (user login)
    google_client_id: str = ""
    google_client_secret: str = ""

    # Google Drive (pipeline integration)
    google_drive_client_id: str = ""
    google_drive_client_secret: str = ""

    # Microsoft / SharePoint (pipeline integration)
    microsoft_client_id: str = ""
    microsoft_client_secret: str = ""
    microsoft_tenant_id: str = "common"  # Use "common" to allow any tenant

    # Dropbox (pipeline integration)
    dropbox_client_id: str = ""
    dropbox_client_secret: str = ""
    dropbox_app_key: str = ""
    dropbox_app_secret: str = ""

    # Box (pipeline integration)
    box_client_id: str = ""
    box_client_secret: str = ""
    box_app_key: str = ""
    box_app_secret: str = ""

    # Backend public URL (for OAuth redirect URIs)
    backend_url: str = "http://localhost:8000"

    # JWT
    jwt_secret_key: str = "gridpull-secret-key"
    jwt_algorithm: str = "HS256"

    # Server-to-server extraction (no JWT): /api/documents/extract-service + /api/documents/service/*
    # Set both in .env; leave empty to disable those routes (they 404). Caller sends the secret as
    # header X-GridPull-Service-Token or form/query service_token. Jobs bill against the given user.
    service_extraction_secret: str = Field(
        default="",
        description="e.g. output of: openssl rand -hex 32 (never commit a real value)",
    )
    service_extraction_user_id: str = Field(
        default="",
        description="Existing users.id UUID (e.g. from DB or after one OAuth login); must match a row in users",
    )

    # OpenAI
    openai_api_key: str = ""

    # Mistral (OCR for scanned PDFs)
    mistral_api_key: str = ""

    # Bear prompt compression
    bear_api_key: str = ""
    bear_model: str = "bear-1.2"
    bear_aggressiveness: float = 0.1
    bear_min_page_count: int = 10
    bear_timeout_seconds: float = 20.0

    # Per-document extraction timeout (seconds); prevents one large doc from hanging the job
    extraction_timeout_seconds: float = 1200.0

    # Chunked multi-record extraction (text + scan): larger pages per chunk => fewer LLM calls
    extraction_chunk_size: int = 12
    extraction_chunk_threshold_pages: int = 8
    # Parser table shape used to detect schedule-like grids (layout-only routing)
    extraction_wide_grid_min_rows: int = 5
    extraction_wide_grid_min_cols: int = 4

    # Stripe
    stripe_secret_key: str = ""
    stripe_webhook_secret: str = ""
    stripe_publishable_key: str = ""

    # Stripe Price IDs for subscription tiers (created in Stripe Dashboard)
    stripe_price_starter: str = ""
    stripe_price_pro: str = ""
    stripe_price_business: str = ""
    max_file_size_mb: int = 5  # hard cap per uploaded file

    # URLs
    frontend_url: str = "http://localhost:3000"

    # Database
    database_url: str = "sqlite+aiosqlite:///./gridpull.db"

    # Redis
    redis_url: str = "redis://localhost:6379"

    # Dirs
    upload_dir: str = "./uploads"
    output_dir: str = "./outputs"

    # OpenAI models to rotate through
    openai_models: List[str] = [
        "gpt-4o-mini",
        "gpt-3.5-turbo",
        "gpt-4o-mini-2024-07-18",
    ]

    class Config:
        env_file = ".env"
        case_sensitive = False
        extra = "ignore"


settings = Settings()

# Create directories
os.makedirs(settings.upload_dir, exist_ok=True)
os.makedirs(settings.output_dir, exist_ok=True)
