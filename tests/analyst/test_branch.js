// The branches of an analysis on the page (docs/BRANCH_DESIGN.md §5; 2.9, patch 0320): branch.js, on the mini DOM, with
// panes written by the pane's own functions (stream-pane.js) as the server's events arrive, the maps drawer and its
// switch (maps.js), and the Workflow map's drawing (workflowGraph.js) on the harness's dagre. The turns a branch keeps - in their fold - and the card of its hint in the left pane;
// the turns of a chain read back from its pane; an analysis as a chain with its branches - what the arrows and the
// Workflow map count; the Analysis map - its boxes, what the drawer says, the way that is lit; going back to a turn -
// the pane that ends there, the composer as a hint's; the hint sent, a branch the server started and one it did not;
// then the page's hooks, read from the sources.
// Run: node tests/analyst/test_branch.js
'use strict';
const fs = require('fs'), path = require('path');
const { makeDocument, fragment } = require(path.join(__dirname, 'minidom.js'));
const html = fs.readFileSync(path.join(__dirname, '..', '..', 'web_app', 'templates', 'index.html'), 'utf8');
const doc = makeDocument(); global.document = doc; global.window = {};
const results = []; const check = (n, c, d) => results.push([n, !!c, d]);
const same = (a, b) => JSON.stringify(a) === JSON.stringify(b);
const $ = id => doc.getElementById(id);
const host = doc.createElement('div'); doc.body.appendChild(host);
host.innerHTML = '<button id="railMapButton"></button><div id="streamOutput"></div><div id="tabContainer"></div><div id="contentOutput"></div>' +
  '<div class="input-area"><div class="textarea-container"><textarea id="queryInput"></textarea><div class="icon-row"><div class="attach-menu-container"></div><div id="modeSliderPopup"></div>' +
  '<button id="architectSwitch" class="ar-switch"></button></div><button id="submitQuery"></button></div></div>' +
  fragment(html, 'workflowMapModal');                              // the maps' drawer: the page's own
$('workflowMapModal').style.display = 'none'; $('queryInput').placeholder = 'Enter your query here';
doc.createElementNS = (ns, tag) => doc.createElement(tag);
// the page's own parts, as far as the module leans on them
const toasts = []; global.showSystemMessage = t => toasts.push(t);
global.responses = []; global.currentResponseIndex = -1; global.currentData = {}; global.queryRunning = false; global.lastActiveChainId = null;
global.liveState = { running: false, away: false, index: null, parent: null, data: null, tasks: null, holders: null };
const loaded = [];
global.loadResponseContent = r => { loaded.push(r.chain_id); $('tabContainer').innerHTML = r.tabContent || ''; $('contentOutput').innerHTML = r.contentOutput || ''; $('streamOutput').innerHTML = r.streamOutput || '';
  window.paneRenew($('streamOutput')); currentData.chain_id = r.chain_id; currentData.thread_id = r.thread_id; };      // a pane kept by an older build, in today's shape: the page's own step
global.updateNavigationButtons = () => { window.BranchUI.onChain(responses[currentResponseIndex]); window.MapsUI.follow(); };
global.extractTaskFromResponse = r => ({ task: '', originalQuestion: r.queryText }); global.extractPlotDataFromResponse = () => null;
const framed = []; window.ArchitectUI = { mark: () => '', started: e => framed.push(e),
  map: n => ({ n: 0, said: '', off: 'Chain ' + n + ' was asked without the Pathfinder', draw() {} }) };      // the Pathfinding level's stand-in: no chain here has a brief with steps
require(path.join(__dirname, '..', '..', 'tools', 'fixtures', 'dagre_stub.js')); global.dagre = window.dagre;
const JS = path.join(__dirname, '..', '..', 'web_app', 'static', 'js');
require(path.join(JS, 'stream-pane.js')); require(path.join(JS, 'workflowGraph.js')); require(path.join(JS, 'branch.js')); require(path.join(JS, 'maps.js'));
// the Workflow level: the page's own (workflow-management.js), taken from its source
const wmSrc = fs.readFileSync(path.join(JS, 'workflow-management.js'), 'utf8');
global.updateSynthesisButtonState = () => {}; global.updateTrajectoryButtonState = () => {}; global.WorkflowGraph = window.WorkflowGraph;
global.workflowMap = new Function(wmSrc.slice(wmSrc.indexOf('function workflowMap() {'), wmSrc.indexOf('\nfunction updateSynthesisButtonState() {')) + '\nreturn workflowMap;')();
const w = window, B = window.BranchUI, M = window.MapsUI;
B.initialize(); M.initialize();

// a chain's left pane, written as its run's events arrive; `kept` turns are those a branch keeps
function paneOf(chain, turns, opt) {
  $('streamOutput').innerHTML = '';
  w.paneIds({ thread_id: 7, chain_id: chain, df_id: 'd1' });
  w.paneRunStart({ mode: 'Deep', of: 8, dollars: 1.5, branch: opt.branch });
  turns.forEach(t => {
    if (t.review) { w.paneTurnStart({ turn: 'review', review: true, seat: 'Reviewer', model: 'r', chain_id: chain, kept: t.kept }); w.paneTurnEnd({ turn: 'review', kind: 'review', thinking: 'Verdict: TEST the second step', kept: t.kept }); return; }
    w.paneTurnStart({ turn: t.n, of: 8, seat: 'Analyst', model: 'm', chain_id: chain, kept: t.kept });
    if (t.cut) return;                                          // the run was stopped while this turn was written
    w.paneTurnEnd({ turn: t.n, kind: t.kind, thinking: t.step, note: '', code: t.kind === 'cell' ? 'x = 1' : '', elapsed: 2, cost: 0.01, kept: t.kept });
    if (t.kind === 'cell') w.paneCell(t.cell ? { cell_no: t.cell, ok: true, peek: t.out, elapsed: 0.1, chars: 10, kept: t.kept ? (t.differs ? 'differs' : 'kept') : undefined }
                                            : { cell_no: null, ok: false, error_line: 'ValueError: slip', elapsed: 0.1, kept: t.kept ? 'kept' : undefined });
    if (t.kind === 'names') w.paneLookup({ kind: 'names', query: '', peek: 'df, pooled' });
  });
  w.paneRunEnd({ status: opt.status || 'answered', turns: turns.filter(t => !t.review).length, of: 8, cells: 1, cost: 0.1, seconds: 3, chain_id: chain, turn_map: opt.map !== false });
  return $('streamOutput').innerHTML;
}
const entry = (chain, parent, question, turns, opt) => ({ chain_id: chain, thread_id: 7, parentChainId: parent, queryText: question, streamOutput: paneOf(chain, turns, opt || {}),
  tabContent: '<div class="tab" id="tab-answer">Answer</div>', contentOutput: '<div id="content-answer">the answer of ' + chain + '</div>', taskContents: {}, branch: (opt || {}).entryBranch || null });
const keep = turns => turns.map(t => Object.assign({}, t, { kept: true }));
const A = [{ n: 1, kind: 'cell', step: 'The question wants two blocks compared. This turn loads both blocks.', cell: 2, out: 'rows 92' },
           { n: 2, kind: 'cell', step: 'Both blocks are in. This turn pools them.', cell: null },
           { n: 3, kind: 'cell', step: 'The pooling failed on a name. This turn pools the two blocks.', cell: 3, out: 'pooled 20' },
           { n: 4, kind: 'names', step: 'The pooled figure is there. This turn lists what the kernel holds.' },
           { review: true },
           { n: 5, kind: 'cell', step: 'The names are as expected. This turn compares the blocks.', cell: 4, out: 'diff 0.5' },
           { n: 6, kind: 'report', step: 'Everything asked is established.' }];
const B1 = [{ n: 4, kind: 'cell', step: 'The hint wants the blocks apart. This turn splits them.', cell: 4, out: 'apart 10' }, { n: 5, kind: 'report', step: 'Each block has its own figure.' }];
const q0 = entry(10, null, 'What is in the data?', [{ n: 1, kind: 'report', step: 'Nothing to compute.' }], { map: false });
const a = entry(20, 10, 'How do the two blocks compare?', A, {});
const b1 = entry(21, 10, 'How do the two blocks compare?', keep(A.slice(0, 3)).concat(B1),
                 { branch: { of: 20, turn: 3, hint: 'keep the two blocks apart' }, entryBranch: { of: 20, turn: 3, hint: 'keep the two blocks apart' } });
const f = entry(30, 21, 'And by soil type?', [{ n: 1, kind: 'cell', step: 'The blocks are apart. This turn follows up.', cell: 5, out: 'more' }, { n: 2, kind: 'report', step: 'Done.' }], {});
const b2 = entry(22, 10, 'How do the two blocks compare?', keep(A.slice(0, 2)).concat([Object.assign({}, A[2], { kept: true, differs: true }), { n: 4, kind: 'report', step: 'Nothing more is needed.' }]),
                 { branch: { of: 20, turn: 3, hint: 'another way' }, entryBranch: { of: 20, turn: 3, hint: 'another way' } });
const c = entry(23, 10, 'How do the two blocks compare?', keep(A.slice(0, 3)).concat(keep(B1.slice(0, 1)), [{ n: 5, kind: 'cell', step: 'Both figures stand. This turn compares them.', cell: 5, out: 'B larger' }, { n: 6, kind: 'report', step: 'B is the larger.' }]),
                { branch: { of: 21, turn: 4, hint: 'and say which is larger' }, entryBranch: { of: 21, turn: 4, hint: 'and say which is larger' } });
const k = entry(70, null, 'A question back', [{ n: 1, kind: 'cell', step: 'First. This turn loads.', cell: 1, out: 'one' }, { n: 2, kind: 'ask', step: 'The measure is not in the data.' }], { status: 'asked' });
const e0 = entry(25, 10, 'How do the two blocks compare?', keep(A.slice(0, 2)), { status: 'stopped', branch: { of: 20, turn: 2, hint: 'stopped at once' }, entryBranch: { of: 20, turn: 2, hint: 'stopped at once' } });
const s = entry(40, null, 'Stopped on the way', [{ n: 1, kind: 'cell', step: 'First. This turn loads.', cell: 1, out: 'one' }, { n: 2, kind: 'cell', step: 'Loaded. This turn sums.', cell: 2, out: 'two' }, { n: 3, cut: true }], { status: 'stopped' });
responses.push(q0, a, b1, f, b2, c, s);
const ids = () => B.analyses().map(m => m.chain_id), fresh = ids();      // before any chain was on screen
const holder = html => { const d = doc.createElement('div'); d.innerHTML = html; return d; };
const show = e => { currentResponseIndex = responses.indexOf(e); loadResponseContent(e); updateNavigationButtons(); };

// ---- the left pane of a branch
const pb = holder(b1.streamOutput), cards = pb.querySelectorAll('.sp-turn[data-turn]'), rowsB = pb.querySelector('.sp-stream').elements.map(e => e.className.split(' ').slice(0, 3).join('.'));
const foldB = pb.querySelector('.sp-kept'), inFold = foldB ? foldB.querySelector('.sp-kept-body').elements.map(e => e.className.split(' ').slice(0, 3).join('.')) : null;
const saysOf = fold => (fold ? fold.querySelector('summary').elements.slice(1).map(e => e.textContent) : null);      // the fold's row: which turns, "kept", from where, its cells
// the pane was written before the thread had a chain: where its kept turns come from is said once it is on screen (below)
check('the pane of a branch (0330: the turns it keeps in one fold): the fold comes first, shut - its row says which turns it holds, that they are kept, and how many cells they ran and '
  + 'how many failed, as the closing card says it; in it the turns kept, each card shut and marked kept, with its step, the word "kept" where a turn of its own has its time and cost, and '
  + 'no way to a prompt - it made no call in this chain -, and the cells kept, marked too. Under the fold the card of the hint: the turn it was given after, and the hint whole; then the '
  + 'branch\'s own turns',
  same(cards.map(x => [x.getAttribute('data-turn'), x.classList.contains('kept'), x.hasAttribute('open'), x.querySelector('summary .meta').textContent, !!x.querySelector('.sp-prompt'), x.closest('.sp-kept') === foldB]),
       [['1', true, false, 'kept', false, true], ['2', true, false, 'kept', false, true], ['3', true, false, 'kept', false, true], ['4', false, false, '2.0 s · $0.01', true, false], ['5', false, false, '2.0 s · $0.01', true, false]])
  && cards[0].querySelector('.sp-think').textContent === A[0].step && cards[0].querySelector('summary .peek').textContent === 'This turn loads both blocks.'
  && same(rowsB, ['sp-turn.sp-kept', 'sp-hint', 'sp-turn', 'sp-row', 'sp-turn', 'sp-done']) && foldB.tag === 'details' && !foldB.hasAttribute('open')
  && same(inFold, ['sp-turn.kept', 'sp-row.kept', 'sp-turn.kept', 'sp-row.fail.kept', 'sp-turn.kept', 'sp-row.kept']) && same(saysOf(foldB), ['Turns 1–3', 'kept', '', '2 cells (1 failed)'])
  && pb.querySelector('.sp-hint').textContent === 'Branch from turn 3keep the two blocks apart' && pb.querySelector('.sp-hint .said').textContent === 'keep the two blocks apart'
  && pb.querySelectorAll('.sp-hint').length === 1 && !!pb.querySelector('.sp-hint .hd svg')
  && same(pb.querySelectorAll('.sp-prompt').map(x => x.getAttribute('data-call')), ['1', '2']), [rowsB, inFold, saysOf(foldB), cards.map(x => x.querySelector('summary .meta').textContent)]);
