"""The codebook and the coder (docs/CONTEXT_DESIGN.md §3.3, §6, §13, step 3): the seed, the file per user, the
vocabulary as the coder receives it, proposals stored and the coach's decisions; the batches, the coder's
messages, the parse of its reply (lines, an array, fences, a cut reply) and the mechanical validation - a code
outside the book, a proposal used in the same reply, a quote not verbatim, a bad tone, the language and rendering
rules, duplicate and unknown ids. Pure, no model. Run: python3 tests/analyst/test_coder.py"""
import json
import os
import shutil
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path[:0] = [os.path.dirname(os.path.abspath(__file__)), ROOT]
import _stubs  # noqa: F401,E402
from analyst import codebook as cb  # noqa: E402
from analyst import coder  # noqa: E402

passed, failed = [], []


def check(name, cond, detail=""):
    (passed if cond else failed).append(name)
    print(("  ok   " if cond else "  FAIL ") + name + ("" if cond else f"  <- {str(detail)[:500]}"))


# ---- the codebook ----
tmp = tempfile.mkdtemp()
book = cb.load(tmp)
groups = {c["group"] for c in book["codes"]}
check("the seed: 36 English codes in six groups, version 1, every one seeded with no uses; the file written under storage/<user>/context on first use",
      len(book["codes"]) == 36 and book["version"] == 1 and all(c["status"] == "seeded" and c["uses"] == 0 for c in book["codes"])
      and groups == {"body and health", "mind", "the session", "performance", "the exchange", "life"} and os.path.exists(os.path.join(tmp, "context", "codebook.json")), (len(book["codes"]), groups))
check("the seed's names are the design's (§13), snake_case, unique", {"fatigue", "freshness", "good_day", "bad_day", "plan_change", "work_study", "family_social", "travel", "test", "question"} <= cb.active_codes(book)
      and len(cb.active_codes(book)) == 36 and all(c["code"] == cb.normalise_code(c["code"]) for c in book["codes"]))
check("normalise_code: lower case, spaces and hyphens to underscores, nothing else, no doubled or edge underscores",
      cb.normalise_code(" Heavy Legs ") == "heavy_legs" and cb.normalise_code("plan-change!") == "plan_change" and cb.normalise_code("__a__b__") == "a_b" and cb.normalise_code(None) == "")
voc = cb.vocabulary_text(book)
check("the vocabulary as the coder receives it: one 'code: definition' line per active code, the seed's first line fatigue", voc.splitlines()[0] == "fatigue: tired, heavy, flat, no energy, needing rest" and len(voc.splitlines()) == 36 and "(proposed" not in voc)
book2 = cb.load(tmp)
check("load reads the file back rather than reseeding", book2["updated"] == book["updated"] and book2 == book)
book, added = cb.add_proposals(book, [{"code": "Heavy legs", "definition": "the legs feel heavy", "example": "C.2: Benene var tunge"},
                                      {"code": "fatigue", "definition": "already there"}, {"code": "no_def"}, {"code": "heavy legs", "definition": "twice"}], coder="m/x")
check("proposals: a new code with a definition is stored as proposed with its proposer, date and example; one the book holds, one without a definition and a repeat are nothing; the version does not move",
      added == ["heavy_legs"] and book["version"] == 1 and sum(1 for c in book["codes"] if c["status"] == "proposed") == 1
      and next(c for c in book["codes"] if c["code"] == "heavy_legs")["proposed_by"] == "m/x" and next(c for c in book["codes"] if c["code"] == "heavy_legs")["examples"] == ["C.2: Benene var tunge"], (added, book["version"]))
check("the proposal rides in the vocabulary last, marked, and in proposed_codes, not in active_codes",
      cb.vocabulary_text(book).splitlines()[-1] == "heavy_legs: the legs feel heavy (proposed, awaiting the coach)" and cb.proposed_codes(book) == {"heavy_legs"} and "heavy_legs" not in cb.active_codes(book))
