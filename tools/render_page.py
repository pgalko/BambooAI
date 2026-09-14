"""Render the REAL page: web_app/templates/index.html with every stylesheet and script, the backend
faked, in headless chromium - then run a snippet (open a dialog, load fake data) and screenshot.
What the box shows, in the box's DOM, with the box's cascade - not a hand-made fragment.

  python3 tools/render_page.py --out /tmp/x.png --js "WorkflowModal.open()" [--light] [--wait 1500]
  python3 tools/render_page.py --out /tmp/x.png --fixtures tools/fixtures/workflows.json --js "..."

Fixtures: a JSON object {url_substring: response_json}; unmatched app URLs get {} / empty; CDN URLs are blocked."""
import argparse, json, os, re, sys
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

def static_index():
    html = open(os.path.join(ROOT, 'web_app', 'templates', 'index.html'), encoding='utf-8').read()
    html = re.sub(r"\{\{\s*url_for\('static',\s*filename='([^']+)'\)\s*\}\}", r"/static/\1", html)
    html = re.sub(r"\{\{[^}]*\}\}", "", html)                       # any other jinja expression
    html = re.sub(r"\{%[^%]*%\}", "", html)
    return html

def main():
    ap = argparse.ArgumentParser(); ap.add_argument('--out', required=True); ap.add_argument('--js', default=''); ap.add_argument('--fixtures', default='')
    ap.add_argument('--light', action='store_true'); ap.add_argument('--wait', type=int, default=1200); ap.add_argument('--width', type=int, default=1400); ap.add_argument('--height', type=int, default=900)
    ap.add_argument('--console', action='store_true')
    a = ap.parse_args()
    fixtures = json.load(open(a.fixtures)) if a.fixtures else {}
    html = static_index()
    from playwright.sync_api import sync_playwright
    with sync_playwright() as pw:
        b = pw.chromium.launch(); pg = b.new_page(viewport={'width': a.width, 'height': a.height})
        logs = []
        pg.on('console', lambda m: logs.append(f"[{m.type}] {m.text}"))
        pg.on('pageerror', lambda e: logs.append(f"[pageerror] {e}"))
        def handle(route):
            url = route.request.url
            if url.startswith('http://app.local/static/'):
                path = os.path.join(ROOT, 'web_app', 'static', url.split('/static/', 1)[1].split('?')[0])
                if os.path.exists(path):
                    ctype = {'.css': 'text/css', '.js': 'application/javascript', '.svg': 'image/svg+xml', '.png': 'image/png', '.jpg': 'image/jpeg', '.woff2': 'font/woff2'}.get(os.path.splitext(path)[1], 'application/octet-stream')
                    return route.fulfill(status=200, content_type=ctype, body=open(path, 'rb').read())
                return route.fulfill(status=404, body='')
            if url == 'http://app.local/' or url == 'http://app.local/index.html':
                return route.fulfill(status=200, content_type='text/html', body=html)
            if url.startswith('http://app.local/'):
                for k, v in fixtures.items():
                    if k in url:
                        return route.fulfill(status=200, content_type='application/json', body=json.dumps(v))
                return route.fulfill(status=200, content_type='application/json', body='{}')
            if 'marked' in url:                                           # the markdown renderer: a render-only stand-in
                return route.fulfill(status=200, content_type='application/javascript', body=open(os.path.join(ROOT, 'tools', 'fixtures', 'marked_stub.js'), 'rb').read())
            if 'dagre' in url:                                            # the map's layout library: a render-only stand-in
                return route.fulfill(status=200, content_type='application/javascript', body=open(os.path.join(ROOT, 'tools', 'fixtures', 'dagre_stub.js'), 'rb').read())
            return route.abort()                                          # CDN and everything else: offline
        pg.route('**/*', handle)
        pg.add_init_script("window.hljs = window.hljs || { highlightBlock() {}, highlightElement() {}, highlightAll() {}, configure() {} };")
        pg.goto('http://app.local/'); pg.wait_for_timeout(600)
        # the app initialises its modules only after the subscription check; run that step regardless
        pg.evaluate("window.handleNewConversation = function () {}; try { if (typeof initializeUIControls === 'function' && !document.querySelector('.menu-overlay')) initializeUIControls(); } catch (e) { console.log('[init-ui]', String(e)); } try { if (typeof continueAppInitialization === 'function') continueAppInitialization(); } catch (e) { console.log('[init]', String(e)); }")
        pg.wait_for_timeout(300)
        pg.evaluate("if (window.WorkspaceGate) { WorkspaceGate.release(); WorkspaceGate.hide(); }")   # the gate waits for an executor the fake backend never starts
        if a.light: pg.evaluate("document.documentElement.setAttribute('data-theme','light')")
        else: pg.evaluate("document.documentElement.setAttribute('data-theme','dark')")
        if a.js:
            try: pg.evaluate(a.js)
            except Exception as e: logs.append(f"[eval] {e}")
        pg.wait_for_timeout(a.wait)
        pg.screenshot(path=a.out); b.close()
    if a.console:
        for l in logs[-40:]: print(l)
    print("rendered", a.out)

if __name__ == '__main__':
    main()
