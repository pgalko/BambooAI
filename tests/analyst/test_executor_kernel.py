"""The kernel the executor image runs is the kernel the tests run (2026-10-05). The image carries its own copy,
containers/executor/kernel.py, forked from delve/kernel.py at the snapshot (one import line and some docstrings
apart). Phase 1 changed only delve's copy: every test passed, and the image ran a kernel without `DS` while the
contract promised it. Since then the copy is delve's with only that import changed, and two checks hold it: the copies are the same
but for that line, and `DS` answers through the executor's own kernel
service, as a run in the app reaches it.

    python3 tests/analyst/test_executor_kernel.py
"""
import os
import sys
import tempfile
import json

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.normpath(os.path.join(HERE, "..", ".."))
sys.path[:0] = [HERE, ROOT, os.path.join(ROOT, "delve"), os.path.join(ROOT, "containers", "executor"), os.path.join(ROOT, "tools", "stack", "fakepkgs")]   # the stand-in plotly: the capture patch writes its figures
import _stubs  # noqa: E402,F401
import pandas as pd  # noqa: E402

results = []


def check(name, cond, detail=""):
    results.append((name, bool(cond)))
    print(("  ok   " if cond else "  FAIL ") + name + ("" if cond else f"  <- {str(detail)[:400]}"))


delve_src = open(os.path.join(ROOT, "delve", "kernel.py"), encoding="utf-8").read()
exec_src = open(os.path.join(ROOT, "containers", "executor", "kernel.py"), encoding="utf-8").read()
check("the executor's kernel is delve's, byte for byte, but for the one import that differs by design (codeutils in the package, executor.py in the image)",
      delve_src.replace("\nfrom codeutils import ", "\nfrom executor import ", 1) == exec_src and "\nfrom codeutils import " in delve_src,
      next((f"first difference at line {k + 1}: {x!r} vs {y!r}" for k, (x, y) in enumerate(zip(delve_src.replace(chr(10) + "from codeutils import ", chr(10) + "from executor import ", 1).splitlines(), exec_src.splitlines())) if x != y), "length differs"))

# DS through the executor's own kernel service: the dataset in the executor's cache, a kernel started on it, cells executed
os.chdir(tempfile.mkdtemp(prefix="bamboo_exec_kernel_"))
import code_executor_api as E  # noqa: E402

