// Asking about a selection (web_app/static/js/selection.js; 2026-11-27, the product owner's pick of three mockups): text
// selected in the content pane gets a small bar - Ask, Copy - that takes no focus; Ask puts the selection on the query
// box as a quote, and the question typed there is asked about the passage and explained where it stands (explain.js,
// tests/analyst/test_explain.js). A plot is quoted whole, by its chat button, its picture beside its name.
// The module is driven here on the mini DOM, with stand-ins for what the mini DOM has not - the browser's selection and
// the boxes of its lines - and the page's hooks are read from the source. The real thing, in a real browser on the real
// page, is tests/e2e/test_selection.py.
// Run: node tests/analyst/test_selection.js
'use strict';
const fs = require('fs'), path = require('path');
const { makeDocument, fragment } = require(path.join(__dirname, 'minidom.js'));
const web = path.join(__dirname, '..', '..', 'web_app');
const js = f => fs.readFileSync(path.join(web, 'static', 'js', f), 'utf8'), css = f => fs.readFileSync(path.join(web, 'static', 'css', f), 'utf8');
const html = fs.readFileSync(path.join(web, 'templates', 'index.html'), 'utf8');
const results = []; const check = (n, c, d) => results.push([n, !!c, d]);
const same = (a, b) => JSON.stringify(a) === JSON.stringify(b);
const doc = makeDocument(); global.document = doc;
const $ = id => doc.getElementById(id);

// the browser's selection, as far as the module asks: what is selected, the element it lies in, the boxes of its lines
let picked = null;
const selection = { get rangeCount() { return picked ? 1 : 0; }, toString: () => (picked ? picked.text : ''), get anchorNode() { return picked ? picked.within : null; },
  getRangeAt: () => ({ commonAncestorContainer: picked.within, getBoundingClientRect: () => picked.box, getClientRects: () => picked.lines }) };
const LINE = 19;
const pick = (text, within, top = 165, lines = 1) => { picked = { text, within, box: { top, bottom: top + LINE * lines },
  lines: Array.from({ length: lines }, (_, i) => ({ top: top + LINE * i, bottom: top + LINE * (i + 1), height: LINE })) }; };
const onWindow = {};
global.window = { innerWidth: 1440, innerHeight: 900, getSelection: () => selection, addEventListener: (type, fn) => { onWindow[type] = fn; } };
let copies = 0, canCopy = true; doc.execCommand = what => (what === 'copy' && canCopy ? (copies += 1, true) : false);
// the page's watch on an element's contents: what is watched, and the callback, for the suite to call as the browser would
const watched = []; global.MutationObserver = class { constructor(fn) { this.fn = fn; } observe(el, how) { watched.push([el, how, this.fn]); } };
// explain.js, as far as the module asks it: where a selection can be asked about - here the words it holds -, whether
// the analysis a place was taken in still stands, and the asking; a plot as a place - here by its card's name -, and a
// place's picture, which the suite hands over when it chooses
const explain = { can: true, stands: true, asked: [], shots: [] };
window.ExplainUI = { place: range => (explain.can && range ? { quote: explain.words || picked.text } : null), stands: () => explain.stands, ask: (where, question) => explain.asked.push([where.quote, question]),
  figure: box => (explain.can ? { quote: box.id, plot: true } : null), picture: where => new Promise(give => explain.shots.push([where, give])) };
const taken = async (image, k = explain.shots.length - 1) => { explain.shots[k][1](image); await tick(); };      // a place's picture arrives, or none does

// the page, as far as the module reaches: the query box with the quote's own markup from index.html, the two panes
const host = doc.createElement('div'); doc.body.appendChild(host);
host.innerHTML = '<div id="leftPanel"><div id="streamOutput"><p id="turn">a turn of the analysis</p></div><div class="textarea-container">' + fragment(html, 'queryQuote') + '<textarea id="queryInput"></textarea></div></div>'
  + '<button id="collapseButton"></button><div id="contentOutput"><div id="content-answer"><p id="passage">on sand the two cannot be told apart</p><input id="note"></div>'
  + '<div id="content-plot"><p id="caption">Yield by regime</p><div class="plot-container" id="Plot 2"></div></div></div>';
