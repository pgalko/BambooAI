"""bambooai - the self-hosted edition's command (docs/OSS_DESIGN.md D19, D29; phase 4, 2026-09-15).

    bambooai serve [--home DIR] [--port N] [--host H] [--no-browser]
    bambooai init  [--home DIR]          make the working folder and its files, then stop
    bambooai where                       print the working folder

One working folder, BAMBOO_HOME (default ~/bambooai), owns everything the app writes: .env,
LLM_CONFIG_template.json (your copy of the seats and prices), bambooai.sqlite, and per user
config/, storage/, memory/, logs/, temp/, datasets/, iframe_figures/. The code is never written
to, wherever it is installed. `serve` writes a .env with generated secrets the first time, loads
it, applies the edition's defaults for anything the file leaves unset, moves into the folder (the
app resolves its paths from the working directory) and runs the web app on localhost.

Nothing here reads /etc/bambooai or the hosted box's gunicorn configuration.
"""
import argparse
import os
import secrets
import shutil
import sys
import threading
import webbrowser

DEFAULT_HOME = os.path.join(os.path.expanduser("~"), "bambooai")
ENV_FILE = ".env"

# the edition's defaults: applied only where .env leaves a variable unset
DEFAULTS = {
    "AUTH_MODE": "single",
    "EXECUTION_MODE": "local",
    "BAMBOO_USER": "local",
    "BAMBOO_LEVEL": "performance",
    "SESSION_COOKIE_NAME": "bambooai",
    "WEB_SEARCH_MODE": "google_ai",
    "APP_PORT": "5001",
}

ENV_TEMPLATE = """# BambooAI - the self-hosted edition. This file is yours; the app never rewrites it.
# Keys are read from here (there is no key entry in the app). Lines starting with # are ignored;
# do not put comments after a value on the same line.

# --- who and how -----------------------------------------------------------------
# one person, no sign-in
AUTH_MODE=single
# names your folders: config/local, storage/local, memory/local...
BAMBOO_USER=local
# cost | performance | max - the first default; the account dialog saves your later choice
BAMBOO_LEVEL=performance
# local: the kernel runs on this machine. api with EXECUTOR_API_BASE_URL: a docker executor
EXECUTION_MODE=local
# EXECUTOR_API_BASE_URL=http://localhost:5055

# --- model keys (only the providers you use) ---------------------------------------
OPENROUTER_API_KEY=
# OPENAI_API_KEY=
# ANTHROPIC_API_KEY=
# GEMINI_API_KEY=            (also turns web search on: Google AI grounding)
# GROQ_API_KEY=
# XAI_API_KEY=
# MISTRAL_API_KEY=
# a local model server
# REMOTE_OLLAMA=http://localhost:11434
# REMOTE_VLLM=http://localhost:8000/v1

# --- integrations (each needs your own registration with the provider) -------------
# SWEATSTACK_CLIENT_ID=
# SWEATSTACK_CLIENT_SECRET=

# --- the server ----------------------------------------------------------------------
APP_PORT=5001
SESSION_COOKIE_NAME=bambooai
FLASK_SECRET={flask_secret}
LLM_CONFIG_ENCRYPTION_KEY={encryption_key}
"""


def _package_root():
    """The installed code: the folder that holds the bambooai, analyst, delve and web_app packages."""
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _refuse_code_folder(home):
    for marker in (".git", "pyproject.toml", "setup.py"):
        if os.path.exists(os.path.join(home, marker)):
            sys.exit(f"bambooai: {home} looks like a code checkout ({marker} is there). The working folder holds your data, "
                     f"not the code - pass --home DIR or set BAMBOO_HOME to another folder.")


def init_home(home, quiet=False):
    """The working folder and its files; safe to call every time."""
    home = os.path.abspath(os.path.expanduser(home))
    os.makedirs(home, exist_ok=True)
    _refuse_code_folder(home)
    env_path = os.path.join(home, ENV_FILE)
    made = []
    if not os.path.exists(env_path):
        with open(env_path, "w", encoding="utf-8") as fh:
            fh.write(ENV_TEMPLATE.format(flask_secret=secrets.token_urlsafe(32), encryption_key=secrets.token_urlsafe(32)))
        made.append(ENV_FILE)
    template_src = os.path.join(_package_root(), "web_app", "LLM_CONFIG_template.json")
    template_dst = os.path.join(home, "LLM_CONFIG_template.json")
    if not os.path.exists(template_dst) and os.path.exists(template_src):
        shutil.copy2(template_src, template_dst)
        made.append("LLM_CONFIG_template.json")
    for d in ("config", "storage", "memory", "logs", "temp", "datasets", "iframe_figures"):
        os.makedirs(os.path.join(home, d), exist_ok=True)
    if not quiet:
        print(f"bambooai: working folder {home}" + (f" (created {', '.join(made)})" if made else ""))
    return home


