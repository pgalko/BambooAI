"""The codebook screen's module side (docs/CONTEXT_DESIGN.md §7 S3, step 6, 2026-10-16): the book as the page shows it
(the view: version, counts, proposals first with their examples, the codes by group in the seed's order, confirmed
last), the reasons a decision is refused before it is tried, the import's validation and the replacement that never
lets the version go back. Pure, no model. Run: python3 tests/analyst/test_codebook.py"""
import json
import os
import shutil
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path[:0] = [os.path.dirname(os.path.abspath(__file__)), ROOT]
import _stubs  # noqa: F401,E402
from analyst import codebook as cb  # noqa: E402

passed, failed = [], []


def check(name, cond, detail=""):
    (passed if cond else failed).append(name)
    print(("  ok   " if cond else "  FAIL ") + name + ("" if cond else f"  <- {str(detail)[:500]}"))


tmp = tempfile.mkdtemp()
book = cb.load(tmp)
check("the seed's groups in the seed's order: the page lists them so", cb.seed_groups() == ["body and health", "mind", "the session", "performance", "the exchange", "life"], cb.seed_groups())

# ---- the view ----
v0 = cb.view(book)
check("the view of a fresh book: version 1, 36 codes, no proposals, nothing used; six groups in the seed's order, every code seeded with its definition and no uses",
      v0["version"] == 1 and v0["counts"] == {"codes": 36, "proposed": 0, "used": 0} and v0["proposals"] == [] and [g["name"] for g in v0["groups"]] == cb.seed_groups()
      and sum(len(g["codes"]) for g in v0["groups"]) == 36 and all(c["status"] == "seeded" and c["definition"] and c["uses"] == 0 for g in v0["groups"] for c in g["codes"])
      and {"code", "definition", "status", "uses"} == set(v0["groups"][0]["codes"][0]), (v0["counts"], [g["name"] for g in v0["groups"]]))
book, added = cb.add_proposals(book, [{"code": "Heavy legs", "definition": "the legs feel heavy", "example": "C.2: Benene var tunge"},
                                      {"code": "coach flag", "definition": "a private note to watch something", "example": "C.9: Private: check the sleep log"}], coder="x/coder-1", when="2026-10-15T10:00:00Z")
cb.record_uses(book, {"fatigue": 31, "heavy_legs": 2, "sleep": 4}, when="2026-10-15T10:00:00Z")
v1 = cb.view(book)
check("the view with proposals: they come first with their definition, proposer, date, example passages and uses; the counts say 36 codes, 2 proposed, 2 used; the groups hold the active codes only",
      [p["code"] for p in v1["proposals"]] == ["heavy_legs", "coach_flag"] and v1["proposals"][0] == {"code": "heavy_legs", "definition": "the legs feel heavy", "proposed_by": "x/coder-1", "proposed_on": "2026-10-15T10:00:00Z", "examples": ["C.2: Benene var tunge"], "uses": 2}
      and v1["counts"] == {"codes": 36, "proposed": 2, "used": 2} and sum(len(g["codes"]) for g in v1["groups"]) == 36 and v1["updated"] == "2026-10-15T10:00:00Z"
      and next(c for g in v1["groups"] for c in g["codes"] if c["code"] == "fatigue")["uses"] == 31, (v1["counts"], v1["proposals"]))
b2, ok = cb.confirm(json.loads(json.dumps(book)), "heavy_legs")
v2 = cb.view(b2)
check("after a confirmation: the code sits in a 'confirmed' group after the seed's six, status confirmed with its uses kept; one proposal left; version 2",
      ok and v2["version"] == 2 and [g["name"] for g in v2["groups"]] == cb.seed_groups() + ["confirmed"] and v2["groups"][-1]["codes"] == [{"code": "heavy_legs", "definition": "the legs feel heavy", "status": "confirmed", "uses": 2}]
      and v2["counts"] == {"codes": 37, "proposed": 1, "used": 3}, ([g["name"] for g in v2["groups"]], v2["counts"]))
b2b = json.loads(json.dumps(b2)); b2b["codes"].append({"code": "odd_one", "group": "", "definition": "no group", "status": "confirmed", "uses": 0}); b2b["codes"].append({"code": "zeta", "group": "extra", "definition": "another group", "status": "seeded", "uses": 0})
v2b = cb.view(b2b)
check("a group the seed lacks lists after the seed's, 'confirmed' after it, a code without a group under 'other' last",
      [g["name"] for g in v2b["groups"]] == cb.seed_groups() + ["extra", "confirmed", "other"], [g["name"] for g in v2b["groups"]])

# ---- the reasons a decision is refused ----
check("why_not: nothing to refuse for a proposal confirmed as it is, renamed to a free name, or merged into an active code",
      cb.why_not(book, "heavy_legs") == "" and cb.why_not(book, "heavy_legs", rename_to="leg heaviness") == "" and cb.why_not(book, "heavy_legs", merge_into="fatigue") == "")
