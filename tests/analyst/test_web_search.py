"""The Web Search seat (0335-0337): the seat and when search is on; the claims an answer's links make and the pages
it cites, their numbers along a path, the digest and the pane's short line; the two guards; OpenRouter's request and what is read back from its
reply; what a search costs on the records - an engine's fee for every search, Google's with its free searches -;
Gemini's tokens as Google charges them; the template, the sample and the built configuration; the check command. No
network: the providers' clients are scripted."""
import contextlib
import io
import json
import os
import shutil
import sys
import tempfile
import types
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path[:0] = [HERE, ROOT, os.path.join(ROOT, "web_app")]
import _stubs  # noqa: F401,E402

WORK = tempfile.mkdtemp(prefix="websearch_")
os.chdir(WORK)
for _k in ("AUTH_MODE", "OPENROUTER_API_KEY", "GEMINI_API_KEY"):
    os.environ.pop(_k, None)

try:                                    # a machine with other Google packages and no google-genai: the stubs leave 'google' alone
    import google.genai                 # noqa: F401
except ImportError:
    for _name in ("google.genai", "google.genai.types", "google.genai.errors"):
        sys.modules[_name] = _stubs._Mod(_name)

from bambooai import log_manager, web_search as W                # noqa: E402
from bambooai.models import ModelManager, prompt_cache           # noqa: E402
from bambooai.models import openrouter_models as OR              # noqa: E402
from bambooai.models import gemini_models as G                   # noqa: E402

passed, failed = [], []


def check(name, cond, detail=""):
    (passed if cond else failed).append(name)
    print(("  ok   " if cond else "  FAIL ") + name + ("" if cond else f"  <- {detail}"))


TPL = json.load(open(os.path.join(ROOT, "web_app", "LLM_CONFIG_template.json"), encoding="utf-8"))
CFG = W.flat(TPL, "cost")
DEEPSEEK = "deepseek/deepseek-v4.1-flash-1017"
FAO = {"title": "Designing crop field trials", "link": "https://www.fao.org/agriculture/crops/field-trials"}
JOURNAL = {"title": "Repeated measures in plot trials", "link": "https://onlinelibrary.wiley.com/journal/agronomy"}
OTHER = {"title": "Notes on trial design", "link": "https://www.example.org/trial-design"}      # a page a search returns and no answer links


# ---------------------------------------------------------------------------------- the seat, and when search is on
levels = {lv: {a["agent"]: a["details"] for a in TPL[f"{lv}_agent_configs"]} for lv in ("free", "cost", "performance", "max")}
check("the template: each of its four levels seats Web Search on OpenRouter with DeepSeek V4.1 Flash, thinking off, its engine Perplexity; "
      "no level has a Google Search seat left - the Executor is this seat, the Summarizer ran nothing",
      all(s["Web Search"] == {"reasoning_effort": "none", "model": DEEPSEEK, "provider": "openrouter", "search_engine": "perplexity", "max_tokens": 8000, "temperature": 0}
          and not [n for n in s if n.startswith("Google Search")] for s in levels.values()), {lv: s.get("Web Search") for lv, s in levels.items()})
check("the template's search engines: Perplexity at $0.005 a search, Parallel in its fast mode at $0.001, each with the tool parameters it is asked with",
      TPL["search_engines"] == {"perplexity": {"per_search": 0.005, "parameters": {"engine": "perplexity"}},
                                "parallel": {"per_search": 0.001, "parameters": {"engine": "parallel", "mode": "fast"}}}, TPL.get("search_engines"))
check("gemini-flash-latest stays in the template with its price and its fee per search, for a seat put on Gemini",
      TPL["model_properties"]["gemini-flash-latest"].get("grounding_search_request") == 0.014 and "prompt_tokens" in TPL["model_properties"]["gemini-flash-latest"])
SAMPLE = json.load(open(os.path.join(ROOT, "LLM_CONFIG_sample.json"), encoding="utf-8"))
sample_seats = {a["agent"]: a["details"] for a in SAMPLE["agent_configs"]}
check("the sample configuration: the same seat, on a model it prices, and the same engines; no Google Search seat",
      sample_seats["Web Search"]["provider"] == "openrouter" and sample_seats["Web Search"]["search_engine"] == "perplexity"
      and sample_seats["Web Search"]["model"] in SAMPLE["model_properties"] and SAMPLE["search_engines"] == TPL["search_engines"]
      and not [n for n in sample_seats if n.startswith("Google Search")], sample_seats.get("Web Search"))

shutil.copy(os.path.join(ROOT, "web_app", "LLM_CONFIG_template.json"), "LLM_CONFIG_template.json")
import llm_config_builder                                         # noqa: E402
built_ok = llm_config_builder.build_user_config("u1", subscription_data={"model_tier": "managed"}, model_preference="max")
BUILT = json.load(open(os.path.join("config", "u1", "LLM_CONFIG.json"), encoding="utf-8")) if built_ok else {}
check("a built configuration carries the search engines beside the seats and the models (the builder had passed three named keys only)",
      BUILT.get("search_engines") == TPL["search_engines"] and W.seat_of(BUILT)[0] == "Web Search" and W.flat(BUILT, "cost") is BUILT, list(BUILT))

OLD = {"agent_configs": [{"agent": "Google Search Executor", "details": {"model": "gemini-flash-latest", "provider": "gemini", "reasoning_effort": "none"}}],
       "model_properties": {"gemini-flash-latest": TPL["model_properties"]["gemini-flash-latest"]}}
check("the seat's lookup: Web Search with its details; the name it had until 2.9, Google Search Executor, where a configuration written then carries that; (None, {}) with neither; "
      "of the template flat() takes one level's seats and leaves the rest",
      W.seat_of(CFG) == ("Web Search", levels["cost"]["Web Search"]) and W.seat_of(OLD)[0] == "Google Search Executor" and W.seat_of({"agent_configs": []}) == (None, {})
      and W.seat_of(None) == (None, {}) and W.flat(TPL, "max")["agent_configs"] == TPL["max_agent_configs"] and "cost_agent_configs" not in CFG and CFG["search_engines"] == TPL["search_engines"])


def cfg_with(**details):
    seat = dict(levels["cost"]["Web Search"], **details)
    return dict(CFG, agent_configs=[{"agent": "Web Search", "details": seat}])


with mock.patch.dict(os.environ, {"OPENROUTER_API_KEY": "k"}):
    on = [W.unavailable(CFG), W.unavailable(cfg_with(search_engine="parallel")), W.unavailable(cfg_with(search_engine=None))]
    engine_off = [W.unavailable(cfg_with(search_engine="exa")), W.unavailable(dict(CFG, search_engines={"perplexity": {"parameters": {}}})), W.unavailable(dict(CFG, search_engines=None))]
check("search is on where the seat's provider has its key: with an OpenRouter key and the template's seat - Perplexity, Parallel, or no engine named, which is Perplexity",
      on == ["", "", ""], on)
check("... off with the reason said: an engine the configuration has no entry for, an entry without a price, no engines at all",
      engine_off[0] == "the search engine 'exa' has no entry with a per_search price in the configuration's search_engines" and "'perplexity'" in engine_off[1] and "'perplexity'" in engine_off[2], engine_off)
with mock.patch.dict(os.environ, {"GEMINI_API_KEY": "g"}):
    with_gemini = [W.unavailable(OLD), W.unavailable(CFG)]
check("... off without the key of the seat's own provider - a Gemini key no longer turns it on for a seat on OpenRouter -; a key handed to the instance counts; "
      "a seat on Gemini is on with the Gemini key, as before; a seat on another provider is off; so is a configuration without the seat",
      W.unavailable(CFG) == "OPENROUTER_API_KEY is not set" and with_gemini == ["", "OPENROUTER_API_KEY is not set"] and W.unavailable(CFG, {"openrouter": "k"}) == ""
      and W.unavailable(OLD) == "GEMINI_API_KEY is not set" and W.unavailable(cfg_with(provider="vllm")) == "the Web Search seat's provider is 'vllm'; web search runs on openrouter or gemini"
      and W.unavailable({"agent_configs": []}) == "the configuration has no 'Web Search' seat", (W.unavailable(CFG), with_gemini, W.unavailable(cfg_with(provider="vllm"))))

from bambooai import cli                                          # noqa: E402
check("the self-hosted edition's .env: no key is said to turn search on, the line that turns it off is there, and no default names the old mode",
      "WEB_SEARCH_MODE" not in cli.DEFAULTS and "turns web search on" not in cli.ENV_TEMPLATE and "# WEB_SEARCH_MODE=off" in cli.ENV_TEMPLATE
      and "web search runs on the Web Search seat" in cli.ENV_TEMPLATE and "# GEMINI_API_KEY=\n" in cli.ENV_TEMPLATE)
