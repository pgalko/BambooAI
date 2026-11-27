"""Asking about a selection, in a real Chromium on the real page (2026-11-27, the product owner's pick of three
mockups; web_app/static/js/selection.js). Text selected in the content pane gets a small bar beside it - Ask, Copy -
which takes no focus, so the selection stays and copies as on any page. Ask puts the selection on the query box as a
quote; the question typed there is sent with the passage under it.

Before, a query popup opened at every mouse-up and took the cursor, which dropped the selection: nothing could be
copied out of a tab, and the popup lay on the text.

    python3 tests/e2e/test_selection.py        # about a minute; skips (exit 0) when playwright is not installed
    SHOTS=/tmp/shots python3 tests/e2e/test_selection.py      # and the bar and the quote as pictures

The page whole - the template with every stylesheet and script, started by the app's own continueAppInitialization() -
with the backend answered here (tools/render_page.py's way); the content is an invented field trial.
"""
import importlib.util
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
try:
    from playwright.sync_api import sync_playwright
except Exception:                                          # noqa: BLE001
    print("playwright not installed: the selection suite is skipped")
    sys.exit(0)

results = []


def check(name, cond, detail=""):
    results.append((name, bool(cond)))
    print(("  ok   " if cond else "  FAIL ") + name + ("" if cond else f"  <- {str(detail)[:600]}"))


spec = importlib.util.spec_from_file_location("render_page", os.path.join(ROOT, "tools", "render_page.py"))
render_page = importlib.util.module_from_spec(spec)
spec.loader.exec_module(render_page)
PAGE = render_page.static_index()
SHOTS = os.environ.get("SHOTS")

PHRASE = "on sand the two cannot be told apart"
QUESTION = "Why can they not be told apart?"
PLOTS = "".join(f"<p>Plot {i}: regime {'ABC'[i % 3]} on {('loam', 'clay', 'sand')[i % 3]}, yield {5 + i % 7 / 10:.1f} t/ha, watered every {2 + i % 3} days "
                "through the season, with the flooded plots kept and flagged.</p>" for i in range(1, 41))
ANSWER = ("<h1>Yield under the three watering regimes</h1><p>Regime B gave the highest yield in this trial. Its lead over regime A is clear on loam and on clay; "
          f"{PHRASE}.</p><p>A note on the trial: <input id=\"note\" value=\"regime B on loam\"></p>{PLOTS}")
OUTPUT = "<pre><code>regime B +0.42 t/ha over A  CI [0.18, 0.66]  n=96\nregime C -0.09 t/ha over A  CI [-0.33, 0.15]  n=96</code></pre>"


def route(r):
    url = r.request.url
    if url.startswith("http://app.local/static/"):
        path = os.path.join(ROOT, "web_app", "static", url.split("/static/", 1)[1].split("?")[0])
        if not os.path.exists(path):
            return r.fulfill(status=404, body="")
        kind = {".css": "text/css", ".js": "application/javascript", ".svg": "image/svg+xml", ".png": "image/png"}.get(os.path.splitext(path)[1], "application/octet-stream")
        return r.fulfill(status=200, content_type=kind, body=open(path, "rb").read())
    if url in ("http://app.local/", "http://app.local/index.html"):
        return r.fulfill(status=200, content_type="text/html", body=PAGE)
    if url.startswith("http://app.local/"):
        return r.fulfill(status=200, content_type="application/json", body="{}")
    for library in ("marked", "dagre"):                    # the two libraries the tools keep a stand-in for; the rest are offline
        if library in url:
            return r.fulfill(status=200, content_type="application/javascript", body=open(os.path.join(ROOT, "tools", "fixtures", library + "_stub.js"), "rb").read())
    return r.abort()


