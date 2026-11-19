// The gallery's Architect states (tools/render_gallery.py; docs/ARCHITECT_DESIGN.md §2.11-§2.15, §2.18, §2.19, §3.7): the
// Architect's first question, the parts + Add offers, its reply awaited, a brief after the conversation - the question as
// the Architect worded it, a line being changed by hand - an earlier version on screen, what the brief rests on checked
// against the data with an explanation proposed, a report against a brief, the next questions under a finished analysis,
// the saved analyses - being read, and what was found with the one the brief builds on - the figures: as grey
// windows while their draft is drawn, and the drafts drawn (§2.20; the plots are tools/fixtures/drafts.json) - and
// the question's check before an analysis starts: the question being read, and the words the Analyst could not
// place with the Architect's wording after it (§2.22). An invented field trial, as the stack's scenario has it.
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
  // the figures and their draft (§2.19, §2.20): what the data will give, on made-up numbers; the target, which follows from its rule, computed
  const FIGURES = [{ title: 'Yield by season, regime C and regime A', kind: 'line', x: 'season', y: 'yield, t/ha', note: 'Whether the gap holds from season to season.',
                     series: [{ name: 'regime C' }, { name: 'regime A' }] },
                   { title: 'The target: 5 percent more each season', kind: 'line', x: 'season', y: 'yield, t/ha', note: 'What a rise of 5 percent a season from 4.0 t/ha comes to.',
                     series: [{ name: 'the target' }] }];
  const described = { versions: [V1, V2, { n: 3, by: 'architect', why: 'answer', changed: ['decision', 'figures.0', 'figures.1'], keys: ['d1', 'd2'],
                                          brief: { question: Q, decision: 'Switch the clay plots to regime C next season, or keep A.', fixed: { comparison: 'regime C against regime A' }, figures: FIGURES } }],
                     turns: [ASK, you('Switch the clay plots to regime C next season, or keep A. Show me what the figures will look like.'),
                             said('A draft is being drawn. Is that what you want to see?', { choices: ['Yes, that is it', 'Change something'], v: 3, call: 2 })], calls: 2 };
  const drafted = Object.assign({}, described, { drafts: { d1: { basis: 'made up' }, d2: { basis: 'computed' } }, draft_calls: 1,
                    turns: described.turns.concat([{ who: 'draft', drawn: [{ title: FIGURES[0].title, basis: 'made up' }, { title: FIGURES[1].title, basis: 'computed' }], v: 3, secs: 7.4, cost: 0.003, call: 1 }]) });
  const framing = { versions: [V1, V2, { n: 3, by: 'architect', why: 'answer', changed: ['expects'], brief: Object.assign({}, BRIEF, { fixed: { comparison: 'regime C against regime A' }, also_check: undefined }) },
                               { n: 4, by: 'person', changed: ['fixed.measure'], brief: BRIEF },
                               { n: 5, by: 'architect', why: 'answer', changed: ['question'], brief: Object.assign({}, BRIEF, { question: WORDED }) }],      // the question as the Architect worded it: written at once
                    turns: [ASK, you('Switch the clay plots to regime C next season, or keep A.'), said('What do you think is going on, and what makes you think so?', { v: 2, call: 2 }),
                            you('C does better than A because the C plots looked greener last season.'), said('What do you expect to see?', { v: 2, call: 3 }),
                            you('C yields at least 0.3 t/ha more than A.'),
                            said('I have worded it as the gap between the two regimes within each soil type. Is that what you mean?', { wording: WORDED, v: 5, call: 4 })], calls: 4 };
  // the question's check (§2.22): the coach worded the question by hand so that it points to an analysis of another day; the reader could not place that, and the Architect worded it again
  const SOIL = ' Take the soil types from the soil column.';
  const pointed = { versions: framing.versions.concat([{ n: 6, by: 'person', changed: ['question'], brief: Object.assign({}, BRIEF, { question: WORDED + ' Take the soil types as in the analysis of 2 March.' }) }]),
                    turns: framing.turns, calls: 4 };
  const unplaced = { versions: pointed.versions.concat([{ n: 7, by: 'architect', why: 'answer', changed: ['question'], brief: Object.assign({}, BRIEF, { question: WORDED + SOIL }) }]),
                     turns: framing.turns.concat([{ who: 'reader', missing: ['the analysis of 2 March'], v: 6, cost: 0.002, call: 1, secs: 2.6 },
                                                  said('The question pointed to an analysis the Analyst is not given. It now says where the soil types come from: the soil column.', { wording: WORDED + SOIL, v: 7, call: 5 })]),
                     calls: 5, read: [6, 7] };
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
  // the saved analyses: two found by a reading, the first built on by the coach's answer; and the reading that found them, in flight
  const PASSAGES = [{ thread: '1763100000', run: '1763100040', when: '2026-10-28', question: 'Is regime C above regime A on like-for-like soil?', where: 'report',
                      passage: 'On plot means within soil type, regime C yields 0.112 t/ha against regime A (95% interval -0.071 to 0.290).',
                      note: 'The same comparison, on the plots of the season before.', marks: 'picked', data: 'field_trial.csv', period: '2025-03-01 to 2025-10-31' },
                    { thread: '1763100000', run: '1763100052', when: '2026-10-29', question: 'Is regime C above regime A on clay alone?', where: 'report',
                      passage: 'On clay the gap is 0.242 t/ha, interval 0.031 to 0.455.', note: 'One soil type of the same trial.', marks: 'alongside', data: 'field_trial.csv', period: '2025-03-01 to 2025-10-31',
                      person: 'First Person', other: true }];
  const READ = { who: 'memory', found: PASSAGES.map(x => ({ id: x.thread + '/' + x.run, when: x.when, question: x.question, where: x.where, quote: x.passage, note: x.note })),
                 across: { topic: 'How the gap was taken', groups: [{ label: 'within soil type', runs: [{}, {}] }, { label: 'across all plots', runs: [{}] }] },
                 of: 12, read: 9, dropped: 0, failed: '', secs: 38.2, cost: 0.06 };
  const LOOKING = [you('C yields at least 0.3 t/ha more than A.'), said('I am looking in your saved analyses.', { v: 3, call: 4 })];
  const looking = { versions: [V1, V2, { n: 3, by: 'architect', why: 'answer', changed: ['expects'], brief: ASKED }], turns: LOOKING, calls: 4, saved: 12 };
  const remembered = { versions: looking.versions.concat([
                         { n: 4, by: 'architect', why: 'answer', changed: ['saved.0'], brief: Object.assign({}, ASKED, { saved: [Object.assign({ accepted: true }, PASSAGES[0])] }) }]),
                       found: PASSAGES,
                       turns: LOOKING.concat([Object.assign({ v: 3 }, READ),
                                              said('Your saved analyses hold two on this. Build on one of them, or go another way?', { v: 3, call: 5 }),
                                              you('Build on the one on like-for-like soil.'),
                                              said('Done: the Analyst gets that analysis, and can open it. The brief is ready: start the analysis, or change a line.', { v: 4, call: 6 })]),
                       calls: 6, saved: 12 };
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
    next(shown) {    // the panel the Next questions button opens in a finished analysis' closing card: what the questions are and the five ways to go - one has questions already, and
      const pane = document.getElementById('streamOutput');      // says how many; `shown`: that way's questions in the list's place - what each starts from, one already run
      responses = [{ chain_id: 1763203380, thread_id: 1763203300, parentChainId: null, queryText: Q, streamOutput: '' }]; currentResponseIndex = 0;      // the chain on screen is a finished one
      NextQuestionsUI.dress(pane);
      const button = pane.querySelector('[data-nq="open"]');
      button.click();
      pane.querySelector('.nq-sets').insertAdjacentHTML('beforeend', NextQuestionsUI.build.set(NEXT, 0));
      button.click(); button.click();                            // shut and opened again: the list is drawn with the set in it
      if (shown) pane.querySelector('.nq-row .n').click();
      pane.scrollTop = pane.scrollHeight;
    },
    talk() { show(first); },      // the Architect's first turn: what the question states is in the brief, and its first question has two choices
    adding() {       // + Add, open: the parts the brief does not show, each under its name
      show(first);
      document.querySelector('#content-brief [data-ar="more"]').click();
    },
    reading() {      // a message on its way: shown at once, the Architect reading, the composer held
      const entry = show(first);
      document.getElementById('streamOutput').innerHTML = ArchitectUI.build.pane(entry, { sent: 'Switch the clay plots to regime C next season, or keep A.', waiting: true });
      composerLock('The Architect is replying');
    },
    brief() {        // after the conversation: the question as the Architect worded it - the row that says so - the switch lit, one line open for typing
      show(framing);
      document.querySelector('#content-brief .ar-line[data-path="expects"] .pen').click();
    },
    version() {      // the arrow back, twice: an earlier version on screen, and Start analysis names it
      show(framing);
      for (let k = 0; k < 2; k++) document.querySelector('#content-brief [data-ar="step"][data-step="-1"]').click();
    },
    drawing() {      // the reply stands, a grey window to each figure while its draft is drawn: the row that says so, the composer held
      const entry = show(described);
      document.getElementById('streamOutput').innerHTML = ArchitectUI.build.pane(entry, { waiting: true, drawing: true });
      document.getElementById('content-brief').innerHTML = ArchitectUI.build.brief(entry.framing, { chain: entry.chain_id, thread: entry.thread_id, state: 'framing', drawing: true });
      composerLock('A draft of the figures is being drawn');
    },
    draft() { show(drafted); },        // the drafts drawn: the first on made-up numbers, with those words across it; the second computed; the row that says how many
    checking() {     // Start analysis pressed: the question is being read as the Analyst will read it - the row that says so, the composer held
      const entry = show(pointed);
      document.getElementById('streamOutput').innerHTML = ArchitectUI.build.pane(entry, { waiting: true, checking: true });
      composerLock('The question is being read as the Analyst will read it');
    },
    unplaced() { show(unplaced); },    // the Analyst could not place something: the row that says which words, the Architect's reply under it, the question worded again - one more version
    checked() { show(checked); },      // what the brief rests on, checked: the round's row, the marks with their facts, keep or change; an explanation proposed, to tick
    saved() { show(remembered); },     // what the saved analyses hold: the reading's row with the analyses found under it, each in full under the brief, and the one the brief builds on
    saving() {       // the saved analyses being read: the row says how far the second model is, with Skip; the composer held
      const entry = show(looking);
      document.getElementById('streamOutput').innerHTML = ArchitectUI.build.pane(entry, { waiting: true, saved: { read: 5, of: 12 } });
      composerLock('Your saved analyses are being read');
    },
    answer() {       // the answer of a run under a brief (0312): what its report says against the brief is not in it
      document.querySelector('#content-answer .markdown-content').innerHTML = ArchitectUI.cutAnswer(REPORT).html;
      activateTab('answer');
    },
    outcome() {      // it stands at the foot of that run's Brief tab: how it turned out
      createOrUpdateTab('brief', ArchitectUI.build.brief(checked, { chain: 1763203380, thread: 1763203300, state: 'run' }));
      ArchitectUI.turnedOut(document.getElementById('contentOutput'), ArchitectUI.cutAnswer(REPORT).against);
      activateTab('brief');
    }
  };
})();
