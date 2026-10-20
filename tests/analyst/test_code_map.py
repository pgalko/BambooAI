"""The code map (docs/CODEMAP_DESIGN.md, 2026-10-20): the extractor against its golden fixtures, its rules one by one,
the build at a chain's end, and the route.

    python3 tests/analyst/test_code_map.py

The fixtures under tests/analyst/fixtures/codemap are the design package's, without the chain built from the product
owner's own data (that one is run from the package, locally): a field trial and its follow-up (run in the real kernel,
with the kernel's registry), the pilot's planted-flaw chain, and a five-chain branching thread (Fibonacci and Lorenz,
one chain with no code). The expected view is the prototype's; the port is compared with it whole, except the layout
fields it does not store, the mockup's pills, and the fields the port builds from the record itself.
"""
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.normpath(os.path.join(HERE, "..", ".."))
sys.path[:0] = [HERE, ROOT, os.path.join(ROOT, "delve")]
import _stubs  # noqa: E402,F401

results = []


def check(name, cond, detail=""):
    results.append((name, bool(cond)))
    print(("  ok   " if cond else "  FAIL ") + name + ("" if cond else f"  <- {str(detail)[:600]}"))


FIX = os.path.join(HERE, "fixtures", "codemap")


def load(path):
    with open(os.path.join(FIX, path), encoding="utf-8") as f:
        return json.load(f)


# ---- golden parity: the view the port builds against the prototype's, chain by chain -------------------------------
from analyst import codemap  # noqa: E402
from analyst.codemap import objects as O  # noqa: E402

from _codemap_golden import comparable, first_difference, with_ids, strip_lines, norm_map, MAPS  # noqa: E402

PRIMARY = {"trial": "field_trial.csv", "trial2": "field_trial.csv", "sim1": "field_trial.csv"}

expected = load("expected/viewmodel.json")
thread = {t["chain"]: t for t in load("inputs/thread5/thread.json")}
titles = {str(k): t["question"] for k, t in thread.items()}


def build_fixture(name, mode):
    """One fixture chain's view and map, as the port builds them from the ChainRecord (earlier chains' exports first)."""
    if re.match(r"^t\d+$", name):
        k = int(name[1:])
        doc = load(f"inputs/thread5/chain{k}_cells.json")
        doc["titles"] = titles
        maps = {}
        for j in sorted(thread):
            if j >= k:
                break
            dj = load(f"inputs/thread5/chain{j}_cells.json")
            if not dj["cells"]:
                continue
            dj["earlier"] = earlier_of(thread[j]["path"][:-1], maps)
            maps[j] = O.build_map(with_ids(strip_lines(dj) if mode == "noline" else dj))
        doc["earlier"] = earlier_of(thread[k]["path"][:-1], maps)
    elif name == "trial2":
        doc = load("inputs/trial2_cells.json")
        prev = load("inputs/trial_cells.json")
        pm = O.build_map(with_ids(strip_lines(prev) if mode == "noline" else prev))
        doc["earlier"] = O.exports(pm, "1")
        doc["titles"] = {"1": prev["question"], "2": doc["question"]}
    else:
        doc = load(f"inputs/{name}_cells.json")
        doc["titles"] = {"1": doc["question"]}
    doc = with_ids(strip_lines(doc) if mode == "noline" else doc)
    # the fixtures predate the primary input's `name`: the prototype was told the dataset's name, as the host tells build()
    return codemap.build_record(doc, primary_name=PRIMARY.get(name, "primary dataset")), doc


def earlier_of(path, maps):
    names, funcs = {}, {}
    for anc in path:
        if anc in maps:
            ex = O.exports(maps[anc], str(anc))
            names.update(ex["names"]); funcs.update(ex["funcs"])
    return dict(names=names, funcs=funcs)


for mode in ("recorded", "noline"):
    for name in ("trial", "trial2", "sim1", "t1", "t2", "t3", "t4", "t5"):
        try:
            cm, doc = build_fixture(name, mode)
            got = comparable(cm["view"])
            want = comparable(expected[name])
            diff = first_difference(got, want)
            check(f"golden ({mode}): {name} - the view matches the prototype's", not diff and "error" not in cm, diff or cm.get("error"))
            if name in MAPS:
                m = norm_map(cm["map"])
                w = norm_map(load(MAPS[name]))
                d2 = first_difference(m, w, "map")
                check(f"golden ({mode}): {name} - the intermediate map matches", not d2, d2)
        except Exception as exc:                            # noqa: BLE001
            import traceback
            check(f"golden ({mode}): {name} - built without an exception", False, traceback.format_exc()[-600:])

