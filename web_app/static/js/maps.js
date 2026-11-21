// maps.js - the maps drawer: one way in, and the switch between its maps (2.9, 2026-11-21).
//
// A thread has three maps, each a level under the one before: Workflow - the thread's chains (workflow-management.js);
// Pathfinding - the steps that made the brief of the chain on screen (architect.js); Analysis - the turns of that
// chain's analysis (branch.js). One drawer holds them, in one drawing (workflowGraph.js). The button on the left bar
// and Ctrl/Cmd+M open it - at the level it was left at, Workflow the first time - and shut it. The switch in its
// head goes from level to level, and so do the left and right arrow keys while it is open.
//
// A level is what its module gives when asked: {n: how many boxes its map has, said: that in words, off: why it
// cannot be shown - '' where it can -, draw()}. Pathfinding and Analysis are of the chain on screen, which the switch
// names; with none on screen - a new thread, a routine's run - the switch is Workflow alone. A level that cannot be
// shown is greyed and says why under the pointer. The drawer follows what is on screen: drawn again when another
// chain comes on screen or the one there changes, and on Workflow from then on where its level cannot be shown. It
// lies over the left pane, so it shuts when an analysis starts (query-processing.js), as it does when a step or a turn
// is clicked.
//
// window.MapsUI = { initialize, toggle, shut, follow }

(function () {
    'use strict';

    const WORDS = { workflow: 'Workflow', pathfinding: 'Pathfinding', analysis: 'Analysis', chain: n => 'Chain ' + n };
    const LEVELS = ['workflow', 'pathfinding', 'analysis'];

    let at = 'workflow';       // the level the drawer was left at
    let opener = null;         // what had the focus when the drawer opened: it has it again when the drawer shuts

    const byId = id => document.getElementById(id);
    const esc = s => String(s == null ? '' : s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
    const isOpen = () => byId('workflowMapModal').style.display === 'flex';

    // The levels as they stand: Workflow, and - of the chain on screen, by its place in the thread as the arrows
    // count it - Pathfinding and Analysis
    function levels() {
        const n = window.RoutinesUI && window.RoutinesUI.inRunView() ? 0 : window.BranchUI.place().i;
        return { chain: n, workflow: workflowMap(), pathfinding: n ? window.ArchitectUI.map(n) : null, analysis: n ? window.BranchUI.map(n) : null };
    }
    // a level's button: its name and how many boxes its map has; the one in use is pressed, one that cannot be shown greyed
    function button(key, level) {
        return '<button type="button" class="map-level" data-level="' + key + '" title="' + esc(level.off || level.said) + '"' +
            (level.off ? ' aria-disabled="true">' + WORDS[key] : ' aria-pressed="' + (key === at) + '">' + WORDS[key] + (level.n ? '<span class="n">' + level.n + '</span>' : '')) + '</button>';
    }
    // The drawer as it stands: the switch, and the map of the level in use
    function draw() {
        const all = levels(), bar = byId('mapLevels'), held = bar.contains(document.activeElement);
        if (!all[at] || all[at].off) at = 'workflow';
        byId('workflowMapModal').setAttribute('data-level', at);
        bar.innerHTML = button('workflow', all.workflow) + (all.chain
            ? '<span class="map-chain">' + WORDS.chain(all.chain) + '</span><span class="map-of-chain">' + button('pathfinding', all.pathfinding) + button('analysis', all.analysis) + '</span>'
            : all.workflow.n ? '' : '<span class="map-chain">' + all.workflow.said + '</span>');
        if (held) bar.querySelector('[aria-pressed="true"]').focus();      // the switch was written again: the focus stays on it
        all[at].draw();
    }
    function open() {
        opener = document.activeElement;
        byId('workflowMapModal').style.display = 'flex';
        draw();
        byId('mapLevels').querySelector('[aria-pressed="true"]').focus();
    }
    function shut() {
        const drawer = byId('workflowMapModal'), held = drawer.contains(document.activeElement);
        drawer.style.display = 'none';
        if (held && opener) opener.focus();
        opener = null;
    }
    function toggle() { if (isOpen()) shut(); else open(); }
    function follow() { if (isOpen()) draw(); }

    // the switch clicked: to that level, where it can be shown
    function onClick(e) {
        const hit = e.target.closest('.map-level');
        if (!hit || hit.getAttribute('aria-disabled')) return;
        at = hit.getAttribute('data-level');
        draw();
    }
    // Left and right, while the drawer is open: to the level before or after, round the ones that can be shown. Not
    // with the focus on something outside the drawer: there the keys are that thing's own
    function onKey(e) {
        if ((e.key !== 'ArrowLeft' && e.key !== 'ArrowRight') || e.ctrlKey || e.metaKey || e.altKey || e.shiftKey || !isOpen()) return;
        const on = document.activeElement;
        if (on && on !== document.body && !byId('workflowMapModal').contains(on)) return;
        const all = levels(), can = LEVELS.filter(k => all[k] && !all[k].off);
        e.preventDefault();
        at = can[(can.indexOf(at) + (e.key === 'ArrowRight' ? 1 : can.length - 1)) % can.length];
        draw();
    }

    function initialize() {
        byId('mapLevels').addEventListener('click', onClick);
        byId('railMapButton').addEventListener('click', e => { e.stopPropagation(); toggle(); });
        document.addEventListener('keydown', e => { if ((e.ctrlKey || e.metaKey) && e.key === 'm') { e.preventDefault(); toggle(); } });
        document.addEventListener('keydown', onKey);
    }

    window.MapsUI = { initialize, toggle, shut, follow };
})();