cb.record_uses(book, {"fatigue": 31, "heavy_legs": 2})
check("record_uses: the last load's counts on the codes, zero for the rest", next(c["uses"] for c in book["codes"] if c["code"] == "fatigue") == 31 and next(c["uses"] for c in book["codes"] if c["code"] == "heavy_legs") == 2 and next(c["uses"] for c in book["codes"] if c["code"] == "sleep") == 0)
b3 = json.loads(json.dumps(book))
b3, ok = cb.confirm(b3, "heavy_legs")
check("confirm: the proposal becomes a confirmed code of the book; the version bumps", ok and b3["version"] == 2 and "heavy_legs" in cb.active_codes(b3) and not cb.proposed_codes(b3))
b4 = json.loads(json.dumps(book))
b4, ok4 = cb.confirm(b4, "heavy_legs", rename_to="leg heaviness")
check("confirm with a rename: the code under its new name, confirmed, version bumped; a rename onto an existing name is refused", ok4 and "leg_heaviness" in cb.active_codes(b4) and "heavy_legs" not in {c["code"] for c in b4["codes"]} and b4["version"] == 2
      and cb.confirm(json.loads(json.dumps(book)), "heavy_legs", rename_to="fatigue")[1] is False)
b5 = json.loads(json.dumps(book))
b5, ok5 = cb.confirm(b5, "heavy_legs", merge_into="fatigue")
check("confirm with a merge: the proposal leaves the book, the target stays, the version bumps; a merge into an unknown code is refused", ok5 and "heavy_legs" not in {c["code"] for c in b5["codes"]} and b5["version"] == 2
      and cb.confirm(json.loads(json.dumps(book)), "heavy_legs", merge_into="nothing")[1] is False)
b6 = json.loads(json.dumps(book))
b6, ok6 = cb.decline(b6, "heavy_legs")
check("decline: the proposal leaves the book without a version bump; declining a seeded code or an unknown one is nothing", ok6 and b6["version"] == 1 and "heavy_legs" not in {c["code"] for c in b6["codes"]}
      and cb.decline(json.loads(json.dumps(book)), "fatigue")[1] is False and len(cb.decline(json.loads(json.dumps(book)), "fatigue")[0]["codes"]) == 37)
cb.save(tmp, book)
with open(os.path.join(tmp, "context", "codebook.json"), "w") as fh:
    fh.write("{not json")
check("a codebook file that cannot be read is replaced by the seed", len(cb.load(tmp)["codes"]) == 36)
shutil.rmtree(tmp, ignore_errors=True)

# ---- the coder ----
passages = [{"id": "C.1", "date": "2026-08-02", "kind": "day_note", "author_role": "subject", "author_name": "", "text": "slept badly, legs flat all day"},
            {"id": "C.2", "date": "2026-08-03", "kind": "activity_message", "author_role": "subject", "author_name": "", "text": "Benene var tunge fra den første stigning, men det gik."},
            {"id": "C.3", "date": "2026-08-03", "kind": "activity_message", "author_role": "coach", "author_name": "Kim", "text": "Keep the next two days easy."},
            {"id": "C.4", "date": "2026-08-05", "kind": "tag", "author_role": "subject", "author_name": "", "text": "sick"},
            {"id": "C.5", "date": "2026-08-06", "kind": "plan_note", "author_role": "coach", "author_name": "Kim", "text": "x" * 500}]
check("batches: by count and by characters, in order, the constants read at the call", [len(b) for b in coder.batches(passages, max_n=2)] == [2, 2, 1] and [len(b) for b in coder.batches(passages, max_chars=60)] == [1, 1, 2, 1]
      and len(coder.batches(passages)) == 1 and coder.batches([]) == [])
system, user = coder.coder_messages("fatigue: tired, heavy\nsleep: how the night went", passages[:3])
check("the coder's messages: the system says the work and the JSON-lines format with the rendering rule; the user carries the vocabulary as data, then each passage under its id with its day, kind and author (a coach's name, not the subject's)",
      system.startswith("You are the Coder") and '"text_en"' in system and "one JSON object per line" in system and "English rendering" in system
      and user.startswith("VOCABULARY (code: definition):\nfatigue: tired, heavy\nsleep: how the night went\n\nPASSAGES (3; id, day, kind, author):\n[C.1] 2026-08-02 · day_note · subject\nslept badly, legs flat all day\n\n[C.2] 2026-08-03 · activity_message · subject\nBenene")
      and "[C.3] 2026-08-03 · activity_message · coach Kim\nKeep the next two days easy.\n" in user, user[:400])