import importlib.util as _ilu, glob as _glob
_adapters = "".join(open(f, encoding="utf-8").read() for f in _glob.glob(os.path.join(ROOT, "bambooai", "models", "*.py")))
check("the adapters' old tool loops are gone (0344): no module of the old search or of the questions a tool put, no adapter names them or keeps a list of functions to call, "
      "and the seat is made without arguments or with the keys",
      all(_ilu.find_spec(m) is None for m in ("bambooai.google_search", "bambooai.context_retrieval", "bambooai.models.gemini_models_openai"))
      and not any(w in _adapters for w in ("SmartSearchOrchestrator", "context_retrieval", "available_functions", "google_search_react_system", "consult_assistant"))
      and W.WebSearch().api_keys == {} and W.WebSearch(api_keys={"a": 1}).api_keys == {"a": 1})

# -------------------------------------------------------------------------- the claims an answer's links make
ANSWER = """- Regime B plots yielded 3.2 t/ha on loam in 2024 ([fao.org](https://www.fao.org/agriculture/crops/field-trials)).
- Soil type alone moves yield by 0.5-1.0 t/ha [wiley.com](https://onlinelibrary.wiley.com/journal/agronomy/). Seasons within a plot are repeated measures. [wiley.com](https://onlinelibrary.wiley.com/journal/agronomy)
- The trial ran over 3 seasons.
- According to [the FAO guide](https://fao.org/agriculture/crops/field-trials#design), 12 plots per regime is usual, approx. 40 in large trials.
- On clay a made-up page says 99% (https://example.org/not-returned).
No figure was found for sand."""
claims, cited, unsourced, summary = W.claims_from_links(ANSWER, [OTHER, JOURNAL, FAO])       # as a search returns them: more pages than the answer links, in its own order
check("a sentence that links a page the search returned is a claim, with that page: the link is taken out of its text - a site's name goes whole, a label that is part of the sentence stays -; "
      "a list item is a line, a line is cut into sentences after a full stop, and a link that follows its sentence's full stop belongs to that sentence",
      [(c["text"], [p["link"] for p in c["links"]]) for c in claims] == [
          ("Regime B plots yielded 3.2 t/ha on loam in 2024.", [FAO["link"]]),
          ("Soil type alone moves yield by 0.5-1.0 t/ha.", [JOURNAL["link"]]),
          ("Seasons within a plot are repeated measures.", [JOURNAL["link"]]),
          ("According to the FAO guide, 12 plots per regime is usual, approx. 40 in large trials.", [FAO["link"]])], claims)
check("two spellings of an address are one page: with or without 'www.', a closing slash, a fragment; a sentence is not cut before a digit ('approx. 40')",
      claims[1]["links"] == [JOURNAL] and claims[3]["links"] == [FAO] and len(claims) == 4)
check("a figure in a sentence with no link, or with a link to a page the search did not return, is without a source; a sentence with neither figure nor link is neither",
      unsourced == ["The trial ran over 3 seasons.", "On clay a made-up page says 99%."], unsourced)
check("the summary is the answer with each link as its source's number, '(no source)' where the page was not returned",
      summary.split("\n") == ["- Regime B plots yielded 3.2 t/ha on loam in 2024 [1].",
                              "- Soil type alone moves yield by 0.5-1.0 t/ha [2]. Seasons within a plot are repeated measures. [2]",
                              "- The trial ran over 3 seasons.",
                              "- According to [1], 12 plots per regime is usual, approx. 40 in large trials.",
                              "- On clay a made-up page says 99% (no source).",
                              "No figure was found for sand."], summary)
check("the answer's sources are the pages it links, each once, in the order it first links them - the numbers in its claims and its summary are theirs; "
      "a page the search returned and the answer does not link is not a source (0336: ten returned, five linked, ten had been listed)",
      cited == [FAO, JOURNAL] and W.claims_from_links(ANSWER, [FAO, JOURNAL])[1] == [FAO, JOURNAL] and W.claims_from_links("Sand held 2 t/ha.", [FAO, OTHER])[1] == [], cited)
c2, _, u2, s2 = W.claims_from_links("Yield rose 12% under regime B. Source: [1](https://www.fao.org/agriculture/crops/field-trials)\n"
                                 "See https://onlinelibrary.wiley.com/journal/agronomy for the plot as the unit (2 seasons each). "
                                 "Sand held 2.1 t/ha [FAO](https://www.fao.org/agriculture/crops/field-trials); clay 2.9 t/ha.", [FAO, JOURNAL])
check("'Source:' and a link after the sentence belong to it; an address written bare is a link",
      [(c["text"], [p["link"] for p in c["links"]]) for c in c2] == [("Yield rose 12% under regime B.", [FAO["link"]]),
                                                                     ("See for the plot as the unit (2 seasons each).", [JOURNAL["link"]]),
                                                                     ("Sand held 2.1 t/ha FAO; clay 2.9 t/ha.", [FAO["link"]])] and u2 == [], (c2, u2))
twice = W.claims_from_links(f"Regime A gave 3 t/ha [fao.org]({FAO['link']}) against 4 t/ha [wiley.com]({JOURNAL['link']}) and 5 t/ha a year on [fao.org]({FAO['link']}/).", [FAO, JOURNAL])[0]
check("a sentence that links two pages has both, each once however often it names it", len(twice) == 1 and twice[0]["links"] == [FAO, JOURNAL], twice)
c3, _, u3, s3 = W.claims_from_links("Regime C gave 4 t/ha [a](https://en.example.org/wiki/Yield_(crop)).\nNothing was found for 2025.", [{"title": "Yield", "link": "https://en.example.org/wiki/Yield_(crop)"}])
check("an address may hold a pair of brackets; with no pages returned every figure is without a source; an answer without figures or links has neither claims nor unsourced",
      [c["text"] for c in c3] == ["Regime C gave 4 t/ha a."] and u3 == ["Nothing was found for 2025."] and s3.startswith("Regime C gave 4 t/ha [1].")
      and W.claims_from_links(ANSWER, [])[0] == [] and len(W.claims_from_links(ANSWER, [])[2]) == 5 and W.claims_from_links("Nothing was found.", [FAO]) == ([], [], [], "Nothing was found.")
      and W.claims_from_links("", [FAO]) == ([], [], [], ""), (c3, u3, s3))

# a source's words quoted, and where a sentence's links stand (0336, from the first live search)
F_LINK, J_LINK = f"[fao.org]({FAO['link']})", f"[wiley.com]({JOURNAL['link']})"


def tied(answer):
    """An answer's claims as (sentence, its pages), and its figures without a source."""
    found, _, without, _ = W.claims_from_links(answer, [FAO, JOURNAL])
    return [(c["text"], c["links"]) for c in found], without


check("a quotation stays whole with the link that follows it: not cut at an ellipsis - a source's words quoted with '...' in them had lost their first half -, "
      "nor at a full stop inside it; the ellipsis stands as the source wrote it, and the dash before a link at the end goes with the link",
      tied(f'The guide: "Plots under regime B ... (12 per soil type)" \u2014 {F_LINK}.') == ([('The guide: "Plots under regime B ... (12 per soil type)".', [FAO])], [])
      and tied(f'The journal: "Regime B gave 3.2 t/ha in 2024. Regime A gave 2.9 t/ha." {J_LINK}') == ([('The journal: "Regime B gave 3.2 t/ha in 2024. Regime A gave 2.9 t/ha."', [JOURNAL])], [])
      and tied(f"Yield rose ... Then it fell to 2 t/ha - {F_LINK}") == ([("Yield rose ... Then it fell to 2 t/ha", [FAO])], []),
      (tied(f'The guide: "Plots under regime B ... (12 per soil type)" \u2014 {F_LINK}.'), tied(f"Yield rose ... Then it fell to 2 t/ha - {F_LINK}")))
check("... in typographic marks too; a sentence ends with the quotation mark that closes it after its full stop, and what follows the link there is the next sentence - without a source",
      tied(f"It says \u201cPlots differ. Soil type moves yield by 0.5 t/ha.\u201d {F_LINK} Then 5 plots more.") == ([("It says \u201cPlots differ. Soil type moves yield by 0.5 t/ha.\u201d", [FAO])], ["Then 5 plots more."])
      and tied(f'One: 3 t/ha {F_LINK}. "Two: 4 t/ha." {J_LINK} Three: 5 t/ha.') == ([("One: 3 t/ha.", [FAO]), ('"Two: 4 t/ha."', [JOURNAL])], ["Three: 5 t/ha."]),
      tied(f'One: 3 t/ha {F_LINK}. "Two: 4 t/ha." {J_LINK} Three: 5 t/ha.'))
