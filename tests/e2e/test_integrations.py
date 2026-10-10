"""End to end, the integrations: the real web app and executor loading from the stack's fake Intervals.icu and Endura
(tools/stack/fake_apis.py, with FIT files the executor's own parser reads), the scripted analyst writing a method on
one window, Save as routine, and a run that loads the next window itself - where the summary file has another name,
the frame has no power column and the wellness file was not written (docs/ROUTINES_DESIGN.md F2 as rebuilt
2026-10-10). Then Endura: a routine made on one race, run on another with the race picked in the dialog.

    python3 tests/e2e/test_integrations.py        # ~3 minutes; the hosted edition (the loaders need the executor)

Skips (exit 0) when playwright is not installed.
"""
import glob
import json
import os
import re
import sys
import tempfile
import time
from datetime import date, timedelta

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path[:0] = [os.path.join(ROOT, "tools", "stack"), os.path.join(ROOT, "tools", "stack", "browser")]

try:
    from playwright.sync_api import sync_playwright
except Exception:                                          # noqa: BLE001
    print("playwright not installed: the integrations suite is skipped")
    sys.exit(0)

import vendor                                              # noqa: E402
import harness_models                                      # noqa: E402
import apis_data                                           # noqa: E402
from stack import Stack                                    # noqa: E402
from browse import open_page                               # noqa: E402

passed, failed = [], []
USER = "localuser"


def check(name, cond, detail=""):
    (passed if cond else failed).append(name)
    print(("  ok   " if cond else "  FAIL ") + name + ("" if cond else f"  <- {str(detail)[:900]}"))


def wait_text(page, selector, text, timeout=180000):
    page.wait_for_function("([sel, t]) => [...document.querySelectorAll(sel)].some(e => e.textContent.includes(t))", arg=[selector, text], timeout=timeout)


def wait_run_end(page, n, timeout=240000):
    wait_text(page, ".sp-done", "Run complete", timeout)
    page.wait_for_function("(n) => typeof queryRunning !== 'undefined' && !queryRunning && typeof responses !== 'undefined' && responses.length >= n", arg=n, timeout=timeout)
    page.wait_for_timeout(300)


def fetch_json(page, url, body=None, method=None):
    return page.evaluate("([u, b, m]) => window.authService.fetch(u, b == null ? undefined : { method: m || 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(b) }).then(r => r.json().then(j => ({ status: r.status, json: j })).catch(() => ({ status: r.status, json: null })))",
                         [url, body, method])