const differs = holder(b2.streamOutput).querySelectorAll('.sp-row').filter(r => r.classList.contains('differs'));
check('... a kept cell that printed something else when it was run again says so on its row, and why on hover; the others say nothing of it',
  differs.length === 1 && differs[0].getAttribute('data-cell') === '3' && differs[0].querySelector('.t').textContent.startsWith('run again: output changed')
  && /printed something else than the first time/.test(differs[0].querySelector('.t').getAttribute('title')) && !/run again/.test(pb.querySelector('.sp-stream').textContent));
const stripOf = e => holder(e.streamOutput).querySelector('.sp-strip'), idsOf = e => holder(e.streamOutput).querySelector('.sp-ids');
check('the mark of an analysis that can be gone on from (0327; until then a button to the Analysis map, 0321): where the run ended with turns to go on from, the row of the ids says so, and '
  + 'holds no button - the way to the map is the maps drawer; the strip keeps the run\'s limit of turns; an analysis with no turn to go on from has no such mark; a stopped one has it',
  idsOf(a).getAttribute('data-branch') === '1' && !idsOf(a).querySelector('button') && !holder(a.streamOutput).querySelector('.sp-turnmap') && stripOf(a).getAttribute('data-of') === '8'
  && stripOf(a).elements.map(e => e.className || e.tag).slice(0, 4).join() === 'live idle,mode,span,bar' && !idsOf(q0).hasAttribute('data-branch') && idsOf(s).getAttribute('data-branch') === '1'
  && holder(s.streamOutput).querySelector('.sp-done .title').textContent === 'Run stopped');
$('streamOutput').innerHTML = '';
w.paneRunStart({ mode: 'Deep', of: 8, dollars: 1, branch: { of: 20, turn: 3, hint: 'stopped at once' } });
w.paneTurnStart({ turn: 1, kept: true });
const shut = !$('streamOutput').querySelector('.sp-turn.kept').hasAttribute('open') && !$('streamOutput').querySelector('.sp-kept').hasAttribute('open'), liveFold = saysOf($('streamOutput').querySelector('.sp-kept'));
w.paneTurnEnd({ turn: 1, kind: 'cell', thinking: 'x', kept: true });
w.paneCell({ cell_no: 1, ok: true, peek: 'one', elapsed: 0.1, chars: 3, kept: 'kept' });
const midRun = !!$('streamOutput').querySelector('[data-branch]') || !!$('streamOutput').querySelector('.sp-hint'), liveCell = saysOf($('streamOutput').querySelector('.sp-kept'));
w.paneRunEnd({ status: 'stopped', turns: 1, of: 8, cells: 0, cost: 0, seconds: 0, chain_id: 99 });
check('... while a run is under way there is no such mark, and a kept turn\'s card goes into the fold as it arrives - both shut from the start, the fold saying where the turns come '
  + 'from and counting the cells kept as they come, nothing of cells before one; a branch that ended before a turn of its own still has the card of its hint, once, before its closing card',
  !midRun && shut && same(liveFold, ['Turn 1', 'kept', 'from the original', '']) && same(liveCell, ['Turn 1', 'kept', 'from the original', '1 cell'])
  && $('streamOutput').querySelector('.sp-stream').elements.map(e => e.className).join() === 'sp-turn sp-kept,sp-hint,sp-done' && !$('streamOutput').querySelector('[data-branch]'), [liveFold, liveCell]);
$('streamOutput').innerHTML = '';
w.paneRunStart({ mode: 'Deep', of: 8, dollars: 1, branch: { of: 20, turn: 3, hint: 'lost on the way' } });      // its stream broke before a turn, and before an end
$('streamOutput').innerHTML = '';
w.paneRunStart({ mode: 'Deep', of: 8, dollars: 1 });
w.paneTurnStart({ turn: 1, of: 8, seat: 'Analyst', model: 'm', chain_id: 98 });
const open1 = $('streamOutput').querySelector('.sp-turn').hasAttribute('open');
w.paneTurnEnd({ turn: 1, kind: 'report', thinking: 'Done.', elapsed: 1, cost: 0 }); w.paneRunEnd({ status: 'answered', turns: 1, of: 8, cells: 0, cost: 0, seconds: 1, chain_id: 98 });
check('... a branch whose run broke off before a turn leaves nothing of its hint in the next run\'s pane; a turn of a run\'s own stands open while it is written',
  open1 && !$('streamOutput').querySelector('.sp-hint') && $('streamOutput').querySelector('.sp-stream').elements.map(e => e.className).join() === 'sp-turn,sp-done',
  $('streamOutput').querySelector('.sp-stream').elements.map(e => e.className).join());

// ---- the turns of a chain, read from its pane
show(a);
const ta = B.turnsOf(a), brief = t => [t.n, t.kind, t.peek, t.cell, t.failed, t.out];
check('the turns of a chain are read from its left pane: each numbered card with its number, what it was, what it did, the cell it ran and what that printed - or that its cell failed; a '
  + 'review is no turn, and a look-up\'s row is no cell; the turns a branch keeps are turns of its pane; the card of a turn the run was stopped in is no turn',
  same(ta.map(brief), [[1, 'cell', 'This turn loads both blocks.', 2, false, 'rows 92'], [2, 'cell', 'This turn pools them.', null, true, ''],
                       [3, 'cell', 'This turn pools the two blocks.', 3, false, 'pooled 20'], [4, 'look-up', 'This turn lists what the kernel holds.', null, false, ''],
                       [5, 'cell', 'This turn compares the blocks.', 4, false, 'diff 0.5'], [6, 'report', 'Everything asked is established.', null, false, '']])
  && same(B.turnsOf(b1).map(t => t.n), [1, 2, 3, 4, 5]) && holder(s.streamOutput).querySelectorAll('.sp-turn').length === 3 && same(B.turnsOf(s).map(t => [t.n, t.kind]), [[1, 'cell'], [2, 'cell']])
  && same(B.turnsOf(k).map(t => [t.n, t.kind]), [[1, 'cell'], [2, 'question']]) && B.turnsOf({ streamOutput: '' }).length === 0, ta.map(brief));

// ---- an analysis: a chain with its branches
const lone = { chain_id: 60, branch: { of: 999, turn: 2, hint: 'x' } };
check('a turn of a chain is a turn of its own, or - where the chain is a branch and kept it - of the chain it went on from, or of one before that; the first run of an analysis is where '
  + 'that ends, and the analysis is that run with every branch of it and of its branches; a branch whose chain is not in the thread stands alone',
  B.owner(c, 5) === c && B.owner(c, 4) === b1 && B.owner(c, 3) === a && B.owner(b2, 3) === a && B.owner(b2, 4) === b2 && B.owner(a, 1) === a && B.first(c) === a && B.first(b1) === a && B.first(f) === f
  && same(B.members(c).map(m => m.chain_id), [20, 21, 22, 23]) && same(B.members(f).map(m => m.chain_id), [30]) && B.owner(lone, 1) === lone && B.first(lone) === lone);
// a branch whose chain is not in the thread - removed from a saved one - draws the turns it kept as its own
const orphan = entry(61, null, 'How do the two blocks compare?', keep(A.slice(0, 2)).concat(B1), { branch: { of: 999, turn: 2, hint: 'x' }, entryBranch: { of: 999, turn: 2, hint: 'x' } });
responses.push(orphan);
const alone = B.boxes(orphan).map(x => [x.key, x.from]);
responses.pop();
check('... the Analysis map of a branch whose chain is not in the thread has every turn of its pane, the kept ones first, in one line',
  same(alone, [['61:1', null], ['61:2', '61:1'], ['61:4', '61:2'], ['61:5', '61:4']]), alone);
show(c); const onC = [ids(), same(B.place(), { i: 2, n: 4 })];
show(a); const onA = [ids(), same(B.place(), { i: 2, n: 4 }), B.step(1) === f, B.step(-1) === q0];
show(s); const onS = [same(B.place(), { i: 4, n: 4 }), B.step(1) === s, B.step(-1) === f];
show(q0); const onQ = [same(B.place(), { i: 1, n: 4 }), B.step(-1) === q0, B.step(1) === a];
check('the arrows count analyses: four of them in a thread of seven chains, in the order they began. Of an analysis they show the chain that was last on screen - a branch brought back '
  + 'stays the one its analysis shows; where none was, its newest - and go to the analysis before or after, staying at either end',
  same(fresh, [10, 23, 30, 40]) && same(onC, [[10, 23, 30, 40], true]) && same(onA, [[10, 20, 30, 40], true, true, true]) && same(onS, [true, true, true]) && same(onQ, [true, true, true]), [fresh, onC, onA, onS, onQ]);
check('... asked of a chain, the place is that chain\'s, whichever is on screen: a branch has the number of the analysis it is a way of - the code trace names chains so (0322)',
  same([q0, a, b1, c, f, s].map(e => B.place(e).i), [1, 2, 2, 2, 3, 4]) && same(B.place(c), { i: 2, n: 4 }) && same(B.place(), { i: 1, n: 4 }), [q0, a, b1, c, f, s].map(e => B.place(e)));
show(b1);
const items = B.items();
check('the Workflow map\'s boxes: a box to an analysis - the chain of it last on screen - with how many branches it has and where its chain stands in the thread; a chain asked from a branch '
  + 'is joined to that branch\'s analysis, whichever chain of it the box shows; the chains themselves are not changed',
  same(items.map(i => [i.chain_id, i.parentChainId, i.branches, i.at]), [[10, null, 0, 0], [21, 10, 3, 2], [30, 21, 0, 3], [40, null, 0, 6]]) && f.parentChainId === 21 && items[1] !== b1 && items[1].streamOutput === b1.streamOutput
  && (show(a), same(B.items().map(i => [i.chain_id, i.parentChainId]), [[10, null], [20, 10], [30, 20], [40, null]])), items.map(i => [i.chain_id, i.parentChainId, i.branches, i.at]));

// ---- the Workflow map, drawn from those boxes: the maps drawer (maps.js) opens on it, the first time
const drawer = $('workflowMapModal'), nodes = () => $('workflowMapContainer').querySelectorAll('.wf-node');
// the drawer's switch, as the person sees and presses it: each level with its number, * the one in use, - one that cannot be shown; the chain named between them
const level = key => $('mapLevels').querySelector('[data-level="' + key + '"]'), press = key => $('mapLevels').dispatch('click', level(key));
const bar = () => $('mapLevels').elements.map(x => (x.classList.contains('map-of-chain') ? x.elements : [x]).map(y => y.textContent + (y.getAttribute('aria-pressed') === 'true' ? '*' : '') + (y.getAttribute('aria-disabled') ? '-' : '')).join(' | ')).join(' / ');
const openMap = () => { if (drawer.style.display !== 'flex') M.toggle(); press('analysis'); };      // the Analysis map: the drawer opened, its level pressed
// what the drawer's panel says (0333): "name [tags] > its button" | what was said | the facts, a row each
const panel = () => { const q = s => $('nodeTaskContent').querySelector(s), tags = $('nodeTaskContent').querySelectorAll('.wf-tag').map(t => t.textContent);
  return [((q('.wf-title') || {}).textContent || '') + (tags.length ? ' [' + tags.join(', ') + ']' : '') + (q('.wf-go') ? ' > ' + q('.wf-go').textContent : ''), (q('.wf-said') || {}).textContent || '']
    .filter(Boolean).concat($('nodePlotPreview').querySelectorAll('.wf-info-row').map(r => r.elements.map(e => e.textContent).join('='))).join(' | '); };
// the way to a box (0333; until then a click on it): the box picked, then the panel's button pressed - where the panel has one
const goTo = i => { nodes()[i].dispatch('click'); const go = $('nodeTaskContent').querySelector('.wf-go'); if (go) go.dispatch('click'); };
const lit = () => nodes().map((x, i) => (x.classList.contains('wf-node--ancestor') ? i + 1 : 0)).filter(Boolean).join();
const edges = () => $('workflowMapContainer').querySelectorAll('.wf-edge').map(e => e.getAttribute('data-from') + '>' + e.getAttribute('data-to')).join();
M.toggle();
const barA = bar();
const tm = { boxes: nodes().map(x => x.querySelector('.wf-node-label').textContent + ' > ' + x.querySelector('.wf-node-chain').textContent + ' > ' + ((x.querySelector('.wf-node-branches') || {}).textContent || '')),
             on: nodes().map((x, i) => (x.classList.contains('wf-node--active') ? i + 1 : 0)).filter(Boolean).join(), edges: edges() };
