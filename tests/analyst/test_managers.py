"""What a run shows, and the prompts it is given outside the analyst's own. The output manager sends events the page
reads. It had carried the displays of the first version - a seat's start, a corrected script, a data model, a silent
mode, a flag for a mode that was always on - which nothing called, and the prompt list named 25 prompts that no longer
existed (0345). Beside it stood a second manager, for a terminal or a notebook, and a flag on the host to choose it:
no run of this version had ever shown its report that way, and the mode is gone (0346). This holds what is left: each
event the manager sends, a run from the question to the answer, that the manager defines no method the product does
not call and takes no argument a run does not hand it, that the prompt file, the loader's list and the host's reads
name the same prompts, and that the mode outside the page has left nothing behind."""
import inspect, json, os, re, sys, tempfile, tomllib
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path[:0] = [HERE, ROOT, os.path.join(ROOT, "delve")]
import _stubs  # noqa: F401,E402
from unittest import mock  # noqa: E402
os.environ["OPENAI_API_KEY"] = "x"; os.environ["EXECUTION_MODE"] = "local"; os.environ["SYNTHESIS_INFOGRAPHIC"] = "false"
import numpy as np, pandas as pd  # noqa: E402

passed, failed = [], []
def check(name, cond, detail=""):
    (passed if cond else failed).append(name); print(("  ok   " if cond else "  FAIL ") + name + ("" if cond else f"  <- {detail}"))


os.chdir(tempfile.mkdtemp())                           # storage/ and logs/ land here
from bambooai import bambooai as B  # noqa: E402
from bambooai.code_executor import CodeExecutor  # noqa: E402
from bambooai.web_output_manager import WebOutputManager  # noqa: E402
from bambooai.messages import prompts as PR  # noqa: E402

TRIAL = pd.DataFrame({"plot": range(1, 201), "regime": np.tile(["A", "B"], 100), "yield_t_ha": np.random.default_rng(1).normal(4.4, 0.3, 200).round(2)})
TRIAL.loc[TRIAL.regime == "B", "yield_t_ha"] += 0.5


def sent(om):
    out = []
    while not om.output_queue.empty():
        out.append(json.loads(om.output_queue.get()))
    return out


def kind(event):
    return event.get("type") or next(iter(event))


# ------------------------------------------------------------------------------------------ the manager's events
page = WebOutputManager()
page.print_wrapper("\nRegime B yields more.", chain_id="c1")
page.print_wrapper("\nOn loam too.", end="", chain_id="c1")
page.print_wrapper("\nAnd on clay.", end="", chain_id="c1")
page.print_wrapper("the gap is the same in each half", end="", chain_id="c1", thought=True)
page.print_wrapper("", end="", chain_id="c1")
check("what a model writes: a piece is a text event under its chain, a thought a thought event; a piece that opens with a line break right after a line "
      "break loses it, any other keeps it; an empty piece sends nothing",
      sent(page) == [{"text": "Regime B yields more.\n", "chain_id": "c1"}, {"text": "On loam too.", "chain_id": "c1"}, {"text": "\nAnd on clay.", "chain_id": "c1"},
                     {"thought": "the gap is the same in each half", "chain_id": "c1"}])

page.display_error(ValueError("no data is loaded"), chain_id="c1")
page.display_system_messages("Stopped.", chain_id="c1")
page.display_call_summary("Chain ID: c1\nTotal Tokens: 150\n")
page.send_synthesis_image("PHN2Zz4=", "image/svg+xml", chain_id="c1")
page.send_chain_id("t1", "c1", "d1", parent_chain_id=None)
check("the notices: an error, a system message, the call summary, the infographic and the chain's ids each go out as the event the page reads",
      sent(page) == [{"error": "no data is loaded", "chain_id": "c1"}, {"system_message": "Stopped."}, {"call_summary": "Chain ID: c1\nTotal Tokens: 150\n"},
                     {"type": "synthesis_image", "data": "PHN2Zz4=", "mime_type": "image/svg+xml", "chain_id": "c1"},
                     {"type": "id", "thread_id": "t1", "chain_id": "c1", "df_id": "d1", "parent_chain_id": None}])

nothing = page.get_user_input()
page.add_user_input("Which regime yields more?")
check("the question: read once from what the person sent, and nothing where nothing was sent", nothing is None and page.get_user_input() == "Which regime yields more?" and page.get_user_input() is None)

