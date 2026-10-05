# State on 2026-10-03 (read this first; the sections below are the 2026-09-05 handover of the engine)

- **How we work (Palo's standing rule, 2026-10-03 - read before changing anything).** When a model
  misbehaves, find the root cause before changing anything: read what the standing text actually
  says - the contract, the DATA block, the task line - and check whether the instruction exists at
  all, or says the opposite; read the record or the run log for the sequence of calls; only then
  decide. The fix goes where the cause is, in the fewest words or lines, and it corrects rather than
  supplements: a wrong sentence is rewritten, not followed by another; a mechanism is replaced, not
  layered. Prompts are held to the same discipline as code - the contract's page cap stands, and a
  sentence that does not change what the model does comes out. Before returning anything, simulate
  it: run the loop with a scripted model, replay the log, count what the seams actually received.
  The lesson behind the rule: an afternoon of 2026-10-03 went on a refused dictionary, a
  first-refusal-free rule, counts threaded through the loop and regexes, for a model whose standing
  text promised that READ never spends a cell turn; making that one promise conditional fixed it,
  and 0076 removed the rest.
- **Where the code lives.** One repository, two remotes: `BambooAI_Prod` (private; `origin` everywhere)
  and `BambooAI` (public). The Mac clone `/Users/palogalko/Projects/Bamboo_AI_v2`, the dev box and prod
  at `/home/data/bambooai` all run the same `main`: the snapshot `f28de59` plus the patch series
  0001-0053 (phases 0-5 of the open-source edition, then Ollama 0038-0045, vLLM 0046-0050, this
  handover 0051, the design document brought current 0052, the Ollama `repeat_penalty` 0053).
  Delivery is a patch series applied with `git am --keep-cr` (26 tracked text files are CRLF, among
  them every `bambooai/models/*.py`; 27 before `embeddings.py` retired), tested, pushed to the private remote, pulled on the boxes, pushed
  to the public remote last. Order: dev box first for anything the hosted edition runs; the Mac first
  for self-hosted work. A release is a version bump in `pyproject.toml` within the series, then a `v*`
  tag pushed to the public remote (`release.yml`, trusted publisher, scoped to `pgalko/BambooAI`).
- **Published.** The public repository carries 2.0 since 2026-09-16 (1.x kept as the `v1` branch and the
  `v1-final` tag). PyPI: 2.0.0 (2026-09-17), 2.0.1 (the Ollama work), 2.0.2 (the vLLM work, 2026-10-02).
  CI (`ci.yml`) runs the unit battery and the executor image build; the browser suites and the package
  test run locally before a push, by decision (three runner-environment failures taught that).
- **The open-source edition** (docs/OSS_DESIGN.md, v1.3 of 2026-10-03, decisions D1-D32; the documents design is in
  docs/DOCUMENTS_DESIGN.md):
  `AUTH_MODE=single` with the identity `BAMBOO_USER`; `bambooai/db/local_store.py` (SQLite behind
  Supabase's query shape); the executor container built from the Dockerfile the package ships and
  managed by `bambooai serve` (`--compute local` the fallback);
  `~/bambooai` the working folder. Configuration is a trio: the master `web_app/LLM_CONFIG_template.json`
  (ships with the package), the person's copy `~/bambooai/LLM_CONFIG_template.json` (four tiers of seats
  and `model_properties`), and the built `config/<user>/LLM_CONFIG.json` (one tier flattened), rebuilt when
  the template is newer or the level is saved in the dialog.
- **Local models.** `bambooai/models/ollama_models.py` on the daemon's native API: `num_ctx` from
  `model_properties.context_window` with a truncation report otherwise, `think` from the seat's effort
  (off / a level name / on, only for models whose /api/show lists thinking), the thinking channel to the
  pane, an unbounded first-token wait with an idle deadline, `keep_alive`, `OLLAMA_API_KEY` for
  ollama.com, the daemon's errors explained and the transient ones retried, `repeat_penalty` 1.0 on
  every request unless the model's `model_properties` entry sets its own (Ollama's Modelfile default
  of 1.1 hurts code and structured output; 2026-10-03). `bambooai/models/vllm_models.py`
  on an OpenAI-compatible server: `delta.reasoning`/`reasoning_content` to the pane, `reasoning_effort` by
  the model's level names (Qwen3.8: low/medium/xhigh; a tie between neighbours folds upward), thinking off
  via `chat_template_kwargs`, exact usage from the stream, a context pre-flight against `context_window`
  (vLLM refuses rather than truncates), the OpenRouter adapter's `_tail_guarded` and `_reasoning_delta_text`
  reused. The dispatcher hands adapters their `model_properties` entry through `set_model_properties`.
  Test beds: the Windows GPU machine (RTX A6000) at 192.168.1.201 - Ollama on Windows (11434), vLLM 0.30
  under WSL2 in mirrored networking (8000) serving Qwen3.8-27B in FP8 with Marlin kernels, CUDA graphs
  without `torch.compile`, MTP speculation (~40 tokens/s); the runbook is `vLLM_on_WSL.md` in the
  2026-10-02 outputs folder.
