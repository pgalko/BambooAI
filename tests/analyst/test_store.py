"""The Intervals.icu store (docs/INCREMENTAL_LOADS_DESIGN.md, 2026-10-15): what a load fetched, kept by activity under
the key's folder, so a window is a view - the loader takes from the store every activity whose file has not changed,
downloads only the rest, and reuses the settled chats. The store's pieces over small frames, then the executor's
loader end to end over the stack's fake calendar with a fake session: a first load fetches every file, a wider
second load only the new ones, a third nothing; a changed file is fetched again; a refresh fetches all.

    python3 tests/analyst/test_store.py
"""
import gzip
import os
import sys
import tempfile
import time
from datetime import date, datetime, timedelta, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.normpath(os.path.join(HERE, "..", ".."))
sys.path[:0] = [HERE, ROOT, os.path.join(ROOT, "delve"), os.path.join(ROOT, "containers", "executor"), os.path.join(ROOT, "tools", "stack"), os.path.join(ROOT, "tools", "stack", "fakepkgs")]
import _stubs  # noqa: E402,F401
import pandas as pd  # noqa: E402

results = []


def check(name, cond, detail=""):
    results.append((name, bool(cond)))
    print(("  ok   " if cond else "  FAIL ") + name + ("" if cond else f"  <- {str(detail)[:600]}"))


WORK = tempfile.mkdtemp(prefix="bamboo_store_")
os.chdir(WORK)
import intervals_store as S  # noqa: E402
import code_executor_api as E  # noqa: E402
import apis_data as D  # noqa: E402
from fit_writer import write_activity  # noqa: E402

TODAY = date.today()


def day_str(d, hour=9):
    return f"{d.isoformat()}T{hour:02d}:00:00"


def entry(aid, d, **extra):
    e = {"id": aid, "name": f"Ride {d}", "type": "Ride", "start_date_local": day_str(d), "elapsed_time": 3600, "moving_time": 3500,
         "distance": 30000.0, "file_type": "fit", "icu_sync_date": "2026-10-01T00:00:00Z"}
    e.update(extra)
    return e


def frame(aid, d, n=5, power=True):
    t0 = datetime(d.year, d.month, d.day, 7, 0, 0)
    rows = [{"activity_id": aid, "datetime": t0 + timedelta(seconds=i), "heart_rate": 120 + i, "speed": 7.5, "distance": 7.5 * i,
             "activity_type": "Ride", "activity_name": "old name"} for i in range(n)]
    if power:
        for i, r in enumerate(rows):
            r["power"] = 200 + i
    return pd.DataFrame(rows)


# ---- the store's pieces -------------------------------------------------------------------------------------------
print("-- the store's pieces")
a, b = entry(1, TODAY - timedelta(days=10)), entry(2, TODAY - timedelta(days=12), type="Run", name="Run")
check("signature: the same entry gives the same signature; a rename does not change it; a re-synced file does",
      S.signature_of(a) == S.signature_of(dict(a)) and S.signature_of(dict(a, name="other")) == S.signature_of(a)
      and S.signature_of(dict(a, icu_sync_date="2026-10-09T00:00:00Z")) != S.signature_of(a) and S.signature_of(dict(a, elapsed_time=3601)) != S.signature_of(a))
check("signature: an entry without the fields still has one (the fake calendar's entries carry no icu_sync_date)", len(S.signature_of({"id": 5})) == 16 and S.signature_of({"id": 5}) == S.signature_of({"id": 6}))

st = S.Store(os.path.join(WORK, "datasets", "u"), "mark1")
check("has_detail: nothing is held before anything is put", not st.has_detail(a) and st.get_detail(1) is None and st.summary()["activities"] == 0)
p = st.put_detail(a, frame(1, TODAY - timedelta(days=10)))
st.put_detail(b, frame(2, TODAY - timedelta(days=12), power=False))
check("put_detail: the file lands under <user>/<mark>/store/activities/<id>.<ext>, by the engine present (parquet in the image, a compressed pickle without pyarrow)",
      p == os.path.join(st.activities_dir, "1." + ("parquet" if S.HAVE_PARQUET else "pkl.gz")) and os.path.isfile(p), p)
check("has_detail: held under the same signature; not under a changed one; a rename still held",
      st.has_detail(a) and st.has_detail(dict(a, name="renamed")) and not st.has_detail(dict(a, icu_sync_date="2026-10-09T00:00:00Z")))