lines = ('{"id": "C.1", "codes": ["sleep", "fatigue"], "tone": "negative", "quotes": {"sleep": "slept badly", "fatigue": "legs flat all day"}, "lang": "en"}\n'
         '{"id": "C.2", "codes": ["fatigue", "heavy legs"], "tone": "mixed", "quotes": {"fatigue": "Benene  var tunge", "heavy legs": "tunge"}, "lang": "da", "text_en": "The legs were heavy from the first climb, but it went.", "propose": [{"code": "heavy legs", "definition": "the legs feel heavy"}]}\n'
         '{"id": "C.3", "codes": ["instruction", "nonsense", "sleep"], "tone": "bossy", "quotes": {"instruction": "Keep the next two days easy", "nonsense": "Keep", "sleep": "sleep well"}, "lang": "en", "text_en": "ignored for an English passage"}\n'
         '{"id": "C.4", "codes": ["illness"], "tone": "negative", "quotes": {"illness": "sick"}, "lang": "da"}\n'
         '{"id": "C.9", "codes": [], "tone": "neutral", "lang": "en"}\n'
         '{"id": "C.4", "codes": ["illness"], "tone": "negative", "quotes": {"illness": "sick"}, "lang": "en"}\n')
items, cut = coder.parse_reply("```json\n" + lines + "```")
check("parse_reply: JSON lines inside fences, every item with an id; not cut", len(items) == 6 and not cut and items[0]["id"] == "C.1")
arr, cut_a = coder.parse_reply(json.dumps([json.loads(l) for l in lines.strip().splitlines()]))
check("parse_reply: one JSON array works the same; a bare object too; an empty reply is nothing", len(arr) == 6 and not cut_a and coder.parse_reply('{"id": "C.1", "codes": []}')[0] == [{"id": "C.1", "codes": []}] and coder.parse_reply("") == ([], False))
cut_items, cut_flag = coder.parse_reply(lines + '{"id": "C.5", "codes": ["instruction"], "tone": "neu')
check("parse_reply: a reply cut mid-line keeps the lines that parsed and says it was cut; chatter before the lines is skipped", len(cut_items) == 6 and cut_flag is True
      and coder.parse_reply("Here you go:\n" + lines)[0][0]["id"] == "C.1" and coder.parse_reply("Here you go:\n" + lines)[1] is False)
v = coder.validate(items, passages, {"fatigue", "sleep", "instruction", "illness"}, set())
rows = {(r["id"], r["code"]): r for r in v["rows"]}
check("validate: codes of the book with verbatim quotes become rows (whitespace normalised); the proposal made in the reply is usable in it and its rows are marked proposed",
      set(rows) == {("C.1", "sleep"), ("C.1", "fatigue"), ("C.2", "fatigue"), ("C.2", "heavy_legs"), ("C.3", "instruction"), ("C.4", "illness")}
      and rows[("C.2", "fatigue")]["quote"] == "Benene var tunge" and rows[("C.2", "heavy_legs")]["status"] == "proposed" and rows[("C.1", "sleep")]["status"] == "codebook", sorted(rows))
check("validate: a code outside the book without a proposal is dropped (nonsense), a quote not in the passage is dropped (sleep on C.3), a tone outside the four becomes neutral and is counted, an unknown id and a duplicate id are counted",
      v["dropped"] == {"unknown_code": 1, "quote": 1, "tone": 1, "unknown_id": 1, "duplicate": 1, "rendering_missing": 1} and rows[("C.3", "instruction")]["tone"] == "neutral", dict(v["dropped"]))
check("validate: the rendering rules - a Danish passage keeps its lang and rendering; an English passage's text_en is dropped; a non-English passage without a rendering is counted as missing (its lang kept)",
      v["renderings"]["C.2"] == {"lang": "da", "text_en": "The legs were heavy from the first climb, but it went."} and v["renderings"]["C.3"] == {"lang": "en", "text_en": ""}
      and v["renderings"]["C.4"] == {"lang": "da", "text_en": ""} and v["dropped"]["rendering_missing"] == 1, v["renderings"])
check("validate: the proposal carries its definition and an example from the passage; seen = the ids the reply answered (a duplicate and an unknown id not among them twice)",
      v["proposals"] == [{"code": "heavy_legs", "definition": "the legs feel heavy", "example": "C.2: Benene var tunge fra den første stigning, men det gik."}] and v["seen"] == {"C.1", "C.2", "C.3", "C.4"}, v["proposals"])
