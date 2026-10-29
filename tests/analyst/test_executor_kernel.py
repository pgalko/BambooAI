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


# the reach record (2026-10-28): the kernel says, per cell, what the cell touched outside the data - the hosts it connected
# to and the bytes each way, the files it opened or listed outside the data, the environment names it read, the programs
# it started - and the restricted word a refused cell was refused for; the box reports itself on /kernel/start and /health
import threading  # noqa: E402
import http.server  # noqa: E402
import socketserver  # noqa: E402


class _Handler(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        body = b"x" * 5000
        self.send_response(200); self.send_header("Content-Length", str(len(body))); self.end_headers(); self.wfile.write(body)

    def do_POST(self):
        self.rfile.read(int(self.headers.get("Content-Length") or 0))
        self.send_response(200); self.send_header("Content-Length", "2"); self.end_headers(); self.wfile.write(b"ok")

    def log_message(self, *a):
        pass


_srv = socketserver.TCPServer(("127.0.0.1", 0), _Handler)
_port = _srv.server_address[1]
threading.Thread(target=_srv.serve_forever, daemon=True).start()
r3 = c.post("/kernel/start", json={"df_id": "t1"}).get_json() or {}
sid3 = r3.get("session_id")
sb = r3.get("sandbox") or {}
check("executor: /kernel/start reports the box as the kernel sees it - user, root or not, capabilities, seccomp, container, mounts, the metadata address",
      all(k in sb for k in ("uid", "user", "root", "caps", "notable_caps", "seccomp", "container", "mounts", "metadata", "docker_socket")) and isinstance(sb["mounts"], list), sb)
hb = (c.get("/health").get_json() or {})
check("executor: /health carries the same facts beside the build", (hb.get("sandbox") or {}).get("uid") == sb.get("uid") and "v69" in str(hb.get("build")), (hb.get("build"), hb.get("sandbox")))


def _run(code):
    return c.post("/kernel/execute", json={"session_id": sid3, "code": code}).get_json() or {}


try:
    o = _run("print(df.a.mean())")
    check("executor: a cell on the data alone reaches nothing, and the route says so", o.get("reaches") == [] and o.get("refused") == "" and not o.get("error"), o)
    o = _run(f"import requests\nr = requests.get('http://127.0.0.1:{_port}/data')\nprint(len(r.content))")
    net = [x for x in o.get("reaches") or [] if x.get("kind") == "net"]
    check("executor: a cell that fetches over HTTP is recorded with the host, the port, the bytes each way and the cell line",
          len(net) == 1 and net[0]["host"] == "127.0.0.1" and net[0]["port"] == _port and net[0]["in"] > 5000 and 0 < net[0]["out"] < 400
          and net[0]["line"] == 2 and net[0]["tls"] is False and not net[0]["failed"] and len(o.get("reaches")) == 1, o.get("reaches"))
    o = _run(f"host = '127.0.0.1'\nr = requests.post(f'http://{{host}}:{_port}/up', data=df.to_csv())\nprint(r.text)")
    net = [x for x in o.get("reaches") or [] if x.get("kind") == "net"]
    check("executor: the text of an f-string is not read as code - f'http://{host}' runs (it had been refused as the http module) - and what the cell sent is counted",
          not o.get("error") and o.get("refused") == "" and len(net) == 1 and net[0]["out"] > 100 and (o.get("stdout") or "").strip() == "ok", o)
    o = _run(f"sess = requests.Session()\nprint(len(sess.get('http://localhost:{_port}/a').content))")
    o2 = _run(f"print(len(sess.get('http://localhost:{_port}/b').content))")
    n1 = [x for x in o.get("reaches") or [] if x.get("kind") == "net"]
    n2 = [x for x in o2.get("reaches") or [] if x.get("kind") == "net"]
    # on a box where localhost resolves to ::1 first (the CI runner), the first address is refused and the second answers: one
    # record, the address that answered, no failure recorded (2026-10-28: the first attempt's refusal had stuck on the record)
    check("executor: a host named by the cell is recorded by its name with the address that answered beside it and no failure, and a connection reused in a later cell is recorded in that cell too",
          len(n1) == 1 and n1[0]["host"] == "localhost" and n1[0]["ip"] == "127.0.0.1" and n1[0]["failed"] == "" and n1[0]["n"] in (1, 2)
          and len(n2) == 1 and n2[0]["host"] == "localhost" and n2[0]["in"] > 5000 and n2[0]["failed"] == ""
          and not any(x.get("kind") == "dns" for x in (o.get("reaches") or []) + (o2.get("reaches") or [])), (o.get("reaches"), o2.get("reaches")))
    o = _run("print(open('/etc/hostname').read().strip() != '')\nbase = '/etc'\nt = pd.read_csv(base + '/passwd', sep=':', header=None)\nprint(t.shape[1])\nprint(len(os.listdir('/')) > 0)")
    files = [(x.get("path"), x.get("op"), x.get("via"), x.get("line")) for x in o.get("reaches") or [] if x.get("kind") == "file"]
    check("executor: a file read outside the data is recorded with its path, through a library too, and a listing of a folder outside the data",
          files == [("/etc/hostname", "read", "code", 1), ("/etc/passwd", "read", "library", 3), ("/", "list", "code", 5)], o.get("reaches"))
    o = _run("nm = 'HO' + 'ME'\nprint(bool(os.environ.get(nm)))\nn = sum(1 for k_, v_ in os.environ.items())\nprint(n > 0)")
    env = [(x.get("name"), x.get("line")) for x in o.get("reaches") or [] if x.get("kind") == "env"]
    check("executor: an environment name the cell reads is recorded, and a walk of the whole environment as '*'", env == [("HOME", 2), ("*", 3)], o.get("reaches"))
    o = _run("import subprocess\nprint(subprocess.run(['ls']).returncode)")
    check("executor: a refused cell comes back with the restricted word beside the notice, not run (2026-10-28: a refusal is not a failure of the code)",
          o.get("refused") == "subprocess" and "Security notice" in (o.get("error") or "") and o.get("reaches") == [], o)
    o = _run("os.execv('/bin/true', ['true'])")
    check("executor: the blacklist's family entries match their members - os.execv is refused as os.exec (the entry had matched nothing)", o.get("refused") == "os.exec", o)
    o = _run("from os import popen\nprint(popen('echo hi').read().strip())")
    proc = [(x.get("command"), x.get("via"), x.get("line")) for x in o.get("reaches") or [] if x.get("kind") == "process"]
    check("executor: a program the cell starts past the blacklist's spelling is recorded with its command", proc == [("echo hi", "os.popen", 2)] and (o.get("stdout") or "").strip() == "hi", o)
    o = _run("try:\n    requests.get('http://169.254.169.254/latest/meta-data/', timeout=2)\n    print('answered')\nexcept Exception as e:\n    print('blocked', type(e).__name__)")
    net = [x for x in o.get("reaches") or [] if x.get("kind") == "net"]
    check("executor: the instance metadata address is refused by the kernel and the attempt recorded as blocked",
          "blocked" in (o.get("stdout") or "") and len(net) == 1 and net[0]["blocked"] is True and net[0]["host"] == "169.254.169.254", o)
    o = _run("try:\n    requests.get('http://127.0.0.1:9/x', timeout=1)\nexcept Exception as e:\n    print(type(e).__name__)")
    net = [x for x in o.get("reaches") or [] if x.get("kind") == "net"]
    check("executor: a connection that failed is still an attempt, recorded with the failure", len(net) == 1 and net[0]["failed"].startswith("ConnectionRefusedError") and net[0]["in"] == 0, o.get("reaches"))
    o = _run("import socketserver\nclass _H(socketserver.BaseRequestHandler):\n    pass\n_s = socketserver.TCPServer(('127.0.0.1', 0), _H)\nprint(_s.server_address[1] > 0)\n_s.server_close()")
    lis = [x for x in o.get("reaches") or [] if x.get("kind") == "listen"]
    check("executor: a listening port the cell opens is recorded", len(lis) == 1 and lis[0]["host"] == "127.0.0.1" and lis[0]["line"] == 4, o.get("reaches"))
    o = _run("from matplotlib import font_manager\nprint(len(font_manager.findSystemFonts()) >= 0)\nimport openpyxl, json, csv\nprint(pd.Timestamp.now(tz='Europe/Prague').tzname() != '')\nwith open('/tmp/_reach_probe.txt', 'w') as fh:\n    fh.write('x')\nprint(DS.save(df.head(2), 'probe.csv') != '')")
    check("executor: what libraries do on a box as a matter of course - the font scan, mime types, time zones - and the cell's own writes under temp and the generated folder are not reaches",
          o.get("reaches") == [] and not o.get("error"), o)
    o = _run("x = 1 / 0")
    check("executor: a failed cell carries no reach records of its own, and the next cell starts clean", o.get("reaches") == [] and "ZeroDivisionError" in (o.get("error") or ""), o)
    # a library scanning the import path for package metadata lists every folder on sys.path - in the image that is /app,
    # the executor's own folder, which is one of the box's places (2026-10-28: "listed /app" on every cell of a statsmodels
    # run); the cell's own listing of such a folder is still a reach, and a folder named in the code only as the head of a
    # longer path is not a choice of that folder
    _pk = os.path.join(os.path.expanduser("~"), ".reach_test_pkgs")
    os.makedirs(os.path.join(_pk, "sub"), exist_ok=True)
    with open(os.path.join(_pk, "sub", "f.txt"), "w") as fh:
        fh.write("hello")
    # a stand-in for a library that scans the import path (pkg_resources, importlib.metadata): a module of its own file, so
    # its frames are not the cell's; under temp, so importing it is no reach
    _lib = tempfile.mkdtemp(prefix="bamboo_reach_lib_")
    with open(os.path.join(_lib, "reachlib.py"), "w") as fh:
        fh.write("import os, sys\n\ndef scan():\n    n = 0\n    for p in list(sys.path):\n        try:\n            n += len(os.listdir(p or '.'))\n        except OSError:\n            pass\n    return n\n")
    o0 = _run(f"import sys as _s\n_s.path.append({_pk!r})\n_s.path.append({_lib!r})\nprint('added')")
    o = _run("import reachlib\nprint(reachlib.scan() >= 0)")
    o2 = _run(f"print(len(os.listdir({_pk!r})) >= 0)")
    names = [x.get("name") for x in (o2.get("registry") or {}).get("namespace") or []]
    check("executor: the record's own state never shows in the registry the analyst reads (v64 had listed _REACHES and _IN_CELL beside the cell's names)",
          o0.get("reaches") == [] and "_REACHES" not in names and "_IN_CELL" not in names and "popen" in names, names)   # _returns is an older stray, not this record's
    o3 = _run(f"print(reachlib.scan() >= 0)\nprint(open({(_pk + '/sub/f.txt')!r}).read())")
    check("executor: a library's scan of a folder on the import path is not a reach; the cell's own listing of it is; a file under it read by the cell is recorded without the library's scan of the folder above",
          o.get("reaches") == [] and not o.get("error")
          and [(x.get("path"), x.get("op"), x.get("via")) for x in o2.get("reaches") or []] == [(_pk, "list", "code")]
          and [(x.get("path"), x.get("op"), x.get("via")) for x in o3.get("reaches") or []] == [(_pk + "/sub/f.txt", "read", "code")], (o, o2.get("reaches"), o3.get("reaches")))
finally:
    c.post("/kernel/stop", json={"session_id": sid3})
    _srv.shutdown()

# the f-string scanner of python 3.11, where an f-string is one token: its text is blanked, its expressions stay, a
# string inside an expression is text too (the executor image runs 3.11; this interpreter may tokenize f-strings itself)
from kernel import _fstring_literal_spans as _spans  # noqa: E402


def _masked(t):
    chars = list(t)
    for x, y in _spans(t):
        for i in range(x, y):
            chars[i] = " "
    return "".join(chars)


_FS = ("f'http://{host}:{port}/up'", "f'a {{ http }} {b:>{w}} c'", 'f\'{"socket"} http\'', "f'''multi {a} http://x'''")
check("kernel: the 3.11 f-string scanner keeps the expressions and blanks the text, the quotes, {{ }} and a string inside an expression",
      [_masked(t) for t in _FS] == ["         {host} {port}    ", "               {b:>{w}}   ", "  {        }      ", "          {a}            "],
      [_masked(t) for t in _FS])

n_fail = sum(1 for _, ok in results if not ok)
print(f"\n{len(results) - n_fail} passed, {n_fail} failed")
sys.exit(1 if n_fail else 0)
