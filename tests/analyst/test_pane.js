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
w.paneToken('###STEP###\nLook <b>first</b> & then model.\n###NOTE###\n- Question as understood: q "quoted"\n###ACTION###\nCELL\n```python\nprint("a<b")\n```');
let card = pane.querySelector('.sp-turn');
check('live: the step as escaped prose, the STEP marker stripped, peek = first sentence, the note not shown', card.querySelector('.sp-think').innerHTML.includes('Look &lt;b&gt;first&lt;/b&gt; &amp; then model.') && !card.querySelector('.sp-think').innerHTML.includes('###') && card.querySelector('summary .peek').textContent === 'Look <b>first</b> & then model.' && !card.querySelector('.sp-think').innerHTML.includes('Question as understood'));
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
      && w.paneCite('doc', 'D1.9').includes('title="open in the Documents view"') && w.paneCite('cell', '7') === '<span class="cite cell" title="How this number was made" onclick="if(typeof paneOpenRecipe===\'function\')paneOpenRecipe(this,7)">cell 7</span>', w.paneCite('doc', 'D1.3'));
check('the read marks the view reads are the same map', w.documentsReadMarks['D1.3'] && w.documentsReadMarks['D1.3'].quote === 'rainfall was 40% above' && !w.documentsReadMarks['D1.9']);
const cited = w.paneCiteHtml('<p>Rain was 40% above [D1.3] and plots [cell 2] <code>x[D1.3]</code> <a title="[cell 9]">t</a></p>');
check('paneCiteHtml: chips in the text between tags - a document chip with its passage, a cell chip - and nothing inside a tag is touched',
      cited.includes('data-unit="D1.3"') && cited.includes('paneOpenRecipe(this,2)') && cited.includes('title="[cell 9]"') && cited.split('class="cite').length === 4, cited);
// a READ over the context (docs/CONTEXT_DESIGN.md S2): the chip's hover carries the passage's day, kind and author with the
// quote, and the original beneath it when the quote is a rendering; the click lands on the READ in the Investigation tab
w.paneLookupStart({kind:'read', query:'CTX the legs on the climbs', model:'deepseek/deepseek-v4.1-flash'});
w.paneLookup({kind:'read', query:'CTX the legs on the climbs', peek:'Heavy legs on the first climb [C.417].', sources:[], passages:[
    {id:'C.417', where:'2026-08-14 · activity_message · subject (rendered from da)', quote:'Legs were heavy from the first climb', original:'Benene var tunge fra den første stigning'},
    {id:'C.420', where:'2026-08-16 · day_note · subject', quote:'slept badly'}]});
const ctxChip = w.paneCite('ctx', 'C.417');
check('[C.417] chip: a context citation whose hover shows where, the quote and the original it was rendered from; the click opens the READ in the Investigation tab',
      ctxChip === '<span class="cite ctx" data-unit="C.417" title="2026-08-14 · activity_message · subject (rendered from da) — &quot;Legs were heavy from the first climb&quot;\noriginal: &quot;Benene var tunge fra den første stigning&quot;" onclick="if(typeof paneOpenPassage===\'function\')paneOpenPassage(\'C.417\')">C.417</span>', ctxChip);
check('an English passage shows no original line; an unknown passage says how to print it in a cell',
      !w.paneCite('ctx', 'C.420').includes('original:') && w.paneCite('ctx', 'C.420').includes('day_note · subject — &quot;slept badly&quot;') && w.paneCite('ctx', 'C.9').includes("title=\"a passage of the context: print(CTX.text('C.9')) in a cell\""), w.paneCite('ctx', 'C.9'));
const citedCtx = w.paneCiteHtml('<p>Heavy legs [C.417], a document [D1.3], a cell [cell 2] and <code>CTX.text(\'C.417\')</code></p>');
check('paneCiteHtml: a context chip beside a document chip and a cell chip; C.417 inside the code tag is not a chip',
      citedCtx.includes('class="cite ctx" data-unit="C.417"') && citedCtx.includes('data-unit="D1.3"') && citedCtx.includes('paneOpenRecipe(this,2)') && citedCtx.split('class="cite').length === 4 && citedCtx.includes("<code>CTX.text('C.417')</code>"), citedCtx);
// a passage named by its bare id (2026-10-14: the first live run wrote "C.39 - written 4 August" and cited cells beside): a chip
// when the passage is known, left alone otherwise and inside code; the report's cited passages arrive before the answer renders
w.panePassages({passages:[{id:'C.600', where:'2026-09-01 · day_note · subject', quote:'slept badly, legs flat all day'}, {id:'C.417', where:'overwritten?', quote:'no'}, {id:'D1.5', where:'notes.md §Weather', quote:'sown a week later'}]});
const bare = w.paneCiteHtml('<p><strong>C.600 - written 2026-09-01</strong> [cell 9]; C.417 again; C.601 unknown. See D1.5 and D1.2.5; <code>CTX.text(\'C.600\')</code> and <pre><code>print(CTX.text(\'C.417\'))</code></pre> end C.600.</p>');
check('bare ids: C.600 and C.417 (known) and D1.5 (known) become chips, C.601 (unknown) and D1.2.5 do not, nothing inside code or pre; a sentence-ending full stop is allowed; the bracketed [cell 9] still a chip',
      bare.split('class="cite ctx"').length === 4 && bare.split('class="cite doc"').length === 2 && bare.includes('C.601 unknown') && bare.includes('D1.2.5') && bare.includes("<code>CTX.text('C.600')</code>") && bare.includes("<pre><code>print(CTX.text('C.417'))</code></pre>") && bare.includes('paneOpenRecipe(this,9)') && bare.endsWith('>C.600</span>.</p>'), bare);
