// Routines (docs/ROUTINES_DESIGN.md): the markup routines.js builds - the Save pill's menu in its three states, the
// Save-as-routine dialog, the manager, the favourites' cards' button - and the composer lock, on the mini DOM; the
// page's hooks (the rail entry, the script) and the stylesheet's rules. Run: node tests/analyst/test_routines.js
'use strict';
const fs = require('fs'), path = require('path');
const { makeDocument } = require(path.join(__dirname, 'minidom.js'));
const doc = makeDocument(); global.document = doc; global.window = { innerWidth: 1400 };
global.responses = []; global.currentResponseIndex = 0; global.currentData = {};
const comp = doc.createElement('div'); comp.innerHTML = '<textarea id="queryInput" placeholder="Enter your query here"></textarea><button id="submitQuery"></button><div class="tab-navigation"><button id="prevResponse"></button><span id="chainPosition"></span><button id="nextResponse"></button></div><div id="streamOutput"></div>'; doc.body.appendChild(comp);
global.clearAllTabs = () => { global.__tabsCleared = (global.__tabsCleared || 0) + 1; }; global.paneRunIds = d => { global.__ids = d; }; global.paneRunStrip = h => { global.__strip = h; }; global.updateRankButtonVisibility = () => { global.__rankSeen = true; };
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
            { number: 2, created: 1791700000, promoted_from: { thread_id: '1001', chain_id: '1791700000' }, change_note: 'the threshold became an input', manifest: { parameters: [{ key: 'threshold', label: 'Threshold', type: 'number', default: 155, origin: 'the analysis split at 155' }], results: [{ cell: 2, index: 0, label: 'rows above the line', typed: false, dropped: false, estimate: '+3.00' }, { cell: 4, index: 0, label: 'dropped one', typed: true, dropped: true, estimate: '+9' }], figures: { count: 1 } }, run_zero: { verified: true, created: 1791700000, line: 'reproduced: 2 result line(s) identical', results: [{ estimate: '+3.00', low: null, high: null }, { estimate: '+9', low: null, high: null }] } }] };
const hd = b.routineHeader(routine);
check('manager header: the name; the source, the columns, the version, and the link to the analysis it was made from (a favourite)',
  hd.title === 'Rows above a line' && hd.sub.startsWith('File · 2 columns · v2 · ') && el(hd.sub).querySelector('a.rt-origin[data-thread="1001"][data-chain="1791600000"]') && hd.sub.includes('a favourite; continue it there'));
check('manager header when the favourite is gone: no link, says so', !el(b.routineHeader(Object.assign({}, routine, { origin_available: false })).sub).querySelector('a') && b.routineHeader(Object.assign({}, routine, { origin_available: false })).sub.includes('no longer in Saved workflows'));
const bd = el(b.routineBody(routine));
check('manager body: purpose, question, the verified mark with run zero\'s line; the current version\'s inputs and results (the dropped line left out); the versions newest first with their notes; the runs table with run 0 and the run-0 item',
  bd.querySelector('.ui-kv').textContent.includes('count the rows above a line') && bd.querySelector('.rt-status.reproduced').textContent === 'verified' && bd.textContent.includes('2 result line(s) identical')
  && bd.querySelectorAll('.rt-inputs tbody tr').length === 1 && bd.querySelectorAll('.rt-results .r').length === 1 && bd.querySelector('.rt-results .r .l').textContent === 'rows above the line'
  && bd.querySelectorAll('.rt-vers .v').length === 2 && bd.querySelector('.rt-vers .v b').textContent === 'v2' && bd.querySelector('.rt-vers .v span').textContent.includes('the threshold became an input')
  && bd.querySelector('.rt-runs thead').textContent.includes('Run 0') && bd.querySelector('.rt-runlist .rt-run[data-run="0"] .rt-status').textContent === 'reproduced');
check('manager actions carry Run first', el(b.actions(routine)).querySelector('[data-act="run"]') && el(b.actions(routine)).elements[0].getAttribute('data-act') === 'run');

// ---- step 2: the run dialog ----
const rr = Object.assign({}, routine, { runs: [{ number: 1, version: 2, created: 1791700000, status: 'ran', data: { name: 'small.csv', source: 'csv', rows: 5 }, inputs: { threshold: 155 }, comparison: { moved: 0, compared: 1, line: '0 of 1 changed' }, results: [{ estimate: '+3.00', low: null, high: null }] }] });
rr.versions[1].manifest.parameters = [{ key: 'threshold', label: 'Threshold', type: 'number', default: 155, origin: 'the analysis split at 155' }, { key: 'bands', label: 'Bands', type: 'numbers', default: [130, 145] },
  { key: 'window', label: 'Window', type: 'date_window', default: ['2026-01-01', '2026-03-31'] }, { key: 'who', label: 'Groups', type: 'choice', multiple: true, column: 'g', default: ['a', 'b'] }, { key: 'flag', label: 'Flag', type: 'toggle', default: true }];
