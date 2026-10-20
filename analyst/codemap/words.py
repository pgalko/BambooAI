"""Every phrase a reader sees on the map, in one place (blueprint 8.9): input names as the app's top bar names them, the
method glossary, the step and check sentences, the notes. British spelling, as the app. The modal's own words (headings,
tooltips) are in code-map.js. A chain is never named by its number here: a reference is the token {chain:<id>}, and the
client numbers it as its navigator does (blueprint 4.12, 8.6)."""

CHAIN_TOKEN = "{chain:%s}"


def chain_ref(chain_id) -> str:
    """The token the client renders as 'chain n' (or 'an earlier chain')."""
    return CHAIN_TOKEN % chain_id


def chain_label(chain_id) -> str:
    """The input label of what an earlier chain left: 'from {chain:<id>}'."""
    return "from " + chain_ref(chain_id)


def is_chain_label(label) -> bool:
    return isinstance(label, str) and label.startswith("from {chain:")


def lane_name(label, primary_name="primary dataset") -> str:
    """An input's name on the map: the app's own name for a loader's file (intervals.js intervalsAuxDisplayName), the
    primary dataset's own name, 'From {chain:<id>}' for an earlier chain's names, else the file name without its
    extension."""
    if is_chain_label(label):
        return "From " + label[len("from "):]
    for key, name in APP_NAMES:
        if key in label:
            return name
    if label == PRIMARY_LABEL:
        return primary_name
    return label.rsplit(".", 1)[0]


PRIMARY_LABEL = "primary dataset"
CONTEXT_LABEL = "context (CTX)"
# the app's own names for the files of an Intervals.icu load (intervals.js, intervalsAuxDisplayName; pinned by a test)
APP_NAMES = [("wellness_data", "Wellness Summary"), ("activity_summary", "Activity Summary"), ("activity_intervals", "Activity Intervals"),
             ("context_notes", "Context"), ("context_codes", "Context codes"), ("planned_workouts", "Planned workouts"),
             ("rider_profile", "Rider profile"), ("custom_zone_times", "Custom zones")]

UNTRACED = "the arithmetic is not traced"          # a helper's own arithmetic, said plainly, never explained
MADE_IN_CODE = "made in the code"
NOT_MAPPED = "Not mapped: the code could not be read"
NOT_TRACED = "Not traced: the map could not follow how this was made"

GLOSS = [
    ("Spearman", "Do the two measures rise and fall together? From -1 (opposite) to +1 (together)."),
    ("Pearson", "Do the two measures move together along a straight line?"),
    ("linear regression", "The best straight line through the points."),
    ("bootstrap", "Re-draws the rows many times to see how far the number could move; that gives the range."),
    ("percentile", "The value below which a given share of the numbers falls."),
    ("interval for a proportion", "The likely range for a share."),
    ("t-test", "Is the gap between the two groups bigger than chance would give?"),
    ("pivot", "Turns rows into a grid: one row per value of the first column, one column per value of the second."),
    ("group by", "Collapses the rows into one row per group, adding them up or averaging them."),
    ("join", "Lines up two tables on a shared column, so each row gets the matching values."),
    ("merge", "Lines up two tables on a shared column, so each row gets the matching values."),
    ("look up", "Adds a value to each row by looking it up in another table."),
]


def gloss_of(text) -> str:
    low = (text or "").lower()
    for key, g in GLOSS:
        if key.lower() in low:
            return g
    return ""


MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]

VERB_CHIP = {"load": "read", "filter": "filter", "combine": "join", "reshape": "pivot", "summarise": "group",
             "resample": "bootstrap", "record": "RESULT", "draw": "figure", "save": "save", "compute": "compute"}
CHIP_ORDER = ["read", "compute", "filter", "add columns", "join", "pivot", "group", "bootstrap", "RESULT", "figure", "save"]
TEST_SHORT = {"Spearman rank correlation": "Spearman", "linear regression": "linear regression", "Pearson correlation": "Pearson",
              "interval for a proportion": "Wilson interval", "Mann-Whitney U test": "Mann-Whitney", "two-sample t-test": "t-test"}

def status_via(chain_id) -> str:
    return "used through " + chain_ref(chain_id)


# worth checking (blueprint 4.11)
def check_cites(lead_cites_only, chain_id, cells) -> str:
    word = "cell" if len(cells) == 1 else "cells"
    lst = ", ".join(str(c) for c in cells[:-1]) + (" and " if len(cells) > 1 else "") + str(cells[-1])
    lead = "the report cites" if lead_cites_only else "the report also cites"
    return f"{lead} {chain_ref(chain_id)}'s {word} {lst}"


def check_rests_on(chain_id, names, cells) -> str:
    nm = " and ".join(names) if len(names) <= 2 else ", ".join(names[:-1]) + " and " + names[-1]
    return f"rests on {chain_ref(chain_id)}: {nm} ({'cell' if len(cells) == 1 else 'cells'} {', '.join(str(c) for c in cells)})"


def check_input(name, status) -> str:
    return f"{name}: {'loaded in cell 1, never used' if status == 'loaded' else 'offered, never read'}"


def check_no_result(cell) -> str:
    return f"no RESULT line: the answer is only printed, in cell {cell}, and the report cites it"


def check_typed(name, value, cells_txt, n, n_results) -> str:
    return f"{name} = {value} is typed into {cells_txt}, not read from the data; {'all ' if n == n_results else ''}{n} result{'s rest' if n != 1 else ' rests'} on it"


def check_nan(n, cells) -> str:
    return f"{n} result{'s' if n != 1 else ''} came out empty (nan): cell{'s' if len(cells) != 1 else ''} {', '.join(str(c) for c in cells)}"


def check_corrected(n) -> str:
    return f"{n} result{'s were' if n != 1 else ' was'} replaced by {'later cells' if n != 1 else 'a later cell'}"


def check_patterns(names) -> str:
    return f"word lists typed into the code decide what counts ({', '.join(names[:5])})"


# the header's facts and the one line of a chain that ran no code
def meta_line(mode, turns, cells, figures_cell, failed, reviews, n_results) -> str:
    parts = ([mode] if mode else []) + [f"{turns} turn{'s' if turns != 1 else ''}",
                                        f"{cells} cell{'s' if cells != 1 else ''}" + (" and a figures cell" if figures_cell else "")]
    if failed:
        parts.append(f"{failed} failed attempt{'s' if failed != 1 else ''}")
    if reviews:
        parts.append(f"{reviews} review{'s' if reviews != 1 else ''}")
    parts.append(f"{n_results} RESULT line{'s' if n_results != 1 else ''}" if n_results else "no RESULT line")
    return " · ".join(parts)


def meta_nocode(mode, turns, searches) -> str:
    parts = ([mode] if mode else []) + [f"{turns} turn{'s' if turns != 1 else ''}"]
    if searches:
        parts.append(f"{searches} web search{'es' if searches != 1 else ''}")
    return " · ".join(parts + ["no code"])


def nocode_text(searches, reads=0, ideas=False) -> str:
    if ideas:
        return "No code ran in this chain: it proposed questions to ask next, so there is nothing to map."
    src = ("a web search" if searches == 1 else f"{searches} web searches") if searches else ("a document read" if reads == 1 else (f"{reads} document reads" if reads else "what it already knew"))
    return f"No code ran in this chain: it answered from {src}, so there is nothing to map."
