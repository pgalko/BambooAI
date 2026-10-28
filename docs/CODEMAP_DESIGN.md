# The code map — design v1.5 (2026-10-28)

The code map shows how one analysis chain got from its data to its numbers: which inputs each cell read, what each
cell made, which number rests on what, and what was typed into the code rather than read from the data. It is built
once, mechanically, when the chain ends — from the committed cells and the kernel's own record, by rules, with no
model call — and kept with the chain. A reader opens it from the closing card's **Code map** button or from the eye
on a chain's box in the thread map. Nothing of it reaches a prompt: the analyst never sees the map, and the map never
changes what the analyst sees.

The story in one paragraph. A coach reads "regime B out-yields A by 0.57 t/ha within soil type" and wants to know
where that number came from without reading twenty cells of Python. The map answers in the reader's words: the
dataset, grouped by plot and regime, then an estimate computed by a helper of the chain's own, then a bootstrap of 500
resamples re-drawing the rows of the plot means, then the percentiles — with the seed and the resample count the
analyst typed in, and the note that the helper's arithmetic is not traced. Beside it, a short list worth checking:
an auxiliary file offered but never read, a date typed into cell 1 that every result rests on, a result that came out
empty. The map says how a number was made, not whether it is right; that stays with the reviewer and the reader.

