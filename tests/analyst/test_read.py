"""READ (docs/DOCUMENTS_DESIGN.md): the pipeline - BM25 candidates with neighbours, the Reader's turn, verbatim
neighbours, the Reader's messages, the parse of its reply, the verbatim check, the digest - end to end
over a thread folder with a scripted reader; then the session: READ turns, the
budget of three, SHOW READ k numbered along the path, the report guard accepting a number from a cited
passage and disclosing a passage that is not in the documents. Run: python3 tests/analyst/test_read.py"""
import os, sys, json, tempfile, shutil, hashlib, re
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path[:0] = [os.path.dirname(os.path.abspath(__file__)), ROOT, os.path.join(ROOT, "delve")]
import _stubs  # noqa: F401
from bambooai import documents as D, reading as R
from analyst import Session, Budget, Notebook, NotebookStore, parse_turn, report as rep
from analyst.session import LAST_TURNS_LINE as LAST_LINE
from kernel import PersistentKernel

passed, failed = [], []
def check(name, cond, detail=""):
    (passed if cond else failed).append(name); print(("  ok   " if cond else "  FAIL ") + name + ("" if cond else f"  <- {str(detail)[:400]}"))

# ---- the pieces ----
units = [{"id": "D1.1", "doc": "D1", "file": "paper.pdf", "kind": "heading", "page": 1, "text": "Methods"},
         {"id": "D1.2", "doc": "D1", "file": "paper.pdf", "kind": "paragraph", "page": 1, "text": "Forty-two athletes aged 40 to 68 were followed for twelve weeks."},
         {"id": "D1.3", "doc": "D1", "file": "paper.pdf", "kind": "paragraph", "page": 2, "text": "The wet season came early: rainfall was 40% above the ten-year average."},
         {"id": "D1.4", "doc": "D1", "file": "paper.pdf", "kind": "table", "page": 2, "table_no": 1, "caption": "Table 1. Groups", "rows": [["Group", "n"], ["40-49", "15"]]},
         {"id": "D1.5", "doc": "D1", "file": "paper.pdf", "kind": "paragraph", "page": 3, "text": "Recovery was shorter for athletes with a steady weekly load."}]
bm = R.BM25([R.tokens(R.unit_text(u)) for u in units])
sc = bm.scores(R.tokens("how many athletes were followed"))
check("BM25: the passage with the query's words ranks first", sc.index(max(sc)) == 1, sc)
cand = R.select(units, "rainfall above average", top_k=1)
check("select: the top unit with its neighbours (the paragraph before it, the table after), not the heading",
      [u["id"] for u in cand] == ["D1.2", "D1.3", "D1.4"], [u["id"] for u in cand])
def hvec(text, dims=32):
    v = [0.0] * dims
    for w in R.tokens(text):
        v[int(hashlib.md5(w.encode()).hexdigest(), 16) % dims] += 1
    return v
check("where: 'paper.pdf p.2' for a PDF unit; the heading trail for the others", R.where(units[2]) == "paper.pdf p.2" and R.where({"file": "m.md", "section": "Agenda > Q3"}) == "m.md §Agenda > Q3")
system, user = R.reader_messages("what about rainfall", cand, "D1")
check("reader_messages: the system asks for exact quotes under ids; the user carries the question, the scope and each candidate with id and place",
      system.startswith("You are the Reader") and "quoted exactly" in system and user.startswith("QUESTION: what about rainfall\nSCOPE: D1") and "[D1.3] (paper.pdf p.2) The wet season" in user, user[:300])
reply = ('- [D1.3] "rainfall was 40% above the ten-year average"\n- [D1.2] "Forty-two athletes were followed"\n- [D1.4] "Group | n 40-49 | 15"\n- [D9.9] "nothing here"\n- [D1.3] "tiny"\n'
         'SUMMARY: The season was wet [D1.3] and forty-two athletes took part [D1.2].')
