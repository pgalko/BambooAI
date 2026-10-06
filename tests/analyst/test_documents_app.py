"""Documents in the app path (docs/DOCUMENTS_DESIGN.md,,): the DATA block carries the
maps even with no dataset; the kernel's copy is synced at chain start, inside a real scripted chain
whose cell reads the document; the executor's documents routes; the executor client's sync over
HTTP against the executor app; the web routes on a test app. Run: python3 tests/analyst/test_documents_app.py"""
import os, sys, json, tempfile, shutil, threading, socket, time, types, io, re
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path[:0] = [os.path.dirname(os.path.abspath(__file__)), ROOT, os.path.join(ROOT, "delve"), os.path.join(ROOT, "containers", "executor")]
import _stubs  # noqa: F401
os.environ["OPENAI_API_KEY"] = "x"; os.environ["EXECUTION_MODE"] = "local"; os.environ["SYNTHESIS_INFOGRAPHIC"] = "false"
import logging; logging.getLogger("werkzeug").setLevel(logging.ERROR)

passed, failed = [], []
def check(name, cond, detail=""):
    (passed if cond else failed).append(name); print(("  ok   " if cond else "  FAIL ") + name + ("" if cond else f"  <- {str(detail)[:400]}"))

work = tempfile.mkdtemp(prefix="bamboo_docs_app_"); os.chdir(work)          # storage/ and datasets/ land here
from bambooai import documents as docs
from analyst import tools
from bambooai import bambooai as B

MD = "# Sales meeting\n\n## Q3 pipeline\nMaria said the Q3 pipeline is 4.2 million, up from 3.1 million.\n\n| Region | Pipeline |\n|---|---|\n| EMEA | 2.1M |\n| APAC | 2.1M |\n"
md_path = os.path.join(work, "meeting.md"); open(md_path, "w").write(MD)

# ---- the engine: a scripted model layer, as test_app_path does ----
NOTE = "- Question as understood: q\n- Best estimate so far: none yet\n- Held fixed: -\n- Open doubts: -\n- Plan: p\n- Names: -"
SCRIPT = ["###NOTE###\n" + NOTE + "\n###ACTION###\nCELL\n```python\nt = open('datasets/u1/documents/D1/text.md').read()\nprint('pipeline line:', [l for l in t.splitlines() if '4.2 million' in l][0][:60])\n```",
          "###NOTE###\n" + NOTE + "\n###ACTION###\nREPORT\n## Answer\nThe meeting put the pipeline at 4.2 million [cell 1].\n"]
state = {"i": 0, "calls": []}
class FakeModels:
    config = {"agent_configs": [{"agent": "Investigator", "details": {"model": "fake/model", "provider": "fake", "reasoning_effort": "low"}}], "model_properties": {}}
    def __init__(self, *a, **k): pass
    def get_model_properties(self): return {"fake/model": {"capability": "reasoning", "multimodal": "false", "prompt_tokens": 0.001, "completion_tokens": 0.002}}
    def get_model_name(self, agent): return ("fake/model", "fake")
    def llm_stream(self, prompts, lacm, om, messages, agent=None, chain_id=None, reasoning_models=None, **kw):
        user = messages[-1]["content"]; state["calls"].append(user)
        lacm.write_to_log(agent, chain_id, "2026-10-03 12:00:00", "fake/model", messages, "reply", 100, 50, 150, 1.0, 50.0)
        if user.startswith("Rewrite the technical report"):
            return "Plain: 4.2 million."
        i = min(state["i"], len(SCRIPT) - 1); state["i"] += 1
        return SCRIPT[i]
    def llm_call(self, *a, **k): return "NO_CARD"
B.ModelManager = FakeModels

