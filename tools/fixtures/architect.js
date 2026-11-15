// The gallery's Architect states (tools/render_gallery.py; docs/ARCHITECT_DESIGN.md §2.11): a brief written by hand, and a
// report against one. An invented field trial, as the stack's scenario has it.
window.galleryArchitect = (function () {
  const Q = 'Is regime C worth switching to from regime A?';
  const BRIEF = { question: Q, decision: 'Switch the clay plots to regime C next season, or keep A.', thinks: 'C does better than A.',
    rests_on: [{ text: 'The C plots looked greener last season.', source: 'person', mark: '' }], expects: 'C yields at least 0.3 t/ha more than A.',
    also_check: [{ text: 'Rainfall differed between the C and A plots.' }], fixed: { comparison: 'regime C against regime A, within soil type', measure: 'yield, plot means' } };
  const framing = { versions: [{ n: 1, by: 'person', changed: [], brief: { question: Q } }, { n: 2, by: 'person', changed: ['fixed.measure'], brief: BRIEF }] };
  const REPORT = '<h1>Regime C is not distinguishable from regime A on like-for-like soil</h1>' +
    '<p>On plot means within soil type, regime C yields 0.112 t/ha against regime A (95% interval -0.071 to 0.290). For the decision, this trial gives no reason to switch.</p>' +
    '<h2>Against the brief</h2><ul><li>Expected: not met - the gap is 0.112 t/ha, interval -0.071 to 0.290</li><li>Would change their mind: cannot tell</li>' +
    '<li>Rainfall differed between the C and A plots: mean rainfall was 421.3 mm on the C plots and 418.9 mm on the A plots</li><li>chance: the interval includes zero</li>' +
    '<li>measurement error: cannot tell - the data does not say how yield was measured</li><li>how the cases compared came to be chosen: the regimes were not assigned at random</li></ul>' +
    '<h2>Did not fit</h2><ul><li>Nothing.</li></ul>';
  return {
    brief() {        // a brief not yet run: the composer held, the switch lit, one line open for typing
      const entry = { status: 'framing', chain_id: 1763203380, thread_id: 1763203300, parentChainId: null, queryText: Q, tabContent: '', contentOutput: '', streamOutput: '', taskContents: {}, framing };
      responses = [entry]; currentResponseIndex = 0; loadResponseContent(entry); updateNavigationButtons();
      document.getElementById('architectSwitch').click();
      document.querySelector('#content-brief .ar-line[data-path="expects"] .pen').click();
    },
    answer() {       // the report's part against the brief, as the card in the answer
      document.querySelector('#content-answer .markdown-content').innerHTML = ArchitectUI.dressAnswer(REPORT);
      activateTab('answer');
    }
  };
})();
