"""The dataset chips' row in the top bar, in a real Chromium (2026-10-15): one row that takes the bar up to the chain
navigation and scrolls sideways when the chips outrun it - the row used to clip what did not fit, and a load with the
context already brings five files. The page's own CSS and the strip's own script (core.js pillStrip) over the top
bar's markup cut from index.html, at a laptop width.

    python3 tests/e2e/test_pill_strip.py      # a few seconds; skips (exit 0) when playwright is not installed
"""
import os
import re
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
try:
    from playwright.sync_api import sync_playwright
except Exception:                                          # noqa: BLE001
    print("playwright not installed: the pill strip suite is skipped")
    sys.exit(0)

results = []


def check(name, cond, detail=""):
    results.append((name, bool(cond)))
    print(("  ok   " if cond else "  FAIL ") + name + ("" if cond else f"  <- {str(detail)[:500]}"))


STATIC = os.path.join(ROOT, "web_app", "static")
html = open(os.path.join(ROOT, "web_app", "templates", "index.html"), encoding="utf-8", errors="replace").read()
m = re.search(r'<header class="topbar">.*?</header>', html, re.S)
topbar = m.group(0)
core = open(os.path.join(STATIC, "js", "core.js"), encoding="utf-8").read()
strip_js = re.search(r"^function pillStrip\(container\) \{.*?^\}\n", core, re.S | re.M).group(0)
css = "".join(f'<link rel="stylesheet" href="file://{os.path.join(STATIC, "css", n)}">' for n in ("tokens.css", "base.css", "styles.css", "components.css", "shell.css"))
PAGE = f"""<!doctype html><html><head><meta charset="utf-8">{css}</head><body><div class="container">{topbar}</div>
<script>{strip_js}
function pill(i, aux) {{ const d = document.createElement('div'); d.className = 'dataset-status-pill ' + (aux ? 'auxiliary-dataset-pill' : 'intervals-dataset-pill') + ' success'; d.id = 'p' + i;
  d.innerHTML = '<div class="dataset-pill-content clickable-pill-content"><span>' + (aux ? 'Auxiliary (activity_summary_20251017_to_20261015)' : 'Intervals ICU (364 days [W+S+C]) loaded') + '</span></div>'; return d; }}
pillStrip(document.getElementById('datasetStatusPillsContainer'));
</script></body></html>"""
path = os.path.join(tempfile.mkdtemp(prefix="bamboo_strip_"), "topbar.html")
open(path, "w", encoding="utf-8").write(PAGE)

