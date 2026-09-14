"""The scripted analyst: a provider module for the local stack.

The web app's model layer (bambooai/models/__init__.py) dispatches to a provider module by
name from a fixed table, so this module is registered under an existing but unused name
(`bambooai.models.vllm_models`; the local config's seats say `"provider": "vllm"`) before the
app is imported - see webapp_launcher.py. No production file changes.

It implements the provider contract the ModelManager calls:
  llm_stream(prompt_manager, log_and_call_manager, output_manager, chain_id, messages, model,
             temperature, max_tokens, tools, response_format, reasoning_models,
             reasoning_effort, api_keys, stop_event=None)
      -> (content, messages, prompt_tokens, completion_tokens, total_tokens, elapsed, tps)
  llm_call(messages, model, temperature, max_tokens, response_format=None, api_keys=None)
      -> the same tuple
and streams the reply through output_manager.print_wrapper exactly as the real adapters do:
reasoning first as `thought` tokens, then the visible text in small chunks, so the pane shows a
turn arriving instead of appearing whole.

What it says comes from a scenario (tools/stack/scenarios/<name>.py): `load(name)` here, then
`SCENARIO.reply(system, user) -> (thinking, text)`. The scenario reads the real prompt (the
question, the turn number, the cell outputs) and answers from it, so the numbers in its report
are the numbers the kernel printed.
"""
import importlib.util
import os
import time

HERE = os.path.dirname(os.path.abspath(__file__))
SCENARIO = None
CHUNK = 48
DELAY = float(os.environ.get("STACK_STREAM_DELAY", "0.012"))    # seconds per chunk while streaming (~4,000 chars/s)
PAUSE = float(os.environ.get("STACK_TURN_PAUSE", "0"))          # seconds of "thinking" before each reply, to watch a run
TRANSPORT_ERRORS = ()               # nothing here is a transport


def load(name):
    """Import tools/stack/scenarios/<name>.py and make it the active scenario."""
    global SCENARIO
    path = os.path.join(HERE, "scenarios", f"{name}.py")
    spec = importlib.util.spec_from_file_location(f"stack_scenario_{name}", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    SCENARIO = mod.Scenario()
    return mod


def init(api_keys=None):
    return None


def _split(messages):
    system = "\n".join(m.get("content", "") for m in messages if m.get("role") == "system")
    user = next((m.get("content", "") for m in reversed(messages) if m.get("role") == "user"), "")
    return system, user


def _tokens(s):
    return max(1, len(s or "") // 4)


def _reply(messages):
    if SCENARIO is None:
        raise RuntimeError("harness_models: no scenario loaded (call harness_models.load(name))")
    system, user = _split(messages)
    thinking, text = SCENARIO.reply(system, user)
    return thinking or "", text or ""


def llm_call(messages, model, temperature, max_tokens, response_format=None, api_keys=None):
    t0 = time.time()
    thinking, text = _reply(messages)
    elapsed = max(0.01, time.time() - t0)
    pt = sum(_tokens(m.get("content", "")) for m in messages)
    ct = _tokens(thinking) + _tokens(text)
    return text, list(messages), pt, ct, pt + ct, round(elapsed, 3), round(ct / elapsed, 1)


def llm_stream(prompt_manager, log_and_call_manager, output_manager, chain_id, messages, model,
               temperature, max_tokens, tools=None, response_format=None, reasoning_models=None,
               reasoning_effort=None, api_keys=None, stop_event=None):
    t0 = time.time()
    thinking, text = _reply(messages)
    if PAUSE:
        waited = 0.0
        while waited < PAUSE and not (stop_event is not None and stop_event.is_set()):
            time.sleep(0.1); waited += 0.1
    stopped = False
    for body, thought in ((thinking, True), (text, False)):
        for i in range(0, len(body), CHUNK):
            if stop_event is not None and stop_event.is_set():
                stopped = True
                break
            output_manager.print_wrapper(body[i:i + CHUNK], end="", flush=True, chain_id=chain_id, thought=thought)
            time.sleep(DELAY)
        if stopped:
            break
    elapsed = max(0.01, time.time() - t0)
    pt = sum(_tokens(m.get("content", "")) for m in messages)
    ct = _tokens(thinking) + _tokens(text)
    return text, list(messages), pt, ct, pt + ct, round(elapsed, 3), round(ct / elapsed, 1)
