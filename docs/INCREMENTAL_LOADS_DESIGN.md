# Incremental loads: the Intervals.icu store

*2026-10-15, v1.0. Built in patches 0161 (the store in the executor, image v55), 0162 (persistence and the page),
0163 (the walk's proof). Companion to docs/ROUTINES_DESIGN.md (F2, the Dataset cache) and docs/CONTEXT_DESIGN.md
(§3.1, the passages).*

## 1. The problem

A load from Intervals.icu downloaded the window whole, every time. The Dataset cache (ROUTINES_DESIGN F2) spared a
run only when its window matched a cached load exactly or sat inside one; a window a day wider, a week later, or asked
by the Data tab after a routine had loaded it, fetched everything again - for a year of second-by-second data, a
gigabyte and some minutes, the files of activities already parsed a dozen times. Palo's first live routine over
the words (2026-10-15) ran into it from the other side: two dialogs took "today" from the UTC clock and asked for
windows a day apart (fixed in 0158), and the cache could not serve one from the other.

The decision (Palo, 2026-10-15): *the platform is smart enough to merge different windows if possible* - the cache
is checked on every load, standard or by a routine, and only the missing bits are downloaded; a person who works
with a small window to keep the compute down still gets a small window.

## 2. The design

**Incrementality lives in the loader, in the executor.** The Data tab's load and a routine's run both ask the
executor for a window (`/fetch_intervals_data`); the executor is where the files are fetched and parsed and where
the frame is cached, so that is where a window is assembled from what is already held. Nothing changes in how the
app asks, in what the frame looks like, or in the Dataset cache above it - a cached window is still a hit, a window
inside one is still cut; what changes is the cost of a miss.

**The store holds activities, not windows.** Under the key's folder on the executor's disk,
`datasets/<user>/<mark>/store/`:

- `activities.json` - the manifest: for each activity id, the signature of its file, the day it started, the file's
  path, its row count and columns, when it was fetched, when a load last served it, and the same for its chat;
- `activities/<id>.parquet` - the activity's second-by-second rows, **every metric the file had** (not the metrics
  one load asked for), zstd-compressed - a year is 60-120 MB where its CSV would be a gigabyte; where pandas has no
  parquet engine (the test sandbox) the same frame goes to `<id>.pkl.gz`;
- `messages/<id>.json` - the chat under the activity, as the API returned it.

**A window is a view.** Each load fetches the window's activity list (one call; it is the manifest of what Intervals
holds now) and, for each activity with a file, asks the store: *is this activity here under this signature?* The
signature is a hash of the list entry's fields that change when the file does - `icu_sync_date`, `file_type`,
`start_date_local`, `elapsed_time`, `moving_time`, `distance` - so a re-synced, re-uploaded or corrected activity is
fetched again and a renamed one is not. The activities held are taken from the store; the rest are downloaded (five
at a time), parsed in parallel with every metric, and kept as they are parsed. The frame is then assembled from the
store for the whole window - the rows of each activity, the type and name as the list has them now, the columns cut
to the metrics asked - and sorted newest first, which is what the loader built before, from the same parse. A load
asking for other metrics over the same window downloads nothing.

**What is fetched fresh every load**: the activity list, the wellness log, the calendar, the subject's record - one
call each, small, and the source of the summary and wellness files and most of the passages. **The chat under an
activity** is fetched again while the activity is recent (started within `MESSAGES_FRESH_DAYS` = 60 days; a chat is
still being written) or when its file changed (a re-sync is a reason to look again), and taken from the store for an
older, unchanged one. **Refresh everything** (the request's `refresh`) fetches every file and every chat of the window
again, for the person who knows something changed that the signature does not see (a message added under an old
activity, say).

**Retention.** When a load ends, activities started more than `RETENTION_DAYS` = 400 days ago leave the store
(rows and chat) unless a load served them within `USED_DAYS` = 30 days - a routine over an old window keeps its data
as long as it runs; a one-off look at an old year is gone a month later. The app can pass `retention_days` with the
request (a free tier's shorter span). The startup cleanup does not touch the store (it clears the app's own datasets
folder and skips every subfolder).

**Tier limits** stay on the window asked, as before: the store makes a load cheaper, not larger.

**Only Intervals.icu.** SweatStack's loader is unchanged (later, if its volumes ask for it); Endura loads one race
and needs nothing.

**The laps file** (the `intervals` auxiliary dataset, one call per activity) is still fetched each load it is asked
for; the same signature would serve it from the store, a later patch.

## 3. Where the store lives, and how it persists

The executor's working folder, `/app/datasets` in the image, under the user's folder and the key's mark - beside the
window's CSV files, which are still written per load (the summary, wellness, laps, context and codes files are the
method's inputs and the Data tab's pills; they are small).

