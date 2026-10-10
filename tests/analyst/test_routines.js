// Routines (docs/ROUTINES_DESIGN.md): the markup routines.js builds - the Save pill's menu in its three states, the
// Save-as-routine dialog, the manager, the favourites' cards' button - and the composer lock, on the mini DOM; the
// page's hooks (the rail entry, the script) and the stylesheet's rules. Run: node tests/analyst/test_routines.js
'use strict';
const fs = require('fs'), path = require('path');
const { makeDocument } = require(path.join(__dirname, 'minidom.js'));
const doc = makeDocument(); global.document = doc; global.window = { innerWidth: 1400 };
global.responses = []; global.currentResponseIndex = 0; global.currentData = {};
const comp = doc.createElement('div'); comp.innerHTML = '<textarea id="queryInput" placeholder="Enter your query here"></textarea><button id="submitQuery"></button>'; doc.body.appendChild(comp);
require(path.join(__dirname, '..', '..', 'web_app', 'static', 'js', 'routines.js'));
const w = window; const b = w.__routinesBuild; const results = []; const check = (n, c, d) => results.push([n, !!c, d]);
const el = html => { const d = doc.createElement('div'); d.innerHTML = html; return d; };

// ---- the Save pill's menu ----
let m = el(b.menu({ saved: false, own: [], thread: [] }));
check('menu, a fresh chain: Save as favourite and Save as routine, the second saying it saves the favourite too',
  m.querySelectorAll('.it').length === 2 && m.querySelector('[data-act="favourite"] b').textContent === 'Save as favourite' && !m.querySelector('.it.done')
  && m.querySelector('[data-act="routine"] span').textContent.includes('saves the favourite too'));
m = el(b.menu({ saved: true, own: [], thread: [{ id: 'r1', name: 'Altitude pace correction', version: 1, chain_id: 'c1' }] }));
check('menu, a saved chain of a routine\'s origin thread: the favourite item is done (inert); the routine item offers the next version or a new one',
  m.querySelector('[data-act="favourite"]').classList.contains('done') && m.querySelector('[data-act="favourite"] b').textContent === 'Saved as favourite'
  && m.querySelector('[data-act="routine"] span').textContent === 'next version of “Altitude pace correction”, or a new one');
m = el(b.menu({ saved: true, own: [{ id: 'r1', name: 'Rows above a line', version: 2 }], thread: [] }));
check('menu, a chain that already has a routine: says so with its name and version', m.querySelector('[data-act="routine"] span').textContent.startsWith('made from this chain: Rows above a line v2'));

// ---- the dialog ----
const shell = el(b.dialogShell());
check('dialog shell: the ui-dlg with header, close, body, footer note and the two buttons the script drives',
  shell.querySelector('.ui-dlg.routine-dlg .ui-dlg-h .title').textContent === 'Save as routine' && shell.querySelector('.ui-dlg-h .x') && shell.querySelector('.ui-dlg-b')
  && shell.querySelector('.ui-dlg-f .note') && shell.querySelector('[data-act="cancel"]') && shell.querySelector('[data-act="create"] span').textContent === 'Create routine');
const proposal = { name: 'Rows above a line', question: 'How many rows are above 155?', source: 'file', data_state: 'same',
  data: { name: 'small.csv', rows: 5, columns: [{ name: 'v' }, { name: 'g' }] },
  inputs: [{ key: 'threshold', label: 'Threshold', type: 'number', default: 155, origin: 'the analysis split at 155' }, { key: 'who', label: 'Groups', type: 'choice', multiple: true, default: ['a', 'b'], origin: 'the groups kept', column: 'g' }],
  kept: ['the seed stays'], results: [{ cell: 2, index: 0, label: 'rows above the line', typed: false }, { cell: 4, index: 0, label: 'a typed one', typed: true }], figures: { count: 1, cells: [3] }, notes: ['one note'] };
