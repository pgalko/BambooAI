import importlib
import logging
import os
import threading
import contextlib
import time
import json
import sys

from bambooai.models import prompt_cache

from logger_config import get_logger
logger = get_logger(__name__)


# ONE LAW FOR EFFORT (2026-08-20). The agent line's reasoning_effort is
# THE value; a runtime caller may only LOWER it (the rescue-rung
# semantics - a truncation retry drops effort to un-wedge a turn -
# promoted from the bridge's table to the global rule). Six former
# habitats (call-site literals, this wrapper's default, delve defaults,
# the bridge's ceiling table, the tier key, transport) collapse into
# this one resolution point. The rank table is duplicated in the
# openrouter transport; a pin holds the two equal.
_EFFORT_RANK = {"none": 0, "minimal": 1, "low": 2, "medium": 3,
                "high": 4, "xhigh": 5, "max": 6}

_warned_missing_effort = set()


def _effective_effort(configured, requested, agent=None):
    """The seat's configured effort, unless the caller asked for a
    recognised LOWER word (honoured and logged - the rescue rung). A
    missing config value degrades to medium with a one-time warning;
    the shipped template never omits it (completeness-pinned)."""
    if configured not in _EFFORT_RANK:
        if agent and agent not in _warned_missing_effort:
            _warned_missing_effort.add(agent)
            logging.getLogger(__name__).warning(
                "Seat %r has no configured reasoning_effort; using "
                "'medium'. Add the key to its agent line.", agent)
        configured = "medium"
    req = str(requested).strip().lower() if requested else None
    if req in _EFFORT_RANK and _EFFORT_RANK[req] < _EFFORT_RANK[configured]:
        logging.getLogger(__name__).info(
            "Seat %r effort lowered %r -> %r by caller (rescue rung).",
            agent, configured, req)
        return req
    return configured


