"""The start-up flows through the real page: login, New workflow, refresh, and a failing start.

    python3 tools/stack/flows.py --out /tmp/flows [--delay 6]

Each flow records the workspace gate's transitions (stage, seconds, whether the page is inert),
whether the composer could be used before the gate released, how many times /new_conversation
was called, and screenshots the pill mid-way and at Ready. A failing start (the fake orchestrator
refusing to spawn) is run on a second stack. Exit 1 on any failed check.
"""
import argparse
import json
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path[:0] = [HERE, os.path.join(HERE, "browser")]
import vendor  # noqa: E402
from stack import Stack  # noqa: E402
from browse import open_page  # noqa: E402

results = []


def check(name, cond, detail=""):
    results.append((name, bool(cond)))
    print(("  ok   " if cond else "  FAIL ") + name + ("" if cond else f"  <- {str(detail)[:300]}"))


SAMPLER = """
() => { if (!window.__gateLog) { window.__gateLog = []; window.__gateTimer = setInterval(() => {
          const g = document.getElementById('workspaceGate'); if (!g || !window.WorkspaceGate || !document.querySelector('.container')) return;
          const st = WorkspaceGate.state();
          const vis = g && !g.classList.contains('hidden') && !g.hidden && getComputedStyle(g).display !== 'none';
          const txt = g ? (g.querySelector('.ws-text') || {}).textContent : '';
          const inert = !!(document.querySelector('.container') && document.querySelector('.container').inert);
          const last = window.__gateLog[window.__gateLog.length - 1];
          const rec = { t: Math.round(performance.now()), stage: st && st.stage, failed: st && st.failed, released: !st.open, visible: !!vis, inert, text: txt };
          if (!last || JSON.stringify([last.stage, last.failed, last.released, last.visible, last.inert]) !== JSON.stringify([rec.stage, rec.failed, rec.released, rec.visible, rec.inert])) window.__gateLog.push(rec);
        }, 100); } }
"""


def install_sampler(page):
    page.add_init_script(SAMPLER + ";(" + SAMPLER + ")();")


def gate_log(page):
    try:
        return page.evaluate("window.__gateLog || []")
    except Exception:                                   # noqa: BLE001
        return []


def wait_text(page, selector, text, timeout=120000):
    page.wait_for_function("([sel, t]) => [...document.querySelectorAll(sel)].some(e => e.textContent.includes(t))", arg=[selector, text], timeout=timeout)


def wait_released(page, timeout=90000):
    page.wait_for_function("() => window.WorkspaceGate && WorkspaceGate.state().open === false", timeout=timeout)


def try_type(page):
    """Can the composer be used right now? (it must not be, while the gate is up)"""
    return page.evaluate("""() => { const q = document.getElementById('queryInput'); if (!q) return 'no composer';
        try { q.focus(); } catch (e) {} const focused = document.activeElement === q;
        const el = document.elementFromPoint(q.getBoundingClientRect().left + 20, q.getBoundingClientRect().top + 10);
        return { focused, hit: el ? (el.id || el.className || el.tagName) : null }; }""")


class Counters:
    """Per-flow: document navigations, the start-up calls, the console's [workspace]/[gate] lines."""
    def __init__(self, page):
        self.navs, self.reqs, self.console = [], [], []
        page.on("load", lambda: self.navs.append(page.url))                     # document loads only (replaceState is not one)
        page.on("request", lambda r: self.reqs.append(r.method + " " + r.url.split("?")[0].rsplit("/", 1)[-1])
                 if r.url.split("?")[0].endswith(("/api/user/initialize", "/new_conversation", "/query")) else None)
        page.on("console", lambda m: self.console.append(f"{m.type}: {m.text}") if m.text.startswith(("[workspace]", "[gate]")) or m.type == "error" else None)

    def reset(self):
        self.navs, self.reqs, self.console = [], [], []

    def count(self, what):
        return sum(1 for r in self.reqs if what in r)


