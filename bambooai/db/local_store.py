"""The self-hosted edition's database (docs/OSS_DESIGN.md D6, D9-D13; phase 3, 2026-09-14).

SQLite in the working folder, behind the same shape the app's code uses against Supabase:

    client.table("labels").select("id, label").eq("bamboo_user_id", u).order("label").execute().data
    client.table("labels").insert({...}).execute()      .update({...}).eq(...)      .upsert({...})      .delete().eq(...)
    client.rpc("insert_usage_with_chain", {...}).execute().data

so web_app/auth/supabase_client.py, labels_routes.py and bambooai/db/supabase_client.py run unchanged
over it. Nine tables from the dev schema dump - the person's own work: threads, chains, labels,
dataset_metadata, usage, llm_config and the three integration tables - plus a one-row users table
for the local identity (save_user_llm_config looks the user up). The billing procedures answer
locally: allowed, no charge, no quota. Nothing here is a Supabase client; nothing here is needed
in the hosted edition.

The vocabulary implemented is exactly what the code uses: select (with the three embedded
selects the label routes make), eq, neq, gt, gte, lt, lte, order, limit, range, single,
insert, update, upsert, delete, execute, rpc. Anything else raises, so a new use is noticed.
"""
import json
import os
import re
import sqlite3
import threading
from datetime import datetime

DB_FILE = "bambooai.sqlite"

_DDL = """
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    auth0_id TEXT NOT NULL UNIQUE,
    bamboo_user_id TEXT NOT NULL,
    email TEXT, name TEXT,
    created_at TEXT DEFAULT (datetime('now')), updated_at TEXT DEFAULT (datetime('now')));
CREATE TABLE IF NOT EXISTS threads (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    thread_id TEXT NOT NULL UNIQUE,
    bamboo_user_id TEXT NOT NULL,
    created_at TEXT DEFAULT (datetime('now')), updated_at TEXT DEFAULT (datetime('now')));
CREATE TABLE IF NOT EXISTS chains (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    chain_id TEXT NOT NULL UNIQUE,
    thread_id INTEGER NOT NULL,
    bamboo_user_id TEXT NOT NULL,
    label_id INTEGER,
    created_at TEXT DEFAULT (datetime('now')), updated_at TEXT DEFAULT (datetime('now')));
CREATE TABLE IF NOT EXISTS labels (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    bamboo_user_id TEXT NOT NULL,
    label TEXT NOT NULL,
    created_at TEXT DEFAULT (datetime('now')), updated_at TEXT DEFAULT (datetime('now')),
    UNIQUE (bamboo_user_id, label));
CREATE TABLE IF NOT EXISTS dataset_metadata (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    bamboo_user_id TEXT NOT NULL, thread_id INTEGER NOT NULL, chain_id INTEGER NOT NULL,
    identifier TEXT NOT NULL, type TEXT NOT NULL, source TEXT NOT NULL,
    original_filename TEXT, columns TEXT, date_range TEXT, shape TEXT,
    created_at TEXT DEFAULT (datetime('now')));
CREATE TABLE IF NOT EXISTS usage (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    bamboo_user_id TEXT NOT NULL, agent TEXT, chain_id TEXT, timestamp TEXT, model TEXT,
    prompt_tokens INTEGER, completion_tokens INTEGER, elapsed_time REAL, tokens_per_second REAL, cost REAL,
    created_at TEXT DEFAULT (datetime('now')),
    compute_tier TEXT DEFAULT 'local', query_cost REAL DEFAULT 0, charges_processed INTEGER DEFAULT 1);
CREATE TABLE IF NOT EXISTS llm_config (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL, auth0_id TEXT NOT NULL UNIQUE,
    model_preference TEXT DEFAULT 'cost',
    created_at TEXT DEFAULT (datetime('now')), updated_at TEXT DEFAULT (datetime('now')));
CREATE TABLE IF NOT EXISTS sweatstack_integration (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    bamboo_user_id TEXT NOT NULL UNIQUE, auth0_id TEXT NOT NULL,
    access_token TEXT NOT NULL, refresh_token TEXT, id_token TEXT, token_type TEXT DEFAULT 'Bearer',
    expires_in INTEGER, scope TEXT, expires_at TEXT,
    created_at TEXT DEFAULT (datetime('now')), updated_at TEXT DEFAULT (datetime('now')), last_used_at TEXT DEFAULT (datetime('now')));
CREATE TABLE IF NOT EXISTS intervals_integration (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    bamboo_user_id TEXT NOT NULL UNIQUE, auth0_id TEXT NOT NULL,
    api_key TEXT NOT NULL, access_token TEXT, refresh_token TEXT, id_token TEXT, token_type TEXT DEFAULT 'api_key',
    expires_in INTEGER, scope TEXT, expires_at TEXT,
    created_at TEXT DEFAULT (datetime('now')), updated_at TEXT DEFAULT (datetime('now')), last_used_at TEXT DEFAULT (datetime('now')));
CREATE TABLE IF NOT EXISTS endura_integration (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    bamboo_user_id TEXT NOT NULL UNIQUE, auth0_id TEXT NOT NULL,
    api_key TEXT NOT NULL, access_token TEXT, refresh_token TEXT, id_token TEXT, token_type TEXT DEFAULT 'api_key',
    expires_in INTEGER, scope TEXT, expires_at TEXT,
    created_at TEXT DEFAULT (datetime('now')), updated_at TEXT DEFAULT (datetime('now')), last_used_at TEXT DEFAULT (datetime('now')));
CREATE INDEX IF NOT EXISTS usage_user_time ON usage (bamboo_user_id, timestamp);
CREATE INDEX IF NOT EXISTS chains_label ON chains (label_id);
"""

