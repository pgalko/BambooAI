"""The real page in headless Chromium against the local stack, walked and screenshotted.

    python3 tools/stack/browse.py --out /tmp/shots                 # starts a fresh stack, walks the story, stops it
    python3 tools/stack/browse.py --out /tmp/shots --attach        # against a stack already `stack.py up`
    python3 tools/stack/browse.py --out /tmp/shots --light         # the same states in the light theme too
    python3 tools/stack/browse.py --out /tmp/shots --state cold    # one named state only (see STATES)
    python3 tools/stack/browse.py --out /tmp/shots --js "WorkflowModal.open()" --name dlg   # any state, by a snippet

The story: cold page -> the dataset uploaded through the file input -> the question typed ->
Deep run (screenshots while it runs and when it completes) -> each right-pane tab -> the
simplified view -> a follow-up on the warm kernel -> the chain navigation -> the thread map ->
Save as favourite -> Saved workflows -> the settings dialogs -> a question framed with the
Architect, its analysis, and the next questions that follow it.
Page errors and console errors are written to <out>/console.txt; a non-empty errors list makes
the exit status 1, so the walk doubles as a smoke test.
"""
import argparse
import json
import os
import re
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path[:0] = [HERE, os.path.join(HERE, "browser")]
import vendor  # noqa: E402
from stack import Stack, DEFAULT_WORKDIR  # noqa: E402

INIT_JS = """
window.__stackErrors = [];
window.addEventListener('error', e => window.__stackErrors.push(String(e.message)));
"""


class Walk:
    def __init__(self, page, out, light=False):
        self.page, self.out, self.light, self.n, self.taken = page, out, light, 0, []
        os.makedirs(out, exist_ok=True)

    def shot(self, name, full=False):
        self.n += 1
        themes = ["dark", "light"] if self.light else ["dark"]
        for theme in themes:
            self.page.evaluate(f"document.documentElement.setAttribute('data-theme','{theme}')")
            self.page.wait_for_timeout(150)
            path = os.path.join(self.out, f"{self.n:02d}_{name}_{theme}.png")
            self.page.screenshot(path=path, full_page=full)
            self.taken.append(path)
        self.page.evaluate("document.documentElement.setAttribute('data-theme','dark')")
        return path

    def wait_text(self, selector, text, timeout=120000):
        self.page.wait_for_function(
            "([sel, t]) => [...document.querySelectorAll(sel)].some(e => e.textContent.includes(t))",
            arg=[selector, text], timeout=timeout)

    def js(self, code):
        return self.page.evaluate(code)


def route_factory(app_url):
    def handle(route):
        url = route.request.url
        if url.startswith(app_url):
            return route.continue_()
        got = vendor.resolve(url)
        if got is not None:
            body, ctype = got
            return route.fulfill(status=200, content_type=ctype, body=body)
        return route.abort()
    return handle


def _wait_ready(page, state, timeout):
    """The page is usable: the workspace gate has released (it reloads once on a fresh load, then waits for
    the executor); on a page without the gate, the app's own 'App initialization complete' line."""
    page.wait_for_function("() => document.getElementById('workspaceGate') ? (window.WorkspaceGate && WorkspaceGate.state().open === false)"
                           " : (typeof continueAppInitialization === 'function' && !!document.querySelector('#queryInput'))", timeout=timeout * 1000)
    t0 = time.time()
    while not state["ready"] and not page.evaluate("!!document.getElementById('workspaceGate')"):
        if time.time() - t0 > timeout:
            raise TimeoutError("the page never reported 'App initialization complete'")
        page.wait_for_timeout(100)
    page.wait_for_timeout(300)


SESSION_COOKIE = {"name": "auth0.local.is.authenticated", "value": "true"}     # what the SDK leaves while signed in
SIGNED_OUT_COOKIE = {"name": "stack.signedout", "value": "1"}                  # the stand-in plays a logged-out browser


