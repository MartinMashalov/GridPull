from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch, MagicMock

_BACKEND = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_BACKEND))

from app.config import settings
from app.services.llm_router import routed_acompletion


def _fake_response():
    resp = MagicMock()
    resp.choices = [MagicMock()]
    resp.choices[0].message.content = "{}"
    resp.usage = MagicMock(prompt_tokens=10, completion_tokens=5)
    resp.model = "gpt-4.1-mini"
    return resp


class LlmRouterTests(unittest.IsolatedAsyncioTestCase):
    async def test_routes_extraction_calls_to_openai_default_model(self) -> None:
        fake_response = _fake_response()
        with patch("app.services.llm_router._get_openai_client") as mock_get_client:
            mock_client = AsyncMock()
            mock_client.chat.completions.create = AsyncMock(return_value=fake_response)
            mock_get_client.return_value = mock_client

            response = await routed_acompletion(
                route_profile="extraction",
                messages=[{"role": "user", "content": "hello"}],
                response_format={"type": "json_object"},
            )

        self.assertIs(response, fake_response)
        kwargs = mock_client.chat.completions.create.await_args.kwargs
        self.assertEqual(kwargs["model"], settings.llm_openai_fallback_model)

    async def test_uses_fallback_model_for_form_fill(self) -> None:
        fake_response = _fake_response()
        with patch("app.services.llm_router._get_openai_client") as mock_get_client:
            mock_client = AsyncMock()
            mock_client.chat.completions.create = AsyncMock(return_value=fake_response)
            mock_get_client.return_value = mock_client

            await routed_acompletion(
                route_profile="form_fill",
                fallback_model="gpt-4.1-nano",
                messages=[{"role": "user", "content": "hello"}],
                response_format={"type": "json_object"},
            )

        kwargs = mock_client.chat.completions.create.await_args.kwargs
        self.assertEqual(kwargs["model"], "gpt-4.1-nano")

    async def test_renames_max_tokens_to_max_completion_tokens_for_new_models(self) -> None:
        fake_response = _fake_response()
        with patch("app.services.llm_router._get_openai_client") as mock_get_client:
            mock_client = AsyncMock()
            mock_client.chat.completions.create = AsyncMock(return_value=fake_response)
            mock_get_client.return_value = mock_client

            await routed_acompletion(
                route_profile="form_fill",
                fallback_model="gpt-5.4-mini",
                messages=[{"role": "user", "content": "hello"}],
                response_format={"type": "json_object"},
                max_tokens=256,
            )

        kwargs = mock_client.chat.completions.create.await_args.kwargs
        self.assertNotIn("max_tokens", kwargs)
        self.assertEqual(kwargs["max_completion_tokens"], 256)

    async def test_keeps_max_tokens_for_legacy_models(self) -> None:
        fake_response = _fake_response()
        with patch("app.services.llm_router._get_openai_client") as mock_get_client:
            mock_client = AsyncMock()
            mock_client.chat.completions.create = AsyncMock(return_value=fake_response)
            mock_get_client.return_value = mock_client

            await routed_acompletion(
                route_profile="extraction",
                fallback_model="gpt-4.1-mini",
                messages=[{"role": "user", "content": "hello"}],
                max_tokens=512,
            )

        kwargs = mock_client.chat.completions.create.await_args.kwargs
        self.assertEqual(kwargs["max_tokens"], 512)
        self.assertNotIn("max_completion_tokens", kwargs)


if __name__ == "__main__":
    unittest.main()
