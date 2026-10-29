"""The Intervals.icu store (2026-10-15, docs/INCREMENTAL_LOADS_DESIGN.md; by athlete and by feed since 2026-10-29,
docs/DATASETS_DESIGN.md): what a load fetched, kept by what it is rather than by window, under the athlete's folder on
the executor's disk (datasets/<user>/<source>/<athlete id>/store/) - one file per activity's second-by-second rows, the
chat and the laps under each activity, a manifest; the wellness log by day, the calendar by entry, the profile as dated
snapshots. A window is then a view: the loader fetches the window's activity list (the manifest of what Intervals
holds), takes from the store every activity it already has whose file has not changed, downloads only the rest, and
assembles the frame from the store. The wellness log and the calendar are fetched fresh each load (one call each) and
merged, so the store's span is the union of every load; the chat and the laps under an activity are fetched again while
the activity is recent or changed, and reused for older ones. The window's files (the summary, wellness, laps, context,
plan and profile files the analysis reads) are written from the store under the athlete's views/ folder.

The files are parquet (compressed; a year of second-by-second data is a tenth of its CSV size). Where pandas has no parquet
engine - the test sandbox - the same frames go to compressed pickles under another extension; the real image carries pyarrow.
"""
import gzip
import hashlib
import json
import os
import re
import time
from datetime import date, timedelta
from typing import Dict, Iterable, List, Optional, Tuple

import pandas as pd

STORE_DIR = "store"
VIEWS_DIR = "views"            # the window's files, beside the store under the athlete's folder (2026-10-29)
MANIFEST = "activities.json"
# the fields of an activity's list entry that change when its file changes (a re-sync, a re-upload, a different
# recording): the detail rows are fetched again when any of them differs from the stored signature
DETAIL_SIGNATURE = ("icu_sync_date", "file_type", "start_date_local", "elapsed_time", "moving_time", "distance")
MESSAGES_FRESH_DAYS = 60       # the chat under an activity started within this many days is fetched again each load
LAPS_FRESH_DAYS = 60           # the laps too: their labels, RPE and lactate are typed in after the sync, without the file changing
RETENTION_DAYS = 400           # activities started earlier than this many days ago leave the store when a load ends...
USED_DAYS = 30                 # ...unless a load served them within this many days (a routine over an old window keeps its data)
ENGINE_WHEN_NO_PARQUET = "pickle"
FEEDS = ("wellness", "events", "entries")   # the feeds kept by day or by entry in one file each (<feed>.json): the wellness log, the
                                             # calendar, and the activity list's entries (2026-10-29: what a load from the store alone starts from)


def _have_parquet() -> bool:
    try:
        import pyarrow                                         # noqa: F401
        return isinstance(getattr(pyarrow, "__version__", None), str)
    except Exception:                                          # noqa: BLE001
        pass
    try:
        import fastparquet                                     # noqa: F401
        return True
    except Exception:                                          # noqa: BLE001
        return False


HAVE_PARQUET = _have_parquet()


def signature_of(entry: dict) -> str:
    """The detail signature of an activity's list entry: a hash of the fields that change when its file does."""
    parts = [str((entry or {}).get(k, "")) for k in DETAIL_SIGNATURE]
    return hashlib.sha1("|".join(parts).encode("utf-8")).hexdigest()[:16]


def _day_of(entry: dict) -> Optional[date]:
    s = str((entry or {}).get("start_date_local") or "")[:10]
    try:
        return date.fromisoformat(s)
    except ValueError:
        return None


