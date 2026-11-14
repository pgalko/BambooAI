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
window.DateWindow = require(path.join(__dirname, '..', '..', 'web_app', 'static', 'js', 'integrations', 'intervals.js')).DateWindow;     // the plan's reach and window (2026-11-08): the run dialog's custom pickers read it
global.localIsoDay = d => d.getFullYear() + '-' + String(d.getMonth() + 1).padStart(2, '0') + '-' + String(d.getDate()).padStart(2, '0');
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
  && [...p.querySelectorAll('.rt-sec .h')].some(h => h.textContent.includes('2 of 2 · 1 figure')));
check('dialog body: without a routine on the thread there is no version choice', !p.querySelector('.rt-version'));
// the promoter's pick (§15.2): the lines kept listed by name with the recorded wording on hover and drop at hand; the lines set
// aside behind one muted line that opens; a typed line visible with its choice following the pick; the head counting
const picked = Object.assign({}, proposal, { results: [
  { cell: 2, index: 0, label: 'the count, first form, 21 rows', typed: false, dropped: true, estimate: '3' },
  { cell: 3, index: 0, label: 'the count, a check with the rows dropped', typed: false, dropped: true, estimate: '2' },
  { cell: 4, index: 0, label: 'the count, final form, 21 rows', typed: false, dropped: false, estimate: '3', name: 'The count' },
  { cell: 4, index: 1, label: 'a typed one', typed: true, dropped: true, estimate: '9' }] });
let ps = el('<div class="rt-sec">' + b.resultsSection(picked, false) + '</div>');
check('dialog, a pick (in the coach\'s words, 2026-11-08): the head "Tracked metrics — recomputed each run and compared with the run before, 1 of 4"; the tracked line by its name with the recorded label as its title, its cell and a drop button; the typed line in place, its choice on drop; the set-aside lines folded behind "2 more metrics computed, not tracked"',
  ps.querySelector('.h').textContent === 'Tracked metrics — recomputed each run and compared with the run before, 1 of 4 · 1 figure' && [...ps.querySelectorAll('.rt-results .r')].map(r => r.getAttribute('data-line')).join(',') === '2,3'
  && ps.querySelector('.rt-results .r[data-line="2"] .l').textContent === 'The count' && ps.querySelector('.rt-results .r[data-line="2"] .l').getAttribute('title') === 'the count, final form, 21 rows'
  && ps.querySelector('.rt-results .r[data-line="2"] .c').textContent === 'cell 4' && ps.querySelector('.rt-results .r[data-line="2"] .act[data-line-act="drop"]').textContent === 'drop'
  && ps.querySelector('.rt-results .r.flag[data-line="3"] .ui-seg .on').getAttribute('data-keep') === '0'
  && ps.querySelector('.rt-results .more .t[data-line-act="more"]').textContent === '▸ 2 more metrics computed, not tracked' && !ps.querySelector('.rt-results .more.open') && !ps.querySelector('.rt-results .aside'), ps.innerHTML);
ps = el('<div class="rt-sec">' + b.resultsSection(picked, true) + '</div>');
check('dialog, the group opened: the set-aside lines greyed under the line, each with its recorded wording, its cell and a track button; the tracked list unchanged',
  ps.querySelector('.rt-results .more.open .t').textContent === '▾ 2 more metrics computed, not tracked' && [...ps.querySelectorAll('.rt-results .aside .r')].map(r => r.getAttribute('data-line')).join(',') === '0,1'
  && ps.querySelectorAll('.rt-results .aside .r.off').length === 2 && ps.querySelector('.rt-results .aside .r[data-line="0"] .l').textContent === 'the count, first form, 21 rows' && ps.querySelector('.rt-results .aside .r[data-line="1"] .c').textContent === 'cell 3'
  && [...ps.querySelectorAll('.rt-results .aside .act[data-line-act="keep"]')].map(a => a.textContent).join() === 'track,track' && [...ps.querySelectorAll('.rt-results .r')].filter(r => !r.closest('.aside')).map(r => r.getAttribute('data-line')).join(',') === '2,3', ps.innerHTML);
check('dialog, no pick (every line kept, as before the pick): the head counts "2 of 2", no muted line, every computed line ticked with a drop button; one line set aside reads "1 more metric"',
  el(b.resultsSection(proposal, false)).textContent.includes('2 of 2 · 1 figure') && !el(b.resultsList(proposal.results, false)).querySelector('.more') && el(b.resultsList(proposal.results, false)).querySelectorAll('.r .act[data-line-act="drop"]').length === 1
  && el(b.resultsList([picked.results[0], picked.results[2]], false)).querySelector('.more .t').textContent === '▸ 1 more metric computed, not tracked');
check('lineName: the promoter\'s name when there is one, else the label trimmed of its trailing date range and count',
  b.lineName({ name: 'The count', label: 'the count, final form, 21 rows' }) === 'The count' && b.lineName({ label: 'the count, final form, all 21 rows, 2026-10-05..2026-11-06' }) === 'the count, final form' && b.lineName({}) === '');
// the Custom instructions section (§15.6): after the tracked metrics, optional, explained in plain words; the box holding the
// proposal's line; Update the list; the Notes section after it, so a note about a metric not computed sits under the box
const pi = el(b.proposal(Object.assign({}, proposal, { instruction: 'track the best power at 5 s and 1 min', notes: ['Not computed in this analysis, so it can’t be tracked: best 3 h power.'] }), []));
const secHeads = [...pi.querySelectorAll('.rt-sec')].map(d => d.querySelector('.h').textContent);
check('dialog: the Custom instructions section follows the Tracked metrics one and precedes the Notes; its head says optional; the explanation reads as the coach would hear it; the box carries the proposal\'s line with an example as its placeholder and a 300-character cap; the button says Update the list',
  secHeads.indexOf('Custom instructions — optional') === secHeads.findIndex(t => t.startsWith('Tracked metrics')) + 1 && secHeads.indexOf('Notes') === secHeads.indexOf('Custom instructions — optional') + 1
  && pi.querySelector('.rt-instr .rt-line.muted').textContent === 'If you want this routine to track particular metrics, say so here and the model building it will add them to the list above — for example the power durations that matter to you. It can only track what the analysis computed; if something you ask for isn’t there, it will tell you.'
  && pi.querySelector('.rt-instr .rt-instr-row input[data-field="instruction"]').getAttribute('value') === 'track the best power at 5 s and 1 min'
  && pi.querySelector('.rt-instr input[data-field="instruction"]').getAttribute('placeholder') === 'e.g. track the best power at 5 s, 1 min, 5 min, 20 min and 1 h, and critical power' && pi.querySelector('.rt-instr input').getAttribute('maxlength') === '300'
  && pi.querySelector('.rt-instr .rt-instr-row button[data-act="instruct"]').textContent === 'Update the list' && [...pi.querySelectorAll('.rt-sec')].pop().querySelector('.rt-line').textContent === 'Not computed in this analysis, so it can’t be tracked: best 3 h power.', secHeads);
check('dialog: without a line the box is empty; the section is there all the same', el(b.proposal(proposal, [])).querySelector('.rt-instr input[data-field="instruction"]').getAttribute('value') === '');
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
  && [...p.querySelectorAll('.rt-line')].some(x => x.textContent.includes('recorded no metrics')));
check('dialog states: the waiting line says what it is given; the error block carries the message and, when asked, a Try again',
  el(b.loading('Reading the routine…')).querySelector('.rt-wait').textContent === 'Reading the routine…' && el(b.loading('x')).querySelector('.rt-wait .live')
  && el(b.error('run zero differed: x', true)).querySelector('.rt-error .msg').textContent === 'run zero differed: x' && el(b.error('x', true)).querySelector('[data-act="retry"]') && !el(b.error('x', false)).querySelector('[data-act="retry"]'));
// the checklist while the proposal is made (§17): four steps in order; done ones ticked with what they found, the running one with the
// dot and its clock (and the retry's words), the rest to come; the words the coach reads, not the machinery's
const t0 = 1800000000000;
const stA = el(b.steps({ chain: { state: 'running', since: t0 } }, t0 + 1500));
const stB = el(b.steps({ chain: { state: 'done', detail: '9 cells · 12 results · 2 figures' }, data: { state: 'done', detail: '206,016 rows · 17 columns · activity summary, wellness' }, model: { state: 'running', since: t0, again: false } }, t0 + 42000));
const stC = el(b.steps({ chain: { state: 'done', detail: '9 cells · 12 results · 2 figures' }, data: { state: 'done', detail: 'no longer loaded — the routine will be made unverified' }, model: { state: 'running', since: t0, again: true }, proposal: {} }, t0 + 12000));
const stK = el(b.steps({ chain: { state: 'done', detail: '2 cells' }, data: { state: 'done', detail: '5 rows' }, model: { state: 'running', since: t0, again: true, detail: 'identifiers were proposed as inputs' } }, t0 + 3000));
const stD = el(b.steps({ chain: { state: 'done' }, data: { state: 'done' }, model: { state: 'done' }, proposal: { state: 'running', since: t0 } }, t0 + 400));
check('steps: as the dialog opens - Reading the analysis running with its clock, the three to come greyed',
  [...stA.querySelectorAll('.s')].map(e => e.getAttribute('data-step') + ':' + e.className.replace('s ', '')).join(',') === 'chain:running,data:pending,model:pending,proposal:pending'
  && stA.querySelector('.s.running .t').textContent === 'Reading the analysis' && stA.querySelector('.s.running .d').textContent === '— 0:01' && stA.querySelector('.s.running .m .live') && stA.querySelector('.s.pending .m').textContent === '○'
  && stA.querySelector('[data-step="model"] .t').textContent === 'Working out what you can change each run, and which results to compare' && !stA.querySelector('.s.pending .d'));
check('steps: the analysis read and the data checked carry what they found, ticked; the model at work with its clock at 0:42; the proposal to come',
  stB.querySelector('[data-step="chain"].done .t').textContent === 'Read the analysis' && stB.querySelector('[data-step="chain"] .d').textContent === '— 9 cells · 12 results · 2 figures' && stB.querySelector('[data-step="chain"] .m').textContent === '✓'
  && stB.querySelector('[data-step="data"].done .d').textContent === '— 206,016 rows · 17 columns · activity summary, wellness' && stB.querySelector('[data-step="model"].running .d').textContent === '— 0:42' && stB.querySelector('[data-step="proposal"].pending .t').textContent === 'Preparing the proposal');
check('steps: a reply that could not be read says so on the model\'s line with the clock, a reply that proposed identifiers says that (§18); data no longer loaded says so; the proposal running has the clock and the others ticked',
  stC.querySelector('[data-step="model"].running .d').textContent === '— the reply could not be read; asking again · 0:12' && stC.querySelector('[data-step="data"] .d').textContent === '— no longer loaded — the routine will be made unverified' && stC.querySelector('[data-step="proposal"]').className === 's pending'
  && stK.querySelector('[data-step="model"].running .d').textContent === '— identifiers were proposed as inputs; asking again · 0:03'
  && stD.querySelector('[data-step="proposal"].running .d').textContent === '— 0:00' && stD.querySelectorAll('.s.done').length === 3 && b.clock(3725000) === '62:05');
const rtSrcSteps = fs.readFileSync(path.join(__dirname, '..', '..', 'web_app', 'static', 'js', 'routines.js'), 'utf8');
check('the page (§17): the routine_step lines are taken off the stream before the pane sees them, a step landing marks the ones before it done and sets the running one\'s clock, the chain\'s facts go to the sub-header, the clock ticks every second until the proposal lands or the dialog closes; the stylesheet has the list',
  rtSrcSteps.includes("if (data.type === 'routine_step') { if (dialogState === st) stepLanded(st, data); return true; }") && rtSrcSteps.includes("order.slice(0, order.indexOf(key)).forEach(k => { if (!st.steps[k] || st.steps[k].state !== 'done') st.steps[k] = Object.assign({}, st.steps[k], { state: 'done' }); });")
  && rtSrcSteps.includes("if (key === 'chain' && data.detail) dialogParts().sub.textContent = 'from this chain · ' + data.detail;") && rtSrcSteps.includes("st.stepTimer = setInterval(() => { if (dialogState !== st || st.proposal) { clearInterval(st.stepTimer); return; } renderSteps(st); }, 1000);")
  && rtSrcSteps.includes("if (dialogState) clearInterval(dialogState.stepTimer);") && dlgCss0().includes('.rt-steps { display: flex; flex-direction: column;') && dlgCss0().includes('.rt-steps .s.done .m { color: var(--c-model); }'));

// ---- the manager ----
const mg = el(b.managerShell());
check('manager shell: the list on the left, the routine on the right with header, actions and body', mg.querySelector('.rt-mgr .rt-left .rt-side') && mg.querySelector('.rt-right .ui-dlg-h .title') && mg.querySelector('.rt-right .rt-actions') && mg.querySelector('.rt-right .ui-dlg-h .x') && mg.querySelector('.rt-right .rt-body'));
const routine = { id: 'r1', name: 'Rows above a line', purpose: 'count the rows above a line', question: 'How many rows are above 155?', source: 'file', current_version: 2, origin: { thread_id: '1001', chain_id: '1791600000' }, origin_available: true,
  versions: [{ number: 1, created: 1791600000, promoted_from: { thread_id: '1001', chain_id: '1791600000' }, change_note: 'first version', manifest: { parameters: [], results: [], figures: { count: 0 } }, run_zero: { verified: true, line: 'reproduced: 1 result line(s) identical' } },
            { number: 2, created: 1791700000, promoted_from: { thread_id: '1001', chain_id: '1791700000' }, change_note: 'the threshold became an input', manifest: { parameters: [{ key: 'threshold', label: 'Threshold', type: 'number', default: 155, origin: 'the analysis split at 155' }], results: [{ cell: 2, index: 0, label: 'rows above the line', typed: false, dropped: false, estimate: '+3.00' }, { cell: 4, index: 0, label: 'dropped one', typed: true, dropped: true, estimate: '+9' }], figures: { count: 1 } }, run_zero: { verified: true, created: 1791700000, line: 'reproduced: 2 result line(s) identical', results: [{ estimate: '+3.00', low: null, high: null }, { estimate: '+9', low: null, high: null }] } }] };
const hd = b.routineHeader(routine);
check('manager header (S2, 2026-11-08): the name; the source, the version and the link to the analysis it was made from - a favourite, said on hover; nothing of the columns',
  hd.title === 'Rows above a line' && hd.sub.startsWith('File · v2 · ') && el(hd.sub).querySelector('a.rt-origin[data-thread="1001"][data-chain="1791600000"]').textContent.startsWith('from the analysis of ') && el(hd.sub).querySelector('a.rt-origin').getAttribute('title').includes('a favourite')
  && !hd.sub.includes('columns') && !el(hd.sub).textContent.includes('a favourite'), hd.sub);
check('manager header when the favourite is gone: no link, says so', !el(b.routineHeader(Object.assign({}, routine, { origin_available: false })).sub).querySelector('a') && b.routineHeader(Object.assign({}, routine, { origin_available: false })).sub.includes('no longer in Saved workflows'));
const bd = el(b.routineBody(routine));
check('manager body (S2, 2026-11-08): the facts - Purpose, Inputs (the current version\'s, a line each: label, default, origin), Tracked (what a run records), Versions newest first (the date, the chain when there are several, the verdict with the lines reproduced, the note after the first version); then the runs - the custom table with run 0 in its head, no runs list, no legend',
  [...bd.querySelector('.rt-facts').querySelectorAll(':scope > b')].map(e => e.textContent).join('|') === 'Purpose|Inputs|Tracked|Versions' && bd.querySelector('.rt-facts').textContent.includes('count the rows above a line') && !bd.textContent.includes('How many rows')
  && bd.querySelectorAll('.rt-facts .rt-input').length === 1 && bd.querySelector('.rt-facts .rt-input[data-key="threshold"] .k').textContent === 'Threshold' && bd.querySelector('.rt-facts .rt-input .val').textContent === '155' && bd.querySelector('.rt-facts .rt-input .from').textContent === 'the analysis split at 155'
  && [...bd.querySelector('.rt-facts').querySelectorAll(':scope > span')][2].textContent === '1 metric and 1 chart per run'
  && [...bd.querySelectorAll('.rt-vers .v')].map(e => e.getAttribute('data-version')).join(',') === '2,1' && bd.querySelector('.rt-vers .v b').textContent === 'v2' && bd.querySelector('.rt-vers .v').textContent.includes(' · from the analysis of ')
  && bd.querySelector('.rt-vers .v .rt-status.reproduced').textContent === 'verified' && bd.querySelector('.rt-vers .v').textContent.includes('verified, 2 lines reproduced · “the threshold became an input”') && bd.querySelector('.rt-vers .v[data-version="1"]').textContent.endsWith('verified')
  && bd.querySelector('.rt-runs thead th[data-run="0"]').textContent.includes('Run 0') && !bd.querySelector('.rt-run') && !bd.querySelector('.rt-legend') && bd.querySelector('.rt-sep'), [[...bd.querySelectorAll('.rt-vers .v')].map(e => e.textContent), bd.querySelector('.rt-facts').innerHTML.slice(0, 400)]);