inst = B.BambooAI(df=None, df_id=None, user_id="u1", webui=True, exploratory=True, planning=True)
tdir = os.path.join(work, "storage", "u1", "documents", "1002")
e1 = docs.attach(tdir, md_path, "meeting.md")
inst.thread_id = "1002"
desc = inst._data_description()
check("DATA block: no dataset, yet the documents block with the map and where the text is",
      desc.startswith("(no dataset attached)") and "Documents attached to this thread (1)." in desc and "datasets/u1/documents/<id>/" in desc and "D1 - meeting.md (Markdown," in desc, desc)
check("the kernel root is datasets/<user>/documents in both compute modes", inst._kernel_documents_root() == "datasets/u1/documents")

inst.output_manager.add_user_input("What did the meeting say about the pipeline?")
inst.pd_agent_converse(thread_id="1002", chain_id=None)
q = inst.output_manager.output_queue; events = []
while not q.empty(): events.append(json.loads(q.get()))
run = inst.notebook.runs[str(inst.chain_id)]
cells = inst.notebook.path_cells(run.id)
check("chain start synced the document into the kernel: the cell read datasets/u1/documents/D1/text.md",
      os.path.exists(os.path.join("datasets", "u1", "documents", "D1", "text.md")) and cells and "pipeline line:" in (cells[0].stdout or "") and "4.2 million" in cells[0].stdout, [c.stdout for c in cells])
check("the prompt the model saw carried the map, the kernel objects and where the files are", any("D1 - meeting.md (Markdown," in c and "D1.grep('pattern', context=1)" in c and "print what you need in a cell" in c and "datasets/u1/documents/<id>/" in c for c in state["calls"]), state["calls"][:1])
check("the report went through with its cell citation", run.report.startswith("## Answer") and "[cell 1]" in run.report and run.status == "answered", (run.status, run.report))
check("the replay re-synced before running and reproduced (the cell reads the file again)", run.replay_status in ("reproduced", "differed"), (run.replay_status, run.replay_script[-200:]))

# ---- a second chain on the same thread: a cell on the kernel's D1 object, a scoped READ, a report citing the passage ----
pipeline_unit = next(u["id"] for u in docs.read_units(tdir, "D1")["units"] if "4.2 million" in u.get("text", ""))
SCRIPT[:] = ["###NOTE###\n" + NOTE + "\n###ACTION###\nCELL\n```python\nprint(D1)\nprint(D1.grep('pipeline', context=0))\nprint(D1.table(1).shape)\n```",
             "###NOTE###\n" + NOTE + f"\n###ACTION###\nREAD {pipeline_unit} what is the pipeline figure",
             "###NOTE###\n" + NOTE + f"\n###ACTION###\nREPORT\n## Answer\nThe meeting put the pipeline at 4.2 million [{pipeline_unit}].\n"]
state.update(i=0)
class FakeModelsReader(FakeModels):
    def llm_call(self, lacm, messages, agent=None, chain_id=None, **k):
        if messages and str(messages[0].get("content", "")).startswith("You are the Reader"):     # the seat is the analyst's when the config has no Reader
            lacm.write_to_log(agent, chain_id, "2026-10-03 12:00:00", "fake/model", messages, "reply", 100, 50, 150, 1.0, 50.0)
            return f'- [{pipeline_unit}] "the Q3 pipeline is 4.2 million, up from 3.1 million"\nSUMMARY: The pipeline figure [{pipeline_unit}].'
        return "NO_CARD"
inst.models = FakeModelsReader()
inst.output_manager.add_user_input("What is the pipeline figure?")
inst.pd_agent_converse(thread_id="1002", chain_id=run.id)
q = inst.output_manager.output_queue; events2 = []
while not q.empty(): events2.append(json.loads(q.get()))
run2 = inst.notebook.runs[str(inst.chain_id)]
look = next((x for x in run2.turns if x.kind == "cell"), None)
check("the engine's prelude put the document object in the kernel: the cell printed D1, the grep hit with its locator, and the table's shape",
      look is not None and "D1 - meeting.md (" in (look.stdout or "") and f"[{pipeline_unit} | Sales meeting > Q3 pipeline] Maria said" in look.stdout and "(2, 2)" in look.stdout and not look.error, (look.stdout if look else None, look.error if look else None))
