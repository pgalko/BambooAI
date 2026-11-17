// architect.js - the Architect on the page (docs/ARCHITECT_DESIGN.md §2.6, §2.8, §2.9, §2.11-§2.14; 2026-11-16). A
// question typed with the switch on is framed before it is analysed: the server opens a framing run on the thread's
// record (POST /architect/open) and the page shows it as a chain of its own, the conversation in the left pane and
// its brief on a Brief tab. The Architect fills the brief from the question and asks for what is missing, one
// exchange a call (POST /architect/say, a stream); while such a chain is on screen the composer is the conversation's
// input. Where a reply had the data looked up, the round is a row of the conversation and the Architect goes on at
// once, with the marks. The coach also changes the brief where it stands, and ticks what the Architect proposed;
// every change kept is one more version, stored by the server (POST /architect/brief). Start analysis continues the
// same chain (/query with run_id), so the question is one box on the thread map.
//
// Where a reply has the coach's saved analyses read (§3.7), the stream says how far the reading is: a row of the
// conversation with a count and Skip (POST /architect/skip). What was found is a row too, and the passages stand in
// the brief, each with a box to tick, a cross to leave it out and Open (GET /architect/saved/<thread>/<run>). The
// coach asks for a reading with Look in saved analyses.
//
// A brief not yet run is drawn from its versions (the chain's `framing`), never from kept markup. Once it runs, the
// Brief tab's markup carries the versions (data-framing), so a restored chain or a saved favourite steps through them
// with nothing else kept.
//
// The report of a run with a brief has a part "Against the brief" (analyst/session.py): dressAnswer() makes it a card
// of verdicts. The page's words sit in WORDS; nothing here reaches a prompt.
//
// window.ArchitectUI = { initialize, isOn, open, tell, restore, onChain, framingInView, started, notStarted,
//                        dressAnswer, mark, apply, tick, build, readStream }

