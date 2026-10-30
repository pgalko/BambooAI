"""A stand-in for the `supabase` package: an in-memory store behind the query-builder chain the
app uses (table().select().eq().order().limit().single().execute(), insert/update/upsert/delete,
rpc().execute()). Registered as sys.modules['supabase'] by webapp_launcher.py, with the env set so
the app's own client code (web_app/auth/supabase_client.py, bambooai/db/supabase_client.py)
builds it exactly as it would build the real one.

Seeded with one free-tier user (auth0|localuser) with a zero balance and the free tier limits,
so the account, usage and label dialogs render with real data flowing through the real routes.
Unknown RPCs answer with an empty dict; unknown tables are empty and accept inserts.
"""
import itertools
import os
import threading
from datetime import datetime

# the account's compute tier (2026-10-10): free by default; STACK_COMPUTE_TIER=pro gives the Intervals loader a year's
# window instead of fourteen days, which the integrations' walk needs for a routine's "later window"
TIER = os.environ.get("STACK_COMPUTE_TIER", "free")
_ids = itertools.count(1)
_lock = threading.Lock()

TABLES = {
    "users": [{"id": 1, "auth0_id": "auth0|localuser", "bamboo_user_id": "localuser", "email": "local@stack", "name": "Local Stack"}],
    "user_subscription": [{"user_id": 1, "model_tier": "free", "compute_tier": TIER, "integration_config": {},
                           "anniversary_date": "2026-09-01", "updated_at": "2026-09-01T00:00:00"}],
    "tier_limits": [
        {"category": "compute", "tier": "free", "variable_rate": 0.0, "max_queries": 20, "max_data_days": 14, "description": "Free"},
        {"category": "compute", "tier": "plus", "variable_rate": 0.05, "max_queries": None, "max_data_days": 90, "description": "Plus"},
        {"category": "compute", "tier": "pro", "variable_rate": 0.10, "max_queries": None, "max_data_days": 365, "description": "Pro"},
        {"category": "model", "tier": "free", "variable_rate": 0.0, "max_queries": 20, "max_data_days": None, "description": "Free models"},
        {"category": "model", "tier": "managed", "variable_rate": 0.0, "max_queries": None, "max_data_days": None, "description": "Managed models"},
    ],
    "user_funds": [{"user_id": 1, "balance": 0.0, "last_updated": None}],
    "usage_counters": [{"user_id": 1, "queries_used": 0, "period_start": "2026-09-01", "period_end": "2026-10-01"}],
    "labels": [], "threads": [], "chains": [], "llm_config": [], "usage": [], "dataset_metadata": [],
    "sweatstack_integration": [], "intervals_integration": [], "endura_integration": [],
}
RPC = {
    "can_execute_chain": lambda p: {"allowed": True, "reason": "ok", "compute_tier": TIER, "balance": 0.0, "query_cost": 0.0,
                                    "queries_used": _counter(), "max_queries": 20},
    "increment_queries_counter": lambda p: _bump(),
    "get_monthly_usage": lambda p: {"period_start": "2026-09-01", "period_end": "2026-10-01", "queries_used": _counter(), "max_queries": 20},
    "get_compute_tier": lambda p: TIER,
    "charge_query_completion": lambda p: {"ok": True, "charged": 0.0},
    "can_continue_exploration": lambda p: {"allowed": True},
    "insert_usage_with_chain": lambda p: _insert_usage(p),
    "check_grounding_search_quota": lambda p: {"allowed": True, "remaining": 100},
    "insert_dataset_metadata": lambda p: {"ok": True},
    "upsert_subscription": lambda p: {"ok": True},
    "add_funds": lambda p: {"ok": True, "balance": 0.0},
}


def _counter():
    return TABLES["usage_counters"][0]["queries_used"]


