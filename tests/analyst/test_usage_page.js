// The Usage dialog (docs/USAGE_DESIGN.md §4): the markup usage.js builds from one answer of /usage - the shell, the
// tiles with their deltas and sparklines, the series ranked into colour slots with the tail folded into Other, the
// stacked column chart, the legend table, the tooltip, what stands out, the sortable tables, the ledger grouped by
// day with its filters, the detail pane with the calls in time, the calls page, the foot - on the mini DOM.
// Run: node tests/analyst/test_usage_page.js
'use strict';
process.env.TZ = 'UTC';
const fs = require('fs'), path = require('path');
const { makeDocument } = require(path.join(__dirname, 'minidom.js'));
const doc = makeDocument(); global.document = doc; global.window = { innerWidth: 1400 };
require(path.join(__dirname, '..', '..', 'web_app', 'static', 'js', 'usage.js'));
const w = window; const b = w.__usageBuild; const results = []; const check = (n, c, d) => results.push([n, !!c, d]);
const el = html => { const d = doc.createElement('div'); d.innerHTML = html; return d; };
const chip_ = o => b.ledgerItem({ chain: 'x', when: '2026-10-18T04:00:00', question: 'q', cost: 1, outcome: o, time: 1 }, 1, false);      // the chip as the ledger draws it
const txt = (root, sel) => (root.querySelector(sel) || { textContent: '' }).textContent;

// ---- one answer of /usage, as the route shapes it (tests/analyst/test_usage.py has the route; this is its shape) ----
function day(key, label, cost, tin, tout, calls, time, chains, seats, models, modes) { return { key, label, cost, tokens_in: tin, tokens_out: tout, calls, time, chains, seats, models, modes }; }
const DAYS = [
  day('2026-10-16', '16 Oct', 1.0, 100000, 5000, 10, 100, 2, { Analyst: [0.8, 90000, 8, 80], Reviewer: [0.2, 15000, 2, 20] }, { 'm-big': [1.0, 105000, 10, 100] }, { Deep: [1.0, 105000, 10, 100] }),
  day('2026-10-17', '17 Oct', 0, 0, 0, 0, 0, 0, {}, {}, {}),
  day('2026-10-18', '18 Oct', 4.0, 400000, 20000, 30, 400, 5, { Analyst: [3.0, 300000, 20, 300], Reviewer: [0.5, 60000, 4, 50], Reader: [0.2, 30000, 3, 30], Coder: [0.1, 10000, 1, 10], Rewriter: [0.1, 10000, 1, 5], Promoter: [0.05, 5000, 1, 3], Figures: [0.03, 3000, 1, 1], Embedder: [0.02, 2000, 1, 1] },
      { 'm-big': [3.5, 360000, 24, 350], 'm-small': [0.5, 60000, 6, 50] }, { Deep: [3.0, 300000, 20, 300], Quick: [0.9, 100000, 9, 97], Routine: [0.1, 20000, 1, 3] }),
  day('2026-10-19', '19 Oct', 0.5, 50000, 2000, 5, 50, 1, { Analyst: [0.5, 52000, 5, 50] }, { 'm-big': [0.5, 52000, 5, 50] }, { Quick: [0.5, 52000, 5, 50] })];
const TOTALS = { cost: 5.5, calls: 45, chains: 8, tokens_in: 550000, tokens_out: 27000, time: 550, cached: 200000, written: 1000, recorded_in: 500000, recorded_calls: 40, savings: 0.9, search_fee: 0.01, image_fee: 0, compute: 0.24, compute_chains: 8, cached_share: 0.4 };
const BEFORE = { cost: 5.0, calls: 50, chains: 10, tokens_in: 500000, tokens_out: 30000, time: 600, cached: 0, written: 0, recorded_in: 0, recorded_calls: 0, savings: 0, search_fee: 0, image_fee: 0, compute: 0.3, compute_chains: 10, cached_share: null };
const SEATS = [{ seat: 'Analyst', calls: 33, chains: 8, tokens_in: 442000, tokens_out: 20000, cost: 4.3, time: 430, cached: 180000, recorded_in: 400000, cached_share: 0.45, tps: 46.5 },
               { seat: 'Reviewer', calls: 6, chains: 4, tokens_in: 75000, tokens_out: 3000, cost: 0.7, time: 70, cached: 20000, recorded_in: 75000, cached_share: 0.27, tps: 42.9 },
               { seat: 'Reader', calls: 3, chains: 2, tokens_in: 30000, tokens_out: 2000, cost: 0.2, time: 30, cached: 0, recorded_in: 0, cached_share: null, tps: 66.7 }];
const MODELS = [{ model: 'm-big', calls: 39, tokens_in: 517000, tokens_out: 25000, cost: 5.0, time: 500, cached: 200000, recorded_in: 470000, cached_share: 0.43, tps: 50, provider: 'anthropic', price_in: 3, price_out: 15, price_cache_read: 0.3, price_cache_write: 3.75, chains: 8 },
                { model: 'm-small', calls: 6, tokens_in: 33000, tokens_out: 2000, cost: 0.5, time: 50, cached: 0, recorded_in: 30000, cached_share: 0, tps: 40, provider: '', price_in: null, price_out: null, price_cache_read: null, price_cache_write: null, chains: 3 }];
