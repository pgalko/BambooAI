// The gallery's Architect states (tools/render_gallery.py; docs/ARCHITECT_DESIGN.md §2.11-§2.15, §2.17, §3.7): the
// Architect's first question, its reply awaited, a brief after the conversation - the Architect's wording of the question
// waiting to be taken, a line being changed by hand - what the brief rests on checked against the data with an
// explanation proposed, a report against a brief, the next questions under a finished analysis, and the saved analyses -
// being read, and what they hold in the brief. An invented field trial, as the stack's scenario has it.
window.galleryArchitect = (function () {
  const Q = 'Is regime C worth switching to from regime A?';
  const WORDED = 'On plot means of yield, is regime C above regime A within each soil type? Give the gap for each soil type with its interval, and say whether it reaches 0.3 t/ha.';
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
                            you('C yields at least 0.3 t/ha more than A.'),
                            said('I have worded it as the gap between the two regimes within each soil type. Is that what you mean?', { wording: WORDED, v: 3, call: 4 })], calls: 4 };
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
  // the saved analyses: two passages found, the first ticked by the coach; and the reading that found them, in flight
  const PASSAGES = [{ thread: '1763100000', run: '1763100040', when: '2026-10-28', question: 'Is regime C above regime A on like-for-like soil?', where: 'report',
                      passage: 'On plot means within soil type, regime C yields 0.112 t/ha against regime A (95% interval -0.071 to 0.290).',
                      note: 'The same comparison, on the plots of the season before.', marks: 'picked', data: 'field_trial.csv', period: '2025-03-01 to 2025-10-31', accepted: true },
                    { thread: '1763100000', run: '1763100052', when: '2026-10-29', question: 'Is regime C above regime A on clay alone?', where: 'report',
                      passage: 'On clay the gap is 0.242 t/ha, interval 0.031 to 0.455.', note: 'One soil type of the same trial.', marks: 'alongside', data: 'field_trial.csv', period: '2025-03-01 to 2025-10-31',
                      person: 'First Person', other: true, accepted: false }];
  const READ = { who: 'memory', found: PASSAGES.map(x => ({ id: x.thread + '/' + x.run, when: x.when, question: x.question, where: x.where, quote: x.passage, note: x.note })),
                 across: { topic: 'How the gap was taken', groups: [{ label: 'within soil type', runs: [{}, {}] }, { label: 'across all plots', runs: [{}] }] },
                 of: 12, read: 9, dropped: 0, failed: '', secs: 38.2, cost: 0.06 };
  const LOOKING = [you('C yields at least 0.3 t/ha more than A.'), said('I am looking in your saved analyses.', { v: 3, call: 4 })];
  const looking = { versions: [V1, V2, { n: 3, by: 'architect', why: 'answer', changed: ['expects'], brief: ASKED }], turns: LOOKING, calls: 4, saved: 12 };
  const remembered = { versions: looking.versions.concat([
                         { n: 4, by: 'architect', why: 'memory', changed: ['saved.0', 'saved.1'], brief: Object.assign({}, ASKED, { saved: PASSAGES.map(x => Object.assign({}, x, { accepted: false })) }) },
                         { n: 5, by: 'person', changed: ['saved.0'], brief: Object.assign({}, ASKED, { saved: PASSAGES }) }]),
                       turns: LOOKING.concat([Object.assign({ v: 4 }, READ),
                                              said('Your saved analyses hold two passages on this: tick the ones the analysis should test. The brief is ready: start the analysis, or change a line.', { v: 4, call: 5 })]),
                       calls: 5, saved: 12 };
  const entryOf = f => ({ status: 'framing', chain_id: 1763203380, thread_id: 1763203300, parentChainId: null, queryText: Q, tabContent: '', contentOutput: '', streamOutput: '', taskContents: {}, framing: f });
  const show = f => { const entry = entryOf(f); responses = [entry]; currentResponseIndex = 0; loadResponseContent(entry); updateNavigationButtons(); document.getElementById('architectSwitch').click(); return entry; };
  const REPORT = '<h1>Regime C is not distinguishable from regime A on like-for-like soil</h1>' +
    '<p>On plot means within soil type, regime C yields 0.112 t/ha against regime A (95% interval -0.071 to 0.290). For the decision, this trial gives no reason to switch.</p>' +
    '<h2>Against the brief</h2><ul><li>Expected: not met - the gap is 0.112 t/ha, interval -0.071 to 0.290</li><li>Would change their mind: cannot tell</li>' +
    '<li>Rainfall differed between the C and A plots: mean rainfall was 421.3 mm on the C plots and 418.9 mm on the A plots</li><li>chance: the interval includes zero</li>' +
    '<li>measurement error: cannot tell - the data does not say how yield was measured</li><li>how the cases compared came to be chosen: the regimes were not assigned at random</li></ul>' +
    '<h2>Did not fit</h2><ul><li>Nothing.</li></ul>';
  // the questions that could follow: one set, its first question run
  const MISFIT = { kind: 'misfit', text: 'The gap is not the same on every soil: 0.242 t/ha on clay, 0.149 on sand [cell 2]' };
  const NEXT = { level: 'emergence', cost: 0.021, chain: 1763203390, questions: [
    { title: 'The clay plots', text: 'Is regime C above regime A on clay alone, on plot means of yield?', from: [MISFIT], ran: '1763203400' },
    { title: 'Rain in the dry seasons', text: 'Does the gap between regime C and regime A hold in the three driest seasons?', from: [{ kind: 'check', text: 'Rainfall differed between the C and A plots: mean rainfall was 421.3 mm on the C plots and 418.9 mm on the A plots' }] },
    { title: 'What it rests on', text: 'Did the C plots get more rain than the A plots in any single season?', from: [{ kind: 'anchor', text: RAIN + ' (does not hold: ' + RAIN_FACT + ')' }] },
    { title: 'The answer and the soil', text: 'Is the gap within soil type the same in early and late seasons?', from: [{ kind: 'found', text: 'On plot means within soil type, regime C yields 0.112 t/ha against regime A.' }, MISFIT] }] };
  return {
    next() {         // under a finished analysis' closing card: a set of questions - where each comes from, one already run - and the list of levels open by the button
      const pane = document.getElementById('streamOutput');
      responses = [{ chain_id: 1763203380, thread_id: 1763203300, parentChainId: null, queryText: Q, streamOutput: '' }]; currentResponseIndex = 0;      // the chain on screen is a finished one
      NextQuestionsUI.dress(pane);
      pane.querySelector('.sp-stream').insertAdjacentHTML('beforeend', NextQuestionsUI.build.set(NEXT, 0));
      pane.scrollTop = pane.scrollHeight;
      pane.querySelector('[data-nq="open"]').click();
    },
    talk() { show(first); },      // the Architect's first turn: what the question states is in the brief, and its first question has two choices
    reading() {      // a message on its way: shown at once, the Architect reading, the composer held
      const entry = show(first);
      document.getElementById('streamOutput').innerHTML = ArchitectUI.build.pane(entry, { sent: 'Switch the clay plots to regime C next season, or keep A.', waiting: true });
      composerLock('The Architect is replying');
    },
    brief() {        // after the conversation: the Architect's wording waits under the question, the switch lit, one line open for typing
      show(framing);
      document.querySelector('#content-brief .ar-line[data-path="expects"] .pen').click();
    },
    checked() { show(checked); },      // what the brief rests on, checked: the round's row, the marks with their facts, keep or change; an explanation proposed, to tick
    saved() { show(remembered); },     // what the saved analyses hold: the reading's row, the passages in the brief - one ticked - and the button that has them read once more
    saving() {       // the saved analyses being read: the row says how far the second model is, with Skip; the composer held
      const entry = show(looking);
      document.getElementById('streamOutput').innerHTML = ArchitectUI.build.pane(entry, { waiting: true, saved: { read: 5, of: 12 } });
      composerLock('Your saved analyses are being read');
    },
    answer() {       // the report's part against the brief, as the card in the answer
      document.querySelector('#content-answer .markdown-content').innerHTML = ArchitectUI.dressAnswer(REPORT);
      activateTab('answer');
    }
  };
})();
