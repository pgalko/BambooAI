"""The end of a load in the three load dialogs - Intervals.icu, Endura, SweatStack - in a real Chromium (2026-11-27, the
product owner's pick of three mockups; docs/DATASETS_DESIGN.md section 19). While a load runs the Load button is grey
and its icon still, and one line says the step; once the data is in, "Loaded" with a tick stands where the button was -
no frame, nothing to press - beside the counts, and the dialog closes itself a moment later; something not loaded keeps
the dialog open with the note, and the button closes it; a failure is said and Load is back; every opening starts from
Load again. Before, the button was active again the moment the data was in, the dialog stayed up for two to six seconds
under a long green line, and the plane in the button spun.

    python3 tests/e2e/test_load_foot.py        # under half a minute; skips (exit 0) when playwright is not installed
    SHOTS=/tmp/shots python3 tests/e2e/test_load_foot.py      # and the foot of each state as a picture

The three dialogs as the page draws them (cut from index.html) with the app's stylesheets and the dialogs' own scripts;
the routes they call are answered here, the loads held until the test lets them end.
"""
import os
import re
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
try:
    from playwright.sync_api import sync_playwright
except Exception:                                          # noqa: BLE001
    print("playwright not installed: the load foot suite is skipped")
    sys.exit(0)

results = []


def check(name, cond, detail=""):
    results.append((name, bool(cond)))
    print(("  ok   " if cond else "  FAIL ") + name + ("" if cond else f"  <- {str(detail)[:600]}"))


def read(*p):
    return open(os.path.join(ROOT, *p), encoding="utf-8").read()


def dialog(html, mid):
    """The dialog's element from the page, whole: from its opening tag to the div that closes it."""
    start = html.index(f'<div id="{mid}"')
    depth, i = 0, start
    for m in re.finditer(r"<(/?)div\b", html[start:]):
        depth += -1 if m.group(1) else 1
        if depth == 0:
            i = start + m.end()
            break
    return html[start:html.index(">", i) + 1]


PAGE = read("web_app", "templates", "index.html").replace("\r\n", "\n")
METRICS = re.compile(r"\{% for metric in sweatstack_metrics %\}.*?\{% endfor %\}", re.S)
DIALOGS = "\n".join(dialog(PAGE, mid) for mid in ("intervalsModal", "enduraModal", "sweatstackModal"))
DIALOGS = METRICS.sub('<label class="metric-option"><input type="checkbox" id="power-checkbox" value="power" checked><span>power</span></label>', DIALOGS)
assert "{{" not in DIALOGS and "{%" not in DIALOGS, "a template tag left in the dialogs"
CSS = "\n".join(read("web_app", "static", "css", f) for f in ("tokens.css", "base.css", "styles.css", "components.css", "dialogs.css"))
CORE = read("web_app", "static", "js", "core.js")
SCRIPTS = [CORE[CORE.index("function localIsoDay(d) {"):CORE.index("// The store's part in a load from Intervals.icu")],
           CORE[CORE.index("// The end of a load in the three load dialogs"):CORE.index("let limitMessageTimeout = null;")],
           read("web_app", "static", "js", "integrations", "intervals.js"),
           read("web_app", "static", "js", "integrations", "sweatstack.js"),
           read("web_app", "static", "js", "integrations", "endura.js")]

