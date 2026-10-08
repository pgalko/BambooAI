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
  `anthropic>=0.88` is now the floor; no kernel change, image v51 stands).
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
- Thread files from the previous design are read tolerantly (their keys are preserved; the
  notebook tree is added beside them). Favourites, previews, replays and the workflow map are
  browser-saved snapshots and are unaffected.
- The executor image no longer copies `toolkit.py`; rebuild it when convenient.

## Tests

`./run_battery.sh` — `tests/analyst/test_analyst.py` (20 checks) and
`tests/analyst/test_app_path.py` (12 checks), both over a real in-process kernel.
