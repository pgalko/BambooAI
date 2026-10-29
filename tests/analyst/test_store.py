"""The Intervals.icu store (docs/INCREMENTAL_LOADS_DESIGN.md, 2026-10-15): what a load fetched, kept by activity under
the key's folder, so a window is a view - the loader takes from the store every activity whose file has not changed,
downloads only the rest, and reuses the settled chats. The store's pieces over small frames, then the executor's
loader end to end over the stack's fake calendar with a fake session: a first load fetches every file, a wider
second load only the new ones, a third nothing; a changed file is fetched again; a refresh fetches all.

    python3 tests/analyst/test_store.py
"""
import gzip
import json
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

    @property
    def ok(self):
        return self.status_code == 200

    def raise_for_status(self):
        if self.status_code != 200:
            raise RuntimeError(f"HTTP {self.status_code}")

    def json(self):
        return self._b


class FakeSession:
    """The Intervals.icu routes the loader calls, answered from the stack's calendar (apis_data), the calls logged."""
    def __init__(self):
        self.calls, self.auth, self.touched = [], None, {}
        self.wellness_patch, self.dropped_events = {}, set()      # a day corrected at the source; a calendar entry deleted there

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
            rows = D.wellness(params["oldest"], params["newest"])
            for row in rows:
                row.update(self.wellness_patch.get(row["id"], {}))
            return _R(rows)
        if path.endswith("/intervals"):
            return _R(D.laps(self._day(path.split("/")[2])))
        if path == "/athlete/0":
            return _R(D.SUBJECT)
        if path == "/athlete/0/events":
            return _R([e for e in D.events(params["oldest"], params["newest"]) if e["id"] not in self.dropped_events])
        if path.startswith("/chats/"):
            return _R(D.chat(int(path.split("/")[2])))
        if path.endswith("/messages"):
            return _R(D.messages(self._day(path.split("/")[2])))
        return _R({}, 404)

    def fits(self):
        return [c for c in self.calls if c.endswith("/fit-file")]

    def chats(self):
        return [c for c in self.calls if c.endswith("/messages")]

    def laps(self):
        return [c for c in self.calls if c.endswith("/intervals")]


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
# the planned workouts file (2026-10-15): written with the context, one row per WORKOUT entry of the window's calendar
plan_path = next((p_ for p_ in r1["aux_datasets"] if "planned_workouts_" in p_), "")
plan_df = pd.read_csv(plan_path, dtype=str, keep_default_na=False) if plan_path else None
ev1 = [e for e in D.events(s1, e1) if e["category"] == "WORKOUT"]
check("the load with the context wrote the planned workouts file beside the context file: one row per WORKOUT entry, the ride days paired to their activity (with its compliance), the skipped sessions with none, the plan's numbers, the step lines and the structure as JSON",
      plan_df is not None and len(plan_df) == len(ev1) and plan_path.endswith(f"planned_workouts_{s1.replace('-', '')}_to_{e1.replace('-', '')}.csv")
      and (plan_df.activity_id != "").sum() == sum(1 for e in ev1 if e["name"] == "Endurance") and (plan_df.activity_id == "").sum() == sum(1 for e in ev1 if e["name"] == "Strength")
      and set(plan_df[plan_df["name"] == "Endurance"].steps) == {"-2h 60%"} and set(plan_df[plan_df["name"] == "Endurance"].prose) == {"Keep it conversational, fuel every hour."}
      and set(plan_df[plan_df["name"] == "Endurance"].planned_duration_sec) == {"7200"} and all(json.loads(x)["steps"][0]["duration"] == 7200 for x in plan_df[plan_df["name"] == "Endurance"].workout_doc)
      and set(plan_df[plan_df["name"] == "Strength"].steps) == {"-45m core"} and set(plan_df[plan_df["name"] == "Strength"].prose) == {""},
      (plan_path, None if plan_df is None else (len(plan_df), len(ev1), plan_df.head(3).to_dict("records"))))
chats1 = len(SESSION.chats())
check("the context: every chat of the window fetched on the first load and kept", chats1 == sum(1 for d in D.days_in(s1, e1) if D.has_chat(d)) and chats1 > 0 and r1["context"]["messages_reused"] == 0, (chats1, r1.get("context")))
# the athlete's folder (2026-10-29, docs/DATASETS_DESIGN.md §2): the load learns the athlete's id from the profile call it makes
# first, and writes under datasets/<user>/intervals/<id>/ - the store, the window's files, the athlete's record
store_dir = os.path.join("datasets", "u", "intervals", D.SUBJECT["id"], "store")
check("the store lives under datasets/<user>/intervals/<athlete id>/store beside the window's files", os.path.isdir(os.path.join(store_dir, "activities")) and os.path.isfile(os.path.join(store_dir, "activities.json"))
      and len(os.listdir(os.path.join(store_dir, "activities"))) == n1 and len(os.listdir(os.path.join(store_dir, "messages"))) == chats1
      and all(p_.startswith(os.path.join("datasets", "u", "intervals", D.SUBJECT["id"]) + os.sep) for p_ in r1["aux_datasets"]), (store_dir, r1.get("aux_datasets")))
_rec = S.athlete_record(os.path.join("datasets", "u"), "intervals/" + D.SUBJECT["id"])
check("the athlete's record beside the store: the source, the id and the name the profile gave, the mark of the key that loaded, first seen and last load, the datasets the load asked for; the load's result and the frame's metadata carry the same athlete",
      _rec.get("source") == "intervals" and _rec.get("id") == D.SUBJECT["id"] and _rec.get("name") == D.SUBJECT["name"] and _rec.get("marks") == [E.key_mark("key-1")] and _rec.get("first_seen") and _rec.get("last_load") and _rec.get("kinds") == ["summary", "wellness", "context"]
      and r1.get("subject") == {"source": "intervals", "id": D.SUBJECT["id"], "name": D.SUBJECT["name"], "folder": "intervals/" + D.SUBJECT["id"]}
      and (E.df_cache.get_all_metadata()[-1].get("subject") or {}).get("id") == D.SUBJECT["id"] and E.df_cache.get_all_metadata()[-1].get("folder") == "intervals/" + D.SUBJECT["id"]
      and not os.path.exists(os.path.join("datasets", "u", E.key_mark("key-1"))), (_rec, r1.get("subject"), E.df_cache.get_all_metadata()[-1]))

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

jp = load(s1, e1, aux=("summary", "plan"))
rp = jp.get("result") or {}
check("the planned workouts asked for on their own: the file written from the calendar (one call), no context file, nothing downloaded",
      jp["status"] == "completed" and any("planned_workouts_" in p_ for p_ in rp["aux_datasets"]) and not any("context_notes_" in p_ for p_ in rp["aux_datasets"]) and rp.get("context") is None
      and len(SESSION.fits()) == 0 and sum(1 for c in SESSION.calls if c == "/athlete/0/events") == 1, (jp.get("error"), rp.get("aux_datasets"), [c for c in SESSION.calls if "events" in c]))
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
mine_store = [s for s in listing.get("stores", []) if s["folder"] == "intervals/" + D.SUBJECT["id"]]
check("/cache/inspect lists the athlete's store among the user's: its folder, the athlete (source, id, name), activities, chats, span and size; a store from before the athlete was known keeps its mark",
      len(mine_store) == 1 and mine_store[0]["subject"] == {"source": "intervals", "id": D.SUBJECT["id"], "name": D.SUBJECT["name"]} and mine_store[0]["key_mark"] == ""
      and mine_store[0]["activities"] == n2 and mine_store[0]["chats"] > 0 and mine_store[0]["to"] == e1
      and [s["folder"] for s in listing["stores"] if s["key_mark"]] == ["mark1"] and [s["subject"] for s in listing["stores"] if s["key_mark"]] == [None], listing.get("stores"))
check("the window's files are listed as before, each with its folder and its athlete, the store folder and the athlete's record not among them; the athletes are listed with their marks",
      all(x["filename"].endswith(".csv") for x in listing["auxiliary_datasets"]) and len(listing["auxiliary_datasets"]) >= 3
      and all(x["folder"] == "intervals/" + D.SUBJECT["id"] and x["subject"]["name"] == D.SUBJECT["name"] and x["key_mark"] == "" for x in listing["auxiliary_datasets"] if x["filename"].startswith(("wellness", "activity_summary", "context")))
      and [a["id"] for a in listing.get("subjects", [])] == [D.SUBJECT["id"]] and listing["subjects"][0]["marks"] == [E.key_mark("key-1")] and listing["subjects"][0]["folder"] == "intervals/" + D.SUBJECT["id"], (listing.get("subjects"), listing["auxiliary_datasets"][:2]))

