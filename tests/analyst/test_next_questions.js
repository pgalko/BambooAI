// Next questions on the page (docs/ARCHITECT_DESIGN.md §2.7, §2.9, §2.15; 2026-11-16): next-questions.js. Its pure parts -
// the button, the five levels, a set of questions as cards, the row a run opens on - and the module driven on the mini DOM
// with a scripted server: the button on a finished analysis' closing card, a level picked, the set that comes back kept
// with the chain, a question changed and run, the card marked once its analysis is on, the thread map's mark. Then the
// page's hooks, read from the source.
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
const button = el(b.button()), levels = el(b.menu());
check('the button of a closing card: its own row, the plant and its two words, a plain title; the list of levels: the five in the design\'s order, each its key, its name and one plain line',
  button.querySelector('.nq-open > .sp-next') === null && button.querySelector('.nq-open .sp-next[data-nq="open"]').textContent === 'Next questions' && button.querySelector('.sp-next svg')
  && button.querySelector('.sp-next').getAttribute('title') === 'Questions that could follow this analysis'
  && same(levels.querySelectorAll('.it[data-nq="level"]').map(i => [i.getAttribute('data-level'), i.querySelector('b').textContent, i.querySelector('span').textContent]),
          [['refine', 'Refine focus', 'the same question, narrower'], ['shift', 'Shift angle', 'another explanation of the result'], ['test', 'Test boundaries', 'what the result rests on'],
           ['blend', 'Blend elements', 'two findings together'], ['emergence', 'Follow emergence', 'what did not fit']]), b.menu());
const set = el(b.set(SET, 2)).querySelector('.nq-set'), cards = set.querySelectorAll('.nq-card');
check('a set: its place and its level ride in its markup; its head says what it is and names the level, with what the call cost and the button to the prompt the Architect received - its own chain on the run log, the first call there',
  set.getAttribute('data-set') === '2' && set.getAttribute('data-level') === 'emergence' && same(text(set, '.nq-head .k, .nq-head .lv'), []) && set.querySelector('.nq-head .k').textContent === 'Next questions'
  && set.querySelector('.nq-head .lv').textContent === 'Follow emergence' && set.querySelector('.nq-head .r').textContent === '$0.02⌘'
  && same(['class', 'data-agent', 'data-chain', 'data-call'].map(a => set.querySelector('.nq-head .sp-prompt').getAttribute(a)), ['agent-instructions-btn sp-prompt', 'Architect', '1700000077', '1'])
  && cards.length === 3 && same(cards.map(c => c.getAttribute('data-k')), ['0', '1', '2']), set.querySelector('.nq-head').outerHTML);
const cheap = el(b.set({ level: 'test', cost: 0.004, questions: [] }, 0));
check('a set whose call cost under half a cent shows no cost; one without a chain on record has no button to a prompt; a level the page does not know is shown as it came',
  cheap.querySelector('.nq-head .r').textContent === '' && !cheap.querySelector('.sp-prompt') && el(b.set({ level: 'deeper', questions: [] }, 0)).querySelector('.lv').textContent === 'deeper'
  && el(b.set({ level: 'test', cost: 0.005, questions: [] }, 0)).querySelector('.nq-head .r').textContent === '$0.01', cheap.innerHTML);
check('a card: where the question comes from in the page\'s words - the lines themselves as the label\'s title, two kinds joined - then its title in bold with one full stop, its text, a pencil and an arrow; '
  + 'what a model wrote is text, never markup; a question without a title has none; a kind the page has no word for gives no label',
  cards[0].querySelector('.from .l').textContent === 'From did not fit' && cards[0].querySelector('.from').getAttribute('title') === MISFIT.text
  && cards[0].querySelector('.tx b').textContent === 'The second half.' && cards[0].querySelector('.tx .q').textContent === 'Is the gap <wider> in the second half?' && !cards[0].querySelector('.q wider')
  && same(cards[0].querySelectorAll('.tools button').map(x => [x.className, x.getAttribute('data-nq'), x.getAttribute('title')]), [['pen', 'edit', 'Change'], ['go', 'run', 'Start the analysis']])
  && cards[1].querySelector('.from .l').textContent === 'From the answer and an earlier answer' && cards[1].querySelector('.from').getAttribute('title') === 'B is above A.\nTwelve rows.' && !cards[1].querySelector('.tx b')
  && cards[2].querySelector('.from .l').textContent === '' && el(b.from(null)).querySelector('.l').textContent === '', cards[0].outerHTML);
