// The Data tab grid: a page renders typed cells and working pager state; a legacy HTML preview still restores.
'use strict';
const path = require('path');
const { makeDocument } = require(path.join(__dirname, 'minidom.js'));
const doc = makeDocument(); global.document = doc; global.window = {};
require(path.join(__dirname, '..', '..', 'web_app', 'static', 'js', 'data-grid.js'));
const results = []; const check = (n, c, d) => results.push([n, !!c, d]);
const tab = doc.createElement('div'); tab.setAttribute('id', 'content-dataframe'); doc.body.appendChild(tab);
const page = { columns: ['session_id', 'lap_avg_hr', 'when', 'surface', 'is_race'], dtypes: ['object', 'float64', 'datetime64[ns]', 'category', 'bool'],
  rows: [['athlete01__i1', 152.5, '2025-09-15 03:05:53', 'asphalt', true], ['athlete02__i2', null, '2025-09-15 03:12:00', null, false]],
  offset: 22700, limit: 50, total: 22705, order_by: 'lap_avg_hr', ascending: false, df_id: 'df_1' };
check('renders a page object into the grid', window.renderDataGrid(tab, page) === true && tab.querySelector('.dg'));
const tds = tab.querySelectorAll('tbody td');
check('cells typed by dtype and name: id monospace, number right-aligned, datetime monospace, category dimmed, bool tick, null dash',
  tds[1].classList.contains('id') && tds[2].classList.contains('num') && tds[2].textContent === '152.5' && tds[3].classList.contains('dt') && tds[4].classList.contains('cat') && tds[5].classList.contains('bool') && tds[5].textContent === '✓' && tab.querySelectorAll('td.null').length === 2 && tab.querySelectorAll('td.null')[0].textContent === '—');
check('the row numbers count from the page offset', tds[0].textContent === '22,701');
check('the bar: total, range, sort label, page size; the last page disables next/last and enables prev/first',
  tab.querySelector('.dims').textContent.includes('22,705') && tab.querySelector('.range').textContent === '22,701–22,702 of 22,705' && tab.querySelector('.sortlabel').textContent.includes('lap_avg_hr') && /selected[^>]*>50</.test(tab.querySelector('.dg-size').outerHTML)
  && tab.querySelector('.dg-next').hasAttribute('disabled') && tab.querySelector('.dg-last').hasAttribute('disabled') && !tab.querySelector('.dg-prev').hasAttribute('disabled'));
check('the sorted column header carries the arrow and dtype under the name', tab.querySelector('th.sorted').innerHTML.includes('▼') && tab.querySelector('th[data-col="when"] .t').textContent.startsWith('datetime64'));
check('values are escaped in cells and titles', (() => { const p2 = Object.assign({}, page, { rows: [['<b>x</b>', 1, 'd', 'c', false]] }); window.renderDataGrid(tab, p2); return tab.innerHTML.includes('&lt;b&gt;x&lt;/b&gt;') && !tab.innerHTML.includes('<b>x</b>'); })());
check('a legacy HTML preview (an old favourite) is placed as-is', window.renderDataGrid(tab, '<table class="dataframe"><tr><td>old</td></tr></table>') === false && tab.innerHTML.includes('class="dataframe"'));
let fails = 0; for (const [n, ok, d] of results) { console.log((ok ? '  ok   ' : '  FAIL ') + n + (ok ? '' : '  <- ' + (d || ''))); if (!ok) fails++; }
console.log(`\n${results.length - fails} passed, ${fails} failed`); process.exit(fails ? 1 : 0);
