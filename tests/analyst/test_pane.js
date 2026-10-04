// The left pane through save, restore, navigation and the run states - in node, on a small real DOM.
// Run: node tests/analyst/test_pane.js
'use strict';
const path = require('path');
const { makeDocument } = require(path.join(__dirname, 'minidom.js'));
const doc = makeDocument(); global.document = doc; global.window = {};
global.window.hljs = { highlightElement: el => el.classList.add('hljs') };
const pane = doc.createElement('div'); pane.setAttribute('id', 'streamOutput'); doc.body.appendChild(pane);
pane.innerHTML = '<div>New workflow started. Ready for your query.</div>';
require(path.join(__dirname, '..', '..', 'web_app', 'static', 'js', 'stream-pane.js'));
const w = window; const results = []; const check = (n, c, d) => results.push([n, !!c, d]);

// 1. a complete run
w.paneIds({thread_id:'1788644290', chain_id:1788644290, df_id:'df_x'});
w.paneRunStart({mode:'Deep', of:15, dollars:1.5});
w.paneTurnStart({turn:1, of:15, seat:'Analyst', model:'x-ai/grok-4.6', chain_id:1788644290});
check('placeholder gone; strip + ids + stream created; strip shows turn 1 as it starts', pane.querySelectorAll(':scope > div:not([class])').length === 0 && pane.querySelector('.sp-strip') && pane.querySelector('.sp-ids') && pane.querySelector('.sp-stream') && pane.querySelector('.sp-strip').textContent.includes('turn 1 of 15'));
w.paneToken('###THINKING###\nLook <b>first</b> & then model.\n###NOTE###\n- Question as understood: q "quoted"\n###ACTION###\nCELL\n```python\nprint("a<b")\n```');
let card = pane.querySelector('.sp-turn');
check('live: thinking as escaped prose, marker stripped, peek = first sentence, the note not shown', card.querySelector('.sp-think').innerHTML.includes('Look &lt;b&gt;first&lt;/b&gt; &amp; then model.') && !card.querySelector('.sp-think').innerHTML.includes('###') && card.querySelector('summary .peek').textContent === 'Look <b>first</b> & then model.' && !card.querySelector('.sp-think').innerHTML.includes('Question as understood'));
w.paneTurnEnd({turn:1, kind:'cell', thinking:'Look <b>first</b> & then model.', note:'- Question as understood: q "quoted"', code:'print("a<b")\nx = {"k": [1,2]}', elapsed:12.3, cost:0.012});
check('ended: collapsed, kind/meta set, note grid + highlighted code folded, cursor gone', !card.hasAttribute('open') && card.querySelector('summary .kind').textContent === 'cell' && card.querySelector('summary .meta').textContent === '12 s · $0.01' && card.querySelector('.sp-note').textContent.includes('q "quoted"') && card.querySelector('.sp-detail pre code').classList.contains('hljs') && !card.querySelector('.cursor') && card.querySelector('.sp-detail pre code').textContent.includes('print("a<b")'));
w.paneCell({cell_no:1, ok:true, peek:'rows 22705 <sess>', elapsed:0.1, chars:3129, figs:1});
w.paneTurnStart({turn:2, of:15, seat:'Analyst', model:'x-ai/grok-4.6', chain_id:1788644290});
w.paneThought('hidden reasoning');
w.paneTurnEnd({turn:2, kind:'cell', thinking:'', note:'', code:'1/0', elapsed:3, cost:0.001});
w.paneCell({cell_no:null, ok:false, error_line:"ZeroDivisionError: division by zero", elapsed:0.2});
w.paneLookupStart({kind:'search', query:'altitude & "pace"'});
const pendingSearch = pane.querySelector('.sp-row.tool.pending');
check('a SEARCH under way: a pending row with the pulse, the query and "searching the web…"', pendingSearch && pendingSearch.querySelector('.live') && pendingSearch.querySelector('.in').textContent.includes('SEARCH altitude') && pendingSearch.querySelector('.out').textContent === 'searching the web…');
w.paneLookup({kind:'search', query:'altitude & "pace"', peek:'r <1>', sources:[{title:'A & B', url:'https://x.y/a?b=1&c=2', host:'x.y'}]});
check('the search row replaces its pending row', !pane.querySelector('.sp-row.tool.pending') && pane.querySelectorAll('.sp-row.tool').length === 1);
w.paneLookupStart({kind:'read', query:'D1 the wet season', model:'deepseek/deepseek-v4.1-flash'});
check('a READ under way: the pending row names the Reader and its model', pane.querySelector('.sp-row.tool.pending .out').textContent === 'reading · Reader on deepseek-v4.1-flash…');
w.paneLookup({kind:'read', query:'D1 the wet season', peek:'An early wet season [D1.3].', sources:[], passages:[{id:'D1.3', where:'notes.md §Weather', quote:'rainfall was 40% above'}, {id:'D1.5', where:'notes.md §Weather', quote:'sown a week later'}]});
check('[D1.3] chip: a document citation with the READ row\'s passage as its hover text, opening the view at the unit; an unknown unit still opens the view',
      w.paneCite('doc', 'D1.3') === '<span class="cite doc" data-unit="D1.3" title="notes.md §Weather — &quot;rainfall was 40% above&quot;" onclick="if(typeof documentsOpenUnit===\'function\')documentsOpenUnit(\'D1.3\')">D1.3</span>'
      && w.paneCite('doc', 'D1.9').includes('title="open in the Documents view"') && w.paneCite('cell', '7') === '<span class="cite cell" onclick="if(typeof paneOpenCell===\'function\')paneOpenCell(7)">cell 7</span>', w.paneCite('doc', 'D1.3'));