check('a question that was run is marked on its card, and the mark opens the analysis it started; one not run has no mark',
  cards[2].classList.contains('ran') && same(['data-nq', 'data-chain', 'title'].map(a => cards[2].querySelector('.was').getAttribute(a)), ['goto', '1700000099', 'Open its analysis'])
  && cards[2].querySelector('.was').textContent === 'run' && !cards[0].classList.contains('ran') && !cards[0].querySelector('.was'), cards[2].outerHTML);
const wait = el(b.waiting('test')), row = el(b.row({ level: 'blend', label: 'From the answer and an earlier answer', lines: 'B is above A.\nTwelve rows.' }));
check('a set on its way names its level and says it is being read; the row a run opens on says it is a next question, at which level and from what, the lines as its title',
  wait.querySelector('.nq-set.nq-wait .nq-head .lv').textContent === 'Test boundaries' && wait.querySelector('.nq-reading').textContent === 'reading…' && !wait.querySelector('.nq-card')
  && row.querySelector('.nq-from').getAttribute('class') === 'nq-from' && row.querySelector('.nq-from .k').textContent === 'Next question' && row.querySelector('.nq-from .lv').textContent === 'Blend elements'
  && row.querySelector('.nq-from').textContent === 'Next question·Blend elements·From the answer and an earlier answer' && row.querySelector('.nq-from').getAttribute('title') === 'B is above A.\nTwelve rows.'
  && el(b.row({ level: 'refine' })).querySelector('.nq-from').textContent === 'Next question·Refine focus', row.innerHTML);

