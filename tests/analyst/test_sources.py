"""Web sources (0337): one number for a page along a path, the sourced claims of a run's searches in view to its report,
an action written inside a fence, the number check, the report's and the rewrite's sources. The session over a real
in-process kernel; the model and the search are scripted. Run: python3 tests/analyst/test_sources.py"""
import os, sys
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path[:0] = [os.path.dirname(os.path.abspath(__file__)), ROOT, os.path.join(ROOT, "delve")]
import pandas as pd
from analyst import Session, Budget, Notebook, parse_turn, report
from analyst import sources as src
from analyst.session import SOURCES_CITED
from kernel import PersistentKernel

passed, failed = [], []
def check(name, cond, detail=""):
    (passed if cond else failed).append(name); print(("  ok   " if cond else "  FAIL ") + name + ("" if cond else f"  <- {detail}"))

df = pd.DataFrame({"plot": [1, 2, 3, 4], "regime": ["A", "B", "A", "B"], "yield_t_ha": [3.1, 3.3, 2.8, 3.0]})
NOTE = "- Question as understood: q\n- Best estimate so far: none yet\n- Held fixed: nothing\n- Open doubts: -\n- Plan: p\n- Names: df"

# ---- a digest's two lists, read back ----
_FAO, _JRN, _GDE = "https://www.fao.org/agriculture/crops/field-trials", "https://onlinelibrary.wiley.com/journal/agronomy", "https://www.example.org/guide_(plots)"
def _digest(claims, pages, without="Sand held 77.7 t/ha."):
    """A search's digest as the host writes it: the sourced claims, the sources by number, a figure without a source, the summary."""
    return (src.CLAIMS_HEAD + "\n" + "\n".join("- " + c for c in claims) + "\n\n" + src.SOURCES_HEAD + "\n" + "\n".join(f"[{n}] {t} - {a}" for n, t, a in pages)
            + "\n\nWITHOUT A SOURCE (the search model named no page for these figures: do not cite them):\n- " + without + "\n\nSUMMARY (the search model's own words):\nIn its own words.")
_d1 = _digest(["Regime B plots yielded 3.2 t/ha on loam. [1]", "Soil type alone moves yield by 0.5-1.0 t/ha. [1][2]"],
              [(1, "Designing crop field trials", _FAO), (2, "Repeated measures in plot trials", _JRN)])
_d2 = _digest(["The plot is the unit over 12 seasons. [2]", "A guide gives 41.5 plots per regime. [3]"], [(2, "Repeated measures in plot trials", _JRN), (3, "A guide [to] plot_trials", _GDE)])
_d3 = _digest(["Clay held 2.9 t/ha in 2024. [4]"], [(4, "Clay soils | yields", "https://soils.example.org/clay")])
_known = src.along([_d1, _d2])
check("sources: a digest's sources are read back as it numbers them; along a path a page has one number - the one it first got, whichever search finds it - and a new page takes the next; "
      "two spellings of an address are one page; on a path searched before 0337, each digest numbered from 1, the first page under a number keeps it; a failed search lists none",
      src.pages(_d1) == [{"n": 1, "title": "Designing crop field trials", "link": _FAO}, {"n": 2, "title": "Repeated measures in plot trials", "link": _JRN}]
      and [(p["n"], p["link"]) for p in _known] == [(1, _FAO), (2, _JRN), (3, _GDE)]
      and src.numbers([{"link": "https://fao.org/agriculture/crops/field-trials/#design"}, {"link": "https://new.example.org/a"}, {"link": _JRN}], _known)
          == {"https://fao.org/agriculture/crops/field-trials/#design": 1, "https://new.example.org/a": 4, _JRN: 2}
      and src.numbers([{"link": _JRN}, {"link": _FAO}]) == {_JRN: 1, _FAO: 2}
      and [(p["n"], p["link"]) for p in src.along([_d1, _digest(["x [1]"], [(1, "Another page", "https://other.example.org/x")])])] == [(1, _FAO), (2, _JRN)]
      and src.pages("(search failed: boom)") == [] and src.along([]) == [] and src.claims(_d1) == "Regime B plots yielded 3.2 t/ha on loam. [1]\nSoil type alone moves yield by 0.5-1.0 t/ha. [1][2]",
      (src.pages(_d1), _known))
_rep = "Loam gave 3.2 t/ha [3]; the unit is the plot [3][1]. Not these: x[2], [cell 2], `[2]`, [see][2], [[2]](u), [2](u), [2024], [9].\n```\n[2]\n```"
check("sources: a report cites a source by its number alone in brackets - [3], or [3][1] for two; an index, a cell's citation, a number in code or of no source is none; "
      "the report then ends with the pages it cites, by number, each title a link to its page - the title's own brackets and marks as words, a bracket in an address written so that it does not end the link; "
      "a report that cites none gains nothing",
      [p["n"] for p in src.cited(_rep, _known)] == [1, 3]
      and src.listing(_rep, _known) == "\n\n## Sources\n\n- [1] [Designing crop field trials](" + _FAO + ")\n- [3] [A guide \\[to\\] plot\\_trials](https://www.example.org/guide_%28plots%29)"
      and src.listing("Nothing from the web: x[1].", _known) == "" and src.listing(_rep, []) == "", src.listing(_rep, _known))
