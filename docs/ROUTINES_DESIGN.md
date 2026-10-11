# Routines — design v1.0 (2026-10-10)

A routine is an analysis kept as a method: built by exploring with the analyst, then run again, without a model,
on new data — a later window from Intervals.icu, another athlete's data behind a new API key, the next race from
Endura, an updated lab file — and compared, run against run. This document is the map of the feature: the
vocabulary, what it builds on, the records, the flows with their failure states, the model's two calls, the screens,
the storage, the build order and the open decisions. Steps 1 (Save as routine) and 2 (Run on current data) are
built; the rest is design.

The story in one paragraph. A coach explores a question with the analyst and lands on something worth keeping.
*Save → Save as routine* keeps the chain as a favourite and turns it into a routine: the method with its few inputs
named, verified once on the original data, linked to the analysis it came from. Later — next week, another athlete,
the next race — *Run* asks for the inputs, loads the data through the same source, runs the method deterministically,
records the run, shows every result next to the previous run's, and says in a few sentences what moved. That is the
whole of a run: nothing to ask, nothing to edit. Exploration stays where it is: the routine's card opens the original
analysis as a favourite, the coach continues it there with the analyst as they would any thread, and when something
new surfaces, *Save as routine* on a chain of that thread offers the routine's next version. Nothing in this costs
more than a few cents a run, because the model never runs the method; it names the inputs once and narrates.

The two halves are kept apart on purpose — exploration (threads, chains, favourites, the analyst) and exploitation
(routines, runs, no model but the narrator) — so that a routine always has its analysis behind it and an analysis is
never confused with a run. Two rules make the line visible on screen: the only things a person can set are the inputs
before a run, and under a run's view the composer is disabled — it comes back on a new thread or when a favourite is
loaded.

One principle governs how a run meets new data (settled 2026-10-10, after the first live run on a new window stopped
at a cell that read the loader's summary file by its dated name): **adapt the data to the method, never the method to
the data**. The routine records the shape of the data the analysis ran on — the frame's columns and types, each
auxiliary file with its name and columns, how the load was asked for — and a run loads new data the same way, then
makes it fit that shape before the cells run: the recorded file names open this load's files, a column this load
lacks is added empty, a type that changed is read back. The stored method is never edited after promotion; the
coach is told what differs before anything runs; a failure is a run, kept and named at its cell. Nothing in the
loaders, the analyst, the kernel or the cache changes for this.

## 1. Vocabulary

- **Routine** — a named method, with a current version and a history of runs. Made from one chain.
- **Version** — an immutable script with its inputs manifest, promoted from a chain. A routine starts at v1; a
  later chain of the origin's thread, saved as the next version, makes v2. Runs record their version.
- **Run** — one deterministic execution of a version on one dataset with one set of input values. Stores its
  results, figures, printed output, status, and the comparison with the run before it.
- **Run zero** — the verification run made at promotion, on the exploration's own data. Every version has one.
- **Inputs** — what varies between runs: the *data input* (a window, a race, a file) and at most a handful of
  *parameters* (a number, a short list of numbers, a date window, a choice, a toggle). Coaches see only these; never
  the script.
- **Data source** — where a run's data comes from: Intervals.icu (window, auxiliaries, metrics), Endura (race,
  auxiliaries), a file (the primary file and up to three auxiliary files, uploaded or from the Dataset cache).
  SweatStack is not given a run dialog; a SweatStack routine runs on whatever dataset is loaded.
- **Comparison** — the computed, model-free table of this run's results against the preceding run's.
- **Narrative** — the Rewriter seat's short note on the comparison, part of the run's output.
- **A run is a record**, not a chain: it is written by the runner as it completes (results, figures, output,
  comparison, narrative) and shown from the record, as a favourite is. No kernel state is kept for it and nothing
  can be asked of it; what a coach wants to ask, they ask of the analysis the routine links to.
- **The origin** — the favourite the routine was made from. Saving as a routine saves the favourite too, so a
  routine is never without its analysis; the routine's card opens it, and a new version comes from that thread.
- **Favourite** — the existing saved-workflow record; a run can be saved as one.

## 2. What this builds on

Facts about the code as of 2.2.2 (patches to 0110), so the design claims nothing the system cannot do:

- `analyst/replay.py` assembles a chain's committed cells, in execution order, into one script with the DS/RESULT
  stubs, figure-capture gating, the kernel's display options and `# --- cell n ---` markers; `compare()` checks the
  cited numbers against a fresh run. The routine takes today's assembly of the chain's cells, not the script stored
  with the run (a chain from before the RESULT stub would stop on a NameError).
- The executor's `/execute` route runs a script against the cached `df` (by `df_id`) with auxiliary files on disk,
  captures stdout and figures (`fig.show()` as Plotly JSON), and returns generated datasets. `BambooAI.run_script`
  is the one client of it for the replay and for a routine's runs, with the replay's timeout rule.
- `RESULT(...)` prints one regular line per estimate — `RESULT: {tags}{what}: {est} (95% CI {lo} to {hi}) {unit},
  {direction}` — and marks a typed one with ` - typed: ...`. The line is parseable (`analyst/routines.py`
  `parse_result_line`); the kernel also keeps a structured record per cell, and the routine's expected lines come
  from those records, keyed by position.
- A run now records what it ran on (`Run.data`, 2026-10-10): the frame's `df_id`, name, source as the executor's
  cache knows it (csv | intervals | endura | sweatstack), columns with dtypes, rows, the loader's details, the
  auxiliary files. The `dataset_metadata` table of the hosted dump is not written by the app; the run's record is.
