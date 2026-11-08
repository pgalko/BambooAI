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
  each file's columns with their types and its row count, read at promotion while the files are still there (the
  table's rows, read whole - 2026-10-16, patch 0171: a line count had put a passage's every line on the CHECK row);
  `span`, the period the frame itself covers (its date column, first and last dates), read by the same probe.
- `parameters`: at most five, each `{key, label, type (number | numbers | date_window | choice | toggle), default,
  origin ("the exploration used …"), column? (choice), multiple? (choice), derived? (span | window)}`. The script
  reads `INPUTS[key]`; the runner writes the `INPUTS = {...}` block at the mark before each run. A derived input is
  not asked: the run writes it from the data (§4.8).
- `results`: the expected RESULT lines in order, each `{cell, index, label, typed, dropped, estimate, low, high,
  unit, direction, name?}` — the identity of a line is `(cell, index)`, never the label. `typed` comes from the kernel's
  records; a dropped line stays in the manifest, so the check by position still maps the chain's lines to the
  routine's. `name` is the promoter's short name for a compared line (§15), shown wherever the line is; `label` stays
  the wording the chain recorded.
- `figures`: how many the script draws, and which cells. Since 2026-10-11 a chain draws in one cell, the figures
  step's after the report (a cell that draws during the analysis is not run), so a routine's figures are that
  cell's; the report's *Figures* section cites it as `[fig n]`, which is how the assembly reaches it.
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
   refuses: nothing to run on for that input. **A column the data never had is the method's own** (2026-10-15: a
   live promoter declared a keyword list over `head`, a column the script computes from the plan notes, and every
   run was refused with "column head is not in this data"): the record knows the data's columns at promotion - the
   frame's and every probed file's - so a choice over a column outside them loses its column, at promotion and
   again at every check for routines saved before; its values go to the method as given and are not looked for in
   the data, and the proposal's notes say so. A record that cannot say what columns the data had (none recorded, a
   file never probed) leaves the inputs as they are.
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
what still arrives as a literal. What the first live routine showed arriving anyway (2026-10-16, patch 0173): a
month read off the data typed as a literal from cell 6 on, the count of complete months typed as a loop bound
(`rng.integers(0, 11, 11)` over `c.index[i]`, an IndexError on a nine-month window), and a figure cell that typed
the ledger's estimates as its points. The promoter's rule 2 now says a count the data determines, used as a bound,
an index or a divisor, becomes that count (`len(...)`), not an input; the figures contract says every number
drawn or written comes from a variable, never typed - a figure of typed numbers is a picture of one run. The
all-or-nothing rule for an input's edits stands (an input is never half made); the promoter's edit that named a
cell without the literal cost that routine its `peak_month` input, and the note said so.

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
   **The path's cells are those computed on the chain's data** (2026-10-12, `Notebook.computed_cells`). The data
   loaded can change between a chain and its follow-up — a routine's run loads another window, a file is replaced —
   and the earlier chains' cells then ran on data that is no longer there: a follow-up asked after the change starts
   in a fresh kernel on the data loaded now; its ledger keeps the earlier chains as context, marked *on other data*
   with their cells named as not in the kernel (SHOW n still opens one from the record), without their names line;
   cell numbering continues along the path; its replay, its figures step and a routine made from it use its own
   cells, and the proposal's notes say what it continues. *The same data* is the same frame (its id) or the same
   data loaded again — the same file name, rows, column names, period and loader details under a new id
   (`notebook.same_data`): an upload gets a fresh id every time, so a favourite continued in a new session with
   its file uploaded again is the same data, rehydrated and continued as before; the frame's id alone decides
   whether the warm kernel can be kept (a kernel holds one frame object). An earlier chain without a data record
   (from before 2026-10-10) counts as on the same data. The first live case: an hour-of-day chain on one window,
   the window replaced by the routine's run, a temperature follow-up in the warm kernel (with `df` and the names of
   the earlier window, while the DATA block described the new one); the routine then re-ran all seventeen cells on
   the new window, the hour-of-day line that joins the summary file with the frame could not reproduce, and the
   routine was refused. Run zero's "the chain's data is still loaded" is the same judgement, so a chain whose file
   was uploaded again is verified on it rather than created unverified.
2. **The promoter**, one call on the Promoter seat (its own entry in the model config since 2026-10-10 — a moderate
   effort and a roomy `max_tokens`, because the reply is a JSON object of edits that a seat tuned for long reasoning
   can spend its whole allowance thinking about; the Analyst seat when the config has no Promoter) with a generic
   prompt (`analyst/routines.py` PROMOTER_SYSTEM; no domain words, DESIGN_CHECKLIST C5): name the constants that
   would change on other data of the same shape; make the data's own range the data's range; propose each remaining
   constant as an input of one of the five types, at most five, fewer is better; leave a loader's file name exactly
   as it is and never make the loaded period an input (§4.7); rewrite as find/replace edits; leave the method, the
   markers and every RESULT call otherwise untouched; say which RESULT lines a run compares and name them (§15);
   return JSON, kept short. A reply that cannot be
   read is asked for once more, then refused ("the script was not understood"); a reply cut at the seat's token limit
   is asked for once more, shorter — one with nothing but reasoning too, with the note that reasoning took the
   allowance (2026-10-12: the same prompt, sent again by the person, came back whole; the reasoning's length varies
   from call to call) — and the refusal then names the cause and the seat to adjust. A default written as a list in
   text (`"[18, 26]"`) is read as the numbers. The cost tier's Promoter runs at *medium* effort (a seventeen-cell
   script at *high* spent the whole allowance thinking). The call runs on a chain id of its own, so the hosted
   edition charges it as a query; the pane shows it as a quiet *Routine* card with the seat and its model.
3. **The dialog** (S1) shows the proposal: name (the promoter's title), purpose (prefilled from the question; one
   line for the card and the narrator), the data (source chip, name, rows, columns; whether the chain's data is
   still loaded), the inputs as rows (label, value now, where it comes from, "keep fixed"), the expected results with
   any *typed* line flagged ("the numbers were typed into the call, not computed — keep as a constant / drop"), the
   figure count, the promoter's notes. On a chain of a thread that already has a routine, the dialog opens on the
   choice *Next version of "…"* / *A new routine*, with a *What changed* line: the routine's own origin chain
   defaults to its next version, the Name field holding the routine's name; a later chain of the thread ("A routine
   was made from an earlier chain of this thread") defaults to a new routine, the Name the promoter's title. The
   button (*Make it v2* / *Create routine*), the note under it, the *What changed* line and the Name follow the
   choice (2026-10-12: they were written once, so a new routine was created under a button reading *Make it v2*,
   and a next version took the promoter's title as the routine's new name; a next version now keeps the name unless
   the person typed another). Create / Cancel.
4. **Stored at once, run zero behind the dialog** (rebuilt 2026-10-15, patch 0160: run zero re-executes every cell of
   the chain — nine minutes on the first live routine over a heavy chain — and nobody waits for a dialog that long).
   On Create the routine is stored, v1 (or the next version) with its manifest and `run_zero.status = verifying`,
   the dialog closes, the chain is saved as a favourite (silently, no rank) when it is not one yet, and a toast
   says "Routine made: <name> · v1 · verifying on the original data in the background". Then, in a thread of the
   app, the runner executes the script with the defaults on the chain's data through the executor (the replay's
   path and timeout). The RESULT lines that come back are checked by position against the chain's records:
   identical numbers *reproduced* (verified); a different count or a different number *differed*, an error *failed*
   — the verdict and its line land on the stored version (`verify_zero`; the output and figures saved as `v1_0`),
   and the page, which follows the routine every three seconds, says it in a toast and refreshes the manager if
   it is open. No pane row: a row emitted after the dialog's stream closed would land in the next request's. The
   refusal creation used to give moves to the run: **a run and the precheck are held** while the version is
   verifying (*still being verified on its chain's own data — run it when it has settled*) and for good after a
   verdict that did not reproduce (*run zero did not reproduce the chain's analysis (…) — the method is not run on
   other data; delete the routine, or make it again from the chain*), `zero_holds`; the manager's Run button is
   disabled with the reason, the card's chip pulses *verifying…* or reads *did not reproduce*, the side item says
   so. With the chain's data no longer loaded, the routine is created *unverified* and says so, and may run (its
   first run shows whether the method still runs). A chain from before the data record takes the data loaded now
   for its own. The library's foreground mode (`create(..., background=False)`, the tests' default) keeps the old
   contract: a method that does not reproduce is refused and not kept.