# the first single-chain test's map (its view was superseded by the thread's chain 1)
try:
    fib = codemap.build_record(with_ids(load("inputs/fib_cells.json")))
    check("golden: fib - the intermediate map matches", not first_difference(norm_map(fib["map"]), norm_map(load("expected/fib_map.json")), "map"),
          first_difference(norm_map(fib["map"]), norm_map(load("expected/fib_map.json")), "map"))
except Exception as exc:                                    # noqa: BLE001
    check("golden: fib - built without an exception", False, repr(exc))


# ---- the rules, one small synthetic cell each (blueprint 9.2) ------------------------------------------------------
COLS = ["plot_id", "regime", "soil", "season", "rainfall_mm", "yield_t_ha", "date"]


def rec(text, line=None, corrects=None, test=None, typed=False):
    return dict(text=text, typed=typed, test=test, corrects=corrects, line=line)


def cell(n, code, results=(), output="", registry=None, figures=0, step="step", kind="analysis"):
    out = output or "".join("RESULT: " + r["text"] + "\n" for r in results)
    return dict(cell=n, turn=n, step=step, code=code, output=out, kind=kind, registry=registry or {}, figures=figures, results=list(results))


def record(cells, report="", inputs=None, failed=(), events=(), earlier=None, registry_start=None, chain_id="1", path=None,
           path_cells=None, titles=None, searches=0, reads=0):
    """A ChainRecord (blueprint section 3) with the field trial's columns as the primary input."""
    cells = list(cells)
    return dict(chain_id=chain_id, question="q?", title="", mode="Quick",
                inputs=inputs if inputs is not None else [dict(kind="primary", label="primary dataset", name="field_trial.csv", columns=COLS, detail="720 rows x 7 columns")],
                cells=cells, failed=list(failed), events=list(events), report=report, searches=searches, reads=reads,
                path=path or [chain_id], path_cells=path_cells or {str(c["cell"]): chain_id for c in cells},
                titles=titles or {chain_id: "q?"}, registry_start=registry_start or {}, earlier=earlier or dict(names={}, funcs={}))


def rule(name, fn):
    try:
        fn()
    except Exception:                                       # noqa: BLE001
        import traceback
        check(f"rule: {name} - built without an exception", False, traceback.format_exc()[-700:])


def no_line(recs):
    return [dict(r, line=None) for r in recs]


def rule_loop():
    code = "for g, sub in df.groupby('regime'):\n    RESULT(f\"mean yield, regime {g}: {sub['yield_t_ha'].mean():.2f} t/ha\")\n"
    recs = [rec("mean yield, regime A: 4.50 t/ha", 2), rec("mean yield, regime B: 5.38 t/ha", 2), rec("mean yield, regime C: 4.71 t/ha", 2)]
    for mode, rs in (("by line", recs), ("by order", no_line(recs))):
        v = codemap.build_record(record([cell(1, code, rs)]))["view"]
        check(f"rule: a RESULT in a loop ({mode}) - one result per printed line, labelled with its printed words",
              [r["label"] for r in v["results"].values()] == ["mean yield, regime A", "mean yield, regime B", "mean yield, regime C"]
              and [r["estimate"] for r in v["results"].values()] == ["4.50", "5.38", "4.71"], v["results"])
        check(f"rule: a RESULT in a loop ({mode}) - a dataset the RESULT read itself is its input and counts as used",
              v["recipes"]["r1"]["inputs"] == ["field_trial.csv"] and v["inputs"][0]["status"] == "used" and v["inputs"][0]["used_columns"] == ["regime", "yield_t_ha"]
              and not v["checks"] and "traced" not in v["recipes"]["r1"], (v["recipes"]["r1"], v["inputs"], v["checks"]))