class Store:
    """One key's store on disk. Cheap to construct; the manifest is read once and written when it changes."""

    def __init__(self, user_dir: str, mark: str):
        # `mark`: the load's folder relative to the user's - <source>/<athlete id> since 2026-10-29, the key's mark before
        self.dir = os.path.join(user_dir, mark or "unmarked", STORE_DIR)
        self.activities_dir = os.path.join(self.dir, "activities")
        self.messages_dir = os.path.join(self.dir, "messages")
        self.laps_dir = os.path.join(self.dir, "laps")
        self.profile_dir = os.path.join(self.dir, "profile")
        self._manifest: Optional[Dict[str, dict]] = None
        self._dirty = False
        self._feeds: Dict[str, "Records"] = {}

    # ---------------------------------------------------------------- the manifest
    def manifest(self) -> Dict[str, dict]:
        if self._manifest is None:
            path = os.path.join(self.dir, MANIFEST)
            try:
                with open(path, encoding="utf-8") as fh:
                    m = json.load(fh)
                self._manifest = m if isinstance(m, dict) else {}
            except (OSError, ValueError):
                self._manifest = {}
        return self._manifest

    def save(self) -> None:
        for feed in self._feeds.values():
            feed.save()
        if not self._dirty:
            return
        os.makedirs(self.dir, exist_ok=True)
        tmp = os.path.join(self.dir, MANIFEST + ".tmp")
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump(self.manifest(), fh)
        os.replace(tmp, os.path.join(self.dir, MANIFEST))
        self._dirty = False

    # ---------------------------------------------------------------- the detail rows
    def _detail_path(self, activity_id, ext: Optional[str] = None) -> str:
        return os.path.join(self.activities_dir, f"{activity_id}.{ext or ('parquet' if HAVE_PARQUET else 'pkl.gz')}")

    def has_detail(self, entry: dict) -> bool:
        """Whether the store holds this activity's rows for the file Intervals has now."""
        aid = str((entry or {}).get("id") or "")
        rec = self.manifest().get(aid)
        if not rec or rec.get("signature") != signature_of(entry):
            return False
        return os.path.isfile(os.path.join(self.dir, rec.get("file") or ""))

    def put_detail(self, entry: dict, frame: pd.DataFrame) -> str:
        """Keep an activity's rows (every metric the file had); the manifest records the signature and the day."""
        aid = str((entry or {}).get("id") or "")
        os.makedirs(self.activities_dir, exist_ok=True)
        path = self._detail_path(aid)
        tmp = path + ".tmp"
        if HAVE_PARQUET:
            frame.to_parquet(tmp, index=False, compression="zstd")
        else:
            frame.to_pickle(tmp, compression="gzip")
        os.replace(tmp, path)
        rec = self.manifest().get(aid) or {}
        rec.update({"signature": signature_of(entry), "file": os.path.relpath(path, self.dir), "rows": int(len(frame)),
                    "day": str((entry or {}).get("start_date_local") or "")[:10], "fetched": time.time(),
                    "columns": [str(c) for c in frame.columns]})
        self.manifest()[aid] = rec
        self._dirty = True
        return path

    def get_detail(self, activity_id) -> Optional[pd.DataFrame]:
        rec = self.manifest().get(str(activity_id))
        if not rec:
            return None
        path = os.path.join(self.dir, rec.get("file") or "")
        try:
            if path.endswith(".parquet"):
                return pd.read_parquet(path)
            return pd.read_pickle(path, compression="gzip")
        except Exception:                                      # noqa: BLE001
            return None

    def assemble(self, entries: Iterable[dict], selected_metrics: Optional[Iterable[str]] = None) -> Tuple[pd.DataFrame, List[str]]:
        """The window's frame from the store: the rows of each entry's activity, in the entries' order, the activity's
        type and name as the list has them now, the columns cut to the metrics asked (every metric when none is).
        Returns (frame, the ids of entries the store could not serve)."""
        wanted = set(str(m) for m in (selected_metrics or []) if m)
        keep_always = {"activity_id", "datetime", "activity_type", "activity_name"}
        frames, missing = [], []
        for entry in entries or []:
            aid = str((entry or {}).get("id") or "")
            df = self.get_detail(aid) if aid else None
            if df is None:
                missing.append(aid)
                continue
            if wanted:
                df = df[[c for c in df.columns if c in keep_always or c in wanted]]
            df = df.copy()
            df["activity_type"] = (entry or {}).get("type", "Unknown")
            df["activity_name"] = (entry or {}).get("name", "Unnamed")
            frames.append(df)
            self.manifest()[aid]["used"] = time.time()           # served now: kept past the retention while in use
            self._dirty = True
        if not frames:
            return pd.DataFrame(), missing
        out = pd.concat(frames, ignore_index=True)
        if "datetime" in out.columns:
            out["datetime"] = pd.to_datetime(out["datetime"])
            out = out.sort_values("datetime", ascending=False).reset_index(drop=True)
        return out, missing

    # ---------------------------------------------------------------- the messages under an activity
    def _messages_path(self, activity_id) -> str:
        return os.path.join(self.messages_dir, f"{activity_id}.json")

    def messages_fresh(self, entry: dict, today: Optional[date] = None, fresh_days: int = MESSAGES_FRESH_DAYS) -> bool:
        """Whether the stored chat of this activity may stand for the live one: stored, the activity older than the fresh
        window (a recent activity's chat is still being written), and its file unchanged since (an edit or re-sync is a
        reason to look again)."""
        aid = str((entry or {}).get("id") or "")
        rec = self.manifest().get(aid) or {}
        if not rec.get("messages_fetched") or not os.path.isfile(self._messages_path(aid)):
            return False
        day = _day_of(entry)
        if day is None or (today or date.today()) - day <= timedelta(days=fresh_days):
            return False
        return rec.get("messages_signature") == signature_of(entry)

    def put_messages(self, entry: dict, messages: list) -> None:
        aid = str((entry or {}).get("id") or "")
        os.makedirs(self.messages_dir, exist_ok=True)
        path = self._messages_path(aid)
        tmp = path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump(messages, fh)
        os.replace(tmp, path)
        rec = self.manifest().get(aid) or {}
        rec.update({"messages_fetched": time.time(), "messages_signature": signature_of(entry), "messages": len(messages or []),
                    "day": rec.get("day") or str((entry or {}).get("start_date_local") or "")[:10]})
        self.manifest()[aid] = rec
        self._dirty = True

    def get_messages(self, activity_id) -> Optional[list]:
        try:
            with open(self._messages_path(activity_id), encoding="utf-8") as fh:
                m = json.load(fh)
            return m if isinstance(m, list) else None
        except (OSError, ValueError):
            return None

    # ---------------------------------------------------------------- the laps under an activity (2026-10-29)
    def _laps_path(self, activity_id) -> str:
        return os.path.join(self.laps_dir, f"{activity_id}.json.gz")

    def laps_fresh(self, entry: dict, today: Optional[date] = None, fresh_days: int = LAPS_FRESH_DAYS) -> bool:
        """Whether the stored laps of this activity may stand for the live ones - the same rule as the chat's: stored,
        the activity older than the fresh window (labels, RPE and lactate are typed in after the sync, without the
        file changing), and its file unchanged since."""
        aid = str((entry or {}).get("id") or "")
        rec = self.manifest().get(aid) or {}
        if not rec.get("laps_fetched") or not os.path.isfile(self._laps_path(aid)):
            return False
        day = _day_of(entry)
        if day is None or (today or date.today()) - day <= timedelta(days=fresh_days):
            return False
        return rec.get("laps_signature") == signature_of(entry)

    def put_laps(self, entry: dict, data: dict) -> None:
        """Keep an activity's laps as the API gave them (the intervals and the groups); the view is made from them."""
        aid = str((entry or {}).get("id") or "")
        os.makedirs(self.laps_dir, exist_ok=True)
        path = self._laps_path(aid)
        tmp = path + ".tmp"
        with gzip.open(tmp, "wt", encoding="utf-8") as fh:
            json.dump(data if isinstance(data, dict) else {}, fh)
        os.replace(tmp, path)
        rec = self.manifest().get(aid) or {}
        rec.update({"laps_fetched": time.time(), "laps_signature": signature_of(entry), "laps": len((data or {}).get("icu_intervals") or []) if isinstance(data, dict) else 0,
                    "day": rec.get("day") or str((entry or {}).get("start_date_local") or "")[:10]})
        self.manifest()[aid] = rec
        self._dirty = True

    def get_laps(self, activity_id) -> Optional[dict]:
        try:
            with gzip.open(self._laps_path(activity_id), "rt", encoding="utf-8") as fh:
                d = json.load(fh)
            return d if isinstance(d, dict) else None
        except (OSError, ValueError, EOFError):
            return None

    # ---------------------------------------------------------------- the feeds kept by day or by entry (2026-10-29)
    def feed(self, name: str) -> "Records":
        """The wellness log (a record per day, keyed by the day) or the calendar (a record per entry, keyed by its id)."""
        if name not in self._feeds:
            self._feeds[name] = Records(os.path.join(self.dir, f"{name}.json"))
        return self._feeds[name]

    # ---------------------------------------------------------------- the profile as dated snapshots (2026-10-29)
    def put_profile(self, athlete: dict, today: Optional[date] = None) -> bool:
        """Keep the record as fetched today, when it differs from the newest snapshot held; the day's own snapshot is
        replaced. Returns whether a snapshot was written."""
        if not isinstance(athlete, dict) or not athlete:
            return False
        day = (today or date.today()).isoformat()
        newest = self.newest_profile()
        if newest and newest[0] != day and json.dumps(newest[1], sort_keys=True) == json.dumps(athlete, sort_keys=True):
            return False
        os.makedirs(self.profile_dir, exist_ok=True)
        tmp = os.path.join(self.profile_dir, day + ".json.tmp")
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump(athlete, fh)
        os.replace(tmp, os.path.join(self.profile_dir, day + ".json"))
        return True

    def profile_days(self) -> List[str]:
        try:
            return sorted(f[:-5] for f in os.listdir(self.profile_dir) if f.endswith(".json"))
        except OSError:
            return []

    def newest_profile(self) -> Optional[Tuple[str, dict]]:
        """(the day, the record) of the newest snapshot, or None."""
        for day in reversed(self.profile_days()):
            try:
                with open(os.path.join(self.profile_dir, day + ".json"), encoding="utf-8") as fh:
                    rec = json.load(fh)
                if isinstance(rec, dict):
                    return day, rec
            except (OSError, ValueError):
                continue
        return None

    # ---------------------------------------------------------------- housekeeping and the account of it
    def prune(self, today: Optional[date] = None, days: int = RETENTION_DAYS, used_days: int = USED_DAYS, now: Optional[float] = None) -> int:
        """Drop activities started earlier than `days` ago (their rows, chat and laps) that no load served within
        `used_days`, the feeds' records of such days, and profile snapshots that old but the newest; returns how many
        activities went. One rule across the feeds (docs/DATASETS_DESIGN.md §7)."""
        cutoff = (today or date.today()) - timedelta(days=days)
        now = time.time() if now is None else now
        gone = 0
        for aid, rec in list(self.manifest().items()):
            try:
                day = date.fromisoformat(str(rec.get("day") or "")[:10])
            except ValueError:
                continue
            if day >= cutoff or now - float(rec.get("used") or 0) <= used_days * 86400:
                continue
            for p in (os.path.join(self.dir, rec.get("file") or "__none__"), self._messages_path(aid), self._laps_path(aid)):
                try:
                    os.remove(p)
                except OSError:
                    pass
            del self.manifest()[aid]
            self._dirty = True
            gone += 1
        for name in FEEDS:
            if os.path.isfile(os.path.join(self.dir, f"{name}.json")) or name in self._feeds:
                self.feed(name).prune(cutoff, used_days=used_days, now=now)
        for day in self.profile_days()[:-1]:
            try:
                if date.fromisoformat(day) < cutoff:
                    os.remove(os.path.join(self.profile_dir, day + ".json"))
            except (ValueError, OSError):
                pass
        return gone

    def summary(self) -> dict:
        """What the store holds, for the cache listing and the dialogs: activities, chats and laps with the span of
        their days, each feed's span and count, the profile's newest day, the size - whole and by part (the tree
        shows each feed's), and when each was last served."""
        m = self.manifest()
        days = sorted(str(r.get("day") or "")[:10] for r in m.values() if r.get("day"))
        laps_days = sorted(str(r.get("day") or "")[:10] for r in m.values() if r.get("laps_fetched") and r.get("day"))
        chat_days = sorted(str(r.get("day") or "")[:10] for r in m.values() if r.get("messages_fetched") and r.get("day"))
        columns: List[str] = []
        for r in m.values():
            for c in r.get("columns") or []:
                if c not in columns:
                    columns.append(str(c))
        size, parts = 0, {}
        for root, _dirs, files in os.walk(self.dir) if os.path.isdir(self.dir) else []:
            for f in files:
                try:
                    n = os.path.getsize(os.path.join(root, f))
                except OSError:
                    continue
                size += n
                rel = os.path.relpath(os.path.join(root, f), self.dir).replace("\\", "/")
                part = rel.split("/")[0] if "/" in rel else rel.split(".")[0]
                parts[part] = parts.get(part, 0) + n
        feeds = {}
        for name in FEEDS:
            if os.path.isfile(os.path.join(self.dir, f"{name}.json")) or name in self._feeds:
                feeds[name] = dict(self.feed(name).span(), bytes=parts.get(name, 0), last_used=self.feed(name).last_used(), **(self.feed(name).facts() if name != "entries" else {}))
        pdays = self.profile_days()
        used = [float(r.get("used") or 0) for r in m.values() if r.get("used")]
        return {"activities": sum(1 for r in m.values() if r.get("file")), "chats": sum(1 for r in m.values() if r.get("messages_fetched")),
                "chats_from": chat_days[0] if chat_days else "", "chats_to": chat_days[-1] if chat_days else "", "messages": sum(int(r.get("messages") or 0) for r in m.values()),
                "laps": sum(1 for r in m.values() if r.get("laps_fetched")), "laps_from": laps_days[0] if laps_days else "", "laps_to": laps_days[-1] if laps_days else "",
                "lap_rows": sum(int(r.get("laps") or 0) for r in m.values()), "columns": columns,
                "from": days[0] if days else "", "to": days[-1] if days else "", "bytes": size, "size_mb": round(size / (1024 * 1024), 2),
                "parts": parts, "last_used": max(used) if used else None,
                "feeds": feeds, "profile": {"as_of": pdays[-1] if pdays else "", "snapshots": len(pdays), "bytes": parts.get("profile", 0)},
                "engine": "parquet" if HAVE_PARQUET else ENGINE_WHEN_NO_PARQUET}


