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
        return ({ file: 'File', intervals: 'Intervals.icu', endura: 'Endura', sweatstack: 'SweatStack', frame: 'File', csv: 'File', none: 'No data' })[kind] || (kind || 'Data');
    }
    function valueText(p) {
        const v = p.default;
        if (p.type === 'date_window' && Array.isArray(v)) return v[0] + ' → ' + v[1];
        if (Array.isArray(v)) return v.join(', ');
        if (p.type === 'toggle') return v ? 'on' : 'off';
        return String(v == null ? '' : v);
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
            const rows = inputs.map(p => '<tr data-key="' + esc(p.key) + '"><td>' + esc(p.label) + (p.type === 'choice' && p.column ? '<span class="from"> · from ' + esc(p.column) + '</span>' : '') + '</td>' +
                '<td><span class="val">' + esc(valueText(p)) + '</span></td><td><span class="from">' + esc(p.origin || '') + '</span></td>' +
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
                ? '<table class="ui-table rt-inputs"><thead><tr><th>Input</th><th>Default</th><th>Where it comes from</th></tr></thead><tbody>' + params.map(p => '<tr><td>' + esc(p.label) + '</td><td><span class="val">' + esc(valueText(p)) + '</span></td><td><span class="from">' + esc(p.origin || '') + '</span></td></tr>').join('') + '</tbody></table>'
                : '<div class="rt-line">None: the method runs as it is on data of the same shape.</div>') + '</div>';
            const res = (m.results || []).filter(x => !x.dropped);
            h += '<div class="rt-sec"><div class="h">Results <span class="n">— compared run to run' + (m.figures && m.figures.count ? ' · ' + m.figures.count + ' figure' + (m.figures.count === 1 ? '' : 's') : '') + '</span></div>' +
                (res.length ? '<div class="rt-results">' + res.map(x => '<div class="r"><span class="g">✓</span><span class="l" title="' + esc(x.label) + '">' + esc(x.label) + '</span><span class="c">cell ' + esc(x.cell) + '</span></div>').join('') + '</div>' : '<div class="rt-line">None recorded: runs keep their printed output and figures.</div>') + '</div>';
            h += '<div class="rt-sec"><div class="h">Versions</div><div class="rt-vers">' + (r.versions || []).slice().reverse().map(x => '<div class="v"><b>v' + esc(x.number) + '</b><span>' + esc(fmtDate(x.created)) + ' · from the analysis of ' + esc(chainDate((x.promoted_from || {}).chain_id) || (x.promoted_from || {}).chain_id) + (x.change_note ? ' · “' + esc(x.change_note) + '”' : '') + '</span></div>').join('') + '</div></div>';
            h += '<div class="rt-sec"><div class="h">Runs</div><div class="rt-line muted">None yet — running a routine on new data is the next step of this feature.</div></div>';
            return h;
        },
        actions(r) {
            return '<a class="ui-btn ghost" href="/routines/' + esc(r.id) + '/script" download title="the script, with its inputs at the top">' + ICON_DOWN + '.py</a>' +
                '<button class="ui-btn ghost" data-act="rename">Rename</button><button class="ui-btn ghost danger-text" data-act="delete">Delete</button>';
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
    function stream(url, body, toPane) {
        const f = (window.authService && window.authService.fetch) ? window.authService.fetch.bind(window.authService) : fetch;
        return f(url, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) }).then(async resp => {
            if (!resp.ok) {
                const j = await resp.json().catch(() => ({}));
                throw new Error(j.message || j.error || ('the server answered ' + resp.status));
            }
            const reader = resp.body.getReader(); const dec = new TextDecoder(); let buf = ''; let closing = null;
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
                    if (data.routine_proposal || data.routine_made || data.routine_error) { closing = data; continue; }
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
            const b = e.target.closest('[data-act]'); if (!b || !managerState.current) return;
            const r = managerState.current;
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
                          cardButton: build.cardButton, cardCount, bindCardButton, composerLock, composerUnlock, build };
    window.composerLock = composerLock; window.composerUnlock = composerUnlock;
    window.__routinesBuild = build;
})();
