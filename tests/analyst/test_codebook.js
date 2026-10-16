// The context codebook's screen (docs/CONTEXT_DESIGN.md §7 S3, step 6, 2026-10-16): the markup codebook.js builds from the
// view - the dialog's shell and header line, the proposals' cards with their examples and the four decisions, the inline
// rename and merge forms, the codes by group as tables, the empty states, the foot - and the module driven on the mini DOM
// with a scripted server: the Context card's line and the pill's count, the dialog opened and rendered, a proposal confirmed, renamed, merged and
// declined through the routes, a refusal shown in the card with its reason, the pill's count following.
// Run: node tests/analyst/test_codebook.js
'use strict';
const fs = require('fs'), path = require('path');
const { makeDocument } = require(path.join(__dirname, 'minidom.js'));
const doc = makeDocument(); global.document = doc;
const calls = []; let answers = {};
global.window = { authService: { fetch: async (url, opts) => { const body = opts && opts.body && typeof opts.body === 'string' ? JSON.parse(opts.body) : null; calls.push([url, (opts && opts.method) || 'GET', body]);
  const a = typeof answers[url] === 'function' ? answers[url](body) : answers[url]; const [status, json] = a || [200, {}]; return { ok: status < 400, status, json: async () => json }; } } };
const pillCounts = []; global.window.contextPillProposals = n => pillCounts.push(n);
const toasts = []; global.showSystemMessage = t => toasts.push(t);
global.setTimeout = (fn, ms) => { global.__timers = (global.__timers || []).concat([[fn, ms]]); return 1; };
// the Context card of the load dialog, as index.html has it: the line slot the module fills, inside a label whose click toggles the box
const cardHost = doc.createElement('div'); cardHost.innerHTML = '<label class="int-card intervals-aux-option"><input type="checkbox" id="context-checkbox" value="context" checked><b>Context</b><span class="d">the words</span><span class="more" id="contextCodebookLine"></span></label>'; doc.body.appendChild(cardHost);
require(path.join(__dirname, '..', '..', 'web_app', 'static', 'js', 'codebook.js'));
const w = window; const b = w.__codebookBuild; const results = []; const check = (n, c, d) => results.push([n, !!c, d]);
const el = html => { const d = doc.createElement('div'); d.innerHTML = html; return d; };

// ---- the view a page gets (the module's cb.view): two proposals, the seed's groups cut to three, a confirmed group ----
const VIEW = { version: 2, updated: '2026-10-15T10:00:00Z', counts: { codes: 7, proposed: 2, used: 3 },
  proposals: [{ code: 'heavy_legs', definition: 'the legs feel heavy', proposed_by: 'x/coder-1', proposed_on: '2026-10-15T10:00:00Z', examples: ['C.2: the legs were heavy today, rode shorter than planned', 'C.7: heavy again'], uses: 2 },
              { code: 'coach_flag', definition: 'a private note to watch something', proposed_by: '', proposed_on: '', examples: [], uses: 0 }],
  groups: [{ name: 'body and health', codes: [{ code: 'fatigue', definition: 'tired, flat, needing rest', status: 'seeded', uses: 31 }, { code: 'sleep', definition: 'how the night went', status: 'seeded', uses: 4 }, { code: 'injury', definition: 'a named injury', status: 'seeded', uses: 0 }] },
           { name: 'mind', codes: [{ code: 'mood', definition: 'upbeat, down, flat', status: 'seeded', uses: 0 }, { code: 'stress', definition: 'pressure from life', status: 'seeded', uses: 0 }] },
           { name: 'the exchange', codes: [{ code: 'instruction', definition: "the coach's direction", status: 'seeded', uses: 0 }] },
           { name: 'confirmed', codes: [{ code: 'leg_heaviness', definition: 'the legs feel heavy', status: 'confirmed', uses: 2 }] }] };

// ---- the builders ----
const sh = el(b.shell());
check('shell: the large ui-dlg with the title, a sub line, the close, the body, and a foot with the next-load line, an Import file picker and an Export link to the route',
  sh.querySelector('.ui-dlg.lg.cb-dlg .ui-dlg-h .title').textContent === 'Context codebook' && sh.querySelector('.ui-dlg-h .sub') && sh.querySelector('.ui-dlg-h .x') && sh.querySelector('.ui-dlg-b')
  && sh.querySelector('.ui-dlg-f .note').textContent === 'A confirmed change applies from the next load; nothing already coded is re-coded.'
  && sh.querySelector('.ui-dlg-f label.cb-import input[type="file"][data-field="import"]') && sh.querySelector('.ui-dlg-f a[href="/codebook/export"][download]').textContent === 'Export', sh.innerHTML);
