"""The brief: what the person agreed before a run, as the analyst receives it (docs/ARCHITECT_DESIGN.md §2.2, §2.5).

A brief is a plain dict, kept with its run. Every part is optional: the analyst is given the parts that hold
something, and one the person did not state is the analyst's to choose.

    {"version": 2,
     "question": "...",          the run's question: the person's words, or the Architect's wording of them
     "decision": "...",          what they will do differently depending on the answer
     "thinks": "...",            what they think is going on
     "rests_on": [{"text": "...", "source": "person", "mark": "", "note": ""}],     what the frame rests on
     "expects": "...",           what they expect to see
     "would_change": "...",      what would change their mind
     "also_check": [{"text": "...", "shows": "...", "source": "architect", "accepted": false}],     other explanations, and what each would show
     "fixed": {"comparison": "...", "measure": "...", "period": "..."},             fixed before the run
     "figures": [{"title": "...", "kind": "line", "x": "...", "y": "...", "z": "...", "note": "...",
                  "series": [{"name": "..."}]}],                                    the figures the person asked to see, each as it is described
     "saved": [{"thread": "...", "run": "...", "when": "...", "question": "...", "passage": "...", "where": "...", "note": "...", "marks": "...", "data": "...", "period": "...",
                "person": "...", "other": true, "accepted": true}],                  passages of the saved analyses it builds on; `other`: of another person's data than the one loaded
     "set_aside": ["..."]}       considered and dropped

A line's source is who it comes from (SOURCES); its mark is what a check against the data found (MARKS), or '' when
nothing checked it. An explanation the Architect proposed says so, and whether the person accepted it; one of the
person's own carries neither. The passages under `saved` are those of the saved analyses the person chose to build
on, as the reader found them (gather(), build_on()). A figure is one the person asked to see, as the Architect
describes it (sketch()): a draft of it is drawn before the run (analyst/draft.py), the analyst computes for it and
the step that draws is given it in words (figure_lines()). normalise() brings what a caller sends into this shape,
agreed() is the brief as the analyst receives it, render() writes the BRIEF block of the prompt, held() says
whether the report is to answer to it, and outcome() reads back what a report says against the brief. While a brief
is being written it is kept as versions on its run: version() adds one, latest() is the one in use - the last, or
an earlier one the person went back to (use()); write() takes in what a reply of the Architect's names and mark()
the marks it gives after its lookups; said() is the conversation the brief came from, as text.
"""
from __future__ import annotations

import re
from typing import Optional

SOURCES = ("person", "architect", "data", "saved", "result")      # who a line comes from; an earlier result is a claim, not a fact
MARKS = ("holds", "does not hold", "cannot be checked")
FIXED = ("comparison", "measure", "period")
SAVED = ("thread", "run", "when", "question", "passage", "where", "note", "marks", "data", "period", "person")
TEXT_CHARS = 600                 # one line of a brief, at most
QUESTION_CHARS = 4000            # the question, at most: the person's words, not a line of the brief
MAX = {"rests_on": 6, "also_check": 4, "saved": 10, "set_aside": 8, "figures": 3}     # bounds on what a prompt carries, not the design's counts; saved: the passages of the analyses built on
# the kinds of figure a description names, each as the analyst reads it
KINDS = {"line": "a line chart", "scatter": "a scatter of points", "bar": "bars", "histogram": "a histogram", "box": "box plots", "heatmap": "a heat map",
         "line3d": "a line in three dimensions"}
FIGURE_CHARS = {"title": 120, "axis": 80, "name": 60, "note": 240}
SERIES = 4                       # the lines or groups one figure holds by name
COUNTS = {"rests_on": 4, "also_check": 2}                               # the design's counts (§2.2): what the Architect writes a brief with
ALWAYS = ("chance", "measurement error", "how the cases compared came to be chosen")      # checked in every briefed run on data
VERDICTS = ("not met", "cannot tell", "met")                     # read in this order: "not met" holds "met"
SEEN = ("not seen", "cannot tell", "seen")


