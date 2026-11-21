// next-questions.js - the questions that could follow a finished analysis (docs/ARCHITECT_DESIGN.md §2.7, §2.15,
// §2.24; 2026-11-16, the panel 2026-11-19). The closing card of a finished analysis carries a Next questions button.
// It opens a panel inside the card: a line that says what the questions are, and five ways to go, each with a
// sentence. The one picked is asked of the server (POST /architect/next, a stream: one call of the Architect's), and
// the questions that come back take the list's place in the panel, in rows of the same look, each saying what it
// starts from. A row's pencil changes its question; its arrow starts a new analysis with it at once (/query with
// `next`): no brief, and the Architect's switch does not apply. Back at the list, a way that has questions says how
// many and opens them again; more of them are written on request.
//
// The panel is part of the analysis' own pane, kept with the chain as the rest of the pane is - in the page's copy
// and in a saved favourite - so a chain shown again has its questions with nothing else kept; sets kept under the
// card by the page before the panel are taken into it. A question that was run is marked on its row, and the pane
// of the run it started opens on a row saying so: that row is how the run's box on the Workflow map is marked. The
// page's words sit in WORDS; nothing here reaches a prompt.
//
// window.NextQuestionsUI = { initialize, dress, restore, holds, started, ran, made, build }

(function () {
    'use strict';

    const WORDS = {
        button: 'Next questions', buttonTitle: 'Questions that could follow this analysis',
        one: 'Next question', run: 'run', runTitle: 'Open its analysis',
        change: 'Change', go: 'Start the analysis', keep: 'Keep', cancel: 'Cancel', prompt: 'the prompt the Architect received (run log)',
        wait: 'The questions are being written. Wait for them.', busyRun: 'Another analysis is running. Wait for it to end, or stop it.',
        none: 'No questions were written', unreachable: 'the server could not be reached',
        // the panel: its heading, what the questions are, and what is said while a set is written
        where: 'Where do you want to go from here?',
        what: 'Up to five questions that could follow this analysis. Each one starts from something it found, took for granted or left open. You can change a question before you run it.',
        writing: 'writing the questions…', all: 'All five', close: 'Close', more: 'Write more', moreTitle: 'More questions of this kind',
        count: n => n + (n === 1 ? ' question' : ' questions'),
        // a way to go: its key (analyst/next_questions.py), its name, and what its questions do, in a sentence
        levels: [['refine', 'Refine focus', 'Stay with the same question and look closer: a smaller group, a shorter period, a stricter measure.'],
                 ['shift', 'Shift angle', 'Ask whether something else explains the result, and put that to the test.'],
                 ['test', 'Test boundaries', 'Check what the result stands on, and find where it stops being true.'],
                 ['blend', 'Blend elements', 'Bring two findings together in one question, such as this result and an earlier one.'],
                 ['emergence', 'Follow emergence', 'Go after what did not fit: the things this analysis could not explain.']],
        // what a question starts from, after "From"
        from: { comparison: 'what was compared', measure: 'the measure', period: 'the period', check: 'what was also checked', proposal: 'a proposal not ticked', anchor: 'what it rests on',
                would_change: 'what would change your mind', misfit: 'what did not fit', asked: 'the question', found: 'the answer', earlier: 'an earlier answer' }
    };
    // the words the page had for three of them before the panel: a set kept from then is brought to today's
    const FROM_BEFORE = [[/\bit rests on\b/g, 'what it rests on'], [/\bdid not fit\b/g, 'what did not fit'], [/\balso checked\b/g, 'what was also checked']];
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
    function levelOf(key) { return WORDS.levels.find(x => x[0] === key) || [key, String(key || ''), '']; }
    function running() { return typeof queryRunning !== 'undefined' && queryRunning; }

    // ------------------------------------------------------------ builders (pure: return HTML)
    const build = {
        // the button on a closing card, in its row of what can be done next
        button() {
            return '<button type="button" class="sp-act sp-next" data-nq="open" title="' + WORDS.buttonTitle + '">' + ICON.plant + WORDS.button + '</button>';
        },
        // the panel of a closing card, empty: what stands over its sets, the sets, what stands under them
        panel() {
            return '<div class="nq-panel" data-show="list"><div class="nq-top"></div><div class="nq-sets"></div><div class="nq-end"></div></div>';
        },
        // the five ways to go, a row each: its name and its sentence; how many questions it has, where it has some;
        // while a set is written its row says so and the others stand back
        levels(counts, writing) {
            return WORDS.levels.map(l => '<button type="button" class="nq-row' + (writing === l[0] ? ' on' : writing ? ' dim' : '') + '" data-nq="level" data-level="' + l[0] + '"><b>' + l[1] + '</b>' +
                '<span>' + l[2] + '</span>' + (writing === l[0] ? '<em class="live">' + WORDS.writing + '</em>'
                    : ((counts || {})[l[0]] ? '<em class="n">' + WORDS.count(counts[l[0]]) + '</em>' : '') + '<i>›</i>') + '</button>').join('');
        },
        // what stands over the sets: the list - the heading, what the questions are, the five rows - or, where the
        // questions of one way are shown, the way back to the list and that way's name and sentence
        top(show, counts, writing) {
            const shut = '<button type="button" class="nq-x" data-nq="shut" title="' + WORDS.close + '">×</button>';
            if (show === 'list') return '<div class="nq-ph"><span class="t">' + WORDS.where + '</span>' + shut + '</div><div class="nq-what">' + WORDS.what + '</div>' + build.levels(counts, writing);
            const level = levelOf(show);
            return '<div class="nq-ph"><button type="button" class="nq-back" data-nq="list">‹ ' + WORDS.all + '</button>' + shut + '</div>' +
                '<div class="nq-lv"><b>' + esc(level[1]) + '</b><span>' + level[2] + '</span></div>';
        },
        // what stands under the questions of one way: more of them, on request - or that they are being written
        end(show, writing) {
            if (show === 'list') return '';
            return '<button type="button" class="nq-more" data-nq="more" data-level="' + esc(show) + '" title="' + WORDS.moreTitle + '"' + (writing ? ' disabled' : '') + '>' + (writing ? WORDS.writing : WORDS.more) + '</button>';
        },
        // what a question starts from: the kinds of its lines in words, the lines themselves as the label's title
        from(lines) {
            lines = Array.isArray(lines) ? lines : [];
            const kinds = lines.map(l => WORDS.from[l.kind]).filter(Boolean);
            return '<div class="from" title="' + esc(lines.map(l => l.text).join('\n')) + '"><span class="l">' + (kinds.length ? 'From ' + esc(kinds.join(' and ')) : '') + '</span></div>';
        },
        // one question, a row: its title, its text with what it starts from under it, the pencil and the arrow; q: {title, text, from, ran}
        card(q, k) {
            return '<div class="nq-card' + (q.ran ? ' ran' : '') + '" data-k="' + k + '">' + build.from(q.from) +
                '<div class="tx">' + (q.title ? '<b>' + esc(String(q.title).replace(/[.:\s]+$/, '')) + '</b> ' : '') + '<span class="q">' + esc(q.text) + '</span></div>' +
                '<div class="tools"><button type="button" class="pen" data-nq="edit" title="' + WORDS.change + '">' + ICON.pen + '</button>' +
                '<button type="button" class="go" data-nq="run" title="' + WORDS.go + '">' + ICON.go + '</button></div>' +
                (q.ran ? build.was(q.ran) : '') + '</div>';
        },
        // the mark on a question that was run: it opens the analysis it started
        was(chain) {
            return '<button type="button" class="was" data-nq="goto" data-chain="' + esc(chain) + '" title="' + WORDS.runTitle + '">' + WORDS.run + '</button>';
        },
        // the line under a set: how many questions, what the call cost, and the button to the prompt the Architect received
        foot(n, cost, prompt) {
            return '<div class="nq-foot"><span>' + WORDS.count(n) + (cost ? ' · ' + cost : '') + '</span>' + (prompt || '') + '</div>';
        },
        // a set as the server keeps it ({level, questions, cost, chain}), at its place among the analysis' sets
        set(asked, at) {
            const cost = Number(asked.cost) || 0, questions = asked.questions || [];
            const prompt = asked.chain ? '<button class="agent-instructions-btn sp-prompt" type="button" title="' + WORDS.prompt + '" data-agent="Architect" data-chain="' + esc(asked.chain) + '" data-call="1">⌘</button>' : '';
            return '<div class="nq-set" data-set="' + esc(at) + '" data-level="' + esc(asked.level) + '">' + questions.map((q, k) => build.card(q, k)).join('') +
                build.foot(questions.length, cost >= 0.005 ? '$' + cost.toFixed(2) : '', prompt) + '</div>';
        },
        // the first row of the run a question started: that a question started it, and which way it went
        row(next) {
            return '<div class="nq-from"><span class="k">' + WORDS.one + '</span><span class="sep">·</span><span class="lv">' + esc(levelOf(next.level)[1]) + '</span></div>';
        },
        editor(text) {
            return '<div class="nq-edit"><textarea class="nq-input" rows="2" maxlength="' + QUESTION_CHARS + '">' + esc(text) + '</textarea>' +
                '<button type="button" class="ok" data-nq="keep" title="' + WORDS.keep + '">' + ICON.ok + '</button><button type="button" class="no" data-nq="cancel" title="' + WORDS.cancel + '">' + ICON.x + '</button></div>';
        }
    };

    // ------------------------------------------------------------ the page
    let asking = null;         // the set being written: {entry, level}

    function holder(html) { const d = document.createElement('div'); d.innerHTML = html || ''; return d; }
    // The panel as it stands: what is over its sets and under them is drawn from the sets themselves - how many
    // questions each way has - and from what it shows: the list, or the questions of one way. `writing`: the way a
    // set is being written for, where one is
    function draw(panel, writing) {
        const sets = Array.from(panel.querySelectorAll('.nq-set')), counts = {}, show = panel.getAttribute('data-show');
        sets.forEach(set => { const level = set.getAttribute('data-level'); counts[level] = (counts[level] || 0) + set.querySelectorAll('.nq-card').length; });
        panel.querySelector('.nq-top').innerHTML = build.top(show, counts, writing || '');
        panel.querySelector('.nq-end').innerHTML = build.end(show, writing || '');
        sets.forEach(set => set.classList.toggle('on', set.getAttribute('data-level') === show));
    }
    // the panel of a pane's closing card - the card of a finished analysis, the one with a row of what can be done
    // next - made, shut, where the card has none
    function panelOf(pane) {
        const panel = pane.querySelector('.nq-panel'), rows = panel ? [] : Array.from(pane.querySelectorAll('.sp-done .acts'));
        if (!rows.length) return panel;
        const card = rows[rows.length - 1].closest('.sp-done'), made = holder(build.panel()).firstElementChild;
        made.classList.add('shut');
        card.insertBefore(made, card.querySelector('.sp-telemetry'));      // under the row of buttons, over the call telemetry
        return made;
    }
    // what is of the moment leaves a pane: a question open for a change, the word that a set is being written
    function tidy(pane) {
        pane.querySelectorAll('.nq-edit').forEach(e => e.remove());
        pane.querySelectorAll('.nq-card.editing').forEach(c => c.classList.remove('editing'));
        pane.querySelectorAll('.nq-panel').forEach(panel => draw(panel));
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
    // Sets the page kept under the closing card, before the panel, are taken into it - shown, as they were: a set's
    // head goes, its cost and its prompt's button stand under its questions, a title loses its full stop, and what a
    // question starts from is said in today's words
    function gather(pane) {
        const loose = Array.from(pane.querySelectorAll('.nq-set')).filter(set => !set.closest('.nq-panel'));
        const panel = loose.length ? panelOf(pane) : null;
        if (!panel) return;
        loose.forEach(set => {
            const head = set.querySelector('.nq-head'), right = head ? head.querySelector('.r') : null, prompt = right ? right.querySelector('.sp-prompt') : null;
            const cost = right ? (right.textContent.match(/\$[\d.]+/) || [''])[0] : '';
            if (head) head.remove();
            set.querySelectorAll('.tx b').forEach(b => { b.textContent = b.textContent.replace(/\.$/, ''); });
            set.querySelectorAll('.from .l').forEach(l => { l.textContent = FROM_BEFORE.reduce((text, pair) => text.replace(pair[0], pair[1]), l.textContent); });
            if (!set.querySelector('.nq-foot')) set.insertAdjacentHTML('beforeend', build.foot(set.querySelectorAll('.nq-card').length, cost, prompt ? prompt.outerHTML : ''));
            panel.querySelector('.nq-sets').appendChild(set);
        });
        panel.setAttribute('data-show', loose[loose.length - 1].getAttribute('data-level'));
        panel.classList.remove('shut');
        draw(panel);
    }
    // a chain shown again (loadResponseContent): its button where it is missing, its questions in the panel, and the
    // word that a set is being written, if one is. An Explore chain of the retired ideas path is five questions, not
    // an analysis: nothing follows from it
    function restore(entry) {
        const pane = byId('streamOutput');
        if (!pane || !entry || entry.status) return;
        tidy(pane);                                             // a pane kept by another hand (Save as routine) may hold the moment it was kept in
        if (!/user requested variations/i.test(entry.queryText || '')) dress(pane);
        gather(pane);
        pane.querySelectorAll('.nq-from').forEach(row => {      // the row of a run kept before the panel also said what its question came from
            row.removeAttribute('title');
            Array.from(row.children).filter(part => part.nodeType === 1).slice(3).forEach(part => part.remove());
        });
        if (asking && asking.entry === entry && panelOf(pane)) draw(panelOf(pane), asking.level);
    }

    // ---- the panel: opened and shut by the card's button, the list and the questions of one way
    function inView(panel) { if (panel && panel.scrollIntoView) panel.scrollIntoView({ block: 'nearest' }); }
    // what the coach does to the panel of the chain on screen, kept with the chain
    function turn(entry, act) {
        change(entry, pane => { const panel = panelOf(pane); if (panel) { act(panel); draw(panel, asking && asking.entry === entry ? asking.level : ''); } });
        inView(panelOf(byId('streamOutput')));
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
    // A set of questions for the finished analysis `entry`, one way: one set at a time, and not while an analysis
    // runs. While it is written the panel says so - on that way's row, or under its questions where more are asked
    // for. The set that comes back is shown. Resolves to whether a set was made; where none was, the reason is said.
    function ask(entry, level) {
        if (asking) { say(WORDS.wait); return Promise.resolve(false); }
        if (running()) { say(WORDS.busyRun); return Promise.resolve(false); }
        asking = { entry, level };
        const live = () => (responses[currentResponseIndex] === entry ? panelOf(byId('streamOutput')) : null);
        if (live()) { draw(live(), level); inView(live()); }
        return window.authService.fetch('/architect/next', { method: 'POST', headers: { 'Content-Type': 'application/json' },
                                                              body: JSON.stringify({ thread_id: entry.thread_id, chain_id: entry.chain_id, level }) })
            .then(r => r.text()).then(closing).catch(() => ({ error: WORDS.none + ': ' + WORDS.unreachable + '.' })).then(out => {
                asking = null;
                if (!out.set) { say(out.error || WORDS.none + '.'); if (live()) draw(live()); return false; }
                change(entry, pane => {
                    const panel = panelOf(pane);
                    if (!panel) return;
                    panel.querySelector('.nq-sets').insertAdjacentHTML('beforeend', build.set(out.set, out.at));
                    panel.setAttribute('data-show', out.set.level);
                    panel.classList.remove('shut');                 // asked for from another chain's screen, or shut meanwhile: the new questions are shown
                    draw(panel);
                });
                const made = live() ? live().querySelector('.nq-set[data-set="' + out.at + '"]') : null;
                if (made && made.scrollIntoView) made.scrollIntoView({ block: 'nearest' });      // the new questions in view
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
        const set = card.closest('.nq-set'), entry = finished();
        if (!set || !entry) return;
        if (running()) { say(WORDS.busyRun); return; }
        if (holds()) return;
        if (card.classList.contains('editing')) close(card, true);
        handleQuerySubmit({ next: { text: card.querySelector('.q').textContent.trim(), chain: entry.chain_id, set: Number(set.getAttribute('data-set')), k: Number(card.getAttribute('data-k')),
                                    level: set.getAttribute('data-level') } });
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
    // whether a chain's question was a next question, for its box on the Workflow map (§2.9): the live chain says so
    // itself, a kept one by the row its pane opens on
    function made(r) { return !!(r && (r.next || /class="nq-from"/.test(r.streamOutput || ''))); }

    function onClick(ev) {
        const hit = ev.target && ev.target.closest ? ev.target.closest('[data-nq]') : null;
        const act = hit ? hit.getAttribute('data-nq') : '', card = hit ? hit.closest('.nq-card') : null;
        if (act === 'goto') { if (typeof navigateToChainId === 'function') navigateToChainId(hit.getAttribute('data-chain')); return; }
        if (card) {
            if (act === 'edit') edit(card);
            else if (act === 'keep') close(card, true);
            else if (act === 'cancel') close(card, false);
            else if (act === 'run') run(card);
            return;
        }
        if (['open', 'shut', 'list', 'level', 'more'].indexOf(act) < 0) return;
        const entry = finished(), level = hit.getAttribute('data-level');
        if (!entry) return;
        if (act === 'open') turn(entry, panel => panel.classList.toggle('shut'));
        else if (act === 'shut') turn(entry, panel => panel.classList.add('shut'));
        else if (act === 'list') turn(entry, panel => panel.setAttribute('data-show', 'list'));
        else if (act === 'level' && hit.querySelector('.n')) turn(entry, panel => panel.setAttribute('data-show', level));      // a way that has questions shows them
        else ask(entry, level);                                                                                                 // a way with none yet, or more of one
    }
    function onKey(ev) {
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
    }

    window.NextQuestionsUI = { initialize, dress, restore, holds, started, ran, made, build };
})();
