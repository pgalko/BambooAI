"""Integration tests for MiniMax provider.

These tests verify end-to-end behavior with the actual MiniMax API.
They require MINIMAX_API_KEY to be set in the environment.
Skip with: pytest -m "not integration"
"""
import os
import sys
import types
import pytest
from unittest.mock import MagicMock

# Skip all tests in this module if no API key is available
pytestmark = pytest.mark.skipif(
    not os.environ.get("MINIMAX_API_KEY"),
    reason="MINIMAX_API_KEY not set"
)


def _load_minimax_models_isolated():
    """Import minimax_models with stubbed-out bambooai dependencies."""
    saved = {}
    stubs = [
        "bambooai.google_search",
        "bambooai.utils",
        "bambooai.context_retrieval",
        "newspaper",
    ]
    for mod in stubs:
        saved[mod] = sys.modules.get(mod)
        sys.modules[mod] = types.ModuleType(mod)

    sys.modules["bambooai.google_search"].SmartSearchOrchestrator = MagicMock
    sys.modules["bambooai.utils"].get_readable_date = lambda: "2026-03-28"
    sys.modules["bambooai.context_retrieval"].request_user_context = MagicMock()

    if "bambooai.models.minimax_models" in sys.modules:
        del sys.modules["bambooai.models.minimax_models"]

    from bambooai.models import minimax_models

    for mod, orig in saved.items():
        if orig is None:
            sys.modules.pop(mod, None)
        else:
            sys.modules[mod] = orig

    return minimax_models


mm = _load_minimax_models_isolated()


class TestMiniMaxIntegrationLlmCall:
    """Integration tests for MiniMax llm_call."""

    @pytest.mark.integration
    def test_llm_call_real_api(self):
        """Test llm_call with the real MiniMax API."""
        messages = [
            {"role": "system", "content": "You are a helpful assistant. Reply in one sentence."},
            {"role": "user", "content": "What is 2+2?"}
        ]
        content, msgs, prompt_t, comp_t, total_t, elapsed, tps = mm.llm_call(
            messages, "MiniMax-M2.7-highspeed", 0.5, 100
        )

        assert isinstance(content, str)
        assert len(content) > 0
        assert prompt_t > 0
        assert comp_t > 0
        assert total_t > 0
        assert elapsed > 0

    @pytest.mark.integration
    def test_llm_call_temperature_zero_clamped(self):
        """Test that temperature 0 works (gets clamped) with real API."""
        messages = [
            {"role": "user", "content": "Say the word 'hello'"}
        ]
        content, _, _, _, _, _, _ = mm.llm_call(
            messages, "MiniMax-M2.7-highspeed", 0, 50
        )

        assert isinstance(content, str)
        assert len(content) > 0


class TestMiniMaxIntegrationInit:
    """Integration tests for MiniMax client initialization."""

    @pytest.mark.integration
    def test_init_creates_valid_client(self):
        """Test that init() creates a working client."""
        client = mm.init()
        assert client is not None
        assert str(client.base_url).rstrip("/") == "https://api.minimax.io/v1"

    @pytest.mark.integration
    def test_client_has_correct_api_key(self):
        """Test that the client uses the correct API key."""
        client = mm.init()
        assert client is not None
        assert client.api_key == os.environ.get("MINIMAX_API_KEY")