# the page's globals the dialogs reach for, and the routes they call: answered here, a load held until window.release()
STAGE = """<!doctype html><html data-theme="dark"><head><meta charset="utf-8"></head><body>
<div id="datasetStatusPillsContainer"></div><button class="endura-data-option" type="button">Endura</button>
DIALOGS
<script>
var currentDatasetName = null; window.auxiliaryDatasetCount = 0;
window.pills = []; function createOrUpdateDatasetPill(id, text) { window.pills.push(text); }
function createOrUpdateTab() {} function activateTab() {} function showUploadLimitMessage(m) { window.limit = m; }
window.job = []; window.held = {};
window.release = name => { const go = window.held[name]; delete window.held[name]; if (go) go(); };
const answer = (body, status) => ({ ok: !status || status < 400, status: status || 200, json: async () => body });
const hold = name => new Promise(go => { window.held[name] = go; });
window.endura = { status: 200, body: { race_title: 'Spring classic', aux_datasets: [], dataframe: null } };
window.authService = { fetch: async (url) => {
    if (url === '/intervals/get_data_limits') return answer({ window_days: 365, reach_days: 1461, window_label: '1 year', reach_label: '4 years' });
    if (url === '/intervals/athletes') return answer({ athletes: [{ id: 'i0', name: 'First Athlete', added: '2026-10-01T00:00:00' }] });
    if (url === '/cache/inspect') return answer({ tree: { sources: [] } });
    if (url === '/intervals/load_data') return answer({ job_id: 'j1' });
    if (url.startsWith('/intervals/job/')) return answer(window.job.length > 1 ? window.job.shift() : window.job[0]);
    if (url.startsWith('/intervals/context_coding/')) return answer({ status: 'done', line: '' });
    if (url === '/endura/status') return answer({ has_api_key: true });
    if (url === '/endura/get_races') return answer({ races: [{ race_data_id: 'r1', race_title: 'Spring classic', race_date: '2026-04-01' }] });
    if (url === '/endura/load_data') { await hold('endura'); return answer(window.endura.body, window.endura.status); }
    if (url === '/sweatstack/get_data_limits') return answer({ max_days: 14 });
    if (url === '/sweatstack/get_users') return answer({ users: [{ id: 'u1', name: 'First Person', is_current: true }] });
    if (url === '/sweatstack/load_data') { await hold('sweatstack'); return answer({ message: 'loaded', dataframe: null }); }
    return answer({}, 404);
} };
</script></body></html>""".replace("DIALOGS", DIALOGS)

RESULT = {"store": {"window": 14, "held": 12, "fetched": 2}, "shape": [50400, 9], "columns": [], "aux_datasets": [], "warnings": [],
          "subject": {"folder": "intervals/i0"}}
STEP = {"status": "processing", "message": "Downloading activities... (5/14)", "percent": 35}

FOOT = """(mid) => {
    const m = document.getElementById(mid), b = m.querySelector('.ui-dlg-f button'), msg = m.querySelector('.ui-dlg-f .status');
    const cb = getComputedStyle(b), svg = b.querySelector('svg'), cm = getComputedStyle(msg);
    return { open: m.style.display === 'flex', state: b.dataset.state || '', text: b.textContent.trim(), disabled: b.disabled, cls: b.className,
             tick: !!b.querySelector('polyline'), plane: !!b.querySelector('path'), border: cb.borderTopColor, color: cb.color, events: cb.pointerEvents,
             spin: svg ? getComputedStyle(svg).animationName : '', title: b.getAttribute('title'), line: msg.textContent, lineCls: msg.className,
             lineShown: cm.display !== 'none', lineColor: cm.color, lineSize: cm.fontSize, captions: m.querySelectorAll('.button-label').length };
}"""


def foot(page, mid, settle=True):
    """The foot as drawn, once the button's colour change has run (styles.css gives it a fifth of a second)."""
    if settle:
        page.wait_for_timeout(350)
    return page.evaluate(FOOT, mid)


def shot(page, mid, name):
    if os.environ.get("SHOTS"):
        os.makedirs(os.environ["SHOTS"], exist_ok=True)
        page.locator(f"#{mid} .ui-dlg").screenshot(path=os.path.join(os.environ["SHOTS"], name + ".png"))


def closes(page, mid, within=4.0):
    """Seconds from now until the dialog is closed by itself; None if it stays past `within`."""
    t0 = time.time()
    try:
        page.wait_for_function("(mid) => document.getElementById(mid).style.display === 'none'", arg=mid, timeout=within * 1000)
    except Exception:                                      # noqa: BLE001
        return None
    return time.time() - t0


def run_intervals(page, job):
    """Open the dialog, wait for its roster and dates, set the job's answers and press Load."""
    page.evaluate("() => showIntervalsModal()")
    page.wait_for_function("() => document.querySelector('#intervalsModal .int-athlete-section').dataset.mode === 'one' && !document.getElementById('connectIntervals').disabled", timeout=10000)
    page.wait_for_function("() => (document.getElementById('intervalsEndDate') || {}).max", timeout=10000)
    page.evaluate("(job) => { window.job = job; }", job)
    page.click("#connectIntervals")


