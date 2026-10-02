# Documents in the analysis: the READ action, the Reader and Embedder seats

Living document. v0.1, 2026-10-03. Kept at `docs/DOCUMENTS_DESIGN.md`. Decisions are numbered on
from `docs/OSS_DESIGN.md` (D1-D32 live there), so D33 onward live here and the two documents never
reuse a number. Updated in the same series that changes a decision. Facts about outside systems
carry the date they were checked.

## 1. What is being built

A person attaches up to four documents to a thread - papers, notes, meeting transcripts, interviews
- as PDF, Word, Markdown or plain text. They are not datasets: they are context the analysis should
be read in, or the thing a question is about. A sales CSV is analysed in the light of what the sales
meeting said; an athlete's watch data in the light of the post-session interview; a paper's tables
become a dataset analysed in the context of the paper; a question about a paper is answered from it,
with or without code. The documents do not enter the context window whole. They sit beside the
analysis, the analyst sees a short map of each, can work on their text with code, and asks for what
it needs with a new action, READ, whose answer is verbatim passages with locators. The report cites
those passages the way it cites cells, and the page shows the passage on hover and opens it on
click.

The method is the one Recursive Language Models describe (Zhang, Kraska, Khattab, arXiv 2512.24601,
submitted 2025-12-31, revised 2026-05-11; checked 2026-10-03): the long input is a variable in a
REPL the model drives with code, and the model calls a language model recursively over pieces of it
rather than reading it whole. This engine already has the REPL (the kernel), the recursive call
(SEARCH, a sub-model pass whose digest comes back sourced, recorded, re-openable and budgeted) and
citation by locator with a provenance guard. Documents are the fourth seam beside the kernel, memory
and search.

Out of scope for the first version (ruled 2026-10-03): scanned PDFs (no text layer; OCR), and
figures-to-data (digitising a plotted chart needs a vision model and yields estimates).

## 2. What exists that this builds on

- The analyst's contract (`analyst/contract.md`) and loop (`analyst/session.py`): one action per
  turn from CELL, SHOW, NAMES, RECALL, SEARCH, ASK, REPORT. A search is a turn of kind `search`; its
  digest is recorded whole, the prompt sees the first 4,000 characters, `SHOW SEARCH k` reopens it,
  and `Budget.searches` caps them per chain with a message when spent.
- The report guard (`analyst/report.py`): every number in the technical report must exist in a cell
  output on the path, and every number in the rewrite in the report; a mismatch is disclosed, never
  silently edited. `[cell n]` and `[fig n]` are the citation forms; the page turns them into chips
  (`web_app/static/js/stream-pane.js`) that open the cell or the Plots tab, and `[A3]` chain
  references already carry a hover tooltip (`content-rendering.js`).
- Files beside the data: auxiliary datasets (up to three) travel to the kernel's working directory -
  locally `datasets/<user>/`, in api mode through the executor's `/file_utils/upload_aux_dataset`
  into `datasets/<user>/` under `/app` - and the analyst is told their paths in one line of the
  prompt. A hosted container is ephemeral: the restart handler clears the list because the files die
  with it.
- Thread files on the app box's disk, in both editions: `storage/<user>/threads/<thread_id>.json`,
  favourites under `storage/<user>/favourites/<thread_id>/`; `cleanup_threads_for_user` removes
  non-favourite threads' files; `delete_thread` removes one.
- Seats: a tier of `LLM_CONFIG_template.json` is a list of `{"agent": name, "details": {...}}`,
  seven per tier today; the app looks a seat up by name and falls back to the Analyst's when a tier
  lacks it (the Rewriter, 2026-09-11). The dispatcher (`bambooai/models/__init__.py`) maps a
  provider to its adapter's `llm_call`/`llm_stream`.
