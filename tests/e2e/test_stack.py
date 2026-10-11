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
    print(("  ok   " if cond else "  FAIL ") + name + ("" if cond else f"  <- {str(detail)[:900]}"))


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
            check("one card per model call (6 analyst turns, the figures step, the rewrite; no review outside Adaptive)", turns == 8, turns)
            # the figures step (2026-10-11): the figure cell of turn 5 was not run - a skipped row; after the report one quiet
            # 'Figures' card, then its cell row as cell 3 with the two figures; the Answer tab's Figures section cites them
            fig = page.evaluate("""() => { const rows = [...document.querySelectorAll('.sp-row')];
                const skipped = rows.filter(r => r.classList.contains('skipped')).map(r => r.textContent);
                const cards = [...document.querySelectorAll('.sp-turn')].map(t => [(t.querySelector('.n') || {}).textContent || '', (t.querySelector('summary .kind') || {}).textContent || '', (t.querySelector('summary .peek') || {}).textContent || '']);
                const figCard = cards.find(c => c[0] === 'Figures');
                const order = rows.map(r => r.classList.contains('skipped') ? 'skipped' : (r.classList.contains('fail') ? 'fail' : (r.classList.contains('tool') ? 'tool' : 'cell')));
                const last = rows.filter(r => !r.classList.contains('tool')).pop();
                return { skipped, figCard, order, last: last ? last.textContent : '', cellRows: rows.filter(r => /In.\\[\\d+\\]/.test(r.textContent)).map(r => r.textContent) }; }""")
            check("the figure cell of turn 5 is a skipped row - In [–], 'not run', figures come after the report - and the analysis went on to its report",
                  len(fig["skipped"]) == 1 and "not run" in fig["skipped"][0] and "figures are drawn after the report" in fig["skipped"][0], fig["skipped"])
            check("the Figures card: quiet, kind 'figures', its line naming the two figures the cell draws; then the cell row In [3] with 2 fig",
                  fig["figCard"] and fig["figCard"][1] == "figures" and fig["figCard"][2].startswith("figure cell: plot-level yield by regime")
                  and "In\xa0[3]" in fig["last"].replace("In [", "In\xa0[") and "2 fig" in fig["last"], (fig["figCard"], fig["last"]))
            check("the rows in order: cell 1, the search, the failed cell, cell 2, the skipped figure cell, then the figures cell after the report",
                  fig["order"][:5] == ["cell", "tool", "fail", "cell", "skipped"] and fig["order"].count("cell") == 3 and len(fig["cellRows"]) == 3, fig["order"])
            fig_seat = page.evaluate("() => { const c = [...document.querySelectorAll('.sp-turn')].find(t => ((t.querySelector('.n') || {}).textContent || '') === 'Figures'); const b = c && c.querySelector('.sp-prompt'); return b ? b.dataset.agent : null; }")
            check("the Figures card ran on the Figures seat the template carries (2026-10-11)", fig_seat == "Figures", fig_seat)
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
            fig_chips = page.evaluate("() => [...document.querySelectorAll('#content-answer .cite.fig')].map(e => e.textContent)")
            check("the Answer tab ends with the Figures section - two captions, each citing the figures cell as a fig 3 chip",
                  "Figures" in answer and "plot-level yield by regime within each soil type" in answer and "mean plot yield by regime" in answer and fig_chips == ["fig 3", "fig 3"]
                  and answer.find("Figures") > answer.find("Next steps"), (fig_chips, answer[-300:]))
            # the plain-language version keeps the figure citation, as a chip (2026-10-11)
            page.wait_for_selector("#content-answer .simplified-summary-btn:not(.loading)", timeout=15000)
            page.click("#content-answer .simplified-summary-btn")
            page.wait_for_timeout(300)
            simp = page.evaluate("() => ({ text: document.querySelector('#content-answer .content-body').textContent, chips: [...document.querySelectorAll('#content-answer .content-body .cite.fig')].map(e => e.textContent) })")
            check("Simplified: the plain-language version cites the figure at the end of the sentence that says what it shows, and the citation is a fig 3 chip",
                  "What was found" in simp["text"] and simp["chips"] == ["fig 3"] and "[fig 3]" not in simp["text"], simp)
            page.click("#content-answer .simplified-summary-btn")
            page.wait_for_timeout(300)
            check("Simplified toggled back: the technical report with its chips", page.evaluate("() => document.querySelectorAll('#content-answer .content-body .cite.fig').length") == 2)
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

            # Save (2026-10-10, routines): the pill opens its menu; Save as favourite is the rank dialog as before
            page.click("#rankButton")
            page.wait_for_selector("#saveMenu", state="visible", timeout=10000)
            menu_items = page.evaluate("() => [...document.querySelectorAll('#saveMenu .it b')].map(e => e.textContent)")
            check("the Save pill opens its menu: Save as favourite and Save as routine", menu_items == ["Save as favourite", "Save as routine"], menu_items)
            page.click("#saveMenu .it[data-act='favourite']")
            page.wait_for_selector("#rankModal", state="visible", timeout=10000)
            page.click("#rankModal .rating-segment[data-value='7']")
            page.click("#submit-rank")
            page.wait_for_timeout(3000)
            pill_after = page.evaluate("() => { const p = document.getElementById('rankButton'); return [getComputedStyle(p).display, p.className]; }")
            check("after the save the pill stays, marked saved (its menu still offers Save as routine)", pill_after[0] != "none" and "saved" in pill_after[1].split(), pill_after)

            # Save as routine on chain 1 (docs/ROUTINES_DESIGN.md F1): the promoter (scripted) names the regime as the one
            # input, run zero runs through the real executor and reproduces the chain's RESULT line, the routine is stored
            # with the favourite as its origin, and the manager and the favourites' card show it
            for _ in range(3):
                page.click("#prevResponse")
                page.wait_for_timeout(400)
            wait_text(page, "#chainPosition", "chain 1 of 4", 10000)
            page.hover("#rankButton")
            page.wait_for_selector("#saveMenu", state="visible", timeout=10000)
            page.click("#saveMenu .it[data-act='routine']")
            page.wait_for_selector("#routineMakeModal", state="visible", timeout=10000)
            page.wait_for_selector("#routineMakeModal .rt-inputs", timeout=120000)
            dlg = page.evaluate("""() => ({ sub: document.querySelector('#routineMakeModal .ui-dlg-h .sub').textContent, name: document.querySelector('#routineMakeModal [data-field="name"]').value,
                inputs: [...document.querySelectorAll('#routineMakeModal .rt-inputs tbody tr')].map(r => [r.dataset.key, r.querySelector('.val').textContent]),
                results: [...document.querySelectorAll('#routineMakeModal .rt-results .r .l')].map(e => e.textContent), data: document.querySelector('#routineMakeModal .rt-data').textContent,
                state: [...document.querySelectorAll('#routineMakeModal .rt-line')].map(e => e.textContent).join(' | '), card: !![...document.querySelectorAll('.sp-turn .n')].find(e => e.textContent === 'Routine'),
                seat: (() => { const c = [...document.querySelectorAll('.sp-turn')].find(t => (t.querySelector('.n') || {}).textContent === 'Routine'); return c ? ((c.querySelector('.sp-prompt') || {}).dataset || {}).agent || '' : ''; })() })""")
            check("Save as routine: the dialog shows the promoter's proposal - the name, the regime as the one input (B), the chain's RESULT line, the data, and that the check runs on this chain's own data; the pane shows the promoter's card on the Promoter seat",
                  dlg["name"] == "Regime contrast within soil, plot means" and dlg["inputs"] == [["regime", "B"]] and len(dlg["results"]) == 1 and "regime B vs A" in dlg["results"][0]
                  and "field_trial.csv" in dlg["data"] and "Checked once" in dlg["state"] and dlg["card"] and "Promoter" in dlg["seat"], dlg)
            page.fill("#routineMakeModal [data-field='purpose']", "the within-soil regime contrast, for the next season")
            page.click("#routineMakeModal [data-act='create']")
            page.wait_for_function("() => document.querySelector('#routineMakeModal').style.display === 'none' || !!document.querySelector('#routineMakeModal .rt-error')", timeout=180000)
            err_box = page.evaluate("() => { const e = document.querySelector('#routineMakeModal .rt-error'); return e ? e.textContent : null; }")
            check("Create routine: run zero reproduced the chain's line through the executor and the dialog closed (no refusal)", err_box is None, err_box)
            page.wait_for_timeout(1500)
            pane_rows = page.evaluate("() => [...document.querySelectorAll('.sp-row.tool')].map(e => e.textContent)")
            check("the pane carries the ROUTINE row with run zero's verdict", any("ROUTINE" in r and "reproduced: 1 result line(s) identical" in r for r in pane_rows), pane_rows[-2:])
            rdirs = glob.glob(os.path.join(workdir, "webapp", "storage", USER, "routines", "*", "routine.json"))
            rj = json.load(open(rdirs[0])) if rdirs else {}
            check("the routine is stored under storage/<user>/routines with v1 verified by run zero, the regime input, and the chain as its origin",
                  len(rdirs) == 1 and rj.get("current_version") == 1 and rj["versions"][0]["run_zero"]["verified"] and rj["versions"][0]["run_zero"]["status"] == "reproduced"
                  and [p["key"] for p in rj["versions"][0]["manifest"]["parameters"]] == ["regime"] and "INPUTS['regime']" in rj["versions"][0]["script"]
                  and rj["origin"]["thread_id"] == str(page.evaluate("() => currentData.thread_id")) and rj.get("purpose", "").startswith("the within-soil"), (len(rdirs), rj.get("versions", [{}])[0].get("run_zero")))
            fav1 = os.path.join(workdir, "webapp", "storage", USER, "favourites", rj["origin"]["thread_id"], rj["origin"]["chain_id"] + ".json") if rdirs else ""
            check("Save as routine saved the chain as a favourite too (individually)", fav1 and os.path.exists(fav1) and json.load(open(fav1)).get("bookmark_type") == "individual", fav1)
            page.hover("#rankButton")
            page.wait_for_selector("#saveMenu", state="visible", timeout=10000)
            page.wait_for_function("() => (document.querySelector('#saveMenu .it[data-act=\"routine\"] span') || {}).textContent.includes('made from this chain')", timeout=10000)
            menu2 = page.evaluate("() => [...document.querySelectorAll('#saveMenu .it')].map(e => [e.className, e.querySelector('span').textContent])")
            check("the menu now says the chain is a favourite and names the routine made from it", "done" in menu2[0][0] and "Regime contrast" in menu2[1][1], menu2)
            page.mouse.move(10, 400)
            page.click("#routinesPill")
            page.wait_for_selector("#routinesModal", state="visible", timeout=10000)
            page.wait_for_selector("#routinesModal .rt-side .it", timeout=15000)
            page.wait_for_function("() => (document.querySelector('#routinesModal .rt-right .title') || {}).textContent", timeout=15000)
            mgr = page.evaluate("""() => ({ items: [...document.querySelectorAll('#routinesModal .rt-side .it b')].map(e => e.textContent), title: document.querySelector('#routinesModal .rt-right .title').textContent,
                sub: document.querySelector('#routinesModal .rt-right .sub').textContent, origin: !!document.querySelector('#routinesModal .rt-origin'), checked: (document.querySelector('#routinesModal .rt-status') || {}).textContent,
                inputs: document.querySelectorAll('#routinesModal .rt-inputs tbody tr').length, badge: document.getElementById('routinesBadge').textContent })""")
            check("the Routines manager lists the routine, verified, with its one input and the link to the analysis it was made from; the rail badge counts 1",
                  mgr["items"] == ["Regime contrast within soil, plot means"] and mgr["origin"] and mgr["checked"] == "verified" and mgr["inputs"] == 1 and "a favourite" in mgr["sub"] and mgr["badge"] == "1", mgr)
            script_status = page.evaluate("(id) => window.authService.fetch('/routines/' + id + '/script').then(r => r.text()).then(t => t.includes('INPUTS = {') && t.includes(\"'regime': 'B'\"))", rj["id"])
            check("the .py download carries the INPUTS block with the default", script_status is True, script_status)
            page.click("#routinesModal .rt-origin")
            page.wait_for_function("() => document.getElementById('routinesModal').style.display === 'none' && /chain 1 of 4/.test(document.getElementById('chainPosition').textContent)", timeout=15000)
            check("open the analysis: the routine's origin loads from favourites into the main panes", True)
            page.click("#workflowManagerPill")
            page.wait_for_selector("#workflowManagerModal .workflow-card-routine", timeout=15000)
            card_btn = page.evaluate("() => [...document.querySelectorAll('#workflowManagerModal .workflow-card-routine')].map(b => [b.className, (b.querySelector('.n') || {}).textContent || ''])")
            check("the favourites' card carries the Routine button, lit with 1", any("has" in c.split() and n == "1" for c, n in card_btn), card_btn)
            page.evaluate("WorkflowModal.close()")
            page.wait_for_timeout(300)

            # Run on current data (docs/ROUTINES_DESIGN.md F2, step 2): the run dialog checks the data loaded now against
            # the routine; run 1 on the same data with the same input reproduces run 0; the run view locks the composer
            # and opens on the comparison; run 2 with another input is compared with run 1; the arrows step through the
            # runs (run 0 included); a file missing a column is refused in the dialog before anything runs
            page.click("#routinesPill")
            page.wait_for_selector("#routinesModal", state="visible", timeout=10000)
            page.wait_for_function("() => (document.querySelector('#routinesModal .rt-right .title') || {}).textContent", timeout=15000)
            runs_before = page.evaluate("() => [...document.querySelectorAll('#routinesModal .rt-runlist .rt-run')].map(e => e.dataset.run)")
            check("the manager before any run: the runs list holds run 0 only", runs_before == ["0"], runs_before)
            page.click("#routinesModal [data-act='run']")
            page.wait_for_selector("#routineRunModal", state="visible", timeout=10000)
            page.wait_for_selector("#routineRunModal .rt-fit", timeout=30000)
            rd = page.evaluate("""() => ({ title: document.querySelector('#routineRunModal .ui-dlg-h .title').textContent, fit: document.querySelector('#routineRunModal .rt-fit').textContent, bad: document.querySelector('#routineRunModal .rt-fit').classList.contains('bad'),
                data: document.querySelector('#routineRunModal .rt-data').textContent, regime: (document.querySelector('#routineRunModal [data-key="regime"]') || {}).value,
                compare: [...document.querySelectorAll('#routineRunModal input[name="rt-compare"]')].map(i => [i.value, i.checked]), runOn: !document.querySelector('#routineRunModal [data-act="run"]').disabled })""")
            check("the run dialog: the data loaded now (field_trial.csv) fits the routine, the regime input carries its default B, the comparison offers run 0 (the only run so far), Run is enabled",
                  "Regime contrast" in rd["title"] and "fits the routine" in rd["fit"] and not rd["bad"] and "field_trial.csv" in rd["data"] and rd["regime"] == "B" and rd["compare"] == [["zero", True]] and rd["runOn"], rd)
            page.click("#routineRunModal [data-act='run']")
            page.wait_for_function("() => document.getElementById('routineRunModal').style.display === 'none' && /run 1/.test(document.getElementById('chainPosition').textContent)", timeout=30000)
            live = page.evaluate("() => ({ pos: document.getElementById('chainPosition').textContent, locked: document.getElementById('queryInput').disabled, pill: getComputedStyle(document.getElementById('rankButton')).display, arrows: [document.getElementById('prevResponse').disabled, document.getElementById('nextResponse').disabled] })")
            check("while run 1 runs: the position says so, both arrows are off, the composer is locked and the Save pill is hidden",
                  "running" in live["pos"] and live["locked"] and live["pill"] == "none" and live["arrows"] == [True, True], live)
            wait_text(page, "#chainPosition", "run 1 of 1", 180000)
            page.wait_for_timeout(600)
            rv = page.evaluate("""() => ({ rows: [...document.querySelectorAll('.sp-row.tool')].map(e => e.textContent), done: (document.querySelector('.sp-done') || {}).textContent || '', warn: !!document.querySelector('.sp-done.warn'),
                tabs: [...document.querySelectorAll('#tabContainer .tab')].map(e => e.id), active: (document.querySelector('#contentOutput .tab-content.active') || {}).id, strip: (document.querySelector('.sp-strip') || {}).textContent || '',
                ids: (document.querySelector('.sp-ids') || {}).textContent || '', locked: document.getElementById('queryInput').disabled && document.getElementById('submitQuery').disabled && document.body.classList.contains('composer-locked'),
                placeholder: document.getElementById('queryInput').placeholder, pill: getComputedStyle(document.getElementById('rankButton')).display, arrows: [document.getElementById('prevResponse').disabled, document.getElementById('nextResponse').disabled],
                cmp: (document.getElementById('content-comparison') || {}).textContent || '', turns: document.querySelectorAll('.sp-turn').length, chip: document.querySelector('#containerStatusText').textContent })""")
            check("after run 1 the executor chip is back to " + {"orchestrator": "Ready", "local": "Local", "direct": "Docker"}[compute] + " (2026-10-10: it stayed on Executing)",
                  rv["chip"] == {"orchestrator": "Ready", "local": "Local", "direct": "Docker"}[compute], rv["chip"])
            check("run 1 in the pane: the CHECK, RUN and COMPARE rows, no model card, and the closing card says run 1 reproduced run 0's line",
                  any("CHECK" in r and "field_trial.csv" in r for r in rv["rows"]) and any("RUN" in r and "run 1" in r for r in rv["rows"]) and any("COMPARE" in r and "run 0" in r for r in rv["rows"])
                  and rv["turns"] == 0 and "Run 1 complete" in rv["done"] and "reproduced: every result line as the run before (1 line)" in rv["done"] and "against run 0" in rv["done"] and not rv["warn"], (rv["rows"], rv["done"][:200]))
            check("run 1 in the panes: the strip reads run 1 · v1 against run 0, the id line names the routine and the run, the Comparison tab is first and open with the line within its interval",
                  "run 1" in rv["strip"] and "v1" in rv["strip"] and "run 0" in rv["strip"] and "Routine:" in rv["ids"] and "Run:1·v1" in rv["ids"].replace(" ", "")
                  and rv["tabs"] and rv["tabs"][0] == "tab-comparison" and rv["active"] == "content-comparison" and "against run 0" in rv["cmp"] and "within" in rv["cmp"] and "regime B vs A" in rv["cmp"], (rv["strip"], rv["ids"], rv["tabs"], rv["active"], rv["cmp"][:200]))
            check("run 1 in the panes: the Plots and Results tabs came through the stream as an analysis's do", "tab-plot" in rv["tabs"] and "tab-code_exec_results" in rv["tabs"], rv["tabs"])
            check("after run 1: the composer stays locked with the reason as its placeholder, the Save pill stays hidden, the position reads run 1 of 1 with the next arrow off and the previous one on (run 0)",
                  rv["locked"] and "open the analysis" in rv["placeholder"] and rv["pill"] == "none" and rv["arrows"] == [False, True], (rv["locked"], rv["placeholder"], rv["pill"], rv["arrows"]))
            # the run before (run 0) through the arrow, then forward again
            page.click("#prevResponse")
            wait_text(page, "#chainPosition", "run 0 of 1", 30000)
            page.wait_for_timeout(400)
            r0 = page.evaluate("() => ({ cmp: (document.getElementById('content-comparison') || {}).textContent || '', done: (document.querySelector('.sp-done') || {}).textContent || '', arrows: [document.getElementById('prevResponse').disabled, document.getElementById('nextResponse').disabled], tabs: [...document.querySelectorAll('#tabContainer .tab')].map(e => e.id) })")
            check("the previous arrow opens run 0 (the version's own check): its own line with the estimate and the interval, nothing it is against, the Results and Data tabs of the stored run, the previous arrow off",
                  r0["cmp"].startswith("Run 0 — the original data") and "against" not in r0["cmp"] and "regime B vs A" in r0["cmp"] and re.search(r"\[[+-]?\d", r0["cmp"]) is not None
                  and "Run 0 complete" in r0["done"] and r0["arrows"] == [True, False] and "tab-code_exec_results" in r0["tabs"] and "tab-dataframe" in r0["tabs"], r0)
            page.click("#nextResponse")
            wait_text(page, "#chainPosition", "run 1 of 1", 30000)
            # the favourite unlocks the composer (Saved workflows -> the card)
            page.click("#workflowManagerPill")
            page.wait_for_selector("#workflowManagerModal .workflow-card", timeout=15000)
            page.click("#workflowManagerModal .workflow-card")
            page.wait_for_function("() => /chain \\d of 4/.test(document.getElementById('chainPosition').textContent) && !document.getElementById('queryInput').disabled", timeout=15000)
            page.wait_for_timeout(300)
            unlocked = page.evaluate("() => ({ locked: document.body.classList.contains('composer-locked'), placeholder: document.getElementById('queryInput').placeholder, pos: document.getElementById('chainPosition').textContent, pill: getComputedStyle(document.getElementById('rankButton')).display })")
            check("loading a favourite leaves the run view: the composer is back with its own placeholder, the chains' navigation and the Save pill return",
                  not unlocked["locked"] and "open the analysis" not in unlocked["placeholder"] and "chain" in unlocked["pos"] and unlocked["pill"] != "none", unlocked)
            # run 2 with the other regime, compared with run 1 (the run before, the dialog's default now)
            page.click("#routinesPill")
            page.wait_for_selector("#routinesModal", state="visible", timeout=10000)
            page.wait_for_function("() => (document.querySelector('#routinesModal .rt-right .title') || {}).textContent", timeout=15000)
            page.click("#routinesModal [data-act='run']")
            page.wait_for_selector("#routineRunModal .rt-fit", timeout=30000)
            cmp_choices = page.evaluate("() => [...document.querySelectorAll('#routineRunModal input[name=\"rt-compare\"]')].map(i => [i.value, i.checked])")
            check("the run dialog after run 1 offers the run before (on) and run 0", cmp_choices == [["previous", True], ["zero", False]], cmp_choices)
            page.fill("#routineRunModal [data-key='regime']", "C")
            page.click("#routineRunModal [data-act='run']")
            wait_text(page, "#chainPosition", "run 2 of 2", 180000)
            page.wait_for_timeout(600)
            r2 = page.evaluate("""() => ({ done: (document.querySelector('.sp-done') || {}).textContent || '', warn: !!document.querySelector('.sp-done.warn'), cmp: (document.getElementById('content-comparison') || {}).textContent || '',
                marks: [...document.querySelectorAll('#content-comparison .rt-mark')].map(e => e.textContent.trim()), strip: (document.querySelector('.sp-strip') || {}).textContent || '', arrows: [document.getElementById('prevResponse').disabled, document.getElementById('nextResponse').disabled],
                results: (document.getElementById('content-code_exec_results') || {}).textContent || '' })""")
            check("run 2 (regime C): ran with its one result line, compared with run 1 - the closing card and the comparison tab say which run it is against and how many lines moved or stayed within their intervals",
                  "Run 2 complete" in r2["done"] and "ran: 1 result line" in r2["done"] and "against run 1" in r2["done"] and "of 1" in r2["done"] and not r2["warn"]
                  and "against run 1" in r2["cmp"] and "run 1" in r2["strip"] and r2["arrows"] == [False, True] and len(r2["marks"]) == 1 and r2["marks"][0] in ("↑", "↓", "="), (r2["done"][:200], r2["cmp"][:200], r2["marks"], r2["strip"]))
            check("run 2's Results tab holds the printed output of the run with regime C", "regime C vs A" in r2["results"] or "C vs A" in r2["results"], r2["results"][:200])
            page.click("#routinesPill")
            page.wait_for_selector("#routinesModal", state="visible", timeout=10000)
            page.wait_for_function("() => document.querySelectorAll('#routinesModal .rt-runlist .rt-run').length >= 3", timeout=15000)
            mg2 = page.evaluate("""() => ({ items: [...document.querySelectorAll('#routinesModal .rt-runlist .rt-run')].map(e => [e.dataset.run, (e.querySelector('.rt-status') || {}).textContent || '', e.textContent]),
                cols: [...document.querySelectorAll('#routinesModal .rt-runs thead th')].map(e => e.textContent.trim()), rows: document.querySelectorAll('#routinesModal .rt-runs tbody tr').length, sub: document.querySelector('#routinesModal .rt-right .sub').textContent })""")
            check("the manager after two runs: the runs table has a column per run (0, 1, 2) and a row for the routine's line; the runs list reads run 2 (ran, regime C), run 1 (reproduced), run 0",
                  [x[0] for x in mg2["items"]] == ["2", "1", "0"] and mg2["items"][0][1].startswith("ran") and "regime = C" in mg2["items"][0][2] and mg2["items"][1][1] == "reproduced" and mg2["rows"] == 1
                  and sum(1 for c in mg2["cols"] if re.match(r"Run [012]", c)) == 3 and "Trend" in mg2["cols"], mg2)
            page.click("#routinesModal .rt-runlist .rt-run[data-run='1']")
            wait_text(page, "#chainPosition", "run 1 of 2", 30000)
            page.wait_for_timeout(400)
            opened = page.evaluate("() => ({ cmp: (document.getElementById('content-comparison') || {}).textContent || '', pos: document.getElementById('chainPosition').textContent, arrows: [document.getElementById('prevResponse').disabled, document.getElementById('nextResponse').disabled], locked: document.getElementById('queryInput').disabled })")
            check("the runs list opens run 1 in the main panes: its comparison against run 0, both arrows on, the composer locked again",
                  "against run 0" in opened["cmp"] and opened["arrows"] == [False, False] and opened["locked"], opened)
            page.click("#nextResponse")
            wait_text(page, "#chainPosition", "run 2 of 2", 30000)
            # the dialog loads the data itself (2026-10-10): a file routine offers an upload beside the data loaded now; the same file
            # again, compared with run 0, reproduces, and the pane opens with a LOAD row
            page.click("#routinesPill")
            page.wait_for_selector("#routinesModal", state="visible", timeout=10000)
            page.wait_for_function("() => (document.querySelector('#routinesModal .rt-right .title') || {}).textContent", timeout=15000)
            page.click("#routinesModal [data-act='run']")
            page.wait_for_selector("#routineRunModal .rt-fit", timeout=30000)
            choices = page.evaluate("() => [...document.querySelectorAll('#routineRunModal input[name=\"rt-data\"]')].map(i => [i.value, i.checked])")
            check("the run dialog of a file routine offers an upload beside the data loaded now (on)", choices == [["upload", False], ["now", True]], choices)
            page.set_input_files("#routineRunModal input[data-load='file']", st.dataset)
            page.wait_for_timeout(200)
            up_state = page.evaluate("() => ({ upload: document.querySelector('#routineRunModal input[name=\"rt-data\"][value=\"upload\"]').checked, runOn: !document.querySelector('#routineRunModal [data-act=\"run\"]').disabled })")
            check("choosing a file switches the choice to the upload and keeps Run on", up_state["upload"] and up_state["runOn"], up_state)
            page.click("#routineRunModal input[name='rt-compare'][value='zero']")
            page.click("#routineRunModal [data-act='run']")
            wait_text(page, "#chainPosition", "run 3 of 3", 240000)
            page.wait_for_timeout(600)
            r3 = page.evaluate("""() => ({ rows: [...document.querySelectorAll('.sp-row.tool')].map(e => e.textContent), done: (document.querySelector('.sp-done') || {}).textContent || '',
                pills: [...document.querySelectorAll('.primary-dataset-pill')].map(p => p.textContent), data: (document.getElementById('content-dataframe') || {}).textContent || '' })""")
            check("run 3 through the dialog's upload: a LOAD row names the file, the CHECK and RUN rows follow, and the same file with the default input reproduces run 0",
                  any("LOAD" in r and "field_trial.csv" in r for r in r3["rows"]) and "Run 3 complete" in r3["done"] and "reproduced" in r3["done"] and "against run 0" in r3["done"] and any("field_trial.csv) loaded" in p_ for p_ in r3["pills"]) and len(r3["pills"]) == 1, (r3["rows"], r3["done"][:160], r3["pills"]))
            # a file without the soil column: the dialog says the column will be empty (the coach decides), the run goes ahead, and the
            # method fails where it divides by a count that is zero without soil - kept as a run, named at its cell (2026-10-10: the first
            # live run on a new window stopped exactly so, and the terminal was the only place it showed)
            import csv
            no_soil = os.path.join(workdir, "data", "no_soil.csv")
            with open(st.dataset, newline="", encoding="utf-8") as src, open(no_soil, "w", newline="", encoding="utf-8") as dst:
                rd_ = csv.DictReader(src)
                cols = [c for c in rd_.fieldnames if c != "soil"]
                w = csv.DictWriter(dst, fieldnames=cols, extrasaction="ignore")
                w.writeheader()
                for row_ in rd_:
                    w.writerow(row_)
            page.set_input_files("#primaryFile", no_soil)
            page.wait_for_function("() => [...document.querySelectorAll('.primary-dataset-pill')].some(p => /no_soil\\.csv\\) loaded/.test(p.textContent))", timeout=60000)
            page.click("#routinesPill")
            page.wait_for_selector("#routinesModal", state="visible", timeout=10000)
            page.wait_for_function("() => (document.querySelector('#routinesModal .rt-right .title') || {}).textContent", timeout=15000)
            page.click("#routinesModal [data-act='run']")
            page.wait_for_selector("#routineRunModal .rt-fit", timeout=30000)
            nofit = page.evaluate("() => ({ fit: document.querySelector('#routineRunModal .rt-fit').textContent, bad: document.querySelector('#routineRunModal .rt-fit').classList.contains('bad'), data: document.querySelector('#routineRunModal .rt-data').textContent, runOn: !document.querySelector('#routineRunModal [data-act=\"run\"]').disabled })")
            check("with no_soil.csv loaded the run dialog says soil will be empty in this data - not a refusal: the run adds the column empty and the coach decides; Run stays on",
                  not nofit["bad"] and "1 of 6 columns empty in this data: soil" in nofit["fit"] and "no_soil.csv" in nofit["data"] and nofit["runOn"], nofit)
            page.click("#routineRunModal [data-act='run']")
            wait_text(page, "#chainPosition", "run 4 of 4", 240000)
            page.wait_for_timeout(600)
            r4 = page.evaluate("""() => ({ rows: [...document.querySelectorAll('.sp-row.tool')].map(e => e.textContent), done: (document.querySelector('.sp-done') || {}).textContent || '', warn: !!document.querySelector('.sp-done.warn'),
                cmp: (document.getElementById('content-comparison') || {}).textContent || '', pos: document.getElementById('chainPosition').textContent })""")
            check("run 4 on the file without soil: the CHECK row says the column is empty, the method fails at its cell dividing by a count that is zero (kept as a run, the card in the warning tone, the error on the Comparison tab)",
                  any("CHECK" in r and "empty in this data: soil" in r for r in r4["rows"]) and "Run 4 failed" in r4["done"] and "failed at cell" in r4["done"] and "ZeroDivisionError" in r4["done"] and r4["warn"]
                  and "ZeroDivisionError" in r4["cmp"] and "run 4 of 4" in r4["pos"], (r4["rows"][-3:], r4["done"][:200]))
            # what differs, said in sentences (step 4, 2026-10-11): the CHECK row says the rows against the original's; the Data tab lists it
            check("the CHECK rows say the rows against the original's: run 3's file the same rows as the original, run 4's too, the column empty said beside it",
                  any("CHECK" in r and "rows as the original" in r for r in r3["rows"]) and any("CHECK" in r and "rows as the original" in r and "empty in this data: soil" in r for r in r4["rows"]), (r3["rows"], r4["rows"]))
            # the stored run, opened with the arrow: its CHECK row says what the live one said, and its Data tab lists what differed
            page.click("#prevResponse")
            wait_text(page, "#chainPosition", "run 3 of 4", 30000)
            page.wait_for_timeout(400)
            r3s = page.evaluate("() => { activateTab('dataframe'); return { rows: [...document.querySelectorAll('.sp-row.tool')].map(e => e.textContent), data: (document.getElementById('content-dataframe') || {}).textContent || '' }; }")
            check("run 3 opened from its record: the CHECK row carries the recorded line (the rows as the original), and the Data tab lists it under Differs",
                  "rows as the original" in [r for r in r3s["rows"] if "CHECK" in r][-1] and "Differs" in r3s["data"] and "rows as the original" in r3s["data"], (r3s["rows"][-4:], r3s["data"][:200]))
            page.click("#nextResponse")
            wait_text(page, "#chainPosition", "run 4 of 4", 30000)
            page.wait_for_timeout(300)
            page.evaluate("RoutinesUI.closeManager()")
            run_files = sorted(os.path.basename(p) for p in glob.glob(os.path.join(os.path.dirname(rdirs[0]), "runs", "*"))) if rdirs else []
            rj2 = json.load(open(rdirs[0])) if rdirs else {}
            run1 = json.load(open(os.path.join(os.path.dirname(rdirs[0]), "runs", "v1_1", "run.json"))) if "v1_1" in run_files else {}
            run4 = json.load(open(os.path.join(os.path.dirname(rdirs[0]), "runs", "v1_4", "run.json"))) if "v1_4" in run_files else {}
            check("on disk: runs/v1_0 (run zero) to v1_4 with run.json and stdout.txt; routine.json lists the four runs with their status, data and comparison; the failed run keeps its traceback, the fit it ran under and its own folder on the executor's side",
                  run_files == ["v1_0", "v1_1", "v1_2", "v1_3", "v1_4"] and os.path.exists(os.path.join(os.path.dirname(rdirs[0]), "runs", "v1_1", "stdout.txt"))
                  and [x["number"] for x in rj2.get("runs", [])] == [1, 2, 3, 4] and [x["status"] for x in rj2["runs"]] == ["reproduced", "ran", "reproduced", "failed"] and rj2["runs"][1]["inputs"] == {"regime": "C"}
                  and run1.get("against") == 0 and run1.get("comparison", {}).get("compared") == 1 and run1.get("data", {}).get("name") == "field_trial.csv" and len(run1.get("results", [])) == 1
                  and "ZeroDivisionError" in run4.get("error", "") and run4.get("fit", {}).get("missing") == ["soil"] and run4.get("run_dir", "").endswith("/v1_4") and run4.get("data", {}).get("load", {}).get("source") == "file",
                  (run_files, [(x.get("number"), x.get("status"), x.get("inputs")) for x in rj2.get("runs", [])], run4.get("fit"), run4.get("run_dir")))
            # back to the thread for the rest of the walk
            page.click("#workflowManagerPill")
            page.wait_for_selector("#workflowManagerModal .workflow-card", timeout=15000)
            page.click("#workflowManagerModal .workflow-card")
            page.wait_for_function("() => /chain \\d of 4/.test(document.getElementById('chainPosition').textContent) && !document.getElementById('queryInput').disabled", timeout=15000)
            page.wait_for_timeout(300)
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
