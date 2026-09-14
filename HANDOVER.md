# State on 2026-09-14 (read this first; the sections below are the 2026-09-05 handover of the engine)

- **The box is at v72** (git `237d856` on the private repo). Packages v62-v72 since the seed of 2026-09-09:
  v62 the workspace gate (the pill from first paint until the executor is Ready; login starts the workspace);
  v63 one start-up instead of two (the workspace starts before the modules initialise; no `?new=true` reload;
  `[workspace]`/`[gate]` console logging); v64 the Reviewer seat (Adaptive's self-review turns on a stronger
  model; `analyst_review_every`); v65 the contract's competing-analyses sentence restored, the prompt button
  shows the clicked call, the map stays closed after Adaptive, `deepseek/deepseek-v4.1-flash`; v66 effort words
  for the flash model (a declared `none` stays `none`); v67 figures as a nudge; grok-4.6 and Sol on effort words
  with headroom; v68 the account dialog's tier text (general, no model names), the pill hidden on a signed-out
  load; v69 the forced-report prompt sees every cell whole, `SHOW 8 9`; v70 tabs respond while another chain
  runs; v71 the Rewriter seat (the plain-language rewrite on the flash model at low); v72 the current schema.
- **Delivery is git from here** (docs/OSS_DESIGN.md D15-D17): one repository tree, private remote
  `BambooAI_Prod` (the box's origin) and public `BambooAI` (same commits, pushed at release points); a
  change arrives as a patch series applied once on the box (`git am`, battery, restart, commit, push).
  The package engine (`tools/deploy/`) is retired and stays on the box untracked, with `docs/history/` and
  `web_app/db_schema.sql`.
- **The local stack** (`tools/stack/`, README there) runs the real app, executor and page here with Auth0,
  Supabase, the orchestrator and the CDNs faked; `tests/e2e/test_stack.py` (30 checks) and
  `tools/stack/flows.py` (the start-up flows) are the rehearsal for every change, next to `run_battery.sh`.
  Battery at v72: 66, 45, 1, 1, 20, 7, 29, 56.
- **The open-source edition**: design and decisions in `docs/OSS_DESIGN.md` (v0.3): the self-hosted
  edition, single user by default, same code selected by `.env`, SQLite for the nine work tables, pip
  install, 2.0.0 on the public repo over v1. Phases 0 (this snapshot) to 6; phase 1 (`AUTH_MODE=single`) is
  next, with phase 2 (`EXECUTION_MODE=local` from the web app) right after.
- **Known and parked** (from the 2026-09-09 review, not yet acted on): the orchestrator's health check
  returns a tuple three call sites test for truth; a single missed probe destroys the container; a failed
  tier lookup answers 'free'. The box runs one gunicorn worker, so the per-process state is not a live hazard.

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
