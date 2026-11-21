// Next questions on the page (docs/ARCHITECT_DESIGN.md §2.7, §2.9, §2.15, §2.24; 2026-11-16, the panel 2026-11-19):
// next-questions.js. Its pure parts - the button, the panel's list of five ways, a set of questions as rows, the row a
// run opens on - and the module driven on the mini DOM with a scripted server: the button on a finished analysis'
// closing card, the panel it opens in the card, a way picked, the set that comes back in the list's place and kept
// with the chain, the list again, more of one way, a question changed and run, its row marked once its analysis is
// on, the Workflow map's mark. Then the page's hooks, read from the source.
// Run: node tests/analyst/test_next_questions.js
'use strict';
const fs = require('fs'), path = require('path');
const { makeDocument } = require(path.join(__dirname, 'minidom.js'));
const doc = makeDocument(); global.document = doc;
const calls = []; let answer = null;
// the scripted server: an answer is [status, body] - the body an object, or the text of a stream - 'down', or a promise of one
global.window = { authService: { fetch: async (url, opts) => { const body = JSON.parse(opts.body); calls.push([url, body]);
  const a = await (typeof answer === 'function' ? answer(body) : answer);
  if (a === 'down') throw new Error('offline');
  const [status, json] = a || [200, {}];
  return { ok: status < 400, status, json: async () => json, text: async () => (typeof json === 'string' ? json : JSON.stringify(json)) }; } } };
const store = {}; global.sessionStorage = { getItem: k => (k in store ? store[k] : null), setItem: (k, v) => { store[k] = String(v); } };
const toasts = []; global.showSystemMessage = t => toasts.push(t);
const stored = []; global.localforage = { setItem: (k, v) => { stored.push([k, v.length]); return Promise.resolve(); } };
global.responses = []; global.currentResponseIndex = -1; global.currentData = {}; global.queryRunning = false; global.liveState = { running: false, index: null };
const host = doc.createElement('div'); doc.body.appendChild(host);
host.innerHTML = '<textarea id="queryInput"></textarea><button id="submitQuery"></button><div id="streamOutput"></div><div id="tabContainer"></div><div id="contentOutput"></div>';
const $ = id => doc.getElementById(id);
const submitted = []; global.handleQuerySubmit = o => submitted.push(o);
const rows = []; global.paneAppend = html => rows.push(html);
const went = []; global.navigateToChainId = c => went.push(c);

require(path.join(__dirname, '..', '..', 'web_app', 'static', 'js', 'next-questions.js'));
require(path.join(__dirname, '..', '..', 'web_app', 'static', 'js', 'architect.js'));
const N = window.NextQuestionsUI, b = N.build;
const results = []; const check = (n, c, d) => results.push([n, !!c, d]);
const el = html => { const d = doc.createElement('div'); d.innerHTML = html; return d; };
const tick = async () => { for (let i = 0; i < 6; i++) await new Promise(r => setImmediate(r)); };
const same = (x, y) => JSON.stringify(x) === JSON.stringify(y);
const text = (root, sel) => root.querySelectorAll(sel).map(e => e.textContent);

// ------------------------------------------------------------ the builders
const MISFIT = { kind: 'misfit', text: 'The gap is twice as wide in the "second" half [cell 3]' };
const SET = { level: 'emergence', cost: 0.0213, chain: 1700000077, questions: [
  { title: 'The second half:', text: 'Is the gap <wider> in the second half?', from: [MISFIT] },
  { title: '', text: 'Does the gap hold with the two rows left out?', from: [{ kind: 'found', text: 'B is above A.' }, { kind: 'earlier', text: 'Twelve rows.' }] },
  { title: 'Unknown', text: 'From a line of a kind the page has no word for?', from: [{ kind: 'other', text: 'x' }], ran: '1700000099' }] };
const button = el(b.button()), levels = el(b.levels({ test: 4, blend: 1 }, '')), writing = el(b.levels({ test: 4 }, 'shift'));
const SAID = [['refine', 'Refine focus', 'Stay with the same question and look closer: a smaller group, a shorter period, a stricter measure.'],
              ['shift', 'Shift angle', 'Ask whether something else explains the result, and put that to the test.'],
              ['test', 'Test boundaries', 'Check what the result stands on, and find where it stops being true.'],
              ['blend', 'Blend elements', 'Bring two findings together in one question, such as this result and an earlier one.'],
              ['emergence', 'Follow emergence', 'Go after what did not fit: the things this analysis could not explain.']];
check('the button of a closing card: a button like the others in the card\'s row of what can be done next (0313: it had a row of its own under the links), the plant and its two words, a plain title. '
  + 'The five ways to go (0314: a list that dropped over the card, a name and three words each): a row each, in the design\'s order - its key, its name, and what its questions do in a sentence; a way '
  + 'that has questions says how many, one or several; while a set is written its row says so in the arrow\'s place, and the others stand back',
  button.elements.length === 1 && button.elements[0].tag === 'button' && button.elements[0].className === 'sp-act sp-next' && !button.querySelector('.nq-open')
  && button.querySelector('.sp-next[data-nq="open"]').textContent === 'Next questions' && button.querySelector('.sp-next svg') && button.querySelector('.sp-next').getAttribute('type') === 'button'
  && button.querySelector('.sp-next').getAttribute('title') === 'Questions that could follow this analysis' && typeof b.menu === 'undefined'
  && same(levels.querySelectorAll('button.nq-row[data-nq="level"]').map(i => [i.getAttribute('data-level'), i.querySelector('b').textContent, i.querySelector('span').textContent]), SAID)
  && same(levels.querySelectorAll('.nq-row').map(i => i.className + ':' + i.elements.slice(2).map(e => e.tag + '.' + e.className + '=' + e.textContent).join()),
          ['nq-row:i.=›', 'nq-row:i.=›', 'nq-row:em.n=4 questions,i.=›', 'nq-row:em.n=1 question,i.=›', 'nq-row:i.=›'])
  && same(writing.querySelectorAll('.nq-row').map(i => i.className + ':' + i.elements.slice(2).map(e => e.tag + '.' + e.className + '=' + e.textContent).join()),
          ['nq-row dim:i.=›', 'nq-row on:em.live=writing the questions…', 'nq-row dim:em.n=4 questions,i.=›', 'nq-row dim:i.=›', 'nq-row dim:i.=›'])
  && el(b.levels()).querySelectorAll('.nq-row .n').length === 0, levels.innerHTML);
