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
import time

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
# a chain asked from an earlier chain (docs/BRANCH_DESIGN.md §3): the kernel goes back to the state that chain ended in, so its
# cell finds what the first analysis made and nothing of the chain asked after it (the reach chain's `calls`)
BACK_QUESTION = "How many plots stand behind the comparison?"
# a branch (docs/BRANCH_DESIGN.md §4): the person goes back to the turn that pooled the soil types in the first analysis
# and says this; the analyst goes on from there with a cell of its own and a report
BRANCH_HINT = "Keep the soil types apart."
BRANCH_TURN = 4

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

# the Pathfinder (docs/ARCHITECT_DESIGN.md §2.11): a question typed with the switch on, its brief filled by hand, then run
BRIEF_QUESTION = "Is regime C worth switching to from regime A?"
BRIEF_ANSWER = "Use yield instead."                # the person's answer when the analyst asks about a measure the data lacks
# the Pathfinder's questions, in the order of its instructions (analyst/architect.md), each with the part it asks for
ARCHITECT_ASKS = (("decision", "What will you do differently depending on the answer?"),
                  ("thinks", "What do you think is going on, and what makes you think so?"),
                  ("expects", "What do you expect to see?"))
ARCHITECT_READY = "The brief is ready: start the analysis, or change a line."
# the check against the data (docs/ARCHITECT_DESIGN.md §2.13): what the scripted Pathfinder looks up for a line the brief
# rests on, by a word of the line - the planted cases - and what it says around the round
ARCHITECT_CHECKING = "Checking this against the data."
ARCHITECT_LOOKS = (("rain", {"op": "total", "column": "rainfall_mm", "by": "regime"}),          # "The C plots got the most rain."
                   ("same number", {"op": "count", "by": "regime"}),                             # "Each regime has the same number of plots."
                   ("seasons", {"op": "list", "column": "season"}),                              # "The trial ran for ten seasons."
                   ("same soil", {"op": "list", "column": "soil"}))                              # "All plots are on the same soil."
ARCHITECT_UNRECORDED = "nothing loaded records it"
ARCHITECT_KEEP = ["Keep it", "Change it"]
ARCHITECT_NOW = "What do you think is going on now, and what makes you think so?"
# another explanation (docs/ARCHITECT_DESIGN.md §2.14): what the scripted Pathfinder proposes with its marks, from a column the
# data has, and what it adds to its last message while the proposal is unticked
ARCHITECT_PROPOSES = {"text": "The C plots sit on other soil than the A plots", "shows": "the gap narrows within a soil type", "column": "soil"}
ARCHITECT_TICK = " What I proposed under Other explanations to test can be ticked."
# the saved analyses (docs/ARCHITECT_DESIGN.md §3.7): what the Pathfinder says while they are read, and when passages were found
ARCHITECT_LOOKING = "I am looking in your saved analyses."
ARCHITECT_FOUND = " Your saved analyses hold something on this: build on it, or go another way?"      # said with the choices: one to each analysis found
ARCHITECT_BUILD_ON = 'Build on "{}"'                                 # the choice that names an analysis, where more than one was found
ARCHITECT_AGAIN = "Look in my saved analyses again."                 # the person asks for one more reading, in words
# the Pathfinder as a tutor (docs/ARCHITECT_DESIGN.md §2.16-§2.18): what could be looked at, and the question worded - written at once
TUTOR_QUESTION = "Plot the two regimes side by side"                 # a bare request: the question is worked out in the conversation
TUTOR_FIRST = ("Two regimes can be put side by side in more than one way. What should the plot show?\n\n"
               "- what each regime gives, season by season;\n- how the plots of one regime spread against the other's.")
TUTOR_CHOICES = ["Season by season", "The spread", "I cannot tell yet"]
ARCHITECT_BACK = "I have put that into the question. Is that what you mean?"      # said with a wording: the engine writes it as the question at once
ARCHITECT_YES = ["Yes, that is it", "Change something"]
ARCHITECT_WRITTEN = "Good. Start the analysis when you are ready, or go on."
ARCHITECT_OWN = "The question is: "                                  # the person gives a wording of their own: the Pathfinder gives it as its wording
ARCHITECT_UNREAD = "Word it yourself."                               # ... or leaves it to the Pathfinder, which then writes the question under the brief: the engine keeps none of it
ARCHITECT_UNREAD_WORDING = "A wording written in the wrong place"
# the figures and their draft (§2.19, §2.20): asked to show them, the Pathfinder describes the figures - a draft of each is then drawn; asked for another order, it names each by its number
COLD_POINTER = "as in the analysis of 2 March"                       # words a question may carry that point outside what the Analyst is given: the question's check names them
ARCHITECT_PLACED = "The question pointed to something the Analyst is not given. I took that out."
FIGURES_QUESTION = "Plot the yield of regime C against regime A"
ARCHITECT_SHOW = "Show me what the figures will look like."
ARCHITECT_DRAFTING = "A draft of the figures is being drawn. Is that what you want to see?"
ARCHITECT_SWAP = "Put the second figure first."
ARCHITECT_SWAPPED = "Done: the second figure stands first."
TARGET = "the target"                                                # what follows from a rule: 5 percent more each season, from 4.0 t/ha
# a question that follows the tutor's analysis (§2.17, §2.18): the saved analyses are read on a follow-up too, a part of the analysis before is opened and read, and "build on it" brings an analysis into the brief
FOLLOW_QUESTION = "And regime B beside them - how was the first plot made?"
ARCHITECT_OPENING = "I am opening the report of the analysis before this one."
ARCHITECT_OPENED = "Its report opens: "
ARCHITECT_BUILD = ["Build on it", "Go another way"]
ARCHITECT_BUILT = "Done: the Analyst gets that analysis, and can open it."
ARCHITECT_ANOTHER = "Then the brief builds on none of them."
BARE_DONE = "Nothing is loaded, so one cell stood in for the work"      # how a briefed run without data reports
SAVED_JUDGE = "What was compared, and what was found?"
SAVED_NOTE = "An earlier analysis that names what this question asks about."
SAVED_QUESTION = "Is regime C still worth switching to from regime A?"      # a question the briefed analysis, once saved, bears on
SAVED_SLOW = 3.0                 # seconds the reader takes over the first reply of a second reading: time for the walk to press Skip


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


