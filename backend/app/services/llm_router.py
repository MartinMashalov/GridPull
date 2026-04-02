from __future__ import annotations

import asyncio
import logging
from itertools import count
from typing import Any

import litellm

from app.config import settings

logger = logging.getLogger(__name__)

_CEREBRAS_EXTRA_HEADERS = {
    "X-Cerebras-3rd-Party-Integration": "litellm",
}
_CEREBRAS_EXTRACTION_MODELS = (
    "cerebras/gpt-oss-120b",
    "cerebras/zai-glm-4.7",
)
_CEREBRAS_FORM_FILL_MODELS = (
    "cerebras/gpt-oss-120b",
)
_REQUEST_COUNTER = count()
_CEREBRAS_MAX_ATTEMPTS = 3


def _cerebras_keys() -> list[str]:
    return [
        key.strip()
        for key in (
            settings.cerebras_api_key,
            settings.cerebras_api_key2,
            settings.cerebras_api_key3,
        )
        if key and key.strip()
    ]


def _has_image_input(messages: Any) -> bool:
    if not isinstance(messages, list):
        return False
    for message in messages:
        if not isinstance(message, dict):
            continue
        content = message.get("content")
        if not isinstance(content, list):
            continue
        for part in content:
            if isinstance(part, dict) and part.get("type") in {"image_url", "input_image"}:
                return True
    return False


def _cerebras_models(route_profile: str) -> tuple[str, ...]:
    return _CEREBRAS_FORM_FILL_MODELS if route_profile == "form_fill" else _CEREBRAS_EXTRACTION_MODELS


def _normalise_completion_kwargs(kwargs: dict[str, Any], route_profile: str) -> dict[str, Any]:
    normalised = dict(kwargs)
    if "max_completion_tokens" in normalised and "max_tokens" not in normalised:
        normalised["max_tokens"] = normalised.pop("max_completion_tokens")
    if route_profile == "form_fill":
        normalised["reasoning_effort"] = "high"
        allowed_params = normalised.get("allowed_openai_params") or []
        if isinstance(allowed_params, str):
            allowed_list = [allowed_params]
        elif isinstance(allowed_params, (list, tuple, set)):
            allowed_list = [str(value) for value in allowed_params]
        else:
            allowed_list = []
        if "reasoning_effort" not in allowed_list:
            # LiteLLM currently needs this explicitly passed through for Cerebras gpt-oss.
            allowed_list.append("reasoning_effort")
        normalised["allowed_openai_params"] = allowed_list
    return normalised


def _clean_provider_specific_kwargs(kwargs: dict[str, Any]) -> dict[str, Any]:
    cleaned = dict(kwargs)
    cleaned.pop("api_base", None)
    cleaned.pop("custom_llm_provider", None)
    cleaned.pop("allowed_openai_params", None)
    cleaned.pop("reasoning_effort", None)
    headers = cleaned.get("extra_headers")
    if isinstance(headers, dict):
        filtered = {
            key: value
            for key, value in headers.items()
            if key.lower() != "x-cerebras-3rd-party-integration"
        }
        if filtered:
            cleaned["extra_headers"] = filtered
        else:
            cleaned.pop("extra_headers", None)
    return cleaned


def _build_cerebras_call_kwargs(
    base_kwargs: dict[str, Any],
    model: str,
    api_key: str,
) -> dict[str, Any]:
    kwargs = dict(base_kwargs)
    kwargs["model"] = model
    kwargs["api_key"] = api_key
    kwargs["api_base"] = settings.cerebras_api_base
    kwargs["custom_llm_provider"] = "cerebras"
    headers = dict(kwargs.get("extra_headers") or {})
    headers.update(_CEREBRAS_EXTRA_HEADERS)
    kwargs["extra_headers"] = headers
    return kwargs


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
    base_kwargs = _normalise_completion_kwargs(kwargs, route_profile)
    messages = base_kwargs.get("messages")
    keys = _cerebras_keys()
    has_image_input = _has_image_input(messages)
    last_cerebras_exc: Exception | None = None

    if has_image_input:
        logger.info("Skipping Cerebras for %s call because messages contain image input", route_profile)

    if not has_image_input and keys:
        models = _cerebras_models(route_profile)
        request_index = next(_REQUEST_COUNTER)
        for attempt in range(_CEREBRAS_MAX_ATTEMPTS):
            model = models[(request_index + attempt) % len(models)]
            key_index = (request_index + attempt) % len(keys)
            try:
                response = await litellm.acompletion(
                    **_build_cerebras_call_kwargs(base_kwargs, model, keys[key_index])
                )
                logger.info(
                    "Cerebras success for %s using %s key#%d",
                    route_profile,
                    model,
                    key_index + 1,
                )
                return response
            except Exception as exc:
                last_cerebras_exc = exc
                logger.warning(
                    "Cerebras attempt %d/%d failed for %s using %s key#%d: %s",
                    attempt + 1,
                    _CEREBRAS_MAX_ATTEMPTS,
                    route_profile,
                    model,
                    key_index + 1,
                    exc,
                )
                if attempt < _CEREBRAS_MAX_ATTEMPTS - 1:
                    await asyncio.sleep(2 ** attempt)

    openai_kwargs = _build_openai_call_kwargs(base_kwargs, fallback_model)
    try:
        response = await litellm.acompletion(**openai_kwargs)
        logger.info(
            "OpenAI fallback success for %s using %s",
            route_profile,
            openai_kwargs["model"],
        )
        return response
    except Exception as exc:
        if last_cerebras_exc is not None:
            logger.error(
                "OpenAI fallback failed for %s after Cerebras failure: cerebras_error=%s openai_error=%s",
                route_profile,
                last_cerebras_exc,
                exc,
            )
        raise