c = E.app.test_client()
E.df_cache.put("t1", pd.DataFrame({"a": range(10), "b": list("abcdefghij"), "c": [1.5] * 10}))
r = c.post("/kernel/start", json={"df_id": "t1"})
sid = (r.get_json() or {}).get("session_id")
check("executor: a kernel starts on a cached dataset", r.status_code == 200 and sid, r.get_data(as_text=True)[:300])
try:
    out1 = (c.post("/kernel/execute", json={"session_id": sid, "code": "print(DS)\nprint(DS.load().shape)"}).get_json() or {})
    check("executor: DS is defined in the executor's kernel and DS.load() returns the dataset (2026-10-05: NameError in both runs)",
          not out1.get("error") and "DS: the dataset as attached, 10 rows x 3 columns" in (out1.get("stdout") or "") and "(10, 3)" in (out1.get("stdout") or ""), out1)
    out2 = (c.post("/kernel/execute", json={"session_id": sid, "code": "for nm, df, t in [('x', df[['a']], 1)]:\n    pass\nprint('done')"}).get_json() or {})
    check("executor: a cell that leaves df without the dataset's columns ends its output with the line naming DS.load()",
          "of the dataset's 3 columns" in (out2.get("stdout") or "") and "DS.load() restores" in (out2.get("stdout") or ""), out2)
    out3 = (c.post("/kernel/execute", json={"session_id": sid, "code": "df = DS.load()\nprint(df.shape)"}).get_json() or {})
    check("executor: df = DS.load() restores the dataset", "(10, 3)" in (out3.get("stdout") or "") and "DS.load() restores" not in (out3.get("stdout") or ""), out3)
    out4 = (c.post("/kernel/execute", json={"session_id": sid, "code": "label = '+HR eval@150'  # eval in a comment\nprint(label)"}).get_json() or {})
    check("executor: a restricted word inside a string or a comment is not a use of it - the cell runs (2026-10-05: a label was refused as eval)",
          "eval@150" in (out4.get("stdout") or "") and not out4.get("error"), out4)
    out5 = (c.post("/kernel/execute", json={"session_id": sid, "code": "x = eval('1+1')\nprint(x)"}).get_json() or {})
    out6 = (c.post("/kernel/execute", json={"session_id": sid, "code": "print(f\"{eval('2+2')}\")"}).get_json() or {})
    check("executor: a call of a restricted name is still refused, inside an f-string too",
          "Security notice" in ((out5.get("stdout") or "") + (out5.get("error") or "")) and "Security notice" in ((out6.get("stdout") or "") + (out6.get("error") or "")), (out5, out6))
    out7 = (c.post("/kernel/execute", json={"session_id": sid, "code": "e = float(df.a.mean())\nRESULT('a, 10 rows', e, e - 1, e + 1, 'units', 'up')\nRESULT('b', 6.1, 4.4, 7.7, 'bpm')"}).get_json() or {})
    check("executor: RESULT(...) prints the line and the route returns the kernel's records, the typed one marked (2026-10-06)",
          "RESULT: a, 10 rows: +4.50 (95% CI +3.50 to +5.50) units, up" in (out7.get("stdout") or "") and len(out7.get("results") or []) == 2
          and out7["results"][0]["typed"] is False and out7["results"][1]["typed"] is True and "typed" in out7["results"][1]["text"], out7)
    # the code map (2026-10-20): each record carries the cell line its call ran from - the call's own line at the top level, the
    # line of the call to a helper when RESULT ran inside it, and the body's line inside a loop
    out8 = (c.post("/kernel/execute", json={"session_id": sid, "code": "def helper(v):\n    RESULT('inside', v, v - 1, v + 1, 'u')\n    return v\n\nhelper(2.0)\nfor k in range(2):\n    RESULT('loop %d' % k, float(k), None, None)\nRESULT('top', 1.0, 0.0, 2.0, 'u')"}).get_json() or {})
    check("executor: a RESULT record carries the cell line of the top-level statement its call ran from - through a helper, inside a loop, at the top level",
          [r.get("line") for r in (out8.get("results") or [])] == [5, 7, 7, 8], out8.get("results"))
finally:
    c.post("/kernel/stop", json={"session_id": sid})

# DS.save through the executor (2026-10-06): a kernel started with the user's generated folder writes there; /cache/inspect
# lists the file under generated_datasets and /download_generated_dataset serves it - the Dataset cache's Generated section
r2 = c.post("/kernel/start", json={"df_id": "t1", "generated_dir": os.path.join("datasets", "u9", "generated")}).get_json() or {}
sid2 = r2.get("session_id")
try:
    out8 = (c.post("/kernel/execute", json={"session_id": sid2, "code": "DS.save(df.head(3), 'Merged laps')"}).get_json() or {})
    listing = (c.get("/cache/inspect", query_string={"user_id": "u9"}).get_json() or {}).get("generated_datasets") or []
    served = c.get("/download_generated_dataset", query_string={"path": os.path.join("datasets", "u9", "generated", "Merged_laps.csv"), "user_id": "u9"})
    check("executor: DS.save writes under datasets/<user>/generated, /cache/inspect lists it under generated_datasets, and the download route serves it (the Dataset cache's Generated section, 2026-10-06)",
          "DATASET: Merged_laps.csv - 3 rows x " in (out8.get("stdout") or "") and [d["filename"] for d in listing] == ["Merged_laps.csv"] and served.status_code == 200
          and served.data.decode().splitlines()[0].startswith("a,"), (r2, out8.get("stdout"), out8.get("error"), listing, served.status_code))
    out9 = (c.post("/kernel/execute", json={"session_id": sid2, "code": "DS.save('a note', 'notes.txt')\nDS.save(df.head(3), 'laps.json')"}).get_json() or {})
    pv_txt = c.post("/cache/preview_aux", json={"file_path": os.path.join("datasets", "u9", "generated", "notes.txt"), "user_id": "u9"}).get_json() or {}
    pv_json = c.post("/cache/preview_aux", json={"file_path": os.path.join("datasets", "u9", "generated", "laps.json"), "user_id": "u9"}).get_json() or {}
    check("executor: a text file saved for the person previews with its basic information (no columns), a json one with its shape and columns (2026-10-06)",
          not out9.get("error") and pv_txt.get("filename") == "notes.txt" and "columns" not in pv_txt and pv_json.get("shape") == [3, 3] and pv_json.get("columns") == ["a", "b", "c"], (out9.get("error"), pv_txt, pv_json))
