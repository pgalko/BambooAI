// The maps drawer (maps.js; 2.9, patch 0327): one way in - the left bar's button, Ctrl/Cmd+M - and the switch between
// its three maps, on the mini DOM. The page's own drawer (index.html), the Workflow level (workflow-management.js, from
// its source), the Analysis level (branch.js) over panes written by the pane's own functions (stream-pane.js), and a
// stand-in for the Pathfinding level (architect.js; its own suite holds the real one). What the switch says and how it
// greys a level; where the drawer opens; how it follows the chain on screen; the arrow keys and the focus; then the
// page's hooks, read from the sources.
// Run: node tests/analyst/test_maps.js
'use strict';
const fs = require('fs'), path = require('path');
const { makeDocument, fragment } = require(path.join(__dirname, 'minidom.js'));
const ROOT = path.join(__dirname, '..', '..', 'web_app'), JS = path.join(ROOT, 'static', 'js');
const html = fs.readFileSync(path.join(ROOT, 'templates', 'index.html'), 'utf8');
const doc = makeDocument(); global.document = doc; global.window = {};
const results = []; const check = (n, c, d) => results.push([n, !!c, d]);
const same = (a, b) => JSON.stringify(a) === JSON.stringify(b);
const $ = id => doc.getElementById(id);
const host = doc.createElement('div'); doc.body.appendChild(host);
host.innerHTML = '<button id="railMapButton"></button><div id="streamOutput"></div><div id="tabContainer"></div><div id="contentOutput"></div>' +
  '<div class="input-area"><textarea id="queryInput"></textarea><div class="icon-row"></div></div>' + fragment(html, 'workflowMapModal');      // the drawer: the page's own
doc.createElementNS = (ns, tag) => doc.createElement(tag);
global.showSystemMessage = () => {};
global.responses = []; global.currentResponseIndex = -1; global.currentData = {}; global.queryRunning = false; global.lastActiveChainId = null;
global.liveState = { running: false, index: null };
global.loadResponseContent = r => { $('streamOutput').innerHTML = r.streamOutput || ''; currentData.chain_id = r.chain_id; };
global.updateNavigationButtons = () => { window.BranchUI.onChain(responses[currentResponseIndex]); window.MapsUI.follow(); };      // as the page's own ends (ui-controls.js)
global.extractTaskFromResponse = r => ({ task: '', originalQuestion: r.queryText }); global.extractPlotDataFromResponse = () => null;
// the Pathfinding level's stand-in: what the chain on screen has, by its chain id
const steps = {}, drawn = [];
window.ArchitectUI = { mark: () => '', map: n => { const s = steps[currentData.chain_id];
  return s ? { n: s, said: s + ' steps', off: '', draw() { drawn.push('pathfinding of chain ' + n); window.WorkflowGraph.rest('the steps'); $('workflowMapContainer').innerHTML = ''; } }
           : { n: 0, said: '', off: 'Chain ' + n + ' was asked without the Architect', draw() {} }; } };
let runView = false; window.RoutinesUI = { inRunView: () => runView };
require(path.join(__dirname, '..', '..', 'tools', 'fixtures', 'dagre_stub.js')); global.dagre = window.dagre;
require(path.join(JS, 'stream-pane.js')); require(path.join(JS, 'workflowGraph.js')); require(path.join(JS, 'branch.js')); require(path.join(JS, 'maps.js'));
const wmSrc = fs.readFileSync(path.join(JS, 'workflow-management.js'), 'utf8');
global.updateSynthesisButtonState = () => {}; global.updateTrajectoryButtonState = () => {}; global.WorkflowGraph = window.WorkflowGraph;
global.workflowMap = new Function(wmSrc.slice(wmSrc.indexOf('function workflowMap() {'), wmSrc.indexOf('\nfunction updateSynthesisButtonState() {')) + '\nreturn workflowMap;')();
const w = window, M = window.MapsUI;
w.BranchUI.initialize(); M.initialize();

