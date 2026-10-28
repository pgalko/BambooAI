"""The reach record: what a cell touched outside the data (2026-10-28).

The kernel records, per cell, the hosts a cell connected to and the bytes each way, the files it opened or listed
outside the data, the environment names it read and the programs it started (containers/executor/kernel.py, the
reaches block of the worker). The session keeps the records on the cell's Turn, each marked `asked`: whether the
question, or an earlier question of the thread, named the host, the file or the name - the one mechanical sign that
the person asked for the reach rather than the model deciding on it. A cell the executor refused before it ran
carries the restricted word on `Turn.refused`; it is not an error of the code.

Nothing here enters a prompt. The record is read by the closing card, the stream pane, the code map and the tally
script (tools/reaches_report.py).
"""
from __future__ import annotations

import re
from typing import Iterable, List

__all__ = ["mark", "asked_for", "kinds", "summary", "summary_of_record", "summarize", "chip", "line", "sandbox_line"]

_MIN = 3     # shorter names (a port, "io") match everything and prove nothing


def _texts(questions: Iterable[str]) -> str:
    return "\n".join(str(q or "") for q in questions).lower()


def asked_for(rec: dict, questions: Iterable[str]) -> bool:
    """Whether a reach was named in the question or an earlier one of the thread: the host or its address, the domain
    the host sits under, the file's path or name, the environment name, the program's name. A substring test on the
    text, nothing cleverer: "fetch it from GitHub" does not name api.github.com, and the card says so."""
    text = _texts(questions)
    if not text.strip():
        return False
    kind = rec.get("kind")
    words: List[str] = []
    if kind in ("net", "dns", "listen"):
        host = str(rec.get("host") or "").lower().removeprefix("unix:")
        words += [host, str(rec.get("ip") or "").lower()]
        labels = host.split(".")
        if len(labels) >= 3 and not re.fullmatch(r"[\d.]+", host):
            words.append(".".join(labels[-2:]))           # api.github.com is named by "github.com"
    elif kind == "file":
        path = str(rec.get("path") or "")
        words += [path.lower(), path.rsplit("/", 1)[-1].lower()]
    elif kind == "env":
        words.append(str(rec.get("name") or "").lower())
    elif kind == "process":
        words.append(str(rec.get("command") or "").split()[0].lower() if str(rec.get("command") or "").split() else "")
    return any(w and len(w) >= _MIN and w != "*" and w in text for w in words)


def mark(reaches: Iterable[dict], questions: Iterable[str]) -> List[dict]:
    """The records with `asked` set, as the Turn keeps them."""
    qs = list(questions)
    out = []
    for r in reaches or []:
        rec = dict(r)
        if rec.get("kind") != "more":
            rec["asked"] = asked_for(rec, qs)
        out.append(rec)
    return out


def kinds(reaches: Iterable[dict]) -> dict:
    """Counts by kind, for a row's tag and the card's heading."""
    out: dict = {}
    for r in reaches or []:
        out[r.get("kind", "?")] = out.get(r.get("kind", "?"), 0) + 1
    return out


def _bytes(n) -> str:
    n = int(n or 0)
    if n >= 1_000_000:
        return f"{n / 1_000_000:.1f} MB"
    if n >= 1_000:
        return f"{n / 1_000:.1f} KB"
    return f"{n} B"


def line(rec: dict) -> str:
    """One record in words, for the card, the map and the tally - the same sentence everywhere."""
    kind = rec.get("kind")
    if kind == "net":
        host = str(rec.get("host") or "?")
        port = rec.get("port")
        where = f"{host}:{port}" if port is not None else host
        if rec.get("blocked"):
            return f"tried {where}: the instance metadata address, refused by the kernel"
        if rec.get("failed") and not (rec.get("in") or rec.get("out")):     # bytes exchanged mean an address answered, whatever the first attempt said
            return f"tried {where}: no connection ({str(rec.get('failed')).split(':')[0]})"
        parts = []
        if rec.get("in"):
            parts.append(f"fetched {_bytes(rec.get('in'))} from {where}")
        if rec.get("out"):
            parts.append(f"sent {_bytes(rec.get('out'))}" + ("" if rec.get("in") else f" to {where}"))
        if not parts:
            parts.append(f"connected to {where}, nothing exchanged")
        n = int(rec.get("n") or 0)
        return ", ".join(parts) + (f" ({n} connections)" if n > 1 else "") + (" over TLS" if rec.get("tls") else "")
    if kind == "dns":
        return f"looked up {rec.get('host')}, no connection followed"
    if kind == "listen":
        return f"opened a listening port ({rec.get('host')}:{rec.get('port')})"
    if kind == "file":
        op = {"read": "read", "write": "wrote", "list": "listed"}.get(rec.get("op"), rec.get("op"))
        via = " (through a library)" if rec.get("via") == "library" else ""
        return f"{op} {rec.get('path')}{via}"
    if kind == "env":
        return "read the whole environment" if rec.get("name") == "*" else f"read the environment name {rec.get('name')}"
    if kind == "process":
        return f"started a program: {str(rec.get('command') or '')[:80]}"
    if kind == "more":
        return f"{rec.get('n')} more, not kept"
    return str(rec)


