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
// the version choice (2026-10-12): the chain's own routine defaults to its next version, the name field holding the routine's name;
// a routine made from an earlier chain of the thread defaults to a new routine, the name the proposal's; the foot follows the choice
const ownP = Object.assign({}, proposal, { chain_id: 'c9' });
p = el(b.proposal(ownP, [{ id: 'r1', name: 'Altitude pace correction', version: 1, chain_id: 'c9' }]));
check('dialog body on the origin chain of a routine: says so; the next-version choice on, a new routine beside it (kept apart from the routine by name), the What-changed line shown, the name field holding the routine\'s name',
  p.querySelector('.rt-version').parentNode.querySelector('.h').textContent === 'This analysis is the origin of a routine'
  && p.querySelector('.rt-version .ui-choice.on[data-version="next"] b').textContent === 'Next version of “Altitude pace correction”' && p.querySelector('.rt-version .ui-choice.on span').textContent.startsWith('v2 ')
  && p.querySelector('.rt-version .ui-choice[data-version="new"] span').textContent === 'kept apart from “Altitude pace correction”' && !(p.querySelector('.rt-change').getAttribute('style') || '').includes('display:none')
  && p.querySelector('[data-field="name"]').getAttribute('value') === 'Altitude pace correction');
p = el(b.proposal(Object.assign({}, proposal, { chain_id: 'c10' }), [{ id: 'r1', name: 'Altitude pace correction', version: 1, chain_id: 'c9' }]));
check('dialog body on a later chain of the thread: "a routine was made from an earlier chain"; a new routine is the default, the What-changed line hidden, the name the proposal\'s',
  p.querySelector('.rt-version').parentNode.querySelector('.h').textContent === 'A routine was made from an earlier chain of this thread'
  && p.querySelector('.rt-version .ui-choice.on[data-version="new"]') && !p.querySelector('.rt-version .ui-choice.on[data-version="next"]') && (p.querySelector('.rt-change').getAttribute('style') || '').includes('display:none')
  && p.querySelector('[data-field="name"]').getAttribute('value') === 'Rows above a line');
const underOwn = b.underOf(ownP, [{ id: 'r2', name: 'Other', version: 3, chain_id: 'c1' }, { id: 'r1', name: 'Altitude pace correction', version: 1, chain_id: 'c9' }]);
check('underOf: the routine made from this very chain comes first, marked own; a thread routine otherwise; none without any',
  underOwn.routine.id === 'r1' && underOwn.own === true && b.underOf(Object.assign({}, proposal, { chain_id: 'c7' }), [{ id: 'r2', name: 'Other', version: 3, chain_id: 'c1' }]).own === false && b.underOf(ownP, []) === null);
const vsNext = b.versionState('next', underOwn, ownP), vsNew = b.versionState('new', underOwn, ownP), vsNone = b.versionState(null, null, ownP);
check('versionState: next -> "Make it v2", the replaces-the-current note, What-changed shown, the routine\'s name; new -> "Create routine", the apart-from note, no What-changed, the proposal\'s name; no routine -> "Create routine"',
  vsNext.label === 'Make it v2' && vsNext.note.includes('before it replaces the current one') && vsNext.change === true && vsNext.name === 'Altitude pace correction'
  && vsNew.label === 'Create routine' && vsNew.note.includes('apart from “Altitude pace correction”') && vsNew.change === false && vsNew.name === 'Rows above a line'
  && vsNone.label === 'Create routine' && vsNone.change === false && vsNone.name === 'Rows above a line', [vsNext, vsNew, vsNone]);
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
// run zero behind the dialog (2026-10-15): a routine can be verifying - the card's chip pulses and says so, the side item says so, Run is held with
// the reason; a verdict that did not reproduce holds Run for good; an older record without a status reads from `verified` as before
const verifying = JSON.parse(JSON.stringify(routine)); verifying.versions[1].run_zero = { status: 'verifying', verified: false, line: "verifying: the method is being run once on the chain's own data" };
const differed = JSON.parse(JSON.stringify(routine)); differed.versions[1].run_zero = { status: 'differed', verified: false, line: '1 of 2 lines moved' };
const vb = el(b.routineBody(verifying)), va = el(b.actions(verifying)), da = el(b.actions(differed)), db = el(b.routineBody(differed));
check('a verifying routine: the chip says verifying… (pulsing class), Run disabled with the reason; a differed verdict: the chip says did not reproduce, Run disabled with the way out; a verified one: Run live',
  vb.querySelector('.rt-status.verifying').textContent === 'verifying…' && va.querySelector('[data-act="run"]').hasAttribute('disabled') && va.querySelector('[data-act="run"]').getAttribute('title').includes('still being verified')
  && db.querySelector('.rt-status.differed').textContent === 'did not reproduce' && db.textContent.includes('1 of 2 lines moved') && da.querySelector('[data-act="run"]').hasAttribute('disabled') && da.querySelector('[data-act="run"]').getAttribute('title').includes('make it again')
  && !el(b.actions(routine)).querySelector('[data-act="run"]').hasAttribute('disabled') && b.zeroStatus({ verified: true }).includes('verified') && b.zeroStatus({}).includes('unverified'),
  [vb.querySelector('.rt-status') && vb.querySelector('.rt-status').outerHTML, va.innerHTML.slice(0, 200)]);
check('the side item says verifying… or did not reproduce from the summary card', el(b.sideItem({ id: 'x', name: 'N', source: 'file', current_version: 1, runs: 0, run_zero_status: 'verifying', created: 1791600000 }, false)).textContent.includes('verifying…')
  && el(b.sideItem({ id: 'x', name: 'N', source: 'file', current_version: 1, runs: 0, run_zero_status: 'failed', created: 1791600000 }, false)).textContent.includes('did not reproduce')
  && !el(b.sideItem({ id: 'x', name: 'N', source: 'file', current_version: 1, runs: 0, run_zero_status: 'reproduced', created: 1791600000 }, false)).textContent.includes('verifying'));
// the run dialog says what a run will take, from the last run or from run zero (2026-10-15)
const eta1 = el(b.runDialog(Object.assign({}, routine, { runs: [{ number: 1, version: 2, status: 'ran', created: 1791700100, elapsed: 512 }] }), { loaded: true, ok: true, line: 'fits', fit: { missing: [] }, data: { name: 'a.csv', source: 'csv', rows: 9, columns: 2 }, plan: { source: 'file' } })).textContent;
const eta0 = el(b.runDialog(Object.assign({}, routine, { runs: [], versions: routine.versions.map((v, i) => i === 1 ? Object.assign({}, v, { run_zero: Object.assign({}, v.run_zero, { elapsed: 45 }) }) : v) }), { loaded: true, ok: true, line: 'fits', fit: { missing: [] }, data: { name: 'a.csv', source: 'csv', rows: 9, columns: 2 }, plan: { source: 'file' } })).textContent;
const etaNone = el(b.runDialog(routine, { loaded: true, ok: true, line: 'fits', fit: { missing: [] }, data: { name: 'a.csv', source: 'csv', rows: 9, columns: 2 }, plan: { source: 'file' } })).textContent;
check('the run dialog: the last run took 9 min - expect about as long; with no run yet, the check on the original data; nothing said under half a minute',
  eta1.includes('the last run took 9 min — expect about as long') && eta0.includes('the check on the original data took 45 s') && !etaNone.includes('took'), [eta1.slice(0, 200), eta0.slice(0, 200)]);

