from pydantic_settings import BaseSettings
from typing import List
import os


class Settings(BaseSettings):
    # Google OAuth
    google_client_id: str = ""
    google_client_secret: str = ""

    # JWT
    jwt_secret_key: str = "gridpull-secret-key"
    jwt_algorithm: str = "HS256"

    # OpenAI
    openai_api_key: str = ""

    # Stripe
    stripe_secret_key: str = ""
    stripe_webhook_secret: str = ""
    stripe_publishable_key: str = ""

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


settings = Settings()

# Create directories
os.makedirs(settings.upload_dir, exist_ok=True)
os.makedirs(settings.output_dir, exist_ok=True)