def chip(reaches: Iterable[dict]) -> dict:
    """A cell's reaches as one short tag for its row in the pane and the map: the one reach in a few words, or a
    count; the tag says whether the question asked for them. {} when the cell reached nothing."""
    recs = [r for r in (reaches or []) if r.get("kind") != "more"]
    if not recs:
        return {}
    tag = "blocked" if any(r.get("blocked") for r in recs) else ("unasked" if any(not r.get("asked") for r in recs) else "asked")
    title = "\n".join(line(r) + ("" if r.get("blocked") else (" · the question named it" if r.get("asked") else " · not asked for")) for r in recs)
    if len(recs) == 1:
        r = recs[0]
        kind = r.get("kind")
        if kind == "net":
            where = f"{r.get('host')}" + (f":{r.get('port')}" if r.get("port") not in (None, 80, 443) else "")
            if r.get("blocked"):
                text = f"⊘ {where}"
            elif r.get("failed"):
                text = f"✗ {where}"
            elif r.get("out") and (not r.get("in") or int(r.get("out") or 0) >= 4 * int(r.get("in") or 0)):
                text = f"↑ {_bytes(r.get('out'))} to {where}"            # what went out is the story: a request's own few hundred bytes are not
            elif r.get("in"):
                text = f"↓ {_bytes(r.get('in'))} from {where}"
            else:
                text = f"↔ {where}"
        elif kind == "file":
            text = {"read": "read", "write": "wrote", "list": "listed"}.get(r.get("op"), r.get("op")) + " " + str(r.get("path"))
        elif kind == "env":
            text = "env *" if r.get("name") == "*" else f"env {r.get('name')}"
        elif kind == "process":
            text = "ran " + str(r.get("command") or "")[:40]
        elif kind == "listen":
            text = f"listens on {r.get('port')}"
        elif kind == "dns":
            text = f"looked up {r.get('host')}"
        else:
            text = kind
    else:
        text = f"{len(recs)} reaches outside the data"
    return {"text": text[:80], "tag": tag, "title": title[:600]}


def summary(run) -> dict:
    """The run's reach report for the closing card: one line per record with its cell and its tag, the refused
    attempts, the counts, and the box in one line. `run` is a notebook.Run."""
    entries, attempt_after = [], 0
    for t in run.turns:
        if t.kind != "cell":
            continue
        step = getattr(t, "step", "") or ""
        where = f"cell {t.cell_no}" if t.cell_no is not None else ("figures step" if step == "figures" else f"attempt after cell {attempt_after}")
        entries.append((where, getattr(t, "reaches", None) or [], getattr(t, "refused", "") or ""))
        if t.cell_no is not None:
            attempt_after = t.cell_no
    return summarize(entries, getattr(run, "sandbox", None) or {})


def summary_of_record(doc: dict) -> dict:
    """The same report from a chain record (analyst/codemap/record.py), for the code map's summary panel."""
    entries = [(f"cell {c.get('cell')}", c.get("reaches") or [], "") for c in doc.get("cells") or []]
    entries += [(f"attempt after cell {f.get('after_cell') or 0}", [], f.get("refused") or "") for f in doc.get("failed") or [] if f.get("refused")]
    return summarize(entries, doc.get("sandbox") or {})


def summarize(entries, sandbox: dict) -> dict:
    """(where, reaches, refused) per cell or attempt -> lines, refused, counts, the sandbox line, recorded."""
    lines, refused = [], []
    for where, reaches, word in entries:
        if word:
            refused.append({"where": where, "word": word, "text": f"not run: restricted operation ({word})"})
        for r in reaches:
            if r.get("kind") == "more":
                lines.append({"where": where, "kind": "more", "text": line(r), "tag": ""})
                continue
            tag = "blocked" if r.get("blocked") else ("asked" if r.get("asked") else "unasked")
            lines.append({"where": where, "kind": r.get("kind"), "text": line(r), "tag": tag, "line": r.get("line")})
    counts = {"lines": len(lines), "unasked": sum(1 for x in lines if x["tag"] == "unasked"),
              "asked": sum(1 for x in lines if x["tag"] == "asked"), "blocked": sum(1 for x in lines if x["tag"] == "blocked"),
              "refused": len(refused), "net": sum(1 for x in lines if x["kind"] in ("net", "dns", "listen"))}
    return {"lines": lines, "refused": refused, "counts": counts, "sandbox": sandbox_line(sandbox or {}), "recorded": bool(sandbox)}


def sandbox_line(f: dict) -> str:
    """The box in one line: the user, root or not, capabilities worth a word, seccomp, the metadata address, the
    mounts. "" when the executor did not report (it predates the record, or the kernel ran in the app's process)."""
    if not f:
        return ""
    parts = []
    user = f.get("user") or (f"uid {f.get('uid')}" if f.get("uid") is not None else "unknown user")
    parts.append(f"{user}" + (" (root)" if f.get("root") else " (not root)" if f.get("root") is False else ""))
    cont = f.get("container") or ""
    if cont == "none seen":
        parts.append("no container seen")
    elif cont:
        parts.append(f"in {cont}")
    caps = f.get("notable_caps") or []
    parts.append("capabilities: " + ", ".join(caps) if caps else "no notable capabilities")
    if f.get("seccomp"):
        parts.append(f"seccomp {f['seccomp']}")
    if f.get("docker_socket"):
        parts.append("the docker socket is mounted")
    meta = f.get("metadata") or ""
    if meta:
        parts.append("metadata address " + ("answers" if meta == "answered" else meta))
    mounts = f.get("mounts") or []
    if mounts:
        parts.append(f"{len(mounts)} mount{'s' if len(mounts) != 1 else ''}: " + "; ".join(m.split(" (")[0] for m in mounts[:4]) + (" ..." if len(mounts) > 4 else ""))
    return "; ".join(parts)