- Memory (`bambooai/knowledge_pack.py`) scores RECALL candidates and the PUSH gate by embedding
  cosine through `bambooai/embeddings.py`, which today picks a hard-coded client by the undocumented
  `EMBEDDING_PLATFORM` variable (OpenAI `text-embedding-3-small` by default, one call per text) and
  falls back to lexical token-set cosine when no client can be built. Nothing stores a vector.

## 3. The documents: upload, parsing, storage

- **D33. Documents belong to the thread.** Up to four per thread, each at most 10 MB, as `.pdf`,
  `.docx`, `.md` or `.txt`. Every chain in the thread sees them, like datasets. *Reason:* the ledger
  of earlier chains rides with every turn; a document a chain read is part of what the next chain
  knows.
- **D34. Parsed once, at upload, into units with locators.** A unit is a paragraph-sized block with
  an id (`D2.17`: document 2, unit 17), a kind (`heading`, `paragraph`, `list`, `table`, `caption`),
  its place (page for a PDF; the heading trail for Word, Markdown and text), and its text. A table
  unit carries its rows as CSV beside the text and its caption when one is adjacent. *Reason:* a
  unit id is exact and checkable, as `[cell 7]` is; a page is not, since a page holds many passages.
- **D35. Files, not tables.** Everything lives under `storage/<user>/documents/<thread_id>/`:
  `manifest.json` (the documents of the thread: id D1-D4, file name, type, pages or sections, units,
  text bytes, sha256, uploaded at), then `<doc_id>/original.<ext>`, `text.json` (the units),
  `text.md` (the units joined, each preceded by its locator marker, for code to grep), `map.md`
  (section 4), `tables/<n>.csv`, and `embeddings/<model>.json` (section 3, D37). The same path and
  layout in both editions; removed by `cleanup_threads_for_user` and `delete_thread` with the
  thread, kept when the thread is favourited; no new table in `local_store.py` or Supabase.
  *Reason:* the two editions must not diverge without need, the thread's files already live this
  way, and a file folder is the smaller hosted change.
