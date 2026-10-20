// The code map's modal (docs/CODEMAP_DESIGN.md, 2026-10-20): the markup code-map.js builds from the server's view - the shell,
// the header with the chain's number and path, the Steps grid with its lanes and rows, the result chips by status, the notes,
// the recipe diagram laid out with the harness's dagre stand-in, the panel in its three forms, the states - and the module
// driven on the mini DOM with a scripted route: opened, a result and a step selected, the view switched, another chain opened
// through the navigator, the navigator moving under an open map, a chain the navigator does not hold, the closing card's button.
// The fixture is the prototype's view model (tests/analyst/fixtures/codemap/expected/viewmodel.json), its chain numbers turned
// into ids and tokens as the port stores them.
// Run: node tests/analyst/test_code_map.js
'use strict';
const fs = require('fs'), path = require('path');
const { makeDocument } = require(path.join(__dirname, 'minidom.js'));
const doc = makeDocument(); global.document = doc;
const calls = []; let answers = {};
global.window = { authService: { fetch: async (url) => { calls.push(url); const a = typeof answers[url] === 'function' ? answers[url]() : answers[url]; const [status, json] = a || [404, { message: 'No such chain.' }]; return { ok: status < 400, status, json: async () => json }; } } };
require(path.join(__dirname, '..', '..', 'tools', 'fixtures', 'dagre_stub.js'));      // window.dagre: the harness's layered stand-in (no edge points)
const navigated = []; global.navigateToChainId = id => { navigated.push(String(id)); const i = global.responses.findIndex(r => String(r.chain_id) === String(id)); if (i >= 0) { global.currentResponseIndex = i; global.updateNavigationButtons(); } };
global.updateNavigationButtons = () => { if (window.CodeMapUI) window.CodeMapUI.onChain(global.responses[global.currentResponseIndex] && global.responses[global.currentResponseIndex].chain_id); };
const opened = []; global.paneOpenCell = n => opened.push(n);
global.currentData = { thread_id: '1001' };
require(path.join(__dirname, '..', '..', 'web_app', 'static', 'js', 'code-map.js'));
const w = window; const b = w.__codeMapBuild; const results = []; const check = (n, c, d) => results.push([n, !!c, d]);
const el = html => { const d = doc.createElement('div'); d.innerHTML = html; return d; };
const tick = () => new Promise(r => setImmediate(r));

// ---- the fixture: the prototype's views with their chain numbers turned into ids ("1", "2", ...) and {chain:<id>} tokens ----
const VM = JSON.parse(fs.readFileSync(path.join(__dirname, 'fixtures', 'codemap', 'expected', 'viewmodel.json'), 'utf8'));
function asIds(view) {
  const tok = s => String(s).replace(/\bchain (\d+)\b/g, '{chain:$1}');
  const v = JSON.parse(JSON.stringify(view, (k, x) => {
    if (typeof x === 'string' && (k === 'text' || k === 'name' || k === 'label' || k === 'names' || k === 'cols' || k === 'nocodeText')) return tok(x);
    return x;
  }));
  v.chain_id = String(v.id); v.path = (v.path || []).map(String); v.pathTitles = Object.fromEntries(Object.entries(v.pathTitles || {}).map(([k, t]) => [String(k), t])); v.titles = v.pathTitles;
  (v.inputs || []).forEach(i => { if (i.chain != null) i.chain = String(i.chain); if (i.through != null) i.through = String(i.through); i.file = tok(i.file || ''); });
  (v.checks || []).forEach(c => { if (c.chain != null) c.chain = String(c.chain); });
  Object.values(v.steps || {}).forEach(s => { (s.takes_chain || []).forEach(t => { t.chain = String(t.chain); }); s.inputs = (s.inputs || []).map(tok); });
  Object.values(v.recipes || {}).forEach(r => { r.inputs = (r.inputs || []).map(tok); (r.items || []).forEach(it => { it.inputs = (it.inputs || []).map(tok); }); });
  Object.values(v.diagrams || {}).forEach(d => { d.nodes.forEach(n => { n.id = String(n.id).replace(/^in:From chain (\d+)$/, 'in:chain:$1'); delete n.x; delete n.y; delete n.w; delete n.h; }); d.edges = d.edges.map(e => e.map(x => String(x).replace(/^in:From chain (\d+)$/, 'in:chain:$1'))); delete d.segs; delete d.heads; delete d.w; delete d.h; });
  delete v.pills; v.version = 1;
  return v;
}
const TRIAL = asIds(VM.trial), TRIAL2 = asIds(VM.trial2), T4 = asIds(VM.t4), T5 = asIds(VM.t5);
global.responses = [{ chain_id: '1', thread_id: '1001', queryText: TRIAL.question }, { chain_id: '2', thread_id: '1001', queryText: TRIAL2.question }];
global.currentResponseIndex = 0;
const ctx = { titles: TRIAL2.titles, built: 'end', number: id => 1 + global.responses.findIndex(r => String(r.chain_id) === String(id)), chainId: '2' };