# what the suite reads off the page: the bar, the selection, the quote, where the focus is
HELPERS = """
window.T = {
  lines(phrase) {      // the boxes of a phrase's lines, in a tab that is on screen
    const walker = document.createTreeWalker(document.getElementById('contentOutput'), NodeFilter.SHOW_TEXT); let node;
    while ((node = walker.nextNode())) { const i = node.textContent.indexOf(phrase);
      if (i >= 0 && node.parentElement.getClientRects().length) { const r = document.createRange(); r.setStart(node, i); r.setEnd(node, i + phrase.length);
        return [...r.getClientRects()].map(b => ({ x: b.x, y: b.y, w: b.width, h: b.height })); } }
    return null; },
  state() {
    const bar = document.querySelector('.selection-bar'), b = bar.getBoundingClientRect(), s = window.getSelection(), quote = document.getElementById('queryQuote');
    const box = s.rangeCount ? s.getRangeAt(0).getBoundingClientRect() : null, ask = bar.querySelector('.ask'), copy = bar.querySelector('.copy');
    const mid = e => { const r = e.getBoundingClientRect(); return [r.x + r.width / 2, r.y + r.height / 2]; };
    return { on: getComputedStyle(bar).display !== 'none', bar: { x: b.x, y: b.y, w: b.width, h: b.height }, words: [ask.textContent, copy.textContent], ask: mid(ask), copy: mid(copy),
             selected: s.toString(), box: box && { x: box.x, y: box.y, w: box.width, h: box.height }, focus: document.activeElement.id || document.activeElement.nodeName,
             quote: { on: getComputedStyle(quote).display !== 'none', words: quote.querySelector('.t').textContent, whole: quote.querySelector('.t').title, remove: mid(quote.querySelector('button')),
                      clipped: quote.querySelector('.t').scrollWidth > quote.querySelector('.t').clientWidth, height: quote.getBoundingClientRect().height },
             box_text: document.getElementById('queryInput').value, folded: document.getElementById('leftPanel').classList.contains('collapsed') }; },
  scroller() {         // what scrolls the tab on screen
    let e = document.querySelector('#contentOutput .tab-content.active') || document.getElementById('contentOutput');
    while (e && !(e.scrollHeight > e.clientHeight + 4 && /auto|scroll/.test(getComputedStyle(e).overflowY))) e = e.parentElement;
    return e; },
};
window.__copies = []; window.__shown = 0;      // what was copied, how often the bar came on
new MutationObserver(() => { if (document.querySelector('.selection-bar').classList.contains('on')) window.__shown += 1; }).observe(document.querySelector('.selection-bar'), { attributes: true, attributeFilter: ['class'] });
document.addEventListener('copy', e => window.__copies.push({ at: e.target.id || e.target.nodeName, selected: window.getSelection().toString() }), true);
"""
# the server, as the page sees it: every call is kept and none is answered, so nothing arrives later to draw the page again
# under the test (the executor's status check, answered, clears the tabs and opens the Data tab)
SERVER = """window.__sent = [];
window.authService = Object.assign(window.authService || {}, { fetch: (url, opts) => { window.__sent.push([url, opts && opts.body ? JSON.parse(opts.body) : null]); return new Promise(() => {}); } });"""
FILL = """([answer, output]) => {
  createOrUpdateTab('answer', 'x'); createOrUpdateTab('code', 'print(1)'); createOrUpdateTab('plot', []); createOrUpdateTab('code_exec_results', 'x');
  document.getElementById('content-answer').innerHTML = '<div class="markdown-content content-body">' + answer + '</div>';
  document.getElementById('content-code_exec_results').innerHTML = output;
  document.getElementById('content-plot').innerHTML = '<p>Yield by regime, for each soil type</p>';
  document.getElementById('streamOutput').innerHTML = '<div style="height: 3000px">the analysis, turn by turn</div>';
  activateTab('answer'); }"""