- **D36. Light, permissively licensed parsers.** `pdfplumber` (MIT) for PDF - text by page with
  layout, tables through its table finder; `python-docx` (MIT) for Word - paragraphs with their
  heading styles, tables; Markdown and text by headings and blank lines. Both become dependencies of
  the package. Not PyMuPDF (AGPL; the hosted service would carry it). A heavier layout parser
  (Docling, MIT, torch) is a later option for the self-hosted machine, never for the web box. A PDF
  whose text layer is empty or near-empty is refused at upload with a plain message ("this PDF has
  no text layer; a scanned document needs OCR, which is not supported"). Parsed text above 2 MB is
  refused with the size stated (open: refuse or keep the first 2 MB - O-D2). *Reason:* parsing is
  the ceiling of everything after it, and the baseline has to run on the web box and install with
  `pip` on a laptop.
- **D37. Embeddings per unit, cached by model.** Computed at upload through the Embedder seat (D48)
  in batches of up to 64 texts, stored as `embeddings/<model>.json` keyed by the seat's model name.
  When the seat cannot be reached at upload, the document is still usable (lexical selection) and
  the embedding is retried at the next READ. *Reason:* embeddings are deterministic for a text and a
  model, so once per thread is enough; a cache keyed by model survives a change of seat by
  re-embedding.

## 4. In the kernel and in the prompt

- **D38. The text travels to the kernel, idempotently, at every chain start.** Locally a copy into
  `datasets/<user>/documents/<doc_id>/`; in api mode through the executor's file route with a
  `documents/<doc_id>/` destination, into the same place under `/app`. What is already there (by
  sha256) is not sent again. The same push runs before a replay, since a cited cell may have read a
  document file. The prompt's data block names them beside the auxiliary files: the folder, and in
  it `text.md`, `text.json` and `tables/*.csv`. *Reason:* this is the REPL half of the method - grep
  a transcript for a product name, slice a section, load table 2 into a dataframe and check it
  against the paragraph that describes it - exact and cheap, and hosted containers forget between
  chains.
- **D39. A map of each document rides with every turn.** `map.md`, built at upload: file name and
  type, pages or sections, word count, the outline (headings, up to twenty), the tables (number,
  caption, shape), the figure captions (up to ten). Under about 250 tokens a document, about 1,000
  for four, in the block that shows the dataframe's schema and the auxiliary files. *Reason:* the
  analyst has to know what exists to decide what to read, without reading it.

## 5. The READ action

- **D40. READ is an action of the contract, served by the platform.** Form: `READ <D1|D2|D3|D4|ALL>
  <what you are looking for>`, e.g. `READ D1 the sample size and inclusion criteria` or `READ ALL
  every mention of the Q3 pipeline`. The platform selects candidate units, hands them to the Reader
  seat (D47) with the question, verifies what comes back, and returns a digest: `PASSAGES (verbatim,
  each with its locator):` then one line per passage - `- [D1.17] (paper.pdf p.4) "..."` - then
  `SUMMARY:` in the reader's words, or a plain statement that nothing in the documents answers. It
  is a turn of kind `read`, its text the query and its stdout the digest; the prompt sees the first
  4,000 characters, `SHOW READ k` reopens it whole, `SHOW RUN k` carries an earlier chain's reads as
  it carries its searches. *Reason:* the recursive call of the method, in the shape the analyst
  already knows from SEARCH.
- **D41. Selection is hybrid and verification is verbatim.** Candidates: lexical (BM25 over the
  units) and embedding cosine (the cached vectors against the embedded question), fused by
  reciprocal rank, the top 24 with their neighbouring units for context, within the named document
  or across all four. The Reader is asked for passages that answer, quoted exactly, each with its
  unit id, and a summary. Every returned passage is checked against the unit's text (whitespace
  normalised); one that is not verbatim is dropped and the digest says how many were. Without a
  reachable Embedder the selection is lexical only, and the digest says so. *Reason:* a quote the
  page shows on hover must be the document's words; the check at READ time is what lets the report
  guard trust the digest (D45).
- **D42. Comprehensive reads recurse, within caps.** When the scope is ALL and the question asks for
  everything, or when the candidates do not fit one reader call, the platform splits the scope into
  segments of about 6,000 tokens (runs of pages or sections), runs the Reader over each (map), then
  once more to merge the findings (reduce) - passages still verbatim with their ids. Caps per READ:
  depth 2 (a segment is split again only when it does not fit), 12 reader calls; a read that would
  need more stops at the cap and names the pages or sections it did not reach. The caps are details
  of the Reader seat: `read_calls` (12), `read_depth` (2), `read_segment_tokens` (6000). *Reason:*
  this is the recursion the method relies on for coverage; the caps are what make a READ's cost
  predictable.
- **D43. Three reads a chain.** `Budget.reads = 3` in every preset, beside `searches`; when spent,
  READ answers as SEARCH does: work with what the earlier reads returned (`SHOW READ k`), or state
  plainly what was not found. *Reason:* settled 2026-10-03; three aimed reads with recursion inside
  them cover a thread's documents, and the kernel path (D38) is always open for more.
- **D44. READ runs on the platform, never in the sandbox.** No kernel function calls a model; the
  executor never holds a model key. *Reason:* the hosted executor runs the person's code.

## 6. Citations, the guard, the page

- **D45. The report cites units.** `[D1.17]` beside `[cell 7]` and `[fig 7]`. The page renders it as
  a chip reading the file name and place ("paper.pdf p.4"); hover shows the passage (the unit's
  text, trimmed to about 300 characters) through the tooltip the chain references use; click opens
  the Documents tab at the unit. The guard extends in two ways: a cited unit must exist in the
  thread's documents (one that does not is disclosed as the number check discloses: "CHECK: [D3.9]
  is not in the documents"), and a number in the report may be matched against the text of cited
  units as well as against cell outputs. Quotations are already verified at READ time (D41).
  *Reason:* one provenance discipline for cells, figures and passages; the reader sees where every
  claim came from.