class Records:
    """A feed's records in one JSON file, each under its key with the day it belongs to and when it was fetched and
    last served: the wellness log by day, the calendar by entry (2026-10-29, docs/DATASETS_DESIGN.md §3). A load merges
    the window it fetched: the window's records are replaced by what came down (a day corrected at the source is
    corrected here, an entry deleted there goes here), the rest stay, so the span held is the union of every load."""

    def __init__(self, path: str):
        self.path = path
        self._recs: Optional[Dict[str, dict]] = None
        self._dirty = False

    def records(self) -> Dict[str, dict]:
        if self._recs is None:
            try:
                with open(self.path, encoding="utf-8") as fh:
                    d = json.load(fh)
                self._recs = d if isinstance(d, dict) else {}
            except (OSError, ValueError):
                self._recs = {}
        return self._recs

    def save(self) -> None:
        if not self._dirty:
            return
        os.makedirs(os.path.dirname(self.path), exist_ok=True)
        tmp = self.path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump(self.records(), fh)
        os.replace(tmp, self.path)
        self._dirty = False

    def merge(self, fetched: Iterable[dict], key_of, day_of, start: str, end: str, now: Optional[float] = None) -> dict:
        """Merge the window's records as fetched: `key_of(record)` its key, `day_of(record)` its day (YYYY-MM-DD).
        Returns {"added", "updated", "removed", "held"} - held: the window's records already there and unchanged."""
        now = time.time() if now is None else now
        recs = self.records()
        seen, out = set(), {"added": 0, "updated": 0, "removed": 0, "held": 0}
        for r in fetched or []:
            if not isinstance(r, dict):
                continue
            k, d = str(key_of(r) or ""), str(day_of(r) or "")[:10]
            if not k:
                continue
            seen.add(k)
            old = recs.get(k)
            if old is None:
                out["added"] += 1
            elif old.get("r") != r:
                out["updated"] += 1
            else:
                out["held"] += 1
                old["u"] = now
                continue
            recs[k] = {"r": r, "day": d, "f": now, "u": now}
        for k, rec in list(recs.items()):
            if k not in seen and start <= str(rec.get("day") or "") <= end:
                del recs[k]
                out["removed"] += 1
        self._dirty = True
        return out

    def within(self, start: str, end: str, mark_used: bool = True, now: Optional[float] = None) -> List[dict]:
        """The window's records, by day then key."""
        now = time.time() if now is None else now
        out = []
        for k, rec in self.records().items():
            if start <= str(rec.get("day") or "") <= end:
                out.append((str(rec.get("day") or ""), k, rec))
                if mark_used:
                    rec["u"] = now
                    self._dirty = True
        return [rec["r"] for _d, _k, rec in sorted(out, key=lambda t: (t[0], t[1]))]

    def span(self) -> dict:
        days = sorted(str(r.get("day") or "") for r in self.records().values() if r.get("day"))
        return {"from": days[0] if days else "", "to": days[-1] if days else "", "count": len(self.records())}

    def last_used(self) -> Optional[float]:
        used = [float(r.get("u") or 0) for r in self.records().values() if r.get("u")]
        return max(used) if used else None

    def facts(self) -> dict:
        """What the records carry, for the dialog's details: the keys seen across them (the wellness log's columns) and,
        for records with a category (the calendar), how many of each."""
        keys: List[str] = []
        cats: Dict[str, int] = {}
        for rec in self.records().values():
            r = rec.get("r") or {}
            if isinstance(r, dict):
                for k in r:
                    if k not in keys:
                        keys.append(str(k))
                if "category" in r:
                    c = str(r.get("category") or "")
                    cats[c] = cats.get(c, 0) + 1
        out: dict = {"columns": keys}
        if cats:
            out["categories"] = cats
        return out

    def prune(self, cutoff: date, used_days: int = USED_DAYS, now: Optional[float] = None) -> int:
        now = time.time() if now is None else now
        gone = 0
        for k, rec in list(self.records().items()):
            try:
                day = date.fromisoformat(str(rec.get("day") or "")[:10])
            except ValueError:
                continue
            if day < cutoff and now - float(rec.get("u") or 0) > used_days * 86400:
                del self.records()[k]
                gone += 1
        if gone:
            self._dirty = True
        return gone