check('panePassages fills the hover of a passage no READ returned and keeps the READ\'s verified quote where one exists',
      w.paneCite('ctx', 'C.600').includes('day_note · subject — &quot;slept badly, legs flat all day&quot;') && w.paneCite('ctx', 'C.417').includes('Legs were heavy from the first climb') && !w.paneCite('ctx', 'C.417').includes('overwritten'), w.paneCite('ctx', 'C.417'));
delete w.documentsReadMarks['C.600']; delete w.documentsReadMarks['D1.5'];
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
check('closing card: the run\'s numbers beside its title, the replay line, no link to a tab (0313) - and no dataset pill of its own (the pills ride once, under the REPLAY row; 2026-10-06)',
  pane.querySelector('.sp-done .head .nums').textContent.includes('2 of 15 turns') && pane.querySelector('.sp-done .head .title').textContent === 'Run complete' && pane.querySelector('.sp-done .rep').textContent.includes('Replay reproduced')
  && pane.querySelectorAll('.sp-done a').length === 0 && !pane.querySelector('.sp-done .grid') && !pane.querySelector('.sp-done .links') && !pane.querySelector('.sp-done .sp-pill.ds') && pane.querySelectorAll('.sp-pill.ds').length === 1,
  pane.querySelector('.sp-done').outerHTML);

// 2. save to favourites = innerHTML; restore = innerHTML into a fresh element (a reload, a navigation arrow, a map click)
w.paneHeartbeat({turn:9, of:15, spent:0.09, dollars:1.5, estimate:'x', mode:'Deep'});
w.paneTurnStart({turn:10, of:15, seat:'Analyst', model:'m'}); w.paneTurnEnd({turn:10, kind:'names', thinking:'', note:'', code:'', elapsed:1, cost:0.001});
check('a turn start moves the strip: turn 10 of 15', pane.querySelector('.sp-strip').textContent.includes('turn 10 of 15'));
const saved = pane.innerHTML;
const pane2 = doc.createElement('div'); pane2.setAttribute('id', 'streamOutput'); pane.remove(); doc.body.appendChild(pane2);
pane2.innerHTML = saved;
check('restore round-trip: the saved HTML re-parses to the same HTML', pane2.innerHTML === saved);
check('restored: cards collapsed with their folds, rows, pills, strip and ids present', pane2.querySelectorAll('.sp-turn').length === 3 && pane2.querySelectorAll('.sp-turn[open]').length === 0 && pane2.querySelector('.sp-note') && pane2.querySelectorAll('.sp-row').length === 6 && pane2.querySelectorAll('.sp-ids .v')[1].textContent === '1788644290');   // 6 rows: In [1], the failed cell, the search row, the REPLAY row, the two READ rows (2026-10-14: one over the context)
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
check('the THINKING marker of earlier runs is stripped from the live card too (the marker until 0104)', !pane2.querySelector('.sp-turn .sp-think').innerHTML.includes('###') && pane2.querySelector('.sp-turn .sp-think').innerHTML.includes('Half a thought'));
w.paneTurnStart({turn:2, of:15, seat:'Analyst', model:'m', chain_id:3});
check('a turn that never ended closes as lost when the next starts', pane2.querySelectorAll('.sp-turn')[0].classList.contains('lost') && !pane2.querySelectorAll('.sp-turn')[0].hasAttribute('open') && pane2.querySelectorAll('.sp-turn')[1].classList.contains('live'));
w.paneRunEnd({status:'stopped', turns:2, of:15, cells:0, failed:0, cost:0.01, seconds:5, replay_status:'', replay_line:'', plots:0, files:[]});

check('stopped run: the live card closed, the closing card says stopped, and has no row of things to do next', !pane2.querySelector('.sp-turn.live') && pane2.querySelector('.sp-done .title').textContent === 'Run stopped'
  && pane2.querySelectorAll('.sp-done a').length === 0 && !pane2.querySelector('.sp-done .acts') && !pane2.querySelector('.sp-done button'));
w.paneRunEnd({status:'answered', turns:31, of:15, cells:7, failed:2, cost:0.4, seconds:300, replay_status:'', replay_line:'', plots:0, files:[]});
const allNums = pane2.querySelectorAll('.sp-done .nums'); const lastNums = allNums[allNums.length - 1].textContent;
check('closing card: "31 of 15 turns", "7 cells (2 failed)", the cost and the time, a dot between each - and no word of plots where the run drew none', lastNums === '31 of 15 turns · 7 cells (2 failed) · $0.40 · 5 min 0 s', lastNums);

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