// ---- the builders ----
const sh = el(b.shell());
check('shell: a ui-dlg with the head, the body split into the map and the panel', sh.querySelector('.ui-dlg.cm-dlg .ui-dlg-h.cm-head') && sh.querySelector('.ui-dlg-b.cm-body .cm-map') && sh.querySelector('.cm-body .cm-panel'), sh.innerHTML);
const hd = el(b.header(TRIAL2, ctx, { view: 'steps', state: '' }));
check('header: the title, the chain numbered as the navigator numbers it, its path with the earlier chain a link, how the map was built with the facts, the report title, the question, the view switch with Steps pressed, the close, the Steps legend',
  hd.querySelector('.cm-head-line .title').textContent === 'Code map' && hd.querySelector('.cm-chain-no').textContent === 'chain 2'
  && hd.querySelector('.cm-path a[data-act="open-chain"][data-chain="1"]').textContent === '1' && hd.querySelector('.cm-path b.cm-path-here').textContent === '2'
  && hd.querySelector('.cm-built').textContent === 'built when the chain ended, kept with it · ' + TRIAL2.meta && hd.querySelector('.cm-title').textContent === TRIAL2.title
  && hd.querySelector('.cm-question').textContent.startsWith('Question: ') && hd.querySelector('.cm-switch button[data-view="steps"]').getAttribute('aria-pressed') === 'true'
  && hd.querySelector('.cm-switch button[data-view="diagram"]').getAttribute('aria-pressed') === 'false' && hd.querySelector('button.x[data-act="close"]')
  && hd.querySelectorAll('.cm-legend span').length === 6 && hd.querySelector('.cm-legend').textContent.includes('result recorded'), hd.innerHTML);
check('header: built now reads so; the diagram view shows the diagram legend; a chain the navigator does not hold is "an earlier chain"',
  el(b.header(TRIAL2, Object.assign({}, ctx, { built: 'now' }), { view: 'diagram', state: '' })).querySelector('.cm-built').textContent.startsWith('built now from the chain\'s record · ')
  && el(b.header(TRIAL2, ctx, { view: 'diagram', state: '' })).querySelectorAll('.cm-legend span').length === 4
  && el(b.header(TRIAL2, Object.assign({}, ctx, { number: () => 0 }), { view: 'steps', state: '' })).querySelector('.cm-chain-no').textContent === 'an earlier chain');
check('states: loading, error, running, unfinished, unreachable - one line each', ['loading', 'error', 'running', 'unfinished', 'unreachable'].every(k => el(b.state(k)).querySelector('.cm-state.cm-state-' + k))
  && el(b.state('error')).textContent === 'The code map could not be built for this chain.' && el(b.state('running')).textContent === 'The code map is built when this chain ends.'
  && el(b.state('unfinished')).textContent === 'No code map: this chain ended without an answer.');

// the Steps grid of the field trial (chain 1): one lane, a failed attempt, two cells and the figures cell
const c1 = { titles: TRIAL.titles, built: 'end', number: ctx.number, chainId: '1' };
const st1 = el(b.steps(TRIAL, c1, null, { cells: null, inputs: null, recipe: null }));
const rows = st1.querySelectorAll('.cm-row');
check('steps: the sticky head with the three column titles and one lane per input, rotated, used in blue with its columns', st1.querySelector('.cm-steps-head .cm-col-h').textContent === 'Step'
  && st1.querySelectorAll('.cm-lanes .cm-lane').length === 1 && st1.querySelector('.cm-lane.used .rot .name').textContent === 'field_trial.csv' && st1.querySelector('.cm-lane .sub').textContent === TRIAL.inputs[0].cols
  && st1.querySelector('.cm-lane').getAttribute('title').includes('Uses: ') && st1.querySelector('.cm-steps').getAttribute('style') === 'min-width: ' + (70 + 34 + 340 + 270) + 'px', st1.querySelector('.cm-steps-head').outerHTML);
