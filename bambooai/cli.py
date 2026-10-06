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

The analysis runs in the executor container (docs/OSS_DESIGN.md D27, as ruled on 2026-09-15): the
same image the hosted service runs, built here from the Dockerfile the package ships, managed by
`serve` - built on first use, started or reused, waited for, stopped on exit. Model-written code
never runs on this machine's account. `--compute local` (or BAMBOO_COMPUTE=local) is the fallback
for a machine without Docker: the kernel in a subprocess here, no isolation, no integrations.

Nothing here reads /etc/bambooai or the hosted box's gunicorn configuration.
"""
import argparse
import os
import re
import secrets
import shutil
import subprocess
import sys
import threading
import time
import webbrowser

DEFAULT_HOME = os.path.join(os.path.expanduser("~"), "bambooai")
ENV_FILE = ".env"

# the edition's defaults: applied only where .env leaves a variable unset
DEFAULTS = {
    "AUTH_MODE": "single",
    "BAMBOO_COMPUTE": "docker",
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
# docker: the analysis runs in the executor container, built and managed by `bambooai serve` (needs Docker running).
# local: the kernel in a subprocess on this machine - no isolation, no integrations - for a machine without Docker.
BAMBOO_COMPUTE=docker
# the port the executor container is published on
EXECUTOR_PORT=5055
# an executor you run yourself (Docker or a server): set these two and BAMBOO_COMPUTE is ignored
# EXECUTION_MODE=api
# EXECUTOR_API_BASE_URL=http://localhost:5055

# --- model keys (only the providers you use) ---------------------------------------
OPENROUTER_API_KEY=
# OPENAI_API_KEY=
# ANTHROPIC_API_KEY=
# GEMINI_API_KEY=            (also turns web search on: Google AI grounding)
# GROQ_API_KEY=
# XAI_API_KEY=
# MISTRAL_API_KEY=
# Ollama on your own computer (the default, http://localhost:11434) or on another machine. Agents with
# "provider": "ollama" in LLM_CONFIG_template.json use it; cloud models need that machine signed in.
# REMOTE_OLLAMA=http://localhost:11434
# Ollama's cloud without a server: REMOTE_OLLAMA=https://ollama.com and a key from ollama.com/settings/keys
# OLLAMA_API_KEY=
# how long a model stays loaded between turns (default 30m) and how long a started stream may be silent (default 300 s)
# OLLAMA_KEEP_ALIVE=30m
# OLLAMA_IDLE_TIMEOUT=300
# vLLM, an OpenAI-compatible server you run (agents with "provider": "vllm"); the key only if the server was started with --api-key
# REMOTE_VLLM=http://localhost:8000/v1
# VLLM_API_KEY=

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


# ---------------------------------------------------------------------------- the executor container
EXECUTOR_CONTAINER = "bambooai-executor"


def _version():
    try:
        from importlib.metadata import version
        return version("bambooai")
    except Exception:                                       # noqa: BLE001
        return "dev"


def _docker(*args, capture=True, timeout=None):
    return subprocess.run(["docker", *args], capture_output=capture, text=True, timeout=timeout)


def docker_ready():
    """None when Docker can be used; otherwise the sentence to print."""
    if shutil.which("docker") is None:
        return "Docker is not installed. Install Docker Desktop (or Docker Engine), or run `bambooai serve --compute local`."
    try:
        r = _docker("info", timeout=20)
    except subprocess.TimeoutExpired:
        return "Docker did not answer. Is Docker Desktop running? (or: bambooai serve --compute local)"
    if r.returncode != 0:
        return "Docker is installed but not running. Start Docker Desktop, or run `bambooai serve --compute local`."
    return None


def _executor_context():
    context = os.path.join(_package_root(), "bambooai_executor_image")
    if not os.path.exists(os.path.join(context, "Dockerfile")):
        context = os.path.join(_package_root(), "containers", "executor")     # a checkout, installed editable
    return context


def _executor_stamp():
    """The executor's own build stamp (EXECUTOR_BUILD in code_executor_api.py, '2026-10-06 v51 (DS in every run)'),
    reduced to its version token: v51. A changed executor is a changed tag, so the image is rebuilt on the
    next serve instead of an old one being reused for the life of the package version (found 2026-10-03:
    the documents routes never reached the container because the 2.0.2 image predated them)."""
    try:
        with open(os.path.join(_executor_context(), "code_executor_api.py"), encoding="utf-8", errors="replace") as f:
            m = re.search(r"EXECUTOR_BUILD\s*=\s*['\"].*?\b(v\d+)\b", f.read())
        return m.group(1) if m else "v0"
    except OSError:
        return "v0"


def executor_image():
    return f"bambooai-executor:{_version()}-{_executor_stamp()}"


def build_executor_image(image):
    """The image from the Dockerfile the package ships - the hosted service's image, built here."""
    context = _executor_context()
    print(f"bambooai: building the executor image {image} (once per package version and executor build; a few minutes - the analysis libraries are installed inside it)")
    r = subprocess.run(["docker", "build", "-t", image, context], text=True)
    if r.returncode != 0:
        sys.exit(f"bambooai: the image build failed (see above). Fix and retry, or run `bambooai serve --compute local`.")


