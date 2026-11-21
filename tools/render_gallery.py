"""Render the interface in its main states to a folder, and compare two folders pixel by pixel.
The guard for changes that must not be visible (the CSS fold): render before, render after, diff.

  python3 tools/render_gallery.py --out /tmp/gallery_before
  python3 tools/render_gallery.py --out /tmp/gallery_after --compare /tmp/gallery_before
"""
import argparse, json, os, sys, importlib.util
HERE = os.path.dirname(os.path.abspath(__file__))
spec = importlib.util.spec_from_file_location('rp', os.path.join(HERE, 'render_page.py')); rp = importlib.util.module_from_spec(spec); spec.loader.exec_module(rp)
FILL = open(os.path.join(HERE, 'fixtures', 'fill_page.js')).read() if os.path.exists(os.path.join(HERE, 'fixtures', 'fill_page.js')) else ''
ARCHITECT = open(os.path.join(HERE, 'fixtures', 'architect.js')).read()       # the Architect's states (2026-11-15): an invented brief and a report against it
DAGRE = open(os.path.join(HERE, 'fixtures', 'dagre_stub.js')).read()             # the maps' layout library, as the harness has it: here the library's address is not reached (2026-11-19, the map of a brief's conversation)
PLOTLY = open(os.path.join(HERE, 'stack', 'browser', 'libs_stub_plotly.js')).read()      # the stack's stand-in for Plotly: here the library's address is not reached (2026-11-18, the drafts of the figures)
PILLS = "const c=document.getElementById('datasetStatusPillsContainer'); c.innerHTML='<div class=\"dataset-status-pill primary-dataset-pill success\"><span class=\"dataset-pill-content clickable-pill-content\"><span>Primary (mtbuller_climate.csv)</span></span><span class=\"dataset-pill-remove-icon\"><svg viewBox=\"0 0 24 24\" fill=\"none\" stroke=\"currentColor\"><line x1=\"5\" y1=\"12\" x2=\"19\" y2=\"12\"/></svg></span></div><div class=\"dataset-status-pill auxiliary-dataset-pill success\"><span class=\"dataset-pill-content clickable-pill-content\"><span>Auxiliary (wellness.csv)</span></span></div>';"
STATES = {
    'page_answer': "activateTab('answer'); const a=document.getElementById('content-answer'); a.insertAdjacentHTML('afterbegin','<h3 class=\"answer-tab-anchor\"></h3>'); addPDFExportButton(a);",
    'page_data': "activateTab('dataframe');",
    'gear': "document.querySelector('.rail .settings-button').focus();",
    'composer_adaptive': "setMode('adaptive'); document.getElementById('queryInput').value='How does the warming trend compare?';",
    'composer_running': "setMode('deep'); document.getElementById('submitQuery').classList.add('query-running'); document.getElementById('saveButton').style.display='block';",
    'collapsed': "document.getElementById('collapseButton').click();",
    'dlg_account': "showSubscriptionModal(false);",
    'dlg_usage': "UsageUI.open();",                      # the dialog over tools/fixtures/usage.json (2026-10-31)
    'dlg_usage_analyses': "UsageUI.open(); setTimeout(()=>{ document.querySelector('.us-tabs [data-tab=analyses]').click(); setTimeout(()=>{ const it=document.querySelector('.us-list .it'); it && it.click(); }, 200); }, 300);",
    'dlg_workflows': "WorkflowModal.open();",
    'dlg_dataset': "document.getElementById('datasetManagerPill').click(); setTimeout(()=>{ const it=document.querySelector('#primaryDatasetList .dataset-item'); it && it.click(); }, 700);",
    'dlg_sweatstack': "document.getElementById('sweatstackModal').style.display='flex'; document.getElementById('users-selection').innerHTML='<label class=\"user-option\"><input type=\"checkbox\" checked><svg class=\"check-icon\" viewBox=\"0 0 24 24\" fill=\"none\" stroke=\"currentColor\" stroke-width=\"3\"><polyline points=\"20 6 9 17 4 12\"></polyline></svg><span>Athlete A</span></label><label class=\"user-option\"><input type=\"checkbox\"><svg class=\"check-icon\" viewBox=\"0 0 24 24\" fill=\"none\" stroke=\"currentColor\" stroke-width=\"3\"><polyline points=\"20 6 9 17 4 12\"></polyline></svg><span>Athlete B</span></label>';",
    'dlg_intervals': "showIntervalsModal(); document.getElementById('intervalsStartDate').value='2025-10-18'; document.getElementById('intervalsEndDate').value='2026-10-16';",     # the load dialogs' shared grammar (2026-10-16)
    'dlg_endura': "document.getElementById('enduraModal').style.display='flex'; document.getElementById('enduraRaceSelect').innerHTML='<option>Spring classic 2026</option>';",
    'dlg_intervals_cfg': "document.getElementById('intervalsConfigModal').style.display='flex';",
    'dlg_codebook': "CodebookUI.open();",
    'architect_talk': ARCHITECT + "galleryArchitect.talk();",          # the Architect's first question, with its choices (docs/ARCHITECT_DESIGN.md §2.12)
    'architect_reading': ARCHITECT + "galleryArchitect.reading();",    # a message on its way: the Architect reading, the composer held
    'architect_adding': ARCHITECT + "galleryArchitect.adding();",      # + Add, open: the parts the brief does not show (§2.18)
    'architect_brief': ARCHITECT + "galleryArchitect.brief();",        # the brief after the conversation: the question as the Architect worded it (§2.18), one line open (§2.11)
    'architect_step': ARCHITECT + "galleryArchitect.step();",          # an earlier step of a conversation that branched on screen: both panes are that step's, Start analysis names it (§2.25)
    'architect_map': DAGRE + ARCHITECT + "galleryArchitect.map();",    # its Pathfinding map, in the maps drawer: the way to the step on screen lit, the pointer on the way that was left (§2.25)
    'architect_drawing': ARCHITECT + "galleryArchitect.drawing();",    # a grey window to each figure while its draft is drawn: the reply above the row that says so (§2.20; 0311)
    'architect_draft': PLOTLY + ARCHITECT + "galleryArchitect.draft();",      # the drafts drawn on the Brief tab: one on made-up numbers, marked, one computed (§2.20)
    'architect_checked': ARCHITECT + "galleryArchitect.checked();",    # what the brief rests on, checked against the data: the row, the marks, keep or change (§2.13)
    'architect_checking': ARCHITECT + "galleryArchitect.checking();",  # Start analysis pressed: the question is being read as the Analyst will read it (§2.22)
    'architect_unplaced': ARCHITECT + "galleryArchitect.unplaced();",  # the words the Analyst cannot place, and the Architect's wording after it (§2.22)
    'architect_answer': ARCHITECT + "galleryArchitect.answer();",      # the answer of a run under a brief: nothing in it of what the report says against the brief (0312)
    'architect_outcome': ARCHITECT + "galleryArchitect.outcome();",    # which stands at the foot of that run's Brief tab: how it turned out (§2.21)
    'architect_saving': ARCHITECT + "galleryArchitect.saving();",      # the saved analyses being read: the row with its count and Skip (§3.7)
    'architect_saved': ARCHITECT + "galleryArchitect.saved();",        # what they hold: the analyses found, to read, and the one the brief builds on (§2.18)
    'next_questions': ARCHITECT + "galleryArchitect.next();",          # the panel of next questions in a finished analysis' closing card: the five ways to go, one with questions (§2.24)
    'next_shown': ARCHITECT + "galleryArchitect.next(true);",          # the questions of one way in the list's place, one of them run (§2.24)
}

def render_all(out, light=False):
    os.makedirs(out, exist_ok=True)
    from playwright.sync_api import sync_playwright
    html = rp.static_index(); fixtures = json.load(open(os.path.join(HERE, 'fixtures', 'workflows.json'))); ROOT = rp.ROOT
    fixtures.update(json.load(open(os.path.join(HERE, 'fixtures', 'codebook.json'))))     # the codebook screen's book (2026-10-16), a file of its own
    fixtures.update(json.load(open(os.path.join(HERE, 'fixtures', 'drafts.json'))))       # the plots of the drafts the Architect's state shows (2026-11-18), by the address the page asks
    usage_fx = os.path.join(HERE, 'fixtures', 'usage.json')                               # the usage dialog's answers (2026-10-31): a synthetic month, made on demand
    if not os.path.exists(usage_fx):
        import subprocess; subprocess.run([sys.executable, os.path.join(HERE, 'usage_fixture.py'), usage_fx], check=True, env=dict(os.environ, PYTHONPATH=os.path.join(ROOT, 'tools', 'stack', 'fakepkgs')))
    fixtures.update(json.load(open(usage_fx)))
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
