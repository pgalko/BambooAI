# BambooAI 2 — the open-source edition: design and decisions

Living document. v1.5, 2026-10-03 (v0.1-v0.7 on 2026-09-14; v0.8-v1.0 on 2026-09-15; v1.1 on 2026-09-16; v1.2-v1.4 on 2026-10-03). Kept in the repository at `docs/OSS_DESIGN.md`; updated as the
design is refined. Decisions are numbered so later notes can refer to them. Each carries a one-line
reason; the reasoning behind the reasons is in the session notes.

## 1. What is being open-sourced

- **D1. The self-hosted edition, not the hosted stack.** Single user by default; a small team on
  their own server as an option. The hosted service — public sign-in, tiers, funds, quotas,
  container scheduling for strangers — stays proprietary. *Reason:* the multi-user machinery is
  infrastructure for strangers; a team on its own server needs none of it, and it is the part with
  the operational burden and the commercial mechanics.
- **D2. The same code, selected by configuration.** The cloud modules (Auth0, Supabase, Stripe,
  the orchestrator) remain in the repository and are dormant without their environment; the
  self-hosted install never configures them. *Reason:* one tree cannot drift; the app already
  degrades to the free tier when Supabase is absent, and the local stack has run without Auth0,
  Supabase and Nomad since 2026-09-09.
- **D3. What the user gets:** the analyst engine, the notebook, the memory pack, the web app, the
  executor image, the local adapters, the tests and the stack. What they do not get: your `.env`
  files (outside the tree in `/etc/bambooai`) and the Supabase schema (D14).

## 2. The five seams

The self-hosted edition differs from the hosted one at five places. Everything else is shared.

- **D4. Identity.** `AUTH_MODE` gains a single-user mode: a fixed local identity, no Auth0 SDK,
  no sign-in stage in the workspace gate. Team mode (later): a local users table and a login page.
  Today `AUTH_MODE=none` exists but `requires_auth` still demands a token — first piece of work.
- **D5. Compute.** `EXECUTION_MODE=local` becomes reachable from the web app: the same
  `PersistentKernel` in a subprocess on the user's machine, no orchestrator. Docker stays as an
  option — a plain `docker run` of the existing executor image — for people who want isolation.
  Today `get_bamboo_ai` always asks the orchestrator — second piece of work.
- **D6. Accounts and data.** `auth/supabase_client.py` keeps its function names; when Supabase is
  absent its client factories hand out a SQLite client that speaks the same query shape
  (`bambooai/db/local_store.py`), so nothing above them changes. Details in §3.
- **D7. The settings dialog.** Models and Compute tabs stay; Funds and Integrations show only what
  the edition has. **Model keys come from `.env`, not from the dialog:** the key-entry UI (the
  hosted "own keys" path) is hidden in the self-hosted edition. *Reason:* the model layer already
  reads provider keys from the environment; a second way in adds complexity for no gain.
- **D8. Serving.** One process on localhost (`bambooai serve`); no nginx, no gunicorn, no
  Nomad/Consul. The box runs one gunicorn worker already (`GUNICORN_WORKERS=1`), so the per-process
  state is not a concern in either edition.

The environment file confirms the split: of the ~45 variables on the box, about thirty are hosted-only,
four are edition switches (`EXECUTION_MODE`, `AUTH_MODE`, `WEB_SEARCH_MODE`, `APP_PORT`), and the rest
are the user's own keys or generated secrets. No `BAMBOO_EDITION` variable is needed: the absence of the
hosted variables selects the local adapters.

## 3. The database

From the dev schema dump of 2026-09-13 (16 tables, 34 functions, 11 triggers, 49 policies), checked
statement by statement against the code.

- **D9. Nine tables become SQLite tables with the same columns:** `threads`, `chains`, `labels`,
  `dataset_metadata`, `usage` (with `compute_tier`, `query_cost`, `charges_processed` fixed at zero),
  `llm_config`, `sweatstack_integration`, `intervals_integration`, `endura_integration`.
