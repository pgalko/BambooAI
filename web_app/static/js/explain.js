// explain.js - a passage of a finished analysis explained, where it stands (2026-11-27, the product owner's pick of
// the mockups: the note under the text) - and a plot, under its picture (2026-11-28).
//
// Ask on a selection (selection.js) puts the selection on the query box, and the question typed there is answered in
// a few plain sentences by one model call (POST /explain, a stream; analyst/explain.py). No analysis starts. The
// passage stays marked in its tab - the Answer, the Code or the Results tab - and what was asked about it stands in a
// note under it: under the paragraph, or under the line of code. A note shows its newest answer open and each earlier
// question as one line, which a click opens. One note is open at a time: a click on a marked passage opens its note,
// or shuts it.
//
// A follow-up is asked as the first question was: words selected in the note or in the marked passage, then Ask. Its
// answer joins that note. Everything asked about one analysis is one conversation on the server, whichever passages
// it is about, so a question builds on the answers before it.
//
// A plot is asked about whole. Its chat button puts it on the query box (selection.js), and the question is answered
// the same way - with the plot's picture as it is on screen, so that the model sees what the person sees. What was
// asked about a plot stands under its picture, in its card: each plot's own, always there, every question a fold, and
// the plot's button says how many there are. A follow-up is the button again, or words selected in what stands there.
//
// What was asked is kept with the analysis on the server's record and nowhere else: the page asks for it when it
// shows a chain (GET /explain/<thread>/<chain>). A passage is found again by its text and by which of its occurrences
// in the tab it is, white space counting as one space; so its mark comes back whenever its tab is drawn again - a
// chain shown again, the Answer's two versions switched, the code highlighted, the formulas set. A passage the tab no
// longer has keeps its note at the tab's foot. Marks and notes are drawn into a tab and never kept in a chain's
// markup: the page's copy of a chain is taken when its run ends, before anything can be asked about it.
//
// window.ExplainUI = { initialize, place, figure, picture, stands, ask, holds, restore, plain, build }