nodes()[1].dispatch('mouseenter'); const tmPanel = panel(); nodes()[1].dispatch('mouseleave');
const before = loaded.length;
goTo(2);
const barF = [drawer.style.display, bar(), nodes().map((x, i) => (x.classList.contains('wf-node--active') ? i + 1 : 0)).filter(Boolean).join()];
M.shut();
check('the Workflow map counts analyses: a box each, the one with branches saying how many - on the box and in the drawer\'s panel -, the open box that of the analysis on screen; a box '
  + 'picked and its button pressed (0333; a click on it until then) brings the chain it stands for on screen, and the drawer stays open (0327): its switch names that chain, and the map has its box open',
  same(tm, { boxes: ['What is in the data? > Chain: 10 > ', 'How do the two blocks compare? > Chain: 20 > 3 branches', 'And by soil type? > Chain: 30 > ', 'Stopped on the way > Chain: 40 > '], on: '2', edges: '0>1,1>2' })
  && tmPanel === 'Chain 2 [on screen, 3 branches] | How do the two blocks compare? | Follows=chain 1 | Followed by=chain 3 | Id=20' && same(loaded.slice(before), [30]) && responses[currentResponseIndex] === f && barA === 'Workflow4* / Chain 2 / Pathfinding- | Analysis11' && same(barF, ['flex', 'Workflow4* / Chain 3 / Pathfinding- | Analysis2', '3']), [tm, tmPanel, loaded.slice(before), barA, barF]);

// ---- the drawer on the Workflow map (0327; the map's own head, 0324): the switch, what the level says of itself, the panel from the first (0332, 0333)
show(a); M.toggle();
const headNow = () => ({ level: drawer.getAttribute('data-level'), shown: drawer.style.display, bar: bar(), said: level('workflow').getAttribute('title'), foot: panel(),
                         tools: $('mapDrawerTools').elements.length, boxes: nodes().length });
const wfHead = headNow();
const allChains = responses.splice(0); currentResponseIndex = -1;      // a thread with no chain yet
M.follow();
const emptyHead = headNow(), emptyMap = $('workflowMapContainer').textContent;
const branchUI = w.BranchUI; w.BranchUI = null;                         // a page without branches, as the level reads its chains
responses.push({ chain_id: 1, parentChainId: null, queryText: 'One question', branches: 1 });
const oneSaid = [workflowMap().n, workflowMap().said];
responses.splice(0); responses.push(...allChains); w.BranchUI = branchUI;
show(a);
M.shut();
check('the drawer on the Workflow map (0327): its switch has Workflow lit, with how many chains; the chain on screen named; and that chain\'s two levels - here Pathfinding greyed, Analysis with '
  + 'how many turns. Under the pointer the level says how many chains, and how many branches their analyses have between them; the panel says, from the first, what the chain on screen '
  + 'is (0332). A thread with no chain yet: the switch is Workflow alone and says so, the panel says nothing, and there is no zoom or full screen to offer; one chain with one branch is "1 chain · 1 branch"',
  same(wfHead, { level: 'workflow', shown: 'flex', bar: 'Workflow4* / Chain 2 / Pathfinding- | Analysis11', said: '4 chains · 3 branches',
                 foot: 'Chain 2 [on screen, 3 branches] | How do the two blocks compare? | Follows=chain 1 | Followed by=chain 3 | Id=20', tools: 2, boxes: 4 })
  && same(emptyHead, { level: 'workflow', shown: 'flex', bar: 'Workflow* / no chains yet', said: 'no chains yet', foot: '', tools: 0, boxes: 0 }) && emptyMap === 'No workflow data to display.'
  && same(oneSaid, [1, '1 chain · 1 branch']), [wfHead, emptyHead, emptyMap, oneSaid]);

// ---- the Analysis map
show(a);
const all = B.boxes(a);
check('the boxes of an analysis\'s Analysis map: the first run\'s turns in a line; each branch\'s own turns after it, the first joined to the turn the branch went on from - two branches from '
  + 'one turn both to that turn, a branch of a branch to the turn of the branch',
  same(all.map(x => [x.key, x.from]), [['20:1', null], ['20:2', '20:1'], ['20:3', '20:2'], ['20:4', '20:3'], ['20:5', '20:4'], ['20:6', '20:5'], ['21:4', '20:3'], ['21:5', '21:4'], ['22:4', '20:3'],
                                       ['23:5', '21:4'], ['23:6', '23:5']]) && all[6].entry === b1 && all[9].turn.n === 5, all.map(x => [x.key, x.from]));
const state = () => ({ shown: drawer.style.display, level: drawer.getAttribute('data-level'), bar: bar(), said: level('analysis').getAttribute('title'),
  boxes: nodes().map(x => x.querySelector('.wf-node-label').textContent + ' > ' + x.querySelector('.wf-node-chain').textContent + ((x.querySelector('.wf-node-made') || {}).textContent ? ' > ' + x.querySelector('.wf-node-made').textContent : '')),
  on: nodes().map((x, i) => (x.classList.contains('wf-node--active') ? i + 1 : 0)).filter(Boolean).join(), lit: lit(), edges: edges(), thread: $('workflowMapContainer').querySelectorAll('.wf-node-branches, .wf-edge-label').length });
openMap();
const opened = state(), restPanel = panel();
nodes()[2].dispatch('mouseenter'); const over3 = { foot: panel(), lit: lit(), printed: $('nodePlotPreview').querySelectorAll('.wf-info-printed b').map(x => x.textContent) }; nodes()[2].dispatch('mouseleave');
nodes()[7].dispatch('mouseenter'); const over8 = { foot: panel(), lit: lit() }; nodes()[7].dispatch('mouseleave');
nodes()[5].dispatch('mouseenter'); const over6 = panel(); nodes()[5].dispatch('mouseleave');
nodes()[1].dispatch('mouseenter'); const over2 = panel(); nodes()[1].dispatch('mouseleave');
check('the Analysis map: the drawer\'s Analysis level, pressed, shows the analysis of the chain on screen - the level lit, how many turns and branches under the pointer, in the panel from the '
  + 'first what the turn on screen is (0332), the thread\'s own marks out of it. Every turn is a box, joined to the turn it follows: on it what the turn did, and under that its number and its cell - or that the cell failed, or what '
  + 'else the turn was; the first turn of a branch carries the mark of its hint. The turn on screen - the last of the chain on screen - is the open box, and the way to it is lit',
  same(opened, { shown: 'flex', level: 'analysis', bar: 'Workflow4 / Chain 2 / Pathfinding- | Analysis11*', said: '11 turns · 3 branches',
    boxes: ['This turn loads both blocks. > Turn 1 · In [2]', 'This turn pools them. > Turn 2 · failed', 'This turn pools the two blo... > Turn 3 · In [3]', 'This turn lists what the ke... > Turn 4 · look-up',
            'This turn compares the blocks. > Turn 5 · In [4]', 'Everything asked is establi... > Turn 6 · report', 'This turn splits them. > Turn 4 · In [4] > hint', 'Each block has its own figure. > Turn 5 · report',
            'Nothing more is needed. > Turn 4 · report > hint', 'This turn compares them. > Turn 5 · In [5] > hint', 'B is the larger. > Turn 6 · report'],
    on: '6', lit: '1,2,3,4,5,6', edges: '0>1,1>2,2>3,3>4,4>5,2>6,6>7,2>8,6>9,9>10', thread: 0 }) && restPanel === 'Turn 6 [on screen, report] | Everything asked is established. | Follows=turn 5 | Followed by=none', [opened, restPanel]);
check('... under the pointer a box lights its own way, and the panel says what the turn is (0333): its number; its tags - "on screen" for the one that is, what it was, the hint\'s mark; '
  + 'the button that goes there; what the turn did; then the turn it follows and those that follow it, the hint its branch was given, and what its cell printed, set apart as printed; when '
  + 'the pointer leaves, the way to the turn on screen is lit again',
  same(over3, { foot: 'Turn 3 [In [3]] > Go to turn 3 | This turn pools the two blocks. | Follows=turn 2 | Followed by=3 turns | Printed=pooled 20', lit: '1,2,3', printed: ['pooled 20'] })
  && same(over8, { foot: 'Turn 5 [report] > Go to turn 5 | Each block has its own figure. | Follows=turn 4 | Followed by=none | Hint=keep the two blocks apart', lit: '1,2,3,7,8' })
  && over6 === 'Turn 6 [on screen, report] | Everything asked is established. | Follows=turn 5 | Followed by=none' && over2 === 'Turn 2 [failed] > Go to turn 2 | This turn pools them. | Follows=turn 1 | Followed by=turn 3' && lit() === '1,2,3,4,5,6', [over3, over8, over6, over2]);
// ---- the drawer's head (0324): zoom and full screen stand in it, before the close
const mapHead = drawer.querySelector('.map-drawer-head'), mapTools = $('mapDrawerTools'), mapSheet = drawer.querySelector('.workflow-modal-content');
const inHead = () => ({ tools: mapTools.elements.map(e => e.className).join(' | '), zoom: mapTools.querySelector('.wf-zoom-controls').elements.map(e => e.className).join(' | '),
                        names: drawer.querySelector('.map-drawer-tools').querySelectorAll('button').map(x => x.getAttribute('aria-label')).join(' | '), level: mapTools.querySelector('.wf-zoom-level').textContent,
                        onMap: drawer.querySelector('.workflow-body').querySelectorAll('.wf-zoom-controls, .wf-zoom-btn, .wf-fullscreen-btn').length });
const zoomBtn = i => mapTools.querySelectorAll('.wf-zoom-btn')[i], fullBtn = () => mapTools.querySelector('.wf-fullscreen-btn');
$('workflowMapContainer').clientWidth = 2000; $('workflowMapContainer').clientHeight = 2000;      // a frame the whole map fits: it is drawn at 100%
openMap();
const headTurns = inHead(), restTurns = panel();
openMap();                                                       // the map drawn again: one set of buttons
const headAgain = inHead();
zoomBtn(1).dispatch('click'); const zoomedIn = inHead().level;
zoomBtn(0).dispatch('click'); zoomBtn(0).dispatch('click'); const zoomedOut = inHead().level;
for (let i = 0; i < 5; i++) zoomBtn(0).dispatch('click');
const zoomLow = [inHead().level, zoomBtn(0).disabled, zoomBtn(1).disabled];
zoomBtn(2).dispatch('click'); const zoomFit = [inHead().level, zoomBtn(0).disabled];
for (let i = 0; i < 8; i++) zoomBtn(1).dispatch('click');
const zoomHigh = [inHead().level, zoomBtn(1).disabled, !!zoomBtn(2).disabled];
zoomBtn(2).dispatch('click'); const zoomHome = [inHead().level, zoomBtn(1).disabled];
check('the drawer\'s head (0324): zoom and full screen stand in the head, before the close - out, the level, in, fit, then full screen - each button with its name for a reader; none of them '
  + 'stands on the map; a map drawn again has one set of them; the level in the head follows the zoom - at its smallest the way further out is shut, at its largest the way further in, and fit never - and fit brings the map back to its frame; the panel says, from the first, '
  + 'what the turn on screen is (0332)',
  same(headTurns, { tools: 'wf-zoom-controls | wf-fullscreen-btn', zoom: 'wf-zoom-btn | wf-zoom-level | wf-zoom-btn | wf-zoom-btn wf-zoom-reset',
                    names: 'Zoom out | Zoom in | Fit to the frame | Full screen | Close', level: '100%', onMap: 0 }) && same(headAgain, headTurns)
  && restTurns === 'Turn 6 [on screen, report] | Everything asked is established. | Follows=turn 5 | Followed by=none' && zoomedIn === '115%' && zoomedOut === '85%'
  && same(zoomLow, ['30%', true, false]) && same(zoomFit, ['100%', false]) && same(zoomHigh, ['200%', true, false]) && same(zoomHome, ['100%', false]),
  [headTurns, headAgain, restTurns, zoomedIn, zoomedOut, zoomLow, zoomFit, zoomHigh, zoomHome]);
const wheel = (deltaY, held) => { let stopped = false; $('workflowMapContainer').onwheel({ deltaY, ctrlKey: held, metaKey: false, preventDefault() { stopped = true; } }); return [inHead().level, stopped]; };
const wheelIn = wheel(-100, true), wheelFree = wheel(-100, false), wheelOut = wheel(100, true);
check('the wheel, with Ctrl or Cmd held, zooms the map by one step a notch - however often a map was drawn in the frame, which outlives its drawings (0327: a step for every drawing '
  + 'until then); without the key the wheel is the page\'s own',
  same(wheelIn, ['115%', true]) && same(wheelFree, ['115%', false]) && same(wheelOut, ['100%', true]) && !(($('workflowMapContainer').listeners || {}).wheel || []).length, [wheelIn, wheelFree, wheelOut]);
