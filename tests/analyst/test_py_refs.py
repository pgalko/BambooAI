"""The Python side's own references, as test_js_refs.py and test_css_refs.py hold the page's (0347). A clean-up took
out arguments nothing read, switches nothing set, functions nothing called and imports nothing used; this keeps them
from coming back, and catches the slip such a clean-up can make:
  1. no module of the product imports a name it does not use;
  2. the web app hands each integration what that integration reads, and an integration uses what it keeps;
  3. the page sends with a question what the route reads, and the route hands the host what the host takes;
  4. what 0347 removed has left nothing behind.
Left as they were, on purpose, and named here so that the list cannot grow unseen: three imports of the hosted
edition's two database clients, one of its billing routes, and one thing its container routes keep.
Run: python3 tests/analyst/test_py_refs.py"""
import ast, inspect, os, re, sys, tempfile, tomllib
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path[:0] = [HERE, ROOT, os.path.join(ROOT, "delve")]
import _stubs  # noqa: F401,E402
os.environ["OPENAI_API_KEY"] = "x"; os.environ["EXECUTION_MODE"] = "local"
os.chdir(tempfile.mkdtemp())                           # the product's modules make their log folder where they are loaded
from bambooai import bambooai as B, executor_client, models, utils  # noqa: E402
from bambooai.messages.prompts import PromptManager  # noqa: E402
from bambooai.models import prompt_cache  # noqa: E402

passed, failed = [], []
def check(name, cond, detail=""):
    (passed if cond else failed).append(name); print(("  ok   " if cond else "  FAIL ") + name + ("" if cond else f"  <- {detail}"))


def read(path):
    with open(os.path.join(ROOT, path), encoding="utf-8") as f:
        return f.read()


# the product's modules: those of the packages the project file lists - not whatever lies in the folders a running app
# keeps its users' files in
PACKAGES = [p for p in tomllib.loads(read("pyproject.toml"))["tool"]["setuptools"]["packages"] if p.split(".")[0] in ("bambooai", "analyst", "web_app")]
PRODUCT = sorted(f"{p.replace('.', '/')}/{name}" for p in PACKAGES for name in os.listdir(os.path.join(ROOT, *p.split("."))) if name.endswith(".py")) + ["logger_config.py"]
SOURCE = {path: read(path) for path in PRODUCT}
TREE = {path: ast.parse(text) for path, text in SOURCE.items()}

# ------------------------------------------------------------------------------------------ 1. imports
LEFT_IMPORTS = {"bambooai/db/supabase_client.py": ["logging"], "web_app/auth/supabase_client.py": ["Optional", "Union"],
                "web_app/subscription_routes.py": ["build_user_config"]}


def unused_imports(path):
    """The names the module's own import statements bind and nothing in the module uses (an __init__ imports for others)."""
    lines, used = SOURCE[path].splitlines(), {n.id for n in ast.walk(TREE[path]) if isinstance(n, ast.Name)}
    listed = set(re.findall(r"['\"](\w+)['\"]", " ".join(line for line in lines if "__all__" in line)))
    out = []
    for node in TREE[path].body:
        if isinstance(node, ast.Import):
            names = [(a.asname or a.name).split(".")[0] for a in node.names]
        elif isinstance(node, ast.ImportFrom) and node.module != "__future__":
            names = [a.asname or a.name for a in node.names]
        else:
            continue
        out += [n for n in names if n not in used and n not in listed and "noqa" not in lines[node.lineno - 1]]
    return sorted(out)


unused = {path: names for path in PRODUCT if not path.endswith("__init__.py") for names in [unused_imports(path)] if names}
check("imports: no module of the product imports a name it does not use, but for the four left on purpose (0347 removed those there were)",
      unused == LEFT_IMPORTS and len(PRODUCT) > 80, {p: n for p, n in unused.items() if LEFT_IMPORTS.get(p) != n} or sorted(set(LEFT_IMPORTS) - set(unused)))

# ------------------------------------------------------------------------------------------ 2. the integrations
APP = SOURCE["web_app/app.py"]
LEFT_KEPT = {"web_app/container_status_routes.py": ["get_dynamic_executor_urls"]}
handed = {n.func.id: sorted(k.arg for k in n.keywords) for n in ast.walk(TREE["web_app/app.py"])
          if isinstance(n, ast.Call) and isinstance(n.func, ast.Name) and re.fullmatch(r"init_\w+_integration", n.func.id)}
GIVEN = r"dependencies(?:\[|\.get\()['\"](\w+)['\"]"                    # how a start reads one of the things it is handed
reads, idle = {}, {}
for path in PRODUCT:
    for fn in TREE[path].body:
        if isinstance(fn, ast.FunctionDef) and re.fullmatch(r"init_\w+_integration", fn.name):
            reads[fn.name] = sorted(set(re.findall(GIVEN, ast.get_source_segment(SOURCE[path], fn))))
            kept = {t.attr for n in ast.walk(fn) if isinstance(n, ast.Assign) and re.search(GIVEN, ast.get_source_segment(SOURCE[path], n.value))
                    for t in n.targets if isinstance(t, ast.Attribute)}
            used = {n.attr for n in ast.walk(TREE[path]) if isinstance(n, ast.Attribute) and isinstance(n.ctx, ast.Load)} | set(re.findall(r"getattr\(\w+, ['\"](\w+)['\"]", SOURCE[path]))
            if kept - used:
                idle[path] = sorted(kept - used)
