// The Architect on the page (docs/ARCHITECT_DESIGN.md §2.6, §2.8, §2.9, §2.11; 2026-11-15): architect.js. Its pure parts -
// the brief with one line changed, the Brief tab's markup in each state, the report's part "Against the brief" made a card,
// the thread map's mark - and the module driven on the mini DOM with a scripted server: a typed question opens its brief,
// a line is changed where it stands and kept as a version, the versions are stepped through, the analysis is started in
// the same chain, the composer is held while a brief not yet run is on screen. Then the page's hooks, read from the source.
// Run: node tests/analyst/test_architect.js
'use strict';
const fs = require('fs'), path = require('path');
const { makeDocument } = require(path.join(__dirname, 'minidom.js'));
const doc = makeDocument(); global.document = doc;
const calls = []; let answers = {};
global.window = { authService: { fetch: async (url, opts) => { const body = JSON.parse(opts.body); calls.push([url, body]);
  const a = typeof answers[url] === 'function' ? answers[url](body) : answers[url];
  if (a === 'down') throw new Error('offline');
  const [status, json] = a || [200, {}]; return { ok: status < 400, status, json: async () => json }; } } };
const store = {}; global.sessionStorage = { getItem: k => (k in store ? store[k] : null), setItem: (k, v) => { store[k] = String(v); } };
const toasts = []; global.showSystemMessage = t => toasts.push(t);
const locks = []; global.composerLock = reason => { locks.push(['lock', reason]); doc.getElementById('submitQuery').disabled = true; };
global.composerUnlock = () => { locks.push(['unlock']); doc.getElementById('submitQuery').disabled = false; };
global.responses = []; global.currentResponseIndex = -1; global.currentData = {}; global.queryRunning = false;
const host = doc.createElement('div'); doc.body.appendChild(host);
host.innerHTML = '<button id="architectSwitch" class="ar-switch" aria-pressed="false"></button><textarea id="queryInput"></textarea><button id="submitQuery"></button>' +
  '<div id="streamOutput"></div><div id="tabContainer"></div><div id="contentOutput"></div>';
const $ = id => doc.getElementById(id);
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
check('what is fixed: a part set or cleared by its name; the last one cleared removes the group',
  same(A.apply(BASE, 'fixed.period', 'the first half').brief.fixed, { measure: 'x', period: 'the first half' }) && same(A.apply(BASE, 'fixed.period', 'the first half').changed, ['fixed.period'])
  && !('fixed' in A.apply(BASE, 'fixed.measure', '').brief) && A.apply(BASE, 'fixed.measure', ' x ') === null);

// ------------------------------------------------------------ the Brief tab
const F1 = { versions: [{ n: 1, by: 'person', changed: [], brief: { question: 'Is B above A?' } }] };
const t1 = el(b.brief(F1, { chain: 71, state: 'framing' })), root1 = t1.querySelector('.ar-brief');
check('an empty brief: the question as the title with its pencil; v1 "from your question", both arrows off; the parts in the brief\'s order',
  root1.querySelector('h1.ar-line.ar-q .tx').textContent === 'Is B above A?' && root1.querySelector('h1 .pen[data-ar="edit"]') && root1.querySelector('h1').getAttribute('data-path') === 'question'
  && root1.querySelector('.ar-ver .step b').textContent === 'v1' && root1.querySelector('.ar-ver .why').textContent === 'from your question'
  && root1.querySelectorAll('.ar-ver [data-ar="step"]').every(x => x.hasAttribute('disabled'))
  && root1.querySelectorAll('h3').map(h => h.textContent).join('|') === 'Decision|What you think|It rests on|You expect|Also check|Fixed before the run', t1.innerHTML);
