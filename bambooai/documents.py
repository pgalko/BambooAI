"""Documents attached to a thread (docs/DOCUMENTS_DESIGN.md).

A person attaches up to four documents - PDF, Word, Markdown, text - to a thread. Each is parsed once,
at upload, into *units*: paragraph-sized blocks with a locator (a page for a PDF, the heading trail for
the others), a kind (heading, paragraph, list, table, caption) and an id `D2.17` (document 2, unit 17).
Everything is kept as files under the thread's documents folder, the same layout in both editions:

    storage/<user>/documents/<thread_id>/manifest.json
    storage/<user>/documents/<thread_id>/D1/original.pdf      the file as uploaded
                                            /text.json         the units
                                            /text.md           the units joined, each under its locator marker
                                            /map.md            what the analyst reads in every prompt
                                            /tables/1.csv      each table's rows

The kernel gets text.json, text.md and the tables (not the original) under
`datasets/<user>/documents/D1/`, synced to the manifest at every chain start. Nothing here talks
to a model or to the page; phase B's READ action works over the same units.

Parsers: pdfplumber (MIT) for PDF, python-docx (MIT) for Word; Markdown and text by headings and blank
lines. Not PyMuPDF (AGPL). A PDF without a text layer is refused, not OCR'd (out of scope).
"""
from __future__ import annotations

import csv
import hashlib
import json
import logging
import os
import re
import shutil
import statistics
import time
from typing import Dict, Iterable, List, Optional, Tuple

logger = logging.getLogger(__name__)

MAX_DOCS = 4
MAX_FILE_BYTES = 10 * 1024 * 1024
MAX_TEXT_BYTES = 2 * 1024 * 1024
MAX_UNIT_CHARS = 1500       # a paragraph longer than this is split at sentence ends into units of at most this size
                            # (2026-10-03: the Reader is shown a unit whole, and OCR paragraphs ran to 2,500 characters)
PDF_X_TOLERANCE = 1.5       # points between two glyphs that mean a word break. pdfplumber's default of 3 glues the words
                            # of LaTeX papers, whose inter-word gap at 10pt is about 2.5pt and has no space glyph (seen
                            # 2026-10-03 on an arXiv PDF: "ofanewobservationD"); within a word, kerning stays under 1.5
TYPES = {".pdf": "PDF", ".docx": "Word", ".md": "Markdown", ".txt": "text"}
KERNEL_FILES = ("text.json", "text.md")          # plus tables/*.csv; the original stays on the app box
MAP_HEADINGS = 20
MAP_CAPTIONS = 10
MIN_CHARS_PER_PAGE = 20                         # below this average a PDF has no usable text layer

_CAPTION_RE = re.compile(r"^(Table|Fig\.?|Figure)\s*(\d+)[.:\s]", re.I)
_TABLE_CAPTION_RE = re.compile(r"^Table\s*(\d+)[.:\s]", re.I)
_MD_HEADING_RE = re.compile(r"^(#{1,6})\s+(.*?)\s*#*\s*$")
_MD_LIST_RE = re.compile(r"^\s*(?:[-*+]|\d+[.)])\s+")
_MD_TABLE_SEP_RE = re.compile(r"^\s*\|?\s*:?-{3,}:?\s*(\|\s*:?-{3,}:?\s*)*\|?\s*$")
_WORD_RE = re.compile(r"\w+")


class Refused(Exception):
    """An upload the person has to act on; the message is shown as written."""


# ----------------------------------------------------------------------------- sizes and types

def _mb(n: int) -> str:
    return f"{n / (1024 * 1024):.1f} MB"


def check_upload(filename: str, size: int, attached: int) -> str:
    """The checks that need no parsing: type, size, count. Returns the extension."""
    ext = os.path.splitext(filename or "")[1].lower()
    if attached >= MAX_DOCS:
        raise Refused(f"Maximum {MAX_DOCS} documents per thread.")
    if ext not in TYPES:
        raise Refused(f"{filename} is not a PDF, Word, Markdown or text file.")
    if size > MAX_FILE_BYTES:
        raise Refused(f"{filename} is {_mb(size)}; the limit is {MAX_FILE_BYTES // (1024 * 1024)} MB a document.")
    return ext


# ----------------------------------------------------------------------------- units

def _unit(kind: str, text: str, page: Optional[int] = None, section: str = "", **extra) -> dict:
    u = {"kind": kind, "text": text.strip(), "page": page, "section": section}
    u.update(extra)
    return u


