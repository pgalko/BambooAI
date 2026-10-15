"""The Intervals and SweatStack dialogs' date inputs, in a real Chromium (2026-10-15): a date being typed passes through
'' and through partial values, and the dialogs' change handlers clamped start and end to each other on every one of
them - typing an end date snapped it to the start, after which neither could be changed (Palo, the dev box). The
handlers are gone; the order is checked at Load. And the plan's limit, which used to be fetched and written over
both dates at every opening, is fetched once and written only into an empty input.

    python3 tests/e2e/test_date_inputs.py      # a few seconds; skips (exit 0) when playwright is not installed

The dialogs' own functions run in the page (cut from the two scripts), over the same inputs the dialogs have, with a
stand-in for the limits route that answers late.
"""
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
try:
    from playwright.sync_api import sync_playwright
except Exception:                                          # noqa: BLE001
    print("playwright not installed: the date inputs suite is skipped")
    sys.exit(0)

results = []


def check(name, cond, detail=""):
    results.append((name, bool(cond)))
    print(("  ok   " if cond else "  FAIL ") + name + ("" if cond else f"  <- {str(detail)[:500]}"))


def cut(src, start_pat, end_pat):
    """The source from the first line matching start_pat up to (not including) the first line matching end_pat after it."""
    m = re.search(start_pat, src, re.M)
    assert m, start_pat
    n = re.search(end_pat, src[m.end():], re.M)
    return src[m.start():m.end() + (n.start() if n else len(src))]


def read(*p):
    return open(os.path.join(ROOT, "web_app", "static", "js", *p), encoding="utf-8").read()


core, ivl, sws = read("core.js"), read("integrations", "intervals.js"), read("integrations", "sweatstack.js")
pieces = [cut(core, r"^function localIsoDay\(d\) \{", r"^\}\n") + "}\n",
          cut(ivl, r"^let intervalsLimitsPromise = null;", r"^// The context's report"),
          cut(ivl, r"^function initializeIntervalsDatePickers\(\) \{", r"^\}\n") + "}\n",
          cut(sws, r"^let sweatstackLimitsPromise = null;", r"^//-{10,}"),
          cut(sws, r"^function initializeDatePickers\(\) \{", r"^\}\n") + "}\n"]
SCRIPT = "\n".join(pieces)
HTML = """<!doctype html><html><body>
<input type="date" id="intervalsStartDate"><input type="date" id="intervalsEndDate">
<input type="date" id="startDate"><input type="date" id="endDate">
<script>
window.calls = [];
window.authService = { fetch: (url) => { window.calls.push(url); return new Promise(res => setTimeout(() => res({ json: async () => ({ max_days: 365 }) }), 400)); } };
</script></body></html>"""


def typed(page, sel, keys):
    """Type a date into a Chromium date input the way a person does: the segments in order, from the first (a fresh
    focus starts on the month segment; a click lands on whichever segment is under it, and Home does not move)."""
    page.evaluate("() => { if (document.activeElement) document.activeElement.blur(); }")   # a fresh focus starts on the month segment
    page.focus(sel)
    for k in keys:
        page.keyboard.type(k)


