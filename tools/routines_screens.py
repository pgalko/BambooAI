"""The routines screens in the REAL page (web_app/templates/index.html with every stylesheet and script, the backend
faked, the page filled as tools/render_gallery.py fills it), one PNG per screen, dark and light with --light:

  python3 tools/routines_screens.py --out /tmp/routines_screens [--light]

Screens: the Save pill's menu on a finished chain; the Save-as-routine dialog with a proposal, with the next-version
choice, and refused; the Routines manager with one routine and empty; the favourites manager with a card's Routine
button lit; the run dialog on a file, refusing, on an Intervals window, and on Week with the weeks to fill (§14.2);
the manager while a fill runs (§14.3), the manager redesigned 2026-11-08 (the facts, the runs as a table). The two streaming routes are answered with the lines the server would send, so
routines.js runs its own path - the dialog is driven by the script, not drawn by hand. Exits 1 when a page error or an
unexpected state shows."""
import argparse, json, os, sys, importlib.util
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
spec = importlib.util.spec_from_file_location('rp', os.path.join(HERE, 'render_page.py')); rp = importlib.util.module_from_spec(spec); spec.loader.exec_module(rp)
FILL = open(os.path.join(HERE, 'fixtures', 'fill_page.js')).read()

PROPOSAL = {"proposal_id": "p1", "thread_id": "1791460000", "chain_id": "1791460001", "name": "Altitude pace correction, within athlete", "purpose": "",
            "question": "How much slower is the same runner at 2,100-3,100 m than at sea level, holding effort and surface fixed?",
            "summary": "The within-athlete, effort-adjusted gap is +0.11 log-speed units.", "source": "file", "data_state": "same",
            "data": {"name": "EEDR_sessions_laps_enriched.csv", "rows": 22705, "columns": [{"name": f"c{i}"} for i in range(49)]},
            "inputs": [{"key": "hard_effort_hr", "label": "Hard-effort threshold (lap HR)", "type": "number", "default": 155, "origin": "the exploration split laps at 155"},
                       {"key": "hr_bands", "label": "HR bands for the matched comparison", "type": "numbers", "default": [130, 145, 155, 165, 175], "origin": "the exploration's bands"},
                       {"key": "exclude", "label": "Athletes to exclude (sensitivity line)", "type": "choice", "multiple": True, "default": ["athlete07", "athlete09"], "origin": "the exploration dropped two athletes with few abroad laps", "column": "athlete_id"},
                       {"key": "span", "label": "Dates quoted in the result labels", "type": "date_window", "default": ["2026-03-02", "2026-06-28"], "derived": "span", "origin": "the first and last lap dates, typed into the labels"}],
            "kept": ["the 1-km lap window", "the speed plausibility bounds", "the bootstrap size and seed"],
            # the promoter's pick (§15): three lines compared under table-head names; the FE-only form and the surface variant set aside, the typed line too
            "results": [{"cell": 2, "index": 0, "label": "log speed, abroad (sea level) vs Ethiopia altitude laps, within-athlete, HR/temp/ascent adjusted, 1-km laps", "typed": False, "dropped": False, "name": "Abroad vs altitude, adjusted"},
                        {"cell": 2, "index": 1, "label": "log speed, abroad vs Ethiopia, athlete FE only, 1-km laps", "typed": False, "dropped": True},
                        {"cell": 3, "index": 0, "label": "log speed per +1000 m venue altitude within Ethiopia, FE", "typed": False, "dropped": False, "name": "Per +1000 m of altitude"},
                        {"cell": 3, "index": 1, "label": "log speed per +1000 m venue altitude within Ethiopia, FE+surface", "typed": False, "dropped": True},
                        {"cell": 4, "index": 0, "label": "correction of cell 3's wording", "typed": True, "dropped": True},
                        {"cell": 5, "index": 0, "label": "log speed, abroad vs Ethiopian road laps at same HR band, athlete FE, athlete-cluster bootstrap", "typed": False, "dropped": False, "name": "Abroad vs road, same HR band"}],
            "figures": {"count": 1, "cells": [5]}, "cells": 5, "cost": 0.04, "notes": [], "routine_id": None, "routine_name": None, "next_version": None}
ROUTINE = {"id": "r1", "name": "Altitude pace correction, within athlete", "created": 1791460000, "updated": 1791460000, "purpose": "the sea-level gap, holding effort and surface fixed",
           "question": PROPOSAL["question"], "summary": PROPOSAL["summary"], "origin": {"thread_id": "1791460000", "chain_id": "1791460001"}, "source": "file", "current_version": 1, "runs": [],
           "origin_available": True, "summary_card": {"data": PROPOSAL["data"]},
           "versions": [{"number": 1, "created": 1791460000, "promoted_from": {"thread_id": "1791460000", "chain_id": "1791460001"}, "change_note": "first version", "script_chars": 9120, "written_chars": 14800,
                         "manifest": {"data": PROPOSAL["data"], "parameters": PROPOSAL["inputs"], "results": [dict(r) for r in PROPOSAL["results"]], "figures": PROPOSAL["figures"]},
                         "run_zero": {"status": "reproduced", "line": "reproduced: 5 result line(s) identical", "verified": True},
                         "condensed": {"status": "condensed", "line": "condensed: 9 cells → 4, 11 prints dropped, 48 s → 4.6 s", "cells": [9, 4], "dropped": {"cells": [1, 2, 4, 6, 8], "prints": 11}, "elapsed": [48.2, 4.6]}}]}     # the pass (§19)
# step 2: three runs of v1 with their lines (the manifest's five kept lines, by position; the dropped typed one still printed)
def _lines(vals):
    out = [{"estimate": f"{v:+.3f}", "low": f"{v - w:+.3f}", "high": f"{v + w:+.3f}"} for v, w in vals]
    return out[:4] + [{"estimate": "+0.000", "low": None, "high": None}] + out[4:]      # the typed line sits fifth, as in the manifest