def _words(text: str) -> int:
    return len(_WORD_RE.findall(text or ""))


class _Trail:
    """The heading trail for Word, Markdown and text: the nearest heading at each level."""

    def __init__(self):
        self.levels: List[Tuple[int, str]] = []

    def push(self, level: int, text: str) -> None:
        self.levels = [(l, t) for (l, t) in self.levels if l < level] + [(level, text)]

    def section(self) -> str:
        return " > ".join(t for _, t in self.levels)


# ----------------------------------------------------------------------------- PDF

def _join_lines(lines: List[str]) -> str:
    out = ""
    for ln in lines:
        ln = ln.strip()
        if not ln:
            continue
        if out.endswith("-") and ln[:1].islower():          # a word broken at the line end
            out = out[:-1] + ln
        else:
            out = (out + " " + ln) if out else ln
    return out


def _parse_pdf(path: str) -> dict:
    import pdfplumber                                     # imported here: the web box pays for it once

    units: List[dict] = []
    pages = 0
    chars_total = 0
    table_no = 0
    with pdfplumber.open(path) as pdf:
        pages = len(pdf.pages)
        for pno, page in enumerate(pdf.pages, 1):
            tables = []
            try:
                found = page.find_tables()
            except Exception:                                   # noqa: BLE001 - a page the finder cannot read
                found = []
            boxes = []
            for t in found:
                try:
                    rows = t.extract()
                except Exception:                               # noqa: BLE001
                    rows = None
                rows = [[(c or "").strip() for c in r] for r in (rows or []) if r and any((c or "").strip() for c in r)]
                if len(rows) >= 2 and max(len(r) for r in rows) >= 2:
                    tables.append((t.bbox, rows))
                    boxes.append(t.bbox)

            def outside(obj, _boxes=boxes):
                x0, top = obj.get("x0", 0), obj.get("top", 0)
                return not any(b[0] - 1 <= x0 <= b[2] + 1 and b[1] - 1 <= top <= b[3] + 1 for b in _boxes)

            body = page.filter(outside) if boxes else page
            try:
                lines = body.extract_text_lines(strip=True, return_chars=True, x_tolerance=PDF_X_TOLERANCE)
            except Exception:                                   # noqa: BLE001
                lines = []
            sizes = [round(c.get("size", 0) or 0, 1) for ln in lines for c in ln.get("chars", [])]
            chars_total += sum(len(ln.get("text", "")) for ln in lines)
            body_size = statistics.median(sizes) if sizes else 0

            # paragraphs: consecutive lines; a vertical gap over 1.6 line heights, or a size change, starts a new one
            page_units: List[Tuple[float, dict]] = []
            para: List[str] = []
            para_top = None
            para_size = None
            prev_bottom = None
            prev_h = None

            def flush():
                nonlocal para, para_top, para_size
                text = _join_lines(para)
                para = []
                if not text:
                    return
                if para_size and body_size and para_size >= body_size * 1.15 and len(text) <= 120 and not text.endswith("."):
                    kind = "heading"
                elif _CAPTION_RE.match(text):
                    kind = "caption"
                else:
                    kind = "paragraph"
                page_units.append((para_top or 0, _unit(kind, text, page=pno)))

            for ln in lines:
                text = ln.get("text", "")
                if not text.strip():
                    continue
                ch = ln.get("chars", [])
                size = round(statistics.median([c.get("size", 0) or 0 for c in ch]), 1) if ch else body_size
                top, bottom = ln.get("top", 0), ln.get("bottom", 0)
                h = max(bottom - top, 1)
                gap = (top - prev_bottom) if prev_bottom is not None else 0
                # a new block: a gap over 1.6 line heights, a size change, or a line that begins a caption
                new_block = (para and (gap > 1.6 * (prev_h or h) or (para_size and abs(size - para_size) > 0.6)
                                       or bool(_CAPTION_RE.match(text.strip()))))
                if new_block:
                    flush()
                if not para:
                    para_top, para_size = top, size
                para.append(text)
                prev_bottom, prev_h = bottom, h
            flush()

            for bbox, rows in tables:
                table_no += 1
                page_units.append((bbox[1], _unit("table", _table_title(rows), page=pno, table_no=table_no, rows=rows)))
            page_units.sort(key=lambda p: p[0])
            units.extend(u for _, u in page_units)

    if pages and chars_total < MIN_CHARS_PER_PAGE * pages:
        raise Refused("this PDF has no text layer; a scanned document needs OCR, which is not supported.")
    _attach_table_captions(units)
    return {"type": "PDF", "pages": pages, "units": units}