with sync_playwright() as p:
    b = p.chromium.launch()
    page = b.new_page(viewport={"width": 1280, "height": 700})
    page.goto("file://" + path)
    page.evaluate("() => { const nav = document.querySelector('.topbar .tab-navigation'); nav.style.display = 'flex'; document.getElementById('chainPosition').textContent = 'run 2 of 3'; }")
    page.evaluate("() => { const c = document.getElementById('datasetStatusPillsContainer'); c.appendChild(pill(0, false)); c.appendChild(pill(1, true)); }")
    page.wait_for_timeout(150)
    few = page.evaluate("""() => { const c = document.getElementById('datasetStatusPillsContainer'), nav = document.querySelector('.topbar .tab-navigation'), bar = document.querySelector('.topbar');
        const r = c.getBoundingClientRect(), n = nav.getBoundingClientRect(), bb = bar.getBoundingClientRect();
        return { overflow: c.scrollWidth - c.clientWidth, cls: c.className, cRight: r.right, navLeft: n.left, navRight: n.right, barRight: bb.right, barH: bb.height, rows: new Set([...c.children].map(e => Math.round(e.getBoundingClientRect().top))).size }; }""")
    check("two chips: no overflow, no fade; the row reaches up to the chain navigation, which sits on its right inside the bar", few["overflow"] == 0 and "more-" not in few["cls"] and few["cRight"] <= few["navLeft"] and few["navRight"] <= few["barRight"] and few["rows"] == 1, few)
    page.evaluate("() => { const c = document.getElementById('datasetStatusPillsContainer'); for (let i = 2; i < 9; i++) c.appendChild(pill(i, true)); }")
    page.wait_for_timeout(900)                                                                     # the strip scrolls smoothly
    many = page.evaluate("""() => { const c = document.getElementById('datasetStatusPillsContainer'), nav = document.querySelector('.topbar .tab-navigation'), bar = document.querySelector('.topbar');
        const r = c.getBoundingClientRect(), n = nav.getBoundingClientRect(), bb = bar.getBoundingClientRect();
        return { overflow: c.scrollWidth - c.clientWidth, cls: c.className, scrollLeft: c.scrollLeft, cRight: r.right, navLeft: n.left, navRight: n.right, barRight: bb.right, barH: bb.height, rows: new Set([...c.children].map(e => Math.round(e.getBoundingClientRect().top))).size,
                 lastVisible: document.getElementById('p8').getBoundingClientRect().left < r.right }; }""")
    check("nine chips: the row overflows and stays one row at the bar's height; the chain navigation stays in place and in view; the last chip was brought into view (the strip scrolled to it) and the left fade says there is more behind",
          many["overflow"] > 100 and many["rows"] == 1 and many["barH"] < 60 and many["cRight"] <= many["navLeft"] and many["navRight"] <= many["barRight"] and many["lastVisible"] and many["scrollLeft"] > 0 and "more-left" in many["cls"], many)
    page.evaluate("() => { const c = document.getElementById('datasetStatusPillsContainer'); c.scrollTo({ left: 0, behavior: 'instant' }); }")
    page.wait_for_timeout(300)
    start = page.evaluate("() => { const c = document.getElementById('datasetStatusPillsContainer'); return { scrollLeft: c.scrollLeft, cls: c.className }; }")
    check("scrolled back to the start: the right fade only", start["scrollLeft"] == 0 and "more-right" in start["cls"] and "more-left" not in start["cls"], start)
    page.hover("#datasetStatusPillsContainer")
    page.mouse.wheel(0, 300)
    page.wait_for_timeout(400)
    wheeled = page.evaluate("() => { const c = document.getElementById('datasetStatusPillsContainer'); return { scrollLeft: c.scrollLeft, cls: c.className, pageY: window.scrollY }; }")
    check("a vertical wheel over the row scrolls it sideways (the page does not move); both fades while in the middle", wheeled["scrollLeft"] > 0 and wheeled["pageY"] == 0 and "more-left" in wheeled["cls"] and "more-right" in wheeled["cls"], wheeled)
    # at the wheel's own pace (2026-10-29): a gesture is many small ticks, and the row must move by their sum - with smooth scrolling
    # each tick restarted the glide from wherever the row was, so a gesture of 300 moved it a fraction of that ("too slow")
    page.evaluate("() => { const c = document.getElementById('datasetStatusPillsContainer'); c.scrollTo({ left: 0, behavior: 'instant' }); }")
    page.wait_for_timeout(200)
    for _ in range(10):
        page.mouse.wheel(0, 30)
    page.wait_for_timeout(500)
    burst = page.evaluate("() => { const c = document.getElementById('datasetStatusPillsContainer'); return { scrollLeft: c.scrollLeft, overflow: c.scrollWidth - c.clientWidth }; }")
    check("ten wheel ticks of 30 move the row by 300 - the gesture's whole distance, at its own pace", burst["overflow"] > 300 and 290 <= burst["scrollLeft"] <= 310, burst)
    b.close()

shell_css = open(os.path.join(STATIC, "css", "shell.css"), encoding="utf-8").read()
check("shell.css: the row's rules - no scrollbar shown, the fades, the chips never shrink, the spacer no longer takes the free width; no smooth scrolling on the row (the wheel sets its pace), and the script glides a new chip into view itself and moves by lines or pages when the wheel reports those",
      all(t in shell_css for t in ("scrollbar-width: none", ".more-right {", ".more-left {", "#datasetStatusPillsContainer > * { flex-shrink: 0; }", ".topbar .sp { flex: 0 0 6px; }")) and "scroll-behavior: smooth" not in shell_css.split("#datasetStatusPillsContainer {")[1].split("\n")[0]
      and "const unit = e.deltaMode === 1 ? 16 : e.deltaMode === 2 ? container.clientWidth : 1;" in strip_js and "container.scrollLeft += d * unit;" in strip_js and "added.scrollIntoView({ behavior: 'smooth', block: 'nearest', inline: 'nearest' })" in strip_js)
fails = [n for n, ok in results if not ok]
print(f"\n{len(results) - len(fails)} passed, {len(fails)} failed")
sys.exit(1 if fails else 0)
