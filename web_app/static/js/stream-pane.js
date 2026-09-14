// stream-pane.js - the left pane (2026-09-06).
//
// One card per analyst turn: while a turn streams, its thinking shows as prose;
// when it completes, the card collapses to one line (kind + first sentence),
// with the note and the code folded beneath. Kernel results are status rows
// under their turn; look-ups and datasets carry pills; a sticky strip at the
// top shows mode, progress, spend and the analyst's best estimate so far; a
// closing card ends the run. Everything is static HTML (details/summary and
// inline handlers), so a saved favourite restores exactly as it looked.
//
// Server events handled here (all carry chain_id):
//   id               -> paneIds
//   pane_run_start   -> paneRunStart     {mode, of}
//   pane_turn_start  -> paneTurnStart    {turn, of, seat, model}
//   text (token)     -> paneToken        content tokens of the live turn
//   thought (token)  -> paneThought      reasoning-channel tokens of the live turn
//   pane_turn_end    -> paneTurnEnd      {turn, kind, peek, elapsed, cost, thinking, note, code}
//   pane_cell        -> paneCell         {cell_no, ok, peek, elapsed, chars, figs, error_line}
//   pane_lookup      -> paneLookup       {kind, query, peek, sources:[{title,url,host}]}
//   pane_heartbeat   -> paneHeartbeat    {turn, of, spent, dollars, estimate, mode}
//   pane_datasets    -> paneDatasets     {files:[{path,name,rows,size}]}
//   pane_run_end     -> paneRunEnd       {turns, of, cells, failed, cost, seconds, replay_status, replay_line, plots}
//   system_message   -> paneSystem(text) ; error -> paneSystem(text, 'error')