check('steps: the rows in order - cell 1, the rolled-back turn 3, cell 2, the figures cell; a failed row carries the error and the purpose; a step row its label, turn, purpose, chips and lanes',
  rows.map(r => r.className).join('|') === 'cm-row step|cm-row failed|cm-row step|cm-row step' && rows[0].querySelector('.cm-cell-no').textContent === 'Cell 1' && rows[0].querySelector('.cm-cell .sub').textContent === 'turn 1'
  && rows[1].querySelector('.cm-cell-no.fail').textContent === 'Turn 3' && rows[1].querySelector('.cm-failed-text .err').textContent === "KeyError: 'Column not found: yield'" && rows[1].querySelector('.cm-failed-text').textContent.startsWith('Rolled back · ')
  && rows[2].querySelector('.cm-purpose').getAttribute('data-act') === 'pick-s' && rows[2].querySelector('.cm-purpose').getAttribute('data-cell') === '2'
  && rows[2].querySelectorAll('.cm-chips .cm-chip').map(c => c.textContent).join() === 'filter,group,bootstrap,RESULT' && rows[2].querySelector('.cm-chip.method').textContent === 'bootstrap' && rows[2].querySelector('.cm-chip.result').textContent === 'RESULT'
  && rows[2].querySelector('.cm-dots .cm-dot.read') && rows[3].querySelector('.cm-cell-no').textContent === 'Fig 3' && rows[3].querySelector('.cm-cell .sub').textContent === 'after report' && rows[3].querySelector('.cm-dot.via'),
  rows.map(r => r.outerHTML.slice(0, 200)));
check('steps: what came out - a recorded result chip with the estimate, interval and short label; a note for a cell with no result; one chip per figure of the figures cell with its caption',
  rows[2].querySelector('.cm-res.recorded[data-act="pick-r"][data-id="r1"] .est').textContent === '+0.57' && rows[2].querySelector('.cm-res .iv').textContent === ' (0.38 to 0.76)' && rows[2].querySelector('.cm-res .short').textContent === TRIAL.results.r1.short
  && rows[0].querySelector('.cm-out .cm-note').textContent === 'Printed only: not used later or cited by the report'
  && rows[3].querySelectorAll('.cm-res.figure').map(f => f.querySelector('.est').textContent + '|' + f.getAttribute('data-id')).join() === 'figure 1|fig3.1,figure 2|fig3.2', rows[3].querySelector('.cm-out').innerHTML);
check('steps: a selected result lights its recipe\'s rows and fades the rest; a selected step marks its row',
  el(b.steps(TRIAL, c1, { t: 'r', id: 'r1' }, { cells: [2], inputs: ['field_trial.csv'], recipe: TRIAL.recipes.r1 })).querySelectorAll('.cm-row').map(r => r.className).join('|') === 'cm-row step faded|cm-row failed faded|cm-row step marked|cm-row step faded'
  && el(b.steps(TRIAL, c1, { t: 's', id: 2 }, { cells: [2], inputs: null, recipe: null })).querySelectorAll('.cm-row')[2].className === 'cm-row step marked');
// the chips of a replaced, an empty and a cited printout
const T4c = { titles: T4.titles, built: 'end', number: () => 4, chainId: '4' };
const replaced = el(b.resultChip(Object.values(T4.results).find(r => r.status === 'corrected'), false, T4c)), empty = el(b.resultChip({ id: 'r9', status: 'not computed', estimate: 'nan', interval: '', short: 'x', label: 'x', cell: 3 }, true, T4c));
const printed = el(b.resultChip(TRIAL2.results.p4, false, ctx));
check('result chips by status: replaced (struck, "replaced by cell n"), came out empty (fail colour, pressed), a cited printout (dashed, "printed")',
  replaced.querySelector('.cm-res.replaced .short').textContent.startsWith('replaced by cell ') && empty.querySelector('.cm-res.empty.on').getAttribute('aria-pressed') === 'true'
  && printed.querySelector('.cm-res.printed .est').textContent === 'printed' && printed.querySelector('.cm-res').getAttribute('title').startsWith('Printed in cell 4, and the report cites it'), [replaced.innerHTML, printed.innerHTML]);
// the follow-up's lanes: the chain lane first, a button that opens chain 1; the primary reached through it
const st2 = el(b.steps(TRIAL2, ctx, null, { cells: null, inputs: null, recipe: null }));
check('a follow-up: the "From chain 1" lane is a button that opens that chain, named by the navigator\'s number; the dataset lane says "through chain 1"',
  st2.querySelector('.cm-lanes button.cm-lane.chain[data-act="open-chain"][data-chain="1"] .name').textContent === 'From chain 1' && st2.querySelector('.cm-lane.chain .sub').textContent === 'adj_diff, plot_means'
  && st2.querySelectorAll('.cm-lane')[1].querySelector('.sub').textContent === 'through chain 1' && st2.querySelector('.cm-lane.chain').getAttribute('title').includes('Opens chain 1\'s map'), st2.querySelector('.cm-lanes').innerHTML);