const fullLooks = () => [mapSheet.classList.contains('wf-fullscreen'), fullBtn().title, fullBtn().getAttribute('aria-label'), fullBtn().innerHTML];
const fullOff = fullLooks();
fullBtn().dispatch('click');
const fullOn = fullLooks();
openMap();                                                       // drawn again while the drawer is over the whole page
const fullDrawn = fullLooks();
fullBtn().dispatch('click');
const fullBack = fullLooks();
check('full screen: the button says what a click does - "Full screen" with the arrows that part, and "Leave full screen" with the arrows that meet while the drawer is over the whole page; a map drawn again meanwhile '
  + 'keeps saying so; a click brings the drawer back to its side',
  same(fullOff.slice(0, 3), [false, 'Full screen', 'Full screen']) && same(fullOn.slice(0, 3), [true, 'Leave full screen', 'Leave full screen']) && /points="15 3 21 3 21 9"/.test(fullOff[3]) && /points="4 14 10 14 10 20"/.test(fullOn[3])
  && same(fullDrawn, fullOn) && same(fullBack, fullOff), [fullOff.slice(0, 3), fullOn.slice(0, 3), fullDrawn.slice(0, 3), fullBack.slice(0, 3)]);
M.shut();
queryRunning = true; openMap(); const whileRun = [drawer.getAttribute('data-level'), bar(), level('analysis').getAttribute('title')]; queryRunning = false;
show(q0); const noTurns = [drawer.getAttribute('data-level'), bar(), level('analysis').getAttribute('title'), B.map(1).n];      // its run ended with no turn to go on from
press('analysis'); const pressedOff = drawer.getAttribute('data-level');
M.shut();
check('... the level cannot be shown while an analysis runs, nor for a chain with no turn to go on from: greyed, it says why under the pointer - the chain by its place in the thread -, '
  + 'and pressed it does nothing: the drawer is on the Workflow map',
  same(whileRun, ['workflow', 'Workflow4* / Chain 2 / Pathfinding- | Analysis-', 'An analysis is running'])
  && same(noTurns, ['workflow', 'Workflow4* / Chain 1 / Pathfinding- | Analysis-', 'Chain 1 has no turns to go back to', 0]) && pressedOff === 'workflow', [whileRun, noTurns, pressedOff]);

// ---- going back to a turn
const rule = () => ($('branchBack') || {}).textContent || '', chip = () => ($('branchChip') || {}).textContent || '';
const comp = () => ({ hint: doc.body.classList.contains('br-hint'), words: $('queryInput').placeholder, chip: chip(), rule: rule(), at: B.standing() });
show(a); openMap(); const tabsWere = $('contentOutput').innerHTML, paneWas = $('streamOutput').innerHTML, n0 = loaded.length;
goTo(2);
const back3 = comp(), shut3 = drawer.style.display;
openMap(); const map3 = [state().on, state().lit]; M.shut();
check('a click on a turn of the chain on screen goes back to it: the drawer shuts, the left pane ends at the turn - the cards after it, what stands under them and a hint given later are '
  + 'out of sight by a rule of the page\'s, the pane\'s own markup untouched -, the tabs stay as they are, and the composer is the hint\'s: its words ask for one, and the row under it says '
  + 'from which turn, with how many turns the analysis has left. On the map the turn is the open box, and the way to it is lit',
  same(back3, { hint: true, words: 'Say how the analysis should go on from turn 3', chip: 'From turn 3 · 5 turns left×',
                rule: '#streamOutput .sp-stream > .sp-turn[data-turn="3"] ~ .sp-turn, #streamOutput .sp-stream > .sp-turn[data-turn="3"] ~ .sp-turn ~ *, #streamOutput .sp-stream > .sp-turn[data-turn="3"] ~ .sp-hint { display: none; } '
                    + '#streamOutput .sp-stream > .sp-turn[data-turn="3"] > summary .sp-branch { color: var(--accent-color); border-color: var(--accent-color); }',
                at: { chain: 20, turn: 3 } })
  && shut3 === 'none' && $('contentOutput').innerHTML === tabsWere && loaded.length === n0 && $('streamOutput').innerHTML === paneWas && same(map3, ['3', '1,2,3'])
  && $('branchChip').parentNode === doc.querySelector('.icon-row') && doc.querySelector('.icon-row').firstElementChild === $('branchChip') && !!$('branchChip').querySelector('svg')
  && $('branchChip').querySelector('button').getAttribute('onclick') === 'BranchUI.leave()' && $('branchChip').querySelector('button').getAttribute('title') === 'Back to the end', [back3, map3]);
openMap(); goTo(7);                        // the last turn of another branch
const onB1 = [responses[currentResponseIndex] === b1, same(loaded.slice(n0), [21]), comp()];
openMap(); const mapB1 = [state().on, state().lit]; goTo(1);      // a turn the branch kept from the first run: on its way
const kept2 = [responses[currentResponseIndex] === b1, loaded.length === n0 + 1, comp(), $('streamOutput').querySelector('.sp-kept').hasAttribute('open')];
openMap(); const mapKept = [state().on, state().lit];
goTo(9);                                     // a turn of a branch of this branch, which can be gone on from
const onC5 = [responses[currentResponseIndex] === c, comp().at, comp().chip];
openMap(); goTo(5);                        // the first run's report
const onA6 = [responses[currentResponseIndex] === a, comp()];
const own = { hint: false, words: 'Enter your query here', chip: '', rule: '', at: null };
check('a click on a turn of another branch brings that branch on screen, tabs and pane: its last turn shows it whole, the composer its own; a turn it kept from the first run is on its '
  + 'way, so the branch stays and its pane ends there, in the fold of its kept turns, opened - on the map the open box is that turn, in the first run\'s line; a turn of a branch of it '
  + 'that can be gone on from brings that '
  + 'chain, gone back to the turn; the report of the first run brings the first run back whole',
  same(onB1, [true, true, own]) && same(mapB1, ['8', '1,2,3,7,8']) && kept2[0] && kept2[1] && same(kept2[2].at, { chain: 21, turn: 2 }) && kept2[2].chip === 'From turn 2 · 6 turns left×'
  && same(mapKept, ['2', '1,2'])
  && kept2[2].rule.startsWith('#streamOutput .sp-kept-body > .sp-turn[data-turn="2"] ~ .sp-turn,') && kept2[3] && same(onC5, [true, { chain: 23, turn: 5 }, 'From turn 5 · 3 turns left×']) && same(onA6, [true, own]),
  [onB1, mapB1, kept2, mapKept, onC5, onA6]);
show(s); openMap(); const sMap = [state().said, state().on]; goTo(1); const sBack = comp().at;
responses.push(k); show(k); openMap(); goTo(0); const kBack = comp().at;
openMap(); goTo(1); const kAsked = comp();
check('a stopped analysis can be gone on from the last turn it finished: the turn it was stopped in ended nothing, and has no box; the turn in which the analyst asked the person a '
  + 'question shows the chain whole, while the turn before it can be gone on from',
  same(sMap, ['2 turns', '2']) && same(sBack, { chain: 40, turn: 2 }) && same(kBack, { chain: 70, turn: 1 }) && same(kAsked, own), [sMap, sBack, kBack, kAsked]);
responses.push(e0); show(e0); openMap();
const noOwn = [state().said, state().on, state().lit, B.boxes(e0).length];
responses.push({ chain_id: 80, thread_id: 7, parentChainId: null, queryText: 'no turn yet', streamOutput: '<div class="sp-stream"></div>' });
M.shut(); show(responses[responses.length - 1]); const noBox = [B.map(6).n, B.map(6).off];
responses.splice(responses.indexOf(e0), 1); responses.splice(responses.length - 1, 1); responses.splice(responses.indexOf(k), 1);
check('a branch that made no turn of its own adds no box: on the map its place is the turn it went on from; a chain with no turn has no map to show',
  same(noOwn, ['11 turns · 4 branches', '2', '1,2', 11]) && same(noBox, [0, 'Chain 6 has no turns to go back to']), [noOwn, noBox]);
show(a); openMap(); goTo(2);
B.leave(); const left = comp();
openMap(); goTo(2); $('queryInput').dispatch('keydown', null, { key: 'a' }); const typed = !!B.standing();
$('queryInput').dispatch('keydown', null, { key: 'Escape' }); const escaped = comp();
openMap(); goTo(2); show(f); const moved = comp();
check('back to the end: the row\'s cross, the Escape key in the composer - no other key -, or another chain coming on screen; the pane is whole and the composer its own again', same(left, own) && typed && same(escaped, own) && same(moved, own), [left, typed, escaped, moved]);
// a hold on the composer (routines.js) keeps the composer's words under its own; the hint's words wait there too
show(a); openMap(); goTo(2);
const q = $('queryInput'); q.setAttribute('data-placeholder', q.placeholder); q.placeholder = 'A fill is running';
B.leave(); const heldLeft = [q.placeholder, q.getAttribute('data-placeholder'), q.getAttribute('data-own')];
openMap(); goTo(2); const heldBack = [q.placeholder, q.getAttribute('data-placeholder')];
q.placeholder = q.getAttribute('data-placeholder'); q.removeAttribute('data-placeholder');      // the hold ends
const freed = q.placeholder; B.leave();
check('where the composer is held, the hold\'s words stay on it: the hint\'s wait under them and show when the hold ends, and leaving the turn puts the composer\'s own back there',
  same(heldLeft, ['A fill is running', 'Enter your query here', null]) && same(heldBack, ['A fill is running', 'Say how the analysis should go on from turn 3']) && freed === 'Say how the analysis should go on from turn 3'
  && q.placeholder === 'Enter your query here', [heldLeft, heldBack, freed, q.placeholder]);

// ---- the drawer, as chains come on screen
show(a); openMap(); const saidA = state().said; show(s); const saidS = state().said; show(c); const saidC = state().said;
check('the Analysis level says how many turns and branches the analysis of the chain on screen has, on any chain of it - and no word of branches where it has none',
  same([saidA, saidS, saidC], ['11 turns · 3 branches', '2 turns', '11 turns · 3 branches']), [saidA, saidS, saidC]);
show(a); show(b1); const followed = [drawer.style.display, state().level, state().on, state().lit];
show(f); const other = [state().level, state().bar, nodes().length];
show(q0); const without = [drawer.style.display, state().level, state().bar];
show(a); const stays = state().level;
press('analysis'); queryRunning = true; updateNavigationButtons(); const running = [drawer.style.display, state().level, state().said]; queryRunning = false;
M.shut();
check('the drawer, while it is open, follows the chain on screen (0327): another chain of the analysis, and the map is drawn again around that chain\'s last turn; a chain of another analysis, '
  + 'and the map is that analysis\'s; a chain with no turns to go back to, and the drawer goes to the Workflow map - and stays there when a chain that has some comes back; a run '
  + 'beginning, and it goes to the Workflow map, the level saying why',
  same(followed, ['flex', 'analysis', '8', '1,2,3,7,8']) && same(other, ['analysis', 'Workflow4 / Chain 3 / Pathfinding- | Analysis2*', 2])
  && same(without, ['flex', 'workflow', 'Workflow4* / Chain 1 / Pathfinding- | Analysis-']) && stays === 'workflow' && same(running, ['flex', 'workflow', 'An analysis is running']),
  [followed, other, without, stays, running]);

// ---- a hint sent
show(b1); openMap(); goTo(1);
const none = (show(a), B.hint('typed with no turn gone back to'));
show(b1); openMap(); goTo(1);
const going = B.hint('start over from the slip'), after = comp();
responses.push({ status: 'running', chain_id: null, thread_id: 7, parentChainId: 21, queryText: going.question, streamOutput: '' });      // as beginLiveChain leaves it
Object.assign(liveState, { running: true, index: responses.length - 1, parent: 21 }); currentResponseIndex = liveState.index; currentData.branch = { of: going.of, turn: going.turn, hint: going.hint };
B.started(going);
const live = responses[liveState.index], begun = [live.branch, live.parentChainId, liveState.parent, same(B.place(), { i: 2, n: 4 }), B.unstarted()];
B.heard('an error that is not about this request, before the chain is announced');
B.announced({ type: 'id', chain_id: 98, thread_id: 7, parent_chain_id: 10 });      // a chain that goes on from no other: the server started no branch
const notYet = B.unstarted();
B.announced({ type: 'id', chain_id: 24, thread_id: 7, parent_chain_id: 10, branch_of: 20, branch_turn: 2 });
B.heard('an error later in the run');
const told = [live.branch, currentData.branch, B.unstarted(), framed.length];
const t0 = toasts.length, nWas = responses.length; B.notStarted('too late to undo'); const late = [toasts.length - t0, responses.length - nWas, liveState.running];
check('a hint sent: with a turn gone back to, what is typed is a hint - the branch it starts names the chain on screen, the turn, the chain that turn is a turn of its own, the '
  + 'analysis\'s question and where it attached -, and the composer is its own again; with no turn gone back to there is none. The chain begun for it is its analysis\'s from the first '
  + 'moment - the arrows count no new analysis - and attaches where the analysis did. It is started when the server announces a chain that goes on from another, and by no other chain\'s '
  + 'announcement; once started it is not undone',
  none === null && same([going.chain, going.of, going.turn, going.hint, going.question, going.parent, going.framing], [21, 20, 2, 'start over from the slip', 'How do the two blocks compare?', 10, null]) && same(after, own)
  && same(begun, [{ of: 20, turn: 2, hint: 'start over from the slip' }, 10, 10, true, true]) && same(told, [{ of: 20, turn: 2, hint: 'start over from the slip' }, { of: 20, turn: 2, hint: 'start over from the slip' }, false, 0])
  && notYet === true && same(late, [0, 0, true]), [none, going, after, begun, notYet, told, late]);