def _text(value) -> str:
    return re.sub(r"\s+", " ", str(value)).strip()[:TEXT_CHARS] if isinstance(value, (str, int, float)) and not isinstance(value, bool) else ""


def wording(value) -> str:
    """A wording of the question, the person's or the Architect's: its lines kept, runs of spaces folded, bounded as
    a question is."""
    if not isinstance(value, str):
        return ""
    return "\n".join(re.sub(r"[ \t]+", " ", line).strip() for line in value.strip().splitlines())[:QUESTION_CHARS]


def _figure(f) -> dict:
    """One figure in its known shape: its title - without one it is no figure - its kind where it is one of KINDS,
    what is on each axis, the lines or groups it holds by name, and its note: how it is laid out and what it is to
    make clear."""
    if not isinstance(f, dict) or not _text(f.get("title")):
        return {}
    out = {"title": _text(f["title"])[:FIGURE_CHARS["title"]], **({"kind": f["kind"]} if isinstance(f.get("kind"), str) and f["kind"] in KINDS else {})}
    out.update({axis: _text(f[axis])[:FIGURE_CHARS["axis"]] for axis in ("x", "y", "z") if _text(f.get(axis))})
    series = []
    for s in f.get("series") if isinstance(f.get("series"), list) else []:
        s = s if isinstance(s, dict) else {"name": s}
        name = _text(s.get("name"))[:FIGURE_CHARS["name"]]
        if name and name not in [x["name"] for x in series]:
            series.append({"name": name})
    if series:
        out["series"] = series[:SERIES]
    if _text(f.get("note")):
        out["note"] = _text(f["note"])[:FIGURE_CHARS["note"]]
    return out


def normalise(brief) -> dict:
    """The brief in its known shape: the parts with content, text on one line and bounded, a line given as a bare
    string made a line of the person's. {} when nothing in it frames the question."""
    if not isinstance(brief, dict):
        return {}
    out = {}
    for key in ("decision", "thinks", "expects", "would_change"):
        if _text(brief.get(key)):
            out[key] = _text(brief.get(key))
    anchors = []
    for a in brief.get("rests_on") if isinstance(brief.get("rests_on"), list) else []:
        a = a if isinstance(a, dict) else {"text": a}
        if _text(a.get("text")):
            line = {"text": _text(a.get("text")), "source": a.get("source") if a.get("source") in SOURCES else "person",
                    "mark": a.get("mark") if a.get("mark") in MARKS else ""}
            if _text(a.get("note")):
                line["note"] = _text(a.get("note"))
            anchors.append(line)
    rivals = []
    for r in brief.get("also_check") if isinstance(brief.get("also_check"), list) else []:
        r = r if isinstance(r, dict) else {"text": r}
        if _text(r.get("text")):
            rivals.append({"text": _text(r.get("text")), **({"shows": _text(r.get("shows"))} if _text(r.get("shows")) else {}),
                           **({"source": "architect", "accepted": r.get("accepted") is True} if r.get("source") == "architect" else {})})
    fixed = {k: _text(v) for k, v in (brief.get("fixed") if isinstance(brief.get("fixed"), dict) else {}).items() if k in FIXED and _text(v)}
    saved = []
    for s in brief.get("saved") if isinstance(brief.get("saved"), list) else []:
        entry = {k: _text(s.get(k)) for k in SAVED if _text(s.get(k))} if isinstance(s, dict) else {}
        if entry.get("passage") or entry.get("question"):
            saved.append({**entry, **({"other": True} if s.get("other") is True else {}), "accepted": s.get("accepted") is True})
    aside = [_text(x) for x in (brief.get("set_aside") if isinstance(brief.get("set_aside"), list) else []) if _text(x)]
    figures = []
    for f in brief.get("figures") if isinstance(brief.get("figures"), list) else []:
        f = _figure(f)
        if f and f["title"].casefold() not in [x["title"].casefold() for x in figures]:      # a title names one figure
            figures.append(f)
    for key, value in (("rests_on", anchors), ("also_check", rivals), ("fixed", fixed), ("figures", figures), ("saved", saved), ("set_aside", aside)):
        if value:
            out[key] = value[:MAX[key]] if key in MAX else value
    if not out:
        return {}
    version = brief.get("version")
    out["version"] = int(version) if isinstance(version, int) and not isinstance(version, bool) and version > 0 else 1
    if wording(brief.get("question")):
        out["question"] = wording(brief.get("question"))
    return out