def described(first, second):
    """The figures the scripted Pathfinder describes for a question about two regimes: the yield of each by season
    and the plot yields of each - both for the data to give - and the target, which follows from its rule."""
    pair = [{"name": f"regime {first}"}, {"name": f"regime {second}"}]
    return [{"title": f"Yield by season, regime {first} and regime {second}", "kind": "line", "x": "season", "y": "yield, t/ha", "series": pair,
             "note": "Whether the gap holds from season to season."},
            {"title": f"Plot yields in regime {first} and regime {second}", "kind": "box", "x": "regime", "y": "yield, t/ha", "series": pair,
             "note": "How much the plots of one regime differ among themselves."},
            {"title": "The target: 5 percent more each season", "kind": "line", "x": "season", "y": "yield, t/ha", "series": [{"name": TARGET}],
             "note": "What a rise of 5 percent a season from 4.0 t/ha comes to."}]


def draft_cell(titles):
    """The cell that drafts figures where no data is, each under its title: the target computed from its rule, and
    said so; the yield of each regime by season as lines and the plot yields of each as boxes, on made-up numbers -
    as any other, as bars."""
    lines = ["# A draft of the figures: nothing is loaded here", "import random", "import plotly.graph_objects as go", "random.seed(7)", "seasons = list(range(1, 7))"]
    for k, title in enumerate(titles, 1):
        pair = [f"regime {r}" for r in re.findall(r"regime (\w)\b", title)] or ["regime C", "regime A"]
        if "target" in title.lower():
            traces, said = f"[go.Scatter(x=seasons, y=[round(4.0 * 1.05 ** (s - 1), 2) for s in seasons], name={TARGET!r})]", ", meta='computed'"
        elif "by season" in title.lower():
            traces, said = f"[go.Scatter(x=seasons, y=[round(4.0 + 0.1 * s + random.uniform(-0.3, 0.3), 2) for s in seasons], name=name) for name in {pair!r}]", ""
        elif "plot yields" in title.lower():
            traces, said = f"[go.Box(y=[round(random.gauss(4.4, 0.4), 2) for _ in range(24)], name=name) for name in {pair!r}]", ""
        else:
            traces, said = "[go.Bar(x=['clay', 'loam', 'sand'], y=[round(random.uniform(3.6, 4.8), 2) for _ in range(3)])]", ""
        lines += [f"fig{k} = go.Figure(data={traces})", f"fig{k}.update_layout(title={title!r}{said})", f"fig{k}.show()"]
    return "\n".join(lines)


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
    return {"decision": one("What the answer is for"), "expects": one("What they expect to see"), "would_change": one("What would change their mind"),
            "also": [ln[2:].strip() for ln in (also.group(1).splitlines() if also else []) if not ln.rstrip().endswith("[always]")],
            "fixed": dict(re.findall(r"^- (comparison|measure|period): (.*)$", block, re.M))}


def _holds(line, fact, numbers):
    """Whether a planted line holds against what its lookup found: the regime the line names has the largest number of
    all; every group has the same number; the list has as many different values as the line says, in a word."""
    words = {"one": 1, "same": 1, "three": 3, "six": 6, "ten": 10}
    if "most" in line:
        named = re.search(r"\b([ABC])\b", line)
        return bool(named) and numbers.get(named.group(1)) == max(numbers.values())
    if "same number" in line:
        return len(set(numbers.values())) == 1
    said = next((n for word, n in words.items() if re.search(rf"\b{word}\b", line)), None)
    different = re.search(r": (\d+) different", fact)
    return said == (int(different.group(1)) if different else 1)


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

CELL_APART = """# B minus A within each soil type, from the plot means the kept turns left in the kernel
apart = {soil: float(g[g.regime == 'B']['yield_t_ha'].mean() - g[g.regime == 'A']['yield_t_ha'].mean()) for soil, g in plot_means.groupby('soil')}
for soil in sorted(apart):
    print(f"APART_{soil.upper()}={apart[soil]:.3f}")
print(f"KEPT={int('adj_diff' in globals())} LATER={int('calls' in globals())}")"""

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

def agreed_cell(titles):
    """The cell that draws the figures agreed in a brief, each under its title: the yield of each regime by season as
    lines, the plot yields of each regime as boxes, the target from its rule, any other as bars of the mean yield
    by soil type."""
    lines = ["# The figures agreed with the person, each under its title", "import plotly.graph_objects as go",
             "by_season = df.groupby(['season', 'regime'])['yield_t_ha'].mean().unstack()", "by_soil = df.groupby('soil')['yield_t_ha'].mean()"]
    for k, title in enumerate(titles, 1):
        traces = ("[go.Scatter(x=list(by_season.index), y=list(by_season[r]), name='regime ' + r) for r in by_season.columns]" if "by season" in title.lower() else
                  "[go.Box(y=list(df[df.regime == r]['yield_t_ha']), name='regime ' + r) for r in sorted(df.regime.unique())]" if "plot yields" in title.lower() else
                  f"[go.Scatter(x=list(range(1, 7)), y=[round(4.0 * 1.05 ** k, 2) for k in range(6)], name={TARGET!r})]" if "target" in title.lower() else
                  "[go.Bar(x=list(by_soil.index), y=list(by_soil.values))]")
        lines += [f"fig{k} = go.Figure(data={traces})", f"fig{k}.update_layout(title={title!r})", f"fig{k}.show()"]
    return "\n".join(lines)


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
raw = plot_means.groupby('regime')['yield_t_ha'].mean()
by_soil = {s: g[g.regime == 'C']['yield_t_ha'].mean() - g[g.regime == 'A']['yield_t_ha'].mean() for s, g in plot_means.groupby('soil')}
widest, narrowest = max(by_soil, key=by_soil.get), min(by_soil, key=by_soil.get)
print(f"BRIEF_DIFF={est_b:.3f} BRIEF_LO={lo_b:.3f} BRIEF_HI={hi_b:.3f}")
print(f"RAIN_C={rain['C']:.1f} RAIN_A={rain['A']:.1f} RAW_DIFF={raw['C'] - raw['A']:.3f}")
print(f"GAP_WIDE={by_soil[widest]:.3f} SOIL_WIDE={widest} GAP_NARROW={by_soil[narrowest]:.3f} SOIL_NARROW={narrowest}")
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