check("the links a sentence is followed by are its own, also where more follows them on the line: in brackets after its full stop, bare, after 'Source:' - "
      "each sentence has its page, not the next one's",
      tied(f"Loam gave 3 t/ha. ({F_LINK}) Clay gave 2 t/ha. ({J_LINK}) Sand gave 1 t/ha.") == ([("Loam gave 3 t/ha.", [FAO]), ("Clay gave 2 t/ha.", [JOURNAL])], ["Sand gave 1 t/ha."])
      and tied(f"Loam gave 3 t/ha. {F_LINK} Clay gave 2 t/ha. Source: {J_LINK}") == ([("Loam gave 3 t/ha.", [FAO]), ("Clay gave 2 t/ha.", [JOURNAL])], []),
      tied(f"Loam gave 3 t/ha. ({F_LINK}) Clay gave 2 t/ha. ({J_LINK}) Sand gave 1 t/ha."))
check("... a link that opens the next sentence is that sentence's: the one before it links nothing; so is the link a line opens with, whatever follows it",
      tied(f"Loam gave 3 t/ha. {F_LINK} says clay gave 2 t/ha.") == ([("says clay gave 2 t/ha.", [FAO])], ["Loam gave 3 t/ha."])
      and tied(f"{F_LINK} gives 3 t/ha for loam. Clay gave 2 t/ha.") == ([("gives 3 t/ha for loam.", [FAO])], ["Clay gave 2 t/ha."])
      and tied(f"Sand held 2 t/ha.\n{F_LINK}: Loam gave 3 t/ha.") == ([("Loam gave 3 t/ha.", [FAO])], ["Sand held 2 t/ha."]),
      (tied(f"Loam gave 3 t/ha. {F_LINK} says clay gave 2 t/ha."), tied(f"Sand held 2 t/ha.\n{F_LINK}: Loam gave 3 t/ha.")))

# ---------------------------------------------------------------------------------- the digest and the short line
TIED = [{"text": "Soil type alone moves yield by 0.5-1.0 t/ha.", "links": [FAO]}, {"text": "The plot is the experimental unit.", "links": [JOURNAL, FAO]},
        {"text": "Soil type alone moves yield by 0.5-1.0 t/ha.", "links": [JOURNAL]}, {"text": " ", "links": [FAO]}]
BEFORE = ("SOURCED CLAIMS (each sentence with the sources behind it):\n"
          "- Soil type alone moves yield by 0.5-1.0 t/ha. [1]\n"
          "- The plot is the experimental unit. [1][2]\n\n"
          "SOURCES:\n"
          "[1] Designing crop field trials - https://www.fao.org/agriculture/crops/field-trials\n"
          "[2] Repeated measures in plot trials - https://onlinelibrary.wiley.com/journal/agronomy\n\n"
          "SUMMARY (the search model's own words):\n"
          "Compare regimes within soil type.")
check("the digest of claims tied to their sources - Google's - is what it was before 0335, to the letter: the claims once each with their sources' numbers, the numbered sources, the summary",
      W.digest(" Compare regimes within soil type. ", TIED, [FAO, JOURNAL]) == BEFORE, W.digest(" Compare regimes within soil type. ", TIED, [FAO, JOURNAL]))
d_links = W.digest(summary, claims, cited, unsourced)
check("the figures without a source stand between the sources and the summary, under a heading that says not to cite them; a digest with nothing found says so",
      d_links.split("\n\n")[2] == W.UNSOURCED_HEAD + "\n- The trial ran over 3 seasons.\n- On clay a made-up page says 99%." and d_links.split("\n\n")[3].startswith(W.SUMMARY_HEAD + "\n- Regime B")
      and "do not cite them" in W.UNSOURCED_HEAD and W.digest("", [], []) == W.SUMMARY_HEAD + "\n(nothing found)", d_links)
check("listed(): the lines a digest has under a heading, without their list marks; none under a heading it does not have",
      W.listed(d_links, W.CLAIMS_HEAD)[0] == "Regime B plots yielded 3.2 t/ha on loam in 2024. [1]" and len(W.listed(d_links, W.CLAIMS_HEAD)) == 4
      and W.listed(d_links, W.UNSOURCED_HEAD) == unsourced and W.listed(BEFORE, W.UNSOURCED_HEAD) == [] and W.listed(BEFORE, W.SUMMARY_HEAD) == ["Compare regimes within soil type."])
check("the pane's short line is the first finding - the first sourced claim without its source marks -, not the digest's heading; with no claim, the first line of the summary; "
      "'no search was run' for a search that ran none; of anything else its first line",
      W.peek(BEFORE) == "Soil type alone moves yield by 0.5-1.0 t/ha." and W.peek(d_links) == "Regime B plots yielded 3.2 t/ha on loam in 2024."
      and W.peek(W.digest("- Nothing was found for sand.\nSecond line.", [], [])) == "Nothing was found for sand." and W.peek(W.NO_SEARCH) == "no search was run"
      and W.peek("(web search is not enabled)") == "(web search is not enabled)" and W.peek("Web search failed: boom\nmore") == "Web search failed: boom" and W.peek("") == "",
      (W.peek(BEFORE), W.peek(d_links), W.peek(W.NO_SEARCH)))

# a page's number along the path (0337): the digest is told the pages numbered before
from analyst import sources as on_path                            # noqa: E402
KNOWN = [{"n": 1, "title": "Notes on trial design", "link": OTHER["link"]}, {"n": 2, "title": "Repeated measures in plot trials", "link": JOURNAL["link"] + "/"}]
c_k, cited_k, u_k, s_k = W.claims_from_links(ANSWER, [OTHER, JOURNAL, FAO], KNOWN)
d_known = W.digest(s_k, c_k, cited_k, u_k, KNOWN)
check("a page's number is its number along the path: one the searches before numbered keeps it - under either spelling of its address -, a new page takes the next; "
      "the claims' marks, the summary's and the list are those numbers, the list in their order (0337: each digest numbered from 1, and [3] in a report was a page of each search)",
      W.listed(d_known, W.CLAIMS_HEAD)[:2] == ["Regime B plots yielded 3.2 t/ha on loam in 2024. [3]", "Soil type alone moves yield by 0.5-1.0 t/ha. [2]"]
      and W.listed(d_known, W.SOURCES_HEAD) == [f"[2] {JOURNAL['title']} - {JOURNAL['link']}", f"[3] {FAO['title']} - {FAO['link']}"]
      and s_k.split("\n")[:2] == ["- Regime B plots yielded 3.2 t/ha on loam in 2024 [3].", "- Soil type alone moves yield by 0.5-1.0 t/ha [2]. Seasons within a plot are repeated measures. [2]"]
      and [(p["n"], p["link"]) for p in on_path.along([d_links, W.digest(s_k, c_k, cited_k, u_k, on_path.along([d_links]))])] == [(1, FAO["link"]), (2, JOURNAL["link"])]
      and W.digest(summary, claims, cited, unsourced, known=()) == d_links, d_known)
check("the digest's two lists are the analyst's side's to read back: their headings and the reader of a list are its own (analyst/sources.py), and it reads this digest's pages as numbered",
      W.CLAIMS_HEAD is on_path.CLAIMS_HEAD and W.SOURCES_HEAD is on_path.SOURCES_HEAD and W.listed is on_path.listed
      and on_path.pages(d_known) == [{"n": 2, "title": JOURNAL["title"], "link": JOURNAL["link"]}, {"n": 3, "title": FAO["title"], "link": FAO["link"]}], on_path.pages(d_known))
glued = f"I'll search for this.**Yield on loam:** 3.2 t/ha in 2024 - {F_LINK}\n\n**Clay:** 2.9 t/ha. {J_LINK}"
c_g, _, u_g, s_g = W.claims_from_links(glued, [FAO, JOURNAL])
check("what the model wrote before its search - set against its answer without a space - starts a line of its own: it is in no finding, and the row's short line is the finding, "
      "as words - the marks of bold stood in it as asterisks (0337, the second live search)",
      [c["text"] for c in c_g] == ["**Yield on loam:** 3.2 t/ha in 2024", "**Clay:** 2.9 t/ha."] and u_g == [] and s_g.split("\n")[:2] == ["I'll search for this.", "**Yield on loam:** 3.2 t/ha in 2024 - [1]"]
      and W.peek(W.digest(s_g, c_g, [FAO, JOURNAL], u_g)) == "Yield on loam: 3.2 t/ha in 2024"
      and W.peek(W.digest("## Yield\n- **Nothing** was found for `sand`.", [], [])) == "Yield" and "at once, before you write anything" in W.WITH_LINKS,
      ([c["text"] for c in c_g], s_g, W.peek(W.digest(s_g, c_g, [FAO, JOURNAL], u_g))))