# the key a row is matched on when upserted (Supabase matches on the unique constraint)
_UPSERT_KEYS = {"users": ("auth0_id",), "threads": ("thread_id",), "chains": ("chain_id",), "labels": ("bamboo_user_id", "label"),
                "llm_config": ("auth0_id",), "sweatstack_integration": ("bamboo_user_id",), "intervals_integration": ("bamboo_user_id",),
                "endura_integration": ("bamboo_user_id",)}
# the embedded selects the code makes: relation name -> (local column, target table, target column)
_EMBEDS = {("chains", "threads"): ("thread_id", "threads", "id"), ("chains", "labels"): ("label_id", "labels", "id")}
_JSON_COLS = {("dataset_metadata", "columns"), ("dataset_metadata", "shape")}
_TABLES = {"users", "threads", "chains", "labels", "dataset_metadata", "usage", "llm_config",
           "sweatstack_integration", "intervals_integration", "endura_integration"}


class Result:
    def __init__(self, data, count=None):
        self.data, self.count = data, count


class _Query:
    def __init__(self, store, table):
        if table not in _TABLES:
            raise RuntimeError(f"local store: no table '{table}' (the hosted edition's tables are not here)")
        self.s, self.t = store, table
        self.op, self.cols, self.values = "select", "*", None
        self.where, self.orders, self.rng, self.single_row = [], [], None, False

    # ---- the builder
    def select(self, cols="*", count=None):
        self.cols = cols
        if self.op == "select":
            pass
        return self

    def insert(self, values):
        self.op, self.values = "insert", values
        return self

    def upsert(self, values, on_conflict=None):
        self.op, self.values = "upsert", values
        return self

    def update(self, values):
        self.op, self.values = "update", values
        return self

    def delete(self):
        self.op = "delete"
        return self

    def eq(self, col, val): self.where.append((col, "=", val)); return self
    def neq(self, col, val): self.where.append((col, "!=", val)); return self
    def gt(self, col, val): self.where.append((col, ">", val)); return self
    def gte(self, col, val): self.where.append((col, ">=", val)); return self
    def lt(self, col, val): self.where.append((col, "<", val)); return self
    def lte(self, col, val): self.where.append((col, "<=", val)); return self
    def is_(self, col, val): self.where.append((col, "IS", val)); return self

    def order(self, col, desc=False, **kwargs):
        self.orders.append((col, "DESC" if desc or kwargs.get("ascending") is False else "ASC"))
        return self

    def limit(self, n): self.rng = (0, n - 1); return self
    def range(self, a, b): self.rng = (a, b); return self
    def single(self): self.single_row = True; return self
    def maybe_single(self): self.single_row = True; return self

    # ---- execution
    def _where_sql(self):
        if not self.where:
            return "", []
        parts, args = [], []
        for col, op, val in self.where:
            if op == "IS":
                parts.append(f'"{col}" IS NULL' if val in (None, "null") else f'"{col}" IS NOT NULL')
            else:
                parts.append(f'"{col}" {op} ?'); args.append(val)
        return " WHERE " + " AND ".join(parts), args

    def execute(self):
        with self.s.lock:
            if self.op == "select":
                return self._select()
            if self.op == "insert":
                rows = self.values if isinstance(self.values, list) else [self.values]
                out = [self.s._insert(self.t, r) for r in rows]
                self.s.conn.commit()
                return Result(out)
            if self.op == "upsert":
                rows = self.values if isinstance(self.values, list) else [self.values]
                out = [self.s._upsert(self.t, r) for r in rows]
                self.s.conn.commit()
                return Result(out)
            if self.op == "update":
                where, args = self._where_sql()
                vals = {k: self.s._enc(self.t, k, v) for k, v in self.values.items()}
                if "updated_at" in self.s.columns(self.t) and "updated_at" not in vals:
                    vals["updated_at"] = datetime.utcnow().isoformat()
                sets = ", ".join(f'"{k}" = ?' for k in vals)
                ids = [r[0] for r in self.s.conn.execute(f'SELECT id FROM "{self.t}"{where}', args)]
                self.s.conn.execute(f'UPDATE "{self.t}" SET {sets}{where}', list(vals.values()) + args)
                self.s.conn.commit()
                return Result(self.s._rows(self.t, ids))
            if self.op == "delete":
                where, args = self._where_sql()
                ids = [r[0] for r in self.s.conn.execute(f'SELECT id FROM "{self.t}"{where}', args)]
                gone = self.s._rows(self.t, ids)
                self.s.conn.execute(f'DELETE FROM "{self.t}"{where}', args)
                self.s.conn.commit()
                return Result(gone)
        raise RuntimeError(f"local store: unknown operation {self.op}")

    def _select(self):
        where, args = self._where_sql()
        order = (" ORDER BY " + ", ".join(f'"{c}" {d}' for c, d in self.orders)) if self.orders else ""
        lim = f" LIMIT {self.rng[1] - self.rng[0] + 1} OFFSET {self.rng[0]}" if self.rng else ""
        cur = self.s.conn.execute(f'SELECT * FROM "{self.t}"{where}{order}{lim}', args)
        names = [d[0] for d in cur.description]
        rows = [dict(zip(names, r)) for r in cur.fetchall()]
        rows = [self.s._decode(self.t, r) for r in rows]
        # the requested columns, and the embedded relations
        plain, embeds = [], []
        for part in re.findall(r"\w+\([^)]*\)|\*|\w+", self.cols):      # commas inside an embed belong to it
            m = re.match(r"(\w+)\((.*)\)", part)
            if m:
                embeds.append((m.group(1), [c.strip() for c in m.group(2).split(",")]))
            else:
                plain.append(part)
        out = []
        for r in rows:
            o = r if (not plain or plain == ["*"]) else {c: r.get(c) for c in plain}
            o = dict(o)
            for rel, rcols in embeds:
                spec = _EMBEDS.get((self.t, rel))
                if not spec:
                    o[rel] = None
                    continue
                local_col, ttable, tcol = spec
                if r.get(local_col) is None:
                    o[rel] = None
                    continue
                trow = self.s.conn.execute(f'SELECT * FROM "{ttable}" WHERE "{tcol}" = ?', (r[local_col],)).fetchone()
                if trow is None:
                    o[rel] = None
                else:
                    tnames = self.s.columns(ttable)
                    td = dict(zip(tnames, trow))
                    o[rel] = {c: td.get(c) for c in rcols} if rcols != ["*"] else td
            out.append(o)
        if self.single_row:
            return Result(out[0] if out else None)
        return Result(out)


