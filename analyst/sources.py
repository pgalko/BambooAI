"""Web sources (0337, 0340). A search's digest - the text a SEARCH returns; the host writes it (bambooai/web_search.py) -
lists the claims its search tied to a source under CLAIMS_HEAD, a line each that ends with its sources' numbers, and
those sources under SOURCES_HEAD, a line each: `[3] the page's title - its address`. From those two lists what a run
needs: a page has one number along a path, whichever search finds it; the sourced claims of a run's searches stay in
view to its report; and the pages a report cites, by those numbers, as data - the search's card in the pane and the
list under the report in the Answer tab are drawn from it. The report's text holds no list of them.

(2026-11-23, the second live search: each digest numbered its sources from 1, so [3] in a report was three pages; a
digest was in view for one turn, so a run searched for the same thing twice; and a reader had no way from a citation
to its page. 2026-11-24, 0340: the list under a report had been written into its text as markdown - a title's
brackets escaped with backslashes, which the page's maths then read as a formula - and the page read the list back out
of the rendered answer to make its chips.)"""
import re

CLAIMS_HEAD = "SOURCED CLAIMS (each sentence with the sources behind it):"
SOURCES_HEAD = "SOURCES:"
IN_VIEW_HEAD = "CLAIMS THIS RUN'S SEARCHES RETURNED (each with its sources' numbers; SHOW SEARCH k re-opens a search whole):"
CITING = "In the report cite a source by the number it has here, as [3], and write no list of sources: one is added under the report from its citations, each page a link."
_PAGE = re.compile(r"^\[(\d+)\] (.*) - (https?://\S+)$")
_CODE = re.compile(r"```.*?```|`[^`\n]*`", re.S)
_CITED = re.compile(r"(?<![\w\]\[])((?:\[\d+\])+)(?![(\[\w])")      # [3] and [3][5]: not x[3], [cell 3], [text][3], [[3]] or [3](...)
_MARKS = re.compile(r"\s*((?:\[\d+\])+)$")                           # the sources' numbers a claim ends with: ' [1][4]'
_HEADING = re.compile(r"#{1,6} ")
_LIST_HEAD = re.compile(r"(?:#{1,6} *|\*\*)?(?:sources|references):?(?:\*\*)?:?", re.I)    # '## Sources', '**References:**', 'Sources:'


def same(address):
    """A page's address as two spellings of it compare: without scheme, 'www.', fragment or closing slash, the host
    in lower case."""
    a = re.sub(r"^https?://(www\.)?", "", (address or "").strip().rstrip(".,;:"), flags=re.I).split("#", 1)[0].rstrip("/")
    host, slash, rest = a.partition("/")
    return host.lower() + slash + rest


def site(address):
    """The site a page is on, as a reader knows it: its address's host, without 'www.'."""
    return same(address).split("/")[0]


def listed(text, head):
    """The lines a digest has under one of its headings, without their list marks."""
    lines = (text or "").split("\n")
    if head not in lines:
        return []
    out = []
    for line in lines[lines.index(head) + 1:]:
        if not line.strip():
            break
        out.append(re.sub(r"^- ", "", line.strip()))
    return out


def pages(digest):
    """The sources a digest lists, as it numbers them: [{"n": 3, "title": ..., "link": ...}]."""
    found = (_PAGE.match(line) for line in listed(digest, SOURCES_HEAD))
    return [{"n": int(m.group(1)), "title": m.group(2), "link": m.group(3)} for m in found if m]


def along(digests):
    """The pages the searches of a path have numbered, in the order of their numbers: each page once, under the number
    it first got. (A path searched before 0337 numbered from 1 in every digest: there the first page under a number
    keeps it.)"""
    known, taken = {}, set()
    for digest in digests:
        for page in pages(digest):
            if same(page["link"]) not in known and page["n"] not in taken:
                known[same(page["link"])] = page
                taken.add(page["n"])
    return sorted(known.values(), key=lambda p: p["n"])


def numbers(found, known=()):
    """The number each page of `found` has along a path whose searches numbered `known`: a page found before keeps its
    number, a new one takes the next. {the page's address as given: its number}."""
    by = {same(p["link"]): p["n"] for p in known}
    last, out = max(by.values(), default=0), {}
    for page in found:
        key = same(page.get("link"))
        if key not in by:
            last += 1
            by[key] = last
        out[page.get("link")] = by[key]
    return out


def claims(digest):
    """The claims a digest ties to a source, as one text: what the report's number check takes as a source's word."""
    return "\n".join(listed(digest, CLAIMS_HEAD))


def findings(digest):
    """The claims a digest ties to a source, each with its sources' numbers: [{"text": ..., "refs": [1, 4]}]."""
    out = []
    for line in listed(digest, CLAIMS_HEAD):
        m = _MARKS.search(line)
        out.append({"text": line[:m.start()] if m else line, "refs": [int(n) for n in re.findall(r"\d+", m.group(1))] if m else []})
    return out


def view(page):
    """A page as the app shows it: its number, its title, its address - a quote or an angle bracket that rode along at
    its end is not part of it - and its site."""
    url = page["link"].strip("'\"<>")
    return {"n": page["n"], "title": page["title"], "url": url, "host": site(url)}


def card(digest):
    """What a search's card in the pane shows (0339): its pages by the numbers the report cites them by, and the claims
    tied to them."""
    return {"sources": [view(p) for p in pages(digest)], "claims": findings(digest)}


def in_view(searches):
    """What stays in view of a run's searches to its report: the sourced claims of each - `searches` gives each as (its
    number along the path, its query, its digest) - and under them the sources those claims cite, once each, by
    number, with the site each is on, and how the report cites one. '' where no search returned a sourced claim."""
    blocks, cited_here = [], {}
    for k, query, digest in searches:
        lines = listed(digest, CLAIMS_HEAD)
        if not lines:
            continue
        blocks.append(f"search {k} ({query}):\n" + "\n".join("- " + line for line in lines))
        for page in pages(digest):
            cited_here.setdefault(page["n"], page)
    if not blocks:
        return ""
    sources = "\n".join(f"[{n}] {p['title']} ({site(p['link'])})" for n, p in sorted(cited_here.items()))
    return IN_VIEW_HEAD + "\n" + "\n".join(blocks) + (f"\n{SOURCES_HEAD}\n{sources}" if sources else "") + f"\n({CITING})"


def cited(text, known):
    """The pages of `known` a report cites, by number: a number alone in brackets - [3], or [3][5] for two - outside code."""
    by = {p["n"]: p for p in known}
    found = {int(n) for marks in _CITED.findall(_CODE.sub(" ", text or "")) for n in re.findall(r"\d+", marks)}
    return [by[n] for n in sorted(found) if n in by]


def of_report(text, digests):
    """The sources under a report (0340): of the pages the searches of its path numbered - their digests, `digests` -
    those its text cites, by number, as the page draws them."""
    return [view(p) for p in cited(text, along(digests))]


def drop_list(text):
    """`text` without a list of sources its writer made all the same - a section headed Sources or References, to the
    next heading -: the page draws the report's sources itself, from its searches."""
    lines = (text or "").split("\n")
    if not any(_LIST_HEAD.fullmatch(line.strip()) for line in lines):
        return text
    kept, dropping = [], False
    for line in lines:
        if _LIST_HEAD.fullmatch(line.strip()):
            dropping = True
        elif dropping and _HEADING.match(line):
            dropping = False
        if not dropping:
            kept.append(line)
    return "\n".join(kept).rstrip()
