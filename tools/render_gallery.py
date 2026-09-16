"""Render the interface in its main states to a folder, and compare two folders pixel by pixel.
The guard for changes that must not be visible (the CSS fold): render before, render after, diff.

  python3 tools/render_gallery.py --out /tmp/gallery_before
  python3 tools/render_gallery.py --out /tmp/gallery_after --compare /tmp/gallery_before
"""
import argparse, json, os, sys, importlib.util
HERE = os.path.dirname(os.path.abspath(__file__))
spec = importlib.util.spec_from_file_location('rp', os.path.join(HERE, 'render_page.py')); rp = importlib.util.module_from_spec(spec); spec.loader.exec_module(rp)
FILL = open(os.path.join(HERE, 'fixtures', 'fill_page.js')).read() if os.path.exists(os.path.join(HERE, 'fixtures', 'fill_page.js')) else ''
PILLS = "const c=document.getElementById('datasetStatusPillsContainer'); c.innerHTML='<div class=\"dataset-status-pill primary-dataset-pill success\"><span class=\"dataset-pill-content clickable-pill-content\"><span>Primary (mtbuller_climate.csv)</span></span><span class=\"dataset-pill-remove-icon\"><svg viewBox=\"0 0 24 24\" fill=\"none\" stroke=\"currentColor\"><line x1=\"5\" y1=\"12\" x2=\"19\" y2=\"12\"/></svg></span></div><div class=\"dataset-status-pill auxiliary-dataset-pill success\"><span class=\"dataset-pill-content clickable-pill-content\"><span>Auxiliary (wellness.csv)</span></span></div>';"
STATES = {
    'page_answer': "activateTab('answer'); const a=document.getElementById('content-answer'); a.insertAdjacentHTML('afterbegin','<h3 class=\"answer-tab-anchor\"></h3>'); addPDFExportButton(a);",
    'page_data': "activateTab('dataframe');",
    'gear': "document.querySelector('.rail .settings-button').focus();",
    'composer_adaptive': "setMode('adaptive'); document.getElementById('queryInput').value='How does the warming trend compare?';",
    'composer_running': "setMode('deep'); document.getElementById('submitQuery').classList.add('query-running'); document.getElementById('rankButton').style.display='';",
    'collapsed': "document.getElementById('collapseButton').click();",
    'dlg_account': "showSubscriptionModal(false);",
    'dlg_usage': "document.getElementById('usageTrackingModal').style.display='flex'; document.getElementById('usageDataContainer').style.display='flex';",
    'dlg_workflows': "WorkflowModal.open();",
    'dlg_dataset': "document.getElementById('datasetManagerPill').click(); setTimeout(()=>{ const it=document.querySelector('#primaryDatasetList .dataset-item'); it && it.click(); }, 700);",
    'dlg_memory': "document.getElementById('memoryReviewPill').style.display=''; document.getElementById('memoryReviewPill').click();",
    'dlg_rank': "currentRankData = {chain_id: 1, thread_id: 't'}; showRankModal(); setTimeout(()=>document.querySelectorAll('#rankModal .rating-segment')[6].click(), 200);",
    'dlg_sweatstack': "document.getElementById('sweatstackModal').style.display='flex';",
    'dlg_intervals_cfg': "document.getElementById('intervalsConfigModal').style.display='flex';",
}

def render_all(out, light=False):
    os.makedirs(out, exist_ok=True)
    from playwright.sync_api import sync_playwright
    html = rp.static_index(); fixtures = json.load(open(os.path.join(HERE, 'fixtures', 'workflows.json'))); ROOT = rp.ROOT
    with sync_playwright() as pw:
        b = pw.chromium.launch()
        for name, js in STATES.items():
            for theme in (['dark', 'light'] if light else ['dark']):
                pg = b.new_page(viewport={'width': 1440, 'height': 900})
                def handle(route):
                    url = route.request.url
                    if url.startswith('http://app.local/static/'):
                        path = os.path.join(ROOT, 'web_app', 'static', url.split('/static/', 1)[1].split('?')[0])
                        if os.path.exists(path):
                            ctype = {'.css': 'text/css', '.js': 'application/javascript', '.svg': 'image/svg+xml', '.png': 'image/png'}.get(os.path.splitext(path)[1], 'application/octet-stream')
                            return route.fulfill(status=200, content_type=ctype, body=open(path, 'rb').read())
                        return route.fulfill(status=404, body='')
                    if url in ('http://app.local/', 'http://app.local/index.html'): return route.fulfill(status=200, content_type='text/html', body=html)
                    if url.startswith('http://app.local/'):
                        for k, v in fixtures.items():
                            if k in url: return route.fulfill(status=200, content_type='application/json', body=json.dumps(v))
                        return route.fulfill(status=200, content_type='application/json', body='{}')
                    return route.abort()
                pg.add_init_script("window.hljs = window.hljs || { highlightBlock() {}, highlightElement() {}, highlightAll() {}, configure() {} };")
                pg.route('**/*', handle); pg.goto('http://app.local/'); pg.wait_for_timeout(500)
                pg.evaluate("document.documentElement.setAttribute('data-theme', '%s')" % theme)
                pg.add_style_tag(content='*, *::before, *::after { animation: none !important; transition: none !important; caret-color: transparent !important; }')
                pg.evaluate("window.handleNewConversation = function () {}; try { if (typeof initializeUIControls === 'function' && !document.querySelector('.menu-overlay')) initializeUIControls(); } catch (e) {} try { if (typeof continueAppInitialization === 'function') continueAppInitialization(); } catch (e) {} if (window.WorkspaceGate) { WorkspaceGate.release(); WorkspaceGate.hide(); }")
                if FILL: pg.evaluate(FILL)
                pg.wait_for_timeout(1600)
                try: pg.evaluate(PILLS + js)
                except Exception as e: print('  [eval]', name, str(e)[:80])
                if os.environ.get('GALLERY_EXTRA_JS'): pg.evaluate(os.environ['GALLERY_EXTRA_JS'])   # e.g. the README shot: the chip as a live page shows it
                pg.wait_for_timeout(1000)
                pg.screenshot(path=os.path.join(out, f'{name}_{theme}.png')); pg.close()
        b.close()
    print('rendered', len(os.listdir(out)), 'images to', out)

def compare(a, b):
    from PIL import Image, ImageChops
    bad = 0
    for f in sorted(os.listdir(a)):
        if not f.endswith('.png') or not os.path.exists(os.path.join(b, f)): continue
        x = Image.open(os.path.join(a, f)).convert('RGB'); y = Image.open(os.path.join(b, f)).convert('RGB')
        if x.size != y.size: print('  DIFF size', f); bad += 1; continue
        diff = ImageChops.difference(x, y); box = diff.getbbox()
        if box:
            n = sum(1 for p in diff.getdata() if p != (0, 0, 0)); bad += 1
            print(f'  DIFF {f}: {n} pixels, box {box}'); diff.point(lambda v: 255 if v else 0).save(os.path.join(b, f.replace('.png', '_diff.png')))
        else: print(f'  same {f}')
    print('\n' + ('IDENTICAL' if not bad else f'{bad} state(s) differ')); return bad

if __name__ == '__main__':
    ap = argparse.ArgumentParser(); ap.add_argument('--out', required=True); ap.add_argument('--compare'); ap.add_argument('--light', action='store_true'); a = ap.parse_args()
    render_all(a.out, a.light)
    if a.compare: sys.exit(1 if compare(a.compare, a.out) else 0)
