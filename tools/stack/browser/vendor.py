"""The page's CDN libraries, served locally.

The page loads marked, highlight.js, mermaid, dagre, localforage, KaTeX, CodeMirror, Plotly and
the Auth0 SPA SDK from CDNs. The browser in the stack is routed here instead:

  1. tools/stack/browser/vendor/<file>  - a real copy. `prepare()` fills this folder from copies
     already on the machine (marked, KaTeX, a highlight.js bundle built from its library files)
     and, when the network allows, downloads the rest from the CDN URLs the page names. On a box
     with internet every library is real after the first run.
  2. tools/stack/browser/<stub>.js       - a stand-in when no real copy exists (localforage in
     memory, a no-op Plotly/mermaid/CodeMirror). The Auth0 SDK is ALWAYS the stand-in.
  3. anything else off-app is refused.

`resolve(url) -> (bytes, content_type) | None`.
"""
import glob
import os
import shutil

HERE = os.path.dirname(os.path.abspath(__file__))
VENDOR = os.path.join(HERE, "vendor")
NPM_ROOTS = [r for r in (os.path.expanduser("~/.npm-global/lib/node_modules"), "/home/claude/.npm-global/lib/node_modules",
                          "/usr/local/lib/node_modules", "/usr/lib/node_modules") if os.path.isdir(r)]


def _find(*parts):
    """First match of a path pattern under any node_modules root (two levels of nesting)."""
    for root in NPM_ROOTS:
        for pat in (os.path.join(root, *parts), os.path.join(root, "*", "node_modules", *parts),
                    os.path.join(root, "@*", "*", "node_modules", *parts),
                    os.path.join(root, "*", "node_modules", "*", "node_modules", *parts),
                    os.path.join(root, "@*", "*", "node_modules", "*", "node_modules", *parts)):
            hits = sorted(glob.glob(pat))
            if hits:
                return hits
    return []

# CDN URL (as index.html and auth.js name it) -> vendor file
FILES = {
    "https://cdn.jsdelivr.net/npm/marked@4.0.18/marked.min.js": "marked.min.js",
    "https://cdnjs.cloudflare.com/ajax/libs/highlight.js/11.5.1/highlight.min.js": "highlight.min.js",
    "https://cdnjs.cloudflare.com/ajax/libs/highlight.js/11.5.1/styles/github.min.css": "github.min.css",
    "https://cdn.jsdelivr.net/npm/mermaid/dist/mermaid.min.js": "mermaid.min.js",
    "https://cdnjs.cloudflare.com/ajax/libs/dagre/0.8.5/dagre.min.js": "dagre.min.js",
    "https://cdn.jsdelivr.net/npm/localforage@1.10.0/dist/localforage.min.js": "localforage.min.js",
    "https://cdnjs.cloudflare.com/ajax/libs/codemirror/5.65.2/codemirror.min.css": "codemirror/codemirror.min.css",
    "https://cdnjs.cloudflare.com/ajax/libs/codemirror/5.65.2/codemirror.min.js": "codemirror/codemirror.min.js",
    "https://cdnjs.cloudflare.com/ajax/libs/codemirror/5.65.2/theme/monokai.min.css": "codemirror/monokai.min.css",
    "https://cdnjs.cloudflare.com/ajax/libs/codemirror/5.65.2/mode/python/python.min.js": "codemirror/python.min.js",
    "https://cdn.plot.ly/plotly-3.0.1.min.js": "plotly.min.js",
}
# URL prefixes -> vendor folders (KaTeX's css pulls its fonts by relative url)
PREFIXES = {"https://cdn.jsdelivr.net/npm/katex@0.16.9/dist/": "katex/"}
# stand-ins when no real copy exists (file in this folder)
STUBS = {
    "https://cdn.auth0.com/js/auth0-spa-js/2.1/auth0-spa-js.production.js": "auth0_stub.js",   # always
    "https://cdn.jsdelivr.net/npm/localforage@1.10.0/dist/localforage.min.js": "localforage_stub.js",
    "https://cdn.jsdelivr.net/npm/mermaid/dist/mermaid.min.js": "libs_stub_mermaid.js",
    "https://cdnjs.cloudflare.com/ajax/libs/dagre/0.8.5/dagre.min.js": "dagre_stub.js",
    "https://cdn.plot.ly/plotly-3.0.1.min.js": "libs_stub_plotly.js",
    "https://cdnjs.cloudflare.com/ajax/libs/codemirror/5.65.2/codemirror.min.js": "libs_stub_codemirror.js",
    "https://cdnjs.cloudflare.com/ajax/libs/highlight.js/11.5.1/highlight.min.js": "libs_stub_hljs.js",
    "https://cdn.jsdelivr.net/npm/marked@4.0.18/marked.min.js": None,   # the fixtures' render-only marked
}
CTYPES = {".js": "application/javascript", ".css": "text/css", ".woff2": "font/woff2", ".woff": "font/woff",
          ".ttf": "font/ttf", ".svg": "image/svg+xml", ".png": "image/png", ".json": "application/json"}


def _ctype(path):
    return CTYPES.get(os.path.splitext(path)[1].lower(), "application/octet-stream")