# the migration (docs/DATASETS_DESIGN.md §9): a key's folder from before the athlete was known moves under the athlete's folder
# the first time the athlete is known - renamed when the athlete has no folder yet, absorbed (its window files kept when absent,
# its store's activities and chats the athlete's store lacks taken over) when it has; nothing is downloaded again
_udir = os.path.join("datasets", "u")
_legacy = S.Store(_udir, "markX")
_legacy.put_detail({"id": 900001, "start_date_local": "2025-01-05T08:00:00", "icu_sync_date": "x"}, pd.DataFrame({"power": [1, 2]})); _legacy.put_messages({"id": 900001, "start_date_local": "2025-01-05T08:00:00"}, [{"content": "old"}]); _legacy.save()
open(os.path.join(_udir, "markX", "wellness_data_20250101_to_20250131.csv"), "w").write("date,weight\n2025-01-01,70\n")
_moved = S.adopt_mark_folder(_udir, "markX", "intervals/i9")
check("a mark's folder for an athlete with no folder yet is renamed whole", _moved == {"renamed": True, "files": 0, "activities": 0} and not os.path.exists(os.path.join(_udir, "markX"))
      and os.path.isfile(os.path.join(_udir, "intervals", "i9", "wellness_data_20250101_to_20250131.csv")) and S.Store(_udir, "intervals/i9").has_detail({"id": 900001, "start_date_local": "2025-01-05T08:00:00", "icu_sync_date": "x"}), _moved)
_old2 = S.Store(_udir, E.key_mark("key-2"))
_recent = (TODAY - timedelta(days=200)).isoformat() + "T08:00:00"                 # within the retention: an old folder's activity that is not is pruned as any other
_old2.put_detail({"id": 900002, "start_date_local": _recent, "icu_sync_date": "y"}, pd.DataFrame({"power": [3]})); _old2.put_messages({"id": 900002, "start_date_local": _recent}, [{"content": "older"}]); _old2.save()
open(os.path.join(_udir, E.key_mark("key-2"), "wellness_data_20250201_to_20250228.csv"), "w").write("date,weight\n2025-02-01,70\n")
before_fits = len(SESSION.fits())
j9 = load(s2, e1, api_key="key-2")                                # a rotated key: the same athlete (the fake's profile), its old folder absorbed
r9 = j9.get("result") or {}
_rec2 = S.athlete_record(_udir, "intervals/" + D.SUBJECT["id"])
check("a rotated key loads the same athlete: the key's old folder is absorbed into the athlete's (the window file kept - under views/ once the load runs, the activity and its chat taken over), the record lists both marks, and the window came from the store - nothing downloaded again",
      j9["status"] == "completed" and r9["subject"]["id"] == D.SUBJECT["id"] and not os.path.exists(os.path.join(_udir, E.key_mark("key-2")))
      and os.path.isfile(os.path.join(_udir, "intervals", D.SUBJECT["id"], "views", "wellness_data_20250201_to_20250228.csv")) and not os.path.exists(os.path.join(_udir, "intervals", D.SUBJECT["id"], "wellness_data_20250201_to_20250228.csv"))
      and S.Store(_udir, "intervals/" + D.SUBJECT["id"]).has_detail({"id": 900002, "start_date_local": _recent, "icu_sync_date": "y"})
      and S.Store(_udir, "intervals/" + D.SUBJECT["id"]).get_messages(900002) == [{"content": "older"}]
      and _rec2.get("marks") == [E.key_mark("key-1"), E.key_mark("key-2")] and r9["store"]["held"] == n2 and len(SESSION.fits()) == 0, (j9.get("error"), r9.get("store"), _rec2, len(SESSION.fits())))

# retention: a key's old data leaves when it is older than the retention asked and not in use
j6 = load(s2, e1, retention_days=50)
r6 = j6.get("result") or {}
check("retention_days from the request: the window's own activities stay (served now), nothing else is there to go", j6["status"] == "completed" and r6["store"]["summary"]["activities"] == n2, r6.get("store"))

# every download failing (the fake calendar lists days it has no file for): the error as before, nothing kept
j7 = load((TODAY + timedelta(days=5)).isoformat(), (TODAY + timedelta(days=9)).isoformat())
check("a window whose files all fail to download is the error it was, and the store keeps none of them", j7["status"] == "error" and "No data could be extracted" in j7["error"]
      and all(not S.Store(os.path.join("datasets", "u"), E.key_mark("key-1")).has_detail(a) for a in D.activities((TODAY + timedelta(days=5)).isoformat(), (TODAY + timedelta(days=9)).isoformat())), j7)

# the rider profile (2026-10-16, docs/RIDER_PROFILE_DESIGN.md): a load asking for it writes the profile from the record - fetched once
# for the context and the profile - and the custom zone times from the list, after the plan; the summary carries the settings in force
sr, er = (TODAY - timedelta(days=120)).isoformat(), (TODAY - timedelta(days=61)).isoformat()      # a window with rides (the fake's rides are older than sixty days)
jr = load(sr, er, aux=("summary", "rider", "context"))
rr = jr.get("result") or {}
rider_path = next((p_ for p_ in rr.get("aux_datasets", []) if "rider_profile_" in p_), "")
zones_path = next((p_ for p_ in rr.get("aux_datasets", []) if "custom_zone_times_" in p_), "")
prof = pd.read_csv(rider_path, dtype=str, keep_default_na=False) if rider_path else None
zt = pd.read_csv(zones_path, dtype=str, keep_default_na=False) if zones_path else None
rides = sum(1 for d in D.days_in(sr, er) if D.is_ride(d))
ptxt = open(rider_path, encoding="utf-8").read() if rider_path else ""
check("a load with the rider profile: the record fetched once for the context and the profile; the profile and the zone times after the plan; the profile's six sections from the record (the scales its form tracks last, 2026-10-18), nothing identifying in it; one zone-time row per ride and custom zone, named from the definitions; the summary's settings columns",
      jr["status"] == "completed" and SESSION.calls.count("/athlete/0") == 1 and rr["aux_datasets"][-2:] == [rider_path, zones_path] and rr.get("profile_note") == ""
      and prof is not None and list(prof.columns) == E.PROFILE_COLUMNS and list(dict.fromkeys(prof.section)) == ["subject", "sport", "zone", "custom_zone", "custom_field", "scale"]
      and prof[(prof.section == "sport") & (prof.key == "ftp")].value.tolist() == ["280"] and prof[(prof.section == "subject") & (prof.key == "weight")].value.tolist() == ["71.0"]
      and prof[prof.section == "custom_zone"].key.tolist() == ["Breath:low", "Breath:high", "Cad:grind"] and set(prof[prof.section == "custom_field"].key) == {"Sickness", "Lbl"}
      and prof[prof.section == "scale"].key.tolist() == ["soreness", "sleepQuality"] and set(prof[prof.section == "scale"].value) == {"1-4"}
      and all(s not in ptxt for s in ("subject@example.test", "not-a-real-key", "424242", "1998-05-20", "Subject"))
      and zt is not None and len(zt) == 3 * rides and rides > 0 and set(zt.zone_name) == {"Low", "High", "Grind"} and set(zt.stream) == {"respiration", "cadence"}
      and {"max_hr_setting", "pm_ftp_watts", "power_zones", "hr_zones"} <= set(pd.read_csv(next(p_ for p_ in rr["aux_datasets"] if "activity_summary_" in p_), nrows=1).columns),
      (jr.get("error"), rr.get("aux_datasets"), None if prof is None else prof.head(12).to_dict("records"), None if zt is None else zt.head(3).to_dict("records")))
# every custom field under its code (2026-10-16, patch 0183): the intervals file carries the account's interval select as the option's
# text under its code with the number beside it; the record is fetched for the definitions whatever files are asked
ji = load(sr, er, aux=("intervals",))
ri = ji.get("result") or {}
ipath = next((p_ for p_ in ri.get("aux_datasets", []) if "activity_intervals_" in p_), "")
idf = pd.read_csv(ipath) if ipath else None
days_r = sum(1 for _ in D.days_in(sr, er))
check("a load with the intervals: the record fetched once for the definitions; the file carries the account's select under its code as the option's text with the number in <code>_value on the rides' laps, nothing on the runs'; the legacy label column (another coach's code) is empty; three laps per activity",
      ji["status"] == "completed" and SESSION.calls.count("/athlete/0") == 1 and idf is not None and len(idf) == 3 * days_r
      and set(idf["Lbl"].dropna()) == {"Recovery", "Endurance", "Tempo"} and sorted(idf["Lbl_value"].dropna().unique()) == [1.0, 2.0, 3.0] and idf["Lbl"].notna().sum() == 3 * rides
      and idf["label"].isna().all() and list(idf.columns)[:2] == ["activity_id", "lap_number"], (ji.get("error"), ipath, None if idf is None else (len(idf), list(idf.columns)[-6:], idf["Lbl"].notna().sum(), rides)))
