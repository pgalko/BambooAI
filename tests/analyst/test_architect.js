// The Pathfinder on the page (docs/ARCHITECT_DESIGN.md §2.6, §2.8, §2.9, §2.11, §2.12; 2026-11-15): architect.js. Its pure
// parts - the brief with one line changed, the Brief tab's markup in each state, the conversation's, the report's part
// "Against the brief" taken out of the answer for the run's Brief tab (0312), the Workflow map's mark - and the module
// driven on the mini DOM with a scripted server: a
// typed question opens its brief and the Pathfinder takes its first turn, the coach answers with a click or in words, a
// line is changed where it stands and kept as a version, the steps of the conversation are gone through - with the
// arrows, and on their map, where a conversation that branched shows every way it went (0316) - the analysis is
// started in the same chain, the composer is the conversation's while a brief not yet run is on screen; the figures
// of a brief as grey windows (0311), and their drafts drawn with a Plotly that keeps what it is asked for (0310).
// Then the page's hooks, read from the source.
// Run: node tests/analyst/test_architect.js
'use strict';
const fs = require('fs'), path = require('path');
const { makeDocument, fragment } = require(path.join(__dirname, 'minidom.js'));
const doc = makeDocument(); global.document = doc;
const calls = []; let answers = {};
// the scripted server: an answer is [status, body] - the body an object, or the text of a stream - 'down', or a promise of one
global.window = { authService: { fetch: async (url, opts) => { const body = opts && opts.body ? JSON.parse(opts.body) : null; calls.push([url, body]);
  const a = await (typeof answers[url] === 'function' ? answers[url](body) : answers[url]);
  if (a === 'down') throw new Error('offline');
  if (a && a.body) return a;                                  // a response whose body arrives as a stream
  const [status, json] = a || [200, {}];
  return { ok: status < 400, status, json: async () => json, text: async () => (typeof json === 'string' ? json : JSON.stringify(json)) }; } } };
const store = {}; global.sessionStorage = { getItem: k => (k in store ? store[k] : null), setItem: (k, v) => { store[k] = String(v); } };
const toasts = []; global.showSystemMessage = t => toasts.push(t);
// Plotly, as far as the module leans on it: what it is asked to draw, and where, is kept; the place then holds a drawing
const plotted = []; global.Plotly = { newPlot: (place, data, layout, config) => { plotted.push({ key: place.getAttribute('data-key'), data, layout, config }); place.innerHTML += '<svg class="main-svg"></svg>'; return Promise.resolve(); } };
// the composer's hold, as routines.js keeps it: the reason in the placeholder, the composer's own words kept beside it
const locks = []; global.composerLock = reason => { locks.push(['lock', reason]); const q = doc.getElementById('queryInput');
  if (q.getAttribute('data-placeholder') == null) q.setAttribute('data-placeholder', q.placeholder || ''); q.placeholder = reason; q.disabled = true; doc.getElementById('submitQuery').disabled = true; };
global.composerUnlock = () => { locks.push(['unlock']); const q = doc.getElementById('queryInput'), was = q.getAttribute('data-placeholder');
  if (was != null) { q.placeholder = was; q.removeAttribute('data-placeholder'); } q.disabled = false; doc.getElementById('submitQuery').disabled = false; };
global.responses = []; global.currentResponseIndex = -1; global.currentData = {}; global.queryRunning = false;
const host = doc.createElement('div'); doc.body.appendChild(host);
host.innerHTML = '<button id="railMapButton"></button><button id="architectSwitch" class="ar-switch" aria-pressed="false"></button><textarea id="queryInput"></textarea><button id="submitQuery"></button>' +
  '<div id="streamOutput"></div><div id="tabContainer"></div><div id="contentOutput"></div>';
const $ = id => doc.getElementById(id);
// the maps drawer - index.html's own -, its switch (maps.js) and the drawing its maps share (workflowGraph.js) on the harness's dagre
const drawerHost = doc.createElement('div'); doc.body.appendChild(drawerHost);
drawerHost.innerHTML = fragment(fs.readFileSync(path.join(__dirname, '..', '..', 'web_app', 'templates', 'index.html'), 'utf8'), 'workflowMapModal');
$('workflowMapModal').style.display = 'none';
doc.createElementNS = (ns, tag) => doc.createElement(tag);      // the drawing asks for SVG elements: here they are elements like any other
// what the Workflow map's own boxes ask of the page (content-rendering.js): what a chain was asked, and no plot
global.extractTaskFromResponse = r => ({ task: '', originalQuestion: r.queryText }); global.extractPlotDataFromResponse = () => null;
$('queryInput').placeholder = 'Enter your query here';      // the mini DOM keeps properties apart from attributes
// the page's own parts, as far as the module leans on them
global.loadResponseContent = r => { $('tabContainer').innerHTML = r.tabContent || ''; $('contentOutput').innerHTML = r.contentOutput || ''; $('streamOutput').innerHTML = r.streamOutput || '';
  currentData.chain_id = r.chain_id; currentData.thread_id = r.thread_id; window.ArchitectUI.restore(r); };
global.updateNavigationButtons = () => { window.ArchitectUI.onChain(responses[currentResponseIndex]); window.MapsUI.follow(); };
const submitted = []; global.handleQuerySubmit = o => submitted.push(o);
const tabs = []; global.createOrUpdateTab = (type, html) => tabs.push([type, html]);
const rows = []; global.paneAppend = html => rows.push(html);
const reverted = []; global.revertLiveChain = e => { reverted.push(e); e.status = 'framing'; };

require(path.join(__dirname, '..', '..', 'tools', 'fixtures', 'dagre_stub.js')); global.dagre = window.dagre;      // window.dagre: the harness's layered stand-in
require(path.join(__dirname, '..', '..', 'web_app', 'static', 'js', 'workflowGraph.js'));
require(path.join(__dirname, '..', '..', 'web_app', 'static', 'js', 'architect.js'));
require(path.join(__dirname, '..', '..', 'web_app', 'static', 'js', 'maps.js'));
// the drawer's other two levels, as far as its switch asks: the thread's chains, counted as they stand, and an analysis with no turns to go back to
global.workflowMap = () => ({ n: responses.length, said: responses.length + ' chains', off: '', draw() { $('workflowMapContainer').innerHTML = '<div class="thread">the thread\'s chains</div>'; } });
window.BranchUI = { place: () => ({ i: currentResponseIndex + 1, n: responses.length }), map: n => ({ n: 0, said: '', off: 'Chain ' + n + ' has no turns to go back to', draw() {} }) };
window.MapsUI.initialize();
const A = window.ArchitectUI, b = A.build;
const results = []; const check = (n, c, d) => results.push([n, !!c, d]);
const el = html => { const d = doc.createElement('div'); d.innerHTML = html; return d; };
function liveBody() {
  const queue = []; let waiting = null;
  const push = part => { if (waiting) { const w = waiting; waiting = null; w(part); } else queue.push(part); };
  const given = part => (part.cut ? Promise.reject(new Error('the stream was cut')) : part);
  return { ok: true, status: 200, body: { getReader: () => ({ read: () => (queue.length ? Promise.resolve(queue.shift()) : new Promise(res => { waiting = res; })).then(given) }) },
           send: text => push({ value: Buffer.from(text, 'utf8'), done: false }), end: () => push({ value: undefined, done: true }), cut: () => push({ cut: true }) };
}
const tick = async () => { for (let i = 0; i < 6; i++) await new Promise(r => setImmediate(r)); };
const same = (x, y) => JSON.stringify(x) === JSON.stringify(y);

// ------------------------------------------------------------ the brief with one line changed
const BASE = { question: 'Is B above A?', decision: 'keep one arm', rests_on: [{ text: 'B looked better', source: 'person', mark: 'holds', note: 'seen in 9 of 12' }, { text: 'a count from the data', source: 'data', mark: 'holds' }],
               also_check: [{ text: 'the two halves differ', shows: 'a gap in one half only' }], fixed: { measure: 'x' } };
const before = JSON.stringify(BASE);
check('a part is set, changed and cleared: the text on one line, the part named as changed; clearing removes it; nothing changing gives null; the input is never altered',
  same(A.apply(BASE, 'thinks', '  B is \n better  '), { brief: Object.assign({}, BASE, { thinks: 'B is better' }), changed: ['thinks'] })
  && A.apply(BASE, 'decision', 'keep one arm ') === null && !('decision' in A.apply(BASE, 'decision', '  ').brief) && same(A.apply(BASE, 'decision', '').changed, ['decision'])
  && JSON.stringify(BASE) === before, A.apply(BASE, 'thinks', '  B is \n better  '));
check('the question can be changed, never emptied; a line is cut at 600 characters; a part the brief does not have is refused',
  A.apply(BASE, 'question', 'Is B above A, on x?').brief.question === 'Is B above A, on x?' && A.apply(BASE, 'question', ' ') === null
  && A.apply(BASE, 'expects', 'y'.repeat(700)).brief.expects.length === 600 && A.apply(BASE, 'verdict', 'x') === null && A.apply(BASE, 'fixed.colour', 'x') === null);
const LONGQ = 'Is B above A?\nWhat I saw: B led in 3 of 4.\n' + 'z'.repeat(800);
check('the question is the coach\'s words, not a line of the brief: its lines and its length are kept (to 4,000 characters); a change to another part leaves it as it is; the same question again changes nothing',
  A.apply(BASE, 'question', '  ' + LONGQ + ' ').brief.question === LONGQ && A.apply(BASE, 'question', 'q'.repeat(5000)).brief.question.length === 4000
  && A.apply({ question: LONGQ }, 'decision', 'keep one arm').brief.question === LONGQ && A.apply({ question: LONGQ }, 'question', LONGQ + '\n') === null);
const added = A.apply(BASE, 'rests_on.+', 'a third thing');
check('a line is added to a list as the coach\'s own, the new line named as changed; nothing typed adds nothing; the lists stop at the design\'s counts (four anchors, two rivals)',
  same(added.brief.rests_on[2], { text: 'a third thing', source: 'person', mark: '' }) && same(added.changed, ['rests_on.2']) && A.apply(BASE, 'rests_on.+', '  ') === null
  && A.apply({ rests_on: [1, 2, 3, 4].map(i => ({ text: 't' + i })) }, 'rests_on.+', 'a fifth') === null
  && same(A.apply(BASE, 'also_check.+', 'luck').brief.also_check[1], { text: 'luck' }) && A.apply({ also_check: [{ text: 'a' }, { text: 'b' }] }, 'also_check.+', 'c') === null
  && same(A.apply({}, 'also_check.+', 'luck'), { brief: { also_check: [{ text: 'luck' }] }, changed: ['also_check.0'] }), added);
const changed = A.apply(BASE, 'rests_on.0', 'B looked better last year');
check('a line the coach changes is their own and loses its mark and note until it is checked again (§2.6); a rival changed loses what it would show',
  same(changed.brief.rests_on[0], { text: 'B looked better last year', source: 'person', mark: '' }) && same(changed.changed, ['rests_on.0'])
  && same(A.apply(BASE, 'also_check.0', 'the halves differ').brief.also_check[0], { text: 'the halves differ' }), changed);
const dropped = A.apply(BASE, 'rests_on.1', '');
check('a fact from a lookup cannot be changed, only left out (§2.6); a line left out names the list and its index; the last line out removes the list',
  A.apply(BASE, 'rests_on.1', 'another count') === null && dropped.brief.rests_on.length === 1 && dropped.removed === 1 && same(dropped.changed, ['rests_on'])
  && !('also_check' in A.apply(BASE, 'also_check.0', '').brief) && A.apply(BASE, 'rests_on.7', 'x') === null, dropped);
const ITS = { text: 'the arms differ in size', shows: 'the gap narrows with size held fixed', source: 'architect', accepted: false };
const WITH = Object.assign({}, BASE, { also_check: [BASE.also_check[0], ITS] }), withBefore = JSON.stringify(WITH);
check('a proposal of the Pathfinder\'s is accepted with a tick, and no longer with another: the line named as changed, nothing else touched; only such a line can be ticked - not the coach\'s own, not a line of '
  + 'another part, not one that is not there; the input is never altered',
  same(A.tick(WITH, 'also_check.1'), { brief: Object.assign({}, WITH, { also_check: [BASE.also_check[0], Object.assign({}, ITS, { accepted: true })] }), changed: ['also_check.1'] })
  && A.tick(A.tick(WITH, 'also_check.1').brief, 'also_check.1').brief.also_check[1].accepted === false
  && A.tick(WITH, 'also_check.0') === null && A.tick(WITH, 'also_check.2') === null && A.tick({ rests_on: [{ text: 'x', source: 'architect' }] }, 'rests_on.0') === null
  && A.tick({}, 'also_check.0') === null && A.tick(null, 'also_check.0') === null
  && JSON.stringify(WITH) === withBefore, A.tick(WITH, 'also_check.1'));
check('a proposal the coach rewrites is their own line: no longer the Pathfinder\'s, with nothing to tick and nothing it would show; left out, it goes like any line',
  same(A.apply(WITH, 'also_check.1', 'the arms differ in age').brief.also_check[1], { text: 'the arms differ in age' }) && same(A.apply(WITH, 'also_check.1', '').brief.also_check, [BASE.also_check[0]])
  && A.apply(WITH, 'also_check.+', 'a third') === null);
check('what is fixed: a part set or cleared by its name; the last one cleared removes the group',
  same(A.apply(BASE, 'fixed.period', 'the first half').brief.fixed, { measure: 'x', period: 'the first half' }) && same(A.apply(BASE, 'fixed.period', 'the first half').changed, ['fixed.period'])
  && !('fixed' in A.apply(BASE, 'fixed.measure', '').brief) && A.apply(BASE, 'fixed.measure', ' x ') === null);

// ------------------------------------------------------------ the Brief tab
const F1 = { versions: [{ n: 1, by: 'person', changed: [], brief: { question: 'Is B above A?' } }] };
const t1 = el(b.brief(F1, { chain: 71, state: 'framing' })), root1 = t1.querySelector('.ar-brief');
const h3s = root => root.querySelectorAll('h3').map(h => h.textContent).join('|');
const KINDS = 'decision=What it is for|thinks=What you think|rests_on.+=Why you think so|expects=What you expect to see|would_change=What would change your mind|also_check.+=Another explanation to test|' +
  'fixed.comparison=What is compared|fixed.measure=Measured by|fixed.period=Period';
const kindsOf = root => root.querySelectorAll('.ar-kinds [data-ar="add"]').map(x => x.getAttribute('data-path') + '=' + x.textContent).join('|');
check('a brief that holds only the question (0308): on top what the Analyst will be asked - said in those words - with the step beside it under its own name: "Step", "1 of 1", both arrows off, no button to a map - the framing was kept before steps (0316) - and '
  + 'nothing said of who made it; the question in its box with its pencil, and under it one line that says this is what the Analyst gets. No part stands: a part shows only when it holds '
  + 'something. One control adds a part, its list shut; Start analysis at the foot. Nothing says what is always tested - a brief with nothing in it is no brief - and no button has the saved '
  + 'analyses read, whatever the framing says of them',
  root1.elements[0].className === 'ar-top' && root1.querySelector('.ar-top .label').textContent === 'What the Analyst will be asked'
  && root1.querySelector('.ar-top .ar-ver .k').textContent === 'Step' && !root1.querySelector('[data-ar="map"]') && root1.querySelector('.ar-ver b').textContent === '1 of 1' && !root1.querySelector('.why') && !root1.querySelector('.step')
  && root1.querySelectorAll('.ar-ver [data-ar="step"]').map(x => x.getAttribute('data-step') + x.hasAttribute('disabled') + x.getAttribute('aria-label')).join() === '-1trueThe step before,1trueThe step after'
  && root1.elements[1].tag === 'h1' && root1.elements[2].className === 'ar-gets' && root1.elements[2].textContent === 'This is what the Analyst gets. Change any line before you start.'
  && root1.querySelector('h1.ar-line.ar-q .tx').textContent === 'Is B above A?' && root1.querySelector('h1 .pen[data-ar="edit"]') && root1.querySelector('h1').getAttribute('data-path') === 'question'
  && h3s(root1) === '' && root1.querySelectorAll('.ar-line').length === 1 && !/\+ Add.*\+ Add/.test(t1.textContent) && !/not said|left to/.test(t1.textContent)
  && root1.elements[3].className === 'ar-more' && root1.querySelector('.ar-more .ar-add[data-ar="more"]').textContent === '+ Add' && root1.querySelector('.ar-add').getAttribute('aria-expanded') === 'false'
  && !root1.querySelector('.ar-kinds') && !root1.hasAttribute('data-adds') && !root1.querySelector('.ar-always') && !root1.querySelector('.ar-memory')
  && root1.elements[4].className === 'ar-foot' && root1.querySelector('.ar-foot .ui-btn.primary[data-ar="start"]').textContent === 'Start analysis'
  && [0, 3].every(n => !el(b.brief(Object.assign({ saved: n }, F1), { chain: 71, state: 'framing' })).querySelector('[data-ar="look"]')), t1.innerHTML);
const opened1 = el(b.brief(F1, { chain: 71, state: 'framing', adds: true })).querySelector('.ar-brief');
const adding1 = el(b.brief(F1, { chain: 71, state: 'framing', adding: 'thinks' })).querySelector('.ar-brief');
const addingList = el(b.brief(F1, { chain: 71, state: 'framing', adding: 'rests_on.+' })).querySelector('.ar-brief'), addingFixed = el(b.brief(F1, { chain: 71, state: 'framing', adding: 'fixed.period' })).querySelector('.ar-brief');
check('+ Add (0308): opened, it lists the parts the brief does not hold, in the brief\'s order, each under the name its place has - the three that are fixed before a run by their own names - and the tab '
  + 'remembers that the list is open. A part being added stands in its place under its heading, with nothing in it and no pencil: the line the coach types in. Nothing is offered that a click '
  + 'could not add, and nothing reads "+ Add" but the one control',
  kindsOf(opened1) === KINDS && opened1.getAttribute('data-adds') === '1' && opened1.querySelector('.ar-add').getAttribute('aria-expanded') === 'true' && opened1.querySelector('.ar-more .ar-kinds')
  && h3s(opened1) === '' && h3s(adding1) === 'What you think' && adding1.querySelector('.ar-line[data-path="thinks"] .tx').textContent === '' && !adding1.querySelector('.ar-line[data-path="thinks"] .pen')
  && !adding1.querySelector('.ar-kinds') && h3s(addingList) === 'Why you think so' && addingList.querySelector('.ar-line[data-path="rests_on.+"]') && h3s(addingFixed) === 'Period'
  && addingFixed.querySelector('.ar-line[data-path="fixed.period"]') && opened1.querySelectorAll('.ar-kinds button').every(x => x.getAttribute('type') === 'button')
  && (opened1.textContent.match(/\+ Add/g) || []).length === 1, opened1.outerHTML);
check('the tab carries what it needs to be stepped through later: the chain, the state, the step shown and the framing whole',
  root1.getAttribute('data-chain') === '71' && root1.getAttribute('data-state') === 'framing' && root1.getAttribute('data-shown') === '1' && same(JSON.parse(root1.getAttribute('data-framing')), F1));
const BUILT = [{ thread: '7', run: '8', when: '2026-02-20', question: 'Was B above A before?', passage: 'B led by 3.', accepted: true },
               { thread: '7', run: '8', when: '2026-02-20', question: 'Was B above A before?', passage: 'And by 2 later.', accepted: true },
               { thread: '7', run: '9', when: '2026-03-01', question: 'Left unticked by a brief of 0307', passage: 'p', accepted: false }];
const FULL = Object.assign({}, BASE, { thinks: 'B is better', expects: 'B above A by 2', would_change: 'a gap under 1',
  rests_on: BASE.rests_on.concat([{ text: 'an earlier finding', source: 'result', mark: 'cannot be checked' }, { text: 'a proposal', source: 'architect', mark: 'does not hold', note: 'A led in 7 of 12' }]),
  also_check: BASE.also_check.concat([{ text: 'luck' }]), saved: BUILT, set_aside: ['the weather'] });
const F3 = { versions: [F1.versions[0], { n: 2, by: 'person', changed: ['decision'], brief: { question: 'Is B above A?', decision: 'keep one arm' } }, { n: 3, by: 'person', changed: ['rests_on.0', 'fixed.measure', 'question', 'saved.1'], brief: FULL }] };
const t3 = el(b.brief(F3, { chain: 71, state: 'framing' })), root3 = t3.querySelector('.ar-brief');
const lineOf = (r, p) => r.querySelector('.ar-line[data-path="' + p + '"]');
check('a filled brief shows its last version, "3 of 3", the arrow back live; each part that holds something stands under its plain name, in the brief\'s order - what is fixed before a run under the name '
  + 'of each part, with no heading over them; a line has its pencil and, in a list, its cross; the lines changed in this version carry the bar; nothing leads a line in',
  root3.querySelector('.ar-ver b').textContent === '3 of 3' && !root3.querySelector('.why')
  && !root3.querySelector('.ar-ver [data-step="-1"]').hasAttribute('disabled') && root3.querySelector('.ar-ver [data-step="1"]').hasAttribute('disabled')
  && h3s(root3) === 'What it is for|What you think|Why you think so|What you expect to see|What would change your mind|Other explanations to test|Measured by|Builds on|Set aside'
  && lineOf(root3, 'decision').querySelector('.tx').textContent === 'keep one arm' && !lineOf(root3, 'decision').querySelector('.tx').getAttribute('data-ar')
  && lineOf(root3, 'decision').querySelector('.pen[data-ar="edit"]') && !lineOf(root3, 'decision').querySelector('.drop') && lineOf(root3, 'would_change').querySelector('.tx').textContent === 'a gap under 1'
  && lineOf(root3, 'rests_on.0').querySelector('.drop[data-ar="drop"]') && lineOf(root3, 'also_check.1').querySelector('.drop') && lineOf(root3, 'fixed.measure').querySelector('.tx').textContent === 'x'
  && !root3.querySelector('.pre') && !root3.querySelector('.ar-grid') && !root3.querySelector('.ar-chips') && !root3.querySelector('.adds')
  && root3.querySelectorAll('.ar-line.changed').map(l => l.getAttribute('data-path') || l.className).join() === 'question,rests_on.0,fixed.measure,ar-line ar-built changed', t3.innerHTML);
check('what a line rests on shows: its mark and the fact beside it (red when it does not hold), who brought it in when it was not the coach; a fact from a lookup has no pencil, only the cross',
  lineOf(root3, 'rests_on.0').querySelector('.mk.ok').textContent === '✓' && lineOf(root3, 'rests_on.0').querySelector('.fact').textContent === 'seen in 9 of 12' && !lineOf(root3, 'rests_on.0').querySelector('.src')
  && lineOf(root3, 'rests_on.1').querySelector('.src').textContent === 'data' && !lineOf(root3, 'rests_on.1').querySelector('.pen') && lineOf(root3, 'rests_on.1').querySelector('.drop')
  && lineOf(root3, 'rests_on.2').querySelector('.mk.q').textContent === '?' && lineOf(root3, 'rests_on.2').querySelector('.src').textContent === 'last result' && lineOf(root3, 'rests_on.2').querySelector('.pen')
  && lineOf(root3, 'rests_on.3').querySelector('.mk.no').textContent === '✕' && lineOf(root3, 'rests_on.3').querySelector('.fact.no').textContent === 'A led in 7 of 12' && lineOf(root3, 'rests_on.3').querySelector('.src.ar').textContent === 'Pathfinder'
  && lineOf(root3, 'also_check.0').querySelector('.fact').textContent === 'a gap in one half only', t3.innerHTML);
const built3 = root3.querySelectorAll('.ar-built');
check('the saved analyses a brief builds on (0308): one line to an analysis, however many of its passages the brief holds - its day as a person writes it and what was asked then - with View, which '
  + 'names the analysis, and a cross to build on it no longer; a passage the coach never accepted (a brief of 0307) is not one built on. No box to tick, no tag, nothing of where a passage stood. '
  + 'What was set aside is shown as it is. Under the parts one line says what is always tested on data - where the brief gives the Analyst something and data is loaded - and + Add offers what is '
  + 'still not there: no more lines to a list at the design\'s count',
  built3.length === 1 && built3[0].querySelector('.tx').textContent === '20 Feb 2026 · Was B above A before?' && built3[0].className === 'ar-line ar-built changed'
  && built3[0].querySelector('.ar-open[data-ar="open"]').textContent === 'View' && built3[0].querySelector('.ar-open').getAttribute('data-thread') === '7' && built3[0].querySelector('.ar-open').getAttribute('data-run') === '8'
  && built3[0].querySelector('.drop[data-ar="unbuild"]').getAttribute('data-id') === '7/8' && built3[0].querySelector('.drop').getAttribute('title') === 'Leave it out'
  && !root3.querySelector('.tick[data-ar="tick"]') && !root3.querySelector('.src.mem') && !/Left unticked|picked|report ·/.test(t3.textContent) && !/Open/.test(t3.textContent)
  && root3.querySelectorAll('h3').slice(-1)[0].textContent === 'Set aside' && !t3.querySelectorAll('.ar-line').slice(-1)[0].querySelector('[data-ar]') && t3.querySelectorAll('.ar-line').slice(-1)[0].textContent === 'the weather'
  && root3.querySelector('.ar-always').textContent === 'Always tested on data: chance, measurement error, how the cases were chosen.'
  && !el(b.brief(Object.assign({ data: false }, F3), { chain: 71, state: 'framing' })).querySelector('.ar-always') && el(b.brief(Object.assign({ data: true }, F3), { chain: 71, state: 'framing' })).querySelector('.ar-always')
  && !el(b.brief({ versions: [{ n: 1, by: 'person', changed: [], brief: { question: 'q', also_check: [ITS] } }] }, { chain: 71, state: 'framing' })).querySelector('.ar-always')      // a proposal not accepted is nothing the Analyst gets
  && el(b.brief({ versions: [{ n: 1, by: 'person', changed: [], brief: { question: 'q', saved: BUILT.slice(0, 1) } }] }, { chain: 71, state: 'framing' })).querySelector('.ar-always')
  && kindsOf(el(b.brief(F3, { chain: 71, state: 'framing', adds: true }))) === 'fixed.comparison=What is compared|fixed.period=Period'
  && !el(b.brief({ versions: [{ n: 1, by: 'person', changed: [], brief: Object.assign({}, FULL, { fixed: { comparison: 'a', measure: 'b', period: 'c' } }) }] }, { chain: 71, state: 'framing' })).querySelector('.ar-more'),
  t3.innerHTML);
const FP = { versions: [F1.versions[0], { n: 2, by: 'architect', why: 'check', changed: ['also_check.1'], brief: Object.assign({}, FULL, { also_check: [BASE.also_check[0], ITS] }) },
                        { n: 3, by: 'person', changed: ['also_check.1'], brief: Object.assign({}, FULL, { also_check: [BASE.also_check[0], Object.assign({}, ITS, { accepted: true })] }) }] };
const proposed = lineOf(el(b.brief(FP, { chain: 71, state: 'framing', shown: 2 })).querySelector('.ar-brief'), 'also_check.1');
const accepted = lineOf(el(b.brief(FP, { chain: 71, state: 'framing' })).querySelector('.ar-brief'), 'also_check.1'), mineToo = lineOf(el(b.brief(FP, { chain: 71, state: 'framing' })).querySelector('.ar-brief'), 'also_check.0');
const acceptedRun = lineOf(el(b.brief(FP, { chain: 71, state: 'run' })).querySelector('.ar-brief'), 'also_check.1');
check('what the Pathfinder proposed has a box to tick, its mark as the one who brought it in and, under it, what it would show: empty until the coach accepts it, ticked after; the coach\'s own lines have no box. '
  + 'It can be ticked, changed and left out in whichever version is on screen (0308); once the analysis has started the box only shows',
  accepted.querySelector('button.tick.on[data-ar="tick"]') && accepted.querySelector('.tick').getAttribute('role') === 'checkbox' && accepted.querySelector('.tick').getAttribute('aria-checked') === 'true'
  && accepted.querySelector('.tick').getAttribute('title') === 'Have the analysis test it' && accepted.querySelector('.tick svg') && accepted.querySelector('.src.ar').textContent === 'Pathfinder'
  && accepted.querySelector('.fact').textContent === 'the gap narrows with size held fixed' && accepted.querySelector('.pen[data-ar="edit"]') && accepted.querySelector('.drop[data-ar="drop"]')
  && !mineToo.querySelector('.tick') && !mineToo.querySelector('.src')
  && proposed.querySelector('button.tick[data-ar="tick"]') && !proposed.querySelector('.tick.on') && proposed.querySelector('.tick').getAttribute('aria-checked') === 'false' && !proposed.querySelector('.tick svg')
  && !proposed.querySelector('.tick').hasAttribute('disabled') && proposed.querySelector('.pen') && proposed.className === 'ar-line changed'
  && acceptedRun.querySelector('button.tick.on') && acceptedRun.querySelector('.tick').hasAttribute('disabled') && !acceptedRun.querySelector('[data-ar]'), accepted.outerHTML + proposed.outerHTML);
const old = el(b.brief(F3, { chain: 71, state: 'framing', shown: 2 })).querySelector('.ar-brief');
const ran = el(b.brief(F3, { chain: 71, state: 'run' })).querySelector('.ar-brief'), ranAt = el(b.brief(Object.assign({ at: 2 }, F3), { chain: 71, state: 'run' })).querySelector('.ar-brief');
check('an earlier step on screen (0316; a version, 0308) is the brief as it stood then, and can be gone on from: "2 of 3", both arrows live, the parts it held and no other, each with its pencil, the one '
  + 'control that adds a part - and Start analysis names the step, so that the coach sees where the analysis will start from. A framing that says which version is in use shows its step, and names it '
  + 'on the button too',
  old.querySelector('.ar-ver b').textContent === '2 of 3' && old.getAttribute('data-shown') === '2' && !old.querySelectorAll('[data-ar="step"]').some(x => x.hasAttribute('disabled'))
  && h3s(old) === 'What it is for' && !lineOf(old, 'thinks') && lineOf(old, 'decision').className === 'ar-line changed' && lineOf(old, 'decision').querySelector('.pen[data-ar="edit"]') && old.querySelector('h1 .pen')
  && old.querySelector('.ar-gets') && old.querySelector('.ar-more [data-ar="more"]') && old.querySelector('.ar-foot [data-ar="start"]').textContent === 'Start analysis from step 2'
  && root3.querySelector('.ar-foot [data-ar="start"]').textContent === 'Start analysis'
  && el(b.brief(Object.assign({ at: 1 }, F3), { chain: 71, state: 'framing' })).querySelector('.ar-ver b').textContent === '1 of 3'
  && el(b.brief(Object.assign({ at: 1 }, F3), { chain: 71, state: 'framing' })).querySelector('[data-ar="start"]').textContent === 'Start analysis from step 1'
  && el(b.brief(Object.assign({ at: 1 }, F3), { chain: 71, state: 'framing', shown: 3 })).querySelector('[data-ar="start"]').textContent === 'Start analysis'
  && [0, 4, '2', true, null].every(at => el(b.brief(Object.assign({ at }, F3), { chain: 71, state: 'framing' })).querySelector('.ar-ver b').textContent === '3 of 3'), old.outerHTML);
check('the brief of a run that has started is read, not changed: what the Analyst got, at the version it started with - the last, or the one the framing names - under the plain names, with no pencil, no '
  + 'cross, no place to add a part, no Start analysis and nothing that says what the Analyst gets; its versions can still be stepped through, and View still shows a saved analysis it built on',
  ran.getAttribute('data-state') === 'run' && ran.querySelector('.ar-ver b').textContent === '3 of 3' && ran.querySelectorAll('[data-ar]').map(x => x.getAttribute('data-ar')).join() === 'step,step,open'
  && !ran.querySelector('.ar-foot') && !lineOf(ran, 'fixed.period') && !ran.querySelector('.ar-more') && !ran.querySelector('.ar-gets') && !ran.querySelector('.pen') && !ran.querySelector('.drop')
  && lineOf(ran, 'fixed.measure').querySelector('.tx').textContent === 'x' && ran.querySelector('.ar-always')
  && h3s(ran) === 'What it is for|What you think|Why you think so|What you expect to see|What would change your mind|Other explanations to test|Measured by|Builds on|Set aside'
  && ranAt.querySelector('.ar-ver b').textContent === '2 of 3' && h3s(ranAt) === 'What it is for' && ranAt.querySelectorAll('[data-ar]').map(x => x.getAttribute('data-ar')).join() === 'step,step', ran.outerHTML);
const READ1 = { who: 'memory', found: [{ id: '7/8', when: '2026-02-20', question: 'Was B above A before?', where: 'report', quote: 'B led by 3.', note: 'The same comparison, a season earlier.' },
                                       { id: '7/9', when: '2026-03-01', question: 'And <C>?', where: 'cell 2', quote: 'gap = b - a', note: '' },
                                       { id: '7/8', when: '2026-02-20', question: 'Was B above A before?', where: 'cell 4', quote: 'And by 2 later.', note: 'Later in the season.' }], of: 12, read: 9, failed: '', secs: 3 };
const READ2 = { who: 'memory', found: [{ id: '7/8', when: '2026-02-20', question: 'Was B above A before?', where: 'report', quote: 'B led by 3.', note: 'Found again.' },
                                       { id: '5/6', when: '2025-12-31', question: 'An older one', where: 'report', quote: 'Nothing in it.', note: '' }], of: 12, read: 12, failed: '', secs: 2 };
const FMEM = Object.assign({}, F3, { turns: [{ who: 'architect', text: 'Looking.', v: 1 }, READ1, { who: 'person', text: 'And further back?' }, { who: 'memory', found: [], failed: 'The person skipped it.' }, READ2] });
const mem = el(b.brief(FMEM, { chain: 71, state: 'framing' })).querySelector('.ar-memory'), its = mem.querySelectorAll('.it');
check('what the readings of the saved analyses found stands under the brief, to read (0308): its own heading, and a line that says the Analyst gets only what the coach builds on; then an analysis '
  + 'to a block, in the order they were found across every reading - its day and what was asked, as text; View; its passages, each once, with the reader\'s note under it; and a mark on the one '
  + 'the brief builds on. Nothing in it can be ticked or changed. It stands before Start analysis and after the control that adds a part; a brief the readings found nothing for has none, a '
  + 'reading that was not made adds nothing, and the brief of a run that has started shows what the Analyst got and no more',
  mem.elements[0].tag === 'h3' && mem.elements[0].textContent === 'Found in your saved analyses' && mem.querySelector('.note').textContent === 'For you to read. The Analyst gets only what you build on.'
  && its.map(i => i.querySelector('.q').textContent).join('|') === '20 Feb 2026 · Was B above A before?|1 Mar 2026 · And <C>?|31 Dec 2025 · An older one'
  && its[0].querySelectorAll('.qt').map(x => x.textContent).join('|') === 'B led by 3.|And by 2 later.' && its[0].querySelectorAll('.why').map(x => x.textContent).join('|') === 'The same comparison, a season earlier.|Later in the season.'
  && !its[1].querySelector('.why') && its[1].querySelector('.qt').textContent === 'gap = b - a' && /And &lt;C&gt;\?/.test(its[1].innerHTML)
  && its.map(i => i.querySelector('.ar-open[data-ar="open"]').getAttribute('data-thread') + '/' + i.querySelector('.ar-open').getAttribute('data-run') + i.querySelector('.ar-open').textContent).join() === '7/8View,7/9View,5/6View'
  && its.map(i => (i.querySelector('.tag') || {}).textContent || '').join('|') === 'built on||' && mem.querySelectorAll('[data-ar]').every(x => x.getAttribute('data-ar') === 'open')
  && mem.parent.elements.slice(-2)[0] === mem && mem.parent.elements.slice(-3)[0].className === 'ar-more' && mem.parent.elements.slice(-1)[0].className === 'ar-foot'
  && !root3.querySelector('.ar-memory') && !el(b.brief(Object.assign({}, F3, { turns: [{ who: 'memory', found: [], failed: '' }, { who: 'memory', found: READ1.found, failed: 'It could not be read.' }] }), { chain: 71, state: 'framing' })).querySelector('.ar-memory')
  && !el(b.brief(FMEM, { chain: 71, state: 'run' })).querySelector('.ar-memory')
  && el(b.brief(FMEM, { chain: 71, state: 'framing', shown: 2 })).querySelectorAll('.ar-memory .tag').length === 0, mem.outerHTML);

