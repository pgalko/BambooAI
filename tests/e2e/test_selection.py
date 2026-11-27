"""Asking about a selection, in a real Chromium on the real page (2026-11-27, the product owner's picks of the
mockups; web_app/static/js/selection.js, explain.js). Text selected in the content pane gets a small bar beside it -
Ask, Copy - which takes no focus, so the selection stays and copies as on any page. Ask puts the selection on the query
box as a quote; the question typed there is answered in a few sentences, in a note under the passage, and the passage
stays marked. No analysis starts. A follow-up is asked the same way: words selected in the note or in the marked
passage, then Ask.

Before, a query popup opened at every mouse-up and took the cursor, which dropped the selection: nothing could be
copied out of a tab, and the popup lay on the text.

    python3 tests/e2e/test_selection.py        # about two minutes; skips (exit 0) when playwright is not installed
    SHOTS=/tmp/shots python3 tests/e2e/test_selection.py      # and the bar, the quote and the notes as pictures

The page whole - the template with every stylesheet and script, started by the app's own continueAppInitialization() -
with a finished analysis drawn into its tabs by the page's own functions and the backend answered here
(tools/render_page.py's way); the content is an invented field trial.
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
    print(("  ok   " if cond else "  FAIL ") + name + ("" if cond else f"  <- {str(detail)[:900]}"))


spec = importlib.util.spec_from_file_location("render_page", os.path.join(ROOT, "tools", "render_page.py"))
render_page = importlib.util.module_from_spec(spec)
spec.loader.exec_module(render_page)
PAGE = render_page.static_index()
SHOTS = os.environ.get("SHOTS")

PHRASE = "on sand the two cannot be told apart"
QUESTION = "Why can they not be told apart?"
REPLY = "On sand the range of the difference runs from below zero to above it, so `B` could be better or worse there."
PLOTS = "\n\n".join(f"Plot {i}: regime {'ABC'[i % 3]} on {('loam', 'clay', 'sand')[i % 3]}, yield {5 + i % 7 / 10:.1f} t/ha, watered every {2 + i % 3} days "
                    "through the season, with the flooded plots kept and flagged." for i in range(1, 41))
ANSWER = ("# Yield under the three watering regimes\n\nRegime B gave the highest yield in this trial. Its lead over regime A is clear on loam and on clay; "
          f"{PHRASE}.\n\nA note on the trial: <input id=\"note\" value=\"regime B on loam\">\n\n1. Loam: the lead of regime B is clear.\n2. Clay: the lead of regime B is clear.\n\n{PLOTS}")
PLAIN = "# Yield under the three watering regimes\n\nRegime B did best. On sand nobody can say which regime is better."
CODE = ('import pandas as pd\n\ndf = DS.load()\nmeans = df.groupby("regime")["yield_t"].mean()\nnote = """the same\nwithin each soil type"""\n'
        'gap = means["B"] - means["A"]\nprint(means, gap)\n')
OUTPUT = "regime B +0.42 t/ha over A  CI [0.18, 0.66]  n=96\nregime C -0.09 t/ha over A  CI [-0.33, 0.15]  n=96\n"
THREAD, CHAIN = 3, 7


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


# The two libraries that draw on a tab after the page has drawn it, as far as they change the page: the highlighter
# turns the code's text into elements - a string of several lines is one of them -, and the formulas' renderer is there
# to be called (without it the Answer tab is never finished: its buttons are added after the formulas are set)
LIBRARIES = r"""window.hljs = { configure() {}, highlightAll() {}, highlightBlock(el) { this.highlightElement(el); },
  highlightElement(el) { const esc = s => s.replace(/&/g, '&amp;').replace(/</g, '&lt;');
    el.innerHTML = esc(el.textContent).replace(/("{3}[\s\S]*?"{3}|"[^"\n]*"|\b(?:import|as|print)\b)/g, m => '<span class="hljs-' + (m[0] === '"' ? 'string' : 'keyword') + '">' + m + '</span>');
    el.classList.add('hljs'); } };
window.renderMathInElement = function () {};"""
# what the suite reads off the page: the bar, the selection, the quote, where the focus is; the marks and the notes
HELPERS = """
window.T = {
  lines(phrase, nth) {      // the boxes of a phrase's lines - its n-th occurrence - in the tab that is on screen
    const walker = document.createTreeWalker(document.querySelector('#contentOutput .tab-content.active'), NodeFilter.SHOW_TEXT); let node, seen = 0;
    while ((node = walker.nextNode())) { let i = -1;
      while ((i = node.textContent.indexOf(phrase, i + 1)) >= 0) { if (seen++ !== (nth || 0)) continue;
        const r = document.createRange(); r.setStart(node, i); r.setEnd(node, i + phrase.length);
        return [...r.getClientRects()].map(b => ({ x: b.x, y: b.y, w: b.width, h: b.height })); } }
    return null; },
  state() {
    const bar = document.querySelector('.selection-bar'), b = bar.getBoundingClientRect(), s = window.getSelection(), quote = document.getElementById('queryQuote');
    const box = s.rangeCount ? s.getRangeAt(0).getBoundingClientRect() : null, ask = bar.querySelector('.ask'), copy = bar.querySelector('.copy');
    const mid = e => { const r = e.getBoundingClientRect(); return [r.x + r.width / 2, r.y + r.height / 2]; };
    return { on: getComputedStyle(bar).display !== 'none', asks: getComputedStyle(ask).display !== 'none', bar: { x: b.x, y: b.y, w: b.width, h: b.height },
             words: [ask.textContent, copy.textContent], ask: mid(ask), copy: mid(copy),
             selected: s.toString(), box: box && { x: box.x, y: box.y, w: box.width, h: box.height }, focus: document.activeElement.id || document.activeElement.nodeName,
             quote: { on: getComputedStyle(quote).display !== 'none', words: quote.querySelector('.t').textContent, whole: quote.querySelector('.t').title, remove: mid(quote.querySelector('button')),
                      clipped: quote.querySelector('.t').scrollWidth > quote.querySelector('.t').clientWidth, height: quote.getBoundingClientRect().height },
             box_text: document.getElementById('queryInput').value, folded: document.getElementById('leftPanel').classList.contains('collapsed') }; },
  notes() {            // the marks, each with its note's number, its words and its tab; the notes, each with where it stands and what it holds
    const box = e => { const r = e.getBoundingClientRect(); return { x: r.x, y: r.y, w: r.width, h: r.height }; };
    return { marks: [...document.querySelectorAll('.xp-mark')].map(m => [m.dataset.k, m.textContent, m.closest('.tab-content').id.slice(8), m.classList.contains('lost')]),
             notes: [...document.querySelectorAll('.xp-note')].map(n => ({ k: n.dataset.k, within: n.parentElement.tagName, before: n.previousElementSibling ? n.previousElementSibling.tagName : '', box: box(n),
               shown: getComputedStyle(n).display !== 'none', font: getComputedStyle(n).fontFamily === getComputedStyle(document.getElementById('queryInput')).fontFamily,
               asked: [...n.querySelectorAll('details')].map(d => ({ open: d.open, live: d.classList.contains('live'), q: d.querySelector('summary').textContent, a: d.querySelector('.a').textContent,
                 html: d.querySelector('.a').innerHTML, cursor: getComputedStyle(d.querySelector('.a'), '::after').content !== 'none' })) })),
             said: document.getElementById('summaryPopup').style.display === 'block' ? document.getElementById('summaryContent').textContent : '' }; },
  at(sel, dx) { const r = document.querySelector(sel).getBoundingClientRect(); return [r.x + (dx || 6), r.y + r.height / 2]; },
  scroller() {         // what scrolls the tab on screen
    let e = document.querySelector('#contentOutput .tab-content.active') || document.getElementById('contentOutput');
    while (e && !(e.scrollHeight > e.clientHeight + 4 && /auto|scroll/.test(getComputedStyle(e).overflowY))) e = e.parentElement;
    return e; },
};
window.__copies = []; window.__shown = 0; window.__clip = [];      // what was copied, how often the bar came on, what a Copy button wrote
new MutationObserver(() => { if (document.querySelector('.selection-bar').classList.contains('on')) window.__shown += 1; }).observe(document.querySelector('.selection-bar'), { attributes: true, attributeFilter: ['class'] });
document.addEventListener('copy', e => window.__copies.push({ at: e.target.id || e.target.nodeName, selected: window.getSelection().toString() }), true);
Object.defineProperty(navigator, 'clipboard', { value: { writeText: t => { window.__clip.push(t); return Promise.resolve(); } }, configurable: true });
"""
# The server, as the page sees it. Every call is kept. A question about a passage is answered as the server answers
# it - the answer in pieces, then everything asked about the analysis so far - or as the suite says (window.__explain);
# what was asked about a chain is given when the page asks for it. No other call is answered, so nothing arrives later
# to draw the page again under the test (the executor's status check, answered, clears the tabs and opens the Data tab)
SERVER = """window.__sent = []; window.__kept = {}; window.__explain = null; window.__reply = ''; window.__ms = 0;
window.authService = Object.assign(window.authService || {}, { fetch: (url, opts) => {
  const body = opts && opts.body ? JSON.parse(opts.body) : null; window.__sent.push([url, body]);
  if (url === '/explain') return window.__explain ? window.__explain(body) : window.__stream(body);
  if (url.startsWith('/explain/')) return Promise.resolve({ ok: true, json: async () => ({ asked: window.__kept[url.split('/').pop()] || [] }) });
  return new Promise(() => {}); } });
window.__stream = body => { const key = String(body.chain_id), enc = new TextEncoder(), text = window.__reply, ms = window.__ms, pieces = text.match(/\\S+\\s*/g) || [];
  return Promise.resolve(new Response(new ReadableStream({ start(c) { let i = 0; const step = () => {
    if (i < pieces.length) { c.enqueue(enc.encode(JSON.stringify({ text: pieces[i++], chain_id: 99 }) + '\\n')); setTimeout(step, ms); return; }
    const kept = (window.__kept[key] = (window.__kept[key] || []).concat([{ tab: body.tab, view: body.view, passage: body.passage, at: body.at, quote: body.quote, question: body.question, answer: text, cost: 0.003, when: 1, chain: 99 }]));
    c.enqueue(enc.encode(JSON.stringify({ explain: { asked: kept } }) + '\\n')); c.close(); }; step(); } }))); };"""
# a finished analysis: its tabs drawn by the page's own functions, and the chain kept as the page keeps one when its run ends
FILL = """([answer, plain, code, output, thread, chain]) => {
  currentData.simplifiedAnswer = plain; currentData.chain_id = chain; currentData.thread_id = thread; currentData.queryText = 'Which regime gives the highest yield?';
  createOrUpdateTab('answer', answer); createOrUpdateTab('code', code); createOrUpdateTab('plot', []); createOrUpdateTab('code_exec_results', output);
  createOrUpdateTab('brief', '<div class="markdown-content"><p>What the answer is for: which regime to keep next season</p></div>');
  document.getElementById('content-plot').innerHTML = '<p>Yield by regime, for each soil type</p>';
  document.getElementById('streamOutput').innerHTML = '<div style="height: 3000px">the analysis, turn by turn</div>';
  activateTab('answer'); }"""
# the plain version has arrived, as the stream brings it once the analysis has ended: its button is on
PLAIN_READY = """() => { const b = document.querySelector('.simplified-summary-btn'); b.style.display = ''; b.disabled = false; b.classList.remove('loading'); updateSimplifiedButtonLabel(); }"""
KEEP = """() => { responses.push({ chain_id: currentData.chain_id, thread_id: currentData.thread_id, queryText: currentData.queryText, parentChainId: null,
  tabContent: document.getElementById('tabContainer').innerHTML, contentOutput: document.getElementById('contentOutput').innerHTML, streamOutput: '', taskContents: {},
  technicalAnswer: currentData.technicalAnswer, simplifiedAnswer: currentData.simplifiedAnswer, summaryViewMode: 'technical' }); currentResponseIndex = responses.length - 1; }"""


class Page:
    """The app's page, started, with a finished analysis on it; the mouse as a person moves it."""

    def __init__(self, browser, finished=True):
        self.errors = []
        self.page = browser.new_page(viewport={"width": 1440, "height": 900})
        self.page.on("pageerror", lambda e: self.errors.append(str(e)))
        self.page.add_init_script(LIBRARIES)
        self.page.route("**/*", route)
        self.page.goto("http://app.local/")
        self.page.wait_for_timeout(600)
        self.page.evaluate("() => {" + SERVER + "}")      # as a function: a script that ends on one would have it called
        self.page.evaluate("window.handleNewConversation = function () {}; initializeUIControls(); if (window.WorkspaceGate) { WorkspaceGate.release(); WorkspaceGate.hide(); }")
        self.page.evaluate("continueAppInitialization()")                     # the app's own start: it starts the modules
        self.page.wait_for_timeout(400)
        self.page.evaluate("() => {" + HELPERS + "}")
        self.page.evaluate(FILL, [ANSWER, PLAIN, CODE, OUTPUT, THREAD, CHAIN])
        self.page.wait_for_timeout(400)
        self.page.evaluate(PLAIN_READY)
        if finished:
            self.page.evaluate(KEEP)
        self.offline = len(self.errors)                    # the libraries that are not reached here have said so by now

    def state(self):
        return self.page.evaluate("T.state()")

    def notes(self):
        return self.page.evaluate("T.notes()")

    def lines(self, phrase, nth=0):
        return self.page.evaluate("([p, n]) => T.lines(p, n)", [phrase, nth])

    def tab(self, name):
        self.page.evaluate("t => activateTab(t)", name)
        self.page.wait_for_timeout(200)

    def drag(self, start, end):
        self.page.mouse.move(*start)
        self.page.mouse.down()
        self.page.mouse.move(*end, steps=6)
        self.page.mouse.up()
        self.page.wait_for_timeout(120)
        return self.state()

    def select(self, phrase=PHRASE, nth=0):
        """The phrase, selected with the mouse from its first letter to its last."""
        lines = self.lines(phrase, nth)
        first, last = lines[0], lines[-1]
        return self.drag((first["x"] + 1, first["y"] + first["h"] / 2), (last["x"] + last["w"] - 1, last["y"] + last["h"] / 2))

    def click(self, point):
        self.page.mouse.click(*point)
        self.page.wait_for_timeout(150)
        return self.state()

    def elsewhere(self):
        """A press on the empty part of the tab strip, which clears the selection as any press on the page does."""
        return self.click((1300, 60))

    def ask(self, question, reply=REPLY, ms=0, wait=400):
        """Ask on the bar that is up, the question typed and sent; the server will answer with `reply`, a piece every `ms`."""
        self.page.evaluate("([reply, ms]) => { window.__reply = reply; window.__ms = ms; }", [reply, ms])
        self.click(self.state()["ask"])
        self.page.keyboard.type(question)
        self.page.click("#submitQuery")
        self.page.wait_for_timeout(wait)

    def sent(self):
        return [body for url, body in self.page.evaluate("window.__sent") if url == "/query"]

    def asked(self):
        return [body for url, body in self.page.evaluate("window.__sent") if url == "/explain"]

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
          s["on"] and s["asks"] and s["words"] == ["Ask", "Copy"] and over and abs(s["bar"]["x"] + s["bar"]["w"] / 2 - (line["x"] + line["w"] - 1)) <= 2
          and s["bar"]["y"] >= 8 and s["bar"]["x"] + s["bar"]["w"] <= 1440 - 8, s)
    check("the bar takes nothing: the selection is still there, the focus has not moved, and the text is marked in the colour it always was",
          s["selected"] == PHRASE and s["focus"] == "BODY"
          and p.page.evaluate("getComputedStyle(document.querySelector('#content-answer p'), '::selection').backgroundColor") == "rgba(140, 231, 182, 0.3)", s)
    if SHOTS:
        os.makedirs(SHOTS, exist_ok=True)
        p.page.screenshot(path=os.path.join(SHOTS, "selection_bar.png"), clip={"x": 681, "y": 82, "width": 759, "height": 240})
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
    low = [l for l in (p.lines(f"Plot {i}: regime")[0] for i in range(6, 16)) if l["y"] + l["h"] < 900][-1]      # the last plot whose first line is in view
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

    # ---- where no bar is offered, and where it only copies
    note = p.page.evaluate("(() => { const r = document.getElementById('note').getBoundingClientRect(); return [r.x + 30, r.y + r.height / 2]; })()")
    p.page.mouse.dblclick(*note)
    p.page.wait_for_timeout(150)
    s = p.state()
    check("text selected in a field being typed in: no bar", not s["on"] and s["focus"] == "note", s)
    p.elsewhere()
    s = p.drag((line["x"] + line["w"] - 1, line["y"] + line["h"] / 2), (1200, 20))
    check("a selection that reaches out of the content pane: no bar", not s["on"] and len(s["selected"]) > len(PHRASE), s)
    p.elsewhere()
    p.tab("plot")
    s = p.select("Yield by regime")
    check("the Plots tab, whose figures have their own question row: no bar", not s["on"] and s["selected"] == "Yield by regime", s)
    p.elsewhere()
    p.tab("brief")
    s = p.select("which regime to keep")
    check("a tab whose text cannot be asked about - the Brief: the bar copies, and has no Ask", s["on"] and not s["asks"] and s["selected"] == "which regime to keep", s)
    p.elsewhere()
    p.tab("code_exec_results")
    s = p.select("regime B +0.42 t/ha over A")
    check("the Results tab's output: the bar with Ask, as on the Answer and the Code tab", s["on"] and s["asks"] and s["selected"] == "regime B +0.42 t/ha over A" and s["bar"]["y"] + s["bar"]["h"] <= s["box"]["y"], s)
    p.elsewhere()
    p.tab("code")
    s = p.select("groupby")
    in_code = s["on"] and s["asks"]
    p.elsewhere()
    p.tab("answer")
    p.page.evaluate("queryRunning = true")
    s = p.select()
    p.page.evaluate("queryRunning = false")
    check("... and while an analysis runs the bar copies only: nothing can be asked beside it", in_code and s["on"] and not s["asks"], s)
    p.elsewhere()
    check("nothing went wrong on the page on the way", p.errors[p.offline:] == [], p.errors[p.offline:])
    p.close()

    q = Page(browser, finished=False)
    s = q.select()
    check("a page with no finished analysis on it - one being written, or none: the bar copies only", s["on"] and not s["asks"] and s["selected"] == PHRASE, s)
    q.close()

    # ---- Ask: the selection on the query box, the question answered in a note under the passage
    p = Page(browser)
    s = p.select()
    s = p.click(s["ask"])
    check("Ask: the bar goes, the selection sits on the query box as a quote - on one line, whole under the pointer - and the cursor is in the box; nothing is sent",
          not s["on"] and s["quote"]["on"] and s["quote"]["words"] == PHRASE and s["quote"]["whole"] == PHRASE and s["focus"] == "queryInput" and p.sent() == [] and p.asked() == [], (s, p.sent()))
    p.page.keyboard.type(QUESTION)
    if SHOTS:
        p.page.screenshot(path=os.path.join(SHOTS, "selection_quote.png"), clip={"x": 47, "y": 740, "width": 634, "height": 160})
    p.page.evaluate("([reply, ms]) => { window.__reply = reply; window.__ms = ms; }", [REPLY, 150])
    p.page.click("#submitQuery")
    p.page.wait_for_timeout(700)
    s, n = p.state(), p.notes()
    mark = p.page.evaluate("(() => { const r = document.querySelector('.xp-mark').getBoundingClientRect(); return { x: r.x, y: r.y, w: r.width, h: r.height }; })()")
    live = n["notes"][0] if n["notes"] else {}
    check("the question sent: no analysis starts - the server is asked about the passage, with where it stands, the words selected and the question; the box is emptied and the quote with it",
          p.sent() == [] and p.asked() == [{"thread_id": THREAD, "chain_id": CHAIN, "tab": "answer", "view": "technical", "passage": PHRASE, "at": 0, "quote": PHRASE, "question": QUESTION}]
          and s["box_text"] == "" and not s["quote"]["on"], (p.sent(), p.asked(), s))
    check("at once the passage is marked where it stands, and its note is open under its paragraph, on the question; the answer is shown as it is written, ending on a cursor",
          n["marks"] == [["0", PHRASE, "answer", False]] and abs(mark["x"] - line["x"]) <= 1 and abs(mark["y"] - line["y"]) <= 3 and len(n["notes"]) == 1 and live["before"] == "P" and live["within"] == "DIV"
          and live["box"]["y"] >= mark["y"] + mark["h"] and live["font"] and len(live["asked"]) == 1 and live["asked"][0]["q"] == QUESTION and live["asked"][0]["open"] and live["asked"][0]["live"]
          and live["asked"][0]["cursor"] and 0 < len(live["asked"][0]["a"]) < len(REPLY) and REPLY.replace("`", "").startswith(live["asked"][0]["a"].replace("`", "")), (n, mark, line))
    p.page.click("#queryInput")
    p.page.keyboard.type("And on clay?")
    p.page.click("#submitQuery")
    p.page.wait_for_timeout(200)
    held = (p.state(), p.notes())
    check("while the answer is being written nothing else starts: a question sent meanwhile stays in the box, and the page says why",
          held[0]["box_text"] == "And on clay?" and p.sent() == [] and len(p.asked()) == 1 and "An explanation is being written. Wait for it." in held[1]["said"], held)
    p.page.wait_for_timeout(3500)
    n = p.notes()
    done = n["notes"][0] if n["notes"] else {}
    check("the answer whole: drawn as the report's text is - a name from the code as code -, no cursor; the passage stays marked",
          n["marks"] == [["0", PHRASE, "answer", False]] and len(done["asked"]) == 1 and not done["asked"][0]["live"] and not done["asked"][0]["cursor"] and done["asked"][0]["a"] == REPLY.replace("`", "")
          and "<code>B</code>" in done["asked"][0]["html"] and done["asked"][0]["open"], n)
    if SHOTS:
        p.page.screenshot(path=os.path.join(SHOTS, "selection_note.png"), clip={"x": 681, "y": 82, "width": 759, "height": 330})
    p.page.evaluate("document.getElementById('queryInput').value = ''; document.getElementById('summaryPopup').style.display = 'none'")

    # a click on the marked passage shuts its note, and opens it; it puts nothing on the query box
    s = p.click(p.page.evaluate("T.at('.xp-mark', 30)"))
    shut = (len(p.notes()["notes"]), s["quote"]["on"], s["on"])
    s = p.click(p.page.evaluate("T.at('.xp-mark', 30)"))
    again = (len(p.notes()["notes"]), s["quote"]["on"], s["focus"])
    check("a click on the marked passage shuts its note, and another opens it; no quote comes onto the query box, no bar, and nothing is asked",
          shut == (0, False, False) and again == (1, False, "BODY") and len(p.asked()) == 1 and p.sent() == [], (shut, again))

    # a press on the marked passage that ends as a selection is the bar's; a click inside that selection is a click
    words = p.lines("the two")[0]
    s = p.select("the two")
    dragged = (s["selected"], s["on"], len(p.notes()["notes"]))
    s = p.click((words["x"] + 10, words["y"] + words["h"] / 2))
    inside = (s["selected"], len(p.notes()["notes"]))
    p.click(p.page.evaluate("T.at('.xp-mark', 30)"))
    check("words selected inside the marked passage - a press that begins and ends on it - open and shut nothing; a click inside that selection clears it and is read as a click, once the browser has "
          "settled what is selected: the note shuts", dragged == ("the two", True, 1) and inside == ("", 0) and len(p.notes()["notes"]) == 1, (dragged, inside))

    # a selection that runs across the open note holds none of its words
    start, end = p.lines("told apart")[0], p.lines("A note on the trial")[0]
    s = p.drag((start["x"] + 1, start["y"] + start["h"] / 2), (end["x"] + end["w"] - 1, end["y"] + end["h"] / 2))
    across = s["selected"]
    s = p.click(s["ask"])
    quoted = s["quote"]["whole"]
    p.click(s["quote"]["remove"])
    check("a selection that runs across the open note: the browser's selection holds the note's words, the quote on the query box none of them",
          QUESTION in across and quoted.startswith("told apart.") and quoted.endswith("A note on the trial") and QUESTION not in quoted and "range of the difference" not in quoted
          and len(p.notes()["notes"]) == 1 and p.notes()["notes"][0]["shown"], (across, quoted))

    # a follow-up: words selected in the note, then Ask
    s = p.select("better or worse")
    in_note = (s["on"], s["asks"], s["selected"])
    p.ask("Which is more likely?", "Neither: the middle of the range is close to zero.")
    n = p.notes()
    follow = n["notes"][0] if n["notes"] else {}
    check("a follow-up is asked as the first question was - words selected in the note, Ask, the question: the server is told the note's own passage and the words selected, and the answer joins "
          "the note - the earlier question one line, the newest open",
          in_note == (True, True, "better or worse") and p.asked()[1] == {"thread_id": THREAD, "chain_id": CHAIN, "tab": "answer", "view": "technical", "passage": PHRASE, "at": 0, "quote": "better or worse",
                                                                             "question": "Which is more likely?"}
          and len(n["notes"]) == 1 and [(a["q"], a["open"]) for a in follow["asked"]] == [(QUESTION, False), ("Which is more likely?", True)] and n["marks"] == [["0", PHRASE, "answer", False]]
          and follow["asked"][1]["a"] == "Neither: the middle of the range is close to zero." and p.sent() == [], (in_note, p.asked()[1:], n))
    p.click(p.page.evaluate("T.at('.xp-note summary', 40)"))
    opened = [a["open"] for a in p.notes()["notes"][0]["asked"]]
    s = p.select("the two")
    on_mark = (s["on"], s["asks"])
    p.ask("Which two?", "Regime A and regime B.")
    n = p.notes()
    check("an earlier question opens at a click on its line; words selected in the marked passage are a follow-up too, to the same note",
          opened == [True, True] and on_mark == (True, True) and p.asked()[2]["passage"] == PHRASE and p.asked()[2]["quote"] == "the two" and p.asked()[2]["at"] == 0
          and [a["q"] for a in n["notes"][0]["asked"]] == [QUESTION, "Which is more likely?", "Which two?"] and [a["open"] for a in n["notes"][0]["asked"]] == [False, False, True], (opened, on_mark, n))

    # another passage: in a list, the second place its words stand at
    s = p.select("the lead of regime B is clear", 1)
    p.ask("How clear?", "Its whole range is above zero.")
    n = p.notes()
    check("another passage, the second place its words stand at in the tab: it is marked there, its note opens at the end of its list item, and the first note shuts - both passages stay marked",
          p.asked()[3]["passage"] == "the lead of regime B is clear" and p.asked()[3]["at"] == 1 and n["marks"] == [["0", PHRASE, "answer", False], ["1", "the lead of regime B is clear", "answer", False]]
          and len(n["notes"]) == 1 and n["notes"][0]["k"] == "1" and n["notes"][0]["within"] == "LI" and [a["q"] for a in n["notes"][0]["asked"]] == ["How clear?"]
          and p.page.evaluate("document.querySelector('.xp-mark[data-k=\"1\"]').closest('li').textContent.startsWith('Clay')"), (p.asked()[3:], n))
    p.click(p.page.evaluate("T.at('.xp-mark[data-k=\"0\"]', 30)"))
    n = p.notes()
    check("a click on the first passage opens its note - all three questions, the newest open - and the other shuts", len(n["notes"]) == 1 and n["notes"][0]["k"] == "0" and len(n["notes"][0]["asked"]) == 3, n)

    # the code
    p.tab("code")
    s = p.select("groupby")
    p.ask("What does this do?", "It forms one group of rows for each regime.")
    n = p.notes()
    code = p.page.evaluate("""(() => { const c = document.querySelector('#content-code pre code'), note = c.querySelector('.xp-note'), mark = c.querySelector('.xp-mark').getBoundingClientRect(),
      next = T.lines('note = ')[0]; return { within: note.parentElement === c, under: note.getBoundingClientRect().y >= mark.bottom - 1, over: note.getBoundingClientRect().bottom <= next.y + 1,
      spans: c.querySelectorAll('span[class^=hljs]').length, wraps: getComputedStyle(note).whiteSpace }; })()""")
    check("a passage of the code: marked in the highlighted script, its note under its line and over the next, read as text - not as code - in the page's own font",
          p.asked()[4]["tab"] == "code" and p.asked()[4]["view"] == "" and p.asked()[4]["passage"] == "groupby" and ["2", "groupby", "code", False] in n["marks"] and len(n["notes"]) == 1
          and n["notes"][0]["font"] and code["within"] and code["under"] and code["over"] and code["spans"] > 4 and code["wraps"] == "normal", (p.asked()[4:], code, n))
    if SHOTS:
        p.page.screenshot(path=os.path.join(SHOTS, "selection_note_code.png"), clip={"x": 681, "y": 82, "width": 759, "height": 330})
    p.page.click("#content-code .copy-button")
    p.page.wait_for_timeout(150)
    check("Copy on the Code tab gives the script as it was written, with a note open in it", p.page.evaluate("window.__clip") == [CODE], p.page.evaluate("window.__clip"))
    s = p.select("within each soil type")
    p.ask("What is this?", "The second line of a note kept in a variable.")
    n = p.notes()
    inside = p.page.evaluate("""(() => { const note = document.querySelector('#content-code .xp-note'), mark = document.querySelector('.xp-mark[data-k="3"]').getBoundingClientRect(), next = T.lines('gap = ')[0];
      return [note.getBoundingClientRect().y >= mark.bottom - 1, note.getBoundingClientRect().bottom <= next.y + 1, document.querySelector('#content-code pre code').textContent.replace(note.textContent, '')]; })()""")
    check("a passage inside a string of several lines, which the highlighter keeps as one element: its note stands under its own line all the same, and the script reads as written",
          ["3", "within each soil type", "code", False] in n["marks"] and inside == [True, True, CODE], (inside[:2], n["marks"]))

    # what was printed
    p.tab("code_exec_results")
    s = p.select("CI [0.18, 0.66]")
    p.ask("What is CI?", "The range the difference is likely to lie in.")
    n = p.notes()
    check("a passage of what the script printed: asked about on the Results tab, its note under its line",
          p.asked()[6]["tab"] == "code_exec_results" and p.asked()[6]["passage"] == "CI [0.18, 0.66]" and ["4", "CI [0.18, 0.66]", "code_exec_results", False] in n["marks"]
          and [x["k"] for x in n["notes"]] == ["4"] and n["notes"][0]["within"] == "CODE", (p.asked()[6:], n))

    # the Answer's other version
    p.tab("answer")
    p.page.click(".simplified-summary-btn")
    p.page.wait_for_timeout(400)
    n = p.notes()
    plain_marks = [m for m in n["marks"] if m[2] == "answer"]
    s = p.select("nobody can say")
    p.ask("Why not?", "The plots on sand are few.")
    n2 = p.notes()
    p.page.click(".simplified-summary-btn")
    p.page.wait_for_timeout(400)
    n3 = p.notes()
    check("the Answer in plain language is a text of its own: the technical report's marks are not drawn on it, a passage asked about there is its own, and back in the technical report that "
          "report's marks stand again",
          plain_marks == [] and p.asked()[7]["view"] == "simplified" and p.asked()[7]["passage"] == "nobody can say" and [m for m in n2["marks"] if m[2] == "answer"] == [["5", "nobody can say", "answer", False]]
          and [m for m in n3["marks"] if m[2] == "answer"] == [["0", PHRASE, "answer", False], ["1", "the lead of regime B is clear", "answer", False]], (plain_marks, p.asked()[7:], n2["marks"], n3["marks"]))

    # the chain shown again: the page asks the server what was asked about it
    before = len(p.page.evaluate("window.__sent"))
    p.page.evaluate("loadResponseContent(responses[0])")
    p.page.wait_for_timeout(900)
    n = p.notes()
    gets = [url for url, body in p.page.evaluate("window.__sent")[before:] if url.startswith("/explain/")]
    check("the chain shown again: what was asked about it is asked of the server, and every passage of the technical report, the code and the output is marked again - after the code is highlighted "
          "afresh -, no note open",
          gets == [f"/explain/{THREAD}/{CHAIN}"] and n["notes"] == [] and sorted(m[:3] for m in n["marks"]) == sorted([["0", PHRASE, "answer"], ["1", "the lead of regime B is clear", "answer"], ["2", "groupby", "code"],
                                                                                                                 ["3", "within each soil type", "code"], ["4", "CI [0.18, 0.66]", "code_exec_results"]])
          and p.page.evaluate("document.querySelector('#content-code pre code').textContent") == CODE, (gets, n))

    # a passage the tab no longer has
    p.tab("answer")
    p.page.evaluate("(() => { const b = document.querySelector('#content-answer .markdown-content'); b.innerHTML = b.innerHTML.replace(/cannot be told apart/g, 'differ little'); })()")
    p.page.wait_for_timeout(300)
    n = p.notes()
    lost = p.page.evaluate("(() => { const l = document.querySelector('#content-answer .xp-lost'); return l ? [l === l.parentElement.lastElementChild, l.parentElement.className, l.textContent] : null; })()")
    p.page.evaluate("document.querySelector('#content-answer .xp-mark.lost').click()")
    p.page.wait_for_timeout(250)
    lost_note = p.page.evaluate("(() => { const n = document.querySelector('.xp-note'); return n ? [n.previousElementSibling.className, n.querySelectorAll('details').length] : null; })()")
    p.page.evaluate("(() => { const b = document.querySelector('#content-answer .markdown-content'); b.innerHTML = b.innerHTML.replace(/differ little/g, 'cannot be told apart'); })()")
    p.page.wait_for_timeout(300)
    n2 = p.notes()
    check("a passage the tab no longer has - the report drawn with other words: its mark stands at the tab's foot, as the words first selected, and a click opens its note there. With the words "
          "back, the mark is on them again",
          ["0", PHRASE, "answer", True] in n["marks"] and lost == [True, "markdown-content content-body", PHRASE] and lost_note == ["xp-lost", 3]
          and ["0", PHRASE, "answer", False] in n2["marks"] and p.page.evaluate("document.querySelectorAll('.xp-lost').length") == 0, (n["marks"], lost, lost_note, n2["marks"]))

    # no answer
    p.page.evaluate("""() => { window.__explain = () => Promise.resolve({ ok: false, status: 403, text: async () => JSON.stringify({ error: 'authorization_failed',
      message: 'You have used all 20 of your 20 free queries this month.' }) }); document.getElementById('summaryPopup').style.display = 'none'; }""")
    p.page.evaluate("T.scroller().scrollTop = 0")             # the note opened at the tab's foot had brought the foot into view
    p.page.wait_for_timeout(150)
    marks_before = p.notes()["marks"]
    s = p.select("Plot 2: regime C on sand")
    p.click(s["ask"])
    p.page.keyboard.type("Which plot is this?")
    p.page.click("#submitQuery")
    p.page.wait_for_timeout(400)
    n = p.notes()
    check("a question the account refuses: the page says the refusal in its words, and the question goes with its mark - the other passages stand as they did",
          "You have used all 20 of your 20 free queries this month." in n["said"] and n["marks"] == marks_before and p.sent() == [], (n["said"], n["marks"]))
    p.page.evaluate("() => { window.__explain = null; }")
    check("nothing went wrong on the page on the way", p.errors[p.offline:] == [], p.errors[p.offline:])
    p.close()

    # ---- the quote on the query box
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
    p.page.evaluate("([reply, ms]) => { window.__reply = reply; window.__ms = ms; }", ["None of the three.", 0])
    p.page.keyboard.type("Which of these plots flooded?")
    p.page.keyboard.press("Control+Enter")
    p.page.wait_for_timeout(400)
    n = p.notes()
    check("... sent from the keyboard: the words go as they were selected, the passage as the tab's text has it, marked through its three paragraphs with one note under the last",
          len(p.asked()) == 1 and p.asked()[0]["quote"] == passage and p.asked()[0]["passage"] == "".join(m[1] for m in n["marks"]) and p.sent() == []
          and [m[1] for m in n["marks"]] == [l for l in passage.split("\n") if l.strip()] and len(n["notes"]) == 1 and n["notes"][0]["before"] == "P", (p.asked(), n))
    p.close()

    p = Page(browser)
    s = p.select()
    s = p.click(s["ask"])
    s = p.click(s["quote"]["remove"])
    gone = (s["quote"]["on"], s["focus"])
    p.page.keyboard.type(QUESTION)
    p.page.click("#submitQuery")
    p.page.wait_for_timeout(300)
    check("the quote's × takes it off and leaves the cursor in the box: the question typed then is one for an analysis, and goes alone",
          gone == (False, "queryInput") and [x["query"] for x in p.sent()] == [QUESTION] and p.asked() == [], (gone, p.sent(), p.asked()))
    p.close()

    p = Page(browser)
    s = p.select()
    p.click(s["ask"])
    p.page.click("#submitQuery")
    p.page.wait_for_timeout(300)
    s = p.state()
    check("a quote with no question typed is not sent, and stays on the box", p.sent() == [] and p.asked() == [] and s["quote"]["on"] and p.notes()["marks"] == [], (p.sent(), s))
    p.page.evaluate("document.getElementById('queryInput').value = 'What does the plot show?'; handleQuerySubmit({ image: 'AAAA' });")
    p.page.wait_for_timeout(300)
    s = p.state()
    check("a plot's own question takes the box as it always did - an analysis, without the passage - and the quote leaves: an analysis has begun, and the passage was another one's",
          [(x["query"], x.get("image")) for x in p.sent()] == [("What does the plot show?", "AAAA")] and p.asked() == [] and s["box_text"] == "" and not s["quote"]["on"], (p.sent(), s))
    p.close()

    p = Page(browser)
    p.page.evaluate("() => { window.__framed = []; window.ArchitectUI.isOn = () => true; window.ArchitectUI.open = q => { window.__framed.push(q); }; }")
    s = p.select()
    p.ask(QUESTION, "The range crosses zero.")
    s, n = p.state(), p.notes()
    check("with the Pathfinder on, a question about a passage is still explained where the passage stands: no brief opens, no analysis starts",
          p.page.evaluate("window.__framed") == [] and p.sent() == [] and len(p.asked()) == 1 and s["box_text"] == "" and not s["quote"]["on"] and n["marks"] == [["0", PHRASE, "answer", False]]
          and n["notes"][0]["asked"][0]["a"] == "The range crosses zero.", (p.page.evaluate("window.__framed"), s, n))
    s = p.select("Plot 2: regime C on sand")
    p.click(s["ask"])
    quoted = p.state()["quote"]["on"]
    p.page.evaluate("responses.push({ chain_id: 8, thread_id: 3, status: 'running', queryText: 'Another question', tabContent: '', contentOutput: '', streamOutput: '', taskContents: {} }); "
                    "currentResponseIndex = responses.length - 1; document.querySelector('#content-answer .markdown-content').insertAdjacentHTML('beforeend', '<p>a new analysis writes here</p>');")
    p.page.wait_for_timeout(300)
    s, n = p.state(), p.notes()
    check("another analysis on screen: the quote taken from the first leaves the query box, and none of the first one's marks is drawn", quoted and not s["quote"]["on"] and n["marks"] == [] and n["notes"] == [], (quoted, s, n))
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
