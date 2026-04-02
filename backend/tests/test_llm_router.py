from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch

_BACKEND = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_BACKEND))

from app.config import settings
from app.services.llm_router import routed_acompletion


class LlmRouterTests(unittest.IsolatedAsyncioTestCase):
    async def test_routes_extraction_calls_to_openai_default_model(self) -> None:
        fake_response = object()
        with patch("app.services.llm_router.litellm.acompletion", new=AsyncMock(return_value=fake_response)) as mocked:
            response = await routed_acompletion(
                route_profile="extraction",
                messages=[{"role": "user", "content": "hello"}],
                response_format={"type": "json_object"},
            )

        self.assertIs(response, fake_response)
        kwargs = mocked.await_args.kwargs
        self.assertEqual(kwargs["model"], settings.llm_openai_fallback_model)
        self.assertNotIn("custom_llm_provider", kwargs)
        self.assertNotIn("api_base", kwargs)

    async def test_ignores_requested_cerebras_model_and_still_uses_openai_default(self) -> None:
        with patch("app.services.llm_router.litellm.acompletion", new=AsyncMock(return_value=object())) as mocked:
            await routed_acompletion(
                route_profile="form_fill",
                model="cerebras/gpt-oss-120b",
                messages=[{"role": "user", "content": "hello"}],
                response_format={"type": "json_object"},
            )

        kwargs = mocked.await_args.kwargs
        self.assertEqual(kwargs["model"], settings.llm_openai_fallback_model)
        self.assertNotIn("custom_llm_provider", kwargs)
        self.assertNotIn("allowed_openai_params", kwargs)


if __name__ == "__main__":
    unittest.main()