- The loaders take the varying inputs: Intervals `/load_data` (start_date, end_date, metrics, aux_datasets:
  wellness, summary, intervals), Endura `/load_data` (race_id, aux_datasets, default profile), file upload into the
  Dataset cache. Each loader is a job the Data tab polls today.
- The Rewriter seat runs cheap text calls; the numbers guard (`report.guard_technical`) checks a text's numbers
  against printed outputs; favourites store a chain's rendered output as HTML, one JSON file per chain under
  `storage/<user>/favourites/<thread>/`.

## 3. The records

Stored as files beside the favourites, one folder per routine: `storage/<user>/routines/<id>/routine.json` (the
routine, its versions, run zero) and `runs/<tag>/` (the printed output and the figures of each run). The same layout
in both editions, like favourites; nothing in the database.

**routine** — id, name, created, updated, purpose (the coach's one line, written at Save as routine), question (the
origin's), summary (the origin report's opening), origin (thread id, chain id — the favourite), source
(file | intervals | endura | sweatstack | none), current_version, versions, runs.

**version** — number, created, promoted_from (thread id, chain id), script (the assembled text with the cell
markers and an `# --- INPUTS ---` mark between the preamble and the first cell), manifest, change_note ("first
version"; later the coach's one line), run_zero (status, line, verified, results, figures, data, inputs).

**manifest**:
- `data`: the run's data record (above) — the columns with their types, which a later run is made to fit; `load`,
  how the data was asked for (the loader routes put it on the instance when a load completes: intervals — the
  window, the metrics, the auxiliary kinds; endura — the race and its auxiliaries; sweatstack — the sports, the
  subjects, the window; a file — its name), which a run repeats; `aux`, the auxiliary files' paths; `aux_shape`,
  each file's columns with their types and its row count, read at promotion while the files are still there;
  `span`, the period the frame itself covers (its date column, first and last dates), read by the same probe.
- `parameters`: at most five, each `{key, label, type (number | numbers | date_window | choice | toggle), default,
  origin ("the exploration used …"), column? (choice), multiple? (choice), derived? (span | window)}`. The script
  reads `INPUTS[key]`; the runner writes the `INPUTS = {...}` block at the mark before each run. A derived input is
  not asked: the run writes it from the data (§4.8).
- `results`: the expected RESULT lines in order, each `{cell, index, label, typed, dropped, estimate, low, high,
  unit, direction}` — the identity of a line is `(cell, index)`, never the label. `typed` comes from the kernel's
  records; a dropped line stays in the manifest, so the check by position still maps the chain's lines to the
  routine's.
- `figures`: how many the script draws, and which cells.
- `notes`: what the promotion left out and why (an input whose edit did not apply, a sixth input).

**run** — built (step 2): number (0 is run zero), version, created, finished, elapsed, status (reproduced | ran |
differed | failed | timed_out), line (the status in words), data (the loaded data's record: source, name, columns
with their types, rows, range, auxiliaries, how it was loaded), inputs (the values the run was given), results (the
lines parsed from the printed output by position), figures (the count; the files beside it), stdout_chars, cells,
against (the reference run's number), comparison (rows, moved, within, changed, missing, compared, line), narrative
(step 3; empty until then), error; and, since the rebuild of F2, how the data was made to fit: `fit` (the columns
missing, extra, retyped; the line), `bindings` (each recorded file name and the path it opened in this run),
`aux_absent` (the recorded files this load lacked, by kind), `shape` (what the probe found in each bound file and
the copies it wrote), `run_dir` (the run's own folder on the executor's side), `generated` (the files the run
wrote). Each run is `runs/v<version>_<number>/run.json` with `stdout.txt` and `fig_n.json` (run zero is `v1_0`); a
light summary — the data without its columns, the comparison's counts — is appended to `routine.json`'s `runs`
list, which the manager and the run dialog read.

Status meanings: *reproduced* — every expected line reappeared with the same numbers (run zero, or a run on the same
data with the same inputs); *ran* — every line reappeared, numbers differ (the normal case on new data); *differed* —
a line is missing, or more came back than expected; *failed* — the script stopped at cell n (the run is kept, so the
history shows it); *timed_out* — likewise; *unverified* — run zero could not run because the analysis's data was no
longer loaded; the first run on data tells. A line that comes back without a number (nan, from a column that was
empty in this data) counts as *differed*. Data with nothing of the method's in it is not a run: the check before
the run says so in the dialog and nothing is recorded (the design had a *did_not_fit* status; built as a refusal,
since a record of nothing would only pad the table); data that differs - a column empty, a file absent - is said and
the coach decides.

## 4. The inputs model

The promoter proposes the inputs; the coach confirms them; the runner writes them. Five rules keep them simple:

1. **The window is the data's.** Date literals that were the exploration data's own range become expressions of the
   loaded data (`df[date].min()`, `.max()`), so the window chosen at load time is the only window there is. A
   literal that is *not* the data's range (a race date, a season boundary) becomes a date parameter.
2. **The athlete is the key.** With Intervals.icu and Endura, whose data is one athlete's, nothing in the script
   names the athlete; changing athletes is changing the API key. Only a dataset with several athletes (a file) gets a
   choice parameter, and only if the exploration filtered on one.
3. **At most five parameters**, of five plain types: a number, a short list of numbers (bands, bins: "130, 145,
   155, 165, 175"), a date window, a choice from a column's values (one or several), a toggle. A range is two
   numbers. A constant the promoter is unsure about stays a constant; the dialog lets the coach keep a proposed one
   fixed ("keep fixed" drops it), never add a free-form one. If the method needs a new input, that is the analysis
   continued and a next version.
4. **The script carries no values.** The stored script reads `INPUTS[...]`; the runner writes the `INPUTS = {...}`
   block at the mark for each run from the dialog's values, and the `.py` download adds the block with the defaults.
5. **The promoter edits, it does not retype.** Its reply is a list of find/replace edits, each a verbatim fragment
   that occurs once in the cell it names; the edits that serve one input apply whole or not at all, so an input is
   never half made, and an input whose edits did not apply is left out with a note the dialog shows. Run zero then
   catches a rewrite that changed the method.
6. **A choice input's values are checked against the data** before a run (built), like the columns: an exclusion of
   "athlete07, athlete09" on a file that has neither is said ("'athlete07' is not in column athlete") rather than
   silently doing nothing; a column the data lacks is said too ("column athlete is not in this data"). The check is
   a small script in the executor that prints the membership, run with the run dialog's values before the run. The
   column is looked for in the frame first, then in the auxiliary files loaded now (2026-10-11: a choice over the
   summary file's `type` was refused as not in the data), and the message names the file ("'Ride' is not in column
   type of the summary file"). One of several chosen values absent is a note, not a refusal — the method keeps the
   other values; a single value absent, every chosen value absent, or a column in neither the frame nor the files
   refuses: nothing to run on for that input.
7. **A loader's file name is the loader's, never an input's** (2026-10-10, the second live run: the promoter had
   made the loaded window an input and written it into the summary's name as an f-string, so the recorded name was
   gone from the text and the run bound nothing). The period is chosen when the data is loaded, before the method
   runs, and each run binds the names the loaders write (`activity_summary_<start>_to_<end>.csv`,
   `race_turns_race_<id>.csv`…) to the files that run loads — by their *kind*, whatever the rest of the name says, so
   a name built from an input, a variable or another window is still this load's file of that kind. An edit that
   changes such a literal in any way is refused and its input dropped with the reason in the dialog's notes; the
   promoter's prompt says to leave the names exactly as they are, dates included, and never to make the loaded
   period itself an input. A routine made before this keeps running: its window input is inert, the binding by kind
   reads past it; the next version under the prompt as it is now drops it.
8. **An input that only restates the period the data covers follows the data** (2026-10-11, the first run that
   completed on a new window: the labels and figure titles carried the original window, typed by the analyst, and
   the promoter had made it a date window the coach had to retype beside the load window). At promotion the probe
   that reads the auxiliary files' shape also records the frame's `span` — its date column, first and last dates —
   and a date-window input whose default is exactly those dates is marked `derived: span`; one whose default is the
   load window is marked `derived: window`. Neither is asked in the run dialog (a line says *follows the data: its
   first and last dates, written at each run*, with the original's dates for the record); the run writes the window
   one from its data record and the span one in the prelude, from the conformed frame (`_ROUTINE_SPAN`), printing
   `ROUTINE_INPUTS:` for the record — the line is taken off the kept output, the values go on the run's `inputs`.
   A window inside the data (a race week) matches neither and is asked as before. The mark is set when the routine
   is made, so a routine from before needs one next version to get it; the `.py` download keeps the defaults.

Relative windows for files: the "updated lab file with extra rows" case runs on the whole file unless the
exploration itself filtered by date, in which case the promoter offers "last N days of the file" with N from the
exploration.

Upstream of all this, the analyst's contract carries one rule since 2026-10-10 (the first live run of a routine on
a new window stopped on a time-zone offset typed into a cell): a value read off the data — a date in it, a subject's
identifier, a threshold — is computed and kept in a named variable, never typed as a literal, so the method holds
when the data is loaded again; a value the question gives stays a literal. It is the one place the literals that
make a routine window-bound originate, and the cheapest fix per routine; the promoter and the run's checks handle
what still arrives as a literal.

## 5. Flows

### F1 — Save as routine (promotion) — built

Entry: the *Save* pill on a finished chain, whose hover (or click) menu has two items — *Save as favourite* (the
rank dialog, as before) and *Save as routine* — and a saved workflow's card (its *Routine* button, grey when the
analysis has no routine). The pill now stays on a saved chain, the bookmark filled, since its menu still offers Save
as routine; the first item then reads "Saved as favourite".

1. The app assembles the chain's script (today's assembly of the cells on the path) and gathers: the question, the
   report's opening, the RESULT ledger from the kernel's records (typed marks included), the run's data record, the
   cells' text. Refused before any call: a chain not in the thread's record, one that ended `asked`, `failed` or
   `stopped`, one with no cells. A chain that recorded no RESULT lines is not refused: runs will not be compared
   number by number, and the dialog says so.
2. **The promoter**, one call on the Promoter seat (its own entry in the model config since 2026-10-10 — a moderate
   effort and a roomy `max_tokens`, because the reply is a JSON object of edits that a seat tuned for long reasoning
   can spend its whole allowance thinking about; the Analyst seat when the config has no Promoter) with a generic
   prompt (`analyst/routines.py` PROMOTER_SYSTEM; no domain words, DESIGN_CHECKLIST C5): name the constants that
   would change on other data of the same shape; make the data's own range the data's range; propose each remaining
   constant as an input of one of the five types, at most five, fewer is better; leave a loader's file name exactly
   as it is and never make the loaded period an input (§4.7); rewrite as find/replace edits; leave the method, the
   markers and every RESULT call otherwise untouched; return JSON, kept short. A reply that cannot be
   read is asked for once more, then refused ("the script was not understood"); a reply cut at the seat's token limit
   is asked for once more, shorter — unless nothing but reasoning arrived, when a second try would go the same way —
   and the refusal then names the cause and the seat to adjust. The call runs on a chain id of its own, so the hosted
   edition charges it as a query; the pane shows it as a quiet *Routine* card with the seat and its model.
3. **The dialog** (S1) shows the proposal: name (the promoter's title), purpose (prefilled from the question; one
   line for the card and the narrator), the data (source chip, name, rows, columns; whether the chain's data is
   still loaded), the inputs as rows (label, value now, where it comes from, "keep fixed"), the expected results with
   any *typed* line flagged ("the numbers were typed into the call, not computed — keep as a constant / drop"), the
   figure count, the promoter's notes. On a chain of a thread that already has a routine, the dialog opens on the
   choice *Next version of "…"* / *A new routine*, with a *What changed* line. Create / Cancel.
4. **Run zero.** On Create, the runner executes the script with the defaults on the chain's data through the
   executor (the replay's path and timeout). The RESULT lines that come back are checked by position against the
   chain's records: identical numbers reproduce; a different count or a different number is *differed*, an error
   *failed* — and the routine is refused with the lines named ("Try again" re-proposes). With the chain's data no
   longer loaded, the routine is created *unverified* and says so. A chain from before the data record takes the
   data loaded now for its own.
5. Stored: the routine, v1 (or the next version), its manifest, run zero with its output and figures. Then the
   chain is saved as a favourite (silently, no rank) when it is not one yet. The pane shows the *ROUTINE* row with
   run zero's verdict; a toast says "Routine made: <name> · v1 · verified on the original data"; the Routines rail
   entry shows a count.

### F2 — Run — built (rebuilt 2026-10-10: the routine loads its own data and makes it fit)

Entry: *Run* on the routine (S2). The dialog (S3) opens on the way the original load asked for its data (the
version's data record, `load`), and offers the data loaded now beside it.

1. **The load, as the original did.** Intervals.icu: a window of the original's length ending today (clamped to
   what the plan allows, and the dialog says so), the metrics and the auxiliary kinds as the original - through the
   same loader job the Data tab uses, with its progress shown in the dialog. Endura: the race list, the original
   race selected. SweatStack: the window shifted, the sports and subjects as the original. A file: an upload, or
   the Dataset cache's pick. A load clears what it replaces first (2026-10-11: the run's pills used to stack beside
   the old ones) — a load from Intervals.icu, Endura or SweatStack clears the primary and the auxiliaries, an upload
   the primary only, each pill removed the way its × removes it (the session's reference dropped, the file left in
   the cache). **The cache first** (2026-10-11: a run re-downloaded a window the Data tab had loaded minutes
   before): as the dialog opens and as the window or the race changes, the page asks `/routines/<id>/cached`, which
   reads the executor's cache listing (`/cache/inspect`: the frames with their source, window and metrics; the
   auxiliary files on disk) against the routine's plan — the same source, the same window and metrics (Intervals)
   or the same event (Endura), and every auxiliary file of the kinds the routine wants there under the loader's
   name for that load (`cache_match`). A line under the window says *✓ this window (… → …) is in the cache (10,200
   rows, with summary, wellness) - no download*, or why not (*not in the cache*, *in the cache without wellness*);
   on Run the page asks again for the window as it stands (the line's earlier answer can lag behind a date typed
   and committed by the click on Run itself — Safari commits a date on blur) and a hit is taken through the Dataset
   cache's own routes (`/cache/load_primary`, `/cache/load_auxiliary`), the pills as a load's, and the LOAD row and
   the run's record say *from the cache*. SweatStack's entries do not
   say which subjects they hold, so they never match; the local edition has no executor cache. The page sends the
   load as it did it (`load`: the source, window or event, kinds, `cached`) with the precheck and the run, so the
   record says what was loaded rather than the cache route's *cache*. The Data tab's pills and the frame view then
   refresh as the Data tab refreshes them, so the session's data is the run's data afterwards, as it was after a
   v1 replay. *The data loaded now* is the other choice when something is loaded (the default for a file routine).