def flow(page, name, action, out, shots_at=(0.4, 2.5), timeout=90000, counters=None):
    page.evaluate("window.__gateLog = []") if page.url != "about:blank" else None
    if counters:
        counters.reset()
    t0 = time.time()
    action()
    for i, at in enumerate(shots_at):
        remaining = at - (time.time() - t0)
        if remaining > 0:
            page.wait_for_timeout(int(remaining * 1000))
        try:
            page.screenshot(path=os.path.join(out, f"{name}_{i + 1}_{int(at * 10):02d}.png"))
        except Exception:                               # noqa: BLE001
            pass
    # the reload may have happened: the sampler re-arms on the new page via the init script
    wait_released(page, timeout)
    page.wait_for_timeout(200)
    page.screenshot(path=os.path.join(out, f"{name}_ready.png"))
    page.wait_for_timeout(1300)
    page.screenshot(path=os.path.join(out, f"{name}_after.png"))
    if counters:
        with open(os.path.join(out, f"console_{name}.txt"), "w") as fh:
            fh.write("\n".join(counters.console))
    return time.time() - t0


def stages(log):
    """The gate's stage sequence, repeats collapsed."""
    out = []
    for r in log:
        if r.get("stage") and (not out or out[-1] != r["stage"]):
            out.append(r["stage"])
    return out