check('manager body without a purpose: the question stands in its place; resultsFacts: metrics and charts, one of them, neither; the Custom instructions fact when the routine has a line (§15.6), none otherwise',
  [...el(b.routineBody(Object.assign({}, routine, { purpose: '' }))).querySelector('.rt-facts').querySelectorAll(':scope > b')].map(e => e.textContent).join('|') === 'Question|Inputs|Tracked|Versions' && el(b.routineBody(Object.assign({}, routine, { purpose: '' }))).querySelector('.rt-facts').querySelector(':scope > span').textContent === 'How many rows are above 155?'
  && [...el(b.routineBody(Object.assign({}, routine, { instruction: 'track the rows above the line' }))).querySelector('.rt-facts').querySelectorAll(':scope > b')].map(e => e.textContent).join('|') === 'Purpose|Inputs|Tracked|Custom instructions|Versions'
  && [...el(b.routineBody(Object.assign({}, routine, { instruction: 'track the rows above the line' }))).querySelector('.rt-facts').querySelectorAll(':scope > span')][3].textContent === 'track the rows above the line'
  && b.resultsFacts({ results: [{ estimate: '1' }, { estimate: '2' }, { estimate: '3', dropped: true }], figures: { count: 2 } }) === '2 metrics and 2 charts per run' && b.resultsFacts({ results: [{ estimate: '1' }], figures: { count: 0 } }) === '1 metric per run'
  && b.resultsFacts({ results: [], figures: { count: 1 } }) === 'no metrics recorded, 1 chart per run' && b.resultsFacts({}) === 'none recorded: runs keep their printed output');
check('manager actions carry Run first', el(b.actions(routine)).querySelector('[data-act="run"]') && el(b.actions(routine)).elements[0].getAttribute('data-act') === 'run');
// run zero behind the dialog (2026-10-15): a routine can be verifying - the card's chip pulses and says so, the side item says so, Run is held with
// the reason; a verdict that did not reproduce holds Run for good; an older record without a status reads from `verified` as before
const verifying = JSON.parse(JSON.stringify(routine)); verifying.versions[1].run_zero = { status: 'verifying', verified: false, line: "verifying: the method is being run once on the chain's own data" };
const differed = JSON.parse(JSON.stringify(routine)); differed.versions[1].run_zero = { status: 'differed', verified: false, line: '1 of 2 lines moved' };
const vb = el(b.routineBody(verifying)), va = el(b.actions(verifying)), da = el(b.actions(differed)), db = el(b.routineBody(differed));
check('a verifying routine: the chip says verifying… (pulsing class), Run disabled with the reason; a differed verdict: the chip says did not reproduce, Run disabled with the way out; a verified one: Run live',
  vb.querySelector('.rt-status.verifying').textContent === 'verifying…' && va.querySelector('[data-act="run"]').hasAttribute('disabled') && va.querySelector('[data-act="run"]').getAttribute('title').includes('still being verified')
  && db.querySelector('.rt-status.differed').textContent === 'did not reproduce' && db.querySelector('.rt-vers .v').textContent.includes('did not reproduce — 1 of 2 lines moved') && da.querySelector('[data-act="run"]').hasAttribute('disabled') && da.querySelector('[data-act="run"]').getAttribute('title').includes('make it again')
  && !el(b.actions(routine)).querySelector('[data-act="run"]').hasAttribute('disabled') && b.zeroStatus({ verified: true }).includes('verified') && b.zeroStatus({}).includes('unverified'),
  [vb.querySelector('.rt-status') && vb.querySelector('.rt-status').outerHTML, va.innerHTML.slice(0, 200)]);
// what Save found on smaller pieces of the analysis's own data (§22): the Tried on fact - a day, a week, a month, each with how many of the
// tracked metrics came back, the piece's dates and the run's line on hover; no fact on a version without trials; a version's row carries its
// verdict and its note, nothing of how the code is run
const tried = JSON.parse(JSON.stringify(routine)); tried.versions[1].tried = [
  { interval: 'day', window: ['2026-10-29', '2026-10-29'], status: 'ran', line: 'ran: 3 of 5 result lines; 2 not computed (cell 3 stopped: LinAlgError: Singular matrix)', came: 3, of: 5 },
  { interval: 'week', window: ['2026-10-19', '2026-10-25'], status: 'ran', line: 'ran: 5 result lines', came: 5, of: 5 },
  { interval: 'month', window: ['2026-09-01', '2026-09-30'], status: 'failed', line: 'failed: Connection aborted', came: 0, of: 5 }];
const tb = el(b.routineBody(tried));
const vrow = r => el(b.routineBody(r)).querySelector('.rt-vers .v').textContent;
check('the Tried on fact: after Tracked, a piece each - how many came back, all of them said as all, a piece that could not be run said so - with its dates and the reason on hover; none without trials; the words for a piece with no data and for a routine that tracks nothing; a version row ends with its note',
  [...tb.querySelector('.rt-facts').querySelectorAll(':scope > b')].map(e => e.textContent).join('|') === 'Purpose|Inputs|Tracked|Tried on|Versions' && tb.querySelector('.rt-tried').textContent === 'a day: 3 of 5 · a week: all 5 · a month: could not be run'
  && tb.querySelector('.rt-tried span').getAttribute('title') === '2026-10-29 → 2026-10-29 — ran: 3 of 5 result lines; 2 not computed (cell 3 stopped: LinAlgError: Singular matrix)' && !bd.querySelector('.rt-tried')
  && b.triedText({ status: 'empty', came: 0, of: 5 }) === 'no data' && b.triedText({ status: 'ran', came: 0, of: 0 }) === 'ran' && b.triedText({ status: 'timed_out', came: 0, of: 5 }) === 'could not be run'
  && vrow(tried).endsWith('verified, 2 lines reproduced · “the threshold became an input”') && !el(b.routineBody(tried)).querySelector('.rt-vers a'), [tb.querySelector('.rt-tried') && tb.querySelector('.rt-tried').innerHTML, vrow(tried)]);
check('the side item says verifying… or did not reproduce from the summary card', el(b.sideItem({ id: 'x', name: 'N', source: 'file', current_version: 1, runs: 0, run_zero_status: 'verifying', created: 1791600000 }, false)).textContent.includes('verifying…')
  && el(b.sideItem({ id: 'x', name: 'N', source: 'file', current_version: 1, runs: 0, run_zero_status: 'failed', created: 1791600000 }, false)).textContent.includes('did not reproduce')
  && !el(b.sideItem({ id: 'x', name: 'N', source: 'file', current_version: 1, runs: 0, run_zero_status: 'reproduced', created: 1791600000 }, false)).textContent.includes('verifying'));
// the time a run will take, for the dialog's footer (2026-10-15; the footer since §16.1): the last run's, or run zero's; a fill's is the units times it
const r9 = Object.assign({}, routine, { runs: [{ number: 1, version: 2, status: 'ran', created: 1791700100, elapsed: 512 }] });
const r45 = Object.assign({}, routine, { runs: [], versions: routine.versions.map((v, i) => i === 1 ? Object.assign({}, v, { run_zero: Object.assign({}, v.run_zero, { elapsed: 45 }) }) : v) });
check('tookLine: "the last run took 9 min"; with no run yet, "the check on the original data took 45 s"; a fill of 41 units "about 5 h 50 min"; nothing when the time is unknown; the dialog body says nothing about it',
  b.tookLine(r9, 1) === 'the last run took 9 min' && b.tookLine(r45, 1) === 'the check on the original data took 45 s' && b.tookLine(r9, 41) === 'about 5 h 50 min' && b.tookLine(routine, 1) === '' && b.tookLine(routine, 41) === ''
  && !el(b.runDialog(r9, { loaded: true, ok: true, line: 'fits', fit: { missing: [] }, data: { name: 'a.csv', source: 'csv', rows: 9, columns: 2 }, plan: { source: 'file' } })).textContent.includes('took'), [b.tookLine(r9, 41)]);

// ---- step 2: the run dialog ----
const rr = Object.assign({}, routine, { runs: [{ number: 1, version: 2, created: 1791700000, status: 'ran', data: { name: 'small.csv', source: 'csv', rows: 5 }, inputs: { threshold: 155 }, comparison: { moved: 0, compared: 1, line: '0 of 1 changed' }, results: [{ estimate: '+3.00', low: null, high: null }] }] });
rr.versions[1].manifest.parameters = [{ key: 'threshold', label: 'Threshold', type: 'number', default: 155, origin: 'the analysis split at 155' }, { key: 'bands', label: 'Bands', type: 'numbers', default: [130, 145] },
  { key: 'window', label: 'Window', type: 'date_window', default: ['2026-01-01', '2026-03-31'] }, { key: 'who', label: 'Groups', type: 'choice', multiple: true, column: 'g', default: ['a', 'b'] }, { key: 'flag', label: 'Flag', type: 'toggle', default: true }];
let rd = el(b.runDialog(rr, { loaded: true, ok: true, line: 'fits the routine (2 of 2 columns)', data: { name: 'small.csv', source: 'csv', rows: 5, columns: 2 }, plan: { source: 'file', name: 'small.csv' } }));
check('run dialog (a file routine, §16.1): the Data row with the data loaded now on, named, and no fit line when it fits; an upload as the other choice; the Inputs row with one widget per input in its type - number, numbers as text, two dates, choice as text, a toggle - the origin on the label\'s hover; the Compare row with the run before (on) and run 0',
  [...rd.querySelectorAll('.rt-row')].map(r => r.getAttribute('data-row')).join(',') === 'data,file,inputs,compare' && rd.querySelector('.rt-row[data-row="data"] input[value="now"]').parentNode.textContent.includes('The data loaded now · small.csv') && !rd.querySelector('.rt-fit') && !rd.querySelector('.rt-data')
  && rd.querySelector('.rt-inputs-grid .k').textContent === 'Threshold' && rd.querySelector('.rt-inputs-grid .k').getAttribute('title') === 'the analysis split at 155'
  && rd.querySelector('input[name="rt-data"][value="now"]').hasAttribute('checked') && rd.querySelector('input[name="rt-data"][value="upload"]') && !rd.querySelector('input[name="rt-data"][value="upload"]').hasAttribute('checked') && rd.querySelector('input[data-load="file"]')
  && rd.querySelector('[data-key="threshold"][data-type="number"]').getAttribute('value') === '155' && rd.querySelector('[data-key="bands"][data-type="numbers"]').getAttribute('value') === '130, 145'
  && rd.querySelectorAll('[data-key="window"][data-type="date_window"]').length === 2 && rd.querySelector('[data-key="who"]').getAttribute('value') === 'a, b' && rd.querySelector('[data-key="flag"][data-type="toggle"]').hasAttribute('checked')
  && rd.querySelector('input[name="rt-compare"][value="previous"]').hasAttribute('checked') && rd.querySelector('input[name="rt-compare"][value="zero"]') && rd.querySelector('.rt-row[data-row="compare"]').textContent.includes('run 1 (the run before)') && rd.querySelector('.rt-row[data-row="compare"]').textContent.includes('run 0 (the original data)'));
