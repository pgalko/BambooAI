// routines.js - Routines (docs/ROUTINES_DESIGN.md, 2026-10-10): the Save pill's menu (Save as favourite / Save as
// routine), the Save-as-routine dialog, the Routines manager behind the rail entry, the favourites' cards' Routine
// button and the composer lock a run's view sets. Markup is built here on the app's own grammar (ui-*); the
// stylesheet rules are in dialogs.css (the dialogs) and shell.css (the pill's menu, the rail entry).
//
// Server routes (web_app/routines_routes.py): GET /routines, GET /routines/<id>, DELETE /routines/<id>,
// POST /routines/<id>/rename, GET /routines/<id>/script, GET /routines/by_origin/<thread>[/<chain>],
// POST /routines/propose and POST /routines/create - the last two stream the pane's rows and end with one of
// routine_proposal | routine_made | routine_error; POST /routines/<id>/run streams a run; a fill (§14.3) is
// POST /routines/<id>/fill, read at GET /routines/fill and stopped at POST /routines/fill/stop.

(function () {
    'use strict';

    function esc(s) {
        return String(s == null ? '' : s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
    }
    function fmtDate(ts) {
        if (!ts) return '';
        try { return new Date(Number(ts) * 1000).toLocaleDateString(undefined, { day: 'numeric', month: 'short' }); } catch (e) { return ''; }
    }
    function fmtDateTime(ts) {
        if (!ts) return '';
        try { return new Date(Number(ts) * 1000).toLocaleString(undefined, { day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit' }); } catch (e) { return ''; }
    }
    function chainDate(chainId) {
        // a chain id is a unix timestamp (the app mints them so); a date for "the analysis of 10 Oct"
        const n = Number(chainId);
        if (!chainId || isNaN(n)) return '';
        return fmtDate(n);
    }
    function sourceLabel(kind) {
        return ({ file: 'File', intervals: 'Intervals.icu', endura: 'Endura', sweatstack: 'SweatStack', frame: 'File', csv: 'File', cache: 'File', none: 'No data' })[kind] || (kind || 'Data');
    }
    function loadLabel(ld) {
        if (!ld || !ld.source) return '';
        const src = sourceKind(ld.source);
        const from = ld.cached_from && ld.cached_from.length === 2 ? ' · cut from the ' + (ld.cached ? 'cached ' : '') + 'load ' + ld.cached_from[0] + ' → ' + ld.cached_from[1] : (ld.cached ? ' · from the cache' : '');     // a set interval's unit is cut from the span loaded (§14.3)
        const store = ld.store && typeof storeLine === 'function' ? storeLine(ld.store) : '';          // what the store held of the window (2026-10-15)
        const who = ld.subject && (ld.subject.name || ld.subject.id) ? ' · ' + (ld.subject.name || ld.subject.id) + ' ·' : '';      // whose (2026-10-30)
        if (src === 'intervals' || src === 'sweatstack') return sourceLabel(src) + who + (ld.start_date ? ' ' + ld.start_date + ' → ' + ld.end_date : '') + (ld.aux_kinds && ld.aux_kinds.length ? ' · ' + ld.aux_kinds.join(', ') : '') + (ld.sports && ld.sports.length ? ' · ' + ld.sports.join(', ') : '') + from + (store ? ' · ' + store : '');
        if (src === 'endura') return 'Endura · ' + (ld.race_title || ('race ' + (ld.race_id || ''))) + from;
        return ld.name ? 'File · ' + ld.name + (ld.cached ? ' · from the Dataset cache' : '') : '';
    }
    function sourceKind(s) {
        s = String(s || '').toLowerCase();
        if (s === 'intervals' || s === 'endura' || s === 'sweatstack') return s;
        return s === 'none' || !s ? 'none' : 'file';
    }
    function valueText(p) {
        const v = p.default;
        if (p.type === 'date_window' && Array.isArray(v)) return v[0] + ' → ' + v[1];
        if (Array.isArray(v)) return v.join(', ');
        if (p.type === 'toggle') return v ? 'on' : 'off';
        return String(v == null ? '' : v);
    }
    // an input that only restates the period the data covers is not asked: it follows the data (docs/ROUTINES_DESIGN.md §4.8)
    function derivedText(p) {
        return p.derived === 'span' ? 'follows the data: its first and last dates, written at each run'
            : (p.derived === 'window' ? 'follows the data: the window loaded, written at each run' : '');
    }
    const ICON_ROUTINE = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><polyline points="17 1 21 5 17 9"/><path d="M3 11V9a4 4 0 0 1 4-4h14"/><polyline points="7 23 3 19 7 15"/><path d="M21 13v2a4 4 0 0 1-4 4H3"/></svg>';
    const ICON_BOOKMARK = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M19 21l-7-5-7 5V5a2 2 0 0 1 2-2h10a2 2 0 0 1 2 2z"/></svg>';
    const ICON_DOWN = '<svg viewBox="0 0 24 24"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="7 10 12 15 17 10"/><line x1="12" y1="15" x2="12" y2="3"/></svg>';

    // ------------------------------------------------------------ builders (pure: return HTML; tests read them)
    const build = {
        // the Save pill's menu: the favourite item (done when the chain is one), the routine item worded by what exists
        menu(st) {
            const fav = st.saved
                ? '<div class="it done" data-act="favourite"><b>Saved as favourite</b><span>this chain is in Saved workflows</span></div>'
                : '<div class="it" data-act="favourite"><b>Save as favourite</b><span>this chain, in Saved workflows</span></div>';
            let sub = 'a method to run again on new data · saves the favourite too';
            if (st.own && st.own.length) sub = 'made from this chain: ' + esc(st.own[0].name) + ' v' + esc(st.own[0].version) + ' · again, or as a next version';
            else if (st.thread && st.thread.length) sub = 'next version of “' + esc(st.thread[0].name) + '”, or a new one';
            return fav + '<div class="it" data-act="routine"><b>Save as routine</b><span>' + sub + '</span></div>';
        },
        dialogShell() {
            return '<div class="modal-content ui-dlg lg routine-dlg">' +
                '<div class="ui-dlg-h"><div><div class="title">Save as routine</div><div class="sub"></div></div><span class="sp"></span><button class="x" aria-label="Close">×</button></div>' +
                '<div class="ui-dlg-b"></div>' +
                '<div class="ui-dlg-f"><span class="note"></span><span class="sp"></span><button class="ui-btn" data-act="cancel">Cancel</button><button class="ui-btn primary" data-act="create">' + ICON_ROUTINE + '<span>Create routine</span></button></div></div>';
        },
        loading(text) {
            return '<div class="rt-wait"><span class="live"></span>' + esc(text) + '</div>';
        },
        // the Save-as-routine dialog while the proposal is made (§17): a checklist that fills as the steps pass - the analysis read,
        // the data checked, the model's turn (with a clock), the proposal prepared - each line with what the step found
        STEPS: [['chain', 'Reading the analysis', 'Read the analysis'], ['data', 'Checking the data', 'Checked the data'],
                ['model', 'Working out what you can change each run, and which results to compare', 'Working out what you can change each run, and which results to compare'],
                ['proposal', 'Preparing the proposal', 'Prepared the proposal']],
        clock(ms) { const sec = Math.max(0, Math.floor(ms / 1000)); return Math.floor(sec / 60) + ':' + String(sec % 60).padStart(2, '0'); },
        steps(st, now) {
            return '<div class="rt-steps">' + build.STEPS.map(([key, doing, done]) => {
                const x = (st || {})[key] || {}, state = x.state || 'pending';
                const detail = state === 'running' ? [x.again ? (x.detail || 'the reply could not be read') + '; asking again' : '', x.since ? build.clock((now || Date.now()) - x.since) : ''].filter(Boolean).join(' · ') : (state === 'done' ? x.detail || '' : '');
                return '<div class="s ' + state + '" data-step="' + key + '"><span class="m">' + (state === 'done' ? '✓' : (state === 'running' ? '<i class="live"></i>' : '○')) + '</span>' +
                    '<span class="t">' + esc(state === 'done' ? done : doing) + '</span>' + (detail ? '<span class="d">— ' + esc(detail) + '</span>' : '') + '</div>';
            }).join('') + '</div>';
        },
        error(message, retry) {
            return '<div class="rt-error"><div class="msg">' + esc(message) + '</div>' + (retry ? '<div class="row"><button class="ui-btn sm" data-act="retry">Try again</button></div>' : '') + '</div>';
        },
        dataLine(p) {
            const d = p.data || {};
            const cols = (d.columns || []).length;
            const meta = [d.rows != null ? Number(d.rows).toLocaleString() + ' rows' : '', cols ? cols + ' columns' : '', d.date_range ? esc(d.date_range) : ''].filter(Boolean).join(' · ');
            const state = p.data_state === 'same' ? 'Checked once on this chain’s own data before it is created.'
                        : (p.data_state === 'assumed' ? 'The chain’s data is not on record; the data loaded now is taken for it, and the check runs on that.'
                        : 'The chain’s data is no longer loaded: the routine will be created unverified, and its first run will show whether the method still runs.');
            return '<div class="rt-data"><span class="ui-chip model"><span class="t">' + esc(sourceLabel(p.source)) + '</span></span>' +
                (d.name ? '<span class="name">' + esc(d.name) + '</span>' : '') + (meta ? '<span class="meta">' + meta + '</span>' : '') + '</div>' +
                '<div class="rt-line' + (p.data_state === 'gone' ? ' warn' : '') + '">' + state + '</div>';
        },
        inputsTable(inputs, kept) {
            if (!inputs || !inputs.length) {
                return '<div class="rt-line">No inputs: the method runs as it is on data of the same shape.</div>' +
                    (kept && kept.length ? '<div class="rt-line muted">' + kept.map(esc).join(' · ') + '</div>' : '');
            }
            const rows = inputs.map(p => '<tr data-key="' + esc(p.key) + '"' + (p.derived ? ' data-derived="' + esc(p.derived) + '"' : '') + '><td>' + esc(p.label) + (p.type === 'choice' && p.column ? '<span class="from"> · from ' + esc(p.column) + '</span>' : '') + '</td>' +
                '<td><span class="val">' + esc(valueText(p)) + '</span>' + (p.derived ? '<span class="rt-derived">' + esc(derivedText(p)) + '</span>' : '') + '</td><td><span class="from">' + esc(p.origin || '') + '</span></td>' +
                '<td class="keep"><label class="rt-check"><input type="checkbox" data-drop="' + esc(p.key) + '"> keep fixed</label></td></tr>').join('');
            return '<table class="ui-table rt-inputs"><thead><tr><th>Input</th><th>Value now</th><th>Where it comes from</th><th></th></tr></thead><tbody>' + rows + '</tbody></table>' +
                (kept && kept.length ? '<div class="rt-line muted">Left as they are: ' + kept.map(esc).join(' · ') + '</div>' : '');
        },
        // the lines a run will compare (§15.2): the lines kept, each named, with drop on hover; the lines the promoter set aside
        // behind one muted line that opens on a click, each with keep; a typed line keeps its flag and its choice, visible, the
        // default following the pick. `open` is whether the set-aside group is unfolded.
        resultsList(results, open) {
            if (!results || !results.length) return '<div class="rt-line">This analysis recorded no RESULT lines, so runs will not be compared number by number; the routine still keeps its printed output and figures.</div>';
            const row = (r, i) => r.typed
                ? '<div class="r flag' + (r.dropped ? ' off' : '') + '" data-line="' + i + '" data-cell="' + esc(r.cell) + '" data-index="' + esc(r.index) + '"><span class="g">!</span><span class="l">cell ' + esc(r.cell) + ': the numbers were typed into the call, not computed — this line will not change with new data</span>' +
                  '<span class="ui-seg"><span' + (r.dropped ? '' : ' class="on"') + ' data-keep="1">keep as a constant</span><span' + (r.dropped ? ' class="on"' : '') + ' data-keep="0">drop</span></span></div>'
                : r.dropped
                    ? '<div class="r off" data-line="' + i + '"><span class="g">○</span><span class="l" title="' + esc(r.label) + '">' + esc(r.label) + '</span><span class="c">cell ' + esc(r.cell) + '</span><button type="button" class="act" data-line-act="keep">keep</button></div>'
                    : '<div class="r" data-line="' + i + '"><span class="g">✓</span><span class="l" title="' + esc(r.label) + '">' + esc(build.lineName(r)) + '</span><span class="c">cell ' + esc(r.cell) + '</span><button type="button" class="act" data-line-act="drop">drop</button></div>';
            const aside = results.map((r, i) => [r, i]).filter(([r]) => r.dropped && !r.typed), setAside = new Set(aside.map(([, i]) => i));
            return '<div class="rt-results">' + results.map((r, i) => setAside.has(i) ? '' : row(r, i)).join('') +
                (aside.length ? '<div class="more' + (open ? ' open' : '') + '"><button type="button" class="t" data-line-act="more">' + (open ? '▾' : '▸') + ' ' + aside.length + ' more line' + (aside.length === 1 ? '' : 's') + ' recorded, not compared</button>' +
                    (open ? '<div class="aside">' + aside.map(([r, i]) => row(r, i)).join('') + '</div>' : '') + '</div>' : '') + '</div>';
        },
        // the dialog's Results section, rebuilt on its own when a line moves (§15.2)
        resultsSection(p, open) {
            const all = (p.results || []), kept = all.filter(r => !r.dropped).length;
            const count = kept === all.length ? kept + ' kept' : kept + ' of ' + all.length + ' kept';
            return '<div class="h">Results <span class="n">— the lines the runs will compare, ' + count + (p.figures && p.figures.count ? ' · ' + p.figures.count + ' figure' + (p.figures.count === 1 ? '' : 's') : '') + '</span></div>' + build.resultsList(all, open);
        },
        // the routine a chain's proposal stands under (2026-10-12): the one made from this very chain, else the thread's
        // first; and which it is, since the offer and its default differ - this chain's own routine defaults to its next
        // version, a routine made from an earlier chain of the thread to a new routine (a follow-up is usually another
        // question - the first live case, a temperature chain after an hour-of-day one, was saved as a new routine with the
        // button still reading "Make it v2")
        underOf(p, threadRoutines) {
            const list = threadRoutines || [];
            const own = list.find(r => p && p.chain_id != null && String(r.chain_id) === String(p.chain_id));
            if (own) return { routine: own, own: true };
            return list.length ? { routine: list[0], own: false } : null;
        },
        // what the dialog's foot and fields say for a version choice: the button's label, the note under it, whether the
        // What-changed line shows, and the name the field holds (the routine's for a next version, the proposal's for a new one)
        versionState(choice, under, p) {
            if (!under) return { label: 'Create routine', note: 'The routine is checked once on this chain’s own data before it is created; the chain is saved as a favourite, and the routine links to it.', change: false, name: p ? p.name : '' };
            if (choice === 'next') return { label: 'Make it v' + (Number(under.routine.version) + 1), note: 'The new version is checked once on this chain’s data before it replaces the current one; earlier versions stay runnable.', change: true, name: under.routine.name };
            return { label: 'Create routine', note: 'The routine is checked once on this chain’s own data before it is created, apart from “' + under.routine.name + '”; the chain is saved as a favourite, and the routine links to it.', change: false, name: p ? p.name : '' };
        },
        proposal(p, threadRoutines) {
            const under = build.underOf(p, threadRoutines);
            const choice = under ? (under.own ? 'next' : 'new') : null;
            const vs = build.versionState(choice, under, p);
            let h = '';
            if (under) {
                h += '<div class="rt-sec"><div class="h">' + (under.own ? 'This analysis is the origin of a routine' : 'A routine was made from an earlier chain of this thread') + '</div><div class="ui-choices rt-version">' +
                    '<div class="ui-choice' + (choice === 'next' ? ' on' : '') + '" data-version="next"><b>Next version of “' + esc(under.routine.name) + '”</b><span>v' + (Number(under.routine.version) + 1) + ' · the method of this chain, the inputs carried over, checked on this chain’s data</span></div>' +
                    '<div class="ui-choice' + (choice === 'new' ? ' on' : '') + '" data-version="new"><b>A new routine</b><span>kept apart from “' + esc(under.routine.name) + '”</span></div></div>' +
                    '<div class="ui-field rt-change"' + (vs.change ? '' : ' style="display:none"') + '><label>What changed</label><input class="ui-input" data-field="change_note" placeholder="one line, for the versions list"></div></div>';
            }
            h += '<div class="ui-field"><label>Name</label><input class="ui-input" data-field="name" value="' + esc(vs.name) + '" maxlength="80"></div>';
            h += '<div class="ui-field"><label>Purpose <span class="ui-muted">— one line for the card and for the note written after each run</span></label><input class="ui-input" data-field="purpose" value="' + esc(p.purpose || p.question || '') + '" maxlength="300"></div>';
            h += '<div class="rt-sec"><div class="h">Data</div>' + build.dataLine(p) + '</div>';
            h += '<div class="rt-sec"><div class="h">Inputs <span class="n">— what you can change each run; everything else stays as the analysis had it</span></div>' + build.inputsTable(p.inputs, p.kept) + '</div>';
            h += '<div class="rt-sec" data-sec="results">' + build.resultsSection(p, false) + '</div>';
            if (p.notes && p.notes.length) h += '<div class="rt-sec"><div class="h">Notes</div><div class="rt-line muted">' + p.notes.map(esc).join('<br>') + '</div></div>';
            return h;
        },
        // the manager
        managerShell() {
            return '<div class="ui-dlg lg rt-mgr"><div class="rt-left"><div class="ui-side-label">Routines</div><div class="rt-side"></div></div>' +
                '<div class="rt-right"><div class="ui-dlg-h"><div><div class="title"></div><div class="sub"></div></div><span class="sp"></span><div class="rt-actions"></div><button class="x" aria-label="Close">×</button></div><div class="rt-body"></div></div></div>';
        },
        sideItem(r, on) {
            const st = r.run_zero_status === 'verifying' ? ' · verifying…' : (r.run_zero_status === 'condensing' ? ' · condensing…' : (r.run_zero_status === 'differed' || r.run_zero_status === 'failed' ? ' · did not reproduce' : ''));
            return '<div class="it' + (on ? ' on' : '') + '" data-id="' + esc(r.id) + '"><b>' + esc(r.name) + '</b><span>' + esc(sourceLabel(r.source)) + ' · v' + esc(r.current_version) + (r.runs ? ' · ' + r.runs + ' run' + (r.runs === 1 ? '' : 's') : '') + st + ' · ' + esc(fmtDate(r.updated || r.created)) + '</span></div>';
        },
        empty() {
            return '<div class="rt-empty">No routines yet. On a finished analysis, hover <b>Save</b> and choose <b>Save as routine</b>: the method keeps its few inputs and runs again on new data, without a model.</div>';
        },
        routineHeader(r) {
            const o = r.origin || {};
            const link = r.origin_available
                ? '<a href="#" class="rt-origin" data-thread="' + esc(o.thread_id) + '" data-chain="' + esc(o.chain_id) + '" title="a favourite: open the analysis and continue it there">from the analysis of ' + esc(chainDate(o.chain_id) || o.chain_id) + ' ↗</a>'
                : '<span class="ui-muted">from the analysis of ' + esc(chainDate(o.chain_id) || o.chain_id) + ' — no longer in Saved workflows</span>';
            return { title: esc(r.name), sub: esc(sourceLabel(r.source)) + ' · v' + esc(r.current_version) + ' · ' + link };
        },
        // the manager's body (S2, redesigned 2026-11-08: one column, one scroll): the facts - Purpose, Inputs, Results, Version(s) -
        // then the runs of the interval and athlete picked as a table. `fill` is the session's fill when it is this routine's
        // (§14.3); `opts` {today, horizon} the units a set interval's view spans (§14.6: the last year, or the plan's day limit)
        routineBody(r, fill, opts) {
            const v = (r.versions || []).find(x => x.number === r.current_version) || (r.versions || [])[(r.versions || []).length - 1] || {};
            const m = v.manifest || {};
            let h = '<div class="ui-kv rt-facts">' + (r.purpose ? '<b>Purpose</b><span>' + esc(r.purpose) + '</span>' : (r.question ? '<b>Question</b><span>' + esc(r.question) + '</span>' : '')) +
                '<b>Inputs</b><span>' + build.inputsFacts(m.parameters || []) + '</span><b>Results</b><span>' + esc(build.resultsFacts(m)) + '</span>' +
                '<b>Version' + ((r.versions || []).length > 1 ? 's' : '') + '</b><span class="rt-vers">' + build.versionRows(r) + '</span></div><div class="rt-sep"></div>';
            // the runs by athlete (2026-10-30): a choice when the runs span more than one; the latest run's athlete first
            const athletes = build.runAthletes(r);
            const picked = athletes.find(a => a.id === managerState.athlete) ? managerState.athlete : (athletes[0] ? athletes[0].id : '');
            const many = athletes.length > 1;
            const pick = many ? '<select class="ui-input rt-athlete-pick" data-pick="athlete" title="whose runs">' + athletes.map(a => '<option value="' + esc(a.id) + '"' + (a.id === picked ? ' selected' : '') + '>' + esc(a.name || a.id || 'athlete not recorded') + ' · ' + a.n + ' run' + (a.n === 1 ? '' : 's') + '</option>').join('') + '</select>' : '';
            // the runs by interval (§14.6): the filter bar's pick - the one asked, else the latest run's; a set interval is the table by
            // unit over the horizon's units, custom the table by run
            const athleteId = many ? picked : null;
            const counts = build.intervalCounts(r, athleteId);
            const kind = counts[managerState.interval] ? managerState.interval : build.openInterval(r, athleteId);
            const o = opts || {};
            const series = kind === 'custom' ? null : build.series(r, kind, athleteId, build.units(kind, o.today || new Date(), o.horizon || 365));
            const prefix = series ? build.sharedPrefix(series.lines.map(l => build.lineName(l))) : '';
            const unit = series && series.lines.length && series.lines.every(l => (l.unit || '') === (series.lines[0].unit || '')) ? (series.lines[0].unit || '') : '';
            const headNote = series ? '— by ' + kind + ', the latest first' + (prefix ? ' · ' + esc(prefix) + (unit && unit !== 'n/a' ? ', ' + esc(unit) : '') : '') : '— each run against the one before it';
            h += '<div class="rt-sec rt-runsec"><div class="h">Runs <span class="n">' + headNote + '</span>' + build.filterBar(counts, kind) + pick + '</div>' + build.fillBar(fill) + (series ? build.byIntervalTable(series, prefix) : build.runsTable(r, athleteId)) + '</div>';
            return h;
        },
        // the Inputs fact: none, or a line per input - the label, its default (a derived one says what it follows), where it came from
        inputsFacts(params) {
            if (!params.length) return 'none';
            return params.map(p => '<span class="rt-input" data-key="' + esc(p.key) + '"' + (p.derived ? ' data-derived="' + esc(p.derived) + '"' : '') + '><span class="k">' + esc(p.label) + '</span> ' +
                (p.derived ? '<span class="rt-derived">' + esc(derivedText(p)) + '</span>' : '<span class="val">' + esc(valueText(p)) + '</span>') + (p.origin ? ' <span class="from">' + esc(p.origin) + '</span>' : '') + '</span>').join('');
        },
        // the Results fact: what a run records - the numbers compared run to run (the table's columns) and the charts
        resultsFacts(m) {
            const n = ((m || {}).results || []).filter(x => !x.dropped && x.estimate != null).length, k = Number(((m || {}).figures || {}).count) || 0;
            const nums = n ? n + ' number' + (n === 1 ? '' : 's') : '', charts = k ? k + ' chart' + (k === 1 ? '' : 's') : '';
            if (!n && !k) return 'none recorded: runs keep their printed output';
            return (nums && charts ? nums + ' and ' + charts : nums || 'no numbers recorded, ' + charts) + ' per run';
        },
        // the Version rows, newest first: the number, the date, the chain it came from when there are several, run zero's verdict (the
        // lines reproduced; the reason when it did not), the condensed code's size and time or that the code runs as written (§19),
        // the consolidation's state (§19.3),
        // the code as written to take away, the change note after the first version
        versionRows(r) {
            const vs = (r.versions || []).slice().reverse(), several = vs.length > 1;
            return vs.map(x => {
                const rz = x.run_zero || {}, st = rz.status || (rz.verified ? 'reproduced' : 'unverified');
                const n = (((x.manifest || {}).results) || []).length;
                let t = esc(fmtDate(x.created)) + (several ? ' · from the analysis of ' + esc(chainDate((x.promoted_from || {}).chain_id) || (x.promoted_from || {}).chain_id) : '') + ' · ' + build.zeroStatus(rz);
                if (st === 'reproduced' || (rz.verified && st !== 'verifying' && st !== 'condensing')) t += n ? ', ' + n + ' line' + (n === 1 ? '' : 's') + ' reproduced' : '';
                else if (st === 'differed' || st === 'failed') t += rz.line ? ' — ' + esc(rz.line) : '';
                const c = x.condensed || {};
                if (c.status === 'condensed' && c.cells) t += ' · ' + esc(c.cells[1]) + ' cell' + (c.cells[1] === 1 ? '' : 's') + (c.elapsed && c.elapsed[1] != null ? ' · ' + build.secsText(c.elapsed[1]) : '');
                else if (c.status === 'as_written') t += ' · <span class="rt-aswritten" title="' + esc(c.line || '') + '">as written</span>';     // the chain's code runs: why on hover
                const k = x.consolidated || {};
                if (k.status === 'consolidated') t += ' · ' + (k.confirmed ? 'rewritten, confirmed on run ' + esc(k.confirmed.run) : 'rewritten, the next run on new data checks it');
                else if (k.status === 'fell_back') t += ' · rewrite dropped on run ' + esc((k.fell_back || {}).run);
                if (x.written_chars > 0 && r.id) t += ' · <a class="rt-written" href="/routines/' + esc(r.id) + '/script?written=1" download title="the code as the analysis wrote it, before it was condensed">as written ↓</a>';
                if (x.change_note && x.change_note !== 'first version') t += ' · “' + esc(x.change_note) + '”';
                return '<span class="v" data-version="' + esc(x.number) + '"><b>v' + esc(x.number) + '</b>' + t + '</span>';
            }).join('');
        },
        secsText(t) { t = Number(t) || 0; return Math.round(t * 10) / 10 < 10 ? (Math.round(t * 10) / 10) + ' s' : fmtTook(t); },
        shown(estimate) { return esc(String(estimate == null ? '' : estimate).replace(/^\+/, '')); },     // a value as the Summary's tables show it: the sign only when negative (2026-11-08)
        // ---- the Summary by interval (§14.6): the counts and the filter bar, the series of one interval on one athlete, the table by
        // unit with a thumbnail per line, the enlarged chart. The runs that count are the current version's that ran.
        INTERVAL_NAMES: { day: 'Daily', week: 'Weekly', month: 'Monthly', year: 'Yearly', custom: 'Custom' },
        doneRuns(r, athleteId) {
            return (r.runs || []).filter(x => x.version === r.current_version && ['ran', 'reproduced', 'differed'].includes(x.status) && (athleteId == null || build.subjectId(x) === String(athleteId)));
        },
        // how many runs each interval has on the athlete; run zero counts as custom when it is theirs
        intervalCounts(r, athleteId) {
            const v = (r.versions || []).find(x => x.number === r.current_version) || {};
            const out = { day: 0, week: 0, month: 0, year: 0, custom: 0 };
            build.doneRuns(r, athleteId).forEach(x => { out[x.interval in out ? x.interval : 'custom'] += 1; });
            if (v.run_zero && v.run_zero.verified && build.zeroFits(v, athleteId)) out.custom += 1;
            return out;
        },
        openInterval(r, athleteId) {    // the interval the Summary opens on: the latest run's, custom without one
            const runs = build.doneRuns(r, athleteId);
            return runs.length && runs[runs.length - 1].interval ? runs[runs.length - 1].interval : 'custom';
        },
        filterBar(counts, on) {
            return '<span class="ui-seg rt-filter">' + Object.keys(build.INTERVAL_NAMES).map(k => { const n = counts[k] || 0;
                return '<span class="' + [k === on ? 'on' : '', n ? '' : 'off'].filter(Boolean).join(' ') + '" data-filter="' + k + '"' + (n ? '' : ' title="no run with this interval yet"') + '>' + build.INTERVAL_NAMES[k] + (n ? '<span class="k">' + n + '</span>' : '') + '</span>'; }).join('') + '</span>';
        },
        // the series: the manifest's lines with estimates; the horizon's units, each with the latest run on it that ran and that run's
        // values by line - a unit whose runs all failed carries its latest failed run under `failed`, a row that says why (2026-11-08),
        // and counts as not run; the rows (the units with a run, the latest first); the first and last unit run; what is missing
        series(r, kind, athleteId, units) {
            const v = (r.versions || []).find(x => x.number === r.current_version) || {};
            const all = (v.manifest || {}).results || [];
            const lines = all.filter(x => !x.dropped && x.estimate != null);
            const byUnit = {}, failedBy = {};
            const key = x => { const w = (x.data || {}).window || []; return w[0] + ' ' + w[1]; };
            build.doneRuns(r, athleteId).filter(x => x.interval === kind).forEach(x => { if (!byUnit[key(x)] || x.number > byUnit[key(x)].number) byUnit[key(x)] = x; });
            (r.runs || []).filter(x => x.version === r.current_version && ['failed', 'timed_out'].includes(x.status) && x.interval === kind && (athleteId == null || build.subjectId(x) === String(athleteId)))
                .forEach(x => { if (!failedBy[key(x)] || x.number > failedBy[key(x)].number) failedBy[key(x)] = x; });
            const points = units.map(w => { const k = w[0] + ' ' + w[1], run = byUnit[k] || null;
                return { unit: w, run, failed: run ? null : failedBy[k] || null, values: run ? lines.map(l => (run.results || [])[all.indexOf(l)] || null) : null }; });
            const have = points.map((p, i) => p.run ? i : -1).filter(i => i >= 0);
            const first = have.length ? have[0] : -1, last = have.length ? have[have.length - 1] : -1;
            return { kind, units, lines, points, first, last, rows: points.filter(p => p.run || p.failed).reverse(), missing: units.length - have.length, missingBefore: have.length ? first : units.length };
        },
        // the words the labels share up to a comma: said once in the heading, so the columns carry what differs
        sharedPrefix(labels) {
            if (labels.length < 2) return '';
            const parts = labels.map(l => String(l).split(/,\s+/));
            let n = 0;
            while (parts.every(p => p.length > n + 1 && p[n] === parts[0][n])) n++;
            return n ? parts[0].slice(0, n).join(', ') : '';
        },
        value(x) { const v = parseFloat(String((x || {}).estimate).replace(/,/g, '')); return x && !isNaN(v) ? v : null; },     // a line's estimate as a number, null without one
        byIntervalTable(s, prefix) {
            if (!s.lines.length) return '<div class="rt-line muted">This routine records no result lines; its runs keep their output and figures.</div>';
            const one = s.kind, many = one + 's';
            if (!s.rows.length) return '<div class="rt-line muted">No ' + one + ' run within the last year.</div>';
            const heads = s.lines.map(l => { const t = build.lineName(l); return prefix && t.startsWith(prefix) ? t.slice(prefix.length).replace(/^,\s*/, '') || t : t; });
            const th = '<th>' + one.charAt(0).toUpperCase() + one.slice(1) + '</th>' + s.lines.map((l, i) => '<th class="m" title="' + esc(l.label) + '"><span class="lab">' + esc(heads[i]) + '</span>' + build.thumb(s, i) + '</th>').join('');
            const body = s.rows.map((p, ri) => {
                const run = p.run || p.failed;
                const w = '<td class="w">' + esc(build.unitText(one, p.unit, true)) + '<span class="open">open →</span><span class="r">run ' + esc(run.number) + '</span></td>';
                if (!p.run) return '<tr class="failed" data-run="' + esc(run.number) + '">' + w + '<td class="f" colspan="' + s.lines.length + '">' + esc(run.line || run.status.replace('_', ' ')) + '</td></tr>';
                let below = null;                                   // the unit before it that ran: the next row below with values
                for (let k = ri + 1; k < s.rows.length && !below; k++) if (s.rows[k].run) below = s.rows[k];
                const tds = s.lines.map((l, i) => {
                    const x = p.values[i], b = below ? below.values[i] : null;
                    const mark = x && b ? build.markOf(x, b) : '';
                    return '<td class="num"' + (x ? ' title="run ' + esc(p.run.number) + (build.ivl(x) ? ' · ' + build.ivl(x).replace(/"/g, '') : '') + '"' : '') + '>' + (x ? build.shown(x.estimate) : '<span class="rt-mark missing">·</span>') +
                        (mark && mark !== 'missing' ? ' <span class="rt-mark ' + esc(mark) + '">' + build.markText(mark) + '</span>' : '') + '</td>';
                }).join('');
                return '<tr' + (ri === 0 ? ' class="latest"' : '') + ' data-run="' + esc(p.run.number) + '">' + w + tds + '</tr>';
            }).join('');
            const gap = s.missing ? '<div class="rt-foot">' + s.missing + ' ' + (s.missing === 1 ? one : many) + (s.missingBefore === s.missing ? ' back to ' + esc(build.dateText(s.units[0][0])) : ' in the last year') + ' not run yet · <a data-act="fill" data-kind="' + esc(one) + '">fill ' + (s.missing === 1 ? 'it' : 'them') + '</a></div>' : '';
            return '<div class="rt-byunit"><table class="ui-table rt-by"><thead><tr>' + th + '</tr></thead><tbody>' + body + '</tbody></table></div>' + gap;
        },
        // a line's thumbnail over the units run, at their place in the calendar (the first run to the last): the line breaks where a
        // unit is not run, the latest dot is ringed; nothing with fewer than two points
        thumb(s, i) {
            const pts = s.points.map((p, k) => ({ k, v: p.values ? build.value(p.values[i]) : null })).filter(p => p.v != null);
            if (pts.length < 2) return '';
            const k0 = pts[0].k, span = Math.max(1, pts[pts.length - 1].k - k0);
            const vals = pts.map(p => p.v), min = Math.min.apply(null, vals), max = Math.max.apply(null, vals), vs = (max - min) || 1;
            const x = k => (4 + (k - k0) / span * 104).toFixed(1), y = v => (20 - (v - min) / vs * 16).toFixed(1);
            const segs = [[pts[0]]];
            pts.slice(1).forEach((p, j) => { if (p.k === pts[j].k + 1) segs[segs.length - 1].push(p); else segs.push([p]); });
            const last = pts[pts.length - 1];
            return '<svg class="rt-thumb" viewBox="0 0 112 24" data-line="' + i + '" role="img"><g><title>' + esc(build.lineName(s.lines[i])) + ' over the ' + s.kind + 's - click for the full chart</title></g>' +
                segs.filter(sg => sg.length > 1).map(sg => '<polyline points="' + sg.map(p => x(p.k) + ',' + y(p.v)).join(' ') + '"/>').join('') +
                pts.map(p => '<circle cx="' + x(p.k) + '" cy="' + y(p.v) + '" r="1.6"/>').join('') + '<circle class="last" cx="' + x(last.k) + '" cy="' + y(last.v) + '" r="3"/></svg>';
        },
        // the units one span of the enlarged chart shows: three, six or twelve months of them
        unitsIn(kind, months) { return Math.max(1, Math.round(months * ({ day: 30.4, week: 4.35, month: 1, year: 1 / 12 })[kind])); },
        // the key to the enlarged chart's lines (0266): each line named with its scale, in its colour; the second one dashed
        trendKeys(s, i, also, colors) {
            const c = Object.assign({ line: '#2ecc71', also: '#5dade2' }, colors || {});
            const key = (li, color, dashed, side) => '<span class="rt-key"><i class="sw' + (dashed ? ' dashed' : '') + '" style="' + (dashed ? 'border-color:' : 'background:') + esc(color) + '"></i>' + esc(build.lineName(s.lines[li])) + ' · ' + side + ' scale</span>';
            return key(i, c.line, false, 'left') + (also != null && also >= 0 && also !== i && s.lines[also] ? key(also, c.also, true, 'right') : '');
        },
        // the enlarged chart (§14.6): a calendar axis over the span, one dot per unit at its place, the line broken where a unit is
        // not run (a dashed box over a stretch of them, with the count when it fits), the values written at the latest, the highest
        // and the lowest, every dot titled with its run; `also` a second line on a right axis. Colours are given, so a PNG keeps them.
        trendChart(s, i, months, also, colors) {
            const c = Object.assign({ text: '#9aa3ad', grid: '#2a3038', line: '#2ecc71', also: '#5dade2', box: '#6b7480' }, colors || {});
            const W = 1180, H = 360, L = 60, R = also != null && also >= 0 ? 60 : 20, T = 28, B = 44, pw = W - L - R, ph = H - T - B;
            const n = build.unitsIn(s.kind, months), k0 = Math.max(0, s.units.length - n), units = s.units.slice(k0);
            if (!units.length) return '<svg class="rt-chart" viewBox="0 0 ' + W + ' ' + H + '"></svg>';
            const x = k => L + (k - k0 + 0.5) / units.length * pw;
            const fmt = v => Math.abs(v) >= 100 ? v.toFixed(0) : (Math.abs(v) >= 10 ? v.toFixed(1) : v.toFixed(2));
            const seriesOf = li => s.points.slice(k0).map((p, j) => ({ k: k0 + j, p, v: p.values ? build.value(p.values[li]) : null })).filter(q => q.v != null);
            const draw = (li, color, side, dashed) => {
                const pts = seriesOf(li);
                if (!pts.length) return { svg: '', pts };
                const vals = pts.map(q => q.v), lo = Math.min.apply(null, vals), hi = Math.max.apply(null, vals), pad = (hi - lo || Math.abs(hi) || 1) * 0.08;
                const y0 = lo - pad, y1 = hi + pad, y = v => T + ph - (v - y0) / (y1 - y0) * ph;
                let g = '';
                for (let t = 0; t <= 4; t++) {                    // the axis: five labels, the grid once (for the left line)
                    const v = y0 + (y1 - y0) * t / 4;
                    g += side === 'left' ? '<line x1="' + L + '" y1="' + y(v).toFixed(1) + '" x2="' + (W - R) + '" y2="' + y(v).toFixed(1) + '" stroke="' + c.grid + '" stroke-width="1"/><text x="' + (L - 8) + '" y="' + (y(v) + 4).toFixed(1) + '" text-anchor="end" fill="' + c.text + '" font-size="11">' + fmt(v) + '</text>'
                        : '<text x="' + (W - R + 8) + '" y="' + (y(v) + 4).toFixed(1) + '" fill="' + color + '" font-size="11">' + fmt(v) + '</text>';
                }
                const segs = [[pts[0]]];
                pts.slice(1).forEach((q, j) => { if (q.k === pts[j].k + 1) segs[segs.length - 1].push(q); else segs.push([q]); });
                g += segs.filter(sg => sg.length > 1).map(sg => '<polyline fill="none" stroke="' + color + '" stroke-width="2"' + (dashed ? ' stroke-dasharray="5 4"' : '') + ' points="' + sg.map(q => x(q.k).toFixed(1) + ',' + y(q.v).toFixed(1)).join(' ') + '"/>').join('');
                const hiK = pts.reduce((a, q) => (q.v > a.v ? q : a)), loK = pts.reduce((a, q) => (q.v < a.v ? q : a)), last = pts[pts.length - 1];
                g += pts.map(q => '<g class="pt"><title>run ' + esc(q.p.run.number) + ' · ' + esc(build.unitText(s.kind, q.p.unit)) + ' · ' + esc(q.p.values[li].estimate) + (build.ivl(q.p.values[li]) ? ' ' + build.ivl(q.p.values[li]).replace(/"/g, '') : '') + '</title>' +
                    '<circle cx="' + x(q.k).toFixed(1) + '" cy="' + y(q.v).toFixed(1) + '" r="' + (q === last ? 5 : 3.5) + '" fill="' + (q === last ? 'none' : color) + '" stroke="' + color + '" stroke-width="2"/></g>').join('');
                if (side === 'left') {
                    const said = [];                               // the values written: the latest, the highest, the lowest - once each
                    [last, hiK, loK].forEach(q => { if (!said.includes(q)) { said.push(q); g += '<text x="' + x(q.k).toFixed(1) + '" y="' + (q === loK && q !== last ? y(q.v) + 18 : y(q.v) - 10).toFixed(1) + '" text-anchor="middle" fill="' + c.text + '" font-size="11">' + esc(q.p.values[li].estimate) + '</text>'; } });
                }
                return { svg: g, pts };
            };
            const main = draw(i, c.line, 'left', false);
            const other = also != null && also >= 0 && also !== i ? draw(also, c.also, 'right', true) : { svg: '', pts: [] };
            // the months along the axis: a label where a unit's month differs from the unit before's; the gaps as dashed boxes
            let axis = '';
            units.forEach((w, j) => { const d = build.dayOf(w[0]), prev = j ? build.dayOf(units[j - 1][0]) : null; if (!prev || d.getMonth() !== prev.getMonth()) axis += '<text x="' + x(k0 + j).toFixed(1) + '" y="' + (H - 18) + '" text-anchor="middle" fill="' + c.text + '" font-size="11">' + build.MONTHS[d.getMonth()] + (d.getMonth() === 0 || !prev ? ' ' + d.getFullYear() : '') + '</text>'; });
            let gaps = '', run = null;
            const flush = (a, b) => { const w = x(b) - x(a) + pw / units.length; const n_ = b - a + 1; gaps += '<rect class="rt-gap" x="' + (x(a) - pw / units.length / 2).toFixed(1) + '" y="' + (T + 6) + '" width="' + w.toFixed(1) + '" height="' + (ph - 12) + '" fill="none" stroke="' + c.box + '" stroke-dasharray="4 4"/>' + (w > 150 ? '<text x="' + ((x(a) + x(b)) / 2).toFixed(1) + '" y="' + (T + ph / 2).toFixed(1) + '" text-anchor="middle" fill="' + c.text + '" font-size="12">' + n_ + ' ' + s.kind + (n_ === 1 ? '' : 's') + ' not run yet</text>' : ''); };
            s.points.slice(k0).forEach((p, j) => { const k = k0 + j; if (!p.run) { if (run === null) run = k; } else if (run !== null) { flush(run, k - 1); run = null; } });
            if (run !== null) flush(run, k0 + units.length - 1);
            const missing = s.points.slice(k0).filter(p => !p.run).length;
            return '<svg class="rt-chart" viewBox="0 0 ' + W + ' ' + H + '" width="' + W + '" height="' + H + '" font-family="-apple-system, Segoe UI, Helvetica, Arial, sans-serif" data-missing="' + missing + '" data-points="' + main.pts.length + '">' + gaps + main.svg + other.svg + axis + '</svg>';
        },
        // the athletes the routine has run on (2026-10-30): id, name, how many runs, the latest run's first; run zero counts for
        // its athlete - a run zero or a run recorded before the athlete was kept makes the "athlete not recorded" group
        runAthletes(r) {
            const v = (r.versions || []).find(x => x.number === r.current_version) || {};
            const out = [];
            const add = (id, name) => { let a = out.find(x => x.id === id); if (!a) { a = { id, name: name || '', n: 0 }; out.push(a); } if (name && !a.name) a.name = name; a.n += 1; };
            (r.runs || []).slice().reverse().forEach(x => add(build.subjectId(x), (((x.data || {}).subject) || {}).name || ''));
            if (v.run_zero && v.run_zero.verified) add(build.zeroSubject(v), ((((v.manifest || {}).data || {}).load || {}).subject || {}).name || '');
            return out;
        },
        // run zero's verdict as a status chip (2026-10-15: run zero runs behind the dialog, so a routine can be verifying; since
        // §19 condensing too, the pass after a verdict of reproduced)
        zeroStatus(rz) {
            const st = (rz && rz.status) || (rz && rz.verified ? 'reproduced' : 'unverified');
            const cls = st === 'verifying' || st === 'condensing' ? 'verifying' : (st === 'reproduced' || (rz && rz.verified) ? 'reproduced' : (st === 'differed' || st === 'failed' ? 'differed' : 'unverified'));
            const word = st === 'condensing' ? 'condensing…' : (cls === 'verifying' ? 'verifying…' : (cls === 'reproduced' ? 'verified' : (cls === 'differed' ? 'did not reproduce' : 'unverified')));
            return '<span class="rt-status ' + cls + '">' + word + '</span>';
        },
        zeroHold(r) {
            const v = (r.versions || []).find(x => x.number === r.current_version) || (r.versions || [])[(r.versions || []).length - 1] || {};
            const st = (v.run_zero || {}).status || r.run_zero_status || '';
            if (st === 'verifying') return 'still being verified on its chain’s own data — run it when it has settled';
            if (st === 'condensing') return 'its code is still being condensed — run it when it has settled';
            if (st === 'differed' || st === 'failed') return 'run zero did not reproduce the chain’s analysis — the method is not run on other data; delete it, or make it again from the chain';
            return '';
        },
        // the header's buttons; while a fill runs (§14.3) Run and Delete are greyed with the reason - the kernel is taken, and a
        // routine under a fill is not deleted under it
        actions(r, fill) {
            const busy = fill && fill.running ? (fill.routine_id === r.id ? 'a fill is running — wait for it, or stop it below' : 'a fill is running on ' + (fill.routine_name || 'another routine') + ' — wait for it, or stop it there') : '';
            const hold = busy || build.zeroHold(r);
            return '<button class="ui-btn primary" data-act="run"' + (hold ? ' disabled title="' + esc(hold) + '"' : ' title="run the method on the data loaded now"') + '>' + ICON_ROUTINE + 'Run</button>' +
                '<a class="ui-btn ghost" href="/routines/' + esc(r.id) + '/script" download title="the script, with its inputs at the top">' + ICON_DOWN + '.py</a>' +
                '<button class="ui-btn ghost" data-act="rename">Rename</button><button class="ui-btn ghost danger-text" data-act="delete"' + (busy ? ' disabled title="' + esc(busy) + '"' : '') + '>Delete</button>';
        },
        // ---- a run (docs/ROUTINES_DESIGN.md F2, S3, S4)
        inputWidget(p) {
            const v = p.default, k = esc(p.key);
            if (p.derived) {                               // written from the data at the run; nothing to type (the original's value shown for the record)
                const a = Array.isArray(v) ? v : ['', ''];
                return '<div class="rt-derived-row" data-derived="' + esc(p.derived) + '"><span class="rt-derived">' + esc(derivedText(p)) + '</span><span class="n">the original: ' + esc(a[0]) + ' → ' + esc(a[1]) + '</span></div>';
            }
            if (p.type === 'toggle') return '<label class="rt-check"><input type="checkbox" data-key="' + k + '" data-type="toggle"' + (v ? ' checked' : '') + '> on</label>';
            if (p.type === 'date_window') {
                const a = Array.isArray(v) ? v : ['', ''];
                return '<div class="rt-window"><input type="date" class="ui-input" data-key="' + k + '" data-type="date_window" data-part="0" value="' + esc(a[0]) + '"><span class="arrow">→</span><input type="date" class="ui-input" data-key="' + k + '" data-type="date_window" data-part="1" value="' + esc(a[1]) + '"></div>';
            }
            const text = Array.isArray(v) ? v.join(', ') : String(v == null ? '' : v);
            const help = p.type === 'numbers' ? 'numbers, separated by commas' : (p.type === 'choice' ? (p.multiple ? 'values of ' + esc(p.column || 'the column') + ', separated by commas' : 'a value of ' + esc(p.column || 'the column')) : '');
            return '<input class="ui-input" data-key="' + k + '" data-type="' + esc(p.type) + '" value="' + esc(text) + '"' + (p.type === 'number' ? ' inputmode="decimal"' : '') + (help ? ' title="' + help + '"' : '') + '>';
        },
        isoDay(d) { const p = n => String(n).padStart(2, '0'); return d.getFullYear() + '-' + p(d.getMonth() + 1) + '-' + p(d.getDate()); },   // the local calendar day, as core.js's localIsoDay (2026-10-15: the UTC day put the run a day past the Data tab's load)
        // ---- the interval (docs/ROUTINES_DESIGN.md §14): a run's calendar unit - a day, a week (Monday to Sunday), a month, a
        // year - or custom, the window as typed. The arithmetic lives here, in pure functions the tests read at known dates.
        MONTHS: ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'],
        MONTHS_LONG: ['January', 'February', 'March', 'April', 'May', 'June', 'July', 'August', 'September', 'October', 'November', 'December'],
        DAYS: ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat'],
        dayOf(iso) { const m = /^(\d{4})-(\d{2})-(\d{2})$/.exec(String(iso || '')); return m ? new Date(Number(m[1]), Number(m[2]) - 1, Number(m[3])) : null; },   // a local day from an ISO date (Date.parse would read it as UTC)
        // the complete units of a kind within the horizon (the last `horizonDays` days), oldest first, as [start, end] ISO days;
        // the unit under way is never complete, so never in
        units(kind, today, horizonDays) {
            const t = new Date(today.getFullYear(), today.getMonth(), today.getDate()), out = [];
            const earliest = new Date(t.getFullYear(), t.getMonth(), t.getDate() - horizonDays);
            let end;
            if (kind === 'day') end = new Date(t.getFullYear(), t.getMonth(), t.getDate() - 1);
            else if (kind === 'week') end = new Date(t.getFullYear(), t.getMonth(), t.getDate() - ((t.getDay() + 6) % 7) - 1);     // the Sunday before this week's Monday
            else if (kind === 'month') end = new Date(t.getFullYear(), t.getMonth(), 0);                                           // the last day of the month before
            else if (kind === 'year') end = new Date(t.getFullYear() - 1, 11, 31);
            else return out;
            for (;;) {
                const start = kind === 'day' ? new Date(end) : (kind === 'week' ? new Date(end.getFullYear(), end.getMonth(), end.getDate() - 6)
                    : (kind === 'month' ? new Date(end.getFullYear(), end.getMonth(), 1) : new Date(end.getFullYear(), 0, 1)));
                if (start < earliest) break;
                out.unshift([build.isoDay(start), build.isoDay(end)]);
                end = new Date(start.getFullYear(), start.getMonth(), start.getDate() - 1);
            }
            return out;
        },
        dateText(iso) { const d = build.dayOf(iso); return d ? d.getDate() + ' ' + build.MONTHS[d.getMonth()] + ' ' + d.getFullYear() : ''; },
        // a unit in words: Thu 5 Nov 2026 · Mon 26 Oct – Sun 1 Nov 2026 · October 2026 · 2026; short, for a table or a line: 5 Nov · 26 Oct – 1 Nov · 19 – 25 Oct · Oct 2026
        unitText(kind, w, short) {
            const a = build.dayOf(w && w[0]), b = build.dayOf(w && w[1]);
            if (!a || !b) return '';
            const day = (d, year) => (short ? '' : build.DAYS[d.getDay()] + ' ') + d.getDate() + ' ' + build.MONTHS[d.getMonth()] + (year ? ' ' + d.getFullYear() : '');
            if (kind === 'day') return day(a, !short);
            if (kind === 'week') return (short && a.getMonth() === b.getMonth() ? a.getDate() : day(a, !short && a.getFullYear() !== b.getFullYear())) + ' – ' + day(b, !short);
            if (kind === 'month') return (short ? build.MONTHS : build.MONTHS_LONG)[a.getMonth()] + ' ' + a.getFullYear();
            return String(a.getFullYear());
        },
        nextDay(iso) { const d = build.dayOf(iso); return d ? build.isoDay(new Date(d.getFullYear(), d.getMonth(), d.getDate() + 1)) : ''; },
        // what Run would do on the interval (§14.2): the units in the horizon, those not run yet on this athlete under the current
        // version (a failed run counts as not run), how many are kept, the last complete unit and whether it is run already
        fillPlan(r, kind, athleteId, units) {
            const done = (r.runs || []).filter(x => x.version === r.current_version && ['ran', 'reproduced', 'differed'].includes(x.status) && x.interval === kind && build.subjectId(x) === String(athleteId || ''));
            const has = w => done.some(x => { const win = (x.data || {}).window || []; return win[0] === w[0] && win[1] === w[1]; });
            const toRun = units.filter(w => !has(w));
            const last = units.length ? units[units.length - 1] : null;
            return { kind, units, toRun, kept: units.length - toRun.length, last, lastRun: !!(last && has(last)), done };
        },
        // the windows one press of Run runs: with the fill, every unit not run yet (the last again when nothing is missing); without, the last alone
        fillWindows(plan, fill) { if (!plan || !plan.last) return []; return fill && plan.toRun.length ? plan.toRun : [plan.last]; },
        // the run a set interval is compared with (§14.1): the latest earlier run of the kind on the athlete, by its window's end
        before(plan, w) {
            const earlier = plan.done.filter(x => (((x.data || {}).window || [])[1] || '') < w[0]);
            return earlier.length ? earlier.reduce((a, x) => (x.data.window[1] > a.data.window[1] || (x.data.window[1] === a.data.window[1] && x.number > a.number) ? x : a)) : null;
        },
        tookOf(r) {          // what a run takes, from the last one that ran (or run zero): said before Run, and the fill's cost
            const v = (r.versions || []).find(x => x.number === r.current_version) || {};
            const runs = (r.runs || []).filter(x => x.version === r.current_version && ['ran', 'reproduced', 'differed'].includes(x.status));
            const last = runs.length ? runs[runs.length - 1] : null;
            return Number((last && last.elapsed) || (v.run_zero && v.run_zero.elapsed) || 0);
        },
        // the footer's time (§16.1): a fill's is the units times the last run's time; one run's the last run's (or the check on the
        // original data's); nothing when unknown
        tookLine(r, units) {
            const took = build.tookOf(r);
            if (!(took >= 1)) return '';
            if (units > 1) return 'about ' + fmtTook(units * took);
            const runs = (r.runs || []).filter(x => x.version === r.current_version && ['ran', 'reproduced', 'differed'].includes(x.status));
            return 'the ' + (runs.length ? 'last run' : 'check on the original data') + ' took ' + fmtTook(took);
        },
        lastInterval(r) {    // the interval the routine was last run on under the current version: the dialog opens on it
            const runs = (r.runs || []).filter(x => x.version === r.current_version);
            return runs.length && runs[runs.length - 1].interval ? runs[runs.length - 1].interval : 'custom';
        },
        intervalRow(kind) {
            const names = { day: 'Day', week: 'Week', month: 'Month', year: 'Year', custom: 'Custom' };
            return '<span class="ui-seg rt-interval">' + Object.keys(names).map(k => '<span' + (k === kind ? ' class="on"' : '') + ' data-interval="' + k + '">' + names[k] + '</span>').join('') + '</span>';
        },
        // under the row (§16.1): the last complete unit (never the one under way) and whether it is run, then the box to fill the
        // units not run yet - or that every unit is run already, or that the horizon holds no complete unit
        intervalPlan(plan, maxDays, fill) {
            const one = plan.kind, many = plan.kind + 's';
            if (!plan.last) return '<div class="rt-plan warn">No complete ' + one + ' within the last ' + esc(Math.min(maxDays, 365)) + ' days.</div>';
            const more = plan.toRun.filter(w => w !== plan.last).length;
            let h = '<div class="rt-plan">Last complete ' + one + ': <b>' + esc(build.unitText(one, plan.last, true)) + '</b> <span class="n">— ' + (plan.lastRun ? 'run already' + (more ? '' : '; Run runs it again') : 'not run yet') + '</span></div>';
            if (plan.units.length < 2) return h;
            const back = 'back to ' + esc(build.dateText(plan.units[0][0]));
            if (!more) return h + '<div class="rt-plan"><span class="n">Every ' + one + ' ' + back + ' is run already (' + plan.kept + ' ' + many + ').</span></div>';
            return h + '<label class="rt-check rt-fillbox"><input type="checkbox" data-load="fill"' + (fill ? ' checked' : '') + '> Fill the ' + many + ' ' + back + ' — ' + more + ' not run yet</label>';
        },
        runLabel(plan, fill) {
            const ws = build.fillWindows(plan, fill);
            if (ws.length > 1) return 'Run ' + ws.length + ' ' + plan.kind + 's';
            return ws.length && plan.lastRun && !plan.toRun.length ? 'Run again' : 'Run';
        },
        // the Summary's line while a fill runs (§14.3); its last word, once it has ended, is the toast's
        fillLine(st) {
            if (!st || !st.total) return '';
            const one = st.interval, many = one + 's';
            if (st.running) return 'Filling the ' + many + ' · ' + st.done + ' of ' + st.total + ' done' + (st.failed ? ' (' + st.failed + ' failed)' : '') + (st.current ? ' · ' + build.unitText(one, st.current, true) + ' running' : '') + (st.left != null && st.done ? ' · about ' + fmtTook(st.left) + ' left' : '');
            if (st.stopped) return 'Stopped after ' + st.done + ' of ' + st.total + ' ' + many + (st.error ? ': ' + st.error : '') + (st.failed ? ' · ' + st.failed + ' failed' : '');
            return 'Filled ' + st.total + ' ' + (st.total === 1 ? one : many) + ' in ' + (st.elapsed < 1 ? 'under a second' : fmtTook(st.elapsed)) + (st.failed ? ' · ' + st.failed + ' failed' : '');
        },
        fillBar(st) {
            if (!st || !st.total || !st.running) return '';
            return '<div class="rt-fillbar"><span class="live"></span><span class="t">' + esc(build.fillLine(st)) + '</span><button class="ui-btn sm" data-act="stop-fill">Stop</button></div>';
        },
        // a result's label without what was true of the original data (§14.4): trailing segments that are a date range or a count
        // ("all 380 activities", "n = 380") are dropped; the full label stays on hover
        metricLabel(label) {
            const parts = String(label || '').split(/,\s+/);
            const tail = s => /^\d{4}-\d{2}-\d{2}\s*(?:\.\.|to|→|->|–|-)\s*\d{4}-\d{2}-\d{2}$/.test(s) || /^(?:all\s+\d[\d,]*(?:\s+\S+)?|n\s*=\s*\d[\d,]*)$/i.test(s);
            while (parts.length > 1 && tail(parts[parts.length - 1])) parts.pop();
            return parts.join(', ');
        },
        // how a line is named where it is shown (§15.3): the promoter's name when the manifest has one, else the recorded
        // label trimmed; the recorded label stays on hover
        lineName(line) { return (line && line.name) || build.metricLabel((line || {}).label); },
        // the Data, Athlete and Interval rows (§16.1): the data on one line - the load, or the data loaded now with its dates; for
        // an Intervals routine the athlete and the interval under it (greyed when the data loaded now is picked), the pickers
        // for a custom window; a problem with the data loaded now under the choice, never the green line; nothing else
        dataRows(plan, pre, limits, kind) {
            const d = (pre && pre.data) || {};
            const loaded = !!(pre && pre.loaded);
            const src = (plan && plan.source) || sourceKind(d.source);
            const isLoad = src === 'intervals' || src === 'endura' || src === 'sweatstack';
            const differs = !!(pre && pre.ok && (((pre.fit || {}).missing || []).length || ((pre.aux || {}).absent || []).length || ((pre.fit || {}).retyped || []).length || (pre.values_notes || []).length));
            const fitLine = loaded && (!pre.ok || differs) ? '<div class="rt-fit' + (pre.ok ? ' note' : ' bad') + '" data-for="now"' + (isLoad ? ' style="display:none"' : '') + '>' + (pre.ok ? '△ ' : '! ') + esc(pre.line || '') + '</div>' : '';     // the frame's problems, shown while it is the choice
            const nowWhen = build.windowOf(d).join(' → ') || d.name || '';
            const nowChoice = loaded ? '<label class="rt-check"><input type="radio" name="rt-data" value="now"' + (isLoad ? '' : ' checked') + '> The data loaded now' + (nowWhen ? ' <span class="n">· ' + esc(nowWhen) + '</span>' : '') + '</label>' : '';
            const today = new Date();
            let choices = '', rows = '';
            if (src === 'intervals' || src === 'sweatstack') {
                const days = Math.max(1, Number((plan && plan.window_days) || 28));
                const dw = window.DateWindow && limits ? window.DateWindow.of(limits) : null;      // the plan's reach and window (2026-11-08, docs/DATASETS_DESIGN.md §18)
                const maxDays = dw ? dw.window : null;
                const span = maxDays ? Math.min(days, maxDays) : days;
                const start = new Date(today); start.setDate(today.getDate() - span);       // calendar days back, not 24-hour steps (a clock change would shift the day)
                const bounds = dw ? window.DateWindow.bounds(dw, today) : null, lim = bounds ? ' min="' + esc(bounds.min) + '" max="' + esc(bounds.max) + '"' : '';
                const custom = !kind || kind === 'custom', hide = custom ? '' : ' style="display:none"';
                choices = '<label class="rt-check"><input type="radio" name="rt-data" value="load" checked> Load from ' + (src === 'intervals' ? 'Intervals.icu' : 'SweatStack') + '</label>' + nowChoice;
                if (src === 'intervals') rows += '<div class="rt-row" data-row="athlete"><label>Athlete</label><div><select class="ui-input" data-load="athlete" data-state="loading"><option value="">loading the athletes…</option></select><div class="rt-athlete-help"></div></div></div>';
                rows += '<div class="rt-row" data-row="interval"><label>' + (src === 'intervals' ? 'Interval' : 'Window') + '</label><div>' + (src === 'intervals' ? build.intervalRow(kind || 'custom') + '<div class="rt-interval-plan"></div>' : '') +
                    '<div class="rt-window rt-loadwin rt-custom"' + hide + '><input type="date" class="ui-input" data-load="start"' + lim + ' value="' + build.isoDay(start) + '"><span class="arrow">→</span><input type="date" class="ui-input" data-load="end"' + lim + ' value="' + build.isoDay(today) + '"></div>' +
                    (dw ? '<div class="rt-plan rt-custom"' + hide + '><span class="n">' + esc(window.DateWindow.line(dw, today)) + '</span></div>' : '') + '</div></div>';
            } else if (src === 'endura') {
                choices = '<label class="rt-check"><input type="radio" name="rt-data" value="load" checked> Load from Endura</label>' + nowChoice;
                rows += '<div class="rt-row" data-row="race"><label>Race</label><select class="ui-input" data-load="race"><option value="">loading the races…</option></select></div>';
            } else {
                // a file the Dataset cache holds (step 4, 2026-10-11): the choice and its pick show once the cache has answered with files
                choices = '<label class="rt-check"><input type="radio" name="rt-data" value="upload"' + (loaded ? '' : ' checked') + '> Upload a file</label>' +
                    '<label class="rt-check rt-cachepick" style="display:none"><input type="radio" name="rt-data" value="cache"> A file from the Dataset cache</label>' + nowChoice;
                rows += '<div class="rt-row" data-row="file"><label>File</label><div class="rt-files"><input type="file" class="ui-input" data-load="file" accept=".csv,.parquet,.json,.xlsx,.xls,.txt,.tsv">' +
                    '<select class="ui-input rt-cachepick" data-load="cached" style="display:none"><option value="">choose a file</option></select>' +
                    (loaded ? '' : '<div class="rt-plan"><span class="n">Nothing is loaded now; upload the file to run on.</span></div>') + '</div></div>';
            }
            return '<div class="rt-row" data-row="data" data-source="' + esc(src) + '"><label>Data</label><div><div class="rt-choices">' + choices + '</div>' + fitLine + '</div></div>' + rows;
        },
        // the dialog (§16.1): the rows, the Inputs row when the routine has any (the origin on the label's hover), the Compare
        // row when there is a choice
        runDialog(r, pre, limits, kind) {
            const v = (r.versions || []).find(x => x.number === r.current_version) || (r.versions || [])[(r.versions || []).length - 1] || {};
            const params = (v.manifest || {}).parameters || [];
            let h = build.dataRows((pre && pre.plan) || {}, pre, limits, kind);
            if (params.length) h += '<div class="rt-row" data-row="inputs"><label>Inputs</label><div class="rt-inputs-grid">' +
                params.map(p => '<span class="k"' + (p.origin ? ' title="' + esc(p.origin) + '"' : '') + '>' + esc(p.label) + '</span>' + build.inputWidget(p)).join('') + '</div></div>';
            // whose runs to compare with, as the dialog opens: the original's athlete for a load, the data loaded now's for a file
            // routine with data loaded; the row is re-rendered as the choice or the athlete changes
            const src0 = (pre && pre.plan && pre.plan.source) || '';
            const s0 = (src0 === 'intervals' || src0 === 'endura' || src0 === 'sweatstack') ? ((pre.plan || {}).subject || {}) : (pre && pre.loaded ? (((pre.data || {}).subject) || {}) : {});
            return h + '<div class="rt-compare-sec">' + build.compareSection(r, v, s0.id || '') + '</div>';
        },
        // whose runs a run is compared with (2026-10-30): the previous run on the same athlete's data, and run zero only when it
        // ran on that athlete's; the first run on an athlete has nothing to compare with yet. Re-rendered as the athlete changes.
        subjectId(x) { return String((((x || {}).data || {}).subject || {}).id || ''); },
        zeroSubject(v) { return String((((((v || {}).manifest || {}).data || {}).load || {}).subject || {}).id || ''); },
        zeroFits(v, athleteId) { return athleteId == null || build.zeroSubject(v) === String(athleteId); },   // run zero is that athlete's alone; one naming none (before 2026-10-30) is nobody's but the subject-less runs'
        // the Compare row (§16.1): custom and the data loaded now only, and only with two runs to choose from - the run before
        // on the athlete and run 0 on their data; one choice is no choice and nothing is shown
        compareSection(r, v, athleteId) {
            const mine = (r.runs || []).filter(x => x.version === r.current_version && ['ran', 'reproduced', 'differed'].includes(x.status) && build.subjectId(x) === String(athleteId || ''));
            const last = mine.length ? mine[mine.length - 1] : null;
            const zero = v.run_zero && v.run_zero.verified && build.zeroFits(v, athleteId || '');
            if (!last || !zero) return '';
            return '<div class="rt-row" data-row="compare"><label>Compare</label><div class="rt-choices">' +
                '<label class="rt-check"><input type="radio" name="rt-compare" value="previous" checked> run ' + esc(last.number) + ' (the run before)</label>' +
                '<label class="rt-check"><input type="radio" name="rt-compare" value="zero"> run 0 (the original data)</label></div></div>';
        },
        num(x) { return x == null || x === '' ? '' : String(x); },
        ivl(s) { return s && s.low != null && s.high != null ? '[' + esc(s.low) + ', ' + esc(s.high) + ']' : ''; },
        markText(m) { return ({ up: '↑', down: '↓', same: '=', missing: '·', unreached: '·', changed: '≠' })[m] || ''; },
        markWord(row) {
            if (row.mark === 'missing') return 'missing';
            if (row.mark === 'unreached') return 'not reached';
            if (row.overlap === true) return 'within';
            if (row.overlap === false) return 'moved';
            return row.mark === 'same' ? 'same' : 'changed';
        },
        // whose data a record is on, and when: the athlete's name (the subject on a summary, or the load's on a full record), and the
        // window asked for - else the file or the race (2026-10-30: the Comparison tab says what is compared with what)
        whoOf(d) { const sub = (d || {}).subject || ((d || {}).load || {}).subject || {}; return String(sub.name || sub.id || ''); },
        windowOf(d) {      // a record's window as [start, end]: the summary's, else the load's dates, else the date range; [] without one
            d = d || {}; const ld = d.load || {};
            if (Array.isArray(d.window) && d.window.length === 2 && d.window[0] && d.window[1]) return [d.window[0], d.window[1]];
            if (ld.start_date && ld.end_date) return [ld.start_date, ld.end_date];
            const m = /^\s*(\d{4}-\d{2}-\d{2})\s*(?:to|->|-|→)\s*(\d{4}-\d{2}-\d{2})\s*$/.exec(String(d.date_range || ''));
            return m ? [m[1], m[2]] : [];
        },
        whenOf(d) {
            const w = build.windowOf(d);
            if (w.length) return w[0] + ' → ' + w[1];
            d = d || {};
            return String((d.extra || {}).race_title || (d.load || {}).race_title || d.name || '');
        },
        // the Trend tab (§14.6; the Comparison tab until 2026-11-06): this run against the one before. `series` (a run on a set
        // interval, from the routine's runs): the heads name the units and a last column carries each line's thumbnail over them.
        comparisonTab(view, series) {
            const run = view.run || {}, c = run.comparison || {};
            const d = run.data || {}, ref = view.against_data || null;
            const kind = series && run.interval ? run.interval : '';
            // the heading: both runs and, when the athletes are known, whose - one name when it is the same athlete, each run's when not
            const who = build.whoOf(d), whoRef = ref ? build.whoOf(ref) : '';
            const same = run.against != null && who === whoRef;
            const named = n => n || 'athlete not recorded';
            const head = run.number === 0 ? 'Run 0 — the original data'
                : ('Run ' + esc(run.number) + (run.against != null && !same ? ' (' + esc(named(who)) + ')' : '') + (run.against != null ? ' against run ' + esc(run.against) + (!same ? ' (' + esc(named(whoRef)) + ')' : '') : ''));
            const whose = (run.against == null || same) && who ? esc(who) + ' · ' : '';
            let h = '<div class="rt-cmp"><div class="rt-sec"><div class="h">' + head + ' <span class="n">— ' + whose + 'v' + esc(run.version) + (run.against != null ? ' · ' + esc(c.line || '') : '') + '</span></div>';
            const th = (n, data) => { const when = kind ? build.unitText(kind, build.windowOf(data), true) : build.whenOf(data); return kind && when ? '<th class="num">' + esc(when) + '<span class="when">run ' + esc(n) + '</span></th>' : '<th class="num">Run ' + esc(n) + (when ? '<span class="when">' + esc(when) + '</span>' : '') + '</th>'; };
            const lineOf = x => series ? series.lines.findIndex(l => l.cell === x.cell && l.index === x.index) : -1;       // the comparison's row as the manifest's line, for its thumbnail
            const trendTh = kind ? '<th class="trend">' + esc(build.INTERVAL_NAMES[kind]) + ' trend</th>' : '', trendTd = x => (kind ? '<td class="trend">' + (lineOf(x) >= 0 ? build.thumb(series, lineOf(x)) : '') + '</td>' : '');
            if (run.status === 'failed' || run.status === 'timed_out') {
                // the failed cell's code beside the traceback (step 4, 2026-10-11): what ran, and where it stopped
                const fc = run.failed_cell || null;
                h += '<div class="rt-error"><div class="msg">' + esc(run.line || '') + '</div>' +
                    (fc && fc.code ? '<div class="rt-error-cell"><div class="h">cell ' + esc(fc.number) + ' — the code that failed</div><pre class="ui-code"><code class="language-python">' + esc(fc.code) + '</code></pre></div>' : '') +
                    (run.error ? '<div class="rt-error-tb"><div class="h">the error</div><pre class="ui-code">' + esc(run.error) + '</pre></div>' : '') + '</div>';
            }
            const rows = c.rows || [];
            if (!rows.length) {
                h += '<div class="rt-line">' + (run.number === 0 || run.against == null ? 'Nothing to compare with: the first run of this version. Its results are on the Results tab.' : 'No result line to compare.') + '</div>';
            } else if (run.against == null) {
                // nothing to compare with - the first run on this athlete, or of the version: the record's own line says which
                h += (run.number !== 0 && c.line ? '<div class="rt-line muted">' + esc(c.line) + '</div>' : '') +
                    '<table class="ui-table rt-cmp-table' + (kind ? ' with-trend' : '') + '"><thead><tr><th>Result</th>' + th(run.number, d) + trendTh + '</tr></thead><tbody>' +
                    rows.map(x => '<tr><td class="label" title="' + esc(x.label) + '">' + esc(build.lineName(x)) + '</td><td class="num">' + esc(build.num((x.now || {}).estimate)) + '<div class="ci">' + build.ivl(x.now) + '</div></td>' + trendTd(x) + '</tr>').join('') + '</tbody></table>';
            } else {
                h += '<table class="ui-table rt-cmp-table' + (kind ? ' with-trend' : '') + '"><thead><tr><th>Result</th>' + th(run.against, ref) + th(run.number, d) + '<th class="num">Change</th><th>Intervals</th>' + trendTh + '</tr></thead><tbody>' +
                    rows.map(x => '<tr class="' + esc(x.mark) + '"><td class="label" title="' + esc(x.label) + '">' + esc(build.lineName(x)) + '</td>' +
                        '<td class="num">' + esc(build.num((x.before || {}).estimate)) + '<div class="ci">' + build.ivl(x.before) + '</div></td>' +
                        '<td class="num">' + esc(build.num((x.now || {}).estimate)) + '<div class="ci">' + build.ivl(x.now) + '</div></td>' +
                        '<td class="num change">' + (x.change == null ? '' : esc((x.change > 0 ? '+' : '') + Number(x.change.toPrecision(3)))) + '</td>' +
                        '<td><span class="rt-mark ' + esc(x.mark) + '">' + build.markText(x.mark) + '</span> ' + build.markWord(x) + '</td>' + trendTd(x) + '</tr>').join('') + '</tbody></table>' +
                    '<div class="rt-legend">Estimates with their 95% intervals, as the routine printed them. "moved" means the two intervals do not overlap; "within" means they do; without intervals, "changed" and "same" compare the estimates' + ((c.unreached || 0) ? '; "not reached" is a line the run failed before printing' : '') + (kind ? '. The trend is each line over the ' + kind + 's run on this athlete, oldest to newest' : '') + '. Nothing here is written by a model.</div>';
            }
            return h + '</div></div>';
        },
        dataTab(d, run) {
            const cols = d.columns || [];
            const ld = loadLabel(d.load);
            const subs = (run && run.bindings) || [];
            const absent = (run && run.aux_absent) || [];
            // each recorded file against this load's (run.sources, 2026-10-15: the executed text names the run's mirror of the
            // recorded layout, so the mirror path would only repeat the recorded name); an older record shows the bound path
            const srcOf = x => (run && run.sources && run.sources[x[0]]) || (x[2] === 'placeholder' ? '' : x[1]);
            const files = subs.length ? subs : Object.keys((run && run.sources) || {}).map(k => [k, run.sources[k], 'bound']);
            const bound = files.length ? '<b>Files</b><span>' + files.map(x => esc(String(x[0]).split('/').pop()) + ' → ' + esc(String(srcOf(x)).split('/').pop() || 'an empty table')).join('<br>') + (absent.length ? '<br>' + esc(absent.join(', ')) + ': absent in this data (an empty table stood in)' : '') + '</span>' : (absent.length ? '<b>Files</b><span>' + esc(absent.join(', ')) + ': absent in this data (an empty table stood in)</span>' : '');
            // what differed from the original's data, as the CHECK row said it (step 4, 2026-10-11): one sentence a line
            const diffs = (run && run.differences) || [];
            const differs = diffs.length ? '<b>Differs</b><span class="rt-differs">' + diffs.map(x => esc(x)).join('<br>') + '</span>' : '';
            return '<div class="rt-cmp"><div class="rt-sec"><div class="h">What this run ran on</div><div class="ui-kv">' +
                '<b>Source</b><span>' + esc(sourceLabel(d.source)) + '</span>' + (ld ? '<b>Loaded as</b><span>' + esc(ld) + '</span>' : '') + (d.name ? '<b>Name</b><span>' + esc(d.name) + '</span>' : '') + bound + differs +
                (d.rows != null ? '<b>Rows</b><span>' + esc(Number(d.rows).toLocaleString()) + '</span>' : '') + (d.date_range ? '<b>Range</b><span>' + esc(d.date_range) + '</span>' : '') +
                (d.aux && d.aux.length ? '<b>Auxiliary</b><span>' + d.aux.map(a => esc(String(a).split('/').pop())).join(', ') + '</span>' : '') +
                '<b>Columns</b><span>' + (Array.isArray(cols) && cols.length && typeof cols[0] === 'object' ? cols.map(c => esc(c.name) + (c.dtype ? ' <span class="ui-muted">' + esc(c.dtype) + '</span>' : '')).join(', ') : esc(String(cols))) + '</span></div></div></div>';
        },
        markOf(now, before) {
            if (!now || !before) return 'missing';
            const a = parseFloat(String(now.estimate).replace(/,/g, '')), b = parseFloat(String(before.estimate).replace(/,/g, ''));
            const ia = now.low != null && now.high != null ? [parseFloat(String(now.low).replace(/,/g, '')), parseFloat(String(now.high).replace(/,/g, ''))] : null;
            const ib = before.low != null && before.high != null ? [parseFloat(String(before.low).replace(/,/g, '')), parseFloat(String(before.high).replace(/,/g, ''))] : null;
            if (ia && ib) return (ia[0] > ib[1] || ia[1] < ib[0]) ? (a > b ? 'up' : 'down') : 'same';
            if (isNaN(a) || isNaN(b)) return now.estimate === before.estimate ? 'same' : 'changed';
            return a === b ? 'same' : (a > b ? 'up' : 'down');
        },
        // the custom runs (§14.6): a column per run in the order they were run, each against the one before - not a series, so no
        // trend is drawn across them; the head says the run's day and its window's length, the window itself on hover, and opens
        // the run; the custom runs that failed are named under the table with their reason, each opening too (2026-11-08)
        runsTable(r, athleteId) {
            const v = (r.versions || []).find(x => x.number === r.current_version) || {};
            const lines = ((v.manifest || {}).results || []).filter(x => !x.dropped && x.estimate != null);
            const cols = [];
            const days = d => { const w = build.windowOf(d), a = build.dayOf(w[0]), b = build.dayOf(w[1]); return a && b ? Math.round((b - a) / 86400000) : null; };     // start to end, as the Data tab's pill and the run dialog count a window
            if (v.run_zero && v.run_zero.verified && build.zeroFits(v, athleteId)) cols.push({ number: 0, created: v.run_zero.created, results: v.run_zero.results || [], when: build.whenOf(((v.manifest || {}).data) || {}), days: days(((v.manifest || {}).data) || {}) });
            build.doneRuns(r, athleteId).filter(x => !x.interval).forEach(x => cols.push({ number: x.number, created: x.created, results: x.results || [], when: build.whenOf(x.data || {}), days: days(x.data || {}) }));
            const failed = (r.runs || []).filter(x => x.version === r.current_version && ['failed', 'timed_out'].includes(x.status) && !x.interval && (athleteId == null || build.subjectId(x) === String(athleteId))).reverse();
            const foot = failed.length ? '<div class="rt-foot">' + failed.map(x => '<span class="rt-failed" data-run="' + esc(x.number) + '">run ' + esc(x.number) + ' · ' + esc(fmtDate(x.created)) + ' · ' + esc(x.line || x.status.replace('_', ' ')) + ' <a>open →</a></span>').join('') + '</div>' : '';
            if (!lines.length || !cols.length) return '<div class="rt-line muted">' + (!lines.length ? 'This routine records no result lines; its runs keep their output and figures.' : 'No custom run yet.') + '</div>' + foot;
            const all = ((v.manifest || {}).results || []);
            // the mark sits between the two numbers it compares, in a column of its own (2026-10-10: beside the second number it read as a misplaced Trend)
            const head = '<thead><tr><th>Result</th>' + cols.map((c, i) => (i ? '<th class="mark"></th>' : '') + '<th class="num" data-run="' + esc(c.number) + '" title="' + esc(c.when ? c.when + ' · ' : '') + 'open the run">Run ' + esc(c.number) + '<span class="d">' + esc(fmtDate(c.created)) + (c.days ? ' · ' + esc(c.days) + ' days' : '') + '</span></th>').join('') + '</tr></thead>';
            const body = lines.map(line => {
                const pos = all.indexOf(line);
                const cells = cols.map(c => c.results[pos] || null);
                let tds = '<td class="label" title="' + esc(line.label) + '">' + esc(build.lineName(line)) + '</td>';
                cells.forEach((x, i) => {
                    if (i) {
                        const mark = build.markOf(x, cells[i - 1]);
                        tds += '<td class="mark">' + (mark === 'missing' ? '' : '<span class="rt-mark ' + esc(mark) + '">' + build.markText(mark) + '</span>') + '</td>';
                    }
                    tds += '<td class="num"' + (x ? ' title="' + build.ivl(x).replace(/"/g, '') + '"' : '') + '>' + (x ? build.shown(x.estimate) : '<span class="rt-mark missing">·</span>') + '</td>';
                });
                return '<tr>' + tds + '</tr>';
            }).join('');
            return '<table class="ui-table rt-runs">' + head + '<tbody>' + body + '</tbody></table>' + foot;
        },
        // the favourites' cards' button
        cardButton(n) {
            return '<button class="workflow-card-routine' + (n ? ' has' : '') + '" title="' + (n ? n + ' routine version' + (n === 1 ? '' : 's') + ' made from this analysis — open' : 'Save as routine: a method to run again on new data') + '">' +
                ICON_ROUTINE + '<span class="t">Routine</span>' + (n ? '<span class="n">' + n + '</span>' : '') + '</button>';
        }
    };

    // ------------------------------------------------------------ state
    const originCache = {};            // "thread/chain" -> [{id, name, version}]; "thread" -> [...]
    let menuEl = null, menuTimer = null, menuState = { saved: false, own: [], thread: [] };
    let dialog = null, dialogState = null;
    let manager = null, managerState = { list: [], current: null, athlete: '', interval: '', horizon: 365 };     // athlete: the runs shown in the manager (2026-10-30); interval: the filter picked (§14.6)
    // the horizon a set interval's view spans (§14.6): the plan's day limit, at most a year; asked once per page
    let horizonPromise = null;
    function horizon() {
        if (!horizonPromise) horizonPromise = fetchJson('/intervals/get_data_limits').then(res => Math.min(365, Number((res.json || {}).max_days) || 365)).catch(() => 365);
        return horizonPromise;
    }

    function fetchJson(url, opts) {
        const f = (window.authService && window.authService.fetch) ? window.authService.fetch.bind(window.authService) : fetch;
        return f(url, opts).then(r => r.json().then(j => ({ ok: r.ok, status: r.status, json: j })).catch(() => ({ ok: r.ok, status: r.status, json: {} })));
    }
    // a streaming route: each line is a pane event (forwarded to the pane when `toPane`) or the closing message
    function stream(url, body, toPane, intercept) {
        const f = (window.authService && window.authService.fetch) ? window.authService.fetch.bind(window.authService) : fetch;
        return f(url, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) }).then(async resp => {
            if (!resp.ok) {
                const j = await resp.json().catch(() => ({}));
                throw new Error(j.message || j.error || ('the server answered ' + resp.status));
            }
            const reader = resp.body.getReader(); const dec = new TextDecoder(); let buf = ''; let closing = null;
            const take = typeof intercept === 'function' ? intercept : null;   // messages the caller handles itself (the run's closing card)
            while (true) {
                const { done, value } = await reader.read();
                if (done) break;
                buf += dec.decode(value, { stream: true });
                let i;
                while ((i = buf.indexOf('\n')) >= 0) {
                    const line = buf.slice(0, i).trim(); buf = buf.slice(i + 1);
                    if (!line) continue;
                    let data = null;
                    try { data = JSON.parse(line); } catch (e) { continue; }
                    if (data.routine_proposal || data.routine_made || data.routine_run || data.routine_error) { closing = data; continue; }
                    if (take && take(data)) continue;
                    if (toPane && typeof processChunk === 'function') processChunk(line + '\n');
                }
            }
            if (!closing) throw new Error('the server ended without an answer');
            if (closing.routine_error) throw new Error(closing.routine_error);
            return closing;
        });
    }
    function current() {
        const r = (typeof responses !== 'undefined' && typeof currentResponseIndex !== 'undefined') ? responses[currentResponseIndex] : null;
        const d = (typeof currentData !== 'undefined') ? currentData : {};
        return { response: r, thread_id: (r && r.thread_id) || d.thread_id || null, chain_id: (r && r.chain_id) || d.chain_id || null };
    }
    function toast(text, level) {
        if (typeof showSystemMessage === 'function') showSystemMessage(text); else console.log(text);
        if (level === 'error') console.error(text);
    }
    function origins(threadId, chainId) {
        const key = chainId ? threadId + '/' + chainId : String(threadId);
        if (originCache[key]) return Promise.resolve(originCache[key]);
        return fetchJson('/routines/by_origin/' + encodeURIComponent(threadId) + (chainId ? '/' + encodeURIComponent(chainId) : '')).then(r => {
            originCache[key] = (r.json && r.json.routines) || [];
            return originCache[key];
        }).catch(() => []);
    }
    function forgetOrigins() { Object.keys(originCache).forEach(k => delete originCache[k]); }
    // the thread's routines, one entry each at its latest version (the by_origin index lists every version)
    function uniqueRoutines(list) {
        const by = {};
        (list || []).forEach(x => { if (!by[x.id] || Number(x.version) > Number(by[x.id].version)) by[x.id] = x; });
        return Object.values(by);
    }

    // ------------------------------------------------------------ the Save pill's menu
    function ensureMenu() {
        if (menuEl) return menuEl;
        menuEl = document.createElement('div'); menuEl.className = 'save-menu'; menuEl.id = 'saveMenu'; menuEl.style.display = 'none';
        document.body.appendChild(menuEl);
        menuEl.addEventListener('mouseenter', () => { if (menuTimer) { clearTimeout(menuTimer); menuTimer = null; } });
        menuEl.addEventListener('mouseleave', hideMenuSoon);
        menuEl.addEventListener('click', e => {
            const it = e.target.closest('.it'); if (!it) return;
            const act = it.getAttribute('data-act');
            hideMenu();
            if (act === 'favourite') { if (!it.classList.contains('done')) saveAsFavourite(); }
            else if (act === 'routine') { const c = current(); if (c.thread_id && c.chain_id) openMake(c.thread_id, c.chain_id, { threadRoutines: menuState.thread, fromCard: false }); }
        });
        return menuEl;
    }
    function renderMenu() {
        const m = ensureMenu();
        m.innerHTML = build.menu(menuState);
    }
    function showMenu() {
        const pill = document.getElementById('rankButton'); if (!pill || pill.style.display === 'none') return;
        if (menuTimer) { clearTimeout(menuTimer); menuTimer = null; }
        const c = current();
        menuState = { saved: !!(c.response && c.response.bookmark_type === 'individual'), own: [], thread: [] };
        renderMenu();
        const m = ensureMenu(); m.style.display = '';
        const r = pill.getBoundingClientRect();
        m.style.top = (r.bottom + 6) + 'px'; m.style.right = Math.max(8, window.innerWidth - r.right) + 'px';
        pill.classList.add('menu-open');
        if (c.thread_id && c.chain_id) {
            Promise.all([origins(c.thread_id, c.chain_id), origins(c.thread_id)]).then(([own, thread]) => {
                if (m.style.display === 'none') return;
                menuState.own = own; menuState.thread = thread;
                renderMenu();
            });
        }
    }
    function hideMenu() {
        if (menuTimer) { clearTimeout(menuTimer); menuTimer = null; }
        if (menuEl) menuEl.style.display = 'none';
        const pill = document.getElementById('rankButton'); if (pill) pill.classList.remove('menu-open');
    }
    function hideMenuSoon() {
        if (menuTimer) clearTimeout(menuTimer);
        menuTimer = setTimeout(hideMenu, 220);
    }
    function toggleMenu() { showMenu(); }   // a click opens (it follows the hover that already opened it); closing is leaving, or a click elsewhere
    function saveAsFavourite() {
        // the rank dialog, as before: a chain loaded from favourites has no rank data yet - the stub the stream end makes
        const c = current();
        if (typeof currentRankData !== 'undefined' && !currentRankData && c.chain_id) { try { currentRankData = { chain_id: c.chain_id, theoretical: true }; } catch (e) { /* read-only */ } }
        if (typeof showRankModal === 'function') showRankModal();
    }
    function bindPill() {
        const pill = document.getElementById('rankButton'); if (!pill) return;
        pill.addEventListener('mouseenter', showMenu);
        pill.addEventListener('mouseleave', hideMenuSoon);
        document.addEventListener('click', e => { if (menuEl && menuEl.style.display !== 'none' && !e.target.closest('#saveMenu') && !e.target.closest('#rankButton')) hideMenu(); });
    }

    // ------------------------------------------------------------ the favourite saved silently (Save as routine saves it too)
    async function ensureFavourite(chainId) {
        // the chain in view, saved as a favourite with its pane as it is now (the ROUTINE row included); a chain that
        // is one already is saved again the same way, so the stored pane carries the row too
        const c = current();
        if (!c.response || String(c.chain_id) !== String(chainId)) return false;
        if (typeof saveAllResponsesToFavorites !== 'function') return false;
        try {
            const so = document.getElementById('streamOutput');
            if (so && !(typeof liveState !== 'undefined' && liveState.running && liveState.away)) c.response.streamOutput = so.innerHTML;
            if (typeof localforage !== 'undefined' && typeof responses !== 'undefined') await localforage.setItem('responses', responses);
        } catch (e) { /* the snapshot is a courtesy */ }
        const status = document.createElement('span'), button = document.createElement('button');
        try { await saveAllResponsesToFavorites(null, status, button, chainId); return true; } catch (e) { return false; }
    }

    // ------------------------------------------------------------ the Save-as-routine dialog
    function ensureDialog() {
        if (dialog) return dialog;
        dialog = document.createElement('div'); dialog.id = 'routineMakeModal'; dialog.className = 'modal ui-modal'; dialog.style.display = 'none';
        dialog.innerHTML = build.dialogShell();
        document.body.appendChild(dialog);
        dialog.addEventListener('click', e => {
            if (e.target === dialog || e.target.closest('.ui-dlg-h .x')) { closeMake(); return; }
            const b = e.target.closest('[data-act]'); if (!b) return;
            const act = b.getAttribute('data-act');
            if (act === 'cancel') closeMake();
            else if (act === 'retry') propose();
            else if (act === 'create') create();
        });
        dialog.addEventListener('click', e => {
            const ch = e.target.closest('.rt-version .ui-choice');
            if (ch) { dialog.querySelectorAll('.rt-version .ui-choice').forEach(x => x.classList.toggle('on', x === ch)); syncVersionChoice(); return; }
            const act = e.target.closest('.rt-results [data-line-act]');
            if (act) { lineAct(act.getAttribute('data-line-act'), act.closest('.r')); return; }
            const seg = e.target.closest('.rt-results .ui-seg > span');
            if (seg) {
                seg.parentNode.querySelectorAll('span').forEach(x => x.classList.toggle('on', x === seg));
                const line = lineOf(seg.closest('.r'));
                if (line) line.dropped = seg.getAttribute('data-keep') === '0';
            }
        });
        return dialog;
    }
    // the proposal's line a row of the Results list stands for
    function lineOf(row) {
        const st = dialogState;
        return st && st.proposal && row ? (st.proposal.results || [])[Number(row.getAttribute('data-line'))] : null;
    }
    // keep / drop move a line between the compared list and the set-aside group; more unfolds the group (§15.2)
    function lineAct(act, row) {
        const st = dialogState; if (!st || !st.proposal || st.busy) return;
        if (act === 'more') st.asideOpen = !st.asideOpen;
        else { const line = lineOf(row); if (!line) return; line.dropped = act === 'drop'; }
        const sec = dialogParts().d.querySelector('.rt-sec[data-sec="results"]');
        if (sec) sec.innerHTML = build.resultsSection(st.proposal, !!st.asideOpen);
    }
    function dialogParts() {
        const d = ensureDialog();
        return { d, sub: d.querySelector('.ui-dlg-h .sub'), body: d.querySelector('.ui-dlg-b'), note: d.querySelector('.ui-dlg-f .note'), createBtn: d.querySelector('[data-act="create"]'), cancelBtn: d.querySelector('[data-act="cancel"]') };
    }
    function versionChoice() {
        const onEl = dialog && dialog.querySelector('.rt-version .ui-choice.on');
        return onEl ? onEl.getAttribute('data-version') : null;
    }
    // the button, the note, the What-changed line and the name follow the version choice (2026-10-12); a name the person
    // typed stays, the two defaults swap
    function syncVersionChoice() {
        const st = dialogState; if (!st || !st.proposal) return;
        const p = dialogParts();
        const under = build.underOf(st.proposal, st.threadRoutines);
        const vs = build.versionState(versionChoice(), under, st.proposal);
        p.createBtn.querySelector('span').textContent = vs.label;
        p.note.textContent = vs.note;
        const f = p.d.querySelector('.rt-change'); if (f) f.style.display = vs.change ? '' : 'none';
        const nameEl = p.d.querySelector('[data-field="name"]');
        if (nameEl) {
            const defaults = [st.proposal.name, under ? under.routine.name : ''].filter(Boolean);
            if (!nameEl.value.trim() || defaults.includes(nameEl.value.trim())) nameEl.value = vs.name;
        }
    }
    function openMake(threadId, chainId, opts) {
        dialogState = { thread_id: threadId, chain_id: chainId, threadRoutines: uniqueRoutines((opts && opts.threadRoutines) || []), fromCard: !!(opts && opts.fromCard), proposal: null, busy: false };
        const p = dialogParts();
        p.d.style.display = 'flex';
        p.sub.textContent = 'from this chain';
        p.note.textContent = '';
        p.createBtn.style.display = 'none';
        if (!dialogState.threadRoutines.length) {
            origins(threadId).then(list => { if (dialogState && String(dialogState.chain_id) === String(chainId)) dialogState.threadRoutines = uniqueRoutines(list); });
        }
        propose();
    }
    function closeMake() {
        if (dialogState && dialogState.busy) return;
        if (dialogState) clearInterval(dialogState.stepTimer);
        const p = dialogParts(); p.d.style.display = 'none'; dialogState = null;
    }
    // the steps as the server says them (§17): a routine_step line moves a step to running or done; the step before a running
    // one is done; the running step's clock ticks on the page
    function stepLanded(st, data) {
        const key = data.step, state = data.state === 'running' ? 'running' : 'done';
        const order = build.STEPS.map(x => x[0]);
        if (!order.includes(key)) return;
        order.slice(0, order.indexOf(key)).forEach(k => { if (!st.steps[k] || st.steps[k].state !== 'done') st.steps[k] = Object.assign({}, st.steps[k], { state: 'done' }); });
        st.steps[key] = { state, detail: data.detail || '', again: !!data.again, since: state === 'running' ? Date.now() : null };
        if (key === 'chain' && data.detail) dialogParts().sub.textContent = 'from this chain · ' + data.detail;
        renderSteps(st);
    }
    function renderSteps(st) {
        const p = dialogParts();
        if (dialogState !== st || st.proposal) return;
        p.body.innerHTML = build.steps(st.steps, Date.now());
    }
    function propose() {
        const st = dialogState; if (!st) return;
        const p = dialogParts();
        st.busy = true; st.proposal = null;
        st.steps = { chain: { state: 'running', since: Date.now() } };
        renderSteps(st);
        clearInterval(st.stepTimer);
        st.stepTimer = setInterval(() => { if (dialogState !== st || st.proposal) { clearInterval(st.stepTimer); return; } renderSteps(st); }, 1000);
        p.createBtn.style.display = 'none';
        p.cancelBtn.disabled = true;
        stream('/routines/propose', { thread_id: st.thread_id, chain_id: st.chain_id }, !st.fromCard, data => {
            if (data.type === 'routine_step') { if (dialogState === st) stepLanded(st, data); return true; }
            return false;
        }).then(msg => {
            if (dialogState !== st) return;
            clearInterval(st.stepTimer);
            st.busy = false; p.cancelBtn.disabled = false;
            st.proposal = msg.routine_proposal;
            const pr = st.proposal;
            const under = st.threadRoutines;
            p.sub.textContent = 'from this chain · ' + pr.cells + ' cell' + (pr.cells === 1 ? '' : 's') + ' · ' + (pr.results || []).length + ' result' + ((pr.results || []).length === 1 ? '' : 's') + (pr.figures && pr.figures.count ? ' · ' + pr.figures.count + ' figure' + (pr.figures.count === 1 ? '' : 's') : '') + (pr.cost ? ' · $' + Number(pr.cost).toFixed(2) : '');
            p.body.innerHTML = build.proposal(pr, under);
            p.createBtn.style.display = '';
            p.createBtn.disabled = false;
            syncVersionChoice();
        }).catch(err => {
            if (dialogState !== st) return;
            clearInterval(st.stepTimer);
            st.busy = false; p.cancelBtn.disabled = false;
            p.body.innerHTML = build.error(err.message || String(err), true);
        });
    }
    function readChoices() {
        const st = dialogState, p = dialogParts();
        const under = build.underOf(st.proposal, st.threadRoutines);
        const nextOn = !!(under && versionChoice() === 'next');
        const field = n => { const el = p.d.querySelector('[data-field="' + n + '"]'); return el ? el.value.trim() : ''; };
        return {
            proposal_id: st.proposal.proposal_id, name: field('name') || (nextOn ? under.routine.name : st.proposal.name), purpose: field('purpose'),
            drop_inputs: Array.from(p.d.querySelectorAll('input[data-drop]:checked')).map(x => x.getAttribute('data-drop')),
            drop_results: (st.proposal.results || []).filter(r => r.dropped).map(r => [r.cell, r.index]),     // the whole set left out of the comparison: the pick with the person's changes (§15.2)
            change_note: nextOn ? field('change_note') : '', routine_id: nextOn ? under.routine.id : null
        };
    }
    function create() {
        const st = dialogState; if (!st || !st.proposal || st.busy) return;
        const p = dialogParts();
        const choices = readChoices();
        st.busy = true;
        p.createBtn.disabled = true; p.cancelBtn.disabled = true;
        p.createBtn.querySelector('span').textContent = 'Checking on this chain’s data…';
        stream('/routines/create', choices, !st.fromCard).then(async msg => {
            if (dialogState !== st) return;
            const made = msg.routine_made;
            st.busy = false;
            forgetOrigins();
            p.d.style.display = 'none'; dialogState = null;
            const name = made.name || choices.name;
            const rz = made.run_zero || {};
            toast('Routine made: ' + name + ' · v' + made.version + (rz.verified ? ' · verified on the original data' : (rz.status === 'verifying' ? ' · verifying on the original data in the background' : ' · not verified')));
            if (rz.status === 'verifying' && made.routine && made.routine.id) watchVerification(made.routine.id, name, made.version);
            if (!st.fromCard) await ensureFavourite(st.chain_id);
            if (typeof updateRankButtonVisibility === 'function') updateRankButtonVisibility();
            if (manager && manager.style.display !== 'none') loadManager(made.routine && made.routine.id);
            if (window.WorkflowModal && typeof window.WorkflowModal.refresh === 'function') window.WorkflowModal.refresh();
        }).catch(err => {
            if (dialogState !== st) return;
            st.busy = false; p.cancelBtn.disabled = false;
            p.createBtn.querySelector('span').textContent = 'Create routine'; p.createBtn.style.display = 'none';
            p.body.innerHTML = build.error(err.message || String(err), true);
        });
    }

    // ------------------------------------------------------------ the manager
    function ensureManager() {
        if (manager) return manager;
        manager = document.createElement('div'); manager.id = 'routinesModal'; manager.className = 'routines-modal-container ui-modal-plain'; manager.style.display = 'none';
        manager.innerHTML = build.managerShell();
        document.body.appendChild(manager);
        manager.addEventListener('click', async e => {
            if (e.target === manager) { closeManager(); return; }
            if (e.target.closest('.ui-dlg-h .x')) { closeManager(); return; }
            const it = e.target.closest('.rt-side .it');
            if (it) { showRoutine(it.getAttribute('data-id')); return; }
            const origin = e.target.closest('.rt-origin');
            if (origin) {
                e.preventDefault();
                const t = origin.getAttribute('data-thread'), c = origin.getAttribute('data-chain');
                closeManager();
                if (typeof loadThreadContent === 'function') loadThreadContent(t, c);
                return;
            }
            const runItem = e.target.closest('.rt-by tr[data-run], .rt-runs th[data-run], .rt-failed[data-run]');     // the table's rows are the runs (2026-11-08)
            if (runItem && managerState.current && !e.target.closest('.rt-thumb')) { const n = Number(runItem.getAttribute('data-run')); closeManager(); viewRun(managerState.current.id, n); return; }
            const fillLink = e.target.closest('.rt-foot [data-act="fill"]');
            if (fillLink && managerState.current) { openRun(managerState.current.id, { interval: fillLink.getAttribute('data-kind') }); return; }
            const filter = e.target.closest('.rt-filter [data-filter]');          // the interval shown (§14.6); one never run is greyed and inert
            if (filter) { if (!filter.classList.contains('off') && managerState.current) { managerState.interval = filter.getAttribute('data-filter'); renderManagerBody(); } return; }
            const thumb = e.target.closest('.rt-thumb[data-line]');
            if (thumb && managerState.current) { openTrend(Number(thumb.getAttribute('data-line'))); return; }
            const b = e.target.closest('[data-act]'); if (!b || !managerState.current) return;
            const r = managerState.current;
            if (b.getAttribute('data-act') === 'run') { openRun(r.id); return; }
            if (b.getAttribute('data-act') === 'stop-fill') {            // the unit under way finishes, nothing more starts (§14.3)
                b.disabled = true;
                const res = await fetchJson('/routines/fill/stop', { method: 'POST' });
                if (res.ok && res.json.fill && res.json.fill.running) toast('Stopping after the ' + res.json.fill.interval + ' under way…');
                return;
            }
            if (b.getAttribute('data-act') === 'delete') {
                if (fillRunning() && fillFor(r.id)) { toast('A fill is running on this routine; stop it first.'); return; }
                if (!confirm('Delete the routine “' + r.name + '” and its runs? The analysis it was made from stays in Saved workflows.')) return;
                const res = await fetchJson('/routines/' + encodeURIComponent(r.id), { method: 'DELETE' });
                if (res.ok) { forgetOrigins(); toast('Routine deleted'); loadManager(); if (window.WorkflowModal && typeof window.WorkflowModal.refresh === 'function') window.WorkflowModal.refresh(); }
            } else if (b.getAttribute('data-act') === 'rename') {
                const name = prompt('Rename the routine', r.name);
                if (!name || name.trim() === r.name) return;
                const res = await fetchJson('/routines/' + encodeURIComponent(r.id) + '/rename', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ name: name.trim() }) });
                if (res.ok) { forgetOrigins(); loadManager(r.id); }
            }
        });
        manager.addEventListener('change', e => {                // whose runs (2026-10-30): the table and the list follow the pick
            const pick = e.target.closest('select[data-pick="athlete"]'); if (!pick || !managerState.current) return;
            managerState.athlete = pick.value;
            renderManagerBody();
        });
        return manager;
    }
    function openManager(routineId) {
        const m = ensureManager();
        m.style.display = 'flex';
        loadManager(routineId);
    }
    function closeManager() { if (manager) manager.style.display = 'none'; }
    function loadManager(routineId) {
        const m = ensureManager();
        const side = m.querySelector('.rt-side'), body = m.querySelector('.rt-body'), title = m.querySelector('.rt-right .title'), sub = m.querySelector('.rt-right .sub'), actions = m.querySelector('.rt-actions');
        side.innerHTML = '<div class="rt-line muted">Loading…</div>';
        return fetchJson('/routines').then(res => {
            managerState.list = (res.json && res.json.routines) || [];
            if (!managerState.list.length) {
                side.innerHTML = ''; title.textContent = 'Routines'; sub.textContent = ''; actions.innerHTML = ''; body.innerHTML = build.empty(); managerState.current = null; return;
            }
            const want = routineId || (managerState.current && managerState.current.id) || managerState.list[0].id;
            const pick = managerState.list.find(r => r.id === want) ? want : managerState.list[0].id;
            side.innerHTML = managerState.list.map(r => build.sideItem(r, r.id === pick)).join('');
            return showRoutine(pick);
        }).catch(err => { side.innerHTML = ''; body.innerHTML = build.error('The routines could not be loaded: ' + (err.message || err), false); });
    }
    function showRoutine(id) {
        const m = ensureManager();
        const body = m.querySelector('.rt-body'), title = m.querySelector('.rt-right .title'), sub = m.querySelector('.rt-right .sub'), actions = m.querySelector('.rt-actions');
        m.querySelectorAll('.rt-side .it').forEach(x => x.classList.toggle('on', x.getAttribute('data-id') === id));
        return Promise.all([fetchJson('/routines/' + encodeURIComponent(id)), horizon()]).then(([res, h]) => {
            if (!res.ok) { body.innerHTML = build.error('This routine could not be loaded.', false); return; }
            const r = res.json.routine; managerState.current = r; managerState.horizon = h;
            const hd = build.routineHeader(r);
            title.innerHTML = hd.title; sub.innerHTML = hd.sub; actions.innerHTML = build.actions(r, fillState);
            renderManagerBody();
        });
    }
    function renderManagerBody() {
        const r = managerState.current; if (!manager || !r) return;
        manager.querySelector('.rt-body').innerHTML = build.routineBody(r, fillFor(r.id), { horizon: managerState.horizon });
    }
    // the series the manager shows (§14.6): the interval and athlete picked, over the horizon's units; null under Custom
    function managerSeries() {
        const r = managerState.current; if (!r) return null;
        const athletes = build.runAthletes(r), many = athletes.length > 1;
        const athleteId = many ? (athletes.find(a => a.id === managerState.athlete) ? managerState.athlete : athletes[0].id) : null;
        const counts = build.intervalCounts(r, athleteId);
        const kind = counts[managerState.interval] ? managerState.interval : build.openInterval(r, athleteId);
        return kind === 'custom' ? null : { series: build.series(r, kind, athleteId, build.units(kind, new Date(), managerState.horizon)), athlete: (athletes.find(a => a.id === athleteId) || {}).name || '' };
    }

    // ------------------------------------------------------------ the enlarged chart (§14.6): a thumbnail at full size, on a calendar axis
    let trendDlg = null, trendState = null;
    function ensureTrendDialog() {
        if (trendDlg) return trendDlg;
        trendDlg = document.createElement('div'); trendDlg.id = 'routineTrendModal'; trendDlg.className = 'modal ui-modal'; trendDlg.style.display = 'none';
        trendDlg.innerHTML = '<div class="modal-content ui-dlg routine-dlg trend-dlg">' +
            '<div class="ui-dlg-h"><div><div class="title"></div><div class="sub"></div><div class="rt-keys"></div></div><span class="sp"></span>' +
            '<span class="ui-seg rt-months"><span data-months="3">3 m</span><span data-months="6">6 m</span><span class="on" data-months="12">12 m</span></span>' +
            '<select class="ui-input rt-also" title="a second line, on the right axis"></select><button class="ui-btn ghost" data-act="png" title="the chart as a picture">' + ICON_DOWN + 'PNG</button><button class="x" aria-label="Close">×</button></div>' +
            '<div class="ui-dlg-b rt-trend"></div><div class="ui-dlg-f"><span class="note"></span></div></div>';
        document.body.appendChild(trendDlg);
        trendDlg.addEventListener('click', e => {
            if (e.target === trendDlg || e.target.closest('.ui-dlg-h .x')) { closeTrend(); return; }
            const m = e.target.closest('.rt-months [data-months]');
            if (m && trendState) { trendState.months = Number(m.getAttribute('data-months')); renderTrend(); return; }
            if (e.target.closest('[data-act="png"]')) savePng();
        });
        trendDlg.addEventListener('change', e => { if (e.target.closest('.rt-also') && trendState) { trendState.also = Number(e.target.value); renderTrend(); } });
        return trendDlg;
    }
    function closeTrend() { if (trendDlg) trendDlg.style.display = 'none'; trendState = null; }
    function chartColors() {
        const css = getComputedStyle(document.documentElement), v = (n, d) => (css.getPropertyValue(n) || '').trim() || d;
        return { text: v('--text-tertiary', '#9aa3ad'), grid: v('--border-color', '#2a3038'), line: v('--c-model', '#2ecc71'), also: v('--c-kernel', '#5dade2'), box: v('--text-quaternary', '#6b7480') };
    }
    function openTrend(line) {
        const ms = managerSeries(); if (!ms || !ms.series.lines[line]) return;
        trendState = { series: ms.series, athlete: ms.athlete, line, months: 12, also: -1 };
        const d = ensureTrendDialog();
        d.querySelectorAll('.rt-months [data-months]').forEach(el => el.classList.toggle('on', el.getAttribute('data-months') === '12'));
        d.querySelector('.rt-also').innerHTML = '<option value="-1">also show: none</option>' + ms.series.lines.map((l, i) => (i === line ? '' : '<option value="' + i + '">' + esc(build.lineName(l)) + '</option>')).join('');
        d.style.display = 'flex';
        renderTrend();
    }
    function renderTrend() {
        const st = trendState; if (!st) return;
        const d = ensureTrendDialog(), s = st.series, one = s.kind;
        d.querySelector('.title').textContent = build.lineName(s.lines[st.line]);
        d.querySelector('.sub').textContent = 'by ' + one + (st.athlete ? ' · ' + st.athlete : '') + ' · the latest ' + st.months + ' months';
        d.querySelectorAll('.rt-months [data-months]').forEach(el => el.classList.toggle('on', Number(el.getAttribute('data-months')) === st.months));
        const colors = chartColors(), two = st.also != null && st.also >= 0 && st.also !== st.line;
        d.querySelector('.rt-trend').innerHTML = build.trendChart(s, st.line, st.months, st.also, colors);
        d.querySelector('.rt-keys').innerHTML = build.trendKeys(s, st.line, two ? st.also : -1, colors);     // which line is which, and its scale (0266)
        d.querySelector('.ui-dlg-f .note').textContent = two ? 'The two lines are on different scales — compare their shapes, not their heights.' : '';
        d.querySelector('.ui-dlg-f').classList.toggle('off', !two);
    }
    function savePng() {
        const svg = trendDlg && trendDlg.querySelector('.rt-chart'); if (!svg) return;
        const xml = new XMLSerializer().serializeToString(svg), img = new Image();
        img.onload = () => {
            const c = document.createElement('canvas'); c.width = 2360; c.height = 720;
            const ctx = c.getContext('2d'); ctx.fillStyle = (getComputedStyle(document.documentElement).getPropertyValue('--bg-secondary') || '#fff').trim() || '#fff'; ctx.fillRect(0, 0, c.width, c.height); ctx.drawImage(img, 0, 0, c.width, c.height);
            const a = document.createElement('a'); a.download = (trendState ? build.lineName(trendState.series.lines[trendState.line]).replace(/[^A-Za-z0-9]+/g, '_') : 'trend') + '.png'; a.href = c.toDataURL('image/png'); a.click();
        };
        img.src = 'data:image/svg+xml;charset=utf-8,' + encodeURIComponent(xml);
    }

    // ------------------------------------------------------------ the run dialog (S3, the data loaded now)
    let runDlg = null, runState = null;
    function ensureRunDialog() {
        if (runDlg) return runDlg;
        runDlg = document.createElement('div'); runDlg.id = 'routineRunModal'; runDlg.className = 'modal ui-modal'; runDlg.style.display = 'none';
        runDlg.innerHTML = '<div class="modal-content ui-dlg routine-dlg run-dlg">' +
            '<div class="ui-dlg-h"><div><div class="title">Run</div><div class="sub"></div></div><span class="sp"></span><button class="x" aria-label="Close">×</button></div>' +
            '<div class="ui-dlg-b"></div><div class="rt-progress" style="display:none"></div>' +         // the load's band (§16.2): under the body, in view whatever the body scrolls
            '<div class="ui-dlg-f"><span class="note"></span><span class="sp"></span><button class="ui-btn" data-act="cancel">Cancel</button><button class="ui-btn primary" data-act="run">' + ICON_ROUTINE + '<span>Run</span></button></div></div>';
        document.body.appendChild(runDlg);
        runDlg.addEventListener('click', e => {
            if (e.target === runDlg || e.target.closest('.ui-dlg-h .x')) { closeRun(); return; }
            const seg = e.target.closest('.rt-interval [data-interval]');
            if (seg) { intervalChanged(seg.getAttribute('data-interval')); return; }
            const b = e.target.closest('[data-act]'); if (!b) return;
            if (b.getAttribute('data-act') === 'cancel') closeRun();
            else if (b.getAttribute('data-act') === 'run') startRun();
        });
        runDlg.addEventListener('change', e => {
            if (e.target.matches('input[name="rt-data"]') || e.target.matches('input[data-load="file"]') || e.target.matches('select[data-load="cached"]')) {
                if (e.target.matches('input[data-load="file"]')) { const up = runDlg.querySelector('input[name="rt-data"][value="upload"]'); if (up) up.checked = true; }
                if (e.target.matches('select[data-load="cached"]')) { const ck = runDlg.querySelector('input[name="rt-data"][value="cache"]'); if (ck) ck.checked = true; }
                renderInterval();                                 // a set interval belongs to the load; the data loaded now is custom
                updateRunButton();
                renderCompare();                                  // whose runs to compare with follows the data choice (2026-10-30)
            }
            if (e.target.matches('input[data-load="fill"]')) updateRunButton();                 // the units to run follow the box: the button and the time
            if (e.target.matches('select[data-load="athlete"]')) athleteChanged();
        });
        runDlg.addEventListener('input', e => {                   // which end of a custom window was set last: the other one moves when the window is over the plan's (2026-11-08)
            if (e.target.matches('input[data-load="start"], input[data-load="end"]') && runState) runState.lastChanged = e.target.getAttribute('data-load');
        });
        return runDlg;
    }
    function runParts() {
        const d = ensureRunDialog();
        return { d, sub: d.querySelector('.ui-dlg-h .sub'), title: d.querySelector('.ui-dlg-h .title'), body: d.querySelector('.ui-dlg-b'), runBtn: d.querySelector('[data-act="run"]'), cancelBtn: d.querySelector('[data-act="cancel"]') };
    }
    function openRun(routineId, opts) {
        if (typeof queryRunning !== 'undefined' && queryRunning) { toast('An analysis is running; run the routine when it has finished.'); return; }
        if (fillRunning()) { toast('A fill is running (' + build.fillLine(fillState) + '); run the routine when it has ended, or stop it in the Summary.'); return; }
        runState = { id: routineId, routine: null, pre: null, busy: false, interval: 'custom' };
        const p = runParts();
        p.d.style.display = 'flex'; p.title.textContent = 'Run'; p.sub.textContent = ''; p.body.innerHTML = build.loading('Reading the routine and checking the data loaded now…');
        progress('');
        p.runBtn.disabled = true; p.cancelBtn.disabled = false;             // Cancel was held while the last run started
        Promise.all([fetchJson('/routines/' + encodeURIComponent(routineId)), fetchJson('/routines/' + encodeURIComponent(routineId) + '/precheck', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: '{}' })]).then(([rr, pr]) => {
            if (!runState || runState.id !== routineId) return;
            if (!rr.ok) { p.body.innerHTML = build.error('This routine could not be loaded.', false); return; }
            runState.routine = rr.json.routine; runState.pre = pr.ok ? pr.json : { loaded: false, ok: false, line: (pr.json && pr.json.error) || 'the check could not run' };
            runState.plan = (runState.pre && runState.pre.plan) || {};
            const r = runState.routine;
            p.title.textContent = 'Run: ' + r.name; p.sub.textContent = 'v' + r.current_version + ' · ' + (r.runs || []).length + ' run' + ((r.runs || []).length === 1 ? '' : 's') + ' so far';
            const src = runState.plan.source || 'file';
            if (src === 'intervals') runState.interval = (opts && opts.interval) || build.lastInterval(r);       // the dialog opens on the interval the routine was last run on (§14.2), or the one asked (the Summary's gap line)
            const after = limits => {
                if (!runState || runState.id !== routineId) return;
                runState.limits = limits || null;
                p.body.innerHTML = build.runDialog(r, runState.pre, limits, runState.interval);
                if (src === 'intervals') { renderInterval(); fillAthletes(p, runState.plan); }
                if (src === 'endura') fillRaces(p, runState.plan);
                if (src !== 'intervals' && src !== 'endura' && src !== 'sweatstack') fillCachePick(p);
                updateRunButton();
            };
            // the window a plan allows (Intervals): the dialog's default window is clamped to it, as the Data tab's is
            if (src === 'intervals') fetchJson('/intervals/get_data_limits').then(res => after(res.ok ? res.json : null)).catch(() => after(null));
            else after(null);
        }).catch(err => { if (runState && runState.id === routineId) p.body.innerHTML = build.error(err.message || String(err), false); });
    }
    // the load the dialog asks for, as the page will do it (the run's record says so; a cached load would otherwise read 'cache')
    function loadAsked(plan, p) {
        const q = sel => p.d.querySelector(sel);
        const src = (plan || {}).source;
        if (src === 'intervals') {
            const a = athletePicked(p);                           // whose data (2026-10-30): on the load, the cache question and the record
            const span = intervalSpan(p);                         // a set interval (§14.2): the span its windows cover, loaded once; custom: the window as typed
            return Object.assign({ source: 'intervals', start_date: span ? span.start : q('input[data-load="start"]').value, end_date: span ? span.end : q('input[data-load="end"]').value, metrics: plan.metrics || [], aux_kinds: plan.aux_kinds || [] }, a.id ? { subject: { source: 'intervals', id: a.id, name: a.name } } : {});
        }
        if (src === 'endura') { const race = q('select[data-load="race"]'); return { source: 'endura', race_id: race ? race.value : '', race_title: race && race.selectedIndex >= 0 ? race.options[race.selectedIndex].textContent : '', aux_kinds: plan.aux_kinds || [] }; }
        if (src === 'sweatstack') return { source: 'sweatstack', start_date: q('input[data-load="start"]').value, end_date: q('input[data-load="end"]').value, sports: plan.sports || [], metrics: plan.metrics || [], users: plan.users || [] };
        const pick = q('select[data-load="cached"]');
        if (dataChoice() === 'cache' && pick && pick.value) return { source: 'file', name: pick.options[pick.selectedIndex].getAttribute('data-name') || '', cached: true };
        const f = q('input[data-load="file"]');
        return { source: 'file', name: f && f.files && f.files.length ? f.files[0].name : '' };
    }
    // the athletes a run can load (2026-10-30, docs/DATASETS_DESIGN.md §17 step 3): those with a key, as the paperclip's
    // roster (the last loaded first), each with what the store holds for them; the original's athlete picked when listed -
    // listed even without a key, since a window the cache holds still runs - else the first
    function fillAthletes(p, plan) {
        const sel = p.d.querySelector('select[data-load="athlete"]'); if (!sel) return;
        const st = runState;
        Promise.all([fetchJson('/intervals/athletes'), fetchJson('/cache/inspect').catch(() => ({ ok: false }))]).then(([ra, rc]) => {
            if (runState !== st || !p.d.contains(sel)) return;
            const keyed = ((ra.ok && ra.json && ra.json.athletes) || []).filter(a => a.id);
            const tree = rc && rc.ok && rc.json ? rc.json.tree : null;
            const rows = typeof intervalsRosterOf === 'function' ? intervalsRosterOf(keyed, tree) : keyed.map(a => ({ id: String(a.id), name: a.name || '', count: 0 }));
            const mine = (plan && plan.subject) || {};
            if (mine.id && !rows.some(a => a.id === mine.id)) rows.push({ id: mine.id, name: mine.name || '', count: 0, nokey: true });
            if (!rows.length) { sel.innerHTML = '<option value="">no athlete: add an athlete’s API key under Settings → Intervals ICU</option>'; sel.setAttribute('data-state', 'none'); athleteChanged(); updateRunButton(); return; }
            const pick = rows.some(a => a.id === mine.id) ? mine.id : rows[0].id;
            sel.innerHTML = rows.map(a => '<option value="' + esc(a.id) + '" data-name="' + esc(a.name || a.id) + '"' + (a.id === pick ? ' selected' : '') + (a.nokey ? ' data-nokey="1"' : '') + '>' + esc(a.name || a.id) + ' · ' + esc(athleteFacts(a)) + '</option>').join('');
            sel.setAttribute('data-state', 'ready');              // Run waits for this: a load before the athletes are listed would take whichever key was used last
            athleteChanged();
            updateRunButton();
        }).catch(() => { if (runState === st) { sel.innerHTML = '<option value="">the athletes could not be listed</option>'; sel.setAttribute('data-state', 'failed'); updateRunButton(); } });
    }
    function athleteFacts(a) {
        if (a.nokey) return 'no key: a window the cache holds only';
        if (a.count) return Number(a.count).toLocaleString() + ' activit' + (Number(a.count) === 1 ? 'y' : 'ies') + ' to ' + (a.to || '');
        return 'nothing held yet';
    }
    // the athlete picked for a load, as the load and the record name them: {id, name}; {} when none is listed or the plan is not Intervals
    function athletePicked(p) {
        const sel = p.d.querySelector('select[data-load="athlete"]');
        if (!sel || !sel.value) return {};
        const o = sel.options[sel.selectedIndex];
        return { id: sel.value, name: (o && o.getAttribute('data-name')) || sel.value };
    }
    // whose data the run will be on, by the data choice: the athlete picked for a load, the data loaded now's subject, none for a file
    function runSubject(p) {
        const c = dataChoice();
        if (c === 'load') return athletePicked(p);
        if (c === 'now') return (((runState && runState.pre && runState.pre.data) || {}).subject) || {};
        return {};
    }
    function athleteChanged() {
        // the athlete changed (or came): the help line under the select, the comparison offered and the cache line follow
        const st = runState; if (!st || !st.routine) return;
        const p = runParts();
        const help = p.d.querySelector('.rt-athlete-help');
        if (help) {
            const sel = p.d.querySelector('select[data-load="athlete"]');
            const o = sel && sel.selectedIndex >= 0 ? sel.options[sel.selectedIndex] : null;
            help.textContent = o && o.getAttribute('data-nokey') ? 'no key stored for them: a window the cache holds runs; anything else needs the key under Settings → Intervals ICU' : '';
        }
        renderInterval();                                     // the units not run yet are this athlete's
        renderCompare();
    }
    function renderCompare() {
        const st = runState; if (!st || !st.routine) return;
        const p = runParts(); const box = p.d.querySelector('.rt-compare-sec'); if (!box) return;
        const r = st.routine, v = (r.versions || []).find(x => x.number === r.current_version) || {};
        const s = runSubject(p);
        const plan = intervalPlan();
        box.innerHTML = plan ? '' : build.compareSection(r, v, s.id || '');
    }
    // ---- the interval (§14.2): the plan under the row follows the kind, the athlete and the fill box; the load, the cache
    // question, the comparison and the button follow the plan
    function intervalPlan() {
        const st = runState; if (!st || !st.routine || dataChoice() !== 'load' || !st.interval || st.interval === 'custom') return null;
        const p = runParts();
        const maxDays = Math.min(365, Number((st.limits || {}).max_days) || 365);       // the plan's horizon, at most a year back
        return build.fillPlan(st.routine, st.interval, athletePicked(p).id || '', build.units(st.interval, new Date(), maxDays));
    }
    function fillOn(p) { const b = p.d.querySelector('input[data-load="fill"]'); return !b || b.checked; }
    function intervalSpan(p) {
        const plan = intervalPlan(); if (!plan) return null;
        const ws = build.fillWindows(plan, fillOn(p));
        return ws.length ? { start: ws[0][0], end: ws[ws.length - 1][1], windows: ws } : { start: '', end: '', windows: [] };
    }
    // the rows that follow the data choice (§16.1): the frame's problems show while the frame is the choice; for an Intervals
    // routine the plan under the interval follows the kind, the athlete and the fill box, and the Athlete and Interval rows grey
    // out when the data loaded now is picked (it runs as it is: the athlete and the interval are the load's)
    function renderInterval() {
        const st = runState; if (!st || !st.routine) return;
        const p = runParts(), choice = dataChoice();
        p.d.querySelectorAll('.rt-fit[data-for="now"]').forEach(el => { el.style.display = choice === 'now' ? '' : 'none'; });
        const box = p.d.querySelector('.rt-interval-plan'); if (!box) return;
        const plan = intervalPlan();
        box.innerHTML = plan ? build.intervalPlan(plan, Number((st.limits || {}).max_days) || 365, fillOn(p)) : '';
        p.d.querySelectorAll('.rt-custom').forEach(el => { el.style.display = st.interval && st.interval !== 'custom' ? 'none' : ''; });
        p.d.querySelectorAll('.rt-row[data-row="athlete"], .rt-row[data-row="interval"]').forEach(el => el.classList.toggle('off', choice !== 'load'));
    }
    function intervalChanged(kind) {
        const st = runState; if (!st || !st.routine || st.busy) return;
        st.interval = kind;
        const p = runParts();
        p.d.querySelectorAll('.rt-interval [data-interval]').forEach(el => el.classList.toggle('on', el.getAttribute('data-interval') === kind));
        renderInterval(); renderCompare(); updateRunButton();
    }
    // the files the Dataset cache holds, for a file routine's dialog (step 4, 2026-10-11): the frames the executor keeps
    // that came from a file (an upload, or a file loaded from the cache before), newest first; nothing without an executor
    // (the local edition) or with nothing cached - the choice stays hidden
    function fillCachePick(p) {
        const sel = p.d.querySelector('select[data-load="cached"]'); if (!sel) return;
        fetchJson('/routines/cache_files').then(res => {
            const files = (res.ok && res.json && res.json.files) || [];
            if (!files.length || !runState) return;
            sel.innerHTML = '<option value="">choose a file</option>' + files.map(f => {
                const rows = f.rows != null ? ' · ' + Number(f.rows).toLocaleString() + ' rows' : '';
                const when = f.cached_at ? ' · ' + fmtDate(Date.parse(f.cached_at) / 1000) : '';
                return '<option value="' + esc(f.df_id) + '" data-name="' + esc(f.name) + '">' + esc(f.name) + esc(rows + when) + '</option>'; }).join('');
            p.d.querySelectorAll('.rt-cachepick').forEach(el => { el.style.display = ''; });
        }).catch(() => { /* no cache to pick from */ });
    }
    // whether the load asked for is already in the executor's cache with every file the routine wants (2026-10-11: a run
    // re-downloaded a window loaded minutes before): asked by the load when Run is pressed; the cached frame and files are
    // taken instead of downloading. (The preview under the window went with the slimmed dialog, §16.1.)
    function cacheAsk(asked) {
        // what to ask the cache about, or null when the dialog has no complete window or event yet
        if (asked.source === 'intervals') return asked.start_date && asked.end_date ? Object.assign({ start: asked.start_date, end: asked.end_date }, asked.subject ? { athlete: asked.subject.id } : {}) : null;
        if (asked.source === 'endura') return asked.race_id ? { race_id: asked.race_id } : null;
        return null;
    }
    function askCache(st, asked) {
        const body = cacheAsk(asked);
        if (!body) return Promise.resolve(null);
        return fetchJson('/routines/' + encodeURIComponent(st.id) + '/cached', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) })
            .then(res => (res.ok && res.json) || { hit: false, line: '' }).catch(() => ({ hit: false, line: '' }));
    }
    function dataChoice() {
        const p = runParts();
        const el = p.d.querySelector('input[name="rt-data"]:checked');
        return el ? el.value : 'now';
    }
    function updateRunButton() {
        // Run is on when the choice can run: a load (checked after it), an upload with a file chosen, or the data loaded now when it fits
        const st = runState; if (!st) return;
        const p = runParts();
        const c = dataChoice();
        const plan = intervalPlan(), windows = build.fillWindows(plan, fillOn(p));
        let on = false;
        if (c === 'load') { const a = p.d.querySelector('select[data-load="athlete"]'); on = (!a || a.getAttribute('data-state') === 'ready') && (!plan || windows.length > 0); }     // an Intervals load waits for the athletes (2026-10-30); a set interval needs a complete unit
        else if (c === 'upload') { const f = p.d.querySelector('input[data-load="file"]'); on = !!(f && f.files && f.files.length); }
        else if (c === 'cache') { const pick = p.d.querySelector('select[data-load="cached"]'); on = !!(pick && pick.value); }
        else on = !!(st.pre && st.pre.ok);
        p.runBtn.disabled = st.busy || !on;
        p.runBtn.querySelector('span').textContent = plan ? build.runLabel(plan, fillOn(p)) : 'Run';       // Run · Run 41 weeks · Run again
        const note = p.d.querySelector('.ui-dlg-f .note');
        if (note) note.textContent = build.tookLine(st.routine, windows.length);
    }
    function fillRaces(p, plan) {
        const sel = p.d.querySelector('select[data-load="race"]'); if (!sel) return;
        fetchJson('/endura/get_races').then(res => {
            const races = (res.ok && res.json && res.json.races) || [];
            if (!races.length) { sel.innerHTML = '<option value="">no races (is the Endura key set?)</option>'; updateRunButton(); return; }
            sel.innerHTML = races.map(x => { const id = x.race_id != null ? x.race_id : (x.id != null ? x.id : x.raceid); const title = x.race_title || x.title || x.name || ('race ' + id);
                return '<option value="' + esc(id) + '"' + (String(id) === String(plan.race_id) ? ' selected' : '') + '>' + esc(title) + (x.race_date ? ' · ' + esc(x.race_date) : '') + '</option>'; }).join('');
            updateRunButton();
        }).catch(() => { sel.innerHTML = '<option value="">the races could not be listed</option>'; });
    }
    function progress(text, kind, percent) {
        const p = runParts(); const el = p.d.querySelector('.rt-progress'); if (!el) return;
        const busy = !!text && kind === 'loading';
        p.body.classList.toggle('rt-busy', busy);
        if (!text) { el.style.display = 'none'; el.innerHTML = ''; return; }
        el.style.display = ''; el.className = 'rt-progress' + (kind ? ' ' + kind : '');
        const n = percent != null && isFinite(Number(percent)) ? Math.max(0, Math.min(100, Number(percent))) : null;
        el.innerHTML = (busy ? '<span class="live"></span>' : '') + '<span class="t">' + esc(text) + '</span>' +
            (busy ? '<div class="bar' + (n == null ? ' sweep' : '') + '"><i' + (n != null ? ' style="width:' + n + '%"' : '') + '></i></div>' : '');
    }
    function sleep(ms) { return new Promise(r => setTimeout(r, ms)); }
    // a load clears what it replaces (2026-10-11: a run's pills used to stack beside the old ones): a load from Intervals,
    // Endura or SweatStack replaces the primary and the auxiliaries, an upload the primary only - each pill removed the way
    // its x removes it (the session's reference dropped, the pill gone)
    async function clearLoaded(scope) {
        const pills = [...document.querySelectorAll('.dataset-status-pill')];
        let n = 0;
        for (const pill of pills) {
            if (scope === 'primary' && pill.dataset.datasetType === 'auxiliary') continue;
            if (typeof removeDatasetPill === 'function') { try { await removeDatasetPill(pill, null, true); } catch (e) { pill.remove(); } }
            else pill.remove();
            n++;
        }
        return n;
    }
    // the load, as the original load asked for its data (the integration routes the Data tab uses; its pills and the
    // dataframe tab refreshed the way the Data tab refreshes them)
    async function loadData(plan, p) {
        const src = plan.source;
        const q = sel => p.d.querySelector(sel);
        const dfTab = job => { if (job && job.dataframe && typeof createOrUpdateTab === 'function') { try { const o = JSON.parse(job.dataframe); createOrUpdateTab('dataframe', o.data); } catch (e) { /* no tab */ } } };
        const asked = loadAsked(plan, p);
        // the cache asked here, for the window or the event as it stands when Run is pressed - not the line's earlier answer,
        // which can lag behind a date typed and committed by the click on Run itself (2026-10-11: a window loaded minutes
        // before was downloaded again)
        let cached = null;
        if (src === 'intervals' || src === 'endura') {
            progress('Asking the cache…', 'loading');
            const c = await askCache(runState, asked);
            cached = c && c.hit ? c : null;
        }
        if (cached) {
            // the load is in the cache with every file the routine wants: the cached frame and files are taken through the
            // Dataset cache's own routes, the pills as a load's, no download
            progress('Taking it from the cache…', 'loading');
            const res = await fetchJson('/cache/load_primary', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ df_id: cached.df_id, folder: cached.folder || '' }) });     // whose frame: the other athletes' files leave the session with it (2026-10-29)
            if (!res.ok) throw new Error((res.json && res.json.error) || 'the cached data could not be loaded');
            for (const fp of cached.files || []) {
                const ar = await fetchJson('/cache/load_auxiliary', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ file_path: fp }) });
                if (!ar.ok) throw new Error((ar.json && ar.json.error) || ('the cached file ' + String(fp).split('/').pop() + ' could not be loaded'));
            }
            // a cached load around the window: the run cuts it to the window (the record says so); the session holds the cached load itself
            const load = Object.assign({}, asked, { cached: true }, cached.cut && cached.cut.length === 2 ? { cached_from: cached.cut } : {}, cached.key ? { key: cached.key } : {});
            if (src === 'intervals') {
                const held = cached.cut && cached.cut.length === 2 ? { start_date: cached.cut[0], end_date: cached.cut[1] } : { start_date: asked.start_date, end_date: asked.end_date };
                const info = Object.assign({ aux_datasets: plan.aux_kinds || [], shape: [cached.rows, null], columns: [], folder: cached.folder || '' }, held);     // the athlete's folder on the record (2026-10-29): the cache dialog's dots read it
                if (typeof createIntervalsPill === 'function') createIntervalsPill(info);
                if (typeof createIntervalsAuxiliaryPills === 'function' && (cached.files || []).length) createIntervalsAuxiliaryPills(cached.files, info);
                dfTab(res.json);
                return { source: 'intervals', start: asked.start_date, end: asked.end_date, aux: cached.files || [], load,
                         loaded: 'Intervals.icu' + (asked.subject && asked.subject.name ? ' · ' + asked.subject.name + ' ·' : '') + ' ' + asked.start_date + ' → ' + asked.end_date + (cached.cut ? ' · cut from the cache' : ' · from the cache') + ((plan.aux_kinds || []).length ? ' · ' + plan.aux_kinds.join(', ') : '') };
            }
            if (typeof createOrUpdateDatasetPill === 'function') {
                createOrUpdateDatasetPill('endura-pill-' + Date.now(), 'Endura (' + (asked.race_title || asked.race_id) + ') loaded', 'endura', 'success', false, null);
                (cached.files || []).forEach((fp, i) => createOrUpdateDatasetPill('endura-aux-pill-' + Date.now() + '-' + i, 'Auxiliary (' + String(fp).split('/').pop().replace('.csv', '') + ')', 'auxiliary', 'success', false, fp));
            }
            dfTab(res.json);
            return { source: 'endura', aux: cached.files || [], load, loaded: 'Endura · ' + (asked.race_title || asked.race_id) + ' · from the cache' };
        }
        if (src === 'intervals') {
            const start = asked.start_date, end = asked.end_date;          // the window as typed, or a set interval's span (§14.2; a day's start is its end)
            if (!start || !end || start > end) throw new Error('the window needs a start before its end');
            progress('Starting the load from Intervals.icu…', 'loading');
            const who = asked.subject || {};                      // whose key (2026-10-30): the app refuses, naming them, when none is stored
            const res = await fetchJson('/intervals/load_data', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(Object.assign({ start_date: start, end_date: end, metrics: plan.metrics || [], aux_datasets: plan.aux_kinds || [] }, who.id ? { athlete: who.id, athlete_name: who.name || '' } : {})) });
            if (!res.ok) throw new Error((res.json && res.json.error) || 'the load could not start');
            const jobId = res.json.job_id;
            const t0 = Date.now();
            while (Date.now() - t0 < 600000) {
                await sleep(1000);
                const jr = await fetchJson('/intervals/job/' + encodeURIComponent(jobId));
                const job = jr.json || {};
                if (job.status === 'completed') {
                    const info = { start_date: start, end_date: end, aux_datasets: plan.aux_kinds || [], shape: (job.result || {}).shape, columns: (job.result || {}).columns, folder: ((job.result || {}).subject || {}).folder || '' };
                    let files = (job.result || {}).aux_datasets || [];
                    // the coding pass behind the load (2026-10-14): a routine's counts depend on the codes, so the run waits for it here
                    let coding = job.result && job.result.context && job.result.context.coding;
                    while (coding && coding.status === 'running' && Date.now() - t0 < 600000) {
                        progress(coding.message || 'Coding the context…', 'loading', coding.percent);
                        await sleep(2000);
                        const cr = await fetchJson('/intervals/context_coding/' + encodeURIComponent(jobId));
                        coding = cr.json || null;
                    }
                    if (coding && coding.codes_path && !files.includes(coding.codes_path)) files = files.concat([coding.codes_path]);
                    if (typeof createIntervalsPill === 'function') createIntervalsPill(info);
                    if (typeof createIntervalsAuxiliaryPills === 'function' && files.length) createIntervalsAuxiliaryPills(files, info);
                    dfTab(job);
                    // the store's part (docs/INCREMENTAL_LOADS_DESIGN.md): on the record and in the LOAD row's fold, not in its clipped text
                    const st_ = job.result && job.result.store;
                    const store = st_ && st_.window ? { window: st_.window, held: st_.held || 0, fetched: st_.fetched || 0, refresh: !!st_.refresh } : null;
                    return { source: 'intervals', start, end, aux: files, load: Object.assign({}, asked, store ? { store } : {}), store, loaded: 'Intervals.icu' + (who.name ? ' · ' + who.name + ' ·' : '') + ' ' + start + ' → ' + end + ((plan.aux_kinds || []).length ? ' · ' + plan.aux_kinds.join(', ') : '') + (coding && coding.line ? ' · ' + coding.line : '') };
                }
                if (job.status === 'error' || job.status === 'not_found') throw new Error(job.error || 'the load failed');
                progress(job.message || 'Loading…', 'loading', job.total > 0 ? job.percent : null);
            }
            throw new Error('the load did not finish in ten minutes');
        }
        if (src === 'endura') {
            const race = q('select[data-load="race"]'); const raceId = race && race.value;
            if (!raceId) throw new Error('pick a race');
            const title = race.options[race.selectedIndex].textContent;
            progress('Loading ' + title + ' from Endura…', 'loading');
            const res = await fetchJson('/endura/load_data', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ race_id: raceId, aux_datasets: plan.aux_kinds || ['profile'] }) });
            if (!res.ok) throw new Error((res.json && res.json.error) || 'the load failed');
            if (typeof createOrUpdateDatasetPill === 'function') {
                createOrUpdateDatasetPill('endura-pill-' + Date.now(), 'Endura (' + ((res.json && res.json.race_title) || title) + ') loaded', 'endura', 'success', false, null);
                (res.json.aux_datasets || []).forEach((fp, i) => createOrUpdateDatasetPill('endura-aux-pill-' + Date.now() + '-' + i, 'Auxiliary (' + String(fp).split('/').pop().replace('.csv', '') + ')', 'auxiliary', 'success', false, fp));
            }
            dfTab(res.json);
            return { source: 'endura', aux: (res.json && res.json.aux_datasets) || [], load: Object.assign({}, asked, { race_title: (res.json && res.json.race_title) || title }), loaded: 'Endura · ' + ((res.json && res.json.race_title) || title) };
        }
        if (src === 'sweatstack') {
            const start = q('input[data-load="start"]').value, end = q('input[data-load="end"]').value;
            progress('Loading from SweatStack…', 'loading');
            const res = await fetchJson('/sweatstack/load_data', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ sports: plan.sports || [], metrics: plan.metrics || [], users: plan.users || [], start_date: start, end_date: end }) });
            if (!res.ok) throw new Error((res.json && res.json.error) || 'the load failed');
            if (typeof createSweatStackPill === 'function') createSweatStackPill({ start_date: start, end_date: end, sports: plan.sports || [], users: plan.users || [] });
            dfTab(res.json);
            return { source: 'sweatstack', start, end, load: asked, loaded: 'SweatStack ' + start + ' → ' + end };
        }
        if (dataChoice() === 'cache') {
            // a file the Dataset cache holds: the frame taken through the cache's own route, the pill as an upload's
            const pick = q('select[data-load="cached"]');
            if (!pick || !pick.value) throw new Error('choose a file from the cache');
            const name = pick.options[pick.selectedIndex].getAttribute('data-name') || 'the cached file';
            progress('Taking ' + name + ' from the Dataset cache…', 'loading');
            const res = await fetchJson('/cache/load_primary', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ df_id: pick.value }) });
            if (!res.ok) throw new Error((res.json && res.json.error) || 'the cached file could not be loaded');
            if (typeof createOrUpdateDatasetPill === 'function') createOrUpdateDatasetPill('primary-dataset-pill-' + Date.now(), 'Primary (' + name + ') loaded', 'primary', 'success', false, null);
            if (typeof currentDatasetName !== 'undefined') { try { currentDatasetName = name; } catch (e) { /* read-only */ } }
            dfTab(res.json);
            return { source: 'file', load: { source: 'file', name, cached: true }, loaded: name + ' · from the Dataset cache' };
        }
        // a file: the Data tab's upload route
        const f = q('input[data-load="file"]');
        if (!f || !f.files || !f.files.length) throw new Error('choose a file');
        const file = f.files[0];
        progress('Uploading ' + file.name + '…', 'loading');
        const fd = new FormData(); fd.append('file', file);
        const r = await window.authService.fetch('/upload', { method: 'POST', body: fd });
        let data = {}; try { data = await r.json(); } catch (e) { data = {}; }
        if (!r.ok) throw new Error(data.message || data.error || 'the upload failed');
        // an upload replaces the primary only (clearLoaded took the primary); the auxiliary files loaded before stay as they are (no `aux` sent)
        if (typeof createOrUpdateDatasetPill === 'function') createOrUpdateDatasetPill('primary-dataset-pill-' + Date.now(), 'Primary (' + file.name + ') loaded', 'primary', 'success', false, null);
        if (typeof currentDatasetName !== 'undefined') { try { currentDatasetName = file.name; } catch (e) { /* read-only */ } }
        dfTab(data);
        return { source: 'file', load: { source: 'file', name: file.name }, loaded: file.name };
    }
    function closeRun() { if (runState && runState.busy) return; const p = runParts(); p.d.style.display = 'none'; runState = null; }
    function readRunValues() {
        const p = runParts(), values = {};
        p.d.querySelectorAll('[data-key]').forEach(el => {
            const k = el.getAttribute('data-key'), t = el.getAttribute('data-type');
            if (t === 'toggle') values[k] = !!el.checked;
            else if (t === 'date_window') { values[k] = values[k] || ['', '']; values[k][Number(el.getAttribute('data-part'))] = el.value; }
            else values[k] = el.value;
        });
        const cmp = p.d.querySelector('input[name="rt-compare"]:checked');
        return { values, compare_with: cmp ? cmp.value : 'previous' };
    }
    async function startRun() {
        const st = runState; if (!st || !st.routine || st.busy) return;
        const p = runParts();
        const { values, compare_with } = readRunValues();
        const plan = intervalPlan(), windows = build.fillWindows(plan, fillOn(p));       // a set interval (§14.2): the units to run; [] for custom
        if (plan && !windows.length) return;
        // a custom window within the plan's reach and window (2026-11-08): one over them is moved into them and said, and Run is pressed again
        if (!plan && dataChoice() === 'load' && (st.plan || {}).source === 'intervals' && st.limits && window.DateWindow) {
            const a = p.d.querySelector('input[data-load="start"]'), b = p.d.querySelector('input[data-load="end"]');
            const fit = window.DateWindow.check(window.DateWindow.of(st.limits), a && a.value, b && b.value, st.lastChanged || 'end');
            if (fit.note) { a.value = fit.start; b.value = fit.end; progress('! ' + fit.note, 'bad'); return; }
        }
        st.busy = true; p.runBtn.disabled = true; p.cancelBtn.disabled = true;
        const choice = dataChoice();
        let loaded = null;
        if (choice !== 'now') {
            // the load, as the original load asked for its data; its progress here, in the dialog - what it replaces cleared first
            try {
                progress('Clearing the data loaded now…', 'loading');
                await clearLoaded(choice === 'upload' || choice === 'cache' ? 'primary' : 'all');
                if (runState !== st) return;
                loaded = await loadData(st.plan || {}, p);
            } catch (err) {
                if (runState !== st) return;
                st.busy = false; p.cancelBtn.disabled = false; updateRunButton();
                progress('! ' + (err.message || err), 'bad');
                return;
            }
            if (runState !== st) return;
            progress('Loaded · checking it against the routine…', 'loading');
        }
        // the checks with the values as typed: what differs from the data the method was made on is said here, before the view changes
        const auxLoaded = loaded && loaded.aux ? loaded.aux : undefined;   // the files this load produced, as the page saw them (an empty list when it produced none)
        const loadDone = loaded && loaded.load ? loaded.load : undefined;   // the load as the page did it (from the cache, or downloaded)
        // one unit of a set interval: the run is cut to it from what was loaded (§14.3) - the loader makes a day's load two days, a cache hit may be wider
        if (plan && windows.length === 1 && loadDone) Object.assign(loadDone, { start_date: windows[0][0], end_date: windows[0][1], cached_from: loadDone.cached_from || [loaded.start, loaded.end] });
        fetchJson('/routines/' + encodeURIComponent(st.id) + '/precheck', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ values, aux: auxLoaded, load: loadDone }) }).then(pr => {
            if (runState !== st) return;
            if (!pr.ok || !pr.json.ok) {
                st.busy = false; p.cancelBtn.disabled = false;
                const line = '! ' + ((pr.json && (pr.json.line || pr.json.error)) || 'the check failed');
                if (choice === 'now') { const fitEl = p.d.querySelector('.rt-fit'); if (fitEl) { fitEl.className = 'rt-fit bad'; fitEl.textContent = line; } }
                else progress(line, 'bad');
                updateRunButton();
                return;
            }
            if (windows.length > 1) { startFill(st, plan, windows, values, auxLoaded, loadDone, p); return; }
            progress('');
            const routine = st.routine;
            p.d.style.display = 'none'; runState = null;
            closeManager();                                   // the run shows in the main panes; the manager would cover them
            const all = runNumbers(routine), next = all.length ? Math.max.apply(null, all) + 1 : 1;
            const subject = (choice === 'now' ? ((st.pre && st.pre.data) || {}).subject : (loadDone || {}).subject) || {};      // whose runs the view will step through (2026-10-30)
            const numbers = runNumbers(routine, subjectIdOf(subject));
            enterRunView(summaryOf(routine), numbers.concat([next]), numbers.length, { pending: true, version: routine.current_version, subject });
            if (loaded && typeof paneLookup === 'function') paneLookup({ kind: 'load', query: loaded.loaded || '', peek: [typeof storeLine === 'function' ? storeLine(loaded.store) : '', (pr.json && pr.json.line) || ''].filter(Boolean).join(' · '), sources: [], passages: [] });
            stream('/routines/' + encodeURIComponent(routine.id) + '/run', { values, compare_with, aux: auxLoaded, load: loadDone, interval: plan ? plan.kind : undefined }, true, data => {
                if (data.type === 'pane_routine_end' && typeof paneRoutineEnd === 'function') { paneRoutineEnd(data); chipIdle(); return true; }
                return false;
            }).then(msg => {
                const out = msg.routine_run;
                finishRunView(out);
                if (manager && manager.style.display !== 'none') loadManager(routine.id);
            }).catch(err => {
                chipIdle();
                if (typeof paneSystem === 'function') paneSystem(err.message || String(err), 'error');
                toast('The run did not go through: ' + (err.message || err));
                if (viewState) { viewState.numbers = runNumbers(routine, subjectIdOf(viewState.subject)); viewState.index = Math.max(0, viewState.numbers.length - 1); viewState.pending = false; updateRunNav(); }
            });
        });
    }
    // a fill (§14.3): the span is loaded; the server runs the units, oldest first, in the background; the Summary shows them land
    function startFill(st, plan, windows, values, aux, load, p) {
        fetchJson('/routines/' + encodeURIComponent(st.id) + '/fill', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ interval: plan.kind, windows, values, aux, load }) }).then(res => {
            if (runState !== st) return;
            if (!res.ok) { st.busy = false; p.cancelBtn.disabled = false; progress('! ' + ((res.json && res.json.error) || 'the fill could not start'), 'bad'); updateRunButton(); return; }
            progress('');
            const routine = st.routine;
            p.d.style.display = 'none'; runState = null;
            fillState = res.json.fill || { running: true, routine_id: routine.id, interval: plan.kind, total: windows.length, done: 0, failed: 0 };
            watchFill();
            openManager(routine.id);
        }).catch(err => { if (runState === st) { st.busy = false; p.cancelBtn.disabled = false; progress('! ' + (err.message || err), 'bad'); updateRunButton(); } });
    }
    let fillState = null, fillTimer = null;
    function fillRunning() { return !!(fillState && fillState.running); }
    function fillFor(routineId) { return fillState && fillState.routine_id === routineId ? fillState : null; }
    function fillReason() { return 'A fill is running (' + build.fillLine(fillState) + ') — the composer comes back when it ends; stop it in the Summary'; }
    // the fill's status every three seconds while it runs: the Summary's line, the composer's reason, the routine re-read as a unit lands;
    // when it ends, the last word, the Summary re-read and the composer back - unless a run's view holds it
    function watchFill() {
        clearTimeout(fillTimer);
        const tick = () => fetchJson('/routines/fill').then(res => {
            const was = fillState, st = (res.json && res.json.fill) || { running: false };
            fillState = st;
            const landed = !was || was.done !== st.done;
            if (st.running) {
                composerLock(fillReason());
                const bar = manager && manager.querySelector('.rt-fillbar .t'); if (bar) bar.textContent = build.fillLine(st);
                if (landed && manager && manager.style.display !== 'none' && managerState.current && managerState.current.id === st.routine_id) showRoutine(st.routine_id);
                fillTimer = setTimeout(tick, 3000);
                return;
            }
            if (was && was.running) {
                toast(build.fillLine(st));
                if (manager && manager.style.display !== 'none') loadManager(st.routine_id);
                if (viewState) composerLock(); else composerUnlock();
            }
        }).catch(() => { fillTimer = setTimeout(tick, 5000); });
        tick();
    }
    function probeFill() {          // a fill from before this page was loaded (a reload): the lock and the line come back
        fetchJson('/routines/fill').then(res => { const st = res.json && res.json.fill; if (st && st.running) { fillState = st; watchFill(); } }).catch(() => {});
    }
    function summaryOf(r) { return { id: r.id, name: r.name, current_version: r.current_version, source: r.source }; }
    function chipIdle() { if (window.containerStatus && typeof window.containerStatus.setExecuting === 'function') window.containerStatus.setExecuting(false); }   // the executor chip back to its polled status (a run sets it as a cell does)
    function runNumbers(r, athleteId) {
        // the runs the arrows step through: run zero then every run - of one athlete when asked (2026-10-30: run zero when it is theirs)
        const v = (r.versions || []).find(x => x.number === r.current_version) || {};
        const out = (v.run_zero && v.run_zero.verified && build.zeroFits(v, athleteId == null ? null : athleteId)) ? [0] : [];
        return out.concat((r.runs || []).filter(x => athleteId == null || build.subjectId(x) === String(athleteId)).map(x => x.number));
    }
    function subjectName(sub) { return sub && (sub.name || sub.id) ? String(sub.name || sub.id) : ''; }
    function subjectIdOf(sub) { return sub && sub.id ? String(sub.id) : ''; }

    // ------------------------------------------------------------ a run in the main panes (S4): one run per view, the arrows between runs
    let viewState = null;
    function inRunView() { return !!viewState; }
    function enterRunView(routine, numbers, index, meta) {
        // meta.subject (2026-10-30): whose runs the view steps through - the id line and the position name them
        viewState = { routine, numbers: numbers || [], index: index || 0, pending: !!(meta && meta.pending), version: meta && meta.version, subject: (meta && meta.subject) || {} };
        const so = document.getElementById('streamOutput'); if (so) so.innerHTML = '';
        if (typeof clearAllTabs === 'function') clearAllTabs();
        const number = viewState.numbers[viewState.index];
        if (typeof paneRunIds === 'function') paneRunIds({ name: routine.name, run: (number != null ? number : '…') + ' · v' + (viewState.version || routine.current_version) + whoLine(), df_id: (typeof currentData !== 'undefined' && currentData.df_id) || '' });
        if (typeof paneRunStrip === 'function') paneRunStrip({ mode: 'Routine', run: number != null ? number : '…', version: viewState.version || routine.current_version, estimate: '' });
        composerLock();
        if (typeof updateRankButtonVisibility === 'function') updateRankButtonVisibility();
        updateRunNav();
    }
    function whoLine() { const n = viewState ? subjectName(viewState.subject) : ''; return n ? ' · ' + n : ''; }
    function finishRunView(out) {
        if (!viewState) return;
        const run = out.run, numbers = out.numbers || viewState.numbers;
        viewState.numbers = numbers; viewState.index = Math.max(0, numbers.indexOf(run.number)); viewState.pending = false; viewState.routine = out.routine || viewState.routine;
        if (out.subject) viewState.subject = out.subject;
        if (typeof paneRunIds === 'function') paneRunIds({ name: viewState.routine.name, run: run.number + ' · v' + run.version + whoLine(), df_id: (run.data || {}).df_id || '' });
        const c = run.comparison || {};
        if (typeof paneRunStrip === 'function') paneRunStrip({ mode: 'Routine', run: run.number, version: run.version, idle: true, estimate: run.against != null ? 'run ' + run.against + ' — ' + (c.line || '') : (c.line || '') });
        if (typeof createOrUpdateTab === 'function') createOrUpdateTab('comparison', build.comparisonTab({ run, against_data: out.against_data || null }));
        withSeries(viewState.routine.id, run, subjectIdOf(viewState.subject), s => createOrUpdateTab('comparison', build.comparisonTab({ run, against_data: out.against_data || null }, s)));
        updateRunNav();
        toast('Run ' + run.number + ' recorded · ' + (run.line || run.status));
    }
    // the Trend tab's series (§14.6): a run on a set interval draws each line over the athlete's units, from the routine's runs
    function withSeries(routineId, run, subjectId, show) {
        if (!run || !run.interval || typeof createOrUpdateTab !== 'function') return;
        Promise.all([fetchJson('/routines/' + encodeURIComponent(routineId)), horizon()]).then(([res, h]) => {
            const r = res.ok && res.json && res.json.routine;
            if (!r || !viewState || viewState.routine.id !== routineId || viewState.numbers[viewState.index] !== run.number) return;
            show(build.series(r, run.interval, subjectId || '', build.units(run.interval, new Date(), h)));
        }).catch(() => {});
    }
    function viewRun(routineId, number) {
        if (typeof queryRunning !== 'undefined' && queryRunning) { toast('An analysis is running; open the run when it has finished.'); return; }
        return fetchJson('/routines/' + encodeURIComponent(routineId) + '/runs/' + encodeURIComponent(number)).then(res => {
            if (!res.ok) { toast('This run could not be opened: ' + ((res.json && res.json.error) || res.status), 'error'); return; }
            const view = res.json, run = view.run;
            const numbers = view.numbers || [number];
            enterRunView(view.routine, numbers, Math.max(0, numbers.indexOf(run.number)), { version: run.version, subject: view.subject || {} });
            const d = run.data || {};
            const cells = run.cells != null ? run.cells + ' cell' + (run.cells === 1 ? '' : 's') : '';
            if (typeof paneLookup === 'function') {
                const ld = loadLabel(d.load);
                if (ld && run.number !== 0 && sourceKind((d.load || {}).source) !== 'file') paneLookup({ kind: 'load', query: ld, peek: '', sources: [], passages: [] });
                // a stored run's CHECK row says what the live one said (the record's line, step 4, 2026-10-11); run 0 and older records the size
                paneLookup({ kind: 'check', query: d.name || sourceLabel(d.source), peek: run.check || ((d.rows != null ? Number(d.rows).toLocaleString() + ' rows · ' : '') + ((d.columns || []).length || d.columns || 0) + ' columns' + (run.number === 0 ? ' · the analysis\u2019s own data' : '')), sources: [], passages: [] });
                paneLookup({ kind: run.number === 0 ? 'routine' : 'run', query: 'run ' + run.number + ' · v' + run.version + (cells ? ' · ' + cells : ''), peek: (run.line || run.status) + ' · ' + (run.figures || 0) + ' figure' + (run.figures === 1 ? '' : 's') + (run.elapsed != null ? ' · ' + run.elapsed + ' s' : ''), sources: [], passages: [] });
                if (run.against != null) { const w = build.whenOf(view.against_data); paneLookup({ kind: 'compare', query: 'with run ' + run.against + (w ? ' (' + w + ')' : ''), peek: (run.comparison || {}).line || '', sources: [], passages: [] }); }
            }
            const c = run.comparison || {};
            if (typeof paneRoutineEnd === 'function') paneRoutineEnd({ number: run.number, name: view.name, version: run.version, status: run.status, line: run.line, results: (run.results || []).length, compared: c.compared || 0, moved: c.moved || 0, changed: c.changed || 0, missing: c.missing || 0, figures: run.figures || 0, elapsed: run.elapsed, against: run.against, comparison_line: c.line });
            if (typeof createOrUpdateTab === 'function') {
                createOrUpdateTab('comparison', build.comparisonTab(view));
                (view.figures || []).forEach(f => createOrUpdateTab('plot', f.data, f.id, f.format));
                if (view.stdout) createOrUpdateTab('code_exec_results', view.stdout);
                createOrUpdateTab('dataframe', build.dataTab(d, run));
                if (typeof activateTab === 'function') activateTab('comparison');
                withSeries(routineId, run, subjectIdOf(view.subject), s => createOrUpdateTab('comparison', build.comparisonTab(view, s)));
            }
            if (typeof paneRunIds === 'function') paneRunIds({ name: view.name, run: run.number + ' · v' + run.version + whoLine(), df_id: d.df_id || '' });
            updateRunNav();
        });
    }
    function exitRunView() {
        viewState = null;
        composerUnlock();
    }
    function navigateRuns(direction) {
        if (!viewState || viewState.pending) return;
        const i = viewState.index + direction;
        if (i < 0 || i >= viewState.numbers.length) return;
        viewRun(viewState.routine.id, viewState.numbers[i]);
    }
    function updateRunNav() {
        const prev = document.getElementById('prevResponse'), next = document.getElementById('nextResponse'), nav = document.querySelector('.tab-navigation'), pos = document.getElementById('chainPosition');
        if (!viewState || !nav) return;
        nav.style.display = 'flex';
        const n = viewState.numbers.length, i = viewState.index;
        if (pos) pos.textContent = (viewState.pending ? 'run ' + viewState.numbers[i] + ' · running' : 'run ' + viewState.numbers[i] + ' of ' + (n ? viewState.numbers[n - 1] : 0)) + whoLine();
        if (prev) prev.disabled = viewState.pending || i <= 0;
        if (next) next.disabled = viewState.pending || i >= n - 1;
    }

    // ------------------------------------------------------------ the rail entry
    // run zero behind the dialog (2026-10-15): the page follows the verdict and says it when it lands; the manager, open on
    // the routine, shows the chip change and the Run button come alive. The condensing pass (§19) follows the verdict: the
    // chip says condensing… meanwhile, and the toast carries the pass's line
    const watching = {};
    function watchVerification(id, name, version) {
        if (watching[id]) return;
        watching[id] = 'verifying';
        const t0 = Date.now();
        const tick = () => fetchJson('/routines/' + encodeURIComponent(id)).then(res => {
            const r = res.json && res.json.routine;
            const v = r && (r.versions || []).find(x => x.number === version);
            const st = v && v.run_zero ? v.run_zero.status : '';
            if (!r || (st && st !== 'verifying' && st !== 'condensing')) {
                delete watching[id];
                if (v) toast(name + ' · v' + version + (v.run_zero.verified ? ' · verified on the original data' + (v.condensed && v.condensed.line ? ' · ' + v.condensed.line : '') : ' · run zero did not reproduce: ' + (v.run_zero.line || '')));
                if (manager && manager.style.display !== 'none') loadManager(id);
                if (window.WorkflowModal && typeof window.WorkflowModal.refresh === 'function') window.WorkflowModal.refresh();
                return;
            }
            if (st && st !== watching[id]) {                 // verifying → condensing: the open manager's chip follows
                watching[id] = st;
                if (manager && manager.style.display !== 'none') loadManager(id);
            }
            if (Date.now() - t0 < 3600000) setTimeout(tick, 3000); else delete watching[id];
        }).catch(() => { setTimeout(tick, 5000); });
        setTimeout(tick, 3000);
    }
    function fmtTook(secs) {
        const s = Math.round(Number(secs) || 0);
        if (s < 60) return s + ' s';
        const m = Math.round(s / 60);
        return m < 60 ? m + ' min' : Math.floor(m / 60) + ' h ' + (m % 60) + ' min';
    }
    function bindRail() {
        const pill = document.getElementById('routinesPill'); if (!pill) return;
        pill.addEventListener('click', e => { e.stopPropagation(); openManager(); });
    }

    // ------------------------------------------------------------ the favourites' cards
    function cardCount(chainOrThread) {
        if (Array.isArray(chainOrThread)) return chainOrThread.reduce((n, c) => n + ((c.routines || []).length), 0);
        return ((chainOrThread && chainOrThread.routines) || []).length;
    }
    function bindCardButton(btn, chain, chains) {
        if (!btn) return;
        btn.addEventListener('click', e => {
            e.stopPropagation();
            const all = (chains || [chain]).flatMap(c => c.routines || []);
            if (all.length) { if (window.WorkflowModal && typeof window.WorkflowModal.close === 'function') window.WorkflowModal.close(); openManager(all[0].id); }
            else { if (window.WorkflowModal && typeof window.WorkflowModal.close === 'function') window.WorkflowModal.close(); openMake(chain.thread_id, chain.chain_id, { fromCard: true }); }
        });
    }

    // ------------------------------------------------------------ the composer lock (a run's view: nothing to ask; a fill: the kernel is taken)
    function composerLock(reason) {
        const input = document.getElementById('queryInput'), send = document.getElementById('submitQuery');
        if (input) { input.disabled = true; if (input.getAttribute('data-placeholder') == null) input.setAttribute('data-placeholder', input.placeholder || input.getAttribute('placeholder') || ''); input.placeholder = reason || 'A run is a record: to go further, open the analysis it was made from'; }
        if (send) send.disabled = true;
        document.body.classList.add('composer-locked');
    }
    function composerUnlock() {
        if (fillRunning()) { composerLock(fillReason()); return; }           // a fill still holds the kernel: the lock stays, with its reason
        const input = document.getElementById('queryInput'), send = document.getElementById('submitQuery');
        if (input) { input.disabled = false; const was = input.getAttribute('data-placeholder'); if (was != null) { input.placeholder = was; input.removeAttribute('data-placeholder'); } }
        if (send) send.disabled = false;
        document.body.classList.remove('composer-locked');
    }

    function initialize() {
        bindPill(); bindRail();
        setTimeout(probeFill, 1500);
    }

    window.RoutinesUI = { initialize, openMake, openManager, closeManager, toggleSaveMenu: toggleMenu, hideSaveMenu: hideMenu, forgetOrigins,
                          cardButton: build.cardButton, cardCount, bindCardButton, composerLock, composerUnlock, build,
                          openRun, viewRun, exitRunView, inRunView, navigateRuns, updateRunNav, enterRunView, runNumbers, clearLoaded, fillRunning };
    window.composerLock = composerLock; window.composerUnlock = composerUnlock;
    window.__routinesBuild = build;
})();