passages, summary, nothing, cut = R.parse_reader(reply)
check("parse_reader: five passage lines and the summary, not cut off", len(passages) == 5 and passages[0] == ("D1.3", "rainfall was 40% above the ten-year average") and summary.startswith("The season was wet") and not nothing and not cut, (passages, summary))
cut_reply = '- [D1.3] "rainfall was 40% above the ten-year average"\n- [D1.2] "Forty-two athletes aged 40 to 68 were followed for twelve weeks."\n- [D1.5] "Recovery was shorter for athletes with a steady weekly load'
p2, s2, n2, cut2 = R.parse_reader(cut_reply)
check("parse_reader: a reply ending mid-quote with no SUMMARY is cut off; the whole lines before it are kept", cut2 and len(p2) == 2 and s2 == "", (p2, s2, cut2))
dg_cut = R.compose_digest([("D1.3", "rainfall was 40% above the ten-year average")], 0, "", False, {u["id"]: u for u in units}, cut_off=True)
check("compose_digest: the cut-off is said in the notes, and the summary's absence too", "reply was cut off by its output cap" in dg_cut and "(the reader gave no summary)" in dg_cut, dg_cut)
kept, dropped = R.verify(passages, {u["id"]: u for u in units})
check("verify: the verbatim excerpt kept; a paraphrase ('athletes were followed' is not contiguous), an unknown id and a too-short quote dropped; a table excerpt matches its embedding text",
      kept == [("D1.3", "rainfall was 40% above the ten-year average"), ("D1.4", "Group | n 40-49 | 15")] and dropped == 3, (kept, dropped))
check("parse_reader: NOTHING ANSWERS", R.parse_reader("NOTHING ANSWERS - the passages are about training load.") == ([], "the passages are about training load.", True, False))
check("verify: at most MAX_PASSAGES kept", len(R.verify([("D1.3", "rainfall was 40% above the ten-year average " + " ")] * 1 + [("D1.2", f"Forty-two athletes aged 40 to 68")] * 1, {u["id"]: u for u in units})[0]) <= R.MAX_PASSAGES)
noise = [{"id": "D9.1", "doc": "D9", "file": "n.pdf", "kind": "paragraph", "page": 1, "text": "9002 rpA 51"}, {"id": "D9.2", "doc": "D9", "file": "n.pdf", "kind": "paragraph", "page": 1, "text": "2"},
         {"id": "D9.3", "doc": "D9", "file": "n.pdf", "kind": "heading", "page": 1, "text": "2.10 Art and Music as By-Products of the Compression Progress Drive"},
         {"id": "D9.4", "doc": "D9", "file": "n.pdf", "kind": "paragraph", "page": 1, "text": "Works of art and music may have important purposes beyond their social aspects."}]
check("substantive: page numbers, arXiv stamps and headings are not candidates; a sentence is", [R.substantive(u) for u in noise] == [False, False, False, True])
cand_n = R.select(noise, "art and music purposes", top_k=3)
check("select: only the substantive unit is a candidate, headings and page numbers are not even neighbours", [u["id"] for u in cand_n] == ["D9.4"], [u["id"] for u in cand_n])
check("digest_peek: the summary line when there is one, else the first passage", R.digest_peek("PASSAGES (verbatim, each with its locator):\n- [D1.3] (p p.2) \"x y z\"\nSUMMARY:\nThe season was wet [D1.3].") == "The season was wet [D1.3]." and R.digest_peek("PASSAGES (verbatim, each with its locator):\n- [D1.3] (p p.2) \"x y z\"\nSUMMARY:\n(the reader gave no summary)") == "(the reader gave no summary)" and R.digest_peek("PASSAGES: none - the reader quoted nothing.") == "PASSAGES: none - the reader quoted nothing.")
check("the Reader is asked for the sentence or two that answers, at most ten lines, not whole paragraphs", "sixty words at most" in R.READER_SYSTEM and "at most ten lines" in R.READER_SYSTEM)
digest = R.compose_digest(kept, dropped, summary, False, {u["id"]: u for u in units})
check("compose_digest: the passages with their locators, the dropped note, the summary",
      digest.startswith('PASSAGES (verbatim, each with its locator):\n- [D1.3] (paper.pdf p.2) "rainfall was 40% above the ten-year average"') and "3 passages the reader quoted were not verbatim and were dropped" in digest and digest.rstrip().endswith("[D1.2]."), digest)
check("parse_digest: the passages back out of the digest", R.parse_digest(digest) == [{"id": "D1.3", "where": "paper.pdf p.2", "quote": "rainfall was 40% above the ten-year average"}, {"id": "D1.4", "where": "paper.pdf p.2", "quote": "Group | n 40-49 | 15"}], R.parse_digest(digest))
check("parse_scope: D2 + question, ALL + question, a bare question is ALL", R.parse_scope("D2 the sample size") == ("D2", "the sample size") and R.parse_scope("all every mention of Q3") == ("ALL", "every mention of Q3") and R.parse_scope("what is the n") == ("ALL", "what is the n"))