# --------------------------------------------------------------------------------- the seat over a scripted model
class Out:
    def __init__(self): self.tools, self.errors, self.printed = [], [], []
    def display_tool_info(self, action, text, chain_id=None): self.tools.append((action, text, chain_id))
    def display_error(self, text, chain_id=None): self.errors.append(text)
    def print_wrapper(self, message, end="\n", flush=False, chain_id=None, thought=False): self.printed.append((message, thought))
    def display_system_messages(self, *a, **k): pass


class Models:
    """The model manager as the seat uses it: each reply is (answer, found, the searches run) or an exception."""
    def __init__(self, config, *replies): self.config, self.replies, self.calls = config, list(replies), []
    def get_model_properties(self): return self.config.get("model_properties", {})

    def llm_stream(self, prompt_manager, log, om, messages, agent=None, chain_id=None, tools=None, reasoning_models=None, label=None):
        self.calls.append({"messages": messages, "agent": agent, "chain": chain_id, "tools": tools, "reasoning": reasoning_models, "label": label, "om": om})
        reply = self.replies.pop(0)
        if isinstance(reply, Exception):
            raise reply
        answer, found, searches = reply
        prompt_cache.reset()
        prompt_cache.record_meta(search_requests=searches)
        om.print_wrapper(answer)                      # as a provider that streams sends it: text
        return answer, found


def ask(models, question="yield of 'regime B' on \"loam\"", **more):
    out = Out()
    text, sources = W.WebSearch(models=models)("prompts", "log", out, "c1", [{"role": "user", "content": question}], **more)
    return text, sources, out


FOUND = [{"query": "q", "result": ANSWER, "links": [OTHER, FAO, JOURNAL, dict(FAO)]}]
m = Models(CFG, (ANSWER, FOUND, 2))
text, sources, out = ask(m)
call = m.calls[0]
check("OpenRouter's route: one call of the seat's model - logged as Web Search - with the web search tool: the engine by its name, and as the tool's parameters five pages a search, "
      "three searches at most, and the engine's own as the configuration writes them",
      len(m.calls) == 1 and (call["agent"], call["label"], call["chain"]) == ("Web Search", "Web Search", "c1")
      and call["tools"] == [{"name": "web_search", "engine": "perplexity", "parameters": {"max_results": 5, "max_uses": 3, "engine": "perplexity"}}], call["tools"])
check("... the instruction asks for a search first, nothing from memory, and a link to its page at the end of every sentence with a figure; the question goes without its quotes; "
      "the seat's effort is honoured - the reasoning models are named to the adapter",
      call["messages"][0] == {"role": "system", "content": W.SEARCH_INSTRUCTION + " " + W.WITH_LINKS} and call["messages"][1] == {"role": "user", "content": "Search Internet for: yield of regime B on loam"}
      and "markdown link" in W.WITH_LINKS and "nothing from memory" in W.WITH_LINKS and DEEPSEEK in call["reasoning"] and "gemini-flash-latest" in call["reasoning"], call["messages"])
check("... what comes back is the digest of the links' claims and the pages the answer links, each once - the pane's pills; a page the search returned and the answer left is not among them",
      text == d_links and sources == [FAO, JOURNAL] and out.errors == [] and out.tools == [("web_search", "Search Internet for: yield of regime B on loam", "c1")], (text, sources))
check("... the answer a provider streams goes out as thought tokens, which the page drops between two cards - as text it would be appended to the pane",
      out.printed == [(ANSWER, True)] and isinstance(call["om"], W._Quiet), out.printed)
text_k, sources_k, _ = ask(Models(CFG, (ANSWER, FOUND, 2)), known=KNOWN)
check("... told the pages the path's searches numbered before, the seat's digest cites by those numbers and numbers a new page after them; its pills are the pages this answer links",
      text_k == d_known and sources_k == [FAO, JOURNAL], text_k)
m = Models(cfg_with(search_engine="parallel"), (ANSWER, FOUND, 1))
ask(m)
check("the seat on Parallel: the tool names it, in its fast mode - the parameters are the configuration's, sent as written",
      m.calls[0]["tools"] == [{"name": "web_search", "engine": "parallel", "parameters": {"max_results": 5, "max_uses": 3, "engine": "parallel", "mode": "fast"}}], m.calls[0]["tools"])
m = Models(dict(CFG, search_engines={"perplexity": {"per_search": 0.005}}), (ANSWER, FOUND, 1))
ask(m)
check("an engine's entry without parameters: the engine by its name", m.calls[0]["tools"][0]["parameters"] == {"max_results": 5, "max_uses": 3, "engine": "perplexity"}, m.calls[0]["tools"])
m = Models(cfg_with(search_engine=None), (ANSWER, FOUND, 1))
ask(m)
check("a seat that names no engine asks Perplexity", m.calls[0]["tools"][0]["engine"] == "perplexity" and m.calls[0]["tools"][0]["parameters"]["engine"] == "perplexity", m.calls[0]["tools"])

# the first guard: no answer without a search
m = Models(CFG, ("From memory: 3.2 t/ha.", [{"query": "q", "result": "x", "links": []}], 0), (ANSWER, FOUND, 1))
text, sources, out = ask(m)
check("a reply given without a search is not passed on: the model is asked once more, told that no search was run - and that reply, which searched, is the one read",
      len(m.calls) == 2 and m.calls[1]["messages"][1]["content"] == "Search Internet for: yield of regime B on loam\n\n" + W.AGAIN and m.calls[1]["messages"][0] == m.calls[0]["messages"][0]
      and text == d_links and sources == [FAO, JOURNAL] and "From memory" not in text, (len(m.calls), text[:80]))
m = Models(CFG, ("From memory: 3.2 t/ha.", [], 0), ("Still from memory: 3.2 t/ha.", [], 0), (ANSWER, FOUND, 1))
text, sources, out = ask(m)
check("... twice without a search: the analyst reads that no search was run and nothing of what the model said; no source, no third call, and the row's short line says it",
      text == W.NO_SEARCH and sources == [] and len(m.calls) == 2 and "memory" not in text and W.peek(text) == "no search was run" and text.startswith("(no search was run:") and out.errors == [], (text, len(m.calls)))

# Gemini's route: called as it was, its claims tied by Google
SEGMENTS = [{"text": "Soil type alone moves yield by 0.5-1.0 t/ha.", "links": [FAO]}, {"text": "The plot is the experimental unit.", "links": [JOURNAL, FAO]}]
G_FOUND = [{"query": "q1", "result": "r", "links": [FAO], "segments": SEGMENTS[:1]}, {"query": "q2", "result": "r", "links": [JOURNAL, FAO], "segments": SEGMENTS[1:]}]
m = Models(OLD, ("Compare regimes within soil type. Regime B gave 3.2 t/ha in 2024.", G_FOUND, 2))
text, sources, out = ask(m)
call = m.calls[0]
check("Gemini's route, from a configuration that names the seat as before: Google's search asked for as it was - the instruction without the links' sentence, no reasoning models named -, "
      "on the seat by its old name, logged as Web Search",
      len(m.calls) == 1 and call["tools"] == [{"name": "google_search"}] and call["messages"][0]["content"] == W.SEARCH_INSTRUCTION and call["reasoning"] is None
      and (call["agent"], call["label"]) == ("Google Search Executor", "Web Search"), call)
check("... the digest is Google's tied claims, the sources once each, the model's words as they came - a figure Google tied to no page is not marked: that route is as it was",
      text == BEFORE.replace("Compare regimes within soil type.", "Compare regimes within soil type. Regime B gave 3.2 t/ha in 2024.") and sources == [FAO, JOURNAL] and W.UNSOURCED_HEAD not in text, text)
