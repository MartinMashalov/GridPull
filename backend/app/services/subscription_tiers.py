"""
Subscription tier definitions — single source of truth for limits, pricing, and overage rates.

Billing is page-based: each page of an uploaded document counts as 1 page toward
the monthly limit. Form fills cost 5 pages each.
"""

from __future__ import annotations
from dataclasses import dataclass
from typing import Optional


# ── Global limits ────────────────────────────────────────────────────────────────
FORM_FILL_PAGE_COST = 5        # 1 form fill = 5 pages
MAX_FILE_SIZE_MB = 5           # hard cap per uploaded file


@dataclass(frozen=True)
class TierConfig:
    name: str
    display_name: str
    price_monthly: int                       # cents
    pages_per_month: int
    overage_rate_cents_per_page: Optional[float]  # cents per page, None = blocked
    has_pipeline: bool
    has_proposals: bool = False


TIERS: dict[str, TierConfig] = {
    "free": TierConfig(
        name="free",
        display_name="Free",
        price_monthly=0,
        pages_per_month=500,
        overage_rate_cents_per_page=None,
        has_pipeline=False,
        has_proposals=False,
    ),
    "starter": TierConfig(
        name="starter",
        display_name="Starter",
        price_monthly=4900,
        pages_per_month=7500,
        overage_rate_cents_per_page=1.2,
        has_pipeline=False,
        has_proposals=False,
    ),
    "pro": TierConfig(
        name="pro",
        display_name="Pro",
        price_monthly=19900,
        pages_per_month=25000,
        overage_rate_cents_per_page=1.0,
        has_pipeline=True,
        has_proposals=True,
    ),
    "business": TierConfig(
        name="business",
        display_name="Business",
        price_monthly=69900,
        pages_per_month=100000,
        overage_rate_cents_per_page=0.6,
        has_pipeline=True,
        has_proposals=True,
    ),
}

TIER_ORDER = ["free", "starter", "pro", "business"]


def get_tier(name: str) -> TierConfig:
    return TIERS.get(name, TIERS["free"])


def is_upgrade(current: str, target: str) -> bool:
    return TIER_ORDER.index(target) > TIER_ORDER.index(current)


def tier_info_dict(tier: TierConfig) -> dict:
    return {
        "name": tier.name,
        "display_name": tier.display_name,
        "price_monthly": tier.price_monthly,
        "pages_per_month": tier.pages_per_month,
        "max_file_size_mb": MAX_FILE_SIZE_MB,
        "overage_rate_cents_per_page": tier.overage_rate_cents_per_page,
        "has_pipeline": tier.has_pipeline,
        "has_proposals": tier.has_proposals,
    }