- **D10. Seven tables stay hosted-only:** `users`, `user_subscription`, `tier_limits`, `user_funds`,
  `usage_counters`, `transactions`, `grounding_search_quotas` — with every procedure, the usage
  billing trigger and the row-level-security policies. Locally, the billing functions answer as the
  code already handles today: allowed, no charge, no tier.
- **D11. No triggers or procedures locally.** `insert_usage_with_chain` and
  `delete_label_and_get_chains` become three plain statements each in Python; the SweatStack
  `expires_at` arithmetic moves to Python. Row-level security is not needed: the app talks through
  the service role today and scopes every query by `bamboo_user_id` in code — which is why the same
  functions work unchanged over SQLite, single user or team.
- **D12. The Usage dialog needs nothing new captured.** The log manager already writes every model
  call's tokens, time and cost both to the `usage` table and to the run log; the dashboard's
  aggregation runs unchanged over the local table. "Total Compute Cost" becomes zero or is hidden.
- **D13. The three integration tables carry an `auth0_id` column.** Locally it holds the local user
  id or stays empty — the one place the identity seam reaches the data.
- **D14. The schema file stays on the box, untracked.** `web_app/db_schema.sql` (the dump shipped in
  v72) is added to `.gitignore` and removed from tracking (`git rm --cached`); neither remote
  receives it from then on. The SQLite schema for the open-source edition is generated from it once
  and is public.

## 4. Repositories, history and delivery

- **D15. One repository tree, two remotes.** `BambooAI_Prod` (private) is the box's origin and holds
  unreleased work; `BambooAI` (public) receives the same commits when pushed, at the maintainer's
  chosen delay. No separate "ops" repository: the secrets already live outside the tree, and the
  files inside it (`nomad/`, `install.sh`, `scripts/`) name paths and resources, not secrets.
- **D16. The public history starts from a clean snapshot.** One initial commit of the tree as it
  stands, scanned for secrets, without the schema. The private `main` is reset to the same snapshot
  with the old history kept on `history-pre-oss` (private only). From that commit on, both remotes
  carry identical commits. *Reason:* pushing the private history publishes every past commit.
- **D17. Delivery is a git patch series, applied once, on the box.** `git am --keep-cr` (26 tracked
  text files are CRLF, every `bambooai/models/*.py` among them; without the flag a patch touching
  them does not apply), the battery, restart, commit, push to the private remote. The Mac clone
  pulls from the private remote and pushes to the public one; it never applies the series a second
  time. Template edits on the box are commits by the maintainer, not local drift. The deploy-package
  engine (md5s, anchors, transforms) retires once the repository is the source of truth.
- **D18. The first push over v1.** Tag and branch the old `main` (`v1-final`, `v1`) so v1 stays
  reachable; publish v2 as **2.0.0** on PyPI under the same name. The README (ruled 2026-09-16) is
  written for 2.0 - logo, a screenshot, plain text - with a short note at the bottom that 1.x was a
  different program, still installable as `bambooai<2` and on the `v1` branch. The importable engine
  remains; the terminal runner `analyst/cli.py` was removed on 2026-10-04 as a second model stack. The public push is the last step of the cycle, after
  the dev box, prod and the Mac have run the same commit.
- **D30. The working places.** The box: `/home/data/bambooai`, origin `BambooAI_Prod`. The Mac:
  `/Users/palogalko/Projects/Bamboo_AI_v2`, a clone of `BambooAI_Prod` with `public` as the second
  remote — deliberately outside Dropbox, which corrupts live `.git` folders when it syncs them.
  Phase 0 steps 1-4 (the snapshot on the box and the private remote, the Mac clone) are being
  deployed on 2026-09-14; step 5 (the public push) waits.

## 5. Install and release

- **D19. `pip install bambooai` (or `uvx bambooai`) and one command.** `bambooai serve` creates the
  working folder `~/bambooai`, writes `.env` with generated secrets and the edition's settings and a
  copy of the template, starts one process on localhost and opens the browser; `bambooai init` does
  the folder alone. Keys go in that `.env` (D7). A Docker image built from the same repo is
  the second, equal door. The page's CDN libraries stay on the CDN (vendoring, as the stack does, is
  optional).
- **D20. On-prem models are a headline, not a footnote.** The vLLM and Ollama providers already
  exist; a team can run with nothing leaving the server.