const panel0 = el(b.panel()).elements[0], topList = el(b.top('list', { test: 4 }, '')), topWay = el(b.top('test', { test: 4 }, ''));
check('the panel (0314): empty, it has a place for what stands over its sets, for the sets, and for what stands under them, and shows the list. Over the sets, the list: a heading that asks where to go, '
  + 'the cross that shuts the panel, one line that says what the questions are, and the five rows. Or the questions of one way: the way back to all five, the cross, and that way\'s name and sentence. '
  + 'Under the questions of one way: more of them, on request - and while they are written the button says so and cannot be pressed; under the list, nothing',
  panel0.className === 'nq-panel' && panel0.getAttribute('data-show') === 'list' && same(panel0.elements.map(e => e.className), ['nq-top', 'nq-sets', 'nq-end'])
  && same(topList.elements.map(e => e.className), ['nq-ph', 'nq-what', 'nq-row', 'nq-row', 'nq-row', 'nq-row', 'nq-row']) && topList.querySelector('.nq-ph .t').textContent === 'Where do you want to go from here?'
  && same(['class', 'data-nq', 'title'].map(a => topList.querySelector('.nq-ph button').getAttribute(a)), ['nq-x', 'shut', 'Close'])
  && topList.querySelector('.nq-what').textContent === 'Up to five questions that could follow this analysis. Each one starts from something it found, took for granted or left open. You can change a question before you run it.'
  && same(topWay.elements.map(e => e.className), ['nq-ph', 'nq-lv']) && same(topWay.querySelectorAll('.nq-ph button').map(x => x.getAttribute('data-nq') + '=' + x.textContent), ['list=‹ All five', 'shut=×'])
  && topWay.querySelector('.nq-lv b').textContent === 'Test boundaries' && topWay.querySelector('.nq-lv span').textContent === SAID[2][2] && !topWay.querySelector('.nq-row')
  && el(b.top('deeper', {}, '')).querySelector('.nq-lv b').textContent === 'deeper'
  && b.end('list', '') === '' && same(['class', 'data-nq', 'data-level', 'title', 'disabled'].map(a => el(b.end('test', '')).elements[0].getAttribute(a)), ['nq-more', 'more', 'test', 'More questions of this kind', null])
  && el(b.end('test', '')).textContent === 'Write more' && el(b.end('test', 'test')).textContent === 'writing the questions…' && el(b.end('test', 'test')).elements[0].hasAttribute('disabled'), [topList.innerHTML, topWay.innerHTML]);
const set = el(b.set(SET, 2)).querySelector('.nq-set'), cards = set.querySelectorAll('.nq-card');
check('a set: its place and its way ride in its markup; it has no head of its own (0314: the panel says which way is shown); under its questions a line says how many there are and what the call '
  + 'cost, with the button to the prompt the Pathfinder received - its own chain on the run log, the first call there',
  set.getAttribute('data-set') === '2' && set.getAttribute('data-level') === 'emergence' && !set.querySelector('.nq-head') && same(set.elements.map(e => e.className.split(' ')[0]), ['nq-card', 'nq-card', 'nq-card', 'nq-foot'])
  && set.querySelector('.nq-foot span').textContent === '3 questions · $0.02' && set.querySelector('.nq-foot').textContent === '3 questions · $0.02⌘'
  && same(['class', 'data-agent', 'data-chain', 'data-call'].map(a => set.querySelector('.nq-foot .sp-prompt').getAttribute(a)), ['agent-instructions-btn sp-prompt', 'Pathfinder', '1700000077', '1'])
  && cards.length === 3 && same(cards.map(c => c.getAttribute('data-k')), ['0', '1', '2']), set.querySelector('.nq-foot').outerHTML);
const cheap = el(b.set({ level: 'test', cost: 0.004, questions: [{ text: 'One?' }] }, 0));
check('a set whose call cost under half a cent shows no cost; one without a chain on record has no button to a prompt; one question is one question',
  cheap.querySelector('.nq-foot').textContent === '1 question' && !cheap.querySelector('.sp-prompt')
  && el(b.set({ level: 'test', cost: 0.005, questions: [] }, 0)).querySelector('.nq-foot').textContent === '0 questions · $0.01', cheap.innerHTML);
check('a question, a row: what it starts from in the page\'s words - the lines themselves as the label\'s title, two kinds joined - its title in bold, without a full stop (0314: it stands in a '
  + 'column of its own), its text, a pencil and an arrow; what a model wrote is text, never markup; a question without a title has none; a kind the page has no word for gives no label',
  cards[0].querySelector('.from .l').textContent === 'From what did not fit' && cards[0].querySelector('.from').getAttribute('title') === MISFIT.text
  && cards[0].querySelector('.tx b').textContent === 'The second half' && cards[0].querySelector('.tx .q').textContent === 'Is the gap <wider> in the second half?' && !cards[0].querySelector('.q wider')
  && same(cards[0].querySelectorAll('.tools button').map(x => [x.className, x.getAttribute('data-nq'), x.getAttribute('title')]), [['pen', 'edit', 'Change'], ['go', 'run', 'Start the analysis']])
  && cards[1].querySelector('.from .l').textContent === 'From the answer and an earlier answer' && cards[1].querySelector('.from').getAttribute('title') === 'B is above A.\nTwelve rows.' && !cards[1].querySelector('.tx b')
  && cards[2].querySelector('.from .l').textContent === '' && el(b.from(null)).querySelector('.l').textContent === ''
  && same(['anchor', 'check', 'misfit', 'would_change', 'proposal', 'comparison'].map(k => el(b.from([{ kind: k, text: 't' }])).querySelector('.l').textContent),
          ['From what it rests on', 'From what was also checked', 'From what did not fit', 'From what would change your mind', 'From a proposal not ticked', 'From what was compared']), cards[0].outerHTML);
check('a question that was run is marked on its card, and the mark opens the analysis it started; one not run has no mark',
  cards[2].classList.contains('ran') && same(['data-nq', 'data-chain', 'title'].map(a => cards[2].querySelector('.was').getAttribute(a)), ['goto', '1700000099', 'Open its analysis'])
  && cards[2].querySelector('.was').textContent === 'run' && !cards[0].classList.contains('ran') && !cards[0].querySelector('.was'), cards[2].outerHTML);
