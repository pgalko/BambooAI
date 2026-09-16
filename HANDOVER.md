# State on 2026-09-16 (read this first; the sections below are the 2026-09-05 handover of the engine)

- **Where the code lives.** One repository, two remotes: `BambooAI_Prod` (private; `origin` everywhere)
  and `BambooAI` (public, pushed last). The Mac clone `/Users/palogalko/Projects/Bamboo_AI_v2`, the dev
  box and prod at `/home/data/bambooai` all run the same `main`: the snapshot `f28de59` plus 31 commits
  (the phase series 0001-0031). Delivery is a patch series applied once with `git am --keep-cr` (five
  files are CRLF), tested, pushed to the private remote, pulled elsewhere. The field order (D23): dev
  box first for anything the hosted edition runs, prod, push private, the Mac's `bambooai serve`, the
  public push last. Hosted-only or self-hosted-only changes may be applied where they matter first.
- **The open-source edition** (docs/OSS_DESIGN.md, v1.1, 39 decisions): phases 0-4 done and verified
  on the Mac, phase 5 built. `AUTH_MODE=single` (the identity `BAMBOO_USER`, no Auth0, Supabase never
  touched); `bambooai/db/local_store.py`, SQLite behind Supabase's query shape, handed out by the two
  client factories (labels, chains, usage, the saved level, the integrations' keys); the compute is the
  executor container built from the Dockerfile the package ships and managed by `bambooai serve` (D27,
  reversed from subprocess-by-default once the integrations showed why), `--compute local` the fallback;
  `pyproject.toml`, the `bambooai` command, `~/bambooai` as the working folder. Nothing hosted moved: the
  self-hosted paths are `cli.py`, `local_store.py`, single-mode branches, and env-driven defaults.
- **Phase 5 as built, awaiting the ruling to publish:** `.github/workflows/ci.yml` (battery, the story in
  three compute modes, the store's persistence, the package, the flows, the executor image),
  `release.yml` (PyPI on a `v*` tag via trusted publisher - to register on pypi.org), `LICENSE` (MIT), the
  2.0 README with a gallery screenshot. The public push procedure is in the design document under phase 5.
- **The tests.** `run_battery.sh` (66/45/1/1/20/7/29/56); `tests/e2e/test_stack.py [--edition local]
  [--compute local|direct]` (32 checks, the story on the real app with the stack's stand-ins);
  `tests/e2e/test_local_store.py` (16, a restart of the server); `tests/e2e/test_package.py` (34, the wheel
  in a fresh virtualenv, `serve` with a docker stand-in); `tools/stack/flows.py` (start-up flows);
  `tools/render_gallery.py --compare` (the page states; the reference moved on 2026-09-16 for the gear
  menu and the dialog title).
- **What the Mac taught** (each now a commit): `pkg_resources` absent from new virtualenvs; `/home` not
  creatable on macOS (logger_config, the executor client's log file); gunicorn's fork dies on macOS (werkzeug
  there, the app built in the worker on Linux); a werkzeug FileStorage handed to requests; a `docker stop`
  cut short by a second Ctrl-C leaves a dying container the next serve must not reuse.
- **Next:** the public push and the 2.0.0 tag when you say so; O5 team mode (a users table exists in the
  store); the padlock icon on 'Models & Compute' if wanted. Parked from 2026-09-09: the orchestrator's
  health check returns a tuple three call sites test for truth; a single missed probe destroys a container;
  a failed tier lookup answers 'free'.

# BambooAI — handover (redesign of 2026-09-05)

One analyst, one kernel, one notebook, one report. The design checklist that every change
must pass is `docs/DESIGN_CHECKLIST.md`; the inventory of what was removed and why is
`docs/REMOVE_MODIFY_INVENTORY.md`; the full history of the previous design is `docs/history/`.

## The shape

- `analyst/` — the whole harness (~1,000 lines): `contract.md` (the only prompt, one page),
  `session.py` (the turn loop, budget, self-review, report + rewrite + guards + replay),
  `notebook.py` (a tree of runs and turns per thread; collapse; JSON persistence),
  `tools.py` (run a cell, show a cell, names, recall, search, ask), `report.py` (the two
  numeric guards, cell/figure references, table repair), `replay.py` (assemble the cited cells
  into one script; rehydrate a path; verify in a fresh kernel), `llm_openrouter.py` + `cli.py`
  (a headless runner for development).
- `bambooai/bambooai.py` (~440 lines) — the instance the web app holds: builds the kernel
  (RemoteKernel in `api` mode, PersistentKernel locally), the model call through the app's model
  layer, the memory and search tools, runs a Session per question, streams artifacts to the
  browser in its existing event vocabulary, stores the notebook under
  `storage/<user>/threads/<thread>.json`, stages memory sources, distills on keep.
- `bambooai/kernel_client.py` — RemoteKernel (the executor's /kernel API). `delve/kernel.py` and
  `containers/executor/kernel.py` — the persistent kernel (no toolkit preload).
- `bambooai/messages/default_prompts.yaml` — survivors only: the infographic extractor, the
  memory distiller, the ideas-explorer question, the web-search seam.
- `web_app/LLM_CONFIG_template.json` — per tier: one `Analyst` seat + Knowledge Distiller,
  Image Generator, Google Search Executor/Summarizer; tier properties carry the analyst's turn
  budgets (`analyst_turns_quick/deep/adaptive`). An existing user config without an `Analyst`
  seat falls back to its `Investigator` seat.

## Modes (see HANDOVER_2026-09-09_session_seed.md for the current presets: Quick 5 / Deep 15 / Adaptive 50)

Quick / Deep / Adaptive are budget presets of the one session: ~2 / 15 / 50 turns (the UI's
planning dial maps to adaptive; `max_investigations` × 4 turns). The adaptive preset asks the
analyst for a self-review every 8 turns.

## Behaviour to know

- A follow-up standing on the kernel's current tip reuses the warm kernel; a branch or a new
  thread gets a fresh kernel rehydrated from the parent's path (the same mechanism replays the
  assembled script at the end of every run).
- ASK ends the run with the question as the answer; the person's reply is the next run.
- Thread files from the previous design are read tolerantly (their keys are preserved; the
  notebook tree is added beside them). Favourites, previews, replays and the workflow map are
  browser-saved snapshots and are unaffected.
- The executor image no longer copies `toolkit.py`; rebuild it when convenient.

## Tests

`./run_battery.sh` — `tests/analyst/test_analyst.py` (20 checks) and
`tests/analyst/test_app_path.py` (12 checks), both over a real in-process kernel.
