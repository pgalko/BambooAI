"""The Web Search seat (docs/OSS_DESIGN.md D28): the analyst's SEARCH is answered by the model on this seat, which
searches the web and names its sources. The seat's provider decides how the search is run:

  openrouter   OpenRouter's web search tool, with any model it carries. The seat names its search engine
               (`search_engine`; perplexity where it names none): an entry of the configuration's `search_engines`
               with what one search costs and the tool's parameters, which go to OpenRouter as written.
  gemini       Google's own search, with a Gemini model.

Either way the analyst reads the same digest: the sentences that carry a source, the numbered sources, the figures
given without one, the search model's own words. Two guards (2026-11-23): a reply given without a search is asked for
once more and then not passed on; and where the sources are the links the model writes - OpenRouter's route; Google
ties each sentence to its pages itself - a figure counts as sourced only in a sentence that links a page the search
returned, and the sources are the pages the answer links: a search returns more pages than an answer uses.

The digest's two lists - the claims and the sources - are read back by the analyst's side (analyst/sources.py, which
names their headings): a page keeps one number along a path, so the seat is told the pages numbered before (`known`).

    python -m bambooai.web_search "a question"      runs the seat once and says what it found and what it cost
"""
import os
import re

from analyst.sources import CLAIMS_HEAD, SOURCES_HEAD, listed, numbers, same as _same, site
from logger_config import get_logger
logger = get_logger("bambooai.web_search")      # by name: run as a module this is __main__, which the logger takes for the orchestrator

SEAT = "Web Search"
SEAT_BEFORE = "Google Search Executor"      # the seat's name until 2.9: a configuration written then is still read
KEYS = {"openrouter": "OPENROUTER_API_KEY", "gemini": "GEMINI_API_KEY"}      # the providers that search, and the key of each
DEFAULT_ENGINE = "perplexity"
RESULTS = 5                                 # the pages one search returns
SEARCHES = 3                                # the searches the model may run for one SEARCH

SEARCH_INSTRUCTION = (
    "You are a research assistant. Answer the query with the specific facts it asks for - figures, rates, "
    "dates, names - not an essay. For every figure give the value with its unit, the period, place and "
    "scope it applies to, and the source, keeping the source's own wording for the number. Prefer primary "
    "sources: agencies, journals, official reports. If a figure is not found, say so plainly instead of "
    "approximating. No preamble, no general background unless the query asks for it, at most 350 words.")
# where the sources are the links the model writes: every figure in a sentence that links its page
WITH_LINKS = (
    "Search the web at once, before you write anything, and give nothing from memory. Put each figure in a sentence of its own "
    "and end that sentence with a markdown link to the page the figure comes from - [the site's name](the "
    "page's address) - with the address as the search returned it.")
AGAIN = "No web search was run for the reply before this one. Run one now, and answer from what it returns."

UNSOURCED_HEAD = "WITHOUT A SOURCE (the search model named no page for these figures: do not cite them):"
SUMMARY_HEAD = "SUMMARY (the search model's own words):"
NO_SEARCH_LINE = "no search was run"
NO_SEARCH = (f"({NO_SEARCH_LINE}: the search model answered without searching the web, so nothing it said is passed "
             f"on. Search again in other words, or state plainly what was not found.)")


# ------------------------------------------------------------------------------------------------ the seat
def seat_of(config):
    """The seat in this configuration: its name - 'Web Search', or the name it had until 2.9 where a configuration
    written then carries that - and its details; (None, {}) where the configuration has neither."""
    seats = {a.get("agent"): a.get("details") or {} for a in (config or {}).get("agent_configs", [])}
    for name in (SEAT, SEAT_BEFORE):
        if name in seats:
            return name, seats[name]
    return None, {}


def engine_of(config, details):
    """The search engine of a seat on OpenRouter: its name and its entry in the configuration's `search_engines` -
    `per_search`, what one search costs in dollars, and `parameters`, the web search tool's, sent as written."""
    name = details.get("search_engine") or DEFAULT_ENGINE
    entry = ((config or {}).get("search_engines") or {}).get(name)
    if not isinstance(entry, dict) or "per_search" not in entry:
        raise ValueError(f"the search engine {name!r} has no entry with a per_search price in the configuration's search_engines")
    return name, entry


