"""The Ollama adapter against a stand-in for the daemon's client (the sandbox has no daemon and no
`ollama` package). The stand-in yields exactly the chunk shapes /api/chat streams - message.content,
message.thinking, done_reason, prompt_eval_count, eval_count - and records what it was asked.

    python3 tests/analyst/test_ollama_adapter.py
"""
import os
import sys
import threading
import time
import types

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.normpath(os.path.join(HERE, "..", ".."))
sys.path[:0] = [ROOT, HERE]
import _stubs  # noqa: E402,F401  (fakes only what is absent, the real `ollama` is absent here)

# tiktoken is absent here too: a counter of two tokens per word stands in for the estimate
tk = types.ModuleType("tiktoken")


class _Enc:
    def encode(self, text):
        return [1] * (2 * len(str(text).split()))


tk.encoding_for_model = lambda name: _Enc()
sys.modules["tiktoken"] = tk

# httpx is absent here: a Timeout that remembers its fields, and the error class the adapter lists
hx = types.ModuleType("httpx")


class _Timeout:
    def __init__(self, timeout=None, connect=None, read=None, write=None, pool=None):
        self.connect, self.read, self.write, self.pool = connect, read, write, pool


hx.Timeout = _Timeout
hx.TransportError = type("TransportError", (Exception,), {})
sys.modules["httpx"] = hx

# a stand-in `ollama` module with the one class the adapter imports
ollama_mod = types.ModuleType("ollama")


class FakeClient:
    """Records the request; streams scripted chunks."""
    calls = []
    script = []            # chunks to stream for the next chat()
    show_info = {"capabilities": ["completion", "thinking"]}
    show_fail = False

    def __init__(self, host=None, timeout=None, headers=None, **kw):
        FakeClient.last_init = {"host": host, "timeout": timeout, "headers": headers}

    def show(self, model):
        if FakeClient.show_fail:
            raise RuntimeError("daemon too old for /api/show")
        return dict(FakeClient.show_info)

    def chat(self, **params):
        FakeClient.calls.append(params)
        if params.get("stream"):
            def gen():
                for c in FakeClient.script:
                    if isinstance(c, float):           # a pause, to exercise the idle deadline
                        time.sleep(c)
                    else:
                        yield c
            return gen()
        last = FakeClient.script[-1] if FakeClient.script else {}
        return {"message": {"content": "".join(c["message"].get("content", "") for c in FakeClient.script if isinstance(c, dict))},
                "prompt_eval_count": last.get("prompt_eval_count", 0), "eval_count": last.get("eval_count", 0)}


ollama_mod.Client = FakeClient
sys.modules["ollama"] = ollama_mod

from bambooai.models import ollama_models as om  # noqa: E402

results = []


def check(name, cond, detail=""):
    results.append((name, bool(cond)))
    print(("  ok   " if cond else "  FAIL ") + name + ("" if cond else f"  <- {str(detail)[:300]}"))


class Pane:
    def __init__(self):
        self.text, self.thought, self.system = [], [], []

    def print_wrapper(self, message, end="\n", flush=False, chain_id=None, thought=False):
        (self.thought if thought else self.text).append(message)

    def display_system_messages(self, m):
        self.system.append(m)


class Prompts:
    google_search_react_system = "{}"


def stream(messages, effort="medium", props=None, script=None, stop_event=None):
    FakeClient.calls.clear(); FakeClient.script[:] = script or []
    om.set_model_properties(props or {})
    om._show_cache.clear()
    pane = Pane()
    out = om.llm_stream(Prompts(), None, pane, "c1", messages, "qwen3:8b", 0, 16000, None, None, [], effort, None, stop_event=stop_event)
    return out, pane, FakeClient.calls[-1]


MSGS = [{"role": "system", "content": "contract " * 3000}, {"role": "user", "content": "question"}]   # ~6k tokens
DONE = {"message": {"content": ""}, "done": True, "done_reason": "stop", "prompt_eval_count": 6100, "eval_count": 3}

# ---- the request: options, think, keep_alive
out, pane, req = stream(MSGS, "high", {"context_window": 65536, "reasoning_efforts": ["low", "medium", "high"]},
                        [{"message": {"content": "ok "}}, {"message": {"content": "done"}}, DONE])
check("num_ctx is sent when the template declares context_window", req["options"].get("num_ctx") == 65536, req["options"])
check("num_predict carries max_tokens; temperature rides along; nothing else is forced (no top_k)", req["options"].get("num_predict") == 16000 and "top_k" not in req["options"], req["options"])
check("think is the model's own level name when it defines levels", req.get("think") == "high", req.get("think"))
check("keep_alive is sent (default 30m)", req.get("keep_alive") == "30m", req.get("keep_alive"))
check("the content streamed to the pane and the reply assembled", "".join(pane.text).startswith("ok done") and out[0] == "ok done", (pane.text, out[0]))
check("token counts come from the daemon's final chunk", out[2] == 6100 and out[3] == 3, out[2:4])

