"""The Intervals.icu keys kept per athlete (2026-10-30, docs/DATASETS_DESIGN.md §17): the store functions in
web_app/auth/supabase_client.py over the local SQLite store and over the stack's Supabase stand-in - the same calls, the
same answers - and the local file's upgrade from one key per user.

    python3 tests/analyst/test_keys.py
"""
import importlib
import os
import sqlite3
import sys
import tempfile
import time

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path[:0] = [os.path.dirname(os.path.abspath(__file__)), ROOT, os.path.join(ROOT, "web_app"), os.path.join(ROOT, "tools", "stack")]
import _stubs  # noqa: F401,E402  (the stand-ins for packages a bare box lacks, as the other suites use)
os.environ["AUTH_MODE"] = "single"
os.environ["LLM_CONFIG_ENCRYPTION_KEY"] = "test-keys"
os.environ["BAMBOO_DATA_DIR"] = tempfile.mkdtemp(prefix="bamboo_keys_")

passed, failed = [], []


def check(name, cond, detail=""):
    (passed if cond else failed).append(name)
    print(("  ok   " if cond else "  FAIL ") + name + ("" if cond else f"  <- {str(detail)[:600]}"))


from flask import Flask, g                                  # noqa: E402
import auth.supabase_client as sc                            # noqa: E402

U, A = "coach", "local|coach"
app = Flask("t")


def scenario(label):
    """The whole life of a coach's keys, over whichever client sc.get_service_client answers with."""
    with app.app_context():
        g.current_user_id = A
        check(f"[{label}] nothing stored: no key, no athletes, the status says so",
              sc.get_intervals_api_key(U, A) is None and sc.list_intervals_athletes(U, A) == [] and sc.get_intervals_integration_status(U, A) == {"authenticated": False, "has_api_key": False, "athletes": []})
        check(f"[{label}] the first athlete's key is stored, named, encrypted (never the key itself in the row), and read back by the athlete and without one",
              sc.store_intervals_api_key(U, A, "key-one", "i0", "The subject") and sc.get_intervals_api_key(U, A, "i0") == "key-one" and sc.get_intervals_api_key(U, A) == "key-one"
              and all(r.get("api_key") != "key-one" for r in sc._intervals_rows(sc.get_service_client(), U)))
        time.sleep(0.02)
        check(f"[{label}] a second athlete's key: both listed, the one last used first; the key read by athlete; without an athlete the last used named one's",
              sc.store_intervals_api_key(U, A, "key-two", "i1", "The other subject") and sc.get_intervals_api_key(U, A, "i1") == "key-two"
              and [a["athlete_id"] for a in sc.list_intervals_athletes(U, A)] == ["i1", "i0"] and sc.get_intervals_api_key(U, A) == "key-two"
              and [a["athlete_id"] for a in sc.list_intervals_athletes(U, A)] == ["i1", "i0"], sc.list_intervals_athletes(U, A))
        time.sleep(0.02)
        got = sc.get_intervals_api_key(U, A, "i0")
        check(f"[{label}] reading an athlete's key marks it used: that athlete now first; the status names both", got == "key-one" and [a["athlete_id"] for a in sc.list_intervals_athletes(U, A)] == ["i0", "i1"]
              and sc.get_intervals_integration_status(U, A)["has_api_key"] is True and len(sc.get_intervals_integration_status(U, A)["athletes"]) == 2)
        check(f"[{label}] the same athlete's key again replaces theirs (a rotated key): still two rows, the new key read, the name kept when none is given",
              sc.store_intervals_api_key(U, A, "key-one-b", "i0", "") and sc.get_intervals_api_key(U, A, "i0") == "key-one-b" and len(sc.list_intervals_athletes(U, A)) == 2
              and next(a for a in sc.list_intervals_athletes(U, A) if a["athlete_id"] == "i0")["athlete_name"] == "", sc.list_intervals_athletes(U, A))
        # a key whose athlete could not be named (Intervals.icu unreachable when it was saved): the one pending row
        check(f"[{label}] a pending key (athlete '') is kept as one row, listed last without a name, never the one taken without an athlete while a named one exists, and read by ''",
              sc.store_intervals_api_key(U, A, "key-pending", "", "") and [a["athlete_id"] for a in sc.list_intervals_athletes(U, A)][-1] == "" and sc.get_intervals_api_key(U, A) in ("key-one-b", "key-two")
              and sc.get_intervals_api_key(U, A, "") == "key-pending" and len(sc.list_intervals_athletes(U, A)) == 3)
        check(f"[{label}] a second pending key replaces the first: still one pending row", sc.store_intervals_api_key(U, A, "key-pending-2", "", "") and sc.get_intervals_api_key(U, A, "") == "key-pending-2" and len(sc.list_intervals_athletes(U, A)) == 3)
        check(f"[{label}] naming the pending key as a new athlete: the row gets the id and the name, nothing pending remains",
              sc.name_pending_intervals_key(U, A, "i2", "A third") and sc.get_intervals_api_key(U, A, "i2") == "key-pending-2" and sc.get_intervals_api_key(U, A, "") is None
              and next(a for a in sc.list_intervals_athletes(U, A) if a["athlete_id"] == "i2")["athlete_name"] == "A third" and len(sc.list_intervals_athletes(U, A)) == 3)
        check(f"[{label}] naming a pending key as an athlete who has a row: theirs takes the key, the pending row goes; nothing pending names nothing",
              sc.store_intervals_api_key(U, A, "key-two-rotated", "", "") and sc.name_pending_intervals_key(U, A, "i1", "") and sc.get_intervals_api_key(U, A, "i1") == "key-two-rotated"
              and sc.get_intervals_api_key(U, A, "") is None and len(sc.list_intervals_athletes(U, A)) == 3 and sc.name_pending_intervals_key(U, A, "i1", "") is False
              and next(a for a in sc.list_intervals_athletes(U, A) if a["athlete_id"] == "i1")["athlete_name"] == "The other subject")
        check(f"[{label}] one athlete's key removed: the others stay; removing without an athlete empties the list",
              sc.remove_intervals_api_key(U, A, "i2") and [a["athlete_id"] for a in sc.list_intervals_athletes(U, A)] in (["i0", "i1"], ["i1", "i0"]) and sc.get_intervals_api_key(U, A, "i2") is None
              and sc.remove_intervals_api_key(U, A) and sc.list_intervals_athletes(U, A) == [] and sc.get_intervals_api_key(U, A) is None)
        g.current_user_id = "local|someone-else"
        check(f"[{label}] another user's identity is refused by every function", sc.store_intervals_api_key(U, A, "k", "i0", "x") is False and sc.get_intervals_api_key(U, A) is None and sc.list_intervals_athletes(U, A) == [] and sc.remove_intervals_api_key(U, A) is False)