def unavailable(config, api_keys=None):
    """Why this configuration cannot search the web, in a sentence; '' when it can. Search is on where the seat's
    provider has its key: no longer only with a Gemini key."""
    name, details = seat_of(config)
    if not name:
        return f"the configuration has no '{SEAT}' seat"
    provider = details.get("provider")
    if provider not in KEYS:
        return f"the {name} seat's provider is {provider!r}; web search runs on {' or '.join(KEYS)}"
    if not ((api_keys or {}).get(provider) or os.environ.get(KEYS[provider])):
        return f"{KEYS[provider]} is not set"
    if provider == "openrouter":
        try:
            engine_of(config, details)
        except ValueError as exc:
            return str(exc)
    return ""


# ----------------------------------------------------------------------------- sentences and the pages they link
_LINK = re.compile(r"\[([^\]\n]*)\]\(\s*(https?://(?:[^\s()]|\([^\s()]*\))+)\s*\)")      # [label](address); an address may hold one pair of brackets
_ADDRESS = re.compile(r"https?://[^\s<>\[\]()]+")
_MARK = re.compile("\ue000(\\d+)\ue001")                                                  # a link's place while a line is cut into sentences
_CITING = {"source", "sources", "see", "via", "per", "from", "ref", "reference", "references", "and", "link", "links"}
# a sentence's end set against a heading or bold words, with no space: where what the model wrote before its search - "I'll
# search for this." - runs into its answer (the second live search: it stood in the first finding)
_GLUED = re.compile(r"(?<=[.!?])(?=\*\*\w|#{1,6} )")
# where a sentence may end: after its full stop, or the quotation mark or bracket that closes it there, before a capital, a link, a bracket, a quotation
_END = re.compile("(?:(?<=[.!?])|(?<=[.!?][\"'\u201d)\\]]))\\s+(?=[A-Z\ue000(\\[\"'\u201c])")
# what a piece opens with when it opens with links: the links, the brackets around them, words such as 'Source:'
_LEAD = re.compile("(?:[\\s()\\[\\],;:.\u2013\u2014-]|\ue000\\d+\ue001|(?:%s)\\b)*" % "|".join(sorted(_CITING)), re.I)


def _cut(line):
    """A line's sentences. A sentence ends with a full stop, a question or an exclamation mark - and the quotation
    mark or bracket that closes it there - before a capital letter, a link, a bracket or a quotation mark: not before
    a digit, where 'approx. 5' would be cut; not after an ellipsis and not inside a quotation, which stays whole with
    the link that follows it (2026-11-23, the first live search: a source's words quoted with '...' in them had lost
    their first half)."""
    pieces, start = [], 0
    for end in _END.finditer(line):
        piece = line[start:end.start()]
        if piece.endswith("...") or piece.count('"') % 2 or piece.count("\u201c") > piece.count("\u201d"):
            continue
        pieces.append(piece)
        start = end.end()
    return pieces + [line[start:]]


def _sentences(answer):
    """The answer as (sentence, [(label, address)]) pairs: each line cut into its sentences (_cut); a list item is a
    line. The links are taken out of the text and returned beside it. The links a sentence is followed by - bare, in
    brackets, after a word such as 'Source:' - are its own, also where more follows them on the line; a link that
    opens the next sentence ('[the guide](...) says ...') is that sentence's."""
    out = []
    for line in (answer or "").splitlines():
        line = re.sub(r"^\s*(?:[-*+\u2022]|\d+[.)]|#+)\s+", "", line).strip()
        if not line:
            continue
        links = []

        def keep(label, address):
            links.append((label.strip(), address.rstrip(".,;:")))
            return f"\ue000{len(links) - 1}\ue001"
        line = _LINK.sub(lambda m: keep(m.group(1), m.group(2)), line)
        line = _ADDRESS.sub(lambda m: keep("", m.group(0)), line)
        pieces = []
        for piece in _cut(line):
            lead = _LEAD.match(piece).group(0) if pieces else ""
            if _MARK.search(lead) and not piece[len(lead):len(lead) + 1].islower():
                pieces[-1] += " " + lead.strip()
                piece = piece[len(lead):]
            if piece:
                pieces.append(piece)
        for piece in pieces:
            mine = [links[int(i)] for i in _MARK.findall(piece)]
            out.append((_text(piece, links), mine))
    return out


