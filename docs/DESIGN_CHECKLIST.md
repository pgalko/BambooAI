# BambooAI redesign — the checklist

2026-09-05. Every intervention from here on must pass every line below. A line that an
intervention cannot pass is a reason to change the intervention, not the line. The list is
short on purpose: if the harness cannot be described on one page, something on the page
is not earning its place.

## A. Shape

- [ ] A1. **One analyst, one session.** One model does the analysis, keeps the working note and writes the answer. No seat re-interprets another seat's output. The only handovers are mechanical (assembling cells into a script; rendering).
- [ ] A2. **One workspace.** A persistent kernel holds the data and every object the analyst built. Nothing is recomputed to be shown; any past cell can be re-opened by number.
- [ ] A3. **One record.** The notebook — ordered cells of code and output, figures, the note as of each turn — is the analysis of record. The executable record *is* the reproduction.
- [ ] A4. **One tree.** Turns have parents. Context for a turn is the path root→parent. Branching, continuation, end-of-run verification and replay all use one mechanism: rehydrate a path in a fresh kernel.
- [ ] A5. **The answer in the form the question needs.** A definition is a paragraph; an estimate is the report with interval and conditions; an ambiguous brief may be answered with a question to the user. The report shape is for analyses, not for every turn.

## B. What the work must have (the standard — this is the contract's spine)

- [ ] B1. Real execution with preserved outputs; nothing asserted that a cell did not print.
- [ ] B2. Quantity, units, direction and scope stated for every reported number.
- [ ] B3. Uncertainty at the sampling unit the estimate generalises over.
- [ ] B4. Support and exclusions visible: what was compared, how many, what was left out and why.
- [ ] B5. Residual confounding stated plainly; a conditional association is reported as one, an unidentified causal effect as one — neither hidden, neither dressed as the other.
- [ ] B6. A budget in turns and money, and honest reporting when it runs out or a computation fails.

## C. What the harness may NOT do

- [ ] C1. No gates, verdict vocabularies, ledger grammars or status taxonomies the model must maintain for a parser.
- [ ] C2. No prescribed method, estimator, toolkit, step order or granularity. "One move per step", "baseline first", "meaning ritual" are gone; the analyst decides.
- [ ] C3. No planner commissioning probes to other seats; no cards; no supersession; no external map. The analyst's note is the map.
- [ ] C4. No second model rewriting, summarising or re-implementing the analyst's work as a default. (Optional, off by default: a critic that returns comments; a cheaper model for the simplified rewrite, guarded.)
- [ ] C5. No benchmark vocabulary, example or method in anything a model reads - and, the standing rule since
  2026-10-05, no coaching aimed at one model's habits (restarts, figure timing, misread intervals, library
  pitfalls) and no examples taken from earlier threads. A prompt describes the work, the mechanisms and the
  format; a failure is answered by a mechanism, by evaluation or by the choice of model, not by a sentence for
  the model. The scanner test stays, and covers every text a model reads: the contract and its inserts, the
  reviewer's prompt, the rewrite task, the Reader, and every string the session, tools and reader send.
- [ ] C6. No structure added without a failure observed in the comparison runs that it fixes. Complexity is earned, never anticipated.
- [ ] C7. No context pasted "just in case": the memory index, registry dumps, prior-chain briefings and record views are replaced by tools the analyst calls (`show`, `names`, `recall`, `search`).

## D. Context and duration

- [ ] D1. The note is the durable state (question as understood; current best estimate with value, interval, unit, direction, scope; what is held fixed and how; open doubts; plan; kernel names that matter). Rewritten every turn, stored with the turn.
- [ ] D2. Recent cells ride in full; older cells collapse to one headline line each; any cell re-openable on demand. The prompt does not grow with the run.
- [ ] D3. Prompt size target: contract ≤ 1 page (~4K chars) + note (~2K) + schema (~5K) + recent cells (~10–15K).
- [ ] D4. A session persists every turn and can be continued after any interruption; a dead kernel is rehydrated from the path.
- [ ] D5. Long budgets are reviewed at fixed intervals (default after every 8th turn) by a reviewer with its own
  prompt and no actions; its verdict (TEST / NARROW / REPORT) rides in the analyst's next prompt and REPORT
  ends the analysis. Every report, in every mode, is reviewed once against the question.
- [ ] D6. Budgets attach to a run (one user question), not to the session, so branches never starve each other.

## E. Modes, routing, tools

- [ ] E1. Quick / Deep / Adaptive are budget presets of the one component (≈1+1 repair, ≈15, ≈40–60 turns), with per-preset model seating in the tier configuration.
- [ ] E2. Routing is a rule: data attached → the kernel has `df` and the schema is in the prompt; none → compute/knowledge analyst with search. It fixes the toolset, never the kind of question; the analyst judges each turn.
- [ ] E3. Tools: run a cell; show a cell; list names; recall from memory; web search; ask the user. Nothing else unless C6 earns it.
- [ ] E4. Memory (knowledge pack) is a tool read on demand and written once from the finished report and note. Its store and review UI are unchanged.
- [ ] E5. The Socratic assistant is retired; the analyst asks the user when the brief is ambiguous and otherwise states its reading in the note.

## F. Outputs, storage, UI

- [ ] F1. Two summaries per answer — technical (Answer first; how established, citing cells; limitations in three kinds; next steps; replay status) and simplified (the analyst's own plain-language rewrite, labelled). Both exportable to PDF with figures resolved by cell reference. Whole-path export as a second option.
- [ ] F2. Two mechanical guards, invisible to the model: numbers in the technical report exist in cell outputs; numbers in the simplified exist in the technical. Mismatch → a visible disclosure, never a silent edit.
- [ ] F3. The assembled script = the cited cells and their dependencies, in order; replayed in a fresh kernel; one status line (reproduced / differed / failed); one repair turn by the analyst on failure.
- [ ] F4. Artifacts render as they land: cells and note → Investigation tab; figures → Plots; reports → Answer / Simplified; script + status → Code; the tree → workflow map.
- [ ] F5. Storage keeps its shape — `threads/` (the tree), `favourites/` (a saved path, self-contained), `replays/` (a path rehydrated on another dataset, filed under its favourite), the pack, datasets, cleanup sparing favourites — with fewer things inside each file. Old threads and favourites convert once.
- [ ] F6. The infographic reads the technical report (shape unchanged).

## G. Acceptance

- [ ] G1. Comparison at equal spend against the current platform on: the altitude task, the F1 turbo-hybrid task, one task with a genuine null, one unseen task. Judged on quantity and direction, defensible design, uncertainty, completion of the deliverable, reproducibility, cost, time — not on distance from any reference number.
- [ ] G2. Every failure observed in G1 is written down before anything is added to fix it (C6).
- [ ] G3. The whole harness described on one page; the contract on one page.