check("sources: what stays in view of a run's searches - the claims of each under its number on the path and its query, then the sources they cite, once each, by number, with the site; "
      "the heading says how the report cites one; nothing where no search returned a sourced claim",
      src.in_view([(1, "yield by soil type", _d1), (2, "plot as the unit", _d2), (3, "nothing", "(search failed: boom)")]) == src.IN_VIEW_HEAD
      + "\nsearch 1 (yield by soil type):\n- Regime B plots yielded 3.2 t/ha on loam. [1]\n- Soil type alone moves yield by 0.5-1.0 t/ha. [1][2]"
      + "\nsearch 2 (plot as the unit):\n- The plot is the unit over 12 seasons. [2]\n- A guide gives 41.5 plots per regime. [3]"
      + "\nSOURCES:\n[1] Designing crop field trials (fao.org)\n[2] Repeated measures in plot trials (onlinelibrary.wiley.com)\n[3] A guide [to] plot_trials (example.org)"
      and "the report cites a source as [3]" in src.IN_VIEW_HEAD and src.in_view([(1, "q", "(no results)")]) == "" and src.in_view([]) == "",
      src.in_view([(1, "yield by soil type", _d1), (2, "plot as the unit", _d2)]))
_fence = lambda body: parse_turn("###NOTE###\nn\n###ACTION###\n" + body)[2]
check("parse: an action written inside a fence is the action - SEARCH with its query, bare or as python, SHOW, NAMES, a REPORT - where it had run as a cell and failed on its first word (0337); "
      "Python that begins with such a word is a cell, and so is a cell that does not compile",
      (_fence("```\nSEARCH yield by soil type\n```").verb, _fence("```\nSEARCH yield by soil type\n```").arg) == ("search", "yield by soil type")
      and (_fence("```python\nSEARCH yield by soil type, plot as unit\n```").verb, _fence("```python\nSEARCH yield by soil type, plot as unit\n```").arg) == ("search", "yield by soil type, plot as unit")
      and (_fence("```\nSHOW 3 4\n```").verb, _fence("```\nSHOW 3 4\n```").arg) == ("show", "3 4") and _fence("```\nNAMES\n```").verb == "names"
      and (_fence("```\nREPORT\n# Title\n\nThe answer.\n```").verb, _fence("```\nREPORT\n# Title\n\nThe answer.\n```").arg) == ("report", "# Title\n\nThe answer.")
      and (_fence("```python\nSEARCH = df.shape\nprint(SEARCH)\n```").verb, _fence("```python\nSEARCH = df.shape\nprint(SEARCH)\n```").arg) == ("cell", "SEARCH = df.shape\nprint(SEARCH)")
      and _fence("```python\nprint(1\n```").verb == "cell" and _fence("```python\nNAMES = 3\n```").verb == "cell",
      (_fence("```\nSEARCH yield by soil type\n```"), _fence("```\nNAMES\n```"), _fence("```\nREPORT\n# Title\n\nThe answer.\n```")))
_SRC_SCRIPT = ["###NOTE###\n" + NOTE + "\n###ACTION###\nSEARCH yield by soil type",
               "###NOTE###\n" + NOTE + "\n###ACTION###\n```\nSEARCH plot as the unit\n```",
               "###NOTE###\n" + NOTE + "\n###ACTION###\nCELL\n```python\nprint('plots', 12)\n```",
               "###NOTE###\n" + NOTE + "\n###ACTION###\nREPORT\n# Regime B yields more on loam\n\nRegime B plots yielded 3.2 t/ha on loam [1], over 12 plots [cell 1]. "
               "A guide gives 41.5 plots per regime [3]; sand held 77.7 t/ha. In code `x[2]` is an index.",
               "###NOTE###\n" + NOTE + "\n###ACTION###\nSEARCH yield on clay",
               "###NOTE###\n" + NOTE + "\n###ACTION###\nCELL\n```python\nprint('rows', len(df))\n```",
               "###NOTE###\n" + NOTE + "\n###ACTION###\nREPORT\n# Clay holds less\n\nClay held 2.9 t/ha [4], against 3.2 t/ha on loam [1]."]
_src_seen = {"prompts": [], "rewrites": []}
def _src_llm(system, user, **hints):
    if user.startswith("Rewrite"):
        _src_seen["rewrites"].append(user)
        return "# Regime B yields more on loam\n\nOn loam, plots under regime B gave 3.2 tonnes per hectare [1].", {"cost": 0}
    if system.startswith("You are drawing the figures"): return "NONE", {"cost": 0}
    _src_seen["prompts"].append(user)
    return _SRC_SCRIPT[len(_src_seen["prompts"]) - 1], {"cost": 0.001}