# ---- the local SQLite store (the self-hosted edition) ----
check("without Supabase the service client is the local store", type(sc.get_service_client()).__name__ == "LocalStore")
scenario("local")

# ---- the Supabase stand-in of the stack (the hosted edition's client surface) ----
import fake_supabase                                         # noqa: E402
_real = sc.get_service_client
sc.get_service_client = lambda: fake_supabase.create_client("http://supabase.local", "local")
try:
    fake_supabase.TABLES["intervals_integration"].clear() if hasattr(fake_supabase, "TABLES") else None
    scenario("stand-in")
finally:
    sc.get_service_client = _real

# ---- the local file from before the keys were kept per athlete: upgraded on opening, the key kept as pending ----
from bambooai.db import local_store                           # noqa: E402
OLD = """CREATE TABLE IF NOT EXISTS intervals_integration (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    bamboo_user_id TEXT NOT NULL UNIQUE, auth0_id TEXT NOT NULL,
    api_key TEXT NOT NULL, access_token TEXT, refresh_token TEXT, id_token TEXT, token_type TEXT DEFAULT 'api_key',
    expires_in INTEGER, scope TEXT, expires_at TEXT,
    created_at TEXT DEFAULT (datetime('now')), updated_at TEXT DEFAULT (datetime('now')), last_used_at TEXT DEFAULT (datetime('now')));"""
old_file = os.path.join(tempfile.mkdtemp(prefix="bamboo_keys_old_"), "bambooai.sqlite")
c = sqlite3.connect(old_file); c.executescript(OLD)
c.execute("INSERT INTO intervals_integration (bamboo_user_id, auth0_id, api_key) VALUES (?, ?, ?)", (U, A, sc._encrypt_value("key-before"))); c.commit(); c.close()
st = local_store.LocalStore(old_file, local_sub=A, bamboo_user_id=U)
cols = st.columns("intervals_integration")
with app.app_context():
    g.current_user_id = A
    _real2 = sc.get_service_client
    sc.get_service_client = lambda: st
    try:
        check("an old file opens upgraded: athlete_id and athlete_name present, the unique index per user and athlete, the key kept as the pending row and read without an athlete; a second athlete's key sits beside it; a duplicate athlete is refused by the index",
              "athlete_id" in cols and "athlete_name" in cols and sc.get_intervals_api_key(U, A) == "key-before" and [a["athlete_id"] for a in sc.list_intervals_athletes(U, A)] == [""]
              and sc.store_intervals_api_key(U, A, "key-new", "i5", "Five") and [a["athlete_id"] for a in sc.list_intervals_athletes(U, A)] == ["i5", ""]
              and sc.get_intervals_api_key(U, A) == "key-new"
              and any(r[2] for r in st.conn.execute("PRAGMA index_list('intervals_integration')")), (cols, sc.list_intervals_athletes(U, A)))
        dup = False
        try:
            st.table("intervals_integration").insert({"bamboo_user_id": U, "auth0_id": A, "api_key": "x", "athlete_id": "i5"}).execute()
        except Exception:                                      # noqa: BLE001
            dup = True
        check("the upgraded file refuses a second row for the same athlete, and the file is not left locked by the refusal", dup and sc.get_intervals_api_key(U, A, "i5") == "key-new")
        st2 = local_store.LocalStore(old_file, local_sub=A, bamboo_user_id=U)
        check("opening the upgraded file again changes nothing", [a for a in st2.table("intervals_integration").select("athlete_id").eq("bamboo_user_id", U).execute().data] and st2.columns("intervals_integration") == cols)
    finally:
        sc.get_service_client = _real2

print(f"\n{len(passed)} passed, {len(failed)} failed")
sys.exit(1 if failed else 0)