const AN = [{ chain: 'c5', thread: 't1', when: '2026-10-18T17:05:00', kind: 'routine', question: 'Save as routine: the proposal', title: '', mode: '', cells: null, figures: 0, outcome: '', wall: null, calls: 1, tokens_in: 20000, cached: 0, recorded_in: 20000, tokens_out: 2000, time: 3, cost: 0.1, savings: 0, compute: 0.03, seats: { Promoter: 0.1 } },
            { chain: 'c2', thread: 't1', when: '2026-10-18T06:00:00', kind: 'analysis', question: 'And the third regime?', title: '', mode: 'Quick', cells: 2, figures: 0, outcome: 'failed at cell 4', wall: 40, calls: 2, tokens_in: 18500, cached: 8000, recorded_in: 18500, tokens_out: 400, time: 9, cost: 0.9, savings: 0.016, compute: 0.03, seats: { Analyst: 0.9 } },
            { chain: 'c1', thread: 't1', when: '2026-10-18T04:00:00', kind: 'analysis', question: 'Does the second regime raise the yield?', title: 'The second regime raises the yield by 12%', mode: 'Deep', cells: 14, figures: 1, outcome: 'reproduced', wall: 252, saved: true, calls: 4, tokens_in: 32000, cached: 19000, recorded_in: 32000, tokens_out: 1200, time: 25, cost: 3.0, savings: 0.041, compute: 0.03, seats: { Analyst: 2.0, Reviewer: 0.7, Reader: 0.3 } },
            { chain: 'c0', thread: 't0', when: '2026-10-16T09:00:00', kind: 'ideas', question: 'Ideas', title: '', mode: 'Ideas', cells: 0, figures: 0, outcome: 'answered', wall: 12, calls: 1, tokens_in: 4000, cached: 0, recorded_in: 0, tokens_out: 600, time: 5, cost: 1.0, savings: 0, compute: 0.03, seats: { Analyst: 1.0 } }];
const DATA = { period: { key: '30d', label: '2 – 31 Oct', start: '2026-10-02T00:00:00', end: '2026-11-01T00:00:00', bucket: 'day', buckets: 30, tz: 0, before: { start: '2026-09-02T00:00:00', end: '2026-10-02T00:00:00', label: '2 Sep – 1 Oct' }, edition: 'hosted', tier: 'pro', truncated: false, rows: 45 },
               totals: TOTALS, before: BEFORE, days: DAYS, seats: SEATS, models: MODELS, analyses: AN,
               stands_out: [{ head: '18 Oct', text: '$4.00, about half of the period, in 5 analyses.' }, { head: 'Cache', text: '40% of the input was served from the cache ($0.90 saved).' }, { head: 'Failures', text: '1 of 3 analyses failed (33%), $0.90 between them.' }] };
const ST = { period: '30d', compare: true, tab: 'overview', measure: 'cost', by: 'seats', isolate: null, sort: { seats: 'cost', models: 'cost' }, ledgerSort: 'date', find: '', mode: 'all', outcome: 'all', pick: null, calls: [], callsPage: 1, callsSize: 100, callsMore: false };

// ---- the shell ----
let s = el(b.shell());
check('shell: the ui-dlg with header (title, the period select with six periods, the compare toggle, Export CSV, close), the four tabs, the body and the foot',
  s.querySelector('.ui-dlg.lg.us-dlg .ui-dlg-h .title').textContent === 'Usage' && s.querySelectorAll('[data-period] option').length === 6 && [...s.querySelectorAll('[data-period] option')].map(o => o.getAttribute('value')).join(',') === '24h,7d,30d,90d,month,last_month'
  && s.querySelector('[data-period] option[value="30d"]').hasAttribute('selected') && s.querySelector('input[data-compare]') && s.querySelector('[data-act="export"]') && s.querySelector('.ui-dlg-h .x.close')
  && [...s.querySelectorAll('.us-tabs [data-tab]')].map(t => t.getAttribute('data-tab')).join(',') === 'overview,seats,analyses,calls' && s.querySelector('.us-tabs .on').getAttribute('data-tab') === 'overview'
  && s.querySelector('[data-body] .us-wait') && s.querySelector('[data-foot]').textContent.includes('nothing is written by a model'));
check('sub line and compare text: the window, its length and the edition; the toggle names the length', b.sub(DATA.period) === '2 – 31 Oct · 30 days · hosted, Pro compute' && b.sub(Object.assign({}, DATA.period, { edition: 'self-hosted', tier: 'local' })) === '2 – 31 Oct · 30 days · the self-hosted edition'
  && b.sub(Object.assign({}, DATA.period, { bucket: 'hour', buckets: 24 })) === '2 – 31 Oct · 24 hours · hosted, Pro compute' && b.compareText(DATA.period) === 'compare with the 30 days before' && b.compareText(Object.assign({}, DATA.period, { bucket: 'hour' })) === 'compare with the 24 hours before');