- **D21. Releases by tag.** A tag on the public repo triggers the PyPI build in CI.

## 6. Testing

- **D22. Both editions in every run.** The battery and the stack's end-to-end suite run in local
  mode (the open-source default) and in api mode with the fake orchestrator. CI on GitHub Actions
  (`.github/workflows/ci.yml`) runs the battery and the executor image build, nothing else (ruled
  2026-09-16, after three runs failed on differences between a fresh runner and the machines the
  suites were written on); the browser suites and the package test run locally before every push.
  The stack is the rehearsal rig for both editions and ships with the repository.

## 7. Working method

- **D23. Proprietary first, by construction.** Every change is developed once in the shared tree and
  tested on the stack in both editions. The order in the field (settled 2026-09-15): the series is
  applied on the **dev box** first and tested there (it exists only as local commits until it passes;
  `git reset --hard origin/main` discards it), then prod pulls, then the push to the private remote,
  then the Mac pulls and the self-hosted edition is tested with `bambooai serve`, and the public push
  comes last. `git am --keep-cr` wherever a series is applied; commit where you edit, push before you
  pull elsewhere. There is no step in which the open-source version is edited by hand.
- **D24. Sessions start from a clone and a handover.** Each session begins from the repository (a
  bundle or clone) and the current handover, and ends with a patch series and an updated handover.
  The design document is updated in the same series that changes a decision.

## 8. Decisions settled on 2026-09-14

- **D25. Licence: MIT stays**, as the public repository carries it.
- **D26. SweatStack: bare machinery, the user's own registration.** The integration ships as code;
  the user registers their own app with SweatStack and puts its client id and secret in `.env`.
- **D27. Docker is the default compute; the subprocess kernel is the fallback** (ruled 2026-09-15,
  reversing the 2026-09-14 ruling once the integrations showed why). `bambooai serve` builds the
  executor image from the Dockerfile the package ships - the hosted service's own image - on first
  use, starts or reuses one container published on localhost, waits for its health, points the app
  at it (`EXECUTION_MODE=api`, `EXECUTOR_API_BASE_URL`) and stops it on exit. One compute model in
  both editions: the executor is the only place model-written code runs, and every executor feature -
  the integrations included - works in the self-hosted edition the day it lands. `--compute local`
  (or `BAMBOO_COMPUTE=local`) keeps the kernel-in-a-subprocess path for a machine without Docker,
  documented as no isolation and no integrations. No image is published; nothing in the hosted
  code moves - the work is `bambooai/cli.py`, the package data and the README.
- **D28. Web search is off unless `GEMINI_API_KEY` is set;** with the key, `google_ai` as today.
  The Selenium mode and `SELENIUM_WEBDRIVER_PATH` are dead and go.

## 8a. Still open

- **O9 - closed by D27.** Intervals, Endura and SweatStack fetch their data inside the executor
  container; with Docker the default compute they work in the self-hosted edition as they do in the
  hosted one. On the `--compute local` fallback they answer "needs an executor", which is now a
  stated property of the fallback rather than a gap.

- **O5. Team mode scope** (login, users table, per-user kernels): phase 6, after single-user ships.
- **O6. The template's prices.** `model_properties` ships with the release; self-hosted users own
  their price lines as the maintainer does. Zero for on-prem models is correct.
- **O7. What of the hosted edition's UI text remains visible** (tier names, "Pay as you go") when
  no tiers exist locally. Proposal: the three levels stay as presets of the template; the words
  about paying go.
- **D29. The local identity is `BAMBOO_USER=local` in `.env`** — a constant the user may change —
  used for `storage/<id>`, `memory/<id>` and `config/<id>` (settled 2026-09-14; was O8).

## 8b. Settled since (2026-09-16 to 2026-10-03)

- **D31. The Ollama adapter stays on the daemon's native API** (`/api/chat` through the `ollama`
  client), not on the OpenAI-compatible endpoint (ruled 2026-10-01, checked against docs.ollama.com).
  *Reason:* only the native API takes `options.num_ctx` per request, and the context length has to be
  set per request: a local model's default context depends on the machine's VRAM and can be 4k, the
  daemon truncates a longer prompt silently, and the analyst's prompt is 10-30k tokens with the
  contract at its start.
