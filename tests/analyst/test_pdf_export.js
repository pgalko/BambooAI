// The PDF export's top section (2026-10-17): the head the analyst writes for the finished report, the question whole, the
// data line, the day - built by a pure model in pdf-export.js, tested here in node.
//     node tests/analyst/test_pdf_export.js
const fs = require('fs'); const path = require('path');
const results = [];
function check(name, ok, detail) { results.push([name, !!ok, detail]); }
const m = require(path.join(__dirname, '..', '..', 'web_app', 'static', 'js', 'pdf-export.js'));
const now = new Date(2026, 9, 17, 10, 0, 0);
const day = now.toLocaleDateString(undefined, { year: 'numeric', month: 'long', day: 'numeric' });
const question = 'Across the whole window, compare two readings of intensity ride by ride: the share of time above VT1 in one custom set and the share above Endurance in another, and say where they disagree most and why - a question long enough that the old export cut it at two hundred characters and lost its end.';
const head = { title: 'Ventilation ran ahead of power only before December 2025', lead: 'Two readings of intensity were compared ride by ride across a year; they disagree only in October and November 2025, by about 86 points.',
               question, data: 'Intervals.icu · 2025-10-18 to 2026-10-16 · 307 activities · activity summary, wellness, context, planned workouts, rider profile, custom zone times', mode: 'deep', replay: 'reproduced', cells: 19, prepared: '2026-10-17', chain_id: 7 };
const full = m.pdfHeadModel({ queryText: question, reportHead: head, summaryViewMode: 'technical' }, now);
check('with a head: the kicker, the title the analyst wrote, the lead, then the question as understood, whole (not cut at 200), the data line, and the Prepared row with the day, the mode and the replay\'s verdict',
  full.kicker === 'Analysis report' && full.title === head.title && full.lead === head.lead && full.rows.length === 3 && full.rows[0][0] === 'Question' && full.rows[0][1] === question && question.length > 200
  && full.rows[1][0] === 'Data' && full.rows[1][1] === head.data && full.rows[2][0] === 'Prepared' && full.rows[2][1] === day + ' with BambooAI · Deep mode · every number re-computed from the recorded cells and reproduced', JSON.stringify(full));
const plain = m.pdfHeadModel({ queryText: question, reportHead: head, summaryViewMode: 'simplified' }, now);
check('the plain-language view says so in the Prepared row', plain.rows[2][1].endsWith(' · plain-language version'));
const differed = m.pdfHeadModel({ queryText: question, reportHead: Object.assign({}, head, { replay: 'differed', mode: '' }) }, now);
check('a replay that differed is said as such; no mode, no mode word', differed.rows[2][1] === day + ' with BambooAI · the re-computation differed from the report - read the CHECK lines');
const bare = m.pdfHeadModel({ queryText: 'What did he write about tired legs in August?' }, now);
check('without a head (an older chain, a rewrite without the lines): the question is the title, no Question row, no lead, the Prepared row alone',
  bare.title === 'What did he write about tired legs in August?' && bare.lead === '' && bare.rows.length === 1 && bare.rows[0][0] === 'Prepared' && bare.rows[0][1] === day + ' with BambooAI', JSON.stringify(bare));
const follow = m.pdfHeadModel({ queryText: 'Extend to 45 terms', reportHead: { title: 'The first 45 Fibonacci numbers, plotted', lead: 'L', question: 'extend the earlier Fibonacci plot to 45 terms', data: 'a dataset of 20 rows' } }, now);
check('a follow-up: the Question row is the question as the analyst understood it - whole on its own - not the typed fragment, and nothing of the thread\'s earlier questions',
  follow.rows.map(r => r[0]).join(',') === 'Question,Data,Prepared' && follow.rows[0][1] === 'extend the earlier Fibonacci plot to 45 terms' && !JSON.stringify(follow).includes('Extend to 45 terms'), JSON.stringify(follow.rows));