def _table_title(rows: List[List[str]]) -> str:
    head = [c for c in rows[0] if c] if rows else []
    return "Table: " + ", ".join(head)[:120] if head else "Table"


def _attach_table_captions(units: List[dict]) -> None:
    """A caption "Table n ..." next to a table unit on the same page names it; the caption stays a unit."""
    for i, u in enumerate(units):
        if u["kind"] != "table":
            continue
        for j in (i - 1, i + 1):
            if 0 <= j < len(units) and units[j]["kind"] == "caption" and _TABLE_CAPTION_RE.match(units[j]["text"]) \
                    and units[j].get("page") == u.get("page"):
                u["caption"] = units[j]["text"]
                break


# ----------------------------------------------------------------------------- Word

def _parse_docx(path: str) -> dict:
    import docx                                           # python-docx
    from docx.table import Table
    from docx.text.paragraph import Paragraph

    document = docx.Document(path)
    units: List[dict] = []
    trail = _Trail()
    table_no = 0
    pending_list: List[str] = []
    body = document.element.body

    def flush_list():
        nonlocal pending_list
        if pending_list:
            units.append(_unit("list", "\n".join(pending_list), section=trail.section()))
            pending_list = []

    for child in body.iterchildren():
        tag = child.tag.rsplit("}", 1)[-1]
        if tag == "p":
            p = Paragraph(child, document)
            text = (p.text or "").strip()
            if not text:
                continue
            style = (p.style.name if p.style is not None else "") or ""
            m = re.match(r"(?i)^heading\s*(\d)", style)
            if style.lower() == "title":
                flush_list(); trail.push(0, text)
                units.append(_unit("heading", text, section=trail.section(), level=0))
            elif m:
                flush_list(); level = int(m.group(1)); trail.push(level, text)
                units.append(_unit("heading", text, section=trail.section(), level=level))
            elif style.lower().startswith("caption"):
                flush_list(); units.append(_unit("caption", text, section=trail.section()))
            elif style.lower().startswith("list") or child.find(".//{http://schemas.openxmlformats.org/wordprocessingml/2006/main}numPr") is not None:
                pending_list.append("- " + text)
            else:
                flush_list()
                units.append(_unit("caption" if _CAPTION_RE.match(text) else "paragraph", text, section=trail.section()))
        elif tag == "tbl":
            flush_list()
            t = Table(child, document)
            rows = []
            for r in t.rows:
                cells = [(c.text or "").strip().replace("\n", " ") for c in r.cells]
                if any(cells):
                    rows.append(cells)
            if len(rows) >= 1:
                table_no += 1
                units.append(_unit("table", _table_title(rows), section=trail.section(), table_no=table_no, rows=rows))
    flush_list()
    _attach_table_captions(units)
    return {"type": "Word", "pages": None, "units": units}


# ----------------------------------------------------------------------------- Markdown and text

def _parse_markdown(text: str, headings: bool = True) -> dict:
    units: List[dict] = []
    trail = _Trail()
    table_no = 0
    lines = text.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    i, n = 0, len(lines)
    para: List[str] = []

    def flush_para():
        nonlocal para
        if para:
            t = " ".join(s.strip() for s in para if s.strip())
            if t:
                units.append(_unit("caption" if _CAPTION_RE.match(t) else "paragraph", t, section=trail.section()))
            para = []

    while i < n:
        ln = lines[i]
        if ln.strip().startswith("```"):                                    # a fenced block is one unit, kept verbatim
            flush_para()
            j = i + 1
            while j < n and not lines[j].strip().startswith("```"):
                j += 1
            block = "\n".join(lines[i + 1:j]).strip("\n")
            if block.strip():
                units.append(_unit("paragraph", block, section=trail.section(), fenced=True))
            i = j + 1
            continue
        m = _MD_HEADING_RE.match(ln) if headings else None
        if m:
            flush_para()
            level, title = len(m.group(1)), m.group(2).strip()
            trail.push(level, title)
            units.append(_unit("heading", title, section=trail.section(), level=level))
            i += 1
            continue
        if ln.lstrip().startswith("|") and i + 1 < n and _MD_TABLE_SEP_RE.match(lines[i + 1]):
            flush_para()
            rows = []
            j = i
            while j < n and lines[j].lstrip().startswith("|"):
                if not _MD_TABLE_SEP_RE.match(lines[j]):
                    cells = [c.strip() for c in lines[j].strip().strip("|").split("|")]
                    rows.append(cells)
                j += 1
            if rows:
                table_no += 1
                units.append(_unit("table", _table_title(rows), section=trail.section(), table_no=table_no, rows=rows))
            i = j
            continue
        if _MD_LIST_RE.match(ln):
            flush_para()
            items = []
            j = i
            while j < n and (_MD_LIST_RE.match(lines[j]) or (lines[j].startswith("  ") and lines[j].strip())):
                items.append(lines[j].strip())
                j += 1
            units.append(_unit("list", "\n".join(items), section=trail.section()))
            i = j
            continue
        if not ln.strip():
            flush_para()
        else:
            para.append(ln)
        i += 1
    flush_para()
    _attach_table_captions(units)
    return {"type": "Markdown" if headings else "text", "pages": None, "units": units}


