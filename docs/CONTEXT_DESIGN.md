# Context — design v0.1 (2026-10-13)

The words written beside the data — what the person the data describes wrote under a session, what their coach
answered, the day's note, the plan's wording, the illness logged — brought into the analysis as data with
provenance, so that an analysis can set numbers against words and say what rests on which. The seed is a
mixed-methods conversation of 2026-10-11 (kept with the delivery notes, outside the repository): three shapes of inquiry (numbers
first, words first, both at once), two parameters (which stream leads, whether they meet in sequence or at once),
one artefact (the joint display, where the mismatches cannot be avoided), and four traps (parallel play, selection
bias, reductive translation, lead-lag). The facts are the inventory of 2026-10-13 (`INTERVALS_CONTEXT_INVENTORY.md`):
on two very different accounts the words are under the activities, about two short messages per session between the
subject and the coach, in three languages; the scales and plan-versus-done are the numbers beside them; custom
fields and tags are a coach's own vocabulary already in use.

**The principle.** A passage is data: a dated row with its author and its source, quoted as written, cited by its
locator. The model's reading of a passage — its code — is a *second* table, one row per code, each carrying the
words it rests on. The analyst computes on both as it computes on anything, reads a passage with grep or READ when
it needs the words, and the report cites `[C.417]` beside `[cell 7]`. **Everything the model writes is English** —
codes, the map, the digests, the report; a passage written in another language is kept as written and rendered
into English once, at load, by the coder, and it is the rendering the analyst reads and the report quotes, marked
as a rendering, with the original a hover away. What is quoted, what is counted and what is
the analyst's own interpretation are told apart by mechanism — a quote is verified verbatim, a count is a cell's
output, the rest is the analyst's — never by a vocabulary the model has to maintain (checklist C1). Nothing
prescribes a method (C2); the contract states the standard a claim about *why* must meet, and the reviewer looks
through one more lens. The text never enters a prompt whole (C7): a map rides in DATA, the words are reached by
tools, and the one expensive step — coding every passage — happens once per load on a cheap seat.

## 1. Vocabulary

- **Passage** — one dated piece of writing from one author in one place: a message under an activity, a day's
  wellness comment, a calendar note, the prose of a planned workout, an illness or holiday entry, a tag, a coach's
  tick with its wording, a custom text field's value. The unit of context; `C.417` is its locator.
- **Kind** — where the passage was written: `activity_message`, `activity_note`, `wellness_note`, `day_note`,
  `plan_note`, `status`, `tag`, `coach_tick`, `custom_field`; later `chat_message`, `athlete_note`, `availability`
  (§12). The kind is a column value, data to the model.
- **Author** — who wrote it: the subject (the person the data describes), a coach, another member; id, name and
  role on the row. Two staff wrote on the professional's account; "coach" is a role, not a person.
- **The context table** — one row per passage, long format, a file of the load like the summary and wellness
  files. **The codes table** — one row per code on a passage, with the quote it rests on. Two files, never merged.
- **Codebook** — the vocabulary of codes, enforced: a code the coder may use must be in it. Seeded (§13), per
  user, grows by stored proposals a coach confirms. English codes, English definitions.
- **Rendering** — the English text of a passage written in another language, made once at load by the coder and
  kept on the row beside the original (`text_en`). The analyst greps and reads renderings; the report quotes them,
  marked *rendered*; the original stays the record and is shown on hover. An English passage is its own rendering.
- **Code** — one label from the codebook on one passage (`fatigue`, `deviation`, `instruction`). A passage can
  carry several or none. **Tone** — negative / neutral / positive, one per passage, from the coder.
- **The coder** — the one model call that reads every passage of a load once, in batches, and writes the codes
  table. A seat (`Coder`), the Reader's when absent. Its prompt is generic; the codebook rides as data.
- **The map** — the few lines in DATA that tell the analyst what context exists: the span, passages per kind and
  month, authors, languages, the codes with their counts, where the files are. Never the text.
- **`CTX`** — the context in the kernel: the two frames, grep, a window around a date, the passages on an activity.
- **READ CTX** — the documents' READ over the passages: candidates by search within a stretch or a date range, the
  Reader quoting verbatim under locators.
- **Window** — the days around a date a join uses (`CTX.around(date, days=3)`): words lead or lag numbers, so a
  same-day match is the wrong test. The analyst chooses the width; the default is a number, not a rule.
- **Plan versus done** — the activity's `paired_event_id`, its `compliance`, the plan's prose and the words
  written after: the first joint display this design is built to make easy.

## 2. What this builds on

- **Documents** (`docs/DOCUMENTS_DESIGN.md`): units with locators, files not tables, the kernel objects from a
  prelude, a map in DATA, a contract section joined only when present, the `READ` action with BM25 candidates and
  the Reader seat quoting verbatim, every quote checked against the unit's text, the report's citation chips with
  hover and click. Context reuses every one of these; the passage is a unit whose "page" is a date.
- **The Intervals.icu load** (patches 0116–0125, 0136): auxiliary files named by kind and window
  (`AUX_KINDS` in `analyst/routines.py`), kept in the key's folder in the executor's cache, listed by
  `/cache/inspect`, matched by `cache_match` for a routine's run, described in DATA by `_auxiliary_block`. The
  context and codes files are two more kinds in that table and travel the same way.