check('an empty brief: every part reads "not said yet" and opens on a click; what is fixed reads "left to the Analyst"; the standing checks are one line marked "always", never changed; a rival is added under it; Start analysis at the foot',
  ['decision', 'thinks', 'rests_on.+', 'expects', 'would_change'].every(p => { const t = root1.querySelector('.ar-line[data-path="' + p + '"] .tx'); return t.textContent === 'not said yet' && t.className === 'tx open' && t.getAttribute('data-ar') === 'edit'
    && t.getAttribute('role') === 'button' && t.getAttribute('tabindex') === '0'; })
  && root1.querySelector('.ar-line[data-path="would_change"] .pre').textContent === 'You would change your mind if:'
  && ['comparison', 'measure', 'period'].every(p => root1.querySelector('.ar-grid .ar-line[data-path="fixed.' + p + '"] .tx').textContent === 'left to the Analyst')
  && root1.querySelectorAll('.ar-grid .k').map(k => k.textContent).join() === 'Compare,Measure,Period'
  && root1.querySelectorAll('.src').length === 1 && root1.querySelector('.src').textContent === 'always' && root1.querySelector('.src').parent.querySelector('.tx').textContent === 'Chance, measurement error, how the cases were chosen'
  && !root1.querySelector('.src').parent.getAttribute('data-path') && root1.querySelector('.ar-line.adds[data-path="also_check.+"] .tx.add').textContent === '+ Add'
  && root1.querySelector('.ar-foot .ui-btn.primary[data-ar="start"]').textContent === 'Start analysis', t1.innerHTML);
check('the tab carries what it needs to be stepped through later: the chain, the state, the version shown and every version',
  root1.getAttribute('data-chain') === '71' && root1.getAttribute('data-state') === 'framing' && root1.getAttribute('data-shown') === '1' && same(JSON.parse(root1.getAttribute('data-framing')), F1));
const FULL = Object.assign({}, BASE, { thinks: 'B is better', expects: 'B above A by 2', would_change: 'a gap under 1',
  rests_on: BASE.rests_on.concat([{ text: 'an earlier finding', source: 'result', mark: 'cannot be checked' }, { text: 'a proposal', source: 'architect', mark: 'does not hold', note: 'A led in 7 of 12' }]),
  also_check: BASE.also_check.concat([{ text: 'luck' }]), saved: [{ when: '2026-02-20', question: 'Was B above A before?', passage: 'B led by 3.' }], set_aside: ['the weather'] });
const F3 = { versions: [F1.versions[0], { n: 2, by: 'person', changed: ['decision'], brief: { question: 'Is B above A?', decision: 'keep one arm' } }, { n: 3, by: 'person', changed: ['rests_on.0', 'fixed.measure', 'question'], brief: FULL }] };
const t3 = el(b.brief(F3, { chain: 71, state: 'framing' })), root3 = t3.querySelector('.ar-brief');
const lineOf = (r, p) => r.querySelector('.ar-line[data-path="' + p + '"]');
check('a filled brief shows its last version: "changed by you", the arrow back live; a line has its pencil and, in a list, its cross; the lines changed in this version carry the bar',
  root3.querySelector('.ar-ver .step b').textContent === 'v3' && root3.querySelector('.ar-ver .why').textContent === 'changed by you'
  && !root3.querySelector('.ar-ver [data-step="-1"]').hasAttribute('disabled') && root3.querySelector('.ar-ver [data-step="1"]').hasAttribute('disabled')
  && lineOf(root3, 'decision').querySelector('.tx').textContent === 'keep one arm' && !lineOf(root3, 'decision').querySelector('.tx').getAttribute('data-ar')
  && lineOf(root3, 'decision').querySelector('.pen[data-ar="edit"]') && !lineOf(root3, 'decision').querySelector('.drop')
  && lineOf(root3, 'rests_on.0').querySelector('.drop[data-ar="drop"]') && lineOf(root3, 'also_check.1').querySelector('.drop')
  && root3.querySelectorAll('.ar-line.changed').map(l => l.getAttribute('data-path')).join() === 'question,rests_on.0,fixed.measure', t3.innerHTML);
check('what a line rests on shows: its mark and the fact beside it (red when it does not hold), who brought it in when it was not the coach; a fact from a lookup has no pencil, only the cross',
  lineOf(root3, 'rests_on.0').querySelector('.mk.ok').textContent === '✓' && lineOf(root3, 'rests_on.0').querySelector('.fact').textContent === 'seen in 9 of 12' && !lineOf(root3, 'rests_on.0').querySelector('.src')
  && lineOf(root3, 'rests_on.1').querySelector('.src').textContent === 'data' && !lineOf(root3, 'rests_on.1').querySelector('.pen') && lineOf(root3, 'rests_on.1').querySelector('.drop')
  && lineOf(root3, 'rests_on.2').querySelector('.mk.q').textContent === '?' && lineOf(root3, 'rests_on.2').querySelector('.src').textContent === 'last result' && lineOf(root3, 'rests_on.2').querySelector('.pen')
  && lineOf(root3, 'rests_on.3').querySelector('.mk.no').textContent === '✕' && lineOf(root3, 'rests_on.3').querySelector('.fact.no').textContent === 'A led in 7 of 12' && lineOf(root3, 'rests_on.3').querySelector('.src.ar').textContent === 'Architect'
  && lineOf(root3, 'also_check.0').querySelector('.fact').textContent === 'a gap in one half only', t3.innerHTML);