def agreed(brief) -> dict:
    """The brief as the analyst receives it: in its known shape, without what the Architect proposed, or the reader
    found in the saved analyses, and the person did not accept."""
    brief = brief if isinstance(brief, dict) else {}
    lines = brief.get("also_check") if isinstance(brief.get("also_check"), list) else []
    saved = brief.get("saved") if isinstance(brief.get("saved"), list) else []
    return normalise({**brief, "also_check": [r for r in lines if not (isinstance(r, dict) and r.get("source") == "architect" and r.get("accepted") is not True)],
                      "saved": [s for s in saved if isinstance(s, dict) and s.get("accepted") is True]})


def working(brief) -> dict:
    """The brief while it is being written: in its known shape, without a version number; one that so far holds only
    the question keeps it."""
    out = {k: v for k, v in normalise(brief).items() if k != "version"}
    if not out and isinstance(brief, dict) and wording(brief.get("question")):
        out = {"question": wording(brief.get("question"))}
    return out


def version(framing: dict, brief, by: str = "person", changed=None, why: str = "") -> dict:
    """A version added to a run's framing: the brief as it stands, who made the change, which parts it touched and,
    for the Architect's, what it was made from (`why`: the question, an answer, or a check against the data). Returns
    the framing with the new version, which is the one in use from now; every earlier one stays."""
    versions = list((framing or {}).get("versions") or [])
    entry = {"n": len(versions) + 1, "by": by if by in ("person", "architect") else "person",
             "changed": [str(c)[:60] for c in (changed or []) if isinstance(c, str)][:12], "brief": working(brief)}
    if why:
        entry["why"] = str(why)[:60]
    return {**{k: v for k, v in (framing or {}).items() if k != "at"}, "versions": versions + [entry]}


def use(framing: dict, n) -> dict:
    """The framing with version `n` in use: the person went back to it, and what is done next - an answer, a change,
    the analysis - goes on from it. The later versions stay. A number the framing does not have changes nothing."""
    versions = (framing or {}).get("versions") or []
    if not isinstance(n, int) or isinstance(n, bool) or not 1 <= n <= len(versions):
        return dict(framing or {})
    rest = {k: v for k, v in framing.items() if k != "at"}
    return rest if n == len(versions) else {**rest, "at": n}