// ------------------------------------------------------------ the figures of the brief: a draft, or a grey window (0309-0311; §2.19, §2.20)
const CS = { edit: true, changed: ['figures.0'] }, CR = { edit: false, changed: [] };
const sk = (fig, i, c) => el(b.figure(c || CR, fig, i || 0)).querySelector('.ar-fig');
const KNOWN = { title: 'Two <paths>', kind: 'line', x: 'x', y: 'how far', series: [{ name: 'start <A>' }, { name: 'start B' }], note: 'They <part>.' };
const ON_DATA = { title: 'Yield by season', kind: 'line', x: 'season', y: 'yield', series: [{ name: 'A' }, { name: 'C' }], note: 'Whether the gap holds.' };
const known = sk(KNOWN, 0, CS);
const windowIn = fig => { const w = fig.querySelector('.ar-wait'); return w ? w.className + '=' + w.textContent : ''; };      // the grey window of a panel: its state and its line
const partsOf = fig => fig.elements.map(e => e.className || e.tag).join();
const OLD = [{ title: 'T', kind: 'line', series: [{ name: 'a', points: [[0, 0], [5, 50], [10, 100]] }] }, { title: 'T', kind: 'heatmap', z: 'how much' }, { title: 'T' }];      // one as a brief of 0309 kept it, with points a model wrote; one of a kind with a third axis; one that is a title alone
check('a figure without a draft (0311): a panel with its number, its title as text and - while the brief can be changed - a cross that names its place; under them a grey window with one line in its '
  + 'middle, and nothing else: no sketch, no key, nothing of how the Pathfinder described the figure, and no word that it is a draft (a live run of 0310 was "too busy"). The line says that there '
  + 'is no draft yet - in the brief of a run, that none was drawn; it does not move, and has nothing under the mouse. Every figure is the same window, whatever its kind and whatever a brief of '
  + '0309 kept with it. A panel changed in the version shown carries the bar; one that is read has no cross',
  known.className === 'ar-fig changed' && partsOf(known) === 'hd,ar-wait'
  && known.querySelector('.hd').elements.map(e => e.className + '=' + e.textContent).join('|') === 'n=1|t=Two <paths>|drop='
  && known.querySelector('.drop').getAttribute('data-ar') === 'unfigure' && known.querySelector('.drop').getAttribute('data-path') === 'figures.0' && known.querySelector('.drop').getAttribute('title') === 'Leave it out'
  && windowIn(known) === 'ar-wait=No draft yet.' && known.querySelector('.ar-wait').elements.map(e => e.tag).join() === 'span' && !known.querySelector('.ar-wait').hasAttribute('title')
  && !known.querySelector('.tag') && !known.querySelector('.plot') && !known.querySelector('.cap') && !known.querySelector('.key') && !/They|how far|start/.test(known.textContent)
  && !known.querySelector('paths') && !known.querySelector('part')
  && sk(KNOWN, 2).className === 'ar-fig' && !sk(KNOWN, 2).querySelector('.drop') && sk(KNOWN, 2).querySelector('.n').textContent === '3' && windowIn(sk(KNOWN, 2)) === 'ar-wait=No draft was drawn.'
  && sk(KNOWN, 1, CS).className === 'ar-fig' && sk(KNOWN, 1, CS).querySelector('.drop').getAttribute('data-path') === 'figures.1'
  && OLD.every(f => partsOf(sk(f)) === 'hd,ar-wait' && windowIn(sk(f, 0, CS)) === 'ar-wait=No draft yet.') && typeof b.sketch === 'undefined', known.outerHTML);
const DC = (drafts, more) => Object.assign({ edit: true, changed: [], keys: ['k1', 'k<2>'], drafts }, more);
const capOf = fig => (fig.querySelector('.cap') || { textContent: '' }).textContent;
const drawnC = sk(KNOWN, 0, DC({ k1: { basis: 'computed' } })), drawnM = sk(KNOWN, 1, DC({ 'k<2>': { basis: 'made up' } })), failedF = sk(KNOWN, 0, DC({ k1: { failed: 'the cell failed: <ValueError> "bad"', tries: 2 } }));
const MADE = 'The numbers are made up. The analysis puts in the real ones.';
check('a figure and its draft (0310, 0311): where its draft was drawn the panel says "draft" and holds the place the page draws the plot in, under the figure\'s key - the grey window stays in the '
  + 'markup after it, for where the plot cannot be shown. On made-up numbers the word and a line under the figure say so, and the place is marked for the words drawn across it; a computed one '
  + 'says neither. Where no draft could be drawn the window says so, the reason under the mouse; while a draft is on its way the window says that, and is the one that breathes - for a figure '
  + 'whose first draft failed too, not for one tried twice, nor for one that has its draft. A figure under another key, or under none, has no draft yet. The key and the reason are text',
  drawnC.className === 'ar-fig drawn' && partsOf(drawnC) === 'hd,plot,ar-wait'
  && drawnC.querySelector('.tag').className === 'tag' && drawnC.querySelector('.tag').textContent === 'draft' && drawnC.querySelector('.plot').getAttribute('data-key') === 'k1'
  && !drawnC.querySelector('.plot').hasAttribute('data-made-up') && drawnC.querySelector('.plot').innerHTML === '' && !drawnC.querySelector('.cap') && !!drawnC.querySelector('.drop')
  && windowIn(drawnC) === 'ar-wait=The draft could not be shown.' && !/They/.test(drawnC.textContent)
  && drawnM.className === 'ar-fig drawn' && partsOf(drawnM) === 'hd,plot,cap,ar-wait' && drawnM.querySelector('.tag').className === 'tag mu' && drawnM.querySelector('.tag').textContent === 'draft · made-up numbers'
  && drawnM.querySelector('.plot').getAttribute('data-key') === 'k<2>' && drawnM.querySelector('.plot').getAttribute('data-made-up') === '1' && capOf(drawnM) === MADE
  && failedF.className === 'ar-fig' && partsOf(failedF) === 'hd,ar-wait' && !failedF.querySelector('.tag') && windowIn(failedF) === 'ar-wait=No draft could be drawn.'
  && failedF.querySelector('.ar-wait').getAttribute('title') === 'the cell failed: <ValueError> "bad"' && !failedF.querySelector('ValueError')
  && windowIn(sk(KNOWN, 0, DC({}, { drawing: true }))) === 'ar-wait live=Drawing a draft…' && !sk(KNOWN, 0, DC({}, { drawing: true })).querySelector('.ar-wait').hasAttribute('title')
  && windowIn(sk(KNOWN, 0, DC({ k1: { failed: 'x', tries: 1 } }, { drawing: true }))) === 'ar-wait live=Drawing a draft…' && windowIn(sk(KNOWN, 0, DC({ k1: { failed: 'x' } }, { drawing: true }))) === 'ar-wait live=Drawing a draft…'
  && windowIn(sk(KNOWN, 0, DC({ k1: { failed: 'x', tries: 2 } }, { drawing: true }))) === 'ar-wait=No draft could be drawn.'
  && sk(KNOWN, 0, DC({ k1: { basis: 'computed' } }, { drawing: true })).className === 'ar-fig drawn' && windowIn(sk(KNOWN, 0, DC({ k1: { basis: 'computed' } }, { drawing: true }))) === 'ar-wait=The draft could not be shown.'
  && windowIn(sk(KNOWN, 0, DC({ k1: { failed: 'x', tries: 1 } }))) === 'ar-wait=No draft could be drawn.'
  && sk(KNOWN, 0, DC({ 'k<2>': { basis: 'computed' } })).className === 'ar-fig' && windowIn(sk(KNOWN, 0, DC({ 'k<2>': { basis: 'computed' } }))) === 'ar-wait=No draft yet.'
  && sk(KNOWN, 2, DC({ k1: { basis: 'computed' } })).className === 'ar-fig' && sk(KNOWN, 0, DC({ k1: { basis: 'computed' } }, { changed: ['figures.0'] })).className === 'ar-fig drawn changed'
  && !sk(KNOWN, 0, DC({ k1: { basis: 'computed' } }, { edit: false })).querySelector('.drop') && windowIn(sk(KNOWN, 0, DC({}, { edit: false }))) === 'ar-wait=No draft was drawn.'
  && !/k<2>/.test(drawnM.innerHTML), [drawnC.outerHTML, drawnM.outerHTML, failedF.outerHTML]);
const LAY = { height: 900, title: { text: 'T' }, annotations: [{ text: 'a' }] }, layWas = JSON.stringify(LAY), layM = A.draftLayout(LAY, true), layC = A.draftLayout(LAY, false);
check('the layout a draft is drawn with (0310): the figure\'s own - its title, its axes, its panels - fitted to its place: as wide as the panel, no taller than 560 and no lower than 280, 360 where '
  + 'the figure sets no height, and not to be dragged about. On made-up numbers those words stand across the figure - over the plot, after the figure\'s own notes; a computed draft has none. '
  + 'The figure\'s own layout is not altered',
  layM.height === 560 && layM.autosize === true && 'width' in layM && layM.width === undefined && layM.dragmode === false && same(layM.title, { text: 'T' })
  && layM.annotations.length === 2 && layM.annotations[0].text === 'a'
  && same(layM.annotations[1], { text: 'made-up numbers', xref: 'paper', yref: 'paper', x: 0.5, y: 0.5, showarrow: false, textangle: -18, opacity: 0.28, font: { size: 30, color: '#8a8a8a' } })
  && same(layC.annotations, [{ text: 'a' }]) && layC.height === 560 && JSON.stringify(LAY) === layWas
  && A.draftLayout(null, false).height === 360 && same(A.draftLayout(undefined, false).annotations, []) && A.draftLayout({ height: 100 }, false).height === 280 && A.draftLayout({ height: 400 }, true).height === 400
  && A.draftLayout({ height: 'tall' }, false).height === 360 && A.draftLayout({}, true).annotations.length === 1, [layM, layC]);
const FIGS = [KNOWN, ON_DATA, { title: 'Spread', kind: 'box', series: [{ name: 'A' }, { name: 'C' }] }];
const FF = { versions: F3.versions.concat([{ n: 4, by: 'architect', why: 'answer', changed: ['figures.0', 'figures.2'], brief: Object.assign({}, FULL, { figures: FIGS }), keys: ['kA', 'kB', 'kC'] },
                                           { n: 5, by: 'person', changed: ['figures'], brief: Object.assign({}, FULL, { figures: FIGS.slice(0, 2) }), keys: ['kA', 'kB'] }]),
             drafts: { kA: { basis: 'computed' }, kB: { basis: 'made up' }, kC: { failed: 'the cell failed', tries: 1 } } };
const tabF = el(b.brief(FF, { chain: 71, thread: 7, state: 'framing', shown: 4 })).querySelector('.ar-brief'), figsF = tabF.querySelector('.ar-figs');
const classesF = o => el(b.brief(FF, Object.assign({ chain: 71, thread: 7, state: 'framing', shown: 4 }, o))).querySelectorAll('.ar-fig').map(f => f.className + '/' + (f.classList.contains('drawn') ? capOf(f) : windowIn(f))).join('|');
const only = (figs, more) => el(b.brief(Object.assign({ versions: [{ n: 1, by: 'architect', changed: [], brief: { question: 'q', figures: figs } }] }, more), { chain: 71, state: 'framing' }));
check('the figures on the Brief tab (0309-0311): under a plain heading of their own, after what is fixed before a run and before what the brief builds on - a panel to a figure, in the brief\'s order, '
  + 'each under its number, the ones this version changed marked; the version on screen shows its own figures. A figure is found drawn by its key among the version\'s keys and the drafts the framing '
  + 'keeps: drawn, a grey window that says no draft could be drawn, or - while one is on its way - one that says so; the tab carries the thread its plots are kept under, and that a draft is on '
  + 'its way. While the brief can be changed each has its cross; the brief of a run that has started shows them to be read, drafts and all. A framing without keys - a brief of 0309 - shows '
  + 'no draft. A brief without figures has no such part, and none can be added by hand: the coach asks the Pathfinder. A brief that holds only figures is a brief: on data, what is always tested is said',
  h3s(tabF) === 'What it is for|What you think|Why you think so|What you expect to see|What would change your mind|Other explanations to test|Measured by|What it will look like|Builds on|Set aside'
  && figsF.elements.map(e => e.className + ':' + e.querySelector('.n').textContent + ':' + e.querySelector('.t').textContent).join('|') === 'ar-fig drawn changed:1:Two <paths>|ar-fig drawn:2:Yield by season|ar-fig changed:3:Spread'
  && classesF({}) === 'ar-fig drawn changed/|ar-fig drawn/' + MADE + '|ar-fig changed/ar-wait=No draft could be drawn.'
  && classesF({ drawing: true }) === 'ar-fig drawn changed/|ar-fig drawn/' + MADE + '|ar-fig changed/ar-wait live=Drawing a draft…'
  && classesF({ shown: 5 }) === 'ar-fig drawn/|ar-fig drawn/' + MADE && classesF({ state: 'run' }) === classesF({}) && figsF.querySelectorAll('.plot').map(x => x.getAttribute('data-key')).join() === 'kA,kB'
  && tabF.getAttribute('data-thread') === '7' && !tabF.hasAttribute('data-drawing') && el(b.brief(FF, { chain: 71, thread: 7, state: 'framing', drawing: true })).querySelector('.ar-brief').getAttribute('data-drawing') === '1'
  && el(b.brief({ versions: FF.versions.map(v => Object.assign({}, v, { keys: undefined })), drafts: FF.drafts }, { chain: 71, state: 'framing', shown: 4 })).querySelectorAll('.ar-fig.drawn').length === 0
  && el(b.brief({ versions: FF.versions }, { chain: 71, state: 'framing', shown: 4 })).querySelectorAll('.ar-fig.drawn').length === 0
  && figsF.querySelectorAll('[data-ar="unfigure"]').map(x => x.getAttribute('data-path')).join() === 'figures.0,figures.1,figures.2'
  && el(b.brief(FF, { chain: 71, state: 'framing' })).querySelectorAll('.ar-fig').length === 2 && !el(b.brief(FF, { chain: 71, state: 'framing' })).querySelector('.ar-fig.changed')
  && el(b.brief(FF, { chain: 71, state: 'run' })).querySelectorAll('.ar-fig').length === 2 && !el(b.brief(FF, { chain: 71, state: 'run' })).querySelector('[data-ar="unfigure"]')
  && el(b.brief(FF, { chain: 71, state: 'run', shown: 4 })).querySelectorAll('.ar-fig').length === 3 && el(b.brief(FF, { chain: 71, state: 'framing', shown: 3 })).querySelectorAll('.ar-fig').length === 0
  && !root3.querySelector('.ar-figs') && h3s(root3).indexOf('What it will look like') < 0 && !/figure/i.test(kindsOf(el(b.brief(FF, { chain: 71, state: 'framing', adds: true }))))
  && only([ON_DATA]).querySelector('.ar-always') && !only([ON_DATA], { data: false }).querySelector('.ar-always') && !only([]).querySelector('.ar-always') && !only([]).querySelector('.ar-figs'), tabF.outerHTML);
const BF = { question: 'q', decision: 'd', figures: FIGS }, beforeF = JSON.stringify(BF);
check('unfigure() (0309): the brief without one of its figures, named by its place - the others keep their order, and with the last one the part goes; the part is named as changed. A place no figure '
  + 'stands at, or a path of another part, gives null; the brief passed in is never altered',
  same(A.unfigure(BF, 'figures.1'), { brief: { question: 'q', decision: 'd', figures: [FIGS[0], FIGS[2]] }, changed: ['figures'] })
  && same(A.unfigure(BF, 'figures.0').brief.figures, [FIGS[1], FIGS[2]]) && same(A.unfigure({ question: 'q', figures: [ON_DATA] }, 'figures.0'), { brief: { question: 'q' }, changed: ['figures'] })
  && [A.unfigure(BF, 'figures.3'), A.unfigure(BF, 'figures.-1'), A.unfigure(BF, 'figures.x'), A.unfigure(BF, 'figures.'), A.unfigure(BF, 'figures'), A.unfigure(BF, 'saved.0'), A.unfigure(BF, 1),
      A.unfigure({}, 'figures.0'), A.unfigure(null, 'figures.0')].every(x => x === null)
  && JSON.stringify(BF) === beforeF, A.unfigure(BF, 'figures.1'));

// ------------------------------------------------------------ the conversation
const ASK = { who: 'architect', text: 'What will you do differently depending on the answer?', choices: ['Keep one arm', 'Keep <both>'], v: 1, cost: 0.004, call: 1 };
const TALK = { chain_id: 71, queryText: 'Is B above A?', framing: { versions: F1.versions, turns: [ASK, { who: 'person', text: 'Keep one arm' }, { who: 'architect', text: 'What do you expect to see?', v: 2, cost: 0.014, call: 3 }], calls: 3 } };
const live = el(b.talk({ chain_id: 71, queryText: 'Is B above A?', framing: { versions: F1.versions, turns: [ASK] } }, { live: true }));
const msgs = c => c.querySelectorAll('.ar-msg').map(m => m.className + '|' + m.textContent);
check('the conversation: the question first, then each message under who said it - the coach\'s as typed, the Pathfinder\'s with its green edge; the last message\'s choices are pills to click, shown as text',
  same(msgs(live), ['ar-msg you|YouIs B above A?', 'ar-msg arch|Pathfinder⌘What will you do differently depending on the answer?Keep one armKeep <both>'])
  && same(live.querySelectorAll('.ar-choices .ar-choice[data-ar="choice"]').map(c => c.textContent), ['Keep one arm', 'Keep <both>']) && !live.querySelector('.ar-choice both'), live.innerHTML);
const later = el(b.talk(TALK, { live: true }));
const marked = el(b.said({ who: 'architect', text: 'Is <b>B</b> & "A" above?', call: 2 }, 71, false));
check('what the Pathfinder wrote is shown as text, never as markup', marked.querySelector('.ar-msg').textContent === 'Pathfinder⌘Is <b>B</b> & "A" above?' && !marked.querySelector('.ar-msg b'), marked.innerHTML);
check('choices are offered once: on the Pathfinder\'s last message while it is the last, never on an earlier one, in a conversation only read, or while a reply is awaited',
  later.querySelectorAll('.ar-choice').length === 0 && same(msgs(later).map(m => m.split('|')[0]), ['ar-msg you', 'ar-msg arch', 'ar-msg you', 'ar-msg arch'])
  && el(b.talk({ chain_id: 71, queryText: 'q', framing: { turns: [ASK] } })).querySelectorAll('.ar-choice').length === 0
  && el(b.talk({ chain_id: 71, queryText: 'q', framing: { turns: [ASK] } }, { live: true, waiting: true })).querySelectorAll('.ar-choice').length === 0);
const button = later.querySelectorAll('.ar-msg.arch .sp-prompt');
check('each message of the Pathfinder\'s has the button to the prompt it received: the Pathfinder\'s own calls in this chain\'s log, by their number - a reply asked for twice counts both',
  button.length === 2 && button.every(x => x.className === 'agent-instructions-btn sp-prompt' && x.getAttribute('data-agent') === 'Pathfinder' && x.getAttribute('data-chain') === '71')
  && same(button.map(x => x.getAttribute('data-call')), ['1', '3']) && !el(b.said({ who: 'architect', text: 'x' }, 71, true)).querySelector('.sp-prompt'), later.innerHTML);
const mid = el(b.talk(TALK, { live: true, sent: 'B above A by <2>', waiting: true }));
check('a message on its way is shown at once, as text, and under it the Pathfinder is reading',
  same(msgs(mid).slice(-2), ['ar-msg you|YouB above A by <2>', 'ar-msg arch wait|Pathfinderreading…']), mid.innerHTML);
// a round of lookups
const CHECK = { who: 'check', found: [{ k: 1, about: 'B looked better', fact: 'rows by arm: A 3 · B <3>', ran: true }, { k: 2, about: 'B looked better', fact: 'total of "y": not looked up - there is no column y', ran: false }], secs: 2.4 };
const rowOf = turn => el(b.checked(turn)).querySelector('.sp-row');
check('a round of lookups is one row of the conversation, as the pane shows a tool\'s: CHECK data, how many things were looked up and how many were not, the seconds; what each found is the row\'s title, a line to a lookup, as text',
  rowOf(CHECK).className === 'sp-row tool read' && rowOf(CHECK).textContent === '✓CHECK data1 thing looked up · 1 not2 s'
  && b.checked(CHECK).includes(' title="rows by arm: A 3 · B &lt;3&gt;\ntotal of &quot;y&quot;: not looked up - there is no column y"') && !rowOf(CHECK).querySelector('3')
  && rowOf({ who: 'check', found: [CHECK.found[0], CHECK.found[0], CHECK.found[0]], secs: 0.2 }).textContent === '✓CHECK data3 things looked up1 s'
  && rowOf({ who: 'check', found: [CHECK.found[1]], secs: 61.5 }).textContent === '✓CHECK data0 things looked up · 1 not62 s' && rowOf({ who: 'check' }).textContent === '✓CHECK data0 things looked up1 s', b.checked(CHECK));
// the saved analyses (0303, §3.7; 0308, §2.18): a reading's row, live and done, and under it what was found, an analysis to a line
const MEMORY = { who: 'memory', found: [{ id: '7/8', when: '2026-03-02', question: 'Was B above A in <spring>?', where: 'report', quote: 'B led A by 3 units', note: 'n' },
                                         { id: '7/9', when: '2026-04-02', question: 'Synthesis: Two arms', where: 'cell 2', quote: 'gap = b - a', note: '' },
                                         { id: '7/8', when: '2026-03-02', question: 'Was B above A in <spring>?', where: 'cell 1', quote: 'gap: 3 units', note: '' }],
                 across: { topic: 'How the gap was taken', groups: [{ label: 'B minus A', runs: [{ run: '7/8' }, { run: '7/9' }] }, { label: 'the ratio', runs: [{ run: '5/6' }] }] },
                 of: 12, read: 9, dropped: 1, failed: '', secs: 41.3, cost: 0.07, v: 3 };
const memRow = turn => el(b.recalled(turn)).querySelector('.sp-row');
check('a reading of the saved analyses is one row of the conversation: MEMORY (0311: the row had said SAVED analyses, which read as something saved), how many analyses were found - not how many '
  + 'passages (0308) - and how many of the saved runs were read, the seconds; the passages and the count to each way across them are the row\'s title, as text',
  memRow(MEMORY).className === 'sp-row tool read' && memRow(MEMORY).textContent === '✓MEMORY2 analyses found · read 9 of 1241 s' && memRow(MEMORY).querySelector('.in').textContent === 'MEMORY'
  && memRow(MEMORY).getAttribute('title') === '2026-03-02 · Was B above A in <spring>?: "B led A by 3 units"\n2026-04-02 · Synthesis: Two arms: "gap = b - a"\n2026-03-02 · Was B above A in <spring>?: "gap: 3 units"\nHow the gap was taken: 2 × B minus A; 1 × the ratio'
  && memRow(Object.assign({}, MEMORY, { found: MEMORY.found.slice(0, 1), across: null, read: 0 })).textContent === '✓MEMORY1 analysis found · 12 saved41 s'
  && memRow({ who: 'memory', found: [], of: 12, read: 12, secs: 0.2 }).textContent === '✓MEMORYnothing found · read 12 of 121 s', b.recalled(MEMORY));
const foundList = el(b.recalled(MEMORY)).querySelector('.ar-found');
check('under the row, what the reading found (0308): an analysis to a line, in the order found - its day as a person writes it and what was asked then, as text - with View, which names the analysis '
  + 'by its thread and run; the passages are not listed here: the Brief tab has them. Nothing can be ticked. A reading that found nothing, or was not made, has no list',
  el(b.recalled(MEMORY)).elements.map(e => e.className).join('|') === 'sp-row tool read|ar-found'
  && foundList.querySelectorAll('.it .q').map(x => x.textContent).join('|') === '2 Mar 2026 · Was B above A in <spring>?|2 Apr 2026 · Synthesis: Two arms' && /in &lt;spring&gt;\?/.test(foundList.innerHTML)
  && foundList.querySelectorAll('.ar-open[data-ar="open"]').map(x => x.getAttribute('data-thread') + '/' + x.getAttribute('data-run') + '=' + x.textContent).join() === '7/8=View,7/9=View'
  && !foundList.querySelector('.qt') && !foundList.querySelector('.why') && !foundList.querySelector('.tag') && foundList.querySelectorAll('[data-ar]').length === 2 && !/B led A by 3 units/.test(foundList.textContent)
  && !el(b.recalled({ who: 'memory', found: [], of: 12, read: 12, secs: 0.2 })).querySelector('.ar-found')
  && !el(b.recalled({ who: 'memory', found: MEMORY.found, failed: 'The person skipped it.', secs: 3 })).querySelector('.ar-found'), b.recalled(MEMORY));
check('a reading that was not made is marked as one that did not run: its row says that the coach skipped it, or why it could not be made; a reading in flight says what is being done - SEARCHING '
  + 'MEMORY (0311) - and how far it is: nothing until the server has said how many are saved, then so many of them read - with Skip, which can be pressed from then on',
  memRow({ who: 'memory', found: [], failed: 'The person skipped it.', secs: 3 }).className === 'sp-row tool read skipped'
  && memRow({ who: 'memory', found: [], failed: 'The person skipped it.', secs: 3 }).textContent === '–MEMORYskipped3 s'
  && memRow({ who: 'memory', found: [], failed: 'The saved analyses could not be read: the executor is <away>', secs: 0.4 }).textContent === '–MEMORYnot read · The saved analyses could not be read: the executor is <away>1 s'
  && el(b.reading({ read: 0, of: null })).querySelector('.sp-row.tool.read.pending').textContent === 'SEARCHING MEMORYSkip' && el(b.reading({ read: 0, of: null })).querySelector('.in').textContent === 'SEARCHING MEMORY'
  && el(b.reading({ read: 0, of: null })).querySelector('.ar-skip').hasAttribute('disabled') && !el(b.reading({ read: 0, of: 12 })).querySelector('.ar-skip').hasAttribute('disabled')
  && el(b.reading({ read: 0, of: 12 })).querySelector('.out').textContent === '0 of 12 read' && el(b.reading({ read: 5, of: 12 })).querySelector('.out').textContent === '5 of 12 read'
  && el(b.reading({ of: 12 })).querySelector('.out').textContent === '0 of 12 read' && el(b.reading({ read: 5, of: 12 })).querySelector('.sp-row').textContent === 'SEARCHING MEMORY5 of 12 readSkip'
  && el(b.reading({ read: 5, of: 12 })).querySelector('button.ar-skip[data-ar="skip"]').textContent === 'Skip' && el(b.reading({ read: 5, of: 12 })).querySelector('.live'), b.reading({ read: 5, of: 12 }));
const BS = { question: 'q', saved: BUILT.slice(0, 2).concat([Object.assign({}, BUILT[2], { accepted: true })]) };
check('unbuild() (0308): the brief builds no longer on one saved analysis, named by its id - every passage of it goes, the others stay, and with the last one the part; an analysis the brief does not '
  + 'build on gives null; the brief passed in is not altered. A passage is no line of its own any more: tick() does not accept one, and apply() does not leave one out',
  same(A.unbuild(BS, '7/8'), { brief: { question: 'q', saved: [BS.saved[2]] }, changed: ['saved'] }) && A.unbuild(BS, '7/9').brief.saved.length === 2
  && !('saved' in A.unbuild({ question: 'q', saved: [BS.saved[2]] }, '7/9').brief) && A.unbuild(BS, '5/5') === null && A.unbuild({ question: 'q' }, '7/8') === null && A.unbuild(null, '7/8') === null
  && BS.saved.length === 3 && A.tick(BS, 'saved.0') === null && A.apply(BS, 'saved.0', '') === null && A.apply(BS, 'saved.0', 'other words') === null);
check('go() on a framing kept before steps (0316; use(), 0308): a step is a version there, and the framing with one in use is as the server will have it once the request that names the step is '
  + 'taken - an earlier one is named, the last names none - with nothing else changed: no steps are made up, the conversation stays whole. A number the framing has no step for changes nothing; '
  + 'the framing passed in is not altered',
  A.go(F3, 2).at === 2 && A.go(F3, 1).versions === F3.versions && !('at' in A.go(Object.assign({ at: 1 }, F3), 3)) && !('at' in F3)
  && [0, 4, -1, '2', true, null, 1.5, undefined].every(k => same(A.go(Object.assign({ at: 2 }, F3), k), Object.assign({ at: 2 }, F3))) && same(A.go(null, 1), {}) && A.go(Object.assign({ at: 2 }, F3), 1).at === 1
  && same(Object.keys(A.go(F3, 2)).sort(), ['at', 'versions']) && A.go(F3, 3) === F3 && typeof A.use === 'undefined');
const namedAt = at => el(b.fold({ chain_id: 71, queryText: 'q', framing: Object.assign(at === undefined ? {} : { at }, F3) })).querySelector('.kind').textContent;
check('the step in use, as the fold above a run names it (0316; the version, 0308) - in a framing kept before steps: that of the version the framing names where it has that version, else the last',
  namedAt(undefined) === 'brief · step 3' && namedAt(2) === 'brief · step 2' && namedAt(1) === 'brief · step 1' && [0, 4, 9, -1, '2', 1.5, null].every(at => namedAt(at) === 'brief · step 3'),
  [namedAt(2), namedAt(9)]);
// ---- the steps of a brief's conversation (0316, §2.25). The fixture is the one the engine's suite checks against analyst/steps.py: a conversation that went
// one way (step 3: a figure by week), came back to step 2 and went another (steps 4 to 6: the period, a line by hand, a reply that changed nothing)
const FX = JSON.parse(fs.readFileSync(path.join(__dirname, 'fixtures', 'steps.json'), 'utf8')), FS = FX.framing, S = A.steps, FS_AS_READ = JSON.stringify(FS);
const ks = list => list.map(x => x.k).join(), EVERY = [1, 2, 3, 4, 5, 6];
const asideOf = f => Object.keys(f.aside || {}).sort().map(k => [k, f.aside[k].turns || []]);
const wholeAt = k => Object.assign({}, FS, FX.go[k]);      // the framing with step k in use, as the engine makes it: the file holds what differs
const OLD3 = { versions: FS.versions.slice(0, 3), turns: FS.turns };      // a framing kept before steps: three versions, one conversation
check('the steps of a framing (0316): as it keeps them, with the one in use and the end of the way being walked. The way to a step is the steps from the first to it. The way through a step ends '
  + 'where the way being walked does while the step is on it, else where the newest steps after it lead; a step\'s place is counted on that way, with the steps beside it - what the arrows '
  + 'show and where they lead. Each step holds its own turns: those of the way in use cut from the framing\'s by their counts, the others from what is set aside; every turn the framing '
  + 'holds is counted where the cost is. The brief of a step is the version that stood at its end, and what it changed is the parts of the versions it made. A framing kept before steps '
  + 'has a step to a version, in use the version it names, and its conversation is not cut: no step holds turns of its own',
  S.kept(FS) && !S.kept(F3) && !S.kept(null) && !S.kept({ steps: [] }) && S.of(FS) === FS.steps && S.on(FS) === 6 && S.tip(FS) === 6
  && ks(S.way(FS.steps, 6)) === '1,2,4,5,6' && ks(S.way(FS.steps, 3)) === '1,2,3' && ks(S.way(FS.steps, 0)) === '' && ks(S.way(FS.steps, 9)) === ''
  && [1, 2, 4, 5, 6].every(k => S.end(FS, k) === 6) && S.end(FS, 3) === 3 && S.end(wholeAt(3), 2) === 3 && S.end(wholeAt(3), 4) === 6
  && S.end({ steps: [{ k: 1, from: 0 }, { k: 2, from: 1 }, { k: 3, from: 1 }, { k: 4, from: 3 }, { k: 5, from: 3 }], step: 2, tip: 2 }, 3) === 5
  && same(EVERY.map(k => S.place(FS, k)), [{ i: 1, n: 5, before: 0, after: 2 }, { i: 2, n: 5, before: 1, after: 4 }, { i: 3, n: 3, before: 2, after: 0 }, { i: 3, n: 5, before: 2, after: 5 },
                                          { i: 4, n: 5, before: 4, after: 6 }, { i: 5, n: 5, before: 5, after: 0 }])
  && same(EVERY.map(k => S.held(FS)[k].length), [1, 2, 2, 2, 0, 2]) && S.held(FS)[3][0].text === 'Show it by week' && S.held(FS)[4][0].text === 'Only the first half' && S.held(FS)[2][0] === FS.turns[1]
  && S.all(FS).length === 9 && S.all(F3).length === 0 && S.all(null).length === 0 && S.all(OLD3).length === 7
  && S.brief(FS, 3) === FS.versions[2].brief && S.brief(FS, 6) === FS.versions[4].brief && same(EVERY.map(k => S.changed(FS, k).join()), ['', 'decision', 'figures', 'fixed.period', 'thinks', ''])
  && same(S.of(OLD3), [{ k: 1, from: 0, v: 1, made: [1] }, { k: 2, from: 1, v: 2, made: [2] }, { k: 3, from: 2, v: 3, made: [3] }]) && S.on(OLD3) === 3 && S.on(Object.assign({ at: 2 }, OLD3)) === 2
  && S.tip(Object.assign({ at: 2 }, OLD3)) === 3 && same(S.place(Object.assign({ at: 1 }, OLD3), 2), { i: 2, n: 3, before: 1, after: 3 }) && same(S.held(OLD3), { 1: [], 2: [], 3: [] })
  && same(S.of({}), [{ k: 1, from: 0, v: 1, made: [1] }]) && S.on(null) === 1,
  [EVERY.map(k => S.place(FS, k)), EVERY.map(k => S.changed(FS, k).join())]);
const goneAs = (got, want) => got.step === want.step && got.at === want.at && same(got.turns, want.turns) && same(asideOf(got), asideOf(want))
  && Object.keys(FS).every(key => ['step', 'tip', 'at', 'turns', 'aside'].indexOf(key) >= 0 || got[key] === FS[key]);
check('go() on a framing that keeps its steps (0316) is held to what the engine makes (tests/analyst/fixtures/steps.json): with a step in use the framing names it, the end of its way and - '
  + 'unless it is the last - the version that stood at its end; its turns are those of the way to the step, and the turns of the other steps are set aside; nothing else is changed, and the '
  + 'framing passed in is not altered. The same from any step to any other: a step is gone to from wherever the coach stands. The way being walked stays the one the coach is on while they '
  + 'step along it - back from the end of the way that was left, the arrows lead forward to that end again - and is another once they go to a step off it. The step in use, and a step the '
  + 'framing does not have, change nothing',
  EVERY.every(k => goneAs(A.go(FS, k), FX.go[k]) && A.go(FS, k).tip === FX.go[k].tip) && EVERY.every(from => EVERY.every(k => goneAs(A.go(A.go(FS, from), k), FX.go[k])))
  && same(EVERY.map(k => A.go(A.go(FS, 3), k).tip), [3, 3, 3, 6, 6, 6]) && same(EVERY.map(k => A.go(A.go(A.go(FS, 3), 2), k).tip), [3, 3, 3, 6, 6, 6]) && same(EVERY.map(k => A.go(A.go(FS, 2), k).tip), [6, 6, 3, 6, 6, 6])
  && A.go(FS, 6) === FS && [0, 7, -1, '2', 2.5, null, undefined, true].every(k => A.go(FS, k) === FS) && JSON.stringify(FS) === FS_AS_READ && !('at' in A.go(A.go(FS, 2), 6)) && !('at' in A.go(FS, 5)),
  EVERY.map(k => [k, goneAs(A.go(FS, k), FX.go[k]), A.go(FS, k).tip]));