finally:
    c.post("/kernel/stop", json={"session_id": sid2})

# the figures of one script come back in the order they were shown (2026-10-13): the app's capture patch names each file
# with its number, and the executor reads the files sorted by name - with id(fig) alone in the name the order was the
# order of the figures' addresses, and a run's two figures swapped places from one run to the next
from bambooai.code_executor import CodeExecutor as _CE   # noqa: E402
_ce = _CE.__new__(_CE); _CE.__init__(_ce, webui=True) if "webui" in _CE.__init__.__code__.co_varnames else _CE.__init__(_ce)
_plots = tempfile.mkdtemp(prefix="bamboo_exec_plots_")
_code = ("import plotly.graph_objects as go\n"
         "for _name in ('first', 'second', 'third', 'fourth'):\n"
         "    go.Figure(go.Scatter(x=[1, 2], y=[2, 1], name=_name)).show()\n")
_r = c.post("/execute", json={"code": _code, "df_id": "t1", "persist_df": False, "patch_code": f"_plots_dir = {_plots!r}\n_generated_files = []\n" + _ce.patch_code,
                              "plots_dir": _plots, "plot_format": "json", "timeout": 60, "generated_datasets_path": os.path.join(_plots, "gen")}).get_json() or {}
_names = [[t.get("name") for t in json.loads(p["data"])["data"]][0] for p in _r.get("plot_images") or [] if p.get("format") == "json"]
_files = sorted(f for f in os.listdir(_plots) if f.startswith("figure_"))
check("executor: four figures shown in one script come back in the order shown, their files numbered 000-003 in that order",
      _names == ["first", "second", "third", "fourth"] and [f[:10] for f in _files] == ["figure_000", "figure_001", "figure_002", "figure_003"], (_names, _files, (_r.get("error") or "")[-200:]))

# a script that fails returns what it printed before the failure beside the error (2026-10-16, image v57): a routine's run
# compares the RESULT lines its cells printed before the one that failed - the route used to return results: None, and
# the record said "no result line came before the failure" of a run whose first eight cells had printed nine
_f = c.post("/execute", json={"code": "print('RESULT: first, 10 rows: +1.00 units')\nprint('RESULT: second, 10 rows: +2.00 units')\nx = 1 / 0\nprint('never')",
                              "df_id": "t1", "persist_df": False, "patch_code": f"_plots_dir = {_plots!r}\n_generated_files = []\n", "plots_dir": _plots, "plot_format": "json", "timeout": 60,
                              "generated_datasets_path": os.path.join(_plots, "gen2")}).get_json() or {}
check("executor: a failed script's results are the lines it printed before the failure, beside the error naming the line",
      "ZeroDivisionError" in (_f.get("error") or "") and (_f.get("results") or "").strip().splitlines() == ["RESULT: first, 10 rows: +1.00 units", "RESULT: second, 10 rows: +2.00 units"] and "line 3" in (_f.get("error") or ""),
      (_f.get("results"), (_f.get("error") or "")[-300:]))
_g = c.post("/execute", json={"code": "x = 1 / 0", "df_id": "t1", "persist_df": False, "patch_code": f"_plots_dir = {_plots!r}\n_generated_files = []\n", "plots_dir": _plots, "plot_format": "json", "timeout": 60,
                              "generated_datasets_path": os.path.join(_plots, "gen3")}).get_json() or {}
check("executor: a script that fails before printing anything returns no results, as before", _g.get("results") is None and "ZeroDivisionError" in (_g.get("error") or ""), _g)


n_fail = sum(1 for _, ok in results if not ok)
print(f"\n{len(results) - n_fail} passed, {n_fail} failed")
sys.exit(1 if n_fail else 0)