# the rendering-missing and length rules, and a proposed code of the book from an earlier load
v2 = coder.validate([{"id": "C.2", "codes": ["fatigue"], "tone": "negative", "quotes": {"fatigue": "tunge"}, "lang": "da"},
                     {"id": "C.5", "codes": ["instruction"], "tone": "neutral", "quotes": {"instruction": "xxxx"}, "lang": "no", "text_en": "short"},
                     {"id": "C.4", "codes": ["old_proposal"], "tone": "neutral", "quotes": {"old_proposal": "sick"}, "lang": "en"},
                     {"id": "C.1", "codes": ["Sleep"], "tone": "NEGATIVE", "quotes": {"Sleep": "“slept badly”"}}],
                    passages, {"fatigue", "sleep", "instruction"}, {"old_proposal"})
check("validate: a non-English passage without a rendering is counted missing; a rendering far shorter than the original is dropped and counted; a proposal stored by an earlier load is usable, its rows marked proposed; "
      "a code name and a tone are read case-insensitively, curly quotes around a quote are tolerated, a missing lang is en",
      v2["dropped"]["rendering_missing"] == 1 and v2["dropped"]["rendering_length"] == 1 and v2["renderings"]["C.5"] == {"lang": "no", "text_en": ""}
      and [(r["id"], r["code"], r["status"]) for r in v2["rows"]] == [("C.2", "fatigue", "codebook"), ("C.5", "instruction", "codebook"), ("C.4", "old_proposal", "proposed"), ("C.1", "sleep", "codebook")]
      and v2["rows"][3]["tone"] == "negative" and v2["renderings"]["C.1"] == {"lang": "en", "text_en": ""}, (dict(v2["dropped"]), v2["rows"]))
# ---- the reading's format 2 (patch 0198): each code with its direction, basis and days; earlier passages for reference ----
check("the system says the reading: earlier passages for reference only, and for each code its quote, which way it points (a denial points better), said or inferred, and the days it is about - the activity's day for a passage on one; the reply's codes are objects",
      "for reference only" in system and "do not code them" in system and "worse, better or neutral" in system and "denies a problem points better for it" in system
      and "said or inferred" in system and "the activity's day unless it says otherwise" in system and '"codes": [{"code": "...", "quote": "...", "direction": "worse", "basis": "said", "about": ""}]' in system
      and coder.READING_VERSION == 2, system[:300])
_pa = [dict(passages[0], id="C.7", date="2026-08-01", activity_id="", activity_date=""), {"id": "C.8", "date": "2026-08-01", "kind": "activity_message", "author_role": "coach", "author_name": "Kim", "text": "Easy tomorrow. " * 40},
       dict(passages[1], id="C.9", activity_date="2026-08-02")]
_sy, _us = coder.coder_messages("fatigue: tired", [_pa[2]], earlier=_pa[:2])
check("the messages with earlier passages: each on a line of its own, without brackets, the day, kind and author, cut at EARLIER_PASSAGE_CHARS; then the passage to code, its head naming the activity's day when it is another",
      "EARLIER PASSAGES (2; for reference, not to code):\nC.7 · 2026-08-01 · day_note · subject: slept badly, legs flat all day\nC.8 · 2026-08-01 · activity_message · coach Kim: Easy tomorrow." in _us
      and _us.split("\nC.8 ")[1].split("\n")[0].endswith(" …") and len(_us.split("\nC.8 ")[1].split("\n")[0]) < coder.EARLIER_PASSAGE_CHARS + 80
      and "PASSAGES (1; id, day, kind, author):\n[C.9] 2026-08-03 · activity_message · subject · the activity of 2026-08-02\nBenene" in _us
      and _us.index("EARLIER PASSAGES") < _us.index("PASSAGES (1;") and _us.count("[C.") == 1, _us)
_all = [{"id": f"C.{i}", "date": d, "text": t} for i, (d, t) in enumerate([("2026-07-01", "long ago"), ("2026-08-01", "a"), ("2026-08-02", "b" * 900), ("2026-08-03", "c"), ("2026-08-03", "d"), ("2026-08-04", "e")], 1)]
check("earlier_for: the passages before the batch's first one, oldest first - at most EARLIER_PASSAGES, within EARLIER_DAYS of it, at most EARLIER_CHARS in all (each counted at most EARLIER_PASSAGE_CHARS); none for the first passage or an unknown one",
      [p["id"] for p in coder.earlier_for(_all, [_all[4]])] == ["C.2", "C.3", "C.4"] and [p["id"] for p in coder.earlier_for(_all, [_all[4]], max_n=2)] == ["C.3", "C.4"]
      and [p["id"] for p in coder.earlier_for(_all, [_all[5]], max_chars=401)] == ["C.4", "C.5"] and [p["id"] for p in coder.earlier_for(_all, [_all[5]], max_chars=403)] == ["C.2", "C.3", "C.4", "C.5"] and coder.earlier_for(_all, [_all[0]]) == [] and coder.earlier_for(_all, [{"id": "C.99"}]) == []
      and coder.earlier_for(_all, []) == [], [p["id"] for p in coder.earlier_for(_all, [_all[4]])])