// ---- step 2: the run dialog ----
const rr = Object.assign({}, routine, { runs: [{ number: 1, version: 2, created: 1791700000, status: 'ran', data: { name: 'small.csv', source: 'csv', rows: 5 }, inputs: { threshold: 155 }, comparison: { moved: 0, compared: 1, line: '0 of 1 changed' }, results: [{ estimate: '+3.00', low: null, high: null }] }] });
rr.versions[1].manifest.parameters = [{ key: 'threshold', label: 'Threshold', type: 'number', default: 155, origin: 'the analysis split at 155' }, { key: 'bands', label: 'Bands', type: 'numbers', default: [130, 145] },
  { key: 'window', label: 'Window', type: 'date_window', default: ['2026-01-01', '2026-03-31'] }, { key: 'who', label: 'Groups', type: 'choice', multiple: true, column: 'g', default: ['a', 'b'] }, { key: 'flag', label: 'Flag', type: 'toggle', default: true }];
let rd = el(b.runDialog(rr, { loaded: true, ok: true, line: 'fits the routine (2 of 2 columns)', data: { name: 'small.csv', source: 'csv', rows: 5, columns: 2 }, plan: { source: 'file', name: 'small.csv' } }));
check('run dialog (a file routine): the data loaded now on, with the fit line (ok), an upload as the other choice; one widget per input in its type - number, numbers as text, two dates, choice as text, a toggle; compare with the run before (on) or run 0',
  rd.querySelector('.rt-data .name').textContent === 'small.csv' && rd.querySelector('.rt-fit').textContent.startsWith('✓ fits the routine') && !rd.querySelector('.rt-fit.bad')
  && rd.querySelector('input[name="rt-data"][value="now"]').hasAttribute('checked') && rd.querySelector('input[name="rt-data"][value="upload"]') && !rd.querySelector('input[name="rt-data"][value="upload"]').hasAttribute('checked') && rd.querySelector('input[data-load="file"]')
  && rd.querySelector('[data-key="threshold"][data-type="number"]').getAttribute('value') === '155' && rd.querySelector('[data-key="bands"][data-type="numbers"]').getAttribute('value') === '130, 145'
  && rd.querySelectorAll('[data-key="window"][data-type="date_window"]').length === 2 && rd.querySelector('[data-key="who"]').getAttribute('value') === 'a, b' && rd.querySelector('[data-key="flag"][data-type="toggle"]').hasAttribute('checked')
  && rd.querySelector('input[name="rt-compare"][value="previous"]').hasAttribute('checked') && rd.querySelector('input[name="rt-compare"][value="zero"]') && rd.textContent.includes('run 1 (') && rd.textContent.includes('the run before'));
// the Dataset cache's pick (step 4, 2026-10-11): a third choice for a file routine, hidden until the page has the cache's answer; none for a loader routine
const rtSrcPick = fs.readFileSync(path.join(__dirname, '..', '..', 'web_app', 'static', 'js', 'routines.js'), 'utf8');
check('run dialog (a file routine): a hidden choice for a file from the Dataset cache with its select, shown by the page once the cache answers; a loader routine has none',
  rd.querySelector('.rt-cachepick input[name="rt-data"][value="cache"]') && rd.querySelector('.rt-cachepick').getAttribute('style').includes('display:none') && rd.querySelector('.rt-cachepick select[data-load="cached"]')
  && !el(b.runDialog(rr, { loaded: false, ok: false, line: '', plan: { source: 'intervals', window_days: 28, aux_kinds: ['summary'] } })).querySelector('.rt-cachepick')
  && rtSrcPick.includes("fetchJson('/routines/cache_files')") && rtSrcPick.includes("if (dataChoice() === 'cache')") && rtSrcPick.includes("choice === 'upload' || choice === 'cache' ? 'primary' : 'all'"));
check('a run loaded from the Dataset cache says so where its load is named', el(b.dataTab({ source: 'file', load: { source: 'file', name: 'a.csv', cached: true } }, {})).textContent.includes('File · a.csv · from the Dataset cache'));
// the run's files (2026-10-15): the executed text names the run's mirror of the recorded path, so the Data tab shows the recorded name
// against this load's file from run.sources; a stand-in reads as an empty table; an older record without sources shows the bound path
const dtF = el(b.dataTab({ source: 'intervals', load: { source: 'intervals', start_date: '2026-07-03', end_date: '2026-08-31', aux_kinds: ['summary', 'wellness'] } },
  { bindings: [['datasets/u/k/activity_summary_20260501_to_20260630.csv', 'datasets/u/routines/r/v1_1/datasets/u/k/activity_summary_20260501_to_20260630.csv', 'bound'], ['datasets/u/k/wellness_data_20260501_to_20260630.csv', 'datasets/u/routines/r/v1_1/datasets/u/k/wellness_data_20260501_to_20260630.csv', 'placeholder']],
    sources: { 'datasets/u/k/activity_summary_20260501_to_20260630.csv': 'datasets/u/k/activity_summary_20260703_to_20260831.csv' }, aux_absent: ['wellness'] })).textContent;
const dtO = el(b.dataTab({ source: 'intervals', load: { source: 'intervals', start_date: '2026-07-03', end_date: '2026-08-31' } }, { bindings: [['datasets/u/k/activity_summary_a.csv', 'datasets/u/routines/r/v1_1/activity_summary_b.csv', 'bound']] })).textContent;
check('the Data tab names each recorded file against this load\'s file (the source), a stand-in as an empty table, and an older record by its bound path',
  dtF.includes('activity_summary_20260501_to_20260630.csv → activity_summary_20260703_to_20260831.csv') && dtF.includes('wellness_data_20260501_to_20260630.csv → an empty table') && dtF.includes('wellness: absent in this data')
  && dtO.includes('activity_summary_a.csv → activity_summary_b.csv'), [dtF.slice(0, 300), dtO.slice(0, 200)]);
