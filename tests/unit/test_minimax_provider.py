"""Unit tests for MiniMax provider module."""
import os
import sys
import json
import time
import types
import pytest
from unittest.mock import patch, MagicMock


# ── Helpers to create a mock‑isolated copy of minimax_models ─────────────
def _load_minimax_models_isolated():
    """Import minimax_models with stubbed-out bambooai dependencies so that
    heavy transitive deps (newspaper, etc.) are not required."""
    # Save originals
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

    # Provide minimal stubs
    sys.modules["bambooai.google_search"].SmartSearchOrchestrator = MagicMock
    sys.modules["bambooai.utils"].get_readable_date = lambda: "2026-03-28"
    sys.modules["bambooai.context_retrieval"].request_user_context = MagicMock()

    # Force re-import
    if "bambooai.models.minimax_models" in sys.modules:
        del sys.modules["bambooai.models.minimax_models"]

    from bambooai.models import minimax_models

    # Restore
    for mod, orig in saved.items():
        if orig is None:
            sys.modules.pop(mod, None)
        else:
            sys.modules[mod] = orig

    return minimax_models


# Load module once for all tests
mm = _load_minimax_models_isolated()


# ── Temperature Clamping ─────────────────────────────────────────────────
class TestTemperatureClamping:
    """Tests for MiniMax temperature clamping behavior."""

    def test_clamp_zero_temperature(self):
        assert mm._clamp_temperature(0) == 0.01

    def test_clamp_negative_temperature(self):
        assert mm._clamp_temperature(-1) == 0.01

    def test_clamp_none_temperature(self):
        assert mm._clamp_temperature(None) == 0.01

    def test_valid_temperature_unchanged(self):
        assert mm._clamp_temperature(0.5) == 0.5

    def test_max_temperature(self):
        assert mm._clamp_temperature(1.0) == 1.0

    def test_temperature_above_max(self):
        assert mm._clamp_temperature(2.0) == 1.0

    def test_small_positive_temperature(self):
        assert mm._clamp_temperature(0.01) == 0.01


# ── Init ─────────────────────────────────────────────────────────────────
class TestMinimaxInit:

    @patch.dict(os.environ, {"MINIMAX_API_KEY": "test-key-123"})
    @patch.object(mm.openai, "OpenAI")
    def test_init_with_api_key(self, mock_openai_cls):
        mock_client = MagicMock()
        mock_openai_cls.return_value = mock_client

        client = mm.init()
        assert client is not None
        mock_openai_cls.assert_called_once_with(
            api_key="test-key-123",
            base_url="https://api.minimax.io/v1",
        )

    def test_init_without_api_key(self):
        env = os.environ.copy()
        env.pop("MINIMAX_API_KEY", None)
        with patch.dict(os.environ, env, clear=True):
            client = mm.init()
        assert client is None


# ── llm_call ─────────────────────────────────────────────────────────────
class TestLlmCall:

    def _mock_response(self, content="Hello World"):
        resp = MagicMock()
        resp.choices = [MagicMock()]
        resp.choices[0].message.content = f"  {content}  "
        resp.usage.prompt_tokens = 10
        resp.usage.completion_tokens = 5
        resp.usage.total_tokens = 15
        return resp

    @patch.dict(os.environ, {"MINIMAX_API_KEY": "k"})
    @patch.object(mm.openai, "OpenAI")
    def test_basic_return_shape(self, mock_cls):
        mock_client = MagicMock()
        mock_cls.return_value = mock_client
        mock_client.chat.completions.create.return_value = self._mock_response()

        result = mm.llm_call([{"role": "user", "content": "hi"}], "MiniMax-M2.7", 0, 100)
        assert len(result) == 7
        content, msgs, pt, ct, tt, elapsed, tps = result
        assert content == "Hello World"
        assert pt == 10
        assert ct == 5
        assert tt == 15

    @patch.dict(os.environ, {"MINIMAX_API_KEY": "k"})
    @patch.object(mm.openai, "OpenAI")
    def test_temperature_clamped_in_api_call(self, mock_cls):
        mock_client = MagicMock()
        mock_cls.return_value = mock_client
        mock_client.chat.completions.create.return_value = self._mock_response()

        mm.llm_call([{"role": "user", "content": "hi"}], "MiniMax-M2.7", 0, 100)

        call_kwargs = mock_client.chat.completions.create.call_args
        assert call_kwargs.kwargs.get("temperature") == 0.01

    @patch.dict(os.environ, {"MINIMAX_API_KEY": "k"})
    @patch.object(mm.openai, "OpenAI")
    def test_response_format_not_passed(self, mock_cls):
        mock_client = MagicMock()
        mock_cls.return_value = mock_client
        mock_client.chat.completions.create.return_value = self._mock_response()

        mm.llm_call(
            [{"role": "user", "content": "hi"}],
            "MiniMax-M2.7", 0.5, 100,
            response_format={"type": "json_object"},
        )

        call_kwargs = mock_client.chat.completions.create.call_args.kwargs
        assert "response_format" not in call_kwargs

    @patch.dict(os.environ, {"MINIMAX_API_KEY": "k"})
    @patch.object(mm, "time")
    @patch.object(mm.openai, "OpenAI")
    def test_rate_limit_retry(self, mock_cls, mock_time):
        import openai as openai_lib

        mock_client = MagicMock()
        mock_cls.return_value = mock_client

        mock_client.chat.completions.create.side_effect = [
            openai_lib.RateLimitError(
                message="rate limited",
                response=MagicMock(status_code=429, headers={}),
                body=None,
            ),
            self._mock_response("retry ok"),
        ]
        mock_time.time.side_effect = [1.0, 2.0, 3.0, 4.0]

        content, *_ = mm.llm_call(
            [{"role": "user", "content": "hi"}], "MiniMax-M2.7", 0.5, 100
        )
        assert content == "retry ok"
        mock_time.sleep.assert_called_once_with(10)