// ---- the tiles ----
let t = el(b.tiles(DATA));
const tiles = t.querySelectorAll('.us-tile');
check('tiles, hosted with a comparison: seven - model cost, analyses, model calls, tokens in, tokens out, model time, compute - each with its value, its delta against the period before and a sparkline over the days',
  tiles.length === 7 && [...tiles].map(x => txt(x, '.l')).join('|') === 'Model cost|Analyses|Model calls|Tokens in|Tokens out|Model time|Compute' && txt(tiles[0], '.v').startsWith('$5.50') && txt(tiles[0], '.d') === '▲ 10%'
  && txt(tiles[1], '.v').startsWith('8') && txt(tiles[1], '.d') === '▼ 20%' && txt(tiles[2], '.d') === '▼ 10%' && txt(tiles[3], '.v').startsWith('550K') && txt(tiles[4], '.v').startsWith('27K') && txt(tiles[5], '.v').startsWith('9 m 10 s')
  && txt(tiles[6], '.v').startsWith('$0.24') && txt(tiles[6], '.d') === '▼ 20%' && tiles[0].querySelector('.spark polyline') && !tiles[6].querySelector('.spark'), [...tiles].map(x => x.textContent));
check('tiles, the sub lines: the period before\'s figure, the average per analysis, calls per analysis, the cached share with the savings over the calls that recorded it, the ratio, the reply pace, the analyses charged on the tier',
  txt(tiles[0], '.s span') === 'vs $5.00 the 30 days before' && txt(tiles[1], '.s span') === 'avg $0.69 · 1 m 09 s each' && txt(tiles[2], '.s span') === '5.6 per analysis' && txt(tiles[3], '.s span') === '40% from cache on 40 of 45 calls · $0.90 saved'
  && txt(tiles[4], '.s span') === 'a 0.05 ratio to the input' && txt(tiles[5], '.s span') === 'a reply every 12 s on average' && txt(tiles[6], '.s span') === '8 analyses charged · Pro', [...tiles].map(x => txt(x, '.s span')));
t = el(b.tiles(Object.assign({}, DATA, { before: null, period: Object.assign({}, DATA.period, { edition: 'self-hosted' }), totals: Object.assign({}, TOTALS, { recorded_in: 0, recorded_calls: 0 }) })));
check('tiles, self-hosted without a comparison: six tiles, no deltas, the cost\'s sub line the calls, the cache "not recorded" when no call carries it',
  t.querySelectorAll('.us-tile').length === 6 && !t.querySelector('.d') && txt(t.querySelectorAll('.us-tile')[0], '.s span') === 'in 45 calls' && txt(t.querySelectorAll('.us-tile')[3], '.s span') === 'cache not recorded on these calls');
t = el(b.tiles(Object.assign({}, DATA, { before: Object.assign({}, BEFORE, { cost: 0.1 }) })));
check('tiles: a delta beyond tenfold reads as a multiple, not a thousand percent', txt(t.querySelectorAll('.us-tile')[0], '.d') === '▲ 55×');

// ---- the series: who gets a colour ----
let ser = w.UsageUI.seriesOf(DAYS, 'seats', 'cost');
check('seriesOf: the keys ranked by the measure over the period, the first six with a slot of their own, the tail folded into Other with its members', ser.map(x => x.key).join(',') === 'Analyst,Reviewer,Reader,Coder,Rewriter,Promoter,Other'
  && ser.map(x => x.cls).join(',') === 'us-s1,us-s2,us-s3,us-s4,us-s5,us-s6,us-s0' && Math.abs(ser[0].total - 4.3) < 1e-9 && ser[6].members.join(',') === 'Figures,Embedder' && Math.abs(ser[6].total - 0.05) < 1e-9 && Math.abs(ser[0].share - 4.3 / 5.5) < 1e-9, ser);
ser = w.UsageUI.seriesOf(DAYS, 'modes', 'calls');
check('seriesOf by mode on the calls: three keys, no Other when seven or fewer', ser.map(x => x.key + ':' + x.total).join(',') === 'Deep:30,Quick:14,Routine:1' && ser.every(x => x.cls !== 'us-s0'));
check('niceTicks: a round scale over the top column', w.UsageUI.niceTicks(4.0).join(',') === '0,1,2,3,4' && w.UsageUI.niceTicks(0.37).join(',') === '0,0.1,0.2,0.3,0.4' && w.UsageUI.niceTicks(1234).join(',') === '0,500,1000,1500' && w.UsageUI.niceTicks(0).join(',') === '0,1');