# ----------------------------------------------------------------------------- parse, map, text.md

_SENTENCE_END_RE = re.compile(r"(?<=[.!?])\s+(?=[A-Z0-9\"\u201c(\[])")


def split_long(u: dict, max_chars: int = MAX_UNIT_CHARS) -> List[dict]:
    """A paragraph or caption longer than max_chars becomes several units of at most max_chars, split at
    sentence ends (a run of sentences that would overflow starts a new unit; a single sentence longer than
    the cap is split at the last space before it). Headings, tables and fenced blocks are never split."""
    text = u.get("text") or ""
    if u.get("kind") not in ("paragraph", "caption") or u.get("fenced") or len(text) <= max_chars:
        return [u]
    sentences = _SENTENCE_END_RE.split(text)
    pieces, cur = [], ""
    for s in sentences:
        while len(s) > max_chars:                              # a monster sentence: cut at a space
            if cur:
                pieces.append(cur); cur = ""
            cut = s.rfind(" ", 0, max_chars)
            cut = cut if cut > max_chars // 2 else max_chars
            pieces.append(s[:cut].rstrip()); s = s[cut:].lstrip()
        if cur and len(cur) + 1 + len(s) > max_chars:
            pieces.append(cur); cur = s
        else:
            cur = (cur + " " + s).strip() if cur else s
    if cur:
        pieces.append(cur)
    return [dict(u, text=piece) for piece in pieces if piece.strip()]


def parse(path: str, filename: str) -> dict:
    """Units with locators for one file, or Refused. Returns {"type", "pages", "units", "words",
    "text_bytes"}; the units carry no document id yet (attach() numbers them)."""
    ext = os.path.splitext(filename or path)[1].lower()
    if ext == ".pdf":
        parsed = _parse_pdf(path)
    elif ext == ".docx":
        parsed = _parse_docx(path)
    elif ext in (".md", ".txt"):
        with open(path, "rb") as f:
            raw = f.read()
        text = raw.decode("utf-8", errors="replace").lstrip("\ufeff")
        parsed = _parse_markdown(text, headings=(ext == ".md"))
    else:
        raise Refused(f"{filename} is not a PDF, Word, Markdown or text file.")
    units = [u for u in parsed["units"] if u.get("text") or u.get("rows")]
    units = [piece for u in units for piece in split_long(u)]
    for n, u in enumerate(units, 1):
        u["n"] = n
    text_bytes = sum(len(u["text"].encode("utf-8")) for u in units) + \
        sum(sum(len(c.encode("utf-8")) for r in u.get("rows", []) for c in r) for u in units if u["kind"] == "table")
    if text_bytes > MAX_TEXT_BYTES:
        raise Refused(f"the text of {filename} is {_mb(text_bytes)}; the limit is {MAX_TEXT_BYTES // (1024 * 1024)} MB.")
    if not units:
        raise Refused(f"{filename} has no text that could be read.")
    parsed["units"] = units
    parsed["words"] = sum(_words(u["text"]) for u in units if u["kind"] != "table") + \
        sum(_words(" ".join(" ".join(r) for r in u.get("rows", []))) for u in units if u["kind"] == "table")
    parsed["text_bytes"] = text_bytes
    return parsed


def locator(doc_id: str, u: dict) -> str:
    """The marker that precedes a unit in text.md and names it in a digest: [D1.17 | p.4] or
    [D1.17 | §Methods > Participants], with the kind when it is not a paragraph."""
    place = f"p.{u['page']}" if u.get("page") else (f"§{u['section']}" if u.get("section") else "")
    kind = ""
    if u["kind"] == "table":
        kind = f"table {u.get('table_no')}"
    elif u["kind"] in ("heading", "caption", "list"):
        kind = u["kind"]
    parts = [f"{doc_id}.{u['n']}"] + [p for p in (place, kind) if p]
    return "[" + " | ".join(parts) + "]"


