// documents.js - documents attached to a thread (docs/DOCUMENTS_DESIGN.md section 6).
// The "Document" entry of the paperclip menu and its hidden file input; one Documents pill in the top
// bar (blue, apart from the green dataset pills) that carries the spinner while a file is parsed, the
// refusal sentence when one is refused, and otherwise "Documents (n/4)" with a hover list of the
// documents and their remove icons; the Documents view - a thread-level dialog in the Dataset cache's
// shape, the list on the left, the selected document's map and text on the right, a page or section
// at a time; and the restore: the pill follows the page's thread, so an opened thread shows its
// documents again. Server: web_app/documents_routes.py. Nothing here is per chain: the right pane's
// tabs are snapshotted per chain and saved into favourites, and a thread's documents do not belong there.
(function () {
    'use strict';
    const MAX = 4;
    const state = { threadId: null, documents: [], loading: null, error: null, selected: null, cache: {}, open: false };
    const esc = s => String(s == null ? '' : s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
    const fetchFn = () => (window.authService && window.authService.fetch) ? window.authService.fetch.bind(window.authService) : window.fetch;
    const pageThread = () => { try { const t = (typeof currentData !== 'undefined' && currentData) ? currentData.thread_id : null; return t == null || t === '' ? null : String(t); } catch (e) { return null; } };
    const ICON = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"></path><polyline points="14 2 14 8 20 8"></polyline><line x1="8" y1="13" x2="16" y2="13"></line><line x1="8" y1="17" x2="14" y2="17"></line></svg>';
    const REMOVE = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor"><circle cx="12" cy="12" r="10"></circle><line x1="8" y1="12" x2="16" y2="12"></line></svg>';

    function meta(d) {
        if (d.pages) return d.pages + ' page' + (d.pages === 1 ? '' : 's');
        return (d.words || 0).toLocaleString() + ' words';
    }

    // ---- the pill ----
    function renderPill() {
        const host = document.getElementById('datasetStatusPillsContainer');
        if (!host) return;
        let pill = document.getElementById('documentsPill');
        if (!(state.documents.length || state.loading || state.error)) { if (pill) pill.remove(); return; }
        if (!pill) { pill = document.createElement('div'); pill.setAttribute('id', 'documentsPill'); host.appendChild(pill); }
        const st = state.error ? 'error' : (state.loading ? 'loading' : 'success');
        pill.className = 'dataset-status-pill documents-pill ' + st;
        pill.setAttribute('onmouseenter', 'documentsMenuPlace(this)');
        let label, title;
        if (state.error) { label = esc(state.error); title = 'Click to dismiss'; }
        else if (state.loading) { label = 'parsing ' + esc(state.loading) + '…'; title = 'Upload, parse and map: one request'; }
        else { label = 'Documents (' + state.documents.length + '/' + MAX + ')'; title = 'Click to open the documents of this thread'; }
        const rows = (!state.error && state.documents.length) ? '<div class="documents-pill-menu">' + state.documents.map(d =>
            '<div class="row" onclick="documentsOpen(\'' + esc(d.id) + '\')"><span class="id">' + esc(d.id) + '</span><span class="file">' + esc(d.file) + '</span><span class="meta">· ' + esc(meta(d)) + '</span><span class="sp"></span>' +
            '<span class="rm dataset-pill-remove-icon" title="Remove ' + esc(d.id) + '" onclick="event.stopPropagation(); documentsRemove(\'' + esc(d.id) + '\')">' + REMOVE + '</span></div>').join('') + '</div>' : '';
        pill.innerHTML = '<span class="dataset-pill-content clickable-pill-content" title="' + esc(title) + '" onclick="documentsPillClick()">' + ICON + '<span class="label">' + label + '</span>' + (state.loading ? '<div class="file-upload-spinner"></div>' : '') + '</span>' + rows;
    }
    // the hover list is position: fixed (the pills container clips what overflows it), placed under the pill as the pointer arrives
    window.documentsMenuPlace = function (pill) {
        const menu = pill && pill.querySelector ? pill.querySelector('.documents-pill-menu') : null;
        if (!menu || typeof pill.getBoundingClientRect !== 'function') return;
        const r = pill.getBoundingClientRect();
        menu.style.left = Math.max(8, r.left) + 'px';
        menu.style.top = (r.bottom + 4) + 'px';
    };
    window.documentsPillClick = function () {
        if (state.error) { state.error = null; renderPill(); return; }
        if (state.loading) return;
        window.documentsOpen();
    };

    // ---- the listing follows the page's thread ----
    function setListing(j) {
        state.documents = (j && j.documents) || [];
        for (const id of Object.keys(state.cache)) if (!state.documents.some(d => d.id === id)) delete state.cache[id];
        renderPill();
        if (state.open) renderDialog();
    }
    window.documentsOnThread = function (threadId) {
        const tid = threadId == null || threadId === '' ? null : String(threadId);
        if (tid === state.threadId && tid !== null) return Promise.resolve();
        state.threadId = tid; state.error = null; state.loading = null; state.cache = {}; state.selected = null;
        if (!tid) { setListing(null); return Promise.resolve(); }
        return fetchFn()('/documents/' + encodeURIComponent(tid), { method: 'GET' })
            .then(r => r.ok ? r.json() : { documents: [] })
            .then(j => { if (state.threadId === tid) setListing(j); })
            .catch(() => { if (state.threadId === tid) setListing(null); });
    };
    // the page sets currentData.thread_id in several places (a question's first answer, opening a thread,
    // navigating, a fresh start); watching it is simpler and safer than hooking each
    window.documentsSync = function () {
        const t = pageThread();
        if (t !== state.threadId) return window.documentsOnThread(t);
        return Promise.resolve();
    };

    // ---- upload ----
    window.documentsPick = function () {
        if (state.documents.length >= MAX) {
            if (typeof showUploadLimitMessage === 'function') showUploadLimitMessage('Maximum ' + MAX + ' documents per thread.');
            return;
        }
        const input = document.getElementById('documentFile');
        if (input && typeof input.click === 'function') input.click();
    };
    window.documentsUpload = function (file) {
        if (!file) return Promise.resolve(null);
        state.error = null; state.loading = file.name; renderPill();
        const fd = new FormData(); fd.append('file', file);
        const tid = pageThread() || state.threadId;
        if (tid) fd.append('thread_id', tid);
        return fetchFn()('/documents/upload', { method: 'POST', body: fd })
            .then(r => r.json().then(j => ({ ok: r.ok, j: j || {} })).catch(() => ({ ok: false, j: {} })))
            .then(({ ok, j }) => {
                state.loading = null;
                if (!ok) { state.error = j.message || 'The upload failed.'; renderPill(); return null; }
                if (j.thread_id) {
                    state.threadId = String(j.thread_id);
                    try {   // the upload started the thread: the page adopts the id, as it adopts a first answer's
                        if (typeof currentData !== 'undefined' && currentData && (currentData.thread_id == null || currentData.thread_id === '')) {
                            currentData.thread_id = /^\d+$/.test(String(j.thread_id)) ? Number(j.thread_id) : j.thread_id;
                        }
                    } catch (e) { /* no page state in a test */ }
                }
                setListing(j);
                if (j.document) { state.selected = j.document.id; window.documentsOpen(j.document.id); }
                return j;
            })
            .catch(e => { state.loading = null; state.error = 'The upload failed: ' + (e && e.message ? e.message : e); renderPill(); return null; });
    };
    window.documentsRemove = function (id) {
        const tid = state.threadId || pageThread();
        if (!tid || !id) return Promise.resolve(null);
        return fetchFn()('/documents/' + encodeURIComponent(tid) + '/' + encodeURIComponent(id), { method: 'DELETE' })
            .then(r => r.json().catch(() => ({})))
            .then(j => { if (state.selected === id) state.selected = null; setListing(j); return j; })
            .catch(() => null);
    };

    // ---- the Documents view: a thread-level dialog ----
    function ensureDialog() {
        let modal = document.getElementById('documentsModal');
        if (modal) return modal;
        modal = document.createElement('div');
        modal.setAttribute('id', 'documentsModal');
        modal.className = 'modal ui-modal';
        modal.innerHTML = '<div class="modal-content ui-dlg lg docs-dlg">' +
            '<div class="ui-dlg-h"><div><div class="title">Documents</div><div class="sub docs-sub"></div></div><span class="sp"></span>' +
            '<button class="close x" aria-label="Close" onclick="documentsClose()">×</button></div>' +
            '<div class="docs-body"><div class="docs-list"></div><div class="docs-view"></div></div></div>';
        document.body.appendChild(modal);
        return modal;
    }
    window.documentsOpen = function (id) {
        const modal = ensureDialog();
        state.open = true;
        if (id) state.selected = id;
        if (!state.selected && state.documents.length) state.selected = state.documents[0].id;
        modal.style.display = 'flex';
        renderDialog();
        if (state.selected) loadDocument(state.selected);
    };
    window.documentsClose = function () {
        const modal = document.getElementById('documentsModal');
        if (modal) modal.style.display = 'none';
        state.open = false;
    };
    window.documentsSelect = function (id) { state.selected = id; renderDialog(); loadDocument(id); };
    window.documentsOpenUnit = function (uid) {
        // a [D1.17] chip in the answer: the view opens on that document, at that unit, highlighted
        const id = String(uid).split('.')[0];
        window.documentsOpen(id);
        (state.cache[id] ? Promise.resolve() : loadDocument(id)).then(() => {
            renderDialog();
            const modal = document.getElementById('documentsModal');
            const el = modal && document.getElementById('unit-' + String(uid));          // the id has a dot: not a selector
            if (!el) return;
            modal.querySelectorAll('.docs-unit.hit').forEach(x => x.classList.remove('hit'));
            el.classList.add('hit');
            let g = el.parentNode; while (g && g.tagName !== 'DETAILS') g = g.parentNode;
            if (g) g.open = true;
            if (el.scrollIntoView) el.scrollIntoView({ block: 'center' });
        });
    };

    function loadDocument(id) {
        const tid = state.threadId || pageThread();
        if (!tid || state.cache[id]) { renderDialog(); return Promise.resolve(); }
        const base = '/documents/' + encodeURIComponent(tid) + '/' + encodeURIComponent(id);
        return Promise.all([fetchFn()(base + '/map', { method: 'GET' }).then(r => r.ok ? r.json() : null),
                            fetchFn()(base + '/text', { method: 'GET' }).then(r => r.ok ? r.json() : null)])
            .then(([m, t]) => { state.cache[id] = { map: m ? m.map : '', units: t ? (t.units || []) : [], file: t ? t.file : '' }; if (state.open) renderDialog(); })
            .catch(() => { state.cache[id] = { map: '', units: [], error: 'The document could not be loaded.' }; if (state.open) renderDialog(); });
    }

    function groups(units) {
        // a PDF by page, the others by their first heading level
        const out = []; let cur = null;
        for (const u of units) {
            const key = u.page ? 'p.' + u.page : (u.section ? '§' + String(u.section).split(' > ')[0] : '');
            if (!cur || cur.key !== key) { cur = { key, units: [] }; out.push(cur); }
            cur.units.push(u);
        }
        return out;
    }
    function table(rows) {
        if (!rows || !rows.length) return '';
        const w = Math.max(...rows.map(r => r.length));
        const cell = (r, i, tag) => '<' + tag + '>' + esc(r[i] == null ? '' : r[i]) + '</' + tag + '>';
        const head = '<tr>' + Array.from({ length: w }, (_, i) => cell(rows[0], i, 'th')).join('') + '</tr>';
        const body = rows.slice(1).map(r => '<tr>' + Array.from({ length: w }, (_, i) => cell(r, i, 'td')).join('') + '</tr>').join('');
        return '<table class="docs-table">' + head + body + '</table>';
    }
    window.documentsRenderUnits = function (units) {
        const marks = window.documentsReadMarks || {};          // the units this thread's READs quoted (stream-pane.js,)
        return groups(units).map((g, gi) => '<details class="docs-group"' + (gi === 0 ? ' open' : '') + '><summary>' + esc(g.key || 'text') + ' <span class="n">' + g.units.length + ' unit' + (g.units.length === 1 ? '' : 's') + '</span></summary>' +
            g.units.map(u => '<div class="docs-unit ' + esc(u.kind) + (marks[u.id] ? ' read' : '') + '" id="unit-' + esc(u.id) + '"><span class="loc" title="' + esc(u.kind + (u.section ? ' · ' + u.section : '')) + '">' + esc(u.id) + '</span>' +
                (marks[u.id] ? '<span class="mark" title="quoted by a READ in this thread">read</span>' : '') + '<div class="txt">' +
                (u.kind === 'table' ? (u.caption ? '<div class="cap">' + esc(u.caption) + '</div>' : '') + table(u.rows) : esc(u.text)) + '</div></div>').join('') + '</details>').join('');
    };
    function renderDialog() {
        const modal = document.getElementById('documentsModal');
        if (!modal) return;
        const list = modal.querySelector('.docs-list'), view = modal.querySelector('.docs-view'), sub = modal.querySelector('.docs-sub');
        if (sub) sub.textContent = state.threadId ? state.documents.length + ' of ' + MAX + ' documents in this thread' : 'no thread yet';
        if (list) list.innerHTML = state.documents.length ? state.documents.map(d =>
            '<div class="docs-item' + (d.id === state.selected ? ' sel' : '') + '" onclick="documentsSelect(\'' + esc(d.id) + '\')"><div class="docs-item-head"><span class="id">' + esc(d.id) + '</span><span class="file">' + esc(d.file) + '</span>' +
            '<span class="sp"></span><span class="rm dataset-pill-remove-icon" title="Remove ' + esc(d.id) + '" onclick="event.stopPropagation(); documentsRemove(\'' + esc(d.id) + '\')">' + REMOVE + '</span></div>' +
            '<div class="docs-item-meta">' + esc(d.type) + ' · ' + esc(meta(d)) + ' · ' + esc(d.tables || 0) + ' table' + (d.tables === 1 ? '' : 's') + ' · ' + esc((d.uploaded_at || '').slice(0, 10)) + (d.embedded === false ? ' · no embeddings yet' : '') + '</div></div>').join('')
            : '<div class="docs-empty">No documents attached to this thread. Use the paperclip: Document.</div>';
        if (!view) return;
        const d = state.documents.find(x => x.id === state.selected);
        if (!d) { view.innerHTML = '<div class="docs-empty">Select a document to read it.</div>'; return; }
        const c = state.cache[d.id];
        view.innerHTML = '<div class="docs-head"><span class="id">' + esc(d.id) + '</span> <span class="file">' + esc(d.file) + '</span></div>' +
            (c ? ('<pre class="docs-map">' + esc(c.map) + '</pre>' + (c.error ? '<div class="docs-empty">' + esc(c.error) + '</div>' : window.documentsRenderUnits(c.units))) : '<div class="docs-empty">Loading…</div>');
    }

    // ---- wiring: the attach entry, the file input, the watcher ----
    function init() {
        const option = document.querySelector('.document-option');
        if (option && option.addEventListener) option.addEventListener('click', window.documentsPick);
        const input = document.getElementById('documentFile');
        if (input && input.addEventListener) input.addEventListener('change', function () {
            const f = this.files && this.files[0]; this.value = '';
            if (f) window.documentsUpload(f);
        });
        if (typeof setInterval === 'function') { const t = setInterval(window.documentsSync, 800); if (t && t.unref) t.unref(); }
        window.documentsSync();
    }
    if (typeof document !== 'undefined' && document.readyState === 'loading' && document.addEventListener) document.addEventListener('DOMContentLoaded', init);
    else init();

    // exposed for tests
    window.__documentsState = state;
    window.__documentsRenderPill = renderPill;
})();
