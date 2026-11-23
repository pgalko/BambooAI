"""Web sources (0337): one number for a page along a path, the sourced claims of a run's searches in view to its report,
an action written inside a fence, the number check, the report's and the rewrite's sources - one list under each, the
engine's (0338). The session over a real in-process kernel; the model and the search are scripted.
Run: python3 tests/analyst/test_sources.py"""
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
      "two spellings of an address are one page - with 'www.' or without, a bracket in it as written or as a link writes it -; on a path searched before 0337, each digest numbered from 1, "
      "the first page under a number keeps it; a failed search lists none; a page's site is its address's host",
      src.pages(_d1) == [{"n": 1, "title": "Designing crop field trials", "link": _FAO}, {"n": 2, "title": "Repeated measures in plot trials", "link": _JRN}]
      and [(p["n"], p["link"]) for p in _known] == [(1, _FAO), (2, _JRN), (3, _GDE)]
      and src.numbers([{"link": "https://fao.org/agriculture/crops/field-trials/#design"}, {"link": "https://new.example.org/a"}, {"link": _JRN}], _known)
          == {"https://fao.org/agriculture/crops/field-trials/#design": 1, "https://new.example.org/a": 4, _JRN: 2}
      and src.numbers([{"link": _JRN}, {"link": _FAO}]) == {_JRN: 1, _FAO: 2}
      and src.numbers([{"link": "https://example.org/guide_%28plots%29"}], _known) == {"https://example.org/guide_%28plots%29": 3} and src.site(_FAO) == "fao.org"
      and [(p["n"], p["link"]) for p in src.along([_d1, _digest(["x [1]"], [(1, "Another page", "https://other.example.org/x")])])] == [(1, _FAO), (2, _JRN)]
      and src.pages("(search failed: boom)") == [] and src.along([]) == [] and src.claims(_d1) == "Regime B plots yielded 3.2 t/ha on loam. [1]\nSoil type alone moves yield by 0.5-1.0 t/ha. [1][2]",
      (src.pages(_d1), _known))
# a line of the list under a report, for each page of the path
_L1 = "- [1] [Designing crop field trials](" + _FAO + ") (fao.org)"
_L2 = "- [2] [Repeated measures in plot trials](" + _JRN + ") (onlinelibrary.wiley.com)"
_L3 = "- [3] [A guide \\[to\\] plot\\_trials](https://www.example.org/guide_%28plots%29) (example.org)"
_rep = "Loam gave 3.2 t/ha [3]; the unit is the plot [3][1]. Not these: x[2], [cell 2], `[2]`, [see][2], [[2]](u), [2](u), [2024], [9].\n```\n[2]\n```"
check("sources: a report cites a source by its number alone in brackets - [3], or [3][1] for two; an index, a cell's citation, a number in code or of no source is none; "
      "the report then ends with the pages it cites, by number, each title a link to its page and its site after it - the title's own brackets and marks as words, a bracket in an address written so "
      "that it does not end the link -, and with any page more that is to be listed, each page once; a report with neither gains nothing",
      [p["n"] for p in src.cited(_rep, _known)] == [1, 3]
      and src.listing(_rep, _known) == "\n\n## Sources\n\n" + _L1 + "\n" + _L3
      and src.listing(_rep, _known, [_known[1], _known[0]]) == "\n\n## Sources\n\n" + _L1 + "\n" + _L2 + "\n" + _L3
      and src.listing("Nothing from the web: x[1].", _known, [_known[1]]) == "\n\n## Sources\n\n" + _L2
      and src.listing("Nothing from the web: x[1].", _known) == "" and src.listing(_rep, []) == "", src.listing(_rep, _known))
