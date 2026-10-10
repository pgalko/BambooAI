"""Scenario: when does the subject's training start, on data loaded from (the stack's fake) Intervals.icu with the
summary and wellness auxiliaries. The scripted analyst reads the summary file by the dated name DATA gives it - as
the real analyst did in the first live routine (2026-10-10) - and writes the method the contract asks for: the home
offset read off the data, never typed. Save as routine then runs the same cells on a later window, where the summary
has another name, the frame has no power column and the wellness file was not written - the loaders' own variation
(apis_data.py), met by the run's binding and conform.

The question (Deep, four turns): inspect; the summary read and the hours counted, three RESULT lines; a figure; the
report. The promoter makes the hour band an input (numbers, default 9 to 11) and, as the live one did, tries to make
the loaded window one by writing it into the summary file's name - refused by the host, which keeps the loader's name
for the run to bind. Any other question gets a short generic answer.
"""
import json
import re

QUESTIONS = ["At what local hour does training usually start, and what share of sessions start between 9 and 12?"]
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


def _summary_path(user):
    """The summary file's path as DATA lists it (Path: datasets/<user>/activity_summary_<start>_to_<end>.csv)."""
    m = re.search(r"^Path: (\S*activity_summary_\d{8}_to_\d{8}\.csv)", user, re.M)
    return m.group(1) if m else "datasets/local/activity_summary.csv"


CELL_INSPECT = """# The frame: one row per second of every session; the columns the device gave
print(df.shape)
print(df.dtypes.to_string())
print(df['activity_type'].value_counts().to_string())
print('sessions:', df['activity_id'].nunique())"""

CELL_HOURS = """# The summary file lists one row per session with its local and UTC start times. The time-zone offset is read off
# the data: the most common offset is home, the rest is travel.
summ = pd.read_csv({path!r})
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
RESULT('sessions in the window', float(n), None, None, 'sessions', 'n/a')
RESULT('the local hour most sessions start', float(peak_h), None, None, 'hour', 'n/a')
RESULT('share of sessions starting in the hour band', p, lo, hi, 'share', 'n/a')"""

CELL_FIGURE = """# The start hours, one bar per local hour
import plotly.graph_objects as go
fig = go.Figure(go.Bar(x=list(range(24)), y=counts.tolist()))
fig.update_layout(title='Session start hour (local clock), %d sessions' % n, xaxis_title='local hour', yaxis_title='sessions')
fig.show()"""

CELL_GENERIC = """print(df.describe(include='all').round(3).to_string())"""


class Scenario:
    def __init__(self):
        self.vals = {}

    def reply(self, system, user):
        if user.startswith("Rewrite the technical report"):
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
        if system.startswith("You are the Reader"):
            return "", "NOTHING ANSWERS - no documents in this story."
        if system.startswith("You are preparing an analysis so that it can be run again"):
            return "", self.promoter(user)
        return "", "OK"

    # ------------------------------------------------------------ the promoter
    def promoter(self, user):
        m = re.search(r"# --- cell (\d+) ---\n(?:(?!# --- cell).)*?band = \[9, 11\]", user, re.S)
        if not m:
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
        return json.dumps({
            "name": "Session start hours", "inputs": inputs, "edits": edits,
            "kept": ["the home offset is read off the data, not typed", "the Wilson interval's z is the method's"]})

    # ------------------------------------------------------------ the analyst
    def analyst(self, user):
        q = _question(user)
        turn, of = _turn(user)
        forced = "STOP:" in user or "Write REPORT now" in user
        if q == QUESTIONS[0]:
            if forced or turn >= 4:
                return self.report(user, q)
            return {1: self.t_inspect, 2: self.t_hours, 3: self.t_figure}[turn](user, q)
        if forced or turn >= 2:
            return _report("Nothing scripted for this question.", _note(q, plan="report"), "## Answer\n\nA first look was taken [cell 1]; nothing more is scripted for this question.")
        return _cell("A question outside the scripted story: one look at the data.", _note(q, plan="describe, then report"), CELL_GENERIC)

    def t_inspect(self, user, q):
        return _cell("The frame is one row per second; the session list with start times is the summary file DATA names. First the frame itself.",
                     _note(q, plan="inspect; then read the summary and count start hours"), CELL_INSPECT)

    def t_hours(self, user, q):
        path = _summary_path(user)
        return _cell("The summary file carries each session's local and UTC start. The home offset is the most common offset in the data - read off it, so the method holds on another window - and the hours are counted on the local clock.",
                     _note(q, held="the clock (local)", plan="count the hours; a figure; report", names="df, summ, counts, n, peak_h, band"),
                     CELL_HOURS.format(path=path))

    def t_figure(self, user, q):
        return _cell("The numbers are printed in cell 2. One figure of the start hours.",
                     _note(q, est="see cell 2", held="the clock (local)", plan="figure; then report", names="df, summ, counts, n, peak_h"), CELL_FIGURE)

    def report(self, user, q):
        m = re.search(r"n=(\d+) peak_hour=(\d+) home_offset=(-?\d+) away_sessions=(\d+) share=([\d.]+) lo=([\d.]+) hi=([\d.]+)", user)
        if not m:
            return _report("The counts did not print.", _note(q, plan="report"), "## Not established\n\nThe start-hour cell did not print its counts; nothing can be reported.")
        n, peak, off, away, share, lo, hi = m.groups()
        body = (f"## Training starts at {peak}:00 on most days\n\nAcross {n} sessions the most common local start hour is {peak}:00 [cell 2]; "
                f"{float(share):.1%} of sessions start between 9:00 and 11:59 (95% interval {float(lo):.1%} to {float(hi):.1%}) [cell 2]. "
                f"The home offset read off the data is UTC{int(off):+d}; {away} sessions were away from it [cell 2].\n\n"
                f"## The comparison\n\nThe question asks when sessions start; the answer counts local start hours over the loaded window [cell 2].\n\n"
                f"## How it was established\n\nThe summary file's local and UTC starts give the offset and the local hour; a Wilson interval for the share [cell 2]; the distribution is in [fig 3].\n\n"
                f"## Limitations\n\nOne window; the away block is short.\n\n## Next steps\n\nWeekday against weekend; rides against runs.")
        return _report("Every number is in cell 2 and the figure is cell 3. Report.", _note(q, est=f"peak hour {peak}:00; band share {float(share):.3f}", held="the clock (local)", plan="report"), body)