class ModelManager:
    def __init__(self, user_id=None, api_keys=None):
        """Initialize ModelManager with user-specific configuration"""
        self.user_id = user_id
        self.api_keys = api_keys or {}
        self.config = self._load_llm_config()
        self._preflight_providers()
    
    def _load_llm_config(self):
        """
        Load LLM configuration from JSON file.
        First tries user-specific config, then falls back to global config.
        Raises an error if configuration can't be loaded.
        """
        if self.user_id:
            user_config_path = f"config/{self.user_id}/LLM_CONFIG.json"
            if os.path.exists(user_config_path):
                try:
                    with open(user_config_path, 'r') as f:
                        return json.load(f)
                except Exception as e:
                    raise ValueError(f"Error reading user config {user_config_path}: {e}")
        
        if os.path.exists("LLM_CONFIG.json"):
            try:
                with open("LLM_CONFIG.json", 'r') as f:
                    return json.load(f)
            except Exception as e:
                raise ValueError(f"Error reading LLM_CONFIG.json file: {e}")
        
        sys.exit("Error: LLM_CONFIG.json not found. Please provide model configuration.")

    def get_model_properties(self):
        return self.config.get("model_properties", {})

    def _init(self, agent):
        agent_configs = self.config.get("agent_configs", [])

        model = None
        provider = None
        max_tokens = 4000
        temperature = 0
        response_format = None
        
        for item in agent_configs:
            if item.get('agent') == agent:
                details = item.get('details', {})
                model = details.get('model')
                provider = details.get('provider')
                max_tokens = details.get('max_tokens', max_tokens)
                temperature = details.get('temperature', temperature)
                # OpenRouter proxies the OpenAI-compatible endpoint, so it accepts
                # response_format on models that support structured output.
                if provider in ('openai', 'openrouter') and 'response_format' in details:
                    response_format = details.get('response_format')
                break
        
        if not model or not provider:
            raise ValueError(f"Agent '{agent}' not found in configuration or has incomplete details")
        
        # Resolve api_type from model_properties (falls back to chat_completions)
        model_props = self.config.get("model_properties", {}).get(model, {})
        api_type = model_props.get('api_type', 'chat_completions')
        
        return model, provider, max_tokens, temperature, response_format, api_type

    @contextlib.contextmanager
    def seat_on_another_seats_model(self, agent, donor_agent):
        """Run `agent` on `donor_agent`'s model, provider, effort and budget
        for the duration of the block, then restore it exactly (2026-09-03:
        the Theorist's provider queue failed a finished run's synthesis; the
        last rung runs the Theorist on the Synthesizer's model). The seat
        NAME stays, so the run log shows which seat ran on which model - a
        fallback is never silent."""
        configs = self.config.get("agent_configs", [])
        seat = next((i for i in configs if i.get('agent') == agent), None)
        donor = next((i for i in configs if i.get('agent') == donor_agent), None)
        if seat is None or donor is None:
            raise ValueError(f"seat_on_another_seats_model: '{agent}' or '{donor_agent}' not configured")
        saved = dict(seat.get('details') or {})
        try:
            seat['details'] = dict(donor.get('details') or {})
            yield
        finally:
            seat['details'] = saved

    def get_agent_reasoning_effort(self, agent):
        """The seat's configured effort word, or None when the config
        omits it (resolution then degrades to medium, warned once)."""
        for item in self.config.get("agent_configs", []):
            if item.get('agent') == agent:
                return (item.get('details', {}) or {}).get('reasoning_effort')
        return None

    def get_model_name(self, agent):
        agent_configs = self.config.get("agent_configs", [])
        model = None
        provider = None
        for item in agent_configs:
            if item.get('agent') == agent:
                details = item.get('details', {})
                model = details.get('model')
                provider = details.get('provider')
                break
        if not model or not provider:
            raise ValueError(f"Agent '{agent}' not found in configuration or has incomplete details")
        return model, provider

    def _try_import(self, module_name):
        return importlib.import_module(__package__ + '.' + module_name)

    def _preflight_providers(self):
        """Import every provider the active config names - at boot, loudly.

        The dispatcher imports provider modules lazily, so a provider that is
        configured but broken - a missing file, a typo'd filename, an absent
        SDK - stays invisible until the FIRST request dispatches to it, and
        that failure then surfaces wherever the call site buries it. Observed
        live: resilience.py was deployed as resILLience.py, every run worked
        for days (only openrouter, which never imports it, was dispatched),
        and the first web search imported gemini_models, whose ImportError
        was swallowed into the search FINDINGS string and reached no log at
        all. This turns that whole class of deployment drift into a boot-time
        journal line naming the module and the error.

        Logs, never raises: a broken provider must not block the ones that
        work, and an absent optional SDK is a legitimate state for a provider
        the config names but a given box never uses.
        """
        providers = sorted({(item.get('details') or {}).get('provider')
                            for item in self.config.get('agent_configs', [])}
                           - {None})
        for provider in providers:
            try:
                self._try_import(f'{provider}_models')
                if provider == 'openai':
                    # openai splits across two modules by api_type.
                    self._try_import('openai_responses_models')
            except Exception as exc:                            # noqa: BLE001
                logger.error(
                    "Provider preflight: '%s_models' failed to import (%s). "
                    "Every dispatch to provider '%s' will fail until this is "
                    "fixed.", provider, exc, provider)

    def llm_call(self, log_and_call_manager, messages: str, agent: str = None, chain_id: str = None):
        timestamp = time.strftime("%Y-%m-%d %H:%M:%S", time.gmtime())
        model, provider, max_tokens, temperature, response_format, api_type = self._init(agent)

        # Clear the cache side channel before dispatch. Doing this per provider
        # leaks the previous call's counts into the next one when the provider
        # does not reset (observed: an OpenAI request billed with an Anthropic
        # request's cached tokens).
        prompt_cache.reset()

        provider_function_map = {
            'local': 'llm_stream',
            'groq': 'llm_call',
            'openai': 'llm_call',
            'ollama': 'llm_call',
            'vllm': 'llm_call',
            'gemini': 'llm_call',
            'anthropic': 'llm_call',
            'mistral': 'llm_call',
            'openrouter': 'llm_call',
            "deepseek": 'llm_call',
            "grok": 'llm_call',
            "litellm": 'llm_call'
        }

        if provider in provider_function_map:
            if provider == 'openai' and api_type == 'responses':
                provider_module = self._try_import('openai_responses_models')
            else:
                provider_module = self._try_import(f'{provider}_models')

            function_name = provider_function_map[provider]

            # Routing preferences are a fact about the MODEL - an optional
            # "routing" object on its model_properties entry, passed
            # verbatim as OpenRouter's provider object. Handed over through
            # a per-thread side channel (the cache-count precedent, and the
            # same reset-before-dispatch discipline) so the uniform call
            # signature stays untouched. Handed over UNCONDITIONALLY, None
            # included: worker threads are reused, and a stale dict left by
            # the previous call would route this model with the last one's
            # rules. Providers without the hook are simply not handed it.
            _set_routing = getattr(provider_module, 'set_model_routing', None)
            if _set_routing:
                _set_routing((self.get_model_properties().get(model) or {})
                             .get('routing'))
            # The model's reasoning STYLE rides the same channel
            # (2026-08-19, the GLM-5.3 floor): "effort" on a
            # model_properties entry marks an effort-word model; the
            # provider module sends the word verbatim instead of a
            # token budget. Unconditional, None included, same stale-
            # thread-local reasoning as the routing hand-off above.
            _set_style = getattr(provider_module, 'set_reasoning_style', None)
            if _set_style:
                _set_style((self.get_model_properties().get(model) or {})
                           .get('reasoning_style'))
            _set_efforts = getattr(provider_module, 'set_reasoning_efforts', None)
            if _set_efforts:
                _set_efforts((self.get_model_properties().get(model) or {})
                             .get('reasoning_efforts'))

            content_received, local_llm_messages, prompt_tokens_used, completion_tokens_used, total_tokens_used, elapsed_time, tokens_per_second = getattr(provider_module, function_name)(
                messages, model, temperature, max_tokens, response_format, self.api_keys
            )
            
            # Providers report what they cached through a per-thread side
            # channel, so their return signatures stay unchanged.
            _cached, _cache_write = prompt_cache.last()
            # Facts the return value cannot carry: the reasoning effort ACTUALLY
            # sent, whether the answer was cut off, and the cap it was cut off
            # against. Same channel, same reset-before-dispatch discipline.
            _meta = prompt_cache.last_meta()
            log_and_call_manager.write_to_log(agent, chain_id, timestamp, model, local_llm_messages, content_received,
                                              prompt_tokens_used, completion_tokens_used, total_tokens_used,
                                              elapsed_time, tokens_per_second,
                                              cached_tokens=_cached,
                                              cache_write_tokens=_cache_write,
                                              call_meta=_meta)
            return content_received
        else:
            raise ValueError(f"Unsupported provider: {provider}")

    def llm_stream(self, prompt_manager, log_and_call_manager, output_manager, messages: str, agent: str = None,
                   chain_id: str = None, tools: str = None, reasoning_models: list = None,
                   reasoning_effort: str = None, stop_event: threading.Event = None):
        timestamp = time.strftime("%Y-%m-%d %H:%M:%S", time.gmtime())

        model, provider, max_tokens, temperature, response_format, api_type = self._init(agent)
        reasoning_effort = _effective_effort(
            self.get_agent_reasoning_effort(agent), reasoning_effort, agent)

        prompt_cache.reset()   # see the note in llm_call

        provider_function_map = {
            'local': 'llm_stream',
            'groq': 'llm_stream',
            'openai': 'llm_stream',
            'ollama': 'llm_stream',
            'vllm': 'llm_stream',
            'gemini': 'llm_stream',
            'anthropic': 'llm_stream',
            'mistral': 'llm_stream',
            'openrouter': 'llm_stream',
            "deepseek": 'llm_stream',
            "grok": 'llm_stream',
            "litellm": 'llm_stream'
        }

        if provider in provider_function_map:
            if provider == 'openai' and api_type == 'responses':
                provider_module = self._try_import('openai_responses_models')
            else:
                provider_module = self._try_import(f'{provider}_models')
            function_name = provider_function_map[provider]

            # The model's routing object, handed over before every dispatch
            # - see the note on the llm_call path; same channel, same
            # unconditional hand-off, None included.
            _set_routing = getattr(provider_module, 'set_model_routing', None)
            if _set_routing:
                _set_routing((self.get_model_properties().get(model) or {})
                             .get('routing'))
            # The model's reasoning STYLE rides the same channel
            # (2026-08-19, the GLM-5.3 floor): "effort" on a
            # model_properties entry marks an effort-word model; the
            # provider module sends the word verbatim instead of a
            # token budget. Unconditional, None included, same stale-
            # thread-local reasoning as the routing hand-off above.
            _set_style = getattr(provider_module, 'set_reasoning_style', None)
            if _set_style:
                _set_style((self.get_model_properties().get(model) or {})
                           .get('reasoning_style'))
            _set_efforts = getattr(provider_module, 'set_reasoning_efforts', None)
            if _set_efforts:
                _set_efforts((self.get_model_properties().get(model) or {})
                             .get('reasoning_efforts'))

            # TURN-LEVEL RETRY ON A TRANSPORT DEATH.
            #
            # The providers restart a stream that dies BEFORE its first token;
            # a drop AFTER the first token is fatal to that STREAM by design
            # (a started answer cannot be resumed). But the TURN is still
            # replayable: the same messages produce a fresh, complete answer.
            # Observed live: "Upstream error from DigitalOcean: Connection
            # closed" mid-Investigator-turn killed an entire chain that one
            # re-ask would very likely have saved. Each hardened provider
            # module exports TRANSPORT_ERRORS (its own SDK's error classes);
            # anything else - including a bug in the provider module -
            # propagates untouched on the first raise. The partial text
            # already streamed stays visible above the retry notice; the
            # returned string is what downstream consumes, so correctness is
            # unaffected.
            transport_errors = getattr(provider_module, 'TRANSPORT_ERRORS', ())
            # THE TURN LADDER (2026-09-04, run 5): five probes died on a
            # provider 400 that recurred on the single 2 s re-ask; the
            # investigation loop then salvaged with 1-3 committed steps. Three
            # re-asks at 5/20/60 s ride out a provider blip; a request the
            # provider rejects deterministically still fails, one minute
            # later, with the same salvage. LLM_TURN_RETRIES overrides the
            # count; extra attempts beyond the table reuse its last delay.
            _TURN_RETRY_DELAYS = (5, 10, 20)   # seconds before re-asking after a dropped answer (2026-09-05: 5/20/60 read as a hang)
            turn_retries = int(os.getenv('LLM_TURN_RETRIES', '3'))
            attempt = 0
            while True:
                try:
                    result = getattr(provider_module, function_name)(
                        prompt_manager,
                        log_and_call_manager,
                        output_manager, chain_id,
                        messages, model,
                        temperature,
                        max_tokens, tools,
                        response_format,
                        reasoning_models,
                        reasoning_effort,
                        self.api_keys,
                        stop_event=stop_event
                    )
                    break
                except transport_errors as exc:
                    # Not transient, never retried: the account is out of credit
                    # or the key is refused (2026-09-05: a 402 - "requires more
                    # credits, or fewer max_tokens" - was re-asked three times).
                    _status = getattr(exc, "status_code", None)
                    if _status in (401, 402, 403):
                        _why = {401: "the API key was refused", 402: "the provider account is out of credit",
                                403: "the provider refused the request"}[_status]
                        _msg = f"Provider error {_status}: {_why}. {str(exc)[:300]}"
                        logger.error(_msg)
                        try:
                            output_manager.display_system_messages(_msg, chain_id=chain_id)
                        except Exception:                       # noqa: BLE001
                            pass
                        raise
                    if attempt >= turn_retries:
                        raise
                    attempt += 1
                    delay = _TURN_RETRY_DELAYS[min(attempt, len(_TURN_RETRY_DELAYS)) - 1]
                    message = (f"The model connection dropped mid-answer "
                               f"({exc}); re-asking the model in {delay}s "
                               f"[{attempt}/{turn_retries}].")
                    logger.warning(message)
                    try:
                        output_manager.display_system_messages(
                            message, chain_id=chain_id)
                    except Exception:                           # noqa: BLE001
                        pass
                    time.sleep(delay)

            if tools:
                (content_received, tool_response, local_llm_messages,
                 prompt_tokens_used, completion_tokens_used, total_tokens_used, elapsed_time, tokens_per_second) = result
            else:
                (content_received, local_llm_messages,
                 prompt_tokens_used, completion_tokens_used, total_tokens_used, elapsed_time, tokens_per_second) = result
                tool_response = []

            # --- NEW: inject a sidecar system message with billing meta (non-breaking) ---
            if tools and isinstance(tool_response, list):
                meta = None
                for it in tool_response:
                    if isinstance(it, dict) and "__meta__" in it:
                        meta = it["__meta__"]
                        break
                if meta:
                    try:
                        meta_enriched = dict(meta)
                        meta_enriched.setdefault("model", model)
                        meta_json = json.dumps(meta_enriched)
                        # Ensure messages is a list (copy to avoid mutating caller's list)
                        local_llm_messages = list(local_llm_messages) + [
                            {"role": "system", "content": f"__billing_meta__: {meta_json}"}
                        ]
                    except Exception:
                        pass

            _cached, _cache_write = prompt_cache.last()
            # Facts the return value cannot carry: the reasoning effort ACTUALLY
            # sent, whether the answer was cut off, and the cap it was cut off
            # against. Same channel, same reset-before-dispatch discipline.
            _meta = prompt_cache.last_meta()
            log_and_call_manager.write_to_log(agent, chain_id, timestamp, model, local_llm_messages, content_received,
                                            prompt_tokens_used, completion_tokens_used, total_tokens_used,
                                            elapsed_time, tokens_per_second,
                                            cached_tokens=_cached,
                                            cache_write_tokens=_cache_write,
                                            call_meta=_meta)

            if tools:
                # Pass only well-formed triplets to callers (strip meta & anything malformed)
                filtered_tool_response = []
                if isinstance(tool_response, list):
                    for it in tool_response:
                        if isinstance(it, dict) and all(k in it for k in ("query", "result", "links")):
                            filtered_tool_response.append(it)
                return content_received, filtered_tool_response
            else:
                return content_received

        else:
            raise ValueError(f"Unsupported provider: {provider}")