def load_env(home):
    """The folder's .env into the environment (a value already set in the environment wins), then the defaults."""
    env_path = os.path.join(home, ENV_FILE)
    try:
        from dotenv import load_dotenv
        load_dotenv(env_path, override=False)
    except ImportError:                                     # python-dotenv is a dependency; be tolerant anyway
        for line in open(env_path, encoding="utf-8"):
            line = line.split("#", 1)[0].strip()
            if "=" in line:
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip())
    for k, v in DEFAULTS.items():
        os.environ.setdefault(k, v)
    os.environ.setdefault("BAMBOO_HOME", home)
    os.environ.setdefault("BAMBOO_DATA_DIR", home)          # bambooai.sqlite (phase 3)
    os.environ.setdefault("BAMBOO_MEMORY_DIR", os.path.join(home, "memory"))


def _missing_keys():
    keys = ("OPENROUTER_API_KEY", "OPENAI_API_KEY", "ANTHROPIC_API_KEY", "GEMINI_API_KEY", "GROQ_API_KEY", "XAI_API_KEY", "MISTRAL_API_KEY", "REMOTE_OLLAMA", "REMOTE_VLLM")
    return not any(os.environ.get(k) for k in keys)


def make_app(home):
    """Import the web app with the working folder as its working directory."""
    root = _package_root()
    for p in (os.path.join(root, "web_app"), os.path.join(root, "delve"), root):
        if p not in sys.path:
            sys.path.insert(0, p)
    os.chdir(home)
    import app as webapp                                     # web_app/app.py: builds its folders under the working directory
    return webapp.application


def serve(home, host, port, open_browser=True):
    home = init_home(home)
    load_env(home)
    port = int(port or os.environ.get("APP_PORT") or DEFAULTS["APP_PORT"])
    application = make_app(home)
    url = f"http://{host if host not in ('0.0.0.0', '') else '127.0.0.1'}:{port}"
    if _missing_keys():
        print(f"bambooai: no model key found in {os.path.join(home, ENV_FILE)} - add one (OPENROUTER_API_KEY, for instance) and restart.")
    print(f"bambooai: {url}  (edition: {os.environ.get('AUTH_MODE')}, compute: {os.environ.get('EXECUTION_MODE')}"
          f"{', executor ' + os.environ['EXECUTOR_API_BASE_URL'] if os.environ.get('EXECUTOR_API_BASE_URL') else ''}, home: {home})")
    if open_browser:
        threading.Timer(1.5, lambda: webbrowser.open(url)).start()
    try:
        import gunicorn.app.base as gunicorn_base           # one process, threads, long-lived streams (as the hosted box runs)

        class _App(gunicorn_base.BaseApplication):
            def load_config(self):
                for k, v in {"bind": f"{host}:{port}", "workers": 1, "worker_class": "gthread", "threads": 8,
                             "timeout": 600, "keepalive": 5, "loglevel": "warning", "accesslog": None}.items():
                    self.cfg.set(k, v)

            def load(self):
                return application
        _App().run()
    except ImportError:                                     # no gunicorn (Windows): werkzeug's threaded server streams fine for one person
        from werkzeug.serving import run_simple
        run_simple(host, port, application, threaded=True, use_reloader=False)


def main(argv=None):
    ap = argparse.ArgumentParser(prog="bambooai", description="BambooAI - the self-hosted edition")
    sub = ap.add_subparsers(dest="cmd")
    s = sub.add_parser("serve", help="run the web app (the default)")
    s.add_argument("--home", default=os.environ.get("BAMBOO_HOME", DEFAULT_HOME), help=f"the working folder (default {DEFAULT_HOME})")
    s.add_argument("--port", type=int, default=None, help="default APP_PORT from .env, else 5001")
    s.add_argument("--host", default="127.0.0.1", help="127.0.0.1 (default) or 0.0.0.0 to reach it from another machine")
    s.add_argument("--no-browser", action="store_true")
    i = sub.add_parser("init", help="create the working folder and its files, then stop")
    i.add_argument("--home", default=os.environ.get("BAMBOO_HOME", DEFAULT_HOME))
    sub.add_parser("where", help="print the working folder")
    a = ap.parse_args(argv)
    if a.cmd in (None, "serve"):
        home = getattr(a, "home", os.environ.get("BAMBOO_HOME", DEFAULT_HOME))
        serve(home, getattr(a, "host", "127.0.0.1"), getattr(a, "port", None), open_browser=not getattr(a, "no_browser", False))
    elif a.cmd == "init":
        home = init_home(a.home)
        print(f"bambooai: edit {os.path.join(home, ENV_FILE)} (a model key at least), then: bambooai serve")
    elif a.cmd == "where":
        print(os.environ.get("BAMBOO_HOME", DEFAULT_HOME))


if __name__ == "__main__":
    main()