let rd = el(b.runDialog(rr, { loaded: true, ok: true, line: 'fits the routine (2 of 2 columns)', data: { name: 'small.csv', source: 'csv', rows: 5, columns: 2 } }));
check('run dialog: the data loaded now with the fit line (ok); one widget per input in its type - number, numbers as text, two dates, choice as text, a toggle; compare with the run before (on) or run 0',
  rd.querySelector('.rt-data .name').textContent === 'small.csv' && rd.querySelector('.rt-fit').textContent.startsWith('✓ fits the routine') && !rd.querySelector('.rt-fit.bad')
  && rd.querySelector('[data-key="threshold"][data-type="number"]').getAttribute('value') === '155' && rd.querySelector('[data-key="bands"][data-type="numbers"]').getAttribute('value') === '130, 145'
  && rd.querySelectorAll('[data-key="window"][data-type="date_window"]').length === 2 && rd.querySelector('[data-key="who"]').getAttribute('value') === 'a, b' && rd.querySelector('[data-key="flag"][data-type="toggle"]').hasAttribute('checked')
  && rd.querySelector('input[name="rt-compare"][value="previous"]').hasAttribute('checked') && rd.querySelector('input[name="rt-compare"][value="zero"]') && rd.textContent.includes('run 1 (') && rd.textContent.includes('the run before'));
rd = el(b.runDialog(rr, { loaded: false, ok: false, line: 'no data is loaded' }));
check('run dialog with nothing loaded: says to load the data on the Data tab', rd.querySelector('.rt-line.warn').textContent.includes('Load the data on the Data tab') && !rd.querySelector('.rt-fit'));
rd = el(b.runDialog(rr, { loaded: true, ok: false, line: 'missing: g - the routine cannot run on this data (1 of 2 columns)', data: { name: 'other.csv', source: 'csv', rows: 9, columns: 1 } }));
check('run dialog with a column missing: the fit line is bad and names the column', rd.querySelector('.rt-fit.bad').textContent.includes('missing: g'));

// ---- step 2: the comparison tab, the data tab, the runs table ----
const run3 = { number: 3, version: 2, status: 'ran', line: 'ran: 2 result lines', against: 2, data: { name: 'later.csv', source: 'csv', rows: 9, columns: [{ name: 'v', dtype: 'int64' }, { name: 'g', dtype: 'object' }] },
  comparison: { line: '1 of 2 moved beyond their intervals', compared: 2, moved: 1, within: 1, changed: 0, missing: 0,
    rows: [{ label: 'a', now: { estimate: '+1.80', low: '+1.60', high: '+2.00' }, before: { estimate: '+1.00', low: '+0.50', high: '+1.50' }, change: 0.8, overlap: false, mark: 'up' },
           { label: 'b', now: { estimate: '+3.10', low: '+2.10', high: '+4.10' }, before: { estimate: '+3.00', low: '+2.00', high: '+4.00' }, change: 0.1, overlap: true, mark: 'same' }] } };
let ct = el(b.comparisonTab({ run: run3 }));
check('comparison tab: the heading names the run, its data and the run it is against; a row per line with both estimates and intervals, the change and the mark (moved / within); the legend says no model wrote it',
  ct.querySelector('.rt-sec .h').textContent.startsWith('Run 3 (later.csv) against run 2') && ct.querySelectorAll('.rt-cmp-table tbody tr').length === 2
  && ct.querySelector('tr.up .change').textContent === '+0.8' && ct.querySelector('tr.up .rt-mark.up').textContent === '↑' && ct.querySelector('tr.up').textContent.includes('moved') && ct.querySelector('tr.same').textContent.includes('within')
  && ct.querySelector('tr.up .ci').textContent === '[+0.50, +1.50]' && ct.querySelector('.rt-legend').textContent.includes('Nothing here is written by a model'));
ct = el(b.comparisonTab({ run: { number: 0, version: 1, status: 'reproduced', against: null, data: {}, comparison: { rows: [] } } }));
check('comparison tab of run 0: nothing to compare with, pointing at the Results tab', ct.textContent.includes('Nothing to compare with') && ct.textContent.includes('Results tab'));
ct = el(b.comparisonTab({ run: { number: 4, version: 2, status: 'failed', line: 'failed at cell 2: KeyError', error: 'Traceback…', against: 3, data: {}, comparison: { rows: [{ label: 'a', now: null, before: { estimate: '+1' }, mark: 'missing' }], line: '1 missing', compared: 0 } } }));
check('comparison tab of a failed run: the error block with the line, the row marked missing', ct.querySelector('.rt-error .msg').textContent.startsWith('failed at cell 2') && ct.querySelector('tr.missing .rt-mark.missing').textContent === '·');
const dt = el(b.dataTab(run3.data));
check('data tab of a stored run: source, name, rows and the columns with their types', dt.textContent.includes('later.csv') && dt.textContent.includes('9') && dt.textContent.includes('v') && dt.textContent.includes('int64'));
const rt = Object.assign({}, routine, { runs: [
  { number: 1, version: 2, created: 1791700000, status: 'ran', data: { name: 'a.csv', source: 'csv' }, inputs: {}, comparison: { moved: 0, compared: 1 }, results: [{ estimate: '+3.00', low: '+2.00', high: '+4.00' }, { estimate: '+9', low: null, high: null }] },
  { number: 2, version: 2, created: 1791800000, status: 'ran', data: { name: 'b.csv', source: 'csv' }, inputs: { threshold: 165 }, comparison: { moved: 1, compared: 1 }, results: [{ estimate: '+5.00', low: '+4.50', high: '+5.50' }, { estimate: '+9', low: null, high: null }] },
  { number: 3, version: 2, created: 1791900000, status: 'failed', data: { name: 'c.csv', source: 'csv' }, inputs: {}, comparison: { moved: 0, compared: 0 }, results: [] }] });
