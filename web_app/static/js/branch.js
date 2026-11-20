// branch.js - the branches of an analysis on the page (docs/BRANCH_DESIGN.md §5; 2.9, 2026-11-21).
//
// An analysis is a line of turns. Its Turn map - the thread map's own drawer and drawing (workflowGraph.js), opened
// from the strip of the left pane - shows every turn of it and of the ways it went on: a box to a turn, joined to
// the turn it follows. A click on a turn goes back to it: the chain that holds the turn comes on screen, the left
// pane ends at it, the tabs stay as they are, and the composer takes a hint. Sent, the hint starts a branch - a
// chain of its own, which keeps the turns up to that one and goes on from there another way (the server's part:
// BambooAI.pd_agent_converse with `after`). A click on a turn that ended its chain brings the chain back whole.
//
// A branch belongs to its analysis. The thread map and the arrows count analyses, and show of each the chain that
// was last on screen. A chain's entry keeps `branch`: {of: the chain whose turn it went on from, turn, hint}.
//
// The pane itself is not touched by going back: what follows the turn is hidden by a rule of this module's own, so
// nothing of the moment is kept with the chain.
//
// window.BranchUI = { initialize, openMap, onChain, hint, started, announced, heard, unstarted, notStarted, leave,
//                     analyses, place, step, items, open, turnsOf, boxes, first, members, owner, standing, WORDS }
// standing(): the turn gone back to - {chain, turn} - or null.