# ---- the athlete's folder (2026-10-29, docs/DATASETS_DESIGN.md §2): datasets/<user>/<source>/<athlete id>/ -----------
# A load is identified by the source's athlete id, learnt from the profile call; the key's mark named the folder until
# then and stays only as a credential's fingerprint. The athlete's record (subject.json - "the subject" is the word the
# app uses) keeps the id, the name the profile gave, the marks that have loaded this athlete, and when.
ATHLETE_RECORD = "subject.json"
SOURCES = ("intervals", "endura", "sweatstack")
APP_FOLDERS = ("generated", "routines", "documents")     # the app's own folders under a user's: never a load's


def athlete_rel(source: str, athlete_id: str, mark: str) -> str:
    """The folder of a load, relative to the user's datasets folder: <source>/<athlete id> when the id is known, else
    the key's mark as before (the profile call failed, or an older executor's load)."""
    aid = str(athlete_id or "").strip().replace("/", "_").replace("\\", "_")
    return f"{source}/{aid}" if aid else (mark or "unmarked")


def athlete_record(user_dir: str, rel: str) -> dict:
    """The athlete's record under the folder, {} when there is none."""
    try:
        with open(os.path.join(user_dir, rel, ATHLETE_RECORD), encoding="utf-8") as fh:
            rec = json.load(fh)
        return rec if isinstance(rec, dict) else {}
    except (OSError, ValueError):
        return {}


