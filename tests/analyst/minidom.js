// A small DOM for testing stream-pane.js in node: an HTML parser for the subset the pane emits,
// serialisation back to HTML (what a favourite saves), and the query methods the pane uses.
'use strict';
const VOID = new Set(['br', 'hr', 'img', 'input', 'meta', 'link', 'path', 'circle', 'line', 'polyline']);
function decode(s) { return s.replace(/&lt;/g, '<').replace(/&gt;/g, '>').replace(/&quot;/g, '"').replace(/&#39;/g, "'").replace(/&nbsp;/g, '\u00a0').replace(/&times;/g, '×').replace(/&amp;/g, '&'); }
function encodeText(s) { return String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/\u00a0/g, '&nbsp;'); }
function encodeAttr(s) { return String(s).replace(/&/g, '&amp;').replace(/"/g, '&quot;').replace(/</g, '&lt;'); }
class Node { constructor() { this.parent = null; } }
class Text extends Node { constructor(t) { super(); this.nodeType = 3; this.data = t; } get textContent() { return this.data; } get outerHTML() { return encodeText(this.data); } }
class Element extends Node {
  constructor(tag) { super(); this.nodeType = 1; this.tag = tag.toLowerCase(); this.attrs = {}; this.children = []; const self = this;
    this.classList = { add: c => self._cls(c, true), remove: c => self._cls(c, false), contains: c => self._c().includes(c), toggle: (c, on) => self._cls(c, on === undefined ? !self._c().includes(c) : on) };
    this.style = {}; this.dataset = new Proxy({}, { get: (_, k) => self.attrs['data-' + String(k).replace(/[A-Z]/g, m => '-' + m.toLowerCase())] }); }
  _c() { return (this.attrs['class'] || '').split(/\s+/).filter(Boolean); }
  _cls(c, on) { const cs = this._c().filter(x => x !== c); if (on) cs.push(c); this.attrs['class'] = cs.join(' '); }
  get className() { return this.attrs['class'] || ''; } set className(v) { this.attrs['class'] = v; }
  get id() { return this.attrs['id'] || ''; }
  getAttribute(a) { return this.attrs[a] == null ? null : this.attrs[a]; } setAttribute(a, v) { this.attrs[a] = String(v); } removeAttribute(a) { delete this.attrs[a]; } hasAttribute(a) { return a in this.attrs; }
  appendChild(n) { if (n.parent) n.parent.children = n.parent.children.filter(c => c !== n); n.parent = this; this.children.push(n); return n; }
  remove() { if (this.parent) this.parent.children = this.parent.children.filter(c => c !== this); this.parent = null; }
  get innerHTML() { return this.children.map(c => c.outerHTML).join(''); }
  set innerHTML(html) { this.children = []; parseInto(this, html); }
  get outerHTML() { const a = Object.entries(this.attrs).map(([k, v]) => ` ${k}="${encodeAttr(v)}"`).join(''); return VOID.has(this.tag) ? `<${this.tag}${a}/>` : `<${this.tag}${a}>${this.innerHTML}</${this.tag}>`; }
  get textContent() { return this.children.map(c => c.textContent).join(''); } set textContent(v) { this.children = [new Text(String(v))]; this.children[0].parent = this; }
  insertAdjacentHTML(pos, html) { const tmp = new Element('div'); parseInto(tmp, html); for (const c of [...tmp.children]) this.appendChild(c); }
  get lastElementChild() { for (let i = this.children.length - 1; i >= 0; i--) if (this.children[i].nodeType === 1) return this.children[i]; return null; }
  get elements() { return this.children.filter(c => c.nodeType === 1); }
  querySelector(sel) { return this.querySelectorAll(sel)[0] || null; }
  querySelectorAll(sel) {
    const parts = sel.trim().replace(/^:scope\s*>\s*/, '@>').split(/\s+(?!>)/);
    let scopeChild = false; if (parts[0].startsWith('@>')) { scopeChild = true; parts[0] = parts[0].slice(2); }
    const match = (el, simple) => {
      let s = simple; let m;
      if ((m = s.match(/^([a-z0-9]+)/))) { if (el.tag !== m[1]) return false; s = s.slice(m[1].length); }
      while (s.length) {
        if (s[0] === '.') { m = s.match(/^\.([\w-]+)/); if (!el._c().includes(m[1])) return false; s = s.slice(m[0].length); }
        else if (s[0] === '#') { m = s.match(/^#([\w-]+)/); if (el.id !== m[1]) return false; s = s.slice(m[0].length); }
        else if (s.startsWith(':not(')) { m = s.match(/^:not\(([^)]+)\)/); if (match(el, m[1])) return false; s = s.slice(m[0].length); }
        else if (s[0] === '[') { m = s.match(/^\[([\w-]+)(?:="([^"]*)")?\]/); if (!(m[1] in el.attrs) || (m[2] !== undefined && el.attrs[m[1]] !== m[2])) return false; s = s.slice(m[0].length); }
        else return false;
      }
      return true;
    };
    const walk = (n, acc) => { for (const c of n.elements) { acc.push(c); walk(c, acc); } return acc; };
    let cands = scopeChild ? this.elements : walk(this, []);
    cands = cands.filter(e => match(e, parts[0]));
    for (let i = 1; i < parts.length; i++) { const next = []; for (const c of cands) for (const d of walk(c, [])) if (match(d, parts[i]) && !next.includes(d)) next.push(d); cands = next; }
    return cands;
  }
}
function parseInto(parent, html) {
  const re = /<!--[\s\S]*?-->|<\/([a-zA-Z0-9]+)\s*>|<([a-zA-Z0-9]+)((?:\s+[\w:-]+(?:="[^"]*"|='[^']*'|=[^\s>]+)?)*)\s*(\/?)>|([^<]+)/g;
  const stack = [parent]; let m;
  while ((m = re.exec(html))) {
    if (m[0].startsWith('<!--')) continue;
    if (m[1]) { for (let i = stack.length - 1; i > 0; i--) if (stack[i].tag === m[1].toLowerCase()) { stack.length = i; break; } continue; }
    if (m[2]) {
      const el = new Element(m[2]); const attrRe = /([\w:-]+)(?:="([^"]*)"|='([^']*)'|=([^\s>]+))?/g; let a;
      while ((a = attrRe.exec(m[3] || ''))) el.attrs[a[1]] = decode(a[2] !== undefined ? a[2] : (a[3] !== undefined ? a[3] : (a[4] !== undefined ? a[4] : '')));
      stack[stack.length - 1].appendChild(el);
      if (!m[4] && !VOID.has(el.tag)) stack.push(el);
      continue;
    }
    if (m[5]) { const t = new Text(decode(m[5])); stack[stack.length - 1].appendChild(t); }
  }
}
function makeDocument() {
  const body = new Element('body');
  const doc = { body, createElement: t => new Element(t), getElementById: id => body.querySelectorAll('#' + id)[0] || null,
    querySelector: s => body.querySelector(s), querySelectorAll: s => body.querySelectorAll(s), addEventListener() {} };
  return doc;
}
module.exports = { Element, Text, makeDocument, parseInto };