// the routine's rows (2026-10-10, docs/ROUTINES_DESIGN.md): the promoter's quiet card, then run zero as a look-up row
pane2.innerHTML = '<div>Ready for your query.</div>';
w.paneTurnStart({turn:'routine', of:null, seat:'Analyst', model:'anthropic/claude-sonnet-5-5', quiet:true});
const rc = pane2.querySelector('.sp-turn');
check('routine card: labelled Routine, quiet (working…, nothing streamed into it)', rc && rc.querySelector('summary .n').textContent === 'Routine' && rc.querySelector('summary .kind').textContent === 'working…' && w.paneToken('{"inputs": []}') === true && !rc.querySelector('.sp-think').textContent.includes('inputs'));
w.paneTurnEnd({turn:'routine', kind:'routine', peek:'2 input(s) proposed, 3 edit(s)', elapsed:9.1, cost:0.03, thinking:'', note:'', code:''});
check('routine card ended: kind routine, the peek says what was proposed, the meta its time and cost', rc.querySelector('summary .kind').textContent === 'routine' && rc.querySelector('summary .peek').textContent === '2 input(s) proposed, 3 edit(s)' && rc.querySelector('summary .meta').textContent === '9.1 s · $0.03');
w.paneLookupStart({kind:'routine', query:'Rows above a line', model:''});
check('run zero under way: a pending ROUTINE row saying the method is being checked on this chain\'s data', pane2.querySelector('.sp-row.tool.pending .in').textContent === 'ROUTINE Rows above a line' && pane2.querySelector('.sp-row.tool.pending .out').textContent === 'checking the method on this chain\'s own data…');
w.paneLookup({kind:'routine', query:'Rows above a line', peek:'reproduced: 9 result line(s) identical', sources:[], passages:[]});
check('run zero done: the ROUTINE row with the ↻ glyph replaces the pending one and carries the verdict', !pane2.querySelector('.sp-row.tool.pending') && pane2.querySelector('.sp-row.tool').textContent.startsWith('↻ROUTINE Rows above a line') && pane2.querySelector('.sp-row.tool .out').textContent.startsWith('reproduced: 9'));
// a LOAD row's text whole (2026-11-08: cut at 120 characters and set nowrap, it ran past the pane); the stylesheet lets a tool row's text wrap
const longLoad = 'Intervals.icu · First Athlete · 2025-12-01 → 2025-12-31 · summary, rider, context, plan · cut from the cached load 2025-11-01 → 2026-01-31 · 61 of 92 days from the store, 31 downloaded';
w.paneLookupStart({kind:'load', query:longLoad, model:''});
check('a pending LOAD row carries the query whole', pane2.querySelector('.sp-row.tool.pending .in').textContent === 'LOAD ' + longLoad);
w.paneLookup({kind:'load', query:longLoad, peek:'', sources:[], passages:[]});
const loadRow = Array.from(pane2.querySelectorAll('.sp-row.tool')).pop();
const paneCss = require('fs').readFileSync(require('path').join(__dirname, '..', '..', 'web_app', 'static', 'css', 'pane.css'), 'utf8');
check('the LOAD row carries the query whole, no cap; the stylesheet wraps a tool row\'s text (normal white space, a minimum width of nought) where a cell row\'s badge stays on one line',
  loadRow.querySelector('.in').textContent === 'LOAD ' + longLoad && paneCss.includes('#streamOutput .sp-row.tool .in { white-space: normal; min-width: 0; overflow-wrap: anywhere; }') && paneCss.includes("#streamOutput .sp-row .in { font-family: 'Courier New', Courier, monospace; color: var(--yaml-key); white-space: nowrap; }"));

// the figures step after the report (2026-10-11): a quiet 'Figures' card per attempt, a correction named as such, its end line
// from the session; a cell the analysis did not run as a skipped row
pane2.innerHTML = ''; w.paneIds({thread_id:'t', chain_id:7, df_id:'d'}); w.paneRunStart({mode:'Deep', of:15, dollars:1});
w.paneCell({cell_no:null, ok:true, skipped:true, peek:'not run: figures are drawn after the report', elapsed:null, chars:0, figs:0});
const skippedRow = Array.from(pane2.querySelectorAll('.sp-row')).pop();
check('a skipped cell row: In [–], the dash glyph, the peek, "not run" in the meta, no fail colour, not clickable',
      skippedRow.classList.contains('skipped') && !skippedRow.classList.contains('fail') && /In.\[(&ndash;|–)\]/.test(skippedRow.querySelector('.in').textContent) && skippedRow.querySelector('.out').textContent.startsWith('not run: figures')
      && skippedRow.querySelector('.t').textContent === 'not run' && !skippedRow.hasAttribute('data-cell'), skippedRow.outerHTML);
w.paneTurnStart({turn:'figures', of:15, seat:'Analyst', model:'m', quiet:true, attempt:1});
const figCard1 = Array.from(pane2.querySelectorAll('.sp-turn')).pop();
w.paneToken('```python\nfig.show()\n```');
check('the Figures card: labelled Figures, quiet (nothing streams, "working…"), collapsed while live', figCard1.querySelector('summary .n').textContent === 'Figures' && figCard1.classList.contains('quiet') && figCard1.querySelector('summary .kind').textContent === 'working…' && !figCard1.querySelector('.sp-think').textContent.includes('fig.show') && !figCard1.hasAttribute('open'), figCard1.outerHTML);
w.paneTurnEnd({turn:'figures', kind:'figures', thinking:'', note:'', code:'fig.show()', elapsed:4, cost:0.002, peek:'figure cell: the estimate with its interval'});
check('the Figures card ended: kind "figures", the peek the session sent, the code folded', figCard1.querySelector('summary .kind').textContent === 'figures' && figCard1.querySelector('summary .peek').textContent === 'figure cell: the estimate with its interval' && figCard1.querySelector('.sp-detail pre code').textContent === 'fig.show()', figCard1.outerHTML);
w.paneCell({cell_no:null, ok:false, error_line:'ValueError: bad trace', elapsed:0.3});
w.paneTurnStart({turn:'figures', of:15, seat:'Analyst', model:'m', quiet:true, attempt:2});
const figCard2 = Array.from(pane2.querySelectorAll('.sp-turn')).pop();
check('a second attempt is "Figures · correction 1"', figCard2.querySelector('summary .n').textContent === 'Figures · correction 1', figCard2.querySelector('summary .n').textContent);
w.paneTurnEnd({turn:'figures', kind:'figures', thinking:'', note:'', code:'fig.show()', elapsed:4, cost:0.002, peek:'figure cell: the estimate with its interval'});
w.paneCell({cell_no:12, ok:true, peek:'', elapsed:0.3, chars:0, figs:2});
check('the figures cell row: In [12] with 2 fig', Array.from(pane2.querySelectorAll('.sp-row')).pop().querySelector('.t').textContent.includes('2 fig'));

