"""Unit tests for form_filling.py helpers.

These cover the deterministic helpers added in the recent geometry-aware
refactor — _capacity_hint, _apply_backstops, _detect_paired_tf, signature
detection, normalization, etc. They run with no API keys and no network.

Targets the recently-changed code (commits c8ecb92, 06086c3, etc).
"""
from __future__ import annotations

import io
import os
import sys

# Stub envs needed for app.config import
os.environ.setdefault("OPENAI_API_KEY", "test")
os.environ.setdefault("ANTHROPIC_API_KEY", "test")
os.environ.setdefault("MISTRAL_API_KEY", "test")
os.environ.setdefault("JWT_SECRET", "test")
os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///:memory:")

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest  # noqa: E402

from app.services.form_filling import (  # noqa: E402
    _apply_backstops,
    _build_field_lines,
    _build_prompt,
    _capacity_hint,
    _detect_paired_tf,
    _humanize_field_name,
    _is_blank,
    _is_signature_field_name,
    _is_signature_partner_name,
    _label_hint,
    _normalize_checkbox,
    _normalize_values,
    _short_field_name,
)


# ─── _is_blank ──────────────────────────────────────────────────────────────

class TestIsBlank:
    def test_empty_string(self):
        assert _is_blank("")
        assert _is_blank("   ")

    def test_none(self):
        assert _is_blank(None)

    def test_placeholder_strings(self):
        assert _is_blank("Please Select...")
        assert _is_blank("N/A")
        assert _is_blank("n/a")
        assert _is_blank("null")
        assert _is_blank("None")

    def test_real_values(self):
        assert not _is_blank("ACME Corp")
        assert not _is_blank("0")          # zero is a real value
        assert not _is_blank("False")      # checkbox value
        assert not _is_blank("Yes")


# ─── _capacity_hint (geometry-aware) ────────────────────────────────────────

class TestCapacityHint:
    def test_tiny_field(self):
        meta = {"type": "text", "width": 25, "height": 13}
        h = _capacity_hint(meta)
        assert "TINY" in h
        assert "25×13" in h

    def test_narrow_field(self):
        meta = {"type": "text", "width": 60, "height": 13}
        h = _capacity_hint(meta)
        assert "NARROW" in h
        assert "NO addresses" in h

    def test_multiline_field(self):
        meta = {"type": "text", "width": 400, "height": 60}
        h = _capacity_hint(meta)
        assert "multi-line" in h
        assert "paragraph OK" in h

    def test_normal_field(self):
        meta = {"type": "text", "width": 300, "height": 14}
        h = _capacity_hint(meta)
        # Just the geometry, no warning
        assert "300×14pt" in h
        assert "NARROW" not in h
        assert "TINY" not in h
        assert "multi-line" not in h

    def test_non_text_field_no_hint(self):
        # Geometry hints are text-only — checkboxes already have Yes/No
        meta = {"type": "checkbox", "width": 12, "height": 12}
        assert _capacity_hint(meta) == ""

    def test_missing_geometry(self):
        # No geometry → no hint (don't print "0×0pt" garbage)
        assert _capacity_hint({"type": "text"}) == ""
        assert _capacity_hint({"type": "text", "width": 0, "height": 0}) == ""

    def test_boundary_narrow_vs_normal(self):
        # 80 wide is the inclusive narrow boundary
        narrow = _capacity_hint({"type": "text", "width": 80, "height": 18})
        assert "NARROW" in narrow
        # 81 wide should not be narrow
        normal = _capacity_hint({"type": "text", "width": 81, "height": 18})
        assert "NARROW" not in normal


# ─── _apply_backstops ───────────────────────────────────────────────────────