saved_subject = D.SUBJECT
D.SUBJECT = dict(saved_subject, custom_items=[it for it in saved_subject["custom_items"] if it["type"] != "ZONES"])
try:
    jn = load(sr, er, aux=("summary", "rider"))
    rn = jn.get("result") or {}
    profn = pd.read_csv(next(p_ for p_ in rn["aux_datasets"] if "rider_profile_" in p_), dtype=str, keep_default_na=False)
    check("an account without custom zone sets: the profile without custom_zone rows and no zone times file beside it; without the context no chat is fetched",
          jn["status"] == "completed" and not any("custom_zone_times_" in p_ for p_ in rn["aux_datasets"]) and "custom_zone" not in set(profn.section) and len(profn[profn.section == "custom_field"]) == 2
          and SESSION.calls.count("/athlete/0") == 1 and not SESSION.chats(), (jn.get("error"), rn.get("aux_datasets")))
finally:
    D.SUBJECT = saved_subject

# ---- the feeds in the store (2026-10-29, docs/DATASETS_DESIGN.md §3, step 2) -----------------------------------------
print("-- the feeds in the store")
_me = S.Store(_udir, "intervals/" + D.SUBJECT["id"])
_views = os.path.join(_udir, "intervals", D.SUBJECT["id"], "views")
check("the window's files live under the athlete's views/ folder, nothing at the folder itself but the record and the store",
      os.path.isdir(_views) and all(p_.startswith(_views + os.sep) for p_ in rn["aux_datasets"] + ri["aux_datasets"] + r1["aux_datasets"])
      and sorted(os.listdir(os.path.join(_udir, "intervals", D.SUBJECT["id"]))) == ["store", "subject.json", "views"], (rn.get("aux_datasets"), sorted(os.listdir(os.path.join(_udir, "intervals", D.SUBJECT["id"])))))
# the laps: the settled window's laps were fetched once (the load above with the intervals file) and kept as the API gave them
_laps_calls_first = days_r
check("the laps of every activity of the window were fetched once and kept under the store (laps/<id>.json.gz, the answer as given), the manifest saying when and under which signature; the result's account says so",
      ri["store"]["laps"] == {"window": days_r, "held": 0, "fetched": days_r} and len(os.listdir(_me.laps_dir)) >= days_r
      and all(_me.manifest()[str(D.activity_id(d))].get("laps_fetched") and _me.manifest()[str(D.activity_id(d))].get("laps") == 3 for d in D.days_in(sr, er))
      and _me.get_laps(D.activity_id(next(iter(D.days_in(sr, er))))) == D.laps(next(iter(D.days_in(sr, er)))), (ri.get("store", {}).get("laps"), sorted(os.listdir(_me.laps_dir))[:3]))
ji2 = load(sr, er, aux=("intervals",))
ri2 = ji2.get("result") or {}
idf2 = pd.read_csv(next(p_ for p_ in ri2["aux_datasets"] if "activity_intervals_" in p_))
check("the same settled window again: no laps fetched - every activity older than sixty days and unchanged is served from the store, and the file is the same",
      ji2["status"] == "completed" and SESSION.laps() == [] and ri2["store"]["laps"] == {"window": days_r, "held": days_r, "fetched": 0}
      and idf2.shape == idf.shape and (idf2.fillna(-1) == idf.fillna(-1)).all().all() and any(l.startswith("Fetching laps") for l in getattr(ji, "lines", [])) and not any(l.startswith("Fetching laps") for l in getattr(ji2, "lines", [])),
      (SESSION.laps()[:3], ri2.get("store", {}).get("laps"), [l for l in getattr(ji2, "lines", []) if "laps" in l]))
_touch_day = next(iter(D.days_in(sr, er)))
SESSION.touched[D.activity_id(_touch_day)] = "2026-10-20T00:00:00Z"
ji3 = load(sr, er, aux=("intervals",))
ri3 = ji3.get("result") or {}
check("a re-synced activity's laps are fetched again, alone (its file changed: the signature decides, as for the chat)", SESSION.laps() == [f"/activity/{D.activity_id(_touch_day)}/intervals"] and ri3["store"]["laps"]["fetched"] == 1 and ri3["store"]["laps"]["held"] == days_r - 1, (SESSION.laps(), ri3.get("store", {}).get("laps")))
ji4 = load(sr, er, aux=("intervals",), refresh=True)
check("refresh fetches every activity's laps again", len(SESSION.laps()) == days_r and (ji4.get("result") or {})["store"]["laps"]["held"] == 0, len(SESSION.laps()))
_recent_s, _recent_e = (TODAY - timedelta(days=20)).isoformat(), (TODAY - timedelta(days=11)).isoformat()
ji5 = load(_recent_s, _recent_e, aux=("intervals",)); ji6 = load(_recent_s, _recent_e, aux=("intervals",))
_n_recent = sum(1 for _ in D.days_in(_recent_s, _recent_e))
check("a recent window's laps are fetched on every load (labels, RPE and lactate are typed in after the sync): held none, fetched all, twice",
      ji5["status"] == "completed" and ji6["status"] == "completed" and len(SESSION.laps()) == _n_recent and (ji6.get("result") or {})["store"]["laps"] == {"window": _n_recent, "held": 0, "fetched": _n_recent}, (len(SESSION.laps()), (ji6.get("result") or {}).get("store", {}).get("laps")))
check("a load without the laps file carries no laps account", r1["store"].get("laps") is None)

# the wellness log by day and the calendar by entry: merged across loads, the span the union, a day corrected at the source
# corrected here, an entry deleted there gone here, the file the store's window
_w = _me.feed("wellness").span(); _e = _me.feed("events").span()
_all_days = [d for d in D.days_in(min(s2, sr), e1) if D.has_wellness(d)]
check("the wellness log in the store spans every window loaded with it (the union), a record per day the source had one; the calendar too, by entry",
      _w["from"] == _all_days[0].isoformat() and _w["to"] == _all_days[-1].isoformat() and _w["count"] == len(_all_days)
      and _e["from"] <= s2 and _e["to"] >= (TODAY - timedelta(days=61)).isoformat() and _e["count"] == len({e["id"] for e in D.events(min(s2, sr), e1) if e["id"] not in SESSION.dropped_events}), (_w, _e, len(_all_days)))
_wday = next(d for d in D.days_in(s2, e1) if D.has_wellness(d)).isoformat()
SESSION.wellness_patch[_wday] = {"weight": 65.5}
_gone_event = next(e["id"] for e in D.events(s2, e1) if e["category"] == "WORKOUT")
SESSION.dropped_events.add(_gone_event)
jw = load(s2, e1, aux=("wellness", "plan"))
rw = jw.get("result") or {}
wdf = pd.read_csv(next(p_ for p_ in rw["aux_datasets"] if "wellness_data_" in p_))
pdf = pd.read_csv(next(p_ for p_ in rw["aux_datasets"] if "planned_workouts_" in p_), dtype=str, keep_default_na=False)
_me = S.Store(_udir, "intervals/" + D.SUBJECT["id"])                  # read afresh: the loader's own Store wrote the files
check("a day corrected at the source is corrected in the store and in the window's file; an entry deleted at the source is gone from both; the span held did not shrink",
      jw["status"] == "completed" and float(wdf[wdf.date == _wday].weight.iloc[0]) == 65.5 and _me.feed("wellness").records()[_wday]["r"]["weight"] == 65.5
      and str(_gone_event) not in set(pdf.event_id) and str(_gone_event) not in _me.feed("events").records() and _me.feed("wellness").span() == _w and _me.feed("events").span()["count"] == _e["count"] - 1,
      (float(wdf[wdf.date == _wday].weight.iloc[0]) if len(wdf[wdf.date == _wday]) else None, _me.feed("wellness").span(), _me.feed("events").span()))
check("the wellness file is the same frame the one call gives (the store is a cache, not another reading): the day as date, newest first, every column with data",
      list(wdf.columns)[0] == "date" and pd.to_datetime(wdf.date).is_monotonic_decreasing and len(wdf) == sum(1 for d in D.days_in(s2, e1) if D.has_wellness(d))
      and set(wdf.columns) == set(E.wellness_frame(D.wellness(s2, e1)).columns), (list(wdf.columns), len(wdf)))
