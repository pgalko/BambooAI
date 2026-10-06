"""End to end: the real web app, the real executor and the real page in headless Chromium,
driven through the local stack (tools/stack) with the scripted analyst. Asserts what the person
sees and what lands on disk, plus what the app asked the orchestrator for.

    python3 tests/e2e/test_stack.py            # ~2 minutes; needs playwright + chromium

Skips (exit 0, one line) when playwright is not installed, so run_battery.sh can include it
unconditionally.
"""
import glob
import json
import os
import re
import shutil
import sys
import tempfile
import time

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path[:0] = [os.path.join(ROOT, "tools", "stack"), os.path.join(ROOT, "tools", "stack", "browser")]

try:
    from playwright.sync_api import sync_playwright
except Exception:                                          # noqa: BLE001
    print("playwright not installed: the end-to-end suite is skipped")
    sys.exit(0)

import vendor                                              # noqa: E402
import harness_models                                      # noqa: E402
from stack import Stack                                    # noqa: E402
from browse import open_page                               # noqa: E402

passed, failed = [], []


def check(name, cond, detail=""):
    (passed if cond else failed).append(name)
    print(("  ok   " if cond else "  FAIL ") + name + ("" if cond else f"  <- {str(detail)[:300]}"))


def wait_run_end(page, n_responses, timeout=180000):
    """The run is over for the page: the closing card is up, the `end` event has been handled (the rank stub
    built, the snapshot saved) and the chain is in responses[]."""
    wait_text(page, ".sp-done", "Run complete", timeout)
    page.wait_for_function("(n) => typeof queryRunning !== 'undefined' && !queryRunning && typeof responses !== 'undefined' && responses.length >= n",
                           arg=n_responses, timeout=timeout)
    page.wait_for_timeout(300)


def wait_text(page, selector, text, timeout=180000):
    page.wait_for_function("([sel, t]) => [...document.querySelectorAll(sel)].some(e => e.textContent.includes(t))",
                           arg=[selector, text], timeout=timeout)


