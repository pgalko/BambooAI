"""The routines screens in the REAL page (web_app/templates/index.html with every stylesheet and script, the backend
faked, the page filled as tools/render_gallery.py fills it), one PNG per screen, dark and light with --light:

  python3 tools/routines_screens.py --out /tmp/routines_screens [--light]

Screens: the Save pill's menu on a finished chain; the Save-as-routine dialog with a proposal, with the next-version
choice, and refused; the Routines manager with one routine and empty; the favourites manager with a card's Routine
button lit. The two streaming routes are answered with the lines the server would send, so routines.js runs its own
path - the dialog is driven by the script, not drawn by hand. Exits 1 when a page error or an unexpected state shows."""
import argparse, json, os, sys, importlib.util
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
spec = importlib.util.spec_from_file_location('rp', os.path.join(HERE, 'render_page.py')); rp = importlib.util.module_from_spec(spec); spec.loader.exec_module(rp)
FILL = open(os.path.join(HERE, 'fixtures', 'fill_page.js')).read()

PROPOSAL = {"proposal_id": "p1", "thread_id": "1791460000", "chain_id": "1791460001", "name": "Altitude pace correction, within athlete", "purpose": "",
            "question": "How much slower is the same runner at 2,100-3,100 m than at sea level, holding effort and surface fixed?",
            "summary": "The within-athlete, effort-adjusted gap is +0.11 log-speed units.", "source": "file", "data_state": "same",
            "data": {"name": "EEDR_sessions_laps_enriched.csv", "rows": 22705, "columns": [{"name": f"c{i}"} for i in range(49)]},
            "inputs": [{"key": "hard_effort_hr", "label": "Hard-effort threshold (lap HR)", "type": "number", "default": 155, "origin": "the exploration split laps at 155"},
                       {"key": "hr_bands", "label": "HR bands for the matched comparison", "type": "numbers", "default": [130, 145, 155, 165, 175], "origin": "the exploration's bands"},
                       {"key": "exclude", "label": "Athletes to exclude (sensitivity line)", "type": "choice", "multiple": True, "default": ["athlete07", "athlete09"], "origin": "the exploration dropped two athletes with few abroad laps", "column": "athlete_id"}],
            "kept": ["the 1-km lap window", "the speed plausibility bounds", "the bootstrap size and seed"],
            "results": [{"cell": 2, "index": 0, "label": "log speed, abroad (sea level) vs Ethiopia altitude laps, within-athlete, HR/temp/ascent adjusted, 1-km laps", "typed": False},
                        {"cell": 2, "index": 1, "label": "log speed, abroad vs Ethiopia, athlete FE only, 1-km laps", "typed": False},
                        {"cell": 3, "index": 0, "label": "log speed per +1000 m venue altitude within Ethiopia, FE", "typed": False},
                        {"cell": 3, "index": 1, "label": "log speed per +1000 m venue altitude within Ethiopia, FE+surface", "typed": False},
                        {"cell": 4, "index": 0, "label": "correction of cell 3's wording", "typed": True},
                        {"cell": 5, "index": 0, "label": "log speed, abroad vs Ethiopian road laps at same HR band, athlete FE, athlete-cluster bootstrap", "typed": False}],
            "figures": {"count": 1, "cells": [5]}, "cells": 5, "cost": 0.04, "notes": [], "routine_id": None, "routine_name": None, "next_version": None}