- **The tests.** `run_battery.sh` (83/45/30/19/49/44/50/1/1 Python; 29/7/29/56/24 JS); `tests/e2e/test_stack.py
  [--edition local] [--compute local|direct]` (32); `tests/e2e/test_local_store.py` (16);
  `tests/e2e/test_package.py` (34); `tools/stack/flows.py`; `tools/render_gallery.py --compare`.
- **Decided not to do, for now:** PRs #61 (LiteLLM SDK as a provider: heavy dependency, duplicated
  capability) and #62 (Requesty: good work, but a copy of the OpenRouter adapter that would drift). The
  right unit, when wanted, is one generic OpenAI-compatible gateway provider with a table of gateways.
- **Documents (2026-10-03; the consolidated series replaces the day's 0054-0089).** A thread carries up to
  four documents (PDF, Word, Markdown, text), parsed once into units with locators (`D1.17`) and stored as
  files under `storage/<user>/documents/<thread>/`, mirrored into the executor by content; in the kernel
  each is an object (`D1.text`, `.page`, `.units`, `.grep`, `.table`, `.outline`) the analyst reads with
  cells; one new action, `READ <scope> <question>`, served by the Reader seat in one call over BM25
  candidates (or exactly the stretch named), every passage verified verbatim, the digest in the prompt
  and `SHOW READ k`; the report cites `[D1.17]`, the guard checks the quote, the page shows the passage
  on hover; the paperclip's Document entry, the Documents pill and view. A READ is a turn, like a
  SEARCH, three a run. The documents paragraph joins the contract only when the thread has documents;
  without them the prompt and the accounting are the original, byte for byte. Removed from the first
  build after real runs (a plain run at nineteen exchanges, a documents run at thirty-three with
  eighteen free looks): the economy of free look-ups, caps and refusals; the `LOOK` action; the
  embedding stack (Embedder seat, `embed()` in the adapters, vectors, reciprocal-rank fusion) and the
  re-wiring of memory to it; map-reduce reads. `docs/DOCUMENTS_DESIGN.md` v1.0 states what is built.
  Also in the series: `SHOW RUN` stays in view - every shown run whole while together they fit 60k characters - and takes several (the synthesis loop; a count of three had kept a five-chain synthesis cycling), a reply is read from its last complete ###ACTION### block (a reasoning model corrects itself in the open; the draft had run) and the contract says so; several CELL blocks in one reply: the first runs and the next prompt says one cell per turn (merging them was tried on 2026-10-04 and reversed: the model wrote fourteen cells blind in one reply; a ###END### terminator enforced as a provider stop sequence was tried the same day and withdrawn: on vLLM and Ollama it cut thinking models off inside their thinking, and it made models drop fences and write turns into the thinking block - three parser conditions for one marker), a reply with
  several actions is handled and a bundled REPORT no longer lost, SHOW of several of anything, the
  `[cell n]` chips fixed. **Hosted push still pending**: the executor image rebuilt and recycled, the
  Reader seat in the boxes' template, `pdfplumber` and `python-docx` in the boxes' venv, a smoke test
  that attaches a PDF.
- **The contract (2026-10-04).** Rewritten as markdown: sections with headings, each rule once; the format a literal
  template of one turn (three marker lines, each once); the actions a table, which gains the `READ` row
  with documents; seven note headings (the count had said six); `ASK` ends the run; `SHOW RUN` chains stay
  in view, shown cells are for the next prompt. No terminator, no invitation to restart - the prompt
  that evolved organically had both, and a reasoning model took them literally. `analyst.session.contract()`
  assembles it. Proof: the battery, and the Fibonacci and documents runs live.
- **Phase 1 of the Adaptive-run review (2026-10-05)**, after the independent review of chain 1791137848
  (REVIEW_adaptive_run_2026-10-05.md in the outputs folder): the parser takes a fenced block directly under
  ###ACTION### as a cell (six turns of forty-eight had been refused for the missing word); the kernel defines
  `DS` - the dataset as attached, `DS.load()` a fresh copy from the file it loaded - and appends a one-line
  warning to a step's output when `df` has lost the dataset's columns (a cell had reused `df` as a loop variable
  and the run paid for it over twenty turns); a run commits at most three figure cells, the fourth refused with
  the reason (a run had drawn nine). Nothing the model is told changed; that is phase 2, with the reviewer seat
  phase 3, each tested on the same question in Deep and Adaptive. Executor build v44.
- **Phase 2 (2026-10-05): the contract.** `DS` named; a Results section - a cell prints `RESULT: ...` and the
  line rides, with its cell number, under RESULTS SO FAR in every later prompt, what the report quotes; the
  cell row of the actions table is "a fenced python block"; the report gains "the comparison: what the
  question asks to compare, and what you compared"; figures drawn last, a fourth figure cell not run; the
  budget as a limit, not a target, and the task line without the countdown ("turn 12; up to 48 turns and
  $4.00"). Phase 1's measures held on both runs (0 rejections, 3 and 1 figure cells); Adaptive took 19 of
  48 against 47 before any phase, not yet credited to anything.
- **Phase 3 (2026-10-05): the reviewer.** The review is no longer a turn of the analyst: after every 8th turn in
  Adaptive the session calls the Reviewer seat with its own prompt (`analyst/reviewer.md`) and its own input - the
  question, the data, the thread, the note, RESULTS SO FAR, the cells one line each, its earlier reviews with the
  analyst's answer to each, the turn - and no actions. The reply is a review in a fixed shape ending in one
  verdict: TEST, NARROW or REPORT. The review rides in the analyst's next prompts under REVIEW until the next one;
  REPORT binds - the next turn is the report, by the path the session uses when the budget runs out. After every
  report, in every mode, the same reviewer reads the report against the question and its note is added for the
  reader. The Reviews section of the contract (`contract_reviews.md`) rides only in Adaptive, naming the cadence.
  Folded in: figures drawn once the estimate is settled (phase 2's 'drawn last' had cost a Deep report its
  figures), and a RESULT: line for every estimate, provisional or final (phase 2's 'a number you may report' had
  the ledger empty until turn 37). Phase 2's measures: the comparison stated in both reports; Adaptive still 46
  turns, the budget wording no brake.
- **Next candidates:** the CI badge back in the README (the public workflow exists now); an 8-bit Ollama
  tag (`qwen3.8:27b-q8_0`) to compare quality with vLLM on equal footing; O5 team mode (a users table
  exists in the store); O9 integrations on the local kernel. Parked
  from 2026-09-09: the orchestrator's health check returns a tuple three call sites test for truth; a
  single missed probe destroys a container; a failed tier lookup answers 'free'.

# BambooAI — handover (redesign of 2026-09-05)

One analyst, one kernel, one notebook, one report. The design checklist that every change
must pass is `docs/DESIGN_CHECKLIST.md`; the inventory of what was removed and why is
`docs/REMOVE_MODIFY_INVENTORY.md`; the full history of the previous design is `docs/history/`.

## The shape

- `analyst/` — the whole harness (~1,000 lines): `contract.md` (the only prompt, one page),
  `session.py` (the turn loop, budget, the reviews, report + rewrite + guards + replay),
  `notebook.py` (a tree of runs and turns per thread; collapse; JSON persistence),
  `tools.py` (run a cell, show a cell, names, recall, search, ask), `report.py` (the two
  numeric guards, cell/figure references, table repair), `replay.py` (assemble the cited cells
  into one script; rehydrate a path; verify in a fresh kernel). The headless runner of the first week
  (`llm_openrouter.py` + `cli.py`, its own OpenRouter client and price table) was removed on 2026-10-04:
  the battery drives the session with a scripted model, and the app is the product.
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
planning dial maps to adaptive; `max_investigations` × 4 turns). The adaptive preset is reviewed
after every 8th turn by the reviewer (its own prompt, `analyst/reviewer.md`); every report is reviewed once.

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