- **D32. Gateway providers are declined for now.** PR #61 (the LiteLLM SDK as a provider) and PR #62
  (a Requesty adapter) were assessed and set aside (recorded in the handover of 2026-10-03): the
  first is a heavy dependency duplicating what the adapters already do, the second good work but a
  copy of the OpenRouter adapter that would drift from it. *Reason:* a lean code base. If gateways
  are wanted, the unit is one generic OpenAI-compatible provider with a table of gateways, not one
  adapter per gateway.
- **D33. Documents** (2026-10-03) are designed in `docs/DOCUMENTS_DESIGN.md`: up to four per thread,
  parsed into units with locators, objects in the kernel read with cells, one `READ` action served by a
  Reader seat with verbatim passages cited as `[D1.17]`; a `READ` is a turn like a `SEARCH`. A first build
  with free look-ups, a `LOOK` action and an embedding stack was removed the same day after real runs.

## 9. Scope, phase by phase

Each phase is one commit series applied on the box, rehearsed on the stack in both modes, and
leaves the hosted edition working unchanged. "Done" is the acceptance line, not the file list.

### Phase 0 — the snapshot (needs the `BambooAI_Prod` bundle)
- Scan the tree and, separately, the old history for anything key-shaped; report both.
- `web_app/db_schema.sql` into `.gitignore` and out of tracking (D14). `docs/OSS_DESIGN.md` in.
- A fresh initial commit of the tree ("BambooAI 2.0 - initial public snapshot"); the private
  `main` reset to it, the old history on `history-pre-oss`; the exact commands for the box, the
  Mac, and the `v1-final` tag / `v1` branch on the public repo (D16, D18).
- **Done when:** the box runs from the snapshot with the battery green; both remotes show the
  same single commit; the scan is clean; v1 is reachable on GitHub.

### Phase 1 — identity: single-user mode (D4, D7)
- `AUTH_MODE=single`: `requires_auth` passes with the fixed local identity (O8) and no token;
  `/api/auth/status` says so; the browser skips the Auth0 SDK entirely and completes sign-in with
  the local user; the logout control is hidden; the workspace gate starts at "Preparing your
  workspace".
- The page must initialise without Supabase: the subscription check and the balance and usage
  routes answer a fixed local tier instead of 500 (today a Supabase outage blocks the page). This
  is the skeleton of the local accounts backend that phase 3 fills in.
- The settings dialog in single mode: levels as presets, no key entry, no Funds (D7, O7).
- Tests: the app-path suite for the auth mode; the stack gains `--edition local`, which runs the
  real app with `AUTH_MODE=single` and no Auth0 or Supabase stand-ins at all - from then on the
  stack tests the open-source edition for real, next to the hosted one.
- **Done when:** with only `AUTH_MODE=single`, `EXECUTION_MODE=api` and a model key in `.env`,
  the page loads, the gate runs workspace -> executor -> ready, and a question is answered.
- **Status 2026-09-14: done** (commits `fe35aef`, `2e2be56`, `2e33466`). Learned on the way: the
  Supabase and Stripe SDK imports had to become optional (the self-hosted edition does not
  install them - a packaging fact for phase 4); the dialog and the integration grid assumed the
  hosted tiers. The executor still comes through the orchestrator in this phase.

### Phase 2 — compute: the local kernel (D5, D27)
- `EXECUTION_MODE=local` reachable from the web app: `get_bamboo_ai` builds the instance without
  the orchestrator; upload loads the dataframe into the instance; the Data tab pages the local
  frame; the replay runs locally; the executor chip reads "Local" and is Ready at start.
- `EXECUTION_MODE=api` with `EXECUTOR_API_BASE_URL` set uses that executor directly - the Docker
  option, one `docker run` of the existing image, no orchestrator.
- Tests: the stack in local mode needs no executor process; the e2e story runs unchanged.
- **Done when:** the field-trial story completes end to end on the kernel in a subprocess, and
  again against a plain Docker executor.
