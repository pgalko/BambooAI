"""The codebook (docs/CONTEXT_DESIGN.md §3.3, §13): the enforced English vocabulary the coder labels passages
with. Per user, under storage/<user>/context/codebook.json; seeded from analyst/codebook_seed.json on first use;
grown only by stored proposals (a code the coder asked for and could not find, kept as `proposed` for the coach);
the version bumps on a confirmed change, never on a proposal. The codes file of a load records the version it was
coded under. Pure: the seed, the file, the vocabulary as the coder receives it (data, like a column name)."""
from __future__ import annotations

import json
import os
import re
import time
from typing import Dict, Iterable, List, Optional, Tuple

SEED_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "codebook_seed.json")
ACTIVE = ("seeded", "confirmed")
_CODE_RE = re.compile(r"[^a-z0-9_]+")


def _now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def normalise_code(name) -> str:
    """A code's name as the book keeps it: lower case, words joined by underscores, nothing else."""
    s = str(name or "").strip().lower().replace("-", "_").replace(" ", "_")
    s = _CODE_RE.sub("", s).strip("_")
    return re.sub(r"_+", "_", s)


def seed() -> dict:
    """A fresh codebook from the seed file: version 1, every code `seeded` with no uses yet."""
    with open(SEED_PATH, encoding="utf-8") as fh:
        raw = json.load(fh)
    codes = [{"code": normalise_code(c["code"]), "group": c.get("group", ""), "definition": c.get("definition", ""),
              "status": "seeded", "uses": 0} for c in raw.get("codes", [])]
    return {"version": int(raw.get("version", 1)), "updated": _now(), "codes": codes}


def path_for(storage_dir: str) -> str:
    return os.path.join(storage_dir, "context", "codebook.json")


def load(storage_dir: str) -> dict:
    """The user's codebook, seeded and written on first use; a file that cannot be read is replaced by the seed."""
    path = path_for(storage_dir)
    try:
        with open(path, encoding="utf-8") as fh:
            book = json.load(fh)
        if isinstance(book, dict) and isinstance(book.get("codes"), list):
            return book
    except (OSError, ValueError):
        pass
    book = seed()
    save(storage_dir, book)
    return book


def save(storage_dir: str, book: dict) -> str:
    path = path_for(storage_dir)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(book, fh, indent=1, ensure_ascii=False)
    os.replace(tmp, path)
    return path


def entries(book: dict) -> List[dict]:
    return [c for c in (book or {}).get("codes", []) if isinstance(c, dict) and c.get("code")]


def active_codes(book: dict) -> set:
    """The codes the coder may use as the book's own: seeded and confirmed."""
    return {c["code"] for c in entries(book) if c.get("status", "seeded") in ACTIVE}


def proposed_codes(book: dict) -> set:
    """Proposals waiting for the coach: usable by the coder, their rows marked `proposed`."""
    return {c["code"] for c in entries(book) if c.get("status") == "proposed"}


def vocabulary_text(book: dict) -> str:
    """The vocabulary as the coder receives it: one line per code, `code: definition`, the proposals last and
    marked. Data, not prompt (the definitions come from the seed file and the coach)."""
    lines = []
    for c in entries(book):
        if c.get("status", "seeded") in ACTIVE:
            lines.append(f"{c['code']}: {c.get('definition', '')}".rstrip())
    for c in entries(book):
        if c.get("status") == "proposed":
            lines.append(f"{c['code']}: {c.get('definition', '')} (proposed, awaiting the coach)".rstrip())
    return "\n".join(lines)


