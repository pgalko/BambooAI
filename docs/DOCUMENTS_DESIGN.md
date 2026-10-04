# Documents — design (v1.0, 2026-10-03)

What is built, and why. The history of how it got here is in the commit messages of the series and
in `HANDOVER.md`; the first version of this document (v0.1–v0.20, D33–D60) described an economy of
free look-ups, an embedding retrieval stack and a `LOOK` action that were built, measured against
real runs, and removed on 2026-10-03 — a plain run had gone from four exchanges to nineteen, and a
documents run spent eighteen of thirty-three exchanges on free looks. The present design keeps what
those runs showed to work.

## 1. What a document is to the analyst

A person attaches up to four documents to a thread — papers, notes, meeting or interview
transcripts — as PDF, Word, Markdown or plain text, each at most 10 MB. They are not datasets: they
are context the analysis is read in, or the thing a question is about. The documents do not enter
the prompt whole. The analyst sees a short map of each, works on their text with code the way it
works on data, and asks for what it needs with one action, `READ`, whose answer is verbatim passages
with locators. The report cites those passages the way it cites cells, and the page shows the
passage on hover and opens it on click.

## 2. Parsing and storage

- **Parsed once, at upload, into units with locators.** A unit is a paragraph-sized block with an id
  (`D2.17`: document 2, unit 17), a kind (heading, paragraph, list, table, caption), its place (the
  page for a PDF; the heading trail for Word, Markdown and text) and its text; a table unit carries
  its rows and the adjacent caption. A paragraph over 1,500 characters is split at sentence ends.
  *Reason:* a unit id is exact and checkable, as `[cell 7]` is; a page is not.
- **Files, not tables.** `storage/<user>/documents/<thread>/`: `manifest.json`, then per document
  `original.<ext>`, `text.json` (the units), `text.md` (the units with their locator markers, for
  code to grep), `map.md`, `tables/<n>.csv`. Removed with the thread, kept when it is favourited; no
  new table in `local_store.py` or Supabase. *Reason:* the two editions must not diverge; a folder
  is the smaller hosted change.
- **Parsers:** `pdfplumber` (MIT) for PDF, `python-docx` (MIT) for Word, headings and blank lines for
  Markdown and text; both are package dependencies. A PDF with no text layer is refused with a plain
  sentence (OCR is not supported); parsed text above 2 MB is refused with the size stated.
- **Ids** are given in upload order and never reused within a thread.

## 3. In the kernel and in the prompt

- **Each document is an object in the kernel:** `D1.text`, `D1.page(n)`, `D1.units(a, b)`,
  `D1.around(ref, k)`, `D1.grep(pattern, context)`, `D1.table(n)` (a DataFrame), `D1.outline()`. The
  objects' source is a prelude the session runs at the start of every run and again after a rollback;
  it is never a cell of the record. The files are mirrored into the executor by content
  (`/file_utils/documents`, `upload_document`, `remove_document`) at every chain start and before a
  replay, since the container forgets between restarts. *Reason:* the analyst reads documents with
  cells, as it reads data; nothing new to learn, and the provenance of a printed line is a cell.
- **A map of each document rides in `DATA`** — file, type, size, the outline, the tables, where the
  files are — and a short *Documents* section and the `READ` row of the actions table join the contract only when
  the thread has documents (`Session(documents=True)`, `analyst.session.contract()`). Without documents
  the system prompt is the base contract, to the byte.

## 4. The READ action

- **Form:** `READ <D1|ALL|D1.35-41|D1 p.7-9> <what you are looking for>`. The platform selects
  candidate units — BM25 over the units' text, the top 24 with their neighbours, within the named
  document or across all — or exactly the stretch the analyst named (up to one Reader call's worth,
  about 6,000 tokens; the digest names the units not reached), and hands them to the **Reader seat**
  with the question in one call. The Reader quotes the sentence or two that answers under each unit's
  id, then a summary. Every passage is checked against the unit's text (whitespace normalised); one
  that is not verbatim is dropped and the digest says how many were. The digest — `PASSAGES` lines
  with locators, a note, `SUMMARY`, a footer naming the stretch form and the grep — is the read turn's
  stdout; the next prompt carries it whole (cut from the middle only past 12,000 characters), and
  `SHOW READ k` re-opens it. The passages a run's reads returned stay in the prompt for the rest of
  the run, so a report written on any later turn has them to cite.
- **A READ is a turn, like a SEARCH; three a run** (`Budget.reads`), after which `READ` answers from
  the budget as `SEARCH` does. *Reason:* the original rule — every exchange is a turn — is the brake
  that keeps a run short, and it needs no switch.
- **READ runs on the platform, never in the sandbox.** No kernel function calls a model; the
  executor never holds a model key.
- **The Reader seat** exists in all four tiers, in the shape of the other seats; a template from
  before it keeps working.

## 5. Citations, the guard, the page

- The report cites units: `[D1.17]` beside `[cell 7]` and `[fig 7]`. The guard treats a number that
  appears in a cited passage as verified, and reports a cited id no document has.
- On the page a `[D1.17]` chip carries the passage a `READ` returned as its hover text and opens the
  Documents view at the unit on click; `[cell n]` and `[fig n]` chips open the cell or the plots
  (the cell chips had been silently broken since the first chain of a thread; fixed with this work).
- The pane shows a `READ` as a row while it runs (a pending row with the Reader's model) and as a row
  with its passage count when done.

## 6. Attaching documents

- The paperclip menu gains **Document** below Auxiliary Dataset; one file a pick; "Maximum 4
  documents per thread" at the limit. A page without a thread mints one at upload, as a first
  question does; a thread with documents and no question is cleaned up after a day.
- While a file is parsed the **Documents pill** carries the spinner; a refusal replaces it with the
  sentence to act on, and stays until clicked away. One pill for all documents ("Documents (2/4)");
  hover lists them with a remove icon, click opens the **Documents view**: each document's map and
  its text, passage by passage, the passages a `READ` returned marked.

## 7. Testing

`tests/analyst/test_documents.py` (parsing, storage, the kernel objects, the map),
`test_read.py` (the pipeline with a scripted Reader; the session's READ turns, SHOW READ, the
guard), `test_documents_app.py` (the engine, the executor's routes and the client's sync, the web
routes, cleanup), `test_documents_page.js` (the attach entry, the pill, the view, the chips); the
story (`tests/e2e/test_stack.py`) attaches a document, asks about it, and checks the chip and the
view. A plain run's prompt and accounting are pinned byte for byte in `test_analyst.py`.

## 8. Not built

Scanned PDFs (OCR); figures to data; embeddings for retrieval (BM25 over paragraph units with a
Reader behind it is enough at this scale — a document of a few dozen pages); map-reduce reads of a
whole long document in one turn (a stretch longer than one call is read in successive `READ`s, the
digest saying where to continue); a `LOOK` action (a cell that prints is a cell).