class Page:
    """The app's page, started and filled; the mouse as a person moves it."""

    def __init__(self, browser):
        self.errors = []
        self.page = browser.new_page(viewport={"width": 1440, "height": 900})
        self.page.on("pageerror", lambda e: self.errors.append(str(e)))
        self.page.add_init_script("window.hljs = window.hljs || { highlightBlock() {}, highlightElement() {}, highlightAll() {}, configure() {} };")
        self.page.route("**/*", route)
        self.page.goto("http://app.local/")
        self.page.wait_for_timeout(600)
        self.page.evaluate(SERVER)
        self.page.evaluate("window.handleNewConversation = function () {}; initializeUIControls(); if (window.WorkspaceGate) { WorkspaceGate.release(); WorkspaceGate.hide(); }")
        self.page.evaluate("continueAppInitialization()")                     # the app's own start: it starts the module
        self.page.wait_for_timeout(400)
        self.page.evaluate(HELPERS)
        self.page.evaluate(FILL, [ANSWER, OUTPUT])
        self.page.wait_for_timeout(300)
        self.offline = len(self.errors)                    # the libraries that are not reached here have said so by now

    def state(self):
        return self.page.evaluate("T.state()")

    def lines(self, phrase):
        return self.page.evaluate("p => T.lines(p)", phrase)

    def drag(self, start, end):
        self.page.mouse.move(*start)
        self.page.mouse.down()
        self.page.mouse.move(*end, steps=6)
        self.page.mouse.up()
        self.page.wait_for_timeout(120)
        return self.state()

    def select(self, phrase=PHRASE):
        """The phrase, selected with the mouse from its first letter to its last."""
        lines = self.lines(phrase)
        first, last = lines[0], lines[-1]
        return self.drag((first["x"] + 1, first["y"] + first["h"] / 2), (last["x"] + last["w"] - 1, last["y"] + last["h"] / 2))

    def click(self, point):
        self.page.mouse.click(*point)
        self.page.wait_for_timeout(150)
        return self.state()

    def elsewhere(self):
        """A press on the empty part of the tab strip, which clears the selection as any press on the page does."""
        return self.click((1300, 60))

    def sent(self):
        return [body for url, body in self.page.evaluate("window.__sent") if url == "/query"]

    def close(self):
        self.page.close()