// ---- the stacked column chart ----
ser = w.UsageUI.seriesOf(DAYS, 'seats', 'cost');
let c = el(b.stacked(DAYS, 'seats', 'cost', ser, null, 2));
const segsOf = root => [...root.querySelectorAll('rect'), ...root.querySelectorAll('path')].filter(x => x.className.startsWith('us-s'));
const segs = segsOf(c);
check('stacked: one hairline grid line and a tick label per round step; the segments stacked per day in the series\' classes, the top one a rounded path when it is tall enough (the thin Other on the 18th stays square); an empty day draws nothing; a hover band on the day asked; an invisible column per day for the hover',
  c.querySelectorAll('line.grid').length === 5 && [...c.querySelectorAll('text.tick')].slice(0, 5).map(x => x.textContent).join(',') === '$0,$1,$2,$3,$4' && segs.length >= 9 && c.querySelectorAll('path.us-s1').length === 1
  && segsOf(c).filter(x => x.tag === 'path').length === 2 && segsOf(c).length === 10 && c.querySelectorAll('rect.hover-band').length === 1 && c.querySelectorAll('rect.col[data-i]').length === 4 && c.querySelector('svg').getAttribute('aria-label') === 'Cost by day, split by seats', [segs.length, c.innerHTML.slice(0, 400)]);
c = el(b.stacked(DAYS, 'seats', 'tokens', ser, 'Reviewer', -1));
check('stacked, one series isolated on the tokens: only its segments, the scale theirs', segsOf(c).length === 2 && segsOf(c).every(x => x.className === 'us-s2') && txt(c, 'text.tick') === '0', c.innerHTML.slice(0, 300));
check('stacked: a day label every day for four days; every third for thirty', el(b.stacked(DAYS, 'seats', 'cost', ser, null, -1)).querySelectorAll('text.tick').length === 5 + 4
  && el(b.stacked(Array.from({ length: 30 }, (_, i) => day('d' + i, 'L' + i, 1, 0, 0, 1, 1, 1, { A: [1, 0, 1, 1] }, {}, {})), 'seats', 'cost', [{ key: 'A', cls: 'us-s1', members: ['A'], total: 30, share: 1 }], null, -1)).querySelectorAll('text.tick').length === 5 + 10);
let lg = el(b.legend(ser, 'seats', 'cost', null));
check('legend: a row per series with its swatch class, amount and share, Other naming its members; the total row', lg.querySelectorAll('.r[data-series]').length === 7 && lg.querySelector('.r[data-series="Analyst"] .us-sw').className === 'us-sw us-s1' && txt(lg, '.r[data-series="Analyst"] .v') === '$4.30'
  && txt(lg, '.r[data-series="Analyst"] .p') === '78%' && lg.querySelector('.r[data-series="Other"]').getAttribute('title') === 'Figures, Embedder' && txt(lg, '.r.sum .v') === '$5.50' && txt(lg, '.h').startsWith('Seats'));
lg = el(b.legend(ser, 'seats', 'cost', 'Reader'));
check('legend with one isolated: it is marked, the others dimmed', lg.querySelector('.r[data-series="Reader"]').className.includes('only') && lg.querySelector('.r[data-series="Analyst"]').className.includes('off'));
let tip = el(b.tooltip(DAYS[2], 'seats', 'cost', ser));
check('tooltip: the day\'s head (cost, analyses, calls, tokens, time) and a row per series with a value', txt(tip, '.h') === '18 Oct · $4.00 · 5 analyses · 30 calls · 420K tokens · 6 m 40 s' && tip.querySelectorAll('.r').length === 7 && txt(tip, '.r b') === '$3.00');
tip = el(b.tooltip(DAYS[2], 'models', 'time', w.UsageUI.seriesOf(DAYS, 'models', 'time')));
check('tooltip on the time by model', tip.querySelectorAll('.r').length === 2 && txt(tip, '.r b') === '5 m 50 s');
let cs = el(b.chartSection(DATA, ST));
check('chart section: the heading with the measure and the split selectors (the current ones on), the chart beside the legend', cs.querySelector('[data-sec="chart"]') && cs.querySelectorAll('[data-measure]').length === 4 && cs.querySelector('[data-measure="cost"]').className === 'on' && cs.querySelector('[data-by="seats"]').className === 'on'
  && cs.querySelector('[data-chart] svg.us-chart') && cs.querySelector('.us-legend') && txt(cs, '.h .n').includes('one column a day'));
cs = el(b.chartSection(Object.assign({}, DATA, { totals: Object.assign({}, TOTALS, { calls: 0 }) }), ST));
check('chart section of an empty period: says so instead of an empty chart', txt(cs, '.us-empty') === 'No model calls in this period.' && !cs.querySelector('svg'));
check('what stands out: the three lines as a key-value list', el(b.standsOut(DATA.stands_out)).querySelectorAll('.us-kv b').length === 3 && b.standsOut([]) === '');
check('overview: the tiles, the chart section and what stands out', (() => { const o = el(b.overview(DATA, ST)); return o.querySelector('.us-tiles') && o.querySelector('[data-sec="chart"]') && o.querySelector('.us-kv'); })());

