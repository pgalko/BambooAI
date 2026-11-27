// A passage explained where it stands (web_app/static/js/explain.js; 2026-11-27, the product owner's pick of the
// mockups: the note under the text): a question about a selection is answered by one call, the passage stays marked,
// and what was asked about it stands in a note under it.
// The module's pure parts, and the module driven on the mini DOM with a scripted server and stand-ins for what the
// mini DOM has not - the browser's selection as a range over the page's texts, the watch on the tabs. Then the
// page's hooks, read from the source. The real thing, in a real browser on the real page, is tests/e2e/test_selection.py.
// Run: node tests/analyst/test_explain.js
'use strict';
const fs = require('fs'), path = require('path');
const { makeDocument } = require(path.join(__dirname, 'minidom.js'));
const web = path.join(__dirname, '..', '..', 'web_app');
const js = f => fs.readFileSync(path.join(web, 'static', 'js', f), 'utf8'), css = f => fs.readFileSync(path.join(web, 'static', 'css', f), 'utf8');
const html = fs.readFileSync(path.join(web, 'templates', 'index.html'), 'utf8');
const results = []; const check = (n, c, d) => results.push([n, !!c, d]);
const same = (a, b) => JSON.stringify(a) === JSON.stringify(b);
const doc = makeDocument(); global.document = doc;
global.NodeFilter = { SHOW_TEXT: 4 };

// ---- the browser's selection: a range from a character of one text to a character of another, over the page's texts
const texts = (n = doc.body, all = []) => { for (const c of n.children) { if (c.nodeType === 3) all.push(c); else texts(c, all); } return all; };
const hidden = t => { for (let e = t.parent; e; e = e.parent) if (e.hidden) return true; return false; };
function range(a, ao, z, zo) {
  const at = (node, off) => [texts().indexOf(node), off], order = (p, q) => p[0] - q[0] || p[1] - q[1];
  const up = n => { const out = []; for (; n; n = n.parent) out.push(n); return out; };
  return {
    get commonAncestorContainer() { return a === z ? a : up(z).find(n => up(a).includes(n)); },
    comparePoint: (node, off) => (order(at(node, off), at(a, ao)) < 0 ? -1 : order(at(node, off), at(z, zo)) > 0 ? 1 : 0),
    intersectsNode: node => (node.nodeType === 3 ? [node] : texts(node)).some(t => order(at(t, t.data.length), at(a, ao)) > 0 && order(at(t, 0), at(z, zo)) < 0),
    // the words selected, as the browser gives them: none of what is hidden
    toString: () => { const all = texts(); return all.slice(all.indexOf(a), all.indexOf(z) + 1).filter(t => !hidden(t)).map(t => t.data.slice(t === a ? ao : 0, t === z ? zo : t.data.length)).join(''); },
  };
}
let picked = null;
// a phrase selected under an element: its n-th occurrence in the element's text as it is written
function pick(root, phrase, nth = 0) {
  const all = texts(root), raw = all.map(t => t.data).join('');
  let k = -1;
  for (let i = 0; i <= nth; i++) { k = raw.indexOf(phrase, k + 1); if (k < 0) throw new Error('not in the text: ' + phrase); }
  const point = (off, end) => { let sum = 0; for (const t of all) { if (off < sum + t.data.length || (end && off === sum + t.data.length)) return [t, off - sum]; sum += t.data.length; } throw new Error('past the text'); };
  picked = range(...point(k, false), ...point(k + phrase.length, true));
  return picked;
}
const selection = { toString: () => (picked ? picked.toString() : ''), get rangeCount() { return picked ? 1 : 0; }, getRangeAt: () => picked };

// ---- the scripted server: the next request is answered by `server`; a stream is fed and ended by the suite
const calls = []; let server = () => Promise.reject(new Error('offline'));
global.window = { getSelection: () => selection, authService: { fetch: (url, opts) => { calls.push([url, opts ? JSON.parse(opts.body) : null]); return server(url); } } };
function stream() {
  const parts = [], waiting = [], give = part => (waiting.length ? waiting.shift()(part) : parts.push(part));
  return { line: d => give({ value: Buffer.from(JSON.stringify(d) + '\n'), done: false }), end: () => give({ done: true }),
           response: { ok: true, status: 200, body: { getReader: () => ({ read: () => (parts.length ? Promise.resolve(parts.shift()) : new Promise(r => waiting.push(r))) }) } } };
}
const whole = (status, body) => Promise.resolve({ ok: status < 400, status, json: async () => body, text: async () => (typeof body === 'string' ? body : JSON.stringify(body)) });
const said = []; global.showSystemMessage = t => said.push(t);
const set = []; global.renderLatex = el => set.push(el);
// the page's watch on the tabs: what is watched, the callback for the suite to call as the browser would, and how often
// the module took the records of its own writes off it
const watch = { taken: 0 }; global.MutationObserver = class { constructor(fn) { watch.fn = fn; } observe(el, how) { watch.on = el; watch.how = how; } takeRecords() { watch.taken += 1; return []; } };
let walked = 0; const walker = doc.createTreeWalker; doc.createTreeWalker = (...a) => { walked += 1; return walker(...a); };