ROUTINE = {"id": "r1", "name": "Altitude pace correction, within athlete", "created": 1791460000, "updated": 1791460000, "purpose": "the sea-level gap, holding effort and surface fixed",
           "question": PROPOSAL["question"], "summary": PROPOSAL["summary"], "origin": {"thread_id": "1791460000", "chain_id": "1791460001"}, "source": "file", "current_version": 1, "runs": [],
           "origin_available": True, "summary_card": {"data": PROPOSAL["data"]},
           "versions": [{"number": 1, "created": 1791460000, "promoted_from": {"thread_id": "1791460000", "chain_id": "1791460001"}, "change_note": "first version", "script_chars": 9120,
                         "manifest": {"data": PROPOSAL["data"], "parameters": PROPOSAL["inputs"], "results": [dict(r, dropped=r["typed"]) for r in PROPOSAL["results"]], "figures": PROPOSAL["figures"]},
                         "run_zero": {"status": "reproduced", "line": "reproduced: 5 result line(s) identical", "verified": True}}]}
SUMMARY = {"id": "r1", "name": ROUTINE["name"], "created": 1791460000, "updated": 1791460000, "source": "file", "purpose": ROUTINE["purpose"], "question": ROUTINE["question"], "origin": ROUTINE["origin"],
           "current_version": 1, "versions": 1, "runs": 0, "verified": True, "run_zero_status": "reproduced", "run_zero_line": "reproduced: 5 result line(s) identical", "inputs": 3, "results": 5, "figures": 1, "data": PROPOSAL["data"]}
SCREENS = {
    's0_save_menu':       {"js": "window.__shot.openMenu()", "routines": []},
    's1_make_dialog':     {"js": "RoutinesUI.openMake('1791460000', '1791460001', {threadRoutines: []})", "routines": []},
    's1b_next_version':   {"js": "RoutinesUI.openMake('1791460000', '1791460001', {threadRoutines: [{id: 'r1', name: 'Altitude pace correction, within athlete', version: 1, chain_id: '1791450000'}]})", "routines": [SUMMARY]},
    's1c_refused':        {"js": "RoutinesUI.openMake('1791460000', '1791460001', {threadRoutines: []})", "routines": [], "propose_error": "run zero on this chain's own data did not reproduce the analysis: 2 of 5 result lines differ ([cell 2] log speed, abroad (sea level) vs Ethiopia altitude laps: +0.11 -> +0.16; [cell 3] log speed per +1000 m venue altitude within Ethiopia, FE: -0.13 -> -0.09)"},
    's2_manager':         {"js": "RoutinesUI.openManager('r1')", "routines": [SUMMARY]},
    's2b_manager_empty':  {"js": "RoutinesUI.openManager()", "routines": []},
    's3_favourite_card':  {"js": "WorkflowModal.open()", "routines": [SUMMARY], "card": True},
}


