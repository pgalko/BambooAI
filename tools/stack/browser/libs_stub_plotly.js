// Plotly stand-in. A JSON figure is drawn plainly: a line or a set of points to a scatter trace, bars to a bar trace, a
// box to a box trace - a panel to each pair of axes the traces name - under the figure's title, with the names of its
// traces and the words a layout puts across it. Enough to see that a figure was drawn and what it holds; nothing of the
// real library is here (2026-11-18: a JSON figure had been an empty box). PNG figures do not need Plotly.
(function () {
    const INK = ['#4c9be8', '#e8a23c', '#5fbf7a', '#d86a6a', '#a98be0', '#58c4c4'];
    const esc = s => String(s == null ? '' : s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
    const r1 = v => Math.round(v * 10) / 10;
    const numbers = a => (Array.isArray(a) ? a.map(Number) : []);
    const range = vs => { const ok = vs.filter(Number.isFinite), lo = Math.min.apply(null, ok), hi = Math.max.apply(null, ok); return ok.length ? [lo, hi > lo ? hi : lo + 1] : [0, 1]; };
    // where a trace's values stand: its y against its x - numbers as they are, names side by side; in three dimensions
    // its z against its x, both leaning with its y into the depth
    function points(t) {
        const deep = Array.isArray(t.z), ys = numbers(deep ? t.z : t.y), lean = deep ? numbers(t.y) : [];
        const xs = Array.isArray(t.x) && t.x.every(v => Number.isFinite(Number(v))) ? numbers(t.x) : ys.map((_, i) => i);
        return ys.map((y, i) => [xs[i] + (deep ? 0.5 * lean[i] : 0), y + (deep ? 0.3 * lean[i] : 0)]).filter(p => p.every(Number.isFinite));
    }
    // one pair of axes: its frame and the marks of the traces it holds (first: the place of its first trace among the figure's, for its colour)
    function panel(traces, box, first) {
        const drawn = traces.map(t => (t.type === 'box' ? numbers(t.y).filter(Number.isFinite).map(v => [0, v]) : points(t)));
        const all = drawn.reduce((a, p) => a.concat(p), []), bars = traces.some(t => t.type === 'bar'), filled = bars || traces.some(t => t.type === 'box');
        const xr = range(all.map(p => p[0])), yr = range(all.map(p => p[1]).concat(bars ? [0] : []));      // bars stand on nought; boxes take the room their values span
        const X = v => box.x + (filled ? 0.1 + 0.8 * (v - xr[0]) / (xr[1] - xr[0]) : (v - xr[0]) / (xr[1] - xr[0])) * box.w, Y = v => box.y + box.h - (v - yr[0]) / (yr[1] - yr[0]) * box.h;
        let out = '<rect x="' + r1(box.x) + '" y="' + r1(box.y) + '" width="' + r1(box.w) + '" height="' + r1(box.h) + '" fill="none" stroke="#6b7280" stroke-width="1"/>';
        traces.forEach((t, k) => {
            const ink = INK[(first + k) % INK.length];
            if (t.type === 'box') {
                const vs = drawn[k].map(p => p[1]).sort((a, b) => a - b), q = f => vs[Math.round(f * (vs.length - 1))], cx = box.x + box.w * (k + 0.5) / traces.length;
                if (vs.length) out += '<path d="M' + r1(cx) + ',' + r1(Y(vs[0])) + 'V' + r1(Y(vs[vs.length - 1])) + 'M' + r1(cx - 18) + ',' + r1(Y(q(0.25))) + 'H' + r1(cx + 18) + 'V' + r1(Y(q(0.75))) + 'H' + r1(cx - 18) + 'ZM' +
                    r1(cx - 18) + ',' + r1(Y(q(0.5))) + 'H' + r1(cx + 18) + '" fill="none" stroke="' + ink + '" stroke-width="1.6"/>';
            } else if (t.type === 'bar') {
                const wide = box.w * 0.8 / Math.max(1, drawn[k].length) / traces.length * 0.86;
                out += drawn[k].map(p => '<rect x="' + r1(X(p[0]) + (k - traces.length / 2) * wide) + '" y="' + r1(Math.min(Y(p[1]), Y(0))) + '" width="' + r1(wide) + '" height="' + r1(Math.abs(Y(p[1]) - Y(0))) +
                    '" fill="' + ink + '" opacity="0.85"/>').join('');
            } else if (/markers/.test(t.mode || '') && !/lines/.test(t.mode || '')) {
                out += drawn[k].map(p => '<circle cx="' + r1(X(p[0])) + '" cy="' + r1(Y(p[1])) + '" r="2.6" fill="' + ink + '"/>').join('');
            } else if (drawn[k].length) {
                out += '<polyline points="' + drawn[k].map(p => r1(X(p[0])) + ',' + r1(Y(p[1]))).join(' ') + '" fill="none" stroke="' + ink + '" stroke-width="1.6" stroke-linejoin="round"/>';
            }
        });
        return out;
    }
    function draw(el, data, layout) {
        const lay = layout || {}, W = Math.max(280, el.clientWidth || 640), H = Number(lay.height) || 360;
        const traces = (data || []).filter(t => t && (Array.isArray(t.y) || Array.isArray(t.z)));
        const pairs = [], of = traces.map(t => { const id = (t.xaxis || 'x') + '/' + (t.yaxis || 'y') + (Array.isArray(t.z) ? '/z' : ''); if (pairs.indexOf(id) < 0) pairs.push(id); return pairs.indexOf(id); });
        const cols = Math.min(pairs.length || 1, 3), rows = Math.ceil((pairs.length || 1) / cols), top = 34, foot = 26, gap = 22;
        const w = (W - 28 - gap * (cols - 1)) / cols, h = (H - top - foot - gap * (rows - 1)) / rows;
        const title = lay.title && typeof lay.title === 'object' ? lay.title.text : lay.title;
        let out = '<svg class="main-svg" xmlns="http://www.w3.org/2000/svg" viewBox="0 0 ' + W + ' ' + H + '" width="100%" height="' + H + '" style="display:block;background:#111418;font-family:Arial,sans-serif">' +
            (title ? '<text x="14" y="21" fill="#e5e7eb" font-size="13">' + esc(title) + '</text>' : '');
        pairs.forEach((id, i) => { out += panel(traces.filter((t, k) => of[k] === i), { x: 14 + (i % cols) * (w + gap), y: top + Math.floor(i / cols) * (h + gap), w, h }, of.indexOf(i)); });
        out += traces.map((t, k) => (t.name ? '<text x="' + (14 + k * 130) + '" y="' + (H - 8) + '" fill="' + INK[k % INK.length] + '" font-size="11">' + esc(t.name) + '</text>' : '')).join('');
        out += (lay.annotations || []).filter(a => a && a.xref === 'paper' && a.text).map(a => {
            const x = (Number(a.x) || 0) * W, y = (1 - (Number(a.y) || 0)) * H, font = a.font || {};
            return '<text x="' + r1(x) + '" y="' + r1(y) + '" text-anchor="middle" fill="' + esc(font.color || '#9ca3af') + '" font-size="' + (Number(font.size) || 12) + '" opacity="' + (a.opacity == null ? 1 : Number(a.opacity)) + '"' +
                (a.textangle ? ' transform="rotate(' + Number(a.textangle) + ' ' + r1(x) + ' ' + r1(y) + ')"' : '') + '>' + esc(a.text) + '</text>';
        }).join('');
        el.innerHTML = out + '</svg>';
        if (el.classList) el.classList.add('js-plotly-plot');
        return Promise.resolve(el);
    }
    window.Plotly = { newPlot: draw, react: draw, relayout() {}, purge(el) { if (el) el.innerHTML = ''; }, toImage: () => Promise.resolve(''), Plots: { resize() {} } };
})();