2. **The check** (`precheck`): the data against the recorded shape - the columns the method ran on, by family
   (number, date, text): *fits the routine (49 of 49 columns)*, or *2 of 49 columns empty in this data: power,
   temperature* (a note - the run adds them empty), or *none of the routine's 49 columns is in this data - nothing to
   run on* (the one refusal); the auxiliary files bound by kind to this load's (*wellness absent in this data - the
   method will see an empty table there*); the chosen values of the choice inputs against their columns. The inputs
   as widgets by type, at their defaults. *Compare with*: the run before or run 0. Pressing *Run* loads first when a
   load is chosen, then checks once more with the values as typed; what fails is said in the dialog and nothing
   runs.
3. **The data made to fit** (`prepare`), in the run's own folder on the executor's side
   (`datasets/<user>/routines/<id>/<tag>/`): each recorded auxiliary file bound, by kind, to this load's file - a
   copy with the recorded columns it lacks added empty when it lacks any; an empty table with the recorded columns
   for a file this load did not write; the executed text is the stored script with every string literal that names
   a recorded file - by its exact name, or by its loader kind when the rest of the name differs (§4.7) - or any
   other path under the user's datasets folder - replaced by this run's path, so the method reads this window's
   summary under the name it was written with and never writes into the person's cache; the
   prelude after the INPUTS block conforms `df`: a recorded column this frame lacks is added empty in its type, a
   column whose type family changed is read back (`conform_prelude`), and `DS` is rebuilt on the conformed frame;
   then the inputs that follow the frame's own dates are written from it (§4.8). The stored script is not changed;
   the record keeps the substitutions and the values written.