def _insert_usage(p):
    """As the hosted function does (2026-10-31, so the stack's usage dialog has rows): the thread and the chain made
    when absent, the usage row kept with the cache split, the savings and the fees - NULL when the payload has none."""
    u = dict((p or {}).get("p_usage_data") or {})
    thread_id = (p or {}).get("p_thread_id")
    if not (u.get("bamboo_user_id") and u.get("chain_id") and thread_id):
        return {"success": False, "error": "missing_required_fields"}
    with _lock:
        t = next((r for r in TABLES["threads"] if r.get("thread_id") == thread_id), None)
        if t is None:
            t = {"id": next(_ids), "thread_id": thread_id, "bamboo_user_id": u["bamboo_user_id"], "created_at": datetime.now().isoformat()}
            TABLES["threads"].append(t)
        c = next((r for r in TABLES["chains"] if r.get("chain_id") == str(u["chain_id"])), None)
        if c is None:
            c = {"id": next(_ids), "chain_id": str(u["chain_id"]), "thread_id": t["id"], "bamboo_user_id": u["bamboo_user_id"], "created_at": datetime.now().isoformat()}
            TABLES["chains"].append(c)
        row = {"id": next(_ids), "created_at": datetime.now().isoformat(), "compute_tier": TIER, "query_cost": 0.03 if TIER == "pro" else 0.0, "charges_processed": False}
        for k in ("bamboo_user_id", "agent", "chain_id", "timestamp", "model", "prompt_tokens", "completion_tokens", "elapsed_time", "tokens_per_second", "cost",
                  "cached_tokens", "cache_write_tokens", "cache_savings", "search_fee", "image_fee"):
            row[k] = u.get(k)
        row["chain_id"] = str(row["chain_id"])
        TABLES["usage"].append(row)
    return {"success": True, "usage_id": row["id"], "chain_id": row["chain_id"], "thread_id": thread_id, "message": "Usage record inserted successfully"}


def _bump():
    with _lock:
        TABLES["usage_counters"][0]["queries_used"] += 1
    return {"queries_used": _counter()}


# the unique keys the hosted tables have (the integration tables one row per user; the Intervals one per user and athlete
# since docs/sql/intervals_keys_per_athlete.sql): an insert that repeats one raises, as the real client does
_UNIQUE = {"intervals_integration": (("bamboo_user_id", "athlete_id"),), "endura_integration": (("bamboo_user_id",),), "sweatstack_integration": (("bamboo_user_id",),),
           "users": (("auth0_id",),), "llm_config": (("auth0_id",),)}


class APIError(Exception):
    """What postgrest raises: the error as a dict, its text the message."""
    def __init__(self, info):
        super().__init__(str(info)); self.info = info


class Result:
    def __init__(self, data, count=None):
        self.data, self.count = data, count