check('a chain lane for a chain the navigator does not hold reads "From an earlier chain"',
  el(b.laneHead(TRIAL2.inputs[0], Object.assign({}, ctx, { number: () => 0 }), false)).querySelector('.name').textContent === 'From an earlier chain');
check('no inputs: the lanes column carries the one line instead', el(b.steps(Object.assign({}, TRIAL, { inputs: [] }), c1, null, { cells: null, inputs: null, recipe: null })).querySelector('.cm-nolane.head').textContent === 'No data attached: the numbers are made in the code');
check('a cell that did not parse: its row says so in the "what came out" column', el(b.row(TRIAL, Object.assign({}, TRIAL.rows[0], { mapped: false }), c1, null, { cells: null, inputs: null, recipe: null })).querySelector('.cm-note').textContent === 'Not mapped: the code could not be read');

// the recipe diagram, laid out with the harness's dagre stand-in
const dg = el(b.diagram(TRIAL, c1, 'r1'));
check('diagram: the picker lists every result and figure with its label, the chosen one selected; the hint',
  dg.querySelectorAll('#cmDiagPick option').map(o => o.getAttribute('value')).join() === Object.keys(TRIAL.diagrams).join() && dg.querySelector('option[value="r1"]').hasAttribute('selected')
  && dg.querySelector('option[value="r1"]').textContent === '+0.57 · ' + TRIAL.results.r1.short && dg.querySelector('option[value="fig3.1"]').textContent.startsWith('Figure 1 of 2, cell 3 · ')
  && dg.querySelector('.cm-diag-head .hint').textContent.startsWith('Read it top to bottom'), dg.querySelector('.cm-diag-head').innerHTML);
const nodes = dg.querySelectorAll('.cm-node');
check('diagram: one positioned box per node - the input in blue, tables and estimates with their names and first steps, the result with the number and "RESULT · cell n" - and one SVG path per edge with the arrow marker',
  nodes.length === TRIAL.diagrams.r1.nodes.length && nodes.every(n => /^left: \d+px; top: \d+px; width: \d+px; height: \d+px$/.test(n.getAttribute('style')))
  && dg.querySelector('.cm-node.in .label').textContent === 'field_trial.csv' && dg.querySelector('.cm-node.in .sub').textContent === 'data the chain was given'
  && dg.querySelector('.cm-node.result .label').textContent === '+0.57 (0.38 to 0.76)' && dg.querySelector('.cm-node.result .names').textContent === 'RESULT · cell 2' && dg.querySelector('.cm-node.result').getAttribute('data-act') === 'pick-r'
  && dg.querySelectorAll('.cm-node.estimate').length === 3 && dg.querySelector('.cm-node.table[data-act="pick-s"][data-cell="2"] .names').textContent === 'plot_means · cell 2'
  && dg.querySelectorAll('svg.cm-edges path').length === TRIAL.diagrams.r1.edges.length + 1 && dg.querySelector('marker#cm-arrow'), dg.querySelector('.cm-diag').innerHTML.slice(0, 600));   // + the marker's own path
const lay = w.CodeMapUI.layout(TRIAL.diagrams.r1);
check('layout: the input sits on the top row, the result at the bottom, every box inside the drawing; a diagram without edges still lays out',
  lay.nodes.find(n => n.kind === 'input').y === 0 && lay.nodes.find(n => n.kind === 'result').y === Math.max(...lay.nodes.map(n => n.y)) && lay.nodes.every(n => n.x >= 0 && n.y >= 0 && n.x + n.w <= lay.w && n.y + n.h <= lay.h)
  && w.CodeMapUI.layout({ nodes: [{ id: 'a', kind: 'table', label: 'a', cell: 1 }], edges: [] }).nodes.length === 1, lay);
const dg2 = el(b.diagram(TRIAL2, ctx, 'p4'));
check('diagram of a printout: the chain input "From chain 1" opens that chain; the result box says "PRINTED · cell 4"',
  dg2.querySelector('.cm-node.in.chain[data-act="open-chain"][data-chain="1"] .label').textContent === 'From chain 1' && dg2.querySelector('.cm-node.in.chain .sub').textContent === 'what chain 1 made'
  && dg2.querySelector('.cm-node.result .names').textContent === 'PRINTED · cell 4', dg2.innerHTML.slice(0, 400));
check('a chain with no recipe to draw: the one line, naming the printed cell', el(b.diagram(Object.assign({}, TRIAL2, { diagrams: {} }), ctx, null)).querySelector('.cm-nocode').textContent === 'Nothing to draw: this chain recorded no RESULT line and drew no figure, so no number has a recipe. Its answer is only printed, in cell 4; the Steps view shows that step.');

