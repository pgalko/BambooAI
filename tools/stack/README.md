# The local stack — the real app on one machine, the outside world faked

Run BambooAI end to end without the dev box: the real web app, the real executor and the real
page in a real browser, with a scripted analyst instead of a model provider and stand-ins for
Auth0, Supabase, the orchestrator/Nomad and the CDNs. See a change on the real page before it
ships; drive the whole path from a test.

    python3 tools/stack/stack.py up [--pause 2]        # start; prints the URLs
    python3 tools/stack/browse.py --out /tmp/shots --attach     # walk the story, screenshot every state
    python3 tools/stack/stack.py down                  # stop
    python3 tests/e2e/test_stack.py                    # the walk as assertions (22 checks, ~2 min)

On the dev box the app runs at http://127.0.0.1:5001 next to the real service (different port,
its own working directory, nothing shared). Open it in a browser: the fake sign-in completes on
its own; upload `/tmp/bamboo_stack/data/field_trial.csv` (the pill, from the paperclip) and ask
the scenario's questions. `--pause 2` makes the scripted analyst "think" two seconds per turn so
a run can be watched arriving.

## What is real, what is not

| Part | In the stack |
|---|---|
| `web_app/app.py`, every route, blueprint, template, stylesheet and script | **real**, served by werkzeug (threaded) from a scratch working directory |
| `bambooai/bambooai.py`, `analyst/`, the model layer, log manager, cost accounting | **real** |
| `containers/executor/code_executor_api.py`, the kernel service, `PersistentKernel` | **real**, as a local process (not Docker); `read_csv(engine='pyarrow')` falls back when pyarrow is absent |
| the model provider | `harness_models.py`: a **scripted analyst** registered as `bambooai.models.vllm_models` (an existing, unused provider name — the dispatch table is fixed); it streams through the real output manager and answers from the real prompt |
| the orchestrator / Nomad | `fake_orchestrator.py`: the same HTTP surface, one local executor for everyone, "ready" decided by the real `/health`, every call recorded at `/_harness/calls` |
| Auth0 | browser: `browser/auth0_stub.js` (always signed in as `auth0|localuser`); server: `validate_auth0_token` accepts the token `local-token` |
| Supabase | `fake_supabase.py`: an in-memory store behind the app's own client code, seeded with one free-tier user; unknown RPCs answer `{}` |
| web search | the scenario's canned digest and sources, through `SmartSearchOrchestrator` |
| the CDN libraries | `browser/vendor.py`: real copies first (`browser/vendor/`, filled from copies on the machine and downloaded when there is network), stand-ins otherwise; the Auth0 SDK is always the stand-in |
| Stripe, SweatStack, Intervals, Endura | unconfigured / a minimal stand-in; their dialogs open, nothing connects |

Missing third-party packages are faked **selectively** (`sandbox.py`: only what `importlib` cannot
find) — on the box's venv nothing is faked, and the executor uses the real pyarrow and plotly.

## The scenario

`scenarios/field_trial.py`: a 120-plot × 6-season fertiliser trial with three regimes and a soil
imbalance (regime B sits on more loam). The story for the first question, in Deep: inspect →
one search (two sources) → a cell that fails on a wrong column and is rolled back → the
soil-adjusted comparison with a plot-level bootstrap → a figure → the report. A follow-up
("and regime C?") reuses the warm kernel in two turns. Explore returns five questions; Save at 7
births a candidate memory card through the real distiller parser. Any other question gets a
short generic answer, so the app can be driven by hand.

Every number in the scripted report is read from the real cell outputs in the prompt, so the two
numeric guards, the replay comparison and the cost accounting all run for real. A scenario is a
module with `DATASET_NAME`, `QUESTIONS`, `make_dataset(path)` and a `Scenario.reply(system, user)
-> (thinking, text)`; a new one goes in `scenarios/` and is chosen with `--scenario`.

## Layout of a running stack (`--workdir`, default `/tmp/bamboo_stack`)

    executor/      the executor's datasets/, temp/, iframe_figures/
    webapp/        LLM_CONFIG_template.json (every seat on the scripted provider; the tier budgets untouched),
                   config/<user>/LLM_CONFIG.json, storage/<user>/{threads,favourites}/, memory/<user>/memory_pack.yaml, logs/
    data/          the scenario's dataset
    logs/          executor.log, orchestrator.log, webapp.log
    stack.json     ports and pids of a detached stack

`browse.py` writes the screenshots, `console.txt` (page errors, console errors, every 4xx/5xx
response), `orchestrator_calls.json` and the three logs into `--out`. A page error makes it exit 1.

## Knobs

- `--auto-ports` (any free ports), `--fresh` (wipe the working directory), `--scenario NAME`.
- `STACK_TURN_PAUSE` / `--pause`: seconds the analyst pauses before each turn. `STACK_STREAM_DELAY`:
  seconds per streamed chunk (default 0.012).
- `SYNTHESIS_INFOGRAPHIC=true` before `up` to exercise the infographic path on a synthesis.
- `browse.py --light` renders each state in both themes; `--js "..." --name x` screenshots one state.

## Adding it to the battery

`run_battery.sh` can run the suite unconditionally — it skips itself with one line when
playwright is missing:

    echo "##### SUITE tests/e2e/test_stack.py"; timeout 900 python3 tests/e2e/test_stack.py || rc=1

## Limits

- Nomad, tiers, capacity and the orchestrator's health/tier rules are not exercised: the fake
  answers "ready" whenever the executor is healthy. The next step for the reliability work is
  the real `ContainerManager` behind the same surface, over a fake Nomad, with the destroy log.
- Without network, dagre, localforage, mermaid, Plotly and CodeMirror are stand-ins (the map's
  layout is a placeholder; Plotly JSON figures render empty — the stack's figures are PNG).
  After one run on a machine with internet, `browser/vendor/` holds the real ones.
- One worker process, so the multi-worker question (`GUNICORN_WORKERS`) is not reproduced here.
- The scripted analyst is deterministic and cheap; it is for the interface and the plumbing, not
  for judging analysis quality.