page.display_results(chain_id="c1", execution_mode="local", df_id="d1", df=TRIAL, api_client=None, plan="<div>the investigation</div>", code="print(1)", answer="## Answer\nB.",
                     simplified_answer="B is higher.", plot_jsons=[json.dumps({"type": "plot", "data": "{}", "id": "p1"})], code_exec_results="1", report_head={"title": "B against A"})
events = sent(page)
check("a result: the data's first page, the report's head, a tab each for the investigation, the script, the answer, the plain answer and the script's output, the "
      "figures, then the end - in that order, each under the chain",
      [kind(e) for e in events] == ["dataframe", "report_head", "plan", "code", "answer", "simplified_answer", "code_exec_results", "plot", "end"]
      and events[0]["data"]["df_id"] == "d1" and len(events[0]["data"]["rows"]) == 50 and events[1] == {"report_head": {"title": "B against A"}, "chain_id": "c1"}
      and events[4] == {"type": "answer", "data": "## Answer\nB.", "chain_id": "c1"} and all(e.get("chain_id") == "c1" for e in events if kind(e) != "plot"),
      [kind(e) for e in events])

figure = json.dumps({"type": "plot", "data": json.dumps({"data": [], "layout": {}}), "id": "p1"})
picture = json.dumps({"type": "plot", "format": "png", "data": "iVBORw0KGgo=", "id": "p1"})
as_it_is = page.optimize_plot_json(figure)
page.plot_size_threshold_mb = 0
with mock.patch.object(page, "plot_json_to_png", return_value=picture):
    over = page.optimize_plot_json(figure)
with mock.patch.object(page, "plot_json_to_png", return_value=None):
    not_drawn = page.optimize_plot_json(figure)
page.plot_size_threshold_mb = 2
check("a figure: under the size limit it is sent as it is; over it, as the picture made of it, and as it is where no picture could be made; one that is a "
      "picture already is sent as that",
      as_it_is == (figure, "json") and over == (picture, "png") and not_drawn == (figure, "json") and page.optimize_plot_json(picture) == (picture, "png"), (as_it_is, over, not_drawn))

# ------------------------------------------------------------------------------------------ a run
NOTE = "- Question as understood: q\n- Best estimate so far: none yet\n- Held fixed: -\n- Open doubts: -\n- Plan: p\n- Names: df"
SCRIPT = ["###NOTE###\n" + NOTE + "\n###ACTION###\nCELL\n```python\nm = df.groupby('regime')['yield_t_ha'].mean().round(2)\nprint('means', m.to_dict())\n```",
          "###NOTE###\n" + NOTE + "\n###ACTION###\nREPORT\n# B above A\n\n## Answer\nRegime B yields more than regime A [cell 1].\n"]
state = {"i": 0}


class FakeModels:
    """A scripted model layer in place of ModelManager: the analyst's two turns, and a plain reply to every other seat."""
    config = {"agent_configs": [{"agent": "Investigator", "details": {"model": "fake/model", "provider": "fake", "reasoning_effort": "low"}}], "model_properties": {}}
    def __init__(self, *a, **k): pass
    def get_model_properties(self): return {"fake/model": {"capability": "reasoning", "multimodal": "false", "prompt_tokens": 0.001, "completion_tokens": 0.002}}
    def get_model_name(self, agent): return ("fake/model", "fake")
    def llm_call(self, *a, **k): return "NO_CARD"

    def llm_stream(self, prompts, lacm, om, messages, agent=None, chain_id=None, reasoning_models=None, **kw):
        lacm.write_to_log(kw.get("label") or agent, chain_id, "2026-09-05 12:00:00", "fake/model", messages, "reply", 100, 50, 150, 1.0, 50.0)
        system, user = messages[0]["content"], messages[-1]["content"]
        if isinstance(user, str) and user.startswith("Rewrite the technical report"):
            return "In plain words: regime B yields more."
        if system.startswith("You are drawing the figures"):
            return "NONE"
        if system.startswith("You propose the questions to analyse next"):
            return "no"
        if system.startswith("You are given a task as an analyst will be given it"):
            return '{"cannot_place": []}'
        i = min(state["i"], len(SCRIPT) - 1); state["i"] += 1
        return SCRIPT[i]