4. **The run**: the manager closes, the main panes enter the run's view (S4) - the strip *run n · vX*, the position
   *run n · running* with both arrows off, the composer locked - with a *LOAD* row when the dialog loaded, then the
   *CHECK* row (the fit line and the files), *RUN* (run n · vX · k cells → the status line, the figures, the seconds),
   *COMPARE with run k*; the Plots, Results and frame tabs through the stream; the closing card; then the Comparison
   tab, opened. The timeout is twice run zero's time plus two minutes, within five and thirty minutes (ten minutes
   when run zero did not run).
5. **Results** parsed from the printed output by position against the manifest's lines (a dropped line is printed
   but not compared); the status (a line that comes back without a number counts as differed); the figures and the
   output kept beside the record.
6. **The comparison** against the reference run: for each expected line, this run's estimate and interval against
   the reference's; the change; whether the intervals overlap (*moved* when they do not, *within* when they do;
   without intervals, *changed* / *same* on the estimates); a line missing on either side marked. The line reads
   *3 of 5 moved beyond their intervals*.
7. The run is recorded as it completes, the routine's `runs` list and the rail badge updated. The composer stays
   locked under the view and comes back on a new thread or when a favourite is loaded.

Failure states, as built: nothing of the method's data in this data - said in the dialog, *Run* off, nothing
recorded; a value not in the data - said in the dialog, nothing runs; a load that fails (no activities in the
window, a key not set) - the loader's own message in the dialog, nothing runs; failed at cell n - the run kept with
status failed, the closing card in the warning tone with the line that names the error (never the kernel's rollback
notice), the Comparison tab with the error block and the rows marked missing; timed out - likewise; a result line
missing or without a number - status differed, the count in the line; the stream broke - the pane says so and the
view returns to the last recorded run.

