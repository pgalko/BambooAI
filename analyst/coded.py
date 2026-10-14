"""The coded passages a user's loads have already read (docs/CONTEXT_DESIGN.md §12 D1, the fallback taken on
2026-10-14): per user and per key mark - one subject's data - under storage/<user>/context/<key mark>/coded.json.
A load codes only the passages the store has not seen; a passage is known by its kind and source id, and re-coded
when its text changed. The codebook version each entry was coded under rides with it, so old labels stay
comparable. Pure: a dict in a file, bounded."""
from __future__ import annotations

import hashlib
import json
import os
import re
from typing import Dict, List, Tuple

MAX_ENTRIES = 6000          # a few seasons of a daily writer; the oldest by day go first


def _hash(text) -> str:
    return hashlib.sha1(re.sub(r"\s+", " ", str(text or "")).strip().encode("utf-8")).hexdigest()[:12]


def passage_key(p: dict) -> str:
    """kind:source_id, or kind:day:hash when the row carries no source id."""
    kind = str(p.get("kind") or "")
    sid = str(p.get("source_id") or "").strip()
    if sid and sid.lower() != "nan":
        return f"{kind}:{sid}"
    return f"{kind}:{str(p.get('date') or '')[:10]}:{_hash(p.get('text'))}"


class CodedStore:
    def __init__(self, storage_dir: str, key_mark: str):
        self.path = os.path.join(storage_dir, "context", str(key_mark or "unmarked"), "coded.json")
        self.entries: Dict[str, dict] = {}
        self.loaded = False

    def load(self) -> "CodedStore":
        try:
            with open(self.path, encoding="utf-8") as fh:
                data = json.load(fh)
            if isinstance(data, dict) and isinstance(data.get("entries"), dict):
                self.entries = data["entries"]
        except (OSError, ValueError):
            self.entries = {}
        self.loaded = True
        return self

    def save(self) -> str:
        self.prune()
        os.makedirs(os.path.dirname(self.path), exist_ok=True)
        tmp = self.path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump({"entries": self.entries}, fh, ensure_ascii=False)
        os.replace(tmp, self.path)
        return self.path

    def lookup(self, passages: List[dict]) -> Tuple[Dict[str, dict], List[dict]]:
        """(known: passage id -> the stored entry, todo: the passages to code) - a passage is known when the store
        holds its key with the same text hash."""
        known, todo = {}, []
        for p in passages:
            e = self.entries.get(passage_key(p))
            if e and e.get("hash") == _hash(p.get("text")):
                known[str(p.get("id"))] = e
            else:
                todo.append(p)
        return known, todo

    def remember(self, passages: List[dict], rows: List[dict], renderings: Dict[str, dict], coder: str, version: int) -> int:
        """Store what a pass established for the passages it answered: the rendering and the codes (an answered
        passage with no code is stored with none, so it is not asked again). Returns the count stored."""
        by_id: Dict[str, List[dict]] = {}
        for r in rows:
            by_id.setdefault(str(r["id"]), []).append({"code": r["code"], "tone": r["tone"], "quote": r["quote"], "status": r["status"]})
        n = 0
        for p in passages:
            uid = str(p.get("id"))
            if uid not in renderings:
                continue                                       # not answered by the coder: nothing to remember
            r = renderings[uid]
            self.entries[passage_key(p)] = {"hash": _hash(p.get("text")), "date": str(p.get("date") or "")[:10], "lang": r.get("lang", ""),
                                            "text_en": r.get("text_en", ""), "codes": by_id.get(uid, []), "coder": coder, "codebook_version": int(version)}
            n += 1
        return n

    def prune(self, max_entries: int = MAX_ENTRIES) -> int:
        if len(self.entries) <= max_entries:
            return 0
        keep = sorted(self.entries.items(), key=lambda kv: kv[1].get("date", ""), reverse=True)[:max_entries]
        dropped = len(self.entries) - len(keep)
        self.entries = dict(keep)
        return dropped