def _text(piece, links):
    """A sentence without its links: a link whose label is the site's name, a number or a word such as 'source' goes
    whole; any other leaves its label, which is part of the sentence. What is left of the brackets around it goes too."""
    def label(m):
        text, address = links[int(m.group(1))]
        host = _same(address).split("/", 1)[0]
        named = text.lower().removeprefix("www.")
        plain = not text or named == host or host.endswith("." + named) or text.isdigit() or named in _CITING or re.fullmatch(r"[\w-]+(\.[\w-]+)+", named)
        return "" if plain else text
    text = _MARK.sub(label, piece)
    text = re.sub(r"[(\[]\s*(?:[Ss]ources?:?)?[\s,;]*[)\]]", "", text)       # (), (Source: ), [ , ]
    text = re.sub(r"\s+(?:[Ss]ources?|[Rr]ef(?:erence)?s?)[:.]?\s*$", "", text)       # 'Source:' left at the end by its link
    text = re.sub(r"\s+([,;:!?]|\.(?!\.))", r"\1", re.sub(r"\s{2,}", " ", text))      # not before an ellipsis: it is the source's
    text = re.sub("\\s*[-\u2013\u2014]+([.!?]?)$", "\\1", text)                 # the dash a link at the end leaves: 'the figure - [site](address).'
    return text.strip(" -\u2013\u2014:")


def claims_from_links(answer, pages, known=()):
    """The claims of an answer whose sources are the links it writes (OpenRouter's route): (claims, cited, unsourced,
    summary). A sentence that links a page the search returned is a claim, with those pages. `cited` is the answer's
    sources: the pages it links, each once, in the order it first links them - a page the search returned and the
    answer does not link is not one (2026-11-23, the first live search: ten pages returned, five linked, ten listed).
    A sentence with a figure and no such link is unsourced - it had no link, or one to a page the search did not
    return. The summary is the answer with each link as its source's number - along the path: `known` are the pages
    numbered before -, '(no source)' where it has none; what the model wrote before its search starts a line of its own."""
    answer = _GLUED.sub("\n", answer or "")
    by = {_same(p.get("link")): p for p in pages or []}
    claims, cited, unsourced = [], [], []
    for text, links in _sentences(answer):
        found = []
        for _, address in links:
            page = by.get(_same(address))
            if page is not None and page not in found:
                found.append(page)
        if found:
            claims.append({"text": text, "links": found})
            cited += [page for page in found if page not in cited]
        elif re.search(r"\d", text):
            unsourced.append(text)
    number = {_same(link): n for link, n in numbers(cited, known).items()}

    def numbered(address):
        n = number.get(_same(address))
        return f"[{n}]" if n else "(no source)"
    summary = _LINK.sub(lambda m: numbered(m.group(2)), answer)
    summary = _ADDRESS.sub(lambda m: numbered(m.group(0)), summary)
    summary = re.sub(r"\(\s*((?:\[\d+\][\s,;]*)+|\(no source\))\s*\)", lambda m: m.group(1).strip(" ,;"), summary)      # ([1]) -> [1]
    return claims, cited, unsourced, summary


# ------------------------------------------------------------------------------------------------ the digest
def digest(answer, claims, sources, unsourced=(), known=()):
    """What the analyst reads, and SHOW SEARCH k re-opens: the sourced claims first - each sentence with the numbers of
    the sources behind it -, then the numbered sources, then any figure the search model gave no source for, then its
    own words. One search should yield a citable figure. A source's number is its number along the path (0337: each
    digest had numbered from 1, and [3] in a report was a page of each search): a page among `known`, those numbered
    before, keeps its number, a new one takes the next."""
    answer = (answer or "").strip()
    sources = list(sources or [])[:15]
    number = numbers(sources, known)
    lines, seen = [], set()
    for claim in claims or []:
        text = (claim.get("text") or "").strip()
        if not text or text in seen:
            continue
        seen.add(text)
        refs = sorted({number[l.get("link")] for l in (claim.get("links") or []) if l.get("link") in number})
        lines.append(f"- {text} " + "".join(f"[{r}]" for r in refs))
    parts = []
    if lines:
        parts.append(CLAIMS_HEAD + "\n" + "\n".join(lines[:40]))
    if sources:
        parts.append(SOURCES_HEAD + "\n" + "\n".join(f"[{number[s.get('link')]}] {s.get('title') or site(s.get('link'))} - {s.get('link')}"
                                                      for s in sorted(sources, key=lambda s: number[s.get("link")])))
    if unsourced:
        parts.append(UNSOURCED_HEAD + "\n" + "\n".join(f"- {text}" for text in list(unsourced)[:40]))
    parts.append(SUMMARY_HEAD + "\n" + (answer if answer else "(nothing found)"))
    return "\n\n".join(parts)