check("sources: what stays in view of a run's searches - the claims of each under its number on the path and its query, then the sources they cite, once each, by number, with the site; "
      "under them how the report cites one, and that it writes no list of them (0338: 'the pages cited are listed under the report' was read as the analyst's task); "
      "nothing where no search returned a sourced claim",
      src.in_view([(1, "yield by soil type", _d1), (2, "plot as the unit", _d2), (3, "nothing", "(search failed: boom)")]) == src.IN_VIEW_HEAD
      + "\nsearch 1 (yield by soil type):\n- Regime B plots yielded 3.2 t/ha on loam. [1]\n- Soil type alone moves yield by 0.5-1.0 t/ha. [1][2]"
      + "\nsearch 2 (plot as the unit):\n- The plot is the unit over 12 seasons. [2]\n- A guide gives 41.5 plots per regime. [3]"
      + "\nSOURCES:\n[1] Designing crop field trials (fao.org)\n[2] Repeated measures in plot trials (onlinelibrary.wiley.com)\n[3] A guide [to] plot_trials (example.org)"
      + "\n(" + src.CITING + ")"
      and "cite a source by the number it has here, as [3], and write no list of sources: one is added under the report" in src.CITING
      and src.in_view([(1, "q", "(no results)")]) == "" and src.in_view([]) == "",
      src.in_view([(1, "yield by soil type", _d1), (2, "plot as the unit", _d2)]))
_body = "# Regime B yields more on loam\n\nLoam gave 3.2 t/ha [1]."
_p1, _p2, _p3 = _known
_own = lambda part, known=_known: src.own_list(_body + "\n\n" + part, known)
_stays = lambda part, known=_known: _own(part, known) == (_body + "\n\n" + part, [])
check("sources: a report has one list of its web sources, the engine's (0338: the first live report with that list had the analyst's own over it) - a list its writer made of the path's pages is "
      "taken out, and the pages it named come back with the text: the list as that report had it, a number and the page's address to a line; the engine's own lines, under References in bold; "
      "a page by its address alone - in a link with a bracket in it, as code in another spelling, under its plain number in italics with a full stop after it; a number in brackets and no address; "
      "under a heading of a word or two more",
      _own("## Sources\n\n[1] FAO, \"Designing crop field trials\" - " + _FAO + "\n[3] A guide to plot trials - " + _GDE + "\n") == (_body, [_p1, _p3])
      and _own("**References:**\n" + _L1 + "\n" + _L3) == (_body, [_p1, _p3])
      and _own("Sources:\n- [the guide](" + _GDE + ")\n- `https://fao.org/agriculture/crops/field-trials/`\n2. The journal: *" + _JRN + "*.") == (_body, [_p3, _p1, _p2])
      and _own("### 4. Works cited\n- [2] the journal's review\n- **[1]** FAO") == (_body, [_p2, _p1]) and _own("## Sources and links\n- FAO: " + _FAO + " [1]") == (_body, [_p1]),
      (_own("**References:**\n" + _L1 + "\n" + _L3), _own("Sources:\n- [the guide](" + _GDE + ")\n- `https://fao.org/agriculture/crops/field-trials/`\n2. The journal: *" + _JRN + "*.")))
