// The gallery's Architect states (tools/render_gallery.py; docs/ARCHITECT_DESIGN.md §2.11-§2.14): the Architect's first
// question, its reply awaited, a brief after the conversation with a line being changed by hand, what the brief rests on
// checked against the data with an explanation proposed, and a report against a brief. An invented field trial, as the
// stack's scenario has it.
window.galleryArchitect = (function () {
  const Q = 'Is regime C worth switching to from regime A?';
  const BRIEF = { question: Q, decision: 'Switch the clay plots to regime C next season, or keep A.', thinks: 'C does better than A.',
    rests_on: [{ text: 'The C plots looked greener last season.', source: 'person', mark: '' }], expects: 'C yields at least 0.3 t/ha more than A.',
    also_check: [{ text: 'Rainfall differed between the C and A plots.' }], fixed: { comparison: 'regime C against regime A, within soil type', measure: 'yield, plot means' } };
  const said = (text, more) => Object.assign({ who: 'architect', text, cost: 0.004 }, more);
  const you = text => ({ who: 'person', text });
  const V1 = { n: 1, by: 'person', changed: [], brief: { question: Q } };
  const V2 = { n: 2, by: 'architect', why: 'question', changed: ['fixed.comparison'], brief: { question: Q, fixed: { comparison: 'regime C against regime A' } } };
  const ASK = said('What will you do differently depending on the answer?', { choices: ['Switch to regime C', 'Keep regime A'], v: 2, call: 1 });
  const first = { versions: [V1, V2], turns: [ASK], calls: 1 };
  const framing = { versions: [V1, V2, { n: 3, by: 'architect', why: 'answer', changed: ['expects'], brief: Object.assign({}, BRIEF, { fixed: { comparison: 'regime C against regime A' }, also_check: undefined }) },
                               { n: 4, by: 'person', changed: ['fixed.measure'], brief: BRIEF }],
                    turns: [ASK, you('Switch the clay plots to regime C next season, or keep A.'), said('What do you think is going on, and what makes you think so?', { v: 2, call: 2 }),
                            you('C does better than A because the C plots looked greener last season.'), said('What do you expect to see?', { v: 2, call: 3 }),
                            you('C yields at least 0.3 t/ha more than A.'), said('The brief is ready: start the analysis, or change a line.', { v: 3, call: 4 })], calls: 4 };
  // the check against the data: a line that does not hold, one that holds, one that cannot be checked
  const RAIN = 'The C plots got the most rain.', SAME = 'Each regime has the same number of plots.', GREEN = 'The C plots looked greener last season.';
  const RAIN_FACT = 'total of rainfall_mm by regime: A 100,448 · B 102,189 · C 100,570', SAME_FACT = 'rows by regime: A 240 · B 240 · C 240';
  const lines = marked => [[RAIN, 'does not hold', RAIN_FACT], [SAME, 'holds', SAME_FACT], [GREEN, 'cannot be checked', 'nothing loaded records it']]
    .map(l => marked ? { text: l[0], source: 'person', mark: l[1], note: l[2] } : { text: l[0], source: 'person', mark: '' });
  const ASKED = { question: Q, decision: BRIEF.decision, thinks: BRIEF.thinks, expects: BRIEF.expects, fixed: { comparison: 'regime C against regime A' } };
  const ITS = { text: 'The C plots sit on other soil than the A plots', shows: 'the gap narrows within a soil type', source: 'architect', accepted: false };      // what it proposes, unticked
  const checked = { versions: [V1, V2, { n: 3, by: 'architect', why: 'answer', changed: ['expects'], brief: Object.assign({}, ASKED, { rests_on: lines(false) }) },
                               { n: 4, by: 'architect', why: 'check', changed: ['also_check.0', 'rests_on.0', 'rests_on.1', 'rests_on.2'], brief: Object.assign({}, ASKED, { rests_on: lines(true), also_check: [ITS] }) }],
                    turns: [you('C does better than A because the C plots got the most rain.'), said('What do you expect to see?', { v: 2, call: 3 }), you('C yields at least 0.3 t/ha more than A.'),
                            said('Checking this against the data.', { v: 3, call: 4 }),
                            { who: 'check', found: [{ k: 1, about: RAIN, fact: RAIN_FACT, ran: true }, { k: 2, about: SAME, fact: SAME_FACT, ran: true }], secs: 1.8 },
                            said('One line does not hold: the B plots got the most rain, 102,189 against 100,570. Keep what you think, or change it?', { choices: ['Keep it', 'Change it'], v: 4, call: 5 })], calls: 5 };
  const entryOf = f => ({ status: 'framing', chain_id: 1763203380, thread_id: 1763203300, parentChainId: null, queryText: Q, tabContent: '', contentOutput: '', streamOutput: '', taskContents: {}, framing: f });
  const show = f => { const entry = entryOf(f); responses = [entry]; currentResponseIndex = 0; loadResponseContent(entry); updateNavigationButtons(); document.getElementById('architectSwitch').click(); return entry; };
  const REPORT = '<h1>Regime C is not distinguishable from regime A on like-for-like soil</h1>' +
    '<p>On plot means within soil type, regime C yields 0.112 t/ha against regime A (95% interval -0.071 to 0.290). For the decision, this trial gives no reason to switch.</p>' +
    '<h2>Against the brief</h2><ul><li>Expected: not met - the gap is 0.112 t/ha, interval -0.071 to 0.290</li><li>Would change their mind: cannot tell</li>' +
    '<li>Rainfall differed between the C and A plots: mean rainfall was 421.3 mm on the C plots and 418.9 mm on the A plots</li><li>chance: the interval includes zero</li>' +
    '<li>measurement error: cannot tell - the data does not say how yield was measured</li><li>how the cases compared came to be chosen: the regimes were not assigned at random</li></ul>' +
    '<h2>Did not fit</h2><ul><li>Nothing.</li></ul>';
  return {
    talk() { show(first); },      // the Architect's first turn: what the question states is in the brief, and its first question has two choices
    reading() {      // a message on its way: shown at once, the Architect reading, the composer held
      const entry = show(first);
      document.getElementById('streamOutput').innerHTML = ArchitectUI.build.pane(entry, { sent: 'Switch the clay plots to regime C next season, or keep A.', waiting: true });
      composerLock('The Architect is replying');
    },
    brief() {        // after the conversation: the composer is the conversation's, the switch lit, one line open for typing
      show(framing);
      document.querySelector('#content-brief .ar-line[data-path="expects"] .pen').click();
    },
    checked() { show(checked); },      // what the brief rests on, checked: the round's row, the marks with their facts, keep or change; an explanation proposed, to tick
    answer() {       // the report's part against the brief, as the card in the answer
      document.querySelector('#content-answer .markdown-content').innerHTML = ArchitectUI.dressAnswer(REPORT);
      activateTab('answer');
    }
  };
})();