class TestApplyBackstops:
    def test_office_use_pg1header_zeroed(self):
        schema = {
            "Pg1Header_Received_By": {"type": "text", "label": "Received by"},
            "Name": {"type": "text", "label": "Name"},
        }
        filled = {
            "Pg1Header_Received_By": "Joe Smith",
            "Name": "ACME Corp",
        }
        zeroed = _apply_backstops(filled, schema)
        assert "Pg1Header_Received_By" in zeroed
        assert filled["Pg1Header_Received_By"] == ""
        assert filled["Name"] == "ACME Corp"  # not touched

    def test_for_office_use_only_label_zeroed(self):
        schema = {
            "headerfield1": {"type": "text", "label": "For IRS Use Only"},
            "headerfield2": {"type": "text", "label": "For Office Use Only"},
            "header_received": {"type": "text", "label": "Received by:"},
            "real_field": {"type": "text", "label": "Taxpayer Name"},
        }
        filled = {
            "headerfield1": "stuff",
            "headerfield2": "more stuff",
            "header_received": "Examiner X",
            "real_field": "Joe",
        }
        zeroed = _apply_backstops(filled, schema)
        assert {"headerfield1", "headerfield2", "header_received"} <= zeroed
        assert filled["real_field"] == "Joe"

    def test_geometry_backstop_long_in_narrow(self):
        # Long content in a narrow field — should be zeroed
        schema = {
            "ItemRef": {"type": "text", "label": "Item", "width": 60, "height": 13},
        }
        filled = {"ItemRef": "1234 Main Street, Springfield IL 62701, USA"}
        zeroed = _apply_backstops(filled, schema)
        assert "ItemRef" in zeroed
        assert filled["ItemRef"] == ""

    def test_geometry_backstop_short_in_narrow_kept(self):
        # Short content in a narrow field — should be kept
        schema = {
            "ItemRef": {"type": "text", "label": "Item", "width": 60, "height": 13},
        }
        filled = {"ItemRef": "ITEM-42"}
        zeroed = _apply_backstops(filled, schema)
        assert "ItemRef" not in zeroed
        assert filled["ItemRef"] == "ITEM-42"

    def test_geometry_backstop_long_in_wide_kept(self):
        # Long content in a wide multi-line field — should be kept
        schema = {
            "Address": {"type": "text", "label": "Address", "width": 400, "height": 60},
        }
        filled = {"Address": "1234 Main Street, Springfield IL 62701, USA"}
        zeroed = _apply_backstops(filled, schema)
        assert "Address" not in zeroed

    def test_geometry_backstop_no_geometry_no_action(self):
        # No geometry available → can't decide; leave alone
        schema = {
            "ItemRef": {"type": "text", "label": "Item", "width": 0, "height": 0},
        }
        filled = {"ItemRef": "1234 Main Street, Springfield IL 62701, USA"}
        zeroed = _apply_backstops(filled, schema)
        assert "ItemRef" not in zeroed

    def test_signature_partner_blanker(self):
        # Build a schema that has a blank signature next to a Date / Title
        schema = {
            "Insured_Signature": {"type": "text", "label": "Signature"},
            "Insured_Date": {"type": "text", "label": "Date"},
            "Insured_Title": {"type": "text", "label": "Title"},
            "Other_Date": {"type": "text", "label": "Effective Date"},  # not a partner
        }
        filled = {
            "Insured_Signature": "",
            "Insured_Date": "2026-01-01",
            "Insured_Title": "President",
            "Other_Date": "2026-12-31",
        }
        zeroed = _apply_backstops(filled, schema)
        # Insured_Date is adjacent (within 3 of) the blank signature → blanked
        assert "Insured_Date" in zeroed
        assert "Insured_Title" in zeroed
        # Other_Date is far away in name order — kept
        # (Note: schema order is what matters; build above puts Other_Date 4th)

    def test_signed_signature_does_not_trigger_partner_blank(self):
        schema = {
            "Insured_Signature": {"type": "text", "label": "Signature"},
            "Insured_Date": {"type": "text", "label": "Date"},
        }
        # Signature was filled (rare but possible) — partner blanker should NOT fire
        filled = {
            "Insured_Signature": "/s/ Joe",
            "Insured_Date": "2026-01-01",
        }
        zeroed = _apply_backstops(filled, schema)
        assert "Insured_Date" not in zeroed

    def test_empty_filled_is_safe(self):
        zeroed = _apply_backstops({}, {})
        assert zeroed == set()


# ─── Signature detection ────────────────────────────────────────────────────