def start_executor(port):
    """Build if absent, start or reuse the container, wait for its health. Returns the executor's URL."""
    image = executor_image()
    if _docker("image", "inspect", image).returncode != 0:
        build_executor_image(image)
    running = _docker("ps", "--filter", f"name=^{EXECUTOR_CONTAINER}$", "--format", "{{.Image}}|{{.Ports}}").stdout.strip()
    reuse = bool(running) and running.split("|")[0] == image and f":{port}->" in running
    if reuse:
        # a container listed as running may be on its way down - a previous serve's `docker stop` cut short by a
        # second Ctrl-C finishes in the background (found on the Mac, 2026-09-15). Trust it only after it has stayed
        # up and healthy for a moment; otherwise start a fresh one.
        time.sleep(3)
        alive = _docker("ps", "-q", "--filter", f"name=^{EXECUTOR_CONTAINER}$").stdout.strip() != ""
        reuse = alive and _health_ok(f"http://127.0.0.1:{port}")
        if reuse:
            print(f"bambooai: executor already running ({image})")
        else:
            print("bambooai: the running executor is stopping or unhealthy; starting a fresh one")
    if not reuse:
        _docker("rm", "-f", EXECUTOR_CONTAINER)                     # a stopped, older, or differently-published one
        r = _docker("run", "-d", "--name", EXECUTOR_CONTAINER, "-p", f"127.0.0.1:{port}:5000",
                    "-e", "KERNEL_MAX_SESSIONS=4", image)
        if r.returncode != 0:
            sys.exit(f"bambooai: could not start the executor container: {r.stderr.strip()[-400:]}")
        print(f"bambooai: executor started ({image}, port {port})")
    url = f"http://127.0.0.1:{port}"
    deadline = time.time() + 180
    while time.time() < deadline:
        if _health_ok(url):
            return url
        if _docker("ps", "-q", "--filter", f"name=^{EXECUTOR_CONTAINER}$").stdout.strip() == "":
            sys.exit(f"bambooai: the executor container stopped while starting. `docker logs {EXECUTOR_CONTAINER}` shows why.")
        time.sleep(1)
    sys.exit(f"bambooai: the executor did not become healthy at {url}/health within three minutes (`docker logs {EXECUTOR_CONTAINER}`).")


def _health_ok(url):
    import urllib.request
    try:
        with urllib.request.urlopen(f"{url}/health", timeout=3) as resp:
            return resp.status == 200
    except Exception:                                       # noqa: BLE001
        return False


def stop_executor():
    """Stop the container on the way out. A second Ctrl-C must not cut this short: Docker would finish the
    stop in the background and the next serve could reuse a container about to die."""
    import signal
    previous = signal.signal(signal.SIGINT, signal.SIG_IGN)
    try:
        print("bambooai: stopping the executor container (a few seconds)...")
        _docker("stop", "-t", "8", EXECUTOR_CONTAINER, timeout=60)
        print("bambooai: executor stopped")
    except Exception:                                       # noqa: BLE001
        pass
    finally:
        signal.signal(signal.SIGINT, previous)


def resolve_compute(compute_flag):
    """Decide where the analysis runs, from the flag, then .env, then the default; set the app's variables."""
    if os.environ.get("EXECUTOR_API_BASE_URL"):            # an executor the person runs themselves
        os.environ["EXECUTION_MODE"] = "api"
        return "external"
    compute = compute_flag or os.environ.get("BAMBOO_COMPUTE") or DEFAULTS["BAMBOO_COMPUTE"]
    if compute == "local":
        os.environ["EXECUTION_MODE"] = "local"
        os.environ.pop("EXECUTOR_API_BASE_URL", None)
        return "local"
    problem = docker_ready()
    if problem:
        sys.exit("bambooai: " + problem)
    port = int(os.environ.get("EXECUTOR_PORT") or 5055)
    os.environ["EXECUTOR_API_BASE_URL"] = start_executor(port)
    os.environ["EXECUTION_MODE"] = "api"
    os.environ["BAMBOO_EXECUTOR_CONTAINER"] = EXECUTOR_CONTAINER   # the app may restart it (the chip's Restart)
    return "docker"