def _md_table(rows: List[List[str]]) -> str:
    width = max(len(r) for r in rows)
    rows = [r + [""] * (width - len(r)) for r in rows]
    esc = lambda c: c.replace("|", "\\|").replace("\n", " ")
    out = ["| " + " | ".join(esc(c) for c in rows[0]) + " |", "|" + "---|" * width]
    out += ["| " + " | ".join(esc(c) for c in r) + " |" for r in rows[1:]]
    return "\n".join(out)


def render_text_md(doc_id: str, filename: str, parsed: dict) -> str:
    lines = [f"# {doc_id} - {filename}", ""]
    for u in parsed["units"]:
        lines.append(locator(doc_id, u))
        if u["kind"] == "table":
            if u.get("caption"):
                lines.append(u["caption"])
            lines.append(_md_table(u["rows"]))
            lines.append(f"(tables/{u['table_no']}.csv)")
        else:
            lines.append(u["text"])
        lines.append("")
    return "\n".join(lines).rstrip("\n") + "\n"


def render_map(doc_id: str, filename: str, parsed: dict) -> str:
    """What the analyst reads about a document in every prompt: a few hundred tokens at most."""
    units = parsed["units"]
    tables = [u for u in units if u["kind"] == "table"]
    figures = [u for u in units if u["kind"] == "caption" and not _TABLE_CAPTION_RE.match(u["text"])]
    headings = [u for u in units if u["kind"] == "heading"]
    size = f"{parsed['pages']} pages, " if parsed.get("pages") else ""
    head = (f"{doc_id} - {filename} ({parsed['type']}, {size}{parsed['words']:,} words, {len(tables)} table"
            f"{'s' if len(tables) != 1 else ''}, {len(figures)} figure caption{'s' if len(figures) != 1 else ''})")
    lines = [head]
    if headings:
        shown = headings[:MAP_HEADINGS]
        items = []
        for h in shown:
            where = f" (p.{h['page']})" if h.get("page") else ""
            items.append(("  " * max(0, (h.get("level") or 1) - 1)) + h["text"][:80] + where)   # level 0 (a title) and 1 flush left
        more = f"; ... {len(headings) - len(shown)} more" if len(headings) > len(shown) else ""
        lines.append("Outline: " + "; ".join(items) + more)
    if tables:
        items = []
        for t in tables:
            where = f"p.{t['page']}, " if t.get("page") else ""
            cap = f' "{t["caption"][:60]}"' if t.get("caption") else ""
            items.append(f"table {t['table_no']}{cap} {len(t['rows'])}x{max(len(r) for r in t['rows'])} ({where}{doc_id}.{t['n']})")
        lines.append("Tables: " + "; ".join(items))
    if figures:
        shown = figures[:MAP_CAPTIONS]
        items = [f"{f['text'][:70]}" + (f" (p.{f['page']})" if f.get("page") else "") for f in shown]
        more = f"; ... {len(figures) - len(shown)} more" if len(figures) > len(shown) else ""
        lines.append("Figures: " + "; ".join(items) + more)
    return "\n".join(lines) + "\n"


# ----------------------------------------------------------------------------- the thread folder