### F3 — Narrate (step 3)

On by default after a run with a comparison, one Rewriter-seat call: input — the routine's question and purpose, the
original report's opening, the two runs' data descriptions and input values, the comparison table; output — a short
note: what moved beyond its interval, in which direction, what held, what failed, in the terms the original report
used. The numbers guard checks it against the two results tables; a number not in them is marked as the report's
are. The note is the *What changed* tab and the card in the pane; it is kept with the run.

### F4 — Versions come from the exploration (step 5; the choice is built)

A run is read, not questioned. To go further, the coach opens the analysis the routine links to — *made from the
analysis of <date> ↗* on the routine's card loads the favourite, as the Saved-workflows manager does — and continues
it there: a question or an extension is a chain in that thread, with the analyst, at the mode they choose, on that
thread's data, with the whole exploration in the ledger. Nothing about that is new.

When a chain of that thread has what the routine should do from now on, *Save → Save as routine* on it recognises
the thread's routine and the dialog asks first: *the next version of "<routine>"* (the default) or *a new routine*.
The next version is promotion again (F1) with two differences: the promoter receives the current manifest and keeps
the inputs that still apply (same keys, labels, defaults), and the coach writes a one-line *What changed*. Run zero
for the new version runs on the chain's data. The routine's current version becomes v2; v1 stays runnable. In the
runs table a version boundary is a divider; a result line present in one version and not the other shows as a gap;
the narrative compares runs within a version and, across a boundary, says the method changed and compares what both
versions share.

The composer under a run's view is disabled; under a loaded favourite it does what it always did — a new chain on
that thread — and has nothing to do with the routine.

### F5 — Manage — built

Run (F2); rename; delete (the routine and its runs; the origin favourite stays); download the current version's
script as `.py` (for the analyst in another domain who wants it in a notebook; the INPUTS block at the top with the
defaults); *made from the analysis of … ↗* (the origin favourite, into the main panes; "no longer in Saved workflows"
when it is gone); the versions list with change notes; the runs table and the runs list (S2). Deleting a favourite
that is a routine's origin will warn (step 5); until then the routine stays runnable and marked. No sharing between
users in this version.

## 6. The model's two calls, and where it is absent

| call | seat | when | input | output | guard |
|---|---|---|---|---|---|
| Promoter | Promoter (else Analyst) | Save as routine; a next version | question, summary, the data record, the cells, the ledger, (the manifest on a next version) | edits + inputs JSON | the edits apply whole per input; run zero must reproduce |
| Narrator | Rewriter | after a run with a comparison | question, purpose, summary, two runs' data and inputs, comparison table | a short note | numbers guard against both results tables |

The run itself never calls a model, and nothing can be asked of a run. Continuing the analysis is an ordinary chain in
the origin's thread and costs what a chain costs at the mode chosen. Both prompts are generic: no sport, no dataset,
no column name in them (the standing-rule scanner in tests/analyst/test_analyst.py covers `analyst/routines.py` and
`bambooai/routines_host.py`).

## 7. Screens

Placement: a **Routines** entry on the rail (between Saved workflows and the Dataset cache, with a count), opening a
manager in the shape of the Saved workflows manager; the existing **Save** pill on a finished chain, whose menu
offers *Save as favourite* and *Save as routine*; the **Routine** button on every saved workflow's card — grey when
no routine was made from the analysis, lit with the number of versions born from it (a click opens the manager on the
routine, or Save as routine when there is none); a run shows in the main panes exactly as an analysis does, one run
per view, the arrows beside the chain position moving between the routine's runs (run 0 included when verified), no
Save (a run is recorded as it completes), the composer disabled. `tools/routines_screens.py` renders the built
screens in the real page (dark and light) with the backend faked, and checks their state.