// the panel: the summary, a result, a printout, a figure, a step
const sm = el(b.summary(TRIAL, c1));
check('panel, nothing selected: how to read it, the data used with the columns, nothing flagged, the six counts',
  sm.querySelectorAll('.cm-h').map(h => h.textContent).join('|') === 'How to read it|Data this chain used|Worth checking|In numbers' && sm.querySelector('.cm-used .in').textContent === 'field_trial.csv'
  && sm.querySelector('.cm-used').textContent === 'field_trial.csv · 4 of 6 columns: ' + TRIAL.inputs[0].used_columns.join(', ') && sm.querySelector('.cm-checks') === null && sm.textContent.includes('Nothing flagged')
  && sm.querySelectorAll('.cm-counts div').map(d => d.querySelector('b').textContent + ' ' + d.querySelector('span').textContent).join('|') === '3 steps|1 failed attempts|1 of 1 inputs used|1 results recorded|0 replaced|0 came out empty', sm.innerHTML);
const sm4 = el(b.summary(T4, { titles: T4.titles, built: 'end', number: id => ({ '1': 1, '3': 3, '4': 4 })[id] || 0, chainId: '4' }));
check('panel, the branching chain: the checks as buttons - a citation into chain 3 opens it at the cell, reliance opens it, a typed value picks its step, a replaced result picks the first - each with chain tokens as links',
  sm4.querySelector('.cm-check.cites[data-act="open-chain"][data-chain="3"][data-cell="5"] a.cm-chain').textContent === 'chain 3' && sm4.querySelector('.cm-check.chain[data-act="open-chain"][data-chain="3"]')
  && sm4.querySelector('.cm-check.typed[data-act="pick-s"][data-cell="14"]') && sm4.querySelector('.cm-check.corrected[data-act="pick-r"]') && sm4.querySelector('.cm-used .in').textContent === 'From chain 3', sm4.querySelector('.cm-checks').innerHTML.slice(0, 500));
const rp = el(b.result(TRIAL, c1, 'r1'));
check('panel, a result: the kicker with the cell, the number, the interval and unit, the label, "recorded", the line that the map does not judge it, Made from, the items in order with names, sizes and glossed steps, the final line, the choices, the cells it rests on, Open in the notebook',
  rp.querySelector('.cm-kicker span').textContent === 'How this number was made · cell 2' && rp.querySelector('.cm-big').textContent === '+0.57' && rp.querySelector('.cm-iv').textContent === '95% CI 0.38 to 0.76 · t/ha, B higher'
  && rp.querySelector('.cm-status.recorded').textContent === 'recorded' && rp.querySelector('.cm-hownot').textContent === 'The map shows how this number was made, not whether it is right.'
  && rp.querySelector('.cm-chips-row .cm-in').textContent === 'field_trial.csv' && rp.querySelectorAll('.cm-item:not(.final)').length === TRIAL.recipes.r1.items.length
  && rp.querySelector('.cm-item .cm-item-label[data-act="pick-s"][data-cell="2"]').textContent === TRIAL.recipes.r1.items[0].label && rp.querySelector('.cm-item .cm-names').textContent === 'plot_means · cell 2 · ' + TRIAL.recipes.r1.items[0].shape
  && rp.querySelector('.cm-item .cm-gloss') && rp.querySelector('.cm-item.final .cm-final').textContent === 'RESULT +0.57 (0.38 to 0.76)'
  && rp.querySelectorAll('.cm-chips-row .cm-chip').map(c => c.textContent).join() === 'random seed 7,500 resamples' && rp.querySelector('.cm-foot span').textContent === 'Rests on cell 2'
  && rp.querySelector('.cm-foot button[data-act="open-nb"][data-cell="2"]').textContent === 'Open in the notebook', rp.innerHTML);
const pp = el(b.result(TRIAL2, ctx, 'p4'));
check('panel, a printout: its printed lines, "printed only", no judging line, Made from "From chain 1" as a link',
  pp.querySelector('.cm-kicker span').textContent === 'How this printout was made · cell 4' && pp.querySelector('.cm-big.printed').textContent === TRIAL2.results.p4.lines.join('\n') && pp.querySelector('.cm-status.printed').textContent === 'printed only'
  && !pp.querySelector('.cm-hownot') && pp.querySelector('.cm-chips-row .cm-in a.cm-chain[data-chain="1"]').textContent === 'chain 1' && pp.querySelector('.cm-item.final .cm-final').textContent === 'printed in cell 4', pp.innerHTML);
