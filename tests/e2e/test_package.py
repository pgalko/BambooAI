"""Phase 4 (docs/OSS_DESIGN.md D19): the package, installed, runs the self-hosted edition.

    python3 tests/e2e/test_package.py

Builds the wheel, installs it into a fresh virtualenv, runs `bambooai init` and `bambooai serve` from
the installed copy (never from the checkout) on a scratch working folder, and checks the folder's
files, the refusal of a code folder, the page, the local answers and the store. No model is called.
In this sandbox the virtualenv sees the system packages and the test stubs stand in for what is
not installed; on a real machine the same steps run with nothing but the package's dependencies.
"""
import glob
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.normpath(os.path.join(HERE, "..", ".."))
STACK = os.path.join(ROOT, "tools", "stack")           # the stack's stand-ins for packages the sandbox lacks (none needed on a real machine)
results = []


def check(name, cond, detail=""):
    results.append((name, bool(cond)))
    print(("  ok   " if cond else "  FAIL ") + name + ("" if cond else f"  <- {str(detail)[:300]}"))


FAKE_DOCKER = r'''#!/usr/bin/env python3
"""A docker stand-in for the package e2e: records every call, and `run` starts a tiny server answering /health."""
import json, os, subprocess, sys, tempfile, time
STATE = os.environ["FAKE_DOCKER_STATE"]
def load():
    return json.load(open(STATE)) if os.path.exists(STATE) else {"calls": [], "images": [], "container": None}
def save(st):
    json.dump(st, open(STATE, "w"))
st = load(); a = sys.argv[1:]; st["calls"].append(a)
out, rc = "", 0
if a[:1] == ["info"]:
    pass
elif a[:2] == ["image", "inspect"]:
    rc = 0 if a[2] in st["images"] else 1
elif a[:1] == ["build"]:
    st["images"].append(a[a.index("-t") + 1]); print("fake docker: built", a[a.index("-t") + 1])
elif a[:1] == ["ps"]:
    c = st["container"]
    if c and ("-q" in a):
        out = "abc123"
    elif c and "--format" in a:
        out = f'{c["image"]}|127.0.0.1:{c["port"]}->5000/tcp'
elif a[:2] == ["rm", "-f"]:
    st["container"] = None
elif a[:1] == ["run"]:
    port = a[a.index("-p") + 1].split(":")[1]; image = a[-1]
    d = tempfile.mkdtemp(); open(os.path.join(d, "health"), "w").write('{"status":"healthy","build":"fake"}')
    p = subprocess.Popen([sys.executable, "-m", "http.server", port, "--bind", "127.0.0.1", "-d", d], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    st["container"] = {"image": image, "port": port, "pid": p.pid, "started": str(time.time())}; out = "abc123"
elif a[:1] == ["inspect"]:
    c = st["container"]; out = c["started"] if c else ""; rc = 0 if c else 1
elif a[:1] == ["restart"]:
    c = st["container"]
    if c:
        c["started"] = str(time.time()); st["restarts"] = st.get("restarts", 0) + 1
elif a[:1] == ["stop"]:
    c = st["container"]
    if c:
        try: os.kill(c["pid"], 15)
        except OSError: pass
        st["container"] = None
save(st); sys.stdout.write(out); sys.exit(rc)
'''


def free_port():
    import socket
    s = socket.socket(); s.bind(("127.0.0.1", 0)); p = s.getsockname()[1]; s.close(); return p


