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

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.normpath(os.path.join(HERE, "..", ".."))
sys.path[:0] = [HERE, ROOT, os.path.join(ROOT, "delve"), os.path.join(ROOT, "containers", "executor")]
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
finally:
    c.post("/kernel/stop", json={"session_id": sid})

n_fail = sum(1 for _, ok in results if not ok)
print(f"\n{len(results) - n_fail} passed, {n_fail} failed")
sys.exit(1 if n_fail else 0)