check('the lists at the design\'s counts take no more lines; a saved analysis and what was set aside are shown as they are, without pencils',
  !lineOf(root3, 'rests_on.+') && !lineOf(root3, 'also_check.+')
  && root3.querySelectorAll('h3').map(h => h.textContent).slice(-2).join('|') === 'From saved analyses|Set aside'
  && root3.querySelector('.src.mem').textContent === 'saved analysis' && root3.querySelector('.src.mem').parent.querySelector('.tx').textContent === '2026-02-20 · Was B above A before?B led by 3.'
  && root3.elements.slice(-2)[0].textContent === 'the weather' && !root3.elements.slice(-2)[0].querySelector('[data-ar]'), t3.innerHTML);
const old = el(b.brief(F3, { chain: 71, state: 'framing', shown: 2 })).querySelector('.ar-brief');
const ran = el(b.brief(F3, { chain: 71, state: 'run' })).querySelector('.ar-brief');
check('an older version is read, not changed: no pencil, no cross, no Start analysis, what it did not say reads "not said"; both arrows live',
  old.querySelector('.ar-ver .step b').textContent === 'v2' && old.getAttribute('data-shown') === '2' && old.querySelectorAll('[data-ar]').map(x => x.getAttribute('data-ar')).join() === 'step,step'
  && !old.querySelectorAll('[data-ar="step"]').some(x => x.hasAttribute('disabled')) && lineOf(old, 'thinks').querySelector('.tx').textContent === 'not said'
  && lineOf(old, 'decision').className === 'ar-line changed' && !old.querySelector('.ar-foot'), old.outerHTML);
check('the brief of a run that has started is read, not changed, at its last version; its versions can still be stepped through',
  ran.getAttribute('data-state') === 'run' && ran.querySelector('.ar-ver .step b').textContent === 'v3' && ran.querySelectorAll('[data-ar]').map(x => x.getAttribute('data-ar')).join() === 'step,step'
  && !ran.querySelector('.ar-foot') && lineOf(ran, 'fixed.period').querySelector('.tx').textContent === 'left to the Analyst');
check('the first version of a follow-up says where it came from; a version of the Architect\'s says so',
  el(b.brief({ versions: [{ n: 1, by: 'person', changed: ['from the last brief'], brief: FULL }] }, { chain: 1, state: 'framing' })).querySelector('.why').textContent === 'from the last brief'
  && el(b.brief({ versions: [F1.versions[0], { n: 2, by: 'architect', changed: [], brief: FULL }] }, { chain: 1, state: 'framing' })).querySelector('.why').textContent === 'changed by the Architect');
const NASTY = { versions: [{ n: 1, by: 'person', changed: [], brief: { question: 'Is "B" <b>above</b> A & C?', decision: '<script>alert(1)</script>', thinks: 'x &lt; y &amp; z' } }] };
const tn = el(b.brief(NASTY, { chain: 9, state: 'framing' })).querySelector('.ar-brief');
check('what the coach typed is shown as text, never as markup, and the versions survive the trip through the tab\'s own markup',
  tn.querySelector('h1 .tx').textContent === 'Is "B" <b>above</b> A & C?' && !tn.querySelector('h1 b') && !tn.querySelector('script')
  && lineOf(tn, 'decision').querySelector('.tx').textContent === '<script>alert(1)</script>' && lineOf(tn, 'thinks').querySelector('.tx').textContent === 'x &lt; y &amp; z'
  && same(JSON.parse(tn.getAttribute('data-framing')), NASTY), tn.outerHTML);