def rule_helper_line():
    code = "def report_mean(s, name):\n    RESULT(f\"{name}: {s.mean():.2f} t/ha\")\n\nreport_mean(df['yield_t_ha'], 'mean yield')\n"
    v = codemap.build_record(record([cell(1, code, [rec("mean yield: 4.87 t/ha", 4)])]))["view"]
    r = v["results"].get("r1") or {}
    check("rule: a RESULT inside a helper - the record's line pairs it with the statement that called the helper",
          r.get("label") == "mean yield" and r.get("estimate") == "4.87" and r.get("cell") == 1 and v["recipes"]["r1"]["inputs"] == ["field_trial.csv"]
          and v["rows"][0]["results"] == ["r1"], (r, v["recipes"]))


def rule_conversion():
    code = "x = df['yield_t_ha']\nx = np.asarray(x, float)\nRESULT(f\"mean yield: {x.mean():.2f} t/ha\")\n"
    cm = codemap.build_record(record([cell(1, code, [rec("mean yield: 4.87 t/ha", 3)])]))
    v = cm["view"]
    check("rule: a type conversion - no box of its own; the value is carried on and the dataset it was read off is the input",
          v["recipes"]["r1"]["items"] == [] and v["recipes"]["r1"]["inputs"] == ["field_trial.csv"] and "traced" not in v["recipes"]["r1"]
          and v["steps"]["1"]["builds"] == [] and cm["selfcheck"]["empty"] == [], (v["recipes"], v["steps"]["1"]["builds"], cm["selfcheck"]))


def rule_draw_helper():
    code = "import plotly.graph_objects as go\ndef add_line(fig, s):\n    fig.add_trace(go.Scatter(y=s, name='yield'))\n\nfig = go.Figure()\nadd_line(fig, df['yield_t_ha'])\nfig.show()\n"
    cm = codemap.build_record(record([cell(1, code, [], figures=1, kind="figures", step="Figures: yield by plot")]))
    v = cm["view"]
    fig = {o["id"]: o for o in cm["map"]["objects"]}.get("fig@1") or {}
    check("rule: drawing through a helper - the figure is drawn on by the call and rests on what the call passed",
          set(v["figures"]) == {"fig1"} and v["figures"]["fig1"]["caption"] == "yield by plot" and v["recipes"]["fig1"]["inputs"] == ["field_trial.csv"]
          and "traced" not in v["recipes"]["fig1"] and "primary dataset" in fig.get("inputs", []) and v["rows"][0]["role"] == "figures",
          (v["figures"], v["recipes"], fig))


def rule_title_only():
    code = "import plotly.graph_objects as go\ntitle = 'Yield by plot'\nfig = go.Figure()\nfig.add_trace(go.Scatter(y=df['yield_t_ha']))\nfig.update_layout(title=title)\nfig.show()\n"
    cm = codemap.build_record(record([cell(1, code, [], figures=1)]))
    objs = {o["id"]: o for o in cm["map"]["objects"]}
    check("rule: a name read only for words on the figure - not among the figure's parents, not in its recipe",
          "fig@1" in objs and "title@1" in objs and "title@1" not in objs["fig@1"]["parents"] and cm["view"]["recipes"]["fig1"]["items"] == []
          and cm["view"]["recipes"]["fig1"]["inputs"] == ["field_trial.csv"] and cm["view"]["recipes"]["fig1"]["params"] == [],
          ({k: o["parents"] for k, o in objs.items()}, cm["view"]["recipes"]))


def rule_bootstrap_rng():
    code = ("def boot(s, rng, B=1000):\n    out = []\n    for _ in range(B):\n        out.append(rng.choice(s, len(s)).mean())\n    return np.percentile(out, [2.5, 97.5])\n\n"
            "rng = np.random.default_rng(1)\ny = df['yield_t_ha'].to_numpy()\nlo, hi = boot(y, rng)\nRESULT(f\"mean yield: 4.87 (95% CI {lo:.2f} to {hi:.2f}) t/ha\")\n")
    cm = codemap.build_record(record([cell(1, code, [rec("mean yield: 4.87 (95% CI 4.78 to 4.96) t/ha", 10)])]))
    v = cm["view"]
    it = v["recipes"]["r1"]["items"]
    f = cm["map"]["functions"]["boot"]
    check("rule: a bootstrap through a helper given rng by position - the helper always re-draws rows; the call is a bootstrap of N resamples",
          f["resamples"] and f["produces"] == "estimate" and len(it) == 1 and it[0]["kind"] == "estimate" and it[0]["label"] == "estimate: bootstrap, 1,000 resamples"
          and "bootstrap" in v["rows"][0]["chips"] and {c["text"] for c in v["recipes"]["r1"]["choices"]} == {"random seed 1", "B=1000"}
          and v["results"]["r1"]["interval"] == "4.78 to 4.96", (f, it, v["rows"][0], v["recipes"]["r1"]["choices"]))


