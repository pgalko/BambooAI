// The report in plain language, written when the person asks for it (web_app/static/js/simplify.js; 2026-11-28 - until
// then every analysis ended with that call). The Answer tab's button says what a click does: Simplify asks the server,
// and once the plain version is there Technical and Simplified switch between the two.
// The module driven on the mini DOM with a scripted server; the left pane is the real one (stream-pane.js), which puts
// the call's card where the run's own end and raises the run's cost and time. Then the page's hooks, read from the
// source. The real thing, in a real browser on the real page, is in tests/e2e/test_stack.py.
// Run: node tests/analyst/test_simplify.js
'use strict';
const fs = require('fs'), path = require('path');
const { makeDocument } = require(path.join(__dirname, 'minidom.js'));
const web = path.join(__dirname, '..', '..', 'web_app');
const js = f => fs.readFileSync(path.join(web, 'static', 'js', f), 'utf8');
const results = []; const check = (n, c, d) => results.push([n, !!c, d]);
const same = (a, b) => JSON.stringify(a) === JSON.stringify(b);
const doc = makeDocument(); global.document = doc;
const calls = []; let answer = null;
// the scripted server: an answer is [status, the text of a stream], 'down', or a promise of one
global.window = { authService: { fetch: async (url, opts) => { calls.push([url, JSON.parse(opts.body)]);
  const a = await (typeof answer === 'function' ? answer() : answer);
  if (a === 'down') throw new Error('offline');
  return { ok: a[0] < 400, status: a[0], text: async () => a[1] }; } } };
const store = {}; global.sessionStorage = { getItem: k => (k in store ? store[k] : null), setItem: (k, v) => { store[k] = String(v); } };
const toasts = []; global.showSystemMessage = t => toasts.push(t);
const stored = []; global.localforage = { setItem: (k, v) => { stored.push([k, v.length]); return Promise.resolve(); } };
global.responses = []; global.currentResponseIndex = -1; global.currentData = {}; global.queryRunning = false; global.liveState = { running: false, index: null };
// the page's markdown, enough of it: a title, a section's heading, paragraphs
global.markdownToHtml = text => String(text).split('\n\n').map(p => (p.startsWith('# ') ? '<h1>' + p.slice(2) + '</h1>' : p.startsWith('## ') ? '<h2>' + p.slice(3) + '</h2>' : '<p>' + p + '</p>')).join('');
const set = []; global.renderLatex = el => set.push(el.innerHTML);
const host = doc.createElement('div'); doc.body.appendChild(host);
host.innerHTML = '<div id="streamOutput"></div><div id="contentOutput"></div>';
const $ = id => doc.getElementById(id);

require(path.join(web, 'static', 'js', 'stream-pane.js'));
require(path.join(web, 'static', 'js', 'architect.js'));
require(path.join(web, 'static', 'js', 'simplify.js'));
global.paneCiteHtml = window.paneCiteHtml; global.paneSourcesHtml = window.paneSourcesHtml;
const S = window.SimplifyUI;
S.initialize();
const tick = async () => { for (let i = 0; i < 8; i++) await new Promise(r => setImmediate(r)); };