rd = el(b.runDialog(rr, { loaded: false, ok: false, line: 'no data is loaded', plan: { source: 'file', name: 'small.csv' } }));
check('run dialog (a file routine) with nothing loaded: the upload is the choice, on, naming the original file; Run waits for a file', rd.querySelector('input[name="rt-data"][value="upload"]').hasAttribute('checked') && rd.textContent.includes('the original: small.csv') && !rd.querySelector('input[name="rt-data"][value="now"]') && rd.querySelector('.rt-line.muted').textContent.includes('upload the file'));
rd = el(b.runDialog(rr, { loaded: true, ok: true, line: '1 of 2 columns empty in this data: g', fit: { missing: ['g'] }, data: { name: 'other.csv', source: 'csv', rows: 9, columns: 1 }, plan: { source: 'file' } }));
check('run dialog with a column missing: the fit line is a note (amber, △), not bad - the column will be empty in this data, the run adds it and the coach decides', !rd.querySelector('.rt-fit.bad') && rd.querySelector('.rt-fit.note') && rd.querySelector('.rt-fit').textContent.startsWith('△ 1 of 2 columns empty in this data: g'));
rd = el(b.runDialog(rr, { loaded: true, ok: true, line: "fits the routine (2 of 2 columns); 'b' is not in column g - the method keeps the other value", fit: { missing: [] }, values_notes: ["'b' is not in column g - the method keeps the other value"], data: { name: 'other.csv', source: 'csv', rows: 9, columns: 2 }, plan: { source: 'file' } }));
check('run dialog with one of several chosen values absent: a note (△), not a refusal - the method keeps the other value (2026-10-11)', !rd.querySelector('.rt-fit.bad') && rd.querySelector('.rt-fit.note') && rd.querySelector('.rt-fit').textContent.includes("'b' is not in column g - the method keeps the other value"));
rd = el(b.runDialog(rr, { loaded: true, ok: false, line: "none of the routine's 2 columns is in this data - nothing to run on", data: { name: 'other.csv', source: 'csv', rows: 9, columns: 1 }, plan: { source: 'file' } }));
check('run dialog with nothing of the routine\'s data: the fit line is bad, nothing to run on', rd.querySelector('.rt-fit.bad').textContent.includes('nothing to run on'));
// an Intervals routine: the load as the original did - the window of the original's length ending today, clamped to the plan's limit, the auxiliary kinds and metrics as the original; the data loaded now as the other choice
rd = el(b.runDialog(rr, { loaded: true, ok: true, line: 'fits the routine (49 of 49 columns)', data: { name: '', source: 'intervals', rows: 10200, columns: 49, date_range: '2026-08-12 to 2026-10-10' },
  plan: { source: 'intervals', window_days: 59, aux_kinds: ['summary', 'wellness'], metrics: [] } }, { max_days: 14 }));
const win = [...rd.querySelectorAll('input[data-load]')].filter(e => e.getAttribute('data-load') !== 'refresh').map(e => [e.getAttribute('data-load'), e.getAttribute('value')]);
const dayGap = (Date.parse(win[1][1]) - Date.parse(win[0][1])) / 86400000;
check('run dialog (an Intervals routine): an Everything-again box under the window, off, saying what it does (the store below the cache, 2026-10-15; worded as the load dialog\'s choice, 2026-10-16)',
  rd.querySelector('.rt-refresh input[data-load="refresh"]') && !rd.querySelector('.rt-refresh input').hasAttribute('checked') && rd.querySelector('.rt-refresh').textContent.includes('Everything again') && rd.querySelector('.rt-refresh').textContent.includes('fetch every file and message of the window afresh'));
check('run dialog (an Intervals routine): Load from Intervals.icu is the choice, on, with a start → end window ending today of the original\'s length clamped to the plan\'s limit, saying so; with summary, wellness and the metrics as the original; the data loaded now as the other choice',
  rd.querySelector('input[name="rt-data"][value="load"]').hasAttribute('checked') && rd.querySelector('.rt-check').textContent.includes('Load from Intervals.icu') && win.length === 2 && win[0][0] === 'start' && win[1][0] === 'end'
  && dayGap === 14 && rd.querySelector('.rt-load .help').textContent.includes('the original\u2019s 59 days, ending today (your plan allows 14)') && rd.querySelector('.rt-load .help').textContent.includes('with summary, wellness') && rd.querySelector('.rt-load .help').textContent.includes('metrics as the original')
  && rd.querySelector('input[name="rt-data"][value="now"]') && !rd.querySelector('input[name="rt-data"][value="now"]').hasAttribute('checked') && rd.querySelector('.rt-progress'), [win, dayGap, rd.querySelector('.rt-load') && rd.querySelector('.rt-load').textContent]);
// an input that follows the data (2026-10-11): no pickers, a line saying so and the original's dates; the make dialog's and the manager's tables say it too
const rrd = JSON.parse(JSON.stringify(rr));
rrd.versions[1].manifest.parameters = [{ key: 'band', label: 'Band', type: 'numbers', default: [9, 11] }, { key: 'span', label: 'The dates in the label', type: 'date_window', default: ['2026-07-13', '2026-10-07'], derived: 'span', origin: 'typed into the label' },
  { key: 'win', label: 'The window loaded', type: 'date_window', default: ['2026-07-12', '2026-10-10'], derived: 'window' }];
rd = el(b.runDialog(rrd, { loaded: true, ok: true, line: 'fits the routine (2 of 2 columns)', data: { name: '', source: 'intervals', rows: 5, columns: 2 }, plan: { source: 'intervals', window_days: 90, aux_kinds: [] } }));
check('run dialog: an input that follows the data has no pickers - a line says it is written at the run from the frame\'s first and last dates (or the window loaded), with the original\'s dates for the record; the band is still asked',
  rd.querySelectorAll('[data-key="span"]').length === 0 && rd.querySelectorAll('[data-key="win"]').length === 0 && rd.querySelector('[data-key="band"]')
  && rd.querySelector('.rt-derived-row[data-derived="span"] .rt-derived').textContent.includes('follows the data: its first and last dates') && rd.querySelector('.rt-derived-row[data-derived="span"] .n').textContent === 'the original: 2026-07-13 → 2026-10-07'
  && rd.querySelector('.rt-derived-row[data-derived="window"] .rt-derived').textContent.includes('the window loaded'), rd.querySelector('.rt-sec:nth-child(2)') && rd.querySelector('.rt-sec:nth-child(2)').innerHTML.slice(0, 500));
const mkd = el(b.inputsTable(rrd.versions[1].manifest.parameters, []));
check('the make dialog\'s inputs table: the row of an input that follows the data carries the mark and the line; keep fixed is still offered', mkd.querySelector('tr[data-key="span"]').getAttribute('data-derived') === 'span' && mkd.querySelector('tr[data-key="span"] .rt-derived').textContent.includes('follows the data') && mkd.querySelector('tr[data-key="span"] input[data-drop]') && !mkd.querySelector('tr[data-key="band"] .rt-derived'));
const mgd = el(b.routineBody(Object.assign({}, rrd, { summary_card: {}, origin: {} })));
check('the manager\'s inputs table says which inputs follow the data', mgd.querySelector('.rt-inputs tr[data-derived="span"] .rt-derived').textContent.includes('first and last dates') && mgd.querySelector('.rt-inputs tr[data-derived="window"] .rt-derived').textContent.includes('the window loaded'));
rd = el(b.runDialog(rr, { loaded: false, ok: false, line: 'no data is loaded', plan: { source: 'endura', race_id: 7, race_title: 'Spring classic', aux_kinds: ['profile', 'turns'] } }));
check('run dialog (an Endura routine): Load from Endura with the race list to fill, the original race named with its auxiliaries; nothing about the Data tab',
  rd.querySelector('input[name="rt-data"][value="load"]').hasAttribute('checked') && rd.querySelector('select[data-load="race"]') && rd.querySelector('.rt-race .help').textContent.includes('the original: Spring classic') && rd.querySelector('.rt-race .help').textContent.includes('with profile, turns') && !rd.textContent.includes('Data tab'));