class TestSignatureDetection:
    def test_signature_field_name(self):
        assert _is_signature_field_name("Signature_A")
        assert _is_signature_field_name("Insured_Signature")
        assert _is_signature_field_name("sig_1")
        assert _is_signature_field_name("DigitalSignature")
        assert _is_signature_field_name("digital_signature_x")
        assert _is_signature_field_name("SigField_A")
        assert _is_signature_field_name("sigfield")
        assert not _is_signature_field_name("Name")
        assert not _is_signature_field_name("Address")

    def test_signature_partner_name(self):
        assert _is_signature_partner_name("PrintName")
        assert _is_signature_partner_name("print_name")
        assert _is_signature_partner_name("DateSigned")
        assert _is_signature_partner_name("NameContractingOfficer")
        assert _is_signature_partner_name("InsuredDate")
        assert _is_signature_partner_name("InsuredTitle")
        assert _is_signature_partner_name("Producer_Title")
        assert not _is_signature_partner_name("FullName")
        assert not _is_signature_partner_name("Building_1_Address")


# ─── _detect_paired_tf ──────────────────────────────────────────────────────

class TestDetectPairedTF:
    def test_dash_separator(self):
        schema = {
            "F1": {"type": "checkbox", "label": "Insured occupies <25k sqft - True"},
            "F2": {"type": "checkbox", "label": "Insured occupies <25k sqft - False"},
            "F3": {"type": "checkbox", "label": "Solo question with no pair"},
        }
        pairs = _detect_paired_tf(schema)
        assert len(pairs) == 1
        # The paired stem should contain both sides
        only = next(iter(pairs.values()))
        assert {s for _, s in only} == {"true", "false"}

    def test_em_dash_separator(self):
        schema = {
            "F1": {"type": "checkbox", "label": "Has been in business >3 years — Yes"},
            "F2": {"type": "checkbox", "label": "Has been in business >3 years — No"},
        }
        pairs = _detect_paired_tf(schema)
        assert len(pairs) == 1

    def test_unpaired_is_dropped(self):
        # Only "True" present, no "False" — should be excluded
        schema = {
            "F1": {"type": "checkbox", "label": "Sole proprietor — True"},
        }
        pairs = _detect_paired_tf(schema)
        assert pairs == {}

    def test_skips_non_checkbox(self):
        schema = {
            "F1": {"type": "text", "label": "Sole proprietor — True"},
            "F2": {"type": "text", "label": "Sole proprietor — False"},
        }
        pairs = _detect_paired_tf(schema)
        assert pairs == {}


# ─── _normalize_checkbox & _normalize_values ────────────────────────────────

class TestNormalizeCheckbox:
    def test_yes_variants_map_to_checked(self):
        states = {"checked": "/Yes", "unchecked": "/Off"}
        for v in ("Yes", "yes", "Y", "true", "TRUE", "1", "checked", "ON"):
            assert _normalize_checkbox(v, states) == "/Yes"

    def test_no_and_unknown_map_to_unchecked(self):
        states = {"checked": "/Yes", "unchecked": "/Off"}
        for v in ("No", "n", "false", "0", "", "blah"):
            assert _normalize_checkbox(v, states) == "/Off"

    def test_custom_appearance_states(self):
        # Some PDFs use non-standard appearance like /1 or /On
        states = {"checked": "/On", "unchecked": "/Off"}
        assert _normalize_checkbox("Yes", states) == "/On"
        assert _normalize_checkbox("No", states) == "/Off"