def main():
    os.environ["STACK_COMPUTE_TIER"] = "pro"             # a year's window for the Intervals loader (free: 14 days)
    vendor.prepare(fetch=bool(os.environ.get("CI")))
    workdir = tempfile.mkdtemp(prefix="bamboo_e2e_apis_")
    mod = harness_models.load("start_hours")
    today = date.today()
    a_start, a_end = today - timedelta(days=100), today - timedelta(days=41)       # the original window: rides, temperature, wellness
    print(f"windows: original {a_start} -> {a_end}; the run's default ends {today}")
    with Stack(workdir=workdir, scenario="start_hours", fresh=True, auto_ports=True, edition="hosted", compute="orchestrator") as st:
        with sync_playwright() as pw:
            b, page, logs = open_page(pw, st.app_url)
            page.goto(st.app_url)
            page.wait_for_selector("#queryInput", state="visible", timeout=60000)
            page.app_ready()
            page.wait_for_function("() => /Ready/.test(document.querySelector('#containerStatusText').textContent)", timeout=60000)
            # the key, as the settings dialog stores it; then the Data tab's Intervals dialog loads the original window
            r = fetch_json(page, "/intervals/store_api_key", {"api_key": "stack-key"})
            check("the Intervals.icu key is stored through its route (the stack's store)", r["status"] == 200, r)
            page.evaluate("showIntervalsModal()")
            page.wait_for_selector("#intervalsModal", state="visible", timeout=10000)
            page.evaluate("([s, e]) => { const a = document.getElementById('intervalsStartDate'), b = document.getElementById('intervalsEndDate'); a.min = ''; b.min = ''; a.value = s; b.value = e; }", [a_start.isoformat(), a_end.isoformat()])
            page.evaluate("() => ['summary-checkbox', 'wellness-checkbox'].forEach(id => { const c = document.getElementById(id); c.checked = true; })")
            page.click("#connectIntervals")
            page.wait_for_function("() => [...document.querySelectorAll('.dataset-status-pill')].some(p => /Intervals ICU \\(\\d+ days/.test(p.textContent) && /loaded/.test(p.textContent))", timeout=240000)
            pills = page.evaluate("() => [...document.querySelectorAll('.dataset-status-pill')].map(p => p.textContent.trim())")
            check("the original window loads from the fake Intervals.icu through the real loader: the primary pill with its days and [W+S], an auxiliary pill each for the activity summary and the wellness log",
                  any("Intervals ICU (59 days [W+S]) loaded" in p for p in pills) and any("Activity Summary" in p for p in pills) and any("Wellness" in p for p in pills), pills)
            exec_ds = os.path.join(workdir, "executor", "datasets", USER)
            aux_a = sorted(os.path.basename(p) for p in glob.glob(os.path.join(exec_ds, "*.csv")))
            tag_a = f"{a_start.strftime('%Y%m%d')}_to_{a_end.strftime('%Y%m%d')}"
            check("the loader wrote the summary and the wellness files named after the window", aux_a == [f"activity_summary_{tag_a}.csv", f"wellness_data_{tag_a}.csv"], aux_a)
            page.evaluate("() => { const m = document.getElementById('intervalsModal'); if (m) m.style.display = 'none'; }")

            page.fill("#queryInput", mod.QUESTIONS[0])
            page.evaluate("setMode('deep')")
            page.click("#submitQuery")
            wait_run_end(page, 1)
            page.evaluate("activateTab('answer')")
            page.wait_for_timeout(300)
            answer = page.inner_text("#content-answer")
            check("the scripted analyst read the summary file by the dated name DATA gave it and reported the modal start hour", "Training starts at" in answer and "cell 2" in answer, answer[:200])
            rows = page.evaluate("() => [...document.querySelectorAll('.sp-row')].map(e => e.textContent)")
            check("the chain: three cells and the replay reproduced the three RESULT lines", sum(1 for r in rows if "In\xa0[" in r or "In [" in r) == 3 and any("REPLAY" in r and "reproduced" in r for r in rows), rows)

            # Save as routine: the promoter (scripted) makes the hour band an input; run zero reproduces on the original window
            page.hover("#rankButton")
            page.wait_for_selector("#saveMenu", state="visible", timeout=10000)
            page.click("#saveMenu .it[data-act='routine']")
            page.wait_for_selector("#routineMakeModal .rt-inputs", timeout=120000)
            dlg = page.evaluate("() => ({ inputs: [...document.querySelectorAll('#routineMakeModal .rt-inputs tbody tr')].map(r => [r.dataset.key, r.querySelector('.val').textContent]), results: document.querySelectorAll('#routineMakeModal .rt-results .r').length, data: document.querySelector('#routineMakeModal .rt-data').textContent, notes: [...document.querySelectorAll('#routineMakeModal .rt-sec')].filter(s => s.querySelector('.h') && s.querySelector('.h').textContent === 'Notes').map(s => s.textContent).join(' ') })")
            check("the make dialog: the band as the one input (9, 11), the three result lines, the data as Intervals.icu", dlg["inputs"] == [["band", "9, 11"]] and dlg["results"] == 3 and "Intervals" in dlg["data"], dlg)
            check("the promoter's other proposal - the loaded window as an input written into the summary's file name, as the live promoter did - is refused with the reason in the notes: the name is the loader's, bound at each run",
                  "The period: could not be made an input" in dlg["notes"] and "the loader's" in dlg["notes"], dlg["notes"])
            page.fill("#routineMakeModal [data-field='purpose']", "when training starts, window by window")
            page.click("#routineMakeModal [data-act='create']")
            page.wait_for_function("() => document.querySelector('#routineMakeModal').style.display === 'none' || !!document.querySelector('#routineMakeModal .rt-error')", timeout=180000)
            err = page.evaluate("() => { const e = document.querySelector('#routineMakeModal .rt-error'); return e ? e.textContent : null; }")
            check("Create routine: run zero reproduced the three lines on the original window", err is None, err)
            rdirs = glob.glob(os.path.join(workdir, "webapp", "storage", USER, "routines", "*", "routine.json"))
            rj = json.load(open(rdirs[0])) if rdirs else {}
            rec = rj["versions"][0]["manifest"]["data"] if rdirs else {}
            vs = rj["versions"][0] if rdirs else {}
            check("the stored script: the band read from INPUTS, the summary still read by the loader's dated name (the refused edit left no trace), the band the only parameter",
                  "INPUTS['band']" in (vs.get("script") or "") and "INPUTS['window']" not in (vs.get("script") or "") and re.search(r"pd\.read_csv\('datasets/\S*activity_summary_\d{8}_to_\d{8}\.csv'\)", vs.get("script") or "")
                  and [p["key"] for p in vs.get("manifest", {}).get("parameters", [])] == ["band"], ((vs.get("script") or "")[:300], vs.get("manifest", {}).get("parameters")))
            check("the routine's data record: the source, how it was loaded (the window, the auxiliary kinds), the two auxiliary files and their columns (the shape a run is made to fit)",
                  rec.get("source") == "intervals" and rec.get("load", {}).get("source") == "intervals" and sorted(rec["load"]["aux_kinds"]) == ["summary", "wellness"] and rec["load"]["start_date"] == a_start.isoformat()
                  and len(rec.get("aux") or []) == 2 and set(rec.get("aux_shape") or {}) == set(rec["aux"]) and any(c["name"] == "avg_power" for c in rec["aux_shape"][rec["aux"][0]]["columns"])
                  and any(c["name"] == "power" for c in rec.get("columns", [])), (rec.get("load"), list((rec.get("aux_shape") or {}).keys())))

            # Run: the dialog loads the next window itself - the original's length, ending today - then checks and runs
            page.click("#routinesPill")
            page.wait_for_selector("#routinesModal", state="visible", timeout=10000)
            page.wait_for_function("() => (document.querySelector('#routinesModal .rt-right .title') || {}).textContent", timeout=15000)
            page.click("#routinesModal [data-act='run']")
            page.wait_for_selector("#routineRunModal .rt-load", timeout=30000)
            page.wait_for_function("() => !!document.querySelector('#routineRunModal input[data-load=\"start\"]')", timeout=15000)
            rd = page.evaluate("""() => ({ choice: (document.querySelector('#routineRunModal input[name="rt-data"]:checked') || {}).value, start: document.querySelector('#routineRunModal input[data-load="start"]').value, end: document.querySelector('#routineRunModal input[data-load="end"]').value,
                help: document.querySelector('#routineRunModal .rt-load .help').textContent, now: !!document.querySelector('#routineRunModal input[name="rt-data"][value="now"]'), runOn: !document.querySelector('#routineRunModal [data-act="run"]').disabled, band: document.querySelector('#routineRunModal [data-key="band"]').value })""")
            b_start, b_end = today - timedelta(days=59), today
            check("the run dialog of an Intervals routine: Load from Intervals.icu on, the window of the original's 59 days ending today, with summary, wellness and the metrics as the original; the data loaded now as the other choice; the band at its default; Run on",
                  rd["choice"] == "load" and rd["start"] == b_start.isoformat() and rd["end"] == b_end.isoformat() and "the original\u2019s 59 days, ending today" in rd["help"] and "summary" in rd["help"] and "wellness" in rd["help"] and "metrics as the original" in rd["help"] and rd["now"] and rd["runOn"] and rd["band"] == "9, 11", rd)
            page.click("#routineRunModal [data-act='run']")
            page.wait_for_function("() => { const p = document.querySelector('#routineRunModal .rt-progress'); return !!p && p.style.display !== 'none' && p.textContent.length > 0; }", timeout=30000)
            prog = page.inner_text("#routineRunModal .rt-progress")
            check("while the load runs the dialog shows the loader's progress", "Intervals" in prog or "Download" in prog or "Pars" in prog or "Load" in prog, prog)
            wait_text(page, "#chainPosition", "run 1 of 1", 300000)
            page.wait_for_timeout(800)
            rv = page.evaluate("""() => ({ rows: [...document.querySelectorAll('.sp-row.tool')].map(e => e.textContent), done: (document.querySelector('.sp-done') || {}).textContent || '', warn: !!document.querySelector('.sp-done.warn'),
                cmp: (document.getElementById('content-comparison') || {}).textContent || '', tabs: [...document.querySelectorAll('#tabContainer .tab')].map(e => e.id), pills: [...document.querySelectorAll('.dataset-status-pill')].map(p => p.textContent.trim()),
                locked: document.getElementById('queryInput').disabled, chip: document.querySelector('#containerStatusText').textContent })""")
            tag_b = f"{b_start.strftime('%Y%m%d')}_to_{b_end.strftime('%Y%m%d')}"
            check("the run view: a LOAD row naming the window and its auxiliaries, a CHECK row saying power is empty in this window and the wellness file absent, a RUN row, a COMPARE row; the closing card ran against run 0; the composer locked, the chip back to Ready",
                  any("LOAD" in r and f"Intervals.icu {b_start.isoformat()} → {b_end.isoformat()}" in r and "summary" in r and "wellness" in r for r in rv["rows"])
                  and any("CHECK" in r and "columns empty in this data: power" in r and "wellness absent in this data" in r for r in rv["rows"])
                  and any("RUN" in r and "run 1" in r for r in rv["rows"]) and any("COMPARE" in r and "run 0" in r for r in rv["rows"])
                  and "Run 1 complete" in rv["done"] and ("ran: 3 result lines" in rv["done"] or "reproduced" in rv["done"]) and "against run 0" in rv["done"] and not rv["warn"] and rv["locked"] and rv["chip"] == "Ready", (rv["rows"], rv["done"][:240], rv["chip"]))
            check("the Comparison tab opened with the three lines against run 0, each marked", "tab-comparison" in rv["tabs"] and rv["cmp"].count("sessions") >= 1 and "against run 0" in rv["cmp"] and ("within" in rv["cmp"] or "same" in rv["cmp"] or "moved" in rv["cmp"]), rv["cmp"][:300])
            check("the Data tab's pills now show the run's window (59 days [W+S]) with the summary's pill - the dialog's load refreshed them as the Data tab does", any("Intervals ICU (59 days [W+S]) loaded" in p for p in rv["pills"]) and any("Activity Summary (59 days)" in p for p in rv["pills"]), rv["pills"])
            page.evaluate("activateTab('dataframe')")
            page.wait_for_timeout(300)
            # the Data tab after a live run is the executor's frame view; the stored run's Data tab (through the arrows) carries the load and the bindings
            page.click("#prevResponse")
            wait_text(page, "#chainPosition", "run 0 of 1", 30000)
            page.click("#nextResponse")
            wait_text(page, "#chainPosition", "run 1 of 1", 30000)
            page.wait_for_timeout(400)
            page.evaluate("activateTab('dataframe')")
            page.wait_for_timeout(200)
            dtab = page.inner_text("#content-dataframe")
            check("the stored run's Data tab: loaded as Intervals.icu with the window, the method's summary name bound to this window's file, the wellness file absent",
                  "Loaded as" in dtab and f"Intervals.icu {b_start.isoformat()} → {b_end.isoformat()}" in dtab and f"activity_summary_{tag_a}.csv → activity_summary_{tag_b}.csv" in dtab and "wellness: absent in this data" in dtab, dtab[:400])
            run1 = json.load(open(os.path.join(os.path.dirname(rdirs[0]), "runs", "v1_1", "run.json")))
            run_dir = os.path.join(workdir, "executor", run1["run_dir"])
            check("on disk: the run's record keeps the bindings, the absent file, the fit (power missing) and the shape it made (the summary copy with the columns this window lacked added); the copy and the wellness placeholder are in the run's own folder on the executor's side, nothing in the user's cache",
                  run1["status"] in ("ran", "reproduced") and run1["aux_absent"] == ["wellness"] and "power" in run1["fit"]["missing"] and run1["data"]["load"]["start_date"] == b_start.isoformat()
                  and run1["bindings"] and run1["bindings"][0][0].endswith(f"activity_summary_{tag_a}.csv") and run1["bindings"][0][1].endswith(f"/v1_1/activity_summary_{tag_b}.csv")
                  and "avg_power" in run1["shape"]["files"][run1["bindings"][0][0]]["missing"] and os.path.exists(os.path.join(run_dir, f"activity_summary_{tag_b}.csv")) and os.path.exists(os.path.join(run_dir, f"wellness_data_{tag_a}.csv"))
                  and not os.path.exists(os.path.join(exec_ds, f"wellness_data_{tag_a}.csv.bak")) and sorted(os.path.basename(p) for p in glob.glob(os.path.join(exec_ds, "wellness_data_*.csv"))) == [f"wellness_data_{tag_a}.csv"],
                  (run1.get("status"), run1.get("aux_absent"), run1.get("fit"), run1.get("bindings"), run1.get("shape")))
            # a run on the data loaded now (the window just loaded) with the band changed: the dialog offers it; compared with run 1
            page.click("#routinesPill")
            page.wait_for_selector("#routinesModal", state="visible", timeout=10000)
            page.wait_for_function("() => (document.querySelector('#routinesModal .rt-right .title') || {}).textContent", timeout=15000)
            page.click("#routinesModal [data-act='run']")
            page.wait_for_selector("#routineRunModal input[name='rt-data'][value='now']", timeout=30000)
            page.click("#routineRunModal input[name='rt-data'][value='now']")
            page.fill("#routineRunModal [data-key='band']", "7, 9")
            page.click("#routineRunModal [data-act='run']")
            wait_text(page, "#chainPosition", "run 2 of 2", 300000)
            page.wait_for_timeout(600)
            r2 = page.evaluate("() => ({ rows: [...document.querySelectorAll('.sp-row.tool')].map(e => e.textContent), done: (document.querySelector('.sp-done') || {}).textContent || '' })")
            check("run 2 on the data loaded now with the band 7 to 9: no LOAD row, the CHECK row, compared with run 1 - the band's share moved",
                  not any("LOAD" in r for r in r2["rows"]) and any("CHECK" in r for r in r2["rows"]) and "Run 2 complete" in r2["done"] and "against run 1" in r2["done"], (r2["rows"], r2["done"][:200]))

            # Endura: a routine made on one race, run on another picked in the dialog (the flat crit has no power channel, no climbs)
            page.click("#routinesPill")
            page.wait_for_selector("#routinesModal", state="visible", timeout=10000)
            page.wait_for_selector("#routinesModal .rt-origin", timeout=15000)
            page.click("#routinesModal .rt-origin")
            page.wait_for_function("() => document.getElementById('routinesModal').style.display === 'none' && !RoutinesUI.inRunView() && !document.getElementById('queryInput').disabled && typeof responses !== 'undefined' && responses.length === 1", timeout=30000)
            check("the routine's origin loads from the favourites and unlocks the composer", True)
            # a new thread for the new data (the chain's cells build on the thread's earlier cells, so a routine made in the
            # Intervals thread would carry those cells): the page reloads into a fresh workspace
            page.evaluate("handleNewConversation()")
            page.wait_for_url("**/?new=true", timeout=60000)
            page.wait_for_selector("#queryInput", state="visible", timeout=60000)
            page.app_ready()
            page.wait_for_function("() => /Ready/.test(document.querySelector('#containerStatusText').textContent)", timeout=60000)
            r = fetch_json(page, "/endura/store_api_key", {"api_key": "stack-key"})
            check("the Endura key is stored through its route", r["status"] == 200, r)
            r = fetch_json(page, "/endura/load_data", {"race_id": 1, "aux_datasets": ["profile", "climbs"]})
            check("race 1 loads from the fake Endura through the real loader: the frame's columns (power present), the profile and climbs files", r["status"] == 200 and "power" in (r["json"] or {}).get("columns", []) and len((r["json"] or {}).get("aux_datasets", [])) == 2, r)
            page.fill("#queryInput", "How fast were they, on average?")
            page.click("#submitQuery")
            wait_run_end(page, 1)
            page.hover("#rankButton")
            page.wait_for_selector("#saveMenu", state="visible", timeout=10000)
            page.click("#saveMenu .it[data-act='routine']")
            page.wait_for_selector("#routineMakeModal [data-act='create']", timeout=120000)
            page.wait_for_function("() => !document.querySelector('#routineMakeModal .rt-wait')", timeout=120000)
            page.click("#routineMakeModal [data-act='create']")
            page.wait_for_function("() => document.querySelector('#routineMakeModal').style.display === 'none' || !!document.querySelector('#routineMakeModal .rt-error')", timeout=180000)
            err = page.evaluate("() => { const e = document.querySelector('#routineMakeModal .rt-error'); return e ? e.textContent : null; }")
            check("an Endura routine is made from the generic chain (no inputs; run zero ran)", err is None, err)
            page.click("#routinesPill")
            page.wait_for_selector("#routinesModal", state="visible", timeout=10000)
            page.wait_for_function("() => document.querySelectorAll('#routinesModal .rt-side .it').length >= 2", timeout=15000)
            page.evaluate("() => { const it = [...document.querySelectorAll('#routinesModal .rt-side .it')].find(e => !/Session start/.test(e.textContent)); it && it.click(); }")
            page.wait_for_function("() => /How fast|Route|race|fast/i.test((document.querySelector('#routinesModal .rt-right .title') || {}).textContent) || !/Session start/.test((document.querySelector('#routinesModal .rt-right .title') || {}).textContent)", timeout=15000)
            page.click("#routinesModal [data-act='run']")
            page.wait_for_selector("#routineRunModal select[data-load='race']", timeout=30000)
            page.wait_for_function("() => document.querySelectorAll('#routineRunModal select[data-load=\"race\"] option').length >= 3", timeout=15000)
            ed = page.evaluate("() => ({ options: [...document.querySelectorAll('#routineRunModal select[data-load=\"race\"] option')].map(o => [o.value, o.textContent, o.selected]), help: document.querySelector('#routineRunModal .rt-race .help').textContent })")
            check("the run dialog of an Endura routine: the race list from Endura with the original race (Spring classic) selected, its auxiliaries named", [o[0] for o in ed["options"]] == ["1", "2", "3"] and ed["options"][0][2] and "the original: Spring classic" in ed["help"] and "profile, climbs" in ed["help"], ed)
            page.select_option("#routineRunModal select[data-load='race']", "2")
            page.click("#routineRunModal [data-act='run']")
            wait_text(page, "#chainPosition", "run 1 of 1", 300000)
            page.wait_for_timeout(600)
            re_ = page.evaluate("() => ({ rows: [...document.querySelectorAll('.sp-row.tool')].map(e => e.textContent), done: (document.querySelector('.sp-done') || {}).textContent || '', pills: [...document.querySelectorAll('.dataset-status-pill')].map(p => p.textContent.trim()) })")
            check("the run on the flat crit: a LOAD row naming the race, the CHECK row saying power is empty in this data (the loader dropped the all-zero channel), the run complete; the Data tab's pills show the race and its files (the climbs file is written empty by the loader, so it is bound, not absent)",
                  any("LOAD" in r and "Endura · Flat crit" in r for r in re_["rows"]) and any("CHECK" in r and "columns empty in this data: power" in r for r in re_["rows"])
                  and "Run 1 complete" in re_["done"] and any("Endura (Flat crit) loaded" in p for p in re_["pills"]) and any("race_climbs_race_2" in p for p in re_["pills"]), (re_["rows"], re_["done"][:200], re_["pills"]))
            errs = page.evaluate("window.__stackErrors || []")
            b.close()
        apis = __import__("requests").get(st.apis_url + "/calls", timeout=5).json()["calls"]
        kinds = sorted({c[1].split("/")[2] if c[1].startswith("/api/v1/") else c[1] for c in apis})
        check("the executor fetched everything from the fake APIs: the activity list, the FIT files, the wellness log, the races and the race data", any("/activities" in c[1] for c in apis) and any("fit-file" in c[1] for c in apis) and any("wellness" in c[1] for c in apis) and any("getraces" in c[1] for c in apis) and any("getracedata" in c[1] for c in apis), kinds)
        page_errors = [l for l in logs if l.startswith(("[pageerror]", "[window.error]"))] + [f"[window.error] {e}" for e in errs]
        check("no page errors during the walk", not page_errors, page_errors[:3])
        http_errors = [l for l in logs if l.startswith("[http 5")]
        check("no 5xx answers from the app", not http_errors, http_errors[:3])
        print(f"  (stack workdir {workdir})")
    print(f"{len(passed)} passed, {len(failed)} failed")
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
