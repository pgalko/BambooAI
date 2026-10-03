// The Documents pill and view (web_app/static/js/documents.js) in node, on the small real DOM the pane suite
// uses, with a scripted authService.fetch. Run: node tests/analyst/test_documents_page.js
'use strict';
const path = require('path');
const { makeDocument } = require(path.join(__dirname, 'minidom.js'));
const doc = makeDocument(); global.document = doc; global.window = global;
const host = doc.createElement('div'); host.setAttribute('id', 'datasetStatusPillsContainer'); doc.body.appendChild(host);
global.currentData = { chain_id: null, thread_id: null };
global.FormData = class { constructor() { this.parts = {}; } append(k, v) { this.parts[k] = v; } };
global.showUploadLimitMessage = msg => { calls.push(['limit', msg]); };

const results = []; const check = (n, c, d) => results.push([n, !!c, d]);
const calls = [];
const docs = [{ id: 'D1', file: 'paper.pdf', type: 'PDF', pages: 12, words: 5400, tables: 3, uploaded_at: '2026-10-03T10:00:00', embedded: null },
              { id: 'D2', file: 'meeting.md', type: 'Markdown', pages: null, words: 3400, tables: 1, uploaded_at: '2026-10-03T10:05:00', embedded: false }];
const units = [{ id: 'D1.1', kind: 'heading', page: 1, text: 'Training Load and Recovery' }, { id: 'D1.2', kind: 'paragraph', page: 1, text: 'Masters athletes <b>kept</b> a steady load.' },
               { id: 'D1.3', kind: 'caption', page: 2, text: 'Table 1. Participant characteristics' },
               { id: 'D1.4', kind: 'table', page: 2, table_no: 1, caption: 'Table 1. Participant characteristics', rows: [['Group', 'n'], ['40-49', '15'], ['50-59', '16']] }];
const json = (status, body) => Promise.resolve({ ok: status < 400, status, json: () => Promise.resolve(body) });
let listing = { thread_id: '1700000001', documents: docs.slice(0, 2), max: 4 };
global.authService = { fetch: (url, opts) => {
    const m = (opts && opts.method) || 'GET'; calls.push([m, url]);
    if (m === 'POST' && url === '/documents/upload') {
        const f = opts.body.parts.file;
        if (f.name.endsWith('.rtf')) return json(400, { message: f.name + ' is not a PDF, Word, Markdown or text file.', thread_id: '1700000009' });
        const d = { id: 'D3', file: f.name, type: 'text', pages: null, words: 12, tables: 0, uploaded_at: '2026-10-03T11:00:00' };
        listing = { thread_id: opts.body.parts.thread_id || '1700000009', documents: listing.documents.concat([d]), max: 4 };
        return json(200, Object.assign({ document: d, message: f.name + ' attached as D3.' }, listing));
    }
    if (m === 'DELETE') { const id = url.split('/').pop(); listing = Object.assign({}, listing, { documents: listing.documents.filter(d => d.id !== id) }); return json(200, Object.assign({ removed: id }, listing)); }
    if (url.endsWith('/map')) return json(200, { map: 'D1 - paper.pdf (PDF, 12 pages, 5,400 words, 3 tables, 1 figure caption)\nOutline: Abstract (p.1)' });
    if (url.endsWith('/text')) return json(200, { doc: 'D1', file: 'paper.pdf', units });
    if (url === '/documents/1700000001') return json(200, listing);
    if (url === '/documents/1700000002') return json(200, { thread_id: '1700000002', documents: [], max: 4 });
    return json(404, { message: 'no' });
} };

require(path.join(__dirname, '..', '..', 'web_app', 'static', 'js', 'documents.js'));
const w = window; const pill = () => doc.getElementById('documentsPill');
const tick = () => new Promise(r => setTimeout(r, 0));

