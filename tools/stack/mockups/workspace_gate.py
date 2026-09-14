"""Mockups of the workspace gate, rendered in the REAL page against the local stack.

    python3 tools/stack/mockups/workspace_gate.py --out /tmp/gate

Every state is injected markup + workspace_gate.css on the live page (no app code is changed).
"""
import argparse
import os
import sys
import json

HERE = os.path.dirname(os.path.abspath(__file__))
STACK = os.path.dirname(HERE)
sys.path[:0] = [STACK, os.path.join(STACK, "browser")]
import vendor  # noqa: E402
from stack import Stack, DEFAULT_WORKDIR  # noqa: E402
from browse import open_page  # noqa: E402

CSS = open(os.path.join(HERE, "workspace_gate.css"), encoding="utf-8").read()
TICK = '<svg viewBox="0 0 24 24"><polyline points="20 6 9 17 4 12"/></svg>'
CROSS = '<svg viewBox="0 0 24 24"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>'


def card_a(line, note="", meta="", state=""):
    icon = TICK if state == "ws-ready" else (CROSS if state == "ws-failed" else "")
    return (f'<div class="ws-card ui-dlg sm {state}" role="dialog" aria-modal="true" aria-live="polite">'
            f'<div class="ws-ring">{icon}</div><div class="ws-title">Setting up your workspace</div>'
            f'<div class="ws-line">{line}</div>' + (f'<div class="ws-note">{note}</div>' if note else "") +
            (f'<div class="ws-meta">{meta}</div>' if meta else "") + '</div>')


def card_b(rows, note="", meta="", title="Setting up your workspace"):
    lis = "".join(f'<li class="{cls}"><span class="dot"></span>{label}<em>{tag}</em></li>' for cls, label, tag in rows)
    return (f'<div class="ws-card ui-dlg sm" role="dialog" aria-modal="true" aria-live="polite">'
            f'<div class="ws-logo">BambooAI</div><div class="ws-title">{title}</div><ul class="ws-steps">{lis}</ul>'
            + (f'<div class="ws-note">{note}</div>' if note else "") + (f'<div class="ws-meta">{meta}</div>' if meta else "") + '</div>')


def card_c(line, meta=""):
    return (f'<div class="ws-card ui-dlg sm" role="dialog" aria-modal="true" aria-live="polite">'
            f'<div class="ws-title">Setting up your workspace</div><div class="ws-bar"><i></i></div>'
            f'<div class="ws-line">{line}</div>' + (f'<div class="ws-meta">{meta}</div>' if meta else "") + '</div>')


NOTE_LONG = "A fresh analysis environment takes up to two minutes the first time; after that it is reused."


def pill(text, dots, state="", caption=""):
    """text: list of segments (str or ('dim', str)); dots: 4 chars of d/b/./f (done/busy/pending/fail)."""
    segs = []
    for t in text:
        segs.append(f'<span class="dim">{t[1]}</span>' if isinstance(t, tuple) else t)
    html = '<span class="sep">·</span>'.join(segs)
    icon = TICK if state == "ready" else ""
    ds = "".join(f'<i class="{ {"d": "done", "b": "busy", "f": "fail"}.get(c, "") }"></i>' for c in dots)
    return (f'<div class="ws-pill-wrap"><div class="ws-pill {state}" role="status" aria-live="polite">'
            f'<span class="ws-ring">{icon}</span><span class="ws-text">{html}</span><span class="ws-dots">{ds}</span></div>'
            + (f'<div class="ws-caption">{caption}</div>' if caption else "") + '</div>')
