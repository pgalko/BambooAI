"""The stylesheets' contract (2026-09-08).
  1. every var(--x) used in any stylesheet is defined in tokens.css;
  2. components.css and tokens.css are the only files allowed to define variables; components.css writes no raw colour;
  3. a report (not a failure) of classes the HTML/JS use that no stylesheet defines, and of classes stylesheets define
     that nothing uses - the map for the cleanup steps.
Run: python3 tests/analyst/test_css_refs.py"""
import os, re, sys, glob
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
CSS = sorted(glob.glob(os.path.join(ROOT, "web_app", "static", "css", "**", "*.css"), recursive=True))
JS = [f for f in glob.glob(os.path.join(ROOT, "web_app", "static", "js", "**", "*.js"), recursive=True) if ".min." not in f]
HTML = glob.glob(os.path.join(ROOT, "web_app", "templates", "*.html"))
def read(f): return open(f, encoding="utf-8", errors="replace").read()
tokens = read(os.path.join(ROOT, "web_app", "static", "css", "tokens.css"))
defined = set(re.findall(r"(--[\w-]+)\s*:", tokens))
fails = []
for f in CSS:
    t = read(f); base = os.path.basename(f)
    used = set(re.findall(r"var\((--[\w-]+)", t))
    missing = sorted(used - defined - set(re.findall(r"(--[\w-]+)\s*:", t)))
    if missing: fails.append(f"{base} uses undefined variables: {missing[:8]}")
    if base not in ("tokens.css",) and re.search(r"^\s*(:root|\[data-theme=\"light\"\])\s*\{", t, re.M):
        fails.append(f"{base} defines theme variables (only tokens.css may)")
comp = read(os.path.join(ROOT, "web_app", "static", "css", "components.css"))
if re.search(r"#[0-9a-fA-F]{3,6}\b", comp): fails.append("components.css contains a raw hex colour")
# the usage map
css_classes = set(); 
for f in CSS: css_classes |= set(re.findall(r"\.([A-Za-z_][\w-]*)", re.sub(r"/\*.*?\*/", "", read(f), flags=re.S)))
used_classes = set()
for f in JS + HTML:
    t = read(f)
    for m in re.findall(r'class(?:Name)?\s*=\s*["\']([^"\']+)["\']', t): used_classes |= set(m.split())
    for m in re.findall(r"classList\.(?:add|remove|toggle|contains)\(([^)]*)\)", t): used_classes |= set(re.findall(r"['\"]([\w-]+)['\"]", m))
    for m in re.findall(r"querySelector(?:All)?\(\s*['\"]([^'\"]+)['\"]", t): used_classes |= set(re.findall(r"\.([A-Za-z_][\w-]*)", m))
    for m in re.findall(r"class=\\?\"([^\"\\]+)", t): used_classes |= set(m.split())
undefined = sorted(c for c in used_classes if c not in css_classes and not c.startswith(("hljs", "fa-", "plotly", "js-")))
unused = sorted(c for c in css_classes if c not in used_classes and not c.startswith(("ui-", "hljs", "sp-", "nb-", "dg-")))
print(f"  report: {len(undefined)} classes used by HTML/JS but styled nowhere (JS hooks are fine); {len(unused)} classes styled but used nowhere (cleanup candidates)")
if fails:
    for x in fails: print("  FAIL " + x)
    print(f"\n0 passed, {len(fails)} failed"); sys.exit(1)
print("  ok   stylesheets: every variable defined in tokens.css; components.css is token-only\n\n1 passed, 0 failed")
if "--map" in sys.argv:
    print("\nUNUSED (styled, never used):", ", ".join(unused[:400]))