# the web search (0335): OpenRouter's reply to the Web Search seat's one request, as its chat completions give it - the
# answer with a link to its page after each claim, the pages cited as annotations, the searches run in the usage. The
# seat reads it for real (tools/stack/webapp_launcher.py): two claims with a source each, two searches at the engine's fee.
SEARCH_QUERY = "fertiliser regime field trial yield comparison within soil type, plot as experimental unit"
SEARCH_CLAIMS = ("Field trials that compare fertiliser regimes across heterogeneous soils report the within-soil contrast, "
                 "since soil type alone can move yield by 0.5-1.0 t/ha",
                 "The plot is the experimental unit: seasons within a plot are repeated measures, and intervals computed "
                 "over rows came out 41.7% too narrow in one review")
# titles as pages have them - brackets, a pair of $ (0340: a title's brackets, escaped for markdown, had been read as a formula)
SEARCH_PAGES = [{"url": "https://www.fao.org/agriculture/crops/field-trials", "title": "FAO: designing crop field trials [PDF]"},
                {"url": "https://onlinelibrary.wiley.com/journal/agronomy", "title": "Agronomy Journal: repeated measures at $5 to $10 a plot"}]
SEARCH_RETURNED = [{"url": "https://www.example.org/trial-design", "title": "Notes on trial design"}] + SEARCH_PAGES      # as the search returns them: a page more than the answer links
SEARCH_USAGE = {"prompt_tokens": 5200, "completion_tokens": 140, "total_tokens": 5340, "server_tool_use": {"web_search_requests": 2}}
SEARCH_REPLY = {
    "provider": "Stack",
    "choices": [{"finish_reason": "stop", "message": {"role": "assistant", "content": (
        f"{SEARCH_CLAIMS[0]} [fao.org]({SEARCH_PAGES[0]['url']}).\n"
        f"{SEARCH_CLAIMS[1]} [wiley.com]({SEARCH_PAGES[1]['url']}).\n"
        "Compare regimes within soil type and treat the plot as the unit for uncertainty."),
        "annotations": [{"type": "url_citation", "url_citation": dict(p, content="an excerpt of the page")} for p in SEARCH_RETURNED]}}],
    "usage": SEARCH_USAGE}

# next questions (docs/ARCHITECT_DESIGN.md §2.7): what the scripted Pathfinder asks from a line of each kind, as the prompt names the
# kinds (analyst/next_questions.py SAID) - a title, and the question around the line's own words
NEXT_MISFIT = "The gap is not the same on every soil"        # the misfit the briefed report plants, from the gap by soil its cell printed
NEXT_FROM = {"Did not fit": ("What did not fit", "What lies behind this: {t}?"),
             "Rests on": ("What it rests on", "Does the answer change without this: {t}?"),
             "Would change their mind": ("The other result", "How close did the result come to this: {t}?"),
             "Also checked": ("Another explanation", "Does this hold in each season taken alone: {t}?"),
             "Proposed, not tested": ("A proposal", "Is this so: {t}?"),
             "Fixed, what was compared": ("The comparison", "What is the gap in each season, for {t}?"),
             "Fixed, the measure": ("The measure", "Does the answer hold on each season's {t}?"),
             "Fixed, the period": ("The period", "Does the answer hold in each half of {t}?"),
             "Asked": ("The question", "Season by season: {t}?"),
             "Found": ("The answer", "Does this hold in every season: {t}?"),
             "Found earlier": ("An earlier answer", "Does this still hold: {t}?")}


