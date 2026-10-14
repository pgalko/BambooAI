// The one Context pill (2026-10-14): the passages and the codes of a load stacked under a single pill in the top bar, as
// the documents are - the label with the days and a spinner while the pass runs behind the load, the hover list naming the
// two files (a click previews either in the Data tab) and the pass's line once it has ended, the pill's x removing both.
// Run: node tests/analyst/test_context_pill.js
'use strict';
const path = require('path');
const { makeDocument } = require(path.join(__dirname, 'minidom.js'));
const doc = makeDocument(); global.document = doc;
const posts = [];
global.window = { authService: { fetch: async (url, opts) => { posts.push([url, opts && opts.body ? JSON.parse(opts.body) : null]); return { ok: true, json: async () => ({}) }; } }, auxiliaryDatasetCount: 2 };
const previews = [];
global.showDatasetPreview = (url, body, kind) => { previews.push([url, body, kind]); };
const made = [];
global.createOrUpdateDatasetPill = (id, text, type, state, loading, ident) => { made.push([id, text, type, ident]); const d = doc.createElement('div'); d.setAttribute('id', id); d.className = 'dataset-status-pill ' + type + '-dataset-pill ' + state; d.innerHTML = '<span class="dataset-pill-content"><span>' + text + '</span></span>'; doc.getElementById('datasetStatusPillsContainer').appendChild(d); };
const host = doc.createElement('div'); host.setAttribute('id', 'datasetStatusPillsContainer'); doc.body.appendChild(host);
const m = require(path.join(__dirname, '..', '..', 'web_app', 'static', 'js', 'integrations', 'intervals.js'));
const results = []; const check = (n, c, d) => results.push([n, !!c, d]);
const info = { start_date: '2026-07-16', end_date: '2026-10-14' };
const NOTES = 'datasets/u/k/context_notes_20260716_to_20261014.csv', CODES = 'datasets/u/k/context_codes_20260716_to_20261014.csv', WELL = 'datasets/u/k/wellness_data_20260716_to_20261014.csv';

const ids = m.createIntervalsAuxiliaryPills([WELL, NOTES], info, { coding: true });
let pill = doc.getElementById('contextPill');
check('a load with context: the wellness file keeps its own pill, the context file goes to the one Context pill (no id returned for it); the auxiliary count moves by two',
      Object.keys(ids).length === 1 && ids[WELL] && made.length === 1 && made[0][1] === 'Auxiliary (Wellness Summary (90 days))' && pill && window.auxiliaryDatasetCount === 4, (ids, made, window.auxiliaryDatasetCount));
check('while the pass runs: the label carries the days and "coding…", the spinner is on, the list names the passages (clickable) and the codes as coding (not clickable); the pill previews the passages on click',
      pill.className === 'dataset-status-pill auxiliary-dataset-pill context-pill success' && pill.querySelector('.dataset-pill-content span').textContent === 'Context (90 days) · coding…' && pill.querySelector('.file-upload-spinner')
      && pill.querySelectorAll('.context-pill-menu .row').length === 2 && pill.querySelectorAll('.context-pill-menu .row')[0].getAttribute('onclick') === "contextPreview('" + NOTES + "')"
      && pill.querySelectorAll('.context-pill-menu .row')[1].className === 'row muted' && pill.querySelectorAll('.context-pill-menu .row')[1].textContent === 'Codescoding…'
      && pill.getAttribute('data-identifier') === NOTES && pill.getAttribute('data-dataset-type') === 'auxiliary' && pill.querySelector('.dataset-pill-content').getAttribute('onclick') === "contextPreview('" + NOTES + "')", pill.outerHTML);
m.contextPillSettle({ status: 'done', line: '201 of 223 coded, 141 rendered into English, 2 codes proposed', codes_path: CODES });
pill = doc.getElementById('contextPill');
const rows = pill.querySelectorAll('.context-pill-menu .row');
check('when the pass ends: the label plain, no spinner, the tooltip the pass\'s line, the codes row clickable, the line as a third row',
      pill.querySelector('.dataset-pill-content span').textContent === 'Context (90 days)' && !pill.querySelector('.file-upload-spinner')
      && pill.querySelector('.dataset-pill-content').getAttribute('title') === 'Context: 201 of 223 coded, 141 rendered into English, 2 codes proposed'
      && rows.length === 3 && rows[1].getAttribute('onclick') === "contextPreview('" + CODES + "')" && rows[2].className === 'row muted line' && rows[2].textContent === '201 of 223 coded, 141 rendered into English, 2 codes proposed', pill.outerHTML);
m.contextPreview(CODES);
check('a row\'s click previews that file in the Data tab through the shared preview', previews.length === 1 && previews[0][0] === '/get_dataset_preview' && previews[0][1].file_path === CODES && previews[0][2] === 'auxiliary', previews);
check('a codes file arriving alone later joins the same pill (the load route\'s completion read again)', m.contextPillAdd([CODES], info, { coding: false, line: 'x' }) === true && doc.querySelectorAll('#contextPill').length === 1 && doc.getElementById('contextPill').querySelectorAll('.context-pill-menu .row').length === 3);
check('a file that is not a context file is not taken', m.contextPillAdd([WELL], info) === false);
m.contextRemove().then(() => {
  check('the pill\'s x removes both files through the auxiliary route and the pill goes; the count moves back by two', posts.length === 2 && posts.every(p => p[0] === '/remove_auxiliary_dataset') && posts.map(p => p[1].file_path).sort().join() === [CODES, NOTES].sort().join() && !doc.getElementById('contextPill') && window.auxiliaryDatasetCount === 2, (posts, window.auxiliaryDatasetCount));
  check('a load without context leaves no Context pill', m.createIntervalsAuxiliaryPills([WELL], info) && !doc.getElementById('contextPill'));
  const fails = results.filter(r => !r[1]);
  results.forEach(r => console.log((r[1] ? '  ok   ' : '  FAIL ') + r[0] + (r[1] ? '' : '  <- ' + String(r[2]).slice(0, 600))));
  console.log('\n' + (results.length - fails.length) + ' passed, ' + fails.length + ' failed');
  process.exit(fails.length ? 1 : 0);
});