const tabS = (f, o) => el(b.brief(f, Object.assign({ chain: 71, thread: 7, state: 'framing' }, o))).querySelector('.ar-brief');
const cutS = '<div class="r"><span class="k">You expected</span> <span class="t">B above A</span> <span class="v ok">met</span></div>';      // what a report said against the brief
const verS = r => r.querySelector('.ar-ver').elements.map(e => e.tag + (e.getAttribute('data-step') || e.getAttribute('data-ar') || '') + (e.hasAttribute('disabled') ? ' off' : '') + (e.tag === 'button' ? '' : '=' + e.textContent)).join('|');
const tabAt = k => { const r = tabS(A.go(FS, k), {}); return [verS(r), r.getAttribute('data-shown'), r.querySelector('[data-ar="start"]').textContent, r.querySelectorAll('.ar-line.changed').map(x => x.getAttribute('data-path')).join(), h3s(r)].join(' / '); };
check('the Brief tab of a conversation that branched (0316): beside "Step" the arrows count the way through the step on screen - "5 of 5" at its end, where the arrow forward is off - and '
  + 'nothing stands after them: the map of the steps is the maps drawer\'s (0327). With another step in use the tab is the brief as it stood there: its place on its way, the parts it held, the line it changed marked, '
  + 'and Start analysis names the step unless it is the last of its way - the end of the way that was left is one, "3 of 3", with its figure. While the Pathfinder replies neither arrow '
  + 'can be pressed. The tab of a run shows the step it is asked for, to be read; what its report said against the brief stands under every step whose brief is the one the run '
  + 'was under - the step it started from, and one before it that the last step did not change - and under no other',
  tabAt(6) === 'span=Step|button-1|b=5 of 5|button1 off / 6 / Start analysis /  / What it is for|What you think|Period'
  && tabAt(5) === 'span=Step|button-1|b=4 of 5|button1 / 5 / Start analysis from step 4 / thinks / What it is for|What you think|Period'
  && tabAt(2) === 'span=Step|button-1|b=2 of 5|button1 / 2 / Start analysis from step 2 / decision / What it is for'
  && tabAt(3) === 'span=Step|button-1|b=3 of 3|button1 off / 3 / Start analysis /  / What it is for|What it will look like'
  && tabAt(1) === 'span=Step|button-1 off|b=1 of 5|button1 / 1 / Start analysis from step 1 /  / '
  && !tabS(FS, {}).querySelector('[data-ar="map"]') && !tabS(FS, {}).querySelector('.ar-map')
  && verS(tabS(FS, { held: true })) === 'span=Step|button-1 off|b=5 of 5|button1 off' && verS(tabS(A.go(FS, 2), { held: true })) === 'span=Step|button-1 off|b=2 of 5|button1 off'
  && verS(tabS(FS, { state: 'run', shown: 3 })) === 'span=Step|button-1|b=3 of 3|button1 off' && !tabS(FS, { state: 'run', shown: 3 }).querySelector('[data-ar="start"]')
  && tabS(FS, { state: 'run', shown: 3 }).getAttribute('data-shown') === '3' && tabS(FS, { state: 'run', shown: 9 }).getAttribute('data-shown') === '6'
  && same(EVERY.map(k => !!tabS(FS, { state: 'run', against: cutS, shown: k }).querySelector('.ar-against')), [false, false, false, false, true, true])
  && same(EVERY.map(k => S.used(FS, k)), [false, false, false, false, true, true]) && same([1, 2, 3].map(k => S.used(Object.assign({ at: 2 }, OLD3), k)), [false, true, false]) && !S.used(FS, 9),
  EVERY.map(tabAt));
const paneS = k => { const p = el(b.pane({ chain_id: 71, thread_id: 7, queryText: 'q', framing: A.go(FS, k) }));
  return [p.querySelector('.sp-strip').textContent, p.querySelectorAll('.ar-msg').map(m => m.className.split(' ')[1] + ':' + m.querySelector('.who').textContent.replace('⌘', '') + ':' + m.textContent.split('⌘').pop().replace(/^You/, '')).join('|'),
          p.querySelectorAll('.ar-choice').length].join(' / '); };
// the conversation of the way to step k, as the engine holds it: the question as it was first asked, then each turn under who said it - a reply's choices after its words
const saidS = k => ['you:You:Is B above A?'].concat(FX.go[k].turns.map(t => (t.who === 'person' ? 'you:You:' : 'arch:Pathfinder:') + t.text)).join('|');
const foldS = k => el(b.fold({ chain_id: 71, queryText: 'q', framing: A.go(FS, k) }));
check('the left pane of a conversation that branched (0316): the conversation of the way to the step in use, and nothing of the others - at the end of the way walked, no word of the figure by '
  + 'week; at the end of the way that was left, that exchange and nothing of what came after the coach went back; at the first step the question and the Pathfinder\'s first message, whose '
  + 'choices can be clicked again. No row says where the coach went. The strip counts what the brief has cost over every step, those set aside too: a way that was left was paid for. The '
  + 'fold above a run names the step it started from, as the arrows count it, and holds the way to it',
  [2, 3, 4, 5, 6].every(k => paneS(k) === 'Pathfinder$0.05 / ' + saidS(k) + ' / 0') && paneS(1) === 'Pathfinder$0.05 / ' + saidS(1) + 'Keep one armKeep both / 2'
  && /Only the first half/.test(paneS(6)) && !/by week/.test(paneS(6)) && /Show it by week/.test(paneS(3)) && !/first half/.test(paneS(3)) && paneS(5) === paneS(4) && !/in use|step/.test(el(b.pane({ chain_id: 71, queryText: 'q', framing: A.go(FS, 2) })).textContent)
  && same([6, 5, 3, 2, 1].map(k => foldS(k).querySelector('.kind').textContent), ['brief · step 5', 'brief · step 4', 'brief · step 3', 'brief · step 2', 'brief · step 1'])
  && foldS(3).querySelectorAll('.sp-detail .ar-msg').length === 6 && foldS(2).querySelectorAll('.sp-detail .ar-msg').length === 4, [paneS(6), paneS(3), paneS(1)]);
const dlg = el(b.savedDialog({ id: '7/8', when: '2026-03-02T10:00:00Z', question: 'Was B above A in <spring>?', title: 'B led', report: '# B led\n\nB led A by <3> units.', marks: ['picked', 'routine'],
                              data: { name: 'spring.csv', period: '2026-03-01 to 2026-05-31', person: 'First <Person>' }, cells: [{ n: 1, code: 'gap = b - a  # <b>' }] }));
const dlgB = el(b.savedDialog({ question: 'q', report: 'r', brief: 'Decision: keep <one>\nFixed before the run:\n- measure: height', cells: [{ n: 2, code: 'x = 1' }] }));
check('a saved analysis that was framed: the brief it ran under is folded under the report, before the code, as text and a line each; one that was not framed has no such fold',
  same([...dlgB.querySelectorAll('details.ar-code summary')].map(x => x.textContent), ['Brief', 'Code']) && dlgB.querySelector('details.ar-code pre.said').textContent === 'Decision: keep <one>\nFixed before the run:\n- measure: height'
  && !dlgB.querySelector('details.ar-code').hasAttribute('open') && dlgB.querySelectorAll('pre.said').length === 1
  && same([...el(b.savedDialog({ question: 'q', report: 'r', brief: '', cells: [{ n: 2, code: 'x = 1' }] })).querySelectorAll('details.ar-code summary')].map(x => x.textContent), ['Code'])
  && same([...el(b.savedDialog({ question: 'q', report: 'r', brief: 'Decision: d' })).querySelectorAll('details.ar-code summary')].map(x => x.textContent), ['Brief']), dlgB.innerHTML);
const dlgC = el(b.savedDialog({ question: 'q', report: 'r', conversation: 'Person: Plot <it>\nPathfinder: A Person: or two things?\n\n- the shape\nPerson: The shape', brief: 'Decision: d - Person: no', cells: [{ n: 2, code: 'x = 1' }] }));
check('a saved analysis that was framed in a conversation: what was said is folded under the report, before the brief, as text with its lines, the person\'s messages under "You"; one without a conversation has no such fold',
  same([...dlgC.querySelectorAll('details.ar-code summary')].map(x => x.textContent), ['Conversation', 'Brief', 'Code'])
  && dlgC.querySelector('details.ar-code pre.said').textContent === 'You: Plot <it>\nPathfinder: A Person: or two things?\n\n- the shape\nYou: The shape' && dlgC.querySelectorAll('pre.said').length === 2
  && dlgC.querySelectorAll('pre.said')[1].textContent === 'Decision: d - Person: no'
  && !dlgC.querySelector('details.ar-code').hasAttribute('open')
  && same([...el(b.savedDialog({ question: 'q', report: 'r', conversation: '', brief: 'Decision: d' })).querySelectorAll('details.ar-code summary')].map(x => x.textContent), ['Brief']), dlgC.innerHTML);
check('a saved analysis opened beside the brief: a dialog with what was asked, the day, whose data it ran on and which, and how it was saved; the report, and under it the code of its cells, folded, as text',
  dlg.querySelector('.ui-dlg.lg[role="dialog"] .ui-dlg-h .title').textContent === 'Was B above A in <spring>?' && dlg.querySelector('.ui-dlg-h .sub').textContent === '2026-03-02 · First <Person> · spring.csv · 2026-03-01 to 2026-05-31 · picked, routine'
  && dlg.querySelector('.ui-dlg-h button.x[data-ar="shut"]') && dlg.querySelector('.ui-dlg-b pre').textContent.indexOf('B led A by <3> units.') >= 0
  && dlg.querySelector('details.ar-code summary').textContent === 'Code' && dlg.querySelector('details.ar-code pre').textContent === 'gap = b - a  # <b>' && !dlg.querySelector('details.ar-code').hasAttribute('open')
  && el(b.savedDialog({ question: '', title: 'A synthesis', report: 'r', cells: [] })).querySelector('.title').textContent === 'A synthesis' && !el(b.savedDialog({ report: 'r' })).querySelector('details'), dlg.innerHTML);
const dlgH = el(b.savedDialog({ question: 'Is B above A?', when: '2026-03-02T10:00:00Z', report: 'r', hints: [{ turn: 2, text: 'Keep the <soil> types apart.' }, { turn: 4, text: 'Leave the sandy plots out.' }] }));
check('a saved analysis that is a branch (2.9): under what was asked and the day, the hints it was made under, each with the turn it was given after, as text; a run without one has no such line',
  same([...dlgH.querySelectorAll('.ui-dlg-h .hint')].map(x => x.textContent), ['From turn 2Keep the <soil> types apart.', 'From turn 4Leave the sandy plots out.'])
  && dlgH.querySelector('.ui-dlg-h .hint b').textContent === 'From turn 2' && dlgH.querySelector('.ui-dlg-h .sub').textContent === '2026-03-02'
  && !dlg.querySelector('.ui-dlg-h .hint') && !el(b.savedDialog({ question: 'q', report: 'r', hints: [] })).querySelector('.hint'), dlgH.innerHTML);
const KEEP = { who: 'architect', text: 'One line does not hold. Keep it, or change it?', choices: ['Keep it', 'Change it'], v: 2, cost: 0.01, call: 5 };
const ROUND = { chain_id: 71, queryText: 'Is B above A?', framing: { versions: F1.versions, turns: [{ who: 'person', text: 'B well above A' }, { who: 'architect', text: 'Checking this against the data.', v: 1, call: 4 }, CHECK, KEEP] } };
const round = b.talk(ROUND, { live: true }), between = el(b.talk({ chain_id: 71, queryText: 'q', framing: { turns: ROUND.framing.turns.slice(0, 3) } }, { live: true }));
check('the row stands in the conversation where the round was made: after the message that asked for it, before the one that marks the lines - whose choices are the ones to click; with the round the last thing said, there is nothing to click',
  round.indexOf('Checking this against the data.') < round.indexOf('class="sp-row tool read"') && round.indexOf('class="sp-row tool read"') < round.indexOf('One line does not hold.')
  && same(el(round).querySelectorAll('.ar-choice').map(c => c.textContent), ['Keep it', 'Change it']) && el(round).querySelectorAll('.sp-row').length === 1 && el(round).querySelectorAll('.ar-msg').length === 4
  && between.querySelectorAll('.ar-choice').length === 0 && between.querySelectorAll('.sp-row').length === 1
  && el(b.fold(ROUND)).querySelectorAll('.sp-detail .sp-row').length === 1 && el(b.fold(ROUND)).querySelectorAll('.sp-detail .ar-choice').length === 0, round);
const paneOf = (e, o) => el(b.pane(e, o));
check('the left pane of a brief not yet run: the strip says Pathfinder and what its calls have cost - nothing while that is under a cent - and names no version: the Brief tab does (0308); the '
  + 'conversation under it',
  paneOf(TALK).querySelector('.sp-strip').textContent === 'Pathfinder$0.02' && paneOf({ chain_id: 1, queryText: 'q', framing: { versions: F3.versions, turns: [ASK] } }).querySelector('.sp-strip').textContent === 'Pathfinder'
  && paneOf(TALK).querySelectorAll('.sp-stream .ar-msg').length === 4 && paneOf(TALK, { waiting: true }).querySelectorAll('.sp-stream .ar-msg').length === 5
  && paneOf({ chain_id: 1, queryText: 'q', framing: F1 }).querySelector('.sp-stream').textContent === 'YouIs B above A?'
  && paneOf({ chain_id: 1, queryText: 'q', framing: {} }).querySelector('.sp-stream').textContent === 'Youq', paneOf(TALK).innerHTML);
const folded = el(b.fold(TALK));
check('once the analysis starts the framing is one folded row above it - Pathfinder, the step, the question - with the conversation inside, to be read: no choices, the prompt buttons kept',
  folded.querySelector('details.sp-turn.ar-fold summary').textContent === 'Pathfinderbrief · step 1Is B above A?' && folded.querySelectorAll('.sp-detail .ar-msg').length === 4
  && folded.querySelectorAll('.sp-detail .sp-prompt').length === 2
  && el(b.fold({ chain_id: 71, queryText: 'q', framing: { versions: F1.versions, turns: [ASK] } })).querySelectorAll('.ar-choice').length === 0, folded.innerHTML);
const NASTY = { versions: [{ n: 1, by: 'person', changed: [], brief: { question: 'Is "B" <b>above</b> A & C?', decision: '<script>alert(1)</script>', thinks: 'x &lt; y &amp; z' } }] };
const tn = el(b.brief(NASTY, { chain: 9, state: 'framing' })).querySelector('.ar-brief');
check('what the coach typed is shown as text, never as markup, and the versions survive the trip through the tab\'s own markup',
  tn.querySelector('h1 .tx').textContent === 'Is "B" <b>above</b> A & C?' && !tn.querySelector('h1 b') && !tn.querySelector('script')
  && lineOf(tn, 'decision').querySelector('.tx').textContent === '<script>alert(1)</script>' && lineOf(tn, 'thinks').querySelector('.tx').textContent === 'x &lt; y &amp; z'
  && same(JSON.parse(tn.getAttribute('data-framing')), NASTY), tn.outerHTML);
const ENTRY = { status: 'framing', chain_id: 71, thread_id: 7, queryText: 'Is B <above> A?', framing: F3 };
const pane = el(b.pane(ENTRY)), fold = el(b.fold(ENTRY)), ed = el(b.editor('a "line" & more'));
check('the left pane of a brief not yet run: the strip says Pathfinder, idle; the coach\'s card holds the question as it was first asked, as text - the brief holds it as it stands now',
  pane.querySelector('.sp-strip .live.idle') && pane.querySelector('.sp-strip .mode').textContent === 'Pathfinder' && pane.querySelector('.sp-strip').textContent === 'Pathfinder'
  && pane.querySelector('.sp-stream .ar-msg.you .who').textContent === 'You' && pane.querySelector('.sp-stream .ar-msg.you').textContent === 'YouIs B above A?'
  && el(b.pane({ chain_id: 71, queryText: 'A later wording', framing: { versions: [{ n: 1, by: 'person', changed: [], brief: { question: 'Is B <above> A?' } }, { n: 2, by: 'architect', changed: ['question'], brief: { question: 'A later wording' } }] } }))
       .querySelector('.sp-stream .ar-msg.you').textContent === 'YouIs B <above> A?', pane.innerHTML);
check('once the analysis starts the framing is one folded row above the run: Pathfinder, the step, the question; the coach\'s card inside',
  fold.querySelector('details.sp-turn.ar-fold') && !fold.querySelector('details').hasAttribute('open') && fold.querySelector('summary .n').textContent === 'Pathfinder' && fold.querySelector('summary .kind').textContent === 'brief · step 3'
  && fold.querySelector('summary .peek').textContent === 'Is B <above> A?' && fold.querySelector('.sp-detail .ar-msg.you').textContent === 'YouIs B above A?', fold.innerHTML);
check('the line being typed: a field holding the text, bounded as a line of the brief is - as the question is, for the question - then Keep and Cancel',
  ed.querySelector('.ar-edit textarea.ar-input').textContent === 'a "line" & more' && ed.querySelector('textarea').getAttribute('maxlength') === '600'
  && el(b.editor('q', true)).querySelector('textarea').getAttribute('maxlength') === '4000'
  && ed.querySelectorAll('[data-ar]').map(x => x.getAttribute('data-ar') + ':' + x.getAttribute('title')).join() === 'keep:Keep,cancel:Cancel', ed.innerHTML);

// ------------------------------------------------------------ the question worded, the version in use, and a part opened (0307, 0308)
const turnW = { who: 'architect', text: 'I have put that into the question.', wording: 'Plot <x>\nagainst z.', v: 2, call: 2, choices: ['Change it'] };
const FW = { versions: [{ n: 1, by: 'person', changed: [], brief: { question: 'Plot it' } }, { n: 2, by: 'architect', why: 'answer', changed: ['question'], brief: { question: 'Plot <x>\nagainst z.' } }],
             turns: [{ who: 'person', text: 'The usual one' }, turnW] };
const entryW = f => ({ chain_id: 71, queryText: 'Plot it', framing: f });
const talkW = el(b.talk(entryW(FW), { live: true })), rowW = talkW.querySelectorAll('.sp-row')[0];
const rowsIn = (versions, turns) => el(b.talk(entryW({ versions, turns }))).querySelectorAll('.sp-row').length;
check('a reply that worded the question (0308): its message shows its words and its choices and nothing of the wording - the question\'s box has it - and under the message a row says the question was '
  + 'updated, and at which step. No row where a reply\'s wording was not written: a message of 0307 whose wording waited, a version the coach made, a version that changed another part, a question '
  + 'that reads otherwise, a reply with none. Nothing in the conversation is taken with a button',
  talkW.elements.map(e => e.className.split(' ').slice(0, 2).join('.')).join() === 'ar-msg.you,ar-msg.you,ar-msg.arch,sp-row.tool'
  && talkW.querySelector('.ar-msg.arch').elements.map(e => e.className).join() === 'who,ar-choices' && !talkW.querySelector('.ar-wording') && !talkW.querySelector('[data-ar="use"]')
  && !/against z/.test(talkW.querySelector('.ar-msg.arch').textContent)
  && rowW.className === 'sp-row tool read' && rowW.elements.map(e => e.className + '=' + e.textContent).join('|') === '=✓|in=QUESTION|out=updated|t=step 2'
  && rowsIn(FW.versions.slice(0, 1), [Object.assign({}, turnW, { v: 1 })]) === 0
  && rowsIn([FW.versions[0], Object.assign({}, FW.versions[1], { by: 'person' })], [turnW]) === 0 && rowsIn([FW.versions[0], Object.assign({}, FW.versions[1], { changed: ['decision'] })], [turnW]) === 0
  && rowsIn([FW.versions[0], Object.assign({}, FW.versions[1], { brief: { question: 'My own words' } })], [turnW]) === 0 && rowsIn(FW.versions, [{ who: 'architect', text: 'No wording.', v: 2 }]) === 0
  && rowsIn(FW.versions, [turnW]) === 1 && el(b.asked('<3>')).querySelector('.t').textContent === 'step <3>' && typeof A.pending === 'undefined' && typeof b.wording === 'undefined', talkW.innerHTML);
// a reply that worded the question, in a conversation that keeps its steps: the row names the step's place on its way, which is not the version's number
const WS = { versions: [FW.versions[0], FW.versions[1]], turns: [{ who: 'architect', text: 'What is it for?', v: 1 }, { who: 'person', text: 'To choose.' }, { who: 'architect', text: 'And over which period?', v: 1 },
                                                              { who: 'person', text: 'x against z' }, turnW],
             steps: [{ k: 1, from: 0, v: 1, made: [1], turns: 1 }, { k: 2, from: 1, v: 1, made: [], turns: 2 }, { k: 3, from: 2, v: 2, made: [2], turns: 2 }], step: 3, tip: 3 };
// ... and one whose way passes a step that was left: the question was read, then the coach went back to the first step and spoke from it
const WL = { versions: [FW.versions[0], FW.versions[1]], turns: [{ who: 'architect', text: 'What is it for?', v: 1 }, { who: 'person', text: 'x against z' }, turnW],
             steps: [{ k: 1, from: 0, v: 1, made: [1], turns: 1 }, { k: 2, from: 1, v: 1, made: [], turns: 1 }, { k: 3, from: 1, v: 2, made: [2], turns: 2 }], step: 3, tip: 3,
             aside: { 2: { turns: [{ who: 'reader', missing: [], v: 1 }] } } };
check('the row under a reply that worded the question, in a conversation that keeps its steps (0316): it names the step\'s place on its way - the third step, though the version it made is the '
  + 'second; and the second where the way passes a step that was left - a step off the way is not counted',
  el(b.talk(entryW(WS))).querySelectorAll('.sp-row').map(r => r.textContent).join('|') === '✓QUESTIONupdatedstep 3' && turnW.v === 2
  && el(b.talk(entryW(WL))).querySelectorAll('.sp-row').map(r => r.textContent).join('|') === '✓QUESTIONupdatedstep 2', [b.talk(entryW(WS)), b.talk(entryW(WL))]);
const DRAFT_OK = { who: 'draft', drawn: [{ title: 'A', basis: 'computed' }, { title: 'B', basis: 'made up' }], v: 2, secs: 6.4, cost: 0.002, call: 3 };
const DRAFT_PART = { who: 'draft', drawn: [{ title: 'A', basis: 'made up' }], missing: ['B'], failed: 'the cell failed: <ValueError>', v: 3, secs: 0.2, cost: 0.004, call: 5 };
const DRAFT_NONE = { who: 'draft', drawn: [], missing: ['A', 'B'], failed: 'it could not be drawn: the sandbox is away', v: 3, secs: 21, cost: 0 };
const turnsD = [{ who: 'person', text: 'Show me' }, Object.assign({}, turnW, { choices: ['Yes', 'Change it'] }), DRAFT_OK];
const talkD = el(b.talk(entryW({ versions: FW.versions, turns: turnsD }), { live: true })), rowsD = [DRAFT_OK, DRAFT_PART, DRAFT_NONE].map(t => el(b.drafted(t, 71)).querySelector('.sp-row'));
const waits = o => el(b.talk(entryW({ versions: FW.versions, turns: turnsD.slice(0, 2) }), Object.assign({ live: true, waiting: true }, o))).elements.slice(-1)[0];
check('the draft of the figures in the conversation (0310): a row under the reply that had it drawn - how many figures were drawn, the seconds, and the button to the prompt its cell was written from, '
  + 'which names the draft\'s call; where some were not drawn the row says how many and is greyed, the reason under the mouse; where none was, it says so. The reply\'s choices can still be '
  + 'clicked with the draft\'s row under it - not once the coach has spoken again. While the draft is on its way a row says what is being done - DRAWING A DRAFT (0311: it had said FIGURES, and what '
  + 'of them in grey after it) - in the place of the Pathfinder\'s "reading"; a reading of the saved analyses is said first. Nothing in a row is markup; a reply of 0309 that says how many it '
  + 'sketched has no row',
  talkD.elements.map(e => e.className.split(' ').slice(0, 2).join('.')).join() === 'ar-msg.you,ar-msg.you,ar-msg.arch,sp-row.tool,sp-row.tool' && talkD.querySelectorAll('.ar-choice').length === 2
  && talkD.querySelectorAll('.sp-row').map(r => r.textContent).join('|') === '✓QUESTIONupdatedstep 2|✓FIGURES2 drawn6 s⌘'
  && rowsD[0].className === 'sp-row tool read' && !rowsD[0].hasAttribute('title') && rowsD[0].elements.map(e => e.className + '=' + e.textContent).join('|') === '=✓|in=FIGURES|out=2 drawn|t=6 s|agent-instructions-btn sp-prompt=⌘'
  && ['data-agent', 'data-chain', 'data-call', 'title'].map(a => rowsD[0].querySelector('.sp-prompt').getAttribute(a)).join('|') === 'Draft|71|3|the prompt the draft was written from (run log)'
  && rowsD[1].className === 'sp-row tool read skipped' && rowsD[1].getAttribute('title') === 'the cell failed: <ValueError>' && rowsD[1].textContent === '–FIGURES1 drawn · 1 not1 s⌘'
  && rowsD[2].className === 'sp-row tool read skipped' && rowsD[2].textContent === '–FIGURESno draft21 s' && !rowsD[2].querySelector('.sp-prompt') && rowsD[2].getAttribute('title') === 'it could not be drawn: the sandbox is away'
  && el(b.talk(entryW({ versions: FW.versions, turns: turnsD.concat([{ who: 'person', text: 'Yes' }]) }), { live: true })).querySelectorAll('.ar-choice').length === 0
  && el(b.talk(entryW({ versions: FW.versions, turns: turnsD.concat([DRAFT_PART]) }), { live: true })).querySelectorAll('.ar-choice').length === 2
  && el(b.talk(entryW({ versions: FW.versions, turns: turnsD }))).querySelectorAll('.ar-choice').length === 0
  && el(b.pending('DOING IT')).querySelector('.sp-row').className === 'sp-row tool read pending' && el(b.pending('DOING IT')).querySelector('.sp-row').elements.map(e => e.className + '=' + e.textContent).join('|') === 'live=|in=DOING IT'
  && typeof b.drawingRow === 'undefined'
  && waits({ drawing: true }).className === 'sp-row tool read pending' && waits({ drawing: true }).textContent === 'DRAWING A DRAFT' && waits({}).className === 'ar-msg arch wait'
  && waits({ drawing: true, saved: { read: 1, of: 3 } }).textContent === 'SEARCHING MEMORY1 of 3 readSkip' && waits({ drawing: true }).parent.querySelectorAll('.ar-choice').length === 0
  && typeof b.sketched === 'undefined' && typeof b.sketch === 'undefined'
  && el(b.talk(entryW({ versions: FW.versions, turns: [{ who: 'architect', text: 'As it was.', sketched: 2, v: 2 }] }))).querySelectorAll('.sp-row').length === 0, [talkD.innerHTML, rowsD.map(r => r.outerHTML)]);
const qRow = (turn, chain) => el(b.checkedQ(turn, chain == null ? 71 : chain)).querySelector('.sp-row');
const qClean = qRow({ who: 'reader', missing: [], v: 2, cost: 0.002, call: 2, secs: 2.4 }), qNot = qRow({ who: 'reader', missing: ['as on 14 May', 'a <b> & "c"'], v: 2, call: 1, secs: 0.3 }, 'c"7');
const talkQ = el(b.talk(entryW({ versions: FW.versions, turns: FW.turns.concat([{ who: 'reader', missing: ['as before'], v: 2, call: 1, secs: 3 }, { who: 'architect', text: 'I said what was before.', v: 2, choices: ['Yes'] }]) }), { live: true }));
check('the question\'s check in the conversation (0313): a row where the question was read as the Analyst will read it - that it stands on its own, the seconds, and the button to what the reader was '
  + 'given, which names the question check\'s call in the run log; where the Analyst cannot place something the row is greyed and says which words, each in quotes, as text - whole: the '
  + 'stylesheet lets that row wrap, where any other row is cut at one line. A read without a '
  + 'call has no button; less than a second reads as one. The Pathfinder\'s reply stands under the row, its choices to be clicked. While the question is read a row says so - CHECKING THE '
  + 'QUESTION - in the place of the Pathfinder\'s "reading"; a draft on its way is said first',
  qClean.className === 'sp-row tool read' && qClean.elements.map(e => e.className + '=' + e.textContent).join('|') === '=✓|in=CHECK question|out=stands on its own|t=2 s|agent-instructions-btn sp-prompt=⌘'
  && ['data-agent', 'data-chain', 'data-call', 'title'].map(a => qClean.querySelector('.sp-prompt').getAttribute(a)).join('|') === 'Question check|71|2|what the question check was given (run log)'
  && qNot.className === 'sp-row tool read skipped ar-unplaced' && qNot.elements.map(e => e.className + '=' + e.textContent).join('|') === '=–|in=CHECK question|out=the Analyst cannot place “as on 14 May” · “a <b> & "c"”|t=1 s|agent-instructions-btn sp-prompt=⌘'
  && qNot.querySelector('.out').elements.length === 0 && qNot.querySelector('.sp-prompt').getAttribute('data-chain') === 'c"7'
  && !qRow({ who: 'reader', missing: [], secs: 1 }).querySelector('.sp-prompt') && qRow({ who: 'reader' }).textContent === '✓CHECK questionstands on its own1 s'
  && talkQ.elements.slice(-2).map(e => e.className.split(' ').slice(0, 2).join('.')).join() === 'sp-row.tool,ar-msg.arch' && talkQ.querySelectorAll('.sp-row').slice(-1)[0].textContent === '–CHECK questionthe Analyst cannot place “as before”3 s⌘'
  && talkQ.querySelectorAll('.ar-choice').length === 1
  && waits({ checking: true }).className === 'sp-row tool read pending' && waits({ checking: true }).textContent === 'CHECKING THE QUESTION' && waits({ checking: true, drawing: true }).textContent === 'DRAWING A DRAFT'
  && fs.readFileSync(path.join(__dirname, '..', '..', 'web_app', 'static', 'css', 'pane.css'), 'utf8').includes('#streamOutput .sp-row.ar-unplaced .out { white-space: normal; overflow: visible; overflow-wrap: anywhere; }')
  && !qClean.className.includes('ar-unplaced'),
  [qClean.outerHTML, qNot.outerHTML, talkQ.innerHTML]);
const wentRow = el(b.went({ who: 'version', v: 2 })).querySelector('.sp-row');
const talkV = el(b.talk(entryW({ versions: FW.versions, turns: FW.turns.concat([{ who: 'version', v: 1 }, { who: 'person', text: 'From the first one' }, { who: 'architect', text: 'As you say.', v: 1 }]) })));
check('a conversation kept before steps (0316): where the coach went to another version before a message (0308), a row says which step is in use from there - before the message it came with; the '
  + 'fold above a run names the step in use, which is not always the last',
  wentRow.className === 'sp-row tool read' && wentRow.elements.map(e => e.className + '=' + e.textContent).join('|') === '=✓|in=BRIEF|out=step 2 in use'
  && talkV.elements.map(e => e.className.split(' ').slice(0, 2).join('.')).join() === 'ar-msg.you,ar-msg.you,ar-msg.arch,sp-row.tool,sp-row.tool,ar-msg.you,ar-msg.arch'
  && talkV.querySelectorAll('.sp-row')[1].textContent === '✓BRIEFstep 1 in use'
  && el(b.fold(entryW(Object.assign({ at: 1 }, FW)))).querySelector('summary .kind').textContent === 'brief · step 1' && el(b.fold(entryW(FW))).querySelector('summary .kind').textContent === 'brief · step 2', talkV.innerHTML);
const rowO = el(b.opened({ who: 'opened', what: 'cell', n: 5, label: 'cell <5>', chars: 12345 })).querySelector('.sp-row');
const rowN = el(b.opened({ who: 'opened', missing: 'there is no cell 99: the cells are 1 to 5' })).querySelector('.sp-row');
const talkO = el(b.talk(entryW({ versions: FW.versions, turns: [{ who: 'person', text: 'How was it drawn?' }, { who: 'architect', text: 'I am opening the cell.', v: 1 },
                                                               { who: 'opened', what: 'cell', n: 5, label: 'cell 5', chars: 66 }, { who: 'architect', text: 'It draws one line a month.', v: 1 }] })));
check('a part of an earlier analysis the Pathfinder opened is a row of the conversation, as the pane shows a tool\'s: READ, what was read - as text - and how long it is; a part that is not there says so in '
  + 'the place of both, marked as a step that did not run. The row stands where the part was opened: after the message that asked, before the one that speaks of it',
  rowO.className === 'sp-row tool read' && rowO.elements.map(e => e.className + '=' + e.textContent).join('|') === '=✓|in=READ|out=cell <5>|t=12,345 characters' && !rowO.querySelector('.out b')
  && rowN.className === 'sp-row tool read skipped' && rowN.elements.map(e => e.className + '=' + e.textContent).join('|') === '=–|in=READ|out=there is no cell 99: the cells are 1 to 5'
  && talkO.elements.map(e => e.className.split(' ').slice(0, 2).join('.')).join() === 'ar-msg.you,ar-msg.you,ar-msg.arch,sp-row.tool,ar-msg.arch', talkO.innerHTML);
check('the field a line is typed in says nothing of its own (0308): the part\'s heading stands over it', !el(b.editor('', false)).querySelector('.ar-input').hasAttribute('placeholder') && b.editor.length === 2);

// ------------------------------------------------------------ the report's part "Against the brief": out of the answer (0312)
const LIST = '<h1 id="t">B is above A</h1>\n<p>For the decision: keep B.</p>\n<h2 id="against-the-brief">Against the brief</h2>\n<ul>\n<li>Expected: not met - the gap is 0.4 <span class="cite cell" onclick="x()">cell 2</span></li>\n' +
  '<li>Would change their mind: seen</li>\n<li>chance: the interval includes 0</li>\n<li>measurement error: cannot tell, nothing says how x was measured</li>\n<li>the two halves differ: the same in both</li>\n</ul>\n' +
  '<h2 id="did-not-fit">Did not fit</h2>\n<ul>\n<li>Nothing.</li>\n</ul>\n';
const cut = A.cutAnswer(LIST), answer = el(cut.html), card = el(b.turnedOut(cut.against));
const tags = c => c.elements.map(e => e.tag + (e.className ? '.' + e.className : '')).join();
const rowsOf = c => c.querySelectorAll('.ar-against .r').map(r => [r.querySelector('.k').textContent, r.querySelector('.t').textContent, r.querySelector('.v').className, r.querySelector('.v').textContent]);
const ROWS = [['You expected', 'the gap is 0.4 cell 2', 'v no', 'not met'], ['Would change your mind', '', 'v no', 'seen'], ['Also checked', 'chance: the interval includes 0', 'v', ''],
              ['', 'measurement error: cannot tell, nothing says how x was measured', 'v q', 'cannot tell'], ['', 'the two halves differ: the same in both', 'v', '']];