got = st.get_detail(1)
check("get_detail: the rows come back as put (datetime, every metric)", got is not None and len(got) == 5 and list(got.power) == [200, 201, 202, 203, 204] and str(got.datetime.dtype).startswith("datetime64"), got)
st.save()
st2 = S.Store(os.path.join(WORK, "datasets", "u"), "mark1")
check("the manifest persists: a new Store over the folder holds the two", st2.has_detail(a) and st2.has_detail(b) and st2.summary()["activities"] == 2 and st2.summary()["from"] == (TODAY - timedelta(days=12)).isoformat())

df, missing = st2.assemble([dict(a, name="Renamed ride"), b, entry(3, TODAY)], selected_metrics=["power", "heart_rate"])
check("assemble: the window's rows in datetime order, newest first, the ids the store lacks reported",
      len(df) == 10 and df.datetime.is_monotonic_decreasing and missing == ["3"] and set(df.activity_id) == {1, 2}, (len(df), missing))
check("assemble: the columns cut to the metrics asked, with the activity's id, time, type and name kept; type and name as the list has them now",
      set(df.columns) == {"activity_id", "datetime", "power", "heart_rate", "activity_type", "activity_name"}
      and set(df[df.activity_id == 1].activity_name) == {"Renamed ride"} and set(df[df.activity_id == 2].activity_type) == {"Run"}, list(df.columns))
check("assemble: a metric one activity lacks is NaN on its rows (as the loader's concat gave)", df[df.activity_id == 2].power.isna().all() and df[df.activity_id == 1].power.notna().all())
df_all, _ = st2.assemble([a, b])
check("assemble with no metrics asked: every metric the files had", {"speed", "distance", "heart_rate", "power"} <= set(df_all.columns))
check("assemble marks the activities served as used now", all(abs(time.time() - st2.manifest()[k]["used"]) < 5 for k in ("1", "2")))

old = entry(7, TODAY - timedelta(days=100))
check("messages_fresh: nothing stored - not fresh", not st2.messages_fresh(old))
st2.put_messages(old, [{"id": 1, "type": "TEXT", "content": "x"}])
check("messages: stored and read back", st2.get_messages(7) == [{"id": 1, "type": "TEXT", "content": "x"}] and os.path.isfile(os.path.join(st2.messages_dir, "7.json")))
check("messages_fresh: an old unchanged activity's chat stands; a changed file (re-sync) does not; a recent activity's chat is fetched again",
      st2.messages_fresh(old) and not st2.messages_fresh(dict(old, icu_sync_date="2026-10-09T00:00:00Z"))
      and not st2.messages_fresh(entry(8, TODAY - timedelta(days=5))) and (st2.put_messages(entry(8, TODAY - timedelta(days=5)), []) or not st2.messages_fresh(entry(8, TODAY - timedelta(days=5)))))
check("messages_fresh: the boundary is MESSAGES_FRESH_DAYS (60): a day older counts as settled, the day itself not",
      (st2.put_messages(entry(9, TODAY - timedelta(days=61)), []) or st2.messages_fresh(entry(9, TODAY - timedelta(days=61))))
      and (st2.put_messages(entry(10, TODAY - timedelta(days=60)), []) or not st2.messages_fresh(entry(10, TODAY - timedelta(days=60)))))

# retention: older than 400 days and not served within 30 goes; in use stays; recent stays
st2.put_detail(entry(20, TODAY - timedelta(days=500)), frame(20, TODAY - timedelta(days=500)))
st2.put_messages(entry(20, TODAY - timedelta(days=500)), [])
st2.put_detail(entry(21, TODAY - timedelta(days=500)), frame(21, TODAY - timedelta(days=500)))
st2.manifest()["21"]["used"] = time.time()
st2.put_detail(entry(22, TODAY - timedelta(days=399)), frame(22, TODAY - timedelta(days=399)))
p20, m20 = os.path.join(st2.dir, st2.manifest()["20"]["file"]), os.path.join(st2.messages_dir, "20.json")
gone = st2.prune()
check("prune: the old unused activity leaves with its rows and chat; the old one in use stays; the one inside the retention stays",
      gone == 1 and "20" not in st2.manifest() and not os.path.exists(p20) and not os.path.exists(m20) and "21" in st2.manifest() and "22" in st2.manifest(), (gone, sorted(st2.manifest())))
