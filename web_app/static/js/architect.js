// architect.js - the Architect on the page (docs/ARCHITECT_DESIGN.md §2.6, §2.8, §2.9, §2.11-§2.14, §2.18; 2026-11-17).
// A question typed with the switch on is framed before it is analysed: the server opens a framing run on the thread's
// record (POST /architect/open) and the page shows it as a chain of its own, the conversation in the left pane and
// its brief on a Brief tab. The Architect fills the brief from the question and asks for what is missing, one
// exchange a call (POST /architect/say, a stream); while such a chain is on screen the composer is the conversation's
// input. Where a reply had the data looked up, the round is a row of the conversation and the Architect goes on at
// once, with the marks. The coach also changes the brief where it stands, and ticks what the Architect proposed;
// every change kept is one more version, stored by the server (POST /architect/brief). Start analysis continues the
// same chain (/query with run_id), so the question is one box on the thread map.
//
// One rule holds the Brief tab together: what it shows is what the Analyst gets. The question is its top box, and
// the Architect words it as the conversation goes: each wording is one more version, and a row of the conversation
// says so. Under it stand the parts that hold something, and no other; + Add lists the ones a coach can add by hand.
// The arrows step through the versions, and the one on screen is the one in use: an answer, a change and Start
// analysis all go on from it (the version rides with the request; analyst/brief.py use()).
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
// without a draft is a grey sketch of where things go. Under an analysis the brief builds on stands what that
// analysis drew (GET /get_chain_preview/<thread>/<chain>).
//
// A brief not yet run is drawn from its versions (the chain's `framing`), never from kept markup. Once it runs, the
// Brief tab's markup carries the versions (data-framing), so a restored chain or a saved favourite steps through them
// with nothing else kept.
//
// The report of a run with a brief has a part "Against the brief" (analyst/session.py): dressAnswer() makes it a card
// of verdicts. The page's words sit in WORDS; nothing here reaches a prompt.
//
// window.ArchitectUI = { initialize, isOn, open, tell, restore, onChain, framingInView, started, notStarted,
//                        dressAnswer, mark, apply, tick, unbuild, unfigure, use, build, readStream, draftLayout }

