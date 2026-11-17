"""The OpenAI adapter's error report: an APIError without a JSON body (a timeout or a dropped connection) must reach the
caller as that same error, with the cause shown, not as an AttributeError from reading e.body.get. No network."""
import os, sys
sys.path.insert(0, os.path.dirname(__file__)); sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
import _stubs  # noqa: F401
import httpx, openai
from unittest import mock
from bambooai.models import openai_models as O, resilience

passed, failed = [], []
def check(name, cond, detail=""):
    (passed if cond else failed).append(name); print(("  ok   " if cond else "  FAIL ") + name + ("" if cond else f"  <- {detail}"))

class Out:
    def __init__(self): self.shown = []
    def display_system_messages(self, m, **k): self.shown.append(m)
    def display_tool_info(self, *a, **k): pass
    def print_wrapper(self, *a, **k): pass

class PM: google_search_react_system = "{}"

class Client:
    def __init__(self, exc): self.exc = exc; self.calls = 0
    @property
    def chat(self): return self
    @property
    def completions(self): return self
    def create(self, **k): self.calls += 1; raise self.exc

REQ = httpx.Request("POST", "https://api.openai.com/v1/chat/completions")

def run(exc):
    out, client = Out(), Client(exc)
    with mock.patch.object(O, "init", return_value=client), mock.patch.object(O.google_search, "SmartSearchOrchestrator"), \
         mock.patch.object(resilience, "STREAM_RETRY_BACKOFF", 0):
        try:
            O.llm_stream(PM(), None, out, "c", [], "gpt-x", 0, 100)
            raised = None
        except BaseException as e:
            raised = e
    return raised, out, client

for label, exc in [("a timeout", openai.APITimeoutError(request=REQ)),
                   ("a dropped connection", openai.APIConnectionError(request=REQ))]:
    raised, out, client = run(exc)
    check(f"{label} (body is None) is re-raised as the same error, not an AttributeError", raised is exc, repr(raised))
    check(f"{label}: the cause is shown on screen", any("Openai API Error" in m for m in out.shown), out.shown)
    check(f"{label}: the stream open was retried within the pre-token budget", client.calls == resilience.STREAM_MIDFLIGHT_RETRIES + 1, client.calls)

resp = httpx.Response(400, request=REQ, json={"error": {"message": "bad"}})
raised, out, _ = run(openai.BadRequestError("bad", response=resp, body={"message": "bad"}))
check("an error with a dict body still shows its message", any("bad" in m for m in out.shown), out.shown)

print(f"\n{len(passed)} passed, {len(failed)} failed"); sys.exit(1 if failed else 0)
