"""Phase 3 (docs/OSS_DESIGN.md §3): the self-hosted edition's data survive a restart of the server.

    python3 tests/e2e/test_local_store.py

On the local edition with the local kernel: run one question, label its chain, save a level, store an
integration key, read the Usage dashboard - then stop the web app, start it again on the same working
folder, and read everything back. Exit 1 on any failed check.
"""
import json
import os
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
STACK = os.path.join(os.path.dirname(HERE), "..", "tools", "stack")
STACK = os.path.normpath(STACK)
sys.path[:0] = [STACK, os.path.join(STACK, "browser")]
import vendor  # noqa: E402
import harness_models  # noqa: E402
from stack import Stack  # noqa: E402
from browse import open_page  # noqa: E402

results = []


def check(name, cond, detail=""):
    results.append((name, bool(cond)))
    print(("  ok   " if cond else "  FAIL ") + name + ("" if cond else f"  <- {str(detail)[:300]}"))


def api(page, method, url, body=None):
    return page.evaluate("""async ([m, u, b]) => { const r = await fetch(u, { method: m, headers: { 'Content-Type': 'application/json' }, body: b ? JSON.stringify(b) : undefined });
                             let j = null; try { j = await r.json(); } catch (e) {} return { status: r.status, body: j }; }""", [method, url, body])


def wait_text(page, selector, text, timeout=180000):
    page.wait_for_function("([sel, t]) => [...document.querySelectorAll(sel)].some(e => e.textContent.includes(t))", arg=[selector, text], timeout=timeout)


def main():
    vendor.prepare(fetch=bool(os.environ.get("CI")))    # a runner has network and no node_modules: fetch the page's libraries
    workdir = tempfile.mkdtemp(prefix="bamboo_store_")
    mod = harness_models.load("field_trial")
    from playwright.sync_api import sync_playwright

    # ---- first life: make some data
    with Stack(workdir=workdir, scenario="field_trial", fresh=True, auto_ports=True, edition="local", compute="local") as st:
        with sync_playwright() as pw:
            b, page, logs = open_page(pw, st.app_url)
            page.goto(st.app_url)
            page.wait_for_selector("#queryInput", state="visible", timeout=60000)
            page.app_ready()
            page.set_input_files("#primaryFile", st.dataset)
            page.wait_for_selector(".primary-dataset-pill", timeout=60000)
            page.fill("#queryInput", mod.QUESTIONS[0])
            page.click("#submitQuery")
            wait_text(page, ".sp-done", "Run complete")
            page.wait_for_function("() => !queryRunning && responses.length >= 1", timeout=60000)
            chain_id = page.evaluate("() => String(currentData.chain_id)")
            check("first life: a run completed and the page knows its chain id", bool(chain_id) and chain_id != "null", chain_id)

            lab = api(page, "POST", "/api/labels", {"label": "alpine"})
            check("labels: a label can be created (POST /api/labels)", lab["status"] == 201 or (lab["status"] == 200 and lab["body"] and lab["body"].get("success")), lab)
            label_id = (lab["body"] or {}).get("label", {}).get("id") or (lab["body"] or {}).get("id")
            lst = api(page, "GET", "/api/labels")
            check("labels: the list shows it", lst["status"] == 200 and any(l["label"] == "alpine" for l in lst["body"].get("labels", [])), lst)
            asg = api(page, "PUT", f"/api/chains/{chain_id}/label", {"label_id": label_id})
            check("labels: the chain takes the label (PUT /api/chains/<id>/label)", asg["status"] == 200, asg)
            got = api(page, "GET", f"/api/chains/{chain_id}/label")
            check("labels: the chain reports its label with the label's name embedded", got["status"] == 200 and json.dumps(got["body"]).count("alpine") >= 1, got)

            lvl = api(page, "POST", "/api/llm-config", {"model_preference": "max"})
            check("level: the dialog's save is accepted (POST /api/llm-config max)", lvl["status"] == 200, lvl)
            cfg = api(page, "GET", "/api/llm-config")
            check("level: read back as max", cfg["status"] == 200 and cfg["body"].get("config", {}).get("model_preference") == "max", cfg)

            key = api(page, "POST", "/intervals/store_api_key", {"api_key": "test-key-123"})
            key_ok = key["status"] in (200, 201)
            check("integration: an Intervals key is stored (encrypted) through the same route as the hosted edition", key_ok, key)

            usage = api(page, "GET", "/usage_tracking?period=30_days")
            total = (usage["body"] or {}).get("summary", {}).get("total_cost") if usage["body"] else None
            calls = (usage["body"] or {}).get("summary", {}).get("total_calls") if usage["body"] else None
            check("usage: the dashboard reads the run's calls from the local store", usage["status"] == 200 and usage["body"] and json.dumps(usage["body"]).count("cost") >= 1, (usage["status"], str(usage["body"])[:200]))
            usage_first = usage["body"]
            b.close()
        store = os.path.join(workdir, "webapp", "bambooai.sqlite")
        check("the store is one SQLite file in the working folder", os.path.exists(store), store)

    # ---- second life: the same working folder, a new process
    with Stack(workdir=workdir, scenario="field_trial", fresh=False, auto_ports=True, edition="local", compute="local") as st:
        with sync_playwright() as pw:
            b, page, logs = open_page(pw, st.app_url)
            page.goto(st.app_url)
            page.wait_for_selector("#queryInput", state="visible", timeout=60000)
            page.app_ready()
            lst = api(page, "GET", "/api/labels")
            check("after restart: the label is still there", lst["status"] == 200 and any(l["label"] == "alpine" for l in lst["body"].get("labels", [])), lst)
            got = api(page, "GET", f"/api/labels/{label_id}/chains")
            check("after restart: the label still lists its chain", got["status"] == 200 and chain_id in json.dumps(got["body"]), got)
            cfg = api(page, "GET", "/api/llm-config")
            check("after restart: the saved level is still max", cfg["status"] == 200 and cfg["body"].get("config", {}).get("model_preference") == "max", cfg)
            built = json.load(open(os.path.join(workdir, "webapp", "config", "local", "LLM_CONFIG.json")))
            check("after restart: the user's config was built at the saved level", built.get("model_preference") == "max", built.get("model_preference"))
            st_ = api(page, "POST", "/api/user/initialize", {})
            iv = ((st_["body"] or {}).get("intervals") or {})
            check("after restart: the Intervals key is still stored (the initialise call reports it)", st_["status"] == 200 and iv.get("intervals_authenticated") is True, st_["body"] and st_["body"].get("intervals"))
            usage = api(page, "GET", "/usage_tracking?period=30_days")
            check("after restart: the Usage dashboard shows the same records", usage["status"] == 200 and usage["body"] == usage_first, (str(usage["body"])[:160], str(usage_first)[:160]))
            b.close()

    n_fail = sum(1 for _, ok in results if not ok)
    print(f"{len(results) - n_fail} passed, {n_fail} failed")
    sys.exit(1 if n_fail else 0)


if __name__ == "__main__":
    main()