- **Single edition** (`bambooai serve`, patch 0162): the container is recreated whenever the image changes, and
  until 0162 ran with no volume, so the store would have gone with every executor update. `serve` now mounts a
  named Docker volume, `bambooai-datasets`, at `/app/datasets` - persistent across restarts and image rebuilds, owned
  by the image's `appuser` on every platform (a folder of the home mounted instead would need its ownership changed
  on Linux, where the host user's id and the container's differ). `BAMBOO_EXECUTOR_DATASETS=<folder>` in the
  working folder's `.env` mounts that folder instead, for a person who wants the files where they can see them.
- **Hosted edition**: the executor is a Nomad dispatch; persistence is the job template's volume, outside this
  repository (HANDOVER notes it for the roll-out). Without one the store lives as long as the container does and is
  simply rebuilt on the first load after.
- **`--compute local`** runs no integrations, so no store.

## 4. What the person sees (patch 0162)

- The loader's progress, as it runs: *The store holds 91 of 101 activities; downloading 10...*, or *The store holds
  all 101 activities of this window; nothing to download*, then *Assembling the window from the store...*; the
  messages step counts the chats taken from the store.
- The load's result carries `store` (`window`, `held`, `fetched`, `refresh`, and the store's `summary` - activities,
  chats, span, size, engine); the Data tab's completion line says *91 of 101 activities from the store, 10 downloaded*.
- The Intervals dialog and the routine run dialog offer *Refresh everything* (off by default).
- `/cache/inspect` lists the stores (`stores`: one per key with a store, by mark); the Dataset cache panel shows
  what each key's store holds.

## 5. Decisions

- **D1 The executor, not the app.** The app has no files; the executor has the parse, the frame cache and the disk.
  A store in the app would mean shipping gigabytes back and forth.
- **D2 By activity, every metric.** A window is a selection of activities; storing by window would keep overlapping
  copies and serve nothing wider. Keeping every metric means a different metric selection is served from the store.
- **D3 The signature from the list entry, not the file.** The list is fetched anyway; a download to find out whether
  a download is needed defeats the purpose. `icu_sync_date` is the field Intervals changes on a re-sync; the others
  guard the cases where it is absent (the fake calendar carries none, and its signature is still stable).
- **D4 Chats settle at sixty days.** A chat under a recent activity is still being written; under an old one, almost
  never. Refresh everything covers the rest.
- **D5 Retention by the activity's day, with the in-use exemption.** By day alone, a routine over an old window would
  re-download it every run that followed a load of a recent one; by use alone, the store would hold every year
  anyone ever looked at.
- **D6 Last writer wins on the manifest.** Two loads under the same key at once (the Data tab and a routine) each
  read the manifest when they start and write it when they end; an entry one wrote and the other did not see costs
  a download next time, never a wrong frame (the files are written whole and replaced atomically).
- **D7 Parquet, with a fallback.** The image pins pyarrow; the sandbox has none and stubs it, so the store writes
  compressed pickles there and says `engine: pickle` in its summary. The walk proves the same code path.
- **D8 A named volume for the single edition** (over a folder of the home) - §3.

## 6. Tests

`tests/analyst/test_store.py` (37): the store's pieces (signatures, put/has/get, the manifest's persistence,
assembly's order, columns, names and misses, the chat's freshness and its boundary, retention with the in-use
exemption, the summary and the listing) and the executor's loader end to end over the stack's fake calendar with a
fake session - a first load fetches every file; a wider second load only the ten new ones and the settled chats
from the store; the same window with other metrics nothing; a re-synced activity alone, its chat with it; a refresh
everything; the frame from the store equal to a straight parse; the progress lines; `/cache/inspect`; the error when
nothing can be fetched. `tests/analyst/test_context.py` (33) still covers the context builder; the stamp check reads
v55. The e2e integrations walk (86) proves the same against the real executor process over the fake API's call
log: the first load fetches the 60-day window whole; the routine's run on the window ending today (19 days of
overlap) fetches 41 files and its LOAD row says *19 of 60 activities from the store, 41 downloaded*; a second key
gets a store of its own; the original window loaded again with the context fetches no file and each chat once; the
same window in a new thread fetches no chat; Refresh everything fetches all 60 files and every chat; the Dataset
cache panel lists both stores.