5. The run dialog says what a run will take before Run is pressed — *the last run took 8 min — expect about as
   long* (from the last run, or run zero's time) — and the pane's REPLAY row says *12 cells · about 7 min* from
   what the cells took the first time: the method's own cost, told rather than discovered.

### F2 — Run — built (rebuilt 2026-10-10: the routine loads its own data and makes it fit)

Entry: *Run* on the routine (S2). The dialog (S3) opens on the way the original load asked for its data (the
version's data record, `load`), and offers the data loaded now beside it.

1. **The load, as the original did.** Intervals.icu: a window of the original's length ending today (clamped to
   what the plan allows, and the dialog says so), the metrics and the auxiliary kinds as the original - through the
   same loader job the Data tab uses, with its progress shown in the dialog. Endura: the race list, the original
   race selected. SweatStack: the window shifted, the sports and subjects as the original. A file: an upload, or
   a file from the Dataset cache (step 4, 2026-10-11: the dialog asks `/routines/cache_files` for the frames the
   executor's cache holds that came from a file - uploads, newest first, with their rows and the day - and shows
   the choice when there are any; the pick is taken through `/cache/load_primary` as a cached window is, the pill
   as an upload's, the LOAD row and the record's `load` read *from the Dataset cache*; without an executor the
   choice stays hidden). A load clears what it replaces first (2026-10-11: the run's pills used to stack beside
   the old ones) — a load from Intervals.icu, Endura or SweatStack clears the primary and the auxiliaries, an upload
   the primary only, each pill removed the way its × removes it (the session's reference dropped, the file left in
   the cache). **The cache first** (2026-10-11: a run re-downloaded a window the Data tab had loaded minutes
   before): as the dialog opens and as the window or the race changes, the page asks `/routines/<id>/cached`, which
   reads the executor's cache listing (`/cache/inspect`: the frames with their source, window and metrics; the
   auxiliary files on disk) against the routine's plan — the same source, the same window and metrics (Intervals)
   or the same event (Endura), and every auxiliary file of the kinds the routine wants there under the loader's
   name for that load (`cache_match`). A line under the window says *✓ this window (… → …) is in the cache (10,200
   rows, with summary, wellness) - no download*, or why not (*not in the cache*, *in the cache without wellness*).
   **A cached load that contains the window is a hit too** (2026-10-11: Feb–May inside a cached Jan–June was
   downloaded again, and used whole it would have shown the cached window's numbers — min/max, counts, all of it):
   the smallest such load is taken, and the run *cuts it to the window before the method runs* — the frame by its
   date column (the one recorded at promotion), the summary by each ride's `start_date_local`, the wellness file by
   its `date`, the intervals file by the rides kept, the context file by its `date` and the codes file by the
   passages the cut context keeps (2026-10-16), any other file by a column of dates it finds or by the rides, or
   whole and said — each cut file written at its mirror path in the run's folder (since 0159; before, under the
   loader's own name for that window), with the recorded columns it lacks added, so the method sees what a fresh
   download of the window would have given it (`CUT_RULES`, `_ROUTINE_CUT` in the prelude; the value check cuts
   the same way). **`CTX` in a run is defined over the run's own context and codes files** — the mirror copies,
   cut, or the empty stand-in for one this load lacks — by the run's prelude, last of all (2026-10-16, patch 0170:
   the host's kernel prelude points `CTX` at the files loaded now, which on a cached load are the whole load's;
   Palo's routine, cut to four months, read seventeen months of words against four months of rides and fell over
   on the months that had words but no rides). The line reads *inside the cached load … → … - it will be cut to the window, no
   download*; the LOAD row *cut from the cache*; the CHECK row *cut to … → … from the cached load … → …*; the
   record's `load` carries `cached_from`, its `date_range` and `rows` are the window's as the method saw them, its
   `bindings` read *cut*. The Data tab afterwards holds the cached load itself (that is what the executor has), and
   its pills say so; the record says what the run used. The one approximation: a session that starts on the
   window's last day and runs past midnight keeps its records (the loader would too). **Whose data the cache
   holds** (2026-10-11, Palo: a coach who changes the Intervals key to look at another subject must not be served
   the first one's windows) is settled where the data lives — in the executor (image v52): the Intervals loader
   marks each frame it caches with a one-way mark of the key that loaded it (`key_mark`: sha256 of the key, twelve
   hex characters, never the key — `metadata.key_mark`) and writes that load's auxiliary files under a folder of
   that name (`datasets/<user>/<mark>/activity_summary_<window>.csv`), so two keys' loads of the same window sit
   side by side; `/cache/inspect` lists the key folders with each file's `key_mark`. The app computes the same
   mark from the key in use (`key_fingerprint`) and the cache check uses a frame only when its mark is the same,
   looking for its files in that folder; a frame marked with another key is said (*loaded under another key - it
   will be downloaded*), one from before the loader marked them is downloaded this once. The Intervals route puts
   the mark on the load record (`load.key`), so a routine and each run say which key they were made and run under.
   **Since 2026-10-29 (docs/DATASETS_DESIGN.md, step 1) a load is the subject's, not the key's**: the loader learns
   the athlete's id and name from the profile before it writes anything, keeps the files and the store under
   `datasets/<user>/<source>/<athlete id>/` with a record of the marks that have loaded that subject
   (`subject.json`), and `/cache/inspect` lists the subjects (`subjects`) and each entry's `folder`; the load record
   carries `load.subject` (source, id, name) beside the mark. The cache check resolves the key in use to its subject
   by those records (`subject_of_key`) and matches frames by the subject's id, so a rotated key is served its
   subject's cached windows once it has loaded; a key that has not loaded yet is still *another key*, and a window
   the cache holds for another subject is said so (*loaded for another subject - it will be downloaded*).
   **Since 2026-10-30 (docs/DATASETS_DESIGN.md §17, step 3) the run dialog names the athlete**: a select above the
   window (the athletes with a key, the original's picked); the cache question and the download carry `athlete`,
   so the match is that athlete's cached windows under their own key; each run's summary carries `data.subject`,
   and the comparison (`reference_run(…, subject_id)`), the manager's history and the arrows (`run_numbers(…,
   subject_id)`) stay within one athlete's runs - run zero counts as its athlete's; one naming none (from before the
   subject was kept) is nobody's but the subject-less runs' (0252). The Comparison tab names the athlete and each
   run's window (`against_data`, the reference run's light record, rides on the view and the run's answer).
   The kinds a run's load can ask for are summary, wellness, intervals, context and, since 2026-10-15, plan - the
   planned workouts table written with the context (docs/CONTEXT_DESIGN.md §3.1a), cut to a window by its `date`.
   **Below the cache, the store** (2026-10-15, docs/INCREMENTAL_LOADS_DESIGN.md): a miss no longer downloads the
   window whole - the executor keeps every activity it has parsed under the key's folder and fetches only the
   activities a window asks for that it does not hold (or whose file changed), so a run on a window a day wider
   than a cached one costs one file, not a year's.
   A frame taken from the Dataset cache — the Data tab's cache, or a routine's run reusing a cached window — is
   recorded with the cached frame's own load (its source, window, metrics, auxiliary kinds and key mark, from the
   executor's metadata; `_load_of_cached`), marked `cached`, never as source "cache" (2026-10-12: a chain analysed
   on a window a routine's run had taken from the cache made a routine whose plan read *file*, and its run dialog
   offered an upload in place of the window; `load_plan` reads such an older record by the data's own source).
   The cut, the derived inputs and the binding go by file name, so the folder changes nothing for them; the DATA
   block shows the longer path. Endura's files are the event's, at the user's folder: no such check. Chosen over an
   app-side ledger of loads with file stamps (built as 0125/0126, set aside): identity recorded by the loader is
   direct and stays right; the ledger reconstructed it from timing and the files still overwrote each other;
   on Run the page asks again for the window as it stands (the line's earlier answer can lag behind a date typed
   and committed by the click on Run itself — Safari commits a date on blur) and a hit is taken through the Dataset
   cache's own routes (`/cache/load_primary`, `/cache/load_auxiliary`), the pills as a load's, and the LOAD row and
   the run's record say *from the cache*. SweatStack's entries do not
   say which subjects they hold, so they never match; the local edition has no executor cache. The page sends the
   load as it did it (`load`: the source, window or event, kinds, `cached`) with the precheck and the run, so the
   record says what was loaded rather than the cache route's *cache*. The Data tab's pills and the frame view then
   refresh as the Data tab refreshes them, so the session's data is the run's data afterwards, as it was after a
   v1 replay. *The data loaded now* is the other choice when something is loaded (the default for a file routine).
   **What a load can be asked for is one registry** (2026-10-16, patch 0181): `LOAD_KINDS` in `analyst/routines.py`
   lists the kinds per source, `LOAD_BRINGS` the kinds a load brings beside them without being asked (the codes
   beside the context), and `LOADER_FILES_MAX` is the most files one load can bring. `load_plan` keeps a routine's
   kinds by it, `cache_match` wants the brought files by it, and the app's auxiliary limit is derived from it
   (`MAX_AUXILIARY_DATASETS = LOADER_FILES_MAX + UPLOAD_ROOM`, handed to the page as `window.MAX_AUXILIARY_DATASETS`)
   — so a new kind is added once, with its prefix in `AUX_KINDS` and its cut rule in `CUT_RULES`, and never trips the
   limit again (the sixth file of a load had, when the limit was a literal). The heads the DATA block shows keep to a
   budget together (`AUX_BLOCK_CHARS` in `bambooai.py`): past it a file's entry is its path and columns.
2. **The check** (`precheck`): the data against the recorded shape - the columns the method ran on, by family
   (number, date, text): *fits the routine (49 of 49 columns)*, or *2 of 49 columns empty in this data: power,
   temperature* (a note - the run adds them empty), or *none of the routine's 49 columns is in this data - nothing to
   run on* (the one refusal); the auxiliary files bound by kind to this load's (*wellness absent in this data - the
   method will see an empty table there*); the chosen values of the choice inputs against their columns. The inputs
   as widgets by type, at their defaults. *Compare with*: the run before or run 0. Pressing *Run* loads first when a
   load is chosen, then checks once more with the values as typed; what fails is said in the dialog and nothing
   runs. **What differs is said in sentences** (step 4, 2026-10-11): the dialog's line says the frame's rows against
   the original's (*the same 5,860 rows as the original* / *2,184 rows where the original had 5,860*); the CHECK row
   at the run adds, from the shape probe, each bound file's rows against the original's, the columns added empty and
   the columns the file has but left empty, a file empty in this data, a file that could not be read
   (`shape_sentences`) - beside the fit line, the absent files, the values and the cut. On a cached load around the
   window the probe cuts the copies as the prelude will and reports the rows after the cut, the frame's too
   (`frame_rows`), so the sentences say what the method sees (2026-10-16, patch 0171: they had said the cached
   load's - 517 wellness rows for a four-month window). The record keeps the
   sentences (`differences`) and the whole line (`check`); a stored run's CHECK row repeats it, and its Data tab
   lists the sentences under *Differs*.
3. **The data made to fit** (`prepare`), in the run's own folder on the executor's side
   (`datasets/<user>/routines/<id>/<tag>/`), laid out as **a mirror of the recorded layout** (2026-10-15, patch
   0159): every recorded auxiliary path exists under the run's folder (`<run folder>/datasets/<user>/<mark>/
   activity_summary_<recorded window>.csv`, `mirror_path`) holding this load's file of that kind - the bytes as
   they are, or with the recorded columns it lacks added empty; cut to the window on a cached load around it; an
   empty table with the recorded columns for a file this load did not write. The executed text is the stored
   script with every string literal under the user's datasets folder moved under the run's folder - a recorded
   path, a folder literal, a file of the person's own, a write target alike - and a loader's file named with other
   dates than the recorded ones (§4.7) pointed at the mirror of that kind's recorded file; a bare file name is left
   as it is and meets a mirrored folder. So the method reads this window's summary under the name it was written
   with, a path built as `folder + name` resolves (the first live routine over the words had read every file that
   way: the folder had become the run's folder and the bare name a full path, and the two concatenated existed
   nowhere), and nothing is ever written into the person's cache. Before the mirror the text was rewritten literal
   by literal - a recorded path to this load's cache path, a bare name to a full path, any other datasets path to
   the run's folder - three rules that were each right alone. The prelude after the INPUTS block conforms `df`: a
   recorded column this frame lacks is added empty in its type, a column whose type family changed is read back
   (`conform_prelude`), and `DS` is rebuilt on the conformed frame; it makes sure of every mirror file (a recorded
   file the probe did not copy is copied from this load's file now; a stand-in not written is written); then the
   inputs that follow the frame's own dates are written from it (§4.8). The stored script is not changed; the record
   keeps the substitutions (`bindings`: literal, mirror path, bound | placeholder | cut | cache), the files of this
   load each recorded path was filled from (`sources`), and the values written; the Data tab shows each recorded
   name against its source.
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
notice), the Comparison tab with the error block - the failed cell's code under its own heading beside the
traceback (`failed_cell` on the record, step 4, 2026-10-11) - and the result lines the run printed before the
failure compared like any other, the ones it did not reach marked *not reached* (`compare_runs(..., failed=True)`;
the COMPARE row reads *1 of 3 moved beyond their intervals before the failure, 2 not reached*). The executor
returns what a failed script printed before it failed, beside the error (image v57, 2026-10-16, patch 0176: it
had returned nothing, so through the executor every failed run read *no result line came before the failure*
while the local kernel kept the lines - the two editions now agree). Timed out -
likewise, though a timed-out script's output is lost; a result line missing or without a number - status differed, the count in the line; the stream broke -
the pane says so and the view returns to the last recorded run. The cell named is the right one with documents in
the thread too: the executor's *Error on line n* head is moved back by the kernel prelude's lines as the frames
are (a failure in cell 2 had been named at cell 3).

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
│ Tracked metrics — recomputed each run and compared with the run │
│                   before, 2 of 6 · 1 figure                     │
│         ✓ log speed, abroad vs Ethiopia, athlete FE …   cell 2   │
│         ! cell 4: typed, not computed   [keep as a constant] [drop] │
│         ▸ 4 more metrics computed, not tracked                    │
│ Custom instructions — optional                                  │
│         If you want this routine to track particular metrics,   │
│         say so here and the model building it will add them to  │
│         the list above — for example the power durations that   │
│         matter to you. It can only track what the analysis      │
│         computed; if something you ask for isn't there, it will │
│         tell you.                                               │
│         [ e.g. track the best power at 5 s, 1 min, 5 min … ] [Update the list] │
│ The routine is checked once on this chain's own data before it  │
│ is created; the chain is saved as a favourite, and the routine  │
│ links to it.                        [Cancel] [Create routine]   │
└─────────────────────────────────────────────────────────────────┘
```

The dialog speaks of *tracked metrics*, not of result lines (2026-11-08): a coach saves a routine to track particular
metrics over time, recomputed each run and compared with the run before. *track* on a set-aside line brings it into the
list, *drop* on a tracked one sets it aside. The *Custom instructions* box is §15.6.

While the promoter works the body reads "The analyst is reading the chain and naming its inputs… · Analyst on
<model>" and the pane shows the quiet card; a refusal (the script not understood, an input dropped that the script still
reads) shows in the body with *Try again*; run zero's verdict comes later, behind the dialog (F1 step 4). On a chain of an origin thread the body opens with *Next version of "…"* / *A new routine* and the
*What changed* line, and the button reads *Make it v2*.