def rule_alias():
    code = ("def diff(g, rng=None):\n    ga, gb = g[g['regime'] == 'A']['yield_t_ha'].to_numpy(), g[g['regime'] == 'B']['yield_t_ha'].to_numpy()\n"
            "    if rng is not None:\n        ga, gb = rng.choice(ga, len(ga)), rng.choice(gb, len(gb))\n    return gb.mean() - ga.mean()\n\n"
            "rng = np.random.default_rng(0)\nest = diff(df)\nboots = np.array([diff(df, rng=rng) for _ in range(200)])\nlo, hi = np.percentile(boots, [2.5, 97.5])\n"
            "RESULT(f\"yield, B vs A: {est:.2f} (95% CI {lo:.2f} to {hi:.2f}) t/ha\")\n")
    reg = {"est": {"type": "float64", "desc": "float64"}, "boots": {"type": "ndarray", "desc": "ndarray 200"}}
    cm = codemap.build_record(record([cell(1, code, [rec("yield, B vs A: 0.88 (95% CI 0.75 to 1.01) t/ha", 11)], registry=reg)]))
    f = cm["map"]["functions"]["diff"]
    redraw = [s for s in f["own"] if s["verb"] == "resample"]
    steps = {it["names"]: [s["text"] for s in it["steps"]] for it in cm["view"]["recipes"]["r1"]["items"]}
    check("rule: tuple aliasing in a helper - the re-draw of ga, gb = g[...], g[...] is a re-draw of the parameter g, only when the call gives the switch",
          f["can_resample"] and f["guard"] == ["rng"] and redraw and redraw[0]["param"] == "g" and redraw[0]["guarded"] and f["untraced"]
          and steps.get("est") == ["keep rows where regime is A; keep rows where regime is B; mean; the arithmetic is not traced (diff)"]
          and steps.get("boots") == ["keep rows where regime is A; keep rows where regime is B; mean; re-draws the rows of df with replacement; the arithmetic is not traced (diff)",
                                     "bootstrap, 200 resamples"], (f, steps))


def rule_string_join():
    code = "cols = ['regime', 'soil']\nlabel = '|'.join(cols)\nprint(label)\n"
    cm = codemap.build_record(record([cell(1, code, [], output="regime|soil\n")]))
    ops = [op["verb"] for o in cm["map"]["objects"] for op in o["ops"]]
    check("rule: a string join - not a table join", "combine" not in ops and "join" not in cm["view"]["rows"][0]["chips"], (ops, cm["view"]["rows"]))


def rule_typed_date():
    code = "start = pd.Timestamp('2026-08-13')\nsub = df[df['date'] >= start]\nRESULT(f\"mean yield since start: {sub['yield_t_ha'].mean():.2f} t/ha\")\n"
    v = codemap.build_record(record([cell(1, code, [rec("mean yield since start: 4.90 t/ha", 3)])]))["view"]
    rc = v["recipes"]["r1"]
    check("rule: a typed date - a typed parameter behind the result, its value in the step's words, and a check",
          rc["params"] == [dict(name="start", value="2026-08-13", typed=True, cell=1)] and [s["text"] for s in rc["items"][0]["steps"]] == ["keep rows where date ≥ 2026-08-13"]
          and [c["text"] for c in v["checks"]] == ["start = 2026-08-13 is typed into cell 1, not read from the data; all 1 result rests on it"], (rc, v["checks"]))


