"""The vLLM adapter against a stand-in for the OpenAI client (the sandbox has no server and no
`openai` package). The stand-in yields the chunk shapes vLLM 0.30 streamed on 2026-10-02 -
delta.reasoning, delta.content, finish_reason, a final usage chunk with reasoning_tokens - and
records what it was asked.

    python3 tests/analyst/test_vllm_adapter.py
"""
import os
import sys
import time
import types
from types import SimpleNamespace as NS

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.normpath(os.path.join(HERE, "..", ".."))
sys.path[:0] = [ROOT, HERE]
import _stubs  # noqa: E402,F401  (fakes only what is absent)

# tiktoken: two tokens per word
tk = types.ModuleType("tiktoken")


class _Enc:
    def encode(self, text):
        return [1] * (2 * len(str(text).split()))


tk.encoding_for_model = lambda name: _Enc()
sys.modules["tiktoken"] = tk

# httpx: a Timeout that remembers its fields
hx = types.ModuleType("httpx")


class _Timeout:
    def __init__(self, timeout=None, connect=None, read=None, write=None, pool=None):
        self.connect, self.read, self.write, self.pool = connect, read, write, pool


hx.Timeout = _Timeout
hx.TransportError = type("TransportError", (Exception,), {})
sys.modules["httpx"] = hx

# openai: the client surface the adapter uses, and the error classes it names
oa = types.ModuleType("openai")


class APIError(Exception):
    pass


class APIConnectionError(APIError):
    pass


class APITimeoutError(APIConnectionError):
    pass


class RateLimitError(APIError):
    pass


class InternalServerError(APIError):
    pass


class BadRequestError(APIError):
    pass


class NotFoundError(APIError):
    pass


class FakeClient:
    calls = []
    script = []
    last_init = None

    def __init__(self, **kw):
        FakeClient.last_init = kw
        self.chat = NS(completions=NS(create=self._create))

    def _create(self, **params):
        FakeClient.calls.append(params)
        if params.get("stream"):
            def gen():
                for c in FakeClient.script:
                    if isinstance(c, float):
                        time.sleep(c)
                    elif isinstance(c, Exception):
                        raise c
                    else:
                        yield c
            return gen()
        text = "".join(getattr(c.choices[0].delta, "content", "") or "" for c in FakeClient.script if hasattr(c, "choices") and c.choices)
        return NS(choices=[NS(message=NS(content=text))], usage=NS(prompt_tokens=10, completion_tokens=4, total_tokens=14))


oa.OpenAI = FakeClient
for cls in (APIError, APIConnectionError, APITimeoutError, RateLimitError, InternalServerError, BadRequestError, NotFoundError):
    setattr(oa, cls.__name__, cls)
sys.modules["openai"] = oa

from bambooai.models import vllm_models as vm  # noqa: E402
from bambooai.models import openrouter_models as om  # noqa: E402

results = []


def check(name, cond, detail=""):
    results.append((name, bool(cond)))
    print(("  ok   " if cond else "  FAIL ") + name + ("" if cond else f"  <- {str(detail)[:300]}"))


def chunk(content=None, reasoning=None, finish=None):
    delta = NS(content=content, reasoning=reasoning, tool_calls=None)
    return NS(choices=[NS(delta=delta, finish_reason=finish)], usage=None)


def usage_chunk(prompt, completion, reasoning):
    return NS(choices=[], usage=NS(prompt_tokens=prompt, completion_tokens=completion, total_tokens=prompt + completion,
                                   completion_tokens_details=NS(reasoning_tokens=reasoning)))


class Pane:
    def __init__(self):
        self.text, self.thought, self.system = [], [], []

    def print_wrapper(self, message, end="\n", flush=False, chain_id=None, thought=False):
        (self.thought if thought else self.text).append(message)

    def display_system_messages(self, m, chain_id=None):
        self.system.append(m)


class Prompts:
    google_search_react_system = "{}"


LAST = [None]


def stream(messages, effort="medium", props=None, script=None, reasoning_models=("qwen3.8-27b",), max_tokens=16000):
    FakeClient.calls.clear(); FakeClient.script[:] = script or []
    vm.set_model_properties(props or {})
    pane = Pane(); LAST[0] = pane
    out = vm.llm_stream(Prompts(), None, pane, "c1", messages, "qwen3.8-27b", 0, max_tokens, None, None, list(reasoning_models), effort, None, stop_event=None)
    return out, pane, FakeClient.calls[-1]


MSGS = [{"role": "system", "content": "contract " * 3000}, {"role": "user", "content": "question"}]   # ~6k tokens by the stand-in
SCRIPT = [chunk(content=""), chunk(reasoning="We need"), chunk(reasoning=" 391."), chunk(content="\n\n391", finish="stop"), usage_chunk(6100, 61, 55)]