check('the header line: the version, the codes, whether the uses are a load\'s; the count in words: the proposals or nothing',
  b.sub(VIEW) === 'version 2 · 7 codes · uses from the last load' && b.sub({ version: 1, counts: { codes: 36, proposed: 0, used: 0 } }) === 'version 1 · 36 codes · no load counted yet' && b.sub({ version: 1, counts: { codes: 1, used: 1 } }) === 'version 1 · 1 code · uses from the last load'
  && b.count(2) === '2 proposals' && b.count(1) === '1 proposal' && b.count(0) === '' && b.count(undefined) === '', [b.sub(VIEW), b.count(2), b.count(0)]);
const cl2 = el(b.cardLine({ codes: 36, proposed: 2 })), cl0 = el(b.cardLine({ codes: 37, proposed: 0 }));
check('the Context card\'s line: the book\'s size and the proposals waiting as the link with the green count; with nothing waiting the link reads "open the codebook"',
  cl2.textContent === 'Coded against your codebook · 36 codes · 2 proposals waiting2' && cl2.querySelector('a#contextCodebookLink .n-badge').textContent === '2'
  && cl0.textContent === 'Coded against your codebook · 37 codes · open the codebook' && !cl0.querySelector('.n-badge') && el(b.cardLine({ codes: 0, proposed: 1 })).textContent === 'Coded against your codebook · 1 proposal waiting1', [cl2.textContent, cl0.textContent]);
const body = el(b.body(VIEW));
const cards = body.querySelectorAll('.cb-card');
check('body: the proposals section first with its count line, one card per proposal in the book\'s order, then the groups', body.elements[0].className === 'cb-sec cb-proposals' && body.querySelector('.cb-proposals .h').textContent === 'Proposals 2 codes the coder asked for · yours to decide'
  && cards.length === 2 && cards.map(c => c.getAttribute('data-code')).join() === 'heavy_legs,coach_flag' && body.querySelectorAll('.cb-group').length === 4, body.querySelector('.cb-proposals .h').textContent);
const c0 = cards[0], c1 = cards[1];
check('a card: the code and definition, the meta line (the coder\'s model by its last segment, the day, the uses), the examples with the passage id and its opening, the four decisions and an empty inline slot',
  c0.querySelector('.cb-head .code').textContent === 'heavy_legs' && c0.querySelector('.cb-head .def').textContent === 'the legs feel heavy'
  && /^proposed by coder-1 on (15 Oct|Oct 15) · on 2 passages in the last load$/.test(c0.querySelector('.cb-meta').textContent)    // the day in the browser's locale
  && c0.querySelectorAll('.cb-examples .ex').length === 2 && c0.querySelector('.cb-examples .ex .id').textContent === 'C.2' && c0.querySelector('.cb-examples .ex .t').textContent === 'the legs were heavy today, rode shorter than planned'
  && ['confirm', 'rename', 'merge', 'decline'].every(a => c0.querySelector('.cb-actions [data-act="' + a + '"]')) && c0.querySelector('[data-act="confirm"]').className === 'ui-btn sm primary' && c0.querySelector('[data-act="decline"]').className.includes('danger-text')
  && c0.querySelector('.cb-inline').innerHTML === '', c0.outerHTML);
check('a card without a proposer, date or examples: "proposed by the coder", not used, no examples block', c1.querySelector('.cb-meta').textContent === 'proposed by the coder · not used in the last load' && !c1.querySelector('.cb-examples'), c1.querySelector('.cb-meta').textContent);
check('Merge into… is disabled when the book has no active code to merge into', el(b.card(VIEW.proposals[0], [])).querySelector('[data-act="merge"]').hasAttribute('disabled') && !c0.querySelector('[data-act="merge"]').hasAttribute('disabled'));
const rf = el(b.renameForm({ code: 'heavy_legs' })), mf = el(b.mergeForm({ code: 'heavy_legs' }, ['fatigue', 'sleep']));
check('the rename form: a field prefilled with the code, Confirm as this name, Cancel, the naming rule; the merge form: a select over the active codes, Merge, Cancel',
  rf.querySelector('.cb-form input[data-field="rename"]').getAttribute('value') === 'heavy_legs' && rf.querySelector('[data-act="rename-go"]').textContent === 'Confirm as this name' && rf.querySelector('[data-act="form-cancel"]') && rf.querySelector('.help').textContent.includes('a name the book has is refused')
  && mf.querySelectorAll('select[data-field="merge"] option').length === 2 && mf.querySelector('option').getAttribute('value') === 'fatigue' && mf.querySelector('[data-act="merge-go"]').textContent === 'Merge' && mf.querySelector('.help').textContent.includes('the proposal leaves the book'), rf.innerHTML + mf.innerHTML);
