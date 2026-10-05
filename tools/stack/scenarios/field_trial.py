"""Scenario: a fertiliser field trial. Three regimes (A, B, C) on 120 plots over six seasons,
with soil type unevenly spread across regimes - so the raw B-A gap and the within-soil gap
differ, which gives the analyst something to hold fixed.

The scripted analyst answers from the REAL prompt: it reads the question, the turn number
and the cell outputs, so every number in its report is one the kernel printed. The story
for the first question (Deep, six turns): inspect, search, a cell that fails on a wrong
column name (rolled back), the adjusted comparison with a plot-level bootstrap, a figure,
the report. A follow-up ("and regime C?") reuses the warm kernel in two turns. Any other
question gets a short generic two-turn answer, so the stack can be driven interactively.
"""
import re

import numpy as np
import pandas as pd

DATASET_NAME = "field_trial.csv"
QUESTIONS = [
    "Does regime B raise yield over regime A once soil type is taken into account?",
    "And how does regime C compare with A on the same footing?",
]
REVIEW_QUESTION = "Walk through ten small checks of the data, one per turn."     # crosses turn 9: Adaptive's first self-review

# a document attached to the thread (docs/DOCUMENTS_DESIGN.md, phase A): the analyst reads it in a cell
DOC_NAME = "field_notes.md"
DOC_TEXT = """# Field notes - 2026 season

## Weather
The wet season came early: rainfall was 40% above the ten-year average in March, and the loam plots drained slowly.

## Regimes
Regime B plots were sown a week later than regime A on the same soils.
"""
DOC_QUESTION = "What do the field notes say about the wet season?"


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
    m = re.search(r"QUESTION:\n(.*?)\n\nYOUR NOTE", user, re.S)
    return (m.group(1) if m else "").strip()


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
    return thinking, f"###THINKING###\n{thinking}\n###NOTE###\n{note}\n###ACTION###\nCELL\n```python\n{code}\n```"


def _action(thinking, note, line):
    return thinking, f"###THINKING###\n{thinking}\n###NOTE###\n{note}\n###ACTION###\n{line}"


