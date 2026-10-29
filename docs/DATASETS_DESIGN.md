# Datasets by athlete — design v1.2 (2026-10-29; v1.0 agreed the same day, step 1 built in patch 0237, step 2 in 0238)

The Dataset cache lists files: one per load, per feed, per window, named by feed and dates, with the athlete nowhere.
Every load adds files and nothing merges, so a coach who works with two athletes, or with one athlete over a growing
window, soon cannot find anything and stops using it. This design replaces the list with a tree — **source → athlete →
feed → span** — backed by one store per athlete, so that a window asked twice is one entry, a window that grows is
one entry whose span grew, and two athletes never share a line. The four decisions behind it were taken on
2026-10-29 (section 11); the next phase, several API keys per coach and an athlete dropdown in the load dialogs, is
the same tree without the data. **Status**: steps 1 and 2 of section 10 are built (patches 0237 and 0238, executor
images v67 and v68; sections 13 and 14 say what they did and where they differ from the text); steps 3-4 are not.

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
   listing view files.
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
