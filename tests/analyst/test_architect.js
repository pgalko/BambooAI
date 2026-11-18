// The Architect on the page (docs/ARCHITECT_DESIGN.md §2.6, §2.8, §2.9, §2.11, §2.12; 2026-11-15): architect.js. Its pure
// parts - the brief with one line changed, the Brief tab's markup in each state, the conversation's, the report's part
// "Against the brief" made a card, the thread map's mark - and the module driven on the mini DOM with a scripted server: a
// typed question opens its brief and the Architect takes its first turn, the coach answers with a click or in words, a
// line is changed where it stands and kept as a version, the versions are stepped through, the analysis is started in the
// same chain, the composer is the conversation's while a brief not yet run is on screen; the figures of a brief as
// sketches, and their drafts drawn with a Plotly that keeps what it is asked for (0310). Then the page's hooks, read
// from the source.
// Run: node tests/analyst/test_architect.js
'use strict';
const fs = require('fs'), path = require('path');
const { makeDocument } = require(path.join(__dirname, 'minidom.js'));
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
host.innerHTML = '<button id="architectSwitch" class="ar-switch" aria-pressed="false"></button><textarea id="queryInput"></textarea><button id="submitQuery"></button>' +
  '<div id="streamOutput"></div><div id="tabContainer"></div><div id="contentOutput"></div>';
const $ = id => doc.getElementById(id);
$('queryInput').placeholder = 'Enter your query here';      // the mini DOM keeps properties apart from attributes
// the page's own parts, as far as the module leans on them
global.loadResponseContent = r => { $('tabContainer').innerHTML = r.tabContent || ''; $('contentOutput').innerHTML = r.contentOutput || ''; $('streamOutput').innerHTML = r.streamOutput || '';
  currentData.chain_id = r.chain_id; currentData.thread_id = r.thread_id; window.ArchitectUI.restore(r); };
global.updateNavigationButtons = () => window.ArchitectUI.onChain(responses[currentResponseIndex]);
const submitted = []; global.handleQuerySubmit = o => submitted.push(o);
const tabs = []; global.createOrUpdateTab = (type, html) => tabs.push([type, html]);
const rows = []; global.paneAppend = html => rows.push(html);
const reverted = []; global.revertLiveChain = e => { reverted.push(e); e.status = 'framing'; };

require(path.join(__dirname, '..', '..', 'web_app', 'static', 'js', 'architect.js'));
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
check('a proposal of the Architect\'s is accepted with a tick, and no longer with another: the line named as changed, nothing else touched; only such a line can be ticked - not the coach\'s own, not a line of '
  + 'another part, not one that is not there; the input is never altered',
  same(A.tick(WITH, 'also_check.1'), { brief: Object.assign({}, WITH, { also_check: [BASE.also_check[0], Object.assign({}, ITS, { accepted: true })] }), changed: ['also_check.1'] })
  && A.tick(A.tick(WITH, 'also_check.1').brief, 'also_check.1').brief.also_check[1].accepted === false
  && A.tick(WITH, 'also_check.0') === null && A.tick(WITH, 'also_check.2') === null && A.tick({ rests_on: [{ text: 'x', source: 'architect' }] }, 'rests_on.0') === null
  && A.tick({}, 'also_check.0') === null && A.tick(null, 'also_check.0') === null
  && JSON.stringify(WITH) === withBefore, A.tick(WITH, 'also_check.1'));