// the cache's answer (2026-10-11): a line under the window or the race, hidden until the cache is asked; the stored run's Data tab says a cached load was one
const rdi = el(b.runDialog(rr, { loaded: false, ok: false, line: '', plan: { source: 'intervals', window_days: 30, aux_kinds: ['summary'], metrics: [] } }));
check('the run dialog carries the cache line under the window (Intervals) and under the race (Endura), hidden until the cache answers; a file routine has none',
  rdi.querySelector('.rt-load .rt-cache') && rdi.querySelector('.rt-load .rt-cache').getAttribute('style').includes('display:none') && rd.querySelector('.rt-race .rt-cache')
  && !el(b.runDialog(rr, { loaded: true, ok: true, line: 'fits', data: { name: 'a.csv', source: 'csv' }, plan: { source: 'file' } })).querySelector('.rt-cache'));
check('a run loaded from the cache says so where its load is named; one cut from a cached load around its window names that load', el(b.dataTab({ source: 'intervals', load: { source: 'intervals', start_date: '2026-07-03', end_date: '2026-08-31', aux_kinds: ['summary'], cached: true } }, {})).textContent.includes('Intervals.icu 2026-07-03 → 2026-08-31 · summary · from the cache')
  && el(b.dataTab({ source: 'endura', load: { source: 'endura', race_title: 'Flat crit', cached: true } }, {})).textContent.includes('Endura · Flat crit · from the cache')
  && el(b.dataTab({ source: 'intervals', load: { source: 'intervals', start_date: '2026-02-01', end_date: '2026-05-31', aux_kinds: ['summary'], cached: true, cached_from: ['2026-01-13', '2026-06-11'] } }, {})).textContent.includes('Intervals.icu 2026-02-01 → 2026-05-31 · summary · cut from the cached load 2026-01-13 → 2026-06-11'));
const rtSrc0 = fs.readFileSync(path.join(__dirname, '..', '..', 'web_app', 'static', 'js', 'routines.js'), 'utf8');
check('the page asks the cache as the window or the race changes (and as a date is typed), asks again for itself when Run is pressed, takes a hit through the Dataset cache routes (the frame with its athlete folder, so the other athletes\' files leave the session: one athlete at a time, 2026-10-29), and sends the load as done with the precheck and the run',
  rtSrc0.includes("fetchJson('/routines/' + encodeURIComponent(st.id) + '/cached'") && rtSrc0.includes("const c = await askCache(runState, asked);") && rtSrc0.includes("runDlg.addEventListener('input', e =>") && rtSrc0.includes("e.target.matches('input[data-load=\"start\"], input[data-load=\"end\"], select[data-load=\"race\"]')") && rtSrc0.includes("fetchJson('/cache/load_primary'") && rtSrc0.includes("body: JSON.stringify({ df_id: cached.df_id, folder: cached.folder || '' })") && rtSrc0.includes("fetchJson('/cache/load_auxiliary'")
  && rtSrc0.includes("body: JSON.stringify({ values, aux: auxLoaded, load: loadDone })") && rtSrc0.includes("{ values, compare_with, aux: auxLoaded, load: loadDone }"));
const dtl = el(b.dataTab({ source: 'intervals', rows: 9, columns: [{ name: 'v', dtype: 'int64' }], load: { source: 'intervals', start_date: '2026-09-10', end_date: '2026-10-10', aux_kinds: ['summary'] } },
  { bindings: [['datasets/u/activity_summary_20260812_to_20261010.csv', 'datasets/u/routines/r/v1_2/activity_summary_20260910_to_20261010.csv']], aux_absent: ['wellness'] }));
check('data tab of a run: how the data was loaded, and the method\'s file names bound to this load\'s (an absent one said)', dtl.textContent.includes('Loaded as') && dtl.textContent.includes('Intervals.icu 2026-09-10 → 2026-10-10 · summary')
  && dtl.textContent.includes('activity_summary_20260812_to_20261010.csv → activity_summary_20260910_to_20261010.csv') && dtl.textContent.includes('wellness: absent in this data'), dtl.textContent);
// what differed from the original's data (step 4, 2026-10-11): the record's sentences, one a line, under Differs
const dtd = el(b.dataTab({ source: 'intervals', rows: 9, columns: [] }, { differences: ['9 rows where the original had 12', 'the summary file: 6 rows where the original had 4, 1 column added empty (note)'] }));
check('data tab of a run: the sentences of what differs from the original, one a line; none when the record has none',
  dtd.textContent.includes('Differs') && dtd.textContent.includes('9 rows where the original had 12') && dtd.querySelectorAll('.rt-differs br').length === 1 && dtd.textContent.includes('1 column added empty (note)')
  && !el(b.dataTab({ source: 'csv', rows: 9, columns: [] }, {})).textContent.includes('Differs'), dtd.textContent);

// ---- step 2: the comparison tab, the data tab, the runs table ----
const run3 = { number: 3, version: 2, status: 'ran', line: 'ran: 2 result lines', against: 2, data: { name: 'later.csv', source: 'csv', rows: 9, columns: [{ name: 'v', dtype: 'int64' }, { name: 'g', dtype: 'object' }] },
  comparison: { line: '1 of 2 moved beyond their intervals', compared: 2, moved: 1, within: 1, changed: 0, missing: 0,
    rows: [{ label: 'a', now: { estimate: '+1.80', low: '+1.60', high: '+2.00' }, before: { estimate: '+1.00', low: '+0.50', high: '+1.50' }, change: 0.8, overlap: false, mark: 'up' },
           { label: 'b', now: { estimate: '+3.10', low: '+2.10', high: '+4.10' }, before: { estimate: '+3.00', low: '+2.00', high: '+4.00' }, change: 0.1, overlap: true, mark: 'same' }] } };
let ct = el(b.comparisonTab({ run: run3, against_data: { name: 'earlier.csv', source: 'csv' } }));
check('comparison tab: the heading names the run and the run it is against; each run\'s file under its column header (a file routine: no athlete named); a row per line with both estimates and intervals, the change and the mark (moved / within); the legend says no model wrote it',
  ct.querySelector('.rt-sec .h').textContent.startsWith('Run 3 against run 2 — v2 ·') && !ct.querySelector('.rt-sec .h').textContent.includes('athlete') && [...ct.querySelectorAll('thead th .when')].map(e => e.textContent).join('|') === 'earlier.csv|later.csv' && ct.querySelectorAll('.rt-cmp-table tbody tr').length === 2
  && ct.querySelector('tr.up .change').textContent === '+0.8' && ct.querySelector('tr.up .rt-mark.up').textContent === '↑' && ct.querySelector('tr.up').textContent.includes('moved') && ct.querySelector('tr.same').textContent.includes('within')
  && ct.querySelector('tr.up .ci').textContent === '[+0.50, +1.50]' && ct.querySelector('.rt-legend').textContent.includes('Nothing here is written by a model'), ct.querySelector('.rt-sec .h').textContent);