let p = el(b.proposal(proposal, []));
check('dialog body: name and purpose fields, the purpose prefilled from the question', p.querySelector('[data-field="name"]').getAttribute('value') === 'Rows above a line' && p.querySelector('[data-field="purpose"]').getAttribute('value') === 'How many rows are above 155?');
check('dialog body: the data row - the source chip, the file name, rows and columns - and the "checked once on this chain\'s own data" line',
  p.querySelector('.rt-data .ui-chip .t').textContent === 'File' && p.querySelector('.rt-data .name').textContent === 'small.csv' && p.querySelector('.rt-data .meta').textContent === '5 rows · 2 columns'
  && p.querySelector('.rt-line').textContent.startsWith('Checked once on this chain'));
check('dialog body: the inputs table - a row per input with its value, its origin, a keep-fixed checkbox keyed by the input; a choice names its column; the kept constants listed',
  p.querySelectorAll('.rt-inputs tbody tr').length === 2 && p.querySelector('tr[data-key="threshold"] .val').textContent === '155' && p.querySelector('tr[data-key="who"] .val').textContent === 'a, b'
  && p.querySelector('tr[data-key="who"] .from').textContent === ' · from g' && p.querySelectorAll('input[data-drop]').length === 2 && p.querySelector('input[data-drop="threshold"]')
  && p.querySelector('.rt-line.muted').textContent.includes('Left as they are: the seed stays'));
check('dialog body: the results - a tick per computed line with its cell; the typed line flagged with keep/drop, keep on by default; the count and the figure in the heading',
  p.querySelectorAll('.rt-results .r').length === 2 && p.querySelector('.rt-results .r:not(.flag) .c').textContent === 'cell 2' && p.querySelector('.rt-results .r.flag[data-cell="4"][data-index="0"]')
  && p.querySelector('.rt-results .r.flag .ui-seg .on').getAttribute('data-keep') === '1' && p.querySelector('.rt-results .r.flag .ui-seg span[data-keep="0"]').textContent === 'drop'
  && [...p.querySelectorAll('.rt-sec .h')].some(h => h.textContent.includes('2 kept · 1 figure')));
check('dialog body: without a routine on the thread there is no version choice', !p.querySelector('.rt-version'));
p = el(b.proposal(proposal, [{ id: 'r1', name: 'Altitude pace correction', version: 1, chain_id: 'c9' }]));
check('dialog body on a chain of an origin thread: the next-version choice first (on), a new routine beside it, the What-changed line',
  p.querySelector('.rt-version .ui-choice.on[data-version="next"] b').textContent === 'Next version of “Altitude pace correction”' && p.querySelector('.rt-version .ui-choice.on span').textContent.startsWith('v2 ')
  && p.querySelector('.rt-version .ui-choice[data-version="new"]') && p.querySelector('.rt-change [data-field="change_note"]'));
p = el(b.proposal(Object.assign({}, proposal, { data_state: 'gone', inputs: [], results: [], figures: { count: 0 } }), []));
check('dialog body with the data gone, no inputs and no result lines: says the routine will be unverified, that the method runs as it is, and that runs will not be compared number by number',
  p.querySelector('.rt-line.warn').textContent.includes('created unverified') && [...p.querySelectorAll('.rt-line')].some(x => x.textContent.startsWith('No inputs:'))
  && [...p.querySelectorAll('.rt-line')].some(x => x.textContent.includes('recorded no RESULT lines')));
check('dialog states: the waiting line names the seat and model; the error block carries the message and, when asked, a Try again',
  el(b.loading('Analyst', 'anthropic/claude-sonnet-5-5')).querySelector('.rt-wait').textContent.includes('Analyst on claude-sonnet-5-5')
  && el(b.error('run zero differed: x', true)).querySelector('.rt-error .msg').textContent === 'run zero differed: x' && el(b.error('x', true)).querySelector('[data-act="retry"]') && !el(b.error('x', false)).querySelector('[data-act="retry"]'));

