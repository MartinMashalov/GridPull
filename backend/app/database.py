from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy.pool import NullPool
from app.config import settings

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
        await conn.run_sync(Base.metadata.create_all)
    await ddl_engine.dispose()
