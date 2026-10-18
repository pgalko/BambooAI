"""End to end, the integrations: the real web app and executor loading from the stack's fake Intervals.icu and Endura
(tools/stack/fake_apis.py, with FIT files the executor's own parser reads), the scripted analyst writing a method on
one window, Save as routine, and a run that loads the next window itself - where the summary file has another name,
the frame has no power column and the wellness file was not written (docs/ROUTINES_DESIGN.md F2 as rebuilt
2026-10-10). Then Endura: a routine made on one race, run on another with the race picked in the dialog.

    python3 tests/e2e/test_integrations.py        # ~3 minutes; the hosted edition (the loaders need the executor)

Skips (exit 0) when playwright is not installed.
"""
import glob
import pandas as pd
import json
import os
import re
import sys
import tempfile
import time
from datetime import date, timedelta

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path[:0] = [ROOT, os.path.join(ROOT, "tools", "stack"), os.path.join(ROOT, "tools", "stack", "browser")]

try:
    from playwright.sync_api import sync_playwright
except Exception:                                          # noqa: BLE001
    print("playwright not installed: the integrations suite is skipped")
    sys.exit(0)

import vendor                                              # noqa: E402
import harness_models                                      # noqa: E402
import apis_data                                           # noqa: E402
from analyst.routines import aux_kind, number as rt_number, mirror_path as aux_mirror     # noqa: E402
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


def wait_verified(routine_json, timeout=240):
    """Run zero runs behind the dialog (2026-10-15): wait until the stored version's verdict is in, and return it."""
    t0 = time.time()
    while time.time() - t0 < timeout:
        try:
            rj = json.load(open(routine_json))
            rz = (rj.get("versions") or [{}])[-1].get("run_zero") or {}
            if rz.get("status") not in (None, "", "verifying"):
                return rj
        except (OSError, ValueError):
            pass
        time.sleep(1.0)
    return json.load(open(routine_json))


def set_window(page, start, end):
    """The dialog's dates, set once the subscription limits have landed on the inputs (applyIntervalsDateLimits is
    async and writes today-365 when it resolves: set before it, the window was overwritten - 2026-10-14)."""
    page.wait_for_function("() => (document.getElementById('intervalsEndDate') || {}).max", timeout=15000)
    page.evaluate("([s, e]) => { const a = document.getElementById('intervalsStartDate'), b = document.getElementById('intervalsEndDate'); a.min = ''; b.min = ''; a.value = s; b.value = e; }", [start.isoformat(), end.isoformat()])


