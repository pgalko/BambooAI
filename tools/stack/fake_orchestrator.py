"""A stand-in for the orchestrator service (orchestration/orchestrator_api.py).

    python3 tools/stack/fake_orchestrator.py --port 5056 --executor-port 5055

Same HTTP surface the web app's client (orchestration/main_app_integration.py) calls:
/spawn/<user>, /status/<user>, /containers, /activity/<user>, /destroy/<user>, /health.
Every user gets the one local executor. The answers mirror the real ContainerManager's
shapes; the executor's real /health decides "ready" versus "failed". Every call is recorded
and served back at /_harness/calls so a test can assert what the app asked for and when.

Not here: Nomad, tiers, capacity, the idle reaper, the destroy-on-a-missed-probe rule. This
is the seam where the real ContainerManager can later be driven against a fake Nomad.
"""
import argparse
import os
import threading
import time
from datetime import datetime

import requests
from flask import Flask, jsonify, request

app = Flask(__name__)
STATE = {"executor": None, "containers": {}, "calls": [], "lock": threading.Lock()}


def _record(kind, user_id=None, **extra):
    with STATE["lock"]:
        STATE["calls"].append({"t": time.time(), "kind": kind, "user_id": user_id, **extra})


def _healthy():
    try:
        r = requests.get(f"http://127.0.0.1:{STATE['executor']}/health", timeout=5)
        return r.status_code == 200 and r.json().get("status") == "healthy", (r.json().get("ram_gb") if r.ok else 0)
    except Exception:                                   # noqa: BLE001
        return False, 0


@app.route("/health")
def health():
    return jsonify({"status": "healthy", "service": "fake-orchestrator", "executor_port": STATE["executor"]})


@app.route("/spawn/<user_id>", methods=["POST"])
def spawn(user_id):
    tier = (request.json or {}).get("compute_tier", "free")
    if user_id not in STATE["containers"]:
        time.sleep(float(os.environ.get("STACK_SPAWN_DELAY", "0")))     # a cold start takes time; rehearse it
        if os.environ.get("STACK_SPAWN_FAIL") == "1":
            _record("spawn", user_id, tier=tier, action="failed", healthy=False)
            return jsonify({"status": "error", "error": "rehearsed start failure", "user_id": user_id, "tier": tier}), 200
    ok, ram = _healthy()
    existing = STATE["containers"].get(user_id)
    action = "reused" if existing else "created"
    _record("spawn", user_id, tier=tier, action=action, healthy=ok)
    if not ok:
        return jsonify({"status": "error", "error": "local executor is not healthy", "user_id": user_id, "tier": tier}), 200
    if existing is None:
        existing = STATE["containers"][user_id] = {
            "ip": "127.0.0.1", "port": str(STATE["executor"]), "job_id": f"local-{user_id}", "tier": tier,
            "created_at": datetime.now().isoformat(), "last_activity": datetime.now().isoformat()}
    return jsonify({"ip": existing["ip"], "port": existing["port"], "job_id": existing["job_id"], "status": "ready",
                    "user_id": user_id, "tier": existing["tier"], "action": action})


@app.route("/status/<user_id>", methods=["GET"])
def status(user_id):
    c = STATE["containers"].get(user_id)
    ok, ram = _healthy()
    _record("status", user_id, known=bool(c), healthy=ok)
    if c is None:
        return jsonify({"status": "not_found", "user_id": user_id}), 200
    if not ok:
        return jsonify({"status": "failed", "user_id": user_id}), 200
    return jsonify({"status": "ready", "ip": c["ip"], "port": c["port"], "job_id": c["job_id"], "tier": c["tier"],
                    "ram_gb": ram, "user_id": user_id}), 200


@app.route("/containers", methods=["GET"])
def containers():
    return jsonify({"active_containers": STATE["containers"], "count": len(STATE["containers"]),
                    "timestamp": datetime.now().isoformat()})


@app.route("/activity/<user_id>", methods=["POST"])
def activity(user_id):
    c = STATE["containers"].get(user_id)
    if c:
        c["last_activity"] = datetime.now().isoformat()
    _record("activity", user_id)
    return jsonify({"status": "updated", "user_id": user_id}), 200


@app.route("/destroy/<user_id>", methods=["DELETE"])
def destroy(user_id):
    existed = STATE["containers"].pop(user_id, None) is not None
    _record("destroy", user_id, existed=existed)
    return jsonify({"status": "destroyed" if existed else "not_found", "user_id": user_id}), 200


@app.route("/_harness/calls", methods=["GET", "DELETE"])
def calls():
    with STATE["lock"]:
        if request.method == "DELETE":
            STATE["calls"].clear()
        return jsonify({"calls": list(STATE["calls"])})


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=5056)
    ap.add_argument("--executor-port", type=int, default=5055)
    a = ap.parse_args()
    STATE["executor"] = a.executor_port
    print(f"[orchestrator] fake; executor at 127.0.0.1:{a.executor_port}; port {a.port}", flush=True)
    app.run(host="127.0.0.1", port=a.port, debug=False, threaded=True, use_reloader=False)


if __name__ == "__main__":
    main()