ct = el(b.comparisonTab({ run: { number: 0, version: 1, status: 'reproduced', against: null, data: {}, comparison: { rows: [] } } }));
check('comparison tab of run 0: nothing to compare with, pointing at the Results tab', ct.textContent.includes('Nothing to compare with') && ct.textContent.includes('Results tab'));
// whose and when (2026-10-30): the athlete in the heading when both runs are theirs, each run's athlete when not; the window under each header
const onA = { source: 'intervals', subject: { id: 'i0', name: 'First Athlete' }, window: ['2026-07-22', '2026-09-19'], date_range: '2026-07-22 to 2026-09-19' };
const runA = Object.assign({}, run3, { number: 6, against: 5, data: { source: 'intervals', load: { source: 'intervals', start_date: '2026-09-01', end_date: '2026-10-30', subject: { source: 'intervals', id: 'i0', name: 'First Athlete' } }, date_range: '2026-09-01 to 2026-10-30' } });
ct = el(b.comparisonTab({ run: runA, against_data: onA }));
const ctB = el(b.comparisonTab({ run: runA, against_data: Object.assign({}, onA, { subject: { id: 'i1', name: 'Second Athlete' } }) }));
const ctN = el(b.comparisonTab({ run: Object.assign({}, runA, { against: null, comparison: { line: 'nothing to compare with: the first run on this subject', rows: [{ label: 'a', now: { estimate: '+1' }, before: null, mark: 'missing' }] } }) }));
const ctU = el(b.comparisonTab({ run: runA, against_data: { source: 'intervals', date_range: '2026-05-01 to 2026-06-30' } }));
const ct0 = el(b.comparisonTab({ run: { number: 0, version: 1, status: 'reproduced', against: null, data: { source: 'intervals', load: { source: 'intervals', start_date: '2026-07-22', end_date: '2026-09-19', subject: { id: 'i0', name: 'First Athlete' } } }, comparison: { rows: [{ label: 'a', now: { estimate: '+1' } }] } } }));
check('comparison tab by athlete: the same athlete on both sides is named once in the heading, with the windows under the headers (the run\'s from its load, the reference\'s from its summary); different athletes are named on each run; one not recorded says so; a first run on an athlete has no reference - its own line above a single column with its window; run 0 names its athlete',
  ct.querySelector('.rt-sec .h').textContent === 'Run 6 against run 5 — First Athlete · v2 · 1 of 2 moved beyond their intervals' && [...ct.querySelectorAll('thead th .when')].map(e => e.textContent).join('|') === '2026-07-22 → 2026-09-19|2026-09-01 → 2026-10-30'
  && ctB.querySelector('.rt-sec .h').textContent.startsWith('Run 6 (First Athlete) against run 5 (Second Athlete) — v2 ·') && ctU.querySelector('.rt-sec .h').textContent.startsWith('Run 6 (First Athlete) against run 5 (athlete not recorded) — v2 ·')
  && ctN.querySelector('.rt-sec .h').textContent === 'Run 6 — First Athlete · v2' && ctN.querySelector('.rt-line.muted').textContent === 'nothing to compare with: the first run on this subject' && [...ctN.querySelectorAll('thead th')].length === 2 && ctN.querySelector('thead th .when').textContent === '2026-09-01 → 2026-10-30'
  && ct0.querySelector('.rt-sec .h').textContent === 'Run 0 — the original data — First Athlete · v1' && ct0.querySelector('thead th .when').textContent === '2026-07-22 → 2026-09-19', [ct.querySelector('.rt-sec .h').textContent, ctB.querySelector('.rt-sec .h').textContent, ctN.textContent.slice(0, 200)]);
check('whoOf / whenOf: the athlete from a summary\'s subject or a record\'s load; the window from the summary\'s window, the load\'s dates or the date range, else the race or the file',
  b.whoOf({ subject: { id: 'i0', name: 'First Athlete' } }) === 'First Athlete' && b.whoOf({ load: { subject: { id: 'i1' } } }) === 'i1' && b.whoOf({ name: 'a.csv' }) === ''
  && b.whenOf({ window: ['2026-01-01', '2026-02-01'], date_range: '2025-01-01 to 2025-06-01' }) === '2026-01-01 → 2026-02-01' && b.whenOf({ load: { start_date: '2026-01-01', end_date: '2026-02-01' } }) === '2026-01-01 → 2026-02-01'
  && b.whenOf({ date_range: '2026-01-01 to 2026-02-01' }) === '2026-01-01 → 2026-02-01' && b.whenOf({ extra: { race_title: 'Spring classic' } }) === 'Spring classic' && b.whenOf({ name: 'a.csv' }) === 'a.csv' && b.whenOf({}) === '');
check('the Data tab\'s "Loaded as" names the athlete of an Intervals load after the source; a load without one reads as before',
  el(b.dataTab({ source: 'intervals', load: { source: 'intervals', start_date: '2026-09-01', end_date: '2026-10-30', aux_kinds: ['summary'], subject: { source: 'intervals', id: 'i0', name: 'First Athlete' } } }, {})).textContent.includes('Loaded asIntervals.icu · First Athlete · 2026-09-01 → 2026-10-30 · summary')
  && el(b.dataTab({ source: 'intervals', load: { source: 'intervals', start_date: '2026-09-01', end_date: '2026-10-30', aux_kinds: ['summary'] } }, {})).textContent.includes('Loaded asIntervals.icu 2026-09-01 → 2026-10-30 · summary'));
ct = el(b.comparisonTab({ run: { number: 4, version: 2, status: 'failed', line: 'failed at cell 2: KeyError', error: 'Traceback…', against: 3, data: {}, comparison: { rows: [{ label: 'a', now: null, before: { estimate: '+1' }, mark: 'missing' }], line: '1 missing', compared: 0 } } }));
check('comparison tab of a failed run: the error block with the line, the row marked missing', ct.querySelector('.rt-error .msg').textContent.startsWith('failed at cell 2') && ct.querySelector('tr.missing .rt-mark.missing').textContent === '·');
// fail well (step 4, 2026-10-11): the failed cell's code beside the traceback; a line the run did not reach is 'not reached', a line printed before the failure compared
ct = el(b.comparisonTab({ run: { number: 5, version: 2, status: 'failed', line: 'failed at cell 2: KeyError', error: 'Traceback…\nKeyError: v', failed_cell: { number: 2, code: "x = df['v'].sum()\nRESULT('rows', x, None, None, '', '')" }, against: 4, data: {},
  comparison: { rows: [{ label: 'first', now: { estimate: '+3' }, before: { estimate: '+3' }, mark: 'same', overlap: null, change: 0 }, { label: 'second', now: null, before: { estimate: '+1' }, mark: 'unreached' }], line: '0 of 1 changed before the failure, 1 not reached', compared: 1, unreached: 1 } } }));