// the run ends as any does: the chain is saved with its branch (saveCurrentResponse), and is the one its analysis shows
responses[liveState.index] = entry(24, 10, going.question, keep(A.slice(0, 2)).concat([{ n: 3, kind: 'report', step: 'Started over.' }]), { branch: { of: 20, turn: 2, hint: going.hint }, entryBranch: currentData.branch });
Object.assign(liveState, { running: false, index: null }); const d = responses[responses.length - 1]; show(d);
check('... once saved the branch is one more way of its analysis: its Analysis map has its turns, joined to the turn it went on from, and it is the chain the arrows show for the analysis',
  same(B.boxes(a).slice(-1).map(x => [x.key, x.from]), [['24:3', '20:2']]) && same(ids(), [10, 24, 30, 40]) && B.map(2).said === '12 turns · 4 branches' && $('streamOutput').querySelector('.sp-hint').textContent === 'Branch from turn 2start over from the slip');
// a branch the server did not start: it said why before it announced a chain
show(b1); openMap(); goTo(2);
const again = B.hint('keep them apart, again'), n1 = responses.length, t1 = toasts.length;
responses.push({ status: 'running', chain_id: null, thread_id: 7, parentChainId: 21, queryText: again.question, streamOutput: '' });
Object.assign(liveState, { running: true, index: responses.length - 1, parent: 21 }); currentResponseIndex = liveState.index; currentData.branch = { of: again.of, turn: again.turn, hint: again.hint };
B.started(again); $('streamOutput').innerHTML = '<div class="sp-sys error">refused</div>';
B.heard('Load the data this analysis ran on first: trial.csv.');
const was = B.unstarted(); B.notStarted();
const refused = { n: responses.length, live: [liveState.running, liveState.index], on: responses[currentResponseIndex] === b1, at: B.standing(), typed: $('queryInput').value, toast: toasts.slice(t1), branch: currentData.branch,
                  pane: $('streamOutput').querySelectorAll('.sp-turn[data-turn]').length === 5 && !$('streamOutput').querySelector('.sp-sys'), unstarted: B.unstarted() };
check('a branch the server did not start - it said why, and announced no chain: the chain begun for it leaves the thread, the chain the hint was typed on is back on screen at its turn, '
  + 'the hint is in the composer to send again, and the server\'s sentence is said',
  was === true && same(refused, { n: n1, live: [false, null], on: true, at: { chain: 21, turn: 3 }, typed: 'keep them apart, again', toast: ['Load the data this analysis ran on first: trial.csv.'], branch: null, pane: true, unstarted: false }), refused);
$('queryInput').value = ''; B.leave();
B.notStarted('nothing was asked for'); const idle = toasts.slice(-1)[0];
// a framed analysis: its branch runs under the same brief
const fr = entry(50, null, 'Is B above A?', [{ n: 1, kind: 'cell', step: 'The brief fixes the measure. This turn computes it.', cell: 1, out: 'B 0.6' }, { n: 2, kind: 'report', step: 'B is above A.' }], {});
fr.contentOutput = '<div id="content-brief"><div class="ar-brief" data-chain="50" data-framing="{&quot;versions&quot;:[{&quot;n&quot;:1,&quot;brief&quot;:{&quot;question&quot;:&quot;Is B above A?&quot;}}],&quot;step&quot;:1}"></div></div>';
responses.push(fr); show(fr); openMap(); goTo(0);
const fg = B.hint('by week'); B.announced({ type: 'id', chain_id: 51, thread_id: 7, parent_chain_id: null, branch_of: 50, branch_turn: 1 });
check('a framed analysis\'s branch runs under the same brief: when the server announces its chain the page is given the framing of the analysis it goes on from, for that chain - the fold '
  + 'above its run and its Brief tab (architect.js); an analysis without a brief has none, and a request that started nothing says nothing where there is nothing to say',
  same(fg.framing, { versions: [{ n: 1, brief: { question: 'Is B above A?' } }], step: 1 }) && same(framed, [{ framing: fg.framing, chain_id: 51, thread_id: 7, queryText: 'Is B above A?' }]) && idle !== 'nothing was asked for',
  [fg.framing, framed, idle]);

// ---- the page's hooks, from the sources
const js = n => fs.readFileSync(path.join(JS, n), 'utf8'), css = n => fs.readFileSync(path.join(JS, '..', 'css', n), 'utf8');
const qp = js('query-processing.js'), wm = js('workflow-management.js'), uc = js('ui-controls.js'), graph = js('workflowGraph.js'), core = js('core.js'), ar = js('architect.js');
const shell = css('shell.css'), paneCss = css('pane.css');
check('the composer\'s send: a typed text is offered to the branch first - a hint where a turn is gone back to - and the Pathfinder is not asked for a branch; the chain begun keeps the '
  + 'analysis\'s question and the branch; the request names the turn; a branch the server did not start - the limit, the network, its own refusal - is undone, and nothing is saved of it',
  qp.includes("const branch = typed && window.BranchUI ? window.BranchUI.hint(query) : null;") && qp.includes("if (window.ArchitectUI && !framed && !branch) {")
  && qp.indexOf('window.BranchUI.hint(query)') < qp.indexOf('window.ArchitectUI.framingInView()') && qp.includes("currentData.queryText = branch ? branch.question : query;")
  && qp.includes("currentData.branch = branch ? { of: branch.of, turn: branch.turn, hint: query } : null;") && qp.includes("if (branch) window.BranchUI.started(branch);")
  && qp.indexOf('beginLiveChain(framed);') < qp.indexOf('window.BranchUI.started(branch)') && qp.includes("if (branch) requestBody.branch = { turn: branch.turn };")
  && qp.includes("if (branch) window.BranchUI.notStarted();") && qp.includes("if (branch && window.BranchUI.unstarted()) window.BranchUI.notStarted();")
  && qp.includes("else if (typeof saveCurrentResponse === 'function') saveCurrentResponse();") && qp.includes("if (branch && !streaming) window.BranchUI.notStarted(error.message);"));
check('the stream: the chain\'s announcement is handed to the branch, and so is an error; the saved chain keeps its branch; the arrows and their count go by analyses, and a chain on '
  + 'screen is told to the branch before the brief\'s hold reads the composer; the module is started with the page, after the scripts it leans on',
  qp.includes("if (window.BranchUI) window.BranchUI.announced(data);") && qp.includes("if (window.BranchUI) window.BranchUI.heard(data.error);") && wm.includes("branch: data.branch || null")
  && wm.includes("const to = window.BranchUI.step(direction);") && wm.includes("if (to) currentResponseIndex = responses.indexOf(to);")
  && uc.includes("const at = window.BranchUI ? window.BranchUI.place() : { i: currentResponseIndex + 1, n: responses.length };") && uc.includes("prevButton.disabled = at.i <= 1;") && uc.includes("nextButton.disabled = at.i >= at.n;")
  && uc.indexOf('window.BranchUI.onChain(responses[currentResponseIndex])') > 0 && uc.indexOf('window.BranchUI.onChain(responses[currentResponseIndex])') < uc.indexOf('window.ArchitectUI.onChain(responses[currentResponseIndex])')
  && core.includes("window.BranchUI.initialize();") && html.indexOf("js/branch.js") > html.indexOf("js/next-questions.js") && html.indexOf("js/branch.js") < html.indexOf("js/workflowGraph.js"));
const branchJs = js('branch.js'), paneJs = js('stream-pane.js');
check('the Workflow map: its boxes are the analyses, the open one that of the chain on screen, the level counting chains and their branches; a box\'s button in the panel - or a double '
  + 'click on it (0333; a click until then) - brings its chain on screen through the branch, and no longer shuts the drawer; a box has no way into the code trace (0330); the drawing takes a map\'s own mark for a box; the Pathfinder\'s cards have the Git '
  + 'branch mark, the left bar\'s button the map\'s',
  wm.includes("var boxes = window.BranchUI ? window.BranchUI.items() : responses;") && wm.includes("WorkflowGraph.render(document.getElementById('workflowMapContainer'), boxes, window.BranchUI ? window.BranchUI.place().i - 1 : currentResponseIndex);")
  && wm.includes("var branches = boxes.reduce(function (sum, r) { return sum + (r.branches || 0); }, 0);") && !wm.includes('showWorkflowMap') && !/workflowMapModal[^\n]*\.style\.display/.test(wm)
  && graph.includes("if (window.BranchUI) window.BranchUI.open(responses[i]);") && graph.includes("var made = of ? (of.tag ? of.tag(resp, idx) : '') : (window.ArchitectUI ? window.ArchitectUI.mark(resp) : '');")
  && graph.includes("if (!of && resp && resp.branches) {") && !graph.includes('wf-node-map') && !graph.includes('CodeMapUI') && !graph.includes(".style.display = 'none'") && graph.includes("mapContainer.onwheel = function (e) {")
  && ar.includes('<line x1="6" y1="3" x2="6" y2="15"/>') && !ar.includes('<rect x="8.5" y="15" width="7" height="6" rx="1.5"/>')
  && html.includes('<rect x="8.5" y="15" width="7" height="6" rx="1.5"/>'));
