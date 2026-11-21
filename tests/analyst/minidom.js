// A small DOM for testing stream-pane.js in node: an HTML parser for the subset the pane emits,
// serialisation back to HTML (what a favourite saves), and the query methods the pane uses.
'use strict';
const VOID = new Set(['br', 'hr', 'img', 'input', 'meta', 'link', 'path', 'circle', 'line', 'polyline']);
function decode(s) { return s.replace(/&lt;/g, '<').replace(/&gt;/g, '>').replace(/&quot;/g, '"').replace(/&#39;/g, "'").replace(/&nbsp;/g, '\u00a0').replace(/&times;/g, '×').replace(/&amp;/g, '&'); }
function encodeText(s) { return String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/\u00a0/g, '&nbsp;'); }
function encodeAttr(s) { return String(s).replace(/&/g, '&amp;').replace(/"/g, '&quot;').replace(/</g, '&lt;'); }
let active = null;      // the element with the focus, as far as focus() and blur() say
class Node { constructor() { this.parent = null; } }
class Text extends Node { constructor(t) { super(); this.nodeType = 3; this.data = t; } get textContent() { return this.data; } get outerHTML() { return encodeText(this.data); } }
class Element extends Node {
  constructor(tag) { super(); this.nodeType = 1; this.tag = tag.toLowerCase(); this.tagName = this.tag.toUpperCase(); this.attrs = {}; this.children = []; const self = this;
    this.classList = { add: c => self._cls(c, true), remove: c => self._cls(c, false), contains: c => self._c().includes(c), toggle: (c, on) => { const to = on === undefined ? !self._c().includes(c) : !!on; self._cls(c, to); return to; } };      // toggle() says, as the browser's does, whether the class is now there
    this.style = {}; this.dataset = new Proxy({}, { get: (_, k) => self.attrs['data-' + String(k).replace(/[A-Z]/g, m => '-' + m.toLowerCase())] }); }
  _c() { return (this.attrs['class'] || '').split(/\s+/).filter(Boolean); }
  _cls(c, on) { const cs = this._c().filter(x => x !== c); if (on) cs.push(c); this.attrs['class'] = cs.join(' '); }
  get className() { return this.attrs['class'] || ''; } set className(v) { this.attrs['class'] = v; }
  get id() { return this.attrs['id'] || ''; } set id(v) { this.attrs['id'] = String(v); }
  getAttribute(a) { return this.attrs[a] == null ? null : this.attrs[a]; } setAttribute(a, v) { this.attrs[a] = String(v); } removeAttribute(a) { delete this.attrs[a]; } hasAttribute(a) { return a in this.attrs; }
  appendChild(n) { if (n.parent) n.parent.children = n.parent.children.filter(c => c !== n); n.parent = this; this.children.push(n); return n; }
  insertBefore(n, ref) {      // before `ref`; at the end where there is none, as the browser does
    if (!ref) return this.appendChild(n);
    if (n.parent) n.parent.children = n.parent.children.filter(c => c !== n);
    n.parent = this; this.children.splice(this.children.indexOf(ref), 0, n); return n;
  }
  remove() { if (this.parent) this.parent.children = this.parent.children.filter(c => c !== this); this.parent = null; }
  get parentNode() { return this.parent || null; }        // the browser's name for it
  get innerHTML() { return this.children.map(c => c.outerHTML).join(''); }
  set innerHTML(html) { this.children = []; parseInto(this, html); }
  get outerHTML() { const a = Object.entries(this.attrs).map(([k, v]) => ` ${k}="${encodeAttr(v)}"`).join(''); return VOID.has(this.tag) ? `<${this.tag}${a}/>` : `<${this.tag}${a}>${this.innerHTML}</${this.tag}>`; }
  get textContent() { return this.children.map(c => c.textContent).join(''); } set textContent(v) { this.children = [new Text(String(v))]; this.children[0].parent = this; }
  insertAdjacentHTML(pos, html) {      // 'afterbegin' before the first child, in order; any other position at the end
    const tmp = new Element('div'); parseInto(tmp, html);
    const first = pos === 'afterbegin' ? this.children[0] || null : null;
    for (const c of [...tmp.children]) this.insertBefore(c, first);
  }
  get lastElementChild() { for (let i = this.children.length - 1; i >= 0; i--) if (this.children[i].nodeType === 1) return this.children[i]; return null; }
  get firstElementChild() { for (const c of this.children) if (c.nodeType === 1) return c; return null; }
  // events and ancestry, enough for a module's click handler to be driven by a test (2026-10-16): listeners are kept per type,
  // dispatch(type, target) calls them with {target}; closest/matches test a selector against the element's own ancestors
  addEventListener(type, fn) { (this.listeners = this.listeners || {})[type] = (this.listeners[type] || []).concat(fn); }
  dispatch(type, target, extra) { const ev = Object.assign({ type, target: target || this, preventDefault() {}, stopPropagation() {} }, extra || {}); for (const fn of ((this.listeners || {})[type] || [])) fn(ev); return ev; }
  matches(sel) { return this.parent ? this.parent.querySelectorAll(sel).includes(this) : false; }
  closest(sel) { let n = this; while (n && n.nodeType === 1) { if (n.matches(sel)) return n; n = n.parent; } return null; }
  focus() { active = this; } select() {} blur() { if (active === this) active = null; }
  contains(n) { for (; n; n = n.parent) if (n === this) return true; return false; }
  getBoundingClientRect() { return { top: 0, right: 0, bottom: 0, left: 0, width: 0, height: 0 }; }      // no layout here: every box is empty
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
  const doc = { body, createElement: t => new Element(t), getElementById: id => { const find = n => { for (const c of n.elements) { if (c.id === id) return c; const r = find(c); if (r) return r; } return null; }; return find(body); },   // by id, not by selector: a dotted id (unit-D1.2) is an id, as in the browser
    querySelector: s => body.querySelector(s), querySelectorAll: s => body.querySelectorAll(s),
    get activeElement() { return active && body.contains(active) ? active : body; },      // the body, where nothing in the page has the focus
    listeners: {}, addEventListener(type, fn) { (this.listeners[type] = this.listeners[type] || []).push(fn); },
    dispatch(type, target, extra) { const ev = Object.assign({ type, target, preventDefault() { ev.defaulted = true; }, stopPropagation() { ev.stopped = true; } }, extra || {}); for (const fn of (this.listeners[type] || [])) fn(ev); return ev; } };
  return doc;
}
// The markup of the page's element with that id, cut from the page's source: the <div> that carries the id, up to
// its own end. A suite that runs a script on a part of the page takes the part from the page, not from a copy of it
function fragment(html, id) {
  const start = html.lastIndexOf('<div', html.indexOf(`id="${id}"`)), re = /<\/?div\b[^>]*>/g;
  let depth = 0, m;
  re.lastIndex = start;
  while ((m = re.exec(html))) { if (m[0].startsWith('</')) { depth--; if (depth === 0) return html.slice(start, m.index + m[0].length); } else if (!m[0].endsWith('/>')) depth++; }
  return html.slice(start);
}
module.exports = { Element, Text, makeDocument, parseInto, fragment };