class _Rpc:
    def __init__(self, store, name, params):
        self.s, self.name, self.params = store, name, params or {}

    def execute(self):
        with self.s.lock:
            fn = getattr(self.s, "rpc_" + self.name, None)
            if fn is None:
                raise RuntimeError(f"local store: procedure '{self.name}' is not available in the self-hosted edition")
            out = fn(**self.params)
            self.s.conn.commit()
            return Result(out)


class LocalStore:
    def __init__(self, path, local_sub=None, bamboo_user_id=None):
        self.path = path
        self.lock = threading.RLock()
        self.conn = sqlite3.connect(path, check_same_thread=False)
        self.conn.execute("PRAGMA journal_mode=WAL")
        self.conn.executescript(_DDL)
        self._cols = {}
        if local_sub and bamboo_user_id:
            self._upsert("users", {"auth0_id": local_sub, "bamboo_user_id": bamboo_user_id, "email": f"{bamboo_user_id}@local", "name": bamboo_user_id})
            self.conn.commit()

    # ---- the client surface
    def table(self, name):
        return _Query(self, name)

    def rpc(self, name, params=None):
        return _Rpc(self, name, params)

    # ---- helpers
    def columns(self, table):
        if table not in self._cols:
            self._cols[table] = [r[1] for r in self.conn.execute(f'PRAGMA table_info("{table}")')]
        return self._cols[table]

    def _enc(self, table, col, val):
        if (table, col) in _JSON_COLS and not isinstance(val, (str, type(None))):
            return json.dumps(val)
        if isinstance(val, bool):
            return int(val)
        if isinstance(val, (dict, list)):
            return json.dumps(val)
        return val

    def _decode(self, table, row):
        for col in list(row):
            if (table, col) in _JSON_COLS and isinstance(row[col], str):
                try:
                    row[col] = json.loads(row[col])
                except ValueError:
                    pass
        if table == "usage" and "charges_processed" in row:
            row["charges_processed"] = bool(row["charges_processed"])
        return row

    def _rows(self, table, ids):
        if not ids:
            return []
        q = ",".join("?" * len(ids))
        cur = self.conn.execute(f'SELECT * FROM "{table}" WHERE id IN ({q})', ids)
        names = [d[0] for d in cur.description]
        return [self._decode(table, dict(zip(names, r))) for r in cur.fetchall()]

    def _insert(self, table, row):
        known = self.columns(table)
        vals = {k: self._enc(table, k, v) for k, v in row.items() if k in known}
        cols = ", ".join(f'"{k}"' for k in vals)
        cur = self.conn.execute(f'INSERT INTO "{table}" ({cols}) VALUES ({",".join("?" * len(vals))})', list(vals.values()))
        return self._rows(table, [cur.lastrowid])[0]

    def _upsert(self, table, row):
        keys = _UPSERT_KEYS.get(table)
        if keys and all(k in row for k in keys):
            where = " AND ".join(f'"{k}" = ?' for k in keys)
            hit = self.conn.execute(f'SELECT id FROM "{table}" WHERE {where}', [row[k] for k in keys]).fetchone()
            if hit:
                known = self.columns(table)
                vals = {k: self._enc(table, k, v) for k, v in row.items() if k in known and k != "id"}
                if "updated_at" in known and "updated_at" not in vals:
                    vals["updated_at"] = datetime.utcnow().isoformat()
                sets = ", ".join(f'"{k}" = ?' for k in vals)
                self.conn.execute(f'UPDATE "{table}" SET {sets} WHERE id = ?', list(vals.values()) + [hit[0]])
                return self._rows(table, [hit[0]])[0]
        return self._insert(table, row)

    def _thread(self, thread_id, bamboo_user_id):
        row = self.conn.execute('SELECT * FROM threads WHERE thread_id = ?', (str(thread_id),)).fetchone()
        if row:
            return dict(zip(self.columns("threads"), row))
        return self._insert("threads", {"thread_id": str(thread_id), "bamboo_user_id": bamboo_user_id})

    def _chain(self, chain_id, thread_row_id, bamboo_user_id):
        row = self.conn.execute('SELECT * FROM chains WHERE chain_id = ?', (str(chain_id),)).fetchone()
        if row:
            return dict(zip(self.columns("chains"), row))
        return self._insert("chains", {"chain_id": str(chain_id), "thread_id": thread_row_id, "bamboo_user_id": bamboo_user_id})

    # ---- the procedures the person's own work needs (from the dump, in Python)
    def rpc_create_or_get_thread(self, p_thread_id, p_bamboo_user_id):
        before = self.conn.execute('SELECT 1 FROM threads WHERE thread_id = ?', (str(p_thread_id),)).fetchone()
        t = self._thread(p_thread_id, p_bamboo_user_id)
        return {"id": t["id"], "thread_id": t["thread_id"], "bamboo_user_id": t["bamboo_user_id"], "created_at": t["created_at"], "is_new": before is None}

    def rpc_insert_usage_with_chain(self, p_usage_data, p_thread_id):
        u = p_usage_data or {}
        if not (u.get("bamboo_user_id") and u.get("chain_id") and p_thread_id):
            return {"success": False, "error": "missing_required_fields"}
        t = self._thread(p_thread_id, u["bamboo_user_id"])
        c = self._chain(u["chain_id"], t["id"], u["bamboo_user_id"])
        row = self._insert("usage", {"bamboo_user_id": u["bamboo_user_id"], "agent": u.get("agent"), "chain_id": str(u["chain_id"]),
                                     "timestamp": u.get("timestamp"), "model": u.get("model"), "prompt_tokens": u.get("prompt_tokens"),
                                     "completion_tokens": u.get("completion_tokens"), "elapsed_time": u.get("elapsed_time"),
                                     "tokens_per_second": u.get("tokens_per_second"), "cost": u.get("cost"),
                                     "compute_tier": "local", "query_cost": 0.0, "charges_processed": 1})
        return {"success": True, "usage_id": row["id"], "thread_id": t["id"], "chain_id": c["id"]}

    def rpc_insert_dataset_metadata(self, p_bamboo_user_id, p_thread_id, p_chain_id, p_metadata_records):
        t = self._thread(p_thread_id, p_bamboo_user_id)                      # forgiving where the procedure raised
        c = self._chain(p_chain_id, t["id"], p_bamboo_user_id)
        for item in p_metadata_records or []:
            self._insert("dataset_metadata", {"bamboo_user_id": p_bamboo_user_id, "thread_id": t["id"], "chain_id": c["id"],
                                              "identifier": item.get("identifier"), "type": item.get("type"), "source": item.get("source"),
                                              "original_filename": item.get("original_filename"), "columns": item.get("columns"),
                                              "date_range": item.get("date_range"), "shape": item.get("shape")})
        return None

    def rpc_delete_label_and_get_chains(self, p_label_id, p_bamboo_user_id):
        row = self.conn.execute('SELECT label FROM labels WHERE id = ? AND bamboo_user_id = ?', (p_label_id, p_bamboo_user_id)).fetchone()
        if not row:
            return {"success": False, "error": "Label not found or access denied"}
        chains = [r[0] for r in self.conn.execute('SELECT chain_id FROM chains WHERE label_id = ? AND bamboo_user_id = ?', (p_label_id, p_bamboo_user_id))]
        self.conn.execute('UPDATE chains SET label_id = NULL WHERE label_id = ?', (p_label_id,))   # SQLite has no ON DELETE SET NULL here
        self.conn.execute('DELETE FROM labels WHERE id = ? AND bamboo_user_id = ?', (p_label_id, p_bamboo_user_id))
        return {"success": True, "label_name": row[0], "affected_chains": chains, "chain_count": len(chains)}

    # ---- the billing procedures: your own machine
    def rpc_can_continue_exploration(self, **kw):
        return {"allowed": True, "reason": None}

    def rpc_charge_query_completion(self, **kw):
        return {"ok": True, "message": "free_tier_no_charge", "charged": 0.0}

    def rpc_check_grounding_search_quota(self, **kw):
        return {"allowed": True, "remaining": None}


_store = None
_store_lock = threading.Lock()


def client(local_sub=None, bamboo_user_id=None):
    """The one store for this process: BAMBOO_DATA_DIR (default: the working folder) / bambooai.sqlite."""
    global _store
    with _store_lock:
        if _store is None:
            root = os.environ.get("BAMBOO_DATA_DIR") or os.getcwd()
            os.makedirs(root, exist_ok=True)
            sub = local_sub or f"local|{os.environ.get('BAMBOO_USER', 'local')}"
            uid = bamboo_user_id or os.environ.get("BAMBOO_USER", "local")
            _store = LocalStore(os.path.join(root, DB_FILE), local_sub=sub, bamboo_user_id=uid)
        return _store
