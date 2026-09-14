// data-grid.js - the Data tab (2026-09-07).
//
// A paged, sortable grid over the primary dataframe. The server sends the first
// page with the chain (the 'dataframe' event carries {columns, dtypes, rows,
// offset, limit, total, order_by, ascending, df_id}); every other page is one
// GET /api/dataframe/page. The browser never holds more than one page.
// Cells render by dtype, not by column position. A saved favourite stores the
// rendered page as static HTML and restores it as such.

(function () {
    'use strict';
    function esc(s) { return String(s == null ? '' : s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;'); }
    function kindOf(dtype, name) {
        const d = String(dtype || '').toLowerCase(); const n = String(name || '').toLowerCase();
        if (d.startsWith('datetime') || d.startsWith('timedelta')) return 'dt';
        if (d === 'bool' || d === 'boolean') return 'bool';
        if (d.startsWith('int') || d.startsWith('uint') || d.startsWith('float') || d.startsWith('decimal')) return 'num';
        if (d === 'category') return 'cat';
        if (/(^|_)(id|uuid|key|code)$/.test(n) || n.endsWith('_id') || n === 'id') return 'id';
        return 'txt';
    }
    function fmt(v, kind) {
        if (v === null || v === undefined || v === '') return ['—', 'null'];
        if (kind === 'bool') return [v ? '✓' : '·', 'bool'];
        if (kind === 'num' && typeof v === 'number') return [Number.isInteger(v) ? v.toLocaleString() : v.toLocaleString(undefined, { maximumFractionDigits: 4 }), 'num'];
        return [String(v), kind];
    }
    const state = {};   // per tab element: {page (server payload), size, fetching}

    function build(page) {
        const cols = page.columns || [], dts = page.dtypes || [], rows = page.rows || [];
        const kinds = cols.map((c, i) => kindOf(dts[i], c));
        const from = (page.offset || 0) + 1, to = (page.offset || 0) + rows.length, total = page.total || rows.length;
        const sortLabel = page.order_by ? `sorted by <b>${esc(page.order_by)}</b> ${page.ascending ? 'ascending' : 'descending'} · <a href="#" class="dg-unsort">clear</a>` : '';
        const head = '<tr><th class="rn">#</th>' + cols.map((c, i) => `<th data-col="${esc(c)}" class="${page.order_by === c ? 'sorted' : ''}" title="sort by ${esc(c)}">${esc(c)}${page.order_by === c ? `<span class="arrow">${page.ascending ? '▲' : '▼'}</span>` : ''}<span class="t">${esc(dts[i] || '')}</span></th>`).join('') + '</tr>';
        const body = rows.map((r, ri) => `<tr><td class="rn">${(from + ri).toLocaleString()}</td>` + r.map((v, ci) => { const [txt, cls] = fmt(v, kinds[ci]); return `<td class="${cls}" title="${esc(v == null ? '' : v)}">${esc(txt)}</td>`; }).join('') + '</tr>').join('');
        const pages = Math.max(1, Math.ceil(total / (page.limit || 50))), cur = Math.floor((page.offset || 0) / (page.limit || 50));
        return `<div class="dg" data-df="${esc(page.df_id || '')}">
<div class="dg-bar"><span class="dims"><b>${total.toLocaleString()}</b> rows × <b>${cols.length}</b> columns</span><span class="sortlabel">${sortLabel}</span><span class="sp"></span>
<span>rows per page</span><select class="dg-size">${[25, 50, 100].map(n => `<option${n === (page.limit || 50) ? ' selected' : ''}>${n}</option>`).join('')}</select>
<span class="pager"><button class="dg-first" title="first page"${cur === 0 ? ' disabled' : ''}>«</button><button class="dg-prev" title="previous page"${cur === 0 ? ' disabled' : ''}>‹</button><span class="range">${from.toLocaleString()}–${to.toLocaleString()} of ${total.toLocaleString()}</span><button class="dg-next" title="next page"${cur >= pages - 1 ? ' disabled' : ''}>›</button><button class="dg-last" title="last page"${cur >= pages - 1 ? ' disabled' : ''}>»</button></span>
<span>go to row</span><input class="dg-jump" type="number" min="1" max="${total}" placeholder="${total.toLocaleString()}"></div>
<div class="dg-scroll"><table class="dg-table"><thead>${head}</thead><tbody>${body}</tbody></table></div>
<div class="dg-foot"><span><span class="k">dataframe</span> ${esc(page.df_id || '')}</span><span class="sp"></span><span class="dg-status">${page.ms != null ? 'page in ' + page.ms + ' ms' : ''}</span></div></div>`;
    }

    async function fetchPage(container, params) {
        const st = state[container.id] || (state[container.id] = {});
        if (st.fetching) return;
        st.fetching = true;
        const status = container.querySelector('.dg-status'); if (status) status.textContent = 'loading…';
        const q = new URLSearchParams({ offset: params.offset, limit: params.limit, order_by: params.order_by || '', ascending: params.ascending === false ? 'false' : 'true', df_id: params.df_id || '' });
        const t0 = Date.now();
        try {
            const f = window.authService ? window.authService.fetch('/api/dataframe/page?' + q) : fetch('/api/dataframe/page?' + q);
            const res = await f; const page = await res.json();
            if (!res.ok || page.error) throw new Error(page.error || ('HTTP ' + res.status));
            page.ms = Date.now() - t0;
            render(container, page);
        } catch (e) {
            if (status) status.textContent = 'could not load the page: ' + (e.message || e);
        } finally { st.fetching = false; }
    }

    function render(container, page) {
        const st = state[container.id] || (state[container.id] = {}); st.page = page;
        container.innerHTML = build(page);
        const limit = page.limit || 50, total = page.total || 0, pages = Math.max(1, Math.ceil(total / limit)), cur = Math.floor((page.offset || 0) / limit);
        const go = (offset, extra) => fetchPage(container, Object.assign({ offset, limit, order_by: page.order_by, ascending: page.ascending, df_id: page.df_id }, extra || {}));
        const on = (sel, fn) => { const el = container.querySelector(sel); if (el) el.onclick = fn; };
        on('.dg-first', () => go(0)); on('.dg-prev', () => go(Math.max(0, (cur - 1) * limit)));
        on('.dg-next', () => go(Math.min(pages - 1, cur + 1) * limit)); on('.dg-last', () => go((pages - 1) * limit));
        const size = container.querySelector('.dg-size'); if (size) size.onchange = () => go(0, { limit: parseInt(size.value, 10) });
        const jump = container.querySelector('.dg-jump'); if (jump) jump.onchange = () => { const r = Math.max(1, Math.min(total, parseInt(jump.value, 10) || 1)); go(Math.floor((r - 1) / limit) * limit); };
        const unsort = container.querySelector('.dg-unsort'); if (unsort) unsort.onclick = e => { e.preventDefault(); go(0, { order_by: null, ascending: true }); };
        container.querySelectorAll('th[data-col]').forEach(th => th.onclick = () => {
            const c = th.getAttribute('data-col');
            if (page.order_by !== c) go(0, { order_by: c, ascending: true });
            else if (page.ascending) go(0, { order_by: c, ascending: false });
            else go(0, { order_by: null, ascending: true });
        });
    }

    // entry: the 'dataframe' event's payload (an object) or a legacy HTML string
    window.renderDataGrid = function (container, data) {
        if (!container) return;
        if (data && typeof data === 'object' && Array.isArray(data.columns)) { render(container, data); return true; }
        container.innerHTML = typeof data === 'string' ? data : '';
        return false;
    };
    window.__dataGridBuild = build;
})();