// a thread of three chains: one that cannot be gone on from, an analysis of three turns, and one of two with a brief of four steps
function paneOf(chain, turns, goesOn) {
  $('streamOutput').innerHTML = '';
  w.paneIds({ thread_id: 7, chain_id: chain, df_id: 'd1' });
  w.paneRunStart({ mode: 'Deep', of: 8, dollars: 1.5 });
  turns.forEach((kind, i) => {
    w.paneTurnStart({ turn: i + 1, of: 8, seat: 'Analyst', model: 'm', chain_id: chain });
    w.paneTurnEnd({ turn: i + 1, kind, thinking: 'The plots are in. This turn takes step ' + (i + 1) + '.', note: '', code: kind === 'cell' ? 'x = 1' : '', elapsed: 2, cost: 0.01 });
    if (kind === 'cell') w.paneCell({ cell_no: i + 1, ok: true, peek: 'rows 720', elapsed: 0.1, chars: 10 });
  });
  w.paneRunEnd({ status: 'answered', turns: turns.length, of: 8, cells: 1, cost: 0.1, seconds: 3, chain_id: chain, turn_map: goesOn });
  return $('streamOutput').innerHTML;
}
const entry = (chain, parent, question, turns, goesOn) => ({ chain_id: chain, thread_id: 7, parentChainId: parent, queryText: question, streamOutput: paneOf(chain, turns, goesOn), taskContents: {} });
const one = entry(10, null, 'What is in the data?', ['report'], false), two = entry(20, 10, 'Does regime B out-yield A?', ['cell', 'cell', 'report'], true),
      three = entry(30, 20, 'Is regime C worth its cost?', ['cell', 'report'], true);
steps[30] = 4;
const show = e => { currentResponseIndex = responses.indexOf(e); loadResponseContent(e); updateNavigationButtons(); };

const drawer = $('workflowMapModal'), bar0 = $('mapLevels'), rail = $('railMapButton'), composer = $('queryInput');
const level = key => bar0.querySelector('[data-level="' + key + '"]'), press = key => bar0.dispatch('click', level(key));
// the switch as the person sees it: each level with its number, * the one in use, - one that cannot be shown; the chain named between them
const bar = () => bar0.elements.map(x => (x.classList.contains('map-of-chain') ? x.elements : [x]).map(y => y.textContent + (y.getAttribute('aria-pressed') === 'true' ? '*' : '') + (y.getAttribute('aria-disabled') ? '-' : '')).join(' | ')).join(' / ');
const focus = () => { const on = doc.activeElement; return on === doc.body ? 'body' : on.id || 'level ' + on.getAttribute('data-level'); };
const now = () => [drawer.style.display || 'none', drawer.getAttribute('data-level'), bar(), focus()];
const boxes = () => $('workflowMapContainer').querySelectorAll('.wf-node').length;
const key = (k, more) => doc.dispatch('keydown', doc.activeElement, Object.assign({ key: k, ctrlKey: false, metaKey: false, altKey: false, shiftKey: false }, more || {}));

// ---- a new thread
drawer.style.display = 'none';
composer.focus();
rail.dispatch('click');
const empty = now(), emptyMap = $('workflowMapContainer').textContent, emptyFoot = $('nodeTaskContent').innerHTML;
rail.dispatch('click');
const emptyShut = now();
check('a new thread: the left bar\'s button opens the drawer on the Workflow map, the switch Workflow alone and saying there are no chains yet - no chain to name, no level of one; the '
  + 'level in use has the focus. The button again shuts the drawer, and the focus is back where it was',
  same(empty, ['flex', 'workflow', 'Workflow* / no chains yet', 'level workflow']) && emptyMap === 'No workflow data to display.' && emptyFoot === '' && same(emptyShut, ['none', 'workflow', 'Workflow* / no chains yet', 'queryInput']),
  [empty, emptyMap, emptyFoot, emptyShut]);