// ---- the tables ----
let st_ = el(b.seatsTable(SEATS, TOTALS, 'cost'));
check('seats table: a row per seat with its swatch, calls, analyses, tokens, cached share (a dash when not recorded), cost, a share bar, time per call, tok/s; the sort column marked',
  st_.querySelectorAll('tbody tr').length === 3 && txt(st_, 'tbody tr td.label') === 'Analyst' && st_.querySelector('tbody tr td.label .us-sw').className === 'us-sw us-s1' && [...st_.querySelectorAll('tbody tr')[0].querySelectorAll('td')].map(x => x.textContent).join('|') === 'Analyst|33|8|442K|45%|20K|$4.30|78%|13 s|47'
  && txt(st_.querySelectorAll('tbody tr')[2], 'td.muted') === '—' && st_.querySelector('th.on').getAttribute('data-sort') === 'cost' && st_.querySelector('tbody tr td.bar span').getAttribute('style') === 'width:100%');
st_ = el(b.seatsTable(SEATS, TOTALS, 'tps'));
check('seats table sorted by tok/s: the Reader first', txt(st_, 'tbody tr td.label') === 'Reader');
st_ = el(b.seatsTable(SEATS, TOTALS, 'seat'));
check('seats table sorted by name', [...st_.querySelectorAll('tbody tr td.label')].map(x => x.textContent).join(',') === 'Analyst,Reader,Reviewer');
let mt = el(b.modelsTable(MODELS, TOTALS, 'cost'));
check('models table: the provider beside the model, the list price per million in and out (a dash without one), the share bar', mt.querySelectorAll('tbody tr').length === 2 && txt(mt, 'tbody tr td.label') === 'm-big · anthropic'
  && [...mt.querySelectorAll('tbody tr')[0].querySelectorAll('td')].map(x => x.textContent).join('|') === 'm-big · anthropic|39|517K|43%|25K|$5.00|91%|$3.00 / $15.00|50' && [...mt.querySelectorAll('tbody tr')[1].querySelectorAll('td')][7].textContent === '—');
check('seats tab: both sections with their notes', (() => { const x = el(b.seatsTab(DATA, ST)); return x.querySelectorAll('.us-sec').length === 2 && x.querySelector('[data-table="seats"]') && x.querySelector('[data-table="models"]'); })());

// ---- the analyses: the ledger with a detail pane ----
let at = el(b.analysesTab(DATA, ST));
check('analyses tab: the note counts the analyses and the other chains with the cost and the model time; the find box, the mode and outcome selects from what the period holds, the three sorts; the split with the list and the empty detail',
  txt(at, '.h .us-note') === '3 analyses and 1 other chain · $5.50 · 9 m 10 s of model time' && at.querySelector('[data-find]') && [...at.querySelectorAll('[data-mode] option')].map(o => o.getAttribute('value')).join(',') === 'all,Deep,Ideas,Other,Quick'
  && [...at.querySelectorAll('[data-outcome] option')].map(o => o.getAttribute('value')).join(',') === 'all,answered,failed,reproduced' && at.querySelectorAll('[data-lsort]').length === 3 && at.querySelector('[data-lsort="date"]').className === 'on'
  && at.querySelectorAll('.us-list .it').length === 4 && txt(at, '[data-detail] .pick').startsWith('Pick an analysis'), at.innerHTML.slice(0, 600));
check('ledger by date: grouped by local day with the day\'s count and cost; each item with the question, the cost, the time, mode, cells, the wall time and the outcome chip; the bar against the dearest',
  at.querySelectorAll('.us-list .day').length === 2 && txt(at, '.us-list .day') === '18 Oct · 3 analyses · $4.00' && [...at.querySelectorAll('.us-list .it')].map(x => x.getAttribute('data-chain')).join(',') === 'c5,c2,c1,c0'
  && txt(at, '.it[data-chain="c1"] .q') === 'Does the second regime raise the yield?' && txt(at, '.it[data-chain="c1"] .c') === '$3.00' && txt(at, '.it[data-chain="c1"] .m').startsWith('04:00 · Deep · 14 cells · 4 m 12 s · ') && txt(at, '.it[data-chain="c1"] .rt-status') === 'reproduced'
  && at.querySelector('.it[data-chain="c2"] .rt-status').className === 'rt-status failed' && at.querySelector('.it[data-chain="c1"] .bar span').getAttribute('style') === 'width:100%' && at.querySelector('.it[data-chain="c2"] .bar span').getAttribute('style') === 'width:30%'
  && txt(at, '.it[data-chain="c5"] .m') === '17:05 · 3 s' && !at.querySelector('.it[data-chain="c5"] .rt-status', at.innerHTML.slice(0, 400)));