check("the integrations: the web app hands each of the five what its own start reads, neither more nor less - less would stop the app as it starts",
      len(handed) == 5 and handed == reads and all(handed.values()), {k: (handed.get(k), reads.get(k)) for k in set(handed) | set(reads) if handed.get(k) != reads.get(k)})
check("...and an integration uses what it keeps of them, but for the one left on purpose (0347: three things were handed to them, kept, and used by none)",
      idle == LEFT_KEPT, idle)

# ------------------------------------------------------------------------------------------ 3. a question
PAGE = read("web_app/static/js/query-processing.js")
body = PAGE[PAGE.index("const requestBody = {"):]
sends = set(re.findall(r"^\s*(\w+):", body[:body.index("};")], re.M)) | set(re.findall(r"\brequestBody\.(\w+)\s*=", PAGE))
route = next(n for n in ast.walk(TREE["web_app/app.py"]) if isinstance(n, ast.FunctionDef) and n.name == "query")
text = ast.get_source_segment(APP, route)
taken = set(re.findall(r"request\.json\[['\"](\w+)['\"]\]", text)) | set(re.findall(r"request\.json\.get\(['\"](\w+)['\"]", text))
check("a question: the page sends what the route reads, and the route reads nothing the page does not send - the mode and the depth among it",
      sends == taken and {"query", "thread_id", "chain_id", "mode", "max_investigations"} <= sends, (sorted(sends - taken), sorted(taken - sends)))


def keywords(tree, called):
    """The keyword arguments of the calls of `called` (a name, or a method's name) in `tree`."""
    return {k.arg for n in ast.walk(tree) if isinstance(n, ast.Call) and getattr(n.func, "attr", getattr(n.func, "id", None)) == called for k in n.keywords}


to_run, to_build = keywords(route, "pd_agent_converse"), keywords(TREE["web_app/app.py"], "BambooAI")
check("...and the route hands a run, and the web app the host it builds, only what each takes - the mode and the depth among it (an argument one of them had "
      "stopped taking would end every question in an error)",
      {"mode", "max_investigations"} <= to_run <= set(inspect.signature(B.BambooAI.pd_agent_converse).parameters)
      and {"df", "user_id", "search_tool"} <= to_build <= set(inspect.signature(B.BambooAI.__init__).parameters),
      (sorted(to_run - set(inspect.signature(B.BambooAI.pd_agent_converse).parameters)), sorted(to_build - set(inspect.signature(B.BambooAI.__init__).parameters))))

# ------------------------------------------------------------------------------------------ 4. what 0347 removed
WEB = "".join(text for path, text in SOURCE.items() if path.startswith("web_app/"))
still = {
    "arguments of the host": sorted({"max_conversations", "exploratory", "planning", "custom_prompt_file"} & set(inspect.signature(B.BambooAI.__init__).parameters)),
    "arguments of a run": sorted({"auto_explore"} & set(inspect.signature(B.BambooAI.pd_agent_converse).parameters)),
    "arguments of the prompt loader": sorted(set(inspect.signature(PromptManager.__init__).parameters) - {"self"}),
    "the host's old switches": re.findall(r"self\.(?:planning|exploratory)\b", SOURCE["bambooai/bambooai.py"]),
    "routes": [r for r in ("/update_planning", "/get_planning_state", "/submit_feedback") if r in WEB],
    "settings and constants of the web app": [w for w in ("'planning'", "'ontology_path'", "EXPLORATORY", "auto_explore =", "max_iterations") if w in WEB],
    "the page's request": [w for w in ("auto_explore:", "max_iterations:") if w in PAGE],
    "functions": [f"{where.__name__}.{name}" for where, names in ((utils, ("ordinal", "get_readable_date", "store_dataset_details", "dataframe_to_string", "dataframe_summary_to_string")),
                                                                  (executor_client.ExecutorAPIClient, ("store_dataset_details", "dataframe_to_string")),
                                                                  (models.ModelManager, ("seat_on_another_seats_model",)), (prompt_cache, ("new_session",)))
                  for name in names if hasattr(where, name)] + re.findall(r"def cleanup_threads\(", APP),
    "the executor's copy of the data": re.findall(r"original_df", SOURCE["bambooai/code_executor.py"]),
    "files": [p for p in ("bambooai/ledger.py", "web_app/ontologies/intervals_icu_ontology.ttl") if os.path.exists(os.path.join(ROOT, p))],
    "the package's data": [g for g in tomllib.loads(read("pyproject.toml"))["tool"]["setuptools"]["package-data"]["web_app"] if "ontolog" in g],
}
check("retired (0347): four arguments of the host nothing read and the loader's file only one of them reached; the two switches a run's mode replaced, with their "
      "routes and settings and what the page sent for them; a setting written in seven places and read in none; a route and ten functions nothing called, with "
      "the module nothing imported; the copy of the data the executor made before every script and never read; and the ontology file nothing read",
      not any(still.values()), {k: v for k, v in still.items() if v})

print(f"\n{len(passed)} passed, {len(failed)} failed")
sys.exit(1 if failed else 0)