def peek(text):
    """The search row's short line in the pane: the first finding - the first sourced claim without its source
    marks, else the first line of the search model's own words - where it was the digest's heading (2026-11-23);
    'no search was run' for a search that ran none; of anything else its first line. A finding is shown as words: the
    row is plain text, and the marks of bold or of a heading stood in it as asterisks."""
    def words(line):
        return re.sub(r"\*+|`|^#+ ", "", line).strip()
    claims, summary = listed(text, CLAIMS_HEAD), listed(text, SUMMARY_HEAD)
    if claims:
        return words(re.sub(r"(?:\s*\[\d+\])+$", "", claims[0]))
    if summary:
        return words(re.sub(r"^[-*] ", "", summary[0]))
    first = next((ln.strip() for ln in (text or "").splitlines() if ln.strip()), "")
    return NO_SEARCH_LINE if first.startswith("(" + NO_SEARCH_LINE) else first


# ------------------------------------------------------------------------------------------------ the search
class _Quiet:
    """The output manager for the model call of a search. A provider that streams (Gemini) sends the answer as text;
    outside a turn's card the page appends text to the pane as it comes, and a search runs between two cards. So the
    answer goes out as thought tokens, which the page drops there, and the provider's own 'Thinking' notice is not
    forwarded; everything else - an error, for one - passes through."""

    def __init__(self, om):
        self._om = om

    def print_wrapper(self, message, end="\n", flush=False, chain_id=None, thought=False):
        return self._om.print_wrapper(message, end=end, flush=flush, chain_id=chain_id, thought=True)

    def display_tool_info(self, action, action_input, chain_id=None):
        if action == "Thinking":
            return None
        return self._om.display_tool_info(action, action_input, chain_id=chain_id)

    def __getattr__(self, name):
        return getattr(self._om, name)