# ---- the request
out, pane, req = stream(MSGS, "high", {"context_window": 65536, "reasoning_efforts": ["low", "medium", "high"]}, SCRIPT)
check("the stream asks for usage (stream_options.include_usage)", req.get("stream_options") == {"include_usage": True}, req.get("stream_options"))
check("reasoning_effort is sent by the model's own level name", req.get("reasoning_effort") == "high", req.get("reasoning_effort"))
check("the thinking goes to the pane's reasoning block, the answer to the content", "".join(pane.thought) == "We need 391." and out[0] == "\n\n391", (pane.thought, out[0]))
check("token counts come from the server's usage chunk (thinking included in completion)", out[2] == 6100 and out[3] == 61, out[2:4])
out, pane, req = stream(MSGS, "xhigh", {"reasoning_efforts": ["low", "medium", "high"]}, SCRIPT)
check("an alias the model lacks folds to its nearest level (xhigh -> high)", req.get("reasoning_effort") == "high", req.get("reasoning_effort"))
out, pane, req = stream(MSGS, "none", {}, SCRIPT)
check("effort 'none' switches thinking off through chat_template_kwargs, and sends no reasoning_effort",
      req.get("extra_body") == {"chat_template_kwargs": {"enable_thinking": False}} and "reasoning_effort" not in req, req)
out, pane, req = stream(MSGS, "high", {}, SCRIPT, reasoning_models=())
check("a model the template does not mark as reasoning is sent no thinking control", "reasoning_effort" not in req and "extra_body" not in req, req.keys())

# ---- no usage chunk (an older server): the estimate stands
out, pane, req = stream(MSGS, "high", {}, [chunk(content="x y z", finish="stop")])
check("without a usage chunk the counts fall back to the estimate", out[2] > 5000 and out[3] == 6, out[2:4])

# ---- the pre-flight
out, pane, req = stream(MSGS, "high", {"context_window": 8000}, SCRIPT, max_tokens=4000)
check("a prompt plus answer that cannot fit the declared context is warned about before sending, with the remedies",
      any("--max-model-len" in m for m in pane.system), pane.system)
out, pane, req = stream(MSGS, "high", {"context_window": 65536}, SCRIPT, max_tokens=4000)
check("one that fits is not", not pane.system, pane.system)

# ---- errors explained
for exc, needle in ((BadRequestError("This model's maximum context length is 65536 tokens. However, you requested 70000 tokens"), "--max-model-len"),
                    (NotFoundError("The model `qwen` does not exist."), "served-model-name")):
    try:
        stream(MSGS, "high", {}, [exc])
        check(f"{type(exc).__name__}: raised", False)
    except Exception:  # noqa: BLE001
        check(f"{type(exc).__name__}: the pane gets the explanation ({needle})", any(needle in m for m in LAST[0].system), LAST[0].system)
check("connection trouble is in TRANSPORT_ERRORS for the dispatcher's retry; a bad request is not",
      APIConnectionError in vm.TRANSPORT_ERRORS and RateLimitError in vm.TRANSPORT_ERRORS and BadRequestError not in vm.TRANSPORT_ERRORS, vm.TRANSPORT_ERRORS)

# ---- the client
os.environ.pop("REMOTE_VLLM", None); os.environ.pop("VLLM_API_KEY", None)
vm.init(); li = FakeClient.last_init
check("the default server is localhost:8000/v1 and the read timeout is unbounded", li["base_url"] == "http://localhost:8000/v1" and li["timeout"].read is None and li["max_retries"] == 0, li)
os.environ["REMOTE_VLLM"] = "192.168.1.201:8000"; os.environ["VLLM_API_KEY"] = "k-1"
vm.init(); li = FakeClient.last_init
check("a bare host:port gets http:// and /v1; VLLM_API_KEY is the key when set", li["base_url"] == "http://192.168.1.201:8000/v1" and li["api_key"] == "k-1", li)
os.environ.pop("REMOTE_VLLM"); os.environ.pop("VLLM_API_KEY")

# ---- the slow first token and the idle deadline (the OpenRouter guard, reused)
om.STREAM_IDLE_TIMEOUT = 1.0
t0 = time.time()
out, pane, req = stream(MSGS, "high", {}, [2.2, chunk(content="slow", finish="stop"), usage_chunk(10, 1, 0)])
check("a slow FIRST chunk is waited for beyond the idle deadline", out[0] == "slow" and time.time() - t0 >= 2.0, (out[0], time.time() - t0))
t0 = time.time()
out, pane, req = stream(MSGS, "high", {}, [chunk(content="first"), 3.0, chunk(content=" late", finish="stop")])
check("silence after output began ends the stream at the idle deadline with what was received", out[0] == "first" and time.time() - t0 < 2.8, (out[0], time.time() - t0))
om.STREAM_IDLE_TIMEOUT = 120.0

# ---- llm_call: thinking off, exact usage, seven values
FakeClient.calls.clear(); FakeClient.script[:] = [chunk(content='{"a": 1}', finish="stop")]
r = vm.llm_call([{"role": "user", "content": "hi"}], "qwen3.8-27b", 0, 100, {"type": "json_object"}, None)
req = FakeClient.calls[-1]
check("llm_call: thinking off, response_format passed, the seven values the dispatcher unpacks",
      req.get("extra_body") == {"chat_template_kwargs": {"enable_thinking": False}} and req.get("response_format") == {"type": "json_object"} and len(r) == 7 and r[2] == 10 and r[3] == 4, (req, r[:4]))

n_fail = sum(1 for _, ok in results if not ok)
print(f"\n{len(results) - n_fail} passed, {n_fail} failed")
sys.exit(1 if n_fail else 0)