check('the read marks the view reads are the same map', w.documentsReadMarks['D1.3'] && w.documentsReadMarks['D1.3'].quote === 'rainfall was 40% above' && !w.documentsReadMarks['D1.9']);
const cited = w.paneCiteHtml('<p>Rain was 40% above [D1.3] and plots [cell 2] <code>x[D1.3]</code> <a title="[cell 9]">t</a></p>');
check('paneCiteHtml: chips in the text between tags - a document chip with its passage, a cell chip - and nothing inside a tag is touched',
      cited.includes('data-unit="D1.3"') && cited.includes('paneOpenCell(2)') && cited.includes('title="[cell 9]"') && cited.split('class="cite').length === 4, cited);
w.paneLookupStart({kind:'replay', query:'9 cells', model:''});
check('the replay under way: a pulsing REPLAY row saying it reproduces the report\'s cells in a fresh kernel', !!pane.querySelector('.sp-row.tool.pending[data-pending="replay"]') && pane.querySelector('.sp-row.tool.pending[data-pending="replay"]').textContent.includes('fresh kernel'));
w.paneLookup({kind:'replay', query:'', peek:'Replay reproduced the cited results in a fresh run (9 cells, 41 numbers).', sources:[], passages:[]});
check('the replay done: the pending row is gone and a REPLAY row carries the replay line', !pane.querySelector('.sp-row.tool.pending[data-pending="replay"]') && Array.from(pane.querySelectorAll('.sp-row.tool')).some(r => r.textContent.includes('REPLAY') && r.textContent.includes('41 numbers')));
const readRow = pane.querySelector('.sp-row.tool.read');
check('the READ row: ¶ glyph, READ label with the query, the summary as peek, "2 passages" on the right; the pending row gone', readRow && readRow.textContent.includes('¶') && readRow.querySelector('.in').textContent.startsWith('READ D1 the wet season') && readRow.querySelector('.out').textContent === 'An early wet season [D1.3].' && readRow.querySelector('.t').textContent === '2 passages' && !pane.querySelector('.sp-row.tool.pending'));
w.paneDatasets({files:[{path:"generated/it's.csv", rows:45}]});
w.paneHeartbeat({turn:2, of:15, spent:0.013, dollars:1.5, estimate:'ratio 1.06 [1.02, 1.10] "matched HR"', mode:'Deep'});
w.paneRunEnd({status:'answered', turns:2, of:15, cells:1, failed:1, cost:0.013, seconds:16, replay_status:'reproduced', replay_line:'Replay reproduced (1 cells, 3 numbers)', plots:1, files:[{path:'generated/x.csv'}]});
const cards = pane.querySelectorAll('.sp-turn');
check('second turn: reasoning block kept (had content), no think block (empty), peek = code line', cards.length === 2 && cards[1].querySelector('.sp-reasoning') && !cards[1].querySelector('.sp-think') && cards[1].querySelector('summary .peek').textContent === '1/0');
check('rows: In [1]; a failed row with the exception line; a search row with a source pill; a dataset pill', pane.querySelector('.sp-row .in').textContent.replace(/\s/g,'') === 'In[1]' && pane.querySelector('.sp-row.fail .out').textContent.startsWith('ZeroDivisionError') && pane.querySelector('.sp-pill.src').getAttribute('href') === 'https://x.y/a?b=1&c=2' && pane.querySelector('.sp-pill.ds'));
check('strip: settled on the final turn and spend, estimate shown, idle dot', pane.querySelector('.sp-strip').textContent.includes('turn 2 of 15') && pane.querySelector('.sp-strip .est').textContent.includes('ratio 1.06') && pane.querySelector('.sp-strip .live').classList.contains('idle'));
check('closing card: counts, replay line, four links, dataset pill', pane.querySelector('.sp-done .grid').textContent.includes('2 of 15') && pane.querySelector('.sp-done .rep').textContent.includes('Replay reproduced') && pane.querySelectorAll('.sp-done a').length === 4 && pane.querySelector('.sp-done .sp-pill.ds'));

