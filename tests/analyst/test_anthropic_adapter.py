"""The Anthropic adapter's request shape for the Claude 5.5 family (2026-10-08), from the model's properties entry: effort
and adaptive thinking, thinking turned off where the model allows it, no sampling parameters; the old shape for earlier
models. No network: the shaping is a pure function of the entry and the seat's effort."""
import os, sys
sys.path.insert(0, os.path.dirname(__file__)); sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
import _stubs  # noqa: F401
from bambooai.models import anthropic_models as A
from bambooai.models import openrouter_models as OR

passed, failed = [], []
def check(name, cond, detail=""):
    (passed if cond else failed).append(name); print(("  ok   " if cond else "  FAIL ") + name + ("" if cond else f"  <- {detail}"))

HAIKU = {"reasoning_style": "effort", "reasoning_efforts": ["low", "medium", "high", "xhigh", "max"], "thinking_off": "disabled", "no_sampling": True}
SONNET = dict(HAIKU, thinking_off="between_tools")
OPUS = {k: v for k, v in HAIKU.items() if k != "thinking_off"}

def shape(props, effort, model="claude-x", temperature=0, stream=True):
    A.set_model_properties(props); A.set_reasoning_style(props.get("reasoning_style")); A.set_reasoning_efforts(props.get("reasoning_efforts"))
    return A.request_params(model, temperature, 16000, effort=effort, stream=stream)

p = shape(HAIKU, "high", "claude-haiku-5-5")
check("Haiku 5.5 at high: output_config.effort high, adaptive thinking with summarized display, no temperature, stream and max_tokens kept",
      p == {"model": "claude-haiku-5-5", "max_tokens": 16000, "stream": True, "thinking": {"type": "adaptive", "display": "summarized"}, "output_config": {"effort": "high"}}, p)
p = shape(HAIKU, "none", "claude-haiku-5-5")
check("Haiku 5.5 asked for no thinking: thinking disabled (allowed at high or below) at the lowest effort, no display field",
      p["thinking"] == {"type": "disabled"} and p["output_config"] == {"effort": "low"}, p)
p = shape(SONNET, "none", "claude-sonnet-5-5")
check("Sonnet 5.5 asked for no thinking: between_tools, its lowest setting, at the lowest effort", p["thinking"] == {"type": "between_tools"} and p["output_config"] == {"effort": "low"}, p)
p = shape(OPUS, "none", "claude-opus-5-5")
check("Opus 5.5 asked for no thinking: it cannot be turned off, so adaptive at the lowest effort", p["thinking"] == {"type": "adaptive", "display": "summarized"} and p["output_config"] == {"effort": "low"}, p)
p = shape(OPUS, "xhigh", "claude-opus-5-5")
check("Opus 5.5 at xhigh: the declared level is sent as is", p["output_config"] == {"effort": "xhigh"}, p)
p = shape(dict(HAIKU, reasoning_efforts=["low", "high", "max"]), "medium")
check("a requested level the model does not declare snaps to the lowest declared level at or above it", p["output_config"] == {"effort": "high"}, p)
p = shape({"reasoning_style": None}, "high", "claude-haiku-4-5-20251001", temperature=0)
check("an earlier model keeps the old shape: temperature sent, no thinking or effort fields", p == {"model": "claude-haiku-4-5-20251001", "max_tokens": 16000, "stream": True, "temperature": 0}, p)
p = shape(HAIKU, None, "claude-haiku-5-5", stream=False)
check("the non-streaming path with no effort known: no thinking or effort field (the model's default), still no temperature", "thinking" not in p and "output_config" not in p and "temperature" not in p and "stream" not in p, p)
A.set_model_properties(None); A.set_reasoning_style(None); A.set_reasoning_efforts(None)
p = A.request_params("claude-haiku-4-5-20251001", 0.5, 1000)
check("after a reset hand-off nothing of the last model's rules remains", p == {"model": "claude-haiku-4-5-20251001", "max_tokens": 1000, "temperature": 0.5}, p)

# OpenRouter: the same no_sampling fact leaves temperature out of the request
OR.set_model_properties({"no_sampling": True})
check("OpenRouter: a model with no_sampling gets no temperature (the client's NOT_GIVEN)", OR._sampling(0) is OR.openai.NOT_GIVEN)
OR.set_model_properties(None)
check("OpenRouter: otherwise the temperature is sent as given", OR._sampling(0) == 0)

print(f"\n{len(passed)} passed, {len(failed)} failed")
sys.exit(1 if failed else 0)