- **Routines**: the recorded data shape binds auxiliary files by kind; a run loads the same way; results are
  compared by position. A routine that counts codes compares them like any result line.
- **The reviewer** (`analyst/reviewer.md`): five lenses, one line each; a sixth when context is present.
- **The report guards**: numbers in the report exist in cell outputs; a cited passage is verbatim (`_unit_text`).
- **The seats**: `Promoter` set the pattern — a seat in every tier of the template, the analyst's when absent.
  `Coder` follows it, falling back to the Reader's seat (cheap, text work).
- **The probes**: `icu_chat_id` is null exactly when nothing was written under an activity; 0.35 s a message call;
  no rate limit seen; custom field values ride under the field's `code`; race descriptions can be HTML;
  `end_date_local` is exclusive; 1 is the good end of every wellness scale.

## 3. The records

### 3.1 The context table — `context_notes_<start>_to_<end>.csv` (kind `context`)

One row per passage, in date order, ids given in that order and stable for the load:

| column | what |
|---|---|
| `id` | `C.1`, `C.2`, … (`C` alone: one context per load; a second subject in a thread is §12) |
| `kind` | one of the kinds in §1 |
| `date` | the local day (ISO) — the message's `created`, the day's entry, the event's start |
| `time` | the local time when the source has one (messages), else empty |
| `end_date` | the last day of a span (`status`: sick, injured, holiday), else empty; **inclusive** (the API's exclusive end minus a day) |
| `activity_id` | when the passage hangs off an activity (messages, activity notes, tags, ticks, custom activity fields, and a plan note through `paired_event_id`) |
| `event_id` | for calendar passages |
| `source_id` | the message id, the event id, the day — what the source calls it |
| `author_id`, `author_name` | from the message or `created_by_id`; the subject's own id for their entries |
| `author_role` | `subject`, `coach`, `other` (the chat's member roles decide `coach`; the key's athlete is `subject`) |
| `private` | true for `hide_from_athlete` entries and private wellness keys (only present under a coach's key) |
| `lang` | the coder's detection (`da`, `no`, `en`), filled by the coding pass; empty before it |
| `text` | the passage as written, plain text: HTML stripped, whitespace normalised, a plan's structured step lines removed (they are in the planned workouts table, §3.1a; the prose stays) |
| `text_en` | the English rendering, written by the coder at load; equal to `text` when `lang` is `en`; empty before the coding pass |
| `chars` | the length of `text` |

What becomes a passage: a message of type `TEXT` or `NOTE` not deleted; an activity `description` that is not
empty and not only a workout structure; a wellness `comments`; a `NOTE` event (its name and description joined);
a `WORKOUT` event's prose (name kept as a prefix: "Endurance: adjust power to altitude"); `SICK` / `INJURED` /
`HOLIDAY` / `RACE_*` / `SEASON_START` / `TARGET` events as `status` rows whose text is the event's name and
category; every activity and event tag as a `tag` row (text = the tag); a coach tick as a `coach_tick` row (text =
its wording, the value in the summary); a custom field of type `text` or `select` with a value, on a day or an
activity, as `custom_field` (text = "field: value"). The numbers beside the words — `feel`, `icu_rpe`,
`session_rpe`, `compliance`, the seven scales, the tick's value, numeric custom fields — stay in the summary and
wellness frames; the activity summary gains `description`, `tags` (joined by `|`), `coach_tick`, `compliance`,
`paired_event_id` and `icu_chat_id` so that the join needs nothing but the frames.

### 3.1a The planned workouts table — `planned_workouts_<start>_to_<end>.csv` (kind `plan`)

The prescription, on the numbers side (2026-10-15; built with the context and written beside it - the page asks for
both under the one Context option). The design above was right to keep a planned workout's step lines out of the
words - `-10m 220w` is not something anyone wrote to anyone, and the coder never sees it - but it left them with
no home at all: of one rider's 237 plan notes, four carried a watt figure in prose, so "how close did he get to
what I asked" had only the platform's compliance score to stand on. One row per `WORKOUT` entry on the calendar:

| column | what |
|---|---|
| `event_id`, `date`, `name`, `type` | the entry, its day, its title, the sport |
| `author_id` | who set it (`created_by_id`) |
| `activity_id` | the activity it was done as (through the activity's `paired_event_id`); **empty for a session not done** - the skipped sessions are these rows |
| `compliance` | that activity's compliance as Intervals scores it (the same number the summary carries as `workout_compliance`) |
| `planned_duration_sec`, `planned_load`, `planned_distance_m` | the plan's numbers (`moving_time`, `icu_training_load`, `distance`) |
| `load_target`, `time_target`, `distance_target` | the targets, when set |
| `prose` | the plan's prose, as the context's `plan_note` has it |
| `steps` | the step lines as written, newline-joined - the lines the context leaves out (a bare repeat count on its own line, "4x", is a step line too) |
| `workout_doc` | the structured workout as Intervals keeps it, as JSON text (each step's duration and power target); empty when the entry has none |
| `availability` | the day's `training_availability` when other than NORMAL |
| `tags` | the entry's tags, joined by `\|` |

The calendar is fetched once per load (`fetch_calendar`) and serves both this table and the context. A routine
made from a chain that read it carries `plan` among its load's kinds; a cached load is cut to a window by `date`.
The laps file holds the executed side (labels, zones, watts per lap), so prescription and execution are two tables
a method can join by `activity_id`. Known limit: the DATA head of this file is cut by the `workout_doc` column's
length; a compact structure column can follow once the shape of `workout_doc` is known from a live load.

### 3.2 The codes table — `context_codes_<start>_to_<end>.csv` (kind `codes`)

One row per code on a passage:

| column | what |
|---|---|
| `id` | the passage |
| `code` | a code from the codebook (or a proposed one, marked) |
| `tone` | the passage's tone (repeated on each of its rows) |
| `quote` | the words the code rests on, verbatim from the passage as written (`text`), so the check is mechanical; the English is on the passage's row |
| `status` | `codebook` or `proposed` |
| `coder` | the model string |
| `codebook_version` | the codebook's version at coding |

A passage with no code has no row; the map counts the uncoded. The table is written by the app after the load
(§4) and uploaded beside the context file (`/file_utils/upload_aux_dataset`), so the kernel, the cache and a
routine see it as one more auxiliary file.

### 3.3 The codebook — `storage/<user>/context/codebook.json`

```
{ "version": 3, "updated": "...",
  "codes": [ {"code": "fatigue", "group": "body", "definition": "tired, heavy, flat, no energy, needing rest",
              "status": "seeded" | "confirmed" | "proposed", "proposed_by": "<model>", "proposed_on": "...",
              "examples": ["C.12 of 2026-08-14: '...'"], "uses": 31} ] }
```

Seeded from §13 the first time a user loads context; per user (a coach's codebook covers all their subjects, so
counts compare across them); a proposal is a code with a definition the coder asked for and could not find; it is
stored `proposed`, used for the labels of that load (marked), and waits for the coach (§7 S3). The version bumps on
every confirmed change; the codes file records the version it was coded under.

### 3.4 The map (in DATA, with the context present)

```
CONTEXT (the words written beside the data; in the kernel as CTX; files context_notes_… and context_codes_…):
  2026-06-15 to 2026-10-13: 212 passages — activity_message 198 (the subject 121, coach 73, other 4),
  day_note 13, plan_note 1, tag 9, custom_field 6; by month Jun 41, Jul 58, Aug 55, Sep 44, Oct 14; languages da, no.
  codes (the model's reading, one row per code, with the words it rests on): fatigue 31, execution 28,
  effort 22, sleep 14, illness 9, deviation 8, … (23 of 36 codes used); 11 passages carry none; 2 codes proposed.
  A plan_note is dated the day it was planned for, not the day it was written.
```

Ten lines at most; the rest is reached by `CTX` and READ. The closing line says what is true of this data and
nowhere else; the rules — how a passage is cited and quoted, a code as a reading, the words and the numbers days
apart — are the contract's Context section, once (step 4 removed them from here, where they had been repeated). The data record a routine keeps gains `aux_kinds`
`context` and `codes`, nothing else.

## 4. Flows

### F1 — The load

Entry: the Intervals.icu load as today (the Data tab's dialog, a routine's run dialog), with *Context* on by
default in the auxiliary kinds. In the container, after the summary, wellness and intervals:

1. `GET /athlete/{id}` — the subject's id, `coach_ticks` wording, `icu_wellness_keys`; `GET /custom-item` — the
   text and select fields (`content.code`, `content.type`, `content.options`).
2. `GET /events?oldest&newest` — every category; the kinds of §3.1 from them; HTML stripped; the exclusive end
   turned inclusive.
3. For each activity with `icu_chat_id` set, `GET /activity/{id}/messages?limit=100` — about two in three
   activities; 0.35 s each; the chat's members (from the first message's chat, or `GET /chats/{id}`) give the
   roles. Deleted messages dropped; `ACTIVITY` / request types dropped. Since 2026-10-15 the chat of an activity
   older than sixty days whose file is unchanged is taken from the executor's store instead of fetched
   (docs/INCREMENTAL_LOADS_DESIGN.md); a load's *Refresh everything* fetches every chat again.
4. The activity summary's new columns (§3.1); the context table written beside the other files in the key's
   folder; the job's result names it.

In the app, when the job completes with a context file: the **coding pass** (§6) in batches of about forty
passages — codes, tone, language, and the English rendering of every passage not in English, written back into
the context file's `text_en` — the codes file uploaded beside it and the context file re-uploaded with its
renderings. Built (step 3, 2026-10-14) **behind the load, never in front of it**: the load completes as today the
moment the executor's job does — the pills, the Data tab, the DATA block with the map — and the app codes in a
thread meanwhile: the passages an earlier load of this subject already coded are reused from the store (§12 D1),
the rest go in batches of twenty, six calls in flight at once, with reasoning off on the Coder seat; a second
round reads only what the first left unanswered. The context pill carries a spinner and *coding…* while it runs
(`/intervals/context_coding/<job id>` says where it is); when it ends the codes file gets a pill of its own and
the context pill's tooltip the pass's line — *201 of 212 coded, 180 already coded by an earlier load, 43 rendered
into English, 2 codes proposed*. A question asked meanwhile works on the words as written, and DATA says the
codes are still coming; a routine's run waits for the pass, since its counts depend on the codes. (The first
build held the load for the pass: seven minutes on a 223-passage window, three of six calls empty — the model
had reasoned at its default depth because the non-streaming path sent no effort, and forty passages with
renderings overran the reply cap; nobody would sit through that.) No card in the pane: the pane belongs to a
chain, and a load has none. The pass is a query for the account's purposes, authorised and charged as Save as
routine's call is.

Failure states, each a sentence in the card, none fatal to the load:
- Intervals refuses or times out on a context call (403, 429, a network error): the file is written with what was
  fetched before the failure, the card says which call failed and what is missing; a load with no context file is
  the load of today.
- A window with no words: a table with no rows, the map's first line says so, the coder is not called.
- The coder's reply cut or not JSON: one retry on the batch; a batch that fails twice leaves its passages uncoded
  and the card counts them.
- A code not in the codebook without a proposal: the row is dropped and counted; a quote not verbatim: the row is
  dropped and counted (the Reader's rule).
- A cached window from before this feature (no context file beside the frame): the context fetched alone for the
  cached window, a small job of its own; the frame is not re-downloaded.

Cost, from the probes: ~100 calls and ~35 s for 120 days of a daily-writing subject; the coder's pass ~10–15 k
tokens of a cheap model, cents. Nothing persists between sessions except the codebook; a wiped cache means a
re-fetch and a re-coding, as for every file.

### F2 — The analysis

The analyst sees the map in DATA and has `CTX` in the kernel (§5). It filters, joins and counts in cells; greps
when it wants words; `READ CTX` when it wants the sentences that answer a question, quoted. The report cites
passages as `[C.417]`, quoting the English rendering, verified verbatim against `text_en` by the existing guard
and marked *rendered* when the original is not English; counts of codes are numbers from cells, checked
like any number; what the analyst makes of the words beside the numbers is its reading, said as such, under the
contract's standard (§6). The reviewer's sixth lens reads the report for exactly that (§6).

**Who chooses the shape.** Nobody in the app: the question does, and the analyst follows it, as the checklist
requires (C2 — no prescribed method, no mode switch). The design's job is to make each of the seed's three shapes
cheap with the same few mechanisms, so that the shape a question calls for is the easy path:

- *Numbers first* ("the power dropped in week 3 — what was written?"): filter the frames, then `CTX.around(date,
  days)` or `READ CTX 2026-08-10..2026-08-24 …`, quote what answers.
- *Words first* ("what comes up in the notes, and how does it relate to load?"): `CTX.codes()` counted by week or
  by code, joined to the summary and wellness frames, then the numbers behind the themes.
- *Both at once* ("where do the words and the numbers disagree?"): the join with a window — passages, codes and
  the day's numbers in one frame — and a pivot of codes against quartiles of a number: the joint display, drawn as
  any other figure.

The seed's two parameters are not settings. *Which stream leads* is in the question's wording; *whether they
meet in sequence or at once* is a property of the method the analyst builds, visible in its cells. A routine
freezes a shape: it is a chosen shape re-run on new windows. The four traps are met by mechanisms rather than
instructions — parallel play by the join itself and the contract's standard (what rests on what); selection bias
by the coder reading every passage of a load, not only the ones around an alarm; reductive translation by every
code carrying the words it rests on, with the original a hover away; lead-lag by the window in `around` and the
contract's sentence that the days can differ — and by the reviewer's lens, which asks whether the report met them.

Failure states: a `[C.n]` that is not a passage or not verbatim → the existing disclosure line (the report is
shown, the citation marked); `READ CTX` over a stretch with no passages → the Reader's "nothing" digest; a
question that needs words the window does not hold → the analyst says so, as with documents.

### F3 — A routine's run

A routine made from a chain that read context records `context` and `codes` among its auxiliary kinds; its run
loads them with the window (F1 in the run dialog's load, the coder included); the method's lines that print counts
are compared like any RESULT line; a run on a window with no words prints zeros and the comparison says *no
passages in this window*. A method that cites a passage id does not survive another window (ids are per load) —
the promoter's existing rule, values read off the data are variables, covers it: a routine counts and filters, it
does not cite.

### F4 — The codebook

Seeded on first use; proposals arrive with loads; the coach opens the codebook page (S3), confirms a proposal
(renaming or merging it into an existing code), or declines it; a confirmed change bumps the version and applies
from the next load. Nothing is re-coded retroactively (a load's codes carry their version).

## 5. In the kernel and in the prompt

- **`CTX`** is built by the prelude, like the document objects, from the two files: `CTX.frame()` — the context
  table as a DataFrame; `CTX.codes()` — the codes table; `CTX.grep(pattern, kind=None, author=None)` — rows whose
  English rendering matches (`original=True` for the text as written); `CTX.around(date, days=3, kind=None)` — the passages within the window; `CTX.on(activity_id)` — the
  passages of one activity; `CTX.between(a, b)`; `CTX.text("C.417")` — one passage with its date, kind, author, the rendering and, when it differs, the original.
  Each returns a DataFrame or a string; the analyst prints what it needs, as with data. The prelude is never a cell
  of the record; the files are mirrored by content, as the documents are.
- **The map** rides in DATA (§3.4) under the auxiliary files' description; the files' own heads are cut to the
  columns, since their rows are the text.
- **`READ CTX <what you look for>`**, `READ CTX 2026-08-01..2026-08-31 <what>`, `READ C.120-160`: the documents'
  mechanism over the passages — BM25 within the range, the top 24 with their neighbours in time, the Reader quoting
  the sentence that answers under each id from the English rendering, verified verbatim against it, the digest in
  the record (the place of a rendered passage ends *(rendered from da)*, the language as the row carries it); `SHOW READ k` re-opens one.
  A READ is a turn, three a run, as for documents.
- **The contract's Context section**, joined only when the load has a context file (`Session(context=True)`,
  beside `documents=True`), kept near the Documents section's size (737 characters as built in step 4 and
  amended by 0155; the Documents section is 578):

  > ## Context
  > The words written beside the data live in the kernel as `CTX`: `CTX.frame()` (the passages, dated, with
  > author and kind), `CTX.codes()` (the codes on them, with the words they rest on), `CTX.grep('pattern')`,
  > `CTX.around('2026-08-14', days=3)`, `CTX.on(activity_id)`, `CTX.text('C.417')` - print what you need in a
  > cell. READ CTX quotes passages under ids like [C.417]; the report cites one as
  > [C.417] beside [cell 7], as written or in its English rendering, marked *rendered*. A code is a model's
  > reading of a passage, not the writer's words; the words and the numbers can be days apart. Where the report
  > explains a number by what was written, it says what that rests on - passages quoted, counts of codes, or
  > your reading.

  Step 4's trim took out what did not change what the model does: *a count of codes is a number like any other*
  (a question that asks for counts gets them), *you write in English* (the question and the contract are), and
  *mapped in DATA* (the map is there to be seen). It had also taken out the two frames' descriptions, and the
  first run under it showed they do change what the model does: with `CTX.codes()` a bare name, the analyst
  reached for the codes file by the path DATA lists (the thing still described) and, on a words question, never
  glanced at the codes it had consulted in every chain of the session before (0155 put the descriptions back,
  in a clause each). The four call examples have never been called in nine chains - the analyst does the same
  work in pandas on the frame, with its own three-language patterns over `text` and `text_en`, which is more
  than `grep` does - and are kept until the benchmark's `context_enabled` rows have run (`on` and `around` are
  the natural moves of two of them); still unused then, they come out. No method, no step order, no vocabulary
  to maintain (C1, C2); the C5 scanner runs over it. The sport's own
  rules — what counts as a divergence, when a plan may change — are not here (§12 D8, D9).

### 5.1 Documents and context in the same thread

A thread can have both: up to four documents attached and a load with context. They are two things to the analyst
— a document is something written *about* the data or the question (a paper, a protocol, a transcript); context
is what was written *beside* the data, dated — and the design keeps them apart while running them through the
same machinery:

- **Two preludes, one kernel.** The documents' prelude defines `D1`, `D2`, …; the context prelude defines `CTX`.
  The session runs both (concatenated, documents first) at the start of a run and after a rollback; the replay
  prefixes both to the script. Neither is a cell of the record.
- **Two sections in the contract.** `Session(documents=True, context=True)` joins the Documents section and the
  Context section, in that order; each is joined only when its thing is present, so a plain run's contract stays
  byte-identical. Their sizes add: the Context section is held near the Documents section's size (737
  characters since step 4's trim and 0155; Documents is 578).
- **Two scopes of READ, one budget.** `READ D1 …`, `READ ALL …` (all documents) and `READ D1.35-41` are the
  documents' scopes; `READ CTX …`, `READ CTX <from>..<to> …` and `READ C.120-160` are the context's. `ALL` does
  not reach into the context and `CTX` does not reach into the documents: the analyst names which it wants. The
  budget stays one — three READs a run — shared between them (C6: one rule until a run shows two are needed).
- **Two locator namespaces, one guard.** `[D2.17]` and `[C.417]` are told apart by their prefix; the report
  guard that checks a cited passage verbatim resolves `D<n>.<k>` against the document's unit and `C.<n>` against
  the passage's English rendering. The citation chip's hover shows a document passage with its page or section
  and a context passage with its date, kind and author, by the same prefix.
- **Two maps in DATA.** The documents' maps as today, then the context map (§3.4), after the auxiliary files.
- **Not coded.** Documents are read, never coded: the coder runs over the context table only. A coach who
  uploads a diary export or a transcript as a document gets READ and grep over it, not codes (§12 D13).

## 6. The model's calls, and where it is absent

- **The coder** — one call per batch at load time, the `Coder` seat (the Reader's when absent), reasoning off
  where the model allows it (the seat's effort now rides on the non-streaming path too — it had not, and a
  reasoning model thought at its default depth on every READ, promotion and coding call). The prompt
  describes the work and the format only: *here is a vocabulary of codes with definitions; for each passage,
  return the codes that apply, the tone, and for each code the words it rests on, verbatim; a passage may take no
  code; if a passage needs a code the vocabulary lacks, propose one with a definition, once.* The codebook, the
  passages (id, kind, author role, date, text) ride as data. The reply is JSON lines, one per passage:
  `{"id": "C.12", "codes": ["fatigue", "sleep"], "tone": "negative", "quotes": {"fatigue": "…", "sleep": "…"},
  "lang": "da", "text_en": "…", "propose": [{"code": "…", "definition": "…"}]}`. Validation is mechanical: codes in
  the codebook or proposed with a definition, quotes verbatim in the passage as written (whitespace-normalised),
  one tone, a `text_en` present for every passage whose `lang` is not `en` (its length within a factor of the
  original's; a rendering cannot be checked for meaning — it is marked as the model's wherever it is shown). The scanner
  covers the template; the codebook is data.
- **The Reader** — READ CTX, unchanged.
- **The analyst** — unchanged; the Context section when present.
- **The reviewer** — a sixth lens, present only with context (`reviewer(context=True)` in `analyst/session.py`
  fills the three places the brief leaves for it: the count of lenses, the bullet among the perspectives, the
  line in the format; without context the brief is byte-identical to before). Its line is parsed like the other
  five and rides to the analyst when it found something:
  > - Words: where a number is explained by what was written - whether that rests on passages quoted, on counts
  >   of codes, or on the analyst's reading, and is reported as what it is; and whether the days of the words
  >   and of the numbers were compared with a window rather than matched by day.
- **Absent**: the fetch, the table, filters, joins, counts, grep, the map, the comparison in a routine's run, the
  codebook's versioning, the guards.

Where the seed's coaching rules go — *no single metric moves a plan; a change matters when the subject's own
account changes; review in arrears* — is a decision (§12 D8, D9): they are rules for coaches and for what a
routine's narrative may say, not analysis methods the contract may prescribe (C2).

## 7. Screens

- **S1 — The load.** The Data tab's dialog gains nothing visible: context is one of the auxiliary kinds, on by
  default, with the others' checkbox pattern if one is wanted. The dialog's line carries the pass's report (§F1). The
  context and codes files stack under **one Context pill** (2026-10-14, as the documents do): the label with the
  days and a spinner with *coding…* while the pass runs; the hover list naming the passages and the codes, each a
  click away from the existing preview (first rows) — the preview of the context file is the passages, which is the
  quickest look a coach gets — and the pass's line once it has ended; the pill's x removes both files.
- **S2 — Citations.** `[C.417]` in the Answer and the Simplified view is the documents' chip: hover shows *2026-08-14
  · activity_message · the subject · "Legs were heavy from the first climb…" (rendered from Danish:
  "Benene var tunge fra den første stigning…")*; click opens the Investigation tab at
  the READ digest or the cell that printed it. The Investigation tab's READ card lists the digest as for documents.
  A passage named by its bare id - *C.39 - written 4 August* - is a chip too, where the id resolves: the first live run
  (2026-10-14) named every passage so and cited cells beside; the host resolves the report's ids at report time and
  sends the passages to the page, so a chip has its hover even when a cell, not a READ, read the passage. The report
  guard reads a bare id the same way - evidence where it resolves, nothing otherwise - and discloses only a
  bracketed id that does not resolve, so a stray "C.3" in prose is never a finding.
- **S3 — The codebook.** Settings → *Context codebook*: the codes by group with definition, status and the last
  load's counts; proposals at the top with the passages they came from (quoted), *Confirm* / *Rename or merge
  into…* / *Decline*; export and import as JSON. Read-only list and proposals first; editing definitions later.
- **S4 — Routines.** Nothing new: the run dialog's load carries context; the comparison table shows count lines
  the method prints; the Comparison tab says *no passages in this window* when so.

## 8. Storage

Executor side: the two files in the key's folder beside the summary, wellness and intervals files
(`datasets/<user>/<key mark>/context_notes_…csv`, `context_codes_…csv`), ephemeral as every file there; a
routine's run copies them into its own folder like the others. App side: `storage/<user>/context/codebook.json`,
files in both editions as the favourites and routines are; nothing in the database. Labels are not persisted (§12
D1). Sizes: a season's context is tens of kilobytes; the codebook a few.

## 9. Editions

The same in both. Context needs the executor, as the loaders do; `--compute local` has no Intervals.icu load and
so no context, as today. The stack's fake Intervals.icu (`tools/stack/fake_apis.py`) gains `/athlete/{id}`,
`/custom-item`, `/events`, `/activity/{id}/messages` and `/chats/{id}` with a calendar of messages in two
languages, a note, a sick span, a tagged activity, a custom select — the variation the design handles — and the
integrations walk loads it, codes it with the scripted model layer, cites a passage in a report, makes a routine
and runs it on the next window. The executor image gains the fetch (a build stamp bump: v53).

## 10. Retired by this feature

Nothing. The summary file's columns grow (§3.1); no existing column changes meaning.

## 11. Build order and acceptance

1. **The load and the table** — the executor's fetch (events, custom items, the subject's record, messages for
   activities with a chat), the kinds, HTML stripping, the plan's prose, the two `AUX_KINDS` entries, the summary's
   new columns, the job's result, the card; the DATA map; the Data tab's pills. *Accepted by:* the executor-kernel
   test and the integrations walk over the fake Intervals.icu (the counts per kind, the roles, the stripped HTML,
   the inclusive span, a window with no words); a live load on the two probed accounts whose counts match the
   probes (212 and ~260 passages for 120 days).
2. **`CTX` and READ CTX** — the prelude, the five calls, the Reader over passages, the citation chips with the
   verbatim guard; the contract's Context section as drafted in §5, joined with `Session(context=True)` (its trim
   and the reviewer's lens stay step 4). *Accepted by:* test_analyst (the session with a scripted reader; a cited passage verified; a
   bad one disclosed), test_app_path (the route and the chips), the stack walk (a question answered with a
   passage cited in both views), live on a probed account.
3. **The codebook and the coder** — the seed (§13), the seat in every tier, the pass at load in batches, the
   validation, the codes file, proposals stored, the dialog line's counts, the map's code line. *Accepted by:* pure tests
   of the validation (a code outside the book, a proposal, a quote not verbatim, a cut reply, a second batch);
   the fake model layer end to end; live: twenty labels of one window read against their passages by Palo, and
   twenty renderings against their originals — the first measure of the coder's precision, written down before
   anything is tuned (C6).
4. **The contract section and the reviewer's lens** — the two texts, the scanner over them, `Session(context=)`.
   *Built 2026-10-14 (patches 0154, 0155):* the section trimmed to 737 characters, the Words lens in the reviewer's brief
   with context only, the map's closing line reduced to the plan note's date (the rules it repeated live in the
   section). *Accepted by:* the scanner over both texts (in the battery); the field trial — the benchmark's
   `context_enabled` rows (patch 0153, rewritten by 0157 in the voice of the coach or the rider with no word of the
   system's — no codes, context, passages, renderings — so that the route is the system's to find, Palo's point of
   2026-10-15: a question that names the codes hands over the route and measures instruction-following, not
   whether the words are brought to bear; twelve questions, one per category, the three shapes among them — *in
   the weeks my 20-minute power jumped the most, what was I saying in the days before and after*, *on the days I
   said I was tired or sore, did my heart rate at a given power look any different*, *how often did he actually do
   the session I set him, and when he did not, did he tell me why* — each with a scoring key under it for the
   person, never shown to the model: use the words where needed, quote rather than paraphrase, a count of codes
   named as the model's reading, a window rather than a same-day match, what rests on what), run in Adaptive mode
   so that the reviewer's Words line is present; the first run is pending. The same standard holds for the
   questions in the testing notes: the verification items stay technical (they are for the person checking the
   build), the questions put to the model do not name the system's parts — the mirror of C5 on the asking side.
5. **Routines carry context** — the aux kinds bound, the run's load with the coder, the comparison. *Built
   2026-10-14 (patch 0156):* most of it was already there by construction — the two kinds in `AUX_KINDS` (1b), the
   run dialog waiting for the pass (0149), the kernel prelude binding `CTX` to the run's load, `bind_script`
   rebinding a literal context or codes path by kind. What was missing: the run's plan dropped `context` from the
   kinds a load is asked for (`load_plan` kept only summary, wellness, intervals), so a routine's run never loaded
   the words; the cache was satisfied by a cached context file without the codes beside it; and a window without
   words read as "the context file is empty (0 rows); codes absent". Now: the plan keeps `context` (never `codes`
   - the pass writes them); `cache_match` wants the codes file beside a cached context file, unless that file is
   its header alone (a window without words, no pass, no codes - told by its size); the CHECK row says *no
   passages in this window (the context and codes tables are empty)* and does not call the codes absent there.
   The run's record keeps the binding's facts (the codes file absent in that load) under the sentence. *Accepted
   by:* unit tests (the plan, the cache, the sentences); the integrations walk - a chain counting a code on the
   rider's own passages (one cell over `CTX.frame()` and `CTX.codes()`, two RESULT lines) made a routine with no
   inputs; run on the next window, the load asking for the context, the pass behind it waited for, the context
   and codes files bound with their rows against the original's, the count the fake calendar predicts, compared
   with run 0; run on the fake's silent fortnight (`apis_data.is_silent`: nothing written for fourteen days),
   the context file its header, no codes file, zeros printed, the sentence on the CHECK row, the Context pill
   for the window with no coding line. Live: pending (D9 is moot until a run carries a narrative - the record's
   `narrative` field is empty by construction today).
6. **The codebook screen** — S3. *Accepted by:* the markup tests, the screens tool, a proposal confirmed live and
   used by the next load.
7. **The joint display** — no code until the field trial shows the analyst cannot draw one with what it has (C6);
   the trial's third question is the test.

## 12. Open decisions

- **D1 — Persisting labels.** Decided the other way on 2026-10-14, after the first live pass took seven minutes:
  the coded passages are kept per user and subject in `storage/<user>/context/<athlete id>/coded.json` — the id
  Intervals.icu reports for the key's athlete, so a regenerated key keeps the store and a coach switching athletes
  never meets another athlete's (the entries are keyed by kind and source id with the text's hash as the guard,
  which on its own already keeps one athlete's words from standing in for another's) — each entry carrying its rendering, codes, coder and
  codebook version; a load codes only the passages the store has not seen (a changed text is coded again), so the
  full pass happens once per subject. The codebook's version makes old labels comparable; the store is bounded
  (the newest 6,000 by day). Nothing else persists.
- **D2 — Scope of the codebook.** Per user, seeded from one list. A shared seed across users keeps cross-coach
  comparison possible; per-coach growth keeps each coach's practice. Decided: per user, seeded; revisit if a team
  of coaches wants one book.
- **D3 — Chats beyond the activity.** The private chat with the coach and the team's group chat are reachable
  (`/athlete/{id}/chats`); both probes showed them dormant or noisy (system notices, many members). Not in v0.1;
  `chat_message` is the kind reserved for them, with the chat's name on the row.
- **D4 — The default window.** `days=3` in `CTX.around`; the analyst chooses; the map says the days can differ.
- **D5 — Private entries under a coach's key.** `hide_from_athlete` events and private wellness keys come through
  a coach's key; they are the coach's own writing and are included with `private` true; the report may quote them.
  Unverified until a coach's key is probed.
- **D6 — Tone.** Kept as one axis per passage, cheap and useful for the joint display; dropped if the live
  precision check shows it noisy.
- **D7 — The plan's prose.** Step lines (`-10m 220w`, `2x -10s CZSS`) are recognised by shape and removed; what
  remains is the prose. If a coach writes everything as steps, the plan note is empty and the structure is in
  `workout_doc` for a later step.
- **D8 — A coach's standing note.** The seed's rules as user content the analyst reads (a per-user note in DATA).
  Not in v0.1 (C6, C7); the question is whether the field trial shows the analyst needs it.
- **D9 — What a routine's narrative may say.** The seed's constraints belong here if anywhere: the Rewriter's
  note on a run reports a divergence and never recommends a change. A product rule for step 5 — moot as built
  (2026-10-14): a run's comparison is sentences the host writes from the numbers, no model writes a narrative on a
  run (the record's `narrative` field is empty); the rule applies the day one does.
- **D10 — Languages. Decided (Palo, 2026-10-13): everything the model writes is English** — codes, definitions,
  proposals, the map, the digests, the report, whatever the question's language. A passage not in English is
  rendered into English once, at load, by the coder (`text_en`); the analyst reads and greps the rendering, the
  Reader and the report quote it marked *rendered*, the original stays on the row and on hover; the code's `quote`
  stays in the original so it can be checked verbatim. The coder's seat must read Danish, Norwegian and English
  well — the precision check in step 3 is per language and includes the renderings.
- **D11 — Two subjects in a thread.** `C` is one context per load; a thread with two subjects' loads is not a case
  today. If it becomes one, the locator gains a subject letter.
- **D13 — A document as context.** A diary export, a debrief transcript or a questionnaire file is dated writing
  about the subject and could be parsed into passages (date, author, text) and coded like the Intervals.icu
  words. Not in v0.1: documents stay documents. If a coach asks for it, the parse is the only new piece — the
  table, the coder and the map exist.
- **D14 — English for documents.** D10 applies to what the model writes; a document passage the Reader quotes is
  the document's own words and today is quoted as written, in its language. The consistent rule — render a
  non-English document's units into English at upload, as the context passages are at load — needs `text_en` on
  the documents' units and the guard checking against it. A later step, if a non-English document is uploaded in
  practice.
- **D12 — The summary's `description` column.** Added for the join; a subject who writes long descriptions puts
  text into the frame's head in DATA. The head is cut at the existing limit; the passage is in the context table.

## 13. The seed codebook (v1)

English codes, one line each; the coder reads the definition, the coach sees it on the codebook page. Groups are
for the page and the joint display's rows; the code alone is what a label carries. The seed ships as a data file
(`analyst/codebook_seed.json`), copied into the user's codebook on first use: data the coder receives, like a
column name, not a prompt — the C5 scanner covers the coder's template and leaves the file alone, as it leaves
`model_properties`.

**Body and health** — `fatigue` tired, heavy, flat, no energy, needing rest · `freshness` fresh, light, strong,
recovered · `soreness` muscle soreness, stiffness, aches without a named injury · `injury` a named injury or pain
that limits · `illness` sick, cold, fever, stomach, cold sore, feeling off · `sleep` how the night went, duration,
waking · `nutrition` eating, fuelling, hunger, carbohydrates, bonking · `hydration` drinking, thirst, dehydration ·
`body` weight, heat, cramps, gut, cycle, breathing · `recovery` rest taken or needed, a day off, recovering.

**Mind** — `mood` upbeat, down, flat, irritable · `motivation` wanting to or not · `stress` pressure, worry,
tension from life · `confidence` belief or doubt in oneself · `focus` concentration, mental fatigue, distraction ·
`nerves` anxiety before an event · `enjoyment` fun, boring, grind.

**The session** — `execution` done as planned, targets hit or missed · `deviation` the plan changed, cut, extended
and why · `effort` how hard it felt against what was expected · `pacing` too hard or too easy early, fading ·
`technique` form, position, skill · `equipment` mechanical, device, bike, trainer, data missing · `conditions`
weather, heat, wind, road, altitude · `company` group, teammates, alone · `logistics` time, travel, schedule, a
clash with work or study · `test` a test or measurement reported.

**Performance** — `good_day` felt strong, a breakthrough · `bad_day` nothing there, weak, worse than usual.

**The exchange** — `question` something asked of the coach · `instruction` the coach's direction for a session
or a day · `feedback` the coach's judgement or encouragement · `plan_change` an agreed change to the plan.

**Life** — `work_study` · `family_social` · `travel`.

Thirty-six codes. No `other`: a passage that fits none carries none, and the uncoded are counted in the map. A
proposal must say what no existing code covers.