// ---- a finished analysis on the page: its pane as the real pane draws it, its Answer tab with the report and the PDF button
const TECH = '<div class="markdown-content content-body"><h1>Regime C yields most</h1><p>Technical: +0.57 t/ha [cell 2].</p></div>';
const PLAIN = '# Regime C yields most\n\nPlain: regime C gives more grain [fig 1].';
function run(status) {                        // one run through the pane, to its closing card
  $('streamOutput').innerHTML = '';
  window.paneRunStart({ mode: 'Deep', of: 15, dollars: 1.5 });
  window.paneTurnStart({ turn: 1, of: 15, seat: 'Analyst', model: 'vendor/analyst', chain_id: 5 });
  window.paneTurnEnd({ turn: 1, kind: 'cell', thinking: 'Compare the regimes.', note: '', code: 'print(1)', elapsed: 5, cost: 0.05 });
  window.paneCell({ cell_no: 1, ok: true, peek: 'done', elapsed: 0.1, chars: 4, figs: 0 });
  window.paneTurnStart({ turn: 2, of: 15, seat: 'Analyst', model: 'vendor/analyst', chain_id: 5 });
  window.paneTurnEnd({ turn: 2, kind: 'report', thinking: '', note: '', code: '', elapsed: 4, cost: 0.05 });
  window.paneLookupStart({ kind: 'replay', query: '1 cells', model: '' });
  window.paneLookup({ kind: 'replay', query: '', peek: 'Replay reproduced the cited results.', sources: [], passages: [] });
  window.paneRunEnd({ status, turns: 2, of: 15, cells: 1, cost: 0.1, seconds: 9, replay_status: 'reproduced', replay_line: 'Replay reproduced the cited results.', chain_id: 5 });
}
function answerTab(buttons) {
  $('contentOutput').innerHTML = '<div id="content-answer" class="tab-content"><div class="tab-header-container"><h3 class="answer-tab-anchor"></h3>'
    + (buttons === false ? '' : '<button class="pdf-export-btn"><span class="pdf-text">PDF</span></button>') + '</div>' + TECH + '</div>';
  return $('content-answer');
}
const CARD = { seat: 'Rewriter', model: 'vendor/flash', elapsed: 4.2, cost: 0.06, chain_id: 5 };
const stream = made => JSON.stringify({ text: 'a token of the call' }) + '\n' + JSON.stringify({ simplify: made }) + '\n';
const button = () => doc.querySelector('.simplified-summary-btn'), word = () => button().querySelector('.simplified-text').textContent;
const click = () => doc.dispatch('click', button().querySelector('.simplified-text'));
const body = () => doc.querySelector('#content-answer .content-body').innerHTML;
const cards = pane => pane.querySelector('.sp-stream').elements.map(e => (e.classList.contains('sp-turn') ? 'turn ' + e.getAttribute('data-turn') : e.className));
const sums = pane => [pane.querySelector('.sp-done .nums').textContent, pane.querySelector('.sp-strip .spent').textContent];
const holder = html => { const d = doc.createElement('div'); d.innerHTML = html; return d; };