// 7. a reply with a tool call in it (2026-10-18): nothing of the call streams into the step, and the finished card is the
// turn the session read - a cell, not a lost turn - with the step it read, or none
w.paneRunStart({mode:'Deep', of:15, dollars:1.5});
w.paneTurnStart({turn:3, of:15, seat:'Analyst', model:'m'});
w.paneToken('\n<invoke name="python">\n<parameter name="code">\nprint(1)\n');
const tc = Array.from(pane2.querySelectorAll('.sp-turn')).pop();
const tcLive = tc.querySelector('.sp-think').textContent;
w.paneToken('</parameter>\n</invoke>\n');
w.paneTurnEnd({turn:3, kind:'cell', thinking:'', note:'', code:'print(1)', elapsed:1, cost:0.001});
check('a cell written as a tool call: nothing of the call in the live step; the card ends as a cell, with no step and the code in its detail, not lost',
      !tcLive.includes('invoke') && !tcLive.includes('print(1)') && tc.querySelector('summary .kind').textContent === 'cell' && !tc.classList.contains('lost')
      && !tc.querySelector('.sp-think') && tc.querySelector('summary .peek').textContent === 'print(1)' && tc.querySelector('.sp-detail pre code').textContent.includes('print(1)'), tc.innerHTML.slice(0, 300));
w.paneTurnStart({turn:4, of:15, seat:'Analyst', model:'m'});
w.paneToken('###STEP###\nI print the table.\n<invoke name="x">\n</invoke>\n```python\nprint(2)\n```\n###STEP###\nThe step it read.\n###NOTE###\n- Names: df\n###ACTION###\n```python\nprint(2)\n```');
const tc2 = Array.from(pane2.querySelectorAll('.sp-turn')).pop();
const tc2Live = tc2.querySelector('.sp-think').textContent;
w.paneTurnEnd({turn:4, kind:'cell', thinking:'The step it read.', note:'- Names: df', code:'print(2)', elapsed:1, cost:0.001});
check('a call before the turn format: the live step stops where the call begins; the finished card shows the step the session read',
      tc2Live.startsWith('I print the table.') && !tc2Live.includes('invoke') && tc2.querySelector('.sp-think').textContent === 'The step it read.', [tc2Live, tc2.querySelector('.sp-think') && tc2.querySelector('.sp-think').textContent]);

// a [cell n] chip opens the code trace on that number (2026-10-24): the chip hands the map its cell and the sentence it sits in
const opened = []; w.CodeMapUI = { open: (id, o) => opened.push([id, o]) };
const para = doc.createElement('p'); para.innerHTML = w.paneCiteHtml('<p>The medians were equal (28 vs 28) [cell 1]. Survivors are on average 2.3 years younger (95% CI −4.5 to −0.1) [cell 2].</p>').replace(/^<p>|<\/p>$/g, '');
w.paneOpenRecipe(para.querySelectorAll('.cite.cell')[1], 2);
check('a [cell n] chip opens the map on the diagram at that cell, with the words of its block for the number the sentence names (the whole block where the DOM cannot cut at the chip)',
      opened.length === 1 && opened[0][0] === null && opened[0][1].view === 'diagram' && opened[0][1].cell === 2 && opened[0][1].near.includes('2.3 years younger (95% CI −4.5 to −0.1)'), opened);
delete w.CodeMapUI;

// Open in the notebook with the lines behind a number (2026-10-24): bars behind the code, per span, the RESULT's own strong; the last lighting cleared
const nbTab = doc.createElement('div'); nbTab.className = 'tab'; nbTab.textContent = 'Investigation'; nbTab.click = () => {}; doc.body.appendChild(nbTab);
const nb = doc.createElement('div'); nb.innerHTML = '<div class="briefing-content"><div class="nb-cell"><div class="nb-cell-head"><span class="nb-cell-idx">In&nbsp;[1]</span></div><pre class="nb-code"><code class="language-python">a = 1\nb = 2</code></pre></div>'
  + '<div class="nb-cell"><div class="nb-cell-head"><span class="nb-cell-idx">In&nbsp;[2]</span></div><pre class="nb-code"><code class="language-python">x = 1\ny = 2\nz = 3\nRESULT(z)</code></pre></div></div>'; doc.body.appendChild(nb);