let shown = b.filterLedger(AN, Object.assign({}, ST, { find: 'regime' }));
check('filterLedger: a word of the question or the title; a mode; an outcome group (every failure under failed); by cost and by time', shown.map(e => e.chain).join(',') === 'c2,c1'
  && b.filterLedger(AN, Object.assign({}, ST, { find: 'yield by 12' })).map(e => e.chain).join(',') === 'c1' && b.filterLedger(AN, Object.assign({}, ST, { mode: 'Quick' })).map(e => e.chain).join(',') === 'c2'
  && b.filterLedger(AN, Object.assign({}, ST, { mode: 'Other' })).map(e => e.chain).join(',') === 'c5' && b.filterLedger(AN, Object.assign({}, ST, { outcome: 'failed' })).map(e => e.chain).join(',') === 'c2'
  && b.filterLedger(AN.concat([{ chain: 'c9', when: '2026-10-17T04:00:00', kind: 'analysis', question: 'An analysis that was not saved', title: '', mode: '', outcome: '', cost: 0.1, time: 1 }]), Object.assign({}, ST, { mode: 'not recorded' })).map(e => e.chain).join(',') === 'c9'
  && b.filterLedger(AN, Object.assign({}, ST, { ledgerSort: 'cost' })).map(e => e.chain).join(',') === 'c1,c0,c2,c5' && b.filterLedger(AN, Object.assign({}, ST, { ledgerSort: 'time' })).map(e => e.chain).join(',') === 'c1,c2,c0,c5');
check('ledger by cost: flat, no day groups; the picked one marked', (() => { const l = el(b.ledger(b.filterLedger(AN, Object.assign({}, ST, { ledgerSort: 'cost' })), Object.assign({}, ST, { ledgerSort: 'cost', pick: 'c0' }))); return !l.querySelector('.day') && l.querySelector('.it.on').getAttribute('data-chain') === 'c0'; })()
  && el(b.ledger([], ST)).textContent === 'No analyses match.');
const DET = { analysis: AN[2], totals: { cost: 3.0, calls: 4, chains: 1, tokens_in: 32000, tokens_out: 1200, time: 25, cached: 19000, written: 1000, recorded_in: 32000, recorded_calls: 4, savings: 0.041, search_fee: 0.01, image_fee: 0, compute: 0.03, compute_chains: 1, cached_share: 19000 / 32000 },
              seats: [{ seat: 'Analyst', calls: 2, cost: 2.0, tokens_in: 22000, tokens_out: 900, time: 18, cached: 15000, recorded_in: 22000, cached_share: 15000 / 22000, tps: 50 }, { seat: 'Reviewer', calls: 1, cost: 0.7, tokens_in: 8000, tokens_out: 200, time: 5, cached: 4000, recorded_in: 8000, cached_share: 0.5, tps: 40 }, { seat: 'Reader', calls: 1, cost: 0.3, tokens_in: 2000, tokens_out: 100, time: 2, cached: 0, recorded_in: 2000, cached_share: 0, tps: 50 }],
              models: [{ model: 'm-big', calls: 3, cost: 2.7, tokens_in: 30000, tokens_out: 1100, time: 23, cached: 19000, recorded_in: 30000, cached_share: 19000 / 30000, tps: 48 }, { model: 'm-small', calls: 1, cost: 0.3, tokens_in: 2000, tokens_out: 100, time: 2, cached: 0, recorded_in: 2000, cached_share: 0, tps: 50 }],
              calls: [{ id: 1, at: 0, t: '2026-10-18T04:00:00', seat: 'Analyst', model: 'm-big', tokens_in: 10000, cached: 6000, written: 1000, tokens_out: 500, elapsed: 10, tps: 50, cost: 1.0, savings: 0.012, search_fee: 0, image_fee: 0 },
                      { id: 2, at: 60, t: '2026-10-18T04:01:00', seat: 'Analyst', model: 'm-big', tokens_in: 12000, cached: 9000, written: 0, tokens_out: 400, elapsed: 8, tps: 50, cost: 1.0, savings: 0.02, search_fee: 0, image_fee: 0 },
                      { id: 3, at: 120, t: '2026-10-18T04:02:00', seat: 'Reviewer', model: 'm-big', tokens_in: 8000, cached: 4000, written: 0, tokens_out: 200, elapsed: 5, tps: 40, cost: 0.7, savings: 0.009, search_fee: 0, image_fee: 0 },
                      { id: 4, at: 180, t: '2026-10-18T04:03:00', seat: 'Reader', model: 'm-small', tokens_in: 2000, cached: 0, written: 0, tokens_out: 100, elapsed: 2, tps: 50, cost: 0.3, savings: 0, search_fee: 0.01, image_fee: 0 }], span: 182 };
let d = el(b.detail(DET));
check('detail: the question and the title, the meta line (when, mode, cells, calls, wall time, outcome) with "open the analysis" carrying the thread and the chain; the figures; the seats ranked with bars in their colours; the calls in time; the models',
  txt(d, '.us-detail-h .q') === 'Does the second regime raise the yield?' && txt(d, '.us-detail-h .t') === 'The second regime raises the yield by 12%' && txt(d, '.us-detail-h .m').startsWith('18 Oct 04:00 · Deep · 14 cells · 4 calls · 4 m 12 s · reproduced')
  && d.querySelector('.open[data-act="open"]').getAttribute('data-thread') === 't1' && d.querySelector('.open').getAttribute('data-chain') === 'c1' && d.querySelectorAll('.us-kpis div').length === 6
  && [...d.querySelectorAll('.us-kpis div')].map(x => x.textContent).join('|') === '$3.00model cost|32Ktokens in · 59% cached|1.2Ktokens out|25 smodel time of 4 m 12 s|$0.04cache savings|$0.03compute charge'
  && d.querySelectorAll('.us-rank .r').length === 3 && txt(d, '.us-rank .r .n') === 'Analyst · 2 calls' && d.querySelector('.us-rank .r .b span').className === 'us-s1' && d.querySelector('.us-rank .r .b span').getAttribute('style') === 'width:100%' && txt(d, '.us-rank .r .v') === '$2.00'
  && d.querySelectorAll('.us-tl rect.call').length === 4 && d.querySelectorAll('.us-tlkey span').length === 3 && d.querySelectorAll('.us-kv.models b').length === 2 && txt(d, '.us-kv.models span') === '3 calls · 30K in (63% cached) · 1.1K out · $2.70', d.innerHTML.slice(0, 900));
