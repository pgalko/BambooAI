// a render-only stand-in for marked (the CDN is blocked in the harness): paragraphs, headings, bold, numbered lists
window.marked = { parse(md) { const esc = s => s; const lines = String(md).split('\n'); let out = '', inOl = false, para = [];
  const flush = () => { if (para.length) { out += '<p>' + para.join(' ') + '</p>'; para = []; } };
  const inline = t => t.replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>').replace(/`(.+?)`/g, '<code>$1</code>');
  for (const l of lines) { const m = l.match(/^\s*(\d+)\.\s+(.*)$/); const h = l.match(/^(#{1,3})\s+(.*)$/);
    if (m) { flush(); if (!inOl) { out += '<ol>'; inOl = true; } out += '<li>' + inline(m[2]) + '</li>'; continue; }
    if (inOl && l.trim() === '') { continue; } if (inOl) { out += '</ol>'; inOl = false; }
    if (h) { flush(); out += '<h' + h[1].length + '>' + inline(h[2]) + '</h' + h[1].length + '>'; continue; }
    if (l.trim() === '') { flush(); continue; } para.push(inline(esc(l))); }
  if (inOl) out += '</ol>'; flush(); return out; }, setOptions() {} };