const none = m.pdfHeadModel({ queryText: 'No query' }, now);
check('nothing at all: "Analysis report" is the title', none.title === 'Analysis report' && none.rows.length === 1);
const partial = m.pdfHeadModel({ queryText: 'Q?', reportHead: { title: '', lead: 'A lead.', question: 'Q?', data: 'a.csv' } }, now);
check('a head without a title: the question is the title and the lead and data still show', partial.title === 'Q?' && partial.lead === 'A lead.' && partial.rows.map(r => r[0]).join(',') === 'Data,Prepared');
const html = m.renderPdfHead(m.pdfHeadModel({ queryText: 'Q <b> & "x"', reportHead: { title: 'T <i>', lead: 'L', question: 'Q <b> & "x"', data: 'D' } }, now));
check('the render: kicker, h1, lead, the meta rows - every value escaped',
  html.startsWith('<div class="pdf-kicker">Analysis report</div><h1>T &lt;i&gt;</h1><p class="pdf-lead">L</p><div class="pdf-meta"><div><b>Question</b>Q &lt;b&gt; &amp; &quot;x&quot;</div><div><b>Data</b>D</div><div><b>Prepared</b>'), html);
check('the file name the browser offers is the title without the characters a name cannot carry, at most 120', m.pdfFileTitle('A title: with / bad * chars?') === 'A title with bad chars' && m.pdfFileTitle('x'.repeat(200)).length === 120 && m.pdfFileTitle('') === '');
// the plumbing: the head rides as a top-level key of the stream, is kept with the chain's record through save, restore and reload,
// and the export sets the page's title to the report's for the print dialog, restoring it after
const qp = fs.readFileSync(path.join(__dirname, '..', '..', 'web_app', 'static', 'js', 'query-processing.js'), 'utf8');
const wm = fs.readFileSync(path.join(__dirname, '..', '..', 'web_app', 'static', 'js', 'workflow-management.js'), 'utf8');
const pe = fs.readFileSync(path.join(__dirname, '..', '..', 'web_app', 'static', 'js', 'pdf-export.js'), 'utf8');
const app = fs.readFileSync(path.join(__dirname, '..', '..', 'web_app', 'app.py'), 'utf8');
const wom = fs.readFileSync(path.join(__dirname, '..', '..', 'bambooai', 'web_output_manager.py'), 'utf8');
check('the stream: the head is a top-level key handled before the generic tab branch, keyed to its chain; an answer of another chain drops it; the record carries reportHead through the new chain shell, the saved response, the restore and the save payload; the load route returns it; the output manager sends it before the answer',
  qp.includes("} else if (data.report_head) {") && qp.indexOf("data.report_head") < qp.indexOf("} else if (data.type && data.type !== 'end' && data.type !== 'id') {")
  && qp.includes("currentData.reportHead = Object.assign({}, data.report_head, { chain_id: data.chain_id || null });") && qp.includes("if (currentData.reportHead && String(currentData.reportHead.chain_id) !== String(data.chain_id)) currentData.reportHead = null;")
  && qp.includes("reportHead: chainData.reportHead || null") && wm.includes("technicalAnswer: null, reportHead: null });") && wm.includes("reportHead: data.reportHead || null,") && wm.includes("currentData.reportHead = response.reportHead || null;")
  && app.includes("'reportHead': chain_data.get('reportHead'),") && wom.replace(/\r/g, '').includes("self.output_queue.put(json.dumps({'report_head': report_head, 'chain_id': chain_id}))") && wom.indexOf("'report_head': report_head") < wom.indexOf("('answer', answer),"));
check('the export: the head model builds the top section, the page title becomes the report\'s title for the print dialog and is restored after; the old 200-character cut is gone',
  pe.includes("headerDiv.innerHTML = renderPdfHead(headModel);") && pe.includes("document.title = pdfFileTitle(headModel.title) || pageTitle;") && pe.includes("document.title = pageTitle;") && !pe.includes("substring(0, 200)") && !pe.includes("Generated: ${new Date().toLocaleString()}"));
let fails = 0; for (const [n, ok, d] of results) { console.log((ok ? '  ok   ' : '  FAIL ') + n + (ok ? '' : '  <- ' + (d || ''))); if (!ok) fails++; }
console.log(`\n${results.length - fails} passed, ${fails} failed`); process.exit(fails ? 1 : 0);