// the Dataset cache's pick (step 4, 2026-10-11): a third choice for a file routine, hidden until the page has the cache's answer; none for a loader routine
const rtSrcPick = fs.readFileSync(path.join(__dirname, '..', '..', 'web_app', 'static', 'js', 'routines.js'), 'utf8');
check('run dialog (a file routine): a hidden choice for a file from the Dataset cache with its select, shown by the page once the cache answers; a loader routine has none',
  rd.querySelector('.rt-row[data-row="data"] label.rt-cachepick input[name="rt-data"][value="cache"]') && [...rd.querySelectorAll('.rt-cachepick')].every(e => e.getAttribute('style').includes('display:none')) && rd.querySelector('.rt-row[data-row="file"] select.rt-cachepick[data-load="cached"]')
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
check('run dialog (a file routine) with nothing loaded: the upload is the choice, on, no data-loaded-now choice, a line saying to upload the file; the Compare row stands (run 1 before, run 0)', rd.querySelector('input[name="rt-data"][value="upload"]').hasAttribute('checked') && !rd.querySelector('input[name="rt-data"][value="now"]') && rd.querySelector('.rt-row[data-row="file"] .rt-plan').textContent.includes('upload the file') && rd.querySelector('.rt-row[data-row="compare"] input[value="zero"]'));
rd = el(b.runDialog(rr, { loaded: true, ok: true, line: '1 of 2 columns empty in this data: g', fit: { missing: ['g'] }, data: { name: 'other.csv', source: 'csv', rows: 9, columns: 1 }, plan: { source: 'file' } }));
check('run dialog with a column missing: the fit line is a note (amber, △), not bad - the column will be empty in this data, the run adds it and the coach decides', !rd.querySelector('.rt-fit.bad') && rd.querySelector('.rt-fit.note') && rd.querySelector('.rt-fit').textContent.startsWith('△ 1 of 2 columns empty in this data: g'));
rd = el(b.runDialog(rr, { loaded: true, ok: true, line: "fits the routine (2 of 2 columns); 'b' is not in column g - the method keeps the other value", fit: { missing: [] }, values_notes: ["'b' is not in column g - the method keeps the other value"], data: { name: 'other.csv', source: 'csv', rows: 9, columns: 2 }, plan: { source: 'file' } }));
check('run dialog with one of several chosen values absent: a note (△), not a refusal - the method keeps the other value (2026-10-11)', !rd.querySelector('.rt-fit.bad') && rd.querySelector('.rt-fit.note') && rd.querySelector('.rt-fit').textContent.includes("'b' is not in column g - the method keeps the other value"));
rd = el(b.runDialog(rr, { loaded: true, ok: false, line: "none of the routine's 2 columns is in this data - nothing to run on", data: { name: 'other.csv', source: 'csv', rows: 9, columns: 1 }, plan: { source: 'file' } }));
check('run dialog with nothing of the routine\'s data: the fit line is bad, nothing to run on', rd.querySelector('.rt-fit.bad').textContent.includes('nothing to run on'));
// an Intervals routine: the load as the original did - the window of the original's length ending today, clamped to the plan's limit, the auxiliary kinds and metrics as the original; the data loaded now as the other choice
rd = el(b.runDialog(rr, { loaded: true, ok: true, line: 'fits the routine (49 of 49 columns)', data: { name: '', source: 'intervals', rows: 10200, columns: 49, date_range: '2026-08-12 to 2026-10-10' },
  plan: { source: 'intervals', window_days: 59, aux_kinds: ['summary', 'wellness'], metrics: [] } }, { max_days: 14 }));
const win = [...rd.querySelectorAll('input[type="date"][data-load]')].map(e => [e.getAttribute('data-load'), e.getAttribute('value')]);
const dayGap = (Date.parse(win[1][1]) - Date.parse(win[0][1])) / 86400000;
check('run dialog (an Intervals routine, §16.1): the rows Data, Athlete, Interval, Inputs (five), Compare; Load from Intervals.icu on, the data loaded now with its dates as the other choice; the pickers a window ending today of the original\'s length clamped to the plan\'s limit, a note saying what the plan allows; nothing about the kinds, the metrics, the cache or fetching everything again; no Inputs row without inputs; the band is the shell\'s, not the body\'s',
  [...rd.querySelectorAll('.rt-row')].map(r => r.getAttribute('data-row')).join(',') === 'data,athlete,interval,inputs,compare' && rd.querySelector('input[name="rt-data"][value="load"]').hasAttribute('checked') && rd.querySelector('.rt-row[data-row="data"] .rt-choices').textContent.includes('Load from Intervals.icu')
  && rd.querySelector('.rt-row[data-row="data"] input[value="now"]').parentNode.textContent.includes('The data loaded now · 2026-08-12 → 2026-10-10') && !rd.querySelector('input[name="rt-data"][value="now"]').hasAttribute('checked') && !rd.querySelector('.rt-fit')
  && win.length === 2 && win[0][0] === 'start' && win[1][0] === 'end' && dayGap === 14 && rd.querySelector('.rt-row[data-row="interval"] .rt-plan .n').textContent.startsWith('up to 14 days at a time · back to ') && rd.querySelector('input[data-load="start"]').getAttribute('min') === win[0][1] && rd.querySelector('input[data-load="end"]').getAttribute('max') === win[1][1] && !rd.querySelector('.rt-plan.warn')
  && !rd.querySelector('[data-load="refresh"]') && !rd.textContent.includes('Everything again') && !rd.textContent.includes('metrics as the original') && !rd.textContent.includes('with summary') && !rd.querySelector('.rt-cache') && !rd.textContent.includes('the original\u2019s')
  && !rd.querySelector('.rt-progress')
  && !el(b.runDialog(Object.assign({}, routine, { versions: routine.versions.map(v => Object.assign({}, v, { manifest: Object.assign({}, v.manifest, { parameters: [] }) })) }), { loaded: false, ok: false, line: '', plan: { source: 'intervals', window_days: 28, aux_kinds: ['summary'] } })).querySelector('.rt-row[data-row="inputs"]'), [win, dayGap, rd.textContent.slice(0, 300)]);
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
const mgd = el(b.routineBody(Object.assign({}, rrd, { origin: {} })));
check('the manager\'s Inputs fact says which inputs follow the data, in place of a default', mgd.querySelector('.rt-facts .rt-input[data-derived="span"] .rt-derived').textContent.includes('first and last dates') && mgd.querySelector('.rt-facts .rt-input[data-derived="window"] .rt-derived').textContent.includes('the window loaded') && !mgd.querySelector('.rt-facts .rt-input[data-derived="span"] .val'));
rd = el(b.runDialog(rr, { loaded: false, ok: false, line: 'no data is loaded', plan: { source: 'endura', race_id: 7, race_title: 'Spring classic', aux_kinds: ['profile', 'turns'] } }));
check('run dialog (an Endura routine): Load from Endura with the race list to fill in a Race row; nothing about the original race or the Data tab',
  rd.querySelector('input[name="rt-data"][value="load"]').hasAttribute('checked') && rd.querySelector('.rt-row[data-row="race"] select[data-load="race"]') && !rd.textContent.includes('the original:') && !rd.textContent.includes('Data tab'));
// the cache (2026-10-11; the preview line gone with §16.1): the load asks it when Run is pressed; the stored run's Data tab says a cached load was one
const rdi = el(b.runDialog(rr, { loaded: false, ok: false, line: '', plan: { source: 'intervals', window_days: 30, aux_kinds: ['summary'], metrics: [] } }));
check('the run dialog has no cache line any more, for any source', !rdi.querySelector('.rt-cache') && !rd.querySelector('.rt-cache') && !el(b.runDialog(rr, { loaded: true, ok: true, line: 'fits', data: { name: 'a.csv', source: 'csv' }, plan: { source: 'file' } })).querySelector('.rt-cache'));
check('a run loaded from the cache says so where its load is named; one cut from a cached load around its window names that load', el(b.dataTab({ source: 'intervals', load: { source: 'intervals', start_date: '2026-07-03', end_date: '2026-08-31', aux_kinds: ['summary'], cached: true } }, {})).textContent.includes('Intervals.icu 2026-07-03 → 2026-08-31 · summary · from the cache')
  && el(b.dataTab({ source: 'endura', load: { source: 'endura', race_title: 'Flat crit', cached: true } }, {})).textContent.includes('Endura · Flat crit · from the cache')
  && el(b.dataTab({ source: 'intervals', load: { source: 'intervals', start_date: '2026-02-01', end_date: '2026-05-31', aux_kinds: ['summary'], cached: true, cached_from: ['2026-01-13', '2026-06-11'] } }, {})).textContent.includes('Intervals.icu 2026-02-01 → 2026-05-31 · summary · cut from the cached load 2026-01-13 → 2026-06-11'));
const rtSrc0 = fs.readFileSync(path.join(__dirname, '..', '..', 'web_app', 'static', 'js', 'routines.js'), 'utf8');
check('the page asks the cache when Run is pressed (the preview under the window went with §16.1), takes a hit through the Dataset cache routes (the frame with its athlete folder, so the other athletes\' files leave the session: one athlete at a time, 2026-10-29), and sends the load as done with the precheck and the run',
  rtSrc0.includes("fetchJson('/routines/' + encodeURIComponent(st.id) + '/cached'") && rtSrc0.includes("const c = await askCache(runState, asked);") && rtSrc0.includes("runState.lastChanged = e.target.getAttribute('data-load');") && !rtSrc0.includes("checkCache") && !rtSrc0.includes("showCache") && rtSrc0.includes("fetchJson('/cache/load_primary'") && rtSrc0.includes("body: JSON.stringify({ df_id: cached.df_id, folder: cached.folder || '' })") && rtSrc0.includes("fetchJson('/cache/load_auxiliary'")
  && rtSrc0.includes("body: JSON.stringify({ values, aux: auxLoaded, load: loadDone })") && rtSrc0.includes("{ values, compare_with, aux: auxLoaded, load: loadDone, interval: plan ? plan.kind : undefined }"));
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
// a run that could not be carried out (§22): the error block with the run's line and the error; its lines a dot that says why on hover
ct = el(b.comparisonTab({ run: { number: 4, version: 2, status: 'failed', line: 'failed: Connection aborted', error: 'Connection aborted', against: 3, data: {}, stopped: [], gaps: [],
  comparison: { rows: [{ label: 'a', now: null, before: { estimate: '+1' }, mark: 'missing', why: 'failed: Connection aborted' }], line: 'no result line to compare', compared: 0 } } }));
check('comparison tab of a run that could not be carried out: the error block with its line and the error, the row a dot with the reason on hover and the words not computed; no statement named',
  ct.querySelector('.rt-error .msg').textContent === 'failed: Connection aborted' && ct.querySelector('.rt-error .rt-error-tb pre').textContent === 'Connection aborted' && !ct.querySelector('.rt-stopped')
  && ct.querySelectorAll('tr.missing td.num')[1].getAttribute('title') === 'failed: Connection aborted' && ct.querySelectorAll('tr.missing td.num')[1].textContent === '·' && ct.querySelectorAll('tr.missing td')[4].textContent.trim() === '· not computed', ct.innerHTML.slice(0, 600));
// a run that lost a statement: no error block - one line per statement that stopped, opening on its code; what was emptier than in the analysis;
// a line without a number is not computed, with the reason on hover; one the run before lacks has no earlier value
const lostOne = { number: 5, version: 2, status: 'ran', line: "ran: 2 of 3 result lines; 1 not computed (cell 2 stopped: KeyError: 'b')", error: '', against: 4, data: {},
  stopped: [{ cell: 2, line: 2, code: "b = float(per['b'])", error: "KeyError: 'b'", skipped: 2 }, { cell: 5, line: 1, code: 'fit(x)', error: 'LinAlgError: Singular matrix', skipped: 0 }], gaps: ['power is empty for 3 of 6 activity_id values'],
  comparison: { rows: [{ label: 'first', now: { estimate: '+3' }, before: { estimate: '+3' }, mark: 'same', overlap: null, change: 0, why: '' }, { label: 'second', now: null, before: { estimate: '+1' }, mark: 'missing', why: "cell 2 stopped: KeyError: 'b'" },
                       { label: 'third', now: { estimate: '+2' }, before: null, mark: 'missing', why: '' }], line: '0 of 1 changed, 2 missing', compared: 1 } };
ct = el(b.comparisonTab({ run: lostOne }));
check('comparison tab of a run that lost a statement: no error block; a line per statement that stopped - its cell, the error, the later statements not run for it - opening on its code; the column emptier than in the analysis, said; a line this run has no number for is not computed, the reason on its hover; one the run before lacks has no earlier value; the legend says nothing of failures',
  !ct.querySelector('.rt-error') && [...ct.querySelectorAll('details.rt-stopped summary')].map(e => e.textContent).join('|') === "cell 2 stopped: KeyError: 'b' · 2 later steps not run|cell 5 stopped: LinAlgError: Singular matrix"
  && ct.querySelector('details.rt-stopped code').textContent === "b = float(per['b'])" && ct.querySelector('.rt-fit.note').textContent === '△ power is empty for 3 of 6 activity_id values'
  && [...ct.querySelectorAll('tbody tr')].map(tr => tr.querySelectorAll('td')[4].textContent.trim()).join('|') === '= same|· not computed|· no earlier value'
  && ct.querySelectorAll('tbody tr')[1].querySelectorAll('td')[4].getAttribute('title') === "cell 2 stopped: KeyError: 'b'" && ct.querySelectorAll('tbody tr')[1].querySelectorAll('td.num')[1].getAttribute('title') === "cell 2 stopped: KeyError: 'b'"
  && !ct.querySelectorAll('tbody tr')[2].querySelectorAll('td')[4].getAttribute('title') && !ct.querySelector('.rt-legend').textContent.includes('reach'), ct.innerHTML.slice(0, 900));
ct = el(b.comparisonTab({ run: { number: 6, version: 2, status: 'empty', line: 'no data in this window', against: null, data: {}, stopped: [], gaps: [], comparison: { rows: [{ label: 'a', now: null, before: null, mark: 'missing', why: 'no data in this window' }], line: 'nothing to compare with: no earlier week on record', compared: 0 } } }));
check('comparison tab of a run on a window with no data: one line that says so, no table and no error', ct.querySelector('.rt-line').textContent === 'No data in this window, so nothing was run.' && !ct.querySelector('table') && !ct.querySelector('.rt-error'));
const dt = el(b.dataTab(run3.data));
check('data tab of a stored run: source, name, rows and the columns with their types', dt.textContent.includes('later.csv') && dt.textContent.includes('9') && dt.textContent.includes('v') && dt.textContent.includes('int64'));
const rt = Object.assign({}, routine, { runs: [
  { number: 1, version: 2, created: 1791700000, status: 'ran', data: { name: 'a.csv', source: 'csv' }, inputs: {}, comparison: { moved: 0, compared: 1 }, results: [{ estimate: '+3.00', low: '+2.00', high: '+4.00' }, { estimate: '+9', low: null, high: null }] },
  { number: 2, version: 2, created: 1791800000, status: 'ran', data: { name: 'b.csv', source: 'csv' }, inputs: { threshold: 165 }, comparison: { moved: 1, compared: 1 }, results: [{ estimate: '+5.00', low: '+4.50', high: '+5.50' }, { estimate: '+9', low: null, high: null }] },
  { number: 3, version: 2, created: 1791900000, status: 'failed', data: { name: 'c.csv', source: 'csv' }, inputs: {}, comparison: { moved: 0, compared: 0 }, results: [] }] });
rt.versions[1].run_zero.results = [{ estimate: '+3.00', low: '+2.00', high: '+4.00' }, { estimate: '+9', low: null, high: null }];
const headName = e => e.textContent.replace(/(Open|Delete)+$/, '').replace(/[A-Z][a-z]{2} \d+( · \d+ days)?$/, '').trim();     // a head's name without its date and its two words (§21)
const tbl = el(b.runsTable(rt));
check('runs table (the custom runs, §14.6): a column per run that ran (run 0 first), each head with Open and Delete on hover (§21; run 0 has no Delete), the manifest\'s lines as rows (the dropped one left out), the values without the plus sign, the mark in its own column between the two numbers it compares - = within, ↑ moved - and no trend across them (custom windows are not a series); the failed run named under the table with its reason and the same two words; no legend (2026-11-08)',
  [...tbl.querySelectorAll('thead th')].map(e => headName(e)).join('|') === 'Result|Run 0||Run 1||Run 2' && [...tbl.querySelectorAll('thead th[data-run]')].map(e => e.getAttribute('data-run')).join(',') === '0,1,2' && tbl.querySelectorAll('tbody tr').length === 1
  && [...tbl.querySelectorAll('tbody td')].map(td => td.className).join('|') === 'label|num|mark|num|mark|num' && [...tbl.querySelectorAll('tbody td.num')].map(td => td.textContent).join('|') === '3.00|3.00|5.00'
  && [...tbl.querySelectorAll('tbody td.mark')].map(td => td.textContent).join('') === '=↑' && !tbl.querySelector('svg') && !tbl.querySelector('.rt-legend')
  && tbl.querySelector('.rt-foot .rt-failed[data-run="3"]').textContent.startsWith('run 3 · ') && tbl.querySelector('.rt-foot .rt-failed').textContent.includes(' · failed')
  && [...tbl.querySelectorAll('thead th[data-run] .acts')].map(a => [...a.querySelectorAll('a')].map(x => x.getAttribute('data-act') + ':' + x.textContent).join(',')).join('|') === 'open-run:Open|open-run:Open,delete-run:Delete|open-run:Open,delete-run:Delete'
  && tbl.querySelector('thead th[data-run="2"] .acts a.x[data-act="delete-run"][data-run="2"]') && [...tbl.querySelectorAll('.rt-foot .rt-failed .acts a')].map(x => x.textContent).join(',') === 'Open,Delete' && !tbl.querySelector('thead th[data-run="0"] [data-act="delete-run"]'),
  [...tbl.querySelectorAll('tbody td')].map(td => td.className + ':' + td.textContent).join(' ') + (tbl.querySelector('.rt-foot') || {}).textContent);
// what a custom run could not give (§22): a run whose window had no data is named under the table with the failed ones; a line that did not come
// back is a dot with the reason on hover; the mark in a run's head says what was emptier than in the analysis
const rtE = Object.assign({}, rt, { runs: rt.runs.concat([{ number: 4, version: 2, created: 1792000000, status: 'empty', line: 'no data in this window', data: { name: 'd.csv', source: 'csv' }, results: [] },
  { number: 5, version: 2, created: 1792100000, status: 'ran', data: { name: 'e.csv', source: 'csv' }, gaps: ['v is empty in 40% of the rows'], results: [{ estimate: null, low: null, high: null, why: "cell 2 stopped: KeyError: 'b'" }, { estimate: '+9' }] }]) });
const tblE = el(b.runsTable(rtE));
check('runs table with what a run could not give: the run on a window with no data under the table, saying so, beside the failed one; the run that lost its line a column whose cell is a dot with the reason on hover and no mark before it; its head carries the mark for the emptier column',
  [...tblE.querySelectorAll('.rt-foot .rt-failed')].map(e => e.getAttribute('data-run')).join(',') === '4,3' && tblE.querySelector('.rt-foot .rt-failed[data-run="4"]').textContent.includes(' · no data in this window')
  && [...tblE.querySelectorAll('thead th[data-run]')].map(e => e.getAttribute('data-run')).join(',') === '0,1,2,5' && tblE.querySelector('thead th[data-run="5"] .rt-gapmark').getAttribute('title') === 'v is empty in 40% of the rows'
  && !tblE.querySelector('thead th[data-run="2"] .rt-gapmark') && [...tblE.querySelectorAll('tbody td.num')].map(td => td.textContent).join('|') === '3.00|3.00|5.00|·'
  && tblE.querySelectorAll('tbody td.num')[3].getAttribute('title') === "cell 2 stopped: KeyError: 'b'" && [...tblE.querySelectorAll('tbody td.mark')].map(td => td.textContent).join('|') === '=|↑|',
  [...tblE.querySelectorAll('tbody td')].map(td => td.className + ':' + td.textContent).join(' ') + (tblE.querySelector('.rt-foot') || {}).textContent);
const tbl2 = el(b.runsTable(Object.assign({}, rt, { runs: rt.runs.slice(0, 1) })));
check('runs table with two runs: the mark between the numbers; a run with a window says its length in the head and carries the window on hover',
  [...tbl2.querySelectorAll('thead th')].map(e => headName(e)).join('|') === 'Result|Run 0||Run 1' && tbl2.querySelector('tbody td.mark .rt-mark.same') && !tbl2.textContent.includes('Trend')
  && (() => { const t = el(b.runsTable(Object.assign({}, rt, { runs: [Object.assign({}, rt.runs[0], { data: Object.assign({}, rt.runs[0].data, { window: ['2026-05-01', '2026-11-05'] }) })] }))); const th = t.querySelectorAll('thead th.num')[1]; return th.textContent.includes('· 188 days') && th.getAttribute('title') === '2026-05-01 → 2026-11-05'; })(), tbl2.innerHTML.slice(0, 300));
check('the runs list is gone (2026-11-08): the table\'s rows and heads are the runs', typeof b.runsList === 'undefined' && typeof b.condensedLine === 'undefined');
check('markOf: intervals apart move, overlapping ones are within, no intervals compare the estimates, a side missing is missing',
  b.markOf({ estimate: '+2', low: '+1.6', high: '+2.4' }, { estimate: '+1', low: '+0.5', high: '+1.5' }) === 'up' && b.markOf({ estimate: '+1.1', low: '+0.6', high: '+1.6' }, { estimate: '+1', low: '+0.5', high: '+1.5' }) === 'same'
  && b.markOf({ estimate: '+2' }, { estimate: '+3' }) === 'down' && b.markOf({ estimate: '+1,234' }, { estimate: '+1234' }) === 'same' && b.markOf(null, { estimate: '+1' }) === 'missing');

// ---- whose runs (2026-10-30, docs/DATASETS_DESIGN.md §17 step 3): the athlete in the run dialog; the comparison and the history within one athlete's runs ----
const two = JSON.parse(JSON.stringify(rt));
two.versions[1].manifest.data = { columns: [{ name: 'v' }], load: { source: 'intervals', subject: { source: 'intervals', id: 'i0', name: 'First Athlete' } } };
const onRun = (n, created, id, name, est) => ({ number: n, version: 2, created, status: 'ran', data: { name: '', source: 'intervals', subject: id ? { id, name } : {} }, inputs: {}, comparison: { moved: 0, compared: 1 }, results: [{ estimate: est, low: null, high: null }, { estimate: '+9', low: null, high: null }] });
two.runs = [onRun(1, 1791700000, 'i0', 'First Athlete', '+3.00'), onRun(2, 1791800000, 'i1', 'Second Athlete', '+5.00'), onRun(3, 1791900000, 'i0', 'First Athlete', '+3.50')];
rd = el(b.runDialog(two, { loaded: false, ok: false, line: '', plan: { source: 'intervals', window_days: 30, aux_kinds: ['summary'], metrics: [], subject: { id: 'i0', name: 'First Athlete' } } }));
check('run dialog (an Intervals routine): the Athlete row above the Interval row - a select to fill, with its help line empty - and the Compare row for the original\'s athlete: the run before on them (run 3, on) and run 0',
  [...rd.querySelectorAll('.rt-row')].map(r => r.getAttribute('data-row')).join(',') === 'data,athlete,interval,inputs,compare' && rd.querySelector('.rt-row[data-row="athlete"] select[data-load="athlete"]') && rd.querySelector('.rt-row[data-row="athlete"] .rt-athlete-help')
  && [...rd.querySelector('.rt-row[data-row="interval"]').children[1].children].map(e => e.className).join('|') === 'ui-seg rt-interval|rt-interval-plan|rt-window rt-loadwin rt-custom'
  && rd.querySelector('.rt-compare-sec input[name="rt-compare"][value="previous"]').hasAttribute('checked') && rd.querySelector('.rt-compare-sec').textContent.includes('run 3 (the run before)')
  && rd.querySelector('.rt-compare-sec input[name="rt-compare"][value="zero"]'), rd.querySelector('.rt-compare-sec') && rd.querySelector('.rt-compare-sec').textContent);
const v2 = two.versions[1];
const cmp = (id, name) => el(b.compareSection(two, v2, id, name));
check('compareSection: the second athlete has one run before (run 2) and no run 0 (it ran on the first athlete\'s data) - one choice, so no row; a third athlete has nothing - no row',
  b.compareSection(two, v2, 'i1') === '' && b.compareSection(two, v2, 'i2') === '' && cmp('i0', 'First Athlete').querySelector('input[value="zero"]'), b.compareSection(two, v2, 'i1'));
const noZero = JSON.parse(JSON.stringify(two)); noZero.versions[1].manifest.data = { columns: [] };
const cmpOther = el(b.compareSection(noZero, noZero.versions[1], 'i0'));
check('compareSection: a run 0 that names no athlete (from before the athlete was kept) is nobody\'s - no row for the second athlete (their run 2 alone, nothing else to choose), none for a third; the first athlete has runs 1 and 3: the run before and "another run" offering run 1 (§21), no run 0; it is the subject-less runs\' (a file routine with a run before: the row); with run 0 theirs, the three choices',
  b.compareSection(noZero, noZero.versions[1], 'i1') === '' && b.compareSection(noZero, noZero.versions[1], 'i2') === ''
  && cmpOther.querySelector('input[name="rt-compare"][value="previous"]') && !cmpOther.querySelector('input[value="zero"]') && cmpOther.querySelector('input[name="rt-compare"][value="other"]') && [...cmpOther.querySelectorAll('select.rt-compare-other option')].map(o => o.getAttribute('value') + ':' + o.textContent).join('|') === '1:run 1 · Oct 11'
  && b.compareSection(Object.assign({}, noZero, { runs: [Object.assign({}, two.runs[0], { data: { name: 'a.csv', source: 'csv' } })] }), noZero.versions[1], '') !== ''
  && [...el(b.compareSection(two, v2, 'i0')).querySelectorAll('input[name="rt-compare"]')].map(i => i.getAttribute('value')).join(',') === 'previous,zero,other', cmpOther.innerHTML);
check('runAthletes: the athletes the routine ran on, the latest run\'s first, with their counts (run 0 counted for its athlete); a run 0 or a run naming none makes the "athlete not recorded" group',
  b.runAthletes(two).map(a => a.id + ':' + a.name + ':' + a.n).join('|') === 'i0:First Athlete:3|i1:Second Athlete:1' && b.runAthletes(noZero).map(a => a.id + ':' + a.n).join('|') === 'i0:2|i1:1|:1' && b.runAthletes(Object.assign({}, noZero, { runs: [] })).map(a => a.id + ':' + a.n).join('|') === ':1'
  && el(b.routineBody(Object.assign({}, noZero, { origin: {} }))).querySelector('select[data-pick="athlete"] option[value=""]').textContent === 'athlete not recorded · 1 run', b.runAthletes(noZero));
const tb0 = el(b.runsTable(two, 'i0')), tb1 = el(b.runsTable(two, 'i1')), tbAll = el(b.runsTable(two));
check('runs table by athlete: the first athlete\'s columns are run 0, 1 and 3; the second\'s run 2 alone (no run 0); unfiltered, every run',
  [...tb0.querySelectorAll('thead th')].map(e => headName(e)).filter(Boolean).join('|') === 'Result|Run 0|Run 1|Run 3' && [...tb1.querySelectorAll('thead th')].map(e => headName(e)).filter(Boolean).join('|') === 'Result|Run 2'
  && [...tbAll.querySelectorAll('thead th')].map(e => headName(e)).filter(Boolean).join('|') === 'Result|Run 0|Run 1|Run 2|Run 3', [tb0.textContent, tb1.textContent]);
const mb2 = el(b.routineBody(Object.assign({}, two, { origin: {} })));
const oneAthlete = Object.assign({}, two, { origin: {}, runs: two.runs.filter(x => ((x.data || {}).subject || {}).id === 'i0') });
const mb1 = el(b.routineBody(oneAthlete)), mb0 = el(b.routineBody(Object.assign({}, oneAthlete, { runs: [] })));
check('the manager with runs on one athlete (2026-11-13): the pick is there with their name selected, so a coach coming back sees whose runs these are - three runs, run 0 among them, and with run 0 alone - under All athletes (§23); the table is every run; runs that name no athlete (a file routine, a run 0 from before the athlete was kept) show no pick',
  [...mb1.querySelectorAll('.rt-sec .h select[data-pick="athlete"] option')].map(o => o.getAttribute('value') + ':' + o.textContent + (o.hasAttribute('selected') ? ' (on)' : '')).join('|') === '*:All athletes|i0:First Athlete · 3 runs (on)'
  && [...mb1.querySelectorAll('.rt-runs thead th')].map(e => headName(e)).filter(Boolean).join('|') === 'Result|Run 0|Run 1|Run 3'
  && [...mb0.querySelectorAll('select[data-pick="athlete"] option')].map(o => o.textContent).join('|') === 'All athletes|First Athlete · 1 run' && [...mb0.querySelectorAll('.rt-runs thead th')].map(e => headName(e)).filter(Boolean).join('|') === 'Result|Run 0'
  && !el(b.routineBody(Object.assign({}, rt, { origin: {} }))).querySelector('select[data-pick="athlete"]')
  && !el(b.routineBody(Object.assign({}, noZero, { origin: {}, runs: [] }))).querySelector('select[data-pick="athlete"]'), mb1.querySelector('.rt-sec .h') && mb1.querySelector('.rt-sec .h').innerHTML);
check('the manager with runs on two athletes: a pick in the Runs heading (the latest run\'s athlete selected, each with its count), the table filtered to them; a routine whose runs name no athlete - no pick',
  mb2.querySelector('.rt-sec .h select[data-pick="athlete"]') && mb2.querySelector('select[data-pick="athlete"] option[selected]').getAttribute('value') === 'i0' && mb2.querySelector('select[data-pick="athlete"] option[selected]').textContent === 'First Athlete · 3 runs'
  && [...mb2.querySelectorAll('.rt-runs thead th')].map(e => headName(e)).filter(Boolean).join('|') === 'Result|Run 0|Run 1|Run 3' && [...mb2.querySelectorAll('.rt-sec .h')].map(h => h.textContent).join('|').startsWith('Runs — each run against the one before it')
  && !el(b.routineBody(Object.assign({}, rt, { origin: {} }))).querySelector('select[data-pick="athlete"]'), mb2.querySelector('select[data-pick="athlete"]') && mb2.querySelector('select[data-pick="athlete"]').outerHTML);
const rtSrc1 = fs.readFileSync(path.join(__dirname, '..', '..', 'web_app', 'static', 'js', 'routines.js'), 'utf8');
check('the page fills the athletes once the dialog is up (the keys and the cache\'s tree, the paperclip\'s roster order), re-renders the comparison and asks the cache as the athlete changes, names the athlete on the cache question, the load (with their name, for the refusal) and the record, and the manager\'s pick re-renders the body',
  rtSrc1.includes("if (src === 'intervals') { renderInterval(); fillAthletes(p, runState.plan); }") && rtSrc1.includes("fetchJson('/intervals/athletes'), fetchJson('/cache/inspect')") && rtSrc1.includes("intervalsRosterOf(keyed, tree)")
  && rtSrc1.includes("if (e.target.matches('select[data-load=\"athlete\"]')) athleteChanged();") && rtSrc1.includes("asked.subject ? { athlete: asked.subject.id } : {}") && rtSrc1.includes("who.id ? { athlete: who.id, athlete_name: who.name || '' } : {}")
  && rtSrc1.includes("a.id ? { subject: { source: 'intervals', id: a.id, name: a.name } } : {}") && rtSrc1.includes("managerState.athlete = pick.value;") && rtSrc1.includes("if (c === 'now') return (((runState && runState.pre && runState.pre.data) || {}).subject) || {};"));
check('the load reads no refresh box any more (Everything again lives in the Intervals.icu dialog) and the load body carries none', !rtSrc1.includes('data-load="refresh"') && !rtSrc1.includes('aux_datasets: plan.aux_kinds || [], refresh }'));
check('the frame\'s problems (§16.1) stand under Data for the data loaded now: rendered hidden for a loader routine (the load is the choice as the dialog opens) and shown for a file routine with the frame as the choice; the page shows them as the choice changes',
  el(b.runDialog(rr, { loaded: true, ok: true, line: '1 of 2 columns empty in this data: g', fit: { missing: ['g'] }, data: { name: '', source: 'intervals', rows: 9, columns: 1, date_range: '2026-08-12 to 2026-10-10' }, plan: { source: 'intervals', window_days: 30, aux_kinds: [] } })).querySelector('.rt-row[data-row="data"] .rt-fit.note').getAttribute('style') === 'display:none'
  && !el(b.runDialog(rr, { loaded: true, ok: true, line: '1 of 2 columns empty in this data: g', fit: { missing: ['g'] }, data: { name: 'other.csv', source: 'csv', rows: 9, columns: 1 }, plan: { source: 'file' } })).querySelector('.rt-fit.note').getAttribute('style')
  && rtSrc1.includes("p.d.querySelectorAll('.rt-fit[data-for=\"now\"]').forEach(el => { el.style.display = choice === 'now' ? '' : 'none'; });"));
check('the page (§16): the footer is the time alone; the athlete and interval rows grey out when the data loaded now is picked; the load\'s band carries the dot, the words and a bar filled to the job\'s percent (sweeping without one) and dims the rows while it shows; the cache pick shows with its choice; the stylesheet has the rows, the band and the set height',
  rtSrc1.includes("if (note) note.textContent = build.tookLine(st.routine, windows.length);") && rtSrc1.includes("p.d.querySelectorAll('.rt-row[data-row=\"athlete\"], .rt-row[data-row=\"interval\"]').forEach(el => el.classList.toggle('off', choice !== 'load'));")
  && rtSrc1.includes("function progress(text, kind, percent) {") && rtSrc1.includes("p.body.classList.toggle('rt-busy', busy);") && rtSrc1.includes("'<div class=\"bar' + (n == null ? ' sweep' : '') + '\"><i' + (n != null ? ' style=\"width:' + n + '%\"' : '') + '></i></div>'")
  && rtSrc1.includes("progress(job.message || 'Loading…', 'loading', job.total > 0 ? job.percent : null);") && rtSrc1.includes("p.d.querySelectorAll('.rt-cachepick').forEach(el => { el.style.display = ''; });")
  && rtSrc1.includes(`'<div class="ui-dlg-b"></div><div class="rt-progress" style="display:none"></div>' +`)
  && dlgCss0().includes('.rt-row { display: grid; grid-template-columns: 76px 1fr;') && dlgCss0().includes('.rt-row.off > label, .rt-row.off > div { opacity: .4; pointer-events: none; }') && dlgCss0().includes('.rt-progress .bar {') && dlgCss0().includes('.rt-progress .bar.sweep i {')
  && dlgCss0().includes('#routineRunModal .ui-dlg-b.rt-busy > .rt-row { opacity: .45; pointer-events: none; }') && !dlgCss0().includes('.rt-cache ') && !dlgCss0().includes('.rt-eta') && !dlgCss0().includes('.rt-load '));
check('Run waits for the athletes of an Intervals routine: the select starts as loading, Run is off until it is ready (a load before would take whichever key was used last); a routine without the select is as before',
  rd.querySelector('select[data-load="athlete"]').getAttribute('data-state') === 'loading' && rtSrc1.includes("on = (!a || a.getAttribute('data-state') === 'ready') && (!plan || windows.length > 0);") && rtSrc1.includes("sel.setAttribute('data-state', 'ready');") && rtSrc1.includes("sel.setAttribute('data-state', 'failed'); updateRunButton();"));

// ---- step 2: the run view's state - the arrows, the position, the composer, the Save pill ----
w.RoutinesUI.enterRunView({ id: 'r1', name: 'Rows above a line', current_version: 2 }, [0, 1, 2], 2, { version: 2 });
const pos = doc.querySelector('#chainPosition');
check('run view: the pane and the tabs cleared, the id line and the strip written for the run, the position counts the runs the arrows step through - run 2, the last of run 0, 1 and 2, reads "3 of 3" - with the next arrow off, the composer locked, the Save pill asked to hide',
  w.RoutinesUI.inRunView() && global.__tabsCleared === 1 && global.__ids.run === '2 · v2' && global.__strip.run === 2 && pos.textContent === '3 of 3' && doc.querySelector('#nextResponse').disabled === true && doc.querySelector('#prevResponse').disabled === false
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
check('the run view on an athlete\'s runs (§23): the position counts their runs alone and names them - run 1, the second of their run 0, 1 and 3, reads "2 of 3 · First Athlete" (the name is plain text until another athlete has a run of the period) - the id line carries the name, both arrows on; a pending run on them says running with the name',
  pos.textContent === '2 of 3 · First Athlete' && !pos.querySelector('.rt-who') && global.__ids.run === '1 · v2 · First Athlete' && doc.querySelector('#prevResponse').disabled === false && doc.querySelector('#nextResponse').disabled === false
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

// ---- the interval and the fill (2026-11-06, docs/ROUTINES_DESIGN.md §14): the calendar arithmetic at known dates, the plan, the words ----
const fri = new Date(2026, 10, 6);                                        // Fri 6 Nov 2026
const wk = b.units('week', fri, 365), mo = b.units('month', fri, 365), dy = b.units('day', fri, 365), yr = b.units('year', fri, 365);
const dayAfter = iso => { const d = b.dayOf(iso); return b.isoDay(new Date(d.getFullYear(), d.getMonth(), d.getDate() + 1)); };
const consecutive = (u, step) => u.every((w, i) => i === 0 || dayAfter(u[i - 1][1]) === w[0]);
check('units: the complete weeks within 365 days back from Fri 6 Nov 2026 - Monday to Sunday, the last 26 Oct – 1 Nov (this week is not complete), the first the Monday on or after 6 Nov 2025, consecutive, 51 of them',
  wk[wk.length - 1].join(' ') === '2026-10-26 2026-11-01' && wk[0].join(' ') === '2025-11-10 2025-11-16' && wk.length === 51 && consecutive(wk) && wk.every(w => b.dayOf(w[0]).getDay() === 1 && b.dayOf(w[1]).getDay() === 0), [wk[0], wk[wk.length - 1], wk.length]);
check('units: the complete months - October 2026 last, December 2025 first (November 2025 starts before the horizon), 11; the days - yesterday last, 365 back; no complete year (2025 lies before 6 Nov 2025)',
  mo[mo.length - 1].join(' ') === '2026-10-01 2026-10-31' && mo[0].join(' ') === '2025-12-01 2025-12-31' && mo.length === 11 && consecutive(mo)
  && dy[dy.length - 1].join(' ') === '2026-11-05 2026-11-05' && dy[0].join(' ') === '2025-11-06 2025-11-06' && dy.length === 365 && yr.length === 0, [mo[0], mo.length, dy[0], dy.length, yr]);
check('units: on 1 January the year before is a complete year within 365 days; on a Monday the last week ended yesterday; on a Sunday it is the week before; a 14-day horizon holds one week and no month',
  b.units('year', new Date(2027, 0, 1), 365).map(w => w.join(' ')).join('|') === '2026-01-01 2026-12-31' && b.units('week', new Date(2026, 10, 2), 365).pop().join(' ') === '2026-10-26 2026-11-01'
  && b.units('week', new Date(2026, 10, 1), 365).pop().join(' ') === '2026-10-19 2026-10-25' && b.units('week', fri, 14).map(w => w.join(' ')).join('|') === '2026-10-26 2026-11-01' && b.units('month', fri, 14).length === 0 && b.units('custom', fri, 365).length === 0);
check('unitText: a week with its days, the year once (both when the years differ); a month in full; a day; a year; the short forms for a table or a line',
  b.unitText('week', ['2026-10-26', '2026-11-01']) === 'Mon 26 Oct – Sun 1 Nov 2026' && b.unitText('week', ['2025-12-29', '2026-01-04']) === 'Mon 29 Dec 2025 – Sun 4 Jan 2026' && b.unitText('week', ['2026-10-26', '2026-11-01'], true) === '26 Oct – 1 Nov' && b.unitText('week', ['2026-10-19', '2026-10-25'], true) === '19 – 25 Oct' && b.unitText('week', ['2026-10-19', '2026-10-25']) === 'Mon 19 Oct – Sun 25 Oct 2026'
  && b.unitText('month', ['2026-10-01', '2026-10-31']) === 'October 2026' && b.unitText('month', ['2026-10-01', '2026-10-31'], true) === 'Oct 2026' && b.unitText('day', ['2026-11-05', '2026-11-05']) === 'Thu 5 Nov 2026' && b.unitText('day', ['2026-11-05', '2026-11-05'], true) === '5 Nov'
  && b.unitText('year', ['2026-01-01', '2026-12-31']) === '2026' && b.unitText('week', null) === '' && b.dateText('2025-11-10') === '10 Nov 2025', [b.unitText('week', ['2025-12-29', '2026-01-04'])]);
const weekly = JSON.parse(JSON.stringify(two));
const wkRun = (n, w, id, status, est) => ({ number: n, version: 2, created: 1793000000 + n, status: status || 'ran', interval: 'week', data: { source: 'intervals', subject: { id, name: id === 'i0' ? 'First Athlete' : 'Second Athlete' }, window: w }, inputs: {}, comparison: { moved: 0, compared: 1 }, results: [{ estimate: est || '+1', low: null, high: null }, { estimate: '+9', low: null, high: null }] });
weekly.runs = weekly.runs.concat(wk.slice(-12).map((w, i) => wkRun(10 + i, w, 'i0', i === 3 ? 'failed' : 'ran', '+' + (10 + i))), [wkRun(30, wk[0], 'i1')]);
const plan0 = b.fillPlan(weekly, 'week', 'i0', wk), plan1 = b.fillPlan(weekly, 'week', 'i1', wk), planM = b.fillPlan(weekly, 'month', 'i0', mo);
check('fillPlan: on the first athlete the last 12 weeks are run but one that failed - 40 to run (the failed one among them), 11 kept, the last run already; the second athlete has one week run, the first; the custom runs and the other athlete\'s weeks count for nothing; months: none run',
  plan0.toRun.length === 40 && plan0.kept === 11 && plan0.lastRun && plan0.toRun.some(w => w === wk[wk.length - 9]) && plan0.last === wk[wk.length - 1]
  && plan1.toRun.length === 50 && plan1.kept === 1 && !plan1.lastRun && planM.toRun.length === 11 && planM.kept === 0, [plan0.toRun.length, plan0.kept, plan1.toRun.length, planM.toRun.length]);
check('fillWindows: with the fill, every unit not run yet; without, the last complete unit alone; nothing missing - the last again; no unit - nothing',
  b.fillWindows(plan0, true).length === 40 && b.fillWindows(plan0, false).length === 1 && b.fillWindows(plan0, false)[0] === plan0.last
  && b.fillWindows(b.fillPlan(weekly, 'week', 'i0', wk.slice(-3)), true).map(w => w.join(' ')).join('|') === '2026-10-26 2026-11-01' && b.fillWindows(b.fillPlan(weekly, 'year', 'i0', yr), true).length === 0);
const ip = el(b.intervalPlan(plan0, 365, true)), ipOff = el(b.intervalPlan(plan0, 365, false)), ip1 = el(b.intervalPlan(plan1, 365, true)), ipY = el(b.intervalPlan(b.fillPlan(weekly, 'year', 'i0', yr), 365, true)), ipAll = el(b.intervalPlan(b.fillPlan(weekly, 'week', 'i0', wk.slice(-3)), 365, true));
check('intervalPlan (§16.1): "Last complete week: 26 Oct – 1 Nov — run already" and the box on, "Fill the weeks back to 10 Nov 2025 — 40 not run yet"; off when asked; nothing about the download, the kept, the cost, the background or the horizon',
  ip.querySelector('.rt-plan b').textContent === '26 Oct – 1 Nov' && ip.querySelector('.rt-plan .n').textContent === '— run already' && ip.querySelector('input[data-load="fill"]').hasAttribute('checked') && !ipOff.querySelector('input[data-load="fill"]').hasAttribute('checked')
  && ip.querySelector('.rt-fillbox').textContent.trim() === 'Fill the weeks back to 10 Nov 2025 — 40 not run yet' && !ip.textContent.includes('download') && !ip.textContent.includes('kept') && !ip.textContent.includes('background') && !ip.textContent.includes('horizon') && !ip.textContent.includes('about'), ip.textContent);
check('intervalPlan: a week not run yet says so; 49 to fill beside it; no complete year - said, no box; everything run - said with the count and "Run runs it again", no box; a plan with 14 days names them',
  ip1.querySelector('.rt-plan .n').textContent === '— not run yet' && ip1.querySelector('.rt-fillbox').textContent.trim() === 'Fill the weeks back to 10 Nov 2025 — 49 not run yet'
  && ipY.querySelector('.rt-plan.warn').textContent === 'No complete year within the last 365 days.' && !ipY.querySelector('input')
  && ipAll.textContent.includes('Every week back to 12 Oct 2026 is run already (3 weeks).') && ipAll.querySelector('.rt-plan .n').textContent === '— run already; Run runs it again' && !ipAll.querySelector('input')
  && el(b.intervalPlan(b.fillPlan(weekly, 'year', 'i0', []), 14, true)).querySelector('.rt-plan.warn').textContent === 'No complete year within the last 14 days.', [ip1.textContent, ipAll.textContent]);
check('a set interval has no Compare row: compareSection is for custom runs and only with two runs to choose from (the run before on the athlete and run 0 on their data); one choice is nothing shown',
  typeof b.compareSentence === 'undefined' && el(b.compareSection(two, two.versions[1], 'i0')).querySelector('.rt-row[data-row="compare"]') && b.compareSection(two, two.versions[1], 'i1') === '' && b.compareSection(Object.assign({}, two, { runs: [] }), two.versions[1], 'i0') === '', b.compareSection(two, two.versions[1], 'i1'));
check('runLabel: Run 40 weeks with the fill; Run for one unit; Run again when the last is run already and nothing is missing',
  b.runLabel(plan0, true) === 'Run 40 weeks' && b.runLabel(plan0, false) === 'Run' && b.runLabel(plan1, false) === 'Run' && b.runLabel(b.fillPlan(weekly, 'week', 'i0', wk.slice(-3)), true) === 'Run again');
check('intervalRow: Day · Week · Month · Year · Custom, the kind on; lastInterval: the latest run\'s under the current version, custom when it has none or there is no run; tookOf: the last run\'s time, else run zero\'s',
  [...el(b.intervalRow('week')).querySelectorAll('[data-interval]')].map(e => e.getAttribute('data-interval') + (e.className === 'on' ? '*' : '')).join(' ') === 'day week* month year custom'
  && b.lastInterval(weekly) === 'week' && b.lastInterval(two) === 'custom' && b.lastInterval(Object.assign({}, two, { runs: [] })) === 'custom' && b.tookOf(Object.assign({}, two, { runs: [Object.assign({}, two.runs[0], { elapsed: 77 })] })) === 77);
const rdw = el(b.runDialog(weekly, { loaded: false, ok: false, line: '', plan: { source: 'intervals', window_days: 30, aux_kinds: ['summary'], metrics: [], subject: { id: 'i0', name: 'First Athlete' } } }, { max_days: 365 }, 'week'));
check('run dialog opened on Week: the Interval row under the athlete with Week on, the plan\'s place, the pickers hidden (custom shows them); nothing said about the kinds or the metrics; a file routine has no Interval row',
  rdw.querySelector('.rt-interval [data-interval="week"]').className === 'on' && rdw.querySelector('.rt-interval-plan') && rdw.querySelector('.rt-loadwin').getAttribute('style') === 'display:none' && !rd.querySelector('.rt-loadwin').getAttribute('style')
  && !rdw.textContent.includes('metrics as the original') && !rd.textContent.includes('the original’s')
  && !el(b.runDialog(rr, { loaded: true, ok: true, line: 'fits', fit: { missing: [] }, data: { name: 'a.csv', source: 'csv', rows: 9, columns: 2 }, plan: { source: 'file' } })).querySelector('.rt-interval'), rdw.textContent.slice(0, 300));
const fs1 = { running: true, routine_id: 'r1', interval: 'week', total: 41, done: 12, failed: 0, current: ['2026-02-02', '2026-02-08'], left: 900 };
check('fillLine: while it runs - the count, the unit under way, the time left; failed counted; stopped - after how many, the reason; ended - how many in how long (the toast\'s words); fillBar: the live dot, the line and Stop while it runs, nothing after',
  b.fillLine(fs1) === 'Filling the weeks · 12 of 41 done · 2 – 8 Feb running · about 15 min left' && b.fillLine(Object.assign({}, fs1, { failed: 2 })).includes('12 of 41 done (2 failed) ·')
  && b.fillLine({ running: false, interval: 'month', total: 12, done: 5, failed: 1, stopped: true, error: 'the data on the Data tab changed' }) === 'Stopped after 5 of 12 months: the data on the Data tab changed · 1 failed'
  && b.fillLine({ running: false, interval: 'week', total: 41, done: 41, failed: 0, elapsed: 1140 }) === 'Filled 41 weeks in 19 min' && b.fillLine({ running: false, interval: 'day', total: 1, done: 1, failed: 0, elapsed: 20 }) === 'Filled 1 day in 20 s' && b.fillLine({ running: false, interval: 'week', total: 4, done: 4, failed: 0, elapsed: 0.4 }) === 'Filled 4 weeks in under a second' && b.fillLine(null) === ''
  && el(b.fillBar(fs1)).querySelector('.rt-fillbar .live') && el(b.fillBar(fs1)).querySelector('.rt-fillbar .t').textContent === b.fillLine(fs1) && el(b.fillBar(fs1)).querySelector('button[data-act="stop-fill"]').textContent === 'Stop' && b.fillBar(null) === '' && b.fillBar({ running: false }) === '', b.fillLine(fs1));
// an ended fill leaves no bar (2026-11-08): its last word is the toast's, and the table says what landed
const fsDone = { running: false, routine_id: 'r1', interval: 'week', total: 41, done: 41, failed: 0, elapsed: 1140 }, fsStop = { running: false, routine_id: 'r1', interval: 'week', total: 41, done: 5, failed: 1, stopped: true, error: 'asked to stop' };
check('fillBar after the fill: nothing, ended or stopped; fillLine still words both for the toast', b.fillBar(fsDone) === '' && b.fillBar(fsStop) === '' && b.fillLine(fsDone) === 'Filled 41 weeks in 19 min' && b.fillLine(fsStop).startsWith('Stopped after 5 of 41 weeks'));
check('manager actions while a fill runs: Run and Delete greyed with the reason - "stop it below" on the routine under the fill, the other routine named otherwise; Rename and the .py stay; nothing greyed once it has ended',
  el(b.actions(routine, fs1)).querySelector('[data-act="run"]').hasAttribute('disabled') && el(b.actions(routine, fs1)).querySelector('[data-act="run"]').getAttribute('title') === 'a fill is running — wait for it, or stop it below'
  && el(b.actions(routine, fs1)).querySelector('[data-act="delete"]').getAttribute('title') === 'a fill is running — wait for it, or stop it below' && !el(b.actions(routine, fs1)).querySelector('[data-act="rename"]').hasAttribute('disabled')
  && el(b.actions(Object.assign({}, routine, { id: 'r9' }), Object.assign({}, fs1, { routine_name: 'Start hours' }))).querySelector('[data-act="run"]').getAttribute('title') === 'a fill is running on Start hours — wait for it, or stop it there'
  && !el(b.actions(routine, fsDone)).querySelector('[data-act="run"]').hasAttribute('disabled') && !el(b.actions(routine, fsDone)).querySelector('[data-act="delete"]').hasAttribute('disabled'));
// the view's day is given, as in every other check of the table by unit (2026-11-11: this one read the real clock, and the fixture's first
// week - the picked athlete's only run - left the one-year view on 11 November 2026: no table after the bar, and the battery red from that day)
const mbf = el(b.routineBody(Object.assign({}, weekly, { origin: {} }), fs1, { today: fri, horizon: 365 }));
check('the manager body with a fill running carries the line under the Runs heading, above the table; without one, nothing',
  mbf.querySelector('.rt-fillbar') && mbf.querySelector('.rt-fillbar').parent.children[mbf.querySelector('.rt-fillbar').parent.children.indexOf(mbf.querySelector('.rt-fillbar')) + 1].className === 'rt-byunit' && !el(b.routineBody(Object.assign({}, weekly, { origin: {} }), null, { today: fri, horizon: 365 })).querySelector('.rt-fillbar'));
check('metricLabel (§14.4): the trailing count and date range dropped, the metric kept; "n = 380" too; a label with none is as it was; a count in the middle stays; never emptied',
  b.metricLabel('mean maximal power, best continuous 5s average, all 380 activities, 2025-11-01..2026-11-04') === 'mean maximal power, best continuous 5s average'
  && b.metricLabel('session start hour, mode, n = 60, 2026-07-29 to 2026-09-26') === 'session start hour, mode' && b.metricLabel('mean power, 20 min') === 'mean power, 20 min' && b.metricLabel('rows above 155, all 200 rows, of 3 columns') === 'rows above 155, all 200 rows, of 3 columns'
  && b.metricLabel('all 380 activities') === 'all 380 activities' && b.metricLabel('mean, 2026-01-01 → 2026-02-01') === 'mean' && b.metricLabel('') === '');
const mbl = el(b.routineBody(Object.assign({}, rr, { origin: {}, versions: rr.versions.map((v, i) => i === 1 ? Object.assign({}, v, { manifest: Object.assign({}, v.manifest, { results: [Object.assign({}, v.manifest.results[0], { label: 'rows above the line, all 200 rows, 2026-01-01..2026-03-01' })].concat(v.manifest.results.slice(1)) }) }) : v) })));
check('the trimmed label is what the Summary\'s runs table shows, the full label on hover; the Comparison tab too',
  mbl.querySelector('.rt-runs td.label').textContent === 'rows above the line' && mbl.querySelector('.rt-runs td.label').getAttribute('title').endsWith('2026-03-01')
  && el(b.comparisonTab({ run: Object.assign({}, run3, { comparison: Object.assign({}, run3.comparison, { rows: run3.comparison.rows.map(x => Object.assign({}, x, { label: 'rows above, all 9 rows' })) }) }), against_data: null })).querySelector('td.label').textContent === 'rows above');
const rtSrcF = fs.readFileSync(path.join(__dirname, '..', '..', 'web_app', 'static', 'js', 'routines.js'), 'utf8');
check('the page: more than one unit goes to POST /routines/<id>/fill after the span is loaded and checked, then the Summary opens on the routine - on the interval being filled, whatever was in view (2026-11-14) - and the fill is watched at GET /routines/fill every three seconds; Stop posts to /routines/fill/stop; one unit runs through /run cut to the unit; a reload probes for a fill; the composer stays locked with the reason while a fill runs; Run and Delete refuse during one',
  rtSrcF.includes("if (windows.length > 1) { startFill(st, plan, windows, values, auxLoaded, loadDone, p); return; }") && rtSrcF.includes("fetchJson('/routines/' + encodeURIComponent(st.id) + '/fill', { method: 'POST'") && rtSrcF.includes("managerState.interval = plan.kind;") && rtSrcF.includes("watchFill();\n            openManager(routine.id);")
  && rtSrcF.includes("const tick = () => fetchJson('/routines/fill').then(res => {") && rtSrcF.includes("fillTimer = setTimeout(tick, 3000);") && rtSrcF.includes("fetchJson('/routines/fill/stop', { method: 'POST' })")
  && rtSrcF.includes("Object.assign(loadDone, { start_date: windows[0][0], end_date: windows[0][1], cached_from: loadDone.cached_from || [loaded.start, loaded.end] });")
  && el(b.dataTab({ source: 'intervals', load: { source: 'intervals', start_date: '2026-10-26', end_date: '2026-11-01', cached_from: ['2025-11-10', '2026-11-01'] } }, {})).textContent.includes('Intervals.icu 2026-10-26 → 2026-11-01 · cut from the load 2025-11-10 → 2026-11-01') && rtSrcF.includes("setTimeout(probeFill, 1500);")
  && rtSrcF.includes("if (fillRunning()) { composerLock(fillReason()); return; }") && rtSrcF.includes("if (fillRunning()) { toast('A fill is running (") && rtSrcF.includes("if (fillRunning() && fillFor(r.id)) { toast('A fill is running on this routine; stop it first.'); return; }") && !rtSrcF.includes('refreshBadge') && typeof w.RoutinesUI.fillRunning === 'function' && w.RoutinesUI.fillRunning() === false);

// ---- the Summary by interval (2026-11-06, docs/ROUTINES_DESIGN.md §14.6): the counts and the filter bar, the series, the table by unit, the thumbnails, the enlarged chart, the Trend tab ----
check('intervalCounts / openInterval: the first athlete has 11 weeks (the failed one not counted) and 3 custom (two runs and run 0, theirs); the second one week and one custom; the Summary opens on the latest run\'s interval - week for the first, custom without a set interval',
  JSON.stringify(b.intervalCounts(weekly, 'i0')) === JSON.stringify({ day: 0, week: 11, month: 0, year: 0, custom: 3 }) && JSON.stringify(b.intervalCounts(weekly, 'i1')) === JSON.stringify({ day: 0, week: 1, month: 0, year: 0, custom: 1 })
  && b.openInterval(weekly, 'i0') === 'week' && b.openInterval(two, 'i0') === 'custom' && b.openInterval(Object.assign({}, two, { runs: [] }), 'i0') === 'custom', [b.intervalCounts(weekly, 'i0'), b.intervalCounts(weekly, 'i1')]);
const fbar = el(b.filterBar(b.intervalCounts(weekly, 'i0'), 'week'));
check('filterBar: Daily · Weekly · Monthly · Yearly · Custom in that order, each with its count, the one shown on, those never run greyed and titled',
  [...fbar.querySelectorAll('[data-filter]')].map(e => e.getAttribute('data-filter') + ':' + e.className + ':' + ((e.querySelector('.k') || {}).textContent || '-')).join(' ') === 'day:off:- week:on:11 month:off:- year:off:- custom::3'
  && fbar.querySelector('[data-filter="day"]').getAttribute('title') === 'no run with this interval yet' && !fbar.querySelector('[data-filter="week"]').getAttribute('title'));
const s0 = b.series(weekly, 'week', 'i0', wk);
check('series: the one kept line; a point per unit of the horizon with the latest run on it - the failed week keeps its failed run as a row without values (2026-11-08) and counts as not run; the rows the units with a run, the latest first; the first and last unit run; 40 missing, 39 of them before the first',
  s0.lines.length === 1 && s0.points.length === 51 && s0.rows.length === 12 && s0.rows[0].unit === wk[50] && s0.rows[0].run.number === 21 && s0.rows[11].run.number === 10 && s0.points[42].run === null && s0.points[42].failed && s0.points[42].values === null && s0.points[42].failed.status === 'failed'
  && s0.rows.filter(p => !p.run).length === 1 && s0.first === 39 && s0.last === 50 && s0.missing === 40 && s0.missingBefore === 39 && s0.rows[0].values[0].estimate === '+21'
  && b.series(Object.assign({}, weekly, { runs: weekly.runs.filter(x => x.status !== 'failed') }), 'week', 'i0', wk).rows.length === 11, [s0.rows.length, s0.first, s0.last, s0.missing, s0.missingBefore]);
// a routine with two lines sharing a prefix, eight weeks run on the first athlete with a gap and a failed week, the values rising
const wk2 = JSON.parse(JSON.stringify(two));
wk2.versions[1].manifest.results = [{ cell: 2, index: 0, label: 'mean maximal power, best continuous 5s average, all 380 activities, 2025-11-01..2026-11-04', typed: false, dropped: false, estimate: '1192', low: '1150', high: '1230', unit: 'W' },
  { cell: 2, index: 1, label: 'mean maximal power, best continuous 60s average, all 380 activities, 2025-11-01..2026-11-04', typed: false, dropped: false, estimate: '636', low: '610', high: '660', unit: 'W' }, { cell: 4, index: 0, label: 'typed', typed: true, dropped: true, estimate: '1' }];
wk2.runs = wk.slice(-8).map((w, i) => ({ number: 40 + i, version: 2, created: 1793000000 + i, status: i === 2 ? 'failed' : 'ran', interval: 'week', data: { source: 'intervals', subject: { id: 'i0', name: 'First Athlete' }, window: w },
  results: i === 2 ? [] : [{ estimate: String(1100 + 20 * i), low: String(1080 + 20 * i), high: String(1120 + 20 * i) }, { estimate: String(600 + (i % 3) * 15), low: String(590 + (i % 3) * 15), high: String(610 + (i % 3) * 15) }, { estimate: '1' }] })).filter((x, i) => i !== 5);     // the sixth week never run
const s2 = b.series(wk2, 'week', 'i0', wk);
check('sharedPrefix: the words the labels share up to a comma; nothing when they share none or one label is the prefix',
  b.sharedPrefix(['mean maximal power, best continuous 5s average', 'mean maximal power, best continuous 60s average']) === 'mean maximal power' && b.sharedPrefix(['a, b, c', 'a, b, d', 'a, b, e']) === 'a, b' && b.sharedPrefix(['x', 'y']) === '' && b.sharedPrefix(['a, b', 'a']) === '' && b.sharedPrefix(['only']) === '');
const bt = el(b.byIntervalTable(s2, 'mean maximal power'));
check('byIntervalTable: a column per line with what differs after the shared prefix and the full label on hover, a thumbnail in each head; a row per week with a run (7: eight weeks less the one never run; the failed week a row that says why), the latest first and tinted, the dates, "open →" for the hover and the run number; each cell its estimate (no plus sign) with the mark against the row below that ran, the run and the interval on hover; the gap line with the fill as a link; no legend',
  [...bt.querySelectorAll('thead th')].map(e => e.textContent.replace(/over the weeks.*$/, '').trim()).join('|').startsWith('Week|best continuous 5s average') && bt.querySelector('thead th.m').getAttribute('title').startsWith('mean maximal power, best continuous 5s average, all 380') && bt.querySelectorAll('thead th.m .rt-thumb').length === 2
  && bt.querySelectorAll('tbody tr').length === 7 && bt.querySelector('tbody tr').className === 'latest' && bt.querySelector('tbody tr td.w').textContent === '26 Oct – 1 Novopen →run 47' && bt.querySelectorAll('tbody tr')[6].querySelector('td.w').textContent === '7 – 13 Sepopen →run 40'
  && [...bt.querySelectorAll('tbody tr')].map(r => r.getAttribute('data-run')).join(',') === '47,46,44,43,42,41,40' && bt.querySelector('tbody tr.failed[data-run="42"] td.f').getAttribute('colspan') === '2' && bt.querySelector('tbody tr.failed td.f').textContent === 'failed'
  && bt.querySelector('tbody tr td.num').textContent === '1240 =' && bt.querySelector('tbody tr td.num').getAttribute('title') === 'run 47 · [1220, 1260]' && bt.querySelectorAll('tbody tr')[6].querySelector('td.num').textContent === '1100'
  && [...bt.querySelectorAll('tbody tr')].map(r => r.textContent.replace(/open →/g, '')).join('|') === '26 Oct – 1 Novrun 471240 =615 =|19 – 25 Octrun 461220 =600 =|5 – 11 Octrun 441180 =615 =|28 Sep – 4 Octrun 431160 =600 =|21 – 27 Seprun 42failed|14 – 20 Seprun 411120 =615 =|7 – 13 Seprun 401100600'
  && bt.querySelector('.rt-byunit') && !bt.querySelector('.rt-legend') && bt.querySelector('.rt-foot').textContent === '45 weeks in the last year not run yet · fill them' && bt.querySelector('.rt-foot a[data-act="fill"]').getAttribute('data-kind') === 'week'
  && el(b.byIntervalTable(Object.assign({}, s2, { rows: s2.rows.map(p => p.failed ? Object.assign({}, p, { failed: Object.assign({}, p.failed, { line: 'failed at cell 2: KeyError: power' }) }) : p) }), 'mean maximal power')).querySelector('tr.failed td.f').textContent === 'failed at cell 2: KeyError: power',
  [[...bt.querySelectorAll('thead th')].map(e => e.textContent), [...bt.querySelectorAll('tbody tr')].map(r => r.textContent), (bt.querySelector('.rt-foot') || {}).textContent]);
// a week that lost a statement, a week with no data, a week whose data was emptier than the analysis's (§22): the numbers the run has and a
// dot with the reason where one is missing; a blank row; a small mark by the week
const wk4 = JSON.parse(JSON.stringify(wk2));
wk4.runs[6].results[1] = { estimate: null, low: null, high: null, why: 'cell 5 stopped: LinAlgError: Singular matrix' };       // run 47, the latest week: its second line not computed
wk4.runs[6].gaps = ['power is empty for 3 of 6 activity_id values'];
wk4.runs[5] = Object.assign({}, wk4.runs[5], { status: 'empty', line: 'no data in this window', results: [0, 1, 2].map(() => ({ estimate: null, low: null, high: null, why: 'no data in this window' })) });     // run 46
const s4 = b.series(wk4, 'week', 'i0', wk), bt4 = el(b.byIntervalTable(s4, 'mean maximal power')), plan4 = b.fillPlan(wk4, 'week', 'i0', wk);
const row4 = n => bt4.querySelector('tbody tr[data-run="' + n + '"]');
check('byIntervalTable with what a run could not give: the week that lost a statement keeps its number and shows a dot with the reason on hover for the other, the mark by its dates saying what was empty; the week with no data is a row of dots that say so, no failure; the line breaks there; a number is marked against the nearest week below that ran, across the one with no data, as the run itself was compared',
  s4.rows.length === 7 && row4(47).className === 'latest' && [...row4(47).querySelectorAll('td.num')].map(td => td.textContent).join('|') === '1240 ↑|·' && row4(47).querySelectorAll('td.num')[1].getAttribute('title') === 'cell 5 stopped: LinAlgError: Singular matrix'
  && row4(47).querySelector('td.w .rt-gapmark').getAttribute('title') === 'power is empty for 3 of 6 activity_id values' && !row4(46).className.includes('failed') && [...row4(46).querySelectorAll('td.num')].map(td => td.textContent).join('|') === '·|·'
  && row4(46).querySelector('td.num').getAttribute('title') === 'no data in this window' && !row4(46).querySelector('.rt-gapmark') && row4(44).querySelector('td.num').textContent === '1180 ='
  && row4(47).querySelector('td.num').getAttribute('title') === 'run 47 · [1220, 1260]'
  && el(b.thumb(s4, 0)).querySelectorAll('circle').length === 6 && b.value({ estimate: null, why: 'x' }) === null && b.has({ estimate: '0' }) && !b.has({ estimate: null }) && !b.has(null), [...bt4.querySelectorAll('tbody tr')].map(r => r.textContent));
check('the counts and the plan with a week that had no data: it is on record - counted on the filter bar, not offered to the fill again; a failed week is still to run',
  b.intervalCounts(wk4, 'i0').week === 6 && !plan4.toRun.some(w => w === wk[wk.length - 2]) && plan4.toRun.some(w => w === wk[wk.length - 6]) && plan4.kept === 6
  && b.runsOf(wk4, b.DONE, 'i0').length === 5 && b.runsOf(wk4, b.KEPT, 'i0').length === 6 && b.runsOf(wk4, b.LOST, 'i0').length === 1, [b.intervalCounts(wk4, 'i0'), plan4.kept]);
const triedW = { interval: 'week', window: ['2026-10-19', '2026-10-25'], status: 'ran', came: 9, of: 11, line: 'ran: 9 of 11 result lines; 2 not computed (cell 5 stopped: LinAlgError: Singular matrix)' };
const ipT = el(b.intervalPlan(plan0, 365, true, triedW));
check('intervalPlan with what Save found on one unit: a line above the plan when the unit gave less than every metric, the dates and the reason on hover; nothing when it gave them all, when the piece had no data, or without a trial; a piece that could not be run says so',
  ipT.querySelector('.rt-plan.rt-tried').textContent === 'One week of the original data gave 9 of the 11 metrics.' && ipT.querySelector('.rt-plan.rt-tried').getAttribute('title').startsWith('2026-10-19 → 2026-10-25 — ran: 9 of 11 result lines')
  && ipT.querySelectorAll('.rt-plan')[1].querySelector('b').textContent === '26 Oct – 1 Nov' && !el(b.intervalPlan(plan0, 365, true, Object.assign({}, triedW, { came: 11 }))).querySelector('.rt-tried')
  && !el(b.intervalPlan(plan0, 365, true, Object.assign({}, triedW, { status: 'empty', came: 0 }))).querySelector('.rt-tried') && !ip.querySelector('.rt-tried')
  && el(b.intervalPlan(plan0, 365, true, Object.assign({}, triedW, { status: 'failed', came: 0 }))).querySelector('.rt-tried').textContent === 'One week of the original data could not be run.', ipT.innerHTML.slice(0, 400));
const th0 = el(b.thumb(s2, 0)), th1 = el(b.thumb(s2, 1));
check('thumb: the line over the weeks run at their place in the calendar - broken at the failed week and the one never run (three segments of two), a dot per week, the latest ringed; titled with the line and the kind; nothing with fewer than two points',
  th0.querySelector('svg.rt-thumb').getAttribute('data-line') === '0' && th0.querySelectorAll('polyline').length === 3 && th0.querySelectorAll('circle').length === 7 && th0.querySelector('circle.last') && th0.querySelector('title').textContent === 'mean maximal power, best continuous 5s average over the weeks - click for the full chart'
  && th1.querySelector('svg').getAttribute('data-line') === '1' && b.thumb(b.series(Object.assign({}, wk2, { runs: wk2.runs.slice(0, 1) }), 'week', 'i0', wk), 0) === '', [th0.innerHTML]);
const colors = { text: '#aaa', grid: '#333', line: '#0f0', also: '#00f', box: '#777' };
const ch = el(b.trendChart(s2, 0, 12, -1, colors)), ch3 = el(b.trendChart(s2, 0, 3, 1, colors));
check('trendChart: twelve months - every unit of the horizon in view, 6 points, 45 missing; a dashed box over each stretch not run (the 43 weeks before the first run with the count written, the failed week and the one never run without - too narrow); the month labels along the axis, the year on the first; the values written at the latest, the highest and the lowest; a title per dot with its run; three months with a second line - 13 weeks in view, the right axis in the second colour',
  ch.querySelector('svg.rt-chart').getAttribute('data-points') === '6' && ch.querySelector('svg').getAttribute('data-missing') === '45' && ch.querySelectorAll('rect.rt-gap').length === 3 && [...ch.querySelectorAll('text')].filter(t => /not run yet/.test(t.textContent)).map(t => t.textContent).join('|') === '43 weeks not run yet'
  && [...ch.querySelectorAll('text')].some(t => t.textContent === 'Nov 2025') && [...ch.querySelectorAll('text')].some(t => t.textContent === 'Oct') && ch.querySelectorAll('g.pt').length === 6 && ch.querySelectorAll('g.pt title')[5].textContent.startsWith('run 47 · Mon 26 Oct – Sun 1 Nov 2026 · 1240 [1220, 1260]')
  && [...ch.querySelectorAll('text')].filter(t => ['1240', '1100'].includes(t.textContent)).length === 2 && ch.querySelectorAll('polyline').length === 3
  && ch3.querySelector('svg').getAttribute('data-missing') === '7' && ch3.querySelector('svg').getAttribute('data-points') === '6' && [...ch3.querySelectorAll('text')].some(t => t.getAttribute('fill') === '#00f') && ch3.querySelectorAll('polyline[stroke="#00f"]').length >= 1,
  [ch.querySelector('svg').getAttribute('data-points'), ch.querySelector('svg').getAttribute('data-missing'), ch.querySelectorAll('rect.rt-gap').length, [...ch.querySelectorAll('text')].map(t => t.textContent)]);
const keys1 = el(b.trendKeys(s2, 0, -1, colors)), keys2 = el(b.trendKeys(s2, 0, 1, colors));
check('trendKeys (0266): the line named with its scale in its colour; with a second line, a dashed key for it on the right scale; the same line twice is one key',
  keys1.querySelectorAll('.rt-key').length === 1 && keys1.querySelector('.rt-key').textContent === 'mean maximal power, best continuous 5s average · left scale' && keys1.querySelector('.rt-key .sw').getAttribute('style') === 'background:#0f0'
  && keys2.querySelectorAll('.rt-key').length === 2 && keys2.querySelectorAll('.rt-key')[1].textContent === 'mean maximal power, best continuous 60s average · right scale' && keys2.querySelectorAll('.rt-key .sw')[1].className === 'sw dashed' && keys2.querySelectorAll('.rt-key .sw')[1].getAttribute('style') === 'border-color:#00f'
  && el(b.trendKeys(s2, 0, 0, colors)).querySelectorAll('.rt-key').length === 1, [keys1.innerHTML, keys2.innerHTML]);
check('unitsIn: three, six and twelve months in days, weeks, months and years', b.unitsIn('week', 12) === 52 && b.unitsIn('week', 3) === 13 && b.unitsIn('month', 6) === 6 && b.unitsIn('day', 3) === 91 && b.unitsIn('year', 12) === 1);
const mbw = el(b.routineBody(Object.assign({}, wk2, { origin: {} }), null, { today: fri, horizon: 365 }));
const mbc = el(b.routineBody(Object.assign({}, two, { origin: {} }), null, { today: fri, horizon: 365 }));
check('the manager body of a routine run weekly: Runs opens on Weekly (the latest run\'s) - the heading says by week, the latest first, and the shared prefix with the unit once; the filter bar, the table by week with the failed week among its rows, no runs list and no box; a routine of custom runs: Custom on, the table by run with run 0',
  mbw.querySelector('.rt-filter [data-filter="week"]').className === 'on' && [...mbw.querySelectorAll('.rt-sec .h')].some(h => h.textContent.includes('— by week, the latest first · mean maximal power, W')) && mbw.querySelector('.rt-byunit') && !mbw.querySelector('.rt-runs')
  && mbw.querySelectorAll('.rt-by tbody tr').length === 7 && mbw.querySelector('.rt-by tbody tr').getAttribute('data-run') === '47' && mbw.querySelector('.rt-by tbody tr.failed[data-run="42"]') && !mbw.querySelector('.rt-run') && !mbw.querySelector('.rt-runbox') && !mbw.textContent.includes('latest five')
  && mbc.querySelector('.rt-filter [data-filter="custom"]').className === 'on' && mbc.querySelector('.rt-filter [data-filter="week"]').className === 'off' && mbc.querySelector('.rt-runs') && !mbc.querySelector('.rt-byunit') && [...mbc.querySelectorAll('.rt-runs thead th[data-run]')].map(e => e.getAttribute('data-run')).join(',') === '0,1,3', [[...mbw.querySelectorAll('.rt-sec .h')].map(h => h.textContent)]);
const wrun = { number: 47, version: 2, status: 'ran', interval: 'week', line: 'ran', against: 46, data: { source: 'intervals', subject: { id: 'i0', name: 'First Athlete' }, window: wk[50] }, comparison: { line: '1 of 2 moved', rows: [
  { cell: 2, index: 0, label: 'mean maximal power, best continuous 5s average, all 380 activities, 2025-11-01..2026-11-04', now: { estimate: '1240', low: '1220', high: '1260' }, before: { estimate: '1220', low: '1200', high: '1240' }, change: 20, overlap: true, mark: 'same' },
  { cell: 2, index: 1, label: 'mean maximal power, best continuous 60s average, all 380 activities, 2025-11-01..2026-11-04', now: { estimate: '615', low: '605', high: '625' }, before: { estimate: '600', low: '590', high: '610' }, change: 15, overlap: false, mark: 'up' }] } };
const tt = el(b.comparisonTab({ run: wrun, against_data: { subject: { id: 'i0', name: 'First Athlete' }, window: wk[49] } }, s2)), tc = el(b.comparisonTab({ run: wrun, against_data: { subject: { id: 'i0', name: 'First Athlete' }, window: wk[49] } }));
check('the Trend tab of a run on a set interval, with the series: the two heads name the weeks with the run number under them, a last column "Weekly trend" with each line\'s thumbnail, the legend saying what the trend is; without the series (the first render, or a custom run) the tab is as it was',
  [...tt.querySelectorAll('thead th')].map(e => e.textContent).join('|') === 'Result|19 – 25 Octrun 46|26 Oct – 1 Novrun 47|Change|Intervals|Weekly trend' && tt.querySelectorAll('td.trend .rt-thumb').length === 2 && tt.querySelector('.rt-legend').textContent.includes('The trend is each line over the weeks run on this athlete')
  && [...tc.querySelectorAll('thead th')].map(e => e.textContent).join('|') === 'Result|Run 46' + wk[49][0] + ' → ' + wk[49][1] + '|Run 47' + wk[50][0] + ' → ' + wk[50][1] + '|Change|Intervals' && !tc.querySelector('.rt-thumb'), [[...tt.querySelectorAll('thead th')].map(e => e.textContent), [...tc.querySelectorAll('thead th')].map(e => e.textContent)]);
// the names where a line is shown (§15.3): the Summary's heads and prefix, the enlarged chart's key, the Trend tab's rows
const wk3 = JSON.parse(JSON.stringify(wk2));
wk3.versions[1].manifest.results[0].name = 'Best 5 s'; wk3.versions[1].manifest.results[1].name = 'Best 60 s';
const s3 = b.series(wk3, 'week', 'i0', wk), bt3 = el(b.byIntervalTable(s3, b.sharedPrefix(s3.lines.map(l => b.lineName(l)))));
const tt3 = el(b.comparisonTab({ run: Object.assign({}, wrun, { comparison: { rows: wrun.comparison.rows.map((r, i) => Object.assign({}, r, { name: ['Best 5 s', 'Best 60 s'][i] })) } }), against_data: { subject: { id: 'i0', name: 'First Athlete' }, window: wk[49] } }, s3));
check('with names on the manifest: the table by week heads the columns with them (the recorded label still the title), the key names the line by it, the Trend tab\'s rows read it; the manager\'s results list too',
  [...bt3.querySelectorAll('thead th.m .lab')].map(e => e.textContent).join('|') === 'Best 5 s|Best 60 s' && bt3.querySelector('thead th.m .rt-thumb title').textContent.startsWith('Best 5 s over the weeks') && bt3.querySelector('thead th.m').getAttribute('title').startsWith('mean maximal power, best continuous 5s average, all 380')
  && el(b.trendKeys(s3, 1, -1, colors)).querySelector('.rt-key').textContent === 'Best 60 s · left scale' && [...tt3.querySelectorAll('tbody td.label')].map(e => e.textContent).join('|') === 'Best 5 s|Best 60 s'
  && [...el(b.routineBody(Object.assign({}, wk3, { origin: {} }), null, { today: fri, horizon: 365 })).querySelectorAll('.rt-by thead th.m .lab')].map(e => e.textContent).join('|') === 'Best 5 s|Best 60 s', [bt3.innerHTML.slice(0, 300), tt3.innerHTML.slice(0, 300)]);
const rtSrcS = fs.readFileSync(path.join(__dirname, '..', '..', 'web_app', 'static', 'js', 'routines.js'), 'utf8');
check('the page (§15.2): keep and drop move a line on the proposal and rebuild the Results section alone, more unfolds the group, a typed line\'s choice lands on the proposal, and Create sends the whole set left out; the stylesheet shows drop on hover and greys the lines set aside',
  rtSrcS.includes("const act = e.target.closest('.rt-results [data-line-act]');") && rtSrcS.includes("if (act === 'more') st.asideOpen = !st.asideOpen;") && rtSrcS.includes("line.dropped = act === 'drop'; }")
  && rtSrcS.includes("sec.innerHTML = build.resultsSection(st.proposal, !!st.asideOpen);") && rtSrcS.includes("if (line) line.dropped = seg.getAttribute('data-keep') === '0';")
  && rtSrcS.includes("drop_results: (st.proposal.results || []).filter(r => r.dropped).map(r => [r.cell, r.index])") && !rtSrcS.includes("querySelectorAll('.rt-results .r.flag')).filter(")
  && dlgCss0().includes('.rt-results .r .act {') && dlgCss0().includes('.rt-results .r:hover .act, .rt-results .r .act:focus-visible { opacity: 1; }') && dlgCss0().includes('.rt-results .r.off {') && dlgCss0().includes('.rt-results .more .aside {'));
check('the page (§15.6): Update the list asks the promoter again with the box\'s line, the fields as the person left them carried over (name, purpose, the version choice, keep fixed, the box), the group folded again; the first pass sends the instruction of the routine this chain is the origin of, read before it (the thread\'s routines first); the next-version choice fills an empty box with the routine\'s line; Create sends the box; a Retry after a failed pass keeps the line',
  rtSrcS.includes("else if (act === 'instruct') propose({ again: true });") && rtSrcS.includes("const again = !!(opts && opts.again && st.proposal);") && rtSrcS.includes("const saved = again ? readFields(p) : null;")
  && rtSrcS.includes("const instruction = again ? (saved.fields.instruction || '').trim() : (st.instruction || '');") && rtSrcS.includes("st.instruction = instruction;")
  && rtSrcS.includes("stream('/routines/propose', { thread_id: st.thread_id, chain_id: st.chain_id, instruction }, !st.fromCard, data => {") && rtSrcS.includes("if (saved) writeFields(p, saved); else syncVersionChoice();") && rtSrcS.includes("st.asideOpen = false;")
  && rtSrcS.includes("const ready = st.threadRoutines.length ? Promise.resolve(st.threadRoutines) : origins(threadId).then(uniqueRoutines);") && rtSrcS.includes("st.instruction = own && own.instruction ? String(own.instruction) : '';")
  && rtSrcS.includes("if (box && vs.change && under && under.routine.instruction && !box.value.trim()) box.value = under.routine.instruction;") && rtSrcS.includes("instruction: field('instruction')")
  && rtSrcS.includes("saved.fixed.forEach(k => { const el = p.d.querySelector('input[data-drop=\"' + k + '\"]'); if (el) el.checked = true; });") && dlgCss0().includes('.rt-instr-row { display: flex; gap: 8px; align-items: flex-start; }'));
check('the page (§19, §22): the dialog\'s header counts the chain\'s cells; nothing of the passes, of a failed cell or of a fix is read or drawn; the run dialog asks what one unit gave when Save tried it; the toast after the proof says what a smaller piece gave when it gave less; the stylesheet has the stopped statements and the mark',
  rtSrcS.includes("p.sub.textContent = 'from this chain · ' + pr.cells + ' cell' + (pr.cells === 1 ? '' : 's') + ' · ' +") && !/condens|written_chars|fixRun|failed_cell|unreached|chain_cells/.test(rtSrcS)
  && rtSrcS.includes("(v.tried || []).find(t => t.interval === plan.kind)") && rtSrcS.includes("less.map(t => 'a ' + t.interval + ' gives ' + build.triedText(t)).join(', ')")
  && !/\.rt-fix\b|\.rt-written|\.rt-aswritten|\.rt-error-cell|unreached/.test(dlgCss0()) && dlgCss0().includes('.rt-stopped summary { cursor: pointer;') && dlgCss0().includes('.rt-gapmark {'));
check('the manager\'s rail (2026-11-08): 300 px wide, a routine\'s name whole and wrapping rather than cut with an ellipsis',
  dlgCss0().includes('#routinesModal .rt-left { width: 300px; flex-shrink: 0;') && /\.rt-side \.it b \{[^}]*overflow-wrap: anywhere;/.test(dlgCss0()) && !/\.rt-side \.it b \{[^}]*text-overflow: ellipsis/.test(dlgCss0()));
check('the page (2026-11-06, the manager\'s frame 2026-11-08): the header\'s buttons are built with the fill; the manager fills the window less the scrim\'s margin and its body is the one scroll (no box of its own around the table, no runs box); the run dialog keeps its set height; the ended fill\'s bar is gone; a run\'s row, a custom run\'s head or a failed run\'s line opens the run, the gap line\'s link opens the Run dialog on the interval',
  rtSrcS.includes("actions.innerHTML = build.actions(r, fillState);") && !rtSrcS.includes("if (fillState && !fillState.running) fillState = null; }")
  && /#routinesModal \.ui-dlg\.rt-mgr \{ width: min\(1800px, 100%\); height: 100%; max-height: none;/.test(dlgCss0()) && /#routineRunModal \.ui-dlg\.run-dlg \{ width: min\(640px, 100%\); height: min\(80vh, 520px\);/.test(dlgCss0())
  && !dlgCss0().includes('.rt-fillbar.done') && !dlgCss0().includes('.rt-runbox') && !dlgCss0().includes('.rt-runlist') && !/\.rt-byunit \{[^}]*max-height/.test(dlgCss0()) && dlgCss0().includes('.rt-by tbody tr[data-run] { cursor: pointer; }') && dlgCss0().includes('.rt-by tbody tr:hover td.w .open { opacity: 1; }')
  && rtSrcS.includes("const runItem = e.target.closest('[data-act=\"open-run\"], .rt-by tr[data-run], .rt-runs th[data-run], .rt-failed[data-run]');") && rtSrcS.includes("if (fillLink && managerState.current) { openRun(managerState.current.id, { interval: fillLink.getAttribute('data-kind') }); return; }")
  && rtSrcS.includes("if (del && managerState.current) { deleteRun(managerState.current, Number(del.getAttribute('data-run'))); return; }") && rtSrcS.includes("if (!confirm('Delete run ' + number + '?')) return;") && rtSrcS.includes("{ method: 'DELETE' });") && rtSrcS.includes("compare_with: !cmp ? 'previous' : (cmp.value === 'other' && other ? other.value : cmp.value)")
  && rtSrcS.includes("runState.interval = ask.interval || build.lastInterval(r);"));
const crSrc = fs.readFileSync(path.join(__dirname, '..', '..', 'web_app', 'static', 'js', 'content-rendering.js'), 'utf8'), spSrc = fs.readFileSync(path.join(__dirname, '..', '..', 'web_app', 'static', 'js', 'stream-pane.js'), 'utf8');
check('the page: the filter bar\'s pick re-renders the body (a greyed interval is inert), a thumbnail opens the enlarged chart over the manager\'s series, the horizon asked once from the limits route (a year at most), the dialog with 3 m / 6 m / 12 m, also show and PNG; the run view draws the Trend tab\'s series from the routine\'s runs, live and stored; the tab is named Trend and the closing card links to it; the old sparkline is gone',
  rtSrcS.includes("const filter = e.target.closest('.rt-filter [data-filter]');") && rtSrcS.includes("if (!filter.classList.contains('off') && managerState.current) { managerState.interval = filter.getAttribute('data-filter'); renderManagerBody(); }")
  && rtSrcS.includes("openTrend(Number(thumb.getAttribute('data-line')))") && rtSrcS.includes("fetchJson('/intervals/get_data_limits').then(res => Math.min(365, Number((res.json || {}).max_days) || 365))") && rtSrcS.includes("trendDlg.id = 'routineTrendModal'")
  && rtSrcS.includes('<span data-months="3">3 m</span><span data-months="6">6 m</span><span class="on" data-months="12">12 m</span>') && rtSrcS.includes("if (e.target.closest('[data-act=\"png\"]')) savePng();")
  && rtSrcS.includes("d.querySelector('.rt-keys').innerHTML = build.trendKeys(s, st.line, two ? st.also : -1, colors);") && rtSrcS.includes("two ? 'The two lines are on different scales — compare their shapes, not their heights.' : ''") && rtSrcS.includes("d.querySelector('.ui-dlg-f').classList.toggle('off', !two);") && dlgCss0().includes('#routineTrendModal .ui-dlg-f.off') && rtSrcS.includes("withRoutine(routineId, run, subjectIdOf(view.subject), s => createOrUpdateTab('comparison', build.comparisonTab(view, s)));")
  && rtSrcS.includes("withRoutine(viewState.routine.id, run, subjectIdOf(viewState.subject), s =>") && crSrc.includes("tabName = 'Trend';") && spSrc.includes("const links = ['Trend'].concat(") && !rtSrcS.includes('rt-spark') && !dlgCss0().includes('.rt-spark') && ['.rt-filter', '.rt-byunit', '.rt-thumb', '.rt-foot', '#routineTrendModal', '.rt-cmp-table td.trend'].every(c => dlgCss0().includes(c)));
function dlgCss0() { return fs.readFileSync(path.join(__dirname, '..', '..', 'web_app', 'static', 'css', 'dialogs.css'), 'utf8'); }

// ---- every athlete on one period (2026-11-14, docs/ROUTINES_DESIGN.md §23): the Summary's table by athlete, the Run dialog asked for a
// period, the athletes of a run's period. Four athletes: two weeks and the original's dates run on some of them, one run with another
// input, one on emptier data that lost a line, one refused, one timed out after a kept one, one of an earlier version, one without dates
const who4 = { i0: 'First Athlete', i1: 'Second Athlete', i2: 'Third Athlete', i3: 'Fourth Athlete' };
const W1 = ['2026-10-26', '2026-11-01'], W2 = ['2026-11-02', '2026-11-08'], OCT = ['2026-10-01', '2026-10-31'], DATES = ['2026-10-07', '2026-11-14'];
const runOn = (n, id, interval, win, more) => Object.assign({ number: n, version: 2, created: 1793000000 + n, status: 'ran', interval, data: { source: 'intervals', subject: { id, name: who4[id] }, window: win }, inputs: { threshold: 250, win }, gaps: [],
  results: [{ estimate: '+' + (100 + n), low: '+90', high: '+120' }, { estimate: '+' + n, low: null, high: null }] }, more || {});
const side = { id: 'r1', name: 'Power over a week', current_version: 2, origin: {}, versions: [{ number: 1 }, { number: 2,
    run_zero: { verified: true, created: 1792000000, results: [{ estimate: '+100', low: null, high: null }, { estimate: '+0', low: null, high: null }], inputs: { threshold: 250, win: DATES } },
    manifest: { parameters: [{ key: 'threshold', label: 'Threshold', type: 'number', default: 250 }, { key: 'win', label: 'Window', type: 'date_window', derived: 'window', default: DATES }],
      results: [{ label: 'mean maximal power, 5 min', unit: 'W', estimate: '+100' }, { label: 'mean maximal power, 20 min', unit: 'W', estimate: '+0' }],
      data: { columns: [], load: { source: 'intervals', start_date: DATES[0], end_date: DATES[1], subject: { source: 'intervals', id: 'i0', name: who4.i0 } } } } }],
  runs: [runOn(1, 'i0', 'week', W1), runOn(2, 'i0', 'week', W2), runOn(3, 'i1', 'week', W1), runOn(4, 'i1', 'week', W2, { inputs: { threshold: 300, win: W2 } }),
    runOn(5, 'i2', 'week', W2, { results: [{ estimate: '+171', low: null, high: null }, { estimate: null, why: 'cell 5 stopped: too few laps' }], gaps: ['power is empty for 3 of 6 activity_id values'] }),
    runOn(6, 'i2', 'week', W1, { status: 'failed', line: 'the load was refused' }), runOn(7, 'i3', 'month', OCT), runOn(8, 'i1', null, DATES),
    runOn(9, 'i1', 'week', W2, { version: 1 }), runOn(10, 'i0', 'week', W2, { status: 'timed_out', line: 'timed out after 60 s' }), runOn(11, 'i3', null, null)] };
const standing = (kind, win) => Object.entries(b.periodRuns(side, kind, win)).map(([id, x]) => id + ':' + x.number).sort().join(' ');
check('periods (§23): the periods of a kind that any athlete has run under the current version, oldest first - two weeks, one month, no day; custom: the original\'s dates, which run 0 and a custom run share; runs that do not say their dates make no period',
  JSON.stringify(b.periods(side, 'week')) === JSON.stringify([W1, W2]) && JSON.stringify(b.periods(side, 'month')) === JSON.stringify([OCT]) && b.periods(side, 'day').length === 0
  && JSON.stringify(b.periods(side, 'custom')) === JSON.stringify([DATES]) && b.periods(two, 'custom').length === 0, [b.periods(side, 'week'), b.periods(side, 'custom'), b.periods(two, 'custom')]);
check('periodRuns: one run stands for an athlete on a period - the latest kept (a later run that timed out does not replace it, a run of an earlier version is not counted), else the latest that could not be carried out; run 0 is its athlete\'s run of the original\'s dates',
  standing('week', W2) === 'i0:2 i1:4 i2:5' && standing('week', W1) === 'i0:1 i1:3 i2:6' && standing('custom', DATES) === 'i0:0 i1:8' && standing('month', W1) === '' && b.periodRuns(side, 'week', W1).i2.status === 'failed', [standing('week', W2), standing('week', W1), standing('custom', DATES)]);
const stepAt = i => el(b.periodStep('week', [W1, W2], i));
check('periodText and the step: a set interval\'s unit as the tables say it; custom dates with the year once, twice when the years differ; the step shows the period between a link to the one before and the one after - at an end the link is off and inert',
  b.periodText('week', W2) === '2 – 8 Nov' && b.periodText('month', OCT) === 'Oct 2026' && b.periodText('custom', DATES) === '7 Oct – 14 Nov 2026' && b.periodText('custom', ['2025-12-20', '2026-01-10']) === '20 Dec 2025 – 10 Jan 2026'
  && stepAt(1).querySelector('.rt-step b').textContent === '2 – 8 Nov' && stepAt(1).querySelector('a[data-act="period"]').getAttribute('data-period') === '2026-10-26 2026-11-01' && stepAt(1).querySelectorAll('a.off').length === 1 && !stepAt(1).querySelector('a.off').hasAttribute('data-act')
  && stepAt(0).querySelector('a[data-act="period"]').getAttribute('data-period') === '2026-11-02 2026-11-08' && el(b.periodStep('month', [OCT], 0)).querySelectorAll('a.off').length === 2, stepAt(1).innerHTML);
const params4 = side.versions[1].manifest.parameters;
check('inputsNotes: a run made with other inputs than most of the rows is said in a sentence, by its number; an input written from the data (the window) is not compared; the same inputs, or no run - nothing',
  JSON.stringify(b.inputsNotes(params4, [side.runs[1], side.runs[3], side.runs[4]])) === '{"4":"ran with other inputs: Threshold 300 (the others 250)"}' && JSON.stringify(b.inputsNotes(params4, [side.runs[0], side.runs[1]])) === '{}' && JSON.stringify(b.inputsNotes(params4, [])) === '{}',
  b.inputsNotes(params4, [side.runs[1], side.runs[3], side.runs[4]]));
const at2 = el(b.byAthleteTable(side, 'week', W2, 'mean maximal power')), rowsA = [...at2.querySelectorAll('tbody tr')];
check('the table by athlete (§23): the head is Athlete and the lines without their shared words, no thumbnail; a row per athlete the routine has run on, by name, each opening the run that stands for them - the numbers as they are, with the run and the interval on hover and no mark between athletes, a dot with the reason where a line is missing; an athlete without a run of the week is offered it, and the link under the table offers the week to another athlete',
  [...at2.querySelectorAll('thead th')].map(e => e.textContent).join('|') === 'Athlete|5 min|20 min' && !at2.querySelector('.rt-thumb') && at2.querySelector('table.rt-by.rt-athletes').getAttribute('data-kind') === 'week' && at2.querySelector('table').getAttribute('data-period') === '2026-11-02 2026-11-08'
  && rowsA.map(tr => (tr.getAttribute('data-run') || tr.className) + ':' + tr.querySelector('td.w').textContent).join('|') === '2:First Athleteopen →run 2|norun:Fourth Athlete|4:Second Athlete △open →run 4|5:Third Athlete △open →run 5'
  && rowsA[0].querySelectorAll('td.num')[0].textContent === '102' && rowsA[0].querySelectorAll('td.num')[0].getAttribute('title') === 'run 2 · [+90, +120]' && rowsA[3].querySelectorAll('td.num')[1].querySelector('.rt-mark.missing') && rowsA[3].querySelectorAll('td.num')[1].getAttribute('title') === 'cell 5 stopped: too few laps'
  && rowsA[1].querySelector('td.nr').textContent === 'not run for this week · run it' && rowsA[1].querySelector('td.nr').getAttribute('colspan') === '2' && rowsA[1].querySelector('a[data-act="run-athlete"]').getAttribute('data-athlete') === 'i3' && rowsA[1].querySelector('a[data-act="run-athlete"]').getAttribute('data-name') === 'Fourth Athlete'
  && at2.querySelector('.rt-foot a[data-act="run-period"]').textContent === 'Run this week for another athlete' && !at2.querySelector('.rt-mark.up') && !at2.querySelector('.rt-mark.down') && !at2.querySelector('.rt-mark.same'), rowsA.map(tr => tr.textContent));
const at1 = el(b.byAthleteTable(side, 'week', W1, '')), atD = el(b.byAthleteTable(side, 'custom', DATES, ''));
check('the table by athlete: the mark by a name says on hover that the run\'s data was emptier than the original\'s, or that it ran with other inputs than the others; a run that could not be carried out is a row with the reason, which opens it; on custom dates run 0 is the original athlete\'s row and the others are offered "these dates"; an athlete the runs do not name is offered nothing; a routine without result lines says so',
  rowsA[2].querySelector('.rt-gapmark').getAttribute('title') === 'ran with other inputs: Threshold 300 (the others 250)' && rowsA[3].querySelector('.rt-gapmark').getAttribute('title') === 'power is empty for 3 of 6 activity_id values' && !rowsA[0].querySelector('.rt-gapmark')
  && at1.querySelector('tr.failed[data-run="6"] td.f').textContent === 'the load was refused' && at1.querySelector('tr.failed td.w').textContent === 'Third Athleteopen →run 6'
  && [...atD.querySelectorAll('tbody tr')].map(tr => (tr.getAttribute('data-run') || tr.className) + ':' + tr.querySelector('td.w').textContent.replace(/open.*/, '')).join('|') === '0:First Athlete|norun:Fourth Athlete|8:Second Athlete|norun:Third Athlete'
  && atD.querySelector('td.nr').textContent === 'not run for these dates · run it' && atD.querySelector('.rt-foot').textContent === 'Run these dates for another athlete'
  && el(b.byAthleteTable(Object.assign({}, side, { runs: side.runs.concat([Object.assign(runOn(12, 'i0', 'week', W1), { data: { source: 'intervals', window: W1 } })]) }), 'week', W2, '')).querySelector('tr.norun:not([data-run]) td.nr').textContent.startsWith('not run for this week')
  && [...el(b.byAthleteTable(Object.assign({}, side, { runs: side.runs.concat([Object.assign(runOn(12, 'i0', 'week', W1), { data: { source: 'intervals', window: W1 } })]) }), 'week', W2, '')).querySelectorAll('tr.norun')].map(tr => tr.textContent).includes('athlete not recordednot run for this week')
  && b.byAthleteTable(Object.assign({}, side, { versions: [{ number: 2, manifest: { results: [] } }] }), 'week', W2, '') === b.NO_LINES, [at1.innerHTML, atD.textContent]);
const bodyA = picks => el(b.routineBody(side, null, Object.assign({ today: new Date(2026, 10, 14) }, picks)));
const allWeek = bodyA({ athlete: b.ALL, interval: 'week' }), allBack = bodyA({ athlete: b.ALL, interval: 'week', period: W1.join(' ') }), allDates = bodyA({ athlete: b.ALL, interval: 'custom' }), oneA = bodyA({});
check('the manager with All athletes picked (§23): the pick opens with All athletes and has the latest run\'s athlete selected until it is picked; picked, the heading reads "one week, athlete by athlete" with the lines\' shared words, the filter counts the runs of every athlete, the step stands on the latest week any of them ran and the table is by athlete; a step back is the week before; custom is "the same dates"',
  [...oneA.querySelectorAll('select[data-pick="athlete"] option')].map(o => o.getAttribute('value') + (o.hasAttribute('selected') ? ' (on)' : '')).join('|') === '*|i3 (on)|i0|i1|i2' && !oneA.querySelector('.rt-step') && !oneA.querySelector('.rt-athletes')
  && allWeek.querySelector('select[data-pick="athlete"] option[selected]').getAttribute('value') === '*' && allWeek.querySelector('.rt-runsec .h .n').textContent === '— one week, athlete by athlete · mean maximal power, W'
  && allWeek.querySelector('.rt-filter [data-filter="week"]').className === 'on' && allWeek.querySelector('.rt-filter [data-filter="week"] .k').textContent === '5' && allWeek.querySelector('.rt-step b').textContent === '2 – 8 Nov' && allWeek.querySelector('.rt-athletes').getAttribute('data-period') === W2.join(' ')
  && [...allWeek.querySelector('.rt-runsec .h').children].filter(e => e.nodeType === 1).map(e => e.className.split(' ').pop()).join('|') === 'n|rt-filter|rt-step|rt-athlete-pick'
  && allBack.querySelector('.rt-step b').textContent === '26 Oct – 1 Nov' && allBack.querySelector('.rt-athletes').getAttribute('data-period') === W1.join(' ') && allBack.querySelector('tr.failed[data-run="6"]')
  && allDates.querySelector('.rt-runsec .h .n').textContent === '— the same dates, athlete by athlete · mean maximal power, W' && allDates.querySelector('.rt-step b').textContent === '7 Oct – 14 Nov 2026' && allDates.querySelector('.rt-athletes').getAttribute('data-kind') === 'custom',
  [allWeek.querySelector('.rt-runsec .h').textContent, oneA.querySelector('select[data-pick="athlete"]').outerHTML]);
check('All athletes without a period: runs that do not say their dates leave nothing to set side by side, said in a line, with no step; a routine whose runs name no athlete has no pick, so the table stays the runs\'',
  el(b.routineBody(Object.assign({}, two, { origin: {} }), null, { athlete: b.ALL })).querySelector('.rt-runsec .rt-line.muted').textContent === 'No run to set side by side yet.' && !el(b.routineBody(Object.assign({}, two, { origin: {} }), null, { athlete: b.ALL })).querySelector('.rt-step')
  && !el(b.routineBody(Object.assign({}, rt, { origin: {} }), null, { athlete: b.ALL })).querySelector('.rt-athletes') && el(b.routineBody(Object.assign({}, rt, { origin: {} }), null, { athlete: b.ALL })).querySelector('.rt-runs'));
const only3 = b.fillPlan(side, 'week', 'i3', [W2], true), only1 = b.fillPlan(side, 'week', 'i1', [W2], true);
check('the Run dialog asked for a period (§23): the plan of one unit asked for by its dates - it runs alone, named without "Last complete" and with no fill box; the button says Run, or Run again when the athlete has the unit already; a plan over the horizon is as before',
  only3.only && JSON.stringify(b.fillWindows(only3, true)) === JSON.stringify([W2]) && el(b.intervalPlan(only3, 365, true)).textContent === 'Week: 2 – 8 Nov — not run yet' && !el(b.intervalPlan(only3, 365, true)).querySelector('input[data-load="fill"]') && b.runLabel(only3, true) === 'Run'
  && el(b.intervalPlan(only1, 365, true)).textContent === 'Week: 2 – 8 Nov — run already; Run runs it again' && b.runLabel(only1, true) === 'Run again' && !plan0.only && el(b.intervalPlan(plan0, 365, true)).querySelector('.rt-plan').textContent.startsWith('Last complete week: '),
  [el(b.intervalPlan(only3, 365, true)).textContent, el(b.intervalPlan(only1, 365, true)).textContent]);
const peers4 = b.peers(side, side.runs[3]), menu4 = el(b.peersMenu(peers4, 'i1'));
check('peers (§23): the athletes with a run of the same period as the run in view, by name, each with the run that stands for them - the week\'s three; run 0\'s are those of the original\'s dates; one athlete alone on a month; none for a run of an earlier version or one that does not say its dates; the menu is headed by the period and marks the athlete in view',
  peers4.text === '2 – 8 Nov' && peers4.list.map(a => a.id + ':' + a.name + ':' + a.number).join('|') === 'i0:First Athlete:2|i1:Second Athlete:4|i2:Third Athlete:5'
  && b.peers(side, { number: 0, version: 2, data: {} }).list.map(a => a.id + ':' + a.number).join('|') === 'i0:0|i1:8' && b.peers(side, { number: 0, version: 2, data: {} }).text === '7 Oct – 14 Nov 2026' && b.peers(side, side.runs[6]).list.map(a => a.id).join() === 'i3'
  && b.peers(side, side.runs[8]).list.length === 0 && b.peers(side, side.runs[10]).list.length === 0 && b.peers(side, null).list.length === 0
  && menu4.querySelector('.h').textContent === '2 – 8 Nov' && [...menu4.querySelectorAll('.it')].map(e => e.className + ':' + e.getAttribute('data-run') + ':' + e.querySelector('b').textContent + ':' + e.querySelector('span').textContent).join('|') === 'it:2:First Athlete:run 2|it on:4:Second Athlete:run 4|it:5:Third Athlete:run 5', [peers4, menu4.innerHTML]);
const rtSrcA = fs.readFileSync(path.join(__dirname, '..', '..', 'web_app', 'static', 'js', 'routines.js'), 'utf8');
check('the page (§23): the step re-renders the body on its period; a row\'s or the table\'s offer opens the Run dialog on the table\'s interval and period - on the row\'s athlete, else skipping the athletes with a run kept for it - and asks to come back; the dialog presets the unit, which runs alone, or the custom dates, picks the athlete asked or the first not skipped, and drops the unit when an interval is picked by hand; the Summary opens again when such a run has landed; All athletes opens on the interval in view, and a fill opens the Summary on the interval it fills',
  rtSrcA.includes("if (step && managerState.current) { managerState.period = step.getAttribute('data-period'); renderManagerBody(); return; }") && rtSrcA.includes("if (ask && managerState.current) { runPeriod(ask); return; }")
  && rtSrcA.includes("openRun(r.id, Object.assign({ interval: kind, window: w, back: true },") && rtSrcA.includes("id ? { athlete: { id, name: link.getAttribute('data-name') || '' } } : { skip: Object.keys(standing).filter(a => build.KEPT.includes(standing[a].status)) }));")
  && rtSrcA.includes("if (src === 'intervals' && ask.window && !custom) runState.unit = ask.window;") && rtSrcA.includes("if (src === 'intervals' && ask.window && custom) ['start', 'end'].forEach((part, i) => {")
  && rtSrcA.includes("st.unit ? [st.unit] : build.units(st.interval, new Date(), maxDays), !!st.unit);") && rtSrcA.includes("const pick = asked.id || (free ? free.id : (rows.some(a => a.id === mine.id) ? mine.id : rows[0].id));")
  && rtSrcA.includes("st.interval = kind; st.unit = null;") && rtSrcA.includes("if (st.ask.back) openManager(routine.id);") && rtSrcA.includes("if (shown && pick.value === build.ALL) managerState.interval = shown.getAttribute('data-filter');")
  && ['.rt-sec > .h .rt-step', '.rt-by tr.norun td.w', '.rt-by td.nr a', '.chain-position .rt-who', '.save-menu.rt-peers .it.on'].every(c => dlgCss0().includes(c)));

// ---- the page and the stylesheets ----
const html = fs.readFileSync(path.join(__dirname, '..', '..', 'web_app', 'templates', 'index.html'), 'utf8');
check('page: the Routines rail entry sits between Saved workflows and the Dataset cache, without a count badge (gone 2026-11-06, §14.5); routines.js is loaded after workflow-modal.js',
  html.indexOf('id="workflowManagerPill"') < html.indexOf('id="routinesPill"') && html.indexOf('id="routinesPill"') < html.indexOf('id="datasetManagerPill"') && !html.includes('routinesBadge') && !html.includes('rb-badge')
  && html.indexOf("js/workflow-modal.js") < html.indexOf("js/routines.js"));
const shellCss = fs.readFileSync(path.join(__dirname, '..', '..', 'web_app', 'static', 'css', 'shell.css'), 'utf8');
const dlgCss = fs.readFileSync(path.join(__dirname, '..', '..', 'web_app', 'static', 'css', 'dialogs.css'), 'utf8');
const rtSrcC = fs.readFileSync(path.join(__dirname, '..', '..', 'web_app', 'static', 'js', 'routines.js'), 'utf8');
check('the page follows the proof behind the dialog (§17, §22): the watch goes on while the status is verifying, and the toast at the end says the verdict - with what a smaller piece gave when one gave less than every metric; the open manager is loaded again',
  rtSrcC.includes("if (!r || (st && st !== 'verifying')) {") && rtSrcC.includes("const less = v ? (v.tried || []).filter(t => t.status !== 'empty' && !(t.status === 'ran' && t.came === t.of)) : [];")
  && rtSrcC.includes("' · verified on the original data' + (less.length ? ' · ' + less.map(t => 'a ' + t.interval + ' gives ' + build.triedText(t)).join(', ') : '')") && rtSrcC.includes("watching[id] = true;")
  && rtSrcC.includes("if (manager && manager.style.display !== 'none') loadManager(id);"));
check('stylesheets: the pill\'s menu and its saved and open states in shell.css (the rail badge rule gone with the badge); the dialog, the manager, the card button, the composer lock, the interval row, the plan, the fill box and the fill line in dialogs.css',
  ['.save-menu', '.save-menu .it.done', '#rankButton.saved', '#rankButton.menu-open'].every(c => shellCss.includes(c)) && !shellCss.includes('.rb-badge')
  && ['#routineMakeModal', '#routinesModal', '.rt-inputs', '.rt-results .r.flag', '.rt-version', '.workflow-card-routine.has', 'body.composer-locked', '.rt-interval', '.rt-plan', '.rt-fillbox', '.rt-fillbar'].every(c => dlgCss.includes(c)));
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
  check('startRun clears what the load replaces before loading - the primary for an upload or a cache pick, everything for an integration; a custom window over the plan\'s reach or window is moved into them and said before anything loads (2026-11-08), and Run is pressed again',
    rtSrc.includes("await clearLoaded(choice === 'upload' || choice === 'cache' ? 'primary' : 'all');") && rtSrc.includes("const fit = window.DateWindow.check(window.DateWindow.of(st.limits), a && a.value, b && b.value, st.lastChanged || 'end');") && rtSrc.includes("if (fit.note) { a.value = fit.start; b.value = fit.end; progress('! ' + fit.note, 'bad'); return; }"));
  // the run view's switch (§23), driven: a run opened from the server's answers - the position counts the athlete's runs, and once the
  // routine's runs are read the name opens the athletes of the run's period; a row opens their run; alone on a period, the name is plain
  const viewOf = (i, numbers, id) => ({ run: side.runs[i], routine: { id: 'r1', name: side.name, current_version: 2 }, numbers, subject: { id, name: who4[id] }, name: side.name });
  const answers = { '/routines/r1/runs/4': viewOf(3, [3, 4, 8, 9], 'i1'), '/routines/r1/runs/5': viewOf(4, [5, 6], 'i2'), '/routines/r1/runs/7': viewOf(6, [7, 11], 'i3'), '/routines/r1': { routine: side }, '/intervals/get_data_limits': { max_days: 365 } };
  window.authService = { fetch: url => Promise.resolve({ ok: url in answers, status: url in answers ? 200 : 404, json: () => Promise.resolve(answers[url] || {}) }) };
  const settle = () => new Promise(done => setTimeout(done, 20));
  w.RoutinesUI.initialize();
  await w.RoutinesUI.viewRun('r1', 4);
  const before = pos.textContent;
  await settle();
  const who = pos.querySelector('a.rt-who');
  check('the run view (§23), driven: run 4 opens as "2 of 4 · Second Athlete" - the second of their four runs; once the routine is read the name is a switch, since two other athletes have a run of the week',
    before === '2 of 4 · Second Athlete' && pos.textContent === '2 of 4 · Second Athlete ▾' && who && who.getAttribute('title') === 'the same period for another athlete' && !doc.querySelector('#routinePeers'), [before, pos.innerHTML]);
  doc.dispatch('click', who);
  const menu = doc.querySelector('#routinePeers'), shownOpen = menu && menu.style.display !== 'none', items = menu ? [...menu.querySelectorAll('.it')].map(e => e.className + ':' + e.textContent) : [];
  doc.dispatch('click', doc.body);
  const shutByClick = menu && menu.style.display === 'none';
  doc.dispatch('click', who);
  menu.dispatch('click', menu.querySelectorAll('.it')[2].querySelector('b'));
  const shutByPick = menu.style.display === 'none';
  await settle();
  check('the switch\'s menu: a click on the name opens it under the name with the week and its three athletes, the one in view marked; a click elsewhere closes it; a row closes it and opens that athlete\'s run of the week - "1 of 2 · Third Athlete", the name a switch there too',
    shownOpen && menu.className === 'save-menu rt-peers' && items.join('|') === 'it:First Athleterun 2|it on:Second Athleterun 4|it:Third Athleterun 5' && shutByClick && shutByPick
    && pos.textContent === '1 of 2 · Third Athlete ▾' && global.__ids.run === '5 · v2 · Third Athlete', [items, pos.textContent, global.__ids]);
  await w.RoutinesUI.viewRun('r1', 7);
  await settle();
  doc.dispatch('click', pos);
  check('an athlete alone on a period: the name is plain text and a click on the position opens nothing; leaving the run view closes the menu',
    pos.textContent === '1 of 2 · Fourth Athlete' && !pos.querySelector('.rt-who') && menu.style.display === 'none' && (w.RoutinesUI.exitRunView(), menu.style.display === 'none'), pos.innerHTML);
  finish();
})();

function finish() {
  let fails = 0; for (const [n, ok, d] of results) { console.log((ok ? '  ok   ' : '  FAIL ') + n + (ok ? '' : '  <- ' + (d || ''))); if (!ok) fails++; }
  console.log(`\n${results.length - fails} passed, ${fails} failed`); process.exit(fails ? 1 : 0);
}