// ---- the manager ----
const mg = el(b.managerShell());
check('manager shell: the list on the left, the routine on the right with header, actions and body', mg.querySelector('.rt-mgr .rt-left .rt-side') && mg.querySelector('.rt-right .ui-dlg-h .title') && mg.querySelector('.rt-right .rt-actions') && mg.querySelector('.rt-right .ui-dlg-h .x') && mg.querySelector('.rt-right .rt-body'));
const routine = { id: 'r1', name: 'Rows above a line', purpose: 'count the rows above a line', question: 'How many rows are above 155?', source: 'file', current_version: 2, origin: { thread_id: '1001', chain_id: '1791600000' }, origin_available: true,
  summary_card: { data: { columns: [{ name: 'v' }, { name: 'g' }] } },
  versions: [{ number: 1, created: 1791600000, promoted_from: { thread_id: '1001', chain_id: '1791600000' }, change_note: 'first version', manifest: { parameters: [], results: [], figures: { count: 0 } }, run_zero: { verified: true, line: 'reproduced: 1 result line(s) identical' } },
            { number: 2, created: 1791700000, promoted_from: { thread_id: '1001', chain_id: '1791700000' }, change_note: 'the threshold became an input', manifest: { parameters: [{ key: 'threshold', label: 'Threshold', type: 'number', default: 155, origin: 'the analysis split at 155' }], results: [{ cell: 2, index: 0, label: 'rows above the line', typed: false, dropped: false }, { cell: 4, index: 0, label: 'dropped one', typed: true, dropped: true }], figures: { count: 1 } }, run_zero: { verified: true, line: 'reproduced: 2 result line(s) identical' } }] };
const hd = b.routineHeader(routine);
check('manager header: the name; the source, the columns, the version, and the link to the analysis it was made from (a favourite)',
  hd.title === 'Rows above a line' && hd.sub.startsWith('File · 2 columns · v2 · ') && el(hd.sub).querySelector('a.rt-origin[data-thread="1001"][data-chain="1791600000"]') && hd.sub.includes('a favourite; continue it there'));
check('manager header when the favourite is gone: no link, says so', !el(b.routineHeader(Object.assign({}, routine, { origin_available: false })).sub).querySelector('a') && b.routineHeader(Object.assign({}, routine, { origin_available: false })).sub.includes('no longer in Saved workflows'));
const bd = el(b.routineBody(routine));
check('manager body: purpose, question, the verified mark with run zero\'s line; the current version\'s inputs and results (the dropped line left out); the versions newest first with their notes; runs: none yet',
  bd.querySelector('.ui-kv').textContent.includes('count the rows above a line') && bd.querySelector('.rt-status.reproduced').textContent === 'verified' && bd.textContent.includes('2 result line(s) identical')
  && bd.querySelectorAll('.rt-inputs tbody tr').length === 1 && bd.querySelectorAll('.rt-results .r').length === 1 && bd.querySelector('.rt-results .r .l').textContent === 'rows above the line'
  && bd.querySelectorAll('.rt-vers .v').length === 2 && bd.querySelector('.rt-vers .v b').textContent === 'v2' && bd.querySelector('.rt-vers .v span').textContent.includes('the threshold became an input')
  && bd.textContent.includes('None yet'));
check('manager actions: the .py download of the current version, Rename, Delete', el(b.actions(routine)).querySelector('a[href="/routines/r1/script"][download]') && el(b.actions(routine)).querySelector('[data-act="rename"]') && el(b.actions(routine)).querySelector('[data-act="delete"]'));
check('manager: the empty state tells the person where Save as routine is', el(b.empty()).textContent.includes('hover Save and choose Save as routine'));
const li = el(b.sideItem({ id: 'r1', name: 'Rows above a line', source: 'intervals', current_version: 1, runs: 0, created: 1791600000 }, true));
check('manager list item: name, source, version; on when selected', li.querySelector('.it.on[data-id="r1"] b').textContent === 'Rows above a line' && li.querySelector('.it span').textContent.startsWith('Intervals.icu · v1 · '));

// ---- the favourites' cards' button ----
check('card button: grey with no routine (title says Save as routine); lit with the count when versions were born from the analysis',
  !el(b.cardButton(0)).querySelector('.workflow-card-routine.has') && el(b.cardButton(0)).querySelector('.workflow-card-routine').getAttribute('title').startsWith('Save as routine')
  && el(b.cardButton(3)).querySelector('.workflow-card-routine.has .n').textContent === '3' && el(b.cardButton(1)).querySelector('.workflow-card-routine').getAttribute('title').startsWith('1 routine version made'));
