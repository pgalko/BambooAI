# Datasets by athlete — design v1.5 (2026-10-29; v1.0 agreed the same day; steps 1-3 built in patches 0237-0241, the dialog redesigned in 0242)

The Dataset cache lists files: one per load, per feed, per window, named by feed and dates, with the athlete nowhere.
Every load adds files and nothing merges, so a coach who works with two athletes, or with one athlete over a growing
window, soon cannot find anything and stops using it. This design replaces the list with a tree — **source → athlete →
feed → span** — backed by one store per athlete, so that a window asked twice is one entry, a window that grows is
one entry whose span grew, and two athletes never share a line. The four decisions behind it were taken on
2026-10-29 (section 11); the next phase, several API keys per coach and an athlete dropdown in the load dialogs, is
the same tree without the data. **Status**: steps 1-3 of section 10 are built (patches 0237-0241, executor images
v67-v71; sections 13-15 say what they did and where they differ from the text), and the dialog was redesigned after the
product owner's second look (patch 0242, image v72; section 16 is the design as it stands); step 4 is not.

## 1. The shape

```
Intervals.icu
   Athlete A (name · i12345)
      Activities (streams)   2025-10-28 → 2026-10-26   101 activities · 60 MB · last used 3 days ago
      Laps                   2026-01-01 → 2026-06-01
      Wellness               2025-10-28 → 2026-10-26
      Calendar               2025-10-28 → 2026-11-30   (planned sessions reach into the future)
      Notes & codes          2025-10-28 → 2026-10-26   1,204 passages · 912 coded
      Profile · zones        as of 2026-10-26
   Athlete B …
Endura
   Athlete C (name · e9981)
      Race: Tour of X, stage 3   2026-09-14
Uploads        titanic.csv · F1 … · EEDR …          as today, by file
Generated      by chain                              as today
```

Each feed line carries its span (the days held, with gaps shown as segments when there are any), a size, when it
was last used, and three actions: **Use** (opens the load dialog, or the routine's run dialog, with the athlete, the
feeds and the span filled in), **Extend to today** (fetches only the missing days), **Forget** (the feed, or at the
athlete's line the whole athlete). Uploads keep their file list and actions; generated files stay by chain.

A feed's leaf is a span for Intervals.icu and an event for Endura (a race is the unit there); the tree holds either.

## 2. Identity: the athlete, not the key

Today a load is identified by a hash of the API key (the *mark*): it names the folder on the executor, tags every
cached frame and window file, and a routine compares it with the key in use. Every call goes to `/athlete/0`, the
key's own athlete, so one key is one athlete — but an athlete who rotates the key becomes a second folder, and a
coach whose key may one day read several athletes (`/athlete/{id}`) would have them all under one mark.

From now on the athlete is identified by **the source's athlete id** (Intervals returns it with the profile, with the
name; Endura its user id), and the key is a credential:

- the folder on the executor is `datasets/<user>/<source>/<athlete id>/`, with the athlete's record beside the files
  (`subject.json`: source, id, name, the marks of the keys that have loaded this athlete, first seen, last load);
- the display name comes from the profile feed when the tree is drawn; it is not written into folder names;
- the mark stays as what it was meant to be: a one-way fingerprint a routine checks to say *the same credential is in
  use*; it no longer names anything;
- a load learns the athlete id from the profile call it already makes, before it writes anything.

## 3. The store, per feed

The activity store exists (docs/INCREMENTAL_LOADS_DESIGN.md): activities by id, every metric, a window assembled
from it, only the missing activities fetched. The other feeds join it under the athlete's folder, each kept by what it
is rather than by window:

| feed | kept as | key | notes |
|---|---|---|---|
| Activities (streams) | as today | activity id | the primary frame of a load is a view of this |
| Laps (`intervals`) | one file per activity | activity id | fetched each load today; the activity's signature serves it from the store, as the streams |
| Wellness | one table, a row per day | day | the window's days are re-fetched each load (one small call) and merged: a day can change, a span never shrinks |
| Calendar / planned sessions | one table, a row per event | event id | re-fetched for the window and merged, as wellness |
| Notes (context) | one table, a row per passage | passage id | re-fetched for the window and merged; the coded passages (today `storage/<user>/context/<mark>/coded.json` in the app) move to the same athlete key |
| Codes | the coded passages' table | passage id | written by the coding pass, as today |
| Profile · zones | dated snapshots | day fetched | the newest is the one a load uses; older ones are kept for the record |
| Messages | as today | activity id | |