check("the feeds' records carry the day, when fetched and when last served; the summary carries each feed's span and count and the profile's newest day",
      all({"r", "day", "f", "u"} <= set(rec) for rec in list(_me.feed("wellness").records().values())[:5])
      and {k: _me.summary()["feeds"]["wellness"][k] for k in ("from", "to", "count")} == _me.feed("wellness").span() and {k: _me.summary()["feeds"]["events"][k] for k in ("from", "to", "count")} == _me.feed("events").span() and _me.summary()["laps"] >= days_r
      and _me.summary()["profile"]["as_of"] == TODAY.isoformat() and _me.summary()["profile"]["snapshots"] == 1 and _me.summary()["parts"]["activities"] > 0 and _me.summary()["feeds"]["wellness"]["bytes"] > 0, _me.summary())

# the profile as dated snapshots: the record as fetched, a new snapshot when it changed, the day's own replaced
_ps = S.Store(_udir, "intervals/snap")
check("put_profile: the first snapshot, the same record another day no new snapshot, a changed record a new one, the day's own replaced; newest_profile is the newest",
      _ps.put_profile({"id": "x", "ftp": 250}, today=date(2026, 1, 1)) and not _ps.put_profile({"id": "x", "ftp": 250}, today=date(2026, 1, 2))
      and _ps.put_profile({"id": "x", "ftp": 260}, today=date(2026, 2, 1)) and _ps.put_profile({"id": "x", "ftp": 265}, today=date(2026, 2, 1))
      and _ps.profile_days() == ["2026-01-01", "2026-02-01"] and _ps.newest_profile() == ("2026-02-01", {"id": "x", "ftp": 265}) and not _ps.put_profile({}, today=date(2026, 3, 1)), (_ps.profile_days(), _ps.newest_profile()))

# retention, one rule across the feeds: an old unused activity leaves with its laps; old unused days and entries leave; old snapshots but the newest leave
_pr = S.Store(_udir, "intervals/prune")
_old_e = entry(777, TODAY - timedelta(days=500))
_pr.put_detail(_old_e, frame(777, TODAY - timedelta(days=500))); _pr.put_laps(_old_e, {"icu_intervals": [{"LapNumber": 1}]})
_pr.feed("wellness").merge([{"id": (TODAY - timedelta(days=500)).isoformat(), "weight": 70}, {"id": (TODAY - timedelta(days=10)).isoformat(), "weight": 71}], key_of=lambda r: r["id"], day_of=lambda r: r["id"],
                           start=(TODAY - timedelta(days=500)).isoformat(), end=TODAY.isoformat(), now=time.time() - 40 * 86400)
_pr.feed("events").merge([{"id": 1, "start_date_local": (TODAY - timedelta(days=500)).isoformat() + "T00:00:00"}], key_of=lambda r: r["id"], day_of=lambda r: r["start_date_local"],
                         start=(TODAY - timedelta(days=500)).isoformat(), end=TODAY.isoformat(), now=time.time() - 40 * 86400)
_pr.put_profile({"a": 1}, today=TODAY - timedelta(days=500)); _pr.put_profile({"a": 2}, today=TODAY - timedelta(days=450)); _pr.put_profile({"a": 3}, today=TODAY)
_laps_file = _pr._laps_path(777)
_pr.save()
check("prune across the feeds: the old activity leaves with its laps file; the old day and the old entry leave, the recent day stays; the old snapshots leave, the newest stays",
      _pr.prune() == 1 and not os.path.exists(_laps_file) and "777" not in _pr.manifest()
      and list(_pr.feed("wellness").records()) == [(TODAY - timedelta(days=10)).isoformat()] and _pr.feed("events").records() == {}
      and _pr.profile_days() == [TODAY.isoformat()], (sorted(_pr.feed("wellness").records()), _pr.feed("events").records(), _pr.profile_days()))
_pr.save()
check("the feeds are written with the store: a new Store over the folder reads the same", S.Store(_udir, "intervals/prune").feed("wellness").span()["count"] == 1 and S.Store(_udir, "intervals/prune").summary()["profile"]["snapshots"] == 1)

# Records on its own: a window merged replaces the window's records and leaves the rest; held and updated counted; within by day
_rc = S.Records(os.path.join(WORK, "feeds", "w.json"))
_m1 = _rc.merge([{"id": "2026-01-01", "w": 1}, {"id": "2026-01-02", "w": 2}], key_of=lambda r: r["id"], day_of=lambda r: r["id"], start="2026-01-01", end="2026-01-03")
_m2 = _rc.merge([{"id": "2026-01-02", "w": 3}, {"id": "2026-01-03", "w": 4}], key_of=lambda r: r["id"], day_of=lambda r: r["id"], start="2026-01-02", end="2026-01-03")
_m3 = _rc.merge([{"id": "2026-01-02", "w": 3}], key_of=lambda r: r["id"], day_of=lambda r: r["id"], start="2026-01-02", end="2026-01-02")
check("Records.merge: the first window added; the second updates a day, adds one, leaves the day before the window; the third holds the one unchanged; within gives the window by day",
      _m1 == {"added": 2, "updated": 0, "removed": 0, "held": 0} and _m2 == {"added": 1, "updated": 1, "removed": 0, "held": 0} and _m3 == {"added": 0, "updated": 0, "removed": 0, "held": 1}
      and [r["w"] for r in _rc.within("2026-01-01", "2026-01-03")] == [1, 3, 4] and _rc.span() == {"from": "2026-01-01", "to": "2026-01-03", "count": 3}, (_m1, _m2, _m3))
_m4 = _rc.merge([{"id": "2026-01-01", "w": 1}], key_of=lambda r: r["id"], day_of=lambda r: r["id"], start="2026-01-01", end="2026-01-02")
check("Records.merge: a day inside the window that did not come down is removed (deleted at the source); a day outside the window is untouched", _m4 == {"added": 0, "updated": 0, "removed": 1, "held": 1} and sorted(_rc.records()) == ["2026-01-01", "2026-01-03"], (_m4, sorted(_rc.records())))

# the migration takes the laps and the feeds too
_oldm = S.Store(_udir, "markL")
_oldm.put_laps(entry(5001, TODAY - timedelta(days=100)), {"icu_intervals": [{"LapNumber": 1}]})
_oldm.feed("wellness").merge([{"id": "2026-05-05", "weight": 70}], key_of=lambda r: r["id"], day_of=lambda r: r["id"], start="2026-05-05", end="2026-05-05")
_oldm.put_profile({"id": "m"}, today=date(2026, 5, 5))
_oldm.save()
os.makedirs(os.path.join(_udir, "intervals", "iL", "store"), exist_ok=True)
S.Store(_udir, "intervals/iL").put_detail(entry(5002, TODAY - timedelta(days=90)), frame(5002, TODAY - timedelta(days=90))); S.Store(_udir, "intervals/iL").save()
_mv = S.adopt_mark_folder(_udir, "markL", "intervals/iL")
_newm = S.Store(_udir, "intervals/iL")
check("adopt_mark_folder absorbs the laps, the feeds' records and the profile snapshots the athlete's store lacks",
      _mv["activities"] == 1 and _newm.get_laps(5001) == {"icu_intervals": [{"LapNumber": 1}]} and _newm.manifest()["5001"].get("laps_fetched")
      and _newm.feed("wellness").span()["count"] == 1 and _newm.profile_days() == ["2026-05-05"] and not os.path.exists(os.path.join(_udir, "markL")), (_mv, _newm.summary()))
check("adopt_views moves window files an earlier executor left at the folder itself under views/, once",
      (open(os.path.join(_udir, "intervals", "iL", "wellness_data_20260101_to_20260131.csv"), "w").write("date\n") or True) and S.adopt_views(_udir, "intervals/iL") == 1
      and os.path.isfile(os.path.join(_udir, "intervals", "iL", "views", "wellness_data_20260101_to_20260131.csv")) and S.adopt_views(_udir, "intervals/iL") == 0 and S.views_rel("intervals/iL") == "intervals/iL/views")

# the cache listing: the window files under views/ listed under the athlete's folder, as before
with E.app.test_client() as c:
    listing2 = c.get("/cache/inspect?user_id=u").get_json()
_mine_files = [x for x in listing2["auxiliary_datasets"] if x["folder"] == "intervals/" + D.SUBJECT["id"]]
check("/cache/inspect lists the window files from under views/ with the athlete's folder and subject; the store's summary carries the feeds",
      _mine_files and all(x["path"].startswith(_views + os.sep) for x in _mine_files) and all(x["subject"]["id"] == D.SUBJECT["id"] for x in _mine_files)
      and next(s_ for s_ in listing2["stores"] if s_["folder"] == "intervals/" + D.SUBJECT["id"])["feeds"]["wellness"]["count"] == _w["count"], ([x["path"] for x in _mine_files][:3], listing2.get("stores")))

