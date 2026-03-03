"""
Centralised logging configuration for GridPull.

All loggers write to two destinations simultaneously:
  1. stdout       — captured by Docker / journald
  2. /app/app.log — bind-mounted to /opt/gridpull/app.log on the host

Format:  2026-01-01 12:00:00.123 [INFO ] documents: message here
"""

import logging
import logging.handlers
import os
import sys
from pathlib import Path

LOG_FILE = os.getenv("LOG_FILE", "/app/app.log")
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()

_FORMAT = "%(asctime)s.%(msecs)03d [%(levelname)-5s] %(name)s: %(message)s"
_DATE_FMT = "%Y-%m-%d %H:%M:%S"


def setup_logging() -> None:
    """Call once at process startup (in main.py lifespan)."""
    root = logging.getLogger()
    root.setLevel(getattr(logging, LOG_LEVEL, logging.INFO))

    formatter = logging.Formatter(_FORMAT, datefmt=_DATE_FMT)

    # ── stdout handler ────────────────────────────────────────────────────────
    stdout_h = logging.StreamHandler(sys.stdout)
    stdout_h.setFormatter(formatter)
    root.addHandler(stdout_h)

    # ── rotating file handler ─────────────────────────────────────────────────
    # max 50 MB per file, keep 5 backups → up to 300 MB total
    try:
        Path(LOG_FILE).parent.mkdir(parents=True, exist_ok=True)
        file_h = logging.handlers.RotatingFileHandler(
            LOG_FILE,
            maxBytes=50 * 1024 * 1024,
            backupCount=5,
            encoding="utf-8",
        )
        file_h.setFormatter(formatter)
        root.addHandler(file_h)
        root.info("Logging to file: %s", LOG_FILE)
    except Exception as exc:
        root.warning("Could not open log file %s: %s — file logging disabled", LOG_FILE, exc)

    # ── silence noisy third-party loggers ────────────────────────────────────
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)
    logging.getLogger("sqlalchemy.pool").setLevel(logging.WARNING)