RUN_LINES = {0: _lines([(0.11, 0.02), (0.31, 0.02), (-0.13, 0.03), (-0.14, 0.05), (0.065, 0.015)]), 1: _lines([(0.11, 0.02), (0.30, 0.02), (-0.14, 0.03), (-0.18, 0.05), (0.072, 0.015)]),
             2: _lines([(0.10, 0.02), (0.32, 0.02), (-0.12, 0.03), (-0.15, 0.05), (0.057, 0.015)]), 3: _lines([(0.16, 0.02), (0.33, 0.02), (-0.089, 0.03), (0.13, 0.05), (0.12, 0.015)])}
ROUTINE["versions"][0]["run_zero"].update({"created": 1791460000, "results": RUN_LINES[0], "elapsed": 4.6, "data": PROPOSAL["data"], "inputs": {"hard_effort_hr": 155, "hr_bands": [130, 145, 155, 165, 175], "exclude": ["athlete07", "athlete09"]}})
ROUTINE["versions"][0]["manifest"]["results"] = [dict(r, estimate=l["estimate"], low=l["low"], high=l["high"]) for r, l in zip(ROUTINE["versions"][0]["manifest"]["results"], RUN_LINES[0])]
def _cmp(now, before):
    rows = []
    for m, a, b in zip(ROUTINE["versions"][0]["manifest"]["results"], now, before):
        if m["dropped"]: continue
        ea, eb = float(a["estimate"]), float(b["estimate"]); ia, ib = (float(a["low"]), float(a["high"])), (float(b["low"]), float(b["high"]))
        overlap = not (ia[0] > ib[1] or ia[1] < ib[0])
        rows.append({"cell": m["cell"], "index": m["index"], "label": m["label"], "name": m.get("name", ""), "unit": "log units", "direction": "", "typed": False, "now": a, "before": b, "change": round(ea - eb, 4), "overlap": overlap, "mark": "same" if overlap else ("up" if ea > eb else "down")})
    moved = sum(1 for r in rows if r["mark"] in ("up", "down"))
    return {"rows": rows, "moved": moved, "within": len(rows) - moved, "changed": 0, "missing": 0, "compared": len(rows), "line": f"{moved} of {len(rows)} moved beyond their intervals"}
RUNS = []
for n, (when, name, against) in enumerate([(1791780000, "EEDR_laps_2026-03.csv", 0), (1792130000, "EEDR_laps_athletes15-28.csv", 1), (1792390000, "EEDR_laps_2026-07.csv", 2)], 1):
    c = _cmp(RUN_LINES[n], RUN_LINES[against])
    RUNS.append({"number": n, "version": 1, "created": when, "finished": when + 31, "elapsed": 31.0, "status": "ran", "line": "ran: 6 result lines", "inputs": {"hard_effort_hr": 155, "hr_bands": [130, 145, 155, 165, 175], "exclude": ["athlete07", "athlete09"]} if n != 2 else {"hard_effort_hr": 155, "hr_bands": [130, 145, 155, 165, 175], "exclude": []},
                 "results": RUN_LINES[n], "figures": 1, "against": against, "cells": 5, "data": {"df_id": f"df_{n}", "name": name, "source": "csv", "rows": 7500 + 900 * n, "columns": 49, "date_range": None, "aux": [], "extra": {}},
                 "comparison": {k: c[k] for k in ("moved", "within", "changed", "missing", "compared", "line")}, "full_comparison": c})
ROUTINE["runs"] = [{k: v for k, v in r.items() if k != "full_comparison"} for r in RUNS]
RUN_VIEW = {"run": dict({k: v for k, v in RUNS[2].items() if k != "full_comparison"}, comparison=RUNS[2]["full_comparison"], narrative="", data=dict(RUNS[2]["data"], columns=PROPOSAL["data"]["columns"])),
            "stdout": "RESULT: log speed, abroad (sea level) vs Ethiopia altitude laps: +0.160 (95% CI +0.140 to +0.180) log units\nRESULT: ...\n", "figures": [], "routine": None, "numbers": [0, 1, 2, 3], "name": ROUTINE["name"], "manifest_results": []}
PRECHECK_OK = {"loaded": True, "ok": True, "line": "fits the routine (49 of 49 columns); the chosen values are in the data", "fit": {"fits": True, "missing": [], "expected": 49}, "values_missing": [], "problems": [],
               "aux": {"absent": [], "bound": {}, "line": ""}, "plan": {"source": "file", "name": "EEDR_laps_2026-07.csv", "aux": [], "aux_kinds": []},
               "data": {"df_id": "df_x", "name": "EEDR_laps_2026-07.csv", "source": "csv", "rows": 10200, "columns": 49, "date_range": None}}
PRECHECK_BAD = {"loaded": True, "ok": False, "line": "none of the routine's 49 columns is in this data - nothing to run on", "fit": {"fits": False, "missing": ["venue_altitude_m", "surface_category"], "expected": 49},
                "values_missing": [], "problems": [], "aux": {"absent": [], "bound": {}, "line": ""}, "plan": {"source": "file", "name": "EEDR_laps_2026-07.csv", "aux": [], "aux_kinds": []},
                "data": {"df_id": "df_y", "name": "wellness_export.csv", "source": "csv", "rows": 180, "columns": 12, "date_range": None}}
# an Intervals.icu routine (2026-10-10): the dialog loads the next window itself - the original's length ending today, the auxiliaries as the original
PRECHECK_INTERVALS = {"loaded": True, "ok": True, "line": "2 of 49 columns empty in this data: power, temperature; wellness absent in this data - the method will see an empty table there", "fit": {"fits": True, "missing": ["power", "temperature"], "expected": 49},
                      "values_missing": [], "problems": [], "aux": {"absent": ["wellness"], "bound": {"summary": "activity_summary_20260812_to_20261010.csv"}, "line": "wellness absent in this data - the method will see an empty table there"},
                      "plan": {"source": "intervals", "name": "", "aux_kinds": ["summary", "wellness"], "metrics": [], "window_days": 59, "start": "2026-07-02", "end": "2026-08-30", "date_range": "2026-07-02 to 2026-08-30", "subject": {"id": "i1", "name": "First Athlete"}},
                      "data": {"df_id": "df_z", "name": "", "source": "intervals", "rows": 10200, "columns": 47, "date_range": "2026-08-12 to 2026-10-10"}}