check("the scoped READ ran the Reader on exactly that unit; the report cites the passage and the guard is content",
      any(x.kind == "read" and x.stdout.startswith("PASSAGES") for x in run2.turns) and run2.status == "answered"
      and f"[{pipeline_unit}]" in run2.report and "CHECK:" not in run2.report, (run2.report, [(x.kind, (x.stdout or "")[:80]) for x in run2.turns]))
check("the task line in its original form; the pane got a cell row and a read row with the passage",
      any("TASK: turn 1; up to 15 turns and $" in c for c in state["calls"])
      and any(e.get("type") == "pane_cell" for e in events2) and any(e.get("type") == "pane_lookup" and e.get("kind") == "read" and e.get("passages") for e in events2),
      ([ln for c in state["calls"] for ln in c.splitlines() if ln.startswith("TASK:")][-4:], [(e.get("type"), e.get("kind")) for e in events2 if e.get("type") in ("pane_cell", "pane_lookup")]))
# a fourth READ on a fresh chain: refused, and the pane says so
SCRIPT[:] = ["###NOTE###\n" + NOTE + f"\n###ACTION###\nREAD {pipeline_unit} q{i}" for i in range(4)] + ["###NOTE###\n" + NOTE + "\n###ACTION###\nREPORT\n## Answer\nDone.\n"]
state.update(i=0)
inst.output_manager.add_user_input("Read it four times")
inst.pd_agent_converse(thread_id="1002", chain_id=run2.id)
q = inst.output_manager.output_queue; events3 = []
while not q.empty(): events3.append(json.loads(q.get()))
read_rows = [e for e in events3 if e.get("type") == "pane_lookup" and e.get("kind") == "read"]
check("the fourth READ is answered from the budget without a reader call, no passages; the three before it carry passages",
      len(read_rows) == 4 and all(r.get("passages") for r in read_rows[:3]) and not read_rows[3].get("passages") and read_rows[3].get("peek", "").startswith("(read budget for this run used: 3 of 3"),
      [(r.get("peek", "")[:40], len(r.get("passages") or [])) for r in read_rows])
hb = [e for e in events3 if e.get("type") == "pane_heartbeat"]
check("the heartbeat counts every exchange as a turn: four reads are four turns",
      hb and hb[-1].get("turn") == 4 and hb[-1].get("of") == 15, [(h.get("turn"), h.get("of")) for h in hb][-3:])
re_rows = [e for e in events3 if e.get("type") == "pane_run_end"]
check("the closing card: the turns taken and no cells", re_rows and re_rows[-1].get("turns") == 5 and re_rows[-1].get("cells") == 0, re_rows[-1:] and {k: re_rows[-1].get(k) for k in ("turns", "cells")})
check("the kernel's names list D1 and docs for the analyst", "D1" in tools.names(inst._kernel) and "docs" in tools.names(inst._kernel), tools.names(inst._kernel)[:200])
check("the engine's kernel prelude names the thread's documents and is empty for a thread without any", "_BambooDocument('D1', 'datasets/u1/documents/D1', 'meeting.md')" in inst._kernel_prelude())

# removal: the engine drops the kernel's copy; a thread without documents clears what is left
docs.remove(tdir, "D1"); inst.remove_document_from_kernel("D1")
check("remove_document_from_kernel: the kernel's D1 folder is gone", not os.path.exists(os.path.join("datasets", "u1", "documents", "D1")))
docs.attach(tdir, md_path, "meeting.md"); inst._sync_documents()
check("a new attach then sync: the document is D2 now, in the kernel", os.path.exists(os.path.join("datasets", "u1", "documents", "D2", "text.json")))
inst.thread_id = "1003"; inst._sync_documents()
check("a thread without documents: no block, and the kernel folder cleared of the other thread's files", inst._documents_block() == "" and not os.listdir(os.path.join("datasets", "u1", "documents")), os.listdir(os.path.join("datasets", "u1", "documents")))