// 2. save to favourites = innerHTML; restore = innerHTML into a fresh element (a reload, a navigation arrow, a map click)
w.paneHeartbeat({turn:9, of:15, spent:0.09, dollars:1.5, estimate:'x', mode:'Deep'});
w.paneTurnStart({turn:10, of:15, seat:'Analyst', model:'m'}); w.paneTurnEnd({turn:10, kind:'names', thinking:'', note:'', code:'', elapsed:1, cost:0.001});
check('a turn start moves the strip: turn 10 of 15', pane.querySelector('.sp-strip').textContent.includes('turn 10 of 15'));
const saved = pane.innerHTML;
const pane2 = doc.createElement('div'); pane2.setAttribute('id', 'streamOutput'); pane.remove(); doc.body.appendChild(pane2);
pane2.innerHTML = saved;
check('restore round-trip: the saved HTML re-parses to the same HTML', pane2.innerHTML === saved);
check('restored: cards collapsed with their folds, rows, pills, strip and ids present', pane2.querySelectorAll('.sp-turn').length === 3 && pane2.querySelectorAll('.sp-turn[open]').length === 0 && pane2.querySelector('.sp-note') && pane2.querySelectorAll('.sp-row').length === 5 && pane2.querySelectorAll('.sp-ids .v')[1].textContent === '1788644290');   // 5 rows: In [1], the failed cell, the search row, the REPLAY row, the READ row and three LOOK rows (2026-10-03)
const dsClick = pane2.querySelector('.sp-pill.ds').getAttribute('onclick');
let called = null; global.downloadFile = p => { called = p; }; new Function(dsClick)();
check("restored handlers: the dataset pill's inline handler runs and passes the exact path (apostrophe included)", called === "generated/it's.csv", dsClick);
check('restored handlers: run-log buttons carry agent + chain (document-level delegation); cell rows carry data-cell', pane2.querySelector('.agent-instructions-btn').getAttribute('data-chain') === '1788644290' && pane2.querySelector('.agent-instructions-btn').getAttribute('data-agent') === 'Analyst' && pane2.querySelector('.sp-row[data-cell]').getAttribute('data-cell') === '1');

// 3. after navigating to a restored chain, a new question: the submit path clears the pane, a fresh chain renders
pane2.innerHTML = '';
w.paneIds({thread_id:'1788644290', chain_id:1788644999, df_id:'df_x'}); w.paneRunStart({mode:'Quick', of:2, dollars:0.2});
w.paneTurnStart({turn:1, of:2, seat:'Analyst', model:'m', chain_id:1788644999}); w.paneToken('###THINKING###\nA quick one.\n###NOTE###\n- Question as understood: q');
w.paneTurnEnd({turn:1, kind:'report', thinking:'A quick one.', note:'- Question as understood: q', code:'', elapsed:2, cost:0.001});
w.paneRunEnd({status:'answered', turns:1, of:2, cells:0, failed:0, cost:0.001, seconds:2, replay_status:'', replay_line:'', plots:0, files:[]});
check('new chain after a restore: one strip, the new chain id, one card, a closing card with no replay line, strip at 1 of 2', pane2.querySelectorAll('.sp-strip').length === 1 && pane2.querySelectorAll('.sp-ids .v')[1].textContent === '1788644999' && pane2.querySelectorAll('.sp-turn').length === 1 && !pane2.querySelector('.sp-done .rep') && pane2.querySelector('.sp-strip').textContent.includes('turn 1 of 2'));

// 4. a lost turn, then a stopped run
pane2.innerHTML = '<div>Ready for your query.</div>';
w.paneIds({thread_id:'t', chain_id:3, df_id:'d'}); w.paneRunStart({mode:'Deep', of:15, dollars:1.5});
w.paneTurnStart({turn:1, of:15, seat:'Analyst', model:'m', chain_id:3}); w.paneToken('###THINKING###\nHalf a thought');
w.paneTurnStart({turn:2, of:15, seat:'Analyst', model:'m', chain_id:3});
check('a turn that never ended closes as lost when the next starts', pane2.querySelectorAll('.sp-turn')[0].classList.contains('lost') && !pane2.querySelectorAll('.sp-turn')[0].hasAttribute('open') && pane2.querySelectorAll('.sp-turn')[1].classList.contains('live'));
w.paneRunEnd({status:'stopped', turns:2, of:15, cells:0, failed:0, cost:0.01, seconds:5, replay_status:'', replay_line:'', plots:0, files:[]});

