// CodeMirror stand-in: the code editor becomes a plain textarea.
window.CodeMirror = function (host, opts) {
  const ta = document.createElement('textarea'); ta.value = (opts && opts.value) || ''; ta.style.width = '100%'; ta.style.minHeight = '240px';
  if (typeof host === 'function') host(ta); else host.appendChild(ta);
  return { getValue: () => ta.value, setValue: v => { ta.value = v; }, on() {}, refresh() {}, setOption() {}, getWrapperElement: () => ta, focus: () => ta.focus() };
};