global.getComputedStyle = () => ({ paddingTop: '16px', paddingBottom: '16px', lineHeight: '20px' });
nb.querySelectorAll('pre code').forEach(c => { c.offsetTop = 0; c.clientHeight = 112; }); nb.querySelectorAll('.nb-cell-idx').forEach(h => { h.scrollIntoView = () => {}; });
const timers = []; const realTimeout = global.setTimeout; global.setTimeout = (fn) => { timers.push(fn); return 0; };
w.paneOpenCell(2, { lines: { '1': [[1, 1]], '2': [[1, 2], [4, 4]] }, own: { '2': [[4, 4]] } }); timers.splice(0).forEach(fn => fn());
const bars = nb.querySelectorAll('.nb-hl');
check('Open in the notebook with a recipe: one bar per span in each cell of the recipe, placed by line below the code\'s top padding, the RESULT\'s own line marked',
      bars.length === 3 && bars.map(b => b.className).join('|') === 'nb-hl|nb-hl|nb-hl own' && bars[1].style.top === '16px' && bars[1].style.height === '40px' && bars[2].style.top === '76px' && bars[2].style.height === '20px', bars.map(b => [b.className, b.style.top, b.style.height]));
w.paneOpenCell(1); timers.splice(0).forEach(fn => fn());
check('opening a cell without a recipe clears the last lighting', nb.querySelectorAll('.nb-hl').length === 0);
global.setTimeout = realTimeout;

// the reach report (2026-10-28): a cell that reached outside the data carries a tag after its peek, the kernel's colour unless
// the question asked for it; a cell the executor refused is its own row, neither ran nor failed; the closing card lists the
// reaches with their cells and tags, the refused cells, and the box in one line; a run that reached nothing says so quietly
w.paneRunStart({mode:'Deep', of:15, dollars:1}); w.paneTurnStart({turn:1, of:15, seat:'Analyst', model:'m'}); w.paneTurnEnd({turn:1, kind:'cell', thinking:'t', note:'', code:'import requests', elapsed:1, cost:0.001});
w.paneCell({cell_no:15, ok:true, peek:'downloaded 1258291 bytes', elapsed:0.9, chars:30, figs:0, reach:{text:'↓ 1.3 MB from data.example.org', tag:'asked', title:'fetched 1.3 MB from data.example.org:443, sent 812 B over TLS · the question named it'}});
w.paneCell({cell_no:16, ok:true, peek:'posted summary table', elapsed:0.8, chars:212, figs:0, reach:{text:'↑ 42.0 KB to 203.0.113.9:8080', tag:'unasked', title:'sent 42.0 KB to 203.0.113.9:8080 · not asked for'}});
w.paneCell({cell_no:null, ok:false, refused:'subprocess', peek:'', elapsed:null, chars:0, figs:0, error_line:'Security notice: code contains restricted module (subprocess) and was not executed.', reach:{}});
const r15 = pane2.querySelector('.sp-row[data-cell="15"]'), r16 = pane2.querySelector('.sp-row[data-cell="16"]'), rr = pane2.querySelector('.sp-row.restricted');
check('reach tags: an asked-for reach plain, a reach not asked for in the kernel\'s colour, both with the full line as hover', r15 && r15.querySelector('.reach') && !r15.querySelector('.reach').classList.contains('unasked') && r15.querySelector('.reach').textContent === '↓ 1.3 MB from data.example.org'
      && r16 && r16.querySelector('.reach.unasked') && r16.querySelector('.reach.unasked').getAttribute('title').endsWith('not asked for'), r15 && r15.innerHTML);
check('a refused cell: its own row - ⊘, In [–], "not run: restricted operation (subprocess)", "not run" - not red, not clickable', rr && !rr.classList.contains('fail') && rr.textContent.includes('⊘') && /In.\[(&ndash;|–)\]/.test(rr.querySelector('.in').textContent)
      && rr.querySelector('.out').textContent === 'not run: restricted operation (subprocess)' && rr.querySelector('.t').textContent === 'not run' && !rr.hasAttribute('onclick') && !rr.querySelector('.reach'), rr && rr.outerHTML);
w.paneRunEnd({status:'answered', turns:3, of:15, cells:2, failed:0, refused:1, cost:0.01, seconds:5, replay_status:'', replay_line:'', plots:0, files:[], chain_id:'1',
              reaches:{lines:[{where:'cell 15', kind:'net', text:'fetched 1.3 MB from data.example.org:443, sent 812 B over TLS', tag:'asked'}, {where:'cell 16', kind:'net', text:'sent 42.0 KB to 203.0.113.9:8080', tag:'unasked'}],
                       refused:[{where:'attempt after cell 16', word:'subprocess', text:'not run: restricted operation (subprocess)'}],
                       counts:{lines:2, unasked:1, asked:1, blocked:0, refused:1, net:2}, sandbox:'appuser (not root); in docker; no notable capabilities; seccomp filter; metadata address refused; 1 mount: /app/datasets', recorded:true}});