# ── Provider Registration ────────────────────────────────────────────────
class TestProviderRegistration:

    def test_minimax_in_provider_maps(self):
        import bambooai.models as models_pkg
        with open(models_pkg.__file__, "r") as f:
            src = f.read()
        # Should appear in both llm_call and llm_stream maps
        assert src.count('"minimax"') + src.count("'minimax'") >= 2

    def test_module_has_expected_exports(self):
        assert callable(mm.llm_call)
        assert callable(mm.llm_stream)
        assert callable(mm.init)
        assert callable(mm._clamp_temperature)


# ── Tools Definition ─────────────────────────────────────────────────────
class TestToolsDefinition:

    def test_minimax_tools_defined(self):
        from bambooai.messages.tools_definition import minimax_tools_definition
        assert isinstance(minimax_tools_definition, list)
        assert len(minimax_tools_definition) == 2

    def test_tools_have_google_search(self):
        from bambooai.messages.tools_definition import minimax_tools_definition
        names = [t["function"]["name"] for t in minimax_tools_definition]
        assert "google_search" in names

    def test_tools_have_request_user_context(self):
        from bambooai.messages.tools_definition import minimax_tools_definition
        names = [t["function"]["name"] for t in minimax_tools_definition]
        assert "request_user_context" in names

    def test_filter_tools_all(self):
        from bambooai.messages.tools_definition import filter_tools
        tools = filter_tools("minimax", search_enabled=True, feedback_enabled=True)
        assert len(tools) == 2

    def test_filter_tools_no_search(self):
        from bambooai.messages.tools_definition import filter_tools
        tools = filter_tools("minimax", search_enabled=False, feedback_enabled=True)
        names = [t["function"]["name"] for t in tools]
        assert "google_search" not in names

    def test_filter_tools_no_feedback(self):
        from bambooai.messages.tools_definition import filter_tools
        tools = filter_tools("minimax", search_enabled=True, feedback_enabled=False)
        names = [t["function"]["name"] for t in tools]
        assert "request_user_context" not in names

    def test_openai_format(self):
        from bambooai.messages.tools_definition import minimax_tools_definition
        for tool in minimax_tools_definition:
            assert tool["type"] == "function"
            assert "function" in tool
            assert "name" in tool["function"]
            assert "parameters" in tool["function"]


# ── LLM Config Sample ────────────────────────────────────────────────────
class TestLlmConfigSample:

    @pytest.fixture(scope="class")
    def config(self):
        path = os.path.join(os.path.dirname(__file__), "..", "..", "LLM_CONFIG_sample.json")
        with open(path, "r") as f:
            return json.load(f)

    def test_m27_in_config(self, config):
        assert "MiniMax-M2.7" in config["model_properties"]

    def test_m27_highspeed_in_config(self, config):
        assert "MiniMax-M2.7-highspeed" in config["model_properties"]

    def test_properties_structure(self, config):
        for name in ["MiniMax-M2.7", "MiniMax-M2.7-highspeed"]:
            props = config["model_properties"][name]
            assert props["capability"] == "base"
            assert props["multimodal"] == "false"
            assert props["templ_formating"] == "text"
            assert "prompt_tokens" in props
            assert "completion_tokens" in props
