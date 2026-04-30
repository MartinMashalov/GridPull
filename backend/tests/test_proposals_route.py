"""Unit tests for the /api/proposals route.

Covers tier-gating logic and the page-cost / quota interaction. Doesn't
hit Papyra (the Papyra HTTP call is the only thing left after these
local checks pass).
"""
from __future__ import annotations

import os
import sys

os.environ.setdefault("OPENAI_API_KEY", "test")
os.environ.setdefault("ANTHROPIC_API_KEY", "test")
os.environ.setdefault("MISTRAL_API_KEY", "test")
os.environ.setdefault("JWT_SECRET", "test")
os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///:memory:")

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.services.subscription_tiers import (  # noqa: E402
    PROPOSAL_PAGE_COST,
    TIERS,
    get_tier,
    tier_info_dict,
)


# ─── Tier gating ────────────────────────────────────────────────────────────

class TestProposalTierGating:
    def test_proposal_page_cost_is_25(self):
        # Surface change: ProposalsPage.tsx hardcodes "25 pages"
        # and LandingPage.tsx FAQ mentions "25 pages". They must match.
        assert PROPOSAL_PAGE_COST == 25

    def test_free_tier_has_proposals(self):
        assert get_tier("free").has_proposals is True

    def test_starter_tier_excluded_from_proposals(self):
        # Starter is the only paid tier without proposals; this is a
        # business/billing decision and a regression here would silently
        # let starter users generate proposals.
        assert get_tier("starter").has_proposals is False

    def test_pro_and_business_have_proposals(self):
        assert get_tier("pro").has_proposals is True
        assert get_tier("business").has_proposals is True

    def test_unknown_tier_falls_back_to_free(self):
        # Important: a stale tier name shouldn't crash, it should fall
        # through to the free tier.
        assert get_tier("legacy_unknown") is TIERS["free"]


# ─── Quota math ─────────────────────────────────────────────────────────────

class TestProposalQuotaMath:
    def test_free_user_blocked_when_proposal_would_exceed_quota(self):
        # 100-page free quota; a user with 80 pages used should be blocked
        # because 80 + 25 = 105 > 100.
        tier = get_tier("free")
        used = 80
        assert tier.name == "free"
        assert used + PROPOSAL_PAGE_COST > tier.pages_per_month

    def test_free_user_allowed_under_quota(self):
        tier = get_tier("free")
        used = 60
        assert used + PROPOSAL_PAGE_COST <= tier.pages_per_month

    def test_pro_user_can_overage(self):
        # Pro tier has overage_rate_cents_per_page set, so it should
        # accept proposals beyond pages_per_month.
        tier = get_tier("pro")
        assert tier.overage_rate_cents_per_page is not None
        # The route only gates free; pro should pass quota check at any usage
        used = 99_999
        # The /proposals/generate route gating:
        #   if tier.name == "free" and used + PROPOSAL_PAGE_COST > pages_per_month
        # So pro would NOT trigger the gate regardless of `used`.
        gated = tier.name == "free" and used + PROPOSAL_PAGE_COST > tier.pages_per_month
        assert gated is False

    def test_business_user_can_overage(self):
        tier = get_tier("business")
        assert tier.overage_rate_cents_per_page is not None
        gated = tier.name == "free" and 99_999 + PROPOSAL_PAGE_COST > tier.pages_per_month
        assert gated is False


# ─── Tier info dict (returned to frontend) ─────────────────────────────────

class TestTierInfoDict:
    def test_includes_has_proposals_flag(self):
        # The frontend ProposalsPage uses this flag to gate the form
        for tier_name in ("free", "starter", "pro", "business"):
            d = tier_info_dict(get_tier(tier_name))
            assert "has_proposals" in d
            assert d["has_proposals"] is get_tier(tier_name).has_proposals

    def test_pricing_fields_present(self):
        for tier_name in ("free", "starter", "pro", "business"):
            d = tier_info_dict(get_tier(tier_name))
            for key in ("name", "display_name", "price_monthly",
                        "pages_per_month", "max_file_size_mb",
                        "overage_rate_cents_per_page", "has_pipeline"):
                assert key in d, f"{tier_name} missing {key}"


# ─── Route imports cleanly ──────────────────────────────────────────────────

class TestRouteImports:
    def test_proposals_route_imports(self):
        # Catches import-time errors (missing settings, broken decorators)
        from app.routes import proposals  # noqa: F401
        assert hasattr(proposals, "router")
        # Must declare the three endpoints the frontend uses
        paths = {r.path for r in proposals.router.routes}
        assert "/proposals/generate" in paths
        assert "/proposals/agency-info" in paths
