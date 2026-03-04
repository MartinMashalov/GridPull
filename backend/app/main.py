import logging
import time
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import JSONResponse

from app.config import settings
from app.database import init_db
from app.logging_config import setup_logging
from app.routes import auth, documents, payments, users
from app.routes import pipelines
from app.workers.pipeline_poller import start_pipeline_poller
from app.workers.pool import worker_pool

# Initialise logging before anything else so all module-level loggers are ready
setup_logging()
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # ── Startup ──────────────────────────────────────────────────────
    logger.info("=" * 60)
    logger.info("GridPull API starting up")
    logger.info("=" * 60)

    logger.info("Initialising database…")
    await init_db()
    logger.info("Database ready")

    logger.info("Starting worker pool (%d workers)…", worker_pool.NUM_WORKERS)
    await worker_pool.start()
    logger.info("Worker pool started")

    logger.info("Starting pipeline poller…")
    import asyncio
    asyncio.create_task(start_pipeline_poller())
    logger.info("Pipeline poller scheduled")

    logger.info("GridPull API is ready to serve requests")

    yield

    # ── Shutdown ─────────────────────────────────────────────────────
    logger.info("GridPull API shutting down…")
    await worker_pool.stop()
    logger.info("Worker pool stopped — goodbye")


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
        "https://pdfexcel.ai",
        "https://www.pdfexcel.ai",
        "http://localhost:3000",
        "http://localhost:3001",
        "http://localhost:5173",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def log_requests(request: Request, call_next):
    """Log every HTTP request with method, path, status, duration, and client IP."""
    start = time.monotonic()
    try:
        response = await call_next(request)
    except Exception as exc:
        duration_ms = (time.monotonic() - start) * 1000
        client = request.client.host if request.client else "-"
        logger.error(
            "UNHANDLED %s %s — %.1fms — %s — %s",
            request.method, request.url.path, duration_ms, client, exc,
        )
        raise

    duration_ms = (time.monotonic() - start) * 1000
    client = request.client.host if request.client else "-"
    status = response.status_code

    # Log level based on status: errors are WARNING/ERROR, normal is INFO
    if status >= 500:
        log = logger.error
    elif status >= 400:
        log = logger.warning
    else:
        log = logger.info

    log(
        "%s %s %d %.1fms %s",
        request.method, request.url.path, status, duration_ms, client,
    )
    return response


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    """Log full 422 validation errors so they appear in app.log."""
    logger.error(
        "422 Validation error — %s %s — errors: %s",
        request.method, request.url.path, exc.errors(),
    )
    return JSONResponse(
        status_code=422,
        content={"detail": exc.errors()},
    )


# Routers
app.include_router(auth.router, prefix="/api")
app.include_router(documents.router, prefix="/api")
app.include_router(payments.router, prefix="/api")
app.include_router(users.router, prefix="/api")
app.include_router(pipelines.router, prefix="/api")


@app.get("/api/health")
async def health():
    queue_size = worker_pool._job_queue.qsize() if worker_pool._job_queue else 0
    logger.debug("Health check — queue depth: %d", queue_size)
    return {
        "status": "ok",
        "service": "GridPull API",
        "workers": worker_pool.NUM_WORKERS,
        "queued_jobs": queue_size,
    }