check("why_not: the reasons - an unknown proposal (a seeded code is not one), an empty new name, a name the book has, a merge target that is not an active code (a proposal is not)",
      cb.why_not(book, "nothing") == "there is no proposal named nothing" and cb.why_not(book, "fatigue") == "there is no proposal named fatigue" and cb.why_not(book, "") == "there is no proposal named ?"
      and cb.why_not(book, "heavy_legs", rename_to="  ") == "the new name is empty" and cb.why_not(book, "heavy_legs", rename_to="Fatigue") == "the book already has a code named fatigue"
      and cb.why_not(book, "heavy_legs", merge_into="nothing") == "nothing is not a code of the book to merge into" and cb.why_not(book, "heavy_legs", merge_into="coach_flag") == "coach_flag is not a code of the book to merge into",
      [cb.why_not(book, "nothing"), cb.why_not(book, "heavy_legs", rename_to="Fatigue"), cb.why_not(book, "heavy_legs", merge_into="coach_flag")])
check("why_not: a rename onto the proposal's own name is no refusal (confirm handles it as a plain confirmation)", cb.why_not(book, "heavy_legs", rename_to="heavy_legs") == "")
check("why_not and confirm agree: every case why_not refuses, confirm refuses too; what why_not allows, confirm does",
      all(cb.confirm(json.loads(json.dumps(book)), *a, **k)[1] is False for a, k in [(("nothing",), {}), (("heavy_legs",), {"rename_to": "fatigue"}), (("heavy_legs",), {"merge_into": "coach_flag"})])
      and all(cb.confirm(json.loads(json.dumps(book)), *a, **k)[1] is True for a, k in [(("heavy_legs",), {}), (("heavy_legs",), {"rename_to": "leg heaviness"}), (("heavy_legs",), {"merge_into": "fatigue"})]))

# ---- the import ----
good = {"version": 3, "updated": "2026-10-01T00:00:00Z", "codes": [{"code": " Heavy Legs ", "group": "body and health", "definition": "the legs feel heavy", "status": "confirmed", "uses": "7"},
                                                                   {"code": "x_flag", "definition": "a flag", "status": "proposed", "proposed_by": "m", "proposed_on": "2026-09-30", "examples": ["C.1: a line", ""]},
                                                                   {"code": "plain", "definition": "no status given"}]}
imp, why = cb.validate_import(good)
check("validate_import: a good file - the names normalised, the uses read, a proposal keeping its proposer, date and non-empty examples (grouped as proposed), a missing status read as seeded, the version kept",
      why == "" and imp["version"] == 3 and [c["code"] for c in imp["codes"]] == ["heavy_legs", "x_flag", "plain"] and imp["codes"][0]["uses"] == 7 and imp["codes"][0]["group"] == "body and health"
      and imp["codes"][1] == {"code": "x_flag", "group": "proposed", "definition": "a flag", "status": "proposed", "uses": 0, "proposed_by": "m", "proposed_on": "2026-09-30", "examples": ["C.1: a line"]}
      and imp["codes"][2]["status"] == "seeded" and imp["codes"][2]["group"] == "" and imp["updated"] == "2026-10-01T00:00:00Z", (why, imp))
bad = [([], "the file is not a codebook: it needs a list of codes"), ({"codes": "x"}, "the file is not a codebook: it needs a list of codes"), ({"codes": []}, "the file holds no codes"),
       ({"codes": ["x"]}, "entry 1 is not an object"), ({"codes": [{"definition": "d"}]}, "entry 1 has no code"), ({"codes": [{"code": "a", "definition": "d"}, {"code": "A", "definition": "d"}]}, "the code a appears twice"),
       ({"codes": [{"code": "a"}]}, "the code a has no definition"), ({"codes": [{"code": "a", "definition": "d", "status": "odd"}]}, "the code a has an unknown status (odd)")]
check("validate_import: the refusals name their reason - not a book, no codes, an entry that is not an object, no code, a duplicate, no definition, an unknown status",
      all(cb.validate_import(o) == (None, r) for o, r in bad), [cb.validate_import(o) for o, r in bad])
check("validate_import: a version that is not a number reads as 1, a uses that is not a count as 0", cb.validate_import({"version": "x", "codes": [{"code": "a", "definition": "d", "uses": "many"}]})[0]["version"] == 1
      and cb.validate_import({"version": "x", "codes": [{"code": "a", "definition": "d", "uses": "many"}]})[0]["codes"][0]["uses"] == 0)

# ---- the replacement ----
cb.save(tmp, b2)                                                    # the user's book at version 2
rep = cb.replace(tmp, imp, when="2026-10-16T00:00:00Z")
check("replace: the imported book in place of the user's, its version one more than the greater of the two (3 imported, 2 held -> 4), written to the file",
      rep["version"] == 4 and [c["code"] for c in rep["codes"]] == ["heavy_legs", "x_flag", "plain"] and rep["updated"] == "2026-10-16T00:00:00Z" and cb.load(tmp)["version"] == 4 and len(cb.load(tmp)["codes"]) == 3)
rep2 = cb.replace(tmp, cb.validate_import({"version": 1, "codes": [{"code": "one", "definition": "d"}]})[0])
check("replace: a file older than the book never takes the version back (4 held, 1 imported -> 5)", rep2["version"] == 5 and cb.load(tmp)["version"] == 5)
check("the view of an imported book: its proposal first, the groups it names, 'other' for the ungrouped", cb.view(rep)["proposals"][0]["code"] == "x_flag" and [g["name"] for g in cb.view(rep)["groups"]] == ["body and health", "other"])
shutil.rmtree(tmp, ignore_errors=True)

print(f"\n{len(passed)} passed, {len(failed)} failed")
sys.exit(1 if failed else 0)