# the Summary by interval (2026-11-06, docs/ROUTINES_DESIGN.md §14.6): an Intervals routine run weekly on one athlete - ten of the last
# eleven complete weeks (one never run), the values drifting - and the run view of the latest week with its Trend tab
def _weeks(n, today=None):
    from datetime import date, timedelta
    t = today or date.today()
    end = t - timedelta(days=t.weekday() + 1)                        # the Sunday before this week's Monday
    return [((end - timedelta(days=7 * k + 6)).isoformat(), (end - timedelta(days=7 * k)).isoformat()) for k in range(n)][::-1]
ROUTINE_W = json.loads(json.dumps(ROUTINE))
ROUTINE_W.update({"source": "intervals", "summary_card": {"data": dict(PROPOSAL["data"], source="intervals")}})
ROUTINE_W["versions"][0]["manifest"]["data"] = dict(PROPOSAL["data"], source="intervals", load={"source": "intervals", "subject": {"source": "intervals", "id": "i1", "name": "First Athlete"}, "start_date": "2026-07-02", "end_date": "2026-08-30"})
_WEEKS = _weeks(11)
_W_RUNS = []
for k, (ws, we) in enumerate(_WEEKS):
    if k == 4: continue                                               # the fifth week never run: a gap in the thumbnails and the chart
    vals = _lines([(0.11 + 0.004 * k, 0.02), (0.31 - 0.003 * k, 0.02), (-0.13 + 0.002 * k * (-1) ** k, 0.03), (-0.14 + 0.01 * k, 0.05), (0.065 + 0.003 * k, 0.015)])
    before = _W_RUNS[-1] if _W_RUNS else None
    c = _cmp(vals, before["results"]) if before else {"rows": [], "moved": 0, "within": 0, "changed": 0, "missing": 0, "compared": 0, "line": "nothing to compare with: no earlier week on record for this subject"}
    _W_RUNS.append({"number": len(_W_RUNS) + 1, "version": 1, "created": 1792400000 + 3600 * k, "finished": 1792400000 + 3600 * k + 31, "elapsed": 31.0, "status": "ran", "line": "ran: 6 result lines", "interval": "week",
                    "inputs": {"hard_effort_hr": 155, "hr_bands": [130, 145, 155, 165, 175], "exclude": ["athlete07", "athlete09"]}, "results": vals, "figures": 1, "against": before["number"] if before else None, "cells": 5,
                    "data": {"df_id": f"df_w{k}", "name": "", "source": "intervals", "rows": 2000 + 90 * k, "columns": 49, "date_range": f"{ws} to {we}", "aux": [], "extra": {}, "subject": {"id": "i1", "name": "First Athlete"}, "window": [ws, we]},
                    "comparison": {kk: c[kk] for kk in ("moved", "within", "changed", "missing", "compared", "line")}, "full_comparison": c})
ROUTINE_W["runs"] = [{kk: v for kk, v in r.items() if kk != "full_comparison"} for r in _W_RUNS]
_last, _prev = _W_RUNS[-1], _W_RUNS[-2]
RUN_VIEW_W = {"run": dict({kk: v for kk, v in _last.items() if kk != "full_comparison"}, comparison=_last["full_comparison"], narrative="", data=dict(_last["data"], columns=PROPOSAL["data"]["columns"], load={"source": "intervals", "subject": {"source": "intervals", "id": "i1", "name": "First Athlete"}, "start_date": _last["data"]["window"][0], "end_date": _last["data"]["window"][1]})),
              "stdout": "RESULT: ...\n", "figures": [], "routine": None, "numbers": [n["number"] for n in _W_RUNS], "name": ROUTINE["name"], "manifest_results": [], "subject": {"id": "i1", "name": "First Athlete"},
              "against_data": dict(_prev["data"])}
SUMMARY = {"id": "r1", "name": ROUTINE["name"], "created": 1791460000, "updated": 1791460000, "source": "file", "purpose": ROUTINE["purpose"], "question": ROUTINE["question"], "origin": ROUTINE["origin"],
           "current_version": 1, "versions": 1, "runs": 0, "verified": True, "run_zero_status": "reproduced", "run_zero_line": "reproduced: 6 result line(s) identical", "inputs": 4, "results": 3, "figures": 1, "data": PROPOSAL["data"]}