// ---- the switch
responses.push(one, two, three); show(two);
rail.dispatch('click');
const opened = now(), marks = bar0.elements.map(e => e.tag + '.' + e.className).join(' '), group = bar0.querySelector('.map-of-chain').elements.map(e => e.getAttribute('data-level')).join();
const says = ['workflow', 'pathfinding', 'analysis'].map(k => level(k).getAttribute('title')), kinds = ['workflow', 'pathfinding', 'analysis'].map(k => level(k).getAttribute('type') + '/' + level(k).tag);
const numbers = ['workflow', 'pathfinding', 'analysis'].map(k => (level(k).querySelector('.n') || { textContent: null }).textContent);
check('the switch (0327): Workflow, with how many chains; the chain on screen, by its place in the thread; then that chain\'s two levels as one control, Pathfinding and Analysis, each with how '
  + 'many boxes its map has. The level in use is pressed. A level that cannot be shown is greyed - marked so for a reader, with no number - and says why under the pointer; the others '
  + 'say what their map holds. Each is a button',
  same(opened, ['flex', 'workflow', 'Workflow3* / Chain 2 / Pathfinding- | Analysis3', 'level workflow']) && marks === 'button.map-level span.map-chain span.map-of-chain' && group === 'pathfinding,analysis'
  && same(says, ['3 chains', 'Chain 2 was asked without the Architect', '3 turns']) && same(kinds, ['button/button', 'button/button', 'button/button']) && same(numbers, ['3', null, '3'])
  && level('pathfinding').getAttribute('aria-disabled') === 'true' && !level('pathfinding').hasAttribute('aria-pressed') && level('analysis').getAttribute('aria-pressed') === 'false' && boxes() === 3,
  [opened, marks, group, says, kinds, numbers, boxes()]);

// ---- from level to level
press('analysis');
const onAnalysis = now().concat(boxes(), $('nodeTaskContent').textContent);
press('pathfinding');                                             // greyed: nothing
const greyed = now();
press('workflow');
const onWorkflow = now();
check('a level pressed is the one the drawer shows: its map, its words in the foot, the level lit - and the focus, which was on the switch, is on it. A greyed level pressed does nothing',
  same(onAnalysis, ['flex', 'analysis', 'Workflow3 / Chain 2 / Pathfinding- | Analysis3*', 'level analysis', 3, 'Click a turn to go back to it. Hover over one to see what it did.'])
  && same(greyed.slice(0, 3), onAnalysis.slice(0, 3)) && same(onWorkflow.slice(0, 3), ['flex', 'workflow', 'Workflow3* / Chain 2 / Pathfinding- | Analysis3']), [onAnalysis, greyed, onWorkflow]);

// ---- the arrow keys
level('workflow').focus();
const right1 = [key('ArrowRight').defaulted, now()];
const right2 = [key('ArrowRight').defaulted, now()];
key('ArrowLeft');
const left1 = now();
doc.activeElement.blur();                                         // the focus nowhere: a box of the map was clicked
key('ArrowLeft');
const fromBody = now();
composer.focus();                                                 // typing: the keys are the caret's
const typing = [key('ArrowRight').defaulted, now()];
level('workflow').focus();
const withKey = [key('ArrowRight', { ctrlKey: true }).defaulted, key('ArrowRight', { shiftKey: true }).defaulted, key('ArrowRight', { altKey: true }).defaulted, key('ArrowRight', { metaKey: true }).defaulted, key('ArrowUp').defaulted, now()[1]];
show(three);
const round = [];
for (let i = 0; i < 4; i++) { key('ArrowRight'); round.push(now()[1]); }
for (let i = 0; i < 4; i++) { key('ArrowLeft'); round.push(now()[1]); }
check('the left and right arrow keys, while the drawer is open, go to the level after or before, round the ones that can be shown - a greyed one is passed over - and a focus that was on '
  + 'the switch goes with the level; the key is taken. They work with the focus nowhere, and not with it on something outside the drawer, where the keys are that thing\'s own; nor with '
  + 'Ctrl, Shift, Alt or Cmd held, nor any other key',
  same(right1, [true, ['flex', 'analysis', 'Workflow3 / Chain 2 / Pathfinding- | Analysis3*', 'level analysis']]) && same(right2, [true, ['flex', 'workflow', 'Workflow3* / Chain 2 / Pathfinding- | Analysis3', 'level workflow']])
  && same(left1, ['flex', 'analysis', 'Workflow3 / Chain 2 / Pathfinding- | Analysis3*', 'level analysis']) && same(fromBody, ['flex', 'workflow', 'Workflow3* / Chain 2 / Pathfinding- | Analysis3', 'body'])
  && same(typing, [undefined, ['flex', 'workflow', 'Workflow3* / Chain 2 / Pathfinding- | Analysis3', 'queryInput']]) && same(withKey, [undefined, undefined, undefined, undefined, undefined, 'workflow'])
  && same(round, ['pathfinding', 'analysis', 'workflow', 'pathfinding', 'workflow', 'analysis', 'pathfinding', 'workflow']), [right1, right2, left1, fromBody, typing, withKey, round]);