def remember_athlete(user_dir: str, rel: str, source: str, athlete_id: str, name: str, mark: str, now: Optional[float] = None,
                     kinds: Optional[Iterable[str]] = None) -> dict:
    """Write or update the athlete's record: the id and name, the marks that have loaded this athlete (the newest last),
    first seen and last load, and the datasets the last load asked for (`kinds`, as the load dialog names them: what
    the dialog's Load asks for again)."""
    now = time.time() if now is None else now
    rec = athlete_record(user_dir, rel)
    marks = [m for m in (rec.get("marks") or []) if m and m != mark] + ([mark] if mark else [])
    rec.update({"source": source, "id": str(athlete_id), "name": str(name or rec.get("name") or ""), "marks": marks,
                "first_seen": rec.get("first_seen") or now, "last_load": now})
    if kinds is not None:
        rec["kinds"] = [str(k) for k in kinds]
    os.makedirs(os.path.join(user_dir, rel), exist_ok=True)
    tmp = os.path.join(user_dir, rel, ATHLETE_RECORD + ".tmp")
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(rec, fh, indent=1)
    os.replace(tmp, os.path.join(user_dir, rel, ATHLETE_RECORD))
    return rec


def update_record(user_dir: str, rel: str, **fields) -> dict:
    """Put fields on the athlete's record (the coaches' ids a load learnt, say); nothing else changes."""
    rec = athlete_record(user_dir, rel)
    if not rec:
        return rec
    rec.update(fields)
    tmp = os.path.join(user_dir, rel, ATHLETE_RECORD + ".tmp")
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(rec, fh, indent=1)
    os.replace(tmp, os.path.join(user_dir, rel, ATHLETE_RECORD))
    return rec


def adopt_mark_folder(user_dir: str, mark: str, rel: str) -> dict:
    """The migration (docs/DATASETS_DESIGN.md §9): what a key's mark folder holds moves under the athlete's folder the
    first time the athlete is known. A folder that does not exist yet is the mark folder renamed; one that does
    absorbs the mark folder's window files (kept when absent) and its store (each activity and chat the athlete's
    store lacks, with its manifest entry), then the mark folder goes. Returns what was moved; {} when there was
    nothing to move. Nothing is downloaded again."""
    src = os.path.join(user_dir, mark) if mark else ""
    dst = os.path.join(user_dir, rel)
    if not mark or not os.path.isdir(src) or os.path.normpath(src) == os.path.normpath(dst):
        return {}
    if not os.path.isdir(dst):
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        os.rename(src, dst)
        return {"renamed": True, "files": 0, "activities": 0}
    moved = {"renamed": False, "files": 0, "activities": 0}
    for name in os.listdir(src):
        p = os.path.join(src, name)
        if os.path.isfile(p) and not os.path.exists(os.path.join(dst, name)):
            os.replace(p, os.path.join(dst, name))
            moved["files"] += 1
    old, new = Store(user_dir, mark), Store(user_dir, rel)
    if os.path.isdir(old.dir):
        om, nm = old.manifest(), new.manifest()
        for aid, entry in om.items():
            if aid in nm:
                continue                                       # the athlete's store has it already: the newer load wins
            kept = dict(entry)
            rel_file = entry.get("file") or ""
            if rel_file and os.path.isfile(os.path.join(old.dir, rel_file)):
                os.makedirs(os.path.dirname(os.path.join(new.dir, rel_file)), exist_ok=True)
                os.replace(os.path.join(old.dir, rel_file), os.path.join(new.dir, rel_file))
            else:
                kept.pop("file", None); kept.pop("signature", None)
            if os.path.isfile(old._messages_path(aid)):
                os.makedirs(new.messages_dir, exist_ok=True)
                os.replace(old._messages_path(aid), new._messages_path(aid))
            else:
                kept.pop("messages_fetched", None); kept.pop("messages_signature", None)
            if os.path.isfile(old._laps_path(aid)):
                os.makedirs(new.laps_dir, exist_ok=True)
                os.replace(old._laps_path(aid), new._laps_path(aid))
            else:
                kept.pop("laps_fetched", None); kept.pop("laps_signature", None)
            nm[aid] = kept
            moved["activities"] += 1
        for name in FEEDS:                                     # a feed's records the athlete's store lacks
            if os.path.isfile(os.path.join(old.dir, f"{name}.json")):
                target = new.feed(name).records()
                for k, rec in old.feed(name).records().items():
                    if k not in target:
                        target[k] = rec
                        new.feed(name)._dirty = True
        for day in old.profile_days():
            if day not in new.profile_days():
                os.makedirs(new.profile_dir, exist_ok=True)
                os.replace(os.path.join(old.profile_dir, day + ".json"), os.path.join(new.profile_dir, day + ".json"))
        new._dirty = True
        new.save()
    import shutil
    shutil.rmtree(src, ignore_errors=True)
    return moved