# ---- the tree, forgetting and the views' age (2026-10-29, docs/DATASETS_DESIGN.md §1, §4, §8, step 3) --------------------------
print("-- the tree")
_tree = listing2.get("tree") or {}
_iv = next((x for x in _tree.get("sources", []) if x["source"] == "intervals"), {})
_sub = next((x for x in _iv.get("subjects", []) if x["id"] == D.SUBJECT["id"]), {})
_feeds = {f["feed"]: f for f in _sub.get("feeds", [])}
check("the inspection carries the tree: Intervals.icu with the athlete under it - name, id, folder, held since, last load, size - and one line per dataset the load dialog offers plus the frame (2026-10-29, the dialog redesigned): Activities with the frame's columns, Activity summary (the list's entries), Activity intervals with their rows, Wellness, Context (the chats and the calendar, the span the union, the categories), Rider profile - each with its span, count, size and the files a load writes from it; no window file anywhere in it",
      _sub.get("name") == D.SUBJECT["name"] and _sub.get("folder") == "intervals/" + D.SUBJECT["id"] and _sub.get("held_since") and _sub.get("last_load") and _sub.get("size_mb", 0) > 0
      and list(_feeds) == ["activities", "summary", "laps", "wellness", "context", "profile"]
      and _feeds["activities"]["count"] == _me.summary()["activities"] and _feeds["activities"]["first"] == _me.summary()["from"] and _feeds["activities"]["bytes"] > 0 and {"power", "heart_rate", "datetime"} <= set(_feeds["activities"]["columns"]) and _feeds["activities"]["files"] == []
      and _feeds["summary"]["count"] == _me.feed("entries").span()["count"] and _feeds["summary"]["first"] == _me.feed("entries").span()["from"] and [f["file"] for f in _feeds["summary"]["files"]] == ["activity_summary_<window>.csv"]
      and _feeds["laps"]["count"] == _me.summary()["laps"] and _feeds["laps"]["from"] and _feeds["laps"]["rows"] == 3 * _me.summary()["laps"] and [f["file"] for f in _feeds["laps"]["files"]] == ["activity_intervals_<window>.csv"]
      and _feeds["wellness"]["count"] == _w["count"] and _feeds["wellness"]["first"] == _w["from"] and [f["file"] for f in _feeds["wellness"]["files"]] == ["wellness_data_<window>.csv"]
      and _feeds["context"]["count"] == _me.summary()["chats"] and _feeds["context"]["rows"] > 0 and _feeds["context"]["entries"] == _me.feed("events").span()["count"] and _feeds["context"]["categories"].get("WORKOUT", 0) > 0
      and _feeds["context"]["first"] == min(_me.summary()["chats_from"], _me.feed("events").span()["from"]) and _feeds["context"]["last"] == max(_me.summary()["chats_to"], _me.feed("events").span()["to"])
      and [f["file"] for f in _feeds["context"]["files"]] == ["context_notes_<window>.csv", "planned_workouts_<window>.csv", "context_codes_<window>.csv"]
      and _feeds["profile"]["as_of"] == TODAY.isoformat() and _feeds["profile"]["count"] == 1 and [f["file"] for f in _feeds["profile"]["files"]] == ["rider_profile_<window>.csv", "custom_zone_times_<window>.csv"] and _sub.get("kinds") == ["wellness", "plan"]
      and "files" not in _sub and not any("filename" in str(x) for x in _iv.get("subjects", [])), (list(_feeds), _sub.get("feeds")))
# the window each dataset's loads covered, on the record (2026-10-29: a load to today must read as ending today, whatever the last
# day with data): the lines' spans are the windows covered joined with the data's days, the data's own first and last day beside
_rec_cov = S.athlete_record(_udir, "intervals/" + D.SUBJECT["id"]).get("covered") or {}
check("the record keeps the window each dataset's loads covered - the activity list and the frame to today (the loads above), the laps' window (the rides' load), the wellness log and the context to today - and the tree's lines show the window covered (to today, though the last activity or chat is older), with the data's own first and last day beside",
      _rec_cov.get("summary") == [min(s2, sr), e1] and _rec_cov.get("activities") == [min(s2, sr), e1] and _rec_cov.get("laps") == [sr, max(er, (TODAY - timedelta(days=11)).isoformat())] and _rec_cov.get("wellness") == [min(s2, sr), e1] and _rec_cov.get("context") == [min(s2, sr), e1]
      and _feeds["activities"]["to"] == e1 and _feeds["activities"]["last"] == _me.summary()["to"] and _feeds["activities"]["first"] == _me.summary()["from"] and _feeds["activities"]["from"] == min(s2, sr, _me.summary()["from"])
      and _feeds["context"]["to"] == e1 and _feeds["context"]["last"] <= e1 and _feeds["wellness"]["to"] == e1 and _feeds["laps"]["to"] == max(er, (TODAY - timedelta(days=11)).isoformat()) and "first" not in _feeds["profile"], (_rec_cov, {k: (v.get("from"), v.get("to"), v.get("first"), v.get("last")) for k, v in _feeds.items()}))
_cov_clip = S.record_covered(_udir, "intervals/" + D.SUBJECT["id"], {"wellness": ((TODAY - timedelta(days=900)).isoformat(), e1)}, cutoff=(TODAY - timedelta(days=400)).isoformat()).get("covered") or {}
check("record_covered widens a dataset's window (the earliest start, the latest end) and the retention's cutoff clips every start; a folder without a record is nothing",
      _cov_clip.get("wellness") == [(TODAY - timedelta(days=400)).isoformat(), e1] and _cov_clip.get("summary") == [min(s2, sr), e1] and S.record_covered(_udir, "intervals/none", {"wellness": ("2026-01-01", "2026-01-02")}) == {}, _cov_clip)
S.record_covered(_udir, "intervals/" + D.SUBJECT["id"], {"wellness": (min(s2, sr), e1)})
# every dataset's columns (the product owner's first point): made the way a load makes the files, over what the store holds
_cols = {f["feed"]: {x["file"]: x["columns"] for x in f.get("files", [])} for f in _sub.get("feeds", [])}
_sdf = pd.read_csv(next(p_ for p_ in r1["aux_datasets"] if "activity_summary_" in p_), nrows=2)
check("every dataset's details carry its columns, as the files have them: the summary's from the entries held (the window file's columns among them, the custom activity field under its code), the laps' from the laps held (activity_id, lap_number, the labels, the custom interval field), the wellness file's as the file names them (date, not id), the context's, plan's and codes' as fixed, the profile's and the zones' (the account defines a custom zone set)",
      set(_sdf.columns) <= set(_cols["summary"]["activity_summary_<window>.csv"]) and "activity_id" in _cols["summary"]["activity_summary_<window>.csv"]
      and {"activity_id", "lap_number", "label", "RPE", "lactate", "average_watts"} <= set(_cols["laps"]["activity_intervals_<window>.csv"]) and set(idf2.columns) <= set(_cols["laps"]["activity_intervals_<window>.csv"])
      and "date" in _cols["wellness"]["wellness_data_<window>.csv"] and "id" not in _cols["wellness"]["wellness_data_<window>.csv"] and "weight" in _cols["wellness"]["wellness_data_<window>.csv"] and set(wdf.columns) <= set(_cols["wellness"]["wellness_data_<window>.csv"])
      and _cols["context"]["context_notes_<window>.csv"] == E.CONTEXT_COLUMNS and _cols["context"]["planned_workouts_<window>.csv"] == E.PLAN_COLUMNS and _cols["context"]["context_codes_<window>.csv"] == E.CODES_COLUMNS
      and _cols["profile"]["rider_profile_<window>.csv"] == E.PROFILE_COLUMNS and _cols["profile"]["custom_zone_times_<window>.csv"] == E.ZONE_TIMES_COLUMNS, _cols)
sys.path.insert(0, os.path.join(ROOT, "analyst"))
import context as _actx  # noqa: E402
check("the codes file's columns the executor names for the dialog are the app's (analyst/context.py writes the file)", E.CODES_COLUMNS == _actx.CODES_COLUMNS, (E.CODES_COLUMNS, _actx.CODES_COLUMNS))
check("the window files are marked as views in the flat listing (the routines' cache check reads them there) and the tree has no uploads but lists Endura and SweatStack empty; no earlier-loads block - a mark folder from before is not in the tree (deleted at start, never listed)",
      all(x.get("view") is True for x in listing2["auxiliary_datasets"] if x["folder"] == "intervals/" + D.SUBJECT["id"]) and _tree["uploads"] == {"frames": [], "files": []}
      and [x["source"] for x in _tree["sources"]] == ["intervals", "endura", "sweatstack"] and _tree["sources"][1]["frames"] == [] and _tree["sources"][1]["files"] == []
      and "legacy" not in _tree and "mark1" not in json.dumps(_tree), (sorted(_tree), _tree.get("uploads")))
