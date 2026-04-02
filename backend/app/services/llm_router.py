from __future__ import annotations

import logging
from typing import Any

import litellm

from app.config import settings

logger = logging.getLogger(__name__)


def _normalise_completion_kwargs(kwargs: dict[str, Any], route_profile: str) -> dict[str, Any]:
    normalised = dict(kwargs)
    if "max_completion_tokens" in normalised and "max_tokens" not in normalised:
        normalised["max_tokens"] = normalised.pop("max_completion_tokens")
    return normalised


def _clean_provider_specific_kwargs(kwargs: dict[str, Any]) -> dict[str, Any]:
    cleaned = dict(kwargs)
    cleaned.pop("api_base", None)
    cleaned.pop("custom_llm_provider", None)
    cleaned.pop("allowed_openai_params", None)
    cleaned.pop("reasoning_effort", None)
    cleaned.pop("extra_headers", None)
    return cleaned


def _build_openai_call_kwargs(
    base_kwargs: dict[str, Any],
    fallback_model: str | None,
) -> dict[str, Any]:
    kwargs = _clean_provider_specific_kwargs(base_kwargs)
    kwargs["model"] = fallback_model or settings.llm_openai_fallback_model
    if settings.openai_api_key:
        kwargs["api_key"] = settings.openai_api_key
    return kwargs


async def routed_acompletion(
    *,
    route_profile: str = "extraction",
    fallback_model: str | None = None,
    **kwargs: Any,
) -> Any:
    openai_kwargs = _build_openai_call_kwargs(
        _normalise_completion_kwargs(kwargs, route_profile),
        fallback_model,
    )
    try:
        response = await litellm.acompletion(**openai_kwargs)
        logger.info(
            "OpenAI success for %s using %s",
            route_profile,
            openai_kwargs["model"],
        )
        return response
    except Exception as exc:
        logger.error(
            "OpenAI call failed for %s using %s: %s",
            route_profile,
            openai_kwargs["model"],
            exc,
        )
        raise