### S2 — Routines manager (modal, like Saved workflows; redesigned 2026-11-08, §20)

Left: the routines (name; source · version · runs · date). Right: the name; "File · v1 · from the analysis of 10 Oct
↗" (the link opens the favourite); the actions (Run, .py, Rename, Delete); then one column with one scroll: the
**facts** as label and value - *Purpose* (the question when none was written), *Inputs* (none, or a line per input:
label, default, where it came from; one that follows the data says so), *Tracked* (what a run records: *9 metrics and
2 charts per run*; *Results* until §15.6), *Custom instructions* when the routine has them (§15.6), *Version(s)* (newest first: the date, the chain it came from when there are several, the verdict -
*verified, 17 lines reproduced*, or *did not reproduce — …* - the condensed code's size and time (§19: *10 cells ·
0.8 s*), the consolidation's state (§19.3: *rewritten, the next run on new data checks it* / *confirmed on run 3* /
*rewrite dropped on run 2*), *as written ↓* - or *as written* with the pass's reason on hover when the chain's code is the
one that runs - the change note after the first version); a rule; **Runs** with the
interval filter and the athlete pick (§14.6) and the table, whose rows are the runs. A set interval: the table by
unit, every row a run that opens (*open →* on hover), a unit whose runs all failed a row with the reason, the values
without a plus sign, and under it the count of the units not run with *fill them* as a link into the Run dialog on
that interval. Custom: the table by run - a column per run that ran (run 0 first), each head opening the run, the
manifest's lines as rows (a dropped one left out), a cell the estimate with its interval on hover and, in a narrow
column of its own between two runs, the mark of the second against the first (↑ ↓ for a change whose intervals do
not overlap, = when they do; · in a cell for a line the run did not print); the custom runs that failed named under
it with their reason, each opening too. No runs list, no legends, no box of its own around a table.

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

The executor image carries the key marks since v52; a hosted container recreated after the roll-out marks its
loads from then on, an older one answers "from before loads were marked" for its cached frames until it is
recreated — quiet in both editions, no coordination. The self-hosted edition rebuilds the image on the next serve
(the tag carries the build stamp).

## 10. Retired by this feature