(function () {
    'use strict';

    // ------------------------------------------------------------ helpers
    function esc(s) {
        return String(s == null ? '' : s)
            .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
    }
    function jsq(s) {
        // a value inside a single-quoted JS string inside a double-quoted attribute
        return String(s == null ? '' : s).replace(/\\/g, '\\\\').replace(/'/g, "\\'").replace(/"/g, '&quot;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/&(?!(quot|lt|gt|amp);)/g, '&amp;');
    }
    function firstSentence(text, max) {
        const t = String(text || '').replace(/\s+/g, ' ').trim();
        if (!t) return '';
        const m = t.match(/^(.{20,}?[.!?])(\s|$)/);
        const s = (m ? m[1] : t);
        return s.length > (max || 140) ? s.slice(0, (max || 140) - 1) + '…' : s;
    }
    function firstCodeLine(code) {
        const lines = String(code || '').split('\n');
        for (const ln of lines) {
            const s = ln.trim();
            if (s && !s.startsWith('#')) return s;
        }
        return '';
    }
    function fmtSecs(s) {
        s = Number(s || 0);
        if (s < 60) return (s < 10 ? s.toFixed(1) : Math.round(s)) + ' s';
        return Math.floor(s / 60) + ' min ' + Math.round(s % 60) + ' s';
    }
    function fmtCost(c) { return '$' + Number(c || 0).toFixed(2); }
    function kindLabel(kind) {
        return ({ cell: 'cell', show: 'look-up', names: 'look-up', recall: 'memory', search: 'search',
                  ask: 'question', report: 'report', rewrite: 'plain-language version', infographic: 'infographic', error: 'lost' })[kind] || kind || '';
    }
    function noteGrid(note) {
        const rows = [];
        String(note || '').split('\n').forEach(ln => {
            const s = ln.trim().replace(/^[-•]\s*/, '');
            if (!s) return;
            const i = s.indexOf(':');
            if (i > 0 && i <= 40) rows.push('<b>' + esc(s.slice(0, i).trim()) + '</b><span>' + esc(s.slice(i + 1).trim()) + '</span>');
            else rows.push('<b></b><span>' + esc(s) + '</span>');
        });
        return rows.length ? '<div class="sp-note">' + rows.join('') + '</div>' : '';
    }
    const ICON_SEARCH = '<svg viewBox="0 0 24 24"><circle cx="11" cy="11" r="7"/><path d="M21 21l-4.3-4.3"/></svg>';
    const ICON_DOWNLOAD = '<svg viewBox="0 0 24 24"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="7 10 12 15 17 10"/><line x1="12" y1="15" x2="12" y2="3"/></svg>';

    // ------------------------------------------------------------ builders (pure: return HTML)
    const build = {
        ids(d) {
            const v = (k, val) => '<span><span class="k">' + k + '</span><span class="v" title="click to copy" onclick="navigator.clipboard&&navigator.clipboard.writeText(this.textContent)">' + esc(val || 'N/A') + '</span></span>';
            return '<div class="sp-ids">' + v('Workflow ID:', d.thread_id) + '<span class="sep">·</span>' + v('Chain ID:', d.chain_id) + '<span class="sep">·</span>' + v('Dataframe ID:', d.df_id) + '</div>';
        },
        strip(h) {
            const pct = h.of ? Math.min(100, Math.round(100 * (h.turn || 0) / h.of)) : 0;
            return '<span class="live"></span>' +
                (h.mode ? '<span class="mode">' + esc(h.mode) + '</span>' : '') +
                '<span>turn <b>' + esc(h.turn || 0) + '</b>' + (h.of ? ' of ' + esc(h.of) : '') + '</span>' +
                '<span class="bar"><i style="width:' + pct + '%"></i></span>' +
                '<span>' + fmtCost(h.spent) + (h.dollars ? ' / ' + fmtCost(h.dollars) : '') + '</span>' +
                '<span class="est"' + (h.estimate ? ' title="' + esc(h.estimate) + '"' : '') + '><b>Best estimate so far:</b> ' + esc(h.estimate || 'none yet') + '</span>';
        },
        turnStart(t) {
            const label = typeof t.turn === 'number' ? 'Turn ' + esc(t.turn) : (t.turn === 'rewrite' ? 'Rewrite' : (t.turn === 'infographic' ? 'Infographic' : esc(t.turn)));
            const seatModel = t.seat ? esc(t.seat) + (t.model ? ' · ' + esc(String(t.model).split('/').pop()) : '') : '';
            return '<details class="sp-turn live' + (t.quiet ? ' quiet' : '') + (t.review ? ' review' : '') + '"' + (t.quiet ? '' : ' open') + ' data-turn="' + esc(t.turn) + '"' +
                (t.review ? ' data-review="1" data-seat-model="' + seatModel + '"' : '') + '>' +
                '<summary><span class="chev"></span><span class="n">' + label + (t.review ? ' · review' : '') + '</span>' +
                '<span class="kind">' + (t.quiet ? 'working…' : 'thinking…') + '</span><span class="peek"></span>' +
                '<span class="meta">' + (t.seat ? esc(t.seat) + (t.model ? ' · ' + esc(String(t.model).split('/').pop()) : '') : 'streaming') + '</span>' +
                (t.seat && t.chain_id ? '<button class="agent-instructions-btn sp-prompt" type="button" title="the prompt this turn received (run log)" data-agent="' + esc(t.seat) + '" data-chain="' + esc(t.chain_id) + '" data-call="' + esc(t.call || 1) + '" onclick="event.preventDefault();">⌘</button>' : '') +
                '</summary>' +
                '<div class="sp-think"><span class="cursor"></span></div>' +
                '<details class="sp-reasoning"><summary><span class="chev"></span>reasoning</summary><pre class="sp-reasoning-body"></pre></details>' +
                '<div class="sp-detail"></div></details>';
        },
        turnDetail(t) {
            let h = '';
            if (t.note) h += noteGrid(t.note);
            if (t.code) h += '<pre><code class="language-python">' + esc(t.code) + '</code></pre>';
            return h;
        },
        cell(c) {
            const ok = !!c.ok;
            const badge = ok ? 'In&nbsp;[' + esc(c.cell_no) + ']' : 'In&nbsp;[&times;]';
            const meta = [c.elapsed != null ? fmtSecs(c.elapsed) : '', ok && c.chars != null ? Number(c.chars).toLocaleString() + ' chars' : '',
                          ok && c.figs ? c.figs + ' fig' : '', !ok ? 'rolled back' : ''].filter(Boolean).join(' · ');
            return '<div class="sp-row' + (ok ? '' : ' fail') + '"' + (ok && c.cell_no ? ' data-cell="' + esc(c.cell_no) + '" title="open on the Investigation tab" onclick="if(typeof paneOpenCell===\'function\')paneOpenCell(' + esc(c.cell_no) + ')"' : '') + '>' +
                '<span>' + (ok ? '✓' : '✗') + '</span><span class="in">' + badge + '</span>' +
                '<span class="out">' + esc(ok ? (c.peek || '(no output)') : (c.error_line || 'failed')) + '</span>' +
                '<span class="t">' + esc(meta) + '</span></div>';
        },
        lookup(l) {
            const label = ({ show: 'SHOW', names: 'NAMES', recall: 'RECALL', search: 'SEARCH' })[l.kind] || String(l.kind || '').toUpperCase();
            const glyph = l.kind === 'search' ? '⌕' : (l.kind === 'recall' ? '✦' : '↺');
            const right = l.kind === 'search' && l.sources && l.sources.length ? l.sources.length + ' source' + (l.sources.length === 1 ? '' : 's') : '';
            let h = '<div class="sp-row tool"><span>' + glyph + '</span><span class="in">' + label + (l.query ? ' ' + esc(l.query).slice(0, 60) : '') + '</span>' +
                '<span class="out">' + esc(l.peek || '') + '</span><span class="t">' + esc(right) + '</span></div>';
            if (l.sources && l.sources.length) {
                h += '<div class="sp-pills">' + l.sources.map(s =>
                    '<a class="sp-pill src" href="' + esc(s.url || '#') + '" target="_blank" rel="noopener noreferrer" title="' + esc(s.url || '') + '">' + ICON_SEARCH +
                    '<span class="t">' + esc(s.title || s.url || 'source') + '</span>' + (s.host ? '<span class="host">' + esc(s.host) + '</span>' : '') + '</a>').join('') + '</div>';
            }
            return h;
        },
        datasets(d) {
            const files = (d.files || []).map(f => {
                const name = f.name || String(f.path || '').split('/').pop();
                const sz = [f.rows ? f.rows + ' rows' : '', f.size || ''].filter(Boolean).join(' · ');
                return '<span class="sp-pill ds" title="download" onclick="if(typeof downloadFile===\'function\')downloadFile(\'' + jsq(f.path) + '\')">' + ICON_DOWNLOAD +
                    '<span class="t">' + esc(name) + '</span>' + (sz ? '<span class="sz">' + esc(sz) + '</span>' : '') + '</span>';
            });
            return files.length ? '<div class="sp-pills">' + files.join('') + '</div>' : '';
        },
        runEnd(r) {
            const rep = r.replay_status === 'reproduced' ? 'ok' : (r.replay_status ? 'warn' : '');
            const links = ['Answer', 'Simplified', 'Investigation'].concat(r.plots ? ['Plots (' + r.plots + ')'] : []).map(l =>
                '<a href="#" onclick="if(typeof paneOpenTab===\'function\')paneOpenTab(\'' + l.split(' ')[0] + '\');return false;">' + l + ' →</a>').join('');
            return '<div class="sp-done"><div class="title">' + (r.status === 'asked' ? 'The analyst has a question for you' : (r.status === 'stopped' ? 'Run stopped' : 'Run complete')) + '</div>' +
                '<div class="grid"><span>Turns <b>' + esc(r.turns) + (r.of ? ' of ' + esc(r.of) : '') + '</b></span>' +
                '<span>Cells <b>' + esc(r.cells || 0) + '</b>' + (r.failed ? ' (' + esc(r.failed) + ' failed)' : '') + '</span>' +
                '<span>Cost <b>' + fmtCost(r.cost) + '</b></span><span>Time <b>' + esc(fmtSecs(r.seconds)) + '</b></span></div>' +
                (r.replay_line ? '<div class="rep ' + rep + '">' + (rep === 'ok' ? '✓ ' : '') + esc(r.replay_line) + '</div>' : '') +
                (r.status === 'answered' ? '<div class="links">' + links + '</div>' : '') +
                (r.files && r.files.length ? build.datasets({ files: r.files }) : '') + '</div>';
        },
        system(text, level) {
            return '<div class="sp-sys' + (level === 'error' ? ' error' : '') + '">' + esc(text) + '</div>';
        }
    };

    // ------------------------------------------------------------ DOM glue
    let lastStrip = null;          // the last heartbeat, so the strip can be re-rendered
    let liveCard = null;           // the open turn card, while streaming
    let liveRaw = '';              // its content tokens so far
    let noteSeen = false;          // the reply reached its structured part

    function pane() { return (typeof liveTargets === 'function') ? liveTargets().stream : document.getElementById('streamOutput'); }
    function ensure() {
        const p = pane();
        if (!p) return null;
        let strip = p.querySelector('.sp-strip');
        if (!strip) {
            // a fresh chain: the pane starts with the strip, the ids line and the stream
            const placeholder = p.querySelector(':scope > div:not([class])');
            if (placeholder && /Ready for your query|New workflow started/.test(placeholder.textContent || '')) placeholder.remove();
            strip = document.createElement('div'); strip.className = 'sp-strip'; strip.style.display = 'none';
            p.appendChild(strip);
            const ids = document.createElement('div'); ids.className = 'sp-ids-slot'; p.appendChild(ids);
            const stream = document.createElement('div'); stream.className = 'sp-stream'; p.appendChild(stream);
        }
        return p;
    }
    function stream() { const p = ensure(); return p ? p.querySelector('.sp-stream') : null; }
    function append(html) {
        const s = stream(); if (!s || !html) return;
        s.insertAdjacentHTML('beforeend', html);
    }

    window.paneIds = function (d) {
        const p = ensure(); if (!p) return;
        const slot = p.querySelector('.sp-ids-slot');
        if (slot) slot.innerHTML = build.ids(d);
    };
    function renderStrip(h) {
        const p = ensure(); if (!p) return;
        const strip = p.querySelector('.sp-strip');
        lastStrip = Object.assign({}, lastStrip || {}, h);
        strip.style.display = '';
        strip.innerHTML = build.strip(lastStrip);
    }
    window.paneRunStart = function (ev) {
        lastStrip = null;
        renderStrip({ mode: ev.mode, turn: 0, of: ev.of, spent: 0, dollars: ev.dollars, estimate: '' });
        liveCard = null; liveRaw = ''; noteSeen = false;
    };
    window.paneHeartbeat = function (h) { renderStrip(h); };
    window.paneTurnStart = function (t) {
        window.paneTurnEnd({ turn: -1 });            // a card left open by a lost turn closes quietly
        if (typeof t.turn === 'number' && lastStrip) renderStrip({ turn: t.turn });
        // which call of this seat this card is, within the chain (2026-09-10): the prompt button asks the run log
        // for exactly this call, not the seat's first one; cards and log entries are appended in the same order
        const s0 = stream();
        t.call = 1 + (s0 && t.seat ? s0.querySelectorAll('.sp-prompt[data-agent="' + String(t.seat).replace(/"/g, '') + '"]').length : 0);
        append(build.turnStart(t));
        const s = stream();
        liveCard = s ? s.lastElementChild : null; liveRaw = ''; noteSeen = false;
    };
    window.paneToken = function (text) {
        if (!liveCard) return false;
        liveRaw += text;
        if (liveCard.classList.contains('quiet')) return true;      // a quiet card (the infographic's YAML) shows nothing
        if (noteSeen) return true;
        const cut = liveRaw.indexOf('###NOTE###');
        let visible = cut >= 0 ? liveRaw.slice(0, cut) : liveRaw;
        visible = visible.replace(/^\s*###THINKING###\s*/, '');
        const think = liveCard.querySelector('.sp-think');
        if (think) think.innerHTML = esc(visible) + '<span class="cursor"></span>';
        const peek = liveCard.querySelector('summary .peek');
        if (peek) peek.textContent = firstSentence(visible, 120);
        if (cut >= 0) {
            noteSeen = true;
            const kind = liveCard.querySelector('summary .kind');
            if (kind) kind.textContent = 'writing the note and the next step…';
        }
        return true;
    };
    window.paneThought = function (text) {
        if (!liveCard) return false;
        const body = liveCard.querySelector('.sp-reasoning-body');
        if (body) { body.textContent += text; liveCard.querySelector('.sp-reasoning').classList.add('has'); }
        return true;
    };
    window.paneTurnEnd = function (t) {
        if (!liveCard) return;
        const card = liveCard; liveCard = null;
        card.classList.remove('live');
        if (t.turn === -1) { card.classList.add('lost'); card.removeAttribute('open'); return; }
        const kind = card.querySelector('summary .kind'); if (kind) kind.textContent = kindLabel(t.kind);
        const peek = card.querySelector('summary .peek');
        if (peek) peek.textContent = t.peek || firstSentence(t.thinking, 120) || firstCodeLine(t.code);
        const meta = card.querySelector('summary .meta');
        // a self-review turn keeps its seat and model on the finished card (2026-09-10): the Reviewer's model is visible
        if (meta) meta.textContent = [t.elapsed != null ? fmtSecs(t.elapsed) : '', t.cost != null ? fmtCost(t.cost) : '',
                                      card.dataset.review === '1' ? (card.dataset.seatModel || '') : ''].filter(Boolean).join(' · ');
        const think = card.querySelector('.sp-think');
        if (think) { const c = think.querySelector('.cursor'); if (c) c.remove(); if (!think.textContent.trim()) think.remove(); }
        const detail = card.querySelector('.sp-detail');
        if (detail) {
            detail.innerHTML = build.turnDetail(t);
            if (window.hljs) detail.querySelectorAll('pre code').forEach(b => { try { window.hljs.highlightElement(b); } catch (e) { /* plain */ } });
        }
        const reasoning = card.querySelector('.sp-reasoning');
        if (reasoning && !reasoning.classList.contains('has')) reasoning.remove();
        card.removeAttribute('open');
    };
    window.paneCell = function (c) { append(build.cell(c)); };
    window.paneSummary = function (text) {
        // the run's call telemetry, kept with the closing card instead of a vanishing popup
        const s = stream(); if (!s || !text) return;
        const done = s.querySelectorAll('.sp-done'); const card = done[done.length - 1];
        const html = '<details class="sp-telemetry"><summary><span class="chev"></span>call telemetry</summary><pre>' + esc(text) + '</pre></details>';
        if (card) card.insertAdjacentHTML('beforeend', html); else append('<div class="sp-done">' + html + '</div>');
    };
    window.paneLookup = function (l) { append(build.lookup(l)); };
    window.paneDatasets = function (d) { append(build.datasets(d)); };
    window.paneRunEnd = function (r) {
        window.paneTurnEnd({ turn: -1 });
        const p = ensure(); if (!p) return;
        if (lastStrip) renderStrip({ turn: r.turns, spent: r.cost != null ? r.cost : lastStrip.spent });
        const strip = p.querySelector('.sp-strip');
        if (strip) { const live = strip.querySelector('.live'); if (live) live.classList.add('idle'); }
        append(build.runEnd(r));
        // the same provenance under the answer, where the reader is (2026-09-08)
        const answer = (typeof liveTargets === 'function') ? liveTargets().content.querySelector('#content-answer') : document.getElementById('content-answer');
        if (answer && r.status === 'answered') {
            const body = answer.querySelector('.markdown-content');
            if (body) {
                // the run's best estimate as the page's key figure, above the report
                const est = lastStrip && lastStrip.estimate ? String(lastStrip.estimate).replace(/^best estimate( so far)?:\s*/i, '') : '';
                if (est && !answer.querySelector('.answer-key')) {
                    const key = document.createElement('div'); key.className = 'answer-key';
                    key.innerHTML = '<span class="label">Best estimate</span><span class="value">' + esc(est) + '</span>';
                    const first = body.firstElementChild; const after = first && /^H[12]$/.test(first.tagName) ? first : null;
                    if (after && after.nextSibling) body.insertBefore(key, after.nextSibling); else body.insertBefore(key, body.firstChild);
                }
                // [cell n] and [fig n] markers become chips that open the cell or the plots
                if (!body.dataset.cited) {
                    body.dataset.cited = '1';
                    const walker = document.createTreeWalker(body, NodeFilter.SHOW_TEXT); const nodes = [];
                    while (walker.nextNode()) if (/\[(cell|fig)\s*\d+\]/.test(walker.currentNode.nodeValue)) nodes.push(walker.currentNode);
                    nodes.forEach(n => {
                        const span = document.createElement('span');
                        span.innerHTML = esc(n.nodeValue).replace(/\[(cell|fig)\s*(\d+)\]/g, (m, kind, num) =>
                            '<span class="cite ' + kind + '" onclick="' + (kind === 'fig' ? "if(typeof paneOpenTab==='function')paneOpenTab('Plots')" : "if(typeof paneOpenCell==='function')paneOpenCell(" + num + ")") + '">' + kind + ' ' + num + '</span>');
                        n.replaceWith(...span.childNodes);
                    });
                }
            }
            let foot = answer.querySelector('.answer-provenance');
            if (!foot) { foot = document.createElement('div'); foot.className = 'answer-provenance'; answer.appendChild(foot); }
            const rep = r.replay_status === 'reproduced' ? 'ok' : (r.replay_status ? 'warn' : '');
            foot.innerHTML = (r.replay_line ? '<span class="' + rep + '">' + (rep === 'ok' ? '✓ ' : '') + esc(r.replay_line) + '</span>' : '') +
                '<span>' + esc(r.cells || 0) + ' cells' + (r.failed ? ', ' + esc(r.failed) + ' failed' : '') + '</span>' +
                (r.plots ? '<span>' + esc(r.plots) + ' figure' + (r.plots === 1 ? '' : 's') + '</span>' : '') +
                '<span>' + fmtCost(r.cost) + ' · ' + esc(fmtSecs(r.seconds)) + '</span>';
        }
    };
    window.paneSystem = function (text, level) { append(build.system(text, level)); };

    // tab helpers the cards call (the right pane's tabs are named as their types)
    window.paneOpenTab = function (name) {
        const tab = Array.from(document.querySelectorAll('.tab, .tab-button, [data-tab]')).find(el => (el.textContent || '').trim().toLowerCase().startsWith(name.toLowerCase()));
        if (tab) tab.click();
    };
    window.paneOpenCell = function (n) {
        window.paneOpenTab('Investigation');
        setTimeout(() => {
            const head = Array.from(document.querySelectorAll('.nb-cell-idx')).find(el => (el.textContent || '').replace(/\s/g, '') === 'In[' + n + ']');
            if (head) head.scrollIntoView({ behavior: 'smooth', block: 'start' });
        }, 150);
    };

    // exposed for tests
    window.__paneBuild = build;
})();