Each table is a parquet file (pickle where there is no engine, as the activity store does), with a small manifest:
the span held per feed, when each day or id was fetched and last used, the engine. "Fetched fresh every load" stays
true for the small feeds — the window's days come down again each load, which is what keeps a corrected weight or a
moved session right — but what comes down is merged into the store instead of overwriting a file, so the span is the
union of every load.

## 4. A window is a view; the files follow the run

What the analyst reads does not change: the window files (`wellness_data_<from>_to_<to>.csv` and the rest) are still
written when a load or a routine run starts, at the paths the prompt names, with the same columns. What changes is
their standing: they are **a run's inputs**, written from the store, shown on that run's Data tab and in a routine's
run record — and listed nowhere in the cache. They live under the athlete's folder in a `views/` subfolder, one file
per feed and window, and are cleaned by age unless a favourite or a routine's run refers to them (the cleanup that
keeps favourites' datasets today extends to them). The same window asked twice writes the same file once.

The cache therefore answers *what do I have, for whom*; a run answers *what did this analysis use*.

## 5. Loads and routines

- **A load** (the Intervals dialog, today one key per user) names the athlete by its connection, asks for feeds and a
  window; the executor assembles the window from the store, fetches only what is missing, writes the views, caches
  the frame. The completion line says what came from the store and what was downloaded, as today.
- **A routine** records the connection it was made with — source and athlete id, beside the key fingerprint and the
  window rule — and resolves its window against that athlete's store at run time. `cache_match` becomes "what does
  the store lack for this window", which is what the activity store already computes.
- **Next phase**: the coach's list of connections (source, athlete id, name, key), kept per user where the single key
  is kept today; the Intervals dialog and the routine run dialog offer a dropdown of that source's athletes; a
  routine made for one athlete can be run for another by choosing them. The tree already has the athlete level, so
  nothing in the cache changes for this.

## 6. The run's record and the code map

`run.data` carries the connection — `athlete: {source, id, name}` — so the code map's *Data this chain used* and the
report's data line can say whose data a chain ran on. The name is the one the profile gave at load time; the record
lives in the coach's own storage, as the question and the report do.

## 7. Retention, per athlete

One rule per athlete store, across feeds: an item (activity, day, passage, snapshot) not used by a load within
`USED_DAYS` (30) leaves when older than `RETENTION_DAYS` (400); a routine over an old window keeps its data as long as
it runs. The numbers are the activity store's today and stay. A free tier's shorter span applies per athlete. The
athlete line shows *held since · last used*, and **Forget** removes the athlete's folder whole. Views follow their
runs (section 4), not this rule.

## 8. The route and the modal

`/cache/inspect` returns the tree:

```
sources: [{source, athletes: [{id, name, held_since, last_used, size_mb,
            feeds: [{feed, span: [[from, to], …] | event, count, size_mb, last_used}]}]}]
uploads: [...]        # today's primary and auxiliary files that belong to no athlete, as today
generated: [...]      # as today
frames: [...]         # the cached frames, each with its athlete and window, for the Use action
```

The modal (`dataset-manager.js`) draws the tree collapsed to athletes, a filter box above it (a name or a feed),
the actions of section 1 on each line. Nothing else in the page changes; the Data tab's pills, the routine dialogs
and the file pickers keep their routes.

## 9. Migration

On the first load after the upgrade with a given key, the executor learns the athlete id and moves `<mark>/store/`
and the key's view files under `<source>/<athlete id>/` (the mark folder renamed when the athlete's folder does not
exist yet; absorbed into it otherwise - files kept when absent, store entries the athlete's store lacks, then the mark
folder goes), and records the mark in the athlete's record (`subject.json`, the marks that have loaded this athlete,
so a routine's fingerprint check and an old run's record still resolve). The app's coded passages already live by
athlete id (`context/<athlete id>/coded.json`, since 2026-10-14). Nothing is downloaded again. A folder whose key
never loads again is left where it is and listed as it was (its mark, *key …xxxx*) until forgotten or cleaned by age.

## 10. Build order

Each step leaves the app working; the image is rebuilt where the executor changes.

1. **Identity and the folder** — the athlete id from the profile, the folder by source and athlete, the migration,
   the athlete's record; routines record the connection; the run's record carries it. *Executor image.* **Built
   (0237, v67; section 13).**