const done = Array.from(pane2.querySelectorAll('.sp-done')).pop(), rep = done.querySelector('.reaches');
check('the closing card\'s report: the heading with the counts, one line per reach with its cell and tag, the refused attempt, the sandbox line; the count of cells says 1 not run, and the report stands before the row of what can be done next', rep && rep.querySelector('.h').textContent === '2 reaches outside the data (1 not asked for) · 1 cell not run'
      && rep.querySelectorAll('.r').length === 3 && rep.querySelectorAll('.r')[0].querySelector('.c').textContent === 'cell 15' && rep.querySelectorAll('.r')[0].querySelector('.tag').textContent === 'the question named it'
      && rep.querySelectorAll('.r')[1].classList.contains('unasked') && rep.querySelectorAll('.r')[1].querySelector('.tag').textContent === 'not asked for'
      && rep.querySelectorAll('.r')[2].querySelector('.what').textContent === 'not run: restricted operation (subprocess)' && rep.querySelectorAll('.r')[2].querySelector('.tag').textContent === 'refused'
      && rep.querySelector('.sandbox').textContent.startsWith('Sandbox: appuser (not root)') && done.querySelector('.nums').textContent.includes('(1 not run)') && done.innerHTML.indexOf('class="reaches"') < done.innerHTML.indexOf('class="acts"'), rep && rep.outerHTML);
w.paneRunStart({mode:'Quick', of:5, dollars:1});
w.paneRunEnd({status:'answered', turns:2, of:5, cells:1, failed:0, refused:0, cost:0.01, seconds:5, replay_status:'', replay_line:'', plots:0, files:[], chain_id:'2', reaches:{lines:[], refused:[], counts:{lines:0, unasked:0, asked:0, blocked:0, refused:0, net:0}, sandbox:'appuser (not root)', recorded:true}});
const quietRep = Array.from(pane2.querySelectorAll('.sp-done')).pop().querySelector('.reaches');
check('a run that reached nothing: one quiet line with the sandbox as its hover; a run from an executor without the record shows nothing', quietRep && quietRep.classList.contains('quiet') && quietRep.textContent === 'No reaches outside the data' && quietRep.getAttribute('title').startsWith('Sandbox: appuser')
      && (w.paneRunStart({mode:'Quick', of:5, dollars:1}), w.paneRunEnd({status:'answered', turns:2, of:5, cells:1, failed:0, cost:0.01, seconds:5, replay_status:'', replay_line:'', plots:0, files:[], chain_id:'3', reaches:{lines:[], refused:[], counts:{lines:0, refused:0}, sandbox:'', recorded:false}}), !Array.from(pane2.querySelectorAll('.sp-done')).pop().querySelector('.reaches')), quietRep && quietRep.outerHTML);

// a run of 239.6 s reads "4 min 0 s", not "3 min 60 s" (2026-10-06)
w.paneRunStart({mode:'Deep', of:15, dollars:1}); w.paneRunEnd({status:'answered', turns:15, of:15, cells:11, failed:2, cost:0.1, seconds:239.6, replay_status:'', replay_line:'', plots:0, files:[]});
const doneCards = pane2.querySelectorAll('.sp-done'); const lastDone = doneCards[doneCards.length - 1];
check('closing card: seconds are rounded before the split into minutes and seconds', lastDone.querySelector('.nums').textContent.includes('4 min 0 s') && !lastDone.querySelector('.nums').textContent.includes('60 s'), lastDone.querySelector('.nums').textContent);
// the peek is the step the analyst took, not its account of the last output (2026-10-06)
w.paneRunStart({mode:'Deep', of:15, dollars:1}); w.paneTurnStart({turn:13, of:15, seat:'Analyst', model:'m'});
w.paneTurnEnd({turn:13, kind:'cell', thinking:'Cell 6 printed the venue table. Now I fit the within-athlete regression, clustered by session.', note:'- Names: df', code:'print(1)', elapsed:1, cost:0.001});
const peek13 = Array.from(pane2.querySelectorAll('.sp-turn')).pop().querySelector('summary .peek');
check('peek: a two-sentence THINKING shows the step (its second sentence), not what the last output showed', peek13 && peek13.textContent.startsWith('Now I fit the within-athlete regression'), peek13 && peek13.textContent);
// a stored note with bold markers around a heading: the grid shows the heading plain
w.paneRunStart({mode:'Deep', of:15, dollars:1}); w.paneTurnStart({turn:12, of:15, seat:'Analyst', model:'m'}); w.paneTurnEnd({turn:12, kind:'cell', thinking:'t', note:'- **Best estimate so far:** 7.4%\n- Names: df', code:'print(1)', elapsed:1, cost:0.001});
const boldRow = Array.from(pane2.querySelectorAll('.sp-note b')).map(b => b.textContent);
check('note grid: bold markers around a heading in a stored note are not shown', boldRow.includes('Best estimate so far') && !boldRow.some(t => t.includes('*')), boldRow);
// the closing card (0313, the product owner's choice of three mockups): the title with the run's numbers beside it, what was reproduced, and one row of what can be done next. It links to no tab
const cardOf = r => { const d = doc.createElement('div'); d.innerHTML = w.__paneBuild.runEnd(Object.assign({ status: 'answered', turns: 2, cells: 1, cost: 0.1, seconds: 9 }, r)); return d.querySelector('.sp-done'); };
const shape = c => c.elements.map(e => e.className).join('|'), numsOf = r => cardOf(r).querySelector('.head .nums').textContent;
const full = cardOf({ of: 15, plots: 3, cells: 8, failed: 4, refused: 1, chain_id: 77, brief: true, replay_status: 'reproduced', replay_line: 'Replay reproduced the cited results.', reaches: { recorded: true, counts: {} } });
check('closing card (0313): the head - the title and, beside it, the turns of how many, the cells with those that failed or were not run, the plots, the cost and the time; then the replay line, the faint line '
  + 'that nothing was reached, and the row of what can be done next, which holds the code trace\'s button. No link, no arrow, no word of a tab - with a brief or without',
  shape(full) === 'head|rep ok|reaches quiet|acts' && full.querySelector('.head').elements.map(e => e.tag + '.' + e.className).join() === 'span.title,span.nums' && full.querySelector('.title').textContent === 'Run complete'
  && numsOf({ of: 15, plots: 3, cells: 8, failed: 4, refused: 1 }) === '2 of 15 turns · 8 cells (4 failed, 1 not run) · 3 plots · $0.10 · 9.0 s'
  && full.querySelectorAll('a').length === 0 && !/→|Answer|Brief|Simplified|Investigation/.test(full.textContent) && cardOf({ brief: true }).outerHTML === cardOf({ brief: false }).outerHTML
  && full.querySelectorAll('.acts button').length === 1 && full.querySelector('.acts .sp-act.sp-codemap').textContent === 'Code trace' && full.querySelector('.acts .sp-codemap').getAttribute('data-chain') === '77'
  && full.querySelector('.acts .sp-codemap svg') && full.querySelector('.acts .sp-codemap').getAttribute('type') === 'button', full.outerHTML);
