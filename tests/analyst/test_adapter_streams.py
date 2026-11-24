"""Every provider adapter's stream, run once over scripted chunks with no network (0344): the text comes back whole, in
the seven-part answer the model layer reads, with the tokens the provider reported. The adapters had each carried the
tool loops of the first version - a search, a question to the person, a second model - which nothing could reach; with
them gone this is what holds the plain stream of each. A tool call no one asked for is not acted on.

An adapter that cannot be imported streams nothing. Mistral's SDK moved its client in 2.0, and the adapter is loaded
here over a made-up SDK in each of the two layouts (0351)."""
import importlib.machinery, importlib.util, os, sys, types
from types import SimpleNamespace as NS
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path[:0] = [HERE, os.path.dirname(os.path.dirname(HERE))]
import _stubs  # noqa: F401,E402
from unittest import mock  # noqa: E402

try:                                    # a machine with other Google packages and no google-genai: the stubs leave 'google' alone
    import google.genai                 # noqa: F401
except ImportError:
    for _name in ("google.genai", "google.genai.types", "google.genai.errors"):
        sys.modules[_name] = _stubs._Mod(_name)

from bambooai.models import (openai_models, openai_responses_models, mistral_models, deepseek_models, groq_models, grok_models,  # noqa: E402
                             openrouter_models, gemini_models, prompt_cache)

passed, failed = [], []
def check(name, cond, detail=""):
    (passed if cond else failed).append(name); print(("  ok   " if cond else "  FAIL ") + name + ("" if cond else f"  <- {detail}"))


class Out:
    def __init__(self): self.text, self.thoughts, self.said = [], [], []
    def print_wrapper(self, t, *a, thought=False, **k): (self.thoughts if thought else self.text).append(t)
    def display_system_messages(self, m, **k): self.said.append(m)
    def display_tool_info(self, *a, **k): pass


class Encoding:
    def encode(self, text): return list(text or "")


TIKTOKEN = NS(encoding_for_model=lambda name: Encoding(), get_encoding=lambda name: Encoding())
MESSAGES = [{"role": "system", "content": "You are the analyst."}, {"role": "user", "content": "Which regime yields more on loam?"}]
TEXT = ["Regime B yields ", "0.6 t/ha more on loam."]
WHOLE = "".join(TEXT)


def usage(p=120, c=30):
    return NS(prompt_tokens=p, completion_tokens=c, total_tokens=p + c, prompt_tokens_details=None, completion_tokens_details=None)


def delta(content=None, **more):
    return NS(content=content, tool_calls=more.pop("tool_calls", None), reasoning_content=None, reasoning=None, **more)


def chat_chunks(with_usage=True, tool_call=False):
    """Chat-completions chunks: the text in two parts, a tool call no one asked for where `tool_call`, the usage last."""
    out = [NS(choices=[NS(delta=delta(t), finish_reason=None)], usage=None, provider="a-host") for t in TEXT]
    if tool_call:
        call = NS(index=0, id="call_1", type="function", function=NS(name="google_search", arguments='{"search_query": "x"}'))
        out.append(NS(choices=[NS(delta=delta(tool_calls=[call]), finish_reason=None)], usage=None, provider="a-host"))
    if with_usage:
        out.append(NS(choices=[], usage=usage(), provider="a-host"))
    return out


class Chat:
    """A client whose chat.completions.create(**request) - or chat.stream(**request), Mistral's - gives the chunks."""
    def __init__(self, chunks): self.chunks, self.requests = chunks, []
    chat = completions = property(lambda self: self)
    def create(self, **request): self.requests.append(request); return iter(self.chunks)
    stream = create


def responses_events():
    done = NS(type="response.completed", response=NS(id="r1", usage=NS(input_tokens=120, output_tokens=30, input_tokens_details=None)))
    return [NS(type="response.output_text.delta", delta=t) for t in TEXT] + [NS(type="response.output_item.done", item=NS(type="function_call", name="google_search", arguments="{}", call_id="c")), done]


class Responses:
    def __init__(self, events): self.events, self.requests = events, []
    responses = property(lambda self: self)
    def create(self, **request): self.requests.append(request); return iter(self.events)