- **D46. The page.** A Documents tab in the pane beside Investigation and Plots: the thread's
  documents with their maps, and the passages each READ returned marked in place. A READ row in the
  stream with the label READ and "n passages" on the right, as a search row shows its sources. In
  the file area, "Documents (n/4)" beside the auxiliary datasets, with upload, remove, and the
  refusal messages of D36 shown as they are written. *Reason:* the action is visible when it happens
  and the evidence is one click away, as for cells and searches.

## 7. The seats

- **D47. A Reader seat.** In all four tiers, the shape of the other seats: `{"agent": "Reader",
  "details": {"provider": "openrouter", "model": "deepseek/deepseek-v4.1-flash", "temperature": 0,
  "max_tokens": 8000, "read_calls": 12, "read_depth": 2, "read_segment_tokens": 6000}}` in the cost
  tier; the other tiers choose their own model (O-D3). A tier without the seat uses its Analyst's,
  as the rewrite does. *Reason:* the reader is a different job from analysis - selection and
  faithful quotation over long text - and should be a cheaper model chosen per tier.
- **D48. An Embedder seat, the only place the embedding model is chosen.** In all four tiers:
  `{"agent": "Embedder", "details": {"provider": "openrouter", "model":
  "openai/text-embedding-3-large"}}`, with an optional `dimensions` detail. One model across tiers,
  so a tier change never invalidates a thread's cache. Providers with an embeddings call: OpenRouter
  (`/api/v1/embeddings`, the OpenAI request shape; checked 2026-10-03), OpenAI, Gemini, Mistral,
  Ollama (`/api/embed`), vLLM when it serves an embedding model. Anthropic, Groq and DeepSeek have
  none, and the configuration dialog says so rather than accept them for this seat. Absent or
  unreachable, documents and memory run on the lexical path and say so. *Reason:* ruled 2026-10-03.
  On OpenRouter `text-embedding-3-large` is $0.13 per million tokens against $0.02 for `-small`,
  inputs up to 8,192 tokens, 3,072 dimensions, MTEB 64.6 against 62.3 and far better multilingual
  retrieval (MIRACL 54.9 against 44.0); a document is embedded once per thread, so a 30-page paper
  costs a third of a cent and a document at the text cap six or seven. `EMBEDDING_PLATFORM` in
  `.env` retires: it was never documented and nothing set it.
- **D49. `embed` in the adapters that have it.** `embed(texts, model, api_keys) -> vectors`,
  batched, in `openrouter_models.py`, `openai_models.py`, `gemini_models.py`, `mistral_models.py`,
  `ollama_models.py`, `vllm_models.py`; the dispatcher gains `embed(agent="Embedder", texts)`.
  *Reason:* the dispatcher pattern we have, one more entry point.
- **D50. The free tier is open.** Its Embedder seat cannot be a paid model if the tier must cost
  nothing; the cheapest OpenRouter lists are $0.01 per million with 512-token inputs. Either the
  tier embeds at that price, or it runs memory and documents on the lexical path and the dialog says
  so (O-D1).

## 8. Memory on the Embedder seat