const tl = el(b.timeline(DET, 600));
const marks = [...tl.querySelectorAll('rect.call')];
check('timeline: one row per seat in rank order, a mark per call at its second and as wide as it took (never thinner than a hair), the axis from 0:00 to the span',
  marks.map(m => m.getAttribute('y')).join(',') === '2,2,13,24' && marks[0].getAttribute('x') === '0.0' && marks[1].getAttribute('x') === (60 / 182 * 600).toFixed(1) && marks[0].getAttribute('width') === (10 / 182 * 600 - 1.5).toFixed(1) && marks[0].className === 'call us-s1' && marks[3].className === 'call us-s3'
  && [...tl.querySelectorAll('text.tick')].map(x => x.textContent).join(',') === '0:00,3:02', marks.map(m => m.outerHTML));
check('callTip: the seat and model, when and how long, the tokens with the cache, the cost and the fees inside it', (() => { const x = el(b.callTip(DET.calls[3])); return txt(x, '.h') === 'Reader · m-small' && x.textContent.includes('at 3:00 for 2 s') && x.textContent.includes('2.0K in · 0 cached') && x.textContent.includes('fees inside it$0.01'); })()
  && el(b.callTip(Object.assign({}, DET.calls[0], { cached: null }))).textContent.includes('cache not recorded'));
check('the outcome words (2026-10-31, from the product owner reading "answered" as the general success): every chip carries its gloss, the detail pane spells it out, the filter\'s options say what each word means',
  el(chip_('reproduced')).querySelector('.rt-status').getAttribute('title') === 'answered; the replay re-ran the cells and the cited numbers matched' && el(chip_('answered')).querySelector('.rt-status').getAttribute('title') === 'answered; no replay on record'
  && el(chip_('failed at cell 4')).querySelector('.rt-status').getAttribute('title') === 'the run failed; the last error was in cell 4' && txt(d, '.us-detail-h .gloss') === 'answered; the replay re-ran the cells and the cited numbers matched'
  && [...el(b.analysesTab(DATA, ST)).querySelectorAll('[data-outcome] option')].map(o => o.textContent).join('|') === 'Every outcome|answered — no replay on record|failed|reproduced — replay matched');
d = el(b.detail(Object.assign({}, DET, { analysis: AN[0] })));
check('detail of a chain the thread store does not know (Save as routine): no title, no "open the analysis"', !d.querySelector('.open') && txt(d, '.us-detail-h .q') === 'Save as routine: the proposal' && !d.querySelector('.us-detail-h .muted'));
d = el(b.detail(Object.assign({}, DET, { analysis: Object.assign({}, AN[2], { saved: false }) })));
check('detail of an analysis not saved as a favourite: no link (the page opens a chain from its saved file), a "not saved" note instead', !d.querySelector('.open') && txt(d, '.us-detail-h .muted') === '· not saved');

// ---- the calls ----
const ROWS = [{ id: 9, t: '2026-10-18T04:03:00', chain: 'c1', seat: 'Reader', model: 'm-small', tokens_in: 2000, cached: null, written: null, tokens_out: 100, elapsed: 2, tps: 50, cost: 0.3, savings: null, search_fee: 0.01, image_fee: 0, tier: 'pro', query_cost: 0.03 },
              { id: 8, t: '2026-10-18T04:00:00', chain: 'c1', seat: 'Analyst', model: 'm-big', tokens_in: 10000, cached: 6000, written: 1000, tokens_out: 500, elapsed: 10, tps: 50, cost: 1.0, savings: 0.012, search_fee: 0, image_fee: 0, tier: 'pro', query_cost: 0.03 }];