def render(out, light=False, width=1440, height=900):
    os.makedirs(out, exist_ok=True)
    from playwright.sync_api import sync_playwright
    html = rp.static_index(); fixtures = json.load(open(os.path.join(HERE, 'fixtures', 'workflows.json')))
    bad = []
    with sync_playwright() as pw:
        b = pw.chromium.launch()
        for name, spec_ in SCREENS.items():
            for theme in (['dark', 'light'] if light else ['dark']):
                pg = b.new_page(viewport={'width': width, 'height': height}); logs = []
                pg.on('pageerror', lambda e: logs.append(f"[pageerror] {e}"))
                threads = json.loads(json.dumps(fixtures.get('/get_threads', {"threads": []})))
                if spec_.get('card'):
                    for t in threads.get('threads', []):
                        for i, c in enumerate(t.get('chains', [])):
                            c['routines'] = [{"id": "r1", "name": ROUTINE["name"], "version": 1}] if i == 0 and t is threads['threads'][0] else []
                def handle(route, request=None, spec_=spec_, threads=threads):
                    url = route.request.url
                    path = url.split('app.local', 1)[1].split('?')[0] if 'app.local' in url else url
                    if url.startswith('http://app.local/static/'):
                        p = os.path.join(ROOT, 'web_app', 'static', url.split('/static/', 1)[1].split('?')[0])
                        if os.path.exists(p):
                            ctype = {'.css': 'text/css', '.js': 'application/javascript', '.svg': 'image/svg+xml', '.png': 'image/png'}.get(os.path.splitext(p)[1], 'application/octet-stream')
                            return route.fulfill(status=200, content_type=ctype, body=open(p, 'rb').read())
                        return route.fulfill(status=404, body='')
                    if path in ('/', '/index.html'): return route.fulfill(status=200, content_type='text/html', body=html)
                    if path == '/routines/propose':
                        if spec_.get('propose_error'):
                            lines = [{"type": "pane_turn_start", "turn": "routine", "seat": "Analyst", "model": "anthropic/claude-sonnet-5-5", "quiet": True}, {"type": "pane_turn_end", "turn": "routine", "kind": "routine", "peek": "3 input(s) proposed, 5 edit(s)", "elapsed": 11.2, "cost": 0.04},
                                     {"type": "pane_lookup_start", "kind": "routine", "query": PROPOSAL["name"]}, {"type": "pane_lookup", "kind": "routine", "query": PROPOSAL["name"], "peek": "2 of 5 result lines differ", "sources": [], "passages": []},
                                     {"routine_error": spec_['propose_error']}]
                        else:
                            lines = [{"type": "pane_turn_start", "turn": "routine", "seat": "Analyst", "model": "anthropic/claude-sonnet-5-5", "quiet": True}, {"type": "pane_turn_end", "turn": "routine", "kind": "routine", "peek": "3 input(s) proposed, 5 edit(s)", "elapsed": 11.2, "cost": 0.04},
                                     {"routine_proposal": PROPOSAL}]
                        return route.fulfill(status=200, content_type='application/json', body="\n".join(json.dumps(x) for x in lines) + "\n")
                    if path == '/routines/create':
                        lines = [{"type": "pane_lookup_start", "kind": "routine", "query": PROPOSAL["name"]}, {"type": "pane_lookup", "kind": "routine", "query": PROPOSAL["name"], "peek": "reproduced: 5 result line(s) identical", "sources": [], "passages": []},
                                 {"routine_made": {"routine": SUMMARY, "version": 1, "run_zero": ROUTINE["versions"][0]["run_zero"], "name": ROUTINE["name"]}}]
                        return route.fulfill(status=200, content_type='application/json', body="\n".join(json.dumps(x) for x in lines) + "\n")
                    if path.startswith('/routines/by_origin/'):
                        parts = path.split('/')[3:]
                        items = [dict(x, chain_id=x.get('chain_id', '1791460001')) for x in spec_.get('routines', [])]
                        if len(parts) == 2 and parts[1] != '1791460001': items = []
                        return route.fulfill(status=200, content_type='application/json', body=json.dumps({"routines": [{"id": x["id"], "name": x["name"], "version": 1, "chain_id": x.get("chain_id", "1791460001")} for x in items]}))
                    if path == '/routines':
                        return route.fulfill(status=200, content_type='application/json', body=json.dumps({"routines": spec_.get('routines', [])}))
                    if path == '/routines/r1':
                        return route.fulfill(status=200, content_type='application/json', body=json.dumps({"routine": ROUTINE}))
                    if path == '/get_threads':
                        return route.fulfill(status=200, content_type='application/json', body=json.dumps(threads))
                    if url.startswith('http://app.local/'):
                        for k, v in fixtures.items():
                            if k in url: return route.fulfill(status=200, content_type='application/json', body=json.dumps(v))
                        return route.fulfill(status=200, content_type='application/json', body='{}')
                    if 'marked' in url: return route.fulfill(status=200, content_type='application/javascript', body=open(os.path.join(HERE, 'fixtures', 'marked_stub.js'), 'rb').read())
                    if 'dagre' in url: return route.fulfill(status=200, content_type='application/javascript', body=open(os.path.join(HERE, 'fixtures', 'dagre_stub.js'), 'rb').read())
                    return route.abort()
                pg.add_init_script("window.hljs = window.hljs || { highlightBlock() {}, highlightElement() {}, highlightAll() {}, configure() {} };")
                pg.route('**/*', handle); pg.goto('http://app.local/'); pg.wait_for_timeout(500)
                pg.evaluate("document.documentElement.setAttribute('data-theme', '%s')" % theme)
                pg.add_style_tag(content='*, *::before, *::after { animation: none !important; transition: none !important; caret-color: transparent !important; }')
                pg.evaluate("window.handleNewConversation = function () {}; try { if (typeof initializeUIControls === 'function' && !document.querySelector('.menu-overlay')) initializeUIControls(); } catch (e) {} try { if (typeof continueAppInitialization === 'function') continueAppInitialization(); } catch (e) {}")
                pg.wait_for_timeout(300)
                pg.evaluate("if (window.WorkspaceGate) { WorkspaceGate.release(); WorkspaceGate.hide(); }")
                pg.evaluate(FILL); pg.wait_for_timeout(1500)
                # the finished chain in view: what the pill and the menu read
                pg.evaluate("responses = [{chain_id: '1791460001', thread_id: '1791460000', queryText: 'q'}]; currentResponseIndex = 0; currentData.chain_id = '1791460001'; currentData.thread_id = '1791460000'; currentRankData = {chain_id: '1791460001', theoretical: true}; updateRankButtonVisibility();"
                            "window.__shot = { openMenu() { const p = document.getElementById('rankButton'); p.dispatchEvent(new MouseEvent('mouseenter', {bubbles: true})); } };")
                try: pg.evaluate(spec_['js'])
                except Exception as e: print('  [eval]', name, str(e)[:200]); bad.append(name)
                pg.wait_for_timeout(1200)
                state = pg.evaluate("({pill: getComputedStyle(document.getElementById('rankButton')).display, menu: !!document.querySelector('#saveMenu') && document.querySelector('#saveMenu').style.display !== 'none', dialog: !!document.querySelector('#routineMakeModal') && document.querySelector('#routineMakeModal').style.display === 'flex', inputs: document.querySelectorAll('#routineMakeModal .rt-inputs tbody tr').length, error: !!document.querySelector('#routineMakeModal .rt-error'), manager: !!document.querySelector('#routinesModal') && document.querySelector('#routinesModal').style.display === 'flex', mgrItems: document.querySelectorAll('#routinesModal .rt-side .it').length, cards: document.querySelectorAll('#workflowManagerModal .workflow-card-routine').length, lit: document.querySelectorAll('#workflowManagerModal .workflow-card-routine.has').length, pane: (document.getElementById('streamOutput').textContent || '').includes('Routine')})")
                want = {'s0_save_menu': state['pill'] != 'none' and state['menu'], 's1_make_dialog': state['dialog'] and state['inputs'] == 3 and state['pane'], 's1b_next_version': state['dialog'] and state['inputs'] == 3,
                        's1c_refused': state['dialog'] and state['error'], 's2_manager': state['manager'] and state['mgrItems'] == 1, 's2b_manager_empty': state['manager'] and state['mgrItems'] == 0,
                        's3_favourite_card': state['cards'] >= 1 and state['lit'] >= 1}[name]
                if not want:
                    bad.append(name); print('  [state]', name, state)
                pg.screenshot(path=os.path.join(out, f'{name}_{theme}.png')); pg.close()
                for l in logs:
                    if 'localforage' in l or 'renderMathInElement' in l or 'marked.Renderer' in l: continue
                    print('  ', name, l[:200]); bad.append(name)
        b.close()
    print('rendered', len(os.listdir(out)), 'images to', out, '; problems:', sorted(set(bad)) or 'none')
    return 1 if bad else 0


if __name__ == '__main__':
    ap = argparse.ArgumentParser(); ap.add_argument('--out', required=True); ap.add_argument('--light', action='store_true')
    a = ap.parse_args(); sys.exit(render(a.out, a.light))
