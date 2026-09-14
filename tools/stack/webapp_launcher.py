"""Run the REAL web app (web_app/app.py) as a local process.

    python3 tools/stack/webapp_launcher.py --port 5001 --orchestrator-port 5056 \
        --workdir /tmp/bamboo_stack/webapp --scenario field_trial

No production file changes. What is replaced, in this process only, before app.py is imported:
  * the Auth0 token check: auth.auth_handler.validate_auth0_token accepts the fixed token the
    browser stand-in sends ('local-token') as user auth0|localuser; ensure_user_exists is a no-op;
  * the model provider: tools/stack/harness_models.py is registered as
    bambooai.models.vllm_models, and the local LLM_CONFIG_template.json seats every agent on it
    ("provider": "vllm"), so the app's own ModelManager, log manager, cost accounting and
    streaming all run for real over a scripted analyst;
  * the web-search seam: bambooai.google_search.SmartSearchOrchestrator returns the scenario's
    canned digest and sources (no key, no network).
  * Supabase: tools/stack/fake_supabase.py, an in-memory store seeded with one free-tier user,
    behind the app's own client code (env SUPABASE_* point at it). Stripe stays unconfigured. The orchestrator is the fake at --orchestrator-port; the executor behind it is real.

Environment the app reads (same names as /etc/bambooai/*.env on the box): AUTH_MODE, AUTH0_*,
FLASK_SECRET, ORCHESTRATOR_API_URL, EXECUTION_MODE=api, BAMBOO_MEMORY_DIR, SYNTHESIS_INFOGRAPHIC.
The working directory holds LLM_CONFIG_template.json, config/, storage/, logs/, temp/ - the
app's cwd-relative layout, as under gunicorn on the box.
"""
import argparse
import json
import os
import shutil
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
TOKEN = "local-token"
USER_SUB = "auth0|localuser"
HARNESS_MODEL = "harness/analyst-sim"


