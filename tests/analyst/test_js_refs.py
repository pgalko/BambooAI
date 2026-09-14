"""Every function the front end calls must still be defined somewhere in it.
Catches the class of bug where a cleanup removes a definition another file
still calls (2026-09-06: startPopupTimer). Run: python3 tests/analyst/test_js_refs.py"""
import os, re, sys, glob
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
JS = os.path.join(ROOT, "web_app", "static", "js")
files = [f for f in glob.glob(os.path.join(JS, "**", "*.js"), recursive=True) if "node_modules" not in f and ".min." not in f]
html = open(os.path.join(ROOT, "web_app", "templates", "index.html"), encoding="utf-8").read()
src = {f: open(f, encoding="utf-8", errors="replace").read() for f in files}
alltext = "\n".join(src.values()) + "\n" + html
defined = set(re.findall(r"\bfunction\s+([A-Za-z_$][\w$]*)\s*\(", alltext))
defined |= set(re.findall(r"\b(?:window\.)?([A-Za-z_$][\w$]*)\s*=\s*(?:async\s*)?(?:function\b|\([^)]*\)\s*=>|[A-Za-z_$][\w$]*\s*=>)", alltext))
defined |= set(re.findall(r"\bwindow\.([A-Za-z_$][\w$]*)\s*=", alltext))
defined |= set(re.findall(r"\b(?:const|let|var)\s+([A-Za-z_$][\w$]*)\s*=", alltext))
# calls that look like app functions: camelCase identifiers, called bare (not obj.method), not JS builtins / DOM globals
BUILTIN = set("""alert confirm prompt fetch setTimeout setInterval clearTimeout clearInterval requestAnimationFrame parseInt parseFloat
isNaN isFinite encodeURIComponent decodeURIComponent encodeURI decodeURI escape unescape eval String Number Boolean Array Object Date
Math JSON Promise Map Set WeakMap Symbol Error TypeError RangeError RegExp Blob File FileReader FormData URL URLSearchParams
AbortController TextDecoder TextEncoder Event CustomEvent MutationObserver ResizeObserver IntersectionObserver Image Audio
localStorage sessionStorage document window navigator console marked hljs Plotly katex renderMathInElement mermaid DOMPurify
require module structuredClone queueMicrotask atob btoa Intl Proxy Reflect Function Uint8Array ArrayBuffer Headers Request Response
addEventListener removeEventListener dispatchEvent getComputedStyle scrollTo print open close focus blur cancelAnimationFrame
Notification WebSocket EventSource performance crypto""".split())
missing = {}
for f, text in src.items():
    body = re.sub(r"//[^\n]*", "", text)
    body = re.sub(r"/\*.*?\*/", "", body, flags=re.S)
    body = re.sub(r"(['\"`])(?:\\.|(?!\1).)*\1", "''", body, flags=re.S)        # strings out
    body = re.sub(r"(?<![\w)\]])/(?:\\.|\[[^\]]*\]|[^/\n])+/[gimsuy]*", "/re/", body)   # regex literals out
    for m in re.finditer(r"(?<![\w$.:])([a-z][A-Za-z0-9_$]*)\s*\(", body):
        name = m.group(1)
        if name in BUILTIN or name in defined or name in ("if", "for", "while", "switch", "catch", "return", "typeof", "function", "await", "async", "new", "delete", "void", "throw", "in", "of", "super", "this"):
            continue
        if re.search(r"typeof\s+" + re.escape(name) + r"\s*===?\s*'function'", text):
            continue                                       # the code guards the call itself
        missing.setdefault(name, set()).add(os.path.basename(f))
if missing:
    for n, fs in sorted(missing.items()):
        print(f"  FAIL {n} is called in {sorted(fs)} but defined nowhere in the front end")
    print(f"\n0 passed, {len(missing)} failed"); sys.exit(1)
print("  ok   every function the front end calls is defined somewhere in it\n\n1 passed, 0 failed")