check('the part leaves the answer (0312: the answer is what goes to other people): the opening before it and Did not fit after it stand as they were, with nothing between them - no heading, no card, '
  + 'no word of a brief. What it said comes back as the rows of a card: what was expected and what would change the coach\'s mind, each with its verdict; the checks after, the first labelled; a citation '
  + 'stays the chip it was. The card says how it turned out',
  tags(answer) === 'h1,p,h2,ul' && answer.querySelector('h2').textContent === 'Did not fit' && !/against|brief|Expected|chance/i.test(cut.html.replace('For the decision', ''))
  && tags(card) === 'div.ar-against' && card.querySelector('.ar-against .label').textContent === 'How it turned out' && same(rowsOf(card), ROWS)
  && card.querySelector('.ar-against .cite.cell').getAttribute('onclick') === 'x()', [cut.html, cut.against]);
check('the rows are one line of markup with no heading in them, and the card\'s builder adds its label and no more; an answer cut once is cut: a second pass (a chain shown again) changes nothing and finds nothing',
  !/\n/.test(cut.against) && !/<h\d/.test(cut.against) && b.turnedOut('<i>r</i>') === '<div class="ar-against"><div class="label">How it turned out</div><i>r</i></div>'
  && same(A.cutAnswer(cut.html), { html: cut.html, against: '' }) && typeof A.dressAnswer === 'undefined' && typeof b.against === 'undefined');
const verdicts = html => rowsOf(el(b.turnedOut(A.cutAnswer('<h2>Against the brief</h2>' + html).against))).map(r => r[0] + '=' + r[3] + '|' + r[1]);
check('the verdict is read as the engine reads it: "not met" before "met", "not seen" before "seen", cannot tell; at the line\'s start or later in it; none when the line gives none',
  same(verdicts('<ul><li>Expected: met (gap 3)</li><li>Would change their mind: not seen</li></ul>'), ['You expected=met|(gap 3)', 'Would change your mind=not seen|'])
  && same(verdicts('<ul><li>Expected: cannot tell: too few</li><li>What would change their mind - cannot tell</li></ul>'), ['You expected=cannot tell|too few', 'Would change your mind=cannot tell|'])
  && same(verdicts('<ul><li>Expected: the gap of 2 was not met</li><li>Expectation: a gap of 2</li></ul>'), ['You expected=not met|the gap of 2 was not met', 'You expected=|a gap of 2']));
check('the labels are found through the markup a model puts round them: bold, code, a loose list\'s paragraphs; the line\'s own markup stays',
  same(verdicts('<ul><li><p><strong>Expected:</strong> <strong>not met</strong> — gap <em>0.4</em></p></li><li><p><code>Would change their mind:</code> seen</p></li></ul>'),
       ['You expected=not met|gap 0.4', 'Would change your mind=seen|'])
  && el(b.turnedOut(A.cutAnswer('<h2>Against the brief</h2><ul><li><strong>Expected:</strong> met, gap <em>3</em></li></ul>').against)).querySelector('.t em').textContent === '3');
const LEVEL3 = A.cutAnswer('<p>Lead.</p><h3 id="x">Against the brief:</h3><p>Expected: met</p><h3>Did not fit</h3>');
check('the part written as plain lines, not a list: one row to a line; the heading at any level, with or without a colon - and the answer goes on at the next heading',
  same(verdicts('\n<p>Expected: met, gap 3<br>Would change their mind: not seen\nchance: fine</p>\n'), ['You expected=met|gap 3', 'Would change your mind=not seen|', 'Also checked=|chance: fine'])
  && LEVEL3.html === '<p>Lead.</p><h3>Did not fit</h3>' && el(b.turnedOut(LEVEL3.against)).querySelector('.ar-against .v.ok').textContent === 'met', LEVEL3);
const TABLE = '<h2>Against the brief</h2>\n<table><tr><td>Expected</td><td>met</td></tr></table>\n<h2>Did not fit</h2>';
const NESTED = '<h2>Against the brief</h2><ul><li>Expected: met<ul><li>a detail</li></ul></li></ul>';
check('a part the rows cannot hold whole - a table, a list inside a list - leaves the answer all the same, and goes as the report wrote it, in one block; a heading with nothing under it goes too, with no '
  + 'rows; an answer without the part is left as it is, whatever it says of what was expected; nothing at all is nothing',
  same(A.cutAnswer(TABLE), { html: '<h2>Did not fit</h2>', against: '<div class="as-is"><table><tr><td>Expected</td><td>met</td></tr></table></div>' })
  && same(A.cutAnswer(NESTED), { html: '', against: '<div class="as-is"><ul><li>Expected: met<ul><li>a detail</li></ul></li></ul></div>' })
  && same(A.cutAnswer('<h2>Answer</h2><p>Expected: met</p>'), { html: '<h2>Answer</h2><p>Expected: met</p>', against: '' })
  && same(A.cutAnswer('<h2>Against the brief</h2>'), { html: '', against: '' }) && same(A.cutAnswer('<p>a</p><h2>Against the brief</h2>\n\n<h2>Next</h2>'), { html: '<p>a</p><h2>Next</h2>', against: '' })
  && same(A.cutAnswer(null), { html: '', against: '' }) && same(A.cutAnswer(undefined), { html: '', against: '' }), [A.cutAnswer(TABLE), A.cutAnswer(NESTED)]);
const FOOT = A.cutAnswer('<h2>Did not fit</h2><p>Nothing.</p><h2>Against the brief</h2><ul><li>Expected: met</li></ul><blockquote><p>Replay reproduced 3 numbers</p></blockquote>');
check('the part at the report\'s end stops at the engine\'s own lines beneath it: they stay in the answer',
  tags(el(FOOT.html)) === 'h2,p,blockquote' && el(FOOT.html).querySelector('blockquote').textContent === 'Replay reproduced 3 numbers' && same(rowsOf(el(b.turnedOut(FOOT.against))), [['You expected', '', 'v ok', 'met']]), FOOT);
// the engine's line at a report's foot, as marked renders it - and as a browser gives it back from a kept answer
const MISSING = '<blockquote>\n<p>CHECK: this report does not say how the result stands against the brief.</p>\n</blockquote>\n';
const REPLAYED = '<blockquote>\n<p>Replay reproduced 3 numbers</p>\n</blockquote>\n';
const silent = A.cutAnswer('<h1>T</h1>\n<p>Lead.</p>\n' + REPLAYED + MISSING), half = A.cutAnswer('<h2>Against the brief</h2><ul><li>chance: fine</li></ul>' + MISSING.replace(/\n/g, '') + REPLAYED);
check('the engine\'s line that the report does not say how the result stands against the brief (0312) leaves the answer with the part - a word of a brief no other reader knows of - and the card says so in '
  + 'one row, after what the part did say; the engine\'s other lines stay where they are, and so does another CHECK. The line the page looks for is the engine\'s own sentence',
  silent.html === '<h1>T</h1>\n<p>Lead.</p>\n' + REPLAYED && same(rowsOf(el(b.turnedOut(silent.against))), [['', 'The report does not say.', 'v', '']])
  && half.html === REPLAYED && same(rowsOf(el(b.turnedOut(half.against))), [['Also checked', 'chance: fine', 'v', ''], ['', 'The report does not say.', 'v', '']])
  && same(A.cutAnswer('<blockquote>\n<p>CHECK: this report cites cell 2.</p>\n</blockquote>\n'), { html: '<blockquote>\n<p>CHECK: this report cites cell 2.</p>\n</blockquote>\n', against: '' })
  && fs.readFileSync(path.join(__dirname, '..', '..', 'analyst', 'session.py'), 'utf8').includes('BRIEF_UNANSWERED = "CHECK: this report does not say how the result stands against the brief."'), [silent, half]);
// an answer kept before 0312: the card stands in it, as the page then made it - a browser gives the markup back as it was written
const KEPT = '<h1>T</h1><p>Lead.</p><div class="ar-against"><div class="label">Against the brief</div>' + cut.against + '</div><h2>Did not fit</h2><ul><li>Nothing.</li></ul>';
const kept = A.cutAnswer(KEPT), bare = A.cutAnswer('<p>a</p><div class="ar-against"><div class="label">Against the brief</div></div><p>b</p>');
check('an answer kept from before (0312) holds the card itself: it leaves the answer whole - its label with it - and its rows are the Brief tab\'s as they stand, the chip in them still a chip; a card '
  + 'without a row leaves no rows; the answer cut is cut for good',
  kept.html === '<h1>T</h1><p>Lead.</p><h2>Did not fit</h2><ul><li>Nothing.</li></ul>' && kept.against === cut.against && same(rowsOf(el(b.turnedOut(kept.against))), ROWS)
  && same(bare, { html: '<p>a</p><p>b</p>', against: '' }) && same(A.cutAnswer(kept.html), { html: kept.html, against: '' }), [kept, bare]);

// ---- on the Brief tab: the rows ride in the brief's own markup, the card stands at the foot of a step whose brief is the one the run was under
const FT = { versions: [{ n: 1, by: 'person', changed: [], brief: { question: 'Is B above A?' } },
                        { n: 2, by: 'architect', why: 'answer', changed: ['expects'], brief: { question: 'Is B above A?', expects: 'B is 2 above A.' } }] };
const tabT = o => el(b.brief(FT, Object.assign({ chain: 71, thread: 7, state: 'run' }, o))).querySelector('.ar-brief');
const withT = tabT({ against: cut.against }), olderT = tabT({ against: cut.against, shown: 1 }), noneT = tabT({});
check('the Brief tab of a run whose report said how it stands against the brief (0312): the rows ride in the brief\'s own markup, as its versions do, and the card is the last thing on the tab - under the '
  + 'brief the run was under. On a step with another brief the rows ride still and no card is shown: it would be read against lines the run was not under. A run that said nothing has neither',
  withT.getAttribute('data-against') === cut.against && withT.elements[withT.elements.length - 1].className === 'ar-against' && withT.querySelectorAll('.ar-against').length === 1
  && same(rowsOf(withT), ROWS) && withT.querySelector('.ar-against .label').textContent === 'How it turned out'
  && olderT.getAttribute('data-against') === cut.against && !olderT.querySelector('.ar-against') && olderT.querySelector('.ar-ver b').textContent === '1 of 2'
  && !noneT.hasAttribute('data-against') && !noneT.querySelector('.ar-against'), withT.outerHTML);

// ------------------------------------------------------------ the Workflow map's mark
check('how a chain\'s question was made: a brief not yet run; framed with the Pathfinder - by its versions while it runs, by its Brief tab once kept; nothing for a typed question',
  A.mark({ status: 'framing', framing: F1 }) === 'not run' && A.mark({ status: 'running', framing: F1, tabContent: '' }) === 'Pathfinder'
  && A.mark({ tabContent: '<div id="tab-brief" class="tab">Brief</div><div id="tab-answer" class="tab active">Answer</div>' }) === 'Pathfinder'
  && A.mark({ tabContent: '<div id="tab-answer" class="tab active">Answer</div>' }) === '' && A.mark({}) === '' && A.mark(null) === '');