// ---- content-rendering.js's Markdown as HTML, the function itself: with the stand-in for marked the page's pictures use
const cr = js('content-rendering.js'), fn = name => cr.match(new RegExp('\\nfunction ' + name + '\\([^)]*\\) \\{[\\s\\S]*?\\n\\}\\n'))[0];
const lib = {}; new Function('window', fs.readFileSync(path.join(__dirname, '..', '..', 'tools', 'fixtures', 'marked_stub.js'), 'utf8'))(lib);
global.protectLatexDelimiters = new Function(fn('protectLatexDelimiters') + '; return protectLatexDelimiters;')();
global.markdownToHtml = new Function('marked', fn('protectLatexDelimiters') + fn('restoreLatexDelimiters') + fn('markdownToHtml') + '; return markdownToHtml;')(lib.marked);
check('content-rendering.js markdownToHtml: Markdown as the page\'s HTML, what stands between LaTeX delimiters kept from the parser; what is done to the HTML is done before the formulas are put back',
  markdownToHtml('The **mean** \\(\\bar{x}_{**}\\) of `yield`.') === '<p>The <strong>mean</strong> \\(\\bar{x}_{**}\\) of <code>yield</code>.</p>'
  && markdownToHtml('a \\(x_1\\) b', h => h.toUpperCase()) === '<P>A \\(x_1\\) B</P>', [markdownToHtml('The **mean** \\(\\bar{x}_{**}\\) of `yield`.'), markdownToHtml('a \\(x_1\\) b', h => h.toUpperCase())]);

// ---- the page, as far as the module reaches: the tabs of a finished analysis, each with its text as content-rendering.js draws it
const REPORT = '<h1>Yield under the three watering regimes</h1>\n<p>Regime B gave the highest yield. On sand the two <strong>cannot be told</strong> apart.</p>\n'
  + '<ul>\n<li>On loam the lead is clear.</li>\n<li>On clay the lead is clear.</li>\n</ul>\n<table><tr><td>regime B</td><td>6.54</td></tr></table>\n<p>The interval excludes zero.</p>\n'
  + '<div class="sp-sources"><span>Cell 2</span></div>';
const PLAIN = '<p>Regime B did best. On sand nobody can say which is better.</p>\n';
const CODE = 'import pandas as pd\nmeans = df.groupby(\'regime\')[\'yield\'].mean()\nprint(means)\ngap = means[\'B\'] - means[\'A\']';
const LIT = 'import pandas <span class="hljs-keyword">as</span> pd\nmeans = df.<span class="hljs-title">groupby</span>(<span class="hljs-string">\'regime\'</span>)[<span class="hljs-string">\'yield\'</span>].mean()\n'
  + '<span class="hljs-built_in">print</span>(means)\ngap = means[<span class="hljs-string">\'B\'</span>] - means[<span class="hljs-string">\'A\'</span>]';
const PRINTED = 'mean yield by regime, t/ha\n  A : 6.12\n  B : 6.54\n';
const host = doc.createElement('div'); doc.body.appendChild(host);
host.innerHTML = '<div id="contentOutput"><div id="content-answer" class="tab-content"><h3 class="answer-tab-anchor"></h3><div class="markdown-content content-body">' + REPORT + '</div></div>'
  + '<div id="content-code" class="tab-content"><h3>Code:</h3><div class="markdown-content"><div class="code-header"><span class="language-label">PYTHON</span></div><pre><code class="language-python">' + CODE + '</code></pre></div></div>'
  + '<div id="content-code_exec_results" class="tab-content"><h3>Results:</h3><div class="markdown-content"><pre><code class="language-plaintext">' + PRINTED + '</code></pre></div></div>'
  + '<div id="content-plot" class="tab-content"><div class="markdown-content"><p>Yield by regime</p></div></div></div>';
const $ = id => doc.getElementById(id);
const text = tab => doc.querySelector('#content-' + tab + ' .markdown-content');
global.responses = [{ chain_id: 7, thread_id: 3 }]; global.currentResponseIndex = 0; global.currentData = { summaryViewMode: 'technical' }; global.queryRunning = false;

require(path.join(web, 'static', 'js', 'architect.js'));      // the stream's reader
require(path.join(web, 'static', 'js', 'explain.js'));
const E = window.ExplainUI, b = E.build;
E.initialize();
const tick = (ms = 5) => new Promise(r => setTimeout(r, ms));
const marks = (root = doc) => root.querySelectorAll('.xp-mark').map(m => m.dataset.k + (m.classList.contains('lost') ? ' lost' : '') + ':' + m.textContent);
const note = () => doc.querySelector('.xp-note');
const folds = () => (note() ? note().querySelectorAll('details').map(d => [d.querySelector('summary').textContent, d.hasAttribute('open'), d.classList.contains('live'), d.querySelector('.a').innerHTML]) : null);
const click = async el => { doc.dispatch('click', el); await tick(); };
const drawn = async (...targets) => { watch.fn(targets.map(target => ({ target }))); await tick(); };      // the browser tells the watch what was drawn in
// a question asked about a selection and answered: the exchange as the server keeps it, with everything asked before
const kept = [];
async function asked(where, question, answer) {
  const s = stream(); server = () => Promise.resolve(s.response);
  E.ask(where, question);
  await tick();
  kept.push(Object.assign({ tab: where.tab, view: where.view, passage: where.passage, at: where.at, quote: where.quote, question, answer, cost: 0.004, when: 1, chain: 900 + kept.length }));
  s.line({ explain: { asked: kept.slice() } }); s.end();
  await tick();
}