def stream(module, client, **patches):
    out = Out()
    prompt_cache.reset()
    with mock.patch.object(module, "init", return_value=client, create=True), mock.patch.multiple(module, **patches) if patches else mock.patch.dict({}, {}):
        got = module.llm_stream(None, None, out, "c1", [dict(m) for m in MESSAGES], "a-model", 0, 1000)
    return got, out


def plain(got, out, tokens=(120, 30, 150)):
    """The seven-part answer of a call without tools: the text whole and shown as it came, the messages, the tokens."""
    return (len(got) == 7 and got[0] == WHOLE and "".join(out.text) == WHOLE and isinstance(got[1], list)
            and (tokens is None or tuple(got[2:5]) == tokens) and got[5] >= 0 and got[6] >= 0)


# ---- the chat-completions adapters
client = Chat(chat_chunks())
got, out = stream(openai_models, client)
check("OpenAI: the stream's text whole, the usage as reported; no tool is sent with the request",
      plain(got, out) and len(client.requests) == 1 and "tools" not in client.requests[0], (got[:5], client.requests))
got, out = stream(openai_models, Chat(chat_chunks(tool_call=True)))
check("... a tool call in the stream - none was asked for - is not acted on: one request, the text as it came", plain(got, out), got[:5])

client = Chat(chat_chunks(with_usage=False))
got, out = stream(deepseek_models, client, tiktoken=TIKTOKEN)
check("DeepSeek: the stream's text whole, its tokens counted here; one request, no tool sent, and a tool call in the stream not acted on",
      plain(got, out, None) and got[3] == len(WHOLE) and len(client.requests) == 1 and "tools" not in client.requests[0]
      and plain(*stream(deepseek_models, Chat(chat_chunks(with_usage=False, tool_call=True)), tiktoken=TIKTOKEN), tokens=None), (got[:5], client.requests))

client = Chat([NS(choices=c.choices, usage=c.usage) for c in chat_chunks()[:2]] + [NS(choices=[], usage=usage())])
got, out = stream(groq_models, client, tiktoken=TIKTOKEN)
check("Groq: the stream's text whole, the usage as reported; one request, no tool sent",
      plain(got, out) and len(client.requests) == 1 and "tools" not in client.requests[0] and "tool_choice" not in client.requests[0], (got[:5], client.requests))

mistral_chunks = [NS(data=NS(choices=[NS(delta=NS(content=t, tool_calls=None))], usage=None)) for t in TEXT] + [NS(data=NS(choices=[], usage=usage()))]
client = Chat(mistral_chunks)
got, out = stream(mistral_models, client, Unset=None, SDKError=ConnectionError)      # the SDK's own names, stood in for where it is absent
check("Mistral: the stream's text whole, the usage as reported; one request, no tool sent",
      plain(got, out) and len(client.requests) == 1 and "tools" not in client.requests[0] and "tool_choice" not in client.requests[0], (got[:5], client.requests))


# ---- Mistral's SDK keeps its client in one of two places: the adapter loads over either
class Client:
    def __init__(self, api_key=None): self.api_key = api_key


class ClientOf2(Client): pass


class ClientOf1(Client): pass


def made_up(name, package=False, **holds):
    """A module of a made-up SDK that holds `holds` and nothing else. A package of it has no folder: no module is found under it."""
    module = types.ModuleType(name)
    module.__spec__ = importlib.machinery.ModuleSpec(name, None, is_package=package)
    if package:
        module.__path__ = []
    vars(module).update(holds)
    return module


def mistral_over(sdk):
    """The adapter loaded afresh while `sdk` - module name to module, None for a module that is not there - is the SDK
    installed: the client its init() builds, or the error it did not load for."""
    spec = importlib.util.spec_from_file_location("mistral_models_afresh", mistral_models.__file__)
    adapter = importlib.util.module_from_spec(spec)
    with mock.patch.dict(sys.modules, sdk):
        try:
            spec.loader.exec_module(adapter)
        except ImportError as e:
            return e
        return adapter.init({"mistral": "a-key"})


def is_client(built, kind):
    return type(built) is kind and built.api_key == "a-key"


built = mistral_over({"mistralai": made_up("mistralai", package=True), "mistralai.client": made_up("mistralai.client", package=True, Mistral=ClientOf2)})
check("Mistral's SDK from 2.0 on - the client under mistralai.client, nothing at the top of the package: the adapter loads, and its init() builds that client with the key",
      is_client(built, ClientOf2), repr(built))