def main():
    edition = "local" if "--edition" in sys.argv and sys.argv[sys.argv.index("--edition") + 1] == "local" else "hosted"
    compute = sys.argv[sys.argv.index("--compute") + 1] if "--compute" in sys.argv else "orchestrator"
    vendor.prepare(fetch=bool(os.environ.get("CI")))    # a runner has network and no node_modules: fetch the page's libraries
    workdir = tempfile.mkdtemp(prefix=f"bamboo_e2e_{edition}_")
    mod = harness_models.load("field_trial")
    q1, q2 = mod.QUESTIONS[0], mod.QUESTIONS[1]
    USER = "local" if edition == "local" else "localuser"        # BAMBOO_USER in the local edition; the Auth0 stand-in's id in the hosted one
    print(f"edition: {edition}")
    print(f"compute: {compute}")
    with Stack(workdir=workdir, scenario="field_trial", fresh=True, auto_ports=True, edition=edition, compute=compute) as st:
        with sync_playwright() as pw:
            b, page, logs = open_page(pw, st.app_url)
            navs, starts = [], []
            page.on("load", lambda: navs.append(page.url))
            page.on("request", lambda r: starts.append(r.url.rsplit("/", 1)[-1]) if r.url.endswith(("/new_conversation", "/api/user/initialize")) else None)
            page.goto(st.app_url)
            page.wait_for_selector("#queryInput", state="visible", timeout=60000)
            page.app_ready()
            check("cold load: the composer is visible and the app reports its initialisation complete", True)
            check("cold load is ONE load (v63): no reload into ?new=true; the initialise call and /new_conversation once each",
                  len(navs) == 1 and "new=true" not in page.url and starts.count("initialize") == 1 and starts.count("new_conversation") == 1, (navs, starts))
            page.wait_for_function("() => /Ready|Local|Docker/.test(document.querySelector('#containerStatusText').textContent)", timeout=30000)
            chip = page.inner_text("#containerStatusText")
            check("the workspace gate released and the chip reads " + {"orchestrator": "Ready", "local": "Local", "direct": "Docker"}[compute],
                  chip == {"orchestrator": "Ready", "local": "Local", "direct": "Docker"}[compute], chip)
            check("the pane is empty (the 'New workflow started' sentence is retired)", page.inner_text("#streamOutput").strip() == "", page.inner_text("#streamOutput"))

            page.set_input_files("#primaryFile", st.dataset)
            page.wait_for_selector(".primary-dataset-pill", timeout=60000)
            check("upload through the real file input: the dataset pill appears", True)

            page.fill("#queryInput", q1)
            page.evaluate("setMode('deep')")
            page.click("#submitQuery")
            t0 = time.time()
            page.wait_for_selector(".sp-row.fail", timeout=120000)
            check("a failed cell shows as a failed row, rolled back", True)
            wait_run_end(page, 1)
            elapsed = time.time() - t0
            done = page.inner_text(".sp-done")
            check("the closing card reports the replay reproduced the cited numbers", "Replay reproduced" in done, done)
            check("the closing card counts 3 cells with 1 failed", "Cells 3 (1 failed)" in done.replace("\n", " ") or ("3" in done and "1 failed" in done), done)
            turns = page.evaluate("() => document.querySelectorAll('.sp-turn').length")
            check("one card per model call (6 analyst turns and the rewrite; no review outside Adaptive)", turns == 7, turns)
            # a dataset the analyst saved (DS.save in the estimate cell): one download pill under the REPLAY row, none in the closing card (2026-10-06)
            ds_pills = page.evaluate("() => [...document.querySelectorAll('.sp-pill.ds')].map(e => e.textContent)")
            check("the dataset the analyst saved shows as one download pill under the REPLAY row, and the closing card does not repeat it",
                  len(ds_pills) == 1 and "plot_means.csv" in ds_pills[0] and page.evaluate("() => document.querySelectorAll('.sp-done .sp-pill.ds').length") == 0, ds_pills)
            tabs = page.evaluate("() => [...document.querySelectorAll('#tabContainer .tab')].map(e => e.textContent)")
            check("no Generated datasets tab in the right pane (2026-10-06): the files are the pane's pills", not any('enerated' in t for t in tabs), tabs)
            if edition == "hosted":
                # the Dataset cache (through the executor): the file under Generated; its details with the buttons in view without scrolling
                page.click("#datasetManagerPill")
                page.wait_for_selector("#generatedDatasetList .dataset-item", timeout=15000)
                page.click("#generatedDatasetList .dataset-item")
                page.wait_for_selector("#datasetDetails .dataset-actions .dataset-download-btn", timeout=15000)
                geom = page.evaluate("""() => { const panel = document.querySelector('.dataset-details-panel'); const pr = panel.getBoundingClientRect();
                    const ar = document.querySelector('#datasetDetails .dataset-actions').getBoundingClientRect(); const cols = document.querySelector('#datasetDetails .dataset-columns');
                    return { name: document.querySelector('#generatedDatasetList .dataset-item').textContent, buttonsInView: ar.bottom <= pr.bottom + 1 && ar.top >= pr.top, panelScrolls: panel.scrollHeight > panel.clientHeight + 1,
                             columnsOwnScroll: cols ? getComputedStyle(cols).overflowY === 'auto' : null }; }""")
                check("Dataset cache: the saved file is listed under Generated, its Load/Download/Remove buttons are in view without scrolling, and the columns list is the part that scrolls",
                      "plot_means.csv" in geom["name"] and geom["buttonsInView"] and not geom["panelScrolls"] and geom["columnsOwnScroll"] is True, geom)
                page.click("#datasetManagerModal .close")
            pills = page.evaluate("() => [...document.querySelectorAll('.sp-pill')].map(e => e.textContent)")
            check("the search row carries the two source pills", any("fao.org" in p for p in pills) and any("wiley" in p for p in pills), pills)
            page.evaluate("activateTab('answer')")
            page.wait_for_timeout(300)
            answer = page.inner_text("#content-answer")
            check("the Answer tab shows the report with the estimate the kernel printed",
                  "t/ha" in answer and "cell 2" in answer.lower() or "cell 2" in answer, answer[:200])
            page.evaluate("activateTab('plot')")
            page.wait_for_timeout(300)
            imgs = page.evaluate("() => document.querySelectorAll('#content-plot img').length")
            check("the Plots tab holds the figure the replay captured", imgs >= 1, imgs)
            plots_link = page.evaluate("() => { const l = [...document.querySelectorAll('.sp-done a, .sp-done .link')].map(e => e.textContent).find(t => /Plots \\(\\d+\\)/.test(t)); return l || (document.querySelector('.sp-done') || {}).textContent || ''; }")
            check("the replay captured both figures: the matplotlib PNG and the plotly JSON (the closing card says Plots (2))", "Plots (2)" in plots_link, plots_link[:120])

            # the prompt button (v65): the card of turn 4 shows the prompt turn 4 received, not the seat's first
            def prompt_of(turn):
                page.click(f'.sp-turn[data-turn="{turn}"] .sp-prompt')
                page.wait_for_function("() => { const u = document.getElementById('userInstructions'); return u && /TASK: turn/.test(u.textContent); }", timeout=15000)
                got = {"title": page.inner_text("#agentInstructionsTitle"), "user": page.inner_text("#userInstructions")}
                page.evaluate("() => { const m = document.getElementById('agentInstructionsModal'); if (m) m.style.display = 'none'; }")
                page.wait_for_timeout(200)
                return got
            p4 = prompt_of(4)
            # exchange 4 is the third cell turn: the SEARCH at exchange 2 spent none (2026-10-03)
            check("prompt button: turn 4's card opens the prompt of exchange 4 ('TASK: turn 4;' - every exchange a turn without documents), titled call 4", "TASK: turn 4;" in p4["user"] and "call 4 of" in p4["title"], (p4["title"], p4["user"][-160:]))
            p1 = prompt_of(1)
            check("prompt button: turn 1's card still opens turn 1's prompt", "TASK: turn 1;" in p1["user"], p1["user"][-120:])

            page.fill("#queryInput", q2)
            page.click("#submitQuery")
            wait_text(page, "#chainPosition", "chain 2 of 2", 60000)
            wait_run_end(page, 2)
            row = page.evaluate("() => [...document.querySelectorAll('.sp-row')].map(e => e.textContent).join(' | ')")
            check("the follow-up runs on the warm kernel: its cell is numbered 4 along the path", "[4]" in row, row[:200])

            # a document attached to the thread (docs/DOCUMENTS_DESIGN.md, phase A): the real file input, the blue pill,
            # the view, a chain whose cell reads the kernel's copy, and the copy coming back after the kernel forgets
            notes = os.path.join(workdir, "data", mod.DOC_NAME)
            with open(notes, "w", encoding="utf-8") as fh:
                fh.write(mod.DOC_TEXT)
            page.set_input_files("#documentFile", notes)
            page.wait_for_function("() => { const p = document.getElementById('documentsPill'); return p && p.className.includes('success'); }", timeout=60000)
            check("document upload through the real file input: the Documents pill reads 1/4 and is the blue one",
                  page.inner_text("#documentsPill .label").strip() == "Documents (1/4)" and "documents-pill" in page.get_attribute("#documentsPill", "class"), page.inner_text("#documentsPill"))
            try:
                page.wait_for_function("() => { const m = document.getElementById('documentsModal'); return !!m && m.style.display === 'flex' && /D1\\.\\d/.test(m.innerText) && /wet season/.test(m.innerText) && /Weather/.test(m.innerText); }", timeout=15000)
                view_ok = True
            except Exception:                                 # noqa: BLE001
                view_ok = False
            check("the Documents view opened on the new document: its units with their locators, the Weather section", view_ok,
                  page.evaluate("() => { const m = document.getElementById('documentsModal'); return m ? [m.style.display, m.innerText.slice(0, 200)] : null; }"))
            page.evaluate("documentsClose()")
            tid_now = str(page.evaluate("() => currentData.thread_id"))
            man = json.load(open(os.path.join(workdir, "webapp", "storage", USER, "documents", tid_now, "manifest.json")))
            check("the upload parsed the document into units with a map: the manifest names the file as D1",
                  man["documents"][0].get("id") == "D1" and man["documents"][0].get("file") == mod.DOC_NAME and man["documents"][0].get("units", 0) > 0, man["documents"][0])
            page.fill("#queryInput", mod.DOC_QUESTION)
            page.click("#submitQuery")
            wait_text(page, "#chainPosition", "chain 3 of 3", 60000)
            wait_run_end(page, 3)
            page.evaluate("activateTab('answer')")
            page.wait_for_timeout(300)
            answer = page.inner_text("#content-answer")
            check("the analyst looked with D1.grep, read the stretch through the Reader, and the report quotes the passage with its number citing the passage, not a cell",
                  "40%" in answer and re.search(r"\bD1\.\d+\b", answer) is not None and "cell 1" not in answer.lower(), answer[:240])   # the citation reads D1.n: it is a chip now
            rows_doc = page.evaluate("() => [...document.querySelectorAll('.sp-row')].map(e => [e.className, e.textContent])")
            check("the pane: the grep's cell row (numbered along the thread) and a READ row with its passage count",
                  any(re.search(r"In\s*\[\d+\]", txt) and "field_notes" in txt for c, txt in rows_doc) and any("read" in c.split() and "1 passage" in txt for c, txt in rows_doc), rows_doc)
            # the [D1.n] chip in the answer (D45): the passage a READ returned on hover, a click opening the view at the unit
            chip = page.evaluate("() => { const c = document.querySelector('#content-answer .cite.doc'); return c ? [c.textContent, c.getAttribute('data-unit'), c.getAttribute('title')] : null; }")
            check("the answer's [D1.n] is a chip: blue, the unit id, the READ's passage as its hover text",
                  chip is not None and re.fullmatch(r"D1\.\d+", chip[0] or "") and chip[1] == chip[0] and "40%" in (chip[2] or ""), chip)
            page.click("#content-answer .cite.doc")
            page.wait_for_function("() => { const m = document.getElementById('documentsModal'); return !!m && m.style.display === 'flex' && !!m.querySelector('.docs-unit.hit'); }", timeout=15000)
            hit = page.evaluate("() => { const h = document.querySelector('#documentsModal .docs-unit.hit'); return h ? [h.id, h.className, !!h.querySelector('.mark'), h.closest('details').open] : null; }")
            check("the click opens the Documents view at that unit: highlighted, marked as read, its group open",
                  hit is not None and hit[0] == "unit-" + chip[0] and "read" in hit[1].split() and hit[2] is True and hit[3] is True, hit)
            page.evaluate("documentsClose()")
            strip_doc = page.inner_text(".sp-strip")
            check("the strip counts the chain's exchanges as turns", re.search(r"turn \d+ of", strip_doc) is not None, strip_doc)
            kernel_copies = glob.glob(os.path.join(workdir, "**", "datasets", USER, "documents", "D1", "text.md"), recursive=True)
            check("the kernel's copy of the document is where the cell read it through D1", len(kernel_copies) >= 1, kernel_copies)
            for kc in kernel_copies:                        # the kernel forgets (a container restart): the next chain start brings it back
                shutil.rmtree(os.path.dirname(kc), ignore_errors=True)

            # the Reviewer seat (v64): an Adaptive run crossing turn 9 runs that turn on the Reviewer seat
            page.fill("#queryInput", mod.REVIEW_QUESTION)
            page.evaluate("setMode('adaptive')")
            page.click("#submitQuery")
            wait_text(page, "#chainPosition", "chain 4 of 4", 60000)
            # while chain 4 runs, browse chain 3 and use its tabs (v70: clicks act on the visible strip, not the parked one)
            wait_text(page, ".sp-turn", "Turn 1", 30000)
            page.click("#prevResponse")
            wait_text(page, "#chainPosition", "chain 3 of 4", 10000)
            page.wait_for_timeout(300)
            switched = []
            for t in ("code", "plan", "answer"):
                if page.query_selector(f"#tabContainer #tab-{t}"):
                    page.click(f"#tabContainer #tab-{t}")
                    page.wait_for_timeout(150)
                    switched.append(page.evaluate("() => { const a = document.querySelector('#contentOutput .tab-content.active'); return a ? a.id : null; }") == f"content-{t}")
            still_running = page.evaluate("typeof queryRunning !== 'undefined' && queryRunning")
            check("browsing a finished chain while another runs: its tabs respond (the visible pane switches on click)", switched and all(switched), (switched, still_running))
            page.click("#nextResponse")
            wait_text(page, "#chainPosition", "chain 4 of 4", 10000)
            wait_run_end(page, 4)
            kernel_again = glob.glob(os.path.join(workdir, "**", "datasets", USER, "documents", "D1", "text.md"), recursive=True)
            check("after the kernel forgot the document, the next chain's start synced it back", len(kernel_again) >= 1, kernel_again)
            chip_after = page.inner_text("#containerStatusText")
            check("after runs the chip still reads " + {"orchestrator": "Ready", "local": "Local", "direct": "Docker"}[compute] + " (the execution branch uses the same text rule)",
                  chip_after == {"orchestrator": "Ready", "local": "Local", "direct": "Docker"}[compute], chip_after)
            page.wait_for_timeout(1200)                       # the old code opened the map 500 ms after an Adaptive run ended
            map_open = page.evaluate("() => { const m = document.getElementById('workflowMapModal'); return !!m && getComputedStyle(m).display !== 'none'; }")
            check("the thread map stays closed when an Adaptive run ends (v65)", not map_open, map_open)
            cards = page.evaluate("() => [...document.querySelectorAll('.sp-turn')].map(t => ({ n: (t.querySelector('.n') || {}).textContent || '', meta: (t.querySelector('.meta') || {}).textContent || '', seat: (t.querySelector('.sp-prompt') || {}).dataset ? t.querySelector('.sp-prompt').dataset.agent : '' }))")
            rewrite_seat = page.evaluate("() => { const c = [...document.querySelectorAll('.sp-turn')].find(t => /Rewrite/.test((t.querySelector('.n') || {}).textContent || '')); const b = c && c.querySelector('.sp-prompt'); return b ? b.dataset.agent : null; }")
            check("rewrite seat: the Rewrite card ran on the Rewriter seat (v71)", rewrite_seat == "Rewriter", rewrite_seat)
            check("review: after turn 8 of the Adaptive run a Review card on the Reviewer seat with its model, between turns 8 and 9 on the Analyst - and its REPORT verdict made turn 9 the report",
                  len(cards) >= 10 and cards[8]["n"] == "Review" and "Reviewer" in cards[8]["meta"] and cards[8]["seat"] == "Reviewer"
                  and cards[7]["n"] == "Turn 8" and cards[7]["seat"] == "Analyst" and cards[9]["n"] == "Turn 9" and cards[9]["seat"] == "Analyst", cards[7:10])
            page.evaluate("setMode('deep')")
            page.click("#prevResponse")
            page.wait_for_timeout(500)
            check("chain navigation: back to chain 3 of 4", "chain 3 of 4" in page.inner_text("#chainPosition"))
            page.click("#prevResponse")
            page.wait_for_timeout(500)
            page.click("#prevResponse")
            page.wait_for_timeout(500)
            p2 = prompt_of(2)                                  # a restored chain: the rebound buttons work and carry the ordinal (v65)
            check("prompt button on a restored chain: turn 2's card opens turn 2's prompt", "TASK: turn 2;" in p2["user"], p2["user"][-120:])
            for _ in range(3):
                page.click("#nextResponse")
                page.wait_for_timeout(400)

            page.click("#rankButton")
            page.wait_for_selector("#rankModal", state="visible", timeout=10000)
            page.click("#rankModal .rating-segment[data-value='7']")
            page.click("#submit-rank")
            page.wait_for_timeout(3000)
            errs = page.evaluate("window.__stackErrors || []")
            # what landed on disk, in the app's own layout under the stack's web app working directory
            wa = os.path.join(workdir, "webapp")
            threads = glob.glob(os.path.join(wa, "storage", USER, "threads", "*.json"))
            check("one notebook thread file stored under storage/<user>/threads", len(threads) == 1, threads)
            nb = json.load(open(threads[0])) if threads else {"runs": {}}
            runs = list(nb["runs"].values())
            # the document chain's one cell (the grep) replays like any other
            check("the thread holds four runs, all answered; every chain with cells reproduced",
                  len(runs) == 4 and all(r["status"] == "answered" for r in runs)
                  and all((r["replay_status"] == "reproduced") == any(t_["kind"] == "cell" for t_ in r["turns"]) for r in runs),
                  [(r["status"], r["replay_status"], sum(1 for t_ in r["turns"] if t_["kind"] == "cell")) for r in runs])
            check("the second run's parent is the first", len(runs) >= 2 and runs[1]["parent"] == runs[0]["id"])
            favs = glob.glob(os.path.join(wa, "storage", USER, "favourites", "*", "*.json"))
            check("Save wrote the favourites (one file per chain of the thread)", len(favs) == 4, favs)
            pack = os.path.join(wa, "memory", USER, "memory_pack.yaml")
            check("Save at 7 ran the write pass: the memory pack holds the distilled candidate card",
                  os.path.exists(pack) and "within_soil_plot_level_contrast" in open(pack).read(), pack)

            # the thread's documents go with the thread (D35): the last thing, since deleting it tombstones the memory card
            tid = str(page.evaluate("() => currentData.thread_id"))
            docs_dir = os.path.join(wa, "storage", USER, "documents", tid)
            had_docs = os.path.isdir(docs_dir) and os.path.exists(os.path.join(docs_dir, "manifest.json"))
            status = page.evaluate("(t) => window.authService.fetch('/delete_thread/' + t, { method: 'DELETE' }).then(r => r.status)", tid)   # as the page does: its auth header rides along
            check("the thread's documents folder existed with its manifest, and deleting the thread removed it",
                  had_docs and status == 200 and not os.path.exists(docs_dir), (had_docs, status, os.path.exists(docs_dir)))
            b.close()

        calls = st.orchestrator_calls()
        kinds = [c["kind"] for c in calls]
        if compute == "orchestrator":
            check("the app never asked the orchestrator to destroy the container", "destroy" not in kinds, kinds)
            check("the app polled the container status and spawned/reused through the orchestrator",
                  kinds.count("status") >= 3 and kinds.count("spawn") >= 1, kinds)
        else:
            check(f"compute {compute}: no orchestrator was involved", not calls and "orchestrator" not in st.procs, list(st.procs))
            check(f"compute {compute}: the executor process " + ("was not started (the kernel ran here)" if compute == "local" else "was the one named in .env"),
                  ("executor" not in st.procs) if compute == "local" else ("executor" in st.procs), list(st.procs))
        page_errors = [l for l in logs if l.startswith(("[pageerror]", "[window.error]"))] + [f"[window.error] {e}" for e in errs]
        check("no page errors during the whole walk", not page_errors, page_errors[:3])
        http_errors = [l for l in logs if l.startswith("[http 5")]
        check("no 5xx answers from the app during the walk", not http_errors, http_errors[:3])
        print(f"  (the first run took {elapsed:.0f}s end to end; stack workdir {workdir})")

    print(f"{len(passed)} passed, {len(failed)} failed")
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