def main():
    work = tempfile.mkdtemp(prefix="bamboo_pkg_")
    whl_dir, venv, home = os.path.join(work, "wheel"), os.path.join(work, "venv"), os.path.join(work, "home")
    # ---- the wheel
    r = subprocess.run([sys.executable, "-m", "pip", "wheel", ROOT, "--no-deps", "--no-build-isolation", "-w", whl_dir, "-q"], capture_output=True, text=True)
    wheels = glob.glob(os.path.join(whl_dir, "bambooai-*.whl"))
    check("the wheel builds from the checkout", r.returncode == 0 and wheels, r.stderr[-300:])
    # ---- a fresh virtualenv (system packages visible: the sandbox has no network for dependencies)
    subprocess.run([sys.executable, "-m", "venv", "--system-site-packages", venv], check=True)
    py = os.path.join(venv, "bin", "python")
    r = subprocess.run([py, "-m", "pip", "install", "--no-deps", "-q", wheels[0]], capture_output=True, text=True)
    check("the wheel installs into the virtualenv", r.returncode == 0, r.stderr[-300:])
    probe = subprocess.run([py, "-c", "import importlib.util as u, os; print('SITE=' + os.path.dirname(os.path.dirname(u.find_spec('bambooai').origin)))"],
                           capture_output=True, text=True, cwd=work).stdout           # not from the checkout's directory
    site = next((l.split("SITE=", 1)[1].strip() for l in probe.splitlines() if "SITE=" in l), "")
    check("the installed copy is the virtualenv's, not the checkout", site.startswith(venv), site)
    for f in ("web_app/templates/index.html", "web_app/static/js/workspace-gate.js", "web_app/LLM_CONFIG_template.json", "analyst/contract.md", "bambooai/messages/default_prompts.yaml", "delve/kernel.py"):
        check(f"installed: {f}", os.path.exists(os.path.join(site, f)))
    env = dict(os.environ, PYTHONPATH=STACK)
    PRE = "import sandbox; sandbox.install(); "              # only packages that are not installed are faked; nothing on a full install
    run = lambda args, **kw: subprocess.run([py, "-c", PRE + "from bambooai.cli import main; main(%r)" % (args,)], capture_output=True, text=True, env=env, cwd=work, **kw)  # noqa: E731

    # ---- bambooai init
    r = run(["init", "--home", home])
    check("bambooai init creates the working folder", r.returncode == 0 and os.path.isdir(home), r.stdout + r.stderr)
    env_text = open(os.path.join(home, ".env")).read() if os.path.exists(os.path.join(home, ".env")) else ""
    check("init wrote .env with generated secrets and the edition's settings", "FLASK_SECRET=" in env_text and "AUTH_MODE=single" in env_text and "BAMBOO_COMPUTE=docker" in env_text and len(env_text.split("FLASK_SECRET=")[1].splitlines()[0]) > 20, env_text[:200])
    check("init copied the template and made the folders", os.path.exists(os.path.join(home, "LLM_CONFIG_template.json")) and all(os.path.isdir(os.path.join(home, d)) for d in ("config", "storage", "memory", "logs")))
    r2 = run(["init", "--home", home])
    check("init is safe to repeat (nothing recreated, the .env kept)", r2.returncode == 0 and open(os.path.join(home, ".env")).read() == env_text, r2.stdout)
    r3 = run(["init", "--home", ROOT])
    check("a code checkout is refused as a working folder", r3.returncode != 0 and "code checkout" in (r3.stdout + r3.stderr), (r3.returncode, (r3.stdout + r3.stderr)[-200:]))

    # ---- bambooai serve
    port = free_port()
    proc = subprocess.Popen([py, "-c", PRE + "from bambooai.cli import main; main(['serve', '--home', %r, '--port', '%d', '--no-browser', '--compute', 'local'])" % (home, port)],
                            env=env, cwd=work, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    import requests
    base = f"http://127.0.0.1:{port}"
    up = False
    for _ in range(120):
        try:
            if requests.get(f"{base}/api/auth/status", timeout=2).ok:
                up = True; break
        except Exception:
            pass
        if proc.poll() is not None:
            break
        time.sleep(0.5)
    out = ""
    if not up:
        out = proc.stdout.read() if proc.stdout else ""
    check("bambooai serve comes up on the port", up, out[-1500:])
    if up:
        st = requests.get(f"{base}/api/auth/status").json()
        check("the edition: single mode with the local identity", st.get("mode") == "single" and (st.get("user") or {}).get("name") == "local", st)
        page = requests.get(base).text
        check("the page is served from the installed templates (the workspace gate is in it)", 'id="workspaceGate"' in page and "workspace-gate.js" in page)
        js = requests.get(f"{base}/static/js/workspace-gate.js")
        check("the static files are served from the installed copy", js.ok and "WorkspaceGate" in js.text)
        sub = requests.get(f"{base}/api/subscription").json()
        check("accounts answer locally (managed, local compute)", (sub.get("data") or sub).get("compute_tier") == "local", sub)
        cs = requests.get(f"{base}/api/container/status").json()
        check("--compute local: the kernel on this machine (status local, ready)", cs.get("status") == "ready" and cs.get("tier") == "local", cs)
        init = requests.post(f"{base}/api/user/initialize", json={})
        check("the user session initialises (the config built from the copied template)", init.ok and os.path.exists(os.path.join(home, "config", "local", "LLM_CONFIG.json")), init.text[:200])
        labels = requests.get(f"{base}/api/labels").json()
        check("the store answers (labels list) and the file sits in the working folder", labels.get("success") is True and os.path.exists(os.path.join(home, "bambooai.sqlite")), labels)
        check("nothing was written into the installed code", not glob.glob(os.path.join(site, "web_app", "config")) and not glob.glob(os.path.join(site, "web_app", "storage")))
    proc.terminate()
    try:
        proc.wait(timeout=10)
    except subprocess.TimeoutExpired:
        proc.kill()

    # ---- the default compute is Docker: without it, a clear refusal
    env_nodocker = dict(env, PATH=os.path.join(work, "empty-bin"))
    os.makedirs(os.path.join(work, "empty-bin"), exist_ok=True)
    os.symlink(py, os.path.join(work, "empty-bin", "python3"))
    r = subprocess.run([py, "-c", PRE + "from bambooai.cli import main; main(['serve', '--home', %r, '--port', '%d', '--no-browser'])" % (home, free_port())],
                       capture_output=True, text=True, env=env_nodocker, cwd=work, timeout=120)
    check("without Docker, serve refuses with the remedy (Docker Desktop, or --compute local)", r.returncode != 0 and "Docker is not installed" in (r.stdout + r.stderr) and "--compute local" in (r.stdout + r.stderr), (r.returncode, (r.stdout + r.stderr)[-300:]))

    # ---- the Docker path, with a docker stand-in on PATH: build on first use, run, health, stop on exit
    bin_dir = os.path.join(work, "fake-bin"); os.makedirs(bin_dir, exist_ok=True)
    fake = os.path.join(bin_dir, "docker"); open(fake, "w").write(FAKE_DOCKER); os.chmod(fake, 0o755)
    state = os.path.join(work, "fake_docker_state.json")
    env_docker = dict(env, PATH=bin_dir + os.pathsep + env["PATH"], FAKE_DOCKER_STATE=state, EXECUTOR_PORT=str(free_port()))
    port2 = free_port()
    proc = subprocess.Popen([py, "-c", PRE + "from bambooai.cli import main; main(['serve', '--home', %r, '--port', '%d', '--no-browser'])" % (home, port2)],
                            env=env_docker, cwd=work, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    base2 = f"http://127.0.0.1:{port2}"; up = False
    for _ in range(120):
        try:
            if requests.get(f"{base2}/api/auth/status", timeout=2).ok:
                up = True; break
        except Exception:
            pass
        if proc.poll() is not None:
            break
        time.sleep(0.5)
    out = "" if up else (proc.stdout.read() if proc.stdout else "")
    check("with Docker (stand-in): serve builds the image, starts the executor and comes up", up, out[-1200:])
    if up:
        st_ = json.load(open(state)); kinds = [c[0] for c in st_["calls"]]
        check("the image was built once, on first use, and the container started", kinds.count("build") == 1 and "run" in kinds, kinds)
        check("the image is tagged with the package version", any(t.startswith("bambooai-executor:") for t in st_["images"]), st_["images"])
        cs = requests.get(f"{base2}/api/container/status").json()
        check("compute: the executor container (status ready, tier docker, from its own /health)", cs.get("status") == "ready" and cs.get("tier") == "docker", cs)
        check("the container's port is published on localhost only", any("127.0.0.1:" in c[c.index("-p") + 1] for c in st_["calls"] if c[:1] == ["run"] and "-p" in c))
        job_before = cs.get("job_id")
        check("the status carries a job id for the managed container (Docker's start time)", bool(job_before) and cs.get("managed") is True, cs)
        rr = requests.post(f"{base2}/api/container/restart", json={})
        check("the chip's Restart restarts the managed container", rr.ok and rr.json().get("success") is True, rr.text[:200])
        cs2 = requests.get(f"{base2}/api/container/status").json()
        check("after the restart the job id is new, which is what the page waits for before reloading", cs2.get("status") == "ready" and cs2.get("job_id") and cs2.get("job_id") != job_before, (job_before, cs2.get("job_id")))
    proc.terminate()
    try:
        proc.wait(timeout=15)
    except subprocess.TimeoutExpired:
        proc.kill()
    st_ = json.load(open(state)) if os.path.exists(state) else {"calls": []}
    check("on exit the executor container is stopped", ["stop", "bambooai-executor"] in st_["calls"], [c for c in st_["calls"] if c[:1] == ["stop"]])
    n_fail = sum(1 for _, ok in results if not ok)
    print(f"{len(results) - n_fail} passed, {n_fail} failed")
    shutil.rmtree(work, ignore_errors=True)
    sys.exit(1 if n_fail else 0)


if __name__ == "__main__":
    main()