(function () {
    'use strict';

    const WORDS = {
        answer: 'Answer, or say what to change', replying: 'The Architect is replying', reading: 'reading…', readingSaved: 'Your saved analyses are being read',
        asked: 'What the Analyst will be asked', gets: 'This is what the Analyst gets. Change any line before you start.',
        head: { decision: 'What it is for', thinks: 'What you think', rests_on: 'Why you think so', expects: 'What you expect to see', would_change: 'What would change your mind',
                also_check: 'Other explanations to test', figures: 'What it will look like', builds: 'Builds on', aside: 'Set aside' },
        add: '+ Add', another: 'Another explanation to test', tick: 'Have the analysis test it',
        always: 'Always tested on data: chance, measurement error, how the cases were chosen.',
        version: 'Version', of: (k, n) => k + ' of ' + n, before: 'The version before', after: 'The version after',
        start: 'Start analysis', startWith: k => 'Start analysis with version ' + k,
        notKept: 'The change was not kept', notOpened: 'The brief could not be opened', unreachable: 'the server could not be reached',
        noReply: 'The Architect did not reply', check: 'CHECK data', lookedUp: n => n + (n === 1 ? ' thing' : ' things') + ' looked up', notLookedUp: n => n + ' not',
        busyRun: 'Another analysis is running. Wait for it to end, or stop it.',
        saved: 'SAVED analyses', found: n => n + (n === 1 ? ' analysis' : ' analyses') + ' found', noneFound: 'nothing found', readOf: (r, m) => r ? 'read ' + r + ' of ' + m : m + ' saved',
        looking: (r, m) => r ? 'reading ' + r + ' of ' + m : (m == null ? 'looking' : 'looking through ' + m), skip: 'Skip', skipped: 'skipped', notRead: 'not read',
        view: 'View', leave: 'Leave it out', builtOn: 'built on',
        memory: 'Found in your saved analyses', memoryNote: 'For you to read. The Analyst gets only what you build on.',
        notOpenedSaved: 'This analysis could not be opened', code: 'Code', agreed: 'Brief', talk: 'Conversation',
        opened: 'READ', chars: n => (Number(n) || 0).toLocaleString('en-US') + ' characters',
        question: 'QUESTION', updated: 'updated', versionN: k => 'version ' + k, brief: 'BRIEF', inUse: k => 'version ' + k + ' in use',
        figures: 'FIGURES', sketch: 'sketch', draft: 'draft', madeUp: 'made-up numbers', madeUpNote: 'The numbers are made up. The analysis puts in the real ones.',
        drawing: 'Drawing a draft…', noDraft: 'No draft could be drawn.', drawingRow: 'drawing a draft…', drawingHold: 'A draft of the figures is being drawn',
        drawn: n => n + ' drawn', notDrawn: n => n + ' not', noneDrawn: 'no draft', draftPrompt: 'the prompt the draft was written from (run log)', drewThen: 'What it drew then',
        notStarted: 'The analysis did not start',
        against: { head: 'Against the brief', expected: 'You expected', would: 'Would change your mind', checks: 'Also checked' }
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
        x: '<svg viewBox="0 0 24 24"><path d="M19 6.41L17.59 5 12 10.59 6.41 5 5 6.41 10.59 12 5 17.59 6.41 19 12 13.41 17.59 19 19 17.59 13.41 12z"/></svg>'
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
    // the version in use: the one the coach went back to (`at`, analyst/brief.py use()), else the last
    function inUse(framing) { const n = latestN(framing), at = framing && framing.at; return Number.isInteger(at) && at >= 1 && at <= n ? at : n; }
    // the framing with version k in use, as the server will have it once the request that carries k is taken (pure)
    function use(framing, k) {
        const out = Object.assign({}, framing || {});
        delete out.at;
        if (Number.isInteger(k) && k >= 1 && k < latestN(framing)) out.at = k;
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

    // ------------------------------------------------------------ a figure sketched (pure: returns markup)
    // A figure as the Architect described it - its kind, what is on each axis, what it holds - as a grey sketch of
    // where things go (docs/ARCHITECT_DESIGN.md §2.19). It stands in a figure's place while its draft is drawn and
    // where there is none (§2.20). A sketch shows no shape and no result: a shape is the draft's cell to compute.
    const PLOT = { x0: 52, x1: 300, y0: 150, y1: 22 };      // where the marks land, in a drawing of 320 by 190
    const CUBE = { x0: 70, x1: 276, y0: 150, y1: 30 };      // ... and inside the frame of a figure in three dimensions
    const NAMED = ['bar', 'box'];                            // the kinds whose series are named at their marks, not in a key
    const CLOUD = [[0.08, 0.3], [0.2, 0.62], [0.31, 0.42], [0.43, 0.74], [0.52, 0.22], [0.63, 0.55], [0.74, 0.36], [0.85, 0.68], [0.93, 0.18]];
    const r1 = v => Math.round(v * 10) / 10;
    const count = n => Array.from({ length: n }, (_, i) => i);
    const rect = (cls, x, y, w, h) => '<rect class="' + cls + '" x="' + r1(x) + '" y="' + r1(y) + '" width="' + r1(w) + '" height="' + r1(h) + '"/>';
    // a path through points, rounded off (Catmull-Rom, written as Bézier curves)
    function curve(pts) {
        let d = 'M' + pts[0].map(r1).join(',');
        for (let i = 0; i < pts.length - 1; i++) {
            const a = pts[i - 1] || pts[i], b = pts[i], c = pts[i + 1], e = pts[i + 2] || c;
            d += 'C' + [b[0] + (c[0] - a[0]) / 6, b[1] + (c[1] - a[1]) / 6, c[0] - (e[0] - b[0]) / 6, c[1] - (e[1] - b[1]) / 6, c[0], c[1]].map(r1).join(',');
        }
        return d;
    }
    // a name in a drawing: cut where it would run past its place, whole under the mouse; beside an upright axis it is
    // turned along it, unless it is a letter or two. o: {cls, start: it begins at x, turn}
    function label(text, max, x, y, o) {
        const t = String(text || ''), cut = t.length > max ? t.slice(0, max - 1) + '…' : t;
        o = o || {};
        return !t ? '' : '<text' + (o.cls ? ' class="' + o.cls + '"' : '') + ' x="' + x + '" y="' + y + '"' + (o.start ? '' : ' text-anchor="middle"') +
            (o.turn && t.length > 3 ? ' transform="rotate(-90 ' + x + ' ' + y + ')"' : '') + '>' + esc(cut) + (cut === t ? '' : '<title>' + esc(t) + '</title>') + '</text>';
    }
    // what stands inside a sketch, by the figure's kind. held: its series - where it names none, as many unnamed ones
    // as show the kind; box: where the marks land
    const each = (held, spare) => (held.length ? held : count(spare).map(() => ({})));
    const apart = (n, k) => 40 + 268 * (k + 1) / (n + 1);      // the middle of mark k of n, side by side
    const MARKS = {
        line(held, box) {
            const mid = (box.y0 + box.y1) / 2;
            return each(held, 1).map((s, k) => '<path class="ph" d="' + curve(count(21).map(i => [box.x0 + (box.x1 - box.x0) * i / 20, mid - 22 * Math.sin(i * 0.42 + k * 2.4)])) + '"/>').join('');
        },
        scatter(held, box) {
            const dot = q => '<circle class="dot" cx="' + r1(q[0]) + '" cy="' + r1(q[1]) + '" r="3"/>';
            return each(held, 1).map((s, k) => CLOUD.map(f => dot([box.x0 + (box.x1 - box.x0) * f[0], box.y0 + (box.y1 - box.y0) * (0.1 + 0.8 * ((f[1] + k * 0.37) % 1))])).join('')).join('');
        },
        bar(held) {
            const bars = each(held, 3), w = Math.min(44, 166 / (bars.length + 1));
            return bars.map((s, k) => rect('ph', apart(bars.length, k) - w / 2, 70, w, 90) + label(s.name, Math.floor(268 / (bars.length + 1) / 6), r1(apart(bars.length, k)), 62, { cls: 'tk' })).join('');
        },
        histogram() {
            const w = (PLOT.x1 - PLOT.x0) / 7;
            return [0.25, 0.5, 0.8, 1, 0.8, 0.5, 0.25].map((h, i) => rect('ph', PLOT.x0 + w * i, 160 - 110 * h, w, 110 * h)).join('');
        },
        box(held) {
            const boxes = each(held, 2);
            return boxes.map((s, k) => { const cx = r1(apart(boxes.length, k));
                return '<path class="ph" d="M' + (cx - 22) + ',62H' + (cx + 22) + 'V110H' + (cx - 22) + 'ZM' + (cx - 22) + ',86H' + (cx + 22) + 'M' + cx + ',62V38M' + (cx - 10) + ',38H' + (cx + 10) +
                    'M' + cx + ',110V134M' + (cx - 10) + ',134H' + (cx + 10) + '"/>' + label(s.name, Math.floor(268 / (boxes.length + 1) / 6), cx, 154, { cls: 'tk' }); }).join('');
        },
        heatmap() {
            const w = (PLOT.x1 - PLOT.x0) / 6, h = (PLOT.y0 - PLOT.y1) / 4;
            return count(24).map(i => rect('cell c' + (i % 6 + 2 * Math.floor(i / 6)) % 3, PLOT.x0 + w * (i % 6), PLOT.y1 + h * Math.floor(i / 6), w - 2, h - 2)).join('');
        }
    };
    MARKS.line3d = MARKS.line;
    // the drawing: the axes under their names - the frame of a box for three dimensions - and the marks of the figure's
    // kind; a figure of no kind the page knows is its axes alone
    function drawing(fig) {
        const deep = fig.kind === 'line3d', held = fig.series || [];
        const frame = deep
            ? '<path class="bk" d="M118,16H298V124H118ZM46,58L118,16M226,58L298,16M226,166L298,124M46,166L118,124M226,58V166M46,58H226"/><path class="ax" d="M46,58V166H226"/>' +
              label(fig.x, 30, 136, 181) + label(fig.y, 20, 96, 158, { start: true }) + label(fig.z, 18, 34, 112, { turn: true })
            : '<path class="ax" d="M40,12V160H308"/>' + label(fig.x, 44, 174, 179) + label(fig.y, 26, 18, 86, { turn: true });
        return '<svg viewBox="0 0 320 190" role="img" aria-label="' + esc(WORDS.sketch + ': ' + (fig.title || '')) + '">' + frame +
            (MARKS[fig.kind] ? MARKS[fig.kind](held, deep ? CUBE : PLOT) : '') + '</svg>';
    }

    // ------------------------------------------------------------ the report's part "Against the brief", as a card (pure)
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
    function against(lines) {
        // three cells to a row, the verdict's empty when the line gives none: the card is one grid (tabs.css)
        const row = (k, html, v) => '<div class="r"><span class="k">' + k + '</span> <span class="t">' + html + '</span> <span class="v' + (v ? ' ' + VERDICT[v] : '') + '">' + (v || '') + '</span></div>';
        let checks = 0;
        const rows = lines.map(html => {
            const e = verdictLine(html, 'expected|expectation', ['not met', 'cannot tell', 'met']);        // "not met" before "met", as the engine reads it
            if (e) return row(WORDS.against.expected, e.html, e.verdict);
            const w = verdictLine(html, '(?:what )?would change (?:their|your) mind', ['not seen', 'cannot tell', 'seen']);
            if (w) return row(WORDS.against.would, w.html, w.verdict);
            return row(checks++ ? '' : WORDS.against.checks, html, /\bcannot tell\b/i.test(plain(html)) ? 'cannot tell' : '');
        });
        return '<div class="ar-against"><div class="label">' + WORDS.against.head + '</div>' + rows.join('') + '</div>';
    }
    // Idempotent: the card holds no heading, so a second pass (a restored chain is rendered again) finds nothing to do.
    function dressAnswer(html) {
        const s = String(html == null ? '' : html);
        const head = /<h([1-6])\b[^>]*>\s*Against the brief\s*:?\s*<\/h\1>/i.exec(s);
        if (!head) return s;
        const after = s.slice(head.index + head[0].length);
        const end = after.search(/<h[1-6]\b|<blockquote\b|<hr\b/i);              // the next part, or the engine's lines at the report's foot
        const lines = sectionLines(end < 0 ? after : after.slice(0, end));
        return lines.length ? s.slice(0, head.index) + against(lines) + (end < 0 ? '' : after.slice(end)) : s;
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
        // which version is on screen, of how many, and the arrows to the one before and the one after
        version(framing, shown) {
            const n = latestN(framing);
            const arrow = (d, glyph, title, off) => '<button type="button" data-ar="step" data-step="' + d + '" title="' + title + '" aria-label="' + title + '"' + (off ? ' disabled' : '') + '>' + glyph + '</button>';
            return '<div class="ar-ver"><span class="k">' + WORDS.version + '</span>' + arrow(-1, '‹', WORDS.before, shown <= 1) + '<b>' + WORDS.of(shown, n) + '</b>' + arrow(1, '›', WORDS.after, shown >= n) + '</div>';
        },
        // the button that shows a saved analysis whole, in a dialog over the page
        view(thread, run) {
            return thread && run ? '<button type="button" class="ar-open" data-ar="open" data-thread="' + esc(thread) + '" data-run="' + esc(run) + '">' + WORDS.view + '</button>' : '';
        },
        // a saved analysis the brief builds on: its day and what was asked then; View, and a cross to build on it no
        // longer; under it the place for what that analysis drew, which the page fills where it kept a picture (mount())
        built(c, g) {
            return '<div class="ar-line ar-built' + (g.paths.some(p => c.changed.indexOf(p) >= 0) ? ' changed' : '') + '"><span class="tx">' + esc(day(g.when) + ' · ' + g.question) + '</span>' +
                build.view(g.thread, g.run) + (c.edit ? '<button type="button" class="drop" data-ar="unbuild" data-id="' + esc(g.id) + '" title="' + WORDS.leave + '">' + ICON.x + '</button>' : '') + '</div>' +
                '<div class="ar-was" data-thread="' + esc(g.thread) + '" data-run="' + esc(g.run) + '"></div>';
        },
        // a figure of the brief (i: its place): its number and title, and a cross to take it out while the brief can
        // be changed. Where its draft was drawn (c.drafts, by the figure's key): the word that it is a draft - on
        // made-up numbers, where they are - and the place the page draws its plot in (mount()). Otherwise it is a
        // sketch: the series it holds, each beside a stroke - and what a heat map's colour shows - and the drawing,
        // with a line where a draft is on its way (c.drawing) or could not be drawn. Under either, what the figure
        // is to make clear. The sketch is in the markup of a drawn figure too: it is what shows if the plot cannot be had
        figure(c, fig, i) {
            const key = (c.keys || [])[i], d = (key && (c.drafts || {})[key]) || {}, drawn = !!d.basis, madeUp = drawn && d.basis !== 'computed';
            const names = (NAMED.indexOf(fig.kind) < 0 ? fig.series || [] : []).map(s => '<span><i class="ph"></i>' + esc(s.name) + '</span>')
                .concat(fig.kind === 'heatmap' && fig.z ? ['<span><i class="sq"></i>' + esc(fig.z) + '</span>'] : []);      // what a heat map's colour shows
            const left = d.failed && !(c.drawing && (Number(d.tries) || 1) < TRIES);      // no draft, and none on its way
            const state = madeUp ? '<span class="mu">' + WORDS.madeUpNote + '</span>' : drawn ? '' : left ? '<span class="ph" title="' + esc(d.failed) + '">' + WORDS.noDraft + '</span>'
                : c.drawing ? '<span class="ph">' + WORDS.drawing + '</span>' : '';
            const cap = [esc(fig.note || ''), state].filter(Boolean).join(' ');
            return '<div class="ar-fig' + (drawn ? ' drawn' : '') + (c.changed.indexOf('figures.' + i) >= 0 ? ' changed' : '') + '"><div class="hd"><span class="n">' + (i + 1) + '</span><span class="t">' + esc(fig.title) + '</span>' +
                '<span class="tag' + (madeUp ? ' mu' : '') + '">' + (drawn ? WORDS.draft + (madeUp ? ' · ' + WORDS.madeUp : '') : WORDS.sketch) + '</span>' +
                (c.edit ? '<button type="button" class="drop" data-ar="unfigure" data-path="figures.' + i + '" title="' + WORDS.leave + '">' + ICON.x + '</button>' : '') + '</div>' +
                (drawn ? '<div class="plot" data-key="' + esc(key) + '"' + (madeUp ? ' data-made-up="1"' : '') + '></div>' : '') +
                (names.length ? '<div class="key">' + names.join('') + '</div>' : '') +
                drawing(fig) + (cap ? '<div class="cap">' + cap + '</div>' : '') + '</div>';
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
        // the Brief tab: on top what the Analyst will be asked, with the version on screen; under it the parts the
        // Analyst gets with it - those that hold something, and the one the coach is adding (o.adding: its path) - and,
        // while the brief can be changed, the one control that adds a part (o.adds: its list is open), what the
        // readings of the saved analyses found, and Start analysis, which names the version when it is not the last.
        // o: {chain, thread, state: 'framing' | 'run', shown, drawing: a draft of the figures is on its way}; the
        // versions ride in the markup, with the thread the drafts' plots are kept under
        brief(framing, o) {
            const n = latestN(framing), shown = Math.min(n, Math.max(1, o.shown || inUse(framing))), v = versionAt(framing, shown), b = v.brief || {};
            const c = { edit: o.state === 'framing', changed: v.changed || [], keys: v.keys || [], drafts: (framing && framing.drafts) || {}, drawing: !!o.drawing };
            const adding = c.edit ? (o.adding || '') : '';
            const part = (name, body) => body ? '<h3>' + name + '</h3>' + body : '';
            const one = path => valueAt(b, path) || adding === path ? build.line(c, path, valueAt(b, path)) : '';
            const built = builtOn(b), found = c.edit ? foundIn(turnsOf(framing)) : [];
            const kinds = c.edit ? KINDS.filter(k => k[0].slice(-2) === '.+' ? (b[k[0].slice(0, -2)] || []).length < CAP[k[0].slice(0, -2)] : !valueAt(b, k[0])) : [];
            const aside = (b.set_aside || []).map(x => '<div class="ar-line"><span class="tx">' + esc(x) + '</span></div>').join('');
            return '<div class="ar-brief" data-chain="' + esc(o.chain) + '" data-thread="' + esc(o.thread) + '" data-state="' + esc(o.state) + '" data-shown="' + shown + '"' +
                    (o.adds ? ' data-adds="1"' : '') + (o.drawing ? ' data-drawing="1"' : '') +
                    ' data-framing="' + esc(JSON.stringify(framing || {})) + '">' +
                '<div class="ar-top"><span class="label">' + WORDS.asked + '</span>' + build.version(framing, shown) + '</div>' +
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
                (c.edit ? '<div class="ar-foot"><button type="button" class="ui-btn primary" data-ar="start">' + (shown === n ? WORDS.start : WORDS.startWith(shown)) + '</button></div>' : '') +
                '</div>';
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
        // the question changed with the reply above it: the Architect worded it, and it is the top box of that version
        asked(turn) {
            return '<div class="sp-row tool read"><span>✓</span><span class="in">' + WORDS.question + '</span><span class="out">' + WORDS.updated + '</span><span class="t">' + WORDS.versionN(esc(turn.v)) + '</span></div>';
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
        // a draft on its way: the reply stands above it, and the Brief tab shows the sketches meanwhile
        drawingRow() {
            return '<div class="sp-row tool read pending"><span class="live"></span><span class="in">' + WORDS.figures + '</span><span class="out">' + WORDS.drawingRow + '</span></div>';
        },
        // the coach went to another version of the brief before the message under it: the conversation goes on from that one
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
        // a reading in flight: how far it is, and Skip - once the server has said how many are saved: it has started
        // then, and a skip sent before would be lost. at: {read, of}
        reading(at) {
            return '<div class="sp-row tool read pending"><span class="live"></span><span class="in">' + WORDS.saved + '</span><span class="out">' + WORDS.looking(at.read, at.of) + '</span>' +
                '<button type="button" class="ar-skip" data-ar="skip"' + (at.of == null ? ' disabled' : '') + '>' + WORDS.skip + '</button></div>';
        },
        // the conversation: the question, then what was said, what was looked up, what the saved analyses hold, what
        // was opened, where the question changed, what a draft of the figures came to and where the coach went to
        // another version. o: {live: the last message's choices can be clicked - a draft's row may stand under it -,
        // sent: a message on its way, waiting: the Architect is replying, saved: the saved analyses are being read -
        // how far -, drawing: its reply stands and the draft is on its way}
        talk(entry, o) {
            o = o || {};
            const turns = turnsOf(entry.framing), versions = versionsOf(entry.framing), can = o.live && !o.waiting;
            // a reply worded the question when the version it left is the Architect's, changed the question, and reads as the reply has it
            const worded = t => { const v = versions[(t.v || 0) - 1]; return !!(t.wording && v && v.by === 'architect' && (v.changed || []).indexOf('question') >= 0 && (v.brief || {}).question === t.wording); };
            return build.you((versionAt(entry.framing, 1).brief || {}).question || entry.queryText) +      // as it was first asked: the brief holds it as it stands now
                turns.map((t, i) => t.who === 'check' ? build.checked(t) : t.who === 'memory' ? build.recalled(t) : t.who === 'opened' ? build.opened(t) : t.who === 'version' ? build.went(t)
                    : t.who === 'draft' ? build.drafted(t, entry.chain_id)
                    : t.who === 'architect' ? build.said(t, entry.chain_id, can && turns.slice(i + 1).every(x => x.who === 'draft')) + (worded(t) ? build.asked(t) : '')
                    : build.you(t.text)).join('') +
                (o.sent ? build.you(o.sent) : '') +
                (o.waiting ? (o.saved ? build.reading(o.saved) : o.drawing ? build.drawingRow() : '<div class="ar-msg arch wait"><span class="who">Architect</span>' + WORDS.reading + '</div>') : '');
        },
        // the left pane of a brief not yet run: what the Architect's calls cost, and the conversation. Which version is
        // on screen is the Brief tab's to say, in one place
        pane(entry, o) {
            const cost = turnsOf(entry.framing).reduce((sum, t) => sum + (Number(t.cost) || 0), 0);
            return '<div class="sp-strip"><span class="live idle"></span><span class="mode">Architect</span>' + (cost >= 0.005 ? '<span>$' + cost.toFixed(2) + '</span>' : '') + '</div>' +
                '<div class="sp-stream">' + build.talk(entry, Object.assign({ live: true }, o)) + '</div>';
        },
        // the framing folded to one row, above the run it started - under the version it started with: the conversation is inside
        fold(entry) {
            return '<details class="sp-turn ar-fold"><summary><span class="chev"></span><span class="n">Architect</span><span class="kind">brief v' + inUse(entry.framing) + '</span>' +
                '<span class="peek">' + esc(entry.queryText) + '</span></summary><div class="sp-detail">' + build.talk(entry) + '</div></details>';
        },
        // a saved analysis in a dialog: what was asked, the day, whose data and which, the report; folded under it the
        // conversation its brief came from - the person's messages under "You", as the pane has them - and the brief,
        // where it was framed, and the code of its cells
        savedDialog(run) {
            const data = run.data || {}, sub = [String(run.when || '').slice(0, 10), data.person, data.name, data.period, (run.marks || []).join(', ')].filter(Boolean).join(' · ');
            const report = typeof marked !== 'undefined' && marked.parse ? marked.parse(String(run.report || '')) : '<pre>' + esc(run.report) + '</pre>';
            const code = (run.cells || []).map(c => '<div class="cell-n">cell ' + esc(c.n) + '</div><pre>' + esc(c.code) + '</pre>').join('');
            const fold = (name, body) => body ? '<details class="ar-code"><summary>' + name + '</summary>' + body + '</details>' : '';
            const said = text => text ? '<pre class="said">' + esc(text) + '</pre>' : '';
            return '<div class="ui-dlg lg ar-saved-dlg" role="dialog" aria-modal="true"><div class="ui-dlg-h"><div><div class="title">' + esc(run.question || run.title || '') + '</div>' +
                '<div class="sub">' + esc(sub) + '</div></div><span class="sp"></span><button class="x" type="button" data-ar="shut" aria-label="Close">' + ICON.x + '</button></div>' +
                '<div class="ui-dlg-b"><div class="markdown-content">' + report + '</div>' + fold(WORDS.talk, said(String(run.conversation || '').replace(/^Person: /gm, 'You: '))) + fold(WORDS.agreed, said(run.brief)) + fold(WORDS.code, code) + '</div></div>';
        },
        against
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
        // how a chain's question was made, for its box on the thread map (§2.9)
        if (!r) return '';
        if (r.status === 'framing') return 'not run';
        if (r.framing || /id="tab-brief"/.test(r.tabContent || '')) return 'Architect';
        return window.NextQuestionsUI && window.NextQuestionsUI.made(r) ? 'next question' : '';
    }
    function framingInView() { const r = responses[currentResponseIndex]; return !!(r && r.status === 'framing'); }

    // ---- the drafts on the page (§2.20). The builders leave a place for each plot; once the tab stands, Plotly draws
    // it there. A plot is fetched once, by where it is kept; where it cannot be had - or the page has no Plotly - the
    // figure is its sketch again. What a saved analysis drew is fetched the same way, a picture kept with the favourite.
    const fetchedOnce = new Map();      // by its address: what the server holds - or that it holds none - is kept for the page's life; an answer that failed, and a server not reached, are asked for again
    const ACROSS = { xref: 'paper', yref: 'paper', x: 0.5, y: 0.5, showarrow: false, textangle: -18, opacity: 0.28, font: { size: 30, color: '#8a8a8a' } };
    // the layout a draft is drawn with (pure): the figure's own, fitted to its place and not to be dragged about - and,
    // on made-up numbers, with those words across it
    function draftLayout(layout, madeUp) {
        const own = layout || {};
        return Object.assign({}, own, { autosize: true, width: undefined, height: Math.max(280, Math.min(Number(own.height) || 360, 560)), dragmode: false,
                                        annotations: (own.annotations || []).concat(madeUp ? [Object.assign({ text: WORDS.madeUp }, ACROSS)] : []) });
    }
    function fetched(url, pick) {
        if (!fetchedOnce.has(url)) fetchedOnce.set(url, window.authService.fetch(url).then(r => (r.ok ? r.json() : r.status === 404 ? null : Promise.reject(new Error('HTTP ' + r.status))))
            .then(json => (json && pick(json)) || null).catch(() => { fetchedOnce.delete(url); return null; }));
        return fetchedOnce.get(url);
    }
    // a figure whose plot cannot be drawn is its sketch again: the plot's place goes, with the words that said it was a draft
    function sketchAgain(fig) {
        if (!fig) return;
        const tag = fig.querySelector('.tag');
        fig.classList.remove('drawn');
        if (tag) { tag.textContent = WORDS.sketch; tag.classList.remove('mu'); }
        [fig.querySelector('.plot'), fig.querySelector('.cap .mu')].forEach(el => { if (el) el.remove(); });
    }
    function mount(root) {
        if (!root) return;
        const at = [root.getAttribute('data-thread'), root.getAttribute('data-chain')];
        root.querySelectorAll('.ar-fig.drawn .plot').forEach(el => {
            if (el.arLive) return;
            el.arLive = true;                              // on the element, not in its markup: a tab restored from kept markup is drawn again
            fetched('/architect/draft/' + at.concat(el.getAttribute('data-key')).map(encodeURIComponent).join('/'), json => json.plot).then(plot => {
                el.innerHTML = '';                         // what kept markup held of an earlier drawing
                return Plotly.newPlot(el, plot.data, draftLayout(plot.layout, el.getAttribute('data-made-up') === '1'), { responsive: true, displayModeBar: false, scrollZoom: false });
            }).catch(() => sketchAgain(el.closest('.ar-fig')));      // no plot, no Plotly on the page, or a plot it cannot draw
        });
        root.querySelectorAll('.ar-was').forEach(el => {
            fetched('/get_chain_preview/' + [el.getAttribute('data-thread'), el.getAttribute('data-run')].map(encodeURIComponent).join('/'), json => json.plotPreview).then(src => {
                if (src) el.innerHTML = '<img src="' + esc(src) + '" alt=""><div class="cap">' + WORDS.drewThen + '</div>';
            });
        });
    }
    function mountAll() { document.querySelectorAll('.ar-brief').forEach(mount); }

    // the left pane of a brief not yet run, its newest message in view
    function drawPane(entry) {
        const pane = byId('streamOutput'), mid = talking && talking.entry === entry;
        pane.innerHTML = build.pane(entry, mid ? { sent: talking.sent, waiting: true, saved: talking.saved, drawing: talking.drawing } : {});
        pane.scrollTop = pane.scrollHeight;
    }
    // the Brief tab of a brief not yet run, as it stands now - its figures as sketches while their draft is on its way
    function briefOf(entry) {
        return build.brief(entry.framing, { chain: entry.chain_id, thread: entry.thread_id, state: 'framing', drawing: !!(talking && talking.entry === entry && talking.drawing) });
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
    }
    // a chain comes on screen: a brief not yet run is drawn from its versions; any other Brief tab came with its markup, and its drafts are drawn in it
    function restore(entry) { if (entry && entry.status === 'framing') show(entry); else mountAll(); }
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
            if (typeof composerLock === 'function') composerLock(running ? WORDS.busyRun : talking.saved ? WORDS.readingSaved : talking.drawing ? WORDS.drawingHold : WORDS.replying);
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
    // One exchange with the Architect: what the coach said - nothing on its first turn - and its reply. `version`: the
    // version of the brief on screen when the coach spoke - the exchange goes on from it. Where the reply had the data
    // looked up, the saved analyses read or a part of an earlier analysis opened, the Architect goes on at once: one
    // more exchange, with nothing said. While the saved analyses are read the pane follows the count. Where a draft of
    // the figures follows the reply, the stream carries the framing with the reply first: the page shows it, and the
    // figures as sketches, until the stream ends on the framing with the draft - a stream that ends before it leaves
    // the reply standing, its figures sketches. Resolves to whether the last reply was kept; when one was not, the
    // brief stands as it did and the reason is said.
    function exchange(entry, text, version) {
        if (busy || !entry || entry.status !== 'framing') return Promise.resolve(false);
        busy = true;
        if (version != null) entry.framing = use(entry.framing, version);      // in use from now, here as on the server
        const mine = talking = { entry, sent: text };
        const inView = () => responses[currentResponseIndex] === entry;
        const draw = () => { if (inView()) { refresh(entry); onChain(entry); } };
        const lost = why => { if (!mine.drawing) say(why); return !!mine.drawing; };      // no reply is said, unless one already stands: the stream ended while its draft was drawn
        draw();
        return window.authService.fetch('/architect/say', { method: 'POST', headers: { 'Content-Type': 'application/json' },
                                                             body: JSON.stringify(Object.assign({ thread_id: entry.thread_id, chain_id: entry.chain_id, text: text || null }, version != null ? { version } : {})) })
            .then(r => readStream(r, d => {
                if (talking !== mine) return;
                if (d.type === 'architect_saved') {
                    mine.saved = { read: Number(d.read) || 0, of: d.of == null ? null : Number(d.of) };
                    if (inView()) { drawPane(entry); onChain(entry); }
                } else if (d.type === 'architect_draft' && d.framing) {      // the reply is kept: it is shown while its figures are drawn
                    entry.framing = d.framing;
                    entry.queryText = (versionAt(entry.framing, inUse(entry.framing)).brief || {}).question || entry.queryText;
                    Object.assign(mine, { sent: '', saved: null, drawing: true });
                    draw();
                }
            })).then(body => {
                const out = closing(body);
                if (out.framing) {
                    entry.framing = out.framing;
                    entry.queryText = (versionAt(entry.framing, inUse(entry.framing)).brief || {}).question || entry.queryText;      // the question of the version in use is the chain's
                    return true;
                }
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
    // what the coach typed or chose, said to the Architect of the brief on screen - of the version on screen; a line
    // being typed in the brief is kept first
    function tell(text) {
        const entry = responses[currentResponseIndex], root = briefRoot();
        text = String(text || '').trim();
        if (busy || !text || !entry || entry.status !== 'framing') return Promise.resolve(false);
        if (typeof queryRunning !== 'undefined' && queryRunning) { say(WORDS.busyRun); return Promise.resolve(false); }
        return (root ? keep(root) : Promise.resolve({})).then(out => {
            if (!out) return false;
            const input = byId('queryInput'), now = briefRoot();
            if (input) { input.value = ''; input.style.height = 'auto'; }
            return exchange(entry, text, now ? stateOf(now).shown : null);
        });
    }

    // ---- the Brief tab's clicks: everything is read from the tab's own markup, so a restored chain behaves the same
    function stateOf(root) {
        let framing = {};
        try { framing = JSON.parse(root.getAttribute('data-framing') || '{}'); } catch (e) { framing = {}; }
        return { framing, chain: root.getAttribute('data-chain'), thread: root.getAttribute('data-thread'), state: root.getAttribute('data-state'),
                 shown: Number(root.getAttribute('data-shown')) || inUse(framing), adds: root.getAttribute('data-adds') === '1', drawing: root.getAttribute('data-drawing') === '1' };
    }
    function entryOf(root) {
        const chain = root.getAttribute('data-chain');
        return responses.find(r => r && r.status === 'framing' && String(r.chain_id) === String(chain)) || null;
    }
    function briefRoot() { const host = byId('content-brief'); return host ? host.querySelector('.ar-brief') : null; }
    function redraw(root, shown, more) {
        const st = stateOf(root), host = root.parentNode;
        host.innerHTML = build.brief(st.framing, Object.assign({ chain: st.chain, thread: st.thread, state: st.state, shown: shown || st.shown, drawing: st.drawing }, more || {}));
        mount(host.querySelector('.ar-brief'));
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
        line.innerHTML = build.editor(valueAt(versionAt(st.framing, st.shown).brief || {}, path), path === 'question');
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
    // one change kept as a version - made to the version on screen, which it goes on from: a line's text (apply), a
    // proposal ticked (tick), a saved analysis built on no longer (unbuild), a figure taken out (unfigure)
    function change(root, path, text, how) {
        const entry = entryOf(root);
        const out = entry ? (how || apply)(versionAt(entry.framing, stateOf(root).shown).brief, path, text) : null;      // of the version on screen
        if (!out) { redraw(root); return Promise.resolve({}); }                // nothing changed: the line as it was
        busy = true;
        return post('/architect/brief', { thread_id: entry.thread_id, chain_id: entry.chain_id, brief: out.brief, changed: out.changed }).then(res => {
            if (!res.ok || !res.json.framing) { say(res.json.error || WORDS.notKept + '.'); return false; }      // the line stays open, with what was typed
            entry.framing = res.json.framing;
            entry.queryText = (versionAt(entry.framing, inUse(entry.framing)).brief || {}).question || entry.queryText;
            if (responses[currentResponseIndex] === entry) refresh(entry);
            return { part: path.split('.')[0], removed: out.removed };
        }).catch(() => { say(WORDS.notKept + ': ' + WORDS.unreachable + '.'); return false; }).then(result => { busy = false; return result; });
    }
    // a cross or a box clicked: the line being typed elsewhere is kept first
    function keptFirst(root, path, text, how) {
        if (root.querySelector('.ar-line.editing')) keepThen(root, path, (again, at) => change(again, at, text, how));
        else change(root, path, text, how);
    }
    function start(root) {
        const entry = entryOf(root);
        if (!entry) return;
        if (typeof queryRunning !== 'undefined' && queryRunning) { say(WORDS.busyRun); return; }
        keep(root).then(out => {
            if (!out) return;
            const shown = stateOf(briefRoot() || root).shown;      // the version on screen is the one the analysis runs under
            entry.framing = use(entry.framing, shown);
            entry.queryText = (versionAt(entry.framing, shown).brief || {}).question || entry.queryText;
            handleQuerySubmit({ framed: entry, version: shown });
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
        if (act === 'step') { settled(root, r => redraw(r, stateOf(r).shown + Number(hit.getAttribute('data-step')))); return; }
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

    window.ArchitectUI = { initialize, isOn, open, tell, restore, onChain, framingInView, started, notStarted, dressAnswer, mark, apply, tick, unbuild, unfigure, use, build, readStream, draftLayout };
})();