SCREENS = {
    's0_save_menu':       {"js": "window.__shot.openMenu()", "routines": []},
    's1_make_dialog':     {"js": "RoutinesUI.openMake('1791460000', '1791460001', {threadRoutines: []})", "routines": []},
    's1b_next_version':   {"js": "RoutinesUI.openMake('1791460000', '1791460001', {threadRoutines: [{id: 'r1', name: 'Altitude pace correction, within athlete', version: 1, chain_id: '1791450000'}]})", "routines": [SUMMARY]},
    's1d_make_dialog_aside': {"js": "RoutinesUI.openMake('1791460000', '1791460001', {threadRoutines: []}); setTimeout(() => document.querySelector('#routineMakeModal .rt-results .more .t').click(), 900)", "routines": []},
    # the checklist while the proposal is made (§17): the fake answers at once, so the builder's view is put up for the picture - the
    # analysis read, the data checked, the model's turn at 0:42, the proposal to come
    's1e_make_dialog_waiting': {"js": "RoutinesUI.openMake('1791460000', '1791460001', {threadRoutines: []}); setTimeout(() => { document.querySelector('#routineMakeModal .ui-dlg-b').innerHTML = RoutinesUI.build.steps({ chain: { state: 'done', detail: '5 cells · 6 results · 1 figure' }, data: { state: 'done', detail: '22,705 rows · 49 columns' }, model: { state: 'running', since: Date.now() - 42000 } }, Date.now()); document.querySelector('#routineMakeModal .ui-dlg-h .sub').textContent = 'from this chain · 5 cells · 6 results · 1 figure'; document.querySelector('#routineMakeModal [data-act=\"create\"]').style.display = 'none'; }, 1500)", "routines": [], "wait": 1000},
    's1c_refused':        {"js": "RoutinesUI.openMake('1791460000', '1791460001', {threadRoutines: []})", "routines": [], "propose_error": "run zero on this chain's own data did not reproduce the analysis: 2 of 5 result lines differ ([cell 2] log speed, abroad (sea level) vs Ethiopia altitude laps: +0.11 -> +0.16; [cell 3] log speed per +1000 m venue altitude within Ethiopia, FE: -0.13 -> -0.09)"},
    's2_manager':         {"js": "RoutinesUI.openManager('r1')", "routines": [SUMMARY]},
    's2b_manager_empty':  {"js": "RoutinesUI.openManager()", "routines": []},
    # the condensing pass behind the verdict (§19): the chip says condensing… and Run is held meanwhile
    's2c_manager_condensing': {"js": "RoutinesUI.openManager('r1')", "routines": [dict(SUMMARY, run_zero_status="condensing")],
                               "routine": {**ROUTINE, "versions": [{**ROUTINE["versions"][0], "run_zero": {**ROUTINE["versions"][0]["run_zero"], "status": "condensing", "line": "condensing: the code is being condensed and checked against run zero"},
                                                                    "condensed": None}]}},
    's3_favourite_card':  {"js": "WorkflowModal.open()", "routines": [SUMMARY], "card": True},
    's4_run_dialog':      {"js": "RoutinesUI.openRun('r1')", "routines": [SUMMARY], "precheck": PRECHECK_OK},
    's4b_run_dialog_nofit': {"js": "RoutinesUI.openRun('r1')", "routines": [SUMMARY], "precheck": PRECHECK_BAD},
    's4c_run_dialog_intervals': {"js": "RoutinesUI.openRun('r1')", "routines": [SUMMARY], "precheck": PRECHECK_INTERVALS},
    's4d_run_dialog_week': {"js": "RoutinesUI.openRun('r1'); setTimeout(() => document.querySelector('#routineRunModal [data-interval=\"week\"]').click(), 900)", "routines": [SUMMARY], "precheck": PRECHECK_INTERVALS, "wait": 1500},
    # the data loaded now picked (§16.1): the athlete and interval rows grey out, the frame's problems stand under the choice
    's4e_run_dialog_now': {"js": "RoutinesUI.openRun('r1'); setTimeout(() => { const r = document.querySelector('#routineRunModal input[name=\"rt-data\"][value=\"now\"]'); r.checked = true; r.dispatchEvent(new Event('change', { bubbles: true })); }, 900)", "routines": [SUMMARY], "precheck": PRECHECK_INTERVALS, "wait": 1500},
    # a load under way (§16.2): Run pressed on Week, the cache misses, the loader's job reports 12 of 40 - the band with its bar, the rows dimmed
    's4f_run_dialog_loading': {"js": "RoutinesUI.openRun('r1'); setTimeout(() => document.querySelector('#routineRunModal [data-interval=\"week\"]').click(), 900); setTimeout(() => document.querySelector('#routineRunModal [data-act=\"run\"]').click(), 1800)", "routines": [SUMMARY], "precheck": PRECHECK_INTERVALS, "wait": 3500, "cache_miss": True, "loading": True},
    's5_run_view':        {"js": "RoutinesUI.viewRun('r1', 3)", "routines": [SUMMARY]},
    's5b_run_live':       {"js": "window.__shot.live()", "routines": [SUMMARY], "precheck": PRECHECK_OK},
    's6_manager_runs':    {"js": "RoutinesUI.openManager('r1')", "routines": [SUMMARY]},
    's6b_manager_fill':   {"js": "setTimeout(() => RoutinesUI.openManager('r1'), 1200)", "routines": [SUMMARY], "wait": 2500,
                           "fill": {"running": True, "routine_id": "r1", "routine_name": ROUTINE["name"], "interval": "week", "total": 41, "done": 12, "failed": 0, "current": ["2026-02-02", "2026-02-08"], "stopped": False, "error": "", "left": 870, "elapsed": 360}},
    # the fill ends while the Summary is open (2026-11-06; the bar goes 2026-11-08): the status answers running once, then ended - the toast says the last word, Run is back
    's6e_manager_filled': {"js": "setTimeout(() => RoutinesUI.openManager('r1'), 1200)", "routines": [SUMMARY], "wait": 5500,
                           "fill": [{"running": True, "routine_id": "r1", "routine_name": ROUTINE["name"], "interval": "week", "total": 41, "done": 40, "failed": 0, "current": ["2026-10-26", "2026-11-01"], "stopped": False, "error": "", "left": 30, "elapsed": 1110},
                                    {"running": False, "routine_id": "r1", "routine_name": ROUTINE["name"], "interval": "week", "total": 41, "done": 41, "failed": 0, "current": None, "stopped": False, "error": "", "left": None, "elapsed": 1140}]},
    's6c_manager_weekly': {"js": "RoutinesUI.openManager('r1')", "routines": [dict(SUMMARY, source="intervals")], "routine": ROUTINE_W},
    's6d_trend_enlarged': {"js": "RoutinesUI.openManager('r1'); setTimeout(() => document.querySelector('#routinesModal .rt-thumb').dispatchEvent(new MouseEvent('click', {bubbles: true})), 1200)", "routines": [dict(SUMMARY, source="intervals")], "routine": ROUTINE_W, "wait": 1200},
    's5c_trend_tab':      {"js": "RoutinesUI.viewRun('r1', %d)" % _last["number"], "routines": [dict(SUMMARY, source="intervals")], "routine": ROUTINE_W, "view": RUN_VIEW_W, "wait": 1000},
}