def add_proposals(book: dict, proposals: Iterable[dict], coder: str = "", when: Optional[str] = None) -> Tuple[dict, List[str]]:
    """Store the coder's proposals that name a code the book lacks, as `proposed`; a proposal of a code the book
    holds under any status is nothing (the coder was told to use what exists). Returns (book, the names added).
    The version does not move: a proposal is not a confirmed change."""
    have = {c["code"] for c in entries(book)}
    added = []
    for p in proposals or []:
        code = normalise_code((p or {}).get("code"))
        definition = str((p or {}).get("definition") or "").strip()
        if not code or not definition or code in have:
            continue
        example = str((p or {}).get("example") or "").strip()
        book.setdefault("codes", []).append({"code": code, "group": "proposed", "definition": definition, "status": "proposed",
                                             "proposed_by": coder or "", "proposed_on": when or _now(),
                                             "examples": [example] if example else [], "uses": 0})
        have.add(code)
        added.append(code)
    if added:
        book["updated"] = when or _now()
    return book, added


def record_uses(book: dict, counts: Dict[str, int], when: Optional[str] = None) -> dict:
    """The last load's count per code, for the codebook page (overwritten by every load)."""
    for c in entries(book):
        c["uses"] = int(counts.get(c["code"], 0))
    book["updated"] = when or _now()
    return book


def confirm(book: dict, code: str, rename_to: Optional[str] = None, merge_into: Optional[str] = None,
            when: Optional[str] = None) -> Tuple[dict, bool]:
    """The coach's decision on a proposal (§4 F4): confirmed as it is, renamed, or merged into an existing code -
    each a confirmed change, so the version bumps. Returns (book, changed)."""
    code = normalise_code(code)
    hit = next((c for c in entries(book) if c["code"] == code and c.get("status") == "proposed"), None)
    if hit is None:
        return book, False
    if merge_into:
        target = normalise_code(merge_into)
        if not any(c["code"] == target and c.get("status", "seeded") in ACTIVE for c in entries(book)):
            return book, False
        book["codes"] = [c for c in entries(book) if c is not hit]
    else:
        if rename_to:
            new = normalise_code(rename_to)
            if not new or any(c["code"] == new for c in entries(book) if c is not hit):
                return book, False
            hit["code"] = new
        hit["status"] = "confirmed"
        hit["group"] = hit.get("group") if hit.get("group") not in ("", "proposed") else "confirmed"
    book["version"] = int(book.get("version", 1)) + 1
    book["updated"] = when or _now()
    return book, True


def decline(book: dict, code: str, when: Optional[str] = None) -> Tuple[dict, bool]:
    """A proposal the coach declines leaves the book (the codes files that used it keep their rows, marked)."""
    code = normalise_code(code)
    before = len(entries(book))
    book["codes"] = [c for c in entries(book) if not (c["code"] == code and c.get("status") == "proposed")]
    changed = len(book["codes"]) != before
    if changed:
        book["updated"] = when or _now()
    return book, changed


# ----------------------------------------------------------------------------- the codebook screen (step 6, S3)
STATUSES = ("seeded", "confirmed", "proposed")


def seed_groups() -> List[str]:
    """The seed's groups in its own order: the order the page lists them in."""
    try:
        with open(SEED_PATH, encoding="utf-8") as fh:
            raw = json.load(fh)
    except (OSError, ValueError):
        return []
    out: List[str] = []
    for c in raw.get("codes", []):
        g = str((c or {}).get("group") or "")
        if g and g not in out:
            out.append(g)
    return out


def why_not(book: dict, code: str, rename_to: Optional[str] = None, merge_into: Optional[str] = None) -> str:
    """Why `confirm` would refuse, in a sentence for the person; '' when it would not."""
    code = normalise_code(code)
    if not any(c["code"] == code and c.get("status") == "proposed" for c in entries(book)):
        return f"there is no proposal named {code or '?'}"
    if merge_into:
        target = normalise_code(merge_into)
        if not any(c["code"] == target and c.get("status", "seeded") in ACTIVE for c in entries(book)):
            return f"{target or '?'} is not a code of the book to merge into"
        return ""
    if rename_to:
        new = normalise_code(rename_to)
        if not new:
            return "the new name is empty"
        if any(c["code"] == new for c in entries(book) if c["code"] != code):
            return f"the book already has a code named {new}"
    return ""