def write(brief, parts) -> tuple:
    """The brief with what a reply of the Architect names written in (analyst/architect.py). A text part is a
    string, and "" empties it; the question is given as a wording, its lines kept, and is never emptied. The two
    lists take lines: a line given under `drop` is taken out of either, when it is there word for word; a line given
    under a list's own name is added to it when it is not there yet, as a line of the person's, up to the design's
    counts. A line given under `propose` is added to the other explanations as the Architect's own, with what it
    would show, not accepted: only the person accepts it. A line the reply does not name stays as it is, with its
    source and its mark. What is fixed is given part by part. Nothing else of the brief is touched. Returns the
    brief and the parts that changed, as the page names them."""
    out = working(brief)
    parts = parts if isinstance(parts, dict) else {}
    changed = []
    if wording(parts.get("question")) and wording(parts["question"]) != out.get("question", ""):
        out["question"] = wording(parts["question"])
        changed.append("question")
    for key in ("decision", "thinks", "expects", "would_change"):
        if isinstance(parts.get(key), str) and _text(parts[key]) != out.get(key, ""):
            out[key] = _text(parts[key])
            changed.append(key)
    gone = {_text(x) for x in (parts.get("drop") if isinstance(parts.get("drop"), list) else [])}
    proposed = lambda t, item: {"text": t, "shows": item.get("shows"), "source": "architect", "accepted": False}
    for key, given, line in (("rests_on", "rests_on", lambda t, item: {"text": t, "source": "person", "mark": ""}),
                             ("also_check", "also_check", lambda t, item: {"text": t}), ("also_check", "propose", proposed)):
        now = [a for a in out.get(key, []) if a["text"] not in gone]
        if len(now) != len(out.get(key, [])):
            changed.append(key)
        for item in parts.get(given) if isinstance(parts.get(given), list) else []:
            item = item if isinstance(item, dict) else {"text": item}
            text = _text(item.get("text"))
            if text and text not in [a["text"] for a in now] and len(now) < COUNTS[key]:
                now.append(line(text, item))
                changed.append(f"{key}.{len(now) - 1}")
        out[key] = now
    fixed = dict(out.get("fixed", {}))
    given = parts.get("fixed") if isinstance(parts.get("fixed"), dict) else {}
    for key in FIXED:
        if isinstance(given.get(key), str) and _text(given[key]) != fixed.get(key, ""):
            fixed[key] = _text(given[key])
            changed.append(f"fixed.{key}")
    return working({**out, "fixed": fixed}), changed          # a part emptied falls away


def sketch(brief, given) -> tuple:
    """The brief with its figures as a reply of the Architect's gives them (analyst/architect.py): every figure as it
    is to stand, in order - one that stays as it is by its number among the brief's, from 1, a new or changed one
    in full; [] takes them all out. A number the brief does not have is passed over, as is a figure without a
    title or under a title another carries; MAX["figures"] are kept. Returns the brief and what changed, as the
    page names it: each place whose figure is new or another than before, and `figures` where fewer stand."""
    out = working(brief)
    was, given = out.get("figures", []), given if isinstance(given, list) else []
    stays = lambda f: isinstance(f, int) and not isinstance(f, bool) and 1 <= f <= len(was)      # noqa: E731
    now = normalise({"figures": [was[f - 1] if stays(f) else f for f in given]}).get("figures", [])
    changed = [f"figures.{i}" for i, f in enumerate(now) if i >= len(was) or f != was[i]] + (["figures"] if len(now) < len(was) else [])
    return working({**out, "figures": now}), changed


def figure_lines(brief) -> list:
    """The figures of a brief in words, a line each, for the analyst, for the model that drafts them and for the step
    that draws them: the title, the kind, what is on each axis, what the figure holds by name, and its note."""
    lines = []
    for f in (brief or {}).get("figures", []):
        parts = ([KINDS[f["kind"]]] if f.get("kind") else []) + [f"{axis}: {f[axis]}" for axis in ("x", "y", "z") if f.get(axis)]
        parts += ["holds: " + ", ".join(s["name"] for s in f["series"])] if f.get("series") else []
        parts += [f"to make clear: {f['note']}"] if f.get("note") else []
        lines.append(f"\"{f['title']}\"" + (" - " + "; ".join(parts) if parts else ""))
    return lines


def carries(text: str, title: str) -> bool:
    """Whether a text - a cell's code, the title a figure was drawn under - carries a figure's title: its words in
    their order, whatever the case and the spacing."""
    fold = lambda s: re.sub(r"\s+", " ", str(s or "")).strip().casefold()      # noqa: E731
    return bool(fold(title)) and fold(title) in fold(text)


def _passage(f: dict) -> dict:
    """A passage the reader found (analyst/reader.py, an entry of its `found`), as a framing keeps it: its run, the
    day, what was asked, the passage word for word and where it stands, the reader's note, the run's marks and the
    data it ran on - with whose it is and whether that is another person than the one whose data is loaded, where
    the host said so."""
    entry = {"thread": f["thread"], "run": f["run"], "when": f["when"][:10], "question": f["question"] or f"Synthesis: {f['title']}", "passage": f["quote"], "where": f["where"],
             "note": f["note"], "marks": ", ".join(f["marks"]), "data": f["data"]["name"], "period": f["data"]["period"], "person": f["data"].get("person")}
    return {**{k: _text(v) for k, v in entry.items() if _text(v)}, **({"other": True} if f["data"].get("other") is True else {})}