m = Models(OLD, ("From memory.", [], 0), ("From memory again.", [], 0))
text, sources, out = ask(m)
check("... the first guard holds on Gemini's route too: twice without a search, and nothing is passed on", text == W.NO_SEARCH and sources == [] and len(m.calls) == 2, text)
text_g, sources_g, _ = ask(Models(OLD, ("Compare regimes within soil type.", G_FOUND, 2)), known=[{"n": 4, "title": "x", "link": JOURNAL["link"]}])
check("... and Google's pages are numbered along the path too: the one found before keeps its number, the other takes the next",
      W.listed(text_g, W.CLAIMS_HEAD) == ["Soil type alone moves yield by 0.5-1.0 t/ha. [5]", "The plot is the experimental unit. [4][5]"]
      and W.listed(text_g, W.SOURCES_HEAD) == [f"[4] {JOURNAL['title']} - {JOURNAL['link']}", f"[5] {FAO['title']} - {FAO['link']}"] and sources_g == [FAO, JOURNAL], text_g)

m = Models(CFG, RuntimeError("the provider said 402"))
text, sources, out = ask(m)
check("a call that fails: the error is the search's result - the analyst reads it and goes on - and it is shown", text == "Web search failed: the provider said 402" and sources is None and out.errors == [text], (text, out.errors))
text, sources, out = ask(Models(cfg_with(provider="vllm")))
check("a seat on a provider that cannot search says so, without a call", text == "Web search failed: the Web Search seat's provider is 'vllm'; web search runs on openrouter or gemini" and sources is None, text)
text, sources, out = ask(Models(cfg_with(search_engine="exa")))
check("a seat whose engine the configuration does not price does not search: a search at no price would be charged to no one", "search engine 'exa' has no entry with a per_search price" in text, text)


# ------------------------------------------------------------------------------------ OpenRouter: the request
class Client:
    def __init__(self, *replies): self.replies, self.bodies = list(replies), []
    chat = property(lambda self: self)
    completions = property(lambda self: self)

    def create(self, **body):
        self.bodies.append(body)
        self.accounts = os.environ.get("AUTH_MODE")              # the app's account setting as the request is made
        return self.replies.pop(0) if len(self.replies) > 1 else self.replies[0]


def cite(page, **more):
    return {"type": "url_citation", "url_citation": dict({"url": page["link"], "title": page["title"], "content": "an excerpt [...] another", "start_index": 10, "end_index": 40}, **more)}


REPLY = {"id": "gen-1", "provider": "DeepSeek",
         "choices": [{"finish_reason": "stop", "message": {"role": "assistant", "content": "  " + ANSWER + "\n", "annotations": [
             cite(OTHER), cite(FAO), {"type": "url_citation", "url": JOURNAL["link"], "title": ""}, cite(FAO), {"type": "file_citation", "url": "https://files.example.org/x"}, "not an annotation"]}}],
         "usage": {"prompt_tokens": 14210, "completion_tokens": 512, "total_tokens": 14722, "prompt_tokens_details": {"cached_tokens": 4000}, "server_tool_use": {"web_search_requests": 2}}}
TOOL = {"name": "web_search", "engine": "perplexity", "parameters": {"max_results": 5, "max_uses": 3, "engine": "perplexity"}}
MESSAGES = [{"role": "system", "content": "instruction"}, {"role": "user", "content": "Search Internet for: yield"}]


def or_search(reply, tool=TOOL, effort="none", routing=None, model=DEEPSEEK):
    client = Client(reply)
    props = TPL["model_properties"][DEEPSEEK]
    OR.set_model_routing(routing)
    OR.set_reasoning_style(props.get("reasoning_style"))
    OR.set_reasoning_efforts(props.get("reasoning_efforts"))
    OR.set_model_properties(props)
    prompt_cache.reset()
    with mock.patch.object(OR, "init", return_value=client):
        got = OR.llm_stream(None, None, None, "c1", MESSAGES, model, 0, 8000, tools=[tool], reasoning_models=[DEEPSEEK], reasoning_effort=effort)
    return got, client.bodies, prompt_cache.last(), prompt_cache.last_meta()


got, bodies, cached, meta = or_search(REPLY, routing={"order": ["deepseek"], "allow_fallbacks": True})
body = bodies[0]
check("OpenRouter: the seat's tool makes one request, not streamed - the model, the messages, the token limit - with the web search tool and the seat's parameters as written",
      len(bodies) == 1 and body["model"] == DEEPSEEK and body["messages"] == MESSAGES and body["max_tokens"] == 8000 and "stream" not in body and "tools" not in body
      and body["extra_body"]["tools"] == [{"type": "openrouter:web_search", "parameters": {"max_results": 5, "max_uses": 3, "engine": "perplexity"}}], body)
check("... only a host that takes tools is asked - one that ignores them answers from memory -, with the model's own routing; the usage is asked for; the seat's effort, none, is sent",
      body["extra_body"]["provider"] == {"require_parameters": True, "order": ["deepseek"], "allow_fallbacks": True} and body["extra_body"]["usage"] == {"include": True}
      and body["extra_body"]["reasoning"] == {"effort": "none"}, body["extra_body"])
answer, found, messages, t_in, t_out, t_all, elapsed, speed = got
check("... read back: the answer whole; the pages its annotations cite, each once, in order - the address under url_citation or on the annotation itself, a title as it came, none for a page without one, "
      "what is no citation of a page left out; the question that was asked",
      answer == ANSWER and found[0] == {"query": "Search Internet for: yield", "result": ANSWER, "links": [OTHER, FAO, {"title": "", "link": JOURNAL["link"]}]} and messages is MESSAGES, found[0])
check("... the searches run, from the usage, with their engine: the record the dispatcher bills from, and said to the seat and the log - with the pages they returned; "
      "the tokens as reported, the cached part of the prompt for its price",
      found[1] == {"__meta__": {"search_billed": 2, "search_engine": "perplexity"}} and (meta.get("search_requests"), meta.get("search_engine"), meta.get("search_pages")) == (2, "perplexity", 3)
      and (t_in, t_out, t_all) == (14210, 512, 14722) and cached == (4000, 0) and meta.get("reasoning_effort") == "none" and meta.get("max_tokens") == 8000 and "truncated" not in meta, (found[1], meta, cached))
def _refused(tools):
    try:
        OR.llm_stream(None, None, None, "c", [], "m", 0, 100, tools)
    except ValueError as e:
        return "Web Search seat" in str(e)
    return False
check("a tool that is not the seat's is no search, and the adapter takes no other (0344: the old function tools went the stream's way)",
      OR._web_search_tool([{"type": "function", "function": {"name": "web_search"}}, {"name": "google_search"}]) is None
      and OR._web_search_tool(None) is None and OR._web_search_tool([{"name": "x"}, TOOL]) is TOOL and _refused([{"type": "function", "function": {"name": "web_search"}}]))


class SDKReply:
    """A reply as the SDK hands it: an object whose model_dump() is the dict."""
    def __init__(self, data): self._data = data
    def model_dump(self): return self._data


responses_shape = {"choices": [{"finish_reason": "length", "message": {"content": "Cut", "annotations": [cite(JOURNAL)]}}],
                   "usage": {"input_tokens": 900, "output_tokens": 8000, "server_tool_use_details": {"web_search_requests": 3}}}
got, bodies, cached, meta = or_search(SDKReply(responses_shape), tool=dict(TOOL, engine="parallel", parameters={"engine": "parallel", "mode": "fast"}), effort="high")
check("the SDK's reply object is read as the dict it dumps; the usage in the Responses API's names - input_tokens, output_tokens, server_tool_use_details - counts the same; "
      "an answer cut at the token limit is marked; another engine and effort go as given",
      got[0] == "Cut" and got[1][1] == {"__meta__": {"search_billed": 3, "search_engine": "parallel"}} and got[3:6] == (900, 8000, 8900) and meta.get("truncated") is True
      and bodies[0]["extra_body"]["tools"][0]["parameters"] == {"engine": "parallel", "mode": "fast"} and bodies[0]["extra_body"]["reasoning"] == {"effort": "high"}
      and bodies[0]["extra_body"]["provider"] == {"require_parameters": True}, (got[:2], got[3:6], meta, bodies[0]["extra_body"]))