def local_template(workdir):
    """The real template with every seat on the scripted provider (the tier budgets untouched)."""
    src = json.load(open(os.path.join(ROOT, "web_app", "LLM_CONFIG_template.json"), encoding="utf-8"))
    seat = {"model": HARNESS_MODEL, "provider": "vllm", "reasoning_effort": "medium", "max_tokens": 16000}
    for key in ("free_agent_configs", "cost_agent_configs", "performance_agent_configs", "max_agent_configs"):
        for a in src.get(key, []):
            a["details"] = dict(seat)
    src.setdefault("model_properties", {})[HARNESS_MODEL] = {
        "capability": "reasoning", "multimodal": "false", "templ_formating": "text",
        "reasoning_style": "effort", "reasoning_efforts": ["low", "medium", "high"],
        "prompt_tokens": 0.001, "completion_tokens": 0.004}          # USD per 1K tokens: a run costs cents, like the real seats
    path = os.path.join(workdir, "LLM_CONFIG_template.json")
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(src, fh, indent=2)
    return path


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=5001)
    ap.add_argument("--orchestrator-port", type=int, default=5056)
    ap.add_argument("--workdir", default=os.path.join("/tmp", "bamboo_stack", "webapp"))
    ap.add_argument("--scenario", default="field_trial")
    ap.add_argument("--fresh", action="store_true", help="wipe the working directory first (config, storage, memory)")
    ap.add_argument("--compute", choices=("orchestrator", "direct", "local"), default="orchestrator")
    ap.add_argument("--executor-port", type=int, default=5055)
    ap.add_argument("--edition", choices=("hosted", "local"), default="hosted",
                    help="hosted: Auth0 and Supabase stand-ins as on the box; local: the self-hosted edition for real - "
                         "AUTH_MODE=single, no Supabase, no Auth0 (docs/OSS_DESIGN.md)")
    a = ap.parse_args()

    if a.fresh and os.path.isdir(a.workdir):
        shutil.rmtree(a.workdir)
    os.makedirs(a.workdir, exist_ok=True)
    local_template(a.workdir)
    os.chdir(a.workdir)

    os.environ.update({
        "AUTH_MODE": "auth0" if a.edition == "hosted" else "single", "AUTH0_DOMAIN": "local.test", "AUTH0_CLIENT_ID": "local", "AUTH0_API_AUDIENCE": "local",
        "BAMBOO_USER": "local", "BAMBOO_LEVEL": "performance",
        "FLASK_SECRET": "local-stack-secret",
        "EXECUTION_MODE": "local" if a.compute == "local" else "api", "BAMBOO_MEMORY_DIR": os.path.join(a.workdir, "memory"),
        "SYNTHESIS_INFOGRAPHIC": os.environ.get("SYNTHESIS_INFOGRAPHIC", "false"),
        "STREAM_HEARTBEAT_SECONDS": "5",
    })
    for k in ("STRIPE_SECRET_KEY", "OPENROUTER_API_KEY", "ORCHESTRATOR_API_URL", "EXECUTOR_API_BASE_URL"):
        os.environ.pop(k, None)
    if a.compute == "orchestrator":
        os.environ["ORCHESTRATOR_API_URL"] = f"http://127.0.0.1:{a.orchestrator_port}"
    elif a.compute == "direct":
        os.environ["EXECUTOR_API_BASE_URL"] = f"http://127.0.0.1:{a.executor_port}"     # one executor, as a docker run would be
    sys.path[:0] = [ROOT, os.path.join(ROOT, "delve"), os.path.join(ROOT, "web_app"), HERE]
    import sandbox
    faked = sandbox.install()                 # only packages that are not installed; nothing on a full venv
    if a.edition == "hosted":
        # the Supabase stand-in (tools/stack/fake_supabase.py): the app's own client code builds it from these
        os.environ.update({"SUPABASE_URL": "http://supabase.local", "SUPABASE_KEY": "local", "SUPABASE_SERVICE_ROLE_KEY": "local",
                           "LLM_CONFIG_ENCRYPTION_KEY": "local-stack"})
        import fake_supabase
        sys.modules["supabase"] = fake_supabase
    else:
        # the local edition: nothing stands in for Supabase; the app's own local answers are what is tested.
        # STACK_STRAY_SUPABASE=1 leaves hosted-looking keys IN the environment (a .env lying next to the app,
        # as found on the dev box on 2026-09-14): single mode must still never call out.
        if os.environ.get("STACK_STRAY_SUPABASE") == "1":
            os.environ.update({"SUPABASE_URL": "http://supabase.stray", "SUPABASE_KEY": "stray", "SUPABASE_SERVICE_ROLE_KEY": "stray"})
            import fake_supabase
            fake_supabase.RPC.clear()                          # any call would now fail loudly, as it did on the box
            sys.modules["supabase"] = fake_supabase
        else:
            for k in ("SUPABASE_URL", "SUPABASE_KEY", "SUPABASE_SERVICE_ROLE_KEY"):
                os.environ.pop(k, None)
        os.environ["LLM_CONFIG_ENCRYPTION_KEY"] = "local-stack"

    # the SweatStack SDK: the index route iterates ss.Metric, which the generic stub cannot do
    import enum
    import types
    ss = types.ModuleType("sweatstack")
    ss.Metric = enum.Enum("Metric", {n: n for n in ("power", "speed", "heart_rate", "cadence", "duration", "lactate", "rpe", "notes")})
    ss.Sport = enum.Enum("Sport", {n: n for n in ("cycling", "running")})          # string-valued, as the SDK's enums are
    ss.Client = lambda *a, **k: None
    sys.modules["sweatstack"] = ss

    # the scripted analyst, under an existing provider name (the dispatch table is fixed)
    import harness_models
    scenario = harness_models.load(a.scenario)
    sys.modules["bambooai.models.vllm_models"] = harness_models

    # the Auth0 check, for the browser stand-in's fixed token (hosted edition only; single mode needs none)
    import auth.auth_handler as ah
    if a.edition == "hosted":
        def validate(token):
            if token != TOKEN:
                raise ValueError("not the local stack's token")
            return {"sub": USER_SUB, "email": "local@stack", "name": "Local Stack"}
        ah.validate_auth0_token = validate
        ah.ensure_user_exists = lambda payload: None

    # the web-search seam
    import bambooai.google_search as gs
    digest = getattr(scenario, "SEARCH_DIGEST", "Sourced claims:\n1. (no claims in this scenario)\nSummary: nothing found.")
    links = getattr(scenario, "SEARCH_LINKS", [])

    def fake_search(self, prompt_manager, log_and_call_manager, output_manager, chain_id, messages):
        return digest, list(links)
    gs.SmartSearchOrchestrator.__call__ = fake_search
    gs.SmartSearchOrchestrator.perform_query = fake_search

    import app as webapp                                     # the real web_app/app.py
    from werkzeug.serving import make_server
    print(f"[webapp] real app ({a.edition} edition, compute {a.compute}); scenario {a.scenario}; workdir {a.workdir}; orchestrator {os.environ.get('ORCHESTRATOR_API_URL')}; "
          f"port {a.port}; faked packages: {faked or 'none'}", flush=True)
    make_server("127.0.0.1", a.port, webapp.app, threaded=True).serve_forever()


if __name__ == "__main__":
    main()