let ct = el(b.callsTab(Object.assign({}, ST, { calls: ROWS, callsPage: 2, callsSize: 100, callsMore: true })));
check('calls: the table in its own scroll box under the section (the header frozen by the stylesheet); a row per call with the chain as a link into the ledger, dashes where the cache was not recorded, the fees; the pager says the rows and offers newer and older',
  ct.querySelector('.us-sec.calls .us-scroll [data-table="calls"]') && ct.querySelectorAll('tbody tr').length === 2 && ct.querySelector('tbody tr td.link a').getAttribute('data-chain') === 'c1' && [...ct.querySelectorAll('tbody tr')[0].querySelectorAll('td')].map(x => x.textContent).join('|') === '18 Oct 04:03|c1|Reader|m-small|2,000|—|—|100|2 s|50|$0.30|—|$0.01'
  && [...ct.querySelectorAll('tbody tr')[1].querySelectorAll('td')].map(x => x.textContent).join('|') === '18 Oct 04:00|c1|Analyst|m-big|10,000|6,000|1,000|500|10 s|50|$1.00|$0.01|—' && txt(ct, '.us-pager span') === 'rows 101 – 102'
  && !ct.querySelector('[data-act="newer"]').hasAttribute('disabled') && !ct.querySelector('[data-act="older"]').hasAttribute('disabled'), ct.innerHTML.slice(0, 600));
ct = el(b.callsTab(Object.assign({}, ST, { calls: [], callsPage: 1, callsMore: false })));
check('calls, none: says so; both pager buttons off', txt(ct, 'tbody td') === 'No calls in this period.' && ct.querySelector('[data-act="newer"]').hasAttribute('disabled') && ct.querySelector('[data-act="older"]').hasAttribute('disabled'));

// ---- the foot ----
check('foot: the standing line; a note when some calls of the period predate the cache fields; a note when the answer stopped at its row limit', b.foot(DATA).includes('The cache split is recorded on calls made since this dialog’s release (40 of 45 calls in this period)')
  && !b.foot(Object.assign({}, DATA, { totals: Object.assign({}, TOTALS, { recorded_calls: 45 }) })).includes('recorded on calls') && b.foot(Object.assign({}, DATA, { period: Object.assign({}, DATA.period, { truncated: true }) })).includes('the figures stop at the first 45 calls')
  && b.foot(Object.assign({}, DATA, { analyses: AN.concat([{ chain: 'c9', kind: 'analysis', question: 'An analysis that was not saved', mode: '' }, { chain: 'c8', kind: 'analysis', question: 'An analysis that was not saved', mode: '' }]) })).includes('2 analyses of this period were not saved as favourites before this release')
  && !b.foot(DATA).includes('not saved as favourites'));
check('wait and error states', el(b.wait()).querySelector('.us-wait .spin') && el(b.error('no')).querySelector('.us-error [data-act="retry"]') && txt(el(b.error('the server answered 500')), '.us-error div') === 'the server answered 500');

// ---- the page's hooks ----
const html = fs.readFileSync(path.join(__dirname, '..', '..', 'web_app', 'templates', 'index.html'), 'utf8');
const core = fs.readFileSync(path.join(__dirname, '..', '..', 'web_app', 'static', 'js', 'core.js'), 'utf8');
const css = fs.readFileSync(path.join(__dirname, '..', '..', 'web_app', 'static', 'css', 'dialogs.css'), 'utf8');
const tokens = fs.readFileSync(path.join(__dirname, '..', '..', 'web_app', 'static', 'css', 'tokens.css'), 'utf8');
check('the page: usage.js linked, the settings entry is .usage-option, the old modal markup and script gone; core.js initialises UsageUI; Plotly stays for the figures',
  html.includes("filename='js/usage.js'") && html.includes('settings-option usage-option') && !html.includes('usageTrackingModal') && !html.includes('usage-tracking.js') && !fs.existsSync(path.join(__dirname, '..', '..', 'web_app', 'static', 'js', 'usage-tracking.js'))
  && core.includes('window.UsageUI.initialize()') && !core.includes('initializeUsageTracking') && html.includes('plotly'));
check('the stylesheets: the series tokens in both themes, the dialog\'s rules (the slots over the tokens, the tiles, the chart, the legend, the ledger, the detail, the timeline, the pager), the old #usageTrackingModal rules gone',
  /--viz-1: #3987e5;[\s\S]*--viz-other: #6b6b6b;/.test(tokens) && /--viz-1: #2a78d6;[\s\S]*--viz-other: #9a9a9a;/.test(tokens) && ['.us-s1 { fill: var(--viz-1); background: var(--viz-1); }', '.us-s0 { fill: var(--viz-other)', '.us-tile', '.us-chart .grid', '.us-legend .r', '.us-list .it', '.us-detail-h', '.us-tl ', '.us-pager', '#usageModal .ui-dlg.us-dlg { width: min(1240px, 100%)',
      '.us-scroll .us-table thead th { position: sticky; top: 0;', '#usageModal .ui-dlg-b:has(.us-body.calls) { overflow: hidden; }', '.us-list .day { position: sticky; top: 0;'].every(x => css.includes(x))
  && !css.includes('#usageTrackingModal'));

const n_fail = results.filter(r => !r[1]).length;
for (const [n, ok, d] of results) console.log((ok ? '  ok   ' : '  FAIL ') + n + (ok ? '' : '  <- ' + String(d == null ? '' : (typeof d === 'object' ? JSON.stringify(d) : d)).slice(0, 700)));
console.log(`\n${results.length - n_fail} passed, ${n_fail} failed`);
process.exit(n_fail ? 1 : 0);