def render(out, light=False, width=1440, height=900):
    os.makedirs(out, exist_ok=True)
    from playwright.sync_api import sync_playwright
    html = rp.static_index(); fixtures = json.load(open(os.path.join(HERE, 'fixtures', 'workflows.json')))
    bad = []
    with sync_playwright() as pw:
        b = pw.chromium.launch()
        for name, spec_ in SCREENS.items():
            for theme in (['dark', 'light'] if light else ['dark']):
                pg = b.new_page(viewport={'width': width, 'height': height}); logs = []
                pg.on('pageerror', lambda e: logs.append(f"[pageerror] {e}"))
                threads = json.loads(json.dumps(fixtures.get('/get_threads', {"threads": []})))
                if spec_.get('card'):
                    for t in threads.get('threads', []):
                        for i, c in enumerate(t.get('chains', [])):
                            c['routines'] = [{"id": "r1", "name": ROUTINE["name"], "version": 1}] if i == 0 and t is threads['threads'][0] else []
                served = {'fill': 0}                                   # this page's count of fill-status answers (a list answers in turn)
                def handle(route, request=None, spec_=spec_, threads=threads):
                    url = route.request.url
                    path = url.split('app.local', 1)[1].split('?')[0] if 'app.local' in url else url
                    if url.startswith('http://app.local/static/'):
                        p = os.path.join(ROOT, 'web_app', 'static', url.split('/static/', 1)[1].split('?')[0])
                        if os.path.exists(p):
                            ctype = {'.css': 'text/css', '.js': 'application/javascript', '.svg': 'image/svg+xml', '.png': 'image/png'}.get(os.path.splitext(p)[1], 'application/octet-stream')
                            return route.fulfill(status=200, content_type=ctype, body=open(p, 'rb').read())
                        return route.fulfill(status=404, body='')
                    if path in ('/', '/index.html'): return route.fulfill(status=200, content_type='text/html', body=html)
                    if path == '/routines/propose':
                        if spec_.get('propose_error'):
                            lines = [{"type": "pane_turn_start", "turn": "routine", "seat": "Analyst", "model": "anthropic/claude-sonnet-5-5", "quiet": True}, {"type": "pane_turn_end", "turn": "routine", "kind": "routine", "peek": "3 input(s) proposed, 5 edit(s)", "elapsed": 11.2, "cost": 0.04},
                                     {"type": "pane_lookup_start", "kind": "routine", "query": PROPOSAL["name"]}, {"type": "pane_lookup", "kind": "routine", "query": PROPOSAL["name"], "peek": "2 of 5 result lines differ", "sources": [], "passages": []},
                                     {"routine_error": spec_['propose_error']}]
                        else:
                            lines = [{"type": "pane_turn_start", "turn": "routine", "seat": "Analyst", "model": "anthropic/claude-sonnet-5-5", "quiet": True}, {"type": "pane_turn_end", "turn": "routine", "kind": "routine", "peek": "3 input(s) proposed, 5 edit(s)", "elapsed": 11.2, "cost": 0.04},
                                     {"routine_proposal": PROPOSAL}]
                        return route.fulfill(status=200, content_type='application/json', body="\n".join(json.dumps(x) for x in lines) + "\n")
                    if path == '/routines/create':
                        lines = [{"type": "pane_lookup_start", "kind": "routine", "query": PROPOSAL["name"]}, {"type": "pane_lookup", "kind": "routine", "query": PROPOSAL["name"], "peek": "reproduced: 5 result line(s) identical", "sources": [], "passages": []},
                                 {"routine_made": {"routine": SUMMARY, "version": 1, "run_zero": ROUTINE["versions"][0]["run_zero"], "name": ROUTINE["name"]}}]
                        return route.fulfill(status=200, content_type='application/json', body="\n".join(json.dumps(x) for x in lines) + "\n")
                    if path.startswith('/routines/by_origin/'):
                        parts = path.split('/')[3:]
                        items = [dict(x, chain_id=x.get('chain_id', '1791460001')) for x in spec_.get('routines', [])]
                        if len(parts) == 2 and parts[1] != '1791460001': items = []
                        return route.fulfill(status=200, content_type='application/json', body=json.dumps({"routines": [{"id": x["id"], "name": x["name"], "version": 1, "chain_id": x.get("chain_id", "1791460001")} for x in items]}))
                    if path == '/routines':
                        return route.fulfill(status=200, content_type='application/json', body=json.dumps({"routines": spec_.get('routines', [])}))
                    if path == '/routines/r1':
                        return route.fulfill(status=200, content_type='application/json', body=json.dumps({"routine": spec_.get('routine') or ROUTINE}))
                    if spec_.get('view') and path == '/routines/r1/runs/%d' % spec_['view']['run']['number']:
                        v = json.loads(json.dumps(spec_['view'])); v["routine"] = dict(SUMMARY, source="intervals")
                        return route.fulfill(status=200, content_type='application/json', body=json.dumps(v))
                    if path == '/routines/r1/precheck':
                        return route.fulfill(status=200, content_type='application/json', body=json.dumps(spec_.get('precheck') or PRECHECK_OK))
                    if path == '/intervals/get_data_limits':
                        return route.fulfill(status=200, content_type='application/json', body=json.dumps({"max_days": 365, "compute_tier": "pro"}))
                    if path == '/intervals/athletes':          # the run dialog's athletes (2026-10-30): Run waits for them
                        return route.fulfill(status=200, content_type='application/json', body=json.dumps({"athletes": [{"id": "i1", "name": "First Athlete"}, {"id": "i2", "name": "Second Athlete"}]}))
                    if path == '/cache/inspect':
                        return route.fulfill(status=200, content_type='application/json', body=json.dumps({"tree": {}, "subjects": []}))
                    if path == '/routines/fill':               # the session's fill (§14.3): running for the manager-with-a-fill screen; a list answers in turn, the last standing
                        fills = spec_.get('fill')
                        if isinstance(fills, list): fills = fills[min(served['fill'], len(fills) - 1)]; served['fill'] += 1
                        return route.fulfill(status=200, content_type='application/json', body=json.dumps({"fill": fills or {"running": False}}))
                    if path == '/routines/r1/cached' and spec_.get('cache_miss'):
                        return route.fulfill(status=200, content_type='application/json', body=json.dumps({"hit": False, "line": ""}))
                    if path == '/intervals/load_data' and spec_.get('loading'):
                        return route.fulfill(status=200, content_type='application/json', body=json.dumps({"job_id": "job-shot"}))
                    if path == '/intervals/job/job-shot':   # the load under way: the band reads the message and the percent (§16.2)
                        return route.fulfill(status=200, content_type='application/json', body=json.dumps({"status": "processing", "message": "Downloading 12 of 40 activities…", "progress": 12, "total": 40, "percent": 30}))
                    if path == '/routines/r1/cached':          # the window the dialog opens on is in the executor's cache (2026-10-11)
                        body = json.loads(route.request.post_data or '{}')
                        return route.fulfill(status=200, content_type='application/json', body=json.dumps({"hit": True, "df_id": "df_c", "files": ["datasets/u/activity_summary_x.csv", "datasets/u/wellness_data_x.csv"], "rows": 10200,
                                                                                                           "line": f"this window ({body.get('start')} → {body.get('end')}) is in the cache (10,200 rows, with summary, wellness) - no download"}))
                    if path == '/routines/r1/runs/3' or path == '/routines/r1/runs/2':
                        v = json.loads(json.dumps(RUN_VIEW)); v["routine"] = SUMMARY
                        return route.fulfill(status=200, content_type='application/json', body=json.dumps(v))
                    if path == '/routines/r1/run':
                        r3 = RUN_VIEW["run"]
                        lines = [{"type": "pane_lookup_start", "kind": "check", "query": "EEDR_laps_2026-07.csv"}, {"type": "pane_lookup", "kind": "check", "query": "EEDR_laps_2026-07.csv", "peek": "fits the routine (49 of 49 columns); the chosen values are in the data", "sources": [], "passages": []},
                                 {"type": "pane_lookup_start", "kind": "run", "query": "run 3 · v1 · 5 cells"}, {"type": "pane_lookup", "kind": "run", "query": "run 3 · v1 · 5 cells", "peek": "ran: 6 result lines · 1 figure · 31.0 s", "sources": [], "passages": []},
                                 {"type": "pane_lookup", "kind": "compare", "query": "with run 2 (21 Oct)", "peek": r3["comparison"]["line"], "sources": [], "passages": []},
                                 {"type": "code_exec_results", "data": RUN_VIEW["stdout"]},
                                 {"type": "pane_routine_end", "number": 3, "name": ROUTINE["name"], "version": 1, "status": "ran", "line": "ran: 6 result lines", "results": 6, "compared": r3["comparison"]["compared"], "moved": r3["comparison"]["moved"], "changed": 0, "missing": 0, "figures": 1, "elapsed": 31.0, "against": 2, "comparison_line": r3["comparison"]["line"]},
                                 {"routine_run": {"run": r3, "summary": ROUTINE["runs"][2], "routine": SUMMARY, "numbers": [0, 1, 2, 3], "name": ROUTINE["name"]}}]
                        return route.fulfill(status=200, content_type='application/json', body="\n".join(json.dumps(x) for x in lines) + "\n")
                    if path == '/get_threads':
                        return route.fulfill(status=200, content_type='application/json', body=json.dumps(threads))
                    if url.startswith('http://app.local/'):
                        for k, v in fixtures.items():
                            if k in url: return route.fulfill(status=200, content_type='application/json', body=json.dumps(v))
                        return route.fulfill(status=200, content_type='application/json', body='{}')
                    if 'marked' in url: return route.fulfill(status=200, content_type='application/javascript', body=open(os.path.join(HERE, 'fixtures', 'marked_stub.js'), 'rb').read())
                    if 'dagre' in url: return route.fulfill(status=200, content_type='application/javascript', body=open(os.path.join(HERE, 'fixtures', 'dagre_stub.js'), 'rb').read())
                    return route.abort()
                pg.add_init_script("window.hljs = window.hljs || { highlightBlock() {}, highlightElement() {}, highlightAll() {}, configure() {} };")
                pg.route('**/*', handle); pg.goto('http://app.local/'); pg.wait_for_timeout(500)
                pg.evaluate("document.documentElement.setAttribute('data-theme', '%s')" % theme)
                pg.add_style_tag(content='*, *::before, *::after { animation: none !important; transition: none !important; caret-color: transparent !important; }')
                pg.evaluate("window.handleNewConversation = function () {}; try { if (typeof initializeUIControls === 'function' && !document.querySelector('.menu-overlay')) initializeUIControls(); } catch (e) {} try { if (typeof continueAppInitialization === 'function') continueAppInitialization(); } catch (e) {}")
                pg.evaluate("window.__toasts = []; const _ssm = window.showSystemMessage; window.showSystemMessage = function (m) { window.__toasts.push(m); return _ssm.apply(this, arguments); };")     # the toasts said, for the states (the toast hides itself; a fill's last word is one)
                pg.wait_for_timeout(300)
                pg.evaluate("if (window.WorkspaceGate) { WorkspaceGate.release(); WorkspaceGate.hide(); }")
                pg.evaluate(FILL); pg.wait_for_timeout(1500)
                # the finished chain in view: what the pill and the menu read
                pg.evaluate("responses = [{chain_id: '1791460001', thread_id: '1791460000', queryText: 'q'}]; currentResponseIndex = 0; currentData.chain_id = '1791460001'; currentData.thread_id = '1791460000'; currentRankData = {chain_id: '1791460001', theoretical: true}; updateRankButtonVisibility();"
                            "window.__shot = { openMenu() { const p = document.getElementById('rankButton'); p.dispatchEvent(new MouseEvent('mouseenter', {bubbles: true})); },"
                            "  live() { RoutinesUI.openRun('r1'); setTimeout(() => document.querySelector('#routineRunModal [data-act=\"run\"]').click(), 900); } };")
                try: pg.evaluate(spec_['js'])
                except Exception as e: print('  [eval]', name, str(e)[:200]); bad.append(name)
                pg.wait_for_timeout(1200)
                if name == 's5b_run_live': pg.wait_for_timeout(2500)
                if spec_.get('wait'): pg.wait_for_timeout(spec_['wait'])
                state = pg.evaluate("({steps: [...document.querySelectorAll('#routineMakeModal .rt-steps .s')].map(e => e.className + (e.querySelector('.d') ? ' ' + e.querySelector('.d').textContent : '')), runOff: !!(document.querySelector('#routinesModal .rt-actions [data-act=\"run\"]') || {}).disabled, fillGone: !document.querySelector('#routinesModal .rt-fillbar'), kept: [...document.querySelectorAll('#routineMakeModal .rt-results .r:not(.off) .l')].map(e => e.textContent), more: (document.querySelector('#routineMakeModal .rt-results .more .t') || {}).textContent || '', aside: document.querySelectorAll('#routineMakeModal .rt-results .aside .r').length, pill: getComputedStyle(document.getElementById('rankButton')).display, menu: !!document.querySelector('#saveMenu') && document.querySelector('#saveMenu').style.display !== 'none', dialog: !!document.querySelector('#routineMakeModal') && document.querySelector('#routineMakeModal').style.display === 'flex', inputs: document.querySelectorAll('#routineMakeModal .rt-inputs tbody tr').length, derived: document.querySelectorAll('#routineMakeModal .rt-inputs tbody tr[data-derived]').length, error: !!document.querySelector('#routineMakeModal .rt-error'), manager: !!document.querySelector('#routinesModal') && document.querySelector('#routinesModal').style.display === 'flex', mgrItems: document.querySelectorAll('#routinesModal .rt-side .it').length, chip: (document.querySelector('#routinesModal .rt-status') || {}).textContent || '', facts: (document.querySelector('#routinesModal .rt-facts') || {}).textContent || '', version: (document.querySelector('#routinesModal .rt-vers .v') || {}).textContent || '', cards: document.querySelectorAll('#workflowManagerModal .workflow-card-routine').length, lit: document.querySelectorAll('#workflowManagerModal .workflow-card-routine.has').length, pane: (document.getElementById('streamOutput').textContent || '').includes('Routine'),"
                                    " runDlg: !!document.querySelector('#routineRunModal') && document.querySelector('#routineRunModal').style.display === 'flex', runBtn: !!document.querySelector('#routineRunModal [data-act=\"run\"]') && !document.querySelector('#routineRunModal [data-act=\"run\"]').disabled, fitBad: !!document.querySelector('#routineRunModal .rt-fit.bad'), widgets: document.querySelectorAll('#routineRunModal [data-key]').length, derivedRows: document.querySelectorAll('#routineRunModal .rt-derived-row').length,"
                                    " dataChoice: (document.querySelector('#routineRunModal input[name=\"rt-data\"]:checked') || {}).value || '', loadWin: document.querySelectorAll('#routineRunModal input[data-load=\"start\"], #routineRunModal input[data-load=\"end\"]').length, rowsOff: [...document.querySelectorAll('#routineRunModal .rt-row.off')].map(e => e.dataset.row), band: (document.querySelector('#routineRunModal .rt-progress .t') || {}).textContent || '', bandBar: (document.querySelector('#routineRunModal .rt-progress .bar i') || {}).style ? document.querySelector('#routineRunModal .rt-progress .bar i').style.width : '', busy: !!document.querySelector('#routineRunModal .ui-dlg-b.rt-busy'), fitNote: !!document.querySelector('#routineRunModal .rt-fit.note') && document.querySelector('#routineRunModal .rt-fit.note').style.display !== 'none',"
                                    " athletes: (document.querySelector('#routineRunModal select[data-load=\"athlete\"]') || {}).value || '', interval: (document.querySelector('#routineRunModal .rt-interval .on') || {}).getAttribute ? document.querySelector('#routineRunModal .rt-interval .on').getAttribute('data-interval') : '', fillBox: !!document.querySelector('#routineRunModal input[data-load=\"fill\"]') && document.querySelector('#routineRunModal input[data-load=\"fill\"]').checked,"
                                    " plan: (document.querySelector('#routineRunModal .rt-plan') || {}).textContent || '', pickers: !!document.querySelector('#routineRunModal .rt-loadwin') && document.querySelector('#routineRunModal .rt-loadwin').style.display === 'none', runLabel: (document.querySelector('#routineRunModal [data-act=\"run\"] span') || {}).textContent || '', compare: (document.querySelector('#routineRunModal .rt-compare-sec') || {}).textContent || '',"
                                    " fillBar: (document.querySelector('#routinesModal .rt-fillbar .t') || {}).textContent || '', stopBtn: !!document.querySelector('#routinesModal [data-act=\"stop-fill\"]'), placeholder: document.getElementById('queryInput').placeholder, toast: (window.__toasts || []).slice(-1)[0] || '',"
                                    " filterOn: (document.querySelector('#routinesModal .rt-filter .on') || {}).getAttribute ? document.querySelector('#routinesModal .rt-filter .on').getAttribute('data-filter') : '', byRows: document.querySelectorAll('#routinesModal .rt-by tbody tr[data-run]').length, thumbs: document.querySelectorAll('#routinesModal .rt-by thead .rt-thumb').length, foot: (document.querySelector('#routinesModal .rt-foot') || {}).textContent || '', scrolls: [...document.querySelectorAll('#routinesModal .rt-right *')].filter(e => { const o = getComputedStyle(e).overflowY; return (o === 'auto' || o === 'scroll') && e.scrollHeight > e.clientHeight; }).map(e => e.className),"
                                    " trendDlg: !!document.querySelector('#routineTrendModal') && document.querySelector('#routineTrendModal').style.display === 'flex', chartPoints: Number((document.querySelector('#routineTrendModal .rt-chart') || {}).getAttribute ? document.querySelector('#routineTrendModal .rt-chart').getAttribute('data-points') : 0), chartGaps: document.querySelectorAll('#routineTrendModal .rt-chart rect.rt-gap').length,"
                                    " trendHeads: [...document.querySelectorAll('#content-comparison thead th')].map(e => e.textContent), trendThumbs: document.querySelectorAll('#content-comparison td.trend .rt-thumb').length, keys: document.querySelectorAll('#routineTrendModal .rt-keys .rt-key').length, footOff: !!document.querySelector('#routineTrendModal .ui-dlg-f.off'),"
                                    " inRun: RoutinesUI.inRunView(), position: document.getElementById('chainPosition').textContent, cmpRows: document.querySelectorAll('#content-comparison tbody tr').length, locked: document.getElementById('queryInput').disabled, done: !!document.querySelector('#streamOutput .sp-done'), runsTable: document.querySelectorAll('#routinesModal .rt-runs tbody tr').length, runHeads: document.querySelectorAll('#routinesModal .rt-runs thead th[data-run]').length, runItems: document.querySelectorAll('#routinesModal .rt-run, #routinesModal .rt-runbox, #routinesModal .rt-legend').length, tabs: [...document.querySelectorAll('#tabContainer .tab')].map(t => t.textContent)})")
                want = {'s0_save_menu': state['pill'] != 'none' and state['menu'], 's1_make_dialog': state['dialog'] and state['inputs'] == 4 and state['derived'] == 1 and state['pane'] and state['kept'] == ['Abroad vs altitude, adjusted', 'Per +1000 m of altitude', 'Abroad vs road, same HR band'] and state['more'] == '▸ 2 more lines recorded, not compared' and state['aside'] == 0,
                        's1d_make_dialog_aside': state['dialog'] and state['more'].startswith('▾ 2 more lines') and state['aside'] == 2,
                        's1e_make_dialog_waiting': state['dialog'] and state['steps'] == ['s done — 5 cells · 6 results · 1 figure', 's done — 22,705 rows · 49 columns', 's running — 0:42', 's pending'], 's1b_next_version': state['dialog'] and state['inputs'] == 4,
                        's1c_refused': state['dialog'] and state['error'], 's2_manager': state['manager'] and state['mgrItems'] == 1 and state['chip'] == 'verified' and state['facts'].startswith('Purposethe sea-level gap, holding effort and surface fixedInputsHard-effort threshold (lap HR) 155 ') and 'Results3 numbers and 1 chart per runVersionv1' in state['facts'] and state['version'].endswith(' · verified, 6 lines reproduced · 4 cells · 4.6 s · as written ↓') and set(state['scrolls']) <= {'rt-body'}, 's2b_manager_empty': state['manager'] and state['mgrItems'] == 0,
                        's2c_manager_condensing': state['manager'] and state['chip'] == 'condensing…' and state['runOff'] and 'cells' not in state['version'],
                        's3_favourite_card': state['cards'] >= 1 and state['lit'] >= 1,
                        's4_run_dialog': state['runDlg'] and state['runBtn'] and state['widgets'] == 3 and state['derivedRows'] == 1 and not state['fitBad'] and state['dataChoice'] == 'now', 's4b_run_dialog_nofit': state['runDlg'] and not state['runBtn'] and state['fitBad'],
                        's4c_run_dialog_intervals': state['runDlg'] and state['runBtn'] and state['widgets'] == 3 and state['dataChoice'] == 'load' and state['loadWin'] == 2 and not state['fitBad'] and not state['fitNote'] and state['athletes'] == 'i1' and state['interval'] == 'custom' and not state['pickers'] and state['rowsOff'] == [] and not state['band'],
                        's4e_run_dialog_now': state['runDlg'] and state['runBtn'] and state['dataChoice'] == 'now' and state['rowsOff'] == ['athlete', 'interval'] and state['fitNote'] and not state['band'],
                        's4f_run_dialog_loading': state['runDlg'] and not state['runBtn'] and state['busy'] and state['band'] == 'Downloading 12 of 40 activities…' and state['bandBar'] == '30%',
                        's4d_run_dialog_week': state['runDlg'] and state['runBtn'] and state['interval'] == 'week' and state['fillBox'] and state['plan'].startswith('Last complete week: ') and state['pickers'] and state['runLabel'].startswith('Run ') and state['runLabel'].endswith(' weeks') and state['compare'] == '' and not state['band'],
                        's5_run_view': state['inRun'] and state['position'] == 'run 3 of 3' and state['cmpRows'] == 3 and state['locked'] and state['done'] and state['pill'] == 'none' and state['tabs'][0] == 'Trend',
                        's5b_run_live': state['inRun'] and state['position'] == 'run 3 of 3' and state['cmpRows'] == 3 and state['locked'] and state['done'] and state['tabs'][0] == 'Trend',
                        's6_manager_runs': state['manager'] and state['runsTable'] == 3 and state['runHeads'] == 4 and state['runItems'] == 0 and state['filterOn'] == 'custom' and state['byRows'] == 0,
                        's6c_manager_weekly': state['manager'] and state['filterOn'] == 'week' and state['byRows'] == 10 and state['thumbs'] == 3 and state['runItems'] == 0 and state['runsTable'] == 0 and state['foot'].endswith(' weeks in the last year not run yet · fill them') and set(state['scrolls']) <= {'rt-body'},
                        's6d_trend_enlarged': state['trendDlg'] and state['chartPoints'] == 10 and state['chartGaps'] >= 2 and state['keys'] == 1 and state['footOff'],
                        's5c_trend_tab': state['inRun'] and state['tabs'][0] == 'Trend' and state['trendHeads'][-1] == 'Weekly trend' and state['trendThumbs'] == 3 and state['cmpRows'] == 3,
                        's6e_manager_filled': state['manager'] and state['fillGone'] and not state['stopBtn'] and not state['runOff'] and not state['locked'] and state['toast'] == 'Filled 41 weeks in 19 min',
                        's6b_manager_fill': state['manager'] and state['runOff'] and state['fillBar'] == 'Filling the weeks · 12 of 41 done · 2 – 8 Feb running · about 15 min left' and state['stopBtn'] and state['locked'] and state['placeholder'].startswith('A fill is running (Filling the weeks · 12 of 41 done')}[name]
                if not want:
                    bad.append(name); print('  [state]', name, state)
                pg.screenshot(path=os.path.join(out, f'{name}_{theme}.png')); pg.close()
                for l in logs:
                    if 'localforage' in l or 'renderMathInElement' in l or 'marked.Renderer' in l: continue
                    print('  ', name, l[:200]); bad.append(name)
        b.close()
    print('rendered', len(os.listdir(out)), 'images to', out, '; problems:', sorted(set(bad)) or 'none')
    return 1 if bad else 0


if __name__ == '__main__':
    ap = argparse.ArgumentParser(); ap.add_argument('--out', required=True); ap.add_argument('--light', action='store_true')
    a = ap.parse_args(); sys.exit(render(a.out, a.light))
