// architect.js - the Architect on the page (docs/ARCHITECT_DESIGN.md §2.6, §2.8, §2.9, §2.11-§2.14, §2.18; 2026-11-17).
// A question typed with the switch on is framed before it is analysed: the server opens a framing run on the thread's
// record (POST /architect/open) and the page shows it as a chain of its own, the conversation in the left pane and
// its brief on a Brief tab. The Architect fills the brief from the question and asks for what is missing, one
// exchange a call (POST /architect/say, a stream); while such a chain is on screen the composer is the conversation's
// input. Where a reply had the data looked up, the round is a row of the conversation and the Architect goes on at
// once, with the marks. The coach also changes the brief where it stands, and ticks what the Architect proposed;
// every change kept is one more version, stored by the server (POST /architect/brief). Start analysis continues the
// same chain (/query with run_id), so the question is one box on the Workflow map.
//
// One rule holds the Brief tab together: what it shows is what the Analyst gets. The question is its top box, and
// the Architect words it as the conversation goes: each wording is one more version, and a row of the conversation
// says so. Under it stand the parts that hold something, and no other; + Add lists the ones a coach can add by hand.
//
// What the coach says or changes, with the Architect's reply, is a step of the conversation (§2.25; analyst/steps.py).
// The arrows step through the steps of the way being walked, and the one on screen is the one in use: the pane shows
// the conversation up to it, the tab the brief as it stood there, and an answer, a change and Start analysis all go
// on from it (the step rides with the request). Going on from a step that has steps after it starts another way:
// the steps left are set aside, out of the pane and of what the Architect reads. The map beside the arrows shows
// every step - in the Workflow map's own drawer and drawing (workflowGraph.js) - and a click goes to one. A brief kept
// before steps is one way, a step to a version, and has no map.
//
// Where a reply has the coach's saved analyses read (§3.7), the stream says how far the reading is: a row of the
// conversation with a count and Skip (POST /architect/skip). What was found is listed under the row, an analysis to
// a line, and in full under the brief, to read; each can be viewed whole (GET /architect/saved/<thread>/<run>). The
// coach chooses by answering the Architect, and the brief then says which analyses it builds on. Where a reply opened
// a part of an earlier analysis, that is a row of the conversation too, and the Architect goes on at once (§2.17).
//
// Where the brief holds figures, a draft of each is drawn after the Architect's reply (§2.20): the stream first
// carries the framing with the reply, the pane shows a row while the cell runs, and the Brief tab then draws each
// plot with Plotly (GET /architect/draft/<thread>/<chain>/<key>) - marked where its numbers are made up. A figure
// without a draft is a grey window with one line: a draft is on its way, none could be drawn, or none was yet.
//
// Start analysis first has the question read as the Analyst will read it (POST /architect/ready, a stream; §2.22):
// a row says so while it is read, and what came of it. Where the reader could not place something, the Architect
// has gone on - the question worded again - and the coach starts again when they have seen it.
//
// A brief not yet run is drawn from its versions (the chain's `framing`), never from kept markup. Once it runs, the
// Brief tab's markup carries the framing (data-framing), so a restored chain or a saved favourite steps through its
// steps - and opens their map, to be read - with nothing else kept.
//
// The report of a run with a brief has a part "Against the brief" (analyst/session.py). It is not the Answer's - the
// Answer is what goes to other people: cutAnswer() takes it out, and turnedOut() shows it at the foot of that run's
// Brief tab, as a card of verdicts (§2.21). The page's words sit in WORDS; nothing here reaches a prompt.
//
// window.ArchitectUI = { initialize, isOn, open, tell, restore, onChain, framingInView, started, notStarted,
//                        cutAnswer, turnedOut, mark, apply, tick, unbuild, unfigure, go, steps, build, readStream, draftLayout }