check("about_days: a day or a range as written, a reversed range put right, the passage's own day as empty; a value that is not a day, or outside 60 days before and 30 after the passage's own, is refused",
      coder.about_days("2026-08-01", "2026-08-03") == ("2026-08-01", True) and coder.about_days("2026-08-01..2026-08-02", "2026-08-03") == ("2026-08-01..2026-08-02", True)
      and coder.about_days("2026-08-02..2026-08-01", "2026-08-03") == ("2026-08-01..2026-08-02", True) and coder.about_days("2026-08-03", "2026-08-03") == ("", True) and coder.about_days("", "2026-08-03") == ("", True)
      and coder.about_days("yesterday", "2026-08-03") == ("", False) and coder.about_days("2026-01-01", "2026-08-03") == ("", False) and coder.about_days("2026-10-01", "2026-08-03") == ("", False)
      and coder.about_days("2026-8-1", "2026-08-03") == ("", False))
v3 = coder.validate([{"id": "C.1", "codes": [{"code": "sleep", "quote": "slept badly", "direction": "worse", "basis": "said", "about": "2026-08-01..2026-08-02"},
                                             {"code": "fatigue", "quote": "legs flat all day", "direction": "Better", "basis": "INFERRED", "about": "2026-08-02"}], "tone": "negative", "lang": "en"},
                     {"id": "C.2", "codes": [{"code": "fatigue", "quote": "Benene var tunge", "direction": "awful", "basis": "guessed", "about": "last week"}], "tone": "mixed", "lang": "da", "text_en": "The legs were heavy from the first climb, but it went."},
                     {"id": "C.3", "codes": ["instruction"], "quotes": {"instruction": "Keep the next two days easy"}, "tone": "neutral", "lang": "en"}],
                    passages, {"fatigue", "sleep", "instruction"}, set())
r3 = {(r["id"], r["code"]): r for r in v3["rows"]}
check("validate, the reading's format 2: each code's direction, basis and days kept (case aside, a passage's own day emptied); a direction, a basis or days that are not one of theirs left empty and counted, the code kept; "
      "a code given by name with its quote in quotes (format 1) still read, with none of the three",
      (r3[("C.1", "sleep")]["direction"], r3[("C.1", "sleep")]["basis"], r3[("C.1", "sleep")]["about"]) == ("worse", "said", "2026-08-01..2026-08-02")
      and (r3[("C.1", "fatigue")]["direction"], r3[("C.1", "fatigue")]["basis"], r3[("C.1", "fatigue")]["about"]) == ("better", "inferred", "")
      and (r3[("C.2", "fatigue")]["direction"], r3[("C.2", "fatigue")]["basis"], r3[("C.2", "fatigue")]["about"]) == ("", "", "") and r3[("C.2", "fatigue")]["quote"] == "Benene var tunge"
      and v3["dropped"] == {"direction": 1, "basis": 1, "about": 1}
      and (r3[("C.3", "instruction")]["direction"], r3[("C.3", "instruction")]["basis"], r3[("C.3", "instruction")]["about"]) == ("", "", ""), (v3["rows"], dict(v3["dropped"])))
check("report_line: the sentence of a pass", coder.report_line({"passages": 212, "coded": 201, "rendered": 180, "proposed": 2, "unanswered": 3, "failed_batches": 1})
      == "201 of 212 coded, 180 rendered into English, 2 codes proposed, 3 not read by the coder, 1 batch failed" and coder.report_line({"passages": 0}) == "nothing to code"
      and coder.report_line({"passages": 4, "coded": 4}) == "4 of 4 coded"
      and coder.report_line({"passages": 9, "coded": 5, "labels": 2, "copies": 1}) == "5 of 9 coded, 2 tags left as labels, 1 copy read as the passage it repeats"
      and coder.report_line({"passages": 9, "coded": 5, "labels": 1, "copies": 3}) == "5 of 9 coded, 1 tag left as a label, 3 copies read as the passages they repeat")

