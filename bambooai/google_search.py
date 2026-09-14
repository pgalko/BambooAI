import re
import os

from logger_config import get_logger
logger = get_logger(__name__)

SEARCH_MODE = os.environ.get('WEB_SEARCH_MODE', 'google_ai')

SEARCH_INSTRUCTION = (
    "You are a research assistant. Answer the query with the specific facts it asks for - figures, rates, "
    "dates, names - not an essay. For every figure give the value with its unit, the period, place and "
    "scope it applies to, and the source, keeping the source's own wording for the number. Prefer primary "
    "sources: agencies, journals, official reports. If a figure is not found, say so plainly instead of "
    "approximating. No preamble, no general background unless the query asks for it, at most 350 words.")


def compose_search_answer(answer_content, search_triplet, top_links):
    """What the analyst reads: the sourced claims first - each supported sentence
    with its sources - then the numbered sources, then the search model's own
    summary. One search should yield a citable figure."""
    answer = (answer_content or "").strip()
    links = list(top_links or [])
    index = {l.get("link"): i + 1 for i, l in enumerate(links)}
    claims, seen = [], set()
    for t in (search_triplet or []):
        for seg in (t.get("segments") or []):
            text = (seg.get("text") or "").strip()
            if not text or text in seen:
                continue
            seen.add(text)
            refs = sorted({index[l.get("link")] for l in (seg.get("links") or []) if l.get("link") in index})
            claims.append(f"- {text} " + "".join(f"[{r}]" for r in refs))
    parts = []
    if claims:
        parts.append("SOURCED CLAIMS (each sentence with the sources behind it):\n" + "\n".join(claims[:40]))
    if links:
        parts.append("SOURCES:\n" + "\n".join(f"[{i + 1}] {l.get('title') or 'Link'} - {l.get('link')}" for i, l in enumerate(links[:15])))
    parts.append("SUMMARY (the search model's own words):\n" + (answer if answer else "(nothing found)"))
    return "\n\n".join(parts)


class SmartSearchOrchestrator:
    """
    Simplified orchestrator that only uses Google AI (Gemini) for search.
    All Selenium-specific functionality has been removed.
    """
    
    def __init__(self, prompt_manager=None, log_and_call_manager=None, output_manager=None, 
                 chain_id=None, messages=None, api_keys=None):
        self.prompt_manager = prompt_manager
        self.log_and_call_manager = log_and_call_manager
        self.output_manager = output_manager
        self.chain_id = chain_id
        self.messages = messages
        self.api_keys = api_keys or {}
        
        # Initialize GeminiSearch on demand
        self.gemini_search = None

    def perform_query(self, prompt_manager, log_and_call_manager, output_manager, chain_id, messages):
        """
        Perform a search query using Google AI (Gemini) with native search capabilities.
        """
        links = None
        
        try:
            # Initialize GeminiSearch when needed
            if not self.gemini_search:
                self.gemini_search = GeminiSearch(api_keys=self.api_keys)
            
            result, links = self.gemini_search(prompt_manager, log_and_call_manager, 
                                              output_manager, chain_id, messages)
        except Exception as e:
            # LOUDLY. This except used to convert the failure into the result
            # string and nothing else - the LLM call never ran, so nothing
            # reached the run log, and no logger call meant nothing reached
            # the journal either. A production import failure lived here
            # invisibly, its only witness a FINDINGS string inside the
            # Investigator's context. The result string is still returned
            # unchanged: delv-e reads it as findings and retries the search,
            # which is exactly the recovery observed live.
            logger.exception("Gemini search failed; returning the error as "
                             "the search result so the caller can retry or "
                             "proceed without it.")
            result = f"Error with Gemini search: {str(e)}"
            output_manager.display_error(result, chain_id=chain_id)
        
        return result, links
    
    def __call__(self, prompt_manager, log_and_call_manager, output_manager, chain_id, messages):
        """
        Make the orchestrator callable, delegating to perform_query.
        """
        return self.perform_query(prompt_manager, log_and_call_manager, output_manager, chain_id, messages)