def open_page(pw, app_url, width=1440, height=900, cookies=None):
    """cookies: None = a browser that has signed in before (the SDK's session cookie); [] = a first visit;
    [SIGNED_OUT_COOKIE] = the page that comes back from a logout."""
    b = pw.chromium.launch()
    ctx = b.new_context(viewport={"width": width, "height": height})
    jar = [dict(c, url=app_url) for c in ([SESSION_COOKIE] if cookies is None else cookies)]
    if jar:
        ctx.add_cookies(jar)
    page = ctx.new_page()
    logs = []
    state = {"ready": False}

    def on_console(m):
        if m.type in ("error", "warning"):
            logs.append(f"[{m.type}] {m.text}")
        if m.text.strip() == "App initialization complete":       # core.js, after the subscription check
            state["ready"] = True
    page.on("console", on_console)
    page.app_ready = lambda timeout=60: _wait_ready(page, state, timeout)
    page.on("pageerror", lambda e: logs.append(f"[pageerror] {e}"))
    page.on("response", lambda r: logs.append(f"[http {r.status}] {r.request.method} {r.url}") if r.status >= 400 else None)
    page.add_init_script(INIT_JS)
    page.route("**/*", route_factory(app_url))
    return b, page, logs


def story(w, mod, dataset, questions):
    p = w.page
    p.goto(w.app_url)
    p.wait_for_selector("#queryInput", state="visible", timeout=60000)
    p.app_ready()
    p.wait_for_function("() => document.querySelector('#containerStatusText') && /Ready|Offline/.test(document.querySelector('#containerStatusText').textContent)", timeout=30000)
    p.wait_for_timeout(500)
    w.shot("cold")

    # the dataset, through the real file input and /upload
    p.set_input_files("#primaryFile", dataset)
    p.wait_for_selector(".primary-dataset-pill", timeout=60000)
    p.wait_for_function("() => document.querySelector('#containerStatusText') && /Ready/.test(document.querySelector('#containerStatusText').textContent)", timeout=30000)
    p.wait_for_timeout(800)
    w.shot("data_loaded")

    # the question, Deep
    p.fill("#queryInput", questions[0])
    w.js("setMode('deep')")
    p.wait_for_timeout(200)
    w.shot("composer")
    p.click("#submitQuery")
    w.wait_text(".sp-turn", "Turn 1", 30000)
    p.wait_for_timeout(700)
    w.shot("running_turn1")
    p.wait_for_selector(".sp-row.fail", timeout=120000)
    p.wait_for_timeout(300)
    w.shot("running_failed_cell")
    w.wait_text(".sp-done", "Run complete", 180000)
    p.wait_for_timeout(1200)
    w.js("activateTab('answer')")
    p.wait_for_timeout(500)
    w.shot("run_complete_answer")
    w.shot("answer_full", full=True)

    for tab, name in (("plan", "tab_investigation"), ("code", "tab_code"), ("plot", "tab_plots"),
                      ("code_exec_results", "tab_results"), ("dataframe", "tab_data")):
        w.js(f"activateTab('{tab}')")
        p.wait_for_timeout(500)
        w.shot(name)
    w.js("activateTab('answer')")
    p.wait_for_timeout(300)
    if p.query_selector(".simplified-summary-btn"):
        p.click(".simplified-summary-btn")
        p.wait_for_timeout(500)
        w.shot("simplified")
        p.click(".simplified-summary-btn")
        p.wait_for_timeout(300)

    # a follow-up on the warm kernel
    p.fill("#queryInput", questions[1])
    p.click("#submitQuery")
    w.wait_text("#chainPosition", "chain 2 of 2", 60000)
    w.wait_text(".sp-done", "Run complete", 180000)
    p.wait_for_timeout(1200)
    w.shot("followup_answer")

    # navigation and the map
    p.click("#prevResponse")
    p.wait_for_timeout(600)
    w.shot("chain1_of_2")
    p.click("#nextResponse")
    p.wait_for_timeout(400)
    p.click("#railMapButton")
    p.wait_for_timeout(900)
    w.shot("thread_map")
    p.click("#workflowMapModal .workflow-close")
    p.wait_for_timeout(300)

    # Save: the pill's menu, then Save as favourite - one click
    if p.query_selector("#saveButton"):
        p.click("#saveButton")
        p.wait_for_selector("#saveMenu", state="visible", timeout=10000)
        w.shot("save_menu")
        p.click("#saveMenu .it[data-act='favourite']")
        p.wait_for_timeout(2500)
        w.shot("saved")

    # the dialogs
    def close_dialogs():
        # every open dialog closed through its own control; whatever survives is hidden outright
        p.evaluate("""() => { const vis = e => e.getClientRects().length > 0;
            document.querySelectorAll('[aria-label="Close"], button.close').forEach(b => { if (vis(b)) b.click(); });
            if (window.WorkflowModal && WorkflowModal.close) { try { WorkflowModal.close(); } catch (e) {} }
            document.querySelectorAll('.modal, .ui-modal, .ui-modal-plain, .map-drawer').forEach(m => { if (vis(m)) m.style.display = 'none'; }); }""")
        p.wait_for_timeout(350)

    p.click("#workflowManagerPill")
    p.wait_for_timeout(1200)
    w.shot("saved_workflows")
    close_dialogs()
    p.click("#datasetManagerPill")
    p.wait_for_timeout(900)
    w.shot("dataset_cache")
    close_dialogs()
    p.click(".settings-container")
    p.wait_for_timeout(500)
    w.shot("settings_menu")
    close_dialogs()
    w.js("showSubscriptionModal(false)")
    p.wait_for_timeout(800)
    w.shot("account_dialog")
    close_dialogs()

    # the Architect (docs/ARCHITECT_DESIGN.md §2.11-§2.14, §2.18): a question typed with the switch on, the conversation that
    # fills its brief, the parts + Add offers, the check of what it rests on against the data, the explanation it proposes and
    # the coach ticks, a line changed by hand, an earlier version on screen, the analysis started from the brief, the report
    # against it, the thread map
    brief_question = getattr(mod, "BRIEF_QUESTION", None)
    if brief_question and p.query_selector("#architectSwitch"):
        def write(path, text, keep=True):
            n = p.evaluate("() => JSON.parse(document.querySelector('#content-brief .ar-brief').dataset.framing).versions.length")
            pen = f'#content-brief .ar-line[data-path="{path}"] [data-ar="edit"]'
            if p.locator(pen).count():
                p.click(pen)
            else:                                            # a part the brief does not show: + Add, then its name
                p.click('#content-brief [data-ar="more"]')
                p.click(f'#content-brief .ar-kinds [data-ar="add"][data-path="{path}"]')
            p.fill("#content-brief .ar-input", text)
            if keep:
                p.keyboard.press("Enter")
                p.wait_for_function("(n) => JSON.parse(document.querySelector('#content-brief .ar-brief').dataset.framing).versions.length === n + 1", arg=n, timeout=15000)

        def said(n):
            p.wait_for_function("(n) => document.querySelectorAll('#streamOutput .sp-stream > .ar-msg.arch:not(.wait)').length === n && !document.getElementById('queryInput').disabled", arg=n, timeout=30000)
            p.wait_for_timeout(300)
        p.click("#architectSwitch")
        p.fill("#queryInput", brief_question)
        p.wait_for_timeout(200)
        w.shot("architect_composer")
        p.click("#submitQuery")
        p.wait_for_selector("#content-brief .ar-brief", timeout=15000)
        said(1)
        w.shot("architect_first_question")
        p.click('#content-brief [data-ar="more"]')           # the parts the brief does not show yet, to add by hand
        p.wait_for_timeout(300)
        w.shot("architect_add")
        p.click('#content-brief [data-ar="more"]')
        p.click("#streamOutput .ar-choice")
        said(2)
        p.fill("#queryInput", "C does better than A because the C plots got the most rain.")
        p.wait_for_timeout(200)
        w.shot("architect_answer_typed")
        p.click("#submitQuery")
        said(3)
        write("rests_on.+", "Each regime has the same number of plots.")
        write("rests_on.+", "The C plots looked greener last season.")
        p.fill("#queryInput", "C yields at least 0.3 t/ha more than A.")
        p.click("#submitQuery")
        said(5)                                              # it says it is checking, the data is looked up, and it goes on with the marks
        w.shot("architect_checked")
        p.click("#streamOutput .ar-choice")                  # Keep it
        said(6)
        w.shot("architect_ready")
        versions = p.evaluate("() => JSON.parse(document.querySelector('#content-brief .ar-brief').dataset.framing).versions.length")
        p.click('#content-brief .ar-line[data-path="also_check.0"] .tick')      # what the Architect proposed, accepted
        p.wait_for_function("(n) => JSON.parse(document.querySelector('#content-brief .ar-brief').dataset.framing).versions.length === n + 1", arg=versions, timeout=15000)
        p.wait_for_timeout(300)
        w.shot("architect_ticked")
        write("also_check.+", "Rainfall differed between the C and A plots.")
        write("fixed.comparison", "regime C against regime A, within soil type")
        write("fixed.measure", "yield_t_ha, plot means", keep=False)
        p.wait_for_timeout(300)
        w.shot("architect_brief_typing")
        p.keyboard.press("Enter")
        p.wait_for_function("() => !document.querySelector('#content-brief .editing')", timeout=15000)
        p.hover('#content-brief .ar-line[data-path="rests_on.0"]')
        p.wait_for_timeout(300)
        w.shot("architect_brief")
        p.click('#content-brief [data-ar="step"][data-step="-1"]')
        p.click('#content-brief [data-ar="step"][data-step="-1"]')
        p.click('#content-brief [data-ar="step"][data-step="-1"]')
        p.wait_for_timeout(300)
        w.shot("architect_brief_older_version")
        for _ in range(3):
            p.click('#content-brief [data-ar="step"][data-step="1"]')
        p.click("#railMapButton")
        p.wait_for_timeout(900)
        w.shot("architect_map_not_run")
        p.click("#workflowMapModal .workflow-close")
        p.wait_for_timeout(300)
        p.click('#content-brief [data-ar="start"]')
        w.wait_text(".sp-done", "Run complete", 180000)
        p.wait_for_timeout(1200)
        w.js("activateTab('answer')")
        p.wait_for_timeout(500)
        w.shot("architect_answer")
        p.click("#streamOutput .ar-fold > summary")
        w.js("activateTab('brief')")
        p.wait_for_timeout(400)
        w.shot("architect_brief_after_run")
        p.click("#streamOutput .ar-fold > summary")
        p.click("#railMapButton")
        p.wait_for_timeout(900)
        w.shot("architect_map")
        p.click("#workflowMapModal .workflow-close")
        p.wait_for_timeout(300)
        # next questions (docs/ARCHITECT_DESIGN.md §2.7): the button on the closing card, the levels, the cards of one level, a
        # question run as it stands - the switch still on - and the analysis it follows with the card marked
        w.js("activateTab('answer')")
        p.click('#streamOutput .sp-done [data-nq="open"]')
        p.wait_for_selector("#nextLevels .it", state="visible", timeout=5000)
        p.wait_for_timeout(300)
        w.shot("next_levels")
        p.click('#nextLevels .it[data-level="emergence"]')
        p.wait_for_selector('#streamOutput .nq-set[data-set="0"] .nq-card', timeout=30000)
        p.wait_for_timeout(500)
        w.shot("next_cards")
        followed = p.evaluate("() => responses.length")
        p.click('#streamOutput .nq-set[data-set="0"] .nq-card[data-k="0"] .go')
        p.wait_for_function("(n) => responses.length === n + 1 && !responses[n].status", arg=followed, timeout=180000)
        w.js("activateTab('answer')")
        p.wait_for_timeout(600)
        w.shot("next_run")
        p.click("#railMapButton")
        p.wait_for_timeout(900)
        w.shot("next_map")
        p.click("#workflowMapModal .workflow-close")
        p.wait_for_timeout(300)
        p.click("#prevResponse")
        p.wait_for_selector("#streamOutput .nq-card.ran", timeout=10000)
        w.js("activateTab('answer'); const s = document.getElementById('streamOutput'); s.scrollTop = s.scrollHeight;")
        p.wait_for_timeout(400)
        w.shot("next_card_run")
        p.click("#architectSwitch")

    # the saved analyses in the Architect (docs/ARCHITECT_DESIGN.md §3.7, §2.18): the framed analysis saved, then a question it
    # bears on framed in a workflow of its own - what the reading found, under its row and under the brief; one analysis
    # viewed whole; the coach's answer that builds on it; a second reading asked for in words and skipped; and the analysis
    # under that brief: its first step opens the saved one
    saved_question = getattr(mod, "SAVED_QUESTION", None)
    if brief_question and saved_question and p.query_selector("#architectSwitch"):
        framed = p.evaluate("() => String(responses[currentResponseIndex].chain_id)")      # the framed analysis, on screen: the one viewed and built on
        view = f'#streamOutput .ar-found [data-ar="open"][data-run="{framed}"]'
        p.click("#saveButton")
        p.wait_for_selector("#saveMenu", state="visible", timeout=10000)
        p.click("#saveMenu .it[data-act='favourite']")
        p.wait_for_function("() => document.getElementById('saveButton').classList.contains('saved')", timeout=30000)
        p.wait_for_timeout(2000)                             # the memory view follows behind the save
        w.js("handleNewConversation()")
        p.wait_for_url("**/?new=true", timeout=60000)
        p.wait_for_selector("#queryInput", state="visible", timeout=60000)
        p.app_ready()
        p.wait_for_function("() => /Ready|Local|Docker/.test(document.querySelector('#containerStatusText').textContent)", timeout=60000)
        p.set_input_files("#primaryFile", dataset)
        p.wait_for_selector(".primary-dataset-pill", timeout=60000)
        p.wait_for_timeout(500)
        p.click("#architectSwitch")
        p.fill("#queryInput", saved_question)
        p.click("#submitQuery")
        p.wait_for_selector("#content-brief .ar-brief", timeout=15000)
        said(1)
        p.click("#streamOutput .ar-choice >> nth=1")
        said(2)
        for n in (3, 5):                                     # two parts skipped; then it says it is looking, the saved analyses are read, and it goes on
            p.fill("#queryInput", "skip")
            p.click("#submitQuery")
            said(n)
        w.shot("saved_found")
        p.click(view)
        p.wait_for_function("() => { const m = document.getElementById('savedAnalysisModal'); return !!m && getComputedStyle(m).display !== 'none'; }", timeout=10000)
        p.wait_for_timeout(400)
        w.shot("saved_open")
        for name, shot in (("Conversation", "saved_open_conversation"), ("Brief", "saved_open_brief")):      # what was said while that analysis was framed, then the brief it ran under
            p.click(f'#savedAnalysisModal details.ar-code summary:text-is("{name}")')
            p.wait_for_timeout(300)
            w.shot(shot)
            p.click(f'#savedAnalysisModal details.ar-code summary:text-is("{name}")')
        p.click("#savedAnalysisModal .ui-dlg-h .x")
        at = p.evaluate("(sel) => [...document.querySelectorAll('#streamOutput .ar-found .it')].findIndex(it => it.contains(document.querySelector(sel)))", view)
        p.click(f"#streamOutput .ar-choice >> nth={max(at, 0)}")      # the choice that names it: the brief builds on that analysis
        said(6)
        p.wait_for_timeout(300)
        w.shot("saved_built")
        p.fill("#queryInput", mod.ARCHITECT_AGAIN)           # one more reading, asked for in words - and skipped
        p.click("#submitQuery")
        p.wait_for_selector("#streamOutput .sp-row.pending .ar-skip:not([disabled])", timeout=15000)
        w.shot("saved_looking")
        p.click("#streamOutput .sp-row.pending .ar-skip")
        said(8)
        w.shot("saved_skipped")
        p.click('#content-brief [data-ar="start"]')          # the Analyst opens the saved analysis the brief builds on, then computes
        w.wait_text(".sp-done", "Run complete", timeout=240000)
        p.wait_for_timeout(600)
        w.shot("saved_run")
        p.click("#architectSwitch")

    # the Architect as a tutor (2026-11-17), with nothing loaded: a bare request, what could be looked at, the question as the
    # Architect words it - written at once, a version each time - and an earlier version brought back with the arrow; then the
    # analysis, a question that follows it - the saved analyses read, the report of the analysis before opened - and "build on it"
    tutor_question = getattr(mod, "TUTOR_QUESTION", None)
    if brief_question and tutor_question and p.query_selector("#architectSwitch"):
        w.js("handleNewConversation()")
        p.wait_for_url("**/?new=true", timeout=60000)
        p.wait_for_selector("#queryInput", state="visible", timeout=60000)
        p.app_ready()
        p.wait_for_function("() => /Ready|Local|Docker/.test(document.querySelector('#containerStatusText').textContent)", timeout=60000)
        p.click("#architectSwitch")
        p.fill("#queryInput", tutor_question)
        p.click("#submitQuery")
        p.wait_for_selector("#content-brief .ar-brief", timeout=15000)
        said(1)
        w.shot("tutor_first")
        p.click("#streamOutput .ar-choice >> nth=0")          # a choice taken: the Architect words the question, and it is the question at once
        said(2)
        p.wait_for_timeout(300)
        w.shot("tutor_question")
        p.fill("#queryInput", mod.ARCHITECT_OWN + "Plot regime C beside regime A")      # a wording of the coach's own: one more version
        p.click("#submitQuery")
        said(3)
        p.click('#content-brief [data-ar="step"][data-step="-1"]')      # the arrow back: the version before is on screen, and Start analysis names it
        p.wait_for_timeout(300)
        w.shot("tutor_version_back")
        follow = getattr(mod, "FOLLOW_QUESTION", None)
        if follow:
            for path, text in (("decision", "I want to see the two side by side."), ("fixed.period", "the 2025 season")):      # added to the version on screen
                write(path, text)
            p.wait_for_timeout(300)
            w.shot("tutor_brief")
            w.js("setMode('deep')")
            p.click('#content-brief [data-ar="start"]')
            w.wait_text(".sp-done", "Run complete", timeout=240000)
            p.wait_for_timeout(600)
            p.fill("#queryInput", follow)                    # a question that follows it, the switch still on
            p.click("#submitQuery")
            p.wait_for_selector('#content-brief .ar-brief[data-state="framing"]', timeout=15000)
            said(3)                                           # having a look, opening the report, speaking from it
            p.wait_for_timeout(300)
            w.shot("tutor_follow")
            p.click("#streamOutput .ar-choice >> nth=0")      # build on it: the brief builds on that analysis
            said(4)
            p.wait_for_timeout(300)
            w.shot("tutor_build")
        p.click("#architectSwitch")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    ap.add_argument("--attach", action="store_true", help="use the stack in --workdir instead of starting one")
    ap.add_argument("--workdir", default=DEFAULT_WORKDIR)
    ap.add_argument("--scenario", default="field_trial")
    ap.add_argument("--light", action="store_true")
    ap.add_argument("--js", default="", help="run this snippet after load and screenshot (no story)")
    ap.add_argument("--name", default="state")
    ap.add_argument("--width", type=int, default=1440)
    ap.add_argument("--height", type=int, default=900)
    ap.add_argument("--edition", choices=("hosted", "local"), default="hosted")
    a = ap.parse_args()

    from playwright.sync_api import sync_playwright
    made, got = vendor.prepare(fetch=True)
    print("CDN libraries:", json.dumps(vendor.status()))

    if a.attach:
        st = json.load(open(os.path.join(a.workdir, "stack.json")))
        stack = None
        app_url, dataset, scenario_name = f"http://127.0.0.1:{st['ports']['app']}", st["dataset"], st["scenario"]
    else:
        stack = Stack(workdir=a.workdir, scenario=a.scenario, fresh=True, auto_ports=True, edition=a.edition).start()
        app_url, dataset, scenario_name = stack.app_url, stack.dataset, a.scenario
    import harness_models
    mod = harness_models.load(scenario_name)
    questions = list(getattr(mod, "QUESTIONS", ["Describe the data.", "What else stands out?"]))

    logs, ok = [], True
    try:
        with sync_playwright() as pw:
            b, page, logs = open_page(pw, app_url, a.width, a.height)
            w = Walk(page, a.out, a.light)
            w.app_url = app_url
            try:
                if a.js:
                    page.goto(app_url)
                    page.wait_for_selector("#queryInput", state="visible", timeout=60000)
                    page.app_ready()
                    page.wait_for_timeout(500)
                    page.evaluate(a.js)
                    page.wait_for_timeout(900)
                    w.shot(a.name)
                else:
                    story(w, mod, dataset, questions)
            except Exception as exc:                        # noqa: BLE001
                ok = False
                logs.append(f"[walk] {type(exc).__name__}: {str(exc)[:400]}")
                try:
                    w.shot("failure_state")
                except Exception:                            # noqa: BLE001
                    pass
            errs = page.evaluate("window.__stackErrors || []")
            logs += [f"[window.error] {e}" for e in errs]
            b.close()
    finally:
        if stack is not None:
            calls = stack.orchestrator_calls()
            open(os.path.join(a.out, "orchestrator_calls.json"), "w").write(json.dumps(calls, indent=1))
            for name in ("webapp", "executor", "orchestrator"):
                open(os.path.join(a.out, f"log_{name}.txt"), "w").write(stack.logs(name, tail=400))
            stack.stop()
    with open(os.path.join(a.out, "console.txt"), "w") as fh:
        fh.write("\n".join(logs))
    real_errors = [l for l in logs if l.startswith(("[pageerror]", "[error]", "[walk]", "[window.error]"))
                   and "favicon" not in l and "ERR_FAILED" not in l and "net::ERR" not in l]
    print(f"{len(w.taken)} screenshots in {a.out}; {len(real_errors)} error(s)" + ("" if ok else "; the walk did not finish"))
    for l in real_errors[:20]:
        print("  ", l[:220])
    sys.exit(0 if ok and not real_errors else 1)


if __name__ == "__main__":
    main()
