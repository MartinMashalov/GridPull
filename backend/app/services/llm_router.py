from __future__ import annotations

import logging
from typing import Any

from openai import AsyncOpenAI

from app.config import settings

logger = logging.getLogger(__name__)

_openai_client: AsyncOpenAI | None = None


def _get_openai_client() -> AsyncOpenAI:
    global _openai_client
    if _openai_client is None:
        _openai_client = AsyncOpenAI(api_key=settings.openai_api_key)
    return _openai_client


_MAX_COMPLETION_TOKENS_MODELS = frozenset({
    "gpt-5.4", "gpt-5.4-mini", "gpt-5.4-nano",
    "o1", "o1-mini", "o1-preview", "o3", "o3-mini", "o4-mini",
})


def _normalise_completion_kwargs(kwargs: dict[str, Any], route_profile: str) -> dict[str, Any]:
    normalised = dict(kwargs)
    model = str(normalised.get("model") or "").lower()
    uses_max_completion = any(m in model for m in _MAX_COMPLETION_TOKENS_MODELS)
    if uses_max_completion:
        if "max_tokens" in normalised and "max_completion_tokens" not in normalised:
            normalised["max_completion_tokens"] = normalised.pop("max_tokens")
    else:
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
    cleaned.pop("api_key", None)
    return cleaned


def _build_openai_call_kwargs(
    base_kwargs: dict[str, Any],
    fallback_model: str | None,
) -> dict[str, Any]:
    kwargs = _clean_provider_specific_kwargs(base_kwargs)
    kwargs["model"] = fallback_model or settings.llm_openai_fallback_model
    return kwargs


async def routed_acompletion(
    *,
    route_profile: str = "extraction",
    fallback_model: str | None = None,
    **kwargs: Any,
) -> Any:
    base = dict(kwargs)
    if fallback_model:
        base["model"] = fallback_model          # explicit override from caller
    elif not base.get("model"):
        base["model"] = settings.llm_openai_fallback_model  # last-resort default
    # else: model already set in kwargs — keep it
    call_kwargs = _clean_provider_specific_kwargs(
        _normalise_completion_kwargs(base, route_profile)
    )
    client = _get_openai_client()
    try:
        response = await client.chat.completions.create(**call_kwargs)
        logger.info(
            "OpenAI success for %s using %s",
            route_profile,
            call_kwargs["model"],
        )
        return response
    except Exception as exc:
        logger.error(
            "OpenAI call failed for %s using %s: %s",
            route_profile,
            call_kwargs["model"],
            exc,
        )
        raise