- **D51. Memory embeds through the seat, in the same round.** `knowledge_pack._get_embedder()` takes
  its client from the dispatcher's `embed` on the Embedder seat and sends one batched call per
  retrieval (the seed and every card's hooks) instead of one call per text. The lexical path stays
  as the fallback and as the PUSH gate's always-on relevance test. `embeddings.py`'s hard-coded
  clients - `OpenAIEmbeddingClient`, `HFSentenceTransformersClient` - and `EMBEDDING_PLATFORM`
  retire; the sentence-transformers option was never a dependency and nothing selected it. *Reason:*
  memory stores no vectors, so the switch changes the next retrieval's scores and nothing else; one
  place to choose the model, for both consumers.

## 9. Testing

- Fakes in `tests/analyst`: a scripted Reader (returns passages by unit id, including one that is
  not verbatim, to prove the drop) and a deterministic Embedder (a hash-based vector), as the Ollama
  and vLLM suites fake their daemons. Fixtures generated in the test, not checked in as binaries: a
  three-page PDF written with matplotlib's `PdfPages`, a Word file written with `python-docx`, a
  Markdown transcript; a PDF with no text layer for the refusal.
- Unit checks: parsing to units and locators for each format; the map; the manifest; `text.md`'s
  markers; the embedding cache keyed by model; hybrid selection and reciprocal rank fusion; the
  verbatim check; the digest's shape; `SHOW READ k`; the budget message; the recursion caps and the
  "not reached" statement; the guard's two extensions; the dispatcher's `embed`; memory's batched
  call.
- The page (`test_pane.js`): the READ row with its count, the `[D1.17]` chip, the hover text, the
  Documents tab. The stack story (`tests/e2e/test_stack.py`): one document uploaded, a READ turn in
  the scripted analyst, a report citing a unit, the chip in the page, the file present in the kernel
  after a simulated container restart, the folder gone after the thread is deleted.
- Real documents on the Mac, not in CI: two papers and two transcripts with questions whose answers
  are known (a number in a table, a statement in a transcript), run as a small set under
  `tests/documents/` with the recall recorded in its README. Nothing is called done on fakes alone.

## 10. Phases

Every phase touches hosted paths (`web_app/`, `analyst/`, `containers/executor/`, the template), so
the order is the dev box first, then prod, then the Mac, and the four `[confirm]` items of the
session seed are due at the start of A.

- **A. Documents in the thread.** The upload slot and its page; parsing (D34, D36) and the folder
  (D35); the map (D39); the push to the kernel at chain start and before replay (D38); cleanup with
  the thread; the Documents tab in its first form (the list and the maps). No new action yet. *Done
  when:* four documents attach to a thread in both editions; the map rides in every chain's prompt;
  the analyst greps a transcript in a cell; the files are back in a hosted container after a
  restart; a deleted thread leaves no folder.
- **B. READ, the seats, memory.** The Reader and Embedder seats in the template and the dialog (D47,
  D48, D50 as decided); `embed` in the adapters and the dispatcher (D49); embeddings at upload
  (D37); memory on the seat (D51); READ with hybrid selection, verification and the digest, `SHOW
  READ k`, the budget (D40, D41, D43, D44); the READ row, the chips and tooltip, the Documents tab's
  passages (D45, D46); the guard's extensions; the README's Documents section. *Done when:* the four
  use cases of section 1 run on the dev box with the scripted analyst and on the Mac with a real
  paper and a real transcript; the battery carries the fakes; the recall set exists.
- **C. Comprehensive reads and the dataset case.** The map-reduce read with its caps (D42); the
  paper to dataset path polished end to end (tables as CSV in the kernel, the generated dataset
  returned); the recall set grown and the selection tuned on it.
- **D. Later, as wanted.** A heavier parser as an option (Docling), OCR for scanned PDFs, figures to
  data through a vision seat, the `dimensions` detail.

## 11. Open

- **O-D1.** The free tier's Embedder: a $0.01 model, or the lexical path (D50).
- **O-D2.** Parsed text above 2 MB: refuse the file, or keep the first 2 MB and say so (D36).
- **O-D3.** The Reader's model per tier beyond the cost tier's `deepseek/deepseek-v4.1-flash` (D47).
- **O-D4.** Upload parsing runs inside the request first; a 300-page PDF may take tens of seconds,
  and a background job with a status, as the container status has, is the step if that proves too
  long.
- **O-D5.** Whether READ digests of earlier chains should be reachable by `SHOW READ` directly, or
  only through `SHOW RUN k` as searches are (D40).
