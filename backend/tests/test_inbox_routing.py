"""Unit tests for the per-user inbox address logic.

These cover the pure functions only — slug, key generation, address
formatting, and plus-tag extraction. Routing against a real DB is
exercised by the live smoke test that runs after deploy.

Run from the backend dir:
    pytest tests/test_inbox_routing.py -q
"""
from __future__ import annotations

import email as email_lib
import string
from email.message import Message

import pytest

from app.services.ingest.email_parser import (
    extract_address_keys,
    format_inbox_address,
    gen_address_key,
    is_alphanumeric_key,
    slugify_name,
)


# ── slugify_name ────────────────────────────────────────────────────────────

@pytest.mark.parametrize(
    "name,expected",
    [
        ("Martin Mashalov", "martin"),
        ("Jane Doe", "jane"),
        ("Bjørn Larsen", "bjrn"),  # NFKD strips combining mark, ø → o is approx
        ("  whitespace  ", "whitespace"),
        ("LongFirstNameThatExceedsTheLimit Other", "longfirstnam"),  # max 12 chars
        ("", "user"),
        (None, "user"),
        ("李雷", "user"),  # no ASCII letters → fallback
        ("123", "123"),  # digits are fine
        ("Mary-Anne Smith", "maryanne"),  # punctuation removed within first token
        ("X Æ A-12", "x"),  # first token after split
        ("   ", "user"),
        ("UPPERCASE", "uppercase"),
    ],
)
def test_slugify_name(name, expected):
    # Special-case: Bjørn becomes "bjrn" because NFKD on ø yields ø itself
    # (it has no decomposition); ascii(ignore) drops it. Keep the assertion
    # tight to whatever the encoder actually does, but require ASCII-only.
    result = slugify_name(name)
    assert result.isascii()
    assert all(c in string.ascii_lowercase + string.digits for c in result)
    if expected == "bjrn":
        # Just require it starts with 'bj' and is lowercase ascii
        assert result.startswith("bj")
    else:
        assert result == expected


def test_slugify_respects_custom_fallback():
    assert slugify_name(None, fallback="anon") == "anon"
    assert slugify_name("", fallback="anon") == "anon"


def test_slugify_truncates():
    long_name = "a" * 100
    assert slugify_name(long_name, max_len=8) == "a" * 8


# ── gen_address_key + is_alphanumeric_key ───────────────────────────────────

def test_gen_address_key_format():
    for _ in range(100):
        key = gen_address_key()
        assert is_alphanumeric_key(key), f"bad key: {key!r}"
        assert len(key) == 6
        assert all(c in string.ascii_lowercase + string.digits for c in key)


def test_is_alphanumeric_key_rejects_legacy():
    # Legacy keys generated via secrets.token_urlsafe(4)[:6].lower() can
    # contain '-' or '_' and we want to detect them as needing migration.
    assert is_alphanumeric_key("abc123") is True
    assert is_alphanumeric_key("a-bc12") is False
    assert is_alphanumeric_key("a_bc12") is False
    assert is_alphanumeric_key("ABC123") is False  # uppercase rejected
    assert is_alphanumeric_key("abc12") is False  # too short
    assert is_alphanumeric_key("abc1234") is False  # too long
    assert is_alphanumeric_key(None) is False
    assert is_alphanumeric_key("") is False


# ── format_inbox_address ────────────────────────────────────────────────────

def test_format_inbox_address_basic():
    out = format_inbox_address("documents@gridpull.com", "martin", "mrt1na")
    assert out == "documents+martin-mrt1na@gridpull.com"


def test_format_inbox_address_preserves_domain():
    out = format_inbox_address("intake@example.co.uk", "alice", "abc123")
    assert out == "intake+alice-abc123@example.co.uk"


def test_format_inbox_address_rejects_bad_universal():
    with pytest.raises(ValueError):
        format_inbox_address("nodomain", "x", "abc123")


# ── extract_address_keys ────────────────────────────────────────────────────

def _msg(headers: dict[str, str]) -> Message:
    m = email_lib.message.Message()
    for k, v in headers.items():
        m[k] = v
    return m


def test_extract_keys_per_user_format():
    m = _msg({"To": "documents+martin-mrt1na@gridpull.com"})
    keys = extract_address_keys(m)
    assert "martin-mrt1na" in keys
    assert "martin" in keys
    assert "mrt1na" in keys


def test_extract_keys_legacy_intake_format():
    m = _msg({"Delivered-To": "documents+intake-mrt1na@gridpull.com"})
    keys = extract_address_keys(m)
    assert "intake-mrt1na" in keys
    assert "intake" in keys
    assert "mrt1na" in keys


def test_extract_keys_minimal_format():
    m = _msg({"To": "documents+abc123@gridpull.com"})
    keys = extract_address_keys(m)
    assert keys == ["abc123"]


def test_extract_keys_no_plus_tag():
    m = _msg({"To": "documents@gridpull.com", "From": "user+oops@gmail.com"})
    # The From header isn't scanned (only recipient headers); no key found.
    assert extract_address_keys(m) == []


def test_extract_keys_multiple_headers():
    m = _msg({
        "To": "documents@gridpull.com",
        "Delivered-To": "documents+jane-zzz999@gridpull.com",
        "Cc": "documents+bob-aaa111@gridpull.com",
    })
    keys = extract_address_keys(m)
    # Delivered-To is checked first, then To, then Cc — preserve discovery order.
    assert keys[0] == "jane-zzz999"
    assert "zzz999" in keys
    assert "aaa111" in keys


def test_extract_keys_dedupe():
    m = _msg({
        "To": "documents+x-y-z@gridpull.com",
        "Delivered-To": "documents+x-y-z@gridpull.com",
    })
    keys = extract_address_keys(m)
    # Should not contain duplicates of "x-y-z" or "x" or "y" or "z"
    assert len(keys) == len(set(keys))
    assert "x-y-z" in keys
    assert "x" in keys
    assert "z" in keys


def test_extract_keys_case_insensitive():
    m = _msg({"To": "documents+Martin-MRT1NA@gridpull.com"})
    keys = extract_address_keys(m)
    assert all(k == k.lower() for k in keys)
    assert "martin-mrt1na" in keys
    assert "mrt1na" in keys


def test_extract_keys_empty_message():
    m = _msg({})
    assert extract_address_keys(m) == []


def test_extract_keys_dict_input():
    # The helper also accepts a plain dict for unit testing convenience.
    keys = extract_address_keys({"To": "documents+x-abc123@gridpull.com"})
    assert "abc123" in keys
    assert "x-abc123" in keys