class _Query:
    def __init__(self, table):
        self.table, self.rows = table, TABLES.setdefault(table, [])
        self.op, self.payload, self.filters, self._single, self._limit, self._orders, self._range = "select", None, [], False, None, [], None

    # builder verbs (each returns self)
    def select(self, *a, **k): self.op = "select"; return self
    def insert(self, data, **k): self.op, self.payload = "insert", data; return self
    def upsert(self, data, **k): self.op, self.payload = "upsert", data; return self
    def update(self, data, **k): self.op, self.payload = "update", data; return self
    def delete(self, **k): self.op = "delete"; return self
    def eq(self, col, val): self.filters.append((col, val)); return self
    def neq(self, col, val): self.filters.append((col, ("neq", val))); return self
    def in_(self, col, vals): self.filters.append((col, ("in", list(vals)))); return self
    def is_(self, col, val): self.filters.append((col, val)); return self
    def order(self, col, **k): self._orders.append((col, bool(k.get("desc", False)))); return self
    def limit(self, n): self._limit = n; return self
    def single(self): self._single = True; return self
    def maybe_single(self): self._single = True; return self
    def range(self, a, b): self._range = (a, b); return self            # real since 2026-10-31: the usage routes page through the rows
    def ilike(self, col, pat): return self
    # the comparisons as Postgres makes them (2026-10-31; they returned everything): the usage routes cut a period out
    # of the rows by timestamp, text against text in the logger's own format
    def gte(self, col, v): self.filters.append((col, (">=", v))); return self
    def lte(self, col, v): self.filters.append((col, ("<=", v))); return self
    def gt(self, col, v): self.filters.append((col, (">", v))); return self
    def lt(self, col, v): self.filters.append((col, ("<", v))); return self

    def _match(self, row):
        for col, val in self.filters:
            if isinstance(val, tuple) and val and val[0] == "neq":
                if row.get(col) == val[1]: return False
            elif isinstance(val, tuple) and val and val[0] == "in":
                if row.get(col) not in val[1]: return False
            elif isinstance(val, tuple) and val and val[0] in (">=", "<=", ">", "<"):
                have, want = row.get(col), val[1]
                if have is None: return False
                a, b = (have, want) if isinstance(have, (int, float)) and isinstance(want, (int, float)) else (str(have).replace("T", " "), str(want).replace("T", " "))
                if not {">=": a >= b, "<=": a <= b, ">": a > b, "<": a < b}[val[0]]: return False
            elif row.get(col) != val:
                return False
        return True

    def execute(self):
        with _lock:
            if self.op == "select":
                rows = [dict(r) for r in self.rows if self._match(r)]
                for col, desc in reversed(self._orders):                     # the first order the strongest, as SQL has it
                    rows.sort(key=lambda r: (r.get(col) is None, r.get(col)), reverse=desc)
                if self._range is not None:
                    rows = rows[self._range[0]:self._range[1] + 1]
                if self._limit is not None:
                    rows = rows[:self._limit]
                return Result(rows[0] if self._single and rows else (None if self._single else rows), len(rows))
            if self.op in ("insert", "upsert"):
                items = self.payload if isinstance(self.payload, list) else [self.payload]
                out = []
                for it in items:
                    row = dict(it)
                    row.setdefault("id", next(_ids))
                    row.setdefault("created_at", datetime.now().isoformat())
                    if self.op == "upsert":
                        # as Supabase does: on the table's unique key - the integration tables are one row per user (a second
                        # key stored replaces the first, 2026-10-11), the rest by id
                        key = "bamboo_user_id" if self.table.endswith("_integration") and row.get("bamboo_user_id") is not None else "id"
                        self.rows[:] = [r for r in self.rows if r.get(key) != row[key]]
                    else:
                        # as Postgres does (2026-10-30): an insert that repeats a unique key is refused - the hosted tables' keys
                        # as they stand after docs/sql/intervals_keys_per_athlete.sql (one row per coach and athlete there)
                        for cols in _UNIQUE.get(self.table, ()):
                            if all(row.get(c) is not None for c in cols) and any(all(r.get(c) == row.get(c) for c in cols) for r in self.rows):
                                raise APIError({"message": f"duplicate key value violates unique constraint \"{self.table}_{'_'.join(cols)}_key\"", "code": "23505",
                                                "details": "Key (" + ", ".join(cols) + ")=(" + ", ".join(str(row.get(c)) for c in cols) + ") already exists."})
                    self.rows.append(row); out.append(dict(row))
                return Result(out, len(out))
            if self.op == "update":
                out = []
                for r in self.rows:
                    if self._match(r):
                        r.update(self.payload or {}); out.append(dict(r))
                return Result(out, len(out))
            if self.op == "delete":
                gone = [dict(r) for r in self.rows if self._match(r)]
                self.rows[:] = [r for r in self.rows if not self._match(r)]
                return Result(gone, len(gone))
        return Result([])


class _Rpc:
    def __init__(self, name, params):
        self.name, self.params = name, params

    def execute(self):
        fn = RPC.get(self.name)
        return Result(fn(self.params or {}) if fn else {})


class Client:
    def __init__(self, url=None, key=None, *a, **k):
        self.url, self.key = url, key
        self.auth = type("Auth", (), {"get_user": staticmethod(lambda *a, **k: None)})()

    def table(self, name):
        return _Query(name)

    def rpc(self, name, params=None):
        return _Rpc(name, params)


def create_client(url, key, *a, **k):
    return Client(url, key)
