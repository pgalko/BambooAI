// codebook.js - the context codebook's screen (docs/CONTEXT_DESIGN.md §7 S3, §4 F4; 2026-10-16): the ways in - the
// Context card's line in the Intervals.icu load dialog (the codes, the proposals waiting, a link) and the Context pill's
// count and row - and the dialog behind them: the coder's proposals first with the passages they came from and the
// coach's decision on each (Confirm, Rename…, Merge into…, Decline), then the codes by group with their definition,
// status and the last load's uses, and the foot: Export, Import, and the line that a confirmed change applies from the
// next load. Intervals-only, so nothing universal (the rail, the gear menu) carries it: the book exists for the words
// an Intervals.icu load brings. Markup is built here on the app's own grammar (ui-*); the rules are in dialogs.css.
//
// Server routes (web_app/codebook_routes.py): GET /codebook (the view), POST /codebook/confirm {code, rename_to?,
// merge_into?}, POST /codebook/decline {code}, GET /codebook/export (the file), POST /codebook/import (a file).

(function () {
    'use strict';

    function esc(s) {
        return String(s == null ? '' : s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
    }
    function fmtDay(iso) {
        if (!iso) return '';
        try { const d = new Date(iso); return isNaN(d.getTime()) ? String(iso).slice(0, 10) : d.toLocaleDateString(undefined, { day: 'numeric', month: 'short' }); } catch (e) { return String(iso).slice(0, 10); }
    }
    function plural(n, one, many) { return n === 1 ? '1 ' + one : n + ' ' + many; }
    // the coder's seat name as the page shows it: the model's last path segment (deepseek/deepseek-v4.1-flash -> deepseek-v4.1-flash)
    function coderName(s) { s = String(s || ''); return s.includes('/') ? s.split('/').pop() : s; }

    // ------------------------------------------------------------ builders (pure: return HTML; tests read them)
    const build = {
        shell() {
            return '<div class="ui-dlg lg cb-dlg">' +
                '<div class="ui-dlg-h"><div><div class="title">Context codebook</div><div class="sub"></div></div><span class="sp"></span><button class="x" aria-label="Close">×</button></div>' +
                '<div class="ui-dlg-b"></div>' +
                '<div class="ui-dlg-f"><span class="note">A confirmed change applies from the next load; nothing already coded is re-coded.</span><span class="sp"></span>' +
                '<label class="ui-btn sm cb-import" title="A codebook exported from here or written by hand: every entry a code, a definition and a status"><input type="file" accept=".json,application/json" data-field="import" style="display:none">Import…</label>' +
                '<a class="ui-btn sm" href="/codebook/export" download title="The book as it is stored, as a file">Export</a></div></div>';
        },
        // the header's second line: the version, the codes, what the uses are
        sub(view) {
            const c = (view && view.counts) || {};
            const n = Number(c.codes || 0);
            return 'version ' + esc(view && view.version != null ? view.version : 1) + ' · ' + plural(n, 'code', 'codes') + (Number(c.used || 0) ? ' · uses from the last load' : ' · no load counted yet');
        },
        // the count in words: '' with nothing waiting
        count(n) { n = Number(n) || 0; return n ? plural(n, 'proposal', 'proposals') : ''; },
        // the Context card's line in the load dialog: the book's size, the proposals waiting as the link, or the plain way in
        cardLine(counts) {
            const c = counts || {}; const codes = Number(c.codes) || 0, n = Number(c.proposed) || 0;
            const link = n ? '<a href="#" id="contextCodebookLink">' + plural(n, 'proposal', 'proposals') + ' waiting<span class="n-badge">' + n + '</span></a>'
                : '<a href="#" id="contextCodebookLink">open the codebook</a>';
            return 'Coded against your codebook' + (codes ? ' · ' + plural(codes, 'code', 'codes') : '') + ' · ' + link;
        },
        body(view) {
            const active = [];
            ((view && view.groups) || []).forEach(g => (g.codes || []).forEach(c => active.push(c.code)));
            return build.proposals((view && view.proposals) || [], active) + build.groups((view && view.groups) || []);
        },
        proposals(list, active) {
            const h = '<div class="cb-sec cb-proposals"><div class="h">Proposals <span class="n">' + (list.length ? plural(list.length, 'code the coder asked for', 'codes the coder asked for') + ' · yours to decide' : 'none waiting') + '</span></div>';
            if (!list.length) return h + '<div class="cb-none">The coder proposes a code when none of the book’s fits a passage; a proposal is used meanwhile, its rows marked, until you decide here.</div></div>';
            return h + list.map(p => build.card(p, active)).join('') + '</div>';
        },
        card(p, active) {
            const ex = (p.examples || []).map(e => {
                const m = String(e).match(/^([A-Za-z]+\.\d+):\s*(.*)$/s);
                return '<div class="ex">' + (m ? '<span class="id">' + esc(m[1]) + '</span><span class="t">' + esc(m[2]) + '</span>' : '<span class="t">' + esc(e) + '</span>') + '</div>';
            }).join('');
            const by = p.proposed_by ? 'proposed by ' + esc(coderName(p.proposed_by)) : 'proposed by the coder';
            const on = p.proposed_on ? ' on ' + esc(fmtDay(p.proposed_on)) : '';
            const uses = Number(p.uses || 0);
            return '<div class="cb-card" data-code="' + esc(p.code) + '">' +
                '<div class="cb-head"><b class="code">' + esc(p.code) + '</b><span class="def">' + esc(p.definition) + '</span></div>' +
                '<div class="cb-meta">' + by + on + ' · ' + (uses ? 'on ' + plural(uses, 'passage', 'passages') + ' in the last load' : 'not used in the last load') + '</div>' +
                (ex ? '<div class="cb-examples">' + ex + '</div>' : '') +
                '<div class="cb-actions"><button class="ui-btn sm primary" data-act="confirm">Confirm</button><button class="ui-btn sm" data-act="rename">Rename…</button>' +
                '<button class="ui-btn sm" data-act="merge"' + (active.length ? '' : ' disabled') + '>Merge into…</button><span class="sp"></span><button class="ui-btn sm ghost danger-text" data-act="decline">Decline</button></div>' +
                '<div class="cb-inline"></div></div>';
        },
        renameForm(p) {
            return '<div class="cb-form"><label>Confirm under the name</label><input class="ui-input" data-field="rename" value="' + esc(p.code) + '" spellcheck="false">' +
                '<button class="ui-btn sm primary" data-act="rename-go">Confirm as this name</button><button class="ui-btn sm ghost" data-act="form-cancel">Cancel</button><span class="help">lower case, words joined by underscores; a name the book has is refused</span></div>';
        },
        mergeForm(p, active) {
            const opts = active.map(c => '<option value="' + esc(c) + '">' + esc(c) + '</option>').join('');
            return '<div class="cb-form"><label>Merge into</label><select class="ui-input" data-field="merge">' + opts + '</select>' +
                '<button class="ui-btn sm primary" data-act="merge-go">Merge</button><button class="ui-btn sm ghost" data-act="form-cancel">Cancel</button><span class="help">the proposal leaves the book; what it marked stays marked as it was</span></div>';
        },
        groups(list) {
            if (!list.length) return '<div class="cb-sec"><div class="h">Codes</div><div class="cb-none">The book holds no codes.</div></div>';
            return list.map(g => '<div class="cb-sec cb-group"><div class="h">' + esc(g.name) + ' <span class="n">' + plural((g.codes || []).length, 'code', 'codes') + '</span></div>' +
                '<table class="ui-table cb-table"><thead><tr><th>Code</th><th>Definition</th><th>Status</th><th class="num">Uses</th></tr></thead><tbody>' +
                (g.codes || []).map(build.row).join('') + '</tbody></table></div>').join('');
        },
        row(c) {
            const uses = Number(c.uses || 0);
            return '<tr data-code="' + esc(c.code) + '"><td class="code">' + esc(c.code) + '</td><td class="def">' + esc(c.definition) + '</td>' +
                '<td><span class="cb-status ' + esc(c.status || 'seeded') + '">' + esc(c.status || 'seeded') + '</span></td><td class="num">' + (uses ? uses : '<span class="ui-muted">–</span>') + '</td></tr>';
        },
        error(message) { return '<div class="cb-error">' + esc(message) + '</div>'; },
        wait(text) { return '<div class="cb-wait">' + esc(text || 'Reading the book…') + '</div>'; }
    };

    // ------------------------------------------------------------ state and the server
    let modal = null, view = null, busy = false;

    function fetchJson(url, opts) {
        const f = (window.authService && window.authService.fetch) ? window.authService.fetch.bind(window.authService) : fetch;
        return f(url, opts).then(r => r.json().then(j => ({ ok: r.ok, status: r.status, json: j })).catch(() => ({ ok: r.ok, status: r.status, json: {} })));
    }
    function toast(text, level) {
        if (typeof showSystemMessage === 'function') showSystemMessage(text); else console.log(text);
        if (level === 'error') console.error(text);
    }

    // ------------------------------------------------------------ the dialog
    function ensureModal() {
        if (modal) return modal;
        modal = document.createElement('div'); modal.id = 'codebookModal'; modal.className = 'codebook-modal-container ui-modal-plain'; modal.style.display = 'none';
        modal.innerHTML = build.shell();
        document.body.appendChild(modal);
        modal.addEventListener('click', e => {
            if (e.target === modal || e.target.closest('.ui-dlg-h .x')) { close(); return; }
            const b = e.target.closest('[data-act]'); if (!b) return;
            const card = b.closest('.cb-card'); const code = card ? card.getAttribute('data-code') : null;
            const act = b.getAttribute('data-act');
            if (act === 'confirm' && code) decide(card, { code });
            else if (act === 'decline' && code) decline(card, code);
            else if (act === 'rename' && code) inline(card, build.renameForm({ code }));
            else if (act === 'merge' && code) inline(card, build.mergeForm({ code }, activeCodes()));
            else if (act === 'form-cancel' && card) inline(card, '');
            else if (act === 'rename-go' && code) decide(card, { code, rename_to: (card.querySelector('[data-field="rename"]') || {}).value || '' });
            else if (act === 'merge-go' && code) decide(card, { code, merge_into: (card.querySelector('[data-field="merge"]') || {}).value || '' });
        });
        modal.addEventListener('keydown', e => {
            if (e.key === 'Enter' && e.target.matches && e.target.matches('[data-field="rename"]')) { e.preventDefault(); const card = e.target.closest('.cb-card'); if (card) decide(card, { code: card.getAttribute('data-code'), rename_to: e.target.value }); }
        });
        modal.addEventListener('change', e => {
            if (e.target.matches && e.target.matches('[data-field="import"]')) importFile(e.target);
        });
        return modal;
    }
    function parts() {
        const m = ensureModal();
        return { m, sub: m.querySelector('.ui-dlg-h .sub'), body: m.querySelector('.ui-dlg-b') };
    }
    function activeCodes() {
        const out = [];
        ((view && view.groups) || []).forEach(g => (g.codes || []).forEach(c => out.push(c.code)));
        return out;
    }
    function render(v) {
        view = v || view;
        const p = parts();
        p.sub.textContent = build.sub(view);
        p.body.innerHTML = build.body(view);
        setCount(view && view.counts ? view.counts.proposed : 0, view && view.counts);
    }
    function inline(card, html) {
        const slot = card.querySelector('.cb-inline'); if (!slot) return;
        slot.innerHTML = html;
        const inp = slot.querySelector('input, select'); if (inp && typeof inp.focus === 'function') { inp.focus(); if (typeof inp.select === 'function') inp.select(); }
    }
    function showError(card, message) {
        const slot = card && card.querySelector('.cb-inline');
        if (slot) slot.insertAdjacentHTML('beforeend', build.error(message)); else toast(message, 'error');
    }
    async function decide(card, body) {
        if (busy) return;
        busy = true;
        card.querySelectorAll('.cb-error').forEach(x => x.remove());
        try {
            const res = await fetchJson('/codebook/confirm', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) });
            if (!res.ok) { showError(card, res.json.error || ('the server answered ' + res.status)); return; }
            render(res.json);
            toast((body.merge_into ? body.code + ' merged into ' + body.merge_into : (body.rename_to ? body.code + ' confirmed as ' + body.rename_to : body.code + ' confirmed')) + ' · codebook v' + res.json.version);
            pillFollow(res.json.counts ? res.json.counts.proposed : 0);
        } catch (e) {
            showError(card, 'the decision could not be sent: ' + (e && e.message ? e.message : e));
        } finally { busy = false; }
    }
    async function decline(card, code) {
        if (busy) return;
        busy = true;
        try {
            const res = await fetchJson('/codebook/decline', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ code }) });
            if (!res.ok) { showError(card, res.json.error || ('the server answered ' + res.status)); return; }
            render(res.json);
            toast(code + ' declined');
            pillFollow(res.json.counts ? res.json.counts.proposed : 0);
        } catch (e) {
            showError(card, 'the decision could not be sent: ' + (e && e.message ? e.message : e));
        } finally { busy = false; }
    }
    async function importFile(input) {
        const file = input.files && input.files[0]; if (!file) return;
        const p = parts();
        try {
            const fd = new FormData(); fd.append('file', file);
            const res = await fetchJson('/codebook/import', { method: 'POST', body: fd });
            if (!res.ok) { p.body.insertAdjacentHTML('afterbegin', build.error('The file was not imported: ' + (res.json.error || ('the server answered ' + res.status)))); return; }
            render(res.json);
            toast('Codebook imported · v' + res.json.version);
            pillFollow(res.json.counts ? res.json.counts.proposed : 0);
        } catch (e) {
            p.body.insertAdjacentHTML('afterbegin', build.error('The file could not be sent: ' + (e && e.message ? e.message : e)));
        } finally { try { input.value = ''; } catch (e) { /* a file input that will not reset */ } }
    }
    async function refresh() {
        const p = parts();
        if (!view) p.body.innerHTML = build.wait();
        const res = await fetchJson('/codebook').catch(() => ({ ok: false, json: {} }));
        if (!res.ok) { p.body.innerHTML = build.error('The codebook could not be read' + (res.json && res.json.error ? ': ' + res.json.error : '') + '.'); return null; }
        render(res.json);
        return res.json;
    }
    function open() {
        const m = ensureModal();
        m.style.display = 'flex';
        refresh();
    }
    function close() { if (modal) modal.style.display = 'none'; }

    // ------------------------------------------------------------ the ways in: the Context card's line, the pill's count and row
    function setCount(n, counts) {
        const el = document.getElementById('contextCodebookLine'); if (!el) return;
        el.innerHTML = build.cardLine(counts || { proposed: n });
    }
    function pillFollow(n) {
        if (typeof window.contextPillProposals === 'function') window.contextPillProposals(Number(n) || 0);
    }
    // the count read from the book: at page load, when the load dialog opens, and whenever a coding pass ends (intervals.js calls it)
    function badge() {
        return fetchJson('/codebook').then(res => {
            if (!res.ok) return null;
            const n = res.json && res.json.counts ? Number(res.json.counts.proposed) || 0 : 0;
            setCount(n, res.json && res.json.counts); pillFollow(n);
            // the open dialog follows a book that moved under it (a pass ended); an unchanged book leaves a form being filled alone
            const moved = !view || view.version !== res.json.version || !view.counts || view.counts.proposed !== n;
            if (modal && modal.style.display !== 'none' && moved) render(res.json);
            return n;
        }).catch(() => null);
    }
    // the card's link sits inside a label whose click toggles the Context box (intervals.js): the link is taken first, in the
    // capture phase, and goes no further
    function bindCardLink() {
        if (bindCardLink.done) return;
        bindCardLink.done = true;
        document.addEventListener('click', e => {
            const a = e.target && e.target.closest ? e.target.closest('#contextCodebookLink') : null;
            if (!a) return;
            e.preventDefault(); e.stopPropagation();
            open();
        }, true);
    }
    function initialize() {
        bindCardLink();
        setTimeout(badge, 1800);
    }

    window.CodebookUI = { initialize, open, close, refresh, badge, build };
    window.__codebookBuild = build;
})();