- **Status 2026-09-14: done** (commits `5886a6a`, `e1d4cb1`, `ed2e046`). Learned on the way: the
  local reproduction run used `exec()` inside the web app's process (v1's design) - it now runs in a
  kernel subprocess; the plotly capture is optional there. Phase 1's dev-box test found that
  `webapp_gunicorn.conf.py` loads `/etc/bambooai/*.env` itself (so `bambooai serve` will not use
  it) and that the per-user folders belong to whoever runs the process - both for phase 4.

### Phase 3 — data: the SQLite backend (D6, D9-D13)
- `auth/supabase_client.py` becomes a facade over two backends selected by the presence of
  `SUPABASE_URL`: the current one, and SQLite in the working folder with the nine tables of D9
  (schema generated from the dump). The usage writer in `bambooai/db/` follows.
- The billing functions answer locally as in D10; the Usage dialog runs unchanged (D12).
- Tests: a unit suite for the SQLite backend; the local-edition e2e covers labels, favourites,
  the Usage dialog and an integration's configuration.
- **Done when:** a saved chain, its label and the Usage dialog survive a restart of the server.
- **Status 2026-09-14: done** (commits `6424c29`, `8c3da64`, `10af511`). The design changed for the
  better on the way: instead of a facade with two implementations of twenty functions, the local
  backend is a SQLite client that speaks Supabase's query-builder shape (`bambooai/db/local_store.py`),
  handed out by the two client factories - every function and route above them, including the label
  routes' inline queries and the usage dashboard, works unchanged. The store is one file,
  `bambooai.sqlite`, in `BAMBOO_DATA_DIR` or the working folder. The level saved from the dialog lives
  there (D7 amended: `BAMBOO_LEVEL` is the default before the first save, not the only source).

### Phase 4 — packaging (D19, D20)
- `pyproject.toml` (the package name `bambooai`, version 2.0.0, curated dependencies; the web app's
  templates and static files as package data), the `bambooai serve` command (working folder,
  default configs, generated secrets, browser), a Dockerfile for the app, the executor image as is.
- **Done when:** `pip install` from a clean virtualenv on a clean machine and `bambooai serve`
  reach the field-trial story with no other step.
- **Status 2026-09-15: built** (commit `ef2496c`); the clean-machine half of "done" is the Mac's
  to confirm (the sandbox has no network for dependencies). The working folder is `~/bambooai`
  (D30 amended: visible, not hidden; `BAMBOO_HOME` overrides; a code checkout is refused as the
  folder). The 1.x `setup.py` is retired.

### Phase 5 — CI and the release (D18, D21, D22)
- GitHub Actions: the battery and the stack's e2e in both modes on every push; the PyPI build on a
  tag. The README rewritten for 2.0 with the v1 note first.
