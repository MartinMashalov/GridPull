"""
Subscription tier definitions — single source of truth for limits, pricing, and overage rates.
"""

from __future__ import annotations
from dataclasses import dataclass
from typing import Optional


# ── Global limits ────────────────────────────────────────────────────────────────
MAX_PAGES_PER_CREDIT = 50      # 1 credit = up to 50 pages
MAX_FILE_SIZE_MB = 5           # hard cap per uploaded file


@dataclass(frozen=True)
class TierConfig:
    name: str
    display_name: str
    price_monthly: int           # cents
    credits_per_month: int
    overage_rate: Optional[int]  # cents per credit, None = blocked
    has_pipeline: bool


TIERS: dict[str, TierConfig] = {
    "free": TierConfig(
        name="free",
        display_name="Free",
        price_monthly=0,
        credits_per_month=10,
        overage_rate=None,
        has_pipeline=False,
    ),
    "starter": TierConfig(
        name="starter",
        display_name="Starter",
        price_monthly=4900,
        credits_per_month=150,
        overage_rate=60,
        has_pipeline=False,
    ),
    "pro": TierConfig(
        name="pro",
        display_name="Pro",
        price_monthly=19900,
        credits_per_month=500,
        overage_rate=50,
        has_pipeline=True,
    ),
    "business": TierConfig(
        name="business",
        display_name="Business",
        price_monthly=54900,
        credits_per_month=1500,
        overage_rate=40,
        has_pipeline=True,
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
        "credits_per_month": tier.credits_per_month,
        "max_pages_per_credit": MAX_PAGES_PER_CREDIT,
        "max_file_size_mb": MAX_FILE_SIZE_MB,
        "overage_rate": tier.overage_rate,
        "has_pipeline": tier.has_pipeline,
    }