check('card count: one chain, or every chain of a thread', w.RoutinesUI.cardCount({ routines: [1, 2] }) === 2 && w.RoutinesUI.cardCount([{ routines: [1] }, {}, { routines: [1, 2] }]) === 3);

// ---- the composer lock ----
w.RoutinesUI.composerLock();
const qi = doc.querySelector('#queryInput'), sq = doc.querySelector('#submitQuery');
check('composer lock: the input and the send button are disabled, the placeholder says why, the body carries the class', qi.disabled === true && sq.disabled === true && qi.placeholder.startsWith('A run is a record') && doc.body.classList.contains('composer-locked'));
w.RoutinesUI.composerUnlock();
check('composer unlock: back to the original placeholder, enabled', qi.disabled === false && sq.disabled === false && qi.placeholder === 'Enter your query here' && !doc.body.classList.contains('composer-locked'));
check('the lock is also reachable as window.composerLock / composerUnlock (workflow-management.js unlocks on a favourite load)', typeof w.composerLock === 'function' && typeof w.composerUnlock === 'function');

// ---- the page and the stylesheets ----
const html = fs.readFileSync(path.join(__dirname, '..', '..', 'web_app', 'templates', 'index.html'), 'utf8');
check('page: the Routines rail entry with its badge sits between Saved workflows and the Dataset cache; routines.js is loaded after workflow-modal.js',
  html.indexOf('id="workflowManagerPill"') < html.indexOf('id="routinesPill"') && html.indexOf('id="routinesPill"') < html.indexOf('id="datasetManagerPill"') && html.includes('id="routinesBadge" class="rb-badge"')
  && html.indexOf("js/workflow-modal.js") < html.indexOf("js/routines.js"));
const shellCss = fs.readFileSync(path.join(__dirname, '..', '..', 'web_app', 'static', 'css', 'shell.css'), 'utf8');
const dlgCss = fs.readFileSync(path.join(__dirname, '..', '..', 'web_app', 'static', 'css', 'dialogs.css'), 'utf8');
check('stylesheets: the pill\'s menu, its saved and open states and the rail badge in shell.css; the dialog, the manager, the card button and the composer lock in dialogs.css',
  ['.save-menu', '.save-menu .it.done', '#rankButton.saved', '#rankButton.menu-open', '.rb-badge'].every(c => shellCss.includes(c))
  && ['#routineMakeModal', '#routinesModal', '.rt-inputs', '.rt-results .r.flag', '.rt-version', '.workflow-card-routine.has', 'body.composer-locked'].every(c => dlgCss.includes(c)));
const qp = fs.readFileSync(path.join(__dirname, '..', '..', 'web_app', 'static', 'js', 'query-processing.js'), 'utf8');
check('the Save pill: a click opens the menu (the rank dialog from its first item); the pill stays on a saved chain, marked .saved',
  qp.includes('window.RoutinesUI.toggleSaveMenu()') && qp.includes("rankButton.classList.toggle('saved', saved)") && !qp.includes("currentResponse.bookmark_type === 'individual') {\n        rankButton.style.display = 'none'"));
const wm = fs.readFileSync(path.join(__dirname, '..', '..', 'web_app', 'static', 'js', 'workflow-modal.js'), 'utf8');
check('the favourites\' cards carry the Routine button in place of the v1 Replay button, bound through RoutinesUI', wm.includes('window.RoutinesUI.cardButton(') && wm.includes('window.RoutinesUI.bindCardButton(routineBtn') && !wm.includes('class="workflow-card-replay"'));
const core = fs.readFileSync(path.join(__dirname, '..', '..', 'web_app', 'static', 'js', 'core.js'), 'utf8');
check('routines.js is initialised after auth with the other modules', core.includes('window.RoutinesUI.initialize()'));

let fails = 0; for (const [n, ok, d] of results) { console.log((ok ? '  ok   ' : '  FAIL ') + n + (ok ? '' : '  <- ' + (d || ''))); if (!ok) fails++; }
console.log(`\n${results.length - fails} passed, ${fails} failed`); process.exit(fails ? 1 : 0);