// ---- where the drawer opens, and how it follows the chain on screen
press('pathfinding');
const onSteps = now().concat(drawn.slice(-1)[0], $('nodeTaskContent').textContent);
composer.focus();
key('m', { ctrlKey: true });
const shutByKey = now();
const cmd = key('m', { metaKey: true });
const reopened = [cmd.defaulted].concat(now());
const plain = [key('m').defaulted, now()[0]];                     // the letter alone: nothing
show(two);                                                        // a chain with no brief comes on screen
const followed = now();
show(three);                                                      // and the one with a brief again: the drawer is where it went
const stays = now();
press('analysis'); show(two);
const sameLevel = now().concat(boxes());
show(one);                                                        // a chain with no turns to go back to
const noTurns = now().concat(level('analysis').getAttribute('title'));
M.shut();
check('the drawer opens where it was left - Ctrl+M and Cmd+M open and shut it as the button does, and take the key; the letter alone does nothing. It follows the chain on screen: on a '
  + 'level the chain now on screen has, it shows that chain\'s map; on one it has not, it goes to the Workflow map and stays there, the switch saying why the level cannot be shown',
  same(onSteps, ['flex', 'pathfinding', 'Workflow3 / Chain 3 / Pathfinding4* | Analysis2', 'level pathfinding', 'pathfinding of chain 3', 'the steps'])
  && same(shutByKey, ['none', 'pathfinding', 'Workflow3 / Chain 3 / Pathfinding4* | Analysis2', 'queryInput'])
  && same(reopened, [true, 'flex', 'pathfinding', 'Workflow3 / Chain 3 / Pathfinding4* | Analysis2', 'level pathfinding']) && same(plain, [undefined, 'flex'])
  && same(followed.slice(0, 3), ['flex', 'workflow', 'Workflow3* / Chain 2 / Pathfinding- | Analysis3']) && same(stays.slice(0, 3), ['flex', 'workflow', 'Workflow3* / Chain 3 / Pathfinding4 | Analysis2'])
  && same(sameLevel.slice(0, 3).concat(sameLevel[4]), ['flex', 'analysis', 'Workflow3 / Chain 2 / Pathfinding- | Analysis3*', 3])
  && same(noTurns.slice(0, 3).concat(noTurns[4]), ['flex', 'workflow', 'Workflow3* / Chain 1 / Pathfinding- | Analysis-', 'Chain 1 has no turns to go back to']),
  [onSteps, shutByKey, reopened, plain, followed, stays, sameLevel, noTurns]);