check("prune: a month on, the one in use goes too", st2.prune(now=time.time() + 31 * 86400) == 1 and "21" not in st2.manifest())
st2.save()
sm = st2.summary()
check("summary: activities, chats, the span of days over every record (rows or chat), the size, the engine", sm["activities"] == 3 and sm["chats"] == 4 and sm["from"] == (TODAY - timedelta(days=399)).isoformat() and sm["to"] == (TODAY - timedelta(days=5)).isoformat()
      and sm["bytes"] > 0 and sm["size_mb"] >= 0 and sm["engine"] in ("parquet", "pickle"), sm)
os.makedirs(os.path.join(WORK, "datasets", "u", "generated"), exist_ok=True)
os.makedirs(os.path.join(WORK, "datasets", "u", "mark2"), exist_ok=True)            # a key's folder without a store
check("stores_under: one entry per key with a store, by mark; the generated and routines folders and storeless keys skipped",
      [s["key_mark"] for s in S.stores_under(os.path.join(WORK, "datasets", "u"))] == ["mark1"] and S.stores_under(os.path.join(WORK, "nowhere")) == [])

# ---- the loader end to end, over the fake calendar ---------------------------------------------------------------
print("-- the loader over the fake calendar")


class _R:
    def __init__(self, body=None, status=200, content=b""):
        self._b, self.status_code, self.content = body, status, content

    def raise_for_status(self):
        if self.status_code != 200:
            raise RuntimeError(f"HTTP {self.status_code}")

    def json(self):
        return self._b


class FakeSession:
    """The Intervals.icu routes the loader calls, answered from the stack's calendar (apis_data), the calls logged."""
    def __init__(self):
        self.calls, self.auth, self.touched = [], None, {}

    def _day(self, aid):
        for d in D.days_in((TODAY - timedelta(days=800)).isoformat(), TODAY.isoformat()):
            if D.activity_id(d) == int(aid):
                return d
        return None

    def get(self, url, params=None, timeout=None):
        path = url.split("/api/v1")[-1]
        self.calls.append(path)
        params = params or {}
        if path == "/athlete/0/activities":
            acts = D.activities(params["oldest"], params["newest"])
            for act in acts:
                if act["id"] in self.touched:
                    act["icu_sync_date"] = self.touched[act["id"]]
            return _R(acts)
        if path.endswith("/fit-file"):
            d = self._day(path.split("/")[2])
            return _R(content=gzip.compress(write_activity(D.fit_records(d), fields=D.fit_fields(d))))
        if path == "/athlete/0/wellness":
            return _R(D.wellness(params["oldest"], params["newest"]))
        if path == "/athlete/0":
            return _R(D.SUBJECT)
        if path == "/athlete/0/events":
            return _R(D.events(params["oldest"], params["newest"]))
        if path.startswith("/chats/"):
            return _R(D.chat(int(path.split("/")[2])))
        if path.endswith("/messages"):
            return _R(D.messages(self._day(path.split("/")[2])))
        return _R({}, 404)

    def fits(self):
        return [c for c in self.calls if c.endswith("/fit-file")]

    def chats(self):
        return [c for c in self.calls if c.endswith("/messages")]


SESSION = FakeSession()
E.requests.Session = lambda: SESSION                      # the loader's session is the fake


class Job(dict):
    """A job record that remembers every progress line it was given (the page polls them)."""
    def __init__(self, *a, **k):
        super().__init__(*a, **k)
        self.lines = []

    def __setitem__(self, k, v):
        if k == "message":
            self.lines.append(str(v))
        super().__setitem__(k, v)


class Jobs(dict):
    """The executor's job table, every record a Job; a record replaced whole (the parse phase resets it) keeps its lines."""
    def __setitem__(self, k, v):
        j = Job(v)
        j.lines = list(getattr(self.get(k), "lines", [])) + ([str(v["message"])] if isinstance(v, dict) and v.get("message") else [])
        super().__setitem__(k, j)


E.intervals_jobs = Jobs()


def load(start, end, metrics=("power", "heart_rate"), aux=("summary", "wellness", "context"), **extra):
    SESSION.calls.clear()
    job = f"job-{len(SESSION.calls)}-{time.time()}"
    E.intervals_jobs[job] = {"status": "starting", "message": "", "created_at": datetime.now(), "progress": 0, "total": 0}
    req = {"api_key": "key-1", "df_id": f"df-{start}-{end}", "start_date": start, "end_date": end, "metrics": list(metrics), "aux_datasets": list(aux), "user_id": "u"}
    req.update(extra)
    E.fetch_intervals_background(req, job)
    return E.intervals_jobs[job]


