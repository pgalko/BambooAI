# Routines — design v1.0 (2026-10-10)

A routine is an analysis kept as a method: built by exploring with the analyst, then run again, without a model,
on new data — a later window from Intervals.icu, another athlete's data behind a new API key, the next race from
Endura, an updated lab file — and compared, run against run. This document is the map of the feature: the
vocabulary, what it builds on, the records, the flows with their failure states, the model's two calls, the screens,
the storage, the build order and the open decisions. Step 1 (Save as routine) is built; the rest is design.

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
- `data`: the run's data record (above) — for a file the columns are the schema fingerprint a later run is checked
  against; for intervals the window and the auxiliaries; for endura the race.
- `parameters`: at most five, each `{key, label, type (number | numbers | date_window | choice | toggle), default,
  origin ("the exploration used …"), column? (choice), multiple? (choice)}`. The script reads `INPUTS[key]`; the
  runner writes the `INPUTS = {...}` block at the mark before each run.
- `results`: the expected RESULT lines in order, each `{cell, index, label, typed, dropped, estimate, low, high,
  unit, direction}` — the identity of a line is `(cell, index)`, never the label. `typed` comes from the kernel's
  records; a dropped line stays in the manifest, so the check by position still maps the chain's lines to the
  routine's.
- `figures`: how many the script draws, and which cells.
- `notes`: what the promotion left out and why (an input whose edit did not apply, a sixth input).

**run** (step 2) — number (0 for run zero), started, finished, status (reproduced | ran | differed | did_not_fit |
failed | timed_out | unverified), data, inputs, results, stdout, figures, generated datasets, comparison, narrative.

Status meanings: *reproduced* — every expected line reappeared with the same numbers (run zero, or a re-run on
identical data); *ran* — every line reappeared, numbers differ (the normal case on new data); *differed* — a line
is missing or a typed line changed; *did_not_fit* — the schema pre-check refused the data; *failed* — the script
stopped at cell n; *timed_out*; *unverified* — run zero could not run because the analysis's data was no longer
loaded; the first run on data will tell.

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
6. **A choice input's values are checked against the data** before a run (step 2), like the columns: an exclusion of
   "athlete07, athlete09" on a file that has neither is said ("not in this file") rather than silently doing nothing.

Relative windows for files: the "updated lab file with extra rows" case runs on the whole file unless the
exploration itself filtered by date, in which case the promoter offers "last N days of the file" with N from the
exploration.

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
2. **The promoter**, one call on the Analyst seat with a generic prompt (`analyst/routines.py` PROMOTER_SYSTEM; no
   domain words, DESIGN_CHECKLIST C5): name the constants that would change on other data of the same shape; make
   the data's own range the data's range; propose each remaining constant as an input of one of the five types, at
   most five, fewer is better; rewrite as find/replace edits; leave the method, the markers and every RESULT call
   otherwise untouched; return JSON. A reply that cannot be read is asked for once more, then refused ("the script
   was not understood"). The call runs on a chain id of its own, so the hosted edition charges it as a query; the
   pane shows it as a quiet *Routine* card.
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

### F2 — Run (step 2)

Entry: *Run* on the routine (S2), or *Run on current data* when a dataset is loaded on the Data tab.

1. **The run dialog** (S3), per source:
   - Intervals.icu: window — start and end, default the original's length ending today (tier day-limits apply as on
     the Data tab); auxiliaries ticked as in the original (untickable, with the warning that a cell may need one);
     metrics as in the original.
   - Endura: a race picked from `get_races`; auxiliaries as in the original.
   - File: the primary file — upload, or pick from the Dataset cache — with the fingerprint check shown inline as
     soon as it is chosen ("fits: 49 of 49 columns" / "missing: venue_altitude_m, surface_category — the routine
     cannot run on this file"); each auxiliary likewise.
   - Parameters with their defaults; "Compare with" — the preceding run of this version (default) or run zero.
   - *Run on current data* skips the loading step and checks the loaded dataset's fingerprint instead.
2. **Load**, through the existing loader job, with the Data tab's own progress; then the fingerprint check (for
   integrations too — a source's format can change) and the check of every choice input's values against the data.
3. **Execute** in the executor with the INPUTS block written at the mark, the timeout as the replay's. The left pane
   shows it as rows: *Loading Intervals.icu 2026-07-12 → 2026-10-10 · wellness*, *Running routine v2 · 7 cells*,
   *Compared with run 4 (3 Oct)*, then the narrative as a card, then a closing card (S4).
4. **Results** parsed from stdout by position; figures and datasets kept; status set.
5. **Comparison** computed: for each expected line, this run's estimate and interval against the reference run's;
   the change; whether the intervals overlap; lines missing on either side listed. The reference is the preceding
   run of the same version; run zero only when there is no other run.
6. The right pane opens on *Comparison*; *Narrative*, *Plots*, *Results* (printed output), *Data* beside it. The
   composer is disabled under the view (`composerLock`, built; a run is a record) and comes back on a new thread or
   when a favourite is loaded (`composerUnlock`, wired).

Failure states: did not fit (named columns; nothing ran; no run record beyond the attempt and its reason); failed at
cell n (the traceback condensed as the analysis condenses it; the run kept with status failed, so the history shows
it); timed out; a result line missing (status differed, the line named); a typed line present (constant, flagged in
the table); the loader job failed (the Data tab's own error, no run).

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

### F5 — Manage (built, without the runs table)

Rename; delete (the routine and its runs; the origin favourite stays); download the current version's script as
`.py` (for the analyst in another domain who wants it in a notebook; the INPUTS block at the top with the defaults);
*made from the analysis of … ↗* (the origin favourite, into the main panes; "no longer in Saved workflows" when it is
gone); the versions list with change notes; the runs table (S2, step 2). Deleting a favourite that is a routine's
origin will warn (step 5); until then the routine stays runnable and marked. No sharing between users in this version.

## 6. The model's two calls, and where it is absent

| call | seat | when | input | output | guard |
|---|---|---|---|---|---|
| Promoter | Analyst | Save as routine; a next version | question, summary, the data record, the cells, the ledger, (the manifest on a next version) | edits + inputs JSON | the edits apply whole per input; run zero must reproduce |
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
routine, or Save as routine when there is none); a run (step 2) shows in the main panes exactly as an analysis does,
one run per view, the arrows beside the chain position moving between the routine's runs, no Save (a run is recorded
as it completes), the composer disabled. `tools/routines_screens.py` renders the built screens in the real page
(dark and light) with the backend faked, and checks their state.

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
analysis of 10 Oct ↗ (a favourite; continue it there)"; the actions (.py, Rename, Delete); Purpose, Question,
Checked (verified / unverified, run zero's line); Inputs (asked before each run: label, default, where it comes
from); Results (compared run to run, with their cells); Versions (newest first, with the change notes); Runs (step 2:
the results-across-runs table — a cell is the estimate with its interval on hover; the last column carries a mark
against the previous run: ↑ ↓ for a change whose intervals do not overlap, = otherwise, · for missing; a row with
three or more runs gets a sparkline; clicking a run opens it in the main panes).

