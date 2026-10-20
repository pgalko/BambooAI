// code-map.js - the code map's modal (docs/CODEMAP_DESIGN.md; 2026-10-20): how one chain got from its data to its
// numbers, drawn from the view the server built when the chain ended (analyst/codemap) and serves at
// GET /code_map/<thread_id>/<chain_id>. Two views: Steps (one row per cell, the inputs as lanes, what came out) and the
// Recipe diagram (the data, the tables and values the code made, the number); a side panel with the chain's summary, a
// result's recipe or a step's detail. The map follows the top bar's chain navigator while it is open (onChain), and
// opening another chain from inside it moves the app there. Markup is built here on the app's own grammar (ui-*);
// the rules are in dialogs.css under #codeMapModal. The map's content comes from the server (analyst/codemap/words.py);
// the modal's own words sit in WORDS below. Nothing here reaches a prompt.
//
// Ways in: the closing card's "Code map" button (stream-pane.js) and the eye on a chain's box in the Thread map drawer
// (workflowGraph.js). window.CodeMapUI = { initialize, open, close, onChain, build }.

(function () {
    'use strict';

    // ------------------------------------------------------------ the modal's own words (British spelling, as the app)
    const WORDS = {
        title: 'Code map',
        builtEnd: 'built when the chain ended, kept with it',
        builtNow: 'built now from the chain\'s record',
        views: [['steps', 'Steps'], ['diagram', 'Recipe diagram']],
        legendSteps: [['read', 'reads the data here'], ['via', 'uses it through an earlier step'], ['recorded', 'result recorded'], ['replaced', 'replaced'], ['empty', 'came out empty'], ['printed', 'cited printout']],
        legendDiagram: [['in', 'data the chain was given'], ['table', 'a table or values the code made'], ['estimate', 'a calculation'], ['result', 'the result']],
        colStep: 'Step', colWhat: 'What the step did, in the analyst\'s words', colOut: 'What came out',
        noLanes: 'No data attached: the numbers are made in the code',
        loading: 'Loading the map…',
        error: 'The code map could not be built for this chain.',
        running: 'The code map is built when this chain ends.',
        unfinished: 'No code map: this chain ended without an answer.',
        unreachable: 'The code map could not be read.',
        notMapped: 'Not mapped: the code could not be read',
        notTraced: 'Not traced: the map could not follow how this was made',
        sizes: 'Table sizes were not recorded for this chain (an older run).',
        howNot: 'The map shows how this number was made, not whether it is right.',
        howToRead: 'Each row is one step of the analysis, one cell of code, in the order it ran. The columns on the left are the data this chain was given; a dot means the step used it. Click a result to see how it was made, or a step to see what it built.',
        diagramHint: 'Read it top to bottom: the data the chain was given, the tables and values the code made from it, then the number or figure. Click a box to see its step.',
        noDiagram: 'Nothing to draw: this chain recorded no RESULT line and drew no figure, so no number has a recipe. ',
        noDiagramPrinted: 'Its answer is only printed, in cell {n}; the Steps view shows that step.',
        noDiagramSteps: 'The Steps view shows what each step did.',
        rolledBack: 'Rolled back',
        reportBand: 'The report is written here. The figures cell, the plain-language rewrite and a final review follow.',
        role: { carries: 'Carries data forward', results: 'Records results', evidence: 'Printed what the report cites', printed: 'Printed only: not used later or cited by the report', figures: 'Draws the figures' },
        note: { figures: '{n} figure{s} drawn after the report', evidence: 'Printed what the report cites', carries: 'Carried forward to {n} later step{s}', printed: 'Printed only: not used later or cited by the report' },
        tips: { 'read': 'Reads one of the files the chain was given.', 'compute': 'Makes numbers in the code; no data file is read.', 'filter': 'Keeps only the rows that match a condition.',
                'add columns': 'Adds new columns computed from the others.', 'join': 'Lines up two tables on a shared column.', 'pivot': 'Turns rows into a grid.', 'group': 'Collapses rows into one row per group.',
                'bootstrap': 'Re-draws the rows many times to see how far the number could move.', 'Spearman': 'Do the two measures rise and fall together?', 'linear regression': 'The best straight line through the points.',
                'RESULT': 'Records a number for the report.', 'figure': 'Draws a figure.', 'print': 'Prints a table or values to read.' },
        methods: ['Spearman', 'bootstrap', 'linear regression', 'Wilson interval', 'Pearson', 't-test', 'Mann-Whitney'],
        status: { recorded: 'recorded', corrected: 'replaced by cell {n}', nan: 'came out empty', printed: 'printed only', figure: 'figure' },
        panel: { summaryHow: 'How to read it', summaryData: 'Data this chain used', summaryChecks: 'Worth checking', summaryNumbers: 'In numbers',
                 nothingFlagged: 'Nothing flagged: every input was used, nothing was typed into the code, and every result was recorded.',
                 noCodeData: 'No code ran, so no data was used.', noData: 'No data attached: every number is made in the code.',
                 number: 'How this number was made', printout: 'How this printout was made', figure: 'How this figure was made', step: 'Step', figuresStep: 'Figures step',
                 madeFrom: 'Made from', nothingOutside: 'Nothing from outside: every value is made in the code.', inOrder: 'How it was made, in order',
                 copy: 'a copy, or a value read off it', params: 'Window and settings it depends on', typed: 'typed into the code, not read from the data',
                 choices: 'Choices written into the code', patterns: 'Word lists that decide what counts', restsOn: 'Rests on cell', openNb: 'Open in the notebook',
                 printedLabel: 'Printed in cell {n}, and the report cites it. It is not recorded as a RESULT line.',
                 figureLabel: 'Drawn after the report. The recipe is the data drawn; numbers written on the figure are left out.',
                 why: 'Why, in the analyst\'s words', uses: 'Uses', builds: 'Tables and numbers it made', figs: 'Figures it drew', printed: 'Printed',
                 printoutLink: 'The report cites this printout · see how it was made', results: 'Results it recorded', usedBy: 'Later steps that use it', lines: '{n} lines of code',
                 seeHow: 'see how it was made', openMap: 'open {chain}\'s map', fromChain: 'from {chain}, cell {cells}: {names}', fromCell: 'from cell {cell}: {names}',
                 colsNotNamed: 'columns not named in the code', usedThrough: 'used through {chain}', allColumns: 'all {n} columns: ', someColumns: '{u} of {n} columns: ' },
        counts: { steps: 'steps', failed: 'failed attempts', inputs: 'inputs used', recorded: 'results recorded', replaced: 'replaced', empty: 'came out empty' },
        earlier: 'an earlier chain',
        picker: 'Recipe of', pickPrinted: 'Printed, cell {n} · {short}', pickFigure: '{name}, cell {n}',
        lane: { loaded: 'loaded, not used', unused: 'not used', chainTip: 'What {chain} made and this chain reuses: {names}. Opens {chain}\'s map.', uses: 'Uses: ', notUsed: 'Not used: ', through: ', used through {chain}' },
        diagramNode: { given: 'data the chain was given', madeBy: 'what {chain} made', result: 'RESULT · cell {n}', printed: 'PRINTED · cell {n}', figure: 'FIGURE · cell {n}', opens: ': opens {chain}\'s map' },
        rowSub: { turn: 'turn {n}', afterReport: 'after report', cell: 'Cell {n}', fig: 'Fig {n}', turnFailed: 'Turn {n}', failed: 'Failed' },
        dot: { read: 'reads {name} here', via: 'uses {name} through an earlier step' },
        band: { review: 'Review after turn {n} · {v}', final: 'Review of the report · {v}', report: 'Turn {n} · report' },
        replacedBy: 'replaced by cell {n} · ',
        printedChip: 'printed', printedTip: 'Printed in cell {n}, and the report cites it. Click to see how it was made.',
        figureChip: 'figure', figureChipN: 'figure {n}', figureTip: ' Click to see how it was made.',
        figureName: 'Figure', figureOf: 'Figure {n} of {of}'
    };

    function esc(s) {
        return String(s == null ? '' : s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
    }
    function fill(t, vars) {
        return String(t).replace(/\{(\w+)\}/g, (m, k) => (vars && k in vars) ? String(vars[k]) : m);
    }
    function plural(n) { return n === 1 ? '' : 's'; }
    function list(xs) {
        return xs.length > 6 ? xs.slice(0, 5).join(', ') + ' and ' + (xs.length - 5) + ' more' : xs.join(', ');
    }
    function cap(t) {
        const s = (t || '').split(/[:;—–(]| \| /)[0].replace(/,\s*$/, '').trim();
        return s.length > 64 ? s.slice(0, 63).replace(/\s+\S*$/, '') + '…' : s;
    }
    function cut(s, n) { s = String(s || ''); return s.length > n ? s.slice(0, n - 1).replace(/\s+\S*$/, '') + '…' : s; }

    // ------------------------------------------------------------ chain references (blueprint 8.6): the navigator numbers chains
    function chainNumber(id) {
        const rs = (typeof responses !== 'undefined' && Array.isArray(responses)) ? responses : [];
        const n = 1 + rs.findIndex(r => r && String(r.chain_id) === String(id));
        return n > 0 ? n : 0;
    }
    function ctxOf(view, built) {
        const titles = (view && view.titles) || {};
        return { titles, built: built || 'end', number: chainNumber, chainId: String(st.chainId || (view ? (view.chain_id || view.id || '') : '')) };
    }
    // a reference as words: "chain n", or "an earlier chain" when the navigator does not hold it
    function chainWords(id, ctx) {
        const n = ctx.number(id);
        return n ? 'chain ' + n : WORDS.earlier;
    }
    // a reference as markup: a link that opens the chain's map (at a cell when given), or plain words with the question as the tooltip
    function chainRef(id, ctx, cell) {
        const n = ctx.number(id);
        if (!n) return '<span class="cm-chain-earlier" title="' + esc(ctx.titles[id] || '') + '">' + WORDS.earlier + '</span>';
        return '<a href="#" class="cm-chain" data-act="open-chain" data-chain="' + esc(id) + '"' + (cell ? ' data-cell="' + esc(cell) + '"' : '') + ' title="' + esc(ctx.titles[id] || '') + '">chain ' + n + '</a>';
    }
    // text from the server with its {chain:<id>} tokens rendered: as links (html) or as words (plain)
    function text(s, ctx) {
        return esc(s).replace(/\{chain:(\w+)\}/g, (m, id) => chainRef(id, ctx));
    }
    function plain(s, ctx) {
        return String(s == null ? '' : s).replace(/\{chain:(\w+)\}/g, (m, id) => chainWords(id, ctx));
    }
    const chainOfInput = i => (i && i.kind === 'chain') ? String(i.chain) : null;

    // ------------------------------------------------------------ the recipe diagram's layout (blueprint 8.8): dagre, inputs on top
    const SIZE = { input: [168, 46], result: [224, 54], box: [224, 72] };
    function sizeOf(n) { return SIZE[n.kind === 'input' ? 'input' : (n.kind === 'result' ? 'result' : 'box')]; }
    // one column, in the order given: without a layout library, or when it fails
    function column(diag) {
        const nodes = (diag && diag.nodes) || [], edges = (diag && diag.edges) || [];
        const pos = {};
        let y = 0, w = 0;
        nodes.forEach(n => { const s = sizeOf(n); pos[n.id] = { x: 0, y, w: s[0], h: s[1] }; y += s[1] + 38; w = Math.max(w, s[0]); });
        return { w, h: Math.max(0, y - 38), nodes: nodes.map(n => Object.assign({}, n, pos[n.id])), paths: edges.map(e => straight(pos[e[0]], pos[e[1]])).filter(Boolean) };
    }
    function layout(diag) {
        const D = (typeof dagre !== 'undefined') ? dagre : ((typeof window !== 'undefined' && window.dagre) ? window.dagre : null);
        const nodes = (diag && diag.nodes) || [], edges = (diag && diag.edges) || [];
        const pos = {};
        if (!D || !D.graphlib) return column(diag);
        const g = new D.graphlib.Graph();
        g.setGraph({ rankdir: 'TB', nodesep: 28, ranksep: 38, marginx: 0, marginy: 0 });
        g.setDefaultEdgeLabel(() => ({}));
        nodes.forEach(n => { const s = sizeOf(n); g.setNode(n.id, { width: s[0], height: s[1] }); });
        edges.forEach(e => { if (e[0] !== e[1]) g.setEdge(e[0], e[1], {}); });
        // a hidden root above every input, so the inputs sit on the top row whatever they feed; not drawn
        const ins = nodes.filter(n => n.kind === 'input');
        if (ins.length) { g.setNode('__root', { width: 1, height: 1 }); ins.forEach(n => g.setEdge('__root', n.id, { weight: 100 })); }
        try { D.layout(g); } catch (e) { return column(diag); }
        let minX = Infinity, minY = Infinity, maxX = 0, maxY = 0;
        nodes.forEach(n => { const v = g.node(n.id) || { x: 0, y: 0 }; const s = sizeOf(n); pos[n.id] = { x: (v.x || 0) - s[0] / 2, y: (v.y || 0) - s[1] / 2, w: s[0], h: s[1] }; minX = Math.min(minX, pos[n.id].x); minY = Math.min(minY, pos[n.id].y); });
        if (!isFinite(minX)) { minX = 0; minY = 0; }
        nodes.forEach(n => { const p = pos[n.id]; p.x = Math.round(p.x - minX); p.y = Math.round(p.y - minY); maxX = Math.max(maxX, p.x + p.w); maxY = Math.max(maxY, p.y + p.h); });
        const paths = edges.map(e => {
            if (e[0] === e[1]) return '';
            const lab = g.edge(e[0], e[1]) || {};
            const pts = (lab.points || []).map(p => ({ x: p.x - minX, y: p.y - minY }));
            if (pts.length >= 2) return 'M' + pts.map(p => p.x.toFixed(1) + ' ' + p.y.toFixed(1)).join(' L');
            return straight(pos[e[0]], pos[e[1]]);          // the harness's stand-in gives no points: centre to centre
        }).filter(Boolean);
        return { w: Math.ceil(maxX), h: Math.ceil(maxY), nodes: nodes.map(n => Object.assign({}, n, pos[n.id])), paths };
    }
    function straight(a, b) {
        if (!a || !b) return '';
        return 'M' + (a.x + a.w / 2).toFixed(1) + ' ' + (a.y + a.h).toFixed(1) + ' L' + (b.x + b.w / 2).toFixed(1) + ' ' + b.y.toFixed(1);
    }

    // ------------------------------------------------------------ builders (pure: return HTML; tests read them)
    const build = {
        shell() {
            return '<div class="ui-dlg cm-dlg" role="dialog" aria-modal="true" aria-label="Code map">' +
                '<div class="ui-dlg-h cm-head"></div>' +
                '<div class="ui-dlg-b cm-body"><div class="cm-map"></div><div class="cm-panel"></div></div></div>';
        },
        // the header: the title, the chain's number, its path, how the map was built, the facts; the title and question;
        // on the right the view switch, the close, and the legend of the view shown
        header(view, ctx, st) {
            const n = ctx.chainId ? ctx.number(ctx.chainId) : 0;
            const path = (view && view.path) || [];
            const pathHtml = path.length > 1 ? '<span class="cm-path"><span class="k">path</span>' + path.map((id, i) => {
                const here = String(id) === ctx.chainId;
                const num = ctx.number(id);
                const t = (view.pathTitles || {})[id] || ctx.titles[id] || '';
                const lab = num ? String(num) : '?';
                return (here ? '<b class="cm-path-here" title="' + esc(t) + '">' + lab + '</b>'
                    : (num ? '<a href="#" class="cm-chain" data-act="open-chain" data-chain="' + esc(id) + '" title="' + esc(t) + '">' + lab + '</a>' : '<span class="cm-chain-earlier" title="' + esc(t) + '">?</span>'))
                    + (i < path.length - 1 ? '<span class="arr">→</span>' : '');
            }).join('') + '</span>' : '';
            const meta = view && view.meta ? ' · ' + esc(view.meta) : '';
            const built = view && !st.state ? (ctx.built === 'now' ? WORDS.builtNow : WORDS.builtEnd) + meta : '';
            const q = view && view.question ? 'Question: ' + cut(view.question, 230) : '';
            const legend = view && !view.nocode && !st.state ? (st.view === 'diagram'
                ? '<div class="cm-legend">' + WORDS.legendDiagram.map(l => '<span><i class="cm-lg cm-lg-' + l[0] + '"></i>' + esc(l[1]) + '</span>').join('') + '</div>'
                : '<div class="cm-legend">' + WORDS.legendSteps.map(l => '<span><i class="cm-lg cm-lg-' + l[0] + '"></i>' + esc(l[1]) + '</span>').join('') + '</div>') : '';
            return '<div class="cm-head-l"><div class="cm-head-line"><span class="title">' + WORDS.title + '</span>' +
                (n ? '<span class="cm-chain-no">chain ' + n + '</span>' : (ctx.chainId ? '<span class="cm-chain-no">' + WORDS.earlier + '</span>' : '')) + pathHtml +
                (built ? '<span class="cm-built">' + built + '</span>' : '') + '</div>' +
                (view && view.title ? '<div class="cm-title">' + esc(view.title) + '</div>' : '') +
                (q ? '<div class="cm-question">' + esc(q) + '</div>' : '') + '</div>' +
                '<div class="cm-head-r"><div class="cm-head-tools"><div class="cm-switch" role="group" aria-label="View">' +
                WORDS.views.map(v => '<button data-act="view" data-view="' + v[0] + '" aria-pressed="' + (st.view === v[0] ? 'true' : 'false') + '"' + (view && view.nocode ? ' disabled' : '') + '>' + v[1] + '</button>').join('') +
                '</div><button class="x" data-act="close" aria-label="Close the code map">×</button></div>' + legend + '</div>';
        },
        state(kind) {
            const t = { loading: WORDS.loading, error: WORDS.error, running: WORDS.running, unfinished: WORDS.unfinished, unreachable: WORDS.unreachable }[kind] || WORDS.error;
            return '<div class="cm-state cm-state-' + esc(kind) + '">' + esc(t) + '</div>';
        },
        nocode(view, ctx) {
            return '<div class="cm-nocode">' + text(view.nocodeText || '', ctx) + '</div>';
        },
        // ---- the Steps view
        lanesWidth(view) { const n = (view.inputs || []).length; return n ? n * 34 : 112; },
        cols(view) { return '70px ' + build.lanesWidth(view) + 'px minmax(0, 1fr) 270px'; },
        laneHead(i, ctx, dim) {
            const used = i.status === 'used' || i.status === 'via';
            const sub = used ? i.cols : (i.status === 'loaded' ? WORDS.lane.loaded : WORDS.lane.unused);
            const cls = 'cm-lane' + (used ? ' used' : (i.status === 'loaded' ? ' loaded' : ' unused')) + (dim ? ' dim' : '');
            if (i.kind === 'chain') {
                const ch = chainOfInput(i);
                const tip = fill(WORDS.lane.chainTip, { chain: chainWords(ch, ctx), names: (i.names || []).join(', ') });
                return '<button class="' + cls + ' chain" data-act="open-chain" data-chain="' + esc(ch) + '" title="' + esc(tip) + '" data-lane="' + esc(i.id) + '">' +
                    '<span class="rot"><span class="name">' + esc(plain(i.name, ctx)) + '</span><span class="sub">' + esc(plain(sub, ctx)) + '</span></span></button>';
            }
            const tip = (i.file || i.name) + (i.detail ? ' (' + i.detail + ')' : '') + (i.status === 'via' ? fill(WORDS.lane.through, { chain: chainWords(i.through, ctx) }) : '') +
                ((i.used_columns || []).length ? '. ' + WORDS.lane.uses + i.used_columns.join(', ') : '') + ((i.unused_columns || []).length ? '. ' + WORDS.lane.notUsed + i.unused_columns.join(', ') : '');
            return '<div class="' + cls + '" title="' + esc(tip) + '" data-lane="' + esc(i.id) + '"><span class="rot"><span class="name">' + esc(i.name) + '</span><span class="sub">' + esc(plain(sub, ctx)) + '</span></span></div>';
        },
        dots(view, marks, laneOn, ctx) {
            const ins = view.inputs || [];
            if (!ins.length) return '<div class="cm-nolane"></div>';
            return ins.map((i, k) => {
                const m = marks ? marks[k] : '';
                const name = ctx ? plain(i.name, ctx) : i.name;
                const words = m === 'read' ? fill(WORDS.dot.read, { name }) : (m === 'via' ? fill(WORDS.dot.via, { name }) : '');
                return '<div class="cm-dot-cell' + (laneOn[k] ? '' : ' dim') + '"' + (words ? ' title="' + esc(words) + '"' : '') + '>' + (m === 'read' ? '<i class="cm-dot read"></i>' : (m === 'via' ? '<i class="cm-dot via"></i>' : '')) + '</div>';
            }).join('');
        },
        resultChip(x, on, ctx) {
            const s = x.status;
            const cls = 'cm-res ' + (s === 'printed' ? 'printed' : (s === 'not computed' ? 'empty' : (s === 'corrected' ? 'replaced' : 'recorded'))) + (on ? ' on' : '');
            const short = s === 'corrected' ? fill(WORDS.replacedBy, { n: x.corrected_by }) + x.short : x.short;
            const tip = s === 'printed' ? fill(WORDS.printedTip, { n: x.cell }) : x.label;
            return '<button class="' + cls + '" data-act="pick-r" data-id="' + esc(x.id) + '" aria-pressed="' + (on ? 'true' : 'false') + '" title="' + esc(tip) + '">' +
                '<span class="est">' + esc(s === 'printed' ? WORDS.printedChip : (x.estimate || '—')) + '</span>' + (x.interval && s !== 'printed' ? '<span class="iv"> (' + esc(x.interval) + ')</span>' : '') +
                ' <span class="short">' + esc(short) + '</span></button>';
        },
        figureChip(f, on) {
            return '<button class="cm-res figure' + (on ? ' on' : '') + '" data-act="pick-r" data-id="' + esc(f.id) + '" aria-pressed="' + (on ? 'true' : 'false') + '" title="' + esc((f.caption || build.figName(f)) + WORDS.figureTip) + '">' +
                '<span class="est">' + esc(f.of > 1 ? fill(WORDS.figureChipN, { n: f.n }) : WORDS.figureChip) + '</span> <span class="short">' + esc(cap(f.caption)) + '</span></button>';
        },
        figName(f) { return f.of > 1 ? fill(WORDS.figureOf, { n: f.n, of: f.of }) : WORDS.figureName; },
        figsOf(view, n) { const figs = view.figures || {}; return Object.keys(figs).filter(k => figs[k].cell === n); },
        chips(row) {
            return (row.chips || []).map(t => {
                const cls = WORDS.methods.indexOf(t) >= 0 ? ' method' : (t === 'RESULT' ? ' result' : '');
                return '<span class="cm-chip' + cls + '"' + (WORDS.tips[t] ? ' title="' + esc(WORDS.tips[t]) + '"' : '') + '>' + esc(t) + '</span>';
            }).join('');
        },
        row(view, r, ctx, sel, focus) {
            const cols = build.cols(view);
            const ins = view.inputs || [];
            const laneOn = ins.map(i => !focus.inputs || focus.inputs.indexOf(i.name) >= 0);
            if (r.type === 'step') {
                const s = view.steps[String(r.cell)] || {};
                const inFocus = !focus.cells || focus.cells.indexOf(r.cell) >= 0;
                const marked = (sel && sel.t === 's' && sel.id === r.cell) || (focus.recipe && focus.recipe.cells.indexOf(r.cell) >= 0);
                const resHtml = [];
                (r.results || []).forEach(rid => { const x = view.results[rid]; if (x) resHtml.push(build.resultChip(x, !!(sel && sel.t === 'r' && sel.id === rid), ctx)); });
                if (r.printout && view.results[r.printout]) resHtml.push(build.resultChip(view.results[r.printout], !!(sel && sel.t === 'r' && sel.id === r.printout), ctx));
                build.figsOf(view, r.cell).forEach(k => resHtml.push(build.figureChip(view.figures[k], !!(sel && sel.t === 'r' && sel.id === k))));
                let note = '';
                if (r.mapped === false) note = WORDS.notMapped;
                else if (!resHtml.length) {
                    const nUsed = (s.used_by || []).length;
                    const nFig = (s.builds || []).filter(b => b.kind === 'figure').length || 1;
                    if (r.figures) note = fill(WORDS.note.figures, { n: nFig, s: plural(nFig) });
                    else if (s.role === 'evidence') note = WORDS.note.evidence;
                    else if (s.role === 'carries') note = fill(WORDS.note.carries, { n: nUsed, s: plural(nUsed) });
                    else if (s.role === 'printed') note = WORDS.note.printed;
                }
                return '<div class="cm-row step' + (inFocus ? '' : ' faded') + (marked ? ' marked' : '') + '" style="grid-template-columns: ' + cols + '" data-cell="' + esc(r.cell) + '">' +
                    '<div class="cm-cell"><button class="cm-cell-no" data-act="pick-s" data-cell="' + esc(r.cell) + '" aria-label="' + (r.figures ? 'Figures cell ' : 'Cell ') + esc(r.cell) + '">' + esc(fill(r.figures ? WORDS.rowSub.fig : WORDS.rowSub.cell, { n: r.cell })) + '</button>' +
                    '<div class="sub">' + esc(r.figures ? WORDS.rowSub.afterReport : (r.turn ? fill(WORDS.rowSub.turn, { n: r.turn }) : '')) + '</div></div>' +
                    '<div class="cm-dots">' + build.dots(view, r.lanes, laneOn, ctx) + '</div>' +
                    '<div class="cm-what"><button class="cm-purpose" data-act="pick-s" data-cell="' + esc(r.cell) + '" title="' + esc(r.purpose) + '"><span>' + esc(r.purpose) + '</span></button><div class="cm-chips">' + build.chips(r) + '</div></div>' +
                    '<div class="cm-out">' + resHtml.join('') + (note ? '<span class="cm-note">' + esc(note) + '</span>' : '') + '</div></div>';
            }
            if (r.type === 'failed') {
                return '<div class="cm-row failed' + (focus.cells ? ' faded' : '') + '" style="grid-template-columns: ' + cols + '">' +
                    '<div class="cm-cell"><span class="cm-cell-no fail">' + esc(r.turn ? fill(WORDS.rowSub.turnFailed, { n: r.turn }) : WORDS.rowSub.failed) + '</span></div>' +
                    '<div class="cm-dots">' + build.dots(view, null, laneOn) + '</div>' +
                    '<div class="cm-failed-text"><span class="k">' + WORDS.rolledBack + ' · </span><span class="err">' + esc(r.error) + '</span><br><span>' + esc(r.purpose) + '</span></div></div>';
            }
            let head = '', t = r.text || '';
            if (r.type === 'review') head = fill(WORDS.band.review, { n: r.turn, v: r.verdict });
            else if (r.type === 'final') head = fill(WORDS.band.final, { v: r.verdict });
            else { head = fill(WORDS.band.report, { n: r.turn }); t = WORDS.reportBand; }
            return '<div class="cm-row band' + (focus.cells ? ' faded' : '') + '"><span class="k">' + esc(head) + '</span><span> · ' + esc(t) + '</span></div>';
        },
        steps(view, ctx, sel, focus) {
            const ins = view.inputs || [];
            const laneOn = ins.map(i => !focus.inputs || focus.inputs.indexOf(i.name) >= 0);
            const lanes = ins.length ? ins.map((i, k) => build.laneHead(i, ctx, !laneOn[k])).join('') : '<div class="cm-nolane head">' + WORDS.noLanes + '</div>';
            const minW = 70 + build.lanesWidth(view) + 340 + 270;
            return '<div class="cm-steps" style="min-width: ' + minW + 'px">' +
                '<div class="cm-steps-head" style="grid-template-columns: ' + build.cols(view) + '"><div class="cm-col-h">' + WORDS.colStep + '</div><div class="cm-lanes">' + lanes + '</div>' +
                '<div class="cm-col-h what">' + WORDS.colWhat + '</div><div class="cm-col-h out">' + WORDS.colOut + '</div></div>' +
                (view.rows || []).map(r => build.row(view, r, ctx, sel, focus)).join('') + '</div>';
        },
        // ---- the recipe diagram
        pickerLabel(view, k) {
            const figs = view.figures || {};
            if (figs[k]) return fill(WORDS.pickFigure, { name: build.figName(figs[k]), n: figs[k].cell }) + (figs[k].caption ? ' · ' + cap(figs[k].caption) : '');
            const x = view.results[k];
            if (!x) return k;
            if (x.kind === 'printed') return fill(WORDS.pickPrinted, { n: x.cell, short: x.short });
            return (x.estimate || '—') + ' · ' + x.short + (x.status === 'corrected' ? ' (replaced)' : (x.status === 'not computed' ? ' (empty)' : ''));
        },
        diagram(view, ctx, key) {
            const keys = Object.keys(view.diagrams || {});
            if (!keys.length) {
                const printedAt = (view.rows || []).filter(r => r.type === 'step' && r.role === 'evidence').map(r => r.cell);
                return '<div class="cm-nocode">' + WORDS.noDiagram + (printedAt.length ? fill(WORDS.noDiagramPrinted, { n: printedAt[printedAt.length - 1] }) : WORDS.noDiagramSteps) + '</div>';
            }
            const figs = view.figures || {};
            const lay = layout(view.diagrams[key]);
            const isFig = !!figs[key], isPr = !isFig && view.results[key] && view.results[key].kind === 'printed';
            const nodes = lay.nodes.map(n => {
                const isIn = n.kind === 'input', isRes = n.kind === 'result';
                const m = isIn ? String(n.id).match(/^in:chain:(\w+)$/) : null;
                const ch = m ? m[1] : null;
                const style = 'left: ' + n.x + 'px; top: ' + n.y + 'px; width: ' + n.w + 'px; height: ' + n.h + 'px';
                if (isIn) {
                    const tip = plain(n.label, ctx) + (ch ? fill(WORDS.diagramNode.opens, { chain: chainWords(ch, ctx) }) : '');
                    const open = ch && ctx.number(ch) ? ' data-act="open-chain" data-chain="' + esc(ch) + '"' : '';
                    return '<button class="cm-node in' + (ch ? ' chain' : '') + '" style="' + style + '" title="' + esc(tip) + '"' + open + '><span class="label">' + esc(plain(n.label, ctx)) + '</span><span class="sub">' +
                        esc(ch ? fill(WORDS.diagramNode.madeBy, { chain: chainWords(ch, ctx) }) : WORDS.diagramNode.given) + '</span></button>';
                }
                if (isRes) {
                    const names = fill(isFig ? WORDS.diagramNode.figure : (isPr ? WORDS.diagramNode.printed : WORDS.diagramNode.result), { n: n.cell });
                    return '<button class="cm-node result" style="' + style + '" data-act="pick-r" data-id="' + esc(key) + '" title="' + esc(n.label) + '"><span class="label">' + esc(n.label) + '</span><span class="names">' + esc(names) + '</span></button>';
                }
                return '<button class="cm-node ' + esc(n.kind) + '" style="' + style + '" data-act="pick-s" data-cell="' + esc(n.cell) + '" title="' + esc(plain(n.label, ctx) + (n.step ? ': ' + n.step : '')) + '">' +
                    '<span class="label">' + esc(plain(n.label, ctx)) + '</span>' + (n.names ? '<span class="names">' + esc(plain(n.names, ctx)) + ' · cell ' + esc(n.cell) + '</span>' : '') +
                    (n.step ? '<span class="step">' + esc(n.step) + '</span>' : '') + '</button>';
            }).join('');
            const svg = '<svg class="cm-edges" width="' + lay.w + '" height="' + lay.h + '" viewBox="0 0 ' + lay.w + ' ' + lay.h + '"><defs><marker id="cm-arrow" viewBox="0 0 10 7" refX="9" refY="3.5" markerWidth="8" markerHeight="6" orient="auto"><path d="M0 0 L10 3.5 L0 7 z"/></marker></defs>' +
                lay.paths.map(p => '<path d="' + p + '" marker-end="url(#cm-arrow)"/>').join('') + '</svg>';
            return '<div class="cm-diag-head"><label class="k" for="cmDiagPick">' + WORDS.picker + '</label><select id="cmDiagPick" data-act="pick-diag">' +
                keys.map(k => '<option value="' + esc(k) + '"' + (k === key ? ' selected' : '') + '>' + esc(build.pickerLabel(view, k)) + '</option>').join('') + '</select>' +
                '<span class="hint">' + WORDS.diagramHint + '</span></div>' +
                '<div class="cm-diag-wrap"><div class="cm-diag" style="width: ' + lay.w + 'px; height: ' + lay.h + 'px">' + svg + nodes + '</div></div>';
        },
        // ---- the panel
        h(t) { return '<div class="cm-h">' + esc(t) + '</div>'; },
        stepsList(steps) {
            return (steps && steps.length ? steps : [{ text: WORDS.panel.copy }]).map(s => '<div class="cm-step-text">' + esc(s.text) + '</div>' + (s.gloss ? '<div class="cm-gloss">' + esc(s.gloss) + '</div>' : '')).join('');
        },
        summary(view, ctx) {
            const ins = view.inputs || [];
            const used = ins.filter(i => i.status === 'used' || i.status === 'via');
            const usedNames = used.map(i => plain(i.name, ctx) + (i.status === 'via' ? ' (' + fill(WORDS.panel.usedThrough, { chain: chainWords(i.through, ctx) }) + ')' : ''));
            let n = { recorded: 0, replaced: 0, empty: 0 };
            Object.keys(view.results || {}).forEach(k => { const x = view.results[k]; if (x.kind === 'printed') return; if (x.status === 'corrected') n.replaced++; else if (x.status === 'not computed') n.empty++; else n.recorded++; });
            const nSteps = (view.rows || []).filter(r => r.type === 'step').length, nFailed = (view.rows || []).filter(r => r.type === 'failed').length;
            const usedLine = view.nocode ? WORDS.panel.noCodeData : (ins.length ? usedNames.length + ' of ' + ins.length + ': ' + usedNames.join(', ') + '.' : WORDS.panel.noData);
            const cols = view.nocode ? '' : used.map(i => {
                let t;
                if (i.kind === 'chain') t = list(i.names || []);
                else {
                    const u = i.used_columns || [], tot = u.length + (i.unused_columns || []).length;
                    t = !u.length ? (i.status === 'via' ? fill(WORDS.panel.usedThrough, { chain: chainWords(i.through, ctx) }) : WORDS.panel.colsNotNamed)
                        : (u.length === tot ? fill(WORDS.panel.allColumns, { n: tot }) : fill(WORDS.panel.someColumns, { u: u.length, n: tot })) + list(u);
                }
                return '<div class="cm-used"><span class="in">' + esc(plain(i.name, ctx)) + '</span> · ' + esc(t) + '</div>';
            }).join('');
            const checks = (view.checks || []).map(k => {
                const ref = k.ref || '';
                let act = '';
                if (k.kind === 'cites' && k.chain) act = 'data-act="open-chain" data-chain="' + esc(k.chain) + '" data-cell="' + esc(k.cell || '') + '"';
                else if (k.kind === 'chain' && k.chain) act = 'data-act="open-chain" data-chain="' + esc(k.chain) + '"';
                else if (/^cell\d+$/.test(ref)) act = 'data-act="pick-s" data-cell="' + esc(ref.slice(4)) + '"';
                else if (/^(r|p)\d+$/.test(ref)) act = 'data-act="pick-r" data-id="' + esc(ref) + '"';
                else if (/^i\d+$/.test(ref)) act = 'data-act="lane" data-lane="' + esc(ref) + '"';
                if ((k.kind === 'cites' || k.kind === 'chain') && k.chain && !ctx.number(k.chain)) act = '';
                return '<button class="cm-check ' + esc(k.kind) + '" ' + act + '><i></i><span>' + text(k.text, ctx) + '</span></button>';
            }).join('');
            const counts = [[nSteps, WORDS.counts.steps], [nFailed, WORDS.counts.failed], [ins.length ? usedNames.length + ' of ' + ins.length : 'none', WORDS.counts.inputs],
                            [n.recorded, WORDS.counts.recorded], [n.replaced, WORDS.counts.replaced], [n.empty, WORDS.counts.empty]];
            return '<div class="cm-pane summary">' +
                (view.nocode ? '' : '<div>' + build.h(WORDS.panel.summaryHow) + '<div class="cm-p">' + WORDS.howToRead + '</div></div>') +
                '<div>' + build.h(WORDS.panel.summaryData) + '<div class="cm-p">' + esc(usedLine) + '</div>' + cols + '</div>' +
                '<div>' + build.h(WORDS.panel.summaryChecks) + (checks ? '<div class="cm-checks">' + checks + '</div>' : '<div class="cm-p">' + WORDS.panel.nothingFlagged + '</div>') + '</div>' +
                (view.nocode ? '' : '<div>' + build.h(WORDS.panel.summaryNumbers) + '<div class="cm-counts">' + counts.map(c => '<div><b>' + esc(c[0]) + '</b><span>' + esc(c[1]) + '</span></div>').join('') + '</div></div>') +
                '</div>';
        },
        recipeItems(rec, ctx) {
            return (rec.items || []).map((it, k) => '<div class="cm-item"><span class="n">' + (k + 1) + '</span><div>' +
                '<button class="cm-item-label" data-act="pick-s" data-cell="' + esc(it.cell) + '">' + esc(plain(it.label, ctx)) + '</button>' +
                '<div class="cm-names">' + esc(plain(it.names, ctx)) + ' · cell ' + esc(it.cell) + (it.shape ? ' · ' + esc(it.shape) : '') + '</div>' + build.stepsList(it.steps) + '</div></div>').join('');
        },
        result(view, ctx, id) {
            const rec = view.recipes[id], figs = view.figures || {}, fig = figs[id] || null, res = view.results[id] || null;
            if (!rec || (!res && !fig)) return build.summary(view, ctx);
            const cell = fig ? fig.cell : res.cell;
            const isPr = !fig && res.kind === 'printed';
            const traced = rec.traced !== false;
            let head;
            if (fig) {
                head = '<div class="cm-big fig">' + esc(build.figName(fig)) + '</div><div class="cm-p">' + esc((fig.caption ? fig.caption + ' ' : '') + WORDS.panel.figureLabel) + '</div><span class="cm-status figure">' + WORDS.status.figure + '</span>';
            } else {
                const sc = res.status === 'not computed' ? 'empty' : (res.status === 'corrected' ? 'replaced' : (isPr ? 'printed' : 'recorded'));
                const stText = isPr ? WORDS.status.printed : (res.status === 'corrected' ? fill(WORDS.status.corrected, { n: res.corrected_by }) : (res.status === 'not computed' ? WORDS.status.nan : WORDS.status.recorded));
                head = '<div class="cm-big ' + sc + '">' + esc(isPr ? (res.lines && res.lines.length ? res.lines : [res.line]).join('\n') : (res.estimate || '—')) + '</div>' +
                    (!isPr && (res.interval || res.unit) ? '<div class="cm-iv">' + esc(res.interval ? '95% CI ' + res.interval + (res.unit ? ' · ' + res.unit : '') : res.unit) + '</div>' : '') +
                    '<div class="cm-p">' + esc(isPr ? fill(WORDS.panel.printedLabel, { n: res.cell }) : res.label) + '</div>' +
                    '<span class="cm-status ' + sc + '">' + esc(stText) + '</span>' + (isPr ? '' : '<div class="cm-hownot">' + WORDS.howNot + '</div>');
            }
            const final = fig ? build.figName(fig).toLowerCase() + ', cell ' + fig.cell : (isPr ? 'printed in cell ' + res.cell : 'RESULT ' + (res.estimate || '—') + (res.interval ? ' (' + res.interval + ')' : ''));
            const seen = {}; const params = [];
            (rec.params || []).forEach(p => { const k = p.name + '=' + p.value; if (seen[k]) return; seen[k] = true; params.push(p); });
            const sizes = view.sizes === false && (rec.items || []).length ? '<div class="cm-note">' + WORDS.sizes + '</div>' : '';
            return '<div class="cm-pane result"><div class="cm-kicker"><span>' + esc(fig ? WORDS.panel.figure : (isPr ? WORDS.panel.printout : WORDS.panel.number)) + ' · cell ' + esc(cell) + '</span><button class="x" data-act="clear" aria-label="Close the recipe">×</button></div>' +
                '<div>' + head + '</div>' +
                (traced ? '<div>' + build.h(WORDS.panel.madeFrom) + '<div class="cm-chips-row">' + ((rec.inputs || []).length ? rec.inputs.map(i => '<span class="cm-in">' + text(i, ctx) + '</span>').join('') : '<span class="cm-p">' + WORDS.panel.nothingOutside + '</span>') + '</div></div>'
                    : '<div class="cm-note">' + WORDS.notTraced + '</div>') +
                '<div>' + build.h(WORDS.panel.inOrder) + '<div class="cm-items">' + build.recipeItems(rec, ctx) + '<div class="cm-item final"><span class="n arrow">→</span><span class="cm-final">' + esc(final) + '</span></div></div></div>' +
                (params.length ? '<div>' + build.h(WORDS.panel.params) + params.map(p => '<div class="cm-param"><span class="v">' + esc(p.value) + '</span><span class="w">' + esc(p.name) + ' · cell ' + esc(p.cell) + '</span>' + (p.typed ? '<span class="cm-typed">' + WORDS.panel.typed + '</span>' : '') + '</div>').join('') + '</div>' : '') +
                ((rec.choices || []).length ? '<div>' + build.h(WORDS.panel.choices) + '<div class="cm-chips-row">' + rec.choices.map(c => '<span class="cm-chip">' + esc(c.text) + '</span>').join('') + '</div></div>' : '') +
                ((rec.patterns || []).length ? '<div>' + build.h(WORDS.panel.patterns) + '<div class="cm-names">' + esc(rec.patterns.map(p => p.name + ' (cell ' + p.cell + ')').join(', ')) + '</div></div>' : '') +
                '<div class="cm-foot"><span>' + esc(WORDS.panel.restsOn + ((rec.cells || []).length === 1 ? ' ' : 's ') + (rec.cells || []).join(', ')) + '</span><button class="ui-btn sm primary" data-act="open-nb" data-cell="' + esc(cell) + '">' + WORDS.panel.openNb + '</button></div>' +
                sizes + '</div>';
        },
        step(view, ctx, n) {
            const s = view.steps[String(n)];
            if (!s) return build.summary(view, ctx);
            const figs = view.figures || {};
            const isFig = s.role === 'figures';
            const takes = (s.takes_chain || []).map(t => {
                const open = ctx.number(t.chain);
                const txt = fill(WORDS.panel.fromChain, { chain: chainWords(t.chain, ctx), cells: (t.cells || []).join(', '), names: (t.names || []).join(', ') }) + (open ? ' · ' + fill(WORDS.panel.openMap, { chain: chainWords(t.chain, ctx) }) : '');
                return '<button class="cm-take chain" ' + (open ? 'data-act="open-chain" data-chain="' + esc(t.chain) + '" data-cell="' + esc((t.cells || [])[0] || '') + '"' : 'disabled') + '>' + esc(txt) + '</button>';
            }).concat((s.takes || []).map(t => '<button class="cm-take" data-act="pick-s" data-cell="' + esc(t.cell) + '">' + esc(fill(WORDS.panel.fromCell, { cell: t.cell, names: (t.names || []).join(', ') })) + '</button>')).join('');
            const inputs = (s.inputs || []).map(i => '<span class="cm-in">' + text(i, ctx) + '</span>').join('');
            const builds = (s.builds || []).filter(b => b.kind !== 'figure').map(b => '<div class="cm-build"><div class="cm-item-label static">' + esc(plain(b.label, ctx)) + '</div><div class="cm-names">' + esc(plain(b.name, ctx)) + (b.shape ? ' · ' + esc(b.shape) : '') + '</div>' + build.stepsList(b.steps) + '</div>').join('');
            const figLinks = build.figsOf(view, n).map(k => '<button class="cm-take chain" data-act="pick-r" data-id="' + esc(k) + '">' + esc(build.figName(figs[k]) + (figs[k].caption ? ' · ' + cap(figs[k].caption) : '') + ' · ' + WORDS.panel.seeHow) + '</button>').join('');
            const results = (s.results || []).map(rid => { const x = view.results[rid]; if (!x) return ''; return '<button class="cm-take ' + (x.status === 'not computed' ? 'empty' : (x.status === 'corrected' ? 'replaced' : '')) + '" data-act="pick-r" data-id="' + esc(rid) + '">' + esc((x.estimate || '—') + (x.interval ? ' (' + x.interval + ')' : '') + ' · ' + x.short) + '</button>'; }).join('');
            const used = (s.used_by || []);
            return '<div class="cm-pane step"><div class="cm-kicker"><span>' + (isFig ? WORDS.panel.figuresStep : WORDS.panel.step) + '</span><button class="x" data-act="clear" aria-label="Close the step">×</button></div>' +
                '<div><div class="cm-big cell">' + esc((isFig ? 'Figures, cell ' : 'Cell ') + s.cell + (s.turn ? ' · turn ' + s.turn : '')) + '</div><span class="cm-status role">' + esc(WORDS.role[s.role] || s.role) + '</span></div>' +
                '<div>' + build.h(WORDS.panel.why) + '<div class="cm-p">' + esc(s.why || s.purpose) + '</div></div>' +
                (inputs || takes ? '<div>' + build.h(WORDS.panel.uses) + (inputs ? '<div class="cm-chips-row">' + inputs + '</div>' : '') + takes + '</div>' : '') +
                (builds ? '<div>' + build.h(WORDS.panel.builds) + '<div class="cm-builds">' + builds + '</div></div>' : '') +
                (figLinks ? '<div>' + build.h(WORDS.panel.figs) + figLinks + '</div>' : '') +
                ((s.printed || []).length || s.printout ? '<div>' + build.h(WORDS.panel.printed) + ((s.printed || []).length ? '<div class="cm-p">' + esc(s.printed.join(' · ')) + '</div>' : '') + (s.printout ? '<button class="cm-take chain" data-act="pick-r" data-id="' + esc(s.printout) + '">' + WORDS.panel.printoutLink + '</button>' : '') + '</div>' : '') +
                (results ? '<div>' + build.h(WORDS.panel.results) + results + '</div>' : '') +
                (used.length ? '<div>' + build.h(WORDS.panel.usedBy) + '<div class="cm-p">' + esc('cell' + (used.length === 1 ? ' ' : 's ') + used.join(', ')) + '</div></div>' : '') +
                '<div class="cm-foot"><span>' + esc(fill(WORDS.panel.lines, { n: s.lines })) + '</span><button class="ui-btn sm primary" data-act="open-nb" data-cell="' + esc(s.cell) + '">' + WORDS.panel.openNb + '</button></div></div>';
        }
    };

    // the rows and lanes a selection lights: a result's recipe, or a step with what it reads and feeds
    function focusOf(view, sel) {
        if (!view || !sel) return { cells: null, inputs: null, recipe: null };
        if (sel.t === 'r') {
            const rec = view.recipes[sel.id];
            return rec ? { cells: rec.cells || [], inputs: rec.inputs || [], recipe: rec } : { cells: null, inputs: null, recipe: null };
        }
        const s = view.steps[String(sel.id)];
        return s ? { cells: [s.cell].concat(s.reads_from || [], s.used_by || []), inputs: null, recipe: null } : { cells: null, inputs: null, recipe: null };
    }

    // ------------------------------------------------------------ state and the server
    const st = { open: false, threadId: null, chainId: null, view: 'steps', sel: null, diag: null, data: null, built: 'end', state: '', pending: null, laneHi: null, seq: 0 };
    let modal = null, opener = null;

    function fetchJson(url) {
        const f = (window.authService && window.authService.fetch) ? window.authService.fetch.bind(window.authService) : fetch;
        return f(url).then(r => r.json().then(j => ({ ok: r.ok, status: r.status, json: j })).catch(() => ({ ok: r.ok, status: r.status, json: {} })));
    }
    function threadIdOf(chainId) {
        const rs = (typeof responses !== 'undefined' && Array.isArray(responses)) ? responses : [];
        const r = rs.find(x => x && String(x.chain_id) === String(chainId));
        const t = (r && r.thread_id) || ((typeof currentData !== 'undefined' && currentData) ? currentData.thread_id : null);
        return t == null || t === '' ? null : String(t);
    }
    function ensureModal() {
        if (modal) return modal;
        modal = document.createElement('div'); modal.id = 'codeMapModal'; modal.className = 'ui-modal-plain'; modal.style.display = 'none';
        modal.innerHTML = build.shell();
        document.body.appendChild(modal);
        modal.addEventListener('click', onClick);
        modal.addEventListener('change', e => { if (e.target && e.target.matches && e.target.matches('[data-act="pick-diag"]')) pickDiag(e.target.value); });
        document.addEventListener('keydown', e => { if (e.key === 'Escape' && st.open) { e.stopPropagation(); close(); } });   // wherever the focus sits
        return modal;
    }
    function parts() {
        const m = ensureModal();
        return { m, head: m.querySelector('.cm-head'), map: m.querySelector('.cm-map'), panel: m.querySelector('.cm-panel') };
    }
    function onClick(e) {
        const t = e.target;
        if (t === modal) { close(); return; }
        const b = t.closest ? t.closest('[data-act]') : null;
        if (!b || b.hasAttribute('disabled')) return;
        const act = b.getAttribute('data-act');
        if (act !== 'lane') st.laneHi = null;
        if (act === 'close') { close(); return; }
        if (b.tagName === 'A') e.preventDefault();
        if (act === 'view') setView(b.getAttribute('data-view'));
        else if (act === 'pick-r') select({ t: 'r', id: b.getAttribute('data-id') });
        else if (act === 'pick-s') select({ t: 's', id: parseInt(b.getAttribute('data-cell'), 10) });
        else if (act === 'clear') select(null);
        else if (act === 'open-chain') openChain(b.getAttribute('data-chain'), b.getAttribute('data-cell'));
        else if (act === 'open-nb') openNotebook(parseInt(b.getAttribute('data-cell'), 10));
        else if (act === 'lane') { st.laneHi = b.getAttribute('data-lane'); select(null); }
    }
    function select(sel) {
        st.sel = sel;
        if (sel && sel.t === 'r') st.diag = sel.id;
        else if (sel && sel.t === 's' && st.data) { const fk = build.figsOf(st.data, sel.id); if (fk.length) st.diag = fk[0]; }
        render();
    }
    function setView(v) { st.view = v === 'diagram' ? 'diagram' : 'steps'; render(); }
    function pickDiag(k) { st.diag = k; st.sel = { t: 'r', id: k }; render(); }
    function defaultDiag(view) {
        const keys = Object.keys(view.diagrams || {});
        if (st.diag && keys.indexOf(st.diag) >= 0) return st.diag;
        const first = keys.find(k => view.results[k] && view.results[k].kind === 'result' && view.results[k].status !== 'corrected' && view.results[k].status !== 'not computed');
        return first || keys[0] || null;
    }
    // another chain's map: the app moves there (navigateToChainId), and onChain brings the map along; a chain the
    // navigator does not hold is read straight from the server
    function openChain(chainId, cell) {
        if (!chainId) return;
        st.pending = cell ? { t: 's', id: parseInt(cell, 10) } : null;
        if (chainNumber(chainId) && typeof navigateToChainId === 'function') {
            navigateToChainId(chainId);
            if (String(st.chainId) !== String(chainId)) load(chainId);     // the hook did not fire (the navigator did not move)
        } else load(chainId);
    }
    function openNotebook(cell) {
        const chain = st.chainId;
        close();
        if (chain && typeof navigateToChainId === 'function' && (typeof responses !== 'undefined') && (typeof currentResponseIndex !== 'undefined') && responses[currentResponseIndex] && String(responses[currentResponseIndex].chain_id) !== String(chain)) navigateToChainId(chain);
        if (typeof paneOpenCell === 'function' && cell) paneOpenCell(cell);
    }
    function load(chainId) {
        const threadId = threadIdOf(chainId);
        st.chainId = String(chainId); st.threadId = threadId; st.data = null; st.state = 'loading'; st.sel = null; st.diag = null; st.laneHi = null;
        const seq = ++st.seq;
        render();
        if (!threadId) { st.state = 'unreachable'; render(); return Promise.resolve(null); }
        return fetchJson('/code_map/' + encodeURIComponent(threadId) + '/' + encodeURIComponent(chainId)).then(res => {
            if (seq !== st.seq) return null;                      // a later load took over
            const j = res.json || {};
            if (!res.ok) { st.state = res.status === 404 ? 'unfinished' : 'unreachable'; render(); return null; }
            if (j.state) { st.state = j.state === 'running' ? 'running' : 'unfinished'; render(); return null; }
            if (j.error || !j.map) { st.state = 'error'; render(); return null; }
            st.data = j.map; st.built = j.built || 'end'; st.state = '';
            st.diag = defaultDiag(j.map);
            if (st.pending) { st.sel = st.pending; st.pending = null; }
            render();
            return j.map;
        }).catch(() => { if (seq === st.seq) { st.state = 'unreachable'; render(); } return null; });
    }
    function render() {
        const p = parts();
        const view = st.data;
        const ctx = ctxOf(view, st.built);
        p.head.innerHTML = build.header(view, ctx, st);
        if (!view) { p.map.innerHTML = build.state(st.state || 'loading'); p.panel.innerHTML = ''; return; }
        if (view.nocode) { p.map.innerHTML = build.nocode(view, ctx); p.panel.innerHTML = build.summary(view, ctx); return; }
        const focus = focusOf(view, st.sel);
        p.map.innerHTML = st.view === 'diagram' ? build.diagram(view, ctx, st.diag || defaultDiag(view)) : build.steps(view, ctx, st.sel, focus);
        if (st.laneHi) { const ln = p.map.querySelector('[data-lane="' + st.laneHi + '"]'); if (ln) ln.classList.add('hi'); }
        p.panel.innerHTML = st.sel && st.sel.t === 'r' ? build.result(view, ctx, st.sel.id) : (st.sel && st.sel.t === 's' ? build.step(view, ctx, st.sel.id) : build.summary(view, ctx));
        if (p.panel.scrollTop) p.panel.scrollTop = 0;
    }

    // ------------------------------------------------------------ the public face
    function open(chainId, opts) {
        const m = ensureModal();
        let id = chainId;
        if (!id && typeof responses !== 'undefined' && typeof currentResponseIndex !== 'undefined' && responses[currentResponseIndex]) id = responses[currentResponseIndex].chain_id;
        if (!id) return;
        opener = (typeof document !== 'undefined' && document.activeElement && document.activeElement !== document.body) ? document.activeElement : null;
        st.open = true; m.style.display = 'flex';
        st.view = (opts && opts.view === 'diagram') ? 'diagram' : 'steps';     // a fresh opening starts at the Steps view; moving between chains keeps the view
        st.pending = opts && opts.cell ? { t: 's', id: parseInt(opts.cell, 10) } : null;
        load(id);
        const x = m.querySelector('.cm-head button.x');
        if (x && typeof x.focus === 'function') x.focus();                   // keyboard users land in the dialog; Escape closes it
    }
    function close() {
        st.open = false;
        if (modal) modal.style.display = 'none';
        if (opener && typeof opener.focus === 'function') { try { opener.focus(); } catch (e) { /* gone */ } }
        opener = null;
    }
    // the chain navigator moved (ui-controls.js updateNavigationButtons): the open map follows it
    function onChain(chainId) {
        if (!st.open || !chainId || String(chainId) === String(st.chainId)) return;
        load(chainId);
    }
    function initialize() { /* the modal is made on first use; the ways in carry their own handlers */ }

    window.CodeMapUI = { initialize, open, close, onChain, build, layout, words: WORDS, state: st };
    window.__codeMapBuild = build;
})();
