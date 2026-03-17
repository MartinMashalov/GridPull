"""
Subscription tier definitions — single source of truth for limits, pricing, and overage rates.
"""

from __future__ import annotations
from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class TierConfig:
    name: str
    display_name: str
    price_monthly: int           # cents
    files_per_month: int
    max_pages_per_file: int
    overage_rate: Optional[int]  # cents per file, None = blocked
    has_pipeline: bool
    stripe_price_id_env: str     # env var name that holds the Stripe Price ID


TIERS: dict[str, TierConfig] = {
    "free": TierConfig(
        name="free",
        display_name="Free",
        price_monthly=0,
        files_per_month=10,
        max_pages_per_file=10,
        overage_rate=None,
        has_pipeline=False,
        stripe_price_id_env="",
    ),
    "starter": TierConfig(
        name="starter",
        display_name="Starter",
        price_monthly=1900,
        files_per_month=200,
        max_pages_per_file=50,
        overage_rate=15,
        has_pipeline=False,
        stripe_price_id_env="STRIPE_PRICE_STARTER",
    ),
    "pro": TierConfig(
        name="pro",
        display_name="Pro",
        price_monthly=4900,
        files_per_month=1000,
        max_pages_per_file=150,
        overage_rate=8,
        has_pipeline=False,
        stripe_price_id_env="STRIPE_PRICE_PRO",
    ),
    "business": TierConfig(
        name="business",
        display_name="Business",
        price_monthly=14900,
        files_per_month=5000,
        max_pages_per_file=500,
        overage_rate=5,
        has_pipeline=True,
        stripe_price_id_env="STRIPE_PRICE_BUSINESS",
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
        "files_per_month": tier.files_per_month,
        "max_pages_per_file": tier.max_pages_per_file,
        "overage_rate": tier.overage_rate,
        "has_pipeline": tier.has_pipeline,
    }