const groups = body.querySelectorAll('.cb-group');
check('the groups: each a section headed by its name and count with a table - Code, Definition, Status, Uses - a row per code with the status chip and the uses (a dash for none); the confirmed group last',
  groups[0].querySelector('.h').textContent === 'body and health 3 codes' && groups[0].querySelectorAll('.cb-table thead th').map(t => t.textContent).join() === 'Code,Definition,Status,Uses'
  && groups[0].querySelectorAll('tbody tr').length === 3 && groups[0].querySelector('tbody tr[data-code="fatigue"] td.code').textContent === 'fatigue' && groups[0].querySelector('tr[data-code="fatigue"] .cb-status.seeded').textContent === 'seeded'
  && groups[0].querySelector('tr[data-code="fatigue"] td.num').textContent === '31' && groups[0].querySelector('tr[data-code="injury"] td.num .ui-muted') && groups[2].querySelector('.h').textContent === 'the exchange 1 code'
  && groups[3].querySelector('.h').textContent === 'confirmed 1 code' && groups[3].querySelector('.cb-status.confirmed'), groups[0].outerHTML);
const empty = el(b.body({ version: 1, counts: { codes: 0, proposed: 0, used: 0 }, proposals: [], groups: [] }));
check('the empty states: no proposals says what a proposal is; no codes says the book holds none', empty.querySelector('.cb-proposals .h').textContent === 'Proposals none waiting' && empty.querySelector('.cb-proposals .cb-none').textContent.startsWith('The coder proposes a code when none of the book')
  && empty.querySelectorAll('.cb-sec')[1].querySelector('.cb-none').textContent === 'The book holds no codes.', empty.innerHTML);
check('markup is escaped', el(b.card({ code: 'x', definition: '<b>&', examples: ['C.1: <i>'] }, [])).querySelector('.def').textContent === '<b>&' && el(b.error('<x>')).querySelector('.cb-error').textContent === '<x>');