def make_app(home):
    """Import the web app with the working folder as its working directory."""
    root = _package_root()
    for p in (os.path.join(root, "web_app"), os.path.join(root, "delve"), root):
        if p not in sys.path:
            sys.path.insert(0, p)
    os.chdir(home)
    import app as webapp                                     # web_app/app.py: builds its folders under the working directory
    return webapp.application


def serve(home, host, port, open_browser=True, compute=None, keep_executor=False):
    home = init_home(home)
    load_env(home)
    port = int(port or os.environ.get("APP_PORT") or DEFAULTS["APP_PORT"])
    url = f"http://{host if host not in ('0.0.0.0', '') else '127.0.0.1'}:{port}"
    if _missing_keys():
        print(f"bambooai: no model key found in {os.path.join(home, ENV_FILE)} - add one (OPENROUTER_API_KEY, for instance) and restart.")
    where = resolve_compute(compute)
    print(f"bambooai: {url}  (edition: {os.environ.get('AUTH_MODE')}, compute: {where}"
          f"{' at ' + os.environ['EXECUTOR_API_BASE_URL'] if os.environ.get('EXECUTOR_API_BASE_URL') else ' - the kernel on this machine, no isolation'}, home: {home})")
    if where == "docker" and not keep_executor:
        import atexit
        import signal
        atexit.register(stop_executor)                      # Ctrl-C stops the app; the container goes with it
        signal.signal(signal.SIGTERM, lambda *a: sys.exit(0))   # a plain kill runs the exit hooks too (gunicorn sets its own handlers later)
    if open_browser:
        threading.Timer(1.5, lambda: webbrowser.open(url)).start()
    # The server. gunicorn forks its worker from the master; on macOS a child forked after numpy, the model
    # clients and Apple's frameworks have initialised dies with SIGSEGV at first use (found on the Mac,
    # 2026-09-15), so there werkzeug's threaded server runs the app in one process, no fork - it streams
    # fine for one person. On Linux gunicorn builds the app inside the worker, never before the fork.
    try:
        if sys.platform == "darwin" or os.environ.get("BAMBOO_SERVER") == "werkzeug":
            raise ImportError("werkzeug on this platform")
        import gunicorn.app.base as gunicorn_base           # one process, threads, long-lived streams (as the hosted box runs)

        class _App(gunicorn_base.BaseApplication):
            def load_config(self):
                for k, v in {"bind": f"{host}:{port}", "workers": 1, "worker_class": "gthread", "threads": 8,
                             "timeout": 600, "keepalive": 5, "loglevel": "warning", "accesslog": None}.items():
                    self.cfg.set(k, v)

            def load(self):
                return make_app(home)                        # in the worker, after the fork
        _App().run()
    except ImportError:
        import logging
        logging.getLogger("werkzeug").setLevel(logging.WARNING)
        from werkzeug.serving import run_simple
        run_simple(host, port, make_app(home), threaded=True, use_reloader=False)


def main(argv=None):
    ap = argparse.ArgumentParser(prog="bambooai", description="BambooAI - the self-hosted edition")
    sub = ap.add_subparsers(dest="cmd")
    s = sub.add_parser("serve", help="run the web app (the default)")
    s.add_argument("--home", default=os.environ.get("BAMBOO_HOME", DEFAULT_HOME), help=f"the working folder (default {DEFAULT_HOME})")
    s.add_argument("--port", type=int, default=None, help="default APP_PORT from .env, else 5001")
    s.add_argument("--host", default="127.0.0.1", help="127.0.0.1 (default) or 0.0.0.0 to reach it from another machine")
    s.add_argument("--no-browser", action="store_true")
    s.add_argument("--compute", choices=("docker", "local"), default=None,
                   help="docker (default; the executor container) or local (the kernel here: no isolation, no integrations)")
    s.add_argument("--keep-executor", action="store_true", help="leave the executor container running when the app stops")
    i = sub.add_parser("init", help="create the working folder and its files, then stop")
    i.add_argument("--home", default=os.environ.get("BAMBOO_HOME", DEFAULT_HOME))
    sub.add_parser("where", help="print the working folder")
    a = ap.parse_args(argv)
    if a.cmd in (None, "serve"):
        home = getattr(a, "home", os.environ.get("BAMBOO_HOME", DEFAULT_HOME))
        serve(home, getattr(a, "host", "127.0.0.1"), getattr(a, "port", None), open_browser=not getattr(a, "no_browser", False),
              compute=getattr(a, "compute", None), keep_executor=getattr(a, "keep_executor", False))
    elif a.cmd == "init":
        home = init_home(a.home)
        print(f"bambooai: edit {os.path.join(home, ENV_FILE)} (a model key at least), then: bambooai serve")
    elif a.cmd == "where":
        print(os.environ.get("BAMBOO_HOME", DEFAULT_HOME))


if __name__ == "__main__":
    main()
