// routines.js - Routines (docs/ROUTINES_DESIGN.md, 2026-10-10): the Save pill's menu (Save as favourite / Save as
// routine), the Save-as-routine dialog, the Routines manager behind the rail entry, the favourites' cards' Routine
// button and the composer lock a run's view sets. Markup is built here on the app's own grammar (ui-*); the
// stylesheet rules are in dialogs.css (the dialogs) and shell.css (the pill's menu, the rail entry).
//
// Server routes (web_app/routines_routes.py): GET /routines, GET /routines/<id>, DELETE /routines/<id>,
// POST /routines/<id>/rename, GET /routines/<id>/script, GET /routines/by_origin/<thread>[/<chain>],
// POST /routines/propose and POST /routines/create - the last two stream the pane's rows and end with one of
// routine_proposal | routine_made | routine_error.

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
        const from = ld.cached ? (ld.cached_from && ld.cached_from.length === 2 ? ' · cut from the cached load ' + ld.cached_from[0] + ' → ' + ld.cached_from[1] : ' · from the cache') : '';
        if (src === 'intervals' || src === 'sweatstack') return sourceLabel(src) + (ld.start_date ? ' ' + ld.start_date + ' → ' + ld.end_date : '') + (ld.aux_kinds && ld.aux_kinds.length ? ' · ' + ld.aux_kinds.join(', ') : '') + (ld.sports && ld.sports.length ? ' · ' + ld.sports.join(', ') : '') + from;
        if (src === 'endura') return 'Endura · ' + (ld.race_title || ('race ' + (ld.race_id || ''))) + from;
        return ld.name ? 'File · ' + ld.name : '';
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
        loading(seat, model) {
            return '<div class="rt-wait"><span class="live"></span>The analyst is reading the chain and naming its inputs…' + (seat ? '<span class="ui-muted"> · ' + esc(seat) + (model ? ' on ' + esc(String(model).split('/').pop()) : '') + '</span>' : '') + '</div>';
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
        resultsList(results) {
            if (!results || !results.length) return '<div class="rt-line">This analysis recorded no RESULT lines, so runs will not be compared number by number; the routine still keeps its printed output and figures.</div>';
            return '<div class="rt-results">' + results.map(r => r.typed
                ? '<div class="r flag" data-cell="' + esc(r.cell) + '" data-index="' + esc(r.index) + '"><span class="g">!</span><span class="l">cell ' + esc(r.cell) + ': the numbers were typed into the call, not computed — this line will not change with new data</span>' +
                  '<span class="ui-seg"><span class="on" data-keep="1">keep as a constant</span><span data-keep="0">drop</span></span></div>'
                : '<div class="r"><span class="g">✓</span><span class="l" title="' + esc(r.label) + '">' + esc(r.label) + '</span><span class="c">cell ' + esc(r.cell) + '</span></div>').join('') + '</div>';
        },
        proposal(p, threadRoutines) {
            const under = (threadRoutines && threadRoutines.length) ? threadRoutines[0] : null;
            let h = '';
            if (under) {
                h += '<div class="rt-sec"><div class="h">This analysis is the origin of a routine</div><div class="ui-choices rt-version">' +
                    '<div class="ui-choice on" data-version="next"><b>Next version of “' + esc(under.name) + '”</b><span>v' + (Number(under.version) + 1) + ' · the method of this chain, the inputs carried over, checked on this chain’s data</span></div>' +
                    '<div class="ui-choice" data-version="new"><b>A new routine</b><span>kept apart from the existing one</span></div></div>' +
                    '<div class="ui-field rt-change"><label>What changed</label><input class="ui-input" data-field="change_note" placeholder="one line, for the versions list"></div></div>';
            }
            h += '<div class="ui-field"><label>Name</label><input class="ui-input" data-field="name" value="' + esc(p.name) + '" maxlength="80"></div>';
            h += '<div class="ui-field"><label>Purpose <span class="ui-muted">— one line for the card and for the note written after each run</span></label><input class="ui-input" data-field="purpose" value="' + esc(p.purpose || p.question || '') + '" maxlength="300"></div>';
            h += '<div class="rt-sec"><div class="h">Data</div>' + build.dataLine(p) + '</div>';
            h += '<div class="rt-sec"><div class="h">Inputs <span class="n">— what you can change each run; everything else stays as the analysis had it</span></div>' + build.inputsTable(p.inputs, p.kept) + '</div>';
            const kept = (p.results || []).filter(r => !r.dropped).length;
            h += '<div class="rt-sec"><div class="h">Results <span class="n">— the lines the runs will compare, ' + kept + ' kept' + (p.figures && p.figures.count ? ' · ' + p.figures.count + ' figure' + (p.figures.count === 1 ? '' : 's') : '') + '</span></div>' + build.resultsList(p.results) + '</div>';
            if (p.notes && p.notes.length) h += '<div class="rt-sec"><div class="h">Notes</div><div class="rt-line muted">' + p.notes.map(esc).join('<br>') + '</div></div>';
            return h;
        },
        // the manager
        managerShell() {
            return '<div class="ui-dlg lg rt-mgr"><div class="rt-left"><div class="ui-side-label">Routines</div><div class="rt-side"></div></div>' +
                '<div class="rt-right"><div class="ui-dlg-h"><div><div class="title"></div><div class="sub"></div></div><span class="sp"></span><div class="rt-actions"></div><button class="x" aria-label="Close">×</button></div><div class="rt-body"></div></div></div>';
        },
        sideItem(r, on) {
            return '<div class="it' + (on ? ' on' : '') + '" data-id="' + esc(r.id) + '"><b>' + esc(r.name) + '</b><span>' + esc(sourceLabel(r.source)) + ' · v' + esc(r.current_version) + (r.runs ? ' · ' + r.runs + ' run' + (r.runs === 1 ? '' : 's') : '') + ' · ' + esc(fmtDate(r.updated || r.created)) + '</span></div>';
        },
        empty() {
            return '<div class="rt-empty">No routines yet. On a finished analysis, hover <b>Save</b> and choose <b>Save as routine</b>: the method keeps its few inputs and runs again on new data, without a model.</div>';
        },
        routineHeader(r) {
            const d = (r.summary_card && r.summary_card.data) || {};
            const cols = (d.columns || []).length;
            const o = r.origin || {};
            const link = r.origin_available
                ? '<a href="#" class="rt-origin" data-thread="' + esc(o.thread_id) + '" data-chain="' + esc(o.chain_id) + '">made from the analysis of ' + esc(chainDate(o.chain_id) || o.chain_id) + ' ↗</a> <span class="ui-muted">(a favourite; continue it there)</span>'
                : '<span class="ui-muted">made from the analysis of ' + esc(chainDate(o.chain_id) || o.chain_id) + ' — no longer in Saved workflows</span>';
            return { title: esc(r.name), sub: esc(sourceLabel(r.source)) + (cols ? ' · ' + cols + ' columns' : '') + ' · v' + esc(r.current_version) + ' · ' + link };
        },
        routineBody(r) {
            const v = (r.versions || []).find(x => x.number === r.current_version) || (r.versions || [])[(r.versions || []).length - 1] || {};
            const m = v.manifest || {};
            const rz = v.run_zero || {};
            let h = '<div class="rt-sec"><div class="ui-kv">' + (r.purpose ? '<b>Purpose</b><span>' + esc(r.purpose) + '</span>' : '') + '<b>Question</b><span>' + esc(r.question) + '</span>' +
                '<b>Checked</b><span><span class="rt-status ' + (rz.verified ? 'reproduced' : 'unverified') + '">' + (rz.verified ? 'verified' : 'unverified') + '</span> ' + esc(rz.line || '') + '</span></div></div>';
            const params = m.parameters || [];
            h += '<div class="rt-sec"><div class="h">Inputs <span class="n">— asked before each run</span></div>' + (params.length
                ? '<table class="ui-table rt-inputs"><thead><tr><th>Input</th><th>Default</th><th>Where it comes from</th></tr></thead><tbody>' + params.map(p => '<tr' + (p.derived ? ' data-derived="' + esc(p.derived) + '"' : '') + '><td>' + esc(p.label) + '</td><td><span class="val">' + esc(valueText(p)) + '</span>' + (p.derived ? '<span class="rt-derived">' + esc(derivedText(p)) + '</span>' : '') + '</td><td><span class="from">' + esc(p.origin || '') + '</span></td></tr>').join('') + '</tbody></table>'
                : '<div class="rt-line">None: the method runs as it is on data of the same shape.</div>') + '</div>';
            const res = (m.results || []).filter(x => !x.dropped);
            h += '<div class="rt-sec"><div class="h">Results <span class="n">— compared run to run' + (m.figures && m.figures.count ? ' · ' + m.figures.count + ' figure' + (m.figures.count === 1 ? '' : 's') : '') + '</span></div>' +
                (res.length ? '<div class="rt-results">' + res.map(x => '<div class="r"><span class="g">✓</span><span class="l" title="' + esc(x.label) + '">' + esc(x.label) + '</span><span class="c">cell ' + esc(x.cell) + '</span></div>').join('') + '</div>' : '<div class="rt-line">None recorded: runs keep their printed output and figures.</div>') + '</div>';
            h += '<div class="rt-sec"><div class="h">Versions</div><div class="rt-vers">' + (r.versions || []).slice().reverse().map(x => '<div class="v"><b>v' + esc(x.number) + '</b><span>' + esc(fmtDate(x.created)) + ' · from the analysis of ' + esc(chainDate((x.promoted_from || {}).chain_id) || (x.promoted_from || {}).chain_id) + (x.change_note ? ' · “' + esc(x.change_note) + '”' : '') + '</span></div>').join('') + '</div></div>';
            h += '<div class="rt-sec"><div class="h">Results across runs <span class="n">— each run against the one before it</span></div>' + build.runsTable(r) + '</div>';
            h += '<div class="rt-sec"><div class="h">Runs <span class="n">— a run opens in the main panes</span></div>' + build.runsList(r) + '</div>';
            return h;
        },
        actions(r) {
            return '<button class="ui-btn primary" data-act="run" title="run the method on the data loaded now">' + ICON_ROUTINE + 'Run</button>' +
                '<a class="ui-btn ghost" href="/routines/' + esc(r.id) + '/script" download title="the script, with its inputs at the top">' + ICON_DOWN + '.py</a>' +
                '<button class="ui-btn ghost" data-act="rename">Rename</button><button class="ui-btn ghost danger-text" data-act="delete">Delete</button>';
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
        isoDay(d) { return d.toISOString().slice(0, 10); },
        loadSection(plan, pre, limits) {
            // the data: loaded as the original load asked for it (the window shifted to end today, the race picked, the
            // file uploaded), or the data loaded now; the fit line for the data loaded now - a load's is checked after it
            const d = (pre && pre.data) || {};
            const loaded = !!(pre && pre.loaded);
            const src = (plan && plan.source) || sourceKind(d.source);
            const nowLine = loaded ? '<span class="ui-chip model"><span class="t">' + esc(sourceLabel(d.source)) + '</span></span>' + (d.name ? '<span class="name">' + esc(d.name) + '</span>' : '') +
                '<span class="meta">' + [d.rows != null ? Number(d.rows).toLocaleString() + ' rows' : '', d.columns ? d.columns + ' columns' : '', d.date_range ? esc(d.date_range) : ''].filter(Boolean).join(' · ') + '</span>' : '';
            // the line under the data loaded now: green when nothing differs from the data the method was made on; a note when a
            // column will be empty or a file absent (the run goes ahead, the coach decides); bad when there is nothing to run on
            const differs = !!(pre && pre.ok && (((pre.fit || {}).missing || []).length || ((pre.aux || {}).absent || []).length || ((pre.fit || {}).retyped || []).length || (pre.values_notes || []).length));
            const fitLine = loaded ? '<div class="rt-fit' + (pre.ok ? (differs ? ' note' : '') : ' bad') + '" data-for="now">' + (pre.ok ? (differs ? '△ ' : '✓ ') : '! ') + esc(pre.line || '') + '</div>' : '';
            const today = new Date();
            let h = '<div class="rt-sec" data-source="' + esc(src) + '"><div class="h">Data</div><div class="rt-choices rt-load">';
            if (src === 'intervals' || src === 'sweatstack') {
                const days = Math.max(1, Number((plan && plan.window_days) || 28));
                const maxDays = limits && limits.max_days ? Number(limits.max_days) : null;
                const span = maxDays ? Math.min(days, maxDays) : days;
                const start = new Date(today.getTime() - span * 86400000);
                const label = src === 'intervals' ? 'Intervals.icu' : 'SweatStack';
                const withWhat = (src === 'intervals' ? (plan.aux_kinds || []) : (plan.sports || [])).join(', ');
                h += '<label class="rt-check"><input type="radio" name="rt-data" value="load" checked> Load from ' + label + '</label>' +
                    '<div class="rt-window rt-loadwin"><input type="date" class="ui-input" data-load="start" value="' + build.isoDay(start) + '"><span class="arrow">→</span><input type="date" class="ui-input" data-load="end" value="' + build.isoDay(today) + '"></div>' +
                    '<div class="help">the original’s ' + esc(days) + ' days, ending today' + (maxDays && days > maxDays ? ' (your plan allows ' + esc(maxDays) + ')' : '') +
                    (withWhat ? ' · with ' + esc(withWhat) : '') + (src === 'intervals' ? ' · metrics as the original' : (plan.users && plan.users.length ? ' · ' + esc(plan.users.length) + ' subject' + (plan.users.length === 1 ? '' : 's') + ' as the original' : '')) + '</div>' +
                    (src === 'intervals' ? '<div class="rt-cache" style="display:none"></div>' : '');
            } else if (src === 'endura') {
                h += '<label class="rt-check"><input type="radio" name="rt-data" value="load" checked> Load from Endura</label>' +
                    '<div class="rt-field rt-race"><select class="ui-input" data-load="race"><option value="">loading the races…</option></select>' +
                    '<div class="help">the original: ' + esc(plan.race_title || plan.race_id || 'a race') + (plan.aux_kinds && plan.aux_kinds.length ? ' · with ' + esc(plan.aux_kinds.join(', ')) : '') + '</div>' +
                    '<div class="rt-cache" style="display:none"></div></div>';
            } else {
                h += '<label class="rt-check"><input type="radio" name="rt-data" value="upload"' + (loaded ? '' : ' checked') + '> Upload a file' + (plan.name ? ' <span class="n">(the original: ' + esc(plan.name) + ')</span>' : '') + '</label>' +
                    '<div class="rt-field rt-upload"><input type="file" class="ui-input" data-load="file" accept=".csv,.parquet,.json,.xlsx,.xls,.txt,.tsv"></div>';
            }
            if (loaded) {
                h += '<label class="rt-check"><input type="radio" name="rt-data" value="now"' + (src !== 'intervals' && src !== 'endura' && src !== 'sweatstack' ? ' checked' : '') + '> The data loaded now</label><div class="rt-data rt-now">' + nowLine + '</div>' + fitLine;
            } else if (src !== 'intervals' && src !== 'endura' && src !== 'sweatstack') {
                h += '<div class="rt-line muted">Nothing is loaded now; upload the file to run on.</div>';
            }
            h += '<div class="rt-progress" style="display:none"></div></div></div>';
            return h;
        },
        runDialog(r, pre, limits) {
            const v = (r.versions || []).find(x => x.number === r.current_version) || (r.versions || [])[(r.versions || []).length - 1] || {};
            const params = (v.manifest || {}).parameters || [];
            let h = build.loadSection((pre && pre.plan) || {}, pre, limits);
            h += '<div class="rt-sec"><div class="h">Inputs <span class="n">— the only things that change; the method runs as it was saved</span></div>';
            if (!params.length) h += '<div class="rt-line">None: the method runs as it is.</div>';
            else h += params.map(p => '<div class="rt-field"><label>' + esc(p.label) + '</label>' + build.inputWidget(p) + (p.origin ? '<div class="help">' + esc(p.origin) + '</div>' : '') + '</div>').join('');
            h += '</div>';
            const runs = (r.runs || []).filter(x => x.version === r.current_version && ['ran', 'reproduced', 'differed'].includes(x.status));
            const last = runs.length ? runs[runs.length - 1] : null;
            const zero = v.run_zero && v.run_zero.verified;
            if (last || zero) {
                h += '<div class="rt-sec"><div class="h">Compare with</div><div class="rt-choices">' +
                    (last ? '<label class="rt-check"><input type="radio" name="rt-compare" value="previous" checked> run ' + esc(last.number) + ' (' + esc(fmtDate(last.created)) + ', the run before)</label>' : '') +
                    (zero ? '<label class="rt-check"><input type="radio" name="rt-compare" value="zero"' + (last ? '' : ' checked') + '> run 0 (the original data)</label>' : '') + '</div></div>';
            }
            return h;
        },
        num(x) { return x == null || x === '' ? '' : String(x); },
        ivl(s) { return s && s.low != null && s.high != null ? '[' + esc(s.low) + ', ' + esc(s.high) + ']' : ''; },
        markText(m) { return ({ up: '↑', down: '↓', same: '=', missing: '·', changed: '≠' })[m] || ''; },
        markWord(row) {
            if (row.mark === 'missing') return 'missing';
            if (row.overlap === true) return 'within';
            if (row.overlap === false) return 'moved';
            return row.mark === 'same' ? 'same' : 'changed';
        },
        comparisonTab(view) {
            const run = view.run || {}, c = run.comparison || {};
            const d = run.data || {};
            const head = run.number === 0 ? 'Run 0 — the original data' : ('Run ' + esc(run.number) + (d.name ? ' (' + esc(d.name) + ')' : '') + (run.against != null ? ' against run ' + esc(run.against) : ''));
            let h = '<div class="rt-cmp"><div class="rt-sec"><div class="h">' + head + ' <span class="n">— v' + esc(run.version) + (run.against != null ? ' · ' + esc(c.line || '') : '') + '</span></div>';
            if (run.status === 'failed' || run.status === 'timed_out') {
                h += '<div class="rt-error"><div class="msg">' + esc(run.line || '') + '</div>' + (run.error ? '<pre class="ui-code">' + esc(run.error) + '</pre>' : '') + '</div>';
            }
            const rows = c.rows || [];
            if (!rows.length) {
                h += '<div class="rt-line">' + (run.number === 0 || run.against == null ? 'Nothing to compare with: the first run of this version. Its results are on the Results tab.' : 'No result line to compare.') + '</div>';
            } else if (run.against == null) {
                h += '<table class="ui-table rt-cmp-table"><thead><tr><th>Result</th><th class="num">Run ' + esc(run.number) + '</th></tr></thead><tbody>' +
                    rows.map(x => '<tr><td class="label" title="' + esc(x.label) + '">' + esc(x.label) + '</td><td class="num">' + esc(build.num((x.now || {}).estimate)) + '<div class="ci">' + build.ivl(x.now) + '</div></td></tr>').join('') + '</tbody></table>';
            } else {
                h += '<table class="ui-table rt-cmp-table"><thead><tr><th>Result</th><th class="num">Run ' + esc(run.against) + '</th><th class="num">Run ' + esc(run.number) + '</th><th class="num">Change</th><th>Intervals</th></tr></thead><tbody>' +
                    rows.map(x => '<tr class="' + esc(x.mark) + '"><td class="label" title="' + esc(x.label) + '">' + esc(x.label) + '</td>' +
                        '<td class="num">' + esc(build.num((x.before || {}).estimate)) + '<div class="ci">' + build.ivl(x.before) + '</div></td>' +
                        '<td class="num">' + esc(build.num((x.now || {}).estimate)) + '<div class="ci">' + build.ivl(x.now) + '</div></td>' +
                        '<td class="num change">' + (x.change == null ? '' : esc((x.change > 0 ? '+' : '') + Number(x.change.toPrecision(3)))) + '</td>' +
                        '<td><span class="rt-mark ' + esc(x.mark) + '">' + build.markText(x.mark) + '</span> ' + build.markWord(x) + '</td></tr>').join('') + '</tbody></table>' +
                    '<div class="rt-legend">Estimates with their 95% intervals, as the routine printed them. "moved" means the two intervals do not overlap; "within" means they do; without intervals, "changed" and "same" compare the estimates. Nothing here is written by a model.</div>';
            }
            return h + '</div></div>';
        },
        dataTab(d, run) {
            const cols = d.columns || [];
            const ld = loadLabel(d.load);
            const subs = (run && run.bindings) || [];
            const absent = (run && run.aux_absent) || [];
            const bound = subs.length ? '<b>Files</b><span>' + subs.map(x => esc(String(x[0]).split('/').pop()) + ' → ' + esc(String(x[1]).split('/').pop())).join('<br>') + (absent.length ? '<br>' + esc(absent.join(', ')) + ': absent in this data (an empty table stood in)' : '') + '</span>' : (absent.length ? '<b>Files</b><span>' + esc(absent.join(', ')) + ': absent in this data (an empty table stood in)</span>' : '');
            return '<div class="rt-cmp"><div class="rt-sec"><div class="h">What this run ran on</div><div class="ui-kv">' +
                '<b>Source</b><span>' + esc(sourceLabel(d.source)) + '</span>' + (ld ? '<b>Loaded as</b><span>' + esc(ld) + '</span>' : '') + (d.name ? '<b>Name</b><span>' + esc(d.name) + '</span>' : '') + bound +
                (d.rows != null ? '<b>Rows</b><span>' + esc(Number(d.rows).toLocaleString()) + '</span>' : '') + (d.date_range ? '<b>Range</b><span>' + esc(d.date_range) + '</span>' : '') +
                (d.aux && d.aux.length ? '<b>Auxiliary</b><span>' + d.aux.map(a => esc(String(a).split('/').pop())).join(', ') + '</span>' : '') +
                '<b>Columns</b><span>' + (Array.isArray(cols) && cols.length && typeof cols[0] === 'object' ? cols.map(c => esc(c.name) + (c.dtype ? ' <span class="ui-muted">' + esc(c.dtype) + '</span>' : '')).join(', ') : esc(String(cols))) + '</span></div></div></div>';
        },
        spark(values) {
            const v = values.filter(x => x != null);
            if (v.length < 3) return '';
            const min = Math.min.apply(null, v), max = Math.max.apply(null, v), span = (max - min) || 1;
            const pts = v.map((x, i) => (4 + i * (64 / (v.length - 1))).toFixed(1) + ',' + (15 - (x - min) / span * 12).toFixed(1));
            return '<svg class="rt-spark" viewBox="0 0 72 18"><polyline points="' + pts.join(' ') + '"/><circle cx="' + pts[pts.length - 1].split(',')[0] + '" cy="' + pts[pts.length - 1].split(',')[1] + '" r="1.8"/></svg>';
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
        runsTable(r) {
            const v = (r.versions || []).find(x => x.number === r.current_version) || {};
            const lines = ((v.manifest || {}).results || []).filter(x => !x.dropped && x.estimate != null);
            const cols = [];
            if (v.run_zero && v.run_zero.verified) cols.push({ number: 0, created: v.run_zero.created, results: v.run_zero.results || [] });
            (r.runs || []).filter(x => x.version === r.current_version && ['ran', 'reproduced', 'differed'].includes(x.status)).forEach(x => cols.push({ number: x.number, created: x.created, results: x.results || [] }));
            if (!lines.length || !cols.length) return '<div class="rt-line muted">' + (!lines.length ? 'This routine records no result lines; its runs keep their output and figures.' : 'No run yet.') + '</div>';
            const all = ((v.manifest || {}).results || []);
            // the mark sits between the two numbers it compares, in a column of its own (2026-10-10: beside the second
            // number it read as a misplaced Trend); Trend holds the sparkline, so it appears with the third run
            const head = '<thead><tr><th>Result</th>' + cols.map((c, i) => (i ? '<th class="mark"></th>' : '') + '<th class="num">Run ' + esc(c.number) + '<span class="d">' + esc(fmtDate(c.created)) + '</span></th>').join('') + (cols.length > 2 ? '<th>Trend</th>' : '') + '</tr></thead>';
            const body = lines.map(line => {
                const pos = all.indexOf(line);
                const cells = cols.map(c => c.results[pos] || null);
                const vals = cells.map(x => x ? parseFloat(String(x.estimate).replace(/,/g, '')) : null);
                let tds = '<td class="label" title="' + esc(line.label) + '">' + esc(line.label) + '</td>';
                cells.forEach((x, i) => {
                    if (i) {
                        const mark = build.markOf(x, cells[i - 1]);
                        tds += '<td class="mark">' + (mark === 'missing' ? '' : '<span class="rt-mark ' + esc(mark) + '">' + build.markText(mark) + '</span>') + '</td>';
                    }
                    tds += '<td class="num"' + (x ? ' title="' + build.ivl(x).replace(/"/g, '') + '"' : '') + '>' + (x ? esc(x.estimate) : '<span class="rt-mark missing">·</span>') + '</td>';
                });
                if (cols.length > 2) tds += '<td>' + build.spark(vals) + '</td>';
                return '<tr>' + tds + '</tr>';
            }).join('');
            return '<table class="ui-table rt-runs">' + head + '<tbody>' + body + '</tbody></table><div class="rt-legend">Between two runs: ↑ ↓ when the intervals do not overlap, = when they do; · a line the run did not print. Hover a number for its interval.' + (cols.length > 2 ? ' Trend: the numbers across the runs.' : '') + '</div>';
        },
        runsList(r) {
            const items = (r.runs || []).slice().reverse().map(x => {
                const d = x.data || {};
                const inputs = Object.keys(x.inputs || {}).length ? Object.entries(x.inputs).map(([k, val]) => esc(k) + ' = ' + esc(Array.isArray(val) ? val.join(', ') : val)).join(' · ') : '';
                const status = x.status === 'reproduced' ? 'reproduced' : (x.status === 'ran' ? ((x.comparison || {}).moved ? 'ran · ' + x.comparison.moved + ' of ' + x.comparison.compared + ' moved' : 'ran') : x.status.replace('_', ' '));
                return '<div class="ui-item rt-run" data-run="' + esc(x.number) + '"><span class="n">run ' + esc(x.number) + '</span><span class="w"><b>' + esc(fmtDate(x.created)) + '</b> ' + esc(sourceLabel(d.source)) + (d.name ? ': ' + esc(d.name) : '') + (d.date_range ? ' · ' + esc(d.date_range) : '') + ' · v' + esc(x.version) + (inputs ? ' · ' + inputs : '') + '</span>' +
                    '<span class="rt-status ' + esc(x.status) + '">' + status + '</span><span class="open">open →</span></div>';
            });
            const v = (r.versions || []).find(x => x.number === r.current_version) || {};
            if (v.run_zero && v.run_zero.verified) items.push('<div class="ui-item rt-run" data-run="0"><span class="n">run 0</span><span class="w"><b>' + esc(fmtDate(v.run_zero.created)) + '</b> the analysis\u2019s own data · v' + esc(v.number) + '</span><span class="rt-status reproduced">reproduced</span><span class="open">open →</span></div>');
            return items.length ? '<div class="ui-list rt-runlist">' + items.join('') + '</div>' : '<div class="rt-line muted">None yet.</div>';
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
    let manager = null, managerState = { list: [], current: null };

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
            if (ch) { dialog.querySelectorAll('.rt-version .ui-choice').forEach(x => x.classList.toggle('on', x === ch)); const f = dialog.querySelector('.rt-change'); if (f) f.style.display = ch.getAttribute('data-version') === 'next' ? '' : 'none'; return; }
            const seg = e.target.closest('.rt-results .ui-seg > span');
            if (seg) { seg.parentNode.querySelectorAll('span').forEach(x => x.classList.toggle('on', x === seg)); }
        });
        return dialog;
    }
    function dialogParts() {
        const d = ensureDialog();
        return { d, sub: d.querySelector('.ui-dlg-h .sub'), body: d.querySelector('.ui-dlg-b'), note: d.querySelector('.ui-dlg-f .note'), createBtn: d.querySelector('[data-act="create"]'), cancelBtn: d.querySelector('[data-act="cancel"]') };
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
        const p = dialogParts(); p.d.style.display = 'none'; dialogState = null;
    }
    function propose() {
        const st = dialogState; if (!st) return;
        const p = dialogParts();
        st.busy = true; st.proposal = null;
        p.body.innerHTML = build.loading('Analyst', '');
        p.createBtn.style.display = 'none';
        p.cancelBtn.disabled = true;
        stream('/routines/propose', { thread_id: st.thread_id, chain_id: st.chain_id }, !st.fromCard).then(msg => {
            if (dialogState !== st) return;
            st.busy = false; p.cancelBtn.disabled = false;
            st.proposal = msg.routine_proposal;
            const pr = st.proposal;
            const under = st.threadRoutines;
            p.sub.textContent = 'from this chain · ' + pr.cells + ' cell' + (pr.cells === 1 ? '' : 's') + ' · ' + (pr.results || []).length + ' result' + ((pr.results || []).length === 1 ? '' : 's') + (pr.figures && pr.figures.count ? ' · ' + pr.figures.count + ' figure' + (pr.figures.count === 1 ? '' : 's') : '') + (pr.cost ? ' · $' + Number(pr.cost).toFixed(2) : '');
            p.body.innerHTML = build.proposal(pr, under);
            p.note.textContent = under.length
                ? 'The new version is checked once on this chain’s data before it replaces the current one; earlier versions stay runnable.'
                : 'The routine is checked once on this chain’s own data before it is created; the chain is saved as a favourite, and the routine links to it.';
            p.createBtn.style.display = '';
            p.createBtn.disabled = false;
            p.createBtn.querySelector('span').textContent = under.length ? 'Make it v' + (Number(under[0].version) + 1) : 'Create routine';
        }).catch(err => {
            if (dialogState !== st) return;
            st.busy = false; p.cancelBtn.disabled = false;
            p.body.innerHTML = build.error(err.message || String(err), true);
        });
    }
    function readChoices() {
        const st = dialogState, p = dialogParts();
        const under = st.threadRoutines;
        const onEl = p.d.querySelector('.rt-version .ui-choice.on');
        const nextOn = !!(under.length && onEl && onEl.getAttribute('data-version') === 'next');
        const field = n => { const el = p.d.querySelector('[data-field="' + n + '"]'); return el ? el.value.trim() : ''; };
        return {
            proposal_id: st.proposal.proposal_id, name: field('name') || st.proposal.name, purpose: field('purpose'),
            drop_inputs: Array.from(p.d.querySelectorAll('input[data-drop]:checked')).map(x => x.getAttribute('data-drop')),
            drop_results: Array.from(p.d.querySelectorAll('.rt-results .r.flag')).filter(r => { const on = r.querySelector('.ui-seg .on'); return on && on.getAttribute('data-keep') === '0'; }).map(r => [Number(r.getAttribute('data-cell')), Number(r.getAttribute('data-index'))]),
            change_note: field('change_note'), routine_id: nextOn ? under[0].id : null
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
            toast('Routine made: ' + name + ' · v' + made.version + (made.run_zero && made.run_zero.verified ? ' · verified on the original data' : ' · not verified'));
            if (!st.fromCard) await ensureFavourite(st.chain_id);
            if (typeof updateRankButtonVisibility === 'function') updateRankButtonVisibility();
            refreshBadge();
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
            const runItem = e.target.closest('.rt-run');
            if (runItem && managerState.current) { const n = Number(runItem.getAttribute('data-run')); closeManager(); viewRun(managerState.current.id, n); return; }
            const b = e.target.closest('[data-act]'); if (!b || !managerState.current) return;
            const r = managerState.current;
            if (b.getAttribute('data-act') === 'run') { openRun(r.id); return; }
            if (b.getAttribute('data-act') === 'delete') {
                if (!confirm('Delete the routine “' + r.name + '” and its runs? The analysis it was made from stays in Saved workflows.')) return;
                const res = await fetchJson('/routines/' + encodeURIComponent(r.id), { method: 'DELETE' });
                if (res.ok) { forgetOrigins(); toast('Routine deleted'); loadManager(); refreshBadge(); if (window.WorkflowModal && typeof window.WorkflowModal.refresh === 'function') window.WorkflowModal.refresh(); }
            } else if (b.getAttribute('data-act') === 'rename') {
                const name = prompt('Rename the routine', r.name);
                if (!name || name.trim() === r.name) return;
                const res = await fetchJson('/routines/' + encodeURIComponent(r.id) + '/rename', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ name: name.trim() }) });
                if (res.ok) { forgetOrigins(); loadManager(r.id); }
            }
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
        return fetchJson('/routines/' + encodeURIComponent(id)).then(res => {
            if (!res.ok) { body.innerHTML = build.error('This routine could not be loaded.', false); return; }
            const r = res.json.routine; managerState.current = r;
            const hd = build.routineHeader(r);
            title.innerHTML = hd.title; sub.innerHTML = hd.sub; actions.innerHTML = build.actions(r); body.innerHTML = build.routineBody(r);
        });
    }

    // ------------------------------------------------------------ the run dialog (S3, the data loaded now)
    let runDlg = null, runState = null;
    function ensureRunDialog() {
        if (runDlg) return runDlg;
        runDlg = document.createElement('div'); runDlg.id = 'routineRunModal'; runDlg.className = 'modal ui-modal'; runDlg.style.display = 'none';
        runDlg.innerHTML = '<div class="modal-content ui-dlg routine-dlg run-dlg">' +
            '<div class="ui-dlg-h"><div><div class="title">Run</div><div class="sub"></div></div><span class="sp"></span><button class="x" aria-label="Close">×</button></div>' +
            '<div class="ui-dlg-b"></div>' +
            '<div class="ui-dlg-f"><span class="note">The method runs as it was saved; only the inputs change. The run is recorded as it completes.</span><span class="sp"></span><button class="ui-btn" data-act="cancel">Cancel</button><button class="ui-btn primary" data-act="run">' + ICON_ROUTINE + '<span>Run</span></button></div></div>';
        document.body.appendChild(runDlg);
        runDlg.addEventListener('click', e => {
            if (e.target === runDlg || e.target.closest('.ui-dlg-h .x')) { closeRun(); return; }
            const b = e.target.closest('[data-act]'); if (!b) return;
            if (b.getAttribute('data-act') === 'cancel') closeRun();
            else if (b.getAttribute('data-act') === 'run') startRun();
        });
        runDlg.addEventListener('change', e => {
            if (e.target.matches('input[name="rt-data"]') || e.target.matches('input[data-load="file"]')) {
                if (e.target.matches('input[data-load="file"]')) { const up = runDlg.querySelector('input[name="rt-data"][value="upload"]'); if (up) up.checked = true; }
                updateRunButton();
            }
            if (e.target.matches('input[data-load="start"], input[data-load="end"], select[data-load="race"]')) { clearTimeout(cacheTimer); cacheTimer = setTimeout(checkCache, 250); }
        });
        runDlg.addEventListener('input', e => {             // a date being typed (Safari commits it on blur only): the line follows the typing
            if (e.target.matches('input[data-load="start"], input[data-load="end"]')) { clearTimeout(cacheTimer); cacheTimer = setTimeout(checkCache, 400); }
        });
        return runDlg;
    }
    function runParts() {
        const d = ensureRunDialog();
        return { d, sub: d.querySelector('.ui-dlg-h .sub'), title: d.querySelector('.ui-dlg-h .title'), body: d.querySelector('.ui-dlg-b'), runBtn: d.querySelector('[data-act="run"]'), cancelBtn: d.querySelector('[data-act="cancel"]') };
    }
    function openRun(routineId) {
        if (typeof queryRunning !== 'undefined' && queryRunning) { toast('An analysis is running; run the routine when it has finished.'); return; }
        runState = { id: routineId, routine: null, pre: null, busy: false };
        const p = runParts();
        p.d.style.display = 'flex'; p.title.textContent = 'Run'; p.sub.textContent = ''; p.body.innerHTML = build.loading('', '').replace('The analyst is reading the chain and naming its inputs…', 'Reading the routine and checking the data loaded now…');
        p.runBtn.disabled = true; p.cancelBtn.disabled = false;             // Cancel was held while the last run started
        Promise.all([fetchJson('/routines/' + encodeURIComponent(routineId)), fetchJson('/routines/' + encodeURIComponent(routineId) + '/precheck', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: '{}' })]).then(([rr, pr]) => {
            if (!runState || runState.id !== routineId) return;
            if (!rr.ok) { p.body.innerHTML = build.error('This routine could not be loaded.', false); return; }
            runState.routine = rr.json.routine; runState.pre = pr.ok ? pr.json : { loaded: false, ok: false, line: (pr.json && pr.json.error) || 'the check could not run' };
            runState.plan = (runState.pre && runState.pre.plan) || {};
            const r = runState.routine;
            p.title.textContent = 'Run: ' + r.name; p.sub.textContent = 'v' + r.current_version + ' · ' + (r.runs || []).length + ' run' + ((r.runs || []).length === 1 ? '' : 's') + ' so far';
            const src = runState.plan.source || 'file';
            const after = limits => {
                if (!runState || runState.id !== routineId) return;
                runState.limits = limits || null;
                p.body.innerHTML = build.runDialog(r, runState.pre, limits);
                if (src === 'endura') fillRaces(p, runState.plan);
                updateRunButton();
                checkCache();
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
        if (src === 'intervals') return { source: 'intervals', start_date: q('input[data-load="start"]').value, end_date: q('input[data-load="end"]').value, metrics: plan.metrics || [], aux_kinds: plan.aux_kinds || [] };
        if (src === 'endura') { const race = q('select[data-load="race"]'); return { source: 'endura', race_id: race ? race.value : '', race_title: race && race.selectedIndex >= 0 ? race.options[race.selectedIndex].textContent : '', aux_kinds: plan.aux_kinds || [] }; }
        if (src === 'sweatstack') return { source: 'sweatstack', start_date: q('input[data-load="start"]').value, end_date: q('input[data-load="end"]').value, sports: plan.sports || [], metrics: plan.metrics || [], users: plan.users || [] };
        const f = q('input[data-load="file"]');
        return { source: 'file', name: f && f.files && f.files.length ? f.files[0].name : '' };
    }
    // whether the load asked for is already in the executor's cache with every file the routine wants (2026-10-11: a run
    // re-downloaded a window loaded minutes before): asked once the dialog is up and again as the window or the race
    // changes; the answer under the window, and the load takes the cached frame and files instead of downloading
    let cacheTimer = null;
    function cacheAsk(asked) {
        // what to ask the cache about, or null when the dialog has no complete window or event yet
        if (asked.source === 'intervals') return asked.start_date && asked.end_date ? { start: asked.start_date, end: asked.end_date } : null;
        if (asked.source === 'endura') return asked.race_id ? { race_id: asked.race_id } : null;
        return null;
    }
    function askCache(st, asked) {
        const body = cacheAsk(asked);
        if (!body) return Promise.resolve(null);
        return fetchJson('/routines/' + encodeURIComponent(st.id) + '/cached', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) })
            .then(res => (res.ok && res.json) || { hit: false, line: '' }).catch(() => ({ hit: false, line: '' }));
    }
    function showCache(p, c) {
        const el = p.d.querySelector('.rt-cache'); if (!el) return;
        if (!c || !c.line) { el.style.display = 'none'; el.textContent = ''; el.className = 'rt-cache'; return; }
        el.style.display = ''; el.className = 'rt-cache ' + (c.hit ? 'hit' : 'miss'); el.textContent = (c.hit ? '✓ ' : '') + c.line;
    }
    function checkCache() {
        // the line under the window: a preview as the dates are set; the load asks again for itself when Run is pressed
        const st = runState; if (!st || !st.plan) return;
        const p = runParts();
        const asked = loadAsked(st.plan, p);
        if (!cacheAsk(asked)) { showCache(p, null); return; }
        askCache(st, asked).then(c => { if (runState === st) showCache(p, c); });
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
        let on = false;
        if (c === 'load') on = true;
        else if (c === 'upload') { const f = p.d.querySelector('input[data-load="file"]'); on = !!(f && f.files && f.files.length); }
        else on = !!(st.pre && st.pre.ok);
        p.runBtn.disabled = st.busy || !on;
    }
    function fillRaces(p, plan) {
        const sel = p.d.querySelector('select[data-load="race"]'); if (!sel) return;
        fetchJson('/endura/get_races').then(res => {
            const races = (res.ok && res.json && res.json.races) || [];
            if (!races.length) { sel.innerHTML = '<option value="">no races (is the Endura key set?)</option>'; updateRunButton(); return; }
            sel.innerHTML = races.map(x => { const id = x.race_id != null ? x.race_id : (x.id != null ? x.id : x.raceid); const title = x.race_title || x.title || x.name || ('race ' + id);
                return '<option value="' + esc(id) + '"' + (String(id) === String(plan.race_id) ? ' selected' : '') + '>' + esc(title) + (x.race_date ? ' · ' + esc(x.race_date) : '') + '</option>'; }).join('');
            checkCache();
        }).catch(() => { sel.innerHTML = '<option value="">the races could not be listed</option>'; });
    }
    function progress(text, kind) {
        const p = runParts(); const el = p.d.querySelector('.rt-progress'); if (!el) return;
        if (!text) { el.style.display = 'none'; el.textContent = ''; return; }
        el.style.display = ''; el.className = 'rt-progress' + (kind ? ' ' + kind : ''); el.textContent = text;
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
            showCache(p, c);
        }
        if (cached) {
            // the load is in the cache with every file the routine wants: the cached frame and files are taken through the
            // Dataset cache's own routes, the pills as a load's, no download
            progress('Taking it from the cache…', 'loading');
            const res = await fetchJson('/cache/load_primary', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ df_id: cached.df_id }) });
            if (!res.ok) throw new Error((res.json && res.json.error) || 'the cached data could not be loaded');
            for (const fp of cached.files || []) {
                const ar = await fetchJson('/cache/load_auxiliary', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ file_path: fp }) });
                if (!ar.ok) throw new Error((ar.json && ar.json.error) || ('the cached file ' + String(fp).split('/').pop() + ' could not be loaded'));
            }
            // a cached load around the window: the run cuts it to the window (the record says so); the session holds the cached load itself
            const load = Object.assign({}, asked, { cached: true }, cached.cut && cached.cut.length === 2 ? { cached_from: cached.cut } : {}, cached.key ? { key: cached.key } : {});
            if (src === 'intervals') {
                const held = cached.cut && cached.cut.length === 2 ? { start_date: cached.cut[0], end_date: cached.cut[1] } : { start_date: asked.start_date, end_date: asked.end_date };
                const info = Object.assign({ aux_datasets: plan.aux_kinds || [], shape: [cached.rows, null], columns: [] }, held);
                if (typeof createIntervalsPill === 'function') createIntervalsPill(info);
                if (typeof createIntervalsAuxiliaryPills === 'function' && (cached.files || []).length) createIntervalsAuxiliaryPills(cached.files, info);
                dfTab(res.json);
                return { source: 'intervals', start: asked.start_date, end: asked.end_date, aux: cached.files || [], load,
                         loaded: 'Intervals.icu ' + asked.start_date + ' → ' + asked.end_date + (cached.cut ? ' · cut from the cache' : ' · from the cache') + ((plan.aux_kinds || []).length ? ' · ' + plan.aux_kinds.join(', ') : '') };
            }
            if (typeof createOrUpdateDatasetPill === 'function') {
                createOrUpdateDatasetPill('endura-pill-' + Date.now(), 'Endura (' + (asked.race_title || asked.race_id) + ') loaded', 'endura', 'success', false, null);
                (cached.files || []).forEach((fp, i) => createOrUpdateDatasetPill('endura-aux-pill-' + Date.now() + '-' + i, 'Auxiliary (' + String(fp).split('/').pop().replace('.csv', '') + ')', 'auxiliary', 'success', false, fp));
            }
            dfTab(res.json);
            return { source: 'endura', aux: cached.files || [], load, loaded: 'Endura · ' + (asked.race_title || asked.race_id) + ' · from the cache' };
        }
        if (src === 'intervals') {
            const start = q('input[data-load="start"]').value, end = q('input[data-load="end"]').value;
            if (!start || !end || start >= end) throw new Error('the window needs a start before its end');
            progress('Starting the load from Intervals.icu…', 'loading');
            const res = await fetchJson('/intervals/load_data', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ start_date: start, end_date: end, metrics: plan.metrics || [], aux_datasets: plan.aux_kinds || [] }) });
            if (!res.ok) throw new Error((res.json && res.json.error) || 'the load could not start');
            const jobId = res.json.job_id;
            const t0 = Date.now();
            while (Date.now() - t0 < 600000) {
                await sleep(1000);
                const jr = await fetchJson('/intervals/job/' + encodeURIComponent(jobId));
                const job = jr.json || {};
                if (job.status === 'completed') {
                    const info = { start_date: start, end_date: end, aux_datasets: plan.aux_kinds || [], shape: (job.result || {}).shape, columns: (job.result || {}).columns };
                    if (typeof createIntervalsPill === 'function') createIntervalsPill(info);
                    if (typeof createIntervalsAuxiliaryPills === 'function' && job.result && job.result.aux_datasets && job.result.aux_datasets.length) createIntervalsAuxiliaryPills(job.result.aux_datasets, info);
                    dfTab(job);
                    return { source: 'intervals', start, end, aux: (job.result || {}).aux_datasets || [], load: asked, loaded: 'Intervals.icu ' + start + ' → ' + end + ((plan.aux_kinds || []).length ? ' · ' + plan.aux_kinds.join(', ') : '') };
                }
                if (job.status === 'error' || job.status === 'not_found') throw new Error(job.error || 'the load failed');
                progress((job.message || 'Loading…') + (job.percent != null ? ' (' + job.percent + '%)' : ''), 'loading');
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
        st.busy = true; p.runBtn.disabled = true; p.cancelBtn.disabled = true;
        const choice = dataChoice();
        let loaded = null;
        if (choice !== 'now') {
            // the load, as the original load asked for its data; its progress here, in the dialog - what it replaces cleared first
            try {
                progress('Clearing the data loaded now…', 'loading');
                await clearLoaded(choice === 'upload' ? 'primary' : 'all');
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
            progress('');
            const routine = st.routine;
            p.d.style.display = 'none'; runState = null;
            closeManager();                                   // the run shows in the main panes; the manager would cover them
            const numbers = runNumbers(routine);
            enterRunView(summaryOf(routine), numbers.concat([numbers.length ? Math.max.apply(null, numbers) + 1 : 1]), numbers.length, { pending: true, version: routine.current_version });
            if (loaded && typeof paneLookup === 'function') paneLookup({ kind: 'load', query: loaded.loaded || '', peek: (pr.json && pr.json.line) || '', sources: [], passages: [] });
            stream('/routines/' + encodeURIComponent(routine.id) + '/run', { values, compare_with, aux: auxLoaded, load: loadDone }, true, data => {
                if (data.type === 'pane_routine_end' && typeof paneRoutineEnd === 'function') { paneRoutineEnd(data); chipIdle(); return true; }
                return false;
            }).then(msg => {
                const out = msg.routine_run;
                finishRunView(out);
                refreshBadge();
                if (manager && manager.style.display !== 'none') loadManager(routine.id);
            }).catch(err => {
                chipIdle();
                if (typeof paneSystem === 'function') paneSystem(err.message || String(err), 'error');
                toast('The run did not go through: ' + (err.message || err));
                if (viewState) { viewState.numbers = runNumbers(routine); viewState.index = Math.max(0, viewState.numbers.length - 1); viewState.pending = false; updateRunNav(); }
            });
        });
    }
    function summaryOf(r) { return { id: r.id, name: r.name, current_version: r.current_version, source: r.source }; }
    function chipIdle() { if (window.containerStatus && typeof window.containerStatus.setExecuting === 'function') window.containerStatus.setExecuting(false); }   // the executor chip back to its polled status (a run sets it as a cell does)
    function runNumbers(r) {
        const v = (r.versions || []).find(x => x.number === r.current_version) || {};
        const out = (v.run_zero && v.run_zero.verified) ? [0] : [];
        return out.concat((r.runs || []).map(x => x.number));
    }

    // ------------------------------------------------------------ a run in the main panes (S4): one run per view, the arrows between runs
    let viewState = null;
    function inRunView() { return !!viewState; }
    function enterRunView(routine, numbers, index, meta) {
        viewState = { routine, numbers: numbers || [], index: index || 0, pending: !!(meta && meta.pending), version: meta && meta.version };
        const so = document.getElementById('streamOutput'); if (so) so.innerHTML = '';
        if (typeof clearAllTabs === 'function') clearAllTabs();
        const number = viewState.numbers[viewState.index];
        if (typeof paneRunIds === 'function') paneRunIds({ name: routine.name, run: (number != null ? number : '…') + ' · v' + (viewState.version || routine.current_version), df_id: (typeof currentData !== 'undefined' && currentData.df_id) || '' });
        if (typeof paneRunStrip === 'function') paneRunStrip({ mode: 'Routine', run: number != null ? number : '…', version: viewState.version || routine.current_version, estimate: '' });
        composerLock();
        if (typeof updateRankButtonVisibility === 'function') updateRankButtonVisibility();
        updateRunNav();
    }
    function finishRunView(out) {
        if (!viewState) return;
        const run = out.run, numbers = out.numbers || viewState.numbers;
        viewState.numbers = numbers; viewState.index = Math.max(0, numbers.indexOf(run.number)); viewState.pending = false; viewState.routine = out.routine || viewState.routine;
        if (typeof paneRunIds === 'function') paneRunIds({ name: viewState.routine.name, run: run.number + ' · v' + run.version, df_id: (run.data || {}).df_id || '' });
        const c = run.comparison || {};
        if (typeof paneRunStrip === 'function') paneRunStrip({ mode: 'Routine', run: run.number, version: run.version, idle: true, estimate: run.against != null ? 'run ' + run.against + ' — ' + (c.line || '') : (c.line || '') });
        if (typeof createOrUpdateTab === 'function') createOrUpdateTab('comparison', build.comparisonTab({ run }));
        updateRunNav();
        toast('Run ' + run.number + ' recorded · ' + (run.line || run.status));
    }
    function viewRun(routineId, number) {
        if (typeof queryRunning !== 'undefined' && queryRunning) { toast('An analysis is running; open the run when it has finished.'); return; }
        return fetchJson('/routines/' + encodeURIComponent(routineId) + '/runs/' + encodeURIComponent(number)).then(res => {
            if (!res.ok) { toast('This run could not be opened: ' + ((res.json && res.json.error) || res.status), 'error'); return; }
            const view = res.json, run = view.run;
            const numbers = view.numbers || [number];
            enterRunView(view.routine, numbers, Math.max(0, numbers.indexOf(run.number)), { version: run.version });
            const d = run.data || {};
            const cells = run.cells != null ? run.cells + ' cell' + (run.cells === 1 ? '' : 's') : '';
            if (typeof paneLookup === 'function') {
                const ld = loadLabel(d.load);
                if (ld && run.number !== 0 && sourceKind((d.load || {}).source) !== 'file') paneLookup({ kind: 'load', query: ld, peek: '', sources: [], passages: [] });
                paneLookup({ kind: 'check', query: d.name || sourceLabel(d.source), peek: (d.rows != null ? Number(d.rows).toLocaleString() + ' rows · ' : '') + ((d.columns || []).length || d.columns || 0) + ' columns' + (run.number === 0 ? ' · the analysis\u2019s own data' : ''), sources: [], passages: [] });
                paneLookup({ kind: run.number === 0 ? 'routine' : 'run', query: 'run ' + run.number + ' · v' + run.version + (cells ? ' · ' + cells : ''), peek: (run.line || run.status) + ' · ' + (run.figures || 0) + ' figure' + (run.figures === 1 ? '' : 's') + (run.elapsed != null ? ' · ' + run.elapsed + ' s' : ''), sources: [], passages: [] });
                if (run.against != null) paneLookup({ kind: 'compare', query: 'with run ' + run.against, peek: (run.comparison || {}).line || '', sources: [], passages: [] });
            }
            const c = run.comparison || {};
            if (typeof paneRoutineEnd === 'function') paneRoutineEnd({ number: run.number, name: view.name, version: run.version, status: run.status, line: run.line, results: (run.results || []).length, compared: c.compared || 0, moved: c.moved || 0, changed: c.changed || 0, missing: c.missing || 0, figures: run.figures || 0, elapsed: run.elapsed, against: run.against, comparison_line: c.line });
            if (typeof createOrUpdateTab === 'function') {
                createOrUpdateTab('comparison', build.comparisonTab(view));
                (view.figures || []).forEach(f => createOrUpdateTab('plot', f.data, f.id, f.format));
                if (view.stdout) createOrUpdateTab('code_exec_results', view.stdout);
                createOrUpdateTab('dataframe', build.dataTab(d, run));
                if (typeof activateTab === 'function') activateTab('comparison');
            }
            if (typeof paneRunIds === 'function') paneRunIds({ name: view.name, run: run.number + ' · v' + run.version, df_id: d.df_id || '' });
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
        if (pos) pos.textContent = viewState.pending ? 'run ' + viewState.numbers[i] + ' · running' : 'run ' + viewState.numbers[i] + ' of ' + (n ? viewState.numbers[n - 1] : 0);
        if (prev) prev.disabled = viewState.pending || i <= 0;
        if (next) next.disabled = viewState.pending || i >= n - 1;
    }

    // ------------------------------------------------------------ the rail entry and its badge
    function refreshBadge() {
        const badge = document.getElementById('routinesBadge'); if (!badge) return;
        fetchJson('/routines').then(res => {
            const n = ((res.json && res.json.routines) || []).length;
            badge.textContent = n ? String(n) : ''; badge.style.display = n ? '' : 'none';
        }).catch(() => {});
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

    // ------------------------------------------------------------ the composer lock (a run's view: nothing to ask)
    function composerLock(reason) {
        const input = document.getElementById('queryInput'), send = document.getElementById('submitQuery');
        if (input) { input.disabled = true; if (input.getAttribute('data-placeholder') == null) input.setAttribute('data-placeholder', input.placeholder || input.getAttribute('placeholder') || ''); input.placeholder = reason || 'A run is a record: to go further, open the analysis it was made from'; }
        if (send) send.disabled = true;
        document.body.classList.add('composer-locked');
    }
    function composerUnlock() {
        const input = document.getElementById('queryInput'), send = document.getElementById('submitQuery');
        if (input) { input.disabled = false; const was = input.getAttribute('data-placeholder'); if (was != null) { input.placeholder = was; input.removeAttribute('data-placeholder'); } }
        if (send) send.disabled = false;
        document.body.classList.remove('composer-locked');
    }

    function initialize() {
        bindPill(); bindRail();
        setTimeout(refreshBadge, 1500);
    }

    window.RoutinesUI = { initialize, openMake, openManager, closeManager, toggleSaveMenu: toggleMenu, hideSaveMenu: hideMenu, refreshBadge, forgetOrigins,
                          cardButton: build.cardButton, cardCount, bindCardButton, composerLock, composerUnlock, build,
                          openRun, viewRun, exitRunView, inRunView, navigateRuns, updateRunNav, enterRunView, runNumbers, clearLoaded };
    window.composerLock = composerLock; window.composerUnlock = composerUnlock;
    window.__routinesBuild = build;
})();
