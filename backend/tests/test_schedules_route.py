"""Unit tests for the /api/schedules route helpers.

Covers _normalize_schedule_type, _classify, and _read_and_pack — the
deterministic input-handling layer that runs *before* any Papyra round-
trip. No network, no DB, no real auth.
"""
from __future__ import annotations

import asyncio
import io
import os
import sys
from unittest.mock import AsyncMock, MagicMock

# Stub envs needed for app.config import
os.environ.setdefault("OPENAI_API_KEY", "test")
os.environ.setdefault("ANTHROPIC_API_KEY", "test")
os.environ.setdefault("MISTRAL_API_KEY", "test")
os.environ.setdefault("JWT_SECRET", "test")
os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///:memory:")

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest  # noqa: E402
from fastapi import HTTPException  # noqa: E402

from app.routes.schedules import (  # noqa: E402
    SCHEDULE_TYPES,
    _classify,
    _normalize_schedule_type,
    _read_and_pack,
)


# ─── _normalize_schedule_type ──────────────────────────────────────────────

class TestNormalizeScheduleType:
    def test_known_slug_lower(self):
        assert _normalize_schedule_type("property") == "property"
        assert _normalize_schedule_type("VEHICLES") == "vehicles"
        assert _normalize_schedule_type(" workers_comp ") == "workers_comp"

    def test_default_when_none(self):
        assert _normalize_schedule_type(None) == "property"
        assert _normalize_schedule_type("") == "property"

    def test_default_override(self):
        assert _normalize_schedule_type(None, default="vehicles") == "vehicles"

    def test_unknown_slug_raises(self):
        with pytest.raises(HTTPException) as exc:
            _normalize_schedule_type("not_a_real_type")
        assert exc.value.status_code == 400
        assert "not_a_real_type" in exc.value.detail

    def test_all_advertised_slugs_valid(self):
        # Every slug in the canonical SCHEDULE_TYPES list MUST normalize cleanly.
        # If you add a slug, this catches the case where it's missing from
        # _VALID_SCHEDULE_TYPES.
        for s in SCHEDULE_TYPES:
            assert _normalize_schedule_type(s["value"]) == s["value"]


# ─── _classify ──────────────────────────────────────────────────────────────

def _mock_upload(filename: str) -> MagicMock:
    m = MagicMock()
    m.filename = filename
    return m


class TestClassify:
    def test_separates_spreadsheets_from_docs(self):
        files = [
            _mock_upload("baseline.xlsx"),
            _mock_upload("source.pdf"),
            _mock_upload("scan.png"),
            _mock_upload("intake.csv"),
        ]
        ss, docs = _classify(files)
        assert {f.filename for f in ss} == {"baseline.xlsx", "intake.csv"}
        assert {f.filename for f in docs} == {"source.pdf", "scan.png"}

    def test_xls_legacy_treated_as_spreadsheet(self):
        ss, docs = _classify([_mock_upload("legacy.xls")])
        assert len(ss) == 1
        assert len(docs) == 0

    def test_unsupported_extension_raises(self):
        with pytest.raises(HTTPException) as exc:
            _classify([_mock_upload("evil.exe")])
        assert exc.value.status_code == 400
        assert "evil.exe" in exc.value.detail

    def test_no_extension_raises(self):
        with pytest.raises(HTTPException) as exc:
            _classify([_mock_upload("noext")])
        assert exc.value.status_code == 400

    def test_email_and_html_supported(self):
        _, docs = _classify([
            _mock_upload("thread.eml"),
            _mock_upload("page.html"),
            _mock_upload("data.json"),
        ])
        assert len(docs) == 3


# ─── _read_and_pack ─────────────────────────────────────────────────────────

class TestReadAndPack:
    def test_charges_one_page_per_non_pdf(self):
        f1 = MagicMock()
        f1.filename = "scan.png"
        f1.content_type = "image/png"
        f1.read = AsyncMock(return_value=b"\x89PNG\r\n\x1a\n" + b"x" * 100)
        f2 = MagicMock()
        f2.filename = "intake.csv"
        f2.content_type = "text/csv"
        f2.read = AsyncMock(return_value=b"a,b,c\n1,2,3\n")

        out, pages = asyncio.run(_read_and_pack([f1, f2]))
        assert pages == 2
        assert len(out) == 2

    def test_skips_empty_files(self):
        f1 = MagicMock()
        f1.filename = "empty.csv"
        f1.content_type = "text/csv"
        f1.read = AsyncMock(return_value=b"")

        out, pages = asyncio.run(_read_and_pack([f1]))
        assert pages == 0
        assert out == []

    def test_oversized_file_raises_413(self):
        from app.services.subscription_tiers import MAX_FILE_SIZE_MB
        big = MagicMock()
        big.filename = "huge.csv"
        big.content_type = "text/csv"
        big.read = AsyncMock(return_value=b"x" * (MAX_FILE_SIZE_MB * 1024 * 1024 + 1))

        with pytest.raises(HTTPException) as exc:
            asyncio.run(_read_and_pack([big]))
        assert exc.value.status_code == 413

    def test_corrupt_pdf_raises_422(self):
        bad = MagicMock()
        bad.filename = "broken.pdf"
        bad.content_type = "application/pdf"
        bad.read = AsyncMock(return_value=b"NOT A PDF AT ALL")

        with pytest.raises(HTTPException) as exc:
            asyncio.run(_read_and_pack([bad]))
        assert exc.value.status_code == 422


# ─── SCHEDULE_TYPES sanity ──────────────────────────────────────────────────

class TestScheduleTypes:
    def test_canonical_list_has_expected_slugs(self):
        slugs = {t["value"] for t in SCHEDULE_TYPES}
        # These are the slugs the frontend depends on
        for required in ("property", "vehicles", "drivers", "workers_comp",
                         "equipment", "aircraft", "events", "cargo",
                         "hazards", "custom"):
            assert required in slugs

    def test_every_entry_has_value_and_label(self):
        for t in SCHEDULE_TYPES:
            assert t["value"]
            assert t["label"]
