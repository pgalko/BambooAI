"""The Intervals.icu store (2026-10-15, docs/INCREMENTAL_LOADS_DESIGN.md): what a load fetched, kept by what it is rather
than by window - one file per activity's second-by-second rows, the chat under each activity, a manifest - under the
key's folder on the executor's disk (datasets/<user>/<mark>/store/). A window is then a view: the loader fetches the
window's activity list (the manifest of what Intervals holds), takes from the store every activity it already has whose
file has not changed, downloads only the rest, and assembles the frame from the store. The wellness log and the calendar
are fetched fresh each load (one call each); the messages under an activity are fetched again while the activity is
recent or changed, and reused for older ones.

The files are parquet (compressed; a year of second-by-second data is a tenth of its CSV size). Where pandas has no parquet
engine - the test sandbox - the same frames go to compressed pickles under another extension; the real image carries pyarrow.
"""
import hashlib
import json
import os
import time
from datetime import date, timedelta
from typing import Dict, Iterable, List, Optional, Tuple

import pandas as pd

STORE_DIR = "store"
MANIFEST = "activities.json"
# the fields of an activity's list entry that change when its file changes (a re-sync, a re-upload, a different
# recording): the detail rows are fetched again when any of them differs from the stored signature
DETAIL_SIGNATURE = ("icu_sync_date", "file_type", "start_date_local", "elapsed_time", "moving_time", "distance")
MESSAGES_FRESH_DAYS = 60       # the chat under an activity started within this many days is fetched again each load
RETENTION_DAYS = 400           # activities started earlier than this many days ago leave the store when a load ends...
USED_DAYS = 30                 # ...unless a load served them within this many days (a routine over an old window keeps its data)
ENGINE_WHEN_NO_PARQUET = "pickle"


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
        self.dir = os.path.join(user_dir, mark or "unmarked", STORE_DIR)
        self.activities_dir = os.path.join(self.dir, "activities")
        self.messages_dir = os.path.join(self.dir, "messages")
        self._manifest: Optional[Dict[str, dict]] = None
        self._dirty = False

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

    # ---------------------------------------------------------------- housekeeping and the account of it
    def prune(self, today: Optional[date] = None, days: int = RETENTION_DAYS, used_days: int = USED_DAYS, now: Optional[float] = None) -> int:
        """Drop activities started earlier than `days` ago (their rows and chat) that no load served within
        `used_days`; returns how many went."""
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
            for p in (os.path.join(self.dir, rec.get("file") or "__none__"), self._messages_path(aid)):
                try:
                    os.remove(p)
                except OSError:
                    pass
            del self.manifest()[aid]
            self._dirty = True
            gone += 1
        return gone

    def summary(self) -> dict:
        """What the store holds, for the cache listing and the dialogs: activities, the span of their days, the size."""
        m = self.manifest()
        days = sorted(str(r.get("day") or "")[:10] for r in m.values() if r.get("day"))
        size = 0
        for root, _dirs, files in os.walk(self.dir) if os.path.isdir(self.dir) else []:
            for f in files:
                try:
                    size += os.path.getsize(os.path.join(root, f))
                except OSError:
                    pass
        return {"activities": sum(1 for r in m.values() if r.get("file")), "chats": sum(1 for r in m.values() if r.get("messages_fetched")),
                "from": days[0] if days else "", "to": days[-1] if days else "", "bytes": size, "size_mb": round(size / (1024 * 1024), 2),
                "engine": "parquet" if HAVE_PARQUET else ENGINE_WHEN_NO_PARQUET}


def stores_under(user_dir: str) -> List[dict]:
    """The stores of every key under a user's datasets folder, each with its mark and summary (for /cache/inspect)."""
    out = []
    if not os.path.isdir(user_dir):
        return out
    for mark in sorted(os.listdir(user_dir)):
        if mark in ("generated", "routines") or not os.path.isdir(os.path.join(user_dir, mark, STORE_DIR)):
            continue
        s = Store(user_dir, mark)
        out.append(dict(key_mark=mark, **s.summary()))
    return out
