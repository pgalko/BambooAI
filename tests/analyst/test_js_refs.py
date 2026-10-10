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
def code_only(text):
    """The code with comments, strings, template literals and regex literals blanked - by a small lexer, since the
    regex-based stripping derailed on a regex literal that holds a quote (/'/g in stream-pane.js) and read the rest
    of the file inside out, passing or failing by the luck of the quote parity (2026-10-10)."""
    out, i, n = [], 0, len(text)
    REGEX_AFTER = set("(,=:[!&|?{};+-*%<>~^") | {"\n"}
    WORDS_BEFORE_REGEX = {"return", "typeof", "case", "do", "else", "in", "of", "instanceof", "new", "delete", "void", "throw"}
    def prev_significant(k):
        j = k - 1
        while j >= 0 and text[j] in " \t\r":
            j -= 1
        return j
    while i < n:
        c = text[i]
        if c == "/" and i + 1 < n and text[i + 1] == "/":
            j = text.find("\n", i); i = n if j < 0 else j; continue
        if c == "/" and i + 1 < n and text[i + 1] == "*":
            j = text.find("*/", i + 2); i = n if j < 0 else j + 2; out.append(" "); continue
        if c in "'\"":
            j = i + 1
            while j < n and text[j] != c:
                j += 2 if text[j] == "\\" else 1
            out.append("''"); i = j + 1; continue
        if c == "`":
            j, depth = i + 1, 0
            while j < n:
                if text[j] == "\\": j += 2; continue
                if depth == 0 and text[j] == "`": break
                if text[j] == "$" and j + 1 < n and text[j + 1] == "{": depth += 1; j += 2; continue
                if depth and text[j] == "}": depth -= 1
                j += 1
            out.append("''"); i = j + 1; continue
        if c == "/":
            p = prev_significant(i)
            word = re.search(r"([A-Za-z_$][\w$]*)$", text[max(0, p - 12):p + 1]) if p >= 0 else None
            if p < 0 or text[p] in REGEX_AFTER or (word and word.group(1) in WORDS_BEFORE_REGEX):
                j, in_class = i + 1, False
                while j < n and text[j] != "\n":
                    if text[j] == "\\": j += 2; continue
                    if text[j] == "[": in_class = True
                    elif text[j] == "]": in_class = False
                    elif text[j] == "/" and not in_class: break
                    j += 1
                j += 1
                while j < n and text[j] in "gimsuyd": j += 1
                out.append("/re/"); i = j; continue
        out.append(c); i += 1
    return "".join(out)

# an object literal's shorthand methods (build = { lookup(l) { ... } }) are definitions too
for text in src.values():
    defined |= set(re.findall(r"^\s*([A-Za-z_$][\w$]*)\s*\([^()]*\)\s*\{", code_only(text), re.M))
missing = {}
for f, text in src.items():
    body = code_only(text)
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