check('closing card: one of a thing is said as one - "1 turn", "1 cell", "1 plot" - and nothing of plots where there are none; a run without a turn count of how many says its turns alone',
  numsOf({ turns: 1, cells: 1, plots: 1 }) === '1 turn · 1 cell · 1 plot · $0.10 · 9.0 s' && numsOf({ turns: 3, cells: 0 }) === '3 turns · 0 cells · $0.10 · 9.0 s' && numsOf({ of: 1, turns: 1 }) === '1 of 1 turns · 1 cell · $0.10 · 9.0 s');
check('closing card: the row of what can be done next stands on every answered run - next-questions.js puts its button there - with the code trace\'s button only where the run ran code and names its chain; '
  + 'a run that was stopped, and one that asked, have no row',
  shape(cardOf({ cells: 0, chain_id: 77 })) === 'head|acts' && cardOf({ cells: 0, chain_id: 77 }).querySelectorAll('.acts button').length === 0 && cardOf({ cells: 2 }).querySelectorAll('.acts button').length === 0
  && cardOf({ cells: 2, chain_id: 77 }).querySelectorAll('.acts button').length === 1
  && shape(cardOf({ status: 'stopped', cells: 2, chain_id: 77 })) === 'head' && cardOf({ status: 'stopped' }).querySelector('.title').textContent === 'Run stopped'
  && shape(cardOf({ status: 'asked', cells: 2, chain_id: 77 })) === 'head' && cardOf({ status: 'asked' }).querySelector('.title').textContent === 'The analyst has a question for you');
// a routine's run
const routineOf = r => { const d = doc.createElement('div'); d.innerHTML = w.__paneBuild.routineEnd(Object.assign({ number: 3, status: 'reproduced', results: 4, elapsed: 5 }, r)); return d.querySelector('.sp-done'); };
const routine = routineOf({ name: 'Weekly', compared: 4, moved: 1, figures: 2, line: 'Reproduced.', comparison_line: 'one moved', against: 2 });
check('the closing card of a routine\'s run (0313): the same shape - its title with what came out beside it, the verdict, the comparison - and no link to a tab; what was not compared, and figures where '
  + 'there are none, are not said; a run that failed is marked',
  shape(routine) === 'head|rep ok|rep' && routine.querySelector('.title').textContent === 'Run 3 complete · Weekly' && routine.querySelector('.nums').textContent === '4 results · 1 of 4 moved · 2 figures · 5.0 s'
  && routine.querySelectorAll('a').length === 0 && !routine.querySelector('.acts') && routineOf({ results: 1 }).querySelector('.nums').textContent === '1 result · 5.0 s'
  && routineOf({ status: 'failed' }).className === 'sp-done warn' && routineOf({ status: 'failed' }).querySelector('.title').textContent === 'Run 3 failed', routine.outerHTML);
// a card kept from before 0313, as a chain's kept markup holds it: shown again, it comes to today's shape
const KEPT_CARD = '<div class="sp-done"><div class="title">Run complete</div><div class="grid"><span>Turns <b>13</b></span><span>Cells <b>8</b> (4 failed)</span><span>Cost <b>$0.14</b></span><span>Time <b>5 min 9 s</b></span></div>' +
  '<div class="rep ok">✓ Replay reproduced.</div><div class="reaches quiet"><span class="h">No reaches outside the data</span></div>' +
  '<div class="links"><a href="#">Answer →</a><a href="#">Brief →</a><a href="#">Simplified →</a><a href="#">Investigation →</a><a href="#">Plots (3) →</a><button class="sp-codemap" data-chain="88">Code trace →</button></div>' +
  '<div class="nq-open"><button type="button" class="sp-next" data-nq="open" title="t">Next questions</button></div><details class="sp-telemetry"><summary>call telemetry</summary><pre>x</pre></details></div>';
const KEPT_ROUTINE = '<div class="sp-done"><div class="title">Run 3 complete</div><div class="grid"><span>Results <b>4</b></span><span>Time <b>5 s</b></span></div><div class="rep ok">✓ Reproduced.</div>' +
  '<div class="links"><a href="#">Trend →</a><a href="#">Results →</a><a href="#">Data →</a></div></div>';