check('a proposal the coach rewrites is their own line: no longer the Architect\'s, with nothing to tick and nothing it would show; left out, it goes like any line',
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
check('a brief that holds only the question (0308): on top what the Analyst will be asked - said in those words - with the version beside it under its own name: "Version", "1 of 1", both arrows off and '
  + 'nothing said of who made it; the question in its box with its pencil, and under it one line that says this is what the Analyst gets. No part stands: a part shows only when it holds '
  + 'something. One control adds a part, its list shut; Start analysis at the foot. Nothing says what is always tested - a brief with nothing in it is no brief - and no button has the saved '
  + 'analyses read, whatever the framing says of them',
  root1.elements[0].className === 'ar-top' && root1.querySelector('.ar-top .label').textContent === 'What the Analyst will be asked'
  && root1.querySelector('.ar-top .ar-ver .k').textContent === 'Version' && root1.querySelector('.ar-ver b').textContent === '1 of 1' && !root1.querySelector('.why') && !root1.querySelector('.step')
  && root1.querySelectorAll('.ar-ver [data-ar="step"]').map(x => x.getAttribute('data-step') + x.hasAttribute('disabled') + x.getAttribute('aria-label')).join() === '-1trueThe version before,1trueThe version after'
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
check('the tab carries what it needs to be stepped through later: the chain, the state, the version shown and every version',
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
  && lineOf(root3, 'rests_on.3').querySelector('.mk.no').textContent === '✕' && lineOf(root3, 'rests_on.3').querySelector('.fact.no').textContent === 'A led in 7 of 12' && lineOf(root3, 'rests_on.3').querySelector('.src.ar').textContent === 'Architect'
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
check('what the Architect proposed has a box to tick, its mark as the one who brought it in and, under it, what it would show: empty until the coach accepts it, ticked after; the coach\'s own lines have no box. '
  + 'It can be ticked, changed and left out in whichever version is on screen (0308); once the analysis has started the box only shows',
  accepted.querySelector('button.tick.on[data-ar="tick"]') && accepted.querySelector('.tick').getAttribute('role') === 'checkbox' && accepted.querySelector('.tick').getAttribute('aria-checked') === 'true'
  && accepted.querySelector('.tick').getAttribute('title') === 'Have the analysis test it' && accepted.querySelector('.tick svg') && accepted.querySelector('.src.ar').textContent === 'Architect'
  && accepted.querySelector('.fact').textContent === 'the gap narrows with size held fixed' && accepted.querySelector('.pen[data-ar="edit"]') && accepted.querySelector('.drop[data-ar="drop"]')
  && !mineToo.querySelector('.tick') && !mineToo.querySelector('.src')
  && proposed.querySelector('button.tick[data-ar="tick"]') && !proposed.querySelector('.tick.on') && proposed.querySelector('.tick').getAttribute('aria-checked') === 'false' && !proposed.querySelector('.tick svg')
  && !proposed.querySelector('.tick').hasAttribute('disabled') && proposed.querySelector('.pen') && proposed.className === 'ar-line changed'
  && acceptedRun.querySelector('button.tick.on') && acceptedRun.querySelector('.tick').hasAttribute('disabled') && !acceptedRun.querySelector('[data-ar]'), accepted.outerHTML + proposed.outerHTML);
const old = el(b.brief(F3, { chain: 71, state: 'framing', shown: 2 })).querySelector('.ar-brief');
const ran = el(b.brief(F3, { chain: 71, state: 'run' })).querySelector('.ar-brief'), ranAt = el(b.brief(Object.assign({ at: 2 }, F3), { chain: 71, state: 'run' })).querySelector('.ar-brief');
check('an older version on screen (0308) is the brief as it stood then, and can be gone on from: "2 of 3", both arrows live, the parts it held and no other, each with its pencil, the one control that '
  + 'adds a part - and Start analysis names it, so that the coach sees which version will run. A framing that says which version is in use shows that one, and names it on the button too',
  old.querySelector('.ar-ver b').textContent === '2 of 3' && old.getAttribute('data-shown') === '2' && !old.querySelectorAll('[data-ar="step"]').some(x => x.hasAttribute('disabled'))
  && h3s(old) === 'What it is for' && !lineOf(old, 'thinks') && lineOf(old, 'decision').className === 'ar-line changed' && lineOf(old, 'decision').querySelector('.pen[data-ar="edit"]') && old.querySelector('h1 .pen')
  && old.querySelector('.ar-gets') && old.querySelector('.ar-more [data-ar="more"]') && old.querySelector('.ar-foot [data-ar="start"]').textContent === 'Start analysis with version 2'
  && root3.querySelector('.ar-foot [data-ar="start"]').textContent === 'Start analysis'
  && el(b.brief(Object.assign({ at: 1 }, F3), { chain: 71, state: 'framing' })).querySelector('.ar-ver b').textContent === '1 of 3'
  && el(b.brief(Object.assign({ at: 1 }, F3), { chain: 71, state: 'framing' })).querySelector('[data-ar="start"]').textContent === 'Start analysis with version 1'
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

// ------------------------------------------------------------ the figures of the brief: a sketch, and the draft (0309, 0310; §2.19, §2.20)
const CS = { edit: true, changed: ['figures.0'] }, CR = { edit: false, changed: [] };
const sk = (fig, i, c) => el(b.figure(c || CR, fig, i || 0)).querySelector('.ar-fig');
const KNOWN = { title: 'Two <paths>', kind: 'line', x: 'x', y: 'how far', series: [{ name: 'start <A>' }, { name: 'start B' }], note: 'They <part>.' };
const known = sk(KNOWN, 0, CS), kSvg = known.querySelector('svg[role="img"]');
check('a figure without a draft (0309, 0310): a panel with its number, its title as text, the word "sketch" and - while the brief can be changed - a cross that names its place; under them the series it '
  + 'holds, each beside a dashed stroke; the drawing, named for a reader that cannot see it; what the figure is to make clear, and nothing else under it. A line is a dashed wave: a sketch has no '
  + 'shape. A panel changed in the version shown carries the bar; one that is read has no cross',
  known.className === 'ar-fig changed' && known.elements.map(e => e.className || e.tag).join() === 'hd,key,svg,cap'
  && known.querySelector('.hd').elements.map(e => e.className + '=' + e.textContent).join('|') === 'n=1|t=Two <paths>|tag=sketch|drop='
  && known.querySelector('.drop').getAttribute('data-ar') === 'unfigure' && known.querySelector('.drop').getAttribute('data-path') === 'figures.0' && known.querySelector('.drop').getAttribute('title') === 'Leave it out'
  && known.querySelectorAll('.key span').map(s => s.querySelector('i').className + '=' + s.textContent).join('|') === 'ph=start <A>|ph=start B'
  && kSvg.getAttribute('viewBox') === '0 0 320 190' && kSvg.getAttribute('role') === 'img' && kSvg.getAttribute('aria-label') === 'sketch: Two <paths>'
  && sk({ title: 'A "quoted" title', kind: 'line' }).querySelector('svg[role="img"]').getAttribute('aria-label') === 'sketch: A "quoted" title'
  && kSvg.querySelectorAll('path').map(x => x.className).join() === 'ax,ph,ph' && !known.querySelector('.plot')
  && known.querySelector('.cap').textContent === 'They <part>.' && !known.querySelector('.cap .ph') && !known.querySelector('paths') && !known.querySelector('part')
  && sk(KNOWN, 2).className === 'ar-fig' && !sk(KNOWN, 2).querySelector('.drop') && sk(KNOWN, 2).querySelector('.n').textContent === '3'
  && sk(KNOWN, 1, CS).className === 'ar-fig' && sk(KNOWN, 1, CS).querySelector('.drop').getAttribute('data-path') === 'figures.1', known.outerHTML);
const ON_DATA = { title: 'Yield by season', kind: 'line', x: 'season', y: 'yield', series: [{ name: 'A' }, { name: 'C' }], note: 'Whether the gap holds.' };
const grey = sk(ON_DATA);
const kindOf = (kind, more) => sk(Object.assign({ title: 'T', kind, series: [{ name: 'A' }, { name: 'C' }] }, more));
const centred = (fig, tag) => { const at = fig.querySelectorAll('svg text.tk'), marks = fig.querySelectorAll('svg[role="img"] ' + tag);      // each name stands over the middle of its mark
  return at.length === marks.length && marks.every((m, k) => Math.abs(Number(m.getAttribute('x')) + Number(m.getAttribute('width')) / 2 - Number(at[k].getAttribute('x'))) < 0.11); };
const even = xs => xs.length > 0 && Math.abs(xs[0] + xs[xs.length - 1] - 348) < 0.3;      // the marks stand evenly about the middle of the frame (40 to 308)
const namesAt = fig => fig.querySelectorAll('svg text.tk').map(t => Number(t.getAttribute('x')));
const heights = sk({ title: 'T', kind: 'histogram' }).querySelectorAll('rect').map(r => Number(r.getAttribute('height'))), heat = sk({ title: 'T', kind: 'heatmap', z: 'how <much>' });
const tally = fig => { const out = {}; fig.querySelector('svg[role="img"]').elements.filter(e => e.tag !== 'text').forEach(e => { const k = e.tag + '.' + e.className.split(' ')[0]; out[k] = (out[k] || 0) + 1; }); return out; };
const OLD = [{ title: 'T', kind: 'line', series: [{ name: 'a', points: [[0, 0], [5, 50], [10, 100]] }] }, { title: 'T', kind: 'scatter', series: [{ name: 'a', points: [[1, 10], [3, 30]] }] },
             { title: 'T', kind: 'line3d', series: [{ name: 'a', points: [[0, 0, 0], [1, 2, 3]] }] }];      // figures as a brief of 0309 kept them: with points a model wrote
check('a sketch shows no result and no shape (0309, 0310): nothing in colour - a dashed wave where a line goes, the names beside dashed strokes. Each kind the Architect can name is drawn as itself: '
  + 'points as small rings, bars and box plots as equal shapes with their names at them and no key, a histogram as one mound, a heat map as a grid, a line in three dimensions inside the frame of a '
  + 'box with its third axis named; a figure of no such kind is its axes alone. A kind that names no series is drawn with as many unnamed ones as show it. Points a model wrote for a line draw '
  + 'nothing (0310): a figure that still holds some is the same grey sketch',
  same(tally(grey), { 'path.ax': 1, 'path.ph': 2 }) && !/class="[^"]*\b(ln|pt|s\d)\b/.test(grey.innerHTML)
  && grey.querySelectorAll('.key i').map(i => i.className).join() === 'ph,ph' && grey.querySelector('.cap').textContent === 'Whether the gap holds.' && !grey.querySelector('.cap .ph')
  && !sk({ title: 'T', kind: 'line' }).querySelector('.cap')
  && same(tally(kindOf('scatter')), { 'path.ax': 1, 'circle.dot': 18 })
  && same(tally(kindOf('bar')), { 'path.ax': 1, 'rect.ph': 2 }) && !kindOf('bar').querySelector('.key') && kindOf('bar').querySelectorAll('svg text.tk').map(t => t.textContent).join() === 'A,C'
  && new Set(kindOf('bar').querySelectorAll('rect').map(r => r.getAttribute('height') + '/' + r.getAttribute('y') + '/' + r.getAttribute('width'))).size === 1
  && same(tally(kindOf('box')), { 'path.ax': 1, 'path.ph': 2 }) && !kindOf('box').querySelector('.key') && kindOf('box').querySelectorAll('svg text.tk').map(t => t.textContent).join() === 'A,C'
  && new Set(kindOf('box').querySelectorAll('path.ph').map(x => x.getAttribute('d').replace(/M[\d.]+|H[\d.]+/g, ''))).size === 1
  && same(tally(kindOf('histogram')), { 'path.ax': 1, 'rect.ph': 7 }) && same(tally(kindOf('heatmap')), { 'path.ax': 1, 'rect.cell': 24 })
  && same(tally(kindOf('line3d', { z: 'z' })), { 'path.bk': 1, 'path.ax': 1, 'path.ph': 2 }) && kindOf('line3d', { x: 'x', y: 'y', z: 'z' }).querySelectorAll('svg text').map(t => t.textContent).join() === 'x,y,z'
  && !kindOf('line', { z: 'z' }).querySelector('.bk') && kindOf('line', { x: 'x', y: 'y', z: 'z' }).querySelectorAll('svg text').map(t => t.textContent).join() === 'x,y'
  && same(tally(kindOf(undefined)), { 'path.ax': 1 }) && same(tally(kindOf('violin')), { 'path.ax': 1 }) && kindOf(undefined).querySelectorAll('.key i.ph').length === 2
  && same(tally(sk({ title: 'T', kind: 'bar' })), { 'path.ax': 1, 'rect.ph': 3 }) && same(tally(sk({ title: 'T', kind: 'box' })), { 'path.ax': 1, 'path.ph': 2 })
  && same(tally(sk({ title: 'T', kind: 'scatter' })), { 'path.ax': 1, 'circle.dot': 9 }) && same(tally(sk({ title: 'T', kind: 'line' })), { 'path.ax': 1, 'path.ph': 1 })
  && !sk({ title: 'T', kind: 'line' }).querySelector('.key') && !sk({ title: 'T', kind: 'bar' }).querySelector('svg text')
  && even(namesAt(kindOf('bar'))) && even(namesAt(kindOf('box'))) && even(namesAt(sk({ title: 'T', kind: 'bar', series: ['a', 'b', 'c', 'd'].map(name => ({ name })) }))) && same(namesAt(kindOf('box', { series: [{ name: 'a' }] })), [174])
  && centred(kindOf('bar'), 'rect') && centred(sk({ title: 'T', kind: 'bar', series: ['a', 'b', 'c', 'd'].map(name => ({ name })) }), 'rect') && same(heights, heights.slice().reverse()) && Math.max.apply(null, heights) === 110
  && same(Array.from(new Set(kindOf('heatmap').querySelectorAll('rect').map(r => r.className))).sort(), ['cell c0', 'cell c1', 'cell c2'])
  && same(heat.querySelectorAll('.key span').map(s => s.querySelector('i').className + '=' + s.textContent), ['sq=how <much>']) && !kindOf('heatmap').querySelector('.key i.sq')
  && !sk({ title: 'T', kind: 'line', z: 'depth' }).querySelector('.key') && heat.querySelectorAll('svg[role="img"] text').length === 0
  && same(OLD.map(f => tally(sk(f))), [{ 'path.ax': 1, 'path.ph': 1 }, { 'path.ax': 1, 'circle.dot': 9 }, { 'path.bk': 1, 'path.ax': 1, 'path.ph': 1 }])
  && OLD.every(f => !/class="[^"]*\b(ln|pt|s\d)\b/.test(sk(f).innerHTML) && sk(f).querySelector('.key i').className === 'ph')
  && sk(OLD[0]).querySelector('path.ph').getAttribute('d') === sk({ title: 'T', kind: 'line', series: [{ name: 'a' }] }).querySelector('path.ph').getAttribute('d'), grey.outerHTML);
const DC = (drafts, more) => Object.assign({ edit: true, changed: [], keys: ['k1', 'k<2>'], drafts }, more);
const capOf = fig => (fig.querySelector('.cap') || { textContent: '' }).textContent;
const drawnC = sk(KNOWN, 0, DC({ k1: { basis: 'computed' } })), drawnM = sk(KNOWN, 1, DC({ 'k<2>': { basis: 'made up' } })), failedF = sk(KNOWN, 0, DC({ k1: { failed: 'the cell failed: <ValueError>', tries: 2 } }));
const MADE = 'The numbers are made up. The analysis puts in the real ones.';
check('a figure and its draft (0310): where its draft was drawn the panel says "draft" and holds the place the page draws the plot in, under the figure\'s key - the sketch stays in the markup, for '
  + 'where the plot cannot be had. On made-up numbers the word and a line under the figure say so, and the place is marked for the words drawn across it; a computed one says neither. Where no draft '
  + 'could be drawn the panel is a sketch with a line that says so, the reason under the mouse; while a draft is on its way a line says that - for a figure whose first draft failed too, not for '
  + 'one tried twice, nor for one that has its draft. A figure under another key, or under none, is a sketch that says nothing. The key and the reason are text',
  drawnC.className === 'ar-fig drawn' && drawnC.elements.map(e => e.className || e.tag).join() === 'hd,plot,key,svg,cap'
  && drawnC.querySelector('.tag').className === 'tag' && drawnC.querySelector('.tag').textContent === 'draft' && drawnC.querySelector('.plot').getAttribute('data-key') === 'k1'
  && !drawnC.querySelector('.plot').hasAttribute('data-made-up') && drawnC.querySelector('.plot').innerHTML === '' && capOf(drawnC) === 'They <part>.' && !!drawnC.querySelector('.drop')
  && drawnM.className === 'ar-fig drawn' && drawnM.querySelector('.tag').className === 'tag mu' && drawnM.querySelector('.tag').textContent === 'draft · made-up numbers'
  && drawnM.querySelector('.plot').getAttribute('data-key') === 'k<2>' && drawnM.querySelector('.plot').getAttribute('data-made-up') === '1'
  && capOf(drawnM) === 'They <part>. ' + MADE && drawnM.querySelector('.cap .mu').textContent === MADE
  && capOf(sk({ title: 'T' }, 0, DC({ k1: { basis: 'made up' } }))) === MADE && !sk({ title: 'T' }, 0, DC({ k1: { basis: 'computed' } })).querySelector('.cap')
  && failedF.className === 'ar-fig' && !failedF.querySelector('.plot') && failedF.querySelector('.tag').textContent === 'sketch' && capOf(failedF) === 'They <part>. No draft could be drawn.'
  && failedF.querySelector('.cap .ph').getAttribute('title') === 'the cell failed: <ValueError>'
  && capOf(sk(KNOWN, 0, DC({}, { drawing: true }))) === 'They <part>. Drawing a draft…' && capOf(sk(KNOWN, 0, DC({ k1: { failed: 'x', tries: 1 } }, { drawing: true }))) === 'They <part>. Drawing a draft…'
  && capOf(sk(KNOWN, 0, DC({ k1: { failed: 'x' } }, { drawing: true }))) === 'They <part>. Drawing a draft…' && capOf(sk(KNOWN, 0, DC({ k1: { failed: 'x', tries: 2 } }, { drawing: true }))) === 'They <part>. No draft could be drawn.'
  && capOf(sk(KNOWN, 0, DC({ k1: { basis: 'computed' } }, { drawing: true }))) === 'They <part>.' && capOf(sk(KNOWN, 0, DC({ k1: { failed: 'x', tries: 1 } }))) === 'They <part>. No draft could be drawn.'
  && sk(KNOWN, 0, DC({ 'k<2>': { basis: 'computed' } })).className === 'ar-fig' && capOf(sk(KNOWN, 0, DC({ 'k<2>': { basis: 'computed' } }))) === 'They <part>.'
  && sk(KNOWN, 2, DC({ k1: { basis: 'computed' } })).className === 'ar-fig' && sk(KNOWN, 0, DC({ k1: { basis: 'computed' } }, { changed: ['figures.0'] })).className === 'ar-fig drawn changed'
  && !sk(KNOWN, 0, DC({ k1: { basis: 'computed' } }, { edit: false })).querySelector('.drop') && !/k<2>/.test(drawnM.innerHTML), [drawnC.outerHTML, drawnM.outerHTML, failedF.outerHTML]);
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
const LONG = sk({ title: 'T', kind: 'line', x: 'x'.repeat(50), y: 'a name beside the upright axis that runs on' }), namesL = LONG.querySelectorAll('svg text');
const turned = y => sk({ title: 'T', kind: 'line', y }).querySelector('svg text').hasAttribute('transform');
const fourBars = sk({ title: 'T', kind: 'bar', series: ['a rather long name', 'b', 'c', 'd'].map(name => ({ name })) }).querySelectorAll('svg text.tk');
check('the names in a drawing (0309): an axis\' name stands under it, or beside the upright one, turned along it - a letter or two stay upright; a name too long for its place is cut, and whole under the '
  + 'mouse; a name is text, never markup; an axis without a name has none. The names at bars and boxes are cut by how many stand side by side',
  namesL[0].innerHTML === 'x'.repeat(43) + '…<title>' + 'x'.repeat(50) + '</title>' && namesL[0].getAttribute('x') + ',' + namesL[0].getAttribute('y') + ',' + namesL[0].getAttribute('text-anchor') === '174,179,middle'
  && !namesL[0].hasAttribute('transform') && namesL[1].innerHTML === 'a name beside the upright…<title>a name beside the upright axis that runs on</title>' && namesL[1].getAttribute('transform') === 'rotate(-90 18 86)'
  && !turned('y') && !turned('yld') && turned('rate') && sk({ title: 'T', kind: 'line', y: 'rate' }).querySelector('svg text').innerHTML === 'rate'
  && sk({ title: 'T', kind: 'line', x: '<b>x</b>' }).querySelector('svg text').textContent === '<b>x</b>' && !sk({ title: 'T', kind: 'line', x: '<b>x</b>' }).querySelector('svg b')
  && !sk({ title: 'T', kind: 'line' }).querySelector('svg text') && !sk({ title: 'T', kind: 'line3d', series: [{ name: 'a' }] }).querySelector('svg text')
  && kindOf('line3d', { x: 'x', y: 'y', z: 'depth' }).querySelectorAll('svg text').map(t => t.textContent + ':' + (t.getAttribute('text-anchor') || 'start') + ':' + t.hasAttribute('transform')).join() === 'x:middle:false,y:start:false,depth:middle:true'
  && fourBars.map(t => t.innerHTML).join('|') === 'a rathe…<title>a rather long name</title>|b|c|d'
  && sk({ title: 'T', kind: 'box', series: [{ name: 'a rather long name' }] }).querySelector('svg text.tk').innerHTML === 'a rather long name', LONG.outerHTML);
const FIGS = [KNOWN, ON_DATA, { title: 'Spread', kind: 'box', series: [{ name: 'A' }, { name: 'C' }] }];
const FF = { versions: F3.versions.concat([{ n: 4, by: 'architect', why: 'answer', changed: ['figures.0', 'figures.2'], brief: Object.assign({}, FULL, { figures: FIGS }), keys: ['kA', 'kB', 'kC'] },
                                           { n: 5, by: 'person', changed: ['figures'], brief: Object.assign({}, FULL, { figures: FIGS.slice(0, 2) }), keys: ['kA', 'kB'] }]),
             drafts: { kA: { basis: 'computed' }, kB: { basis: 'made up' }, kC: { failed: 'the cell failed', tries: 1 } } };
const tabF = el(b.brief(FF, { chain: 71, thread: 7, state: 'framing', shown: 4 })).querySelector('.ar-brief'), figsF = tabF.querySelector('.ar-figs');
const classesF = o => el(b.brief(FF, Object.assign({ chain: 71, thread: 7, state: 'framing', shown: 4 }, o))).querySelectorAll('.ar-fig').map(f => f.className + '/' + capOf(f).replace('They <part>. ', '').replace('Whether the gap holds. ', '')).join('|');
const only = (figs, more) => el(b.brief(Object.assign({ versions: [{ n: 1, by: 'architect', changed: [], brief: { question: 'q', figures: figs } }] }, more), { chain: 71, state: 'framing' }));
check('the figures on the Brief tab (0309, 0310): under a plain heading of their own, after what is fixed before a run and before what the brief builds on - a panel to a figure, in the brief\'s order, '
  + 'each under its number, the ones this version changed marked; the version on screen shows its own figures. A figure is found drawn by its key among the version\'s keys and the drafts the framing '
  + 'keeps: drawn, a sketch that says no draft could be drawn, or - while one is on its way - a sketch that says so; the tab carries the thread its plots are kept under, and that a draft is on '
  + 'its way. While the brief can be changed each has its cross; the brief of a run that has started shows them to be read, drafts and all. A framing without keys - a brief of 0309 - shows '
  + 'sketches. A brief without figures has no such part, and none can be added by hand: the coach asks the Architect. A brief that holds only figures is a brief: on data, what is always tested is said',
  h3s(tabF) === 'What it is for|What you think|Why you think so|What you expect to see|What would change your mind|Other explanations to test|Measured by|What it will look like|Builds on|Set aside'
  && figsF.elements.map(e => e.className + ':' + e.querySelector('.n').textContent + ':' + e.querySelector('.t').textContent).join('|') === 'ar-fig drawn changed:1:Two <paths>|ar-fig drawn:2:Yield by season|ar-fig changed:3:Spread'
  && classesF({}) === 'ar-fig drawn changed/They <part>.|ar-fig drawn/' + MADE + '|ar-fig changed/No draft could be drawn.'
  && classesF({ drawing: true }) === 'ar-fig drawn changed/They <part>.|ar-fig drawn/' + MADE + '|ar-fig changed/Drawing a draft…'
  && classesF({ shown: 5 }) === 'ar-fig drawn/They <part>.|ar-fig drawn/' + MADE && classesF({ state: 'run' }) === classesF({}) && figsF.querySelectorAll('.plot').map(x => x.getAttribute('data-key')).join() === 'kA,kB'
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
check('the conversation: the question first, then each message under who said it - the coach\'s as typed, the Architect\'s with its green edge; the last message\'s choices are pills to click, shown as text',
  same(msgs(live), ['ar-msg you|YouIs B above A?', 'ar-msg arch|Architect⌘What will you do differently depending on the answer?Keep one armKeep <both>'])
  && same(live.querySelectorAll('.ar-choices .ar-choice[data-ar="choice"]').map(c => c.textContent), ['Keep one arm', 'Keep <both>']) && !live.querySelector('.ar-choice both'), live.innerHTML);
const later = el(b.talk(TALK, { live: true }));
const marked = el(b.said({ who: 'architect', text: 'Is <b>B</b> & "A" above?', call: 2 }, 71, false));
check('what the Architect wrote is shown as text, never as markup', marked.querySelector('.ar-msg').textContent === 'Architect⌘Is <b>B</b> & "A" above?' && !marked.querySelector('.ar-msg b'), marked.innerHTML);
check('choices are offered once: on the Architect\'s last message while it is the last, never on an earlier one, in a conversation only read, or while a reply is awaited',
  later.querySelectorAll('.ar-choice').length === 0 && same(msgs(later).map(m => m.split('|')[0]), ['ar-msg you', 'ar-msg arch', 'ar-msg you', 'ar-msg arch'])
  && el(b.talk({ chain_id: 71, queryText: 'q', framing: { turns: [ASK] } })).querySelectorAll('.ar-choice').length === 0
  && el(b.talk({ chain_id: 71, queryText: 'q', framing: { turns: [ASK] } }, { live: true, waiting: true })).querySelectorAll('.ar-choice').length === 0);
const button = later.querySelectorAll('.ar-msg.arch .sp-prompt');
check('each message of the Architect\'s has the button to the prompt it received: the Architect\'s own calls in this chain\'s log, by their number - a reply asked for twice counts both',
  button.length === 2 && button.every(x => x.className === 'agent-instructions-btn sp-prompt' && x.getAttribute('data-agent') === 'Architect' && x.getAttribute('data-chain') === '71')
  && same(button.map(x => x.getAttribute('data-call')), ['1', '3']) && !el(b.said({ who: 'architect', text: 'x' }, 71, true)).querySelector('.sp-prompt'), later.innerHTML);
const mid = el(b.talk(TALK, { live: true, sent: 'B above A by <2>', waiting: true }));
check('a message on its way is shown at once, as text, and under it the Architect is reading',
  same(msgs(mid).slice(-2), ['ar-msg you|YouB above A by <2>', 'ar-msg arch wait|Architectreading…']), mid.innerHTML);
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
check('a reading of the saved analyses is one row of the conversation: SAVED analyses, how many analyses were found - not how many passages (0308) - and how many of the saved runs were read, the '
  + 'seconds; the passages and the count to each way across them are the row\'s title, as text',
  memRow(MEMORY).className === 'sp-row tool read' && memRow(MEMORY).textContent === '✓SAVED analyses2 analyses found · read 9 of 1241 s'
  && memRow(MEMORY).getAttribute('title') === '2026-03-02 · Was B above A in <spring>?: "B led A by 3 units"\n2026-04-02 · Synthesis: Two arms: "gap = b - a"\n2026-03-02 · Was B above A in <spring>?: "gap: 3 units"\nHow the gap was taken: 2 × B minus A; 1 × the ratio'
  && memRow(Object.assign({}, MEMORY, { found: MEMORY.found.slice(0, 1), across: null, read: 0 })).textContent === '✓SAVED analyses1 analysis found · 12 saved41 s'
  && memRow({ who: 'memory', found: [], of: 12, read: 12, secs: 0.2 }).textContent === '✓SAVED analysesnothing found · read 12 of 121 s', b.recalled(MEMORY));
const foundList = el(b.recalled(MEMORY)).querySelector('.ar-found');
check('under the row, what the reading found (0308): an analysis to a line, in the order found - its day as a person writes it and what was asked then, as text - with View, which names the analysis '
  + 'by its thread and run; the passages are not listed here: the Brief tab has them. Nothing can be ticked. A reading that found nothing, or was not made, has no list',
  el(b.recalled(MEMORY)).elements.map(e => e.className).join('|') === 'sp-row tool read|ar-found'
  && foundList.querySelectorAll('.it .q').map(x => x.textContent).join('|') === '2 Mar 2026 · Was B above A in <spring>?|2 Apr 2026 · Synthesis: Two arms' && /in &lt;spring&gt;\?/.test(foundList.innerHTML)
  && foundList.querySelectorAll('.ar-open[data-ar="open"]').map(x => x.getAttribute('data-thread') + '/' + x.getAttribute('data-run') + '=' + x.textContent).join() === '7/8=View,7/9=View'
  && !foundList.querySelector('.qt') && !foundList.querySelector('.why') && !foundList.querySelector('.tag') && foundList.querySelectorAll('[data-ar]').length === 2 && !/B led A by 3 units/.test(foundList.textContent)
  && !el(b.recalled({ who: 'memory', found: [], of: 12, read: 12, secs: 0.2 })).querySelector('.ar-found')
  && !el(b.recalled({ who: 'memory', found: MEMORY.found, failed: 'The person skipped it.', secs: 3 })).querySelector('.ar-found'), b.recalled(MEMORY));
check('a reading that was not made is marked as one that did not run: its row says that the coach skipped it, or why it could not be made; a reading in flight shows how far it is - looking, looking through the saved runs, reading so many of them - with Skip, '
  + 'which can be pressed once the server has said how many are saved',
  memRow({ who: 'memory', found: [], failed: 'The person skipped it.', secs: 3 }).className === 'sp-row tool read skipped'
  && memRow({ who: 'memory', found: [], failed: 'The person skipped it.', secs: 3 }).textContent === '–SAVED analysesskipped3 s'
  && memRow({ who: 'memory', found: [], failed: 'The saved analyses could not be read: the executor is <away>', secs: 0.4 }).textContent === '–SAVED analysesnot read · The saved analyses could not be read: the executor is <away>1 s'
  && el(b.reading({ read: 0, of: null })).querySelector('.sp-row.tool.read.pending').textContent === 'SAVED analyseslookingSkip'
  && el(b.reading({ read: 0, of: null })).querySelector('.ar-skip').hasAttribute('disabled') && !el(b.reading({ read: 0, of: 12 })).querySelector('.ar-skip').hasAttribute('disabled')
  && el(b.reading({ read: 0, of: 12 })).querySelector('.out').textContent === 'looking through 12' && el(b.reading({ read: 5, of: 12 })).querySelector('.out').textContent === 'reading 5 of 12'
  && el(b.reading({ read: 1, of: 12 })).querySelector('.out').textContent === 'reading 1 of 12'
  && el(b.reading({ read: 5, of: 12 })).querySelector('button.ar-skip[data-ar="skip"]').textContent === 'Skip' && el(b.reading({ read: 5, of: 12 })).querySelector('.live'), b.reading({ read: 5, of: 12 }));
const BS = { question: 'q', saved: BUILT.slice(0, 2).concat([Object.assign({}, BUILT[2], { accepted: true })]) };
check('unbuild() (0308): the brief builds no longer on one saved analysis, named by its id - every passage of it goes, the others stay, and with the last one the part; an analysis the brief does not '
  + 'build on gives null; the brief passed in is not altered. A passage is no line of its own any more: tick() does not accept one, and apply() does not leave one out',
  same(A.unbuild(BS, '7/8'), { brief: { question: 'q', saved: [BS.saved[2]] }, changed: ['saved'] }) && A.unbuild(BS, '7/9').brief.saved.length === 2
  && !('saved' in A.unbuild({ question: 'q', saved: [BS.saved[2]] }, '7/9').brief) && A.unbuild(BS, '5/5') === null && A.unbuild({ question: 'q' }, '7/8') === null && A.unbuild(null, '7/8') === null
  && BS.saved.length === 3 && A.tick(BS, 'saved.0') === null && A.apply(BS, 'saved.0', '') === null && A.apply(BS, 'saved.0', 'other words') === null);
check('use() (0308): the framing with a version in use, as the server will have it once the request that carries the number is taken - an earlier version is named, the last names none, and a number '
  + 'the framing does not have names none either; the framing passed in is not altered',
  A.use(F3, 2).at === 2 && A.use(F3, 1).versions === F3.versions && !('at' in A.use(Object.assign({ at: 1 }, F3), 3)) && !('at' in F3)
  && [0, 3, 4, -1, '2', true, null, 1.5].every(k => !('at' in A.use(Object.assign({ at: 2 }, F3), k))) && same(A.use(null, 1), {}) && A.use(Object.assign({ at: 2 }, F3), 1).at === 1);
const namedAt = at => el(b.fold({ chain_id: 71, queryText: 'q', framing: Object.assign(at === undefined ? {} : { at }, F3) })).querySelector('.kind').textContent;
check('the version in use, as the fold above a run names it (0308): the one the framing names where it has that version, else the last',
  namedAt(undefined) === 'brief v3' && namedAt(2) === 'brief v2' && namedAt(1) === 'brief v1' && [0, 4, 9, -1, '2', 1.5, null].every(at => namedAt(at) === 'brief v3'), [namedAt(2), namedAt(9)]);
const dlg = el(b.savedDialog({ id: '7/8', when: '2026-03-02T10:00:00Z', question: 'Was B above A in <spring>?', title: 'B led', report: '# B led\n\nB led A by <3> units.', marks: ['picked', 'routine'],
                              data: { name: 'spring.csv', period: '2026-03-01 to 2026-05-31', person: 'First <Person>' }, cells: [{ n: 1, code: 'gap = b - a  # <b>' }] }));
const dlgB = el(b.savedDialog({ question: 'q', report: 'r', brief: 'Decision: keep <one>\nFixed before the run:\n- measure: height', cells: [{ n: 2, code: 'x = 1' }] }));
check('a saved analysis that was framed: the brief it ran under is folded under the report, before the code, as text and a line each; one that was not framed has no such fold',
  same([...dlgB.querySelectorAll('details.ar-code summary')].map(x => x.textContent), ['Brief', 'Code']) && dlgB.querySelector('details.ar-code pre.said').textContent === 'Decision: keep <one>\nFixed before the run:\n- measure: height'
  && !dlgB.querySelector('details.ar-code').hasAttribute('open') && dlgB.querySelectorAll('pre.said').length === 1
  && same([...el(b.savedDialog({ question: 'q', report: 'r', brief: '', cells: [{ n: 2, code: 'x = 1' }] })).querySelectorAll('details.ar-code summary')].map(x => x.textContent), ['Code'])
  && same([...el(b.savedDialog({ question: 'q', report: 'r', brief: 'Decision: d' })).querySelectorAll('details.ar-code summary')].map(x => x.textContent), ['Brief']), dlgB.innerHTML);
const dlgC = el(b.savedDialog({ question: 'q', report: 'r', conversation: 'Person: Plot <it>\nArchitect: A Person: or two things?\n\n- the shape\nPerson: The shape', brief: 'Decision: d - Person: no', cells: [{ n: 2, code: 'x = 1' }] }));
check('a saved analysis that was framed in a conversation: what was said is folded under the report, before the brief, as text with its lines, the person\'s messages under "You"; one without a conversation has no such fold',
  same([...dlgC.querySelectorAll('details.ar-code summary')].map(x => x.textContent), ['Conversation', 'Brief', 'Code'])
  && dlgC.querySelector('details.ar-code pre.said').textContent === 'You: Plot <it>\nArchitect: A Person: or two things?\n\n- the shape\nYou: The shape' && dlgC.querySelectorAll('pre.said').length === 2
  && dlgC.querySelectorAll('pre.said')[1].textContent === 'Decision: d - Person: no'
  && !dlgC.querySelector('details.ar-code').hasAttribute('open')
  && same([...el(b.savedDialog({ question: 'q', report: 'r', conversation: '', brief: 'Decision: d' })).querySelectorAll('details.ar-code summary')].map(x => x.textContent), ['Brief']), dlgC.innerHTML);
check('a saved analysis opened beside the brief: a dialog with what was asked, the day, whose data it ran on and which, and how it was saved; the report, and under it the code of its cells, folded, as text',
  dlg.querySelector('.ui-dlg.lg[role="dialog"] .ui-dlg-h .title').textContent === 'Was B above A in <spring>?' && dlg.querySelector('.ui-dlg-h .sub').textContent === '2026-03-02 · First <Person> · spring.csv · 2026-03-01 to 2026-05-31 · picked, routine'
  && dlg.querySelector('.ui-dlg-h button.x[data-ar="shut"]') && dlg.querySelector('.ui-dlg-b pre').textContent.indexOf('B led A by <3> units.') >= 0
  && dlg.querySelector('details.ar-code summary').textContent === 'Code' && dlg.querySelector('details.ar-code pre').textContent === 'gap = b - a  # <b>' && !dlg.querySelector('details.ar-code').hasAttribute('open')
  && el(b.savedDialog({ question: '', title: 'A synthesis', report: 'r', cells: [] })).querySelector('.title').textContent === 'A synthesis' && !el(b.savedDialog({ report: 'r' })).querySelector('details'), dlg.innerHTML);
const KEEP = { who: 'architect', text: 'One line does not hold. Keep it, or change it?', choices: ['Keep it', 'Change it'], v: 2, cost: 0.01, call: 5 };
const ROUND = { chain_id: 71, queryText: 'Is B above A?', framing: { versions: F1.versions, turns: [{ who: 'person', text: 'B well above A' }, { who: 'architect', text: 'Checking this against the data.', v: 1, call: 4 }, CHECK, KEEP] } };
const round = b.talk(ROUND, { live: true }), between = el(b.talk({ chain_id: 71, queryText: 'q', framing: { turns: ROUND.framing.turns.slice(0, 3) } }, { live: true }));
check('the row stands in the conversation where the round was made: after the message that asked for it, before the one that marks the lines - whose choices are the ones to click; with the round the last thing said, there is nothing to click',
  round.indexOf('Checking this against the data.') < round.indexOf('class="sp-row tool read"') && round.indexOf('class="sp-row tool read"') < round.indexOf('One line does not hold.')
  && same(el(round).querySelectorAll('.ar-choice').map(c => c.textContent), ['Keep it', 'Change it']) && el(round).querySelectorAll('.sp-row').length === 1 && el(round).querySelectorAll('.ar-msg').length === 4
  && between.querySelectorAll('.ar-choice').length === 0 && between.querySelectorAll('.sp-row').length === 1
  && el(b.fold(ROUND)).querySelectorAll('.sp-detail .sp-row').length === 1 && el(b.fold(ROUND)).querySelectorAll('.sp-detail .ar-choice').length === 0, round);
const paneOf = (e, o) => el(b.pane(e, o));
check('the left pane of a brief not yet run: the strip says Architect and what its calls have cost - nothing while that is under a cent - and names no version: the Brief tab does (0308); the '
  + 'conversation under it',
  paneOf(TALK).querySelector('.sp-strip').textContent === 'Architect$0.02' && paneOf({ chain_id: 1, queryText: 'q', framing: { versions: F3.versions, turns: [ASK] } }).querySelector('.sp-strip').textContent === 'Architect'
  && paneOf(TALK).querySelectorAll('.sp-stream .ar-msg').length === 4 && paneOf(TALK, { waiting: true }).querySelectorAll('.sp-stream .ar-msg').length === 5
  && paneOf({ chain_id: 1, queryText: 'q', framing: F1 }).querySelector('.sp-stream').textContent === 'YouIs B above A?'
  && paneOf({ chain_id: 1, queryText: 'q', framing: {} }).querySelector('.sp-stream').textContent === 'Youq', paneOf(TALK).innerHTML);
const folded = el(b.fold(TALK));
check('once the analysis starts the framing is one folded row above it - Architect, the version, the question - with the conversation inside, to be read: no choices, the prompt buttons kept',
  folded.querySelector('details.sp-turn.ar-fold summary').textContent === 'Architectbrief v1Is B above A?' && folded.querySelectorAll('.sp-detail .ar-msg').length === 4
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
check('the left pane of a brief not yet run: the strip says Architect, idle; the coach\'s card holds the question as it was first asked, as text - the brief holds it as it stands now',
  pane.querySelector('.sp-strip .live.idle') && pane.querySelector('.sp-strip .mode').textContent === 'Architect' && pane.querySelector('.sp-strip').textContent === 'Architect'
  && pane.querySelector('.sp-stream .ar-msg.you .who').textContent === 'You' && pane.querySelector('.sp-stream .ar-msg.you').textContent === 'YouIs B above A?'
  && el(b.pane({ chain_id: 71, queryText: 'A later wording', framing: { versions: [{ n: 1, by: 'person', changed: [], brief: { question: 'Is B <above> A?' } }, { n: 2, by: 'architect', changed: ['question'], brief: { question: 'A later wording' } }] } }))
       .querySelector('.sp-stream .ar-msg.you').textContent === 'YouIs B <above> A?', pane.innerHTML);
check('once the analysis starts the framing is one folded row above the run: Architect, the version, the question; the coach\'s card inside',
  fold.querySelector('details.sp-turn.ar-fold') && !fold.querySelector('details').hasAttribute('open') && fold.querySelector('summary .n').textContent === 'Architect' && fold.querySelector('summary .kind').textContent === 'brief v3'
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
  + 'updated, and in which version. No row where a reply\'s wording was not written: a message of 0307 whose wording waited, a version the coach made, a version that changed another part, a question '
  + 'that reads otherwise, a reply with none. Nothing in the conversation is taken with a button',
  talkW.elements.map(e => e.className.split(' ').slice(0, 2).join('.')).join() === 'ar-msg.you,ar-msg.you,ar-msg.arch,sp-row.tool'
  && talkW.querySelector('.ar-msg.arch').elements.map(e => e.className).join() === 'who,ar-choices' && !talkW.querySelector('.ar-wording') && !talkW.querySelector('[data-ar="use"]')
  && !/against z/.test(talkW.querySelector('.ar-msg.arch').textContent)
  && rowW.className === 'sp-row tool read' && rowW.elements.map(e => e.className + '=' + e.textContent).join('|') === '=✓|in=QUESTION|out=updated|t=version 2'
  && rowsIn(FW.versions.slice(0, 1), [Object.assign({}, turnW, { v: 1 })]) === 0
  && rowsIn([FW.versions[0], Object.assign({}, FW.versions[1], { by: 'person' })], [turnW]) === 0 && rowsIn([FW.versions[0], Object.assign({}, FW.versions[1], { changed: ['decision'] })], [turnW]) === 0
  && rowsIn([FW.versions[0], Object.assign({}, FW.versions[1], { brief: { question: 'My own words' } })], [turnW]) === 0 && rowsIn(FW.versions, [{ who: 'architect', text: 'No wording.', v: 2 }]) === 0
  && rowsIn(FW.versions, [turnW]) === 1 && el(b.asked({ v: '<3>' })).querySelector('.t').textContent === 'version <3>' && typeof A.pending === 'undefined' && typeof b.wording === 'undefined', talkW.innerHTML);
const DRAFT_OK = { who: 'draft', drawn: [{ title: 'A', basis: 'computed' }, { title: 'B', basis: 'made up' }], v: 2, secs: 6.4, cost: 0.002, call: 3 };
const DRAFT_PART = { who: 'draft', drawn: [{ title: 'A', basis: 'made up' }], missing: ['B'], failed: 'the cell failed: <ValueError>', v: 3, secs: 0.2, cost: 0.004, call: 5 };
const DRAFT_NONE = { who: 'draft', drawn: [], missing: ['A', 'B'], failed: 'it could not be drawn: the sandbox is away', v: 3, secs: 21, cost: 0 };
const turnsD = [{ who: 'person', text: 'Show me' }, Object.assign({}, turnW, { choices: ['Yes', 'Change it'] }), DRAFT_OK];
const talkD = el(b.talk(entryW({ versions: FW.versions, turns: turnsD }), { live: true })), rowsD = [DRAFT_OK, DRAFT_PART, DRAFT_NONE].map(t => el(b.drafted(t, 71)).querySelector('.sp-row'));
const waits = o => el(b.talk(entryW({ versions: FW.versions, turns: turnsD.slice(0, 2) }), Object.assign({ live: true, waiting: true }, o))).elements.slice(-1)[0];
check('the draft of the figures in the conversation (0310): a row under the reply that had it drawn - how many figures were drawn, the seconds, and the button to the prompt its cell was written from, '
  + 'which names the draft\'s call; where some were not drawn the row says how many and is greyed, the reason under the mouse; where none was, it says so. The reply\'s choices can still be '
  + 'clicked with the draft\'s row under it - not once the coach has spoken again. While the draft is on its way a row says so in the place of the Architect\'s "reading"; a reading of the '
  + 'saved analyses is said first. Nothing in a row is markup; a reply of 0309 that says how many it sketched has no row',
  talkD.elements.map(e => e.className.split(' ').slice(0, 2).join('.')).join() === 'ar-msg.you,ar-msg.you,ar-msg.arch,sp-row.tool,sp-row.tool' && talkD.querySelectorAll('.ar-choice').length === 2
  && talkD.querySelectorAll('.sp-row').map(r => r.textContent).join('|') === '✓QUESTIONupdatedversion 2|✓FIGURES2 drawn6 s⌘'
  && rowsD[0].className === 'sp-row tool read' && !rowsD[0].hasAttribute('title') && rowsD[0].elements.map(e => e.className + '=' + e.textContent).join('|') === '=✓|in=FIGURES|out=2 drawn|t=6 s|agent-instructions-btn sp-prompt=⌘'
  && ['data-agent', 'data-chain', 'data-call', 'title'].map(a => rowsD[0].querySelector('.sp-prompt').getAttribute(a)).join('|') === 'Draft|71|3|the prompt the draft was written from (run log)'
  && rowsD[1].className === 'sp-row tool read skipped' && rowsD[1].getAttribute('title') === 'the cell failed: <ValueError>' && rowsD[1].textContent === '–FIGURES1 drawn · 1 not1 s⌘'
  && rowsD[2].className === 'sp-row tool read skipped' && rowsD[2].textContent === '–FIGURESno draft21 s' && !rowsD[2].querySelector('.sp-prompt') && rowsD[2].getAttribute('title') === 'it could not be drawn: the sandbox is away'
  && el(b.talk(entryW({ versions: FW.versions, turns: turnsD.concat([{ who: 'person', text: 'Yes' }]) }), { live: true })).querySelectorAll('.ar-choice').length === 0
  && el(b.talk(entryW({ versions: FW.versions, turns: turnsD.concat([DRAFT_PART]) }), { live: true })).querySelectorAll('.ar-choice').length === 2
  && el(b.talk(entryW({ versions: FW.versions, turns: turnsD }))).querySelectorAll('.ar-choice').length === 0
  && el(b.drawingRow()).querySelector('.sp-row').className === 'sp-row tool read pending' && el(b.drawingRow()).querySelector('.sp-row').elements.map(e => e.className + '=' + e.textContent).join('|') === 'live=|in=FIGURES|out=drawing a draft…'
  && waits({ drawing: true }).className === 'sp-row tool read pending' && waits({ drawing: true }).textContent === 'FIGURESdrawing a draft…' && waits({}).className === 'ar-msg arch wait'
  && /^SAVED analyses/.test(waits({ drawing: true, saved: { read: 1, of: 3 } }).textContent) && waits({ drawing: true }).parent.querySelectorAll('.ar-choice').length === 0
  && typeof b.sketched === 'undefined' && typeof b.sketch === 'undefined'
  && el(b.talk(entryW({ versions: FW.versions, turns: [{ who: 'architect', text: 'As it was.', sketched: 2, v: 2 }] }))).querySelectorAll('.sp-row').length === 0, [talkD.innerHTML, rowsD.map(r => r.outerHTML)]);
const wentRow = el(b.went({ who: 'version', v: 2 })).querySelector('.sp-row');
const talkV = el(b.talk(entryW({ versions: FW.versions, turns: FW.turns.concat([{ who: 'version', v: 1 }, { who: 'person', text: 'From the first one' }, { who: 'architect', text: 'As you say.', v: 1 }]) })));
check('where the coach went to another version before a message (0308), a row says which version is in use from there - before the message it came with; the fold above a run names the version in '
  + 'use, which is not always the last',
  wentRow.className === 'sp-row tool read' && wentRow.elements.map(e => e.className + '=' + e.textContent).join('|') === '=✓|in=BRIEF|out=version 2 in use'
  && talkV.elements.map(e => e.className.split(' ').slice(0, 2).join('.')).join() === 'ar-msg.you,ar-msg.you,ar-msg.arch,sp-row.tool,sp-row.tool,ar-msg.you,ar-msg.arch'
  && talkV.querySelectorAll('.sp-row')[1].textContent === '✓BRIEFversion 1 in use'
  && el(b.fold(entryW(Object.assign({ at: 1 }, FW)))).querySelector('summary .kind').textContent === 'brief v1' && el(b.fold(entryW(FW))).querySelector('summary .kind').textContent === 'brief v2', talkV.innerHTML);
const rowO = el(b.opened({ who: 'opened', what: 'cell', n: 5, label: 'cell <5>', chars: 12345 })).querySelector('.sp-row');
const rowN = el(b.opened({ who: 'opened', missing: 'there is no cell 99: the cells are 1 to 5' })).querySelector('.sp-row');
const talkO = el(b.talk(entryW({ versions: FW.versions, turns: [{ who: 'person', text: 'How was it drawn?' }, { who: 'architect', text: 'I am opening the cell.', v: 1 },
                                                               { who: 'opened', what: 'cell', n: 5, label: 'cell 5', chars: 66 }, { who: 'architect', text: 'It draws one line a month.', v: 1 }] })));
check('a part of an earlier analysis the Architect opened is a row of the conversation, as the pane shows a tool\'s: READ, what was read - as text - and how long it is; a part that is not there says so in '
  + 'the place of both, marked as a step that did not run. The row stands where the part was opened: after the message that asked, before the one that speaks of it',
  rowO.className === 'sp-row tool read' && rowO.elements.map(e => e.className + '=' + e.textContent).join('|') === '=✓|in=READ|out=cell <5>|t=12,345 characters' && !rowO.querySelector('.out b')
  && rowN.className === 'sp-row tool read skipped' && rowN.elements.map(e => e.className + '=' + e.textContent).join('|') === '=–|in=READ|out=there is no cell 99: the cells are 1 to 5'
  && talkO.elements.map(e => e.className.split(' ').slice(0, 2).join('.')).join() === 'ar-msg.you,ar-msg.you,ar-msg.arch,sp-row.tool,ar-msg.arch', talkO.innerHTML);
check('the field a line is typed in says nothing of its own (0308): the part\'s heading stands over it', !el(b.editor('', false)).querySelector('.ar-input').hasAttribute('placeholder') && b.editor.length === 2);

// ------------------------------------------------------------ the report's part "Against the brief", as a card
const LIST = '<h1 id="t">B is above A</h1>\n<p>For the decision: keep B.</p>\n<h2 id="against-the-brief">Against the brief</h2>\n<ul>\n<li>Expected: not met - the gap is 0.4 <span class="cite cell" onclick="x()">cell 2</span></li>\n' +
  '<li>Would change their mind: seen</li>\n<li>chance: the interval includes 0</li>\n<li>measurement error: cannot tell, nothing says how x was measured</li>\n<li>the two halves differ: the same in both</li>\n</ul>\n' +
  '<h2 id="did-not-fit">Did not fit</h2>\n<ul>\n<li>Nothing.</li>\n</ul>\n';
const card = el(A.dressAnswer(LIST));
const rowsOf = c => c.querySelectorAll('.ar-against .r').map(r => [r.querySelector('.k').textContent, r.querySelector('.t').textContent, r.querySelector('.v').className, r.querySelector('.v').textContent]);
check('the part becomes a card in its place: the opening before it and Did not fit after it untouched; a row for what was expected and one for what would change the coach\'s mind, each with its verdict; the checks after, the first labelled',
  card.elements.map(e => e.tag + (e.className ? '.' + e.className : '')).join() === 'h1,p,div.ar-against,h2,ul' && card.querySelector('.ar-against .label').textContent === 'Against the brief'
  && same(rowsOf(card), [['You expected', 'the gap is 0.4 cell 2', 'v no', 'not met'], ['Would change your mind', '', 'v no', 'seen'], ['Also checked', 'chance: the interval includes 0', 'v', ''],
                         ['', 'measurement error: cannot tell, nothing says how x was measured', 'v q', 'cannot tell'], ['', 'the two halves differ: the same in both', 'v', '']])
  && card.querySelector('.ar-against .cite.cell').getAttribute('onclick') === 'x()' && card.querySelector('h2').textContent === 'Did not fit', card.innerHTML);
check('the card is one line of markup with no heading in it: rendered again (a restored chain), it stays as it is', !/\n/.test(b.against(['Expected: met', 'chance: fine'])) && !/<h\d/.test(b.against(['Expected: met']))
  && A.dressAnswer(A.dressAnswer(LIST)) === A.dressAnswer(LIST));
const verdicts = html => rowsOf(el(A.dressAnswer('<h2>Against the brief</h2>' + html))).map(r => r[0] + '=' + r[3] + '|' + r[1]);
check('the verdict is read as the engine reads it: "not met" before "met", "not seen" before "seen", cannot tell; at the line\'s start or later in it; none when the line gives none',
  same(verdicts('<ul><li>Expected: met (gap 3)</li><li>Would change their mind: not seen</li></ul>'), ['You expected=met|(gap 3)', 'Would change your mind=not seen|'])
  && same(verdicts('<ul><li>Expected: cannot tell: too few</li><li>What would change their mind - cannot tell</li></ul>'), ['You expected=cannot tell|too few', 'Would change your mind=cannot tell|'])
  && same(verdicts('<ul><li>Expected: the gap of 2 was not met</li><li>Expectation: a gap of 2</li></ul>'), ['You expected=not met|the gap of 2 was not met', 'You expected=|a gap of 2']));
check('the labels are found through the markup a model puts round them: bold, code, a loose list\'s paragraphs; the line\'s own markup stays',
  same(verdicts('<ul><li><p><strong>Expected:</strong> <strong>not met</strong> — gap <em>0.4</em></p></li><li><p><code>Would change their mind:</code> seen</p></li></ul>'),
       ['You expected=not met|gap 0.4', 'Would change your mind=seen|'])
  && el(A.dressAnswer('<h2>Against the brief</h2><ul><li><strong>Expected:</strong> met, gap <em>3</em></li></ul>')).querySelector('.t em').textContent === '3');
check('the part written as plain lines, not a list: one row to a line; the heading at any level, with or without a colon',
  same(verdicts('\n<p>Expected: met, gap 3<br>Would change their mind: not seen\nchance: fine</p>\n'), ['You expected=met|gap 3', 'Would change your mind=not seen|', 'Also checked=|chance: fine'])
  && el(A.dressAnswer('<h3 id="x">Against the brief:</h3><p>Expected: met</p><h3>Did not fit</h3>')).querySelector('.ar-against .v.ok').textContent === 'met');
const TABLE = '<h2>Against the brief</h2><table><tr><td>Expected</td><td>met</td></tr></table><h2>Did not fit</h2>';
const NESTED = '<h2>Against the brief</h2><ul><li>Expected: met<ul><li>a detail</li></ul></li></ul>';
check('a part the card cannot hold whole - a table, a list inside a list - is left as the report wrote it; so is a report without the part, and nothing at all',
  A.dressAnswer(TABLE) === TABLE && A.dressAnswer(NESTED) === NESTED && A.dressAnswer('<h2>Answer</h2><p>Expected: met</p>') === '<h2>Answer</h2><p>Expected: met</p>'
  && A.dressAnswer('<h2>Against the brief</h2>') === '<h2>Against the brief</h2>' && A.dressAnswer(null) === '' && A.dressAnswer(undefined) === '');
const FOOT = el(A.dressAnswer('<h2>Did not fit</h2><p>Nothing.</p><h2>Against the brief</h2><ul><li>Expected: met</li></ul><blockquote><p>Replay reproduced 3 numbers</p></blockquote>'));
check('the part at the report\'s end stops at the engine\'s own lines beneath it', FOOT.elements.map(e => e.tag).join() === 'h2,p,div,blockquote' && FOOT.querySelector('blockquote').textContent === 'Replay reproduced 3 numbers', FOOT.innerHTML);

// ------------------------------------------------------------ the thread map's mark
check('how a chain\'s question was made: a brief not yet run; framed with the Architect - by its versions while it runs, by its Brief tab once kept; nothing for a typed question',
  A.mark({ status: 'framing', framing: F1 }) === 'not run' && A.mark({ status: 'running', framing: F1, tabContent: '' }) === 'Architect'
  && A.mark({ tabContent: '<div id="tab-brief" class="tab">Brief</div><div id="tab-answer" class="tab active">Answer</div>' }) === 'Architect'
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
  let reply;                                       // the Architect's reply, held until the test lets it go
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
  check('the Architect takes its first turn at once: asked with the brief\'s thread and chain and no words of the coach\'s; while it replies the pane says it is reading, the composer is held and says why, and the brief takes no change',
    same(calls[1], ['/architect/say', { thread_id: 7, chain_id: 71, text: null }]) && same(pane(), ['you|YouIs B above A?', 'arch wait|Architectreading…'])
    && same(locks[locks.length - 1], ['lock', 'The Architect is replying']) && $('queryInput').disabled === true && doc.body.classList.contains('ar-framing') && A.framingInView() === true
    && !$('contentOutput').querySelector('.editing') && !$('contentOutput').querySelector('.ar-kinds'), [calls[1], pane(), locks.slice(-2)]);
  const F1T = { versions: F1.versions, turns: [ASK], calls: 1 };
  reply([200, stream({ framing: F1T })]); await tick();
  check('its reply, the last message of the stream: the conversation and the brief are the record\'s again - its question in the pane with its choices; the composer is the conversation\'s, its own words kept for later',
    same(entry.framing, F1T) && same(pane(), ['you|YouIs B above A?', 'arch|Architect⌘What will you do differently depending on the answer?Keep one armKeep <both>'])
    && same(locks[locks.length - 1], ['unlock']) && $('queryInput').disabled === false && $('queryInput').placeholder === 'Answer, or say what to change'
    && $('queryInput').getAttribute('data-placeholder') === 'Enter your query here' && toasts.length === 0, [entry.framing, pane(), $('queryInput').placeholder]);
  check('the brief on screen: the left pane says Architect, brief v1, with the question; one tab, Brief, drawn from the versions and open to changes',
    $('streamOutput').querySelector('.sp-strip').textContent === 'Architect' && $('streamOutput').querySelector('.ar-msg.you').textContent === 'YouIs B above A?'
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
  const serve = () => { answers['/architect/brief'] = body => { const f = JSON.parse(JSON.stringify(entry.framing)); f.versions.push({ n: f.versions.length + 1, by: 'person', changed: body.changed, brief: body.brief }); return [200, { framing: f }]; }; };
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
    same(calls[calls.length - 1], ['/architect/brief', { thread_id: 7, chain_id: 71, brief: { question: 'Is B above A?', decision: 'keep one arm' }, changed: ['decision'] }]) && entry.framing.versions.length === 2, calls[calls.length - 1]);
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

  // the versions: the arrows show another one, and what is done next goes on from it
  const before0 = entry.framing.versions.length;
  n = calls.length;
  doc.dispatch('click', brief().querySelector('[data-step="-1"]'));
  const back = brief();
  check('the arrow back shows the version before (0308): which it is of how many, its own lines with their pencils, and Start analysis naming it; nothing is sent',
    back.querySelector('.ar-ver b').textContent === (before0 - 1) + ' of ' + before0 && back.getAttribute('data-shown') === String(before0 - 1) && !lineOf(back, 'thinks') && lineOf(back, 'decision').querySelector('.pen')
    && back.querySelector('[data-ar="start"]').textContent === 'Start analysis with version ' + (before0 - 1) && calls.length === n);
  doc.dispatch('click', lineOf(brief(), 'decision').querySelector('.pen'));
  lineOf(brief(), 'decision').querySelector('.ar-input').value = 'keep the better arm';
  doc.dispatch('keydown', lineOf(brief(), 'decision').querySelector('.ar-input'), { key: 'Enter' }); await tick();
  const last = entry.framing.versions.length;
  check('a line changed on an earlier version (0308): the server is sent that version\'s brief with the change - what the version after it held is not in it - and the version it answers with is the last, on screen',
    same(calls[calls.length - 1][1].changed, ['decision']) && calls[calls.length - 1][1].brief.decision === 'keep the better arm' && !('thinks' in calls[calls.length - 1][1].brief)
    && last === before0 + 1 && brief().querySelector('.ar-ver b').textContent === last + ' of ' + last && brief().querySelector('[data-ar="start"]').textContent === 'Start analysis', calls[calls.length - 1]);
  doc.dispatch('click', brief().querySelector('[data-step="-1"]'));
  const withThinks = !!lineOf(brief(), 'thinks');
  doc.dispatch('click', lineOf(brief(), 'decision').querySelector('.pen'));
  const olderText = lineOf(brief(), 'decision').querySelector('.ar-input').textContent;
  doc.dispatch('keydown', lineOf(brief(), 'decision').querySelector('.ar-input'), { key: 'Escape' });
  const olderStill = brief().querySelector('.ar-ver b').textContent + '|' + !brief().querySelector('.editing');
  doc.dispatch('click', brief().querySelector('[data-step="1"]'));
  check('the arrows step both ways: back to the version that held the other line - there the pencil opens a line with that version\'s text, and Escape leaves that version on screen - and forward to the last',
    withThinks && olderText === 'keep one arm' && olderStill === (last - 1) + ' of ' + last + '|true' && brief().querySelector('.ar-ver b').textContent === last + ' of ' + last && !lineOf(brief(), 'thinks'),
    [olderText, olderStill]);

  // leaving and coming back; the composer
  const lockCount = locks.length;
  currentResponseIndex = 0; loadResponseContent(responses[0]); updateNavigationButtons();
  check('another chain on screen: the composer is its own again, with its own words; the page\'s mark gone', same(locks[locks.length - 1], ['unlock']) && locks.length === lockCount + 1 && !doc.body.classList.contains('ar-framing')
    && A.framingInView() === false && $('queryInput').placeholder === 'Enter your query here' && $('queryInput').getAttribute('data-placeholder') == null);
  updateNavigationButtons();
  check('the Architect lifts only its own hold: a second look at a plain chain touches nothing', locks.length === lockCount + 1);
  queryRunning = true;
  currentResponseIndex = 1; loadResponseContent(entry); updateNavigationButtons();
  check('back on the brief while another chain runs: drawn again from its versions, at the last one, with its conversation; the composer is held and says why - and that chain\'s Stop stays within reach',
    brief().querySelector('.ar-ver b').textContent === last + ' of ' + last && pane().length === 2 && same(locks[locks.length - 1], ['lock', 'Another analysis is running. Wait for it to end, or stop it.'])
    && $('queryInput').disabled === true && $('submitQuery').disabled === false);
  const before = calls.length;
  doc.dispatch('click', $('streamOutput').querySelector('.ar-choice')); await tick();
  check('nothing is said to the Architect while another analysis runs: a choice clicked sends nothing, and the page says why', calls.length === before && toasts[toasts.length - 1] === 'Another analysis is running. Wait for it to end, or stop it.');

  // Start analysis
  doc.dispatch('click', brief().querySelector('[data-ar="start"]')); await tick();
  check('Start analysis while another analysis runs: said in plain words, nothing started', submitted.length === 0 && toasts[toasts.length - 1] === 'Another analysis is running. Wait for it to end, or stop it.');
  queryRunning = false;
  addPart('expects').querySelector('.ar-input').value = 'B above A by 2';
  doc.dispatch('click', brief().querySelector('[data-ar="start"]')); await tick();
  check('Start analysis with a line still being typed: the line is kept first, then the page\'s own send starts this chain - under the version on screen, which the send is told',
    calls[calls.length - 1][1].brief.expects === 'B above A by 2' && submitted.length === 1 && submitted[0].framed === entry && Object.keys(submitted[0]).join() === 'framed,version'
    && submitted[0].version === entry.framing.versions.length && !('at' in entry.framing)
    && entry.framing.versions[entry.framing.versions.length - 1].brief.expects === 'B above A by 2', submitted);
  // what the send does next: the chain runs, the framing folds, the Brief tab stays
  entry.status = 'running';
  ['streamOutput', 'tabContainer', 'contentOutput'].forEach(id => { $(id).innerHTML = ''; });      // as the send clears the panes for the run
  A.started(entry);
  const stays = el(tabs[0][1]).querySelector('.ar-brief');
  check('the analysis begins: the framing is one row above the run; the Brief tab is made again to be read, with its versions',
    rows.length === 1 && el(rows[0]).querySelector('details.ar-fold .kind').textContent === 'brief v' + entry.framing.versions.length && tabs[0][0] === 'brief' && stays.getAttribute('data-state') === 'run'
    && !stays.querySelector('.pen') && !stays.querySelector('[data-ar="start"]') && same(JSON.parse(stays.getAttribute('data-framing')), entry.framing), rows);
  updateNavigationButtons();
  check('the composer is free once the brief runs (its send is the run\'s Stop)', same(locks[locks.length - 1], ['unlock']));
  // the server did not start it
  A.notStarted(entry, 'Network response was not ok');
  check('an analysis the server did not start: the chain is a brief again, drawn as it stood; the reason is said',
    reverted[0] === entry && entry.status === 'framing' && brief().getAttribute('data-state') === 'framing' && brief().querySelector('[data-ar="start"]') && pane().length === 2
    && same(locks[locks.length - 1], ['unlock']) && $('queryInput').placeholder === 'Answer, or say what to change' && toasts[toasts.length - 1] === 'The analysis did not start: Network response was not ok');
  const quiet = toasts.length; A.notStarted(entry);
  check('refused for the balance, the page has its own dialog: nothing more is said', toasts.length === quiet);
  // Start analysis with an earlier version on screen: the send is told which, and the chain is that version's from then on
  const lastNow = entry.framing.versions.length, textNow = entry.queryText;
  const asksOther = lastNow - entry.framing.versions.slice().reverse().findIndex(v => v.brief.question !== textNow);      // the last version that asks another question
  for (let k = lastNow; k > asksOther; k--) doc.dispatch('click', brief().querySelector('[data-step="-1"]'));
  doc.dispatch('click', brief().querySelector('[data-ar="start"]')); await tick();
  entry.status = 'running';
  A.started(entry);
  const olderRun = { sent: submitted.length, version: submitted[submitted.length - 1].version, at: entry.framing.at, text: entry.queryText, was: entry.framing.versions[asksOther - 1].brief.question,
                     tab: el(tabs[tabs.length - 1][1]).querySelector('.ar-ver b').textContent, fold: el(rows[rows.length - 1]).querySelector('.kind').textContent, calls: calls.length };
  A.notStarted(entry);
  const olderBack = brief().querySelector('.ar-ver b').textContent + '|' + brief().querySelector('[data-ar="start"]').textContent;
  entry.framing = A.use(entry.framing, lastNow); entry.queryText = textNow; loadResponseContent(entry); updateNavigationButtons();      // the last version on screen again, for what follows
  check('Start analysis with an earlier version on screen (0308) - one that asks another question than the last: nothing is sent to the brief\'s own route - the send is told the version, the chain\'s '
    + 'framing names it as the one in use and the chain\'s question is that version\'s; the run\'s Brief tab and the fold above it show that version; an analysis the server did not start leaves the '
    + 'brief on it',
    asksOther < lastNow && olderRun.was !== textNow
    && same(olderRun, { sent: 2, version: asksOther, at: asksOther, text: olderRun.was, was: olderRun.was, tab: asksOther + ' of ' + lastNow, fold: 'brief v' + asksOther, calls: olderRun.calls })
    && olderBack === asksOther + ' of ' + lastNow + '|Start analysis with version ' + asksOther && !('at' in entry.framing), [asksOther, lastNow, olderRun, olderBack]);

  // the conversation: a choice clicked, an answer typed, a reply that does not come
  const latest = () => entry.framing.versions[entry.framing.versions.length - 1];
  const answered = (said, text, version, more) => { const f = JSON.parse(JSON.stringify(entry.framing));
    if (version) f.versions.push(Object.assign({ n: f.versions.length + 1, by: 'architect', why: 'answer' }, version));
    f.turns = f.turns.concat([{ who: 'person', text: said }, Object.assign({ who: 'architect', text, v: f.versions.length, cost: 0.02, call: (f.calls || 0) + 1 }, more || {})]); f.calls = (f.calls || 0) + 1; return f; };
  held();
  doc.dispatch('click', $('streamOutput').querySelector('.ar-choice')); await tick();
  const sent = calls[calls.length - 1];
  doc.dispatch('click', lineOf(brief(), 'decision').querySelector('.pen'));
  check('a choice clicked is the coach\'s answer: said to the Architect as it reads, shown at once as the coach\'s message; the choices are gone, the Architect is reading, the composer is held, the brief takes no change',
    same(sent, ['/architect/say', { thread_id: 7, chain_id: 71, text: 'Keep one arm', version: entry.framing.versions.length }]) && same(pane().slice(-2), ['you|YouKeep one arm', 'arch wait|Architectreading…'])
    && $('streamOutput').querySelectorAll('.ar-choice').length === 0 && same(locks[locks.length - 1], ['lock', 'The Architect is replying']) && !brief().querySelector('.editing'), [sent, pane()]);
  const was = entry.framing.versions.length;
  reply([200, stream({ framing: answered('Keep one arm', 'What do you expect to see?', { changed: ['decision'], brief: Object.assign({}, latest().brief, { decision: 'Keep one arm' }) }) })]); await tick();
  check('the reply: the brief shows the version the Architect made from the answer, the changed line marked; the pane has both messages and what the calls have cost; the composer is the conversation\'s again',
    entry.framing.versions.length === was + 1 && brief().querySelector('.ar-ver b').textContent === (was + 1) + ' of ' + (was + 1) && !brief().querySelector('.why')
    && lineOf(brief(), 'decision').className === 'ar-line changed' && lineOf(brief(), 'decision').querySelector('.tx').textContent === 'Keep one arm'
    && same(pane().slice(-2), ['you|YouKeep one arm', 'arch|Architect⌘What do you expect to see?']) && $('streamOutput').querySelector('.sp-strip').textContent === 'Architect$0.02'
    && same(locks[locks.length - 1], ['unlock']) && $('queryInput').placeholder === 'Answer, or say what to change', [pane(), $('streamOutput').querySelector('.sp-strip').textContent]);
  // a reply that words the question (0308): the Architect writes it at once, and the chain's own text follows
  const asked1 = entry.framing.versions[0].brief.question;
  held();
  A.tell('Yes, like that'); await tick();
  reply([200, stream({ framing: answered('Yes, like that', 'I have put that into the question.\n\nLook at how far apart the two end.', { changed: ['question'], brief: Object.assign({}, latest().brief, { question: 'Is B above A, on plot means?' }) },
                                         { wording: 'Is B above A, on plot means?' }) })]); await tick();
  check('a reply that words the question (0308): the Architect\'s version holds it, the question\'s box shows it, marked as changed, and the chain\'s own text follows; under the message a row says the '
    + 'question was updated, and in which version - nothing is there to take; the conversation still opens on the question as it was first asked, and a message keeps its lines',
    entry.queryText === 'Is B above A, on plot means?' && brief().querySelector('h1 .tx').textContent === 'Is B above A, on plot means?' && brief().querySelector('h1').className === 'ar-line ar-q changed'
    && $('streamOutput').querySelectorAll('.sp-row').map(r => r.textContent).slice(-1)[0] === '✓QUESTIONupdatedversion ' + entry.framing.versions.length
    && !$('streamOutput').querySelector('.ar-wording') && !$('streamOutput').querySelector('[data-ar="use"]') && !brief().querySelector('.ar-wording') && pane()[0] === 'you|You' + asked1 && asked1 !== entry.queryText
    && pane()[pane().length - 1] === 'arch|Architect⌘I have put that into the question.\n\nLook at how far apart the two end.', [entry.queryText, pane()[0], pane()[pane().length - 1]]);
  // an answer typed, with a line of the brief still open: the line is kept first, then the answer is said
  serve();
  addPart('fixed.period').querySelector('.ar-input').value = 'this season';
  $('queryInput').value = 'B above A by 3';
  held(); n = calls.length;
  A.tell('  B above A by 3 '); await tick();
  check('an answer typed in the composer while a line of the brief is being typed: the line is kept first, as a version of the coach\'s; then the answer is said, the composer emptied',
    calls.length === n + 2 && calls[n][0] === '/architect/brief' && calls[n][1].brief.fixed.period === 'this season' && same(calls[n + 1], ['/architect/say', { thread_id: 7, chain_id: 71, text: 'B above A by 3', version: entry.framing.versions.length }])
    && $('queryInput').value === '' && latest().by === 'person' && h3s(brief()).indexOf('Period') >= 0 && pane()[pane().length - 2] === 'you|YouB above A by 3', calls.slice(n));
  const stood = JSON.stringify(entry.framing);
  reply([200, stream({ error: 'The Architect\'s reply could not be read (it holds no JSON object).' })]); await tick();
  check('a reply that could not be kept: the reason is said, the brief and the conversation stand as they did, and what was typed is back in the composer',
    toasts[toasts.length - 1] === 'The Architect\'s reply could not be read (it holds no JSON object).' && JSON.stringify(entry.framing) === stood && pane()[pane().length - 1] === 'arch|Architect⌘I have put that into the question.\n\nLook at how far apart the two end.'
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
    refusedSay === 'You need $0.010 per query but your balance is $0.00. Please add funds to continue.' && toasts[toasts.length - 2] === 'The Architect did not reply: the server could not be reached.'
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
    cutShort === 'Provider error 402: the provider account is out of credit.' && onlyTraffic === 'The Architect did not reply.' && toasts.length === quietly && JSON.stringify(entry.framing) === stood, toasts.slice(-3));
  // a reply that had the data looked up: the round is a row of the conversation, and the Architect goes on at once, with nothing said
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
  check('a reply that had the data looked up: the round is a row under its message, and the Architect is asked again at once with nothing said - the pane says it is reading, the composer stays held, nothing to click',
    same(goesOn.calls, [['/architect/say', { thread_id: 7, chain_id: 71, text: 'B well above A', version: asking.versions.length }], ['/architect/say', { thread_id: 7, chain_id: 71, text: null }]])
    && same(goesOn.pane, ['you|YouB well above A', 'arch|Architect⌘Checking this against the data.', 'arch wait|Architectreading…']) && goesOn.rows === 2 && goesOn.choices === 0      // the round's row, under the row of the question worded before
    && same(goesOn.lock, ['lock', 'The Architect is replying']), goesOn);
  check('the reply after the round: one more version, made after checking the data - the line with its mark and, in red, the fact beside it; the question whether to keep or change, with its choices; no further call, and the composer is the conversation\'s again',
    calls.length === n + 2 && same(entry.framing, marking) && brief().querySelector('.ar-ver b').textContent === marking.versions.length + ' of ' + marking.versions.length && line0.className === 'ar-line changed'
    && line0.querySelector('.mk.no').textContent === '✕' && line0.querySelector('.fact.no').textContent === 'rows by arm: A 3 · B 3'
    && same($('streamOutput').querySelectorAll('.ar-choice').map(c => c.textContent), ['Keep it', 'Change it']) && $('streamOutput').querySelectorAll('.sp-row').length === 2
    && same(locks[locks.length - 1], ['unlock']) && $('queryInput').value === '' && $('queryInput').placeholder === 'Answer, or say what to change', [calls.slice(n), pane().slice(-2)]);
  // what the Architect proposed: a tick accepts it, another takes the tick back - each a version of the coach's
  serve(); n = calls.length;
  const boxWas = lineOf(brief(), 'also_check.0').querySelector('.tick').className + '|' + lineOf(brief(), 'also_check.0').querySelector('.src').textContent + '|' + lineOf(brief(), 'also_check.0').className;
  doc.dispatch('click', lineOf(brief(), 'also_check.0').querySelector('.tick')); await tick();
  const ticked = { call: calls[n], box: lineOf(brief(), 'also_check.0').querySelector('.tick').className, ver: brief().querySelector('.ar-ver b').textContent, line: lineOf(brief(), 'also_check.0').className, by: latest().by };
  doc.dispatch('click', lineOf(brief(), 'expects').querySelector('.pen'));
  lineOf(brief(), 'expects').querySelector('.ar-input').value = 'B above A by 4';
  doc.dispatch('click', lineOf(brief(), 'also_check.0').querySelector('.tick')); await tick();
  check('the box on what the Architect proposed: a click sends the brief with the line accepted, and the tab shows the new version - the box ticked, the line marked; another click takes the '
    + 'tick back - a line being typed elsewhere kept first, as its own version',
    boxWas === 'tick|Architect|ar-line changed' && same(ticked.call, ['/architect/brief', { thread_id: 7, chain_id: 71, brief: Object.assign({}, marking.versions[marking.versions.length - 1].brief, { also_check: [Object.assign({}, ITS, { accepted: true })] }), changed: ['also_check.0'] }])
    && ticked.box === 'tick on' && ticked.ver === (marking.versions.length + 1) + ' of ' + (marking.versions.length + 1) && ticked.line === 'ar-line changed' && ticked.by === 'person'
    && calls.length === n + 3 && same(calls[n + 1][1].changed, ['expects']) && calls[n + 1][1].brief.expects === 'B above A by 4' && calls[n + 1][1].brief.also_check[0].accepted === true
    && same(calls[n + 2][1].changed, ['also_check.0']) && calls[n + 2][1].brief.also_check[0].accepted === false && calls[n + 2][1].brief.expects === 'B above A by 4'
    && lineOf(brief(), 'also_check.0').querySelector('.tick').className === 'tick' && !brief().querySelector('.editing'), [boxWas, ticked, calls.slice(n + 1)]);
  held(); n = calls.length;
  A.tell('and the other line?'); await tick();
  const again = JSON.parse(JSON.stringify(entry.framing));
  again.turns = again.turns.concat([{ who: 'person', text: 'and the other line?' }, { who: 'architect', text: 'Checking.', v: again.versions.length, call: 11 }, CHECK]);
  reply([200, stream({ framing: again })]); await tick();
  reply([200, stream({ error: 'The Architect\'s reply could not be read (it holds no JSON object).' })]); await tick();
  check('the Architect not going on after a round: the reason is said, and the conversation stands with the round as its last thing - the coach\'s message was taken, so it does not come back into the composer, which is theirs again; nothing is asked a third time',
    calls.length === n + 2 && toasts[toasts.length - 1] === 'The Architect\'s reply could not be read (it holds no JSON object).' && same(entry.framing, again)
    && pane()[pane().length - 1] === 'arch|Architect⌘Checking.' && $('streamOutput').querySelectorAll('.sp-row').length === 3 && $('queryInput').value === '' && same(locks[locks.length - 1], ['unlock']), [calls.slice(n), toasts.slice(-1), pane().slice(-2)]);
  // the Architect replying while the coach looks elsewhere
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
  check('while the Architect replies, another question is not framed - the page says why; the coach can look at another chain, whose composer is its own; the reply lands on its brief, and is there when they come back',
    elsewhere === 'The Architect is replying.' && calls.length === n && freeThere && untouched && pane()[pane().length - 1] === 'arch|Architect⌘The brief is ready: start the analysis, or change a line.'
    && lineOf(brief(), 'expects').querySelector('.tx').textContent === 'B above A by 3' && $('queryInput').placeholder === 'Answer, or say what to change', [elsewhere, freeThere, untouched, pane().slice(-1)]);

  // the saved analyses read in an exchange (0303; 0308): the stream says how far the reading is, Skip, and the Architect goes on with nothing said; what was found
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
  check('a reply that has the saved analyses read: while they are read the pane shows a row in the place of the Architect\'s wait - how many are saved, then how many are read, a line of the stream cut in two '
    + 'taken whole - the held composer says so, and Skip tells the server once; the reading done, its row stands under the Architect\'s message with the analyses found under it, the Brief tab lists them in '
    + 'full under the brief - which has not changed: no version, nothing built on - and the Architect is asked again with nothing said',
    !early && opened === 'SAVED analyseslooking through 12Skip' && waitGone && holds === 'Your saved analyses are being read' && mid === 'reading 5 of 12' && same(skipped, { call: ['/architect/skip', {}], off: true })
    && same(went.calls, [['/architect/say', { thread_id: 7, chain_id: 71, text: 'Go on.', version: shownGo }], ['/architect/skip', {}], ['/architect/say', { thread_id: 7, chain_id: 71, text: null }]])
    && same(went.pane, ['arch|Architect⌘I am looking in your saved analyses.', 'arch wait|Architectreading…']) && went.row === '✓SAVED analyses2 analyses found · read 9 of 1241 s' && !went.pending
    && went.left === '2 Mar 2026 · Was B above A in <spring>?|2 Apr 2026 · Synthesis: Two arms' && went.right === 2 && went.ver === shownGo + ' of ' + shownGo && !went.built && same(entry.framing, told)
    && pane()[pane().length - 1] === 'arch|Architect⌘You asked this in spring. Build on it, or go another way?Build on the spring oneGo another way', [opened, mid, skipped, went]);
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
  // 'build on it', said by a choice: the Architect's reply brings the analysis into the brief; the cross takes it out again
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
  check('\'build on it\' (0308): the coach\'s choice is said to the Architect like any answer; its reply brings the analysis into the brief - one line under Builds on, however many passages, marked as '
    + 'changed, with View - and the list under the brief marks the analysis as built on. The cross on that line sends the brief without its passages - a version of the coach\'s - and the part is gone, '
    + 'the mark with it; what was found stays listed',
    same(builtNow.said, ['/architect/say', { thread_id: 7, chain_id: 71, text: 'Build on the spring one', version: told.versions.length }])
    && same(builtNow, { said: builtNow.said, heads: 'Builds on|Found in your saved analyses', line: 'ar-line ar-built changed|2 Mar 2026 · Was B above A in <spring>?', lines: 1, tags: 'built on|', view: 'View' })
    && calls.length === n + 1 && same(calls[n][1].changed, ['saved']) && !('saved' in calls[n][1].brief) && latest().by === 'person' && !brief().querySelector('.ar-built') && h3s(brief()).indexOf('Builds on') < 0
    && brief().querySelectorAll('.ar-memory .it').length === 2 && !brief().querySelector('.ar-memory .tag') && !brief().querySelector('[data-ar="look"]') && !brief().querySelector('.ar-memory .tick') && !brief().querySelector('.ar-built .tick'), [builtNow, calls[n]]);
  // the coach goes back to an earlier version and answers from it: the version rides with the message, and a row says which is in use
  const lastB = entry.framing.versions.length;
  doc.dispatch('click', brief().querySelector('[data-step="-1"]'));
  held(); n = calls.length;
  A.tell('From this one, then.'); await tick();
  const fromOlder = { call: calls[n], at: entry.framing.at, shown: brief().querySelector('.ar-ver b').textContent };
  const older = JSON.parse(JSON.stringify(entry.framing));
  older.turns = older.turns.concat([{ who: 'version', v: lastB - 1 }, { who: 'person', text: 'From this one, then.' }, { who: 'architect', text: 'As you say.', v: lastB - 1, cost: 0.01, call: 21 }]);
  reply([200, stream({ framing: older })]); await tick();
  check('an answer sent from an earlier version (0308): the message carries the version on screen; that version is the one in use at once, and the tab stays on it; after the reply a row in '
    + 'the conversation says which version is in use, before the message that came with it; the tab stays on that version, and Start analysis names it',
    same(fromOlder, { call: ['/architect/say', { thread_id: 7, chain_id: 71, text: 'From this one, then.', version: lastB - 1 }], at: lastB - 1, shown: (lastB - 1) + ' of ' + lastB })
    && $('streamOutput').querySelectorAll('.sp-row').map(r => r.textContent).slice(-1)[0] === '✓BRIEFversion ' + (lastB - 1) + ' in use' && pane().slice(-2)[0] === 'you|YouFrom this one, then.'
    && brief().querySelector('.ar-ver b').textContent === (lastB - 1) + ' of ' + lastB && brief().querySelector('[data-ar="start"]').textContent === 'Start analysis with version ' + (lastB - 1)
    && h3s(brief()).indexOf('Builds on') >= 0, [fromOlder, brief().querySelector('.ar-ver b').textContent]);
  entry.framing = A.use(entry.framing, lastB); loadResponseContent(entry); updateNavigationButtons();      // the last version again, for what follows
  const textB = entry.queryText, otherB = lastB - entry.framing.versions.slice().reverse().findIndex(v => v.brief.question !== textB);      // the last version that asks another question
  for (let k = lastB; k > otherB; k--) doc.dispatch('click', brief().querySelector('[data-step="-1"]'));
  held();
  A.tell('And from here.'); await tick();
  doc.dispatch('click', brief().querySelector('[data-step="1"]'));
  const steppedMid = brief().querySelector('.ar-ver b').textContent;
  const fromOther = JSON.parse(JSON.stringify(entry.framing));
  fromOther.turns = fromOther.turns.concat([{ who: 'version', v: otherB }, { who: 'person', text: 'And from here.' }, { who: 'architect', text: 'From there, then.', v: otherB, cost: 0.01, call: 22 }]);
  reply([200, stream({ framing: fromOther })]); await tick();
  check('an answer from a version that asks another question (0308): once the reply is in, the chain\'s own text is the question of the version in use; and while the Architect replies the arrows '
    + 'still step',
    otherB < lastB && steppedMid === (otherB + 1) + ' of ' + lastB && entry.framing.at === otherB && entry.queryText === entry.framing.versions[otherB - 1].brief.question && entry.queryText !== textB
    && brief().querySelector('.ar-ver b').textContent === otherB + ' of ' + lastB, [otherB, lastB, steppedMid, entry.queryText]);
  entry.framing = A.use(entry.framing, lastB); entry.queryText = textB; loadResponseContent(entry); updateNavigationButtons();
  // a part of an earlier analysis opened (0307): a row of the conversation, and the Architect goes on at once
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
  check('a reply that opened a part of an earlier analysis: the part is a row under its message - READ, what it is, how long - and the Architect is asked again at once with nothing said; its next message '
    + 'stands under the row, and no further call is made',
    same(openedNow.calls, [['/architect/say', { thread_id: 7, chain_id: 71, text: 'How was the figure drawn?', version: opening.versions.length }], ['/architect/say', { thread_id: 7, chain_id: 71, text: null }]])
    && openedNow.row === '✓READcell 51,234 characters' && openedNow.wait === 'arch wait|Architectreading…' && same(openedNow.lock, ['lock', 'The Architect is replying'])
    && calls.length === n + 2 && pane()[pane().length - 1] === 'arch|Architect⌘It draws one line a month.' && same(locks[locks.length - 1], ['unlock']), openedNow);
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
  const figsNow = () => brief().querySelectorAll('.ar-fig').map(f => f.className + ':' + f.querySelector('.n').textContent + ':' + f.querySelector('.t').textContent + ':' + f.querySelector('.tag').textContent).join('|');
  const lastRow = () => $('streamOutput').querySelectorAll('.sp-row').map(r => r.className + ':' + r.textContent).slice(-1)[0];
  const asked = () => calls.slice(n).map(c => c[0]), drew = () => plotted.map(p => p.key + ':' + p.layout.height + ':' + p.layout.annotations.map(a => a.text).join() + ':' + p.config.displayModeBar + ':' + p.data.length);
  liveD.send(JSON.stringify({ type: 'architect_saved', read: 1, of: 3 }) + '\n'); await tick();
  const asksNow = entry.queryText; entry.queryText = 'as it was before the reply';
  liveD.send(JSON.stringify({ type: 'architect_draft', chain_id: 71, framing: replied }) + '\n'); await tick();
  const taken = entry.queryText === asksNow;
  A.restore({ status: 'framing', chain_id: 73, thread_id: 7, queryText: 'q', framing: { versions: [{ n: 1, by: 'architect', changed: [], brief: { question: 'q', figures: [ON_DATA] }, keys: ['zz'] }], turns: [] } });
  const elsewhere = { drawing: brief().getAttribute('data-drawing'), lines: brief().querySelectorAll('.ar-fig .cap .ph').length, chain: brief().getAttribute('data-chain') };
  A.restore(entry);
  doc.dispatch('click', brief().querySelector('[data-ar="step"][data-step="-1"]')); doc.dispatch('click', brief().querySelector('[data-ar="step"][data-step="1"]')); await tick();
  const meanwhile = { figs: figsNow(), lines: brief().querySelectorAll('.ar-fig .cap .ph').map(x => x.textContent).join('|'), pane: pane().slice(-2), said: pane().filter(m => m === 'you|YouShow me what it will look like').length,
                      row: lastRow(), hold: $('queryInput').placeholder, choices: $('streamOutput').querySelectorAll('.ar-choice').length, asked: asked(), drew: drew(), drawing: brief().getAttribute('data-drawing'),
                      thread: brief().getAttribute('data-thread'), versions: entry.framing.versions.length };
  const drawnF = JSON.parse(JSON.stringify(replied));
  Object.assign(drawnF, { drafts: { k1: { basis: 'computed' }, k2: { basis: 'made up' } }, draft_calls: 1 });
  drawnF.turns.push({ who: 'draft', drawn: [{ title: 'Two <paths>', basis: 'computed' }, { title: 'Yield by season', basis: 'made up' }], v: drawnF.versions.length, secs: 6.2, cost: 0.002, call: 1 });
  liveD.send(JSON.stringify({ architect: { framing: drawnF } }) + '\n'); liveD.end(); await tick();
  const drawnNow = { figs: figsNow(), heads: h3s(brief()).split('|').slice(-2).join('|'), row: lastRow(), hold: $('queryInput').placeholder, choices: $('streamOutput').querySelectorAll('.ar-choice').length, asked: asked(), drew: drew(),
                     drawing: brief().getAttribute('data-drawing'), by: latest().by, crosses: brief().querySelectorAll('.ar-fig [data-ar="unfigure"]').length, held: brief().querySelectorAll('.ar-fig .plot svg').length,
                     made: brief().querySelectorAll('.ar-fig .cap .mu').length };
  const sketchedAt = entry.framing.versions.length;
  doc.dispatch('click', brief().querySelector('[data-ar="step"][data-step="-1"]')); await tick();
  const back = { figs: figsNow(), drew: plotted.length };
  doc.dispatch('click', brief().querySelector('[data-ar="step"][data-step="1"]')); await tick();
  const again = { figs: figsNow(), drew: plotted.length, asked: asked().length };
  check('a reply and the draft of its figures (0310): the coach asks in words, like any answer. The stream first carries the framing with the reply: its message stands - once - with a row under it '
    + 'that a draft is on its way - not the row of the reading that came before it -, the composer is held with those words, the chain\'s question is the reply\'s, the figures stand in the '
    + 'brief as sketches that say a draft is being drawn - still after a step to another version and back, and not in another chain\'s brief - and nothing is asked of the server yet. '
    + 'The stream ends on the framing with the draft: each figure is drawn by Plotly in its place - its plot asked for once, under the thread, the chain and the figure\'s key - as its layout '
    + 'fitted to the panel, the words across the one on made-up numbers; the row says how many were drawn, the reply\'s choices can be clicked, the composer is the conversation\'s again. '
    + 'Stepping to a version without figures and back draws them again, with nothing asked of the server',
    same(meanwhile, { figs: 'ar-fig changed:1:Two <paths>:sketch|ar-fig changed:2:Yield by season:sketch', lines: 'Drawing a draft…|Drawing a draft…',
                      pane: ['you|YouShow me what it will look like', 'arch|Architect⌘A draft is being drawn. Is that what you want to see?'], said: 1, row: 'sp-row tool read pending:FIGURESdrawing a draft…',
                      hold: 'A draft of the figures is being drawn', choices: 0, asked: ['/architect/say'], drew: [], drawing: '1', thread: '7', versions: sketchedAt })
    && taken && same(elsewhere, { drawing: null, lines: 0, chain: '73' })
    && same(drawnNow, { figs: 'ar-fig drawn changed:1:Two <paths>:draft|ar-fig drawn changed:2:Yield by season:draft · made-up numbers', heads: 'What it will look like|Found in your saved analyses',
                        row: 'sp-row tool read:✓FIGURES2 drawn6 s⌘', hold: 'Answer, or say what to change', choices: 2, asked: ['/architect/say', '/architect/draft/7/71/k1', '/architect/draft/7/71/k2'],
                        drew: ['k1:360::false:1', 'k2:560:made-up numbers:false:1'], drawing: null, by: 'architect', crosses: 2, held: 2, made: 1 })
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
    cuts.push({ told: toasts.length - told, typed: $('queryInput').value, hold: $('queryInput').placeholder, drawing: brief().getAttribute('data-drawing'), figs: figsNow(), lines: brief().querySelectorAll('.ar-fig .cap .ph').length,
                last: pane().slice(-1)[0], choices: $('streamOutput').querySelectorAll('.ar-choice').length, lock: locks[locks.length - 1], kept: same(entry.framing, shown), rows: $('streamOutput').querySelectorAll('.sp-row.pending').length });
  }
  check('a stream that ends while the draft is drawn (0310): the reply the page shows stands - nothing says the Architect did not reply, what was typed is not put back, the figures are sketches '
    + 'that no longer say a draft is on its way, the row that said so is gone, the reply\'s choices can be clicked and the composer is free - whether the stream ended without its last line or was cut',
    cuts.length === 2 && cuts.every(c => same(c, { told: 0, typed: '', hold: 'Answer, or say what to change', drawing: null, figs: 'ar-fig changed:1:Yield by season:sketch', lines: 0,
                                                 last: 'arch|Architect⌘A draft is being drawn.Yes', choices: 1, lock: ['unlock'], kept: true, rows: 0 })), cuts);
  // a plot that cannot be had, a page without Plotly, a tab that came with its markup, and what a saved analysis drew
  const kept = entry.framing, wasPlotly = global.Plotly;
  const lone = (key, basis, more) => Object.assign({ versions: [{ n: 1, by: 'architect', changed: [], brief: Object.assign({ question: 'q', figures: [ON_DATA] }, more), keys: [key] }], drafts: { [key]: { basis } }, turns: [] });
  answers['/architect/draft/7/71/gone'] = [404, { error: 'No draft is kept for this figure.' }];
  entry.framing = lone('gone', 'made up'); n = calls.length; plotted.length = 0;
  loadResponseContent(entry); await tick();
  const gone = { fig: figsNow(), made: brief().querySelectorAll('.cap .mu').length, tag: brief().querySelector('.ar-fig .tag').className, drew: plotted.length, asked: asked(), shown: !!brief().querySelector('.ar-fig svg[role="img"]'),
                 place: !!brief().querySelector('.ar-fig .plot') };
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
  answers['/get_chain_preview/7301/7302'] = [200, { threadId: '7301', chainId: '7302', hasPlotly: true, plotPreview: 'data:image/png;base64,AAAA' }];
  answers['/get_chain_preview/7301/7309'] = [200, { threadId: '7301', chainId: '7309', hasPlotly: false }];
  entry.framing = lone('k2', 'made up', { saved: SAVED_ON }); n = calls.length;
  loadResponseContent(entry); await tick();
  const was = brief().querySelectorAll('.ar-was');
  const built = { holders: was.map(w => w.getAttribute('data-thread') + '/' + w.getAttribute('data-run')).join(), first: was[0].elements.map(e => e.tag + ':' + (e.getAttribute('src') || e.textContent)).join('|'),
                  second: was[1].innerHTML, under: brief().querySelectorAll('.ar-built')[0].parent.elements.indexOf(was[0]) - brief().querySelectorAll('.ar-built')[0].parent.elements.indexOf(brief().querySelectorAll('.ar-built')[0]),
                  asked: asked().sort(), fig: figsNow() };
  doc.dispatch('click', brief().querySelector('[data-ar="more"]')); await tick();
  const twice = { asked: asked().length, first: brief().querySelector('.ar-was img') ? brief().querySelector('.ar-was img').getAttribute('src') : '' };
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
  check('where a plot cannot be had (0310): a figure whose plot the server no longer holds is its sketch again - the tag says so, and nothing says its numbers are made up - and the server is '
    + 'not asked for it a second time, and the plot\'s place is gone; where the server was not reached, or its answer failed, the figure is a sketch for now and its plot is asked for again '
    + 'when the tab is next drawn. Every figure is a sketch '
    + 'on a page without Plotly; nothing breaks. What a saved analysis drew stands under the line that builds on it, where its favourite kept a picture - asked for once, however often the '
    + 'tab is drawn - and nothing stands there where it kept none. A Brief tab that came with its markup - a run restored - has its drafts drawn in it again, in the place of what the markup '
    + 'held, once however often the page looks at it; and the Brief tab of an analysis that starts has its drafts drawn, asked for under its thread and chain',
    same(gone, { fig: 'ar-fig:1:Yield by season:sketch', made: 0, tag: 'tag', drew: 0, asked: ['/architect/draft/7/71/gone'], shown: true, place: false }) && same(goneStill, { fig: gone.fig, asked: 1 })
    && down === 'ar-fig:1:Yield by season:sketch' && failed === down && same(up, { fig: 'ar-fig drawn:1:Yield by season:draft', drew: 'later', asked: 3 })
    && same(bare, { fig: 'ar-fig:1:Yield by season:sketch', drew: 0 })
    && same(built, { holders: '7301/7302,7301/7309', first: 'img:data:image/png;base64,AAAA|div:What it drew then', second: '', under: 1, asked: ['/get_chain_preview/7301/7302', '/get_chain_preview/7301/7309'],
                     fig: 'ar-fig drawn:1:Yield by season:draft · made-up numbers' })
    && same(twice, { asked: 2, first: 'data:image/png;base64,AAAA' })
    && same(cameBack, { drew: 'k2:1', live: true, stale: false, asked: [], cross: false }) && same(again2, { drew: 1, svgs: 1 })
    && same(ran, { state: 'run', asked: ['/architect/draft/7/74/run1'], drew: 'run1', cross: false }), [gone, goneStill, down, failed, up, bare, built, twice, cameBack, again2, ran]);
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

  // a chain kept with its brief: the tab alone steps through the versions
  const done = { chain_id: 80, thread_id: 7, queryText: 'A framed question', tabContent: '<div id="tab-brief" class="tab active">Brief</div>',
                 contentOutput: '<div id="content-brief" class="tab-content active">' + b.brief(F3, { chain: 80, state: 'run' }) + '</div>', streamOutput: '' };
  responses.push(done); currentResponseIndex = 2; loadResponseContent(done); updateNavigationButtons();
  doc.dispatch('click', brief().querySelector('[data-step="-1"]'));
  doc.dispatch('click', brief().querySelector('[data-step="-1"]'));
  const first = brief().querySelector('.ar-ver b').textContent + '|' + !!brief().querySelector('.why') + '|' + brief().querySelectorAll('.pen').length;
  doc.dispatch('click', brief().querySelector('[data-step="-1"]'));
  n = calls.length;
  doc.dispatch('click', brief().querySelector('h1'));
  check('a restored chain: its Brief tab steps through the versions from its own markup, down to the first and no further; nothing can be changed, nothing is sent',
    first === '1 of 3|false|0' && brief().querySelector('.ar-ver b').textContent === '1 of 3' && !brief().querySelector('[data-ar="start"]') && brief().getAttribute('data-state') === 'run' && calls.length === n && A.mark(done) === 'Architect', first);

  // ---- the page's hooks, from the source ----
  const root = path.join(__dirname, '..', '..', 'web_app'), js = f => fs.readFileSync(path.join(root, 'static', 'js', f), 'utf8'), css = f => fs.readFileSync(path.join(root, 'static', 'css', f), 'utf8');
  const html = fs.readFileSync(path.join(root, 'templates', 'index.html'), 'utf8'), qp = js('query-processing.js'), wm = js('workflow-management.js'), cr = js('content-rendering.js');
  check('index.html: the switch sits after the mode control, in the composer\'s row of icons; architect.js is loaded after the modules it leans on; the app starts it',
    html.indexOf('id="architectSwitch"') > html.indexOf('id="modeParams"') && html.indexOf('id="architectSwitch"') < html.indexOf('id="submitQuery"')
    && /<button id="architectSwitch" type="button" class="ar-switch" aria-pressed="false" title="Architect: write a brief before the analysis runs">/.test(html)
    && html.indexOf('js/architect.js') > html.indexOf('js/code-map.js') && html.indexOf('js/architect.js') > html.indexOf('js/routines.js') && js('core.js').includes('window.ArchitectUI.initialize();'));
  check('the send: only the composer\'s own send is framed (the button, Ctrl+Enter); with a brief not yet run on screen what is typed is said to the Architect and nothing else starts; a brief\'s analysis names its run and where it attached',
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
  check('the tabs: a Brief tab takes the markup architect.js builds; the answer is dressed where it is rendered, technical and plain',
    /case 'comparison':[^\n]*\n\s*case 'brief':[^\n]*\n\s*content = String\(data == null \? '' : data\);/.test(cr) && (cr.match(/window\.ArchitectUI\.dressAnswer\(finalContent\)/g) || []).length === 2);
  const graph = js('workflowGraph.js');
  check('the thread map: a box says how its question was made; a brief not yet run has no code map to open',
    graph.includes("var made = window.ArchitectUI ? window.ArchitectUI.mark(resp) : '';") && graph.includes("madeSpan.className = 'wf-node-made';") && graph.includes("if (made === 'not run') div.classList.add('wf-node--notrun');")
    && graph.includes("if (resp && resp.chain_id && made !== 'not run') {"));
  const shell = css('shell.css'), tabsCss = css('tabs.css'), paneCss = css('pane.css');
  check('the stylesheets: the switch and the map\'s tag in shell.css, the conversation\'s cards and choices in pane.css, the Brief tab and the answer\'s card in tabs.css',
    shell.includes('.left-panel .icon-row .ar-switch.on {') && shell.includes('#workflowMapModal .wf-node-made {') && shell.includes('#workflowMapModal .wf-node--notrun {')
    && paneCss.includes('#streamOutput .ar-msg {') && paneCss.includes('#streamOutput .ar-msg.arch {') && paneCss.includes('#streamOutput .ar-msg.wait {') && paneCss.includes('#streamOutput .ar-choice {')
    && tabsCss.includes('#content-brief .ar-line.changed::before {') && tabsCss.includes('#content-brief .ar-foot { position: sticky;')
    && tabsCss.includes('#content-brief .ar-line .tick {') && tabsCss.includes('#content-brief .ar-line .tick.on {')
    && tabsCss.includes('#content-answer .ar-against {') && tabsCss.includes('#content-answer .ar-against .r { display: contents; }') && ['ok', 'no', 'q'].every(v => tabsCss.includes('#content-answer .ar-against .v.' + v + ' {')));
  check('the stylesheets, 0308: the version control with its name and its arrows, the one control that adds a part and the list it opens, the line of what is always tested, a saved analysis built on and '
    + 'what the readings found are styled in tabs.css; what a reading found under its row in pane.css. The pencil is in view at rest; the cross shows under the mouse, and stays in view on a saved '
    + 'analysis built on. Nothing is left of the wording\'s card, the parts on offer by chips, a passage as a line, or the button that had the saved analyses read; the page\'s words for the Brief tab '
    + 'are plain ones, and none says a part is "not said" or "left to" anyone',
    ['.ar-top {', '.ar-top .label {', '.ar-gets {', '.ar-ver {', '.ar-ver .k {', '.ar-ver b {', '.ar-ver button {', '.ar-ver button:disabled {', '.ar-always {', '.ar-more {', '.ar-add {', '.ar-kinds {', '.ar-kinds button {',
     '.ar-built {', '.ar-memory {', '.ar-memory .note {', '.ar-memory .q {', '.ar-memory .qt {', '.ar-memory .why {', '.ar-memory .tag {'].every(s => tabsCss.includes('#content-brief ' + s))
    && ['.ar-found {', '.ar-found .hd {', '.ar-found .q {', '.ar-found .ar-open {'].every(s => paneCss.includes('#streamOutput ' + s))
    && /#content-brief \.ar-line \.pen, #content-brief \.ar-line \.drop \{[^}]* opacity: \.85; \}/.test(tabsCss) && tabsCss.includes('#content-brief .ar-line .drop { opacity: 0; }')
    && !/\.pen\b[^{}]*\{[^}]*opacity: 0;/.test(tabsCss)
    && tabsCss.includes('#content-brief .ar-line:hover .drop, #content-brief .ar-line .drop:focus-visible, #content-brief .ar-built .drop { opacity: .85; }')
    && !/ar-wording|ar-use|ar-chips|ar-grid|ar-look|ar-saved \.|\.tx\.add|\.ar-ver \.step|\.src\.mem/.test(tabsCss) && !/ar-wording|ar-use/.test(paneCss)
    && !/not said|left to the Analyst|unsaid|Use this wording|Look in saved|Fixed before the run|from your answer|changed by you/.test(js('architect.js'))
    && ["asked: 'What the Analyst will be asked'", "gets: 'This is what the Analyst gets. Change any line before you start.'", "decision: 'What it is for'", "rests_on: 'Why you think so'", "expects: 'What you expect to see'",
        "would_change: 'What would change your mind'", "also_check: 'Other explanations to test'", "builds: 'Builds on'", "another: 'Another explanation to test'",
        "always: 'Always tested on data: chance, measurement error, how the cases were chosen.'", "version: 'Version'", "startWith: k => 'Start analysis with version ' + k", "view: 'View'",
        "memory: 'Found in your saved analyses', memoryNote: 'For you to read. The Analyst gets only what you build on.'", "['comparison', 'What is compared'], ['measure', 'Measured by'], ['period', 'Period']",
        "opened: 'READ'", "question: 'QUESTION', updated: 'updated'"].every(s => js('architect.js').includes(s)));
  const engine = f => fs.readFileSync(path.join(root, '..', 'analyst', f), 'utf8'), own = js('architect.js');
  check('the saved analyses: the page knows a skipped reading by the reader\'s own sentence; the dialog of a saved analysis lies over the page, the row\'s Skip is styled in pane.css and View in tabs.css; '
    + 'the version in use is read as the engine keeps it (`at`), and the send carries the version on screen to the server, which hands it to the analysis',
    engine('reader.py').includes('\nSKIPPED = "The person skipped it."\n') && own.includes("const SKIPPED = 'The person skipped it.';") && !own.includes('READINGS')
    && css('dialogs.css').includes('#savedAnalysisModal { display: none; position: fixed; inset: 0;') && own.includes("modal.id = 'savedAnalysisModal'; modal.className = 'ui-modal-plain';")
    && paneCss.includes('#streamOutput .sp-row .ar-skip {') && tabsCss.includes('#content-brief .ar-open {')
    && /^def use\(framing: dict, n\) -> dict:/m.test(engine('brief.py')) && engine('brief.py').includes('at = (framing or {}).get("at")') && own.includes('const n = latestN(framing), at = framing && framing.at;')
    && qp.includes('if (framed && version) requestBody.version = version;') && qp.includes('const { synthesis, image, typed, framed, next, version } = options;')
    && fs.readFileSync(path.join(root, 'app.py'), 'utf8').includes("version = request.json.get('version')")
    && fs.readFileSync(path.join(root, 'app.py'), 'utf8').includes('version=version if isinstance(version, int) and not isinstance(version, bool) else None,')
    && fs.readFileSync(path.join(root, 'architect_routes.py'), 'utf8').includes("framing = instance.architect_say(data['thread_id'], data['chain_id'], text, version=version)"));
  const kindsPy = /\nKINDS = \{([^}]*)\}/.exec(engine('brief.py'))[1].match(/"(\w+)":/g).map(k => k.slice(1, -2));
  check('the stylesheet and the words, 0310: the panels of the figures are styled in tabs.css - side by side in equal columns while there is room, a drawn draft across the whole row, the tag - in the '
    + 'kernel\'s sand where the numbers are made up -, the cross in view, the key, the sketch grey and dashed, no wider than a sketch needs and hidden under a drawn draft; what a saved analysis '
    + 'drew under its line. The page sketches every kind the engine lets the Architect name. Nothing is left of the points a model wrote - in the engine, on the page or in the stylesheet. The '
    + 'words for a draft are plain ones. The page reads what the engine keeps - the keys beside a version, the drafts by key, the draft\'s turn - and what the host sends and serves',
    ['.ar-figs { display: grid; grid-template-columns: repeat(auto-fill, minmax(250px, 1fr));', '.ar-fig {', '.ar-fig.changed::before {', '.ar-fig .hd .tag {', '.ar-fig .hd .tag.mu {', '.ar-fig.drawn { grid-column: 1 / -1;',
     '.ar-fig.drawn > .key, #content-brief .ar-fig.drawn > svg { display: none; }', '.ar-fig .plot {', '.ar-fig .drop {', '.ar-fig .key i {', '.ar-fig .key i.sq {', '.ar-fig > svg .ax {', '.ar-fig > svg .bk {', '.ar-fig > svg .ph {',
     '.ar-fig > svg .dot {', '.ar-fig > svg .cell {', '.ar-fig .cap {', '.ar-fig .cap .mu {', '.ar-was:empty { display: none; }', '.ar-was img { display: block; width: 100%; max-width: 460px; height: auto;', '.ar-was .cap {', '.ar-fig .plot { min-height: 280px;'].every(s => tabsCss.includes('#content-brief ' + s))
    && !/\.ar-fig[^{]*\.(ln|pt|s\d)\b/.test(tabsCss) && !tabsCss.includes('var(--s)') && /\.ar-fig \.key i \{[^}]*border-top: 2px dashed var\(--text-tertiary\);/.test(tabsCss)
    && /\.ar-fig > svg \{[^}]*max-width: 380px;/.test(tabsCss) && /\.ar-fig > svg \.ph \{[^}]*stroke: var\(--text-tertiary\);[^}]*stroke-dasharray: 6 5;/.test(tabsCss) && !/\.ar-fig \.drop \{[^}]*opacity: 0;/.test(tabsCss)
    && /\.ar-fig \.hd \.tag\.mu \{[^}]*color: var\(--c-kernel\);/.test(tabsCss) && /\.ar-fig \.cap \.mu \{ color: var\(--c-kernel\); \}/.test(tabsCss)
    && same(kindsPy, ['line', 'scatter', 'bar', 'histogram', 'box', 'heatmap', 'line3d']) && kindsPy.every(k => Object.keys(tally(kindOf(k))).some(m => !/\.(ax|bk)$/.test(m)))
    && engine('brief.py').includes('\nSERIES = 4 ') && !/POINTS|_points/.test(engine('brief.py')) && !/\bplaced\b|\bDRAWN\b|\bFRONT\b|\bDEPTH\b|byData|\.sketched\b|sketched[(:]/.test(own) && own.includes("const NAMED = ['bar', 'box'];")
    && own.includes('const TRIES = 2;') && /\nTRIES = 2 /.test(engine('draft.py')) && !engine('architect.py').includes('sketched')
    && ["figures: 'What it will look like'", "figures: 'FIGURES', sketch: 'sketch', draft: 'draft', madeUp: 'made-up numbers', madeUpNote: 'The numbers are made up. The analysis puts in the real ones.',",
        "drawing: 'Drawing a draft…', noDraft: 'No draft could be drawn.', drawingRow: 'drawing a draft…', drawingHold: 'A draft of the figures is being drawn',", "drewThen: 'What it drew then'"].every(s => own.includes(s))
    && engine('draft.py').includes('turn = {"who": "draft", "drawn": [') && own.includes("t.who === 'draft' ? build.drafted(t, entry.chain_id)")
    && engine('draft.py').includes('"keys": [key(brief.get("question", ""), f) for f in brief["figures"]]') && own.includes('keys: v.keys || [], drafts: (framing && framing.drafts) || {}')
    && engine('draft.py').includes('COMPUTED, MADE_UP = "computed", "made up"') && own.includes("madeUp = drawn && d.basis !== 'computed'")
    && fs.readFileSync(path.join(root, '..', 'bambooai', 'bambooai.py'), 'utf8').includes("self._pane('architect_draft', framing=run.framing)") && own.includes("d.type === 'architect_draft' && d.framing")
    && fs.readFileSync(path.join(root, '..', 'bambooai', 'bambooai.py'), 'utf8').includes('label="Draft"') && own.includes('data-agent="Draft"')
    && fs.readFileSync(path.join(root, 'architect_routes.py'), 'utf8').includes("@architect_bp.route('/architect/draft/<thread_id>/<run_id>/<key>', methods=['GET'])")
    && own.includes("'/architect/draft/' + at.concat(el.getAttribute('data-key')).map(encodeURIComponent).join('/')")
    && fs.readFileSync(path.join(root, 'app.py'), 'utf8').includes("@app.route('/get_chain_preview/<thread_id>/<chain_id>', methods=['GET'])") && own.includes("'/get_chain_preview/' + [el.getAttribute('data-thread'), el.getAttribute('data-run')]")
    && own.includes("else if (act === 'unfigure') keptFirst(root, hit.getAttribute('data-path'), null, unfigure);") && /window\.ArchitectUI = \{[^}]*\bunfigure\b[^}]*\bdraftLayout\b/.test(own));
  finish();
})().catch(e => { check('the module ran without throwing', false, e && e.stack); finish(); });

function finish() {
  let fails = 0; for (const [n, ok, d] of results) { console.log((ok ? '  ok   ' : '  FAIL ') + n + (ok ? '' : '  <- ' + (typeof d === 'string' ? d : JSON.stringify(d) || '').slice(0, 900))); if (!ok) fails++; }
  console.log(`\n${results.length - fails} passed, ${fails} failed`); process.exit(fails ? 1 : 0);
}
