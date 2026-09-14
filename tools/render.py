"""Render a piece of the interface with the app's own stylesheets, in the page's own order, and
screenshot it with chromium (playwright). What the box will show, before it ships.

  python3 tools/render.py --dialog subscriptionModal --out /tmp/x.png [--light] [--class mandatory] [--tab funds]
  python3 tools/render.py --html snippet.html --out /tmp/x.png

A dialog is cut from web_app/templates/index.html and shown the way its JS shows it (display:flex)."""
import argparse, os, re, shutil, sys, tempfile
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

def fragment(html, elem_id):
    s = html.index(f'id="{elem_id}"'); start = html.rfind('<div', 0, s); depth = 0
    for m in re.finditer(r'<(/?)div\b[^>]*?(/?)>', html[start:]):
        if m.group(1): depth -= 1
        elif not m.group(2): depth += 1
        if depth == 0: return html[start:start + m.end()]
    return html[start:]

def main():
    ap = argparse.ArgumentParser(); ap.add_argument('--dialog'); ap.add_argument('--html'); ap.add_argument('--out', required=True)
    ap.add_argument('--light', action='store_true'); ap.add_argument('--class', dest='klass', default=''); ap.add_argument('--tab', default='')
    ap.add_argument('--width', type=int, default=1200); ap.add_argument('--height', type=int, default=860); ap.add_argument('--full', action='store_true')
    a = ap.parse_args()
    index = open(os.path.join(ROOT, 'web_app', 'templates', 'index.html'), encoding='utf-8').read()
    links = re.findall(r"filename='css/([^']+)'", index)
    work = tempfile.mkdtemp(prefix='render_'); os.makedirs(os.path.join(work, 'css'), exist_ok=True)
    for rel in links:
        src = os.path.join(ROOT, 'web_app', 'static', 'css', rel)
        if os.path.exists(src):
            os.makedirs(os.path.dirname(os.path.join(work, 'css', rel)), exist_ok=True); shutil.copy(src, os.path.join(work, 'css', rel))
    head = "\n".join(f'<link rel="stylesheet" href="css/{rel}">' for rel in links)
    if a.dialog:
        body = fragment(index, a.dialog)
        body = re.sub(r'(id="' + a.dialog + r'"\s+class=")([^"]*)"', lambda m: m.group(1) + m.group(2) + (' ' + a.klass if a.klass else '') + '" style="display:flex"', body, count=1)
        if a.tab:
            body = re.sub(r'class="([\w-]*tab[\w-]*) active"', r'class="\1"', body)
            body = body.replace(f'data-tab="{a.tab}"', f'data-tab="{a.tab}" data-active="1"')
            body = re.sub(r'class="([\w-]*tab[\w-]*)" data-tab="' + a.tab + '" data-active="1"', r'class="\1 active" data-tab="' + a.tab + '"', body)
            body = re.sub(r'id="([\w-]+)-tab" class="tab-content( active)?"', lambda m: f'id="{m.group(1)}-tab" class="tab-content' + (' active' if m.group(1) == a.tab else '') + '"', body)
    else:
        body = open(a.html, encoding='utf-8').read()
    page = f'<!doctype html><html><head><meta charset="utf-8">{head}</head><body{" data-theme=\"light\"" if a.light else ""} style="margin:0;background:var(--bg-primary)">{body}</body></html>'
    p = os.path.join(work, 'page.html'); open(p, 'w', encoding='utf-8').write(page)
    from playwright.sync_api import sync_playwright
    with sync_playwright() as pw:
        b = pw.chromium.launch(); pg = b.new_page(viewport={'width': a.width, 'height': a.height})
        pg.goto('file://' + p); pg.wait_for_timeout(250); pg.screenshot(path=a.out, full_page=a.full); b.close()
    print("rendered", a.out)

if __name__ == '__main__':
    main()