### S0 — Save

The Save pill's menu: *Save as favourite* ("this chain, in Saved workflows"; "Saved as favourite" once it is one) and
*Save as routine* ("a method to run again on new data · saves the favourite too"). On a chain of a thread that is a
routine's origin the second item reads "next version of '<routine>', or a new one"; on a chain a routine was made
from, "made from this chain: <name> v1 · again, or as a next version".

### S1 — Save as routine (dialog)

```
┌ Save as routine ────────────────────────────────────────────────┐
│ from this chain · 5 cells · 6 results · 1 figure · $0.04        │
│ Name    [ Altitude pace correction, within athlete           ]  │
│ Purpose [ How much slower is the same runner at 2,100-3,100 m  ] │
│ Data    (File) EEDR_sessions_laps_enriched.csv · 22,705 rows    │
│         Checked once on this chain's own data before it is     │
│         created.                                                │
│ Inputs  Hard-effort threshold   155       the exploration …  ☐ keep fixed │
│         HR bands   130, 145, 155, 165, 175   the exploration's bands  ☐  │
│         Left as they are: the 1-km lap window · the bootstrap …  │
│ Results ✓ log speed, abroad vs Ethiopia, athlete FE …   cell 2   │
│         ! cell 4: typed, not computed   [keep as a constant] [drop] │
│ The routine is checked once on this chain's own data before it  │
│ is created; the chain is saved as a favourite, and the routine  │
│ links to it.                        [Cancel] [Create routine]   │
└─────────────────────────────────────────────────────────────────┘
```

While the promoter works the body reads "The analyst is reading the chain and naming its inputs… · Analyst on
<model>" and the pane shows the quiet card; a refusal (run zero differed, the script not understood) shows in the body
with *Try again*. On a chain of an origin thread the body opens with *Next version of "…"* / *A new routine* and the
*What changed* line, and the button reads *Make it v2*.

### S2 — Routines manager (modal, like Saved workflows)

Left: the routines (name; source · version · runs · date). Right: the name; "File · 49 columns · v1 · made from the
analysis of 10 Oct ↗ (a favourite; continue it there)"; the actions (Run, .py, Rename, Delete); Purpose, Question,
Checked (verified / unverified, run zero's line); Inputs (asked before each run: label, default, where it comes
from); Results (compared run to run, with their cells); Versions (newest first, with the change notes); Runs (built):
the results-across-runs table — a column per run that ran (run 0 first; a failed run left out), the manifest's lines
as rows (a dropped one left out), a cell the estimate with its interval on hover and, in a narrow column of its own
between two runs, the mark of the second against the first (↑ ↓ for a change whose intervals do not overlap, = when
they do; · in a cell for a line the run did not print) — it sat beside the second number until 2026-10-10, where it
read as a misplaced Trend; a Trend column with the sparkline from the third run on, not before; under it the runs
list, newest first (the date, the data, the version, the inputs, a status chip — *ran ·
3 of 5 moved*, *reproduced*, *failed*), run 0 last; each opens the run in the main panes.

### S3 — Run (dialog) — built

```
┌ Run: Session start hours ───────────────────────────────────────┐
│ v1 · 2 runs so far                                              │
│ DATA                                                            │
│ (•) Load from Intervals.icu  [2026-08-12] → [2026-10-10]         │
│     the original's 59 days, ending today · with summary,        │
│     wellness · metrics as the original                          │
│ ( ) The data loaded now  (Intervals.icu) 10,200 rows · 47 cols  │
│     △ 2 of 49 columns empty in this data: power, temperature;   │
│       wellness absent in this data - the method will see an     │
│       empty table there                                         │
│ INPUTS — the only things that change; the method runs as saved  │
│   The hour band counted   [9, 11]   the analysis counted 9-11   │
│ COMPARE WITH   (•) run 2 (10 Oct, the run before)  ( ) run 0    │
│ The method runs as it was saved; only the inputs change. The    │
│ run is recorded as it completes.            [Cancel] [Run]      │
└─────────────────────────────────────────────────────────────────┘
```