Eight rules governed the build and still govern changes (the product owner's, 2026-10-20):

1. **Mechanical.** No model call anywhere in the map; the same chain always gives the same map.
2. **Grounded.** Nothing on the map that the code or the kernel did not show; where the extractor cannot tell, the map
   says so ("not traced", "not mapped", "the arithmetic is not traced"), never guesses.
3. **Invisible to the model.** Nothing from the map or the registry enters any prompt.
4. **A map failure never breaks a chain.** It is recorded on the run and the modal says the map could not be built.
5. **The top bar's dataset pills are never changed by the map.**
6. **Product decisions are asked, not assumed.** The ones taken are in section 9.
7. **Privacy.** The design package's coach fixtures, run logs, mockup and the first three visuals are never
   committed (the repository has a public remote); the other fixtures are tests.
8. **Conventions.** Plain words, British spelling, one patch per milestone, the battery green.

## 1. Vocabulary

- **Chain** — one run of the analyst (`analyst.notebook.Run`): a question, its turns, its report. Named by its id
  everywhere in the map; the page numbers chains as its navigator does.
- **Cell** — a committed code turn, numbered along the thread's path (`Turn.cell_no`).
- **ChainRecord** — everything the extractor needs about one chain, as one JSON-able dict (section 3).
- **Input** — what the chain was offered: the primary dataset, each auxiliary file, the context (CTX) files, the
  thread's documents (D1, D2, ...), and, for a follow-up, the names an earlier chain left in the kernel.
- **Object** — a name (or a tuple of names) a statement made or changed in a cell, with its kind: table, estimate,
  value, figure, function, param (a known scalar), pattern (a word list), helper (a list or dict).
- **Result** — one printed `RESULT(...)` line, with its estimate, interval and unit, by status: recorded, replaced
  (a later RESULT with `corrects=`), came out empty (`nan`); a **printout** is a cell the report cites by `[cell n]`
  that printed but recorded no RESULT line; a **figure** is one figure of the figures cell.
- **Recipe** — the boxes a result rests on, in creation order, with the inputs, the known values ("params"), the word
  lists and the choices (seeds, thresholds, typed dates, resample counts) behind it.
- **Lane** — one column of the Steps view per input; a dot where a cell reads it, a ring where it uses it through an
  earlier step.
- **Check** — a mechanical observation worth the reader's attention, each with a target it opens (section 5.4).

## 2. Architecture

```
chain ends (_finish)                       request
  record.chain_record(nb, run, inputs)       GET /code_map/<thread>/<chain>
      |                                        |
  extract.build  -> statements, lineage,       | stored map at the current version -> built "end"
  verbs, helpers, RESULT lines paired to calls | else build now (ancestors first) -> built "now", cached, never written back
      |                                        |
  objects.build_map -> objects, kinds, steps   v
      |                                   code-map.js: the modal (Steps | Recipe diagram | panel)
  view.build_view -> rows, lanes, recipes,
  diagrams, checks; self-checks
      |
  run.code_map = {version, built, ms, view, exports, selfcheck, inputs}
```

| Piece | Where |
|---|---|
| the package | `analyst/codemap/`: `__init__.py` (`VERSION`, `build`, `build_record`, `earlier_of`), `record.py`, `vocab.py`, `extract.py`, `objects.py`, `view.py`, `words.py` |
| the record kept for it | `Turn.registry` (the kernel's `{name: {type, desc}}` for the names a cell made or changed), `Turn.results[].line` (the cell line a RESULT call ran from, both kernels), `Run.mode`, `Run.code_map` |
| the build | `analyst/session.py` `_finish`, after the replay, before the run is answered; `Session(map_inputs=...)` |
| the host's inputs | `bambooai/bambooai.py` `_map_inputs`: the primary with its columns, each auxiliary file with its columns (one executor call), the context, the documents |
| the route | `web_app/code_map_routes.py`, registered after the codebook |
| the modal | `web_app/static/js/code-map.js`; rules under `#codeMapModal` in `dialogs.css`; tokens in `tokens.css` |
| the ways in | the closing card and the report's `[cell n]` chips (`stream-pane.js`), the thread map's eye (`workflowGraph.js`), the eye on a notebook cell (`analyst/render.py`); the navigator hook (`ui-controls.js`) |
| tests | `tests/analyst/test_code_map.py`, `tests/analyst/test_code_map.js`, the stack walk; fixtures under `tests/analyst/fixtures/codemap/` |

Behaviour was ported from a research prototype (the design package of 2026-10-20), not its structure: the prototype's
`exec` over a whitelist became an AST evaluator, its module-level state became arguments, its chain numbers became
ids and tokens. The golden fixtures pin the prototype's output; the departures are listed in section 10.

## 3. The ChainRecord

`record.chain_record(nb, run, inputs, context, earlier, registry_start)` draws it from the Run and its thread:

- `chain_id`, `question`, `title`, `report`, `mode`, `turns` (the turns that count, as `Notebook.failed_attempts`
  counts them: not reviews, rewrites or the figures step), `searches`, `reads`, `ideas`;
- `inputs`: the host's list (section 7.6 of the package), else from `run.data` alone. Each has a `kind` (primary,
  file, context, document, chain), a `label` that is the matching key the extractor finds (the primary's is
  "primary dataset"; a file's is its basename without the loaders' `_YYYYMMDD_to_YYYYMMDD` suffix; a document's is
  its kernel name, D1), a `name` (the primary's own name; a document's file), `columns`, `detail`;
- `cells[]`: each committed cell with its `turn`, `kind` (analysis or figures), `step` (the STEP text; for the
  figures cell "Figures: " + its captions), `code`, `output`, `registry`, `results` (the kernel's records, with
  `line`), `figures`, `captions`;
  Since 2026-10-28 each cell also carries `reaches[]`, the kernel's record of what it touched outside the data
  (docs/REACH_DESIGN.md), each record marked `asked`;
- `failed[]`: each failed attempt with its turn, the cell before it, its purpose and its error line; a cell the
  executor refused before it ran rides here with `refused` (the restricted word) and is shown as its own state;
- `sandbox`: the box the cells ran on, as the kernel saw itself (2026-10-28);
- `events[]`: the reviews (turn, verdict, the most consequential problem), the review of the report, the report turn;
- `path`, `path_cells`, `titles`: the chain's path root first, which chain each cell number belongs to, the question
  of every chain the view names;
- `registry_start`: what the kernel held when the chain began (the earlier cells' registries merged);
- `earlier`: the exports of the earlier chains on the computed path (`run.code_map["exports"]`, merged root first).

## 4. The rules, in short

The pipeline is three stages (`extract` → `objects` → `view`), each a port of the prototype's; the fixtures pin the
behaviour, so this is a summary, not the specification.

**Statements and lineage.** Each cell is parsed with `ast`; a cell that does not parse keeps its row, marked "not
mapped". Per top-level statement: the names it reads, writes and mutates (a subscript or attribute store, a container
method, `inplace=True`, drawing on a figure). A statement depends on the latest writer of each name it reads, across
cells; a name nobody wrote is a kernel input (`df`, `DS`, `CTX`, `D1`...), a name from an earlier chain, or ignored.

**Verbs.** Calls map to verbs by a fixed vocabulary (`vocab.py`): load, filter, select, combine, reshape, summarise,
derive, test, resample, record, draw, save, show, call (a helper of the chain's own), compute. Special rules: a loop
over `range(N)` whose body re-draws rows is one step "bootstrap, N resamples"; `"|".join` is not a table join; typed
choices (a date in `pd.Timestamp`, an offset, a non-zero threshold, `name = <number>`, a seed, a typed mapping, a
helper's numeric default) are listed under "Choices written into the code"; a type conversion folds into "tidy
types"; a mask bound to a name is named where it is applied; file names are resolved from constants, `+`,
f-strings and `os.path.join`.

**RESULT lines.** One result per printed line. A record's `line` pairs it with the call whose span covers it (a call
in a loop takes every line it printed; a call inside a helper goes to the statement that called the helper). Older
runs without `line` pair by order and by each label's fixed words. The kernel's record wins over the code for
`corrects`, `test` and `typed`. Status: not computed for `nan`, corrected when a later RESULT has `corrects=`.
A `[cell n]` the report cites that recorded no RESULT line becomes a printout, traced from its print statements.

**Helpers.** A function the chain defined is read from its own code: its steps, whether it always re-draws rows or
only under an `if` on a parameter (then "can resample", switched on when the call passes `rng`, `random_state`,
`seed` or `generator`), which parameter's rows a re-draw takes (followed through aliases), whether its return is
arithmetic the vocabulary does not name ("the arithmetic is not traced"). Inside a helper, a parameter named for a
generator and a generator it makes are generators. The analyst's own description of a helper is never used.

**Objects and kinds.** One object per statement output (a tuple assignment is one object; a figure drawn is split
out); kinds by a first-match ladder in which the registry's type wins over the verbs (a DataFrame is a table, a
number behind a test or a re-draw is an estimate, a name with a known value is a param). Known values are evaluated
without the data: constants, known names, date arithmetic, set algebra on column sets, the safe calls.

**Recipes and labels.** Boxes are tables, estimates, figures and values made in the code; a value read off a table
with no operation of its own stays inside that table. A table is named by its input's app name plus what its steps add
(a date window, "by soil", a pivot, ", joined"); an estimate "estimate: <method>"; a value by its variable and size.
A box with one parent box in the same cell and family merges into it ("a → b"). Each step is said in plain words
with a one-line gloss under each method.

**Inputs.** Status used (a result, a cited printout or a figure rests on it), via (reached only through an earlier
chain's names), loaded (read, nothing that counts rests on it), unused (offered, never read). A column counts as
used when its name appears in a statement of an object made from that input. An input a `RESULT` or `print` reads
itself, with no table in between, counts as read. A document whose passage the report cites (`[D1.3]`) counts as
used.

**Checks**, in this order: citations into an earlier chain's cells; reliance on an earlier chain's names; an input
offered and never read, or loaded and never used; no RESULT line while the report cites a printout; a value typed
into the code with how many results rest on it; results that came out empty; results replaced by later cells; word
lists typed into the code.

**Self-checks**, before storing: RESULT records against results built per cell; a figure whose recipe has no data
box and no input while its cell reads data; a result or printout with an empty recipe and no input. Each marks the
view (`traced: false`) and is listed in `selfcheck`; nothing blocks the chain.

## 5. What is stored, and the route

`run.code_map = {version, built, ms, view, exports, selfcheck, inputs}` (version 3 since 2026-10-24: the recipes carry the
lines behind each number); on failure `{version, built, error, inputs}`,
and when even the import fails, `{"error": ...}`. `exports` (the names and helpers the chain left in the kernel, for
later chains) and `inputs` (as the chain ended, with the auxiliary files' columns) let a later rebuild give the same
map without the host. `view` is one chain's entry of the fixtures' `viewmodel.json`, with chain ids in place of
numbers (`path`, `pathTitles`, `inputs[].chain`, `inputs[].through`, `steps[].takes_chain[].chain`, `checks[].chain`;
input nodes `in:chain:<id>`; texts carry `{chain:<id>}` tokens), diagrams as nodes and edges only (the client lays
them out), and `version`, `chain_id`, `titles`, `meta`, `sizes` (false for an old run with no registry), `mapped`,
`traced`. A chain's map is 20-70 KB; the thread file is rewritten after every turn and grows by that much per
chain (a sidecar file is the fallback if that ever matters).

`GET /code_map/<thread_id>/<chain_id>`: 400 for ids of the wrong shape, 404 for an unknown chain or thread; for a
running chain `{"state": "running"}`, for one that ended without an answer `{"state": "unfinished"}`; a stored map
at the current version as `{"built": "end", "map": ...}`; a missing, stale or failed one is built now from the inputs
the stored map kept (else `run.data`), its ancestors without current exports first, root to leaf, cached in the
process (64 entries, a failure not kept) and never written back, because the live session rewrites the thread file
after every turn; when that build fails too, `{"error": ...}`. The notebook is the live instance's when it holds the
thread, else the thread file. `codemap.VERSION` goes up whenever the rules or the view change; nothing migrates in
place.

## 6. The modal

`#codeMapModal` sits past the rail and the top bar like the thread map drawer, 24 px from the edges, so the chain
navigator stays usable: the open map follows it (`CodeMapUI.onChain` at the end of `updateNavigationButtons`), and
opening another chain from inside the map moves the app there (`navigateToChainId`); a chain the navigator does not
hold (not favourited before a reload) is read straight from the route and named "an earlier chain", its question as
the tooltip. One function renders every `{chain:<id>}` token and path step as "chain n" (the navigator's number) or
"an earlier chain".

- **Header**: "Code map", the chain's number, its path (each earlier chain a link), the facts (mode, turns, cells,
  failed attempts, reviews, RESULT lines; whether the map was built at the chain's end or now rides on that span as
  `data-built`, not in words), the report's title, the question; Steps | Recipe diagram; ×; the legend of the view
  shown.
- **Steps**: one rotated lane per input (used in blue with its columns, loaded, struck when never read; a chain lane
  opens that chain; the lanes head is as tall as the longest name, capped at 136 px with the rest an ellipsis and the
  whole name in the tooltip), one row per cell with "Cell n · turn t", the STEP sentence (up to 320 characters, three lines),
  verb chips with tooltips, the lane dots, and what came out: result chips by status (recorded, replaced by cell n,
  came out empty, a cited printout, the figures; a chip's label up to 96 characters, wrapping to two lines, the whole
  label in its tooltip), or a note (carried forward to N later steps; printed what the report cites; printed only; N figures
  drawn after the report; not mapped). Failed attempts on a red tint with their error; review bands; the report
  turn. A selection fades the rows and lanes outside its recipe.
- **Recipe diagram**: a picker of every result, printout and figure — a button and a listbox of the map's own, so the
  list always drops below the button (a native select's menu opens wherever the browser puts it) and a long label
  wraps; arrows, Home and End move, Enter picks, Escape closes the list and not the map, a click elsewhere closes it;
  dagre (the page's global) lays the nodes out,
  with a hidden root above the inputs so they sit on the top row whatever they feed; edges from dagre's points as one
  SVG string (centre to centre under the harness's stand-in, which gives none); a box carries its label, its names
  and up to three lines of its first steps (200 characters; the rest in its tooltip); a box opens its step, a "From
  chain k" input opens that chain, the result opens its recipe. The area scrolls both ways. **Zoom** (2026-10-24),
  as the thread map has it: out, the level, in, fit, at the diagram head's end; Ctrl/Cmd and the wheel; 30 %–200 %
  in steps of 15 %. A diagram shown for the first time is fitted to the frame (never enlarged past 100 %); a reader's
  zoom stays while the same diagram is on screen; the frame takes the scaled size, so the area scrolls no further
  than the drawing.
- **Panel**: nothing selected — how to read it, the data this chain used with its columns, Worth checking (each a
  button that opens its target), the counts; a result — the number, its interval and unit, the label, its status
  ("recorded"), the line "The map shows how this number was made, not whether it is right", Made from, How it was made
  in order (each box with its names, cell, size and glossed steps), the settings it depends on (typed ones marked),
  the choices, the word lists, Rests on cells, Open in the notebook and, beside it, the other view of the same recipe
  (**Recipe diagram** from the Steps view, **Show in the steps** from the diagram; 2026-10-24). *Open in the notebook*
  from a recipe lights the lines behind the number in the Investigation tab (2026-10-24): each recipe carries `lines`
  (per cell, the spans of every statement the number rests on - the result's closure, touching spans merged) and
  `own` (the RESULT's own statement); the notebook draws a translucent bar behind each span, the own one strong,
  placed by line number so the syntax colouring is untouched, in every cell of the recipe, and clears them when
  another cell is opened. Where the map could not trace, nothing lights. A printout and a figure likewise with their
  own heads; a step — why in the analyst's words, its role, what it uses (inputs, names from earlier cells and chains),
  what it made with sizes, the figures it drew, what it printed, the results it recorded, the later steps that use it,
  its lines, Open in the notebook.
- **States**: loading; "The code map could not be built for this chain."; "The code map is built when this chain
  ends."; "No code map: this chain ended without an answer."; "The code map could not be read."; a chain with no
  code: its one line with its citations.
- **Keyboard and readers**: a dialog with its label; Escape closes; the focus lands on the close and returns to the
  opener; every clickable element is a button or a link with words; every colour-coded state carries text; lane dots
  say what they mark; no text below 11 px.
- **Backdrop**: the modal sits past the rail and the top bar, so the dataset pills and the rail stay as they are; the
  working window under it is dimmed by a heavy scrim (`--scrim-heavy`, both themes) and blurred.
- **Ways in**: the closing card's **Code map →** button on its links line (the links' style and size with a slight
  border; for an answered chain that ran code; the chain id rides in the saved markup, so a restored card still
  opens its map); the eye on a chain's box in the thread map drawer, shown on the hovered box and the open chain's
  (it moves the app to the chain, closes the drawer, opens the map); and a `[cell n]` citation in the report or its
  plain-language version (2026-10-24): the chip opens the map on the Recipe diagram at that cell's recorded number -
  the cell's one number, or of several the one the sentence names (a number in the sentence equal to the estimate or
  an end of its interval, the report's rounding allowed for) - and otherwise on the Steps view at the cell's row.
  The chip hands the map the words before it in its block, from the last sentence end. The cell's code is a click
  further, from the panel's *Open in the notebook*. And the eye on each committed cell's header in the Investigation
  tab (`analyst/render.py`, 2026-10-24), the thread map's glyph, opens the map on the Steps view at that cell - the
  loop closed from the notebook's side; inline, so a saved favourite's cells keep it. The map never opens on its own.

All of the modal's own words sit in `WORDS` at the top of `code-map.js`; the map's content comes from `words.py`.

## 7. Tests

- `tests/analyst/test_code_map.py` (80): golden parity with the design package's fixtures (the field trial and its
  follow-up, the planted-flaw chain, a five-chain branching thread; the whole view and the intermediate map, in both
  pairing modes); one synthetic cell per rule; the build from a Run and a follow-up; the field-trial scenario run on
  a real kernel through the Session, whose views are the golden ones; the route's every answer, the cache, the live
  notebook; a ten-chain thread served and built now in well under a second; the host's file-name table pinned to
  `intervals.js`.
- `tests/analyst/test_code_map.js` (51): every builder on the prototype's views, the layout, the module on the mini
  DOM with a scripted route, the ways in and the hook pinned in their files.
- The stack walk: the map through the real app and executor — the card's button, a recipe with the kernel's sizes,
  the diagram, the drawer's eye, a restored favourite's card, Escape; the document chain's D1 lane.
- Before a release, the coach chain is run from the design package locally (never committed): its view must equal
  the prototype's but for the departures below.

## 8. Known limits (stated on the map, never hidden)

Which branch of an `if` ran; names computed at run time (`df[col]` in a loop); changes inside unknown library calls;
row counts inside a cell (the registry gives a name's shape at the end of the cell); exact column use (close, not
exact); a helper's arithmetic (listed as its steps, then "the arithmetic is not traced"); numpy numbers and dates
show their type, not their value (the registry's text is what the analyst reads, and it must not change); captions
are paired with figures by order; whether the method was right. Coding styles not yet in the fixtures (scikit-learn,
statsmodels formulas, SQL/polars, `plt.plot` with no figure variable, classes) will need the vocabulary extended;
every chain style that breaks the extractor goes into the fixtures.

## 9. Decisions taken (the product owner, 2026-10-20)

1. Colours as in the mockups, adjusted to the app's tokens (data inputs in the look-up blue).
2. "Recorded" instead of "stands", and the line "The map shows how this number was made, not whether it is right".
3. The run's mode on the header (`Run.mode`).
4. Two ways in: the thread map's eye on each chain box (shown on hover and on the open chain's) and the closing
   card's button; the map never pops up on its own; no Code tab entry. *Amended 2026-10-24: a third way in - a
   `[cell n]` citation in the report opens the map on that cell's number (the cell's code is a click further, from
   the panel); and a fourth, the eye on a committed cell in the Investigation tab, which opens the Steps view at
   that cell. The map still never opens on its own.*
5. The map is opt-in: no checks on the closing card. *Amended 2026-10-28: the reach report (docs/REACH_DESIGN.md)
   is on the closing card - a security matter, not a map check - and the map's summary panel carries the same lines
   under "Reaches outside the data", each a button to its step; a step row carries the cell's reach chip and a
   refused attempt is its own row.*
6. The five further checks (an interval with no width, an estimate outside its interval, rows behind each estimate,
   filters that drop most rows, numbers in the report with nothing behind them) are a follow-up.
7. Documents are inputs, mapped like CTX.

## 10. Departures from the prototype

Each from a rule test, verified against the code: an input a `RESULT` or `print` reads itself counts as read (the
prototype said "offered, never read"); a value read off a dataset with no table in between still names the dataset;
a helper of the chain's own wins over a vocabulary name (`diff()`); inside a helper a parameter named `rng` and a
generator it makes are generators, and `rng.choice(x, n)` re-draws `x` (so a helper's re-draw follows its parameter
through `ga, gb = g[...], g[...]`; at the top level a bootstrap loop's step adds ", re-drawing the rows of x"); a
document the report cites by passage counts as used; the no-code header leaves out "0 web searches"; chain ids and
`{chain:<id>}` tokens instead of numbers; a stored failure is rebuilt on request.