def main():
    with sync_playwright() as p:
        b = p.chromium.launch()
        page = b.new_page(locale="en-US")
        page.set_content(HTML)
        page.add_script_tag(content=SCRIPT)
        # the old trap, for the record: the handlers the dialogs had, over a spare pair of inputs
        page.evaluate("""() => { const s = document.createElement('input'), e = document.createElement('input'); s.type = 'date'; e.type = 'date'; s.id = 'os'; e.id = 'oe'; document.body.append(s, e);
            s.value = '2025-10-17'; e.value = '2026-10-15';
            e.addEventListener('change', function() { if (s.value && this.value < s.value) { this.value = s.value; } }); }""")
        typed(page, "#oe", "09172026")
        check("the old handler, kept aside for the record: typing an end date into a Chromium date input snaps it to the start (the value passes through '' and partial dates, each read as out of order)",
              page.input_value("#oe") == "2025-10-17", page.input_value("#oe"))

        # the dialogs now: the first opening, the person typing before the limits answer lands
        page.evaluate("() => initializeIntervalsDatePickers()")
        typed(page, "#intervalsStartDate", "10172025")
        page.wait_for_timeout(700)
        v = page.evaluate("() => ({ s: document.getElementById('intervalsStartDate').value, e: document.getElementById('intervalsEndDate').value, smin: document.getElementById('intervalsStartDate').min, smax: document.getElementById('intervalsStartDate').max, emin: document.getElementById('intervalsEndDate').min, emax: document.getElementById('intervalsEndDate').max, calls: window.calls.length })")
        today = page.evaluate("() => localIsoDay(new Date())")
        lo = page.evaluate("() => { const d = new Date(); d.setDate(d.getDate() - 365); return localIsoDay(d); }")
        check("Intervals: a start typed before the limits answer landed stays; the end gets the default (today); the bounds are the plan's window on both inputs; one request",
              v["s"] == "2025-10-17" and v["e"] == today and v["smin"] == lo and v["smax"] == today and v["emin"] == lo and v["emax"] == today and v["calls"] == 1, v)
        typed(page, "#intervalsEndDate", "09172026")
        v2 = page.evaluate("() => ({ s: document.getElementById('intervalsStartDate').value, e: document.getElementById('intervalsEndDate').value })")
        check("Intervals: an end date typed in sticks as typed, the start untouched (no clamp)", v2 == {"s": "2025-10-17", "e": "2026-09-17"}, v2)
        typed(page, "#intervalsEndDate", "01012025")
        v3 = page.evaluate("() => ({ s: document.getElementById('intervalsStartDate').value, e: document.getElementById('intervalsEndDate').value })")
        check("Intervals: an end before the start is left as typed - nothing rewrites a date while it is typed; Load is where the order is refused", v3 == {"s": "2025-10-17", "e": "2025-01-01"}, v3)
        typed(page, "#intervalsEndDate", "09172026")
        page.evaluate("() => initializeIntervalsDatePickers()")
        page.wait_for_timeout(100)
        v4 = page.evaluate("() => ({ s: document.getElementById('intervalsStartDate').value, e: document.getElementById('intervalsEndDate').value, calls: window.calls.length })")
        check("Intervals: the dialog opened again keeps the window typed last time and asks for the limits no second time", v4 == {"s": "2025-10-17", "e": "2026-09-17", "calls": 1}, v4)

        # SweatStack, the same way
        page.evaluate("() => initializeDatePickers()")
        page.wait_for_timeout(700)
        typed(page, "#endDate", "09172026")
        typed(page, "#startDate", "10172025")
        w = page.evaluate("() => ({ s: document.getElementById('startDate').value, e: document.getElementById('endDate').value, smin: document.getElementById('startDate').min, emax: document.getElementById('endDate').max, calls: window.calls.length })")
        check("SweatStack: both dates as typed, the bounds set, one request of its own", w == {"s": "2025-10-17", "e": "2026-09-17", "smin": lo, "emax": today, "calls": 2}, w)
        page.evaluate("() => initializeDatePickers()")
        page.wait_for_timeout(100)
        w2 = page.evaluate("() => ({ s: document.getElementById('startDate').value, e: document.getElementById('endDate').value, calls: window.calls.length })")
        check("SweatStack: opened again, the window stays", w2 == {"s": "2025-10-17", "e": "2026-09-17", "calls": 2}, w2)
        b.close()

    # the scripts: no clamp left, the order checked at Load, both dates required
    check("neither dialog clamps a date on change any more; both refuse Load without both dates and with the start not before the end",
          "this.value = endDateInput.value" not in ivl and "this.value = startDateInput.value" not in ivl and "this.value = endDateInput.value" not in sws and "this.value = startDateInput.value" not in sws
          and "Please pick both dates." in ivl and "the start before the end" in ivl and "Please pick both dates." in sws and "the start before the end" in sws)
    fails = [n for n, ok in results if not ok]
    print(f"\n{len(results) - len(fails)} passed, {len(fails)} failed")
    sys.exit(1 if fails else 0)


if __name__ == "__main__":
    main()