# the pure function over made-up lists: frames and files sorted into the groups
_ct = S.cache_tree([{"df_id": "a", "source": "intervals", "date_range": "2026-01-01 to 2026-02-01", "shape": [10, 3], "folder": "intervals/i0", "subject": {"id": "i0"}},
                    {"df_id": "b", "source": "endura", "race_id": 2, "race_title": "Flat crit", "shape": [5, 2]}, {"df_id": "c", "source": "csv", "original_filename": "titanic.csv", "shape": [891, 12]},
                    {"df_id": "d", "source": "intervals", "date_range": "2025-01-01 to 2025-02-01", "shape": [10, 3], "key_mark": "abcdef012345"}, {"df_id": "e", "source": "sweatstack", "shape": [1, 1]}],
                   [{"filename": "race_climbs_race_2.csv", "path": "datasets/u/race_climbs_race_2.csv", "size_mb": 0.1, "folder": ""}, {"filename": "eedr.csv", "path": "datasets/u/eedr.csv", "size_mb": 1.0, "folder": ""},
                    {"filename": "wellness_data_20260101_to_20260201.csv", "path": "datasets/u/intervals/i0/views/wellness_data_20260101_to_20260201.csv", "folder": "intervals/i0", "view": True},
                    {"filename": "activity_summary_20250101_to_20250201.csv", "path": "datasets/u/abcdef012345/activity_summary_20250101_to_20250201.csv", "folder": "abcdef012345", "key_mark": "abcdef012345"}],
                   [{"folder": "intervals/i0", "activities": 2, "chats": 1, "laps": 0, "from": "2026-01-01", "to": "2026-02-01", "size_mb": 1.5, "parts": {"activities": 1000, "messages": 10}, "feeds": {"entries": {"from": "2026-01-01", "to": "2026-02-01", "count": 3}}, "profile": {},
                     "columns_of": {"activity_summary": ["activity_id", "name"]}}, {"folder": "abcdef012345", "activities": 1, "size_mb": 0.2}],
                   [{"source": "intervals", "id": "i0", "name": "One", "folder": "intervals/i0", "marks": ["m"], "first_seen": 1.0, "last_load": 2.0}])
check("cache_tree: the athlete's datasets (activities, the summary from the entries with its file's columns, the context from the chats here) and frame under Intervals.icu; Endura's frame and race file; SweatStack's frame; the csv frame and the plain file under uploads; the mark folder's frame, file and store nowhere (no earlier loads); the view file nowhere",
      [f["feed"] for f in _ct["sources"][0]["subjects"][0]["feeds"]] == ["activities", "summary", "context"] and _ct["sources"][0]["subjects"][0]["feeds"][0]["bytes"] == 1000 and _ct["sources"][0]["subjects"][0]["feeds"][2]["bytes"] == 10
      and _ct["sources"][0]["subjects"][0]["feeds"][1] == {"feed": "summary", "from": "2026-01-01", "to": "2026-02-01", "count": 3, "bytes": 0, "last_used": None, "files": [{"file": "activity_summary_<window>.csv", "columns": ["activity_id", "name"]}]}
      and [fr["df_id"] for fr in _ct["sources"][0]["subjects"][0]["frames"]] == ["a"]
      and _ct["sources"][0]["frames"] == [] and [fr["df_id"] for fr in _ct["sources"][1]["frames"]] == ["b"] and [f["filename"] for f in _ct["sources"][1]["files"]] == ["race_climbs_race_2.csv"]
      and [fr["df_id"] for fr in _ct["sources"][2]["frames"]] == ["e"] and [fr["df_id"] for fr in _ct["uploads"]["frames"]] == ["c"] and [f["filename"] for f in _ct["uploads"]["files"]] == ["eedr.csv"]
      and "legacy" not in _ct and "abcdef012345" not in json.dumps(_ct) and "wellness_data" not in json.dumps(_ct), _ct)

# forgetting: a feed, then the athlete whole; the frames in memory go with the activities
_fg = S.Store(_udir, "intervals/fg")
_fg.put_detail(entry(8001, TODAY - timedelta(days=70)), frame(8001, TODAY - timedelta(days=70))); _fg.put_messages(entry(8001, TODAY - timedelta(days=70)), [{"content": "x"}]); _fg.put_laps(entry(8001, TODAY - timedelta(days=70)), {"icu_intervals": [{"LapNumber": 1}]})
_fg.feed("wellness").merge([{"id": "2026-06-01", "weight": 70}], key_of=lambda r: r["id"], day_of=lambda r: r["id"], start="2026-06-01", end="2026-06-01")
_fg.feed("events").merge([{"id": 9, "start_date_local": "2026-06-01T00:00:00"}], key_of=lambda r: r["id"], day_of=lambda r: r["start_date_local"], start="2026-06-01", end="2026-06-01")
_fg.put_profile({"id": "fg"}); _fg.save()
S.remember_athlete(_udir, "intervals/fg", "intervals", "fg", "Forgotten", "mk")
os.makedirs(os.path.join(_udir, "intervals", "fg", "views"), exist_ok=True); open(os.path.join(_udir, "intervals", "fg", "views", "wellness_data_20260601_to_20260601.csv"), "w").write("date\n")
check("forget a feed: the laps go with their file and their manifest fields, the activity stays; wellness and events go as files; the profile's snapshots go; the rest stands",
      S.forget(_udir, "intervals/fg", "laps") == {"removed": "laps"} and not os.path.exists(_fg._laps_path(8001)) and "laps_fetched" not in S.Store(_udir, "intervals/fg").manifest()["8001"] and S.Store(_udir, "intervals/fg").has_detail(entry(8001, TODAY - timedelta(days=70)))
      and S.forget(_udir, "intervals/fg", "wellness") == {"removed": "wellness"} and not os.path.exists(os.path.join(_fg.dir, "wellness.json")) and S.Store(_udir, "intervals/fg").feed("events").span()["count"] == 1
      and S.forget(_udir, "intervals/fg", "profile") == {"removed": "profile"} and S.Store(_udir, "intervals/fg").profile_days() == [] and S.forget(_udir, "intervals/fg", "nonsense") == {"removed": ""}, sorted(os.listdir(_fg.dir)))
check("delete the context: the chats go with their files and manifest fields, the calendar goes; the activity's rows stay",
      S.forget(_udir, "intervals/fg", "context") == {"removed": "context"} and not os.path.isdir(_fg.messages_dir) and not os.path.exists(os.path.join(_fg.dir, "events.json"))
      and "messages_fetched" not in S.Store(_udir, "intervals/fg").manifest()["8001"] and S.Store(_udir, "intervals/fg").has_detail(entry(8001, TODAY - timedelta(days=70))), sorted(os.listdir(_fg.dir)))
check("delete the activities: the rows go with their files and manifest fields; an entry with nothing left goes from the manifest (the laps and chats were deleted above); the activity list's entries stay",
      (_fg.feed("entries").merge([entry(8001, TODAY - timedelta(days=70))], key_of=lambda r: r["id"], day_of=lambda r: r["start_date_local"], start="2000-01-01", end="2099-01-01") or True)
      and (_fg.save() or True) and os.path.exists(os.path.join(_fg.dir, "entries.json"))
      and S.forget(_udir, "intervals/fg", "activities") == {"removed": "activities"} and not os.path.isdir(_fg.activities_dir) and S.Store(_udir, "intervals/fg").manifest() == {} and S.Store(_udir, "intervals/fg").summary()["activities"] == 0
      and S.Store(_udir, "intervals/fg").feed("entries").span()["count"] == 1, (S.Store(_udir, "intervals/fg").manifest(), sorted(os.listdir(_fg.dir))))
check("forget the athlete: the folder goes whole - the record, the store, the views; nothing where it was; an unknown folder is nothing removed",
      S.forget(_udir, "intervals/fg", "") == {"removed": "subject"} and not os.path.exists(os.path.join(_udir, "intervals", "fg")) and S.forget(_udir, "intervals/nothere", "") == {"removed": ""})
# the route: the folder checked, the athlete's frames in memory dropped with the activities or the folder
with E.app.test_client() as c:
    _bad = c.post("/cache/forget", json={"user_id": "u", "folder": "../etc", "feed": ""}).status_code
    _bad2 = c.post("/cache/forget", json={"user_id": "u", "folder": "generated", "feed": ""}).status_code
    _none = c.post("/cache/forget", json={"user_id": "u", "folder": "intervals/nothere", "feed": ""}).status_code
    _before = [m["df_id"] for m in E.df_cache.get_all_metadata() if (m.get("subject") or {}).get("id") == D.SUBJECT["id"]]
    _r = c.post("/cache/forget", json={"user_id": "u", "folder": "intervals/" + D.SUBJECT["id"], "feed": "laps"}).get_json()
    _after_laps = [m["df_id"] for m in E.df_cache.get_all_metadata() if (m.get("subject") or {}).get("id") == D.SUBJECT["id"]]
    _r2 = c.post("/cache/forget", json={"user_id": "u", "folder": "intervals/" + D.SUBJECT["id"], "feed": ""}).get_json()
    _after = [m["df_id"] for m in E.df_cache.get_all_metadata() if (m.get("subject") or {}).get("id") == D.SUBJECT["id"]]