(async () => {
  // ---- the button: where it stands, and what it says
  run('answered');
  let tab = answerTab();
  const A = { chain_id: 5, thread_id: 't1', streamOutput: $('streamOutput').innerHTML, contentOutput: $('contentOutput').innerHTML, simplifiedAnswer: null };
  const B = { chain_id: 6, thread_id: 't1', streamOutput: '<div class="sp-strip"></div><div class="sp-stream"><div class="sp-done"><div class="head"><span class="nums"></span></div><div class="acts"></div></div></div>', contentOutput: '', simplifiedAnswer: null };
  responses.push(A, B); currentResponseIndex = 0;
  Object.assign(currentData, { chain_id: 5, thread_id: 't1', technicalAnswer: TECH, simplifiedAnswer: null, summaryViewMode: 'technical', reportHead: { sources: [] } });
  S.dress(tab);
  check('an analysis that ended with a report has the button in its Answer tab, before PDF: it says Simplify, with what that does as its hover, and is still',
    tab.querySelector('.tab-header-container').elements.map(e => e.className).join('|') === 'answer-tab-anchor|simplified-summary-btn|pdf-export-btn' && word() === 'Simplify'
    && button().title === 'Write this report in plain language' && button().getAttribute('aria-label') === button().title && button().getAttribute('type') === 'button'
    && !button().classList.contains('loading') && !button().disabled && button().querySelector('svg.simplified-icon') && button().querySelector('.simplified-spinner'), tab.querySelector('.tab-header-container').innerHTML);
  S.dress(tab);
  check('dressed again, the tab has its one button', tab.querySelectorAll('.simplified-summary-btn').length === 1);
  const none = [];
  run('asked'); S.dress(answerTab()); none.push(!!button());                       // the analyst asked a question: no report
  run('stopped'); S.dress(answerTab()); none.push(!!button());
  run('answered'); S.dress(answerTab(false)); none.push(!!button());               // an answer without its PDF button: no header to stand in
  window.RoutinesUI = { inRunView: () => true }; currentData.simplifiedAnswer = PLAIN;
  S.dress(answerTab()); none.push(!!button());                                     // a routine's run in the pane: the Answer tab is the run's
  window.RoutinesUI = { inRunView: () => false };
  $('streamOutput').innerHTML = '<div>a pane kept from before the cards</div>';     // a plain version at hand: the button switches to it, whatever the pane holds
  S.dress(answerTab()); none.push(word(), button().title);
  currentData.summaryViewMode = 'simplified'; S.dress(tab = answerTab()); none.push(word(), button().title);
  check('no button where there is nothing to rewrite - a run that asked, a run that was stopped - nor without the PDF button\'s header, nor in a routine\'s run view; with a plain version at hand the button '
    + 'is there whatever the pane holds, and says the version a click brings: Simplified over the technical report, Technical over the plain one',
    same(none, [false, false, false, false, 'Simplified', 'Show the plain-language version', 'Technical', 'Show the technical report']), none);
  Object.assign(currentData, { simplifiedAnswer: null, summaryViewMode: 'technical' });

  // ---- asked for: one request, the button turning meanwhile, nothing else beside it
  run('answered'); S.dress(tab = answerTab());
  const before = { cards: cards($('streamOutput')), sums: sums($('streamOutput')) };
  let release; answer = () => new Promise(r => { release = () => r([200, stream({ text: PLAIN, card: CARD })]); });
  click(); await tick();
  const during = [same(calls, [['/simplify', { thread_id: 't1', chain_id: 5 }]]), button().classList.contains('loading'), button().disabled, word(), S.holds(), toasts.slice(), body() === holder(TECH).querySelector('.content-body').innerHTML];
  const quiet = toasts.length;
  click(); await tick();                                                           // the button is still: a click on it does nothing, and says nothing
  check('a click on Simplify asks the server once, for the chain on screen. While the plain version is written the button turns and takes no click, the report stays, and the module holds what would '
    + 'start beside it, saying why',
    same(during, [true, true, true, 'Simplify', true, ['The plain-language version is being written. Wait for it.'], true]) && calls.length === 1 && toasts.length === quiet, [during, toasts]);
  check('before the plain version arrives the pane is the run\'s own: its two turns, the row under the first, the replay\'s row, the closing card', same(before.cards, ['turn 1', 'sp-row', 'turn 2', 'sp-row tool', 'sp-done'])
    && same(before.sums, ['2 of 15 turns · 1 cell · $0.10 · 9.0 s', '$0.10']), before);
  toasts.length = 0; release(); await tick();
  const late = $('streamOutput').querySelector('.sp-turn[data-turn="rewrite"]');
  check('the plain version is shown as soon as it arrives - its title, its figure citation a chip - and the button now says Technical; nothing is said; the maths is set in it',
    body() === '<h1>Regime C yields most</h1><p>Plain: regime C gives more grain ' + window.paneCite('fig', '1') + '.</p>' && currentData.summaryViewMode === 'simplified' && currentData.simplifiedAnswer === PLAIN
    && word() === 'Technical' && button().title === 'Show the technical report' && !button().classList.contains('loading') && !button().disabled && !S.holds() && toasts.length === 0 && set[set.length - 1] === body(), [body(), word(), toasts]);
  check('the call is the analysis\' own: its card stands in the left pane where the run\'s own cards end - before the replay\'s row and the closing card -, shut, as a turn\'s that has ended: Rewrite, what it '
    + 'is, what it took and cost, what it wrote inside, and the button to its prompt in the run log',
    same(cards($('streamOutput')), ['turn 1', 'sp-row', 'turn 2', 'turn rewrite', 'sp-row tool', 'sp-done']) && late.className === 'sp-turn' && !late.hasAttribute('open')
    && late.querySelector('summary .n').textContent === 'Rewrite' && late.querySelector('summary .kind').textContent === 'plain-language version' && late.querySelector('summary .meta').textContent === '4.2 s · $0.06'
    && late.querySelector('.sp-think').textContent === PLAIN && late.getAttribute('data-kind') === 'rewrite'
    && same(['data-agent', 'data-chain', 'data-call'].map(a => late.querySelector('.sp-prompt').getAttribute(a)), ['Rewriter', '5', '1']), late.outerHTML);
  check('the run\'s cost and time are raised by the call\'s where the pane says them: on the closing card and on the strip',
    same(sums($('streamOutput')), ['2 of 15 turns · 1 cell · $0.16 · 13 s', '$0.16']), sums($('streamOutput')));
  check('the chain keeps it: the plain version, and its pane with the call\'s card - written to the page\'s store',
    A.simplifiedAnswer === PLAIN && A.streamOutput === $('streamOutput').innerHTML && holder(A.streamOutput).querySelectorAll('.sp-turn[data-turn="rewrite"]').length === 1 && same(stored[stored.length - 1], ['responses', 2]), stored);

  // ---- then the button switches between the two versions, with no call
  const seen = [];
  click(); await tick(); seen.push(word(), button().title, currentData.summaryViewMode, body() === holder(TECH).querySelector('.content-body').innerHTML);
  click(); await tick(); seen.push(word(), currentData.summaryViewMode, body().includes('Plain: regime C'));
  check('with the plain version there, a click brings the technical report back as it was drawn, and the next one the plain version again - no request is made',
    same(seen, ['Simplified', 'Show the plain-language version', 'technical', true, 'Technical', 'simplified', true]) && calls.length === 1, seen);
  const kept = body();
  currentData.technicalAnswer = null; click(); await tick();
  check('a chain whose technical report the page did not keep: the text stays as it is', body() === kept && currentData.summaryViewMode === 'technical', body());
  currentData.technicalAnswer = TECH;

  // ---- what the plain version is drawn from: the report's sources, the part against the brief cut
  const drawn = S.build.plain('# T\n\nPlain: it rose [1].\n\n## Against the brief\n\n- Expected: met.\n\n## Did not fit\n\nNothing.', [{ n: 1, title: 'A page', url: 'https://example.org/a', host: 'example.org' }]);
  check('the plain version as the tab shows it: a source it cites by number is a chip that opens the page, the report\'s Sources stand under it, and what it says against the brief is cut, as in the technical report - '
    + 'the part that follows it stays',
    drawn.includes('<a class="cite web" href="https://example.org/a"') && drawn.endsWith(window.paneSourcesHtml([{ n: 1, title: 'A page', url: 'https://example.org/a', host: 'example.org' }]))
    && !drawn.includes('Against the brief') && !drawn.includes('Expected: met') && drawn.includes('<h2>Did not fit</h2><p>Nothing.</p>') && same(S.build.plain('# T\n\nPlain.', []), '<h1>T</h1><p>Plain.</p>'), drawn);

  // ---- no plain version came back: the reason is said, and the button asks again
  const said = [];
  for (const a of [[200, stream({ error: 'No plain-language version was written: the model\'s reply was empty' })], 'down', [401, JSON.stringify({ error: 'Sign in again.' })], [200, stream({ text: '' })], [200, '']]) {
    Object.assign(currentData, { simplifiedAnswer: null, summaryViewMode: 'technical' }); run('answered'); S.dress(tab = answerTab());
    toasts.length = 0; answer = a; click(); await tick();
    said.push([toasts.slice(), word(), button().classList.contains('loading'), button().disabled, S.holds(), currentData.simplifiedAnswer, cards($('streamOutput')).includes('turn rewrite')]);
  }
  const back = ['Simplify', false, false, false, null, false];
  check('where none was written the reason is said - the server\'s, that it could not be reached, a refusal\'s - or, where nothing says why, that none was written; the button is Simplify again, still, and '
    + 'nothing is held; the pane and the chain are as they were',
    same(said, [[['No plain-language version was written: the model\'s reply was empty'], ...back], [['No plain-language version was written: the server could not be reached.'], ...back],
                [['Sign in again.'], ...back], [['No plain-language version was written.'], ...back], [['No plain-language version was written.'], ...back]]), said);

  // ---- not while something else is being written
  const n0 = calls.length, refused = [];
  toasts.length = 0; queryRunning = true; click(); await tick(); refused.push(toasts.slice(), calls.length - n0); queryRunning = false;
  toasts.length = 0; window.NextQuestionsUI = { holds: () => { toasts.push('questions'); return true; } }; click(); await tick(); refused.push(toasts.slice(), calls.length - n0); delete window.NextQuestionsUI;
  toasts.length = 0; window.ExplainUI = { holds: () => { toasts.push('explanation'); return true; } }; click(); await tick(); refused.push(toasts.slice(), calls.length - n0); delete window.ExplainUI;
  responses[0] = Object.assign({}, A, { status: 'running' }); toasts.length = 0; click(); await tick(); refused.push(toasts.slice(), calls.length - n0);
  responses[0] = Object.assign({}, A, { chain_id: null }); click(); await tick(); refused.push(calls.length - n0);
  responses[0] = A;
  check('no request while an analysis runs - that is said - nor while next questions or an explanation are being written, which say so themselves; none for a chain that has not ended, or one that is no chain of a thread',
    same(refused, [['An analysis is running. Wait for it to end, or stop it.'], 0, ['questions'], 0, ['explanation'], 0, [], 0, 0]), refused);

  // ---- the person went to another chain meanwhile: it is done to the chain's kept copy
  Object.assign(A, { simplifiedAnswer: null }); run('answered'); A.streamOutput = $('streamOutput').innerHTML;
  Object.assign(currentData, { simplifiedAnswer: null, summaryViewMode: 'technical' }); S.dress(tab = answerTab());
  answer = () => new Promise(r => { release = () => r([200, stream({ text: PLAIN, card: CARD })]); });
  click(); await tick();
  currentResponseIndex = 1; $('streamOutput').innerHTML = B.streamOutput;          // chain B on screen, with its own pane and Answer tab
  Object.assign(currentData, { chain_id: 6, simplifiedAnswer: null, summaryViewMode: 'technical' }); S.dress(tab = answerTab());
  const away = [word(), button().classList.contains('loading'), S.holds()];
  toasts.length = 0; click(); await tick();                                         // Simplify on B while A's is written: one at a time
  away.push(toasts.slice(), calls.filter(c => c[1].chain_id === 6).length);
  const paneB = $('streamOutput').innerHTML, bodyB = body();
  release(); await tick();
  const keptA = holder(A.streamOutput);
  check('gone to another chain while the plain version is written: that chain\'s button is its own - Simplify, still - and a click on it says one is being written. What arrives goes to the chain it was '
    + 'asked for, in its kept copy: the plain version, the call\'s card in its place, its sums raised. The chain on screen is as it was',
    same(away, ['Simplify', false, true, ['The plain-language version is being written. Wait for it.'], 0]) && A.simplifiedAnswer === PLAIN && same(cards(keptA), ['turn 1', 'sp-row', 'turn 2', 'turn rewrite', 'sp-row tool', 'sp-done'])
    && same(sums(keptA), ['2 of 15 turns · 1 cell · $0.16 · 13 s', '$0.16']) && $('streamOutput').innerHTML === paneB && body() === bodyB && currentData.simplifiedAnswer === null && B.simplifiedAnswer === null
    && word() === 'Simplify' && !S.holds(), [away, cards(keptA), sums(keptA)]);

  // ---- a plain version the server had kept, asked for again: no second card, the sums not raised again
  currentResponseIndex = 0; $('streamOutput').innerHTML = A.streamOutput; A.simplifiedAnswer = null;
  Object.assign(currentData, { chain_id: 5, simplifiedAnswer: null, summaryViewMode: 'technical' }); S.dress(tab = answerTab());
  answer = [200, stream({ text: PLAIN, card: CARD })]; click(); await tick();
  check('the server keeps the plain version and gives it again when asked: a pane that has the call\'s card gets no second one, and its sums stay; the plain version is shown',
    $('streamOutput').querySelectorAll('.sp-turn[data-turn="rewrite"]').length === 1 && same(sums($('streamOutput')), ['2 of 15 turns · 1 cell · $0.16 · 13 s', '$0.16']) && currentData.summaryViewMode === 'simplified' && word() === 'Technical',
    sums($('streamOutput')));

  // ---- the library that sets the formulas did not load: the plain version stands all the same
  Object.assign(A, { simplifiedAnswer: null }); run('answered'); A.streamOutput = $('streamOutput').innerHTML;
  Object.assign(currentData, { simplifiedAnswer: null, summaryViewMode: 'technical' }); S.dress(tab = answerTab());
  const lost = [], onLost = e => lost.push(String(e && e.message)), setLatex = global.renderLatex, n1 = stored.length;
  process.on('unhandledRejection', onLost);
  global.renderLatex = () => { throw new Error('the formulas\' library is not there'); };
  answer = [200, stream({ text: PLAIN, card: CARD })]; click(); await tick();
  global.renderLatex = setLatex; process.removeListener('unhandledRejection', onLost);
  check('where the formulas cannot be set - their library did not load - the plain version is shown and kept all the same, and the button is Technical, still: the failure is the library\'s to report',
    body().includes('Plain: regime C') && currentData.summaryViewMode === 'simplified' && word() === 'Technical' && !button().classList.contains('loading') && !button().disabled && !S.holds()
    && A.simplifiedAnswer === PLAIN && stored.length === n1 + 1 && same(lost, ['the formulas\' library is not there']), [word(), lost, stored.length - n1]);

  // ---- the page's hooks, from the source
  const html = fs.readFileSync(path.join(web, 'templates', 'index.html'), 'utf8'), core = js('core.js'), pdf = js('pdf-export.js'), qp = js('query-processing.js'), nq = js('next-questions.js');
  const wm = js('workflow-management.js'), all = fs.readdirSync(path.join(web, 'static', 'js')).filter(f => f.endsWith('.js'));
  check('the page loads the module after the pane and the Pathfinder\'s, whose stream reader it uses, and starts it; the button is put where an answer\'s buttons are, after PDF\'s own',
    html.indexOf("js/simplify.js') }}") > html.indexOf("js/stream-pane.js') }}") && html.indexOf("js/simplify.js') }}") > html.indexOf("js/architect.js') }}") && html.indexOf("js/stream-pane.js') }}") > 0
    && core.includes("if (typeof window.SimplifyUI !== 'undefined' && typeof window.SimplifyUI.initialize === 'function') {\n        window.SimplifyUI.initialize();")
    && pdf.includes('addPDFExportButton(answerTab);\n            if (window.SimplifyUI) window.SimplifyUI.dress(answerTab);'));
  check('nothing starts beside a plain version being written: the query box asks the module before anything is sent, and so do the next questions',
    qp.includes('if (window.SimplifyUI && window.SimplifyUI.holds()) return;') && qp.indexOf('window.SimplifyUI.holds()') < qp.indexOf('window.SelectionUI.send(query)')
    && nq.includes('if (window.SimplifyUI && window.SimplifyUI.holds()) return Promise.resolve(false);'));
  const old = all.filter(f => /simplified_answer|addSimplifiedSummaryButton|updateSimplifiedButton|handleSimplifiedSummaryToggle|createSimplifiedSummaryButton/.test(js(f)));
  check('the plain version is the module\'s alone: no analysis sends one with its answer any more, and the page\'s older code for the button - in the renderer, the stream\'s reader and the chain\'s restore - is gone; '
    + 'a new answer still starts with no plain version',
    same(old, []) && same(all.filter(f => js(f).includes('simplified-summary-btn')), ['simplify.js']) && !/Simplified/.test(wm)
    && qp.includes("if (data.type === 'answer') {\n                        currentData.simplifiedAnswer = null;\n                        currentData.summaryViewMode = 'technical';"), old);

  let fails = 0; for (const [n, ok, d] of results) { console.log((ok ? '  ok   ' : '  FAIL ') + n + (ok ? '' : '  <- ' + JSON.stringify(d))); if (!ok) fails++; }
  console.log(`\n${results.length - fails} passed, ${fails} failed`); process.exit(fails ? 1 : 0);
})();