class WebSearch:
    """The seat as the analyst's SEARCH calls it: the query in, the digest and its sources out."""

    def __init__(self, models=None, api_keys=None):
        self.models = models            # the host's model manager; one is made for the call where the host gave none
        self.api_keys = api_keys or {}

    def __call__(self, prompt_manager, log_and_call_manager, output_manager, chain_id, messages, known=()):
        """`known`: the pages the searches before this one on the path numbered (analyst.sources.along): the digest
        cites one of them by its number, and numbers a new page after them."""
        query = "Search Internet for: " + re.sub("'|\"", "", messages[-1]["content"]).strip()
        output_manager.display_tool_info("web_search", query, chain_id)
        try:
            return self._search(prompt_manager, log_and_call_manager, output_manager, chain_id, query, known)
        except Exception as exc:                                # noqa: BLE001
            # with its traceback: this except once turned a production import failure into a string only the analyst
            # saw. The string is still returned - the analyst reads it and searches again or goes on without
            logger.exception("Web search failed; the error is returned as the search's result")
            result = f"Web search failed: {exc}"
            output_manager.display_error(result, chain_id=chain_id)
            return result, None

    def _search(self, prompt_manager, log_and_call_manager, output_manager, chain_id, query, known=()):
        from bambooai.models import ModelManager, prompt_cache      # here, not above: the adapters import this module
        models = self.models or ModelManager(log_and_call_manager.user_id, api_keys=self.api_keys)
        seat, details = seat_of(models.config)
        provider = details.get("provider")
        if provider == "openrouter":
            engine, entry = engine_of(models.config, details)
            tool = {"name": "web_search", "engine": engine,
                    "parameters": {"max_results": RESULTS, "max_uses": SEARCHES, **(entry.get("parameters") or {"engine": engine})}}
            instruction = SEARCH_INSTRUCTION + " " + WITH_LINKS
            reasoning = [m for m, p in (models.get_model_properties() or {}).items() if (p or {}).get("capability") == "reasoning"]
        elif provider == "gemini":
            tool, instruction, reasoning = {"name": "google_search"}, SEARCH_INSTRUCTION, None      # Google's own search: the Gemini adapter knows it by this name
        else:
            raise ValueError(unavailable(models.config, self.api_keys) or f"the {seat} seat cannot search")

        def ask(text):
            """One call of the seat's model: its answer, what it found, the searches it ran. Logged as the Web Search
            seat's, whichever name the configuration has it under."""
            answer, found = models.llm_stream(prompt_manager, log_and_call_manager, _Quiet(output_manager),
                                              [{"role": "system", "content": instruction}, {"role": "user", "content": text}],
                                              agent=seat, chain_id=chain_id, tools=[tool], reasoning_models=reasoning, label=SEAT)
            return answer, found, int(prompt_cache.last_meta().get("search_requests") or 0)

        answer, found, searches = ask(query)
        if not searches:
            logger.warning("Web search: %s answered without searching; asked once more", seat)
            answer, found, searches = ask(query + "\n\n" + AGAIN)
        if not searches:
            return NO_SEARCH, []
        pages, seen = [], set()
        for link in (l for t in found for l in t.get("links") or []):
            if link.get("link") and link["link"] not in seen:
                seen.add(link["link"])
                pages.append({"title": link.get("title"), "link": link["link"]})      # the digest names a page with no title by its site
        if provider == "gemini":            # Google ties each sentence to its pages itself, and hands over those pages alone
            return digest(answer, [s for t in found for s in t.get("segments") or []], pages, known=known), pages
        claims, cited, unsourced, summary = claims_from_links(answer, pages, known)
        return digest(summary, claims, cited, unsourced, known), cited


# ------------------------------------------------------------------------------------------------ the check
def flat(config, level="cost"):
    """A configuration as the model layer reads it: a built one as it is; of the template, one level's seats."""
    seats = f"{level}_agent_configs"
    if "agent_configs" in config or seats not in config:
        return config
    return {**{k: v for k, v in config.items() if not k.endswith("_agent_configs")}, "agent_configs": config[seats]}