s1, e1 = (TODAY - timedelta(days=90)).isoformat(), TODAY.isoformat()
j1 = load(s1, e1)
r1 = j1.get("result") or {}
n1 = len(D.activities(s1, e1))
check("a first load fetches every file of the window and keeps each activity in the store", j1["status"] == "completed" and len(SESSION.fits()) == n1 == 91
      and r1["store"]["held"] == 0 and r1["store"]["fetched"] == n1 and r1["store"]["window"] == n1 and r1["store"]["summary"]["activities"] == n1, (j1.get("error"), j1.get("message"), r1.get("store")))
df1 = E.df_cache.get(r1["df_id"])
check("the frame is the window's: every activity, the metrics asked, newest first, the activity's name and type from the list",
      df1 is not None and df1.activity_id.nunique() == n1 and {"power", "heart_rate", "activity_id", "datetime", "activity_type", "activity_name"} == set(df1.columns)
      and df1.datetime.is_monotonic_decreasing and df1.activity_name.str.startswith(("Ride ", "Run ")).all(), (None if df1 is None else (df1.shape, list(df1.columns))))
chats1 = len(SESSION.chats())
check("the context: every chat of the window fetched on the first load and kept", chats1 == sum(1 for d in D.days_in(s1, e1) if D.has_chat(d)) and chats1 > 0 and r1["context"]["messages_reused"] == 0, (chats1, r1.get("context")))
store_dir = os.path.join("datasets", "u", E.key_mark("key-1"), "store")
check("the store lives under datasets/<user>/<mark>/store beside the window's files", os.path.isdir(os.path.join(store_dir, "activities")) and os.path.isfile(os.path.join(store_dir, "activities.json"))
      and len(os.listdir(os.path.join(store_dir, "activities"))) == n1 and len(os.listdir(os.path.join(store_dir, "messages"))) == chats1)

# the same frame as a straight parse would give (the store is a cache, not a different reading)
direct = []
for d in D.days_in(s1, e1):
    fit = write_activity(D.fit_records(d), fields=D.fit_fields(d))
    df = E.parse_fit_file_parallel(fit, D.activity_id(d), D.activity(d), ["power", "heart_rate"])
    if df is not None:
        direct.append(df)
direct = E.transform_intervals_detail_data(pd.concat(direct, ignore_index=True)).sort_values(["datetime", "activity_id"]).reset_index(drop=True)
mine = df1.sort_values(["datetime", "activity_id"]).reset_index(drop=True)[direct.columns]
check("the frame from the store equals the frame a straight parse gives", mine.shape == direct.shape and (mine.fillna(-1) == direct.fillna(-1)).all().all(), (mine.shape, direct.shape))

s2 = (TODAY - timedelta(days=100)).isoformat()
j2 = load(s2, e1)
r2 = j2.get("result") or {}
n2 = len(D.activities(s2, e1))
check("a wider second load fetches only the ten new files; the rest come from the store", j2["status"] == "completed" and len(SESSION.fits()) == 10 and r2["store"]["held"] == n1 and r2["store"]["fetched"] == 10
      and E.df_cache.get(r2["df_id"]).activity_id.nunique() == n2 == n1 + 10, (len(SESSION.fits()), r2.get("store")))
new_chats = sum(1 for d in D.days_in(s2, (TODAY - timedelta(days=91)).isoformat()) if D.has_chat(d))
check("the chats of the settled activities come from the store; only the new activities' chats are fetched", len(SESSION.chats()) == new_chats and r2["context"]["messages_reused"] == chats1, (len(SESSION.chats()), new_chats, r2.get("context", {}).get("messages_reused")))
ctx2 = pd.read_csv(r2["context"]["path"])
check("the context file of the second window has the passages of both (the reused chats among them)", len(ctx2) > 0 and (ctx2.kind == "activity_message").sum() >= chats1, (len(ctx2), ctx2.kind.value_counts().to_dict()))