# ---- the store of coded passages (D1's fallback, 2026-10-14) ----
from analyst.coded import CodedStore, passage_key
tmp2 = tempfile.mkdtemp()
st = CodedStore(tmp2, "k-one").load()
ps = [{"id": "C.1", "kind": "day_note", "date": "2026-08-02", "source_id": "11", "text": "slept badly"},
      {"id": "C.2", "kind": "activity_message", "date": "2026-08-03", "source_id": "22", "text": "Benene var tunge"},
      {"id": "C.3", "kind": "tag", "date": "2026-08-05", "source_id": "", "text": "sick"}]
check("a fresh store knows nothing: every passage is to do; keys are kind:source_id, or kind:day:hash without a source id",
      st.lookup(ps) == ({}, ps) and passage_key(ps[0]) == "day_note:11" and passage_key(ps[2]).startswith("tag:2026-08-05:") and len(passage_key(ps[2])) == len("tag:2026-08-05:") + 12)
rows = [{"id": "C.1", "code": "sleep", "tone": "negative", "quote": "slept badly", "status": "codebook"}, {"id": "C.2", "code": "fatigue", "tone": "mixed", "quote": "tunge", "status": "codebook"}]
rend = {"C.1": {"lang": "en", "text_en": ""}, "C.2": {"lang": "da", "text_en": "The legs were heavy"}}
check("remember stores the answered passages with their rendering and codes and returns the count; the unanswered one is not stored", st.remember(ps, rows, rend, "m/x", 1) == 2 and sorted(st.entries) == ["activity_message:22", "day_note:11"]
      and st.entries["activity_message:22"] == {"hash": st.entries["activity_message:22"]["hash"], "date": "2026-08-03", "lang": "da", "text_en": "The legs were heavy", "codes": [{"code": "fatigue", "tone": "mixed", "quote": "tunge", "status": "codebook"}], "coder": "m/x", "codebook_version": 1})
st.save()
st2 = CodedStore(tmp2, "k-one").load()
known, todo = st2.lookup([dict(ps[0]), dict(ps[1], id="C.9"), dict(ps[2]), dict(ps[0], id="C.4", text="slept badly, then well")])
check("a reload reads the file back; lookup knows a passage by key and text hash whatever its id this load, and sends a changed text and the unknown tag to the coder",
      set(known) == {"C.1", "C.9"} and known["C.9"]["text_en"] == "The legs were heavy" and [p["id"] for p in todo] == ["C.3", "C.4"], (sorted(known), [p["id"] for p in todo]))
st3 = CodedStore(tmp2, "k-three").load()
st3.remember(ps[:2], [dict(rows[0], direction="worse", basis="said", about="2026-08-01"), rows[1]], rend, "m/x", 1, reading=2)
st3.save()
st3b = CodedStore(tmp2, "k-three").load()
k3, t3 = st3b.lookup(ps[:2], reading=2)
kold, told = st2.lookup([dict(ps[0]), dict(ps[1], id="C.9")], reading=2)
check("the reading's format (patch 0198): remember keeps each code's direction, basis and days and marks the entry with the format; lookup under format 2 knows those entries and sends an entry read under format 1 (no mark) to the coder again",
      st3b.entries["day_note:11"]["reading"] == 2 and st3b.entries["day_note:11"]["codes"] == [{"code": "sleep", "tone": "negative", "quote": "slept badly", "status": "codebook", "direction": "worse", "basis": "said", "about": "2026-08-01"}]
      and set(k3) == {"C.1", "C.2"} and t3 == [] and kold == {} and [p["id"] for p in told] == ["C.1", "C.9"], (st3b.entries, sorted(k3), [p["id"] for p in told]))
check("another key mark is another store", CodedStore(tmp2, "k-two").load().entries == {} and os.path.dirname(CodedStore(tmp2, "k-two").path).endswith(os.path.join("context", "k-two")))
big = CodedStore(tmp2, "k-big")
big.entries = {f"day_note:{i}": {"hash": "h", "date": f"2026-{1 + i % 12:02d}-{1 + i % 28:02d}", "codes": []} for i in range(7000)}
check("prune keeps the newest by day under the cap", big.prune() == 1000 and len(big.entries) == 6000 and min(e["date"] for e in big.entries.values()) >= "2026-02")
shutil.rmtree(tmp2, ignore_errors=True)

print(f"\n{len(passed)} passed, {len(failed)} failed")
sys.exit(1 if failed else 0)