let unfolded = 0; $('collapseButton').click = () => { unfolded += 1; $('leftPanel').classList.remove('collapsed'); };

require(path.join(web, 'static', 'js', 'selection.js'));
const S = window.SelectionUI;
S.initialize();
const bar = doc.querySelector('.selection-bar'), quote = $('queryQuote'), shot = quote.querySelector('img'), PASSAGE = 'on sand the two cannot be told apart';
bar.offsetWidth = 134; bar.offsetHeight = 32;      // the mini DOM lays nothing out: the bar's size as the browser measures it
const tick = (ms = 5) => new Promise(r => setTimeout(r, ms));
const press = (el, button = 0) => doc.dispatch('mousedown', el, { button });
const letGo = async (el, x, y) => { doc.dispatch('mouseup', el, { clientX: x, clientY: y }); await tick(); return at(); };
const at = () => ({ on: bar.classList.contains('on'), left: parseFloat(bar.style.left), top: parseFloat(bar.style.top) });
// a selection made in the pane with the mouse: pressed there, let go at (x, y)
const select = (x = 973, y = 175, text = PASSAGE, within = $('passage'), top = 165, lines = 1) => { press(within); pick(text, within, top, lines); return letGo(within, x, y); };
const words = () => [bar.querySelector('.ask').textContent, bar.querySelector('.copy').textContent];
const quoteOn = () => quote.classList.contains('on');