B.ModelManager = FakeModels
try:
    host = B.BambooAI(df=TRIAL, df_id="d1", user_id="u1")
    handed, real = set(), host.output_manager.display_results
    host.output_manager.display_results = lambda **kw: (handed.update(kw), real(**kw))[1]
    host.output_manager.add_user_input("Does regime B yield more than regime A?")
    host.pd_agent_converse(thread_id="1001", chain_id=None)
    kinds = [kind(e) for e in sent(host.output_manager)]
    takes = set(inspect.signature(WebOutputManager.display_results).parameters) - {"self"}
    first = {k: kinds.index(k) for k in set(kinds)}
    check("a run: the question is read from what the person sent; the page is told the chain's ids, that a run has started and the data's first page before any turn; the "
          "investigation is sent as it grows; and the result goes out as the report's head, the script, the answer and the end, the run's end after them",
          type(host.output_manager) is WebOutputManager and all(k in first for k in ("id", "pane_run_start", "dataframe", "pane_turn_start", "plan", "report_head", "code", "answer", "pane_run_end"))
          and first["id"] < first["pane_run_start"] < first["dataframe"] < first["pane_turn_start"] < first["plan"] < first["report_head"] < first["answer"]
          and kinds.count("plan") > 1 and kinds[-1] in ("end", "pane_run_end", "call_summary"), kinds)
    check("the manager takes for a result what a run hands it and no more: no argument is left that no run passes (the first version's question, data model and "
          "review were such, 0345; the files a run made, kept for the manager outside the page, 0346)", handed == takes, (sorted(takes - handed), sorted(handed - takes)))
    host.pd_agent_converse(action="reset"); host.cleanup()
except Exception:                                              # noqa: BLE001
    import traceback
    check("a run: the checks ran", False, traceback.format_exc()[-1500:])

# ------------------------------------------------------------------------------------------ nothing idle, nothing left behind
def source(*parts):
    with open(os.path.join(ROOT, *parts), encoding="utf-8") as f:
        return f.read()


MANAGER = source("bambooai", "web_output_manager.py")
product = ""
for folder in ("bambooai", "web_app", "analyst", "delve", "tools"):
    for where, _dirs, names in os.walk(os.path.join(ROOT, folder)):
        if "vendor" in where or "__pycache__" in where:
            continue
        for name in names:
            if name.endswith(".py") and name != "web_output_manager.py":
                product += source(where, name)
idle = [name for name, member in vars(WebOutputManager).items()
        if callable(member) and not name.startswith("__") and not re.search(r"\.%s\(" % name, product) and not re.search(r"self\.%s\(" % name, MANAGER)]
check("the manager defines no method nothing calls: each is called by the product, or by the manager itself on its way to one (0345: a seat's start, a corrected "
      "script, the prompt for a question, the silent mode and the assistant's consultation were defined and never called)", idle == [] and len(product) > 100000, idle)

HOST = source("bambooai", "bambooai.py")
in_file = set(__import__("yaml").safe_load(source("bambooai", "messages", "default_prompts.yaml")))
read = set(re.findall(r"\.prompts\.(\w+)", HOST))
loaded = PR.PromptManager()
check("prompts (0345): the prompts in the file, the names the loader lists and the names the host reads are the same, and each loads as text - no name without a "
      "prompt (the list named 25 of the first version's), no prompt without a reader (the file held one)",
      bool(in_file) and in_file == set(PR._EXPECTED_TEMPLATES) == read and all(isinstance(getattr(loaded, n, None), str) and getattr(loaded, n).strip() for n in in_file),
      (sorted(in_file), sorted(PR._EXPECTED_TEMPLATES), sorted(read)))

listed = tomllib.loads(source("pyproject.toml"))["project"]["dependencies"] + [line for line in source("requirements.txt").splitlines() if line.strip() and not line.startswith("#")]
asked_for = {re.split(r"[<>=!;\[ ]", entry.strip(), maxsplit=1)[0].lower() for entry in listed}
check("retired (0346): the mode outside the page - neither the host nor the code executor takes a flag for it, there is one output manager and no module for another, "
      "and the two packages only the other one imported are not asked for at an install",
      "webui" not in inspect.signature(B.BambooAI.__init__).parameters and "webui" not in inspect.signature(CodeExecutor.__init__).parameters
      and not os.path.exists(os.path.join(ROOT, "bambooai", "output_manager.py")) and "webui" not in product.lower() and "webui" not in MANAGER.lower()
      and "pandas" in asked_for and not {"termcolor", "ipython"} & asked_for, sorted({"termcolor", "ipython"} & asked_for))

print(f"\n{len(passed)} passed, {len(failed)} failed")
sys.exit(1 if failed else 0)