const row = el(b.row({ level: 'blend', label: 'From the answer and an earlier answer', lines: 'B is above A.\nTwelve rows.' }));
check('the row a run opens on says that a question started it, and which way it went - and no more (0314: it had gone on to say what the question came from, which says nothing to a reader of the '
  + 'run); a set on its way has no markup of its own any more: the panel says it',
  typeof b.waiting === 'undefined' && typeof b.head === 'undefined' && row.querySelector('.nq-from').getAttribute('class') === 'nq-from' && row.querySelector('.nq-from .k').textContent === 'Next question'
  && row.querySelector('.nq-from .lv').textContent === 'Blend elements' && row.querySelector('.nq-from').textContent === 'Next question·Blend elements' && !row.querySelector('.nq-from').hasAttribute('title')
  && el(b.row({ level: 'refine' })).querySelector('.nq-from').textContent === 'Next question·Refine focus' && el(b.row({ level: 'deeper' })).querySelector('.lv').textContent === 'deeper', row.innerHTML);

// ------------------------------------------------------------ the button on closing cards
// closing cards as stream-pane.js builds them (0313): an answered run ends on the row of what can be done next, with the code trace's button where it ran code
const DONE = '<div class="sp-done"><div class="head"><span class="title">Run complete</span><span class="nums">2 turns</span></div><div class="acts"><button type="button" class="sp-act sp-codemap">Code trace</button></div></div>';
const NO_CODE = '<div class="sp-done"><div class="head"><span class="title">Run complete</span><span class="nums">1 turn</span></div><div class="acts"></div></div>';
const ROUTINE = '<div class="sp-done"><div class="head"><span class="title">Run 3 complete</span><span class="nums">4 results</span></div><div class="rep ok">Reproduced.</div></div>';
const ASKED = '<div class="sp-done"><div class="head"><span class="title">The analyst has a question for you</span><span class="nums">2 turns</span></div></div>';
const PANE = body => '<div class="sp-strip"></div><div class="sp-ids-slot"></div><div class="sp-stream"><details class="sp-turn"></details>' + body + '</div>';
const several = el(PANE(DONE + ROUTINE + ASKED + NO_CODE));
N.dress(several); N.dress(several); N.dress(null);
const inRow = k => several.querySelectorAll('.sp-done')[k].querySelectorAll('.acts button').map(x => x.textContent).join('|');
check('dress: the closing card of a finished analysis - the one with a row of what can be done next - gets the button, first in that row, before the code trace\'s, once however often it is dressed; a run '
  + 'that ran no code has it alone; a routine\'s run and an analysis that ended on a question have no row and get none',
  several.querySelectorAll('[data-nq="open"]').length === 2 && inRow(0) === 'Next questions|Code trace' && inRow(3) === 'Next questions' && !several.querySelectorAll('.sp-done')[1].querySelector('.sp-next')
  && !several.querySelectorAll('.sp-done')[2].querySelector('.sp-next') && !several.querySelector('.nq-open'), several.innerHTML);

