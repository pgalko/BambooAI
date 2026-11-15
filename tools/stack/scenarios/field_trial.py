"""Scenario: a fertiliser field trial. Three regimes (A, B, C) on 120 plots over six seasons,
with soil type unevenly spread across regimes - so the raw B-A gap and the within-soil gap
differ, which gives the analyst something to hold fixed.

The scripted analyst answers from the REAL prompt: it reads the question, the turn number
and the cell outputs, so every number in its report is one the kernel printed. The story
for the first question (Deep, six turns): inspect, search, a cell that fails on a wrong
column name (rolled back), the adjusted comparison with a plot-level bootstrap, a figure,
the report. A follow-up ("and regime C?") reuses the warm kernel in two turns. Any other
question gets a short generic two-turn answer, so the stack can be driven interactively.

A run with a brief (docs/ARCHITECT_DESIGN.md §2.11) is scripted by the brief, whatever the question's words: the analyst
computes what the brief fixes - regime C against A within soil, on plot means - and its report says how the result stands
against what the brief expects, with a line for each Also check. A brief that fixes a measure the data does not have
(protein) makes it stop and ask; the person's answer naming yield lets the next run go ahead.
"""
import json
import os
import re

import numpy as np
import pandas as pd

DATASET_NAME = "field_trial.csv"
QUESTIONS = [
    "Does regime B raise yield over regime A once soil type is taken into account?",
    "And how does regime C compare with A on the same footing?",
]
REVIEW_QUESTION = "Walk through ten small checks of the data, one per turn."     # crosses turn 9: Adaptive's first self-review
# the reach report (2026-10-28): a chain whose first cell the executor refuses (the blacklist) and whose second reaches the
# fake integrations service - which the question does not name - so the card, the pane and the map show the record
REACH_QUESTION = "Is the integrations service answering right now?"

# a question that needs no data (docs/ROUTINES_DESIGN.md §24): asked in a workflow with nothing loaded, its cell computes from
# values written into it - the routine made from it has those values as its inputs and runs without data
ALONE_QUESTION = "Starting from 100 and losing 5% at every step, how much is left after 40 steps?"

# a document attached to the thread (docs/DOCUMENTS_DESIGN.md, phase A): the analyst reads it in a cell
DOC_NAME = "field_notes.md"
DOC_TEXT = """# Field notes - 2026 season

## Weather
The wet season came early: rainfall was 40% above the ten-year average in March, and the loam plots drained slowly.

## Regimes
Regime B plots were sown a week later than regime A on the same soils.
"""
DOC_QUESTION = "What do the field notes say about the wet season?"

# the Architect (docs/ARCHITECT_DESIGN.md §2.11): a question typed with the switch on, its brief filled by hand, then run
BRIEF_QUESTION = "Is regime C worth switching to from regime A?"
BRIEF_ANSWER = "Use yield instead."                # the person's answer when the analyst asks about a measure the data lacks


def make_dataset(path, seed=20260909):
    rng = np.random.default_rng(seed)
    plots = pd.DataFrame({"plot_id": np.arange(1, 121)})
    plots["regime"] = np.repeat(["A", "B", "C"], 40)
    soil_p = {"A": [0.5, 0.2, 0.3], "B": [0.2, 0.6, 0.2], "C": [0.35, 0.35, 0.3]}     # B sits on more loam
    plots["soil"] = [rng.choice(["clay", "loam", "sand"], p=soil_p[r]) for r in plots["regime"]]
    plot_effect = rng.normal(0, 0.35, len(plots))
    rows = []
    for season in range(1, 7):
        season_effect = rng.normal(0, 0.25)
        rain = rng.normal(420, 60, len(plots)).round(0)
        for i, p in plots.iterrows():
            base = 4.6 + {"clay": -0.2, "loam": 0.8, "sand": -0.5}[p.soil] + {"A": 0.0, "B": 0.5, "C": 0.1}[p.regime]
            y = base + plot_effect[i] + season_effect + 0.0012 * (rain[i] - 420) + rng.normal(0, 0.3)
            rows.append({"plot_id": int(p.plot_id), "regime": p.regime, "soil": p.soil, "season": season,
                         "rainfall_mm": float(rain[i]), "yield_t_ha": round(float(y), 3)})
    df = pd.DataFrame(rows)
    df.to_csv(path, index=False)
    return df


# ----------------------------------------------------------------- helpers
def _turn(user):
    """The turn about to be taken."""
    m = re.search(r"TASK: turn (\d+); up to (\d+)", user)
    return (int(m.group(1)), int(m.group(2))) if m else (1, 15)


def _question(user):
    m = re.search(r"QUESTION:\n(.*?)\n\n(?:BRIEF \(|YOUR NOTE)", user, re.S)      # a run with a brief carries it under the question
    return (m.group(1) if m else "").strip()


def _brief(user):
    """The BRIEF block of the prompt (analyst/brief.py render()), read back: the one-line parts by their labels, the
    person's own Also check lines, what is fixed."""
    m = re.search(r"^BRIEF \([^\n]*\n(.*?)(?:\n\n|\Z)", user, re.S | re.M)
    block = m.group(1) if m else ""
    one = lambda label: (re.search(rf"^{label}: (.*)$", block, re.M) or [None, ""])[1].strip()
    also = re.search(r"^Also check:\n((?:- .*\n?)+)", block, re.M)
    return {"decision": one("Decision"), "expects": one("What they expect to see"), "would_change": one("What would change their mind"),
            "also": [ln[2:].strip() for ln in (also.group(1).splitlines() if also else []) if not ln.rstrip().endswith("[always]")],
            "fixed": dict(re.findall(r"^- (comparison|measure|period): (.*)$", block, re.M))}