silent = {"choices": [{"message": {"content": "With pages", "annotations": [cite(FAO)]}}], "usage": {"prompt_tokens": 10, "completion_tokens": 5}}
nothing = {"choices": [{"message": {"content": "From memory"}}], "usage": {"prompt_tokens": 10, "completion_tokens": 5, "server_tool_use": {"web_search_requests": 0}}}
empty = {"choices": [], "usage": None}
check("a usage that does not say how many searches ran: one where pages came back, none where none did; a reply that says none ran, or holds nothing, is none - and no page",
      or_search(silent)[0][1][1]["__meta__"]["search_billed"] == 1 and or_search({"choices": [{"message": {"content": "x"}}]})[0][1][1]["__meta__"]["search_billed"] == 0
      and or_search(nothing)[0][1] == [{"query": "Search Internet for: yield", "result": "From memory", "links": []}, {"__meta__": {"search_billed": 0, "search_engine": "perplexity"}}]
      and or_search(empty)[0][0] == "" and or_search(empty)[0][3:6] == (0, 0, 0) and OR._searches_run({"server_tool_use": {}}) is None and OR._cited_pages(None) == []
      and or_search(nothing)[3].get("search_pages") == 0 and or_search(silent)[3].get("search_pages") == 1)


# -------------------------------------------------------- end to end: the seat, the dispatcher, the adapter, the log
class Store:
    """The hosted store as the log manager asks it: the usage rows written, the quota's answers - and whether it was asked."""
    def __init__(self, quota=None): self.rows, self.asked, self.quota = [], [], quota
    def is_available(self): return True
    def check_grounding_search_quota(self, n): self.asked.append(n); return self.quota
    def insert_usage_with_chain(self, data, thread_id): self.rows.append(dict(data)); return True


def logged(user):
    return json.load(open(os.path.join(WORK, "logs", user, "bambooai_run_log.json"), encoding="utf-8"))


def run_seat(config, user, reply, store=None):
    """The seat through the real dispatcher and log manager, OpenRouter's client scripted: (text, sources, the log manager, the client's requests)."""
    models = ModelManager(config=config)
    log = log_manager.LogAndCallManager(models.get_model_properties(), user_id=user, thread_id="t1", search_engines=config.get("search_engines"))
    log.supabase_client = store
    client = Client(*reply) if isinstance(reply, list) else Client(reply)
    with mock.patch.object(OR, "init", return_value=client), mock.patch.dict(os.environ, {"AUTH_MODE": "single"} if store else {}):
        text, sources = W.WebSearch(models=models)(None, log, Out(), "c9", [{"role": "user", "content": "yield of regime B on loam"}])
    return text, sources, log, client.bodies


store = Store()
text, sources, log, bodies = run_seat(CFG, "u_perplexity", REPLY, store)
entry = logged("u_perplexity")[-1]
rates = TPL["model_properties"][DEEPSEEK]
tokens_cost = (10210 * rates["prompt_tokens"] + 4000 * rates["cache_read_tokens"] + 512 * rates["completion_tokens"]) / 1000
check("the seat through the dispatcher, the adapter and the log, on the template's own seat: the request carries the seat's model, its routing and the tool; "
      "the digest comes back with its two sources - the pages the answer links, of the three the searches returned -, a page with no title named by its site (0340)",
      len(bodies) == 1 and bodies[0]["model"] == DEEPSEEK and bodies[0]["extra_body"]["provider"]["order"] == ["deepseek"] and bodies[0]["extra_body"]["tools"][0]["type"] == "openrouter:web_search"
      and bodies[0]["extra_body"]["reasoning"] == {"effort": "none"} and bodies[0]["messages"][1]["content"] == "Search Internet for: yield of regime B on loam"
      and text.startswith(W.CLAIMS_HEAD + "\n- Regime B plots yielded 3.2 t/ha on loam in 2024. [1]") and [s["link"] for s in sources] == [FAO["link"], JOURNAL["link"]]
      and OTHER["link"] not in text and W.listed(text, W.SOURCES_HEAD) == [f"[1] {FAO['title']} - {FAO['link']}", f"[2] onlinelibrary.wiley.com - {JOURNAL['link']}"], (bodies, text[:200]))
check("... the call's record: the Web Search seat's, two searches on Perplexity at $0.005 each on top of the tokens - the cached part of the prompt at its own price -, "
      "the three pages they returned, the billing note not in the messages kept",
      (entry["agent"], entry["model"], entry["search_requests"], entry["search_engine"], entry["search_pages"]) == ("Web Search", DEEPSEEK, 2, "perplexity", 3) and abs(entry["search_fee"] - 0.01) < 1e-12
      and abs(entry["cost"] - (tokens_cost + 0.01)) < 1e-12 and (entry["prompt_tokens"], entry["completion_tokens"], entry["cached_tokens"]) == (14210, 512, 4000)
      and "__billing_meta__" not in json.dumps(entry["messages"]) and "grounding_fee" not in entry and abs(log.token_summary["c9"]["web_search_cost"] - 0.01) < 1e-12, entry)
check("... the usage row carries the fee, and Google's free searches were not asked about: an engine's search is charged every time",
      len(store.rows) == 1 and store.rows[0]["agent"] == "Web Search" and store.rows[0]["search_fee"] == 0.01 and abs(store.rows[0]["cost"] - round(tokens_cost + 0.01, 4)) < 1e-9 and store.asked == [], (store.rows, store.asked))
text, sources, log, bodies = run_seat(cfg_with(search_engine="parallel"), "u_parallel", REPLY, Store())
entry = logged("u_parallel")[-1]
check("... on Parallel: its fast mode asked for, two searches at $0.001 each",
      bodies[0]["extra_body"]["tools"][0]["parameters"] == {"max_results": 5, "max_uses": 3, "engine": "parallel", "mode": "fast"} and entry["search_engine"] == "parallel" and abs(entry["search_fee"] - 0.002) < 1e-12, entry)
text, sources, log, bodies = run_seat(CFG, "u_twice", [nothing, REPLY])
calls = logged("u_twice")
check("... a reply without a search and the one asked again are two calls on the record, the first with no search and no fee, and the digest is the second's",
      len(bodies) == 2 and [(c["search_requests"], c["search_fee"]) for c in calls] == [(0, 0.0), (2, 0.01)] and bodies[1]["messages"][1]["content"].endswith(W.AGAIN) and text.startswith(W.CLAIMS_HEAD), calls)

# Google's fee: as it was, with the month's free searches
G_COSTS = {"gemini-flash-latest": TPL["model_properties"]["gemini-flash-latest"]}
SIDE = [{"role": "system", "content": '__billing_meta__: {"search_billed": 3, "model": "gemini-flash-latest"}'}, {"role": "user", "content": "q"}]


def google_fee(quota, user):
    store = Store(quota)
    log = log_manager.LogAndCallManager(G_COSTS, user_id=user, thread_id="t1", search_engines=TPL["search_engines"])
    log.supabase_client = store
    with mock.patch.dict(os.environ, {"AUTH_MODE": "single"}):
        log.write_to_log("Web Search", "c1", "2026-11-23 00:00:00", "gemini-flash-latest", SIDE, "reply", 0, 0, 0, 1.0, 1.0)
    return store.rows[0]["search_fee"], store.asked, logged(user)[-1]


free, paid, unknown = google_fee({"should_charge": False}, "g_free"), google_fee({"should_charge": True}, "g_paid"), google_fee(None, "g_none")
check("Google's searches, which name no engine, are charged as before: the store is asked with their number - it counts the month's free ones -; not charged while it says so, "
      "else the model's fee for each, also where the store has no answer",
      free[:2] == (0.0, [3]) and paid[:2] == (0.042, [3]) and unknown[:2] == (0.042, [3]) and free[2]["search_requests"] == 3 and "search_engine" not in free[2], (free[:2], paid[:2], unknown[:2]))


# -------------------------------------------------------------------- Gemini: the tokens as Google charges them
def usage(**counts):
    return types.SimpleNamespace(**dict({"prompt_token_count": 200, "candidates_token_count": 300, "thoughts_token_count": 150, "tool_use_prompt_token_count": 5000, "total_token_count": 5650}, **counts))


check("Gemini's usage as Google charges it: the answer and the thinking are output; the prompt is input, and what the tools handed the model only where the URL tool read a page - "
      "a search's retrieved results are not charged as tokens",
      G.billed_tokens(usage()) == (200, 450) and G.billed_tokens(usage(), pages_read=True) == (5200, 450) and G.billed_tokens(usage(thoughts_token_count=None, tool_use_prompt_token_count=None), True) == (200, 300)
      and G.billed_tokens(types.SimpleNamespace()) == (0, 0), (G.billed_tokens(usage()), G.billed_tokens(usage(), True)))


def page(status):
    return types.SimpleNamespace(retrieved_url="https://www.fao.org/x", url_retrieval_status=status)