check("... and anything else stays as its writer wrote it: a part with a line that is no page of the path - a note, a number of no source, another address under a page's number, a reference under a "
      "plain number -, a list in numbers of its writer's own - a page under another's number, in brackets, plain or after its address: its text cites by them -, a part under another heading, a heading with nothing "
      "under it, a thread that searched nothing; a list in the middle of a report goes and what follows it stays; of two such headings the last is the list",
      _stays("## Sources\n[1] FAO - " + _FAO + "\nAll pages were read on the day.") and _stays("## Sources\n[1] FAO\n[9] Another page")
      and _stays("## Sources\n[1] A page elsewhere - https://elsewhere.example.org/x") and _stays("## References\n1. A handbook of field trials (1977)\n2. A second handbook (1925)")
      and _stays("## Sources\n[1] The journal - " + _JRN + "\n[2] FAO - " + _FAO) and _stays("## Sources\n1. The journal: " + _JRN + "\n2. FAO: " + _FAO)
      and _stays("## Sources\n- The journal: " + _JRN + " [1]\n- FAO: " + _FAO + " [2]")
      and _stays("## Next steps\n[1] gives the design in full.") and _stays("## Sources") and _stays("## Sources\n[1] FAO", [])
      and _own("## Sources\n[1] FAO\n\n## Next steps\nRead the guide.") == (_body + "\n\n## Next steps\nRead the guide.", [_p1])
      and _own("## Sources\nThe pages agree [1].\n\n## References\n[1] FAO") == (_body + "\n\n## Sources\nThe pages agree [1].", [_p1]),
      (_own("## Sources\n[1] FAO\n\n## Next steps\nRead the guide."), _own("## Sources\nThe pages agree [1].\n\n## References\n[1] FAO")))
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
# the list the analyst ends its report with, as the first live report with sources did (0338): a page more than its text cites, and a year no cell printed
_OWN = "\n\n## Sources\n\n[1] FAO, \"Designing crop field trials\" - " + _FAO + "\n[2] A journal's review of repeated measures (2019) - " + _JRN + "\n[3] A guide to plot trials - " + _GDE
_SRC_SCRIPT = ["###NOTE###\n" + NOTE + "\n###ACTION###\nSEARCH yield by soil type",
               "###NOTE###\n" + NOTE + "\n###ACTION###\n```\nSEARCH plot as the unit\n```",
               "###NOTE###\n" + NOTE + "\n###ACTION###\nCELL\n```python\nprint('plots', 12)\n```",
               "###NOTE###\n" + NOTE + "\n###ACTION###\nREPORT\n# Regime B yields more on loam\n\nRegime B plots yielded 3.2 t/ha on loam [1], over 12 plots [cell 1]. "
               "A guide gives 41.5 plots per regime [3]; sand held 77.7 t/ha. In code `x[2]` is an index." + _OWN,
               "###NOTE###\n" + NOTE + "\n###ACTION###\nSEARCH yield on clay",
               "###NOTE###\n" + NOTE + "\n###ACTION###\nCELL\n```python\nprint('rows', len(df))\n```",
               "###NOTE###\n" + NOTE + "\n###ACTION###\nREPORT\n# Clay holds less\n\nClay held 2.9 t/ha [4], against 3.2 t/ha on loam [1]."]
_src_seen = {"prompts": [], "rewrites": []}
def _src_llm(system, user, **hints):
    if user.startswith("Rewrite"):
        _src_seen["rewrites"].append(user)
        return "# Regime B yields more on loam\n\nOn loam, plots under regime B gave 3.2 tonnes per hectare [1].\n\n**Sources**\n- [1] FAO\n- [2] the journal", {"cost": 0}
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
check("the turn after a search: its digest whole, and under it how a source is cited and that the report writes no list of them; nothing else of it in view yet",
      ("SEARCH (yield by soil type):\n" + _d1 + SOURCES_CITED + "\n(searches left in this run: 3)") in _p[1] and src.IN_VIEW_HEAD not in _p[1] and SOURCES_CITED == "\n(" + src.CITING + ")", _p[1][-600:])
check("... the turn after the next search: the first search's sourced claims stay in view with their sources' numbers - a digest was in view for one turn, and a run searched twice for the same thing -, "
      "the newest search whole under them and not twice",
      (src.in_view([(1, "yield by soil type", _d1)]) + "\n\nSEARCH (plot as the unit):\n" + _d2) in _p[2] and "search 2 (plot as the unit)" not in _p[2] and _p[2].count("The plot is the unit over 12 seasons. [2]") == 1, _p[2][-900:])
check("... and to the report: the claims of both searches and their sources, once each, with no digest whole - the figures without a source and the summary are a SHOW SEARCH away",
      src.in_view([(1, "yield by soil type", _d1), (2, "plot as the unit", _d2)]) in _p[3] and "In its own words." not in _p[3] and "WITHOUT A SOURCE" not in _p[3]
      and _p[3].index(src.IN_VIEW_HEAD) > _p[3].index("CELLS SO FAR:"), _p[3][-900:])
_listed1 = "\n\n## Sources\n\n" + _L1 + "\n" + _L2 + "\n" + _L3
_check1 = "\n\n> CHECK: 1 number(s) in this report were not printed by any cell or given with a source by a search (77.7). Treat them as unverified."
check("the report ends with one list of its sources, the engine's, before the engine's own lines - the analyst ended it with a list of its own (0338): that list is out of the report, the pages it "
      "named are in the engine's - the two the text cites and the one more -, each a link with its site, and the year in it is not held against the report; the turn keeps what the analyst wrote",
      rs1.report.startswith("# Regime B yields more on loam\n") and rs1.report.endswith("`x[2]` is an index." + _listed1 + _check1) and rs1.report.count("Sources") == 1
      and rs1.turns[3].text.endswith(_OWN), rs1.report[-700:])
