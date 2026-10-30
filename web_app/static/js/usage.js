// usage.js - the Usage dialog (docs/USAGE_DESIGN.md §4, 2026-10-31): what the analyses cost and where the money and
// the time went, from one answer of /usage (web_app/usage_routes.py). Four tabs - Overview (the tiles, the stacked
// column chart with its legend table and tooltip, what stands out), Seats & models (two sortable tables), Analyses
// (the ledger with a detail pane fed by /usage/analysis/<chain>), Calls (the raw rows, paged) - a period, a
// compare-with-the-period-before toggle and Export CSV in the header. The charts are the page's own SVG; a series
// colour is a class (us-s1..7, us-s0 for Other) over the --viz tokens, so the fills follow the theme. The markup is
// built here on the app's grammar (ui-*); the rules are in dialogs.css. Nothing shown here is written by a model.

(function () {
    'use strict';

    const MEASURES = { cost: 'Cost', tokens: 'Tokens', calls: 'Calls', time: 'Time' };
    const MI = { cost: 0, tokens: 1, calls: 2, time: 3 };                       // the split arrays' order: [cost, tokens, calls, time]
    const BYS = { seats: 'Seats', models: 'Models', modes: 'Modes' };
    const MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
    const SLOTS = 7;                                                           // series colours before the tail folds into Other
    const FOOT = 'Costs are the providers’ list prices applied to the tokens each call reported, cache reads and writes priced as the provider prices them; time is the models’ own, not the kernel’s. Every number here comes from the call records; nothing is written by a model.';

    function esc(s) {
        return String(s == null ? '' : s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
    }
    function money(x, d) {
        x = Number(x) || 0;
        if (d == null) d = (Math.abs(x) >= 0.00005 && Math.abs(x) < 0.01) ? 4 : 2;      // a cost under a cent keeps four places; a trace rounds to $0.00
        const neg = x < 0; x = Math.abs(x);
        return (neg ? '−$' : '$') + x.toLocaleString(undefined, { minimumFractionDigits: d, maximumFractionDigits: d });
    }
    function compact(n) {
        n = Number(n) || 0;
        if (n >= 1e6) return (n / 1e6).toFixed(n >= 1e7 ? 0 : 1) + 'M';
        if (n >= 1e4) return Math.round(n / 1e3) + 'K';
        if (n >= 1e3) return (n / 1e3).toFixed(1) + 'K';
        return String(Math.round(n));
    }
    function num(n) { return (Number(n) || 0).toLocaleString(); }
    function dur(s) {
        s = Number(s) || 0;
        if (s < 1) return s === 0 ? '0 s' : s.toFixed(1) + ' s';
        if (s < 60) return Math.round(s) + ' s';
        const h = Math.floor(s / 3600), m = Math.floor((s % 3600) / 60), sec = Math.round(s % 60);
        if (h) return h + ' h ' + String(m).padStart(2, '0') + ' m';
        return m + ' m ' + String(sec).padStart(2, '0') + ' s';
    }
    function clock(s) {                                                        // m:ss for a timeline axis
        s = Math.max(0, Math.round(Number(s) || 0));
        return Math.floor(s / 60) + ':' + String(s % 60).padStart(2, '0');
    }
    function pct(x) { return x == null ? '—' : Math.round(x * 100) + '%'; }
    function tz() { return -new Date().getTimezoneOffset(); }
    function local(t) {                                                        // a UTC timestamp as the page's local time, its UTC getters reading local
        const ms = Date.parse(String(t).replace(' ', 'T') + 'Z');
        return isNaN(ms) ? null : new Date(ms + tz() * 60000);
    }
    function dayOf(t) { const d = local(t); return d ? d.getUTCFullYear() + '-' + String(d.getUTCMonth() + 1).padStart(2, '0') + '-' + String(d.getUTCDate()).padStart(2, '0') : ''; }
    function dayLabel(t) { const d = local(t); return d ? d.getUTCDate() + ' ' + MONTHS[d.getUTCMonth()] : ''; }
    function timeLabel(t) { const d = local(t); return d ? String(d.getUTCHours()).padStart(2, '0') + ':' + String(d.getUTCMinutes()).padStart(2, '0') : ''; }
    function whenLabel(t) { return dayLabel(t) + ' ' + timeLabel(t); }
    function tierName(t) { return ({ free: 'Free', plus: 'Plus', pro: 'Pro', local: 'local' })[t] || t || ''; }
    function statusClass(o) {
        o = String(o || '');
        if (o === 'reproduced' || o === 'ran') return 'reproduced';
        if (o.startsWith('failed') || o === 'refused' || o === 'replay failed') return 'failed';
        if (o === 'differed' || o === 'stopped') return 'differed';
        return '';
    }
    function chip(o) { return o ? '<span class="rt-status ' + statusClass(o) + '">' + esc(o) + '</span>' : ''; }
    function fetchJson(url, opts) {
        const f = (window.authService && window.authService.fetch) ? window.authService.fetch.bind(window.authService) : fetch;
        return f(url, opts).then(r => r.json().then(j => ({ ok: r.ok, status: r.status, json: j })).catch(() => ({ ok: r.ok, status: r.status, json: {} })));
    }
    function toast(text) { if (typeof showSystemMessage === 'function') showSystemMessage(text); else console.log(text); }

    // ------------------------------------------------------------ the series: who gets a colour
    // the keys of a split ranked by the measure over the period; the first SLOTS keep a slot of their own, the rest
    // fold into Other (one key alone is not folded); a key's slot holds whatever the filter shows
    function seriesOf(days, by, measure) {
        const tot = {};
        for (const d of days) for (const k in (d[by] || {})) tot[k] = (tot[k] || 0) + (d[by][k][MI[measure]] || 0);
        const keys = Object.keys(tot).sort((a, b) => tot[b] - tot[a] || a.localeCompare(b));
        const sum = keys.reduce((s, k) => s + tot[k], 0) || 0;
        const out = [];
        const own = keys.length <= SLOTS ? keys : keys.slice(0, SLOTS - 1);
        own.forEach((k, i) => out.push({ key: k, cls: 'us-s' + (i + 1), total: tot[k], share: sum ? tot[k] / sum : 0, members: [k] }));
        const rest = keys.slice(own.length);
        if (rest.length) {
            const t = rest.reduce((s, k) => s + tot[k], 0);
            out.push({ key: 'Other', cls: 'us-s0', total: t, share: sum ? t / sum : 0, members: rest });
        }
        return out;
    }
    function valueOf(day, by, series, measure) {                              // one series' value on one day
        let v = 0;
        for (const k of series.members) v += ((day[by] || {})[k] || [0, 0, 0, 0])[MI[measure]] || 0;
        return v;
    }
    function fmtMeasure(v, measure, short) {
        if (measure === 'cost') return short ? ('$' + (v >= 100 || v % 1 === 0 ? Math.round(v) : v < 1 ? v.toFixed(2) : v.toFixed(1))) : money(v);
        if (measure === 'tokens') return compact(v);
        if (measure === 'time') return short ? (v >= 3600 ? (v / 3600).toFixed(v >= 36000 ? 0 : 1) + ' h' : v >= 60 ? Math.round(v / 60) + ' m' : Math.round(v) + ' s') : dur(v);
        return num(v);
    }
    function niceTicks(max) {
        if (!(max > 0)) return [0, 1];
        const mag = Math.pow(10, Math.floor(Math.log10(max)));
        const f = max / mag;
        const step = (f <= 1 ? 0.25 : f <= 2 ? 0.5 : f <= 5 ? 1 : 2) * mag;
        const top = Math.ceil(max / step - 1e-9) * step;
        const out = [];
        for (let t = 0; t <= top + step / 2; t += step) out.push(Number(t.toFixed(10)));
        return out;
    }

    // ------------------------------------------------------------ the markup
    const build = {
        shell() {
            return '<div class="modal-content ui-dlg lg us-dlg">'
                + '<div class="ui-dlg-h"><div><div class="title">Usage</div><div class="sub" data-sub>Loading…</div></div><span class="sp"></span>'
                + '<div class="us-controls"><label class="lbl" for="usagePeriod">Period</label>'
                + '<select id="usagePeriod" class="ui-input" data-period><option value="24h">Last 24 hours</option><option value="7d">Last 7 days</option><option value="30d" selected>Last 30 days</option>'
                + '<option value="90d">Last 90 days</option><option value="month">This month</option><option value="last_month">Last month</option></select>'
                + '<label class="rt-check"><input type="checkbox" data-compare checked> <span data-compare-text>compare with the period before</span></label>'
                + '<button class="ui-btn ghost" data-act="export">Export CSV</button></div>'
                + '<button class="close x" aria-label="Close">×</button></div>'
                + '<div class="ui-dlg-b"><div class="ui-tabs us-tabs"><span class="on" data-tab="overview">Overview</span><span data-tab="seats">Seats &amp; models</span><span data-tab="analyses">Analyses</span><span data-tab="calls">Calls</span></div>'
                + '<div class="us-body" data-body><div class="us-wait"><div class="spin"></div>Loading usage…</div></div>'
                + '<div class="us-foot" data-foot>' + esc(FOOT) + '</div></div></div>';
        },
        wait(text) { return '<div class="us-wait"><div class="spin"></div>' + esc(text || 'Loading usage…') + '</div>'; },
        error(text) { return '<div class="us-error"><div>' + esc(text || 'Usage could not be loaded.') + '</div><button class="ui-btn sm" data-act="retry">Try again</button></div>'; },
        sub(period) {
            const span = period.bucket === 'hour' ? '24 hours' : period.buckets + ' days';
            const ed = period.edition === 'hosted' ? ('hosted' + (period.tier ? ', ' + tierName(period.tier) + ' compute' : '')) : 'the self-hosted edition';
            return period.label + ' · ' + span + ' · ' + ed;
        },
        compareText(period) {
            return 'compare with the ' + (period.bucket === 'hour' ? '24 hours' : period.buckets + ' days') + ' before';
        },
        spark(values) {
            const w = 60, h = 18, n = values.length;
            if (n < 2) return '';
            const mx = Math.max(...values, 0) || 1;
            const pts = values.map((v, i) => (i * w / (n - 1)).toFixed(1) + ',' + (h - 1 - (v / mx) * (h - 2)).toFixed(1));
            return '<svg class="spark" viewBox="0 0 ' + w + ' ' + h + '" width="' + w + '" height="' + h + '" aria-hidden="true"><polyline points="' + pts.join(' ') + '"/><circle cx="' + w + '" cy="' + (h - 1 - (values[n - 1] / mx) * (h - 2)).toFixed(1) + '" r="2.2"/></svg>';
        },
        tile(label, value, delta, sub, series) {
            const d = delta == null ? '' : '<span class="d" title="against the period before">' + (delta > 0 ? '▲' : delta < 0 ? '▼' : '=') + ' ' + (delta >= 9 ? Math.round(1 + delta) + '×' : Math.abs(Math.round(delta * 100)) + '%') + '</span>';
            return '<div class="us-tile"><div class="l">' + esc(label) + '</div><div class="v">' + value + d + '</div><div class="s"><span>' + sub + '</span>' + (series ? build.spark(series) : '') + '</div></div>';
        },
        tiles(data) {
            const t = data.totals, b = data.before, days = data.days, hosted = data.period.edition === 'hosted';
            const delta = (k) => (b && b[k] > 0 && t[k] != null) ? (t[k] - b[k]) / b[k] : null;
            const per = (k) => days.map(d => d[k] || 0);
            const out = [];
            out.push(build.tile('Model cost', money(t.cost), delta('cost'), b ? 'vs ' + money(b.cost) + ' the ' + (data.period.bucket === 'hour' ? '24 hours' : data.period.buckets + ' days') + ' before' : 'in ' + num(t.calls) + ' calls', per('cost')));
            out.push(build.tile('Analyses', num(t.chains), delta('chains'), t.chains ? 'avg ' + money(t.cost / t.chains) + ' · ' + dur(t.time / t.chains) + ' each' : 'none in this period', per('chains')));
            out.push(build.tile('Model calls', num(t.calls), delta('calls'), t.chains ? (t.calls / t.chains).toFixed(1) + ' per analysis' : '', per('calls')));
            let cache;
            if (!t.recorded_in) cache = 'cache not recorded on these calls';
            else cache = pct(t.cached_share) + ' from cache' + (t.recorded_calls < t.calls ? ' on ' + num(t.recorded_calls) + ' of ' + num(t.calls) + ' calls' : '') + ' · ' + money(t.savings) + (t.savings >= 0 ? ' saved' : ' spent on writes');
            out.push(build.tile('Tokens in', compact(t.tokens_in), delta('tokens_in'), cache, per('tokens_in')));
            out.push(build.tile('Tokens out', compact(t.tokens_out), delta('tokens_out'), t.tokens_in ? 'a ' + (t.tokens_out / t.tokens_in).toFixed(2) + ' ratio to the input' : '', per('tokens_out')));
            out.push(build.tile('Model time', dur(t.time), delta('time'), t.calls ? 'a reply every ' + dur(t.time / t.calls) + ' on average' : '', per('time')));
            if (hosted) out.push(build.tile('Compute', money(t.compute), delta('compute'), num(t.compute_chains) + ' analyses charged' + (data.period.tier ? ' · ' + tierName(data.period.tier) : ''), null));
            return '<div class="us-tiles">' + out.join('') + '</div>';
        },
        // the stacked column chart: one column a bucket, the series stacked largest at the base, a 2px gap of the
        // surface between segments, the top segment's corners rounded; hairline gridlines; text in the text tokens
        stacked(days, by, measure, series, isolate, hover, width, height) {
            width = width || 900; height = height || 250;
            const L = 48, R = 8, T = 10, B = 26, pw = width - L - R, ph = height - T - B;
            const shown = isolate ? series.filter(s => s.key === isolate) : series;
            const n = days.length || 1;
            const cols = days.map(d => shown.map(s => valueOf(d, by, s, measure)));
            const max = Math.max(0, ...cols.map(c => c.reduce((a, v) => a + v, 0)));
            const ticks = niceTicks(max), ymax = ticks[ticks.length - 1] || 1;
            const out = ['<svg class="us-chart" viewBox="0 0 ' + width + ' ' + height + '" role="img" aria-label="' + esc(MEASURES[measure] + ' by ' + (days.length && days[0].label && days[0].label.indexOf(':') >= 0 ? 'hour' : 'day') + ', split by ' + BYS[by].toLowerCase()) + '">'];
            for (const t of ticks) {
                const y = T + ph - ph * t / ymax;
                out.push('<line x1="' + L + '" y1="' + y.toFixed(1) + '" x2="' + (L + pw) + '" y2="' + y.toFixed(1) + '" class="grid"/>');
                out.push('<text x="' + (L - 6) + '" y="' + (y + 3.5).toFixed(1) + '" class="tick" text-anchor="end">' + esc(fmtMeasure(t, measure, true)) + '</text>');
            }
            const slot = pw / n, bw = Math.max(2, Math.min(24, slot - Math.max(2, slot * 0.3)));
            const every = Math.max(1, Math.ceil(n / 10));
            days.forEach((d, i) => {
                const x = L + slot * i + (slot - bw) / 2;
                let y = T + ph;
                const parts = cols[i];
                const last = parts.map((v, j) => ph * v / ymax >= 0.6 ? j : -1).filter(j => j >= 0).pop();
                parts.forEach((v, j) => {
                    const h = ph * v / ymax;
                    if (h < 0.6) return;
                    y -= h;
                    const hh = Math.max(h - 2, 0.5);                            // 2px of the surface between segments
                    if (j === last && h >= 4) {
                        const r = Math.min(3, bw / 2);
                        out.push('<path class="' + shown[j].cls + '" d="M' + x.toFixed(1) + ',' + (y + hh).toFixed(1) + ' V' + (y + r).toFixed(1) + ' a' + r + ',' + r + ' 0 0 1 ' + r + ',-' + r + ' H' + (x + bw - r).toFixed(1) + ' a' + r + ',' + r + ' 0 0 1 ' + r + ',' + r + ' V' + (y + hh).toFixed(1) + ' Z"/>');
                    } else {
                        out.push('<rect class="' + shown[j].cls + '" x="' + x.toFixed(1) + '" y="' + y.toFixed(1) + '" width="' + bw.toFixed(1) + '" height="' + hh.toFixed(1) + '"/>');
                    }
                });
                if (i % every === 0) out.push('<text x="' + (x + bw / 2).toFixed(1) + '" y="' + (T + ph + 16) + '" class="tick" text-anchor="middle">' + esc(d.label) + '</text>');
                if (i === hover) out.push('<rect class="hover-band" x="' + (x - 3).toFixed(1) + '" y="' + T + '" width="' + (bw + 6).toFixed(1) + '" height="' + ph + '"/>');
                out.push('<rect class="col" data-i="' + i + '" x="' + (L + slot * i).toFixed(1) + '" y="' + T + '" width="' + slot.toFixed(1) + '" height="' + ph + '" fill="transparent"/>');
            });
            out.push('</svg>');
            return out.join('');
        },
        legend(series, by, measure, isolate) {
            const total = series.reduce((s, x) => s + x.total, 0);
            const rows = series.map(s => '<div class="r' + (isolate ? (isolate === s.key ? ' only' : ' off') : '') + '" data-series="' + esc(s.key) + '" title="' + esc(s.members.length > 1 ? s.members.join(', ') : 'click to isolate') + '">'
                + '<i class="us-sw ' + s.cls + '"></i><span class="n">' + esc(s.key) + '</span><span class="v">' + esc(fmtMeasure(s.total, measure)) + '</span><span class="p">' + pct(s.share) + '</span></div>').join('');
            return '<div class="us-legend"><div class="h">' + esc(BYS[by]) + ' <span class="n">· click one to isolate it</span></div>' + rows
                + '<div class="r sum"><i></i><span class="n">Total</span><span class="v">' + esc(fmtMeasure(total, measure)) + '</span><span class="p">100%</span></div></div>';
        },
        tooltip(day, by, measure, series) {
            const rows = series.map(s => [s, valueOf(day, by, s, measure)]).filter(([s, v]) => v > 0)
                .map(([s, v]) => '<div class="r"><i class="us-sw ' + s.cls + '"></i><span>' + esc(s.key) + '</span><b>' + esc(fmtMeasure(v, measure)) + '</b></div>').join('');
            const head = esc(day.label) + ' · <b>' + esc(money(day.cost)) + '</b> · ' + num(day.chains) + (day.chains === 1 ? ' analysis' : ' analyses') + ' · ' + num(day.calls) + ' calls · ' + compact((day.tokens_in || 0) + (day.tokens_out || 0)) + ' tokens · ' + dur(day.time);
            return '<div class="us-tip"><div class="h">' + head + '</div>' + (rows || '<div class="r"><i></i><span>nothing</span><b></b></div>') + '</div>';
        },
        chartSection(data, st) {
            const series = seriesOf(data.days, st.by, st.measure);
            const seg = (opts, on, attr) => '<span class="ui-seg">' + Object.keys(opts).map(k => '<span class="' + (k === on ? 'on' : '') + '" data-' + attr + '="' + k + '">' + esc(opts[k]) + '</span>').join('') + '</span>';
            const unit = data.period.bucket === 'hour' ? 'hour' : 'day';
            const empty = !data.totals.calls;
            return '<div class="us-sec" data-sec="chart"><div class="h">Over time <span class="n">— one column a ' + unit + '; hover a column for its split</span><span class="sp"></span>' + seg(MEASURES, st.measure, 'measure') + seg(BYS, st.by, 'by') + '</div>'
                + '<div class="us-chartrow"><div class="us-chartbox" data-chart>' + (empty ? '<div class="us-empty">No model calls in this period.</div>' : build.stacked(data.days, st.by, st.measure, series, st.isolate, -1)) + '</div>'
                + build.legend(series, st.by, st.measure, st.isolate) + '</div></div>';
        },
        standsOut(lines) {
            if (!lines || !lines.length) return '';
            return '<div class="us-sec"><div class="h">What stands out <span class="n">— computed from the records, no model</span></div><div class="ui-kv us-kv">'
                + lines.map(l => '<b>' + esc(l.head) + '</b><span>' + esc(l.text) + '</span>').join('') + '</div></div>';
        },
        overview(data, st) {
            return build.tiles(data) + build.chartSection(data, st) + build.standsOut(data.stands_out);
        },
        // the two tables, sortable by a click on a heading; a thin bar for the share of the cost
        seatsTable(seats, totals, sort) {
            const mx = Math.max(...seats.map(s => s.cost), 0) || 1, tot = totals.cost || 1;
            const rows = sortRows(seats, sort, 'seat');
            const series = seriesOf([{ seats: Object.fromEntries(seats.map(s => [s.seat, [s.cost, 0, 0, 0]])) }], 'seats', 'cost');
            const cls = Object.fromEntries(series.flatMap(s => s.members.map(m => [m, s.cls])));
            const th = (k, label, numeric) => '<th class="' + (numeric ? 'num' : '') + (sort === k ? ' on' : '') + '" data-sort="' + k + '">' + label + '</th>';
            return '<table class="ui-table us-table" data-table="seats"><thead><tr>' + th('seat', 'Seat') + th('calls', 'Calls', 1) + th('chains', 'Analyses', 1) + th('tokens_in', 'Tokens in', 1) + th('cached_share', 'cached', 1) + th('tokens_out', 'Tokens out', 1)
                + th('cost', 'Cost', 1) + '<th>Share</th>' + th('per_call', 'Per call', 1) + th('tps', 'tok/s', 1) + '</tr></thead><tbody>'
                + rows.map(s => '<tr><td class="label"><i class="us-sw ' + (cls[s.seat] || 'us-s0') + '"></i>' + esc(s.seat) + '</td><td class="num">' + num(s.calls) + '</td><td class="num">' + num(s.chains) + '</td><td class="num">' + compact(s.tokens_in) + '</td>'
                    + '<td class="num muted">' + pct(s.cached_share) + '</td><td class="num">' + compact(s.tokens_out) + '</td><td class="num">' + money(s.cost) + '</td>'
                    + '<td class="bar"><span style="width:' + Math.round(s.cost / mx * 100) + '%"></span><em>' + pct(s.cost / tot) + '</em></td><td class="num muted">' + (s.calls ? dur(s.time / s.calls) : '—') + '</td><td class="num muted">' + (s.tps == null ? '—' : Math.round(s.tps)) + '</td></tr>').join('')
                + '</tbody></table>';
        },
        modelsTable(models, totals, sort) {
            const mx = Math.max(...models.map(m => m.cost), 0) || 1, tot = totals.cost || 1;
            const rows = sortRows(models, sort, 'model');
            const th = (k, label, numeric) => '<th class="' + (numeric ? 'num' : '') + (sort === k ? ' on' : '') + '" data-sort="' + k + '">' + label + '</th>';
            const price = (m) => (m.price_in == null && m.price_out == null) ? '—' : (m.price_in == null ? '—' : money(m.price_in)) + ' / ' + (m.price_out == null ? '—' : money(m.price_out));
            return '<table class="ui-table us-table" data-table="models"><thead><tr>' + th('model', 'Model') + th('calls', 'Calls', 1) + th('tokens_in', 'Tokens in', 1) + th('cached_share', 'cached', 1) + th('tokens_out', 'Tokens out', 1)
                + th('cost', 'Cost', 1) + '<th>Share</th><th class="num" title="the configuration\'s list price per million tokens, in and out">List price / 1M in · out</th>' + th('tps', 'tok/s', 1) + '</tr></thead><tbody>'
                + rows.map(m => '<tr><td class="label">' + esc(m.model) + (m.provider ? '<span class="muted"> · ' + esc(m.provider) + '</span>' : '') + '</td><td class="num">' + num(m.calls) + '</td><td class="num">' + compact(m.tokens_in) + '</td>'
                    + '<td class="num muted">' + pct(m.cached_share) + '</td><td class="num">' + compact(m.tokens_out) + '</td><td class="num">' + money(m.cost) + '</td>'
                    + '<td class="bar"><span style="width:' + Math.round(m.cost / mx * 100) + '%"></span><em>' + pct(m.cost / tot) + '</em></td><td class="num muted">' + esc(price(m)) + '</td><td class="num muted">' + (m.tps == null ? '—' : Math.round(m.tps)) + '</td></tr>').join('')
                + '</tbody></table>';
        },
        seatsTab(data, st) {
            return '<div class="us-sec"><div class="h">Seats <span class="n">— who spent what; a seat is one role the analyst plays (the Analyst writes the cells, the Reviewer judges them, the Reader reads documents, the Coder codes the context, the Promoter makes routines…)</span></div>' + build.seatsTable(data.seats, data.totals, st.sort.seats) + '</div>'
                + '<div class="us-sec"><div class="h">Models <span class="n">— the list price is the configuration’s, per million tokens; the cost is what the calls came to at it</span></div>' + build.modelsTable(data.models, data.totals, st.sort.models) + '</div>';
        },
        // the ledger: every chain of the period with what it cost, grouped by day; pick one for its breakdown
        ledgerItem(e, mx, on) {
            const meta = [timeLabel(e.when), e.mode || (e.kind === 'routine' ? 'Routine' : e.kind === 'other' ? '' : ''), e.cells != null ? e.cells + ' cell' + (e.cells === 1 ? '' : 's') : '', e.wall != null && e.wall > 0 ? dur(e.wall) : dur(e.time)].filter(Boolean).map(esc).join(' · ');
            return '<div class="it' + (on ? ' on' : '') + '" data-chain="' + esc(e.chain) + '"><span class="q" title="' + esc(e.question) + '">' + esc(e.question || '(no question recorded)') + '</span><span class="c">' + money(e.cost) + '</span>'
                + '<span class="m">' + meta + (e.outcome ? ' · ' + chip(e.outcome) : '') + '</span><span class="bar"><span style="width:' + Math.round(e.cost / mx * 100) + '%"></span></span></div>';
        },
        ledger(entries, st) {
            if (!entries.length) return '<div class="none">No analyses match.</div>';
            const mx = Math.max(...entries.map(e => e.cost), 0) || 1;
            if (st.ledgerSort !== 'date') return entries.map(e => build.ledgerItem(e, mx, e.chain === st.pick)).join('');
            const out = []; let day = null;
            for (const e of entries) {
                const d = dayOf(e.when);
                if (d !== day) {
                    day = d;
                    const same = entries.filter(x => dayOf(x.when) === d);
                    out.push('<div class="day">' + esc(dayLabel(e.when)) + ' · ' + same.length + (same.length === 1 ? ' analysis' : ' analyses') + ' · ' + money(same.reduce((s, x) => s + x.cost, 0)) + '</div>');
                }
                out.push(build.ledgerItem(e, mx, e.chain === st.pick));
            }
            return out.join('');
        },
        filterLedger(entries, st) {
            const q = (st.find || '').trim().toLowerCase();
            let out = entries.filter(e => (!q || (e.question + ' ' + e.title).toLowerCase().includes(q)) && (st.mode === 'all' || (e.mode || (e.kind === 'routine' ? 'Routine' : 'Other')) === st.mode)
                && (st.outcome === 'all' || outcomeGroup(e.outcome) === st.outcome));
            if (st.ledgerSort === 'cost') out = out.slice().sort((a, b) => b.cost - a.cost || (a.when < b.when ? 1 : -1));
            else if (st.ledgerSort === 'time') out = out.slice().sort((a, b) => ((b.wall || b.time) - (a.wall || a.time)) || (a.when < b.when ? 1 : -1));
            return out;
        },
        analysesTab(data, st) {
            const all = data.analyses || [];
            const modes = Array.from(new Set(all.map(e => e.mode || (e.kind === 'routine' ? 'Routine' : 'Other')))).sort();
            const groups = Array.from(new Set(all.map(e => outcomeGroup(e.outcome)))).filter(Boolean).sort();
            const shown = build.filterLedger(all, st);
            const opt = (v, label, on) => '<option value="' + esc(v) + '"' + (on ? ' selected' : '') + '>' + esc(label) + '</option>';
            const runs = all.filter(e => e.kind === 'analysis' || e.kind === 'ideas').length, others = all.length - runs;
            const note = num(runs) + (runs === 1 ? ' analysis' : ' analyses') + (others ? ' and ' + others + ' other chain' + (others === 1 ? '' : 's') : '') + ' · ' + money(data.totals.cost) + ' · ' + dur(data.totals.time) + ' of model time';
            return '<div class="us-sec"><div class="h">Analyses <span class="n">— every question with what it cost; pick one for its breakdown</span><span class="sp"></span><span class="us-note">' + esc(note) + '</span></div>'
                + '<div class="us-filters"><input class="ui-input find" data-find placeholder="Find a question…" value="' + esc(st.find || '') + '">'
                + '<select class="ui-input" data-mode>' + opt('all', 'Every mode', st.mode === 'all') + modes.map(m => opt(m, m, st.mode === m)).join('') + '</select>'
                + '<select class="ui-input" data-outcome>' + opt('all', 'Every outcome', st.outcome === 'all') + groups.map(g => opt(g, g, st.outcome === g)).join('') + '</select>'
                + '<span class="ui-seg"><span class="' + (st.ledgerSort === 'date' ? 'on' : '') + '" data-lsort="date">By date</span><span class="' + (st.ledgerSort === 'cost' ? 'on' : '') + '" data-lsort="cost">By cost</span><span class="' + (st.ledgerSort === 'time' ? 'on' : '') + '" data-lsort="time">By time</span></span>'
                + '<span class="us-note">' + (shown.length === all.length ? '' : esc(shown.length + ' of ' + all.length + ' shown')) + '</span></div>'
                + '<div class="us-split"><div class="us-list" data-list>' + build.ledger(shown, st) + '</div><div class="us-detail" data-detail>' + (st.pick ? build.wait('Loading the analysis…') : '<div class="pick">Pick an analysis on the left for its breakdown: its seats, its calls in time, its models.</div>') + '</div></div></div>';
        },
        // the detail pane: the figures, the seats ranked, the calls laid out in time, the models
        timeline(det, width) {
            const W = width || 600, calls = det.calls || [], seats = (det.seats || []).map(s => s.seat), span = Math.max(det.span || 0, 1);
            const H = seats.length * 11 + 22;
            const series = seriesOf([{ seats: Object.fromEntries((det.seats || []).map(s => [s.seat, [s.cost, 0, 0, 0]])) }], 'seats', 'cost');
            const cls = Object.fromEntries(series.flatMap(s => s.members.map(m => [m, s.cls])));
            const marks = calls.map((c, i) => {
                const x = c.at / span * W, w = Math.max(c.elapsed / span * W - 1.5, 1.5), row = seats.indexOf(c.seat);
                return '<rect class="call ' + (cls[c.seat] || 'us-s0') + '" data-i="' + i + '" x="' + x.toFixed(1) + '" y="' + (Math.max(row, 0) * 11 + 2) + '" width="' + w.toFixed(1) + '" height="8" rx="2"/>';
            }).join('');
            return '<svg class="us-tl" viewBox="0 0 ' + W + ' ' + H + '" role="img" aria-label="the calls in time, one row per seat">' + marks
                + '<line x1="0" y1="' + (H - 2) + '" x2="' + W + '" y2="' + (H - 2) + '" class="grid"/><text x="0" y="' + (H - 5) + '" class="tick">0:00</text><text x="' + W + '" y="' + (H - 5) + '" class="tick" text-anchor="end">' + clock(span) + '</text></svg>';
        },
        callTip(c) {
            const cache = c.cached == null ? 'cache not recorded' : (compact(c.cached) + ' cached' + (c.written ? ', ' + compact(c.written) + ' written' : ''));
            return '<div class="us-tip"><div class="h"><b>' + esc(c.seat) + '</b> · ' + esc(c.model) + '</div><div class="r"><i></i><span>at ' + esc(clock(c.at)) + ' for ' + esc(dur(c.elapsed)) + '</span><b></b></div>'
                + '<div class="r"><i></i><span>' + compact(c.tokens_in) + ' in · ' + esc(cache) + '</span><b></b></div><div class="r"><i></i><span>' + compact(c.tokens_out) + ' out' + (c.tps ? ' · ' + Math.round(c.tps) + ' tok/s' : '') + '</span><b></b></div>'
                + '<div class="r"><i></i><span>cost</span><b>' + money(c.cost) + '</b></div>' + ((c.search_fee || c.image_fee) ? '<div class="r"><i></i><span>fees inside it</span><b>' + money((c.search_fee || 0) + (c.image_fee || 0)) + '</b></div>' : '') + '</div>';
        },
        detail(det) {
            const a = det.analysis, t = det.totals;
            const series = seriesOf([{ seats: Object.fromEntries((det.seats || []).map(s => [s.seat, [s.cost, 0, 0, 0]])) }], 'seats', 'cost');
            const cls = Object.fromEntries(series.flatMap(s => s.members.map(m => [m, s.cls])));
            const mx = Math.max(...(det.seats || []).map(s => s.cost), 0) || 1;
            const run = a.thread && (a.kind === 'analysis' || a.kind === 'ideas'), canOpen = run && a.saved;      // the page opens a chain from its saved favourite
            const meta = [whenLabel(a.when), a.mode, a.cells != null ? a.cells + ' cell' + (a.cells === 1 ? '' : 's') : '', t.calls + ' call' + (t.calls === 1 ? '' : 's'), a.wall ? dur(a.wall) : ''].filter(Boolean).map(esc).join(' · ');
            const kpis = [[money(t.cost), 'model cost'], [compact(t.tokens_in), 'tokens in' + (t.recorded_in ? ' · ' + pct(t.cached_share) + ' cached' : '')], [compact(t.tokens_out), 'tokens out'],
                          [dur(t.time), 'model time' + (a.wall && a.wall > t.time ? ' of ' + dur(a.wall) : '')], [t.recorded_in ? money(t.savings) : '—', 'cache savings' + (t.recorded_in ? '' : ' (not recorded)')]];
            if (t.compute) kpis.push([money(t.compute), 'compute charge']);
            const rank = (det.seats || []).map(s => '<div class="r"><i class="us-sw ' + (cls[s.seat] || 'us-s0') + '"></i><span class="n">' + esc(s.seat) + ' <small>· ' + s.calls + ' call' + (s.calls === 1 ? '' : 's') + '</small></span><span class="b"><span class="' + (cls[s.seat] || 'us-s0') + '" style="width:' + Math.round(s.cost / mx * 100) + '%"></span></span><span class="v">' + money(s.cost) + '</span></div>').join('');
            const models = (det.models || []).map(m => '<b>' + esc(m.model) + '</b><span>' + m.calls + ' call' + (m.calls === 1 ? '' : 's') + ' · ' + compact(m.tokens_in) + ' in' + (m.recorded_in ? ' (' + pct(m.cached_share) + ' cached)' : '') + ' · ' + compact(m.tokens_out) + ' out · ' + money(m.cost) + '</span>').join('');
            return '<div class="us-detail-h"><div class="q">' + esc(a.question || '(no question recorded)') + '</div>' + (a.title ? '<div class="t">' + esc(a.title) + '</div>' : '')
                + '<div class="m">' + meta + (a.outcome ? ' · ' + chip(a.outcome) : '') + (canOpen ? ' <a class="open" data-act="open" data-thread="' + esc(a.thread) + '" data-chain="' + esc(a.chain) + '">open the analysis →</a>' : (run ? ' <span class="muted" title="save the analysis as a favourite to open it from here">· not saved</span>' : '')) + '</div></div>'
                + '<div class="us-kpis">' + kpis.map(([v, l]) => '<div><b>' + v + '</b><span>' + esc(l) + '</span></div>').join('') + '</div>'
                + '<div class="us-sec"><div class="h">By seat <span class="n">— the cost of this analysis, who spent it</span></div><div class="us-rank">' + rank + '</div></div>'
                + '<div class="us-sec"><div class="h">The calls in time <span class="n">— one row per seat, left to right; hover a call for its model, tokens and cost</span></div><div class="us-tlbox" data-tl>' + build.timeline(det) + '</div>'
                + '<div class="us-tlkey">' + (det.seats || []).map(s => '<span><i class="us-sw ' + (cls[s.seat] || 'us-s0') + '"></i>' + esc(s.seat) + '</span>').join('') + '</div></div>'
                + '<div class="us-sec"><div class="h">Models</div><div class="ui-kv us-kv models">' + models + '</div></div>';
        },
        // the raw rows, a page at a time
        callsTab(st) {
            const rows = st.calls || [];
            const body = rows.map(c => '<tr><td class="muted nowrap">' + esc(whenLabel(c.t)) + '</td><td class="link"><a href="#" data-chain="' + esc(c.chain) + '" title="this analysis in the ledger">' + esc(c.chain) + '</a></td><td>' + esc(c.seat) + '</td><td class="muted">' + esc(c.model) + '</td>'
                + '<td class="num">' + num(c.tokens_in) + '</td><td class="num muted">' + (c.cached == null ? '—' : num(c.cached)) + '</td><td class="num muted">' + (c.written == null ? '—' : num(c.written)) + '</td><td class="num">' + num(c.tokens_out) + '</td>'
                + '<td class="num muted">' + esc(dur(c.elapsed)) + '</td><td class="num muted">' + (c.tps ? Math.round(c.tps) : '—') + '</td><td class="num">' + money(c.cost) + '</td><td class="num muted">' + (c.savings == null ? '—' : money(c.savings)) + '</td>'
                + '<td class="num muted">' + ((c.search_fee || c.image_fee) ? money((c.search_fee || 0) + (c.image_fee || 0)) : '—') + '</td></tr>').join('');
            const from = (st.callsPage - 1) * st.callsSize + 1, to = from + rows.length - 1;
            return '<div class="us-sec"><div class="h">Calls <span class="n">— one row per model call, newest first, as recorded; a dash where the cache was not recorded</span><span class="sp"></span>'
                + '<span class="us-pager"><span>' + (rows.length ? 'rows ' + num(from) + ' – ' + num(to) : 'no rows') + '</span><button class="ui-btn sm" data-act="newer"' + (st.callsPage > 1 ? '' : ' disabled') + '>Newer</button><button class="ui-btn sm" data-act="older"' + (st.callsMore ? '' : ' disabled') + '>Older</button></span></div>'
                + '<table class="ui-table us-table" data-table="calls"><thead><tr><th>When</th><th>Chain</th><th>Seat</th><th>Model</th><th class="num">Tokens in</th><th class="num">cached</th><th class="num">written</th><th class="num">Tokens out</th><th class="num">Time</th><th class="num">tok/s</th><th class="num">Cost</th><th class="num">Savings</th><th class="num">Fees</th></tr></thead>'
                + '<tbody>' + (body || '<tr><td colspan="13" class="muted">No calls in this period.</td></tr>') + '</tbody></table></div>';
        },
        foot(data) {
            const t = data && data.totals;
            let line = FOOT;
            if (t && t.calls && t.recorded_calls < t.calls) line += ' The cache split is recorded on calls made since this dialog’s release (' + num(t.recorded_calls) + ' of ' + num(t.calls) + ' calls in this period); earlier calls show no cache figures.';
            if (data && data.period && data.period.truncated) line += ' This period has more rows than one answer aggregates: the figures stop at the first ' + num(data.period.rows) + ' calls.';
            return esc(line);
        }
    };
    function outcomeGroup(o) {
        o = String(o || '');
        if (!o) return '';
        if (o.startsWith('failed') || o === 'refused' || o === 'replay failed') return 'failed';
        return o;
    }
    function sortRows(rows, sort, nameKey) {
        const key = sort || 'cost';
        const val = (r) => key === 'per_call' ? (r.calls ? r.time / r.calls : 0) : r[key];
        return rows.slice().sort((a, b) => {
            const x = val(a), y = val(b);
            if (typeof x === 'string' || typeof y === 'string') return String(x).localeCompare(String(y));
            return ((y == null ? -1 : y) - (x == null ? -1 : x)) || String(a[nameKey]).localeCompare(String(b[nameKey]));
        });
    }

    // ------------------------------------------------------------ the dialog
    let modal = null, seq = 0;
    const st = { period: '30d', compare: true, tab: 'overview', data: null, measure: 'cost', by: 'seats', isolate: null, sort: { seats: 'cost', models: 'cost' },
                 ledgerSort: 'date', find: '', mode: 'all', outcome: 'all', pick: null, detail: null, calls: [], callsPage: 1, callsSize: 100, callsMore: false, loading: false, error: '' };

    function ensure() {
        if (modal) return modal;
        modal = document.createElement('div'); modal.id = 'usageModal'; modal.className = 'modal ui-modal'; modal.style.display = 'none';
        modal.innerHTML = build.shell();
        document.body.appendChild(modal);
        modal.addEventListener('click', onClick);
        modal.addEventListener('change', onChange);
        modal.addEventListener('input', e => {
            if (e.target.matches('[data-find]')) { st.find = e.target.value; renderList(); }
        });
        modal.addEventListener('mouseover', onHover);
        modal.addEventListener('mouseout', e => {
            if (e.target.closest && (e.target.closest('[data-chart]') || e.target.closest('[data-tl]'))) {
                const to = e.relatedTarget;
                if (!to || !(to.closest && (to.closest('[data-chart]') || to.closest('[data-tl]')))) hideTip();
            }
        });
        document.addEventListener('keydown', e => { if (e.key === 'Escape' && modal.style.display !== 'none') close(); });
        return modal;
    }
    function open() {
        const m = ensure();
        m.style.display = 'flex';
        if (!st.data) load();
        else render();
    }
    function close() { if (modal) modal.style.display = 'none'; hideTip(); }
    function load() {
        const m = ensure(), my = ++seq;
        st.loading = true; st.error = ''; st.isolate = null; st.pick = null; st.detail = null; st.calls = []; st.callsPage = 1; st.callsMore = false;
        m.querySelector('[data-body]').innerHTML = build.wait();
        m.querySelector('[data-sub]').textContent = 'Loading…';
        return fetchJson('/usage?period=' + encodeURIComponent(st.period) + '&compare=' + (st.compare ? 1 : 0) + '&tz=' + tz()).then(res => {
            if (my !== seq) return;
            st.loading = false;
            if (!res.ok || !res.json || res.json.error) { st.error = (res.json && res.json.error) || ('the server answered ' + res.status); st.data = null; render(); return; }
            st.data = res.json;
            render();
            if (st.tab === 'calls') loadCalls();
        }).catch(err => { if (my !== seq) return; st.loading = false; st.error = err.message || String(err); st.data = null; render(); });
    }
    function render() {
        const m = ensure(), body = m.querySelector('[data-body]');
        m.querySelectorAll('.us-tabs [data-tab]').forEach(t => t.classList.toggle('on', t.getAttribute('data-tab') === st.tab));
        if (st.error) { body.innerHTML = build.error(st.error); return; }
        if (!st.data) { body.innerHTML = build.wait(); return; }
        const d = st.data;
        m.querySelector('[data-sub]').textContent = build.sub(d.period);
        m.querySelector('[data-compare-text]').textContent = build.compareText(d.period);
        m.querySelector('[data-foot]').innerHTML = build.foot(d);
        if (st.tab === 'overview') body.innerHTML = build.overview(d, st);
        else if (st.tab === 'seats') body.innerHTML = build.seatsTab(d, st);
        else if (st.tab === 'analyses') { body.innerHTML = build.analysesTab(d, st); if (st.pick) renderDetail(); }
        else body.innerHTML = build.callsTab(st);
    }
    function renderChart() {
        const m = ensure(), sec = m.querySelector('[data-sec="chart"]');
        if (!sec || !st.data) return;
        sec.outerHTML = build.chartSection(st.data, st);
    }
    function renderList() {
        const m = ensure(), list = m.querySelector('[data-list]');
        if (!list || !st.data) return;
        const shown = build.filterLedger(st.data.analyses || [], st);
        list.innerHTML = build.ledger(shown, st);
        const note = m.querySelector('.us-filters .us-note');
        if (note) note.textContent = shown.length === (st.data.analyses || []).length ? '' : shown.length + ' of ' + (st.data.analyses || []).length + ' shown';
    }
    function renderDetail() {
        const m = ensure(), pane = m.querySelector('[data-detail]');
        if (!pane) return;
        if (!st.pick) { pane.innerHTML = '<div class="pick">Pick an analysis on the left for its breakdown: its seats, its calls in time, its models.</div>'; return; }
        if (st.detail && st.detail.analysis && st.detail.analysis.chain === st.pick) { pane.innerHTML = build.detail(st.detail); return; }
        pane.innerHTML = build.wait('Loading the analysis…');
        const chain = st.pick, my = ++seq;
        fetchJson('/usage/analysis/' + encodeURIComponent(chain) + '?tz=' + tz()).then(res => {
            if (my !== seq || st.pick !== chain) return;
            if (!res.ok || !res.json || res.json.error) { pane.innerHTML = build.error((res.json && res.json.error) || ('the server answered ' + res.status)).replace('data-act="retry"', 'data-act="redetail"'); return; }
            st.detail = res.json;
            pane.innerHTML = build.detail(st.detail);
        }).catch(err => { if (my === seq) pane.innerHTML = build.error(err.message || String(err)).replace('data-act="retry"', 'data-act="redetail"'); });
    }
    function loadCalls() {
        const m = ensure(), my = ++seq, body = m.querySelector('[data-body]');
        body.innerHTML = build.wait('Loading the calls…');
        fetchJson('/usage/calls?period=' + encodeURIComponent(st.period) + '&tz=' + tz() + '&page=' + st.callsPage + '&size=' + st.callsSize).then(res => {
            if (my !== seq || st.tab !== 'calls') return;
            if (!res.ok || !res.json || res.json.error) { body.innerHTML = build.error((res.json && res.json.error) || ('the server answered ' + res.status)).replace('data-act="retry"', 'data-act="recalls"'); return; }
            st.calls = res.json.rows || []; st.callsMore = !!res.json.more;
            body.innerHTML = build.callsTab(st);
        }).catch(err => { if (my === seq) body.innerHTML = build.error(err.message || String(err)).replace('data-act="retry"', 'data-act="recalls"'); });
    }
    function exportCsv() {
        const f = (window.authService && window.authService.fetch) ? window.authService.fetch.bind(window.authService) : fetch;
        const url = '/usage/export.csv?period=' + encodeURIComponent(st.period) + '&tz=' + tz();
        f(url).then(async r => {
            if (!r.ok) throw new Error('the server answered ' + r.status);
            const blob = await r.blob();
            const name = (r.headers.get('Content-Disposition') || '').match(/filename="([^"]+)"/);
            const a = document.createElement('a'); a.href = URL.createObjectURL(blob); a.download = name ? name[1] : 'usage.csv';
            document.body.appendChild(a); a.click(); a.remove();
            setTimeout(() => URL.revokeObjectURL(a.href), 2000);
        }).catch(err => toast('The export failed: ' + (err.message || err)));
    }
    function showTip(box, html, x, y) {
        hideTip();
        const tip = document.createElement('div'); tip.innerHTML = html; const el = tip.firstElementChild;
        el.setAttribute('data-tip', '1');
        box.appendChild(el);
        const bw = box.clientWidth || 600, tw = el.offsetWidth || 200;
        el.style.left = Math.max(4, Math.min(x + 14, bw - tw - 4)) + 'px';
        el.style.top = Math.max(4, y - 10) + 'px';
    }
    function hideTip() { if (modal) modal.querySelectorAll('[data-tip], .us-chart .hover-band').forEach(t => t.remove()); }
    function onHover(e) {
        const col = e.target.closest && e.target.closest('.us-chart [data-i]');
        if (col && st.data) {
            const box = col.closest('[data-chart]'), i = Number(col.getAttribute('data-i')), day = st.data.days[i];
            if (!box || !day) return;
            const series = seriesOf(st.data.days, st.by, st.measure).filter(s => !st.isolate || s.key === st.isolate);
            const r = box.getBoundingClientRect();
            showTip(box, build.tooltip(day, st.by, st.measure, series), e.clientX - r.left, e.clientY - r.top);
            box.querySelectorAll('.hover-band').forEach(b => b.remove());
            const svg = box.querySelector('svg'), band = col.cloneNode(false);
            band.setAttribute('class', 'hover-band'); band.removeAttribute('data-i'); band.removeAttribute('fill');
            if (svg) svg.insertBefore(band, col);
            return;
        }
        const call = e.target.closest && e.target.closest('.us-tl [data-i]');
        if (call && st.detail) {
            const box = call.closest('[data-tl]'), c = st.detail.calls[Number(call.getAttribute('data-i'))];
            if (!box || !c) return;
            const r = box.getBoundingClientRect();
            showTip(box, build.callTip(c), e.clientX - r.left, e.clientY - r.top);
        }
    }
    function onChange(e) {
        const t = e.target;
        if (t.matches('[data-period]')) { st.period = t.value; load(); return; }
        if (t.matches('[data-compare]')) { st.compare = t.checked; load(); return; }
        if (t.matches('[data-mode]')) { st.mode = t.value; renderList(); return; }
        if (t.matches('[data-outcome]')) { st.outcome = t.value; renderList(); return; }
    }
    function onClick(e) {
        if (e.target === modal) { close(); return; }
        const t = e.target;
        if (t.closest('.ui-dlg-h .x')) { close(); return; }
        const tab = t.closest('.us-tabs [data-tab]');
        if (tab) { st.tab = tab.getAttribute('data-tab'); if (st.tab === 'calls' && st.data) { render(); loadCalls(); } else render(); return; }
        const act = t.closest('[data-act]');
        if (act) {
            const a = act.getAttribute('data-act');
            if (a === 'export') exportCsv();
            else if (a === 'retry') load();
            else if (a === 'redetail') { st.detail = null; renderDetail(); }
            else if (a === 'recalls') loadCalls();
            else if (a === 'newer') { st.callsPage = Math.max(1, st.callsPage - 1); loadCalls(); }
            else if (a === 'older') { st.callsPage += 1; loadCalls(); }
            else if (a === 'open') {
                const thread = act.getAttribute('data-thread'), chain = act.getAttribute('data-chain');
                close();
                if (typeof loadThreadContent === 'function') loadThreadContent(thread, chain); else toast('The analysis could not be opened from here.');
            }
            return;
        }
        const m = t.closest('[data-measure]'); if (m) { st.measure = m.getAttribute('data-measure'); renderChart(); return; }
        const by = t.closest('[data-by]'); if (by) { st.by = by.getAttribute('data-by'); st.isolate = null; renderChart(); return; }
        const row = t.closest('.us-legend .r[data-series]'); if (row) { const k = row.getAttribute('data-series'); st.isolate = st.isolate === k ? null : k; renderChart(); return; }
        const th = t.closest('.us-table th[data-sort]');
        if (th) {
            const table = th.closest('[data-table]').getAttribute('data-table');
            if (table in st.sort) { st.sort[table] = th.getAttribute('data-sort'); render(); }
            return;
        }
        const ls = t.closest('[data-lsort]'); if (ls) { st.ledgerSort = ls.getAttribute('data-lsort'); render(); return; }
        const it = t.closest('.us-list .it[data-chain]');
        if (it) { st.pick = it.getAttribute('data-chain'); st.detail = null; modal.querySelectorAll('.us-list .it').forEach(x => x.classList.toggle('on', x === it)); renderDetail(); return; }
        const link = t.closest('.us-table td.link a[data-chain]');
        if (link) { e.preventDefault(); st.tab = 'analyses'; st.pick = link.getAttribute('data-chain'); st.detail = null; st.find = ''; st.mode = 'all'; st.outcome = 'all'; render(); return; }
    }
    function bind() {
        const opt = document.querySelector('.usage-option');
        if (opt && !opt.__usage) { opt.__usage = true; opt.addEventListener('click', open); }
    }
    function initialize() { bind(); }

    window.UsageUI = { initialize, open, close, load, build, state: st, seriesOf, niceTicks };
    window.__usageBuild = build;
})();