(function () {
    'use strict';

    const WORDS = { wait: 'An explanation is being written. Wait for it.', none: 'No explanation was written', unreachable: 'the server could not be reached',
                    later: 'A plot can be asked about once its analysis has finished.', blind: 'Answered without the picture.' };
    const TABS = ['answer', 'code', 'code_exec_results'];      // the tabs a passage can be asked about, as their contents are named (content-rendering.js)
    const PLOT = 'plot';                                       // the Plots tab: a plot is asked about whole
    const OURS = '.xp-note, .xp-lost';                         // what is drawn into a tab here: no part of the tab's own text
    const NOTE = '.markdown-content .xp-note';                 // the open note of a passage: in its tab's text
    const NO_MATH = 'pre, code, .answer-sources';              // where no formula is set (content-rendering.js renderLatex)

    let kept = {};         // chain id -> what was asked about that analysis, in order, as the server keeps it
    let asking = null;     // the exchange being written: where its passage stands, the question, the answer as far as it has come
    let open = '';         // the note that is open, by its place
    let watch = null;      // the observer of the tabs

    // ------------------------------------------------------------ helpers
    function esc(s) { return String(s == null ? '' : s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;'); }
    function byId(id) { return document.getElementById(id); }
    function say(text) { if (typeof showSystemMessage === 'function') showSystemMessage(text); }
    function running() { return typeof queryRunning !== 'undefined' && queryRunning; }
    // The finished analysis on screen: a chain whose run has ended, on a thread. A routine's run shown in the pane is
    // no chain: the chain behind it is not on screen
    function finished() {
        const entry = responses[currentResponseIndex];
        if (window.RoutinesUI && window.RoutinesUI.inRunView()) return null;
        return entry && !entry.status && entry.chain_id != null && entry.thread_id != null ? entry : null;
    }
    // which of the Answer tab's two versions is on screen; the other tabs have one
    function view(tab) { return tab === 'answer' ? currentData.summaryViewMode || 'technical' : ''; }
    // the text of a tab: what the report, the code or the output is drawn into
    function body(tab) { const root = byId('content-' + tab); return root ? root.querySelector('.markdown-content') : null; }
    function marksOf(k) { return Array.from(document.querySelectorAll('.xp-mark[data-k="' + k + '"]')); }
    // the plots of the tab on screen, in order; and a plot's name, as its card says it
    function plots() { return Array.from(document.querySelectorAll('#content-' + PLOT + ' .plot-container')); }
    function named(box) { const head = box.querySelector('.plot-header h3'); return head ? head.textContent.trim().replace(/:$/, '') : ''; }
    // where a plot stands, as a passage does: by its name, and which of the tab's plots of that name it is
    function spot(box) { const name = named(box); return { tab: PLOT, view: '', passage: name, at: plots().filter(b => named(b) === name).indexOf(box) }; }
    // the plot a place names, or none
    function plotAt(where) { return plots().filter(b => named(b) === where.passage)[where.at] || null; }

    // ------------------------------------------------------------ what was asked, as notes
    // where an exchange's passage stands, as one value: exchanges with the same place are one note
    function key(x) { return [x.tab, x.view, x.at, x.passage].join('\n'); }
    // The notes of the analysis on screen, in the order their passages were first asked about: each with its place and
    // what was asked there, the exchange being written last. A note's number is its place in this list
    function notes() {
        const entry = finished(), chain = entry ? entry.chain_id : null, out = [];
        (kept[chain] || []).concat(asking && String(asking.chain) === String(chain) ? [asking] : []).forEach(x => {
            let n = out.find(o => o.key === key(x));
            if (!n) out.push(n = { key: key(x), tab: x.tab, view: x.view, passage: x.passage, at: x.at, asked: [] });
            n.asked.push(x);
        });
        return out;
    }
    // what a note's markup was drawn from: how many exchanges, and whether one is still being written
    function sign(n) { return n.asked.length + (n.asked.some(x => x.live) ? ' live' : ''); }

    // ------------------------------------------------------------ builders (pure: return HTML)
    const build = {
        // one question and its answer, a fold: the question is its line. An answer still being written is shown as far
        // as it has come, as plain text; one about a plot that was written without the plot's picture says so
        asked(x, newest) {
            return '<details' + (newest ? ' open' : '') + (x.live ? ' class="live"' : '') + '><summary>' + esc(x.question) + '</summary><div class="a">' +
                (x.live ? esc(x.answer.trim()) : markdownToHtml(x.answer)) + '</div>' + (x.blind ? '<p class="blind">' + WORDS.blind + '</p>' : '') + '</details>';
        },
        // what a note holds: every question asked at its passage, the newest open
        note(n) { return n.asked.map((x, i) => build.asked(x, i === n.asked.length - 1)).join(''); },
        // the mark of a passage its tab no longer has, at the tab's foot: the words first selected there, on one line
        lost(n, k) { return '<mark class="xp-mark lost" data-k="' + k + '">' + esc(n.asked[0].quote.replace(/\s+/g, ' ')) + '</mark>'; },
    };

    // ------------------------------------------------------------ a tab's text, and a passage in it
    // A tab's text as a passage is found in it: its text nodes in order - none of what is drawn here - with every run
    // of white space as one space; and for each character the node it stands in, and where. A text that still holds
    // the source of a formula is not the tab's text yet: the renderer puts the formula in its place - and would not,
    // had a mark been set into the source
    function read(text) {
        const walker = document.createTreeWalker(text, NodeFilter.SHOW_TEXT), map = { text: '', nodes: [], offs: [] };
        for (let node = walker.nextNode(); node; node = walker.nextNode()) {
            if (node.parentElement.closest(OURS)) continue;
            if (/[$\\]/.test(node.data) && !node.parentElement.closest(NO_MATH) && protectLatexDelimiters(node.data).placeholders.length) continue;
            for (let i = 0; i < node.data.length; i++) {
                const c = /\s/.test(node.data[i]) ? ' ' : node.data[i];
                if (c === ' ' && map.text.endsWith(' ')) continue;
                map.text += c; map.nodes.push(node); map.offs.push(i);
            }
        }
        return map;
    }
    // how often a text has a passage before a place in it
    function count(text, passage, before) {
        let n = 0;
        for (let k = text.indexOf(passage); k >= 0 && k < before; k = text.indexOf(passage, k + 1)) n += 1;
        return n;
    }
    // the first and the last character of a note's passage in a tab's text - the occurrence it was asked about -, or
    // nothing where the text has it no more
    function find(map, n) {
        let k = -1;
        for (let i = 0; i <= n.at; i++) { k = map.text.indexOf(n.passage, k + 1); if (k < 0) return null; }
        return [k, k + n.passage.length - 1];
    }
    // the first and the last character of a tab's text that a selection holds, the blanks at its ends left out
    function held(map, range) {
        let a = -1, b = -1, node = null, inside = false;
        for (let k = 0; k < map.text.length; k++) {
            if (map.nodes[k] !== node) { node = map.nodes[k]; inside = range.intersectsNode(node); }
            if (inside && map.text[k] !== ' ' && range.comparePoint(node, map.offs[k]) === 0 && range.comparePoint(node, map.offs[k] + 1) === 0) { if (a < 0) a = k; b = k; }
        }
        return a < 0 ? null : [a, b];
    }

    // ------------------------------------------------------------ marks
    // A passage marked: in each text node it runs through, its part of the node wrapped. Blanks alone - the white space
    // between two blocks of text, a line end between two elements of the code - are left as they are
    function wrap(map, span, k) {
        const parts = [];
        for (let i = span[0]; i <= span[1]; i++) {
            const last = parts[parts.length - 1];
            if (last && last[0] === map.nodes[i]) last[2] = map.offs[i]; else parts.push([map.nodes[i], map.offs[i], map.offs[i]]);
        }
        parts.forEach(([node, from, to]) => {
            if (!node.data.slice(from, to + 1).trim()) return;
            node.splitText(to + 1);
            const part = node.splitText(from), mark = document.createElement('mark');
            mark.className = 'xp-mark';
            mark.dataset.k = k;
            part.before(mark);
            mark.append(part);
        });
    }
    // a mark taken off: its text stays where it stood; the mark of a passage that was lost goes whole, its line with it
    function unmark(mark) {
        const parent = mark.parentNode;
        if (!mark.classList.contains('lost')) mark.replaceWith(...mark.childNodes);
        else if (parent.querySelectorAll('.xp-mark').length > 1) mark.remove();
        else parent.remove();
        parent.normalize();
    }
    // a passage its tab no longer has: its mark at the tab's foot, as the words first selected there
    function lose(text, n, k) {
        if (!text.querySelector('.xp-lost')) text.insertAdjacentHTML('beforeend', '<p class="xp-lost"></p>');
        text.querySelector('.xp-lost').insertAdjacentHTML('beforeend', build.lost(n, k));
    }
    // whether a note's passage is marked where the tab's text has it - or, where the text has it no more, at its foot
    function marked(map, n, k) {
        const marks = marksOf(k), span = find(map, n);
        if (!marks.length) return false;
        return span ? marks[0].contains(map.nodes[span[0]]) && marks[marks.length - 1].contains(map.nodes[span[1]]) : marks[0].classList.contains('lost');
    }

    // ------------------------------------------------------------ the note
    // The note under the text its passage ends in. In a block of code: after the line - the text is cut behind the
    // line's end, and the note stands there. In a list: at the end of the item, so that the list stays one. Elsewhere:
    // after the part of the tab's text that holds the passage - its paragraph, its heading, its table
    function put(note, last) {
        const pre = last.closest('pre'), item = last.closest('li');
        if (!pre && item) { item.append(note); return; }
        if (!pre) {
            let block = last;
            while (!block.parentNode.matches('.markdown-content')) block = block.parentNode;
            block.after(note);
            return;
        }
        const walker = document.createTreeWalker(pre, NodeFilter.SHOW_TEXT);
        let past = false;
        for (let node = walker.nextNode(); node; node = walker.nextNode()) {
            const end = past ? node.data.indexOf('\n') : -1;
            if (last.contains(node)) past = true;
            else if (end >= 0) { node.splitText(end + 1).before(note); return; }
        }
        (pre.querySelector('code') || pre).append(note);
    }
    // a note taken out of its tab: the text it was cut into is whole again
    function shut(note) {
        const parent = note.parentNode;
        note.remove();
        parent.normalize();
    }
    // a note's questions and answers drawn, the formulas of the answers set
    function fill(note, n) {
        note.dataset.n = sign(n);
        note.innerHTML = build.note(n);
        try { renderLatex(note); } catch (e) { /* the formulas stay as they were written */ }
    }

    // ------------------------------------------------------------ the plots
    // What was asked about the plots of the tab on screen: each plot's under its picture, in its card, drawn from what
    // was asked there, and on the plot's button how many questions that is. A plot nothing was asked about has neither
    function captions(all) {
        plots().forEach(box => {
            const k = all.findIndex(n => n.key === key(spot(box))), button = box.querySelector('.plot-query-btn');
            let note = box.querySelector(':scope > .xp-note');
            if (k < 0 && note) note.remove();
            if (k >= 0 && !note) { note = document.createElement('div'); note.className = 'xp-note'; box.append(note); }
            if (k >= 0) { note.dataset.k = k; if (note.dataset.n !== sign(all[k])) fill(note, all[k]); }
            button.classList.toggle('asked', k >= 0);
            if (k >= 0) button.setAttribute('data-n', all[k].asked.length); else button.removeAttribute('data-n');
        });
    }

    // ------------------------------------------------------------ the page
    // The marks, the open note and the plots' notes of the analysis on screen, put where they belong - after anything
    // that draws a tab again, and after every change to what was asked. In each tab: a mark that is no note's any more
    // goes; a passage that is not marked where the text has it now is marked afresh, each on the text as the mark
    // before left it. Then the open note: under its passage, drawn from what was asked there. Then the plots
    function dress() {
        const all = notes(), moved = [];
        TABS.forEach(tab => {
            const text = body(tab), here = n => !!n && n.tab === tab && n.view === view(tab);
            if (!text) return;
            text.querySelectorAll('.xp-mark').forEach(mark => { if (!here(all[mark.dataset.k])) unmark(mark); });
            const mine = all.map((n, k) => k).filter(k => here(all[k]));
            if (!mine.length) return;      // nothing was asked here: the tab's text is not read - a running analysis draws its tabs many times a second
            const before = read(text), astray = mine.filter(k => !marked(before, all[k], k));
            astray.forEach(k => marksOf(k).forEach(unmark));
            astray.forEach(k => { const map = read(text), span = find(map, all[k]); if (span) wrap(map, span, k); else lose(text, all[k], k); });
            moved.push(...astray);
        });
        const k = all.findIndex(n => n.key === open), marks = k < 0 ? [] : marksOf(k);
        let note = document.querySelector(NOTE);
        if (note && (!marks.length || note.dataset.k !== String(k) || moved.includes(k))) { shut(note); note = null; }
        if (!marks.length) open = '';
        else if (!note) {
            note = document.createElement('div');
            note.className = 'xp-note';
            note.dataset.k = k;
            put(note, marks[marks.length - 1]);
            fill(note, all[k]);
        } else if (note.dataset.n !== sign(all[k])) fill(note, all[k]);
        captions(all);
        drawn();
    }
    // what was drawn here is no change of the tabs' own: the observer is not told of it
    function drawn() { if (watch) watch.takeRecords(); }
    // the answer being written, as far as it has come, in its note
    function tick() {
        const live = document.querySelector('.xp-note .live .a');
        if (live) { live.textContent = asking.answer.trim(); drawn(); }
    }
    // the note of a place brought into view, where it is drawn
    function show(at) {
        const note = document.querySelector('.xp-note[data-k="' + notes().findIndex(n => n.key === at) + '"]');
        if (note && note.scrollIntoView) note.scrollIntoView({ block: 'nearest' });
    }

    // a click on a marked passage: its note opens, or shuts - not where the press ended as a selection, which is the bar's
    function toggle(mark) {
        const n = notes()[mark.dataset.k];
        if (!n || String(window.getSelection()).trim()) return;
        open = open === n.key ? '' : n.key;
        dress();
        show(n.key);
    }

    // The words a selection holds, as the person sees them. An open note the selection is not in is hidden while they
    // are read: a selection that runs across it holds none of its words
    function quote(inside) {
        const note = inside ? null : document.querySelector(NOTE);
        if (note) note.hidden = true;
        const said = String(window.getSelection()).trim();
        if (note) note.hidden = false;
        return said;
    }
    // Where a selection can be asked about, and the words it holds: {chain, thread, tab, view, passage, at, quote}. A
    // selection in the text of the Answer, Code or Results tab: the passage, and which of its occurrences. A selection in
    // a note - a passage's or a plot's -, or one that touches a marked passage: that note's own place - the question is
    // a follow-up. Nothing where no finished analysis is on screen, an analysis is running, or the selection lies elsewhere
    function place(range) {
        const entry = finished(), node = range.commonAncestorContainer, el = node.nodeType === 1 ? node : node.parentElement;
        const root = el.closest('.tab-content'), tab = root ? root.id.slice('content-'.length) : '', text = TABS.includes(tab) ? root.querySelector('.markdown-content') : null;
        const note = el.closest('.xp-note');
        if (!entry || running() || !(text || note)) return null;
        const mark = note || Array.from(text.querySelectorAll('.xp-mark')).find(m => range.intersectsNode(m));
        const where = { chain: entry.chain_id, thread: entry.thread_id, quote: quote(note) };
        if (mark) {
            const n = notes()[mark.dataset.k];
            return n ? Object.assign(where, { tab: n.tab, view: n.view, passage: n.passage, at: n.at }) : null;
        }
        const map = read(text), span = held(map, range);
        if (!span) return null;
        const passage = map.text.slice(span[0], span[1] + 1);
        return Object.assign(where, { tab, view: view(tab), passage, at: count(map.text, passage, span[0]) });
    }
    // A plot as a place to ask about, its name the words quoted - or nothing, and the reason said, where no finished
    // analysis is on screen or one is running
    function figure(box) {
        const entry = finished();
        if (!entry || running()) { say(WORDS.later); return null; }
        const where = spot(box);
        return Object.assign({ chain: entry.chain_id, thread: entry.thread_id, quote: where.passage }, where);
    }
    // The picture of the plot a place names, as the model is given it: the PNG the plot is, or the interactive plot as it
    // is on screen now. Its base64, promised - nothing where the place is no plot's, or no picture can be taken
    function picture(where) {
        const box = where.tab === PLOT ? plotAt(where) : null, still = box && box.querySelector('.plot-image'), live = box && box.querySelector('.js-plotly-plot');
        const bare = src => String(src || '').split(',')[1] || null;
        if (still) return Promise.resolve(bare(still.getAttribute('src')));
        return live ? Promise.resolve().then(() => window.Plotly.toImage(live, { format: 'png' })).then(bare, () => null) : Promise.resolve(null);
    }
    // whether the analysis a place was taken in is still the finished one on screen
    function stands(where) {
        const entry = finished();
        return !!entry && !running() && String(entry.chain_id) === String(where.chain);
    }

    // A question about a place (place(), figure()), answered: the passage is marked and its note opens at once, on the
    // question - a plot's stands under its picture -; the answer is shown as it is written, and what the server then
    // keeps is what the page draws from. A plot's picture is taken as the question is sent, and goes with it. Where no
    // answer was made, the reason is said and the question goes - with its mark, where it was the first at its passage
    function ask(where, question) {
        if (asking) return;
        const mine = asking = Object.assign({}, where, { question, answer: '', live: true });
        let out = {};
        if (mine.tab !== PLOT) open = key(mine);
        dress();
        show(key(mine));
        const send = image => window.authService.fetch('/explain', { method: 'POST', headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ thread_id: mine.thread, chain_id: mine.chain, tab: mine.tab, view: mine.view, passage: mine.passage, at: mine.at, quote: mine.quote, question, image }) });
        (mine.tab === PLOT ? picture(mine).then(send) : send())
            .then(r => window.ArchitectUI.readStream(r, d => {
                if (d.explain) out = d.explain;
                else if (d.message || d.error || d.routine_error) out = { error: d.message || d.error || d.routine_error };      // a refusal: the balance, the month's queries
                else if (typeof d.text === 'string') { mine.answer += d.text; tick(); }
            }))
            .catch(() => { out = { error: WORDS.none + ': ' + WORDS.unreachable + '.' }; })
            .then(() => {
                asking = null;
                if (Array.isArray(out.asked)) kept[mine.chain] = out.asked; else say(out.error || WORDS.none + '.');
                dress();
                show(key(mine));
            });
    }
    // an analysis may not start while an explanation is being written: the two would share the instance's stream
    function holds() {
        if (!asking) return false;
        say(WORDS.wait);
        return true;
    }

    // a chain shown again (loadResponseContent): no note open; what was asked about it, as the page last had it and
    // then as the server keeps it
    function restore(entry) {
        open = '';
        dress();
        if (!entry || entry.status || entry.chain_id == null || entry.thread_id == null) return;
        window.authService.fetch('/explain/' + encodeURIComponent(entry.thread_id) + '/' + encodeURIComponent(entry.chain_id))
            .then(r => r.json()).then(d => { if (d && Array.isArray(d.asked)) { kept[entry.chain_id] = d.asked; dress(); } })
            .catch(() => { /* the notes stay as the page has them */ });
    }

    // a copy of a tab's content without what is drawn into it here: the export's
    function plain(root) {
        root.querySelectorAll(OURS).forEach(e => e.remove());
        root.querySelectorAll('.xp-mark').forEach(unmark);
        return root;
    }

    function initialize() {
        // a press may end as a selection: what is selected is known only once the browser has settled it (selection.js)
        document.addEventListener('click', e => { const mark = e.target.closest ? e.target.closest('.xp-mark') : null; if (mark) setTimeout(() => toggle(mark), 0); });
        // a tab drawn again - or drawn on: the code highlighted, the formulas set - has lost its marks: they are put
        // back when the browser says what changed. A change in a tab that holds no passages is none of this module's:
        // an interactive plot draws inside itself over and over, and the plots of a finished analysis stay as drawn
        watch = new MutationObserver(records => {
            const ours = r => { const tab = r.target.closest('.tab-content'); return !tab || TABS.includes(tab.id.slice('content-'.length)); };
            if (records.some(ours)) dress();
        });
        watch.observe(byId('contentOutput'), { childList: true, subtree: true });
    }

    window.ExplainUI = { initialize, place, figure, picture, stands, ask, holds, restore, plain, build };
})();