const keptPane = doc.createElement('div'); keptPane.innerHTML = '<div class="sp-stream">' + KEPT_CARD + KEPT_ROUTINE + '<div class="sp-done"><div class="title">Run stopped</div><div class="grid"><span>Turns <b>2</b></span></div></div>' + w.__paneBuild.runEnd({ status: 'answered', turns: 2, cells: 1, cost: 0.1, seconds: 9, chain_id: 5 }) + '</div>';
const today = keptPane.querySelectorAll('.sp-done')[3].outerHTML;
w.paneRenew(keptPane);
const renewed = keptPane.querySelectorAll('.sp-done');
check('a closing card kept from before (0313), shown again: its title and its numbers on one line, as they were written; its links gone, every one - the tabs are the way to the answer; the code trace\'s '
  + 'button as today\'s, with its chain, in the row of what can be done next - the Next questions button it had under the links first in that row, the same button; the telemetry last, untouched. The '
  + 'card of a routine\'s run keeps no row; a run that was stopped had none. Today\'s card is left as it is, and a pane renewed twice is renewed once; no pane at all is no error',
  shape(renewed[0]) === 'head|rep ok|reaches quiet|acts|sp-telemetry' && renewed[0].querySelector('.head').elements.map(e => e.className).join() === 'title,nums'
  && renewed[0].querySelector('.nums').textContent === 'Turns 13Cells 8 (4 failed)Cost $0.14Time 5 min 9 s' && renewed[0].querySelectorAll('a').length === 0 && !/→/.test(renewed[0].textContent)
  && renewed[0].querySelectorAll('.acts button').map(x => x.className + '=' + x.textContent).join('|') === 'sp-next sp-act=Next questions|sp-act sp-codemap=Code trace'
  && renewed[0].querySelector('.acts .sp-codemap').getAttribute('data-chain') === '88' && renewed[0].querySelector('.acts [data-nq="open"]').getAttribute('title') === 't' && !renewed[0].querySelector('.nq-open')
  && shape(renewed[1]) === 'head|rep ok' && renewed[1].querySelector('.nums').textContent === 'Results 4Time 5 s' && shape(renewed[2]) === 'head' && renewed[3].outerHTML === today
  && (() => { const once = keptPane.innerHTML; w.paneRenew(keptPane); w.paneRenew(null); return keptPane.innerHTML === once; })(), renewed[0].outerHTML);
const showSrc = require('fs').readFileSync(require('path').join(__dirname, '..', '..', 'web_app', 'static', 'js', 'workflow-management.js'), 'utf8');
check('the closing card\'s look and its hook, from the sources (0313): the title and the numbers share a line, and wrap where the pane is narrow; the buttons stand side by side over one rule, and a row '
  + 'that holds no button shows nothing; a button has its border; where nothing was reached the reach report is one faint line, with no rule of its own; nothing is left of the grid or the links. '
  + 'A chain shown again has its kept card renewed as soon as its pane is put back',
  paneCss.includes('#streamOutput .sp-done .head { display: flex; align-items: baseline; justify-content: space-between; flex-wrap: wrap;')
  && paneCss.includes('#streamOutput .sp-done .acts { display: flex; flex-wrap: wrap; gap: 8px; margin-top: 10px; padding-top: 10px; border-top: 1px solid var(--border-color); }')
  && paneCss.includes('#streamOutput .sp-done .acts:empty { display: none; }') && /#streamOutput \.sp-act \{[^}]*border: 1px solid var\(--chip-model-border\);/.test(paneCss)
  && paneCss.includes('#streamOutput .sp-done .reaches.quiet { margin-top: 3px; padding-top: 0; border-top: 0;') && !/\.sp-done \.(grid|links)\b/.test(paneCss)
  && showSrc.includes("document.getElementById('streamOutput').innerHTML = response.streamOutput;\n    if (typeof paneRenew === 'function') paneRenew(document.getElementById('streamOutput'));"));
pane2.innerHTML = '';
w.paneAppend('<details class="sp-turn ar-fold"><summary>Pathfinder</summary></details>');
w.paneRunStart({mode:'Deep', of:15, dollars:1}); w.paneTurnStart({turn:1, of:15, seat:'Analyst', model:'m'});
check('a row of the page\'s own (the framing, folded): it makes the pane\'s strip, ids line and stream when the pane is empty and goes first in the stream; the run\'s strip and cards follow it',
  pane2.elements.map(e => e.className).join() === 'sp-strip,sp-ids-slot,sp-stream' && pane2.querySelector('.sp-stream').elements.map(e => e.className).join('|') === 'sp-turn ar-fold|sp-turn live'
  && pane2.querySelector('.sp-strip .mode').textContent === 'Deep', pane2.innerHTML.slice(0, 400));

// every check above is printed and counted here (2026-11-15: the loop sat above the last checks, which then counted as passed whatever they found;
// three of them read the first pane after the second had taken its place)
let fails = 0; for (const [n, ok, d] of results) { console.log((ok ? '  ok   ' : '  FAIL ') + n + (ok ? '' : '  <- ' + (d || ''))); if (!ok) fails++; }
console.log(`\n${results.length - fails} passed, ${fails} failed`); process.exit(fails ? 1 : 0);