check('the Analysis map is the drawer\'s (0327), from the sources: no button to it is made above an analysis - the run\'s end marks the row of the ids instead, and a pane kept with the '
  + 'button hides it, the button still read as the mark; the module gives the level to the drawer, shuts the drawer when a turn is clicked, and has it follow when a turn is gone back '
  + 'to or left; the words say why the level cannot be shown',
  !paneJs.includes('sp-turnmap') && !paneJs.includes('turnMap') && paneJs.includes("if (r.turn_map && ids) ids.setAttribute('data-branch', '1');")
  && branchJs.includes("const goesOn = pane => !!pane && !!(pane.querySelector('.sp-ids[data-branch]') || pane.querySelector('.sp-turnmap'));") && paneCss.includes("#streamOutput .sp-turnmap { display: none; }")
  && !branchJs.includes('openMap') && !branchJs.includes('mapFollows') && /window\.BranchUI = \{ initialize, map, onChain,/.test(branchJs) && (branchJs.match(/window\.MapsUI\.follow\(\);/g) || []).length === 2
  && branchJs.includes("window.MapsUI.shut();\n                go(here && owner(here, b.turn.n) === b.entry ? here : b.entry, b.turn.n);")
  && branchJs.includes("mapOff: { running: 'An analysis is running', none: n => 'Chain ' + n + ' has no turns to go back to' },"));
check('the stylesheets: with a turn gone back to the composer shows no file menu, no mode and no Pathfinder switch, and the row of the turn is styled; the drawer hides the thread\'s '
  + 'buttons while it holds the turns; the Workflow map\'s box has a place for its branches; kept turns are faint, in a fold that shows as a stack of cards while it is shut (0330); a '
  + 'cell that printed something else is marked; the hint is a card in the colours of the composer\'s row of a turn gone back to, its words whole, on their lines; the ids\' row stays in '
  + 'view under the strip, on one line, its last id giving way first',
  shell.includes("body.br-hint .left-panel .icon-row .attach-menu-container, body.br-hint .left-panel #modeSliderPopup, body.br-hint .left-panel .icon-row .ar-switch { display: none !important; }")
  && shell.includes(".left-panel .icon-row .br-chip {") && shell.includes('#workflowMapModal:not([data-level="workflow"]) .map-drawer-foot { display: none; }') && shell.includes("#workflowMapModal .wf-node-branches {")
  && paneCss.includes("#streamOutput .sp-turn.kept, #streamOutput .sp-row.kept { opacity: .6; }") && paneCss.includes("#streamOutput .sp-row.differs .t {")
  && paneCss.includes("#streamOutput .sp-kept > summary { opacity: .6; }") && /#streamOutput \.sp-kept:not\(\[open\]\) \{[^}]*box-shadow: /.test(paneCss) && paneCss.includes("#streamOutput .sp-kept-body {")
  && /#streamOutput \.sp-hint \{[^}]*border: 1px solid var\(--chip-model-border\);/.test(paneCss) && /\.br-chip \{[^}]*border: 1px solid var\(--chip-model-border\);/.test(shell)
  && /#streamOutput \.sp-hint \.hd \{[^}]*color: var\(--c-model\);/.test(paneCss) && /\.br-chip \{[^}]*color: var\(--c-model\);/.test(shell)
  && /#streamOutput \.sp-hint \.said \{[^}]*white-space: pre-wrap;/.test(paneCss)
  && shell.includes(".left-panel #streamOutput .sp-ids-slot { position: sticky; top: 41px;") && shell.includes(".left-panel #streamOutput .sp-strip { top: 0; height: 41px;")
  && /#streamOutput \.sp-ids \{[^}]*white-space: nowrap;/.test(paneCss) && paneCss.includes("#streamOutput .sp-ids > span { min-width: 0; overflow: hidden; text-overflow: ellipsis; }")
  && paneCss.includes("#streamOutput .sp-ids > span:last-of-type { flex-shrink: 10000; }"));

// ---- the branch button on a turn's card (0323): the way to a turn without the map
const cardBtns = e => holder(e.streamOutput).querySelectorAll('.sp-turn[data-turn]').map(x => [x.getAttribute('data-turn'), (x.querySelector('summary .sp-branch') || { getAttribute: () => null }).getAttribute('title')]);
const pressCard = n => B.from($('streamOutput').querySelectorAll('.sp-turn[data-turn]').find(x => x.getAttribute('data-turn') === String(n)).querySelector('summary .sp-branch'));
check('the branch button on a turn\'s card: when a run ends with turns to go on from, every turn it can go on from has one in its card\'s head, after the prompt\'s button, saying its turn - '
  + 'the turns a branch kept too, in their fold; the report\'s card has none, nor a question\'s to the person, a review\'s, or the card of a turn the run was stopped in; a run with no turn to go on from has none',
  same(cardBtns(a), [['1', 'Branch from turn 1'], ['2', 'Branch from turn 2'], ['3', 'Branch from turn 3'], ['4', 'Branch from turn 4'], ['review', null], ['5', 'Branch from turn 5'], ['6', null]])
  && same(cardBtns(b1), [['1', 'Branch from turn 1'], ['2', 'Branch from turn 2'], ['3', 'Branch from turn 3'], ['4', 'Branch from turn 4'], ['5', null]])
  && same(cardBtns(s), [['1', 'Branch from turn 1'], ['2', 'Branch from turn 2'], ['3', null]]) && same(cardBtns(k), [['1', 'Branch from turn 1'], ['2', null]]) && same(cardBtns(q0), [['1', null]])
  && holder(a.streamOutput).querySelector('.sp-turn summary').elements.map(x => x.className.split(' ').pop()).join('|') === 'chev|n|kind|peek|meta|sp-prompt|sp-branch'
  && holder(a.streamOutput).querySelector('.sp-branch').getAttribute('onclick') === 'event.preventDefault(); if (window.BranchUI) BranchUI.from(this);'
  && holder(a.streamOutput).querySelector('.sp-branch').getAttribute('aria-label') === 'Branch from turn 1' && !!holder(a.streamOutput).querySelector('.sp-branch svg'),
  [cardBtns(a), cardBtns(b1), cardBtns(s), cardBtns(k), cardBtns(q0)]);
show(a);
const cardPane = $('streamOutput').innerHTML, cardLoads = loaded.length;
pressCard(3);
const cardAt3 = comp(), cardSame = $('streamOutput').innerHTML === cardPane && loaded.length === cardLoads;
pressCard(1);
const cardAt1 = comp().at;
pressCard(1);
const cardOff = comp();
queryRunning = true;
const cardToasts = toasts.length;
pressCard(2);
const cardBusy = [comp().at, toasts.length - cardToasts, toasts.slice(-1)[0]];
queryRunning = false;
show(b1); pressCard(2);
const cardKept = [responses[currentResponseIndex] === b1, comp().at, comp().chip];
B.leave();
check('... a click goes back to that turn of the chain on screen, as a click on its box of the map: the pane ends there by the page\'s rule - which lights the turn\'s button -, its markup '
  + 'untouched, and the composer is the hint\'s; another turn\'s button goes to that turn; the button of the turn gone back to brings the end back; while an analysis runs it says so and '
  + 'goes nowhere; a turn a branch kept is gone back to on the branch',
  same(cardAt3.at, { chain: 20, turn: 3 }) && cardAt3.hint && cardAt3.chip === 'From turn 3 · 5 turns left×'
  && cardAt3.rule.endsWith('[data-turn="3"] > summary .sp-branch { color: var(--accent-color); border-color: var(--accent-color); }')
  && cardSame && same(cardAt1, { chain: 20, turn: 1 }) && same(cardOff, own) && same(cardBusy, [null, 1, B.WORDS.busy]) && same(cardKept, [true, { chain: 21, turn: 2 }, 'From turn 2 · 6 turns left×']),
  [cardAt3, cardSame, cardAt1, cardOff, cardBusy, cardKept]);
const oldChain = Object.assign({}, a, { chain_id: 90, parentChainId: null, streamOutput: a.streamOutput.replace(/<button type="button" class="sp-branch"[^>]*>.*?<\/button>/g, '') });
const plainChain = entry(91, null, 'An analysis from before 2.9', [{ n: 1, kind: 'cell', step: 'First. This turn loads.', cell: 1, out: 'one' }, { n: 2, kind: 'report', step: 'Done.' }], { map: false });
responses.push(oldChain, plainChain);
const cardsBare = cardBtns(oldChain).filter(x => x[1]).length;
show(oldChain);
const cardsDressed = $('streamOutput').querySelectorAll('.sp-branch').length;
B.dress($('streamOutput'));
const cardsTwice = $('streamOutput').querySelectorAll('.sp-branch').length;
pressCard(4);
const cardOld = comp().at;
B.leave(); show(plainChain);
const cardsPlain = $('streamOutput').querySelectorAll('.sp-branch').length + holder(plainChain.streamOutput).querySelectorAll('.sp-branch').length;
check('... a chain kept from before the button existed gets its buttons when it comes on screen - once, however often it is dressed - and they work; a chain that cannot be gone on from gets none, when its run ends or later',
  cardsBare === 0 && cardsDressed === 5 && cardsTwice === 5 && same(cardOld, { chain: 90, turn: 4 }) && cardsPlain === 0, [cardsBare, cardsDressed, cardsTwice, cardOld, cardsPlain]);
// a pane kept by a build before the maps had one drawer (0318 to 0326): no mark on the ids' row, and the button to the Analysis map at its end
const withButton = oldChain.streamOutput.replace('<div class="sp-ids" data-branch="1">', '<div class="sp-ids">')
  .replace(/(<div class="sp-ids">.*?)(<\/div>)/, '$1<button type="button" class="sp-turnmap" title="Analysis map" onclick="if(window.BranchUI)BranchUI.openMap()"><span>Analysis map</span><span class="n"></span></button>$2');
const keptChain = Object.assign({}, a, { chain_id: 92, parentChainId: null, streamOutput: withButton });
responses.push(keptChain); show(keptChain);
const keptMarks = [withButton !== oldChain.streamOutput, !!holder(withButton).querySelector('.sp-ids .sp-turnmap'), holder(withButton).querySelector('.sp-ids').hasAttribute('data-branch')];
const keptWorks = [$('streamOutput').querySelectorAll('.sp-branch').length, B.map(7).n, B.map(7).off];
responses.splice(responses.indexOf(keptChain), 1);
check('... a pane kept with the button to the Analysis map (0318 to 0326) is one that can be gone on from, as that button said: its turns get their buttons and its map can be shown',
  same(keptMarks, [true, true, false]) && same(keptWorks, [5, 6, '']), [keptMarks, keptWorks]);
check('the stylesheet: the branch button stands before the prompt\'s in a card\'s head, whatever their order in the markup, in a box of its size, on its line; a kept turn, which has no prompt, leaves that place empty',
  /#streamOutput \.sp-branch \{ order: 1;[^}]*width: 22px; height: 18px; margin: 0 -10px 0 6px;/.test(paneCss) && paneCss.includes("#streamOutput .sp-turn > summary .sp-prompt { order: 2; box-sizing: border-box; min-width: 22px; height: 18px; margin-bottom: 0; justify-content: center; }")
  && paneCss.includes("#streamOutput .sp-turn.kept > summary .sp-branch { margin-right: 28px; }") && paneCss.includes("#streamOutput .sp-branch:hover { color: var(--accent-color); border-color: var(--accent-color); }"));

// ---- the fold of a branch's kept turns, on screen (0330)
const foldOn = () => $('streamOutput').querySelector('.sp-kept'), foldNow = () => [saysOf(foldOn()), foldOn() ? foldOn().hasAttribute('open') : null];
show(b1); const onB1Fold = foldNow(), oneFold = $('streamOutput').querySelectorAll('.sp-kept').length;
const b1Pane = $('streamOutput').innerHTML; B.onChain(b1); const toldTwice = $('streamOutput').innerHTML === b1Pane;
show(c); const onCFold = foldNow(); show(b2); const onB2Fold = foldNow(); show(a); const onAFold = foldOn();
check('the fold of a branch\'s kept turns, on screen (0330): shut, it says where the turns come from - the original, or a branch by the number the arrows give it - as soon as the chain '
  + 'is on screen, once however often the page tells it; a chain that keeps no turns has no fold',
  same(onB1Fold, [['Turns 1–3', 'kept', 'from the original', '2 cells (1 failed)'], false]) && oneFold === 1 && toldTwice
  && same(onCFold, [['Turns 1–4', 'kept', 'from branch 1', '3 cells (1 failed)'], false]) && same(onB2Fold, [['Turns 1–3', 'kept', 'from the original', '2 cells (1 failed)'], false])
  && onAFold === null, [onB1Fold, oneFold, toldTwice, onCFold, onB2Fold]);
// a branch's pane kept by 0320 to 0329: its kept turns loose, over a row of its hint
const oldPane = holder(b1.streamOutput), oldFold = oldPane.querySelector('.sp-kept');
oldFold.querySelector('.sp-kept-body').elements.forEach(x => oldFold.parentNode.insertBefore(x, oldFold)); oldFold.remove();
oldPane.querySelector('.sp-hint').innerHTML = '<svg viewBox="0 0 24 24"><line x1="6" y1="3" x2="6" y2="15"/></svg><b>From turn 3</b><span>keep the two blocks apart</span>';
const oldB1 = Object.assign({}, b1, { chain_id: 28, streamOutput: oldPane.innerHTML });
responses.push(oldB1); show(oldB1);
const oldNow = { rows: $('streamOutput').querySelector('.sp-stream').elements.map(e => e.className.split(' ').slice(0, 3).join('.')), fold: foldNow(),
                 inFold: foldOn().querySelector('.sp-kept-body').elements.map(e => e.className.split(' ').slice(0, 3).join('.')),
                 hint: [$('streamOutput').querySelector('.sp-hint .hd').textContent, $('streamOutput').querySelector('.sp-hint .said').textContent, !!$('streamOutput').querySelector('.sp-hint .hd svg')],
                 turns: B.turnsOf({ streamOutput: $('streamOutput').innerHTML }).map(t => t.n).join(), kept: B.turnsOf(oldB1).map(t => t.n).join(), buttons: foldOn().querySelectorAll('.sp-branch').length };
const oldShown = $('streamOutput').innerHTML; w.paneRenew($('streamOutput')); B.onChain(oldB1);
const oldAgain = $('streamOutput').innerHTML === oldShown;
responses.pop();
check('... a branch\'s pane kept by 0320 to 0329 - its kept turns loose, over a row of its hint - comes on screen in today\'s shape: its kept turns in the fold, which says where they '
  + 'come from, and its hint a card; its turns read the same in the markup kept and on screen, and the kept ones have their buttons in the fold; once, however often it is renewed',
  same(oldNow, { rows: ['sp-turn.sp-kept', 'sp-hint', 'sp-turn', 'sp-row', 'sp-turn', 'sp-done'], fold: [['Turns 1–3', 'kept', 'from the original', '2 cells (1 failed)'], false],
                 inFold: ['sp-turn.kept', 'sp-row.kept', 'sp-turn.kept', 'sp-row.fail.kept', 'sp-turn.kept', 'sp-row.kept'], hint: ['Branch from turn 3', 'keep the two blocks apart', true],
                 turns: '1,2,3,4,5', kept: '1,2,3,4,5', buttons: 3 }) && oldAgain, [oldNow, oldAgain]);
// a kept turn that searched (the walk's first analysis searches in its second turn): its pages stand on its card (0339); in a pane kept
// before 0339 its sources stand under it, a row and pills
const ofSearch = s => { const f = s.querySelector('.sp-kept'), cls = e => e.className.split(' ').slice(0, 2).join('.');
  return { rows: s.elements.map(cls), inFold: f ? f.querySelector('.sp-kept-body').elements.map(cls) : null, says: saysOf(f) }; };
$('streamOutput').innerHTML = '';
w.paneIds({ thread_id: 7, chain_id: 29, df_id: 'd1' }); w.paneRunStart({ mode: 'Deep', of: 8, dollars: 1, branch: { of: 20, turn: 3, hint: 'after the search' } });
w.paneTurnStart({ turn: 1, kept: true }); w.paneTurnEnd({ turn: 1, kind: 'cell', thinking: 'The data first. This turn loads it.', kept: true });
w.paneCell({ cell_no: 1, ok: true, peek: 'rows 92', kept: 'kept' });
w.paneTurnStart({ turn: 2, kept: true }); w.paneTurnEnd({ turn: 2, kind: 'search', thinking: 'Loaded. This turn searches.', kept: true });
w.paneLookup({ kind: 'search', query: 'fertiliser trials', peek: 'two sources', sources: [{ n: 1, url: 'https://example.org/a', title: 'Trial A', host: 'example.org' }, { n: 2, url: 'https://example.org/b', title: 'Trial B', host: 'example.org' }], claims: [] });
w.paneTurnStart({ turn: 3, kept: true }); w.paneTurnEnd({ turn: 3, kind: 'cell', thinking: 'Searched. This turn pools the blocks.', kept: true });
w.paneCell({ cell_no: 2, ok: true, peek: 'pooled 20', kept: 'kept' });
w.paneTurnStart({ turn: 4, of: 8, seat: 'Analyst', model: 'm', chain_id: 29 }); w.paneTurnEnd({ turn: 4, kind: 'report', thinking: 'Done.', elapsed: 1, cost: 0 });
w.paneRunEnd({ status: 'answered', turns: 4, of: 8, cells: 2, cost: 0, seconds: 1, chain_id: 29 });
const searchedLive = ofSearch($('streamOutput').querySelector('.sp-stream'));
const pagesLive = Array.from($('streamOutput').querySelectorAll('.sp-kept .sp-turn.search .sp-face .ttl')).map(a => a.textContent).join();
const keptOld = $('streamOutput').querySelector('.sp-stream'), oldFold2 = keptOld.querySelector('.sp-kept');      // as 0320 to 0329 kept it: loose, the hint a row
oldFold2.querySelector('.sp-kept-body').elements.forEach(x => keptOld.insertBefore(x, oldFold2)); oldFold2.remove();
const wasSearch = keptOld.querySelector('.sp-turn.search'), oldRows = doc.createElement('div');      // and its search as before 0339: a row, and a pill for each page
wasSearch.querySelector('summary .sp-face').remove(); wasSearch.classList.remove('search');
oldRows.innerHTML = '<div class="sp-row tool"><span>⌕</span><span class="in">SEARCH fertiliser trials</span><span class="out">two sources</span><span class="t">2 sources</span></div>'
  + '<div class="sp-pills"><a class="sp-pill src" href="https://example.org/a"><span class="t">Trial A</span></a><a class="sp-pill src" href="https://example.org/b"><span class="t">Trial B</span></a></div>';
const afterSearch = wasSearch.nextElementSibling; oldRows.elements.forEach(x => keptOld.insertBefore(x, afterSearch));
keptOld.querySelector('.sp-hint').innerHTML = '<b>From turn 3</b><span>after the search</span>';
w.paneRenew($('streamOutput'));
const searchedOld = ofSearch(keptOld);
check('... a kept turn that searched has its pages on its card, in the fold (0339), and the kept turns after it go in too as they arrive; in a pane kept by 0320 to 0329, before 0339, '
  + 'its search\'s row and pills go into the fold with it',
  same(searchedLive, { rows: ['sp-turn.sp-kept', 'sp-hint', 'sp-turn', 'sp-done'], inFold: ['sp-turn.kept', 'sp-row.kept', 'sp-turn.kept', 'sp-turn.kept', 'sp-row.kept'],
                       says: ['Turns 1–3', 'kept', 'from the original', '2 cells'] }) && pagesLive === 'Trial A,Trial B'
  && same(searchedOld, { rows: searchedLive.rows, inFold: ['sp-turn.kept', 'sp-row.kept', 'sp-turn.kept', 'sp-row.tool', 'sp-pills', 'sp-turn.kept', 'sp-row.kept'], says: ['Turns 1–3', 'kept', '', '2 cells'] }),
  [searchedLive, pagesLive, searchedOld]);
// a hint is text, whatever it holds; a turn of the branch's own stays out of the fold, with no hint's card between too
const keptThen = (hint, chain) => {
  $('streamOutput').innerHTML = '';
  w.paneRunStart({ mode: 'Deep', of: 8, dollars: 1, branch: { of: 20, turn: 1, hint } });
  w.paneTurnStart({ turn: 1, kept: true }); w.paneTurnEnd({ turn: 1, kind: 'cell', thinking: 'Loads. This turn loads.', kept: true });
  w.paneTurnStart({ turn: 2, of: 8, seat: 'Analyst', model: 'm', chain_id: chain }); w.paneTurnEnd({ turn: 2, kind: 'report', thinking: 'Done.', elapsed: 1, cost: 0 });
  w.paneRunEnd({ status: 'answered', turns: 2, of: 8, cells: 0, cost: 0, seconds: 1, chain_id: chain });
  return $('streamOutput').querySelector('.sp-stream');
};
const marked = keptThen('keep <b>A</b> & <i>B</i> apart', 97).querySelector('.sp-hint .said'), asText = [marked.textContent, marked.elements.length];
const noCard = keptThen('', 96).elements.map(e => e.className);
check('... the hint is text, whatever it holds; and the fold holds the kept turns alone: a turn of the branch\'s own stays out of it, also where no hint\'s card stands between',
  same(asText, ['keep <b>A</b> & <i>B</i> apart', 0]) && same(noCard, ['sp-turn sp-kept', 'sp-turn', 'sp-done']), [asText, noCard]);
// going back to a turn the branch kept
show(b1);
const keptRule = n => { const t = '#streamOutput .sp-kept-body > .sp-turn[data-turn="' + n + '"]';
  return t + ' ~ .sp-turn, ' + t + ' ~ .sp-turn ~ *, #streamOutput .sp-stream > .sp-kept ~ * { display: none; } ' + t + ' > summary .sp-branch { color: var(--accent-color); border-color: var(--accent-color); }'; };
pressCard(2); const atKept2 = [comp().at, comp().rule === keptRule(2), foldNow()[1]];
pressCard(4); const atOwn4 = [comp().at, comp().rule.startsWith('#streamOutput .sp-stream > .sp-turn[data-turn="4"] ~ .sp-turn, '), foldNow()[1]];
pressCard(1); const atKept1 = [comp().at, comp().rule === keptRule(1), foldNow()[1]];
B.leave(); const leftKept = [comp().at, comp().rule, foldNow()[1]];
foldOn().setAttribute('open', '');                                // the person opens the fold
pressCard(3); const theirs3 = foldNow()[1]; B.leave(); const theirsLeft = foldNow()[1];
foldOn().removeAttribute('open'); pressCard(2); show(f); show(b1); const comesBack = [comp().at, foldNow()[1]];
check('going back to a turn a branch kept (0330): the fold opens, and the page\'s rule ends the pane at the turn - the kept turns after it are out of sight, and all that stands under the '
  + 'fold; going to a turn of the branch\'s own shuts it again, and so does going back to the end. A fold the person opened stays open; the chain drawn again has it shut',
  same(atKept2, [{ chain: 21, turn: 2 }, true, true]) && same(atOwn4, [{ chain: 21, turn: 4 }, true, false]) && same(atKept1, [{ chain: 21, turn: 1 }, true, true])
  && same(leftKept, [null, '', false]) && theirs3 === true && theirsLeft === true && same(comesBack, [null, false]), [atKept2, atOwn4, atKept1, leftKept, theirs3, theirsLeft, comesBack]);
// the Analysis map's foot: the whole of what a turn said, as the page has it - streamed into the turn's card, on more than one line
const longStep = 'The blocks were pooled in the turn before, and the pooled figure stands. This turn compares the blocks on the pooled figure, block by block, and keeps the '
  + 'difference for the report, with how far apart they are in the units of the data.\nIt also says which <block> is the larger, so the report can say it plainly.';
$('streamOutput').innerHTML = '';
w.paneIds({ thread_id: 7, chain_id: 27, df_id: 'd1' }); w.paneRunStart({ mode: 'Deep', of: 8, dollars: 1.5 });
w.paneTurnStart({ turn: 1, of: 8, seat: 'Analyst', model: 'm', chain_id: 27 }); w.paneToken('###STEP###\n' + longStep);
w.paneTurnEnd({ turn: 1, kind: 'cell', thinking: longStep, note: '', code: 'x = 1', elapsed: 2, cost: 0.01 }); w.paneCell({ cell_no: 1, ok: true, peek: 'diff 0.5', elapsed: 0.1, chars: 8 });
w.paneTurnStart({ turn: 2, of: 8, seat: 'Analyst', model: 'm', chain_id: 27 }); w.paneToken('###STEP###\nDone.');
w.paneTurnEnd({ turn: 2, kind: 'report', thinking: 'Done.', elapsed: 1, cost: 0 });
w.paneRunEnd({ status: 'answered', turns: 2, of: 8, cells: 1, cost: 0.1, seconds: 3, chain_id: 27, turn_map: true });
const longChain = { chain_id: 27, thread_id: 7, parentChainId: null, queryText: 'A long step', streamOutput: $('streamOutput').innerHTML, tabContent: '', contentOutput: '', taskContents: {}, branch: null };
responses.push(longChain); show(longChain); openMap();
nodes()[0].dispatch('mouseenter');
const longFoot = { said: ($('nodeTaskContent').querySelector('.wf-said') || {}).textContent, box: nodes()[0].querySelector('.wf-node-label').textContent };
nodes()[0].dispatch('click'); nodes()[0].dispatch('mouseleave');
longFoot.stays = ($('nodeTaskContent').querySelector('.wf-said') || {}).textContent;
M.shut(); responses.pop();
check('the Analysis map\'s panel says the whole of what a turn said - every line of it, as text (0330: its first sentence, cut at 120 characters); the box keeps its short line; the panel '
  + 'keeps saying it when the box is picked and the pointer leaves it, so what does not fit can be scrolled to',
  same(longFoot, { said: longStep, box: 'This turn compares the bloc...', stays: longStep }), longFoot);

// ---- the panel (0333): from the first the box in use - the last box where none is in use (0332) -; a click picks a box, the pointer shows another until it leaves; the button, or a double click, goes there
const tagKinds = () => $('nodeTaskContent').querySelectorAll('.wf-tag').map(t => t.textContent + '/' + t.className);
const pickedNow = () => nodes().map((x, i) => (x.classList.contains('wf-node--picked') ? i + 1 : 0)).filter(Boolean).join();
show(a); openMap(); const atOpen = panel(); nodes()[5].dispatch('mouseenter'); const atHover = panel(); nodes()[5].dispatch('mouseleave');
nodes()[2].dispatch('mouseenter'); nodes()[2].dispatch('click'); nodes()[2].dispatch('mouseleave');
const picked3 = { panel: panel(), picked: pickedNow(), lit: lit(), at: B.standing(), open: drawer.style.display, kinds: tagKinds() };
nodes()[7].dispatch('mouseenter'); const over8b = panel(); nodes()[7].dispatch('mouseleave');
nodes()[6].dispatch('mouseenter'); const hinted = [panel(), tagKinds()]; nodes()[6].dispatch('mouseleave');      // the first turn of a branch: the hint's mark
const leftOver = { panel: panel(), lit: lit() };
nodes()[1].dispatch('click'); const failedKinds = tagKinds();
nodes()[2].dispatch('dblclick'); const dbl = { at: B.standing(), open: drawer.style.display };
openMap(); const backTo3 = { panel: panel(), kinds: tagKinds() }; M.shut(); B.leave();
b1.branch.hint = 'keep <b>A</b> & B apart'; openMap(); nodes()[7].dispatch('mouseenter');                // a hint that reads as markup
const hintSaid = $('nodePlotPreview').querySelectorAll('.wf-info-row').map(r => r.elements.map(e => e.textContent).join('=')).filter(r => r.startsWith('Hint=')); M.shut(); b1.branch.hint = 'keep the two blocks apart';
const said3 = 'The pooled figure stands.\n\nThis turn compares `df.mean()` by block,\nas the hint asks.';
$('nodeTaskContent').innerHTML = ''; window.WorkflowGraph.foot({ title: 'Turn 3', go: 'Go to turn 3', tags: [['In [3]', 'kernel'], ['hint', 'model'], ['not run', '']], said: said3, rows: window.WorkflowGraph.row('Hint', 'apart', 'x') });
const card = { head: $('nodeTaskContent').querySelector('.wf-head').innerHTML, ps: $('nodeTaskContent').querySelectorAll('.wf-said p').map(p => p.innerHTML), rows: $('nodePlotPreview').querySelectorAll('.wf-info-row').map(r => r.className) };
window.WorkflowGraph.foot({ title: 'Turn <3>', tags: [['<b>x</b> & y', '']] });      // a name and a tag that read as markup
const markupAsText = [$('nodeTaskContent').querySelector('.wf-title').textContent, $('nodeTaskContent').querySelector('.wf-tag').textContent];
window.WorkflowGraph.foot(); const nothing = [$('nodeTaskContent').innerHTML, $('nodePlotPreview').innerHTML];
window.WorkflowGraph.render($('workflowMapContainer'), [{ chain_id: 1, parentChainId: null, queryText: 'First' }, { chain_id: '2<i>b</i>', parentChainId: 1, queryText: 'Second' }], -1);
const noneInUse = [panel(), pickedNow()];
nodes()[0].dispatch('mouseenter'); const firstChain = panel(); nodes()[0].dispatch('mouseleave');
check('the panel (0333, on the right of the map; at its foot, 0329-0332) says from the first what the box in use is, as it says under the pointer; where no box is in use, the last box. '
  + 'A click picks a box: the panel holds it and its way is lit, the box ringed, and nothing goes anywhere; under the pointer the panel says what another box is, and the picked one again '
  + 'when the pointer leaves. Its button - or a double click on the box - goes there: back to that turn, the drawer shut; the turn gone back to, and a report on screen, are there already '
  + 'and have none. A tag is in the colour of what it says: on screen and the hint\'s mark in the analyst\'s, what a turn was in the colour of cells, a failure in red, the rest in grey. '
  + 'The name, the button, the tags: one head. What was said stands in paragraphs - a blank line parts two, a line break stays -, as text, `code` set as code; the facts under it, a row '
  + 'each, a kind of row named; a map with nothing on it, nothing. A hint, and a chain\'s id, that read as markup are text',
  atOpen === atHover && atOpen === 'Turn 6 [on screen, report] | Everything asked is established. | Follows=turn 5 | Followed by=none'
  && same(picked3, { panel: 'Turn 3 [In [3]] > Go to turn 3 | This turn pools the two blocks. | Follows=turn 2 | Followed by=3 turns | Printed=pooled 20', picked: '3', lit: '1,2,3', at: null, open: 'flex', kinds: ['In [3]/wf-tag wf-tag--kernel'] })
  && over8b === 'Turn 5 [report] > Go to turn 5 | Each block has its own figure. | Follows=turn 4 | Followed by=none | Hint=keep the two blocks apart' && same(leftOver, { panel: 'Turn 3 [In [3]] > Go to turn 3 | This turn pools the two blocks. | Follows=turn 2 | Followed by=3 turns | Printed=pooled 20', lit: '1,2,3' })
  && same(failedKinds, ['failed/wf-tag wf-tag--fail']) && same(dbl, { at: { chain: 20, turn: 3 }, open: 'none' })
  && same(backTo3, { panel: 'Turn 3 [on screen, In [3]] | This turn pools the two blocks. | Follows=turn 2 | Followed by=3 turns | Printed=pooled 20', kinds: ['on screen/wf-tag wf-tag--model', 'In [3]/wf-tag wf-tag--kernel'] })
  && same(card, { head: '<div class="wf-head-row"><h3 class="wf-title">Turn 3</h3><button type="button" class="ui-btn primary wf-go">Go to turn 3</button></div>'
                        + '<div class="wf-tags"><span class="wf-tag wf-tag--kernel">In [3]</span><span class="wf-tag wf-tag--model">hint</span><span class="wf-tag">not run</span></div>',
                  ps: ['The pooled figure stands.', 'This turn compares <code>df.mean()</code> by block,\nas the hint asks.'], rows: ['wf-info-row x'] })
  && same(hinted, ['Turn 4 [In [4], hint] > Go to turn 4 | This turn splits them. | Follows=turn 3 | Followed by=2 turns | Hint=keep the two blocks apart | Printed=apart 10', ['In [4]/wf-tag wf-tag--kernel', 'hint/wf-tag wf-tag--model']]) && same(markupAsText, ['Turn <3>', '<b>x</b> & y'])
  && same(nothing, ['', '']) && same(noneInUse, ['Chain 2 > Go to chain 2 | Second | Follows=chain 1 | Followed by=none | Id=2<i>b</i>', '2']) && same(hintSaid, ['Hint=keep <b>A</b> & B apart'])
  && firstChain === 'Chain 1 > Go to chain 1 | First | Follows=the start | Followed by=chain 2 | Id=1',
  [atOpen, atHover, picked3, over8b, hinted, leftOver, failedKinds, dbl, backTo3, card, markupAsText, nothing, noneInUse, firstChain, hintSaid]);

// ---- the arrows at the head of the Investigation tab (0329)
// a thread of its own: a first question; an analysis that went on three ways - two from its third turn, one from the first of those; and a follow-up, an analysis of one run
const NOTEBOOK = '<div class="briefing-content"><div class="nb">the notebook</div></div>';
const tabbed = (e, more, stale) => Object.assign({}, e, more || {}, { tabContent: '<div class="tab" id="tab-answer">Answer</div><div class="tab" id="tab-plan">Investigation</div>',
  contentOutput: '<div id="content-answer">the answer</div><div id="content-plan" class="tab-content">' + (stale || '') + NOTEBOOK + '</div>' });
const nbA = tabbed(a), nbB1 = tabbed(b1), nbF = tabbed(f, null, '<div class="br-top"><div class="br-ver"><b>9 of 9</b></div></div>'),
      nbB2 = tabbed(b2, { branch: { of: 20, turn: 3, hint: 'another <way> & "more"' } }, '<div class="br-top"><div class="br-ver"><b>1 of 1</b></div></div>'), nbC = tabbed(c), bare = Object.assign({}, a, { chain_id: 26, branch: { of: 20, turn: 2, hint: 'no tab' } });
responses.splice(0); responses.push(q0, nbA, nbB1, nbF, nbB2, nbC); B.leave();
const activated = []; global.activateTabInView = t => activated.push('in view: ' + t); global.activateTab = t => activated.push(t);
const head = () => { const tab = $('content-plan'), row = tab ? tab.querySelector('.br-top') : null, ver = row ? row.querySelector('.br-ver') : null;
  return { chain: currentData.chain_id, rows: tab ? tab.querySelectorAll('.br-top').length : null, first: tab ? tab.elements[0].className : null,
           from: row && row.querySelector('.label') ? row.querySelector('.label').textContent : '', said: row && row.querySelector('.br-said') ? [row.querySelector('.br-said').textContent, row.querySelector('.br-said').getAttribute('title')] : null,
           ver: ver ? ver.elements.map(x => x.tag + (x.className ? '.' + x.className : '') + '=' + x.textContent + (x.tag === 'button' ? '|' + x.getAttribute('aria-label') + '|' + x.getAttribute('title') + (x.hasAttribute('disabled') ? '|off' : '') + '|' + x.getAttribute('onclick') : '')) : null }; };
const arrow = (way, to, off) => 'button=' + (to < 0 ? '‹' : '›') + '|The branch ' + way + '|The branch ' + way + (off ? '|off' : '') + '|if (window.BranchUI) BranchUI.flip(' + to + ');';
const verOf = (said, offBefore, offAfter) => ['span.k=Branch', arrow('before', -1, offBefore), 'b=' + said, arrow('after', 1, offAfter)];
show(nbA); const atOriginal = head();
B.flip(1); const at1 = head(), act1 = activated.splice(0);
B.flip(1); const at2 = head();
B.flip(1); const at3 = head(), loadedTo = loaded.length;
B.flip(1); const atEnd = head(), loadedEnd = loaded.length - loadedTo;      // no branch after the last: nothing moves
B.flip(-1); B.flip(-1); B.flip(-1); const backAt = head();
B.flip(-1); const beforeFirst = [head().chain, loaded.length - loadedTo];
activated.splice(0); delete global.activateTabInView;
B.flip(1); const actPlain = activated.splice(0);                                 // a page without the live view's way to a tab: the tab's own
show(nbF); const single = head();                                                  // an analysis of one run, its tab kept with a row
show(q0); const noTab = head();                                                   // a chain with no Investigation tab
B.onChain(null); B.onChain(undefined);
responses.push(bare); show(nbA); B.flip(1); B.flip(1); B.flip(1); B.flip(1);       // to a branch with no Investigation tab
const toBare = [currentData.chain_id, $('content-plan'), activated.splice(0)];
responses.pop();
const tabsCss = css('tabs.css');
check('the arrows in the Investigation tab (0329): an analysis that went on more than one way has a row at the head of the tab - for a branch, the turn it went on from and its hint, whole '
  + 'under the pointer and as text; then "Branch", and between the arrows the original, or the branch by its place among them in the order they were made; an arrow with nothing beyond is '
  + 'off. An arrow brings the next branch on screen on its Investigation tab, and past the last or before the first nothing moves. The row is drawn when a chain comes on screen: one kept '
  + 'with the tab is drawn again, and gone where the analysis has one run. A chain with no Investigation tab has none, and is still gone to',
  same(atOriginal, { chain: 20, rows: 1, first: 'br-top', from: '', said: null, ver: verOf('original', true, false) })
  && same(at1, { chain: 21, rows: 1, first: 'br-top', from: 'From turn 3', said: ['keep the two blocks apart', 'keep the two blocks apart'], ver: verOf('1 of 3', false, false) }) && same(act1, ['in view: plan'])
  && same(at2, { chain: 22, rows: 1, first: 'br-top', from: 'From turn 3', said: ['another <way> & "more"', 'another <way> & "more"'], ver: verOf('2 of 3', false, false) })
  && same(at3, { chain: 23, rows: 1, first: 'br-top', from: 'From turn 4', said: ['and say which is larger', 'and say which is larger'], ver: verOf('3 of 3', false, true) })
  && same(atEnd, at3) && loadedEnd === 0 && same(backAt, atOriginal) && same(beforeFirst, [20, 3]) && same(actPlain, ['plan'])
  && same(single, { chain: 30, rows: 0, first: 'briefing-content', from: '', said: null, ver: null }) && same(noTab, { chain: 10, rows: null, first: null, from: '', said: null, ver: null })
  && same(toBare, [26, null, ['plan', 'plan', 'plan']]),
  [atOriginal, at1, at2, at3, atEnd, loadedEnd, backAt, beforeFirst, actPlain, single, noTab, toBare]);
check('the stylesheet: the row and its arrows are the Brief tab\'s own - each rule of the Brief\'s head row and of its stepper names the Investigation tab\'s beside it, so the two cannot '
  + 'differ; the row sets its own type, which the Brief\'s took from its brief; the hint is the part that gives way, on one line',
  ['#content-brief .ar-top, #content-plan .br-top { display: flex; align-items: center; flex-wrap: wrap; gap: 4px 12px; margin-bottom: 8px; font-size: 13.5px; line-height: 1.55; color: var(--text-primary); }',
   '#content-brief .ar-top .label, #content-plan .br-top .label {', '#content-brief .ar-ver, #content-plan .br-ver {', '#content-brief .ar-ver .k, #content-plan .br-ver .k {', '#content-brief .ar-ver b, #content-plan .br-ver b {',
   '#content-brief .ar-ver button, #content-plan .br-ver button {', '#content-brief .ar-ver button:not(:disabled):hover, #content-plan .br-ver button:not(:disabled):hover {',
   '#content-brief .ar-ver button:disabled, #content-plan .br-ver button:disabled {', '#content-plan .br-top { flex-wrap: nowrap; }', '#content-plan .br-top .label, #content-plan .br-top .br-ver { flex-shrink: 0; }',
   '#content-plan .br-top .br-said { min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;'].every(r => tabsCss.includes(r))
  && !/#content-brief \.ar-(top|ver)[^,{]*\{/.test(tabsCss.replace('#content-brief .ar-ver .ar-map {', '')) && !/\n#content-plan \.br-ver[^,{]*\{/.test(tabsCss)
  && js('ui-controls.js').includes('window.BranchUI.onChain(responses[currentResponseIndex])'));

let fails = 0; for (const [n, ok, d] of results) { console.log((ok ? '  ok   ' : '  FAIL ') + n + (ok ? '' : '  <- ' + JSON.stringify(d === undefined ? '' : d).slice(0, 1500))); if (!ok) fails++; }
console.log(`\n${results.length - fails} passed, ${fails} failed`); process.exit(fails ? 1 : 0);