def rule_nan():
    code = "m = df['yield_t_ha'].mean()\nRESULT(f\"mean yield: {m} t/ha\")\n"
    v = codemap.build_record(record([cell(1, code, [rec("mean yield: nan t/ha", 2)])]))["view"]
    check("rule: nan - the result is not computed, and a check says so",
          v["results"]["r1"]["status"] == "not computed" and [c["text"] for c in v["checks"]] == ["1 result came out empty (nan): cell 1"], (v["results"], v["checks"]))


def rule_corrects():
    c1 = "m = df['yield_t_ha'].mean()\nRESULT(f\"mean yield: {m:.2f} t/ha\")\n"
    c2 = "m = df['yield_t_ha'].median()\nRESULT(f\"(corrects cell 1) median yield: {m:.2f} t/ha\", corrects=1)\n"
    v = codemap.build_record(record([cell(1, c1, [rec("mean yield: 4.87 t/ha", 2)]), cell(2, c2, [rec("(corrects cell 1) median yield: 4.80 t/ha", 2, corrects=1)])]))["view"]
    r1, r2 = v["results"]["r1"], v["results"]["r2"]
    check("rule: corrects - the earlier cell's result is corrected by the later one, the note dropped from the short label",
          r1["status"] == "corrected" and r1["corrected_by"] == 2 and r2["status"] == "recorded" and r2["short"] == "median yield"
          and [c["text"] for c in v["checks"]] == ["1 result was replaced by a later cell"], (r1, r2, v["checks"]))


def rule_cited_printout():
    code = "t = df.groupby('regime')['yield_t_ha'].mean().round(2)\nprint(t.to_string())\n"
    v = codemap.build_record(record([cell(1, code, [], output="regime\nA    4.50\nB    5.38\nC    4.71\n")], report="Regime B is highest [cell 1].\n"))["view"]
    p = v["results"].get("p1") or {}
    check("rule: a cited printout - a printed result traced back from the print, with its first three lines, and a check",
          p.get("kind") == "printed" and p.get("lines") == ["regime", "A    4.50", "B    5.38"] and v["rows"][0]["role"] == "evidence" and v["rows"][0]["printout"] == "p1"
          and [it["label"] for it in v["recipes"]["p1"]["items"]] == ["field_trial.csv, by regime"]
          and [c["text"] for c in v["checks"]] == ["no RESULT line: the answer is only printed, in cell 1, and the report cites it"], (p, v["rows"], v["checks"]))


def rule_several_figures():
    code = "import plotly.graph_objects as go\nfig1 = go.Figure(go.Scatter(y=df['yield_t_ha']))\nfig1.show()\nfig2 = go.Figure(go.Bar(y=df['rainfall_mm']))\nfig2.show()\n"
    v = codemap.build_record(record([cell(1, code, [], figures=2, kind="figures", step="Figures: yield by plot | rainfall by plot")]))["view"]
    f = v["figures"]
    check("rule: a figure cell with several plots - one recipe per figure, in creation order, each with its caption",
          [(k, x["label"], x["caption"], x["name"]) for k, x in f.items()] == [("fig1.1", "figure 1 of 2", "yield by plot", "fig1"), ("fig1.2", "figure 2 of 2", "rainfall by plot", "fig2")]
          and v["recipes"]["fig1.2"]["inputs"] == ["field_trial.csv"], (f, v["recipes"]))


def rule_unparsed():
    cm = codemap.build_record(record([cell(1, "def (:\n  pass\n", []), cell(2, "m = df['yield_t_ha'].mean()\nRESULT(f\"mean yield: {m:.2f} t/ha\")\n", [rec("mean yield: 4.87 t/ha", 2)])]))
    v = cm["view"]
    check("rule: a cell that does not parse - its row stays, marked not mapped; the rest of the chain is mapped",
          "error" not in cm and v["rows"][0]["mapped"] is False and "mapped" not in v["rows"][1] and v["results"]["r1"]["estimate"] == "4.87"
          and cm["map"]["unparsed"] == [1], (cm.get("error"), v["rows"], cm["map"].get("unparsed")))