_src_search = lambda q: _d1 if "soil" in q else _d2 if "unit" in q else _d3
ksrc = PersistentKernel(df=df); nbsrc = Notebook("tsrc")
try:
    _ssrc = Session(ksrc, nbsrc, _src_llm, data_description="d", search=_src_search)
    rs1 = _ssrc.run("Does regime B yield more?", budget=Budget(turns=10, dollars=1.0))
    rs2 = _ssrc.run("And on clay?", parent=rs1.id, budget=Budget(turns=10, dollars=1.0))
finally:
    ksrc.cleanup()
_p = _src_seen["prompts"]
check("a search written inside a fence runs as the search: two searches and a cell, no failed turn",
      [t.kind for t in rs1.turns] == ["search", "search", "cell", "report", "rewrite"] and not any(t.error for t in rs1.turns) and rs1.turns[1].text == "plot as the unit", [(t.kind, t.error) for t in rs1.turns])
check("the turn after a search: its digest whole, and under it how a source is cited; nothing else of it in view yet",
      ("SEARCH (yield by soil type):\n" + _d1 + SOURCES_CITED + "\n(searches left in this run: 3)") in _p[1] and src.IN_VIEW_HEAD not in _p[1] and "cited by its number, as [3]" in SOURCES_CITED, _p[1][-600:])
check("... the turn after the next search: the first search's sourced claims stay in view with their sources' numbers - a digest was in view for one turn, and a run searched twice for the same thing -, "
      "the newest search whole under them and not twice",
      (src.in_view([(1, "yield by soil type", _d1)]) + "\n\nSEARCH (plot as the unit):\n" + _d2) in _p[2] and "search 2 (plot as the unit)" not in _p[2] and _p[2].count("The plot is the unit over 12 seasons. [2]") == 1, _p[2][-900:])
check("... and to the report: the claims of both searches and their sources, once each, with no digest whole - the figures without a source and the summary are a SHOW SEARCH away",
      src.in_view([(1, "yield by soil type", _d1), (2, "plot as the unit", _d2)]) in _p[3] and "In its own words." not in _p[3] and "WITHOUT A SOURCE" not in _p[3]
      and _p[3].index(src.IN_VIEW_HEAD) > _p[3].index("CELLS SO FAR:"), _p[3][-900:])
_listed1 = "\n\n## Sources\n\n- [1] [Designing crop field trials](" + _FAO + ")\n- [3] [A guide \\[to\\] plot\\_trials](https://www.example.org/guide_%28plots%29)"
_check1 = "\n\n> CHECK: 1 number(s) in this report were not printed by any cell or given with a source by a search (77.7). Treat them as unverified."
check("the report ends with the pages it cites, each a link, before the engine's own lines: the two it cites by number - not the one it does not, nor the index in its code",
      rs1.report.startswith("# Regime B yields more on loam\n") and (_listed1 + _check1) in rs1.report and "[2] [Repeated" not in rs1.report and rs1.report.count("## Sources") == 1, rs1.report[-500:])
check("the number check takes a claim a search tied to a source as the source's word - 3.2 and 41.5 pass, as 12, which a cell printed -; a figure the search gave no source for is flagged, "
      "and the line says what it looked in; without a search its words are as they were",
      "3.2" not in rs1.report.split("> CHECK")[1].split("\n")[0] and "41.5" not in rs1.report.split("> CHECK")[1].split("\n")[0] and "(77.7)" in rs1.report
      and report.guard_technical("Sand held 77.7 t/ha.", ["x"]) == "CHECK: 1 number(s) in this report were not printed by any cell (77.7). Treat them as unverified."
      and report.guard_technical("Sand held 77.7 t/ha.", ["x"], searched=True) == _check1[4:], rs1.report[-300:])
check("the plain-language version is asked to keep a source's number, and ends with the pages it cites itself: one here",
      "Where the report cites a web source by its number alone, as [3], keep that citation" in _src_seen["rewrites"][0] and "## Sources" not in _src_seen["rewrites"][0]
      and rs1.rewrite.endswith("tonnes per hectare [1].\n\n## Sources\n\n- [1] [Designing crop field trials](" + _FAO + ")"), rs1.rewrite[-300:])
check("a later chain of the thread: its search is the path's third - in view under that number, the one SHOW SEARCH takes -, the claims in view are its own, and its report cites a page of the "
      "first chain's search by the number it has along the path: the list under the report names both",
      [t.text for t in nbsrc.searches(rs2.id)] == ["yield by soil type", "plot as the unit", "yield on clay"] and "SHOW SEARCH k re-opens one): [1] yield by soil type; [2] plot as the unit" in _p[4]
      and ("SEARCH (yield on clay):\n" + _d3) in _p[5] and src.IN_VIEW_HEAD not in _p[5] and src.in_view([(3, "yield on clay", _d3)]) in _p[6] and "search 1 (" not in _p[6]
      and rs2.report.endswith("\n\n## Sources\n\n- [1] [Designing crop field trials](" + _FAO + ")\n- [4] [Clay soils \\| yields](https://soils.example.org/clay)") and "> CHECK" not in rs2.report, rs2.report[-400:])

print(f"\n{len(passed)} passed, {len(failed)} failed")
sys.exit(1 if failed else 0)