def g_chunk(text=None, usage_=None, grounding=None, pages=None, version=None, thought=None):
    parts = [types.SimpleNamespace(text=text, thought=thought, function_call=None)] if text else None
    candidate = types.SimpleNamespace(content=types.SimpleNamespace(parts=parts) if parts else None, finish_reason=None, grounding_metadata=grounding,
                                      url_context_metadata=types.SimpleNamespace(url_metadata=pages) if pages is not None else None)
    return types.SimpleNamespace(candidates=[candidate], usage_metadata=usage_, model_version=version)


check("the URL tool read a page: an entry retrieved, or one that does not say; not one that failed, not an empty list, not a chunk without the tool's record",
      G._pages_read(g_chunk("x", pages=[page("UrlRetrievalStatus.URL_RETRIEVAL_STATUS_SUCCESS")])) and G._pages_read(g_chunk("x", pages=[page("URL_RETRIEVAL_STATUS_ERROR"), page(None)]))
      and not G._pages_read(g_chunk("x", pages=[page("URL_RETRIEVAL_STATUS_ERROR")])) and not G._pages_read(g_chunk("x", pages=[])) and not G._pages_read(g_chunk("x"))
      and not G._pages_read(types.SimpleNamespace(candidates=None)))

GROUNDING = types.SimpleNamespace(grounding_chunks=[types.SimpleNamespace(web=types.SimpleNamespace(title="fao.org", uri="https://vertexaisearch.example/redirect/1"))],
                                  web_search_queries=["yield by soil type", "plot as unit"], search_entry_point=None,
                                  grounding_supports=[types.SimpleNamespace(segment=types.SimpleNamespace(text="Soil type alone moves yield by 0.5-1.0 t/ha."), grounding_chunk_indices=[0])])


class GeminiClient:
    def __init__(self, chunks): self.chunks, self.models, self.asked = chunks, self, []
    def count_tokens(self, model=None, contents=None): return types.SimpleNamespace(total_tokens=7)
    def generate_content_stream(self, model=None, contents=None, config=None): self.asked.append(model); return iter(self.chunks)


def gemini_search(chunks):
    """The adapter's stream over scripted chunks; the SDK's request types and error class stood in for, so the same runs with and without the SDK."""
    client, out = GeminiClient(chunks), Out()
    prompt_cache.reset()
    with mock.patch.object(G, "init", return_value=client), mock.patch.object(G, "types", _stubs._Mod("types")), \
         mock.patch.object(G, "genai_errors", types.SimpleNamespace(APIError=ConnectionError)):
        got = G.llm_stream(None, None, out, "c1", [{"role": "system", "content": "i"}, {"role": "user", "content": "q"}], "gemini-flash-latest", 0, 8000, tools=[{"name": "google_search"}])
    return got, prompt_cache.last_meta(), client


thinking = g_chunk("Weighing the sources.", thought=True)
got, meta, client = gemini_search([thinking, g_chunk("Soil type alone moves yield ", version="gemini-3.8-flash-001"),
                                   g_chunk("by 0.5-1.0 t/ha.", usage_=usage(), grounding=GROUNDING, version="gemini-3.8-flash-001")])
check("a Gemini search: the tokens counted are the prompt in, the answer and the thinking out - the thinking had cost nothing on the records, the retrieved results are not tokens",
      got[0] == "Soil type alone moves yield by 0.5-1.0 t/ha." and got[3:6] == (200, 450, 650) and client.asked == ["gemini-flash-latest"], got[3:6])
check("... the searches run - two here - go to the billing record as before, and are said to the seat; the model that answered under the alias is said to the log",
      got[1][-1]["__meta__"]["search_billed"] == 2 and meta.get("search_requests") == 2 and meta.get("model_version") == "gemini-3.8-flash-001"
      and got[1][0]["segments"] == [{"text": "Soil type alone moves yield by 0.5-1.0 t/ha.", "links": [{"title": "fao.org", "link": "https://vertexaisearch.example/redirect/1"}]}], (got[1], meta))
got, meta, client = gemini_search([g_chunk("Read the page.", pages=[page("URL_RETRIEVAL_STATUS_SUCCESS")]), g_chunk(" Done.", usage_=usage(), grounding=GROUNDING)])
check("... where the URL tool read a page, what the tools handed the model is input too", got[3:6] == (5200, 450, 5650) and meta.get("model_version") is None, got[3:6])
got, meta, client = gemini_search([g_chunk("From memory."), g_chunk(usage_=usage(tool_use_prompt_token_count=0, thoughts_token_count=0))])
check("... a Gemini reply without a search says so to the seat: no search, no triplet", meta.get("search_requests") == 0 and got[1][-1]["__meta__"]["search_billed"] == 0 and len(got[1]) == 1 and got[3:6] == (200, 300, 500), (meta, got[1]))


# ------------------------------------------------------------------------------------------ the check command
def run_check(reply, config=CFG, env=None, **more):
    here, client = os.getcwd(), Client(reply)
    with mock.patch.object(OR, "init", return_value=client), mock.patch.dict(os.environ, {"OPENROUTER_API_KEY": "k", "AUTH_MODE": "auth0"} if env is None else env):
        ok, lines = W.check("yield of regime B on loam", config, **more)
        kept = (os.getcwd() == here, os.environ.get("AUTH_MODE"), getattr(client, "accounts", "no request"))
    return ok, lines, kept


before = sorted(os.listdir(WORK))
ok, lines, kept = run_check(REPLY)
check("the check runs the seat once and says what happened: the seat with its engine and price, the searches and the calls, the answer's sources of the pages the searches returned, "
      "the claims with a source and the figures without, the tokens, the cost with the fees in it, then the digest, then that it went well",
      ok is True and lines[0] == f"Web Search seat: {DEEPSEEK} on openrouter, engine perplexity ($0.005 a search)" and lines[1] == "Searches run: 2, in 1 call of the model"
      and lines[2] == "Sources: 2 (pages returned: 3)" and lines[3] == "Claims with a source: 4; figures without one: 2" and lines[4] == "Tokens: 14,210 in, 512 out"
      and lines[5] == f"Cost: ${tokens_cost + 0.01:.4f}, of it search fees $0.0100" and lines[6].startswith("Time: ") and lines[7:10] == ["", "What the analyst reads:", ""]
      and lines[10].startswith(W.CLAIMS_HEAD) and lines[-1].startswith("OK: ") and lines[-2] == "", lines[:10] + lines[-2:])
check("... outside the app's accounts: the app's account setting is out of the process while the request is made and back after, the folder is the one it started in, and nothing is left in it",
      kept == (True, "auth0", None) and sorted(os.listdir(WORK)) == before, (kept, sorted(os.listdir(WORK)), before))
verdicts = [run_check(r)[:2] for r in (nothing, {"choices": [{"message": {"content": "A figure: 3 t/ha."}}], "usage": {"server_tool_use": {"web_search_requests": 1}}},
                                        {"choices": [{"message": {"content": "A figure: 3 t/ha.", "annotations": [cite(FAO)]}}], "usage": {"server_tool_use": {"web_search_requests": 1}}})]
check("... and says what went wrong: the model answered twice without searching; a search ran but no page came back with the reply; pages came back but no sentence links one",
      [ok for ok, _ in verdicts] == [False, False, False] and [ln[-1].split(":")[0] for _, ln in verdicts] == ["NO SEARCH", "NO SOURCES", "NO CLAIM WITH A SOURCE"]
      and verdicts[0][1][1] == "Searches run: 0, in 2 calls of the model" and [ln[2] for _, ln in verdicts] == ["Sources: 0", "Sources: 0", "Sources: 0 (pages returned: 1)"],
      [ln[-1] for _, ln in verdicts] + [ln[2] for _, ln in verdicts])
import logging                                                    # noqa: E402
adapter_log = logging.getLogger("bambooai.models.openrouter_models")
state0 = (adapter_log.level, list(adapter_log.handlers))
with contextlib.redirect_stderr(io.StringIO()) as as_it_came:
    ok_raw = run_check(REPLY, raw=True)[0]
with contextlib.redirect_stderr(io.StringIO()) as quiet:
    run_check(REPLY)
check("... asked for the reply as it came, it prints OpenRouter's own - the annotations, the usage - and leaves the adapter's log as it found it; not asked, it prints none of it",
      ok_raw is True and '"web_search_requests": 2' in as_it_came.getvalue() and '"url_citation"' in as_it_came.getvalue() and "the reply as it came" not in quiet.getvalue()
      and (adapter_log.level, list(adapter_log.handlers)) == state0, (as_it_came.getvalue()[:300], quiet.getvalue()[:200]))