STATES = {
    # reference: what exists today
    "ref_overlay_today": dict(js="showLoadingOverlay('Starting new workflow...')"),
    "ref_sentence_today": dict(js="document.getElementById('streamOutput').innerHTML = '<div>New workflow started. Ready for your query.</div>'"),
    # A: the ring
    "A1_signing_in": dict(card=card_a("Signing you in"), dark=True),
    "A2_environment": dict(card=card_a("Starting the analysis environment", NOTE_LONG, "0:14"), chip="spawning"),
    "A3_ready": dict(card=card_a("Ready", state="ws-ready"), chip="ready"),
    "A4_failed": dict(card=card_a("The analysis environment did not start", "Use Restart on the executor chip, or refresh the page.", state="ws-failed"), chip="failed"),
    # B: the stages
    "B1_signing_in": dict(card=card_b([("busy", "Signing you in", "…"), ("", "Preparing the workspace", ""), ("", "Analysis environment", "")]), dark=True),
    "B2_environment": dict(card=card_b([("done", "Signed in", "ok"), ("done", "Workspace prepared", "ok"), ("busy", "Analysis environment", "starting")], NOTE_LONG, "0:14"), chip="spawning"),
    "B3_ready": dict(card=card_b([("done", "Signed in", "ok"), ("done", "Workspace prepared", "ok"), ("done", "Analysis environment", "ready")], title="Your workspace is ready"), chip="ready"),
    "B4_failed": dict(card=card_b([("done", "Signed in", "ok"), ("done", "Workspace prepared", "ok"), ("fail", "Analysis environment", "did not start")],
                                  "Use Restart on the executor chip, or refresh the page.", title="Setting up your workspace"), chip="failed"),
    # C: the line
    "C2_environment": dict(card=card_c("Starting the analysis environment", "0:14"), chip="spawning"),
    # P: the pill
    "P1_signing_in": dict(card=pill(["Signing you in", ("dim", "3 s")], "b..."), dark=True),
    "P2_workspace": dict(card=pill(["Preparing your workspace", ("dim", "5 s")], "db.."), chip="offline"),
    "P3_executor": dict(card=pill(["Starting your executor", ("dim", "pro"), ("dim", "12 s")], "ddb."), chip="spawning"),
    "P4_ready": dict(card=pill(["Executor ready", ("dim", "pro"), ("dim", "14 s")], "dddd", state="ready"), chip="ready"),
    "P5_long_wait": dict(card=pill(["Starting your executor", ("dim", "pro"), ("dim", "1:05")], "ddb.",
                                   caption="A fresh executor takes up to two minutes the first time; after that it is reused."), chip="spawning"),
    "P6_failed": dict(card=pill(["Executor did not start", ("dim", "pro"), ("dim", "2:00")], "ddf.", state="failed",
                                caption="Use Restart on the executor chip, or refresh the page."), chip="failed"),
    "P7_login_no_container": dict(card=pill(["Your executor starts with your first dataset"], "dd..", state="ready"), chip="offline"),
    # the pane after the sentence is retired: nothing, or a quiet hint
    "E1_pane_blank": dict(js="document.getElementById('streamOutput').innerHTML = ''"),
    "E2_pane_hint": dict(js="document.getElementById('streamOutput').innerHTML = '<div class=\"sp-empty\">Attach a dataset with the paperclip, or ask a question. <kbd>Enter</kbd> sends.</div>'"),
}


def apply(page, spec):
    page.evaluate("""(css) => { let s = document.getElementById('ws-mock-css'); if (!s) { s = document.createElement('style'); s.id = 'ws-mock-css'; document.head.appendChild(s); } s.textContent = css;
                    document.querySelectorAll('#workspaceGate, .loading-overlay').forEach(e => e.remove());
                    const c = document.querySelector('.container'); if (c) c.style.display = ''; }""", CSS)
    if spec.get("chip"):
        page.evaluate("""(st) => { const el = document.getElementById('containerStatus'); const t = document.getElementById('containerStatusText');
                         if (el) el.className = 'container-status status-' + st; if (t) t.textContent = {ready:'Ready', spawning:'Starting', failed:'Failed'}[st] || st; }""", spec["chip"])
    if spec.get("card"):
        page.evaluate("""([html, dark]) => { const g = document.createElement('div'); g.id = 'workspaceGate'; g.className = 'modal ui-modal ws-gate' + (dark ? ' on-dark' : '');
                         g.innerHTML = html; document.body.appendChild(g); if (dark) { const c = document.querySelector('.container'); if (c) c.style.display = 'none'; } }""",
                      [spec["card"], bool(spec.get("dark"))])
    if spec.get("js"):
        page.evaluate(spec["js"])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    ap.add_argument("--workdir", default=DEFAULT_WORKDIR)
    ap.add_argument("--attach", action="store_true")
    ap.add_argument("--light", nargs="*", default=["A2_environment", "B2_environment", "C2_environment", "E2_pane_hint", "P3_executor"], help="states also rendered in the light theme")
    ap.add_argument("--only", nargs="*", default=None)
    a = ap.parse_args()
    from playwright.sync_api import sync_playwright
    vendor.prepare(fetch=False)
    os.makedirs(a.out, exist_ok=True)
    if a.attach:
        st = json.load(open(os.path.join(a.workdir, "stack.json"))); stack = None; app_url = f"http://127.0.0.1:{st['ports']['app']}"
    else:
        stack = Stack(workdir=a.workdir, fresh=True, auto_ports=True).start(); app_url = stack.app_url
    try:
        with sync_playwright() as pw:
            b, page, logs = open_page(pw, app_url)
            page.goto(app_url); page.wait_for_selector("#queryInput", state="visible", timeout=60000); page.app_ready(); page.wait_for_timeout(600)
            n = 0
            for name, spec in STATES.items():
                if a.only and name not in a.only:
                    continue
                for theme in (["dark", "light"] if name in a.light else ["dark"]):
                    page.evaluate(f"document.documentElement.setAttribute('data-theme','{theme}')")
                    apply(page, spec)
                    page.wait_for_timeout(350)
                    n += 1
                    page.screenshot(path=os.path.join(a.out, f"{n:02d}_{name}_{theme}.png"))
                    page.evaluate("""() => { document.querySelectorAll('#workspaceGate, .loading-overlay').forEach(e => e.remove()); const c = document.querySelector('.container'); if (c) c.style.display = '';
                                            document.getElementById('streamOutput').innerHTML = ''; const el = document.getElementById('containerStatus'); if (el) { el.className = 'container-status status-offline'; document.getElementById('containerStatusText').textContent = 'Offline'; } }""")
            b.close()
            print(f"{n} mockups in {a.out}")
    finally:
        if stack is not None:
            stack.stop()


if __name__ == "__main__":
    main()