top = made_up("mistralai", package=True, Mistral=ClientOf1)
built = [mistral_over({"mistralai": top, "mistralai.client": under}) for under in (made_up("mistralai.client", MistralClient=Client), None)]
check("... and 1.x - the client at the top of the package, none under mistralai.client, be that module the first client's or not there: the adapter loads, on that client",
      all(is_client(b, ClientOf1) for b in built), repr(built))

# ---- the Responses adapters
client = Responses(responses_events())
got, out = stream(openai_responses_models, client)
check("OpenAI, the Responses API: the text whole, the usage as reported; a function call among the items is not acted on - one request, no tool sent",
      plain(got, out) and len(client.requests) == 1 and "tools" not in client.requests[0] and "previous_response_id" not in client.requests[0], (got[:5], client.requests))
client = Responses(responses_events())
got, out = stream(grok_models, client)
check("xAI: the text whole, the usage as reported; a function call among the items is not acted on - one request, no tool sent, nothing stored",
      plain(got, out) and len(client.requests) == 1 and "tools" not in client.requests[0] and client.requests[0].get("store") is False, (got[:5], client.requests))

# ---- OpenRouter: the plain stream, and the tool call a provider makes of the model's own text
client = Chat(chat_chunks())
got, out = stream(openrouter_models, client, _get_encoding=lambda: Encoding())
check("OpenRouter: the stream's text whole, the usage as reported; one request, no tool sent",
      plain(got, out) and len(client.requests) == 1 and "tools" not in client.requests[0], (got[:5], client.requests))
code_call = NS(index=0, id="call_1", type="function", function=NS(name="python", arguments='{"code": "print(1)"}'))
client = Chat([NS(choices=[NS(delta=delta(tool_calls=[code_call]), finish_reason=None)], usage=None, provider="a-host"), NS(choices=[], usage=usage(), provider="a-host")])
got, out = stream(openrouter_models, client, _get_encoding=lambda: Encoding())
check("... a provider that takes the model's cell for a tool call: the call comes back as the text it was, a python block - one request, nothing called",
      len(got) == 7 and "print(1)" in got[0] and "```python" in got[0] and len(client.requests) == 1, got[0])

# ---- Gemini without the seat's tool
def g_chunk(text=None, usage_=None, thought=None):
    parts = [NS(text=text, thought=thought, function_call=None)] if text else None
    return NS(candidates=[NS(content=NS(parts=parts) if parts else None, finish_reason=None, grounding_metadata=None, url_context_metadata=None)], usage_metadata=usage_, model_version=None)


class Gemini:
    def __init__(self, chunks): self.chunks, self.models, self.requests = chunks, self, 0
    def count_tokens(self, model=None, contents=None): return NS(total_tokens=7)
    def generate_content_stream(self, model=None, contents=None, config=None): self.requests += 1; return iter(self.chunks)


g_usage = NS(prompt_token_count=120, candidates_token_count=30, thoughts_token_count=0, tool_use_prompt_token_count=0, total_token_count=150, cached_content_token_count=0)
client = Gemini([g_chunk("Weighing it.", thought=True)] + [g_chunk(t) for t in TEXT] + [g_chunk(usage_=g_usage)])
got, out = stream(gemini_models, client, types=_stubs._Mod("types"), genai_errors=NS(APIError=ConnectionError))
check("Gemini without the seat's tool: the text whole and the thinking apart, the usage as reported, one request; the answer in seven parts - no search record",
      plain(got, out) and out.thoughts == ["Weighing it."] and client.requests == 1, (got[:5], out.thoughts))
stopped = __import__("threading").Event(); stopped.set()
client = Gemini([g_chunk(t) for t in TEXT])
out = Out()
with mock.patch.object(gemini_models, "init", return_value=client), mock.patch.multiple(gemini_models, types=_stubs._Mod("types"), genai_errors=NS(APIError=ConnectionError)):
    got = gemini_models.llm_stream(None, None, out, "c1", [dict(m) for m in MESSAGES], "a-model", 0, 1000, stop_event=stopped)
check("... a stop asked before the stream: no request is made, and the call still answers - empty - in seven parts", len(got) == 7 and got[0] == "" and client.requests == 0, got[:5])

print(f"\n{len(passed)} passed, {len(failed)} failed")
sys.exit(1 if failed else 0)
