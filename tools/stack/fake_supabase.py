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
import threading
from datetime import datetime

_ids = itertools.count(1)
_lock = threading.Lock()

TABLES = {
    "users": [{"id": 1, "auth0_id": "auth0|localuser", "bamboo_user_id": "localuser", "email": "local@stack", "name": "Local Stack"}],
    "user_subscription": [{"user_id": 1, "model_tier": "free", "compute_tier": "free", "integration_config": {},
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
    "labels": [], "chains": [], "llm_config": [], "usage": [], "dataset_metadata": [],
    "sweatstack_integration": [], "intervals_integration": [], "endura_integration": [],
}
RPC = {
    "can_execute_chain": lambda p: {"allowed": True, "reason": "ok", "compute_tier": "free", "balance": 0.0, "query_cost": 0.0,
                                    "queries_used": _counter(), "max_queries": 20},
    "increment_queries_counter": lambda p: _bump(),
    "get_monthly_usage": lambda p: {"period_start": "2026-09-01", "period_end": "2026-10-01", "queries_used": _counter(), "max_queries": 20},
    "get_compute_tier": lambda p: "free",
    "charge_query_completion": lambda p: {"ok": True, "charged": 0.0},
    "can_continue_exploration": lambda p: {"allowed": True},
    "insert_usage_with_chain": lambda p: {"ok": True},
    "check_grounding_search_quota": lambda p: {"allowed": True, "remaining": 100},
    "insert_dataset_metadata": lambda p: {"ok": True},
    "upsert_subscription": lambda p: {"ok": True},
    "add_funds": lambda p: {"ok": True, "balance": 0.0},
}


def _counter():
    return TABLES["usage_counters"][0]["queries_used"]


def _bump():
    with _lock:
        TABLES["usage_counters"][0]["queries_used"] += 1
    return {"queries_used": _counter()}


class Result:
    def __init__(self, data, count=None):
        self.data, self.count = data, count


class _Query:
    def __init__(self, table):
        self.table, self.rows = table, TABLES.setdefault(table, [])
        self.op, self.payload, self.filters, self._single, self._limit, self._order = "select", None, [], False, None, None

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
    def order(self, col, **k): self._order = (col, bool(k.get("desc", False))); return self
    def limit(self, n): self._limit = n; return self
    def single(self): self._single = True; return self
    def maybe_single(self): self._single = True; return self
    def range(self, a, b): return self
    def ilike(self, col, pat): return self
    def gte(self, col, v): return self
    def lte(self, col, v): return self

    def _match(self, row):
        for col, val in self.filters:
            if isinstance(val, tuple) and val and val[0] == "neq":
                if row.get(col) == val[1]: return False
            elif isinstance(val, tuple) and val and val[0] == "in":
                if row.get(col) not in val[1]: return False
            elif row.get(col) != val:
                return False
        return True

    def execute(self):
        with _lock:
            if self.op == "select":
                rows = [dict(r) for r in self.rows if self._match(r)]
                if self._order:
                    rows.sort(key=lambda r: (r.get(self._order[0]) is None, r.get(self._order[0])), reverse=self._order[1])
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
                        self.rows[:] = [r for r in self.rows if r.get("id") != row["id"]]
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