rt.versions[1].run_zero.results = [{ estimate: '+3.00', low: '+2.00', high: '+4.00' }, { estimate: '+9', low: null, high: null }];
const tbl = el(b.runsTable(rt));
check('runs table: a column per run that ran (run 0 first; the failed run left out), the manifest\'s lines as rows (the dropped one left out), the mark against the column before - = within, ↑ moved - and a sparkline with three runs',
  [...tbl.querySelectorAll('thead th')].map(e => e.textContent.replace(/[A-Z][a-z]{2} \d+$/, '').trim()).join('|') === 'Result|Run 0|Run 1|Run 2|Trend' && tbl.querySelectorAll('tbody tr').length === 1
  && tbl.querySelectorAll('tbody .rt-mark.same').length === 1 && tbl.querySelectorAll('tbody .rt-mark.up').length === 1 && tbl.querySelector('tbody .rt-spark polyline'), tbl.innerHTML.slice(0, 400));
const lst = el(b.runsList(rt));
check('runs list: newest first with the data, the version, the inputs and a status chip; run 0 last; each opens', lst.querySelectorAll('.rt-run').length === 4 && lst.querySelector('.rt-run').getAttribute('data-run') === '3' && lst.querySelector('.rt-run .rt-status.failed')
  && lst.querySelector('.rt-run[data-run="2"]').textContent.includes('threshold = 165') && lst.querySelector('.rt-run[data-run="2"] .rt-status').textContent.includes('1 of 1 moved') && lst.querySelector('.rt-run[data-run="0"]') && lst.querySelectorAll('.rt-run .open').length === 4);
check('markOf: intervals apart move, overlapping ones are within, no intervals compare the estimates, a side missing is missing',
  b.markOf({ estimate: '+2', low: '+1.6', high: '+2.4' }, { estimate: '+1', low: '+0.5', high: '+1.5' }) === 'up' && b.markOf({ estimate: '+1.1', low: '+0.6', high: '+1.6' }, { estimate: '+1', low: '+0.5', high: '+1.5' }) === 'same'
  && b.markOf({ estimate: '+2' }, { estimate: '+3' }) === 'down' && b.markOf({ estimate: '+1,234' }, { estimate: '+1234' }) === 'same' && b.markOf(null, { estimate: '+1' }) === 'missing');

// ---- step 2: the run view's state - the arrows, the position, the composer, the Save pill ----
w.RoutinesUI.enterRunView({ id: 'r1', name: 'Rows above a line', current_version: 2 }, [0, 1, 2], 2, { version: 2 });
const pos = doc.querySelector('#chainPosition');
check('run view: the pane and the tabs cleared, the id line and the strip written for the run, the position reads "run 2 of 2" with the next arrow off, the composer locked, the Save pill asked to hide',
  w.RoutinesUI.inRunView() && global.__tabsCleared === 1 && global.__ids.run === '2 · v2' && global.__strip.run === 2 && pos.textContent === 'run 2 of 2' && doc.querySelector('#nextResponse').disabled === true && doc.querySelector('#prevResponse').disabled === false
  && doc.querySelector('#queryInput').disabled === true && global.__rankSeen === true, [global.__ids, pos.textContent]);
w.RoutinesUI.enterRunView({ id: 'r1', name: 'x', current_version: 2 }, [0, 1, 2, 3], 3, { version: 2, pending: true });
check('a run under way: the position says so and both arrows are off', pos.textContent === 'run 3 · running' && doc.querySelector('#prevResponse').disabled === true && doc.querySelector('#nextResponse').disabled === true);
w.RoutinesUI.exitRunView();
check('leaving the run view: not in it, the composer back', !w.RoutinesUI.inRunView() && doc.querySelector('#queryInput').disabled === false);
check('runNumbers: run 0 when verified, then every run', w.RoutinesUI.runNumbers(rt).join(',') === '0,1,2,3' && w.RoutinesUI.runNumbers(Object.assign({}, rt, { versions: [{ number: 2, run_zero: { verified: false } }] })).join(',') === '1,2,3');
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