def views_rel(rel: str) -> str:
    """The folder of a load's window files, relative to the user's: the athlete's views/ (2026-10-29)."""
    return f"{rel}/{VIEWS_DIR}" if rel else VIEWS_DIR


LOADER_PREFIXES = ("activity_summary_", "wellness_data_", "activity_intervals_", "context_notes_", "context_codes_", "planned_workouts_",
                   "rider_profile_", "custom_zone_times_")                                   # the Intervals loader's window files
ENDURA_PREFIXES = ("athlete_profiles_race_", "race_turns_race_", "race_climbs_race_", "race_waymarkers_race_")
# The dataset lines of an athlete (2026-10-29, the dialog redesigned): exactly the datasets the Intervals.icu dialog offers,
# plus the frame - and the window files a load writes from each (the prefix; the executor supplies the columns of each).
# The calendar sits inside Context, as it does in the dialog (the planned workouts file rides along).
FEED_ORDER = ("activities", "summary", "laps", "wellness", "context", "profile")
LINE_FILES = {"activities": (), "summary": ("activity_summary",), "laps": ("activity_intervals",), "wellness": ("wellness_data",),
              "context": ("context_notes", "planned_workouts", "context_codes"), "profile": ("rider_profile", "custom_zone_times")}


def _line_files(sm: dict, feed: str) -> List[dict]:
    cols = sm.get("columns_of") or {}
    return [{"file": p + "_<window>.csv", "columns": list(cols.get(p) or [])} for p in LINE_FILES.get(feed, ())]


def feeds_of(summary: dict) -> List[dict]:
    """The dataset lines of a store's summary, for the tree - one per dataset the load dialog offers, named as there,
    plus the frame (activities: the second-by-second files; summary: the activity list's entries, one row each; laps:
    the activity intervals; wellness; context: the chats and the calendar; profile: the rider profile and zones) - each
    with its span, count, size, last use, what it holds, and the files a load writes from it with their columns
    (`columns_of` on the summary, by file prefix, from the executor); only the datasets held."""
    sm = summary or {}
    parts = sm.get("parts") or {}
    feeds = sm.get("feeds") or {}
    out = []
    if sm.get("activities"):
        out.append({"feed": "activities", "from": sm.get("from", ""), "to": sm.get("to", ""), "count": sm.get("activities", 0),
                    "bytes": parts.get("activities", 0), "last_used": sm.get("last_used"), "columns": sm.get("columns") or [], "files": []})
    f = feeds.get("entries")
    if f and f.get("count"):
        out.append({"feed": "summary", "from": f.get("from", ""), "to": f.get("to", ""), "count": f.get("count", 0), "bytes": f.get("bytes", 0), "last_used": f.get("last_used"),
                    "files": _line_files(sm, "summary")})
    if sm.get("laps"):
        out.append({"feed": "laps", "from": sm.get("laps_from", ""), "to": sm.get("laps_to", ""), "count": sm.get("laps", 0), "rows": sm.get("lap_rows", 0),
                    "bytes": parts.get("laps", 0), "last_used": sm.get("last_used"), "files": _line_files(sm, "laps")})
    f = feeds.get("wellness")
    if f and f.get("count"):
        files = _line_files(sm, "wellness")
        if not files[0]["columns"]:
            files[0]["columns"] = ["date" if c == "id" else c for c in f.get("columns") or []]      # as the file names the day
        out.append({"feed": "wellness", "from": f.get("from", ""), "to": f.get("to", ""), "count": f.get("count", 0), "bytes": f.get("bytes", 0), "last_used": f.get("last_used"), "files": files})
    ev = feeds.get("events") or {}
    if sm.get("chats") or ev.get("count"):
        days = [d for d in (sm.get("chats_from"), sm.get("chats_to"), ev.get("from"), ev.get("to")) if d]
        used = [u for u in (sm.get("last_used"), ev.get("last_used")) if u]
        out.append({"feed": "context", "from": min(days) if days else "", "to": max(days) if days else "", "count": sm.get("chats", 0), "rows": sm.get("messages", 0),
                    "entries": ev.get("count", 0), "categories": ev.get("categories") or {}, "bytes": parts.get("messages", 0) + ev.get("bytes", 0),
                    "last_used": max(used) if used else None, "files": _line_files(sm, "context")})
    pf = sm.get("profile") or {}
    if pf.get("snapshots"):
        out.append({"feed": "profile", "as_of": pf.get("as_of", ""), "count": pf.get("snapshots", 0), "bytes": pf.get("bytes", 0), "files": _line_files(sm, "profile")})
    return out