check("/cache/forget: a folder outside the sources or the app's own is refused, an absent one is 404; forgetting the laps keeps the frames; forgetting the athlete drops its frames from memory and says which, and the folder is gone",
      _bad == 400 and _bad2 == 400 and _none == 404 and _r.get("removed") == "laps" and _r.get("frames_dropped") == [] and _after_laps == _before and len(_before) >= 1
      and _r2.get("removed") == "subject" and sorted(_r2.get("frames_dropped") or []) == sorted(_before) and _after == [] and not os.path.exists(os.path.join(_udir, "intervals", D.SUBJECT["id"])), (_bad, _bad2, _none, _r, _r2, _before, _after))

# earlier loads of the same athlete (2026-10-29, Palo: "get rid of earlier loads"): a mark folder whose store holds an activity the
# athlete's store holds too is the same athlete's - absorbed into the athlete's folder on the next load; one with nothing in common stays
_ab = S.Store(_udir, "intervals/ab")
_ab.put_detail(entry(4001, TODAY - timedelta(days=80)), frame(4001, TODAY - timedelta(days=80))); _ab.save()
_same = S.Store(_udir, "aaaaaaaaaaa1")
_same.put_detail(entry(4001, TODAY - timedelta(days=80)), frame(4001, TODAY - timedelta(days=80))); _same.put_detail(entry(4002, TODAY - timedelta(days=81)), frame(4002, TODAY - timedelta(days=81))); _same.save()
open(os.path.join(_udir, "aaaaaaaaaaa1", "wellness_data_20260801_to_20260831.csv"), "w").write("date\n")
_other = S.Store(_udir, "bbbbbbbbbbb2")
_other.put_detail(entry(5001, TODAY - timedelta(days=80)), frame(5001, TODAY - timedelta(days=80))); _other.save()
_absorbed = S.absorb_mark_folders(_udir, "intervals/ab")
check("absorb_mark_folders: the mark folder sharing an activity with the athlete's store is absorbed (its other activity and its window file taken over, the folder gone); the one with nothing in common stays; an athlete without a store absorbs nothing",
      _absorbed == ["aaaaaaaaaaa1"] and not os.path.exists(os.path.join(_udir, "aaaaaaaaaaa1")) and S.Store(_udir, "intervals/ab").has_detail(entry(4002, TODAY - timedelta(days=81)))
      and os.path.isfile(os.path.join(_udir, "intervals", "ab", "wellness_data_20260801_to_20260831.csv")) and os.path.isdir(os.path.join(_udir, "bbbbbbbbbbb2"))
      and S.absorb_mark_folders(_udir, "intervals/empty") == [], (_absorbed, sorted(os.listdir(_udir))))
# ...and in the loader: the athlete's own earlier folder under another key, with the same activities, is absorbed on a load
_leg = S.Store(_udir, "ccccccccccc3")
_leg.put_detail(D.activity(next(iter(D.days_in(s2, e1)))), frame(D.activity_id(next(iter(D.days_in(s2, e1)))), next(iter(D.days_in(s2, e1))))); _leg.save()
jab = load(s2, e1)
check("a load absorbs an earlier folder that holds one of the athlete's activities: the folder is gone, the activity stays in the athlete's store, the load is fine",
      jab["status"] == "completed" and not os.path.exists(os.path.join(_udir, "ccccccccccc3")) and S.Store(_udir, "intervals/" + D.SUBJECT["id"]).manifest().get(str(D.activity_id(next(iter(D.days_in(s2, e1)))))), (jab.get("error"), sorted(os.listdir(_udir))))

# a dataset asked for that gave no file is said on the result (2026-10-29, Palo: one went missing on a live load, unexplained)
class _Fail500(_R):
    def __init__(self): super().__init__({}, 500)
_orig_get = SESSION.get
def _get_wellness_fails(url, params=None, timeout=None):
    if url.split("/api/v1")[-1] == "/athlete/0/wellness":
        SESSION.calls.append("/athlete/0/wellness"); return _Fail500()
    return _orig_get(url, params=params, timeout=timeout)
SESSION.get = _get_wellness_fails
try:
    jwf = load(s2, e1, aux=("summary", "wellness"))
finally:
    SESSION.get = _orig_get
rwf = jwf.get("result") or {}
check("the wellness call failing: the file is still written from the days the store holds, and the result's warnings say the call failed and that the days held stand; nothing else is said",
      jwf["status"] == "completed" and any("wellness_data_" in p_ for p_ in rwf.get("aux_datasets", [])) and len(rwf.get("warnings", [])) == 1 and "could not be fetched" in rwf["warnings"][0] and "days held from earlier loads stand" in rwf["warnings"][0], (jwf.get("error"), rwf.get("warnings")))
check("a load with every dataset says nothing is missing: no warnings", (load(s1, e1, aux=("summary", "intervals", "wellness", "context", "rider")).get("result") or {}).get("warnings") == [])

# a load from the store alone (2026-10-29, the Dataset cache dialog's Load): nothing is fetched - the activity list's entries the
# store kept, the files, the laps, the chats, the wellness log, the calendar and the newest profile all come from the store
_entries = S.Store(_udir, "intervals/" + D.SUBJECT["id"]).feed("entries").span()
check("every online load keeps the activity list's entries in the store, by id with the day", _entries["count"] >= len(D.activities(s2, e1)) and _entries["from"] <= s2, _entries)
_fits_all, _calls_all = len(SESSION.fits()), len(SESSION.calls)
joff = load(s2, e1, aux=("summary", "intervals", "wellness", "context", "rider"), from_store=True, folder="intervals/" + D.SUBJECT["id"])
roff = joff.get("result") or {}
_names_off = sorted(os.path.basename(p_) for p_ in roff.get("aux_datasets", []))
check("from the store alone: the load completes without one call to the API; the frame is the window's; every file is written - summary, intervals, wellness, context, plan, rider, zones; the chats come from the store whatever the activity's age; the result says offline and that nothing was fetched; no warning",
      joff["status"] == "completed" and SESSION.calls == [] and E.df_cache.get(roff["df_id"]).activity_id.nunique() == len(D.activities(s2, e1))
      and _names_off == sorted(f"{k}_{s2.replace('-', '')}_to_{e1.replace('-', '')}.csv" for k in ("activity_summary", "activity_intervals", "wellness_data", "context_notes", "planned_workouts", "rider_profile", "custom_zone_times"))
      and roff["store"]["offline"] is True and roff["store"]["fetched"] == 0 and roff["store"]["held"] == len(D.activities(s2, e1)) and roff["store"]["laps"]["fetched"] == 0
      and roff["context"]["calls"] == 0 and roff["context"]["messages_reused"] == sum(1 for d in D.days_in(s2, e1) if D.has_chat(d)) and roff.get("warnings") == [],
      (joff.get("error"), SESSION.calls[:5], _names_off, roff.get("store", {}).get("laps"), roff.get("context"), roff.get("warnings")))
_ctx_off = pd.read_csv(roff["context"]["path"], dtype=str, keep_default_na=False)
check("from the store alone, the context has the chats' messages and the coaches told apart by the record (kept by the online loads)",
      (_ctx_off.kind == "activity_message").sum() > 0 and (_ctx_off.author_role == "coach").sum() > 0 and S.athlete_record(_udir, "intervals/" + D.SUBJECT["id"]).get("coaches"), (_ctx_off.author_role.value_counts().to_dict(), S.athlete_record(_udir, "intervals/" + D.SUBJECT["id"]).get("coaches")))
_old_span_s = (TODAY - timedelta(days=300)).isoformat(); _old_span_e = (TODAY - timedelta(days=290)).isoformat()
joff2 = load(_old_span_s, _old_span_e, aux=("summary",), from_store=True, folder="intervals/" + D.SUBJECT["id"])
roff2 = joff2.get("result") or {}
check("from the store alone over a span the store never held: the activity list is fetched this once and kept (the one call), but the files are not - the load says the store holds none of them and points to the Intervals.icu dialog",
      joff2["status"] == "error" and "holds none of the" in joff2["error"] and "Intervals.icu dialog" in joff2["error"] and SESSION.calls == ["/athlete/0/activities"]
      and S.Store(_udir, "intervals/" + D.SUBJECT["id"]).feed("entries").within(_old_span_s, _old_span_e), (joff2.get("error"), SESSION.calls[:5]))
