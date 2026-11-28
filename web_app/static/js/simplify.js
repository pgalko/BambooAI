// simplify.js - the report of a finished analysis in plain language, written when the person asks for it (2026-11-28,
// the product owner: until then every analysis ended with that call, whether the plain version was read or not).
// The Answer tab of an analysis that ended with a report has a button beside PDF. It says what a click does:
//
//   Simplify     there is no plain version yet: it is asked of the server (POST /simplify, a stream: one call on the
//                Rewriter's seat). The button turns while it is written, and nothing else starts beside it
//   Technical    the plain version is on screen: the technical report comes back
//   Simplified   the technical report is on screen: the plain version comes back
//
// The plain version is shown as soon as it arrives. It is kept with the analysis - by the server, which writes it
// once, and in the page's copy of the chain - and the call is the analysis' own: its card goes into the left pane
// where the run's own cards end, and the run's cost and time are raised by the call's where the pane says them
// (stream-pane.js paneLate). Where the person has gone to another chain meanwhile, all of that is done to the chain's
// kept copy. The page's words sit in WORDS; nothing here reaches a prompt.
//
// window.SimplifyUI = { initialize, dress, holds, build }

(function () {
    'use strict';

    const WORDS = {
        // the button: its word and its hover, by what a click does
        ask: ['Simplify', 'Write this report in plain language'], plain: ['Simplified', 'Show the plain-language version'], technical: ['Technical', 'Show the technical report'],
        wait: 'The plain-language version is being written. Wait for it.', busyRun: 'An analysis is running. Wait for it to end, or stop it.',
        none: 'No plain-language version was written', unreachable: 'the server could not be reached'
    };
    const BUTTON = '.simplified-summary-btn';
    let asking = null;        // the chain whose plain version is being written

    function byId(id) { return document.getElementById(id); }
    function say(text) { if (typeof showSystemMessage === 'function') showSystemMessage(text); }
    function holder(html) { const d = document.createElement('div'); d.innerHTML = html || ''; return d; }
    function running() { return typeof queryRunning !== 'undefined' && queryRunning; }
    // The finished analysis on screen: a chain whose run has ended, on a thread. A routine's run shown in the pane is no
    // chain: the chain behind it is not on screen
    function onScreen() {
        const entry = responses[currentResponseIndex];
        if (window.RoutinesUI && window.RoutinesUI.inRunView()) return null;
        return entry && !entry.status && entry.chain_id != null && entry.thread_id != null ? entry : null;
    }

    // ------------------------------------------------------------ builders (pure: return HTML)
    const build = {
        button() {
            return '<button type="button" class="simplified-summary-btn"><svg class="simplified-icon" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" ' +
                'stroke-linecap="round" stroke-linejoin="round"><path d="M9 18h6"></path><path d="M10 22h4"></path>' +
                '<path d="M15.09 14c.18-.98.65-1.74 1.41-2.5A4.65 4.65 0 0 0 18 8 6 6 0 0 0 6 8c0 1 .23 2.23 1.5 3.5A4.61 4.61 0 0 1 8.91 14"></path></svg>' +
                '<span class="simplified-text"></span><div class="simplified-spinner"></div></button>';
        },
        // the plain version as the Answer tab shows it: its citations chips, as in the technical report (2026-10-11); what
        // the report says against its brief cut, as there (architect.js, 0312); the report's sources under it (0340)
        plain(text, sources) {
            let html = markdownToHtml(text);
            if (typeof paneCiteHtml === 'function') html = paneCiteHtml(html, sources);
            if (window.ArchitectUI) html = window.ArchitectUI.cutAnswer(html).html;
            return html + (typeof paneSourcesHtml === 'function' ? paneSourcesHtml(sources) : '');
        }
    };

    // ------------------------------------------------------------ the button
    // The button as the chain on screen stands: its word, and turning while that chain's plain version is written
    function draw() {
        const button = document.querySelector(BUTTON);
        if (!button) return;
        const busy = !!asking && asking === responses[currentResponseIndex];
        const word = WORDS[!currentData.simplifiedAnswer ? 'ask' : (currentData.summaryViewMode === 'simplified' ? 'technical' : 'plain')];
        button.querySelector('.simplified-text').textContent = word[0];
        button.title = word[1];
        button.setAttribute('aria-label', word[1]);
        button.classList.toggle('loading', busy);
        button.disabled = busy;
    }
    // The button in an Answer tab's header, before PDF (pdf-export.js handleAnswerTabUpdate: wherever an answer is
    // drawn, a chain shown again included): where the analysis has a plain version, or ended with a report - its
    // closing card then has the row of what can be done next (stream-pane.js). A run that asked, or was stopped, and
    // a routine's run have neither
    function dress(answerTab) {
        const pdf = answerTab && answerTab.querySelector('.pdf-export-btn'), pane = byId('streamOutput');
        const offered = !(window.RoutinesUI && window.RoutinesUI.inRunView()) && (!!currentData.simplifiedAnswer || (!!pane && !!pane.querySelector('.sp-done .acts')));
        if (!pdf || !offered) return;
        if (!answerTab.querySelector(BUTTON)) pdf.parentElement.insertBefore(holder(build.button()).firstElementChild, pdf);
        draw();
    }
    // One of the report's two versions in the Answer tab: the plain one, or the technical report as it was drawn. Its
    // formulas are set last: the text and the button stand whatever the library that sets them does
    function show(view) {
        const body = document.querySelector('#content-answer .content-body'), report = holder(currentData.technicalAnswer);
        if (!body) return;
        if (view === 'simplified') body.innerHTML = build.plain(currentData.simplifiedAnswer, (currentData.reportHead && currentData.reportHead.sources) || []);
        else if (currentData.technicalAnswer) body.innerHTML = (report.querySelector('.content-body') || report).innerHTML;
        currentData.summaryViewMode = view;
        draw();
        renderLatex(body);
    }

    // ------------------------------------------------------------ asking
    // The plain version that arrived, taken as the chain's: into its kept copy, and its call's card into its pane - the
    // one on screen when the chain is in view, else its kept markup - unless the pane has that card (a plain version the
    // server had kept, asked for again). On screen it is shown at once
    function take(entry, out) {
        const here = responses[currentResponseIndex] === entry, pane = here ? byId('streamOutput') : holder(entry.streamOutput);
        entry.simplifiedAnswer = out.text;
        if (out.card && !pane.querySelector('.sp-turn[data-turn="rewrite"]')) {
            window.paneLate(pane, Object.assign({ turn: 'rewrite', kind: 'rewrite', said: out.text }, out.card));
        }
        entry.streamOutput = pane.innerHTML;
        if (typeof localforage !== 'undefined') Promise.resolve(localforage.setItem('responses', responses)).catch(() => { /* the page's copy is a courtesy */ });
        if (here) { currentData.simplifiedAnswer = out.text; show('simplified'); }
    }
    // The plain version of the finished analysis on screen, asked of the server: one at a time, and not while an
    // analysis runs or another call beside the analyses is being written - they would share the instance's stream.
    // Where none comes back, the reason is said
    function ask() {
        const entry = onScreen();
        if (asking) { say(WORDS.wait); return; }
        if (running()) { say(WORDS.busyRun); return; }
        if (!entry || (window.NextQuestionsUI && window.NextQuestionsUI.holds()) || (window.ExplainUI && window.ExplainUI.holds())) return;
        let out = {};
        asking = entry;
        draw();
        window.authService.fetch('/simplify', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ thread_id: entry.thread_id, chain_id: entry.chain_id }) })
            .then(r => window.ArchitectUI.readStream(r, d => {
                if (d.simplify) out = d.simplify;
                else if (d.error || d.routine_error) out = { error: d.error || d.routine_error };
            }))
            .catch(() => { out = { error: WORDS.none + ': ' + WORDS.unreachable + '.' }; })
            .then(() => {
                asking = null;
                draw();
                if (out.text) take(entry, out); else say(out.error || WORDS.none + '.');
            });
    }
    // an analysis may not start while a plain version is being written: the two would share the instance's stream
    function holds() {
        if (!asking) return false;
        say(WORDS.wait);
        return true;
    }

    // a click on the button, wherever an Answer tab has one: the other version, or - there is no plain one yet - the request for it
    function initialize() {
        document.addEventListener('click', event => {
            const button = event.target.closest ? event.target.closest(BUTTON) : null;
            if (!button || button.disabled) return;
            if (currentData.simplifiedAnswer) show(currentData.summaryViewMode === 'simplified' ? 'technical' : 'simplified');
            else ask();
        });
    }

    window.SimplifyUI = { initialize, dress, holds, build };
})();