// ---- a chain's box clicked; a run; a routine's run on screen; the drawer shut
show(two); composer.focus(); rail.dispatch('click');
$('workflowMapContainer').querySelectorAll('.wf-node')[2].dispatch('click');
const boxClicked = now().slice(0, 3).concat(responses[currentResponseIndex] === three);
press('analysis');
queryRunning = true; updateNavigationButtons();
const running = now().slice(0, 3).concat(level('analysis').getAttribute('title'));
queryRunning = false; updateNavigationButtons();
const ended = now().slice(0, 3);
press('analysis');
runView = true; M.follow();                                       // a routine's run comes on screen: no chain is
const inRun = now().slice(0, 3);
runView = false; M.follow();
const outOfRun = now().slice(0, 3);
show(three); press('pathfinding'); level('pathfinding').focus(); M.shut();
const back = focus(), draws = drawn.length, barShut = bar(); show(two); show(three);      // shut: nothing is drawn, whatever comes on screen
doc.activeElement.blur();
const shutKey = key('ArrowRight').defaulted;                      // and the arrow keys are the page's own
const whileShut = [drawn.length - draws, bar() === barShut, shutKey, drawer.style.display, drawer.getAttribute('data-level')];
rail.dispatch('click'); rail.focus(); M.shut();                   // shut with the focus on something outside it: the focus stays there
const keeps = focus();
check('a chain\'s box clicked on the Workflow map brings that chain on screen and leaves the drawer open, the switch naming it. A run beginning greys the Analysis level, which says so, and '
  + 'the drawer goes to the Workflow map; when the run ends the level can be shown again. With a routine\'s run on screen no chain is: the switch is Workflow alone. Shut, the drawer '
  + 'draws nothing as chains come on screen and takes no key, and the focus it held goes back where it was - a focus that had left the drawer stays where it went',
  same(boxClicked, ['flex', 'workflow', 'Workflow3* / Chain 3 / Pathfinding4 | Analysis2', true]) && same(running, ['flex', 'workflow', 'Workflow3* / Chain 3 / Pathfinding4 | Analysis-', 'An analysis is running'])
  && same(ended, ['flex', 'workflow', 'Workflow3* / Chain 3 / Pathfinding4 | Analysis2']) && same(inRun, ['flex', 'workflow', 'Workflow3*']) && same(outOfRun, ['flex', 'workflow', 'Workflow3* / Chain 3 / Pathfinding4 | Analysis2'])
  && back === 'queryInput' && same(whileShut, [0, true, undefined, 'none', 'pathfinding']) && keeps === 'railMapButton', [boxClicked, running, ended, inRun, outOfRun, back, whileShut, keeps]);

// ---- the page's hooks, from the sources
const js = n => fs.readFileSync(path.join(JS, n), 'utf8'), css = n => fs.readFileSync(path.join(JS, '..', 'css', n), 'utf8');
const own = js('maps.js'), uc = js('ui-controls.js'), wm = js('workflow-management.js'), graph = js('workflowGraph.js'), core = js('core.js'), rt = js('routines.js'), qp = js('query-processing.js'), shell = css('shell.css');
const head = fragment(html, 'workflowMapModal');
check('the page: the left bar\'s button is the maps\', with its shortcut in its tip; the drawer\'s head holds the switch\'s place and the tools, and no name of one map; the module is loaded '
  + 'with the page and started with it; nothing else opens the drawer - the button\'s click and the shortcut are the module\'s own',
  html.includes('<button id="railMapButton" class="rb" data-tip="Maps (⌘M)" aria-label="Maps">') && head.includes('<div class="map-levels" id="mapLevels" role="group" aria-label="Maps"></div>')
  && !head.includes('<h2') && !head.includes('map-drawer-icon') && !html.includes('Workflow map') && html.includes("filename='js/maps.js'") && core.includes('window.MapsUI.initialize();')
  && !uc.includes('showWorkflowMap') && !uc.includes('railMapButton') && !uc.includes("e.key === 'm'") && !uc.includes('workflow-map-option')
  && own.includes("byId('railMapButton').addEventListener('click', e => { e.stopPropagation(); toggle(); });")
  && own.includes("document.addEventListener('keydown', e => { if ((e.ctrlKey || e.metaKey) && e.key === 'm') { e.preventDefault(); toggle(); } });"));
