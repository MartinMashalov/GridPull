import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware

from app.config import settings
from app.database import init_db
from app.routes import auth, documents, payments, users
from app.workers.pool import worker_pool

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # ── Startup ──────────────────────────────────────────────────────
    logger.info("Initialising database…")
    await init_db()

    logger.info("Starting worker pool (%d workers)…", worker_pool.NUM_WORKERS)
    await worker_pool.start()

    yield

    # ── Shutdown ─────────────────────────────────────────────────────
    logger.info("Stopping worker pool…")
    await worker_pool.stop()


app = FastAPI(
    title="GridPull API",
    description="PDF → Excel extraction API powered by AI",
    version="2.0.0",
    lifespan=lifespan,
)

# GZip — compress JSON responses ≥ 1 KB (~70% size reduction)
app.add_middleware(GZipMiddleware, minimum_size=1000)

# CORS — allow SSE from browser
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        settings.frontend_url,
        "http://localhost:3000",
        "http://localhost:3001",
        "http://localhost:5173",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Routers
app.include_router(auth.router, prefix="/api")
app.include_router(documents.router, prefix="/api")
app.include_router(payments.router, prefix="/api")
app.include_router(users.router, prefix="/api")


@app.get("/api/health")
async def health():
    queue_size = worker_pool._job_queue.qsize() if worker_pool._job_queue else 0
    return {
        "status": "ok",
        "service": "GridPull API",
        "workers": worker_pool.NUM_WORKERS,
        "queued_jobs": queue_size,
    }