def check(question, config, raw=False):
    """Run the seat once on `question`, outside the app's accounts - no thread, the app's account settings left out of
    this process, the logs in a folder of their own that goes with it - and return (ok, lines): the seat, the searches
    run, the answer's sources and the pages the searches returned, the claims with a source and the figures without,
    the tokens, the cost with the search fees in it, the time, then the digest the analyst would read. `raw` prints
    OpenRouter's reply as it came."""
    import json
    import logging
    import tempfile
    from bambooai import log_manager
    from bambooai.models import ModelManager

    class Silent:
        def __getattr__(self, name):
            return lambda *a, **k: None

    seat, details = seat_of(config)
    lines = []
    why = unavailable(config)
    if why:
        return False, [f"Web search is off: {why}."]
    head = f"{seat} seat: {details.get('model')} on {details.get('provider')}"
    if details.get("provider") == "openrouter":
        engine, entry = engine_of(config, details)
        head += f", engine {engine} (${entry['per_search']:g} a search)"
    lines.append(head)
    adapter = logging.getLogger("bambooai.models.openrouter_models")      # says the reply as it came, at the debug level
    here, auth, level, shown = os.getcwd(), os.environ.pop("AUTH_MODE", None), adapter.level, logging.StreamHandler()
    if raw:
        adapter.addHandler(shown)
        adapter.setLevel(logging.DEBUG)
    try:
        models = ModelManager(config=config)
        with tempfile.TemporaryDirectory(prefix="bamboo_search_check_") as folder:
            os.chdir(folder)
            try:
                log = log_manager.LogAndCallManager(models.get_model_properties(), search_engines=config.get("search_engines"))
                text, sources = WebSearch(models=models)(None, log, Silent(), "search-check", [{"role": "user", "content": question}])
                try:
                    calls = json.load(open(log.run_log_file_path, encoding="utf-8"))
                except (OSError, ValueError):
                    calls = []
                log.logger.handlers[0].close()
            finally:
                os.chdir(here)
    finally:
        if auth is not None:
            os.environ["AUTH_MODE"] = auth
        if raw:
            adapter.removeHandler(shown)
            adapter.setLevel(level)
    searches = sum(int(c.get("search_requests") or 0) for c in calls)
    returned = sum(int(c.get("search_pages") or 0) for c in calls)      # OpenRouter's route says them; Google hands over the cited pages alone
    lines.append(f"Searches run: {searches}, in {len(calls)} call{'' if len(calls) == 1 else 's'} of the model")
    lines.append(f"Sources: {len(sources or [])}" + (f" (pages returned: {returned})" if returned else ""))
    lines.append(f"Claims with a source: {len(listed(text, CLAIMS_HEAD))}; figures without one: {len(listed(text, UNSOURCED_HEAD))}")
    lines.append(f"Tokens: {sum(c.get('prompt_tokens') or 0 for c in calls):,} in, {sum(c.get('completion_tokens') or 0 for c in calls):,} out")
    lines.append(f"Cost: ${sum(c.get('cost') or 0 for c in calls):.4f}, of it search fees ${sum(c.get('search_fee') or 0 for c in calls):.4f}")
    lines.append(f"Time: {sum(c.get('elapsed_time') or 0 for c in calls):.1f} s")
    answered = sorted({c["model_version"] for c in calls if c.get("model_version")})
    if answered:
        lines.append(f"Answered as: {', '.join(answered)}")
    lines += ["", "What the analyst reads:", "", text]
    if text.startswith("Web search failed"):
        verdict = "FAILED: the call did not go through (the line above says why)."
    elif text == NO_SEARCH:
        verdict = "NO SEARCH: the model answered twice without searching the web."
    elif not sources and not returned:
        verdict = "NO SOURCES: a search ran, but no page came back with the reply."
    elif not listed(text, CLAIMS_HEAD):
        verdict = "NO CLAIM WITH A SOURCE: pages came back, but no sentence of the answer links one of them."
    else:
        verdict = "OK: the search ran, its sources came back, and the answer ties figures to them."
    lines += ["", verdict]
    return verdict.startswith("OK"), lines


def main(argv=None):
    import argparse
    import json
    ap = argparse.ArgumentParser(prog="python -m bambooai.web_search", description="Run the Web Search seat once and say what it found and what it cost. "
                                 "Nothing is written to the usage table and nothing is charged to an account; the provider is paid as for any search.")
    ap.add_argument("question")
    ap.add_argument("--config", help="a configuration: LLM_CONFIG_template.json of this folder where it has one, else its LLM_CONFIG.json")
    ap.add_argument("--level", default="cost", help="of a template, the level whose seats are used: free, cost (the default), performance or max")
    ap.add_argument("--model", help="for this run, the seat on another model the configuration prices")
    ap.add_argument("--provider", help="... and that model's provider: openrouter or gemini")
    ap.add_argument("--engine", help="for this run, another of the configuration's search engines")
    ap.add_argument("--raw", action="store_true", help="also print OpenRouter's reply as it came")
    a = ap.parse_args(argv)
    if os.path.exists(".env"):                  # the working folder's keys, as `bambooai serve` reads them
        from bambooai.cli import load_env
        load_env(os.getcwd())
    path = a.config or next((p for p in ("LLM_CONFIG_template.json", "LLM_CONFIG.json") if os.path.exists(p)), None)
    if not path:
        print("No configuration here: run it in the folder that holds LLM_CONFIG_template.json or LLM_CONFIG.json, or name one with --config.")
        return 2
    with open(path, encoding="utf-8") as fh:
        config = flat(json.load(fh), a.level)
    other = {k: v for k, v in (("model", a.model), ("provider", a.provider), ("search_engine", a.engine)) if v}
    if other:                                   # the seat as this run wants it; the configuration's file is not touched
        name = seat_of(config)[0]
        config = dict(config, agent_configs=[dict(s, details=dict(s.get("details") or {}, **other)) if s.get("agent") == name else s
                                             for s in config.get("agent_configs", [])])
    ok, lines = check(a.question, config, raw=a.raw)
    print("\n".join(lines))
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