def _local_copies():
    """Copies already on this machine (other npm tools ship them) -> vendor/."""
    made = []
    marked = [m for m in _find("marked", "marked.min.js")
              if '"version":"4.' in open(os.path.join(os.path.dirname(m), "package.json"), encoding="utf-8").read().replace(" ", "")]
    if marked and not os.path.exists(os.path.join(VENDOR, "marked.min.js")):
        shutil.copy(marked[0], os.path.join(VENDOR, "marked.min.js")); made.append("marked.min.js (4.x)")
    katex = _find("katex", "dist", "katex.min.js")
    if katex and not os.path.exists(os.path.join(VENDOR, "katex", "katex.min.js")):
        src = os.path.dirname(katex[0])
        dst = os.path.join(VENDOR, "katex")
        os.makedirs(dst, exist_ok=True)
        for name in ("katex.min.js", "katex.min.css"):
            shutil.copy(os.path.join(src, name), os.path.join(dst, name))
        os.makedirs(os.path.join(dst, "contrib"), exist_ok=True)
        shutil.copy(os.path.join(src, "contrib", "auto-render.min.js"), os.path.join(dst, "contrib", "auto-render.min.js"))
        shutil.copytree(os.path.join(src, "fonts"), os.path.join(dst, "fonts"), dirs_exist_ok=True)
        made.append("katex/")
    hl = _find("highlight.js", "lib", "core.js")
    if hl and not os.path.exists(os.path.join(VENDOR, "highlight.min.js")):
        lib = os.path.dirname(hl[0])
        core = open(hl[0], encoding="utf-8").read()
        parts = ["window.hljs=(function(){var module={exports:{}};var exports=module.exports;\n", core,
                 "\nreturn module.exports;})();\n"]
        for lang in ("python", "json", "yaml", "bash", "javascript", "markdown"):
            f = os.path.join(lib, "languages", f"{lang}.js")
            if os.path.exists(f):
                parts += ["(function(){var module={exports:{}};var exports=module.exports;\n", open(f, encoding="utf-8").read(),
                          f"\nwindow.hljs.registerLanguage('{lang}', module.exports);}})();\n"]
        parts.append("if(!window.hljs.highlightElement){window.hljs.highlightElement=function(el){window.hljs.highlightBlock(el);};}\n"
                     "if(!window.hljs.highlightAll){window.hljs.highlightAll=function(){document.querySelectorAll('pre code').forEach(function(el){window.hljs.highlightBlock(el);});};}\n")
        open(os.path.join(VENDOR, "highlight.min.js"), "w", encoding="utf-8").write("".join(parts)); made.append("highlight.min.js (bundled)")
        css = os.path.join(os.path.dirname(lib), "styles", "github.css")
        if os.path.exists(css):
            shutil.copy(css, os.path.join(VENDOR, "github.min.css")); made.append("github.min.css")
    return made


def _fetch_missing(timeout=4.0):
    """Download what is still missing from the CDN URLs the page names; silent when offline."""
    import requests
    got = []
    targets = dict(FILES)
    for prefix, folder in PREFIXES.items():
        for name in ("katex.min.js", "katex.min.css", "contrib/auto-render.min.js"):
            targets[prefix + name] = folder + name
    for url, rel in targets.items():
        path = os.path.join(VENDOR, rel)
        if os.path.exists(path):
            continue
        try:
            r = requests.get(url, timeout=timeout)
            if r.status_code == 200 and r.content:
                os.makedirs(os.path.dirname(path), exist_ok=True)
                open(path, "wb").write(r.content); got.append(rel)
        except Exception:                               # noqa: BLE001
            return got            # no network: stop trying
    return got


def prepare(fetch=True):
    os.makedirs(VENDOR, exist_ok=True)
    made = _local_copies()
    got = _fetch_missing() if fetch else []
    return made, got


def status():
    """Which libraries are real and which are stand-ins."""
    out = {}
    for url, rel in FILES.items():
        out[rel] = "real" if os.path.exists(os.path.join(VENDOR, rel)) else ("stand-in" if STUBS.get(url) else "absent")
    out["katex/"] = "real" if os.path.exists(os.path.join(VENDOR, "katex", "katex.min.js")) else "absent"
    out["auth0-spa-js"] = "stand-in (always)"
    return out


def resolve(url):
    """(bytes, content_type) for a CDN url, or None to refuse it."""
    if url in STUBS and STUBS[url] and url.startswith("https://cdn.auth0.com/"):
        p = os.path.join(HERE, STUBS[url])
        return open(p, "rb").read(), _ctype(p)
    for prefix, folder in PREFIXES.items():
        if url.startswith(prefix):
            p = os.path.join(VENDOR, folder, url[len(prefix):].split("?")[0])
            return (open(p, "rb").read(), _ctype(p)) if os.path.exists(p) else (b"", _ctype(p))
    rel = FILES.get(url.split("?")[0])
    if rel:
        p = os.path.join(VENDOR, rel)
        if os.path.exists(p):
            return open(p, "rb").read(), _ctype(p)
    stub = STUBS.get(url.split("?")[0])
    if stub:
        p = os.path.join(HERE, stub)
        return open(p, "rb").read(), _ctype(p)
    if stub is None and url.split("?")[0] in STUBS:                 # marked: the fixtures' stand-in
        p = os.path.join(os.path.dirname(os.path.dirname(HERE)), "fixtures", "marked_stub.js")
        return open(p, "rb").read(), "application/javascript"
    if rel and rel.endswith(".css"):
        return b"", "text/css"
    return None