ok, lines, kept = run_check(REPLY, env={})
check("... without the seat's key it says that search is off and why, and runs nothing", (ok, lines) == (False, ["Web search is off: OPENROUTER_API_KEY is not set."]), lines)
with mock.patch.object(OR, "init", side_effect=ValueError("no key")), mock.patch.object(OR, "TRANSPORT_ERRORS", (ConnectionError,)), mock.patch.dict(os.environ, {"OPENROUTER_API_KEY": "k"}):
    ok, lines = W.check("q", CFG)
check("... a call that does not go through is said as failed, with the reason in the lines", ok is False and lines[-1].startswith("FAILED: ") and "Web search failed: no key" in lines, lines[-3:])
shown = io.StringIO()
with mock.patch.object(OR, "init", return_value=Client(REPLY)), mock.patch.dict(os.environ, {"OPENROUTER_API_KEY": "k"}), contextlib.redirect_stdout(shown):
    code = W.main(["yield of regime B on loam", "--level", "max"])
    code_none = W.main(["q", "--config", os.path.join(WORK, "LLM_CONFIG_template.json"), "--level", "free"])
check("the command: in a folder with the template it runs the seat and exits 0 when it went well; --config names another configuration",
      (code, code_none) == (0, 0) and shown.getvalue().count("OK: the search ran") == 2 and "Web Search seat: " in shown.getvalue(), (code, code_none, shown.getvalue()[:200]))
by_level = json.loads(json.dumps(TPL))
next(a for a in by_level["max_agent_configs"] if a["agent"] == "Web Search")["details"]["search_engine"] = "parallel"
json.dump(by_level, open("by_level.json", "w", encoding="utf-8"))
shown = io.StringIO()
with mock.patch.dict(os.environ, {"OPENROUTER_API_KEY": "k"}), contextlib.redirect_stdout(shown):
    with mock.patch.object(OR, "init", return_value=Client(REPLY)):
        codes = [W.main(["q", "--config", "by_level.json", "--level", "max"]), W.main(["q", "--config", "by_level.json"])]
    with mock.patch.object(OR, "init", return_value=Client(nothing)):
        codes.append(W.main(["q", "--config", "by_level.json"]))
os.remove("by_level.json")
check("... of a template it runs the seat of the level named - cost where none is; it exits 1 when the search did not go well",
      codes == [0, 0, 1] and shown.getvalue().count("engine parallel ($0.001 a search)") == 1 and shown.getvalue().count("engine perplexity ($0.005 a search)") == 2
      and "NO SEARCH: " in shown.getvalue(), (codes, [ln for ln in shown.getvalue().split("\n") if "seat:" in ln]))
open(".env", "w", encoding="utf-8").write("# the working folder's keys\nOPENROUTER_API_KEY=from-the-folder\n")
with mock.patch.object(OR, "init", return_value=Client(REPLY)), mock.patch.dict(os.environ, {}), contextlib.redirect_stdout(io.StringIO()) as with_env:
    code = W.main(["yield of regime B on loam"])
    key_read = os.environ.get("OPENROUTER_API_KEY")
os.remove(".env")
check("... the working folder's .env is read for the keys, as `bambooai serve` reads it: the seat's key from there is enough",
      code == 0 and key_read == "from-the-folder" and "OK: the search ran" in with_env.getvalue() and "OPENROUTER_API_KEY" not in os.environ, (code, key_read, with_env.getvalue()[:200]))
# the seat as one run wants it: another engine, another model, Gemini - without touching the configuration
template_before = open("LLM_CONFIG_template.json", encoding="utf-8").read()
tried, ran_with, the_check = Client(REPLY), [], W.check
with mock.patch.object(OR, "init", return_value=tried), mock.patch.dict(os.environ, {"OPENROUTER_API_KEY": "k"}), contextlib.redirect_stdout(io.StringIO()) as other, \
     mock.patch.object(W, "check", lambda question, config, raw=False: (ran_with.append({a["agent"]: a["details"] for a in config["agent_configs"]}), the_check(question, config, raw=raw))[1]):
    codes = [W.main(["q", "--engine", "parallel"]), W.main(["q", "--model", "openai/gpt-5.6-luna-pro"]), W.main(["q", "--engine", "exa"]), W.main(["q", "--model", "gemini-flash-latest", "--provider", "gemini"])]
seats = [ln for ln in other.getvalue().split("\n") if ln.startswith("Web Search seat: ")]
check("the command runs the seat on another engine or another model for one run: Parallel at its price and in its fast mode, another OpenRouter model; an engine the configuration does not price "
      "is not run, nor a seat on Gemini without the Gemini key - each said; the configuration's file is as it was",
      codes == [0, 0, 1, 1] and seats[0] == f"Web Search seat: {DEEPSEEK} on openrouter, engine parallel ($0.001 a search)" and seats[1] == "Web Search seat: openai/gpt-5.6-luna-pro on openrouter, engine perplexity ($0.005 a search)"
      and len(seats) == 2 and "Web search is off: the search engine 'exa' has no entry" in other.getvalue() and "Web search is off: GEMINI_API_KEY is not set." in other.getvalue() and len(tried.bodies) == 2
      and tried.bodies[0]["extra_body"]["tools"][0]["parameters"] == {"max_results": 5, "max_uses": 3, "engine": "parallel", "mode": "fast"} and tried.bodies[1]["model"] == "openai/gpt-5.6-luna-pro"
      and open("LLM_CONFIG_template.json", encoding="utf-8").read() == template_before, (codes, seats, len(tried.bodies)))
check("... it is the search's seat that runs another way: the others are as the configuration has them",
      [r["Web Search"]["model"] for r in ran_with] == [DEEPSEEK, "openai/gpt-5.6-luna-pro", DEEPSEEK, "gemini-flash-latest"] and ran_with[3]["Web Search"]["provider"] == "gemini"
      and all({k: v for k, v in r.items() if k != "Web Search"} == {k: v for k, v in levels["cost"].items() if k != "Web Search"} for r in ran_with), [r["Web Search"] for r in ran_with])
# on a hosted box: the same check through tools/search_check.py, which takes the app's environment first
import importlib.util                                             # noqa: E402
sys.path.insert(0, os.path.join(ROOT, "tools"))
import memory_ask                                                 # noqa: E402
_spec = importlib.util.spec_from_file_location("search_check", os.path.join(ROOT, "tools", "search_check.py"))
search_check = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(search_check)
took = []
with mock.patch.object(OR, "init", return_value=Client(REPLY)), mock.patch.dict(os.environ, {}), contextlib.redirect_stdout(io.StringIO()) as on_box, \
     mock.patch.object(memory_ask, "environment", lambda: (took.append(os.getcwd()), os.environ.update({"OPENROUTER_API_KEY": "from-the-box", "AUTH_MODE": "auth0"}))):
    code = search_check.main(["yield of regime B on loam", "--level", "performance"])
check("the box's command takes the app's environment - its files, as its gunicorn loads them - and then runs the same check in the app's folder: the key comes from there",
      code == 0 and took == [WORK] and "OK: the search ran" in on_box.getvalue() and "Web Search seat: " in on_box.getvalue() and "OPENROUTER_API_KEY" not in os.environ, (code, took, on_box.getvalue()[:200]))
os.chdir(tempfile.mkdtemp(prefix="websearch_empty_"))
with contextlib.redirect_stdout(io.StringIO()) as nowhere:
    code = W.main(["q"])
os.chdir(WORK)
check("... in a folder without a configuration it says where to run it, and exits 2", code == 2 and "LLM_CONFIG_template.json" in nowhere.getvalue(), (code, nowhere.getvalue()))

# started as the README says, `python -m bambooai.web_search` (0343: as __main__ its logger was given the orchestrator's log file, which a laptop does not have)
import runpy
from unittest import mock as _mock
_out, _rc, _why = io.StringIO(), None, ""
with _mock.patch.dict(os.environ, {"APP_ROOT_DIR": os.path.join(tempfile.gettempdir(), "no-such-box")}), _mock.patch.object(sys, "argv", ["web_search", "--help"]), contextlib.redirect_stdout(_out):
    try:
        runpy.run_module("bambooai.web_search", run_name="__main__")
    except SystemExit as e:
        _rc = e.code
    except Exception as e:                # noqa: BLE001
        _why = repr(e)
check("the check runs as a module where no box is: its help comes, with no log file of the orchestrator's asked for", _rc == 0 and "--provider" in _out.getvalue(), (_rc, _why))

print(f"\n{len(passed)} passed, {len(failed)} failed")
sys.exit(1 if failed else 0)