with sync_playwright() as pw:
    browser = pw.chromium.launch()

    # ---- the bar
    p = Page(browser)
    check("the app starts the module: one bar on the page, not shown; nothing of the popup it replaces",
          p.page.evaluate("document.querySelectorAll('.selection-bar').length") == 1 and not p.state()["on"] and not p.page.evaluate("!!document.getElementById('selectionPopup')"))
    line = p.lines(PHRASE)[0]
    s = p.select()
    over = s["bar"]["y"] + s["bar"]["h"] <= s["box"]["y"]
    check("text selected with the mouse: the bar - Ask, Copy - stands over the selection, not on it, where the pointer let go, inside the window",
          s["on"] and s["words"] == ["Ask", "Copy"] and over and abs(s["bar"]["x"] + s["bar"]["w"] / 2 - (line["x"] + line["w"] - 1)) <= 2
          and s["bar"]["y"] >= 8 and s["bar"]["x"] + s["bar"]["w"] <= 1440 - 8, s)
    check("the bar takes nothing: the selection is still there, the focus has not moved, and the text is marked in the colour it always was",
          s["selected"] == PHRASE and s["focus"] == "BODY"
          and p.page.evaluate("getComputedStyle(document.querySelector('#content-answer p'), '::selection').backgroundColor") == "rgba(140, 231, 182, 0.3)", s)
    if SHOTS:
        os.makedirs(SHOTS, exist_ok=True)
        p.page.screenshot(path=os.path.join(SHOTS, "selection_bar.png"), clip={"x": 681, "y": 82, "width": 759, "height": 200})
    p.page.keyboard.press("Control+c")
    p.page.wait_for_timeout(100)
    check("Ctrl+C copies the selection, as on any page", p.page.evaluate("window.__copies") == [{"at": "P", "selected": PHRASE}], p.page.evaluate("window.__copies"))
    s = p.click(s["copy"])
    said = s["words"]
    p.page.wait_for_timeout(1100)
    later = p.state()
    check("Copy copies it too, and takes no focus either: the button says Copied, the bar goes a moment later, the selection stays",
          len(p.page.evaluate("window.__copies")) == 2 and p.page.evaluate("window.__copies")[1] == {"at": "P", "selected": PHRASE} and said == ["Ask", "Copied"] and s["on"]
          and s["focus"] == "BODY" and not later["on"] and later["selected"] == PHRASE, (said, s["focus"], later, p.page.evaluate("window.__copies")))
    p.elsewhere()
    s = p.select()
    p.page.keyboard.press("Escape")
    after = p.state()
    check("Esc hides the bar and leaves the selection", s["on"] and s["words"] == ["Ask", "Copy"] and not after["on"] and after["selected"] == PHRASE, (s, after))
    p.elsewhere()
    s = p.select()
    after = p.elsewhere()
    check("a press elsewhere hides it", s["on"] and not after["on"], (s, after))
    s = p.select()
    p.page.evaluate("window.__shown = 0")
    after = p.click((line["x"] + 40, line["y"] + line["h"] / 2))
    check("a click inside the selection clears it, and the bar does not come back even for a moment (the browser still reports the selection at that mouse-up)",
          s["on"] and not after["on"] and after["selected"] == "" and p.page.evaluate("window.__shown") == 0, (s, after, p.page.evaluate("window.__shown")))
    s = p.select()
    p.page.click("#modeSliderPopup .mode-option[data-mode=quick]")
    p.page.wait_for_timeout(150)
    after = p.state()
    check("a button pressed elsewhere on the page does not bring the bar back, whatever is still selected", s["on"] and not after["on"], (s, after))
    p.elsewhere()
    s = p.select()
    p.page.mouse.click(line["x"] + 40, line["y"] + line["h"] / 2, button="right")
    p.page.wait_for_timeout(150)
    after = p.state()
    check("a right click on the selection, for the browser's own menu: the selection stays for its Copy, and the bar goes and does not come back", s["on"] and not after["on"] and after["selected"] == PHRASE, (s, after))
    p.elsewhere()
    p.page.mouse.dblclick(line["x"] + 40, line["y"] + line["h"] / 2)
    p.page.wait_for_timeout(150)
    s = p.state()
    check("a word selected with a double click gets the bar as well", s["on"] and s["selected"].strip() == "sand", s)
    p.elsewhere()

    edge = p.lines("on loam and on clay;")[0]
    s = p.select("on loam and on clay;")
    check("a selection at the pane's right edge: the bar is kept inside the window", s["on"] and edge["x"] + edge["w"] > 1440 - 75 and abs(s["bar"]["x"] + s["bar"]["w"] - (1440 - 8)) <= 1, (edge, s))
    p.elsewhere()

    # ---- where the bar stands for a selection of several lines
    top, bottom = p.lines("Plot 2: regime C")[0], p.lines("Plot 4: regime B")[0]
    s = p.drag((top["x"] + 1, top["y"] + top["h"] / 2), (bottom["x"] + bottom["w"], bottom["y"] + bottom["h"] / 2))
    check("several lines selected downwards: the bar stands under the last line", s["on"] and s["bar"]["y"] >= s["box"]["y"] + s["box"]["h"] and s["box"]["h"] > 3 * line["h"], s)
    p.elsewhere()
    s = p.drag((bottom["x"] + bottom["w"], bottom["y"] + bottom["h"] / 2), (top["x"] + 1, top["y"] + top["h"] / 2))
    check("... selected upwards: over the first line", s["on"] and s["bar"]["y"] + s["bar"]["h"] <= s["box"]["y"] and s["box"]["h"] > 3 * line["h"], s)
    p.elsewhere()
    low = [l for l in (p.lines(f"Plot {i}: regime")[0] for i in range(8, 16)) if l["y"] + l["h"] < 900][-1]      # the last plot whose first line is in view
    s = p.drag((top["x"] + 1, top["y"] + top["h"] / 2), (low["x"] + 300, low["y"] + low["h"] / 2))
    check("no room under a selection that ends at the foot of the window: the bar goes over its first line instead",
          s["on"] and s["box"]["y"] + s["box"]["h"] > 900 - 48 and s["bar"]["y"] + s["bar"]["h"] <= s["box"]["y"], s)
    p.elsewhere()

    # ---- what takes the bar away, and what does not
    s = p.select()
    p.page.evaluate("T.scroller().scrollTop += 60")
    p.page.wait_for_timeout(150)
    after = p.state()
    check("the tab scrolled: the bar goes (it would be left behind), the selection stays", s["on"] and not after["on"] and after["selected"] == PHRASE, (s, after))
    p.page.evaluate("T.scroller().scrollTop = 0")
    p.page.wait_for_timeout(150)
    p.elsewhere()
    s = p.select()
    p.page.evaluate("document.getElementById('streamOutput').scrollTop += 200")
    p.page.wait_for_timeout(150)
    after = p.state()
    check("the other pane scrolled, as it does all through an analysis: the bar stays",
          s["on"] and after["on"] and p.page.evaluate("document.getElementById('streamOutput').scrollTop") > 0, (s, after))
    p.page.evaluate("document.querySelector('#content-answer .markdown-content').insertAdjacentHTML('beforeend', '<p>Plot 41: regime C on sand, yield 5.6 t/ha.</p>')")
    p.page.wait_for_timeout(200)
    after = p.state()
    check("the tab added to further down, the selection untouched: the bar stays too", after["on"] and after["selected"] == PHRASE, after)
    p.page.evaluate("window.getSelection().removeAllRanges()")
    p.page.wait_for_timeout(200)
    after = p.state()
    check("the selection cleared by the page itself, with no press and no key: the bar goes", not after["on"] and after["selected"] == "", after)
    p.elsewhere()
    s = p.select()
    p.page.evaluate("(() => { const tab = document.querySelector('#content-answer .markdown-content'); tab.innerHTML = tab.innerHTML; })()")
    p.page.wait_for_timeout(200)
    after = p.state()
    check("the tab drawn again under the selection, as a running analysis draws it: the selection is gone and the bar with it", s["on"] and not after["on"] and after["selected"] == "", (s, after))
    s = p.select()
    p.page.set_viewport_size({"width": 1380, "height": 900})
    p.page.wait_for_timeout(200)
    after = p.state()
    p.page.set_viewport_size({"width": 1440, "height": 900})
    p.page.wait_for_timeout(200)
    check("the window resized: the bar goes", s["on"] and not after["on"], (s, after))
    p.elsewhere()

    # ---- where no bar is offered
    note = p.page.evaluate("(() => { const r = document.getElementById('note').getBoundingClientRect(); return [r.x + 30, r.y + r.height / 2]; })()")
    p.page.mouse.dblclick(*note)
    p.page.wait_for_timeout(150)
    s = p.state()
    check("text selected in a field being typed in: no bar", not s["on"] and s["focus"] == "note", s)
    p.elsewhere()
    s = p.drag((line["x"] + line["w"] - 1, line["y"] + line["h"] / 2), (1200, 20))
    check("a selection that reaches out of the content pane: no bar", not s["on"] and len(s["selected"]) > len(PHRASE), s)
    p.elsewhere()
    p.page.evaluate("activateTab('plot')")
    p.page.wait_for_timeout(150)
    s = p.select("Yield by regime")
    check("the Plots tab, whose figures have their own question row: no bar", not s["on"] and s["selected"] == "Yield by regime", s)
    p.elsewhere()
    p.page.evaluate("activateTab('code_exec_results')")
    p.page.wait_for_timeout(150)
    s = p.select("regime B +0.42 t/ha over A")
    check("the Results tab's output: the bar, as on every other tab", s["on"] and s["selected"] == "regime B +0.42 t/ha over A" and s["bar"]["y"] + s["bar"]["h"] <= s["box"]["y"], s)
    p.elsewhere()
    p.page.evaluate("activateTab('answer')")
    p.page.wait_for_timeout(150)

    # ---- Ask: the selection on the query box, the question sent with it
    s = p.select()
    s = p.click(s["ask"])
    check("Ask: the bar goes, the selection sits on the query box as a quote - on one line, whole under the pointer - and the cursor is in the box; nothing is sent",
          not s["on"] and s["quote"]["on"] and s["quote"]["words"] == PHRASE and s["quote"]["whole"] == PHRASE and s["focus"] == "queryInput" and p.sent() == [], (s, p.sent()))
    p.page.keyboard.type(QUESTION)
    if SHOTS:
        p.page.screenshot(path=os.path.join(SHOTS, "selection_quote.png"), clip={"x": 47, "y": 740, "width": 634, "height": 160})
    p.page.click("#submitQuery")
    p.page.wait_for_timeout(300)
    s = p.state()
    check("the question sent: the passage goes under it, as the analyst has always been given the two; the box is emptied and the quote with it",
          [q["query"] for q in p.sent()] == [QUESTION + "\n**Task Context:**\n" + PHRASE] and s["box_text"] == "" and not s["quote"]["on"], (p.sent(), s))
    check("nothing went wrong on the page on the way", p.errors[p.offline:] == [], p.errors[p.offline:])
    p.close()

    p = Page(browser)
    s = p.select()
    p.click(s["ask"])
    first, last = p.lines("Plot 1: regime B")[0], p.lines("Plot 3: regime A")[0]
    s = p.drag((first["x"] + 1, first["y"] + first["h"] / 2), (last["x"] + last["w"], last["y"] + last["h"] / 2))
    passage = s["selected"].strip()
    s = p.click(s["ask"])
    check("another Ask takes the first quote's place; a passage of several paragraphs is one clipped line on the box and whole under the pointer",
          s["quote"]["on"] and s["quote"]["whole"] == passage and "\n" in passage and "\n" not in s["quote"]["words"] and s["quote"]["words"].startswith("Plot 1: regime B on clay")
          and s["quote"]["clipped"] and s["quote"]["height"] < 40, s)
    p.page.keyboard.type("Which of these plots flooded?")
    p.page.keyboard.press("Control+Enter")
    p.page.wait_for_timeout(300)
    check("... and goes whole under its question, sent from the keyboard", [q["query"] for q in p.sent()] == ["Which of these plots flooded?\n**Task Context:**\n" + passage], p.sent())
    p.close()

    p = Page(browser)
    s = p.select()
    s = p.click(s["ask"])
    s = p.click(s["quote"]["remove"])
    gone = (s["quote"]["on"], s["focus"])
    p.page.keyboard.type(QUESTION)
    p.page.click("#submitQuery")
    p.page.wait_for_timeout(300)
    check("the quote's × takes it off and leaves the cursor in the box: the question then goes alone",
          gone == (False, "queryInput") and [q["query"] for q in p.sent()] == [QUESTION], (gone, p.sent()))
    p.close()

    p = Page(browser)
    s = p.select()
    p.click(s["ask"])
    p.page.click("#submitQuery")
    p.page.wait_for_timeout(300)
    s = p.state()
    check("a quote with no question typed is not sent, and stays on the box", p.sent() == [] and s["quote"]["on"], (p.sent(), s))
    p.page.evaluate("document.getElementById('queryInput').value = 'What does the plot show?'; handleQuerySubmit({ image: 'AAAA' });")
    p.page.wait_for_timeout(300)
    s = p.state()
    check("a plot's own question takes the box as it always did - without the passage - and the box is emptied, the quote with it",
          [(q["query"], q.get("image")) for q in p.sent()] == [("What does the plot show?", "AAAA")] and s["box_text"] == "" and not s["quote"]["on"], (p.sent(), s))
    p.close()

    p = Page(browser)
    p.page.evaluate("() => { window.__framed = []; window.ArchitectUI.isOn = () => true; window.ArchitectUI.open = q => { window.__framed.push(q); }; }")
    s = p.select()
    p.click(s["ask"])
    p.page.keyboard.type(QUESTION)
    p.page.click("#submitQuery")
    p.page.wait_for_timeout(300)
    s = p.state()
    check("with the Pathfinder on, the question is framed like any other typed one, its passage with it; the box is the Pathfinder's to empty when the brief opens",
          p.page.evaluate("window.__framed") == [QUESTION + "\n**Task Context:**\n" + PHRASE] and p.sent() == [] and s["box_text"] == QUESTION and s["quote"]["on"], (p.page.evaluate("window.__framed"), s))
    p.close()

    p = Page(browser)
    p.page.click("#collapseButton")
    p.page.wait_for_timeout(400)
    folded = p.state()["folded"]
    s = p.select()
    s = p.click(s["ask"])
    p.page.wait_for_timeout(400)
    s = p.state()
    check("the left pane folded away: Ask opens it, with the quote on the box and the cursor there",
          folded and not s["folded"] and s["quote"]["on"] and s["focus"] == "queryInput" and p.page.evaluate("document.getElementById('queryInput').getBoundingClientRect().width") > 200, s)
    p.click(s["quote"]["remove"])
    p.page.evaluate("document.body.classList.add('composer-locked')")
    s = p.select()
    look = p.page.evaluate("(() => { const c = getComputedStyle(document.querySelector('.selection-bar .ask')); return [c.opacity, c.pointerEvents]; })()")
    held = p.click(s["ask"])
    copies = len(p.page.evaluate("window.__copies"))
    p.click(held["copy"])
    check("the query box held (a run's view, the Pathfinder replying): Ask is greyed and takes no press, Copy works",
          s["on"] and look == ["0.4", "none"] and not held["quote"]["on"] and held["on"] and len(p.page.evaluate("window.__copies")) == copies + 1, (look, held))
    check("nothing went wrong on this page either", p.errors[p.offline:] == [], p.errors[p.offline:])
    p.close()
    browser.close()

n_fail = sum(1 for _, ok in results if not ok)
print(f"\n{len(results) - n_fail} passed, {n_fail} failed")
sys.exit(1 if n_fail else 0)