def view(book: dict) -> dict:
    """The book as the page shows it (docs/CONTEXT_DESIGN.md §7 S3): the version and date, the counts, the proposals
    first (each with its definition, proposer, date, example passages and the last load's uses), then the codes by
    group - the seed's groups in the seed's order, any other group after them, `confirmed` last - each code with
    its definition, status and uses."""
    items = entries(book)
    proposals = [{"code": c["code"], "definition": c.get("definition", ""), "proposed_by": c.get("proposed_by", ""),
                  "proposed_on": c.get("proposed_on", ""), "examples": list(c.get("examples") or []), "uses": int(c.get("uses") or 0)}
                 for c in items if c.get("status") == "proposed"]
    active = [c for c in items if c.get("status", "seeded") in ACTIVE]
    order = seed_groups()
    others = sorted({str(c.get("group") or "") for c in active} - set(order) - {"confirmed", ""})
    groups = []
    for g in order + others + ["confirmed", ""]:
        codes = [{"code": c["code"], "definition": c.get("definition", ""), "status": c.get("status", "seeded"), "uses": int(c.get("uses") or 0)}
                 for c in active if str(c.get("group") or "") == g]
        if codes:
            groups.append({"name": g or "other", "codes": codes})
    return {"version": int(book.get("version", 1)), "updated": str(book.get("updated") or ""),
            "counts": {"codes": len(active), "proposed": len(proposals), "used": sum(1 for c in active if int(c.get("uses") or 0) > 0)},
            "proposals": proposals, "groups": groups}


def validate_import(obj) -> Tuple[Optional[dict], str]:
    """A book from a file, checked: a dict with a list of codes, each a dict with a code (normalised, unique), a
    definition and a status the book knows; the proposals keep their proposer, date and examples. Returns (book,
    '') or (None, the reason)."""
    if not isinstance(obj, dict) or not isinstance(obj.get("codes"), list):
        return None, "the file is not a codebook: it needs a list of codes"
    codes: List[dict] = []
    seen = set()
    for i, c in enumerate(obj["codes"]):
        if not isinstance(c, dict):
            return None, f"entry {i + 1} is not an object"
        code = normalise_code(c.get("code"))
        definition = str(c.get("definition") or "").strip()
        status = str(c.get("status") or "seeded")
        if not code:
            return None, f"entry {i + 1} has no code"
        if code in seen:
            return None, f"the code {code} appears twice"
        if not definition:
            return None, f"the code {code} has no definition"
        if status not in STATUSES:
            return None, f"the code {code} has an unknown status ({status})"
        seen.add(code)
        entry = {"code": code, "group": str(c.get("group") or ("proposed" if status == "proposed" else "")), "definition": definition,
                 "status": status, "uses": int(c.get("uses") or 0) if str(c.get("uses") or "0").lstrip("-").isdigit() else 0}
        if status == "proposed":
            entry.update({"proposed_by": str(c.get("proposed_by") or ""), "proposed_on": str(c.get("proposed_on") or ""),
                          "examples": [str(x) for x in (c.get("examples") or []) if str(x).strip()]})
        codes.append(entry)
    if not codes:
        return None, "the file holds no codes"
    try:
        version = int(obj.get("version", 1))
    except (TypeError, ValueError):
        version = 1
    return {"version": max(version, 1), "updated": str(obj.get("updated") or _now()), "codes": codes}, ""


def replace(storage_dir: str, imported: dict, when: Optional[str] = None) -> dict:
    """The imported book in place of the user's: the version never goes back (the codes files carry versions), so it
    is one more than the greater of the two; written."""
    current = load(storage_dir)
    book = dict(imported)
    book["version"] = max(int(current.get("version", 1)), int(imported.get("version", 1))) + 1
    book["updated"] = when or _now()
    save(storage_dir, book)
    return book