const ENTRY = { status: 'framing', chain_id: 71, thread_id: 7, queryText: 'Is B <above> A?', framing: F3 };
const pane = el(b.pane(ENTRY)), fold = el(b.fold(ENTRY)), ed = el(b.editor('a "line" & more'));
check('the left pane of a brief not yet run: the strip says Architect and which version stands, idle; the question as the coach\'s card',
  pane.querySelector('.sp-strip .live.idle') && pane.querySelector('.sp-strip .mode').textContent === 'Architect' && pane.querySelector('.sp-strip').textContent === 'Architectbrief v3'
  && pane.querySelector('.sp-stream .ar-msg.you .who').textContent === 'You' && pane.querySelector('.sp-stream .ar-msg.you').textContent === 'YouIs B <above> A?', pane.innerHTML);
check('once the analysis starts the framing is one folded row above the run: Architect, the version, the question; the coach\'s card inside',
  fold.querySelector('details.sp-turn.ar-fold') && !fold.querySelector('details').hasAttribute('open') && fold.querySelector('summary .n').textContent === 'Architect' && fold.querySelector('summary .kind').textContent === 'brief v3'
  && fold.querySelector('summary .peek').textContent === 'Is B <above> A?' && fold.querySelector('.sp-detail .ar-msg.you').textContent === 'YouIs B <above> A?', fold.innerHTML);