def rule_no_cells():
    v = codemap.build_record(record([], searches=1, report="The answer is 42."))["view"]
    check("rule: a chain with no cells - one line, no rows, no inputs",
          v["nocode"] is True and v["nocodeText"] == "No code ran in this chain: it answered from a web search, so there is nothing to map." and v["rows"] == [] and v["inputs"] == []
          and v["meta"] == "Quick · 0 turns · 1 web search · no code", v)
    v = codemap.build_record(record([], reads=1, chain_id="2", path=["1", "2"], path_cells={"1": "1", "2": "1"}, titles={"1": "q1", "2": "q2"}, report="See [cell 1] and [cell 2].\n"))["view"]
    check("rule: a chain with no cells - its citations into the earlier chain are listed, that chain named by its id",
          v["nocodeText"].endswith("there is nothing to map. The report cites {chain:1}'s cells 1 and 2.")
          and [(c["kind"], c["chain"], c["cell"]) for c in v["checks"]] == [("cites", "1", 1)] and v["titles"] == {"1": "q1", "2": "q2"}, v)


def rule_follow_up():
    c1 = "plot_means = df.groupby(['plot_id', 'regime'], as_index=False)['yield_t_ha'].mean()\nRESULT(f\"plots: {len(plot_means)}\")\n"
    reg = {"plot_means": {"type": "DataFrame", "desc": "DataFrame 120x3 cols=plot_id,regime,yield_t_ha"}}
    first = codemap.build_record(record([cell(1, c1, [rec("plots: 120", 2)], registry=reg)]))
    c2 = "gap = plot_means.groupby('regime')['yield_t_ha'].mean()\nRESULT(f\"mean of plot means, regime B: {gap['B']:.2f} t/ha\")\n"
    doc2 = record([cell(2, c2, [rec("mean of plot means, regime B: 5.38 t/ha", 2)])], chain_id="2", path=["1", "2"], path_cells={"1": "1", "2": "2"},
                  titles={"1": "q1", "2": "q2"}, earlier=first["exports"], registry_start=reg, report="B leads [cell 1] [cell 2].\n")
    v = codemap.build_record(doc2)["view"]
    lane = v["inputs"][0]
    check("rule: a follow-up's taken names - a lane for the earlier chain, used; the dataset reached through it; the step and the recipe say so",
          first["exports"]["names"]["plot_means"]["chain_id"] == "1"
          and (lane["kind"], lane["name"], lane["status"], lane["cols"], lane["names"], lane["from_cells"]) == ("chain", "From {chain:1}", "used", "plot_means", ["plot_means"], [1])
          and (v["inputs"][1]["status"], v["inputs"][1]["through"], v["inputs"][1]["cols"]) == ("via", "1", "through {chain:1}")
          and v["rows"][0]["lanes"] == ["read", "via"] and v["steps"]["2"]["takes_chain"] == [dict(chain="1", names=["plot_means"], cells=[1])]
          and v["recipes"]["r1"]["inputs"] == ["From {chain:1}"] and v["recipes"]["r1"]["items"][0]["names"] == "from {chain:1}"
          and ["in:chain:1", "gap@2"] in v["diagrams"]["r1"]["edges"], (first["exports"], v["inputs"], v["rows"], v["steps"]["2"], v["recipes"], v["diagrams"]))
    check("rule: a citation into an earlier chain - the report's [cell 1] belongs to chain 1: a check that opens it there, before the chain check",
          [(c["kind"], c.get("chain"), c.get("cell"), c["text"]) for c in v["checks"]]
          == [("cites", "1", 1, "the report also cites {chain:1}'s cell 1"), ("chain", "1", None, "rests on {chain:1}: plot_means (cell 1)")], v["checks"])


for name, fn in [("a RESULT in a loop", rule_loop), ("a RESULT inside a helper", rule_helper_line), ("a type conversion", rule_conversion),
                 ("drawing through a helper", rule_draw_helper), ("a title-only read", rule_title_only), ("a bootstrap through a helper", rule_bootstrap_rng),
                 ("tuple aliasing in a helper", rule_alias), ("a string join", rule_string_join), ("a typed date", rule_typed_date), ("nan", rule_nan),
                 ("corrects", rule_corrects), ("a cited printout", rule_cited_printout), ("several figures", rule_several_figures),
                 ("a cell that does not parse", rule_unparsed), ("a chain with no cells", rule_no_cells), ("a follow-up", rule_follow_up)]:
    rule(name, fn)

# ---- the build at a chain's end: from the Run, never raising -------------------------------------------------------
from analyst.notebook import Notebook, Turn  # noqa: E402