def calls_of(st, kind):
    """How many calls the fake APIs have seen whose path carries `kind` (fit-file, messages...), from their log."""
    return len([c for c in __import__("requests").get(st.apis_url + "/calls", timeout=5).json()["calls"] if kind in c[1]])


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
            set_window(page, a_start, a_end)
            rd_default = page.evaluate("() => document.getElementById('rider-checkbox').checked")
            page.evaluate("() => { ['summary-checkbox', 'wellness-checkbox'].forEach(id => { const c = document.getElementById(id); c.checked = true; }); ['context-checkbox', 'rider-checkbox'].forEach(id => { const c = document.getElementById(id); if (c) c.checked = false; }); }")   # the context and the rider profile (both on by default) are walked at the end
            page.click("#connectIntervals")
            page.wait_for_function("() => [...document.querySelectorAll('.dataset-status-pill')].some(p => /Intervals ICU \\(\\d+ days/.test(p.textContent) && /loaded/.test(p.textContent))", timeout=240000)
            pills = page.evaluate("() => [...document.querySelectorAll('.dataset-status-pill')].map(p => p.textContent.trim())")
            check("the original window loads from the fake Intervals.icu through the real loader: the primary pill with its days and [W+S], an auxiliary pill each for the activity summary and the wellness log",
                  any("Intervals ICU (59 days [W+S]) loaded" in p for p in pills) and any("Activity Summary" in p for p in pills) and any("Wellness" in p for p in pills), pills)
            import hashlib
            _kf = lambda k: hashlib.sha256(k.encode("utf-8")).hexdigest()[:12]      # analyst.routines.key_fingerprint = the loader's key_mark
            exec_ds = os.path.join(workdir, "executor", "datasets", USER, _kf("stack-key"))                                # the key's own folder (2026-10-11)
            aux_a = sorted(os.path.basename(p) for p in glob.glob(os.path.join(exec_ds, "*.csv")))
            tag_a = f"{a_start.strftime('%Y%m%d')}_to_{a_end.strftime('%Y%m%d')}"
            check("the loader wrote the summary and the wellness files named after the window, under the folder of the key that loaded them; nothing at the user's folder itself",
                  aux_a == [f"activity_summary_{tag_a}.csv", f"wellness_data_{tag_a}.csv"] and not glob.glob(os.path.join(workdir, "executor", "datasets", USER, "*.csv")), aux_a)
            # the store below the cache (docs/INCREMENTAL_LOADS_DESIGN.md, 2026-10-15): the first load fetched the window whole and kept it
            msg_a = page.inner_text("#intervals-modal-message")
            store_a = os.path.join(exec_ds, "store")
            manifest_a = json.load(open(os.path.join(store_a, "activities.json"))) if os.path.isfile(os.path.join(store_a, "activities.json")) else {}
            check("the first load downloaded the window whole and the dialog's line says so (60 activities downloaded); the executor kept every activity in the key's store - the manifest and one file each - beside the window's files",
                  "Data loaded successfully! 60 activities downloaded." in msg_a and len(manifest_a) == 60 and len(os.listdir(os.path.join(store_a, "activities"))) == 60 and all(r.get("signature") and r.get("day") for r in manifest_a.values()),
                  (msg_a, len(manifest_a), sorted(os.listdir(store_a)) if os.path.isdir(store_a) else None))
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
            dlg = page.evaluate("() => ({ inputs: [...document.querySelectorAll('#routineMakeModal .rt-inputs tbody tr')].map(r => [r.dataset.key, r.querySelector('.val').textContent, r.dataset.derived || '', (r.querySelector('.rt-derived') || {}).textContent || '']), results: document.querySelectorAll('#routineMakeModal .rt-results .r').length, data: document.querySelector('#routineMakeModal .rt-data').textContent, notes: [...document.querySelectorAll('#routineMakeModal .rt-sec')].filter(s => s.querySelector('.h') && s.querySelector('.h').textContent === 'Notes').map(s => s.textContent).join(' ') })")
            check("the make dialog: the band (9, 11), the session types (a choice over the summary file's column) and the dates typed into the label as the inputs, the three result lines, the data as Intervals.icu",
                  [i[:2] for i in dlg["inputs"]] == [["band", "9, 11"], ["kinds", "Ride, Run"], ["span", f"{a_start.isoformat()} → {a_end.isoformat()}"]] and dlg["results"] == 3 and "Intervals" in dlg["data"], dlg)
            check("the dates typed into the label are the frame's first and last: the row says the input follows the data, written at each run (the probe recorded the frame's period at promotion)",
                  dlg["inputs"][2][2] == "span" and "follows the data: its first and last dates" in dlg["inputs"][2][3] and dlg["inputs"][0][2] == "" and dlg["inputs"][1][2] == "", dlg["inputs"])
            check("the promoter's other proposal - the loaded window as an input written into the summary's file name, as the live promoter did - is refused with the reason in the notes: the name is the loader's, bound at each run",
                  "The period: could not be made an input" in dlg["notes"] and "the loader's" in dlg["notes"], dlg["notes"])
            page.fill("#routineMakeModal [data-field='purpose']", "when training starts, window by window")
            page.click("#routineMakeModal [data-act='create']")
            page.wait_for_function("() => document.querySelector('#routineMakeModal').style.display === 'none' || !!document.querySelector('#routineMakeModal .rt-error')", timeout=180000)
            err = page.evaluate("() => { const e = document.querySelector('#routineMakeModal .rt-error'); return e ? e.textContent : null; }")
            t_create = time.time()
            rdirs = glob.glob(os.path.join(workdir, "webapp", "storage", USER, "routines", "*", "routine.json"))
            rj0 = json.load(open(rdirs[0])) if rdirs else {}
            check("Create routine returns without waiting for run zero: the dialog closed with no error and the routine is stored - as verifying, or already with its verdict when run zero was quicker than the page (2026-10-15)",
                  err is None and rdirs and (rj0.get("versions") or [{}])[0].get("run_zero", {}).get("status") in ("verifying", "reproduced"), (err, (rj0.get("versions") or [{}])[0].get("run_zero")))
            rj = wait_verified(rdirs[0]) if rdirs else {}
            check("run zero's verdict lands on the stored version: reproduced the three lines on the original window; the toast said so",
                  (rj.get("versions") or [{}])[0].get("run_zero", {}).get("status") == "reproduced" and (rj.get("versions") or [{}])[0].get("run_zero", {}).get("verified") is True, (rj.get("versions") or [{}])[0].get("run_zero"))
            rec = rj["versions"][0]["manifest"]["data"] if rdirs else {}
            vs = rj["versions"][0] if rdirs else {}
            check("the stored script: the band read from INPUTS, the summary still read by the loader's dated name (the refused edit left no trace), the band the only parameter",
                  "INPUTS['band']" in (vs.get("script") or "") and "INPUTS['window']" not in (vs.get("script") or "") and re.search(r"pd\.read_csv\('datasets/\S*activity_summary_\d{8}_to_\d{8}\.csv'\)", vs.get("script") or "")
                  and [(p["key"], p.get("derived")) for p in vs.get("manifest", {}).get("parameters", [])] == [("band", None), ("kinds", None), ("span", "span")]
                  and (vs.get("manifest", {}).get("data", {}).get("span") or {}).get("column") == "datetime", ((vs.get("script") or "")[:300], vs.get("manifest", {}).get("parameters"), vs.get("manifest", {}).get("data", {}).get("span")))
            check("the routine's data record: the source, how it was loaded (the window, the auxiliary kinds, the mark of the key - never the key), the two auxiliary files in the key's folder and their columns (the shape a run is made to fit)",
                  rec.get("source") == "intervals" and rec.get("load", {}).get("source") == "intervals" and sorted(rec["load"]["aux_kinds"]) == ["summary", "wellness"] and rec["load"]["start_date"] == a_start.isoformat()
                  and rec["load"].get("key") == _kf("stack-key") and "stack-key" not in json.dumps(rec) and all(f"/{_kf('stack-key')}/" in p for p in rec.get("aux") or [])
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
                help: document.querySelector('#routineRunModal .rt-load .help').textContent, now: !!document.querySelector('#routineRunModal input[name="rt-data"][value="now"]'), runOn: !document.querySelector('#routineRunModal [data-act="run"]').disabled, band: document.querySelector('#routineRunModal [data-key="band"]').value,
                span: (document.querySelector('#routineRunModal .rt-derived-row') || {}).textContent || '', spanPickers: document.querySelectorAll('#routineRunModal [data-key="span"]').length,
                kinds: document.querySelector('#routineRunModal [data-key="kinds"]').value, fit: (document.querySelector('#routineRunModal .rt-fit') || {}).textContent || '' })""")
            b_start, b_end = today - timedelta(days=59), today
            local_today = page.evaluate("() => ({ today: localIsoDay(new Date()), dataTabMax: (document.getElementById('intervalsEndDate') || {}).max || '', utc: new Date().toISOString().slice(0, 10) })")
            check("the run dialog's window ends on the page's local calendar day - the same day the Data tab's dialog offers as its latest (2026-10-15: both had taken the UTC day, a day apart before 11:00 in Melbourne)",
                  rd["end"] == local_today["today"] and local_today["dataTabMax"] == local_today["today"], (rd["end"], local_today))
            check("the run dialog of an Intervals routine: Load from Intervals.icu on, the window of the original's 59 days ending today, with summary, wellness and the metrics as the original; the data loaded now as the other choice; the band at its default; Run on",
                  rd["choice"] == "load" and rd["start"] == b_start.isoformat() and rd["end"] == b_end.isoformat() and "the original\u2019s 59 days, ending today" in rd["help"] and "summary" in rd["help"] and "wellness" in rd["help"] and "metrics as the original" in rd["help"] and rd["now"] and rd["runOn"] and rd["band"] == "9, 11", rd)
            check("the session types (a choice over the summary file's column, not the frame's) are checked where they live: the data loaded now passes, nothing missing",
                  rd["kinds"] == "Ride, Run" and rd["fit"].startswith("✓ fits the routine") and "is not in" not in rd["fit"] and "not in this data" not in rd["fit"], rd["fit"])
            check("the dates input is not asked: no pickers, a line saying it follows the data, the original's dates for the record",
                  rd["spanPickers"] == 0 and "follows the data: its first and last dates" in rd["span"] and f"the original: {a_start.isoformat()} → {a_end.isoformat()}" in rd["span"], rd["span"])
            page.wait_for_function("() => { const c = document.querySelector('#routineRunModal .rt-cache'); return !!c && c.style.display !== 'none' && c.textContent.length > 0; }", timeout=15000)
            cl = page.evaluate("() => ({ text: document.querySelector('#routineRunModal .rt-cache').textContent, cls: document.querySelector('#routineRunModal .rt-cache').className })")
            check("the dialog asked the executor's cache about the window: the next window is not there, so it says it will be downloaded", "miss" in cl["cls"] and "not in the cache" in cl["text"] and "will be downloaded" in cl["text"], cl)
            refresh_box = page.evaluate("() => { const b = document.querySelector('#routineRunModal input[data-load=\"refresh\"]'); return b ? { on: b.checked, text: b.closest('label').textContent } : null; }")
            check("the run dialog offers Everything again under the window, off (the store below the cache, 2026-10-15)", refresh_box and refresh_box["on"] is False and "fetch every file and message of the window afresh" in refresh_box["text"], refresh_box)
            fits_before_run1 = calls_of(st, "fit-file")
            page.click("#routineRunModal [data-act='run']")
            page.wait_for_function("() => { const p = document.querySelector('#routineRunModal .rt-progress'); return !!p && p.style.display !== 'none' && p.textContent.length > 0; }", timeout=30000)
            first = page.inner_text("#routineRunModal .rt-progress")
            page.wait_for_function("() => { const p = document.querySelector('#routineRunModal .rt-progress'); return !!p && /Intervals|Download|Pars|Load/.test(p.textContent); }", timeout=30000)
            prog = page.inner_text("#routineRunModal .rt-progress")
            check("the dialog first clears the data loaded now, then shows the loader's progress", (first.startswith("Clearing") or "Intervals" in first) and ("Intervals" in prog or "Download" in prog or "Pars" in prog or "Load" in prog), (first, prog))
            wait_text(page, "#chainPosition", "run 1 of 1", 300000)
            page.wait_for_timeout(800)
            rv = page.evaluate("""() => ({ rows: [...document.querySelectorAll('.sp-row.tool')].map(e => e.textContent), done: (document.querySelector('.sp-done') || {}).textContent || '', warn: !!document.querySelector('.sp-done.warn'),
                cmp: (document.getElementById('content-comparison') || {}).textContent || '', tabs: [...document.querySelectorAll('#tabContainer .tab')].map(e => e.id), pills: [...document.querySelectorAll('.dataset-status-pill')].map(p => p.textContent.trim()),
                locked: document.getElementById('queryInput').disabled, chip: document.querySelector('#containerStatusText').textContent })""")
            tag_b = f"{b_start.strftime('%Y%m%d')}_to_{b_end.strftime('%Y%m%d')}"
            fits_run1 = calls_of(st, "fit-file") - fits_before_run1
            load_row = page.evaluate("() => { const r = [...document.querySelectorAll('.sp-row.tool')].find(e => /LOAD/.test(e.textContent)); return r ? { text: r.textContent, fold: (r.querySelector('.out') || {}).title || '' } : null; }")
            check("run 1's load fetched only the days the store lacked: 41 FIT files for the 60-day window (19 of its days are the original's, held under the same signature); the LOAD row's fold says 19 of 60 activities from the store, 41 downloaded",
                  fits_run1 == 41 and load_row is not None and "19 of 60 activities from the store, 41 downloaded" in load_row["fold"], (fits_run1, load_row))
            check("the run view: a LOAD row naming the window and its auxiliaries, a CHECK row saying power is empty in this window, the wellness file absent and one of the chosen session types not in this window's summary (the method keeps the other), a RUN row, a COMPARE row; the closing card ran against run 0; the composer locked, the chip back to Ready",
                  any("LOAD" in r and f"Intervals.icu {b_start.isoformat()} → {b_end.isoformat()}" in r and "summary" in r and "wellness" in r for r in rv["rows"])
                  and any("CHECK" in r and "columns empty in this data: power" in r and "wellness absent in this data" in r and "'Ride' is not in column type of the summary file - the method keeps the other value" in r for r in rv["rows"])
                  and any("RUN" in r and "run 1" in r for r in rv["rows"]) and any("COMPARE" in r and "run 0" in r for r in rv["rows"])
                  and "Run 1 complete" in rv["done"] and ("ran: 3 result lines" in rv["done"] or "reproduced" in rv["done"]) and "against run 0" in rv["done"] and not rv["warn"] and rv["locked"] and rv["chip"] == "Ready", (rv["rows"], rv["done"][:240], rv["chip"]))
            check("the Comparison tab opened with the three lines against run 0, each marked", "tab-comparison" in rv["tabs"] and rv["cmp"].count("sessions") >= 1 and "against run 0" in rv["cmp"] and ("within" in rv["cmp"] or "same" in rv["cmp"] or "moved" in rv["cmp"]), rv["cmp"][:300])
            # what differs, said in sentences (step 4, 2026-10-11): the frame's rows and the summary file's rows against the original's
            _chk1 = next((r for r in rv["rows"] if "CHECK" in r), "")
            check("the CHECK row says what differs from the original in sentences: the frame's rows against the original's, the summary file's rows against the original's and its columns added empty",
                  ("rows as the original" in _chk1 or "rows where the original had" in _chk1) and "the summary file:" in _chk1
                  and ("rows as the original" in _chk1.split("the summary file:")[1] or "rows where the original had" in _chk1.split("the summary file:")[1]) and set(re.search(r"columns added empty \(([^)]*)\)", _chk1).group(1).split(", ")) == {"paired_event_id", "chat_id", "avg_power", "elevation_gain_m", "workout_compliance"}, _chk1)     # the ride-only columns (the pairing, the compliance) and the chat flag (the last sixty days carry no chat in the fake) join avg_power and elevation (2026-10-13); the order follows the first activity's fields, so a set
            check("the Data tab's pills now show the run's window (59 days [W+S]) with the summary's pill - the dialog's load refreshed them as the Data tab does - and only them: the original window's pills were cleared before the load (its wellness pill is gone; one Intervals pill)",
                  any("Intervals ICU (59 days [W+S]) loaded" in p for p in rv["pills"]) and any("Activity Summary (59 days)" in p for p in rv["pills"]) and sum(1 for p in rv["pills"] if "Intervals ICU" in p) == 1 and not any("Wellness" in p for p in rv["pills"]) and len(rv["pills"]) == 2, rv["pills"])
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
            check("the run's record carries the store's part of its load (window, held, fetched, refresh) and the stored run's Data tab says it", run1["data"]["load"].get("store") == {"window": 60, "held": 19, "fetched": 41, "refresh": False} and "19 of 60 activities from the store, 41 downloaded" in dtab, (run1["data"]["load"].get("store"), dtab[:300]))
            sp = run1.get("inputs", {}).get("span") or ["", ""]
            check("the dates input was written from this window's frame: its first and last dates on the record, inside the window loaded and not the original's; the label printed carries them; the output keeps no marker line",
                  b_start.isoformat() <= sp[0] <= sp[1] <= b_end.isoformat() and sp != [a_start.isoformat(), a_end.isoformat()] and run1["inputs"].get("band") == [9, 11]
                  and (run1.get("results") or [{}])[0].get("what") == f"sessions in the window {sp[0]} to {sp[1]}"
                  and "ROUTINE_INPUTS" not in open(os.path.join(os.path.dirname(rdirs[0]), "runs", "v1_1", "stdout.txt"), encoding="utf-8").read(), (sp, run1.get("inputs"), (run1.get("results") or [{}])[0]))
            check("on disk: the run's record keeps the bindings, the absent file, the fit (power missing) and the shape it made (the summary copy with the columns this window lacked added); the copy and the wellness placeholder are in the run's own folder on the executor's side, nothing in the user's cache",
                  run1["status"] in ("ran", "reproduced") and run1["aux_absent"] == ["wellness"] and "power" in run1["fit"]["missing"] and run1["data"]["load"]["start_date"] == b_start.isoformat()
                  and run1["bindings"] and run1["bindings"][0][0].endswith(f"activity_summary_{tag_a}.csv") and run1["bindings"][0][1] == aux_mirror(run1["run_dir"], run1["bindings"][0][0])     # the mirror of the recorded path (2026-10-15)
                  and run1["sources"][run1["bindings"][0][0]].endswith(f"activity_summary_{tag_b}.csv")
                  and "avg_power" in run1["shape"]["files"][run1["bindings"][0][0]]["missing"] and os.path.exists(os.path.join(workdir, "executor", run1["bindings"][0][1]))
                  and os.path.exists(os.path.join(workdir, "executor", aux_mirror(run1["run_dir"], next(p_ for p_ in run1["shape"]["placeholders"]))))
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

            # run 3 on the original window again: it is in the executor's cache with its summary and wellness files, so the dialog
            # says so as the dates are set and the run takes it from there - no download (the fake API sees no new FIT requests)
            fits_before = len([c for c in __import__("requests").get(st.apis_url + "/calls", timeout=5).json()["calls"] if "fit-file" in c[1]])
            page.click("#routinesPill")
            page.wait_for_selector("#routinesModal", state="visible", timeout=10000)
            page.wait_for_function("() => (document.querySelector('#routinesModal .rt-right .title') || {}).textContent", timeout=15000)
            page.click("#routinesModal [data-act='run']")
            page.wait_for_function("() => !!document.querySelector('#routineRunModal input[data-load=\"start\"]')", timeout=30000)
            page.evaluate("([s, e]) => { const a = document.querySelector('#routineRunModal input[data-load=\"start\"]'), b = document.querySelector('#routineRunModal input[data-load=\"end\"]'); a.value = s; b.value = e; b.dispatchEvent(new Event('change', { bubbles: true })); }", [a_start.isoformat(), a_end.isoformat()])
            page.wait_for_function("() => { const c = document.querySelector('#routineRunModal .rt-cache'); return !!c && /hit/.test(c.className); }", timeout=15000)
            cl3 = page.inner_text("#routineRunModal .rt-cache")
            check("the window set back to the original's: the line says it is in the cache with summary and wellness - no download", "in the cache" in cl3 and "no download" in cl3 and "summary" in cl3 and "wellness" in cl3, cl3)
            page.click("#routineRunModal [data-act='run']")
            wait_text(page, "#chainPosition", "run 3 of 3", 300000)
            page.wait_for_timeout(800)
            r3 = page.evaluate("() => ({ rows: [...document.querySelectorAll('.sp-row.tool')].map(e => e.textContent), done: (document.querySelector('.sp-done') || {}).textContent || '', pills: [...document.querySelectorAll('.dataset-status-pill')].map(p => p.textContent.trim()) })")
            fits_after = len([c for c in __import__("requests").get(st.apis_url + "/calls", timeout=5).json()["calls"] if "fit-file" in c[1]])
            run3 = json.load(open(os.path.join(os.path.dirname(rdirs[0]), "runs", "v1_3", "run.json")))
            check("run 3 took the original window from the cache: the LOAD row says so, nothing was downloaded (no new FIT requests at the fake API), the record's load says cached with the window, the frame is the original load's, the summary and wellness files bound, the pills show the window with both auxiliaries",
                  any("LOAD" in r and f"Intervals.icu {a_start.isoformat()} → {a_end.isoformat()}" in r and "from the cache" in r for r in r3["rows"]) and "Run 3 complete" in r3["done"] and fits_after == fits_before
                  and run3["data"]["load"].get("cached") is True and run3["data"]["load"]["start_date"] == a_start.isoformat() and run3["data"]["df_id"] == rec.get("df_id") and run3["aux_absent"] == [] and run3["status"] in ("ran", "reproduced")
                  and sum(1 for p in r3["pills"] if "Intervals ICU" in p) == 1 and any("Wellness" in p for p in r3["pills"]) and any("Activity Summary" in p for p in r3["pills"]), (r3["rows"], r3["done"][:160], (fits_before, fits_after), run3["data"].get("load"), run3.get("aux_absent"), r3["pills"]))

            # run 4 on a window inside the original's: the cached load around it is used and cut to the window before the method
            # runs - the frame by its dates, the summary and wellness files by theirs - so the counts are the window's, not the cached load's
            c_start, c_end = a_start + timedelta(days=10), a_end - timedelta(days=12)
            page.click("#routinesPill")
            page.wait_for_selector("#routinesModal", state="visible", timeout=10000)
            page.wait_for_function("() => (document.querySelector('#routinesModal .rt-right .title') || {}).textContent", timeout=15000)
            page.click("#routinesModal [data-act='run']")
            page.wait_for_function("() => !!document.querySelector('#routineRunModal input[data-load=\"start\"]')", timeout=30000)
            page.evaluate("([s, e]) => { const a = document.querySelector('#routineRunModal input[data-load=\"start\"]'), b = document.querySelector('#routineRunModal input[data-load=\"end\"]'); a.value = s; b.value = e; b.dispatchEvent(new Event('change', { bubbles: true })); }", [c_start.isoformat(), c_end.isoformat()])
            page.wait_for_function("() => { const c = document.querySelector('#routineRunModal .rt-cache'); return !!c && /hit/.test(c.className) && /cut/.test(c.textContent); }", timeout=15000)
            cl4 = page.inner_text("#routineRunModal .rt-cache")
            check("a window inside the original's: the line says it is inside the cached load and will be cut to the window - no download", f"inside the cached load {a_start.isoformat()} → {a_end.isoformat()}" in cl4 and "cut to the window, no download" in cl4, cl4)
            page.click("#routineRunModal [data-act='run']")
            wait_text(page, "#chainPosition", "run 4 of 4", 300000)
            page.wait_for_timeout(800)
            r4 = page.evaluate("() => ({ rows: [...document.querySelectorAll('.sp-row.tool')].map(e => e.textContent), done: (document.querySelector('.sp-done') || {}).textContent || '', pills: [...document.querySelectorAll('.dataset-status-pill')].map(p => p.textContent.trim()) })")
            fits_after4 = len([c for c in __import__("requests").get(st.apis_url + "/calls", timeout=5).json()["calls"] if "fit-file" in c[1]])
            run4 = json.load(open(os.path.join(os.path.dirname(rdirs[0]), "runs", "v1_4", "run.json")))
            n_days = (c_end - c_start).days + 1
            got4 = {x.get("what", ""): x.get("estimate") for x in (run4.get("results") or [])}
            sessions4 = next((v for k, v in got4.items() if k.startswith("sessions in the window")), None)
            check("run 4 was cut from the cached load: the LOAD and CHECK rows say so, nothing downloaded, the record's load names the window and the cached load it was cut from, the data record says the window and fewer rows than the cached load, the file the method names is bound to its cut copy under the window's name, the session count is the window's days (one a day in the fake data) and the dates input is the cut frame's first and last",
                  any("LOAD" in r and f"Intervals.icu {c_start.isoformat()} → {c_end.isoformat()}" in r and "cut from the cache" in r for r in r4["rows"]) and any("CHECK" in r and f"cut to {c_start.isoformat()} → {c_end.isoformat()} from the cached load {a_start.isoformat()} → {a_end.isoformat()}" in r for r in r4["rows"])
                  and "Run 4 complete" in r4["done"] and fits_after4 == fits_after and run4["data"]["load"].get("cached_from") == [a_start.isoformat(), a_end.isoformat()] and run4["data"]["load"]["start_date"] == c_start.isoformat()
                  and run4["data"]["date_range"] == f"{c_start.isoformat()} to {c_end.isoformat()}" and run4["data"]["rows"] < run3["data"]["rows"] and all(b[2] == "cut" for b in run4["bindings"])
                  and [os.path.basename(b[1]) for b in run4["bindings"]] == [f"activity_summary_{tag_a}.csv"] and run4["bindings"][0][1] == aux_mirror(run4["run_dir"], run4["bindings"][0][0])   # the method names the summary only, at its mirror path; the wellness file is cut beside it, unnamed
                  and sessions4 is not None and float(sessions4) == n_days and run4["inputs"].get("span") == [c_start.isoformat(), c_end.isoformat()] and run4["status"] in ("ran", "reproduced"),
                  (r4["rows"], (fits_after, fits_after4), run4["data"].get("load"), run4["data"].get("date_range"), run4["data"].get("rows"), run4.get("bindings"), got4, run4.get("inputs"), run4.get("status"), (run4.get("error") or "")[-200:]))
            check("the Data tab's pills after the cut run show what the session holds - the cached load's window - not the run's", any(f"Intervals ICU (59 days [W+S]) loaded" in p for p in r4["pills"]), r4["pills"])

            # a chain on the window a run took from the cache, then a routine from it (2026-10-12): the session's frame came
            # "from the cache", and the chain's record must still say the Intervals load - its window, kinds and key - so the
            # routine's run dialog offers the window, not a file upload (the live case: the dialog offered Upload a file)
            page.click("#routinesPill")
            page.wait_for_selector("#routinesModal", state="visible", timeout=10000)
            page.wait_for_selector("#routinesModal .rt-origin", timeout=15000)
            page.click("#routinesModal .rt-origin")
            page.wait_for_function("() => document.getElementById('routinesModal').style.display === 'none' && !RoutinesUI.inRunView() && !document.getElementById('queryInput').disabled && typeof responses !== 'undefined' && responses.length >= 1", timeout=30000)
            page.fill("#queryInput", "How many sessions are in this window, again?")
            page.click("#submitQuery")
            wait_text(page, "#chainPosition", "chain 2 of 2", 120000)
            wait_run_end(page, 2)
            page.hover("#rankButton")
            page.wait_for_selector("#saveMenu", state="visible", timeout=10000)
            page.click("#saveMenu .it[data-act='routine']")
            page.wait_for_selector("#routineMakeModal [data-act='create']", timeout=120000)
            page.wait_for_function("() => !document.querySelector('#routineMakeModal .rt-wait')", timeout=120000)
            mk = page.evaluate("""() => { const v = document.querySelector('#routineMakeModal .rt-version'); const on = v && v.querySelector('.ui-choice.on');
                return { heading: v ? v.parentNode.querySelector('.h').textContent : '', on: on ? on.getAttribute('data-version') : '', label: document.querySelector('#routineMakeModal [data-act="create"] span').textContent,
                         name: document.querySelector('#routineMakeModal [data-field="name"]').value }; }""")
            check("Save as routine on a later chain of the thread: 'a routine was made from an earlier chain', A new routine on by default, the button reads Create routine, the name the proposal's",
                  "earlier chain of this thread" in mk["heading"] and mk["on"] == "new" and mk["label"] == "Create routine" and "Session start" not in mk["name"], mk)
            page.fill("#routineMakeModal [data-field='name']", "Again on the cached window")
            page.click("#routineMakeModal [data-act='create']")
            page.wait_for_function("() => document.querySelector('#routineMakeModal').style.display === 'none' || !!document.querySelector('#routineMakeModal .rt-error')", timeout=180000)
            err_c = page.evaluate("() => { const e = document.querySelector('#routineMakeModal .rt-error'); return e ? e.textContent : null; }")
            check("...created: run zero ran on the cached frame", err_c is None, err_c)
            rj_c_path = next((f for f in glob.glob(os.path.join(workdir, "webapp", "storage", USER, "routines", "*", "routine.json")) if "Again on the cached window" in open(f).read()), None)
            rj_c = wait_verified(rj_c_path) if rj_c_path else {}
            check("...and its verdict landed: reproduced", (rj_c.get("versions") or [{}])[0].get("run_zero", {}).get("status") == "reproduced", (rj_c.get("versions") or [{}])[0].get("run_zero"))
            load_c = ((rj_c.get("versions") or [{}])[0].get("manifest") or {}).get("data", {}).get("load") or {}
            check("the routine's data record: the load is the cached frame's own Intervals load - the window, the kinds, the key's mark - marked cached, not 'cache'",
                  load_c.get("source") == "intervals" and load_c.get("cached") is True and load_c.get("start_date") == a_start.isoformat() and load_c.get("end_date") == a_end.isoformat()
                  and sorted(load_c.get("aux_kinds") or []) == ["summary", "wellness"] and load_c.get("key") == _kf("stack-key"), load_c)
            page.click("#routinesPill")
            page.wait_for_selector("#routinesModal", state="visible", timeout=10000)
            page.wait_for_function("() => [...document.querySelectorAll('#routinesModal .rt-side .it')].some(e => /Again on the cached window/.test(e.textContent))", timeout=15000)
            page.evaluate("() => { const it = [...document.querySelectorAll('#routinesModal .rt-side .it')].find(e => /Again on the cached window/.test(e.textContent)); it && it.click(); }")
            page.wait_for_function("() => /Again on the cached window/.test((document.querySelector('#routinesModal .rt-right .title') || {}).textContent)", timeout=15000)
            page.click("#routinesModal [data-act='run']")
            page.wait_for_function("() => !!document.querySelector('#routineRunModal input[data-load=\"start\"]') || !!document.querySelector('#routineRunModal input[data-load=\"file\"]')", timeout=30000)
            rd_c = page.evaluate("() => ({ window: !!document.querySelector('#routineRunModal input[data-load=\"start\"]'), file: !!document.querySelector('#routineRunModal input[data-load=\"file\"]'), help: (document.querySelector('#routineRunModal .help') || {}).textContent || '' })")
            check("its run dialog: Load from Intervals.icu with the original's window (59 days ending today, summary and wellness) - no file upload",
                  rd_c["window"] and not rd_c["file"] and "59 days, ending today" in rd_c["help"] and "summary" in rd_c["help"], rd_c)
            page.click("#routineRunModal [data-act='cancel']")
            page.evaluate("RoutinesUI.closeManager()")
            page.wait_for_function("() => document.getElementById('routinesModal').style.display === 'none'", timeout=10000)
            r = fetch_json(page, "/routines/" + rj_c.get("id", "none"), {}, "DELETE")       # the rest of the walk runs the first routine by its place in the list
            check("the routine from the second chain deleted again (the rest of the walk runs the first)", r["status"] == 200, r)

            # the coach changes the key (another subject): the cached windows are the first subject's and must not be served
            r = fetch_json(page, "/intervals/store_api_key", {"api_key": "stack-key-two"})
            check("another Intervals.icu key stored", r["status"] == 200, r)
            page.click("#routinesPill")
            page.wait_for_selector("#routinesModal", state="visible", timeout=10000)
            page.wait_for_function("() => (document.querySelector('#routinesModal .rt-right .title') || {}).textContent", timeout=15000)
            page.click("#routinesModal [data-act='run']")
            page.wait_for_function("() => !!document.querySelector('#routineRunModal input[data-load=\"start\"]')", timeout=30000)
            page.evaluate("([s, e]) => { const a = document.querySelector('#routineRunModal input[data-load=\"start\"]'), b = document.querySelector('#routineRunModal input[data-load=\"end\"]'); a.value = s; b.value = e; b.dispatchEvent(new Event('change', { bubbles: true })); }", [a_start.isoformat(), a_end.isoformat()])
            page.wait_for_function("() => { const c = document.querySelector('#routineRunModal .rt-cache'); return !!c && c.style.display !== 'none' && /another key/.test(c.textContent); }", timeout=15000)
            cl5 = page.inner_text("#routineRunModal .rt-cache")
            check("under another key the original window, though cached, is not used: the line says it was loaded under another key and will be downloaded", "loaded under another key" in cl5 and "will be downloaded" in cl5, cl5)
            page.click("#routineRunModal [data-act='run']")
            wait_text(page, "#chainPosition", "run 5 of 5", 300000)
            page.wait_for_timeout(800)
            r5 = page.evaluate("() => ({ rows: [...document.querySelectorAll('.sp-row.tool')].map(e => e.textContent), done: (document.querySelector('.sp-done') || {}).textContent || '' })")
            fits_after5 = len([c for c in __import__("requests").get(st.apis_url + "/calls", timeout=5).json()["calls"] if "fit-file" in c[1]])
            run5 = json.load(open(os.path.join(os.path.dirname(rdirs[0]), "runs", "v1_5", "run.json")))
            check("run 5 downloaded the window afresh under the new key (new FIT requests, no 'from the cache'), and its record carries the new key's mark - never the key",
                  fits_after5 > fits_after4 and any("LOAD" in r and "from the cache" not in r for r in r5["rows"]) and "Run 5 complete" in r5["done"] and run5["data"]["load"].get("key") == _kf("stack-key-two") and "stack-key-two" not in json.dumps(run5),
                  (r5["rows"], (fits_after4, fits_after5), run5["data"].get("load")))
            exec_ds2 = os.path.join(workdir, "executor", "datasets", USER, _kf("stack-key-two"))
            check("the second key's files went to its own folder; the first key's are where they were", os.path.exists(os.path.join(exec_ds2, f"activity_summary_{tag_a}.csv")) and os.path.exists(os.path.join(exec_ds, f"activity_summary_{tag_a}.csv")), (sorted(os.listdir(exec_ds2)), sorted(os.listdir(exec_ds))))
            check("the second key has a store of its own, with the window just fetched; the first key's store was not consulted for it (the whole window was downloaded) and holds its 101 activities still",
                  len(json.load(open(os.path.join(exec_ds2, "store", "activities.json")))) == 60 and len(json.load(open(os.path.join(exec_ds, "store", "activities.json")))) == 101, None)
            # the first key again: its window is still in the cache, untouched by the second key's load
            r = fetch_json(page, "/intervals/store_api_key", {"api_key": "stack-key"})
            page.click("#routinesPill")
            page.wait_for_selector("#routinesModal", state="visible", timeout=10000)
            page.wait_for_function("() => (document.querySelector('#routinesModal .rt-right .title') || {}).textContent", timeout=15000)
            page.click("#routinesModal [data-act='run']")
            page.wait_for_function("() => !!document.querySelector('#routineRunModal input[data-load=\"start\"]')", timeout=30000)
            page.evaluate("([s, e]) => { const a = document.querySelector('#routineRunModal input[data-load=\"start\"]'), b = document.querySelector('#routineRunModal input[data-load=\"end\"]'); a.value = s; b.value = e; b.dispatchEvent(new Event('change', { bubbles: true })); }", [a_start.isoformat(), a_end.isoformat()])
            page.wait_for_function("() => { const c = document.querySelector('#routineRunModal .rt-cache'); return !!c && c.style.display !== 'none' && /hit|another key/.test(c.className + ' ' + c.textContent); }", timeout=15000)
            cl6 = page.evaluate("() => ({ text: document.querySelector('#routineRunModal .rt-cache').textContent, cls: document.querySelector('#routineRunModal .rt-cache').className })")
            check("back under the first key, the original window is a hit again - the second key's load did not overwrite it", "hit" in cl6["cls"] and "no download" in cl6["text"], cl6)
            page.click("#routineRunModal [data-act='cancel']")
            page.evaluate("RoutinesUI.closeManager()")
            page.wait_for_function("() => document.getElementById('routinesModal').style.display === 'none'", timeout=10000)

            # Endura: a routine made on one race, run on another picked in the dialog (the flat crit has no power channel, no climbs)
            page.click("#routinesPill")
            page.wait_for_selector("#routinesModal", state="visible", timeout=10000)
            page.wait_for_selector("#routinesModal .rt-origin", timeout=15000)
            page.click("#routinesModal .rt-origin")
            page.wait_for_function("() => document.getElementById('routinesModal').style.display === 'none' && !RoutinesUI.inRunView() && !document.getElementById('queryInput').disabled && typeof responses !== 'undefined' && responses.length >= 1", timeout=30000)
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
            # the Endura routine's verdict before its run (the manager holds Run while a routine is verifying)
            for _f in glob.glob(os.path.join(workdir, "webapp", "storage", USER, "routines", "*", "routine.json")):
                wait_verified(_f)
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
            # ---- the context (docs/CONTEXT_DESIGN.md, step 1): the words written beside the data as a file of the load ----
            page.evaluate("handleNewConversation()")
            page.wait_for_url("**/?new=true", timeout=60000)
            page.wait_for_selector("#queryInput", state="visible", timeout=60000)
            page.app_ready()
            page.wait_for_function("() => /Ready/.test(document.querySelector('#containerStatusText').textContent)", timeout=60000)
            r = fetch_json(page, "/intervals/store_api_key", {"api_key": "stack-key"})
            page.evaluate("showIntervalsModal()")
            page.wait_for_selector("#intervalsModal", state="visible", timeout=10000)
            set_window(page, a_start, a_end)
            cx_default = page.evaluate("() => document.getElementById('context-checkbox').checked")
            page.evaluate("() => ['summary-checkbox', 'wellness-checkbox', 'context-checkbox'].forEach(id => { const c = document.getElementById(id); c.checked = true; })")
            fits_before_c, msgs_before_c = calls_of(st, "fit-file"), calls_of(st, "/messages")
            page.click("#connectIntervals")
            page.wait_for_function("() => /Data loaded successfully/.test((document.getElementById('intervals-modal-message') || {}).textContent || '')", timeout=240000)
            msg = page.inner_text("#intervals-modal-message")
            chats_a = sum(1 for i in range(60) if apis_data.has_chat(a_start + timedelta(days=i)))
            check("the original window loaded again with the context: no FIT file fetched (all 60 activities from the store, the line says so); the chats fetched once, one call per activity with a chat",
                  calls_of(st, "fit-file") == fits_before_c and calls_of(st, "/messages") - msgs_before_c == chats_a and "all 60 activities from the store, nothing downloaded" in msg, (calls_of(st, "fit-file") - fits_before_c, calls_of(st, "/messages") - msgs_before_c, chats_a, msg[:200]))
            page.wait_for_function("() => [...document.querySelectorAll('.dataset-status-pill')].some(p => /W\\+S\\+C/.test(p.textContent))", timeout=60000)
            pills_c = page.evaluate("() => [...document.querySelectorAll('.dataset-status-pill')].map(p => p.textContent.trim())")
            ctx_pill = page.evaluate("() => { const p = document.getElementById('contextPill'); if (!p) return null; const c = p.querySelector('.dataset-pill-content'); return { label: c.querySelector('span').textContent, spinner: !!p.querySelector('.file-upload-spinner'), rows: [...p.querySelectorAll('.context-pill-menu .row')].map(r => r.textContent), title: c.title, pills: [...document.querySelectorAll('.dataset-status-pill')].length }; }")
            check("the context option is on by default in the dialog; the load with it carries [W+S+C+R] (the rider profile on by default too) and ONE Context pill - the days, a spinner and 'coding…' while the pass runs behind the load, its list naming the passages and the codes as coding - no separate pill per file; the dialog's line reports the passages by kind, names no failed call and says the coding runs in the background",
                  cx_default is True and rd_default is True and any("Intervals ICU (59 days [W+S+C+R]) loaded" in p for p in pills_c) and ctx_pill is not None and ctx_pill["label"] == "Context (59 days) \u00b7 coding\u2026" and ctx_pill["spinner"] is True
                  and len(ctx_pill["rows"]) == 2 and ctx_pill["rows"][0].startswith("Passagescontext_notes_") and ctx_pill["rows"][1] == "Codescoding\u2026" and ctx_pill["pills"] == 7
                  and any(p == "Auxiliary (Planned workouts (59 days))" for p in pills_c)      # the planned workouts file rides with the context (2026-10-15), a pill of its own
                  and not any(p.startswith("Auxiliary (Context") for p in pills_c)
                  and "Context: " in msg and "passages" in msg and "activity_message" in msg and "failed" not in msg and "coding in the background" in msg, (cx_default, pills_c, ctx_pill, msg))
            # the pass behind the load (2026-10-14): the page follows it on the one pill; when it ends the pill settles - the line, the codes row
            page.wait_for_function("() => { const p = document.getElementById('contextPill'); return !!p && !p.querySelector('.file-upload-spinner'); }", timeout=120000)
            pills_c = page.evaluate("() => [...document.querySelectorAll('.dataset-status-pill')].map(p => p.textContent.trim())")
            ctx_pill = page.evaluate("() => { const p = document.getElementById('contextPill'); const c = p.querySelector('.dataset-pill-content'); return { label: c.querySelector('span').textContent, rows: [...p.querySelectorAll('.context-pill-menu .row')].map(r => r.textContent), title: c.title, pills: [...document.querySelectorAll('.dataset-status-pill')].length }; }")
            check("when the pass ends the one pill reads plain with the pass's line as its tooltip - coded of total, the renderings, the proposal - and its list names the passages, the codes, the line and (the pass proposed a code) the row to the codebook screen; still five pills in the bar",
                  ctx_pill["label"] == "Context (59 days)" and re.search(r"^Context: \d+ of \d+ coded, \d+ tags? left as (?:labels|a label), \d+ rendered into English, 1 code proposed$", ctx_pill["title"]) is not None
                  and len(ctx_pill["rows"]) == 4 and ctx_pill["rows"][1].startswith("Codescontext_codes_") and re.search(r"^\d+ of \d+ coded", ctx_pill["rows"][2]) and ctx_pill["rows"][3] == "CodebookCodebook \u00b7 1 proposal awaits you" and ctx_pill["pills"] == 7, (pills_c, ctx_pill))
            page.evaluate("() => { const r = [...document.querySelectorAll('#contextPill .context-pill-menu .row')][0]; r.click(); }")
            page.wait_for_function("() => { const t = document.querySelector('#content-dataframe, .tab-content.active'); return !!t && /text_en/.test(t.textContent || ''); }", timeout=30000)
            check("the list's Passages row previews the context file in the Data tab, with the lang and text_en columns", True)
            ctx_path = os.path.join(exec_ds, f"context_notes_{tag_a}.csv")
            ctx = pd.read_csv(ctx_path, dtype=str, keep_default_na=False) if os.path.exists(ctx_path) else None
            kinds_c = dict(ctx["kind"].value_counts()) if ctx is not None else {}
            check("the executor wrote the context file beside the summary and wellness files, in the key's folder, with the columns of the design and the kinds the fake calendar holds: messages (subject and coach), the coach's private notes, descriptions, tags, ticks, wellness comments, the custom select, the plan's prose, notes, the sick span, the race",
                  ctx is not None and list(ctx.columns)[:5] == ["id", "kind", "date", "time", "end_date"]
                  and all(k in kinds_c for k in ("activity_message", "activity_private_note", "activity_note", "tag", "coach_tick", "wellness_note", "custom_field", "plan_note", "day_note", "status")), (ctx_path, kinds_c))
            # the planned workouts file beside it (2026-10-15): one row per WORKOUT entry of the window's calendar, the rides paired
            # to their activity with its compliance, the skipped sessions with none, the step lines and the structure as JSON
            plan_path = os.path.join(exec_ds, f"planned_workouts_{tag_a}.csv")
            plan_f = pd.read_csv(plan_path, dtype=str, keep_default_na=False) if os.path.exists(plan_path) else None
            ev_a = [e_ for e_ in apis_data.events(a_start.isoformat(), a_end.isoformat()) if e_["category"] == "WORKOUT"]
            check("the executor wrote the planned workouts file beside the context file: a row per planned workout, the rides paired (with the activity's compliance), the skipped sessions unpaired, the step lines the context leaves out, the plan's numbers and the structured workout as JSON",
                  plan_f is not None and len(plan_f) == len(ev_a) and (plan_f.activity_id != "").sum() == sum(1 for e_ in ev_a if e_["name"] == "Endurance") and (plan_f.activity_id == "").sum() == sum(1 for e_ in ev_a if e_["name"] == "Strength")
                  and set(plan_f[plan_f["name"] == "Endurance"].steps) == {"-2h 60%"} and set(plan_f[plan_f["name"] == "Endurance"].planned_duration_sec) == {"7200"} and all(json.loads(x_)["steps"][0]["duration"] == 7200 for x_ in plan_f[plan_f["name"] == "Endurance"].workout_doc)
                  and all(c_ != "" for c_ in plan_f[plan_f["name"] == "Endurance"].compliance) and (ctx is None or not ctx["text"].str.contains("-2h 60%").any()),
                  (plan_path, None if plan_f is None else (len(plan_f), len(ev_a), plan_f.head(2).to_dict("records"))))
            # the rider profile (2026-10-16, docs/RIDER_PROFILE_DESIGN.md): on by default, two files beside the others - the settings the data
            # is read against from the subject's record (a whitelist: nothing identifying), and the time in the account's custom zones per ride
            rider_path, zones_path = os.path.join(exec_ds, f"rider_profile_{tag_a}.csv"), os.path.join(exec_ds, f"custom_zone_times_{tag_a}.csv")
            prof_f = pd.read_csv(rider_path, dtype=str, keep_default_na=False) if os.path.exists(rider_path) else None
            zones_f = pd.read_csv(zones_path, dtype=str, keep_default_na=False) if os.path.exists(zones_path) else None
            rides_a = sum(1 for i in range(60) if apis_data.is_ride(a_start + timedelta(days=i)))
            prof_text = open(rider_path, encoding="utf-8").read() if os.path.exists(rider_path) else ""
            check("the rider profile loads by default beside the others: its pill without a window and the custom zones pill with it; the profile file's six sections from the fake record (the subject's measurements, the ride and run groups' thresholds, the zones with bounds, "
                  "the two custom zone sets, the two custom fields with their options, the two scales its form tracks) and nothing identifying in it; the zone times file one row per ride and custom zone, named from the definitions",
                  any(p == "Auxiliary (Rider profile)" for p in pills_c) and any(p == "Auxiliary (Custom zones (59 days))" for p in pills_c)
                  and prof_f is not None and list(dict.fromkeys(prof_f.section)) == ["subject", "sport", "zone", "custom_zone", "custom_field", "scale"]
                  and prof_f[prof_f.section == "scale"].key.tolist() == ["soreness", "sleepQuality"]
                  and prof_f[(prof_f.section == "sport") & (prof_f.key == "ftp")].value.tolist() == ["280"] and prof_f[(prof_f.section == "sport") & (prof_f.key == "threshold_pace")].sport_types.tolist() == ["Run"]
                  and prof_f[(prof_f.section == "zone") & (prof_f.key == "power_zone_6")].high.tolist() == [""] and prof_f[prof_f.section == "custom_zone"].key.tolist() == ["Breath:low", "Breath:high", "Cad:grind"]
                  and "options: 1 Recovery | 2 Endurance | 3 Tempo" in prof_f[(prof_f.section == "custom_field") & (prof_f.key == "Lbl")].note.iloc[0]
                  and all(s_ not in prof_text for s_ in ("subject@example.test", "not-a-real-key", "424242", "1998-05-20", "Subject"))
                  and zones_f is not None and len(zones_f) == 3 * rides_a and rides_a > 0 and set(zones_f.zone_name) == {"Low", "High", "Grind"},
                  (pills_c, None if prof_f is None else prof_f.head(8).to_dict("records"), None if zones_f is None else (len(zones_f), rides_a)))
            if ctx is not None:
                msgs = ctx[ctx["kind"] == "activity_message"]
                sick = ctx[(ctx["kind"] == "status") & ctx["text"].str.startswith("SICK")]
                race = ctx[(ctx["kind"] == "status") & ctx["text"].str.startswith("RACE_B")]
                priv = ctx[ctx["kind"] == "activity_private_note"]
                plan = ctx[ctx["kind"] == "plan_note"]
                check("the rows: messages by the subject and by the coach (told apart through the chat's members), dated and timed in the subject's zone; the private notes marked private; the sick span's inclusive end; the race's HTML stripped; the plan's step line gone and the plan joined to its activity",
                      set(msgs["author_role"]) == {"subject", "coach"} and all(len(t) == 5 for t in msgs["time"]) and (priv["private"].astype(str).str.lower() == "true").all()
                      and len(sick) >= 1 and all(e and (pd.Timestamp(e) - pd.Timestamp(d)).days == 2 for d, e in zip(sick["date"], sick["end_date"]))
                      and len(race) >= 1 and all("<" not in t and "Distance: 60km" in t for t in race["text"])
                      and len(plan) >= 1 and "60%" not in plan.iloc[0]["text"] and plan.iloc[0]["text"].startswith("Endurance: Keep it conversational") and plan.iloc[0]["activity_id"] != "",
                      (set(msgs["author_role"]), sick.to_dict("records"), race.to_dict("records"), plan.head(1).to_dict("records")))
                check("ids C.1..C.n in day order; a Danish and an English line both present",
                      list(ctx["id"]) == [f"C.{i}" for i in range(1, len(ctx) + 1)] and list(ctx["date"]) == sorted(ctx["date"])
                      and ctx["text"].str.contains("Sov dårligt|Benene var tunge|ondt i knæet").any() and ctx["text"].str.contains("Good legs today|Felt strong|Cut the session").any(), ctx[["id", "date", "kind"]].head(3).to_dict("records"))
                # ---- step 3: the coding pass at load - the renderings in the context file, the codes file beside it, the codebook ----
                da = ctx[ctx["text"].str.startswith("Benene var tunge")]
                en = ctx[ctx["text"].str.startswith("Good legs today")]
                tagrows = ctx[ctx["kind"] == "tag"]
                check("the coder wrote the language and an English rendering into every Danish passage and left the English ones their own (lang en, text_en empty); a tag is a label, never sent to the coder - no language, no rendering (patch 0197)",
                      len(da) and (da["lang"] == "da").all() and (da["text_en"] == "The legs were heavy today, rode shorter than planned.").all()
                      and len(en) and (en["lang"] == "en").all() and (en["text_en"] == "").all() and len(tagrows) and (tagrows["lang"] == "").all() and (tagrows["text_en"] == "").all(), (da[["lang", "text_en"]].head(2).to_dict("records"), en[["lang", "text_en"]].head(1).to_dict("records"), tagrows[["lang", "text_en"]].head(2).to_dict("records")))
                codes_path = os.path.join(exec_ds, f"context_codes_{tag_a}.csv")
                codes = pd.read_csv(codes_path, dtype=str, keep_default_na=False) if os.path.exists(codes_path) else None
                check("the codes file beside the context file: the design's columns, one row per code with the words it rests on verbatim in the original, the tone, codebook rows and the proposed code's rows marked, the coder and the codebook's version",
                      codes is not None and list(codes.columns) == ["id", "code", "tone", "quote", "status", "coder", "codebook_version"] and len(codes) > 20
                      and all(q in ctx.set_index("id").loc[i, "text"] for i, q in zip(codes["id"], codes["quote"]))
                      and set(codes["status"]) == {"codebook", "proposed"} and (codes[codes["code"] == "coach_flag"]["status"] == "proposed").all() and len(codes[codes["code"] == "coach_flag"]) >= 1
                      and set(codes["tone"]) <= {"positive", "negative", "neutral", "mixed"} and (codes["codebook_version"] == "1").all() and (codes["coder"] != "").all()
                      and {"fatigue", "sleep", "instruction", "deviation"} <= set(codes["code"]), (codes_path, None if codes is None else (list(codes.columns), len(codes), codes.head(3).to_dict("records"))))
                book_path = os.path.join(workdir, "webapp", "storage", USER, "context", "codebook.json")
                book = json.load(open(book_path)) if os.path.exists(book_path) else None
                check("the user's codebook was seeded on first use (36 codes, version 1) and holds the coder's proposal as proposed with its definition and an example passage; the last load's uses are recorded",
                      book is not None and book.get("version") == 1 and sum(1 for c in book["codes"] if c.get("status") == "seeded") == 36
                      and any(c["code"] == "coach_flag" and c.get("status") == "proposed" and c.get("definition") and c.get("examples") for c in book["codes"])
                      and sum(c.get("uses", 0) for c in book["codes"]) == len(codes), (book_path, None if book is None else [(c["code"], c.get("status"), c.get("uses")) for c in book["codes"] if c.get("status") == "proposed"]))
                store_path = os.path.join(workdir, "webapp", "storage", USER, "context", apis_data.SUBJECT["id"], "coded.json")
                store = json.load(open(store_path)) if os.path.exists(store_path) else None
                check("the coded passages are remembered per subject under storage/<user>/context/<athlete id>/coded.json (the id Intervals reports, not the key's mark) - one entry per answered passage with its rendering and codes (a tag and a copy are never sent) - so the next load of this subject codes only what is new",
                      store is not None and len(store.get("entries", {})) == len(ctx[(ctx["kind"] != "tag") & (ctx["copy_of"] == "")]) and any(e.get("text_en", "").startswith("The legs were heavy today") for e in store["entries"].values()), (store_path, None if store is None else len(store.get("entries", {}))))
            page.evaluate("() => { const m = document.getElementById('intervalsModal'); if (m) m.style.display = 'none'; }")
            # the analyst's DATA block: the context file's entry is columns and a count, the map follows, no passage in the prompt
            page.fill("#queryInput", mod.QUESTIONS[0])
            page.evaluate("setMode('deep')")
            page.click("#submitQuery")
            wait_run_end(page, 1)
            page.click('.sp-turn[data-turn="1"] .sp-prompt')
            page.wait_for_function("() => { const u = document.getElementById('userInstructions'); return u && /TASK: turn/.test(u.textContent); }", timeout=15000)
            prompt1 = page.inner_text("#userInstructions")
            page.evaluate("() => { const m = document.getElementById('agentInstructionsModal'); if (m) m.style.display = 'none'; }")
            check("DATA: the context file is listed with its columns and its row count and none of its rows; the map follows - the span, the passages by kind with the authors of the messages, the roles, the private entries, the months, the closing sentence",
                  f"Path: datasets/{USER}/{_kf('stack-key')}/context_notes_{tag_a}.csv" in prompt1 and "Rows: " in prompt1 and "(the rows are passages: read them with CTX, not from this head)" in prompt1
                  and "CONTEXT (the words written beside the data; in the kernel as CTX; files " in prompt1 and "activity_message" in prompt1 and "(subject " in prompt1 and "authors: subject " in prompt1
                  and "private entries " in prompt1 and "by month " in prompt1 and "A plan_note is dated the day it was planned for, not the day it was written." in prompt1 and "A passage is cited as" not in prompt1
                  and "Private: check the sleep log" not in prompt1 and "Bra jobba" not in prompt1, prompt1[prompt1.find("CONTEXT ("):prompt1.find("CONTEXT (") + 700] if "CONTEXT (" in prompt1 else prompt1[-800:])    # the chat's lines are in the context alone (a description also sits in the summary's head, 2026-10-15)
            check("DATA with the rider profile: its entry is the columns, the count with what a row is, and the Settings line from the file's rows - the measurements, the ride and run groups' thresholds, the rest counted; the zone times file described as any other",
                  re.search(rf"Path: datasets/{USER}/{_kf('stack-key')}/rider_profile_{tag_a}\.csv\s+Columns: section, sport_types, key, value, unit, low, high, note\s+Rows: \d+ \(one row per setting: section, key, value, unit, the bounds for a zone, a note; read the file with pandas\)", prompt1) is not None
                  and re.search(r"Settings: weight 71\.0 kg, height 1\.78 m, resting_hr 47 bpm, age \d+ years, sex M, timezone [\w/]+; Ride\|VirtualRide: ftp 280 W, indoor_ftp 270 W, lthr 168 bpm, max_hr 188 bpm; Run: lthr 160 bpm, max_hr 182 bpm, threshold_pace 3\.4 m/s; "
                            r"soreness, sleepQuality 1-4 \(the wellness file's subjective scales, by the platform's convention: a bigger number is worse, 1 the good end\); "
                            r"also in the file: 22 zone rows with their bounds, 3 custom zone rows in 2 sets \(Breath 'Breathing' on respiration; Cad 'Cadence' on cadence\), 2 custom field definitions - the codes other files' columns carry, with their options; "
                            r"the custom zone sets are the account's own, set by hand rather than the platform's defaults, and take precedence over the standard zones when reading intensity", prompt1) is not None
                  and "model_cp" not in prompt1 and re.search(rf"custom_zone_times_{tag_a}\.csv\s+Head:", prompt1) is not None, prompt1[prompt1.find("rider_profile_"):prompt1.find("rider_profile_") + 900] if "rider_profile_" in prompt1 else prompt1[-800:])
            check("DATA after the pass: the codes file listed as columns and count, the map's languages and its codes line - the counts per code, 'of 36 codes used', the uncoded, the proposal",
                  f"context_codes_{tag_a}.csv" in prompt1 and "languages en " in prompt1 and " da " in prompt1 and "codes (the model's reading, one row per code, with the words it rests on): " in prompt1
                  and re.search(r"\(\d+ of 36 codes used\)", prompt1) is not None and re.search(r"\d+ passages? carr(y|ies) none", prompt1) is not None and "proposed: coach_flag." in prompt1,
                  prompt1[prompt1.find("codes ("):prompt1.find("codes (") + 400] if "codes (" in prompt1 else prompt1[-600:])
            page.evaluate("activateTab('answer')")
            page.wait_for_timeout(300)
            answer_c = page.inner_text("#content-answer")
            check("the scripted analyst still finds the summary file by its dated name and answers (the context's entries did not confuse the DATA block)", "Training starts at" in answer_c, answer_c[:200])
            # ---- step 2: CTX in the kernel, READ CTX through the Reader, the passage cited as [C.n] in the answer with its chip ----
            page.fill("#queryInput", mod.CONTEXT_QUESTION)
            page.evaluate("setMode('deep')")
            page.click("#submitQuery")
            wait_text(page, "#chainPosition", "chain 2 of 2", 60000)
            wait_run_end(page, 2)
            rows_ctx = page.evaluate("() => [...document.querySelectorAll('.sp-row')].map(e => [e.className, e.textContent])")
            check("the pane: the cell row over CTX (the grep printed the span and the passages), then a READ CTX row with its passage count",
                  any(re.search(r"In\s*\[\d+\]", txt) and "CTX:" in txt for c, txt in rows_ctx) and any("read" in c.split() and "READ CTX what was written about the legs" in txt and re.search(r"\d passages?", txt) for c, txt in rows_ctx), rows_ctx)
            page.evaluate("activateTab('answer')")
            page.wait_for_timeout(300)
            answer_x = page.inner_text("#content-answer")
            check("the answer quotes a passage the Reader returned, with its day, and cites it as C.n (a chip now); the guard found the passage in the context (no CHECK line about passages)",
                  ("Good legs today" in answer_x or "legs" in answer_x.lower()) and re.search(r"\bC\.\d+\b", answer_x) is not None and "cited passage" not in answer_x and "not in the context loaded" not in answer_x, answer_x[:400])
            chips_c = page.evaluate("() => [...document.querySelectorAll('#content-answer .cite.ctx')].map(c => [c.textContent, c.getAttribute('data-unit'), c.getAttribute('title')])")
            chip_c = chips_c[0] if chips_c else None
            check("the answer's passages are chips of the context: the one quoted twice - named bare in the heading and cited as [C.n] - a Danish passage read in its rendering, "
                  "its hover the rendering's place, the English quote and the original beneath; and the passage beside it, named bare and never READ, with its day, kind, author and text from the file (resolved at report time)",
                  len(chips_c) == 3 and chips_c[0][0] == chips_c[1][0] and chips_c[0][2] == chips_c[1][2] and all(c[1] == c[0] and re.fullmatch(r"C\.\d+", c[0]) for c in chips_c)
                  and re.search(r"\d{4}-\d{2}-\d{2} · activity_message · subject \(rendered from da\) — \"The legs were heavy today", chip_c[2] or "") and "\noriginal: \"Benene var tunge" in (chip_c[2] or "")
                  and chips_c[2][0] != chips_c[0][0] and re.search(r"^\d{4}-\d{2}-\d{2} · \w+ · ", chips_c[2][2] or "") and "print(CTX.text" not in (chips_c[2][2] or ""), chips_c)
            page.click("#content-answer .cite.ctx")
            page.wait_for_function("() => { const s = document.querySelector('.tab-content.active .nb-step.nb-read'); return !!s && s.open; }", timeout=15000)
            step_c = page.evaluate("([u]) => { const s = [...document.querySelectorAll('.tab-content.active .nb-step.nb-read')].find(x => (' ' + (x.getAttribute('data-units') || '') + ' ').includes(' ' + u + ' ')); return s ? [s.open, s.querySelector('.nb-out-label').textContent, s.querySelector('.nb-out-peek').textContent, s.querySelector('.nb-out-body').textContent.slice(0, 160)] : null; }", [chip_c[0] if chip_c else ""])
            check("the click opens the Investigation tab at the READ that quoted the passage: the step 'Read the context' with the query as its peek, open, its digest in the fold",
                  step_c is not None and step_c[0] is True and step_c[1] == "Read the context" and step_c[2] == "CTX what was written about the legs" and step_c[3].startswith("PASSAGES"), step_c)
            page.evaluate("activateTab('answer')")
            page.wait_for_selector("#content-answer .simplified-summary-btn:not(.loading)", timeout=15000)
            page.click("#content-answer .simplified-summary-btn")
            page.wait_for_timeout(300)
            simp_c = page.evaluate("() => ({ text: document.querySelector('#content-answer .content-body').textContent, chips: [...document.querySelectorAll('#content-answer .content-body .cite.ctx')].map(e => [e.textContent, e.getAttribute('title')]) })")
            check("Simplified: the plain-language version keeps the quote and its citation as a chip of the context with the same hover",
                  "own words" in simp_c["text"] and len(simp_c["chips"]) == 1 and simp_c["chips"][0][0] == chip_c[0] and simp_c["chips"][0][1] == chip_c[2], simp_c)
            page.click("#content-answer .simplified-summary-btn")
            page.wait_for_timeout(300)

            # ---- step 6: the codebook screen (docs/CONTEXT_DESIGN.md §7 S3, 2026-10-16) - Intervals-only, so its ways in are the Intervals
            # dialog's Context card (its line: the book's size, the proposals waiting as a link) and the Context pill (the green count, the
            # row); the dialog shows the book with the coder's proposal first (its definition, its coder, the passages it came from) and the
            # codes by group with the last load's uses; Confirm makes the proposal a code of the book - version 2, the count and the pill's
            # row gone - and the next pass (run 1 below) uses it as the book's own ----
            pill_badge = page.evaluate("() => { const b = document.querySelector('#contextPill .pill-badge'); return b ? b.textContent : null; }")
            page.evaluate("showIntervalsModal()")
            page.wait_for_selector("#intervalsModal", state="visible", timeout=10000)
            page.wait_for_function("() => /codebook/.test((document.getElementById('contextCodebookLine') || {}).textContent || '')", timeout=15000)
            card_line = page.evaluate("() => document.getElementById('contextCodebookLine').textContent")
            page.click("#contextCodebookLink")
            page.wait_for_selector("#codebookModal .cb-card", timeout=15000)
            ctx_still_on = page.evaluate("() => document.getElementById('context-checkbox').checked")
            check("the ways in: the Context pill carries the count (1) since the pass proposed a code; the Intervals dialog's Context card says 'Coded against your codebook · 36 codes · 1 proposal waiting'; the link opens the screen without toggling the Context box",
                  pill_badge == "1" and card_line == "Coded against your codebook \u00b7 36 codes \u00b7 1 proposal waiting1" and ctx_still_on is True, (pill_badge, card_line, ctx_still_on))
            cbv = page.evaluate("""() => ({ sub: document.querySelector('#codebookModal .ui-dlg-h .sub').textContent, shown: document.getElementById('codebookModal').style.display,
                cards: [...document.querySelectorAll('#codebookModal .cb-card')].map(c => ({ code: c.getAttribute('data-code'), def: c.querySelector('.def').textContent, meta: c.querySelector('.cb-meta').textContent, ex: [...c.querySelectorAll('.cb-examples .ex')].map(e => e.textContent), acts: [...c.querySelectorAll('[data-act]')].map(b => b.getAttribute('data-act')) })),
                groups: [...document.querySelectorAll('#codebookModal .cb-group .h')].map(h => h.textContent), rows: document.querySelectorAll('#codebookModal .cb-table tbody tr').length,
                used: [...document.querySelectorAll('#codebookModal .cb-table tbody tr')].filter(r => !r.querySelector('td.num .ui-muted')).length, foot: document.querySelector('#codebookModal .ui-dlg-f .note').textContent, exp: document.querySelector('#codebookModal .ui-dlg-f a[download]').getAttribute('href') })""")
            check("the codebook screen: version 1, the 36 codes in the seed's six groups with the last load's uses on some; the coder's proposal first with its definition, its coder and day, the passage it came from (an id and the opening) and the four decisions; the foot's line and the Export link",
                  cbv["shown"] == "flex" and cbv["sub"] == "version 1 \u00b7 36 codes \u00b7 uses from the last load" and [c["code"] for c in cbv["cards"]] == ["coach_flag"] and "private note" in cbv["cards"][0]["def"]
                  and re.match(r"^proposed by \S+ on \S+ \S+ \u00b7 on \d+ passages? in the last load$", cbv["cards"][0]["meta"]) and len(cbv["cards"][0]["ex"]) >= 1 and re.match(r"^C\.\d+", cbv["cards"][0]["ex"][0]) and cbv["cards"][0]["acts"] == ["confirm", "rename", "merge", "decline"]
                  and cbv["groups"] == ["body and health 10 codes", "mind 7 codes", "the session 10 codes", "performance 2 codes", "the exchange 4 codes", "life 3 codes"] and cbv["rows"] == 36 and cbv["used"] >= 4
                  and cbv["foot"] == "A confirmed change applies from the next load; nothing already coded is re-coded." and cbv["exp"] == "/codebook/export", cbv)
            page.click("#codebookModal .cb-card[data-code='coach_flag'] [data-act='rename']")
            page.fill("#codebookModal .cb-card[data-code='coach_flag'] input[data-field='rename']", "fatigue")
            page.click("#codebookModal .cb-card[data-code='coach_flag'] [data-act='rename-go']")
            page.wait_for_selector("#codebookModal .cb-card .cb-error", timeout=15000)
            cb_err = page.evaluate("() => document.querySelector('#codebookModal .cb-card .cb-error').textContent")
            check("a rename onto a name the book has is refused in the card with the reason; nothing changed", cb_err == "the book already has a code named fatigue" and json.load(open(os.path.join(workdir, "webapp", "storage", USER, "context", "codebook.json")))["version"] == 1, cb_err)
            page.click("#codebookModal .cb-card[data-code='coach_flag'] [data-act='confirm']")
            page.wait_for_function("() => document.querySelectorAll('#codebookModal .cb-card').length === 0 && /^version 2/.test(document.querySelector('#codebookModal .ui-dlg-h .sub').textContent)", timeout=15000)
            page.wait_for_timeout(500)
            cbv2 = page.evaluate("""() => ({ sub: document.querySelector('#codebookModal .ui-dlg-h .sub').textContent, none: (document.querySelector('#codebookModal .cb-proposals .h') || {}).textContent,
                groups: [...document.querySelectorAll('#codebookModal .cb-group .h')].map(h => h.textContent), confirmed: document.querySelectorAll('#codebookModal .cb-group tbody tr[data-code="coach_flag"] .cb-status.confirmed').length,
                line: document.getElementById('contextCodebookLine').textContent, badge: (() => { const b = document.querySelector('#contextPill .pill-badge'); return b ? b.textContent : null; })(),
                pillrow: (() => { const r = [...document.querySelectorAll('#contextPill .context-pill-menu .row')].find(x => x.className.includes('codebook')); return r ? r.textContent : null; })() })""")
            book2 = json.load(open(os.path.join(workdir, "webapp", "storage", USER, "context", "codebook.json")))
            check("Confirm: the proposal is a confirmed code of the book - version 2, 37 codes, a 'confirmed' group last with it; no proposal waiting, the card's line now 'open the codebook' with 37 codes, the pill's count and row gone; the file says the same",
                  cbv2["sub"] == "version 2 \u00b7 37 codes \u00b7 uses from the last load" and cbv2["none"] == "Proposals none waiting" and cbv2["groups"][-1] == "confirmed 1 code" and cbv2["confirmed"] == 1 and cbv2["line"] == "Coded against your codebook \u00b7 37 codes \u00b7 open the codebook" and cbv2["badge"] is None and cbv2["pillrow"] is None
                  and book2["version"] == 2 and any(c["code"] == "coach_flag" and c["status"] == "confirmed" and c["group"] == "confirmed" for c in book2["codes"]), (cbv2, book2["version"]))
            exp_r = fetch_json(page, "/codebook/export")
            check("Export: the stored book as a file (version 2, 37 codes)", exp_r["status"] == 200 and isinstance(exp_r["json"], dict) and exp_r["json"].get("version") == 2 and len(exp_r["json"].get("codes") or []) == 37, (exp_r["status"], (exp_r["json"] or {}).get("version") if isinstance(exp_r["json"], dict) else exp_r["json"]))
            page.evaluate("() => { CodebookUI.close(); const m = document.getElementById('intervalsModal'); if (m) m.style.display = 'none'; }")

            # ---- step 5: routines carry context (docs/CONTEXT_DESIGN.md F3, 2026-10-14) - a chain that counts a code on the rider's
            # own passages, made a routine; run on the next window (the load with context, the pass behind it waited for, the count
            # compared like any result line) and on a window without words (a context file of its header, no codes: zeros, said so) ----
            def fatigue_expected(s_day, e_day):
                """What the fake calendar holds that the scripted coder reads as fatigue (its lexicon: 'Benene var tunge', 'Sov dårligt'):
                the subject's chat lines and the descriptions in prose, by day - the count the method should print on that window."""
                n = 0
                for d_ in apis_data.days_in(s_day.isoformat(), e_day.isoformat()):
                    lines = [m_["content"] for m_ in apis_data.messages(d_) if m_["athlete_id"] == apis_data.SUBJECT["id"]]
                    desc = apis_data.activity(d_).get("description") or ""
                    n += sum(1 for t_ in lines + [desc] if "benene var tunge" in t_.lower() or "sov dårligt" in t_.lower())
                return n
            # a thread of its own, so the method is the count chain alone (a follow-up in the thread above would stand on the
            # start-hours cells too - the thread's earlier chains on the same data are part of its computation); the same window,
            # loaded again with context - the store makes the pass a matter of seconds
            page.evaluate("handleNewConversation()")
            page.wait_for_url("**/?new=true", timeout=60000)
            page.wait_for_selector("#queryInput", state="visible", timeout=60000)
            page.app_ready()
            page.wait_for_function("() => /Ready/.test(document.querySelector('#containerStatusText').textContent)", timeout=60000)
            fetch_json(page, "/intervals/store_api_key", {"api_key": "stack-key"})
            page.evaluate("showIntervalsModal()")
            page.wait_for_selector("#intervalsModal", state="visible", timeout=10000)
            set_window(page, a_start, a_end)
            page.evaluate("() => ['summary-checkbox', 'wellness-checkbox', 'context-checkbox'].forEach(id => { const c = document.getElementById(id); c.checked = true; })")
            msgs_before_r = calls_of(st, "/messages")
            page.click("#connectIntervals")
            page.wait_for_function("() => /Data loaded successfully/.test((document.getElementById('intervals-modal-message') || {}).textContent || '')", timeout=240000)
            page.wait_for_function("() => { const p = document.getElementById('contextPill'); return !!p && !p.querySelector('.file-upload-spinner'); }", timeout=120000)
            reuse_line = page.evaluate("() => (document.querySelector('#contextPill .dataset-pill-content') || {}).getAttribute('title')")
            check("the same window loaded again in a new thread: the pass reused the store (the line says so) and settled in seconds", "already coded by an earlier load" in (reuse_line or ""), reuse_line)
            ctx_again = pd.read_csv(os.path.join(exec_ds, f"context_notes_{tag_a}.csv"), dtype=str, keep_default_na=False)
            check("the chats of the window came from the store this time (every activity is older than sixty days and unchanged): no messages call, and the context file has the messages as before",
                  calls_of(st, "/messages") == msgs_before_r and (ctx_again.kind == "activity_message").sum() > 0 and ctx is not None and (ctx_again.kind == "activity_message").sum() == (ctx.kind == "activity_message").sum(), (calls_of(st, "/messages") - msgs_before_r, (ctx_again.kind == "activity_message").sum()))
            # Everything again (the Download choice's second side): the whole window fetched again - every FIT file and every chat - and the
            # choice back on Only what's new after
            page.click("#intervalsDownload [data-refresh='1']")
            dl_state = page.evaluate("() => ({ box: document.getElementById('intervals-refresh').checked, on: document.querySelector('#intervalsDownload .on').textContent })")
            check("the Download choice: Everything again clicked - the hidden box on, the side lit", dl_state["box"] is True and dl_state["on"] == "Everything again", dl_state)
            fits_before_rf, msgs_before_rf = calls_of(st, "fit-file"), calls_of(st, "/messages")
            page.click("#connectIntervals")
            page.wait_for_function("() => /fetched again/.test((document.getElementById('intervals-modal-message') || {}).textContent || '')", timeout=240000)
            page.wait_for_function("() => { const p = document.getElementById('contextPill'); return !!p && !p.querySelector('.file-upload-spinner'); }", timeout=120000)
            msg_rf = page.inner_text("#intervals-modal-message")
            check("Everything again: every FIT file and every chat of the window fetched again, the line says 60 activities fetched again, and the choice is back on Only what's new for the next load",
                  calls_of(st, "fit-file") - fits_before_rf == 60 and calls_of(st, "/messages") - msgs_before_rf == chats_a and "60 activities fetched again" in msg_rf and page.evaluate("() => document.getElementById('intervals-refresh').checked") is False and page.evaluate("() => document.querySelector('#intervalsDownload .on').textContent") == "Only what\u2019s new",
                  (calls_of(st, "fit-file") - fits_before_rf, calls_of(st, "/messages") - msgs_before_rf, msg_rf[:160]))
            page.evaluate("() => { const m = document.getElementById('intervalsModal'); if (m) m.style.display = 'none'; }")
            # the Dataset cache panel lists the key's store
            page.evaluate("() => { DatasetManager.refresh(); const m = document.getElementById('datasetManagerModal'); if (m) m.style.display = 'block'; }")
            page.wait_for_function("() => (document.getElementById('storeList') || {}).textContent && !/Nothing kept|Loading/.test(document.getElementById('storeList').textContent)", timeout=15000)
            store_items = page.evaluate("() => [...document.querySelectorAll('#storeList .dataset-item')].map(e => e.textContent.replace(/\\s+/g, ' ').trim())")
            check("the Dataset cache panel lists the stores under Store: one per key, with the activities and chats held, the span and the size", len(store_items) == 2 and any("101 activities" in i and f"{a_start.isoformat()} → {today.isoformat()}" in i and "MB" in i for i in store_items) and any("60 activities" in i for i in store_items), store_items)
            page.evaluate("() => { const m = document.getElementById('datasetManagerModal'); if (m) m.style.display = 'none'; }")
            page.fill("#queryInput", mod.COUNT_QUESTION)
            page.evaluate("setMode('deep')")
            page.click("#submitQuery")
            wait_run_end(page, 1)
            page.evaluate("activateTab('answer')")
            page.wait_for_timeout(300)
            answer_n = page.inner_text("#content-answer")
            exp_a = fatigue_expected(a_start, a_end)
            m_n = re.search(r"(\d+) of the rider's (\d+) passages were read as fatigue", answer_n)
            check("the count chain: one cell over CTX.frame() and CTX.codes(), the report with the count the fake calendar predicts and the sentence that a code is the pass's reading",
                  m_n is not None and int(m_n.group(1)) == exp_a and int(m_n.group(2)) > exp_a and "coding pass's reading" in answer_n, (answer_n[:300], exp_a))
            page.hover("#rankButton")
            page.wait_for_selector("#saveMenu", state="visible", timeout=10000)
            page.click("#saveMenu .it[data-act='routine']")
            page.wait_for_selector("#routineMakeModal .rt-results, #routineMakeModal .rt-error", timeout=120000)     # no inputs table: nothing varies
            mk = page.evaluate("() => ({ data: (document.querySelector('#routineMakeModal .rt-data') || {}).textContent || '', inputs: document.querySelectorAll('#routineMakeModal .rt-inputs tbody tr').length, results: document.querySelectorAll('#routineMakeModal .rt-results .r').length, err: (document.querySelector('#routineMakeModal .rt-error') || {}).textContent || null })")
            check("Save as routine on the count chain: two result lines, nothing made an input (the code counted is the question's)", mk["err"] is None and mk["results"] == 2 and mk["inputs"] == 0, mk)
            page.fill("#routineMakeModal [data-field='purpose']", "fatigue in his own words, window by window")
            page.click("#routineMakeModal [data-act='create']")
            page.wait_for_function("() => document.querySelector('#routineMakeModal').style.display === 'none' || !!document.querySelector('#routineMakeModal .rt-error')", timeout=180000)
            err_n = page.evaluate("() => { const e = document.querySelector('#routineMakeModal .rt-error'); return e ? e.textContent : null; }")
            rdirs_n = [d_ for d_ in glob.glob(os.path.join(workdir, "webapp", "storage", USER, "routines", "*", "routine.json")) if "fatigue" in json.load(open(d_)).get("name", "").lower()]
            rj_n = wait_verified(rdirs_n[0]) if rdirs_n else {}
            rec_n = ((rj_n.get("versions") or [{}])[0].get("manifest") or {}).get("data") or {}
            check("Create: run zero reproduced the two lines on the original window; the record's auxiliary files are the seven of the load - summary, wellness, context, planned workouts, codes, the rider profile and the custom zone times (on by default, 2026-10-16) - under the key's folder, the load's kinds with context, plan and rider",
                  err_n is None and rdirs_n and (rj_n.get("versions") or [{}])[0].get("run_zero", {}).get("status") == "reproduced"
                  and sorted(aux_kind(p_) for p_ in rec_n.get("aux") or []) == ["codes", "context", "plan", "rider", "summary", "wellness", "zones"] and {"context", "plan", "rider"} <= set((rec_n.get("load") or {}).get("aux_kinds", [])), (err_n, rec_n.get("aux"), (rec_n.get("load") or {}).get("aux_kinds")))
            rid_n = rj_n.get("id")
            # run 1: the next window - the dialog's load asks for the context too; the pass behind the load is waited for; the count compared
            page.click("#routinesPill")
            page.wait_for_selector("#routinesModal", state="visible", timeout=10000)
            page.wait_for_function("() => (document.querySelector('#routinesModal .rt-right .title') || {}).textContent", timeout=15000)
            page.evaluate("([id]) => { const it = document.querySelector('#routinesModal .rt-side .it[data-id=\"' + id + '\"]'); if (it) it.click(); }", [rid_n])
            page.wait_for_function("([id]) => { const it = document.querySelector('#routinesModal .rt-side .it[data-id=\"' + id + '\"]'); return !!it && it.classList.contains('on'); }", arg=[rid_n], timeout=15000)
            page.click("#routinesModal [data-act='run']")
            page.wait_for_selector("#routineRunModal .rt-load", timeout=30000)
            page.wait_for_function("() => !!document.querySelector('#routineRunModal input[data-load=\"start\"]')", timeout=15000)
            help_n = page.evaluate("() => document.querySelector('#routineRunModal .rt-load .help').textContent")
            check("the run dialog of the context routine: the load asks for the summary, the wellness log and the context - the codes are the pass's, not asked for",
                  all(k_ in help_n for k_ in ("summary", "wellness", "context")) and "codes" not in help_n, help_n)
            b_start_n, b_end_n = page.evaluate("() => [document.querySelector('#routineRunModal input[data-load=\"start\"]').value, document.querySelector('#routineRunModal input[data-load=\"end\"]').value]")
            page.click("#routineRunModal [data-act='run']")
            seen_coding = page.wait_for_function("() => { const p = document.querySelector('#routineRunModal .rt-progress'); return !!p && /Coding the context|run 1 of/.test(p.textContent + ' ' + ((document.querySelector('#chainPosition') || {}).textContent || '')); }", timeout=300000)
            wait_text(page, "#chainPosition", "run 1 of 1", 300000)
            page.wait_for_timeout(800)
            rv_n = page.evaluate("""() => ({ rows: [...document.querySelectorAll('.sp-row.tool')].map(e => e.textContent), done: (document.querySelector('.sp-done') || {}).textContent || '', warn: !!document.querySelector('.sp-done.warn'),
                cmp: (document.getElementById('content-comparison') || {}).textContent || '', pills: [...document.querySelectorAll('.dataset-status-pill')].map(p => p.textContent.trim()),
                ctx: (() => { const p = document.getElementById('contextPill'); if (!p) return null; const c = p.querySelector('.dataset-pill-content'); return { label: c.querySelector('span').textContent, spinner: !!p.querySelector('.file-upload-spinner'), rows: [...p.querySelectorAll('.context-pill-menu .row')].map(r => r.textContent) }; })() })""")
            exp_b = fatigue_expected(date.fromisoformat(b_start_n), date.fromisoformat(b_end_n))
            _chk_n = next((r for r in rv_n["rows"] if "CHECK" in r), "")
            run1_n = json.load(open(os.path.join(os.path.dirname(rdirs_n[0]), "runs", "v1_1", "run.json")))
            res1_n = {r_.get("what"): rt_number(r_.get("estimate")) for r_ in run1_n.get("results") or []}
            check("run 1 on the next window: the LOAD row names the window with context; the pass ran behind the load and the run waited for it (the codes file bound, no 'codes absent'); "
                  "the CHECK row says the context file's rows against the original's; the count printed is the fake calendar's for that window; the Comparison tab sets it against run 0",
                  any("LOAD" in r and f"Intervals.icu {b_start_n} → {b_end_n}" in r for r in rv_n["rows"]) and "the context file:" in _chk_n and "rows where the original had" in _chk_n.split("the context file:")[1] and "the codes file:" in _chk_n
                  and "codes absent" not in _chk_n and "no passages in this window" not in _chk_n and run1_n["status"] in ("ran", "reproduced") and "codes" not in run1_n.get("aux_absent", [])
                  and {aux_kind(f_) for f_ in ((run1_n.get("shape") or {}).get("files") or {})} >= {"context", "codes"} and not run1_n.get("bindings")      # the method reads CTX: no literal path to rebind
                  and res1_n.get("of them read as fatigue by the coding pass") == exp_b and "against run 0" in rv_n["cmp"] and "fatigue" in rv_n["cmp"] and "Run 1 complete" in rv_n["done"] and not rv_n["warn"],
                  (rv_n["rows"], _chk_n, res1_n, exp_b, run1_n.get("aux_absent"), rv_n["done"][:200]))
            check("the Data tab after the run: the one Context pill for the run's window, settled (no spinner), its list with the passages and the codes", rv_n["ctx"] is not None and not rv_n["ctx"]["spinner"] and rv_n["ctx"]["label"].startswith("Context (") and any(r_.startswith("Codescontext_codes_") for r_ in rv_n["ctx"]["rows"]), rv_n["ctx"])
            # the confirmed code in the next pass (step 6): the window overlaps the original's tail, whose passages the store holds - those
            # are not re-coded and keep version 1 with coach_flag as it was coded (proposed); the days after it are coded now, under version
            # 2, and the coder's coach_flag (it still proposes it) is the book's own there - marked codebook, not proposed
            tag_b = f"{b_start_n.replace('-', '')}_to_{b_end_n.replace('-', '')}"
            codes_b_path = os.path.join(exec_ds, f"context_codes_{tag_b}.csv")
            codes_b = pd.read_csv(codes_b_path, dtype=str, keep_default_na=False) if os.path.exists(codes_b_path) else None
            ctx_b_path = os.path.join(exec_ds, f"context_notes_{tag_b}.csv")
            ctx_b = pd.read_csv(ctx_b_path, dtype=str, keep_default_na=False) if os.path.exists(ctx_b_path) else None
            cb_rows = codes_b.merge(ctx_b[["id", "date"]], on="id", how="left") if codes_b is not None and ctx_b is not None else None
            old_b = cb_rows[cb_rows["date"] <= a_end.isoformat()] if cb_rows is not None else None
            new_b = cb_rows[cb_rows["date"] > a_end.isoformat()] if cb_rows is not None else None
            check("after the confirmation the next pass uses the code as the book's own and re-codes nothing: in run 1's codes file the passages the store held (the original window's tail) keep version 1 and coach_flag as it was coded (proposed); "
                  "the days after it are coded under version 2 with coach_flag marked codebook; the pill shows no count and no codebook row",
                  cb_rows is not None and len(old_b) > 0 and len(new_b) > 0 and (old_b["codebook_version"] == "1").all() and (new_b["codebook_version"] == "2").all()
                  and len(new_b[new_b["code"] == "coach_flag"]) >= 1 and (new_b[new_b["code"] == "coach_flag"]["status"] == "codebook").all() and not (new_b["status"] == "proposed").any()
                  and (old_b[old_b["code"] == "coach_flag"]["status"] == "proposed").all()
                  and page.evaluate("() => !document.querySelector('#contextPill .pill-badge')") is True and not any(r_.startswith("Codebook") for r_ in rv_n["ctx"]["rows"]),
                  (codes_b_path, None if cb_rows is None else (len(old_b), set(old_b["codebook_version"]), len(new_b), set(new_b["codebook_version"]), cb_rows[cb_rows["code"] == "coach_flag"][["id", "date", "status", "codebook_version"]].to_dict("records"))))
            # run 2: a window without words (the fake's silent fortnight): the context file is its header, no codes file, the method
            # prints zeros, the CHECK row says 'no passages in this window' and does not call the codes absent
            c_start, c_end = today - timedelta(days=33), today - timedelta(days=22)
            assert all(apis_data.is_silent(d_) for d_ in apis_data.days_in(c_start.isoformat(), c_end.isoformat())), "the silent window is not silent"
            page.click("#routinesPill")
            page.wait_for_selector("#routinesModal", state="visible", timeout=10000)
            page.wait_for_function("() => (document.querySelector('#routinesModal .rt-right .title') || {}).textContent", timeout=15000)
            page.evaluate("([id]) => { const it = document.querySelector('#routinesModal .rt-side .it[data-id=\"' + id + '\"]'); if (it) it.click(); }", [rid_n])
            page.wait_for_function("([id]) => { const it = document.querySelector('#routinesModal .rt-side .it[data-id=\"' + id + '\"]'); return !!it && it.classList.contains('on'); }", arg=[rid_n], timeout=15000)
            page.click("#routinesModal [data-act='run']")
            page.wait_for_selector("#routineRunModal .rt-load", timeout=30000)
            page.wait_for_function("() => !!document.querySelector('#routineRunModal input[data-load=\"start\"]')", timeout=15000)
            page.fill("#routineRunModal input[data-load='start']", c_start.isoformat())
            page.fill("#routineRunModal input[data-load='end']", c_end.isoformat())
            page.wait_for_timeout(700)
            page.click("#routineRunModal [data-act='run']")
            wait_text(page, "#chainPosition", "run 2 of 2", 300000)
            page.wait_for_timeout(800)
            rv_s = page.evaluate("""() => ({ rows: [...document.querySelectorAll('.sp-row.tool')].map(e => e.textContent), done: (document.querySelector('.sp-done') || {}).textContent || '', warn: !!document.querySelector('.sp-done.warn'),
                cmp: (document.getElementById('content-comparison') || {}).textContent || '', ctx: (() => { const p = document.getElementById('contextPill'); if (!p) return null; const c = p.querySelector('.dataset-pill-content'); return { label: c.querySelector('span').textContent, title: c.getAttribute('title'), rows: [...p.querySelectorAll('.context-pill-menu .row')].map(r => r.textContent) }; })() })""")
            _chk_s = next((r for r in rv_s["rows"] if "CHECK" in r), "")
            run2_n = json.load(open(os.path.join(os.path.dirname(rdirs_n[0]), "runs", "v1_2", "run.json")))
            res2_n = {r_.get("what"): rt_number(r_.get("estimate")) for r_ in run2_n.get("results") or []}
            tag_c = f"{c_start.strftime('%Y%m%d')}_to_{c_end.strftime('%Y%m%d')}"
            ctx_c = os.path.join(exec_ds, f"context_notes_{tag_c}.csv")
            check("run 2 on a window without words: the loader wrote the context file as its header alone and no codes file; the CHECK row says 'no passages in this window' and does not call the codes absent (the wellness file is); "
                  "the method printed its zeros; the Comparison tab sets them against run 1; the Context pill shows the window with no coding line",
                  os.path.exists(ctx_c) and len(open(ctx_c, encoding="utf-8").read().strip().splitlines()) == 1 and not os.path.exists(os.path.join(exec_ds, f"context_codes_{tag_c}.csv"))
                  and "no passages in this window (the context and codes tables are empty)" in _chk_s and "codes absent" not in _chk_s and "wellness absent in this data" in _chk_s
                  and res2_n.get("passages the subject wrote in the window") == 0 and res2_n.get("of them read as fatigue by the coding pass") == 0 and run2_n["status"] in ("ran", "reproduced")
                  and "against run 1" in rv_s["cmp"] and "Run 2 complete" in rv_s["done"] and not rv_s["warn"] and rv_s["ctx"] is not None and rv_s["ctx"]["label"].startswith("Context (")
                  and not any(r_.startswith("Codes") for r_ in rv_s["ctx"]["rows"]),
                  (_chk_s, res2_n, rv_s["done"][:200], rv_s["ctx"], os.path.exists(ctx_c)))
            # run 3: a window inside the original load, which the executor's cache still holds (the refresh's frame) with its four
            # files - the run takes the cached frame and files through the cache routes and cuts them (2026-10-15: the cache route
            # refused the fourth file, 'Maximum 3 auxiliary datasets allowed', so a context routine could never run from the cache;
            # Palo's was five files). Run 1's own load has no wellness file (the fake stops logging sixty days ago), so it is no hit.
            d_start, d_end = today - timedelta(days=80), today - timedelta(days=70)
            page.click("#routinesPill")
            page.wait_for_selector("#routinesModal", state="visible", timeout=10000)
            page.wait_for_function("() => (document.querySelector('#routinesModal .rt-right .title') || {}).textContent", timeout=15000)
            page.evaluate("([id]) => { const it = document.querySelector('#routinesModal .rt-side .it[data-id=\"' + id + '\"]'); if (it) it.click(); }", [rid_n])
            page.wait_for_function("([id]) => { const it = document.querySelector('#routinesModal .rt-side .it[data-id=\"' + id + '\"]'); return !!it && it.classList.contains('on'); }", arg=[rid_n], timeout=15000)
            page.click("#routinesModal [data-act='run']")
            page.wait_for_selector("#routineRunModal .rt-load", timeout=30000)
            page.wait_for_function("() => !!document.querySelector('#routineRunModal input[data-load=\"start\"]')", timeout=15000)
            page.fill("#routineRunModal input[data-load='start']", d_start.isoformat())
            page.fill("#routineRunModal input[data-load='end']", d_end.isoformat())
            page.wait_for_function("([s]) => { const c = document.querySelector('#routineRunModal .rt-cache'); return !!c && c.style.display !== 'none' && c.textContent.includes('(' + s + ' '); }", arg=[d_start.isoformat()], timeout=15000)   # the typed window's answer, not the default's
            cl_d = page.evaluate("() => ({ text: document.querySelector('#routineRunModal .rt-cache').textContent, cls: document.querySelector('#routineRunModal .rt-cache').className })")
            check("the context routine on a window inside the original load: the line says it is inside the cached load, with summary, wellness, context, codes - it will be cut, no download",
                  "hit" in cl_d["cls"] and f"inside the cached load {a_start.isoformat()} → {a_end.isoformat()}" in cl_d["text"] and all(k_ in cl_d["text"] for k_ in ("summary", "wellness", "context", "codes")) and "no download" in cl_d["text"], cl_d)
            fits_before_d = calls_of(st, "fit-file")
            page.click("#routineRunModal [data-act='run']")
            page.wait_for_function("() => /run 3 of 3/.test((document.querySelector('#chainPosition') || {}).textContent || '') || /Maximum|could not be loaded|failed/.test(((document.querySelector('#routineRunModal .rt-progress') || {}).textContent) || '')", timeout=300000)
            page.wait_for_timeout(800)
            prog_d = page.evaluate("() => ((document.querySelector('#routineRunModal .rt-progress') || {}).textContent) || ''")
            rv_d = page.evaluate("""() => ({ rows: [...document.querySelectorAll('.sp-row.tool')].map(e => e.textContent), done: (document.querySelector('.sp-done') || {}).textContent || '', warn: !!document.querySelector('.sp-done.warn'),
                position: (document.querySelector('#chainPosition') || {}).textContent || '' })""")
            run3_path = os.path.join(os.path.dirname(rdirs_n[0]), "runs", "v1_3", "run.json")
            run3_n = json.load(open(run3_path)) if os.path.exists(run3_path) else {}
            _chk_d = next((r for r in rv_d["rows"] if "CHECK" in r), "")
            check("run 3 ran from the cache with all seven files - none refused by the auxiliary limit (derived from the loaders' registry since 0181): no download, the LOAD row 'cut from the cache', the CHECK row - a sentence per file, whole on the page (the 600-character cut had lost its tail) - ending 'cut to the window from the cached load', the context, codes, plan, rider profile and zone times files among the seven bound, the run complete",
                  "run 3 of 3" in rv_d["position"] and "Maximum" not in prog_d and calls_of(st, "fit-file") == fits_before_d
                  and any("LOAD" in r and "cut from the cache" in r for r in rv_d["rows"]) and f"cut to {d_start.isoformat()} → {d_end.isoformat()} from the cached load" in _chk_d
                  and run3_n.get("status") in ("ran", "reproduced") and sorted(aux_kind(p_) for p_ in (run3_n.get("data") or {}).get("aux") or []) == ["codes", "context", "plan", "rider", "summary", "wellness", "zones"]
                  and not run3_n.get("aux_absent") and "Run 3 complete" in rv_d["done"] and not rv_d["warn"],
                  (prog_d[:200], rv_d["position"], _chk_d[-300:], calls_of(st, "fit-file") - fits_before_d, rv_d["warn"], sorted(aux_kind(p_) for p_ in (run3_n.get("data") or {}).get("aux") or []), run3_n.get("status"), run3_n.get("aux_absent"), rv_d["done"][:160]))
            # the words of a cut run are the window's (2026-10-16): the count the method printed is the fake calendar's for the
            # window, not the cached load's (CTX used to read the files loaded now - the whole load's context)
            res3_n = {r_.get("what"): rt_number(r_.get("estimate")) for r_ in run3_n.get("results") or []}
            check("the cut run's words are the window's: the fatigue count is the fake calendar's for the window, smaller than the cached load's", res3_n.get("of them read as fatigue by the coding pass") == fatigue_expected(d_start, d_end) and fatigue_expected(d_start, d_end) < exp_a, (res3_n, fatigue_expected(d_start, d_end), exp_a))
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