- **Done when:** the public repo is green, `pip install bambooai==2.0.0` works, v1 is reachable.
- **Status 2026-09-16: built.** `.github/workflows/ci.yml` runs the battery and, in a second job,
  builds the executor image, on every push and pull request - nothing else: the first version also
  ran the story in all three compute modes, the persistence and package e2e and the start-up flows,
  and three runs each failed on a difference between a fresh runner and the machines the suites were
  written on (the stubs, the page's libraries, a Python without setuptools), so the browser suites
  and the package test run locally before every push (D22). `release.yml` publishes to PyPI on a `v*`
  tag through a trusted publisher (to be registered on pypi.org: owner `pgalko`, repository
  `BambooAI`, workflow `release.yml`, environment `pypi`). `LICENSE` (MIT) is in the tree; the README
  is the 2.0 one with a screenshot from the gallery. The public push procedure (the Mac, `public`
  remote): `git fetch public`, `git tag v1-final public/main`, `git branch v1 public/main`, `git push
  public v1-final v1`, remove any protection on the public `main`, `git push public main --force`,
  then `git tag v2.0.0 && git push public v2.0.0` when the release is wanted.
- **Status 2026-10-03: released.** The public repository carries 2.0 since 2026-09-16, with 1.x
  reachable as the `v1` branch and the `v1-final` tag; the trusted publisher is registered and PyPI
  has 2.0.0 (2026-09-17), 2.0.1 (the Ollama work) and 2.0.2 (2026-10-02, the vLLM adapter). Both jobs
  of `release.yml` run only when the repository is the public one (2026-10-01): the private remote
  receives every tag too, and its publish step used to fail against the publisher registered for
  `pgalko/BambooAI`. A release is a version bump in `pyproject.toml` within the series, then the tag.
- **Status 2026-10-06: 2.1.0.** Documents in the analysis (Phase 7), the analyst's contract as one page of
  Markdown, results recorded by the kernel (`RESULT(...)`), the reviewer with its evidence handed over in one call,
  a verification ledger and five perspectives, Quick and Deep without a reviewer, generated datasets (`DS.save`) in
  the Dataset cache, and the run's prompts read turn by turn and tidied - patches 0057-0096, executor build v51.
- **Status 2026-10-07: 2.1.1.** The configuration template tidied and repriced, OpenRouter's gpt-6.1-sol on the
  sol seats, and a pricing preflight that names any seat whose model has no price - patches 0097-0100. No kernel
  change: executor build v51 stands.
- **Status 2026-10-08: 2.2.2.** The Claude 5.5 family on the Anthropic adapter (effort, adaptive thinking with its
  summary in the card's reasoning fold, refusals named by category, temperature through extra_body), the contract's
  step section (`###STEP###`, for the person following the run - the THINKING section had tripped the 5.5 models'
  reasoning-extraction classifier), the forced report's card, the replay printing as the kernel prints, auxiliary
  files described in DATA, the template's Claude seats - patches 0101-0110. No kernel change: executor build v51
  stands.
- **Status 2026-10-13: 2.3.0.** Routines (docs/ROUTINES_DESIGN.md): an analysis saved as a method and run again on
  new data - the promoter's edits and inputs, run zero verified against the kernel's records, the manager and the runs
  table, versions, the loaders and the Dataset cache in the run dialog, the retirements, the computation path for a
  follow-up on other data; the figures step; the Code tab; the Plots tab in order; Ask about a plot with the picture;
  PR #63 (Stripe API 2026-09-30) with the SDK pinned and the webhook crediting a paid session only - patches
  0111-0141. Executor build v52 (each Intervals load marked with its key): the image is rebuilt with this ship.
- **Status 2026-10-29: unreleased (patches 0237-0241).** Datasets by subject, steps 1-3 (docs/DATASETS_DESIGN.md):
  the Intervals loader keeps the store and the window's files under the subject's folder, `datasets/<user>/intervals/
  <athlete id>/`, with the subject's record beside them; a key's mark folder is adopted on the first load; the load
  record, the routines and the runs carry whose data; the cache check matches by the subject (0237, v67). The store
  keeps the laps, the wellness log by day, the calendar by entry and the profile's snapshots, and the window's files
  go under the subject's `views/` (0238, v68). The Dataset cache dialog draws the cache as a tree - source → athlete
  → dataset, a click opening the details with Load (from the store alone, nothing fetched), Load to today and
  Forget - from `/cache/inspect`'s `tree`; `/cache/forget`; window files older than a month leave (0239-0241,
  v71). The dialog redesigned after the product owner's second look: the lines are the Intervals.icu dialog's
  datasets plus the frame, each with its columns and a dot for what is on the Data tab; one dataset can be loaded
  alone (`with_frame` off); Forget is off the Data tab and out of the cache; each line says in words whether it is
  on the Data tab; a line's span is the window its loads covered, on the record; earlier loads are deleted on the
  executor's first start; one athlete at a time on the Data tab, the rule where the pills are made, the ledger saying another subject's data (0242-0247, v73). **Executor build v73**: the image is rebuilt with this ship.
- **Status 2026-10-28: 2.6.1.** A first address refused no longer marks a connection that then answered (on a box
  without an IPv6 route every dual-stack host would have read as "no connection" under a download that worked); the
  executor suite's checks hold on the public CI's runner - patch 0235. **Executor build v66**: the image is rebuilt
  with this ship.
- **Status 2026-10-28: 2.6.0.** The reach record (docs/REACH_DESIGN.md): the kernel records, per cell, what the cell
  touched outside the data - the hosts and the bytes each way, the files outside the data, the environment names, the
  programs started - each marked whether the question asked for it; a refused cell is its own state, not a failure;
  the record on the closing card, the pane's rows, the Investigation tab and the code map; the tally script per
  model; the cloud instance metadata address refused by the kernel; two blacklist faults fixed (the `os.exec` and
  `os.spawn` families, the text of f-strings) - patches 0230-0232; a library's scan of the import path and the record's
  state names out of the registry - patch 0234. Executor build v65.
- **Status 2026-10-24: 2.5.1.** The code map's ways in and out: a `[cell n]` citation in the report opens the map on
  that number; the eye on each notebook cell opens it at that cell; the recipe panel offers the other view; *Open in
  the notebook* lights the lines behind the number in the cell (map version 3). The diagram zooms as the thread map
  does. The `[cell n]` chip and the panel's buttons in the result colour; the light theme's result border. The
  README's figure. The stack's fake wellness on a cycle every window holds - patches 0220-0228. No kernel change:
  executor build v63 stands.
- **Status 2026-10-21: 2.5.0.** The code map (docs/CODEMAP_DESIGN.md): how a chain got from its data to its numbers,
  read mechanically from the committed cells and the kernel's record - no model call, nothing of it in a prompt - built
  at the chain's end and kept with it; the Steps view with the inputs as lanes, the recipe diagram of each number, the
  panel and the checks worth making; opened from the closing card's link or the thread map's eye - patches 0210-0217.
  The record's registry per cell, each RESULT's line and the run's mode (0210); the note surviving a review, CTX's
  tables typed (0208); the README's figure (0218). Executor build v63 (0210): the image is rebuilt with this ship.
- **Status 2026-10-18: 2.4.2.** The context's reading: each code with which way it points against the person's usual
  state, said or inferred, and the day it describes; a tag a label and a copy read once; each passage with its
  activity's day; earlier passages beside each batch; the calendar's categories on the map; the profile's custom sets
  and which end of the wellness scales is good; the report turn at medium effort; an action written as a tool call
  taken - patches 0191-0206. Reading version 4: the first load of each subject re-reads its passages once. Executor
  build v62 (0195, 0196): the image is rebuilt with this ship.
- **Status 2026-10-17: 2.4.1.** The README's head and overview in a technical register (patch 0189); no code change,
  executor build v60 stands.
- **Status 2026-10-17: 2.4.0.** The context (docs/CONTEXT_DESIGN.md): the words written beside Intervals.icu data -
  messages, notes, the plan's prose, calendar entries, custom fields - as a file of the load, coded against a codebook
  by the Coder seat, `CTX` in the kernel, `READ CTX` through the Reader, passages cited as [C.n] and shown as chips,
  the codebook screen with the coach's decisions; the Intervals.icu store (docs/INCREMENTAL_LOADS_DESIGN.md): a load
  downloads only what the store lacks, the hosted executor's datasets in a Docker volume per user (`nomad/jobs/`); the
  load dialogs' one grammar; the rider profile, the custom zone times and every custom field under its code
  (docs/RIDER_PROFILE_DESIGN.md); the auxiliary limit derived from the loaders' registry; the report's title as its
  first line, heading the Answer tab and the PDF export's top section (title, the question as understood, the data,
  the day and the reproduction verdict) - patches 0142-0187. Executor build v60: the image is rebuilt with this ship,
  and the four Nomad jobs re-registered for the volume.

### Phase 6 — team mode (O5)
- A users table, a login page, per-user kernels (subprocess or Docker), one process.

### Phase 7 — documents in the analysis
- Up to four documents a thread (PDF, Word, Markdown, text) parsed into units with locators and kept as
  thread files; a map of each in every prompt and the objects in the kernel; the READ action with
  verbatim, verified passages; `[D1.17]` citations with the passage on hover; the Reader seat. The
  design is `docs/DOCUMENTS_DESIGN.md`; it is hosted-path work, dev box first.
- **Status 2026-10-03: built and consolidated on the Mac; the hosted push pending.**

Phases 0 and 1 go together; nothing is installable before the identity seam works.