check('the drawer follows what is on screen: the page\'s hook for a chain on screen ends on it, after the branch and the brief have taken the chain; a routine\'s run coming on screen '
  + 'tells it too; an analysis that starts shuts it, once the page has taken the request for one - a question that opens a brief does not; the cross, a click beside the drawer, the eye '
  + 'of a chain\'s box and the thread\'s report shut it through the module; a chain reached from the drawer leaves it open',
  uc.includes("    if (window.ArchitectUI) window.ArchitectUI.onChain(responses[currentResponseIndex]);\n    // the maps drawer, where open, shows the chain now on screen (maps.js)\n    if (window.MapsUI) window.MapsUI.follow();\n}")
  && rt.includes("        updateRunNav();\n        if (window.MapsUI) window.MapsUI.follow();")
  && qp.includes("    if (window.MapsUI) window.MapsUI.shut();") && qp.indexOf('window.MapsUI.shut()') > qp.indexOf('queryRunning = true;') && qp.indexOf('window.MapsUI.shut()') > qp.indexOf('window.ArchitectUI.open(query);')
  && (qp.match(/MapsUI/g) || []).length === 2 && (wm.match(/window\.MapsUI\.shut\(\);/g) || []).length === 3 && (graph.match(/window\.MapsUI\.shut\(\);/g) || []).length === 1
  && !/workflowMapModal'\)\.style\.display/.test(wm + graph) && graph.includes('return { render: render, rest: rest, toggleFullscreen: toggleFullscreen };') && !graph.includes('function head('));
check('the stylesheet: the head is one line - the switch, which takes the room left, then the tools; a level is a button of the head\'s size, the one in use lit as the mode control\'s is, '
  + 'a greyed one faint under a pointer that says no; the chain\'s two levels are one control; the chain\'s name is the part that gives way; the thread\'s buttons show on the Workflow '
  + 'map alone; the drawer is wide enough for two digits on every level',
  /#workflowMapModal\.map-drawer \{[^}]*width: 560px;/.test(shell) && shell.includes('#workflowMapModal .map-levels { flex: 1; min-width: 0; display: flex; align-items: center; gap: 8px; }')
  && /#workflowMapModal \.map-level \{[^}]*flex-shrink: 0;[^}]*height: 26px;[^}]*font-size: var\(--fs-meta\);[^}]*white-space: nowrap;/.test(shell)
  && shell.includes('#workflowMapModal .map-level[aria-pressed="true"], #workflowMapModal .map-level[aria-pressed="true"] .n { background: var(--bg-tertiary); color: var(--c-model); }')
  && shell.includes('#workflowMapModal .map-level[aria-disabled="true"] { background: none; color: var(--text-quaternary); cursor: not-allowed; }')
  && /#workflowMapModal \.map-chain \{ min-width: 0; overflow: hidden; text-overflow: ellipsis;/.test(shell) && /#workflowMapModal \.map-of-chain \{[^}]*overflow: hidden;/.test(shell)
  && shell.includes('#workflowMapModal .map-of-chain .map-level + .map-level { border-left: 1px solid var(--border-color); }')
  && shell.includes('#workflowMapModal:not([data-level="workflow"]) .map-drawer-foot { display: none; }') && !/map-drawer-(icon|name|sub)|#workflowMapModal\.(steps|turns)/.test(shell));

let fails = 0; for (const [n, ok, d] of results) { console.log((ok ? '  ok   ' : '  FAIL ') + n + (ok ? '' : '  <- ' + JSON.stringify(d === undefined ? '' : d).slice(0, 1800))); if (!ok) fails++; }
console.log(`\n${results.length - fails} passed, ${fails} failed`); process.exit(fails ? 1 : 0);