check('comparison tab of a failed run: the failed cell\'s code under its own heading beside the error, the line printed before the failure compared and the one after it "not reached", the legend explaining it',
  ct.querySelector('.rt-error .rt-error-cell .h').textContent === 'cell 2 — the code that failed' && ct.querySelector('.rt-error .rt-error-cell code').textContent.includes("df['v'].sum()") && ct.querySelector('.rt-error .rt-error-tb pre').textContent.includes('KeyError: v')
  && ct.querySelector('tr.same') && ct.querySelector('tr.unreached').textContent.includes('not reached') && ct.querySelector('.rt-legend').textContent.includes('"not reached" is a line the run failed before printing'), ct.innerHTML.slice(0, 600));
const dt = el(b.dataTab(run3.data));
check('data tab of a stored run: source, name, rows and the columns with their types', dt.textContent.includes('later.csv') && dt.textContent.includes('9') && dt.textContent.includes('v') && dt.textContent.includes('int64'));
const rt = Object.assign({}, routine, { runs: [
  { number: 1, version: 2, created: 1791700000, status: 'ran', data: { name: 'a.csv', source: 'csv' }, inputs: {}, comparison: { moved: 0, compared: 1 }, results: [{ estimate: '+3.00', low: '+2.00', high: '+4.00' }, { estimate: '+9', low: null, high: null }] },
  { number: 2, version: 2, created: 1791800000, status: 'ran', data: { name: 'b.csv', source: 'csv' }, inputs: { threshold: 165 }, comparison: { moved: 1, compared: 1 }, results: [{ estimate: '+5.00', low: '+4.50', high: '+5.50' }, { estimate: '+9', low: null, high: null }] },
  { number: 3, version: 2, created: 1791900000, status: 'failed', data: { name: 'c.csv', source: 'csv' }, inputs: {}, comparison: { moved: 0, compared: 0 }, results: [] }] });
rt.versions[1].run_zero.results = [{ estimate: '+3.00', low: '+2.00', high: '+4.00' }, { estimate: '+9', low: null, high: null }];
const tbl = el(b.runsTable(rt));
check('runs table: a column per run that ran (run 0 first; the failed run left out), the manifest\'s lines as rows (the dropped one left out), the mark in its own column between the two numbers it compares - = within, ↑ moved - and a sparkline under Trend with three runs',
  [...tbl.querySelectorAll('thead th')].map(e => e.textContent.replace(/[A-Z][a-z]{2} \d+$/, '').trim()).join('|') === 'Result|Run 0||Run 1||Run 2|Trend' && tbl.querySelectorAll('tbody tr').length === 1
  && [...tbl.querySelectorAll('tbody td')].map(td => td.className).join('|') === 'label|num|mark|num|mark|num|'
  && [...tbl.querySelectorAll('tbody td.mark')].map(td => td.textContent).join('') === '=↑' && tbl.querySelector('tbody .rt-spark polyline'), [...tbl.querySelectorAll('tbody td')].map(td => td.className + ':' + td.textContent).join(' '));
const tbl2 = el(b.runsTable(Object.assign({}, rt, { runs: rt.runs.slice(0, 1) })));
check('runs table with two runs: no Trend column (nothing to draw yet), the mark between the numbers',
  [...tbl2.querySelectorAll('thead th')].map(e => e.textContent.replace(/[A-Z][a-z]{2} \d+$/, '').trim()).join('|') === 'Result|Run 0||Run 1' && tbl2.querySelector('tbody td.mark .rt-mark.same') && !tbl2.querySelector('.rt-spark') && !tbl2.textContent.includes('Trend'), tbl2.innerHTML.slice(0, 300));
const lst = el(b.runsList(rt));
check('runs list: newest first with the data, the version, the inputs and a status chip; run 0 last; each opens', lst.querySelectorAll('.rt-run').length === 4 && lst.querySelector('.rt-run').getAttribute('data-run') === '3' && lst.querySelector('.rt-run .rt-status.failed')
  && lst.querySelector('.rt-run[data-run="2"]').textContent.includes('threshold = 165') && lst.querySelector('.rt-run[data-run="2"] .rt-status').textContent.includes('1 of 1 moved') && lst.querySelector('.rt-run[data-run="0"]') && lst.querySelectorAll('.rt-run .open').length === 4);
check('markOf: intervals apart move, overlapping ones are within, no intervals compare the estimates, a side missing is missing',
  b.markOf({ estimate: '+2', low: '+1.6', high: '+2.4' }, { estimate: '+1', low: '+0.5', high: '+1.5' }) === 'up' && b.markOf({ estimate: '+1.1', low: '+0.6', high: '+1.6' }, { estimate: '+1', low: '+0.5', high: '+1.5' }) === 'same'
  && b.markOf({ estimate: '+2' }, { estimate: '+3' }) === 'down' && b.markOf({ estimate: '+1,234' }, { estimate: '+1234' }) === 'same' && b.markOf(null, { estimate: '+1' }) === 'missing');

// ---- whose runs (2026-10-30, docs/DATASETS_DESIGN.md §17 step 3): the athlete in the run dialog; the comparison and the history within one athlete's runs ----
const two = JSON.parse(JSON.stringify(rt));
two.versions[1].manifest.data = { columns: [{ name: 'v' }], load: { source: 'intervals', subject: { source: 'intervals', id: 'i0', name: 'First Athlete' } } };
const onRun = (n, created, id, name, est) => ({ number: n, version: 2, created, status: 'ran', data: { name: '', source: 'intervals', subject: id ? { id, name } : {} }, inputs: {}, comparison: { moved: 0, compared: 1 }, results: [{ estimate: est, low: null, high: null }, { estimate: '+9', low: null, high: null }] });
two.runs = [onRun(1, 1791700000, 'i0', 'First Athlete', '+3.00'), onRun(2, 1791800000, 'i1', 'Second Athlete', '+5.00'), onRun(3, 1791900000, 'i0', 'First Athlete', '+3.50')];
rd = el(b.runDialog(two, { loaded: false, ok: false, line: '', plan: { source: 'intervals', window_days: 30, aux_kinds: ['summary'], metrics: [], subject: { id: 'i0', name: 'First Athlete' } } }));
check('run dialog (an Intervals routine): the athlete above the window - a select to fill, with its help line - and the comparison for the original\'s athlete: the run before on them (run 3, on) and run 0',
  rd.querySelector('.rt-load .rt-athlete select[data-load="athlete"]') && rd.querySelector('.rt-load').elements.map(e => e.className).join('|').includes('rt-field rt-athlete|rt-window rt-loadwin') && rd.querySelector('.rt-athlete .rt-athlete-help')
  && rd.querySelector('.rt-compare-sec input[name="rt-compare"][value="previous"]').hasAttribute('checked') && rd.querySelector('.rt-compare-sec').textContent.includes('run 3 (') && rd.querySelector('.rt-compare-sec').textContent.includes('the run before on First Athlete')
  && rd.querySelector('.rt-compare-sec input[name="rt-compare"][value="zero"]'), rd.querySelector('.rt-compare-sec') && rd.querySelector('.rt-compare-sec').textContent);
