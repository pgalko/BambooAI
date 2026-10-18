"""Scenario: when does the subject's training start, on data loaded from (the stack's fake) Intervals.icu with the
summary and wellness auxiliaries. The scripted analyst reads the summary file by the dated name DATA gives it - as
the real analyst did in the first live routine (2026-10-10) - and writes the method the contract asks for: the home
offset read off the data, never typed. Save as routine then runs the same cells on a later window, where the summary
has another name, the frame has no power column and the wellness file was not written - the loaders' own variation
(apis_data.py), met by the run's binding and conform.

The question (Deep, four turns): inspect; the summary read and the hours counted, three RESULT lines; a figure; the
report. The promoter makes the hour band an input (numbers, default 9 to 11), the session types kept a choice over the
summary file's `type` column (a column the frame does not have), and, as the live one did, tries to make
the loaded window one by writing it into the summary file's name - refused by the host, which keeps the loader's name
for the run to bind. The analyst also types the frame's first and last dates into a RESULT label (against the
contract, as the first live chain did), and the promoter makes them a date window: the host marks it as following the
data, and each run writes it from the frame. Any other question gets a short generic answer.
"""
import json
import re

QUESTIONS = ["At what local hour does training usually start, and what share of sessions start between 9 and 12?"]
# the context (docs/CONTEXT_DESIGN.md, step 2): a question answered from the words beside the data - a cell over CTX, a
# READ CTX through the Reader, the report quoting a passage and citing it as [C.n]
CONTEXT_QUESTION = "What did the rider write about the legs, and when?"
# the context in a routine (docs/CONTEXT_DESIGN.md F3, step 5): a chain that counts a code on the subject's own passages - one
# cell over CTX.frame() and CTX.codes(), two RESULT lines, a report - made a routine and run on other windows, where the
# count is compared like any result line and a window without words prints zeros
COUNT_QUESTION = "How many of the rider's own passages in this window were read as fatigue?"
DATASET_NAME = "start_hours_stub.csv"          # the stack wants a file; the walk loads from Intervals instead


def make_dataset(path):
    with open(path, "w", encoding="utf-8") as fh:
        fh.write("a,b\n1,2\n")


def _turn(user):
    m = re.search(r"TASK: turn (\d+); up to (\d+)", user)
    return (int(m.group(1)), int(m.group(2))) if m else (1, 15)


def _question(user):
    m = re.search(r"QUESTION:\n(.*?)\n\nYOUR NOTE", user, re.S)
    return (m.group(1) if m else "").strip()


def _note(q, est="none yet", held="nothing yet", doubts="-", plan="-", names="df"):
    return (f"- Question as understood: {q}\n- Best estimate so far: {est}\n- Held fixed: {held}\n"
            f"- Open doubts: {doubts}\n- Plan: {plan}\n- Names: {names}\n- Standing instructions from the person: none")


def _cell(thinking, note, code):
    return thinking, f"###STEP###\n{thinking}\n###NOTE###\n{note}\n###ACTION###\nCELL\n```python\n{code}\n```"


def _report(thinking, note, body):
    return thinking, f"###STEP###\n{thinking}\n###NOTE###\n{note}\n###ACTION###\nREPORT\n{body}"


def _action(thinking, note, line):
    return thinking, f"###STEP###\n{thinking}\n###NOTE###\n{note}\n###ACTION###\n{line}"


def _first_last(user):
    """The frame's first and last dates as the inspect cell printed them (typed into the label, as the live chain did)."""
    m = re.search(r"first: (\d{4}-\d{2}-\d{2}) last: (\d{4}-\d{2}-\d{2})", user)
    return (m.group(1), m.group(2)) if m else ("2026-01-01", "2026-12-31")


def _summary_path(user):
    """The summary file's path as DATA lists it (Path: datasets/<user>/activity_summary_<start>_to_<end>.csv)."""
    m = re.search(r"^Path: (\S*activity_summary_\d{8}_to_\d{8}\.csv)", user, re.M)
    return m.group(1) if m else "datasets/local/activity_summary.csv"


CELL_INSPECT = """# The frame: one row per second of every session; the columns the device gave
print(df.shape)
print(df.dtypes.to_string())
print(df['activity_type'].value_counts().to_string())
print('sessions:', df['activity_id'].nunique())
print('first:', df['datetime'].min().date(), 'last:', df['datetime'].max().date())"""