(async () => {
  N.initialize();
  const pane = $('streamOutput');
  const A1 = { chain_id: 11, thread_id: 7, parentChainId: null, queryText: 'Is B above A?', streamOutput: PANE(DONE) };
  const A2 = { chain_id: 12, thread_id: 7, parentChainId: 11, queryText: 'And in the second half?', streamOutput: PANE(DONE) };
  const OLD = { chain_id: 9, thread_id: 7, queryText: 'User requested variations of the enquiry', streamOutput: PANE(DONE) };
  const view = (entry) => { currentResponseIndex = responses.indexOf(entry); pane.innerHTML = entry.streamOutput || ''; N.restore(entry); };
  responses.push(OLD, A1, A2, { status: 'framing', chain_id: 13, thread_id: 7, streamOutput: PANE(DONE) }, { status: 'running', chain_id: 14, thread_id: 7, streamOutput: '' });

  // ---- a chain shown again
  view(OLD); const oldButtons = pane.querySelectorAll('[data-nq="open"]').length;
  view(responses[3]); const framingButtons = pane.querySelectorAll('[data-nq="open"]').length;
  // a pane as the page kept it before the panel (0313 and earlier): the sets under the card, each under its head - and, here, what was of the moment when it was kept
  const KEPT = '<div class="nq-set" data-set="0" data-level="test"><div class="nq-head"><span class="k">Next questions</span><span class="sep">·</span><span class="lv">Test boundaries</span>'
    + '<span class="r">$0.02<button class="agent-instructions-btn sp-prompt" type="button" data-agent="Pathfinder" data-chain="55" data-call="1">⌘</button></span></div>'
    + '<div class="nq-card editing" data-k="0"><div class="from" title="x"><span class="l">From it rests on and did not fit</span></div><div class="tx"><b>The scale.</b> <span class="q">q</span></div><div class="nq-edit"></div></div></div>'
    + '<div class="nq-set" data-set="1" data-level="shift"><div class="nq-head"><span class="k">Next questions</span><span class="r"></span></div>'
    + '<div class="nq-card" data-k="0"><div class="from"><span class="l">From also checked</span></div><div class="tx"><span class="q">r</span></div></div><div class="nq-card" data-k="1"><div class="tx"><span class="q">s</span></div></div></div>';
  pane.innerHTML = PANE(DONE.replace(/<\/div>$/, '<details class="sp-telemetry"></details></div>') + KEPT + '<div class="sp-done"><div class="head"></div></div>');
  currentResponseIndex = 1; N.restore(A1);
  const taken = pane.querySelector('.sp-done .nq-panel'), takenOnce = pane.innerHTML;
  N.restore(A1);
  check('a chain shown again: a finished analysis has its button, though its pane was kept before the button existed; an Explore chain of the retired ideas path has none, nor a brief not yet run; what was of '
    + 'the moment when a pane was kept - a question open for a change - is gone. Sets kept under the card before the panel (0314) are taken into it, in the card that has the buttons, under them and over the call telemetry: the panel is open on '
    + 'the last one\'s way; a set\'s head is gone, and what its call cost and the button to its prompt stand under its questions with how many there are; a title has lost its full stop; what a question '
    + 'starts from is said in today\'s words. Shown again, nothing changes',
    oldButtons === 0 && framingButtons === 0 && pane.querySelectorAll('[data-nq="open"]').length === 1 && !pane.querySelector('.nq-edit') && !pane.querySelector('.nq-card.editing')
    && taken && taken.className === 'nq-panel' && taken.getAttribute('data-show') === 'shift' && same(pane.querySelector('.sp-done').elements.map(e => e.className), ['head', 'acts', 'nq-panel', 'sp-telemetry'])
    && pane.querySelectorAll('.nq-set').length === 2 && pane.querySelectorAll('.nq-set').every(x => x.closest('.nq-sets')) && !pane.querySelector('.nq-head')
    && same(pane.querySelectorAll('.nq-set').map(x => x.className + ':' + x.querySelector('.nq-foot').textContent), ['nq-set:1 question · $0.02⌘', 'nq-set on:2 questions'])
    && pane.querySelector('.nq-foot .sp-prompt').getAttribute('data-chain') === '55' && pane.querySelector('.tx b').textContent === 'The scale' && pane.querySelector('.nq-card .q').textContent === 'q'
    && same(text(pane, '.from .l'), ['From what it rests on and what did not fit', 'From what was also checked']) && taken.querySelector('.nq-lv b').textContent === 'Shift angle'
    && taken.querySelector('.nq-more') && pane.innerHTML === takenOnce, pane.innerHTML);
  // the run a question started, kept before the panel: its opening row also said what the question came from
  pane.innerHTML = PANE('<div class="nq-from" title="the line"><span class="k">Next question</span><span class="sep">·</span><span class="lv">Test boundaries</span><span class="sep">·</span>'
    + '<span>From did not fit</span></div>' + DONE);
  N.restore(A1);
  const oldRow = pane.querySelector('.nq-from');
  check('a chain shown again: the opening row of a run kept before the panel says which way its question went, and no more - not what it came from, in words or behind the row',
    oldRow.textContent === 'Next question·Test boundaries' && oldRow.elements.length === 3 && !oldRow.hasAttribute('title') && el(b.row({ level: 'test' })).querySelector('.nq-from').textContent === oldRow.textContent,
    oldRow.outerHTML);

  // ---- the panel, opened and shut
  const panel = () => pane.querySelector('.nq-panel'), rowsNow = () => pane.querySelectorAll('.nq-row').map(r => r.className + ':' + r.elements.slice(2).map(e => e.textContent).join('|'));
  const wayRow = k => pane.querySelectorAll('.nq-row')[k], click = x => doc.dispatch('click', x);
  view(A1); stored.length = 0;
  const none = !panel();
  click(pane.querySelector('[data-nq="open"]'));
  const firstOpen = { cls: panel().className, show: panel().getAttribute('data-show'), card: pane.querySelector('.sp-done').elements.map(e => e.className), rows: rowsNow(), head: text(pane, '.nq-ph .t'),
                   kept: el(A1.streamOutput).querySelectorAll('.nq-panel .nq-row').length, stored: stored.length };
  click(pane.querySelector('[data-nq="open"]')); const shut1 = [panel().className, el(A1.streamOutput).querySelector('.nq-panel').className];
  click(pane.querySelector('[data-nq="open"]')); click(pane.querySelector('.sp-turn')); const stays = panel().className;
  click(pane.querySelector('[data-nq="shut"]')); const shut2 = panel().className;
  check('the button opens the panel (0314: a list dropped from it, over the card and the question box), inside the card, under its row of buttons: the heading, the five ways with their arrows, none with '
    + 'questions yet. It is kept with the chain as it stands. The button shuts it again, and so does its cross; a click elsewhere leaves it. Nothing is made outside the pane',
    none && same(firstOpen, { cls: 'nq-panel', show: 'list', card: ['head', 'acts', 'nq-panel'], rows: Array(5).fill('nq-row:›'), head: ['Where do you want to go from here?'], kept: 5, stored: 1 })
    && same(shut1, ['nq-panel shut', 'nq-panel shut']) && stays === 'nq-panel' && shut2 === 'nq-panel shut' && !$('nextLevels') && doc.body.querySelectorAll('.save-menu').length === 0, [firstOpen, shut1, stays, shut2]);
  view(responses[4]); pane.innerHTML = PANE(DONE); N.dress(pane); toasts.length = 0;
  click(pane.querySelector('[data-nq="open"]'));
  check('on a chain still running the button does not open the panel: that the analysis is running is said', !panel() && same(toasts, ['Another analysis is running. Wait for it to end, or stop it.']), toasts);

  // ---- a way picked: the set
  view(A1); calls.length = 0; toasts.length = 0; stored.length = 0;
  let release; answer = () => new Promise(r => { release = r; });
  click(pane.querySelector('[data-nq="open"]'));
  click(wayRow(4));
  await tick();
  const during = { rows: rowsNow(), kept: /writing the questions|nq-row (on|dim)/.test(A1.streamOutput), holds: N.holds(), said: toasts.slice(), open: panel().className };
  click(wayRow(0));
  await tick();
  const second = { calls: calls.length, said: toasts.slice() };
  click(pane.querySelector('[data-nq="shut"]')); click(pane.querySelector('[data-nq="open"]'));      // shut and opened while the set is written
  const turned = { rows: rowsNow()[4], open: panel().className, kept: /writing the questions|nq-row (on|dim)/.test(A1.streamOutput), panelKept: /class="nq-panel"/.test(A1.streamOutput) };
  view(A2); const away = pane.querySelectorAll('.nq-row.on').length + pane.querySelectorAll('.live').length;
  view(A1); const back = rowsNow()[4];
  release([200, '{"type": "text", "text": "{"}\n\n' + JSON.stringify({ next: { set: SET, at: 0 } }) + '\n']);
  await tick();
  check('a way picked: the server is asked for a set - the thread, the chain on screen, the way. While it is written that way\'s row says so and the others stand back; nothing of that is kept with '
    + 'the chain, a new analysis is held, and a second way is not asked for: the wait is said. The panel shut and opened meanwhile still says so, and what the chain keeps of it does not. On another chain nothing is being written; back on the first the row says so again',
    same(calls[0], ['/architect/next', { thread_id: 7, chain_id: 11, level: 'emergence' }]) && same(during.rows, ['nq-row dim:›', 'nq-row dim:›', 'nq-row dim:›', 'nq-row dim:›', 'nq-row on:writing the questions…'])
    && !during.kept && during.holds === true && same(during.said, ['The questions are being written. Wait for them.']) && during.open === 'nq-panel'
    && second.calls === 1 && same(second.said.slice(1), ['The questions are being written. Wait for them.']) && same(turned, { rows: 'nq-row on:writing the questions…', open: 'nq-panel', kept: false, panelKept: true }) && away === 0 && back === 'nq-row on:writing the questions…', [during, second, turned, away, back]);
  const shown = () => ({ show: panel().getAttribute('data-show'), top: panel().querySelector('.nq-top').elements.map(e => e.className), way: text(pane, '.nq-lv b').join(), rows: pane.querySelectorAll('.nq-row').length,
                         sets: pane.querySelectorAll('.nq-set').map(x => x.className + ':' + x.getAttribute('data-set')), end: text(pane, '.nq-end button').join() });
  const came = shown();
  check('the set that comes back takes the list\'s place in the panel: the way back to all five, that way\'s name and sentence, its questions, how many they are and what they cost, and under them the '
    + 'button for more. It is kept with the chain - in its markup and in the page\'s store - and nothing holds a new analysis any more; the stream\'s other lines are passed over',
    same(came, { show: 'emergence', top: ['nq-ph', 'nq-lv'], way: 'Follow emergence', rows: 0, sets: ['nq-set on:0'], end: 'Write more' }) && pane.querySelectorAll('.nq-set.on .nq-card').length === 3
    && pane.querySelector('.nq-set .nq-foot').textContent === '3 questions · $0.02⌘' && pane.querySelector('.nq-set').closest('.nq-sets') && pane.querySelector('.nq-set').closest('.sp-done')
    && el(A1.streamOutput).querySelectorAll('.nq-panel .nq-set[data-set="0"] .nq-card').length === 3 && el(A1.streamOutput).querySelector('.nq-panel').getAttribute('data-show') === 'emergence'
    && A1.streamOutput.includes('data-nq="open"') && same(stored, Array(4).fill(['responses', 5])) && N.holds() === false && toasts.length === 2, [came, pane.innerHTML.slice(-300), stored.slice()]);      // kept when it was opened, shut and opened again, and with the set

  // ---- back at the list: a way that has questions says so, and shows them again
  calls.length = 0; stored.length = 0;
  click(pane.querySelector('[data-nq="list"]'));
  const atList = { show: panel().getAttribute('data-show'), rows: rowsNow(), sets: pane.querySelectorAll('.nq-set').map(x => x.className), kept: el(A1.streamOutput).querySelector('.nq-panel').getAttribute('data-show') };
  click(wayRow(4).querySelector('.n'));
  await tick();
  const shownAgain = { shown: shown(), calls: calls.length };
  click(pane.querySelector('[data-nq="list"]'));
  check('back at the list (0314): the way that has questions says how many, its questions are out of sight, and the chain keeps that the list is shown. A click on that way shows its questions again: '
    + 'the server is asked nothing',
    same(atList, { show: 'list', rows: ['nq-row:›', 'nq-row:›', 'nq-row:›', 'nq-row:›', 'nq-row:3 questions|›'], sets: ['nq-set'], kept: 'list' })
    && same(shownAgain, { shown: came, calls: 0 }), [atList, shownAgain]);

  // ---- no set made
  const tries = [];
  for (const a of [[200, JSON.stringify({ next: { error: 'The Pathfinder\'s reply could not be read (it holds no JSON object).' } })],
                   [403, { error: 'authorization_failed', message: 'You need $0.010 per query but your balance is $0.00. Please add funds to continue.' }], 'down', [200, '\n']]) {
    answer = a; toasts.length = 0; stored.length = 0;
    click(wayRow(1));
    await tick();
    tries.push([toasts.slice(), pane.querySelectorAll('.nq-set').length, rowsNow()[1], stored.length, N.holds()]);
  }
  check('no set made: the reason is said - the server\'s own words, a refusal for the balance, a server that cannot be reached, a stream that ends on nothing - the way\'s row is a row to click again, '
    + 'nothing is kept and nothing is held',
    same(tries, [[['The Pathfinder\'s reply could not be read (it holds no JSON object).'], 1, 'nq-row:›', 0, false], [['You need $0.010 per query but your balance is $0.00. Please add funds to continue.'], 1, 'nq-row:›', 0, false],
                 [['No questions were written: the server could not be reached.'], 1, 'nq-row:›', 0, false], [['No questions were written.'], 1, 'nq-row:›', 0, false]]), tries);
  queryRunning = true; calls.length = 0; toasts.length = 0;
  click(wayRow(2)); await tick();
  click(pane.querySelector('.nq-card .go')); await tick();
  queryRunning = false;
  check('while an analysis runs no set is asked for and no question is run: that it runs is said', calls.length === 0 && submitted.length === 0 && same(toasts, Array(2).fill('Another analysis is running. Wait for it to end, or stop it.')), toasts);

  // ---- a set that comes back while another chain is on screen
  answer = () => new Promise(r => { release = r; }); calls.length = 0; stored.length = 0;
  click(pane.querySelector('[data-nq="shut"]'));                    // the coach shut the panel after asking
  click(pane.querySelector('[data-nq="open"]')); click(wayRow(2)); click(pane.querySelector('[data-nq="shut"]')); await tick();
  view(A2);
  release([200, JSON.stringify({ next: { set: { level: 'test', cost: 0, chain: 1700000078, questions: [{ title: 'The scale', text: 'Was one scale used for both arms?', from: [{ kind: 'anchor', text: 'The scale was the same. (cannot be checked)' }] }] }, at: 1 } })]);
  await tick();
  const elsewhere = pane.querySelectorAll('.nq-set').length + pane.querySelectorAll('.nq-panel').length, keptSets = el(A1.streamOutput).querySelectorAll('.nq-set').map(x => x.getAttribute('data-set'));
  view(A1);
  check('a set that comes back while another chain is on screen goes to the chain it was asked for - into the panel of its kept pane, not the one on screen - and is there when that chain is shown '
    + 'again: the panel is open on the new questions, though the coach had shut it',
    elsewhere === 0 && same(keptSets, ['0', '1']) && same(pane.querySelectorAll('.nq-set').map(x => x.className + ':' + x.getAttribute('data-level')), ['nq-set:emergence', 'nq-set on:test'])
    && panel().className === 'nq-panel' && panel().getAttribute('data-show') === 'test' && pane.querySelector('.nq-lv b').textContent === 'Test boundaries'
    && pane.querySelectorAll('.nq-set')[1].querySelector('.from .l').textContent === 'From what it rests on', [elsewhere, keptSets]);

  // ---- more of one way
  answer = () => new Promise(r => { release = r; }); calls.length = 0; toasts.length = 0;
  click(pane.querySelector('[data-nq="more"]')); await tick();
  const moreAsked = { call: calls[0], end: pane.querySelector('.nq-more').textContent, off: pane.querySelector('.nq-more').hasAttribute('disabled'), way: pane.querySelector('.nq-lv b').textContent,
                      kept: /writing the questions/.test(A1.streamOutput) };
  release([200, JSON.stringify({ next: { set: { level: 'test', cost: 0.02, questions: [{ title: 'One more', text: 'And the other scale?', from: [{ kind: 'would_change', text: 'x' }] }, { text: 'And the third?', from: [] }] }, at: 2 } })]);
  await tick();
  const moreCame = { sets: pane.querySelectorAll('.nq-set').map(x => x.className + ':' + x.getAttribute('data-set')), end: pane.querySelector('.nq-more').textContent, off: pane.querySelector('.nq-more').hasAttribute('disabled') };
  click(pane.querySelector('[data-nq="list"]'));
  const counted = rowsNow();
  click(wayRow(4));
  check('more of one way (0314): Write more, under a way\'s questions, asks the server for a set of that way; while it is written the button says so and cannot be pressed, the questions stay, and '
    + 'nothing of the moment is kept. The new set stands under the one before, both shown; at the list the way counts the questions of both',
    same(moreAsked, { call: ['/architect/next', { thread_id: 7, chain_id: 11, level: 'test' }], end: 'writing the questions…', off: true, way: 'Test boundaries', kept: false })
    && same(moreCame, { sets: ['nq-set:0', 'nq-set on:1', 'nq-set on:2'], end: 'Write more', off: false })
    && same(counted, ['nq-row:›', 'nq-row:›', 'nq-row:3 questions|›', 'nq-row:›', 'nq-row:3 questions|›']) && panel().getAttribute('data-show') === 'emergence', [moreAsked, moreCame, counted]);

  // ---- a question changed
  const card0 = pane.querySelectorAll('.nq-set')[0].querySelectorAll('.nq-card')[0];
  doc.dispatch('click', card0.querySelector('.pen'));
  const opened = { editing: card0.classList.contains('editing'), value: card0.querySelector('.nq-input').value, kept: A1.streamOutput.includes('nq-edit') };
  doc.dispatch('click', card0.querySelector('.pen'));
  const once = card0.querySelectorAll('.nq-edit').length;
  card0.querySelector('.nq-input').value = '  Is the gap wider\n in the last third?  ';
  const cardB = pane.querySelectorAll('.nq-set')[0].querySelectorAll('.nq-card')[1];
  doc.dispatch('click', cardB.querySelector('.pen'));      // another question is open for a change while this one is kept
  stored.length = 0;
  doc.dispatch('click', card0.querySelector('[data-nq="keep"]'));
  const keptText = el(A1.streamOutput).querySelector('.nq-card .q').textContent;
  const stillOpen = [cardB.classList.contains('editing'), !!cardB.querySelector('.nq-edit'), A1.streamOutput.includes('nq-edit'), A1.streamOutput.includes('editing')];
  doc.dispatch('click', cardB.querySelector('[data-nq="cancel"]'));
  check('the pencil opens the question where it stands, once; Keep makes what was typed the card\'s question, on one line - on screen, and kept with the chain. A question the coach changed is their own: '
    + 'the title it came with goes. The kept pane never holds a question open for a change - not the one still open on screen beside it',
    opened.editing && opened.value === 'Is the gap <wider> in the second half?' && !opened.kept && once === 1 && !card0.classList.contains('editing') && !card0.querySelector('.nq-edit')
    && card0.querySelector('.q').textContent === 'Is the gap wider in the last third?' && !card0.querySelector('.tx b') && keptText === 'Is the gap wider in the last third?'
    && !el(A1.streamOutput).querySelectorAll('.nq-card')[0].querySelector('.tx b') && el(A1.streamOutput).querySelectorAll('.nq-card')[2].querySelector('.tx b') && same(stored, [['responses', 5]])
    && same(stillOpen, [true, true, false, false]), [opened, once, keptText, stillOpen]);
  const card3 = pane.querySelectorAll('.nq-set')[1].querySelectorAll('.nq-card')[0];
  stored.length = 0;
  doc.dispatch('click', card3.querySelector('.pen')); doc.dispatch('click', card3.querySelector('[data-nq="keep"]'));
  check('a question kept as it stood is not changed: its title stays, and nothing is written to the chain',
    card3.querySelector('.tx b').textContent === 'The scale' && card3.querySelector('.q').textContent === 'Was one scale used for both arms?' && !card3.classList.contains('editing') && stored.length === 0, card3.outerHTML);
  const card1 = pane.querySelectorAll('.nq-set')[0].querySelectorAll('.nq-card')[1], was1 = card1.querySelector('.q').textContent;
  doc.dispatch('click', card1.querySelector('.pen')); card1.querySelector('.nq-input').value = 'Dropped.';
  doc.dispatch('click', card1.querySelector('[data-nq="cancel"]'));
  const afterCancel = [card1.querySelector('.q').textContent, card1.classList.contains('editing')];
  doc.dispatch('click', card1.querySelector('.pen')); card1.querySelector('.nq-input').value = 'Dropped again.';
  const esc = doc.dispatch('keydown', card1.querySelector('.nq-input'), { key: 'Escape' });
  const afterEscape = [card1.querySelector('.q').textContent, card1.classList.contains('editing'), !!esc.defaulted];
  doc.dispatch('click', card1.querySelector('.pen')); card1.querySelector('.nq-input').value = '   ';
  const enter = doc.dispatch('keydown', card1.querySelector('.nq-input'), { key: 'Enter' });
  const afterEmpty = [card1.querySelector('.q').textContent, card1.classList.contains('editing'), !!enter.defaulted];
  doc.dispatch('click', card1.querySelector('.pen')); card1.querySelector('.nq-input').value = 'Does the gap hold without the two rows?';
  const shift = doc.dispatch('keydown', card1.querySelector('.nq-input'), { key: 'Enter', shiftKey: true });
  const afterShift = [card1.classList.contains('editing'), !!shift.defaulted];
  doc.dispatch('keydown', card1.querySelector('.nq-input'), { key: 'Enter', isComposing: true });
  const afterComposing = card1.classList.contains('editing');
  doc.dispatch('keydown', card1.querySelector('.nq-input'), { key: 'Enter' });
  check('Cancel and Escape leave the question as it was; Enter keeps what was typed, Shift+Enter is a new line, a key pressed while a word is being composed is not Enter; nothing typed keeps the question',
    same(afterCancel, [was1, false]) && same(afterEscape, [was1, false, true]) && same(afterEmpty, [was1, false, true]) && same(afterShift, [true, false]) && afterComposing === true
    && card1.querySelector('.q').textContent === 'Does the gap hold without the two rows?' && !card1.classList.contains('editing'), [afterCancel, afterEscape, afterEmpty, afterShift]);

  // ---- a question run
  submitted.length = 0; toasts.length = 0;
  $('queryInput').value = 'something the coach was typing';
  doc.dispatch('click', card0.querySelector('.go'));
  const card2 = pane.querySelectorAll('.nq-set')[0].querySelectorAll('.nq-card')[2];
  doc.dispatch('click', card2.querySelector('.pen')); card2.querySelector('.nq-input').value = 'Typed, then run at once?';
  doc.dispatch('click', card2.querySelector('.go'));
  check('the arrow runs the question as it stands: the page\'s send is given the question, the chain it follows, the set and the question by their places, and the way it went - no more (0314: it had carried where the question comes from, for the row the run opens on); a question '
    + 'open for a change is taken as typed, and kept. The composer\'s own words are not touched',
    same(submitted[0], { next: { text: 'Is the gap wider in the last third?', chain: 11, set: 0, k: 0, level: 'emergence' } })
    && same(submitted[1], { next: { text: 'Typed, then run at once?', chain: 11, set: 0, k: 2, level: 'emergence' } }) && !card2.classList.contains('editing')
    && el(A1.streamOutput).querySelectorAll('.nq-set')[0].querySelectorAll('.nq-card .q')[2].textContent === 'Typed, then run at once?' && $('queryInput').value === 'something the coach was typing'
    && toasts.length === 0, submitted);
  answer = () => new Promise(r => { release = r; }); submitted.length = 0;
  click(pane.querySelector('[data-nq="list"]')); click(wayRow(3)); await tick();
  doc.dispatch('click', card0.querySelector('.go'));
  const heldRun = [submitted.length, toasts.slice()];
  release([200, JSON.stringify({ next: { error: 'no' } })]); await tick();
  check('while a set is being written a question is not run: the wait is said', same(heldRun, [0, ['The questions are being written. Wait for them.']]), heldRun);

  // ---- the run it started: the row, the mark on the card, the map
  const live = { status: 'running', chain_id: null, thread_id: 7, parentChainId: 11, queryText: 'Does the gap hold without the two rows?', streamOutput: '' };
  responses.push(live); liveState.running = true; liveState.index = responses.length - 1; currentResponseIndex = liveState.index; pane.innerHTML = ''; rows.length = 0;
  const next = { text: live.queryText, chain: 11, set: 0, k: 1, level: 'emergence' };
  N.started(next);
  const marks = () => el(A1.streamOutput).querySelectorAll('.nq-set').map(s => s.querySelectorAll('.nq-card').map(c => c.querySelectorAll('.was').map(w => w.getAttribute('data-chain')).join('+') + (c.classList.contains('ran') ? '' : '-')));
  const beforeId = marks();      // the third question of the first set came from the server as run
  stored.length = 0;
  N.ran(null); N.ran(1700000100); N.ran(1700000101);
  check('the analysis a question started: the live chain carries what it was started from and its pane opens on the row that says so. Once the server has named the run\'s chain the question\'s card - that '
    + 'set\'s, that question\'s - is marked with it, in the kept pane of the analysis it follows, once; the other cards are as they were',
    live.next === next && rows.length === 1 && el(rows[0]).querySelector('.nq-from').textContent === 'Next question·Follow emergence'
    && same(beforeId, [['-', '-', '1700000099'], ['-'], ['-', '-']]) && same(marks(), [['-', '1700000100', '1700000099'], ['-'], ['-', '-']]) && same(stored, [['responses', 6]]) && pane.innerHTML === '', [rows, beforeId, marks()]);
  const done = { chain_id: 1700000100, thread_id: 7, parentChainId: 11, queryText: live.queryText, streamOutput: PANE(rows[0] + DONE) };
  check('the Workflow map\'s mark: a chain started from a question says next question - while it runs by what it carries, afterwards by the row its kept pane opens on; an analysis typed by the coach says '
    + 'nothing, one framed with the Pathfinder says so',
    N.made(live) === true && N.made(done) === true && N.made(A2) === false && N.made(null) === false && window.ArchitectUI.mark(live) === 'next question' && window.ArchitectUI.mark(done) === 'next question'
    && window.ArchitectUI.mark(A2) === '' && window.ArchitectUI.mark({ tabContent: '<div id="tab-brief" class="tab">Brief</div>', streamOutput: done.streamOutput }) === 'Pathfinder', null);
  responses[liveState.index] = done; liveState.running = false;      // the run ended: its kept entry stands where the live one did
  N.ran(1700000102);
  const afterEnd = marks();
  view(A1);
  const again = pane.querySelectorAll('.nq-set')[0].querySelectorAll('.nq-card')[1];
  went.length = 0; doc.dispatch('click', again.querySelector('.was'));
  const start = n => { responses.push({ status: 'running', chain_id: null, thread_id: 7, next: n }); liveState.running = true; liveState.index = responses.length - 1; };
  start({ chain: 11, set: 1, k: 0 }); N.ran(1700000103);
  const other = marks();
  start(Object.assign({}, next, { marked: false })); N.ran(1700000104);
  liveState.running = false; liveState.index = null; responses.pop(); responses.pop();
  check('a chain not started from a question marks nothing; the mark on the card opens the analysis the question started; a question of another set is marked in its own set; a question run again carries '
    + 'the chain of its last run, one mark - on screen too, where the analysis it follows is the one in view',
    same(afterEnd, [['-', '1700000100', '1700000099'], ['-'], ['-', '-']]) && same(went, ['1700000100']) && same(other, [['-', '1700000100', '1700000099'], ['1700000103'], ['-', '-']])
    && same(marks(), [['-', '1700000104', '1700000099'], ['1700000103'], ['-', '-']]) && again.querySelectorAll('.was').length === 1 && again.querySelector('.was').getAttribute('data-chain') === '1700000104',
    [afterEnd, went, other, marks()]);

  // ---- the page's hooks, read from the source
  const root = path.join(__dirname, '..', '..', 'web_app'), js = f => fs.readFileSync(path.join(root, 'static', 'js', f), 'utf8'), css = f => fs.readFileSync(path.join(root, 'static', 'css', f), 'utf8');
  const html = fs.readFileSync(path.join(root, 'templates', 'index.html'), 'utf8'), qp = js('query-processing.js');
  check('index.html: the plant and its popover have left the composer; next-questions.js is loaded after the Pathfinder\'s module and before the map\'s; the app starts it',
    !html.includes('suggestQuestions') && !html.includes('branchingSliderPopup') && !html.includes('branching-icon') && html.indexOf('js/next-questions.js') > html.indexOf('js/architect.js')
    && html.indexOf('js/next-questions.js') < html.indexOf('js/workflowGraph.js') && js('core.js').includes('window.NextQuestionsUI.initialize();'));
  check('the send: a next question is the query as it stands - not typed, so the Pathfinder\'s switch does not apply; nothing starts while a set is being written; the run\'s pane is told what started it; '
    + 'the composer is neither cleared nor refilled; the server is told the set and the question; the stream\'s id line marks the card',
    qp.includes("const query = framed ? String(framed.queryText || '').trim() : (next ? String(next.text || '').trim() : queryInput.value.trim());")
    && qp.includes('if (window.NextQuestionsUI && window.NextQuestionsUI.holds()) return;') && qp.indexOf('window.NextQuestionsUI.holds()') < qp.indexOf('window.ArchitectUI.framingInView()')
    && qp.indexOf('window.NextQuestionsUI.holds()') > qp.indexOf('stopAutoExplore();') && qp.includes('if (next) window.NextQuestionsUI.started(next);')
    && qp.indexOf('if (next) window.NextQuestionsUI.started(next);') > qp.indexOf('beginLiveChain(framed);') && qp.includes('if (!synthesis && !next) {') && qp.includes('if (!framed && !next) queryInput.value = query;')
    && qp.includes('if (next) requestBody.next = { set: next.set, k: next.k };') && qp.includes('if (window.NextQuestionsUI) window.NextQuestionsUI.ran(data.chain_id);')
    && qp.indexOf('window.NextQuestionsUI.ran(data.chain_id)') > qp.indexOf("if (data.type === \"id\")") && qp.indexOf('window.NextQuestionsUI.ran(data.chain_id)') < qp.indexOf('data.type === "html"'));
  check('the pane and the map: a finished analysis is dressed when its closing card is made and when its chain is shown again; the map asks the Pathfinder\'s module for the mark, which asks this one',
    js('stream-pane.js').includes('append(build.runEnd(r));\n        if (window.NextQuestionsUI) window.NextQuestionsUI.dress(p);')
    && js('workflow-management.js').includes('if (window.NextQuestionsUI) window.NextQuestionsUI.restore(response);')
    && js('workflow-management.js').indexOf('window.NextQuestionsUI.restore(response)') > js('workflow-management.js').indexOf('reattachRestoredListeners();\n    if (window.ArchitectUI)')
    && js('architect.js').includes("return window.NextQuestionsUI && window.NextQuestionsUI.made(r) ? 'next question' : '';") && js('workflowGraph.js').includes('window.ArchitectUI.mark(resp)'));
  const paneCss = css('pane.css'), shell = css('shell.css');
  check('the stylesheets (0314): in pane.css the panel inside the card, under a rule, out of sight when shut; a way\'s row and a question\'s row on the same grid - a column for the name or the title, '
    + 'one for the text, the marks at the right - the row of the way being written outlined and the others faded; a question\'s title and text as cells of its row, what it starts from under the '
    + 'text in small plain letters, the mark of a run beside the pencil; only the sets of the way shown are shown; the run\'s row. Nothing is left of a set\'s head, of the word that a set is '
    + 'being read, of the list on the Save menu\'s look in shell.css, of the plant and its popover, or of the button\'s own row',
    ['.sp-done .nq-panel { margin-top: 10px; padding-top: 10px; border-top: 1px solid var(--border-color);', '.sp-done .nq-panel.shut { display: none; }',
     '.nq-row { display: grid; grid-template-columns: 128px 1fr auto auto;', '.nq-row.on { border-color: var(--c-model);', '.nq-row.dim { opacity: .45; }', '.nq-row .n {', '.nq-row .live::before {',
     '.nq-card { display: grid; grid-template-columns: 128px 1fr auto auto;', '.nq-card .tx { display: contents; }', '.nq-card .tx b { grid-column: 1;', '.nq-card .q { grid-column: 2; grid-row: 1;',
     '.nq-card .from { grid-column: 2; grid-row: 2; font-size: 11px;', '.nq-card .was { grid-column: 3; grid-row: 1;', '.nq-card .tools { grid-column: 4; grid-row: 1;', '.nq-card .nq-edit { grid-column: 2 / 4; grid-row: 1; }',
     '.nq-card.editing .q, #streamOutput .nq-card.editing .pen, #streamOutput .nq-card.editing .was { display: none; }', '.nq-set { display: none; }', '.nq-set.on { display: block;', '.nq-foot {',
     '.nq-more:disabled {', '.nq-lv {', '.nq-what {', '.nq-back {', '.nq-x {', '.nq-from {', '.nq-input {'].every(r => paneCss.includes('#streamOutput ' + r))
    && !/\.nq-card \.from \{[^}]*text-transform/.test(paneCss) && !paneCss.includes('.nq-head') && !paneCss.includes('.nq-reading') && !paneCss.includes('.nq-open') && !paneCss.includes('.sp-next')
    && paneCss.includes('#streamOutput .sp-done .acts {') && paneCss.includes('#streamOutput .sp-act {')
    && !shell.includes('nq-menu') && !shell.includes('branchingSliderPopup') && !shell.includes('suggest-questions')
    && !css('styles.css').includes('suggest-questions') && !css('styles.css').includes('.branching-icon') && !js('ui-controls.js').includes('SuggestQuestions')
    && !/nextLevels|save-menu|hideMenu|showMenu/.test(js('next-questions.js')));

  finish();
})().catch(e => { check('the module ran without throwing', false, e && e.stack); finish(); });

function finish() {
  let pass = 0, fail = 0;
  for (const [n, c, d] of results) { if (c) pass++; else fail++; console.log((c ? '  ok   ' : '  FAIL ') + n + (c ? '' : '  <- ' + (d === undefined ? '' : JSON.stringify(d)).slice(0, 900))); }
  console.log(`\n${pass} passed, ${fail} failed`);
  process.exit(fail ? 1 : 0);
}
