"""Web sources (0337). A search's digest - the text a SEARCH returns; the host writes it (bambooai/web_search.py) -
lists the claims its search tied to a source under CLAIMS_HEAD, a line each that ends with its sources' numbers, and
those sources under SOURCES_HEAD, a line each: `[3] the page's title - its address`. From those two lists, three
things a run needs: a page has one number along a path, whichever search finds it; the sourced claims of a run's
searches stay in view to its report; and a report ends with the pages it cites, each a link - in one list, made here.

(2026-11-23, the second live search: each digest numbered its sources from 1, so [3] in a report was three pages; a
digest was in view for one turn, so a run searched for the same thing twice and wrote its report without its first
search; and a reader had no way from a citation to its page. The third, 0338: the analyst ended its report with a
list of the sources of its own - 'the pages cited are listed under the report' read as its task -, the list made
here came under it, and the plain-language version copied the one and was given the other.)"""
import re

CLAIMS_HEAD = "SOURCED CLAIMS (each sentence with the sources behind it):"
SOURCES_HEAD = "SOURCES:"
IN_VIEW_HEAD = "CLAIMS THIS RUN'S SEARCHES RETURNED (each with its sources' numbers; SHOW SEARCH k re-opens a search whole):"
CITING = "In the report cite a source by the number it has here, as [3], and write no list of sources: one is added under the report from its citations, each page a link."
REPORT_HEAD = "## Sources"
_PAGE = re.compile(r"^\[(\d+)\] (.*) - (https?://\S+)$")
_CODE = re.compile(r"```.*?```|`[^`\n]*`", re.S)
_CITED = re.compile(r"(?<![\w\]\[])((?:\[\d+\])+)(?![(\[\w])")      # [3] and [3][5]: not x[3], [cell 3], [text][3], [[3]] or [3](...)
_ADDRESS = re.compile(r"https?://(?:[^\s<>()\[\]\"*`]|\([^\s()]*\))+")      # an address in a text; it may hold a pair of brackets
_HEADING = re.compile(r"#{1,6} ")
# the heading a writer gives a list of sources of its own: '## Sources', '**References:**', 'Sources cited:', '### 7. Sources and links'
_OWN_HEAD = re.compile(r"(?:#{1,6} *|\*\*)?(?:\d+[.)] *)?(?:web )?(?:sources?|references?|bibliography|citations?|works cited)(?: \w+){0,2}:?(?:\*\*)?:?", re.I)
_OWN_LINE = re.compile(r"(?:[-*+] +)?\**(?:\[(\d+)\]|(\d+)[.)])?")      # the number a line of such a list opens with, if any: in brackets - '[3] ...', '- **[3]** ...' -, or plain - '3. ...'


def _words(title):
    """A page's title as words in markdown, none of it read as markup."""
    return re.sub(r"([\\`*_\[\]<>|])", r"\\\1", " ".join((title or "").split()))


def _href(address):
    """A page's address as a markdown link's: a bracket would end the link, a space cut it."""
    return address.replace("(", "%28").replace(")", "%29").replace(" ", "%20")


def same(address):
    """A page's address as two spellings of it compare: without scheme, 'www.', fragment or closing slash, the host
    in lower case, a bracket as a link writes it."""
    a = re.sub(r"^https?://(www\.)?", "", (address or "").strip().rstrip(".,;:"), flags=re.I).split("#", 1)[0].rstrip("/")
    host, slash, rest = a.partition("/")
    return _href(host.lower() + slash + rest)


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


def own_list(text, known):
    """`text` without the list of sources its writer made, and the pages that list named: a report has one list of its
    web sources, `listing`'s. The writer's goes when it is a list of pages of `known`, numbered as they are, and nothing
    else - the last part headed Sources or References, each line of it a page: by its address, any number the line
    gives it the page's own, or with no address by the number in brackets the line opens with. Anything else stays
    as written - `text` as it is, and no pages -: a note among the lines, a page of no search, and a list in numbers
    of its writer's own, by which its text then cites."""
    lines = (text or "").split("\n")
    heads = [i for i, line in enumerate(lines) if _OWN_HEAD.fullmatch(line.strip())]
    if not heads:
        return text, []
    start = heads[-1]
    end = next((i for i in range(start + 1, len(lines)) if _HEADING.match(lines[i])), len(lines))
    by_address, by_number = {same(p["link"]): p for p in known}, {p["n"]: p for p in known}
    named = []
    for line in filter(None, (line.strip() for line in lines[start + 1:end])):
        given, (bracket, plain) = _ADDRESS.findall(line), _OWN_LINE.match(line).groups()
        marked = re.findall(r"\[(\d+)\]", line) + ([plain] if plain else [])      # the numbers the line gives its page
        found = [by_address.get(same(a)) for a in given] if given else [by_number.get(int(bracket)) if bracket else None]
        if None in found or (given and any(int(n) not in [p["n"] for p in found] for n in marked)):
            return text, []
        named += found
    if not named:
        return text, []
    rest = "\n".join(lines[end:]).strip("\n")
    return "\n".join(lines[:start]).rstrip() + ("\n\n" + rest if rest else ""), named


def listing(text, known, also=()):
    """The part a report that cites web sources ends with: REPORT_HEAD and a line for each page it cites - its number,
    its title as a link to it, and its site (the page makes the citations in the text links from this list) -, and
    for each page of `also`, those a list of its writer's own named. '' when there is none."""
    found = {p["n"]: p for p in [*cited(text, known), *also]}
    if not found:
        return ""
    return "\n\n" + REPORT_HEAD + "\n\n" + "\n".join(f"- [{n}] [{_words(p['title'])}]({_href(p['link'])}) ({site(p['link'])})" for n, p in sorted(found.items()))