(async () => {
  check('started: one bar on the page with Ask and Copy, not shown; no quote on the query box, so a question typed there is not the module\'s to send',
    doc.querySelectorAll('.selection-bar').length === 1 && bar.parent === doc.body && same(words(), ['Ask', 'Copy']) && !at().on && !quoteOn() && S.send('Why?') === false && !explain.asked.length);

  // ---- where the bar stands
  check('a selection of one line: the bar over it - its own height and the gap above the line - centred on where the pointer let go', same(await select(), { on: true, left: 906, top: 125 }), at());
  check('several lines, the pointer let go on the last: under the selection', same(await select(900, 215, PASSAGE, $('passage'), 165, 3), { on: true, left: 833, top: 165 + 3 * LINE + 8 }), at());
  check('... let go on the first: over it', same(await select(900, 170, PASSAGE, $('passage'), 165, 3), { on: true, left: 833, top: 125 }), at());
  check('no room under a selection at the foot of the window: over its first line instead', same(await select(900, 880, PASSAGE, $('passage'), 700, 10), { on: true, left: 833, top: 660 }), at());
  check('no room at either end of a selection taller than the window: at the window\'s edge on the pointer\'s side', same(await select(900, 880, PASSAGE, $('passage'), -400, 80), { on: true, left: 833, top: 860 }), at());
  check('the bar is kept inside the window sideways', (await select(1436)).left === 1440 - 134 - 8 && (await select(3)).left === 8, at());
  explain.can = false; await select();
  const copyOnly = [bar.classList.contains('copies'), at().on];
  explain.can = true; await select();
  check('Ask is on the bar only where the selection can be asked about - explain.js says where: elsewhere the bar copies', same(copyOnly, [true, true]) && !bar.classList.contains('copies') && at().on, copyOnly);

  // ---- when it is offered
  press($('turn')); pick(PASSAGE, $('passage'));
  check('a press that began outside the content pane ends without a bar, whatever is selected there', !(await letGo($('passage'), 973, 175)).on, at());
  check('a selection on the Plots tab: the bar, as in any tab of the pane', (await select(900, 175, 'Yield by regime', $('caption'))).on, at());
  press($('passage')); pick('a turn ... told apart', host);
  check('a selection that began in the pane and reaches out of it: none', !(await letGo($('turn'), 300, 175)).on, at());
  press($('passage'), 2); pick(PASSAGE, $('passage'));
  check('a press with another button - the browser\'s own menu over a selection - ends without a bar', !(await letGo($('passage'), 973, 175)).on, at());
  $('note').focus();
  check('text selected in a field being typed in: none', !(await select()).on, at());
  $('note').blur();
  await select(); press($('passage')); picked = null;
  check('nothing selected at the end of the press - a click, also one inside a selection: none', !(await letGo($('passage'), 800, 175)).on, at());

  // ---- what takes it away
  const shown = async () => (await select()).on;
  const gone = [];
  if (await shown()) { doc.dispatch('keydown', null, { key: 'Escape' }); gone.push(['Esc', !at().on]); }
  if (await shown()) { press($('turn')); gone.push(['a press elsewhere', !at().on]); }
  if (await shown()) { doc.dispatch('scroll', $('contentOutput')); gone.push(['the selection scrolled', !at().on]); }
  if (await shown()) { onWindow.resize(); gone.push(['the window resized', !at().on]); }
  if (await shown()) { picked = null; doc.dispatch('selectionchange'); gone.push(['the selection gone', !at().on]); }
  if (await shown()) { picked = null; watched[0][2](); gone.push(['the selection gone from under it, its tab drawn again', !at().on]); }
  check('the bar goes with Esc, a press elsewhere, the selection scrolled, the window resized, the selection gone - also from under it when the content pane is drawn again, which the page watches for itself',
    gone.length === 6 && gone.every(g => g[1]) && watched.length === 1 && watched[0][0] === $('contentOutput') && same(watched[0][1], { childList: true, subtree: true }), gone);
  const stays = [];
  if (await shown()) { doc.dispatch('scroll', $('streamOutput')); stays.push(['the other pane scrolled', at().on]); }
  if (at().on) { doc.dispatch('selectionchange'); stays.push(['the selection changed and still there', at().on]); }
  if (at().on) { watched[0][2](); stays.push(['the content pane drawn again and the selection still there', at().on]); }
  if (at().on) { doc.dispatch('keydown', null, { key: 'a' }); stays.push(['another key', at().on]); }
  let kept = false; bar.dispatch('mousedown', bar, { preventDefault() { kept = true; } });
  if (at().on) { press(bar.querySelector('.copy')); stays.push(['a press on the bar', at().on && kept]); }
  check('... and stays when the other pane scrolls, the selection changes or the pane is drawn again with the selection still there, another key is pressed; a press on the bar itself is kept from the page, so the selection is not dropped',
    stays.length === 5 && stays.every(s => s[1]), stays);

  // ---- Copy
  await select();
  bar.querySelector('.copy').dispatch('click');
  const copied = [copies, words(), at().on];
  await tick(1000);
  check('Copy: the browser copies the selection, the button says Copied, and the bar goes a moment later', same(copied, [1, ['Ask', 'Copied'], true]) && !at().on, [copied, at()]);
  await select();
  check('the next bar says Copy again', same(words(), ['Ask', 'Copy']) && at().on, words());
  canCopy = false; bar.querySelector('.copy').dispatch('click'); await tick(1000); canCopy = true;
  check('a browser that will not copy: nothing is claimed, and the bar stays', copies === 1 && same(words(), ['Ask', 'Copy']) && at().on, [copies, words(), at()]);

  // ---- Ask, and the quote on the query box
  bar.querySelector('.ask').dispatch('click');
  check('Ask: the selection is on the query box - its words, and whole under the pointer -, the cursor in the box, the bar gone; the left pane was open and is left alone',
    quoteOn() && quote.querySelector('.t').textContent === PASSAGE && quote.querySelector('.t').title === PASSAGE && doc.activeElement === $('queryInput') && !at().on && unfolded === 0, quote.outerHTML);
  const sent = [S.send('Why?'), quoteOn(), explain.asked.slice()];
  check('a question typed with the quote on the box is the module\'s to send: it is asked about the place the quote was taken at, and the module says that it was - the one who sends empties the box',
    same(sent, [true, true, [[PASSAGE, 'Why?']]]), sent);
  $('queryInput').blur(); $('leftPanel').classList.add('collapsed');
  await select(900, 215, 'Plot 1: on clay\n\nPlot 2:   on sand', $('passage'), 165, 3);
  bar.querySelector('.ask').dispatch('click');
  check('another Ask takes the quote\'s place, the left pane opened by its own button where it was folded away; a passage of several lines is one line on the box, and it is the place now asked about',
    quote.querySelector('.t').textContent === 'Plot 1: on clay Plot 2: on sand' && quote.querySelector('.t').title === 'Plot 1: on clay\n\nPlot 2:   on sand' && unfolded === 1
    && !$('leftPanel').classList.contains('collapsed') && doc.activeElement === $('queryInput') && S.send('Which?') && same(explain.asked[1], ['Plot 1: on clay\n\nPlot 2:   on sand', 'Which?']), quote.outerHTML);
  $('queryInput').blur();
  quote.querySelector('button').dispatch('click');
  check('the quote\'s ×: the quote is off, a question typed is the page\'s own again, the cursor is in the box',
    !quoteOn() && S.send('Why?') === false && explain.asked.length === 2 && quote.querySelector('.t').textContent === '' && doc.activeElement === $('queryInput'), quote.outerHTML);
  picked = null; bar.querySelector('.ask').dispatch('click');
  check('Ask with nothing selected any more: no quote', !quoteOn() && S.send('Why?') === false);
  await select(); explain.can = false; bar.querySelector('.ask').dispatch('click'); explain.can = true;
  check('Ask on a selection that can no longer be asked about - its analysis went since the bar came: no quote, and the bar goes', !quoteOn() && !at().on && S.send('Why?') === false);

  // ---- the quote goes with the analysis it was taken from
  await select(); bar.querySelector('.ask').dispatch('click');
  doc.dispatch('selectionchange'); watched[0][2]();
  const stood = quoteOn();
  explain.stands = false; doc.dispatch('selectionchange');
  const went = quoteOn();
  explain.stands = true; await select(); bar.querySelector('.ask').dispatch('click'); explain.stands = false; watched[0][2]();
  check('the quote goes with the analysis it was taken from - another chain on screen, an analysis begun - as soon as the selection or the content pane changes; while that analysis stands, it stays',
    stood && !went && !quoteOn() && S.send('Why?') === false && explain.asked.length === 2, [stood, went, quoteOn()]);
  explain.stands = true;
  explain.words = 'the two cannot'; await select(); bar.querySelector('.ask').dispatch('click'); explain.words = null;
  check('the quote is the words of the place - explain.js leaves out what an open note adds to a selection that runs across it -, not the selection as the browser gives it',
    quote.querySelector('.t').textContent === 'the two cannot' && quote.querySelector('.t').title === 'the two cannot' && S.send('Why?') && same(explain.asked[2], ['the two cannot', 'Why?']), quote.outerHTML);

  // ---- a plot quoted
  quote.querySelector('button').dispatch('click'); $('queryInput').blur(); $('leftPanel').classList.add('collapsed');
  await select(); const up = at().on, folded = unfolded;
  S.plot($('Plot 2'));
  const quoted = [quoteOn(), quote.querySelector('.t').textContent, doc.activeElement === $('queryInput'), unfolded - folded, at().on, shot.hasAttribute('src')];
  const asksFor = explain.shots[explain.shots.length - 1][0];
  await taken('PIC');
  check('a plot\'s chat button: the plot is on the query box - its name the words -, the cursor in the box, the left pane opened where it was folded away, the bar gone. Its picture is asked for and stands beside '
    + 'the name once it is taken', up && same(quoted, [true, 'Plot 2', true, 1, false, false]) && same(asksFor, { quote: 'Plot 2', plot: true }) && shot.getAttribute('src') === 'data:image/png;base64,PIC', [quoted, asksFor, shot.outerHTML]);
  const sentPlot = [S.send('What does it show?'), explain.asked[explain.asked.length - 1]];
  check('a question typed with a plot on the box is asked about the plot', same(sentPlot, [true, ['Plot 2', 'What does it show?']]), sentPlot);
  await select(); bar.querySelector('.ask').dispatch('click');
  const swapped = [quote.querySelector('.t').textContent, shot.hasAttribute('src')];
  await taken(null);
  check('a passage quoted in the plot\'s place: the picture leaves the box, and a passage has none', same(swapped, [PASSAGE, false]) && !shot.hasAttribute('src'), swapped);
  S.plot($('Plot 2')); const late = explain.shots.length - 1;
  await select(); bar.querySelector('.ask').dispatch('click'); await taken(null);
  await taken('LATE', late);
  check('a picture that arrives after another quote has taken the plot\'s place is not put beside it', quote.querySelector('.t').textContent === PASSAGE && !shot.hasAttribute('src'), shot.outerHTML);
  S.plot($('Plot 2')); await taken('PIC');
  quote.querySelector('button').dispatch('click');
  const off = [quoteOn(), shot.hasAttribute('src'), S.send('Why?')];
  S.plot($('Plot 2')); await taken('');
  const none = [quoteOn(), shot.hasAttribute('src')];
  explain.can = false; quote.querySelector('button').dispatch('click'); S.plot($('Plot 2')); explain.can = true;
  check('the quote taken off: the picture with it. A plot whose picture cannot be taken is quoted by its name alone; a plot that cannot be asked about - explain.js says why - is not quoted',
    same(off, [false, false, false]) && same(none, [true, false]) && !quoteOn() && explain.asked.length === 4, [off, none, quoteOn()]);
  $('queryInput').blur();

  // ---- the query box emptied (core.js): the one function, the quote with what was typed
  const emptyComposer = new Function(js('core.js').match(/function emptyComposer\(\) \{[\s\S]*?\n\}\n/)[0] + '; return emptyComposer;')();
  await select(); bar.querySelector('.ask').dispatch('click');
  $('queryInput').value = 'Why?'; $('queryInput').style.height = '120px';
  const before = quoteOn();
  emptyComposer();
  check('the query box emptied: its words, its height, and the quote', before && $('queryInput').value === '' && $('queryInput').style.height === 'auto' && !quoteOn() && S.send('Why?') === false, quote.outerHTML);
  window.SelectionUI = undefined; $('queryInput').value = 'Why?';
  emptyComposer();
  window.SelectionUI = S;
  check('... and on a page without this module, the words alone', $('queryInput').value === '');

  // ---- the page's hooks, from the source
  const qp = js('query-processing.js'), ar = js('architect.js'), core = js('core.js'), cr = js('content-rendering.js'), shell = css('shell.css');
  const under = (dir, sub = '') => fs.readdirSync(path.join(dir, sub), { withFileTypes: true }).flatMap(e => (e.isDirectory() ? under(dir, path.join(sub, e.name)) : [path.join(sub, e.name)]));
  const scripts = under(path.join(web, 'static', 'js')).filter(f => f.endsWith('.js')).map(f => [f, js(f)]);
  const sheets = fs.readdirSync(path.join(web, 'static', 'css')).filter(f => f.endsWith('.css') && f !== '_retired.css').map(f => [f, css(f)]);
  check('the send: with a quote on the box the composer\'s own send is the module\'s - the question is asked about the passage, the box emptied by the one function, and nothing else starts: no analysis, no '
    + 'brief, no branch. A send with nothing typed is none; a next question and a brief\'s analysis are not typed. A plot\'s chat button asks the module to quote the plot',
    qp.includes("const query = framed ? String(framed.queryText || '').trim() : (next ? String(next.text || '').trim() : queryInput.value.trim());")
    && qp.includes('if (typed && window.SelectionUI && window.SelectionUI.send(query)) { emptyComposer(); return; }')
    && qp.indexOf('if (!query && !synthesis) {') < qp.indexOf('window.SelectionUI.send(query)') && qp.indexOf('window.SelectionUI.send(query)') < qp.indexOf('window.BranchUI.hint(query)')
    && qp.indexOf('window.SelectionUI.send(query)') < qp.indexOf('if (window.ArchitectUI && !framed && !branch)')
    && qp.includes('if (!synthesis && !next) emptyComposer();') && !qp.includes("queryInput.value = '';") && cr.includes('if (plotContainer && window.SelectionUI) window.SelectionUI.plot(plotContainer);'));
  check('one place empties the query box: the Pathfinder calls it when a brief opens and when it is told something; nowhere else is the box emptied by hand',
    (ar.match(/emptyComposer\(\);/g) || []).length === 2 && scripts.filter(([, s]) => /\.value = '';\s*\w+\.style\.height = 'auto';/.test(s)).map(([f]) => f).join() === 'core.js',
    scripts.filter(([, s]) => /\.value = '';\s*\w+\.style\.height = 'auto';/.test(s)).map(([f]) => f));
  check('the app starts the module; its script is loaded with the page\'s other modules',
    core.includes('window.SelectionUI.initialize();') && html.indexOf('js/selection.js') > html.indexOf('js/maps.js') && html.indexOf('js/selection.js') < html.indexOf('js/integrations/sweatstack.js'));
  check('index.html: the quote\'s place is in the query box, above the words typed - the place of a plot\'s picture, then a mark, the words, a button to take it off',
    (() => { const box = doc.createElement('div'); box.innerHTML = html.slice(html.indexOf('<div class="textarea-container">'), html.indexOf('<div class="icon-row">'));
      const q = box.querySelector('.textarea-container #queryQuote.query-quote'); return q && q.nextElementSibling.id === 'queryInput' && q.firstElementChild.tag === 'img' && !q.firstElementChild.hasAttribute('src')
        && q.firstElementChild.nextElementSibling.tag === 'svg' && q.querySelector('.t') && q.querySelector('button[title="Remove"]'); })());
  const OLD = ['selectionPopup', 'selection-popup', 'selectionForm', 'selectionQuery', 'selected-text-display', 'handleTextSelection', 'handleQuerySubmission', 'handleScroll', 'highlightElements', 'currentRange'];
  const left = [...scripts, ...sheets, ['index.html', html]].filter(([, s]) => OLD.some(o => s.includes(o))).map(([f]) => f);
  check('the popup this replaces is gone whole: its markup, its handlers, its variables, its scroll hooks, its styles', left.length === 0 && !/let (currentSelection|selectedText)\b/.test(core), left);
  check('a passage is no longer sent to the analyst under a question: its heading is written nowhere on the page', scripts.filter(([, s]) => s.includes('Task Context')).map(([f]) => f).join() === '');
  check('shell.css: the bar is fixed, shown only while it is on - without Ask where it copies -, and Ask is greyed and takes no press while the query box is held, as a plot\'s chat button is; the quote is shown only while '
    + 'it is on, on one clipped line, a plot\'s picture - once there is one - in the mark\'s place',
    shell.includes('.selection-bar { position: fixed; z-index: 1001; display: none;') && shell.includes('.selection-bar.on { display: inline-flex; }')
    && shell.includes('.selection-bar.copies .ask, .selection-bar.copies .sep { display: none; }')
    && shell.includes('body.composer-locked .selection-bar button.ask, body.composer-locked #content-plot .plot-query-btn { opacity: .4; pointer-events: none; }') && shell.includes('.left-panel .query-quote { display: none;')
    && /\.left-panel \.query-quote img \{ display: none; [^}]*\}/.test(shell) && shell.includes('.left-panel .query-quote img[src] { display: block; }') && shell.includes('.left-panel .query-quote img[src] + svg { display: none; }')
    && shell.includes('.left-panel .query-quote.on { display: flex; }') && shell.includes('.left-panel .query-quote .t { flex: 1; min-width: 0; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }'));
  const rules = sheets.filter(([, s]) => /::(-moz-)?selection/.test(s)).map(([f, s]) => f + ':' + (s.match(/::(-moz-)?selection/g) || []).length);
  check('selected text is coloured by one rule, base.css\'s, in the colour it had (two rules said it before, the later one winning)',
    same(rules, ['base.css:1']) && css('base.css').includes('::selection { background: var(--selection-bg); color: inherit; }') && css('tokens.css').includes('--selection-bg: rgba(140, 231, 182, 0.3);'), rules);

  let fails = 0; for (const [n, ok, d] of results) { console.log((ok ? '  ok   ' : '  FAIL ') + n + (ok ? '' : '  <- ' + (typeof d === 'string' ? d : JSON.stringify(d)))); if (!ok) fails++; }
  console.log(`\n${results.length - fails} passed, ${fails} failed`); process.exit(fails ? 1 : 0);
})().catch(e => { console.log('  FAIL the suite ran without throwing  <- ' + (e && e.stack || e)); process.exit(1); });