def _same(a: dict, b: dict) -> bool:
    """Whether two entries are one passage: the same words of the same run."""
    return all(a.get(k) == b.get(k) for k in ("thread", "run", "passage"))


def gather(kept, read) -> list:
    """The passages the readings of a brief have found so far, with one more reading's (_passage()): in the order
    they were found, a passage that is there already not added again. The analyses they come from are numbered in
    this order (analyses()): a reply of the Architect's builds on one by its number."""
    out = [dict(s) for s in kept if isinstance(s, dict)] if isinstance(kept, list) else []
    for entry in [_passage(f) for f in read] if isinstance(read, list) else []:
        if not any(_same(s, entry) for s in out):
            out.append(entry)
    return out


def build_on(brief, found, numbers) -> tuple:
    """The brief built on the saved analyses a reply of the Architect's names, on the person's word: by their
    numbers among the analyses the readings found (analyses(found)), from 1. Their passages stand under `saved`,
    and no other: an analysis the reply does not name is built on no longer. A number the readings do not have is
    passed over, and what the brief has no room for is left out. Returns the brief and what changed, as the page
    names it: each passage added, and `saved` where one went."""
    out = working(brief)
    groups = analyses(found if isinstance(found, list) else [])
    chosen = sorted({n for n in numbers if isinstance(n, int) and not isinstance(n, bool) and 1 <= n <= len(groups)}) if isinstance(numbers, list) else []
    was = out.get("saved", [])
    now = [{**s, "accepted": True} for n in chosen for s in groups[n - 1]][:MAX["saved"]]
    changed = [f"saved.{i}" for i, s in enumerate(now) if not any(_same(s, o) and o.get("accepted") for o in was)]
    gone = any(not any(_same(o, s) for s in now) for o in was)
    return working({**out, "saved": now}), changed + (["saved"] if gone else [])


def mark(brief, marks, facts) -> tuple:
    """The brief with lines it rests on marked, as a reply of the Architect's says (analyst/architect.py). `marks`:
    [{"line", "mark", "lookup", "why"}], a line named word for word. `facts`: what the lookups made so far found, by
    number: (the line of the brief the lookup was made for, what it found as the host wrote it, whether that is a
    result). "holds" and "does not hold" stand only on a lookup made for the line that gave a result, and the fact
    beside the line is that lookup's own; given without one, the mark is passed over and the line stays as it is. A
    line that "cannot be checked" has the reason given beside it. Returns the brief and the lines that changed, as
    the page names them."""
    out = working(brief)
    lines = out.get("rests_on", [])
    changed = []
    for m in marks if isinstance(marks, list) else []:
        m = m if isinstance(m, dict) else {}
        at = next((i for i, a in enumerate(lines) if a["text"] == _text(m.get("line"))), None)
        if at is None or m.get("mark") not in MARKS:
            continue
        k = m.get("lookup")
        about, fact, result = facts.get(k, ("", "", False)) if isinstance(k, int) and not isinstance(k, bool) else ("", "", False)
        if m["mark"] == "cannot be checked":
            note = _text(m.get("why"))
        elif result and about == lines[at]["text"]:
            note = fact
        else:
            continue
        new = {**{key: v for key, v in lines[at].items() if key != "note"}, "mark": m["mark"], **({"note": note} if note else {})}
        if new != lines[at]:
            lines[at] = new
            changed += [f"rests_on.{at}"] if f"rests_on.{at}" not in changed else []
    return working(out), changed