# ---- think mapping
out, pane, req = stream(MSGS, "none", {}, [{"message": {"content": "x"}}, DONE])
check("effort 'none' turns thinking off (think=false)", req.get("think") is False, req.get("think"))
out, pane, req = stream(MSGS, "medium", {}, [{"message": {"content": "x"}}, DONE])
check("a thinking model with no level names gets think=true", req.get("think") is True, req.get("think"))
out, pane, req = stream(MSGS, "xhigh", {"reasoning_efforts": ["low", "medium", "high"]}, [{"message": {"content": "x"}}, DONE])
check("an alias the model lacks folds to its nearest level (xhigh -> high)", req.get("think") == "high", req.get("think"))
FakeClient.show_info = {"capabilities": ["completion"]}
out, pane, req = stream(MSGS, "high", {}, [{"message": {"content": "x"}}, DONE])
check("a model without the thinking capability is sent no think field at all", "think" not in req, req.keys())
FakeClient.show_info = {"capabilities": ["completion", "thinking"]}
FakeClient.show_fail = True
out, pane, req = stream(MSGS, "high", {}, [{"message": {"content": "x"}}, DONE])
check("an old daemon without /api/show: no think field, the call still works", "think" not in req and out[0] == "x", req.keys())
FakeClient.show_fail = False
check("no num_ctx when the template says nothing (the daemon's default stands)", "num_ctx" not in req["options"], req["options"])

# ---- the thinking channel
out, pane, req = stream(MSGS, "high", {}, [{"message": {"thinking": "let me think"}}, {"message": {"thinking": " more"}}, {"message": {"content": "answer"}}, DONE])
check("message.thinking goes to the pane's reasoning block, never into the answer", "".join(pane.thought) == "let me think more" and out[0] == "answer" and "think" not in out[0], (pane.thought, out[0]))

# ---- truncation report
short = dict(DONE, prompt_eval_count=4096)
out, pane, req = stream(MSGS, "high", {}, [{"message": {"content": "x"}}, short])
check("a prompt the daemon evaluated far short of what we sent is reported, with the remedies", any("context length is shorter" in m and "context_window" in m for m in pane.system), pane.system)
out, pane, req = stream(MSGS, "high", {}, [{"message": {"content": "x"}}, DONE])
check("a prompt evaluated in full is not reported", not pane.system, pane.system)

# ---- the idle deadline and stop
om.OLLAMA_IDLE_TIMEOUT = 1.0
t0 = time.time()
try:
    out, pane, req = stream(MSGS, "high", {}, [{"message": {"content": "first"}}, 2.5, {"message": {"content": "late"}}, DONE])
    check("silence after the first chunk beyond the idle deadline ends the stream with an error", False, out[0])
except Exception as exc:  # noqa: BLE001
    check("silence after the first chunk beyond the idle deadline ends the stream with an error", "no data" in str(exc) and time.time() - t0 < 2.4, (exc, time.time() - t0))
t0 = time.time()
out, pane, req = stream(MSGS, "high", {}, [2.2, {"message": {"content": "slow first token"}}, DONE])
check("a slow FIRST chunk is waited for, beyond the idle deadline", out[0] == "slow first token" and time.time() - t0 >= 2.0, (out[0], time.time() - t0))
om.OLLAMA_IDLE_TIMEOUT = 300.0

# ---- the client: host, headers, unbounded read
os.environ.pop("REMOTE_OLLAMA", None); os.environ.pop("OLLAMA_API_KEY", None)
om.init(); li = FakeClient.last_init
check("the default host is the local daemon", li["host"] == "http://localhost:11434", li)
check("the read timeout is unbounded (the idle deadline guards the stream)", li["timeout"] is None or getattr(li["timeout"], "read", 1) is None, li["timeout"])
os.environ["REMOTE_OLLAMA"] = "https://ollama.com"; os.environ["OLLAMA_API_KEY"] = "k-1"
om.init(); li = FakeClient.last_init
check("direct cloud: the key becomes the Authorization header", li["headers"] == {"Authorization": "Bearer k-1"}, li["headers"])
os.environ["REMOTE_OLLAMA"] = "myhost:11434"; os.environ.pop("OLLAMA_API_KEY")
om.init(); li = FakeClient.last_init
check("a bare host:port gets http:// and no header", li["host"] == "http://myhost:11434" and not li["headers"], li)
os.environ.pop("REMOTE_OLLAMA")

# ---- llm_call: a utility call runs with thinking off
FakeClient.calls.clear(); FakeClient.script[:] = [{"message": {"content": "{\"a\": 1}"}, "prompt_eval_count": 10, "eval_count": 4}]
om.set_model_properties({})
om._show_cache.clear()
r = om.llm_call([{"role": "user", "content": "hi"}], "qwen3:8b", 0, 100, {"type": "json_object"}, None)
req = FakeClient.calls[-1]
check("llm_call: think=false, keep_alive, format json", req.get("think") is False and req.get("keep_alive") == "30m" and req.get("format") == "json", req)
check("llm_call returns the seven values the dispatcher unpacks", len(r) == 7 and r[0] == "{\"a\": 1}" and r[2] == 10 and r[3] == 4, r[:4])

n_fail = sum(1 for _, ok in results if not ok)
print(f"\n{len(results) - n_fail} passed, {n_fail} failed")
sys.exit(1 if n_fail else 0)