const fp = el(b.result(TRIAL, c1, 'fig3.2'));
check('panel, a figure: its name, the caption with the figures line, the "figure" status, its recipe and the cells it rests on',
  fp.querySelector('.cm-kicker span').textContent === 'How this figure was made · cell 3' && fp.querySelector('.cm-big.fig').textContent === 'Figure 2 of 2' && fp.querySelector('.cm-p').textContent.endsWith('Drawn after the report. The recipe is the data drawn; numbers written on the figure are left out.')
  && fp.querySelector('.cm-status.figure') && fp.querySelector('.cm-item.final .cm-final').textContent === 'figure 2 of 2, cell 3' && fp.querySelector('.cm-foot span').textContent === 'Rests on cells 2, 3', fp.innerHTML);
check('panel: a typed parameter is marked; a recipe not traced says so and lists nothing it was made from; sizes not recorded is said once',
  el(b.result(T4, T4c, 'r1')).querySelector('.cm-param .cm-typed') !== null
  && el(b.result(Object.assign({}, TRIAL, { recipes: Object.assign({}, TRIAL.recipes, { r1: Object.assign({}, TRIAL.recipes.r1, { traced: false }) }) }), c1, 'r1')).querySelector('.cm-note').textContent === 'Not traced: the map could not follow how this was made'
  && el(b.result(Object.assign({}, TRIAL, { sizes: false }), c1, 'r1')).querySelectorAll('.cm-note').map(n => n.textContent).join() === 'Table sizes were not recorded for this chain (an older run).');
const sp = el(b.step(TRIAL2, ctx, 4));
check('panel, a step: the cell and turn, its role, why, what it uses - the inputs and what it takes from chain 1 (a link that opens chain 1 at the cell) - what it made with sizes, what it printed with the printout link, the line count, Open in the notebook',
  sp.querySelector('.cm-kicker span').textContent === 'Step' && sp.querySelector('.cm-big.cell').textContent === 'Cell 4 · turn 1' && sp.querySelector('.cm-status.role').textContent === 'Printed what the report cites'
  && sp.querySelector('.cm-p').textContent === TRIAL2.steps['4'].why && sp.querySelector('.cm-chips-row .cm-in a.cm-chain[data-chain="1"]')
  && sp.querySelector('.cm-take.chain[data-act="open-chain"][data-chain="1"][data-cell="2"]').textContent === 'from chain 1, cell 2: adj_diff, plot_means · open chain 1\'s map'
  && sp.querySelectorAll('.cm-builds .cm-build').length === TRIAL2.steps['4'].builds.length && sp.querySelector('.cm-build .cm-names').textContent.includes(' · ')
  && sp.querySelector('.cm-take[data-act="pick-r"][data-id="p4"]').textContent === 'The report cites this printout · see how it was made' && sp.querySelector('.cm-foot span').textContent === TRIAL2.steps['4'].lines + ' lines of code'
  && sp.querySelector('.cm-foot button[data-act="open-nb"][data-cell="4"]'), sp.innerHTML);
check('panel, the figures step: named so, with its figures as links to their recipes and the results it recorded as links',
  el(b.step(TRIAL, c1, 3)).querySelector('.cm-kicker span').textContent === 'Figures step' && el(b.step(TRIAL, c1, 3)).querySelectorAll('.cm-take[data-act="pick-r"]').filter(x => x.getAttribute('data-id').startsWith('fig3')).length === 2
  && el(b.step(TRIAL, c1, 2)).querySelector('.cm-take[data-act="pick-r"][data-id="r1"]').textContent.startsWith('+0.57 (0.38 to 0.76) · '));
check('a chain with no code: the one line with its citation as a link, the summary without the reading guide or the counts',
  el(b.nocode(T5, { titles: T5.titles, built: 'now', number: id => (id === '1' ? 1 : 0), chainId: '5' })).querySelector('.cm-nocode a.cm-chain[data-chain="1"]').textContent === 'chain 1'
  && el(b.summary(T5, { titles: T5.titles, built: 'now', number: () => 1, chainId: '5' })).querySelectorAll('.cm-h').map(h => h.textContent).join('|') === 'Data this chain used|Worth checking');

// ---- the module on the mini DOM, with a scripted route ----
const route = (thread, chain, view, built) => [200, { thread_id: thread, chain_id: chain, built: built || 'end', map: view }];
answers = { '/code_map/1001/1': route('1001', '1', TRIAL), '/code_map/1001/2': route('1001', '2', TRIAL2, 'now'), '/code_map/1001/3': [200, { thread_id: '1001', chain_id: '3', state: 'running' }],
            '/code_map/1001/4': [200, { thread_id: '1001', chain_id: '4', state: 'unfinished' }], '/code_map/1001/5': [200, { thread_id: '1001', chain_id: '5', error: 'x' }] };
