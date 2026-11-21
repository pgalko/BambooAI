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
    """The run is over for the page: the closing card is up, the `end` event has been handled (the snapshot
    saved) and the chain is in responses[]."""
    wait_text(page, ".sp-done", "Run complete", timeout)
    page.wait_for_function("(n) => typeof queryRunning !== 'undefined' && !queryRunning && typeof responses !== 'undefined' && responses.length >= n",
                           arg=n_responses, timeout=timeout)
    page.wait_for_timeout(300)


def wait_text(page, selector, text, timeout=180000):
    page.wait_for_function("([sel, t]) => [...document.querySelectorAll(sel)].some(e => e.textContent.includes(t))",
                           arg=[selector, text], timeout=timeout)


def wait_position(page, text, timeout=180000):
    """A run's place among the runs the arrows step through, as the top bar says it: "3 of 3" - whole, since a chain's reads
    "chain 3 of 3" (docs/ROUTINES_DESIGN.md §23)."""
    page.wait_for_function("(t) => document.getElementById('chainPosition').textContent === t", arg=text, timeout=timeout)


def usage_rows(wa, edition, user):
    """The usage rows the logger wrote, read from outside the app: the stand-in's journal (hosted) or the SQLite file (local)."""
    if edition == "hosted":
        p = os.path.join(wa, "usage_rows.jsonl")
        return [json.loads(ln) for ln in open(p, encoding="utf-8")] if os.path.exists(p) else []
    import sqlite3
    c = sqlite3.connect(os.path.join(wa, "bambooai.sqlite")); c.row_factory = sqlite3.Row
    return [dict(r) for r in c.execute("select * from usage where bamboo_user_id = ?", (user,))]


# ---- the Architect (docs/ARCHITECT_DESIGN.md §2.11-§2.14): the helpers of its section ----
def brief_on_screen(page):
    """The Brief tab as the coach sees it: the step on screen of how many on its way and the name of the button to the map beside the arrows, the parts that hold something - a part with nothing in it has no line - and what can be changed; each line the brief
    rests on with its mark, the fact beside it and whether the fact is in red; each other explanation with what it would show, its box - ticked, unticked or none - and who brought it in; the one
    control that adds a part, with its list while that is open; the line of what a run on data always tests; what Start analysis reads."""
    return page.evaluate("""() => { const r = document.querySelector('#content-brief .ar-brief'); if (!r) return null;
        const line = p => { const l = r.querySelector('.ar-line[data-path="' + p + '"] .tx'); return l ? l.textContent : null; };
        const text = c => (r.querySelector(c) || {}).textContent || '';
        const anchor = l => { const t = l.querySelector('.tx').cloneNode(true), f = t.querySelector('.fact'), m = l.querySelector('.mk'); if (f) f.remove();
            return [t.textContent, m ? m.title : '', f ? f.textContent : '', !!(f && f.classList.contains('no'))]; };
        return { state: r.dataset.state, v: text('.ar-ver b'), label: text('.ar-ver .k'), map: (r.querySelector('.ar-ver [data-ar="map"]') || {}).title || '', title: text('h1 .tx'), asked: text('.ar-top .label'), gets: text('.ar-gets'),
                 heads: [...r.querySelectorAll('h3')].map(h => h.textContent), always: text('.ar-always'), add: text('[data-ar="more"]'),
                 kinds: [...r.querySelectorAll('.ar-kinds [data-ar="add"]')].map(k => k.textContent),
                 decision: line('decision'), thinks: line('thinks'), rests: line('rests_on.0'), expects: line('expects'), would: line('would_change'),
                 anchors: [...r.querySelectorAll('.ar-line[data-path^="rests_on."]')].map(anchor),
                 rivals: [...r.querySelectorAll('.ar-line[data-path^="also_check."]')].map(l => { const a = anchor(l), box = l.querySelector('.tick'), by = l.querySelector('.src');
                     return [a[0], a[2], box ? (box.classList.contains('on') ? 'ticked' : 'unticked') : '', by ? by.textContent : '']; }),
                 compare: line('fixed.comparison'), measure: line('fixed.measure'), period: line('fixed.period'), pens: r.querySelectorAll('.pen').length, start: text('[data-ar="start"]'),
                 changed: [...r.querySelectorAll('.ar-line.changed')].map(l => l.dataset.path || 'builds'), versions: JSON.parse(r.dataset.framing).versions.length }; }""")


def brief_type(page, path, text):
    """Change one line of the brief as a coach does - its pencil, or + Add and the part's name where the brief does not show the part - type, Enter - and wait for the version the server makes
    of it."""
    n = page.evaluate("() => JSON.parse(document.querySelector('#content-brief .ar-brief').dataset.framing).versions.length")
    pen = f'#content-brief .ar-line[data-path="{path}"] [data-ar="edit"]'
    if page.locator(pen).count():
        page.click(pen)
    else:
        page.click('#content-brief [data-ar="more"]')
        page.click(f'#content-brief .ar-kinds [data-ar="add"][data-path="{path}"]')
    page.fill("#content-brief .ar-input", text)
    page.keyboard.press("Enter")
    page.wait_for_function("(n) => { const r = document.querySelector('#content-brief .ar-brief'); return r && JSON.parse(r.dataset.framing).versions.length === n + 1 && !r.querySelector('.editing'); }",
                           arg=n, timeout=15000)


def talk_on_screen(page, within="#streamOutput"):
    """The conversation as the coach sees it: who said what, the choices on offer, the buttons to the Architect's prompts, and the rows that say the question was updated, and at which step -
    each with what stands above it and under it."""
    return page.evaluate("""(within) => { const s = document.querySelector(within);
        const words = m => { const c = m.cloneNode(true); c.querySelectorAll('.who, .ar-choices').forEach(x => x.remove()); return c.textContent; };
        const cls = x => x ? x.className : '';
        return { said: [...s.querySelectorAll('.ar-msg')].map(m => [m.classList.contains('arch') ? 'Architect' : 'You', words(m)]), choices: [...s.querySelectorAll('.ar-choice')].map(c => c.textContent),
                 notes: [...s.querySelectorAll('.sp-row.tool.read')].filter(r => /^(QUESTION|BRIEF)$/.test(r.children[1].textContent))
                     .map(r => [...r.children].slice(1).map(c => c.textContent).concat([cls(r.previousElementSibling), cls(r.nextElementSibling)])),
                 waiting: !!s.querySelector('.ar-msg.wait'), prompts: s.querySelectorAll('.ar-msg.arch .sp-prompt').length }; }""", within)


def conversation_map(page):
    """A map as the person sees it in the drawer - the Brief map (docs/ARCHITECT_DESIGN.md §2.25), the Analysis map, the Workflow map: whether it is open, its name and what the head says
    is on it; each box - what it says and what stands under that -, which box is the open one, which are lit and not faint; what the drawer's foot says, with its rows; how many of the
    Workflow map's own marks it has, and whether the thread's buttons are in view. And the head (0324): which mark is shown, the buttons by their names, whether mark, name, counts and
    buttons stand in that order on the head's middle line, how many of the buttons stand on the map, and whether the foot's line is the quiet one."""
    return page.evaluate("""() => { const d = document.getElementById('workflowMapModal'), boxes = [...d.querySelectorAll('.wf-node')];
        const nth = keep => boxes.map((x, i) => keep(x) ? i + 1 : 0).filter(Boolean);
        return { open: getComputedStyle(d).display !== 'none', title: d.querySelector('h2').textContent, sub: document.getElementById('mapDrawerSub').textContent,
                 boxes: boxes.map(x => [x.querySelector('.wf-node-label').textContent, x.querySelector('.wf-node-chain').textContent]),
                 on: nth(x => x.classList.contains('wf-node--active')), lit: nth(x => parseFloat(getComputedStyle(x).opacity) === 1),
                 says: document.getElementById('nodeTaskContent').textContent, rows: [...d.querySelectorAll('#nodePlotPreview .wf-info-row')].map(r => [...r.children].map(c => c.textContent)),
                 thread: d.querySelectorAll('.wf-node-made, .wf-node-map, .wf-edge-label').length, buttons: getComputedStyle(d.querySelector('.map-drawer-foot')).display !== 'none',
                 head: (() => { const box = e => e.getBoundingClientRect(), h = box(d.querySelector('.map-drawer-head')), marks = [...d.querySelectorAll('.map-drawer-icon')].filter(e => getComputedStyle(e).display !== 'none');
                     const tools = [...d.querySelectorAll('.map-drawer-tools button')], parts = marks.concat([d.querySelector('h2'), document.getElementById('mapDrawerSub')], tools);
                     return { mark: marks.map(e => e.classList.contains('tree') ? 'tree' : 'branch').join(), names: tools.map(b => b.getAttribute('aria-label')),
                              line: parts.every(e => box(e).width > 0 && box(e).top >= h.top && box(e).bottom <= h.bottom && Math.abs(box(e).top + box(e).height / 2 - (h.top + 22)) <= 2),
                              order: parts.every((e, i) => i === 0 || box(e).left >= box(parts[i - 1]).right),
                              on_map: [...d.querySelectorAll('.wf-zoom-controls, .wf-fullscreen-btn')].filter(e => d.querySelector('.workflow-body').contains(e)).length,
                              quiet: !!d.querySelector('#nodeTaskContent .map-rest') }; })() }; }""")


def map_head(mark):
    """The drawer's head as every map has it (0324), with the mark that is the map's own: the rail's for the Workflow map, the Git branch for the other two."""
    return {"mark": mark, "names": ["Zoom out", "Zoom in", "Fit to the frame", "Full screen", "Close"], "line": True, "order": True, "on_map": 0, "quiet": True}


def steps_of(framing):
    """The steps of a framing on the record, each as its number, the step it follows, the version in use at its end, the versions it made and how many turns are its own."""
    return [(x["k"], x["from"], x["v"], x["made"], x["turns"]) for x in framing.get("steps", [])]


def architect_said(page, n):
    """Wait until the Architect has replied n times in the brief on screen and the composer is the coach's again."""
    page.wait_for_function("(n) => document.querySelectorAll('#streamOutput .sp-stream > .ar-msg.arch:not(.wait)').length === n && !document.getElementById('queryInput').disabled", arg=n, timeout=30000)


def tell(page, text=None, choice=None, replies=1):
    """Say something to the Architect as a coach does - type it and send it, or click a choice - and wait for its reply:
    two of them where it has the data looked up and goes on."""
    n = page.evaluate("() => document.querySelectorAll('#streamOutput .sp-stream > .ar-msg.arch:not(.wait)').length")
    if choice is not None:
        page.click(f"#streamOutput .ar-choice >> nth={choice}")
    else:
        page.fill("#queryInput", text)
        page.click("#submitQuery")
    architect_said(page, n + replies)


def month_queries(page):
    """The queries the account has used this month, as the app reports them: the hosted stand-in counts them, the self-hosted edition counts none."""
    return page.evaluate("async () => { const r = await window.authService.fetch('/api/monthly-usage'); const d = await r.json(); return (d.data || {}).queries_used || 0; }")


def composer(page):
    return page.evaluate("""() => { const q = document.getElementById('queryInput'); return { locked: q.disabled, placeholder: q.placeholder, send: document.getElementById('submitQuery').disabled,
        framing: document.body.classList.contains('ar-framing'), save: getComputedStyle(document.getElementById('saveButton')).display, position: document.getElementById('chainPosition').textContent }; }""")


def left_pane(page):
    """The left pane as the person sees it, with a turn gone back to or without (docs/BRANCH_DESIGN.md §5): the numbered turn cards in sight - each with whether
    the chain kept it from another -, how many cards the pane holds, the rows of hints in sight, whether the closing card is; the composer - the row of the turn
    gone back to, its words, and whether the files' menu, the mode and the Architect's switch are in sight; the turn the page stands at; the arrows' count; the
    number on the Analysis map's button; how long the tabs' markup is, and the answer's text."""
    return page.evaluate("""() => { const vis = e => !!e && getComputedStyle(e).display !== 'none' && e.offsetParent !== null;
        const s = document.querySelector('#streamOutput .sp-stream'), cards = [...s.querySelectorAll(':scope > .sp-turn[data-turn]')];
        return { turns: cards.filter(e => /^\\d+$/.test(e.getAttribute('data-turn')) && vis(e)).map(e => [Number(e.getAttribute('data-turn')), e.classList.contains('kept')]),
                 cards: cards.length, hidden: cards.filter(e => !vis(e)).length, hints: [...s.querySelectorAll(':scope > .sp-hint')].filter(vis).map(e => e.textContent), done: vis(s.querySelector('.sp-done')),
                 chip: (document.getElementById('branchChip') || {}).textContent || '', words: document.getElementById('queryInput').placeholder,
                 controls: ['.attach-menu-container', '#modeSliderPopup', '#architectSwitch'].map(q => vis(document.querySelector('.left-panel ' + q))),
                 standing: BranchUI.standing(), position: document.getElementById('chainPosition').textContent, badge: (s.parentNode.querySelector('.sp-turnmap .n') || {}).textContent || '',
                 tabs: document.getElementById('contentOutput').innerHTML.length, answer: ((document.querySelector('#content-answer .markdown-content') || {}).textContent || '').length }; }""")


def open_turn_map(page):
    """The Analysis map of the analysis on screen, opened with the button on the left pane's strip, as the person sees it."""
    page.click("#streamOutput .sp-turnmap")
    page.wait_for_function("() => getComputedStyle(document.getElementById('workflowMapModal')).display !== 'none' && document.getElementById('workflowMapModal').classList.contains('turns')", timeout=10000)
    page.wait_for_timeout(200)
    return conversation_map(page)


def turn_box(page, keep):
    """Click the Analysis map's first box that `keep` - a JS test of (its second line, its mark) - says yes to."""
    page.evaluate("(keep) => { const f = eval(keep); [...document.querySelectorAll('#workflowMapModal .wf-node')].find(x => f(x.querySelector('.wf-node-chain').textContent, "
                  "(x.querySelector('.wf-node-made') || {}).textContent || '')).click(); }", keep)
    page.wait_for_timeout(300)


def thread_run(wa, user, thread_id, run_id):
    path = os.path.join(wa, "storage", user, "threads", f"{thread_id}.json")
    return (json.load(open(path, encoding="utf-8"))["runs"] if os.path.exists(path) else {}).get(str(run_id)) or {}


def walk_architect(page, st, mod, wa, edition, user):
    """A question typed with the Architect on opens its brief and runs nothing. The Architect fills the brief from the question
    and asks for what is missing, one question a message; the coach answers with a click or in words, and adds lines by hand.
    With nothing left to ask the Architect has the data looked up and marks what the brief rests on: a line that does not
    hold (the planted false premise), one that holds, one that cannot be checked. With the marks it proposes another
    explanation, which the coach ticks. The coach keeps the view, asks for a change in words, and changes lines by hand;
    the arrows go through the steps of the conversation, and both panes show the one on screen.
    Start analysis runs the same chain under the brief. First with a measure the
    data does not have: the analyst stops and asks. The answer, typed with the switch still on, opens a brief that starts from
    the last one; the Architect takes the answer into it, the analysis runs, and its report says how the result stands
    against the brief."""
    page.evaluate("handleNewConversation()")
    page.wait_for_url("**/?new=true", timeout=60000)
    page.wait_for_selector("#queryInput", state="visible", timeout=60000)
    page.app_ready()
    page.wait_for_function("() => /Ready|Local|Docker/.test(document.querySelector('#containerStatusText').textContent)", timeout=60000)
    page.set_input_files("#primaryFile", st.dataset)
    page.wait_for_selector(".primary-dataset-pill", timeout=60000)
    page.wait_for_timeout(500)
    rows0 = len(usage_rows(wa, edition, user))
    own = page.evaluate("() => document.getElementById('queryInput').placeholder")
    counted = [month_queries(page)]             # the month's queries, read as the section goes
    asks = [ask for _, ask in mod.ARCHITECT_ASKS]

    # the switch, then the question: its brief, the Architect's first turn, and nothing run
    off = page.evaluate("() => document.getElementById('architectSwitch').getAttribute('aria-pressed')")
    page.click("#architectSwitch")
    page.fill("#queryInput", mod.BRIEF_QUESTION)
    page.click("#submitQuery")
    page.wait_for_selector("#content-brief .ar-brief", timeout=15000)
    architect_said(page, 1)
    counted.append(month_queries(page))         # the brief opened
    b1, c1, t1 = brief_on_screen(page), composer(page), talk_on_screen(page)
    page.click('#content-brief [data-ar="more"]')
    kinds = brief_on_screen(page)["kinds"]
    page.click('#content-brief [data-ar="more"]')
    p1 = page.evaluate("""() => ({ strip: document.querySelector('#streamOutput .sp-strip').textContent, tabs: [...document.querySelectorAll('#tabContainer .tab')].map(t => t.textContent),
        on: document.getElementById('architectSwitch').getAttribute('aria-pressed'), n: responses.length, status: responses[0].status, running: queryRunning,
        typed: document.getElementById('queryInput').value, thread: currentData.thread_id, chain: currentData.chain_id })""")
    tid, cid = p1["thread"], p1["chain"]
    rec1 = thread_run(wa, user, tid, cid)
    new1 = usage_rows(wa, edition, user)[rows0:]
    check("the Architect's switch, off until it is pressed; a question typed with it on opens its brief and runs nothing: one tab - Brief - with the question as its title and, beside it, which step "
          "of the conversation is on screen: Step, 1 of 1, between its arrows, and after them the button to the conversation's map (0316) - the pane's strip names none. The Architect takes its first turn at once: it writes what the question states - the two regimes compared - as a version of its own, and "
          "asks the first thing missing, with the two courses the question names as choices. The brief shows the parts that hold something and no other - here what is compared; + Add opens the list "
          "of the parts not there, each under its plain name, and closes again; one line says what a run on data always tests",
          off == "false" and p1["on"] == "true" and re.fullmatch(r"Architect(\$\d+\.\d\d)?", p1["strip"]) and p1["tabs"] == ["Brief"] and p1["n"] == 1 and p1["status"] == "framing" and not p1["running"] and p1["typed"] == ""
          and t1["said"] == [["You", mod.BRIEF_QUESTION], ["Architect", asks[0]]] and t1["choices"] == ["Switch to regime C", "Keep regime A"] and not t1["waiting"] and t1["notes"] == []
          and b1["state"] == "framing" and (b1["label"], b1["v"], b1["map"]) == ("Step", "1 of 1", "Brief map") and b1["title"] == mod.BRIEF_QUESTION and b1["compare"] == "regime C against regime A"
          and b1["changed"] == ["fixed.comparison"] and [b1[k] for k in ("decision", "thinks", "expects", "would", "measure", "period")] == [None] * 6
          and b1["asked"] == "What the Analyst will be asked" and b1["gets"] == "This is what the Analyst gets. Change any line before you start."
          and b1["always"] == "Always tested on data: chance, measurement error, how the cases were chosen." and b1["heads"] == ["What is compared"] and (b1["add"], b1["kinds"]) == ("+ Add", [])
          and kinds == ["What it is for", "What you think", "Why you think so", "What you expect to see", "What would change your mind", "Another explanation to test", "Measured by", "Period"]
          and brief_on_screen(page)["kinds"] == [] and b1["start"] == "Start analysis", (off, p1, t1, b1, kinds))
    f1 = rec1.get("framing", {})
    check("the brief is a run on the thread's record before any analysis: status framing, the question, the versions - the Architect's saying it was made from the question - and the conversation, which is one step so far (0316): the question, "
          "with the Architect's first turn and the version it made; its one model call "
          "is on the usage record as the Architect's, under the brief's own chain; the composer is the conversation's, and there is nothing to save",
          rec1.get("status") == "framing" and rec1.get("question") == mod.BRIEF_QUESTION and rec1.get("turns") == [] and [(v["n"], v["by"], v.get("why")) for v in f1.get("versions", [])] == [(1, "person", None), (2, "architect", "question")]
          and [(t["who"], t["text"], t.get("choices"), t.get("call")) for t in f1.get("turns", [])] == [("architect", asks[0], ["Switch to regime C", "Keep regime A"], 1)] and f1.get("calls") == 1
          and steps_of(f1) == [(1, 0, 2, [1, 2], 1)] and (f1.get("step"), f1.get("tip")) == (1, 1)
          and [(r["agent"], str(r["chain_id"])) for r in new1] == [("Architect", str(cid))]
          and not c1["locked"] and not c1["send"] and c1["placeholder"] == "Answer, or say what to change" and c1["framing"] and c1["save"] == "none", (rec1.get("status"), f1, new1, c1))

    # the conversation: a choice clicked, an answer typed, two lines added by hand; the last answer, and the check against the data
    tell(page, choice=0)
    b2, t2 = brief_on_screen(page), talk_on_screen(page)
    because = "C does better than A because the C plots got the most rain."      # the planted false premise: the B plots got the most
    tell(page, because)
    b3 = brief_on_screen(page)
    rain, same, green = "The C plots got the most rain.", "Each regime has the same number of plots.", "The C plots looked greener last season."
    for text in (same, green):
        brief_type(page, "rests_on.+", text)
    expects = "C yields at least 0.3 t/ha more than A."
    tell(page, expects, replies=2)
    b4, t4 = brief_on_screen(page), talk_on_screen(page)
    row4 = page.evaluate("""() => { const rows = [...document.querySelectorAll('#streamOutput .sp-stream > *')], at = rows.findIndex(x => x.classList.contains('sp-row'));
        return { n: document.querySelectorAll('#streamOutput .sp-row').length, text: [...rows[at].children].map(c => c.textContent), title: rows[at].title,
                 before: rows[at - 1].className, saved: [...rows[at + 1].children].map(c => c.textContent), savedClass: rows[at + 1].className, after: rows[at + 2].className,
                 last: at + 2 === rows.length - 1 }; }""")
    rain_fact, same_fact = "total of rainfall_mm by regime: A 100,448 · B 102,189 · C 100,570", "rows by regime: A 240 · B 240 · C 240"
    not_held = f"One line does not hold: {rain.rstrip('.')} ({rain_fact.split(': ')[1]}). Keep what you think, or change it?"
    its = [mod.ARCHITECT_PROPOSES["text"], mod.ARCHITECT_PROPOSES["shows"]]
    check("a choice clicked is the coach's answer: it is said in the pane, written into the part that was asked for - which the brief now shows, under its name - as one more version, the exchange the conversation's second step - and the next "
          "question follows - one to a message, no choices where the question names none",
          t2["said"][2:] == [["You", "Switch to regime C"], ["Architect", asks[1]]] and t2["choices"] == [] and b2["v"] == "2 of 2"
          and b2["decision"] == "Switch to regime C" and b2["changed"] == ["decision"] and b2["heads"] == ["What it is for", "What is compared"], (t2, b2))
    check("an answer typed in the composer goes the same way, in the coach's words: what they think and what it rests on from one answer - a line not yet checked, with no mark",
          b3["v"] == "3 of 3" and b3["thinks"] == "C does better than A." and b3["rests"] == rain and b3["changed"] == ["thinks", "rests_on.0"] and b3["anchors"] == [[rain, "", "", False]], b3)
    check("with nothing left to ask the Architect checks what the brief rests on: it says so, the data is looked up - one row in the conversation, the two things looked up, what each found on hover - the "
          "saved analyses are read - a row of their own: the one that is saved holds nothing on this, so nothing is found and the brief gains nothing - and it goes on at once, with no word from the coach. The premise planted in the answer does not hold, and the brief shows it before any analysis: the mark, and in red the numbers the data gave; a line "
          "that holds has its fact too; a line nothing loaded records cannot be checked, and says why. The answer and all the Architect did with it are one step - the sixth: each line the coach added by hand was a step "
          "of its own - and the tab marks every line that step changed",
          b4["v"] == "6 of 6" and b4["changed"] == ["rests_on.0", "rests_on.1", "rests_on.2", "expects", "also_check.0"] and b4["expects"] == expects and b4["would"] is None
          and b4["anchors"] == [[rain, "does not hold", rain_fact, True], [same, "holds", same_fact, False], [green, "cannot be checked", mod.ARCHITECT_UNRECORDED, False]]
          and t4["said"] == [["You", mod.BRIEF_QUESTION], ["Architect", asks[0]], ["You", "Switch to regime C"], ["Architect", asks[1]], ["You", because], ["Architect", asks[2]], ["You", expects],
                             ["Architect", mod.ARCHITECT_CHECKING], ["Architect", not_held]] and t4["prompts"] == 5 and t4["choices"] == mod.ARCHITECT_KEEP and not t4["waiting"]
          and row4["n"] == 2 and row4["text"][:3] == ["✓", "CHECK data", "2 things looked up"] and re.fullmatch(r"\d+ s", row4["text"][3]) and row4["title"] == rain_fact + "\n" + same_fact
          and row4["savedClass"] == "sp-row tool read" and row4["saved"][:3] == ["✓", "MEMORY", "nothing found · 1 saved"] and re.fullmatch(r"\d+ s", row4["saved"][3])
          and row4["before"] == "ar-msg arch" and row4["after"] == "ar-msg arch" and row4["last"], (b4, t4, row4))
    tell(page, choice=0)
    b_kept, t_kept = brief_on_screen(page), talk_on_screen(page)
    check("the coach keeps the view: nothing in the brief changes - the line stays, with its mark that it does not hold; the exchange is a step that changed nothing, so the tab marks no line "
          "as changed - and the Architect says the brief is ready, and that what it proposed can be ticked",
          b_kept["v"] == "7 of 7" and b_kept["changed"] == [] and b_kept["anchors"] == b4["anchors"] and t_kept["said"][-2:] == [["You", "Keep it"], ["Architect", mod.ARCHITECT_READY + mod.ARCHITECT_TICK]] and t_kept["choices"] == []
          and t_kept["prompts"] == 6, (b_kept, t_kept))
    page.click('#content-brief .ar-line[data-path="also_check.0"] .tick')
    page.wait_for_function("() => { const r = document.querySelector('#content-brief .ar-brief'); return r && JSON.parse(r.dataset.framing).versions.length === 9; }", timeout=15000)
    b_tick = brief_on_screen(page)
    check("with its marks the Architect proposed another explanation, from a column the data has: in the brief as its own - its mark, what it would show - with an empty box, nothing accepted. The coach "
          "ticks it: one more version, theirs, the box ticked",
          b4["rivals"] == [its + ["unticked", "Architect"]] and b_kept["rivals"] == b4["rivals"]
          and b_tick["v"] == "8 of 8" and b_tick["changed"] == ["also_check.0"] and b_tick["rivals"] == [its + ["ticked", "Architect"]], (b4["rivals"], b_tick))
    tell(page, "The measure is protein content of the grain.")
    b5, t_measure = brief_on_screen(page), talk_on_screen(page)
    typed = [("would_change", "a gap under 0.1 t/ha"), ("also_check.+", "Rainfall differed between the C and A plots."), ("fixed.comparison", "regime C against regime A, within soil type")]
    for path, text in typed:
        brief_type(page, path, text)
    b9 = brief_on_screen(page)
    rec9 = thread_run(wa, user, tid, cid)
    f9 = rec9.get("framing", {})
    last = (f9.get("versions") or [{}])[-1]
    check("a change asked for in words is made, and no other; the coach's own changes follow by hand, a version and a step each, the last change marked - a part the brief did not show is added through "
          "+ Add - on top of what the Architect wrote",
          b5["v"] == "9 of 9" and b5["measure"] == "protein content of the grain" and b5["changed"] == ["fixed.measure"] and b5["decision"] == "Switch to regime C"
          and b5["expects"] == expects and b5["anchors"] == b4["anchors"] and b5["rivals"] == b_tick["rivals"] and t_measure["said"][-1] == ["Architect", mod.ARCHITECT_READY]
          and b9["v"] == "12 of 12" and b9["changed"] == ["fixed.comparison"] and b9["would"] == typed[0][1] and b9["compare"] == typed[2][1]
          and b9["rivals"] == [its + ["ticked", "Architect"], [typed[1][1], "", "", ""]]
          and b9["thinks"] == "C does better than A." and b9["measure"] == "protein content of the grain" and b9["period"] is None
          and re.fullmatch(r"Architect(\$\d+\.\d\d)?", page.inner_text("#streamOutput .sp-strip").replace("\n", "").replace(" ", "")), (b5, b9))
    arch_rows = [r for r in usage_rows(wa, edition, user)[rows0:]]
    counted.append(month_queries(page))         # seven exchanges later
    found9 = next((t.get("found", []) for t in f9.get("turns", []) if t["who"] == "check"), [])
    check("the record keeps every version with who made it and from what, the lines as the coach gave them with what the check found, and the conversation in order - the round of lookups a turn of its own, "
          "each lookup under its number with the line it was made for, the reading of the saved analyses after it; the steps of the conversation (0316) - an exchange each, with the versions it made and the turns that are its own, and each change by "
          "hand a step that holds no turn - one way, the last step in use; the run is still a brief - seven calls of the Architect's, the reader's two under the same chain, and none of the "
          "analyst's",
          rec9.get("status") == "framing"
          and [(v["by"], v.get("why")) for v in f9["versions"]] == [("person", None), ("architect", "question")] + [("architect", "answer")] * 2 + [("person", None)] * 2
                                                                    + [("architect", "answer"), ("architect", "check"), ("person", None), ("architect", "answer")] + [("person", None)] * 3
          and [v["changed"] for v in f9["versions"]][2:10] == [["decision"], ["thinks", "rests_on.0"], ["rests_on.1"], ["rests_on.2"], ["expects"], ["also_check.0", "rests_on.0", "rests_on.1", "rests_on.2"],
                                                               ["also_check.0"], ["fixed.measure"]]
          and last["brief"].get("also_check") == [{"text": its[0], "shows": its[1], "source": "architect", "accepted": True}, {"text": typed[1][1]}] and f9.get("proposed") == 1
          and last["brief"].get("rests_on") == [{"text": rain, "source": "person", "mark": "does not hold", "note": rain_fact}, {"text": same, "source": "person", "mark": "holds", "note": same_fact},
                                                {"text": green, "source": "person", "mark": "cannot be checked", "note": mod.ARCHITECT_UNRECORDED}]
          and last["brief"].get("fixed") == {"comparison": typed[2][1], "measure": "protein content of the grain"}
          and [t["who"] for t in f9["turns"]] == ["architect", "person"] * 3 + ["architect", "check", "memory", "architect", "person", "architect", "person", "architect"]
          and [(t["found"], t["across"], t["of"], t["read"], t["failed"]) for t in f9["turns"] if t["who"] == "memory"] == [([], None, 1, 0, "")]
          and found9 == [{"k": 1, "about": rain, "fact": rain_fact, "ran": True}, {"k": 2, "about": same, "fact": same_fact, "ran": True}]
          and [t.get("call") for t in f9["turns"] if t["who"] == "architect"] == [1, 2, 3, 4, 5, 6, 7] and f9.get("calls") == 7
          and steps_of(f9) == [(1, 0, 2, [1, 2], 1), (2, 1, 3, [3], 2), (3, 2, 4, [4], 2), (4, 3, 5, [5], 0), (5, 4, 6, [6], 0), (6, 5, 8, [7, 8], 5), (7, 6, 8, [], 2), (8, 7, 9, [9], 0),
                               (9, 8, 10, [10], 2), (10, 9, 11, [11], 0), (11, 10, 12, [12], 0), (12, 11, 13, [13], 0)] and (f9.get("step"), f9.get("tip")) == (12, 12) and "aside" not in f9
          and [(r["agent"], str(r["chain_id"])) for r in arch_rows] == [("Architect", str(cid))] * 4 + [("Memory Reader", str(cid))] * 2 + [("Architect", str(cid))] * 3,
          (rec9.get("status"), f9.get("versions"), f9.get("turns"), arch_rows))
    page.click('#content-brief [data-ar="step"][data-step="-1"]')
    b8 = brief_on_screen(page)
    for _ in range(3):                          # three more: the step where the coach ticked the box, before they named the measure
        page.click('#content-brief [data-ar="step"][data-step="-1"]')
    b_at8, t_at8 = brief_on_screen(page), talk_on_screen(page)
    for _ in range(4):
        page.click('#content-brief [data-ar="step"][data-step="1"]')
    t_end = talk_on_screen(page)
    page.click('#content-brief .ar-line[data-path="decision"] [data-ar="edit"]')
    page.fill("#content-brief .ar-input", "something else")
    page.keyboard.press("Escape")
    back = brief_on_screen(page)
    f_walked = thread_run(wa, user, tid, cid).get("framing", {})
    check("the arrows go through the steps of the conversation (0316): the one before shows the comparison as the Architect wrote it, with its pencils, the line that step changed marked, and "
          "Start analysis names the step - the analysis would start from the step on screen. Three steps further back, before the coach named the measure, both panes are that step's: the "
          "brief without the measure, the box just ticked, and the conversation up to there - its last message the Architect's word that the brief is ready, and nothing of what was said "
          "after. Stepping alone changes nothing on the record. Forward again to the last step the conversation is whole and the button names no step; Escape leaves a line as it was",
          b8["v"] == "11 of 12" and b8["compare"] == "regime C against regime A" and b8["pens"] > 0 and b8["start"] == "Start analysis from step 11" and b8["changed"] == ["also_check.1"]
          and (b_at8["v"], b_at8["measure"], b_at8["changed"], b_at8["start"]) == ("8 of 12", None, ["also_check.0"], "Start analysis from step 8") and b_at8["rivals"] == b_tick["rivals"]
          and t_at8["said"] == t_kept["said"] and len(t_at8["said"]) == len(t_measure["said"]) - 2 and t_end["said"] == t_measure["said"]
          and back["v"] == "12 of 12" and back["start"] == "Start analysis" and back["pens"] > 0 and back["decision"] == "Switch to regime C" and back["versions"] == 13
          and "at" not in f_walked and (f_walked.get("step"), f_walked.get("tip")) == (12, 12), (b8, b_at8, t_at8["said"][-2:], back, f_walked.get("step")))
    page.click("#streamOutput .sp-stream > .ar-msg.arch .sp-prompt")
    page.wait_for_function("() => { const u = document.getElementById('userInstructions'); return u && /CONVERSATION:/.test(u.textContent); }", timeout=15000)
    read = {"system": page.inner_text("#systemInstructions"), "user": page.inner_text("#userInstructions")}
    page.evaluate("() => { const m = document.getElementById('agentInstructionsModal'); if (m) m.style.display = 'none'; const u = document.getElementById('userInstructions'); if (u) u.textContent = ''; }")
    check("what the Architect read for its first message, through the message's button: its instructions, then the data's description, the question, the brief as it stood and the conversation - nothing yet",
          read["system"].startswith("You are the Architect.") and read["user"].startswith("DATA:\n") and ("QUESTION:\n" + mod.BRIEF_QUESTION + "\n\nBRIEF (version 1):\ndecision: (empty)") in read["user"]
          and "fixed.comparison: (empty)" in read["user"] and "CONVERSATION:\n(nothing yet)" in read["user"] and "EARLIER" not in read["user"], (read["system"][:80], read["user"][-500:]))

    # nothing else starts from a brief not yet run; its box on the Workflow map
    page.evaluate("handleQuerySubmit({ synthesis: true })")
    page.wait_for_timeout(300)
    held = page.evaluate("() => ({ running: queryRunning, n: responses.length, toast: document.getElementById('summaryContent').textContent })")
    page.evaluate("closePopup()")
    page.evaluate("showWorkflowMap()")
    page.wait_for_selector("#workflowMapModal .wf-node", timeout=10000)
    box = page.evaluate("""() => { const n = document.querySelector('#workflowMapModal .wf-node'); return { made: (n.querySelector('.wf-node-made') || {}).textContent, notrun: n.classList.contains('wf-node--notrun'),
        eye: !!n.querySelector('.wf-node-map'), nodes: document.querySelectorAll('#workflowMapModal .wf-node').length }; }""")
    page.evaluate("document.getElementById('workflowMapModal').style.display = 'none'")
    check("a brief not yet run: nothing else starts from it, and the page says so; on the Workflow map it is one box, marked 'not run', with no code map to open",
          not held["running"] and held["n"] == 1 and "This brief has not been run" in held["toast"] and box == {"made": "not run", "notrun": True, "eye": False, "nodes": 1}, (held, box))

    # Start analysis: the same chain runs under the brief - and stops on its question, the measure not being in the data
    page.click('#content-brief [data-ar="start"]')
    wait_text(page, ".sp-done", "The analyst has a question for you", 180000)
    page.wait_for_function("() => !queryRunning && responses.length === 1 && !responses[0].status", timeout=60000)
    page.wait_for_timeout(400)
    a1 = page.evaluate("""() => ({ n: responses.length, chain: responses[0].chain_id, first: document.querySelector('#streamOutput .sp-stream').firstElementChild.className,
        fold: document.querySelector('#streamOutput .ar-fold summary').textContent, tabs: [...document.querySelectorAll('#tabContainer .tab')].map(t => t.textContent),
        answer: (document.getElementById('content-answer') || {}).textContent || '', rows: [...document.querySelectorAll('#streamOutput .sp-row')].length,
        checked: document.querySelectorAll('#streamOutput .ar-fold .sp-detail .sp-row.tool.read').length,
        read: [...document.querySelectorAll('#streamOutput .ar-fold .sp-detail .sp-row.tool.read')].slice(-1).map(r => [r.className].concat([...r.children].map(c => c.textContent)))[0],
        cards: [...document.querySelectorAll('#streamOutput .sp-turn[data-turn]')].map(t => t.querySelector('summary .kind').textContent) })""")
    folded = talk_on_screen(page, "#streamOutput .ar-fold .sp-detail")
    counted.append(month_queries(page))         # its analysis started and ended
    c2 = composer(page)
    page.click("#tab-brief")
    kept = brief_on_screen(page)
    asked = thread_run(wa, user, tid, cid)
    prompt1 = turn_prompt(page, 1)
    check("Start analysis runs the brief's own chain - still one chain, under the same id - with the framing folded to one row above the run, which names the step the analysis started from - the thirteenth - the conversation inside it, to be read - its last row "
          "the question's check (0313): read before the analysis started, it stands on its own, and is that thirteenth step; the analyst, held to a measure the data does not have, puts nothing in its place: it looks, then asks",
          a1["n"] == 1 and str(a1["chain"]) == str(cid) and a1["first"] == "sp-turn ar-fold" and a1["fold"].startswith("Architectbrief · step 13") and a1["cards"] == ["cell", "question"]
          and len(folded["said"]) == 13 and folded["said"][0] == ["You", mod.BRIEF_QUESTION] and folded["said"][-1] == ["Architect", mod.ARCHITECT_READY] and folded["choices"] == [] and folded["prompts"] == 7
          and a1["checked"] == 3 and a1["read"][:4] == ["sp-row tool read", "✓", "CHECK question", "stands on its own"] and a1["read"][5:] == ["⌘"]
          and "the data records none" in a1["answer"] and "Shall I use yield?" in a1["answer"] and a1["tabs"][0] == "Brief" and "Answer" in a1["tabs"], (a1, folded))
    check("the analyst read the brief under the question - what was agreed, what each line it rests on is worth after the check, the explanation the coach ticked with what it would show beside their own, the "
          "parts that were fixed and no line for one that was not - through its own first turn's button, the Architect's calls counted apart; the run keeps the version it was started with, the question asked, every version of "
          "the framing, and the read of its question as the conversation's last turn (0313) - a step of its own, which the analysis started from (0316)",
          "QUESTION:\n" + mod.BRIEF_QUESTION + "\n\nBRIEF (agreed with the person before this run):\nWhat the answer is for: Switch to regime C\n" in prompt1
          and "Fixed before the run:\n- comparison: regime C against regime A, within soil type\n- measure: protein content of the grain\n\n" in prompt1 and "left to you" not in prompt1 and "not said" not in prompt1
          and f"What it rests on:\n- {rain} [checked against the data: does not hold - {rain_fact}]\n- {same} [checked against the data: holds - {same_fact}]\n- {green} [cannot be checked - {mod.ARCHITECT_UNRECORDED}]\n" in prompt1
          and f"Also check:\n- {its[0]}: it would show {its[1]}\n- Rainfall differed between the C and A plots.\n- chance [always]" in prompt1
          and asked.get("status") == "asked" and asked.get("brief", {}).get("version") == 13 and asked["brief"].get("fixed", {}).get("measure") == "protein content of the grain"
          and len(asked.get("framing", {}).get("versions", [])) == 13 and len(asked["framing"].get("turns", [])) == 15
          and {k: v for k, v in asked["framing"]["turns"][-1].items() if k not in ("secs", "cost")} == {"who": "reader", "missing": [], "v": 13, "call": 1} and asked["framing"].get("read") == [13]
          and steps_of(asked["framing"])[-1] == (13, 12, 13, [], 1) and (asked["framing"].get("step"), asked["framing"].get("tip")) == (13, 13)
          and [t["kind"] for t in asked.get("turns", [])] == ["cell", "ask"], (asked.get("status"), asked.get("brief"), prompt1[:400]))
    check("after the run the Brief tab stays, to be read: the step the analysis started from, no pencil, no Start analysis; the composer is the coach's own again, for the answer",
          kept["state"] == "run" and kept["v"] == "13 of 13" and kept["pens"] == 0 and not kept["start"] and kept["add"] == "" and kept["measure"] == "protein content of the grain" and kept["anchors"] == b4["anchors"]
          and kept["rivals"] == b9["rivals"]
          and not c2["locked"] and not c2["framing"]
          and c2["placeholder"] == own, (kept, c2))

    # the answer, typed with the switch still on: a brief of its own, from the last one, and the Architect takes the answer into it
    page.fill("#queryInput", mod.BRIEF_ANSWER)
    page.click("#submitQuery")
    wait_text(page, "#chainPosition", "chain 2 of 2", 15000)
    page.wait_for_selector('#content-brief .ar-brief[data-state="framing"]', timeout=15000)
    architect_said(page, 1)
    counted.append(month_queries(page))         # the answer's brief opened
    f2, t5 = brief_on_screen(page), talk_on_screen(page)
    cid2 = page.evaluate("() => currentData.chain_id")
    rec_f2 = thread_run(wa, user, tid, cid2)
    v2 = rec_f2.get("framing", {}).get("versions", [{}, {}])
    check("the coach's answer, typed with the switch on, opens a brief of its own under the analysis it answers: it starts from the last brief and says so, with the answer as its title. The Architect, which reads "
          "what the analyst asked, changes the part the answer settles - the measure - and nothing else, and says the brief is ready",
          f2["v"] == "1 of 1" and f2["title"] == mod.BRIEF_ANSWER and f2["decision"] == "Switch to regime C" and f2["expects"] == expects and f2["rivals"] == b9["rivals"]
          and f2["compare"] == typed[2][1] and f2["measure"] == "yield" and f2["changed"] == ["fixed.measure"] and f2["start"] and t5["said"] == [["You", mod.BRIEF_ANSWER], ["Architect", mod.ARCHITECT_READY]]
          and rec_f2.get("status") == "framing" and str(rec_f2.get("parent")) == str(cid) and v2[0].get("changed") == ["from the last brief"] and v2[0]["brief"]["fixed"]["measure"] == "protein content of the grain"
          and (v2[1].get("by"), v2[1].get("why")) == ("architect", "question"), (f2, t5, rec_f2.get("parent"), v2))
    page.click("#streamOutput .sp-stream > .ar-msg.arch .sp-prompt")
    page.wait_for_function("() => { const u = document.getElementById('userInstructions'); return u && /CONVERSATION:/.test(u.textContent); }", timeout=15000)
    read2 = page.inner_text("#userInstructions")
    page.evaluate("() => { const m = document.getElementById('agentInstructionsModal'); if (m) m.style.display = 'none'; const u = document.getElementById('userInstructions'); if (u) u.textContent = ''; }")
    check("on a follow-up the Architect is given the analyses the question follows: the first question, and that the analyst stopped and asked - with what it asked - then the answer as the question and the "
          "last brief as the one that stands",
          "EARLIER (the analyses this question follows, oldest first):\n[1] Q: " + mod.BRIEF_QUESTION + "\nThe analyst stopped and asked: The brief fixes the measure as protein content" in read2
          and "QUESTION:\n" + mod.BRIEF_ANSWER + "\n\nBRIEF (version 1):\ndecision: Switch to regime C\n" in read2 and "fixed.measure: protein content of the grain" in read2, read2[-900:])
    page.click("#prevResponse")
    wait_text(page, "#chainPosition", "chain 1 of 2", 10000)
    away = composer(page)
    page.click("#nextResponse")
    wait_text(page, "#chainPosition", "chain 2 of 2", 10000)
    page.wait_for_selector('#content-brief .ar-brief[data-state="framing"]', timeout=10000)
    again, home, t6 = brief_on_screen(page), composer(page), talk_on_screen(page)
    check("away from the brief and back with the arrows: on the first chain the composer is its own and the Save pill shows; back on the brief it is drawn again from its versions, with its conversation, and "
          "the composer is the conversation's",
          not away["locked"] and not away["framing"] and away["save"] != "none" and away["placeholder"] == own and not home["locked"] and home["framing"] and home["save"] == "none"
          and home["placeholder"] == "Answer, or say what to change" and again == f2 and t6 == t5, (away, home))
    page.evaluate("setMode('deep')")
    page.click('#content-brief [data-ar="start"]')
    wait_run_end(page, 2)
    page.wait_for_function("() => responses.length === 2 && !responses[1].status", timeout=60000)
    counted.append(month_queries(page))         # its analysis ran

    # the report against the brief: on the run's Brief tab, and not in the Answer (0312)
    rep = page.evaluate("""() => { const a = document.getElementById('content-answer'), tab = document.querySelector('#content-brief .ar-brief'), card = tab.querySelector('.ar-against');
        return { rows: card ? [...card.querySelectorAll('.r')].map(r => [r.querySelector('.k').textContent, r.querySelector('.t').textContent, r.querySelector('.v').textContent]) : null,
                 label: card ? card.querySelector('.label').textContent : null, heads: [...a.querySelectorAll('.markdown-content h2')].map(h => h.textContent),
                 cites: card ? card.querySelectorAll('.cite.cell').length : 0, text: a.querySelector('.markdown-content').textContent,
                 cards: [a.querySelectorAll('.ar-against').length, tab.querySelectorAll('.ar-against').length], last: tab.lastElementChild === card,
                 kept: (() => { const d = document.createElement('div'), told = x => JSON.stringify([...x.querySelectorAll('.r')].map(r => r.textContent)); d.innerHTML = tab.dataset.against || ''; return !!card && told(d) === told(card); })(),
                 raw: currentData.technicalAnswer || '',
                 done: [...document.querySelectorAll('.sp-done')].pop().textContent,
                 card: (() => { const c = [...document.querySelectorAll('.sp-done')].pop(), box = x => x.getBoundingClientRect(), t = c.querySelector('.head .title'), n = c.querySelector('.head .nums');
                     return { parts: [...c.children].map(x => x.className || x.tagName.toLowerCase()), title: t.textContent, nums: n.textContent, line: Math.abs(box(t).bottom - box(n).bottom) < 4, beside: box(n).left > box(t).right,
                              right: Math.abs(box(n).right - box(c.querySelector('.rep')).right) < 2, links: c.querySelectorAll('a').length,
                              buttons: [...c.querySelectorAll('.acts > button')].map(b => [b.textContent, b.className, getComputedStyle(b).borderTopStyle, Math.round(box(b).top)]) }; })(),
                 peek: [...document.querySelectorAll('#streamOutput .sp-row[data-cell] .out')].map(e => e.textContent).join(' | ') }; }""")
    nums = re.search(r"BRIEF_DIFF=(-?[\d.]+) BRIEF_LO=(-?[\d.]+) BRIEF_HI=(-?[\d.]+)", rep["peek"])
    d, lo, hi = (float(x) for x in nums.groups()) if nums else (None, None, None)
    want = None if d is None else ("met" if lo >= 0.3 else ("not met" if hi < 0.3 else "cannot tell"))
    seen = None if d is None else ("seen" if hi < 0.1 else ("not seen" if lo >= 0.1 else "cannot tell"))
    rows = rep["rows"] or []
    check("the report says how the result stands against the brief, and the page shows it as a card at the foot of the run's Brief tab, under How it turned out (0312; it stood in the answer): what "
          "was expected with its verdict - the one the kernel's interval gives against the 0.3 the coach expected - and what would change their mind; then a row for each Also check - the "
          "explanation the Architect proposed and the coach ticked, the coach's own, and the three standing ones - 'cannot tell' marked where the report says so; the cell citations stay chips. "
          "The rows ride in the brief's own markup",
          rep["label"] == "How it turned out" and rep["cards"] == [0, 1] and rep["last"] and rep["kept"] and len(rows) == 7 and rows[0][0] == "You expected" and rows[0][2] == want and f"{d:.3f}" in rows[0][1]
          and rows[1][0] == "Would change your mind" and rows[1][2] == seen and rows[2][0] == "Also checked" and rows[2][1].startswith(f"{its[0]}: the gap is ") and f"{d:.3f} within soil type" in rows[2][1]
          and rows[3][1].startswith("Rainfall differed between the C and A plots: mean rainfall was")
          and [r[0] for r in rows[3:]] == ["", "", "", ""] and [r[1].split(":")[0] for r in rows[4:]] == ["chance", "measurement error", "how the cases compared came to be chosen"]
          and [r[2] for r in rows[2:]] == ["", "", "", "cannot tell", ""] and rep["cites"] >= 4, (rows, want, seen, rep["peek"]))
    said = [r[1].split(":")[0] for r in rows[2:]]        # how each check's line opens: the words that would give the part away
    check("the answer is the analyst's own without the part (0312: the answer is what goes to other people): the opening says what the result means for the decision, Did not fit keeps its heading, "
          "and nothing of the part is left - no heading, no card, none of its lines - on the tab and in the copy the page keeps for the toggle",
          "For the decision - Switch to regime C - " in rep["text"] and "Did not fit" in rep["heads"] and "Against the brief" not in rep["heads"] and len(said) == 5
          and not any(x in rep["text"] or x in rep["raw"] for x in ["Against the brief", "How it turned out", "Would change their mind", "ar-against"] + [s + ":" for s in said])
          and "Replay reproduced" in rep["done"], (rep["heads"], rep["done"][:200], said, rep["text"][:600]))
    card = rep["card"]
    check("the closing card (0313, the product owner's choice of three mockups): its title, and on the same line, beside it and out to the card's right, the run's numbers - turns, cells, cost, time, a "
          "dot between each; then what was reproduced, the line that nothing was reached, and one row of what can be done next: Next questions and Code map, two buttons alike, side by side, in that "
          "order. No link to a tab and no arrow: the tabs are the way to the answer and to the brief",
          card["parts"][:4] == ["head", "rep ok", "reaches quiet", "acts"] and card["title"] == "Run complete" and bool(re.fullmatch(r"\d+(?: of \d+)? turns? · \d+ cells?(?: \([^)]*\))?(?: · \d+ plots?)? · \$\d+\.\d\d · (?:\d+ min )?[\d.]+ s", card["nums"]))
          and card["line"] and card["beside"] and card["right"] and card["links"] == 0 and "→" not in rep["done"] and "Simplified" not in rep["done"] and "Brief" not in rep["done"]
          and [b[0] for b in card["buttons"]] == ["Next questions", "Code map"] and [b[1] for b in card["buttons"]] == ["sp-act sp-next", "sp-act sp-codemap"]
          and [b[2] for b in card["buttons"]] == ["solid", "solid"] and card["buttons"][0][3] == card["buttons"][1][3], card)
    page.click("#tab-answer")
    page.wait_for_selector("#content-answer .simplified-summary-btn:not(.loading)", timeout=15000)
    page.evaluate("() => { window.__printed = []; window.print = () => { window.__printed.push(document.getElementById('pdf-print-container').textContent); }; }")
    printed = lambda n: (page.click("#content-answer .pdf-export-btn"), page.wait_for_function("(n) => window.__printed.length === n", arg=n, timeout=20000),      # noqa: E731
                         page.wait_for_function("() => !document.getElementById('pdf-print-container')", timeout=10000), page.evaluate("() => window.__printed[window.__printed.length - 1]"))[3]
    paper = printed(1)
    page.click("#content-answer .simplified-summary-btn")
    page.wait_for_function("() => currentData.summaryViewMode === 'simplified'", timeout=5000)
    plain = page.evaluate("() => ({ text: document.querySelector('#content-answer .content-body').textContent, cards: document.querySelectorAll('#content-answer .ar-against').length, "
                          "wrote: currentData.simplifiedAnswer || '', tab: document.querySelectorAll('#content-brief .ar-against .r').length })")
    paper_plain = printed(2)
    page.click("#content-answer .simplified-summary-btn")
    page.wait_for_function("() => currentData.summaryViewMode === 'technical'", timeout=5000)
    again = page.evaluate("() => ({ text: document.querySelector('#content-answer .content-body').textContent, cards: document.querySelectorAll('#content-answer .ar-against').length, "
                          "tab: document.querySelectorAll('#content-brief .ar-against .r').length })")
    gone = lambda text: not any(x in text for x in ["Against the brief", "How it turned out", "Would change their mind", "You expected"] + [s + ":" for s in said])      # noqa: E731
    check("the plain-language version is the answer without the part too (0312): the rewrite keeps the part under its heading, and the page cuts it where it shows the answer - no card, no heading, "
          "none of its lines; toggled back, the technical answer has none either, and the card on the Brief tab stood through both. What the PDF button hands the printer is the answer as its tab "
          "holds it, in either version: the report's opening, and not a word of the part",
          "## Against the brief" in plain["wrote"] and plain["cards"] == 0 and gone(plain["text"]) and "Did not fit" in plain["text"] and plain["tab"] == 7
          and again["cards"] == 0 and gone(again["text"]) and "For the decision - Switch to regime C - " in again["text"] and again["tab"] == 7
          and "For the decision - Switch to regime C - " in paper and gone(paper) and "Did not fit" in paper and gone(paper_plain) and "Did not fit" in paper_plain and paper != paper_plain,
          (plain["text"][:400], plain["wrote"][:300], again["text"][:200], paper[:400], paper_plain[:400]))
    page.click("#tab-brief")
    page.wait_for_function("() => document.getElementById('content-brief').classList.contains('active')", timeout=5000)
    ran2 = brief_on_screen(page)
    turned = lambda: page.evaluate("""() => { const r = document.querySelector('#content-brief .ar-brief'), c = r.querySelector('.ar-against');      // noqa: E731
        return [r.querySelector('.ar-ver b').textContent, c ? getComputedStyle(c).display : '', c ? c.querySelectorAll('.r').length : 0, !!r.dataset.against, c ? Math.round(c.getBoundingClientRect().width) > 300 : false]; }""")
    under2 = turned()
    chip = page.evaluate("""() => { const c = document.querySelector('#content-brief .ar-against .cite.cell'), s = c ? getComputedStyle(c) : null;
        return c ? [c.textContent, s.display, s.borderTopLeftRadius, s.borderTopStyle, s.cursor] : null; }""")
    page.click('#content-brief .ar-against .cite.cell')
    page.wait_for_selector("#codeMapModal .cm-diag .cm-node.result, #codeMapModal .cm-pane.step", timeout=15000)
    mapped = page.evaluate("() => ({ open: document.getElementById('codeMapModal').style.display === 'flex', kicker: (document.querySelector('#codeMapModal .cm-panel .cm-kicker span') || {}).textContent || '' })")
    page.keyboard.press("Escape")
    page.wait_for_function("() => document.getElementById('codeMapModal').style.display === 'none'", timeout=5000)
    page.click('#content-brief [data-ar="step"][data-step="-1"]')
    page.wait_for_function("() => document.querySelector('#content-brief .ar-ver b').textContent === '1 of 2'", timeout=5000)
    under1 = turned()
    page.click('#content-brief [data-ar="step"][data-step="1"]')
    page.wait_for_function("() => document.querySelector('#content-brief .ar-ver b').textContent === '2 of 2'", timeout=5000)
    check("the Brief tab after the run, read by the coach (0312): under the brief the analysis ran under, the card of how it turned out shows at the tab's foot, a grid across it. A citation "
          "in it is the chip it was in the answer - it looks like one, and a click opens the code map on its cell. The arrow back shows the step before - the last step was the question's "
          "read, which changed nothing - with the same brief, so the card stands under it too (0316); the arrow forward shows the last step again, from the tab's own markup",
          under2 == ["2 of 2", "grid", 7, True, True] and under1 == ["1 of 2", "grid", 7, True, True] and turned() == under2
          and bool(chip) and re.fullmatch(r"cell \d+", chip[0]) and chip[1:] == ["inline-block", "8px", "solid", "pointer"] and mapped["open"] and chip[0] in mapped["kicker"].lower(),
          (under2, under1, turned(), chip, mapped))
    done2 = thread_run(wa, user, tid, cid2)
    prompt2 = turn_prompt(page, 1)
    check("the Brief tab holds the brief the run was started with, to be read: the step it started from - the question's read, which changed no line - with the measure as the Architect changed "
          "it; the record keeps that version on the run, with what the report said against it and the one result it said did not fit",
          ran2["state"] == "run" and ran2["v"] == "2 of 2" and ran2["measure"] == "yield" and ran2["changed"] == [] and ran2["pens"] == 0 and not ran2["start"]
          and done2.get("status") == "answered" and done2.get("brief", {}).get("version") == 2 and done2["brief"]["fixed"]["measure"] == "yield"
          and done2.get("brief_outcome", {}).get("stated") is True and done2["brief_outcome"].get("expected") == want and done2["brief_outcome"].get("would_change") == seen
          and len(done2["brief_outcome"].get("checks", [])) == 5 and len(done2["brief_outcome"].get("did_not_fit", [])) == 1 and done2["brief_outcome"]["did_not_fit"][0].startswith(mod.NEXT_MISFIT + ": ")
          and "BRIEF (agreed with the person before this run):" in prompt2 and "- measure: yield\n" in prompt2, (ran2, done2.get("brief_outcome"), prompt2[:300]))

    # a chain kept before 0312: its answer holds the card, its Brief tab none - made here from the chain as the page keeps it, shown again, and put back as it was
    kept_old = page.evaluate("""async () => { const e = responses[currentResponseIndex], was = { contentOutput: e.contentOutput, technicalAnswer: e.technicalAnswer };
        const d = document.createElement('div'); d.innerHTML = e.contentOutput;
        const tab = d.querySelector('#content-brief .ar-brief'), card = tab.querySelector('.ar-against'), body = d.querySelector('#content-answer .markdown-content');
        const rows = () => [...document.querySelectorAll('#content-brief .ar-against .r')].map(r => r.querySelector('.t').textContent);
        const before = rows();
        card.querySelector('.label').textContent = 'Against the brief'; tab.removeAttribute('data-against');
        body.insertBefore(card, [...body.querySelectorAll('h2')].find(h => h.textContent === 'Did not fit'));
        e.contentOutput = d.innerHTML; e.technicalAnswer = body.outerHTML;
        const old = { answer: d.querySelectorAll('#content-answer .ar-against').length, tab: d.querySelectorAll('#content-brief .ar-against').length, rides: tab.hasAttribute('data-against') };
        loadResponseContent(e);
        await new Promise(r => setTimeout(r, 600));
        const a = document.getElementById('content-answer'), t = document.querySelector('#content-brief .ar-brief'), c = t.querySelector('.ar-against');
        const shown = { answer: a.querySelectorAll('.ar-against').length, text: a.querySelector('.markdown-content').textContent, raw: currentData.technicalAnswer || '', tab: t.querySelectorAll('.ar-against').length,
                        label: c ? c.querySelector('.label').textContent : '', last: t.lastElementChild === c, rides: t.hasAttribute('data-against'), same: JSON.stringify(rows()) === JSON.stringify(before),
                        chips: c ? c.querySelectorAll('.cite.cell').length : 0, heads: [...a.querySelectorAll('.markdown-content h2')].map(h => h.textContent) };
        Object.assign(e, was); loadResponseContent(e);
        await new Promise(r => setTimeout(r, 600));
        return { old, shown, back: [document.querySelectorAll('#content-answer .ar-against').length, rows().length, JSON.stringify(rows()) === JSON.stringify(before)] }; }""")
    check("a chain kept from before 0312, shown again: its answer held the card and its Brief tab none. The card leaves the answer - on the tab and in the copy kept for the toggle - and stands at the "
          "foot of the chain's Brief tab under How it turned out, its rows and their chips as they were, and rides in the brief's markup from then on; Did not fit keeps its place in the answer",
          kept_old["old"] == {"answer": 1, "tab": 0, "rides": False}
          and (kept_old["shown"]["answer"], kept_old["shown"]["tab"], kept_old["shown"]["label"], kept_old["shown"]["last"], kept_old["shown"]["rides"], kept_old["shown"]["same"]) == (0, 1, "How it turned out", True, True, True)
          and kept_old["shown"]["chips"] >= 4 and "Did not fit" in kept_old["shown"]["heads"] and "ar-against" not in kept_old["shown"]["raw"]
          and not any(x in kept_old["shown"]["text"] for x in ["Against the brief", "You expected", "Would change your mind"]) and kept_old["back"] == [0, 7, True], kept_old)
    # a closing card kept before 0313 - its numbers in a grid, a row of links with the code map's button last, the Next questions button under them - shown again, and put back
    kept_card = page.evaluate("""async () => { const e = responses[currentResponseIndex], was = e.streamOutput;
        const d = document.createElement('div'); d.innerHTML = e.streamOutput;
        const c = [...d.querySelectorAll('.sp-done')].pop(), chain = c.querySelector('.sp-codemap').dataset.chain, tele = c.querySelector('.sp-telemetry'), old = document.createElement('div');
        old.className = 'sp-done';
        old.innerHTML = '<div class="title">Run complete</div><div class="grid"><span>Turns <b>2</b></span><span>Cells <b>1</b></span><span>Cost <b>$0.05</b></span><span>Time <b>2.6 s</b></span></div>' +
            '<div class="rep ok">✓ Replay reproduced.</div><div class="reaches quiet"><span class="h">No reaches outside the data</span></div>' +
            '<div class="links"><a href="#">Answer →</a><a href="#">Brief →</a><a href="#">Simplified →</a><a href="#">Investigation →</a><button class="sp-codemap" data-chain="' + chain + '">Code map →</button></div>' +
            '<div class="nq-open"><button type="button" class="sp-next" data-nq="open" title="Questions that could follow this analysis">Next questions</button></div>';
        if (tele) old.appendChild(tele.cloneNode(true));
        c.replaceWith(old); e.streamOutput = d.innerHTML;
        loadResponseContent(e);
        await new Promise(r => setTimeout(r, 400));
        const now = [...document.querySelectorAll('#streamOutput .sp-done')].pop(), box = x => x.getBoundingClientRect(), t = now.querySelector('.head .title'), n = now.querySelector('.head .nums');
        const shown = { parts: [...now.children].map(x => x.className || x.tagName.toLowerCase()), links: now.querySelectorAll('a').length, arrows: /→/.test(now.textContent), nums: n ? n.textContent : '',
                        line: !!t && !!n && Math.abs(box(t).bottom - box(n).bottom) < 4 && box(n).left > box(t).right, chain: (now.querySelector('.acts .sp-codemap') || { dataset: {} }).dataset.chain === chain,
                        buttons: [...now.querySelectorAll('.acts > button')].map(b => [b.textContent, getComputedStyle(b).borderTopStyle, Math.round(box(b).top)]) };
        e.streamOutput = was; loadResponseContent(e);
        await new Promise(r => setTimeout(r, 400));
        return { shown, back: [...[...document.querySelectorAll('#streamOutput .sp-done')].pop().querySelectorAll('.acts > button')].map(b => b.textContent) }; }""")
    kc = kept_card["shown"]
    check("a closing card kept from before 0313, shown again, comes to today's shape: its title and its numbers on one line; no link and no arrow; one row of what can be done next - Next questions "
          "and Code map, two buttons alike, side by side, the code map's with its chain; the telemetry last",
          kc["parts"] == ["head", "rep ok", "reaches quiet", "acts"] + (["sp-telemetry"] if "sp-telemetry" in kc["parts"] else []) and kc["links"] == 0 and not kc["arrows"] and kc["line"] and kc["chain"]
          and kc["nums"].startswith("Turns 2") and [b[0] for b in kc["buttons"]] == ["Next questions", "Code map"] and [b[1] for b in kc["buttons"]] == ["solid", "solid"]
          and kc["buttons"][0][2] == kc["buttons"][1][2] and kept_card["back"] == ["Next questions", "Code map"], kept_card)

    # the Workflow map: one box to a question, each saying how it was made; a typed question with the switch off runs at once
    page.evaluate("showWorkflowMap()")
    page.wait_for_selector("#workflowMapModal .wf-node", timeout=10000)
    boxes = page.evaluate("() => [...document.querySelectorAll('#workflowMapModal .wf-node')].map(n => [(n.querySelector('.wf-node-made') || {}).textContent || '', n.classList.contains('wf-node--notrun'), !!n.querySelector('.wf-node-map')])")
    page.evaluate("document.getElementById('workflowMapModal').style.display = 'none'")
    page.click("#architectSwitch")
    page.fill("#queryInput", "How many plots are there?")
    page.click("#submitQuery")
    wait_text(page, "#chainPosition", "chain 3 of 3", 60000)
    wait_run_end(page, 3)
    plain = page.evaluate("""() => ({ tabs: [...document.querySelectorAll('#tabContainer .tab')].map(t => t.textContent), fold: !!document.querySelector('#streamOutput .ar-fold'), card: !!document.querySelector('#contentOutput .ar-against'),
        on: document.getElementById('architectSwitch').getAttribute('aria-pressed'), done: [...document.querySelectorAll('.sp-done')].pop().textContent })""")
    third = thread_run(wa, user, tid, page.evaluate("() => currentData.chain_id"))
    counted.append(month_queries(page))         # a plain question ran
    steps = [b - a for a, b in zip(counted, counted[1:])]
    by_chain = {}
    for r in usage_rows(wa, edition, user)[rows0:]:
        by_chain.setdefault(str(r["chain_id"]), []).append(r["agent"])
    check("the Workflow map: two questions, two boxes - an Architect run and its analysis share one - each marked Architect, each with its code map; the switch off again, a typed question runs at once, "
          "as before: no brief on the page or on the run. On the usage record each framed chain holds the Architect's calls, the one call that read its question before the analysis (0313) and its analysis' "
          "own, under the one chain; the plain one holds no call of the Architect's",
          boxes == [["Architect", False, True], ["Architect", False, True]] and plain["on"] == "false" and "Brief" not in plain["tabs"] and not plain["fold"] and not plain["card"]
          and "Brief" not in plain["done"] and third.get("status") == "answered" and third.get("brief") == {} and third.get("framing") == {}
          and by_chain.get(str(cid), [])[:10] == ["Architect"] * 4 + ["Memory Reader"] * 2 + ["Architect"] * 3 + ["Question check"] and "Architect" not in by_chain.get(str(cid), [])[9:]
          and "Question check" not in by_chain.get(str(cid), [])[10:] and len(by_chain.get(str(cid), [])) > 10
          and by_chain.get(str(cid2), [])[:2] == ["Architect", "Question check"] and "Architect" not in by_chain.get(str(cid2), [])[1:] and len(by_chain.get(str(cid2), [])) > 2
          and all("Architect" not in v for k, v in by_chain.items() if k not in (str(cid), str(cid2))), (boxes, plain, third.get("brief"), by_chain))
    check("a framed question is one query of the month's: counted when its brief opens - not at each exchange with the Architect, and not again when its analysis starts; a plain question counts when it runs "
          "(the self-hosted edition counts none)",
          steps == ([1, 0, 0, 1, 0, 1] if edition == "hosted" else [0] * 6), (counted, steps))
    walk_next_questions(page, mod, wa, edition, user, tid, cid2)
    return tid, cid2


# ---- next questions (docs/ARCHITECT_DESIGN.md §2.7, §2.15): the helpers of its section ----
def sets_on_screen(page):
    """The sets of next questions in the closing card's panel, as the coach sees them: each set's way, whether it is among those shown, the line under it and whether that has the button to its
    prompt, and each question's row: what it starts from, the lines behind that (the label's title), its title, its question, and the chain its mark opens once it was run."""
    return page.evaluate("""() => [...document.querySelectorAll('#streamOutput .sp-done .nq-panel .nq-sets > .nq-set')].map(s => ({ at: s.dataset.set, level: s.dataset.level,
        shown: getComputedStyle(s).display !== 'none' && s.getBoundingClientRect().height > 0, foot: (s.querySelector('.nq-foot span') || {}).textContent || '', prompt: !!s.querySelector('.nq-foot .sp-prompt'),
        cards: [...s.querySelectorAll('.nq-card')].map(c => ({ from: c.querySelector('.from .l').textContent, lines: c.querySelector('.from').title, title: (c.querySelector('.tx b') || {}).textContent || '',
            q: c.querySelector('.q').textContent, ran: c.classList.contains('ran') ? c.querySelector('.was').dataset.chain : '' })) }))""")


def panel_on_screen(page):
    """The Next questions panel as the coach sees it: how many there are, whether it is open, in the closing card under its row of buttons and within the card's box; what it shows - the list (its
    heading, its line of what the questions are, a row for each way: key, name, sentence, how many questions it has) or the questions of one way (the way back, the way's name and sentence, the button
    for more)."""
    return page.evaluate("""() => { const all = document.querySelectorAll('#streamOutput .nq-panel'), p = all[0], text = s => (p.querySelector(s) || {}).textContent || '';
        if (!p) return { n: 0 };
        const card = p.closest('.sp-done'), box = p.getBoundingClientRect(), around = card ? card.getBoundingClientRect() : null;
        return { n: all.length, open: getComputedStyle(p).display !== 'none' && box.height > 0, show: p.dataset.show, under: !!card && p.previousElementSibling === card.querySelector('.acts'),
            within: !!around && box.left >= around.left && box.right <= around.right && box.bottom <= around.bottom, head: text('.nq-ph .t'), what: text('.nq-what'), back: text('.nq-back'),
            way: [...p.querySelectorAll('.nq-lv b, .nq-lv span')].map(x => x.textContent), more: text('.nq-more'),
            rows: [...p.querySelectorAll('.nq-row')].map(r => [r.dataset.level, r.querySelector('b').textContent, r.querySelector('span').textContent, (r.querySelector('.n') || {}).textContent || '']) }; }""")


NEXT_WAYS = [["refine", "Refine focus", "Stay with the same question and look closer: a smaller group, a shorter period, a stricter measure."],
             ["shift", "Shift angle", "Ask whether something else explains the result, and put that to the test."],
             ["test", "Test boundaries", "Check what the result stands on, and find where it stops being true."],
             ["blend", "Blend elements", "Bring two findings together in one question, such as this result and an earlier one."],
             ["emergence", "Follow emergence", "Go after what did not fit: the things this analysis could not explain."]]


def walk_next_questions(page, mod, wa, edition, user, tid, cid2):
    """A finished analysis carries a Next questions button on its closing card: it opens a panel in the card - what the questions are, and the five ways to go, a sentence each. A way picked brings
    up to five questions in the list's place, each from a line the analysis left - the way's own lines first: at Follow emergence the misfit the report planted, at Test boundaries the lines the
    brief rests on that did not hold or could not be checked. The list again says how many questions a way has, and that way shows them with no call; more of a way are written on request. A
    question is changed and run with the Architect's switch on: a new analysis at once, under the one it follows, with no brief; its row is marked, and its box on the map says how it was made."""
    rows0, month0 = len(usage_rows(wa, edition, user)), month_queries(page)
    bare = lambda s: {k: v for k, v in s.items() if k != "shown"}
    page.click("#prevResponse")
    wait_text(page, "#chainPosition", "chain 2 of 3", 10000)
    page.wait_for_selector('#streamOutput .sp-done [data-nq="open"]', timeout=10000)
    card = page.evaluate("""() => ({ buttons: [...document.querySelectorAll('#streamOutput [data-nq="open"]')].map(b => b.textContent), inCard: !!document.querySelector('#streamOutput .sp-done .acts > .sp-next:first-child'),
        plant: !!document.getElementById('suggestQuestions'), list: !!document.getElementById('nextLevels'), panels: document.querySelectorAll('#streamOutput .nq-panel').length,
        tab: document.querySelector('#tabContainer .tab.active').textContent })""")
    page.click('#streamOutput [data-nq="open"]')
    page.wait_for_selector("#streamOutput .sp-done .nq-panel .nq-row", state="visible", timeout=5000)
    opened = panel_on_screen(page)
    page.click('#streamOutput .nq-panel [data-nq="shut"]')
    crossed = panel_on_screen(page)
    page.click('#streamOutput [data-nq="open"]')
    page.wait_for_selector("#streamOutput .nq-panel .nq-row", state="visible", timeout=5000)
    page.click('#streamOutput [data-nq="open"]')
    shut = panel_on_screen(page)
    page.click('#streamOutput [data-nq="open"]')
    page.wait_for_selector("#streamOutput .nq-panel .nq-row", state="visible", timeout=5000)
    check("the plant has left the composer: a finished analysis carries one Next questions button, first in its closing card's row of what can be done next. It opens one panel in the card, under that "
          "row and within the card's box - nothing drops over the page: a heading, a line of what the questions are, and the five ways to go, each a name and a sentence. Its cross shuts it, and so "
          "does the button; the button opens it again",
          card["buttons"] == ["Next questions"] and card["inCard"] and not card["plant"] and not card["list"] and card["panels"] == 0
          and (opened["n"], opened["open"], opened["show"], opened["under"], opened["within"]) == (1, True, "list", True, True) and opened["head"] == "Where do you want to go from here?"
          and opened["what"].startswith("Up to five questions that could follow this analysis.") and opened["rows"] == [w + [""] for w in NEXT_WAYS] and not opened["back"] and not opened["more"]
          and (crossed["n"], crossed["open"]) == (1, False) and (shut["n"], shut["open"]) == (1, False) and panel_on_screen(page) == opened, (card, opened, crossed, shut))

    # a way picked: its questions in the list's place, each from a line of the record - the way's own first
    done = thread_run(wa, user, tid, cid2)
    misfit = (done.get("brief_outcome", {}).get("did_not_fit") or [""])[0]
    wide = re.search(r"t/ha on (\w+),", misfit)
    page.click('#streamOutput .nq-row[data-level="emergence"]')
    page.wait_for_selector('#streamOutput .nq-panel .nq-set[data-set="0"] .nq-card', timeout=20000)
    s0, p0 = sets_on_screen(page), panel_on_screen(page)
    after0 = page.evaluate("""() => ({ tab: document.querySelector('#tabContainer .tab.active').textContent, loose: document.querySelectorAll('#streamOutput .sp-stream > .nq-set').length,
        heads: document.querySelectorAll('#streamOutput .nq-head').length })""")
    first = s0[0]["cards"][0] if s0 and s0[0]["cards"] else {}
    check("Follow emergence: five questions in the panel, in the list's place, the answer's side of the page as it was: over them the way back to the list and the way's name and sentence, under "
          "them how many there are, the button to what the Architect read, and Write more. The first comes from the misfit the report planted - the gap by soil, which the coach's frame does not "
          "explain: its row says From what did not fit, the report's own line behind the label, and asks about the soil where the gap is widest; the others come from the other lines of the brief "
          "and the report, each saying which",
          len(s0) == 1 and s0[0]["level"] == "emergence" and s0[0]["shown"] and s0[0]["prompt"] and re.fullmatch(r"5 questions( · \$\d+\.\d\d)?", s0[0]["foot"]) and len(s0[0]["cards"]) == 5
          and (p0["n"], p0["open"], p0["show"], p0["within"], p0["back"], p0["way"], p0["more"], p0["rows"], p0["head"]) == (1, True, "emergence", True, "‹ All five", NEXT_WAYS[4][1:], "Write more", [], "")
          and misfit.startswith(mod.NEXT_MISFIT) and wide is not None and first.get("from") == "From what did not fit" and first.get("lines") == misfit
          and first.get("q") == f"Is regime C above regime A on {wide.group(1)} alone, on plot means of yield?" and first.get("title") == f"The {wide.group(1)} plots"
          and [c["from"] for c in s0[0]["cards"][1:]] == ["From what was compared", "From the measure", "From what was also checked", "From what was also checked"]
          and all(c["lines"] and not c["ran"] for c in s0[0]["cards"]) and after0 == {"tab": card["tab"], "loose": 0, "heads": 0}, (s0, p0, misfit, after0))
    page.click('#streamOutput .nq-panel [data-nq="list"]')
    page.wait_for_selector('#streamOutput .nq-row[data-level="test"]', state="visible", timeout=5000)
    listed, hidden = panel_on_screen(page), [s["shown"] for s in sets_on_screen(page)]
    page.click('#streamOutput .nq-row[data-level="test"]')
    page.wait_for_selector('#streamOutput .nq-panel .nq-set[data-set="1"] .nq-card', timeout=20000)
    s1, p1 = sets_on_screen(page), panel_on_screen(page)
    rests = [c for c in (s1[1]["cards"] if len(s1) > 1 else []) if c["from"] == "From what it rests on"]
    check("the list again: the way that has questions says how many, the questions themselves out of sight. Test boundaries, a second set, shown in the first one's place: its questions come first "
          "from what the brief rests on - the premise that did not hold, with the numbers the data gave, and the line that could not be checked, with why - then from what would change the coach's "
          "mind; no question of the first set is asked again",
          listed["show"] == "list" and listed["rows"] == [w + (["5 questions"] if w[0] == "emergence" else [""]) for w in NEXT_WAYS] and hidden == [False]
          and len(s1) == 2 and bare(s1[0]) == bare(s0[0]) and [s["shown"] for s in s1] == [False, True] and s1[1]["level"] == "test" and len(s1[1]["cards"]) == 5
          and (p1["n"], p1["show"], p1["way"], p1["within"]) == (1, "test", NEXT_WAYS[2][1:], True)
          and [c["from"] for c in s1[1]["cards"][:3]] == ["From what it rests on", "From what it rests on", "From what would change your mind"]
          and len(rests) == 2 and rests[0]["lines"].startswith("The C plots got the most rain. (does not hold: total of rainfall_mm by regime: ")
          and rests[1]["lines"].endswith(f"(cannot be checked: {mod.ARCHITECT_UNRECORDED})") and rests[1]["q"].startswith("Does the answer change without this: ")
          and not {c["q"] for c in s1[1]["cards"]} & {c["q"] for c in s0[0]["cards"]}, (listed, hidden, s1[1:], p1))
    page.click('#streamOutput .nq-set[data-set="1"] .nq-foot .sp-prompt')
    page.wait_for_function("() => { const u = document.getElementById('userInstructions'); return u && /SOURCES:/.test(u.textContent); }", timeout=15000)
    read, instructions = page.inner_text("#userInstructions"), page.evaluate("() => document.getElementById('systemInstructions').textContent")
    page.evaluate("() => { const m = document.getElementById('agentInstructionsModal'); if (m) m.style.display = 'none'; const u = document.getElementById('userInstructions'); if (u) u.textContent = ''; }")
    check("what the Architect read for the second set, through the button under it: its instructions for next questions, then the data, the analyses before, the question, the report whole, the brief "
          "as the analyst received it, the questions proposed before, the level, and the lines numbered - what the brief rests on first, then the others",
          instructions.lstrip().startswith("You propose the questions to analyse next.") and read.startswith("DATA:\n") and "\n\nEARLIER (the analyses this question follows, oldest first):\n[1] Q: " + mod.BRIEF_QUESTION in read and "\n\nREPORT:\n## Regime C is " in read and "\n## Did not fit\n" in read
          and "\n\nBRIEF (agreed with the person before this run):\n" in read and "\n\nPROPOSED BEFORE:\n- " + first.get("q", "?") + "\n" in read
          and "\n\nLEVEL: test - a question at this level tests what the result rests on, or where it stops holding\n\nSOURCES:\n1. Rests on: The C plots got the most rain. (does not hold: " in read
          and "\nOther lines:\n" in read and read.index("\n3. Would change their mind: ") < read.index("\nOther lines:\n") < read.index(". Did not fit: " + misfit) and read.endswith("Reply with the JSON object."),
          read[-1400:])

    # the list, a way that has questions - shown with no call - and more of a way
    calls2 = len(usage_rows(wa, edition, user))
    page.click('#streamOutput .nq-panel [data-nq="list"]')
    page.wait_for_selector('#streamOutput .nq-row[data-level="emergence"] .n', state="visible", timeout=5000)
    both = panel_on_screen(page)["rows"]
    page.click('#streamOutput .nq-row[data-level="emergence"]')
    page.wait_for_selector('#streamOutput .nq-set[data-set="0"] .nq-card', state="visible", timeout=5000)
    page.wait_for_timeout(600)
    again, calls3 = sets_on_screen(page), len(usage_rows(wa, edition, user))
    check("the list says how many questions each of the two ways has, and a click on one that has some shows them, the other's out of sight - no call",
          [r[3] for r in both] == ["", "", "5 questions", "", "5 questions"] and [bare(s) for s in again] == [bare(s) for s in s1] and [s["shown"] for s in again] == [True, False] and calls3 == calls2,
          (both, again, calls2, calls3))
    page.click('#streamOutput .nq-panel [data-nq="list"]')
    page.click('#streamOutput .nq-row[data-level="blend"]')
    page.wait_for_selector('#streamOutput .nq-panel .nq-set[data-set="2"] .nq-card', timeout=20000)
    page.click('#streamOutput .nq-panel .nq-more')
    page.wait_for_selector('#streamOutput .nq-panel .nq-set[data-set="3"] .nq-card', timeout=20000)
    s2, p2 = sets_on_screen(page), panel_on_screen(page)
    joined, more = (s2[2]["cards"], s2[3]["cards"]) if len(s2) > 3 else ([], [])
    page.click('#streamOutput .nq-panel [data-nq="list"]')
    counted = [r[3] for r in panel_on_screen(page)["rows"]]
    page.click('#streamOutput .nq-row[data-level="emergence"]')
    page.wait_for_selector('#streamOutput .nq-set[data-set="0"] .nq-card', state="visible", timeout=5000)
    check("Blend elements, each question from two lines; then Write more, under its questions: a further set of the same way, shown under the first, each with its own count and button to its "
          "prompt - none of its questions was proposed before. The list counts the two sets as one way's questions",
          len(s2) == 4 and [(s["level"], s["shown"]) for s in s2] == [("emergence", False), ("test", False), ("blend", True), ("blend", True)] and len(joined) == 5 and 1 <= len(more) <= 5
          and all(c["from"].startswith("From the answer and ") and "\n" in c["lines"] for c in joined + more) and s2[2]["prompt"] and s2[3]["prompt"] and s2[2]["foot"].startswith("5 questions")
          and s2[3]["foot"].startswith(f"{len(more)} question") and not {c["q"] for c in more} & {c["q"] for s in s2[:3] for c in s["cards"]}
          and (p2["n"], p2["show"], p2["way"], p2["more"], p2["within"]) == (1, "blend", NEXT_WAYS[3][1:], "Write more", True)
          and counted == ["", "", "5 questions", f"{5 + len(more)} questions", "5 questions"], (s2[2:], p2, counted))
    rec = thread_run(wa, user, tid, cid2).get("next_questions") or []
    by_chain = {}
    for r in usage_rows(wa, edition, user)[rows0:]:
        by_chain.setdefault(str(r["chain_id"]), []).append(r["agent"])
    month1 = month_queries(page)
    check("the four sets are kept with the analysis they follow, on its record: the level, each question with the lines it comes from, the chain its call was logged under. Each set was one call of "
          "the Architect's under a chain of its own, which is no run of the thread - and a query of the month's (the self-hosted edition counts none)",
          [s.get("level") for s in rec] == ["emergence", "test", "blend", "blend"] and [len(s.get("questions", [])) for s in rec] == [5, 5, 5, len(more)]
          and rec[0]["questions"][0] == {"title": f"The {wide.group(1)} plots", "text": first.get("q"), "from": [{"kind": "misfit", "text": misfit}]}
          and [q["from"][0]["kind"] for q in rec[1]["questions"][:3]] == ["anchor", "anchor", "would_change"] and not any("ran" in q for s in rec for q in s["questions"])
          and sorted(by_chain) == sorted(str(s.get("chain")) for s in rec) and all(v == ["Architect"] for v in by_chain.values())
          and not any(thread_run(wa, user, tid, s.get("chain")) for s in rec) and month1 - month0 == (4 if edition == "hosted" else 0), (rec[:1], by_chain, month0, month1))

    # a question changed, then run - with the Architect's switch on: an analysis at once, as it stands
    changed = f"Is regime C above regime A on {wide.group(1)} plots alone, season by season?"
    page.click("#architectSwitch")
    page.fill("#queryInput", "typed by the coach, not sent")
    page.click('#streamOutput .nq-set[data-set="0"] .nq-card[data-k="0"] .pen')
    page.fill("#streamOutput .nq-input", changed)
    page.click('#streamOutput .nq-set[data-set="0"] .nq-card[data-k="0"] .go')
    wait_text(page, "#chainPosition", "chain 4 of 4", 60000)
    wait_run_end(page, 4)
    page.wait_for_function("() => responses.length === 4 && !responses[3].status", timeout=60000)
    ran = page.evaluate("""() => ({ first: (document.querySelector('#streamOutput .sp-stream > *') || {}).className, row: (document.querySelector('#streamOutput .nq-from') || {}).textContent,
        behind: (document.querySelector('#streamOutput .nq-from') || {}).title, tabs: [...document.querySelectorAll('#tabContainer .tab')].map(t => t.textContent), fold: !!document.querySelector('#streamOutput .ar-fold'),
        on: document.getElementById('architectSwitch').getAttribute('aria-pressed'), typed: document.getElementById('queryInput').value, button: document.querySelectorAll('#streamOutput .sp-done [data-nq="open"]').length,
        panels: document.querySelectorAll('#streamOutput .nq-panel').length })""")
    cid4 = page.evaluate("() => currentData.chain_id")
    fourth, followed = thread_run(wa, user, tid, cid4), thread_run(wa, user, tid, cid2)
    month2 = month_queries(page)
    check("a question changed and run: a new analysis at once, though the Architect's switch is on - no brief on the page, none on the run - under the analysis it follows, asking what the coach made of "
          "the question. Its pane opens on the row that says it was a next question and which way it went - not what it came from; what the coach was typing in the composer is still there; the new "
          "analysis has a Next questions button of its own, and no panel until it is asked for. On the record the question is marked with the chain it started, and it is a query of the month's as "
          "any analysis is",
          ran["first"] == "nq-from" and ran["row"] == "Next question·Follow emergence" and not ran["behind"] and "Brief" not in ran["tabs"] and "Answer" in ran["tabs"] and not ran["fold"]
          and ran["on"] == "true" and ran["typed"] == "typed by the coach, not sent" and ran["button"] == 1 and ran["panels"] == 0
          and fourth.get("status") == "answered" and fourth.get("question") == changed and str(fourth.get("parent")) == str(cid2) and fourth.get("brief") == {} and fourth.get("framing") == {}
          and [q.get("ran") for q in followed["next_questions"][0]["questions"]] == [str(cid4), None, None, None, None] and followed["next_questions"][0]["questions"][0]["text"] == first.get("q")
          and not any("ran" in q for s in followed["next_questions"][1:] for q in s["questions"]) and month2 - month1 == (1 if edition == "hosted" else 0), (ran, fourth.get("parent"), followed["next_questions"][0]["questions"][0], month2))
    page.evaluate("showWorkflowMap()")
    page.wait_for_selector("#workflowMapModal .wf-node", timeout=10000)
    boxes = page.evaluate("() => [...document.querySelectorAll('#workflowMapModal .wf-node')].map(n => [(n.querySelector('.wf-node-made') || {}).textContent || '', n.classList.contains('wf-node--fork')])")
    page.evaluate("document.getElementById('workflowMapModal').style.display = 'none'")
    page.click("#prevResponse")
    page.click("#prevResponse")
    wait_text(page, "#chainPosition", "chain 2 of 4", 10000)
    page.wait_for_selector("#streamOutput .nq-card.ran", timeout=10000)
    back, pback = sets_on_screen(page), panel_on_screen(page)
    check("the Workflow map gained one box - the questions are none, the one that was run is one, under the analysis it follows - and it says next question; no box is a fork. Back on the analysis the "
          "panel is as it was left, open on the way the question was run from, and the sets are as they were kept: the question as the coach changed it, without the title it came with, marked as run",
          boxes == [["Architect", False], ["Architect", False], ["", False], ["next question", False]] and len(back) == 4 and (pback["n"], pback["open"], pback["show"], pback["within"]) == (1, True, "emergence", True)
          and back[0]["cards"][0] == {"from": "From what did not fit", "lines": misfit, "title": "", "q": changed, "ran": str(cid4)} and back[0]["cards"][1:] == s0[0]["cards"][1:]
          and [bare(s) for s in back[1:]] == [bare(s) for s in s2[1:]] and [s["shown"] for s in back] == [True, False, False, False], (boxes, back[0]["cards"][:1], pback))

    # sets kept by the page before the panel (0313): under the card, each under a head; and the row of the run a question started, which also said what it came from - shown again, and put back
    kept = page.evaluate("""async () => { const e = responses[currentResponseIndex], was = e.streamOutput, d = document.createElement('div');
        d.innerHTML = was;
        const panel = d.querySelector('.nq-panel'), card = panel.closest('.sp-done'), names = { emergence: 'Follow emergence', test: 'Test boundaries' };
        const before = { 'From what it rests on': 'From it rests on', 'From what did not fit': 'From did not fit', 'From what was also checked': 'From also checked' };
        [...panel.querySelectorAll('.nq-set')].slice(0, 2).reverse().forEach(s => {
            const foot = s.querySelector('.nq-foot'), prompt = foot.querySelector('.sp-prompt'), head = document.createElement('div');
            head.className = 'nq-head';
            head.innerHTML = '<span class="k">Next questions</span><span class="sep">·</span><span class="lv">' + names[s.dataset.level] + '</span><span class="r">$0.02' + (prompt ? prompt.outerHTML : '') + '</span>';
            foot.remove(); s.classList.remove('on'); s.insertBefore(head, s.firstChild);
            s.querySelectorAll('.tx b').forEach(b => { b.textContent += '.'; });
            s.querySelectorAll('.from .l').forEach(l => { l.textContent = before[l.textContent] || l.textContent; });
            card.after(s);
        });
        panel.remove(); e.streamOutput = d.innerHTML;
        loadResponseContent(e);
        await new Promise(r => setTimeout(r, 400));
        const p = document.querySelector('#streamOutput .nq-panel'), sets = [...document.querySelectorAll('#streamOutput .nq-set')], vis = x => getComputedStyle(x).display !== 'none';
        const shown = { panels: document.querySelectorAll('#streamOutput .nq-panel').length, inCard: !!p && !!p.closest('.sp-done') && vis(p), show: p ? p.dataset.show : '', heads: document.querySelectorAll('#streamOutput .nq-head').length,
            loose: sets.filter(s => !s.closest('.nq-panel')).length, sets: sets.map(s => [s.dataset.set, s.dataset.level, vis(s), s.querySelector('.nq-foot span').textContent, !!s.querySelector('.nq-foot .sp-prompt')]),
            from: [...new Set([...document.querySelectorAll('#streamOutput .nq-card .from .l')].map(l => l.textContent))].sort(), stops: [...document.querySelectorAll('#streamOutput .nq-card .tx b')].filter(b => b.textContent.endsWith('.')).length,
            ran: document.querySelectorAll('#streamOutput .nq-card.ran').length };
        e.streamOutput = was; loadResponseContent(e);
        await new Promise(r => setTimeout(r, 400));
        // the run the question started: its row as 0313 kept it
        const r = responses[responses.length - 1], rowWas = r.streamOutput, f = document.createElement('div');
        f.innerHTML = rowWas;
        const row = f.querySelector('.nq-from');
        row.title = 'the line'; row.insertAdjacentHTML('beforeend', '<span class="sep">·</span><span>From did not fit</span>');
        r.streamOutput = f.innerHTML;
        const old = row.textContent, at = currentResponseIndex;
        currentResponseIndex = responses.length - 1; loadResponseContent(r);
        await new Promise(x => setTimeout(x, 400));
        const now = document.querySelector('#streamOutput .nq-from'), rowNow = [now.textContent, now.title, now.children.length];
        r.streamOutput = rowWas; currentResponseIndex = at; loadResponseContent(responses[at]);
        await new Promise(x => setTimeout(x, 400));
        return { shown, old, rowNow, back: document.querySelectorAll('#streamOutput .nq-panel .nq-set').length }; }""")
    check("sets the page kept before the panel - under the closing card, each under its own head - are taken into the card's panel when their analysis is shown again: one panel, open on the last "
          "set's way, no head left, each set's count, cost and prompt button under its questions, what a question starts from in today's words, no title ending on a full stop, the mark of the one "
          "that was run still on it. The row of a run kept from then, which also said From did not fit, says the way only. The page's own copies are put back",
          kept["shown"]["panels"] == 1 and kept["shown"]["inCard"] and kept["shown"]["show"] == "test" and kept["shown"]["heads"] == 0 and kept["shown"]["loose"] == 0
          and kept["shown"]["sets"] == [["0", "emergence", False, "5 questions · $0.02", True], ["1", "test", True, "5 questions · $0.02", True]]
          and not [f for f in kept["shown"]["from"] if f in ("From it rests on", "From did not fit", "From also checked")] and "From what did not fit" in kept["shown"]["from"]
          and kept["shown"]["stops"] == 0 and kept["shown"]["ran"] == 1 and kept["old"] == "Next question·Follow emergence·From did not fit" and kept["rowNow"] == ["Next question·Follow emergence", "", 3]
          and kept["back"] == 4, kept)
    page.wait_for_selector("#streamOutput .nq-card.ran .was", state="visible", timeout=10000)
    page.click("#streamOutput .nq-card.ran .was")
    wait_text(page, "#chainPosition", "chain 4 of 4", 10000)
    page.click("#architectSwitch")
    check("the mark on the question that was run opens the analysis it started", page.evaluate("() => String(currentData.chain_id)") == str(cid4), page.evaluate("() => String(currentData.chain_id)"))


# ---- the saved analyses in the Architect (docs/ARCHITECT_DESIGN.md §3.7): the helpers of its section ----
def saved_on_screen(page):
    """The saved analyses the readings found, as the coach sees them: under a reading's row in the conversation an analysis to a line - the day and what was asked then, View; under the brief
    each in full - its passages, the reader's notes, the tag of one the brief builds on; in the brief the analyses it builds on, each with View and its cross. Whether anything of it can be
    ticked, and whether a button has them read."""
    return page.evaluate("""() => { const r = document.querySelector('#content-brief .ar-brief'), text = (l, c) => (l.querySelector(c) || {}).textContent || '';
        const view = l => { const b = l.querySelector('[data-ar="open"]'); return b ? [b.dataset.thread, b.dataset.run] : null; };
        const item = full => it => Object.assign({ asked: text(it, '.q'), view: view(it), label: text(it, '[data-ar="open"]') },
            full ? { tag: text(it, '.tag'), quotes: [...it.querySelectorAll('.qt')].map(x => x.textContent), notes: [...it.querySelectorAll('.why')].map(x => x.textContent) } : {});
        return { left: [...document.querySelectorAll('#streamOutput .sp-stream > .ar-found .it')].map(item(false)), right: [...r.querySelectorAll('.ar-memory .it')].map(item(true)),
                 head: text(r, '.ar-memory h3'), note: text(r, '.ar-memory .note'),
                 built: [...r.querySelectorAll('.ar-built')].map(l => ({ asked: text(l, '.tx'), view: view(l), label: text(l, '[data-ar="open"]'), cross: !!l.querySelector('[data-ar="unbuild"]') })),
                 boxes: document.querySelectorAll('#streamOutput .ar-found .tick, #content-brief .ar-memory .tick, #content-brief .ar-built .tick').length,
                 look: !!document.querySelector('[data-ar="look"]') }; }""")


def saved_row(page):
    """The last row of the conversation, as the coach sees it: its marks, its parts, what it shows on hover, whether the analyses found are listed under it, and the message that follows."""
    return page.evaluate("""() => { const rows = [...document.querySelectorAll('#streamOutput .sp-stream > .sp-row')], r = rows[rows.length - 1];
        const list = r.nextElementSibling && r.nextElementSibling.classList.contains('ar-found') ? r.nextElementSibling : null, next = (list || r).nextElementSibling;
        return { n: rows.length, cls: r.className, text: [...r.children].map(c => c.textContent), title: r.title, found: !!list, after: next ? next.className : '' }; }""")


def as_written(iso):
    """A day as the page writes it: 2026-03-02 -> 2 Mar 2026."""
    return f"{int(iso[8:10])} {'Jan Feb Mar Apr May Jun Jul Aug Sep Oct Nov Dec'.split()[int(iso[5:7]) - 1]} {iso[:4]}" if re.fullmatch(r"\d{4}-\d{2}-\d{2}", iso or "") else iso


def walk_saved(page, st, mod, wa, edition, user, tid, cid2):
    """The analysis a brief started is saved, and a question it bears on is framed in a workflow of its own. The Architect is told how many analyses are saved; with nothing left to ask it has
    them read. A row of the conversation says how far the reading is, then what it found; the analyses found are listed under the row and, in full, under the brief - to read: nothing is ticked.
    The coach views one whole, then answers the Architect - build on that one - and the brief says which analysis it builds on. A second reading, asked for in words, is skipped. The coach
    leaves the analysis out with its cross, goes back one step with the arrow and starts the analysis from there: the Analyst receives the passage of the analysis built on, and no other."""
    storage = os.path.join(wa, "storage", user)
    page.click("#prevResponse")
    page.click("#prevResponse")
    wait_text(page, "#chainPosition", "chain 2 of 4", 10000)
    page.click("#saveButton")
    page.wait_for_selector("#saveMenu", state="visible", timeout=10000)
    page.click("#saveMenu .it[data-act='favourite']")
    page.wait_for_function("() => document.getElementById('saveButton').classList.contains('saved')", timeout=30000)
    mem = kept_memory(storage, lambda v: any(r["run"] == str(cid2) and "picked" in r["marks"] for r in v["runs"]))
    kept = {r["run"]: r for r in mem["runs"] if r["thread"] == str(tid)}
    first = lambda report: re.split(r"(?<=[.!?])\s", next(ln for ln in report.splitlines() if ln.strip() and not ln.startswith("#")), maxsplit=1)[0]      # a report's opening sentence
    framed, later = kept.get(str(cid2), {}), next((r for r in kept.values() if r["question"].startswith("Is regime C above regime A on ")), {})
    quote, other = first(framed.get("report", "-")), first(later.get("report", "-"))
    day, data = framed.get("when", "")[:10], framed.get("data", {}).get("name", "")

    # a question the saved analysis bears on, in a workflow of its own: three answers, and nothing left to ask
    page.evaluate("handleNewConversation()")
    page.wait_for_url("**/?new=true", timeout=60000)
    page.wait_for_selector("#queryInput", state="visible", timeout=60000)
    page.app_ready()
    page.wait_for_function("() => /Ready|Local|Docker/.test(document.querySelector('#containerStatusText').textContent)", timeout=60000)
    page.set_input_files("#primaryFile", st.dataset)
    page.wait_for_selector(".primary-dataset-pill", timeout=60000)
    page.wait_for_timeout(500)
    rows0 = len(usage_rows(wa, edition, user))
    page.click("#architectSwitch")
    page.fill("#queryInput", mod.SAVED_QUESTION)
    page.click("#submitQuery")
    page.wait_for_selector("#content-brief .ar-brief", timeout=15000)
    architect_said(page, 1)
    tid3, cid = page.evaluate("() => [currentData.thread_id, currentData.chain_id]")
    page.click("#streamOutput .sp-stream > .ar-msg.arch .sp-prompt")
    page.wait_for_function("() => { const u = document.getElementById('userInstructions'); return u && /CONVERSATION:/.test(u.textContent); }", timeout=15000)
    told = page.inner_text("#userInstructions")
    page.evaluate("() => { const m = document.getElementById('agentInstructionsModal'); if (m) m.style.display = 'none'; const u = document.getElementById('userInstructions'); if (u) u.textContent = ''; }")
    before = saved_on_screen(page)
    tell(page, choice=1)
    tell(page, "skip")
    page.evaluate("""() => { window.__savedRows = []; const pane = document.getElementById('streamOutput');
        new MutationObserver(records => records.forEach(m => m.addedNodes.forEach(n => {
            const row = n.nodeType !== 1 ? null : n.matches('.sp-row.pending') ? n : n.querySelector('.sp-row.pending');
            const text = row ? [...row.children].map(c => c.textContent).filter(Boolean).join(' · ') : '';
            if (text && window.__savedRows[window.__savedRows.length - 1] !== text) window.__savedRows.push(text);
        }))).observe(pane, { childList: true, subtree: true }); }""")
    tell(page, "skip", replies=2)
    live, row, b1, t1, s1 = page.evaluate("() => window.__savedRows"), saved_row(page), brief_on_screen(page), talk_on_screen(page), saved_on_screen(page)
    f1 = thread_run(wa, user, tid3, cid).get("framing", {})
    m1 = next((t for t in f1.get("turns", []) if t["who"] == "memory"), {})
    mine = next((k for k, it in enumerate(s1["right"]) if it["view"] == [str(tid), str(cid2)]), 0)      # where the framed analysis stands among the two found
    asked = [mod.BRIEF_ANSWER, later.get("question")] if mine == 0 else [later.get("question"), mod.BRIEF_ANSWER]
    line = {"asked": f"{as_written(day)} · {mod.BRIEF_ANSWER}", "view": [str(tid), str(cid2)], "label": "View"}
    check("a saved analysis is memory, and the Architect is told how many there are: SAVED, above the question, in what it read for its first message. With nothing left to ask - the coach skipped two "
          "parts - it says that it is looking, and the saved analyses are read: a row of the conversation says that memory is being searched (0311) and how many the second model has read, with Skip; done, "
          "the row says how many analyses were found and how many of the saved ones were read, the passages a line each on hover with what was found across them, and under the row stand the "
          "analyses found, a line each - the day, what was asked then, View. The Architect goes on at once: the brief is ready, and which analysis to build on - a choice to each, and one for none",
          str(cid2) in kept and framed.get("marks") == ["picked"] and framed.get("question") == mod.BRIEF_ANSWER and f"\n\nSAVED: {len(mem['runs'])}\n\nQUESTION:\n{mod.SAVED_QUESTION}\n" in told
          and before == {"left": [], "right": [], "head": "", "note": "", "built": [], "boxes": 0, "look": False}
          and live == [f"SEARCHING MEMORY · 0 of {len(mem['runs'])} read · Skip", "SEARCHING MEMORY · 2 of 2 read · Skip"]
          and row["n"] == 1 and row["cls"] == "sp-row tool read" and row["text"][:3] == ["✓", "MEMORY", f"2 analyses found · read 2 of {len(mem['runs'])}"] and re.fullmatch(r"\d+ s", row["text"][3])
          and sorted(row["title"].split("\n")[:2]) == sorted([f'{day} · {mod.BRIEF_ANSWER}: "{quote}"', f'{day} · {later.get("question")}: "{other}"'])
          and row["title"].split("\n")[2:] == ["What was compared: 2 × it reports a comparison"] and row["found"] and row["after"] == "ar-msg arch"
          and len(s1["left"]) == 2 and s1["left"][mine] == line and s1["left"][1 - mine]["asked"] == f"{as_written(later.get('when', '')[:10])} · {later.get('question')}"
          and t1["said"][-4:] == [["Architect", mod.ARCHITECT_ASKS[2][1]], ["You", "skip"], ["Architect", mod.ARCHITECT_LOOKING], ["Architect", mod.ARCHITECT_READY + mod.ARCHITECT_FOUND]]
          and t1["choices"] == [mod.ARCHITECT_BUILD_ON.format(q) for q in asked] + mod.ARCHITECT_BUILD[1:] and not t1["waiting"], (told[:300], before, live, row, s1["left"], t1["said"][-4:], t1["choices"]))
    check("what the reading found stands under the brief too, in full, to read: Found in your saved analyses, and that the Analyst gets only what the coach builds on; an analysis to a block - the day "
          "and what was asked then, View, the passage word for word as the saved report has it, the reader's note - with nothing to tick, no tag yet, and no button that has them read. The brief "
          "itself is as it was: no version was made - the step marks no line as changed - and it builds on nothing; the record keeps the reading as a turn of the conversation, with what it cost, and the passages found beside the brief",
          b1["v"] == "4 of 4" and b1["changed"] == [] and b1["heads"] == ["What it is for", "What is compared", "Found in your saved analyses"]
          and (s1["head"], s1["note"]) == ("Found in your saved analyses", "For you to read. The Analyst gets only what you build on.") and len(s1["right"]) == 2 and quote in framed.get("report", "")
          and s1["right"][mine] == {**line, "tag": "", "quotes": [quote], "notes": [mod.SAVED_NOTE]} and s1["right"][1 - mine]["quotes"] == [other] and s1["right"][1 - mine]["tag"] == ""
          and [it["asked"] for it in s1["right"]] == [it["asked"] for it in s1["left"]] and s1["built"] == [] and s1["boxes"] == 0 and not s1["look"]
          and [(v["by"], v.get("why")) for v in f1.get("versions", [])] == [("person", None), ("architect", "question"), ("architect", "answer")]
          and [t["who"] for t in f1.get("turns", [])] == ["architect", "person"] * 3 + ["architect", "memory", "architect"]
          and (len(m1.get("found", [])), m1.get("of"), m1.get("read"), m1.get("failed"), m1.get("dropped")) == (2, len(mem["runs"]), 2, "", 0) and m1.get("v") == 3
          and [len(g["runs"]) for g in (m1.get("across") or {}).get("groups", [])] == [2]
          and sorted((x["run"], x["passage"], x["marks"]) for x in f1.get("found", [])) == sorted([(str(cid2), quote, "picked"), (str(later.get("run")), other, "alongside")])
          and not any("saved" in v["brief"] for v in f1["versions"]), (b1, s1, m1, f1.get("found")))

    # the coach views the analysis whole, from the line under the reading's row
    page.click(f'#streamOutput .ar-found [data-ar="open"][data-run="{cid2}"]')
    page.wait_for_function("() => { const m = document.getElementById('savedAnalysisModal'); return !!m && getComputedStyle(m).display !== 'none'; }", timeout=10000)
    dlg = page.evaluate("""() => { const m = document.getElementById('savedAnalysisModal'), box = m.querySelector('.ui-dlg').getBoundingClientRect();
        const top = document.elementFromPoint(box.left + box.width / 2, box.top + 24), under = document.elementFromPoint(8, innerHeight / 2);      // what a click would reach: the dialog, and beside it the scrim
        return { title: m.querySelector('.title').textContent, sub: m.querySelector('.sub').textContent,
                 heads: [...m.querySelectorAll('.markdown-content h2')].map(h => h.textContent), text: m.querySelector('.markdown-content').textContent,
                 folds: [...m.querySelectorAll('.ar-code summary')].map(x => x.textContent), said: [...m.querySelectorAll('.ar-code pre.said')].map(x => x.textContent),
                 code: [...m.querySelectorAll('.ar-code pre:not(.said)')].map(x => x.textContent).join(' '), folded: [...m.querySelectorAll('.ar-code')].every(d => !d.open),
                 seen: box.width > 400 && box.top >= 0 && box.bottom <= innerHeight && !!top && m.contains(top) && under === m,
                 chain: String(currentData.chain_id) }; }""")
    page.click("#savedAnalysisModal .ui-dlg-h .x")
    shut = page.evaluate("() => getComputedStyle(document.getElementById('savedAnalysisModal')).display")
    check("View shows the analysis whole in a dialog over the page - the workflow on screen stays the one being framed: what was asked, the day, the data and how it was saved, the report with the "
          "passage in it, and folded under it the conversation its brief came from - the coach's messages under You - the brief it ran under and the code of its cells; its cross closes it, and "
          "the brief is as it was",
          dlg["title"] == mod.BRIEF_ANSWER and dlg["sub"] == f"{day} · {data} · picked" and "Against the brief" in dlg["heads"] and "Did not fit" in dlg["heads"] and quote in dlg["text"]
          and dlg["folds"] == ["Conversation", "Brief", "Code"] and framed.get("conversation") == f"Person: {mod.BRIEF_ANSWER}\nArchitect: {mod.ARCHITECT_READY}"
          and dlg["said"][0] == f"You: {mod.BRIEF_ANSWER}\nArchitect: {mod.ARCHITECT_READY}"
          and dlg["said"][1].startswith("What the answer is for: ") and "left to you" not in dlg["said"][1]
          and "BRIEF_DIFF" in dlg["code"] and dlg["folded"] and dlg["seen"] and dlg["chain"] == str(cid) and shut == "none" and brief_on_screen(page) == b1, (dlg, shut))

    # the coach answers the Architect: build on that one. Its favourite keeps a picture of what it drew - put there by hand here: the stack's stand-in for Plotly makes none
    picture = "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNkYPhfDwAChwGA60e6kgAAAABJRU5ErkJggg=="
    fav = os.path.join(storage, "favourites", str(tid), f"{cid2}.json")
    page_copy = json.load(open(fav, encoding="utf-8"))
    json.dump({**page_copy, "plotPreview": picture}, open(fav, "w", encoding="utf-8"))
    previews = []
    watch = lambda request: previews.append(request.url) if "/get_chain_preview/" in request.url else None      # noqa: E731
    page.on("request", watch)
    tell(page, choice=mine)
    page.wait_for_selector("#content-brief .ar-built", timeout=15000)
    page.wait_for_timeout(400)
    page.remove_listener("request", watch)
    under = page.evaluate("""() => { const line = document.querySelector('#content-brief .ar-built'), next = line.nextElementSibling;
        return { pictures: document.querySelectorAll('#content-brief img').length, next: next ? next.className.split(' ')[0] : '' }; }""")
    check("nothing of the analysis the brief builds on is drawn under its line (0311; 0310 had put the picture its favourite keeps there, and a live brief was too busy): the Brief tab holds "
          "no picture, and the page asked the server for none",
          under["pictures"] == 0 and under["next"] != "ar-was" and previews == [], (under, previews))
    b2, t2, s2 = brief_on_screen(page), talk_on_screen(page), saved_on_screen(page)
    last2 = (thread_run(wa, user, tid3, cid).get("framing", {}).get("versions") or [{}])[-1]
    check("the coach chooses by answering the Architect - the choice that names the analysis: the brief builds on it, as one more version - Builds on, with the day and what was asked then, View "
          "and a cross; under the brief that analysis carries the tag 'built on', the other none, and the line under the reading's row stands as it did. On the record the version is the "
          "Architect's, made from the answer, and holds that analysis's passage - the other's is in no version",
          t2["said"][-2:] == [["You", mod.ARCHITECT_BUILD_ON.format(mod.BRIEF_ANSWER)], ["Architect", mod.ARCHITECT_BUILT]] and t2["choices"] == []
          and b2["v"] == "5 of 5" and b2["changed"] == ["builds"] and b2["heads"] == ["What it is for", "What is compared", "Builds on", "Found in your saved analyses"]
          and s2["built"] == [{**line, "cross": True}] and [it["tag"] for it in s2["right"]] == (["built on", ""] if mine == 0 else ["", "built on"]) and s2["left"] == s1["left"] and s2["boxes"] == 0
          and (last2.get("by"), last2.get("why"), last2.get("changed")) == ("architect", "answer", ["saved.0"])
          and [(x["run"], x["passage"], x["accepted"]) for x in last2.get("brief", {}).get("saved", [])] == [(str(cid2), quote, True)], (t2["said"][-2:], b2, s2, last2))

    # a second reading, asked for in words - and skipped
    said = page.evaluate("() => document.querySelectorAll('#streamOutput .sp-stream > .ar-msg.arch:not(.wait)').length")
    page.fill("#queryInput", mod.ARCHITECT_AGAIN)
    page.click("#submitQuery")
    page.wait_for_selector("#streamOutput .sp-row.pending .ar-skip:not([disabled])", timeout=15000)
    mid = page.evaluate("""() => { const s = document.querySelector('#streamOutput .sp-stream'), row = s.querySelector('.sp-row.pending'), msgs = [...s.querySelectorAll('.ar-msg')];
        const last = msgs[msgs.length - 1].cloneNode(true); last.querySelectorAll('.who').forEach(x => x.remove());
        return { last: [msgs[msgs.length - 1].className, last.textContent], wait: !!s.querySelector('.ar-msg.wait'),
                 row: [...row.children].map(c => c.textContent).filter(Boolean), under: row === s.lastElementChild,
                 held: document.getElementById('queryInput').disabled && document.getElementById('queryInput').placeholder }; }""")
    page.click("#streamOutput .sp-row.pending .ar-skip")
    architect_said(page, said + 2)
    row2, t3, s3, b3 = saved_row(page), talk_on_screen(page), saved_on_screen(page), brief_on_screen(page)
    f3 = thread_run(wa, user, tid3, cid).get("framing", {})
    m3 = [t for t in f3.get("turns", []) if t["who"] == "memory"]
    rows = [(r["agent"], str(r["chain_id"])) for r in usage_rows(wa, edition, user)[rows0:]]
    check("one more reading, asked for in words: the reading starts - its row under the coach's words while it goes, the composer held and saying why. Skip ends it: the Architect's message "
          "that it is looking stands above the row, which says it was skipped, with nothing listed under it; the brief and what was found before stand as they were, and the Architect goes on. On "
          "the usage record the brief's chain holds the Architect's calls and the two models of the reading, in order - of the skipped reading no call, or the one that was on its way",
          mid == {"last": ["ar-msg you", mod.ARCHITECT_AGAIN], "wait": False, "row": ["SEARCHING MEMORY", f"0 of {len(mem['runs'])} read", "Skip"], "under": True,
                  "held": "Your saved analyses are being read"}
          and row2["n"] == 2 and row2["cls"] == "sp-row tool read skipped" and row2["text"][:3] == ["–", "MEMORY", "skipped"] and not row2["found"] and row2["after"] == "ar-msg arch"
          and t3["said"][-3:] == [["You", mod.ARCHITECT_AGAIN], ["Architect", mod.ARCHITECT_LOOKING], ["Architect", mod.ARCHITECT_READY]] and s3 == s2
          and b3 == {**b2, "v": "6 of 6", "changed": []}
          and [t["who"] for t in f3.get("turns", [])][-4:] == ["person", "architect", "memory", "architect"] and len(m3) == 2 and (m3[1]["failed"], m3[1]["found"]) == ("The person skipped it.", [])
          and len(f3.get("versions", [])) == 4 and len(f3.get("found", [])) == 2 and f3.get("calls") == 8
          and rows[:11] == [("Architect", str(cid))] * 4 + [("Memory Reader", str(cid))] * 2 + [("Memory Pieces", str(cid)), ("Memory Reader", str(cid))] + [("Architect", str(cid))] * 3
          and rows[11:] in ([("Architect", str(cid))], [("Memory Reader", str(cid)), ("Architect", str(cid))]), (mid, row2, t3["said"][-3:], rows, m3[1:], s3))

    # the coach leaves the analysis out with its cross, then goes back one step with the arrow
    page.click('#content-brief .ar-built [data-ar="unbuild"]')
    page.wait_for_function("() => { const r = document.querySelector('#content-brief .ar-brief'); return r && JSON.parse(r.dataset.framing).versions.length === 5; }", timeout=15000)
    b4, s4 = brief_on_screen(page), saved_on_screen(page)
    page.click('#content-brief [data-ar="step"][data-step="-1"]')
    b5, s5 = brief_on_screen(page), saved_on_screen(page)
    f5 = thread_run(wa, user, tid3, cid).get("framing", {})
    last5 = (f5.get("versions") or [{}])[-1]
    check("the cross on Builds on leaves the analysis out: one more version, the coach's, that builds on nothing - the tag is gone under the brief, where the analyses found stay, to read. The arrow "
          "back shows the step before, where the brief builds on it, and Start analysis names that step",
          b4["v"] == "7 of 7" and s4["built"] == [] and [it["tag"] for it in s4["right"]] == ["", ""] and "Builds on" not in b4["heads"] and b4["start"] == "Start analysis" and s4["left"] == s1["left"]
          and (last5.get("by"), last5.get("changed")) == ("person", ["saved"]) and "saved" not in last5.get("brief", {}) and "at" not in f5
          and b5["v"] == "6 of 7" and s5["built"] == s2["built"] and [it["tag"] for it in s5["right"]] == [it["tag"] for it in s2["right"]] and b5["start"] == "Start analysis from step 6",
          (b4, s4["built"], last5, b5, s5["built"]))

    # Start analysis from step 6: the Analyst receives the passage of the analysis the brief builds on there, and no other
    page.evaluate("setMode('deep')")
    page.click('#content-brief [data-ar="start"]')
    wait_run_end(page, 1)
    page.wait_for_function("() => responses.length === 1 && !responses[0].status", timeout=60000)
    prompt = turn_prompt(page, 1)
    ran = thread_run(wa, user, tid3, cid)
    fold = page.evaluate("""() => ({ head: document.querySelector('#streamOutput .ar-fold summary').textContent,
        rows: [...document.querySelectorAll('#streamOutput .ar-fold .sp-detail .sp-row.tool.read')].map(r => r.className) })""")
    page.click("#tab-brief")
    after = brief_on_screen(page)
    check("Start analysis from step 6 (0316): the analysis runs under the brief of the step on screen, not the last one. The Analyst is given the passage of the analysis that brief builds on, "
          "in its BRIEF block, numbered - the day, what was asked then, where it stands, the passage, the data - as an earlier result to test; the passage of the other analysis found is "
          "nowhere in its prompt, nor on the run's own brief. The question's read is a step that follows step 6 - another way than the cross, which is left - and the analysis starts from "
          "it: the record says which version is in use and which step; the framing folds above the run under that step, the seventh of its way, with both readings' rows inside, and the "
          "Brief tab, read after the run, shows it - with no pencil and no Start analysis",
          f'\nSaved analyses the person chose (earlier results: claims to test, not evidence):\n1. {day} "{mod.BRIEF_ANSWER}" ({data}): in its report "{quote}"' in prompt and other not in prompt
          and ran.get("status") == "answered" and ran.get("brief", {}).get("version") == 4 and [(x["run"], x["passage"], x["accepted"]) for x in ran.get("brief", {}).get("saved", [])] == [(str(cid2), quote, True)]
          and ran.get("framing", {}).get("at") == 4 and len(ran["framing"].get("versions", [])) == 5
          and steps_of(ran["framing"])[-2:] == [(7, 6, 5, [5], 0), (8, 6, 4, [], 1)] and (ran["framing"].get("step"), ran["framing"].get("tip")) == (8, 8)
          and fold["head"].startswith("Architectbrief · step 7") and fold["rows"] == ["sp-row tool read", "sp-row tool read skipped", "sp-row tool read"]
          and after["state"] == "run" and after["v"] == "7 of 7" and after["pens"] == 0 and not after["start"] and "Builds on" in after["heads"] and "Found in your saved analyses" not in after["heads"],
          (prompt[:900], ran.get("brief", {}).get("saved"), ran.get("framing", {}).get("at"), fold, after))
    opened = next((t for t in ran.get("turns", []) if t["kind"] == "show"), {})
    shown = page.evaluate("() => [...document.querySelectorAll('#streamOutput .sp-row.tool')].map(r => r.textContent).filter(t => /SHOW/.test(t))")
    check("the Analyst opens the saved analysis the passage comes from before it computes (SHOW SAVED 1): what was asked, the brief it ran under - what was agreed, and none of the words its own "
          "analyst was given for a part left open - the report with the passage in it and the code of its cells, as memory holds it; the pane shows the step as a row that says which analysis "
          "was opened; then its own cell, and the report",
          [t["kind"] for t in ran.get("turns", [])][:3] == ["show", "cell", "report"] and opened.get("stdout", "").startswith(f'--- saved analysis 1: {day} "{mod.BRIEF_ANSWER}" ---\nQUESTION: {mod.BRIEF_ANSWER}\n')
          and "\nBRIEF:\nWhat the answer is for: " in opened.get("stdout", "") and "left to you" not in opened.get("stdout", "") and "[always]" not in opened.get("stdout", "")
          and quote in opened.get("stdout", "") and "BRIEF_DIFF" in opened.get("stdout", "") and len(shown) == 1 and f'saved analysis 1: {day} "{mod.BRIEF_ANSWER}"' in shown[0] and "---" not in shown[0],
          (opened.get("stdout", "")[:600], shown, [t["kind"] for t in ran.get("turns", [])]))

    # the framed analysis that was saved, opened again from Saved workflows: its brief came with it
    page.click("#workflowManagerPill")
    page.wait_for_selector(f'#workflowManagerModal .workflow-card[data-thread-id="{tid}"]', timeout=15000)
    page.click(f'#workflowManagerModal .workflow-card[data-thread-id="{tid}"]')
    page.wait_for_function("() => /chain \\d of 4/.test(document.getElementById('chainPosition').textContent) && !document.getElementById('queryInput').disabled", timeout=15000)
    for _ in range(4):
        at, want = page.evaluate("(c) => [currentResponseIndex, responses.findIndex(r => String(r.chain_id) === String(c))]", cid2)
        if at == want:
            break
        page.click("#nextResponse" if want > at else "#prevResponse")
        page.wait_for_timeout(300)
    page.wait_for_selector("#tab-brief", timeout=10000)
    page.click("#tab-brief")
    again = brief_on_screen(page)
    page.click('#content-brief [data-ar="step"][data-step="-1"]')
    before2 = brief_on_screen(page)
    inside = talk_on_screen(page, "#streamOutput .ar-fold .sp-detail")
    check("a framed analysis saved and opened again from Saved workflows: its Brief tab comes with it, to be read - the step it started from, no pencil, no Start analysis - and goes back "
          "through its steps: the first holds the same brief, with the line the Architect changed in it marked; the framing is folded above the run, the conversation inside",
          again["state"] == "run" and again["v"] == "2 of 2" and again["measure"] == "yield" and again["pens"] == 0 and not again["start"] and again["versions"] == 2
          and before2["v"] == "1 of 2" and before2["measure"] == "yield" and before2["changed"] == ["fixed.measure"] and before2["pens"] == 0 and not before2["start"]
          and inside["said"] == [["You", mod.BRIEF_ANSWER], ["Architect", mod.ARCHITECT_READY]], (again, before2["v"], before2["measure"], inside))


def walk_tutor(page, mod, wa, edition, user):
    """The Architect as a tutor (2026-11-17), with nothing loaded. A bare request: the Architect says what could be looked at, in a message of several lines with choices. It then words the
    question, and its wording is the question at once: the box on the Brief tab shows it as one more version, and a row of the conversation says so; a wording the coach gives goes the same
    way, and a question the Architect writes among the brief's parts is not kept. The coach steps back to an earlier step with the arrow and goes on from it: another way, with nothing of the way left in what
    the Architect reads. The conversation's map shows both ways (0316): the coach goes to the end of the one that was left, goes on from there, comes back, and goes on by hand. The
    analysis then runs under what was agreed and nothing else: with no data there are no standing checks, and the report is not asked how it stands against a brief that expects nothing. A
    question that follows it opens a brief with what the answer was for; the Architect has the saved analyses read, opens the report of the analysis before and speaks from it; told to build
    on it, it brings that analysis into the brief."""
    page.evaluate("handleNewConversation()")
    page.wait_for_url("**/?new=true", timeout=60000)
    page.wait_for_selector("#queryInput", state="visible", timeout=60000)
    page.app_ready()
    page.wait_for_function("() => /Ready|Local|Docker/.test(document.querySelector('#containerStatusText').textContent)", timeout=60000)
    if page.evaluate("() => document.getElementById('architectSwitch').getAttribute('aria-pressed')") != "true":
        page.click("#architectSwitch")
    page.fill("#queryInput", mod.TUTOR_QUESTION)
    page.click("#submitQuery")
    page.wait_for_selector("#content-brief .ar-brief", timeout=15000)
    architect_said(page, 1)
    tid, cid = page.evaluate("() => [currentData.thread_id, currentData.chain_id]")
    wording = mod.TUTOR_QUESTION + ", season by season"
    read_last = lambda: (page.click("#streamOutput .sp-stream > .ar-msg.arch .sp-prompt >> nth=-1"),
                         page.wait_for_function("() => { const u = document.getElementById('userInstructions'); return u && /CONVERSATION:/.test(u.textContent); }", timeout=15000),
                         page.inner_text("#userInstructions"),
                         page.evaluate("() => { const m = document.getElementById('agentInstructionsModal'); if (m) m.style.display = 'none'; const u = document.getElementById('userInstructions'); if (u) u.textContent = ''; }"))[2]
    t0, b0 = talk_on_screen(page), brief_on_screen(page)
    lines = page.evaluate("() => { const m = document.querySelector('#streamOutput .sp-stream > .ar-msg.arch:not(.wait)'), who = m.querySelector('.who').getBoundingClientRect().height;"
                          " return [getComputedStyle(m).whiteSpace, Math.round((m.getBoundingClientRect().height - m.querySelector('.ar-choices').getBoundingClientRect().height - who) / 19.5)]; }")
    rows0 = len(usage_rows(wa, edition, user))
    tell(page, choice=0)
    t1, b1, rec1 = talk_on_screen(page), brief_on_screen(page), thread_run(wa, user, tid, cid)
    asked1 = page.evaluate("() => responses[currentResponseIndex].queryText")
    v1 = rec1.get("framing", {}).get("versions", [])
    check("a bare request: the Architect says what could be looked at, in a message of several lines with choices; the conversation shows the message as written, line for line, and the brief "
          "stands at its one version, under the question as it was asked. The coach picks one, and the Architect words the question: its wording is the question at once - in the box on the Brief "
          "tab, marked as changed, as version 2, a version of the Architect's made from the answer - and the run's question on the record; a row under the Architect's message says the question "
          "was updated, and at which step. Nothing waits to be taken, and no button takes it: one call was made",
          t0["said"] == [["You", mod.TUTOR_QUESTION], ["Architect", mod.TUTOR_FIRST]] and t0["choices"] == mod.TUTOR_CHOICES and lines[0] == "pre-wrap" and lines[1] >= 4 and t0["notes"] == []
          and (b0["v"], b0["title"], b0["heads"], b0["asked"]) == ("1 of 1", mod.TUTOR_QUESTION, [], "What the Analyst will be asked")
          and t1["said"][-2:] == [["You", mod.TUTOR_CHOICES[0]], ["Architect", mod.ARCHITECT_BACK]] and t1["choices"] == mod.ARCHITECT_YES
          and t1["notes"] == [["QUESTION", "updated", "step 2", "ar-msg arch", ""]] and (b1["v"], b1["title"], b1["changed"]) == ("2 of 2", wording, ["question"])
          and rec1.get("question") == wording and asked1 == wording and page.evaluate("() => document.querySelectorAll('.ar-wording, .ar-use').length") == 0
          and [(v["by"], v.get("why"), v["changed"], v["brief"]["question"]) for v in v1] == [("person", None, [], mod.TUTOR_QUESTION), ("architect", "answer", ["question"], wording)]
          and len(usage_rows(wa, edition, user)) == rows0 + 1, (t0, lines, b0, t1["said"][-2:], t1["notes"], b1, rec1.get("question"), v1))
    own = "Plot regime C beside regime A"
    tell(page, mod.ARCHITECT_OWN + own)
    t2, b2, rec2 = talk_on_screen(page), brief_on_screen(page), thread_run(wa, user, tid, cid)
    check("a wording the coach gives: the Architect gives it as its own, and it is the question at once - one more version, and a row to each wording, under the message that gave it; the "
          "conversation still opens on the question as it was asked",
          t2["said"][0] == ["You", mod.TUTOR_QUESTION] and t2["said"][-2:] == [["You", mod.ARCHITECT_OWN + own], ["Architect", mod.ARCHITECT_BACK]]
          and t2["notes"] == [["QUESTION", "updated", "step 2", "ar-msg arch", "ar-msg you"], ["QUESTION", "updated", "step 3", "ar-msg arch", ""]]
          and (b2["v"], b2["title"], b2["changed"]) == ("3 of 3", own, ["question"]) and rec2.get("question") == own, (t2["said"][-2:], t2["notes"], b2, rec2.get("question")))

    # the arrow back to step 2, and the coach goes on from it: another way (0316)
    rows2 = len(usage_rows(wa, edition, user))
    page.click('#content-brief [data-ar="step"][data-step="-1"]')
    b3, t3 = brief_on_screen(page), talk_on_screen(page)
    stepped = [len(usage_rows(wa, edition, user)), thread_run(wa, user, tid, cid).get("framing", {}).get("step")]
    tell(page, choice=0)
    t4, b4, rec4 = talk_on_screen(page), brief_on_screen(page), thread_run(wa, user, tid, cid)
    read4 = read_last()
    f4 = rec4.get("framing", {})
    check("the arrow back (0316): step 2 of 3 is on screen, and both panes are that step's - the first wording in the box, with its pencil; the conversation up to there, its last message the "
          "Architect's question whether that is meant, with its choices to click again, and nothing of the wording the coach gave after; Start analysis names the step. Nothing went to the "
          "server. What the coach does next goes on from the step on screen: they click a choice, and the exchange is a step that follows step 2 - another way, and its third step. The "
          "Architect reads the question and the brief as they stood at step 2 and the conversation up to there: not a word of the step that was left, and no word that the coach went back. Its "
          "reply changes nothing, so no version is made: version 2 is the one in use - on the record, in the box - and its question is the run's. The record keeps the step that was left, "
          "with what was said in it, set aside",
          (b3["v"], b3["title"], b3["start"], b3["changed"]) == ("2 of 3", wording, "Start analysis from step 2", ["question"]) and b3["pens"] > 0 and stepped == [rows2, 3]
          and t3["said"] == t1["said"] and t3["choices"] == mod.ARCHITECT_YES and t3["notes"] == t1["notes"]
          and t4["said"] == t1["said"] + [["You", mod.ARCHITECT_YES[0]], ["Architect", mod.ARCHITECT_WRITTEN]] and t4["notes"] == [["QUESTION", "updated", "step 2", "ar-msg arch", "ar-msg you"]]
          and (b4["v"], b4["title"], b4["start"], b4["changed"]) == ("3 of 3", wording, "Start analysis", [])
          and rec4.get("question") == wording and f4.get("at") == 2 and len(f4.get("versions", [])) == 3
          and steps_of(f4) == [(1, 0, 1, [1], 1), (2, 1, 2, [2], 2), (3, 2, 3, [3], 2), (4, 2, 2, [], 2)] and (f4.get("step"), f4.get("tip")) == (4, 4)
          and list(f4.get("aside", {})) == ["3"] and [t.get("text") for t in f4["aside"]["3"].get("turns", [])] == [mod.ARCHITECT_OWN + own, mod.ARCHITECT_BACK]
          and not any(t.get("who") == "version" for t in f4.get("turns", []))
          and f"QUESTION:\n{wording}\n(first asked as: {mod.TUTOR_QUESTION})\n\nBRIEF (version 2):" in read4
          and f"Architect: {mod.ARCHITECT_BACK}\n(the question was written as: {wording})\n(choices offered: " in read4 and f"\nPerson: {mod.ARCHITECT_YES[0]}\n\nReply with the JSON object." in read4
          and own not in read4 and "went to version" not in read4,
          (b3, stepped, t3["said"][-2:], t4["said"][-2:], t4["notes"], b4["v"], rec4.get("question"), f4.get("at"), steps_of(f4), f4.get("aside"), read4[-600:]))
    tell(page, mod.ARCHITECT_UNREAD)
    b5, t5, rec5 = brief_on_screen(page), talk_on_screen(page), thread_run(wa, user, tid, cid)
    read = read_last()
    check("a question the Architect writes among the brief's parts is not kept: the brief and the run's question stand. The Architect reads the question as it stands, with how it was first asked, "
          "the wording under the message that gave it - and, nothing being loaded, that there is no data",
          (b5["v"], b5["title"], rec5.get("question")) == ("4 of 4", wording, wording) and mod.ARCHITECT_UNREAD_WORDING not in json.dumps(rec5)
          and f"QUESTION:\n{wording}\n(first asked as: {mod.TUTOR_QUESTION})\n\nBRIEF (version 2):" in read and read.startswith("DATA:\n(no dataset attached")
          and f"Architect: {mod.ARCHITECT_BACK}\n(the question was written as: {wording})\n(choices offered: " in read and "not taken yet" not in read and own not in read,
          (b5["v"], b5["title"], rec5.get("question"), read[:300]))

    # the conversation's map (0316): the Workflow map's drawer, a box to a step; the way that was left is there to go back to, and to go on from
    cut = lambda text: text if len(text) <= 30 else text[:27] + "..."      # noqa: E731 - what a box says, as the map's drawing cuts it
    open_map = lambda: (page.click('#content-brief .ar-ver [data-ar="map"]'), page.wait_for_selector("#workflowMapModal .wf-node", timeout=10000))      # noqa: E731
    shut_map = lambda: page.wait_for_function("() => getComputedStyle(document.getElementById('workflowMapModal')).display === 'none'", timeout=5000)      # noqa: E731
    rows_m, rec_m = len(usage_rows(wa, edition, user)), thread_run(wa, user, tid, cid)
    open_map()
    m0 = conversation_map(page)
    page.hover("#workflowMapModal .wf-node >> nth=2")
    m_over = conversation_map(page)
    page.hover("#workflowMapModal .map-drawer-head")       # the pointer off the boxes
    m_rest = conversation_map(page)
    page.click("#workflowMapModal .wf-node >> nth=2")
    shut_map()
    b_left, t_left = brief_on_screen(page), talk_on_screen(page)
    open_map()
    m_left = conversation_map(page)                # opened again: the step now on screen is the open box
    page.click("#workflowMapModal .workflow-close")
    shut_map()
    quiet_m = [len(usage_rows(wa, edition, user)) == rows_m, thread_run(wa, user, tid, cid) == rec_m]
    check("the conversation's map (0316): the button beside the arrows opens the Workflow map's drawer under the conversation's own name - how many steps, where they branch - with the thread's "
          "buttons out of it. A box to a step, joined to the step it follows: on it what the coach said - the question as it was asked on the first - and under it what the step changed. The "
          "step on screen is the open box and the way to it is lit; the step that was left is faint. Under the pointer that box lights its own way, and the drawer's foot says what was said "
          "there, where the step stands as the arrows would count it, what it follows, how many follow it, what it changed and the first sentence of the Architect's reply; the pointer gone, "
          "the way to the step on screen is lit again. A click on the box shuts the drawer, and both panes are that step's: the wording the coach gave in the box, the conversation of the way "
          "that was left - and nothing of the way taken since. Opened again, the map has that step open, its way lit and the other way faint, and its foot says what a click and the pointer do; its cross "
          "shuts it. Its head (0324) is the drawer's one head: the Git branch mark, the name, what is on the map, then zoom, full screen and the close on one line - nothing on the map. "
          "Nothing went to the server, and the record is as it was",
          m0["open"] and (m0["title"], m0["sub"], m0["says"], m0["rows"]) == ("Brief map", "5 steps · 1 branch", "Click a step to go to it. Hover over one to read what was said.", [])
          and m0["head"] == map_head("branch")
          and m0["boxes"] == [[cut(mod.TUTOR_QUESTION), "your question"], [cut(mod.TUTOR_CHOICES[0]), "question"], [cut(mod.ARCHITECT_OWN + own), "question"], [cut(mod.ARCHITECT_YES[0]), ""],
                              [cut(mod.ARCHITECT_UNREAD), ""]]
          and (m0["on"], m0["lit"], m0["thread"], m0["buttons"]) == ([5], [1, 2, 4, 5], 0, False)
          and m_over["lit"] == [1, 2, 3, 5] and m_over["says"] == mod.ARCHITECT_OWN + own
          and m_over["rows"] == [["Step", "3 of 3"], ["Follows", "step 2"], ["Follow-ups", "none"], ["Changed", "question"], ["Architect", mod.ARCHITECT_BACK.split(". ")[0] + "."]]
          and m_rest["lit"] == [1, 2, 4, 5] and m_rest["on"] == [5]
          and (b_left["v"], b_left["title"], b_left["start"]) == ("3 of 3", own, "Start analysis") and t_left["said"] == t2["said"] and t_left["notes"] == t2["notes"] and t_left["choices"] == mod.ARCHITECT_YES
          and (m_left["on"], m_left["lit"], m_left["says"], m_left["rows"]) == ([3], [1, 2, 3], "Click a step to go to it. Hover over one to read what was said.", [])
          and quiet_m == [True, True], (m0, m_over, m_rest["lit"], b_left["v"], b_left["title"], t_left["said"][-2:], m_left, quiet_m))
    tell(page, choice=0)                         # at the end of the way that was left: the coach takes the wording after all
    t_on, b_on, f_on = talk_on_screen(page), brief_on_screen(page), thread_run(wa, user, tid, cid).get("framing", {})
    read_on = read_last()
    open_map()
    m1 = conversation_map(page)
    page.click("#workflowMapModal .wf-node >> nth=4")       # and back to the step they had come from
    shut_map()
    b_home, t_home = brief_on_screen(page), talk_on_screen(page)
    check("the way that was left, gone on from (0316): the coach answers at its end, and the exchange is a step that follows it - the Architect reads the wording the coach gave as the "
          "question, the brief as it stood there and that way's conversation, with nothing of the other way. The map then has six steps, the new one open at the end of its way and the other "
          "way faint. A click on the step the coach had come from, and both panes are that step's again: its question, its conversation. On the record the step in use is still the last one "
          "spoken from: a step looked at is put in use by what is said or changed next",
          t_on["said"] == t2["said"] + [["You", mod.ARCHITECT_YES[0]], ["Architect", mod.ARCHITECT_WRITTEN]] and (b_on["v"], b_on["title"]) == ("4 of 4", own)
          and steps_of(f_on)[-1] == (6, 3, 3, [], 2) and (f_on.get("step"), f_on.get("tip")) == (6, 6) and sorted(f_on.get("aside", {})) == ["4", "5"] and "at" not in f_on
          and f"QUESTION:\n{own}\n(first asked as: {mod.TUTOR_QUESTION})\n\nBRIEF (version 3):" in read_on and mod.ARCHITECT_UNREAD not in read_on
          and (m1["sub"], m1["on"], m1["lit"]) == ("6 steps · 1 branch", [6], [1, 2, 3, 6]) and m1["boxes"][5] == [cut(mod.ARCHITECT_YES[0]), ""]
          and (b_home["v"], b_home["title"], b_home["start"]) == ("4 of 4", wording, "Start analysis") and t_home["said"] == t5["said"]
          and thread_run(wa, user, tid, cid).get("framing", {}).get("step") == 6,
          (t_on["said"][-2:], b_on["v"], steps_of(f_on), f_on.get("aside", {}).keys(), read_on[:300], m1, b_home["v"], b_home["title"]))

    # what was agreed, and nothing else: two lines the coach adds by hand, at the step on screen, then the analysis - with nothing loaded
    what_for, period = "I want to see the two side by side.", "the 2025 season"
    brief_type(page, "decision", what_for)
    b_one, f_one = brief_on_screen(page), thread_run(wa, user, tid, cid).get("framing", {})
    brief_type(page, "fixed.period", period)
    b6 = brief_on_screen(page)

    # the question's check (0313): the coach words the question so that it points to an analysis the Analyst is not given. Start analysis has it read first - nothing runs, the Architect
    # words it again - and the next Start runs at once
    pointed = wording + ", " + mod.COLD_POINTER
    brief_type(page, "question", pointed)
    rows_c, said_c = len(usage_rows(wa, edition, user)), page.evaluate("() => document.querySelectorAll('#streamOutput .sp-stream > .ar-msg.arch:not(.wait)').length")
    page.evaluate("""() => { window.__checking = null;
        const watch = new MutationObserver(() => {
            const row = document.querySelector('#streamOutput .sp-stream > .sp-row.pending');
            if (!row) return;
            watch.disconnect();
            const input = document.getElementById('queryInput');
            window.__checking = { row: [...row.children].map(c => c.textContent).filter(Boolean), hold: [input.disabled, input.placeholder], running: queryRunning };
        });
        watch.observe(document.body, { childList: true, subtree: true }); }""")
    page.evaluate("setMode('deep')")
    page.click('#content-brief [data-ar="start"]')
    architect_said(page, said_c + 1)
    checking = page.evaluate("() => window.__checking")
    b7, t7, rec7 = brief_on_screen(page), talk_on_screen(page), thread_run(wa, user, tid, cid)
    f7 = rec7.get("framing", {})
    row7 = page.evaluate("""() => { const rows = [...document.querySelectorAll('#streamOutput .sp-stream > .sp-row.tool.read')].filter(r => r.children[1].textContent === 'CHECK question'), r = rows[rows.length - 1];
        const out = r && r.children[2];
        return r ? { n: rows.length, cls: r.className, text: [...r.children].map(c => c.textContent), under: r.nextElementSibling ? r.nextElementSibling.className : '',
                     whole: out.scrollWidth <= out.clientWidth + 1 && getComputedStyle(out).whiteSpace === 'normal' } : null; }""") or {}
    page.click("#streamOutput .sp-stream > .sp-row.tool.read .sp-prompt[data-agent='Question check'] >> nth=-1")
    page.wait_for_function("() => { const u = document.getElementById('userInstructions'); return u && /QUESTION:/.test(u.textContent); }", timeout=15000)
    given7 = page.inner_text("#userInstructions")
    page.evaluate("() => { const m = document.getElementById('agentInstructionsModal'); if (m) m.style.display = 'none'; const u = document.getElementById('userInstructions'); if (u) u.textContent = ''; }")
    page.wait_for_timeout(200)
    used7 = [r["agent"] for r in usage_rows(wa, edition, user)[rows_c:]]
    held7 = page.evaluate("() => ({ running: queryRunning, n: responses.length, status: responses[0].status, input: [document.getElementById('queryInput').disabled, document.getElementById('queryInput').placeholder] })")
    check("the question's check (0313): the coach words the question so that it points to an analysis the Analyst is not given, and presses Start analysis. The question is read first - a row says "
          "so, the composer is held and says why - by a reader given what the Analyst will be given: the data's word that nothing is loaded, the question, the brief as agreed. Nothing runs: the "
          "conversation holds the read - the words the Analyst cannot place, greyed and whole: the row wraps -, with its seconds and the button to what the reader was given - and under it the Architect's reply, which "
          "took them out: its wording is one more version, the question in the box and the run's. The record keeps the read as a turn, lists both versions as read, and the usage record holds "
          "the two calls, each under its name",
          checking == {"row": ["CHECKING THE QUESTION"], "hold": [True, "The question is being read as the Analyst will read it"], "running": False}
          and held7 == {"running": False, "n": 1, "status": "framing", "input": [False, "Answer, or say what to change"]} and rec7.get("status") == "framing"
          and row7.get("n") == 1 and row7.get("cls") == "sp-row tool read skipped ar-unplaced" and row7["text"][:3] == ["–", "CHECK question", f"the Analyst cannot place “{mod.COLD_POINTER}”"]
          and row7["whole"]
          and re.fullmatch(r"\d+ s", row7["text"][3]) and row7["text"][4:] == ["⌘"] and row7["under"] == "ar-msg arch"
          and t7["said"][-1] == ["Architect", mod.ARCHITECT_PLACED] and t7["notes"][-1][:2] == ["QUESTION", "updated"]
          and (b7["v"], b7["title"], b7["start"]) == ("8 of 8", wording, "Start analysis") and rec7.get("question") == wording
          and [(v["by"], v["changed"], v["brief"]["question"]) for v in f7.get("versions", [])][5:] == [("person", ["question"], pointed), ("architect", ["question"], wording)]
          and [t["who"] for t in f7.get("turns", [])][-2:] == ["reader", "architect"]
          and {k: v for k, v in f7["turns"][-2].items() if k not in ("secs", "cost")} == {"who": "reader", "missing": [mod.COLD_POINTER], "v": 6, "call": 1} and f7.get("read") == [6, 7]
          and used7 == ["Question check", "Architect"]
          and given7.startswith("DATA:\n(no dataset attached") and given7.rstrip().endswith("Reply with the JSON object.")
          and f"\n\nQUESTION:\n{pointed}\n\nBRIEF (agreed with the person before this run):\nWhat the answer is for: {what_for}\nFixed before the run:\n- period: {period}\n\nReply with" in given7,
          (checking, held7, row7, t7["said"][-1], t7["notes"][-1:], b7["v"], b7["title"], f7.get("read"), f7.get("turns", [])[-2:], used7, given7[-500:]))
    rows_s = len(usage_rows(wa, edition, user))
    page.click('#content-brief [data-ar="start"]')
    wait_run_end(page, 1)
    page.wait_for_function("() => responses.length === 1 && !responses[0].status", timeout=60000)
    prompt = turn_prompt(page, 1)
    ran = thread_run(wa, user, tid, cid)
    rep = page.evaluate("""() => { const a = document.getElementById('content-answer');
        return { card: !!document.querySelector('#contentOutput .ar-against') || !!document.querySelector('#content-brief .ar-brief[data-against]'),
                 heads: [...a.querySelectorAll('.markdown-content h2')].map(h => h.textContent), text: a.querySelector('.markdown-content').textContent }; }""")
    page.click("#tab-brief")
    kept = brief_on_screen(page)
    check("a line the coach adds by hand goes on from the step on screen too (0316): added through + Add at the step they came back to, it is one more version - the fourth - made on the brief "
          "that stood there, with its question, and a step that follows that one; the last version is the one in use again, and the next line makes the fifth. The analysis of a brief with "
          "nothing loaded: the Analyst is asked the question of the version the coach went on from, "
          "and reads under it what was agreed and nothing else - what the answer is for, the period that was fixed - with no line for a part that was not said, none for a part left to it, and "
          "none of the checks a run on data makes: the brief shows no such line either. The brief expects nothing, so the report is not asked how it stands against it: no such part, no card, "
          "and no line that says the brief was left unanswered; what did not fit keeps its heading. The Brief tab, read after the run, shows the parts the Analyst got and no other",
          (b_one["v"], b_one["title"], b_one["decision"], b_one["start"]) == ("5 of 5", wording, what_for, "Start analysis") and "at" not in f_one
          and steps_of(f_one)[-1] == (7, 5, 4, [4], 0) and (f_one.get("step"), f_one.get("tip")) == (7, 7) and sorted(f_one.get("aside", {})) == ["3", "6"]
          and [(v["by"], v["brief"]["question"]) for v in f_one.get("versions", [])][2:] == [("architect", own), ("person", wording)]
          and (b6["v"], b6["decision"], b6["period"], b6["measure"], b6["always"]) == ("6 of 6", what_for, period, None, "") and b6["heads"] == ["What it is for", "Period"]
          and f"\n\nQUESTION:\n{wording}\n\nBRIEF (agreed with the person before this run):\nWhat the answer is for: {what_for}\nFixed before the run:\n- period: {period}\n\nYOUR NOTE" in prompt
          and not any(w in prompt for w in ("[always]", "not said", "left to you")) and prompt.startswith("DATA:\n(no dataset attached")
          and ran.get("status") == "answered" and ran.get("question") == wording and ran.get("brief") == {"decision": what_for, "fixed": {"period": period}, "question": wording, "version": 7}
          and ran.get("brief_outcome", {}).get("stated") is False and "does not say how the result stands against the brief" not in ran.get("report", "")
          and not rep["card"] and "Against the brief" not in rep["heads"] and "Did not fit" in rep["heads"] and mod.BARE_DONE in rep["text"]
          and kept["state"] == "run" and kept["heads"] == ["What it is for", "Period"] and (kept["decision"], kept["period"], kept["measure"], kept["thinks"]) == (what_for, period, None, None)
          and (kept["gets"], kept["always"], kept["add"]) == ("", "", ""), (b_one, b6, prompt[:700], ran.get("brief"), ran.get("brief_outcome"), rep["heads"], kept))

    folded = talk_on_screen(page, "#streamOutput .ar-fold .sp-detail")
    fold_head = page.evaluate("() => document.querySelector('#streamOutput .ar-fold summary .kind').textContent")
    kept_way = ran.get("framing", {})
    check("what the run keeps of a conversation that branched (0316): the way to the step it started from, and nothing of the way that was left. The fold above the run names that step - the "
          "eighth of its way - and holds that way's conversation: not the wording the coach gave and then left. On the record the framing's conversation is that way's too - what a later "
          "question may open, and what is remembered of the analysis once it is saved - and the steps of the other way are set aside, with what was said in them",
          fold_head == "brief · step 8" and folded["said"][:4] == t1["said"] and [mod.ARCHITECT_OWN + own] not in [x[1:] for x in folded["said"]] and len(folded["said"]) == 9
          and own not in json.dumps(kept_way.get("turns")) and (kept_way.get("step"), kept_way.get("tip")) == (10, 10) and sorted(kept_way.get("aside", {})) == ["3", "6"]
          and [t.get("text") for t in kept_way["aside"]["3"]["turns"]] == [mod.ARCHITECT_OWN + own, mod.ARCHITECT_BACK] and steps_of(kept_way)[-1] == (10, 9, 7, [7], 2),
          (fold_head, folded["said"], steps_of(kept_way), list(kept_way.get("aside", {}))))
    fold7 = page.evaluate("""() => [...document.querySelectorAll('#streamOutput .ar-fold .sp-detail .sp-row.tool.read')].filter(r => r.children[1].textContent === 'CHECK question').map(r => r.children[2].textContent)""")
    check("Start analysis again (0313): the version the Architect left runs at once - a read holds a start up once: no call of the question check's is made, and the analysis' own calls follow. "
          "What the reader was given is how the Analyst's own first prompt begins, the question apart; the conversation folded above the run keeps the read",
          "Question check" not in [r["agent"] for r in usage_rows(wa, edition, user)[rows_s:]] and len(usage_rows(wa, edition, user)) > rows_s
          and prompt.startswith(given7.rstrip()[:-len("Reply with the JSON object.")].rstrip().replace(pointed, wording) + "\n\nYOUR NOTE")
          and fold7 == [f"the Analyst cannot place “{mod.COLD_POINTER}”"] and ran.get("framing", {}).get("read") == [6, 7] and len(ran.get("framing", {}).get("versions", [])) == 7,
          ([r["agent"] for r in usage_rows(wa, edition, user)[rows_s:]][:4], prompt[:400], given7[:400], fold7, ran.get("framing", {}).get("read")))

    # a question that follows it, the switch still on: the brief starts from what the answer was for; a reading, a part opened, an analysis built on
    report = (thread_run(wa, user, tid, cid).get("report") or "").strip()
    opens = re.sub(r"^#+ *", "", report.splitlines()[0]) if report else ""
    page.fill("#queryInput", mod.FOLLOW_QUESTION)
    page.click("#submitQuery")
    wait_text(page, "#chainPosition", "chain 2 of 2", 15000)
    page.wait_for_selector('#content-brief .ar-brief[data-state="framing"]', timeout=15000)
    architect_said(page, 3)
    f1, t5, s5 = brief_on_screen(page), talk_on_screen(page), saved_on_screen(page)
    cid2 = page.evaluate("() => currentData.chain_id")
    recf = thread_run(wa, user, tid, cid2).get("framing", {})
    pane = page.evaluate("() => [...document.querySelectorAll('#streamOutput .sp-stream > *')].map(x => x.classList.contains('sp-row') ? [...x.children].map(c => c.textContent) : x.className)")
    read2 = read_last()
    saved_n = recf.get("saved") or 0
    check("a question that follows the analysis, typed with the switch on: its brief starts from what the last answer was for and says so - the period fixed for the question before is not in it. "
          "The Architect has the saved analyses read on a follow-up too - their row, the analyses found listed under it, and it goes on at once - then opens the report of the analysis before: a "
          "row that says what was read and how long it is, and again it goes on at once, and speaks from what it read. The record keeps the reading and the part opened as turns of the "
          "conversation - of the part its name, never its text",
          recf.get("versions", [{}])[0] == {"n": 1, "by": "person", "changed": ["from the last brief"], "brief": {"decision": what_for, "question": mod.FOLLOW_QUESTION}}
          and f1["decision"] == what_for and f1["period"] is None and f1["title"] == mod.FOLLOW_QUESTION
          and [t["who"] for t in recf.get("turns", [])] == ["architect", "memory", "architect", "opened", "architect"]
          and recf["turns"][3] == {"who": "opened", "what": "report", "label": "the report", "chars": len(report)} and "## Did not fit" in report and "## Did not fit" not in json.dumps(recf)
          and t5["said"] == [["You", mod.FOLLOW_QUESTION], ["Architect", mod.ARCHITECT_LOOKING], ["Architect", mod.ARCHITECT_OPENING], ["Architect", mod.ARCHITECT_OPENED + opens]]
          and t5["choices"] == mod.ARCHITECT_BUILD and len(pane) == 7 and pane[2][:2] == ["✓", "MEMORY"] and pane[3] == "ar-found" and pane[5] == ["✓", "READ", "the report", f"{len(report):,} characters"]
          and [pane[k] for k in (1, 4, 6)] == ["ar-msg arch"] * 3 and len(s5["left"]) >= 1 and [it["asked"] for it in s5["right"]] == [it["asked"] for it in s5["left"]]
          and s5["built"] == [] and s5["boxes"] == 0, (recf.get("versions", [{}])[0], [t["who"] for t in recf.get("turns", [])], t5, pane, s5))
    check("what the Architect read for the message it wrote from the report: the analysis before in a few lines, with what there is to open and a line to each of its cells; that no reading can be "
          "made again before the coach has spoken; what it opened, named in the conversation; and the report itself, whole, in a block of its own under the conversation",
          f"EARLIER (the analyses this question follows, oldest first):\n[1] Q: {wording}\nFound: " in read2 and "\nTo open: its report, its conversation, its cells:\n[cell 1] " in read2      # the prompt's dialog drops a line's indent
          and f"\n\nSAVED: {saved_n} (no reading can be made now: they were read since the person last spoke)\n\nQUESTION:\n{mod.FOLLOW_QUESTION}\n" in read2 and saved_n >= 1
          and f"Architect: {mod.ARCHITECT_OPENING}\nOpened: the report\n\nOPENED (in view until the person next speaks):\n--- the report ---\n{report.splitlines()[0]}\n" in read2
          and "## Did not fit" in read2.split("OPENED (in view")[-1] and read2.rstrip().endswith("Reply with the JSON object."), read2[-1200:])
    tell(page, choice=0)
    f2, t6, s6 = brief_on_screen(page), talk_on_screen(page), saved_on_screen(page)
    last6 = (thread_run(wa, user, tid, cid2).get("framing", {}).get("versions") or [{}])[-1]
    read3 = read_last()
    first = s5["left"][0] if s5["left"] else {}
    check("'Build on it', the coach's word: the Architect names the analysis, and the brief builds on it - a version of its own, made from the answer: Builds on, with View and a cross, and the tag "
          "under the brief - so the Analyst will get its passages and can open it. The report the Architect opened is no longer in what it reads: the coach has spoken since, and the "
          "conversation says only that it was opened",
          t6["said"][-2:] == [["You", mod.ARCHITECT_BUILD[0]], ["Architect", mod.ARCHITECT_BUILT]] and f2["changed"] == ["builds"] and s6["built"] == [{**first, "cross": True}]
          and [it["tag"] for it in s6["right"]] == ["built on"] + [""] * (len(s6["right"]) - 1) and len(s6["right"]) == len(s5["right"]) and s6["boxes"] == 0
          and (last6.get("by"), last6.get("why")) == ("architect", "answer") and {(x["thread"], x["run"]) for x in last6.get("brief", {}).get("saved", [])} == {tuple(first.get("view") or ())}
          and all(x.get("accepted") is True for x in last6.get("brief", {}).get("saved", []))
          and "OPENED (" not in read3 and "\nOpened: the report\n" in read3 and "## Did not fit" not in read3, (t6["said"][-2:], f2["changed"], s6, last6, read3[-500:]))


def figures_on_screen(page):
    """The figures on the Brief tab as the coach sees them: the part's heading; each panel's number, title and tag - none where it has no draft -, whether it is marked as changed, has its
    cross and stands as a drawn draft - then, of its plot: the key it is kept under, whether a drawing stands in its place and under which title, whether it is marked as made up and what
    stands across it; the line of its grey window, where that shows; the line under it; whether it takes the whole row; and the conversation's rows about the figures."""
    return page.evaluate("""() => { const r = document.querySelector('#content-brief .ar-brief'), figs = [...r.querySelectorAll('.ar-fig')], row = r.querySelector('.ar-figs');
        const shown = x => !!x && getComputedStyle(x).display !== 'none', wide = x => Math.round(x.getBoundingClientRect().width);
        return { head: [...r.querySelectorAll('h3')].map(h => h.textContent).filter(h => /look/.test(h)),
                 figs: figs.map(f => { const plot = f.querySelector('.plot'), drawing = plot && plot.querySelector('svg');
                     return { n: f.querySelector('.n').textContent, title: f.querySelector('.t').textContent, tag: (f.querySelector('.tag') || {}).textContent || '',
                              changed: f.classList.contains('changed'), cross: !!f.querySelector('[data-ar="unfigure"]'), drawn: f.classList.contains('drawn'),
                              plot: plot ? { key: plot.dataset.key, live: !!drawing, head: drawing ? (drawing.querySelector('text') || {}).textContent || '' : '', made: plot.dataset.madeUp === '1',
                                             across: drawing ? [...drawing.querySelectorAll('text[transform]')].map(t => t.textContent) : [] } : null,
                              window: shown(f.querySelector('.ar-wait')) ? f.querySelector('.ar-wait').textContent : '', cap: (f.querySelector('.cap') || {}).textContent || '',
                              row: !!row && wide(f) === wide(row) }; }),
                 rows: [...document.querySelectorAll('#streamOutput .sp-stream > .sp-row.tool.read')].filter(x => x.children[1].textContent === 'FIGURES').map(x => [...x.children].slice(1).map(c => c.textContent)) }; }""")


def walk_draft(page, st, mod, wa, edition, user):
    """The figures and their draft (2026-11-18, docs/ARCHITECT_DESIGN.md §2.19, §2.20), on data. Asked to show the figures, the Architect describes them, and a draft of each is drawn in the
    same exchange: a cell written by the model that drafts, run where no data is, each plot kept beside the thread's record and drawn on the Brief tab - on made-up numbers what the data will
    give, computed what follows from a rule. Asked for another order, the Architect names the figures by their numbers and nothing is drawn again. The coach takes one out with its cross and
    goes back a step. The analysis then runs under the brief: the Analyst reads the figures that stand, the step that draws reads the same lines and the cell that drew their draft -
    its first reply leaves one out, and it is asked again before anything runs - and the report holds each agreed figure under its title."""
    page.evaluate("handleNewConversation()")
    page.wait_for_url("**/?new=true", timeout=60000)
    page.wait_for_selector("#queryInput", state="visible", timeout=60000)
    page.app_ready()
    page.wait_for_function("() => /Ready|Local|Docker/.test(document.querySelector('#containerStatusText').textContent)", timeout=60000)
    page.set_input_files("#primaryFile", st.dataset)
    page.wait_for_selector(".primary-dataset-pill", timeout=60000)
    page.wait_for_timeout(500)
    if page.evaluate("() => document.getElementById('architectSwitch').getAttribute('aria-pressed')") != "true":
        page.click("#architectSwitch")
    page.fill("#queryInput", mod.FIGURES_QUESTION)
    page.click("#submitQuery")
    page.wait_for_selector("#content-brief .ar-brief", timeout=15000)
    architect_said(page, 1)
    tid, cid = page.evaluate("() => [currentData.thread_id, currentData.chain_id]")
    shut = "() => { const m = document.getElementById('agentInstructionsModal'); if (m) m.style.display = 'none'; const u = document.getElementById('userInstructions'); if (u) u.textContent = ''; }"
    read = lambda button, mark: (page.click(button), page.wait_for_function("(mark) => { const u = document.getElementById('userInstructions'); return u && u.textContent.includes(mark); }", arg=mark, timeout=15000),      # noqa: E731
                                 page.inner_text("#userInstructions"), page.evaluate(shut))[2]
    drawn = lambda n: page.wait_for_function("(n) => document.querySelectorAll('#content-brief .ar-fig.drawn .plot svg').length === n", arg=n, timeout=30000)      # noqa: E731
    want = mod.described("C", "A")
    line, boxes, target = (f["title"] for f in want)
    made = "The numbers are made up. The analysis puts in the real ones."
    lines_of = lambda *figs: "".join(f'{k}. "{f["title"]}" - {"a line chart" if f["kind"] == "line" else "box plots"}; x: {f["x"]}; y: {f["y"]}; holds: {", ".join(s["name"] for s in f["series"])}; '      # noqa: E731
                                     f'to make clear: {f["note"]}\n' for k, f in enumerate(figs, 1))
    f0, rows0 = figures_on_screen(page), len(usage_rows(wa, edition, user))
    # what stands between the reply and its drafts: the first the page shows of the figures, taken as it is drawn
    page.evaluate("""() => { window.__drawing = null;
        const watch = new MutationObserver(() => {
            const live = [...document.querySelectorAll('#content-brief .ar-fig .ar-wait.live')], row = document.querySelector('#streamOutput .sp-stream > .sp-row.pending');
            if (!live.length || !row) return;
            watch.disconnect();
            const input = document.getElementById('queryInput'), above = row.previousElementSibling;
            const words = m => { const c = m.cloneNode(true); c.querySelectorAll('.who, .ar-choices').forEach(x => x.remove()); return c.textContent; };
            window.__drawing = { above: above && above.matches('.ar-msg.arch') ? words(above) : '', row: [...row.children].map(c => c.textContent).filter(Boolean), hold: [input.disabled, input.placeholder],
                figs: live.map(w => { const fig = w.closest('.ar-fig'), box = w.getBoundingClientRect();
                    return [fig.querySelector('.t').textContent, [...fig.children].map(c => c.className), w.textContent, getComputedStyle(w).display, Math.round(box.height),
                            getComputedStyle(w.querySelector('span')).animationName]; }) };
        });
        watch.observe(document.body, { childList: true, subtree: true }); }""")
    tell(page, mod.ARCHITECT_SHOW)
    drawn(3)
    during = page.evaluate("() => window.__drawing")
    check("while the draft is drawn (0311): the Architect's reply stands, the row under it says what is being done - DRAWING A DRAFT - and the composer is held with the same words. Each of "
          "the three figures is its title over a grey window that shows, with one line in its middle - Drawing a draft… - that breathes; none is tagged as a draft, and nothing else is "
          "in its place",
          during == {"above": mod.ARCHITECT_DRAFTING, "row": ["DRAWING A DRAFT"], "hold": [True, "A draft of the figures is being drawn"],
                     "figs": [[title, ["hd", "ar-wait live"], "Drawing a draft…", "grid", 200, "ar-wait"] for title in (line, boxes, target)]}, during)
    f1, t1, b1 = figures_on_screen(page), talk_on_screen(page), brief_on_screen(page)
    ran1 = thread_run(wa, user, tid, cid)
    rec1 = ran1.get("framing", {})
    v1, n1 = (rec1.get("versions") or [{}])[-1], len(rec1.get("versions", []))
    keys = (v1.get("keys") or []) + [None] * 3
    kept = [os.path.join(wa, "storage", user, "drafts", str(tid), str(cid), f"{k}.json") for k in keys[:3]]
    plots = [json.load(open(p, encoding="utf-8")) if os.path.exists(p) else {} for p in kept]
    served = page.evaluate("(u) => window.authService.fetch(u).then(r => r.json().then(j => [r.status, j]))", f"/architect/draft/{tid}/{cid}/{keys[2]}")
    absent = page.evaluate("(u) => window.authService.fetch(u).then(r => r.status)", f"/architect/draft/{tid}/{cid}/000000000000")
    check("asked to show the figures, the Architect describes them and a draft of each is drawn in the same exchange: the Brief tab has a part for them, under a plain heading - a panel to a "
          "figure, numbered, as changed in this version, with a cross, each across the whole row. What the data will give is a draft on made-up numbers: the tag says so, a line under the "
          "figure says so, and the words stand across the plot; the target, which follows from its rule, is a draft with none of that. Each plot is drawn in its figure's place, under its "
          "title; the grey window under it does not show, and nothing of how the Architect described the figure is on the page (0311). A row under the Architect's message says three were "
          "drawn, with the seconds and the button to the draft's prompt, and the reply's choices can still be clicked. Before, the brief had no such part",
          f0["head"] == [] and f0["figs"] == [] and f1["head"] == ["What it will look like"]
          and [(f["n"], f["title"], f["tag"], f["changed"], f["cross"], f["drawn"], f["row"], f["window"]) for f in f1["figs"]]
          == [("1", line, "draft · made-up numbers", True, True, True, True, ""), ("2", boxes, "draft · made-up numbers", True, True, True, True, ""), ("3", target, "draft", True, True, True, True, "")]
          and [f["plot"] for f in f1["figs"]] == [{"key": keys[0], "live": True, "head": line, "made": True, "across": ["made-up numbers"]},
                                                 {"key": keys[1], "live": True, "head": boxes, "made": True, "across": ["made-up numbers"]},
                                                 {"key": keys[2], "live": True, "head": target, "made": False, "across": []}]
          and [f["cap"] for f in f1["figs"]] == [made, made, ""] and not any(f["note"] in page.inner_text("#content-brief") for f in want)
          and len(f1["rows"]) == 1 and f1["rows"][0][:2] == ["FIGURES", "3 drawn"] and bool(re.fullmatch(r"\d+ s", f1["rows"][0][2])) and f1["rows"][0][3:] == ["⌘"]
          and t1["said"][-2:] == [["You", mod.ARCHITECT_SHOW], ["Architect", mod.ARCHITECT_DRAFTING]] and t1["choices"] == mod.ARCHITECT_YES and (b1["v"], n1) == ("2 of 2", 3), (f0, f1, t1["said"][-2:], t1["choices"], b1["v"]))
    check("the draft on the record and on disk: the figures are one more version of the Architect's, each named as changed, each a description and no more, with its key beside the version; "
          "the framing says of each key what its draft is - made up, made up, computed - and the round is the conversation's last turn. The cell that drew stands on the run's record with "
          "the keys it drew; each plot is a file of its own beside the thread's record, the target's with its rule's numbers and the word that it is computed. The page is served a plot by "
          "its key, and none under a key that has no draft. Two calls were made and logged: the Architect's and the draft's",
          (v1.get("by"), v1.get("why"), v1.get("changed")) == ("architect", "answer", ["figures.0", "figures.1", "figures.2"]) and len(set(keys[:3])) == 3 and None not in keys[:3]
          and [f["title"] for f in v1.get("brief", {}).get("figures", [])] == [line, boxes, target] and "points" not in json.dumps(v1.get("brief", {}))
          and rec1.get("drafts") == {keys[0]: {"basis": "made up"}, keys[1]: {"basis": "made up"}, keys[2]: {"basis": "computed"}} and rec1.get("draft_calls") == 1
          and {k: v for k, v in rec1.get("turns", [{}])[-1].items() if k not in ("secs", "cost")}
          == {"who": "draft", "drawn": [{"title": line, "basis": "made up"}, {"title": boxes, "basis": "made up"}, {"title": target, "basis": "computed"}], "v": n1, "call": 1}
          and ran1.get("drafts") == [{"code": mod.draft_cell([line, boxes, target]), "keys": keys[:3]}]
          and all(os.path.isfile(p) for p in kept) and [(p.get("layout") or {}).get("meta") for p in plots] == [None, None, "computed"]
          and [(p.get("layout", {}).get("title") or {}).get("text") for p in plots] == [line, boxes, target] and plots[2]["data"][0]["y"] == [4.0, 4.2, 4.41, 4.63, 4.86, 5.11]
          and [t.get("name") for t in plots[0]["data"]] == ["regime C", "regime A"] and served == [200, {"plot": plots[2]}] and absent == 404
          and len(usage_rows(wa, edition, user)) == rows0 + 2, (v1, rec1.get("drafts"), rec1.get("turns", [{}])[-1], ran1.get("drafts"), served, absent, len(usage_rows(wa, edition, user)) - rows0))

    # the draft's prompt; then another order, asked for in words: the Architect names the figures by their numbers, and nothing is drawn again
    asked = read('#streamOutput .sp-stream > .sp-row .sp-prompt[data-agent="Draft"]', "FIGURES TO DRAW:")
    rows1 = len(usage_rows(wa, edition, user))
    tell(page, mod.ARCHITECT_SWAP)
    drawn(3)
    f2 = figures_on_screen(page)
    read2 = read("#streamOutput .sp-stream > .ar-msg.arch .sp-prompt >> nth=-1", "CONVERSATION:")
    ran2 = thread_run(wa, user, tid, cid)
    rec2 = ran2.get("framing", {})
    v2 = (rec2.get("versions") or [{}])[-1]
    check("the draft was written from the question as it stands and the figures in words - the kind, what is on each axis, what it holds, what it is to make clear - and nothing of the data. "
          "Asked for the second figure first, the Architect read the figures each under its number, and what the draft came to as a line of the conversation; its reply names the figures by "
          "number, the first two the other way round: the panels change places with their drafts - each under the key it had - the two that moved marked as changed. One more version of "
          "the Architect's, and one call: nothing was drawn again",
          asked.startswith(f"QUESTION:\n{mod.FIGURES_QUESTION}\n\nFIGURES TO DRAW:\n{lines_of(*want)}\nReply with the cell.") and "regime B" not in asked and "yield_t_ha" not in asked
          and f"\nfigures:\n{lines_of(*want)}".replace("\n1. ", "\n- [1] ").replace("\n2. ", "\n- [2] ").replace("\n3. ", "\n- [3] ") in read2 and "sketched" not in read2
          and f'\nDraft of the figures: drawn - "{line}" (on made-up numbers), "{boxes}" (on made-up numbers), "{target}" (computed)\nPerson: {mod.ARCHITECT_SWAP}' in read2
          and [(f["n"], f["title"], f["changed"], f["drawn"], f["plot"]["key"], f["plot"]["live"]) for f in f2["figs"]]
          == [("1", boxes, True, True, keys[1], True), ("2", line, True, True, keys[0], True), ("3", target, False, True, keys[2], True)]
          and len(f2["rows"]) == 1 and (v2.get("by"), v2.get("changed"), v2.get("keys")) == ("architect", ["figures.0", "figures.1"], [keys[1], keys[0], keys[2]])
          and v2["brief"]["figures"][1] == v1["brief"]["figures"][0] and [t["who"] for t in rec2.get("turns", [])].count("draft") == 1 and rec2.get("draft_calls") == 1 and len(ran2.get("drafts", [])) == 1
          and len(usage_rows(wa, edition, user)) == rows1 + 1, (asked[:700], read2[-1500:], f2, v2))

    # the cross on the third figure, and the arrow back a step
    rows2 = len(usage_rows(wa, edition, user))
    page.click('#content-brief .ar-fig [data-ar="unfigure"][data-path="figures.2"]')
    page.wait_for_function("(n) => { const r = document.querySelector('#content-brief .ar-brief'); return r && JSON.parse(r.dataset.framing).versions.length === n; }", arg=n1 + 2, timeout=15000)
    drawn(2)
    f3, b3 = figures_on_screen(page), brief_on_screen(page)
    v3 = (thread_run(wa, user, tid, cid).get("framing", {}).get("versions") or [{}])[-1]
    page.click('#content-brief [data-ar="step"][data-step="-1"]')
    drawn(3)
    f4, b4 = figures_on_screen(page), brief_on_screen(page)
    page.click('#content-brief [data-ar="step"][data-step="1"]')
    drawn(2)
    f5 = figures_on_screen(page)
    check("the cross on a figure takes it out: one more version, the coach's, that names the part as changed - two panels stay, each with its draft, and no model was called. The arrow back "
          "shows the step before with its three drafts, and Start analysis names that step; the arrow forward shows the two again",
          [(f["title"], f["drawn"], f["plot"]["key"], f["plot"]["live"]) for f in f3["figs"]] == [(boxes, True, keys[1], True), (line, True, keys[0], True)] and not any(f["changed"] for f in f3["figs"])
          and b3["v"] == "4 of 4" and b3["start"] == "Start analysis"
          and (v3.get("by"), v3.get("changed"), v3.get("keys")) == ("person", ["figures"], [keys[1], keys[0]]) and [f["title"] for f in v3.get("brief", {}).get("figures", [])] == [boxes, line]
          and len(usage_rows(wa, edition, user)) == rows2
          and [(f["title"], f["drawn"]) for f in f4["figs"]] == [(boxes, True), (line, True), (target, True)] and b4["v"] == "3 of 4" and b4["start"] == "Start analysis from step 3"
          and [f["title"] for f in f5["figs"]] == [boxes, line], (f3, v3, b4["v"], b4["start"]))

    # Start analysis: the Analyst reads the figures that stand, the step that draws reads them and the cell that drew their draft
    page.evaluate("setMode('deep')")
    page.click('#content-brief [data-ar="start"]')
    wait_run_end(page, 1)
    page.wait_for_function("() => responses.length === 1 && !responses[0].status", timeout=60000)
    prompt = turn_prompt(page, 1)
    ran = thread_run(wa, user, tid, cid)
    drew = []
    for k in range(page.locator('.sp-turn .sp-prompt[data-agent="Figures"]').count()):
        drew.append(read(f'.sp-turn .sp-prompt[data-agent="Figures"] >> nth={k}', "THE REPORT, AS WRITTEN:"))
        page.wait_for_timeout(200)
    steps = [(t["kind"], t.get("cell_no"), (t.get("stdout") or "").strip()[:120], [f.get("title") for f in t.get("figures", []) if isinstance(f, dict)]) for t in ran.get("turns", []) if t.get("step") == "figures"]
    lines = lines_of(want[1], want[0])
    saw = (f'THE DRAFT THE PERSON SAW (it drew "{boxes}", "{line}" - on made-up numbers: "{boxes}", "{line}"):\n```python\n' + mod.draft_cell([line, boxes, target]) + "\n```\n")
    answer = page.inner_text("#content-answer")
    page.click("#tab-brief")
    drawn(2)
    f6, b6 = figures_on_screen(page), brief_on_screen(page)
    check("Start analysis under a brief with figures: the Analyst reads the two that stand in its BRIEF block, numbered, in words - the one taken out is not in its prompt, nor the draft's "
          "cell. The step that draws reads the same lines under its question, to draw first and under their titles, and under them the cell that drew their draft, with the word that both "
          "stand on made-up numbers. Its first reply left the second figure out: nothing ran, the attempt is on the record with what was left out, and it was asked again with that title; "
          "its next cell drew both from the data, each under its agreed title. The report's Figures part holds the two, with no line about a figure not drawn. The Brief tab, read after "
          "the run, still shows the two drafts - with no cross - and the run keeps the cell that drew them",
          ("\nFigures agreed with the person:\n" + lines) in prompt and target not in prompt and "THE DRAFT THE PERSON SAW" not in prompt
          and len(drew) == 2 and drew[0].startswith(f"QUESTION:\n{mod.FIGURES_QUESTION}\n\nTHE FIGURES AGREED WITH THE PERSON (draw these first, in this order, each as described and under its title, word for word):\n"
                                                    f"{lines}\n{saw}\nTHE REPORT, AS WRITTEN:\n")
          and "YOUR LAST REPLY LEFT OUT" not in drew[0] and drew[0].count("THE DRAFT THE PERSON SAW") == 1
          and f'YOUR LAST REPLY LEFT OUT a figure agreed with the person (attempt 1 of 4): "{line}". Nothing was run.' in drew[1]
          and [s[0] for s in steps] == ["error", "cell"] and steps[0][2] == f'the reply left out a figure agreed with the person: "{line}"' and steps[1][1] is not None and steps[1][3] == [boxes, line]
          and ran.get("status") == "answered" and [f["title"] for f in ran.get("brief", {}).get("figures", [])] == [boxes, line] and ran.get("drafts") == ran1.get("drafts")
          and f"## Figures\n\n- [fig {steps[1][1]}] {boxes[:1].lower() + boxes[1:]}\n- [fig {steps[1][1]}] {line[:1].lower() + line[1:]}" in ran.get("report", "") and "not drawn" not in ran.get("report", "")
          and "Figures" in answer and line[1:] in answer
          and b6["state"] == "run" and [(f["title"], f["cross"], f["drawn"], f["plot"]["key"], f["plot"]["live"], f["tag"]) for f in f6["figs"]]
          == [(boxes, False, True, keys[1], True, "draft · made-up numbers"), (line, False, True, keys[0], True, "draft · made-up numbers")],
          (prompt[:900], [d[:1500] for d in drew], steps, ran.get("report", "")[-400:], f6))

    # a branch of this analysis (0320, docs/BRANCH_DESIGN.md §5): back to its first turn, a hint, with the Architect still switched on
    rows3 = len(usage_rows(wa, edition, user))
    open_turn_map(page)
    turn_box(page, "(sub) => sub.startsWith('Turn 1 ·')")
    page.wait_for_function("() => BranchUI.standing() !== null", timeout=10000)
    page.fill("#queryInput", mod.BRANCH_HINT)
    page.click("#submitQuery")
    wait_run_end(page, 2)
    page.wait_for_function("() => responses.length === 2 && !responses[1].status", timeout=60000)
    of_b = page.evaluate("""() => { const e = responses[currentResponseIndex], s = document.querySelector('#streamOutput .sp-stream'), brief = document.querySelector('#content-brief .ar-brief');
        return { chain: e.chain_id, branch: e.branch, q: e.queryText, on: document.getElementById('architectSwitch').getAttribute('aria-pressed'),
                 first: s.firstElementChild.className, fold: (s.querySelector(':scope > .ar-fold .kind') || {}).textContent || '',
                 turns: [...s.querySelectorAll(':scope > .sp-turn[data-turn]')].filter(c => /^\\d+$/.test(c.getAttribute('data-turn'))).map(c => [Number(c.getAttribute('data-turn')), c.classList.contains('kept')]),
                 hints: [...s.querySelectorAll(':scope > .sp-hint')].map(h => h.textContent), tabs: [...document.querySelectorAll('#tabContainer .tab')].map(t => t.textContent.trim()),
                 brief: brief ? [brief.dataset.state, brief.dataset.chain] : null, made: ArchitectUI.mark(e) }; }""")
    ran_b = thread_run(wa, user, tid, of_b["chain"])
    calls_b = [r["agent"] for r in usage_rows(wa, edition, user)[rows3:]]
    check("a branch of a framed analysis (0320): the hint starts it at once - the Architect, switched on, is not asked, and no call reads the question again - and it runs under the same "
          "brief: the brief's row stands above the run, the turn it keeps under that, then the hint and its own turns; the Brief tab is there for the new chain, to be read; the record "
          "keeps the brief, with its figures and their drafts, and the question; the report follows the hint, and the figures agreed are drawn again",
          of_b["on"] == "true" and calls_b and "Architect" not in calls_b and "Question check" not in calls_b
          and of_b["branch"] == {"of": cid, "turn": 1, "hint": mod.BRANCH_HINT} and of_b["q"] == mod.FIGURES_QUESTION
          and of_b["first"].startswith("sp-turn ar-fold") and of_b["fold"].startswith("brief · step ") and of_b["turns"][0] == [1, True] and all(not kept for _, kept in of_b["turns"][1:])
          and len(of_b["turns"]) >= 3 and of_b["hints"] == ["From turn 1" + mod.BRANCH_HINT] and "Brief" in of_b["tabs"] and of_b["brief"] == ["run", str(of_b["chain"])] and of_b["made"] == "Architect"
          and ran_b.get("status") == "answered" and ran_b.get("branch") == {"of": str(cid), "turn": 1} and ran_b.get("brief") == ran.get("brief") and ran_b.get("drafts") == ran.get("drafts")
          and ran_b.get("question") == ran.get("question") and "## Each soil type on its own" in ran_b.get("report", "")
          and [[f.get("title") for f in t.get("figures", []) if isinstance(f, dict)] for t in ran_b.get("turns", []) if t.get("step") == "figures" and t.get("kind") == "cell"][-1:] == [[boxes, line]],
          (of_b, calls_b, ran_b.get("status"), ran_b.get("branch"), ran_b.get("report", "")[-300:]))

    # ---- the branch saved (0321, docs/BRANCH_DESIGN.md §2, decisions 2 and 13) ----
    # The thread is saved from the branch: both ways are stored, and memory takes the branch - with its hint - and leaves the first run. Opened again in a
    # new workflow, the saved thread is one analysis with its branch; a turn of it is gone back to and the analysis goes on a third way - nothing is locked
    storage, b_id = os.path.join(wa, "storage", user), str(of_b["chain"])
    logs_at = os.path.join(os.path.dirname(wa), "logs", "webapp.log")

    def save_here():
        page.click("#saveButton")
        page.wait_for_selector("#saveMenu", state="visible", timeout=10000)
        page.click("#saveMenu .it[data-act='favourite']")
        page.wait_for_function("() => document.getElementById('saveButton').classList.contains('saved')", timeout=30000)

    def remembered(until):
        view = kept_memory(storage, until)
        return {r["run"]: r for r in view["runs"] if r["thread"] == str(tid)}, view["not_read"].get("left", 0)

    left_before = kept_memory(storage)["not_read"].get("left", 0)
    save_here()
    mem_b, left_b = remembered(lambda v: any(r["run"] == b_id for r in v["runs"]))
    stored = sorted(f[:-5] for f in os.listdir(os.path.join(storage, "favourites", str(tid))))
    check("a thread saved from a branch (0321): both ways are stored - every branch is, with the thread - and memory takes the branch, picked, with the hint it was made under, its "
          "brief and its own report; the first run, which the person left, is no memory and is counted as left",
          stored == sorted([str(cid), b_id]) and list(mem_b) == [b_id] and mem_b[b_id]["marks"] == ["picked"] and mem_b[b_id]["hints"] == [{"turn": 1, "text": mod.BRANCH_HINT}]
          and mem_b[b_id]["question"] == mod.FIGURES_QUESTION and "## Each soil type on its own" in mem_b[b_id]["report"] and mem_b[b_id]["brief"] and left_b == left_before + 1,
          (stored, list(mem_b), mem_b.get(b_id, {}).get("hints"), left_before, left_b))
    saved_b = page.evaluate("(a) => window.authService.fetch('/architect/saved/' + a[0] + '/' + a[1]).then(r => r.json())", [str(tid), b_id])
    page.evaluate("handleNewConversation()")
    page.wait_for_url("**/?new=true", timeout=60000)
    page.wait_for_selector("#queryInput", state="visible", timeout=60000)
    page.app_ready()
    page.wait_for_function("() => /Ready|Local|Docker/.test(document.querySelector('#containerStatusText').textContent)", timeout=60000)
    page.set_input_files("#primaryFile", st.dataset)
    page.wait_for_selector(".primary-dataset-pill", timeout=60000)
    page.wait_for_timeout(500)
    page.evaluate("(a) => loadThreadContent(a[0], a[1])", [str(tid), b_id])
    page.wait_for_function("(c) => responses.length === 2 && String(currentData.chain_id) === c && !!document.querySelector('#streamOutput .sp-turnmap')", arg=b_id, timeout=30000)
    page.wait_for_timeout(500)
    again = page.evaluate("""() => ({ branches: responses.map(r => r.branch ? [String(r.branch.of), r.branch.turn, r.branch.hint] : null), analyses: BranchUI.analyses().map(e => String(e.chain_id)),
        place: BranchUI.place(), badge: (document.querySelector('#streamOutput .sp-turnmap .n') || {}).textContent || '', hints: [...document.querySelectorAll('#streamOutput .sp-hint')].map(h => h.textContent) })""")
    page.evaluate("showWorkflowMap()")
    page.wait_for_selector("#workflowMapModal .wf-node", timeout=10000)
    thread_boxes = page.evaluate("() => [...document.querySelectorAll('#workflowMapModal .wf-node')].map(n => (n.querySelector('.wf-node-branches') || {}).textContent || '')")
    page.evaluate("document.getElementById('workflowMapModal').style.display = 'none'")
    map_again = open_turn_map(page)
    check("the saved thread opened again (0321): its two chains are one analysis, the branch saying what it went on from, after which turn and under what hint - from the thread's "
          "record; the Workflow map has one box, with its branch; the Analysis map shows both ways, the branch's first turn marked; and the saved analysis, opened to read, says its hint",
          again["branches"] == [None, [str(cid), 1, mod.BRANCH_HINT]] and again["analyses"] == [b_id] and again["place"] == {"i": 1, "n": 1} and again["badge"] == "1"
          and again["hints"] == ["From turn 1" + mod.BRANCH_HINT] and thread_boxes == ["1 branch"]
          and map_again["sub"] == f"{len(map_again['boxes'])} turns · 1 branch" and [x[1].split(" · ")[0] for x in map_again["boxes"]] == ["Turn 1", "Turn 2", "Turn 2", "Turn 3"]
          and saved_b.get("hints") == [{"turn": 1, "text": mod.BRANCH_HINT}], (again, thread_boxes, map_again["sub"], map_again["boxes"], saved_b.get("hints")))
    # the branch button on a turn's card (0323): the way to a turn without the map. The branch on screen has one on the turn it kept and one on its own
    # working turn, none on its report or on the cards that are no turns; a click goes back to the turn, a second click on the same button back to the end
    cards = page.evaluate("""() => [...document.querySelectorAll('#streamOutput .sp-stream > .sp-turn')].map(c => { const b = c.querySelector('summary .sp-branch'), p = c.querySelector('summary .sp-prompt');
        return { turn: c.getAttribute('data-turn'), kept: c.classList.contains('kept'), title: b ? b.getAttribute('title') : null, x: b ? Math.round(b.getBoundingClientRect().left) : null,
                 before: b && p ? b.getBoundingClientRect().right <= p.getBoundingClientRect().left : null, end: p ? Math.round(p.getBoundingClientRect().right) : null,
                 level: b && p ? Math.abs(b.getBoundingClientRect().top - p.getBoundingClientRect().top) < 1 && Math.abs(b.getBoundingClientRect().height - p.getBoundingClientRect().height) < 1 : null,
                 middle: p ? Math.abs((p.getBoundingClientRect().top + p.getBoundingClientRect().bottom) - (c.querySelector('summary').getBoundingClientRect().top + c.querySelector('summary').getBoundingClientRect().bottom)) < 2 : null }; })""")
    own_btn = "#streamOutput .sp-stream > .sp-turn[data-turn='2'] > summary .sp-branch"
    was_open = page.evaluate("""() => document.querySelector("#streamOutput .sp-stream > .sp-turn[data-turn='2']").open""")
    page.click(own_btn)
    page.wait_for_function("() => BranchUI.standing() !== null", timeout=10000)
    lit = page.evaluate("""(sel) => { const b = document.querySelector(sel), accent = getComputedStyle(document.querySelector('#streamOutput .sp-turn .n')).color;
        return { at: BranchUI.standing().turn, lit: getComputedStyle(b).color === accent, other: getComputedStyle(document.querySelector("#streamOutput .sp-turn[data-turn='1'] > summary .sp-branch")).color === accent,
                 hidden: getComputedStyle(document.querySelector("#streamOutput .sp-stream > .sp-turn[data-turn='3']")).display, words: document.getElementById('queryInput').placeholder,
                 open: document.querySelector("#streamOutput .sp-stream > .sp-turn[data-turn='2']").open }; }""", own_btn)
    page.click(own_btn)
    page.wait_for_function("() => BranchUI.standing() === null", timeout=10000)
    whole = page.evaluate("""() => getComputedStyle(document.querySelector("#streamOutput .sp-stream > .sp-turn[data-turn='3']")).display""")
    by_turn = {c["turn"]: c for c in cards}
    check("the branch button on a turn's card (0323): every turn the analysis can go on from has one - the turn the branch kept and its own working turn -, the report's card and the "
          "cards that are no turns have none; it stands before the prompt's button, on its line and of its height, in the middle of the card's head; the prompt's stays at the card's end, and the kept "
          "turn's - a card with no prompt - stands in the same column. A click goes back to the turn without opening the card: the pane ends there, the button is lit, the composer asks for the hint; a second click brings the end back",
          [c["turn"] for c in cards if c["title"]] == ["1", "2"] and by_turn["1"]["kept"] and by_turn["1"]["title"] == "Branch from turn 1" and by_turn["2"]["title"] == "Branch from turn 2"
          and by_turn["2"]["before"] is True and by_turn["2"]["level"] is True and by_turn["2"]["middle"] is True and by_turn["3"]["middle"] is True
          and abs(by_turn["1"]["x"] - by_turn["2"]["x"]) <= 1 and abs(by_turn["2"]["end"] - by_turn["3"]["end"]) <= 1
          and lit == {"at": 2, "lit": True, "other": False, "hidden": "none", "words": "Say how the analysis should go on from turn 2", "open": was_open} and whole != "none",
          (cards, lit, was_open, whole))
    # nothing is locked: back to the turn both ways share - by the button on its card -, and a third way from it
    more_hint = "Now leave the sandy plots out."
    page.click("#streamOutput .sp-stream > .sp-turn[data-turn='1'] > summary .sp-branch")
    page.wait_for_function("() => BranchUI.standing() !== null && BranchUI.standing().turn === 1", timeout=10000)
    page.fill("#queryInput", more_hint)
    page.click("#submitQuery")
    wait_run_end(page, 3)
    page.wait_for_function("() => responses.length === 3 && !responses[2].status", timeout=60000)
    third = page.evaluate("""() => { const e = responses[currentResponseIndex];
        return { chain: String(e.chain_id), branch: e.branch ? [String(e.branch.of), e.branch.turn, e.branch.hint] : null, place: BranchUI.place(), n: responses.length,
                 badge: (document.querySelector('#streamOutput .sp-turnmap .n') || {}).textContent || '', hints: [...document.querySelectorAll('#streamOutput .sp-hint')].map(h => h.textContent),
                 fold: !!document.querySelector('#streamOutput .sp-stream > .ar-fold'), tabs: [...document.querySelectorAll('#tabContainer .tab')].map(t => t.textContent.trim()) }; }""")
    ran_3 = thread_run(wa, user, tid, third["chain"])
    log_3 = open(logs_at, encoding="utf-8", errors="replace").read() if os.path.exists(logs_at) else ""
    save_here()
    mem_3, left_3 = remembered(lambda v: any(r["run"] == third["chain"] for r in v["runs"]))
    check("nothing is locked after saving (0321): from a turn of the saved thread - gone back to by its card's button (0323) - the analysis goes on a third way - a branch of the first run, in a kernel that ran the kept cell "
          "again, under the brief, whose row and tab it has; the page counts one analysis with two branches. Saved again, the new branch is stored with the others; memory holds the "
          "two ways the person saved from, each with its own hint, and the first run stays left",
          third["branch"] == [str(cid), 1, more_hint] and third["place"] == {"i": 1, "n": 1} and third["n"] == 3 and third["badge"] == "2" and third["hints"] == ["From turn 1" + more_hint]
          and third["fold"] and "Brief" in third["tabs"]
          and ran_3.get("status") == "answered" and ran_3.get("branch") == {"of": str(cid), "turn": 1} and ran_3.get("hints") == [{"turn": 1, "text": more_hint}] and ran_3.get("brief") == ran.get("brief")
          and f"A fresh kernel for the branch: the 0 cells before chain {b_id} and the 1 it keeps of it are run again" in log_3
          and sorted(mem_3) == sorted([b_id, third["chain"]]) and mem_3[third["chain"]]["hints"] == [{"turn": 1, "text": more_hint}] and mem_3[b_id]["hints"] == [{"turn": 1, "text": mod.BRANCH_HINT}]
          and mem_3[third["chain"]]["marks"] == ["picked"] and mem_3[b_id]["marks"] == ["picked"] and left_3 == left_before + 1
          and len(os.listdir(os.path.join(storage, "favourites", str(tid)))) == 3,
          (third, ran_3.get("status"), ran_3.get("branch"), ran_3.get("hints"), sorted(mem_3), left_3, [l for l in log_3.splitlines() if "kernel for the branch" in l][-2:]))

    # ---- the code map and the Investigation tab of a branch (0322, docs/BRANCH_DESIGN.md §6) ----
    # Both show the branch's whole way and now say what of it is the branch's: the step it kept is marked, the hint stands where the person gave it, and the
    # map's header says after which turn the analysis went on - under the number the arrows show for it, one analysis whatever its branches
    page.click("#streamOutput .sp-done .sp-codemap")
    page.wait_for_selector("#codeMapModal .cm-map .cm-row.step", timeout=15000)
    page.wait_for_timeout(300)
    cm_b = page.evaluate("""() => { const m = document.getElementById('codeMapModal');
        return { no: m.querySelector('.cm-chain-no').textContent, branch: (m.querySelector('.cm-branch') || {}).textContent || '', facts: (m.querySelector('.cm-facts') || {}).textContent || '',
                 rows: [...m.querySelectorAll('.cm-map .cm-row')].map(r => [r.className.replace('cm-row ', ''), [...r.querySelectorAll('.cm-cell .sub')].map(s => s.textContent).join('|')]),
                 hint: (m.querySelector('.cm-row.band.hint') || {}).textContent || '',
                 colour: m.querySelector('.cm-row.band.hint .k') ? getComputedStyle(m.querySelector('.cm-row.band.hint .k')).color === getComputedStyle(m.querySelector('.cm-branch')).color : null }; }""")
    page.click("#codeMapModal .cm-map .cm-row.step .cm-cell-no")
    page.wait_for_selector("#codeMapModal .cm-pane.step .cm-big.cell", timeout=5000)
    cm_b["panel"] = page.evaluate("() => document.querySelector('#codeMapModal .cm-pane.step .cm-big.cell').textContent")
    page.keyboard.press("Escape")
    page.wait_for_function("() => document.getElementById('codeMapModal').style.display === 'none'", timeout=5000)
    page.evaluate("paneOpenTab('Investigation')")
    page.wait_for_selector(".briefing-content .nb-cell", timeout=5000)
    inv = page.evaluate("""() => { const nb = document.querySelector('.briefing-content .nb'), kids = [...nb.children], hint = nb.querySelector('.nb-step--hint');
        return { hint: hint ? hint.textContent : '', metas: [...nb.querySelectorAll('.nb-cell-head .nb-cell-meta')].map(x => x.textContent),
                 before: hint ? kids.slice(0, kids.indexOf(hint)).filter(x => x.classList.contains('nb-cell')).length : -1, cells: nb.querySelectorAll('.nb-cell').length }; }""")
    check("the code map of a branch (0322): its header says the analysis's number as the arrows count it - one analysis, whatever its branches - and after which turn it went on, "
          "and its line of facts how many turns it kept; the step it kept says kept under its turn and in its panel, its own step says nothing; the hint stands in a row of "
          "its own after the kept step, in the header's colour. The Investigation tab says the same: kept in the head of the kept cell, the hint in a row after it",
          cm_b["no"] == "chain 1" and cm_b["branch"] == "branch from turn 1" and " turns, 1 kept · " in cm_b["facts"]
          and cm_b["rows"][:3] == [["step", "turn 1|kept"], ["band hint", ""], ["step", "turn 2"]] and cm_b["hint"] == "Hint · after turn 1 · " + more_hint and cm_b["colour"] is True
          and cm_b["panel"] == "Cell 1 · turn 1 · kept" and not any("kept" in r[1] for r in cm_b["rows"][2:])
          and inv["hint"] == "Your hint " + more_hint and inv["before"] == 1 and inv["metas"][0].endswith(" · kept") and not any("kept" in x for x in inv["metas"][1:]) and inv["cells"] >= 2,
          (cm_b, inv))


def turn_prompt(page, turn):
    """The prompt a turn's card received, through its prompt button."""
    page.click(f'.sp-turn[data-turn="{turn}"] .sp-prompt')
    page.wait_for_function("() => { const u = document.getElementById('userInstructions'); return u && /TASK: turn/.test(u.textContent); }", timeout=15000)
    text = page.inner_text("#userInstructions")
    page.evaluate("() => { const m = document.getElementById('agentInstructionsModal'); if (m) m.style.display = 'none'; const u = document.getElementById('userInstructions'); if (u) u.textContent = ''; }")
    page.wait_for_timeout(200)
    return text


def kept_memory(storage, until=lambda view: True, timeout=15.0):
    """The memory view as the app keeps it for the user (analyst/memory.py), once `until` holds of it: the app brings
    it up to date behind the request that changed what is saved, so the walk waits for it."""
    if ROOT not in sys.path:
        sys.path.append(ROOT)
    from analyst import memory
    end = time.time() + timeout
    while True:
        view = memory.view(storage)
        if until(view) or time.time() > end:
            return view
        time.sleep(0.2)


def footer_time(record, note, words):
    """The run dialog's footer against the routine's record: it says how long the last run took - the check, with no
    run yet - and nothing where that was under a second."""
    r = json.load(open(record))
    took = (r["runs"][-1] if r["runs"] else r["versions"][-1]["run_zero"])["elapsed"]
    return note.startswith(words) if took >= 1 else note == ""


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
            store_dir = os.path.join(workdir, "webapp", "storage", USER)
            mem = kept_memory(store_dir, lambda v: v["built"] is not None)
            check("the memory view is built behind the sign-in and kept under the user's storage (2.8): nothing is saved yet, so it holds no run",
                  mem["built"] is not None and mem["runs"] == [] and os.path.exists(os.path.join(store_dir, "memory", "view.json")), mem)

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
            check("the closing card counts 3 cells with 1 failed", "3 cells (1 failed)" in done.replace("\n", " "), done)
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
            nums = page.evaluate("() => (document.querySelector('.sp-done .head .nums') || {}).textContent || ''")
            check("the replay captured both figures: the matplotlib PNG and the plotly JSON (the closing card counts 2 plots among the run's numbers)", " · 2 plots · " in nums, nums)

            # the third way in (2026-10-24): a [cell n] chip in the report opens the code map on that cell's number - the diagram
            # with its recipe in the panel - and Escape closes it; the zoom controls sit at the diagram head's end
            page.evaluate("activateTab('answer')")
            page.wait_for_selector("#content-answer .cite.cell", timeout=5000)
            cite_cell = page.evaluate("() => { const c = document.querySelector('#content-answer .cite.cell'); return c ? c.textContent : ''; }")
            page.click("#content-answer .cite.cell")
            page.wait_for_selector("#codeMapModal .cm-diag .cm-node.result, #codeMapModal .cm-pane.step", timeout=15000)
            cm_cite = page.evaluate("() => ({ open: document.getElementById('codeMapModal').style.display === 'flex', diagram: !!document.querySelector('#codeMapModal .cm-diag'), kicker: (document.querySelector('#codeMapModal .cm-panel .cm-kicker span') || {}).textContent || '', zoom: (document.querySelector('#codeMapModal .cm-zoom-level') || {}).textContent || '' })")
            check("a [cell n] chip in the report opens the map on that cell's number: the diagram, the recipe in the panel, the zoom at its fit",
                  cm_cite["open"] and cm_cite["diagram"] and cm_cite["kicker"].startswith("How this number was made · " + cite_cell) and cm_cite["zoom"].endswith("%"), (cite_cell, cm_cite))
            page.click("#codeMapModal .cm-zoom-btn[data-dir='out']")
            page.wait_for_timeout(150)
            cm_zoom = page.evaluate("() => { const d = document.querySelector('#codeMapModal .cm-diag'), f = document.querySelector('#codeMapModal .cm-diag-frame'); const z = parseFloat((d.style.transform.match(/scale\\(([\\d.]+)\\)/) || [])[1]); return { level: document.querySelector('#codeMapModal .cm-zoom-level').textContent, z, frameOk: Math.abs(parseFloat(f.style.width) - Math.round(parseFloat(d.style.width) * z)) <= 1 }; }")
            check("zoom out: the drawing scaled a step down, the level saying so, the frame sized to the drawing", cm_zoom["z"] < 1 and cm_zoom["level"] == str(round(cm_zoom["z"] * 100)) + "%" and cm_zoom["frameOk"], cm_zoom)
            page.click("#codeMapModal .cm-zoom-btn[data-dir='fit']")
            page.keyboard.press("Escape")
            page.wait_for_function("() => document.getElementById('codeMapModal').style.display === 'none'", timeout=5000)
            # the fourth way in (2026-10-24): the eye on a cell in the Investigation tab opens the map on the Steps view at that cell
            page.evaluate("paneOpenTab('Investigation')")
            page.wait_for_selector(".briefing-content .nb-cell-map", timeout=5000)
            eye_cell = page.evaluate("() => document.querySelector('.briefing-content .nb-cell-map').dataset.cell")
            page.click(".briefing-content .nb-cell-map")
            page.wait_for_selector("#codeMapModal .cm-pane.step", timeout=15000)
            cm_eye = page.evaluate("() => ({ open: document.getElementById('codeMapModal').style.display === 'flex', steps: !!document.querySelector('#codeMapModal .cm-steps'), cell: (document.querySelector('#codeMapModal .cm-pane.step .cm-big.cell') || {}).textContent || '' })")
            check("the eye on a notebook cell opens the map on the Steps view with that cell's row selected", cm_eye["open"] and cm_eye["steps"] and cm_eye["cell"].startswith("Cell " + eye_cell), (eye_cell, cm_eye))
            page.keyboard.press("Escape")
            page.wait_for_function("() => document.getElementById('codeMapModal').style.display === 'none'", timeout=5000)

            # the code map (2026-10-20, M4): the closing card's button opens the modal on this chain, built at its end; a result's
            # recipe; the diagram; the Workflow map's eye opens it too
            check("the closing card carries the Code map button with this chain's id", page.evaluate("() => { const b = document.querySelector('.sp-done .sp-codemap'); return b && b.dataset.chain === String(responses[currentResponseIndex].chain_id); }"))
            page.click(".sp-done .sp-codemap")
            page.wait_for_selector("#codeMapModal .cm-row.step", timeout=15000)
            cm_head = page.evaluate("() => ({ chain: document.querySelector('#codeMapModal .cm-chain-no').textContent, built: document.querySelector('#codeMapModal .cm-facts').getAttribute('data-built'), facts: document.querySelector('#codeMapModal .cm-facts').textContent, line: document.querySelector('#codeMapModal .cm-head-line').textContent, rows: document.querySelectorAll('#codeMapModal .cm-row.step').length, failed: document.querySelectorAll('#codeMapModal .cm-row.failed').length, lanes: [...document.querySelectorAll('#codeMapModal .cm-lane .name')].map(e => e.textContent), results: document.querySelectorAll('#codeMapModal .cm-res.recorded').length, lanesHeight: document.querySelector('#codeMapModal .cm-lanes').getBoundingClientRect().height })")
            check("the code map opens on chain 1, built when the chain ended (said in its data, not in words): the facts, its cells and the rolled-back attempt as rows, the dataset's lane as tall as its name, a recorded result",
                  cm_head["chain"] == "chain 1" and cm_head["built"] == "end" and "cells" in cm_head["facts"] and "built" not in cm_head["line"] and cm_head["rows"] >= 3 and cm_head["failed"] == 1 and cm_head["lanes"] == ["field_trial.csv"]
                  and 70 < cm_head["lanesHeight"] < 160 and cm_head["results"] >= 1, cm_head)
            page.click("#codeMapModal .cm-res.recorded")
            page.wait_for_selector("#codeMapModal .cm-pane.result", timeout=5000)
            cm_panel = page.evaluate("() => ({ kicker: document.querySelector('#codeMapModal .cm-kicker span').textContent, est: document.querySelector('#codeMapModal .cm-big').textContent, items: document.querySelectorAll('#codeMapModal .cm-item:not(.final)').length, sizes: [...document.querySelectorAll('#codeMapModal .cm-item .cm-names')].map(e => e.textContent), status: document.querySelector('#codeMapModal .cm-status').textContent })")
            check("a result's recipe: the number, its boxes in order with the kernel's sizes, the status 'recorded'",
                  cm_panel["kicker"].startswith("How this number was made · cell ") and cm_panel["est"].startswith("+0.") and cm_panel["items"] >= 2 and any("rows" in x or "values" in x or "a number" in x for x in cm_panel["sizes"]) and cm_panel["status"] == "recorded", cm_panel)
            page.click("#codeMapModal .cm-switch button[data-view='diagram']")
            page.wait_for_selector("#codeMapModal .cm-diag .cm-node.result", timeout=5000)
            cm_diag = page.evaluate("() => ({ nodes: document.querySelectorAll('#codeMapModal .cm-node').length, edges: document.querySelectorAll('#codeMapModal .cm-edges path').length, top: Math.min(...[...document.querySelectorAll('#codeMapModal .cm-node.in')].map(n => parseInt(n.style.top, 10))), result: document.querySelector('#codeMapModal .cm-node.result .names').textContent })")
            check("the recipe diagram: the input on the top row, boxes and edges laid out by dagre, the result at the bottom", cm_diag["nodes"] >= 3 and cm_diag["edges"] >= 2 and cm_diag["top"] == 0 and cm_diag["result"].startswith("RESULT · cell "), cm_diag)
            page.click("#codeMapModal #cmDiagPick")
            page.wait_for_selector("#codeMapModal .cm-pick.open .cm-pick-opt", timeout=5000)
            cm_pick = page.evaluate("() => { const b = document.querySelector('#codeMapModal #cmDiagPick').getBoundingClientRect(), l = document.querySelector('#codeMapModal .cm-pick-list').getBoundingClientRect(); return { below: l.top >= b.bottom && l.left >= b.left - 1, visible: l.height > 10 && l.width >= b.width - 1, focused: document.activeElement && document.activeElement.classList.contains('cm-pick-opt'), on: document.querySelectorAll('#codeMapModal .cm-pick-opt[aria-selected=\"true\"]').length }; }")
            check("the picker's list opens below its button, as wide, the chosen option focused", cm_pick["below"] and cm_pick["visible"] and cm_pick["focused"] and cm_pick["on"] == 1, cm_pick)
            page.keyboard.press("Escape")
            page.wait_for_timeout(150)
            check("Escape closes the list and leaves the map open, the focus on the button", page.evaluate("() => !document.querySelector('#codeMapModal .cm-pick.open') && document.getElementById('codeMapModal').style.display === 'flex' && document.activeElement && document.activeElement.id === 'cmDiagPick'"))
            page.click("#codeMapModal .cm-head button.x")
            page.wait_for_function("() => document.getElementById('codeMapModal').style.display === 'none'", timeout=5000)
            page.evaluate("showWorkflowMap()")
            page.wait_for_selector("#workflowMapModal .wf-node .wf-node-map", timeout=5000)
            page.hover("#workflowMapModal .wf-node")
            page.click("#workflowMapModal .wf-node .wf-node-map")
            page.wait_for_selector("#codeMapModal .cm-row.step", timeout=15000)
            check("the Workflow map's eye opens the chain's code map and closes the drawer", page.evaluate("() => document.getElementById('workflowMapModal').style.display === 'none' && document.getElementById('codeMapModal').style.display === 'flex'"))
            page.click("#codeMapModal .cm-head button.x")
            page.wait_for_timeout(200)
            # the lines behind a number (2026-10-24): Open in the notebook from a recipe lights the statements the number rests on
            # in the Investigation tab, the RESULT's own line strong, placed inside the cell's code block
            page.click(".sp-done .sp-codemap")
            page.wait_for_selector("#codeMapModal .cm-res.recorded", timeout=15000)
            page.click("#codeMapModal .cm-res.recorded")
            page.wait_for_selector("#codeMapModal .cm-pane.result .cm-foot button[data-act='open-nb']", timeout=5000)
            lit_cell = page.evaluate("() => document.querySelector('#codeMapModal .cm-pane.result .cm-foot button[data-act=\"open-nb\"]').dataset.cell")
            page.click("#codeMapModal .cm-pane.result .cm-foot button[data-act='open-nb']")
            page.wait_for_selector(".briefing-content .nb-hl.own", timeout=5000)
            lit = page.evaluate("""() => { const own = document.querySelector('.briefing-content .nb-hl.own'); const cell = own.closest('.nb-cell'); const code = cell.querySelector('pre.nb-code code'); const cr = code.getBoundingClientRect(), orr = own.getBoundingClientRect();
                const text = code.textContent.split('\\n'); const cs = getComputedStyle(code); const lh = parseFloat(cs.lineHeight); const line = Math.round((orr.top - cr.top - parseFloat(cs.paddingTop)) / lh) + 1;
                return { idx: cell.querySelector('.nb-cell-idx').textContent.replace(/\\s/g, ''), bars: document.querySelectorAll('.briefing-content .nb-hl').length, own: document.querySelectorAll('.briefing-content .nb-hl.own').length,
                         inside: orr.top >= cr.top - 1 && orr.bottom <= cr.bottom + 1, ownLine: (text[line - 1] || '').trim().slice(0, 7), modal: document.getElementById('codeMapModal').style.display }; }""")
            check("Open in the notebook from a recipe: the map closes, the number's cell is lit - its own RESULT line strong and on the RESULT call, the other bars on the statements it rests on, all inside the code block",
                  lit["modal"] == "none" and lit["idx"] == "In[" + lit_cell + "]" and lit["own"] == 1 and lit["bars"] >= 2 and lit["inside"] and lit["ownLine"].startswith("RESULT"), (lit_cell, lit))

            # the Code tab (2026-10-11, routines S10): the script is read or taken away - Copy and Download; Edit and run is retired
            page.evaluate("activateTab('code')")
            page.wait_for_timeout(300)
            code_tab = page.evaluate("""() => ({ buttons: [...document.querySelectorAll('#content-code .code-header button')].map(b => b.className + '|' + b.title),
                editor: document.querySelectorAll('#content-code .edit-button, #content-code .execute-button, #content-code .CodeMirror').length,
                code: (document.querySelector('#content-code pre code') || {}).textContent || '', highlighted: !!document.querySelector('#content-code pre code.hljs, #content-code pre code .hljs-keyword') })""")
            check("the Code tab shows the chain's script highlighted, with Copy and Download in its header and no editor",
                  len(code_tab["buttons"]) == 2 and code_tab["buttons"][0].startswith("code-action-button copy-button|Copy") and code_tab["buttons"][1].startswith("code-action-button download-button|Download")
                  and code_tab["editor"] == 0 and "import" in code_tab["code"], code_tab)
            copied = page.evaluate("""async () => { const got = []; navigator.clipboard.writeText = t => { got.push(t); return Promise.resolve(); };
                document.querySelector('#content-code .copy-button').click(); await new Promise(r => setTimeout(r, 100));
                return { text: got[0] || '', check: getComputedStyle(document.querySelector('#content-code .copy-button .check-icon')).display }; }""")
            check("Copy puts the script on the clipboard and shows the check for a moment", copied["text"] == code_tab["code"] and copied["check"] == "block", {k: str(v)[:80] for k, v in copied.items()})
            with page.expect_download(timeout=10000) as dl:
                page.click("#content-code .download-button")
            dl_name = dl.value.suggested_filename
            check("Download saves the script as a .py named after the question's first words", dl_name.endswith(".py") and dl_name == "does_regime_b_raise_yield.py", dl_name)

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
            check("the Workflow map stays closed when an Adaptive run ends (v65)", not map_open, map_open)
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

            # Save trajectory in the Workflow map (2.8): the whole thread at once - no dialog - and the map stays open
            page.evaluate("showWorkflowMap()")
            page.wait_for_selector("#trajectoryButton:not([disabled])", timeout=10000)
            page.click("#trajectoryButton")
            page.wait_for_function("() => /Saved the whole thread/.test(document.getElementById('summaryPopup').textContent)", timeout=30000)
            traj = page.evaluate("""() => ({ map: getComputedStyle(document.getElementById('workflowMapModal')).display !== 'none', dialog: !!document.getElementById('rankModal'),
                marks: responses.map(r => r.bookmark_type || null), thread: String(currentData.thread_id) })""")
            traj_docs = [json.load(open(f)) for f in glob.glob(os.path.join(workdir, "webapp", "storage", USER, "favourites", traj["thread"], "*.json"))]
            check("Save trajectory saves the whole thread in one click (2.8): every chain stored alongside, none picked, no rating; the page says so and the map stays open",
                  traj["map"] and not traj["dialog"] and traj["marks"] == ["trajectory"] * 4 and len(traj_docs) == 4
                  and all(d.get("bookmark_type") == "trajectory" and "rank" not in d for d in traj_docs), (traj, [d.get("bookmark_type") for d in traj_docs]))
            # what was saved is memory (2.8, docs/ARCHITECT_DESIGN.md §3.5): the view follows behind the save, from the thread's record
            record = json.load(open(os.path.join(store_dir, "threads", traj["thread"] + ".json")))["runs"]
            reported = sorted(c for c, r in record.items() if (r.get("report") or "").strip())
            mem = kept_memory(store_dir, lambda v: len([r for r in v["runs"] if r["thread"] == traj["thread"]]) == len(reported))
            mine = {r["run"]: r for r in mem["runs"] if r["thread"] == traj["thread"]}
            check("what was saved is memory: behind the save the view holds the thread's chains - each stored alongside, with its question, its report and its cells' code from the record; "
                  "a follow-up names the chain it was built on",
                  sorted(mine) == reported and len(reported) == 4 and all(r["marks"] == ["alongside"] for r in mine.values())
                  and all(r["question"] == record[c]["question"].strip() and r["report"] == record[c]["report"].strip()
                          and [x["code"] for x in r["cells"]] == [t["code"] for t in record[c]["turns"] if t["kind"] == "cell" and t.get("cell_no") is not None and t.get("step") != "figures"]
                          and r["path"][-1:] == ([f"{traj['thread']}/{record[c]['parent']}"] if record[c].get("parent") else []) for c, r in mine.items())
                  and any(r["path"] for r in mine.values()) and any(r["cells"] for r in mine.values()), (reported, {c: (r["marks"], r["path"], len(r["cells"])) for c, r in mine.items()}))
            page.click("#workflowMapModal .workflow-close")
            page.wait_for_timeout(300)

            # Save (2026-10-10, routines): the pill opens its menu; Save as favourite saves at once (2.8: no dialog, no rating)
            page.click("#saveButton")
            page.wait_for_selector("#saveMenu", state="visible", timeout=10000)
            menu_items = page.evaluate("() => [...document.querySelectorAll('#saveMenu .it b')].map(e => e.textContent)")
            check("the Save pill opens its menu: Save as favourite and Save as routine", menu_items == ["Save as favourite", "Save as routine"], menu_items)
            page.click("#saveMenu .it[data-act='favourite']")
            page.wait_for_function("() => document.getElementById('saveButton').classList.contains('saved')", timeout=30000)
            saved = page.evaluate("""() => { const p = document.getElementById('saveButton'), t = document.getElementById('summaryPopup');
                return { pill: [getComputedStyle(p).display, p.className, p.textContent.trim()], said: getComputedStyle(t).display !== 'none' ? t.textContent : '',
                         dialog: !!document.getElementById('rankModal'), thread: String(currentData.thread_id), chain: String(currentData.chain_id) }; }""")
            fav4 = os.path.join(workdir, "webapp", "storage", USER, "favourites", saved["thread"], saved["chain"] + ".json")
            fav4_doc = json.load(open(fav4)) if os.path.exists(fav4) else {}
            check("Save as favourite is one click (2.8): no dialog and no rating - the page says it is saved, the chain stored alongside becomes the one picked, and the pill stays, marked saved (its menu still offers Save as routine)",
                  saved["pill"][0] != "none" and "saved" in saved["pill"][1].split() and saved["pill"][2] == "Save" and "Saved as favourite" in saved["said"] and not saved["dialog"]
                  and fav4_doc.get("bookmark_type") == "individual" and "rank" not in fav4_doc, (saved, sorted(fav4_doc)[:14]))
            mem = kept_memory(store_dir, lambda v: any(r["run"] == saved["chain"] and r["marks"] == ["picked"] for r in v["runs"]))
            check("... and in memory the chain is the one picked, the others still alongside",
                  {r["run"]: r["marks"] for r in mem["runs"] if r["thread"] == saved["thread"]} == {c: ["picked"] if c == saved["chain"] else ["alongside"] for c in reported},
                  {r["run"]: r["marks"] for r in mem["runs"]})

            # Save as routine on chain 1 (docs/ROUTINES_DESIGN.md F1): the promoter (scripted) names the regime as the one
            # input, run zero runs through the real executor and reproduces the chain's RESULT line, the routine is stored
            # with the favourite as its origin, and the manager and the favourites' card show it
            for _ in range(3):
                page.click("#prevResponse")
                page.wait_for_timeout(400)
            wait_text(page, "#chainPosition", "chain 1 of 4", 10000)
            page.hover("#saveButton")
            page.wait_for_selector("#saveMenu", state="visible", timeout=10000)
            page.click("#saveMenu .it[data-act='routine']")
            page.wait_for_selector("#routineMakeModal", state="visible", timeout=10000)
            page.wait_for_selector("#routineMakeModal .rt-inputs", timeout=120000)
            dlg = page.evaluate("""() => ({ sub: document.querySelector('#routineMakeModal .ui-dlg-h .sub').textContent, name: document.querySelector('#routineMakeModal [data-field="name"]').value,
                inputs: [...document.querySelectorAll('#routineMakeModal .rt-inputs tbody tr')].map(r => [r.dataset.key, r.querySelector('.val').textContent]),
                results: [...document.querySelectorAll('#routineMakeModal .rt-results .r .l')].map(e => e.textContent), data: document.querySelector('#routineMakeModal .rt-data').textContent,
                state: [...document.querySelectorAll('#routineMakeModal .rt-line')].map(e => e.textContent).join(' | '), card: !![...document.querySelectorAll('.sp-turn .n')].find(e => e.textContent === 'Routine'),
                seat: (() => { const c = [...document.querySelectorAll('.sp-turn')].find(t => (t.querySelector('.n') || {}).textContent === 'Routine'); return c ? ((c.querySelector('.sp-prompt') || {}).dataset || {}).agent || '' : ''; })() })""")
            check("Save as routine: the dialog shows the promoter's proposal - the name, the regime as the one input (B), the chain's RESULT line, the data, and that the check runs on this chain's own data; the header counts the chain's 3 cells; the pane shows the promoter's card on the Promoter seat",
                  dlg["name"] == "Regime contrast within soil, plot means" and dlg["inputs"] == [["regime", "B"]] and len(dlg["results"]) == 1 and "regime B vs A" in dlg["results"][0] and "· 3 cells ·" in dlg["sub"]
                  and "field_trial.csv" in dlg["data"] and "Checked once" in dlg["state"] and dlg["card"] and "Promoter" in dlg["seat"], dlg)
            page.fill("#routineMakeModal [data-field='purpose']", "the within-soil regime contrast, for the next season")
            # the custom instructions (§15.6): the coach's line goes to the promoter again with Update the list; the scripted promoter
            # answers the yield line for the contrast (named) and nothing for the plot count; the fields typed before stay
            instr = page.evaluate("""() => ({ head: document.querySelector('#routineMakeModal .rt-sec[data-sec="results"] .h').textContent, sec: document.querySelector('#routineMakeModal .rt-instr .h').textContent,
                text: document.querySelector('#routineMakeModal .rt-instr .rt-line').textContent, box: document.querySelector('#routineMakeModal [data-field="instruction"]').value,
                btn: document.querySelector('#routineMakeModal [data-act="instruct"]').textContent, named: [...document.querySelectorAll('#routineMakeModal .rt-results .r .l')].map(e => [e.textContent, e.getAttribute('title')]) })""")
            check("the dialog in the coach's words (2026-11-08): the Tracked metrics head, the Custom instructions section (optional) with its explanation, an empty box and Update the list; the chain's one line tracked under its recorded wording (the promoter named nothing)",
                  instr["head"].startswith("Tracked metrics — recomputed each run and compared with the run before, 1 of 1") and instr["sec"] == "Custom instructions — optional"
                  and instr["text"].startswith("If you want this routine to track particular metrics, say so here") and instr["box"] == "" and instr["btn"] == "Update the list"
                  and len(instr["named"]) == 1 and instr["named"][0][0].startswith("yield, regime B vs A"), instr)
            page.fill("#routineMakeModal [data-field='instruction']", "track the yield contrast and the plot count")
            page.click("#routineMakeModal [data-act='instruct']")
            page.wait_for_function("() => { const l = document.querySelector('#routineMakeModal .rt-results .r .l'); return !!l && l.textContent === 'Yield, B vs A'; }", timeout=120000)
            instr2 = page.evaluate("""() => ({ named: [...document.querySelectorAll('#routineMakeModal .rt-results .r .l')].map(e => [e.textContent, e.getAttribute('title')]), head: document.querySelector('#routineMakeModal .rt-sec[data-sec="results"] .h').textContent,
                box: document.querySelector('#routineMakeModal [data-field="instruction"]').value, purpose: document.querySelector('#routineMakeModal [data-field="purpose"]').value,
                notes: [...document.querySelectorAll('#routineMakeModal .rt-sec')].filter(s => s.querySelector('.h').textContent === 'Notes').map(s => s.querySelector('.rt-line').textContent),
                after: [...document.querySelectorAll('#routineMakeModal .rt-sec')].map(s => s.querySelector('.h').textContent.split(' ')[0]), create: document.querySelector('#routineMakeModal [data-act="create"] span').textContent })""")
            check("Update the list: the promoter asked again with the line - the yield line now named as it answered (its recorded wording the title), the head still 1 of 1; the plot count it found no line for is a note under the box; the purpose typed before and the box stand; Create routine offered again",
                  instr2["named"] == [["Yield, B vs A", "yield, regime B vs A within soil type, plot means"]] and ", 1 of 1" in instr2["head"] and instr2["box"] == "track the yield contrast and the plot count"
                  and instr2["purpose"] == "the within-soil regime contrast, for the next season" and instr2["notes"] == ["Not computed in this analysis, so it can’t be tracked: the plot count"]
                  and instr2["after"][-3:] == ["Tracked", "Custom", "Notes"] and instr2["create"] == "Create routine", instr2)
            page.click("#routineMakeModal [data-act='create']")
            page.wait_for_function("() => document.querySelector('#routineMakeModal').style.display === 'none' || !!document.querySelector('#routineMakeModal .rt-error')", timeout=180000)
            err_box = page.evaluate("() => { const e = document.querySelector('#routineMakeModal .rt-error'); return e ? e.textContent : null; }")
            check("Create routine: the dialog closed at once with no refusal (run zero runs behind it, 2026-10-15)", err_box is None, err_box)
            rdirs = glob.glob(os.path.join(workdir, "webapp", "storage", USER, "routines", "*", "routine.json"))
            # run zero behind the dialog: the verdict lands on the stored version; the pane carries no row for it (the toast and
            # the manager's chip say it); wait for the verdict on disk before reading the record
            t_v = time.time()
            rj = json.load(open(rdirs[0])) if rdirs else {}
            while rdirs and (rj.get("versions") or [{}])[0].get("run_zero", {}).get("status") in ("verifying", None) and time.time() - t_v < 240:
                time.sleep(1.0)
                rj = json.load(open(rdirs[0]))
            pane_rows = page.evaluate("() => [...document.querySelectorAll('.sp-row.tool')].map(e => e.textContent)")
            check("the pane carries no ROUTINE row for run zero any more - it ran behind the dialog; the REPLAY row stays the chain's own", not any("ROUTINE" in r for r in pane_rows) and any("REPLAY" in r for r in pane_rows), pane_rows[-2:])
            check("the routine is stored under storage/<user>/routines with v1 verified by run zero, the regime input, and the chain as its origin",
                  len(rdirs) == 1 and rj.get("current_version") == 1 and rj["versions"][0]["run_zero"]["verified"] and rj["versions"][0]["run_zero"]["status"] == "reproduced"
                  and [p["key"] for p in rj["versions"][0]["manifest"]["parameters"]] == ["regime"] and "INPUTS['regime']" in rj["versions"][0]["script"]
                  and rj["origin"]["thread_id"] == str(page.evaluate("() => currentData.thread_id")) and rj.get("purpose", "").startswith("the within-soil"), (len(rdirs), rj.get("versions", [{}])[0].get("run_zero")))
            made_from = str((rj.get("origin") or {}).get("chain_id"))
            mem = kept_memory(store_dir, lambda v: any(r["run"] == made_from and "routine" in r["marks"] and "picked" in r["marks"] for r in v["runs"]))
            check("in memory the chain the routine was made from carries that mark, and is picked: Save as routine saved it",
                  [r["marks"] for r in mem["runs"] if r["run"] == made_from] == [["picked", "routine"]], {r["run"]: r["marks"] for r in mem["runs"]})
            # one stored text (docs/ROUTINES_DESIGN.md §19, §22): the chain as written with the promoter's edit - the inspection cell, the prints and
            # the two tables only printed (tab, raw) included; the proof behind the verdict ran every statement (run zero), then only what the
            # tracked line and the two figures rest on, held to run zero's line and pictures (the matplotlib PNG, the Plotly figure by its data)
            v1 = (rj.get("versions") or [{}])[0]
            lean = v1.get("lean") or {}
            runs_of = re.match(r"^runs (\d+) of (\d+) statements$", lean.get("line") or "")
            check("the version keeps one script, the chain's three cells as written with the input in place; the proof left the statements nothing tracked or drawn rests on out of a run and says how many run, each line knows its "
                  "place among the statements and the version their mark; run zero drew two figures; a file has no smaller pieces to try; nothing of an earlier pass",
                  [ln for ln in v1["script"].splitlines() if ln.startswith("# --- cell")] == ["# --- cell 1 ---", "# --- cell 2 ---", "# --- cell 3 ---"] and "print(df.shape)" in v1["script"]
                  and re.search(r"^raw = plot_means\[plot_means.regime == 'B'\]", v1["script"], re.M) and "b=INPUTS['regime']" in v1["script"] and "RESULT(" in v1["script"] and "pfig.show()" in v1["script"]
                  and runs_of and int(runs_of.group(1)) < int(runs_of.group(2)) and len(lean.get("steps") or []) == int(runs_of.group(1)) and re.fullmatch(r"[0-9a-f]{12}", v1.get("steps") or "")
                  and all(isinstance(e.get("at"), list) for e in v1["manifest"]["results"] if e.get("estimate") is not None) and v1["run_zero"]["figures"] == 2 and v1.get("tried") == []
                  and not {"script_written", "script_fallback", "condensed", "consolidated", "pruned"} & set(v1), (lean, v1.get("steps"), v1.get("tried"), sorted(v1)))
            fav1 = os.path.join(workdir, "webapp", "storage", USER, "favourites", rj["origin"]["thread_id"], rj["origin"]["chain_id"] + ".json") if rdirs else ""
            def _fav_type():
                try:
                    return json.load(open(fav1)).get("bookmark_type") if fav1 and os.path.exists(fav1) else None
                except (OSError, ValueError):
                    return None
            t_f = time.time()                                 # the favourite is saved by the page after the dialog closes; a quick run zero lands first (the local edition, 2026-10-15),
            while _fav_type() != "individual" and time.time() - t_f < 20:   # and the earlier Save left the chain's file marked 'trajectory' until that save rewrites it (hosted)
                time.sleep(0.5)
            check("Save as routine saved the chain as a favourite too (individually)", _fav_type() == "individual", (fav1, _fav_type()))
            page.hover("#saveButton")
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
                facts: [...document.querySelectorAll('#routinesModal .rt-facts > b')].map(e => e.textContent), version: (document.querySelector('#routinesModal .rt-vers .v') || {}).textContent, results: [...document.querySelectorAll('#routinesModal .rt-facts > span')].map(e => e.textContent).find(t => /per run/.test(t)) || '',
                links: document.querySelectorAll('#routinesModal .rt-vers a').length, inputs: [...document.querySelectorAll('#routinesModal .rt-facts .rt-input')].map(e => e.textContent),
                instruction: (() => { const bs = [...document.querySelectorAll('#routinesModal .rt-facts > b')]; const i = bs.findIndex(e => e.textContent === 'Custom instructions'); return i < 0 ? null : [...document.querySelectorAll('#routinesModal .rt-facts > span')][i].textContent; })(),
                badge: !!document.getElementById('routinesBadge') || !!document.querySelector('#routinesPill .rb-badge'), scrolls: [...document.querySelectorAll('#routinesModal .rt-right *')].filter(e => { const o = getComputedStyle(e).overflowY; return (o === 'auto' || o === 'scroll') && e.scrollHeight > e.clientHeight; }).map(e => e.className) })""")
            check("the Routines manager (S2, 2026-11-08) lists the routine; the header's sub-line carries the source, the version and the link to the analysis it was made from, nothing of the columns or the favourite; the facts - Purpose, Inputs (the one input with its default and origin), Tracked (what a run records), Custom instructions (the line typed in the dialog, §15.6), Version (verified with the lines reproduced, nothing of how the code is run) - and no scroll inside the body's; the rail entry carries no count badge",
                  mgr["items"] == ["Regime contrast within soil, plot means"] and mgr["origin"] and mgr["checked"] == "verified" and mgr["sub"].startswith("File · v1 · from the analysis of ") and "columns" not in mgr["sub"] and "a favourite" not in mgr["sub"] and mgr["badge"] is False
                  and mgr["facts"] == ["Purpose", "Inputs", "Tracked", "Custom instructions", "Version"] and mgr["inputs"] == ["The regime compared with A B the analysis compared B against A"]
                  and mgr["results"] == "1 metric and 2 charts per run" and mgr["instruction"] == "track the yield contrast and the plot count" and re.search(r"^v1(?:[A-Z][a-z]{2} \d+|\d+ [A-Z][a-z]{2}) · verified, 1 line reproduced$", mgr["version"])
                  and mgr["links"] == 0 and set(mgr["scrolls"]) <= {"rt-body"}, mgr)
            script_status = page.evaluate("(id) => window.authService.fetch('/routines/' + id + '/script').then(r => r.text()).then(t => t.includes('INPUTS = {') && t.includes(\"'regime': 'B'\") && t.includes('print(df.shape)'))", rj["id"])
            check("the .py download carries the INPUTS block with the default and the chain's code as written", script_status is True, script_status)
            page.click("#routinesModal .rt-origin")
            page.wait_for_function("() => document.getElementById('routinesModal').style.display === 'none' && /chain 1 of 4/.test(document.getElementById('chainPosition').textContent)", timeout=15000)
            check("open the analysis: the routine's origin loads from favourites into the main panes", True)
            page.click("#workflowManagerPill")
            # the gallery re-renders its cards once the chains arrive: wait for the lit button, not for a card (2026-10-20: a flake)
            try:
                page.wait_for_function("() => [...document.querySelectorAll('#workflowManagerModal .workflow-card-routine')].some(b => b.className.split(' ').includes('has') && (b.querySelector('.n') || {}).textContent === '1')", timeout=15000)
            except Exception:                                  # noqa: BLE001 - the check below says what was there
                pass
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
            runs_before = page.evaluate("() => [...document.querySelectorAll('#routinesModal .rt-runs thead th[data-run]')].map(e => e.dataset.run)")
            check("the manager before any run: the custom table's one column is run 0", runs_before == ["0"], runs_before)
            page.click("#routinesModal [data-act='run']")
            page.wait_for_selector("#routineRunModal", state="visible", timeout=10000)
            page.wait_for_selector("#routineRunModal .rt-row[data-row='data']", timeout=30000)
            rd = page.evaluate("""() => ({ title: document.querySelector('#routineRunModal .ui-dlg-h .title').textContent, fit: (document.querySelector('#routineRunModal .rt-fit') || {}).textContent || null,
                data: document.querySelector('#routineRunModal .rt-row[data-row="data"]').textContent, rows: [...document.querySelectorAll('#routineRunModal .rt-row')].map(r => r.dataset.row), regime: (document.querySelector('#routineRunModal [data-key="regime"]') || {}).value,
                compare: [...document.querySelectorAll('#routineRunModal input[name="rt-compare"]')].map(i => [i.value, i.checked]), runOn: !document.querySelector('#routineRunModal [data-act="run"]').disabled, note: document.querySelector('#routineRunModal .ui-dlg-f .note').textContent })""")
            check("the run dialog (§16.1): the rows Data, File, Inputs - the data loaded now (field_trial.csv) the choice, nothing said about its fit since it fits, the regime input with its default B; no Compare row with run 0 the only run (one choice is no choice); the footer the time of the check (nothing where it took under a second); Run enabled",
                  "Regime contrast" in rd["title"] and rd["fit"] is None and "The data loaded now · field_trial.csv" in rd["data"] and rd["rows"] == ["data", "file", "inputs"] and rd["regime"] == "B" and rd["compare"] == [] and rd["runOn"] and footer_time(rdirs[0], rd["note"], "the check on the original data took "), rd)
            page.click("#routineRunModal [data-act='run']")
            page.wait_for_function("() => document.getElementById('routineRunModal').style.display === 'none' && /run 1/.test(document.getElementById('chainPosition').textContent)", timeout=30000)
            live = page.evaluate("() => ({ pos: document.getElementById('chainPosition').textContent, locked: document.getElementById('queryInput').disabled, pill: getComputedStyle(document.getElementById('saveButton')).display, arrows: [document.getElementById('prevResponse').disabled, document.getElementById('nextResponse').disabled] })")
            check("while run 1 runs: the position says so, both arrows are off, the composer is locked and the Save pill is hidden",
                  "running" in live["pos"] and live["locked"] and live["pill"] == "none" and live["arrows"] == [True, True], live)
            wait_position(page, "2 of 2", 180000)
            page.wait_for_timeout(600)
            rv = page.evaluate("""() => ({ rows: [...document.querySelectorAll('.sp-row.tool')].map(e => e.textContent), done: (document.querySelector('.sp-done') || {}).textContent || '', warn: !!document.querySelector('.sp-done.warn'),
                tabs: [...document.querySelectorAll('#tabContainer .tab')].map(e => e.id), active: (document.querySelector('#contentOutput .tab-content.active') || {}).id, strip: (document.querySelector('.sp-strip') || {}).textContent || '',
                ids: (document.querySelector('.sp-ids') || {}).textContent || '', locked: document.getElementById('queryInput').disabled && document.getElementById('submitQuery').disabled && document.body.classList.contains('composer-locked'),
                placeholder: document.getElementById('queryInput').placeholder, pill: getComputedStyle(document.getElementById('saveButton')).display, arrows: [document.getElementById('prevResponse').disabled, document.getElementById('nextResponse').disabled],
                cmp: (document.getElementById('content-comparison') || {}).textContent || '', turns: document.querySelectorAll('.sp-turn').length, chip: document.querySelector('#containerStatusText').textContent })""")
            check("after run 1 the executor chip is back to " + {"orchestrator": "Ready", "local": "Local", "direct": "Docker"}[compute] + " (2026-10-10: it stayed on Executing)",
                  rv["chip"] == {"orchestrator": "Ready", "local": "Local", "direct": "Docker"}[compute], rv["chip"])
            check("run 1 in the pane: the CHECK, RUN and COMPARE rows, no model card, and the closing card says run 1 reproduced run 0's line",
                  any("CHECK" in r and "field_trial.csv" in r for r in rv["rows"]) and any("RUN" in r and "run 1" in r for r in rv["rows"]) and any("COMPARE" in r and "run 0" in r for r in rv["rows"])
                  and rv["turns"] == 0 and "Run 1 complete" in rv["done"] and "reproduced: every result line as the run before (1 line)" in rv["done"] and "against run 0" in rv["done"] and not rv["warn"], (rv["rows"], rv["done"][:200]))
            check("run 1 in the panes: the strip reads run 1 · v1 against run 0, the id line names the routine and the run, the Comparison tab is first and open with the line (under the name the instruction gave it) within its interval",
                  "run 1" in rv["strip"] and "v1" in rv["strip"] and "run 0" in rv["strip"] and "Routine:" in rv["ids"] and "Run:1·v1" in rv["ids"].replace(" ", "")
                  and rv["tabs"] and rv["tabs"][0] == "tab-comparison" and rv["active"] == "content-comparison" and "against run 0" in rv["cmp"] and "within" in rv["cmp"] and "Yield, B vs A" in rv["cmp"], (rv["strip"], rv["ids"], rv["tabs"], rv["active"], rv["cmp"][:200]))
            check("run 1 in the panes: the Plots and Results tabs came through the stream as an analysis's do", "tab-plot" in rv["tabs"] and "tab-code_exec_results" in rv["tabs"], rv["tabs"])
            check("after run 1: the composer stays locked with the reason as its placeholder, the Save pill stays hidden, the position reads 2 of 2 - run 0 and run 1 - with the next arrow off and the previous one on (run 0)",
                  rv["locked"] and "open the analysis" in rv["placeholder"] and rv["pill"] == "none" and rv["arrows"] == [False, True], (rv["locked"], rv["placeholder"], rv["pill"], rv["arrows"]))
            # the run before (run 0) through the arrow, then forward again
            page.click("#prevResponse")
            wait_position(page, "1 of 2", 30000)
            page.wait_for_timeout(400)
            r0 = page.evaluate("() => ({ cmp: (document.getElementById('content-comparison') || {}).textContent || '', done: (document.querySelector('.sp-done') || {}).textContent || '', arrows: [document.getElementById('prevResponse').disabled, document.getElementById('nextResponse').disabled], tabs: [...document.querySelectorAll('#tabContainer .tab')].map(e => e.id) })")
            check("the previous arrow opens run 0 (the version's own check): its own line with the estimate and the interval, nothing it is against, the Results and Data tabs of the stored run, the previous arrow off",
                  r0["cmp"].startswith("Run 0 — the original data") and "against" not in r0["cmp"] and "Yield, B vs A" in r0["cmp"] and re.search(r"\[[+-]?\d", r0["cmp"]) is not None
                  and "Run 0 complete" in r0["done"] and r0["arrows"] == [True, False] and "tab-code_exec_results" in r0["tabs"] and "tab-dataframe" in r0["tabs"], r0)
            page.click("#nextResponse")
            wait_position(page, "2 of 2", 30000)
            # the favourite unlocks the composer (Saved workflows -> the card)
            page.click("#workflowManagerPill")
            page.wait_for_selector("#workflowManagerModal .workflow-card", timeout=15000)
            page.click("#workflowManagerModal .workflow-card")
            page.wait_for_function("() => /chain \\d of 4/.test(document.getElementById('chainPosition').textContent) && !document.getElementById('queryInput').disabled", timeout=15000)
            page.wait_for_timeout(300)
            unlocked = page.evaluate("() => ({ locked: document.body.classList.contains('composer-locked'), placeholder: document.getElementById('queryInput').placeholder, pos: document.getElementById('chainPosition').textContent, pill: getComputedStyle(document.getElementById('saveButton')).display })")
            check("loading a favourite leaves the run view: the composer is back with its own placeholder, the chains' navigation and the Save pill return",
                  not unlocked["locked"] and "open the analysis" not in unlocked["placeholder"] and "chain" in unlocked["pos"] and unlocked["pill"] != "none", unlocked)
            # the code map from a restored chain (2026-10-20, M5): the card saved as HTML carries the chain id, so its button still opens the map
            restored_btn = page.evaluate("() => { const b = document.querySelector('#streamOutput .sp-done .sp-codemap'); return b ? b.dataset.chain : null; }")
            check("a restored favourite's closing card keeps its Code map button with the chain's id", restored_btn and restored_btn == str(page.evaluate("() => responses[currentResponseIndex].chain_id")), restored_btn)
            page.click("#streamOutput .sp-done .sp-codemap")
            page.wait_for_selector("#codeMapModal .cm-row.step", timeout=15000)
            check("... and it opens that chain's map, built when the chain ended", page.evaluate("() => document.querySelector('#codeMapModal .cm-facts').getAttribute('data-built')") == "end")
            page.keyboard.press("Escape")
            page.wait_for_function("() => document.getElementById('codeMapModal').style.display === 'none'", timeout=5000)
            check("Escape closes the map", True)
            # run 2 with the other regime, compared with run 1 (the run before, the dialog's default now)
            page.click("#routinesPill")
            page.wait_for_selector("#routinesModal", state="visible", timeout=10000)
            page.wait_for_function("() => (document.querySelector('#routinesModal .rt-right .title') || {}).textContent", timeout=15000)
            page.click("#routinesModal [data-act='run']")
            page.wait_for_selector("#routineRunModal .rt-row[data-row='compare']", timeout=30000)
            cmp_choices = page.evaluate("() => ({ choices: [...document.querySelectorAll('#routineRunModal input[name=\"rt-compare\"]')].map(i => [i.value, i.checked]), note: document.querySelector('#routineRunModal .ui-dlg-f .note').textContent })")
            check("the run dialog after run 1 has the Compare row - the run before (on) and run 0 - and the footer the last run's time (nothing where it took under a second)", cmp_choices["choices"] == [["previous", True], ["zero", False]] and footer_time(rdirs[0], cmp_choices["note"], "the last run took "), cmp_choices)
            page.fill("#routineRunModal [data-key='regime']", "C")
            page.click("#routineRunModal [data-act='run']")
            wait_position(page, "3 of 3", 180000)
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
            page.wait_for_function("() => document.querySelectorAll('#routinesModal .rt-runs thead th[data-run]').length >= 3", timeout=15000)
            mg2 = page.evaluate("""() => ({ heads: [...document.querySelectorAll('#routinesModal .rt-runs thead th[data-run]')].map(e => [e.dataset.run, e.textContent.trim(), e.getAttribute('title')]), acts: [...document.querySelectorAll('#routinesModal .rt-runs thead th[data-run]')].map(e => [...e.querySelectorAll('.acts a')].map(a => a.textContent)),
                cols: [...document.querySelectorAll('#routinesModal .rt-runs thead th')].map(e => e.textContent.trim()), rows: document.querySelectorAll('#routinesModal .rt-runs tbody tr:not(.in)').length, values: [...document.querySelectorAll('#routinesModal .rt-runs tbody tr:not(.in) td.num')].map(e => e.textContent), sub: document.querySelector('#routinesModal .rt-right .sub').textContent,
                ins: [...document.querySelectorAll('#routinesModal .rt-runs tbody tr.in')].map(tr => [...tr.querySelectorAll('td.label, td.num')].map(td => td.textContent.trim())),
                filter: [...document.querySelectorAll('#routinesModal .rt-filter [data-filter]')].map(e => e.dataset.filter + ':' + e.className + ':' + ((e.querySelector('.k') || {}).textContent || '')), list: !!document.querySelector('#routinesModal .rt-run, #routinesModal .rt-runbox, #routinesModal .rt-legend') })""")
            check("the manager after two runs: the filter bar on Custom with its 3 runs, the set intervals greyed (none run); the runs table has a column per run (0, 1, 2), each head with Open and Delete on hover (run 0 without Delete), a row for the routine's line with the values without a plus sign and, above it, a row for the input the runs differ in (2026-11-14: the regime - B, B, C), no trend across custom runs; no runs list and no legend (2026-11-08)",
                  [h[0] for h in mg2["heads"]] == ["0", "1", "2"] and mg2["acts"] == [["Open"], ["Open", "Delete"], ["Open", "Delete"]] and mg2["rows"] == 1 and all(not v.startswith("+") for v in mg2["values"]) and len(mg2["values"]) == 3
                  and mg2["ins"] == [["The regime compared with A input", "B", "B", "C"]]
                  and sum(1 for c in mg2["cols"] if re.match(r"Run [012]", c)) == 3 and "Trend" not in mg2["cols"] and mg2["filter"] == ["day:off:", "week:off:", "month:off:", "year:off:", "custom:on:3"] and not mg2["list"], mg2)
            page.click("#routinesModal .rt-runs thead th[data-run='1']")
            wait_position(page, "2 of 3", 30000)
            page.wait_for_timeout(400)
            opened = page.evaluate("() => ({ cmp: (document.getElementById('content-comparison') || {}).textContent || '', pos: document.getElementById('chainPosition').textContent, arrows: [document.getElementById('prevResponse').disabled, document.getElementById('nextResponse').disabled], locked: document.getElementById('queryInput').disabled })")
            check("a run's head in the manager's table opens run 1 in the main panes: its comparison against run 0, both arrows on, the composer locked again",
                  "against run 0" in opened["cmp"] and opened["arrows"] == [False, False] and opened["locked"], opened)
            page.click("#nextResponse")
            wait_position(page, "3 of 3", 30000)
            # the dialog loads the data itself (2026-10-10): a file routine offers an upload beside the data loaded now; the same file
            # again, compared with run 0, reproduces, and the pane opens with a LOAD row
            page.click("#routinesPill")
            page.wait_for_selector("#routinesModal", state="visible", timeout=10000)
            page.wait_for_function("() => (document.querySelector('#routinesModal .rt-right .title') || {}).textContent", timeout=15000)
            page.click("#routinesModal [data-act='run']")
            page.wait_for_selector("#routineRunModal .rt-row[data-row='data']", timeout=30000)
            choices = page.evaluate("() => [...document.querySelectorAll('#routineRunModal input[name=\"rt-data\"]')].map(i => [i.value, i.checked])")
            check("the run dialog of a file routine offers an upload and a file from the Dataset cache beside the data loaded now (on)", choices == [["upload", False], ["cache", False], ["now", True]], choices)
            page.set_input_files("#routineRunModal input[data-load='file']", st.dataset)
            page.wait_for_timeout(200)
            up_state = page.evaluate("() => ({ upload: document.querySelector('#routineRunModal input[name=\"rt-data\"][value=\"upload\"]').checked, runOn: !document.querySelector('#routineRunModal [data-act=\"run\"]').disabled })")
            check("choosing a file switches the choice to the upload and keeps Run on", up_state["upload"] and up_state["runOn"], up_state)
            page.click("#routineRunModal input[name='rt-compare'][value='zero']")
            page.click("#routineRunModal [data-act='run']")
            wait_position(page, "4 of 4", 240000)
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
            nofit = page.evaluate("() => ({ fit: document.querySelector('#routineRunModal .rt-fit').textContent, bad: document.querySelector('#routineRunModal .rt-fit').classList.contains('bad'), shown: document.querySelector('#routineRunModal .rt-fit').style.display !== 'none', data: document.querySelector('#routineRunModal .rt-row[data-row=\"data\"]').textContent, runOn: !document.querySelector('#routineRunModal [data-act=\"run\"]').disabled })")
            check("with no_soil.csv loaded the run dialog says under Data that soil will be empty in this data (the frame being the choice, the line shows) - not a refusal: the run adds the column empty and the coach decides; Run stays on",
                  not nofit["bad"] and nofit["shown"] and "1 of 6 columns empty in this data: soil" in nofit["fit"] and "no_soil.csv" in nofit["data"] and nofit["runOn"], nofit)
            page.click("#routineRunModal [data-act='run']")
            wait_position(page, "5 of 5", 240000)
            page.wait_for_timeout(600)
            r4 = page.evaluate("""() => ({ rows: [...document.querySelectorAll('.sp-row.tool')].map(e => e.textContent), done: (document.querySelector('.sp-done') || {}).textContent || '', warn: !!document.querySelector('.sp-done.warn'),
                cmp: (document.getElementById('content-comparison') || {}).textContent || '', pos: document.getElementById('chainPosition').textContent })""")
            check("run 4 on the file without soil: the CHECK row says the column is empty; the statement of cell 2 that divides by a count of zero stops and costs its own line - the run is kept as one that ran, 0 of 1 result line "
                  "with the reason beside it; no warning tone",
                  any("CHECK" in r and "empty in this data: soil" in r for r in r4["rows"]) and "Run 4 complete" in r4["done"] and "ran: 0 of 1 result line; 1 not computed (cell 2 stopped: ZeroDivisionError" in r4["done"] and not r4["warn"]
                  and r4["pos"] == "5 of 5", (r4["rows"][-3:], r4["done"][:300], r4["pos"]))
            # the statement that stopped (docs/ROUTINES_DESIGN.md §22): one line on the Trend tab - its cell, the error - opening on its code; the line it cost is not computed
            r4s = page.evaluate("""() => ({ stopped: [...document.querySelectorAll('#content-comparison details.rt-stopped summary')].map(e => e.textContent), code: [...document.querySelectorAll('#content-comparison details.rt-stopped code')].map(e => e.textContent),
                words: [...document.querySelectorAll('#content-comparison .rt-cmp-table tbody tr')].map(tr => tr.querySelectorAll('td')[4].textContent.trim()), why: [...document.querySelectorAll('#content-comparison .rt-cmp-table tbody tr')].map(tr => tr.querySelectorAll('td')[4].getAttribute('title') || ''),
                error: !!document.querySelector('#content-comparison .rt-error') })""")
            check("the Trend tab of run 4 names the statement that stopped - cell 2, the error - with its code under it (the call of the adjusted difference); its result line is not computed, the reason on hover; no error block; the COMPARE row says nothing was compared",
                  len(r4s["stopped"]) >= 1 and r4s["stopped"][0].startswith("cell 2 stopped: ZeroDivisionError") and "adj_diff" in r4s["code"][0] and "def adj_diff" not in r4s["code"][0] and r4s["words"] == ["· not computed"]
                  and r4s["why"][0].startswith("cell 2 stopped: ZeroDivisionError") and not r4s["error"] and any("COMPARE" in r and "no result line to compare" in r for r in r4["rows"]), (r4s, r4["rows"][-2:]))
            # what differs, said in sentences (step 4, 2026-10-11): the CHECK row says the rows against the original's; the Data tab lists it
            check("the CHECK rows say the rows against the original's: run 3's file the same rows as the original, run 4's too, the column empty said beside it",
                  any("CHECK" in r and "rows as the original" in r for r in r3["rows"]) and any("CHECK" in r and "rows as the original" in r and "empty in this data: soil" in r for r in r4["rows"]), (r3["rows"], r4["rows"]))
            # the stored run, opened with the arrow: its CHECK row says what the live one said, and its Data tab lists what differed
            page.click("#prevResponse")
            wait_position(page, "4 of 5", 30000)
            page.wait_for_timeout(400)
            r3s = page.evaluate("() => { activateTab('dataframe'); return { rows: [...document.querySelectorAll('.sp-row.tool')].map(e => e.textContent), data: (document.getElementById('content-dataframe') || {}).textContent || '' }; }")
            check("run 3 opened from its record: the CHECK row carries the recorded line (the rows as the original), and the Data tab lists it under Differs",
                  "rows as the original" in [r for r in r3s["rows"] if "CHECK" in r][-1] and "Differs" in r3s["data"] and "rows as the original" in r3s["data"], (r3s["rows"][-4:], r3s["data"][:200]))
            page.click("#nextResponse")
            wait_position(page, "5 of 5", 30000)
            page.wait_for_timeout(300)
            # the Dataset cache's pick (step 4, 2026-10-11): a file routine's dialog offers the files the executor's cache holds - the
            # uploads of this walk - and a run on one of them; the local edition has no executor cache, so the choice stays hidden
            page.click("#routinesPill")
            page.wait_for_selector("#routinesModal", state="visible", timeout=10000)
            page.wait_for_function("() => (document.querySelector('#routinesModal .rt-right .title') || {}).textContent", timeout=15000)
            page.click("#routinesModal [data-act='run']")
            page.wait_for_selector("#routineRunModal .rt-row[data-row='data']", timeout=30000)
            page.wait_for_timeout(1200)
            pick = page.evaluate("""() => { const picks = [...document.querySelectorAll('#routineRunModal .rt-cachepick')]; const sel = document.querySelector('#routineRunModal select[data-load="cached"]');
                return { shown: picks.length === 2 && picks.every(e => e.style.display !== 'none'), options: sel ? [...sel.options].map(o => o.textContent) : [] }; }""")
            if edition == "hosted":
                check("the file routine's dialog offers a file from the Dataset cache: the walk's uploads, newest first, with their rows and the day",
                      pick["shown"] and len(pick["options"]) >= 3 and any("no_soil.csv" in o for o in pick["options"]) and any("field_trial.csv" in o and "720 rows" in o for o in pick["options"]), pick)
                # run 5 on field_trial.csv taken from the cache: no upload, the LOAD row says so, and it reproduces run 3's line
                page.evaluate("""() => { const sel = document.querySelector('#routineRunModal select[data-load="cached"]'); const opt = [...sel.options].find(o => o.textContent.includes('field_trial.csv'));
                    sel.value = opt.value; sel.dispatchEvent(new Event('change', { bubbles: true })); }""")
                page.wait_for_timeout(200)
                check("choosing a cached file checks its choice and turns Run on", page.evaluate("() => document.querySelector('#routineRunModal input[name=\"rt-data\"][value=\"cache\"]').checked && !document.querySelector('#routineRunModal [data-act=\"run\"]').disabled"))
                page.click("#routineRunModal input[name='rt-compare'][value='zero']")
                page.click("#routineRunModal [data-act='run']")
                wait_position(page, "6 of 6", 240000)
                page.wait_for_timeout(600)
                r5 = page.evaluate("""() => ({ rows: [...document.querySelectorAll('.sp-row.tool')].map(e => e.textContent), done: (document.querySelector('.sp-done') || {}).textContent || '',
                    pills: [...document.querySelectorAll('.primary-dataset-pill')].map(p => p.textContent) })""")
                check("run 5 from the Dataset cache: the LOAD row names the file and the cache, the CHECK row the rows as the original, one primary pill, and the run reproduces run 0",
                      any("LOAD" in r and "field_trial.csv" in r and "from the Dataset cache" in r for r in r5["rows"]) and any("CHECK" in r and "rows as the original" in r for r in r5["rows"])
                      and "Run 5 complete" in r5["done"] and "reproduced" in r5["done"] and "against run 0" in r5["done"] and len(r5["pills"]) == 1 and "field_trial.csv" in r5["pills"][0], (r5["rows"][-4:], r5["done"][:200], r5["pills"]))
            else:
                check("the local edition has no executor cache: the file routine's dialog keeps the Dataset cache's choice hidden", not pick["shown"], pick)
                page.click("#routineRunModal [data-act='cancel']")
                page.wait_for_timeout(200)
            page.evaluate("RoutinesUI.closeManager()")
            run_files = sorted(os.path.basename(p) for p in glob.glob(os.path.join(os.path.dirname(rdirs[0]), "runs", "*"))) if rdirs else []
            rj2 = json.load(open(rdirs[0])) if rdirs else {}
            run4_folder = os.path.join(os.path.dirname(rdirs[0]), "runs", "v1_4")
            run4 = json.load(open(os.path.join(run4_folder, "run.json"))) if "v1_4" in run_files else {}
            run1 = json.load(open(os.path.join(os.path.dirname(rdirs[0]), "runs", "v1_1", "run.json"))) if "v1_1" in run_files else {}
            _n_runs = 5 if edition == "hosted" else 4
            run5 = json.load(open(os.path.join(os.path.dirname(rdirs[0]), "runs", "v1_5", "run.json"))) if "v1_5" in run_files else {}
            check("on disk: runs/v1_0 (run zero) to the last run with run.json and stdout.txt; routine.json lists the runs with their status, data and comparison; the run that lost a statement keeps it - the cell, the code, the error - with the line it cost blank for that reason, the fit it ran under and its own folder on the executor's side; the cache-picked run's load says the file and the cache",
                  run_files == ["v1_%d" % i for i in range(_n_runs + 1)] and os.path.exists(os.path.join(os.path.dirname(rdirs[0]), "runs", "v1_1", "stdout.txt"))
                  and [x["number"] for x in rj2.get("runs", [])] == list(range(1, _n_runs + 1)) and [x["status"] for x in rj2["runs"]][:4] == ["reproduced", "ran", "reproduced", "ran"] and rj2["runs"][1]["inputs"] == {"regime": "C"}
                  and (edition != "hosted" or (rj2["runs"][4]["status"] == "reproduced" and run5.get("data", {}).get("load") == {"source": "file", "name": "field_trial.csv", "cached": True} and run5.get("data", {}).get("name") == "field_trial.csv"))
                  and run1.get("against") == 0 and run1.get("comparison", {}).get("compared") == 1 and run1.get("data", {}).get("name") == "field_trial.csv" and len(run1.get("results", [])) == 1
                  and run1.get("stopped") == [] and run1.get("gaps") == [] and run4.get("error") == "" and [(s["cell"], s["error"].split(":")[0]) for s in run4.get("stopped", [])][:1] == [(2, "ZeroDivisionError")]
                  and "adj_diff" in run4["stopped"][0]["code"] and run4["results"][0]["estimate"] is None and run4["results"][0]["why"].startswith("cell 2 stopped: ZeroDivisionError")
                  and rj2["runs"][3]["results"][0]["why"].startswith("cell 2 stopped: ZeroDivisionError") and run4.get("fit", {}).get("missing") == ["soil"] and run4.get("run_dir", "").endswith("/v1_4") and run4.get("data", {}).get("load", {}).get("source") == "file",
                  (run_files, [(x.get("number"), x.get("status"), x.get("inputs")) for x in rj2.get("runs", [])], run4.get("fit"), run4.get("run_dir")))
            # a run deleted from the history (2026-11-08, docs/ROUTINES_DESIGN.md §21): run 4 - the one that lost its line - is a column of the Custom
            # table like the others, its cell a dot that says why; Delete in its head asks, the line and the folder go, the Summary is read again
            page.click("#routinesPill")
            page.wait_for_selector("#routinesModal", state="visible", timeout=10000)
            all_heads = [str(n) for n in range(0, _n_runs + 1)]                                             # run 0, then every run: each ran
            page.wait_for_function("(want) => [...document.querySelectorAll('#routinesModal .rt-runs thead th[data-run]')].map(e => e.dataset.run).join(',') === want", arg=",".join(all_heads), timeout=15000)
            before_del = page.evaluate("""() => ({ heads: [...document.querySelectorAll('#routinesModal .rt-runs thead th[data-run]')].map(e => e.dataset.run), failed: document.querySelectorAll('#routinesModal .rt-foot .rt-failed').length,
                acts: [...document.querySelectorAll('#routinesModal .rt-runs thead th[data-run="4"] .acts a')].map(a => a.textContent), cells: [...document.querySelectorAll('#routinesModal .rt-runs tbody tr:not(.in) td.num')].map(td => td.textContent),
                why: ([...document.querySelectorAll('#routinesModal .rt-runs tbody td.num')].filter(td => td.querySelector('.rt-mark.missing')).map(td => td.getAttribute('title'))[0] || '') })""")
            page.once("dialog", lambda d: d.accept())
            page.click("#routinesModal .rt-runs thead th[data-run='4'] [data-act='delete-run']")
            page.wait_for_function("() => !document.querySelector('#routinesModal .rt-runs thead th[data-run=\"4\"]') && document.querySelectorAll('#routinesModal .rt-runs thead th[data-run]').length > 0", timeout=15000)
            after_del = page.evaluate("() => ({ heads: [...document.querySelectorAll('#routinesModal .rt-runs thead th[data-run]')].map(e => e.dataset.run), side: (document.querySelector('#routinesModal .rt-side .it span') || {}).textContent || '' })")
            rj3 = json.load(open(rdirs[0]))
            check("the run that lost its line is a column of the Custom table - a dot where its number would be, the reason on hover - and nothing is named under the table as failed; Delete in its head: the run asked about and gone - off the "
                  "table, off routine.json, its folder off the disk - the other runs standing with their numbers, the rail's count down by one",
                  before_del["heads"] == all_heads and before_del["failed"] == 0 and before_del["acts"] == ["Open", "Delete"] and before_del["cells"][4] == "·" and before_del["why"].startswith("cell 2 stopped: ZeroDivisionError")
                  and after_del["heads"] == [h for h in all_heads if h != "4"] and [x["number"] for x in rj3.get("runs", [])] == [n for n in range(1, _n_runs + 1) if n != 4]
                  and not os.path.isdir(run4_folder) and f"{_n_runs - 1} runs" in after_del["side"], (before_del, after_del, [x["number"] for x in rj3.get("runs", [])]))
            page.evaluate("RoutinesUI.closeManager()")
            # back to the thread for the rest of the walk
            page.click("#workflowManagerPill")
            page.wait_for_selector("#workflowManagerModal .workflow-card", timeout=15000)
            page.click("#workflowManagerModal .workflow-card")
            page.wait_for_function("() => /chain \\d of 4/.test(document.getElementById('chainPosition').textContent) && !document.getElementById('queryInput').disabled", timeout=15000)
            page.wait_for_timeout(300)
            # a follow-up after the data changed (2026-10-12): another file loaded through the Data tab, then a question on chain 1 -
            # the earlier chains' cells ran on data that is no longer loaded, so the follow-up starts in a fresh kernel, its ledger
            # marks them as on other data, and its replay re-runs its own cell only
            page.set_input_files("#primaryFile", no_soil)
            page.wait_for_function("() => [...document.querySelectorAll('.primary-dataset-pill')].some(p => /no_soil\\.csv\\) loaded/.test(p.textContent))", timeout=60000)
            for _ in range(4):
                if page.evaluate("() => document.getElementById('prevResponse').disabled"):
                    break
                page.click("#prevResponse")
                page.wait_for_timeout(400)
            check("chain navigation: on chain 1 of 4 with the other file loaded", "chain 1 of 4" in page.inner_text("#chainPosition"), page.inner_text("#chainPosition"))
            page.fill("#queryInput", "How many rows does this file have?")
            page.click("#submitQuery")
            wait_text(page, "#chainPosition", "chain 5 of 5", 60000)
            wait_run_end(page, 5)
            p5 = prompt_of(1)
            done5 = page.evaluate("() => { const d = document.querySelectorAll('.sp-done'); return d.length ? d[d.length - 1].textContent : ''; }")
            check("a follow-up on chain 1 after no_soil.csv was loaded: its first prompt's ledger keeps chain 1 marked as on other data (field_trial.csv, its cells not in the kernel), lists no names, and CELLS SO FAR starts empty",
                  "[run 1] Q: " + q1 in p5["user"] and "On other data (field_trial.csv" in p5["user"] and "not in the kernel (SHOW n re-opens one from the record)" in p5["user"]
                  and "Names left in the kernel" not in p5["user"] and "CELLS SO FAR:\n(no cells yet)" in p5["user"], p5["user"][:700])
            cell5 = page.evaluate("() => [...document.querySelectorAll('#streamOutput .sp-row[data-cell]')].map(e => Number(e.getAttribute('data-cell')))")
            check("...the chain's one cell is numbered along the path (after chain 1's cells) and its replay re-runs that cell only, reproduced",
                  "Replay reproduced" in done5 and "(1 cells," in done5 and len(cell5) == 1 and cell5[0] > 3, (done5[:160], cell5))
            # the same file uploaded again (a new frame id, the same name, rows and columns): the same data - a follow-up on chain 1 is
            # rehydrated from its cells as any follow-up, its ledger plain, its replay the whole path (2026-10-12: a favourite continued
            # in a new session, the file uploaded again)
            page.set_input_files("#primaryFile", st.dataset)
            page.wait_for_function("() => [...document.querySelectorAll('.primary-dataset-pill')].some(p => /field_trial\\.csv\\) loaded/.test(p.textContent))", timeout=60000)
            for _ in range(6):
                if page.evaluate("() => document.getElementById('prevResponse').disabled"):
                    break
                page.click("#prevResponse")
                page.wait_for_timeout(400)
            check("chain navigation: on chain 1 of 5 with the same file uploaded again", "chain 1 of 5" in page.inner_text("#chainPosition"), page.inner_text("#chainPosition"))
            page.fill("#queryInput", "How many rows does this file have?")
            page.click("#submitQuery")
            wait_text(page, "#chainPosition", "chain 6 of 6", 60000)
            wait_run_end(page, 6)
            p6 = prompt_of(1)
            done6 = page.evaluate("() => { const d = document.querySelectorAll('.sp-done'); return d.length ? d[d.length - 1].textContent : ''; }")
            check("a follow-up on chain 1 with the same file uploaded again: its prompt's ledger is plain (no 'other data' mark, the names line present) and CELLS SO FAR lists chain 1's cells; the replay re-runs the whole path",
                  "On other data" not in p6["user"] and "Names left in the kernel" in p6["user"] and "--- cell 1 ---" in p6["user"] and "CELLS SO FAR:\n(no cells yet)" not in p6["user"]
                  and "Replay reproduced" in done6 and "(1 cells," not in done6, (p6["user"][:500], done6[:160]))
            # Ask AI about a plot (2026-10-13): the Plots tab's chat button sends the picture with the question; the analyst's model
            # takes images (the stack's harness model is flagged so), the prompt names the figure, and the scripted analyst saw it
            for _ in range(6):
                if page.evaluate("() => document.getElementById('prevResponse').disabled"):
                    break
                page.click("#prevResponse")
                page.wait_for_timeout(400)
            page.evaluate("activateTab('plot')")
            page.wait_for_timeout(300)
            plots_now = page.evaluate("() => [...document.querySelectorAll('#content-plot .plot-container')].map(c => ({ id: c.getAttribute('data-plot-id'), png: !!c.querySelector('.plot-image'), plotly: !!c.querySelector('.plotly-plot') }))")
            check("chain 1's Plots tab: plot 1 is the matplotlib PNG, plot 2 the Plotly figure (the executor returns the figures in order; the Plotly files numbered as shown)",
                  [p_["id"] for p_ in plots_now] == ["plot_1", "plot_2"] and plots_now[0]["png"] and plots_now[1]["plotly"], plots_now)
            page.click("#content-plot .plot-container[data-plot-id='plot_1'] .plot-query-btn")
            page.fill("#content-plot .plot-container[data-plot-id='plot_1'] .plot-query-input", "What does the taller bar mean?")
            page.click("#content-plot .plot-container[data-plot-id='plot_1'] .plot-query-submit")
            wait_text(page, "#chainPosition", "chain 7 of 7", 60000)
            wait_run_end(page, 7)
            p7 = prompt_of(1)
            ans7 = page.evaluate("() => { activateTab('answer'); return (document.getElementById('content-answer') || {}).textContent || ''; }")
            check("Ask AI about plot 1: a new chain with the question, its prompt naming the figure attached, and the analyst's model given the picture (the scripted analyst's report says it was in view)",
                  "QUESTION:\nWhat does the taller bar mean?" in p7["user"] and "THE FIGURE THE PERSON ASKS ABOUT is attached" in p7["user"] and "[a picture was attached to this message" in p7["user"]
                  and "The figure attached to the question was in view." in ans7, (p7["user"][:300], ans7[:300]))
            # the reach report (2026-10-28): a chain whose first cell the executor refuses (the blacklist) and whose second
            # fetches from the fake integrations service, which the question does not name - the pane's rows, the closing
            # card, the Investigation tab, the code map and the record
            page.fill("#queryInput", mod.REACH_QUESTION)
            page.click("#submitQuery")
            wait_text(page, "#chainPosition", "chain 8 of 8", 60000)
            wait_run_end(page, 8)
            page.wait_for_timeout(500)
            rows8 = page.evaluate("""() => { const rows = [...document.querySelectorAll('#streamOutput .sp-row')]; return {
                restricted: rows.filter(r => r.classList.contains('restricted')).map(r => ({ out: r.querySelector('.out').textContent, t: r.querySelector('.t').textContent, fail: r.classList.contains('fail'), glyph: r.firstElementChild.textContent })),
                reach: rows.filter(r => r.querySelector('.reach')).map(r => ({ cell: r.dataset.cell, text: r.querySelector('.reach').textContent, unasked: r.querySelector('.reach').classList.contains('unasked'), title: r.querySelector('.reach').getAttribute('title') })),
                failed: rows.filter(r => r.classList.contains('fail')).length }; }""")
            check("the pane: the refused cell is its own row - ⊘, 'not run: restricted operation (subprocess)', 'not run' - not a failed row; the fetch cell carries its tag in the kernel's colour, the service's address and the bytes, 'not asked for' in the hover",
                  len(rows8["restricted"]) == 1 and rows8["restricted"][0]["out"] == "not run: restricted operation (subprocess)" and rows8["restricted"][0]["t"] == "not run" and not rows8["restricted"][0]["fail"] and rows8["restricted"][0]["glyph"] == "⊘"
                  and len(rows8["reach"]) == 1 and rows8["reach"][0]["unasked"] and rows8["reach"][0]["text"].startswith("↓") and "127.0.0.1:" in rows8["reach"][0]["text"] and rows8["reach"][0]["title"].endswith("not asked for")
                  and rows8["failed"] == 0, rows8)
            card8 = page.evaluate("""() => { const d = [...document.querySelectorAll('#streamOutput .sp-done')].pop(); const r = d.querySelector('.reaches'); return r ? { h: r.querySelector('.h').textContent, nums: d.querySelector('.head .nums').textContent,
                lines: [...r.querySelectorAll('.r')].map(x => ({ c: x.querySelector('.c').textContent, what: x.querySelector('.what').textContent, tag: x.querySelector('.tag').textContent, unasked: x.classList.contains('unasked') })),
                sandbox: (r.querySelector('.sandbox') || {}).textContent || '' } : null; }""")
            check("the closing card: '1 reach outside the data (1 not asked for) · 1 cell not run', the fetch line with its cell and 'not asked for', the refused attempt, the count of cells saying 1 not run, and the sandbox line naming the box (no container: the stack's executor is a local process)",
                  card8 and card8["h"] == "1 reach outside the data (1 not asked for) · 1 cell not run" and "(1 not run)" in card8["nums"] and len(card8["lines"]) == 2
                  and card8["lines"][0]["c"].startswith("cell ") and card8["lines"][0]["what"].startswith("fetched ") and "127.0.0.1:" in card8["lines"][0]["what"] and card8["lines"][0]["tag"] == "not asked for" and card8["lines"][0]["unasked"]
                  and card8["lines"][1]["c"].startswith("attempt after cell ") and card8["lines"][1]["what"] == "not run: restricted operation (subprocess)" and card8["lines"][1]["tag"] == "refused"
                  and card8["sandbox"].startswith("Sandbox: ") and "no container seen" in card8["sandbox"] and "metadata address" in card8["sandbox"], card8)
            nb8 = page.evaluate("() => { activateTab('plan'); const c = document.getElementById('content-plan'); return { restricted: c.querySelectorAll('.nb-cell--restricted').length, failed: c.querySelectorAll('.nb-cell--failed').length, notrun: (c.querySelector('.nb-out--restricted') || {}).textContent || '', reach: [...c.querySelectorAll('.nb-reach')].map(x => [x.className, x.textContent]) }; }")
            check("the Investigation tab: the refused cell marked restricted with its 'Not run' line, no failed cell, the fetch cell's tag in its header",
                  nb8["restricted"] == 1 and nb8["failed"] == 0 and nb8["notrun"].startswith("Not run") and "subprocess" in nb8["notrun"] and len(nb8["reach"]) == 1 and nb8["reach"][0][0] == "nb-reach unasked" and "127.0.0.1" in nb8["reach"][0][1], nb8)
            page.click("#streamOutput .sp-done:last-of-type .sp-codemap")
            page.wait_for_function("() => { const m = document.getElementById('codeMapModal'); return !!m && getComputedStyle(m).display !== 'none' && m.querySelectorAll('.cm-row').length > 0; }", timeout=20000)
            map8 = page.evaluate("""() => { const m = document.getElementById('codeMapModal'); return {
                meta: (m.querySelector('.cm-facts') || m).textContent.includes('1 cell not run'),
                restricted: [...m.querySelectorAll('.cm-row.restricted')].map(r => r.querySelector('.cm-restricted-text').textContent),
                failedRows: m.querySelectorAll('.cm-row.failed').length,
                chip: [...m.querySelectorAll('.cm-reach-chip')].map(c => [c.className, c.textContent]),
                section: [...m.querySelectorAll('.cm-check.reach')].map(c => [c.className, c.textContent, c.getAttribute('data-act'), c.getAttribute('data-cell')]),
                heads: [...m.querySelectorAll('.cm-panel .cm-h')].map(h => h.textContent) }; }""")
            check("the code map: the meta line says 1 cell not run; the refused attempt is its own row (not a failed row); the fetch step carries the reach chip; the summary's section lists the reach (a button to its step) and the refused attempt before 'Worth checking'",
                  map8["meta"] and len(map8["restricted"]) == 1 and map8["restricted"][0].startswith("Not run · restricted operation (subprocess)") and map8["failedRows"] == 0
                  and len(map8["chip"]) == 1 and map8["chip"][0][0] == "cm-chip cm-reach-chip" and "127.0.0.1" in map8["chip"][0][1]
                  and len(map8["section"]) == 2 and map8["section"][0][0] == "cm-check reach unasked" and "not asked for" in map8["section"][0][1] and map8["section"][0][2] == "pick-s" and map8["section"][0][3]
                  and "refused" in map8["section"][1][1] and map8["heads"].index("Reaches outside the data") < map8["heads"].index("Worth checking"), map8)
            page.evaluate("CodeMapUI.close()")
            page.wait_for_timeout(300)
            errs = page.evaluate("window.__stackErrors || []")
            # what landed on disk, in the app's own layout under the stack's web app working directory
            wa = os.path.join(workdir, "webapp")
            threads = glob.glob(os.path.join(wa, "storage", USER, "threads", "*.json"))
            check("one notebook thread file stored under storage/<user>/threads", len(threads) == 1, threads)
            nb = json.load(open(threads[0])) if threads else {"runs": {}}
            runs = list(nb["runs"].values())
            # the document chain's one cell (the grep) replays like any other
            check("the thread holds eight runs, all answered; every chain with cells reproduced",
                  len(runs) == 8 and all(r["status"] == "answered" for r in runs)
                  and all((r["replay_status"] == "reproduced") == any(t_["kind"] == "cell" for t_ in r["turns"]) for r in runs),
                  [(r["status"], r["replay_status"], sum(1 for t_ in r["turns"] if t_["kind"] == "cell")) for r in runs])
            check("the second run's parent is the first", len(runs) >= 2 and runs[1]["parent"] == runs[0]["id"])
            # the code map (2026-10-20, M3): built at each chain's end by the host, through the executor's columns call
            with_cells = [r for r in runs if any(t_["kind"] == "cell" and t_.get("cell_no") for t_ in r["turns"])]
            check("every chain with cells carries its code map, built at its end with no error, its view naming the chain and the primary by its file",
                  with_cells and all(r["code_map"].get("view") and "error" not in r["code_map"] and r["code_map"]["view"]["chain_id"] == r["id"]
                                     and r["code_map"]["inputs"][0]["kind"] == "primary" and r["code_map"]["inputs"][0]["name"].endswith(".csv") for r in with_cells),
                  [(r["id"], {k_: v for k_, v in r["code_map"].items() if k_ != "view"}) for r in with_cells][:2])
            doc_runs = [r for r in with_cells if r["question"] == mod.DOC_QUESTION]
            check("the document chain's map lists the document as an input, as the kernel names it, and its cell read it",
                  doc_runs and any(i.get("kind") == "document" and i.get("label") == "D1" and i.get("name") == mod.DOC_NAME for i in doc_runs[0]["code_map"]["inputs"])
                  and any(i["kind"] == "document" and i["status"] == "used" for i in doc_runs[0]["code_map"]["view"]["inputs"]),
                  (doc_runs[0]["code_map"]["inputs"], doc_runs[0]["code_map"]["view"]["inputs"]) if doc_runs else runs)
            cm_j = page.evaluate("(a) => window.authService.fetch('/code_map/' + a[0] + '/' + a[1]).then(r => r.json())", [nb["thread_id"], runs[0]["id"]])
            check("the route answers the first chain's map as stored at its end", cm_j.get("built") == "end" and cm_j.get("map", {}).get("chain_id") == runs[0]["id"]
                  and cm_j["map"]["results"], {k_: v for k_, v in cm_j.items() if k_ != "map"})
            check("the fifth run - the follow-up after the data changed - stands on the first, ran on the other file (its own data record), and its replay script holds its cell alone",
                  runs[4]["parent"] == runs[0]["id"] and runs[4]["data"].get("name") == "no_soil.csv" and runs[4]["data"].get("df_id") not in (None, runs[0]["data"].get("df_id"))
                  and runs[4]["replay_script"].count("# --- cell") == 1 and "adj_diff" not in runs[4]["replay_script"], (runs[4]["data"].get("name"), runs[4]["replay_script"].count("# --- cell")))
            check("the sixth run - the follow-up with the same file uploaded again - stands on the first under a new frame id, and its replay script holds chain 1's cells with its own",
                  runs[5]["parent"] == runs[0]["id"] and runs[5]["data"].get("name") == "field_trial.csv" and runs[5]["data"].get("df_id") != runs[0]["data"].get("df_id")
                  and runs[5]["replay_script"].count("# --- cell") >= 4 and "adj_diff" in runs[5]["replay_script"], (runs[5]["data"].get("name"), runs[5]["replay_script"].count("# --- cell")))
            r8 = runs[7]
            t8 = [t_ for t_ in r8["turns"] if t_["kind"] == "cell"]
            check("the record: the eighth run's refused cell carries the restricted word and no cell number, its fetch cell the reach marked not asked for with the bytes and the line, the run its sandbox, and its map the report",
                  len(t8) == 2 and t8[0]["refused"] == "subprocess" and t8[0]["cell_no"] is None and t8[0]["reaches"] == [] and t8[1]["refused"] == "" and len(t8[1]["reaches"]) == 1
                  and t8[1]["reaches"][0]["kind"] == "net" and t8[1]["reaches"][0]["asked"] is False and t8[1]["reaches"][0]["in"] > 0 and t8[1]["reaches"][0]["line"] == 2
                  and r8["sandbox"].get("uid") is not None and r8["code_map"]["view"]["reaches"]["counts"] == {"lines": 1, "unasked": 1, "asked": 0, "blocked": 0, "refused": 1, "net": 1},
                  ([(t_.get("refused"), t_.get("cell_no"), t_.get("reaches")) for t_ in t8], r8.get("sandbox"), (r8.get("code_map") or {}).get("view", {}).get("reaches")))
            favs = glob.glob(os.path.join(wa, "storage", USER, "favourites", "*", "*.json"))
            check("Save wrote the favourites (one file per chain of the thread)", len(favs) == 4, favs)
            check("the old memory is retired (2.8): no favourite carries a rating, and nothing made a memory folder in the working directory",
                  all("rank" not in json.load(open(f)) for f in favs) and not os.path.exists(os.path.join(wa, "memory")), sorted(os.listdir(wa)))
            gone = page.evaluate("""() => Promise.all([['/submit_rank', 'POST'], ['/memory/review', 'GET'], ['/memory/review/action', 'POST'], ['/storage/favourites', 'POST']]
                .map(([u, m]) => window.authService.fetch(u, { method: m, headers: { 'Content-Type': 'application/json' }, body: m === 'POST' ? '{}' : undefined }).then(r => r.status)))""")
            check("its routes are gone: the rating, the memory review and its action, the single-favourite save all answer 404", gone == [404, 404, 404, 404], gone)

            # a chain asked from an earlier chain (0318, docs/BRANCH_DESIGN.md §3): the kernel keeps the state of every cell, so
            # it goes back to the state that chain ended in - nothing is run again - and what the chain asked after it made is
            # not there. Chain 7 is the earlier one; the kernel is at the end of chain 8, whose cell made `calls`
            for _ in range(8):
                if page.evaluate("() => document.getElementById('nextResponse').disabled"):
                    break
                page.click("#nextResponse")
                page.wait_for_timeout(400)
            page.click("#prevResponse")
            wait_text(page, "#chainPosition", "chain 7 of 8", 10000)
            page.fill("#queryInput", mod.BACK_QUESTION)
            page.click("#submitQuery")
            wait_text(page, "#chainPosition", "chain 9 of 9", 60000)
            wait_run_end(page, 9)
            row9 = page.evaluate("() => [...document.querySelectorAll('#streamOutput .sp-row')].map(e => e.textContent).join(' | ')")
            logs = {name: open(os.path.join(workdir, "logs", name + ".log"), encoding="utf-8", errors="replace").read() if os.path.exists(os.path.join(workdir, "logs", name + ".log")) else ""
                    for name in ("webapp", "executor")}
            went = re.findall(r"at step (\d+) from the state after step (\d+), (\d+) step\(s\) run again", logs["executor"])
            check("a chain asked from an earlier chain (0318): its cell finds what the first analysis made and nothing of the chain asked after it - the kernel went back to the state the earlier chain ended in, "
                  "the app says so, and the executor says it got there from that state's own snapshot with no step run again",
                  "PLOTS=" in row9 and "LATER=0" in row9 and "The kernel went back to the state chain" in logs["webapp"]
                  and (compute == "local" or (bool(went) and went[-1][0] == went[-1][1] and went[-1][2] == "0")), (row9[:200], went[-2:], compute))

            # ---- branches on the page (0320, docs/BRANCH_DESIGN.md §4, §5) ----
            # Go back to a turn of an analysis on its Analysis map, type a hint, and the analysis goes on from there another way. First
            # from the chain asked just before, whose state the thread's kernel holds: the kernel goes back, no cell is run again.
            # Then from the turn of the first analysis that pooled the soil types - a chain on a frame loaded earlier, so a fresh
            # kernel runs its kept cells again
            def runs_b():
                with open(os.path.join(wa, "storage", USER, "threads", f"{tid_b}.json"), encoding="utf-8") as fh:
                    return json.load(fh)["runs"]

            def logs_b():
                return {name: open(os.path.join(workdir, "logs", name + ".log"), encoding="utf-8", errors="replace").read() if os.path.exists(os.path.join(workdir, "logs", name + ".log")) else ""
                        for name in ("webapp", "executor")}

            def cells_of(run):
                return [t for t in run.get("turns", []) if t["kind"] == "cell" and t.get("cell_no") is not None and not t.get("step")]

            def entry_b():
                return page.evaluate("() => { const e = responses[currentResponseIndex] || {}; return { chain: e.chain_id, branch: e.branch || null, parent: e.parentChainId, q: e.queryText, n: responses.length }; }")

            tid_b = str(page.evaluate("() => currentData.thread_id"))
            thread_b = runs_b()
            first_b = min((r for r in thread_b.values() if r["question"] == mod.QUESTIONS[0] and not r.get("brief")), key=lambda r: r["created"])
            last_b = max((r for r in thread_b.values() if r["question"] == mod.BACK_QUESTION), key=lambda r: r["created"])
            n_b = entry_b()["n"]
            page.wait_for_timeout(800)                       # the answer's own buttons settle a moment after the run ends
            whole = left_pane(page)
            # the button's place (0321): the end of the ids' row, which stays under the strip - seen here in a pane too short for its analysis, at its end
            head = page.evaluate("""() => { const p = document.getElementById('streamOutput'), b = p.querySelector('.sp-turnmap'), row = p.querySelector('.sp-ids'), strip = p.querySelector('.sp-strip');
                const box = e => e.getBoundingClientRect();
                p.style.maxHeight = '240px'; p.scrollTop = p.scrollHeight;
                const out = { scrolled: p.scrollTop > 60, words: b.textContent, row: b.parentNode === row && row.lastElementChild === b, strip: !!strip.querySelector('.sp-turnmap'),
                              end: Math.abs(box(b).right - (box(row).right - parseFloat(getComputedStyle(row).paddingRight))) < 2, under: Math.abs(box(row).top - box(strip).bottom) < 2,
                              seen: box(b).top >= box(p).top && box(b).bottom <= box(p).bottom, line: box(row).height < 40 };
                p.style.maxHeight = ''; p.scrollTop = p.scrollHeight;
                return out; }""")
            map1 = open_turn_map(page)
            check("the Analysis map (0320; the button's place 0321): a finished analysis has its button at the end of the ids' row, with its name - none on the strip; the row is one line "
                  "and stays under the strip, so the button is in view with the pane at its end. It opens the Workflow map's drawer as the map of the analysis's turns - its name, how "
                  "many turns, the thread's own buttons out of it; a box to a turn, with its number and its cell under what it did; the last turn is the open box. Its head (0324): the Git "
                  "branch mark, the name, what is on the map, then zoom, full screen and the close on one line - none of them on the map; the foot says what a click and the pointer do",
                  head == {"scrolled": True, "words": "Analysis map", "row": True, "strip": False, "end": True, "under": True, "seen": True, "line": True}
                  and map1["title"] == "Analysis map" and map1["sub"] == f"{len(map1['boxes'])} turns" and len(map1["boxes"]) >= 2 and map1["buttons"] is False
                  and map1["head"] == map_head("branch") and map1["says"] == "Click a turn to go back to it. Hover over one to see what it did."
                  and re.fullmatch(r"Turn 1 · In \[\d+\]", map1["boxes"][0][1]) and map1["boxes"][-1][1] == f"Turn {len(map1['boxes'])} · report" and map1["on"] == [len(map1["boxes"])]
                  and map1["lit"] == list(range(1, len(map1["boxes"]) + 1)) and whole["badge"] == "", (head, map1, whole["badge"]))
            used = page.evaluate("""() => { const d = document.getElementById('workflowMapModal'), q = s => d.querySelector(s), level = () => parseInt(q('.wf-zoom-level').textContent, 10);
                const press = name => q('.map-drawer-tools button[aria-label="' + name + '"]').click(), wide = () => Math.round(q('.workflow-modal-content').getBoundingClientRect().width);
                const full = () => [q('.wf-fullscreen-btn').getAttribute('aria-label'), q('.wf-fullscreen-btn').title, wide() > innerWidth - 100];
                const out = { at: level(), side: wide() < 600 };
                press('Zoom in'); out.more = level(); press('Zoom out'); press('Zoom out'); out.less = level(); press('Fit to the frame'); out.fit = level();
                out.before = full(); press('Full screen'); out.over = full(); press('Leave full screen'); out.back = full();
                return out; }""")
            check("the head's buttons, used (0324): zoom in and zoom out move the level in the head by 15, and fit brings the map back to its frame; full screen lays the drawer over the page, and "
                  "the button then says the way back; pressed again, the drawer is at its side",
                  (used["more"], used["less"], used["fit"]) == (used["at"] + 15, used["at"] - 15, used["at"]) and used["side"] is True
                  and (used["before"], used["over"], used["back"]) == (["Full screen", "Full screen", False], ["Leave full screen", "Leave full screen", True], ["Full screen", "Full screen", False]), used)
            turn_box(page, "(sub) => sub.startsWith('Turn 1 ·')")
            page.wait_for_function("() => BranchUI.standing() !== null", timeout=10000)
            back1 = left_pane(page)
            shut1 = page.evaluate("() => getComputedStyle(document.getElementById('workflowMapModal')).display")
            check("going back to a turn (0320): a click on its box shuts the drawer and ends the left pane at the turn - the later cards and the closing card are out of sight - while the "
                  "tabs stay as they were; the composer asks for a hint, the row under it says from which turn and how many turns are left, and the files' menu, the mode and the "
                  "Architect's switch are out of sight; the arrows' count is as it was",
                  shut1 == "none" and back1["turns"] == [[1, False]] and back1["hidden"] == back1["cards"] - 1 >= 1 and back1["done"] is False and whole["done"] is True
                  and re.fullmatch(r"From turn 1 · \d+ turns left×", back1["chip"]) and back1["words"] == "Say how the analysis should go on from turn 1" and back1["controls"] == [False, False, False]
                  and whole["controls"] == [True, True, True] and back1["standing"] == {"chain": int(last_b["id"]), "turn": 1} and back1["tabs"] == whole["tabs"] and back1["position"] == whole["position"] == "chain 9 of 9",
                  (shut1, back1, whole))
            page.fill("#queryInput", mod.BRANCH_HINT)
            page.click("#submitQuery")
            wait_run_end(page, n_b + 1)
            pane_g, entry_g = left_pane(page), entry_b()
            run_g = thread_run(wa, USER, tid_b, str(entry_g["chain"])) or {}
            cells_g, logs_g = cells_of(run_g), logs_b()
            went_g = re.findall(r"at step (\d+) from the state after step (\d+), (\d+) step\(s\) run again", logs_g["executor"])
            check("a hint sent from a turn whose state the kernel holds (0320): the branch runs as a chain of its own - its pane has the kept turn first, marked, then the row of the "
                  "hint, then its own turns and its closing card; the composer is its own again. It is its analysis's: the arrows count no new chain, and its entry keeps the chain, "
                  "the turn and the hint. The kernel went back - the app says so, the executor says it got there from that state's own snapshot with no step run again - and "
                  "the branch's cell finds what the path made and nothing a later chain made",
                  pane_g["turns"][:2] == [[1, True], [2, False]] and pane_g["hints"] == ["From turn 1" + mod.BRANCH_HINT] and pane_g["done"] is True and pane_g["hidden"] == 0 and pane_g["chip"] == ""
                  and pane_g["controls"] == [True, True, True] and pane_g["standing"] is None and pane_g["position"] == "chain 9 of 9" and pane_g["badge"] == "1" and entry_g["n"] == n_b + 1
                  and entry_g["branch"] == {"of": int(last_b["id"]), "turn": 1, "hint": mod.BRANCH_HINT} and entry_g["q"] == mod.BACK_QUESTION and str(entry_g["parent"]) == str(last_b.get("parent"))
                  and run_g.get("branch") == {"of": last_b["id"], "turn": 1} and run_g.get("status") == "answered" and [c.get("kept") for c in cells_g] == ["kept", ""]
                  and "KEPT=1 LATER=0" in cells_g[-1]["stdout"] and f"The kernel went back to the state after turn 1 of chain {last_b['id']}" in logs_g["webapp"]
                  and (compute == "local" or (bool(went_g) and went_g[-1][0] == went_g[-1][1] and went_g[-1][2] == "0")),
                  (pane_g, entry_g, run_g.get("branch"), run_g.get("status"), [c.get("kept") for c in cells_g], went_g[-2:], compute))
            map2 = open_turn_map(page)
            tags2 = page.evaluate("() => [...document.querySelectorAll('#workflowMapModal .wf-node')].map(x => (x.querySelector('.wf-node-made') || {}).textContent || '')")
            n1 = len(map1["boxes"])
            check("the Analysis map of an analysis with a branch (0320): the two ways from turn 1 - the first run's turns, and the branch's own joined to the turn it went on from, the first "
                  "of them marked with its hint; the line under the name counts the branch; the branch's last turn is the open box and the way to it is lit, the way that was left faint",
                  map2["sub"] == f"{len(map2['boxes'])} turns · 1 branch" and len(map2["boxes"]) == n1 + len(pane_g["turns"]) - 1 and tags2 == [""] * n1 + ["hint"] + [""] * (len(map2["boxes"]) - n1 - 1)
                  and map2["boxes"][n1][1].startswith("Turn 2 · In [") and map2["on"] == [len(map2["boxes"])] and map2["lit"] == [1] + list(range(n1 + 1, len(map2["boxes"]) + 1)), (map2, tags2))
            turn_box(page, f"(sub) => sub === 'Turn {n1} · report'")
            page.wait_for_function("(c) => String(currentData.chain_id) === String(c)", arg=last_b["id"], timeout=10000)
            first_way = left_pane(page)
            check("moving between branches (0320): a click on the last turn of the way that was left brings that chain back, tabs and pane, whole; its Analysis map's button says the analysis has a branch",
                  first_way["turns"] == [[n, False] for n in range(1, n1 + 1)] and first_way["hidden"] == 0 and first_way["done"] is True and first_way["hints"] == [] and first_way["standing"] is None
                  and first_way["answer"] == whole["answer"] > 0 and pane_g["answer"] != whole["answer"] and first_way["position"] == "chain 9 of 9" and first_way["badge"] == "1"
                  and entry_b()["chain"] == int(last_b["id"]), (first_way, whole["answer"], pane_g["answer"]))

            # the first analysis, after the turn that pooled the soil types
            page.evaluate("(c) => navigateToChainId(c)", int(first_b["id"]))
            page.wait_for_function("(c) => String(currentData.chain_id) === String(c)", arg=first_b["id"], timeout=10000)
            at_first = left_pane(page)["position"]
            open_turn_map(page)
            turn_box(page, f"(sub) => sub.startsWith('Turn {mod.BRANCH_TURN} ·')")
            page.wait_for_function("() => BranchUI.standing() !== null", timeout=10000)
            back_b = left_pane(page)
            page.fill("#queryInput", mod.BRANCH_HINT)
            page.click("#submitQuery")
            wait_run_end(page, n_b + 2)
            pane_b, entry_b2 = left_pane(page), entry_b()
            run_b = thread_run(wa, USER, tid_b, str(entry_b2["chain"])) or {}
            cells_b, logs_2 = cells_of(run_b), logs_b()
            check("a branch of the first analysis, after the turn that pooled the soil types (0320): the pane ended at that turn while the hint was typed; the branch's pane has its "
                  "four kept turns first, marked, then the hint, then its own; a fresh kernel ran its kept cells again and they printed what they had, so none is marked; its "
                  "cell finds what they made, the function among it; the report follows the hint and its replay reproduces; the first analysis is as it was",
                  back_b["turns"] == [[n, False] for n in range(1, mod.BRANCH_TURN + 1)] and back_b["position"] == at_first
                  and pane_b["turns"] == [[n, True] for n in range(1, mod.BRANCH_TURN + 1)] + [[5, False], [6, False]] and pane_b["hints"] == [f"From turn {mod.BRANCH_TURN}" + mod.BRANCH_HINT]
                  and pane_b["position"] == at_first and entry_b2["branch"] == {"of": int(first_b["id"]), "turn": mod.BRANCH_TURN, "hint": mod.BRANCH_HINT} and entry_b2["q"] == mod.QUESTIONS[0]
                  and run_b.get("branch") == {"of": first_b["id"], "turn": mod.BRANCH_TURN} and run_b.get("hints") == [{"turn": mod.BRANCH_TURN, "text": mod.BRANCH_HINT}]
                  and run_b.get("parent") == first_b.get("parent") and run_b.get("status") == "answered" and run_b.get("replay_status") == "reproduced"
                  and [c.get("kept") for c in cells_b] == ["kept", "kept", ""] and "KEPT=1 LATER=0" in cells_b[-1]["stdout"] and "APART_LOAM=" in cells_b[-1]["stdout"]
                  and "## Each soil type on its own" in run_b.get("report", "") and (thread_run(wa, USER, tid_b, first_b["id"]) or {}).get("turns") == first_b["turns"]
                  and f"a branch of chain {first_b['id']} after turn {mod.BRANCH_TURN}" in logs_2["webapp"]
                  and f"A fresh kernel for the branch: the 0 cells before chain {first_b['id']} and the 2 it keeps of it are run again" in logs_2["webapp"],
                  (back_b, pane_b, entry_b2, run_b.get("branch"), run_b.get("status"), run_b.get("replay_status"), [c.get("stdout", "")[-60:] for c in cells_b[-1:]]))

            # the Workflow map and the arrows count analyses
            page.click("#railMapButton")
            page.wait_for_function("() => getComputedStyle(document.getElementById('workflowMapModal')).display !== 'none' && document.querySelector('#workflowMapModal h2').textContent === 'Workflow map'", timeout=10000)
            thread_map = page.evaluate("""() => { const d = document.getElementById('workflowMapModal'), boxes = [...d.querySelectorAll('.wf-node')];
                return { sub: document.getElementById('mapDrawerSub').textContent, boxes: boxes.length, branches: boxes.map(x => (x.querySelector('.wf-node-branches') || {}).textContent || '').filter(Boolean),
                         on: boxes.filter(x => x.classList.contains('wf-node--active')).map(x => x.querySelector('.wf-node-chain').textContent), cls: d.className,
                         buttons: getComputedStyle(d.querySelector('.map-drawer-foot')).display !== 'none' }; }""")
            thread_drawer = conversation_map(page)
            page.click("#railMapButton")
            page.click("#nextResponse")
            page.wait_for_timeout(500)
            stepped = left_pane(page)["position"]
            page.click("#prevResponse")
            page.wait_for_timeout(500)
            came_back = [left_pane(page)["position"], entry_b()["chain"]]
            check("the Workflow map and the arrows count analyses, not branches (0320): eleven chains in the thread, nine boxes - the two analyses that went on another way each saying "
                  "so -, the open box that of the analysis on screen, showing the branch; the arrows step to the next analysis and back to the branch that was on screen. The map's head "
                  "(0324) is the drawer's one head, with the rail's mark, and its foot says what a click and the pointer do",
                  thread_map["boxes"] == 9 and entry_b2["n"] == n_b + 2 == 11 and thread_map["sub"] == "9 chains · 2 branches" and thread_map["branches"] == ["1 branch", "1 branch"]
                  and thread_drawer["head"] == map_head("tree") and (thread_drawer["title"], thread_drawer["says"]) == ("Workflow map", "Click a chain to open it. Hover over one to see its question.")
                  and thread_map["on"] == [f"Chain: {entry_b2['chain']}"] and thread_map["buttons"] is True and "turns" not in thread_map["cls"]
                  and stepped != at_first and came_back == [at_first, entry_b2["chain"]], (thread_map, at_first, stepped, came_back))

            # a branch the server does not start: the request is changed on its way so that it names a turn the analysis never had
            open_turn_map(page)
            turn_box(page, "(sub, mark) => mark === 'hint'")
            page.wait_for_function("() => BranchUI.standing() !== null", timeout=10000)
            runs_were = len(runs_b())
            page.evaluate("""() => { const send = window.authService.fetch;
                window.authService.fetch = function (url, o) { if (url === '/query') { const b = JSON.parse(o.body); if (b.branch) { b.branch.turn = 99; o = Object.assign({}, o, { body: JSON.stringify(b) }); window.authService.fetch = send; } }
                                                               return send.call(window.authService, url, o); }; }""")
            page.fill("#queryInput", "this one is refused")
            page.click("#submitQuery")
            page.wait_for_function("() => !queryRunning && BranchUI.standing() !== null && document.getElementById('queryInput').value === 'this one is refused'", timeout=60000)
            page.wait_for_timeout(300)
            refused = left_pane(page)
            said_no = page.evaluate("() => document.getElementById('summaryContent').textContent")
            check("a branch the server does not start (0320): it says why - the person reads it - and nothing is kept of the request: no chain on the page or on the record; the chain the "
                  "hint was typed on is back at its turn, the hint in the composer to send again",
                  "Turn 99 cannot be gone on from" in said_no and entry_b()["n"] == n_b + 2 and len(runs_b()) == runs_were and entry_b()["chain"] == entry_b2["chain"]
                  and refused["standing"] == {"chain": entry_b2["chain"], "turn": 5} and refused["turns"] == pane_b["turns"][:5] and refused["chip"].startswith("From turn 5")
                  and refused["position"] == at_first, (said_no[-200:], refused, entry_b()))
            page.click("#branchChip button")
            page.fill("#queryInput", "")
            left_it = left_pane(page)
            sent_n = page.evaluate("""async (a) => { const r = await window.authService.fetch('/query', { method: 'POST', headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ query: a.hint, thread_id: a.thread, chain_id: a.chain, branch: { turn: null } }) }); return (await r.text()).split('\\n').filter(l => l.trim()).map(l => JSON.parse(l)); }""",
                                   {"hint": mod.BRANCH_HINT, "thread": int(tid_b), "chain": int(first_b["id"])})
            check("the cross on the composer's row leaves the turn: the pane is whole, the composer its own; and a request whose branch names no turn is refused by the server - what was "
                  "typed is not asked as a question, no chain is made",
                  left_it["standing"] is None and left_it["chip"] == "" and left_it["hidden"] == 0 and left_it["controls"] == [True, True, True]
                  and any(str(m.get("error", "")).startswith("Turn 0 cannot be gone on from: this analysis can go on from turns 1 to ") for m in sent_n)
                  and not any(m.get("type") == "id" for m in sent_n) and len(runs_b()) == runs_were, (left_it, [m for m in sent_n if m.get("error") or m.get("type") == "id"]))
            page.evaluate("(c) => navigateToChainId(c)", int(last_b["id"]))      # the chain the walk goes on from
            page.wait_for_function("(c) => String(currentData.chain_id) === String(c)", arg=last_b["id"], timeout=10000)

            # ---- the Usage dialog (docs/USAGE_DESIGN.md, step 3): what it shows against the rows the logger wrote ----
            rows = usage_rows(wa, edition, USER)
            by_chain = {}
            for r in rows:
                by_chain.setdefault(str(r["chain_id"]), []).append(r)
            exp = {"calls": len(rows), "chains": len(by_chain), "cost": sum(float(r["cost"] or 0) for r in rows), "tokens_in": sum(int(r["prompt_tokens"] or 0) for r in rows),
                   "tokens_out": sum(int(r["completion_tokens"] or 0) for r in rows), "time": sum(float(r["elapsed_time"] or 0) for r in rows)}
            seat_cost = {}
            for r in rows:
                seat_cost[r["agent"]] = seat_cost.get(r["agent"], 0.0) + float(r["cost"] or 0)
            run_ids = [r["id"] for r in runs]
            check("usage rows: the logger wrote one per model call - every run's chain among them and the Promoter's billing chain, the cache fields recorded (zeros when nothing was cached, never NULL)",
                  all(rid in by_chain for rid in run_ids) and any(r["agent"] == "Promoter" for r in rows) and exp["calls"] > 20
                  and all(r.get("cached_tokens") is not None and r.get("cache_savings") is not None for r in rows), (exp, sorted(by_chain)[:3], [r["agent"] for r in rows][:5]))
            page.hover(".settings-button"); page.wait_for_timeout(300)
            page.click(".usage-option")
            page.wait_for_selector("#usageModal .us-tile", timeout=20000)
            data = page.evaluate("() => UsageUI.state.data")
            tot = data["totals"]
            check("Usage opens from the gear menu; its answer agrees with the rows: calls, chains, cost, tokens in and out, model time; every call recorded the cache; the hosted edition's tier in the header",
                  tot["calls"] == exp["calls"] and tot["chains"] == exp["chains"] and abs(tot["cost"] - exp["cost"]) < 1e-6 and tot["tokens_in"] == exp["tokens_in"] and tot["tokens_out"] == exp["tokens_out"]
                  and abs(tot["time"] - exp["time"]) < 1e-3 and tot["recorded_calls"] == exp["calls"] and data["period"]["edition"] == ("hosted" if edition == "hosted" else "self-hosted")
                  and (data["period"]["tier"] == "free" if edition == "hosted" else data["period"]["tier"] == "local"), (tot, exp, data["period"]))
            ui = page.evaluate("""() => { const m = document.getElementById('usageModal');
                return { sub: m.querySelector('[data-sub]').textContent, tiles: [...m.querySelectorAll('.us-tile')].map(t => [t.querySelector('.l').textContent, t.querySelector('.v').textContent.trim()]),
                         cols: m.querySelectorAll('.us-chart rect.col').length,
                         filled: new Set([...m.querySelectorAll('.us-chart rect'), ...m.querySelectorAll('.us-chart path')].filter(e => (e.getAttribute('class') || '').startsWith('us-s')).map(e => e.getAttribute('x') || e.getAttribute('d').slice(1).split(',')[0])).size,
                         legend: [...m.querySelectorAll('.us-legend .r[data-series]')].map(r => [r.querySelector('.n').textContent, r.querySelector('.v').textContent]),
                         total: m.querySelector('.us-legend .r.sum .v').textContent, standout: [...m.querySelectorAll('.us-kv b')].map(b => b.textContent) }; }""")
            # the page rounds dollars from the shortest decimal (0.015 -> $0.02), Python from the binary value ($0.01): compare to half a cent
            close = lambda text, value: abs(float(str(text).lstrip("$").replace(",", "")) - value) < 0.0051
            top_seats = sorted(seat_cost, key=lambda k: -seat_cost[k])
            exp_legend = top_seats if len(top_seats) <= 7 else top_seats[:6] + ["Other"]
            # the days filled are the days the route counted calls on: today's alone, or yesterday's too when the walk ran past midnight
            # (2026-11-11: a walk started at 23:58 UTC filled two columns and failed a check that expected one)
            days_with_calls = sum(1 for d_ in data["days"] if d_.get("calls"))
            check("the Overview: the tiles say the rows' figures (model cost, analyses, model calls; Compute on the hosted edition only, free: nothing charged); the chart has a column per day of the window and the days with calls are the ones filled (today's, and yesterday's when the walk ran past midnight); the legend ranks the seats by cost with the rows' totals; three lines stand out",
                  ui["tiles"][0][0] == "Model cost" and close(ui["tiles"][0][1], exp["cost"]) and ui["tiles"][1] == ["Analyses", str(exp["chains"])] and ui["tiles"][2] == ["Model calls", format(exp["calls"], ",")]
                  and (ui["tiles"][6][0] == "Compute" and ui["tiles"][6][1] == "$0.00" if edition == "hosted" else len(ui["tiles"]) == 6)
                  and ui["cols"] == data["period"]["buckets"] == 30 and ui["filled"] == days_with_calls and 1 <= days_with_calls <= 2 and [n for n, v in ui["legend"]] == exp_legend and close(ui["legend"][0][1], seat_cost[top_seats[0]])
                  and close(ui["total"], exp["cost"]) and ui["sub"].endswith("hosted, Free compute" if edition == "hosted" else "the self-hosted edition") and ui["standout"] == [data["days"][-1]["label"], "Cache", "Failures"], ui)
            page.click("#usageModal .us-tabs [data-tab=analyses]")
            page.wait_for_selector("#usageModal .us-list .it", timeout=10000)
            led = page.evaluate("""() => [...document.querySelectorAll('#usageModal .us-list .it')].map(it => ({ chain: it.getAttribute('data-chain'), q: it.querySelector('.q').textContent, cost: it.querySelector('.c').textContent,
                                           outcome: (it.querySelector('.rt-status') || {}).textContent || '', meta: it.querySelector('.m').textContent }))""")
            led_by = {e["chain"]: e for e in led}
            saved_chains = {os.path.basename(f)[:-5] for f in favs}
            check("the Analyses ledger: every chain of the rows once, newest first; each run under its own question with its outcome (reproduced where it had cells, answered where not) and its cost from its rows; the Promoter's chain named Save as routine",
                  len(led) == exp["chains"] and set(led_by) == set(by_chain) and all(led_by[r["id"]]["q"] == r["question"] for r in runs)
                  and all(led_by[r["id"]]["outcome"] == ("reproduced" if any(t_["kind"] == "cell" for t_ in r["turns"]) else "answered") for r in runs)
                  and all(close(led_by[r["id"]]["cost"], sum(float(x["cost"] or 0) for x in by_chain[r["id"]])) for r in runs)
                  and any(e["q"] == "Save as routine: the proposal" for e in led) and [e["chain"] for e in led] == sorted(led_by, key=lambda c: min(str(x["timestamp"]) for x in by_chain[c]), reverse=True),
                  (len(led), exp["chains"], [(e["chain"], e["q"][:40], e["outcome"], e["cost"]) for e in led][:4], [(r["id"], r["question"][:40]) for r in runs][:4]))
            first = runs[0]["id"]
            page.click(f"#usageModal .us-list .it[data-chain='{first}']")
            page.wait_for_selector("#usageModal .us-detail-h", timeout=10000)
            det = page.evaluate("() => UsageUI.state.detail")
            pane = page.evaluate("""() => { const d = document.querySelector('#usageModal .us-detail'); return { q: d.querySelector('.us-detail-h .q').textContent, open: !!d.querySelector('.open'), notsaved: !!d.querySelector('.us-detail-h .muted'),
                                   marks: d.querySelectorAll('.us-tl rect.call').length, ranks: [...d.querySelectorAll('.us-rank .r .n')].map(x => x.textContent.split(' ·')[0]), models: d.querySelectorAll('.us-kv.models b').length }; }""")
            chain_rows = by_chain[first]
            chain_seats = sorted({r["agent"] for r in chain_rows}, key=lambda a: -sum(float(r["cost"] or 0) for r in chain_rows if r["agent"] == a))
            check("the first run's detail: its calls one for one with its rows, in time; the seats ranked by cost as the rows have them; a mark per call on the timeline; its models; 'open the analysis' since it is saved as a favourite",
                  det["analysis"]["chain"] == first and len(det["calls"]) == len(chain_rows) and abs(det["totals"]["cost"] - sum(float(r["cost"] or 0) for r in chain_rows)) < 1e-6
                  and [s["seat"] for s in det["seats"]] == chain_seats and pane["marks"] == len(chain_rows) and pane["ranks"] == chain_seats and pane["q"] == runs[0]["question"]
                  and det["analysis"]["mode"] == "Deep" and det["analysis"]["cells"] == sum(1 for t_ in runs[0]["turns"] if t_["kind"] == "cell" and t_.get("cell_no")) and det["analysis"]["saved"] is True and pane["open"] and not pane["notsaved"]
                  and (first in saved_chains), (pane, [s["seat"] for s in det["seats"]], chain_seats, len(det["calls"]), len(chain_rows)))
            unsaved = next((r["id"] for r in runs if r["id"] not in saved_chains), None)
            if unsaved:
                page.click(f"#usageModal .us-list .it[data-chain='{unsaved}']")
                page.wait_for_function("(c) => UsageUI.state.detail && UsageUI.state.detail.analysis.chain === c", arg=unsaved, timeout=10000)
                pane2 = page.evaluate("() => { const d = document.querySelector('#usageModal .us-detail'); return { open: !!d.querySelector('.open'), notsaved: (d.querySelector('.us-detail-h .muted') || {}).textContent || '' }; }")
                check("a run not saved as a favourite: no 'open the analysis' (the page opens a chain from its saved file), 'not saved' in its place", not pane2["open"] and pane2["notsaved"] == "· not saved", pane2)
            # a branch in the ledger (0321, docs/BRANCH_DESIGN.md §2, decision 14): the branch of the first analysis made above
            branch_c = str(entry_b2["chain"])
            page.click(f"#usageModal .us-list .it[data-chain='{branch_c}']")
            page.wait_for_function("(c) => UsageUI.state.detail && UsageUI.state.detail.analysis.chain === c", arg=branch_c, timeout=10000)
            det_b = page.evaluate("() => { const d = document.querySelector('#usageModal .us-detail'); return { analysis: UsageUI.state.detail.analysis, q: d.querySelector('.us-detail-h .q').textContent, "
                                  "hint: (d.querySelector('.us-detail-h .hint') || {}).textContent || '' }; }")
            own_cells = sum(1 for t_ in run_b["turns"] if t_["kind"] == "cell" and t_.get("cell_no") and not t_.get("kept"))
            check("a branch in the Usage dialog (0321): its row carries its analysis's question and says from which turn it went on; its cells are its own - not the two it kept - and "
                  "its cost is that of its own calls; the detail shows the hint under the question; a run that is no branch says neither",
                  led_by[branch_c]["q"] == mod.QUESTIONS[0] and f" · from turn {mod.BRANCH_TURN} · " in led_by[branch_c]["meta"] and "from turn" not in led_by[first]["meta"]
                  and det_b["analysis"]["branch"] == {"turn": mod.BRANCH_TURN, "hint": mod.BRANCH_HINT} and det_b["hint"] == f"From turn {mod.BRANCH_TURN}" + mod.BRANCH_HINT and det_b["q"] == mod.QUESTIONS[0]
                  and det_b["analysis"]["cells"] == own_cells == sum(1 for t_ in run_b["turns"] if t_["kind"] == "cell" and t_.get("cell_no")) - 2
                  and f" · {own_cells} cell" in led_by[branch_c]["meta"] and close(led_by[branch_c]["cost"], sum(float(x["cost"] or 0) for x in by_chain[branch_c]))
                  and det["analysis"]["branch"] == {}, (led_by[branch_c], det_b, own_cells))
            page.click("#usageModal .us-tabs [data-tab=calls]")
            page.wait_for_selector("#usageModal [data-table=calls] tbody tr", timeout=10000)
            calls_ui = page.evaluate("() => ({ n: document.querySelectorAll('#usageModal [data-table=calls] tbody tr').length, first: document.querySelector('#usageModal [data-table=calls] tbody tr td.link a').textContent, pager: document.querySelector('#usageModal .us-pager span').textContent, header_sticky: getComputedStyle(document.querySelector('#usageModal .us-scroll thead th')).position })")
            newest = max(rows, key=lambda r: (str(r["timestamp"]), int(r["id"])))
            csv = page.evaluate("async () => { const r = await window.authService.fetch('/usage/export.csv?period=30d&tz=' + (-new Date().getTimezoneOffset())); const t = await r.text(); return [r.status, r.headers.get('Content-Disposition'), t.split('\\n').filter(Boolean).length]; }")
            check("the Calls tab: the rows a hundred a page, newest first, under a frozen header; Export CSV answers an attachment with one line per row",
                  calls_ui["n"] == min(100, exp["calls"]) and calls_ui["first"] == str(newest["chain_id"]) and calls_ui["pager"].startswith("rows 1 – ") and calls_ui["header_sticky"] == "sticky"
                  and csv[0] == 200 and "attachment; filename=\"usage_30d_" in (csv[1] or "") and csv[2] == exp["calls"] + 1, (calls_ui, csv))
            page.click("#usageModal .us-tabs [data-tab=analyses]")
            page.click(f"#usageModal .us-list .it[data-chain='{first}']")
            page.wait_for_selector("#usageModal .us-detail-h .open", timeout=10000)
            page.click("#usageModal .us-detail-h .open")
            page.wait_for_function("() => document.getElementById('usageModal').style.display === 'none' && String(currentData.thread_id) === %r" % str(nb["thread_id"]), timeout=15000)
            page.wait_for_timeout(500)
            check("'open the analysis' closes the dialog and loads the saved thread at that chain", "chain 1 of" in page.inner_text("#chainPosition"), page.inner_text("#chainPosition"))

            # the thread's documents go with the thread (D35)
            tid = str(page.evaluate("() => currentData.thread_id"))
            docs_dir = os.path.join(wa, "storage", USER, "documents", tid)
            had_docs = os.path.isdir(docs_dir) and os.path.exists(os.path.join(docs_dir, "manifest.json"))
            # memory (2.8): first one chain is removed from the saved workflow - the one a saved follow-up was built on - then the workflow
            kept_file = os.path.join(store_dir, "memory", "view.json")

            def kept_follows(left):                                 # the kept file, once `left` holds of it: it follows behind the request
                t_k = time.time()
                while not left(json.load(open(kept_file))["threads"]) and time.time() - t_k < 15:
                    time.sleep(0.2)
                return left(json.load(open(kept_file))["threads"])
            mine = {r["id"] for r in kept_memory(store_dir)["runs"] if r["thread"] == tid}
            base = next((p for r in kept_memory(store_dir)["runs"] if r["thread"] == tid for p in r["path"] if p in mine), "/")
            status = page.evaluate("(c) => window.authService.fetch('/delete_chain/' + c, { method: 'DELETE' }).then(r => r.status)", base)
            less = kept_memory(store_dir)                           # not waited for: the chain has left with its file
            check("a chain removed from a saved workflow leaves memory at once (2.8): it is no run, and stays as the earlier step of the saved run built on it - its question and "
                  "cells, not its report; the kept view follows behind the request",
                  status == 200 and base in mine and base not in {r["id"] for r in less["runs"]} and sorted(less["steps"].get(base, {})) == ["cells", "question"]
                  and kept_follows(lambda threads: base.split("/")[1] not in threads[tid]["sig"]["saved"]), (status, base, sorted(mine), sorted(less["steps"])))
            remembered = [r["id"] for r in less["runs"] if r["thread"] == tid]
            status = page.evaluate("(t) => window.authService.fetch('/delete_thread/' + t, { method: 'DELETE' }).then(r => r.status)", tid)   # as the page does: its auth header rides along
            check("the thread's documents folder existed with its manifest, and deleting the thread removed it",
                  had_docs and status == 200 and not os.path.exists(docs_dir), (had_docs, status, os.path.exists(docs_dir)))
            forgotten = [r["id"] for r in kept_memory(store_dir)["runs"] if r["thread"] == tid]              # not waited for either
            check("a saved workflow that is deleted leaves memory at once (2.8), and the kept view follows behind the request",
                  remembered and forgotten == [] and kept_follows(lambda threads: tid not in threads), (remembered, forgotten))

            # a routine without data (2026-11-14, docs/ROUTINES_DESIGN.md §24), last and in a workflow of its own: New workflow leaves
            # nothing loaded; a question that needs no data is answered from the values in its cell; Save as routine checks it like any
            # chain - no warning of data that is gone - with those values as its inputs (the stand-in promoter gives them only under the
            # brief for such a chain); the Run dialog asks for no data; the runs' table says the input the runs differ in
            page.evaluate("handleNewConversation()")
            page.wait_for_url("**/?new=true", timeout=60000)
            page.wait_for_selector("#queryInput", state="visible", timeout=60000)
            page.app_ready()
            page.wait_for_function("() => /Ready|Local|Docker/.test(document.querySelector('#containerStatusText').textContent)", timeout=60000)
            page.fill("#queryInput", mod.ALONE_QUESTION)
            page.click("#submitQuery")
            wait_run_end(page, 1)
            alone_run = page.evaluate("() => ({ pills: document.querySelectorAll('.primary-dataset-pill').length, done: document.querySelector('.sp-done').textContent, cells: document.querySelectorAll('.sp-row.cell, .sp-row.ok').length })")
            check("a new workflow has no dataset, and a question that needs none is answered from the values in its cell: the replay reproduces the number",
                  alone_run["pills"] == 0 and "Replay reproduced" in alone_run["done"], alone_run)
            page.hover("#saveButton")
            page.wait_for_selector("#saveMenu", state="visible", timeout=10000)
            page.click("#saveMenu .it[data-act='routine']")
            page.wait_for_selector("#routineMakeModal .rt-inputs", timeout=120000)
            mk = page.evaluate("""() => { const m = document.getElementById('routineMakeModal'); return { chip: m.querySelector('.rt-data .ui-chip .t').textContent, warn: !!m.querySelector('.rt-line.warn'),
                lines: [...m.querySelectorAll('.rt-line')].map(e => e.textContent).join(' | '), note: m.querySelector('.ui-dlg-f .note').textContent, name: m.querySelector('[data-field="name"]').value,
                inputs: [...m.querySelectorAll('.rt-inputs tbody tr')].map(r => [r.dataset.key, r.querySelector('.val').textContent]), results: [...m.querySelectorAll('.rt-results .r .l')].map(e => e.textContent) }; }""")
            check("Save as routine on it: the dialog says No data and that the routine runs without one - no warning of data that is gone, nothing about this chain's own data - with the chain's line, and the "
                  "starting value and the steps as its inputs (given only under the promoter's brief for a chain that read no data)",
                  mk["chip"] == "No data" and "This chain used no dataset, so the routine runs without one." in mk["lines"] and not mk["warn"] and "own data" not in mk["lines"] + mk["note"] and "no longer loaded" not in mk["lines"]
                  and mk["note"].startswith("The routine is checked once before it is created;") and mk["name"] == "What is left after the steps" and mk["inputs"] == [["start", "100"], ["steps", "40"]]
                  and mk["results"] == ["left after the steps"], mk)
            page.click("#routineMakeModal [data-act='create']")
            page.wait_for_function("() => document.querySelector('#routineMakeModal').style.display === 'none' || !!document.querySelector('#routineMakeModal .rt-error')", timeout=180000)

            def _alone_routine():
                for p_ in glob.glob(os.path.join(workdir, "webapp", "storage", USER, "routines", "*", "routine.json")):
                    r_ = json.load(open(p_, encoding="utf-8"))
                    if r_.get("name") == "What is left after the steps":
                        return r_
                return {}
            t_end = time.time() + 120
            while time.time() < t_end and (((_alone_routine().get("versions") or [{}])[-1].get("run_zero") or {}).get("status") or "verifying") == "verifying":
                page.wait_for_timeout(500)
            ar = _alone_routine()
            av = (ar.get("versions") or [{}])[-1]
            arz, amf = av.get("run_zero") or {}, av.get("manifest") or {}
            check("the routine is created and verified with nothing loaded: run zero reproduced the chain's line, the record of its data says none, the two inputs are stored",
                  arz.get("status") == "reproduced" and arz.get("verified") is True and (amf.get("data") or {}).get("source") == "none" and not (amf.get("data") or {}).get("df_id")
                  and [p_["key"] for p_ in amf.get("parameters") or []] == ["start", "steps"], (arz.get("status"), arz.get("line"), amf.get("data")))
            page.click("#routinesPill")
            page.wait_for_selector("#routinesModal", state="visible", timeout=10000)
            page.wait_for_selector(f"#routinesModal .rt-side .it[data-id='{ar.get('id')}']", timeout=15000)
            page.click(f"#routinesModal .rt-side .it[data-id='{ar.get('id')}']")
            page.wait_for_function("() => (document.querySelector('#routinesModal .rt-right .title') || {}).textContent === 'What is left after the steps'", timeout=15000)
            page.click("#routinesModal [data-act='run']")
            page.wait_for_selector("#routineRunModal .rt-row[data-row='data']", timeout=30000)
            ard = page.evaluate("""() => { const m = document.getElementById('routineRunModal'); return { rows: [...m.querySelectorAll('.rt-row')].map(r => r.dataset.row), data: m.querySelector('.rt-row[data-row="data"]').textContent,
                choices: m.querySelectorAll('input[name="rt-data"]').length, file: !!m.querySelector('input[type="file"]'), fit: (m.querySelector('.rt-fit') || {}).textContent || null,
                start: m.querySelector('[data-key="start"]').value, steps: m.querySelector('[data-key="steps"]').value, runOn: !m.querySelector('[data-act="run"]').disabled }; }""")
            check("its Run dialog asks for no data: the Data row reads 'none needed' - no choice, no file to pick, no line about what is loaded - then the two inputs with the values the analysis used, and Run is on",
                  ard["rows"] == ["data", "inputs"] and ard["data"] == "Datanone needed" and ard["choices"] == 0 and not ard["file"] and ard["fit"] is None
                  and float(ard["start"]) == 100.0 and float(ard["steps"]) == 40.0 and ard["runOn"], ard)
            page.fill("#routineRunModal [data-key='start']", "200")
            page.click("#routineRunModal [data-act='run']")
            wait_position(page, "2 of 2", 180000)
            page.wait_for_timeout(600)
            arv = page.evaluate("""() => ({ rows: [...document.querySelectorAll('.sp-row.tool')].map(e => e.textContent), done: (document.querySelector('.sp-done') || {}).textContent || '',
                active: (document.querySelector('#contentOutput .tab-content.active') || {}).id, cmp: (document.getElementById('content-comparison') || {}).textContent || '', data: (document.getElementById('content-dataframe') || {}).textContent || '' })""")
            check("the run from another starting value: RUN and COMPARE rows and no CHECK row - there is no data to check; the closing card says the line changed against run 0; the Comparison tab is open, "
                  "and the Data tab says what the run ran on: no data, and the two inputs it was made with",
                  not any("CHECK" in r for r in arv["rows"]) and any("RUN" in r and "run 1" in r for r in arv["rows"]) and any("COMPARE" in r and "run 0" in r for r in arv["rows"])
                  and "Run 1 complete" in arv["done"] and "1 of 1 changed" in arv["done"] and arv["active"] == "content-comparison" and "against run 0" in arv["cmp"]
                  and arv["data"].startswith("What this run ran onSourceNo data") and "Starting value 200" in arv["data"] and "Steps 40" in arv["data"] and "Columns" not in arv["data"], arv)
            page.click("#routinesPill")
            page.wait_for_selector("#routinesModal", state="visible", timeout=10000)
            page.wait_for_function("() => document.querySelectorAll('#routinesModal .rt-runs thead th[data-run]').length >= 2", timeout=15000)
            atab = page.evaluate("""() => ({ heads: [...document.querySelectorAll('#routinesModal .rt-runs thead th[data-run]')].map(e => e.dataset.run), sub: document.querySelector('#routinesModal .rt-right .sub').textContent,
                ins: [...document.querySelectorAll('#routinesModal .rt-runs tbody tr.in')].map(tr => [...tr.querySelectorAll('td.label, td.num')].map(td => td.textContent.trim())),
                vals: [...document.querySelectorAll('#routinesModal .rt-runs tbody tr:not(.in) td.num')].map(td => td.textContent.trim()) })""")
            check("the manager: the header says No data; the runs' table has run 0 and run 1 and, above the result, one row for the input the two runs differ in - the starting value, 100 and 200; "
                  "the steps, the same in both, have none",
                  atab["heads"] == ["0", "1"] and atab["sub"].startswith("No data · v1") and atab["ins"] == [["Starting value input", "100", "200"]]
                  and len(atab["vals"]) == 2 and atab["vals"][0] != atab["vals"][1], atab)
            page.evaluate("RoutinesUI.closeManager()")
            errs = errs + page.evaluate("window.__stackErrors || []")

            # the Architect (2026-11-15, docs/ARCHITECT_DESIGN.md §2.11), last and in a workflow of its own
            framed = walk_architect(page, st, mod, wa, edition, USER)
            errs = errs + page.evaluate("window.__stackErrors || []")

            # the saved analyses in the Architect (2026-11-16, docs/ARCHITECT_DESIGN.md §3.7): the analysis it framed is saved,
            # and a question it bears on is framed in a workflow of its own
            walk_saved(page, st, mod, wa, edition, USER, *framed)
            errs = errs + page.evaluate("window.__stackErrors || []")

            # the Architect as a tutor (2026-11-17): the question worked out in the conversation, with nothing loaded
            walk_tutor(page, mod, wa, edition, USER)
            errs = errs + page.evaluate("window.__stackErrors || []")

            # the figures and their draft (2026-11-18, docs/ARCHITECT_DESIGN.md §2.19, §2.20): on data, in a workflow of its own
            walk_draft(page, st, mod, wa, edition, USER)
            errs = errs + page.evaluate("window.__stackErrors || []")
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
