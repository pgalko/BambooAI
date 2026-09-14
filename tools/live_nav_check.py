import os, json, importlib.util, sys
spec = importlib.util.spec_from_file_location('rp', '/home/claude/project/tools/render_page.py'); rp = importlib.util.module_from_spec(spec); spec.loader.exec_module(rp)
from playwright.sync_api import sync_playwright
ROOT = sys.argv[1] if len(sys.argv) > 1 else rp.ROOT
html = open(os.path.join(ROOT, 'web_app', 'templates', 'index.html'), encoding='utf-8').read(); import re
html = re.sub(r"\{\{ url_for\('static', filename='([^']+)'\) \}\}", r"/static/\1", html); html = re.sub(r"\{%.*?%\}", "", html, flags=re.S); html = re.sub(r"\{\{.*?\}\}", "", html)
fixtures = json.load(open('/home/claude/project/tools/fixtures/workflows.json'))
with sync_playwright() as pw:
    b = pw.chromium.launch(); pg = b.new_page(viewport={'width': 1440, 'height': 900})
    pg.add_init_script("window.hljs = window.hljs || { highlightBlock() {}, highlightElement() {}, highlightAll() {}, configure() {} };")
    errs = []; pg.on('pageerror', lambda e: errs.append(str(e) + ' @ ' + (str(e.stack)[:400] if hasattr(e, 'stack') else '')))
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
        if 'marked' in url: return route.fulfill(status=200, content_type='application/javascript', body=open('/home/claude/project/tools/fixtures/marked_stub.js', 'rb').read())
        return route.abort()
    pg.route('**/*', handle); pg.goto('http://app.local/'); pg.wait_for_timeout(600)
    pg.evaluate("window.handleNewConversation = function () {}; try { initializeUIControls(); } catch (e) {} try { continueAppInitialization(); } catch (e) {} if (window.WorkspaceGate) { WorkspaceGate.release(); WorkspaceGate.hide(); }"); pg.wait_for_timeout(1200)
    pg.evaluate("void (window.feed = (objs) => { buffer = ''; processChunk(objs.map(o => JSON.stringify(o)).join('\\n') + '\\n'); })")
    pg.evaluate("currentData.queryText = 'Plot Fibonacci sequence'; document.getElementById('streamOutput').innerHTML=''; clearAllTabs(); beginLiveChain();")
    pg.evaluate("feed([{type:'id', chain_id:'c1', thread_id:'t1', parent_chain_id:null}, {type:'pane_run_start', mode:'Deep', of:15, dollars:1.5, chain_id:'c1'}, {type:'pane_turn_start', turn:1, seat:'Analyst', model:'grok', chain_id:'c1'}, {type:'pane_turn_end', turn:1, kind:'cell', thinking:'Fibonacci up to 20 and Binet.', note:'', code:'print(1)', elapsed:3, cost:0.01, chain_id:'c1'}, {type:'pane_cell', turn:1, cell_no:1, ok:true, chars:40, figs:1, first_line:'[0, 1, 1, 2, 3]', elapsed:0.1, chain_id:'c1'}, {type:'answer', data:'# Fibonacci\\n\\nThe first twenty terms.', chain_id:'c1'}, {type:'pane_run_end', status:'answered', turns:1, of:15, cells:1, failed:0, cost:0.02, seconds:10, replay_status:'reproduced', replay_line:'replay reproduced 20 numbers', plots:1, chain_id:'c1'}])")
    pg.evaluate("saveCurrentResponse();"); pg.wait_for_timeout(300)
    r = {}
    r['after_chain1'] = pg.evaluate("({n: responses.length, idx: currentResponseIndex, status: responses[0].status, chain: responses[0].chain_id, running: liveState.running})")
    pg.evaluate("currentData.queryText = 'Who was Fibonacci'; document.getElementById('streamOutput').innerHTML=''; clearAllTabs(); beginLiveChain(); feed([{type:'id', chain_id:'c2', thread_id:'t1', parent_chain_id:'c1'}, {type:'pane_run_start', mode:'Deep', of:15, dollars:1.5, chain_id:'c2'}, {type:'pane_turn_start', turn:1, seat:'Analyst', model:'grok', chain_id:'c2'}, {type:'pane_turn_end', turn:1, kind:'search', thinking:'A biographical question; search first.', note:'', code:'', elapsed:5, cost:0.01, chain_id:'c2'}])")
    r['chain2_started'] = pg.evaluate("({n: responses.length, idx: currentResponseIndex, live: liveState.index, label: document.getElementById('chainPosition').textContent, cards: document.querySelectorAll('#streamOutput .sp-turn').length})")
    pg.evaluate("navigateResponses(-1)"); pg.wait_for_timeout(200)
    r['viewing_chain1'] = pg.evaluate("({idx: currentResponseIndex, away: liveState.away, label: document.getElementById('chainPosition').textContent, streamHasChain1: document.getElementById('streamOutput').innerHTML.includes('Fibonacci up to 20'), streamHasChain2: document.getElementById('streamOutput').innerHTML.includes('biographical'), answerTab: (document.querySelector('#content-answer .markdown-content')||{}).textContent})")
    pg.evaluate("feed([{type:'pane_turn_start', turn:2, seat:'Analyst', model:'grok', chain_id:'c2'}, {type:'pane_turn_end', turn:2, kind:'report', thinking:'Search 1 already gives a sourced identity.', note:'', code:'', elapsed:6, cost:0.02, chain_id:'c2'}, {type:'answer', data:'# Leonardo of Pisa\\n\\nKnown as Fibonacci, c. 1170 to c. 1250.', chain_id:'c2'}, {type:'pane_run_end', status:'answered', turns:2, of:15, cells:0, failed:0, cost:0.04, seconds:30, replay_status:'', replay_line:'', plots:0, chain_id:'c2'}])")
    pg.wait_for_timeout(300)
    r['while_away_visible0'] = 0
    r['while_away_visible'] = pg.evaluate("({streamHasChain2: document.getElementById('streamOutput').innerHTML.includes('sourced identity'), answerVisible: (document.querySelector('#content-answer .markdown-content')||{}).textContent, liveHolderHasChain2: liveState.holders.stream.innerHTML.includes('sourced identity'), liveAnswer: (liveState.holders.content.querySelector('#content-answer .markdown-content')||{}).textContent})")
    # a second run: away, then back before the end
    pg.evaluate("saveCurrentResponse();"); pg.wait_for_timeout(200)
    r['after_end_while_away'] = pg.evaluate("({n: responses.length, idx: currentResponseIndex, running: liveState.running, c2status: responses[1].status, c2chain: responses[1].chain_id, c2parent: responses[1].parentChainId, c2answer: (responses[1].technicalAnswer||'').includes('Leonardo'), c2stream: responses[1].streamOutput.includes('sourced identity'), viewStill1: document.getElementById('streamOutput').innerHTML.includes('Fibonacci up to 20'), label: document.getElementById('chainPosition').textContent})")
    pg.evaluate("navigateResponses(1)"); pg.wait_for_timeout(300)
    r['navigated_to_chain2'] = pg.evaluate("({idx: currentResponseIndex, streamHasChain2: document.getElementById('streamOutput').innerHTML.includes('sourced identity'), streamHasChain1: document.getElementById('streamOutput').innerHTML.includes('Fibonacci up to 20'), answer: (document.querySelector('#content-answer .markdown-content')||{}).textContent, label: document.getElementById('chainPosition').textContent})")
    pg.evaluate("currentData.queryText = 'Plot golden ratio'; document.getElementById('streamOutput').innerHTML=''; clearAllTabs(); beginLiveChain(); feed([{type:'id', chain_id:'c3', thread_id:'t1', parent_chain_id:'c2'}, {type:'pane_run_start', mode:'Deep', of:15, dollars:1.5, chain_id:'c3'}, {type:'pane_turn_start', turn:1, seat:'Analyst', model:'grok', chain_id:'c3'}, {type:'pane_turn_end', turn:1, kind:'cell', thinking:'Ratios of consecutive terms.', note:'', code:'print(2)', elapsed:3, cost:0.01, chain_id:'c3'}])")
    pg.evaluate("navigateResponses(-1)"); pg.wait_for_timeout(200)
    pg.evaluate("feed([{type:'pane_cell', turn:1, cell_no:1, ok:true, chars:40, figs:1, peek:'phi 1.618', elapsed:0.1, chain_id:'c3'}])")
    r['run3_cell_in_holder'] = pg.evaluate("({holderHasPhi: liveState.holders.stream.innerHTML.includes('phi'), holderStream: !!liveState.holders.stream.querySelector('.sp-stream'), cellHtml: (liveState.holders.stream.querySelector('.sp-cell')||{outerHTML:'none'}).outerHTML.slice(0,200)})")
    r['run3_away'] = pg.evaluate("({label: document.getElementById('chainPosition').textContent, visibleHasRun3: document.getElementById('streamOutput').innerHTML.includes('Ratios of consecutive'), visibleIsChain2: document.getElementById('streamOutput').innerHTML.includes('sourced identity')})")
    pg.evaluate("navigateResponses(1)"); pg.wait_for_timeout(200)
    r['run3_back_mid_run'] = pg.evaluate("({label: document.getElementById('chainPosition').textContent, away: liveState.away, visibleHasRun3: document.getElementById('streamOutput').innerHTML.includes('Ratios of consecutive'), cellRow: document.getElementById('streamOutput').innerHTML.includes('phi 1.618')})")
    pg.evaluate("feed([{type:'answer', data:'# The golden ratio - phi is 1.618.', chain_id:'c3'}, {type:'pane_run_end', status:'answered', turns:1, of:15, cells:1, failed:0, cost:0.02, seconds:12, replay_status:'reproduced', replay_line:'replay reproduced 5 numbers', plots:1, chain_id:'c3'}])"); pg.evaluate("saveCurrentResponse();"); pg.wait_for_timeout(200)
    r['run3_ended_in_view'] = pg.evaluate("({n: responses.length, idx: currentResponseIndex, answerVisible: (document.querySelector('#content-answer .markdown-content')||{}).textContent, c3parent: responses[2].parentChainId, label: document.getElementById('chainPosition').textContent, lastActive: lastActiveChainId})")
    pg.screenshot(path='/tmp/live_nav.png')
    r['errors'] = [e[:400] for e in errs if not any(x in e for x in ('localforage', 'marked.Renderer', 'renderMathInElement'))][:5]
    print(json.dumps(r, indent=1)); b.close()