// ------------------------------------------------------------ the button on closing cards
const DONE = '<div class="sp-done"><div class="title">Run complete</div><div class="links"><a href="#">Answer →</a><a href="#">Investigation →</a></div></div>';
const ROUTINE = '<div class="sp-done"><div class="title">Run 3 complete</div><div class="links"><a href="#">Trend →</a><a href="#">Results →</a></div></div>';
const ASKED = '<div class="sp-done"><div class="title">The analyst has a question for you</div></div>';
const PANE = body => '<div class="sp-strip"></div><div class="sp-ids-slot"></div><div class="sp-stream"><details class="sp-turn"></details>' + body + '</div>';
const several = el(PANE(DONE + ROUTINE + ASKED));
N.dress(several); N.dress(several); N.dress(null);
check('dress: the closing card of a finished analysis - the one whose links open on the answer - gets the button, once however often it is dressed; a routine\'s run and an analysis that ended on a question get none',
  several.querySelectorAll('[data-nq="open"]').length === 1 && several.querySelectorAll('.sp-done')[0].querySelector('.sp-next') && !several.querySelectorAll('.sp-done')[1].querySelector('.sp-next')
  && !several.querySelectorAll('.sp-done')[2].querySelector('.sp-next'), several.innerHTML);

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
  pane.innerHTML = PANE(DONE + '<div class="nq-set nq-wait"></div><div class="nq-set" data-set="0"><div class="nq-card editing" data-k="0"><div class="tx"><span class="q">q</span></div><div class="nq-edit"></div></div></div>');
  currentResponseIndex = 1; N.restore(A1);
  check('a chain shown again: a finished analysis has its button, though its pane was kept before the button existed; an Explore chain of the retired ideas path has none, nor a brief not yet run; what was of '
    + 'the moment when a pane was kept - a question open for a change, a set on its way - is gone',
    oldButtons === 0 && framingButtons === 0 && pane.querySelectorAll('[data-nq="open"]').length === 1 && !pane.querySelector('.nq-wait') && !pane.querySelector('.nq-edit')
    && !pane.querySelector('.nq-card.editing') && pane.querySelector('.nq-card .q').textContent === 'q', pane.innerHTML);

  // ---- the levels
  view(A1);
  const open = pane.querySelector('[data-nq="open"]');
  doc.dispatch('click', open);
  const list = $('nextLevels'), shown1 = list && list.style.display;
  doc.dispatch('click', open); const shown2 = list.style.display;
  doc.dispatch('click', open); doc.dispatch('keydown', pane, { key: 'Escape' }); const shown3 = list.style.display;
  doc.dispatch('click', open); doc.dispatch('click', pane.querySelector('.sp-turn')); const shown4 = list.style.display;
  check('the button opens the list of levels, once made, by the button; a second click, Escape or a click elsewhere closes it',
    list && list.className === 'save-menu nq-menu' && shown1 === '' && shown2 === 'none' && shown3 === 'none' && shown4 === 'none' && list.querySelectorAll('.it').length === 5 && list.parent === doc.body
    && doc.body.querySelectorAll('#nextLevels').length === 1, [shown1, shown2, shown3, shown4]);
  view(responses[4]); pane.innerHTML = PANE(DONE); N.dress(pane); toasts.length = 0;
  doc.dispatch('click', pane.querySelector('[data-nq="open"]'));
  check('on a chain still running the button does not open the list: that the analysis is running is said', list.style.display === 'none' && same(toasts, ['Another analysis is running. Wait for it to end, or stop it.']), toasts);

  // ---- a level picked: the set
  view(A1); calls.length = 0; toasts.length = 0; stored.length = 0;
  let release; answer = () => new Promise(r => { release = r; });
  doc.dispatch('click', pane.querySelector('[data-nq="open"]'));
  doc.dispatch('click', list.querySelectorAll('.it')[4]);
  await tick();
  const during = { menu: list.style.display, wait: text(pane, '.nq-wait .lv, .nq-wait .nq-reading'), level: pane.querySelector('.nq-wait .lv') && pane.querySelector('.nq-wait .lv').textContent,
                   reading: pane.querySelector('.nq-wait .nq-reading') && pane.querySelector('.nq-wait .nq-reading').textContent, last: pane.querySelector('.sp-stream').lastElementChild.className,
                   kept: A1.streamOutput.includes('nq-wait'), holds: N.holds(), said: toasts.slice() };
  doc.dispatch('click', pane.querySelector('[data-nq="open"]'));
  doc.dispatch('click', list.querySelectorAll('.it')[0]);
  await tick();
  const second = { calls: calls.length, said: toasts.slice() };
  view(A2); const awayWait = pane.querySelectorAll('.nq-wait').length;
  view(A1); const backWait = pane.querySelectorAll('.nq-wait').length;
  release([200, '{"type": "text", "text": "{"}\n\n' + JSON.stringify({ next: { set: SET, at: 0 } }) + '\n']);
  await tick();
  check('a level picked: the list closes and the server is asked for a set - the thread, the chain on screen, the level; while it is on its way the pane says so under the closing card, nothing of that is '
    + 'kept with the chain, a new analysis is held, and a second level is not asked for: the wait is said. On another chain nothing waits; back on the first the wait is shown again',
    during.menu === 'none' && same(calls[0], ['/architect/next', { thread_id: 7, chain_id: 11, level: 'emergence' }]) && during.level === 'Follow emergence' && during.reading === 'reading…'
    && during.last === 'nq-set nq-wait' && !during.kept && during.holds === true && same(during.said, ['The questions are being written. Wait for them.'])
    && second.calls === 1 && same(second.said.slice(1), ['The questions are being written. Wait for them.']) && awayWait === 0 && backWait === 1, [during, second, awayWait, backWait]);
  check('the set that comes back: its cards under the closing card in the place of the wait, kept with the chain - in its markup and in the page\'s store - and nothing holds a new analysis any more; the '
    + 'stream\'s other lines are passed over',
    !pane.querySelector('.nq-wait') && pane.querySelector('.sp-stream').lastElementChild.getAttribute('data-set') === '0' && pane.querySelectorAll('.nq-set .nq-card').length === 3
    && el(A1.streamOutput).querySelectorAll('.nq-set[data-set="0"] .nq-card').length === 3 && !A1.streamOutput.includes('nq-wait') && A1.streamOutput.includes('data-nq="open"')
    && same(stored, [['responses', 5]]) && N.holds() === false && toasts.length === 2, [pane.innerHTML.slice(-300), stored]);

  // ---- no set made
  const tries = [];
  for (const a of [[200, JSON.stringify({ next: { error: 'The Architect\'s reply could not be read (it holds no JSON object).' } })],
                   [403, { error: 'authorization_failed', message: 'You need $0.010 per query but your balance is $0.00. Please add funds to continue.' }], 'down', [200, '\n']]) {
    answer = a; toasts.length = 0; stored.length = 0;
    doc.dispatch('click', list.querySelectorAll('.it')[1]);
    await tick();
    tries.push([toasts.slice(), pane.querySelectorAll('.nq-set').length, pane.querySelectorAll('.nq-wait').length, stored.length, N.holds()]);
  }
  check('no set made: the reason is said - the server\'s own words, a refusal for the balance, a server that cannot be reached, a stream that ends on nothing - the wait leaves the pane, nothing is kept and '
    + 'nothing is held',
    same(tries, [[['The Architect\'s reply could not be read (it holds no JSON object).'], 1, 0, 0, false], [['You need $0.010 per query but your balance is $0.00. Please add funds to continue.'], 1, 0, 0, false],
                 [['No questions were written: the server could not be reached.'], 1, 0, 0, false], [['No questions were written.'], 1, 0, 0, false]]), tries);
  queryRunning = true; calls.length = 0; toasts.length = 0;
  doc.dispatch('click', list.querySelectorAll('.it')[2]); await tick();
  doc.dispatch('click', pane.querySelector('.nq-card .go')); await tick();
  queryRunning = false;
  check('while an analysis runs no set is asked for and no question is run: that it runs is said', calls.length === 0 && submitted.length === 0 && same(toasts, Array(2).fill('Another analysis is running. Wait for it to end, or stop it.')), toasts);

  // ---- a set that comes back while another chain is on screen
  answer = () => new Promise(r => { release = r; }); calls.length = 0; stored.length = 0;
  doc.dispatch('click', list.querySelectorAll('.it')[2]); await tick();
  view(A2);
  release([200, JSON.stringify({ next: { set: { level: 'test', cost: 0, chain: 1700000078, questions: [{ title: 'The scale', text: 'Was one scale used for both arms?', from: [{ kind: 'anchor', text: 'The scale was the same. (cannot be checked)' }] }] }, at: 1 } })]);
  await tick();
  const elsewhere = pane.querySelectorAll('.nq-set').length, keptSets = el(A1.streamOutput).querySelectorAll('.nq-set').map(s => s.getAttribute('data-set'));
  view(A1);
  check('a set that comes back while another chain is on screen goes to the chain it was asked for - into its kept pane, not the one on screen - and is there when that chain is shown again',
    elsewhere === 0 && same(keptSets, ['0', '1']) && same(pane.querySelectorAll('.nq-set').map(s => s.getAttribute('data-level')), ['emergence', 'test']) && same(stored, [['responses', 5]])
    && pane.querySelectorAll('.nq-set')[1].querySelector('.from .l').textContent === 'From it rests on', [elsewhere, keptSets]);

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
    card3.querySelector('.tx b').textContent === 'The scale.' && card3.querySelector('.q').textContent === 'Was one scale used for both arms?' && !card3.classList.contains('editing') && stored.length === 0, card3.outerHTML);
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
  check('the arrow runs the question as it stands: the page\'s send is given the question, the chain it follows, the set and the question by their places, the level, and where it comes from; a question '
    + 'open for a change is taken as typed, and kept. The composer\'s own words are not touched',
    same(submitted[0], { next: { text: 'Is the gap wider in the last third?', chain: 11, set: 0, k: 0, level: 'emergence', label: 'From did not fit', lines: MISFIT.text } })
    && same(submitted[1], { next: { text: 'Typed, then run at once?', chain: 11, set: 0, k: 2, level: 'emergence', label: '', lines: 'x' } }) && !card2.classList.contains('editing')
    && el(A1.streamOutput).querySelectorAll('.nq-set')[0].querySelectorAll('.nq-card .q')[2].textContent === 'Typed, then run at once?' && $('queryInput').value === 'something the coach was typing'
    && toasts.length === 0, submitted);
  answer = () => new Promise(r => { release = r; }); submitted.length = 0;
  doc.dispatch('click', list.querySelectorAll('.it')[3]); await tick();
  doc.dispatch('click', card0.querySelector('.go'));
  const heldRun = [submitted.length, toasts.slice()];
  release([200, JSON.stringify({ next: { error: 'no' } })]); await tick();
  check('while a set is being written a question is not run: the wait is said', same(heldRun, [0, ['The questions are being written. Wait for them.']]), heldRun);

  // ---- the run it started: the row, the mark on the card, the map
  const live = { status: 'running', chain_id: null, thread_id: 7, parentChainId: 11, queryText: 'Does the gap hold without the two rows?', streamOutput: '' };
  responses.push(live); liveState.running = true; liveState.index = responses.length - 1; currentResponseIndex = liveState.index; pane.innerHTML = ''; rows.length = 0;
  const next = { text: live.queryText, chain: 11, set: 0, k: 1, level: 'emergence', label: 'From the answer and an earlier answer', lines: 'B is above A.\nTwelve rows.' };
  N.started(next);
  const marks = () => el(A1.streamOutput).querySelectorAll('.nq-set').map(s => s.querySelectorAll('.nq-card').map(c => c.querySelectorAll('.was').map(w => w.getAttribute('data-chain')).join('+') + (c.classList.contains('ran') ? '' : '-')));
  const beforeId = marks();      // the third question of the first set came from the server as run
  stored.length = 0;
  N.ran(null); N.ran(1700000100); N.ran(1700000101);
  check('the analysis a question started: the live chain carries what it was started from and its pane opens on the row that says so. Once the server has named the run\'s chain the question\'s card - that '
    + 'set\'s, that question\'s - is marked with it, in the kept pane of the analysis it follows, once; the other cards are as they were',
    live.next === next && rows.length === 1 && el(rows[0]).querySelector('.nq-from').textContent === 'Next question·Follow emergence·From the answer and an earlier answer'
    && same(beforeId, [['-', '-', '1700000099'], ['-']]) && same(marks(), [['-', '1700000100', '1700000099'], ['-']]) && same(stored, [['responses', 6]]) && pane.innerHTML === '', [rows, beforeId, marks()]);
  const done = { chain_id: 1700000100, thread_id: 7, parentChainId: 11, queryText: live.queryText, streamOutput: PANE(rows[0] + DONE) };
  check('the thread map\'s mark: a chain started from a question says next question - while it runs by what it carries, afterwards by the row its kept pane opens on; an analysis typed by the coach says '
    + 'nothing, one framed with the Architect says so',
    N.made(live) === true && N.made(done) === true && N.made(A2) === false && N.made(null) === false && window.ArchitectUI.mark(live) === 'next question' && window.ArchitectUI.mark(done) === 'next question'
    && window.ArchitectUI.mark(A2) === '' && window.ArchitectUI.mark({ tabContent: '<div id="tab-brief" class="tab">Brief</div>', streamOutput: done.streamOutput }) === 'Architect', null);
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
    same(afterEnd, [['-', '1700000100', '1700000099'], ['-']]) && same(went, ['1700000100']) && same(other, [['-', '1700000100', '1700000099'], ['1700000103']])
    && same(marks(), [['-', '1700000104', '1700000099'], ['1700000103']]) && again.querySelectorAll('.was').length === 1 && again.querySelector('.was').getAttribute('data-chain') === '1700000104',
    [afterEnd, went, other, marks()]);

  // ---- the page's hooks, read from the source
  const root = path.join(__dirname, '..', '..', 'web_app'), js = f => fs.readFileSync(path.join(root, 'static', 'js', f), 'utf8'), css = f => fs.readFileSync(path.join(root, 'static', 'css', f), 'utf8');
  const html = fs.readFileSync(path.join(root, 'templates', 'index.html'), 'utf8'), qp = js('query-processing.js');
  check('index.html: the plant and its popover have left the composer; next-questions.js is loaded after the Architect\'s module and before the map\'s; the app starts it',
    !html.includes('suggestQuestions') && !html.includes('branchingSliderPopup') && !html.includes('branching-icon') && html.indexOf('js/next-questions.js') > html.indexOf('js/architect.js')
    && html.indexOf('js/next-questions.js') < html.indexOf('js/workflowGraph.js') && js('core.js').includes('window.NextQuestionsUI.initialize();'));
  check('the send: a next question is the query as it stands - not typed, so the Architect\'s switch does not apply; nothing starts while a set is being written; the run\'s pane is told what started it; '
    + 'the composer is neither cleared nor refilled; the server is told the set and the question; the stream\'s id line marks the card',
    qp.includes("const query = framed ? String(framed.queryText || '').trim() : (next ? String(next.text || '').trim() : queryInput.value.trim());")
    && qp.includes('if (window.NextQuestionsUI && window.NextQuestionsUI.holds()) return;') && qp.indexOf('window.NextQuestionsUI.holds()') < qp.indexOf('window.ArchitectUI.framingInView()')
    && qp.indexOf('window.NextQuestionsUI.holds()') > qp.indexOf('stopAutoExplore();') && qp.includes('if (next) window.NextQuestionsUI.started(next);')
    && qp.indexOf('if (next) window.NextQuestionsUI.started(next);') > qp.indexOf('beginLiveChain(framed);') && qp.includes('if (!synthesis && !next) {') && qp.includes('if (!framed && !next) queryInput.value = query;')
    && qp.includes('if (next) requestBody.next = { set: next.set, k: next.k };') && qp.includes('if (window.NextQuestionsUI) window.NextQuestionsUI.ran(data.chain_id);')
    && qp.indexOf('window.NextQuestionsUI.ran(data.chain_id)') > qp.indexOf("if (data.type === \"id\")") && qp.indexOf('window.NextQuestionsUI.ran(data.chain_id)') < qp.indexOf('data.type === "html"'));
  check('the pane and the map: a finished analysis is dressed when its closing card is made and when its chain is shown again; the map asks the Architect\'s module for the mark, which asks this one',
    js('stream-pane.js').includes('append(build.runEnd(r));\n        if (window.NextQuestionsUI) window.NextQuestionsUI.dress(p);')
    && js('workflow-management.js').includes('if (window.NextQuestionsUI) window.NextQuestionsUI.restore(response);')
    && js('workflow-management.js').indexOf('window.NextQuestionsUI.restore(response)') > js('workflow-management.js').indexOf('reattachRestoredListeners();\n    if (window.ArchitectUI)')
    && js('architect.js').includes("return window.NextQuestionsUI && window.NextQuestionsUI.made(r) ? 'next question' : '';") && js('workflowGraph.js').includes('window.ArchitectUI.mark(resp)'));
  const paneCss = css('pane.css'), shell = css('shell.css');
  check('the stylesheets: the button, a set\'s head, the cards with their pencil, arrow and mark, the editor and the run\'s row in pane.css; the list of levels on the Save menu\'s look in shell.css; the '
    + 'plant\'s and its popover\'s rules are gone',
    ['.sp-done .nq-open {', '.sp-next {', '.nq-head, #streamOutput .nq-from {', '.nq-card {', '.nq-card .go {', '.nq-card .was {', '.nq-card.editing .tx, #streamOutput .nq-card.editing .pen { display: none; }',
     '.nq-input {', '.nq-reading {'].every(r => paneCss.includes('#streamOutput ' + r))
    && shell.includes('.save-menu.nq-menu .it { flex-direction: row;') && !shell.includes('branchingSliderPopup') && !shell.includes('suggest-questions')
    && !css('styles.css').includes('suggest-questions') && !css('styles.css').includes('.branching-icon') && !js('ui-controls.js').includes('SuggestQuestions'));

  finish();
})().catch(e => { check('the module ran without throwing', false, e && e.stack); finish(); });

function finish() {
  let pass = 0, fail = 0;
  for (const [n, c, d] of results) { if (c) pass++; else fail++; console.log((c ? '  ok   ' : '  FAIL ') + n + (c ? '' : '  <- ' + (d === undefined ? '' : JSON.stringify(d)).slice(0, 900))); }
  console.log(`\n${pass} passed, ${fail} failed`);
  process.exit(fail ? 1 : 0);
}