def main():
    with sync_playwright() as p:
        b = p.chromium.launch()
        page = b.new_page(viewport={"width": 900, "height": 900}, device_scale_factor=2 if os.environ.get("SHOTS") else 1)
        errors = []
        page.on("pageerror", lambda e: errors.append(str(e)))
        page.set_content(STAGE)
        page.add_style_tag(content=CSS)
        for s in SCRIPTS:
            page.add_script_tag(content=s)
        page.evaluate("() => { initializeIntervalsModals(); initializeSweatStackModals(); window.Endura.initialize(); }")

        # ---- Intervals.icu: the load runs, then the data is in
        run_intervals(page, [STEP])
        page.wait_for_function("() => document.getElementById('intervals-modal-message').textContent === 'Downloading activities · 5 of 14'", timeout=10000)
        busy = foot(page, "intervalsModal")
        shot(page, "intervalsModal", "intervals_1_loading")
        check("Intervals.icu, while the load runs: one line with the step as a count (no percent), the button grey with its own icon and word and its icon still, nothing to press, no second caption",
              busy["state"] == "busy" and busy["disabled"] and busy["plane"] and busy["text"] == "Load" and busy["border"] == "rgba(255, 255, 255, 0.25)"
              and busy["color"] == "rgba(255, 255, 255, 0.4)" and busy["spin"] == "none" and busy["events"] == "none" and busy["captions"] == 0 and "loading-message" in busy["lineCls"], busy)
        page.evaluate("() => { hideIntervalsModal(); showIntervalsModal(); }")        # closed and opened again while the load runs
        page.wait_for_function("() => document.querySelector('#intervalsModal .int-athlete-section').dataset.mode === 'one'", timeout=10000)
        during = foot(page, "intervalsModal")
        check("Intervals.icu, opened again while the load runs: the button stays grey and pressed no more - the opening and the roster drawn again leave a running load's foot alone",
              during["state"] == "busy" and during["disabled"] and during["color"] == "rgba(255, 255, 255, 0.4)", during)
        page.evaluate("(r) => { window.job = [{ status: 'completed', result: r }]; }", RESULT)
        page.wait_for_function("() => document.getElementById('connectIntervals').dataset.state === 'done'", timeout=10000)
        t_done = time.time()
        done = foot(page, "intervalsModal")
        shot(page, "intervalsModal", "intervals_2_loaded")
        gone = closes(page, "intervalsModal")
        waited = time.time() - t_done
        check("Intervals.icu, the data in: \"Loaded\" with a tick where the button was - no frame, nothing to press - and the counts beside it in plain grey; the dialog still open",
              done["open"] and done["text"] == "Loaded" and done["tick"] and not done["plane"] and done["disabled"] and done["border"] == "rgba(0, 0, 0, 0)" and done["events"] == "none"
              and done["color"] == "rgb(80, 250, 123)" and done["title"] == "Loaded" and done["line"] == "14 activities · 2 new" and "done-message" in done["lineCls"]
              and done["lineColor"] == "rgba(255, 255, 255, 0.6)" and done["lineSize"] == "12px", done)
        check("Intervals.icu: the dialog closes itself about a second and a half after \"Loaded\" (not at once, not two to six seconds later as before)",
              gone is not None and 1.2 <= waited <= 2.4, (gone, round(waited, 2)))
        page.evaluate("() => showIntervalsModal()")
        page.wait_for_function("() => !document.getElementById('connectIntervals').disabled", timeout=10000)
        again = foot(page, "intervalsModal")
        check("Intervals.icu, opened again: Load as the page drew it - its icon, its word, its title - and the foot's store line in place of the counts",
              again["state"] == "idle" and again["text"] == "Load" and again["plane"] and not again["disabled"] and again["title"] == "Load data from Intervals.icu"
              and again["line"].startswith("Nothing in the store for First Athlete yet") and "done-message" not in again["lineCls"], again)

        # ---- something not loaded: the dialog stays, the note beside the counts, the button closes it
        noted = dict(RESULT, warnings=["no wellness file: the window has no wellness days"])
        run_intervals(page, [{"status": "completed", "result": noted}])
        page.wait_for_function("() => document.getElementById('connectIntervals').dataset.state === 'close'", timeout=10000)
        page.mouse.move(5, 5)                                # the pointer off the button it pressed: Close is drawn as at rest, not under the pointer
        note = foot(page, "intervalsModal")
        shot(page, "intervalsModal", "intervals_3_not_loaded")
        stays = closes(page, "intervalsModal", within=2.5)
        page.click("#connectIntervals")
        shut = page.evaluate("() => document.getElementById('intervalsModal').style.display")
        check("Intervals.icu, something not loaded: the note beside the counts says what and why, the button reads Close and is pressable, the dialog stays open - and Close closes it",
              note["line"] == "14 activities · 2 new. Wellness not loaded: the window has no wellness days." and note["text"] == "Close" and not note["disabled"]
              and note["border"] == "rgb(80, 250, 123)" and stays is None and shut == "none", (note, stays, shut))

        # ---- a failure: said in red, Load back
        run_intervals(page, [{"status": "error", "error": "the executor did not answer"}])
        page.wait_for_function("() => /Failed/.test(document.getElementById('intervals-modal-message').textContent)", timeout=10000)
        failed = foot(page, "intervalsModal")
        check("Intervals.icu, a failure: the line says it in red and Load is back, pressable, with its icon",
              failed["line"] == "✗ Failed: the executor did not answer" and "error-message" in failed["lineCls"] and failed["state"] == "idle" and not failed["disabled"] and failed["plane"]
              and failed["lineColor"] == "rgb(255, 107, 107)", failed)

        # ---- closed and opened again in the moment before the close: the dialog opened again stays
        run_intervals(page, [{"status": "completed", "result": RESULT}])
        page.wait_for_function("() => document.getElementById('connectIntervals').dataset.state === 'done'", timeout=10000)
        page.evaluate("() => { hideIntervalsModal(); showIntervalsModal(); }")
        kept = closes(page, "intervalsModal", within=2.5)
        check("Intervals.icu: a dialog closed and opened again within that moment is not closed under the person by the earlier load", kept is None, kept)
        page.evaluate("() => hideIntervalsModal()")

        # ---- a load started from the Dataset cache dialog: it hears how the load goes; the Intervals.icu dialog's foot is not touched
        page.evaluate("() => { showIntervalsModal(); hideIntervalsModal(); document.getElementById('intervals-modal-message').textContent = 'as it stood'; }")
        page.evaluate("(r) => { window.job = [{ status: 'processing', message: 'Assembling the window from the store...' }, { status: 'completed', result: r }]; window.said = [];"
                      " window.Intervals.pollJob('j2', { start: '2026-08-01', end: '2026-10-30' }, [], { progress: l => window.said.push(['progress', l]), end: (ok, l, n) => window.said.push(['end', ok, l, n]) }); }",
                      dict(RESULT, store={"window": 101, "held": 101, "fetched": 0, "offline": True}))
        page.wait_for_function("() => window.said.some(s => s[0] === 'end')", timeout=10000)
        heard = page.evaluate("() => ({ said: window.said, state: document.getElementById('connectIntervals').dataset.state, line: document.getElementById('intervals-modal-message').textContent })")
        check("the Dataset cache dialog's load hears the step and the end - the counts as from the store - through its report; the Intervals.icu dialog's button and line are left as they were",
              heard["said"] == [["progress", "Assembling the window from the store…"], ["end", True, "101 activities · from the store", ""]] and heard["state"] == "idle" and heard["line"] == "as it stood", heard)

        # ---- Endura: the same end; its line keeps the dialog's look while it changes
        page.evaluate("() => { currentDatasetName = null; window.Intervals.state.isLoaded = false; }")
        page.click(".endura-data-option")
        page.wait_for_function("() => document.getElementById('enduraModal').style.display === 'flex' && document.querySelectorAll('#enduraRaceSelect option').length === 2", timeout=10000)
        page.select_option("#enduraRaceSelect", "r1")
        page.click("#loadEnduraData")
        page.wait_for_function("() => 'endura' in window.held", timeout=10000)
        e_busy = foot(page, "enduraModal")
        page.evaluate("() => window.release('endura')")
        page.wait_for_function("() => document.getElementById('loadEnduraData').dataset.state === 'done'", timeout=10000)
        e_done = foot(page, "enduraModal")
        shot(page, "enduraModal", "endura_loaded")
        e_gone = closes(page, "enduraModal")
        check("Endura: grey and still while the race loads, its line in the dialog's own look (the line's classes kept); then \"Loaded\" with no line beside it, and the dialog closes itself",
              e_busy["state"] == "busy" and e_busy["spin"] == "none" and e_busy["color"] == "rgba(255, 255, 255, 0.4)" and e_busy["line"] == "Loading race data..."
              and "int-message" in e_busy["lineCls"] and "status" in e_busy["lineCls"] and "loading-message" in e_busy["lineCls"] and e_busy["lineColor"] == "rgba(255, 255, 255, 0.5)"
              and e_done["text"] == "Loaded" and e_done["tick"] and not e_done["lineShown"] and e_gone is not None and e_gone <= 2.4, (e_busy, e_done, e_gone))
        page.evaluate("() => { currentDatasetName = null; window.Endura.state.isLoaded = false; window.endura = { status: 500, body: { error: 'the race file is not there' } }; }")
        page.click(".endura-data-option")
        page.wait_for_function("() => document.getElementById('enduraModal').style.display === 'flex' && document.getElementById('loadEnduraData').dataset.state === 'idle'", timeout=10000)
        page.wait_for_function("() => document.querySelectorAll('#enduraRaceSelect option').length === 2", timeout=10000)
        page.select_option("#enduraRaceSelect", "r1")
        page.click("#loadEnduraData")
        page.wait_for_function("() => 'endura' in window.held", timeout=10000)
        page.evaluate("() => window.release('endura')")
        page.wait_for_function("() => /Failed/.test(document.getElementById('endura-modal-message').textContent)", timeout=10000)
        e_fail = foot(page, "enduraModal")
        check("Endura, a failure: said in red in the dialog's look, Load back and pressable",
              e_fail["line"] == "✗ Failed: the race file is not there" and "int-message" in e_fail["lineCls"] and "error-message" in e_fail["lineCls"] and e_fail["lineColor"] == "rgb(255, 107, 107)"
              and e_fail["state"] == "idle" and not e_fail["disabled"] and e_fail["plane"], e_fail)
        page.evaluate("() => { document.getElementById('enduraModal').style.display = 'none'; }")

        # ---- SweatStack: the same end; the foot's own note at every opening
        page.evaluate("() => { currentDatasetName = null; window.SweatStack.showModal(); }")
        page.wait_for_function("() => document.querySelectorAll('#users-selection input:checked').length === 1", timeout=10000)
        s_open = foot(page, "sweatstackModal")
        page.click("#connectSweatstack")
        page.wait_for_function("() => 'sweatstack' in window.held", timeout=10000)
        s_busy = foot(page, "sweatstackModal")
        page.evaluate("() => window.release('sweatstack')")
        page.wait_for_function("() => document.getElementById('connectSweatstack').dataset.state === 'done'", timeout=10000)
        s_done = foot(page, "sweatstackModal")
        shot(page, "sweatstackModal", "sweatstack_loaded")
        s_gone = closes(page, "sweatstackModal")
        page.evaluate("() => { currentDatasetName = null; window.SweatStack.showModal(); }")
        s_again = foot(page, "sweatstackModal")
        check("SweatStack: grey and still while it loads, then \"Loaded\" with no line, the dialog closing itself; opened again, Load and the page's own note - not the longer sentence that came back after a load",
              s_open["line"] == "More metrics and a longer window take longer to load and process." and s_busy["state"] == "busy" and s_busy["spin"] == "none" and s_busy["captions"] == 0
              and s_done["text"] == "Loaded" and not s_done["lineShown"] and s_gone is not None and s_gone <= 2.4
              and s_again["state"] == "idle" and s_again["text"] == "Load" and s_again["line"] == s_open["line"], (s_open, s_busy, s_done, s_gone, s_again))
        check("no error on the page through all of it", not errors, errors)
        b.close()

    fails = [n for n, ok in results if not ok]
    print(f"\n{len(results) - len(fails)} passed, {len(fails)} failed")
    sys.exit(1 if fails else 0)


if __name__ == "__main__":
    main()