class _NoStack:
    """A stand-in context for flows that do not apply to an edition."""
    def __enter__(self): return None
    def __exit__(self, *a): return False


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    ap.add_argument("--delay", type=float, default=6.0, help="seconds the fake orchestrator takes to start an executor")
    ap.add_argument("--edition", choices=("hosted", "local"), default="hosted")
    a = ap.parse_args()
    from playwright.sync_api import sync_playwright
    vendor.prepare(fetch=bool(os.environ.get("CI")))
    os.makedirs(a.out, exist_ok=True)
    os.environ["STACK_SPAWN_DELAY"] = str(a.delay)
    os.environ.pop("STACK_SPAWN_FAIL", None)

    with Stack(workdir=os.path.join("/tmp", "bamboo_flows"), fresh=True, auto_ports=True, edition=a.edition) as st:
        with sync_playwright() as pw:
            b, page, logs = open_page(pw, st.app_url)
            install_sampler(page)
            app = st.app_url
            ctr = Counters(page)

            # ---- 1. login: a fresh navigation - ONE load (v63)
            calls_before = len([c for c in st.orchestrator_calls() if c["kind"] == "spawn"])
            took = flow(page, "login", lambda: page.goto(app), a.out, shots_at=(0.5, 3.0), counters=ctr)
            log = gate_log(page)
            seq = stages(log)
            check("login: the pill was visible from the first sample", log and log[0]["visible"], log[:2])
            check("login: ONE document load - no reload into ?new=true", len(ctr.navs) == 1 and "new=true" not in page.url, (ctr.navs, page.url))
            check("login: the initialise call once, /new_conversation once", ctr.count("initialize") == 1 and ctr.count("new_conversation") == 1, ctr.reqs)
            check("login: each stage once, in order (the console shows the workspace stage even when too quick to sample)",
                  seq[-2:] == ["executor", "ready"] and len(seq) == len(set(seq)) and any("stage workspace" in c for c in ctr.console), (seq, ctr.console[:3]))
            check("login: the page was inert until the gate released", all(r["inert"] for r in log if not r["released"]) and not log[-1]["inert"], log)
            spawns = [c for c in st.orchestrator_calls() if c["kind"] == "spawn"]
            check("login: the executor was started (a spawn reached the orchestrator)", len(spawns) > calls_before, spawns)
            check(f"login: released in {took:.1f}s with a {a.delay:.0f}s start delay", took < a.delay + 20, took)
            typing = try_type(page)
            check("after release: the composer takes focus", typing.get("focused") is True, typing)
            check("login: the console carries the [workspace] log with the server reset timing",
                  any("server reset done" in c for c in ctr.console) and any("saved responses cleared; verified empty: true" in c for c in ctr.console), ctr.console[:8])

            # ---- 2. New workflow from the rail: the server reset on this page, then ONE reload
            page.evaluate("window.__gateLog = []")
            took = flow(page, "new_workflow", lambda: page.click("#railNewButton"), a.out, shots_at=(0.3, 1.5), counters=ctr)
            log = gate_log(page)
            check("New workflow: the gate showed 'Starting your executor' on the old page before the reload",
                  any(r["stage"] == "executor" and r["visible"] for r in log) or any("executor" in (r["text"] or "").lower() for r in log), log[:6])
            check("New workflow: one reload into ?new=true, /new_conversation once, no second reset on the reloaded page",
                  len(ctr.navs) == 1 and any("new=true" in n for n in ctr.navs) and ctr.count("new_conversation") == 1 and ctr.count("initialize") == 1, (ctr.navs, ctr.reqs))
            check("New workflow: released at ready, page usable", log[-1]["released"] and not log[-1]["inert"], log[-1])

            # ---- 3. refresh: ONE load - after a real run, so the browser holds saved chains that must not survive
            import harness_models
            q1 = harness_models.load("field_trial").QUESTIONS[0]
            page.set_input_files("#primaryFile", st.dataset)
            page.wait_for_selector(".primary-dataset-pill", timeout=60000)
            page.fill("#queryInput", q1)
            page.click("#submitQuery")
            wait_text(page, ".sp-done", "Run complete", 180000)
            page.wait_for_timeout(800)
            saved = page.evaluate("async () => { const r = await localforage.getItem('responses'); return r ? r.length : 0; }")
            check("before the refresh: the run's chain is in the browser's saved responses (localforage)", saved >= 1, saved)
            page.evaluate("window.__gateLog = []")
            took = flow(page, "refresh", lambda: page.reload(), a.out, shots_at=(0.4, 2.0), counters=ctr)
            after = page.evaluate("async () => ({ store: await localforage.getItem('responses'), responses: (typeof responses !== 'undefined') ? responses.length : null,"
                                  " pane: document.getElementById('streamOutput').innerText.trim(), chainPos: document.getElementById('chainPosition').textContent.trim(),"
                                  " pills: document.querySelectorAll('.dataset-status-pill').length })")
            check("after the refresh: localforage holds no saved responses, the page has no chains, an empty pane, no chain position, no dataset pill",
                  after["store"] in (None, []) and after["responses"] == 0 and after["pane"] == "" and after["chainPos"] == "" and after["pills"] == 0, after)
            log = gate_log(page)
            seq = stages(log)
            check("refresh: ONE document load, the initialise call once, /new_conversation once, no ?new=true",
                  len(ctr.navs) == 1 and ctr.count("initialize") == 1 and ctr.count("new_conversation") == 1 and "new=true" not in page.url, (ctr.navs, ctr.reqs))
            check("refresh: each stage once, in order (the console shows the workspace stage even when too quick to sample)",
                  seq[-2:] == ["executor", "ready"] and len(seq) == len(set(seq)) and any("stage workspace" in c for c in ctr.console), (seq, ctr.console[:3]))
            check("refresh: the pill was up and the page inert until ready", any(r["inert"] for r in log) and log[-1]["released"], log[:4])
            check("refresh: the workspace start saw a 'reload' navigation", any("fresh load (reload)" in c for c in ctr.console), ctr.console[:4])
            page.evaluate("""() => { document.getElementById('queryInput').focus(); }""")
            check("refresh: the sentence 'New workflow started' is gone from the pane", "New workflow started" not in page.inner_text("#streamOutput"))
            errs = [l for l in logs if l.startswith(("[pageerror]", "[http 5"))]
            check("no page errors and no 5xx across the three flows", not errs, errs[:3])
            b.close()

    # ---- 4. a first visit (no session cookie) and the page after a logout (signed out), on the same stack (hosted edition only)
    with (Stack(workdir=os.path.join("/tmp", "bamboo_flows_auth"), fresh=True, auto_ports=True) if a.edition == "hosted" else _NoStack()) as st:
        with (sync_playwright() if st is not None else _NoStack()) as pw:
          if st is None:
            pass
          else:
              from browse import SIGNED_OUT_COOKIE
              b, page, logs = open_page(pw, st.app_url, cookies=[])
              install_sampler(page)
              ctr = Counters(page)
              page.goto(st.app_url)
              page.wait_for_function("() => window.WorkspaceGate && WorkspaceGate.state().released === true && WorkspaceGate.state().open === false", timeout=90000)
              log = gate_log(page)
              check("first visit (no session cookie): the pill never showed 'Signing you in' - it waited, hidden, for the sign-in to complete",
                    all(r["stage"] != "signin" for r in log if r["visible"]) and any("no session hint" in c for c in ctr.console), log[:2])
              seq = stages(log)
              check("first visit: once the shell appears the pill runs workspace -> executor -> ready as usual", seq[-3:] == ["workspace", "executor", "ready"], seq)
              check("first visit: the console says why the pill waited", any("no session hint" in c for c in ctr.console), ctr.console[:3])
              b.close()

              b, page, logs = open_page(pw, st.app_url, cookies=[SIGNED_OUT_COOKIE])
              install_sampler(page)
              page.goto(st.app_url)
              page.wait_for_selector("#authScreen", state="visible", timeout=60000)
              page.wait_for_timeout(800)
              page.screenshot(path=os.path.join(a.out, "signed_out_login_screen.png"))
              gate_vis = page.evaluate("() => { const g = document.getElementById('workspaceGate'); return !!g && !g.classList.contains('hidden') && getComputedStyle(g).display !== 'none'; }")
              btn = page.evaluate("() => { const b = document.querySelector('#authScreen button'); return b ? (b.getClientRects().length > 0) : false; }")
              check("signed out (after a logout): the sign-in screen shows, the pill does not, and the Sign In button is usable", not gate_vis and btn, (gate_vis, btn))
              st_ = page.evaluate("WorkspaceGate.state()")
              check("signed out: the gate never showed and is not blocking (open=false, stage still signin)", st_["open"] is False and st_["stage"] == "signin", st_)
              b.close()

    # ---- 5. a failing start on a second stack
    os.environ["STACK_SPAWN_FAIL"] = "1"
    with Stack(workdir=os.path.join("/tmp", "bamboo_flows_fail"), fresh=True, auto_ports=True, edition=a.edition) as st:
        with sync_playwright() as pw:
            b, page, logs = open_page(pw, st.app_url)
            install_sampler(page)
            page.on("dialog", lambda d: d.accept())                  # the existing alert on a failed start
            page.goto(st.app_url)
            page.wait_for_function("() => window.WorkspaceGate && WorkspaceGate.state().failed === true", timeout=60000)
            page.wait_for_timeout(500)
            page.screenshot(path=os.path.join(a.out, "failed_start.png"))
            st_ = page.evaluate("WorkspaceGate.state()")
            txt = page.inner_text("#workspaceGate")
            check("failing start: the pill shows the failed state and the Refresh action", st_["failed"] and "did not start" in txt and "Refresh" in txt, txt)
            check("failing start: the page is no longer inert (the chip's Restart is reachable)", not page.evaluate("document.querySelector('.container').inert"))
            b.close()
    os.environ.pop("STACK_SPAWN_FAIL", None)

    n_fail = sum(1 for _, ok in results if not ok)
    print(f"{len(results) - n_fail} passed, {n_fail} failed; screenshots in {a.out}")
    sys.exit(1 if n_fail else 0)


if __name__ == "__main__":
    main()
