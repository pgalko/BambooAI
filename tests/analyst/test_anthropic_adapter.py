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

# a refusal on the stream (2026-10-08: four turns of a Sonnet 5.5 run): stop_details names the category; the pane
# message and the reply marker carry it, and the request meta records it for the log and the session
from types import SimpleNamespace as NS
from bambooai.models import prompt_cache
class _OM:
    def __init__(self): self.msgs = []; self.thoughts = []; self.text = []
    def display_system_messages(self, m, *a, **k): self.msgs.append(m)
    def print_wrapper(self, m, *a, **k): (self.thoughts if k.get("thought") else self.text).append(m)
def _refusal_stream(details):
    yield NS(type="message_start", message=NS(usage=NS(input_tokens=412, cache_read_input_tokens=0, cache_creation_input_tokens=0)))
    yield NS(type="message_delta", delta=NS(stop_reason="refusal", stop_sequence=None, stop_details=details), usage=NS(output_tokens=0))
def _thinking_stream(think_parts):
    yield NS(type="message_start", message=NS(usage=NS(input_tokens=300, cache_read_input_tokens=0, cache_creation_input_tokens=0)))
    if think_parts:
        yield NS(type="content_block_start", index=0, content_block=NS(type="thinking", thinking="", signature=""))
        for t in think_parts:
            yield NS(type="content_block_delta", index=0, delta=NS(type="thinking_delta", thinking=t))
        yield NS(type="content_block_delta", index=0, delta=NS(type="signature_delta", signature="sig"))
        yield NS(type="content_block_stop", index=0)
    yield NS(type="content_block_start", index=1, content_block=NS(type="text", text=""))
    yield NS(type="content_block_delta", index=1, delta=NS(type="text_delta", text="###STEP###\nDone.\n###NOTE###\nn\n###ACTION###\nNAMES"))
    yield NS(type="content_block_stop", index=1)
    yield NS(type="message_delta", delta=NS(stop_reason="end_turn", stop_sequence=None, stop_details=None), usage=NS(output_tokens=90))
def _drive(details, stream=None):
    om, got = _OM(), []
    A.init = lambda api_keys=None: NS(messages=NS(create=lambda **kw: (stream if stream is not None else _refusal_stream(details))))
    A.set_model_properties(SONNET); A.set_reasoning_style("effort"); A.set_reasoning_efforts(SONNET["reasoning_efforts"])
    r = A.call_and_parse_stream(om, got, None, [{"role": "user", "content": "q"}], "sys", "claude-sonnet-5-5", 0, 1000, "c1",
                                api_keys={"anthropic": "k"}, effort="high")
    return om, got, r, prompt_cache.last_meta()
_init = A.init
try:
    om, got, r, meta = _drive(NS(type="refusal", category="reasoning_extraction", explanation="The request asks for the model's reasoning."))
    check("a refusal with stop_details: the pane names the category and the explanation, the reply marker names the category, "
          "the meta records both, no text, the prompt tokens counted",
          got == ["[claude-sonnet-5-5 declined this request: stop_reason refusal, reasoning_extraction]"]
          and om.msgs == ["claude-sonnet-5-5 declined this request (stop_reason: refusal, reasoning_extraction): The request asks for the model's reasoning."]
          and meta.get("declined") == "reasoning_extraction" and meta.get("declined_why") == "The request asks for the model's reasoning."
          and r[6] == 412 and r[7] == 0, (got, om.msgs, meta, r[6:]))
    om, got, r, meta = _drive(None)
    check("a refusal without stop_details (an older SDK, or no category): 'no category given', and nothing else differs",
          got == ["[claude-sonnet-5-5 declined this request: stop_reason refusal, no category given]"]
          and om.msgs == ["claude-sonnet-5-5 declined this request (stop_reason: refusal, no category given)."]
          and meta.get("declined") == "no category given" and "declined_why" not in meta, (got, om.msgs, meta))
    # the summarized thinking (2026-10-08): streamed to the pane's reasoning fold as it arrives, kept apart from the text,
    # and the call's meta says how much there was - 0 when the model produced no thinking block
    om, got, r, meta = _drive(None, stream=_thinking_stream(["Sea-level laps are the abroad ", "sessions; fit within athlete."]))
    check("a thinking block streams to the pane as thought, the text as text; the meta carries the thinking's length and block count; the reply is the text alone",
          om.thoughts == ["Sea-level laps are the abroad ", "sessions; fit within athlete."] and "".join(om.text) == "###STEP###\nDone.\n###NOTE###\nn\n###ACTION###\nNAMES"
          and got == ["###STEP###\nDone.\n###NOTE###\nn\n###ACTION###\nNAMES"] and meta.get("thinking_chars") == 59 and meta.get("thinking_blocks") == 1
          and r[5][0].thinking == "Sea-level laps are the abroad sessions; fit within athlete." and r[7] == 90, (om.thoughts, om.text, got, meta))
    om, got, r, meta = _drive(None, stream=_thinking_stream([]))
    check("a reply with no thinking block (adaptive thinking skipped it): nothing on the thought channel, thinking_chars 0 and thinking_blocks 0 in the meta",
          om.thoughts == [] and meta.get("thinking_chars") == 0 and meta.get("thinking_blocks") == 0 and got == ["###STEP###\nDone.\n###NOTE###\nn\n###ACTION###\nNAMES"], (om.thoughts, meta))
finally:
    A.init = _init
    A.set_model_properties(None); A.set_reasoning_style(None); A.set_reasoning_efforts(None)

# OpenRouter: the same no_sampling fact leaves temperature out of the request
OR.set_model_properties({"no_sampling": True})
check("OpenRouter: a model with no_sampling gets no temperature (the client's NOT_GIVEN)", OR._sampling(0) is OR.openai.NOT_GIVEN)
OR.set_model_properties(None)
check("OpenRouter: otherwise the temperature is sent as given", OR._sampling(0) == 0)

print(f"\n{len(passed)} passed, {len(failed)} failed")
sys.exit(1 if failed else 0)