# ---- read() over a thread folder ----
tmp = tempfile.mkdtemp(prefix="bamboo_read_")
MD = "# Field notes\n\n## Weather\nThe wet season came early: rainfall was 40% above the ten-year average in March.\n\n## Regimes\nRegime B plots were sown a week later than regime A on the same soils.\n"
md = os.path.join(tmp, "notes.md"); open(md, "w").write(MD)
tdir = os.path.join(tmp, "storage", "u", "documents", "77")
D.attach(tdir, md, "notes.md")
calls = []
def reader(system, user):
    """A scripted Reader: quotes the candidate about rainfall verbatim (whatever its id), plus one paraphrase."""
    calls.append(user)
    m = re.search(r"^\[(D\d+\.\d+)\] \([^)]*\) (.*rainfall was 40% above the ten-year average in March)", user, re.M)
    uid = m.group(1) if m else "D1.3"
    return f'- [{uid}] "rainfall was 40% above the ten-year average in March"\n- [{uid}] "rainfall was about 40 percent above"\nSUMMARY: An early wet season [{uid}].'
dg, ps = R.read(tdir, "D1 what about the wet season", reader)
check("read: BM25 selection, the reader called once with the matching passage, one passage kept and one dropped",
      len(calls) == 1 and "[D1.3] (notes.md §Field notes > Weather)" in calls[0] and ps == [{"id": "D1.3", "where": "notes.md §Field notes > Weather", "quote": "rainfall was 40% above the ten-year average in March"}]
      and "1 passage the reader quoted was not verbatim and was dropped" in dg, (dg, calls[0][:200]))
D.remove(tdir, "D1"); D.attach(tdir, md, "notes.md")          # D2 now
check("read: an unknown document, an empty question, a thread without documents answer with a note, not an error",
      R.read(tdir, "D7 anything", reader)[0].startswith("(no document D7 in this thread; attached: D2)") and R.read(tdir, "D2", reader)[0].startswith("(READ needs what you are looking for")
      and R.read(os.path.join(tmp, "none"), "ALL x", None, None, reader)[0].startswith("(no documents are attached"))

# ---- scoped READ: the analyst picks the stretch, the Reader reads it whole ----
check("parse_scope: the stretch forms - D1.35-41, D1.36, D1 p.7-9, D1 p.7 - and the whole-document and ALL forms",
      R.parse_scope("D1.35-41 what does the formula say") == ("D1.35-41", "what does the formula say") and R.parse_scope("D1.36") == ("D1.36", "")
      and R.parse_scope("D1 p.7-9 the beauty section") == ("D1 p.7-9", "the beauty section") and R.parse_scope("d1 p. 7 x") == ("D1 p.7", "x")
      and R.parse_scope("D1 the sample size") == ("D1", "the sample size") and R.parse_scope("ALL x") == ("ALL", "x"))
check("parse_stretch: units and pages as data; None for a whole document", R.parse_stretch("D1.35-41") == {"doc": "D1", "units": (35, 41)} and R.parse_stretch("D1.36") == {"doc": "D1", "units": (36, 36)}
      and R.parse_stretch("D1 p.7-9") == {"doc": "D1", "pages": (7, 9)} and R.parse_stretch("D1") is None and R.parse_stretch("ALL") is None)
