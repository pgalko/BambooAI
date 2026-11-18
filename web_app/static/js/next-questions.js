// next-questions.js - the questions that could follow a finished analysis (docs/ARCHITECT_DESIGN.md §2.7, §2.15;
// 2026-11-16). The closing card of a finished analysis carries a Next questions button. It opens the five levels; the
// one picked is asked of the server (POST /architect/next, a stream: one call of the Architect's), and the questions
// that come back are cards under the closing card, each saying which line of the brief or the report it comes from.
// A card's pencil changes its question; its arrow starts a new analysis with it at once (/query with `next`): no
// brief, and the Architect's switch does not apply.
//
// The cards are part of the analysis' own pane, kept with the chain as the rest of the pane is - in the page's copy
// and in a saved favourite - so a chain shown again has them with nothing else kept. A question that was run is
// marked on its card, and the pane of the run it started opens on a row saying what the question came from: that row
// is how the run's box on the thread map is marked. The page's words sit in WORDS; nothing here reaches a prompt.
//
// window.NextQuestionsUI = { initialize, dress, restore, holds, started, ran, made, build }

(function () {
    'use strict';

    const WORDS = {
        button: 'Next questions', buttonTitle: 'Questions that could follow this analysis',
        head: 'Next questions', one: 'Next question', reading: 'reading…', run: 'run', runTitle: 'Open its analysis',
        change: 'Change', go: 'Start the analysis', keep: 'Keep', cancel: 'Cancel', prompt: 'the prompt the Architect received (run log)',
        wait: 'The questions are being written. Wait for them.', busyRun: 'Another analysis is running. Wait for it to end, or stop it.',
        none: 'No questions were written', unreachable: 'the server could not be reached',
        // a level's key (analyst/next_questions.py), its name, and what it reads in one plain line
        levels: [['refine', 'Refine focus', 'the same question, narrower'], ['shift', 'Shift angle', 'another explanation of the result'],
                 ['test', 'Test boundaries', 'what the result rests on'], ['blend', 'Blend elements', 'two findings together'], ['emergence', 'Follow emergence', 'what did not fit']],
        // the kind of line a question comes from, after "From"
        from: { comparison: 'what was compared', measure: 'the measure', period: 'the period', check: 'also checked', proposal: 'a proposal not ticked', anchor: 'it rests on',
                would_change: 'what would change your mind', misfit: 'did not fit', asked: 'the question', found: 'the answer', earlier: 'an earlier answer' }
    };
    const QUESTION_CHARS = 4000;                  // a question, as analyst/brief.py bounds it
    const ICON = {
        plant: '<svg viewBox="0 0 24 24"><path d="M12 10a6 6 0 0 0 -6 -6h-3v2a6 6 0 0 0 6 6h3"/><path d="M12 14a6 6 0 0 1 6 -6h3v1a6 6 0 0 1 -6 6h-3"/><path d="M12 20l0 -10"/></svg>',
        pen: '<svg viewBox="0 0 24 24"><path d="M3 17.25V21h3.75L17.81 9.94l-3.75-3.75L3 17.25zM20.71 7.04c.39-.39.39-1.02 0-1.41l-2.34-2.34c-.39-.39-1.02-.39-1.41 0l-1.83 1.83 3.75 3.75 1.83-1.83z"/></svg>',
        go: '<svg viewBox="0 0 24 24"><path d="M2.01 21L23 12 2.01 3 2 10l15 2-15 2z"/></svg>',
        ok: '<svg viewBox="0 0 24 24"><path d="M9 16.17L4.83 12l-1.42 1.41L9 19 21 7l-1.41-1.41z"/></svg>',
        x: '<svg viewBox="0 0 24 24"><path d="M19 6.41L17.59 5 12 10.59 6.41 5 5 6.41 10.59 12 5 17.59 6.41 19 12 13.41 17.59 19 19 17.59 13.41 12z"/></svg>'
    };

    // ------------------------------------------------------------ helpers
    function esc(s) { return String(s == null ? '' : s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;'); }
    function byId(id) { return document.getElementById(id); }
    function say(text) { if (typeof showSystemMessage === 'function') showSystemMessage(text); }
    function levelName(key) { const l = WORDS.levels.find(x => x[0] === key); return l ? l[1] : String(key || ''); }
    function running() { return typeof queryRunning !== 'undefined' && queryRunning; }

    // ------------------------------------------------------------ builders (pure: return HTML)
    const build = {
        // the button on a closing card, in its row of what can be done next
        button() {
            return '<button type="button" class="sp-act sp-next" data-nq="open" title="' + WORDS.buttonTitle + '">' + ICON.plant + WORDS.button + '</button>';
        },
        // the five levels, a name and one plain line each
        menu() {
            return WORDS.levels.map(l => '<div class="it" data-nq="level" data-level="' + l[0] + '"><b>' + l[1] + '</b><span>' + l[2] + '</span></div>').join('');
        },
        // what a question comes from: the kinds of its lines in words, the lines themselves as the label's title
        from(lines) {
            lines = Array.isArray(lines) ? lines : [];
            const kinds = lines.map(l => WORDS.from[l.kind]).filter(Boolean);
            return '<div class="from" title="' + esc(lines.map(l => l.text).join('\n')) + '"><span class="l">' + (kinds.length ? 'From ' + esc(kinds.join(' and ')) : '') + '</span></div>';
        },
        // one question: where it comes from, its title and its text, the pencil and the arrow; q: {title, text, from, ran}
        card(q, k) {
            return '<div class="nq-card' + (q.ran ? ' ran' : '') + '" data-k="' + k + '">' + build.from(q.from) +
                '<div class="tx">' + (q.title ? '<b>' + esc(String(q.title).replace(/[.:\s]+$/, '')) + '.</b> ' : '') + '<span class="q">' + esc(q.text) + '</span></div>' +
                '<div class="tools"><button type="button" class="pen" data-nq="edit" title="' + WORDS.change + '">' + ICON.pen + '</button>' +
                '<button type="button" class="go" data-nq="run" title="' + WORDS.go + '">' + ICON.go + '</button></div>' +
                (q.ran ? build.was(q.ran) : '') + '</div>';
        },
        // the mark on a question that was run: it opens the analysis it started
        was(chain) {
            return '<button type="button" class="was" data-nq="goto" data-chain="' + esc(chain) + '" title="' + WORDS.runTitle + '">' + WORDS.run + '</button>';
        },
        // the line over a set, or over the row of a run a question started: what it is, and at which level
        head(what, level, rest) {
            return '<span class="k">' + what + '</span><span class="sep">·</span><span class="lv">' + esc(levelName(level)) + '</span>' + (rest || '');
        },
        // a set as the server keeps it ({level, questions, cost, chain}), at its place among the analysis' sets
        set(asked, at) {
            const cost = Number(asked.cost) || 0;
            const prompt = asked.chain ? '<button class="agent-instructions-btn sp-prompt" type="button" title="' + WORDS.prompt + '" data-agent="Architect" data-chain="' + esc(asked.chain) + '" data-call="1">⌘</button>' : '';
            return '<div class="nq-set" data-set="' + esc(at) + '" data-level="' + esc(asked.level) + '">' +
                '<div class="nq-head">' + build.head(WORDS.head, asked.level, '<span class="r">' + (cost >= 0.005 ? '$' + cost.toFixed(2) : '') + prompt + '</span>') + '</div>' +
                (asked.questions || []).map((q, k) => build.card(q, k)).join('') + '</div>';
        },
        // a set on its way
        waiting(level) {
            return '<div class="nq-set nq-wait"><div class="nq-head">' + build.head(WORDS.head, level) + '</div><div class="nq-reading">' + WORDS.reading + '</div></div>';
        },
        // the first row of the run a question started: the level it was asked at, and what it came from
        row(next) {
            return '<div class="nq-from" title="' + esc(next.lines || '') + '">' + build.head(WORDS.one, next.level, next.label ? '<span class="sep">·</span><span>' + esc(next.label) + '</span>' : '') + '</div>';
        },
        editor(text) {
            return '<div class="nq-edit"><textarea class="nq-input" rows="2" maxlength="' + QUESTION_CHARS + '">' + esc(text) + '</textarea>' +
                '<button type="button" class="ok" data-nq="keep" title="' + WORDS.keep + '">' + ICON.ok + '</button><button type="button" class="no" data-nq="cancel" title="' + WORDS.cancel + '">' + ICON.x + '</button></div>';
        }
    };

    // ------------------------------------------------------------ the page
    let asking = null;         // the set being written: {entry, level}
    let menu = null;           // the list of levels, once made

    function holder(html) { const d = document.createElement('div'); d.innerHTML = html || ''; return d; }
    // what is of the moment leaves a pane: a question open for a change, a set still on its way
    function tidy(pane) {
        pane.querySelectorAll('.nq-edit').forEach(e => e.remove());
        pane.querySelectorAll('.nq-wait').forEach(e => e.remove());
        pane.querySelectorAll('.nq-card.editing').forEach(c => c.classList.remove('editing'));
        return pane;
    }
    // the finished chain on screen; of one still running, that is said
    function finished() {
        const entry = responses[currentResponseIndex];
        if (entry && !entry.status) return entry;
        if (entry && entry.status === 'running') say(WORDS.busyRun);
        return null;
    }
    // a change to a finished chain's pane - the one on screen when the chain is in view, else its kept markup - written
    // back to the chain and to the page's store
    function change(entry, act) {
        const pane = responses[currentResponseIndex] === entry ? byId('streamOutput') : holder(entry.streamOutput);
        act(pane);
        entry.streamOutput = tidy(holder(pane.innerHTML)).innerHTML;      // as the chain keeps it: nothing of the moment
        if (typeof localforage !== 'undefined') Promise.resolve(localforage.setItem('responses', responses)).catch(() => { /* the page's copy is a courtesy */ });
    }
    function streamOf(pane) { return pane.querySelector('.sp-stream') || pane; }

    // the button on the closing card of every finished analysis in a pane that lacks it: a run that has just ended, or a
    // chain kept from before the button existed. It stands first in the card's row of what can be done next
    // (stream-pane.js): a run that was stopped or that asked, and a routine's run, have no such row
    function dress(pane) {
        if (!pane) return;
        pane.querySelectorAll('.sp-done .acts').forEach(row => {
            if (!row.querySelector('[data-nq="open"]')) row.insertBefore(holder(build.button()).firstElementChild, row.firstElementChild);
        });
    }
    // a chain shown again (loadResponseContent): its button where it is missing, and the set on its way, if one is.
    // An Explore chain of the retired ideas path is five questions, not an analysis: nothing follows from it
    function restore(entry) {
        const pane = byId('streamOutput');
        if (!pane || !entry || entry.status) return;
        tidy(pane);                                             // a pane kept by another hand (Save as routine) may hold the moment it was kept in
        if (!/user requested variations/i.test(entry.queryText || '')) dress(pane);
        if (asking && asking.entry === entry) streamOf(pane).insertAdjacentHTML('beforeend', build.waiting(asking.level));
    }

    // ---- the levels
    function hideMenu() { if (menu) menu.style.display = 'none'; }
    function showMenu(button) {
        if (!menu) {
            menu = document.createElement('div'); menu.className = 'save-menu nq-menu'; menu.id = 'nextLevels'; menu.style.display = 'none';
            menu.innerHTML = build.menu();
            document.body.appendChild(menu);
        }
        if (menu.style.display !== 'none') { hideMenu(); return; }
        menu.style.display = '';
        const r = button.getBoundingClientRect(), tall = menu.offsetHeight || 0, room = (typeof window !== 'undefined' && window.innerHeight) || 0;
        menu.style.left = Math.max(8, r.left) + 'px';
        menu.style.top = (room && r.bottom + 6 + tall > room ? Math.max(8, r.top - 6 - tall) : r.bottom + 6) + 'px';      // above the button where there is no room under it
    }

    // What the stream ends on: the route's closing message - the set and its place, or why none was made. A refusal
    // (the balance, the month's queries) is one JSON object; the model's own traffic is passed over.
    function closing(body) {
        let out = {};
        String(body || '').split('\n').forEach(line => {
            if (!line.trim()) return;
            let d = null;
            try { d = JSON.parse(line); } catch (e) { return; }
            if (d && d.next) out = d.next;
            else if (d && (d.message || d.error || d.routine_error)) out = { error: d.message || d.error || d.routine_error };
        });
        return out;
    }
    // A set of questions for the finished analysis `entry`, at a level: one at a time, and not while an analysis runs.
    // Resolves to whether a set was made; where none was, the reason is said.
    function ask(entry, level) {
        if (asking) { say(WORDS.wait); return Promise.resolve(false); }
        if (running()) { say(WORDS.busyRun); return Promise.resolve(false); }
        asking = { entry, level };
        const inView = () => responses[currentResponseIndex] === entry;
        if (inView()) { const pane = byId('streamOutput'); streamOf(pane).insertAdjacentHTML('beforeend', build.waiting(level)); pane.scrollTop = pane.scrollHeight; }
        return window.authService.fetch('/architect/next', { method: 'POST', headers: { 'Content-Type': 'application/json' },
                                                              body: JSON.stringify({ thread_id: entry.thread_id, chain_id: entry.chain_id, level }) })
            .then(r => r.text()).then(closing).catch(() => ({ error: WORDS.none + ': ' + WORDS.unreachable + '.' })).then(out => {
                asking = null;
                if (inView()) { const pane = byId('streamOutput'); pane.querySelectorAll('.nq-wait').forEach(e => e.remove()); }
                if (!out.set) { say(out.error || WORDS.none + '.'); return false; }
                change(entry, pane => streamOf(pane).insertAdjacentHTML('beforeend', build.set(out.set, out.at)));
                const made = inView() ? byId('streamOutput').querySelector('.nq-set[data-set="' + out.at + '"]') : null;
                if (made && made.scrollIntoView) made.scrollIntoView({ block: 'nearest' });      // the whole set in view; its head, where the pane is too short for all of it
                return true;
            });
    }
    // an analysis may not start while a set is being written: the two would share the instance's stream
    function holds() {
        if (!asking) return false;
        say(WORDS.wait);
        return true;
    }

    // ---- a card: its question changed, or run
    function inputOf(card) { return card.querySelector('.nq-input'); }
    function edit(card) {
        if (card.classList.contains('editing')) return;
        card.classList.add('editing');
        card.insertAdjacentHTML('beforeend', build.editor(card.querySelector('.q').textContent));
        const input = inputOf(card);
        input.value = card.querySelector('.q').textContent;
        input.focus(); grow(input);
    }
    function grow(input) { if (input.style && input.scrollHeight) { input.style.height = 'auto'; input.style.height = input.scrollHeight + 'px'; } }
    // the editor closed: with `take`, what was typed is the card's question - unless nothing was typed. A question the
    // coach changed is their own: it loses the title it came with
    function close(card, take) {
        const input = inputOf(card), q = card.querySelector('.q');
        const typed = take && input ? String(input.value == null ? '' : input.value).replace(/\s+/g, ' ').trim().slice(0, QUESTION_CHARS) : '';
        const text = typed === q.textContent ? '' : typed;
        const entry = responses[currentResponseIndex];
        const act = () => {
            if (text) { q.textContent = text; card.querySelectorAll('.tx b').forEach(e => e.remove()); }
            card.querySelectorAll('.nq-edit').forEach(e => e.remove());
            card.classList.remove('editing');
        };
        if (text && entry && !entry.status) change(entry, act); else act();
    }
    // a question run as it stands: a new analysis under the one on screen, at once. What is being typed in the card is
    // taken first; what is typed in the composer is left alone
    function run(card) {
        const set = card.closest('.nq-set'), entry = finished(), from = card.querySelector('.from');
        if (!set || !entry) return;
        if (running()) { say(WORDS.busyRun); return; }
        if (holds()) return;
        if (card.classList.contains('editing')) close(card, true);
        handleQuerySubmit({ next: { text: card.querySelector('.q').textContent.trim(), chain: entry.chain_id, set: Number(set.getAttribute('data-set')), k: Number(card.getAttribute('data-k')),
                                    level: set.getAttribute('data-level'), label: from ? from.textContent : '', lines: from ? from.getAttribute('title') || '' : '' } });
    }
    // the analysis of a question begins (handleQuerySubmit, after the panes are cleared): the live chain carries what it
    // was started from, and its pane opens on the row that says so
    function started(next) {
        if (typeof liveState !== 'undefined' && responses[liveState.index]) responses[liveState.index].next = next;
        if (typeof paneAppend === 'function') paneAppend(build.row(next));
    }
    // the server named the chain of the run under way (the stream's id line): where a question started it, the
    // question's card - in the pane of the analysis it follows, as kept - is marked with that chain
    function ran(chainId) {
        const live = typeof liveState !== 'undefined' ? responses[liveState.index] : null;
        const next = live && live.next;
        if (!next || next.marked || chainId == null) return;
        next.marked = true;
        const entry = responses.find(r => r && String(r.chain_id) === String(next.chain));
        if (!entry) return;
        change(entry, pane => {
            const card = pane.querySelector('.nq-set[data-set="' + next.set + '"] .nq-card[data-k="' + next.k + '"]');
            if (!card) return;
            card.querySelectorAll('.was').forEach(e => e.remove());
            card.classList.add('ran');
            card.insertAdjacentHTML('beforeend', build.was(chainId));
        });
    }
    // whether a chain's question was a next question, for its box on the thread map (§2.9): the live chain says so
    // itself, a kept one by the row its pane opens on
    function made(r) { return !!(r && (r.next || /class="nq-from"/.test(r.streamOutput || ''))); }

    function onClick(ev) {
        const hit = ev.target && ev.target.closest ? ev.target.closest('[data-nq]') : null;
        const act = hit ? hit.getAttribute('data-nq') : '', card = hit ? hit.closest('.nq-card') : null;
        if (act === 'open') { if (finished()) showMenu(hit); return; }
        hideMenu();
        if (act === 'level') { const entry = finished(); if (entry) ask(entry, hit.getAttribute('data-level')); return; }
        if (act === 'goto') { if (typeof navigateToChainId === 'function') navigateToChainId(hit.getAttribute('data-chain')); return; }
        if (!card) return;
        if (act === 'edit') edit(card);
        else if (act === 'keep') close(card, true);
        else if (act === 'cancel') close(card, false);
        else if (act === 'run') run(card);
    }
    function onKey(ev) {
        if (ev.key === 'Escape') hideMenu();
        const input = ev.target && ev.target.closest ? ev.target.closest('.nq-input') : null;
        if (!input || ev.isComposing) return;
        const card = input.closest('.nq-card');
        if (ev.key === 'Enter' && !ev.shiftKey) { ev.preventDefault(); close(card, true); }
        else if (ev.key === 'Escape') { ev.preventDefault(); close(card, false); }
    }

    function initialize() {
        document.addEventListener('click', onClick);
        document.addEventListener('keydown', onKey);
        document.addEventListener('input', ev => { const input = ev.target && ev.target.closest ? ev.target.closest('.nq-input') : null; if (input) grow(input); });
        if (typeof window !== 'undefined' && window.addEventListener) window.addEventListener('scroll', hideMenu, true);      // the list is placed by the button: it goes when the pane moves
    }

    window.NextQuestionsUI = { initialize, dress, restore, holds, started, ran, made, build };
})();