def latest(framing: dict) -> dict:
    """The brief of the version in use, numbered with it: the one the person went back to (use()), else the last;
    {} when there is none."""
    versions = (framing or {}).get("versions") or []
    at = (framing or {}).get("at")
    v = versions[at - 1] if isinstance(at, int) and not isinstance(at, bool) and 1 <= at <= len(versions) else versions[-1] if versions else {}
    return {**v["brief"], "version": v.get("n", len(versions))} if v.get("brief") else {}



def said(framing, question: str = "") -> str:
    """What the person and the Architect said while a brief was written, as text: each message under who said it,
    the question as it was first asked before them - `question` where the framing kept no first version - and the
    question as the Architect worded it on a line of its own. "" where nothing was said. What was looked up, read
    or opened meanwhile, and where the person went to another version, is no part of it."""
    framing = framing if isinstance(framing, dict) else {}
    turns = [t for t in framing.get("turns") or [] if t.get("who") in ("person", "architect") and str(t.get("text") or "").strip()]
    if not turns:
        return ""
    first = str(((framing.get("versions") or [{}])[0].get("brief") or {}).get("question") or question or "").strip()
    lines = [f"Person: {first}"] if first else []
    for t in turns:
        lines.append(f"{'Architect' if t['who'] == 'architect' else 'Person'}: {str(t['text']).strip()}")
        if t.get("wording"):
            lines.append(f"Architect's wording of the question: {t['wording']}")
    return "\n".join(lines)


def carried(parent) -> dict:
    """The brief a run takes over from the run it answers: the analyst asked, the person replied, and what was
    agreed still stands. {} when the parent did not end on a question or had no brief."""
    if parent is None or getattr(parent, "status", "") != "asked" or not getattr(parent, "brief", None):
        return {}
    return {**{k: v for k, v in parent.brief.items() if k != "carried_from"}, "carried_from": parent.id}


def analyses(saved: list) -> list:
    """The saved passages of a brief by the analysis each comes from, the analyses in the order they first stand in
    it: SHOW SAVED k opens the k-th. A passage that names no run stands alone."""
    groups: dict = {}
    for i, s in enumerate(saved):
        groups.setdefault((s["thread"], s["run"]) if s.get("thread") and s.get("run") else i, []).append(s)
    return list(groups.values())


def _standing(anchor: dict) -> str:
    """What a line the frame rests on is worth, as the analyst reads it."""
    note = f" - {anchor['note']}" if anchor.get("note") else ""
    if anchor.get("mark") == "cannot be checked":
        return "cannot be checked" + note
    if anchor.get("mark"):
        return f"checked against the data: {anchor['mark']}{note}"
    if anchor.get("source") in ("saved", "result"):
        return "from an earlier result: a claim to test" + note
    return "the person's word, not checked" + note


def held(brief, data: bool = True) -> bool:
    """Whether a brief gives something to hold the result against: what the person expects to see, what would change
    their mind, or a check - among them the ones every run on data makes. The report answers to such a brief in a
    part of its own."""
    brief = brief if isinstance(brief, dict) else {}
    return bool(brief) and bool(data or brief.get("expects") or brief.get("would_change") or brief.get("also_check"))