(function () {
    'use strict';

    const WORDS = {
        map: 'Turn map', mapHover: 'Hover over a turn to see what it did',
        mapSub: (n, branches) => n + (n === 1 ? ' turn' : ' turns') + (branches ? ' · ' + WORDS.branches(branches) : '') + ' · click one to go back to it',
        branches: n => n + (n === 1 ? ' branch' : ' branches'),
        turn: n => 'Turn ' + n, from: n => 'From turn ' + n, left: n => n + (n === 1 ? ' turn left' : ' turns left'),
        say: n => 'Say how the analysis should go on from turn ' + n,
        end: 'Back to the end', hinted: 'hint', onScreen: 'on screen', ways: n => n + ' ways',
        failed: 'failed', notRun: 'not run', aCell: n => 'cell In [' + n + ']', aFailed: 'a cell that failed', aNotRun: 'a cell that was not run',
        info: { turn: 'Turn', did: 'Did', hint: 'Hint', ways: 'Went on', printed: 'Printed' },
        busy: 'An analysis is running: wait for it, or stop it, then go back to a turn'
    };
    const ICON = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><line x1="6" y1="3" x2="6" y2="15"/>' +
        '<circle cx="18" cy="6" r="3"/><circle cx="6" cy="18" r="3"/><path d="M18 9a9 9 0 0 1-9 9"/></svg>';

    let back = null;           // the turn gone back to: {chain, turn} - the chain on screen, and the turn its left pane ends at
    let going = null;          // a branch asked for, until its run ends: {chain, of, turn, hint, question, parent, framing, announced, error}
    const shown = {};          // of each analysis, the chain last on screen - by the chain id of its first run

    const byId = id => document.getElementById(id);
    const esc = s => String(s == null ? '' : s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
    const same = (a, b) => a != null && b != null && String(a) === String(b);
    const say = text => { if (text && typeof showSystemMessage === 'function') showSystemMessage(text); };
    const holder = html => { const d = document.createElement('div'); d.innerHTML = html || ''; return d; };
    const text = el => (el ? String(el.textContent || '').replace(/\s+/g, ' ').trim() : '');
    const onScreen = () => responses[currentResponseIndex] || null;
    const busy = () => typeof queryRunning !== 'undefined' && !!queryRunning;
    const entryOf = chain => responses.find(r => r && same(r.chain_id, chain)) || null;

    // ------------------------------------------------------------ an analysis: a chain with its branches
    // the chain a turn of `entry` is a turn of its own: the turns a branch keeps are those of the chain it went on from
    function owner(entry, n) {
        for (let i = 0; i < 99 && entry && entry.branch && n <= entry.branch.turn; i++) {
            const of = entryOf(entry.branch.of);
            if (!of || of === entry) break;
            entry = of;
        }
        return entry;
    }
    // the first run of the analysis a chain is of
    function first(entry) { return owner(entry, 0); }
    function members(entry) { const f = first(entry); return responses.filter(r => r && first(r) === f); }
    // the analyses of the thread, in the order they began: of each, the chain last on screen - its newest where none was
    function analyses() {
        const firsts = [];
        responses.forEach(r => { if (r && firsts.indexOf(first(r)) < 0) firsts.push(first(r)); });
        return firsts.map(f => { const all = members(f); return all.find(m => same(m.chain_id, shown[String(f.chain_id)])) || all[all.length - 1]; });
    }
    // where the chain on screen stands among the analyses, as the arrows count them
    function place() {
        const all = analyses(), f = onScreen() ? first(onScreen()) : null;
        return { i: all.findIndex(m => first(m) === f) + 1, n: all.length };
    }
    // the chain the arrows go to: of the analysis before, or after, the one last on screen
    function step(direction) {
        const all = analyses(), to = place().i - 1 + direction;
        return all[Math.max(0, Math.min(all.length - 1, to))] || null;
    }
    // The thread map's boxes: a box to an analysis - the chain of it last on screen -, joined to the analysis it was
    // asked from, with how many branches it has. Each is a copy that says where its chain stands in the thread (`at`)
    function items() {
        const all = analyses();
        const boxOf = chain => { const e = entryOf(chain), m = e ? all.find(x => first(x) === first(e)) : null; return m ? m.chain_id : chain; };
        return all.map(m => Object.assign({}, m, { at: responses.indexOf(m), branches: members(m).length - 1,
                                                    parentChainId: first(m).parentChainId == null ? null : boxOf(first(m).parentChainId) }));
    }
    // a chain comes on screen
    function show(entry) {
        currentResponseIndex = responses.indexOf(entry);
        lastActiveChainId = entry.chain_id || null;
        loadResponseContent(entry);
        if (typeof updateNavigationButtons === 'function') updateNavigationButtons();
    }
    // a box of the thread map clicked
    function open(item) { const entry = responses[item.at]; if (entry) show(entry); }

    // ------------------------------------------------------------ the turns of a chain, read from its left pane
    // Each numbered card is a turn: its number, what it was (the card's own word), what it did (the card's line), the
    // cell it ran - or that its cell failed - and what the cell printed. A card cut off before its turn ended - the
    // run was stopped there - is no turn. Read from the markup the chain keeps
    function turnsOf(entry) {
        const stream = holder(entry.streamOutput).querySelector('.sp-stream');
        const out = []; let turn = null;
        Array.prototype.forEach.call(stream ? stream.children : [], el => {
            if (el.nodeType !== 1) return;
            if (el.classList.contains('sp-turn')) {
                const n = el.getAttribute('data-turn');
                turn = /^\d+$/.test(n || '') && !el.classList.contains('lost')
                    ? { n: Number(n), kind: text(el.querySelector('summary .kind')), peek: text(el.querySelector('summary .peek')), cell: null, failed: false, out: '' } : null;
                if (turn) out.push(turn);
            } else if (turn && el.classList.contains('sp-row')) {
                if (el.getAttribute('data-cell')) { turn.cell = Number(el.getAttribute('data-cell')); turn.out = text(el.querySelector('.out')); }
                else if (el.classList.contains('fail')) turn.failed = true;
            }
        });
        return out;
    }
    // a turn the analysis can go on from: one that did not end its chain - not the report, not a question to the person
    const can = t => !!t && t.kind !== 'report' && t.kind !== 'question';
    // what a turn did, in a word or two: for its box, and - said whole - for the drawer's foot
    const did = t => (t.kind !== 'cell' ? t.kind : t.cell != null ? 'In [' + t.cell + ']' : t.failed ? WORDS.failed : WORDS.notRun);
    const didWhole = t => (t.kind !== 'cell' ? t.kind : t.cell != null ? WORDS.aCell(t.cell) : t.failed ? WORDS.aFailed : WORDS.aNotRun);
    // The boxes of an analysis's Turn map: each chain's own turns, in order - a branch's first one joined to the turn
    // it went on from. {key, from: the key of the box it follows, entry: its chain, turn}
    function boxes(entry) {
        const out = [];
        members(entry).forEach(m => {
            const kept = m.branch ? m.branch.turn : 0;
            let before = m.branch ? m.branch.of + ':' + kept : null;
            turnsOf(m).filter(t => t.n > kept).forEach(t => { const key = m.chain_id + ':' + t.n; out.push({ key, from: before, entry: m, turn: t }); before = key; });
        });
        return out;
    }
    // the box of the turn on screen: the one gone back to; else the last of the chain's own - or, where it has none, the turn it went on from
    function boxOnScreen(all, entry) {
        const at = (chain, n) => all.findIndex(b => b.entry === chain && b.turn.n === n);
        if (back && same(back.chain, entry.chain_id)) return at(owner(entry, back.turn), back.turn);
        for (let i = all.length - 1; i >= 0; i--) if (all[i].entry === entry) return i;
        return entry.branch ? at(entryOf(entry.branch.of), entry.branch.turn) : -1;
    }

    // ------------------------------------------------------------ going back to a turn
    // The left pane ends at the turn: the cards after it, what stands under them, and the row of a hint given later
    // are out of sight. The rule is this module's, in the page's head: the pane's markup stays as the chain keeps it
    function ends(n) {
        let rule = byId('branchBack');
        if (n == null) { if (rule) rule.remove(); return; }
        if (!rule) { rule = document.createElement('style'); rule.id = 'branchBack'; (document.head || document.body).appendChild(rule); }
        const turn = '#streamOutput .sp-stream > .sp-turn[data-turn="' + n + '"]';
        rule.textContent = turn + ' ~ .sp-turn, ' + turn + ' ~ .sp-turn ~ *, ' + turn + ' ~ .sp-hint { display: none; }';
    }
    // the composer's words, kept apart from a hold's: where the composer is held (routines.js), the words wait under the hold's
    function words(input, to) { if (input.getAttribute('data-placeholder') != null) input.setAttribute('data-placeholder', to); else input.placeholder = to; }
    // The composer as the hint's: its words ask for one, and the row under it says from which turn - with how many
    // turns the analysis has left, since the turns kept count as used - in the place of the mode, the Architect's
    // switch and the files, which a branch takes from the analysis it goes on from
    function composer() {
        const input = byId('queryInput'), row = document.querySelector('.icon-row');
        let chip = byId('branchChip');
        document.body.classList.toggle('br-hint', !!back);
        if (input && back) {
            if (input.getAttribute('data-own') == null) input.setAttribute('data-own', input.getAttribute('data-placeholder') != null ? input.getAttribute('data-placeholder') : input.placeholder || '');
            words(input, WORDS.say(back.turn));
        } else if (input && input.getAttribute('data-own') != null) {
            words(input, input.getAttribute('data-own'));
            input.removeAttribute('data-own');
        }
        if (!back) { if (chip) chip.remove(); return; }
        if (!chip && row) { chip = document.createElement('span'); chip.id = 'branchChip'; chip.className = 'br-chip'; row.insertBefore(chip, row.firstElementChild); }
        const strip = byId('streamOutput') ? byId('streamOutput').querySelector('.sp-strip') : null, of = Number(strip && strip.getAttribute('data-of')) || 0;
        if (chip) chip.innerHTML = ICON + '<span>' + WORDS.from(back.turn) + (of > back.turn ? ' · ' + WORDS.left(of - back.turn) : '') + '</span>' +
            '<button type="button" title="' + WORDS.end + '" aria-label="' + WORDS.end + '" onclick="BranchUI.leave()">×</button>';
    }
    function stand(entry, n) {
        back = { chain: entry.chain_id, turn: n };
        ends(n);
        composer();
        const pane = byId('streamOutput'), input = byId('queryInput');
        if (pane) pane.scrollTop = pane.scrollHeight;
        if (input && typeof input.focus === 'function') input.focus();
    }
    // back to the end of the chain: the pane whole, the composer its own
    function leave() {
        if (!back) return;
        back = null;
        ends(null);
        composer();
        mapFollows(onScreen());
    }
    // To a turn of a chain: the chain comes on screen, and where the analysis can go on from the turn, the left pane
    // ends there and the composer takes the hint; a turn that ended the chain shows it whole
    function go(entry, n) {
        if (onScreen() !== entry) show(entry);
        if (can(turnsOf(entry).find(t => t.n === n))) stand(entry, n); else leave();
    }

    // ------------------------------------------------------------ the Turn map
    // Every turn of the analysis on screen, and of its branches, in the thread map's drawer: a box says what the turn
    // did and, under it, its number and its cell; a branch's first turn carries the mark of a hint. The way to the turn
    // on screen is lit. Under the pointer a box lights its own way and the drawer's foot says what the turn was, the
    // hint it was made under, how many ways the analysis went on from it and what its cell printed. A click goes to
    // the turn and shuts the drawer: on the chain on screen where the turn is on its way, else on the turn's own chain.
    // Not while an analysis runs: a turn of a run under way cannot be gone on from
    function openMap() {
        const entry = onScreen(), drawer = byId('workflowMapModal');
        if (!entry || !drawer || !window.WorkflowGraph) return;
        if (busy()) { say(WORDS.busy); return; }
        const all = boxes(entry), on = boxOnScreen(all, entry);
        if (!all.length) return;
        const row = (name, value) => '<div class="wf-info-row"><span>' + name + '</span><b>' + value + '</b></div>';
        drawer.classList.remove('steps');
        drawer.classList.add('turns');                          // the thread's own buttons are not this map's
        drawer.setAttribute('data-chain', first(entry).chain_id);
        drawer.querySelector('h2').textContent = WORDS.map;
        byId('mapDrawerSub').textContent = WORDS.mapSub(all.length, members(entry).length - 1);
        byId('nodeTaskContent').textContent = WORDS.mapHover;
        byId('nodePlotPreview').innerHTML = '';
        drawer.style.display = 'flex';
        window.WorkflowGraph.render(byId('workflowMapContainer'), all.map(b => ({ chain_id: b.key, parentChainId: b.from, queryText: b.turn.peek || did(b.turn) })), on, {
            sub: (item, i) => WORDS.turn(all[i].turn.n) + ' · ' + did(all[i].turn),
            tag: (item, i) => (all[i].entry.branch && all[i].turn.n === all[i].entry.branch.turn + 1 ? WORDS.hinted : ''),
            show: (item, i) => {
                const b = all[i], t = b.turn, ways = all.filter(x => x.from === b.key).length;
                byId('nodeTaskContent').textContent = t.peek || did(t);
                byId('nodePlotPreview').innerHTML = '<div class="wf-info">' + row(WORDS.info.turn, t.n + (i === on ? ' · ' + WORDS.onScreen : '')) + row(WORDS.info.did, esc(didWhole(t))) +
                    (b.entry.branch ? row(WORDS.info.hint, esc(b.entry.branch.hint)) : '') + (ways > 1 ? row(WORDS.info.ways, WORDS.ways(ways)) : '') +
                    (t.out ? '<div class="wf-info-row wf-info-conclusion"><span>' + WORDS.info.printed + '</span><b>' + esc(t.out) + '</b></div>' : '') + '</div>';
            },
            pick: (item, i) => {
                const b = all[i], here = onScreen();
                drawer.style.display = 'none';
                go(here && owner(here, b.turn.n) === b.entry ? here : b.entry, b.turn.n);
            }
        });
    }
    // The map, while its drawer is open, follows the chain on screen: drawn again - another turn may be the one on
    // screen, a branch may have been added - and shut once a chain of another analysis is on screen, or a run begins
    function mapFollows(entry) {
        const drawer = byId('workflowMapModal');
        if (!drawer || !drawer.classList.contains('turns') || drawer.style.display !== 'flex') return;
        if (entry && same(drawer.getAttribute('data-chain'), first(entry).chain_id) && !busy()) openMap();
        else drawer.style.display = 'none';
    }
    // A chain is on screen (updateNavigationButtons): it is the one its analysis shows from now on; a turn gone back to
    // on another chain is left; the strip's button says how many branches the analysis has; the map follows
    function onChain(entry) {
        if (entry) shown[String(first(entry).chain_id)] = entry.chain_id;
        if (back && !(entry && same(back.chain, entry.chain_id))) { back = null; ends(null); }
        composer();
        const pane = byId('streamOutput'), button = pane ? pane.querySelector('.sp-turnmap') : null, n = entry ? members(entry).length - 1 : 0;
        if (button) {
            const count = button.querySelector('.n');
            if (count) count.textContent = n ? String(n) : '';
            button.setAttribute('title', WORDS.map + (n ? ': ' + WORDS.branches(n) : ''));
        }
        mapFollows(entry);
    }

    // ------------------------------------------------------------ a hint sent
    // What the composer's send asks first (handleQuerySubmit): with a turn gone back to, what is typed is a hint, and
    // the branch it starts is returned - the chain on screen, the turn, the chain that turn is a turn of its own, the
    // analysis's question and where it attached, and its brief where it has one. The composer is its own again.
    // null where no turn is gone back to
    function hint(typed) {
        const entry = onScreen();
        if (!back || !entry || !same(back.chain, entry.chain_id)) return null;
        const brief = document.querySelector('#content-brief .ar-brief');
        let framing = null;
        try { framing = brief ? JSON.parse(brief.getAttribute('data-framing') || 'null') : null; } catch (e) { framing = null; }
        going = { chain: entry.chain_id, of: owner(entry, back.turn).chain_id, turn: back.turn, hint: typed, question: entry.queryText,
                  parent: entry.parentChainId == null ? null : entry.parentChainId, framing, announced: false, error: '' };
        back = null; ends(null); composer();
        return going;
    }
    // the branch's run has begun on the page (beginLiveChain): its chain is its analysis's from the first moment, and
    // attaches where the analysis did
    function started(branch) {
        const live = typeof liveState !== 'undefined' && liveState.index != null ? responses[liveState.index] : null;
        if (!live) return;
        live.branch = { of: branch.of, turn: branch.turn, hint: branch.hint };
        live.parentChainId = branch.parent;
        liveState.parent = branch.parent;
        if (typeof updateNavigationButtons === 'function') updateNavigationButtons();
    }
    // The server announces the branch's chain (the `id` message names the chain it goes on from): the branch is
    // started. A framed analysis's branch runs under the same brief: the framing folds above the run and the Brief
    // tab stands, read - what the report says against the brief goes there
    function announced(d) {
        if (!going || d.branch_of == null) return;
        going.announced = true;
        if (going.framing && window.ArchitectUI) window.ArchitectUI.started({ framing: going.framing, chain_id: d.chain_id, thread_id: d.thread_id, queryText: going.question });
    }
    // an error the server sent: where it announced no branch, this is why
    function heard(error) { if (going) going.error = String(error || ''); }
    // whether a branch was asked for and the server did not start it
    function unstarted() { return !!going && !going.announced; }
    // The server started no branch - it said why, or could not be reached, or the account's limit stood in the way:
    // the chain begun for it leaves the thread, and the chain the hint was typed on is back at its turn, with the
    // hint to send again
    function notStarted(why) {
        const b = going;
        going = null;
        if (!b || b.announced) return;
        if (typeof liveState !== 'undefined') {
            if (liveState.index != null && responses[liveState.index] && responses[liveState.index].status === 'running') responses.splice(liveState.index, 1);
            liveState.running = false; liveState.away = false; liveState.index = null; liveState.holders = null; liveState.data = null; liveState.tasks = null;
        }
        currentData.branch = null;
        const entry = entryOf(b.chain), input = byId('queryInput');
        if (entry) { show(entry); go(entry, b.turn); }
        if (input) input.value = b.hint;
        say(why || b.error);
    }

    function initialize() {
        const input = byId('queryInput');
        if (input) input.addEventListener('keydown', e => { if (e.key === 'Escape' && back) leave(); });
    }

    window.BranchUI = { initialize, openMap, onChain, hint, started, announced, heard, unstarted, notStarted, leave, analyses, place, step, items, open,
                        turnsOf, boxes, first, members, owner, standing: () => back, WORDS };
})();