(function () {
    'use strict';

    const WORDS = {
        answer: 'Answer, or say what to change', replying: 'The Architect is replying', reading: 'reading…', readingSaved: 'Your saved analyses are being read',
        asked: 'What the Analyst will be asked', gets: 'This is what the Analyst gets. Change any line before you start.',
        head: { decision: 'What it is for', thinks: 'What you think', rests_on: 'Why you think so', expects: 'What you expect to see', would_change: 'What would change your mind',
                also_check: 'Other explanations to test', figures: 'What it will look like', builds: 'Builds on', aside: 'Set aside' },
        add: '+ Add', another: 'Another explanation to test', tick: 'Have the analysis test it',
        always: 'Always tested on data: chance, measurement error, how the cases were chosen.',
        step: 'Step', of: (k, n) => k + ' of ' + n, before: 'The step before', after: 'The step after',
        start: 'Start analysis', startFrom: k => 'Start analysis from step ' + k,
        notKept: 'The change was not kept', notOpened: 'The brief could not be opened', unreachable: 'the server could not be reached',
        noReply: 'The Architect did not reply', check: 'CHECK data', lookedUp: n => n + (n === 1 ? ' thing' : ' things') + ' looked up', notLookedUp: n => n + ' not',
        busyRun: 'Another analysis is running. Wait for it to end, or stop it.',
        saved: 'MEMORY', found: n => n + (n === 1 ? ' analysis' : ' analyses') + ' found', noneFound: 'nothing found', readOf: (r, m) => r ? 'read ' + r + ' of ' + m : m + ' saved',
        searching: 'SEARCHING MEMORY', readSoFar: (r, m) => (m == null ? '' : (r || 0) + ' of ' + m + ' read'), skip: 'Skip', skipped: 'skipped', notRead: 'not read',
        view: 'View', leave: 'Leave it out', builtOn: 'built on',
        memory: 'Found in your saved analyses', memoryNote: 'For you to read. The Analyst gets only what you build on.',
        notOpenedSaved: 'This analysis could not be opened', code: 'Code', agreed: 'Brief', talk: 'Conversation', fromTurn: n => 'From turn ' + n,
        opened: 'READ', chars: n => (Number(n) || 0).toLocaleString('en-US') + ' characters',
        question: 'QUESTION', updated: 'updated', stepN: k => 'step ' + k, brief: 'BRIEF', inUse: k => 'step ' + k + ' in use',
        figures: 'FIGURES', draft: 'draft', madeUp: 'made-up numbers', madeUpNote: 'The numbers are made up. The analysis puts in the real ones.',
        drawing: 'Drawing a draft…', noDraft: 'No draft could be drawn.', noDraftYet: 'No draft yet.', notDrafted: 'No draft was drawn.', notShown: 'The draft could not be shown.',
        drawingRow: 'DRAWING A DRAFT', drawingHold: 'A draft of the figures is being drawn',
        checkingRow: 'CHECKING THE QUESTION', checkingHold: 'The question is being read as the Analyst will read it', checkQ: 'CHECK question', standsAlone: 'stands on its own',
        unplaced: 'the Analyst cannot place', checkPrompt: 'what the question check was given (run log)',
        drawn: n => n + ' drawn', notDrawn: n => n + ' not', noneDrawn: 'no draft', draftPrompt: 'the prompt the draft was written from (run log)',
        notStarted: 'The analysis did not start',
        // the Brief map - the steps of the brief's conversation: the drawer's words, what a box says where the coach said nothing, and its second line - the parts of the brief the step changed, in the tab's words
        map: 'Brief map', mapSub: (n, forks) => n + (n === 1 ? ' step' : ' steps') + (forks ? ' · ' + forks + (forks === 1 ? ' branch' : ' branches') : ''),
        mapRest: 'Click a step to go to it. Hover over one to read what was said.', asked1: 'your question', byHand: 'You changed a line', checked: 'Question check', wentOn: 'The Architect went on',
        info: { step: 'Step', follows: 'Follows', next: 'Follow-ups', changed: 'Changed', replied: 'Architect' }, onScreen: 'on screen', theStart: 'the start', none: 'none', nothing: 'nothing',
        part: { question: 'question', decision: 'what it is for', thinks: 'what you think', rests_on: 'why you think so', expects: 'what you expect', would_change: 'what would change your mind',
                also_check: 'other explanations', 'fixed.comparison': 'what is compared', 'fixed.measure': 'measured by', 'fixed.period': 'period', figures: 'figure', saved: 'builds on' },
        against: { head: 'How it turned out', expected: 'You expected', would: 'Would change your mind', checks: 'Also checked', missing: 'The report does not say.' }
    };
    const TEXT_CHARS = 600, QUESTION_CHARS = 4000;   // one line of a brief, and the question, as analyst/brief.py bounds them
    const CAP = { rests_on: 4, also_check: 2 };   // the design's counts (§2.2): three or four anchors, at most two rivals
    const TRIES = 2;                              // the rounds a figure's draft gets, as analyst/draft.py counts them
    const SKIPPED = 'The person skipped it.';     // why a reading the coach skipped was not made, as the reader says it (analyst/reader.py)
    const SINGLE = ['question', 'decision', 'thinks', 'expects', 'would_change'];
    const FIXED = [['comparison', 'What is compared'], ['measure', 'Measured by'], ['period', 'Period']];
    // the parts a coach can add by hand, in the brief's order, each under the name its place has; a list takes one line more
    const KINDS = [['decision', WORDS.head.decision], ['thinks', WORDS.head.thinks], ['rests_on.+', WORDS.head.rests_on], ['expects', WORDS.head.expects],
                   ['would_change', WORDS.head.would_change], ['also_check.+', WORDS.another]].concat(FIXED.map(f => ['fixed.' + f[0], f[1]]));
    const LOCKED = ['data'];                      // a fact from a lookup: left out, never changed (§2.6)
    const SOURCE = { architect: ['ar', 'Architect'], data: ['', 'data'], result: ['', 'last result'] };   // the coach's own lines carry no chip
    const MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
    const MARK = { 'holds': ['ok', '✓'], 'does not hold': ['no', '✕'], 'cannot be checked': ['q', '?'] };
    const VERDICT = { 'met': 'ok', 'not met': 'no', 'not seen': 'ok', 'seen': 'no', 'cannot tell': 'q' };
    const ICON = {
        pen: '<svg viewBox="0 0 24 24"><path d="M3 17.25V21h3.75L17.81 9.94l-3.75-3.75L3 17.25zM20.71 7.04c.39-.39.39-1.02 0-1.41l-2.34-2.34c-.39-.39-1.02-.39-1.41 0l-1.83 1.83 3.75 3.75 1.83-1.83z"/></svg>',
        ok: '<svg viewBox="0 0 24 24"><path d="M9 16.17L4.83 12l-1.42 1.41L9 19 21 7l-1.41-1.41z"/></svg>',
        x: '<svg viewBox="0 0 24 24"><path d="M19 6.41L17.59 5 12 10.59 6.41 5 5 6.41 10.59 12 5 17.59 6.41 19 12 13.41 17.59 19 19 17.59 13.41 12z"/></svg>',
        // the Git branch mark, as on the button to the Analysis map (stream-pane.js): a map of ways gone, where the
        // Workflow map keeps its own - boxes joined by lines (2.9, the product owner's choice)
        map: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><line x1="6" y1="3" x2="6" y2="15"/>' +
            '<circle cx="18" cy="6" r="3"/><circle cx="6" cy="18" r="3"/><path d="M18 9a9 9 0 0 1-9 9"/></svg>'
    };

    // ------------------------------------------------------------ helpers
    function esc(s) { return String(s == null ? '' : s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;'); }
    function clean(s) { return String(s == null ? '' : s).replace(/\s+/g, ' ').trim().slice(0, TEXT_CHARS); }
    function byId(id) { return document.getElementById(id); }
    function say(text) { if (typeof showSystemMessage === 'function') showSystemMessage(text); }
    function versionsOf(framing) { return framing && Array.isArray(framing.versions) ? framing.versions : []; }
    function turnsOf(framing) { return framing && Array.isArray(framing.turns) ? framing.turns : []; }
    function latestN(framing) { return Math.max(1, versionsOf(framing).length); }
    function versionAt(framing, n) {
        const all = versionsOf(framing);
        return all[Math.min(all.length, Math.max(1, n || all.length)) - 1] || { n: 1, by: 'person', changed: [], brief: {} };
    }
    // the version in use: the one the framing names (`at`: the step in use ends on it), else the last
    function inUse(framing) { const n = latestN(framing), at = framing && framing.at; return Number.isInteger(at) && at >= 1 && at <= n ? at : n; }

    // ---- the steps of the conversation (pure; analyst/steps.py holds the same on the server). A framing keeps its
    // steps, the one in use, the last of the way being walked, and - set aside - the turns of the steps off the way to
    // the one in use; its own turns are those of that way. One kept before steps has a step to a version, and its
    // conversation is one: nothing in it is cut.
    const steps = {
        kept(framing) { return !!(framing && Array.isArray(framing.steps) && framing.steps.length); },
        of(framing) { return steps.kept(framing) ? framing.steps : Array.from({ length: latestN(framing) }, (_, i) => ({ k: i + 1, from: i, v: i + 1, made: [i + 1] })); },
        // the step in use, and the last step of the way being walked
        on(framing) { return steps.kept(framing) ? framing.step : inUse(framing); },
        tip(framing) { return steps.kept(framing) ? framing.tip : latestN(framing); },
        // the steps from the first to step k, in order
        way(all, k) {
            const out = [];
            while (all[k - 1] && out.length < all.length) { out.unshift(all[k - 1]); k = all[k - 1].from; }
            return out;
        },
        // where the way through step k ends: where the way being walked does, while k is on it; else where the newest steps after k lead
        end(framing, k) {
            const all = steps.of(framing), tip = steps.tip(framing);
            if (steps.way(all, tip).some(s => s.k === k)) return tip;
            for (;;) {
                const after = all.filter(s => s.from === k).map(s => s.k);
                if (!after.length) return k;
                k = Math.max.apply(null, after);
            }
        },
        // where step k stands on the way through it: its place, of how many, and the steps before and after it
        place(framing, k) {
            const way = steps.way(steps.of(framing), steps.end(framing, k)).map(s => s.k), i = way.indexOf(k);
            return { i: i + 1, n: way.length, before: way[i - 1] || 0, after: way[i + 1] || 0 };
        },
        // the turns each step holds, by its number: those of the way to the step in use from the framing's turns, cut by their counts, the others from what is set aside
        held(framing) {
            const out = {}, aside = framing.aside || {};
            let at = 0;
            steps.of(framing).forEach(s => { out[s.k] = (aside[s.k] || {}).turns || []; });
            if (steps.kept(framing)) steps.way(framing.steps, framing.step).forEach(s => { out[s.k] = turnsOf(framing).slice(at, at + s.turns); at += s.turns; });
            return out;
        },
        // every turn the framing holds, those set aside too: what the brief has cost is counted over them
        all(framing) { const aside = (framing && framing.aside) || {}; return Object.keys(aside).reduce((out, k) => out.concat(aside[k].turns || []), turnsOf(framing)); },
        // the brief as it stood at the end of step k
        brief(framing, k) { const s = steps.of(framing)[k - 1]; return versionAt(framing, s ? s.v : inUse(framing)).brief || {}; },
        // the parts of the brief step k changed: those of the versions it made
        changed(framing, k) { const s = steps.of(framing)[k - 1]; return ((s && s.made) || []).reduce((out, n) => out.concat(versionAt(framing, n).changed || []), []); },
        // whether the brief of step k is the one in use - the one an analysis that ran was under: a step that changed nothing has the brief of the step before it
        used(framing, k) { return (steps.of(framing)[k - 1] || {}).v === inUse(framing); }
    };
    // the framing with step k in use, as the server will have it once the request that names k is taken (pure;
    // analyst/steps.py go()): the version that stood at the step's end is the one in use and - where the framing keeps
    // steps - its turns are those of the way to the step, the others' set aside. A step it does not have changes nothing
    function go(framing, k) {
        const all = steps.of(framing), to = Number.isInteger(k) ? all[k - 1] : null;
        if (!to || k === steps.on(framing)) return framing || {};
        const out = Object.assign({}, framing);
        delete out.at;
        if (to.v < latestN(framing)) out.at = to.v;
        if (!steps.kept(framing)) return out;
        const held = steps.held(framing), on = steps.way(all, k).map(s => s.k);
        Object.assign(out, { step: k, tip: steps.end(framing, k), turns: on.reduce((said, n) => said.concat(held[n]), []), aside: {} });
        all.forEach(s => { if (on.indexOf(s.k) < 0 && held[s.k].length) out.aside[s.k] = { turns: held[s.k] }; });
        return out;
    }
    function valueAt(brief, path) {
        const part = path.split('.')[0], at = path.split('.')[1];
        if (part === 'rests_on' || part === 'also_check') return at === '+' ? '' : (((brief[part] || [])[Number(at)] || {}).text || '');
        if (part === 'fixed') return (brief.fixed || {})[at] || '';
        return brief[part] || '';
    }
    function day(iso) { const m = /^(\d{4})-(\d{2})-(\d{2})/.exec(String(iso || '')); return m ? Number(m[3]) + ' ' + MONTHS[Number(m[2]) - 1] + ' ' + m[1] : String(iso || ''); }
    // the saved analyses the readings among `turns` found: one entry to an analysis, in the order found, its passages under it
    function foundIn(turns) {
        const out = [];
        (turns || []).forEach(t => {
            if (t.who !== 'memory' || t.failed) return;
            (t.found || []).forEach(f => {
                let g = out.find(x => x.id === f.id);
                if (!g) { g = { id: f.id, when: f.when, question: f.question, passages: [] }; out.push(g); }
                if (!g.passages.some(p => p.quote === f.quote)) g.passages.push({ quote: f.quote, note: f.note || '' });
            });
        });
        return out;
    }
    // the saved analyses a brief builds on: one entry to an analysis, in the brief's order, with where its passages stand
    function builtOn(brief) {
        const out = [];
        ((brief || {}).saved || []).forEach((s, i) => {
            if (!s.accepted) return;
            const id = s.thread + '/' + s.run;
            let g = out.find(x => x.id === id);
            if (!g) { g = { id, thread: s.thread, run: s.run, when: s.when, question: s.question, paths: [] }; out.push(g); }
            g.paths.push('saved.' + i);
        });
        return out;
    }
    // whether a brief gives the Analyst anything beside the question (analyst/brief.py agreed()): one that does not is no brief
    function given(brief) {
        const b = brief || {};
        return !!(b.decision || b.thinks || b.expects || b.would_change || (b.rests_on || []).length || (b.also_check || []).some(r => r.source !== 'architect' || r.accepted) ||
                  Object.keys(b.fixed || {}).length || builtOn(b).length || (b.set_aside || []).length || (b.figures || []).length);
    }

    // ------------------------------------------------------------ the brief with one line changed (pure)
    // Returns {brief, changed, removed} - the brief as it would stand, the parts the change touched, the index of a line
    // left out - or null when nothing would change. An empty text clears a part or leaves a line out; a line the coach
    // changes is their own: it loses its mark until it is checked again (§2.6), and a proposal of the Architect's its box.
    function apply(brief, path, text) {
        const part = String(path).split('.')[0], at = String(path).split('.')[1];
        const b = JSON.parse(JSON.stringify(brief || {}));
        const t = part === 'question' ? String(text == null ? '' : text).trim().slice(0, QUESTION_CHARS) : clean(text);      // the question keeps its lines
        if (part === 'rests_on' || part === 'also_check') {
            const list = Array.isArray(b[part]) ? b[part] : [];
            const made = part === 'rests_on' ? { text: t, source: 'person', mark: '' } : { text: t };
            if (at === '+') {
                if (!t || list.length >= CAP[part]) return null;
                b[part] = list.concat([made]);
                return { brief: b, changed: [part + '.' + list.length] };
            }
            const i = Number(at), was = list[i];
            if (!was || clean(was.text) === t || (t && LOCKED.indexOf(was.source) >= 0)) return null;
            if (t) { list[i] = made; return { brief: b, changed: [path] }; }
            list.splice(i, 1);
            if (!list.length) delete b[part];
            return { brief: b, changed: [part], removed: i };
        }
        if (part === 'fixed') {
            if (!FIXED.some(f => f[0] === at)) return null;
            const fixed = b.fixed && typeof b.fixed === 'object' ? b.fixed : {};
            if (clean(fixed[at]) === t) return null;
            if (t) fixed[at] = t; else delete fixed[at];
            if (Object.keys(fixed).length) b.fixed = fixed; else delete b.fixed;
            return { brief: b, changed: [path] };
        }
        if (SINGLE.indexOf(part) < 0 || (part === 'question' ? !t || b.question === t : clean(b[part]) === t)) return null;
        if (t) b[part] = t; else delete b[part];
        return { brief: b, changed: [path] };
    }

    // the brief with a proposal of the Architect's accepted or no longer (pure): {brief, changed}, or null for any other line
    function tick(brief, path) {
        const b = JSON.parse(JSON.stringify(brief || {}));
        const line = String(path).split('.')[0] === 'also_check' ? (b.also_check || [])[Number(String(path).split('.')[1])] : null;
        if (!line || line.source !== 'architect') return null;
        line.accepted = !line.accepted;
        return { brief: b, changed: [path] };
    }
    // the brief no longer built on one saved analysis, named by its id (pure): {brief, changed}, or null when it does not build on it
    function unbuild(brief, id) {
        const b = JSON.parse(JSON.stringify(brief || {}));
        const kept = (b.saved || []).filter(s => s.thread + '/' + s.run !== id);
        if (kept.length === (b.saved || []).length) return null;
        if (kept.length) b.saved = kept; else delete b.saved;
        return { brief: b, changed: ['saved'] };
    }
    // the brief without one of its figures, named by its place (pure): {brief, changed}, or null when no figure stands there
    function unfigure(brief, path) {
        const b = JSON.parse(JSON.stringify(brief || {})), at = /^figures\.(\d+)$/.exec(String(path));
        if (!at || !(b.figures || [])[Number(at[1])]) return null;
        b.figures.splice(Number(at[1]), 1);
        if (!b.figures.length) delete b.figures;
        return { brief: b, changed: ['figures'] };
    }

    // ------------------------------------------------------------ a figure without a draft (pure: returns markup)
    // The grey window that stands in a figure's place: one line in its middle - softly pulsing while the draft is on
    // its way (live) - and, where there is one, the reason under the mouse (docs/ARCHITECT_DESIGN.md §2.20).
    const windowOf = (line, live, why) => '<div class="ar-wait' + (live ? ' live' : '') + '"' + (why ? ' title="' + esc(why) + '"' : '') + '><span>' + line + '</span></div>';

    // ------------------------------------------------------------ the report's part "Against the brief": out of the answer (pure)
    const INLINE = '(?:\\s*</?(?:strong|em|b|i|code)\\b[^>]*>\\s*)*';
    function plain(html) { return String(html).replace(/<[^>]+>/g, '').replace(/&nbsp;/g, ' ').replace(/&amp;/g, '&').replace(/\s+/g, ' ').trim(); }
    // the lines of the part: its list items, or its paragraphs line by line; [] when it holds anything else (a table, a
    // list inside a list), which is then left as the report wrote it
    function sectionLines(body) {
        const lines = [];
        const rest = String(body).replace(/<li\b[^>]*>([\s\S]*?)<\/li>|<p\b[^>]*>([\s\S]*?)<\/p>/gi, (m, li, p) => {
            if (li != null) lines.push(li.replace(/^\s*<p\b[^>]*>([\s\S]*)<\/p>\s*$/i, '$1').trim());
            else p.split(/<br\s*\/?>|\n/i).forEach(x => { if (x.trim()) lines.push(x.trim()); });
            return '';
        }).replace(/<\/?(?:ul|ol)\b[^>]*>/gi, '');
        return rest.trim() ? [] : lines.filter(x => plain(x));
    }
    // a line that opens with a label and a verdict word: the word, and the line without both
    function verdictLine(html, label, words) {
        const lead = new RegExp('^' + INLINE + '(?:' + label + ')' + INLINE + '\\s*[:\\-\\u2013\\u2014]' + INLINE + '\\s*', 'i').exec(html);
        if (!lead) return null;
        let rest = html.slice(lead[0].length);
        const first = new RegExp('^' + INLINE + '(' + words.join('|') + ')\\b' + INLINE + '[\\s:;,.\\-\\u2013\\u2014]*', 'i').exec(rest);
        if (first) return { verdict: first[1].toLowerCase(), html: rest.slice(first[0].length) };
        const said = plain(rest).toLowerCase();
        return { verdict: words.find(w => new RegExp('\\b' + w + '\\b').test(said)) || '', html: rest };
    }
    // a row of the card - three cells, the verdict's empty when the line gives none: the card is one grid (tabs.css)
    const row = (k, html, v) => '<div class="r"><span class="k">' + k + '</span> <span class="t">' + html + '</span> <span class="v' + (v ? ' ' + VERDICT[v] : '') + '">' + (v || '') + '</span></div>';
    // the part's lines as the card's rows: what was expected and what would change the coach's mind, each with its
    // verdict; the checks after, the first labelled
    function rowsOf(lines) {
        let checks = 0;
        return lines.map(html => {
            const e = verdictLine(html, 'expected|expectation', ['not met', 'cannot tell', 'met']);        // "not met" before "met", as the engine reads it
            if (e) return row(WORDS.against.expected, e.html, e.verdict);
            const w = verdictLine(html, '(?:what )?would change (?:their|your) mind', ['not seen', 'cannot tell', 'seen']);
            if (w) return row(WORDS.against.would, w.html, w.verdict);
            return row(checks++ ? '' : WORDS.against.checks, html, /\bcannot tell\b/i.test(plain(html)) ? 'cannot tell' : '');
        }).join('');
    }
    // the card as an answer kept before 0312 holds it, with its rows; and the engine's line at a report's foot that says
    // the part is missing (analyst/session.py BRIEF_UNANSWERED), as the page renders it
    const KEPT = /<div class="ar-against"><div class="label">[^<]*<\/div>((?:<div class="r">[\s\S]*?<span class="v[^"]*">[^<]*<\/span><\/div>)*)<\/div>/;
    const MISSING = /<blockquote>\s*<p>CHECK: this report does not say how the result stands against the brief\.<\/p>\s*<\/blockquote>\s*/;
    // The answer without what it says against its brief (0312): the part under its heading, as the report wrote it; the
    // card an answer kept from before holds; the engine's line that the part is missing. {html: the answer without them,
    // against: the rows of the card the run's Brief tab shows (turnedOut()) - a part the rows cannot hold whole (a
    // table, a list inside a list) as the report wrote it; '' where the answer says nothing against a brief}
    function cutAnswer(html) {
        let s = String(html == null ? '' : html), rows = '';
        const without = m => s.slice(0, m.index) + s.slice(m.index + m[0].length);
        const kept = KEPT.exec(s);
        if (kept) { rows = kept[1]; s = without(kept); }
        const head = /<h([1-6])\b[^>]*>\s*Against the brief\s*:?\s*<\/h\1>/i.exec(s);
        if (head) {
            const after = s.slice(head.index + head[0].length), end = after.search(/<h[1-6]\b|<blockquote\b|<hr\b/i);      // the next part, or the engine's lines at the report's foot
            const body = (end < 0 ? after : after.slice(0, end)).trim(), lines = sectionLines(body);
            rows = lines.length ? rowsOf(lines) : body ? '<div class="as-is">' + body + '</div>' : '';
            s = s.slice(0, head.index) + (end < 0 ? '' : after.slice(end));
        }
        const missing = MISSING.exec(s);
        if (missing) { rows += row('', WORDS.against.missing, ''); s = without(missing); }
        return { html: s, against: rows };
    }

    // ------------------------------------------------------------ builders (pure: return HTML)
    const build = {
        // one line of the brief: its text - empty where the coach is adding the part, and the line is then typed in; a
        // pencil where the coach can change it, a cross where they can leave it out; a box to tick on what the
        // Architect proposed. o: {list, source, mark, note, shows, locked, tick}
        line(c, path, text, o) {
            o = o || {};
            const can = c.edit && !(text && o.locked);
            const mark = MARK[o.mark] ? '<span class="mk ' + MARK[o.mark][0] + '" title="' + esc(o.mark) + '">' + MARK[o.mark][1] + '</span>'
                : o.tick == null ? '' : '<button type="button" class="tick' + (o.tick ? ' on' : '') + '" role="checkbox" aria-checked="' + !!o.tick + '" title="' + WORDS.tick + '"' +
                    (c.edit ? ' data-ar="tick"' : ' disabled') + '>' + (o.tick ? ICON.ok : '') + '</button>';
            const under = [o.note ? '<span class="fact' + (o.mark === 'does not hold' ? ' no' : '') + '">' + esc(o.note) + '</span>' : '',
                           o.shows ? '<span class="fact">' + esc(o.shows) + '</span>' : ''].join('');
            const tools = text && c.edit ? (can ? '<button type="button" class="pen" data-ar="edit" title="Change">' + ICON.pen + '</button>' : '')
                                           + (o.list ? '<button type="button" class="drop" data-ar="drop" title="' + WORDS.leave + '">' + ICON.x + '</button>' : '') : '';
            const chip = SOURCE[o.source] ? '<span class="src' + (SOURCE[o.source][0] ? ' ' + SOURCE[o.source][0] : '') + '">' + SOURCE[o.source][1] + '</span>' : '';
            return '<div class="ar-line' + (c.changed.indexOf(path) >= 0 ? ' changed' : '') + '" data-path="' + esc(path) + '">' + mark + '<span class="tx">' + esc(text) + under + '</span>' + tools + chip + '</div>';
        },
        // a list of the brief: its lines, and the place for one more where the coach is adding it
        lines(c, part, items, of, adding) {
            const rows = (items || []).map((x, i) => build.line(c, part + '.' + i, x.text, Object.assign({ list: true, locked: LOCKED.indexOf(x.source) >= 0 }, of(x))));
            return rows.concat(adding === part + '.+' ? [build.line(c, part + '.+', '')] : []).join('');
        },
        // which step of the conversation is on screen, of how many on the way through it, the arrows to the one before
        // and the one after, and - where the framing keeps steps - the button to the map of them all. held: the
        // Architect is replying - what is on its way goes on from the step it left, so none of them can be pressed
        stepper(framing, shown, held) {
            const at = steps.place(framing, shown), off = held ? ' disabled' : '';
            const arrow = (d, glyph, title, to) => '<button type="button" data-ar="step" data-step="' + d + '" title="' + title + '" aria-label="' + title + '"' + (to ? off : ' disabled') + '>' + glyph + '</button>';
            return '<div class="ar-ver"><span class="k">' + WORDS.step + '</span>' + arrow(-1, '‹', WORDS.before, at.before) + '<b>' + WORDS.of(at.i, at.n) + '</b>' + arrow(1, '›', WORDS.after, at.after) +
                (steps.kept(framing) ? '<button type="button" class="ar-map" data-ar="map" title="' + WORDS.map + '" aria-label="' + WORDS.map + '"' + off + '>' + ICON.map + '</button>' : '') + '</div>';
        },
        // the button that shows a saved analysis whole, in a dialog over the page
        view(thread, run) {
            return thread && run ? '<button type="button" class="ar-open" data-ar="open" data-thread="' + esc(thread) + '" data-run="' + esc(run) + '">' + WORDS.view + '</button>' : '';
        },
        // a saved analysis the brief builds on: its day and what was asked then; View, and a cross to build on it no longer
        built(c, g) {
            return '<div class="ar-line ar-built' + (g.paths.some(p => c.changed.indexOf(p) >= 0) ? ' changed' : '') + '"><span class="tx">' + esc(day(g.when) + ' · ' + g.question) + '</span>' +
                build.view(g.thread, g.run) + (c.edit ? '<button type="button" class="drop" data-ar="unbuild" data-id="' + esc(g.id) + '" title="' + WORDS.leave + '">' + ICON.x + '</button>' : '') + '</div>';
        },
        // a figure of the brief (i: its place): its number and title, and a cross to take it out while the brief can
        // be changed. Where its draft was drawn (c.drafts, by the figure's key): the word that it is a draft - on
        // made-up numbers, where they are -, the place the page draws its plot in (mount()) and, on made-up numbers,
        // the line that says so. Otherwise the grey window, with one line: a draft is on its way (c.drawing: for a
        // figure whose first draft failed too, not for one tried twice), none could be drawn - why, under the mouse -,
        // or none was drawn: yet, while the brief can be changed. The window is in the markup of a drawn figure too:
        // it is what shows if the plot cannot be shown. How the Architect described the figure is not on the page
        figure(c, fig, i) {
            const key = (c.keys || [])[i], d = (key && (c.drafts || {})[key]) || {}, drawn = !!d.basis, madeUp = drawn && d.basis !== 'computed';
            const live = c.drawing && !drawn && !(d.failed && (Number(d.tries) || 1) >= TRIES);
            return '<div class="ar-fig' + (drawn ? ' drawn' : '') + (c.changed.indexOf('figures.' + i) >= 0 ? ' changed' : '') + '"><div class="hd"><span class="n">' + (i + 1) + '</span><span class="t">' + esc(fig.title) + '</span>' +
                (drawn ? '<span class="tag' + (madeUp ? ' mu' : '') + '">' + WORDS.draft + (madeUp ? ' · ' + WORDS.madeUp : '') + '</span>' : '') +
                (c.edit ? '<button type="button" class="drop" data-ar="unfigure" data-path="figures.' + i + '" title="' + WORDS.leave + '">' + ICON.x + '</button>' : '') + '</div>' +
                (drawn ? '<div class="plot" data-key="' + esc(key) + '"' + (madeUp ? ' data-made-up="1"' : '') + '></div>' + (madeUp ? '<div class="cap">' + WORDS.madeUpNote + '</div>' : '') : '') +
                (drawn ? windowOf(WORDS.notShown) : live ? windowOf(WORDS.drawing, true) : d.failed ? windowOf(WORDS.noDraft, false, d.failed) : windowOf(c.edit ? WORDS.noDraftYet : WORDS.notDrafted)) + '</div>';
        },
        // the saved analyses a reading found, to read: an analysis to a line with View - under the conversation's row -
        // or in full (o.full: its passages and the reader's notes), marked where the brief builds on it (o.built: ids)
        found(groups, o) {
            o = o || {};
            return groups.map(g => {
                const at = String(g.id).split('/');
                return '<div class="it"><div class="hd"><span class="q">' + esc(day(g.when) + ' · ' + g.question) + '</span>' +
                    ((o.built || []).indexOf(g.id) >= 0 ? '<span class="tag">' + WORDS.builtOn + '</span>' : '') + build.view(at[0], at[1]) + '</div>' +
                    (o.full ? g.passages.map(p => '<div class="qt">' + esc(p.quote) + '</div>' + (p.note ? '<div class="why">' + esc(p.note) + '</div>' : '')).join('') : '') + '</div>';
            }).join('');
        },
        // the Brief tab: on top what the Analyst will be asked, with the step of the conversation on screen; under it
        // the parts the Analyst gets with it, as they stood at that step - those that hold something, and the one the
        // coach is adding (o.adding: its path) - and, while the brief can be changed, the one control that adds a part
        // (o.adds: its list is open), what the readings of the saved analyses found, and Start analysis, which names
        // the step when it is not the last of its way. o: {chain, thread, state: 'framing' | 'run', shown: the step on
        // screen, held: the Architect is replying, drawing: a draft of the figures is on its way, against: what the
        // run's report says against the brief - the card's rows (cutAnswer())}; the framing rides in the markup, with the thread the drafts' plots are
        // kept under and what the report says against the brief - shown at the foot of a step whose brief is the one the run was under
        brief(framing, o) {
            const all = steps.of(framing), shown = all[(o.shown || 0) - 1] ? o.shown : steps.on(framing), v = versionAt(framing, all[shown - 1].v), b = v.brief || {};
            const c = { edit: o.state === 'framing', changed: steps.changed(framing, shown), keys: v.keys || [], drafts: (framing && framing.drafts) || {}, drawing: !!o.drawing };
            const adding = c.edit ? (o.adding || '') : '';
            const part = (name, body) => body ? '<h3>' + name + '</h3>' + body : '';
            const one = path => valueAt(b, path) || adding === path ? build.line(c, path, valueAt(b, path)) : '';
            const built = builtOn(b), found = c.edit ? foundIn(turnsOf(framing)) : [];
            const kinds = c.edit ? KINDS.filter(k => k[0].slice(-2) === '.+' ? (b[k[0].slice(0, -2)] || []).length < CAP[k[0].slice(0, -2)] : !valueAt(b, k[0])) : [];
            const aside = (b.set_aside || []).map(x => '<div class="ar-line"><span class="tx">' + esc(x) + '</span></div>').join('');
            return '<div class="ar-brief" data-chain="' + esc(o.chain) + '" data-thread="' + esc(o.thread) + '" data-state="' + esc(o.state) + '" data-shown="' + shown + '"' +
                    (o.adds ? ' data-adds="1"' : '') + (o.drawing ? ' data-drawing="1"' : '') + (o.against ? ' data-against="' + esc(o.against) + '"' : '') +
                    ' data-framing="' + esc(JSON.stringify(framing || {})) + '">' +
                '<div class="ar-top"><span class="label">' + WORDS.asked + '</span>' + build.stepper(framing, shown, o.held) + '</div>' +
                '<h1 class="ar-line ar-q' + (c.changed.indexOf('question') >= 0 ? ' changed' : '') + '" data-path="question"><span class="tx">' + esc(b.question || '') + '</span>' +
                    (c.edit ? '<button type="button" class="pen" data-ar="edit" title="Change">' + ICON.pen + '</button>' : '') + '</h1>' +
                (c.edit ? '<p class="ar-gets">' + WORDS.gets + '</p>' : '') +
                part(WORDS.head.decision, one('decision')) +
                part(WORDS.head.thinks, one('thinks')) +
                part(WORDS.head.rests_on, build.lines(c, 'rests_on', b.rests_on, x => ({ source: x.source, mark: x.mark, note: x.note }), adding)) +
                part(WORDS.head.expects, one('expects')) +
                part(WORDS.head.would_change, one('would_change')) +
                part(WORDS.head.also_check, build.lines(c, 'also_check', b.also_check, x => ({ shows: x.shows, source: x.source, tick: x.source === 'architect' ? !!x.accepted : null }), adding)) +
                FIXED.map(f => part(f[1], one('fixed.' + f[0]))).join('') +
                part(WORDS.head.figures, (b.figures || []).length ? '<div class="ar-figs">' + b.figures.map((f, i) => build.figure(c, f, i)).join('') + '</div>' : '') +
                part(WORDS.head.builds, built.map(g => build.built(c, g)).join('')) +
                part(WORDS.head.aside, aside) +
                (given(b) && !(framing && framing.data === false) ? '<p class="ar-always">' + WORDS.always + '</p>' : '') +      // the checks of a briefed run on data
                (kinds.length ? '<div class="ar-more"><button type="button" class="ar-add" data-ar="more" aria-expanded="' + !!o.adds + '">' + WORDS.add + '</button>' +
                    (o.adds ? '<div class="ar-kinds">' + kinds.map(k => '<button type="button" data-ar="add" data-path="' + k[0] + '">' + k[1] + '</button>').join('') + '</div>' : '') + '</div>' : '') +
                (found.length ? '<div class="ar-memory"><h3>' + WORDS.memory + '</h3><p class="note">' + WORDS.memoryNote + '</p>' + build.found(found, { full: true, built: built.map(g => g.id) }) + '</div>' : '') +
                (c.edit ? '<div class="ar-foot"><button type="button" class="ui-btn primary" data-ar="start">' +
                    (steps.place(framing, shown).after ? WORDS.startFrom(steps.place(framing, shown).i) : WORDS.start) + '</button></div>' : '') +
                (o.against && steps.used(framing, shown) ? build.turnedOut(o.against) : '') +
                '</div>';
        },
        // what the run's report says against the brief, as a card of verdicts under it (rows: cutAnswer())
        turnedOut(rows) {
            return '<div class="ar-against"><div class="label">' + WORDS.against.head + '</div>' + rows + '</div>';
        },
        // the field a line is typed in
        editor(text, question) {
            return '<span class="ar-edit"><textarea class="ar-input" rows="1" maxlength="' + (question ? QUESTION_CHARS : TEXT_CHARS) + '">' + esc(text) + '</textarea>' +
                '<button type="button" class="ok" data-ar="keep" title="Keep">' + ICON.ok + '</button><button type="button" class="no" data-ar="cancel" title="Cancel">' + ICON.x + '</button></span>';
        },
        you(text) { return '<div class="ar-msg you"><span class="who">You</span>' + esc(text) + '</div>'; },
        // a message of the Architect's: its words, the button to the prompt it received (the run log's call) and its
        // choices while they can still be clicked
        said(turn, chain, live) {
            const prompt = turn.call ? '<button class="agent-instructions-btn sp-prompt" type="button" title="the prompt the Architect received (run log)" data-agent="Architect" data-chain="' +
                esc(chain) + '" data-call="' + esc(turn.call) + '">⌘</button>' : '';
            const choices = live && (turn.choices || []).length ? '<div class="ar-choices">' + turn.choices.map(c => '<button type="button" class="ar-choice" data-ar="choice">' + esc(c) + '</button>').join('') + '</div>' : '';
            return '<div class="ar-msg arch"><span class="who">Architect' + prompt + '</span>' + esc(turn.text) + choices + '</div>';
        },
        // the question changed with the reply above it: the Architect worded it, and it is the top box from that step on (at: the step's place on its way)
        asked(at) {
            return '<div class="sp-row tool read"><span>✓</span><span class="in">' + WORDS.question + '</span><span class="out">' + WORDS.updated + '</span><span class="t">' + WORDS.stepN(esc(at)) + '</span></div>';
        },
        // a draft of the figures, done: how many were drawn and how many were not - why is the row's title - the
        // seconds, and the button to the prompt its cell was written from (the run log's call)
        drafted(turn, chain) {
            const n = (turn.drawn || []).length, m = (turn.missing || []).length;
            const prompt = turn.call ? '<button class="agent-instructions-btn sp-prompt" type="button" title="' + WORDS.draftPrompt + '" data-agent="Draft" data-chain="' + esc(chain) +
                '" data-call="' + esc(turn.call) + '">⌘</button>' : '';
            return '<div class="sp-row tool read' + (m ? ' skipped" title="' + esc(turn.failed || '') : '') + '"><span>' + (m ? '–' : '✓') + '</span><span class="in">' + WORDS.figures + '</span>' +
                '<span class="out">' + (n ? WORDS.drawn(n) + (m ? ' · ' + WORDS.notDrawn(m) : '') : WORDS.noneDrawn) + '</span><span class="t">' + Math.max(1, Math.round(Number(turn.secs) || 0)) + ' s</span>' +
                prompt + '</div>';
        },
        // something on its way - a draft, the question's check: a row that says what is being done
        pending(doing) {
            return '<div class="sp-row tool read pending"><span class="live"></span><span class="in">' + doing + '</span></div>';
        },
        // the question read as the Analyst will read it, before its analysis (0313): it stands on its own, or the
        // Analyst cannot place some of its words - which, read whole: the row wraps; the seconds, and the button to
        // what the reader was given (the run log's call)
        checkedQ(turn, chain) {
            const missing = turn.missing || [];
            const prompt = turn.call ? '<button class="agent-instructions-btn sp-prompt" type="button" title="' + WORDS.checkPrompt + '" data-agent="Question check" data-chain="' + esc(chain) +
                '" data-call="' + esc(turn.call) + '">⌘</button>' : '';
            return '<div class="sp-row tool read' + (missing.length ? ' skipped ar-unplaced' : '') + '"><span>' + (missing.length ? '–' : '✓') + '</span><span class="in">' + WORDS.checkQ + '</span>' +
                '<span class="out">' + (missing.length ? WORDS.unplaced + ' ' + missing.map(m => '“' + esc(m) + '”').join(' · ') : WORDS.standsAlone) + '</span>' +
                '<span class="t">' + Math.max(1, Math.round(Number(turn.secs) || 0)) + ' s</span>' + prompt + '</div>';
        },
        // in a conversation kept before steps: the coach went to another version of the brief before the message under it
        went(turn) {
            return '<div class="sp-row tool read"><span>✓</span><span class="in">' + WORDS.brief + '</span><span class="out">' + WORDS.inUse(esc(turn.v)) + '</span></div>';
        },
        // a part of an earlier analysis the Architect opened: what it is and how long - or why there is no such part
        opened(turn) {
            return '<div class="sp-row tool read' + (turn.missing ? ' skipped' : '') + '"><span>' + (turn.missing ? '–' : '✓') + '</span><span class="in">' + WORDS.opened + '</span>' +
                '<span class="out">' + esc(turn.missing || turn.label) + '</span>' + (turn.missing ? '' : '<span class="t">' + WORDS.chars(turn.chars) + '</span>') + '</div>';
        },
        // a round of lookups, as the pane shows a tool's row: how many gave a result, how many did not, the seconds;
        // what each found is the row's title, a line to a lookup
        checked(turn) {
            const found = turn.found || [], ran = found.filter(f => f.ran).length;
            return '<div class="sp-row tool read" title="' + esc(found.map(f => f.fact).join('\n')) + '"><span>✓</span><span class="in">' + WORDS.check + '</span>' +
                '<span class="out">' + WORDS.lookedUp(ran) + (ran < found.length ? ' · ' + WORDS.notLookedUp(found.length - ran) : '') + '</span>' +
                '<span class="t">' + Math.max(1, Math.round(Number(turn.secs) || 0)) + ' s</span></div>';
        },
        // a reading of the saved analyses, done: how many analyses it found, how many of the saved runs were read, the
        // seconds - or that the coach skipped it, or why nothing was read; under the row the analyses found, a line
        // each with View; the passages and what was found across them are the row's title
        recalled(turn) {
            const found = turn.found || [], across = turn.across, groups = foundIn([turn]);
            const lines = found.map(f => f.when + ' · ' + f.question + ': "' + f.quote + '"')
                .concat(across ? [across.topic + ': ' + (across.groups || []).map(g => (g.runs || []).length + ' × ' + g.label).join('; ')] : []);
            const out = turn.failed === SKIPPED ? WORDS.skipped : turn.failed ? WORDS.notRead + ' · ' + turn.failed
                : (groups.length ? WORDS.found(groups.length) : WORDS.noneFound) + ' · ' + WORDS.readOf(turn.read || 0, turn.of || 0);
            return '<div class="sp-row tool read' + (turn.failed ? ' skipped' : '') + '" title="' + esc(lines.join('\n')) + '"><span>' + (turn.failed ? '–' : '✓') + '</span><span class="in">' + WORDS.saved + '</span>' +
                '<span class="out">' + esc(out) + '</span><span class="t">' + Math.max(1, Math.round(Number(turn.secs) || 0)) + ' s</span></div>' +
                (groups.length ? '<div class="ar-found">' + build.found(groups) + '</div>' : '');
        },
        // a reading in flight: what is being done, how far it is, and Skip - once the server has said how many are
        // saved: it has started then, and a skip sent before would be lost. at: {read, of}
        reading(at) {
            return '<div class="sp-row tool read pending"><span class="live"></span><span class="in">' + WORDS.searching + '</span><span class="out">' + WORDS.readSoFar(at.read, at.of) + '</span>' +
                '<button type="button" class="ar-skip" data-ar="skip"' + (at.of == null ? ' disabled' : '') + '>' + WORDS.skip + '</button></div>';
        },
        // the conversation of the way to the step in use: the question, then what was said, what was looked up, what
        // the saved analyses hold, what was opened, where the question changed - at which step of the way -, what a
        // draft of the figures came to and, in a conversation kept before steps, where the coach went to another
        // version. o: {live: the last message's choices can be clicked - a draft's row may stand under it -, sent: a
        // message on its way, waiting: the Architect is replying, saved: the saved analyses are being read - how far
        // -, drawing: its reply stands and the draft is on its way, checking: the question is being read before its
        // analysis}
        talk(entry, o) {
            o = o || {};
            const turns = turnsOf(entry.framing), versions = versionsOf(entry.framing), can = o.live && !o.waiting;
            // the place on the way of the step each turn belongs to; in a conversation kept before steps, the version the turn left
            const way = steps.kept(entry.framing) ? steps.way(entry.framing.steps, entry.framing.step) : [];
            const places = way.reduce((out, s, i) => out.concat(Array(s.turns).fill(i + 1)), []), placeOf = (t, i) => places[i] || t.v;
            // a reply worded the question when the version it left is the Architect's, changed the question, and reads as the reply has it
            const worded = t => { const v = versions[(t.v || 0) - 1]; return !!(t.wording && v && v.by === 'architect' && (v.changed || []).indexOf('question') >= 0 && (v.brief || {}).question === t.wording); };
            return build.you((versionAt(entry.framing, 1).brief || {}).question || entry.queryText) +      // as it was first asked: the brief holds it as it stands now
                turns.map((t, i) => t.who === 'check' ? build.checked(t) : t.who === 'memory' ? build.recalled(t) : t.who === 'opened' ? build.opened(t) : t.who === 'version' ? build.went(t)
                    : t.who === 'draft' ? build.drafted(t, entry.chain_id) : t.who === 'reader' ? build.checkedQ(t, entry.chain_id)
                    : t.who === 'architect' ? build.said(t, entry.chain_id, can && turns.slice(i + 1).every(x => x.who === 'draft')) + (worded(t) ? build.asked(placeOf(t, i)) : '')
                    : build.you(t.text)).join('') +
                (o.sent ? build.you(o.sent) : '') +
                (o.waiting ? (o.saved ? build.reading(o.saved) : o.drawing ? build.pending(WORDS.drawingRow) : o.checking ? build.pending(WORDS.checkingRow)
                    : '<div class="ar-msg arch wait"><span class="who">Architect</span>' + WORDS.reading + '</div>') : '');
        },
        // the left pane of a brief not yet run: what the brief's calls have cost - those of the steps set aside too -
        // and the conversation. Which step is on screen is the Brief tab's to say, in one place
        pane(entry, o) {
            const cost = steps.all(entry.framing).reduce((sum, t) => sum + (Number(t.cost) || 0), 0);
            return '<div class="sp-strip"><span class="live idle"></span><span class="mode">Architect</span>' + (cost >= 0.005 ? '<span>$' + cost.toFixed(2) + '</span>' : '') + '</div>' +
                '<div class="sp-stream">' + build.talk(entry, Object.assign({ live: true }, o)) + '</div>';
        },
        // the framing folded to one row, above the run it started - from which step of the conversation: the way to it is inside
        fold(entry) {
            return '<details class="sp-turn ar-fold"><summary><span class="chev"></span><span class="n">Architect</span><span class="kind">brief · ' +
                WORDS.stepN(steps.place(entry.framing, steps.on(entry.framing)).i) + '</span>' +
                '<span class="peek">' + esc(entry.queryText) + '</span></summary><div class="sp-detail">' + build.talk(entry) + '</div></details>';
        },
        // a saved analysis in a dialog: what was asked, the day, whose data and which, the hints it was made under - a
        // branch, as the left pane says them -, the report; folded under it the conversation its brief came from - the
        // person's messages under "You", as the pane has them - and the brief, where it was framed, and the code of its cells
        savedDialog(run) {
            const data = run.data || {}, sub = [String(run.when || '').slice(0, 10), data.person, data.name, data.period, (run.marks || []).join(', ')].filter(Boolean).join(' · ');
            const report = typeof marked !== 'undefined' && marked.parse ? marked.parse(String(run.report || '')) : '<pre>' + esc(run.report) + '</pre>';
            const code = (run.cells || []).map(c => '<div class="cell-n">cell ' + esc(c.n) + '</div><pre>' + esc(c.code) + '</pre>').join('');
            const fold = (name, body) => body ? '<details class="ar-code"><summary>' + name + '</summary>' + body + '</details>' : '';
            const said = text => text ? '<pre class="said">' + esc(text) + '</pre>' : '';
            return '<div class="ui-dlg lg ar-saved-dlg" role="dialog" aria-modal="true"><div class="ui-dlg-h"><div><div class="title">' + esc(run.question || run.title || '') + '</div>' +
                '<div class="sub">' + esc(sub) + '</div>' + (run.hints || []).map(h => '<div class="hint"><b>' + WORDS.fromTurn(esc(h.turn)) + '</b>' + esc(h.text) + '</div>').join('') +
                '</div><span class="sp"></span><button class="x" type="button" data-ar="shut" aria-label="Close">' + ICON.x + '</button></div>' +
                '<div class="ui-dlg-b"><div class="markdown-content">' + report + '</div>' + fold(WORDS.talk, said(String(run.conversation || '').replace(/^Person: /gm, 'You: '))) + fold(WORDS.agreed, said(run.brief)) + fold(WORDS.code, code) + '</div></div>';
        }
    };

    // ------------------------------------------------------------ the page
    let on = false;            // the switch: a typed question is framed first
    let mine = false;          // the composer's words are the Architect's
    let busy = false;          // a change or a message is on its way to the server
    let talking = null;        // the exchange in flight: {entry, sent, saved: how far a reading of the saved analyses is}

    function isOn() { return on; }
    function setOn(value) {
        on = !!value;
        const sw = byId('architectSwitch');
        if (sw) { sw.classList.toggle('on', on); sw.setAttribute('aria-pressed', on ? 'true' : 'false'); }
        try { sessionStorage.setItem('architectOn', on ? '1' : '0'); } catch (e) { /* no storage: the switch lasts the page */ }
    }
    function post(url, body) {
        return window.authService.fetch(url, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) })
            .then(r => r.json().catch(() => ({})).then(json => ({ ok: r.ok, json: json || {} })));
    }
    function mark(r) {
        // how a chain's question was made, for its box on the Workflow map (§2.9)
        if (!r) return '';
        if (r.status === 'framing') return 'not run';
        if (r.framing || /id="tab-brief"/.test(r.tabContent || '')) return 'Architect';
        return window.NextQuestionsUI && window.NextQuestionsUI.made(r) ? 'next question' : '';
    }
    function framingInView() { const r = responses[currentResponseIndex]; return !!(r && r.status === 'framing'); }

    // ---- the drafts on the page (§2.20). The builders leave a place for each plot; once the tab stands, Plotly draws
    // it there. A plot is fetched once, by where it is kept; where it cannot be had - or the page has no Plotly - the
    // grey window stands in its place and says so.
    const plots = new Map();      // by a plot's address: the plot - or that the server holds none -, kept for the page's life; an answer that failed, and a server not reached, are asked for again
    const ACROSS = { xref: 'paper', yref: 'paper', x: 0.5, y: 0.5, showarrow: false, textangle: -18, opacity: 0.28, font: { size: 30, color: '#8a8a8a' } };
    // the layout a draft is drawn with (pure): the figure's own, fitted to its place and not to be dragged about - and,
    // on made-up numbers, with those words across it
    function draftLayout(layout, madeUp) {
        const own = layout || {};
        return Object.assign({}, own, { autosize: true, width: undefined, height: Math.max(280, Math.min(Number(own.height) || 360, 560)), dragmode: false,
                                        annotations: (own.annotations || []).concat(madeUp ? [Object.assign({ text: WORDS.madeUp }, ACROSS)] : []) });
    }
    function plotAt(url) {
        if (!plots.has(url)) plots.set(url, window.authService.fetch(url).then(r => (r.ok ? r.json() : r.status === 404 ? null : Promise.reject(new Error('HTTP ' + r.status))))
            .then(json => (json && json.plot) || null).catch(() => { plots.delete(url); return null; }));
        return plots.get(url);
    }
    // a figure whose plot cannot be shown: its place goes, with the words that said it was a draft, and the grey window under it says so
    function unshown(el) {
        const fig = el.closest('.ar-fig');
        fig.classList.remove('drawn');
        [fig.querySelector('.tag'), fig.querySelector('.cap'), el].forEach(x => { if (x) x.remove(); });
    }
    function mount(root) {
        if (!root) return;
        const at = [root.getAttribute('data-thread'), root.getAttribute('data-chain')];
        root.querySelectorAll('.ar-fig.drawn .plot').forEach(el => {
            if (el.arLive) return;
            el.arLive = true;                              // on the element, not in its markup: a tab restored from kept markup is drawn again
            plotAt('/architect/draft/' + at.concat(el.getAttribute('data-key')).map(encodeURIComponent).join('/')).then(plot => {
                el.innerHTML = '';                         // what kept markup held of an earlier drawing
                return Plotly.newPlot(el, plot.data, draftLayout(plot.layout, el.getAttribute('data-made-up') === '1'), { responsive: true, displayModeBar: false, scrollZoom: false });
            }).catch(() => unshown(el));                   // no plot, no Plotly on the page, or a plot it cannot draw
        });
    }
    function mountAll() { document.querySelectorAll('.ar-brief').forEach(mount); }

    // the left pane of a brief not yet run, its newest message in view
    function drawPane(entry) {
        const pane = byId('streamOutput'), mid = talking && talking.entry === entry;
        pane.innerHTML = build.pane(entry, mid ? { sent: talking.sent, waiting: true, saved: talking.saved, drawing: talking.drawing, checking: talking.checking } : {});
        pane.scrollTop = pane.scrollHeight;
    }
    // the Brief tab of a brief not yet run, as it stands now - its steps held while the Architect replies, its figures
    // saying so while their draft is on its way
    function briefOf(entry) {
        const mid = talking && talking.entry === entry;
        return build.brief(entry.framing, { chain: entry.chain_id, thread: entry.thread_id, state: 'framing', held: !!mid, drawing: !!(mid && talking.drawing) });
    }
    function show(entry) {
        drawPane(entry);
        byId('tabContainer').innerHTML = '<div id="tab-brief" class="tab active">Brief</div>';
        byId('contentOutput').innerHTML = '<div id="content-brief" class="tab-content active">' + briefOf(entry) + '</div>';
        mount(briefRoot());
    }
    // after a change: the brief and the pane in place, so the tab keeps its scroll
    function refresh(entry) {
        const root = briefRoot();
        if (root) { root.parentNode.innerHTML = briefOf(entry); mount(briefRoot()); }
        drawPane(entry);
        mapFollows();
    }
    // a chain comes on screen: a brief not yet run is drawn from its versions; any other Brief tab came with its markup, and its drafts are drawn in it
    function restore(entry) { if (entry && entry.status === 'framing') show(entry); else mountAll(); mapFollows(); }
    // While a brief not yet run is on screen the composer is the conversation with the Architect: held while it
    // replies or the saved analyses are read, and while another chain runs - whose Stop stays within reach. Anywhere
    // else it is as it was.
    function onChain(entry) {
        const framing = !!(entry && entry.status === 'framing');
        document.body.classList.toggle('ar-framing', framing);
        if (!framing) {
            if (mine) { mine = false; if (typeof composerUnlock === 'function') composerUnlock(); }
            return;
        }
        if (window.RoutinesUI && typeof window.RoutinesUI.inRunView === 'function' && window.RoutinesUI.inRunView()) return;      // a routine's run is on screen: its hold stands
        mine = true;
        const input = byId('queryInput'), send = byId('submitQuery');
        const running = typeof queryRunning !== 'undefined' && queryRunning;
        if (talking && talking.entry === entry || running) {
            if (typeof composerLock === 'function') composerLock(running ? WORDS.busyRun : talking.saved ? WORDS.readingSaved : talking.drawing ? WORDS.drawingHold : talking.checking ? WORDS.checkingHold : WORDS.replying);
            if (send && running) send.disabled = false;
            return;
        }
        if (typeof composerUnlock === 'function') composerUnlock();
        if (input && !input.disabled) {                        // not held by anything else: the conversation's words, the composer's own kept for later
            if (input.getAttribute('data-placeholder') == null) input.setAttribute('data-placeholder', input.placeholder || '');
            input.placeholder = WORDS.answer;
        }
    }

    // a question typed with the switch on: its framing run is opened on the record, the page moves to it, and the
    // Architect takes its first turn
    function open(question) {
        if (busy) { if (talking) say(WORDS.replying + '.'); return; }
        busy = true;
        post('/architect/open', { question, thread_id: currentData.thread_id || null, chain_id: currentData.chain_id || null }).then(res => {
            if (!res.ok) { say(res.json.message || res.json.error || WORDS.notOpened + '.'); return null; }
            const d = res.json;
            const entry = { status: 'framing', chain_id: d.chain_id, thread_id: d.thread_id, parentChainId: d.parent_chain_id == null ? null : d.parent_chain_id, queryText: question,
                            tabContent: '', contentOutput: '', streamOutput: '', taskContents: {}, technicalAnswer: null, reportHead: null, framing: d.framing };
            responses.push(entry);
            currentResponseIndex = responses.length - 1;
            const input = byId('queryInput');
            if (input) { input.value = ''; input.style.height = 'auto'; }
            loadResponseContent(entry);
            if (typeof updateNavigationButtons === 'function') updateNavigationButtons();
            return entry;
        }).catch(() => { say(WORDS.notOpened + ': ' + WORDS.unreachable + '.'); return null; }).then(entry => { busy = false; if (entry) exchange(entry, ''); });
    }

    // What the exchange's stream ends on: the route's closing message - the framing, or why no reply was kept. A
    // stream cut short leaves the last error it carried; a refusal (the balance, the month's queries) is one JSON
    // object. The model's own traffic - its text as it arrives - is passed over.
    function closing(body) {
        let out = {};
        String(body || '').split('\n').forEach(line => {
            if (!line.trim()) return;
            let d = null;
            try { d = JSON.parse(line); } catch (e) { return; }
            if (d && d.architect) out = d.architect;
            else if (d && (d.message || d.error || d.routine_error)) out = { error: d.message || d.error || d.routine_error };
        });
        return out;
    }
    // A response's body, each of its JSON lines handed to `each` - where one is given - as it arrives, where the
    // browser gives the body as a stream; resolves to the whole body.
    function readStream(r, each) {
        const feed = line => { let d = null; try { d = line.trim() ? JSON.parse(line) : null; } catch (e) { d = null; } if (d && typeof each === 'function') each(d); };
        if (!r.body || typeof r.body.getReader !== 'function') return r.text().then(body => { String(body || '').split('\n').forEach(feed); return body; });
        const reader = r.body.getReader(), dec = new TextDecoder();
        let all = '', rest = '';
        const pump = () => reader.read().then(part => {
            if (part.value) {
                const text = dec.decode(part.value, { stream: true }), lines = (rest + text).split('\n');
                all += text; rest = lines.pop(); lines.forEach(feed);
            }
            if (!part.done) return pump();
            feed(rest);
            return all;
        });
        return pump();
    }
    // a framing taken as the chain's - as the server sent it, or with a step put in use: the question of the
    // version in use is the chain's own
    function take(entry, framing) {
        entry.framing = framing;
        entry.queryText = (versionAt(framing, inUse(framing)).brief || {}).question || entry.queryText;
    }
    // What the stream of an exchange carries before it ends, taken as it arrives: how far a reading of the saved
    // analyses is - the pane follows the count - and, where a draft of the figures follows the reply, the framing with
    // the reply - shown while they are drawn. `mine`: the exchange's own state, as long as it is the one going on
    function along(entry, mine, draw) {
        return d => {
            if (talking !== mine) return;
            if (d.type === 'architect_saved') {
                mine.saved = { read: Number(d.read) || 0, of: d.of == null ? null : Number(d.of) };
                if (responses[currentResponseIndex] === entry) { drawPane(entry); onChain(entry); }
            } else if (d.type === 'architect_draft' && d.framing) {      // the reply is kept: it is shown while its figures are drawn
                take(entry, d.framing);
                Object.assign(mine, { sent: '', saved: null, drawing: true });      // a draft on its way is said before a read
                draw();
            }
        };
    }
    // One exchange with the Architect: what the coach said - nothing on its first turn - and its reply. The request
    // names the step in use here - the one on screen - and the exchange goes on from it. Where the reply had the data
    // looked up, the saved analyses read or a part of an earlier analysis opened, the Architect goes on at once: one
    // more exchange, with nothing said. While the saved analyses are read the pane follows the count. Where a draft of
    // the figures follows the reply, the stream carries the framing with the reply first: the page shows it, and the
    // figures as grey windows, until the stream ends on the framing with the draft - a stream that ends before it
    // leaves the reply standing, its figures without a draft. Resolves to whether the last reply was kept; when one
    // was not, the brief stands as it did and the reason is said.
    function exchange(entry, text) {
        if (busy || !entry || entry.status !== 'framing') return Promise.resolve(false);
        busy = true;
        const mine = talking = { entry, sent: text };
        const inView = () => responses[currentResponseIndex] === entry;
        const draw = () => { if (inView()) { refresh(entry); onChain(entry); } };
        const lost = why => { if (!mine.drawing) say(why); return !!mine.drawing; };      // no reply is said, unless one already stands: the stream ended while its draft was drawn
        draw();
        return window.authService.fetch('/architect/say', { method: 'POST', headers: { 'Content-Type': 'application/json' },
                                                             body: JSON.stringify({ thread_id: entry.thread_id, chain_id: entry.chain_id, text: text || null, step: steps.on(entry.framing) }) })
            .then(r => readStream(r, along(entry, mine, draw))).then(body => {
                const out = closing(body);
                if (out.framing) { take(entry, out.framing); return true; }
                return lost(out.error || WORDS.noReply + '.');
            }).catch(() => lost(WORDS.noReply + ': ' + WORDS.unreachable + '.')).then(kept => {
                busy = false; talking = null;
                const turns = turnsOf(entry.framing);
                if (kept && turns.length && ['check', 'memory', 'opened'].indexOf(turns[turns.length - 1].who) >= 0) return exchange(entry, '');
                draw();
                const input = byId('queryInput');
                if (!kept && text && inView() && input && !input.value) input.value = text;      // what was typed is not lost
                return kept;
            });
    }
    // what the coach typed or chose, said to the Architect of the brief on screen; a line being typed in the brief is
    // kept first
    function tell(text) {
        const entry = responses[currentResponseIndex], root = briefRoot();
        text = String(text || '').trim();
        if (busy || !text || !entry || entry.status !== 'framing') return Promise.resolve(false);
        if (typeof queryRunning !== 'undefined' && queryRunning) { say(WORDS.busyRun); return Promise.resolve(false); }
        return (root ? keep(root) : Promise.resolve({})).then(out => {
            if (!out) return false;
            const input = byId('queryInput');
            if (input) { input.value = ''; input.style.height = 'auto'; }
            return exchange(entry, text);
        });
    }

    // ---- the Brief tab's clicks: everything is read from the tab's own markup, so a restored chain behaves the same
    function stateOf(root) {
        let framing = {};
        try { framing = JSON.parse(root.getAttribute('data-framing') || '{}'); } catch (e) { framing = {}; }
        return { framing, chain: root.getAttribute('data-chain'), thread: root.getAttribute('data-thread'), state: root.getAttribute('data-state'),
                 shown: Number(root.getAttribute('data-shown')) || steps.on(framing), adds: root.getAttribute('data-adds') === '1', drawing: root.getAttribute('data-drawing') === '1',
                 against: root.getAttribute('data-against') || '' };
    }
    function entryOf(root) {
        const chain = root.getAttribute('data-chain');
        return responses.find(r => r && r.status === 'framing' && String(r.chain_id) === String(chain)) || null;
    }
    function briefRoot() { const host = byId('content-brief'); return host ? host.querySelector('.ar-brief') : null; }
    function redraw(root, shown, more) {
        const st = stateOf(root), host = root.parentNode;
        host.innerHTML = build.brief(st.framing, Object.assign({ chain: st.chain, thread: st.thread, state: st.state, shown: shown || st.shown, drawing: st.drawing, against: st.against }, more || {}));
        mount(host.querySelector('.ar-brief'));
        mapFollows();
    }
    // What a run's report says against its brief, on that run's Brief tab (0312). `root` holds the run's tabs: the page's,
    // or the holder of a run that goes on while another chain is on screen. The rows are kept in the brief's own markup,
    // as its versions are, so the arrows and a chain shown again have them with nothing else kept; the card stands at
    // the foot of a step whose brief is the one the run was under. The tab is changed where it stands - its drafts are
    // not drawn again.
    // An answer that says nothing against a brief leaves the tab as it is: a chain shown again has its card already
    function turnedOut(root, against) {
        const brief = against && root ? root.querySelector('#content-brief .ar-brief') : null;
        if (!brief) return;
        brief.setAttribute('data-against', against);
        const st = stateOf(brief), old = brief.querySelector('.ar-against');
        if (old) old.remove();
        if (steps.used(st.framing, st.shown)) brief.insertAdjacentHTML('beforeend', build.turnedOut(against));
    }
    // a click on another line while one is being typed: the typed line is kept first, then the click is carried out on the
    // brief as it then stands - the clicked line one place up when a line above it was left out
    function keepThen(root, path, act) {
        keep(root).then(out => {
            const again = out ? briefRoot() : null, parts = path.split('.');
            if (again) act(again, out.removed != null && out.part === parts[0] && Number(parts[1]) > out.removed ? parts[0] + '.' + (Number(parts[1]) - 1) : path);
        });
    }
    function edit(root, line) {
        const path = line.getAttribute('data-path'), openLine = root.querySelector('.ar-line.editing');
        if (openLine === line) return;
        if (openLine) {
            keepThen(root, path, (again, at) => { const target = again.querySelector('.ar-line[data-path="' + at + '"]'); if (target) edit(again, target); });
            return;
        }
        const st = stateOf(root);
        line.classList.add('editing');
        line.innerHTML = build.editor(valueAt(steps.brief(st.framing, st.shown), path), path === 'question');
        const input = line.querySelector('.ar-input');
        if (input) { input.focus(); grow(input); if (input.setSelectionRange) input.setSelectionRange(input.value.length, input.value.length); }
    }
    // a part the coach adds by hand: it takes its place in the brief, open for typing; given up, it is gone again
    function add(root, path) {
        redraw(root, null, { adding: path });
        const again = briefRoot(), line = again ? again.querySelector('.ar-line[data-path="' + path + '"]') : null;
        if (line) edit(again, line);
    }
    // a click that draws the tab again while a line is being typed: the line is kept first
    function settled(root, act) {
        if (!root.querySelector('.ar-line.editing')) { act(root); return; }
        keep(root).then(out => { const again = out ? briefRoot() : null; if (again) act(again); });
    }
    function grow(input) { if (input.style && input.scrollHeight) { input.style.height = 'auto'; input.style.height = input.scrollHeight + 'px'; } }
    // the line being typed is kept: resolves to what changed ({part, removed}), or false when the server did not keep it
    function keep(root) {
        const line = root.querySelector('.ar-line.editing');
        if (!line) return Promise.resolve({});
        const input = line.querySelector('.ar-input');
        return change(root, line.getAttribute('data-path'), input.value != null ? input.value : input.textContent);
    }
    // one change kept as a version - made to the brief of the step on screen, and a step that follows it: a line's
    // text (apply), a proposal ticked (tick), a saved analysis built on no longer (unbuild), a figure taken out (unfigure)
    function change(root, path, text, how) {
        const entry = entryOf(root), step = entry ? steps.on(entry.framing) : 0;
        const out = entry ? (how || apply)(steps.brief(entry.framing, step), path, text) : null;      // of the step in use: the one on screen
        if (!out) { redraw(root); return Promise.resolve({}); }                // nothing changed: the line as it was
        busy = true;
        return post('/architect/brief', { thread_id: entry.thread_id, chain_id: entry.chain_id, brief: out.brief, changed: out.changed, step }).then(res => {
            if (!res.ok || !res.json.framing) { say(res.json.error || WORDS.notKept + '.'); return false; }      // the line stays open, with what was typed
            take(entry, res.json.framing);
            if (responses[currentResponseIndex] === entry) refresh(entry);
            return { part: path.split('.')[0], removed: out.removed };
        }).catch(() => { say(WORDS.notKept + ': ' + WORDS.unreachable + '.'); return false; }).then(result => { busy = false; return result; });
    }
    // a cross or a box clicked: the line being typed elsewhere is kept first
    function keptFirst(root, path, text, how) {
        if (root.querySelector('.ar-line.editing')) keepThen(root, path, (again, at) => change(again, at, text, how));
        else change(root, path, text, how);
    }
    // Before a brief's analysis starts (0313, §2.22): the question of the step in use is read as the Analyst will
    // read it - once: a version of the brief the framing lists as read starts at once. While it is read the pane
    // says so and the composer is held. Resolves to whether the analysis can start. Where the reader could not place
    // something, the Architect has gone on: the conversation and the brief are the record's - the read, its reply,
    // the question as it worded it, the figures as grey windows while a draft follows - or the page says why it
    // made no reply; the coach starts again when they have seen it. A read that could not be had holds nothing up:
    // the start goes on, and says what it meets
    function ready(entry) {
        if (busy) return Promise.resolve(false);
        if (((entry.framing || {}).read || []).indexOf(inUse(entry.framing)) >= 0) return Promise.resolve(true);
        busy = true;
        const mine = talking = { entry, checking: true };
        const draw = () => { if (responses[currentResponseIndex] === entry) { refresh(entry); onChain(entry); } };
        draw();
        return window.authService.fetch('/architect/ready', { method: 'POST', headers: { 'Content-Type': 'application/json' },
                                                               body: JSON.stringify({ thread_id: entry.thread_id, chain_id: entry.chain_id, step: steps.on(entry.framing) }) })
            .then(r => readStream(r, along(entry, mine, draw))).then(body => {      // the Architect's reply after the read, as after a message
                const out = closing(body);
                if (!out.framing) return true;
                take(entry, out.framing);
                if (out.error) say(out.error);
                return out.clean !== false;
            }).catch(() => true).then(clean => {
                busy = false; talking = null;
                const turns = turnsOf(entry.framing);
                if (!clean && turns.length && ['check', 'memory', 'opened'].indexOf(turns[turns.length - 1].who) >= 0) exchange(entry, '');      // the Architect went on to look something up: it goes on
                else draw();
                return clean;
            });
    }
    function start(root) {
        const entry = entryOf(root);
        const free = () => { const running = typeof queryRunning !== 'undefined' && queryRunning; if (running) say(WORDS.busyRun); return !running; };
        if (!entry || !free()) return;
        keep(root).then(out => {
            if (!out) return;
            // the read takes a moment: the analysis starts where the brief is still on screen, and nothing else began meanwhile. It starts from the
            // step in use then - the one on screen, or the read, which is a step of its own - under the brief that stands there
            ready(entry).then(clean => { if (clean && responses[currentResponseIndex] === entry && free()) handleQuerySubmit({ framed: entry, step: steps.on(entry.framing) }); });
        });
    }
    // the analysis of a brief begins (handleQuerySubmit, after the panes are cleared): the framing folds to one row above
    // the run, the Brief tab stays, read-only
    function started(entry) {
        if (typeof paneAppend === 'function') paneAppend(build.fold(entry));
        if (typeof createOrUpdateTab === 'function') createOrUpdateTab('brief', build.brief(entry.framing, { chain: entry.chain_id, thread: entry.thread_id, state: 'run' }));
        mountAll();
    }
    // the server did not start it (the balance, the network): the chain is a brief again, as it stood
    function notStarted(entry, why) {
        if (typeof revertLiveChain === 'function') revertLiveChain(entry);
        if (responses[currentResponseIndex] === entry) show(entry);
        if (typeof updateNavigationButtons === 'function') updateNavigationButtons();
        if (why) say(WORDS.notStarted + ': ' + why);
    }

    // Another step on screen (the arrows, the map). In a brief not yet run it is the one in use from then, here as it
    // will be on the server: the pane shows the conversation up to it, the tab the brief as it stood there. Not while
    // the Architect replies to this brief: what is on its way goes on from the step it left. A brief that ran is
    // read: its tab shows the brief of that step, and nothing else changes
    function stepTo(root, k) {
        const entry = entryOf(root);
        if (!entry) { redraw(root, k); return; }
        if (talking && talking.entry === entry) return;
        take(entry, go(entry.framing, k));
        if (responses[currentResponseIndex] === entry) { refresh(entry); onChain(entry); }
    }
    // what a step is, for its box on the map and for the drawer's foot: what the coach said in it - for the first, the
    // question as it was asked - or, where they said nothing, what was done: a line changed by hand, the question
    // read, the Architect gone on; what the Architect last replied; and the parts of the brief the step changed, in
    // the tab's words
    function stepWords(framing, s, turns) {
        const said = (turns.find(t => t.who === 'person') || {}).text, reply = (turns.filter(t => t.who === 'architect').pop() || {}).text || '';
        const parts = steps.changed(framing, s.k).map(p => WORDS.part[p] || WORDS.part[String(p).split('.')[0]] || '').filter((w, i, all) => w && all.indexOf(w) === i);
        const label = !s.from ? (versionAt(framing, 1).brief || {}).question || '' : said || (!turns.length ? WORDS.byHand : turns[0].who === 'reader' ? WORDS.checked : WORDS.wentOn);
        return { label, reply, parts };
    }
    // The Brief map - the map of a brief's conversation (§2.25): every step a box, in the Workflow map's own drawer and
    // with its drawing (workflowGraph.js) - the way to the step on screen lit, the steps off it faint; a box says what
    // the coach said and, under it, what the step changed. Under the pointer a box lights its own way, and the drawer's
    // foot says, as the Workflow map's does of a chain: what was said, where the step stands - as the arrows would
    // count it -, what it follows, how many follow it, what it changed and what the Architect replied. A click goes to
    // the step and shuts the drawer
    function openMap(root) {
        const st = stateOf(root), framing = st.framing, all = steps.of(framing), held = steps.held(framing), drawer = byId('workflowMapModal');
        if (!drawer || !window.WorkflowGraph) return;
        const words = all.map(s => stepWords(framing, s, held[s.k]));
        const forks = all.filter(s => all.filter(x => x.from === s.k).length > 1).length;
        const row = (name, value) => '<div class="wf-info-row"><span>' + name + '</span><b>' + value + '</b></div>';
        drawer.classList.remove('turns');                      // the drawer may last have held the map of an analysis's turns (branch.js)
        drawer.classList.add('steps');                         // the thread's own buttons are not this map's
        drawer.setAttribute('data-chain', st.chain);
        window.WorkflowGraph.head(WORDS.map, WORDS.mapSub(all.length, forks), WORDS.mapRest);
        drawer.style.display = 'flex';
        window.WorkflowGraph.render(byId('workflowMapContainer'), all.map((s, i) => ({ chain_id: s.k, parentChainId: s.from || null, queryText: words[i].label })), st.shown - 1, {
            sub: (item, i) => (all[i].from ? [] : [WORDS.asked1]).concat(words[i].parts).join(' · '),
            show: (item, i) => {
                const s = all[i], at = steps.place(framing, s.k), next = all.filter(x => x.from === s.k).length, first = /^[\s\S]{20,240}?[.!?](?=\s|$)/.exec(words[i].reply);
                byId('nodeTaskContent').textContent = words[i].label.length > 300 ? words[i].label.slice(0, 297) + '...' : words[i].label;
                byId('nodePlotPreview').innerHTML = '<div class="wf-info">' +
                    row(WORDS.info.step, WORDS.of(at.i, at.n) + (s.k === st.shown ? ' · ' + WORDS.onScreen : '')) +
                    row(WORDS.info.follows, s.from ? WORDS.stepN(at.i - 1) : WORDS.theStart) + row(WORDS.info.next, next || WORDS.none) +
                    row(WORDS.info.changed, esc(words[i].parts.join(' · ') || WORDS.nothing)) +
                    (words[i].reply ? '<div class="wf-info-row wf-info-conclusion"><span>' + WORDS.info.replied + '</span><b>' + esc(first ? first[0] : words[i].reply.slice(0, 240)) + '</b></div>' : '') + '</div>';
            },
            // a box clicked: the drawer shuts, and the map's brief - the one on screen while the drawer is open (mapFollows()) - goes to the step
            pick: (item, i) => { drawer.style.display = 'none'; stepTo(briefRoot(), all[i].k); }
        });
    }
    // The map, while its drawer is open, follows its brief: drawn again whenever the brief is - another step may be on
    // screen, a step may have been added - and shut once another chain is on screen
    function mapFollows() {
        const drawer = byId('workflowMapModal'), root = briefRoot();
        if (!drawer || !drawer.classList.contains('steps') || drawer.style.display !== 'flex') return;
        if (root && root.getAttribute('data-chain') === drawer.getAttribute('data-chain')) openMap(root);
        else drawer.style.display = 'none';
    }

    // a saved analysis a reading found, viewed whole in a dialog over the page: the report, and under it the conversation,
    // the brief and the code
    function openSaved(thread, run) {
        window.authService.fetch('/architect/saved/' + encodeURIComponent(thread) + '/' + encodeURIComponent(run)).then(r => r.json().catch(() => ({})).then(json => ({ ok: r.ok, json: json || {} })))
            .then(res => {
                if (!res.ok) { say(res.json.error || WORDS.notOpenedSaved + '.'); return; }
                let modal = byId('savedAnalysisModal');
                if (!modal) {
                    modal = document.createElement('div'); modal.id = 'savedAnalysisModal'; modal.className = 'ui-modal-plain';
                    document.body.appendChild(modal);
                }
                modal.innerHTML = build.savedDialog(res.json);
                modal.style.display = 'flex';
            }).catch(() => say(WORDS.notOpenedSaved + ': ' + WORDS.unreachable + '.'));
    }

    function onClick(ev) {
        const hit = ev.target && ev.target.closest ? ev.target.closest('[data-ar]') : null;
        if (hit && hit.getAttribute('data-ar') === 'choice') { tell(hit.textContent); return; }      // a choice clicked is the coach's answer
        if (hit && hit.getAttribute('data-ar') === 'skip') { hit.disabled = true; post('/architect/skip', {}).catch(() => { hit.disabled = false; }); return; }
        if (hit && hit.getAttribute('data-ar') === 'open') { openSaved(hit.getAttribute('data-thread'), hit.getAttribute('data-run')); return; }      // View: in the conversation, or on the Brief tab
        if ((hit && hit.getAttribute('data-ar') === 'shut') || (ev.target && ev.target.id === 'savedAnalysisModal')) { byId('savedAnalysisModal').style.display = 'none'; return; }      // its cross, or beside it
        const root = hit ? hit.closest('.ar-brief') : null;
        if (!root) return;
        const act = hit.getAttribute('data-ar');
        if (act === 'step') { settled(root, r => { const at = steps.place(stateOf(r).framing, stateOf(r).shown); stepTo(r, Number(hit.getAttribute('data-step')) < 0 ? at.before : at.after); }); return; }
        if (act === 'map') { settled(root, openMap); return; }
        if (busy) return;
        const line = hit.closest('.ar-line');
        if (act === 'edit') edit(root, line);
        else if (act === 'more') settled(root, r => redraw(r, null, { adds: !stateOf(r).adds }));
        else if (act === 'add') settled(root, r => add(r, hit.getAttribute('data-path')));
        else if (act === 'drop') keptFirst(root, line.getAttribute('data-path'), '');
        else if (act === 'tick') keptFirst(root, line.getAttribute('data-path'), null, tick);
        else if (act === 'unbuild') keptFirst(root, hit.getAttribute('data-id'), null, unbuild);
        else if (act === 'unfigure') keptFirst(root, hit.getAttribute('data-path'), null, unfigure);
        else if (act === 'keep') keep(root);
        else if (act === 'cancel') redraw(root);
        else if (act === 'start') start(root);
    }
    function onKey(ev) {
        const at = ev.target && ev.target.closest ? ev.target : null;
        const root = at ? at.closest('.ar-brief') : null;
        if (!root || ev.isComposing || !at.closest('.ar-input')) return;
        if (ev.key === 'Enter' && !ev.shiftKey) { ev.preventDefault(); if (!busy) keep(root); }      // Shift+Enter is a new line (the question may have several)
        else if (ev.key === 'Escape') { ev.preventDefault(); redraw(root); }
    }

    function initialize() {
        const sw = byId('architectSwitch');
        if (sw) sw.addEventListener('click', () => setOn(!on));
        let stored = null;
        try { stored = sessionStorage.getItem('architectOn'); } catch (e) { /* no storage */ }
        setOn(stored === '1');
        document.addEventListener('click', onClick);
        document.addEventListener('keydown', onKey);
        document.addEventListener('input', ev => { const input = ev.target && ev.target.closest ? ev.target.closest('.ar-input') : null; if (input) grow(input); });
    }

    window.ArchitectUI = { initialize, isOn, open, tell, restore, onChain, framingInView, started, notStarted, cutAnswer, turnedOut, mark, apply, tick, unbuild, unfigure, go, steps, build, readStream, draftLayout };
})();