CELL_HOURS = """# The summary file lists one row per session with its local and UTC start times. The time-zone offset is read off
# the data: the most common offset is home, the rest is travel.
summ = pd.read_csv({path!r})
summ = summ[summ['type'].isin(['Ride', 'Run'])]
summ['start_local'] = pd.to_datetime(summ['start_date_local'])
summ['start_utc'] = pd.to_datetime(summ['start_date_utc'], utc=True)
summ['offset_h'] = ((summ['start_local'] - summ['start_utc'].dt.tz_localize(None)).dt.total_seconds() / 3600).round().astype(int)
summ['hour'] = summ['start_local'].dt.hour
home_offset = int(summ['offset_h'].mode().iloc[0])
away = summ[summ['offset_h'] != home_offset]
counts = summ['hour'].value_counts().reindex(range(24), fill_value=0)
n = int(counts.sum())
peak_h = int(counts.idxmax())
band = [9, 11]
k = int(counts.loc[band[0]:band[1]].sum())
p = k / n if n else float('nan')
z = 1.96
den = 1 + z * z / n
c = p + z * z / (2 * n)
hw = z * np.sqrt(p * (1 - p) / n + z * z / (4 * n * n))
lo, hi = (c - hw) / den, (c + hw) / den
print(f"n={{n}} peak_hour={{peak_h}} home_offset={{home_offset}} away_sessions={{len(away)}} share={{p:.3f}} lo={{lo:.3f}} hi={{hi:.3f}}")
RESULT('sessions in the window {first} to {last}', float(n), None, None, 'sessions', 'n/a')
RESULT('the local hour most sessions start', float(peak_h), None, None, 'hour', 'n/a')
RESULT('share of sessions starting in the hour band', p, lo, hi, 'share', 'n/a')"""

CELL_FIGURE = """# The start hours, one bar per local hour
import plotly.graph_objects as go
fig = go.Figure(go.Bar(x=list(range(24)), y=counts.tolist()))
fig.update_layout(title='Session start hour (local clock), %d sessions' % n, xaxis_title='local hour', yaxis_title='sessions')
fig.show()"""

CELL_GENERIC = """print(df.describe(include='all').round(3).to_string())"""

CELL_COUNT = """# The passages the subject wrote and the codes the coding pass put on them: a code is the model's reading, counted here
notes = CTX.frame()
codes = CTX.codes()
mine = notes[notes['author_role'] == 'subject']
hit = codes[(codes['code'] == 'fatigue') & codes['id'].isin(mine['id'])]
n_mine, n_fatigue = int(len(mine)), int(hit['id'].nunique())
print(f"COUNT subject_passages={n_mine} fatigue={n_fatigue}")
RESULT('passages the subject wrote in the window', float(n_mine), None, None, 'passages', 'n/a')
RESULT('of them read as fatigue by the coding pass', float(n_fatigue), None, None, 'passages', 'n/a')"""