check("the number check takes a claim a search tied to a source as the source's word - 3.2 and 41.5 pass, as 12, which a cell printed -; a figure the search gave no source for is flagged, "
      "and the line says what it looked in; without a search its words are as they were",
      "3.2" not in rs1.report.split("> CHECK")[1].split("\n")[0] and "41.5" not in rs1.report.split("> CHECK")[1].split("\n")[0] and "(77.7)" in rs1.report
      and report.guard_technical("Sand held 77.7 t/ha.", ["x"]) == "CHECK: 1 number(s) in this report were not printed by any cell (77.7). Treat them as unverified."
      and report.guard_technical("Sand held 77.7 t/ha.", ["x"], searched=True) == _check1[4:], rs1.report[-300:])
check("the plain-language version: the Rewriter is asked to keep a source's number and to write no list, and is shown none - the analyst's is out of the report it reads, the engine's not yet "
      "under it; it ended its text with a list all the same, and the text has one, the engine's: the page it cites and the one more its own list named - not the report's third",
      "as [3], keep that citation after the words it stands for, and write no list of sources: one is added under your text." in _src_seen["rewrites"][0] and "Sources" not in _src_seen["rewrites"][0]
      and rs1.rewrite.endswith("tonnes per hectare [1].\n\n## Sources\n\n" + _L1 + "\n" + _L2) and rs1.rewrite.count("Sources") == 1, rs1.rewrite[-400:])
check("a later chain of the thread: its search is the path's third - in view under that number, the one SHOW SEARCH takes -, the claims in view are its own, and its report cites a page of the "
      "first chain's search by the number it has along the path: the list under the report names both",
      [t.text for t in nbsrc.searches(rs2.id)] == ["yield by soil type", "plot as the unit", "yield on clay"] and "SHOW SEARCH k re-opens one): [1] yield by soil type; [2] plot as the unit" in _p[4]
      and ("SEARCH (yield on clay):\n" + _d3) in _p[5] and src.IN_VIEW_HEAD not in _p[5] and src.in_view([(3, "yield on clay", _d3)]) in _p[6] and "search 1 (" not in _p[6]
      and rs2.report.endswith("[1].\n\n## Sources\n\n" + _L1 + "\n- [4] [Clay soils \\| yields](https://soils.example.org/clay) (soils.example.org)") and "> CHECK" not in rs2.report, rs2.report[-400:])
# a run stopped after its report - here in the figures step - keeps the report as it stands then: without the analyst's own list, with the engine's
_STOP_SCRIPT = ["###NOTE###\n" + NOTE + "\n###ACTION###\nSEARCH yield by soil type", "###NOTE###\n" + NOTE + "\n###ACTION###\nCELL\n```python\nprint('plots', 12)\n```",
                "###NOTE###\n" + NOTE + "\n###ACTION###\nREPORT\n# Regime B yields more on loam\n\nLoam gave 3.2 t/ha [1], over 12 plots [cell 1].\n\n## Sources\n\n[1] FAO - " + _FAO]
_stop_seen = []
def _stop_llm(system, user, **hints):
    if system.startswith("You are drawing the figures"): raise RuntimeError("stopped")
    _stop_seen.append(user)
    return _STOP_SCRIPT[len(_stop_seen) - 1], {"cost": 0.001}
kstop = PersistentKernel(df=df); nbstop = Notebook("tstop")
try:
    Session(kstop, nbstop, _stop_llm, data_description="d", search=_src_search).run("Does regime B yield more?", budget=Budget(turns=10, dollars=1.0))
    _stopped = ""
except RuntimeError as exc:
    _stopped = str(exc)
finally:
    kstop.cleanup()
_rstop = list(nbstop.runs.values())[-1]
check("a run stopped in the figures step, after its report: the report on the record is the analyst's text without its own list of sources and with the engine's - its sources are not lost with the list",
      _stopped == "stopped" and _rstop.report == "# Regime B yields more on loam\n\nLoam gave 3.2 t/ha [1], over 12 plots [cell 1].\n\n## Sources\n\n" + _L1, (_stopped, _rstop.report))

print(f"\n{len(passed)} passed, {len(failed)} failed")
sys.exit(1 if failed else 0)