def purge_earlier_loads(datasets_root: str) -> List[str]:
    """Earlier loads leave the system on the executor's first start after the upgrade (2026-10-29, the product owner:
    not consolidated, not listed - deleted): under every user's folder, each folder of a load from before the athlete
    was known (a key's mark, or "unmarked") and each window file an older executor wrote at the user's folder itself.
    Uploads, the athletes' folders and the app's own folders stay. Returns what went, as paths relative to the root."""
    import shutil
    gone: List[str] = []
    if not os.path.isdir(datasets_root):
        return gone
    for user in sorted(os.listdir(datasets_root)):
        udir = os.path.join(datasets_root, user)
        if not os.path.isdir(udir):
            continue
        for name in sorted(os.listdir(udir)):
            p = os.path.join(udir, name)
            try:
                if os.path.isdir(p) and name not in SOURCES and name not in APP_FOLDERS and (re.fullmatch(r"[0-9a-f]{12}", name) or name == "unmarked"):
                    shutil.rmtree(p, ignore_errors=True)
                    gone.append(f"{user}/{name}/")
                elif os.path.isfile(p) and name.startswith(LOADER_PREFIXES):
                    os.remove(p)
                    gone.append(f"{user}/{name}")
            except OSError:
                pass
    return gone


def absorb_mark_folders(user_dir: str, rel: str) -> List[str]:
    """Mark folders from before the athlete was known whose store holds an activity the athlete's store holds too are
    the same athlete's (an activity id is the platform's, one per activity): each is absorbed into the athlete's
    folder (adopt_mark_folder), so nothing is listed twice and nothing is downloaded again. A mark folder with no
    activity in common stays as it is. Returns the marks absorbed."""
    mine = set(Store(user_dir, rel).manifest())
    done = []
    if not mine:
        return done
    for name, rec in athlete_folders(user_dir):
        if rec or "/" in name or name == rel:
            continue
        theirs = set(Store(user_dir, name).manifest())
        if theirs and theirs & mine:
            adopt_mark_folder(user_dir, name, rel)
            done.append(name)
    return done


def cache_tree(frames: Iterable[dict], files: Iterable[dict], stores: Iterable[dict], subjects: Iterable[dict]) -> dict:
    """The cache as the tree the Dataset cache dialog draws (docs/DATASETS_DESIGN.md §8, 2026-10-29): source → athlete →
    dataset, with the athlete's frames in memory under it; the window files are not listed (they are a run's inputs).
    Endura and SweatStack carry their frames (and Endura its race files); uploads are the frames and files that belong
    to no loader. A folder that is no athlete's (a load whose profile call failed) is not listed: earlier loads are
    deleted at start (purge_earlier_loads), not shown."""
    frames = [f for f in frames or [] if isinstance(f, dict)]
    files = [f for f in files or [] if isinstance(f, dict)]
    stores_by = {str(s.get("folder") or ""): s for s in stores or [] if isinstance(s, dict)}

    def frame_entry(f):
        return {k: f.get(k) for k in ("df_id", "source", "date_range", "shape", "metrics", "memory_mb", "cached_at", "activities_count", "race_id", "race_title",
                                     "race_date", "original_filename", "folder", "key_mark", "subject") if k in f}

    def file_entry(f):
        return {k: f.get(k) for k in ("filename", "path", "size_mb", "modified_at", "folder") if k in f}

    by_folder: Dict[str, List[dict]] = {}
    for f in frames:
        by_folder.setdefault(str(f.get("folder") or f.get("key_mark") or ""), []).append(f)
    subs = []
    for rec in sorted((r for r in subjects or [] if isinstance(r, dict)), key=lambda r: (str(r.get("name") or ""), str(r.get("id") or ""))):
        folder = str(rec.get("folder") or "")
        sm = stores_by.get(folder) or {}
        subs.append({"id": rec.get("id", ""), "name": rec.get("name", ""), "folder": folder, "source": rec.get("source", "intervals"),
                     "held_since": rec.get("first_seen"), "last_load": rec.get("last_load"), "marks": list(rec.get("marks") or []), "kinds": list(rec.get("kinds") or []),
                     "size_mb": sm.get("size_mb", 0), "feeds": feeds_of(sm), "frames": [frame_entry(f) for f in by_folder.pop(folder, [])]})
    top_frames = by_folder.get("", [])
    top_files = [f for f in files if not f.get("folder")]
    intervals_loose = [frame_entry(f) for f in top_frames if str(f.get("source")) == "intervals"]
    endura_files = [file_entry(f) for f in top_files if str(f.get("filename") or "").startswith(ENDURA_PREFIXES)]
    sources = [{"source": "intervals", "title": "Intervals.icu", "subjects": subs, "frames": intervals_loose},
               {"source": "endura", "title": "Endura", "frames": [frame_entry(f) for f in top_frames if str(f.get("source")) == "endura"], "files": endura_files},
               {"source": "sweatstack", "title": "SweatStack", "frames": [frame_entry(f) for f in top_frames if str(f.get("source")) == "sweatstack"]}]
    uploads = {"frames": [frame_entry(f) for f in top_frames if str(f.get("source")) not in ("intervals", "endura", "sweatstack")],
               "files": [file_entry(f) for f in top_files if not str(f.get("filename") or "").startswith(ENDURA_PREFIXES + LOADER_PREFIXES)]}
    return {"sources": sources, "uploads": uploads}