The v1 *Execute* on a saved workflow (a new analyst chain seeded with the script, costing a run, nesting the script)
has left the favourites' cards (the Routine button stands where its button stood); `chain_replay_utils`, the
replay view in workflow-replay.js, the dataset-name mappings and the two canned sentences in `app.py` ("User updated
the data in the datasets…", "User manually edited your code…") went with step 4. *Edit and run* on the Code tab went
with them — coaches do not edit scripts; the analyst in another domain downloads the `.py`.

**Retired (2026-10-11, patch 0134).** Gone: `web_app/replay_routes.py` (the `/storage/replay_favourites` and
`/load_replay` routes), `web_app/chain_replay_utils.py`, `web_app/static/js/workflow-replay.js` and its script tag,
the replay view in workflow-modal.js with the modal's state snapshot (which served nothing else), the replay rules
in dialogs.css and the pill's `.replay`/`.replay-success` states, the replay storage handler in query-processing.js;
`/query` reads no `user_code` or `dataset_mappings` and carries neither canned sentence; `pd_agent_converse` has no
`user_code` or `replay` parameter (the question was seeded with the code as a first cell). The Code tab's Edit,
Discard and Execute are replaced by **Copy** and **Download (.py)** — the file named after the question's first
words — and CodeMirror's four CDN tags leave the page (the stack's vendor map and stub go with them). The kernel's
own `_user_code` variable (delve/kernel.py) is unrelated and stays.

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
   key. **The sentences — built (2026-10-11, patch 0131)**: the dialog's line, the CHECK row, the record and the
   stored run's Data tab (F2.2); the pure cases in test_routines.py, the host path on a later window (the summary's
   rows against the original's, the column added), the two walks (the file routine's rows as the original; the
   Intervals routine's summary rows and columns added). **Fail well — built (2026-10-11, patch 0132)**: the failed
   cell's code beside the traceback, the lines printed before the failure compared and the rest *not reached*, the
   cell named right with documents in the thread; the pure module, the host path, the markup and the stack walk
   (the run without `soil`: cell 2's code on the Comparison tab, its line not reached).
   **The Dataset cache's pick — built (2026-10-11, patch 0133)**: the choice in the file routine's dialog, the route,
   the pure filter; the hosted walk runs on a cached upload (run 5), the local walk finds the choice hidden.
   **Retirements — done (2026-10-11, patch 0134)**: §10's list, the Code tab's Copy and Download in place of Edit
   and run; the static checks (test_shell.js, test_dialogs.js, test_app_path.py) hold the retirement.
   **The first live test of the next-version choice (2026-10-12, patch 0135)** found the dialog's foot not following
   the choice and the path mixing two datasets (F1.1 above): the computation path, the dialog's defaults and foot,
   the promoter's retry and the bracketed defaults, the refusal logged; the pure cases (test_analyst.py: the
   notebook's computed cells, the ledger's marks, a follow-up's figures prompt and replay; test_routines.py: a
   follow-up promoted from its own cells, the name kept on a next version), the instance (test_app_path.py: a
   follow-up after the frame was replaced - fresh kernel, the ledger, the replay, the routine; the warm kernel on
   the same data as before; the same file uploaded again under a new id - rehydrated, verified), the markup
   (test_routines.js), and the stack walk in both editions (another file loaded, a follow-up on chain 1: its prompt,
   its cell's number, its replay of one cell, the thread file; the same file uploaded again, a follow-up continued).
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
  promoter did not touch (a count, a place name, a fixed offset in a label). The figures step (2026-10-11) narrows
  it further for new chains: its one instruction on titles is that any number in a title or a label comes from a
  variable, never typed; since 2026-10-16 (patch 0173) every number drawn or written - a point, a bar, an
  interval - comes from a variable, after a figure cell typed the ledger's estimates as its points.
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

## 14. Trends by the calendar (2026-11-06): the interval, the fill, the Summary by interval

**What was wrong.** The runs table and its sparkline follow the order the runs were made in, not the calendar: a run
on May–November made first and a run on January–June made second draw a rising athlete as a falling line. And the
windows differ in length - six months, three, a year - so even in calendar order the numbers are not a series. Both
modals do their jobs otherwise (the Summary: the routines left, the details and the runs right; the Run dialog), so
nothing is replaced: the Run dialog gains an interval, the runs their calendar place, the Summary a view by interval.

### 14.1 The interval

A run has an **interval**: *day*, *week*, *month*, *year*, or *custom*. A set interval is a calendar unit - a week is
Monday to Sunday, a month and a year are the calendar's, a day is one date - and a run on it has exactly that window
(the cut's end is inclusive: the Sunday, the last day of the month). The record and the summary carry `interval`
("week" …); none recorded is custom, so every run before this section is custom, run zero included. The dates are
where they were (`data.window`).

A set interval is compared with **the one before it**: the latest earlier run of the same interval and the same
athlete (by its window's end), which is the week before when the weeks are filled; the first one on an athlete has
nothing before it and says so. Custom runs are compared as before (the run before on the athlete, or run 0, the
dialog's choice) and are never the reference of a set interval, nor it theirs. Runs of different intervals are
different series.

### 14.2 The Run dialog (S3): the Interval row

For an Intervals.icu routine, under *Athlete*: **Interval** - *Day · Week · Month · Year · Custom* (the segmented
control); the dialog opens on the interval the routine was last run on, custom when it has no run. *Custom* is the
dialog as it was: the two date pickers, any window. A set interval has no pickers (the auxiliary kinds and the
metrics are still said under the plan):

- a line naming the last complete unit: *The last complete week: Mon 26 Oct – Sun 1 Nov 2026 (this week is not
  complete, so it is not run)*; *The last complete month: October 2026*. The current, incomplete unit is never run.
- a box, on by default: *Fill the weeks back to 3 Nov 2025 — 40 weeks not run yet, from one download; the 12 already
  run are kept*, and under it the cost in words: *about 20 minutes, in the background; the Summary shows the
  progress and each week appears as it lands. The 365-day limit of the plan is the horizon.* The time is the units
  to run times the last run's time (or run zero's). Off, only the last complete unit runs.
- the cache line, asked about the span to load; *Everything again* as before.
- *Compare with* is one sentence, no radios: *the week before (19 – 25 Oct), run 14 — a set interval is always
  compared with the one before it on the same athlete*; *the month before (September 2026) once it is filled*.
- the button says what it will do: *Run*, *Run 41 weeks*, *Run 12 months*.

Which units: the complete units whose whole window lies within the plan's horizon - today minus `max_days`
(`/intervals/get_data_limits`), the same bound the loader clamps a window to silently, which is why a unit outside it
is never asked (the clamp would hand the cut an empty frame), and at most a year back, the span the Summary's charts
cover. A complete year fits within 365 days on 1 January alone (after a common year); otherwise the dialog says *No
complete year within the last 365 days* and Run stays off. Already run: a run on record with the same
athlete, interval and window whose status is ran, reproduced or differed - a failed one is run again. Coming back
after three months, the three missing months are what the fill runs; the rest are kept. The arithmetic is the
page's, in pure functions the tests read (`build.units`, `build.fillPlan`); the server runs the windows it is given,
checked against the span.

A file routine and an Endura routine (a race is an event, not a window) have no row: custom. SweatStack: custom for
now; the same mechanism would serve once its limits are asked by the dialog.

### 14.3 The fill

One unit to run (the box off, or nothing missing but the latest) goes the way a run goes today: `/routines/<id>/run`
with `interval`, the main panes, the Comparison tab. More than one is a **fill**:

1. The page loads the span once - from the first window's start to the last window's end - through the dialog's own
   load (`loadData`: the cache, the store, the download, its progress in the dialog). The Data tab then holds the
   span, as after any run's load.
2. `POST /routines/<id>/fill {interval, windows: [[start, end] …], values, aux, load}` - `load` being the span's load
   as the page did it. The route answers at once; the work is a thread on the session's instance, one at a time. The
   dialog closes and the Summary opens on the routine.
3. Each window, oldest first, is `run_routine` with the window's dates over the span's load and `cached_from` the
   span - the cut mechanics of a cached run (`cut_window`, the probe, the prelude: the frame and each file cut to the
   window, the record saying the window) - with `interval` and the reference of 14.1, and *quiet*: no rows to the
   pane, no tabs, no closing card (the output queue is drained only by a stream; rows left on it would land on the
   next). Each run is recorded as it completes; a window that fails is a failed run and the fill goes on.
4. `GET /routines/fill` (the session's one fill) → `{running, routine_id, interval, total, done, failed, current,
   stopped, error, left}`; the page puts it in words (`fillLine`); the Summary
   polls it every three seconds while it runs, as it watches a verification, and re-reads the routine as runs land:
   *Filling the weeks · 12 of 41 done · 26 Oct – 1 Nov running · about 15 min left* with **Stop**
   (`POST /routines/fill/stop`: the window under way finishes, nothing more starts). A toast when it ends.
5. Guards: the fill stops itself when the Data tab's frame is no longer the span (`df_id` changed: the line says *the
   data on the Data tab changed*); while one runs the composer is locked with the reason (*A fill is running (12 of
   41 weeks) — the composer comes back when it ends; stop it in the Summary*), Run and Delete refuse with a toast, and
   the server answers 409 to a second `/fill` and to `/run`; a fill is not started while a query runs (Run refuses
   then, as it did). Reloading the page loses nothing: the state is the instance's; the page asks for it as it loads.
6. Said in the Summary (2026-11-06, after the first live fill: "no indication in the modal when the run has finished;
   the run button stays available during the run"): while a fill runs the header's **Run** and **Delete** are greyed
   with the reason (*a fill is running — wait for it, or stop it below*; on another routine, the one under the fill
   named: the status carries `routine_name`); when it ends, the bar goes (until 2026-11-08 its place kept the last
   word) and the toast says it - *Filled 41 weeks in 19 min*, or *Stopped after 5 of 41 weeks: …* - while the table
   shows what landed, the weeks that failed among its rows.

The dialogs keep their size (2026-11-06: "the modal changes size slightly when I click on different elements … only
the scroll bars should change"): the Summary fills the window (§20) and the Run dialog has a set height, so what comes
and goes inside them - the plan under the interval, the pickers, the lines, the filter's rows - scrolls the body and
never moves the box.

A daily fill is 365 runs; the dialog says the count and the time before Run, and that is the whole of the protection.

### 14.4 The labels

A result line's label often ends in what was true of the original data - *mean maximal power, best continuous 5s
average, all 380 activities, 2025-11-01..2026-11-04*. Wherever results are listed or tabulated (the Summary's Results
and runs table, the Comparison tab, the table by interval), the label is trimmed by one rule, no model: trailing
comma-separated segments are dropped while a segment is a date range or a count (*all 380 activities*, *380 rows*,
*n = 380*). The full label stays on hover. The record is not changed.

### 14.5 The badge

The count under the rail's Routines entry is removed (barely visible in the dark theme, no information the entry
does not give): the span in the template, `refreshBadge` and its calls, the `.rb-badge` rule.

### 14.6 The Summary (S2) by interval

*Runs* (*Results across runs* until 2026-11-08) gets a filter bar: **Daily · Weekly · Monthly · Yearly · Custom**,
each with its count on the athlete picked; an interval never run is greyed with *no run with this interval yet*; the
pick opens on the latest run's interval. The athlete pick stays beside it.

A set interval shows **a table by interval**: a row per unit run, the latest at the top (tinted), its run number
under the dates (*26 Oct – 1 Nov · run 15*; the latest run of a unit that ran stands for it; a unit whose runs all
failed is a row with the reason since 2026-11-08, and still counts as not run); each row opens its run (§20);
a column per result line, its label trimmed (14.4) and, when every label shares a prefix up to a comma, the prefix
said once in the section's head (with the unit when all share one) and the rest in the column; in each column head a
**thumbnail** of the metric over the units, from the first run to the last at their place in the calendar, oldest
left, the line broken where a unit is not run, the latest dot ringed (nothing with fewer than two points); each cell
the estimate with its mark against the row below - the unit before it that ran (↑ ↓ when the intervals do not
overlap, = when they do; the run and the interval on hover). The table sits in the body's one scroll with its head
stuck to the top (until 2026-11-08 it scrolled in a box of its own, under a legend). Under it, when units of the
horizon are missing, *40 weeks back to 3 Nov 2025 not run yet · fill them* (*in the last year* when the gaps are not
all before the first run), the link opening the Run dialog on the interval with the fill on. *Custom* is today's
table - a column per run in run order, the head *Run 1 · 5 Nov · 186 days* with the window on hover, opening the run
- without the sparkline it had; custom windows are not a series and no trend is drawn across them. The horizon is
the plan's day limit, at most a year (`/intervals/get_data_limits`, asked once per page).

**Enlarge.** A thumbnail opens the chart at full size, in a dialog of the Summary's (`#routineTrendModal`): a
calendar axis over the span - *3 m · 6 m · 12 m* of units, the months named along it - one dot per unit run at its
place, the line broken at a unit not run and a dashed box over each stretch of them (the count written when the box
is wide enough), the values written at the latest, the highest and the lowest only and every dot titled with its
run, dates and estimate with its interval; *also show* draws a second line on a right axis in its own colour; PNG
saves the chart as drawn (the colours are written into it, so the picture keeps them). Under the title a key names
each line with its scale (*best continuous 5s average · left scale*; the second dashed, *· right scale*), and with
two lines a footer says *The two lines are on different scales — compare their shapes, not their heights*; nothing
else is explained (0266: the first footer described the dots and the gaps, which the picture shows). Nothing is
computed there that the thumbnail does not have.

The runs list under the table (the latest five in a box, with status chips) went on 2026-11-08: the table's rows and
heads are the runs (§20).

**The Trend tab.** The run view's *Comparison* tab is renamed **Trend** (the closing card's link too); for a run on a
set interval its two head cells are the units with the run numbers under them (*19 – 25 Oct · run 14*, *26 Oct – 1
Nov · run 15*), and a last column *Weekly trend* carries the thumbnail of each line over the athlete's units, drawn
from the routine's runs once the tab is up (the first render is without it). A custom run's tab is as it was, under
the new name.

### 14.7 Build order and acceptance

- **Patch 0264 — the interval and the fill**: 14.1–14.5. The record's `interval`; `reference_run` by interval; the
  `/run` route taking `interval`; the fill route, its thread, status and stop, the guards; the Run dialog's row, the
  units and the plan (pure functions), the sentence, the button; the labels trimmed where they are shown today; the
  badge gone. Accepted by: the pure module (the reference by interval; a run recording its interval; the trimmed
  label is the page's, read on the mini DOM), the instance and the routes over the fake model layer (a fill of three
  windows: three runs oldest first, each against the one before, nothing on the pane's queue; stopped when the
  frame changes; the 409s), the markup (the row, the plan's sentences at known dates, the button, the badge gone
  from the template and the stylesheet), the screens tool (the dialog on *Week* with its fill), and the
  integrations walk (an Intervals routine run on *Week* with the fill over the fake Intervals: the runs land with
  their interval, the Summary shows the progress and then the runs).
- **Patch 0265 — the Summary by interval** (built 2026-11-06): 14.6. The filter bar, the table by interval with its
  thumbnails, the enlarge, Runs in a box, the Trend tab. Accepted by: the markup on the mini DOM (the counts and the
  bar's greying, the series from the runs, the rows newest first with the marks against the row below, the
  thumbnails broken at the gaps, the enlarged chart's dots, boxes, axis and written values, the prefix said once, the
  custom table without a trend, the Trend tab's heads and column, the tab's name), the screens tool (the Summary on
  *Weekly*, the enlarged chart, the Trend tab of a week), and the walks (the stack walk's custom Summary; the
  integrations walk's filled routine - the Summary by week, the enlarge over it, the Trend tab of the latest week).

## 15. The lines a run compares, and their names (2026-11-06)

The first live power-curve routine compared ten lines from four cells: the chain had computed the same quantity in
cell 2, cell 3 and cell 4, and the routine kept all three versions, each under the wording the analyst gave it in
that cell. Two facts of the design meet here. The ledger is append-only (the contract's *Results*: a revised estimate
gets a new line, the earlier one stays), and promotion took the whole ledger of the path's cells as the lines to
compare, with a choice only on a typed line. Neither is specific to one kind of analysis: every chain that iterated
carried its drafts into its routine, and compared them run after run.

### 15.1 The promoter picks, and names

The promoter's one call (F1 step 2) already reads the script and the ledger. Its ledger is numbered now
(`7. [cell 4] …`), and its reply carries `"compare": [{"line": 7, "name": "…"}, …]`: the lines a run should compare —
the final form of each quantity the answer rests on; not an earlier cell's version that a later cell computed again,
re-specified or extended, nor a check or a trial the answer does not rest on — each with a name as a table head reads
it: the quantity and what tells it from the other lines, without the counts, periods and dates that vary with the data.
Every other line is *dropped* in the manifest (§3: a dropped line stays, is printed and checked by position, and is
left out of the comparison). A reply without a usable `compare` — absent, empty, no valid line — keeps every line, as
before, without names: the pick is a proposal, never a refusal. The name goes on the manifest as `results[i].name`, at
most 60 characters; `label` stays the recorded wording. The prompt stays domain-free (DESIGN_CHECKLIST C5).

### 15.2 The dialog (S1)

The coach is not asked to pick. The section lists the lines a run will compare — the name, the recorded wording on
hover, the cell — under *Tracked metrics — recomputed each run and compared with the run before, 5 of 10 · 2 figures*
(the words since 2026-11-08; it read *Results — the lines the runs will compare, 5 of 10 kept* before); a tracked line
shows *drop* when hovered. The lines set aside are one muted line, *5 more metrics computed, not tracked*, that opens on
a click into the greyed lines with their recorded wording and *track* on each. A typed line keeps its flag and its
*keep as a constant / drop* choice, visible as before (a warning is not hidden), the default following the pick. The
page keeps the state on the proposal and sends the whole set of dropped lines on Create; the library's `create` without
choices takes the proposal's. The decision (2026-11-06): trust the model's pick, keep the coach in charge without asking
anything of them, and show the set-aside lines only on a click, so they neither clutter the dialog nor read as something
to decide. What the coach can say about the pick is the box of §15.6.

### 15.3 Where the name shows

Wherever a line is shown by its label — the dialog, the Summary (the table by interval's heads, the custom table,
the enlarged chart's title and key; its results list went in §20), a run's Trend tab — the page shows `name` when the
manifest has one, else the label trimmed as §14.4 says (`build.lineName`); the full recorded label stays on hover.
`compare_runs` rows carry the name, so a run's record reads the same way.

Not here: a RESULT that carries a list (a quantity over a fixed short set of points — durations, zones, groups —
recorded in one call and compared point by point), which is what a curve wants; it changes what the analyst writes and
waits for a simulation on chains of several kinds.

### 15.4 Build order and acceptance

- **Patch 0267 — the pick and the names**: 15.1–15.3. Accepted by: the pure module (the numbered ledger; `pick_results`
  with a valid, a partial, an empty and an absent `compare`, names cut at 60; `create` without `drop_results` taking the
  proposal's drops, with them the page's; `compare_runs` rows naming the line), the markup on the mini DOM (the kept
  list with names and their titles, the muted line and the group it opens, *keep* and *drop* moving a line and the
  head's count following, the typed row's choice following the pick, the name used by the Summary's heads and the
  Trend tab), the integrations walk (its scripted promoter picks two of the chain's three lines and names them: the
  dialog's two groups, keep and drop live, the manifest stored, the Summary's two named columns, the enlarged chart
  and the Trend tab by name; the stack walk's chain records one line, so nothing changes there), and the screens tool
  (the dialog with lines set aside, closed and open; the manifest on the pick in the manager, the run view and the
  Summary).
- **Patch 0276 — the pick, steadied**: 15.5. Accepted by: the pure module (the prompt's three sentences; `promoter_user`
  with cited cells, sorted and once each, and without), the host's path (the propose test's payload carries the cell
  its report cites), the C5 scan.
- **Patch 0281 — custom instructions**: 15.6, and the dialog in the coach's words (15.2). Accepted by: the pure module
  (`tracked_lines` on a valid, a bare, an out-of-range, a doubled and an empty answer; `pick_results` with the
  instruction's lines over an empty and a named pick; `apply_edits` refusing an edit that adds a RESULT call;
  `promoter_user` with and without the section; `parse_promoter` leaving `tracked` absent), the host's path (the
  section in the payload, the one retry and its step, the union and the notes, the proposal's `instruction`; `create`
  keeping, leaving and clearing it; the summary and the by-origin index), the routes (propose with the line, create
  keeping it, the views), the markup on the mini DOM (the section's words, the box, the button, the Notes after it;
  the facts' *Tracked* and *Custom instructions*), the page's source (the re-pick carrying the fields, the first pass
  with the origin routine's line, the next-version fill), the stack walk (the box typed, *Update the list*, the line
  named as the scripted promoter answered, the note for the metric it found no line for, the fields standing, the
  facts after the save), the screens tool.

### 15.5 The pick, steadied (2026-11-07)

The pick was erratic on the same chain: one save compared the whole series of a quantity over its durations, the next
three steps of it and a sensitivity line. The promoter had the rule - the final form of a quantity the answer rests on,
not a draft, not a check - and nothing to tell a series from a few of its lines, a check from a result, or the cells the
answer was read from, from the cells it passed over. Three sentences in step 5 of its prompt, and one more section of
its payload, all domain-free (C5):

- *the report's citations*: the payload ends with `THE REPORT CITES (the cells the answer was read from): cells 5, 6` -
  the `[cell n]` citations of the report, computed in the host with `analyst.report.cited_cells`, limited to the cells of
  the method; left out when the report cites nothing. The prompt: where the report cites cells, those are the cells the
  answer was read from, and the final forms are among their lines. An earlier cell's version of the quantity is usually
  uncited, and reads as the draft it is.
- *a check*: a quantity computed again with part of the data left out, under another cut or a what-if, is a check when
  another line gives it on all the data.
- *a series*: lines that form a series - one quantity over durations, bands, groups or periods - are compared whole,
  every line of the series from the cell that printed it last, or none of them.

Nothing else moved: the reply's shape, `pick_results`, the dialog, the manifest. The condensing pass (§19) runs after
the pick and never touches a RESULT line, so the prints it drops have no part in this.

### 15.6 Custom instructions (2026-11-08)

The steadied pick still missed: on a power-curve chain the promoter kept 1 s and 5 s and set the rest of the ladder
aside, naming in its reasoning the durations it was dropping. The rule of 15.5 was read and not followed; a sentence in
a prompt is advice the model weighs against its own judgement, and here the judgement was the problem. Palo's idea: let
the coach say what the routine should track, and put that in front of the promoter. The design makes the coach's line a
question the model must answer, line by line, and lets the host keep what it answers - the model does the matching (a
recognition task it does reliably), the host does the keeping (no judgement left to it).

**The dialog.** After the pick, under the Tracked metrics, a section *Custom instructions — optional*, explained in two
ordinary sentences (*If you want this routine to track particular metrics, say so here and the model building it will
add them to the list above — for example the power durations that matter to you. It can only track what the analysis
computed; if something you ask for isn't there, it will tell you.*), one box (an example as its placeholder, 300
characters), and *Update the list*. The promoter runs at once when Save as routine is pressed, as before - most picks
are right, a question before every save would be friction paid every time, and the coach writes a better line once they
see what was picked. *Update the list* asks the promoter again with the box's line; the dialog's fields stand as the
coach left them (name, purpose, the version choice, keep fixed, the box), the group folds again, and a keep/drop made
by hand before it is replaced by the new pick. The Notes section follows the box, so a note about a metric not computed
sits under it.

**The prompt.** The payload carries the line as its own section right after the ledger: `THE PERSON'S INSTRUCTION (what
the runs should track; answer it under "tracked", from the ledger alone):`. Step 6 of the system prompt says what it is
and is not: not a request to compute anything - the method is fixed, nothing is computed, added or rewritten for what it
names, no input is made for it; for each quantity it names, the ledger lines that *are* that quantity (its final form,
from the cell that printed it last) with a name each; a match is that quantity, not the nearest one; a quantity no line
gives is an empty list and nothing more - no reason, no substitute. The reply object gains `"tracked": [{"asked": …,
"lines": [{"line": n, "name": …}]}]`, empty without an instruction. A required key is the most prominent thing in the
prompt: it is how `compare` and `unfit` already work, and the model cannot leave it out without breaking the shape.

**The host.** `tracked_lines(expected, tracked)` reads the answer: a number outside the ledger is dropped; a line
already given for an earlier quantity is not given again (one line never stands for two quantities - the second is
said as not found); the lines come back as `{number: name}`, the quantities with no line as a list. `pick_results`
takes them as `extra`: kept whatever `compare` says, the pick's name standing where it has one. Each missing quantity is
a note, *Not computed in this analysis, so it can't be tracked: best 3 h power*, written by the host. A reply that
leaves `tracked` out when the section was sent is asked once more with the reason (`PROMOTER_TRACKED`; the model step
reads *the instruction was not answered*), as the identifier rule is; left out twice, the proposal stands on the pick
with the note *The custom instructions were not applied this time; try Update the list again.* `apply_edits` refuses an
edit that adds or removes a `RESULT(` call (the count in the fragment before and after), so "compute it for the coach"
cannot reach the code; run zero still has to reproduce the recorded lines. A reply cut at the token limit is handled as
before. The worst case of a line asking for what was never computed is a note, not a changed routine. The one thing no
check can catch is a wrong match - the 2 h line answered for 3 h - which shows as a tracked row whose title is the 2 h
line; the dialog stays clean rather than carry a line per match.

**Kept with the routine.** `routine.instruction` is the box as it stood at Create (a next version with the key sent
replaces it, emptied included; a caller without the key leaves it). The summary, the by-origin index and
`GET /routines/<id>` carry it; the manager's facts show it as *Custom instructions* under *Tracked* (the Results fact
renamed: *9 metrics and 2 charts per run*). The dialog's first pass sends the instruction of the routine this very chain
is the origin of - the page reads the thread's routines before it proposes - so a chain saved again keeps what the
coach asked; choosing *Next version of …* on a later chain fills an empty box with that routine's line, and *Update
the list* applies it. Not here: the promoter's words on why it set a line aside, and any check that a matched line is
the quantity named - both would be more text for the coach and judgement for the model.

## 16. The Run dialog, slimmed (2026-11-06)

Palo on the first live Week run (the Run dialog of 14.2 with the cache line, the kinds line, *Everything again*, the
frame's chip and its green fit line, *Inputs — None*, the comparison sentence and the footer's sentence): "there is too
much detail and it is confusing; pretty much all of it should go". And: the load's progress was a small line - "hard
to see that something is happening". The rule since: **the dialog shows what the coach decides, and problems speak
only when they occur, in place.** It supersedes the layout in 14.2 and S3; the mechanics are unchanged.

### 16.1 The rows

A label column and the content (`.rt-row`); the body is these rows and nothing else:

- **Data** - the choice on one line: *Load from Intervals.icu* · *The data loaded now · 2025-11-10 → 2026-11-01* (the
  frame's dates; the second choice only when something is loaded). A file routine: *Upload a file* [the file input],
  *A file from the Dataset cache* [the pick, once the cache has answered with files], *The data loaded now · name*.
  Endura: *Load from Endura* with the race pick; SweatStack: the load with its window.
- **Athlete** (Intervals) - the pick. Under it a line only when it matters: *no key stored for them: a window the cache
  holds runs; anything else needs the key under Settings → Intervals ICU*.
- **Interval** (Intervals) - *Day · Week · Month · Year · Custom*, and under it one line: *Last complete week:
  **26 Oct – 1 Nov** — not run yet* (or *— run already; Run runs it again*), then the box *Fill the weeks back to 3 Nov
  2025 — 40 not run yet* when there are units to fill, or *Every week back to 3 Nov 2025 is run already (12 weeks)*;
  *No complete month within the last 14 days* when the horizon holds none. *Custom*: the two pickers, and a note only
  when the plan clamps the window (*your plan allows 182 days*). With *The data loaded now* picked, the Athlete and
  Interval rows grey out (the box keeps its layout) and the frame's problems, if any, stand under Data: *△ 2 of 17
  columns are empty in this data: power, temperature …*, *! nothing to run on: …* (the precheck's line, never the
  green one).
- **Inputs** - only when the routine has any: the label (its origin on hover) and the widget, a derived one its line.
- **Compare** - Custom and the data loaded now only, and only with two runs to choose from: *run 14 (the run before)*
  · *run 0 (the original data)*. One choice is no choice: nothing shown, it applies. A set interval compares with the
  unit before it by rule (14.1); nothing is said.
- The footer is the time alone: *about 20 min* for a fill (the units times the last run's time), *the last run took 2
  min* (or *the check on the original data took …*) for one run, nothing when unknown. Cancel · *Run* / *Run 41 weeks*
  / *Run again*.

Gone from the dialog: *Everything again* (its home is the Intervals.icu dialog: *Only what's new / Everything again*;
the store re-fetches changed files on its own), the cache preview (the load asks the cache itself when Run is pressed,
and the LOAD row says *from the cache* after), *with summary, wellness · metrics as the original*, *the original's N
days, ending today*, the frame's chip with rows and columns, the green *fits the routine* line, *Inputs — None: the
method runs as it is*, the comparison sentence and its explanation, the footer's two sentences, the ETA line (the
footer has it). Nothing of the record changes: the run's data tab, the LOAD row and the record still carry all of it.

### 16.2 The load's progress

Run pressed: the rows dim (`.rt-busy`) and a band stands at the foot of the body - a live dot, the loader's message
(*Downloading 12 of 40 activities…*, *Coding the context… (40%)*) in the body's size, and a bar filled to the job's
percent when it has one, sweeping when it has none. A failure takes the band's place in red, the rows back for another
go. The band goes as the dialog closes (the run shows in the main panes, a fill in the Summary). The dialog's set
height comes down to what the rows need (520px / 80vh).

### 16.3 Build order and acceptance

- **Patch 0269 — the slimmed dialog and the progress band**: 16.1–16.2. Accepted by: the markup on the mini DOM (the
  rows and their order per source; the plan's lines at known dates; the fill box and its count; the Inputs row only
  with inputs; the Compare row only with two choices; the data-loaded-now line only when something is off; the
  footer's time; nothing of what went), the page's source (the band with its bar and percent, the rows dimmed while
  busy, the cache preview and the refresh box gone from the dialog and the load), the stylesheet, the screens tool
  (the dialog on Week, on Custom, on the data loaded now, and while a load runs), the stack walk (the file routine's
  dialog) and the integrations walk (the Intervals dialog on Week, the fill, the load's band seen while it runs).

## 17. Save as routine: what happens while you wait (2026-11-07)

The dialog of S1 showed one line for the whole wait - *The analyst is reading the chain and naming its inputs… · Analyst*
- "bare, and nothing of what is happening under the hood". What happens is four steps: the chain read (the cells on the
path, the result lines, the figures, the data record - a second), the data probed when it is still loaded (the frame's
span, the auxiliary files' columns - a few seconds), the model's turn (it reads the script and the ledger and decides
the inputs, the edits, the lines to compare and their names - twenty seconds to minutes; a reply that cannot be read is
asked for once more), and the proposal prepared (the edits applied and checked).

The dialog now shows them as a checklist that fills as the steps pass, in the coach's words:

```
✓ Read the analysis — 9 cells · 12 results · 2 figures
✓ Checked the data — 206,016 rows · 17 columns · activity summary, wellness
●  Working out what you can change each run, and which results to compare — 0:42
○ Preparing the proposal
```

A done step carries what it found; the running one the dot and a clock that ticks on the page; a reply asked for again
says so on the model's line (*the reply could not be read; asking again · 0:12*); data no longer loaded says so on its
line (*no longer loaded — the routine will be made unverified*). The chain's facts go to the sub-header as soon as they
are known (*from this chain · 9 cells · 12 results · 2 figures*). The seat and the model stay on the pane's quiet card.
When the proposal lands the checklist gives way to it; a refusal takes its place with *Try again*, as before.

Mechanics: `propose` emits a `step` event as each step passes (`{step: chain | data | model | proposal, state: running |
done, detail, again}`); the instance puts it on the stream as a `routine_step` line (`_emit_routine`); the dialog takes
those lines off the stream before the pane sees them (`stream`'s intercept) and draws `build.steps`. A step landing marks
the steps before it done. Not a pane row, ever.

Accepted by (patch 0270): the pure module (the steps emitted in order with their facts; the retry marked; the data gone
said), the route (the `routine_step` lines on the stream around the pane's card), the markup on the mini DOM (the four
states of a line, the clock, the words), the screens tool (the dialog waiting at 0:42), and the walks unchanged (the
step lines never reach the pane).

## 18. The promoter's brief, and identifiers (2026-11-07)

The first live routine over a within-session analysis (power, heart rate and ventilation at fixed power) came out with
two inputs that no coach can set: the six sessions carrying ventilation, by id, and the three heat sessions, by id.
The chain had retyped both lists from an earlier cell's output although it had the rules (sessions with more than 500
ventilation samples; mean cockpit temperature above 18 °C), and the promoter's brief listed "identifiers of subjects
or groups" among the constants to consider. Palo: "the user cannot possibly know and identify them on new data" - and
"is the promoter sufficiently informed of the purpose of the task?" It was not, quite.

### 18.1 The brief

The promoter's prompt now opens with what the result is for - the routine's life: made from this chain, opened later
by a person who picks the data (usually a new window of the same source, often another subject's), sets the inputs in
a dialog and runs it, the result lines compared with the run before; the data loaded fresh each run, so nothing of
this window survives - not its rows, not the identifiers of its sessions or groups, not the dates inside it - only
the shape; run zero on this very data as the check on any rewrite. Then **the test of an input**: could the person
set it before the data is loaded, without looking at it? A threshold, a band, a number of days, a switch, a choice
among values known by name - yes. An identifier of a row, a session or a group of this data, a list of them, a date or
a name found by looking - no: it is replaced by the rule that produced it (the expression the chain used, where a cell
has one) and never made an input; where the chain has no rule, the literal is reported under `unfit`. Identifiers are
gone from the list of candidates; a choice is "never over a key column"; an edit may replace a literal of the data by
the expression that computes it. The data description names the **key columns** (`key_column`: `id`, `*_id`,
`*_ids`, `id_*`, `uuid`). The reply carries `recomputed` (one clause per literal turned into a rule, naming the cell)
and `unfit`. No domain words (C5).

### 18.2 The floor

Whatever the promoter says, an input that reads as identifiers - a `choice` over a key column, or any input but a
toggle named as one (`heat_ride_ids`) - is not accepted (`key_inputs`): the reply is asked for once more with the
reason (`PROMOTER_KEYS`: the inputs named, the rule restated), and a second such reply is refused - *the method picks
rows of this data by their identifiers (rides over activity_id), which other data will not have; ask the analyst to
pick them by a rule, then save again*. While it is asked again the dialog's checklist says so on the model's line
(*identifiers were proposed as inputs; asking again*, §17) and the pane's quiet card names them in its peek. A reply
with `unfit` entries is refused the same way, naming the cell and what it names. The dialog's notes say what was
recomputed instead of typed, so the coach sees the method changed shape - run zero verified it. The analyst's contract
already says a value read off the data is computed and kept in a variable, never typed; the brief and the floor are
for the chains that did it anyway. At run time the precheck stands as the backstop: chosen values absent from the data
refuse the run, which identifiers of other data always are.

Accepted by (patch 0271): the pure module (`key_column`, `key_inputs`, `unfit_line`, the parse), `propose` over a
fake promoter (the key column named in the data description; a keyed reply asked again with the reason and the step
marked as asked again; a second keyed reply refused; an unfit reply refused; the recomputed clause a note), the C5
scan over the new text, and the walks unchanged.

## 19. The condensing pass (2026-11-07)

A routine runs the chain's cells as the analyst wrote them, and the analyst explores: inspections, printed tables,
a computation redone three ways, a loop over rows where a rolling sum would do. The routine inherits all of it. Two
things went wrong with that in practice: the time (the MMC chain computed its curve by brute force - minutes per run,
and a fill runs forty of them), and the clutter (an output full of exploration a coach never asked for). Palo's first
thought was a fourth analysis mode that primes the analyst to write routine-ready code; dropped, since it would cost the
analysis its exploring and touch every chain for the few that become routines. The shaping belongs after the chain,
when the outputs are known - and not in the promoter's pass, which is a reading job (verbatim fragments, find/replace)
that run zero can check.

Patch 0272 shipped the pass as a model's job: a Condenser seat given the cells, asked for the kept cells, its
candidate run and compared. On the first live chain (the MMC, twelve cells, 2026-11-07) the seat it fell back to - the
analyst's, tuned for long reasoning on short replies - spent its whole token allowance reasoning and returned nothing;
the floor held and the routine stayed as written, but the design was fragile in three ways: the reply grew with the
chain, the model saw code without the context that made it, and equivalence was checked on one dataset. Palo: "this
feels a little fragile". 0273 took the model out of the pass; what remains needs none.

### 19.1 The pass

After run zero reproduces, the cells are pruned from the code alone (`rt.prune_cells`). Each cell is parsed; the pass
reads what it defines - names bound, names it mutates in place (a subscript or attribute assignment, an in-place call,
`inplace=True`), functions, classes - what it reads from before it, and whether anything rests on it: a RESULT call,
a figure (its cell named in the manifest, or a show / savefig call), a save or write (`to_csv` and its kind,
`write_*`), an input read that no other kept cell makes. The reads are walked in statement order with Python's
scopes: a name the cell binds before reading it - an earlier statement's, a loop or with target, a function's
parameters and locals, a comprehension's or lambda's own - is not read from outside, so the `g`, `s` and `n` the
analyst reuses in every cell do not chain the cells together (the first live chain, twelve cells, kept all twelve
under the naive rule and ten under this one, the two that went being the inspection and a check). A walk from the
last cell to the first keeps a cell when it is anchored so, or when a later kept cell reads a name it defines; every
other cell goes - its imports kept in place, since they are cheap and a later cell may lean on them - as do the
top-level `print` and `display` statements of the cells kept (a print inside a loop or a branch stays). Markers and
numbers stay, as do the capture switches between cells. A cell that does not parse prunes nothing, with the reason on
the record.

The candidate is not trusted; it is run. `condense` in the host checks its cells against the original's
(`check_condensed`: a subsequence of the markers, every figure cell kept, the same inputs read), joins the script and
runs it on the chain's own data through the same runner as run zero, and accepts it only when `check_lines` says
reproduced - every RESULT line identical as printed, the same count - and `same_figures` says the same pictures: the
same number, each figure's Plotly data and layout equal with numbers within a relative 1e-9 (plotly's typed arrays
decoded and compared the same way; nan as nan), a PNG byte for byte. When the pruning of cells fails that test - a
dropped cell mattered through a path the code does not show, a function mutating a list it was handed - the prints
alone are tried; when that fails too, or there is nothing to cut, the script stays as written, the line saying why.
Two runs at most, no model, no cost beyond them.

### 19.2 What is kept, and what the coach sees

When the candidate is accepted the version's `script` is the condensed one and the chain's stays as
`script_written`; run zero's record - its results, figure count, time and the files under `runs/v1_0` - becomes the
condensed run's, since that is the script every later run is read against; the pass itself is on the version as
`condensed` {status, line, cells [before, after], dropped {cells, prints}, elapsed [run zero's, the candidate's]}.
Kept as written, the version carries the record and no `script_written`.

Behind the dialog the verdict's thread runs the pass after run zero: the version is written as `condensing`
meanwhile - `zero_holds` holds a run, the manager's chip says *condensing…* and the list row too - then settled. The
page's watch (`watchVerification`) goes on through it, reloads an open manager when the status turns so the chip
follows, and its toast carries the pass's line: *verified on the original data · condensed: 12 cells → 5, 23 prints
dropped, 190 s → 184 s*, or *· as written: the pruned code did not reproduce the figures: figure 2 differs*. The
Summary's version row (the Checked row until §20) carries the outcome after the verdict - *10 cells · 0.8 s* - with
*as written ↓* beside it when the condensed code is the one that runs - `/routines/<id>/script?written=1`, the chain's
code with the INPUTS block, named `_as_written.py`. Nothing else speaks: no pane rows, no figures shown (the
candidate's exist to be compared).

The pass runs only where it can be checked: a routine made with the chain's data gone (unverified) is left as
written, as is one whose run zero differed or failed. A run's Results tab may be empty afterwards when the method
printed nothing but what the pass dropped - the RESULT lines, when there are any, still print there. The time the
pass saves is the dropped cells'; the slow cell that stays is the consolidation's (§19.3).

### 19.3 The consolidation (patch 0274)

The speed. The MMC method's cost is one computation the cells redo several ways, and no pruning touches it. A rewrite
of that is a model's job again - done, this time, on the footing §19 set out: the unit is the method, not a cell; the
model gets the context the analyst had; the rewrite is checked on two datasets; and the step is opted in by seat,
never a fallback.

**The seat.** `Condenser` in the model config. Without the entry the step does not run (`_condenser_seat` is None):
the one fallback 0272 made - the analyst's seat, tuned for long reasoning on short replies - was the failure. Since
0275 the shipped template carries the seat in every preset (Palo: "add it to the template as default, the same model
as the analyst"): the preset's analyst model and provider, medium effort, the Promoter's token allowance - a seat at
medium, not the analyst's xhigh, and the call asks for medium in any case (`_effective_effort` only ever lowers).
Removing the entry turns the step off; the stack's copy of the template puts it on the harness like every seat, so
the walks exercise the path. The call is a quiet one from the verdict's thread (`_llm_quiet`: a silent output
manager, the cost read off the save's chain, which the proposal carries as `billing_chain_id`; the Usage dialog lists
it there under *Condenser*), at medium effort, low on the second try.

**When.** After the pruning, and only when the method takes time: run zero's elapsed - the pruned run's when there
was one - at or above `CONSOLIDATE_MIN_SECONDS` (15; the environment `BAMBOO_CONSOLIDATE_MIN_SECONDS` sets it, the
stack sets 0). Below it the record says *not consolidated: the method runs in 2.3 s* and nothing is called.

**The brief** (`CONSOLIDATE_SYSTEM`, `consolidate_user`): the question, the answer, the cells of the method - the
pruned script's - each with the output it printed when the analysis ran (`cell_outputs` on the proposal, from the
kernel's record of each cell, clipped at 1,500 characters), the numbered RESULT lines, the figure cells, the inputs
with their labels and defaults, the time each cell took. The method is to be written again under the same markers:
the cells that print a RESULT line or draw a figure keep their markers, numbers and order; a cell that only prepares
may go, its work moved under a kept marker; each RESULT call stays under the marker of the cell it came from, in its
order, with its label and arguments; each figure is drawn by the same calls; every INPUTS key is read; loads and
DS.save stay. Compute once what the cells computed several times; vectorise; never faster by a different answer -
no sampling, no fewer draws, no other seed, a loop that draws random numbers keeps its draws in their order. One code
block, or UNCHANGED.

**The check at creation** (`consolidate`): the reply read (`parse_cells`), the cells checked before anything runs
(`check_consolidated`: `check_condensed`'s subsequence, figure cells and inputs, and every RESULT call still under the
marker it came from, by count per cell), the script run on the chain's own data and accepted only when `check_lines`
says reproduced and `same_figures` the same pictures. A fault goes back once (`CONSOLIDATE_RETRY`); the second keeps
the method as it was (*as it was: the rewritten method did not reproduce the result lines: …*); UNCHANGED is *nothing
to gain*; a reply cut at the token limit names the remedy. Accepted, the rewrite becomes the version's `script` and
the script it replaced waits under `script_fallback`; the record `consolidated` {status, line, cells, elapsed,
attempts, cost, seat, model, provisional: true, confirmed, fell_back}; run zero's record is the rewrite's. The
Summary's line: *consolidated: 10 cells → 4, 190 s → 6 s; checked on the original data, the first run on new data
checks it again*.

**The check on the next data** (`check_consolidated_run`, inside `run`): on the first run of a provisional version,
the method it replaced runs once more on the same data - bound the same way (`prepare` hands out the datasets
folder for the second binding), the same inputs and prelude - and the two outputs are compared: the same RESULT lines
as printed (`same_lines`), the same figures. Agree, and the rewrite is confirmed - `script_fallback` goes, the line
ends *; confirmed on run 1*, the run's record and the pane's CHECK row say *the rewritten method confirmed on this
data*. Disagree, and the version falls back to the method it replaced, whose output becomes this run's - the line
reads *as it was since run 1: the rewritten method differed on new data (line 3 (…): +4.00 -> +3.00)*, the run's
record says *fell back at run 1: …*. The rewrite failing where the old method ran falls back the same way; both
failing, or the old method alone, gives no verdict and the rewrite stays provisional for the next run. A fill's first
window does the check like any run. Two datasets are not a proof; a rewrite that survives the window it was made on
and the next is on the footing of everything else here.

**What the coach sees.** The chip says *condensing…* through both passes; the toast carries the pass's line and then
the consolidation's, and the Summary's version row their outcome in a few words (*10 cells · 0.8 s · rewritten, the
next run on new data checks it*, then *confirmed on run 3* or *rewrite dropped on run 2*); *as written ↓* is there
whenever a script as written is stored (`written_chars` on the version view). Nothing else speaks.

Accepted by (patch 0274): the pure module (`parse_cells`, `check_consolidated`, `same_lines`, the brief), `consolidate`
over the kernel (left alone under the threshold; the brief's contents and the effort; a rewrite kept provisionally;
a RESULT call moved refused before running and asked again at low effort; a number changed twice; UNCHANGED; a cut
reply), `create` with both passes in the foreground and behind the dialog (the scripts, the records), `run` on other
data (a rewrite confirmed, the record and the pane; a rewrite that typed a number falls back, the run's output the
old method's; a second run with nothing to check), the app path (the quiet call on the Condenser seat at medium
effort, billed to the save's chain; the route's first run confirming), the page's line, the stack walk (the stack's
own Condenser drops the dead stores; the rewrite provisional, then confirmed on run 1) and the C5 scan.

## 20. The Summary, one column (2026-11-08)

Palo, with three screenshots of the manager scrolled through: "very cluttered now with multiple scroll bars, and even
me as a designer of the system am struggling with the UI" - the whole scrolled, and the table by interval and the runs
list each scrolled inside it; the modal took a small part of the screen; the runs' pills (*ran · 5 of 9 moved*,
*differed*) said more than anyone reads; the design needed to be cleaner, what to keep and what to drop assessed on
the UI. A first mockup grouped the columns that shared their first and last words under one head and put the athletes
under the routine in the rail; both refused ("this could become problematic", "with 10 athletes and multiple routines
this would become a problem - leave it as it was"); the second, approved: one column, four facts, the table with the
full names, the athlete choice as it was.

**The modal** fills the window less the scrim's margin (`width: min(1800px, 100%); height: 100%`), the rail as it was
(300 px since 0282, a routine's name wrapping rather than cut with an ellipsis), and the body is the one scroll: no box
around the table (its head sticks to the body's top), no runs box.

**The facts** (S2): *Purpose*, *Inputs*, *Results* (*Tracked* since §15.6, with *Custom instructions* under it when there are any), *Version(s)* as label and value. Gone from the header: the columns
count and *(a favourite; continue it there)* (the link's hover says it); gone from the body: the Question when a
purpose was written, the Checked row (its verdict and the passes' outcomes are the version row's, in a few words:
*verified, 17 lines reproduced · 10 cells · 0.8 s · as written ↓*), the inputs table (a line per input), the Results
list (it repeated the table's column heads line for line; *9 numbers and 2 charts per run* says what a run records),
the Versions list (the version rows), the *first version* note.

**The runs** are the table: a set interval's rows and the custom table's heads open the run (*open →* on hover in the
unit's cell); a unit whose runs all failed is a row with the reason (`run.line`: *failed at cell 6: ValueError: …*),
the custom runs that failed are named under their table, each opening; the runs list with its pills went. The values
show without the plus sign the RESULT format writes (`build.shown`; the sign stays on a negative). The legends went;
the gap line is a link - *18 weeks in the last year not run yet · fill them* - that opens the Run dialog on the
interval (`openRun(id, {interval})`, the fill box on by default). The fill's bar stays while the fill runs; its last
word is the toast's, and the table shows what landed.

Accepted by (patch 0277): the mini DOM (the header's sub-line; the facts, each; the version rows across the verdicts
and the passes; the table by interval with a failed week among its rows and the gap link; the custom table's heads and
its failed runs; the fill bar running and gone), the stylesheet (the frame, no box, no runs rules), the page's handlers
(a row, a head or a failed line opens the run; the gap link opens the Run dialog on the interval), the stack walk (the
manager's facts and the custom table after two runs, a run opened from a head), the integrations walk (the manager by
athlete without a list, the fill's end with no bar and the toast's last word, the table by week with the gap link, a
week opened from its row), the screens tool (the manager's states with no scroll inside the body's).

## 21. Custom runs: Open, Delete, and any earlier run to compare with (2026-11-08)

With the reach of four years (docs/DATASETS_DESIGN.md §18) a custom run is how two periods are compared across years -
the six months before one season's goal beside the same six months of another - and the Custom tab is where they
live. Three things it lacked (Palo, 2026-11-08): a visible way to open a custom run in the main panes (0277 made the
head the link, but nothing said so), a way to delete runs from the history, and a way to compare a run with a chosen
earlier one rather than the one before.

**Open and Delete.** A run's head in the Custom table carries the two words on hover - *Open* and *Delete*, set
apart - and a failed custom run's line under the table the same; run 0 has no Delete (it is the check on the
original data). Delete asks (*Delete run 61?*), then `DELETE /routines/<id>/runs/<n>`: the run's line comes off the
record and its folder (`runs/v<version>_<n>`) off the disk, and the Summary is read again. A run another run was
compared against stays named by its number on that run's record (the comparison was made then); a fill running on the
routine refuses the delete until it ends (409). The rows of a set interval's table are not deletable here - a week
re-run replaces the week; nothing is lost by keeping the record.

**Another run.** The Run dialog's Compare row offers, beside *the run before* and *run 0*, *another run* with a list
of the athlete's earlier custom runs (number · window); picking one checks the choice and sends its number as
`compare_with`, which `reference_run` already took. The row shows when there are at least two choices, as before.

Accepted by (patch 0279): the host (`delete_run`: the line, the folder, run 0 refused), the route (test_app_path.py:
the deletion, the count, run 0 and a run already gone refused, a later run still naming the deleted one), the mini DOM
(the heads' two words, none on run 0, the failed line's; the Compare row's third choice and its list; the page's
handlers and the choice sent), the stack walk (the failed run deleted through the Summary - off the foot, off the
record, off the disk, the rail's count down by one), the integrations walk (the heads read without their two words).
