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
const head = { title: 'Ventilation ran ahead of power only before December 2025',
               question, data: 'Intervals.icu · 2025-10-18 to 2026-10-16 · 307 activities · activity summary, wellness, context, planned workouts, rider profile, custom zone times', mode: 'deep', replay: 'reproduced', cells: 19, prepared: '2026-10-17', chain_id: 7 };
const full = m.pdfHeadModel({ queryText: 'typed', reportHead: head, summaryViewMode: 'technical' }, now);
check('with a head: the kicker, the report\'s title, no lead, then the question as understood (whole, not cut at 200), the data line, and the Prepared row with the day, the mode and the replay\'s verdict',
  full.kicker === 'Analysis report' && full.title === head.title && !('lead' in full) && full.rows.length === 3 && full.rows[0][0] === 'Question' && full.rows[0][1] === question && question.length > 200
  && full.rows[1][0] === 'Data' && full.rows[1][1] === head.data && full.rows[2][0] === 'Prepared' && full.rows[2][1] === day + ' with BambooAI · Deep mode · every number re-computed from the recorded cells and reproduced', JSON.stringify(full));
const plain = m.pdfHeadModel({ queryText: question, reportHead: head, summaryViewMode: 'simplified' }, now);
check('the plain-language view says so in the Prepared row', plain.rows[2][1].endsWith(' · plain-language version'));
const differed = m.pdfHeadModel({ queryText: question, reportHead: Object.assign({}, head, { replay: 'differed', mode: '' }) }, now);
check('a replay that differed is said as such; no mode, no mode word', differed.rows[2][1] === day + ' with BambooAI · the re-computation differed from the report - read the CHECK lines');
const bare = m.pdfHeadModel({ queryText: 'What did he write about tired legs in August?' }, now);
check('without a head (an older chain): the typed question is the title, no Question row, the Prepared row alone',
  bare.title === 'What did he write about tired legs in August?' && bare.rows.length === 1 && bare.rows[0][0] === 'Prepared' && bare.rows[0][1] === day + ' with BambooAI', JSON.stringify(bare));
const follow = m.pdfHeadModel({ queryText: 'Extend to 45 terms', reportHead: { title: 'The first 45 Fibonacci numbers, plotted', question: 'extend the earlier Fibonacci plot to 45 terms', data: 'a dataset of 20 rows' } }, now);
check('a follow-up: the Question row is the question as the analyst understood it - whole on its own - not the typed fragment, and nothing of the thread\'s earlier questions',
  follow.rows.map(r => r[0]).join(',') === 'Question,Data,Prepared' && follow.rows[0][1] === 'extend the earlier Fibonacci plot to 45 terms' && !JSON.stringify(follow).includes('Extend to 45 terms'), JSON.stringify(follow.rows));
const none = m.pdfHeadModel({ queryText: 'No query' }, now);
check('nothing at all: "Analysis report" is the title', none.title === 'Analysis report' && none.rows.length === 1);
const partial = m.pdfHeadModel({ queryText: 'typed', reportHead: { title: '', question: 'as understood', data: 'a.csv' } }, now);
check('a head without a title (the report opened without its line): the question as understood is the title, the data still shows', partial.title === 'as understood' && partial.rows.map(r => r[0]).join(',') === 'Data,Prepared');
const html = m.renderPdfHead(m.pdfHeadModel({ queryText: 'typed', reportHead: { title: 'T <i>', question: 'Q <b> & "x"', data: 'D' } }, now));
check('the render: kicker, h1, the meta rows - every value escaped, no lead',
  html.startsWith('<div class="pdf-kicker">Analysis report</div><h1>T &lt;i&gt;</h1><div class="pdf-meta"><div><b>Question</b>Q &lt;b&gt; &amp; &quot;x&quot;</div><div><b>Data</b>D</div><div><b>Prepared</b>') && !html.includes('pdf-lead'), html);
// the body's own title line comes off (the head carries it); a heading further down, or a different one, stays
const { Element } = require(path.join(__dirname, 'minidom.js'));
const body1 = new Element('div'); body1.innerHTML = '<h1>Two hard weeks.</h1><h2>What this answers</h2><p>text</p>';
const body2 = new Element('div'); body2.innerHTML = '<p>lead</p><h1>Two hard weeks</h1>';
const body3 = new Element('div'); body3.innerHTML = '<h1>Another heading</h1><p>text</p>';
check('dropBodyTitle: the first element removed when it is an h1 reading as the title (a full stop or folded spaces aside); a body opening otherwise, or with another h1, is left alone',
  m.dropBodyTitle(body1, 'Two hard weeks') === true && body1.innerHTML === '<h2>What this answers</h2><p>text</p>' && m.dropBodyTitle(body2, 'Two hard weeks') === false && body2.children.length === 2
  && m.dropBodyTitle(body3, 'Two hard weeks') === false && body3.children.length === 2 && m.dropBodyTitle(null, 'x') === false, body1.innerHTML);
// the figures for print: white paper, dark text, light grid, the title broken into lines that stay whole, annotations readable
const L = m.printLayout({ title: { text: 'A very long figure title that would be clipped at the edge of the exported image because plotly does not wrap titles at all, ever' }, xaxis: { title: { text: 'x' } }, yaxis: {}, annotations: [{ text: 'a', font: { color: '#fff' } }], template: { layout: { paper_bgcolor: '#000' } }, legend: { font: { color: '#fff' } } });
check('printLayout: the page\'s dark template dropped for white paper and dark text, the axes\' grid light, the title in lines of at most 90 characters with the top margin to fit, annotations and legend readable; a layout without a title untouched there',
  L.paper_bgcolor === '#ffffff' && L.plot_bgcolor === '#ffffff' && L.font.color === '#333333' && !('template' in L) && L.xaxis.gridcolor === '#e6e6e6' && L.xaxis.title.font.color === '#333333'
  && L.title.text.split('<br>').length === 2 && L.title.text.split('<br>').every(s => s.length <= 90) && L.margin.t === 84 && L.annotations[0].font.color === '#333333' && L.legend.font.color === '#333333'
  && !('title' in m.printLayout({ xaxis: {} })) && m.printLayout(null).paper_bgcolor === '#ffffff', JSON.stringify(L).slice(0, 300));
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
check('the print styles carry the citation chips - a quiet pill, not interactive - and the charts are captured on the print layout with a fallback to the page\'s own',
  pe.includes('#pdf-print-container .cite {') && pe.includes('cursor: default;') && pe.includes('#pdf-print-container .cite.doc, #pdf-print-container .cite.ctx {') && pe.includes('#pdf-print-container .cite.fig {')
  && pe.includes('layout: printLayout(plot.element.layout || {})') && pe.includes("imgData = await Plotly.toImage(plot.element, { format: 'png', width: 1000, height: 560, scale: 2 });") && pe.includes('dropBodyTitle(contentClone, headModel.title);'));
check('the export: the head model builds the top section, the page title becomes the report\'s title for the print dialog and is restored after; the old 200-character cut is gone',
  pe.includes("headerDiv.innerHTML = renderPdfHead(headModel);") && pe.includes("document.title = pdfFileTitle(headModel.title) || pageTitle;") && pe.includes("document.title = pageTitle;") && !pe.includes("substring(0, 200)") && !pe.includes("Generated: ${new Date().toLocaleString()}"));
let fails = 0; for (const [n, ok, d] of results) { console.log((ok ? '  ok   ' : '  FAIL ') + n + (ok ? '' : '  <- ' + (d || ''))); if (!ok) fails++; }
console.log(`\n${results.length - fails} passed, ${fails} failed`); process.exit(fails ? 1 : 0);