(async () => {
  // ------------------------------------------------------------ the builders
  check('a question and its answer are a fold, the question its line: the answer as Markdown; the newest of a note open',
    b.asked({ question: 'Why <b>?', answer: 'It is **so**.' }, true) === '<details open><summary>Why &lt;b&gt;?</summary><div class="a"><p>It is <strong>so</strong>.</p></div></details>'
    && b.asked({ question: 'Why?', answer: 'So.' }, false) === '<details><summary>Why?</summary><div class="a"><p>So.</p></div></details>', b.asked({ question: 'Why <b>?', answer: 'It is **so**.' }, true));
  check('an answer still being written: as plain text, as far as it has come, and the fold says so',
    b.asked({ question: 'Why?', answer: ' It <is> **so', live: true }, true) === '<details open class="live"><summary>Why?</summary><div class="a">It &lt;is&gt; **so</div></details>', b.asked({ question: 'Why?', answer: ' It <is> **so', live: true }, true));
  check('a note: every question asked at its passage, in order, the newest open',
    b.note({ asked: [{ question: 'One?', answer: 'A.' }, { question: 'Two?', answer: 'B.' }] }) === '<details><summary>One?</summary><div class="a"><p>A.</p></div></details><details open><summary>Two?</summary><div class="a"><p>B.</p></div></details>');
  const gone = { passage: 'a <b', asked: [{ quote: 'a <\n  b' }, { quote: 'words selected later, in its note' }] };
  check('the mark of a passage its tab no longer has: the words first selected there, on one line', b.lost(gone, 2) === '<mark class="xp-mark lost" data-k="2">a &lt; b</mark>', b.lost(gone, 2));

  // ------------------------------------------------------------ where a selection can be asked about
  check('started: the tabs are watched for what is drawn into them', watch.on === $('contentOutput') && same(watch.how, { childList: true, subtree: true }) && !marks().length && !note());
  const HERE = { chain: 7, thread: 3 };
  const first = E.place(pick(text('answer'), 'cannot be told apart'));
  check('a selection in the Answer tab\'s text: the analysis on screen, the words selected, and where the passage stands - the tab, which of its two versions, the passage and which of its occurrences. '
    + 'A passage runs through the elements of its text', same(first, Object.assign({}, HERE, { quote: 'cannot be told apart', tab: 'answer', view: 'technical', passage: 'cannot be told apart', at: 0 })), first);
  const twice = [E.place(pick(text('answer'), 'the lead is clear')), E.place(pick(text('answer'), 'the lead is clear', 1))].map(p => p && [p.passage, p.at]);
  check('a passage the text has twice: which of the two it is', same(twice, [['the lead is clear', 0], ['the lead is clear', 1]]), twice);
  const across = E.place(pick(text('answer'), 'apart.</p>\n<ul>\n<li>On loam'.replace(/<[^>]+>/g, '')));
  check('a selection across two blocks: the words as the browser gives them, the passage with every run of white space as one space',
    across && across.quote === 'apart.\n\nOn loam' && across.passage === 'apart. On loam' && across.at === 0, across);
  const blanks = E.place(pick(text('answer'), ' two '));
  check('the blanks at a selection\'s ends are no part of the passage', blanks && blanks.quote === 'two' && blanks.passage === 'two' && blanks.at === 0, blanks);
  const tabs = [E.place(pick(text('code'), 'groupby(\'regime\')')), E.place(pick(text('code_exec_results'), 'B : 6.54'))].map(p => p && [p.tab, p.view, p.passage, p.at]);
  check('the Code and the Results tab: a passage of the script, of what it printed; these tabs have one version', same(tabs, [['code', '', 'groupby(\'regime\')', 0], ['code_exec_results', '', 'B : 6.54', 0]]), tabs);
  currentData.summaryViewMode = 'simplified';
  const plainView = E.place(pick(text('answer'), 'the two'));
  currentData.summaryViewMode = 'technical';
  check('the Answer tab in plain language: a passage of that version', plainView && plainView.view === 'simplified' && plainView.tab === 'answer', plainView);
  const none = {};
  none.plots = E.place(pick(text('plot'), 'Yield by regime'));
  none.heading = E.place(pick($('content-code_exec_results'), 'Results:'));
  none.blank = E.place(pick(text('answer'), '\n\n'));
  queryRunning = true; none.running = E.place(pick(text('answer'), 'cannot be told apart')); none.standsRunning = E.stands(HERE); queryRunning = false;
  responses[0].status = 'running'; none.live = E.place(pick(text('answer'), 'cannot be told apart')); none.standsLive = E.stands(HERE); delete responses[0].status;
  responses[0].chain_id = null; none.chain = E.place(pick(text('answer'), 'cannot be told apart')); responses[0].chain_id = 7;
  responses[0].thread_id = null; none.thread = E.place(pick(text('answer'), 'cannot be told apart')); responses[0].thread_id = 3;
  currentResponseIndex = -1; none.nothing = E.place(pick(text('answer'), 'cannot be told apart')); currentResponseIndex = 0;
  check('nothing can be asked about a selection on the Plots tab, outside a tab\'s text, of blanks alone; nor while an analysis runs, on a chain that has not ended, on one without its chain or its thread, '
    + 'on an empty page', Object.values(none).every(v => !v) && Object.keys(none).length === 10, none);
  check('a place stands while the analysis it was taken in is the finished one on screen', E.stands(HERE) && E.stands({ chain: '7' }) && !E.stands({ chain: 8 }));
  window.RoutinesUI = { inRunView: () => true };
  const inRun = [E.place(pick(text('answer'), 'cannot be told apart')), E.stands(HERE)];
  window.RoutinesUI = { inRunView: () => false };
  check('a routine\'s run shown in the pane is no analysis to ask about: the chain behind it is not on screen', same(inRun, [null, false]) && !!E.place(pick(text('answer'), 'cannot be told apart')) && E.stands(HERE), inRun);

  // ------------------------------------------------------------ a question asked
  const QUESTION = 'Why can they not be told apart?', ANSWER = 'On sand the gap between the two is smaller than its `noise`.';
  const s1 = stream(); server = () => Promise.resolve(s1.response);
  const taken0 = watch.taken;
  E.ask(first, QUESTION);
  const atOnce = [marks(), folds(), note() && note().previousSibling.tag, note() && note().parent === text('answer'), calls.slice()];
  check('a question asked: at once the passage is marked - each part of it in its own element -, and its note is open under the paragraph, on the question; the server is asked with the place, the words and the question',
    same(atOnce, [['0:cannot be told', '0: apart'], [[QUESTION, true, true, '']], 'p', true,
                  [['/explain', { thread_id: 3, chain_id: 7, tab: 'answer', view: 'technical', passage: 'cannot be told apart', at: 0, quote: 'cannot be told apart', question: QUESTION }]]]), atOnce);
  check('... and the paragraph reads as it did', text('answer').querySelector('p').textContent === 'Regime B gave the highest yield. On sand the two cannot be told apart.' && text('answer').querySelector('strong').textContent === 'cannot be told');
  const held = [E.holds(), said.slice()];
  E.ask(E.place(pick(text('answer'), 'The interval')), 'And this?');
  check('while an explanation is written nothing else starts: the page is told so, in words, and a second question is not sent', same(held, [true, ['An explanation is being written. Wait for it.']]) && calls.length === 1 && marks().length === 2, [held, calls.length]);
  const noteWas = note();
  s1.line({ thought: 'reading the report' }); s1.line({ text: ' On sand ', chain_id: 900 }); await tick();
  const part1 = folds();
  s1.line({ text: 'the <gap>', chain_id: 900 }); await tick();
  const part2 = [folds(), note() === noteWas, watch.taken > taken0, set.length];
  check('the answer is shown as it is written: plain text, in the note as it stands - nothing is drawn again -, and the watch is not told of the module\'s own writes',
    same(part1, [[QUESTION, true, true, 'On sand']]) && same(part2, [[[QUESTION, true, true, 'On sand the &lt;gap&gt;']], true, true, 1]), [part1, part2]);
  const X1 = { tab: 'answer', view: 'technical', passage: 'cannot be told apart', at: 0, quote: 'cannot be told apart', question: QUESTION, answer: ANSWER, cost: 0.004, when: 1, chain: 900 };
  kept.push(X1);
  s1.line({ explain: { asked: [X1] } }); s1.end(); await tick();
  const done = [folds(), marks(), E.holds(), said.length, set[set.length - 1] === note()];
  check('the stream\'s last line is everything asked about the analysis, as the server keeps it: the note is drawn from it - the answer as Markdown, its formulas set -, and the page is free again',
    same(done, [[[QUESTION, true, false, '<p>On sand the gap between the two is smaller than its <code>noise</code>.</p>']], ['0:cannot be told', '0: apart'], false, 1, true]), done);

  // ------------------------------------------------------------ follow-ups
  const inNote = E.place(pick(note(), 'smaller than its noise'));
  check('a selection in the note is a follow-up: the note\'s own place, with the words selected', same(inNote, Object.assign({}, HERE, { quote: 'smaller than its noise', tab: 'answer', view: 'technical', passage: 'cannot be told apart', at: 0 })), inNote);
  const onMark = E.place(pick(text('answer').querySelector('p'), 'told apart.'));
  check('... and so is one that touches the marked passage', same(onMark, Object.assign({}, HERE, { quote: 'told apart.', tab: 'answer', view: 'technical', passage: 'cannot be told apart', at: 0 })), onMark);
  const over = E.place(pick(text('answer'), '.' + note().textContent + '\n\nOn loam'));
  check('a selection that runs across the open note and touches no marked passage is a passage of the tab\'s text: it holds none of the note\'s words, and the note is shown as before',
    over && over.quote === '.\n\nOn loam' && over.passage === '. On loam' && over.at === 0 && over.tab === 'answer' && note().hidden === false, over);
  await asked(inNote, 'What is noise here?', 'How much the plots of one regime differ among themselves.');
  check('a follow-up\'s answer joins its note: the earlier question one line, the newest open; the server was told the note\'s place and the words selected',
    same(folds().map(f => f.slice(0, 3)), [[QUESTION, false, false], ['What is noise here?', true, false]]) && same(calls[1][1], { thread_id: 3, chain_id: 7, tab: 'answer', view: 'technical', passage: 'cannot be told apart', at: 0,
      quote: 'smaller than its noise', question: 'What is noise here?' }) && doc.querySelectorAll('.xp-note').length === 1 && same(marks(), ['0:cannot be told', '0: apart']), [folds(), calls[1]]);

  // ------------------------------------------------------------ a second passage; one note open at a time
  const clay = E.place(pick(text('answer'), 'On clay the lead is clear.'));
  await asked(clay, 'Clear by how much?', 'By 0.42 t/ha.');
  const item = text('answer').querySelectorAll('li')[1];
  check('a second passage: its note opens - in a list, at the end of its item - and the first shuts; both passages stay marked',
    doc.querySelectorAll('.xp-note').length === 1 && note().parent === item && item.children[item.children.length - 1] === note() && same(folds().map(f => f[0]), ['Clear by how much?'])
    && same(marks(), ['0:cannot be told', '0: apart', '1:On clay the lead is clear.']), [marks(), note() && note().parent.tag]);
  const before = calls.length;
  picked = null;
  await click(text('answer').querySelector('strong .xp-mark'));
  const opened = [note().previousSibling.tag, folds().map(f => f.slice(0, 2)), doc.querySelectorAll('.xp-note').length];
  await click(text('answer').querySelectorAll('.xp-mark')[1]);
  const shut = !note();
  pick(text('answer'), 'told');
  await click(text('answer').querySelector('strong .xp-mark'));
  const selecting = !note();
  picked = null;
  check('a click on a marked passage opens its note - every question asked there, the newest open - and shuts the other; a click on it again shuts it; a press that ended as a selection opens nothing. No click asks anything',
    same(opened, ['p', [[QUESTION, false], ['What is noise here?', true]], 1]) && shut && selecting && calls.length === before && same(marks(), ['0:cannot be told', '0: apart', '1:On clay the lead is clear.']), [opened, shut, selecting]);

  // ------------------------------------------------------------ no answer
  const refused = async (answer, where, question = 'And this?') => { server = answer; said.length = 0; E.ask(where, question); await tick(); return [said.slice(), marks(), !!note(), E.holds()]; };
  const fresh = () => E.place(pick(text('answer'), 'The interval excludes zero.'));
  const no = [];
  no.push(await refused(() => whole(403, { error: 'authorization_failed', message: 'You need $0.010 per query but your balance is $0.00.' }), fresh()));
  no.push(await refused(() => whole(400, { error: 'The selection is too long to explain: select less.' }), fresh()));
  no.push(await refused(() => Promise.reject(new Error('offline')), fresh()));
  no.push(await refused(() => whole(500, '<html>Internal Server Error</html>'), fresh()));
  no.push(await refused(() => whole(200, JSON.stringify({ explain: { error: 'This analysis is no longer on record: nothing can be asked about it.' } }) + '\n'), fresh()));
  no.push(await refused(() => whole(200, JSON.stringify({ routine_error: 'something went wrong: boom' }) + '\n'), fresh()));
  const STAY = ['0:cannot be told', '0: apart', '1:On clay the lead is clear.'];
  check('no answer: the reason is said - the account\'s refusal, the server\'s, the server out of reach, a reply that is no stream, the analysis off the record, a failure in the stream - and the question goes, with its mark',
    same(no.map(n => n[0]), [['You need $0.010 per query but your balance is $0.00.'], ['The selection is too long to explain: select less.'], ['No explanation was written: the server could not be reached.'],
                             ['No explanation was written.'], ['This analysis is no longer on record: nothing can be asked about it.'], ['something went wrong: boom']])
    && no.every(n => same(n.slice(1), [STAY, false, false])), no);
  const s2 = stream(); server = () => Promise.resolve(s2.response); said.length = 0;
  E.ask(fresh(), 'And this?'); await tick();
  const mine = [marks().length, !!note()];
  responses.push({ chain_id: 8, thread_id: 3 }); currentResponseIndex = 1; await drawn(text('answer'));
  const theirs = [marks(), !!note()];
  currentResponseIndex = 0; responses.pop(); await drawn(text('answer'));
  const mineAgain = [marks().length, !!note()];
  s2.line({ explain: { error: 'Stopped.' } }); s2.end(); await tick();
  check('a question being answered is its own analysis\': another chain on screen meanwhile shows nothing of it; back on its chain the passage is marked again, its note shut, until the answer - here none - arrives',
    same(mine, [4, true]) && same(theirs, [[], false]) && same(mineAgain, [4, false]) && same(marks(), STAY) && same(said, ['Stopped.']), [mine, theirs, mineAgain, marks(), said]);
  const again = await refused(() => whole(403, { message: 'No.' }), E.place(pick(text('answer'), 'On clay the lead')));
  check('... a follow-up that gets no answer leaves its note as it was, open on what was asked before', same(again, [['No.'], STAY, true, false]) && same(folds().map(f => f.slice(0, 3)), [['Clear by how much?', true, false]]), [again, folds()]);

  const sets = renderLatex; global.renderLatex = () => { throw new Error('the formulas\' renderer is not loaded'); };
  picked = null;
  await click(text('answer').querySelector('strong .xp-mark'));
  const unset = folds().map(f => f.slice(0, 2));
  await click(text('answer').querySelectorAll('li')[1].querySelector('.xp-mark'));
  global.renderLatex = sets;
  check('formulas that cannot be set leave a note as it was written: it opens all the same, and so does the next', same(unset, [[QUESTION, false], ['What is noise here?', true]]) && same(folds().map(f => f[0]), ['Clear by how much?']), [unset, folds()]);

  // ------------------------------------------------------------ a tab drawn again
  text('answer').innerHTML = REPORT;
  const bare = [marks(), !!note()];
  await drawn(text('answer'));
  check('a tab drawn again has lost its marks and its note: they are put back once the watch says so - the passages found by their text, the open note under its passage',
    same(bare, [[], false]) && same(marks(), STAY) && note() && note().parent === text('answer').querySelectorAll('li')[1] && same(folds().map(f => f[0]), ['Clear by how much?']), [bare, marks()]);
  text('answer').innerHTML = REPORT;
  await drawn(text('plot'), text('plot').querySelector('p'));
  const elsewhere = marks();
  await drawn(text('answer').querySelector('h1'));
  const byPart = marks();
  text('answer').innerHTML = REPORT;
  await drawn($('contentOutput'));
  check('what is drawn into a tab that holds no passages is none of the module\'s: nothing is put back for it. A change in a part of a tab\'s text, and one of the tabs themselves, is', same([elsewhere, byPart, marks()], [[], STAY, STAY]), [elsewhere, byPart, marks()]);
  const walks = walked, takes = watch.taken;
  await drawn(text('answer'));
  check('marks that stand where they belong are left alone: the tab is read once and nothing is drawn', walked === walks + 1 && same(marks(), STAY) && watch.taken === takes + 1, [walked - walks, watch.taken - takes]);

  window.RoutinesUI = { inRunView: () => true };
  await drawn(text('answer'));
  const behind = [marks(), !!note()];
  window.RoutinesUI = { inRunView: () => false };
  await drawn(text('answer'));
  check('... and none of that chain\'s passages is marked in the run\'s tabs; they are again when the chain is back on screen', same(behind, [[], false]) && same(marks(), STAY) && !note(), [behind, marks()]);

  // ------------------------------------------------------------ the Answer's two versions
  currentData.summaryViewMode = 'simplified'; text('answer').innerHTML = PLAIN; await drawn(text('answer'));
  const inPlain = [marks(), !!note()];
  currentData.summaryViewMode = 'technical'; text('answer').innerHTML = REPORT; await drawn(text('answer'));
  const andBack = [marks(), !!note()];
  currentData.summaryViewMode = 'simplified'; text('answer').innerHTML = PLAIN; await drawn(text('answer'));
  await asked(E.place(pick(text('answer'), 'nobody can say')), 'Why not?', 'The gap is within the noise.');
  const plainNote = [marks(), folds().map(f => f[0]), calls[calls.length - 1][1].view];
  currentData.summaryViewMode = 'technical'; text('answer').innerHTML = REPORT; await drawn(text('answer'));
  check('the Answer\'s two versions each have their own passages: in plain language the technical report\'s marks and note are not drawn; a passage asked about there is that version\'s; back in the '
    + 'technical report its own marks return, and the note that was open there stays shut', same(inPlain, [[], false]) && same(andBack, [STAY, false]) && same(plainNote, [['2:nobody can say'], ['Why not?'], 'simplified'])
    && same(marks(), STAY) && !note(), [inPlain, andBack, plainNote, marks()]);

  // ------------------------------------------------------------ a passage the tab no longer has
  const clayItem = () => text('answer').querySelectorAll('li')[1];
  clayItem().textContent = 'On clay the lead holds.'; await drawn(clayItem());
  const lostLine = text('answer').querySelector('.xp-lost');
  const lost = [marks(), lostLine && lostLine.tag, lostLine && text('answer').children[text('answer').children.length - 1] === lostLine];
  await click(lostLine.querySelector('.xp-mark'));
  const lostNote = [note() && note().previousSibling === text('answer').querySelector('.xp-lost'), folds().map(f => f[0])];
  const follow = E.place(pick(text('answer').querySelector('.xp-lost'), 'the lead is'));
  clayItem().textContent = 'On clay the lead is clear.'; await drawn(clayItem());
  check('a passage the tab no longer has keeps its mark at the tab\'s foot, as the words first selected there: a click opens its note there, and it can be asked about further. When the text has the passage again, '
    + 'it is marked in its place, and its open note moves under it',
    same(lost, [['0:cannot be told', '0: apart', '1 lost:On clay the lead is clear.'], 'p', true]) && same(lostNote, [true, ['Clear by how much?']])
    && follow && follow.passage === 'On clay the lead is clear.' && follow.quote === 'the lead is' && same(marks(), STAY) && !text('answer').querySelector('.xp-lost')
    && doc.querySelectorAll('.xp-note').length === 1 && note().parent === clayItem() && clayItem().children[clayItem().children.length - 1] === note(), [lost, lostNote, follow, marks(), note() && note().parent.tag]);
  await asked(E.place(pick(text('answer'), 'the lead is clear', 0)), 'On which soil?', 'On loam.');
  const which = text('answer').querySelectorAll('li').map(li => marks(li));
  check('a passage the text has twice is marked where it was asked about', same(which, [['3:the lead is clear'], ['1:On clay the lead is clear.']]) && note().parent === text('answer').querySelectorAll('li')[0], which);

  // ------------------------------------------------------------ where a note stands
  const under = async (phrase, root = text('answer')) => { await asked(E.place(pick(root, phrase)), 'What is this?', 'A part of the report.'); return note(); };
  const places = [];
  places.push([(await under('three watering')).previousSibling.tag, note().parent === text('answer')]);
  places.push([(await under('regime B')).previousSibling.tag, note().parent === text('answer')]);
  places.push([(await under('Cell 2')).previousSibling.className, note().parent === text('answer')]);
  check('a note stands after the block its passage ends in - a heading, a table whole - and after the part of the tab that holds the passage where it is in no such block', same(places, [['h1', true], ['table', true], ['sp-sources', true]]), places);
  const wide = [(await under('6.54\nThe interval')).previousSibling.tag, marks(text('answer')).filter(m => m.startsWith('7:')), calls[calls.length - 1][1].passage, text('answer').children.filter(c => c.nodeType === 3 && c.data === '\n').length];
  check('a passage that runs from one block into the next is marked in each, the blanks between the two left as they are; its note stands after the block it ends in',
    same(wide, ['p', ['7:6.54', '7:The interval'], '6.54 The interval', 5]), wide);

  // ------------------------------------------------------------ the code
  const code = () => text('code').querySelector('code');
  await under('groupby(\'regime\')', text('code'));
  const inCode = [marks(text('code')), note().parent === code(), note().previousSibling.data, note().nextSibling.data, code().textContent.replace(note().textContent, '') === CODE];
  check('a note in the code stands after the line its passage is on: the text is cut behind the line\'s end', same(inCode, [['8:groupby(\'regime\')'], true, 'means = df.groupby(\'regime\')[\'yield\'].mean()\n'.slice('means = df.groupby(\'regime\')'.length),
    'print(means)\ngap = means[\'B\'] - means[\'A\']', true]), inCode);
  code().innerHTML = LIT; await drawn(code());
  const lit = [marks(text('code')), note().parent === code(), note().previousSibling.data, note().nextElementSibling.textContent];
  check('the code highlighted: the passage is found in the text as it now is - through the highlighter\'s elements - and the note is under its line again', same(lit, [['8:groupby', '8:(', '8:\'regime\'', '8:)'], true, '].mean()\n', 'print']), lit);
  await click(text('code').querySelector('.xp-mark'));
  check('a note shut leaves the code as it was written', !note() && code().textContent === CODE && code().children.filter(c => c.nodeType === 3).every(t => t.data.length) && same(marks(text('code')), ['8:groupby', '8:(', '8:\'regime\'', '8:)']), code().innerHTML);
  await under('means[\'A\']', text('code'));
  check('a passage on the code\'s last line, which has no line end: the note is at the code\'s end', note().parent === code() && code().children[code().children.length - 1] === note() && same(marks(text('code')).slice(4), ['9:means[', '9:\'A\'', '9:]']), marks(text('code')));
  await under('A : 6.12\n  B', text('code_exec_results'));
  const out = text('code_exec_results').querySelector('code');
  check('what was printed: a passage of two lines is marked through its line end, and its note is after its last line', same(marks(text('code_exec_results')), ['10:A : 6.12\n  B']) && note().parent === out && note().previousSibling.data === ' : 6.54\n'
    && out.elements[out.elements.length - 1] === note() && !out.textContent.endsWith('\n\n'), [marks(text('code_exec_results')), out.innerHTML]);

  // ------------------------------------------------------------ the export's copy
  await click(text('answer').querySelector('strong .xp-mark'));
  text('answer').insertAdjacentHTML('beforeend', '<p class="xp-lost">' + b.lost({ asked: [{ quote: 'gone' }] }, 9) + '</p>');
  const copy = doc.createElement('div'); copy.innerHTML = text('answer').innerHTML;
  const dressed = [copy.querySelectorAll('.xp-mark').length, copy.querySelectorAll('.xp-note').length, copy.querySelectorAll('.xp-lost').length];
  const back = E.plain(copy);
  text('answer').querySelector('.xp-lost').remove();
  const bareReport = doc.createElement('div'); bareReport.innerHTML = REPORT;
  check('the export\'s copy of a tab: without the notes, the passages no longer found and the marks - the report as it was drawn, each text in one piece again',
    back === copy && same(dressed, [10, 1, 1]) && copy.innerHTML === bareReport.innerHTML && copy.querySelector('p').children.length === 3, [dressed, copy.querySelector('p').children.length, copy.innerHTML]);

  // ------------------------------------------------------------ a chain shown again
  const ALL = kept.slice();
  calls.length = 0; server = () => whole(200, { asked: ALL.slice(0, 3) });
  E.restore(responses[0]);
  const shownAgain = [!!note(), marks(text('answer')).length, calls.slice()];
  await tick();
  check('a chain shown again: no note is open, and what was asked about it is asked of the server - the page then draws what the server keeps',
    same(shownAgain, [false, 9, [['/explain/3/7', null]]]) && same(marks(), STAY) && !note(), [shownAgain, marks()]);
  server = () => Promise.reject(new Error('offline')); E.restore(responses[0]); await tick();
  const offline = marks();
  calls.length = 0;
  E.restore(null); E.restore({ chain_id: 8, thread_id: 3, status: 'running' }); E.restore({ chain_id: null, thread_id: 3 }); E.restore({ chain_id: 8, thread_id: null });
  check('... the server out of reach: the marks stay as the page has them. A chain that has not ended, or has no chain or thread of its own, is not asked about', same(offline, STAY) && calls.length === 0, [offline, calls]);
  responses.push({ chain_id: 8, thread_id: 3 }); currentResponseIndex = 1; text('answer').innerHTML = PLAIN;
  server = () => whole(200, { asked: [] }); E.restore(responses[1]); await tick();
  const other = [marks(), calls.slice(), E.stands(HERE), E.stands({ chain: 8 })];
  const quiet = walked;
  await drawn(text('answer'), text('code'));
  check('another chain on screen: none of the first one\'s marks, and a place taken in the first no longer stands. Where nothing was asked, a tab drawn again is not read at all - a running analysis draws its tabs many times a second',
    same(other, [[], [['/explain/3/8', null]], false, true]) && walked === quiet, [other, walked - quiet]);
  currentResponseIndex = 0; text('answer').innerHTML = REPORT; code().innerHTML = CODE;
  const letter = at => ({ tab: 'code_exec_results', view: '', passage: 'e', at, quote: 'e', question: 'Which letter?', answer: 'This one.' });
  const both = view => ({ tab: 'answer', view, passage: 'Regime B', at: 0, quote: 'Regime B', question: 'Which regime?', answer: 'The second.' });
  server = () => whole(200, { asked: ALL.concat([letter(0), letter(3), both('simplified'), both('technical')]) }); E.restore(responses[0]); await tick();
  const fourth = text('code_exec_results').querySelector('.xp-mark[data-k="12"]');
  check('... and back on the first: all of its marks, in every tab. The same words at two places are two passages, each marked at the occurrence it was asked about; and the same words in the Answer\'s '
    + 'two versions are a passage of each',
    same(marks(text('answer')), ['4:three watering', '14:Regime B', '0:cannot be told', '0: apart', '3:the lead is clear', '1:On clay the lead is clear.', '5:regime B', '7:6.54', '7:The interval', '6:Cell 2'])
    && same(marks(text('code')), ['8:groupby(\'regime\')', '9:means[\'A\']']) && same(marks(text('code_exec_results')), ['11:e', '12:e', '10:A : 6.12\n  B'])
    && fourth.previousSibling.data.endsWith('regim') && fourth.nextSibling.data.startsWith(', t/ha') && !note(), marks());

  // ------------------------------------------------------------ formulas still to be set
  responses.push({ chain_id: 9, thread_id: 3 }); currentResponseIndex = 2;
  const SOURCE = 'The slope \\(\\beta\\) is positive, and beta is its name.';
  text('answer').innerHTML = '<p>' + SOURCE + '</p>\n<pre><code>x = \\(1\\)</code></pre>\n';
  const named = passage => ({ tab: 'answer', view: 'technical', passage, at: 0, quote: passage, question: 'What is this?', answer: 'A name.' });
  server = () => whole(200, { asked: [named('is positive'), named('x = \\(1')] }); E.restore(responses[2]); await tick();
  const para = text('answer').querySelector('p');
  const waiting = [marks(), para.children.length, para.textContent];
  para.innerHTML = 'The slope <span class="katex">β</span> is positive, and beta is its name.'; await drawn(para);
  check('a text that still holds the source of a formula is left whole - a mark set into the source would keep the formula from being set: its passage waits at the tab\'s foot, and is marked in its place '
    + 'once the formula stands there. Code is never such a text', same(waiting, [['1:x = \\(1', '0 lost:is positive'], 1, SOURCE]) && same(marks(), ['0:is positive', '1:x = \\(1']) && para.querySelector('.xp-mark').previousSibling.data === ' '
    && !text('answer').querySelector('.xp-lost'), [waiting, marks()]);
  responses.pop(); currentResponseIndex = 0;

  // ------------------------------------------------------------ the page's hooks, from the source
  const qp = js('query-processing.js'), core = js('core.js'), wm = js('workflow-management.js'), nq = js('next-questions.js'), pdf = js('pdf-export.js'), tabsCss = css('tabs.css');
  check('index.html loads the module after selection.js, which asks it; the app starts it', html.indexOf('js/explain.js') > html.indexOf('js/selection.js') && html.indexOf('js/explain.js') < html.indexOf('js/integrations/sweatstack.js')
    && core.includes('window.ExplainUI.initialize();'));
  check('the send: nothing starts while an explanation is written - no analysis, no set of next questions',
    qp.includes('if (window.ExplainUI && window.ExplainUI.holds()) return;') && qp.indexOf('window.ExplainUI.holds()') > qp.indexOf('window.NextQuestionsUI.holds()')
    && qp.indexOf('window.ExplainUI.holds()') < qp.indexOf('window.SelectionUI.send(query)') && nq.includes('if (window.ExplainUI && window.ExplainUI.holds()) return Promise.resolve(false);'));
  check('a chain shown again is dressed with what was asked about it, after its tabs are drawn; the export takes its copy of the Answer without what is drawn into it here',
    wm.includes('if (window.ExplainUI) window.ExplainUI.restore(response);') && wm.indexOf('window.ExplainUI.restore(response)') > wm.indexOf('window.NextQuestionsUI.restore(response)')
    && pdf.includes('const contentClone = answerContent.cloneNode(true);\n        if (window.ExplainUI) window.ExplainUI.plain(contentClone);'));
  check('the Code tab copies and downloads the script as it was drawn, not what the tab holds now: a note open in the code is no part of it',
    cr.includes('const source = codeElement.textContent;') && cr.includes('navigator.clipboard.writeText(source)') && cr.includes('new Blob([source], { type: \'text/x-python\' })')
    && cr.indexOf('const source = codeElement.textContent;') < cr.indexOf('hljs.highlightElement(codeElement);') && !cr.includes('writeText(codeElement.textContent)'));
  const guards = fs.readdirSync(path.join(web, 'static', 'js')).filter(f => f.endsWith('.js')).map(f => [f, (js(f).match(/protectLatexDelimiters\(/g) || []).length]).filter(g => g[1]);
  check('Markdown with formulas is turned into the page\'s HTML in one place - the formulas are kept from the parser once: the Answer, its plain version and a note\'s answer all go through it. The same '
    + 'function tells this module a text that still holds a formula\'s source',
    same(guards, [['content-rendering.js', 2], ['explain.js', 1]]) && cr.includes('let finalContent = markdownToHtml(data, transformChainIdReferences);') && cr.includes('let finalContent = markdownToHtml(currentData.simplifiedAnswer);')
    && js('explain.js').includes('markdownToHtml(x.answer)'), guards);
  check('tabs.css: a marked passage is underlined and tinted, and takes a click; a note is set off from the text it stands in - in the code it reads as text, not as code; the answer being written ends on a cursor',
    /#contentOutput \.xp-mark \{[^}]*border-bottom: 1px dashed var\(--c-model\);[^}]*background: var\(--accent-bg-hover\);[^}]*cursor: pointer; \}/.test(tabsCss)
    && /#contentOutput \.xp-note \{[^}]*border-left: 2px solid var\(--c-model\);[^}]*font-family: var\(--font-ui\);[^}]*white-space: normal;[^}]*\}/.test(tabsCss)
    && tabsCss.includes('#contentOutput .xp-lost {') && tabsCss.includes('#contentOutput .xp-note .live .a { white-space: pre-wrap; }') && tabsCss.includes('#contentOutput .xp-note .live .a::after {'), '');

  let fails = 0; for (const [n, ok, d] of results) { console.log((ok ? '  ok   ' : '  FAIL ') + n + (ok ? '' : '  <- ' + (typeof d === 'string' ? d : JSON.stringify(d)))); if (!ok) fails++; }
  console.log(`\n${results.length - fails} passed, ${fails} failed`); process.exit(fails ? 1 : 0);
})().catch(e => { console.log('  FAIL the suite ran without throwing  <- ' + (e && e.stack || e)); process.exit(1); });