(function () {
    'use strict';

    const WORDS = {
        answer: 'Answer, or say what to change', replying: 'The Architect is replying', reading: 'reading…', readingSaved: 'Your saved analyses are being read',
        unsaid: 'not said yet', unsaidKept: 'not said', left: 'left to the Analyst', add: '+ Add', tick: 'Have the analysis test it',
        standing: 'Chance, measurement error, how the cases were chosen',
        would: 'You would change your mind if:',
        why: { question: 'from your question', last: 'from the last brief', person: 'changed by you',
               architect: { question: 'the Architect, from your question', answer: 'the Architect, from your answer', check: 'the Architect, after checking the data',
                            memory: 'the Architect, from your saved analyses' } },
        notKept: 'The change was not kept', notOpened: 'The brief could not be opened', unreachable: 'the server could not be reached',
        noReply: 'The Architect did not reply', check: 'CHECK data', lookedUp: n => n + (n === 1 ? ' thing' : ' things') + ' looked up', notLookedUp: n => n + ' not',
        busyRun: 'Another analysis is running. Wait for it to end, or stop it.',
        saved: 'SAVED analyses', found: n => n + (n === 1 ? ' passage' : ' passages') + ' found', noneFound: 'nothing found', readOf: (r, m) => r ? 'read ' + r + ' of ' + m : m + ' saved',
        looking: (r, m) => r ? 'reading ' + r + ' of ' + m : (m == null ? 'looking' : 'looking through ' + m), skip: 'Skip', skipped: 'skipped', notRead: 'not read',
        open: 'Open', look: 'Look in saved analyses', lookSay: 'Look in my saved analyses.', notOpenedSaved: 'This analysis could not be opened', code: 'Code', agreed: 'Brief', talk: 'Conversation',
        notStarted: 'The analysis did not start',
        against: { head: 'Against the brief', expected: 'You expected', would: 'Would change your mind', checks: 'Also checked' }
    };
    const FROM_LAST = 'from the last brief';      // the server's mark on the first version of a follow-up's brief (BambooAI.open_framing)
    const TEXT_CHARS = 600, QUESTION_CHARS = 4000;   // one line of a brief, and the question, as analyst/brief.py bounds them
    const CAP = { rests_on: 4, also_check: 2 };   // the design's counts (§2.2): three or four anchors, at most two rivals
    const READINGS = 4;                           // readings of the saved analyses in one brief (analyst/architect.py)
    const SKIPPED = 'The person skipped it.';     // why a reading the coach skipped was not made, as the reader says it (analyst/reader.py)
    const SINGLE = ['question', 'decision', 'thinks', 'expects', 'would_change'];
    const FIXED = [['comparison', 'Compare'], ['measure', 'Measure'], ['period', 'Period']];
    const LOCKED = ['data', 'saved'];             // a fact from a lookup, a passage of a saved analysis: left out, never changed (§2.6)
    const SOURCE = { architect: ['ar', 'Architect'], data: ['', 'data'], saved: ['mem', 'saved analysis'], result: ['', 'last result'] };   // the coach's own lines carry no chip
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
    function valueAt(brief, path) {
        const part = path.split('.')[0], at = path.split('.')[1];
        if (part === 'rests_on' || part === 'also_check') return at === '+' ? '' : (((brief[part] || [])[Number(at)] || {}).text || '');
        if (part === 'fixed') return (brief.fixed || {})[at] || '';
        return brief[part] || '';
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
        if (part === 'saved') {                                   // a passage of a saved analysis: left out, never changed (§2.6)
            const list = Array.isArray(b.saved) ? b.saved : [], i = Number(at);
            if (t || !list[i]) return null;
            list.splice(i, 1);
            if (!list.length) delete b.saved;
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

    // the brief with a proposal of the Architect's, or a passage of a saved analysis, accepted or no longer (pure):
    // {brief, changed}, or null for any other line
    function tick(brief, path) {
        const b = JSON.parse(JSON.stringify(brief || {}));
        const part = String(path).split('.')[0];
        const line = part === 'also_check' || part === 'saved' ? (b[part] || [])[Number(String(path).split('.')[1])] : null;
        if (!line || (part === 'also_check' && line.source !== 'architect')) return null;
        line.accepted = !line.accepted;
        return { brief: b, changed: [path] };
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
        // one line of the brief: its text, or what an empty part reads; a pencil where the coach can change it, a cross
        // where they can leave it out; a box to tick on what the Architect proposed. o: {empty, pre, list, source,
        // mark, note, shows, locked, tick}
        line(c, path, text, o) {
            o = o || {};
            const can = c.edit && !(text && o.locked);
            const mark = MARK[o.mark] ? '<span class="mk ' + MARK[o.mark][0] + '" title="' + esc(o.mark) + '">' + MARK[o.mark][1] + '</span>'
                : o.tick == null ? '' : '<button type="button" class="tick' + (o.tick ? ' on' : '') + '" role="checkbox" aria-checked="' + !!o.tick + '" title="' + WORDS.tick + '"' +
                    (c.edit ? ' data-ar="tick"' : ' disabled') + '>' + (o.tick ? ICON.ok : '') + '</button>';
            const under = [o.note ? '<span class="fact' + (o.mark === 'does not hold' ? ' no' : '') + '">' + esc(o.note) + '</span>' : '',
                           o.shows ? '<span class="fact">' + esc(o.shows) + '</span>' : ''].join('');
            const body = text ? '<span class="tx">' + esc(text) + under + '</span>'
                              : '<span class="tx ' + (o.add ? 'add' : 'open') + '"' + (can ? ' data-ar="edit" role="button" tabindex="0"' : '') + '>' + (o.add ? WORDS.add : (o.empty || (c.edit ? WORDS.unsaid : WORDS.unsaidKept))) + '</span>';
            const tools = text && c.edit ? (can ? '<button type="button" class="pen" data-ar="edit" title="Change">' + ICON.pen + '</button>' : '')
                                           + (o.list ? '<button type="button" class="drop" data-ar="drop" title="Leave out">' + ICON.x + '</button>' : '') : '';
            const chip = SOURCE[o.source] ? '<span class="src' + (SOURCE[o.source][0] ? ' ' + SOURCE[o.source][0] : '') + '">' + SOURCE[o.source][1] + '</span>' : '';
            return '<div class="ar-line' + (c.changed.indexOf(path) >= 0 ? ' changed' : '') + (o.add ? ' adds' : '') + '" data-path="' + esc(path) + '">' +
                (o.pre ? '<span class="pre">' + o.pre + '</span> ' : '') + mark + body + tools + chip + '</div>';
        },
        // a passage of a saved analysis: a box to tick, the day and what was asked then, the passage, the reader's
        // note, where it stands, whose data it ran on and which; Open, and a cross to leave it out
        passage(c, path, s) {
            const tick = '<button type="button" class="tick' + (s.accepted ? ' on' : '') + '" role="checkbox" aria-checked="' + !!s.accepted + '" title="' + WORDS.tick + '"' +
                (c.edit ? ' data-ar="tick"' : ' disabled') + '>' + (s.accepted ? ICON.ok : '') + '</button>';
            const from = [s.where, s.person, s.data, s.period, s.marks].filter(Boolean).join(' · ');
            return '<div class="ar-line ar-saved' + (c.changed.indexOf(path) >= 0 ? ' changed' : '') + '" data-path="' + esc(path) + '">' + tick +
                '<span class="tx">' + esc([s.when, s.question].filter(Boolean).join(' · ')) + (s.passage ? '<span class="fact quote">' + esc(s.passage) + '</span>' : '') +
                (s.note ? '<span class="fact said">' + esc(s.note) + '</span>' : '') + (from ? '<span class="fact from">' + esc(from) + '</span>' : '') + '</span>' +
                (s.thread && s.run ? '<button type="button" class="ar-open" data-ar="open" data-thread="' + esc(s.thread) + '" data-run="' + esc(s.run) + '">' + WORDS.open + '</button>' : '') +
                (c.edit ? '<button type="button" class="drop" data-ar="drop" title="Leave out">' + ICON.x + '</button>' : '') + '<span class="src mem">' + SOURCE.saved[1] + '</span></div>';
        },
        // a list of the brief: its lines, then where the next one is typed while the design's count allows it
        lines(c, part, items, of) {
            const rows = (items || []).map((x, i) => build.line(c, part + '.' + i, x.text, Object.assign({ list: true, locked: LOCKED.indexOf(x.source) >= 0 }, of(x))));
            if (!rows.length && part === 'rests_on') rows.push(build.line(c, part + '.+', ''));
            else if (c.edit && rows.length < CAP[part]) rows.push(build.line(c, part + '.+', '', { add: true }));
            return rows.join('');
        },
        version(framing, shown) {
            const n = latestN(framing), v = versionAt(framing, shown);
            const why = v.by === 'architect' ? (WORDS.why.architect[v.why] || WORDS.why.architect.answer)
                : (shown > 1 ? WORDS.why.person : ((v.changed || []).indexOf(FROM_LAST) >= 0 ? WORDS.why.last : WORDS.why.question));
            const arrow = (d, glyph, title, off) => '<button type="button" data-ar="step" data-step="' + d + '" title="' + title + '"' + (off ? ' disabled' : '') + '>' + glyph + '</button>';
            return '<div class="ar-ver"><span class="step">' + arrow(-1, '‹', 'The version before', shown <= 1) + '<b>v' + shown + '</b>' + arrow(1, '›', 'The version after', shown >= n) + '</span>' +
                '<span class="why">' + why + '</span></div>';
        },
        // the Brief tab. o: {chain, state: 'framing' | 'run', shown}; the versions ride in the markup
        brief(framing, o) {
            const n = latestN(framing), shown = Math.min(n, Math.max(1, o.shown || n)), v = versionAt(framing, shown), b = v.brief || {};
            const c = { edit: o.state === 'framing' && shown === n, changed: v.changed || [] };
            const fixed = b.fixed || {};
            const saved = (b.saved || []).map((x, i) => build.passage(c, 'saved.' + i, x)).join('');
            const readings = turnsOf(framing).filter(t => t.who === 'memory').length;
            const look = c.edit && Number(framing.saved) > 0 && readings < READINGS ? '<div class="ar-line"><button type="button" class="ar-look" data-ar="look">' + WORDS.look + '</button></div>' : '';
            const aside = (b.set_aside || []).map(x => '<div class="ar-line"><span class="tx">' + esc(x) + '</span></div>').join('');
            return '<div class="ar-brief" data-chain="' + esc(o.chain) + '" data-state="' + esc(o.state) + '" data-shown="' + shown + '" data-framing="' + esc(JSON.stringify(framing || {})) + '">' +
                '<h1 class="ar-line ar-q' + (c.changed.indexOf('question') >= 0 ? ' changed' : '') + '" data-path="question"><span class="tx">' + esc(b.question || '') + '</span>' +
                    (c.edit ? '<button type="button" class="pen" data-ar="edit" title="Change">' + ICON.pen + '</button>' : '') + '</h1>' +
                build.version(framing, shown) +
                '<h3>Decision</h3>' + build.line(c, 'decision', b.decision) +
                '<h3>What you think</h3>' + build.line(c, 'thinks', b.thinks) +
                '<h3>It rests on</h3>' + build.lines(c, 'rests_on', b.rests_on, x => ({ source: x.source, mark: x.mark, note: x.note })) +
                '<h3>You expect</h3>' + build.line(c, 'expects', b.expects) + build.line(c, 'would_change', b.would_change, { pre: WORDS.would }) +
                '<h3>Also check</h3><div class="ar-line"><span class="tx">' + WORDS.standing + '</span><span class="src">always</span></div>' +
                    build.lines(c, 'also_check', b.also_check, x => ({ shows: x.shows, source: x.source, tick: x.source === 'architect' ? !!x.accepted : null })) +
                '<h3>Fixed before the run</h3><div class="ar-grid">' + FIXED.map(f => '<span class="k">' + f[1] + '</span>' + build.line(c, 'fixed.' + f[0], fixed[f[0]], { empty: WORDS.left })).join('') + '</div>' +
                (saved || look ? '<h3>From saved analyses</h3>' + saved + look : '') +
                (aside ? '<h3>Set aside</h3>' + aside : '') +
                (c.edit ? '<div class="ar-foot"><button type="button" class="ui-btn primary" data-ar="start">Start analysis</button></div>' : '') +
                '</div>';
        },
        editor(text, question) {
            return '<span class="ar-edit"><textarea class="ar-input" rows="1" maxlength="' + (question ? QUESTION_CHARS : TEXT_CHARS) + '">' + esc(text) + '</textarea>' +
                '<button type="button" class="ok" data-ar="keep" title="Keep">' + ICON.ok + '</button><button type="button" class="no" data-ar="cancel" title="Cancel">' + ICON.x + '</button></span>';
        },
        you(text) { return '<div class="ar-msg you"><span class="who">You</span>' + esc(text) + '</div>'; },
        // a message of the Architect's: its words, the button to the prompt it received (the run log's call), and its
        // choices while they can still be clicked
        said(turn, chain, live) {
            const prompt = turn.call ? '<button class="agent-instructions-btn sp-prompt" type="button" title="the prompt the Architect received (run log)" data-agent="Architect" data-chain="' +
                esc(chain) + '" data-call="' + esc(turn.call) + '">⌘</button>' : '';
            const choices = live && (turn.choices || []).length ? '<div class="ar-choices">' + turn.choices.map(c => '<button type="button" class="ar-choice" data-ar="choice">' + esc(c) + '</button>').join('') + '</div>' : '';
            return '<div class="ar-msg arch"><span class="who">Architect' + prompt + '</span>' + esc(turn.text) + choices + '</div>';
        },
        // a round of lookups, as the pane shows a tool's row: how many gave a result, how many did not, the seconds;
        // what each found is the row's title, a line to a lookup
        checked(turn) {
            const found = turn.found || [], ran = found.filter(f => f.ran).length;
            return '<div class="sp-row tool read" title="' + esc(found.map(f => f.fact).join('\n')) + '"><span>✓</span><span class="in">' + WORDS.check + '</span>' +
                '<span class="out">' + WORDS.lookedUp(ran) + (ran < found.length ? ' · ' + WORDS.notLookedUp(found.length - ran) : '') + '</span>' +
                '<span class="t">' + Math.max(1, Math.round(Number(turn.secs) || 0)) + ' s</span></div>';
        },
        // a reading of the saved analyses, done: how many passages it found, how many of the saved runs were read,
        // the seconds - or that the coach skipped it, or why nothing was read; the passages and what was found
        // across them are the row's title
        recalled(turn) {
            const found = turn.found || [], across = turn.across;
            const lines = found.map(f => f.when + ' · ' + f.question + ': "' + f.quote + '"')
                .concat(across ? [across.topic + ': ' + (across.groups || []).map(g => (g.runs || []).length + ' × ' + g.label).join('; ')] : []);
            const out = turn.failed === SKIPPED ? WORDS.skipped : turn.failed ? WORDS.notRead + ' · ' + turn.failed
                : (found.length ? WORDS.found(found.length) : WORDS.noneFound) + ' · ' + WORDS.readOf(turn.read || 0, turn.of || 0);
            return '<div class="sp-row tool read' + (turn.failed ? ' skipped' : '') + '" title="' + esc(lines.join('\n')) + '"><span>' + (turn.failed ? '–' : '✓') + '</span><span class="in">' + WORDS.saved + '</span>' +
                '<span class="out">' + esc(out) + '</span><span class="t">' + Math.max(1, Math.round(Number(turn.secs) || 0)) + ' s</span></div>';
        },
        // a reading in flight: how far it is, and Skip - once the server has said how many are saved: it has started
        // then, and a skip sent before would be lost. at: {read, of}
        reading(at) {
            return '<div class="sp-row tool read pending"><span class="live"></span><span class="in">' + WORDS.saved + '</span><span class="out">' + WORDS.looking(at.read, at.of) + '</span>' +
                '<button type="button" class="ar-skip" data-ar="skip"' + (at.of == null ? ' disabled' : '') + '>' + WORDS.skip + '</button></div>';
        },
        // the conversation: the question, then what was said, what was looked up and what the saved analyses hold. o:
        // {live: the last message's choices can be clicked, sent: a message on its way, waiting: the Architect is
        // replying, saved: the saved analyses are being read - how far}
        talk(entry, o) {
            o = o || {};
            const turns = turnsOf(entry.framing);
            return build.you((versionAt(entry.framing, 1).brief || {}).question || entry.queryText) +      // as it was first asked: the brief holds it as it stands now
                turns.map((t, i) => t.who === 'check' ? build.checked(t) : t.who === 'memory' ? build.recalled(t)
                    : t.who === 'architect' ? build.said(t, entry.chain_id, o.live && !o.waiting && i === turns.length - 1) : build.you(t.text)).join('') +
                (o.sent ? build.you(o.sent) : '') +
                (o.waiting ? (o.saved ? build.reading(o.saved) : '<div class="ar-msg arch wait"><span class="who">Architect</span>' + WORDS.reading + '</div>') : '');
        },
        // the left pane of a brief not yet run: which version stands, what the Architect's calls cost, the conversation
        pane(entry, o) {
            const cost = turnsOf(entry.framing).reduce((sum, t) => sum + (Number(t.cost) || 0), 0);
            return '<div class="sp-strip"><span class="live idle"></span><span class="mode">Architect</span><span>brief <b>v' + latestN(entry.framing) + '</b></span>' +
                (cost >= 0.005 ? '<span>$' + cost.toFixed(2) + '</span>' : '') + '</div>' +
                '<div class="sp-stream">' + build.talk(entry, Object.assign({ live: true }, o)) + '</div>';
        },
        // the framing folded to one row, above the run it started: the conversation is inside
        fold(entry) {
            return '<details class="sp-turn ar-fold"><summary><span class="chev"></span><span class="n">Architect</span><span class="kind">brief v' + latestN(entry.framing) + '</span>' +
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

    // the left pane of a brief not yet run, its newest message in view
    function drawPane(entry) {
        const pane = byId('streamOutput'), mid = talking && talking.entry === entry;
        pane.innerHTML = build.pane(entry, mid ? { sent: talking.sent, waiting: true, saved: talking.saved } : {});
        pane.scrollTop = pane.scrollHeight;
    }
    function show(entry) {
        drawPane(entry);
        byId('tabContainer').innerHTML = '<div id="tab-brief" class="tab active">Brief</div>';
        byId('contentOutput').innerHTML = '<div id="content-brief" class="tab-content active">' + build.brief(entry.framing, { chain: entry.chain_id, state: 'framing' }) + '</div>';
    }
    // after a change: the brief and the pane in place, so the tab keeps its scroll
    function refresh(entry) {
        const root = briefRoot();
        if (root) root.parentNode.innerHTML = build.brief(entry.framing, { chain: entry.chain_id, state: 'framing' });
        drawPane(entry);
    }
    function restore(entry) { if (entry && entry.status === 'framing') show(entry); }
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
            if (typeof composerLock === 'function') composerLock(running ? WORDS.busyRun : talking.saved ? WORDS.readingSaved : WORDS.replying);
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
    // One exchange with the Architect: what the coach said - nothing on its first turn - and its reply. Where the
    // reply had the data looked up or the saved analyses read, the Architect goes on at once: one more exchange, with
    // nothing said. While the saved analyses are read the pane follows the count. `look`: the coach asks for the
    // saved analyses - they are read first, and the Architect replies in the exchange after. Resolves to whether
    // the last reply was kept; when one was not, the brief stands as it did and the reason is said.
    function exchange(entry, text, look) {
        if (busy || !entry || entry.status !== 'framing') return Promise.resolve(false);
        busy = true;
        const mine = talking = Object.assign({ entry, sent: text }, look ? { saved: { read: 0, of: null } } : {});      // asked for, the reading starts at once
        const inView = () => responses[currentResponseIndex] === entry;
        const draw = () => { if (inView()) { refresh(entry); onChain(entry); } };
        draw();
        return window.authService.fetch('/architect/say', { method: 'POST', headers: { 'Content-Type': 'application/json' },
                                                             body: JSON.stringify(Object.assign({ thread_id: entry.thread_id, chain_id: entry.chain_id, text: text || null }, look ? { look: true } : {})) })
            .then(r => readStream(r, d => {
                if (d.type !== 'architect_saved' || talking !== mine) return;
                mine.saved = { read: Number(d.read) || 0, of: d.of == null ? null : Number(d.of) };
                if (inView()) { drawPane(entry); onChain(entry); }
            })).then(body => {
                const out = closing(body);
                if (out.framing) {
                    entry.framing = out.framing;
                    entry.queryText = (versionAt(entry.framing).brief || {}).question || entry.queryText;      // a wording the person agreed to is the chain's question
                    return true;
                }
                say(out.error || WORDS.noReply + '.');
                return false;
            }).catch(() => { say(WORDS.noReply + ': ' + WORDS.unreachable + '.'); return false; }).then(kept => {
                busy = false; talking = null;
                const turns = turnsOf(entry.framing);
                if (kept && turns.length && ['check', 'memory'].indexOf(turns[turns.length - 1].who) >= 0) return exchange(entry, '');
                draw();
                const input = byId('queryInput');
                if (!kept && text && inView() && input && !input.value) input.value = text;      // what was typed is not lost
                return kept;
            });
    }
    // what the coach typed or chose, said to the Architect of the brief on screen; a line being typed in the brief is kept first
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
        return { framing, chain: root.getAttribute('data-chain'), state: root.getAttribute('data-state'), shown: Number(root.getAttribute('data-shown')) || latestN(framing) };
    }
    function entryOf(root) {
        const chain = root.getAttribute('data-chain');
        return responses.find(r => r && r.status === 'framing' && String(r.chain_id) === String(chain)) || null;
    }
    function briefRoot() { const host = byId('content-brief'); return host ? host.querySelector('.ar-brief') : null; }
    function redraw(root, shown) {
        const st = stateOf(root);
        root.parentNode.innerHTML = build.brief(st.framing, Object.assign(st, { shown: shown || st.shown }));
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
        const pre = line.querySelector('.pre');
        line.classList.add('editing');
        line.innerHTML = (pre ? pre.outerHTML + ' ' : '') + build.editor(valueAt(versionAt(stateOf(root).framing).brief || {}, path), path === 'question');
        const input = line.querySelector('.ar-input');
        if (input) { input.focus(); grow(input); if (input.setSelectionRange) input.setSelectionRange(input.value.length, input.value.length); }
    }
    function grow(input) { if (input.style && input.scrollHeight) { input.style.height = 'auto'; input.style.height = input.scrollHeight + 'px'; } }
    // the line being typed is kept: resolves to what changed ({part, removed}), or false when the server did not keep it
    function keep(root) {
        const line = root.querySelector('.ar-line.editing');
        if (!line) return Promise.resolve({});
        const input = line.querySelector('.ar-input');
        return change(root, line.getAttribute('data-path'), input.value != null ? input.value : input.textContent);
    }
    // one change kept as a version: a line's text (apply), or a proposal ticked (tick)
    function change(root, path, text, how) {
        const entry = entryOf(root);
        const out = entry ? (how || apply)(versionAt(entry.framing).brief, path, text) : null;
        if (!out) { redraw(root); return Promise.resolve({}); }                // nothing changed: the line as it was
        busy = true;
        return post('/architect/brief', { thread_id: entry.thread_id, chain_id: entry.chain_id, brief: out.brief, changed: out.changed }).then(res => {
            if (!res.ok || !res.json.framing) { say(res.json.error || WORDS.notKept + '.'); return false; }      // the line stays open, with what was typed
            entry.framing = res.json.framing;
            entry.queryText = (versionAt(entry.framing).brief || {}).question || entry.queryText;
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
        keep(root).then(out => { if (out) handleQuerySubmit({ framed: entry }); });
    }
    // the analysis of a brief begins (handleQuerySubmit, after the panes are cleared): the framing folds to one row above
    // the run, the Brief tab stays, read-only
    function started(entry) {
        if (typeof paneAppend === 'function') paneAppend(build.fold(entry));
        if (typeof createOrUpdateTab === 'function') createOrUpdateTab('brief', build.brief(entry.framing, { chain: entry.chain_id, state: 'run' }));
    }
    // the server did not start it (the balance, the network): the chain is a brief again, as it stood
    function notStarted(entry, why) {
        if (typeof revertLiveChain === 'function') revertLiveChain(entry);
        if (responses[currentResponseIndex] === entry) show(entry);
        if (typeof updateNavigationButtons === 'function') updateNavigationButtons();
        if (why) say(WORDS.notStarted + ': ' + why);
    }

    // the coach asks for the saved analyses: said in the conversation, and read at once; a line being typed in the brief is kept first
    function lookNow(root) {
        const entry = entryOf(root);
        if (!entry) return;
        if (typeof queryRunning !== 'undefined' && queryRunning) { say(WORDS.busyRun); return; }
        keep(root).then(out => { if (out) exchange(entry, WORDS.lookSay, true); });
    }
    // a saved analysis the brief names, to read beside it: the report, and the code under it
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
        if (hit && hit.getAttribute('data-ar') === 'open') { openSaved(hit.getAttribute('data-thread'), hit.getAttribute('data-run')); return; }
        if ((hit && hit.getAttribute('data-ar') === 'shut') || (ev.target && ev.target.id === 'savedAnalysisModal')) { byId('savedAnalysisModal').style.display = 'none'; return; }      // its cross, or beside it
        const root = hit ? hit.closest('.ar-brief') : null;
        if (!root) return;
        const act = hit.getAttribute('data-ar');
        if (act === 'step') { redraw(root, stateOf(root).shown + Number(hit.getAttribute('data-step'))); return; }
        if (busy) return;
        if (act === 'look') { lookNow(root); return; }
        const line = hit.closest('.ar-line');
        if (act === 'edit') edit(root, line);
        else if (act === 'drop') keptFirst(root, line.getAttribute('data-path'), '');
        else if (act === 'tick') keptFirst(root, line.getAttribute('data-path'), null, tick);
        else if (act === 'keep') keep(root);
        else if (act === 'cancel') redraw(root);
        else if (act === 'start') start(root);
    }
    function onKey(ev) {
        const at = ev.target && ev.target.closest ? ev.target : null;
        const root = at ? at.closest('.ar-brief') : null;
        if (!root || ev.isComposing) return;
        if (at.closest('.ar-input')) {
            if (ev.key === 'Enter' && !ev.shiftKey) { ev.preventDefault(); if (!busy) keep(root); }      // Shift+Enter is a new line (the question may have several)
            else if (ev.key === 'Escape') { ev.preventDefault(); redraw(root); }
        } else if (at.closest('.tx[data-ar="edit"]') && (ev.key === 'Enter' || ev.key === ' ') && !busy) {      // a part not said yet, reached with the keyboard
            ev.preventDefault();
            edit(root, at.closest('.ar-line'));
        }
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

    window.ArchitectUI = { initialize, isOn, open, tell, restore, onChain, framingInView, started, notStarted, dressAnswer, mark, apply, tick, build, readStream };
})();