2. **The feeds into the store** — wellness, calendar, notes, codes, profile and zones kept by day, id or snapshot and
   merged; laps served by signature; views written from the store under `views/`. *Executor image.* **Built (0238,
   v68; section 14).**
3. **The tree** — the route's new shape, the modal redrawn, the actions, the per-athlete retention. The cache stops
   listing view files. **Built (0239, v69; rebuilt after the first look in 0240, v70; section 15).**
4. **Connections** (next phase) — the list per user, the dropdowns, a routine run for another athlete.

The e2e walk gains a chain per step on the stack's fake Intervals.icu (two athletes, a window that grows, a key that
rotates); the unit suites cover the store's merge and span, the migration, the tree, the routine's resolution.

## 11. Decisions taken (the product owner, 2026-10-29)

1. **Athlete id, not the key.** The source's athlete id names the store; the key is a credential with a fingerprint.
2. **Views are a run's inputs.** The per-run window files are listed nowhere in the cache; the run and the routine
   show them.
3. **Retention per athlete**, one rule across feeds; the numbers stay.
4. **The primary frame is a feed of the athlete.** No PRIMARY / AUXILIARY split; the streams are *Activities* under
   the athlete. Uploads and generated files keep their own groups.
5. **Source at the top.** Intervals.icu, Endura, Uploads, Generated; an athlete sits under a source, and the same
   person on two sources is two athletes until the coach links them (not in this design).
6. **Several keys per coach and the athlete dropdown are the next phase**, built on this tree.

## 12. Open, to decide when the steps are built

- Whether an Endura "athlete" is the Endura user, and whether a race belongs to one (section 1 assumes yes).
- How long a view file lives after its run (a month, as the store's used-days rule, is the natural default).
- Whether the tree shows the store's size per athlete on the hosted service (it is the coach's own disk on the single
  edition; on the hosted boxes it is a quota question).
- The name in `run.data` (section 6): on screen only, or in the record as proposed.

## 13. Step 1 as built (patch 0237, executor image v67)

What the executor does on every Intervals.icu load (`fetch_intervals_background`): it fetches the profile first
(`/athlete/0`, the call it made later for the profile file anyway), takes the athlete's id and name, names the folder
`intervals/<id>` under the user's (`athlete_rel`; a load whose profile gives no id falls back to the key's mark, as
before), adopts the key's mark folder if one exists (`adopt_mark_folder`), writes or updates the record
(`remember_athlete`), and only then loads: the store under that folder, the window's files beside it, the frame's
metadata with `subject` {source, id, name} and `folder`, the job's result with `subject`. `/cache/inspect` walks
the athlete folders (`athlete_folders`: `<source>/<id>` with its record, and any mark folder left) and returns
`subjects` (one per athlete: source, id, name, folder, marks, first seen, last load), each file's `folder` and
`subject` (`key_mark` only for a file still in a mark folder), and the stores with their `subject`.

