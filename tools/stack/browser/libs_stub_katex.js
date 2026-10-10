// KaTeX stand-in for the stack when no real copy is in vendor/ (2026-10-10): the page calls renderMathInElement on
// every rendered answer, and without the library each call was a page error in the walk. Nothing is typeset.
window.katex = window.katex || { render: function () {}, renderToString: function (s) { return String(s); } };
window.renderMathInElement = window.renderMathInElement || function () {};