def render(brief: dict, record: bool = False, data: bool = True) -> str:
    """The BRIEF block of the analyst's prompt: the parts that hold something, each on its line; a part the person
    did not state is not there. `data`: whether the run has data to run on - the checks every such run makes are
    listed then. `record`: the brief as a record keeps it (the memory view) - without the heading and those checks."""
    if not brief:
        return ""
    part = lambda label, text: [f"{label}: {text}"] if text else []      # noqa: E731
    lines = [] if record else ["BRIEF (agreed before your question; the QUESTION above is the person's answer, and it stands where the two differ):"
                               if brief.get("carried_from") else "BRIEF (agreed with the person before this run):"]
    lines += part("What the answer is for", brief.get("decision")) + part("What the person thinks", brief.get("thinks"))
    lines += ["What it rests on:"] + [f"- {a['text']} [{_standing(a)}]" for a in brief["rests_on"]] if brief.get("rests_on") else []
    lines += part("What they expect to see", brief.get("expects")) + part("What would change their mind", brief.get("would_change"))
    also = [f"- {r['text'].rstrip('.')}: it would show {r['shows']}" if r.get("shows") else f"- {r['text']}" for r in brief.get("also_check", [])]
    also += [f"- {x} [always]" for x in ALWAYS] if data and not record else []
    lines += ["Also check:"] + also if also else []
    fixed = [f"- {k}: {brief['fixed'][k]}" for k in FIXED if brief.get("fixed", {}).get(k)]
    lines += ["Fixed before the run:"] + fixed if fixed else []
    lines += ["Figures agreed with the person:"] + [f"{k}. {line}" for k, line in enumerate(figure_lines(brief), 1)] if brief.get("figures") else []
    if brief.get("saved"):
        lines.append("Saved analyses the person chose (earlier results: claims to test, not evidence):")
        for k, passages in enumerate(analyses(brief["saved"]), 1):          # numbered as SHOW SAVED k opens them
            s = passages[0]
            ran_on = ", ".join(x for x in (s.get("data"), s.get("period"), "another person's data" if s.get("other") else "") if x)
            quotes = "; ".join((f"in its {p['where']} " if p.get("where") else "") + f"\"{p['passage']}\"" for p in passages if p.get("passage"))
            lines.append(f"{k}. " + " ".join(x for x in (s.get("when"), f"\"{s['question']}\"" if s.get("question") else "") if x)
                         + (f" ({ran_on})" if ran_on else "") + (f": {quotes}" if quotes else ""))
    if brief.get("set_aside"):
        lines.append("Set aside (considered and dropped): " + "; ".join(brief["set_aside"]))
    return "\n".join(lines)


def _section(report: str, name: str) -> Optional[str]:
    """The text under a heading of the report, up to the next heading; None when the report has no such heading."""
    m = re.search(rf"(?im)^#{{1,6}}[ \t]*{re.escape(name)}[ \t]*:?[ \t]*$", report or "")
    if not m:
        return None
    rest = report[m.end():]
    end = re.search(r"(?m)^(#{1,6}[ \t]+\S|> CHECK:)", rest)
    return rest[:end.start()] if end else rest


def _items(section: str) -> list:
    """The lines of a part, each without its list mark or emphasis."""
    out = []
    for line in (section or "").splitlines():
        line = re.sub(r"^[ \t]*(?:[-*+]|\d+[.)])[ \t]+", "", line).replace("**", "").replace("`", "").strip()
        if line:
            out.append(line)
    return out


def _verdict(items: list, label: str, words: tuple) -> tuple:
    """(the verdict word, the line) of the line that opens with the label (a pattern) and a colon; ('', '') when
    there is none."""
    for line in items:
        m = re.match(rf"(?i)(?:{label})[ \t]*[:\-][ \t]*(.*)$", line)
        if m:
            rest = m.group(1).lower()
            first = re.match(r"\W*(" + "|".join(words) + r")\b", rest)
            return (first.group(1) if first else next((w for w in words if re.search(rf"\b{w}\b", rest)), "")), line
    return "", ""


def outcome(report: str) -> dict:
    """What a report says against its brief: whether it has the part at all (stated), the verdict on what was expected
    (met, not met, cannot tell) and on what would change the person's mind (seen, not seen, cannot tell) - each ''
    where the report gives none, as for a part the brief left unsaid - the other lines of the part (the checks), and
    what did not fit."""
    against, misfit = _section(report, "Against the brief"), _section(report, "Did not fit")
    items = _items(against)
    expected, line_e = _verdict(items, r"expected|expectation", VERDICTS)
    changed, line_c = _verdict(items, r"(?:what )?would change their mind", SEEN)
    return {"stated": against is not None,
            "expected": expected, "would_change": changed,
            "checks": [x for x in items if x not in (line_e, line_c)],
            "did_not_fit": [x for x in _items(misfit) if not re.fullmatch(r"(?i)(nothing|none)\W*", x)]}