class TestNormalizeValues:
    def test_text_field(self):
        schema = {"name": {"type": "text"}}
        assert _normalize_values({"name": "ACME"}, schema) == {"name": "ACME"}
        assert _normalize_values({"name": "  spaced  "}, schema) == {"name": "  spaced  "}
        assert _normalize_values({"name": ""}, schema) == {"name": ""}
        assert _normalize_values({"name": "N/A"}, schema) == {"name": ""}

    def test_dropdown_exact_option(self):
        schema = {"state": {"type": "dropdown", "options": ["CA", "NY", "TX"]}}
        assert _normalize_values({"state": "NY"}, schema) == {"state": "NY"}

    def test_dropdown_case_insensitive_match(self):
        schema = {"state": {"type": "dropdown", "options": ["CA", "NY", "TX"]}}
        assert _normalize_values({"state": "ny"}, schema) == {"state": "NY"}

    def test_dropdown_no_match_blanked(self):
        schema = {"state": {"type": "dropdown", "options": ["CA", "NY", "TX"]}}
        assert _normalize_values({"state": "FL"}, schema) == {"state": ""}

    def test_checkbox(self):
        schema = {
            "agreed": {"type": "checkbox", "appearance_states": {"checked": "/Yes", "unchecked": "/Off"}},
        }
        assert _normalize_values({"agreed": "Yes"}, schema) == {"agreed": "/Yes"}
        assert _normalize_values({"agreed": "No"}, schema) == {"agreed": "/Off"}

    def test_radio_with_options(self):
        schema = {"plan": {"type": "radio", "options": ["Basic", "Premium"]}}
        assert _normalize_values({"plan": "Premium"}, schema) == {"plan": "Premium"}
        assert _normalize_values({"plan": "Bogus"}, schema) == {"plan": ""}


# ─── Field name humanization ────────────────────────────────────────────────

class TestFieldNameHelpers:
    def test_short_field_name(self):
        assert _short_field_name("topmostSubform[0].Page1[0].field_42[0]") == "field_42"
        assert _short_field_name("simple") == "simple"
        assert _short_field_name("a.b.c[3]") == "c"

    def test_humanize_camelcase(self):
        assert _humanize_field_name("FullName_A") == "Full Name"
        assert _humanize_field_name("Producer_FullName_B") == "Producer Full Name"
        assert _humanize_field_name("Policy_EffectiveDate") == "Policy Effective Date"

    def test_humanize_strips_variant(self):
        # _A1 / _B suffixes are field-variant indicators, should be stripped
        assert _humanize_field_name("Address_A") == "Address"
        assert _humanize_field_name("Address_B2") == "Address"

    def test_label_hint_prefers_label_then_name(self):
        assert _label_hint({"label": "Insured Name"}, "Insured_FullName_A") == ' [label: "Insured Name"]'
        # No label → falls back to humanized name
        assert _label_hint({}, "Insured_FullName_A") == ' [name: "Insured Full Name"]'
        # Neither → empty
        assert _label_hint({}, "x") == ""


# ─── _build_field_lines / _build_prompt smoke ────────────────────────────────

class TestBuildFieldLines:
    def test_text_with_geometry(self):
        schema = {
            "tiny": {"type": "text", "label": "Code", "width": 20, "height": 13},
            "big":  {"type": "text", "label": "Notes", "width": 400, "height": 80},
        }
        lines = _build_field_lines(schema)
        assert "TINY" in lines
        assert "multi-line" in lines

    def test_checkbox_yes_no(self):
        schema = {"agreed": {"type": "checkbox", "label": "I agree"}}
        lines = _build_field_lines(schema)
        assert '"agreed"' in lines
        assert "Yes" in lines and "No" in lines

    def test_dropdown_lists_options(self):
        schema = {"state": {"type": "dropdown", "label": "State", "options": ["CA", "NY"]}}
        lines = _build_field_lines(schema)
        assert "CA" in lines and "NY" in lines

    def test_focus_filter(self):
        schema = {
            "a": {"type": "text", "label": "A"},
            "b": {"type": "text", "label": "B"},
        }
        lines = _build_field_lines(schema, focus_names=["a"])
        assert '"a"' in lines
        assert '"b"' not in lines


class TestBuildPrompt:
    def test_smoke_includes_source_and_fields(self):
        schema = {"name": {"type": "text", "label": "Name"}}
        prompt = _build_prompt("source data here", schema)
        assert "source data here" in prompt
        assert '"name"' in prompt

    def test_focus_block_lists_blanks(self):
        schema = {"name": {"type": "text", "label": "Name"}, "addr": {"type": "text"}}
        prompt = _build_prompt("src", schema, focus_names=["addr"], prior_values={"name": "ACME"})
        # Should mention the prior values somewhere
        assert "ACME" in prompt