def _drop_fields(st: "Store", fields: Tuple[str, ...]) -> None:
    """Take the fields off every manifest entry; an entry with nothing left (no file, laps or chat) goes."""
    for aid, rec in list(st.manifest().items()):
        for k in fields:
            rec.pop(k, None)
        if not any(rec.get(k) for k in ("file", "laps_fetched", "messages_fetched")):
            del st.manifest()[aid]
    st._dirty = True
    st.save()


def forget(user_dir: str, rel: str, feed: str = "") -> dict:
    """Delete a dataset from the athlete's store, or the athlete whole (no feed): the folder with its record, store and
    views. The datasets are the dialog's lines (2026-10-29): activities (the files; the laps and chats under them stay
    with their own lines), laps, wellness, context (the chats and the calendar), profile - and views, the window files.
    Returns {"removed": what}."""
    import shutil
    top = os.path.join(user_dir, rel)
    if not rel or not os.path.isdir(top):
        return {"removed": ""}
    feed = str(feed or "")
    if not feed or feed == "subject":
        shutil.rmtree(top, ignore_errors=True)
        return {"removed": "subject"}
    st = Store(user_dir, rel)
    if feed == "activities":
        shutil.rmtree(st.activities_dir, ignore_errors=True)
        _drop_fields(st, ("file", "signature", "rows", "columns", "fetched", "used"))
    elif feed == "laps":
        shutil.rmtree(st.laps_dir, ignore_errors=True)
        _drop_fields(st, ("laps_fetched", "laps_signature", "laps"))
    elif feed == "context":
        shutil.rmtree(st.messages_dir, ignore_errors=True)
        _drop_fields(st, ("messages_fetched", "messages_signature", "messages"))
        try:
            os.remove(os.path.join(st.dir, "events.json"))
        except OSError:
            pass
    elif feed in FEEDS:
        try:
            os.remove(os.path.join(st.dir, f"{feed}.json"))
        except OSError:
            pass
    elif feed == "profile":
        shutil.rmtree(st.profile_dir, ignore_errors=True)
    elif feed == "views":
        shutil.rmtree(os.path.join(top, VIEWS_DIR), ignore_errors=True)
    else:
        return {"removed": ""}
    return {"removed": feed}


def prune_views(user_dir: str, rel: str, days: int = USED_DAYS, now: Optional[float] = None) -> int:
    """The window files under views/ not written within `days` leave (docs/DATASETS_DESIGN.md §4: a run's inputs,
    cleaned by age; a routine's run keeps its own copies, a favourite its results); returns how many went."""
    now = time.time() if now is None else now
    folder = os.path.join(user_dir, rel, VIEWS_DIR)
    if not os.path.isdir(folder):
        return 0
    gone = 0
    for name in os.listdir(folder):
        p = os.path.join(folder, name)
        try:
            if os.path.isfile(p) and now - os.path.getmtime(p) > days * 86400:
                os.remove(p)
                gone += 1
        except OSError:
            pass
    return gone


def adopt_views(user_dir: str, rel: str) -> int:
    """The window files an earlier executor wrote at the athlete's (or the mark's) folder itself move under views/,
    the first time the folder is loaded under this one; returns how many moved. A file already under views/ stays."""
    top = os.path.join(user_dir, rel)
    if not os.path.isdir(top):
        return 0
    moved = 0
    for name in os.listdir(top):
        p = os.path.join(top, name)
        if os.path.isfile(p) and name.endswith(".csv"):
            os.makedirs(os.path.join(top, VIEWS_DIR), exist_ok=True)
            if not os.path.exists(os.path.join(top, VIEWS_DIR, name)):
                os.replace(p, os.path.join(top, VIEWS_DIR, name))
            else:
                os.remove(p)
            moved += 1
    return moved


def athlete_folders(user_dir: str) -> List[Tuple[str, dict]]:
    """Every load folder under a user's datasets folder: (the folder relative to it, the athlete's record or {}) -
    the athletes' folders by source, then the marks of loads before the athlete was known."""
    out: List[Tuple[str, dict]] = []
    if not os.path.isdir(user_dir):
        return out
    for name in sorted(os.listdir(user_dir)):
        p = os.path.join(user_dir, name)
        if name in APP_FOLDERS or not os.path.isdir(p):
            continue
        if name in SOURCES:
            for aid in sorted(os.listdir(p)):
                if os.path.isdir(os.path.join(p, aid)):
                    rel = f"{name}/{aid}"
                    out.append((rel, athlete_record(user_dir, rel) or {"source": name, "id": aid, "name": ""}))
        else:
            out.append((name, {}))
    return out


def stores_under(user_dir: str) -> List[dict]:
    """The stores under a user's datasets folder, each with its folder, its subject (the record's source, id and name -
    the athlete; none for a mark's folder from before the athlete was known), the mark for such a folder, and its
    summary (for /cache/inspect)."""
    out = []
    for rel, rec in athlete_folders(user_dir):
        if not os.path.isdir(os.path.join(user_dir, rel, STORE_DIR)):
            continue
        s = Store(user_dir, rel)
        subject = {"source": rec.get("source", ""), "id": rec.get("id", ""), "name": rec.get("name", "")} if rec else None
        out.append(dict(key_mark="" if "/" in rel else rel, folder=rel, subject=subject, **s.summary()))
    return out