(async () => {
    check('no thread, no documents: no pill', !pill());

    // the page opens a thread with two documents: the pill comes back from the manifest
    currentData.thread_id = 1700000001; await w.documentsSync(); await tick();
    check('a thread with documents: one pill, blue (documents-pill success), "Documents (2/4)"', pill() && pill().className === 'dataset-status-pill documents-pill success' && pill().querySelector('.label').textContent === 'Documents (2/4)', pill() && pill().outerHTML.slice(0, 200));
    const rows = pill().querySelectorAll('.documents-pill-menu .row');
    check('hover list: one row per document - id, file, pages or words, a remove icon', rows.length === 2 && rows[0].querySelector('.id').textContent === 'D1' && rows[0].querySelector('.file').textContent === 'paper.pdf' && rows[0].querySelector('.meta').textContent === '· 12 pages' && rows[1].querySelector('.meta').textContent === '· 3,400 words' && rows[0].querySelector('.rm'), rows.map(r => r.textContent));
    pill().getBoundingClientRect = () => ({ left: 96, bottom: 34 });
    w.documentsMenuPlace(pill());
    check('the hover list is placed under the pill from its rect (fixed, so the pills container cannot clip it)', pill().getAttribute('onmouseenter') === 'documentsMenuPlace(this)' && pill().querySelector('.documents-pill-menu').style.left === '96px' && pill().querySelector('.documents-pill-menu').style.top === '38px', pill().querySelector('.documents-pill-menu').style);
    check('a second sync with the same thread fetches nothing more', (calls.filter(c => c[1] === '/documents/1700000001').length === 1) && (await w.documentsSync(), calls.filter(c => c[1] === '/documents/1700000001').length === 1));

    // upload: the spinner while it parses, then the count; the view opens on the new document
    const p = w.documentsUpload({ name: 'notes.txt' });
    check('while parsing: the loading state with the spinner and "parsing notes.txt…"', pill().className.includes('loading') && pill().querySelector('.label').textContent === 'parsing notes.txt…' && pill().querySelector('.file-upload-spinner'), pill().outerHTML.slice(0, 300));
    const j = await p; await tick();
    check('after: "Documents (3/4)", the thread id sent with the upload, the new document selected in the view', j && j.document.id === 'D3' && pill().querySelector('.label').textContent === 'Documents (3/4)' && calls.some(c => c[0] === 'POST') && doc.getElementById('documentsModal') && doc.getElementById('documentsModal').style.display === 'flex' && w.__documentsState.selected === 'D3', pill().querySelector('.label').textContent);
    w.documentsClose();
    check('close hides the view', doc.getElementById('documentsModal').style.display === 'none');
    // a refusal: the sentence in the error state, until clicked away
    await w.documentsUpload({ name: 'notes.rtf' }); await tick();
    check('a refusal: the error pill carries the sentence as written', pill().className.includes('error') && pill().querySelector('.label').textContent === 'notes.rtf is not a PDF, Word, Markdown or text file.', pill().querySelector('.label').textContent);
    check('the hover list is not shown on an error pill', !pill().querySelector('.documents-pill-menu'));
    w.documentsPillClick();
    check('a click dismisses the refusal and the count is back', pill().className.includes('success') && pill().querySelector('.label').textContent === 'Documents (3/4)');

    // the limit
    listing.documents.push({ id: 'D4', file: 'x.md', type: 'Markdown', words: 1, tables: 0 }); await w.documentsOnThread('1700000002'); await w.documentsOnThread('1700000001'); await tick();
    check('four attached: the pill says 4/4 and the picker answers with the limit message, no file dialog', pill().querySelector('.label').textContent === 'Documents (4/4)' && (w.documentsPick(), calls.some(c => c[0] === 'limit' && c[1] === 'Maximum 4 documents per thread.')));

    // remove: DELETE, the listing re-rendered
    await w.documentsRemove('D4'); await tick();
    check('remove: a DELETE to /documents/<thread>/<id>, the pill back to 3/4', calls.some(c => c[0] === 'DELETE' && c[1] === '/documents/1700000001/D4') && pill().querySelector('.label').textContent === 'Documents (3/4)');

    // the view: the list, the map, the units grouped by page, the table
    w.documentsOpen('D1'); await tick(); await tick();
    const modal = doc.getElementById('documentsModal');
    check('the view: a thread-level dialog in the Dataset cache shape, the list with meta and remove, the selected item marked',
          modal.className === 'modal ui-modal' && modal.querySelectorAll('.docs-item').length === 3 && modal.querySelector('.docs-item.sel .id').textContent === 'D1' && modal.querySelector('.docs-item-meta').textContent.includes('PDF · 12 pages · 3 tables · 2026-10-03') && modal.querySelector('.docs-item .rm'), modal.querySelector('.docs-list').innerHTML.slice(0, 300));
    check('the view: "no embeddings yet" on a document the Embedder did not reach', modal.querySelectorAll('.docs-item-meta')[1].textContent.includes('no embeddings yet'));
    const view = modal.querySelector('.docs-view');
    check('the view: the map first, then the units grouped by page (p.1 open, p.2 folded)', view.querySelector('.docs-map').textContent.startsWith('D1 - paper.pdf (PDF, 12 pages') && view.querySelectorAll('.docs-group').length === 2 && view.querySelectorAll('.docs-group')[0].hasAttribute('open') && !view.querySelectorAll('.docs-group')[1].hasAttribute('open') && view.querySelectorAll('.docs-group summary')[1].textContent.startsWith('p.2'), view.innerHTML.slice(0, 400));
    check('units: the locator in the margin, the kind as a class, text escaped', view.querySelector('#unit-D1\\.2') === null ? view.querySelectorAll('.docs-unit')[1].querySelector('.loc').textContent === 'D1.2' && view.querySelectorAll('.docs-unit')[1].className === 'docs-unit paragraph' && view.querySelectorAll('.docs-unit')[1].querySelector('.txt').innerHTML.includes('&lt;b&gt;kept&lt;/b&gt;') : false, view.querySelectorAll('.docs-unit')[1].outerHTML);
    const tbl = view.querySelector('.docs-unit.table');
    check('a table unit: its caption, then an HTML table from the rows', tbl && tbl.querySelector('.cap').textContent === 'Table 1. Participant characteristics' && tbl.querySelectorAll('.docs-table th').length === 2 && tbl.querySelectorAll('.docs-table tr').length === 3 && tbl.querySelectorAll('.docs-table td')[0].textContent === '40-49', tbl && tbl.outerHTML);
    check('the same document again is served from the cache (map and text fetched once)', (w.documentsSelect('D1'), await tick(), calls.filter(c => c[1].endsWith('/D1/text')).length === 1));

    // the thread changes: the pill follows; a thread without documents has no pill
    // a [D1.17] chip (D45): the view opens at the unit, highlighted, its group open; a READ-quoted unit carries a mark
    w.documentsReadMarks = { 'D1.2': { quote: 'x', where: 'paper.pdf p.1' } };
    const rendered = w.documentsRenderUnits(units);
    check('read marks: the unit a READ quoted is marked in the view, the others are not', rendered.includes('class="docs-unit paragraph read" id="unit-D1.2"') && rendered.includes('<span class="mark" title="quoted by a READ in this thread">read</span>') && !rendered.includes('class="docs-unit heading read"'), rendered.slice(0, 300));
    await w.documentsOpenUnit('D1.2'); await new Promise(r => setTimeout(r, 0));
    const modal2 = doc.getElementById('documentsModal'); const hit = doc.getElementById('unit-D1.2');
    check('documentsOpenUnit: the view opens on D1 with the unit highlighted and its group open', modal2.style.display === 'flex' && w.__documentsState.selected === 'D1' && hit && hit.classList.contains('hit') && (() => { let g = hit.parentNode; while (g && g.tagName !== 'DETAILS') g = g.parentNode; return g && g.open === true; })(), hit && hit.outerHTML.slice(0, 160));
    w.documentsReadMarks = {};                      // the view stays open: the thread switch below expects it

    currentData.thread_id = 1700000002; await w.documentsSync(); await tick();

    check('another thread with no documents: the pill is gone and the view lists none', !pill() && modal.querySelector('.docs-empty').textContent.startsWith('No documents attached'), modal.querySelector('.docs-list').innerHTML);
    currentData.thread_id = null; await w.documentsSync();
    check('a fresh start (no thread): no pill, no fetch', !pill() && !calls.some(c => c[1] === '/documents/null'));

    // an upload before any question: the page adopts the minted thread as a number
    await w.documentsUpload({ name: 'first.txt' }); await tick();
    check('an upload with no thread mints one and the page adopts it', currentData.thread_id === 1700000009 && w.__documentsState.threadId === '1700000009' && pill(), currentData.thread_id);
    w.documentsClose();

    let fails = 0;
    for (const [n, ok, d] of results) { console.log((ok ? '  ok   ' : '  FAIL ') + n + (ok ? '' : '  <- ' + String(d).slice(0, 300))); if (!ok) fails++; }
    console.log(`\n${results.length - fails} passed, ${fails} failed`);
    process.exit(fails ? 1 : 0);
})().catch(e => { console.error(e); process.exit(1); });