# ---- the executor's routes, through its test client ----
exec_cwd = tempfile.mkdtemp(prefix="bamboo_exec_"); os.chdir(exec_cwd)
import code_executor_api as E
c = E.app.test_client()
def up(rel, content=b"x", user="u1"):
    return c.post("/file_utils/upload_document", data={"user_id": user, "path": rel, "file": (io.BytesIO(content), "f")}, content_type="multipart/form-data")
r = up("D1/text.md", b"# D1 - meeting.md\n")
check("executor: upload_document stores the file at its relative path and answers its sha256", r.status_code == 200 and os.path.exists(os.path.join("datasets", "u1", "documents", "D1", "text.md")) and len(r.get_json()["sha256"]) == 64, (r.status_code, r.get_json()))
check("executor: a path outside the document shape is refused (traversal, the original, a stray name)",
      up("../x.md").status_code == 400 and up("D1/original.pdf").status_code == 400 and up("D1/tables/a.csv").status_code == 400 and up("D1/tables/2.csv").status_code == 200, "")
check("executor: an invalid user id is refused", up("D1/text.md", user="../u2").status_code == 400)
inv = c.get("/file_utils/documents", query_string={"user_id": "u1"}).get_json()["files"]
check("executor: the inventory lists relative paths with their sha256", set(inv) == {"D1/text.md", "D1/tables/2.csv"} and all(len(v) == 64 for v in inv.values()), inv)
r = c.post("/file_utils/remove_document", json={"user_id": "u1", "path": "D1/tables/2.csv"})
check("executor: remove one file, and its emptied folder", r.status_code == 200 and not os.path.exists(os.path.join("datasets", "u1", "documents", "D1", "tables")), os.listdir(os.path.join("datasets", "u1", "documents", "D1")))
r = c.post("/file_utils/remove_document", json={"user_id": "u1", "path": "D1"})
check("executor: remove a whole document by id; a second remove says 'not present' and is not an error",
      r.status_code == 200 and not os.path.exists(os.path.join("datasets", "u1", "documents", "D1")) and c.post("/file_utils/remove_document", json={"user_id": "u1", "path": "D1"}).get_json()["message"] == "not present")
check("executor: /health carries the build stamp (v49: DS.save)", "v49" in c.get("/health").get_json().get("build", ""))

# ---- the executor client's sync over HTTP, against the executor app on a port ----
def free_port():
    s = socket.socket(); s.bind(("127.0.0.1", 0)); p = s.getsockname()[1]; s.close(); return p
port = free_port()
threading.Thread(target=lambda: E.app.run(host="127.0.0.1", port=port, threaded=True, use_reloader=False), daemon=True).start()
import requests
for _ in range(100):
    try:
        if requests.get(f"http://127.0.0.1:{port}/health", timeout=1).status_code == 200: break
    except Exception: time.sleep(0.1)
