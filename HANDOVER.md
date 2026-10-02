# State on 2026-10-03 (read this first; the sections below are the 2026-09-05 handover of the engine)

- **Where the code lives.** One repository, two remotes: `BambooAI_Prod` (private; `origin` everywhere)
  and `BambooAI` (public). The Mac clone `/Users/palogalko/Projects/Bamboo_AI_v2`, the dev box and prod
  at `/home/data/bambooai` all run the same `main`: the snapshot `f28de59` plus the patch series
  0001-0050 (phases 0-5 of the open-source edition, then Ollama 0038-0045 and vLLM 0046-0050).
  Delivery is a patch series applied with `git am --keep-cr` (27 tracked text files are CRLF, among
  them every `bambooai/models/*.py`), tested, pushed to the private remote, pulled on the boxes, pushed
  to the public remote last. Order: dev box first for anything the hosted edition runs; the Mac first
  for self-hosted work. A release is a version bump in `pyproject.toml` within the series, then a `v*`
  tag pushed to the public remote (`release.yml`, trusted publisher, scoped to `pgalko/BambooAI`).
- **Published.** The public repository carries 2.0 since 2026-09-16 (1.x kept as the `v1` branch and the
  `v1-final` tag). PyPI: 2.0.0 (2026-09-17), 2.0.1 (the Ollama work), 2.0.2 (the vLLM work, 2026-10-02).
  CI (`ci.yml`) runs the unit battery and the executor image build; the browser suites and the package
  test run locally before a push, by decision (three runner-environment failures taught that).
- **The open-source edition** (docs/OSS_DESIGN.md): `AUTH_MODE=single` with the identity `BAMBOO_USER`;
  `bambooai/db/local_store.py` (SQLite behind Supabase's query shape); the executor container built from
  the Dockerfile the package ships and managed by `bambooai serve` (`--compute local` the fallback);
  `~/bambooai` the working folder. Configuration is a trio: the master `web_app/LLM_CONFIG_template.json`
  (ships with the package), the person's copy `~/bambooai/LLM_CONFIG_template.json` (four tiers of seats
  and `model_properties`), and the built `config/<user>/LLM_CONFIG.json` (one tier flattened), rebuilt when
  the template is newer or the level is saved in the dialog.
- **Local models.** `bambooai/models/ollama_models.py` on the daemon's native API: `num_ctx` from
  `model_properties.context_window` with a truncation report otherwise, `think` from the seat's effort
  (off / a level name / on, only for models whose /api/show lists thinking), the thinking channel to the
  pane, an unbounded first-token wait with an idle deadline, `keep_alive`, `OLLAMA_API_KEY` for
  ollama.com, the daemon's errors explained and the transient ones retried. `bambooai/models/vllm_models.py`
  on an OpenAI-compatible server: `delta.reasoning`/`reasoning_content` to the pane, `reasoning_effort` by
  the model's level names (Qwen3.8: low/medium/xhigh; a tie between neighbours folds upward), thinking off
  via `chat_template_kwargs`, exact usage from the stream, a context pre-flight against `context_window`
  (vLLM refuses rather than truncates), the OpenRouter adapter's `_tail_guarded` and `_reasoning_delta_text`
  reused. The dispatcher hands adapters their `model_properties` entry through `set_model_properties`.
  Test beds: the Windows GPU machine (RTX A6000) at 192.168.1.201 - Ollama on Windows (11434), vLLM 0.30
  under WSL2 in mirrored networking (8000) serving Qwen3.8-27B in FP8 with Marlin kernels, CUDA graphs
  without `torch.compile`, MTP speculation (~40 tokens/s); the runbook is `vLLM_on_WSL.md` in the
  2026-10-02 outputs folder.
- **The tests.** `run_battery.sh` (66/45/29/19/1/1 Python; 20/7/29/56 JS); `tests/e2e/test_stack.py
  [--edition local] [--compute local|direct]` (32); `tests/e2e/test_local_store.py` (16);
  `tests/e2e/test_package.py` (34); `tools/stack/flows.py`; `tools/render_gallery.py --compare`.
- **Decided not to do, for now:** PRs #61 (LiteLLM SDK as a provider: heavy dependency, duplicated
  capability) and #62 (Requesty: good work, but a copy of the OpenRouter adapter that would drift). The
  right unit, when wanted, is one generic OpenAI-compatible gateway provider with a table of gateways.
- **Next candidates:** `repeat_penalty: 1.0` in the Ollama adapter's options (Ollama's Modelfile default
  of 1.1 hurts code and structured output); the CI badge back in the README (the public workflow exists
  now); O5 team mode (a users table exists in the store); O9 integrations on the local kernel. Parked
  from 2026-09-09: the orchestrator's health check returns a tuple three call sites test for truth; a
  single missed probe destroys a container; a failed tier lookup answers 'free'.

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