// ---- the module on the mini DOM with a scripted server ----
answers['/codebook'] = [200, VIEW];
(async () => {
  const n = await w.CodebookUI.badge();
  const countEl = doc.getElementById('contextCodebookLine');
  check('badge: GET /codebook, the Context card\'s line filled with the book\'s size and the proposals waiting, the pill told the count', n === 2 && calls[0][0] === '/codebook' && countEl.textContent === 'Coded against your codebook · 7 codes · 2 proposals waiting2' && pillCounts.join() === '2', [n, countEl.textContent, pillCounts]);
  w.CodebookUI.open();
  await new Promise(r => setImmediate(r)); await new Promise(r => setImmediate(r));
  const modal = doc.getElementById('codebookModal');
  check('open: the dialog injected once (#codebookModal, a plain modal), shown, the book read and rendered - the sub line, two cards, four groups',
    modal && modal.className === 'codebook-modal-container ui-modal-plain' && modal.style.display === 'flex' && modal.querySelector('.ui-dlg-h .sub').textContent === 'version 2 · 7 codes · uses from the last load'
    && modal.querySelectorAll('.cb-card').length === 2 && modal.querySelectorAll('.cb-group').length === 4 && calls.length === 2, modal ? modal.querySelector('.ui-dlg-h .sub').textContent : 'no modal');
  // confirm as it is: the route answers the whole book; the dialog re-renders from it; the count follows
  const AFTER1 = Object.assign({}, VIEW, { version: 3, counts: { codes: 8, proposed: 1, used: 4 }, proposals: [VIEW.proposals[1]], groups: VIEW.groups.concat([{ name: 'confirmed', codes: [{ code: 'heavy_legs', definition: 'the legs feel heavy', status: 'confirmed', uses: 2 }] }]) });
  answers['/codebook/confirm'] = body => body.rename_to === 'taken' ? [400, { error: 'the book already has a code named taken' }] : [200, AFTER1];
  modal.dispatch('click', modal.querySelector('.cb-card[data-code="heavy_legs"] [data-act="confirm"]'));
  await new Promise(r => setImmediate(r)); await new Promise(r => setImmediate(r));
  check('Confirm: POST /codebook/confirm {code}; the dialog re-rendered from the answer (version 3, one card left, the confirmed group), a toast, the gear count and the pill following',
    calls[2][0] === '/codebook/confirm' && calls[2][1] === 'POST' && JSON.stringify(calls[2][2]) === '{"code":"heavy_legs"}' && modal.querySelector('.ui-dlg-h .sub').textContent === 'version 3 · 8 codes · uses from the last load'
    && modal.querySelectorAll('.cb-card').length === 1 && modal.querySelector('.cb-card').getAttribute('data-code') === 'coach_flag' && toasts[toasts.length - 1] === 'heavy_legs confirmed · codebook v3'
    && countEl.textContent === 'Coded against your codebook · 8 codes · 1 proposal waiting1' && pillCounts[pillCounts.length - 1] === 1, [calls[2], toasts, countEl.textContent, pillCounts]);
  // rename: the inline form, a refusal shown in the card with the reason, then a name that goes through
  const card = modal.querySelector('.cb-card[data-code="coach_flag"]');
  modal.dispatch('click', card.querySelector('[data-act="rename"]'));
  const inp = card.querySelector('.cb-inline input[data-field="rename"]');
  check('Rename…: the inline form opens in the card with the code as the starting name', inp && inp.getAttribute('value') === 'coach_flag' && card.querySelector('[data-act="rename-go"]'), card.innerHTML);
  inp.value = 'taken';
  modal.dispatch('click', card.querySelector('[data-act="rename-go"]'));
  await new Promise(r => setImmediate(r)); await new Promise(r => setImmediate(r));
  check('a refused rename: POST with rename_to; the reason shown in the card, the dialog otherwise as it was', JSON.stringify(calls[3][2]) === '{"code":"coach_flag","rename_to":"taken"}' && card.querySelector('.cb-inline .cb-error').textContent === 'the book already has a code named taken' && modal.querySelectorAll('.cb-card').length === 1, card.innerHTML);
  const AFTER2 = Object.assign({}, AFTER1, { version: 4, counts: { codes: 9, proposed: 0, used: 4 }, proposals: [] });
  answers['/codebook/confirm'] = body => [200, AFTER2];
  inp.value = 'coach note';
  modal.dispatch('keydown', inp, { key: 'Enter' });
  await new Promise(r => setImmediate(r)); await new Promise(r => setImmediate(r));
  check('Enter in the name field confirms under that name: POST with rename_to, the dialog re-rendered (no proposals left, the count cleared), the toast naming both',
    JSON.stringify(calls[4][2]) === '{"code":"coach_flag","rename_to":"coach note"}' && modal.querySelectorAll('.cb-card').length === 0 && modal.querySelector('.cb-proposals .h').textContent === 'Proposals none waiting' && countEl.textContent === 'Coded against your codebook · 9 codes · open the codebook' && pillCounts[pillCounts.length - 1] === 0
    && toasts[toasts.length - 1] === 'coach_flag confirmed as coach note · codebook v4', [calls[4], countEl.textContent, toasts[toasts.length - 1]]);
  // merge and decline on a fresh view
  answers['/codebook'] = [200, VIEW]; await w.CodebookUI.refresh();
  const c2 = modal.querySelector('.cb-card[data-code="heavy_legs"]');
  modal.dispatch('click', c2.querySelector('[data-act="merge"]'));
  const sel = c2.querySelector('.cb-inline select[data-field="merge"]');
  check('Merge into…: a select over the active codes of the view (the groups\' codes, the confirmed among them)', sel && sel.querySelectorAll('option').map(o => o.getAttribute('value')).join() === 'fatigue,sleep,injury,mood,stress,instruction,leg_heaviness', sel ? sel.outerHTML : c2.innerHTML);
  sel.value = 'fatigue';
  answers['/codebook/confirm'] = body => [200, AFTER1];
  modal.dispatch('click', c2.querySelector('[data-act="merge-go"]'));
  await new Promise(r => setImmediate(r)); await new Promise(r => setImmediate(r));
  check('Merge: POST with merge_into; the toast says so', JSON.stringify(calls[calls.length - 1][2]) === '{"code":"heavy_legs","merge_into":"fatigue"}' && toasts[toasts.length - 1] === 'heavy_legs merged into fatigue · codebook v3', [calls[calls.length - 1], toasts[toasts.length - 1]]);
  answers['/codebook/decline'] = body => [200, AFTER2];
  modal.dispatch('click', modal.querySelector('.cb-card[data-code="coach_flag"] [data-act="decline"]'));
  await new Promise(r => setImmediate(r)); await new Promise(r => setImmediate(r));
  check('Decline: POST /codebook/decline {code}; the dialog re-rendered', calls[calls.length - 1][0] === '/codebook/decline' && JSON.stringify(calls[calls.length - 1][2]) === '{"code":"coach_flag"}' && modal.querySelectorAll('.cb-card').length === 0 && toasts[toasts.length - 1] === 'coach_flag declined', [calls[calls.length - 1], toasts[toasts.length - 1]]);
  modal.dispatch('click', modal);
  const closedFirst = modal.style.display === 'none';
  w.CodebookUI.initialize();
  const ev = doc.dispatch('click', doc.getElementById('contextCodebookLink'));
  check('a click on the scrim closes; the card\'s link opens it again - taken in the capture phase, stopped before the label toggles the Context box (initialize binds it and schedules the count)',
    closedFirst && modal.style.display === 'flex' && ev.defaulted === true && ev.stopped === true && (global.__timers || []).some(t => t[1] === 1800), [closedFirst, modal.style.display, ev.defaulted, ev.stopped]);
  check('a click elsewhere is left alone', (() => { const e2 = doc.dispatch('click', doc.getElementById('context-checkbox')); return !e2.stopped && !e2.defaulted; })());
  // a book that cannot be read
  answers['/codebook'] = [500, { error: 'disk' }];
  await w.CodebookUI.refresh();
  check('a failed read: the body says the book could not be read, with the reason', modal.querySelector('.ui-dlg-b .cb-error').textContent === 'The codebook could not be read: disk.', modal.querySelector('.ui-dlg-b').innerHTML);

  // ---- the page's hooks ----
  const root = path.join(__dirname, '..', '..', 'web_app');
  const html = fs.readFileSync(path.join(root, 'templates', 'index.html'), 'utf8'), core = fs.readFileSync(path.join(root, 'static', 'js', 'core.js'), 'utf8');
  const dcss = fs.readFileSync(path.join(root, 'static', 'css', 'dialogs.css'), 'utf8'), scss = fs.readFileSync(path.join(root, 'static', 'css', 'shell.css'), 'utf8');
  const intMod = el(html.slice(html.indexOf('id="intervalsModal"'), html.indexOf('id="intervalsConfigModal"')));
  check('index.html: the Context card of the Intervals dialog carries the line slot the module fills; nothing universal carries the codebook (no gear item, no rail entry); codebook.js is loaded after memory-review.js; core.js initialises the module after auth',
    intMod.querySelector('.int-card #context-checkbox') && intMod.querySelector('.int-card .more#contextCodebookLine') && !html.includes('codebook-option') && !html.includes('codebookPill')
    && html.indexOf("js/codebook.js") > html.indexOf("js/memory-review.js") && core.includes('window.CodebookUI.initialize();'));
  check('the stylesheets: the dialog\'s rules in dialogs.css (the modal, the cards, the forms, the status chips, the tables, the card\'s badge), the pill\'s badge in shell.css',
    dcss.includes('#codebookModal { display: none; position: fixed;') && dcss.includes('.cb-card {') && dcss.includes('.cb-form {') && dcss.includes('.cb-status.confirmed') && dcss.includes('.cb-table td.num') && dcss.includes('.integration-dialog .n-badge {') && scss.includes('.topbar .context-pill .pill-badge {'));
  finish();
})().catch(e => { check('the module ran without throwing', false, e && e.stack); finish(); });

function finish() {
  let fails = 0; for (const [n, ok, d] of results) { console.log((ok ? '  ok   ' : '  FAIL ') + n + (ok ? '' : '  <- ' + String(d || '').slice(0, 900))); if (!ok) fails++; }
  console.log(`\n${results.length - fails} passed, ${fails} failed`); process.exit(fails ? 1 : 0);
}