def _first_number(text, default):
    m = re.search(r"\d+(?:\.\d+)?", text or "")
    return float(m.group(0)) if m else default


def _grab(user, key, cast=float):
    m = re.search(rf"(?<![A-Z_]){key}=(-?[\d.]+)", user)
    return cast(m.group(1)) if m else None


def _table_rows(user):
    """The soil x regime table cell 2 printed (reset_index().to_string(index=False))."""
    rows = re.findall(r"^\s*(clay|loam|sand)\s+([ABC])\s+(-?[\d.]+)\s+(\d+)\s*$", user, re.M)
    seen, out = set(), []
    for r in rows:
        if (r[0], r[1]) not in seen:
            seen.add((r[0], r[1])); out.append(r)
    return out


def _note(q, est="none yet", held="nothing yet", doubts="-", plan="-", names="df"):
    return (f"- Question as understood: {q}\n- Best estimate so far: {est}\n- Held fixed: {held}\n"
            f"- Open doubts: {doubts}\n- Plan: {plan}\n- Names: {names}\n- Standing instructions from the person: none")


def _cell(thinking, note, code):
    return thinking, f"###STEP###\n{thinking}\n###NOTE###\n{note}\n###ACTION###\nCELL\n```python\n{code}\n```"


def _action(thinking, note, line):
    return thinking, f"###STEP###\n{thinking}\n###NOTE###\n{note}\n###ACTION###\n{line}"


def _report(thinking, note, body):
    return thinking, f"###STEP###\n{thinking}\n###NOTE###\n{note}\n###ACTION###\nREPORT\n{body}"


CELL_INSPECT = """# Shape, dtypes, the soil mix by regime, and raw yield by regime
print(df.shape)
print(df.dtypes.to_string())
print(df['regime'].value_counts().to_dict())
print(pd.crosstab(df['regime'], df['soil']).to_string())
print(df.groupby('regime')['yield_t_ha'].agg(['mean', 'std', 'count']).round(3).to_string())"""

CELL_FAIL = """# Yield by regime within soil (plot-level means first)
plot_means = df.groupby(['plot_id', 'regime', 'soil'], as_index=False)['yield'].mean()
print(plot_means.groupby(['soil', 'regime'])['yield'].mean().round(3).to_string())"""

CELL_ADJUSTED = """# Plot-level means (one row per plot), then B minus A within each soil type,
# weighted by the number of plots compared; uncertainty by bootstrap over PLOTS, not rows
plot_means = df.groupby(['plot_id', 'regime', 'soil'], as_index=False)['yield_t_ha'].mean()
tab = plot_means.groupby(['soil', 'regime'])['yield_t_ha'].agg(['mean', 'count']).round(3)
print(tab.reset_index().to_string(index=False))

def adj_diff(pm, a='A', b='B', rng=None):
    total, weight = 0.0, 0
    for soil, g in pm.groupby('soil'):
        ga, gb = g[g.regime == a]['yield_t_ha'], g[g.regime == b]['yield_t_ha']
        if rng is not None:
            ga = ga.sample(len(ga), replace=True, random_state=rng)
            gb = gb.sample(len(gb), replace=True, random_state=rng)
        n = min(len(ga), len(gb))
        if n:
            total += n * (gb.mean() - ga.mean()); weight += n
    return total / weight

rng = np.random.default_rng(7)
est = adj_diff(plot_means)
boots = np.array([adj_diff(plot_means, rng=rng) for _ in range(500)])
lo, hi = np.percentile(boots, [2.5, 97.5])
raw = plot_means[plot_means.regime == 'B']['yield_t_ha'].mean() - plot_means[plot_means.regime == 'A']['yield_t_ha'].mean()
print(f"RAW_DIFF={raw:.3f}")
print(f"ADJ_DIFF={est:.3f} CI_LO={lo:.3f} CI_HI={hi:.3f}")
print(f"N_PLOTS_A={int((plot_means.regime == 'A').sum())} N_PLOTS_B={int((plot_means.regime == 'B').sum())}")
RESULT('yield, regime B vs A within soil type, plot means', est, lo, hi, 't/ha', 'B higher')
DS.save(plot_means, 'plot_means')"""

CELL_FIGURE = """# Plot-level yield by regime within each soil type
fig, axes = plt.subplots(1, 3, figsize=(10, 3.4), sharey=True)
for ax, (soil, g) in zip(axes, plot_means.groupby('soil')):
    ax.boxplot([g[g.regime == r]['yield_t_ha'].values for r in ['A', 'B', 'C']], tick_labels=['A', 'B', 'C'])
    ax.set_title(f'soil: {soil}'); ax.set_xlabel('regime')
axes[0].set_ylabel('yield (t/ha), plot mean over the seasons')
fig.tight_layout()
plt.show()
# the same contrast as a plotly figure, the way the contract asks for figures (fig.show())
import plotly.graph_objects as go
means = plot_means.groupby('regime')['yield_t_ha'].mean()
pfig = go.Figure(data=[go.Bar(x=list(means.index), y=list(means.values))])
pfig.update_layout(title='mean plot yield by regime (t/ha)')
pfig.show()
print('figure drawn: yield by regime within soil')"""