// ------------------------------------------------------------ the module on the page
(async () => {
  // the switch
  check('the switch is off until it is set', A.isOn() === false);
  store.architectOn = '1'; A.initialize();
  const sw = $('architectSwitch');
  check('the switch comes back as it was left in this session: lit, pressed', A.isOn() === true && sw.className.includes('on') && sw.getAttribute('aria-pressed') === 'true');
  sw.dispatch('click');
  check('a click turns it off, and that is kept', A.isOn() === false && !sw.classList.contains('on') && sw.getAttribute('aria-pressed') === 'false' && store.architectOn === '0');
  sw.dispatch('click');

  // a typed question opens its brief
  responses.push({ chain_id: 70, thread_id: 7, parentChainId: null, queryText: 'A first question', tabContent: '<div id="tab-answer" class="tab active">Answer</div>', contentOutput: '', streamOutput: '' });
  currentResponseIndex = 0; currentData.chain_id = 70; currentData.thread_id = 7;
  $('queryInput').value = 'Is B above A?';
  answers['/architect/open'] = body => [200, { thread_id: 7, chain_id: 71, parent_chain_id: 70, framing: F1 }];
  let reply;                                       // the Pathfinder's reply, held until the test lets it go
  const held = () => { answers['/architect/say'] = () => new Promise(r => { reply = r; }); };
  // the exchange's stream as the server sends it: the model's own traffic, heartbeats, then the route's closing message
  const stream = last => '{"text": "{\\"say\\": ", "chain_id": 71}\n\n{"thought": "x", "chain_id": 71}\n\n' + JSON.stringify({ architect: last }) + '\n';
  const pane = () => $('streamOutput').querySelectorAll('.ar-msg').map(m => m.className.replace('ar-msg ', '') + '|' + m.textContent);
  held();
  A.open('Is B above A?'); await tick();
  const entry = responses[1];
  check('a question typed with the switch on: the server is asked to open its brief with the question and the chain on screen; the brief is a chain of its own, where the question was asked, and the page moves to it',
    same(calls[0], ['/architect/open', { question: 'Is B above A?', thread_id: 7, chain_id: 70 }]) && responses.length === 2 && currentResponseIndex === 1
    && entry.status === 'framing' && entry.chain_id === 71 && entry.thread_id === 7 && entry.parentChainId === 70 && entry.queryText === 'Is B above A?' && same(entry.framing, F1)
    && currentData.chain_id === 71 && $('queryInput').value === '', [calls[0], entry]);
  doc.dispatch('click', $('contentOutput').querySelector('[data-ar="more"]'));
  check('the Pathfinder takes its first turn at once: asked with the brief\'s thread and chain, no words of the coach\'s, and the step in use - every request names it (0316); while it replies the pane says it is reading, the composer is held and says why, and the brief takes no change',
    same(calls[1], ['/architect/say', { thread_id: 7, chain_id: 71, text: null, step: 1 }]) && same(pane(), ['you|YouIs B above A?', 'arch wait|Pathfinderreading…'])
    && same(locks[locks.length - 1], ['lock', 'The Pathfinder is replying']) && $('queryInput').disabled === true && doc.body.classList.contains('ar-framing') && A.framingInView() === true
    && !$('contentOutput').querySelector('.editing') && !$('contentOutput').querySelector('.ar-kinds'), [calls[1], pane(), locks.slice(-2)]);
  const F1T = { versions: F1.versions, turns: [ASK], calls: 1 };
  reply([200, stream({ framing: F1T })]); await tick();
  check('its reply, the last message of the stream: the conversation and the brief are the record\'s again - its question in the pane with its choices; the composer is the conversation\'s, its own words kept for later',
    same(entry.framing, F1T) && same(pane(), ['you|YouIs B above A?', 'arch|Pathfinder⌘What will you do differently depending on the answer?Keep one armKeep <both>'])
    && same(locks[locks.length - 1], ['unlock']) && $('queryInput').disabled === false && $('queryInput').placeholder === 'Answer, or say what to change'
    && $('queryInput').getAttribute('data-placeholder') === 'Enter your query here' && toasts.length === 0, [entry.framing, pane(), $('queryInput').placeholder]);
  check('the brief on screen: the left pane says Pathfinder, brief v1, with the question; one tab, Brief, drawn from the versions and open to changes',
    $('streamOutput').querySelector('.sp-strip').textContent === 'Pathfinder' && $('streamOutput').querySelector('.ar-msg.you').textContent === 'YouIs B above A?'
    && $('tabContainer').querySelectorAll('.tab').length === 1 && $('tabContainer').querySelector('#tab-brief.tab.active').textContent === 'Brief'
    && $('contentOutput').querySelector('#content-brief.tab-content.active .ar-brief').getAttribute('data-state') === 'framing' && $('contentOutput').querySelector('[data-ar="start"]'), $('contentOutput').innerHTML);
  answers['/architect/open'] = [500, { error: 'The brief could not be opened: disk' }];
  A.open('Another question'); await tick();
  answers['/architect/open'] = 'down';
  A.open('Another question'); await tick();
  check('a brief the server did not open: the reason is said, no chain is made', responses.length === 2 && toasts.slice(-2).join('|') === 'The brief could not be opened: disk|The brief could not be opened: the server could not be reached.', toasts);

  // a line is changed where it stands
  const brief = () => $('contentOutput').querySelector('.ar-brief');
  // a part the brief does not hold is added through the one control: its list opened, the part chosen - its line is then open for typing
  const addPart = path => { doc.dispatch('click', brief().querySelector('[data-ar="more"]')); doc.dispatch('click', brief().querySelector('.ar-kinds [data-ar="add"][data-path="' + path + '"]')); return lineOf(brief(), path); };
  const serve = () => { answers['/architect/brief'] = body => { const f = JSON.parse(JSON.stringify(entry.framing)); f.versions.push({ n: f.versions.length + 1, by: 'person', changed: body.changed, brief: body.brief }); delete f.at; return [200, { framing: f }]; }; };      // a version made is the one in use
  serve();
  doc.dispatch('click', brief().querySelector('[data-ar="more"]'));
  const listed = kindsOf(brief()) + '|' + brief().getAttribute('data-adds');
  doc.dispatch('click', brief().querySelector('[data-ar="more"]'));
  const shut = !brief().querySelector('.ar-kinds') && brief().getAttribute('data-adds') !== '1';
  doc.dispatch('click', brief().querySelector('[data-ar="more"]'));
  doc.dispatch('click', brief().querySelector('.ar-kinds [data-ar="add"][data-path="decision"]'));
  let field = lineOf(brief(), 'decision').querySelector('textarea.ar-input');
  check('a part added through the one control (0308): a click opens its list - every part the brief does not hold - a second click shuts it, a third opens it again - and the part chosen stands under '
    + 'its heading, its line open for typing: the field empty, with Keep and Cancel; the list is shut again',
    listed === KINDS + '|1' && shut && field && field.textContent === '' && lineOf(brief(), 'decision').classList.contains('editing') && h3s(brief()) === 'What it is for' && !brief().querySelector('.ar-kinds')
    && lineOf(brief(), 'decision').querySelectorAll('[data-ar]').map(x => x.getAttribute('data-ar')).join() === 'keep,cancel', lineOf(brief(), 'decision').outerHTML);
  field.value = '  keep one   arm ';
  doc.dispatch('click', lineOf(brief(), 'decision').querySelector('[data-ar="keep"]')); await tick();
  check('Keep: the server is sent the brief as it would stand and the part changed; it answers with one more version',
    same(calls[calls.length - 1], ['/architect/brief', { thread_id: 7, chain_id: 71, brief: { question: 'Is B above A?', decision: 'keep one arm' }, changed: ['decision'], step: 1 }]) && entry.framing.versions.length === 2, calls[calls.length - 1]);
  check('the tab shows the new version, "2 of 2", the changed line marked and no longer being typed',
    brief().querySelector('.ar-ver b').textContent === '2 of 2' && !brief().querySelector('.why') && lineOf(brief(), 'decision').className === 'ar-line changed'
    && lineOf(brief(), 'decision').querySelector('.tx').textContent === 'keep one arm', brief().outerHTML);
  let n = calls.length;
  doc.dispatch('click', lineOf(brief(), 'decision').querySelector('.pen'));
  field = lineOf(brief(), 'decision').querySelector('.ar-input');
  const prefilled = field.textContent;
  field.value = 'keep one arm';
  doc.dispatch('keydown', field, { key: 'Enter' }); await tick();
  check('the pencil opens the line with its text; kept unchanged, nothing is sent and no version is made', prefilled === 'keep one arm' && calls.length === n && entry.framing.versions.length === 2 && !brief().querySelector('.editing'));
  field = addPart('thinks').querySelector('.ar-input'); field.value = 'B is better';
  const esc = doc.dispatch('keydown', field, { key: 'Escape' }); await tick();
  check('a part being added and given up - Escape - is gone again: nothing sent, no heading left behind, the list shut',
    calls.length === n && esc.defaulted === true && !brief().querySelector('.editing') && !lineOf(brief(), 'thinks') && h3s(brief()) === 'What it is for' && !brief().querySelector('.ar-kinds'));
  field = addPart('would_change').querySelector('.ar-input'); field.value = 'a gap under 1';
  const stillHeaded = h3s(brief()) === 'What it is for|What would change your mind';
  const composing = doc.dispatch('keydown', field, { key: 'Enter', isComposing: true }); await tick();
  const shifted = doc.dispatch('keydown', field, { key: 'Enter', shiftKey: true }); await tick();
  const whileComposing = calls.length;
  const enter = doc.dispatch('keydown', field, { key: 'Enter' }); await tick();
  check('Enter keeps the line (not while a character is still being composed, and Shift+Enter is a new line); the line stands under its heading while it is typed',
    stillHeaded && whileComposing === n && !composing.defaulted && !shifted.defaulted && enter.defaulted === true && calls.length === n + 1 && same(calls[n][1].changed, ['would_change'])
    && lineOf(brief(), 'would_change').querySelector('.tx').textContent === 'a gap under 1' && entry.framing.versions.length === 3, calls[n]);

  // lines of a list; another line clicked while one is being typed
  addPart('rests_on.+').querySelector('.ar-input').value = 'B looked better';
  doc.dispatch('click', brief().querySelector('[data-ar="more"]')); await tick();      // the control clicked while a line is being typed: the line is kept first, then the list opens
  const listAfter = kindsOf(brief()).split('|').slice(0, 3).join('|');
  doc.dispatch('click', brief().querySelector('.ar-kinds [data-ar="add"][data-path="also_check.+"]'));
  check('the one control clicked while a line is being typed: the line is kept first - a line of the coach\'s own on the list - then the list opens on the brief as it then stands, and the part chosen is open for typing',
    same(calls[calls.length - 1][1].brief.rests_on, [{ text: 'B looked better', source: 'person', mark: '' }]) && same(calls[calls.length - 1][1].changed, ['rests_on.0'])
    && listAfter === 'thinks=What you think|rests_on.+=Why you think so|expects=What you expect to see'
    && lineOf(brief(), 'rests_on.0').className === 'ar-line changed' && lineOf(brief(), 'also_check.+').classList.contains('editing') && brief().querySelectorAll('.editing').length === 1, brief().outerHTML);
  lineOf(brief(), 'also_check.+').querySelector('.ar-input').value = 'luck';
  doc.dispatch('click', lineOf(brief(), 'also_check.+').querySelector('[data-ar="keep"]')); await tick();
  addPart('rests_on.+').querySelector('.ar-input').value = 'a second thing';
  doc.dispatch('keydown', lineOf(brief(), 'rests_on.+').querySelector('.ar-input'), { key: 'Enter' }); await tick();
  check('the lists grow a line at a time, each under the last, and no empty line waits under them', same(entry.framing.versions[entry.framing.versions.length - 1].brief.rests_on.map(a => a.text), ['B looked better', 'a second thing'])
    && same(entry.framing.versions[entry.framing.versions.length - 1].brief.also_check, [{ text: 'luck' }]) && !lineOf(brief(), 'rests_on.+') && !lineOf(brief(), 'also_check.+'));
  // the first line emptied while the second is clicked: the first goes, and the pencil opens the line that was second
  doc.dispatch('click', lineOf(brief(), 'rests_on.0').querySelector('.pen'));
  lineOf(brief(), 'rests_on.0').querySelector('.ar-input').value = '';
  doc.dispatch('click', lineOf(brief(), 'rests_on.1').querySelector('.pen')); await tick();
  check('a line kept empty is left out; the line clicked meanwhile is the one that opens, under its new place',
    same(calls[calls.length - 1][1].brief.rests_on.map(a => a.text), ['a second thing']) && same(calls[calls.length - 1][1].changed, ['rests_on'])
    && lineOf(brief(), 'rests_on.0').classList.contains('editing') && lineOf(brief(), 'rests_on.0').querySelector('.ar-input').textContent === 'a second thing', brief().outerHTML);
  doc.dispatch('click', lineOf(brief(), 'rests_on.0').querySelector('[data-ar="cancel"]'));
  n = calls.length;
  doc.dispatch('click', lineOf(brief(), 'also_check.0').querySelector('.drop')); await tick();
  check('Cancel leaves the line as it was; the cross leaves a line out at once', !brief().querySelector('.editing') && calls.length === n + 1 && !('also_check' in calls[n][1].brief) && same(calls[n][1].changed, ['also_check'])
    && !lineOf(brief(), 'also_check.0') && h3s(brief()).indexOf('Other explanations to test') < 0);
  // a cross clicked while another line is being typed: the typed line is not lost
  addPart('also_check.+').querySelector('.ar-input').value = 'the season';
  n = calls.length;
  doc.dispatch('click', lineOf(brief(), 'rests_on.0').querySelector('.drop')); await tick();
  check('a cross clicked while another line is being typed: the typed line is kept first, then the other is left out - two versions, nothing lost',
    calls.length === n + 2 && same(calls[n][1].changed, ['also_check.0']) && same(calls[n][1].brief.also_check, [{ text: 'the season' }]) && calls[n][1].brief.rests_on.length === 1
    && same(calls[n + 1][1].changed, ['rests_on']) && !('rests_on' in calls[n + 1][1].brief) && same(calls[n + 1][1].brief.also_check, [{ text: 'the season' }])
    && lineOf(brief(), 'also_check.0').querySelector('.tx').textContent === 'the season' && !lineOf(brief(), 'rests_on.0') && h3s(brief()).indexOf('Why you think so') < 0, [calls[n], calls[n + 1]]);

  // the question
  doc.dispatch('click', brief().querySelector('h1 .pen'));
  const questionBound = brief().querySelector('h1 .ar-input').getAttribute('maxlength');
  brief().querySelector('h1 .ar-input').value = 'Is B above A, on x?';
  doc.dispatch('keydown', brief().querySelector('h1 .ar-input'), { key: 'Enter' }); await tick();
  check('the question is changed like any line, in a field with the question\'s own bound: the chain\'s own text follows, in the title and the map\'s label; the pane\'s first card keeps it as it was first asked',
    questionBound === '4000' && calls[calls.length - 1][1].brief.question === 'Is B above A, on x?' && entry.queryText === 'Is B above A, on x?' && brief().querySelector('h1 .tx').textContent === 'Is B above A, on x?'
    && brief().querySelector('h1').className === 'ar-line ar-q changed' && $('streamOutput').querySelector('.ar-msg.you').textContent === 'You' + entry.framing.versions[0].brief.question
    && entry.framing.versions[0].brief.question !== 'Is B above A, on x?', $('streamOutput').querySelector('.ar-msg.you').textContent);

  // a change the server does not keep
  const versions = entry.framing.versions.length;
  answers['/architect/brief'] = [409, { error: 'This brief can no longer be changed: its analysis has started.' }];
  addPart('thinks').querySelector('.ar-input').value = 'B is better';
  doc.dispatch('keydown', lineOf(brief(), 'thinks').querySelector('.ar-input'), { key: 'Enter' }); await tick();
  const refused = toasts[toasts.length - 1] === 'This brief can no longer be changed: its analysis has started.' && lineOf(brief(), 'thinks').classList.contains('editing') && entry.framing.versions.length === versions;
  answers['/architect/brief'] = 'down';
  doc.dispatch('keydown', lineOf(brief(), 'thinks').querySelector('.ar-input'), { key: 'Enter' }); await tick();
  check('a change the server does not keep: the reason is said, the line stays open with what was typed, no version is made - also when the server cannot be reached',
    refused && toasts[toasts.length - 1] === 'The change was not kept: the server could not be reached.' && lineOf(brief(), 'thinks').classList.contains('editing') && entry.framing.versions.length === versions, toasts.slice(-2));
  serve();
  doc.dispatch('keydown', lineOf(brief(), 'thinks').querySelector('.ar-input'), { key: 'Enter' }); await tick();

  // the steps: the arrows show another one, and what is done next goes on from it
  const before0 = entry.framing.versions.length;
  n = calls.length;
  doc.dispatch('click', brief().querySelector('[data-step="-1"]'));
  const back = brief();
  check('the arrow back shows the step before (0316; the version, 0308): which it is of how many, its own lines with their pencils, and Start analysis naming it. It is the one in use on the page at '
    + 'once - the framing names its version - and nothing is sent',
    back.querySelector('.ar-ver b').textContent === (before0 - 1) + ' of ' + before0 && back.getAttribute('data-shown') === String(before0 - 1) && !lineOf(back, 'thinks') && lineOf(back, 'decision').querySelector('.pen')
    && back.querySelector('[data-ar="start"]').textContent === 'Start analysis from step ' + (before0 - 1) && calls.length === n && entry.framing.at === before0 - 1);
  doc.dispatch('click', lineOf(brief(), 'decision').querySelector('.pen'));
  lineOf(brief(), 'decision').querySelector('.ar-input').value = 'keep the better arm';
  doc.dispatch('keydown', lineOf(brief(), 'decision').querySelector('.ar-input'), { key: 'Enter' }); await tick();
  const last = entry.framing.versions.length;
  check('a line changed on an earlier step (0316; 0308): the server is sent the brief that stood there with the change - what the step after it held is not in it - and the step, and the version it '
    + 'answers with is the last, on screen',
    same(calls[calls.length - 1][1].changed, ['decision']) && calls[calls.length - 1][1].step === before0 - 1 && calls[calls.length - 1][1].brief.decision === 'keep the better arm' && !('thinks' in calls[calls.length - 1][1].brief)
    && last === before0 + 1 && brief().querySelector('.ar-ver b').textContent === last + ' of ' + last && brief().querySelector('[data-ar="start"]').textContent === 'Start analysis', calls[calls.length - 1]);
  doc.dispatch('click', brief().querySelector('[data-step="-1"]'));
  const withThinks = !!lineOf(brief(), 'thinks');
  doc.dispatch('click', lineOf(brief(), 'decision').querySelector('.pen'));
  const olderText = lineOf(brief(), 'decision').querySelector('.ar-input').textContent;
  doc.dispatch('keydown', lineOf(brief(), 'decision').querySelector('.ar-input'), { key: 'Escape' });
  const olderStill = brief().querySelector('.ar-ver b').textContent + '|' + !brief().querySelector('.editing');
  doc.dispatch('click', brief().querySelector('[data-step="1"]'));
  check('the arrows step both ways: back to the step that held the other line - there the pencil opens a line with the text that stood there, and Escape leaves that step on screen - and forward to the last',
    withThinks && olderText === 'keep one arm' && olderStill === (last - 1) + ' of ' + last + '|true' && brief().querySelector('.ar-ver b').textContent === last + ' of ' + last && !lineOf(brief(), 'thinks'),
    [olderText, olderStill]);

  // leaving and coming back; the composer
  const lockCount = locks.length;
  currentResponseIndex = 0; loadResponseContent(responses[0]); updateNavigationButtons();
  check('another chain on screen: the composer is its own again, with its own words; the page\'s mark gone', same(locks[locks.length - 1], ['unlock']) && locks.length === lockCount + 1 && !doc.body.classList.contains('ar-framing')
    && A.framingInView() === false && $('queryInput').placeholder === 'Enter your query here' && $('queryInput').getAttribute('data-placeholder') == null);
  updateNavigationButtons();
  check('the Pathfinder lifts only its own hold: a second look at a plain chain touches nothing', locks.length === lockCount + 1);
  queryRunning = true;
  currentResponseIndex = 1; loadResponseContent(entry); updateNavigationButtons();
  check('back on the brief while another chain runs: drawn again from its versions, at the last one, with its conversation; the composer is held and says why - and that chain\'s Stop stays within reach',
    brief().querySelector('.ar-ver b').textContent === last + ' of ' + last && pane().length === 2 && same(locks[locks.length - 1], ['lock', 'Another analysis is running. Wait for it to end, or stop it.'])
    && $('queryInput').disabled === true && $('submitQuery').disabled === false);
  const before = calls.length;
  doc.dispatch('click', $('streamOutput').querySelector('.ar-choice')); await tick();
  check('nothing is said to the Pathfinder while another analysis runs: a choice clicked sends nothing, and the page says why', calls.length === before && toasts[toasts.length - 1] === 'Another analysis is running. Wait for it to end, or stop it.');

  // Start analysis
  doc.dispatch('click', brief().querySelector('[data-ar="start"]')); await tick();
  check('Start analysis while another analysis runs: said in plain words, nothing started', submitted.length === 0 && toasts[toasts.length - 1] === 'Another analysis is running. Wait for it to end, or stop it.');
  queryRunning = false;
  addPart('expects').querySelector('.ar-input').value = 'B above A by 2';
  doc.dispatch('click', brief().querySelector('[data-ar="start"]')); await tick();
  check('Start analysis with a line still being typed: the line is kept first; then the question of the step on screen is sent to be read as the Analyst will read it (0313) - the thread, the chain, '
    + 'the step; then the page\'s own send starts this chain, from that step, which the send is told',
    calls[calls.length - 2][0] === '/architect/brief' && calls[calls.length - 2][1].brief.expects === 'B above A by 2'
    && same(calls[calls.length - 1], ['/architect/ready', { thread_id: 7, chain_id: 71, step: entry.framing.versions.length }])
    && submitted.length === 1 && submitted[0].framed === entry && Object.keys(submitted[0]).join() === 'framed,step'
    && submitted[0].step === entry.framing.versions.length && !('at' in entry.framing)
    && entry.framing.versions[entry.framing.versions.length - 1].brief.expects === 'B above A by 2', submitted);
  // what the send does next: the chain runs, the framing folds, the Brief tab stays
  entry.status = 'running';
  ['streamOutput', 'tabContainer', 'contentOutput'].forEach(id => { $(id).innerHTML = ''; });      // as the send clears the panes for the run
  A.started(entry);
  const stays = el(tabs[0][1]).querySelector('.ar-brief');
  check('the analysis begins: the framing is one row above the run, which names the step it started from; the Brief tab is made again to be read, with its framing',
    rows.length === 1 && el(rows[0]).querySelector('details.ar-fold .kind').textContent === 'brief · step ' + entry.framing.versions.length && tabs[0][0] === 'brief' && stays.getAttribute('data-state') === 'run'
    && !stays.querySelector('.pen') && !stays.querySelector('[data-ar="start"]') && same(JSON.parse(stays.getAttribute('data-framing')), entry.framing), rows);
  // a branch of this analysis (branch.js) runs under the same brief: its chain is given the framing as the Brief tab keeps it, with its own ids and the question
  const r0 = rows.length, t0 = tabs.length;
  A.started({ framing: JSON.parse(stays.getAttribute('data-framing')), chain_id: 72, thread_id: 7, queryText: entry.queryText });
  const ofBranch = { fold: el(rows[r0]).querySelector('details.ar-fold'), tab: el(tabs[t0][1]).querySelector('.ar-brief') };
  rows.length = r0; tabs.length = t0;
  check('a branch of a framed analysis: from the framing its Brief tab keeps, the new chain and the question, the fold stands above the branch\'s run and the Brief tab is made for that chain, to be read',
    ofBranch.fold.querySelector('.kind').textContent === 'brief · step ' + entry.framing.versions.length && ofBranch.fold.querySelector('.peek').textContent === entry.queryText
    && ofBranch.tab.getAttribute('data-state') === 'run' && ofBranch.tab.getAttribute('data-chain') === '72' && same(JSON.parse(ofBranch.tab.getAttribute('data-framing')), entry.framing));
  updateNavigationButtons();
  check('the composer is free once the brief runs (its send is the run\'s Stop)', same(locks[locks.length - 1], ['unlock']));
  // the server did not start it
  A.notStarted(entry, 'Network response was not ok');
  check('an analysis the server did not start: the chain is a brief again, drawn as it stood; the reason is said',
    reverted[0] === entry && entry.status === 'framing' && brief().getAttribute('data-state') === 'framing' && brief().querySelector('[data-ar="start"]') && pane().length === 2
    && same(locks[locks.length - 1], ['unlock']) && $('queryInput').placeholder === 'Answer, or say what to change' && toasts[toasts.length - 1] === 'The analysis did not start: Network response was not ok');
  const quiet = toasts.length; A.notStarted(entry);
  check('refused for the balance, the page has its own dialog: nothing more is said', toasts.length === quiet);
  // Start analysis with an earlier step on screen: the send is told which, and the chain is that step's from then on
  const lastNow = entry.framing.versions.length, textNow = entry.queryText;
  const asksOther = lastNow - entry.framing.versions.slice().reverse().findIndex(v => v.brief.question !== textNow);      // the last version that asks another question
  for (let k = lastNow; k > asksOther; k--) doc.dispatch('click', brief().querySelector('[data-step="-1"]'));
  doc.dispatch('click', brief().querySelector('[data-ar="start"]')); await tick();
  entry.status = 'running';
  A.started(entry);
  const olderRun = { sent: submitted.length, step: submitted[submitted.length - 1].step, at: entry.framing.at, text: entry.queryText, was: entry.framing.versions[asksOther - 1].brief.question,
                     tab: el(tabs[tabs.length - 1][1]).querySelector('.ar-ver b').textContent, fold: el(rows[rows.length - 1]).querySelector('.kind').textContent, calls: calls.length };
  A.notStarted(entry);
  const olderBack = brief().querySelector('.ar-ver b').textContent + '|' + brief().querySelector('[data-ar="start"]').textContent;
  entry.framing = A.go(entry.framing, lastNow); entry.queryText = textNow; loadResponseContent(entry); updateNavigationButtons();      // the last step on screen again, for what follows
  check('Start analysis with an earlier step on screen (0316; a version, 0308) - one that asks another question than the last: nothing is sent to the brief\'s own route - the send is told the step, the '
    + 'chain\'s framing names its version as the one in use and the chain\'s question is the one that stood there; the run\'s Brief tab and the fold above it show that step; an analysis the server '
    + 'did not start leaves the brief on it',
    asksOther < lastNow && olderRun.was !== textNow
    && same(olderRun, { sent: 2, step: asksOther, at: asksOther, text: olderRun.was, was: olderRun.was, tab: asksOther + ' of ' + lastNow, fold: 'brief · step ' + asksOther, calls: olderRun.calls })
    && olderBack === asksOther + ' of ' + lastNow + '|Start analysis from step ' + asksOther && !('at' in entry.framing), [asksOther, lastNow, olderRun, olderBack]);

  // the conversation: a choice clicked, an answer typed, a reply that does not come
  const latest = () => entry.framing.versions[entry.framing.versions.length - 1];
  const answered = (said, text, version, more) => { const f = JSON.parse(JSON.stringify(entry.framing));
    if (version) { f.versions.push(Object.assign({ n: f.versions.length + 1, by: 'architect', why: 'answer' }, version)); delete f.at; }
    f.turns = f.turns.concat([{ who: 'person', text: said }, Object.assign({ who: 'architect', text, v: f.versions.length, cost: 0.02, call: (f.calls || 0) + 1 }, more || {})]); f.calls = (f.calls || 0) + 1; return f; };
  held();
  doc.dispatch('click', $('streamOutput').querySelector('.ar-choice')); await tick();
  const sent = calls[calls.length - 1];
  doc.dispatch('click', lineOf(brief(), 'decision').querySelector('.pen'));
  check('a choice clicked is the coach\'s answer: said to the Pathfinder as it reads, shown at once as the coach\'s message; the choices are gone, the Pathfinder is reading, the composer is held, the brief takes no change',
    same(sent, ['/architect/say', { thread_id: 7, chain_id: 71, text: 'Keep one arm', step: entry.framing.versions.length }]) && same(pane().slice(-2), ['you|YouKeep one arm', 'arch wait|Pathfinderreading…'])
    && $('streamOutput').querySelectorAll('.ar-choice').length === 0 && same(locks[locks.length - 1], ['lock', 'The Pathfinder is replying']) && !brief().querySelector('.editing'), [sent, pane()]);
  const was = entry.framing.versions.length;
  reply([200, stream({ framing: answered('Keep one arm', 'What do you expect to see?', { changed: ['decision'], brief: Object.assign({}, latest().brief, { decision: 'Keep one arm' }) }) })]); await tick();
  check('the reply: the brief shows the version the Pathfinder made from the answer, the changed line marked; the pane has both messages and what the calls have cost; the composer is the conversation\'s again',
    entry.framing.versions.length === was + 1 && brief().querySelector('.ar-ver b').textContent === (was + 1) + ' of ' + (was + 1) && !brief().querySelector('.why')
    && lineOf(brief(), 'decision').className === 'ar-line changed' && lineOf(brief(), 'decision').querySelector('.tx').textContent === 'Keep one arm'
    && same(pane().slice(-2), ['you|YouKeep one arm', 'arch|Pathfinder⌘What do you expect to see?']) && $('streamOutput').querySelector('.sp-strip').textContent === 'Pathfinder$0.02'
    && same(locks[locks.length - 1], ['unlock']) && $('queryInput').placeholder === 'Answer, or say what to change', [pane(), $('streamOutput').querySelector('.sp-strip').textContent]);
  // a reply that words the question (0308): the Pathfinder writes it at once, and the chain's own text follows
  const asked1 = entry.framing.versions[0].brief.question;
  held();
  A.tell('Yes, like that'); await tick();
  reply([200, stream({ framing: answered('Yes, like that', 'I have put that into the question.\n\nLook at how far apart the two end.', { changed: ['question'], brief: Object.assign({}, latest().brief, { question: 'Is B above A, on plot means?' }) },
                                         { wording: 'Is B above A, on plot means?' }) })]); await tick();
  check('a reply that words the question (0308): the Pathfinder\'s version holds it, the question\'s box shows it, marked as changed, and the chain\'s own text follows; under the message a row says the '
    + 'question was updated, and at which step - nothing is there to take; the conversation still opens on the question as it was first asked, and a message keeps its lines',
    entry.queryText === 'Is B above A, on plot means?' && brief().querySelector('h1 .tx').textContent === 'Is B above A, on plot means?' && brief().querySelector('h1').className === 'ar-line ar-q changed'
    && $('streamOutput').querySelectorAll('.sp-row').map(r => r.textContent).slice(-1)[0] === '✓QUESTIONupdatedstep ' + entry.framing.versions.length
    && !$('streamOutput').querySelector('.ar-wording') && !$('streamOutput').querySelector('[data-ar="use"]') && !brief().querySelector('.ar-wording') && pane()[0] === 'you|You' + asked1 && asked1 !== entry.queryText
    && pane()[pane().length - 1] === 'arch|Pathfinder⌘I have put that into the question.\n\nLook at how far apart the two end.', [entry.queryText, pane()[0], pane()[pane().length - 1]]);
  // an answer typed, with a line of the brief still open: the line is kept first, then the answer is said
  serve();
  addPart('fixed.period').querySelector('.ar-input').value = 'this season';
  $('queryInput').value = 'B above A by 3';
  held(); n = calls.length;
  A.tell('  B above A by 3 '); await tick();
  check('an answer typed in the composer while a line of the brief is being typed: the line is kept first, as a version of the coach\'s; then the answer is said, the composer emptied',
    calls.length === n + 2 && calls[n][0] === '/architect/brief' && calls[n][1].brief.fixed.period === 'this season' && same(calls[n + 1], ['/architect/say', { thread_id: 7, chain_id: 71, text: 'B above A by 3', step: entry.framing.versions.length }])
    && $('queryInput').value === '' && latest().by === 'person' && h3s(brief()).indexOf('Period') >= 0 && pane()[pane().length - 2] === 'you|YouB above A by 3', calls.slice(n));
  const stood = JSON.stringify(entry.framing);
  reply([200, stream({ error: 'The Pathfinder\'s reply could not be read (it holds no JSON object).' })]); await tick();
  check('a reply that could not be kept: the reason is said, the brief and the conversation stand as they did, and what was typed is back in the composer',
    toasts[toasts.length - 1] === 'The Pathfinder\'s reply could not be read (it holds no JSON object).' && JSON.stringify(entry.framing) === stood && pane()[pane().length - 1] === 'arch|Pathfinder⌘I have put that into the question.\n\nLook at how far apart the two end.'
    && $('queryInput').value === 'B above A by 3' && $('queryInput').disabled === false, [toasts.slice(-1), pane().slice(-2)]);
  $('queryInput').value = '';
  answers['/architect/say'] = [403, { error: 'authorization_failed', message: 'You need $0.010 per query but your balance is $0.00. Please add funds to continue.', reason: 'insufficient_funds' }];
  A.tell('again'); await tick();
  const refusedSay = toasts[toasts.length - 1];
  answers['/architect/say'] = 'down';
  A.tell('again'); await tick();
  answers['/architect/say'] = [200, '{"routine_error": "something went wrong: boom"}\n'];
  A.tell('again'); await tick();
  n = calls.length;
  A.tell('   '); await tick();
  check('an exchange refused for the balance says the server\'s words; a server that cannot be reached, or a stream that ends on its own failure, is said too; nothing typed says nothing',
    refusedSay === 'You need $0.010 per query but your balance is $0.00. Please add funds to continue.' && toasts[toasts.length - 2] === 'The Pathfinder did not reply: the server could not be reached.'
    && toasts[toasts.length - 1] === 'something went wrong: boom' && calls.length === n && JSON.stringify(entry.framing) === stood, toasts.slice(-3));
  answers['/architect/say'] = [200, '{"text": "{\\"say\\": \\"What", "chain_id": 71}\n{"error": "Provider error 402: the provider account is out of credit.", "chain_id": 71}\n'];
  A.tell('again'); await tick();
  const cutShort = toasts[toasts.length - 1];
  answers['/architect/say'] = [200, '{"text": "{\\"say\\": \\"What", "chain_id": 71}\n\n'];
  A.tell('again'); await tick();
  const onlyTraffic = toasts[toasts.length - 1];
  const quietly = toasts.length;
  answers['/architect/say'] = [200, '{"error": "The model connection dropped mid-answer; re-asking the model in 5s [1/3].", "chain_id": 71}\n' + JSON.stringify({ architect: { framing: entry.framing } }) + '\n'];
  A.tell('again'); await tick();
  check('the stream\'s edges: cut short after an error of the model layer\'s, that error is said; the model\'s text as it arrives is never taken for a reply or a reason; an error on the way that the call got past says nothing - the closing message is what counts',
    cutShort === 'Provider error 402: the provider account is out of credit.' && onlyTraffic === 'The Pathfinder did not reply.' && toasts.length === quietly && JSON.stringify(entry.framing) === stood, toasts.slice(-3));
  // a reply that had the data looked up: the round is a row of the conversation, and the Pathfinder goes on at once, with nothing said
  $('queryInput').value = '';
  held(); n = calls.length;
  A.tell('B well above A'); await tick();
  const asking = JSON.parse(JSON.stringify(entry.framing));
  asking.turns = asking.turns.concat([{ who: 'person', text: 'B well above A' }, { who: 'architect', text: 'Checking this against the data.', v: asking.versions.length, cost: 0.01, call: 9 }, CHECK]);
  reply([200, stream({ framing: asking })]); await tick();
  const goesOn = { calls: calls.slice(n), pane: pane().slice(-3), rows: $('streamOutput').querySelectorAll('.sp-row').length, lock: locks[locks.length - 1], choices: $('streamOutput').querySelectorAll('.ar-choice').length };
  const marking = JSON.parse(JSON.stringify(asking));
  marking.versions.push({ n: marking.versions.length + 1, by: 'architect', why: 'check', changed: ['also_check.0', 'rests_on.0'],
                          brief: Object.assign({}, latest().brief, { rests_on: [{ text: 'B looked better', source: 'person', mark: 'does not hold', note: 'rows by arm: A 3 · B 3' }], also_check: [ITS] }) });
  marking.turns.push({ who: 'architect', text: 'One line does not hold. Keep it, or change it?', choices: ['Keep it', 'Change it'], v: marking.versions.length, cost: 0.01, call: 10 });
  reply([200, stream({ framing: marking })]); await tick();
  const line0 = lineOf(brief(), 'rests_on.0');
  check('a reply that had the data looked up: the round is a row under its message, and the Pathfinder is asked again at once with nothing said - the pane says it is reading, the composer stays held, nothing to click',
    same(goesOn.calls, [['/architect/say', { thread_id: 7, chain_id: 71, text: 'B well above A', step: asking.versions.length }], ['/architect/say', { thread_id: 7, chain_id: 71, text: null, step: asking.versions.length }]])
    && same(goesOn.pane, ['you|YouB well above A', 'arch|Pathfinder⌘Checking this against the data.', 'arch wait|Pathfinderreading…']) && goesOn.rows === 2 && goesOn.choices === 0      // the round's row, under the row of the question worded before
    && same(goesOn.lock, ['lock', 'The Pathfinder is replying']), goesOn);
  check('the reply after the round: one more version, made after checking the data - the line with its mark and, in red, the fact beside it; the question whether to keep or change, with its choices; no further call, and the composer is the conversation\'s again',
    calls.length === n + 2 && same(entry.framing, marking) && brief().querySelector('.ar-ver b').textContent === marking.versions.length + ' of ' + marking.versions.length && line0.className === 'ar-line changed'
    && line0.querySelector('.mk.no').textContent === '✕' && line0.querySelector('.fact.no').textContent === 'rows by arm: A 3 · B 3'
    && same($('streamOutput').querySelectorAll('.ar-choice').map(c => c.textContent), ['Keep it', 'Change it']) && $('streamOutput').querySelectorAll('.sp-row').length === 2
    && same(locks[locks.length - 1], ['unlock']) && $('queryInput').value === '' && $('queryInput').placeholder === 'Answer, or say what to change', [calls.slice(n), pane().slice(-2)]);
  // what the Pathfinder proposed: a tick accepts it, another takes the tick back - each a version of the coach's
  serve(); n = calls.length;
  const boxWas = lineOf(brief(), 'also_check.0').querySelector('.tick').className + '|' + lineOf(brief(), 'also_check.0').querySelector('.src').textContent + '|' + lineOf(brief(), 'also_check.0').className;
  doc.dispatch('click', lineOf(brief(), 'also_check.0').querySelector('.tick')); await tick();
  const ticked = { call: calls[n], box: lineOf(brief(), 'also_check.0').querySelector('.tick').className, ver: brief().querySelector('.ar-ver b').textContent, line: lineOf(brief(), 'also_check.0').className, by: latest().by };
  doc.dispatch('click', lineOf(brief(), 'expects').querySelector('.pen'));
  lineOf(brief(), 'expects').querySelector('.ar-input').value = 'B above A by 4';
  doc.dispatch('click', lineOf(brief(), 'also_check.0').querySelector('.tick')); await tick();
  check('the box on what the Pathfinder proposed: a click sends the brief with the line accepted, and the tab shows the new version - the box ticked, the line marked; another click takes the '
    + 'tick back - a line being typed elsewhere kept first, as its own version',
    boxWas === 'tick|Pathfinder|ar-line changed' && same(ticked.call, ['/architect/brief', { thread_id: 7, chain_id: 71, brief: Object.assign({}, marking.versions[marking.versions.length - 1].brief, { also_check: [Object.assign({}, ITS, { accepted: true })] }), changed: ['also_check.0'], step: marking.versions.length }])
    && ticked.box === 'tick on' && ticked.ver === (marking.versions.length + 1) + ' of ' + (marking.versions.length + 1) && ticked.line === 'ar-line changed' && ticked.by === 'person'
    && calls.length === n + 3 && same(calls[n + 1][1].changed, ['expects']) && calls[n + 1][1].brief.expects === 'B above A by 4' && calls[n + 1][1].brief.also_check[0].accepted === true
    && same(calls[n + 2][1].changed, ['also_check.0']) && calls[n + 2][1].brief.also_check[0].accepted === false && calls[n + 2][1].brief.expects === 'B above A by 4'
    && lineOf(brief(), 'also_check.0').querySelector('.tick').className === 'tick' && !brief().querySelector('.editing'), [boxWas, ticked, calls.slice(n + 1)]);
  held(); n = calls.length;
  A.tell('and the other line?'); await tick();
  const again = JSON.parse(JSON.stringify(entry.framing));
  again.turns = again.turns.concat([{ who: 'person', text: 'and the other line?' }, { who: 'architect', text: 'Checking.', v: again.versions.length, call: 11 }, CHECK]);
  reply([200, stream({ framing: again })]); await tick();
  reply([200, stream({ error: 'The Pathfinder\'s reply could not be read (it holds no JSON object).' })]); await tick();
  check('the Pathfinder not going on after a round: the reason is said, and the conversation stands with the round as its last thing - the coach\'s message was taken, so it does not come back into the composer, which is theirs again; nothing is asked a third time',
    calls.length === n + 2 && toasts[toasts.length - 1] === 'The Pathfinder\'s reply could not be read (it holds no JSON object).' && same(entry.framing, again)
    && pane()[pane().length - 1] === 'arch|Pathfinder⌘Checking.' && $('streamOutput').querySelectorAll('.sp-row').length === 3 && $('queryInput').value === '' && same(locks[locks.length - 1], ['unlock']), [calls.slice(n), toasts.slice(-1), pane().slice(-2)]);
  // the Pathfinder replying while the coach looks elsewhere
  $('queryInput').value = '';
  held();
  A.tell('B above A by 3'); await tick();
  n = calls.length;
  A.open('Another question'); await tick();
  const elsewhere = toasts[toasts.length - 1];
  currentResponseIndex = 0; loadResponseContent(responses[0]); updateNavigationButtons();
  const freeThere = same(locks[locks.length - 1], ['unlock']) && $('queryInput').disabled === false && $('queryInput').placeholder === 'Enter your query here';
  reply([200, stream({ framing: answered('B above A by 3', 'The brief is ready: start the analysis, or change a line.', { changed: ['expects'], brief: Object.assign({}, latest().brief, { expects: 'B above A by 3' }) }) })]); await tick();
  const untouched = $('streamOutput').innerHTML === '' && !$('contentOutput').querySelector('.ar-brief');
  currentResponseIndex = 1; loadResponseContent(entry); updateNavigationButtons();
  check('while the Pathfinder replies, another question is not framed - the page says why; the coach can look at another chain, whose composer is its own; the reply lands on its brief, and is there when they come back',
    elsewhere === 'The Pathfinder is replying.' && calls.length === n && freeThere && untouched && pane()[pane().length - 1] === 'arch|Pathfinder⌘The brief is ready: start the analysis, or change a line.'
    && lineOf(brief(), 'expects').querySelector('.tx').textContent === 'B above A by 3' && $('queryInput').placeholder === 'Answer, or say what to change', [elsewhere, freeThere, untouched, pane().slice(-1)]);

  // the saved analyses read in an exchange (0303; 0308): the stream says how far the reading is, Skip, and the Pathfinder goes on with nothing said; what was found
  // is listed under the row and, in full, under the brief; the coach chooses by answering, and the brief then says what it builds on
  {
  const live = liveBody();
  answers['/architect/say'] = live; answers['/architect/skip'] = [200, { skipped: true }];
  n = calls.length;
  const shownGo = entry.framing.versions.length;
  A.tell('Go on.'); await tick();
  live.send('{"thought": "x", "chain_id": 71}\n'); await tick();
  const early = !!$('streamOutput').querySelector('.sp-row.pending');      // the model's own traffic moves nothing
  live.send('{"type": "architect_saved", "chain_id": 71, "read": 0, "of": 12}\n'); await tick();
  const opened = $('streamOutput').querySelector('.sp-row.pending') ? $('streamOutput').querySelector('.sp-row.pending').textContent : '', holds = $('queryInput').placeholder;
  const waitGone = !$('streamOutput').querySelector('.ar-msg.wait');
  live.send('{"type": "architect_saved", "chain_id": 71, "read": 5, "of": 12}\n{"type": "archi'); await tick();
  const mid = $('streamOutput').querySelector('.sp-row.pending .out').textContent;
  doc.dispatch('click', $('streamOutput').querySelector('[data-ar="skip"]')); await tick();
  const skipped = { call: calls[calls.length - 1], off: $('streamOutput').querySelector('[data-ar="skip"]').disabled === true };
  const reading = JSON.parse(JSON.stringify(entry.framing));
  reading.saved = 12;
  reading.turns = reading.turns.concat([{ who: 'person', text: 'Go on.' }, { who: 'architect', text: 'I am looking in your saved analyses.', v: reading.versions.length, cost: 0.01, call: 13 },
                                        Object.assign({}, MEMORY, { v: reading.versions.length })]);
  held();
  live.send('tect_saved", "chain_id": 71, "read": 12, "of": 12}\n' + JSON.stringify({ architect: { framing: reading } }) + '\n'); live.end(); await tick();
  const went = { calls: calls.slice(n), pane: pane().slice(-2), row: $('streamOutput').querySelectorAll('.sp-row').map(r => r.textContent).slice(-1)[0], pending: !!$('streamOutput').querySelector('.sp-row.pending'),
                 left: $('streamOutput').querySelectorAll('.ar-found .it .q').map(x => x.textContent).join('|'), right: brief().querySelectorAll('.ar-memory .it').length, ver: brief().querySelector('.ar-ver b').textContent,
                 built: h3s(brief()).indexOf('Builds on') >= 0 };
  const told = JSON.parse(JSON.stringify(reading));
  told.turns.push({ who: 'architect', text: 'You asked this in spring. Build on it, or go another way?', choices: ['Build on the spring one', 'Go another way'], v: told.versions.length, cost: 0.01, call: 14 });
  reply([200, stream({ framing: told })]); await tick();
  check('a reply that has the saved analyses read: while they are read the pane shows a row in the place of the Pathfinder\'s wait - how many are saved, then how many are read, a line of the stream cut in two '
    + 'taken whole - the held composer says so, and Skip tells the server once; the reading done, its row stands under the Pathfinder\'s message with the analyses found under it, the Brief tab lists them in '
    + 'full under the brief - which has not changed: no version, nothing built on - and the Pathfinder is asked again with nothing said',
    !early && opened === 'SEARCHING MEMORY0 of 12 readSkip' && waitGone && holds === 'Your saved analyses are being read' && mid === '5 of 12 read' && same(skipped, { call: ['/architect/skip', {}], off: true })
    && same(went.calls, [['/architect/say', { thread_id: 7, chain_id: 71, text: 'Go on.', step: shownGo }], ['/architect/skip', {}], ['/architect/say', { thread_id: 7, chain_id: 71, text: null, step: shownGo }]])
    && same(went.pane, ['arch|Pathfinder⌘I am looking in your saved analyses.', 'arch wait|Pathfinderreading…']) && went.row === '✓MEMORY2 analyses found · read 9 of 1241 s' && !went.pending
    && went.left === '2 Mar 2026 · Was B above A in <spring>?|2 Apr 2026 · Synthesis: Two arms' && went.right === 2 && went.ver === shownGo + ' of ' + shownGo && !went.built && same(entry.framing, told)
    && pane()[pane().length - 1] === 'arch|Pathfinder⌘You asked this in spring. Build on it, or go another way?Build on the spring oneGo another way', [opened, mid, skipped, went]);
  // View, in either pane: the saved analysis in a dialog over the page
  answers['/architect/saved/7/8'] = [200, { id: '7/8', when: '2026-03-02T10:00:00Z', question: 'Was B above A in <spring>?', title: 'B led', report: 'B led A by 3 units.', marks: ['picked'], data: { name: 'spring.csv', period: '' }, cells: [] }];
  n = calls.length;
  doc.dispatch('click', $('streamOutput').querySelector('.ar-found [data-ar="open"]')); await tick();
  const shown = { call: calls[calls.length - 1], title: $('savedAnalysisModal').querySelector('.title').textContent, display: $('savedAnalysisModal').style.display, sent: calls.length - n, label: $('streamOutput').querySelector('.ar-found [data-ar="open"]').textContent };
  doc.dispatch('click', $('savedAnalysisModal').querySelector('.ui-dlg-h .x'));
  const closed = $('savedAnalysisModal').style.display;
  doc.dispatch('click', brief().querySelector('.ar-memory [data-ar="open"]')); await tick();
  const fromTab = { call: calls[calls.length - 1], display: $('savedAnalysisModal').style.display, stays: !!brief() && currentResponseIndex === 1 };
  doc.dispatch('click', $('savedAnalysisModal'));
  const beside = $('savedAnalysisModal').style.display;
  answers['/architect/saved/7/8'] = [404, { error: 'This analysis is no longer among your saved ones.' }];
  doc.dispatch('click', brief().querySelector('.ar-memory [data-ar="open"]')); await tick();
  const gone = toasts[toasts.length - 1];
  check('View (0308), under the reading\'s row and on the Brief tab alike: the server is asked for that analysis, and it is shown in a dialog over the page - the brief and the conversation stay where '
    + 'they are - which closes on its cross or on a click beside it; one saved no more says so',
    same(shown, { call: ['/architect/saved/7/8', null], title: 'Was B above A in <spring>?', display: 'flex', sent: 1, label: 'View' }) && closed === 'none'
    && same(fromTab, { call: ['/architect/saved/7/8', null], display: 'flex', stays: true }) && beside === 'none' && gone === 'This analysis is no longer among your saved ones.', [shown, fromTab, gone]);
  // 'build on it', said by a choice: the Pathfinder's reply brings the analysis into the brief; the cross takes it out again
  held(); n = calls.length;
  doc.dispatch('click', $('streamOutput').querySelector('.ar-choice')); await tick();
  const P8 = { thread: '7', run: '8', when: '2026-03-02', question: 'Was B above A in <spring>?', passage: 'B led A by 3 units', where: 'report', accepted: true };
  reply([200, stream({ framing: answered('Build on the spring one', 'Done: the Analyst gets it, and can open it.', { changed: ['saved.0', 'saved.1'],
                                         brief: Object.assign({}, latest().brief, { saved: [P8, Object.assign({}, P8, { passage: 'gap: 3 units', where: 'cell 1' })] }) }) })]); await tick();
  const builtLine = brief().querySelector('.ar-built');
  const builtNow = { said: calls[n], heads: h3s(brief()).split('|').slice(-2).join('|'), line: builtLine.className + '|' + builtLine.querySelector('.tx').textContent, lines: brief().querySelectorAll('.ar-built').length,
                     tags: brief().querySelectorAll('.ar-memory .it').map(i => (i.querySelector('.tag') || {}).textContent || '').join('|'), view: builtLine.querySelector('[data-ar="open"]').textContent };
  serve(); n = calls.length;
  doc.dispatch('click', builtLine.querySelector('[data-ar="unbuild"]')); await tick();
  check('\'build on it\' (0308): the coach\'s choice is said to the Pathfinder like any answer; its reply brings the analysis into the brief - one line under Builds on, however many passages, marked as '
    + 'changed, with View - and the list under the brief marks the analysis as built on. The cross on that line sends the brief without its passages - a version of the coach\'s - and the part is gone, '
    + 'the mark with it; what was found stays listed',
    same(builtNow.said, ['/architect/say', { thread_id: 7, chain_id: 71, text: 'Build on the spring one', step: told.versions.length }])
    && same(builtNow, { said: builtNow.said, heads: 'Builds on|Found in your saved analyses', line: 'ar-line ar-built changed|2 Mar 2026 · Was B above A in <spring>?', lines: 1, tags: 'built on|', view: 'View' })
    && calls.length === n + 1 && same(calls[n][1].changed, ['saved']) && !('saved' in calls[n][1].brief) && latest().by === 'person' && !brief().querySelector('.ar-built') && h3s(brief()).indexOf('Builds on') < 0
    && brief().querySelectorAll('.ar-memory .it').length === 2 && !brief().querySelector('.ar-memory .tag') && !brief().querySelector('[data-ar="look"]') && !brief().querySelector('.ar-memory .tick') && !brief().querySelector('.ar-built .tick'), [builtNow, calls[n]]);
  // the coach goes back to an earlier step and answers from it: the step rides with the message
  const lastB = entry.framing.versions.length;
  doc.dispatch('click', brief().querySelector('[data-step="-1"]'));
  held(); n = calls.length;
  A.tell('From this one, then.'); await tick();
  const fromOlder = { call: calls[n], at: entry.framing.at, shown: brief().querySelector('.ar-ver b').textContent };
  const older = JSON.parse(JSON.stringify(entry.framing));
  older.turns = older.turns.concat([{ who: 'person', text: 'From this one, then.' }, { who: 'architect', text: 'As you say.', v: lastB - 1, cost: 0.01, call: 21 }]);
  reply([200, stream({ framing: older })]); await tick();
  check('an answer sent from an earlier step (0316; a version, 0308): the message names the step on screen, which is the one in use; no row of the conversation says where the coach went - what is '
    + 'on screen is in use; after the reply the tab stays on that step, and Start analysis names it',
    same(fromOlder, { call: ['/architect/say', { thread_id: 7, chain_id: 71, text: 'From this one, then.', step: lastB - 1 }], at: lastB - 1, shown: (lastB - 1) + ' of ' + lastB })
    && !/in use/.test($('streamOutput').textContent) && pane().slice(-2)[0] === 'you|YouFrom this one, then.'
    && brief().querySelector('.ar-ver b').textContent === (lastB - 1) + ' of ' + lastB && brief().querySelector('[data-ar="start"]').textContent === 'Start analysis from step ' + (lastB - 1)
    && h3s(brief()).indexOf('Builds on') >= 0, [fromOlder, brief().querySelector('.ar-ver b').textContent]);
  entry.framing = A.go(entry.framing, lastB); loadResponseContent(entry); updateNavigationButtons();      // the last step again, for what follows
  const textB = entry.queryText, otherB = lastB - entry.framing.versions.slice().reverse().findIndex(v => v.brief.question !== textB);      // the last version that asks another question
  for (let k = lastB; k > otherB; k--) doc.dispatch('click', brief().querySelector('[data-step="-1"]'));
  held();
  A.tell('And from here.'); await tick();
  const offMid = brief().querySelectorAll('.ar-ver button').map(x => x.hasAttribute('disabled')).join();
  doc.dispatch('click', brief().querySelector('[data-step="1"]'));
  const steppedMid = brief().querySelector('.ar-ver b').textContent;
  const fromOther = JSON.parse(JSON.stringify(entry.framing));
  fromOther.turns = fromOther.turns.concat([{ who: 'person', text: 'And from here.' }, { who: 'architect', text: 'From there, then.', v: otherB, cost: 0.01, call: 22 }]);
  reply([200, stream({ framing: fromOther })]); await tick();
  check('an answer from a step that asks another question (0316; 0308): the chain\'s own text is the question that stood there. While the Pathfinder replies the arrows are off - what is on its way '
    + 'goes on from the step it left - and a click on one changes nothing; with the reply they are back',
    otherB < lastB && offMid === 'true,true' && steppedMid === otherB + ' of ' + lastB && !brief().querySelector('[data-step="1"]').hasAttribute('disabled') && entry.framing.at === otherB && entry.queryText === entry.framing.versions[otherB - 1].brief.question && entry.queryText !== textB
    && brief().querySelector('.ar-ver b').textContent === otherB + ' of ' + lastB, [otherB, lastB, steppedMid, entry.queryText]);
  entry.framing = A.go(entry.framing, lastB); entry.queryText = textB; loadResponseContent(entry); updateNavigationButtons();
  // a part of an earlier analysis opened (0307): a row of the conversation, and the Pathfinder goes on at once
  held(); n = calls.length;
  A.tell('How was the figure drawn?'); await tick();
  const opening = JSON.parse(JSON.stringify(entry.framing));
  opening.turns = opening.turns.concat([{ who: 'person', text: 'How was the figure drawn?' }, { who: 'architect', text: 'I am opening the cell that drew it.', v: opening.versions.length, cost: 0.01, call: 18 },
                                        { who: 'opened', what: 'cell', n: 5, label: 'cell 5', chars: 1234 }]);
  reply([200, stream({ framing: opening })]); await tick();
  const openedNow = { calls: calls.slice(n), row: $('streamOutput').querySelectorAll('.sp-row').map(r => r.textContent).slice(-1)[0], wait: pane().slice(-1)[0], lock: locks[locks.length - 1] };
  const spoke = JSON.parse(JSON.stringify(opening));
  spoke.turns.push({ who: 'architect', text: 'It draws one line a month.', v: spoke.versions.length, cost: 0.01, call: 19 });
  reply([200, stream({ framing: spoke })]); await tick();
  check('a reply that opened a part of an earlier analysis: the part is a row under its message - READ, what it is, how long - and the Pathfinder is asked again at once with nothing said; its next message '
    + 'stands under the row, and no further call is made',
    same(openedNow.calls, [['/architect/say', { thread_id: 7, chain_id: 71, text: 'How was the figure drawn?', step: opening.versions.length }], ['/architect/say', { thread_id: 7, chain_id: 71, text: null, step: opening.versions.length }]])
    && openedNow.row === '✓READcell 51,234 characters' && openedNow.wait === 'arch wait|Pathfinderreading…' && same(openedNow.lock, ['lock', 'The Pathfinder is replying'])
    && calls.length === n + 2 && pane()[pane().length - 1] === 'arch|Pathfinder⌘It draws one line a month.' && same(locks[locks.length - 1], ['unlock']), openedNow);
  // a part of what is fixed before a run that the brief does not hold: added like any part, under its own name
  serve(); n = calls.length;
  const offered = (doc.dispatch('click', brief().querySelector('[data-ar="more"]')), kindsOf(brief()).split('|').filter(k => k.indexOf('fixed.') === 0).join('|'));
  doc.dispatch('click', brief().querySelector('.ar-kinds [data-ar="add"][data-path="fixed.comparison"]'));
  const lineC = lineOf(brief(), 'fixed.comparison');
  const typing = { head: h3s(brief()).indexOf('What is compared') >= 0, hint: lineC.querySelector('.ar-input').hasAttribute('placeholder'), editing: lineC.classList.contains('editing') };
  lineC.querySelector('.ar-input').value = 'B against A';
  doc.dispatch('click', lineC.querySelector('[data-ar="keep"]')); await tick();
  doc.dispatch('click', brief().querySelector('[data-ar="more"]'));
  check('a part of what is fixed before a run that the brief does not hold (0308) is offered by its own name among the parts to add - no heading stands over the three; chosen, its field opens under '
    + 'that name; kept, it is a line of the brief there, and the list offers it no more',
    /fixed\.comparison=What is compared/.test(offered) && same(typing, { head: true, hint: false, editing: true }) && same(calls.slice(n).map(c => [c[0], c[1].changed, c[1].brief.fixed.comparison]), [['/architect/brief', ['fixed.comparison'], 'B against A']])
    && lineOf(brief(), 'fixed.comparison').querySelector('.tx').textContent === 'B against A' && h3s(brief()).indexOf('Fixed before the run') < 0
    && kindsOf(brief()).indexOf('fixed.comparison') < 0 && !brief().querySelector('.ar-grid') && !brief().querySelector('.ar-chips'), [typing, offered, calls.slice(n)]);
  doc.dispatch('click', brief().querySelector('[data-ar="more"]'));
  // the figures of the brief and their draft (0309, 0310): the reply stands while the draft is drawn, then each plot is drawn in its figure; the cross takes a figure out - a line
  // being typed elsewhere kept first - and the one left keeps its draft
  {
  const liveD = liveBody(), KEY = { 'Two <paths>': 'k1', 'Yield by season': 'k2' };
  answers['/architect/say'] = liveD; n = calls.length; plotted.length = 0;
  answers['/architect/draft/7/71/k1'] = [200, { plot: { data: [{ type: 'scatter', y: [1, 2] }], layout: { title: { text: 'Two <paths>' }, meta: 'computed' } } }];
  answers['/architect/draft/7/71/k2'] = [200, { plot: { data: [{ type: 'bar', y: [3] }], layout: { title: { text: 'Yield by season' }, height: 700 } } }];
  A.tell('Show me what it will look like'); await tick();
  const replied = answered('Show me what it will look like', 'A draft is being drawn. Is that what you want to see?',
                           { changed: ['figures.0', 'figures.1'], brief: Object.assign({}, latest().brief, { figures: [KNOWN, ON_DATA] }), keys: ['k1', 'k2'] }, { choices: ['Yes', 'Change something'] });
  const figsNow = () => brief().querySelectorAll('.ar-fig').map(f => f.className + ':' + f.querySelector('.n').textContent + ':' + f.querySelector('.t').textContent + ':' +
                                                                     (f.querySelector('.tag') ? f.querySelector('.tag').textContent : windowIn(f))).join('|');
  const lastRow = () => $('streamOutput').querySelectorAll('.sp-row').map(r => r.className + ':' + r.textContent).slice(-1)[0];
  const asked = () => calls.slice(n).map(c => c[0]), drew = () => plotted.map(p => p.key + ':' + p.layout.height + ':' + p.layout.annotations.map(a => a.text).join() + ':' + p.config.displayModeBar + ':' + p.data.length);
  liveD.send(JSON.stringify({ type: 'architect_saved', read: 1, of: 3 }) + '\n'); await tick();
  const asksNow = entry.queryText; entry.queryText = 'as it was before the reply';
  liveD.send(JSON.stringify({ type: 'architect_draft', chain_id: 71, framing: replied }) + '\n'); await tick();
  const taken = entry.queryText === asksNow;
  A.restore({ status: 'framing', chain_id: 73, thread_id: 7, queryText: 'q', framing: { versions: [{ n: 1, by: 'architect', changed: [], brief: { question: 'q', figures: [ON_DATA] }, keys: ['zz'] }], turns: [] } });
  const elsewhere = { drawing: brief().getAttribute('data-drawing'), figs: figsNow(), chain: brief().getAttribute('data-chain') };
  A.restore(entry);
  doc.dispatch('click', brief().querySelector('[data-ar="step"][data-step="-1"]')); doc.dispatch('click', brief().querySelector('[data-ar="step"][data-step="1"]')); await tick();
  const meanwhile = { figs: figsNow(), pane: pane().slice(-2), said: pane().filter(m => m === 'you|YouShow me what it will look like').length,
                      row: lastRow(), hold: $('queryInput').placeholder, choices: $('streamOutput').querySelectorAll('.ar-choice').length, asked: asked(), drew: drew(), drawing: brief().getAttribute('data-drawing'),
                      thread: brief().getAttribute('data-thread'), versions: entry.framing.versions.length };
  const drawnF = JSON.parse(JSON.stringify(replied));
  Object.assign(drawnF, { drafts: { k1: { basis: 'computed' }, k2: { basis: 'made up' } }, draft_calls: 1 });
  drawnF.turns.push({ who: 'draft', drawn: [{ title: 'Two <paths>', basis: 'computed' }, { title: 'Yield by season', basis: 'made up' }], v: drawnF.versions.length, secs: 6.2, cost: 0.002, call: 1 });
  liveD.send(JSON.stringify({ architect: { framing: drawnF } }) + '\n'); liveD.end(); await tick();
  const drawnNow = { figs: figsNow(), heads: h3s(brief()).split('|').slice(-2).join('|'), row: lastRow(), hold: $('queryInput').placeholder, choices: $('streamOutput').querySelectorAll('.ar-choice').length, asked: asked(), drew: drew(),
                     drawing: brief().getAttribute('data-drawing'), by: latest().by, crosses: brief().querySelectorAll('.ar-fig [data-ar="unfigure"]').length, held: brief().querySelectorAll('.ar-fig .plot svg').length,
                     made: brief().querySelectorAll('.ar-fig .cap').map(x => x.textContent).join('|'), waits: brief().querySelectorAll('.ar-wait.live').length };
  const sketchedAt = entry.framing.versions.length;
  doc.dispatch('click', brief().querySelector('[data-ar="step"][data-step="-1"]')); await tick();
  const back = { figs: figsNow(), drew: plotted.length };
  doc.dispatch('click', brief().querySelector('[data-ar="step"][data-step="1"]')); await tick();
  const again = { figs: figsNow(), drew: plotted.length, asked: asked().length };
  check('a reply and the draft of its figures (0310, 0311): the coach asks in words, like any answer. The stream first carries the framing with the reply: its message stands - once - with a row under '
    + 'it that says a draft is being drawn - not the row of the reading that came before it -, the composer is held with those words, the chain\'s question is the reply\'s, the figures stand in the '
    + 'brief as grey windows that say a draft is being drawn - still after a step to another version and back, and not in another chain\'s brief - and nothing is asked of the server yet. '
    + 'The stream ends on the framing with the draft: each figure is drawn by Plotly in its place - its plot asked for once, under the thread, the chain and the figure\'s key - as its layout '
    + 'fitted to the panel, the words across the one on made-up numbers; the row says how many were drawn, the reply\'s choices can be clicked, the composer is the conversation\'s again. '
    + 'Stepping to a version without figures and back draws them again, with nothing asked of the server',
    same(meanwhile, { figs: 'ar-fig changed:1:Two <paths>:ar-wait live=Drawing a draft…|ar-fig changed:2:Yield by season:ar-wait live=Drawing a draft…',
                      pane: ['you|YouShow me what it will look like', 'arch|Pathfinder⌘A draft is being drawn. Is that what you want to see?'], said: 1, row: 'sp-row tool read pending:DRAWING A DRAFT',
                      hold: 'A draft of the figures is being drawn', choices: 0, asked: ['/architect/say'], drew: [], drawing: '1', thread: '7', versions: sketchedAt })
    && taken && same(elsewhere, { drawing: null, figs: 'ar-fig:1:Yield by season:ar-wait=No draft yet.', chain: '73' })
    && same(drawnNow, { figs: 'ar-fig drawn changed:1:Two <paths>:draft|ar-fig drawn changed:2:Yield by season:draft · made-up numbers', heads: 'What it will look like|Found in your saved analyses',
                        row: 'sp-row tool read:✓FIGURES2 drawn6 s⌘', hold: 'Answer, or say what to change', choices: 2, asked: ['/architect/say', '/architect/draft/7/71/k1', '/architect/draft/7/71/k2'],
                        drew: ['k1:360::false:1', 'k2:560:made-up numbers:false:1'], drawing: null, by: 'architect', crosses: 2, held: 2, made: 'The numbers are made up. The analysis puts in the real ones.', waits: 0 })
    && back.figs === '' && back.drew === 2 && again.figs === drawnNow.figs && again.drew === 4 && again.asked === 3 && same(locks[locks.length - 1], ['unlock']), [meanwhile, taken, elsewhere, drawnNow, back, again]);
  answers['/architect/brief'] = body => { const f = JSON.parse(JSON.stringify(entry.framing));
    f.versions.push({ n: f.versions.length + 1, by: 'person', changed: body.changed, brief: body.brief, keys: (body.brief.figures || []).map(x => KEY[x.title]) }); return [200, { framing: f }]; };
  n = calls.length;
  doc.dispatch('click', lineOf(brief(), 'fixed.comparison').querySelector('.pen'));
  lineOf(brief(), 'fixed.comparison').querySelector('.ar-input').value = 'B against A, on x';
  doc.dispatch('click', brief().querySelector('.ar-fig [data-ar="unfigure"]')); await tick();
  const oneLeft = figsNow(), drewLeft = plotted.slice(-1).map(p => p.key).join();
  doc.dispatch('click', brief().querySelector('.ar-fig [data-ar="unfigure"]')); await tick();
  check('the cross on a figure (0309, 0310): it sends the brief without the figure - a version of the coach\'s, the line being typed elsewhere kept first as its own - and the figure left moves up '
    + 'to its number with its draft, drawn again from the plot the page holds; with the last one out the part is gone',
    calls.length === n + 3 && calls.slice(n).every(c => c[0] === '/architect/brief') && same(calls[n][1].changed, ['fixed.comparison']) && same(calls[n][1].brief.figures, [KNOWN, ON_DATA])
    && same(calls[n + 1][1].changed, ['figures']) && same(calls[n + 1][1].brief.figures, [ON_DATA]) && calls[n + 1][1].brief.fixed.comparison === 'B against A, on x'
    && oneLeft === 'ar-fig drawn:1:Yield by season:draft · made-up numbers' && drewLeft === 'k2' && same(calls[n + 2][1].changed, ['figures']) && !('figures' in calls[n + 2][1].brief) && latest().by === 'person'
    && entry.framing.versions.length === sketchedAt + 3 && !brief().querySelector('.ar-figs') && h3s(brief()).indexOf('What it will look like') < 0 && !brief().querySelector('.editing'), [oneLeft, drewLeft, calls.slice(n)]);
  // a stream that ends while the draft is drawn - without its last line, or cut: the reply the page already shows stands
  const cuts = [];
  for (const how of ['end', 'cut']) {
    const live = liveBody(), told = toasts.length; answers['/architect/say'] = live;
    A.tell('And now, ' + how + '?'); await tick();
    const shown = answered('And now, ' + how + '?', 'A draft is being drawn.', { changed: ['figures.0'], brief: Object.assign({}, latest().brief, { figures: [ON_DATA] }), keys: ['cut-' + how] }, { choices: ['Yes'] });
    live.send(JSON.stringify({ type: 'architect_draft', chain_id: 71, framing: shown }) + '\n'); await tick();
    live[how](); await tick();
    cuts.push({ told: toasts.length - told, typed: $('queryInput').value, hold: $('queryInput').placeholder, drawing: brief().getAttribute('data-drawing'), figs: figsNow(),
                last: pane().slice(-1)[0], choices: $('streamOutput').querySelectorAll('.ar-choice').length, lock: locks[locks.length - 1], kept: same(entry.framing, shown), rows: $('streamOutput').querySelectorAll('.sp-row.pending').length });
  }
  check('a stream that ends while the draft is drawn (0310, 0311): the reply the page shows stands - nothing says the Pathfinder did not reply, what was typed is not put back, the figures\' windows '
    + 'no longer say a draft is on its way - there is none yet -, the row that said so is gone, the reply\'s choices can be clicked and the composer is free - whether the stream ended without its '
    + 'last line or was cut',
    cuts.length === 2 && cuts.every(c => same(c, { told: 0, typed: '', hold: 'Answer, or say what to change', drawing: null, figs: 'ar-fig changed:1:Yield by season:ar-wait=No draft yet.',
                                                 last: 'arch|Pathfinder⌘A draft is being drawn.Yes', choices: 1, lock: ['unlock'], kept: true, rows: 0 })), cuts);
  // a plot that cannot be shown, a page without Plotly, a tab that came with its markup - and nothing asked for of a saved analysis the brief builds on
  const kept = entry.framing, wasPlotly = global.Plotly;
  const lone = (key, basis, more) => Object.assign({ versions: [{ n: 1, by: 'architect', changed: [], brief: Object.assign({ question: 'q', figures: [ON_DATA] }, more), keys: [key] }], drafts: { [key]: { basis } }, turns: [] });
  const UNSHOWN = 'ar-fig:1:Yield by season:ar-wait=The draft could not be shown.';
  answers['/architect/draft/7/71/gone'] = [404, { error: 'No draft is kept for this figure.' }];
  entry.framing = lone('gone', 'made up'); n = calls.length; plotted.length = 0;
  loadResponseContent(entry); await tick();
  const gone = { fig: figsNow(), parts: partsOf(brief().querySelector('.ar-fig')), drew: plotted.length, asked: asked() };
  loadResponseContent(entry); await tick();
  const goneStill = { fig: figsNow(), asked: asked().length };
  answers['/architect/draft/7/71/later'] = 'down';
  entry.framing = lone('later', 'computed'); n = calls.length;
  loadResponseContent(entry); await tick();
  const down = figsNow();
  answers['/architect/draft/7/71/later'] = [502, 'Bad gateway'];
  loadResponseContent(entry); await tick();
  const failed = figsNow();
  answers['/architect/draft/7/71/later'] = [200, { plot: { data: [{ type: 'bar', y: [1] }], layout: {} } }];
  loadResponseContent(entry); await tick();
  const up = { fig: figsNow(), drew: plotted.map(p => p.key).join(), asked: asked().length };
  delete global.Plotly; plotted.length = 0;
  entry.framing = lone('k2', 'made up'); loadResponseContent(entry); await tick();
  const bare = { fig: figsNow(), drew: plotted.length };
  global.Plotly = wasPlotly;
  const SAVED_ON = [{ thread: '7301', run: '7302', when: '2026-03-02', question: 'Was B above A in spring?', passage: 'B led', accepted: true }, { thread: '7301', run: '7309', when: '2026-04-02', question: 'And in April?', passage: 'B led again', accepted: true }];
  entry.framing = lone('k2', 'made up', { saved: SAVED_ON }); n = calls.length;
  loadResponseContent(entry); await tick();
  const builtOn = brief().querySelectorAll('.ar-built');
  const built = { lines: builtOn.length, under: builtOn.map(l => { const e = l.parent.elements; return e[e.indexOf(l) + 1].className.split(' ')[0]; }).join(), pictures: brief().querySelectorAll('img').length,
                  asked: asked(), fig: figsNow() };
  entry.framing = kept;
  const restored = { chain_id: 72, thread_id: 7, parentChainId: 70, queryText: 'A run', tabContent: '<div id="tab-brief" class="tab active">Brief</div>', streamOutput: '',
                     contentOutput: '<div id="content-brief" class="tab-content active">' + b.brief(lone('k2', 'made up'), { chain: 71, thread: 7, state: 'run' }).replace('<div class="plot" data-key="k2" data-made-up="1"></div>', '<div class="plot" data-key="k2" data-made-up="1"><svg class="stale"></svg></div>') + '</div>' };
  responses.push(restored); currentResponseIndex = responses.length - 1; plotted.length = 0; n = calls.length;
  loadResponseContent(restored); await tick();
  const cameBack = { drew: plotted.map(p => p.key + ':' + p.layout.annotations.length).join(), live: !!brief().querySelector('.plot .main-svg'), stale: !!brief().querySelector('.plot .stale'), asked: asked(), cross: !!brief().querySelector('[data-ar="unfigure"]') };
  A.restore(restored); await tick();
  const again2 = { drew: plotted.length, svgs: brief().querySelectorAll('.plot svg').length };
  const tabWas = global.createOrUpdateTab;
  global.createOrUpdateTab = (type, html) => { $('contentOutput').innerHTML = '<div id="content-' + type + '" class="tab-content active">' + html + '</div>'; };      // the tab in the page, as the page's own makes it
  answers['/architect/draft/7/74/run1'] = [200, { plot: { data: [{ type: 'bar', y: [2] }], layout: {} } }];
  plotted.length = 0; n = calls.length;
  A.started({ status: 'running', chain_id: 74, thread_id: 7, queryText: 'q', framing: lone('run1', 'computed') }); await tick();
  const ran = { state: brief().getAttribute('data-state'), asked: asked(), drew: plotted.map(p => p.key).join(), cross: !!brief().querySelector('[data-ar="unfigure"]') };
  global.createOrUpdateTab = tabWas;
  responses.pop(); currentResponseIndex = 1; loadResponseContent(entry); updateNavigationButtons(); await tick();
  check('where a plot cannot be shown (0310, 0311): a figure whose plot the server no longer holds is a grey window that says the draft could not be shown - the plot\'s place is gone, with the word '
    + 'that it is a draft and the line that its numbers are made up - and the server is not asked for it a second time; where the server was not reached, or its answer failed, the window says '
    + 'so for now and the plot is asked for again when the tab is next drawn. Every figure is that window on a page without Plotly; nothing breaks. Under a saved analysis the brief builds on '
    + 'stands nothing (0311): no picture, and nothing is asked of the server for one. A Brief tab that came with its markup - a run restored - has its drafts drawn in it again, in the place of '
    + 'what the markup held, once however often the page looks at it; and the Brief tab of an analysis that starts has its drafts drawn, asked for under its thread and chain',
    same(gone, { fig: UNSHOWN, parts: 'hd,ar-wait', drew: 0, asked: ['/architect/draft/7/71/gone'] }) && same(goneStill, { fig: UNSHOWN, asked: 1 })
    && down === UNSHOWN && failed === UNSHOWN && same(up, { fig: 'ar-fig drawn:1:Yield by season:draft', drew: 'later', asked: 3 })
    && same(bare, { fig: UNSHOWN, drew: 0 })
    && same(built, { lines: 2, under: 'ar-line,ar-always', pictures: 0, asked: [], fig: 'ar-fig drawn:1:Yield by season:draft · made-up numbers' })
    && same(cameBack, { drew: 'k2:1', live: true, stale: false, asked: [], cross: false }) && same(again2, { drew: 1, svgs: 1 })
    && same(ran, { state: 'run', asked: ['/architect/draft/7/74/run1'], drew: 'run1', cross: false }), [gone, goneStill, down, failed, up, bare, built, cameBack, again2, ran]);
  }
  const parts = [];
  const whole = await A.readStream({ text: async () => '{"a": 1}\n\nnot json\n{"b": 2}' }, d => parts.push(d));
  const fed = liveBody(), parts2 = [];
  const pending = A.readStream(fed, d => parts2.push(d));
  fed.send('{"a": 1}\n{"b"'); fed.send(': 2}\n\n{"c": 3}'); fed.end();
  const whole2 = await pending;
  check('readStream: each JSON line of a body is handed over - as it arrives where the body is a stream, a line cut between two parts taken whole, the last line without its end too - and the whole body is returned; '
    + 'a line that is no JSON is passed over',
    same(parts, [{ a: 1 }, { b: 2 }]) && whole === '{"a": 1}\n\nnot json\n{"b": 2}' && same(parts2, [{ a: 1 }, { b: 2 }, { c: 3 }]) && whole2 === '{"a": 1}\n{"b": 2}\n\n{"c": 3}', [parts, parts2, whole2]);
  }

  // the question read as the Analyst will read it, before its analysis starts (0313)
  {
    const rowsNow = () => $('streamOutput').querySelectorAll('.sp-row').map(r => r.className + ':' + r.textContent), lastRow = () => rowsNow().slice(-1)[0];
    const startBtn = () => brief().querySelector('[data-ar="start"]'), sentNow = () => submitted.length, asksNow = () => brief().querySelector('h1 .tx').textContent;
    const posted = from => calls.slice(from).map(c => [c[0], c[0] === '/architect/ready' ? c[1] : c[0] === '/architect/brief' ? c[1].changed : c[1].text]);
    // the framing as the server leaves it after a read of the question in use: the reader's turn, the version listed as read
    const readAs = (missing, more) => { const f = JSON.parse(JSON.stringify(entry.framing)), at = f.at || f.versions.length;
      f.turns = f.turns.concat([{ who: 'reader', missing, v: at, cost: 0.002, call: f.turns.filter(t => t.who === 'reader').length + 1, secs: 2.4 }]);
      f.read = (f.read || []).concat([at]); return Object.assign(f, more || {}); };
    // ... and after the Pathfinder's reply to it: its message, its wording as one more version, that version listed too
    const reworded = (f, text, wording, more) => { const k = f.versions.length + 1;
      f.versions.push({ n: k, by: 'architect', why: 'answer', changed: ['question'].concat((more || {}).changed || []), brief: Object.assign({}, f.versions[k - 2].brief, { question: wording }, (more || {}).brief), keys: (more || {}).keys || [] });
      f.turns.push({ who: 'architect', text, wording, v: k, cost: 0.02, call: (f.calls || 0) + 1 }); f.calls = (f.calls || 0) + 1; f.read.push(k); return f; };
    // the coach words the question by hand: a version nobody has read
    const ask = async text => { doc.dispatch('click', lineOf(brief(), 'question').querySelector('.pen')); lineOf(brief(), 'question').querySelector('.ar-input').value = text;
                                doc.dispatch('click', lineOf(brief(), 'question').querySelector('[data-ar="keep"]')); await tick(); return entry.framing.versions.length; };
    const v0 = await ask('Draw the series as bars.');
    const live = liveBody(), sent0 = sentNow(); answers['/architect/ready'] = live; n = calls.length;
    doc.dispatch('click', startBtn()); await tick();
    const inFlight = { posted: posted(n), row: lastRow(), hold: $('queryInput').placeholder, lock: locks[locks.length - 1], sent: sentNow() - sent0, start: !!startBtn() };
    doc.dispatch('click', startBtn()); doc.dispatch('click', lineOf(brief(), 'question').querySelector('.pen')); await tick();      // Start again, and a pencil: nothing while it is read
    const meanwhile = { posted: calls.length - n, editing: !!brief().querySelector('.editing'), sent: sentNow() - sent0 };
    live.send('{"text": "{\\"cannot_place\\": ", "chain_id": 71}\n'); await tick();
    const still = lastRow();
    live.send(JSON.stringify({ architect: { framing: readAs([]), clean: true } }) + '\n'); live.end(); await tick();
    const button = $('streamOutput').querySelectorAll('.sp-row').slice(-1)[0].querySelector('.sp-prompt');
    const clean = { sent: sentNow() - sent0, how: Object.keys(submitted[submitted.length - 1]).join(), framed: submitted[submitted.length - 1].framed === entry, step: submitted[submitted.length - 1].step, row: lastRow(),
                    read: entry.framing.read, prompt: ['data-agent', 'data-chain', 'data-call', 'title'].map(a => button.getAttribute(a)), hold: $('queryInput').placeholder, lock: locks[locks.length - 1], told: toasts.length };
    n = calls.length;
    doc.dispatch('click', startBtn()); await tick();
    const again = { posted: calls.length - n, sent: sentNow() - sent0 };
    check('Start analysis reads the question first (0313): the question of the step on screen is sent to be read as the Analyst will read it - the thread, the chain, the step. While it is read a row says so, the '
      + 'composer is held with those words, nothing starts, and neither Start nor a pencil does anything. The read came back clean: the page\'s own send starts the chain from that step; the '
      + 'conversation holds the read as a row - the question stands on its own, the seconds, the button to what the reader was given, the first call of the question check in the run log - and the '
      + 'framing lists the version as read. Started again - the server had not started it - the same version starts at once: nothing is sent to be read',
      same(inFlight, { posted: [['/architect/ready', { thread_id: 7, chain_id: 71, step: v0 }]], row: 'sp-row tool read pending:CHECKING THE QUESTION', hold: 'The question is being read as the Analyst will read it',
                       lock: ['lock', 'The question is being read as the Analyst will read it'], sent: 0, start: true })
      && same(meanwhile, { posted: 1, editing: false, sent: 0 }) && still === inFlight.row
      && same(clean, { sent: 1, how: 'framed,step', framed: true, step: v0, row: 'sp-row tool read:✓CHECK questionstands on its own2 s⌘', read: [v0],
                       prompt: ['Question check', '71', '1', 'what the question check was given (run log)'], hold: 'Answer, or say what to change', lock: ['unlock'], told: clean.told })
      && same(again, { posted: 0, sent: 2 }), [inFlight, meanwhile, still, clean, again]);

    // the reader cannot place something: the Pathfinder has gone on, and the analysis does not start
    const live2 = liveBody(), sent1 = sentNow(), told1 = toasts.length; answers['/architect/ready'] = live2; n = calls.length;
    doc.dispatch('click', lineOf(brief(), 'question').querySelector('.pen'));
    lineOf(brief(), 'question').querySelector('.ar-input').value = 'Draw the series as bars, as on 14 May & <before>.';
    doc.dispatch('click', startBtn()); await tick();                    // the line being typed is kept first: a version of the coach's, then that one is read
    const v1 = entry.framing.versions.length, sentFor = posted(n);
    const flagged = reworded(readAs(['as on 14 May', '<before>']), 'I took out what pointed to another day.', 'Draw the series as bars, in one colour.');
    live2.send(JSON.stringify({ architect: { framing: flagged, clean: false } }) + '\n'); live2.end(); await tick();
    const heldUp = { sent: sentNow() - sent1, rows: rowsNow().slice(-2), said: pane().slice(-1)[0], ver: brief().querySelector('.ar-ver b').textContent, asks: asksNow(), text: entry.queryText,
                     start: startBtn().textContent, hold: $('queryInput').placeholder, lock: locks[locks.length - 1], told: toasts.length - told1, read: entry.framing.read,
                     safe: !$('streamOutput').innerHTML.includes('<before>') };
    n = calls.length;
    doc.dispatch('click', startBtn()); await tick();
    const startsNow = { posted: calls.length - n, sent: sentNow() - sent1, step: submitted[submitted.length - 1].step };
    doc.dispatch('click', brief().querySelector('[data-step="-1"]')); n = calls.length;
    doc.dispatch('click', startBtn()); await tick();
    const wentBack = { posted: calls.length - n, sent: sentNow() - sent1, step: submitted[submitted.length - 1].step };
    entry.framing = A.go(entry.framing, v1 + 1); loadResponseContent(entry); updateNavigationButtons();      // the last step on screen again, for what follows
    check('a question the Analyst could not place something in (0313): a line being typed is kept first, as a version of the coach\'s, and that version is read. The analysis does not start. The '
      + 'conversation holds the read - which words the Analyst cannot place, as text - then the Pathfinder\'s reply and the row of its wording; the Brief tab is on the version the Pathfinder left, '
      + 'with its question, which is the chain\'s; the composer is the conversation\'s again, and nothing more is said. Start analysis then starts from that step at once - a read holds a start up '
      + 'once - and so does the step before it, which the coach went back to: both versions are listed as read',
      same(sentFor, [['/architect/brief', ['question']], ['/architect/ready', { thread_id: 7, chain_id: 71, step: v1 }]]) && v1 === v0 + 1
      && same(heldUp, { sent: 0, rows: ['sp-row tool read skipped ar-unplaced:–CHECK questionthe Analyst cannot place “as on 14 May” · “<before>”2 s⌘', 'sp-row tool read:✓QUESTIONupdatedstep ' + (v1 + 1)],
                        said: 'arch|Pathfinder⌘I took out what pointed to another day.', ver: (v1 + 1) + ' of ' + (v1 + 1), asks: 'Draw the series as bars, in one colour.', text: 'Draw the series as bars, in one colour.',
                        start: 'Start analysis', hold: 'Answer, or say what to change', lock: ['unlock'], told: 0, read: [v0, v1, v1 + 1], safe: true })
      && same(startsNow, { posted: 0, sent: 1, step: v1 + 1 }) && same(wentBack, { posted: 0, sent: 2, step: v1 }), [sentFor, heldUp, startsNow, wentBack]);

    // an earlier step on screen whose question nobody has read: the server reads that one, and it is the one in use from then
    const lastK = entry.framing.versions.length, earlyK = v0 - 1, sentK = sentNow();
    for (let k = lastK; k > earlyK; k--) doc.dispatch('click', brief().querySelector('[data-step="-1"]'));
    answers['/architect/ready'] = () => [200, stream({ framing: readAs([]), clean: true })]; n = calls.length;
    doc.dispatch('click', startBtn()); await tick();
    const early = { posted: posted(n), sent: sentNow() - sentK, step: submitted[submitted.length - 1].step, at: entry.framing.at, text: entry.queryText === entry.framing.versions[earlyK - 1].brief.question,
                    other: entry.framing.versions[earlyK - 1].brief.question !== entry.framing.versions[lastK - 1].brief.question, fold: el(b.fold(entry)).querySelector('.kind').textContent,
                    read: entry.framing.read.slice(-1), row: lastRow() };
    entry.framing = A.go(entry.framing, lastK); entry.queryText = entry.framing.versions[lastK - 1].brief.question; loadResponseContent(entry); updateNavigationButtons();      // the last step on screen again
    check('Start analysis with an earlier step on screen whose question was not read (0313): the step is named for the read; the framing the server leaves names its version as the one in use, the '
      + 'chain\'s question is the one that stood there, the send is told the step, and the fold above the run would name it',
      same(early, { posted: [['/architect/ready', { thread_id: 7, chain_id: 71, step: earlyK }]], sent: 1, step: earlyK, at: earlyK, text: true, other: true, fold: 'brief · step ' + earlyK, read: [earlyK],
                    row: 'sp-row tool read:✓CHECK questionstands on its own2 s⌘' }), early);

    // ... and the Pathfinder made no reply to it: the page says why, the read stands
    const v2 = await ask('Draw the series as bars, as usual.'), sent2 = sentNow(), told2 = toasts.length;
    answers['/architect/ready'] = () => [200, stream({ framing: readAs(['as usual']), clean: false, error: 'The Pathfinder\'s reply could not be read (it holds no JSON object).' })]; n = calls.length;
    doc.dispatch('click', startBtn()); await tick();
    const noReply = { sent: sentNow() - sent2, row: lastRow(), said: toasts.slice(told2), ver: brief().querySelector('.ar-ver b').textContent, hold: $('queryInput').placeholder, read: entry.framing.read.slice(-1) };
    n = calls.length;
    doc.dispatch('click', startBtn()); await tick();
    const goesOn = { posted: calls.length - n, sent: sentNow() - sent2 };
    check('the Analyst could not place something, and the Pathfinder made no reply (0313): the analysis does not start, the read stands as the conversation\'s last row, the brief is as it was, and the '
      + 'page says why there is no reply, in the server\'s words. Start analysis then starts it: the version is listed as read',
      same(noReply, { sent: 0, row: 'sp-row tool read skipped ar-unplaced:–CHECK questionthe Analyst cannot place “as usual”2 s⌘', said: ['The Pathfinder\'s reply could not be read (it holds no JSON object).'],
                      ver: v2 + ' of ' + v2, hold: 'Answer, or say what to change', read: [v2] }) && same(goesOn, { posted: 0, sent: 1 }), [noReply, goesOn]);

    // a read that cannot be had holds nothing up
    const v3 = await ask('Draw the series as bars, once more.'), outs = [];
    for (const answer of ['down', [502, 'Bad gateway'], [200, stream({ error: 'This brief can no longer be changed: its analysis has started.' })], [402, { message: 'Your balance is used up.' }], [200, 'not a stream at all']]) {
      const before = { sent: sentNow(), told: toasts.length, turns: entry.framing.turns.length }; answers['/architect/ready'] = answer; n = calls.length;
      doc.dispatch('click', startBtn()); await tick();
      outs.push({ posted: posted(n).map(c => c[0]).join(), sent: sentNow() - before.sent, step: submitted[submitted.length - 1].step, told: toasts.length - before.told, turns: entry.framing.turns.length - before.turns,
                  read: (entry.framing.read || []).indexOf(v3) >= 0, hold: $('queryInput').placeholder, pending: $('streamOutput').querySelectorAll('.sp-row.pending').length });
    }
    check('a read that cannot be had holds nothing up (0313): the server unreachable, an error page, a brief the server says has started, a refusal for the balance, a body that is no stream - each '
      + 'time the page\'s own send starts the chain from the step on screen, which says what it meets; the page says nothing of the read, the conversation gains no row, the version is not '
      + 'listed as read - the next start asks again - and no row is left saying a read is under way',
      outs.length === 5 && outs.every(o => same(o, { posted: '/architect/ready', sent: 1, step: v3, told: 0, turns: 0, read: false, hold: 'Answer, or say what to change', pending: 0 })), outs);

    // the read takes a moment: the coach may have left the brief, or another analysis may have begun
    const live5 = liveBody(), sent5 = sentNow(), told5 = toasts.length; answers['/architect/ready'] = live5;
    doc.dispatch('click', startBtn()); await tick();
    currentResponseIndex = 0; loadResponseContent(responses[0]); updateNavigationButtons();      // the coach goes to another chain
    const away = { pane: $('streamOutput').querySelectorAll('.sp-row.pending').length, lock: locks[locks.length - 1] };
    live5.send(JSON.stringify({ architect: { framing: readAs([]), clean: true } }) + '\n'); live5.end(); await tick();
    const left = { sent: sentNow() - sent5, told: toasts.length - told5, read: entry.framing.read.indexOf(v3) >= 0 };
    currentResponseIndex = 1; loadResponseContent(entry); updateNavigationButtons(); n = calls.length;
    const backRow = lastRow();
    doc.dispatch('click', startBtn()); await tick();
    const back5 = { posted: calls.length - n, sent: sentNow() - sent5 };
    const v4 = await ask('Draw the series as bars, a last time.'), live6 = liveBody(), sent6 = sentNow(), told6 = toasts.length; answers['/architect/ready'] = live6;
    doc.dispatch('click', startBtn()); await tick();
    queryRunning = true;                                                  // another analysis began meanwhile
    live6.send(JSON.stringify({ architect: { framing: readAs([]), clean: true } }) + '\n'); live6.end(); await tick();
    const other = { sent: sentNow() - sent6, said: toasts.slice(told6), read: entry.framing.read.indexOf(v4) >= 0 };
    queryRunning = false; updateNavigationButtons();
    check('the read takes a moment (0313). The coach went to another chain meanwhile: that chain\'s pane shows no row of the read and its composer is free; the read is kept - the brief shows it when '
      + 'the coach comes back - but nothing starts behind their back: Start analysis then starts it at once. Another analysis began meanwhile: nothing starts - the page\'s send would stop that '
      + 'one - and the page says that another analysis is running',
      same(away, { pane: 0, lock: ['unlock'] }) && same(left, { sent: 0, told: 0, read: true }) && backRow === 'sp-row tool read:✓CHECK questionstands on its own2 s⌘' && same(back5, { posted: 0, sent: 1 })
      && same(other, { sent: 0, said: ['Another analysis is running. Wait for it to end, or stop it.'], read: true }), [away, left, backRow, back5, other]);

    // the Pathfinder's reply after a read: a draft of its figures follows, or it went to look something up
    const v5 = await ask('Draw the series as bars, like the one of spring.'), live7 = liveBody(), sent7 = sentNow(); answers['/architect/ready'] = live7; plotted.length = 0; n = calls.length;
    answers['/architect/draft/7/71/cold1'] = [200, { plot: { data: [{ type: 'bar', y: [1, 2] }], layout: {} } }];
    doc.dispatch('click', startBtn()); await tick();
    const withFigure = reworded(readAs(['the one of spring']), 'I put the figure into the brief.', 'Draw the series as bars.', { changed: ['figures.0'], brief: { figures: [ON_DATA] }, keys: ['cold1'] });
    live7.send(JSON.stringify({ type: 'architect_draft', chain_id: 71, framing: withFigure }) + '\n'); await tick();
    const drawing = { rows: rowsNow().slice(-3), hold: $('queryInput').placeholder, fig: brief().querySelectorAll('.ar-fig .ar-wait.live').length, asks: asksNow(), sent: sentNow() - sent7, posted: posted(n).map(c => c[0]) };
    const drawnF = JSON.parse(JSON.stringify(withFigure));
    Object.assign(drawnF, { drafts: Object.assign({}, drawnF.drafts, { cold1: { basis: 'made up' } }) });
    drawnF.turns.push({ who: 'draft', drawn: [{ title: ON_DATA.title, basis: 'made up' }], v: drawnF.versions.length, secs: 5.1, cost: 0.002, call: 9 });
    live7.send(JSON.stringify({ architect: { framing: drawnF, clean: false } }) + '\n'); live7.end(); await tick();
    const drawn = { row: lastRow(), hold: $('queryInput').placeholder, figs: brief().querySelectorAll('.ar-fig.drawn').length, sent: sentNow() - sent7, drew: plotted.map(p => p.key).filter(k => k !== 'k2').join(),      // 'k2': the figure the brief had before, drawn again from the plot the page holds
                    pending: $('streamOutput').querySelectorAll('.sp-row.pending').length };
    const v6 = await ask('Draw the series as bars, as the table has it.'), sent8 = sentNow();
    const looking = readAs(['as the table has it']);
    looking.turns.push({ who: 'architect', text: 'Let me look at the table.', v: v6, cost: 0.02, call: (looking.calls || 0) + 1 }, { who: 'check', found: [{ k: 1, about: 'the table', fact: '3 rows', ran: true }], secs: 1.2 });
    looking.calls = (looking.calls || 0) + 1;
    answers['/architect/ready'] = [200, stream({ framing: looking, clean: false })];
    const wentOn = JSON.parse(JSON.stringify(looking));
    wentOn.turns.push({ who: 'architect', text: 'The table has three rows. Is that the one you mean?', v: v6, cost: 0.02, call: looking.calls + 1 }); wentOn.calls = looking.calls + 1;
    answers['/architect/say'] = [200, stream({ framing: wentOn })]; n = calls.length;
    doc.dispatch('click', startBtn()); await tick();
    const looked = { posted: posted(n), sent: sentNow() - sent8, said: pane().slice(-1)[0], hold: $('queryInput').placeholder };
    // ... or had the saved analyses read: the pane follows the count, as in any exchange, and the Pathfinder goes on after the reading
    const v7 = await ask('Draw the series as bars, as two springs ago.'), live9 = liveBody(), sent9 = sentNow(); answers['/architect/ready'] = live9; n = calls.length;
    doc.dispatch('click', startBtn()); await tick();
    live9.send(JSON.stringify({ type: 'architect_saved', read: 1, of: 3 }) + '\n'); await tick();
    const reading = { row: lastRow(), hold: $('queryInput').placeholder };
    const recalled = readAs(['as two springs ago']);
    recalled.turns.push({ who: 'architect', text: 'I am looking in your saved analyses.', v: v7, cost: 0.02, call: (recalled.calls || 0) + 1 }, { who: 'memory', found: [], of: 3, read: 3, secs: 4.2, cost: 0.01 });
    recalled.calls = (recalled.calls || 0) + 1;
    const afterIt = JSON.parse(JSON.stringify(recalled));
    afterIt.turns.push({ who: 'architect', text: 'Nothing saved is from two springs ago. What should the bars show?', v: v7, cost: 0.02, call: recalled.calls + 1 }); afterIt.calls = recalled.calls + 1;
    answers['/architect/say'] = [200, stream({ framing: afterIt })];
    live9.send(JSON.stringify({ architect: { framing: recalled, clean: false } }) + '\n'); live9.end(); await tick();
    const readThem = { posted: posted(n).map(c => c[0]), sent: sentNow() - sent9, said: pane().slice(-1)[0], hold: $('queryInput').placeholder };
    check('the Pathfinder\'s reply after a read (0313). Where a draft of its figures follows, the stream first carries the framing with the reply: the conversation shows the read and the reply, the row '
      + 'says a draft is being drawn - not that the question is read -, the composer is held with those words, the figure is a grey window, and the question is the reply\'s; the stream ends on the '
      + 'framing with the draft, which is drawn in its place. Where the reply went to look something up, the Pathfinder goes on as after any lookup: one more exchange, with nothing said. Where '
      + 'it had the saved analyses read, the row follows the count and the composer says so, and the Pathfinder goes on after the reading. None of the three starts the analysis',
      same(drawing, { rows: ['sp-row tool read skipped ar-unplaced:–CHECK questionthe Analyst cannot place “the one of spring”2 s⌘', 'sp-row tool read:✓QUESTIONupdatedstep ' + (v5 + 1), 'sp-row tool read pending:DRAWING A DRAFT'],
                      hold: 'A draft of the figures is being drawn', fig: 1, asks: 'Draw the series as bars.', sent: 0, posted: ['/architect/ready'] })
      && same(drawn, { row: 'sp-row tool read:✓FIGURES1 drawn5 s⌘', hold: 'Answer, or say what to change', figs: 1, sent: 0, drew: 'cold1', pending: 0 })
      && same(looked, { posted: [['/architect/ready', { thread_id: 7, chain_id: 71, step: v6 }], ['/architect/say', null]], sent: 0, said: 'arch|Pathfinder⌘The table has three rows. Is that the one you mean?',
                        hold: 'Answer, or say what to change' })
      && same(reading, { row: 'sp-row tool read pending:SEARCHING MEMORY1 of 3 readSkip', hold: 'Your saved analyses are being read' })
      && same(readThem, { posted: ['/architect/ready', '/architect/say'], sent: 0, said: 'arch|Pathfinder⌘Nothing saved is from two springs ago. What should the bars show?', hold: 'Answer, or say what to change' }),
      [drawing, drawn, looked, reading, readThem]);
    answers['/architect/ready'] = undefined;
  }

  // a conversation that branched (0316): the arrows and the map go through its steps, both panes follow, and what is said next goes on from the step on screen
  {
    const TH = FX.then, stepped = { status: 'framing', chain_id: 90, thread_id: 7, parentChainId: 70, queryText: 'Is B above A?', framing: JSON.parse(FS_AS_READ), tabContent: '', contentOutput: '', streamOutput: '' };
    responses.push(stepped);
    const show90 = () => { currentResponseIndex = responses.indexOf(stepped); loadResponseContent(stepped); updateNavigationButtons(); };
    show90();
    const nowS = () => [brief().querySelector('.ar-ver b').textContent, stepped.framing.step, pane().length, brief().querySelector('[data-ar="start"]').textContent, h3s(brief())].join(' / ');
    const arrow = d => doc.dispatch('click', brief().querySelector('[data-step="' + d + '"]'));
    const sameAs = (got, want) => got.step === want.step && got.tip === want.tip && got.at === want.at && same(got.turns, want.turns) && same(asideOf(got), asideOf(want));
    n = calls.length;
    const atEnd = nowS();
    arrow(-1);
    const atHand = nowS() + ' / ' + lineOf(brief(), 'thinks').className;
    arrow(-1); arrow(-1);
    const atTwo = nowS() + ' / ' + /first half/.test($('streamOutput').textContent) + ' / ' + stepped.framing.at + ' / ' + $('queryInput').placeholder, asTwo = sameAs(stepped.framing, FX.go[2]);
    arrow(1);
    const forward = nowS();
    arrow(-1);
    check('the arrows in a conversation that branched (0316): each goes to the step beside the one on screen, on the way being walked, and that step is in use at once - the tab is the brief as it '
      + 'stood there, the pane the conversation up to there, Start analysis names the step, and the composer is still the conversation\'s. The framing the page then holds is the one the engine '
      + 'would make of it. Forward from the step where the ways part, the arrow follows the way being walked. Nothing is sent',
      atEnd === '5 of 5 / 6 / 8 / Start analysis / What it is for|What you think|Period'
      && atHand === '4 of 5 / 5 / 6 / Start analysis from step 4 / What it is for|What you think|Period / ar-line changed'
      && atTwo === '2 of 5 / 2 / 4 / Start analysis from step 2 / What it is for / false / 2 / Answer, or say what to change' && asTwo
      && forward === '3 of 5 / 4 / 6 / Start analysis from step 3 / What it is for|Period' && calls.length === n && sameAs(stepped.framing, FX.go[2]), [atEnd, atHand, atTwo, forward]);

    // the coach speaks from step 2: one more way
    held(); n = calls.length;
    A.tell(TH.turns[0].text); await tick();
    const sent90 = { call: calls[n], pane: pane().slice(-2), ver: verS(brief()) }, midOff = A.map(4).off;
    loadResponseContent({ chain_id: 95, thread_id: 7, tabContent: '<div id="tab-brief" class="tab active">Brief</div>', streamOutput: '',
                          contentOutput: '<div id="content-brief" class="tab-content active">' + b.brief(TH.framing, { chain: 95, thread: 7, state: 'run' }) + '</div>' });
    const midOther = [A.map(4).n, A.map(4).off];                 // another chain's brief on screen meanwhile: the Pathfinder is not replying to it
    loadResponseContent(stepped);
    arrow(1);                                                    // pressed all the same while the Pathfinder replies: nothing
    const mid90 = stepped.framing.step;
    reply([200, stream({ framing: TH.framing })]); await tick();
    const after90 = [nowS(), $('streamOutput').querySelector('.sp-strip').textContent, pane().slice(-1)[0], verS(brief()), /by week|first half/.test($('streamOutput').textContent)].join(' / ');
    check('a message from an earlier step (0316): it names the step on screen. While the Pathfinder replies the pane shows the conversation up to that step and the message, and neither arrow '
      + 'can be pressed - an arrow pressed all the same does nothing. The reply is one more step, which follows the step the coach spoke from: the tab is at the end of a new '
      + 'way, "3 of 3", with what the reply changed; the pane holds that way - the question, the first exchange, this one - and nothing of the ways left, whose cost the strip still counts',
      same(sent90, { call: ['/architect/say', { thread_id: 7, chain_id: 90, text: 'Compare the medians instead', step: 2 }], pane: ['you|YouCompare the medians instead', 'arch wait|Pathfinderreading…'],
                     ver: 'span=Step|button-1 off|b=2 of 5|button1 off' })
      && mid90 === 2 && same(stepped.framing, TH.framing)
      && after90 === '3 of 3 / 7 / 6 / Start analysis / What it is for|Measured by / Pathfinder$0.06 / arch|Pathfinder⌘The measure is the median. / span=Step|button-1|b=3 of 3|button1 off / false',
      [sent90, mid90, after90]);

    // the map: a level of the maps drawer, in the Workflow map's drawing, with the steps for boxes
    const drawer = $('workflowMapModal'), boxes = () => $('workflowMapContainer').querySelectorAll('.wf-node');
    const lit = () => boxes().map((x, i) => (x.classList.contains('wf-node--ancestor') ? i + 1 : 0)).filter(Boolean).join();
    // what the drawer's panel says (0333): "name [tags] > its button" | what was said | the facts, a row each
    const panel = () => { const q = s => $('nodeTaskContent').querySelector(s), tags = $('nodeTaskContent').querySelectorAll('.wf-tag').map(t => t.textContent);
      return [((q('.wf-title') || {}).textContent || '') + (tags.length ? ' [' + tags.join(', ') + ']' : '') + (q('.wf-go') ? ' > ' + q('.wf-go').textContent : ''), (q('.wf-said') || {}).textContent || '']
        .filter(Boolean).concat($('nodePlotPreview').querySelectorAll('.wf-info-row').map(r => r.elements.map(e => e.textContent).join('='))).join(' | '); };
    // the way to a box (0333; until then a click on it): the box picked, then the panel's button pressed
    const goTo = i => { boxes()[i].dispatch('click'); const go = $('nodeTaskContent').querySelector('.wf-go'); if (go) go.dispatch('click'); };
    const level = key => $('mapLevels').querySelector('[data-level="' + key + '"]'), press = key => $('mapLevels').dispatch('click', level(key));
    const bar = () => $('mapLevels').elements.map(x => (x.classList.contains('map-of-chain') ? x.elements : [x]).map(y => y.textContent + (y.getAttribute('aria-pressed') === 'true' ? '*' : '') + (y.getAttribute('aria-disabled') ? '-' : '')).join(' | ')).join(' / ');
    const openIt = () => { if (drawer.style.display !== 'flex') window.MapsUI.toggle(); press('pathfinding'); };
    n = calls.length;
    window.MapsUI.toggle();                                       // the left bar's button: the first time, the drawer opens on the thread's map
    const first = [drawer.style.display, drawer.getAttribute('data-level'), bar(), level('analysis').getAttribute('title'), $('workflowMapContainer').textContent];
    press('pathfinding');
    const opened = { shown: drawer.style.display, level: drawer.getAttribute('data-level'), bar: bar(), said: level('pathfinding').getAttribute('title'), foot: panel(),
                     boxes: boxes().map(x => x.querySelector('.wf-node-label').textContent + ' > ' + x.querySelector('.wf-node-chain').textContent), kinds: boxes().map(x => x.className.replace(/wf-node--(ancestor|active|picked)/g, '').trim()).filter((c, i, all) => all.indexOf(c) === i).join(),
                     on: boxes().map((x, i) => (x.classList.contains('wf-node--active') ? i + 1 : 0)).filter(Boolean).join(), lit: lit(), wrap: $('workflowMapContainer').querySelector('.wf-graph').className,
                     edges: $('workflowMapContainer').querySelectorAll('.wf-edge').map(e => e.getAttribute('data-from') + '>' + e.getAttribute('data-to')).join(),
                     thread: $('workflowMapContainer').querySelectorAll('.wf-node-made, .wf-edge-label').length };
    boxes()[2].dispatch('mouseenter');
    const over3 = { foot: panel(), lit: lit() };
    boxes()[2].dispatch('mouseleave');
    const left3 = lit();
    const feet = [0, 1, 4, 5, 6].map(i => { boxes()[i].dispatch('mouseenter'); const f = panel(); boxes()[i].dispatch('mouseleave'); return f; });
    check('the map of a conversation (0316; in the maps drawer, 0327): the drawer opens on the thread\'s map, its switch naming the chain on screen and its two levels - Pathfinding with how '
      + 'many steps, Analysis greyed, saying why. Pathfinding pressed, the drawer holds the conversation\'s map - the level lit, how many steps and where they branch under the pointer, in the panel '
      + 'from the first what the step on screen is (0332). Every step is a box, drawn by the Workflow map\'s drawing and joined to the step it follows: on it what the coach said - the '
      + 'question as it was asked on the first, and what was done where they said nothing - and under that what the step changed, in the tab\'s words. The step on screen is the open box, and '
      + 'the way to it is lit while the pointer is nowhere. No box is a fork or carries the Workflow map\'s marks. Under the pointer a box lights its own way and the panel says (0333), as the '
      + 'Workflow map does of a chain: the step as the arrows would count it; its tags - "on screen" for the one that is, the question as it was asked on the first, the parts it changed -; the '
      + 'button that goes there, but for the step on screen; what was said, the step it follows and those that follow it, and the whole of what the Pathfinder replied (0330: its first '
      + 'sentence); when the pointer leaves, the way to the step on screen is lit again. Nothing is sent',
      same(first, ['flex', 'workflow', 'Workflow3* / Chain 3 / Pathfinding7 | Analysis-', 'Chain 3 has no turns to go back to', 'the thread\'s chains'])
      && same(opened, { shown: 'flex', level: 'pathfinding', bar: 'Workflow3 / Chain 3 / Pathfinding7* | Analysis-', said: '7 steps · 1 branch',
        foot: 'Step 3 [on screen, measured by] | Compare the medians instead | Follows=step 2 | Followed by=none | Pathfinder=The measure is the median.',
        boxes: ['Is B above A? > your question', 'Keep one arm > what it is for', 'Show it by week > figure', 'Only the first half > period', 'You changed a line > what you think', 'Is that all you need? > ',
                'Compare the medians instead > measured by'],
        kinds: 'wf-node wf-node--normal', on: '7', lit: '1,2,7', wrap: 'wf-graph wf-path-active', edges: '0>1,1>2,1>3,3>4,4>5,1>6', thread: 0 })
      && same(over3, { foot: 'Step 3 [figure] > Go to step 3 | Show it by week | Follows=step 2 | Followed by=none | Pathfinder=A line for each arm, by week.', lit: '1,2,3' }) && left3 === '1,2,7'
      && same(feet, ['Step 1 [your question] > Go to step 1 | Is B above A? | Follows=the start | Followed by=step 2 | Pathfinder=What will you do differently depending on the answer?',
                     'Step 2 [what it is for] > Go to step 2 | Keep one arm | Follows=step 1 | Followed by=3 steps | Pathfinder=What do you expect to see?',
                     'Step 4 [what you think] > Go to step 4 | You changed a line | Follows=step 3 | Followed by=step 5',
                     'Step 5 > Go to step 5 | Is that all you need? | Follows=step 4 | Followed by=none | Pathfinder=Yes. Start the analysis when you are ready. It will compare the two arms over the first half.',
                     'Step 3 [on screen, measured by] | Compare the medians instead | Follows=step 2 | Followed by=none | Pathfinder=The measure is the median.'])
      && calls.length === n, [first, opened, over3, left3, feet]);

    // a box gone to (0333: picked, and its button pressed; a click on it until then): the step is the one on screen, the drawer shuts
    goTo(2);
    const picked = [drawer.style.display, nowS(), /Show it by week/.test($('streamOutput').textContent), /medians/.test($('streamOutput').textContent), sameAs(stepped.framing, Object.assign({}, TH.framing, { step: 3, tip: 3, at: 3 }, { turns: FX.go[3].turns, aside: stepped.framing.aside }))].join(' / ');
    const asideNow = Object.keys(stepped.framing.aside).join();
    openIt();
    const again = { on: boxes().map((x, i) => (x.classList.contains('wf-node--active') ? i + 1 : 0)).filter(Boolean).join(), lit: lit(), foot: panel() };
    arrow(-1);                                                    // an arrow, with the map open: the map follows
    const followed = { shown: drawer.style.display, on: boxes().map((x, i) => (x.classList.contains('wf-node--active') ? i + 1 : 0)).filter(Boolean).join(), lit: lit(), ver: brief().querySelector('.ar-ver b').textContent };
    goTo(5);
    const toSix = [drawer.style.display, nowS()].join(' / ');
    openIt();
    currentResponseIndex = 0; loadResponseContent(responses[0]); updateNavigationButtons();      // another chain on screen, the map still open: the drawer follows
    const elsewhere = [drawer.style.display, drawer.getAttribute('data-level'), bar(), level('pathfinding').getAttribute('title'), stepped.framing.step].join(' / ');
    show90();
    const backOn = [drawer.style.display, drawer.getAttribute('data-level'), bar()].join(' / ');      // the brief's chain again: the drawer is where it went
    window.MapsUI.shut();
    check('a box gone to (0316; picked and its button pressed, 0333): the drawer shuts and the step is the one on screen and in use - at the end of the way that was left, the tab shows its figure and the pane that exchange, and '
      + 'nothing of the ways taken since; the steps off that way are set aside. Opened again, the map has that step open and its way lit, and its panel says what that step is (0332) - nothing of the box last under the pointer. While the drawer is open the map follows its brief: an '
      + 'arrow pressed, and the box of the step now on screen is the open one. The end of another way is gone to so too. With another chain on screen - one with no brief - the drawer '
      + 'stays open and goes to the thread\'s map, the switch naming that chain and why it has no steps to show; back on the brief\'s chain it stays there. Nothing is sent',
      picked === 'none / 3 of 3 / 3 / 6 / Start analysis / What it is for|What it will look like / true / false / true' && asideNow === '4,6,7'
      && same(again, { on: '3', lit: '1,2,3', foot: 'Step 3 [on screen, figure] | Show it by week | Follows=step 2 | Followed by=none | Pathfinder=A line for each arm, by week.' }) && same(followed, { shown: 'flex', on: '2', lit: '1,2', ver: '2 of 3' })
      && toSix === 'none / 5 of 5 / 6 / 8 / Start analysis / What it is for|What you think|Period' && elsewhere === 'flex / workflow / Workflow3* / Chain 1 / Pathfinding- | Analysis- / Chain 1 was asked without the Pathfinder / 6'
      && backOn === 'flex / workflow / Workflow3* / Chain 3 / Pathfinding7 | Analysis-' && calls.length === n,
      [picked, asideNow, again, followed, toSix, elsewhere, backOn]);

    // the tab of a run: the map is read
    const ran = { chain_id: 91, thread_id: 7, queryText: 'Is B above A?', tabContent: '<div id="tab-brief" class="tab active">Brief</div>',
                  contentOutput: '<div id="content-brief" class="tab-content active">' + b.brief(TH.framing, { chain: 91, thread: 7, state: 'run' }) + '</div>', streamOutput: '<div class="kept">the run\'s pane</div>' };
    responses.push(ran); currentResponseIndex = responses.indexOf(ran); loadResponseContent(ran); updateNavigationButtons();
    openIt();
    const ranMap = [drawer.style.display, drawer.getAttribute('data-level'), boxes().length, lit()].join(' / ');
    goTo(3);
    const ranAt = [drawer.style.display, brief().querySelector('.ar-ver b').textContent, brief().getAttribute('data-shown'), brief().getAttribute('data-state'), h3s(brief()), !!brief().querySelector('.pen, [data-ar="start"]'),
                   $('streamOutput').textContent, same(JSON.parse(brief().getAttribute('data-framing')), TH.framing)].join(' / ');
    check('the map on the tab of a run (0316): the same drawer, with the step the run started from open. A box gone to shows the brief as it stood at that step, to be read - the tab alone '
      + 'changes: its framing, the run\'s pane and the record stay as they are, and nothing is sent',
      ranMap === 'flex / pathfinding / 7 / 1,2,7' && ranAt === 'none / 3 of 5 / 4 / run / What it is for|Period / false / the run\'s pane / true' && calls.length === n, [ranMap, ranAt]);
    openIt();
    doc.dispatch('click', brief().querySelector('[data-step="-1"]'));      // an arrow on the run's tab, the map open: the map follows
    const ranFollows = [drawer.style.display, brief().querySelector('.ar-ver b').textContent, boxes().map((x, i) => (x.classList.contains('wf-node--active') ? i + 1 : 0)).filter(Boolean).join(), lit()].join(' / ');
    // the drawer on the Workflow map: the conversation's is not drawn over it
    press('workflow');
    doc.dispatch('click', brief().querySelector('[data-step="1"]'));
    const threads = [drawer.style.display, drawer.getAttribute('data-level'), $('workflowMapContainer').textContent, brief().querySelector('.ar-ver b').textContent].join(' / ');
    window.MapsUI.shut();
    check('the map while its drawer is open (0316): an arrow pressed on a run\'s tab - back from a step off the way the run took, to the step where the ways part, counted on the run\'s way '
      + 'again - and the box of the step now on screen is the open one, its way lit. Where the drawer is on the Workflow map, the conversation\'s map is not drawn over it: the tab steps - forward, '
      + 'along the run\'s way - and the drawer is the thread\'s',
      ranFollows === 'flex / 2 of 3 / 2 / 1,2' && threads === 'flex / workflow / the thread\'s chains / 3 of 3', [ranFollows, threads]);

    // the map's words: a conversation of one step; a step in which the question was read, one in which the Pathfinder went on by itself, a step that changed two lines of one part
    const mapOf = framing => { const e = { chain_id: 92, thread_id: 7, queryText: 'Q?', tabContent: '<div id="tab-brief" class="tab active">Brief</div>',
                                             contentOutput: '<div id="content-brief" class="tab-content active">' + b.brief(framing, { chain: 92, thread: 7, state: 'run' }) + '</div>', streamOutput: '' };
      responses.push(e); currentResponseIndex = responses.indexOf(e); loadResponseContent(e); updateNavigationButtons(); openIt();
      const replies = [];      // the Pathfinder's reply as the panel holds it: its lines kept (0332)
      const feet = boxes().map(x => { x.dispatch('mouseenter'); const f = panel(); replies.push(...$('nodePlotPreview').querySelectorAll('.wf-info-conclusion b .wf-said').map(r => r.textContent)); x.dispatch('mouseleave'); return f; });
      const out = { sub: level('pathfinding').getAttribute('title'), boxes: boxes().map(x => x.className.replace(/ wf-node--(ancestor|active|picked)/g, '') + ': ' + x.querySelector('.wf-node-label').textContent + ' > ' + x.querySelector('.wf-node-chain').textContent),
                    feet, replies, forks: $('workflowMapContainer').querySelectorAll('.wf-edge-label').length };
      window.MapsUI.shut(); responses.pop(); return out; };
    const ONE = { versions: F1.versions, steps: [{ k: 1, from: 0, v: 1, made: [1], turns: 0 }], step: 1, tip: 1 };
    const DRAWN = 'A draft of the figure is drawn: B > A & <the median>.\nSay if it should change.';      // a reply on two lines, with what reads as markup (0332)
    const WORDY = { versions: [F1.versions[0], { n: 2, by: 'architect', changed: ['rests_on.0'], brief: { question: 'Is B above A?', rests_on: [{ text: 'a' }] } },
                               { n: 3, by: 'architect', changed: ['rests_on.1', 'also_check.0'], brief: { question: 'Is B above A?', rests_on: [{ text: 'a' }, { text: 'b' }], also_check: [{ text: 'c' }] } }],
                    turns: [{ who: 'person', text: 'User requested variations of the plot, on two grounds.' }, { who: 'architect', text: 'Checking this against the data.', v: 2 }, { who: 'check', found: [] },
                            { who: 'architect', text: 'Both hold. Anything else?', v: 3 }, { who: 'reader', missing: [], v: 3 }, { who: 'architect', text: DRAWN, v: 3 }],
                    steps: [{ k: 1, from: 0, v: 1, made: [1], turns: 0 }, { k: 2, from: 1, v: 3, made: [2, 3], turns: 4 }, { k: 3, from: 2, v: 3, made: [], turns: 1 }, { k: 4, from: 3, v: 3, made: [], turns: 1 }],
                    step: 4, tip: 4 };
    const one = mapOf(ONE), wordy = mapOf(WORDY);
    check('the map\'s words (0316): a conversation of one step is said so - "1 step", and no word of branches where it has none. A box where the coach said nothing says what was done: the '
      + 'question was read; the Pathfinder went on. Under a box each part the step changed is named once, whatever the lines; the panel gives the Pathfinder\'s last reply of the step - as text, '
      + 'its lines kept (0332). What a box '
      + 'says makes it no fork of the Workflow map\'s: the coach\'s own words may be the Workflow map\'s',
      same(one, { sub: '1 step', boxes: ['wf-node wf-node--normal: Is B above A? > your question'],
                  feet: ['Step 1 [on screen, your question] | Is B above A? | Follows=the start | Followed by=none'], replies: [], forks: 0 })
      && wordy.sub === '4 steps' && wordy.forks === 0
      && same(wordy.boxes, ['wf-node wf-node--normal: Is B above A? > your question', 'wf-node wf-node--normal: User requested variations o... > why you think so · other explanations',
                            'wf-node wf-node--normal: Question check > ', 'wf-node wf-node--normal: The Pathfinder went on > '])
      && same(wordy.feet.slice(1), ['Step 2 [why you think so, other explanations] > Go to step 2 | User requested variations of the plot, on two grounds. | Follows=step 1 | Followed by=step 3 | Pathfinder=Both hold. Anything else?',
                                    'Step 3 > Go to step 3 | Question check | Follows=step 2 | Followed by=step 4',
                                    'Step 4 [on screen] | The Pathfinder went on | Follows=step 3 | Followed by=none | Pathfinder=' + DRAWN])
      && same(wordy.replies, ['Both hold. Anything else?', DRAWN]), [one, wordy]);
    // why the level cannot be shown
    const offOf = (e, place) => { responses.push(e); currentResponseIndex = responses.indexOf(e); loadResponseContent(e); updateNavigationButtons(); const out = A.map(place); responses.pop(); return [out.n, out.off]; };
    const noBrief = offOf({ chain_id: 93, thread_id: 7, queryText: 'Q?', tabContent: '<div id="tab-answer" class="tab active">Answer</div>', contentOutput: '<div id="content-answer">an answer</div>', streamOutput: '' }, 4);
    const oldBrief = offOf({ chain_id: 94, thread_id: 7, queryText: 'Q?', tabContent: '<div id="tab-brief" class="tab active">Brief</div>',
                             contentOutput: '<div id="content-brief" class="tab-content active">' + b.brief(OLD3, { chain: 94, thread: 7, state: 'run' }) + '</div>', streamOutput: '' }, 5);
    check('why the Pathfinding map cannot be shown (0327): a chain asked without the Pathfinder has no brief, and a brief kept before steps has no map of them - the level says which, naming the '
      + 'chain by its place in the thread; while the Pathfinder replies to the brief on screen it says that - and the map of another chain\'s brief can be shown meanwhile',
      same(noBrief, [0, 'Chain 4 was asked without the Pathfinder']) && same(oldBrief, [0, "Chain 5's brief was made before version 2.8.1"]) && midOff === 'The Pathfinder is replying' && same(midOther, [7, '']),
      [noBrief, oldBrief, midOff, midOther]);
    // the Workflow map, drawn by the same drawing with nothing said of another map: as it was
    const CHAINS = [{ chain_id: 11, parentChainId: null, queryText: 'A first question', streamOutput: '', technicalAnswer: '<p>B is above A by two units, on plot means.</p>' },
                    { chain_id: 12, parentChainId: 11, queryText: 'User requested variations', streamOutput: '' }, { chain_id: 13, parentChainId: 11, queryText: 'A brief', status: 'framing', framing: F1 }];
    window.WorkflowGraph.render($('workflowMapContainer'), CHAINS, 0);
    const wrap = () => $('workflowMapContainer').querySelector('.wf-graph').className;
    const thread = { boxes: boxes().map(x => x.className + ': ' + x.textContent), rest: wrap(), forks: $('workflowMapContainer').querySelectorAll('.wf-edge-label').map(x => x.textContent).join(),
                     traces: boxes().map(x => !!x.querySelector('.wf-node-map')).join() };
    boxes()[2].dispatch('mouseenter');
    const threadOver = [panel(), wrap(), lit()].join(' / ');
    boxes()[2].dispatch('mouseleave');
    check('the Workflow map, drawn by the drawing the conversation\'s map now shares (0316), is as it was: a box says its chain and how its question was made - and no longer has a way '
      + 'into the code trace (0330); a fork is a fork, with its badge; nothing is lit while the pointer is nowhere; under the pointer a box lights its way and the panel is the thread\'s own - '
      + 'the chain and its tags, the button that goes there, what it follows and what follows it, its id (0333)',
      same(thread, { boxes: ['wf-node wf-node--normal wf-node--active wf-node--picked: A first questionChain: 11', 'wf-node wf-node--fork: User requested variationsChain: 12',
                             'wf-node wf-node--normal wf-node--notrun: A briefChain: 13not run'], rest: 'wf-graph', forks: 'Fork', traces: 'false,false,false' })
      && threadOver === 'Chain 3 [not run] > Go to chain 3 | A brief | Follows=chain 1 | Followed by=none | Id=13 / wf-graph wf-path-active / 1,3' && wrap() === 'wf-graph', [thread, threadOver, wrap()]);

    // the panel says everything (0330): a long question, on two lines, with what reads as markup in it, and a long first sentence of what the chain concluded
    const LONG_Q = 'Across the three regimes, ' + 'how do the plots on loam compare with the plots on clay and on sand, '.repeat(4) + 'and is the gap <larger> than the spread?\nSay it per regime.';
    const LONG_A = 'Regime B is above regime A on every soil type, '.repeat(6) + 'by about two units.';
    window.WorkflowGraph.render($('workflowMapContainer'), [{ chain_id: 14, parentChainId: null, queryText: LONG_Q, streamOutput: '', technicalAnswer: '<p>' + LONG_A + ' The rest is noise.</p>' }], 0);
    boxes()[0].dispatch('mouseenter');
    const wholeFoot = [($('nodeTaskContent').querySelector('.wf-said') || {}).textContent, ($('nodePlotPreview').querySelector('.wf-info-conclusion b') || {}).textContent];
    boxes()[0].dispatch('mouseleave');
    check('the Workflow map\'s panel says everything (0330): the question whole, its lines kept, as text - and the first sentence of what the chain concluded, whole; they were cut at 200 '
      + 'and 240 characters. The pane scrolls',
      same(wholeFoot, [LONG_Q, LONG_A]) && LONG_Q.length > 200 && LONG_A.length > 240, wholeFoot);

    // the branch button on the Pathfinder's cards (0325): the way to a step with no map opened
    {
      const carded = { status: 'framing', chain_id: 91, thread_id: 7, parentChainId: 70, queryText: 'Is B above A?', framing: JSON.parse(FS_AS_READ), tabContent: '', contentOutput: '', streamOutput: '' };
      responses.push(carded);
      currentResponseIndex = responses.indexOf(carded); loadResponseContent(carded); updateNavigationButtons();
      const archCards = () => $('streamOutput').querySelectorAll('.ar-msg.arch');
      const cards = () => archCards().map(m => { const x = m.querySelector('.sp-branch'); return x ? x.getAttribute('title') + ' > ' + x.getAttribute('data-step') + (x.classList.contains('on') ? ' on' : '') : '-'; });
      const press = i => doc.dispatch('click', archCards()[i].querySelector('.sp-branch'));
      const where = () => [brief().querySelector('.ar-ver b').textContent, carded.framing.step, carded.framing.tip, brief().querySelector('[data-ar="start"]').textContent].join(' / ');
      const head1 = archCards()[0].querySelector('.who'), mark1 = head1.querySelector('.sp-branch');
      const looks = [head1.elements.map(e => e.className).join(' | '), head1.textContent, mark1.getAttribute('type'), mark1.getAttribute('data-ar'), mark1.getAttribute('aria-label'), mark1.textContent, mark1.querySelectorAll('circle').length];
      n = calls.length;
      const atEnd91 = [cards(), where()];
      press(2);                                                  // the card of the third step of the way
      const atThree = [cards(), where(), pane().length, sameAs(carded.framing, FX.go[4])];
      press(2);                                                  // lit: the end again
      const backEnd = [cards(), where(), sameAs(carded.framing, FX.go[6])];
      press(0);
      const atOne = [cards(), where(), pane().length];
      press(0);
      arrow(-1);                                                 // the step before the end is a line changed by hand: no card of the Pathfinder's is its own
      const atHand91 = [cards(), where()];
      arrow(1);
      check('the branch button on the Pathfinder\'s cards (0325): while a brief is not yet run, the Pathfinder\'s card of every step of the way but its end has one, in the card\'s head before the button of '
        + 'its prompt - the Git branch mark, saying its step as the arrows count it. A click is a click on the step\'s box of the map: the pane ends at that card and the tab is the brief as it '
        + 'stood there, the framing the one the engine would make of it; the button of the step in use is lit, and a click on it brings the end of the way back. A step with no card of the '
        + 'Pathfinder\'s - a line changed by hand - lights none. Nothing is sent',
        same(looks, ['sp-branch | agent-instructions-btn sp-prompt', 'Pathfinder⌘', 'button', 'from', 'Branch from step 1', '', 2])
        && same(atEnd91, [['Branch from step 1 > 1', 'Branch from step 2 > 2', 'Branch from step 3 > 4', '-'], '5 of 5 / 6 / 6 / Start analysis'])
        && same(atThree, [['Branch from step 1 > 1', 'Branch from step 2 > 2', 'Branch from step 3 > 4 on'], '3 of 5 / 4 / 6 / Start analysis from step 3', 6, true])
        && same(backEnd, [atEnd91[0], atEnd91[1], true])
        && same(atOne, [['Branch from step 1 > 1 on'], '1 of 5 / 1 / 6 / Start analysis from step 1', 2])
        && same(atHand91, [['Branch from step 1 > 1', 'Branch from step 2 > 2', 'Branch from step 3 > 4'], '4 of 5 / 5 / 6 / Start analysis from step 4'])
        && same([cards(), where()], atEnd91) && calls.length === n, [looks, atEnd91, atThree, backEnd, atOne, atHand91]);

      // which cards: by the builder
      const marks = (framing, o, fold) => el(fold ? b.fold({ chain_id: 91, queryText: 'q', framing }) : b.pane({ chain_id: 91, queryText: 'q', framing }, o)).querySelectorAll('.ar-msg.arch')
        .map(m => { const x = m.querySelector('.sp-branch'); return x ? x.getAttribute('data-step') + (x.classList.contains('on') ? ' on' : '') : '-'; }).join();
      const TWICE = { versions: FS.versions.slice(0, 1), steps: [{ k: 1, from: 0, v: 1, made: [1], turns: 3 }, { k: 2, from: 1, v: 1, made: [], turns: 2 }], step: 2, tip: 2,
                      turns: [{ who: 'architect', text: 'I will look that up.' }, { who: 'check', found: [] }, { who: 'architect', text: 'It is there. What next?' }, { who: 'person', text: 'Go on' },
                              { who: 'architect', text: 'Ready.' }] };
      const which = [marks(wholeAt(4)), marks(wholeAt(4), { sent: 'And by week?', waiting: true }), marks(wholeAt(4), null, true), marks(OLD3), marks(TWICE), marks(A.go(TWICE, 1))];
      check('... which cards have it: none while the Pathfinder replies - nor the card that says it is reading -, none in the fold above a run, none in a conversation kept before steps. Where the Pathfinder spoke twice in a step - it looked '
        + 'something up and went on - the button is on its last message of the step; with that step in use and the way going further, there too, lit',
        same(which, ['1,2,4 on', '-,-,-,-', '-,-,-', '-,-,-,-', '-,1,-', '-,1 on']), which);

      // a line of the brief being typed when a button is pressed: the line is kept first, as the arrows have it
      const briefWas = answers['/architect/brief'];
      answers['/architect/brief'] = body => { const f = JSON.parse(JSON.stringify(carded.framing)); f.versions.push({ n: f.versions.length + 1, by: 'person', changed: body.changed, brief: body.brief });
        f.steps.push({ k: f.steps.length + 1, from: body.step, v: f.versions.length, made: [f.versions.length], turns: 0, found: 0, proposed: 0 }); f.step = f.tip = f.steps.length; delete f.at;
        return [200, { framing: f }]; };
      const typeIn = text => { doc.dispatch('click', lineOf(brief(), 'decision').querySelector('.pen')); lineOf(brief(), 'decision').querySelector('.ar-input').value = text; };
      const sentSince = () => calls.slice(n).map(c => [c[0], c[1].changed, c[1].step]);
      typeIn('Keep one arm next season'); n = calls.length;
      press(1); await tick();
      const typedThen = [sentSince(), where(), cards()];
      typeIn('Keep both arms'); n = calls.length;
      press(1); await tick();                                    // the lit one: the line kept is one more step, and the end of the way
      const typedLit = [sentSince(), where(), cards()];
      check('... with a line of the brief being typed: the line is kept first - one more step, the coach\'s - then the card\'s step is gone to; the lit button then goes to the end of the way as it '
        + 'stands - the step just made, which follows the step the coach stood on',
        same(typedThen, [[['/architect/brief', ['decision'], 6]], '2 of 6 / 2 / 7 / Start analysis from step 2', ['Branch from step 1 > 1', 'Branch from step 2 > 2 on']])
        && same(typedLit, [[['/architect/brief', ['decision'], 2]], '3 of 3 / 8 / 8 / Start analysis', ['Branch from step 1 > 1', 'Branch from step 2 > 2']]), [typedThen, typedLit]);
      answers['/architect/brief'] = briefWas;
      responses.splice(responses.indexOf(carded), 1);
    }
    show90();
  }

  // a chain kept with its brief: the tab alone goes through the steps
  const done = { chain_id: 80, thread_id: 7, queryText: 'A framed question', tabContent: '<div id="tab-brief" class="tab active">Brief</div>',
                 contentOutput: '<div id="content-brief" class="tab-content active">' + b.brief(F3, { chain: 80, state: 'run' }) + '</div>', streamOutput: '' };
  responses.push(done); currentResponseIndex = 2; loadResponseContent(done); updateNavigationButtons();
  doc.dispatch('click', brief().querySelector('[data-step="-1"]'));
  doc.dispatch('click', brief().querySelector('[data-step="-1"]'));
  const first = brief().querySelector('.ar-ver b').textContent + '|' + !!brief().querySelector('.why') + '|' + brief().querySelectorAll('.pen').length;
  doc.dispatch('click', brief().querySelector('[data-step="-1"]'));
  n = calls.length;
  doc.dispatch('click', brief().querySelector('h1'));
  check('a restored chain: its Brief tab goes through the steps from its own markup, down to the first and no further; nothing can be changed, nothing is sent',
    first === '1 of 3|false|0' && brief().querySelector('.ar-ver b').textContent === '1 of 3' && !brief().querySelector('[data-ar="start"]') && brief().getAttribute('data-state') === 'run' && calls.length === n && A.mark(done) === 'Pathfinder', first);

  // what the run's report says against its brief comes to that run's Brief tab (0312)
  {
    const tabs = $('contentOutput'), shownNow = () => brief().querySelector('.ar-ver b').textContent, cardNow = () => brief().querySelectorAll('.ar-against').length;
    const lastOf = () => { const all = brief().elements; return all[all.length - 1].className; };
    A.turnedOut(tabs, cut.against);
    const onFirst = [shownNow(), cardNow(), brief().getAttribute('data-against') === cut.against];        // the tab stands on its first step: the rows are kept, no card is shown
    doc.dispatch('click', brief().querySelector('[data-step="1"]'));
    const onSecond = [shownNow(), cardNow()];
    doc.dispatch('click', brief().querySelector('[data-step="1"]'));
    const onLast = [shownNow(), cardNow(), lastOf(), same(rowsOf(brief()), ROWS)];
    A.turnedOut(tabs, cut.against);
    const twice = [cardNow(), lastOf()];
    A.turnedOut(tabs, '<div class="r"><span class="k">You expected</span> <span class="t">again</span> <span class="v ok">met</span></div>');
    const other = [cardNow(), lastOf(), brief().querySelector('.ar-against .t').textContent, brief().getAttribute('data-against').includes('again')];
    A.turnedOut(tabs, '');
    const kept1 = [cardNow(), brief().getAttribute('data-against').includes('again')];
    doc.dispatch('click', brief().querySelector('[data-step="-1"]'));
    const back = [shownNow(), cardNow(), brief().getAttribute('data-against').includes('again')];
    doc.dispatch('click', brief().querySelector('[data-step="1"]'));
    const forth = [shownNow(), cardNow(), brief().querySelector('.ar-against .t').textContent];
    const nowhere = [(() => { try { A.turnedOut(null, cut.against); A.turnedOut($('streamOutput'), cut.against); return 'quiet'; } catch (e) { return String(e); } })(), $('streamOutput').querySelectorAll('.ar-against').length,
                     brief().querySelector('.ar-against .t').textContent];        // the page's own brief is not the one meant: it keeps what it had
    check('what a run\'s report says against its brief comes to that run\'s Brief tab (0312), in the tabs it is handed - the page\'s, or the holder of a run that goes on off screen. The rows are kept in the '
      + 'brief\'s markup whichever step is on screen; the card stands under the brief the run was under and under no other, so the arrows show it and take it away, from the markup alone. Said '
      + 'again, there is one card still, the last thing on the tab; other rows take its place; an answer that says nothing leaves the tab as it is - a chain shown again has its card already. Tabs '
      + 'without a brief, and none at all, take nothing - and the brief on the page, which is not among them, keeps what it had',
      same(onFirst, ['1 of 3', 0, true]) && same(onSecond, ['2 of 3', 0]) && same(onLast, ['3 of 3', 1, 'ar-against', true]) && same(twice, [1, 'ar-against'])
      && same(other, [1, 'ar-against', 'again', true]) && same(kept1, [1, true]) && same(back, ['2 of 3', 0, true]) && same(forth, ['3 of 3', 1, 'again']) && same(nowhere, ['quiet', 0, 'again']),
      [onFirst, onSecond, onLast, twice, other, kept1, back, forth, nowhere]);
  }

  // ---- the page's hooks, from the source ----
  const root = path.join(__dirname, '..', '..', 'web_app'), js = f => fs.readFileSync(path.join(root, 'static', 'js', f), 'utf8'), css = f => fs.readFileSync(path.join(root, 'static', 'css', f), 'utf8');
  const html = fs.readFileSync(path.join(root, 'templates', 'index.html'), 'utf8'), qp = js('query-processing.js'), wm = js('workflow-management.js'), cr = js('content-rendering.js');
  check('index.html: the switch sits after the mode control, in the composer\'s row of icons; architect.js is loaded after the modules it leans on; the app starts it',
    html.indexOf('id="architectSwitch"') > html.indexOf('id="modeParams"') && html.indexOf('id="architectSwitch"') < html.indexOf('id="submitQuery"')
    && /<button id="architectSwitch" type="button" class="ar-switch" aria-pressed="false" title="Pathfinder: write a brief before the analysis runs">\s*<svg[^\n]*\s*<span>Pathfinder<\/span>/.test(html)
    && html.indexOf('js/architect.js') > html.indexOf('js/code-map.js') && html.indexOf('js/architect.js') > html.indexOf('js/routines.js') && js('core.js').includes('window.ArchitectUI.initialize();'));
  check('the send: only the composer\'s own send is framed (the button, Ctrl+Enter); with a brief not yet run on screen what is typed is said to the Pathfinder and nothing else starts; a brief\'s analysis names its run and where it attached',
    qp.includes("submitQueryButton.addEventListener('click', () => handleQuerySubmit({ typed: true }));") && js('ui-controls.js').includes('handleQuerySubmit({ typed: true });')
    && qp.includes('if (typed && window.ArchitectUI.isOn()) {') && qp.indexOf('window.ArchitectUI.framingInView()') < qp.indexOf('if (typed && window.ArchitectUI.isOn())')
    && qp.includes('if (typed) window.ArchitectUI.tell(query);') && qp.indexOf('if (typed) window.ArchitectUI.tell(query);') < qp.indexOf("showSystemMessage('This brief has not been run")
    && qp.indexOf('stopAutoExplore();') < qp.indexOf('window.ArchitectUI.framingInView()') && qp.indexOf('window.ArchitectUI.open(query);') < qp.indexOf('queryRunning = true;')
    && qp.includes('if (framed) requestBody.run_id = framed.chain_id;') && qp.includes('chain_id: framed ? framed.parentChainId : currentData.chain_id,')
    && [...cr.matchAll(/handleQuerySubmit\(([^)]*)\)/g)].every(m => !m[1].includes('typed')));
  check('the live chain of a brief: the same chain runs, the framing folded above it; an analysis the server did not start leaves the brief',
    qp.includes('beginLiveChain(framed);') && qp.indexOf('beginLiveChain(framed);') < qp.indexOf('window.ArchitectUI.started(framed);') && wm.includes("framed.status = 'running';") && wm.includes('liveState.index = responses.indexOf(framed);')
    && wm.includes('function revertLiveChain(framed) {') && qp.includes('if (framed) window.ArchitectUI.notStarted(framed);') && qp.includes('if (framed && !streaming) window.ArchitectUI.notStarted(framed, error.message);'));
  check('the chain on screen: a brief not yet run is drawn when its chain is loaded, and holds the composer wherever the view changes; it is not saved with its thread, and the Save pill stays away',
    wm.includes('if (window.ArchitectUI) window.ArchitectUI.restore(response);') && js('ui-controls.js').includes('if (window.ArchitectUI) window.ArchitectUI.onChain(responses[currentResponseIndex]);')
    && qp.includes("resp.thread_id === threadId && resp.status !== 'framing'") && qp.includes("currentResponse.status !== 'running' && currentResponse.status !== 'framing'"));
  check('the tabs: a Brief tab takes the markup architect.js builds. Where the answer is rendered, what it says against its brief is cut out of it (0312) - the technical version\'s goes to the Brief tab '
    + 'among the tabs the answer is rendered in, the plain version\'s goes nowhere - and before the answer\'s own copy for the toggle is kept; nothing dresses the answer any more',
    /case 'comparison':[^\n]*\n\s*case 'brief':[^\n]*\n\s*content = String\(data == null \? '' : data\);/.test(cr)
    && cr.includes("const cut = window.ArchitectUI.cutAnswer(finalContent);\n                finalContent = cut.html;\n                window.ArchitectUI.turnedOut(_root, cut.against);")
    && cr.includes("if (window.ArchitectUI) finalContent = window.ArchitectUI.cutAnswer(finalContent).html;") && (cr.match(/cutAnswer\(/g) || []).length === 2 && (cr.match(/turnedOut\(/g) || []).length === 1
    && cr.indexOf('window.ArchitectUI.turnedOut(_root, cut.against);') < cr.indexOf("currentData.technicalAnswer = '<div class=\"markdown-content content-body\">' + finalContent + '</div>';")
    && cr.includes("const _root = (typeof liveTargets === 'function') ? liveTargets().content : document.getElementById('contentOutput');")
    && !cr.includes('dressAnswer') && !js('architect.js').includes('dressAnswer'), [(cr.match(/cutAnswer\(/g) || []).length, (cr.match(/turnedOut\(/g) || []).length]);
  const graph = js('workflowGraph.js');
  check('the Workflow map: a box says how its question was made, a brief not yet run that it is; no box has a way into the code trace (0330)',
    graph.includes("var made = of ? (of.tag ? of.tag(resp, idx) : '') : (window.ArchitectUI ? window.ArchitectUI.mark(resp) : '');") && graph.includes("madeSpan.className = 'wf-node-made';") && graph.includes("if (made === 'not run') div.classList.add('wf-node--notrun');")
    && !graph.includes('wf-node-map'));
  const shell = css('shell.css'), tabsCss = css('tabs.css'), paneCss = css('pane.css');
  check('the stylesheets: the switch and the map\'s tag in shell.css, the conversation\'s cards and choices in pane.css, the Brief tab and - on it since 0312, in the answer no more - the card of what the '
    + 'report says against the brief in tabs.css, with a place for a part that goes as the report wrote it',
    shell.includes('.left-panel .icon-row .ar-switch.on {') && shell.includes('#workflowMapModal .wf-node-made {') && shell.includes('#workflowMapModal .wf-node--notrun {')
    && paneCss.includes('#streamOutput .ar-msg {') && paneCss.includes('#streamOutput .ar-msg.arch {')
    && paneCss.includes('#streamOutput .ar-msg.arch .who { display: flex; align-items: center; color: var(--c-model); }')      // the head of the Pathfinder's card (0325): its buttons in the line, at its end, one size
    && paneCss.includes('#streamOutput .ar-msg.arch .who > button { order: 0; flex-shrink: 0; box-sizing: border-box; min-width: 22px; height: 18px; margin: 0 0 0 6px;')
    && paneCss.includes('#streamOutput .ar-msg.arch .who > button:first-child { margin-left: auto; }') && paneCss.includes('#streamOutput .ar-msg.arch .sp-branch.on { color: var(--accent-color); border-color: var(--accent-color); }')
    && !/#streamOutput \.ar-msg\.arch [^{]*\{[^}]*float:/.test(paneCss) && paneCss.includes('#streamOutput .ar-msg.wait {') && paneCss.includes('#streamOutput .ar-choice {')
    && tabsCss.includes('#content-brief .ar-line.changed::before {') && tabsCss.includes('#content-brief .ar-foot { position: sticky;')
    && tabsCss.includes('#content-brief .ar-line .tick {') && tabsCss.includes('#content-brief .ar-line .tick.on {')
    && tabsCss.includes('#content-brief .ar-against { display: grid; grid-template-columns: max-content 1fr max-content;') && tabsCss.includes('#content-brief .ar-against .r { display: contents; }') && ['ok', 'no', 'q'].every(v => tabsCss.includes('#content-brief .ar-against .v.' + v + ' {'))
    && tabsCss.includes('#content-brief .ar-against .as-is { grid-column: 1 / -1; min-width: 0; }') && !tabsCss.includes('#content-answer .ar-against'));
  check('the stylesheets, 0308: the version control with its name and its arrows, the one control that adds a part and the list it opens, the line of what is always tested, a saved analysis built on and '
    + 'what the readings found are styled in tabs.css; what a reading found under its row in pane.css. The pencil is in view at rest; the cross shows under the mouse, and stays in view on a saved '
    + 'analysis built on. Nothing is left of the wording\'s card, the parts on offer by chips, a passage as a line, or the button that had the saved analyses read; the page\'s words for the Brief tab '
    + 'are plain ones, and none says a part is "not said" or "left to" anyone',
    ['.ar-top, #content-plan .br-top {', '.ar-top .label, #content-plan .br-top .label {', '.ar-gets {', '.ar-ver, #content-plan .br-ver {', '.ar-ver .k, #content-plan .br-ver .k {', '.ar-ver b, #content-plan .br-ver b {',
     '.ar-ver button, #content-plan .br-ver button {', '.ar-ver button:disabled, #content-plan .br-ver button:disabled {', '.ar-always {', '.ar-more {', '.ar-add {', '.ar-kinds {', '.ar-kinds button {',
     '.ar-built {', '.ar-memory {', '.ar-memory .note {', '.ar-memory .q {', '.ar-memory .qt {', '.ar-memory .why {', '.ar-memory .tag {'].every(s => tabsCss.includes('#content-brief ' + s))
    && ['.ar-found {', '.ar-found .hd {', '.ar-found .q {', '.ar-found .ar-open {'].every(s => paneCss.includes('#streamOutput ' + s))
    && /#content-brief \.ar-line \.pen, #content-brief \.ar-line \.drop \{[^}]* opacity: \.85; \}/.test(tabsCss) && tabsCss.includes('#content-brief .ar-line .drop { opacity: 0; }')
    && !/\.pen\b[^{}]*\{[^}]*opacity: 0;/.test(tabsCss)
    && tabsCss.includes('#content-brief .ar-line:hover .drop, #content-brief .ar-line .drop:focus-visible, #content-brief .ar-built .drop { opacity: .85; }')
    && !/ar-wording|ar-use|ar-chips|ar-grid|ar-look|ar-saved \.|\.tx\.add|\.ar-ver \.step|\.src\.mem/.test(tabsCss) && !/ar-wording|ar-use/.test(paneCss)
    && !/not said|left to the Analyst|unsaid|Use this wording|Look in saved|Fixed before the run|from your answer|changed by you/.test(js('architect.js'))
    && ["asked: 'What the Analyst will be asked'", "gets: 'This is what the Analyst gets. Change any line before you start.'", "decision: 'What it is for'", "rests_on: 'Why you think so'", "expects: 'What you expect to see'",
        "would_change: 'What would change your mind'", "also_check: 'Other explanations to test'", "builds: 'Builds on'", "another: 'Another explanation to test'",
        "always: 'Always tested on data: chance, measurement error, how the cases were chosen.'", "step: 'Step', of: (k, n) => k + ' of ' + n, before: 'The step before', after: 'The step after',", "start: 'Start analysis', startFrom: k => 'Start analysis from step ' + k,", "view: 'View'",
        "memory: 'Found in your saved analyses', memoryNote: 'For you to read. The Analyst gets only what you build on.'", "['comparison', 'What is compared'], ['measure', 'Measured by'], ['period', 'Period']",
        "opened: 'READ'", "question: 'QUESTION', updated: 'updated'"].every(s => js('architect.js').includes(s)));
  const engine = f => fs.readFileSync(path.join(root, '..', 'analyst', f), 'utf8'), own = js('architect.js');
  check('the saved analyses: the page knows a skipped reading by the reader\'s own sentence; the dialog of a saved analysis lies over the page, the row\'s Skip is styled in pane.css and View in tabs.css; '
    + 'the version in use is read as the engine keeps it (`at`), and the send carries the step on screen to the server, which hands it to the analysis - as each route of the Pathfinder '
    + 'does (0316): the engine goes to the step, and nothing of 0308\'s use() is left',
    engine('reader.py').includes('\nSKIPPED = "The person skipped it."\n') && own.includes("const SKIPPED = 'The person skipped it.';") && !own.includes('READINGS')
    && css('dialogs.css').includes('#savedAnalysisModal { display: none; position: fixed; inset: 0;') && own.includes("modal.id = 'savedAnalysisModal'; modal.className = 'ui-modal-plain';")
    && paneCss.includes('#streamOutput .sp-row .ar-skip {') && tabsCss.includes('#content-brief .ar-open {')
    && !/^def use\(/m.test(engine('brief.py')) && /^def go\(framing: dict, k\) -> dict:/m.test(engine('steps.py')) && engine('brief.py').includes('at = (framing or {}).get("at")') && own.includes('const n = latestN(framing), at = framing && framing.at;')
    && qp.includes('if (framed && step) requestBody.step = step;') && qp.includes('const { synthesis, image, typed, framed, next, step } = options;')
    && fs.readFileSync(path.join(root, 'app.py'), 'utf8').includes("step = request.json.get('step')")
    && fs.readFileSync(path.join(root, 'app.py'), 'utf8').includes('step=step if isinstance(step, int) and not isinstance(step, bool) else None,')
    && ["framing = instance.architect_say(data['thread_id'], data['chain_id'], text, step=step)", "got = instance.architect_ready(data['thread_id'], data['chain_id'], step=step)",
        "question=str(data['brief'].get('question') or '')[:QUESTION_CHARS], step=_step(data))"].every(t => fs.readFileSync(path.join(root, 'architect_routes.py'), 'utf8').includes(t))
    && ["text: text || null, step: steps.on(entry.framing) }) })", "brief: out.brief, changed: out.changed, step })", "chain_id: entry.chain_id, step: steps.on(entry.framing) }) })"].every(t => own.includes(t)));
  check('the question\'s check, 0313, from the sources: the words are plain ones - what is being done while it is read, what the row says, what the composer says; Start analysis has the question read '
    + 'first and starts only where the brief is still on screen and nothing else runs; the page posts to the route the server has, reads the list of versions read that the engine keeps, and '
    + 'names the call as the host logs it',
    ["checkingRow: 'CHECKING THE QUESTION', checkingHold: 'The question is being read as the Analyst will read it', checkQ: 'CHECK question', standsAlone: 'stands on its own',",
     "unplaced: 'the Analyst cannot place', checkPrompt: 'what the question check was given (run log)'"].every(t => own.includes(t))
    && own.includes("ready(entry).then(clean => { if (clean && responses[currentResponseIndex] === entry && free()) handleQuerySubmit({ framed: entry, step: steps.on(entry.framing) }); });")
    && own.includes("window.authService.fetch('/architect/ready', { method: 'POST'") && own.includes("if (((entry.framing || {}).read || []).indexOf(inUse(entry.framing)) >= 0) return Promise.resolve(true);")
    && own.includes("t.who === 'reader' ? build.checkedQ(t, entry.chain_id)") && own.includes('data-agent="Question check"')
    && fs.readFileSync(path.join(root, 'architect_routes.py'), 'utf8').includes("@architect_bp.route('/architect/ready', methods=['POST'])")
    && fs.readFileSync(path.join(root, '..', 'bambooai', 'bambooai.py'), 'utf8').includes('label="Question check"')
    && engine('cold.py').includes('run.framing = steps.take({**framing, "turns": list(framing.get("turns") or []) + [turn], "read": done + [at]})')
    && engine('cold.py').includes('turn = {"who": "reader", "missing": missing, "v": at,'));
  check('the map of a conversation (0316; a level of the maps drawer, 0327), from the sources: the page has the drawer and the places in it the map writes to, its head the switch; the '
    + 'button that stood beside the arrows is gone - a tab kept with one hides it - and the thread\'s buttons are out of the drawer while it holds the steps; the drawing is told what is the '
    + 'map\'s own in its last argument, and the Workflow map tells it nothing; a step gone to shuts the drawer, and a brief drawn again has the drawer follow; the words are plain ones; the '
    + 'module gives the level, go() and the steps, and nothing of 0308\'s use()',
    ['id="workflowMapModal"', 'id="mapLevels"', 'id="workflowMapContainer"', 'id="nodeTaskContent"', 'id="nodePlotPreview"', 'map-drawer-foot'].every(t => html.includes(t)) && !html.includes('mapDrawerSub')
    && wm.includes("WorkflowGraph.render(document.getElementById('workflowMapContainer'), boxes, window.BranchUI ? window.BranchUI.place().i - 1 : currentResponseIndex);")
    && tabsCss.includes('#content-brief .ar-ver .ar-map { display: none; }') && tabsCss.includes('#content-brief .ar-ver button:disabled, #content-plan .br-ver button:disabled {') && shell.includes('#workflowMapModal:not([data-level="workflow"]) .map-drawer-foot { display: none; }')
    && /#workflowMapModal:not\(\[data-level="workflow"\]\) \.wf-node-chain \{[^}]*white-space: nowrap;[^}]*font-family: var\(--font-ui\);/.test(shell)
    && !own.includes('data-ar="map"') && !own.includes('mapFollows') && !own.includes('openMap') && own.includes("pick: (item, i) => { window.MapsUI.shut(); stepTo(briefRoot(), all[i].k); }")
    && (own.match(/window\.MapsUI\.follow\(\);/g) || []).length === 2 && /window\.ArchitectUI = \{[^}]*\bmark, map, apply\b/.test(own)
    && graph.includes('function render(container, responses, activeIndex, of) {') && graph.includes('if (of) { of.pick(responses[i], i); return; }')
    && graph.includes('if (of) of.show(responses[i], i); else updateDetailPane(i, responses[i], nodeContents, nodePlots, responses, activeIndex);')
    && graph.includes('var picked = responses[activeIndex] ? activeIndex : responses.length - 1;') && graph.includes('        pick(picked);') && graph.includes("chainSpan.textContent = of ? of.sub(resp, idx) : 'Chain: ' + nd.chainId;")
    && ["mapOff: { none: n => 'Chain ' + n + ' was asked without the Pathfinder', old: n => 'Chain ' + n + \"'s brief was made before version 2.8.1\" },", "asked1: 'your question', byHand: 'You changed a line', checked: 'Question check', wentOn: 'The Pathfinder went on',",
        "info: { step: 'Step', follows: 'Follows', next: 'Followed by', replied: 'Pathfinder' }, onScreen: 'on screen', theStart: 'the start', none: 'none',", "goTo: k => 'Go to step ' + k, steps: n => n + ' steps',",
        "question: 'QUESTION', updated: 'updated', stepN: k => 'step ' + k, brief: 'BRIEF', inUse: k => 'step ' + k + ' in use',"].every(t => own.includes(t))
    && /window\.ArchitectUI = \{[^}]*\bgo, steps, build\b/.test(own) && !/\buse\(|WORDS\.version|startWith|set aside'|setAside/.test(own) && !own.includes('mapRest') && !own.includes('WorkflowGraph.rest'));
  check('the stylesheet and the words, 0311: the panels of the figures are styled in tabs.css - one under another, the tag - in the kernel\'s sand where the numbers are made up -, the cross in view, '
    + 'the plot\'s place with its height, the grey window - as tall for every state, hidden under a drawn draft, its line breathing only while a draft is on its way and still for a reader who '
    + 'asked for less motion - and the made-up line in the kernel\'s sand. Nothing is left of the sketch of 0309 - its drawing, its key, the word - nor of the points a model wrote, nor of the '
    + 'picture of a saved analysis: in the engine, on the page or in the stylesheet. The words are plain ones, and a row in flight says what is being done. The page reads what the engine '
    + 'keeps - the keys beside a version, the drafts by key, the draft\'s turn - and what the host sends and serves',
    ['.ar-figs { display: grid; gap: 12px;', '.ar-fig {', '.ar-fig.changed::before {', '.ar-fig .hd .tag {', '.ar-fig .hd .tag.mu {', '.ar-fig .plot { min-height: 280px;', '.ar-fig .drop {',
     '.ar-fig .ar-wait { display: grid; place-items: center; height: 200px;', '.ar-fig.drawn > .ar-wait { display: none; }', '.ar-fig .ar-wait.live span { animation: ar-wait 2.4s ease-in-out infinite; }',
     '.ar-fig .cap {'].every(s => tabsCss.includes('#content-brief ' + s))
    && tabsCss.includes('@keyframes ar-wait { 0%, 100% { opacity: .5; } 50% { opacity: 1; } }')
    && tabsCss.includes('@media (prefers-reduced-motion: reduce) { #content-brief .ar-fig .ar-wait.live span { animation: none; } }')
    && /\.ar-fig \.ar-wait \{[^}]*background: var\(--bg-tertiary\);[^}]*color: var\(--text-tertiary\);/.test(tabsCss) && !/\.ar-wait(?!\.live)[^{]*\{[^}]*animation/.test(tabsCss)
    && !/\.ar-fig[^{]*\.(ln|pt|s\d|key|ph|dot|cell|ax|bk|tk)\b/.test(tabsCss) && !/\.ar-fig[^{]*> svg/.test(tabsCss) && !tabsCss.includes('var(--s)') && !tabsCss.includes('.ar-was') && !/grid-template-columns[^}]*minmax\(250px/.test(tabsCss)
    && !/\.ar-fig \.drop \{[^}]*opacity: 0;/.test(tabsCss) && /\.ar-fig \.hd \.tag\.mu \{[^}]*color: var\(--c-kernel\);/.test(tabsCss) && /\.ar-fig \.cap \{[^}]*color: var\(--c-kernel\);/.test(tabsCss)
    && engine('brief.py').includes('\nSERIES = 4 ') && !/POINTS|_points/.test(engine('brief.py')) && !engine('architect.py').includes('sketched')
    && !/\bplaced\b|\bDRAWN\b|\bFRONT\b|\bDEPTH\b|byData|\.sketched\b|sketched[(:]|\bMARKS\b|\bNAMED\b|\bCLOUD\b|function drawing|WORDS\.sketch|ar-was|drewThen|get_chain_preview|fig\.note/.test(own)
    && own.includes('const TRIES = 2;') && /\nTRIES = 2 /.test(engine('draft.py'))
    && ["figures: 'What it will look like'", "saved: 'MEMORY',", "searching: 'SEARCHING MEMORY', readSoFar: (r, m) => (m == null ? '' : (r || 0) + ' of ' + m + ' read'),",
        "figures: 'FIGURES', draft: 'draft', madeUp: 'made-up numbers', madeUpNote: 'The numbers are made up. The analysis puts in the real ones.',",
        "drawing: 'Drawing a draft…', noDraft: 'No draft could be drawn.', noDraftYet: 'No draft yet.', notDrafted: 'No draft was drawn.', notShown: 'The draft could not be shown.',",
        "drawingRow: 'DRAWING A DRAFT', drawingHold: 'A draft of the figures is being drawn',"].every(s => own.includes(s))
    && engine('draft.py').includes('turn = {"who": "draft", "drawn": [') && own.includes("t.who === 'draft' ? build.drafted(t, entry.chain_id)")
    && engine('draft.py').includes('"keys": [key(brief.get("question", ""), f) for f in brief["figures"]]') && own.includes('keys: v.keys || [], drafts: (framing && framing.drafts) || {}')
    && engine('draft.py').includes('COMPUTED, MADE_UP = "computed", "made up"') && own.includes("madeUp = drawn && d.basis !== 'computed'")
    && fs.readFileSync(path.join(root, '..', 'bambooai', 'bambooai.py'), 'utf8').includes("self._pane('architect_draft', framing=run.framing)") && own.includes("d.type === 'architect_draft' && d.framing")
    && fs.readFileSync(path.join(root, '..', 'bambooai', 'bambooai.py'), 'utf8').includes('label="Draft"') && own.includes('data-agent="Draft"')
    && fs.readFileSync(path.join(root, 'architect_routes.py'), 'utf8').includes("@architect_bp.route('/architect/draft/<thread_id>/<run_id>/<key>', methods=['GET'])")
    && own.includes("plotAt('/architect/draft/' + at.concat(el.getAttribute('data-key')).map(encodeURIComponent).join('/'))")
    && own.includes("else if (act === 'unfigure') keptFirst(root, hit.getAttribute('data-path'), null, unfigure);") && /window\.ArchitectUI = \{[^}]*\bunfigure\b[^}]*\bdraftLayout\b/.test(own));

  // ------------------------------------------------------------ what a chain kept before 2.9 says (0328)
  // the markup of today with the name of then where the page wrote it; the person's words, and the Pathfinder's own, say Architect in both
  const KF = { versions: [FP.versions[0], Object.assign({}, FP.versions[1], { brief: Object.assign({}, FP.versions[1].brief, { thinks: 'The Architect is right' }) })],
               turns: [ASK, { who: 'person', text: 'Ask the Architect' }, { who: 'architect', text: 'An Architect would ask what you expect.', v: 2, call: 3 }], calls: 3 };
  const nowKept = { chain_id: 71, thread_id: 7, tabContent: '<div id="tab-brief" class="tab active">Brief</div>',
    contentOutput: '<div id="content-brief" class="tab-content active">' + b.brief(KF, { chain: 71, thread: 7, state: 'run' }) + '</div>',
    streamOutput: b.fold({ chain_id: 71, queryText: 'Would an Architect ask this?', framing: KF }) +
      '<div class="nq-panel" data-show="list"><div class="nq-sets"><div class="nq-set" data-set="0" data-level="test"><div class="nq-foot"><span>3 questions</span>' +
      '<button class="agent-instructions-btn sp-prompt" type="button" title="the prompt the Pathfinder received (run log)" data-agent="Pathfinder" data-chain="71" data-call="1">⌘</button></div></div></div></div>' };
  const then = text => text.replace(/Pathfinder/g, 'Architect');
  const onScreen = r => { loadResponseContent(r); return { pane: $('streamOutput').innerHTML, tab: $('contentOutput').innerHTML }; };
  const asNow = onScreen(nowKept), wasKept = Object.assign({}, nowKept, { contentOutput: then(nowKept.contentOutput), streamOutput: then(nowKept.streamOutput) }), asThen = onScreen(wasKept);
  const fold = $('streamOutput').querySelector('.ar-fold'), who = fold.querySelectorAll('.ar-msg.arch .who');
  check('a chain kept before 2.9 says Pathfinder when it comes on screen (0328): the fold above its run and that fold\'s cards, their prompt buttons and the next questions\' - which ask '
    + 'for the prompt by that name -, the chips of the lines it proposed; what the person said and what it said itself are left as they were; a chain of today is shown as it is',
    same(asThen, asNow) && !same(wasKept.streamOutput, nowKept.streamOutput) && !same(wasKept.contentOutput, nowKept.contentOutput)
    && fold.querySelector('summary .n').textContent === 'Pathfinder' && fold.querySelector('.peek').textContent === 'Would an Architect ask this?'
    && who.length === 2 && who.every(w => w.textContent.startsWith('Pathfinder')) && fold.querySelectorAll('.sp-prompt').every(p => p.getAttribute('data-agent') === 'Pathfinder' && p.getAttribute('title') === 'the prompt the Pathfinder received (run log)')
    && fold.querySelectorAll('.ar-msg.you').some(m => m.textContent === 'YouAsk the Architect') && fold.querySelectorAll('.ar-msg.arch')[1].textContent.endsWith('An Architect would ask what you expect.')
    && $('streamOutput').querySelector('.nq-foot .sp-prompt').getAttribute('data-agent') === 'Pathfinder' && $('streamOutput').querySelector('.nq-foot').textContent.startsWith('3 questions')
    && $('contentOutput').querySelectorAll('.src.ar').length > 0 && $('contentOutput').querySelectorAll('.src.ar').every(c => c.textContent === 'Pathfinder')
    && /The Architect is right/.test($('contentOutput').textContent),
    [asThen.pane.slice(0, 600), asThen.tab.slice(0, 300)]);
  finish();
})().catch(e => { check('the module ran without throwing', false, e && e.stack); finish(); });

function finish() {
  let fails = 0; for (const [n, ok, d] of results) { console.log((ok ? '  ok   ' : '  FAIL ') + n + (ok ? '' : '  <- ' + (typeof d === 'string' ? d : JSON.stringify(d) || '').slice(0, 900))); if (!ok) fails++; }
  console.log(`\n${results.length - fails} passed, ${fails} failed`); process.exit(fails ? 1 : 0);
}