const v2 = two.versions[1];
const cmp = (id, name) => el(b.compareSection(two, v2, id, name));
check('compareSection: the second athlete - their one run before (run 2), no run 0 (it ran on the first athlete\'s data); a third athlete - the first run on them, nothing to compare with yet, no radios',
  cmp('i1', 'Second Athlete').textContent.includes('run 2 (') && cmp('i1', 'Second Athlete').textContent.includes('the run before on Second Athlete') && !cmp('i1', 'Second Athlete').querySelector('input[value="zero"]')
  && cmp('i2', 'Third Athlete').textContent.includes('the first run on Third Athlete: nothing to compare with yet') && !cmp('i2', 'Third Athlete').querySelector('input[name="rt-compare"]'), cmp('i2', 'Third Athlete').textContent);
const noZero = JSON.parse(JSON.stringify(two)); noZero.versions[1].manifest.data = { columns: [] };
check('compareSection: a run 0 that names no athlete (from before the athlete was kept) is nobody\'s - not offered to the second athlete (their run 2 alone) nor to a third (nothing to compare with yet); it is the subject-less runs\' (a file routine: offered, on)',
  !el(b.compareSection(noZero, noZero.versions[1], 'i1', 'Second Athlete')).querySelector('input[value="zero"]') && el(b.compareSection(noZero, noZero.versions[1], 'i1', 'Second Athlete')).querySelector('input[value="previous"]')
  && el(b.compareSection(noZero, noZero.versions[1], 'i2', 'Third Athlete')).textContent.includes('the first run on Third Athlete: nothing to compare with yet') && !el(b.compareSection(noZero, noZero.versions[1], 'i2', 'Third Athlete')).querySelector('input[name="rt-compare"]')
  && el(b.compareSection(noZero, noZero.versions[1], '', '')).querySelector('input[value="zero"]').hasAttribute('checked'));
check('runAthletes: the athletes the routine ran on, the latest run\'s first, with their counts (run 0 counted for its athlete); a run 0 or a run naming none makes the "athlete not recorded" group',
  b.runAthletes(two).map(a => a.id + ':' + a.name + ':' + a.n).join('|') === 'i0:First Athlete:3|i1:Second Athlete:1' && b.runAthletes(noZero).map(a => a.id + ':' + a.n).join('|') === 'i0:2|i1:1|:1' && b.runAthletes(Object.assign({}, noZero, { runs: [] })).map(a => a.id + ':' + a.n).join('|') === ':1'
  && el(b.routineBody(Object.assign({}, noZero, { summary_card: {}, origin: {} }))).querySelector('select[data-pick="athlete"] option[value=""]').textContent === 'athlete not recorded · 1 run', b.runAthletes(noZero));
const tb0 = el(b.runsTable(two, 'i0')), tb1 = el(b.runsTable(two, 'i1')), tbAll = el(b.runsTable(two));
check('runs table by athlete: the first athlete\'s columns are run 0, 1 and 3; the second\'s run 2 alone (no run 0); unfiltered, every run',
  [...tb0.querySelectorAll('thead th')].map(e => e.textContent.replace(/[A-Z][a-z]{2} \d+$/, '').trim()).filter(Boolean).join('|') === 'Result|Run 0|Run 1|Run 3|Trend' && [...tb1.querySelectorAll('thead th')].map(e => e.textContent.replace(/[A-Z][a-z]{2} \d+$/, '').trim()).filter(Boolean).join('|') === 'Result|Run 2'
  && [...tbAll.querySelectorAll('thead th')].map(e => e.textContent.replace(/[A-Z][a-z]{2} \d+$/, '').trim()).filter(Boolean).join('|') === 'Result|Run 0|Run 1|Run 2|Run 3|Trend', [tb0.textContent, tb1.textContent]);
const ls1 = el(b.runsList(two, 'i1')), lsAll = el(b.runsList(two));
check('runs list by athlete: the second athlete\'s run alone, named with the athlete; unfiltered, every run and run 0, each naming its athlete',
  [...ls1.querySelectorAll('.rt-run')].map(e => e.getAttribute('data-run')).join(',') === '2' && ls1.querySelector('.rt-run').textContent.includes('Intervals.icu · Second Athlete')
  && [...lsAll.querySelectorAll('.rt-run')].map(e => e.getAttribute('data-run')).join(',') === '3,2,1,0' && lsAll.querySelector('.rt-run[data-run="1"]').textContent.includes('· First Athlete'));
const mb2 = el(b.routineBody(Object.assign({}, two, { summary_card: {}, origin: {} })));
check('the manager with runs on two athletes: a pick in the Results heading (the latest run\'s athlete selected, each with its count), the table and the list filtered to them, the Runs heading naming them; one athlete - no pick',
  mb2.querySelector('.rt-sec .h select[data-pick="athlete"]') && mb2.querySelector('select[data-pick="athlete"] option[selected]').getAttribute('value') === 'i0' && mb2.querySelector('select[data-pick="athlete"] option[selected]').textContent === 'First Athlete · 3 runs'
  && [...mb2.querySelectorAll('.rt-runs thead th')].map(e => e.textContent.replace(/[A-Z][a-z]{2} \d+$/, '').trim()).filter(Boolean).join('|') === 'Result|Run 0|Run 1|Run 3|Trend' && [...mb2.querySelectorAll('.rt-run')].map(e => e.getAttribute('data-run')).join(',') === '3,1,0'
  && [...mb2.querySelectorAll('.rt-sec .h')].some(h => h.textContent.includes('a run opens in the main panes · First Athlete')) && !el(b.routineBody(Object.assign({}, rt, { summary_card: {}, origin: {} }))).querySelector('select[data-pick="athlete"]'), mb2.querySelector('select[data-pick="athlete"]') && mb2.querySelector('select[data-pick="athlete"]').outerHTML);
const rtSrc1 = fs.readFileSync(path.join(__dirname, '..', '..', 'web_app', 'static', 'js', 'routines.js'), 'utf8');
check('the page fills the athletes once the dialog is up (the keys and the cache\'s tree, the paperclip\'s roster order), re-renders the comparison and asks the cache as the athlete changes, names the athlete on the cache question, the load (with their name, for the refusal) and the record, and the manager\'s pick re-renders the body',
  rtSrc1.includes("if (src === 'intervals') fillAthletes(p, runState.plan);") && rtSrc1.includes("fetchJson('/intervals/athletes'), fetchJson('/cache/inspect')") && rtSrc1.includes("intervalsRosterOf(keyed, tree)")
  && rtSrc1.includes("if (e.target.matches('select[data-load=\"athlete\"]')) athleteChanged();") && rtSrc1.includes("asked.subject ? { athlete: asked.subject.id } : {}") && rtSrc1.includes("who.id ? { athlete: who.id, athlete_name: who.name || '' } : {}")
  && rtSrc1.includes("a.id ? { subject: { source: 'intervals', id: a.id, name: a.name } } : {}") && rtSrc1.includes("managerState.athlete = pick.value;") && rtSrc1.includes("if (c === 'now') return (((runState && runState.pre && runState.pre.data) || {}).subject) || {};"));