CELL_C = """# C minus A on the same footing: plot means within soil, bootstrap over plots
est_c = adj_diff(plot_means, a='A', b='C')
rng_c = np.random.default_rng(11)
boots_c = np.array([adj_diff(plot_means, a='A', b='C', rng=rng_c) for _ in range(500)])
lo_c, hi_c = np.percentile(boots_c, [2.5, 97.5])
print(f"ADJ_DIFF_C={est_c:.3f} CI_LO_C={lo_c:.3f} CI_HI_C={hi_c:.3f} N_PLOTS_C={int((plot_means.regime == 'C').sum())}")"""

CELL_BRIEF = """# What the brief fixes: regime C against regime A within soil type, on plot means of yield_t_ha; uncertainty by bootstrap
# over PLOTS. Also checked: whether rainfall differed between the two regimes' plots.
plot_means = df.groupby(['plot_id', 'regime', 'soil'], as_index=False)[['yield_t_ha', 'rainfall_mm']].mean()

def adj_diff(pm, a='A', b='B', rng=None):
    total, weight = 0.0, 0
    for soil, g in pm.groupby('soil'):
        ga, gb = g[g.regime == a]['yield_t_ha'], g[g.regime == b]['yield_t_ha']
        if rng is not None:
            ga = ga.sample(len(ga), replace=True, random_state=rng)
            gb = gb.sample(len(gb), replace=True, random_state=rng)
        n = min(len(ga), len(gb))
        if n:
            total += n * (gb.mean() - ga.mean()); weight += n
    return total / weight

rng_b = np.random.default_rng(11)
est_b = adj_diff(plot_means, a='A', b='C')
boots_b = np.array([adj_diff(plot_means, a='A', b='C', rng=rng_b) for _ in range(500)])
lo_b, hi_b = np.percentile(boots_b, [2.5, 97.5])
rain = plot_means.groupby('regime')['rainfall_mm'].mean()
print(f"BRIEF_DIFF={est_b:.3f} BRIEF_LO={lo_b:.3f} BRIEF_HI={hi_b:.3f}")
print(f"RAIN_C={rain['C']:.1f} RAIN_A={rain['A']:.1f}")
RESULT('yield, regime C vs A within soil type, plot means', est_b, lo_b, hi_b, 't/ha', 'C higher')"""

CELL_BRIEF_COLUMNS = """# The brief fixes the measure: which columns does the data have for it?
print(df.dtypes.to_string())"""

CELL_GENERIC = """# A first look at the columns the question names
print(df.describe(include='all').round(3).to_string())"""

CELL_ALONE = """# A value that loses a fixed share at every step: what is left after the steps
start = 100.0
share = 0.05
steps = 40
left = start
for _ in range(steps):
    left -= share * left
print(f"LEFT={left:.3f}")
RESULT('left after the steps', left, None, None, 'units')"""

SEARCH_DIGEST = (
    "Sourced claims:\n"
    "1. Field trials that compare fertiliser regimes across heterogeneous soils report the within-soil "
    "contrast, since soil type alone can move yield by 0.5-1.0 t/ha [1].\n"
    "2. The plot is the experimental unit: seasons within a plot are repeated measures, and intervals "
    "computed over rows understate uncertainty [2].\n"
    "Summary: compare regimes within soil type and treat the plot as the unit for uncertainty.")
SEARCH_LINKS = [{"link": "https://www.fao.org/agriculture/crops/field-trials", "title": "FAO: designing crop field trials"},
                {"link": "https://onlinelibrary.wiley.com/journal/agronomy", "title": "Agronomy Journal: repeated measures in plot trials"}]

IDEAS = """1. **Season by regime**: Does the B-A advantage hold in every season, or is it carried by one or two wet seasons?
2. **Rainfall as a covariate**: Does adjusting for rainfall change the within-soil B-A estimate, and by how much?
3. **Dose-response in loam**: Within loam alone, is the B effect larger than the pooled estimate suggests?
4. **Plot-level consistency**: What share of plots under B beat the soil-matched A mean in at least five of six seasons?
5. **C on sand**: Is regime C's small overall effect hiding a real advantage on sand plots?"""