class _SearchStream:
    """Routes the search's streamed answer into the open search element.

    GeminiSearch opens a 'google_ai_search' tool-call block, then delegates to
    the provider - which streams the answer through print_wrapper WITHOUT
    thought=True. The front end closes any open block on data.text
    (finishToolCall fires) and appends the raw markdown loose to the pane, so
    the summary landed OUTSIDE the very element announcing it. Same failure
    shape, same cure as the bridge's _Collapsed: for the duration of the model
    call, every token is forced onto the thought channel, which the front end
    routes into the current block's thoughts-container and parses as markdown
    once the block closes.

    The provider's interior 'Thinking' announcement is suppressed rather than
    forwarded: a new tool_call would close the search block and steal the
    stream. Suppression is safe here - unlike the case _Collapsed's docstring
    warns about - because a thought-capable container is already open: the
    search block itself, which the front end gives the .thinking treatment.
    Everything else (send_html_content for the SERP pills, display_error,
    silent-mode capture) passes through untouched.
    """

    def __init__(self, om):
        self._om = om

    def print_wrapper(self, message, end="\n", flush=False, chain_id=None,
                      thought=False):
        return self._om.print_wrapper(message, end=end, flush=flush,
                                      chain_id=chain_id, thought=True)

    def display_tool_info(self, action, action_input, chain_id=None):
        if action == "Thinking":
            return None
        return self._om.display_tool_info(action, action_input,
                                          chain_id=chain_id)

    def __getattr__(self, name):
        return getattr(self._om, name)


class GeminiSearch:
    """
    Unified Gemini-powered search that delegates to the integrated gemini_models.llm_stream
    via ModelManager. This removes the direct genai.Client usage, preserving logging,
    token counting, config, and HTML search preview behavior.
    """
    
    def __init__(self, api_keys=None):
        # Keep agent name to match LLM_CONFIG.json and ModelManager routing
        self.agent = 'Google Search Executor'
        self.api_keys = api_keys or {}

    def _extract_search_query(self, messages):
        """
        Preserve existing behavior: take the last user message, strip quotes,
        and format a single-turn search prompt that encourages tool invocation.
        """
        query = messages[-1]['content']
        search_query = re.sub('\'|"', '', query).strip()
        return f"Search Internet for: {search_query}"

    def _dedupe_links(self, search_triplet):
        """
        search_triplet is a list of dicts emitted by gemini_models.llm_stream when tools are used:
        [
          {"query": "...", "result": "...", "links": [{"title": "...", "link": "https://..."}, ...]},
          ...
        ]
        """
        seen = set()
        links_out = []
        if not search_triplet:
            return links_out
            
        for t in search_triplet:
            for lnk in (t.get("links") or []):
                url = lnk.get("link")
                if url and url not in seen:
                    seen.add(url)
                    # Normalize keys just in case
                    links_out.append({
                        "title": lnk.get("title") or "Link",
                        "link": url
                    })
        return links_out

    def __call__(self, prompt_manager, log_and_call_manager, output_manager, chain_id, messages):
        """
        Delegates to ModelManager.llm_stream with tools=[{'name': 'google_search'}].
        gemini_models.llm_stream will:
          - stream answer text to output_manager
          - push Google Search HTML (SERP preview) via output_manager.send_html_content(...)
          - return (answer_content, search_triplet, ...token/logging metrics...)
        We repackage into (answer, top_links) to preserve the original interface.
        """
        from bambooai.models import ModelManager

        # Build the single-turn search message
        search_query = self._extract_search_query(messages)
        output_manager.display_tool_info('google_ai_search', search_query, chain_id)

        # The research instruction (2026-09-07): specific figures with their scope and source,
        # each number in the source's own words, no essay. The search model used to write
        # 5-8K characters of unsourced prose, and a determined analyst searched nine times
        # for one citable number.
        gemini_messages = [{"role": "system", "content": SEARCH_INSTRUCTION},
                           {"role": "user", "content": search_query}]

        models = ModelManager(log_and_call_manager.user_id, api_keys=self.api_keys)

        # IMPORTANT: tools flag ensures gemini_models config attaches GoogleSearch + UrlContext
        # The wrapper applies to the MODEL CALL only: the search block above
        # went to the real output manager, and the summary now streams into
        # it as thoughts instead of landing loose in the pane as text.
        answer_content, search_triplet = models.llm_stream(
            prompt_manager,
            log_and_call_manager,
            _SearchStream(output_manager),
            gemini_messages,
            agent=self.agent,
            chain_id=chain_id,
            tools=[{"name": "google_search"}]
        )

        # Extract and dedupe links from the structured tool response
        top_links = self._dedupe_links(search_triplet)

        return compose_search_answer(answer_content, search_triplet, top_links), top_links