"""The local stack: the real executor + the fake orchestrator + the real web app, together.

    python3 tools/stack/stack.py up      [--scenario field_trial] [--fresh]   start detached, print URLs
    python3 tools/stack/stack.py status                                        are the three answering?
    python3 tools/stack/stack.py down                                          stop them

    from stack import Stack
    with Stack(scenario="field_trial") as s:        # browse.py and the e2e tests use this
        s.app_url ...

Ports default to 5055 (executor), 5056 (orchestrator), 5001 (web app); --auto-ports picks free
ones. Everything the stack writes lives under --workdir (default /tmp/bamboo_stack):
executor/, webapp/ (config, storage, memory, logs), data/ (the scenario's dataset), logs/
(one file per process), stack.json (ports and pids of a detached stack).
"""
import argparse
import json
import os
import signal
import socket
import subprocess
import sys
import time

import requests

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
DEFAULT_WORKDIR = os.path.join("/tmp", "bamboo_stack")


def free_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _port_free(port):
    with socket.socket() as s:
        try:
            s.bind(("127.0.0.1", port))
            return True
        except OSError:
            return False


def stack_processes():
    """(pid, args) of every stack process on this machine, found by command line."""
    out = []
    try:
        ps = subprocess.run(["ps", "-eo", "pid,args"], capture_output=True, text=True).stdout
    except Exception:                                      # noqa: BLE001
        return out
    for line in ps.splitlines()[1:]:
        pid, _, args = line.strip().partition(" ")
        if "tools/stack/" in args and any(k in args for k in ("executor_launcher.py", "fake_orchestrator.py", "webapp_launcher.py")):
            out.append((int(pid), args))
    return out


def kill_stack_processes(match=""):
    """SIGTERM every stack process whose command line contains `match` ('' = all). Returns the pids."""
    pids = [pid for pid, args in stack_processes() if match in args and pid != os.getpid()]
    for pid in pids:
        try:
            os.killpg(os.getpgid(pid), signal.SIGTERM)
        except Exception:                                  # noqa: BLE001
            try:
                os.kill(pid, signal.SIGTERM)
            except Exception:                              # noqa: BLE001
                pass
    return pids


def _wait(url, ok, timeout=60, what=""):
    t0 = time.time()
    last = None
    while time.time() - t0 < timeout:
        try:
            r = requests.get(url, timeout=3)
            if ok(r):
                return True
            last = f"{r.status_code} {r.text[:80]}"
        except Exception as exc:                          # noqa: BLE001
            last = str(exc)[:80]
        time.sleep(0.5)
    raise RuntimeError(f"{what or url} not ready after {timeout}s: {last}")


class Stack:
    def __init__(self, workdir=DEFAULT_WORKDIR, scenario="field_trial", executor_port=5055, orchestrator_port=5056,
                 app_port=5001, auto_ports=False, fresh=False, detached=False, pause=0.0, edition="hosted"):
        self.workdir, self.scenario, self.fresh, self.detached, self.pause, self.edition = workdir, scenario, fresh, detached, pause, edition
        self.executor_port = free_port() if auto_ports else executor_port
        self.orchestrator_port = free_port() if auto_ports else orchestrator_port
        self.app_port = free_port() if auto_ports else app_port
        self.procs = {}
        self.app_url = f"http://127.0.0.1:{self.app_port}"
        self.executor_url = f"http://127.0.0.1:{self.executor_port}"
        self.orchestrator_url = f"http://127.0.0.1:{self.orchestrator_port}"
        self.dataset = None

    # ----------------------------------------------------------- lifecycle
    def _spawn(self, name, args):
        os.makedirs(os.path.join(self.workdir, "logs"), exist_ok=True)
        log = open(os.path.join(self.workdir, "logs", f"{name}.log"), "ab", buffering=0)
        env = dict(os.environ, STACK_TURN_PAUSE=str(self.pause))
        p = subprocess.Popen([sys.executable, "-u"] + args, stdout=log, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL,
                             cwd=ROOT, start_new_session=True, env=env)
        self.procs[name] = p
        return p

    def start(self):
        busy = [p for p in (self.executor_port, self.orchestrator_port, self.app_port) if not _port_free(p)]
        if busy:
            raise RuntimeError(f"port(s) {busy} already in use - `stack.py down` (or --auto-ports); "
                               f"stack processes running: {[pid for pid, _ in stack_processes()]}")
        os.makedirs(self.workdir, exist_ok=True)
        sys.path.insert(0, HERE)
        import harness_models
        mod = harness_models.load(self.scenario)
        os.makedirs(os.path.join(self.workdir, "data"), exist_ok=True)
        self.dataset = os.path.join(self.workdir, "data", getattr(mod, "DATASET_NAME", "data.csv"))
        if hasattr(mod, "make_dataset") and not os.path.exists(self.dataset):
            mod.make_dataset(self.dataset)

        self._spawn("executor", [os.path.join(HERE, "executor_launcher.py"), "--port", str(self.executor_port),
                                 "--workdir", os.path.join(self.workdir, "executor")])
        self._spawn("orchestrator", [os.path.join(HERE, "fake_orchestrator.py"), "--port", str(self.orchestrator_port),
                                     "--executor-port", str(self.executor_port)])
        web = [os.path.join(HERE, "webapp_launcher.py"), "--port", str(self.app_port), "--orchestrator-port",
               str(self.orchestrator_port), "--workdir", os.path.join(self.workdir, "webapp"), "--scenario", self.scenario, "--edition", self.edition]
        if self.fresh:
            web.append("--fresh")
        self._spawn("webapp", web)
        try:
            _wait(f"{self.executor_url}/health", lambda r: r.ok and r.json().get("status") == "healthy", 90, "executor")
            _wait(f"{self.orchestrator_url}/health", lambda r: r.ok, 30, "orchestrator")
            _wait(f"{self.app_url}/api/auth/status", lambda r: r.ok and "auth_enabled" in r.json(), 90, "web app")
        except Exception:
            self.stop()
            raise
        with open(os.path.join(self.workdir, "stack.json"), "w") as fh:
            json.dump({"ports": {"executor": self.executor_port, "orchestrator": self.orchestrator_port, "app": self.app_port},
                       "pids": {k: p.pid for k, p in self.procs.items()}, "scenario": self.scenario, "dataset": self.dataset,
                       "workdir": self.workdir}, fh, indent=1)
        return self

    def stop(self):
        for name, p in list(self.procs.items()):
            try:
                os.killpg(os.getpgid(p.pid), signal.SIGTERM)
            except Exception:                              # noqa: BLE001
                pass
        for name, p in list(self.procs.items()):
            try:
                p.wait(timeout=10)
            except Exception:                              # noqa: BLE001
                try:
                    os.killpg(os.getpgid(p.pid), signal.SIGKILL)
                except Exception:                          # noqa: BLE001
                    pass
        self.procs.clear()

    def __enter__(self):
        return self.start()

    def __exit__(self, *exc):
        if not self.detached:
            self.stop()

    # ---------------------------------------------------------------- probes
    def orchestrator_calls(self, clear=False):
        r = requests.request("DELETE" if clear else "GET", f"{self.orchestrator_url}/_harness/calls", timeout=5)
        return r.json().get("calls", [])

    def logs(self, name, tail=40):
        p = os.path.join(self.workdir, "logs", f"{name}.log")
        if not os.path.exists(p):
            return ""
        return "\n".join(open(p, encoding="utf-8", errors="replace").read().splitlines()[-tail:])