def sha256_of(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def load_manifest(tdir: str) -> dict:
    p = os.path.join(tdir, "manifest.json")
    if os.path.exists(p):
        with open(p, encoding="utf-8") as f:
            return json.load(f)
    return {"next": 1, "documents": []}


def save_manifest(tdir: str, manifest: dict) -> None:
    os.makedirs(tdir, exist_ok=True)
    tmp = os.path.join(tdir, "manifest.json.tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=1)
    os.replace(tmp, os.path.join(tdir, "manifest.json"))


def attach(tdir: str, src_path: str, filename: str) -> dict:
    """Parse and store one document in the thread folder; the manifest entry comes back. Ids are given
    in upload order and never reused within a thread. Nothing is written when the file is refused."""
    manifest = load_manifest(tdir)
    size = os.path.getsize(src_path)
    ext = check_upload(filename, size, len(manifest["documents"]))
    parsed = parse(src_path, filename)
    doc_id = f"D{manifest['next']}"
    ddir = os.path.join(tdir, doc_id)
    if os.path.exists(ddir):
        shutil.rmtree(ddir)
    os.makedirs(os.path.join(ddir, "tables"), exist_ok=True)
    shutil.copyfile(src_path, os.path.join(ddir, "original" + ext))
    with open(os.path.join(ddir, "text.json"), "w", encoding="utf-8") as f:
        json.dump({"doc": doc_id, "file": filename, "type": parsed["type"], "pages": parsed["pages"],
                   "units": [dict(u, id=f"{doc_id}.{u['n']}") for u in parsed["units"]]}, f, ensure_ascii=False)
    with open(os.path.join(ddir, "text.md"), "w", encoding="utf-8") as f:
        f.write(render_text_md(doc_id, filename, parsed))
    with open(os.path.join(ddir, "map.md"), "w", encoding="utf-8") as f:
        f.write(render_map(doc_id, filename, parsed))
    for u in parsed["units"]:
        if u["kind"] == "table":
            with open(os.path.join(ddir, "tables", f"{u['table_no']}.csv"), "w", encoding="utf-8", newline="") as f:
                csv.writer(f).writerows(u["rows"])
    tables = sum(1 for u in parsed["units"] if u["kind"] == "table")
    entry = {"id": doc_id, "file": filename, "type": parsed["type"], "pages": parsed["pages"],
             "units": len(parsed["units"]), "words": parsed["words"], "tables": tables,
             "text_bytes": parsed["text_bytes"], "size": size, "sha256": sha256_of(src_path),
             "uploaded_at": time.strftime("%Y-%m-%dT%H:%M:%S")}
    manifest["documents"].append(entry)
    manifest["next"] += 1
    save_manifest(tdir, manifest)
    return entry


def remove(tdir: str, doc_id: str) -> bool:
    manifest = load_manifest(tdir)
    before = len(manifest["documents"])
    manifest["documents"] = [d for d in manifest["documents"] if d["id"] != doc_id]
    ddir = os.path.join(tdir, doc_id)
    if os.path.isdir(ddir) and re.fullmatch(r"D\d+", doc_id):
        shutil.rmtree(ddir)
    save_manifest(tdir, manifest)
    return len(manifest["documents"]) < before


def remove_thread(tdir: str) -> None:
    """The thread is gone: so is its folder (cleanup and delete_thread call this)."""
    if os.path.isdir(tdir):
        shutil.rmtree(tdir, ignore_errors=True)


def read_map(tdir: str, doc_id: str) -> str:
    p = os.path.join(tdir, doc_id, "map.md")
    with open(p, encoding="utf-8") as f:
        return f.read()


def read_units(tdir: str, doc_id: str) -> dict:
    with open(os.path.join(tdir, doc_id, "text.json"), encoding="utf-8") as f:
        return json.load(f)


# ----------------------------------------------------------------------------- ranking text

RANK_CHARS = 2000             # a unit's text as ranked (a table: caption, header, first rows)


def unit_rank_text(u: dict) -> str:
    """A unit's text for ranking: its text, or for a table its caption, header row and first rows."""
    if u.get("kind") == "table":
        rows = u.get("rows") or []
        head = " | ".join(rows[0]) if rows else ""
        body = "; ".join(" | ".join(r) for r in rows[1:6])
        text = " ".join(x for x in (u.get("caption") or "", head, body) if x)
    else:
        text = u.get("text") or ""
    return text[:RANK_CHARS]







# ----------------------------------------------------------------------------- the kernel's copy

def kernel_files(tdir: str, entry: dict) -> List[Tuple[str, str, str]]:
    """(relative path under documents/, absolute source, sha256) for what the kernel gets: text.json,
    text.md and the tables - never the original."""
    ddir = os.path.join(tdir, entry["id"])
    out = []
    for name in KERNEL_FILES:
        p = os.path.join(ddir, name)
        if os.path.exists(p):
            out.append((f"{entry['id']}/{name}", p, sha256_of(p)))
    tdir_tables = os.path.join(ddir, "tables")
    if os.path.isdir(tdir_tables):
        for name in sorted(os.listdir(tdir_tables)):
            p = os.path.join(tdir_tables, name)
            out.append((f"{entry['id']}/tables/{name}", p, sha256_of(p)))
    return out


def sync_plan(wanted: Iterable[Tuple[str, str, str]], present: Dict[str, str]) -> Tuple[List[Tuple[str, str, str]], List[str]]:
    """What to send and what to delete so the kernel's documents folder mirrors the thread: `wanted` as
    kernel_files() gives it, `present` as {relative path: sha256} of what the kernel has."""
    wanted = list(wanted)
    want = {rel: sha for rel, _, sha in wanted}
    send = [(rel, src, sha) for rel, src, sha in wanted if present.get(rel) != sha]
    delete = [rel for rel in present if rel not in want]
    return send, delete


def inventory(root: str) -> Dict[str, str]:
    """{relative path: sha256} of a documents folder (the kernel's, or the thread's copy)."""
    out = {}
    if not os.path.isdir(root):
        return out
    for dirpath, _, files in os.walk(root):
        for name in files:
            p = os.path.join(dirpath, name)
            out[os.path.relpath(p, root).replace(os.sep, "/")] = sha256_of(p)
    return out


def sync_local(tdir: str, kernel_root: str) -> Tuple[int, int]:
    """Mirror the thread's documents into the kernel's folder on the same machine (compute local or
    direct). Returns (files written, files deleted)."""
    manifest = load_manifest(tdir)
    wanted = [f for d in manifest["documents"] for f in kernel_files(tdir, d)]
    send, delete = sync_plan(wanted, inventory(kernel_root))
    for rel, src, _ in send:
        dst = os.path.join(kernel_root, rel)
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        shutil.copyfile(src, dst)
    for rel in delete:
        try:
            os.remove(os.path.join(kernel_root, rel))
        except OSError:
            pass
    for dirpath, _, _ in list(os.walk(kernel_root, topdown=False)):
        if dirpath != kernel_root:
            try:
                if not os.listdir(dirpath):
                    os.rmdir(dirpath)
            except OSError:
                pass
    return len(send), len(delete)


# ----------------------------------------------------------------------------- the prompt

# ----------------------------------------------------------------------------- the kernel's document objects
# in the kernel each document is an object - D1.grep("beauty", context=1), D1.units(35, 41), D1.around("D1.36", 2),
# D1.page(7), D1.outline(), D1.table(2), D1.text - so one cell does what three slicing cells did. The source is sent to
# the kernel by the host at start (uncommitted, like the pd/np prelude), again after a rollback, and prefixed to the
# replay script; it is never a cell of the record. Methods return strings for the analyst to print.
KERNEL_API_SOURCE = r'''
import json as _bamboo_json, os as _bamboo_os, re as _bamboo_re

class _BambooDocument:
    """A document attached to the thread, as an object in the kernel (docs/DOCUMENTS_DESIGN.md)."""
    def __init__(self, doc_id, folder, file):
        self.id, self.folder, self.file = doc_id, folder, file
        self._units = None
    def _load(self):
        if self._units is None:
            with open(_bamboo_os.path.join(self.folder, "text.json"), encoding="utf-8") as f:
                self._units = _bamboo_json.load(f).get("units", [])
        return self._units
    def __repr__(self):
        us = self._load()
        pages = max((u.get("page") or 0) for u in us) if us else 0
        return "%s - %s (%d units%s)" % (self.id, self.file, len(us), ", %d pages" % pages if pages else "")
    def _n(self, ref):
        s = str(ref)
        return int(s.split(".")[-1]) if "." in s else int(s)
    def _fmt(self, u):
        where = (" | p.%s" % u["page"]) if u.get("page") else ((" | %s" % u["section"]) if u.get("section") else "")
        kind = (" | %s" % u["kind"]) if u.get("kind") in ("heading", "caption", "table") else ""
        if u.get("kind") == "table":
            rows = u.get("rows") or []
            body = (u.get("caption") or "") + "\n" + "\n".join(" | ".join(str(c) for c in r) for r in rows[:12])
        else:
            body = u.get("text", "")
        return "[%s%s%s] %s" % (u["id"], where, kind, body)
    @property
    def text(self):
        with open(_bamboo_os.path.join(self.folder, "text.md"), encoding="utf-8") as f:
            return f.read()
    def unit(self, ref):
        n = self._n(ref)
        for u in self._load():
            if self._n(u["id"]) == n:
                return self._fmt(u)
        return "(no unit %s.%d)" % (self.id, n)
    def units(self, a, b=None):
        a, b = self._n(a), (self._n(b) if b is not None else self._n(a))
        out = [self._fmt(u) for u in self._load() if a <= self._n(u["id"]) <= b]
        return "\n\n".join(out) if out else "(no units %s.%d-%d)" % (self.id, a, b)
    def around(self, ref, k=1):
        n = self._n(ref)
        return self.units(max(1, n - k), n + k)
    def page(self, n):
        out = [self._fmt(u) for u in self._load() if u.get("page") == n]
        return "\n\n".join(out) if out else "(no page %s in %s)" % (n, self.id)
    def outline(self):
        out = ["[%s%s] %s" % (u["id"], (" | p.%s" % u["page"]) if u.get("page") else "", u.get("text", "")) for u in self._load() if u.get("kind") == "heading"]
        return "\n".join(out) if out else "(no headings in %s)" % self.id
    def grep(self, pattern, context=0, limit=20, flags=_bamboo_re.I):
        rx = _bamboo_re.compile(pattern, flags)
        us = self._load(); hits = [i for i, u in enumerate(us) if rx.search(u.get("text", "") or " ".join(" ".join(r) for r in (u.get("rows") or [])))]
        out = []
        for i in hits[:limit]:
            lo, hi = max(0, i - context), min(len(us) - 1, i + context)
            out.append("\n".join(self._fmt(us[j]) for j in range(lo, hi + 1)))
        tail = "\n(%d more matches; raise limit or narrow the pattern)" % (len(hits) - limit) if len(hits) > limit else ""
        return ("\n---\n".join(out) if out else "(no match for %r in %s)" % (pattern, self.id)) + tail
    def table(self, n):
        import pandas as _bamboo_pd
        path = _bamboo_os.path.join(self.folder, "tables", "%d.csv" % int(n))
        if not _bamboo_os.path.exists(path):
            raise FileNotFoundError("%s has no table %s (tables: %s)" % (self.id, n, sorted(_bamboo_os.listdir(_bamboo_os.path.join(self.folder, "tables"))) if _bamboo_os.path.isdir(_bamboo_os.path.join(self.folder, "tables")) else "none"))
        return _bamboo_pd.read_csv(path)

docs = {}
__BINDINGS__
'''


def kernel_api_source(tdir: str, kernel_root_rel: str) -> str:
    """The source that defines D1, D2, ... and `docs` in the kernel for this thread's documents; empty when
    there are none. Executed by the host at kernel start and after a rollback, prefixed to the replay script."""
    manifest = load_manifest(tdir)
    entries = manifest.get("documents") or []
    if not entries:
        return ""
    lines = []
    for d in entries:
        folder = f"{kernel_root_rel}/{d['id']}"
        lines.append(f"{d['id']} = _BambooDocument({d['id']!r}, {folder!r}, {d['file']!r}); docs[{d['id']!r}] = {d['id']}")
    return KERNEL_API_SOURCE.replace("__BINDINGS__", "\n".join(lines))


def prompt_block(tdir: str, kernel_root_rel: str, in_kernel: bool = True) -> str:
    """The documents part of the DATA block: each map, then where the text is - in the kernel's working
    directory, or, when this kernel has no copy (an executor image from before documents), only through
    READ. Empty when the thread has no documents."""
    manifest = load_manifest(tdir)
    docs = manifest.get("documents") or []
    if not docs:
        return ""
    first = docs[0]["id"]
    if in_kernel:
        lines = [f"Documents attached to this thread ({len(docs)}). Their text is not in this prompt. In the kernel each is "
                 f"an object: {first}.grep('pattern', context=1), {first}.units(35, 41), {first}.around('{first}.36', 2), "
                 f"{first}.page(7), {first}.outline(), {first}.table(2) (a DataFrame), {first}.text - print what you need in a "
                 f"cell. READ {first} <what you want> finds and quotes passages in {first}, READ ALL <what you want> across every "
                 f"document, READ {first}.35-41 <what you want> reads that stretch whole. Cite a passage by its id, e.g. "
                 f"[{first}.17]. The files are under {kernel_root_rel}/<id>/ "
                 f"(text.md, text.json, tables/<n>.csv) if you ever need them; if they are not there, READ."]
    else:
        lines = [f"Documents attached to this thread ({len(docs)}). Their text is not in this prompt and NOT in this "
                 f"kernel (its executor predates documents): READ is the way to read them - READ {first} <what you are "
                 f"looking for> in {first}, READ ALL <what you want> across every document, READ {first}.35-41 <what you want> "
                 f"for a stretch whole; cite a passage by "
                 f"its id, e.g. [{first}.17]. Do not look for document files with code."]
    for d in docs:
        try:
            lines.append(read_map(tdir, d["id"]).rstrip("\n"))
        except OSError:
            lines.append(f"{d['id']} - {d['file']} (map unavailable)")
    return "\n".join(lines)