joff3 = load(s2, e1, aux=("summary",), from_store=True, folder="intervals/nothere")
check("from the store alone for an athlete nothing is held for: refused with a plain sentence", joff3["status"] == "error" and "Nothing is held" in joff3["error"], joff3)

# a load of one dataset alone (2026-10-29, the dialog's Load <dataset>): `with_frame` off - the frame is not touched (nothing
# downloaded, assembled or cached), only the files asked for are written; the result says so and names the kinds asked
_cached_before = sorted(m["df_id"] for m in E.df_cache.get_all_metadata())
_kinds_before = S.athlete_record(_udir, "intervals/" + D.SUBJECT["id"]).get("kinds")
jone = load(s2, e1, aux=("wellness",), from_store=True, folder="intervals/" + D.SUBJECT["id"], with_frame=False, df_id="df-one-alone")
rone = jone.get("result") or {}
check("one dataset alone, from the store: the wellness file alone is written, no call made, no frame cached (the df_id asked is not in the cache, the result's is None), the result says frame off with the kinds asked, the store's account carries no window; the record's last-load kinds are not touched",
      jone["status"] == "completed" and SESSION.calls == [] and [os.path.basename(p_)[:13] for p_ in rone.get("aux_datasets", [])] == ["wellness_data"] and rone.get("frame") is False and rone.get("kinds") == ["wellness"]
      and rone.get("df_id") is None and sorted(m["df_id"] for m in E.df_cache.get_all_metadata()) == _cached_before and "df-one-alone" not in _cached_before and rone["store"]["window"] == 0 and rone["store"]["offline"] is True
      and S.athlete_record(_udir, "intervals/" + D.SUBJECT["id"]).get("kinds") == _kinds_before, (jone.get("error"), SESSION.calls[:5], rone.get("aux_datasets"), rone.get("frame"), rone.get("kinds"), rone.get("store", {}).get("window")))
_laps_before_one = len(os.listdir(_me.laps_dir))
jone2 = load(s2, TODAY.isoformat(), aux=("intervals",), with_frame=False, df_id="df-one-online")
rone2 = jone2.get("result") or {}
check("one dataset alone, to today through Intervals.icu: the list, the profile and the laps of the days the store lacks are fetched, no file downloaded (no FIT call), no frame cached, the intervals file alone written for the span",
      jone2["status"] == "completed" and SESSION.fits() == [] and "/athlete/0/activities" in SESSION.calls and len(SESSION.laps()) > 0 and len(os.listdir(_me.laps_dir)) > _laps_before_one
      and [os.path.basename(p_)[:18] for p_ in rone2.get("aux_datasets", [])] == ["activity_intervals"] and rone2.get("frame") is False and "df-one-online" not in [m["df_id"] for m in E.df_cache.get_all_metadata()]
      and rone2["store"]["laps"]["fetched"] > 0, (jone2.get("error"), SESSION.fits()[:3], len(SESSION.laps()), rone2.get("aux_datasets")))
jone3 = load(s2, e1, aux=("context", "plan", "rider"), from_store=True, folder="intervals/" + D.SUBJECT["id"], with_frame=False, df_id="df-one-ctx")
rone3 = jone3.get("result") or {}
check("the context alone, from the store: the context, plan, rider and zones files written without the frame, the coaches told apart, no call",
      jone3["status"] == "completed" and SESSION.calls == [] and sorted(os.path.basename(p_).split("_2")[0] for p_ in rone3.get("aux_datasets", [])) == ["context_notes", "custom_zone_times", "planned_workouts", "rider_profile"]
      and rone3.get("frame") is False and rone3["context"]["calls"] == 0, (jone3.get("error"), rone3.get("aux_datasets")))

# earlier loads leave on the first start after the upgrade (2026-10-29): a mark folder, "unmarked", and the loader's files at the
# user's folder itself go; uploads, the athletes' folders and the app's own folders stay
_pu = os.path.join(WORK, "purge")
for _d in ("u1/abcdef012345/store/activities", "u1/unmarked/store", "u1/intervals/i9/views", "u1/generated", "u1/routines", "u2/0123456789ab", "u2/endura/x"):
    os.makedirs(os.path.join(_pu, _d), exist_ok=True)
for _f in ("u1/abcdef012345/store/activities.json", "u1/activity_summary_20250101_to_20250201.csv", "u1/wellness_data_20250101_to_20250201.csv", "u1/my_upload.csv", "u1/generated/out.csv",
           "u1/intervals/i9/subject.json", "u1/intervals/i9/views/activity_summary_20260101_to_20260201.csv", "u2/0123456789ab/x.csv", "u2/race_turns_race_2.csv"):
    open(os.path.join(_pu, _f), "w").write("x\n")
_gone = S.purge_earlier_loads(_pu)
check("purge_earlier_loads: the mark folders and 'unmarked' go with everything in them, the loader's window files at the user's folder go; the upload, the Endura race file, the athlete's folder with its views, generated and routines stay; what went is named; nothing to do the second time or without the root",
      sorted(_gone) == ["u1/abcdef012345/", "u1/activity_summary_20250101_to_20250201.csv", "u1/unmarked/", "u1/wellness_data_20250101_to_20250201.csv", "u2/0123456789ab/"]
      and sorted(os.listdir(os.path.join(_pu, "u1"))) == ["generated", "intervals", "my_upload.csv", "routines"] and sorted(os.listdir(os.path.join(_pu, "u2"))) == ["endura", "race_turns_race_2.csv"]
      and os.path.isfile(os.path.join(_pu, "u1/intervals/i9/views/activity_summary_20260101_to_20260201.csv")) and S.purge_earlier_loads(_pu) == [] and S.purge_earlier_loads(os.path.join(WORK, "nowhere")) == [],
      (_gone, sorted(os.listdir(os.path.join(_pu, "u1"))), sorted(os.listdir(os.path.join(_pu, "u2")))))
check("the executor runs the purge at start, over its datasets folder (the module says what went)", "purge_earlier_loads('datasets')" in open(os.path.join(ROOT, "containers", "executor", "code_executor_api.py"), encoding="utf-8").read())
# the small calls wait out a rate limit (2026-10-29: the wellness call of a live load failed after a thousand calls)
class _Limited:
    def __init__(self, fails): self.fails, self.n = fails, 0
    def get(self, url, params=None, timeout=None):
        self.n += 1
        if self.n <= self.fails:
            r = _R({}, 429); r.headers = {"Retry-After": "0"}; return r
        r = _R([{"id": "2026-01-01", "weight": 70}]); r.headers = {}; return r
_lim = _Limited(2)
_t0 = time.time()
_recs, _failed = E.fetch_wellness_records(_lim, "http://icu/api/v1", "2026-01-01", "2026-01-02")
check("get_with_retry: a 429 is waited out (Retry-After honoured, two retries) and the records come on the third try; a limit that does not lift is the failure it was",
      _recs == [{"id": "2026-01-01", "weight": 70}] and _failed == "" and _lim.n == 3 and E.fetch_wellness_records(_Limited(9), "http://icu/api/v1", "2026-01-01", "2026-01-02")[1] != "", (_recs, _failed, _lim.n))

# the views' age: a window file not written within a month leaves at the end of a load; a fresh one stays
_pv = os.path.join(_udir, "intervals", "pv", "views"); os.makedirs(_pv, exist_ok=True)
open(os.path.join(_pv, "wellness_data_20260101_to_20260131.csv"), "w").write("date\n"); open(os.path.join(_pv, "activity_summary_20261001_to_20261029.csv"), "w").write("id\n")
os.utime(os.path.join(_pv, "wellness_data_20260101_to_20260131.csv"), (time.time() - 40 * 86400, time.time() - 40 * 86400))
check("prune_views: the file older than a month goes, the fresh one stays; a folder without views is nothing",
      S.prune_views(_udir, "intervals/pv") == 1 and sorted(os.listdir(_pv)) == ["activity_summary_20261001_to_20261029.csv"] and S.prune_views(_udir, "intervals/none") == 0)
jv = load(s1, e1)
check("a load prunes its athlete's old views: the window just written stays (the loader writes it fresh)", jv["status"] == "completed" and all(os.path.isfile(p_) for p_ in (jv.get("result") or {}).get("aux_datasets", [])), jv.get("error"))

fails = [n for n, ok in results if not ok]
print(f"\n{len(results) - len(fails)} passed, {len(fails)} failed")
sys.exit(1 if fails else 0)