### S3 — Run (dialog, step 2)

```
┌ Run: Altitude pace correction (v2) ─────────────────────────────┐
│ Data from Intervals.icu                                         │
│   Window   [2026-07-12] → [2026-10-10]   (97 days, as before)   │
│   With     ☑ wellness                                            │
│ Inputs                                                          │
│   HR bands      [130, 145, 155, 165, 175]                        │
│   Minimum laps  [20]                                            │
│ Compare with   (•) run 4 (3 Oct)   ( ) run 0 (the original)      │
│                                              [Cancel] [Run]     │
└─────────────────────────────────────────────────────────────────┘
```

For a file routine the Data section is a file chooser with the fingerprint line under it; for Endura, a race list.

### S4 — A run in the main panes (step 2)

Left pane rows, as an analysis: *Loading Intervals.icu 12 Jul → 10 Oct · wellness* (pending → done), *Running
routine v2 · 7 cells · 14 s*, *Compared with run 2 (21 Oct): 4 of 9 moved*, the narrative card ("What changed",
collapsible), a closing card: *Run 3 complete · <routine> · 9 results · 4 moved · 1 figure · $0.02 · 31 s* with
Comparison → What changed → Plots → Results → Data links. The position reads "run 3 of 3" and the arrows move
between the routine's runs. No Save pill: the run is already recorded. The composer is disabled, its placeholder
saying why ("A run is a record: to go further, open the analysis it was made from"); it is enabled again on a new
thread or when a favourite is loaded.

Right pane tabs: **Comparison** (the table of this run against the reference: label, previous, now, change,
whether the intervals overlap; the legend says nothing there is written by a model), **What changed** (the note),
**Plots**, **Results** (printed output), **Data**.

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
`runs/<tag>/stdout.txt`, `fig_n.json`. Sizes: a run's figures are the replay's Plotly JSON (hundreds of kilobytes
each); a deleted routine removes its folder. No pruning in this version.

## 9. Editions

Everything above is the same in both editions. The integrations need the executor container, as they do today; a
file routine works on the local kernel too (`--compute local`), because the runner uses the same executor client the
replay uses — the end-to-end walk (tests/e2e/test_stack.py) makes a routine in both editions.

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
2. **Run on current data** — the runner, the fingerprint and value checks, results by position, the run record, the
   comparison, S4's rows and tabs, the arrows between runs, the composer locked. Accepted when: the same data gives
   *reproduced*; a file with a column dropped gives *did_not_fit* naming it; a script error gives *failed at cell n*
   with the run kept; two runs on different data give a comparison with the overlap flags right (unit tests on the
   arithmetic).
3. **Narrate** — the Narrator, the guard, the What-changed tab and card. Accepted when: a narrative's numbers all
   come from the two tables; a run without a comparison (run zero) gets no narrative.
4. **The run dialog and the runs table** — S3 for Intervals.icu, Endura and files; S2's runs table; retirements.
   Accepted when: the e2e story runs a file routine end to end on the local stack; the Intervals dialog is exercised
   on dev with a real key.
5. **Versions** — the next-version choice is built; the inputs carried through the manifest, the boundary in the
   table, the warning on deleting an origin. Accepted when: v2's inputs keep their keys; the runs table shows the
   divider and the gaps; a deleted origin leaves the routine runnable and marked.

Each step ships as its own patch, tested on dev before prod, the standing method.

## 12. Open decisions

- **Run zero when the original data is gone.** Built as: create unverified and say so; the first run on data tells.
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