The app: the load record carries `load.subject` (the Intervals route, from the result; the cached-frame load, from the
metadata), the routine's data record and each run's with it; the code map's *Data this chain used* names the
subject on the primary input; the run dialog's cache check resolves the key in use to its athlete by the records
(`subject_of_key`: the record whose marks include the key's mark) and matches frames by the athlete's id - a rotated
key is served its athlete's cached windows once it has loaded, a key that has not loaded yet is still *another key*,
a window held for another athlete only is said so (*loaded for another subject - it will be downloaded*); the Dataset
cache panel's store lines carry the athlete's name. Nothing else in the modal changes until step 3.

Words: on the app side and in every string a model could read, the athlete is *the subject* (the routines module's
C5 rule keeps domain words out of model-read strings); the executor's record file is `subject.json` for the same
reason. This document keeps *athlete*, as the product owner said it.

Tests: `tests/analyst/test_store.py` (the folder, the record, the listing, the migration's rename and absorb),
`tests/analyst/test_routines.py` (the match by subject), the integrations walk (the stack's fake Intervals.icu
answers another athlete to a key ending in `-two`: the folders, the records, *another key* before the key has loaded
and *another subject* after, the first athlete's window a hit again under its own key).

## 14. Step 2 as built (patch 0238, executor image v68)

The store under the athlete's folder now keeps, beside the streams and the chats:

- **the laps** under each activity (`store/laps/<id>.json.gz`, the API's answer as given, with the signature and the
  time on the activity's manifest entry), served from the store by the chat's rule - the activity older than sixty
  days and its file unchanged - and fetched again otherwise, because labels, RPE and lactate are typed in after the
  sync without the file changing; *Refresh everything* fetches them all. The load's result carries the laps' account
  (`store.laps`: window, held, fetched) and the dialog's completion line says *every lap from the store* or *laps: n
  of m from the store*;
- **the wellness log by day** and **the calendar by entry** (`store/wellness.json`, `store/events.json`: each record
  under its key with its day, when fetched and when last served). The window's days or entries come down each load
  (one call each) and are merged: what came down replaces the window's records - a day corrected at the source is
  corrected here, an entry deleted there goes here - and the rest stay, so the span held is the union of every
  load. The window's file is written from the store's window. A call that fails leaves what the store holds of the
  window to stand, said in the log and the context's report;
- **the profile as dated snapshots** (`store/profile/<day>.json`, the record as fetched, a new snapshot only when it
  changed, the day's own replaced); the profile and zones files are built from the record just fetched, as before.

The window's files - summary, wellness, laps, context (and the codes the app writes beside it), planned workouts,
profile, zone times - are written under the athlete's `views/` folder, the same window to the same file; files an
earlier executor left at the athlete's folder itself move under `views/` on the first load. `/cache/inspect` lists
them as before, each with the athlete's folder and subject (the tree of step 3 stops listing them); the store's
summary carries each feed's span and count and the profile's newest day. The retention rule runs across the feeds:
an activity older than the retention and unused leaves with its rows, chat and laps; so do such days and entries;
old snapshots leave but the newest. The migration of a mark folder takes the laps, the feeds and the snapshots too.

Where this differs from section 3: the **passages of the context are not kept as a table**. They are derived, at
each load, from records the store already keeps or the load fetches anyway - the chats (stored), the notes and tags
on the activities (the window's list), the wellness comments (stored by day), the calendar entries (stored by
entry) - so a passages table would be a second copy of the same words; the coded passages stay the app's, keyed by
athlete id. The summary file is built from the window's activity list, fetched each load as the manifest of what
Intervals holds; the list's entries are not stored either. The tree (step 3) therefore shows the feeds the store
holds - activities, laps, wellness, calendar, profile - and counts the passages from the newest context view.

Tests: `tests/analyst/test_store.py` (the laps served, re-fetched on a changed file, on a refresh and while recent;
the feeds merged with a correction and a deletion, their spans; the snapshots; the retention across the feeds; the
migration; the listing), `tests/analyst/test_dialogs.js` (the completion line), the integrations walk (the files
under `views/`, the prompts' paths).

## 15. Step 3 as built (patch 0239, executor image v69; rebuilt after the product owner's first look in 0240, v70)

`/cache/inspect` carries `tree` beside the flat lists (which stay: the routines' cache check reads a window's files
from `auxiliary_datasets`, each window file now marked `view`): `sources` (Intervals.icu with its athletes - id,
name, folder, held since, last load, size, the marks that loaded them - each with its datasets; Endura and
SweatStack with their frames, Endura with its race files); `uploads` (the frames and files that belong to no
loader); `legacy` (a mark folder from before the athlete was known that holds no activity of a known athlete). An
athlete's **datasets are named as the load dialog names them** - *Activities* (the streams the frame and the summary
are made from), *Activity intervals*, *Wellness*, *Calendar*, *Context · chats*, *Rider profile* - each with its
span (the profile its newest day), its count, its size, when it was last served and what it holds (the columns of
the activities and of the wellness log, the calendar's entries by category, the laps' and messages' counts). The
tree is composed by `cache_tree` in `intervals_store.py` from the lists the route already had.

The dialog (`dataset-manager.js`) draws it as the first look asked: an athlete's block that the caret folds and
unfolds; **a click on the athlete's line or on a dataset's line opens its details on the right**, where the actions
are, as the files' Load and Remove always were. The athlete's details carry the name and id, held since, the last
load, the size, how many keys have loaded them and the table of datasets held; a dataset's details its span, count,
size, last use, what a load writes from it (the file names) and its columns or categories. Every details pane
carries the same three actions - **Load**, **Load to today** and **Forget** (the athlete's or the dataset's):

- **Load** brings the span held onto the Data tab **from the store alone**: nothing is fetched. The executor
  (`from_store` on the request, the athlete's `folder`) makes the window from what the store holds - the activity
  list's entries it kept from every online load (`entries.json`, by id with the day), the files, the laps, the
  chats, the wellness log, the calendar, the newest profile, the coaches the record kept - with the datasets of the
  last load (the record's `kinds`). A span the store has no entries for (held from before the entries were kept)
  takes one call for the list, said on the completion line; a span whose files the store does not hold is refused
  with a sentence pointing to the Intervals.icu dialog. The completion line says *all n activities from the store,
  nothing fetched*.
- **Load to today** goes through Intervals.icu for the same span extended to today: the store serves what it holds,
  the missing days come down, the wellness log and the calendar are fetched afresh and merged, recent chats and laps
  looked at again - the load the Intervals.icu dialog would make for that window.
- A window loaded now is let go first, after asking, with its file pills; the job's progress shows in the pane; the
  dialog closes by itself; the Data tab shows the window and its pills as any load's.

Uploads and Generated keep their groups; the frames of Endura, SweatStack and uploads open the details with Load and
Remove as before. The filter box shows only with more than one athlete. No window file is listed, and nothing is
called *in memory*: an Intervals.icu window is a view of the store, assembled in seconds.

`/cache/forget` (the executor, proxied by the app) drops a dataset - the laps alone, a feed's records, the profile's
snapshots, the activities with their chats and laps - or the athlete's folder whole, and the athlete's frames in
memory with the activities or the folder; the page lets go of the Data tab's frame when it was one of them.

**Earlier loads.** A mark folder from before the athlete was known whose store holds an activity the athlete's
store holds too is the athlete's own earlier loads (an activity id is the platform's, one per activity): it is
absorbed into the athlete's folder at the end of the next online load (`absorb_mark_folders`), so nothing is listed
twice and nothing is downloaded again. A mark folder with nothing in common is another athlete's (or another
account's), loaded under a key that is not the one in use: it stays listed as *earlier loads · key …xxxx*, its
details saying so, with Forget; a load with that key files it under its athlete.

**Retention per athlete** was already the store's rule across the feeds (step 2); step 3 adds the views' age: a
window file not written within thirty days leaves at the end of the athlete's next load. Where this differs from
section 4: the age rule stands alone - a routine's run keeps its own copies of the files it ran on, and a favourite
keeps its results and its generated files, so neither refers to a window file after the load.

**A dataset that gave no file says why.** A load asked for a dataset that produced no file (the call failed, the
window has nothing of it) puts a sentence on the result (`warnings`), and the dialog's completion line reads *Not
written: …* and stays until the dialog is closed; a failed wellness or calendar call leaves what the store holds of
the window to stand and says so. The small calls - the profile, the activity list, the wellness log, the calendar -
wait out a rate limit (429, `Retry-After` honoured) or a passing server fault and try again, twice
(`get_with_retry`): a live load with every dataset had lost its wellness file right after a thousand calls for the
files, laps and chats.

Not in this step: Endura's athletes (an Endura load is one race under the user, as before), the *Extend* action for a
dataset that takes no window (the profile).

Tests: `tests/analyst/test_store.py` (the tree from the inspection and from made-up lists, with what each dataset
holds; forgetting a dataset, the activities and the athlete; the route's checks; the views' age; earlier loads
absorbed by a shared activity, on their own and in a load; the warnings), `tests/analyst/test_dialogs.js` (the
dialog's ids, lines, details, actions, names and styles), the integrations walk (the athlete's and a dataset's
details; Load from the dialog with a window loaded - let go on asking, loaded from the store, the dialog closing by
itself, each file's pill once; every dataset loaded together with all eight files written and seven pills; the tree
with two athletes, fold and filter, Forget through the details, Load to today declined).

## 16. The dialog redesigned (patch 0242, executor image v72)

The product owner's second look (2026-10-29) found the rebuilt dialog still an old design bent to the new logic: the
columns showed for two datasets only, Load on a dataset loaded everything, earlier loads were still listed. The
dialog was redesigned from mockups he approved; this section is the design as it stands and replaces the parts of
sections 1, 8 and 15 it contradicts.

**The lines are the dialog's datasets.** Under an athlete there is one line per dataset the Intervals.icu dialog
offers, plus the frame - *Activities* (the second-by-second files: the frame), *Activity summary* (the activity
list's entries, one row each), *Activity intervals* (the laps), *Wellness*, *Context* (the chats and the calendar
together, as the dialog has no calendar box; the planned workouts ride along), *Rider profile* (the settings and the
zone times) - each with its span, what is held, its size. `feeds_of` in `intervals_store.py` makes them from the
store's summary (`FEED_ORDER`, `LINE_FILES`). A **dot** in front of each line says whether that dataset is **on the
Data tab now** (filled) or in the store only (empty); the page reads it from the pills - an auxiliary pill's file
path names the athlete's folder and the file's prefix names the line (`PREFIX_FEED`); the frame's pill carries the
athlete's folder on its record (`dataInfo.folder`, from the job's `subject`).

**Every dataset shows its columns.** The details of a line carry what it is, what is held, whether it is on the
Data tab (with the window's file), the files a load writes from it and **their columns** - every dataset, not only
those whose records happen to carry keys. The executor supplies them on `/cache/inspect` (`dataset_columns`, by file
prefix, as `columns_of` on each store's summary): made the way a load makes the files - the summary over the activity
list's entries with the account's activity fields, the wellness file over the log's days (the day as `date`), the
laps file's fixed columns plus the account's interval fields under their codes; the context, plan, codes, profile
and zones files have fixed columns (`CODES_COLUMNS` on the executor mirrors `analyst/context.py`; the zones file only
when the account defines a custom zone set).

**Selective load.** A dataset's details carry **Load <dataset>** (the span held, from the store alone) and **Load
<dataset> to today** (through Intervals.icu, only the missing days come down); the athlete's carry **Load
everything** and **Load everything to today** (every dataset held). Loading Activities, or everything, loads the
frame: the frame on the Data tab is let go first, after asking, and the pills of the kinds loaded are replaced. Any
other dataset alone leaves the frame as it is and replaces its own pill(s) - `with_frame` off on the request: the
loader (`fetch_intervals_background`) downloads no file, assembles and caches nothing, writes only the files asked
for, and the result says `frame: false` with the `kinds` asked; the app's completion (`get_job_status`) then
replaces the session's files of those kinds (and what they bring: the codes with the context, the zones with the
profile) and keeps the rest - uploads, other kinds - adds the kinds to the load record, and starts the coding pass
when a context file came. The dialog polls such a job itself (`pollDatasetJob`); a frame load keeps the Intervals.icu
dialog's poller. The session's files are replaced **by kind** on every completion now, a whole load's too (they
were replaced wholesale, which dropped uploads).

**Forget is off the Data tab; Delete is off the disk.** **Forget <dataset>** takes the dataset's pill(s) off the
Data tab through the pills' own removers (the session's file list follows); **Forget everything** takes every pill
of the athlete off, the frame's too. The store keeps the data - Load brings it back - so there is no question. Forget
is greyed when the dataset is not on the tab. **Delete from the store…** is a quiet link on each pane that, after
asking, removes the dataset (or the athlete whole) from the executor's disk through `/cache/forget` - the datasets as
the lines: activities (the files alone; the laps and chats stay with their lines), laps, wellness, context (the chats
and the calendar), profile; no link on the summary (the activity list is the store's own, every load from the store
starts from it).

**Earlier loads are deleted, not shown.** On the executor's first start after the upgrade, `purge_earlier_loads`
deletes under every user's folder the folders of loads from before the athlete was known (a key's mark, or
*unmarked*) and the loader's window files an older executor wrote at the user's folder itself; uploads, the athletes'
folders and the app's own folders stay; the log says what went. The tree has no *legacy* block any more; a folder
that is no athlete's (a load whose profile call failed) is not listed. `absorb_mark_folders` stays for that one case.

Tests: `tests/analyst/test_store.py` (the six lines with their files and columns, the columns checked against the
files a load wrote and the app's codes columns; a load of one dataset alone from the store and to today; the context
alone; deleting the context and the activities; the purge), `tests/analyst/test_dialogs.js` (the actions, the dots,
the names, the styles), the integrations walk (earlier loads gone at start with the upload kept; the athlete's and
three datasets' details with their dots and columns; the tree with two athletes and the dots; Delete of the other
athlete; Load everything from the store; Forget Wellness; Load Wellness alone from the store; Load Activity intervals
to today alone; Forget everything; Delete Wellness from the store).