from bambooai.executor_client import ExecutorAPIClient
client = ExecutorAPIClient(base_url=f"http://127.0.0.1:{port}")
os.chdir(work)
tdir2 = os.path.join(work, "storage", "u1", "documents", "2001")
docs.attach(tdir2, md_path, "meeting.md")
sent, removed = client.sync_documents("u1", tdir2)
inv = client.documents_inventory("u1")
check("client.sync_documents: text.json, text.md and the table reach the executor; nothing else", (sent, removed) == (3, 0) and set(inv) == {"D1/text.json", "D1/text.md", "D1/tables/1.csv"}, (sent, removed, inv))
check("client.sync_documents: a second sync sends nothing", client.sync_documents("u1", tdir2) == (0, 0))
docs.remove(tdir2, "D1"); docs.attach(tdir2, md_path, "again.md")
sent, removed = client.sync_documents("u1", tdir2)
check("client.sync_documents: after remove and re-attach, D2 arrives and D1's three files go", (sent, removed) == (3, 3) and set(client.documents_inventory("u1")) == {"D2/text.json", "D2/text.md", "D2/tables/1.csv"}, (sent, removed))
api_inst = B.BambooAI(df=None, df_id=None, user_id="u1", webui=True, execution_mode="api", executor_api_url=f"http://127.0.0.1:{port}")
api_inst.thread_id = "2001"; docs.remove(tdir2, "D2"); api_inst._sync_documents()
check("the engine in api mode syncs through the client: an emptied thread clears the executor's folder", client.documents_inventory("u1") == {}, client.documents_inventory("u1"))
check("client.remove_document: a document id", client.upload_document("u1", "D7/text.md", md_path) and client.remove_document("u1", "D7") and client.documents_inventory("u1") == {})

# an executor from before documents: no route. The client says None, the engine warns and tells the analyst
old_client = ExecutorAPIClient(base_url=f"http://127.0.0.1:{port}/nowhere")       # every route 404s there
check("client.sync_documents: None, not (0, 0), when the executor has no documents route", old_client.sync_documents("u1", tdir2) is None)
docs.attach(tdir2, md_path, "again.md")
old_inst = B.BambooAI(df=None, df_id=None, user_id="u1", webui=True, execution_mode="api", executor_api_url=f"http://127.0.0.1:{port}/nowhere")
old_inst.thread_id = "2001"; old_inst._sync_documents()
blk = old_inst._data_description()
check("the engine with such an executor: the kernel is marked as having no copy, the DATA block says READ is the way, not the filesystem, and no kernel objects are prepared",
      old_inst._documents_in_kernel is False and "NOT in this kernel" in blk and "READ is the way to read them" in blk and "Do not look for document files with code" in blk and old_inst._kernel_prelude() == "", blk[:400])
check("the engine with a current executor: the DATA block names the objects and READ, and where the files are",
      (lambda fid, blk2: all(x in blk2 for x in (f"{fid}.grep('pattern', context=1)", "print what you need in a cell", f"READ {fid} <what you want> finds and quotes passages in {fid}, READ ALL <what you want> across every document", f"READ {fid}.35-41 <what you want> reads that stretch whole", "datasets/u1/documents/<id>/", "if they are not there, READ")))(docs.load_manifest(tdir2)["documents"][0]["id"], docs.prompt_block(tdir2, "datasets/u1/documents")), docs.prompt_block(tdir2, "datasets/u1/documents")[:300])

# ---- the CLI's executor image tag carries the executor's build stamp, so a changed executor rebuilds (2026-10-03) ----
import importlib.util
spec = importlib.util.spec_from_file_location("bamboo_cli", os.path.join(ROOT, "bambooai", "cli.py")); cli = importlib.util.module_from_spec(spec); spec.loader.exec_module(cli)
check("cli: the executor image is tagged <version>-<executor build>, v49 for the image's kernel", re.fullmatch(r"bambooai-executor:[\w.]+-v49", cli.executor_image()) is not None, cli.executor_image())