check('stopped run: the live card closed, the closing card says stopped, no tab links', !pane2.querySelector('.sp-turn.live') && pane2.querySelector('.sp-done .title').textContent === 'Run stopped' && pane2.querySelectorAll('.sp-done a').length === 0);
w.paneRunEnd({status:'answered', turns:31, of:15, cells:7, failed:2, cost:0.4, seconds:300, replay_status:'', replay_line:'', plots:0, files:[]});
const grids = pane2.querySelectorAll('.sp-done .grid'); const lastGrid = grids[grids.length - 1].textContent;
check('closing card: "Turns 31 of 15", "Cells 7 (2 failed)"', lastGrid.includes('Turns 31 of 15') && lastGrid.includes('Cells 7 (2 failed)') && !lastGrid.includes('Cell turns'), lastGrid);

// 5. tokens with no live turn are refused (the dispatcher then appends plain text itself)
check('no live turn: tokens and thoughts refused', w.paneToken('x') === false && w.paneThought('y') === false);

// 6. a legacy favourite restores untouched
const legacy = '<div class="session-ids"><div class="id-row"><span class="id-label">Workflow ID:</span> <span class="id-value">1</span></div></div><div class="tool-call thinking"><div class="thoughts-container"><div class="thought-stream">old</div></div></div>';
pane2.innerHTML = legacy;
check('a legacy favourite restores byte-identical', pane2.innerHTML === legacy);

// 7. an ASK run: the closing card names it
pane2.innerHTML = ''; w.paneIds({thread_id:'t', chain_id:4, df_id:'d'}); w.paneRunStart({mode:'Deep', of:15, dollars:1.5});
w.paneTurnStart({turn:1, of:15, seat:'Analyst', model:'m', chain_id:4}); w.paneTurnEnd({turn:1, kind:'ask', thinking:'The brief is ambiguous.', note:'', code:'', elapsed:3, cost:0.002});
w.paneRunEnd({status:'asked', turns:1, of:15, cells:0, failed:0, cost:0.002, seconds:3, replay_status:'', replay_line:'', plots:0, files:[]});
check('an ASK run: kind "question", the closing card says the analyst has a question', pane2.querySelector('.sp-turn summary .kind').textContent === 'question' && pane2.querySelector('.sp-done .title').textContent.includes('question'));

// 8. a quiet card (the infographic's YAML never shows) and the telemetry folded into the closing card
pane2.innerHTML = ''; w.paneIds({thread_id:'t', chain_id:5, df_id:'d'}); w.paneRunStart({mode:'Deep', of:15, dollars:1.5});
w.paneTurnStart({turn:'infographic', of:null, seat:'Image Generator', model:'', quiet:true, chain_id:5});
w.paneToken('title: x\nsections:\n  - a'); 
const quiet = pane2.querySelector('.sp-turn.quiet');
check('quiet card: not open, shows "working…", and its tokens are not rendered', quiet && !quiet.hasAttribute('open') && quiet.querySelector('summary .kind').textContent === 'working…' && !quiet.querySelector('.sp-think').textContent.includes('title: x'));
w.paneTurnEnd({turn:'infographic', kind:'infographic', peek:'infographic drawn', elapsed:9, cost:null, thinking:'', note:'', code:''});
check('quiet card ended: kind infographic, peek, no think block', quiet.querySelector('summary .kind').textContent === 'infographic' && quiet.querySelector('summary .peek').textContent === 'infographic drawn' && !quiet.querySelector('.sp-think'));
w.paneRunEnd({status:'answered', turns:1, of:15, cells:0, failed:0, cost:0.05, seconds:9, replay_status:'', replay_line:'', plots:0, files:[]});
w.paneSummary('Analyst: 12 calls, 143,000 tokens, $0.44\nImage Generator: 1 call');
check('telemetry: folded into the closing card as a collapsible pre', pane2.querySelector('.sp-done .sp-telemetry pre').textContent.includes('Analyst: 12 calls') && !pane2.querySelector('.sp-done .sp-telemetry').hasAttribute('open'));

let fails = 0; for (const [n, ok, d] of results) { console.log((ok ? '  ok   ' : '  FAIL ') + n + (ok ? '' : '  <- ' + (d || ''))); if (!ok) fails++; }
console.log(`\n${results.length - fails} passed, ${fails} failed`); process.exit(fails ? 1 : 0);