j3 = load(s2, e1, metrics=("heart_rate", "speed"))
r3 = j3.get("result") or {}
check("the same window again, other metrics: nothing downloaded, the frame served from the store with the metrics now asked",
      j3["status"] == "completed" and len(SESSION.fits()) == 0 and r3["store"]["held"] == n2 and r3["store"]["fetched"] == 0 and len(SESSION.chats()) == 0
      and {"heart_rate", "speed"} <= set(E.df_cache.get(r3["df_id"]).columns) and "power" not in E.df_cache.get(r3["df_id"]).columns, (len(SESSION.fits()), r3.get("store"), list(E.df_cache.get(r3["df_id"]).columns) if r3 else None))
check("the loader's progress lines say what the store held and what was downloaded (the page shows them)",
      any(l == f"The store holds all {n2} activities of this window; nothing to download" for l in getattr(j3, "lines", []))
      and any(l == f"The store holds {n1} of {n2} activities; downloading 10..." for l in getattr(j2, "lines", []))
      and any(l.startswith("Fetching messages 1/") for l in getattr(j2, "lines", [])), (getattr(j2, "lines", [])[:6], getattr(j3, "lines", [])[:4]))

# a changed file: one activity re-synced on Intervals
touched_day = next(d for d in D.days_in((TODAY - timedelta(days=85)).isoformat(), (TODAY - timedelta(days=61)).isoformat()) if D.has_chat(d))   # one with a chat, among the held
SESSION.touched[D.activity_id(touched_day)] = "2026-10-15T00:00:00Z"
j4 = load(s2, e1)
r4 = j4.get("result") or {}
check("a re-synced activity (its signature changed) is fetched again, alone; its chat too", len(SESSION.fits()) == 1 and SESSION.fits()[0] == f"/activity/{D.activity_id(touched_day)}/fit-file"
      and r4["store"]["fetched"] == 1 and len(SESSION.chats()) == (1 if D.has_chat(touched_day) else 0), (SESSION.fits(), SESSION.chats()))
check("the one fetch's progress line counts the chats taken from the store before it", D.has_chat(touched_day) and any(l.startswith("Fetching messages") and "from the store" in l for l in getattr(j4, "lines", [])), [l for l in getattr(j4, "lines", []) if "messages" in l])

j5 = load(s2, e1, refresh=True)
r5 = j5.get("result") or {}
check("refresh: every file and every chat fetched again", len(SESSION.fits()) == n2 and r5["store"]["held"] == 0 and r5["store"]["fetched"] == n2 and r5["store"]["refresh"]
      and len(SESSION.chats()) == sum(1 for d in D.days_in(s2, e1) if D.has_chat(d)) and r5["context"]["messages_reused"] == 0, (len(SESSION.fits()), r5.get("store")))

# the cache listing shows the store
with E.app.test_client() as c:
    listing = c.get("/cache/inspect?user_id=u").get_json()
mine_store = [s for s in listing.get("stores", []) if s["key_mark"] == E.key_mark("key-1")]
check("/cache/inspect lists the key's store among the user's: its mark, activities, chats, span and size", len(mine_store) == 1 and [s["key_mark"] for s in listing["stores"]] == sorted(s["key_mark"] for s in listing["stores"])
      and mine_store[0]["activities"] == n2 and mine_store[0]["chats"] > 0 and mine_store[0]["to"] == e1, listing.get("stores"))
check("the window's files are listed as before, the store folder not among them", all(x["filename"].endswith(".csv") for x in listing["auxiliary_datasets"]) and len(listing["auxiliary_datasets"]) >= 3)

# retention: a key's old data leaves when it is older than the retention asked and not in use
j6 = load(s2, e1, retention_days=50)
r6 = j6.get("result") or {}
check("retention_days from the request: the window's own activities stay (served now), nothing else is there to go", j6["status"] == "completed" and r6["store"]["summary"]["activities"] == n2, r6.get("store"))

# every download failing (the fake calendar lists days it has no file for): the error as before, nothing kept
j7 = load((TODAY + timedelta(days=5)).isoformat(), (TODAY + timedelta(days=9)).isoformat())
check("a window whose files all fail to download is the error it was, and the store keeps none of them", j7["status"] == "error" and "No data could be extracted" in j7["error"]
      and all(not S.Store(os.path.join("datasets", "u"), E.key_mark("key-1")).has_detail(a) for a in D.activities((TODAY + timedelta(days=5)).isoformat(), (TODAY + timedelta(days=9)).isoformat())), j7)

fails = [n for n, ok in results if not ok]
print(f"\n{len(results) - len(fails)} passed, {len(fails)} failed")
sys.exit(1 if fails else 0)