check('the cache line shows the latest question\'s answer only: an earlier answer arriving late is dropped (the athlete\'s question and the window\'s race)', rtSrc1.includes("const seq = ++cacheSeq;") && rtSrc1.includes("if (runState === st && seq === cacheSeq) showCache(p, c);") && rtSrc1.includes("cacheSeq++;"));
check('Run waits for the athletes of an Intervals routine: the select starts as loading, Run is off until it is ready (a load before would take whichever key was used last); a routine without the select is as before',
  rd.querySelector('select[data-load="athlete"]').getAttribute('data-state') === 'loading' && rtSrc1.includes("on = !a || a.getAttribute('data-state') === 'ready';") && rtSrc1.includes("sel.setAttribute('data-state', 'ready');") && rtSrc1.includes("sel.setAttribute('data-state', 'failed'); updateRunButton();"));

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
// the arrows within one athlete (2026-10-30): the numbers of their runs alone, run 0 when it is theirs; the position names them
check('runNumbers by athlete: the first athlete\'s run 0, 1 and 3; the second\'s run 2 alone; a run 0 naming none belongs to the subject-less group only',
  w.RoutinesUI.runNumbers(two, 'i0').join(',') === '0,1,3' && w.RoutinesUI.runNumbers(two, 'i1').join(',') === '2' && w.RoutinesUI.runNumbers(noZero, 'i0').join(',') === '1,3' && w.RoutinesUI.runNumbers(noZero, '').join(',') === '0' && w.RoutinesUI.runNumbers(two).join(',') === '0,1,2,3');
w.RoutinesUI.enterRunView({ id: 'r1', name: 'Rows above a line', current_version: 2 }, [0, 1, 3], 1, { version: 2, subject: { id: 'i0', name: 'First Athlete' } });
check('the run view on an athlete\'s runs: the position reads "run 1 of 3 · First Athlete", the id line carries the name, both arrows on; a pending run on them says running with the name',
  pos.textContent === 'run 1 of 3 · First Athlete' && global.__ids.run === '1 · v2 · First Athlete' && doc.querySelector('#prevResponse').disabled === false && doc.querySelector('#nextResponse').disabled === false
  && (w.RoutinesUI.enterRunView({ id: 'r1', name: 'x', current_version: 2 }, [2, 4], 1, { version: 2, pending: true, subject: { id: 'i1', name: 'Second Athlete' } }), pos.textContent === 'run 4 · running · Second Athlete'), [pos.textContent, global.__ids]);
w.RoutinesUI.exitRunView();
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
// the executor chip (2026-10-10, Palo's test: it stayed on Executing after a run): the routine's ROUTINE / RUN rows set it as a
// cell does, so their completion releases it as the replay's does; the closing card and a broken stream release it too
const lookupLine = qp.split('\n').find(l => l.includes('data.type === "pane_lookup")')) || '';
const rtSrc = fs.readFileSync(path.join(__dirname, '..', '..', 'web_app', 'static', 'js', 'routines.js'), 'utf8');
check('the executor chip goes back to its polled status when the ROUTINE or RUN row completes, on the closing card, and when the run\'s stream breaks',
  lookupLine.includes("data.kind === 'replay' || data.kind === 'routine' || data.kind === 'run'") && lookupLine.includes('setExecuting(false)')
  && rtSrc.includes("paneRoutineEnd(data); chipIdle();") && /catch\(err => \{\s*chipIdle\(\);/.test(rtSrc) && rtSrc.includes('function chipIdle() { if (window.containerStatus'),
  lookupLine.slice(0, 200));
const wm = fs.readFileSync(path.join(__dirname, '..', '..', 'web_app', 'static', 'js', 'workflow-modal.js'), 'utf8');
check('the favourites\' cards carry the Routine button in place of the v1 Replay button, bound through RoutinesUI', wm.includes('window.RoutinesUI.cardButton(') && wm.includes('window.RoutinesUI.bindCardButton(routineBtn') && !wm.includes('class="workflow-card-replay"'));
const core = fs.readFileSync(path.join(__dirname, '..', '..', 'web_app', 'static', 'js', 'core.js'), 'utf8');
check('routines.js is initialised after auth with the other modules', core.includes('window.RoutinesUI.initialize()'));
// a load clears what it replaces (2026-10-11): the pills go the way their x takes them (file-management's removeDatasetPill, quiet);
// here, without file-management, the fallback removes the elements - an upload clears the primary and keeps the auxiliaries
const pc = doc.createElement('div'); pc.setAttribute('id', 'datasetStatusPillsContainer'); doc.body.appendChild(pc);
pc.innerHTML = '<div class="dataset-status-pill intervals-dataset-pill success" data-dataset-type="intervals"></div><div class="dataset-status-pill auxiliary-dataset-pill success" data-dataset-type="auxiliary" data-identifier="datasets/u/wellness_data_x.csv"></div><div class="dataset-status-pill primary-dataset-pill success" data-dataset-type="primary"></div>';
const fm = fs.readFileSync(path.join(__dirname, '..', '..', 'web_app', 'static', 'js', 'file-management.js'), 'utf8');
(async () => {
  const n1 = await window.RoutinesUI.clearLoaded('primary');
  const left = [...doc.querySelectorAll('.dataset-status-pill')].map(e => e.dataset.datasetType);
  const n2 = await window.RoutinesUI.clearLoaded('all');
  check('clearLoaded: an upload clears the primary pills and keeps the auxiliaries; a load from an integration clears everything; file-management exposes the removal the x uses, with a quiet mode for this',
    n1 === 2 && left.join(',') === 'auxiliary' && n2 === 1 && doc.querySelectorAll('.dataset-status-pill').length === 0
    && fm.includes('async function removeDatasetPill(pillElement, removeButton, quiet = false)') && fm.includes('return removeDatasetPill(document.getElementById(removeButton.dataset.pillId), removeButton);'), [n1, left, n2]);
  check('startRun clears what the load replaces before loading - the primary for an upload or a cache pick, everything for an integration', rtSrc.includes("await clearLoaded(choice === 'upload' || choice === 'cache' ? 'primary' : 'all');"));
  finish();
})();

function finish() {
  let fails = 0; for (const [n, ok, d] of results) { console.log((ok ? '  ok   ' : '  FAIL ') + n + (ok ? '' : '  <- ' + (d || ''))); if (!ok) fails++; }
  console.log(`\n${results.length - fails} passed, ${fails} failed`); process.exit(fails ? 1 : 0);
}