Endura: *Load from Endura* with the race list (the original race selected; its auxiliaries named). A file: *Upload
a file* (the original's name shown) beside *The data loaded now*, which is the default when something is loaded. The
line under the data loaded now is green when nothing differs, a note (△) when a column will be empty or a file is
absent, red when there is nothing to run on - the one case *Run* is off. While a load runs, its progress shows
under the choices (*Downloading activities… (12/60)*); a load that fails leaves its message there.

### S4 — A run in the main panes — built

The strip reads *Routine · run 3 · v1 · Against the run before: run 2 — 3 of 5 moved beyond their intervals*; the
id line *Routine: <name> · Run: 3 · v1 · Dataframe ID*. Left pane rows, as an analysis: *LOAD Intervals.icu
2026-08-12 → 2026-10-10 · summary, wellness* when the dialog loaded, *CHECK intervals — 2 of 49 columns empty in
this data: power, temperature; wellness absent in this data*, *RUN run 3 · v1 · 5 cells — ran: 6 result lines · 1
figure · 31 s*, *COMPARE with run 2 — 3 of 5 moved beyond their intervals* (step 3 adds the narrative card), then the
closing card: *Run 3 complete · <routine>* with Results 6, Moved 3 of 5, Figures 1, Time 31 s, the status line, the
line against run 2, and Comparison → Plots (1) → Results → Data links (What changed with step 3). A failed or
differed run's card is in the warning tone. The position reads "run 3 of 3" and the arrows move between the
routine's runs, run 0 included when verified (its view: the version's own check, its line with the estimate and the
interval, nothing it is against); while a run is under way the position reads "run 3 · running" and both arrows are
off. No Save pill: the run is already recorded. The composer is disabled, its placeholder saying why ("A run is a
record: to go further, open the analysis it was made from"); it is enabled again on a new thread or when a favourite
is loaded.

Right pane tabs: **Comparison** (the table of this run against the reference: label, the reference's estimate and
interval, this run's, the change, the mark — moved / within, or changed / same without intervals, missing; the
legend says nothing there is written by a model; a failed run's error block above the table), **What changed** (the
note, step 3), **Plots**, **Results** (printed output), **Data** (what the run ran on: source, how it was loaded,
name, rows, range, the method's file names and what they opened in this run, a file absent, the columns with their
types).

### S5 — Save on a chain of the origin thread

The coach opened the analysis from the routine's card, continued it, and on the chain that has what the routine
should do from now on hovers *Save*: the second item reads "Save as routine — next version of '<routine>', or a new
one".

### S6 — The next version

The Save-as-routine dialog with one section first: *Next version of "…"* (on) or *A new routine*, then *What
changed* (one line), then the dialog as in S1 with the inputs carried over. The footer says the new version is
checked on this chain's data before it replaces the current one, and that earlier versions stay runnable; the button
reads *Make it v2*.

Words on screen, chosen for coaches: Save as routine, Run, Compare with, What changed, Purpose, Next version, made
from the analysis of. Not: promote, manifest, procedure, replay, amend, update, investigate, ask.

## 8. Storage

Files beside the favourites, in both editions: `storage/<user>/routines/<id>/routine.json` and
`runs/<tag>/run.json`, `stdout.txt`, `fig_n.json` (the tag `v<version>_<number>`; run zero `v1_0`). On the
executor's side a run has its own folder, `datasets/<user>/routines/<id>/<tag>/`: the copies of auxiliary files made
to fit, the empty tables standing in for absent ones, anything the method writes under the datasets folder, and its
`DS.save` datasets - never the person's cache, which lists only `datasets/<user>/` itself and its `generated/`.
Sizes: a run's figures are the replay's Plotly JSON (hundreds of kilobytes each); a deleted routine removes its
storage folder (the executor-side folders are left to the executor's housekeeping). No pruning in this version.

## 9. Editions

Everything above is the same in both editions. The integrations need the executor container, as they do today; a
file routine works on the local kernel too (`--compute local`), because the runner uses the same executor client the
replay uses — the end-to-end walk (tests/e2e/test_stack.py) makes and runs a routine in both editions. The
integrations' path is walked end to end too (tests/e2e/test_integrations.py): the stack's fake Intervals.icu and
Endura (tools/stack/fake_apis.py, with FIT files the executor's own parser reads, served from a calendar with the
loaders' variation built in - a window without a power meter, a device that stopped logging temperature, a wellness
log that ends, a flat race without power or climbs), the real loaders, a routine made on one window and run on the
next, then one made on one race and run on another.

## 10. Retired by this feature

The v1 *Execute* on a saved workflow (a new analyst chain seeded with the script, costing a run, nesting the script)
has left the favourites' cards (the Routine button stands where its button stood); `chain_replay_utils`, the
replay view in workflow-replay.js, the dataset-name mappings and the two canned sentences in `app.py` ("User updated
the data in the datasets…", "User manually edited your code…") go with step 4. *Edit and run* on the Code tab goes
with them — coaches do not edit scripts; the analyst in another domain downloads the `.py`.

## 11. Build order and acceptance

1. **Save as routine** — built (2026-10-10): the Save menu, the dialog with Purpose, the promoter, run zero, the
   records, the favourite saved too, the origin link, the Routines rail entry and manager (without the runs table),
   the favourites' cards' Routine button, the composer lock. Accepted by: the pure module and the host's path over a
   real kernel with a scripted promoter (tests/analyst/test_routines.py), the instance and the routes over the fake
   model layer (test_app_path.py), the markup (test_routines.js, test_pane.js), the real page with the backend faked
   (tools/routines_screens.py), and the end-to-end walk in the real app in both editions (tests/e2e/test_stack.py:
   the scripted promoter names the regime as the one input, run zero reproduces the chain's line through the
   executor, the routine is stored and linked, the manager and the card show it). The first live test is a Titanic
   chain with the real promoter.
2. **Run on current data** — built (2026-10-10): the runner, the fit and value checks, results by position, the
   run record and its files, the comparison, the run dialog on the data loaded now, S4's rows, strip and tabs, the
   arrows between runs (run 0 included), the composer locked, the manager's runs table and list. Accepted by: the
   pure module (the fit, the value check, the status, the comparison with the overlap flags, a failed cell named)
   and the host's path over a real kernel (the same data reproduced; a column dropped refused by name before
   anything runs; a script error *failed at cell n* with the run kept; a timeout) in tests/analyst/test_routines.py;
   the instance and the routes over the fake model layer (test_app_path.py); the markup (test_routines.js); the real
   page with the backend faked (tools/routines_screens.py: the dialog, the dialog refusing, the view, the view live,
   the manager's runs); and the end-to-end walk in both editions (tests/e2e/test_stack.py: run 1 on the same data
   reproduces run 0, run 2 with another input is compared with run 1, the arrows step through runs 0–2, the composer
   locks and comes back with a favourite, a file without the `soil` column is refused in the dialog with nothing
   recorded, the files on disk). The first live test is a Titanic routine run on its own data, then on a copy with
   a column dropped.
   **Rebuilt (2026-10-10, after the first live run on a new Intervals window)**: the routine loads its own data as
   the original load did (the dialog, per source, through the Data tab's own loader routes) and makes it fit the
   recorded shape before the cells run - the auxiliary files bound by kind, copies with the missing columns added,
   empty tables for absent files, the executed text carrying this run's paths, `df` conformed - the stored script
   never edited; a column missing is said and the run goes ahead (refused only with nothing to run on); the run's
   own folder on the executor's side; the LOAD row and the Data tab's bindings. Accepted by: the pure module (the
   kinds, the binding, the bound text, the conform prelude run on a frame, the shape probe on files), the host over
   a real kernel (a method reading a dated summary file, run on a later window's file with a column fewer, and with
   the file absent), the routes, the markup, the screens (the Intervals dialog), and two end-to-end walks: the file
   routine (the dialog's upload; the file without `soil` runs to a kept failure at the cell that divides by zero,
   named) and the integrations (above, §9). **The second live run** (a Jan–June window after a Jul–Oct original)
   stopped on the promoter's own edit — the loaded window made an input and written into the summary's name — met
   by §4.7: the binding by kind, the refusal, the prompt rule; the integrations walk's scripted promoter now makes
   the same proposal and the make dialog's notes show it refused.
3. **Narrate** — the Narrator, the guard, the What-changed tab and card. Accepted when: a narrative's numbers all
   come from the two tables; a run without a comparison (run zero) gets no narrative.
4. **Say what differs; fail well** — the differences said in full sentences from the shape probe (the rows each
   file has, a column empty, a file written empty), the lines printed before a failure compared, the failed cell's
   code beside the traceback; the Dataset cache's pick in the file dialog; retirements (§10). Accepted when: the
   e2e walks show the sentences and the partial comparison; the Intervals dialog is exercised on dev with a real
   key.
5. **Versions** — the next-version choice is built; the inputs carried through the manifest, the boundary in the
   table, the warning on deleting an origin. Accepted when: v2's inputs keep their keys; the runs table shows the
   divider and the gaps; a deleted origin leaves the routine runnable and marked.

Each step ships as its own patch, tested on dev before prod, the standing method.

## 12. Open decisions

- **Run zero when the original data is gone.** Built as: create unverified and say so; the first run on data tells.
- **Data that does not fit.** Rebuilt 2026-10-10: a column missing is added empty and said, a file absent stands
  in as an empty table and is said; the coach decides. The one refusal is data with none of the method's columns:
  nothing ran, nothing recorded.
- **The executed text.** A run substitutes, in the stored script's text, the recorded file names and any path under
  the datasets folder with this run's paths. Chosen over shadowing pandas' readers (a cell may `import pandas as pd`
  again, and a patch in the executor's process would outlive the run) and over changing the working directory (the
  executor serves other requests meanwhile). A loader's file name is matched by its kind when the rest of the name
  differs (§4.7), so a name the promoter rebuilt around an input still binds; a path built at run time from pieces
  with no loader prefix in any one literal is not caught; the record shows every substitution made.
- **Typed text in titles and labels** (2026-10-10, the first run that completed on a new window): a figure's title
  carried the original window and count, typed by the analyst (*91 sessions, 13 Jul - 7 Oct 2026*), and the run
  on Jan–June shows it unchanged. Prose is not data: the mechanics bind files and conform columns, they cannot
  rewrite a sentence. For new analyses the contract clause (§4, 2026-10-10) has the range computed into a variable
  and formatted into the title; for routines already made, the option is the promoter pointing at typed ranges and
  counts in titles as it points at constants. Parked by Palo until the mechanics are settled. Where the promoter
  *did* make the typed period an input, §4.8 (2026-10-11) now writes it from the data; what is left is text the
  promoter did not touch (a count, a place name, a fixed offset in a label).
- **How many runs to keep.** All, for now; the table and storage will say when that is wrong.
- **Auxiliaries that are untickable.** Allowed with a warning (proposed), or fixed as in the original.
- **The parameter cap of five.** A guess at "simple"; the first live promotions will test it.
- **The promoter's edits in practice.** The scripted promoter edits exactly; a model may misquote a fragment, and
  such an input is then left out with a note. The first live promotions will show how often, and whether a second
  pass that hands the model its failed fragments is worth its cost.

## 13. The simulation (2026-10-10), and what it changed above

Before anything was built, the whole path was simulated in the sandbox on one real chain: the Sonnet 5.5 run of
2026-10-08 (five cells on the EEDR laps file, ten RESULT lines, one of them typed, one figure, a seeded athlete
bootstrap), its cells rebuilt from the run log, a synthetic dataset generated from the DATA block's 49 columns, the
chain's script assembled by `replay.assemble`, the promoter's rewrite done by hand under §4, and the runner, the
fingerprint check, the comparison and the narrator's input written as sketches. What came out, and holds in the
build: the assembled script runs as it is on data of the right shape; three inputs for that chain (the hard-effort
threshold, the HR bands, the athletes excluded), under the cap; run zero reproduced nine of nine kept lines by
position; on a later window every change stayed within its interval, on a shifted window four of nine moved with the
overlap test right each time; a file without one column was refused by name; the script must carry no values (the
first attempt's defaults overrode a run's values); the typed mark comes from the kernel's records, not from the
replay's output; chains that printed their result lines by hand have no records and nothing to key by position.