class Scenario:
    def __init__(self):
        self.vals = {}

    # ----------------------------------------------------------- dispatch
    def reply(self, system, user):
        if user.startswith("Rewrite the technical report"):
            return "", self.rewrite(user)
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
        if system.startswith("You are the Pathfinder"):
            return "", self.architect(user)
        if system.startswith("You propose the questions to analyse next"):
            return "", self.next_questions(user)
        if system.startswith("You are drawing the figures"):
            return "", self.figures(user)
        if system.startswith("You draw a draft of the figures"):
            return "", self.draft(user)
        if system.startswith("You are given a task as an analyst will be given it"):
            return "", self.cold(user)
        if system.startswith("You are the Reader"):
            return "", self.reader(user)
        if system.startswith("You look things up in a person's saved analyses"):
            return "", self.saved_reader(user)
        if system.startswith("You read saved analyses for another model"):
            return "", self.saved_pieces(user)
        if system.startswith("You are preparing an analysis so that it can be run again"):
            return "", self.promoter(user, system)
        return "", "OK"

    # ------------------------------------------------------------ the question's check (docs/ARCHITECT_DESIGN.md §2.22)
    def cold(self, user):
        """The question read as the Analyst will read it, before its analysis starts (analyst/cold.py): the words of
        QUESTION that point outside what was given - COLD_POINTER, where the question carries it - and none in any
        other question."""
        question = (re.search(r"^QUESTION:\n(.*?)(?:\n\nBRIEF \(|\n\nReply with)", user, re.S | re.M) or [None, ""])[1]
        return json.dumps({"cannot_place": [COLD_POINTER] if COLD_POINTER in question else []})

    # ------------------------------------------------------------ the Pathfinder (docs/ARCHITECT_DESIGN.md §2.12)
    def architect(self, user):
        """The Pathfinder's reply, read off its prompt (analyst/architect.py). On its first turn it writes what the
        question states: the two regimes it compares, or - where the analyst had stopped and asked - the measure the
        person's answer names. After that the person's last message goes, as they gave it, into the part the Pathfinder
        had just asked for ("... because ..." also gives what the view rests on; "The measure is ..." changes what is
        fixed; "skip" leaves the part empty). Then it asks for the next part still empty and not yet asked for, with
        two choices where the question names two courses. When nothing is left to ask it checks the lines the brief
        rests on that show no mark: a lookup for each line a word of which it knows (ARCHITECT_LOOKS), then - the
        results before it - a mark for each, and where a line does not hold the question whether to keep the view or
        change it. With the marks it proposes another explanation, from a column the data has (ARCHITECT_PROPOSES).
        With every line marked it says the brief is ready - and, while its proposal is unticked, that it can be
        ticked. On a question that follows no analysis, where the person has saved analyses, it has them read once:
        with its lookups, or in the place of saying that the brief is ready; right after a reading that found
        something it asks, with the brief ready, whether to build on it: two choices where one analysis was found,
        else a choice to each analysis, by what was asked then, and one to go another way. Told to build, it names
        that analysis by its number (`build`); told to go another way, it names none. Asked in words to look again
        (ARCHITECT_AGAIN), it has them read once more.

        The question worked out in the conversation (2026-11-17): to a bare request (TUTOR_QUESTION) it says what
        the plot could show, in a message of several lines with choices; the first choice taken, it gives its
        wording of the question, with two choices; a wording the person gives (ARCHITECT_OWN) it gives as its own.
        The engine writes a wording at once. Left to word it itself (ARCHITECT_UNREAD), it writes the question
        under the brief - which the engine does not keep.

        A question that follows the tutor's analysis (FOLLOW_QUESTION): it has the saved analyses read, then opens
        the report of the analysis before, then says how that report opens, with two choices; told to build on it,
        it names the first analysis found.

        The figures (2026-11-18): asked to show them (ARCHITECT_SHOW) it describes three, for the two regimes the
        question names, and says a draft is being drawn; asked for the second first (ARCHITECT_SWAP) it gives the
        figures of BRIEF by their numbers, the first two the other way round.

        The question's check (2026-11-19): where CONVERSATION ends on what a reader could not place, it gives the
        question without those words as its wording, and says so (ARCHITECT_PLACED)."""
        find = lambda pattern: (re.search(pattern, user, re.S | re.M) or [None, ""])[1].strip()
        question = find(r"^QUESTION:\n(.*?)\n\nBRIEF \(").split("\n(first asked as: ")[0]
        empty = lambda key: find(rf"^{re.escape(key)}: ([^\n]*)$") in ("", "(empty)")
        said_so_far = find(r"^CONVERSATION:\n(.*?)\n\n(?:OPENED \(|Reply with)")
        talk = re.findall(r"^(Pathfinder|Person): (.*)$", said_so_far, re.M)
        unplaced = re.match(r"A reader given what the analyst will be given could not place: (.*)$", said_so_far.splitlines()[-1] if said_so_far else "")
        if unplaced:
            wording = question
            for phrase in re.findall(r'"(.*?)"', unplaced.group(1)):
                wording = wording.replace(phrase, "")
            return json.dumps({"say": ARCHITECT_PLACED, "wording": re.sub(r"[ ,]+([?.])", r"\1", re.sub(r" {2,}", " ", wording)).strip(" ,")})
        if question == FOLLOW_QUESTION:
            if talk and talk[-1] == ("Person", ARCHITECT_BUILD[0]):
                return json.dumps({"say": ARCHITECT_BUILT, "build": [1]})
            if "\nOPENED (" in user:                            # the part it opened is in view: it speaks from it
                opens = (re.search(r"^--- the report ---\n(?:#+ *)?(.*)$", user, re.M) or [None, ""])[1]
                return json.dumps({"say": ARCHITECT_OPENED + opens, "choices": ARCHITECT_BUILD})
            if "\nSaved analyses" in "\n" + said_so_far:        # the reading is done: the report of the analysis before
                return json.dumps({"say": ARCHITECT_OPENING, "open": {"what": "report"}})
            return json.dumps({"say": ARCHITECT_LOOKING, "recall": True})
        asked = [key for key, ask in ARCHITECT_ASKS if ("Pathfinder", ask) in talk]
        pair = re.search(r"regime (\w)\b.*\bregime (\w)\b", question)
        writes = {}
        if not talk and question == TUTOR_QUESTION:
            return json.dumps({"say": TUTOR_FIRST, "choices": TUTOR_CHOICES})
        if not talk:
            other = re.match(r"(?i)use (\w+) instead", question)
            if other and "The analyst stopped and asked:" in user:
                return json.dumps({"brief": {"fixed": {"measure": other.group(1)}}, "say": ARCHITECT_READY})
            if pair and empty("fixed.comparison"):
                writes["fixed"] = {"comparison": f"regime {pair.group(1)} against regime {pair.group(2)}"}
        elif talk[-1][0] == "Person":
            said, before = talk[-1][1].strip(), talk[-2][1] if len(talk) > 1 and talk[-2][0] == "Pathfinder" else ""
            if said == TUTOR_CHOICES[0] or said.startswith(ARCHITECT_OWN):
                wording = said[len(ARCHITECT_OWN):] if said.startswith(ARCHITECT_OWN) else question.rstrip("?.") + ", season by season"
                return json.dumps({"say": ARCHITECT_BACK, "wording": wording, "choices": ARCHITECT_YES})
            if said == ARCHITECT_YES[0]:
                return json.dumps({"say": ARCHITECT_WRITTEN})
            if said == ARCHITECT_SHOW:
                return json.dumps({"say": ARCHITECT_DRAFTING, "figures": described(*(pair.groups() if pair else ("C", "A"))), "choices": ARCHITECT_YES})
            if said == ARCHITECT_SWAP:
                held = len(re.findall(r"^- \[\d+\] ", (re.search(r"^figures:\n((?:- \[\d+\] .*\n)+)", user, re.M) or [None, ""])[1], re.M))
                return json.dumps({"say": ARCHITECT_SWAPPED, "figures": [2, 1] + list(range(3, held + 1))})
            named = re.fullmatch(re.escape(ARCHITECT_BUILD_ON).replace(r"\{\}", "(.*)"), said)
            if said == ARCHITECT_BUILD[0] or named:             # the person chose: the one analysis found, or the one they named
                numbers = {asked: int(k) for k, asked in re.findall(r'^\[(\d+)\] \S+ "(.*?)": ', said_so_far, re.M)}
                return json.dumps({"say": ARCHITECT_BUILT, "build": [numbers.get(named.group(1), 0) if named else 1]})
            if said == ARCHITECT_BUILD[1]:
                return json.dumps({"say": ARCHITECT_ANOTHER, "build": []})
            if said == ARCHITECT_AGAIN:
                return json.dumps({"say": ARCHITECT_LOOKING, "recall": True})
            if said == ARCHITECT_UNREAD:
                return json.dumps({"brief": {"question": ARCHITECT_UNREAD_WORDING}, "say": ARCHITECT_WRITTEN})
            part = next((key for key, ask in ARCHITECT_ASKS + (("thinks", ARCHITECT_NOW),) if ask == before), None)
            measure = re.match(r"(?i)the measure is (.+?)\.?$", said)
            if measure:
                writes["fixed"] = {"measure": measure.group(1)}
            elif said == ARCHITECT_KEEP[1]:
                return json.dumps({"say": ARCHITECT_NOW})
            elif part and said.lower() != "skip":
                if part == "thinks" and " because " in said:
                    view, ground = said.split(" because ", 1)
                    writes.update(thinks=view.strip() + ".", rests_on=[ground.strip()[:1].upper() + ground.strip()[1:]])
                else:
                    writes[part] = said
        nxt = next(((key, ask) for key, ask in ARCHITECT_ASKS if key not in asked and key not in writes and empty(key)), None)
        if nxt:
            reply = {"brief": writes, "say": nxt[1]}
            if nxt[0] == "decision" and pair:
                reply["choices"] = [f"Switch to regime {pair.group(1)}", f"Keep regime {pair.group(2)}"]
            return json.dumps(reply)
        # nothing left to ask: the lines the brief rests on that show no mark are checked, then the brief is ready
        rests = re.search(r"^rests_on:\n((?:- .*\n)+)", user, re.M)
        lines = re.findall(r"^- (.*?)( \[(?:holds|does not hold|cannot be checked)\b.*\])?$", rests.group(1) if rests else "", re.M)
        open_lines = [text for text, mark in lines if not mark] + writes.get("rests_on", [])
        found = {about: fact for about, fact in re.findall(r'^\d+\. about "(.*)" - (.*)$', said_so_far, re.M)}      # the last lookup made for a line
        since = said_so_far[max(said_so_far.rfind("\nPathfinder: "), said_so_far.rfind("\nPerson: "), 0):]      # what came back after the last thing said
        looked = bool(re.search(r'^\d+\. about ".*" - ', since, re.M))             # a round of lookups
        read_now = "\nSaved analyses" in since                                      # a reading of the saved analyses
        recall = bool(re.search(r"^SAVED: \d+$", user, re.M)) and "EARLIER (" not in user and "\nSaved analyses" not in "\n" + said_so_far
        asks = [{"about": text, **look} for text in open_lines for look in [next((l for word, l in ARCHITECT_LOOKS if word in text.lower()), None)] if look]
        if asks and not looked:
            return json.dumps({"brief": writes, "say": ARCHITECT_CHECKING, "lookups": asks, **({"recall": True} if recall else {})})
        if recall and not asks:
            return json.dumps({"brief": writes, "say": ARCHITECT_LOOKING, "recall": True})
        numbers = {about: {k: float(v.replace(",", "")) for k, v in re.findall(r"(\w+) (\d[\d,]*(?:\.\d+)?)(?= ·|$)", fact.split(": ", 1)[-1])} for about, fact in found.items()}
        marks, failed = [], []
        for text in open_lines:
            fact, k = found.get(text, ""), next((int(n) for n, about in reversed(re.findall(r'^(\d+)\. about "(.*)" - ', said_so_far, re.M)) if about == text), None)
            if not fact or "not looked up" in fact:
                marks.append({"line": text, "mark": "cannot be checked", "why": ARCHITECT_UNRECORDED})
                continue
            holds = _holds(text, fact, numbers[text])
            marks.append({"line": text, "mark": "holds" if holds else "does not hold", "lookup": k})
            if not holds:
                failed.append(f"{text.rstrip('.')} ({fact.split(': ', 1)[-1]})")
        proposes = bool(marks) and ARCHITECT_PROPOSES["text"] not in user and re.search(r"^soil: ", user, re.M) is not None
        unticked = proposes or f"- {ARCHITECT_PROPOSES['text']} [proposed by you, not accepted]" in user
        holds = re.findall(r'^\[\d+\] \S+ "(.*?)": ', since, re.M) if read_now else []      # what was asked in each analysis the reading just made found
        holds_some = bool(holds)
        reply = {"brief": writes, "marks": marks, "say": ARCHITECT_READY + (ARCHITECT_TICK if unticked else "") + (ARCHITECT_FOUND if holds_some else "")}
        if proposes:
            reply["propose"] = [ARCHITECT_PROPOSES]
        if holds_some:
            reply["choices"] = ARCHITECT_BUILD if len(holds) == 1 else [ARCHITECT_BUILD_ON.format(asked) for asked in holds][:3] + ARCHITECT_BUILD[1:]
        if failed:
            reply.update(say=f"{'One line does' if len(failed) == 1 else 'Some lines do'} not hold: {'; '.join(failed)}. Keep what you think, or change it?", choices=ARCHITECT_KEEP)
        return json.dumps(reply)

    # ------------------------------------------------------------ the saved analyses (docs/ARCHITECT_DESIGN.md §3.6, §3.7)
    def saved_reader(self, user):
        """The reader's reply, read off its prompt (analyst/reader.py): first a cell that lists the saved runs whose
        question, title or report holds a word of the question; then - where it listed any - a question to the second
        model about them; then its answer: the second model's quote for each run, and, where it answered for more
        than one, the runs grouped by its answer. Where the cell lists none, the answer is empty. A second reading -
        the brief it is given says what it builds on, as it does once a reading found something - takes its time over
        the first reply (SAVED_SLOW)."""
        question = (re.search(r"^QUESTION:\n(.*?)\n\n", user, re.S | re.M) or [None, ""])[1]
        words = sorted({w for w in re.findall(r"[a-z]{5,}", question.lower())} - {"which", "there", "their", "about", "would", "should", "better", "still"})
        if "\n[1] CELL\n" not in user:
            if re.search(r"^builds_on:", user, re.M):
                time.sleep(SAVED_SLOW)
            return ("CELL\n```python\nwords = " + repr(words) + "\nhits = [r['id'] for r in SAVED['runs'] if any(w in (r['question'] + ' ' + r['title'] + ' ' + r['report']).lower() for w in words)]\n"
                    "print(hits)\n```")
        if "] JUDGE " not in user:
            listed = re.search(r"^PRINTED:\n(\[.*\])$", user, re.M)
            hits = json.loads(listed.group(1).replace("'", '"')) if listed else []
            return "JUDGE\n" + json.dumps({"runs": hits, "parts": ["report"], "question": SAVED_JUDGE}) if hits else 'ANSWER\n{"found": []}'
        rows = re.findall(r'^- (\S+) \| [^|]+ \| ([^|]+) \| "(.*)"$', user, re.M)
        answer = {"found": [{"run": run, "quote": quote, "note": SAVED_NOTE} for run, _, quote in rows]}
        if len(rows) > 1:
            ways = {}
            for run, said, _ in rows:
                ways.setdefault(said.strip(), []).append(run)
            answer["across"] = {"topic": "What was compared", "groups": [{"label": label, "runs": runs} for label, runs in ways.items()]}
        return "ANSWER\n" + json.dumps(answer)

    def saved_pieces(self, user):
        """The second model's reply, read off its prompt: for each analysis given, what its title says, with the
        first sentence of its report under the title as the quote - word for word, so it stands."""
        answers = []
        for run, body in re.findall(r"^=== (\S+) ===\n(.*?)(?=^=== \S+ ===\n|\nReply with the JSON object\.)", user, re.S | re.M):
            title = (re.search(r"^TITLE: (.*)$", body, re.M) or [None, ""])[1]
            report = body.split("\nREPORT:\n", 1)[1] if "\nREPORT:\n" in body else ""
            line = next((ln.strip() for ln in report.splitlines() if ln.strip() and not ln.lstrip().startswith(("#", "|", "-", ">", "*"))), "")
            quote = re.split(r"(?<=[.!?])\s", line, maxsplit=1)[0][:300]
            if len(quote) >= 8:
                answers.append({"run": run, "answer": " ".join(title.split()[:8]) or "it reports a comparison", "quote": quote})
        return json.dumps({"answers": answers})

    # ------------------------------------------------------------ next questions (docs/ARCHITECT_DESIGN.md §2.7)
    def next_questions(self, user):
        """The questions that could follow an analysis, read off the prompt (analyst/next_questions.py): one from each
        line under SOURCES in the order given - the level's own lines come first there - as far as five go. A question
        is the line's own words in the sentence its kind has (NEXT_FROM); the planted misfit gets the question it calls
        for, on the soil where the gap is widest. A question already proposed for the analysis is not asked again. At
        the level that joins two findings each question joins the answer with one other line."""
        level = (re.search(r"^LEVEL: (\w+) - ", user, re.M) or [None, ""])[1]
        listed = user.split("\nSOURCES:\n", 1)[-1].split("\n\nReply with", 1)[0]
        lines = [(int(n), kind, text) for n, kind, text in re.findall(r"^(\d+)\. ([^:]+): (.*)$", listed, re.M)]
        before = re.findall(r"^- (.*)$", (re.search(r"^PROPOSED BEFORE:\n((?:- .*\n)+)", user, re.M) or [None, ""])[1], re.M)
        bare = lambda text: re.sub(r"\s*\[cell \d+\]\.?\s*$", "", text).rstrip(".?")
        def question(kind, text):
            wide = re.search(r"t/ha on (\w+),", text) if text.startswith(NEXT_MISFIT) else None
            if wide:
                return {"title": f"The {wide.group(1)} plots", "question": f"Is regime C above regime A on {wide.group(1)} alone, on plot means of yield?"}
            title, sentence = NEXT_FROM[kind]
            return {"title": title, "question": sentence.format(t=bare(text))}
        if level == "blend":
            answer = next(n for n, kind, _ in lines if kind == "Found")
            joined = [{"title": "Two findings", "question": f"Does one explain the other: the answer, and this - {bare(text)}?", "from": [answer, n]}
                      for n, kind, text in lines if n != answer]
            return json.dumps({"questions": [q for q in joined if q["question"] not in before][:5]})
        asked = [{**question(kind, text), "from": [n]} for n, kind, text in lines]
        return json.dumps({"questions": [q for q in asked if q["question"] not in before][:5]})

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

    # ------------------------------------------------------------ the draft of the figures (2026-11-18)
    def draft(self, user):
        """Before the analysis (docs/ARCHITECT_DESIGN.md §2.20): one cell that draws each figure under FIGURES TO DRAW
        under its title, with no data (draft_cell)."""
        listed = re.search(r"^FIGURES TO DRAW:\n((?:\d+\. .*(?:\n|$))+)", user, re.M)
        return "```python\n" + draft_cell(re.findall(r'^\d+\. "(.*?)"(?: - .*)?$', listed.group(1) if listed else "", re.M)) + "\n```"

    # ------------------------------------------------------------ the figures step (2026-10-11)
    def figures(self, user):
        """After the report: the first question's figure, drawn once from the kernel's variables (the plot means and the
        estimate the cells left) - a matplotlib figure and a Plotly one, as the executor captures both; a caption for
        each. The follow-ups need none: a number answers, or the earlier chain's figure is cited.

        Where the prompt lists the figures agreed with the person (docs/ARCHITECT_DESIGN.md §2.19), each is drawn
        from the data under its title, word for word - whatever cell drew its draft. With two or more agreed, the
        first reply leaves the last one out: the step is asked again, and then draws them all."""
        agreed = re.search(r"^THE FIGURES AGREED WITH THE PERSON[^\n]*\n((?:\d+\. .*\n)+)", user, re.M)
        if agreed:
            titles = re.findall(r'^\d+\. "(.*?)"(?: - .*)?$', agreed.group(1), re.M)
            draw = titles if len(titles) < 2 or "YOUR LAST REPLY LEFT OUT" in user else titles[:-1]
            return "```python\n" + agreed_cell(draw) + "\n```\n" + "\n".join(f"CAPTION: {t[:1].lower() + t[1:]}" for t in draw)
        m = re.search(r"QUESTION:\n(.*?)\n\n(?:HINT FROM THE PERSON|THE FIGURES AGREED|THE DRAFT THE PERSON SAW|THE REPORT)", user, re.S)
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
        if "\nHINT FROM THE PERSON (" in user:
            # a branch: the turns kept are in the prompt, and the hint; one cell of its own, then the report
            if forced or "APART_CLAY=" in user:
                return self.report_apart(user, q)
            return _cell("The person went back to the pooled comparison and wants the soil types kept apart: B minus A within each, from the plot means.",
                         _note(q, held="soil type (each on its own)", plan="B minus A within each soil type, then report", names="df, plot_means, apart")
                         .replace("Standing instructions from the person: none", "Standing instructions from the person: " + BRANCH_HINT), CELL_APART)
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
        if q == BACK_QUESTION:
            if forced or turn >= 2:
                return self.report_back(user, q)
            return _cell("The plot means are in the kernel from the first analysis; count them.",
                         _note(q, plan="count the plots, then report", names="df, plot_means"),
                         "print(f\"PLOTS={len(plot_means)} LATER={int('calls' in globals())}\")")
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

    # ------------------------------------------------------------ a run with a brief (the Pathfinder)
    def briefed(self, user, q, turn, forced):
        b = _brief(user)
        measure = b["fixed"].get("measure", "")
        if "\nDATA:\n(no dataset attached" in "\n" + user:      # nothing is loaded: one cell stands in for the work, then the report
            if forced or turn >= 2:
                return self.report_bare(user, q, b)
            return _cell("Nothing is loaded: one cell stands in for the work the question asks.", _note(q, plan="one cell, then report", names="-"), CELL_ALONE)
        if turn == 1 and not forced and "\nSaved analyses the person chose" in user:      # the brief names a saved analysis: it is opened first (SHOW SAVED 1)
            return _action("The brief names a saved analysis. I open it before computing anything.", _note(q, plan="read the saved analysis; then the fixed comparison", names="df"), "SHOW SAVED 1")
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
        if forced or re.search(r"BRIEF_DIFF=-?\d", user):      # this chain's cell printed it: a saved analysis shown holds the line of code, not a number
            return self.report_brief(user, q, b)
        return _cell("The brief fixes the comparison and the measure: regime C against A within soil type, on plot means of yield. One cell computes it, with the rainfall of the two regimes' plots for the check the brief names.",
                     _note(q, held="soil type (stratified), as the brief fixes", plan="the fixed comparison; then report against the brief", names="df, plot_means, adj_diff, est_b"), CELL_BRIEF)

    def report_brief(self, user, q, b):
        d, lo, hi = (_grab(user, k) for k in ("BRIEF_DIFF", "BRIEF_LO", "BRIEF_HI"))
        rain_c, rain_a, raw = _grab(user, "RAIN_C"), _grab(user, "RAIN_A"), _grab(user, "RAW_DIFF")
        soils = re.search(r"GAP_WIDE=(-?[\d.]+) SOIL_WIDE=(\w+) GAP_NARROW=(-?[\d.]+) SOIL_NARROW=(\w+)", user)
        # a result the person's frame does not explain: the gap by soil, as the cell printed it
        misfit = f"- {NEXT_MISFIT}: {float(soils.group(1)):.3f} t/ha on {soils.group(2)}, {float(soils.group(3)):.3f} on {soils.group(4)} [cell {{cell}}]" if soils else "- Nothing."
        nos = [int(n) for n in re.findall(r"^--- cell (\d+) ---", user, re.M)]
        cell = max(nos) if nos else 1
        if d is None:
            return _report("The comparison did not print.", _note(q, plan="report"), "## Not established\n\nThe cell did not print the comparison the brief fixes; nothing can be reported.")
        said = lambda part: b[part]                           # a part the brief does not give has no line, as the contract says
        want, under = _first_number(said("expects"), 0.3), _first_number(said("would_change"), 0.1)
        expected = "met" if lo >= want else ("not met" if hi < want else "cannot tell")
        changed = "seen" if hi < under else ("not seen" if lo >= under else "cannot tell")
        verdicts = ((f"- Expected: {expected} - the gap is {d:.3f} t/ha, interval {lo:.3f} to {hi:.3f} [cell {cell}]\n" if said("expects") else "")
                    + (f"- Would change their mind: {changed}\n" if said("would_change") else ""))
        title = "Regime C is above regime A on like-for-like soil" if lo > 0 else "Regime C is not distinguishable from regime A on like-for-like soil"
        # a line for each Also check: the one about soil by the gap with and without soil held fixed, any other by the rainfall
        rivals = "".join(f"- {r.split(': it would show')[0].rstrip('.')}: " + (f"the gap is {raw:.3f} t/ha across all plots and {d:.3f} within soil type [cell {cell}]\n" if "soil" in r and raw is not None
                         else f"mean rainfall was {rain_c:.1f} mm on the C plots and {rain_a:.1f} mm on the A plots [cell {cell}]\n") for r in b["also"])
        body = (f"## {title}\n\nOn plot means within soil type, regime C yields {d:.3f} t/ha against regime A (95% interval {lo:.3f} to {hi:.3f}) [cell {cell}]."
                + (f" For the decision - {said('decision').rstrip('.')} - " + ("the gap is real; whether it is large enough is for the person to judge." if lo > 0 else "this trial gives no reason to switch.") if said("decision") else "") + "\n\n"
                "## Against the brief\n\n" + verdicts + rivals +
                f"- chance: the interval {'excludes' if lo > 0 or hi < 0 else 'includes'} zero [cell {cell}]\n"
                "- measurement error: cannot tell - the data does not say how yield was measured\n"
                "- how the cases compared came to be chosen: the regimes were not assigned at random; soil type is held fixed, nothing else\n\n"
                "## Did not fit\n\n" + misfit.format(cell=cell) + "\n\n"
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
                       "SEARCH " + SEARCH_QUERY)

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
        # the search's two sources, cited by their numbers where the prompt still shows them - turns after the search (0337) -,
        # with the figure the second one gave: no cell printed it, and the report's number check takes it as the source's
        fao, journal = ((" [1]", "; in one review intervals over rows came out 41.7% too narrow [2]")
                        if f"[1] {SEARCH_PAGES[0]['title']}" in user and f"[2] {SEARCH_PAGES[1]['title']}" in user else ("", ""))
        body = f"""Within the same soil type, regime B out-yielded regime A by about {v['ADJ_DIFF']:.2f} t/ha per plot, and the interval does not include zero. The raw gap of {v['RAW_DIFF']:.2f} t/ha overstates it: B was sown on more loam, the most productive soil, and that accounts for part of the raw difference.

## The estimate
Plot-mean yield, regime B minus regime A within soil type, weighted by plots compared: **{v['ADJ_DIFF']:.3f} t/ha** (95% bootstrap interval {v['CI_LO']:.3f} to {v['CI_HI']:.3f}), over {v['N_PLOTS_A']} A plots and {v['N_PLOTS_B']} B plots, each averaged over its seasons [cell 2]. It is a within-soil association; the trial did not randomise regime to plot, so it is not a causal effect of the regime alone.

## Conditions
Soil type held fixed by stratification, as trials across mixed soils report the contrast{fao}; the plot is the unit (seasons within a plot are repeated measures){journal}; rainfall is not held fixed.

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
        # ... and where it cites them it ends with a list of them of its own, as the first live report with web sources did
        # (0338): the report the reader gets has one list, the engine's
        if fao:
            body += "\n\n## Sources\n\n" + "\n".join(f"[{n}] {p['title']} - {p['url']}" for n, p in enumerate(SEARCH_PAGES, 1))
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

    def report_apart(self, user, q):
        nos = [int(n) for n in re.findall(r"^--- cell (\d+) ---", user, re.M)]
        cell = max(nos) if nos else 1
        v = {soil: _grab(user, "APART_" + soil.upper()) for soil in ("clay", "loam", "sand")}
        return _report("Each soil type has its own difference now; that is what the hint asked for.",
                       _note(q, est="B minus A by soil type, see the report", held="soil type (each on its own)", plan="report", names="df, plot_means, apart")
                       .replace("Standing instructions from the person: none", "Standing instructions from the person: " + BRANCH_HINT),
                       f"## Each soil type on its own\n\nKept apart, regime B minus regime A is {v['clay']:.3f} t/ha on clay, {v['loam']:.3f} on loam and "
                       f"{v['sand']:.3f} on sand [cell {cell}]. The hint asked for the soil types apart, and this is the comparison within each.")

    def report_back(self, user, q):
        nos = [int(n) for n in re.findall(r"^--- cell (\d+) ---", user, re.M)]
        cell = max(nos) if nos else 1
        plots = _grab(user, "PLOTS", int)
        return _report("The cell printed the count; that is the answer.", _note(q, est=f"{plots} plots", plan="report", names="df, plot_means"),
                       f"## The plots\n\n{plots} plots stand behind the comparison [cell {cell}].")

    def report_alone(self, user, q):
        nos = [int(n) for n in re.findall(r"^--- cell (\d+) ---", user, re.M)]
        cell = max(nos) if nos else 1
        left = _grab(user, "LEFT")
        said = f"{left:.2f}" if left is not None else "an amount the cell did not print"
        return _report("The cell printed what is left; that is the answer.", _note(q, est=f"{said} left", plan="report", names="start, share, steps, left"),
                       f"## What is left\n\nAfter 40 steps of losing 5%, {said} of the 100 is left [cell {cell}]. No data was read: the answer follows from the starting value, the share and the number of steps.")

    def report_bare(self, user, q, b):
        """A briefed run with nothing loaded: what the cell printed and what did not fit - nothing - and, only where
        the brief says what the person expects, how the result stands against it."""
        nos = [int(n) for n in re.findall(r"^--- cell (\d+) ---", user, re.M)]
        cell = max(nos) if nos else 1
        left = _grab(user, "LEFT")
        against = f"\n\n## Against the brief\n- Expected: cannot tell - nothing was measured [cell {cell}]." if b["expects"] else ""
        return _report("The cell ran; that is all there is to report.", _note(q, plan="report", names="start, share, steps, left"),
                       f"## What was done\n\n{BARE_DONE}: it printed {left if left is not None else 0:.2f} [cell {cell}]." + against + "\n\n## Did not fit\n- Nothing.")

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
                    "The comparison holds soil type fixed" + (", as trials on mixed soils are reported [1]," if "report the contrast [1]" in user else ",") + " because regime B happened to be planted on more of the richest "
                    "soil. Rainfall was not held fixed, and the regimes were not assigned at random, so this is a strong "
                    "association rather than a proof of cause.\n\n## What it does not mean\nIt does not say what would happen "
                    f"on a single new plot; the plain gap between all B plots and all A plots was larger, {v['RAW_DIFF']:.2f} "
                    "tonnes per hectare, and part of that is the soil.\n\n## How it was checked\nEach plot was averaged over "
                    "its seasons first, so a plot counts once; the range comes from re-drawing plots many times. The spread "
                    "of plot yields by regime within each soil is in the first figure [fig 3].\n\n"
                    "## What to do next\nAllow for rainfall, look season by season, and compare regime C the same way."
                    + ("\n\n**Sources**\n- [1] FAO" if "report the contrast [1]" in user else ""))      # a list of its own, though it is shown none (0338)
        if "ADJ_DIFF_C" in v and v.get("ADJ_DIFF_C") is not None:
            return (f"## What was found\nOn like-for-like soil, regime C and regime A are about level: the difference is "
                    f"{v['ADJ_DIFF_C']:.2f} tonnes per hectare, and the plausible range from {v['CI_LO_C']:.2f} to "
                    f"{v['CI_HI_C']:.2f} includes zero.\n\n## What it depends on\nThe same footing as the B comparison: soil type "
                    "held fixed, one value per plot.\n\n## What it does not mean\nA small real effect cannot be ruled out at "
                    "this trial's size.\n\n## What to do next\nPut all three regimes in one model with soil and rainfall.")
        return "The plain-language version of a placeholder answer: nothing was computed for this question."