check('the line being typed: a field holding the text, bounded as a line of the brief is - as the question is, for the question - then Keep and Cancel',
  ed.querySelector('.ar-edit textarea.ar-input').textContent === 'a "line" & more' && ed.querySelector('textarea').getAttribute('maxlength') === '600'
  && el(b.editor('q', true)).querySelector('textarea').getAttribute('maxlength') === '4000'
  && ed.querySelectorAll('[data-ar]').map(x => x.getAttribute('data-ar') + ':' + x.getAttribute('title')).join() === 'keep:Keep,cancel:Cancel', ed.innerHTML);

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
  A.open('Is B above A?'); await tick();
  const entry = responses[1];
  check('a question typed with the switch on: the server is asked to open its brief with the question and the chain on screen; the brief is a chain of its own, where the question was asked, and the page moves to it',
    same(calls[0], ['/architect/open', { question: 'Is B above A?', thread_id: 7, chain_id: 70 }]) && responses.length === 2 && currentResponseIndex === 1
    && entry.status === 'framing' && entry.chain_id === 71 && entry.thread_id === 7 && entry.parentChainId === 70 && entry.queryText === 'Is B above A?' && same(entry.framing, F1)
    && currentData.chain_id === 71 && $('queryInput').value === '', [calls[0], entry]);
  check('the brief on screen: the left pane says Architect, brief v1, with the question; one tab, Brief, drawn from the versions and open to changes',
    $('streamOutput').querySelector('.sp-strip').textContent === 'Architectbrief v1' && $('streamOutput').querySelector('.ar-msg.you').textContent === 'YouIs B above A?'
    && $('tabContainer').querySelectorAll('.tab').length === 1 && $('tabContainer').querySelector('#tab-brief.tab.active').textContent === 'Brief'
    && $('contentOutput').querySelector('#content-brief.tab-content.active .ar-brief').getAttribute('data-state') === 'framing' && $('contentOutput').querySelector('[data-ar="start"]'), $('contentOutput').innerHTML);
  check('while the brief is on screen the composer is held, and says why; the page marks the state', same(locks[locks.length - 1], ['lock', 'Fill the brief, then Start analysis']) && doc.body.classList.contains('ar-framing')
    && A.framingInView() === true);
  answers['/architect/open'] = [500, { error: 'The brief could not be opened: disk' }];
  A.open('Another question'); await tick();
  answers['/architect/open'] = 'down';
  A.open('Another question'); await tick();
  check('a brief the server did not open: the reason is said, no chain is made', responses.length === 2 && toasts.slice(-2).join('|') === 'The brief could not be opened: disk|The brief could not be opened: the server could not be reached.', toasts);

  // a line is changed where it stands
  const brief = () => $('contentOutput').querySelector('.ar-brief');
  const serve = () => { answers['/architect/brief'] = body => { const f = JSON.parse(JSON.stringify(entry.framing)); f.versions.push({ n: f.versions.length + 1, by: 'person', changed: body.changed, brief: body.brief }); return [200, { framing: f }]; }; };
  serve();
  doc.dispatch('click', lineOf(brief(), 'decision').querySelector('.tx'));
  let field = lineOf(brief(), 'decision').querySelector('textarea.ar-input');
  check('a click on a part not said yet: the field opens in its line, empty, with Keep and Cancel', field && field.textContent === '' && lineOf(brief(), 'decision').classList.contains('editing')
    && lineOf(brief(), 'decision').querySelectorAll('[data-ar]').map(x => x.getAttribute('data-ar')).join() === 'keep,cancel', lineOf(brief(), 'decision').outerHTML);
  field.value = '  keep one   arm ';
  doc.dispatch('click', lineOf(brief(), 'decision').querySelector('[data-ar="keep"]')); await tick();
  check('Keep: the server is sent the brief as it would stand and the part changed; it answers with one more version',
    same(calls[calls.length - 1], ['/architect/brief', { thread_id: 7, chain_id: 71, brief: { question: 'Is B above A?', decision: 'keep one arm' }, changed: ['decision'] }]) && entry.framing.versions.length === 2, calls[calls.length - 1]);
  check('the tab shows the new version: v2, changed by you, the changed line marked and no longer being typed; the pane\'s strip follows',
    brief().querySelector('.ar-ver .step b').textContent === 'v2' && brief().querySelector('.why').textContent === 'changed by you' && lineOf(brief(), 'decision').className === 'ar-line changed'
    && lineOf(brief(), 'decision').querySelector('.tx').textContent === 'keep one arm' && $('streamOutput').querySelector('.sp-strip').textContent === 'Architectbrief v2', brief().outerHTML);
  let n = calls.length;
  doc.dispatch('click', lineOf(brief(), 'decision').querySelector('.pen'));
  field = lineOf(brief(), 'decision').querySelector('.ar-input');
  const prefilled = field.textContent;
  field.value = 'keep one arm';
  doc.dispatch('keydown', field, { key: 'Enter' }); await tick();
  check('the pencil opens the line with its text; kept unchanged, nothing is sent and no version is made', prefilled === 'keep one arm' && calls.length === n && entry.framing.versions.length === 2 && !brief().querySelector('.editing'));
  const other = doc.dispatch('keydown', lineOf(brief(), 'thinks').querySelector('.tx'), { key: 'a' });
  const opened = doc.dispatch('keydown', lineOf(brief(), 'thinks').querySelector('.tx'), { key: 'Enter' });
  field = lineOf(brief(), 'thinks').querySelector('.ar-input'); field.value = 'B is better';
  const esc = doc.dispatch('keydown', field, { key: 'Escape' }); await tick();
  check('a part not said yet opens from the keyboard too (Enter on it, no other key); Escape leaves the line as it was: nothing sent',
    !other.defaulted && opened.defaulted === true && calls.length === n && esc.defaulted === true && !brief().querySelector('.editing') && lineOf(brief(), 'thinks').querySelector('.tx').textContent === 'not said yet');
  doc.dispatch('click', lineOf(brief(), 'would_change').querySelector('.tx'));
  field = lineOf(brief(), 'would_change').querySelector('.ar-input'); field.value = 'a gap under 1';
  const stillLabelled = lineOf(brief(), 'would_change').querySelector('.pre').textContent === 'You would change your mind if:';
  const composing = doc.dispatch('keydown', field, { key: 'Enter', isComposing: true }); await tick();
  const shifted = doc.dispatch('keydown', field, { key: 'Enter', shiftKey: true }); await tick();
  const whileComposing = calls.length;
  const enter = doc.dispatch('keydown', field, { key: 'Enter' }); await tick();
  check('Enter keeps the line (not while a character is still being composed, and Shift+Enter is a new line); the line keeps its lead-in while it is typed',
    stillLabelled && whileComposing === n && !composing.defaulted && !shifted.defaulted && enter.defaulted === true && calls.length === n + 1 && same(calls[n][1].changed, ['would_change'])
    && lineOf(brief(), 'would_change').querySelector('.tx').textContent === 'a gap under 1' && entry.framing.versions.length === 3, calls[n]);

  // lines of a list; another line clicked while one is being typed
  doc.dispatch('click', lineOf(brief(), 'rests_on.+').querySelector('.tx'));
  lineOf(brief(), 'rests_on.+').querySelector('.ar-input').value = 'B looked better';
  doc.dispatch('click', lineOf(brief(), 'also_check.+').querySelector('.tx')); await tick();
  check('another line clicked while one is being typed: the first is kept - a line of the coach\'s own on the list - and the second opens in the brief as it then stands',
    same(calls[calls.length - 1][1].brief.rests_on, [{ text: 'B looked better', source: 'person', mark: '' }]) && same(calls[calls.length - 1][1].changed, ['rests_on.0'])
    && lineOf(brief(), 'rests_on.0').className === 'ar-line changed' && lineOf(brief(), 'also_check.+').classList.contains('editing') && brief().querySelectorAll('.editing').length === 1, brief().outerHTML);
  lineOf(brief(), 'also_check.+').querySelector('.ar-input').value = 'luck';
  doc.dispatch('click', lineOf(brief(), 'also_check.+').querySelector('[data-ar="keep"]')); await tick();
  doc.dispatch('click', lineOf(brief(), 'rests_on.+').querySelector('.tx'));
  lineOf(brief(), 'rests_on.+').querySelector('.ar-input').value = 'a second thing';
  doc.dispatch('keydown', lineOf(brief(), 'rests_on.+').querySelector('.ar-input'), { key: 'Enter' }); await tick();
  check('the lists grow a line at a time, each under the last', same(entry.framing.versions[entry.framing.versions.length - 1].brief.rests_on.map(a => a.text), ['B looked better', 'a second thing'])
    && same(entry.framing.versions[entry.framing.versions.length - 1].brief.also_check, [{ text: 'luck' }]) && lineOf(brief(), 'rests_on.+').querySelector('.tx.add'));
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
    && !lineOf(brief(), 'also_check.0') && lineOf(brief(), 'also_check.+'));
  // a cross clicked while another line is being typed: the typed line is not lost
  doc.dispatch('click', lineOf(brief(), 'also_check.+').querySelector('.tx'));
  lineOf(brief(), 'also_check.+').querySelector('.ar-input').value = 'the season';
  n = calls.length;
  doc.dispatch('click', lineOf(brief(), 'rests_on.0').querySelector('.drop')); await tick();
  check('a cross clicked while another line is being typed: the typed line is kept first, then the other is left out - two versions, nothing lost',
    calls.length === n + 2 && same(calls[n][1].changed, ['also_check.0']) && same(calls[n][1].brief.also_check, [{ text: 'the season' }]) && calls[n][1].brief.rests_on.length === 1
    && same(calls[n + 1][1].changed, ['rests_on']) && !('rests_on' in calls[n + 1][1].brief) && same(calls[n + 1][1].brief.also_check, [{ text: 'the season' }])
    && lineOf(brief(), 'also_check.0').querySelector('.tx').textContent === 'the season' && lineOf(brief(), 'rests_on.+').querySelector('.tx.open'), [calls[n], calls[n + 1]]);

  // the question
  doc.dispatch('click', brief().querySelector('h1 .pen'));
  const questionBound = brief().querySelector('h1 .ar-input').getAttribute('maxlength');
  brief().querySelector('h1 .ar-input').value = 'Is B above A, on x?';
  doc.dispatch('keydown', brief().querySelector('h1 .ar-input'), { key: 'Enter' }); await tick();
  check('the question is changed like any line, in a field with the question\'s own bound: the chain\'s own text follows, in the title, the pane and the map\'s label',
    questionBound === '4000' && calls[calls.length - 1][1].brief.question === 'Is B above A, on x?' && entry.queryText === 'Is B above A, on x?' && brief().querySelector('h1 .tx').textContent === 'Is B above A, on x?'
    && brief().querySelector('h1').className === 'ar-line ar-q changed' && $('streamOutput').querySelector('.ar-msg.you').textContent === 'YouIs B above A, on x?');

  // a change the server does not keep
  const versions = entry.framing.versions.length;
  answers['/architect/brief'] = [409, { error: 'This brief can no longer be changed: its analysis has started.' }];
  doc.dispatch('click', lineOf(brief(), 'thinks').querySelector('.tx'));
  lineOf(brief(), 'thinks').querySelector('.ar-input').value = 'B is better';
  doc.dispatch('keydown', lineOf(brief(), 'thinks').querySelector('.ar-input'), { key: 'Enter' }); await tick();
  const refused = toasts[toasts.length - 1] === 'This brief can no longer be changed: its analysis has started.' && lineOf(brief(), 'thinks').classList.contains('editing') && entry.framing.versions.length === versions;
  answers['/architect/brief'] = 'down';
  doc.dispatch('keydown', lineOf(brief(), 'thinks').querySelector('.ar-input'), { key: 'Enter' }); await tick();
  check('a change the server does not keep: the reason is said, the line stays open with what was typed, no version is made - also when the server cannot be reached',
    refused && toasts[toasts.length - 1] === 'The change was not kept: the server could not be reached.' && lineOf(brief(), 'thinks').classList.contains('editing') && entry.framing.versions.length === versions, toasts.slice(-2));
  serve();
  doc.dispatch('keydown', lineOf(brief(), 'thinks').querySelector('.ar-input'), { key: 'Enter' }); await tick();

  // the versions
  const last = entry.framing.versions.length;
  doc.dispatch('click', brief().querySelector('[data-step="-1"]'));
  const back = brief();
  check('the arrow back shows the version before, to read: no pencil, no Start analysis; nothing is sent', back.querySelector('.step b').textContent === 'v' + (last - 1) && !back.querySelector('.pen') && !back.querySelector('[data-ar="start"]')
    && back.getAttribute('data-shown') === String(last - 1));
  doc.dispatch('click', brief().querySelector('[data-step="1"]'));
  check('the arrow forward returns to the last version, open to changes again', brief().querySelector('.step b').textContent === 'v' + last && brief().querySelector('[data-ar="start"]') && lineOf(brief(), 'thinks').querySelector('.pen'));

  // leaving and coming back; the composer
  const lockCount = locks.length;
  currentResponseIndex = 0; loadResponseContent(responses[0]); updateNavigationButtons();
  check('another chain on screen: the composer is free again, the page\'s mark gone', same(locks[locks.length - 1], ['unlock']) && locks.length === lockCount + 1 && !doc.body.classList.contains('ar-framing') && A.framingInView() === false);
  updateNavigationButtons();
  check('the Architect lifts only its own hold: a second look at a plain chain touches nothing', locks.length === lockCount + 1);
  queryRunning = true;
  currentResponseIndex = 1; loadResponseContent(entry); updateNavigationButtons();
  check('back on the brief: drawn again from its versions, at the last one; the composer held - and with another chain running, its Stop stays within reach',
    brief().querySelector('.step b').textContent === 'v' + last && same(locks[locks.length - 1], ['lock', 'Fill the brief, then Start analysis']) && $('submitQuery').disabled === false);

  // Start analysis
  doc.dispatch('click', brief().querySelector('[data-ar="start"]')); await tick();
  check('Start analysis while another analysis runs: said in plain words, nothing started', submitted.length === 0 && toasts[toasts.length - 1] === 'Another analysis is running. Wait for it to end, or stop it.');
  queryRunning = false;
  doc.dispatch('click', lineOf(brief(), 'expects').querySelector('.tx'));
  lineOf(brief(), 'expects').querySelector('.ar-input').value = 'B above A by 2';
  doc.dispatch('click', brief().querySelector('[data-ar="start"]')); await tick();
  check('Start analysis with a line still being typed: the line is kept first, then the page\'s own send starts this chain',
    calls[calls.length - 1][1].brief.expects === 'B above A by 2' && submitted.length === 1 && submitted[0].framed === entry && Object.keys(submitted[0]).join() === 'framed'
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
    reverted[0] === entry && entry.status === 'framing' && brief().getAttribute('data-state') === 'framing' && brief().querySelector('[data-ar="start"]') && same(locks[locks.length - 1], ['lock', 'Fill the brief, then Start analysis'])
    && toasts[toasts.length - 1] === 'The analysis did not start: Network response was not ok');
  const quiet = toasts.length; A.notStarted(entry);
  check('refused for the balance, the page has its own dialog: nothing more is said', toasts.length === quiet);

  // a chain kept with its brief: the tab alone steps through the versions
  const done = { chain_id: 80, thread_id: 7, queryText: 'A framed question', tabContent: '<div id="tab-brief" class="tab active">Brief</div>',
                 contentOutput: '<div id="content-brief" class="tab-content active">' + b.brief(F3, { chain: 80, state: 'run' }) + '</div>', streamOutput: '' };
  responses.push(done); currentResponseIndex = 2; loadResponseContent(done); updateNavigationButtons();
  doc.dispatch('click', brief().querySelector('[data-step="-1"]'));
  doc.dispatch('click', brief().querySelector('[data-step="-1"]'));
  const first = brief().querySelector('.step b').textContent + '|' + brief().querySelector('.why').textContent + '|' + brief().querySelectorAll('.pen').length;
  doc.dispatch('click', brief().querySelector('[data-step="-1"]'));
  n = calls.length;
  doc.dispatch('click', brief().querySelector('h1'));
  check('a restored chain: its Brief tab steps through the versions from its own markup, down to the first and no further; nothing can be changed, nothing is sent',
    first === 'v1|from your question|0' && brief().querySelector('.step b').textContent === 'v1' && brief().getAttribute('data-state') === 'run' && calls.length === n && A.mark(done) === 'Architect', first);

  // ---- the page's hooks, from the source ----
  const root = path.join(__dirname, '..', '..', 'web_app'), js = f => fs.readFileSync(path.join(root, 'static', 'js', f), 'utf8'), css = f => fs.readFileSync(path.join(root, 'static', 'css', f), 'utf8');
  const html = fs.readFileSync(path.join(root, 'templates', 'index.html'), 'utf8'), qp = js('query-processing.js'), wm = js('workflow-management.js'), cr = js('content-rendering.js');
  check('index.html: the switch sits after the mode control, before the plant; architect.js is loaded after the modules it leans on; the app starts it',
    html.indexOf('id="architectSwitch"') > html.indexOf('id="modeParams"') && html.indexOf('id="architectSwitch"') < html.indexOf('id="suggestQuestions"')
    && /<button id="architectSwitch" type="button" class="ar-switch" aria-pressed="false" title="Architect: write a brief before the analysis runs">/.test(html)
    && html.indexOf('js/architect.js') > html.indexOf('js/code-map.js') && html.indexOf('js/architect.js') > html.indexOf('js/routines.js') && js('core.js').includes('window.ArchitectUI.initialize();'));
  check('the send: only the composer\'s own send is framed (the button, Ctrl+Enter); with a brief not yet run on screen nothing else starts; a brief\'s analysis names its run and where it attached',
    qp.includes("submitQueryButton.addEventListener('click', () => handleQuerySubmit({ typed: true }));") && js('ui-controls.js').includes('handleQuerySubmit({ typed: true });')
    && qp.includes('if (typed && window.ArchitectUI.isOn()) {') && qp.indexOf('window.ArchitectUI.framingInView()') < qp.indexOf('if (typed && window.ArchitectUI.isOn())')
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
  check('the stylesheets: the switch and the map\'s tag in shell.css, the coach\'s card in pane.css, the Brief tab and the answer\'s card in tabs.css; the plant is out of reach while a brief not yet run is on screen',
    shell.includes('.left-panel .icon-row .ar-switch.on {') && shell.includes('#workflowMapModal .wf-node-made {') && shell.includes('#workflowMapModal .wf-node--notrun {')
    && shell.includes('body.ar-framing .left-panel .icon-row .suggest-questions { opacity: .35; pointer-events: none; }')
    && paneCss.includes('#streamOutput .ar-msg {') && tabsCss.includes('#content-brief .ar-line.changed::before {') && tabsCss.includes('#content-brief .ar-foot { position: sticky;')
    && tabsCss.includes('#content-answer .ar-against {') && tabsCss.includes('#content-answer .ar-against .r { display: contents; }') && ['ok', 'no', 'q'].every(v => tabsCss.includes('#content-answer .ar-against .v.' + v + ' {')));
  finish();
})().catch(e => { check('the module ran without throwing', false, e && e.stack); finish(); });

function finish() {
  let fails = 0; for (const [n, ok, d] of results) { console.log((ok ? '  ok   ' : '  FAIL ') + n + (ok ? '' : '  <- ' + (typeof d === 'string' ? d : JSON.stringify(d) || '').slice(0, 900))); if (!ok) fails++; }
  console.log(`\n${results.length - fails} passed, ${fails} failed`); process.exit(fails ? 1 : 0);
}