# ------------------------------------------------------------------ the CLI
def _state(workdir):
    p = os.path.join(workdir, "stack.json")
    return json.load(open(p)) if os.path.exists(p) else None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["up", "down", "status", "down-all"])
    ap.add_argument("--workdir", default=DEFAULT_WORKDIR)
    ap.add_argument("--scenario", default="field_trial")
    ap.add_argument("--fresh", action="store_true")
    ap.add_argument("--auto-ports", action="store_true")
    ap.add_argument("--pause", type=float, default=0.0, help="seconds the scripted analyst 'thinks' before each turn (to watch a run)")
    ap.add_argument("--edition", choices=("hosted", "local"), default="hosted", help="hosted (stand-ins for Auth0/Supabase) or the self-hosted edition")
    a = ap.parse_args()
    if a.cmd == "up":
        st = Stack(workdir=a.workdir, scenario=a.scenario, fresh=a.fresh, auto_ports=a.auto_ports, detached=True, pause=a.pause, edition=a.edition).start()
        print(f"web app      {st.app_url}\norchestrator {st.orchestrator_url}\nexecutor     {st.executor_url}\n"
              f"dataset      {st.dataset}\nlogs         {os.path.join(a.workdir, 'logs')}/")
    elif a.cmd == "down":
        s = _state(a.workdir)
        if s:
            for name, pid in s["pids"].items():
                try:
                    os.killpg(os.getpgid(pid), signal.SIGTERM); print(f"stopped {name} ({pid})")
                except Exception as exc:                   # noqa: BLE001
                    print(f"{name} ({pid}): {exc}")
            os.remove(os.path.join(a.workdir, "stack.json"))
        # whatever else is left from this workdir (a stack whose state file was lost)
        left = kill_stack_processes(a.workdir)
        if left:
            print(f"stopped {len(left)} stray stack process(es): {left}")
        if not s and not left:
            print("nothing to stop")
    elif a.cmd == "down-all":
        print("stopped:", kill_stack_processes("") or "nothing")
    else:
        s = _state(a.workdir)
        if not s:
            print("no stack.json"); return
        for name, port in s["ports"].items():
            url = {"executor": f"http://127.0.0.1:{port}/health", "orchestrator": f"http://127.0.0.1:{port}/health",
                   "app": f"http://127.0.0.1:{port}/api/auth/status"}[name]
            try:
                r = requests.get(url, timeout=3); print(f"{name:13s} {port}  {r.status_code}  {r.text[:70]}")
            except Exception as exc:                       # noqa: BLE001
                print(f"{name:13s} {port}  down  ({str(exc)[:60]})")


if __name__ == "__main__":
    main()