many = [{"id": f"D3.{i}", "doc": "D3", "file": "p.pdf", "kind": "paragraph", "page": 1 + (i - 1) // 10, "text": f"unit number {i} says something about the trial."} for i in range(1, 61)]
su = R.stretch_units(many, {"doc": "D3", "units": (5, 40)})
check("stretch_units: the units of the stretch, whole and in order", len(su) == 36 and su[0]["id"] == "D3.5" and su[-1]["id"] == "D3.40")
sp = R.stretch_units(many, {"doc": "D3", "pages": (2, 6)})
check("stretch_units: a page stretch is every unit on those pages", all(2 <= u["page"] <= 6 for u in sp) and len(sp) == 50)
# (the document in this folder is D2 by now: D1 was removed and re-attached above)
calls_s = []
def reader_s(system, user):
    calls_s.append(user)
    return '- [D2.3] "rainfall was 40% above the ten-year average in March"\nSUMMARY: Early rains [D2.3].'
dg_s, ps_s = R.read(tdir, "D2.2-4 what about rainfall", reader_s)
check("read: a stretch is read whole - the Reader sees exactly units 2-4 in order, labelled as read whole",
      "SCOPE: D2.2-4 (3 units, read whole)" in calls_s[-1] and all(f"[D2.{i}]" in calls_s[-1] for i in (2, 3, 4)) and "[D2.5]" not in calls_s[-1] and "[D2.1]" not in calls_s[-1], calls_s[-1][:400])
check("read: the stretch digest carries the passage and the footer pointing to the two paths",
      ps_s and ps_s[0]["id"] == "D2.3" and "For a stretch whole: READ D2.1-5 <what you want>" in dg_s and "print(D2.grep(" in dg_s, dg_s)
# a long stretch - a fixture of 40 units - is read up to one call's worth; the digest names the units not reached
md_long = os.path.join(tmp, "long.md"); open(md_long, "w").write("# Long\n\n" + "\n\n".join(f"Paragraph {i} of the long report says that measure {i} rose by {i} percent in the trial." for i in range(1, 41)))
tdir_long = os.path.join(tmp, "storage", "u", "documents", "long"); D.attach(tdir_long, md_long, "long.md")
seg_calls = []
def reader_seg(system, user):
    seg_calls.append(user)
    lines = re.findall(r"^\[(D\d+\.\d+)\] \([^)]*\) (Paragraph \d+ of the long report says that measure \d+ rose by \d+ percent)", user, re.M)
    return "\n".join(f'- [{uid}] "{txt}"' for uid, txt in lines[:5]) + f"\nSUMMARY: {len(lines[:5])} measures rose."
dg_l, ps_l = R.read(tdir_long, "D1.1-41 how did the measures move", reader_seg, read_tokens=120)
check("a stretch longer than one call: one Reader call over the first units, the digest names the units not reached and says to READ them next",
      len(seg_calls) == 1 and "not reached; READ it next" in dg_l and re.search(r"D1\.\d+-\d+ not reached", dg_l) and len(ps_l) >= 1, (len(seg_calls), dg_l[:300]))
seg_calls.clear()
dg_one, _ = R.read(tdir_long, "D1.3-5 measure three", reader_seg)

check("a short stretch is one call, labelled read whole, nothing unreached", len(seg_calls) == 1 and "(3 units, read whole)" in seg_calls[0] and "not reached" not in dg_one, (seg_calls[0][:120], dg_one[:200]))
dg_q, _ = R.read(tdir, "D2.3", reader_s)
check("read: a stretch with no question still reads - the default question asks what the passages say", "QUESTION: What do these passages say?" in calls_s[-1] and ps_s, calls_s[-1][:120])
check("read: a stretch beyond the document is said", R.read(tdir, "D2.90-95 x", reader_s)[0].startswith("(nothing in D2.90-95: D2 has"), R.read(tdir, "D2.90-95 x", reader_s)[0])
dg_f, _ = R.read(tdir, "D2 the wet season", reader)
check("read: the ranked digest carries the footer too - the two paths", "For a stretch whole: READ D2." in dg_f and "print(D2.grep(" in dg_f, dg_f)

# ---- the session: READ turns, the budget, SHOW READ, the guard ----
NOTE = "- Question as understood: q\n- Best estimate so far: none yet\n- Held fixed: -\n- Open doubts: -\n- Plan: p\n- Names: -"
def act(line): return "###NOTE###\n" + NOTE + "\n###ACTION###\n" + line
script = [act("READ D2 what about the wet season"), act("READ ALL regimes"), act("READ D2 soils"), act("READ D2 a fourth time"),
          act("SHOW READ 1"), act("REPORT\n## Answer\nRainfall was 40% above the average [D2.3]; the plots [D9.9] were sown later. Also 4.2 million.")]
i = {"n": 0}; prompts = []
def fake_llm(system, user, **hints):
    prompts.append(user)
    if user.startswith("Rewrite the technical report"):
        return "Plain.", {"cost": 0.0}
    k = min(i["n"], len(script) - 1); i["n"] += 1
    return script[k], {"cost": 0.001}
store = NotebookStore(tempfile.mkdtemp()); nb = Notebook("t-read")
read_calls = []
def host_read(arg):
    read_calls.append(arg); dg, _ = R.read(tdir, arg, reader); return dg
def host_unit_text(uid):
    try:
        return next(R.unit_text(u) for u in D.read_units(tdir, uid.split(".")[0])["units"] if u["id"] == uid)
    except Exception:
        return None
events = []
s = Session(PersistentKernel(), nb, fake_llm, store=store, emit=events.append, data_description="(no dataset attached)", read=host_read, unit_text=host_unit_text, documents=True)
run = s.run("What did the notes say?", budget=Budget(turns=10, dollars=1.0))
kinds = [t.kind for t in run.turns]
starts = [e for e in events if e.get("type") == "lookup_start"]
check("session: a READ announces itself before the reader runs (lookup_start with the kind and the query), once per answered read, not for the one the budget answered",
      len(starts) == 3 and starts[0] == {"type": "lookup_start", "run": run.id, "kind": "read", "query": "D2 what about the wet season"}, starts)
check("session: three READ turns answered, the fourth answered from the budget without a reader call - pointing at SHOW READ and the kernel objects - then SHOW READ, then the report",
      kinds == ["read", "read", "read", "read", "show", "report", "rewrite"] and len(read_calls) == 3 and run.turns[3].stdout.startswith("(read budget for this run used: 3 of 3")
      and "D1.grep" in run.turns[3].stdout, (kinds, run.turns[3].stdout[:80]))
check("session: a read turn records the scope and query as its text and the digest as its stdout", run.turns[0].text == "D2 what about the wet season" and run.turns[0].stdout.startswith("PASSAGES (verbatim"), run.turns[0].stdout[:120])
# the report turn (the last cell turn: everything in view) carries the passages the run's reads returned
rp_prompts = []
rp_script = [act("READ D2 what about the wet season"), act("CELL\n```python\nprint('compute')\n```"), act("REPORT\n## r\n\nDone [D2.3].")]
rp_n = {"i": 0}
def rp_llm(system, user, **h):
    rp_prompts.append(user)
    if user.startswith("Rewrite"): return "Plain.", {"cost": 0.0}
    k = min(rp_n["i"], len(rp_script) - 1); rp_n["i"] += 1
    return rp_script[k], {"cost": 0.0}
Session(PersistentKernel(), Notebook("t-report"), rp_llm, store=store, read=host_read, unit_text=host_unit_text, documents=True).run("q", budget=Budget(turns=2, dollars=1.0))
report_prompt = next((q for q in rp_prompts if "EVERY CELL OF THIS RUN" in q), "")
block = report_prompt.split("PASSAGES THIS RUN'S READS RETURNED")[1].split("\n\nTASK:")[0] if "PASSAGES THIS RUN'S READS RETURNED" in report_prompt else ""
check("the passages this run's reads returned stay in the prompt - the lines with their ids, no summaries or footers - on the report turn too",
      report_prompt and block and "- [D2.3] (notes.md" in block and "SUMMARY:" not in block and "For a stretch whole" not in block, report_prompt[-700:])
check("they are in every prompt after the read, not only the last one (2026-10-03: a report written early had nothing to cite)",
      all("PASSAGES THIS RUN'S READS RETURNED" in q for q in rp_prompts[1:] if not q.startswith("Rewrite")) and "PASSAGES THIS RUN'S READS RETURNED" not in rp_prompts[0], [("PASSAGES" in q) for q in rp_prompts])
check("session: SHOW READ 1 reopens the first digest whole", run.turns[4].stdout.startswith("--- read 1: D2 what about the wet season ---\nPASSAGES"), run.turns[4].stdout[:100])
from analyst.session import view_digest, DIGEST_VIEW_CHARS
short = "PASSAGES (verbatim, each with its locator):\n- [D1.3] (p p.2) \"x\"\nSUMMARY:\nShort."
check("view_digest: a digest under the safety cap rides whole", view_digest(short, "SHOW READ 1") == short)
big = "PASSAGES (verbatim, each with its locator):\n" + "\n".join(f'- [D1.{i}] (p p.{i}) "passage number {i} ' + "lorem ipsum " * 40 + '"' for i in range(1, 60)) + "\nSUMMARY:\nThe one line that must survive [D1.3]."
shown_big = view_digest(big, "SHOW READ 2 for all")
check("view_digest: a pathological digest is cut from the middle at line ends - the first passages and the SUMMARY both survive, and the marker says how much and how to see it all",
      len(big) > DIGEST_VIEW_CHARS and len(shown_big) <= DIGEST_VIEW_CHARS + 120 and shown_big.startswith("PASSAGES (verbatim") and "- [D1.1] (p p.1)" in shown_big
      and shown_big.rstrip().endswith("The one line that must survive [D1.3].") and "characters omitted from the middle for length; SHOW READ 2 for all" in shown_big, (len(big), len(shown_big), shown_big[-200:]))
cut_line = shown_big.split("... [")[0].rstrip().splitlines()[-1]
check("view_digest: the cut falls at a line end, never inside a passage", cut_line.startswith("- [D1.") and cut_line.endswith('"'), cut_line[-60:])
first_read_prompt = next((u for u in prompts if "READ (D2 what about the wet season):" in u), "")
check("the next prompt carries the whole digest after a READ, with the reads-left line", run.turns[0].stdout in first_read_prompt and "(reads left in this run: 2)" in first_read_prompt, first_read_prompt[-300:])
check("guard: the number 40 came from the cited passage [D2.3], so it passes; 4.2 did not and is disclosed; [D9.9] is disclosed as not in the documents",
      "40" not in (run.report.split("CHECK:")[1] if "CHECK:" in run.report else "") and "4.2" in run.report.split("CHECK:")[1] and "not in this thread's documents: [D9.9]" in run.report, run.report[-500:])
events2 = []
s2 = Session(PersistentKernel(), nb, lambda sy, us, **h: (act("SHOW READ 2") if "TASK: turn 1 of" in us and "SHOWN:" not in us else act("REPORT\nDone."), {"cost": 0.0}) if not us.startswith("Rewrite") else ("Plain.", {"cost": 0.0}), store=store, emit=events2.append, read=host_read, unit_text=host_unit_text, documents=True)
run2 = s2.run("follow-up", parent=run.id, budget=Budget(turns=4, dollars=1.0))
check("session: in a follow-up chain, SHOW READ 2 reaches the earlier chain's second read - numbered along the path, as searches are", run2.turns[0].stdout.startswith("--- read 2: ALL regimes ---"), run2.turns[0].stdout[:80])
check("notebook: reads() along the path counts both chains' read turns, the budget-refused one included as searches do", len(nb.reads(run2.id)) == 4, len(nb.reads(run2.id)))
check("the documents' part of the contract names READ with its stretch forms, READ ALL, SHOW READ and the passage citation, and no LOOK; the base contract has none of them",
      all(x in open(os.path.join(ROOT, "analyst", "contract_documents.md")).read() for x in ("READ D1.35-41 <what you want>", "READ ALL <what you want>", "SHOW READ <k>", "[D1.17]"))
      and "LOOK" not in open(os.path.join(ROOT, "analyst", "contract_documents.md")).read()
      and not any(x in open(os.path.join(ROOT, "analyst", "contract.md")).read() for x in ("LOOK", "READ D", "[D1.17]")))
check("parse_turn: READ with a scope and a question", parse_turn("###NOTE###\nn\n###ACTION###\nREAD D1 the sample size")[2].verb == "read" and parse_turn("###NOTE###\nn\n###ACTION###\nREAD D1 the sample size")[2].arg == "D1 the sample size")
check("report.cited_units: ids in order, once each", rep.cited_units("x [D1.3] y [D2.1] z [D1.3]") == ["D1.3", "D2.1"] and rep.guard_units([]) == "")
two = parse_turn("###NOTE###\nn\n###ACTION###\nSEARCH Schmidhuber subjective beauty proportional bits\nREAD D1 section 4 visual illustrations")[2]
check("parse_turn: one action per turn - a READ line after a SEARCH is not part of the query", two.verb == "search" and two.arg == "Schmidhuber subjective beauty proportional bits", two)
multi = parse_turn("###NOTE###\nn\n###ACTION###\nASK Which season do you mean:\nthe wet one, or the whole year?\n\n###THINKING###\nmore chatter")[2]
check("parse_turn: a question's own second line still belongs to it; a blank line or a marker ends it", multi.arg == "Which season do you mean:\nthe wet one, or the whole year?", multi)
chatter = parse_turn("###NOTE###\nn\n###ACTION###\nREAD D1 altitude correction headline\n\n###THINKING###\nI got the document read. Let me digest what it says.\nActually the READ returned a summary")[2]
check("parse_turn: a READ query is its one line - forty lines of chatter after it are not the question (2026-10-03)", chatter.arg == "D1 altitude correction headline", chatter)
check("contract: the turn begins at its first marker", "the first marker first - nothing before ###THINKING###" in open(os.path.join(ROOT, "analyst", "contract.md")).read())

shutil.rmtree(tmp, ignore_errors=True)
print(f"\n{len(passed)} passed, {len(failed)} failed")
sys.exit(1 if failed else 0)