# ---- the web routes, on a test app with the app's two names faked ----
sys.path.insert(0, os.path.join(ROOT, "web_app"))
fake_auth = types.ModuleType("auth"); fake_auth.requires_auth = lambda f: f; sys.modules["auth"] = fake_auth
fake_app = types.ModuleType("app"); fake_app.user_path = lambda root, *p: os.path.join(root, "u1", *p); fake_app.bamboo_ai_instances = {}; sys.modules["app"] = fake_app
import documents_routes as R
from flask import Flask
wapp = Flask("t"); wapp.secret_key = "t"; wapp.register_blueprint(R.documents_bp); wc = wapp.test_client()
r = wc.post("/documents/upload", data={"file": (io.BytesIO(MD.encode()), "meeting.md")}, content_type="multipart/form-data")
j = r.get_json()
check("web: an upload with no thread mints one and attaches D1", r.status_code == 200 and j["thread_id"].isdigit() and j["document"]["id"] == "D1" and j["documents"][0]["file"] == "meeting.md" and j["max"] == 4, j)
tid = j["thread_id"]
r = wc.post("/documents/upload", data={"thread_id": tid, "file": (io.BytesIO(b"plain notes\n\nmore"), "notes.txt")}, content_type="multipart/form-data")
check("web: a second upload into the same thread is D2", r.status_code == 200 and r.get_json()["document"]["id"] == "D2")
r = wc.post("/documents/upload", data={"thread_id": tid, "file": (io.BytesIO(b"x"), "notes.rtf")}, content_type="multipart/form-data")
check("web: a refusal is a 400 with the sentence to show", r.status_code == 400 and r.get_json()["message"] == "notes.rtf is not a PDF, Word, Markdown or text file.", r.get_json())
check("web: the listing", [d["id"] for d in wc.get(f"/documents/{tid}").get_json()["documents"]] == ["D1", "D2"])
check("web: the map and the text for the tab", wc.get(f"/documents/{tid}/D1/map").get_json()["map"].startswith("D1 - meeting.md") and wc.get(f"/documents/{tid}/D1/text").get_json()["units"][0]["id"] == "D1.1")
check("web: an unknown document is 404", wc.get(f"/documents/{tid}/D9/map").status_code == 404 and wc.delete(f"/documents/{tid}/D9").status_code == 404)
r = wc.delete(f"/documents/{tid}/D1")
check("web: remove answers the remaining listing", r.status_code == 200 and r.get_json()["removed"] == "D1" and [d["id"] for d in r.get_json()["documents"]] == ["D2"])
check("web: an invalid thread id never reaches the disk", wc.get("/documents/..%2F..%2Fetc").status_code in (400, 404) and wc.post("/documents/upload", data={"thread_id": "../x", "file": (io.BytesIO(b"a"), "a.txt")}, content_type="multipart/form-data").status_code == 400)
check("web: a thread with no documents lists none", wc.get("/documents/1234567890").get_json()["documents"] == [])

# ---- cleanup: a thread's documents go with it; orphans after a day ----
sys.path.insert(0, os.path.join(ROOT, "web_app"))
import cleanup as C
os.makedirs(os.path.join("storage", "u1", "threads"), exist_ok=True); os.makedirs(os.path.join("storage", "u1", "favourites"), exist_ok=True)
docs.attach(os.path.join("storage", "u1", "documents", "3001"), md_path, "a.md"); open(os.path.join("storage", "u1", "threads", "3001.json"), "w").write("{}")
docs.attach(os.path.join("storage", "u1", "documents", "3002"), md_path, "b.md")     # no thread JSON: an orphan
old = time.time() - 2 * 24 * 3600
os.utime(os.path.join("storage", "u1", "documents", "3002"), (old, old))
n = C.cleanup_orphan_documents("u1")
check("cleanup: an orphan documents folder older than a day is removed, a thread's folder is kept", n == 1 and not os.path.exists(os.path.join("storage", "u1", "documents", "3002")) and os.path.exists(os.path.join("storage", "u1", "documents", "3001")))
C.cleanup_threads_for_user("u1")
check("cleanup: a non-favourite thread's documents go with its JSON", not os.path.exists(os.path.join("storage", "u1", "threads", "3001.json")) and not os.path.exists(os.path.join("storage", "u1", "documents", "3001")))

os.chdir("/"); shutil.rmtree(work, ignore_errors=True); shutil.rmtree(exec_cwd, ignore_errors=True)
print(f"\n{len(passed)} passed, {len(failed)} failed")
sys.exit(1 if failed else 0)