class Scenario:
    def __init__(self):
        self.vals = {}

    # ----------------------------------------------------------- dispatch
    def reply(self, system, user):
        if user.startswith("Rewrite the technical report"):
            return "", self.rewrite(user)
        if "Propose five follow-up questions" in user:
            return "", IDEAS
        if "infographic" in user[:400].lower() or "infographic" in system[:400].lower():
            return "", ""
        if system.startswith("You are the reviewer"):
            # as the brief asks (2026-10-06): the cells to check are handed over under TO CHECK NOW; one Checked line per
            # cell, and a REPORT citing a checked cell binds
            handed = [int(n) for n in re.findall(r"^--- cell (\d+) \(", user, re.M)]
            cells = handed or [int(n) for n in re.findall(r"\bcell (\d+)\b", user)]
            last = max(cells) if cells else 1
            checked = "".join(f"- Checked: cell {n} - computes the comparison its line names; matches its line\n" for n in handed)
            return "", ("###REVIEW###\n- The question requires: the comparison the question names, with its uncertainty.\n"
                        f"- Established: the comparison was made and its interval printed [cell {last}].\n" + checked +
                        "- Most consequential problem: none\n"
                        f"- Verdict: REPORT the comparison the question requires is made and its uncertainty stated [cell {last}].")
        if system.startswith("You are the analyst"):
            return self.analyst(user)
        if system.startswith("You are drawing the figures"):
            return "", self.figures(user)
        if system.startswith("You are the Reader"):
            return "", self.reader(user)
        if system.startswith("You are preparing an analysis so that it can be run again"):
            return "", self.promoter(user, system)
        return "", "OK"

    # ------------------------------------------------------------ the promoter (routines, docs/ROUTINES_DESIGN.md)
    def promoter(self, user, system=""):
        """The routine's inputs for the story's first chain: the regime compared becomes a choice from the regime
        column (the analysis compared B against A); the bootstrap size and seed stay the method's. The edits name
        the cell that defines adj_diff, wherever the chain numbered it. With the person's instruction (§15.6) the answer
        names the yield line for the contrast and finds no line for the plot count. For the chain that read no data
        (§24) the inputs are the values its cell starts from - under the brief for such a chain only, so a proposal
        with those inputs says which brief the app sent."""
        alone = re.search(r"# --- cell (\d+) ---\n(?:(?!# --- cell).)*?start = 100\.0", user, re.S)
        if alone and "This analysis read no data" in system:
            cell = int(alone.group(1))
            return json.dumps({
                "name": "What is left after the steps",
                "inputs": [{"key": "start", "label": "Starting value", "type": "number", "default": "100.0", "origin": "the analysis started from 100"},
                           {"key": "steps", "label": "Steps", "type": "number", "default": "40", "origin": "the analysis ran 40 steps"}],
                "edits": [{"cell": cell, "find": "start = 100.0", "replace": "start = INPUTS['start']"},
                          {"cell": cell, "find": "steps = 40", "replace": "steps = int(INPUTS['steps'])"}],
                "kept": ["the share lost at a step is the method's"]})
        m = re.search(r"# --- cell (\d+) ---\n(?:(?!# --- cell).)*?def adj_diff", user, re.S)
        if not m:
            return json.dumps({"name": "As it is", "inputs": [], "edits": [], "kept": ["nothing in this chain varies with the data"]})
        cell = int(m.group(1))
        tracked = {}
        if "THE PERSON'S INSTRUCTION" in user:
            n = re.search(r"^(\d+)\. \[cell \d+\] yield, regime B vs A", user, re.M)
            tracked = {"tracked": [{"asked": "the yield contrast", "lines": [{"line": int(n.group(1)), "name": "Yield, B vs A"}] if n else []}, {"asked": "the plot count", "lines": []}]}
        return json.dumps({
            "name": "Regime contrast within soil, plot means", **tracked,
            "inputs": [{"key": "regime", "label": "The regime compared with A", "type": "choice", "default": "B", "origin": "the analysis compared B against A", "column": "regime", "multiple": False}],
            # the edits a promoter makes are on the method it was shown (§19.3): the raw difference is only printed, so it is not there
            "edits": [e for e in [
                {"cell": cell, "find": "def adj_diff(pm, a='A', b='B', rng=None):", "replace": "def adj_diff(pm, a='A', b=INPUTS['regime'], rng=None):"},
                {"cell": cell, "find": "raw = plot_means[plot_means.regime == 'B']['yield_t_ha'].mean()", "replace": "raw = plot_means[plot_means.regime == INPUTS['regime']]['yield_t_ha'].mean()"},
                {"cell": cell, "find": "RESULT('yield, regime B vs A within soil type, plot means', est, lo, hi, 't/ha', 'B higher')",
                 "replace": "RESULT(f\"yield, regime {INPUTS['regime']} vs A within soil type, plot means\", est, lo, hi, 't/ha', f\"{INPUTS['regime']} higher\")"}] if e["find"] in user],
            "kept": ["the 500 bootstrap draws and the seed are the method's", "soil is the stratification, not an input"]})

    # ------------------------------------------------------------ the figures step (2026-10-11)
    def figures(self, user):
        """After the report: the first question's figure, drawn once from the kernel's variables (the plot means and the
        estimate the cells left) - a matplotlib figure and a Plotly one, as the executor captures both; a caption for
        each. The follow-ups need none: a number answers, or the earlier chain's figure is cited."""
        m = re.search(r"QUESTION:\n(.*?)\n\nTHE REPORT", user, re.S)
        q = (m.group(1) if m else "").strip()
        if q != QUESTIONS[0]:
            return "NONE"
        return ("```python\n" + CELL_FIGURE + "\n```\n"
                "CAPTION: plot-level yield by regime within each soil type, the estimate's spread\n"
                "CAPTION: mean plot yield by regime")

    # ------------------------------------------------------------ the Reader seat
    def reader(self, user):
        """The Reader quotes, exactly, every candidate passage that mentions the wet season (the story's document
        question); whole, as the passages are short. The platform verifies each quote against the unit."""
        hits = [(uid, text) for uid, text in re.findall(r"^\[(D\d+\.\d+)\] \([^)]*\) (.+)$", user, re.M) if "wet season" in text.lower()]
        if not hits:
            return "NOTHING ANSWERS - the passages are about the trial's regimes and soils."
        lines = [f'- [{uid}] "{text.strip()}"' for uid, text in hits]
        return "\n".join(lines) + f"\nSUMMARY: The notes record an early wet season [{hits[0][0]}]."

    # ------------------------------------------------------------ analyst
    def analyst(self, user):
        q = _question(user)
        turn, of = _turn(user)
        forced = "STOP:" in user or "Write REPORT now" in user
        if "\nBRIEF (" in user:
            return self.briefed(user, q, turn, forced)
        if q == QUESTIONS[0]:
            # turn 1 inspects; turn 2 the search (a turn, as every exchange is without documents -, 2026-10-03);
            # turn 3, with the digest in the prompt, the cell that fails; turn 4 the corrected cell; turn 5 a figure cell,
            # which is not run (2026-10-11: figures are drawn after the report, in the figures step); turn 6 the report
            if forced or turn >= 6:
                return self.report_b(user, q)
            return {1: self.t_inspect, 2: self.t_search, 3: self.t_fail, 4: self.t_adjusted, 5: self.t_figure}[turn](q)
        if q == QUESTIONS[1]:
            if forced or turn >= 2:
                return self.report_c(user, q)
            return self.t_cell_c(q)
        if q == DOC_QUESTION:
            # the documents path: a cell with the kernel's D1 object finds where the wet season is, a scoped READ reads
            # that unit whole through the Reader, the report quotes the passage and cites it.
            if forced or "READ (" in user:
                return self.report_doc(user, q)
            if "grep('wet season'" in user:                 # this chain's grep cell is in the record: read the unit it found
                return self.t_doc_read(user, q)
            return self.t_doc(user, q)
        if q == REACH_QUESTION:
            if forced or turn >= 3:
                return self.report_reach(user, q)
            return {1: self.t_reach_refused, 2: self.t_reach_fetch}[turn](q)
        if q == ALONE_QUESTION:
            if forced or turn >= 2:
                return self.report_alone(user, q)
            return _cell("Nothing is loaded and nothing is needed: the answer follows from the three values in the question.",
                         _note(q, plan="compute it step by step, then report", names="-"), CELL_ALONE)
        if q == REVIEW_QUESTION:
            if forced or turn >= 10:
                return _report("Ten checks done.", _note(q, plan="report"), "Ten small checks ran, one per turn [cell 1]; nothing else was computed.")
            return _cell("Check %d of ten." % turn, _note(q, plan="one check per turn"), "print('check %d: rows=%%d' %% len(df))" % turn)
        if forced or turn >= 2:
            return self.report_generic(user, q)
        return _cell("A question outside the scripted story: one look at the data, then a short answer.",
                     _note(q, plan="describe, then report"), CELL_GENERIC)

    # ------------------------------------------------------------ a run with a brief (the Architect)
    def briefed(self, user, q, turn, forced):
        b = _brief(user)
        measure = b["fixed"].get("measure", "")
        # the measure the brief fixes is not in the data - unless the person's answer to that question, which stands where
        # the two differ, names the one to use
        answered = "BRIEF (agreed before your question" in user and "yield" in q.lower()
        if "protein" in measure.lower() and not answered:
            if turn == 1 and not forced:
                return _cell("The brief fixes the measure as protein content. First, the columns the data has.",
                             _note(q, plan="look for the measure the brief fixes", names="df"), CELL_BRIEF_COLUMNS)
            return _action("No column records protein, so the measure the brief fixes cannot be computed, and nothing else is put in its place.",
                           _note(q, doubts="the fixed measure is not in the data", plan="ask the person"),
                           "ASK The brief fixes the measure as protein content, and the data records none: its columns are plot_id, regime, soil, season, "
                           "rainfall_mm and yield_t_ha. The comparison the brief fixes can be made on yield_t_ha. Shall I use yield?")
        if forced or "BRIEF_DIFF=" in user:
            return self.report_brief(user, q, b)
        return _cell("The brief fixes the comparison and the measure: regime C against A within soil type, on plot means of yield. One cell computes it, with the rainfall of the two regimes' plots for the check the brief names.",
                     _note(q, held="soil type (stratified), as the brief fixes", plan="the fixed comparison; then report against the brief", names="df, plot_means, adj_diff, est_b"), CELL_BRIEF)

    def report_brief(self, user, q, b):
        d, lo, hi = (_grab(user, k) for k in ("BRIEF_DIFF", "BRIEF_LO", "BRIEF_HI"))
        rain_c, rain_a = _grab(user, "RAIN_C"), _grab(user, "RAIN_A")
        nos = [int(n) for n in re.findall(r"^--- cell (\d+) ---", user, re.M)]
        cell = max(nos) if nos else 1
        if d is None:
            return _report("The comparison did not print.", _note(q, plan="report"), "## Not established\n\nThe cell did not print the comparison the brief fixes; nothing can be reported.")
        # a part the brief gives as "not said" has no line, as the contract says
        said = lambda part: b[part] if b[part] and b[part] != "not said" else ""
        want, under = _first_number(said("expects"), 0.3), _first_number(said("would_change"), 0.1)
        expected = "met" if lo >= want else ("not met" if hi < want else "cannot tell")
        changed = "seen" if hi < under else ("not seen" if lo >= under else "cannot tell")
        verdicts = ((f"- Expected: {expected} - the gap is {d:.3f} t/ha, interval {lo:.3f} to {hi:.3f} [cell {cell}]\n" if said("expects") else "")
                    + (f"- Would change their mind: {changed}\n" if said("would_change") else ""))
        title = "Regime C is above regime A on like-for-like soil" if lo > 0 else "Regime C is not distinguishable from regime A on like-for-like soil"
        rivals = "".join(f"- {r.rstrip('.')}: mean rainfall was {rain_c:.1f} mm on the C plots and {rain_a:.1f} mm on the A plots [cell {cell}]\n" for r in b["also"])
        body = (f"## {title}\n\nOn plot means within soil type, regime C yields {d:.3f} t/ha against regime A (95% interval {lo:.3f} to {hi:.3f}) [cell {cell}]."
                + (f" For the decision - {said('decision').rstrip('.')} - " + ("the gap is real; whether it is large enough is for the person to judge." if lo > 0 else "this trial gives no reason to switch.") if said("decision") else "") + "\n\n"
                "## Against the brief\n\n" + verdicts + rivals +
                f"- chance: the interval {'excludes' if lo > 0 or hi < 0 else 'includes'} zero [cell {cell}]\n"
                "- measurement error: cannot tell - the data does not say how yield was measured\n"
                "- how the cases compared came to be chosen: the regimes were not assigned at random; soil type is held fixed, nothing else\n\n"
                "## Did not fit\n\n- Nothing.\n\n"
                f"## How it was established\n\nPlot means first, then C minus A within each soil type, weighted by the plots compared; a 500-draw bootstrap over plots [cell {cell}].")
        return _report("The cell printed the comparison the brief fixes and the rainfall of both regimes; the report says how the result stands against the brief.",
                       _note(q, est=f"C-A {d:.3f} t/ha [{lo:.3f}, {hi:.3f}]", held="soil type (stratified), as the brief fixes", plan="report", names="df, plot_means, adj_diff, est_b"), body)

    def t_inspect(self, q):
        return _cell("The question is a between-regime contrast, and 'once soil type is taken into account' says the soil "
                     "mix differs by regime. First: shape, dtypes, the crosstab of regime by soil, and raw yield by regime.",
                     _note(q, plan="inspect; then decide the unit and what to hold fixed"), CELL_INSPECT)

    def t_search(self, q):
        return _action("Repeated seasons per plot means the plot is the unit, not the row. One aimed search on how "
                       "regime trials across mixed soils are reported, to confirm the within-soil contrast and the unit.",
                       _note(q, doubts="whether seasons within a plot are independent; whether rainfall differs by regime",
                             plan="search once; then plot-level means within soil"),
                       "SEARCH fertiliser regime field trial yield comparison within soil type, plot as experimental unit")

    def t_fail(self, q):
        return _cell("Plot-level means first, then the within-soil table.",
                     _note(q, held="soil (by stratifying)", plan="plot means within soil; then the adjusted difference"), CELL_FAIL)

    def t_adjusted(self, q):
        return _cell("KeyError: the column is yield_t_ha, not yield. Same cell, correct name, and I add the adjusted "
                     "difference with a bootstrap over plots so the interval is at the right unit.",
                     _note(q, held="soil type (stratified; weights by plots compared)",
                           doubts="rainfall not yet held fixed", plan="adjusted B-A with a plot-level bootstrap; then a figure",
                           names="df, plot_means"), CELL_ADJUSTED)

    def t_figure(self, q):
        # a figure cell during the analysis, as a model that skipped the contract's Figures section would write: it is not
        # run, and the refusal rides into the next prompt (the stack shows the skipped row and the step that draws later)
        return _cell("The adjusted gap and its interval are printed. One figure of the estimate and where it varies: "
                     "plot-level yield by regime within each soil type.",
                     _note(q, est="see cell 2: adjusted B-A with 95% bootstrap interval", held="soil type (stratified)",
                           doubts="rainfall", plan="figure; then report", names="df, plot_means, adj_diff, est, boots"), CELL_FIGURE)

    # ------------------------------------------------------------ the document
    def t_doc(self, user, q):
        """The DATA block names the kernel's document objects; a cell greps the notes for the wet season the way a
        real analyst would - print(D1.grep(...))."""
        m = re.search(r"^(D\d+) - " + re.escape(DOC_NAME), user, re.M)
        doc = m.group(1) if m else "D1"
        return _action(f"The notes are {doc} in the kernel; the map lists a Weather section. One cell greps them for the "
                       "wet season to find the passage's id, then a READ of that stretch.",
                       _note(q, plan="grep for the passage; READ the stretch; report"),
                       f"CELL\n```python\nprint({doc})\nprint({doc}.grep('wet season', context=0))\n```")

    def t_doc_read(self, user, q):
        """The cell printed the matching unit with its id; the READ of exactly that unit goes through the Reader."""
        m = re.search(r"^\[(D\d+\.\d+)[^\]]*\] [^\n]*wet season", user, re.M | re.I)
        uid = m.group(1) if m else "D1.3"
        return _action(f"The passage is {uid}. READ it whole so the quote is the Reader's, verified against the document.",
                       _note(q, plan=f"READ {uid}; then report", names="-"),
                       f"READ {uid} what do the notes say about the wet season")

    def report_doc(self, user, q):
        # the READ digest in the prompt: take its passage line - the quote the platform verified - and cite the id
        m = re.search(r"^- \[(D\d+\.\d+)\] \([^)]*\) \"(.+)\"\s*$", user, re.M)
        if not m:
            return _report("The passage was not found.", _note(q, plan="report"),
                           "The field notes were looked at but no passage mentions the wet season.")
        uid, passage = m.group(1), m.group(2)
        return _report("The passage is quoted by the Reader; the report quotes it and cites the passage.", _note(q, plan="report"),
                       f"The field notes record an early wet season: {passage} [{uid}]. "
                       "That is the notes' account; whether the trial data agree would be a separate question over `df`.")

    # ------------------------------------------------------------- reports
    def report_b(self, user, q):
        v = {k: _grab(user, k) for k in ("RAW_DIFF", "ADJ_DIFF", "CI_LO", "CI_HI")}
        v["N_PLOTS_A"] = _grab(user, "N_PLOTS_A", int); v["N_PLOTS_B"] = _grab(user, "N_PLOTS_B", int)
        rows = _table_rows(user)
        if v["ADJ_DIFF"] is None:
            body = ("Regime B was not established as better than A within the budget: the within-soil comparison "
                    "did not run before the turns were used up. What is known: the soil mix differs by regime [cell 1], "
                    "so the raw difference is not the answer. Next: the plot-level comparison within soil type.")
            return _report("Out of turns before the adjusted cell ran: say what stands and what does not.",
                           _note(q, plan="report what stands"), body)
        self.vals = v
        table = "| soil | regime | mean yield (t/ha) | plots |\n|---|---|---|---|\n" + \
                "\n".join(f"| {s} | {r} | {m} | {n} |" for s, r, m, n in rows)
        body = f"""Within the same soil type, regime B out-yielded regime A by about {v['ADJ_DIFF']:.2f} t/ha per plot, and the interval does not include zero. The raw gap of {v['RAW_DIFF']:.2f} t/ha overstates it: B was sown on more loam, the most productive soil, and that accounts for part of the raw difference.

## The estimate
Plot-mean yield, regime B minus regime A within soil type, weighted by plots compared: **{v['ADJ_DIFF']:.3f} t/ha** (95% bootstrap interval {v['CI_LO']:.3f} to {v['CI_HI']:.3f}), over {v['N_PLOTS_A']} A plots and {v['N_PLOTS_B']} B plots, each averaged over its seasons [cell 2]. It is a within-soil association; the trial did not randomise regime to plot, so it is not a causal effect of the regime alone.

## Conditions
Soil type held fixed by stratification; the plot is the unit (seasons within a plot are repeated measures); rainfall is not held fixed.

The means behind the estimate [cell 2]:

{table}

## How it was established
Cell 1 showed the soil mix differs by regime. Cell 2 computed plot means, the within-soil B minus A difference weighted by plots compared, and a 500-draw bootstrap resampling plots within each soil and regime.

## Limitations
- What the data cannot support: regime was not randomised, so any plot-level factor that differs by regime and is not soil remains in the estimate.
- How much the answer moves under other choices: the raw contrast is {v['RAW_DIFF']:.2f} t/ha; the soil-adjusted one is {v['ADJ_DIFF']:.2f} t/ha, so the adjustment matters at the first decimal.
- Not certain was computed as stated: nothing; every number above is printed in cell 2.

## Next steps
1. Add rainfall as a covariate and re-estimate the within-soil difference.
2. Check the difference season by season.
3. Compare regime C on the same footing."""
        return _report("Every number I need is printed in cell 2; the figure comes after the report. Report: answer first, "
                       "then the estimate, the conditions, how it was established, the three limitations, next steps.",
                       _note(q, est=f"B-A {v['ADJ_DIFF']:.3f} t/ha per plot, 95% CI [{v['CI_LO']:.3f}, {v['CI_HI']:.3f}], within soil",
                             held="soil type (stratified)", doubts="rainfall; regime not randomised", plan="report",
                             names="df, plot_means, adj_diff, est, boots"), body)

    def report_c(self, user, q):
        c = {k: _grab(user, k) for k in ("ADJ_DIFF_C", "CI_LO_C", "CI_HI_C")}
        c["N_PLOTS_C"] = _grab(user, "N_PLOTS_C", int)
        if c["ADJ_DIFF_C"] is None:
            return _report("Out of turns.", _note(q, plan="report what stands"),
                           "The C versus A comparison did not run within the budget. The method from the earlier chain applies unchanged.")
        self.vals = c
        body = f"""On the same footing as before, regime C is close to regime A: the within-soil difference is {c['ADJ_DIFF_C']:.2f} t/ha per plot and its interval includes zero.

## The estimate
Plot-mean yield, regime C minus regime A within soil type: **{c['ADJ_DIFF_C']:.3f} t/ha** (95% bootstrap interval {c['CI_LO_C']:.3f} to {c['CI_HI_C']:.3f}), over {c['N_PLOTS_C']} C plots [cell 4]. Not distinguishable from no difference at this sample size.

## Conditions
The same as the B comparison: soil held fixed by stratification, the plot as the unit, rainfall not held fixed. [fig 3] from the earlier chain shows C alongside A and B.

## How it was established
Cell 4 reused the plot means and the adjusted-difference function from the earlier chain with C in place of B, and a fresh 500-draw bootstrap over plots.

## Limitations
- What the data cannot support: a small C effect of a tenth of a tonne would sit inside this interval; the trial cannot rule it in or out.
- How much the answer moves under other choices: none checked beyond the soil stratification.
- Not certain was computed as stated: nothing.

## Next steps
1. Pool the three regimes in one model with soil and rainfall.
2. Look at C on sand specifically."""
        return _report("Cell 4 printed the C-A contrast; it straddles zero. Short report on the same footing.",
                       _note(q, est=f"C-A {c['ADJ_DIFF_C']:.3f} t/ha, 95% CI [{c['CI_LO_C']:.3f}, {c['CI_HI_C']:.3f}]",
                             held="soil type (stratified)", plan="report", names="df, plot_means, adj_diff, est_c"), body)

    # ------------------------------------------------------------ the reach report's chain
    def t_reach_refused(self, q):
        return _cell("First a look at what else runs on this box: the process list.",
                     _note(q, plan="list the processes, then ask the service"),
                     "import subprocess\nprint(subprocess.run(['ps', 'aux'], capture_output=True, text=True).stdout[:400])")

    def t_reach_fetch(self, q):
        # the service's address is the stack's own (STACK_FAKE_APIS, set by stack.py for the processes it spawns); the cell
        # names it as a literal, as a model would, and the question does not - so the reach is "not asked for"
        base = os.environ.get("STACK_FAKE_APIS") or "http://127.0.0.1:1"
        return _cell("The process list is not available here. The service's health route says whether it answers, and how many calls it has taken.",
                     _note(q, plan="ask the service's health route, then report"),
                     f"import requests\nr = requests.get('{base}/health', timeout=5)\ncalls = r.json().get('calls', 0)\n"
                     "print(f'calls taken: {calls}')\nRESULT('the service answers', 1.0 if r.ok else 0.0, None, None, '1 = yes')")

    def report_reach(self, user, q):
        nos = [int(n) for n in re.findall(r"^--- cell (\d+) ---", user, re.M)]
        cell = max(nos) if nos else 1
        m = re.search(r"calls taken: (\d+)", user)
        n = m.group(1) if m else "a number of"
        return _report("The service answered; that is the answer.", _note(q, est="answering", plan="report"),
                       f"## The service answers\n\nThe integrations service answered its health route [cell {cell}]; it had taken {n} calls at the time. "
                       "The box's process list could not be read: the executor does not run that operation.")

    def report_alone(self, user, q):
        nos = [int(n) for n in re.findall(r"^--- cell (\d+) ---", user, re.M)]
        cell = max(nos) if nos else 1
        left = _grab(user, "LEFT")
        said = f"{left:.2f}" if left is not None else "an amount the cell did not print"
        return _report("The cell printed what is left; that is the answer.", _note(q, est=f"{said} left", plan="report", names="start, share, steps, left"),
                       f"## What is left\n\nAfter 40 steps of losing 5%, {said} of the 100 is left [cell {cell}]. No data was read: the answer follows from the starting value, the share and the number of steps.")

    def report_generic(self, user, q):
        # the cell this chain ran (the newest in the prompt: a follow-up's cells are numbered along the path), cited
        nos = [int(n) for n in re.findall(r"^--- cell (\d+) ---", user, re.M)]
        cell = max(nos) if nos else 1
        body = ("This question is outside the scripted story of the local stack, so the answer is a placeholder: the "
                f"data was described in [cell {cell}] and nothing further was computed. Ask one of the scenario's questions "
                "to see a full analysis.")
        if "[IMAGE ATTACHED]" in user:               # the plot the person asked about rode along as a picture (2026-10-13)
            body += " The figure attached to the question was in view."
        return _report("Nothing scripted for this question; report the placeholder.", _note(q, plan="report"), body)

    def t_cell_c(self, q):
        return _cell("The B comparison's plot means and function are still in the kernel; C in place of B, "
                     "a fresh bootstrap, same footing.",
                     _note(q, held="soil type (stratified)", plan="C-A adjusted difference; then report",
                           names="df, plot_means, adj_diff"), CELL_C)

    # ------------------------------------------------------------ rewrite
    def rewrite(self, user):
        v = self.vals
        kept = re.search(r"## Against the brief\n.*?## Did not fit\n\n.*?(?=\n\n## |\Z)", user, re.S)
        if kept:                                    # a run with a brief: the two parts stay under their headings, as the task asks
            return "## What was found\nOn like-for-like soil the two regimes were compared on what each plot yielded on average.\n\n" + kept.group(0)
        if "ADJ_DIFF" in v and v.get("ADJ_DIFF") is not None:
            return (f"## What was found\nOn like-for-like soil, plots under regime B produced about {v['ADJ_DIFF']:.2f} tonnes per hectare "
                    f"more than plots under regime A. A plausible range for that gain runs from {v['CI_LO']:.2f} to "
                    f"{v['CI_HI']:.2f} tonnes per hectare, and the whole range is above zero.\n\n## What it depends on\n"
                    "The comparison holds soil type fixed, because regime B happened to be planted on more of the richest "
                    "soil. Rainfall was not held fixed, and the regimes were not assigned at random, so this is a strong "
                    "association rather than a proof of cause.\n\n## What it does not mean\nIt does not say what would happen "
                    f"on a single new plot; the plain gap between all B plots and all A plots was larger, {v['RAW_DIFF']:.2f} "
                    "tonnes per hectare, and part of that is the soil.\n\n## How it was checked\nEach plot was averaged over "
                    "its seasons first, so a plot counts once; the range comes from re-drawing plots many times. The spread "
                    "of plot yields by regime within each soil is in the first figure [fig 3].\n\n"
                    "## What to do next\nAllow for rainfall, look season by season, and compare regime C the same way.")
        if "ADJ_DIFF_C" in v and v.get("ADJ_DIFF_C") is not None:
            return (f"## What was found\nOn like-for-like soil, regime C and regime A are about level: the difference is "
                    f"{v['ADJ_DIFF_C']:.2f} tonnes per hectare, and the plausible range from {v['CI_LO_C']:.2f} to "
                    f"{v['CI_HI_C']:.2f} includes zero.\n\n## What it depends on\nThe same footing as the B comparison: soil type "
                    "held fixed, one value per plot.\n\n## What it does not mean\nA small real effect cannot be ruled out at "
                    "this trial's size.\n\n## What to do next\nPut all three regimes in one model with soil and rainfall.")
        return "The plain-language version of a placeholder answer: nothing was computed for this question."
