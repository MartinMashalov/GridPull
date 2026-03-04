from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy.pool import NullPool
from app.config import settings

# Import must happen before create_all so all tables are registered in metadata

_is_postgres = settings.database_url.startswith("postgresql")

# ── Application engine (connects via PgBouncer on port 6432) ─────────────────
_app_kwargs: dict = {
    "echo": False,
    "pool_recycle": 1800,
    "pool_pre_ping": True,
}

if _is_postgres:
    # asyncpg + PgBouncer transaction-mode: must disable prepared statement cache.
    # pool_size=50 matches our concurrency target so requests never wait for a slot.
    _app_kwargs["pool_size"] = 15
    _app_kwargs["max_overflow"] = 15
    _app_kwargs["pool_timeout"] = 30
    _app_kwargs["connect_args"] = {
        "prepared_statement_cache_size": 0,
        "statement_cache_size": 0,
        "command_timeout": 30,
    }
else:
    _app_kwargs["connect_args"] = {"check_same_thread": False}
    _app_kwargs.pop("pool_recycle", None)
    _app_kwargs.pop("pool_pre_ping", None)

engine = create_async_engine(settings.database_url, **_app_kwargs)

AsyncSessionLocal = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


class Base(DeclarativeBase):
    pass


async def get_db():
    async with AsyncSessionLocal() as session:
        try:
            yield session
        finally:
            await session.close()


async def init_db():
    """Run DDL (CREATE TABLE IF NOT EXISTS) at startup.

    For PostgreSQL, we bypass PgBouncer and connect directly to port 5432
    using NullPool — DDL needs session-level semantics that PgBouncer
    transaction mode doesn't support (prepared statements conflict).
    """
    if _is_postgres:
        # Replace PgBouncer port (6432) with direct PostgreSQL port (5432)
        direct_url = settings.database_url.replace(":6432/", ":5432/")
        ddl_engine = create_async_engine(
            direct_url,
            poolclass=NullPool,
            connect_args={
                "prepared_statement_cache_size": 0,
                "statement_cache_size": 0,
            },
        )
    else:
        ddl_engine = create_async_engine(
            settings.database_url,
            poolclass=NullPool,
            connect_args={"check_same_thread": False},
        )

    async with ddl_engine.begin() as conn:
        # Ensure all model classes are registered before create_all
        import app.models  # noqa: F401
        await conn.run_sync(Base.metadata.create_all)
        # Add new columns to existing tables (safe to run every startup)
        for sql in [
            "ALTER TABLE users ADD COLUMN IF NOT EXISTS auto_renewal_enabled BOOLEAN NOT NULL DEFAULT FALSE",
            "ALTER TABLE users ADD COLUMN IF NOT EXISTS auto_renewal_threshold FLOAT NOT NULL DEFAULT 5.0",
            "ALTER TABLE users ADD COLUMN IF NOT EXISTS auto_renewal_refill FLOAT NOT NULL DEFAULT 20.0",
            # Migrate credits → balance (dollar float); seed from old integer credits if present
            "ALTER TABLE users ADD COLUMN IF NOT EXISTS balance FLOAT NOT NULL DEFAULT 1.0",
            "UPDATE users SET balance = credits WHERE credits IS NOT NULL AND balance = 1.0 AND credits > 0",
            # Job cost column (replaces credits_used)
            "ALTER TABLE extraction_jobs ADD COLUMN IF NOT EXISTS cost FLOAT NOT NULL DEFAULT 0.0",
            # Per-doc completion counter for polling progress
            "ALTER TABLE extraction_jobs ADD COLUMN IF NOT EXISTS completed_docs INTEGER NOT NULL DEFAULT 0",
            # Stripe payment method storage for saved cards / auto-renewal
            "ALTER TABLE users ADD COLUMN IF NOT EXISTS stripe_customer_id VARCHAR",
            "ALTER TABLE users ADD COLUMN IF NOT EXISTS stripe_payment_method_id VARCHAR",
            "ALTER TABLE users ADD COLUMN IF NOT EXISTS stripe_card_brand VARCHAR",
            "ALTER TABLE users ADD COLUMN IF NOT EXISTS stripe_card_last4 VARCHAR",
            # Pipelines feature — new tables are created by create_all above;
            # these guards handle deployments where tables already exist
            "ALTER TABLE pipelines ADD COLUMN IF NOT EXISTS processed_file_ids JSON",
            "ALTER TABLE pipelines ADD COLUMN IF NOT EXISTS files_processed INTEGER NOT NULL DEFAULT 0",
            "ALTER TABLE pipelines ADD COLUMN IF NOT EXISTS last_checked_at TIMESTAMP",
            "ALTER TABLE pipelines ADD COLUMN IF NOT EXISTS last_run_at TIMESTAMP",
            # Outlook source config (from_filter, subject_filter, mark_as_read)
            "ALTER TABLE pipelines ADD COLUMN IF NOT EXISTS source_config JSON",
            # Per-run structured log lines for real-time tracking
            "ALTER TABLE pipeline_runs ADD COLUMN IF NOT EXISTS log_lines JSON",
        ]:
            await conn.execute(__import__("sqlalchemy").text(sql))
    await ddl_engine.dispose()