(async () => {
  w.CodeMapUI.open('1'); await tick(); await tick();
  const m = doc.getElementById('codeMapModal');
  check('open: the modal is made once, shown, the route called for the chain on the page\'s thread, the Steps view and the summary drawn',
    m && m.style.display === 'flex' && calls[0] === '/code_map/1001/1' && m.querySelectorAll('.cm-map .cm-row').length === 4 && m.querySelector('.cm-panel .cm-pane.summary') && m.querySelector('.cm-chain-no').textContent === 'chain 1', calls);
  m.dispatch('click', m.querySelector('.cm-res[data-id="r1"]')); await tick();
  check('click a result chip: its recipe in the panel, the other rows faded, the chip pressed', m.querySelector('.cm-panel .cm-kicker span').textContent === 'How this number was made · cell 2'
    && m.querySelectorAll('.cm-row.faded').length === 3 && m.querySelector('.cm-res[data-id="r1"]').getAttribute('aria-pressed') === 'true');
  m.dispatch('click', m.querySelector('.cm-switch button[data-view="diagram"]')); await tick();
  check('switch to the diagram: the selected result\'s recipe drawn, the picker on it, the panel kept, the legend swapped', m.querySelector('.cm-diag') && m.querySelector('#cmDiagPick option[selected]').getAttribute('value') === 'r1'
    && m.querySelector('.cm-panel .cm-kicker span').textContent === 'How this number was made · cell 2' && m.querySelectorAll('.cm-legend span').length === 4);
  const pick = m.querySelector('#cmDiagPick'); pick.value = 'fig3.1'; m.dispatch('change', pick); await tick();
  check('pick a figure in the picker: its diagram and its recipe', m.querySelector('.cm-node.result .names').textContent === 'FIGURE · cell 3' && m.querySelector('.cm-panel .cm-kicker span').textContent === 'How this figure was made · cell 3');
  m.dispatch('click', m.querySelector('.cm-node.table[data-act="pick-s"]')); await tick();
  check('click a box: its step in the panel, the diagram stays', m.querySelector('.cm-panel .cm-kicker span').textContent === 'Step' && m.querySelector('.cm-diag'));
  m.dispatch('click', m.querySelector('.cm-switch button[data-view="steps"]')); await tick();
  m.dispatch('click', m.querySelector('.cm-panel .cm-kicker .x')); await tick();
  check('back to Steps, the panel\'s × returns to the summary with no row faded', m.querySelector('.cm-panel .cm-pane.summary') && m.querySelectorAll('.cm-row.faded').length === 0);
  // the navigator moves under the open map: the map follows
  global.currentResponseIndex = 1; global.updateNavigationButtons(); await tick(); await tick();
  check('the navigator moves to chain 2: the map follows (one route call), built now, its path and lanes', calls[calls.length - 1] === '/code_map/1001/2' && m.querySelector('.cm-chain-no').textContent === 'chain 2'
    && m.querySelector('.cm-built').textContent.startsWith('built now from the chain\'s record') && m.querySelector('.cm-lane.chain .name').textContent === 'From chain 1', calls);
  const before = calls.length;
  global.updateNavigationButtons(); await tick();
  check('the navigator settling on the same chain does not reload', calls.length === before);
  // from inside the map: open chain 1 at its cell 2 through the lane
  m.dispatch('click', m.querySelector('.cm-panel .cm-check.chain') || m.querySelector('.cm-lane.chain')); await tick(); await tick();
  check('open chain 1 from inside the map: the app navigates there (navigateToChainId) and the map shows chain 1', navigated[navigated.length - 1] === '1' && m.querySelector('.cm-chain-no').textContent === 'chain 1' && global.currentResponseIndex === 0, navigated);
  global.currentResponseIndex = 1; global.updateNavigationButtons(); await tick(); await tick();
  m.dispatch('click', m.querySelector('.cm-take.chain[data-act="open-chain"][data-chain="1"][data-cell="2"]') || m.querySelector('.cm-cell-no')); await tick();
  m.dispatch('click', m.querySelector('.cm-take.chain[data-act="open-chain"][data-chain="1"][data-cell="2"]')); await tick(); await tick();
  check('a step\'s "from chain 1, cell 2" link opens chain 1 with cell 2 selected', m.querySelector('.cm-chain-no').textContent === 'chain 1' && m.querySelector('.cm-panel .cm-big.cell').textContent === 'Cell 2 · turn 4', m.querySelector('.cm-panel').innerHTML.slice(0, 200));
  // Open in the notebook: the modal closes and the notebook scrolls to the cell
  m.dispatch('click', m.querySelector('.cm-foot button[data-act="open-nb"]')); await tick();
  check('Open in the notebook: the modal closes, the cell is opened', m.style.display === 'none' && opened[opened.length - 1] === 2, opened);
  // the states
  for (const [id, kind, txt] of [['3', 'running', 'The code map is built when this chain ends.'], ['4', 'unfinished', 'No code map: this chain ended without an answer.'], ['5', 'error', 'The code map could not be built for this chain.'], ['9', 'unfinished', 'No code map: this chain ended without an answer.']]) {
    w.CodeMapUI.open(id); await tick(); await tick();
    check('state ' + kind + ' for chain ' + id + ': the line in place of the map, the panel empty', m.querySelector('.cm-map .cm-state-' + kind) && m.querySelector('.cm-map .cm-state').textContent === txt && m.querySelector('.cm-panel').innerHTML === '', m.querySelector('.cm-map').innerHTML);
  }
  check('the header × closes the modal', (m.dispatch('click', m.querySelector('.cm-head button.x[data-act="close"]')), m.style.display === 'none'));
  w.CodeMapUI.open('1'); await tick(); await tick();
  m.dispatch('click', m.querySelector('.cm-switch button[data-view="diagram"]')); await tick();
  w.CodeMapUI.close(); w.CodeMapUI.open('1'); await tick(); await tick();
  check('a fresh opening starts at the Steps view whatever was shown before', m.querySelector('.cm-map .cm-steps') && !m.querySelector('.cm-map .cm-diag'));
  w.CodeMapUI.close();
  // a chain the navigator does not hold: read straight from the server, its path's chains "an earlier chain"
  answers['/code_map/1001/7'] = route('1001', '7', Object.assign({}, TRIAL2, { chain_id: '7', id: '7', path: ['6', '7'], pathTitles: { '6': 'q6', '7': 'q7' }, titles: { '6': 'q6', '7': 'q7' } }));
  w.CodeMapUI.open('7'); await tick(); await tick();
  check('a chain outside the navigator: shown as "an earlier chain", its path step a plain mark with the question as tooltip', m.querySelector('.cm-chain-no').textContent === 'an earlier chain' && m.querySelector('.cm-path .cm-chain-earlier').getAttribute('title') === 'q6');
  w.CodeMapUI.close();
  // the closing card's button (stream-pane.js): for an answered chain with cells only
  const pane = fs.readFileSync(path.join(__dirname, '..', '..', 'web_app', 'static', 'js', 'stream-pane.js'), 'utf8');
  check('the closing card carries a Code map button with the chain id in its markup, for an answered chain that ran code, guarded for a page without the module',
    pane.includes("r.status === 'answered' && r.cells > 0 && r.chain_id") && pane.includes('<button class="sp-codemap" data-chain="') && pane.includes("if(typeof CodeMapUI!==\\'undefined\\')CodeMapUI.open(this.dataset.chain)"));
  const graph = fs.readFileSync(path.join(__dirname, '..', '..', 'web_app', 'static', 'js', 'workflowGraph.js'), 'utf8');
  check('the thread map drawer: an eye on each chain box that moves the app to the chain, closes the drawer and opens its map', graph.includes("eye.className = 'wf-node-map'") && graph.includes('window.CodeMapUI.open(resp.chain_id)') && graph.includes("drawer.style.display = 'none'"));
  const ui = fs.readFileSync(path.join(__dirname, '..', '..', 'web_app', 'static', 'js', 'ui-controls.js'), 'utf8');
  check('the navigator hands the chain on screen to the map (onChain) at the end of updateNavigationButtons', ui.includes('window.CodeMapUI.onChain(responses[currentResponseIndex] && responses[currentResponseIndex].chain_id)'));
  const css = fs.readFileSync(path.join(__dirname, '..', '..', 'web_app', 'static', 'css', 'dialogs.css'), 'utf8');
  check('the styles sit under #codeMapModal in dialogs.css, past the rail and the top bar like the thread map drawer', css.includes('#codeMapModal { display: none; position: fixed; left: 46px; top: 40px; right: 0; bottom: 0;') && css.includes('#codeMapModal .cm-lane .rot { writing-mode: vertical-rl;'));

  const failed = results.filter(r => !r[1]);
  results.forEach(r => console.log((r[1] ? '  ok   ' : '  FAIL ') + r[0] + (r[1] ? '' : '  <- ' + String(r[2] == null ? '' : (typeof r[2] === 'string' ? r[2] : JSON.stringify(r[2]))).slice(0, 700))));
  console.log(`\n${results.length - failed.length} passed, ${failed.length} failed`);
  process.exit(failed.length ? 1 : 0);
})().catch(e => { console.error(e); process.exit(1); });
