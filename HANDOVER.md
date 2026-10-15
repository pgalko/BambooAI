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
  `v1-final` tag). PyPI: 2.0.0 (2026-09-17), 2.0.1 (the Ollama work), 2.0.2 (the vLLM work, 2026-10-02), 2.1.0
  (2026-10-06: documents in the analysis, the Markdown contract, results recorded by the kernel, the reviewer's
  evidence and perspectives, generated datasets - patches 0057-0096), 2.1.1 (2026-10-07: the configuration template
  tidied and repriced, gpt-6.1-sol, the pricing preflight - patches 0097-0100; no kernel change, image v51 stands),
  2.2.2 (2026-10-08: the Claude 5.5 family on the Anthropic adapter, the contract's STEP section, the forced report's
  card, the replay's display options, auxiliary files in DATA, the template's Claude seats - patches 0101-0110;
  `anthropic>=0.88` is now the floor; no kernel change, image v51 stands), 2.3.0 (2026-10-13: routines - an analysis
  saved as a method and run again on new data: the promoter and its inputs, run zero verified against the kernel's
  records, the manager and the runs table, versions, the loaders in the run dialog, the Dataset cache, the retirements,
  the computation path for a follow-up on other data; the figures step and the plain-language version citing the
  figures; the Code tab; the Plots tab in order and sized to the tab; Ask about a plot with the picture; the Answer
  tab's measure; PR #63 and the Stripe follow-ups - patches 0111-0141; **executor image v52** (patch 0125: each
  Intervals load marked with its key, its files in the key's folder) - the boxes rebuild and roll it out with this ship). **Next ship carries executor image v55** (patches 0143, 0145: the context fetch, the coaches by the plan; 0161: the Intervals.icu store) - rebuild and roll out, and re-register the four Nomad jobs (`nomad/jobs/`, patch 0164: a volume per user at `/app/datasets`, so the store outlives a dispatch).
  CI (`ci.yml`) runs the unit battery and the executor image build; the browser suites and the package
  test run locally before a push, by decision (three runner-environment failures taught that).
- **The open-source edition** (docs/OSS_DESIGN.md, v1.3 of 2026-10-03, decisions D1-D32; the documents design is in
  docs/DOCUMENTS_DESIGN.md, the routines design in docs/ROUTINES_DESIGN.md, the context design in docs/CONTEXT_DESIGN.md):
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
- **The tests.** `run_battery.sh` (210/155/31/24/18/49/44/69/11/127/33/37/29/1/1 Python; 49/7/33/67/24/71/8/4 JS); `tests/e2e/test_stack.py
  [--edition local] [--compute local|direct]` (104 hosted, 101 local; the walk needs a real marked 4.x in tools/stack/browser/vendor/ -
  `vendor.prepare()` copies one from a node_modules on the machine or fetches it with network); `tests/e2e/test_local_store.py` (16);
  `tests/e2e/test_package.py` (37); `tests/e2e/test_date_inputs.py` (8, Chromium over the dialogs' date inputs); `tests/e2e/test_integrations.py` (88; hosted only - the loaders need the executor; the
  stack's fake Intervals.icu and Endura behind the real loaders); `tools/stack/flows.py`; `tools/render_gallery.py --compare`.
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
- **Phase 3b (2026-10-05), from Palo's reading of the phase-3 runs.** (1) One kernel: the executor image ran its own
  copy of the kernel (containers/executor/kernel.py), forked at the snapshot; phase 1 had changed only delve's, so `DS`
  never existed in the image and both runs' first cell failed on it. The image's copy is now delve's but for the one
  import that differs by design, and tests/analyst/test_executor_kernel.py holds it there and runs `DS` through the
  executor's own kernel service. Build v45. (2) A reply carries one action: every action in every ###ACTION### block is
  found, and if they are not all the same nothing runs and the analyst is told (a reply had held a 69-line cell and a
  four-line restart of imports; the last-complete-action rule ran the four lines and the reviewer's test never
  happened); the same action written twice runs once; after REPORT the block is the report; a fence without its
  closing line is not run. (3) A TEST's outcome goes on a RESULT line tagged with it - `RESULT: (test after turn 16)
  ...` - and the session reports its status, answered or open, in the analyst's REVIEW block and in the reviewer's
  input, with the cells, failures, empty cells and RESULT lines since each review. (4) The reviewer's REPORT needs every
  condition it listed under The question requires addressed by a RESULT line it cites, or stated as not estimable,
  and no open TEST unless a decline is accepted and said; claims cite [cell n] with the number and interval as
  printed, and a comparison writes both numbers out (a review had called +22.1 'comfortably' inside -17.9 to +13.7).
- **Phase 3c (2026-10-05), from Palo's second reading: the reviewer could judge direction, not verify implementation.**
  Its input had the note, the RESULT lines, a line per cell and a count of failures - no code, no outputs, no failure
  details, none of the analyst's intermediate admissions, and no way to open a cell. Now: the reviewer may open cells
  before its review (`SHOW 12 14`, `SHOW turn 22` for any turn, a failed one included - code and complete output, at
  most twice a review); its REPORT binds only when it opened every cell it cites, else it is advice and the analyst's
  REVIEW block says so; its input lists every analyst turn with the analyst's own account (the THINKING), the action
  and the outcome (first printed line, the error of a failure, a refusal) - turn 22's 'the within-abroad fit is
  mislabelled: no athlete dummies, -2.1 is pooled' would have been in view; a RESULT line beginning
  `(corrects cell 14)` marks cell 14's line as corrected in every prompt; the brief: a RESULT line is not proof its
  label describes the computation - open the cells the verdict rests on and check the estimator, the sample, the
  adjustment and the unit, and that the adjustment set covers the recorded differences between the compared groups.
- **Phase 3d (2026-10-05): three faults, and the prompts cleaned to a standing rule.** (1) A reviewer reply with a
  placeholder review and a SHOW line was treated as a review and dropped: a reply with no valid verdict and a SHOW
  line is now a request. (2) The 3c Adaptive run lost its figures because the replay runs a plain script in the
  executor (/execute, not the kernel) and its figure cell began `df = DS.load()`: the assembled script now defines
  `DS`. (The replay already ran cells cited as [fig n]; it now also reads combined citations - [cell 5, cell 6],
  [cells 6-9].) (3) The kernel's restricted-name check matched words inside strings - a label '+HR eval@150' was
  refused as eval: comments and plain strings are blanked before the check, f-strings stay. Executor build v46.
  The standing rule (docs/DESIGN_CHECKLIST.md C5, extended): no task-specific or model-specific content in any prompt. Removed:
  the rewrite task's heart-rate and 4-11% examples; the contract's training-load example, the note's examples from
  earlier threads, 'where it breaks down', the figure-timing advice and 'write the turn once'; the reviewer's
  'within' parenthesis, its examples echoing the test question, 'an association reported as a correction', the
  pooled-subgroup example, 'write both out', the empty-cell line and the redundancy examples; the session's advice
  after two failures and after a refused reply (the facts stay). A battery check scans every authored prompt text.
- **Standing issues, one patch each, verified on one Deep and one Adaptive run (2026-10-05).** The auto-evaluation
  work (the first 0077) was dropped before it was deployed. Issue 1, this patch: Quick and Deep make no reviewer
  call - the review after the report runs only in a run that has reviews during it (Adaptive). Next, in order:
  RESULT lines the code did not compute are marked; the reviewer gets its evidence in one call with a verification
  ledger instead of SHOW rounds; a reviewer's finding marks the ledger; the replay runs to the last figure cell.
- **Issue 2 (2026-10-06): a result the code did not compute no longer counts as evidence.** An analyst had typed
  "+6.1 bpm (95% CI +4.4 to +7.7)" into a RESULT print whose own regression printed -0.19, and the report quoted it;
  nothing downstream could tell a typed line from a computed one. Now the kernel records results: the cell calls
  `RESULT(what, estimate, low, high, unit, direction, test=, corrects=)`, the kernel prints the line from the values
  and keeps a record (both kernel copies, build v47); the ledger reads the records, not printed text - a printed
  "RESULT:" line is output like any other. A number written into the call - a literal, or an expression of literals,
  read from the cell's code at the call - is marked "typed" on the line and in the record, and the report guard no
  longer counts that line's numbers (nor the call's literals in the code) as evidence, so a report quoting them is
  flagged. The tags became arguments: test="after turn 16", corrects=14. The contract's Results section shows the call. The replayed
  script defines RESULT when its runtime has none (the executor's /execute route runs a plain script), printing the
  kernel's line to the character (2026-10-06: the first Deep replay under 0078 had stopped on NameError).
- **Prompt hygiene (2026-10-06), from reading every prompt of a Deep run as the model does.** (1) A reply with several
  different actions runs the first, and the next prompt says the rest did not run - refusing it had cost one or two
  turns a run (the first two turns of that Deep run, both restarts). (2) The budget line and the whole view come on the
  last turn itself, not the one before: Deep had 14 working turns of 15. (3) The ledger does not repeat the newest
  cell's RESULT lines while that cell's output is in view whole. (4) The one-line summaries of collapsed and failed
  cells, and the pane card's peek, describe a cell by the analyst's own account of the step - its THINKING from the
  second sentence on, the first being what the last output showed - and what came out by a printed fact: the first
  RESULT line the kernel recorded, else the first printed line, or the error. Code is read only without an account,
  and then never an import or an option line ("import pandas as pd" had stood for three cells of five).
- **Two faults from the first run under 0080/0081 (2026-10-06).** (1) RESULT marked thirteen computed lines as typed:
  the analyst had passed its values starred - RESULT("...", *fit()[:3], "units", "up") - so the unit and the
  direction strings sat in the numeric slots and a string constant counted as a literal. Only numeric constants
  count now, and a starred argument leaves the positions alone (a text estimate is still caught at runtime).
  Executor build v48. (2) The step sentence split at abbreviations - "(e.g. Jan Meda", "i.e. it is venue" - so
  one-liners began mid-sentence; sentences no longer end at e.g., i.e., vs., cf., etc., an initial, in the
  notebook and in the pane's peek.
- **The reviewer gets its evidence in one call (2026-10-06), replacing the SHOW rounds.** The rounds re-sent the whole
  input each time (48% of an Adaptive run's cost), the reviewer drafted a review before asking, and it cited cells it
  had not opened while saying it had checked them. Now the session hands it the cells to check under TO CHECK NOW: the
  cells behind the best estimate (cited by its line, or whose RESULT line carries its numbers), those tagged as
  answering a TEST, then those that recorded a result since the last review, and a cell the last review asked to see
  again - up to 20,000 characters, the rest named; after the report, the cells the report cites. A cell handed to an
  earlier review is not sent again: its Checked line rides under CHECKED BY EARLIER REVIEWS (the verification ledger,
  Turn.shown/checked/recheck). The turn log covers the turns since the last review. A REPORT binds only when every
  cell it cites has been checked, in this review or an earlier one; otherwise it is advice and the analyst's block says
  which cell. The reader's note names the cited cells checked and not checked. The reviewer's brief has TO CHECK NOW,
  Checked and Re-check lines, and no SHOW.
- **Seen on the first 0083 run (2026-10-06):** one call per review (three calls, 35,700 input tokens against six calls
  and 60,000 before); the first review's Checked line on cell 5 - a substantive one - rode into the second review;
  the test's tagged answer was handed to the review that checked it; no cell sent twice. The reviewer wrote a Checked
  line for only some of the cells handed to it (one of three, one of four), which is fine - a handed cell counts as
  checked - and still cited cells it was never handed, which the reader's note now names as not checked. The review
  after the report ran to 16,700 tokens: its evidence budget is now three fifths of the mid-run one (the report is
  in view), and earlier verdicts are capped at 400 characters in EARLIER REVIEWS.
- **docs/RUN_ASSESSMENT_2026-10-06.md:** the altitude question across 21 runs - the spread of headlines against D1,
  what every solution shares, what decides where one lands (the comparison chosen; effort as a covariate, never as
  strata), and how to score a new run. Mechanics improve patch by patch; substance has not moved.
- **A reviewer's finding changes the record (2026-10-06).** A Checked line that says "does not" (and not "matches")
  marks every RESULT line of that cell in the ledger - "(the review after turn 16 found this line does not describe
  its code)" - for the analyst and for later reviews; a report that cites the cell gets a CHECK note for the reader;
  a later review's "matches" on the same cell clears the mark (the latest word stands). Turn.checked carries ok per
  line.
- **The replay runs to the run's last figure cell (2026-10-06).** It ran to the last cell the report cites; a figure
  drawn after that cell was never replayed and never reached the reader. Now it runs to the later of the last cited
  cell, the run's last figure cell and the last [fig n] cited. This closes the standing list of issues of 2026-10-05;
  the next runs confirm 0083-0086 together.
- **From the run that confirmed 0083-0086 (2026-10-06):** reviews one call each (10,400 / 12,000 / 13,500 tokens),
  the handed cells counted as checked and carried forward, the test's tagged answers handed to the review that judged
  them; three RESULT lines typed in by the analyst (5.23, -1.05, 11.90 copied from an earlier output; 1.00 for a check
  that is not an estimate) were marked typed, correctly. Two faults fixed: a Re-check asked by one review had lost to
  the next review's budget - it now comes first; and a reply cut at the seat's max_tokens (16,000 tokens of reasoning,
  887 characters of text, no action) had been reported as "no valid action" - the app's model call now returns whether
  the reply was truncated, and the analyst is told it was cut off at the length limit.
- **The reviewer's perspectives (2026-10-06).** The analyst follows one path; the reviewer's brief now makes it look
  through five generic lenses before it judges - identification, alternative explanation, heterogeneity (each thing
  the analyst holds fixed is also a candidate for a condition the effect depends on), measurement, the question's
  frame - one line each or "nothing", and a TEST must come from one of them. The lens lines that found something ride
  into the analyst's REVIEW block. No task content: the lenses are the questions a second analyst asks of any study
  (the standing rule's scan covers the brief). The measure of success is in docs/RUN_ASSESSMENT_2026-10-06.md: whether
  the TEST verdicts change kind - a split by a recorded condition where every run so far restricted or adjusted.
  Palo chose not to hand the reviewer the list of unused columns.
- **The first run under 0088 (2026-10-06, Adaptive, 40 turns, $0.65).** The lenses changed the reviewer: its first
  review's heterogeneity line noticed the two arms sat at different effort levels, and its TEST asked for the
  comparison within comparable easy effort without conditioning on it - the first split by a recorded condition in
  22 runs, where every earlier test restricted or adjusted. The analyst followed; the headline became an
  effort-stratified bracket (+4.0%/1000 m at easy effort, hard effort not estimable, a 4-athlete sea anchor), in the
  reference answer's magnitude for the first time though in the other stratum. Later lenses raised terrain
  measurement and the surface/temperature confound; the review after the report caught a misstated bound in the
  reader-facing text. Reviews ran 4,000-8,000 output tokens; the reviewer was $0.21 of the run. Two fixes: the
  Re-check and Shown lines were riding into the analyst's REVIEW block and the analyst read "Re-check: cell 17,
  cell 18" as an instruction to itself - six turns of SHOW; they are the session's and stay out of the block now.
  And a REPORT verdict's "most consequential problem", when not "none", now reaches the reader's note as a caution.
- **The second run under the lenses (2026-10-06, 32 turns, $0.59).** The heterogeneity lens did not raise effort this
  time; the first TEST was a restriction (drop the race laps from the sea-level anchor), and the run concluded "no
  usable correction" - so the effort split of the first run is one of two, not a rule. Reviews ran 4,000-10,000 output
  tokens (the reviewer $0.19, a third of the run). Two fixes: the review after the report ended with a stray
  ###REVIEW### after a complete review and parse_review read the empty text after it - it now takes the last marker
  that has a verdict after it; and the reviewer's talk of "unchecked cells" and "cite only checked numbers" had the
  analyst spend six turns on SHOW - the brief now says checking is the reviewer's own work and it asks the analyst
  for analysis, not verification.
- **Generated datasets reinstated (2026-10-06).** The original BambooAI's prompt told the agent to save a dataset it made
  under `datasets/<user_id>/generated/` - the folder the Dataset cache lists under Generated and the download route
  serves. The rebuilt analyst had no such place, so a dataset it "returned" landed in the kernel worker's working
  directory where nothing listed it (Palo: a merge of two datasets, reported as generated, nowhere to be seen). Now
  the app hands the kernel that folder at start (RemoteKernel -> /kernel/start generated_dir -> PersistentKernel ->
  the worker's fourth argument), `DS.save(frame, "name")` writes `<name>.csv` there and prints "DATASET: name.csv -
  rows x columns, in the Dataset cache under Generated", the replayed script's DS stub does the same into the folder
  the /execute route already passes (now in the script's namespace as _generated_dir; the local replay's kernel gets
  it too), and the contract's workspace paragraph has one sentence naming DS.save. The UI, the /cache blueprint and
  the executor routes were intact and unchanged. Executor build v49.
- **Two amendments after the first DS.save run (2026-10-06).** (1) In the Dataset cache a generated file with 845 columns put
  the Load/Download/Remove buttons a long scroll away: #datasetDetails (the panel's one child) is now the flex column
  that fills the panel, the file's details and the buttons stay in view, and the columns list scrolls by itself - the
  layout was checked in a headless render (845 columns, a 49-column primary, a 640-px window) and in the hosted story
  through the real executor. (2) The run's dataset pills showed twice; they ride once, under the REPLAY row, and the
  closing card no longer repeats them. Also seen there: "3 min 60 s" - seconds are rounded before the split now. The
  stack's scenario saves a dataset (DS.save in its estimate cell), so both stories see the pill; the hosted story opens
  the Dataset cache and checks the Generated entry and its buttons.
- **No Generated datasets tab (2026-10-06).** The web output manager had sent a generated_datasets payload with the
  results, and the tab factory made a right-pane tab for every type it did not know - an empty "Generated_datasets" tab.
  The payload is gone (the pane's pills carry the files) and the factory makes no tab for the type; both stories check.
- **DS.save in other formats (2026-10-06).** The format follows the name's extension - csv (default), json (records),
  parquet, xlsx, txt/tsv (tab-separated) - or `fmt=`; a string is written as a text file whatever the extension. The
  replay stub mirrors it; the executor's preview gives a text file its basic information (columns when it reads as a
  tab-separated table). The contract's sentence names the formats. Executor build v50.
- **DS in every run (2026-10-06).** The kernel had defined DS only beside an attached dataset. A run with no dataset
  ("plot the Fibonacci sequence and return it as json and txt") hit NameError on DS.save, which the contract promised,
  and spent twelve of fifteen turns hunting for a delivery route - reading dataio.py and the kernel's own source off the
  disk, trying sys.argv and importlib (both stopped by the restricted-module guard) - before reporting files in /app
  that nobody could see. DS now exists in every run: without a dataset, DS.load() prints that nothing is attached and
  returns None, the df check is a no-op, and DS.save works as everywhere. The replay stub likewise. Executor build v51.
- **The template tidied (Palo, 2026-10-07).** web_app/LLM_CONFIG_template.json: fifteen stale model entries removed
  (grok-4.3/4.5/4.6, the Mistral and Codestral entries, the Gemini 3.x previews and image models, gemini-3.7-flash,
  deepseek-v4-flash-0731, the local Qwen 30B and the R1-distill path, claude-sonnet-5/opus-5), claude-sonnet-5-5 and
  claude-opus-5-5 added, openai/gpt-5.6-sol repriced to 0.002/0.010 per 1k tokens (cache 0.0001/0.0025). Seats and
  tiers unchanged; every seat's model priced and its effort level valid; no code names a removed model outside
  comments. The direct gpt-5.6-sol entry was aligned to the same price (OpenRouter's is the current one, Palo).
  LLM_CONFIG_sample.json at the repository root still lists the old entries.
- **Pricing preflight (2026-10-07).** A call's cost is its token counts times the prices of model_properties[model]
  in the working LLM_CONFIG.json; a model string with no entry costs $0.00 with nothing said (a Reviewer on
  openai/gpt-5.6-sol ran a whole performance-tier run at $0.00 while OpenRouter billed it). ModelManager now names,
  at boot, every seat whose model has no priced entry (ModelManager.unpriced_seats, _preflight_pricing - a warning
  beside the provider preflight).
- **gpt-6.1-sol (2026-10-07).** OpenRouter's openai/gpt-5.6-sol is superseded by openai/gpt-6.1-sol (released 2026-09-29;
  checked on openrouter.ai and OpenAI's pricing page: $2 / $10 per 1M tokens, cache read $0.10, cache write $2.50 -
  the same prices as the 5.6 entry carried; efforts low, medium, high, xhigh, max; 1.05M context, 128k output). The
  template's three seats on 5.6-sol (the performance Reviewer, the max Analyst and Reviewer) run on 6.1-sol; the 5.6
  OpenRouter entry is replaced by the 6.1 one. The direct-API gpt-5.6-* entries and the 5.6 -pro entries still stand.
- **Auxiliary files in DATA (2026-10-07).** A run with two auxiliary files and no primary dataset read "(no dataset
  attached)" and nothing else - the auxiliary line in _dataset_description came after an early return - and the
  analyst reported having no data; the original BambooAI always described the auxiliary files with their first rows.
  Now DATA carries an AUXILIARY FILES block in every case: each file's path as the kernel sees it (relative to its
  working directory, the same in both compute modes) and its first five rows - from the executor's
  /aux_datasets_to_string in api mode, read here otherwise - a wide head cut at 3,000 characters with a note. With no
  primary it opens with "No primary dataset is attached: `df` is not defined and DS has nothing to load. The data are
  the auxiliary files below; read one into a frame yourself". With neither, "(no dataset attached)" stands.
- **Claude Haiku 5.5 and the Anthropic adapter brought up to the 5.5 API (2026-10-08).** Researched on anthropic.com,
  platform.claude.com and openrouter.ai: Haiku 5.5 (`claude-haiku-5-5`, released 2026-10-07) is $0.10 / $0.50 per 1M
  tokens, cache read $0.01, cache write $0.125 for prompts up to 100k tokens (5x those prices above 100k), 1M context,
  128k output, an adjustable effort setting; Sonnet 5.5 cache reads halved to $0.10 (Opus 5.5 reads $0.20, writes $5).
  The 5.5 family controls thinking with `output_config.effort` (low, medium, high, xhigh, max) and adaptive thinking
  (on by default; `budget_tokens` is a 400), returns thinking blocks empty unless `display: "summarized"`, rejects any
  non-default temperature/top_p/top_k, assistant prefill and (Sonnet) forced tool choice, and declines with
  `stop_reason: "refusal"`; thinking can be turned off with `disabled` on Haiku 5.5 and `between_tools` on Sonnet 5.5
  at effort high or below, never on Opus 5.5. Prompt caching is unchanged in shape (explicit `cache_control`
  breakpoints, 512-token minimum on the 5.5 family) - the adapter's system-prompt breakpoint stands.
  The template: `claude-haiku-5-5` added, Sonnet's cache read repriced, the three direct 5.5 entries and the three
  OpenRouter routes (`anthropic/claude-haiku-5.5`, `-sonnet-5.5`, `-opus-5.5`, same prices) carry
  `reasoning_style: effort`, the five levels, `thinking_off` (disabled / between_tools) and `no_sampling: true`.
  The Anthropic adapter takes the dispatcher's hand-offs (properties, style, efforts) and shapes the request from
  them (`request_params`): effort snapped to the declared vocabulary, adaptive thinking with summarized display so the
  pane sees the reasoning, thinking off where the entry allows it when a seat asks for "none", no temperature on a
  `no_sampling` model, the effort and thinking type recorded in the call's meta; a refusal stop reason is said in the
  pane and in the reply. The OpenRouter adapter honours `no_sampling` too (with tools it asks OpenRouter to require
  every parameter, so a temperature it cannot honour would have failed the route). Untested live: Palo tests direct,
  then through OpenRouter. The monthly API credit for subscribers is a billing matter, nothing in the code.
- **The refusals of the first Sonnet 5.5 run: the contract's THINKING section (2026-10-08, patch 0104).** Four of the
  run's sixteen analyst calls came back `stop_reason: refusal` within a second and with no output tokens; each refused
  prompt differed from the next, accepted one only by the task line and a note sentence. That is Anthropic's
  `reasoning_extraction` classifier (platform.claude.com/docs/en/build-with-claude/refusals-and-fallback): it declines a
  prompt that asks the model to fill a thinking/reasoning/scratchpad section before the answer, or to keep private
  notes or a running log of its reasoning - the wording may sit in the system prompt - and such refusals are billed
  before any output; the guidance is "change the prompt rather than retrying", and there is no fallback model for the
  category. The contract's `###THINKING###` section and a note described as "your memory across turns" were that
  pattern. Now: the section is `###STEP###`, "two or three sentences for the person following the run: what the last
  output showed, what this turn does and why" (an explanation of an action, which the policy allows), and the note is
  "the standing state of the analysis, for the person and for your next turn"; the parser and the pane read either
  marker, so an old record streams and renders as before; the reviews paragraph and the REVIEW block say "answer it in
  your STEP". The adapter reads `stop_details` on a refusal and records the category (and the explanation) in the
  call's meta, the pane message and the reply marker; the session tells the model "the provider declined the request
  before any text (category); nothing ran" instead of "no valid action" - the analyst had re-sent the same SHOW three
  times, each time told its reply had no action. The same run's other findings are separate patches: the forced
  report's missing card (0105), the replay's display options (0106). Untested live; a test guards the contract and the
  reviewer prompt against the words thinking, reasoning, scratchpad, memory and private.
- **The forced report has a card; a report without the marker lines is told so (2026-10-08, patch 0105).** The
  Sonnet 5.5 run used all fifteen turns; the report the session then asks for once ("Write REPORT now.") had a turn_end
  and no turn_start, so its text streamed into no card and the app printed it raw under the closing card. The same held
  for the report forced after five failed cells. Both calls now open a card (turn 16 of 15; turn n+1 after the failures),
  and the exhausted-budget call carries what the last turn produced (a failure's traceback, a lost reply's note) ahead
  of the ask. A lost reply shaped like the report - headings or [cell n] citations, no fence, no ###ACTION### - is told
  "read like the report but had no ###ACTION### block ... A report is: ###ACTION### on its own line, REPORT on the next,
  then the report" instead of "no valid action". Not done: taking a bare REPORT line as the action - a parser leniency
  held back until 0104 shows whether the scaffold-dropping persists.
- **The replay prints what the kernel printed (2026-10-08, patch 0106).** "Replay ran but 4 of 235 cited numbers did not
  reappear (0.06428, 1.401e+04, 1.49e+04, 2532)" was formatting, not reproduction: the analysis kernel prints floats at
  four significant digits with every column shown (delve/kernel.py), the replay runs the assembled script through the
  plain executor route under pandas' defaults - 14901.6 for 1.49e+04, a seven-column crosstab elided to "..." (2532
  gone). Reproduced here with the same frame under both settings, to the number. The assembled script now sets the
  kernel's five display options after its imports (`analyst/replay.py` DISPLAY_OPTIONS, held to kernel.py's lines by a
  test) and resets them on its last lines, since the executor's process goes on serving the data views; when a replay
  stops early the app sends the reset on its own (`RESET_OPTIONS`). The numbers check reads e-notation at its own
  precision (1.49e+04 matches 14901.6: the mantissa's decimals less the exponent), so a report that quotes a kernel line
  is not held to half a unit. No kernel change, no image rebuild.
- **A Claude card shows its reasoning (2026-10-08, patch 0107).** 0103 asked for `display: "summarized"` "so the pane
  sees the reasoning" and then captured the thinking deltas for tool replay only: no Claude card had a reasoning fold,
  and whether a turn had thought at all could not be seen - which is why a Sonnet 5.5 run read as "quick, as if
  reasoning were off" (the logged run's output tokens put its hidden thinking at roughly 300-1,700 tokens a turn:
  present, light). The adapter now streams each thinking delta to the pane's thought channel as every other reasoning
  adapter does, and the call's meta records `thinking_chars` (the summary's length) and `thinking_blocks` (0 when
  adaptive thinking skipped thinking - the docs say it may, for a simple request, and that effort "controls how often
  and how deeply it thinks"). The request shape is unchanged and the same for Sonnet, Haiku and Opus; how much a model
  thinks at `high` is its own choice under adaptive thinking - a seat that wants more sets `xhigh` or `max`.
- **Temperature through extra_body; the preflight names the nearest entry (2026-10-08, patch 0108).** A max-tier
  run on `claude-opus-5.5` (a dot; the API id and the template's key are `claude-opus-5-5`) died before the request:
  `Messages.create() got an unexpected keyword argument 'temperature'`. Two things: the current Anthropic SDK's typed
  create() carries no temperature/top_p/top_k at all, so any seat that still sends one - every model without
  `no_sampling` on its entry, the Haiku 4.5 shape among them - raised a TypeError on the client; and the misspelt
  model string had no properties entry, so none of the entry's facts (effort levels, thinking, no_sampling) applied and
  the request fell to the old shape. Now the adapter passes temperature in `extra_body`, which every SDK version merges
  into the request body (the API still accepts it on the earlier models; the 5.5 family keeps `no_sampling`), and the
  pricing preflight's warning names the nearest `model_properties` key when the seat's string is within a character or
  two of one ("The nearest entry is 'claude-opus-5-5' - a misspelling of it?") and says the entry's facts do not apply.
- **The template's Claude seats (Palo, 2026-10-08, patch 0109).** The performance tier's Analyst, Rewriter and Reader
  on `claude-sonnet-5-5` (the Analyst at `xhigh`), the max tier's three on `claude-opus-5-5` (the Analyst at `xhigh`);
  the Reviewers stay on `openai/gpt-6.1-sol` (high / xhigh), the free and cost tiers on DeepSeek with Grok reviewing.
  `model_properties` unchanged. Every seat's model is priced, every Anthropic seat's entry carries `no_sampling` and its
  effort levels, every seat's effort is one the entry declares.
- **Routines, step 1 built (2026-10-10, patches 0111-0112; docs/ROUTINES_DESIGN.md v1.0).** An analysis kept as a
  method and run again without a model on new data, with exploration and exploitation kept apart (Palo's design: the
  only thing a person sets is the inputs before a run; a run is a record, nothing to ask; under a run's view the
  composer is disabled, back on a new thread or a favourite load). Built now - *Save as routine*: the Save pill's menu
  (Save as favourite = the rank dialog as before; Save as routine, which saves the favourite too, so the pill now
  stays on a saved chain with the bookmark filled), the promoter (one Analyst-seat call with a generic prompt that
  returns find/replace edits and inputs as JSON, never a retyped script; edits apply whole per input; `analyst/routines.py`,
  `bambooai/routines_host.py`), the dialog (name, purpose, data, inputs with "keep fixed", results with typed lines
  flagged, the next-version choice on an origin thread), run zero on the chain's data through `BambooAI.run_script`
  (the replay's path) checked by position against the kernel's RESULT records (differed = refused with the lines
  named; data gone = created unverified), the records as files beside the favourites (`storage/<user>/routines/<id>/`),
  the routes (`web_app/routines_routes.py`; the two slow ones stream the pane's rows like /submit_rank; propose is
  authorised and charged as a query on a chain id of its own), the Routines rail entry with its count and the manager
  (list, verified mark, inputs, results, versions, .py download with the INPUTS block, rename, delete, "made from the
  analysis of … ↗" opening the favourite), the favourites' cards' Routine button (grey / lit with the number of
  versions born from the analysis, in place of the v1 Replay button), and `composerLock/composerUnlock`. A run now
  records what it ran on (`Run.data`: df_id, name, source, columns, rows, aux; `ExecutorAPIClient.cache_preview`).
  Tested: the pure module and the host over a real kernel with a scripted promoter (test_routines.py, 51), the
  instance and the routes on the fake model layer (test_app_path.py), the markup (test_routines.js, test_pane.js),
  the real page with the backend faked (`tools/routines_screens.py --out DIR --light`, seven screens with state
  checks), and the end-to-end walk in both editions (the scripted scenario's promoter names the regime as the one
  input; run zero reproduces through the executor; the routine is stored, linked, listed and lit on the card). Also:
  tests/analyst/test_js_refs.py lexes the scripts instead of regex-stripping them (a regex literal holding a quote had
  turned the rest of stream-pane.js inside out, and the scan passed or failed by quote parity); a KaTeX stand-in in
  the stack's browser; a local-mode upload names its file in the DATA header. Palo's Titanic test of step 1 on dev
  passed with the real promoter.
- **Routines, step 2 built (2026-10-10, patch 0113).** *Run on current data*: the manager's Run opens the run dialog
  on the data loaded now (the Data tab's upload, Intervals.icu or Endura; the loaders in the dialog are step 4) with
  the fit line from `precheck_routine` ("fits the routine (6 of 6 columns, 2 more)" / "missing: soil - the routine
  cannot run on this data"; Run off until it fits; nothing recorded for data that does not fit - the design's
  did_not_fit status became a refusal), the inputs as widgets by type, Compare with the run before or run 0; Run
  rechecks with the typed values (a choice input's values against its column, a small script in the executor) and
  says a missing value in the dialog. The run (`routines_host.run`, `BambooAI.run_routine`, POST /routines/<id>/run
  streaming): the version's script with the INPUTS block at the mark through `run_script` (timeout 2x run zero + 2 min
  within 5-30 min), results parsed by position, status (reproduced | ran | differed | failed at cell n | timed_out -
  `run_status`, `failed_cell`), the comparison against the reference run (`compare_runs`: change, interval overlap ->
  moved / within, missing; `reference_run`: previous | zero | n), the record as `runs/v<ver>_<n>/run.json` + stdout +
  figures and a light summary in routine.json's `runs`. The view (S4): the pane's CHECK / RUN / COMPARE rows and a
  closing card (`paneRoutineEnd`), the strip in run mode, the id line, the Comparison tab first (`content-rendering`
  'comparison'), Plots / Results / dataframe through the stream, the Data tab for stored runs, "run n of N" with the
  arrows stepping through the routine's runs (run 0 included when verified; GET /routines/<id>/runs/<n>), both off
  while a run is under way; the composer locked, back when a favourite loads; the Save pill hidden. The manager:
  the results-across-runs table (a column per run, marks against the column before, sparklines) and the runs list
  (status chips, each opening the run). Found by the e2e walk and fixed: the manager stayed open under the run
  (closes when the run starts); the run dialog's Cancel stayed disabled after a run (re-enabled on open). Tested:
  test_routines.py (68: precheck, run, reference, run_view, failed, timed_out, the value check over a real kernel),
  test_app_path.py (76: precheck / run / runs routes), test_routines.js (44: dialog, comparison and data tabs, runs
  table and list, run view state), `tools/routines_screens.py` (twelve screens, dark and light, state checks), the
  e2e walk in both editions (run 1 on the same data reproduces run 0; run 2 with regime C compared with run 1; the
  arrows through runs 0-2; the composer; a copy of the file without `soil` refused with nothing recorded; the files
  on disk).
- **Five auxiliary files, not three (2026-10-15, patch 0166).** Palo ran a context routine (five files: laps, summary,
  wellness, context, codes) on a window inside a cached load: the dialog said *inside the cached load … it will be
  cut*, and the run stopped with *Maximum 3 auxiliary datasets allowed*. The limit of three dates from the first
  version, when a load brought wellness, summary and laps at most; the Intervals loader route sets the session's
  list whole and was never limited, but a run cut from the Dataset cache loads the cached frame and its files one by
  one through the cache route, which refused the fourth - so no routine with the context (four files) or with the
  context and the laps (five) could ever run from the cache, and neither could an Endura routine with all four of its
  kinds. One number now, `MAX_AUXILIARY_DATASETS = 5` in web_app/app.py, handed to the cache blueprint (`max_aux`) and
  mirrored in core.js for the page's upload button and the Dataset cache panel; the cache route also no longer counts
  a file already in the list as a new one. Proof: the integrations walk's run 3 of the context routine, a window
  inside run 1's load, taken from the cache with its four files, none refused, the CHECK row *cut to … from the
  cached load* (88 checks).
- **The dialogs' dates are the person's (2026-10-15, patch 0165).** Palo, testing on the dev box: the Intervals dialog's
  *to* date snapped to the *from* date as he changed it, and then neither could be changed. Reproduced in a real
  Chromium: a date being typed into an `<input type="date">` passes through `''` and partial values (`0009-10-15`,
  `202601-10-15`) on every keystroke, and the dialog's `change` handlers - kept from the first version, one pair added
  at every opening - clamped start and end to each other on each of them (`'' < anything`), so typing an end date
  snapped it to the start, and with both equal every edit of either was out of order and overwritten. The handlers
  are gone from the Intervals and SweatStack dialogs; the order is checked where it belongs, when Load is pressed
  (*Please pick both dates.* / *Please select a valid date range: the start before the end.*), and the empty-date
  fallback to a three-month window is no longer reached from Load. The same principle on the other rewrite: the
  plan's limit used to be fetched at every opening and written over both dates when it landed - a second or more
  on the dev box, wiping a choice made meanwhile, and never remembering a window between openings. Now
  `applyIntervalsDateLimits` (and SweatStack's) fetches once per page, puts the bounds on the inputs at every
  opening and writes a default only into an empty input - so a date typed before the answer landed stays, and the
  window chosen last time is there at the next opening. Not changed, for a decision: the default *from* is the
  plan's earliest allowed day (today - 365 on pro, today - 3650 on the local tier, which is why the dialog opened on
  2016), not a sensible working window. Tests: tests/e2e/test_date_inputs.py (8, Chromium over the dialogs' own
  functions: the old trap for the record, a date typed before the answer kept, no clamp, the reopening keeps the
  window, one request per page, both dialogs; the scripts' Load checks), test_local_day.js's call count loosened.
- **The hosted edition's store kept (2026-10-15, patch 0164).** Palo: the Nomad jobs live in the repository, under
  `nomad/jobs/` (the 0162 entry below had them outside it). The four job specifications - `bambooai-executor-free`,
  `-plus`, `-pro` and the generic one - give the executor task `volume_driver = "local"` and `volumes =
  ["bambooai-datasets-${NOMAD_META_user_id}:/app/datasets"]`: a Docker volume of the user's own, created on first use
  with the image's ownership (the same thing `bambooai serve` does, one per user), kept across dispatches, so the
  store and the loaded windows' files outlive the container; one volume per user, so a container never sees another
  user's files (a shared host folder would, and its ownership would need setting for the image's `appuser`). The
  driver line matters: without it Nomad reads a relative source as a folder inside the allocation directory (the
  documentation: "If volume_driver is omitted, then relative paths will be mounted from inside the allocation dir"),
  which goes with the allocation. **Roll-out on each box, in this order:** (1) the Nomad client's configuration gets
  `plugin "docker" { config { volumes { enabled = true } } }` if it is not there (`grep -rn volumes /etc/nomad.d/`;
  the documentation gives the default as false, and a volume driver is refused without it) and the agent is
  restarted (running allocations survive a client restart); (2) image v55 built and pushed to the box's registry as
  before; (3) the four jobs re-registered (`nomad job run nomad/jobs/bambooai-executor-<tier>.hcl`) and the running
  dispatches stopped (`nomad job status`, stop the dispatch children) so the next ones carry the volume; (4) check:
  log in and load a window - `docker volume ls` shows `bambooai-datasets-<user id>`, `docker inspect <container>
  --format '{{json .Mounts}}'` shows `/app/datasets` of type volume, the executor's log reads *Found N activities to
  process; 0 in the store, N to download*; stop the dispatch, log in again, load the same window - *N in the store,
  0 to download*. Named volumes survive `docker volume prune` (anonymous volumes only, since Docker 23) but not
  `docker volume prune --all` or `docker system prune --volumes` - never run those on the boxes. Disk: about 100 MB
  per user-year, bounded by the retention; a departed user's volume is removed by hand (`docker volume rm`). A volume
  lives on the node that made it, so a cluster of several client nodes needs a shared volume driver or a node
  constraint. The user id in the volume name is the app's file-system-safe one (the part after the provider's `|`),
  which fits Docker's volume-name rules for the ids seen. Nothing diverges from the single edition inside the
  container: the same image, the same paths; only how the volume is attached differs (`-v` in `bambooai serve`, the
  job's `volumes` here).
- **The store proved on the real executor (2026-10-15, patch 0163).** The integrations walk counts the fake API's
  calls around each load (`calls_of`): the first load fetches the 60-day window whole (the dialog's line *60
  activities downloaded*; the key's store on disk with the manifest and a file per activity); the routine's run on
  the window ending today (19 days overlap) fetches 41 FIT files, its LOAD row's fold and its record's `load.store`
  say *19 of 60 activities from the store, 41 downloaded*; the second key gets a store of its own and the first's is
  untouched; the original window loaded again with the context fetches no file and each chat once; the same window
  in a new thread fetches no chat (all older than sixty days) and the context file carries the same messages; Refresh
  everything fetches all 60 files and every chat again and the box is off after; the Dataset cache panel lists both
  stores. The fake API's call log keeps 3000 entries now (the refresh load adds up). Integrations walk 86. The stack
  walk's favourite check waits up to twenty seconds for the file: the page saves the favourite after the dialog
  closes, and in the local edition a quick run zero now lands before it (a race of the walk's, not the page's).
- **The store kept, and seen (2026-10-15, patch 0162).** Persistence: `bambooai serve` ran the executor container with no
  volume, and the container is recreated on every image change, so the store (and the loaded windows' files) would
  have gone with each executor update; `start_executor` now mounts the named Docker volume `bambooai-datasets` at
  `/app/datasets` (`executor_datasets()`; `BAMBOO_EXECUTOR_DATASETS=<folder>` in .env mounts a folder of the person's
  own instead - a named volume by default because a folder of the home is owned by the host user, whom the image's
  `appuser` cannot write for on Linux). The hosted executor's persistence is the Nomad job's volume - in
  `nomad/jobs/`, patch 0164 (this entry had it outside the repository). The app's load route passes `refresh` and the tier's `retention_days` (120 on
  the free tier, 400 otherwise) to the executor. The page: the Intervals dialog has a *Download* section with *Refresh
  everything* (off; cleared after each load) and the line *only what the store lacks is downloaded*; the load's
  success message carries `storeLine` (core.js: *91 of 101 activities from the store, 10 downloaded* / *all 101 …,
  nothing downloaded* / *101 activities downloaded* / *… fetched again*); the routine run dialog has the same box
  under the window - ticked, the Dataset cache route is skipped and the load fetches the window whole - and the run's
  LOAD row carries the phrase in its fold (the row's text is clipped at sixty characters) and its record's `load.store`
  the counts (`_load_as_said` admits that one dict; the loader route puts the same on the Data tab's load record, so a
  routine made from a chain says it too, through `loadLabel`); the Dataset cache panel lists each key's store under
  *Store* (activities, chats, span, size; shown, not loaded or removed). Tests: test_dialogs.js 33 (the option,
  storeLine's phrases, the script's hooks), test_routines.js 71 (the box in the run dialog), test_app_path.py 155 (the
  store dict on the run's record, other dicts still dropped), test_package.py 37 (the volume on the docker run).
- **The Intervals.icu store: a window is a view, only the new files are fetched (2026-10-15, patch 0161; executor image
  v55; docs/INCREMENTAL_LOADS_DESIGN.md).** Every load from Intervals.icu downloaded its window whole - a routine's run
  on a window a day wider than the Data tab's, or the Data tab's after a routine's, fetched a year's files again
  (a gigabyte, minutes). Palo's decision: the cache is checked on every load, standard or by a routine, and only the
  missing bits are downloaded. It is built where the files are fetched and parsed, in the executor
  (`containers/executor/intervals_store.py`): under the key's folder, `datasets/<user>/<mark>/store/`, one parquet
  file per activity with every metric its file had (zstd; a year 60-120 MB; a compressed pickle where pandas has no
  parquet engine - the sandbox), the chat under each activity as JSON, and a manifest keyed by activity id. A load
  fetches the window's activity list as before - it is the manifest of what Intervals holds - and takes from the
  store every activity held under the same *signature* (a hash of `icu_sync_date`, `file_type`, `start_date_local`,
  `elapsed_time`, `moving_time`, `distance`: a re-sync changes it, a rename does not), downloads the rest and keeps
  them as they are parsed, then assembles the window from the store cut to the metrics asked (so other metrics over
  the same window download nothing). The wellness log, the calendar and the subject's record are fetched fresh (one
  call each); the chat under an activity is fetched again while the activity is within sixty days or its file
  changed, and taken from the store for an older unchanged one; the request's `refresh` fetches every file and chat
  again. When a load ends, activities older than 400 days (`retention_days` in the request for a shorter tier) leave
  unless a load served them within thirty days - a routine over an old window keeps its data as long as it runs.
  Progress says what the store held (*The store holds 91 of 101 activities; downloading 10...*); the job's result
  carries `store` (window, held, fetched, refresh, the store's summary); the context report `messages_reused`;
  `/cache/inspect` lists the stores by mark. The frame, the files and the Dataset cache above are unchanged; the
  laps file is still fetched per activity (the same signature would serve it; later). Persistence is the next patch
  (the single edition's container has no volume; the hosted job's volume is outside the repository). Tests:
  tests/analyst/test_store.py (37: the pieces, and the executor's loader end to end over the fake calendar - a wider
  second load fetches ten files and reuses the settled chats, the same window with other metrics nothing, a
  re-synced activity alone, a refresh everything, the frame equal to a straight parse); the stamp checks of
  test_context.py and test_documents_app.py read v55; the integrations walk 77 over the real executor process.
- **Run zero behind the dialog; a run told its cost beforehand (2026-10-15, patch 0160).** Creating the first live
  routine over the words took nine minutes: not the promoter (36 s) and not the context - run zero, the method's
  twelve cells re-executed on the chain's data (cross-validated models and permutation tests over 1.3 million rows;
  one cell six minutes), the same cost the chain's replay had just paid. The proof stays, the waiting goes: `create`
  (`background=True`, the instance's way) stores the routine at once as *verifying* and returns a `verify` callable
  the instance runs in a daemon thread (`verify_zero`: the script with its defaults, the lines checked by position,
  the verdict - reproduced / differed / failed - written on the stored version, the output saved as `v1_0`; no pane
  rows, since a row after the dialog's stream closed would land in the next request's). The page toasts *verifying
  on the original data in the background*, follows the routine every three seconds (`watchVerification`) and says
  the verdict; the manager's card chip pulses *verifying…* or reads *did not reproduce*, the side item says so, and
  Run is disabled with the reason. The refusal creation used to give moves to the run: `zero_holds` - the precheck
  and `run` refuse while verifying (*run it when it has settled*) and for good after a verdict that did not
  reproduce (*delete the routine, or make it again from the chain*); unverified (the data gone) still runs, as
  before; the library's foreground mode keeps the old refusal for the tests. The cost said before it is paid: the
  run dialog reads *the last run took 8 min - expect about as long* (from the last run, else run zero), and the
  pane's REPLAY row *12 cells · about 7 min* from what the cells took (the session's `replay_start` carries the
  seconds). Palo's question answered on the way - the replay is not moved: it is how the Plots and Results tabs
  and the verification line are made, drawn once from a reproduction. Tests: test_routines.py 127 (background
  creation, the hold on the precheck and the run, the verdict landing, differed held for good, deleted while
  verifying, the foreground refusal kept), test_routines.js 70 (the chip states, the hold, the side item, the
  duration line), test_app_path 155 (the instance's thread, no pane rows, the route), the stack walk 104/101 (no
  ROUTINE row; the verdict waited for on disk), the integrations walk 77 (both creations waited for). docs/
  ROUTINES_DESIGN.md F1 step 4-5, S1.
- **A run's folder mirrors the recorded layout (2026-10-15, patch 0159).** Palo's first routine over the words failed at
  cell 1 with FileNotFoundError on `run_folder/datasets/local/<key>/activity_summary_….csv`: the analyst had written
  `base = 'datasets/local/<key>/'` and `pd.read_csv(base + 'activity_summary_….csv')`, and `bind_script` rewrote the
  two literals by two rules each right alone - a folder under the datasets dir to the run's folder (so a run never
  writes into the cache), a bare recorded name to this load's full path - which concatenated existed nowhere; it
  fails on the identical window too, and run zero passed because creation runs the script unbound on the chain's
  own data. One rule now: the run's folder holds a mirror of the recorded layout - every recorded path exists under it
  (`mirror_path`), filled with this load's file of that kind (the probe copies the bytes, or the frame with the
  missing columns added; the cut on a cached load lands there; a stand-in for a file the load lacks) - and the
  executed text has every literal under the datasets folder moved under the run's folder, a loader's file named with
  other dates pointed at the mirror of its kind, bare names untouched; `prepare` builds the bound and placeholder
  maps as mirror paths, keeps `sources` (recorded path → this load's file) on the record, and the prelude's
  `_routine_materialise` copies a bound file the probe did not write from its source rather than standing an empty
  table in (a bound file gone *after* the probe now runs on the probe's copy). The Data tab shows each recorded name
  against its source (a stand-in as *an empty table*; an older record by its bound path). The recorded files' folder
  is recognised even without a `datasets/<user>/` prefix (the tests' temp folders). Tests: test_routines.py 122 (the
  mirror on the later window, the stand-in, the probe failed, the file gone after the probe, the cut copies at their
  mirror paths, `bind_script` with the f-string and with folder + name, an end-to-end folder + name run),
  test_routines.js 67 (the Data tab's sources), the integrations walk 75 (the record's mirror paths and sources).
  docs/ROUTINES_DESIGN.md F2 step 3 and the cut paragraph.
- **"Today" is the local calendar day in every dialog (2026-10-15, patch 0158).** Palo's first routine over the words
  (the benchmark's predictive question, a 1.3-million-row window) re-downloaded "the same window": the chain ran on
  16 May → 14 October, the run asked for 17 May → 15 October. Both the loaders' dialogs and the routine run dialog
  took "today" from `toISOString()`, the UTC day - he loaded at 10:29 Melbourne time (23:29 UTC on the 14th) and ran
  at 11:28 (00:28 UTC on the 15th), so the run's default window ("the original's 151 days, ending today") slid a day
  along and no cached window could serve it. Every "today" on the page now goes through `localIsoDay` (core.js; the
  Intervals and SweatStack dialogs' ten uses each) and routines.js's `isoDay` reckons the same way, its window counted
  back in calendar days rather than 24-hour steps. Tests: test_local_day.js 4 (new: 10:29 in Melbourne is the 15th
  here and the 14th in UTC; no `toISOString()` left in the three dialogs), the integrations walk 75 (the run dialog's
  end is the page's local day and the Data tab's latest day; a no-passage check made specific to the chat's lines,
  since a description also sits in the summary's head). The same test thread found two more things, each its own
  patch: the run failed on a path built as `folder + name` (0159), and creation took nine minutes in run zero (0160).
- **The benchmark's context rows asked as a coach or a rider would (2026-10-15, patch 0157).** Palo, before testing
  0154-0156: the context questions of the benchmark and the testing notes "mention words like codes, context and
  others that a normal user like coach or athlete would not use ... sterile questions that already offer hints for
  the system". Right, and for this feature the vocabulary leaks the answer: a question that says *codes* hands the
  analyst the route and measures instruction-following, not whether the words are brought to bear - yesterday's
  finding (the analyst never glanced at the codes on a words question) is invisible to a question that names them.
  The mirror of C5 on the asking side. The twelve `context_enabled` rows are rewritten in the voice of the coach
  about the rider (nine) or the rider's own (three), with no word of the system's - no codes, context, passages,
  renderings, plan notes, ids - the same analytical substance (the join, the window, the judgement), and the
  12-month window named by month or by the data (*the weeks my 20-minute power jumped the most*, *the last time he
  was ill*), never "this week" (Palo: the benchmark loads a year). Under each row a comment for the scorer, never
  for the model - *key*: what a good answer must do (use the words where needed, quote rather than paraphrase, name
  a count of codes as the model's reading, a window rather than a same-day match where the days can differ, say
  what rests on what) - and the voice it is asked in; the heading's comment says the convention. The verification
  items of the testing notes stay technical (they are for the person checking the build); the questions put to the
  model follow the same standard from now on (TESTING_context_0154-0156_natural.md replaces the question lists of
  the three notes). Scanned: no system word in any of the twelve; the additions parse once line 12's `Z1: <55%` is
  quoted. No code.
- **Context, step 5: routines carry context (2026-10-14, patch 0156).** Most of F3 was there by construction - the
  two kinds in `AUX_KINDS` (1b), the run dialog waiting for the pass (0149), the replay's prelude binding `CTX` to
  whatever the run loaded, `bind_script` rebinding a literal context or codes path by kind. Three things were not:
  (1) `load_plan` kept only summary, wellness and intervals among the kinds a run's load asks for, so a routine made
  from a chain that read the words never loaded them - `context` stays, `codes` never (the pass writes them);
  (2) `cache_match` took a cached context file without the codes beside it as a hit - it now wants the codes file
  too, unless the cached context file is its header alone (`CONTEXT_HEADER_BYTES`, from the inspection's size: a
  window without words, for which no pass runs); (3) a window without words read as "the context file is empty in
  this data (0 rows); codes absent" - `shape_sentences` now says *no passages in this window (the context and codes
  tables are empty)* for the context kind and `aux_line(binding, shape)` leaves the codes out of the absent files
  there (`rt.context_empty`); the run's record keeps the binding's facts under the sentence. The stack: the fake
  calendar has a silent fortnight 21-34 days ago (`apis_data.is_silent`: no description, tag, tick or calendar entry;
  chats, rides and wellness stop at sixty days anyway); the scenario's count question (`COUNT_QUESTION`: one cell over
  `CTX.frame()` and `CTX.codes()`, two RESULT lines, a report saying a code is the pass's reading; the promoter makes
  no input). The walk (integrations 74): the same window loaded again in a new thread (the store reused, the line
  says so), the count chain's report with the count the fake calendar predicts, Save as routine (two lines, no
  input, the record's four files), run 1 on the next window (the dialog's load with the context, the pass waited
  for, the context and codes files' rows against the original's on the CHECK row, the count the calendar predicts
  for that window, compared with run 0, the one Context pill settled), run 2 on the silent window (the context file
  its header, no codes file, zeros, the sentence, no 'codes absent', the pill with no coding line). The fake API's
  call log keeps 1000 calls (the walk's loads had pushed the race calls out of 200). Tests: test_routines 120 (the
  plan, the cache with and without the codes and with a header-only file, the sentences, `context_empty`). D9 is
  moot until a run carries a narrative (the record's field is empty by construction). Live: pending; the testing
  note has the questions. Next: step 6 (the codebook screen) - or the benchmark run first.
- **The two frames described again in the Context section (2026-10-14, patch 0155).** The first thread under 0154
  (two Deep questions, one Adaptive, read against the five earlier context-phase logs) showed the trim had taken out
  a sentence that does change what the model does: with `CTX.codes()` a bare name, the analyst read the codes file
  by the path DATA lists (the thing still described) in the codes-by-week question - seven `CTX.codes()` calls
  under 0151, none under 0154 - and on the tired-legs question never glanced at the codes it had printed beside
  each candidate before; every chain of the 0151 session had used `CTX.codes()`, none of the three under 0154.
  The section now reads `CTX.frame()` (the passages, dated, with author and kind), `CTX.codes()` (the codes on
  them, with the words they rest on) - 737 characters. The same reading of the logs: `CTX.grep`, `around`, `on`
  and `text` have never been called in nine chains (the analyst does the same in pandas on the frame, with its own
  three-language patterns over `text` and `text_en` - more than `grep` does), READ CTX once, where a digest across
  many passages was wanted; the four examples stay until the benchmark's `context_enabled` rows have run and come
  out if still unused. What the thread showed of 0154 itself: nothing lost by the trim on the two re-asked
  questions; the reviewer's Words line present in both reviews with substance (a regex count read as a quoted
  classification, a denial read off a cut-off rendering, the writing day against the ride the message hangs off)
  and acted on; the post-report NARROW right. Observed, not changed: one analyst reply cut at the 16k cap with its
  reasoning in the content (flash at `xhigh`, one in 42); the Reviewer seat (grok-4.7, `high`) 3-4 minutes and
  $0.12 a review, 56% of the Adaptive chain's cost. Test: test_analyst's section check updated (210).
- **Context, step 4: the contract section trimmed, the reviewer's Words lens (2026-10-14, patch 0154).** Palo: 0152
  worked well; proceed. The two texts of docs/CONTEXT_DESIGN.md §5-6, finished by the standing rule - a sentence
  stays only if it changes what the model does. (1) `analyst/contract_context.md` from 945 to 644 characters, within
  a line of the Documents section (578): the calls listed with their arguments, READ CTX and the [C.417] citation,
  *rendered*, a code as a model's reading, the words and the numbers days apart, what an explanation rests on. Out:
  *a count of codes is a number like any other* (a question that asks for counts gets them), *you write in English*
  (the question and the contract are), the frames described (their columns print), *mapped in DATA* (the map is
  there). (2) The map's closing line had repeated three of the section's rules in other words, both texts in every
  prompt with context; the line now says only what is true of this data and nowhere else - a plan_note is dated
  the day it was planned for (the sentence 0152 added, live-proven on question 7). (3) The reviewer's sixth lens,
  *Words*, present only with context: `reviewer(context)` in session.py fills the three places `reviewer.md` leaves
  for it (the count of lenses, the bullet after the question's frame, the line in the format) from
  `REVIEWER_WORDS_LENS`; without context the brief is byte-identical to before (`REVIEWER = reviewer(False)`); the
  review call passes `reviewer(self.context)`; `_REVIEW_LENSES` gains `Words`, so the line is parsed, dropped when
  it says nothing, and rides to the analyst after the other five when it found something. The lens asks whether an
  explanation of a number by the words rests on passages quoted, on counts of codes or on the analyst's reading and
  is reported as such, and whether the days were compared with a window rather than matched by day. The scanner
  covers the six-lens brief. Tests: test_analyst 210 (the section's size and phrases, the brief with and without
  context, the parser, a run with context calling the reviewer on the six-lens brief); test_app_path and the
  integrations walk pin the map's new closing line. Step 4's field trial is the benchmark's `context_enabled` rows
  (0153) in Adaptive mode, pending Palo's first run. Next: step 5 (routines carry context).
- **The benchmark gains a `context_enabled` heading (2026-10-14, patch 0153).** Palo re-evaluates the system with
  `benchmarking/20251125_task_eval_BambooAI.yaml` after major updates; its headings under each category encode the
  question's type (`coach_athlete`, `technical`, `search_enabled`). A fourth, `context_enabled`, now sits under every
  category - twelve questions that mix the words with the numbers, one per category and two each under Workout
  Structure (plan versus done; a pacing instruction against the quarters ridden) and Recovery (an illness window
  aligned on the day of the words; weekly fatigue words against load, lagged both ways). Each takes the design's
  shapes in turn - numbers first (the week the 20-minute power jumped, what was written either side; a coach's
  comment grouped by tone against the ride's metrics), words first (passages per month by kind and author beside the
  volume; days coded fatigue against the HR at fixed power bins and the diary's ratings; named routes against GPS
  clusters), both at once (planned repeats against the intervals detected in the 1Hz data; `conditions` passages
  against the sensors; context features added to a power model) - at the benchmark's pitch (joins, 1Hz
  computations, a judgement at the end), written window-relative rather than for 2025, since the words live on a
  coached account. Datasets name the two files as `context_notes` and `context_codes`; the entries are unevaluated
  (`able_to_solve: null`, score 0) like the categories after the `# FINISHED HERE` mark; a two-line comment at the
  first heading says what the heading means. The file is read by people, not parsed (line 12's `Z1: <55%` already
  breaks strict YAML); the additions parse once that line is quoted. No code, no tests changed.
- **Context: the store keyed by the athlete, one Context pill, a plan note's date (2026-10-14, patch 0152).** Palo's
  test session on 0149-0151 (the nine questions of TESTING_context_0151): the coder at `none` read 63 new passages
  of an overlapping window in four parallel calls of 6-11 s for a cent - reuse works - and five analyses ran on the
  words. All five read as the design intends: *tired or heavy legs in August* found four days, 13 August included,
  the Danish quoted with the rendering marked and the translator's bracket named, a stricter count beside the
  inclusive one; *codes by week against load* used `CTX.codes()` joined to the summary, said a code is the model's
  reading and dropped the proposed rows; *the week power dropped* found the week by a stated rule and quoted both
  authors (and noticed the coach's "Heat session" note is eighteen identical copies); *instructions versus what was
  done* joined the `instruction` code to `workout_compliance`; *was he ill* set the platform's flag, the words and the
  numbers side by side with the crash as the competing cause. Costs $0.07-0.19 and 4-10 minutes a question on flash
  in Deep mode - the analyst's turns, not the context's. One misreading to fix at the source: the analyst took plan
  notes dated the day of the ride as written that day ("descriptions, not prescriptions"); a plan note's date is the
  day it was planned for, and the map's closing sentence now says so. Palo's concern - the store of coded passages
  is per user, so a coach switching athletes would meet the wrong store: as built the store was per key mark, which
  is per athlete when each athlete has a key, and its entries are keyed by Intervals' global ids with the text hash,
  so one athlete's words could never stand in for another's; still the structure should say what it is - the store
  is now under `storage/<user>/context/<athlete id>/` with the id the job's context report carries (the key's mark
  only without one), so a regenerated key keeps it and a future coach-key flow is safe (the stores made by 0149 under
  the key mark are orphaned and re-coded once, cents). Palo's ask: two pills for one thing wasted the bar - the
  context and codes files now stack under **one Context pill** (`contextPillAdd` / `contextPillSettle` in
  intervals.js, the dialog, the run dialog and the Dataset cache all routing through it): the days and a spinner
  with *coding…* while the pass runs, a hover list with Passages and Codes (each a click to the Data tab's preview,
  `showDatasetPreview` factored out of the pill click) and the pass's line once ended, the x removing both files
  (`removeDatasetPill` defers to it, so a run's load clears both). Tests: test_context_pill.js 8 (new),
  test_app_path.py 155 (the athlete-keyed store), integrations 66 (one pill, its list, the preview, the store under
  the fake subject's id). Observed, not changed: repeated identical plan prose inflates code counts (the heat
  protocol carries `body`, `hydration` eighteen times) - a count of repeats in the map is a cheap step-4 candidate.
- **The Reader and the Coder on DeepSeek flash in every tier (2026-10-14, patch 0151).** Palo's second live pass on
  0149+0150 (223 passages, twelve batches of twenty, six in flight, all twelve answered whole, no second round):
  2.4 minutes behind the load, $0.15 - the calls 28-80 s each because his config still ran the Coder at `low`
  (the log's `reasoning_effort`), where flash spends 2-10k tokens thinking per 1.5k of reply. At `none` the pass
  should be ~30 s and a third of the cost; a config built before 0149 needs the seat set to `none` by hand or a
  rebuild. The renderings are there (141 of 223: da 86, no 55 - the coach writes Norwegian) and faithful on a
  sample of twenty read against their originals; C.64's "benene meget" came out as "very [heavy]", the coder's
  inference bracketed, and coded fatigue; the Reader quoted the renderings in English in 3 s; the report cited
  [C.52] and [C.142]. Labels on the same sample: sensible, with `body` (47) and `hydration` (24) carried mostly by a
  heat block (core temperature, weight before and after, "drink 500 ml") - defensible; `race` and `treatment`
  proposed, both real gaps in the seed; tone almost never `negative` (4 of 223) - the rider writes upbeat. The first
  question of the session was asked while the pass ran and DATA said so. Palo's ask: the Reader and the Coder on
  flash in the performance and max tiers too (Claude there would be slow and dear for quoting and transcribing) -
  the template now says so. Seen for the next image bump: a plan note whose step lines are bare "2x" survive the
  stripper (C.159 "Hard TT session: 2x / 2x / 2x / 2x").
- **The dispatcher's reasoning-model list on the non-streaming path (2026-10-14, patch 0150).** The first live pass
  on 0149 failed on every call: `'ModelManager' object has no attribute 'reasoning_models'` - the list lives on the
  BambooAI instance (bambooai.py computes it for the stream and passes it in), and 0149's `llm_call` read it off
  the manager. The unit test had planted the attribute by hand, and the stack's scripted provider had no
  `set_call_reasoning` hook, so the branch never ran in a walk. Now `llm_call` reads the list off
  `model_properties` itself (capability `reasoning`, the same rule), the test plants nothing, and the stack's
  provider takes the hand-off (`harness_models.set_call_reasoning`, recorded) so every walk runs the branch.
- **Context: the coder behind the load, in parallel, reasoning off, remembered per subject (2026-10-14, patch 0149).**
  Palo's first pass on 0148 took seven minutes for 120 of 223 passages and the dialog gave up at five: six calls of
  65-80 s, each at the 16k reply cap, **three of them empty**. Root cause, from the log: the non-streaming path
  (`ModelManager.llm_call`) sent no reasoning effort, so DeepSeek flash reasoned at its default depth and spent the
  whole budget thinking - the Reader and the Promoter had paid the same tax unseen - and forty passages with
  renderings overran the cap; the retry doubled it. Four changes, each where its cause is. (1) `llm_call` resolves
  the seat's effort as the stream does (`_effective_effort`; a caller may lower it) and hands it with the
  reasoning-model list to the provider on the per-thread channel (`set_call_reasoning`); OpenRouter builds the same
  `reasoning` body the stream sends, Anthropic shapes `request_params` with the effort; the Coder seat runs at
  `none` on flash (declared) and `low` on sonnet/opus. (2) `bambooai/context_host.py`: batches of twenty (8,000
  characters), six calls in flight (`ThreadPoolExecutor`), validation in batch order so a proposal is usable by the
  next batch, and a second round only for the passages no reply answered - a failed batch or the tail of a cut
  reply - instead of a blind retry of the batch. (3) The load no longer waits: `_coding_start` in the Intervals
  route starts the pass in a thread after the instance is set up and completes the load at once with
  `result['context']['coding'] = {status: running}`; `GET /intervals/context_coding/<job_id>` says where it is; when
  it ends the codes file joins the session's files (the instance's list assigned, which drops its frames) and a
  completion read again puts it back; the page (`pollContextCoding`) keeps a spinner and *coding…* on the context
  pill, then names it plain with the line as its tooltip and gives the codes file a pill (`Context (59 days)` /
  `Context codes (59 days)`, the Dataset cache naming them the same); DATA says *the coding pass is still running*
  while it does; a routine's run waits for the pass in the run dialog (its counts depend on the codes). (4) D1
  decided the other way: `analyst/coded.py` keeps the coded passages per user and key mark
  (`storage/<user>/context/<key mark>/coded.json`, kind:source_id with the text hash as the guard, the rendering,
  codes, coder and codebook version on each entry, the newest 6,000 kept); a load reuses what the store holds and
  codes only the new passages, so the full pass happens once per subject - the line says *180 already coded by an
  earlier load*. Expected on the Danish window: ~30-40 s in the background on flash the first time, seconds after.
  Considered and parked: a typed-choice classifier (OpenRouter's Jev) for the codes half - fast and nearly free, but
  it gives neither the rendering nor the quote; the twenty-label precision check decides whether it is ever
  wanted. Tests: test_vllm_adapter.py 24 (the effort on OpenRouter's llm_call and through the dispatcher),
  test_anthropic_adapter.py 18, test_coder.py 29 (the store), test_app_path.py 154 (the parallel pass with a second
  round, reuse on a second load, a changed text re-coded, the route's start/running/done/read-again/skipped states),
  integrations 65 (the pass followed on the page; the store written). The billing decision stands (one query per
  load with context).
- **Context, step 3: the codebook and the coder (2026-10-14, patch 0148).** The words beside the data are now read once
  by a model at load (docs/CONTEXT_DESIGN.md §3.2, §3.3, §4 F1, §6, §13). `analyst/codebook_seed.json` (data, outside the
  C5 scanner): the design's 36 English codes in six groups with their definitions. `analyst/codebook.py`: the user's
  book under `storage/<user>/context/codebook.json`, seeded on first use, the vocabulary as the coder receives it
  (`code: definition` lines, proposals last and marked), proposals stored as `proposed` with proposer, date and an
  example passage (no version bump), the coach's decisions for the codebook screen of step 6 - `confirm` (as it is,
  renamed, or merged into an existing code; the version bumps), `decline` - and the last load's `uses` per code.
  `analyst/coder.py` (scanned): batches of forty passages or 12,000 characters; the Coder's messages (the template
  says the work and the JSON-lines format - codes, tone, the words each code rests on verbatim, lang, text_en for a
  passage not in English, a proposal at most once; the vocabulary and the passages ride as data); the parse of a reply
  (lines, an array, fences, a cut reply kept to what parsed); the mechanical validation - a code outside the book
  without a proposal dropped, a quote not verbatim dropped (the Reader's whitespace rule), one tone of four or
  neutral, an English passage's rendering discarded, a missing or implausibly short rendering counted, duplicate and
  unknown ids counted. `bambooai/context_host.py`: the pass - the file read back, each batch called on the Coder seat
  (`_coder_seat`: 'Coder' when the config has it, else the Reader's), one retry, the renderings written into the
  context file, the codes file written beside it (`context_codes_<window>.csv`, the design's columns, the coder and
  the codebook version on every row), both through the executor's existing upload route (the key's folder sent as the
  user id - no image change), the proposals and uses into the codebook; the report. The load route holds a completed
  job as 'processing' with *Coding the context: batch k of n…* while a thread of the app codes (`_coding_step`),
  authorised and charged as Save as routine's call (`can_execute_chain`, a billing chain, `charge_for_completed_query`;
  a refused account loads uncoded with the reason in the line), remembers a finished pass for an hour so a poll in
  flight cannot restart it, and lets the completion through with the codes file among the auxiliary files and the
  pass under `result['context']['coding']` / `coding_line`; the dialog's line appends it (*201 of 212 coded, 180
  rendered into English, 2 codes proposed*). The map's codes line now says "k of 36 codes used" (the user's book).
  The `Coder` seat in every tier of the template (flash / flash / sonnet / opus, effort low, 16k). The stack's
  Intervals scenario scripts a Coder from a lexicon over the fake calendar (renderings for the Danish and Norwegian
  lines, one proposal `coach_flag`), its Reader quotes a rendered passage first, and the walk checks the files, the
  codebook, the dialog's line, the map, and a chip whose hover shows the rendering with the original beneath (64).
  Found on the way: `contract_context.md` (0146) was missing from pyproject's package-data - an installed edition would
  have failed at import; both new files are listed now and test_analyst checks the list against the folder.
  Not done here: the pane card of §F1 (a load has no chain; the dialog's line carries the report - the design says
  so now); re-coding a cached window (step 5 territory); the codebook screen (step 6). Tests: test_coder.py 24 (new),
  test_app_path.py 149 (the pass end to end on a local instance with a scripted Coder - the files, the book, the map,
  a failing batch; the route's step - the hold, the thread, the enrichment, the in-flight poll, the refused account),
  test_analyst.py 207 (the scanner over coder and codebook; the packaging check). **For the live check (step 3's
  acceptance): twenty labels of one window read against their passages, and twenty renderings against their
  originals, by Palo - the first measure of the coder's precision, before anything is tuned.** The hosted billing
  decision - a load with context counts as one query - is easy to change in `_coding_step` if Palo wants it free.
- **Context: a passage named by its bare id is a citation too (2026-10-14, patch 0147).** Palo's first run on 0146 (a
  Danish rider's 90 days; *what did the rider write about tired legs in August, and on which days*; DeepSeek v4.1
  flash, 14 turns, $0.08) exercised step 2 where it reached: the Context section and the `READ CTX` row in the
  contract, `CTX` alive from cell 1 and used in all twelve cells (`CTX.frame()` then pandas, with the model's own
  Danish and English word lists - the better route while `text_en` is empty), the quotes verbatim (checked against
  the printed passages), original Danish then the model's rendering marked *rendered*, the day written kept apart
  from the day of the ride. Not exercised: READ CTX and the `CTX` calls (cells did the work), and the chips - the
  report named every passage *C.39 - written 2026-08-04* and cited `[cell 9]` beside, never `[C.39]`, so no chip, no
  hover, no guard resolution. The fix meets the model where it writes: `report.named_units` reads the bare ids
  (outside brackets and code, a full stop allowed after); the session counts a bare id as a citation only where it
  resolves (its passage is evidence) and discloses only a bracketed id that does not, so a stray "C.3" in prose is
  nothing; the host resolves the report's cited passages at report time (`_cited_passages`: place, quote clipped to
  300 characters, the original beneath a rendering) and sends them as `pane_passages` before the answer renders;
  `paneCiteHtml` makes a chip of a bare id when the passage is known (a READ returned it or the report's passages
  arrived), outside code and pre, the bracketed forms as before. The stack's context report names the quoted
  passage bare in its heading and a neighbour never READ, and the walk checks three chips with their hovers. Also
  seen in the run, not changed here: RESULT lines with "95% CI +3 to +4" on a census count (the model put a
  definitional range in the interval slots and said so in the report - a sentence for step 4's trim); the model's
  reading of one Danish idiom as a clipped adjective (step 3's rendering, and a Danish eye); the subject's name on
  message rows only (events, notes, tags carry the id alone - fill from the athlete record with the next image bump).
  Tests: test_read.py 69, test_app_path.py 137, test_pane.js 49; integrations 59.
- **Context, step 2: `CTX` in the kernel, READ CTX, the passage cited as [C.n] (2026-10-14, patch 0146).** The
  words beside the data are now reached the way documents are (docs/CONTEXT_DESIGN.md §5, 5.1). `analyst/context.py`
  gains the kernel object: `kernel_api_source(notes_path, codes_path)` defines `CTX` over the loaded files -
  `frame()` (the table with a `day` column), `codes()`, `grep(pattern, kind=, author=, original=)`, `around(date,
  days=3)`, `between(a, b)`, `on(activity_id)`, `text('C.417')` (the original beneath a rendering) - printed as
  lines `[C.12] 2026-08-14 · activity_message · subject: …`, frames on `as_frame=True`; the host's kernel prelude is
  now the documents' prelude and the context's joined (`_kernel_prelude`, `_documents_prelude`,
  `_context_prelude`), run as before. READ over the context: `parse_context_scope` reads `READ CTX <what>`,
  `READ CTX 2026-08-01..2026-08-31 <what>` (also `to`, `->`, `-`) and `READ C.120-160 <what>` (a stretch without a
  question is read whole, oldest first, up to one call's worth); `reading.read_context` turns the table into
  units (`passage_units`: the rendering as the text, the original kept, `where` = day · kind · author, *(rendered
  from da)* when the text is a rendering) and runs the same BM25 selection, Reader call, verbatim check and digest
  as a document read, under `[C.n]` ids, with a footer naming `READ C.a-b` and the `CTX` calls; a one-word
  passage (a tag) is a candidate. `BambooAI._read` dispatches by the scope; `_unit_text('C.n')` gives the report
  guard the passage's English text; the guard's `UNIT_REF_RE` accepts `[C.n]` and names the store a missing id
  belongs to ("not in the context loaded"). The contract's Context section (`analyst/contract_context.md`, 945
  characters - the trim to ~600 and the reviewer's lens stay step 4) is joined by `Session(context=True)` after
  Documents, with the `READ CTX` row; the host sets the flag from the context prelude. The page: `[C.417]` in the
  Answer and the Simplified view is a chip (`paneCiteHtml`, `.cite.ctx`, styled as the documents' chip - the prefix
  tells them apart) whose hover shows the passage's day, kind and author with the verified quote and, beneath a
  rendering, the original (the READ's pane event carries `original` for rendered quotes); the click opens the
  Investigation tab at the READ that quoted it. That tab had never rendered READ turns (a documents-phase gap):
  `analyst/render.py` now shows a READ as a step - *Read the context* / *Read a document*, the query as its
  peek, the digest in the fold, the ids it quoted as `data-units`, which is what the chip's click lands on. The
  stack's Intervals scenario gains a context question (a cell over `CTX`, `READ CTX` through the scripted Reader,
  the report quoting the passage and citing it; the plain-language version keeps the chip); the integrations walk
  asks it (59) and the dialog's dates are now set after the subscription limits land (`set_window`: the async
  limits had overwritten the window once). Tests: test_read.py 68 (the scopes, the units, the digest, the
  originals, the empty cases, the session with context, the guard, the notebook view), test_analyst.py 206 (the
  section, the scanner over it), test_app_path.py 134 (the prelude run in a kernel, the five calls, `_read`,
  `_unit_text`, the pane event, the frames read once per load - `auxiliary_datasets` is a property whose setter drops them,
  since every load assigns the list), test_pane.js 47 (the chip, the hover, the Simplified view's chip). Still from
  the live run: an English grep over Danish passages finds little until step 3 writes `text_en`.
- **Context: the coaches told by the plan; minute marks in step lines; image v54 (2026-10-14, patch 0145).** Palo's
  first live load (a Danish rider's 90 days: 223 passages - 133 messages, 61 plan notes, 9 notes, 8 status entries,
  7 tags, 4 custom fields, 1 description; the map and the file's DATA entry as designed; the analyst read the file
  with pandas and grepped it for fatigue words, which is the use the design intends before `CTX` exists) showed
  every coach as `other`: the activity chat's members carry neither a COACH role nor a coach flag on that account.
  Now a coach is also whoever created the planned workouts (`WORKOUT` / `PLAN` events) and is not the subject -
  the plan's author is the coach on every coached account - and the job's report carries `coach_ids` and
  `chat_roles` (what the chat showed) for the next diagnosis. Step lines with minute and second marks
  (`5x20' @ 300w`, `30" all out`) are structure too. test_context.py 33. One more thing the run showed, for step 3:
  the analyst's grep for "fatigue" found one passage in 223 because the subject writes Danish - the English
  rendering (`text_en`) is what makes the words searchable.
- **Context, step 1b: the app side - the kinds, the map in DATA, the dialog's option, the fake Intervals.icu and
  the walk (2026-10-13, patch 0144).** `analyst/routines.py` `AUX_KINDS` gains `context_notes_` → `context` and
  `context_codes_` → `codes` (a routine's plan binds them like the summary file; a cached frame's load record lists
  them). `analyst/context.py` (new, pure; in the C5 scanner): the two files as frames (`read_context`, `read_codes`)
  and the map of docs/CONTEXT_DESIGN.md §3.4 (`context_map`: the span, the passages by kind with the authors of the
  messages and notes, the roles, private entries, the months, languages once coded, the codes line with the
  counts, the uncoded and the proposed, the closing sentence; "no passages in this window" for a file without
  rows). `BambooAI._auxiliary_block` lists a context or codes file as its path, columns and row count - never its
  rows, which are text - and appends the map (`_context_map`, `_context_file`: from the executor through the new
  client method `read_aux_dataset` in api mode, read here otherwise). The Intervals dialog has a fourth option,
  *Context (notes, messages, calendar)*, on by default; the pill reads `[W+S+C]`; the dialog's success line carries
  the context's report (`contextReportLine`: the passages by kind, the failed calls) and stays six seconds. The
  stack's fake Intervals.icu serves `/athlete/0`, `/athlete/0/events` (the category filter validated as the live
  API does), `/chats/{id}`, `/activity/{id}/messages`, from a calendar of words deterministic in the date
  (tools/stack/apis_data.py: Danish and English lines by turns, the coach's replies and private notes, tags,
  ticks, a sick span, a race with HTML, a hidden note, the plan's prose, wellness comments, the `Sickness` select).
  The integrations walk (54): its routines part loads without context (the option set off, so its [W+S] checks
  stand - the summary's new ride-only columns changed one CHECK sentence) and ends with a context load - the pill,
  the dialog's line, the file's kinds, roles, times, the private flag, the sick span's inclusive end, the race's
  HTML stripped, the plan's prose joined to its activity, the ids, the empty `text_en`/`lang` - and a run whose turn-1
  prompt shows the file as columns and a count, the map, and no passage. test_app_path.py 125 (the DATA block with a
  context file, with the codes file, with an empty file; the kinds; the cached record), test_shell.js 67 (the
  dialog's option, the pill letter, the report line). Not yet: `CTX` in the kernel, READ CTX, the coder (steps 2-3);
  a cached window loaded before this patch has no context file beside it, so a routine's run that wants context
  re-downloads the window (the design's "context fetched alone for a cached window" is a later step).
- **Context, step 1a: the executor fetches the words and writes the context table; image v53 (2026-10-13, patch
  0143).** `containers/executor/code_executor_api.py`: with `context` among the load's auxiliary kinds the Intervals
  job fetches the subject's record once (`GET /athlete/0`: id, time zone, the tick wording, the custom items), the
  calendar once (`/athlete/0/events`), one activity chat's members (the coaches), and the messages of every activity
  whose `icu_chat_id` is set (one call each; the probes showed the flag null exactly when nothing was written), and
  builds one row per passage - `fetch_context_rows`: kinds `activity_message` / `activity_private_note` (type TEXT /
  NOTE, deleted and system messages dropped, dated in the subject's time zone), `activity_note` (a description that
  is not only a workout structure), `wellness_note` (the day's comment, off the wellness JSON kept with the frame:
  `fetch_wellness_data(with_records=True)`), `day_note`, `plan_note` (a planned workout's prose with its name as
  prefix, the step lines removed - `plan_prose`; joined to its activity through `paired_event_id`), `status` (sick,
  injured, holiday, races, season start, target; `end_date` inclusive - the API's is exclusive), `tag` (activities
  and events), `coach_tick` (the value with its wording, the defaults when the record has none), `custom_field`
  (text and select items of the wellness form and of activities, under `content.code`). HTML stripped
  (`plain_text`), ids `C.1..C.n` by day, time, kind; columns of docs/CONTEXT_DESIGN.md §3.1 (`text_en`, `lang` empty
  until the coding pass). Written as `context_notes_<start>_to_<end>.csv` beside the other files in the key's folder;
  the job's result carries a `context` report (passages by kind, calls, the failed calls as sentences - never fatal
  to the load; a window without words is a file with no rows). The activity summary gains `description` (plain
  text), `tags` (joined by |), `coach_tick`, `paired_event_id`, `chat_id`. New route `/file_utils/read_aux_dataset`
  (a file under datasets/ whole, 8 MB cap) for the map and the coding pass. `EXECUTOR_BUILD` v53 - rebuild and roll
  out. tests/analyst/test_context.py (31): the pure pieces and the builder over canned API shapes, the failure
  states, the summary's columns, the file's name, the route. The app side (the kinds, the map in DATA, the dialog's
  checkbox, the pills) follows as 0144.
- **Context, the design (2026-10-13, patch 0142; docs/CONTEXT_DESIGN.md v0.1, docs/INTERVALS_CONTEXT_INVENTORY.md).**
  The next phase: the words written beside the data - what the subject wrote under a session, what the coach
  answered, the day's note, the plan's wording, an illness logged - as data with provenance, so an analysis can set
  numbers against words and say what rests on which. The seed was a mixed-methods conversation Palo brought (three
  shapes of inquiry, two parameters, the joint display, four traps); the facts are the live Intervals.icu OpenAPI
  specification (117 endpoints, diffed against a 2025 copy: chats, `GET /athletes` with the coach's `icu_notes`,
  training availability, the `PLAN` category are new) and two probes of real accounts with a read-only script
  (`intervals_probe.py`, in the delivery folder): the words are under the activities (two short messages a session
  between the subject and the coach, Danish, Norwegian, English), descriptions and wellness comments are nearly
  empty, the scales and plan-versus-done are complete, custom fields and tags are a coach's own vocabulary already
  in use. Decided with Palo: one long context table of passages and a second table of codes (the model's reading,
  each with the words it rests on), an enforced English codebook seeded with 36 codes that grows by stored
  proposals; the model never reads the whole corpus in the analysis - filters and grep are free, codes make reading
  unnecessary, READ CTX quotes, the one coding pass runs once per load on a cheap seat; everything the model writes
  is English, a passage in another language rendered once at load and quoted as a rendering; labels not persisted
  (re-coded per load, cents); the shape of an inquiry chosen by the question, never by the app (checklist C2); the
  seed's coaching rules kept out of the contract (open decisions D8, D9). Build order of seven steps in §11; step 1
  (the executor's fetch and the context table) follows as 0143.
- **Stripe after PR #63: the SDK pinned, the webhook credits a paid session only (2026-10-13, patch 0140).** PR #63
  (brandonphelps1212, a change written by the ApiPolice tool; one deleted line, merged from the command line before
  this patch) took `payment_method_types=['card']` out of the account-credit Checkout create call: Stripe API
  2026-09-30.endive removed the parameter (a 400 if sent) and stripe-python 16.x pins that version, which an
  unpinned `stripe` in requirements.txt gets on any fresh install. Two consequences handled here: `stripe>=16,<17`
  in requirements.txt, so the SDK moves by decision; and, since the methods Checkout offers now come from the
  Dashboard rather than the call, the webhook credits a `checkout.session.completed` only with `payment_status`
  `paid` (a card), acknowledges an `unpaid` one (a bank debit, a voucher - delayed methods) and credits it on the
  later `checkout.session.async_payment_succeeded` - the endpoint in the Dashboard has to send that event too, or
  the Dashboard keeps to cards and wallets. The deprecated `stripe.error.` spelling of the signature error is the
  plain `stripe.SignatureVerificationError` (every 7.x+ SDK). Hosted edition only: the self-hosted one imports no
  stripe. test_app_path.py 120: the routes on a test app with Stripe faked - the create call's keywords, the
  minimum, the four webhook cases.
- **The Answer tab's measure 92ch (2026-10-13, patch 0139).** The report's reading measure was 76ch (2026-09-08),
  which on a wide screen is half the pane; it is 92ch now, the pills container with it. The measure stays a
  measure: a cap on prose width, not a stretch to the pane.
- **Ask about a plot: the picture reaches the analyst (2026-10-13, patch 0138).** The plot's chat button had sent the
  picture with the question since v1, and `pd_agent_converse(image=)` never used it; the config's `multimodal` flag
  was read nowhere. Now the figure rides with every analysis turn as an OpenAI image part in the user message
  (`_llm(image=)`, `Session.run(image=)`, `FIGURE_ASKED_LINE` in the prompt) when the analyst seat's model is
  flagged `multimodal: "true"`; otherwise the question goes alone and the pane says the model does not take images.
  The OpenAI-compatible adapters pass the part through; Anthropic converts it to an image block, Gemini to inline
  data, Ollama to its `images` field, the local text formats drop it; the run log keeps a placeholder; the prompt
  viewer shows the text with a line for the picture. test_app_path.py 113, test_anthropic_adapter.py 17,
  test_ollama_adapter.py 31; the stack walk asks about plot 1 (its harness model flagged multimodal) in both
  editions.
- **The Plots tab: the figures in order, sized to the tab (2026-10-13, patch 0137).** Two things seen on the first
  routines with figures. A run's figures came back shuffled - the capture patch named each Plotly file `figure_<id(fig)>`
  and both executors read the files sorted by name, so the order was the order of the figures' addresses; with an
  address reused, one file overwrote another and a figure was lost (the executor test shows four figures come back as
  three on the old patch). The file is now numbered in the order shown (`figure_000_<id>`), the executors unchanged.
  And a Plotly figure drawn while its tab was hidden took Plotly's default width - every run opened on a plot filling
  half the tab: `activateTab` resizes the tab's plots when it shows them (as `liveComeBack` already did), and a plot
  is appended with `insertAdjacentHTML` rather than `innerHTML +=`, which had re-parsed the earlier plots into static
  copies. test_executor_kernel.py 11, test_shell.js 64; the stack walk checks chain 1's plot order.
- **A frame from the Dataset cache keeps its own load (2026-10-12, patch 0136).** A routine's run that reused a cached
  Intervals window left the instance's load record as `{source: cache}`; the next chain analysed on that frame
  recorded it so, the routine made from the chain got a plan that read *file*, and its run dialog offered an upload
  in place of the window. `_data_record` now records a cached frame with the cached frame's own load from the
  executor's metadata (`_load_of_cached`: source, window, metrics, auxiliary kinds, key mark; `cached: true`), and
  `load_plan` reads an older record whose load says "cache" by the data's own source. test_app_path.py 110,
  test_routines.py 117; the integrations walk 48 (a chain on the window a run took from the cache, a routine from it,
  its dialog offering the window - the walk fails on the old code as the live dialog did).
- **The computation path; the next-version dialog (2026-10-12, patch 0135).** The first live test of the next-version
  choice: an hour-of-day chain on one window, saved as a routine and run on another window (the run's load replaces
  the app's data), then a temperature follow-up on the first chain, saved as a new routine - and refused. Two causes.
  The follow-up had gone on in the warm kernel, with `df` and the names of the earlier window while the DATA block
  described the new one (it reloaded by luck); and a routine's script is the whole path, so run zero re-ran the
  hour-of-day cells on the new window and their line that joins the summary file with the frame could not reproduce.
  Now the path's **computation** is the part that ran on the run's data (`Notebook.computed_cells`, by the frame's id
  on each run's record): a follow-up asked after the data changed starts in a fresh kernel on the data loaded now
  (`_kernel_for` checks the tip's data; nothing of the earlier chains is rehydrated), its ledger keeps them as
  context marked *On other data (…): its numbers are that data's; its cells 1-6 are not in the kernel (SHOW n
  re-opens one from the record)* without the names line, cell numbering continues, and its replay, its figures
  step and a routine made from it use its own cells (the proposal's notes say what it continues); the run's data
  record is set at creation (`Session.run(..., data=)`). *The same data* is the same frame or the same data loaded
  again under a new id - the same name, rows, column names, period and loader details (`notebook.same_data`,
  `data_signature`): an upload gets a fresh id each time, so a favourite continued in a new session with its file
  uploaded again is rehydrated and continued as before, and run zero counts its data as loaded; the frame's id alone
  decides whether the warm kernel is kept (`_same_frame`). An earlier chain without a record counts as on the same
  data; a cache load keeps the frame's id. The dialog: the chain's
  own routine defaults to its next version (the Name field the routine's), a later chain of the thread to a new
  routine ("A routine was made from an earlier chain of this thread"); the button, the note, the What-changed line
  and the Name follow the choice (`build.versionState`, `syncVersionChoice`); the request's choice is final
  (`create_routine` no longer falls back to the proposal's routine); a next version keeps its name unless another
  was typed. Housekeeping: a refusal is logged in the terminal; a promoter reply cut with nothing but reasoning is
  asked once more (the person's own retry had succeeded on the same prompt); a numbers default written as text in
  brackets is read; the cost tier's Promoter at medium effort. README (follow-ups), DESIGN_CHECKLIST A4,
  ROUTINES_DESIGN F1.1-F1.3 and §11.4. test_analyst.py 205, test_app_path.py 108, test_routines.py 116,
  test_routines.js 66; the stack walk 102 hosted / 99 local (another file loaded, a follow-up on chain 1; the same
  file uploaded again, a follow-up continued).
- **Routines, step 4: the retirements (2026-10-11, patch 0134).** The v1 way of running a chain again is gone, as
  ROUTINES_DESIGN.md §10 said it would: `web_app/replay_routes.py` (`/storage/replay_favourites`, `/load_replay`),
  `chain_replay_utils.py`, `workflow-replay.js` and its tag, the replay view in workflow-modal.js with the modal's
  state snapshot (it served nothing else), the replay rules in dialogs.css and the pill's `.replay` states, the
  replay storage handler in query-processing.js; `/query` reads no `user_code` or `dataset_mappings` and carries
  neither canned sentence; `pd_agent_converse` has no `user_code` or `replay`. *Edit and run* on the Code tab went
  with it: Copy and Download (.py, named after the question's first words) in place of Edit, Discard and Execute,
  and CodeMirror's four CDN tags leave the page (the stack's vendor entries and stub too). The kernel's own
  `_user_code` (delve/kernel.py) is unrelated and stays. test_shell.js 61, test_dialogs.js 30, test_app_path.py 99;
  the stack walk 95 hosted / 92 local (the Code tab: Copy puts the script on the clipboard, Download names the file).
- **Routines, step 4: the Dataset cache's pick in the file dialog (2026-10-11, patch 0133).** A file routine's run
  dialog offered an upload or the data loaded now; a file the person had uploaded before sat in the executor's cache
  with no way to run on it. Now a third choice, *A file from the Dataset cache*, with a select of the cache's file
  frames (name · rows · the day, newest first), shown once `/routines/cache_files` has answered with any
  (`analyst.routines.cached_files` over the executor's listing: a loader's frame is not a file; the route answers an
  empty list without an executor or when the listing fails - never an error, so the local edition's dialog keeps the
  choice hidden and the page makes no failing call). The pick goes through `/cache/load_primary` as a cached window
  does, clears the primary only, the pill as an upload's; the LOAD row and the Data tab's *Loaded as* read *from the
  Dataset cache*; the record's `load` is `{source: file, name, cached: true}` and its name the file's. ROUTINES_DESIGN.md
  F2.1, §11.4. test_routines.py 111, test_app_path.py 96, test_routines.js 63; the hosted walk 92 (run 5 on the
  cached field_trial.csv reproduces run 0), the local walk 89 (the choice hidden).
- **Routines, step 4: fail well (2026-10-11, patch 0132).** A failed run's Comparison tab showed the traceback and every
  row *missing*. Now the record carries `failed_cell` (the number and the cell's code, `cell_text`), shown under its
  own heading beside the traceback; `compare_runs(..., failed=True)` compares the lines the run printed before it
  failed like any other and marks the rest *unreached* (the row reads *not reached*, the line *0 of 1 changed before
  the failure, 1 not reached* / *no result line came before the failure (2 not reached)*; the summary's comparison
  carries the count). Found on the way: with documents in the thread the cell named was one too high - `run_script`
  moved the `File "<string>", line n` frames back by the kernel prelude's lines but not the executor's *Error on
  line n* head, which `failed_cell` reads first; both are moved now, and the stack walk's run without `soil` says
  cell 2, as it should. The local edition's reproduction run (`code_executor._execute_locally`) had the same fault
  for another reason - its prelude and patch pushed the kernel's traceback lines down and nothing moved them back;
  it moves them now, as the executor's filter does with its patch. ROUTINES_DESIGN.md F2 (failure states), §11.4.
  test_routines.py 110, test_routines.js 61, the stack walk 89 in both editions.
- **Routines, step 4 begun: what differs, said in sentences (2026-10-11, patch 0131).** The CHECK row had said the
  fit (columns empty, files absent, values) and nothing of the rows. Now `analyst.routines.shape_sentences(record,
  data, shape, binding)` says, from the promotion's record (`rows`, `aux_shape`) and the run's shape probe: the
  frame's rows against the original's (*the same 5,860 rows as the original* / *2,184 rows where the original had
  5,860*), each bound file's rows against the original's with the columns added empty and the columns left empty
  (*the summary file: 91 rows where the original had 180, 1 column added empty (power)*), a file empty in this data
  (0 rows), a file that could not be read; nothing where nothing is known. The dialog's line carries the frame's
  sentence (no probe); the CHECK row the lot, between the fit line and the absent files; the record keeps
  `differences` and the whole `check` line; a stored run's CHECK row repeats the recorded line (it had said the
  size) and its Data tab lists the sentences under *Differs*; the pane's rows carry their whole text on hover and
  the routine rows are cut at 600 characters, not 200. ROUTINES_DESIGN.md F2.2, §11.4. test_routines.py 107,
  test_routines.js 60, the stack walk 88 (run 3 and 4's rows, the stored run 3 opened with the arrow), the
  integrations walk 43 (the summary's rows and the two columns added empty).
- **The figures request made reliable, and the run read in full (2026-10-11, patch 0130).** Palo's third run under
  0126-0129 - "Plot Fibonacci sequence", no data, deepseek-v4.1-flash at xhigh - took 290 s, $0.086 and 68,000
  completion tokens for no figure, where the same question had taken three or four turns. Read call by call (the run
  log, every prompt and reply whole), three causes, none of them the empty-REPORT slip (turn 6 wrote its report under
  the word): (1) *the failed-attempts list had no position in time* - listed after the cells, its line beginning
  "This turn generates...", a failure at turn 1 read as a failure after cell 2; the analyst rebuilt everything it had
  ("a later attempt this run rolled back") and then spent two whole allowances arguing which attempt had failed;
  (2) *the figures wording made the analysis prepare the figure* - "from the variables your cells defined" and
  "recompute nothing" produced a cell of "arrays the figure cell will use" and spiral-arc geometry planned in cells,
  and for a request that is a figure the report became a promise of three panels the figures request then had to
  honour; (3) *an effort-word model at xhigh has no reasoning budget* (`reasoning_style: effort` - the adapter's own
  warning), so the figures request spent its 16,000 tokens thinking and sent nothing - and the step took that for NONE,
  told the reader "a number answers", and went on to the rewrite. One revision: `Notebook.failed_attempts` places each
  failure ("turn 1, before any cell" / "turn 7, after cell 4"); the contract says cells "draw nothing and prepare
  nothing for a figure", the figures are drawn "from what the kernel holds", "the figure the question asks for, or
  the estimate and its uncertainty, first", and "a request for a figure is a short report - what is drawn, from what,
  what it shows - and the figure follows" (the SEARCH row's "settles a figure" became "settles a number"; the kernel
  paragraph and the standard's first item lost their restatements to stay on one page, 8,983 characters);
  FIGURES_SYSTEM likewise, with "the drawing's own arithmetic ... is the cell's to compute; the numbers the report
  states are not recomputed"; `_figures` treats a reply cut at the length limit, an empty one or prose without a block
  as an attempt - said as such (`FIGURES_CUT`, `FIGURES_NO_BLOCK`), asked again for a shorter cell within the four,
  each on the record as a lost turn of the step - and when the attempts run out the report ends with "> The figures
  were not drawn: <why>" (`figures_outcome`); NONE is recognised as the reply's first line (`answers_none`), bare or
  in markdown; and a **Figures seat** in the model config (`_figures_seat`, the Promoter precedent: a one-shot code
  reply where long reasoning only costs) - low effort in every tier of the template (Palo's current template, with
  the seat added after the Analyst), the sample config and the README, the analyst seat when absent. The README's
  "After REPORT" section now describes the flow as it is (figures, rewrite, replay). test_analyst.py 195 (the dated
  list; the cut, empty, prose, NONE-in-markdown and always-failing outcomes; the outcome line), test_app_path.py 94
  (the seat), the stack walk 86 (the Figures card on the Figures seat).
- **What steered the model to an empty REPORT, and the sentence rewritten (2026-10-11, patch 0129).** Palo, after the
  second run in a row ended at the word REPORT (caught by 0127 this time, the report written on the next turn): "why
  does it keep happening? The condition we introduced is only a patch that should almost never trigger". Read as the
  standing rule asks: the only text that changed between the runs that wrote their reports and the two that did not is
  0126's Figures paragraph - "Figures are drawn once, after the report, in a step of their own: shown your report, you
  write one cell ...". In the contract a *step* is one reply (the reply's first section is STEP), so the paragraph
  reads as a system-driven step after REPORT in which the analyst is shown a report and writes; both replies echo it
  ("I will now write the report; the figure itself is drawn in the step that follows", "This turn writes the report;
  the histogram is drawn in the step after it"), then give REPORT alone - the word taken as the action that starts that
  sequence, the text expected to be asked for the way the figures are. Told once that the report is the text under
  REPORT in the same reply (0127's line), the model wrote it at once. Rewritten, not supplemented: the REPORT row of
  the actions table says "The report, on the lines after it in this reply"; the Figures paragraph says "The figures
  come after the report: once it is written, one more request shows it to you and asks for one cell ..." - no step,
  nothing shown before it is written; FIGURES_LATER likewise ("from a request of their own, not from a cell of the
  analysis"). 8,995 characters. 0127 stays as the guard it is. test_analyst.py 189.
- **The plain-language version cites the figures (2026-10-11, patch 0128).** Palo: the simplified answer "could also
  benefit from figure citations". REWRITE_TASK: where the report cites a figure as [fig n], keep that citation at the
  end of the sentence that says what the figure shows (the cell citations still go, as before); the Simplified view
  passes its text through `paneCiteHtml`, so the citation is the same chip as in the technical answer, opening the
  Plots tab. The stack scenario's rewrite cites [fig 3]; the walk toggles to Simplified and finds the chip (85 hosted /
  84 local). test_analyst.py 189.
- **REPORT with nothing under it is not a report (2026-10-11, patch 0127).** Palo's first run under 0126 (Titanic, the
  age distribution of survivors, deepseek-v4.1-flash at xhigh) showed the Answer tab holding the Figures section and the
  replay line alone. The run log: the report turn's reply ended at `###ACTION###\nREPORT` - its STEP said "I will now
  write the report; the figure itself is drawn in the step that follows", its note "this turn = REPORT", and nothing
  followed the word (776 completion tokens, not cut). The parser took REPORT with an empty body as the report, so
  `_finish` ran on "", the figures step saw an empty report (and still drew three figures from the cells), the
  rewrite rewrote the captions, and the replay line read "the report cites no numbered cells". Fix at the cause:
  `_actions_in` returns no action for REPORT with nothing under it (`REPORT_EMPTY`), the turn is told "Your last reply
  ended at REPORT with no report under it, so nothing ran: the report is the text under REPORT, in the same reply.
  Write it now - ###ACTION### on its own line, REPORT on the next, then the report", and text on the REPORT line itself
  counts as the report's first line (it was dropped). The figures step also skips a run with no report text. The forced
  report at the budget's end keeps its fallback (the whole reply). test_analyst.py 188.
- **Figures drawn once, after the report, in a step of their own (2026-10-11, patch 0126).** Palo, from reading
  his runs: the analyst redrew near-identical charts across cells as it refined the numbers, the reader saw every
  version, each cell cost a turn and tokens, and a routine carried them all; he wanted fewer figures, only the final
  ones, none duplicated. The mechanism, settled with him: cells compute and draw nothing - a cell that calls
  `fig.show()`, `plt.show()` or `savefig` during the analysis is not run (`FIGURES_LATER` in its output and in the
  next prompt; a skipped row *In [–] · not run* in the pane and the notebook) - and after the report the session makes
  one call outside the turn budget, like the rewrite (`_figures`, `FIGURES_SYSTEM`, on the analyst seat): shown the
  question, the report as written, every cell's code, the RESULT lines and the note, the analyst answers NONE or one
  cell that draws one to three figures from the kernel's variables, with a `CAPTION:` line per figure. The cell runs
  wrapped (`FIGURES_WRAP_HEAD/TAIL`: the kernel's silent Plotly show replaced for the cell by a collector that prints
  the titles after `FIGURES:`; the record keeps the analyst's code alone, the traceback's lines mapped back by
  `unwrap_error`); a cell that fails comes back with its error for a corrected one, three corrections at most
  (`FIGURES_ATTEMPTS = 4`), each attempt a quiet *Figures* / *Figures · correction n* card followed by its cell row;
  the committed cell gets the next cell number, `step = "figures"` on its Turn (the strip's turn count leaves it out),
  and `figures` carrying the kernel's saved plots plus `{plotly, title}` per Plotly figure shown. The report gains
  `## Figures` with one `- [fig n] caption` line per figure (a figure without a caption is named by its title), and
  from there the section is part of the report: the guards, the rewrite, the replay's assembly (so the figures cell
  is cited and captured) and a routine's method read it as such. The contract's Figures section says the rule in
  four lines (8,980 characters); FIGURE_CELLS_MAX and the three-cell cap are gone. Executor and kernel unchanged.
  test_analyst.py 186 (the parser, the unwrap, a refused cell, the step with a failure and its correction, the
  section, the cards, the replay, NONE, the vocabulary scan of FIGURES_SYSTEM), test_app_path.py 93 (the step
  through the app: the skipped row, two cards, the failed row and cell 3, the Plots count, the notebook view),
  test_pane.js 44; the stack walk 83 hosted / 82 local (turn 5 draws anyway and is skipped; the Figures card; the
  rows in order; the Answer tab's Figures section with two fig 3 chips; Plots (2) still); the integrations walk 42
  (the start-hours story is contract-clean: two cells, the figure drawn by the step as cell 3, the routine made from
  it carries the figure). The stack's fake plotly keeps `update_layout` kwargs so titles read back.
- **Routines: whose data the cache holds - each Intervals load marked with its key, its files in the key's folder;
  executor image v52 (2026-10-11, patch 0125).** Palo: a coach who changes the Intervals key to look at another subject
  would have been served the first subject's cached windows. Settled in the container, where the data lives (chosen
  over an app-side ledger of loads with file stamps, built as 0125/0126 and set aside unapplied - `superseded/`):
  `code_executor_api.py` `key_mark(api_key)` (sha256, twelve hex characters, never the key; the same formula as
  `analyst.routines.key_fingerprint`), `metadata['key_mark']` on each Intervals frame, `save_aux_dataset(...,
  subdir=mark)` -> `datasets/<user>/<mark>/`, `/cache/inspect` lists the key folders (not `generated`/`routines`)
  with each file's `key_mark`; `EXECUTOR_BUILD` v52 - the self-hosted image tag follows it, the hosted containers
  pick it up as they are recreated (an older container's frames read 'from before loads were marked' until then).
  App: `cache_match(..., key)` uses a frame only with the same mark, its files from that folder (`have` keyed by
  (folder, name)); the exact window's newest frame first; `/routines/<id>/cached` reads the key through
  `get_intervals_api_key` and returns the mark on a hit, which the page passes in `load`; the Intervals route stamps
  `prefs['load']['key']` so the data record's `load.key` says which key a routine and its runs were made under;
  `run_routine`/`precheck_routine` merge the page's load over the instance's. `tools/stack/fake_supabase.py`: upsert
  on `bamboo_user_id` for the integration tables, as Supabase does. test_routines.py 104, test_app_path.py 88,
  test_documents_app.py (v52); the integrations walk: the files under the key's folder, a second key stored -> the
  line, a fresh download into its own folder, the first key's files untouched, the first key's window a hit again
  (42). ROUTINES_DESIGN.md F2.1, §9.
- **Routines: a cached load that contains the window is used, cut to the window before the method runs (2026-10-11,
  patch 0124).** Palo: Feb-May inside a cached Jan-June was downloaded again - and, as he saw, used whole it would show
  the cached window's numbers. `cache_match` now takes the exact window first, else the smallest cached load (same
  source and metrics) whose window contains the one asked, with every wanted file beside it under *that* load's name;
  the answer carries `cut: [cached start, cached end]`. The page passes `cached_from` in the load; `cut_window(ver, d)`
  (host) gives {start, end, column} - the frame's date column recorded at promotion; `prepare` rebinds every bound
  file to a run-folder copy named for the window (`cut_name`) and hands the prelude `_ROUTINE_CUT` {start, end,
  column, files: {new: {source, columns, by, column}}}; `CUT_SNIPPET` (shared with the precheck script) cuts the frame
  by its dates and each file by `CUT_RULES` (summary: start_date_local; wellness: date; intervals: the activity ids
  kept; others: a column of dates found by name, else the ids, else whole and said), adds the recorded columns a cut
  file lacks, prints `ROUTINE_DATA:` with the rows the method saw (read back into the record, the line taken off the
  output); the span inputs are computed after the cut. The value check cuts the same way, so a value absent from the
  window is a note. The CHECK row says the cut; the LOAD row 'cut from the cache'; `loadLabel` names the cached load.
  The Data tab afterwards holds the cached load (its pills say its window); the record says the run's. test_routines.py
  101 (a run on a cached Jan-June asked Feb-May over a real kernel: 2 of 4 sessions, the summary 2 of 4 rows, wellness 1
  of 3, intervals 2 of 4 by the ids kept, the span input from the cut frame, the precheck's note in the window);
  test_app_path.py 87; the integrations walk's run 4 (37): a window inside the original's, cut from the cached load,
  no FIT requests, the session count equal to the window's days. ROUTINES_DESIGN.md F2.1.
- **Routines: a choice column is looked for in the auxiliary files too; a partly absent choice is a note; the cache
  asked at Run time (2026-10-11, patch 0123).** Palo's third routine ("Rides by local start hour and midday share")
  refused every run with "column type is not in this data (for 'Ride')": the choice input's column `type` is the
  summary file's, not the frame's, and `precheck_script` looked in the frame alone. Now it looks in the frame first,
  then in each file loaded now (the header, then only that column: `_column_of`), and reports `where`; `value_verdict`
  (replacing `missing_values` in the host) refuses when the column is nowhere, a single value is absent or every chosen
  value is absent, and makes one of several absent a note ("'Ride' is not in column type of the summary file - the
  method keeps the other value") - `precheck` returns `values_notes`, the dialog shows them as a △ note, the run's
  CHECK row carries them. Also from his report: the second run re-downloaded a window already in the cache - the
  line's answer was stale (Safari commits a typed date on blur, which the click on Run itself causes, so the
  debounced check ran after `startRun`); `loadData` now asks the cache itself for the window as it stands
  (`askCache`), the line being a preview, and an `input` listener follows the typing; the route logs each answer at
  INFO. The integrations walk's scripted promoter proposes a choice over the summary's `type` (default Ride, Run);
  on the next window there are no rides, so the walk shows the note and the run going ahead (34). test_routines.py 95,
  test_routines.js 59. ROUTINES_DESIGN.md §4.6, F2.1.
- **Routines: a load already in the executor's cache is taken from there (2026-10-11, patch 0122).** Palo: "it would
  be good if cache and the files could be checked whether they exist for the desired window. Otherwise it
  re-downloads every time which is wasteful". `rt.cache_match(plan, inspect, start, end, race_id)` (pure) reads the
  executor's `/cache/inspect` listing against the routine's plan: a frame of the same source with the same window
  and metrics (Intervals) or the same event (Endura), and every auxiliary file of the wanted kinds present under the
  loader's name for that load (`kind_prefix`); SweatStack never matches (its entries do not name the subjects). The
  route `POST /routines/<id>/cached` {start, end | race_id} fetches the listing (no executor - the local edition - or
  an error: no hit, nothing said) and answers {hit, df_id, files, rows, line}. The page asks on open and as the window
  or the race changes (`checkCache`, debounced), shows the line under the window (`.rt-cache.hit|miss`), and on Run
  takes a hit through `/cache/load_primary` + `/cache/load_auxiliary` (`cacheFor`), the pills as a load's; every load
  now returns `load` - the load as the page did it (`loadAsked` + `cached`) - which rides with the precheck and the
  run (`routines_routes`, `precheck_routine`/`run_routine(load=)`, `_load_as_said`: plain values, no frame id) into
  the run's data record, so a cached run's record says the window and `cached: true` rather than the cache route's
  'cache'; `loadLabel` adds 'from the cache'. The LOAD row's query puts 'from the cache' before the kinds (the pane
  cuts a query at 60 characters). test_routines.py 92, test_app_path.py 87 (the route without and with an executor,
  the record), test_routines.js 58, the screens (s4c with the hit line); the integrations walk's run 3 sets the
  window back to the original's and takes it from the cache - no new FIT requests at the fake API (33).
  ROUTINES_DESIGN.md F2.1.
- **Routines: a run's load clears what it replaces (2026-10-11, patch 0121).** The run's pills stacked beside the
  old ones (Palo: "if there are any datasets in the UI, they should be cleared before the Run is executed"). Before
  the dialog's load, `clearLoaded(scope)` removes each pill the way its x does: file-management.js's handler is split
  into `handleRemoveDatasetPill(event)` and `removeDatasetPill(pillElement, removeButton, quiet)` (the route per
  dataset type, the pill gone, the Data tab told; `quiet` removes the pill without an alert when the session's
  reference is gone already). A load from Intervals, Endura or SweatStack clears everything; an upload clears the
  primary and keeps the auxiliaries (it cannot re-supply them). The files stay in the executor's cache - the
  removal routes drop the session's references only - which the next patch builds on. test_routines.js 55; the
  integrations walk checks the original window's wellness pill is gone after the run and one Intervals pill remains;
  the stack walk that the upload leaves one primary pill. ROUTINES_DESIGN.md F2.1.
- **Routines: an input that only restates the period the data covers follows the data (2026-10-11, patch 0120).**
  Palo's first routine made under 0118 had a date-window input "quoted in the result labels and figure titles" (the
  frame's first and last session dates, typed by the analyst, which the promoter made an input): the run on Jan-June
  asked for it beside the load window and wrote whatever was typed into the titles. Now the promotion probe
  (`shape_probe_script`, the aux-shape probe extended) records the frame's `span` (date column, first, last) on the
  data record; `derive_inputs` marks a date_window input whose default equals it `derived: span`, one equal to the
  load window `derived: window`; the run dialog shows such an input as a line (*follows the data: its first and
  last dates, written at each run* + the original's dates), no pickers; `run` writes the window kind from the data
  record (`derived_window_values`) and the span kind in the conform prelude from the conformed frame (`_ROUTINE_SPAN`,
  `_routine_span`, printed after `ROUTINE_INPUTS:` and read back by `read_marked`; the marker line is taken off the kept
  output; the values go on the record's `inputs`). The make dialog's and the manager's inputs tables say which
  inputs follow the data. A routine from before 0120 has no span on record - a next version gets it; the window
  kind works on old records too. The integrations walk's scripted analyst now types the frame's first and last
  dates into a label (as the live chain did) and its promoter proposes them; the walk checks the mark, the dialog
  and the run's record (30). ROUTINES_DESIGN.md §3, §4.8, F2, §12. test_routines.py 90, test_routines.js 53.
- **Routines: the runs table's mark sits between the two numbers it compares (2026-10-10, patch 0119).** Palo's
  first run that completed on a new window (Jan-June after Jul-Oct: three of five lines moved, the peak hour held)
  showed the manager's table with the ↑ = ↓ beside the second run's numbers and an empty Trend column - it read as
  a misplaced Trend. The mark now has a narrow column of its own between the runs it compares (`td.mark`; blank when
  a side is missing, the cell's · says it), and Trend appears with the third run, when there is a sparkline to put
  in it; the legend rewritten. Parked by Palo, in ROUTINES_DESIGN.md §12: typed text in figure titles (*91 sessions,
  13 Jul - 7 Oct 2026*) shows the original window on a new one - prose is not data; the contract clause covers new
  analyses, the pointing promoter the old. test_routines.js 50; the screens re-rendered (s6_manager_runs).
- **Routines: a loader's file name is bound by its kind; an edit that changes one is refused (2026-10-10, patch
  0118).** The cause of Palo's run under 0116, pinned from its `run.json`: the live promoter had made the loaded window
  an input (`window`, date_window, default the original window) and rewritten the five `read_csv` literals as
  f-strings on `INPUTS['window']`, so the recorded name was gone from the text; the generic datasets-folder rule moved
  the f-string into the run folder and the stand-in was never written for a name that did not exist - while the
  loaded files themselves bound fine (`shape.files`, fit 17/17). Three things: `bind_script` binds any datasets-folder
  literal whose basename carries a loader's prefix by its kind (`by_kind`) when the exact name is not on the table,
  so a name built around an input, a variable or another window is this load's file of that kind; `apply_edits`
  refuses an edit whose loader-file literals differ between find and replace (`loader_file_literals`) and the input
  is dropped with the reason in the dialog's notes ("the period or the file name is the loader's, not an input -
  each run binds the name to the file it loaded"); PROMOTER_SYSTEM rule 1 says to leave such names exactly as they
  are, dates included, and never to make the loaded period an input. His routine 53d031cf746c runs as it is (the
  `window` input inert; a next version under the prompt drops it). The integrations walk's scripted promoter now
  makes the same proposal as the live one and the make dialog's notes show it refused, the stored script still
  reading the dated name. ROUTINES_DESIGN.md §4.7. test_routines.py 86, test_integrations.py 27.
- **Routines: a run is self-sufficient about its files (2026-10-10, patch 0117).** Palo's first run under 0116 on a
  Jan-June window stopped on `FileNotFoundError` at the stand-in's path for the summary
  (`datasets/local/routines/<id>/v1_1/activity_summary_<old window>.csv`): the loaded data's file list had no summary
  in it at run time and the probe had not written the stand-in - the record itself binds correctly when replayed here,
  so the cause is in the run's state and is not yet pinned (the run.json's `data.aux`, `aux_absent`, `bindings` and
  `shape` will). Hardened so the class cannot reach the method: `prepare` makes a stand-in path for every absent file
  whether or not the probe wrote it (a recorded name is never rewritten as a cache path); the conform prelude
  materialises every path the executed text names before the cells run (`_ROUTINE_FILES`: a stand-in not written is
  written with the recorded columns; a bound file gone is stood in for and said in the output; a cache file the method
  reads under its run-folder name is copied there); the page sends the files its load produced (`aux`, an empty list
  when none) and the run prefers them; `run_script` rebases traceback lines past the kernel prelude; `failed_cell`
  reads the executor's `Error on line N:` header (its frames are cut at 1,000 characters); the run logs its data and
  the binding at INFO so the terminal shows the file list next time. test_routines.py 82 (a failed probe, a vanished
  bound file).
- **Routines, F2 rebuilt: the routine loads its own data and makes it fit the recorded shape (2026-10-10, patch 0116).**
  The first live run on a new Intervals window (patch 0113's "run on current data") read the loader's summary file by
  its dated name - `activity_summary_20260812_to_20261010.csv` is the auxiliary the Intervals loader writes, named by
  the window - so the method read the old window or nothing, and divided by zero. The concept now (ROUTINES_DESIGN.md,
  the opening and F2): adapt the data to the method, never the method to the data. Built: (1) the run dialog loads as
  the original load did - `load_params` set by every loader route (intervals: the window, metrics, aux kinds, kept
  with the job; endura: the race; sweatstack: the fetch params; a file: its name; the cache) rides into the run's data
  record as `load`, and `routines_host.load_plan` reads it (or derives it from the record's date range and file
  names for routines made before); the dialog (routines.js `build.loadSection`, `loadData`) offers Intervals.icu
  (a window of the original's length ending today, clamped by `/intervals/get_data_limits`, with the auxiliaries and
  metrics as the original, polling `/intervals/job`), Endura (the race list), SweatStack, or an upload, beside the
  data loaded now; the Data tab's pills and frame view refresh as the Data tab does; a LOAD row in the pane. (2) The
  data made to fit (`analyst/routines.py` aux_kind / bind_aux / bind_script / conform_prelude / shape_script;
  `routines_host.prepare`): the recorded auxiliary files bound by kind (activity_summary_ -> summary, wellness_data_,
  activity_intervals_, athlete_profiles_race_, race_turns_race_, race_climbs_race_, race_waymarkers_race_; an
  attached file by its name) to this load's; a probe script in the executor writes, in the run's own folder
  (`datasets/<user>/routines/<id>/<tag>/`), a copy with the recorded columns the new file lacks and an empty table for
  a recorded file this load did not write; the executed text is the stored script with every string literal naming a
  recorded file (or any path under the datasets folder) replaced by this run's path - the stored script untouched, the
  substitutions in the record (`bindings`); the prelude after INPUTS conforms `df` (missing columns added empty in
  their type, a type family that changed read back) and rebuilds DS on it. The aux files' columns go on record at
  promotion (`record_aux_shape`, `aux_shape`) while the files are there. (3) The fit is no longer a refusal: a column
  missing is said (`fit_check`: "2 of 49 columns empty in this data: power, temperature"; the dialog's line is an
  amber note) and the run goes ahead; the one refusal is data with none of the method's columns; a line that comes
  back as nan reads as differed; the error line named as the analysis names it (`error_line`, never the kernel's
  rollback notice). Testing from the get go: `tools/stack/fake_apis.py` + `apis_data.py` (a calendar with the
  loaders' variation: rides and power until sixty days ago, temperature until forty, wellness until sixty, a travel
  block every hundred days; three races, the second without power or climbs) + `fit_writer.py` (a FIT encoder
  fitparse reads); the executor's requests to intervals.icu / team-hub.co.uk are routed to it by executor_launcher.py
  (`STACK_FAKE_APIS`), nothing in the executor changes; `STACK_COMPUTE_TIER=pro` for a year's window; the plotly
  stand-in takes a single trace. `tests/e2e/test_integrations.py` (25): the original window loaded through the
  Intervals dialog, the scripted analyst (scenario `start_hours`) reading the summary by its dated name with the home
  offset read off the data, Save as routine, Run loading the next window itself (power absent, wellness absent, the
  summary bound and copied with the columns added), the arrows, the Data tab's bindings, a run on the data loaded
  now, then Endura: race 1 -> a routine -> run on the flat crit picked in the dialog. test_stack.py's tail: the
  dialog's upload, the LOAD row, the file without `soil` running to a kept failure at the cell that divides by zero.
  Next: 0117 (say what differs from the probe's counts; partial lines on a failure; the failed cell's code), 0118
  (the pointing promoter with silent derivations; the make dialog without choices), then Narrate.
- **The contract: values read off the data are variables, not literals (2026-10-10, patch 0115).** The first routine
  run on a new Intervals window failed at a cell that had the athlete's time-zone offsets typed in (`offset_h == 2`)
  and divided by a count that was zero on that window; the literals originate in exploration, so the contract's
  kernel section now says: a value read off the data - a date in it, a subject's identifier, a threshold - is computed
  and kept in a named variable, never typed as a literal, so the method holds when the data is loaded again; a value
  the question gives stays a literal. Kept under the one-page limit (9,000) by trimming redundancy elsewhere (the
  turn-ends sentence said twice, the figures paragraph, SEARCH's row). The routines design (docs/ROUTINES_DESIGN.md
  §4) records it as the upstream lever; the rework of F2 (the routine loads its own data and conforms it to the
  recorded shape; says what differs; fails well; the pointing promoter) follows as 0116-0118.
- **Routines, two fixes from Palo's Titanic test (2026-10-10, patch 0114).** (1) The executor chip stayed on
  *Executing* after a run: the routine's ROUTINE / RUN rows set it as a cell does (`pane_cell_start`) but only the
  replay's `pane_lookup` released it; now the routine's kinds release it too (query-processing.js), and routines.js
  releases it on the closing card and on a broken stream. (2) The promoter has its own seat, **Promoter**, in every
  tier of `web_app/LLM_CONFIG_template.json` (and `LLM_CONFIG_sample.json`, the README's table): Palo saw a Sonnet
  seat at xhigh spend its whole allowance reasoning, twice, and the dialog said "invalid JSON". `_promoter_seat()`
  returns 'Promoter' when the config carries one, else the analyst's seat (`_llm(..., seat=)` names a seat outright);
  a reply the model layer flags as truncated is now said as such - nothing but reasoning: refused after one call (a
  second would go the same way); cut mid-object: one more try asking for a shorter object (`PROMOTER_CUT`); cut
  twice: refused - and the refusal names the Promoter seat's `max_tokens` / effort as the thing to change. The
  prompt also asks for a short object. Deployed templates need the four Promoter lines (or the patched template).
  Tests: test_app_path.py 81 (the seat with and without an entry; the three cut cases through the instance),
  test_routines.py 71, test_routines.js 45 (the chip release), the e2e walk (the chip back to Ready after a run;
  the promoter's card on the Promoter seat). Next: Palo's Titanic run on dev (run on its own data = reproduced,
  an input changed, a column dropped); then step 3, Narrate (the Rewriter-seat note under the numbers guard, the
  What-changed tab and card).
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
after every 8th turn by the reviewer (its own prompt, `analyst/reviewer.md`), and its report once; Quick and Deep make
no reviewer call (2026-10-05).

## Behaviour to know

- A follow-up standing on the kernel's current tip reuses the warm kernel; a branch or a new
  thread gets a fresh kernel rehydrated from the parent's path (the same mechanism replays the
  assembled script at the end of every run).
- ASK ends the run with the question as the answer; the person's reply is the next run.
- Cells compute; the figures are drawn once, after the report, by the figures step (2026-10-11): a cell that
  draws during the analysis is not run, and the report's `## Figures` section cites the one cell that drew.
- Thread files from the previous design are read tolerantly (their keys are preserved; the
  notebook tree is added beside them). Favourites, previews, replays and the workflow map are
  browser-saved snapshots and are unaffected.
- The executor image no longer copies `toolkit.py`; rebuild it when convenient.

## Tests

`./run_battery.sh` — `tests/analyst/test_analyst.py` (20 checks) and
`tests/analyst/test_app_path.py` (12 checks), both over a real in-process kernel.