def _report(thinking, note, body):
    return thinking, f"###THINKING###\n{thinking}\n###NOTE###\n{note}\n###ACTION###\nREPORT\n{body}"


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
print(f"N_PLOTS_A={int((plot_means.regime == 'A').sum())} N_PLOTS_B={int((plot_means.regime == 'B').sum())}")"""

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

CELL_GENERIC = """# A first look at the columns the question names
print(df.describe(include='all').round(3).to_string())"""

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
        if system.startswith("You are the Knowledge Distiller"):
            return "", self.card()
        if "infographic" in user[:400].lower() or "infographic" in system[:400].lower():
            return "", ""
        if system.startswith("You are the reviewer"):
            return "", ("###REVIEW###\n- The question requires: the comparison the question names, with its uncertainty.\n"
                        "- Established: the comparison was made and its interval printed.\n"
                        "- Most consequential problem: none\n"
                        "- Verdict: REPORT the comparison the question requires is made and its uncertainty stated.")
        if system.startswith("You are the analyst"):
            return self.analyst(user)
        if system.startswith("You are the Reader"):
            return "", self.reader(user)
        return "", "OK"

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
        if q == QUESTIONS[0]:
            # turn 1 inspects; turn 2 the search (a turn, as every exchange is without documents -, 2026-10-03);
            # turn 3, with the digest in the prompt, the cell that fails; turn 4 the corrected cell; turn 5 the figure;
            # turn 6 the report
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
        if q == REVIEW_QUESTION:
            if forced or turn >= 10:
                return _report("Ten checks done.", _note(q, plan="report"), "Ten small checks ran, one per turn [cell 1]; nothing else was computed.")
            return _cell("Check %d of ten." % turn, _note(q, plan="one check per turn"), "print('check %d: rows=%%d' %% len(df))" % turn)
        if forced or turn >= 2:
            return self.report_generic(user, q)
        return _cell("A question outside the scripted story: one look at the data, then a short answer.",
                     _note(q, plan="describe, then report"), CELL_GENERIC)

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

[fig 3] shows the plot-level yields by regime within each soil type.

## How it was established
Cell 1 showed the soil mix differs by regime. Cell 2 computed plot means, the within-soil B minus A difference weighted by plots compared, and a 500-draw bootstrap resampling plots within each soil and regime. Cell 3 drew the figure.

## Limitations
- What the data cannot support: regime was not randomised, so any plot-level factor that differs by regime and is not soil remains in the estimate.
- How much the answer moves under other choices: the raw contrast is {v['RAW_DIFF']:.2f} t/ha; the soil-adjusted one is {v['ADJ_DIFF']:.2f} t/ha, so the adjustment matters at the first decimal.
- Not certain was computed as stated: nothing; every number above is printed in cell 2.

## Next steps
1. Add rainfall as a covariate and re-estimate the within-soil difference.
2. Check the difference season by season.
3. Compare regime C on the same footing."""
        return _report("Every number I need is printed in cell 2 and the figure is cell 3. Report: answer first, "
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

    def report_generic(self, user, q):
        body = ("This question is outside the scripted story of the local stack, so the answer is a placeholder: the "
                "data was described in [cell 1] and nothing further was computed. Ask one of the scenario's questions "
                "to see a full analysis.")
        return _report("Nothing scripted for this question; report the placeholder.", _note(q, plan="report"), body)

    def t_cell_c(self, q):
        return _cell("The B comparison's plot means and function are still in the kernel; C in place of B, "
                     "a fresh bootstrap, same footing.",
                     _note(q, held="soil type (stratified)", plan="C-A adjusted difference; then report",
                           names="df, plot_means, adj_diff"), CELL_C)

    # ------------------------------------------------------------ rewrite
    def rewrite(self, user):
        v = self.vals
        if "ADJ_DIFF" in v and v.get("ADJ_DIFF") is not None:
            return (f"## What was found\nOn like-for-like soil, plots under regime B produced about {v['ADJ_DIFF']:.2f} tonnes per hectare "
                    f"more than plots under regime A. A plausible range for that gain runs from {v['CI_LO']:.2f} to "
                    f"{v['CI_HI']:.2f} tonnes per hectare, and the whole range is above zero.\n\n## What it depends on\n"
                    "The comparison holds soil type fixed, because regime B happened to be planted on more of the richest "
                    "soil. Rainfall was not held fixed, and the regimes were not assigned at random, so this is a strong "
                    "association rather than a proof of cause.\n\n## What it does not mean\nIt does not say what would happen "
                    f"on a single new plot; the plain gap between all B plots and all A plots was larger, {v['RAW_DIFF']:.2f} "
                    "tonnes per hectare, and part of that is the soil.\n\n## How it was checked\nEach plot was averaged over "
                    "its seasons first, so a plot counts once; the range comes from re-drawing plots many times.\n\n"
                    "## What to do next\nAllow for rainfall, look season by season, and compare regime C the same way.")
        if "ADJ_DIFF_C" in v and v.get("ADJ_DIFF_C") is not None:
            return (f"## What was found\nOn like-for-like soil, regime C and regime A are about level: the difference is "
                    f"{v['ADJ_DIFF_C']:.2f} tonnes per hectare, and the plausible range from {v['CI_LO_C']:.2f} to "
                    f"{v['CI_HI_C']:.2f} includes zero.\n\n## What it depends on\nThe same footing as the B comparison: soil type "
                    "held fixed, one value per plot.\n\n## What it does not mean\nA small real effect cannot be ruled out at "
                    "this trial's size.\n\n## What to do next\nPut all three regimes in one model with soil and rainfall.")
        return "The plain-language version of a placeholder answer: nothing was computed for this question."

    # --------------------------------------------------------------- memory
    def card(self):
        return """```yaml
name: within_soil_plot_level_contrast
kind: method
status: candidate
hooks:
  answers_question: "How much does one regime change yield compared with another when the soil mix differs by regime?"
  use_when: "Comparing treatments across plots with repeated seasons and an unevenly spread stratifying factor"
body:
  function_definition: "Average each plot over its seasons; within each stratum compute treatment minus control on the plot means; weight strata by the number of plots compared; bootstrap by resampling plots within stratum and treatment for the interval."
  assumes: "The stratifying factor is the main imbalance; plots are exchangeable within stratum and treatment."
  limitations: "Does not adjust for covariates that vary within stratum (rainfall); not causal without randomised assignment."
  rationale: "Plots, not rows, are the sampling unit; stratifying removes the imbalance the raw contrast carries."
relations:
  requires: []
  depends_on: []
  produces: []
  alternative_to: []
  complemented_by: []
```"""