def chain_turns(code, text, line, question, registry=None):
    return [Turn(kind="cell", thinking="Mean yield first.", code=code, stdout="RESULT: " + text + "\n", cell_no=None,
                 results=[dict(text=text, typed=False, test=None, corrects=None, line=line)], registry=registry or {}),
            Turn(kind="report", text="done")]


nb = Notebook("t1")
r1 = nb.new_run("Mean yield?")
r1.turns = chain_turns("m = df['yield_t_ha'].mean()\nRESULT(f\"mean yield: {m:.2f} t/ha\")\n", "mean yield: 4.87 t/ha", 2, "q1",
                       registry={"m": {"type": "float64", "desc": "float64"}})
r1.turns[0].cell_no = 1
r1.report = "## Mean yield\nThe mean is 4.87 t/ha [cell 1].\n"
r1.mode = "Quick"
r1.data = dict(df_id="d1", name="field_trial.csv", rows=720, columns=[dict(name=c) for c in COLS])
cm1 = codemap.build(nb, r1)
r1.code_map = cm1
check("build: a Run's map - a view at the current version, the exports for later chains, no error",
      cm1.get("version") == codemap.VERSION and "error" not in cm1 and cm1["view"]["results"]["r1"]["estimate"] == "4.87"
      and cm1["view"]["inputs"][0]["name"] == "field_trial.csv" and cm1["view"]["inputs"][0]["detail"] == "720 rows x 7 columns"
      and cm1["view"]["meta"].startswith("Quick · ") and list(cm1["exports"]["names"]) == ["m"] and "map" not in cm1, cm1)
r2 = nb.new_run("And the median?", parent=r1.id)
r2.turns = chain_turns("md = df['yield_t_ha'].median()\nRESULT(f\"median yield: {md:.2f} t/ha, mean was {m:.2f}\")\n", "median yield: 4.80 t/ha, mean was 4.87", 2, "q2")
r2.turns[0].cell_no = 2
r2.data = dict(r1.data)
cm2 = codemap.build(nb, r2)
lanes = [(i["kind"], i["name"], i["status"]) for i in cm2["view"]["inputs"]]
check("build: a follow-up - the earlier chain's names come from its stored exports, the registry from its cells; the lane names the chain by id",
      lanes == [("chain", "From {chain:%s}" % r1.id, "used"), ("primary", "field_trial.csv", "used")] and cm2["view"]["path"] == [r1.id, r2.id]
      and cm2["view"]["titles"] == {r1.id: "Mean yield?", r2.id: "And the median?"}, (lanes, cm2["view"].get("path"), cm2["view"].get("titles"), cm2.get("error")))
bad = codemap.build(None, None)
check("build: a record that cannot be built - an error entry, never an exception", bad.get("version") == codemap.VERSION and bad.get("error") and "view" not in bad, bad)

# ---- the app's names for an Intervals.icu load: words.APP_NAMES pinned to intervals.js (blueprint 4.10) ---------------
from analyst.codemap import words as W  # noqa: E402

with open(os.path.join(ROOT, "web_app", "static", "js", "integrations", "intervals.js"), encoding="utf-8") as f:
    js = f.read()
fn = js[js.index("function intervalsAuxDisplayName("):]
fn = fn[:fn.index("\n}\n")]
js_names = [(k, re.sub(r"\s*\(\$\{dayCount\} days\)", "", v)) for k, v in re.findall(r"filename\.includes\('([^']+)'\)\) return [`']([^`']+)[`']", fn)]
check("words.APP_NAMES is the top bar's table (intervalsAuxDisplayName, without the day count)", js_names == list(W.APP_NAMES), (js_names, W.APP_NAMES))
check("lane_name: a file is named as the top bar names it, the primary by its name, another file without its extension",
      (W.lane_name("activity_summary_20260801_to_20261001.csv", "x"), W.lane_name(W.PRIMARY_LABEL, "field_trial.csv"), W.lane_name("rainfall.csv", "x"))
      == ("Activity Summary", "field_trial.csv", "rainfall"))

n_fail = sum(1 for _, ok in results if not ok)
print(f"\n{len(results) - n_fail} passed, {n_fail} failed")
sys.exit(1 if n_fail else 0)