class Scenario:
    def __init__(self):
        self.vals = {}

    def reply(self, system, user):
        if user.startswith("Rewrite the technical report"):
            k = re.search(r"## (\d+) of the rider's (\d+) passages were read as fatigue", user)
            if k:                                       # the count question's report (step 5)
                return "", f"Of the {k.group(2)} notes the rider wrote, a program read {k.group(1)} as being about fatigue; that is the program's reading, not the rider's words."
            m = re.search(r"\"([^\"]+)\" \[(C\.\d+)\]", user)
            if m:                                       # the context question's report: the plain version keeps the quote and its citation
                return "", f"The rider's own words under one session were \"{m.group(1)}\" [{m.group(2)}]; the day it was written is in the report."
            return "", "Most sessions start in the morning on the local clock; the share in the 9 to 12 band is given with its interval."
        if "Propose five follow-up questions" in user:
            return "", "1. **Weekday vs weekend**: Does the start hour differ?\n2. **Travel**: Does the away block shift it?\n3. **Type**: Rides vs runs?\n4. **Season**: Earlier in summer?\n5. **Load**: Do later starts follow heavier days?"
        if system.startswith("You are the Knowledge Distiller"):
            return "", "NO_CARD"
        if "infographic" in user[:400].lower() or "infographic" in system[:400].lower():
            return "", ""
        if system.startswith("You are the reviewer"):
            handed = [int(n) for n in re.findall(r"^--- cell (\d+) \(", user, re.M)]
            last = max(handed) if handed else 2
            checked = "".join(f"- Checked: cell {n} - computes what its line names; matches its line\n" for n in handed)
            return "", ("###REVIEW###\n- The question requires: the modal start hour and the band's share.\n"
                        f"- Established: both printed [cell {last}].\n" + checked + "- Most consequential problem: none\n"
                        f"- Verdict: REPORT the question is answered [cell {last}].")
        if system.startswith("You are the analyst"):
            return self.analyst(user)
        if system.startswith("You are drawing the figures"):
            # the figures step after the report (2026-10-11): the story's one figure, from the counts cell 2 left in the kernel
            m = re.search(r"QUESTION:\n(.*?)\n\nTHE REPORT", user, re.S)
            if (m.group(1) if m else "").strip() != QUESTIONS[0]:
                return "", "NONE"
            return "", "```python\n" + CELL_FIGURE + "\n```\nCAPTION: sessions by local start hour over the window"
        if system.startswith("You are the Reader"):
            return "", self.reader(user)
        if system.startswith("You are the Coder"):
            return "", self.coder(user)
        if system.startswith("You are preparing an analysis so that it can be run again"):
            return "", self.promoter(user)
        return "", "OK"

    # ------------------------------------------------------------ the promoter
    def promoter(self, user):
        m = re.search(r"# --- cell (\d+) ---\n(?:(?!# --- cell).)*?band = \[9, 11\]", user, re.S)
        if not m:
            if "COUNT subject_passages=" in user or "codes['code'] == 'fatigue'" in user:
                # the count chain (step 5): the code counted is the question's; the window is the load's; nothing to make an input
                return json.dumps({"name": "Fatigue in the rider's own words", "inputs": [], "edits": [], "kept": ["the code counted is the question's; the passages and the codes are the load's files, bound at each run"]})
            return json.dumps({"name": "Start hours", "inputs": [], "edits": [], "kept": ["nothing varies with the data"]})
        cell = int(m.group(1))
        inputs = [{"key": "band", "label": "The hour band counted", "type": "numbers", "default": [9, 11], "origin": "the analysis counted 9 to 11", "multiple": False}]
        edits = [{"cell": cell, "find": "band = [9, 11]", "replace": "band = INPUTS['band']"}]
        # what the live promoter did on the first Intervals routine (2026-10-10): the loaded window made an input and
        # written into the summary's file name as an f-string - the name is the loader's, so the host refuses the edit,
        # drops the input with the reason in the dialog's notes, and the dated name stays for the run to bind
        p = re.search(r"pd\.read_csv\('(datasets/\S*activity_summary_(\d{8})_to_(\d{8})\.csv)'\)", user)
        if p:
            path, s, e = p.groups()
            inputs.append({"key": "window", "label": "The period", "type": "date_window", "default": [f"{s[:4]}-{s[4:6]}-{s[6:]}", f"{e[:4]}-{e[4:6]}-{e[6:]}"],
                           "origin": "the period the analysis ran on, also encoded in the summary file's name"})
            edits.append({"cell": cell, "find": f"pd.read_csv('{path}')",
                          "replace": "pd.read_csv(f\"" + path.rsplit("activity_summary_", 1)[0] + "activity_summary_{str(INPUTS['window'][0]).replace('-','')}_to_{str(INPUTS['window'][1]).replace('-','')}.csv\")"})
        # the session types kept, a choice over a column of the summary file - not of the frame (2026-10-11, Palo's routine:
        # the check looked for the column in the frame alone and refused)
        inputs.append({"key": "kinds", "label": "Session types counted", "type": "choice", "multiple": True, "column": "type", "default": ["Ride", "Run"], "origin": "the two types the analysis kept"})
        edits.append({"cell": cell, "find": "isin(['Ride', 'Run'])", "replace": "isin(INPUTS['kinds'])"})
        # the frame's first and last dates, typed into a label: proposed as a window (the host marks it as the data's own)
        d = re.search(r"RESULT\('sessions in the window (\d{4}-\d{2}-\d{2}) to (\d{4}-\d{2}-\d{2})'", user)
        if d:
            inputs.append({"key": "span", "label": "The dates in the label", "type": "date_window", "default": [d.group(1), d.group(2)], "origin": "the first and last session dates, written into the label"})
            edits.append({"cell": cell, "find": f"'sessions in the window {d.group(1)} to {d.group(2)}'", "replace": "f\"sessions in the window {INPUTS['span'][0]} to {INPUTS['span'][1]}\""})
        return json.dumps({
            "name": "Session start hours", "inputs": inputs, "edits": edits,
            "kept": ["the home offset is read off the data, not typed", "the Wilson interval's z is the method's"]})

    # ------------------------------------------------------------ the Reader seat (the context, step 2)
    def reader(self, user):
        """The Reader over the passages of the context: every candidate that mentions the legs, quoted whole (the
        passages are one line each); the platform verifies each quote against the passage. A rendered passage
        (step 3: the Danish lines carry an English rendering, and that is what the Reader sees) is quoted first, so
        the walk meets the rendering path. No documents in this story."""
        hits = [(uid, place, text) for uid, place, text in re.findall(r"^\[(C\.\d+)\] (\((?:[^()]|\([^()]*\))*\)) (.+)$", user, re.M) if "legs" in text.lower()]
        hits.sort(key=lambda h: 0 if "rendered from" in h[1] else 1)
        if not hits:
            return "NOTHING ANSWERS - no passage mentions the legs."
        return "\n".join(f'- [{uid}] "{text.strip()}"' for uid, _, text in hits[:3]) + f"\nSUMMARY: The rider wrote about the legs on the days of the sessions [{hits[0][0]}]."

    # ------------------------------------------------------------ the Coder seat (the context, step 3)
    LEXICON = [   # (a stretch of the fake calendar's words, lang, tone, [(code, quote)], text_en, proposals)
        ("Benene var tunge", "da", "negative", [("fatigue", "Benene var tunge"), ("deviation", "kørte kortere end planlagt")], "The legs were heavy today, rode shorter than planned.", []),
        ("Good legs today", "en", "positive", [("freshness", "Good legs today"), ("execution", "held the power easily")], "", []),
        ("Sov dårligt", "da", "negative", [("sleep", "Sov dårligt"), ("fatigue", "var træt fra start")], "Slept badly, was tired from the start.", []),
        ("Felt strong on the climbs", "en", "positive", [("good_day", "Felt strong on the climbs")], "", []),
        ("ondt i knæet", "da", "negative", [("injury", "ondt i knæet")], "A bit of knee pain after the ride.", []),
        ("Cut the session short", "en", "neutral", [("deviation", "Cut the session short"), ("work_study", "work ran late")], "", []),
        ("tag det roligt", "da", "neutral", [("instruction", "tag det roligt i morgen")], "Fine, take it easy tomorrow.", []),
        ("Same again Thursday", "en", "positive", [("feedback", "Good."), ("instruction", "Same again Thursday")], "", []),
        ("Keep the cadence up", "en", "neutral", [("instruction", "Keep the cadence up next time")], "", []),
        ("Bra jobba", "no", "positive", [("feedback", "Bra jobba")], "Good job.", []),
        ("Exams all week", "en", "negative", [("work_study", "Exams all week")], "", []),
        ("check the sleep log", "en", "neutral", [("sleep", "check the sleep log"), ("coach_flag", "Private: check the sleep log this week")], "",
         [{"code": "coach flag", "definition": "a coach's private note to watch something in the coming days"}]),
        ("Watch motivation", "en", "neutral", [("motivation", "Watch motivation"), ("coach_flag", "Watch motivation")], "",
         [{"code": "coach flag", "definition": "a coach's private note to watch something in the coming days"}]),   # proposed again: a batch cannot use a later batch's proposal
        ("Keep it conversational", "en", "neutral", [("instruction", "Keep it conversational"), ("nutrition", "fuel every hour")], "", []),
        ("Dårlig nat", "da", "negative", [("sleep", "Dårlig nat, vågnede flere gange")], "Bad night, woke up several times.", []),
        ("Slept well", "en", "positive", [("sleep", "Slept well"), ("freshness", "fresh this morning")], "", []),
        ("Cold", "en", "negative", [("illness", "Cold")], "", []),
    ]

    def coder(self, user):
        """The coder over a batch (docs/CONTEXT_DESIGN.md §6): one JSON line per passage, by a lexicon over the fake
        calendar's words - the codes with their verbatim quotes and the way the tone points (the reading's format 2,
        patch 0198), the tone, the language, an English rendering of
        every Danish or Norwegian line, one proposal (coach_flag) the seed lacks; a passage the lexicon does not know
        gets no code. The platform's checks do the rest."""
        out = []
        for m in re.finditer(r"^\[(C\.\d+)\] [^\n]*\n(.*?)(?=\n\n\[C\.\d+\]|\Z)", user.split("PASSAGES (", 1)[-1], re.M | re.S):
            uid, text = m.group(1), m.group(2).strip()
            hit = next((e for e in self.LEXICON if e[0].lower() in text.lower()), None)
            if hit is None:
                out.append(json.dumps({"id": uid, "codes": [], "tone": "neutral", "lang": "en"}))
                continue
            _, lang, tone, codes, text_en, proposals = hit
            way = "worse" if tone == "negative" else "better" if tone == "positive" else "neutral"
            item = {"id": uid, "codes": [{"code": c, "quote": q, "direction": way, "basis": "said", "about": ""} for c, q in codes], "tone": tone, "lang": lang}
            if text_en:
                item["text_en"] = text_en
            if proposals:
                item["propose"] = proposals
            out.append(json.dumps(item, ensure_ascii=False))
        return "\n".join(out)

    # ------------------------------------------------------------ the analyst
    def analyst(self, user):
        q = _question(user)
        turn, of = _turn(user)
        forced = "STOP:" in user or "Write REPORT now" in user
        if q == QUESTIONS[0]:
            # turn 1 inspects, turn 2 counts, turn 3 reports; the figure is the figures step's, after the report (2026-10-11)
            if forced or turn >= 3:
                return self.report(user, q)
            return {1: self.t_inspect, 2: self.t_hours}[turn](user, q)
        if q == COUNT_QUESTION:
            c = re.search(r"--- cell (\d+) ---\n(?:(?!--- cell).)*?COUNT subject_passages=(\d+) fatigue=(\d+)", user, re.S)
            if forced or c:
                if not c:
                    return _report("The count did not print.", _note(q, plan="report"), "## Not established\n\nThe counting cell did not print; nothing can be reported.")
                cell, n_mine, n_fat = c.group(1), c.group(2), c.group(3)
                return _report("The two counts are printed; the report says what they rest on - the coding pass's reading, not the rider's words.", _note(q, est=f"{n_fat} of {n_mine}", plan="report"),
                               f"## {n_fat} of the rider's {n_mine} passages were read as fatigue\n\nOf the {n_mine} passages the rider wrote in this window, {n_fat} carry the code fatigue [cell {cell}]. "
                               f"A code is the coding pass's reading of a passage, not something the rider said; the count rests on the codes table, not on the words quoted.\n\n"
                               f"## How it was established\n\nThe subject's rows of CTX.frame() joined to CTX.codes() on the passage id, the code counted once per passage [cell {cell}].")
            return _cell("The passages are in CTX.frame(), the codes the pass put on them in CTX.codes(); one cell counts the code on the subject's own passages.",
                         _note(q, plan="count; report", names="notes, codes, mine, hit"), CELL_COUNT)
        if q == CONTEXT_QUESTION:
            # the context path: a cell over CTX finds the passages that mention the legs, a READ CTX quotes them through the
            # Reader, the report quotes one as the Reader returned it and cites it as [C.n]
            if forced or "READ (" in user:
                return self.report_context(user, q)
            if "CTX.grep(" in user:
                return _action("The grep lists the passages with their ids and days. READ them through the Reader so the quotes are verified against the passages.",
                               _note(q, plan="READ CTX; then report", names="-"), "READ CTX what was written about the legs")
            return _cell("The words written beside the data are in the kernel as CTX; DATA's map lists messages by the subject. One cell: the span, then every passage that mentions the legs.",
                         _note(q, plan="grep the context; READ the passages; report", names="-"), "print(CTX)\nprint(CTX.grep('legs', kind='activity_message', author='subject'))")
        if forced or turn >= 2:
            return _report("Nothing scripted for this question.", _note(q, plan="report"), "## Answer\n\nA first look was taken [cell 1]; nothing more is scripted for this question.")
        return _cell("A question outside the scripted story: one look at the data.", _note(q, plan="describe, then report"), CELL_GENERIC)

    def t_inspect(self, user, q):
        return _cell("The frame is one row per second; the session list with start times is the summary file DATA names. First the frame itself.",
                     _note(q, plan="inspect; then read the summary and count start hours"), CELL_INSPECT)

    def t_hours(self, user, q):
        path = _summary_path(user)
        first, last = _first_last(user)
        return _cell("The summary file carries each session's local and UTC start. The home offset is the most common offset in the data - read off it, so the method holds on another window - and the hours are counted on the local clock.",
                     _note(q, held="the clock (local)", plan="count the hours; report", names="df, summ, counts, n, peak_h, band"),
                     CELL_HOURS.format(path=path, first=first, last=last))

    def report_context(self, user, q):
        # the READ digest in the prompt: the first passage line - the quote the platform verified, with its day - cited by id
        m = re.search(r"^- \[(C\.\d+)\] \((\d{4}-\d{2}-\d{2}) \u00b7 ([^\u00b7]+) \u00b7 ([^()]*(?:\([^()]*\))?)\) \"(.+)\"\s*$", user, re.M)   # the place may end "(rendered from da)"
        if not m:
            return _report("No passage came back.", _note(q, plan="report"), "## Nothing written about the legs\n\nThe context was read [cell 1] and no passage mentions the legs.")
        uid, day, kind, who, quote = m.groups()
        who = re.sub(r"\s*\(rendered from \w+\)", "", who)
        n = len(re.findall(r"^- \[C\.\d+\] \(", user, re.M))
        # the passage after the quoted one, named by its bare id and never READ (as the first live run named every passage,
        # 2026-10-14): the host resolves it at report time for the chip's hover; cell 1's print(CTX) said how many there are
        total = re.search(r"CTX: (\d+) passages", user)
        k = int(uid.split(".")[1])
        nxt = f"C.{k + 1 if total and k + 1 <= int(total.group(1)) else max(1, k - 1)}"
        return _report("The Reader's quote is verified; the report quotes it, says the day and the kind, and cites the passage.", _note(q, plan="report"),
                       f"## The rider wrote about the legs on {day}\n\n**{uid} - written {day}** [cell 1]: the {who.strip()} wrote, under the session ({kind.strip()}): \"{quote}\" [{uid}]. "
                       f"The passage beside it, {nxt}, is in the context too. "
                       f"The READ returned {n} such passage(s) [cell 1]; the day a thing was written and the day the numbers show it can differ, so a comparison with the "
                       f"power of those sessions would be a separate question over `df`.\n\n## How it was established\n\nCTX.grep over the subject's messages [cell 1], then READ CTX through the Reader.")

    def report(self, user, q):
        m = re.search(r"n=(\d+) peak_hour=(\d+) home_offset=(-?\d+) away_sessions=(\d+) share=([\d.]+) lo=([\d.]+) hi=([\d.]+)", user)
        if not m:
            return _report("The counts did not print.", _note(q, plan="report"), "## Not established\n\nThe start-hour cell did not print its counts; nothing can be reported.")
        n, peak, off, away, share, lo, hi = m.groups()
        body = (f"## Training starts at {peak}:00 on most days\n\nAcross {n} sessions the most common local start hour is {peak}:00 [cell 2]; "
                f"{float(share):.1%} of sessions start between 9:00 and 11:59 (95% interval {float(lo):.1%} to {float(hi):.1%}) [cell 2]. "
                f"The home offset read off the data is UTC{int(off):+d}; {away} sessions were away from it [cell 2].\n\n"
                f"## The comparison\n\nThe question asks when sessions start; the answer counts local start hours over the loaded window [cell 2].\n\n"
                f"## How it was established\n\nThe summary file's local and UTC starts give the offset and the local hour; a Wilson interval for the share [cell 2].\n\n"
                f"## Limitations\n\nOne window; the away block is short.\n\n## Next steps\n\nWeekday against weekend; rides against runs.")
        return _report("Every number is in cell 2; the figure comes after the report. Report.", _note(q, est=f"peak hour {peak}:00; band share {float(share):.3f}", held="the clock (local)", plan="report"), body)
