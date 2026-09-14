# Redesign inventory — what goes, what changes, what stays

2026-09-05. Against the checklist in `01_DESIGN_CHECKLIST.md`. "Remove" means delete the
code as the replacement lands (in place, not in a parallel tree). "Simplify" means keep
the responsibility, cut the mechanism to what the checklist allows. Line counts are the
current tree's.

## 1. New (one small package, ~600–900 lines total)

| Module | Responsibility | Checklist |
|---|---|---|
| `analyst/session.py` | the turn loop: build the prompt (contract + note + schema + recent cells), call the model, dispatch the action (cell / show / names / recall / search / ask / report), store the turn, self-review at intervals, budget in turns and money | A1 A2 D1–D6 E2 E3 |
| `analyst/notebook.py` | the tree of turns (id, parent, question, cells, figures, note snapshot, reports, replay status); path resolution; collapse older cells to headlines; persist every turn | A3 A4 D2 D4 F5 |
| `analyst/note.py` | the working-note schema and its parse/render (question as understood; estimate value/interval/unit/direction/scope; held fixed and how; doubts; plan; names) | D1 |
| `analyst/tools.py` | `run_cell`, `show_cell`, `names`, `recall` (knowledge pack), `search` (existing search seam), `ask_user` | E3 E4 |
| `analyst/replay.py` | assemble cited cells + dependencies into one script; rehydrate a path in a fresh kernel; compare outputs; status line; one repair turn | A4 F3 |
| `analyst/report.py` | the two summaries from the analyst's last turns; figure references by cell; the two numeric guards; export hooks | F1 F2 F6 |
| `analyst/contract.md` | the one-page contract (the only prompt) | B1–B6 C1–C7 G3 |

## 2. Remove (the seats and the machinery between them)

| Module / symbol | Lines | Why it goes |
|---|---|---|
| `bambooai/adaptive_delve.py` — entire module: `RunState`, `parse_outer_decision`, `enforce_budgets`, `card_from_briefing`, `run_adaptive_delve_loop`, `_render_card/_register/_pool/_map`, `compose_outer_prompt`, `run_outer_delve`, `run_inner_delve`, `extract_result_tables`, `tag_result_tables`, `plot_catalogue`, `resolve_figure_markers`, `script_reproduction_missing`, `method_identity_disclosure`, `consolidation_failure_disclosure`, `degraded_disclosure`, `build_trajectory`, `format_trajectory_for_synthesis`, `run_adaptive_delve`, `_run_terminal_synthesis`, `_check_can_continue`, `_get_dataset_schema` (moves), `_compact_dataset_schema` (moves), `repair_markdown_tables` (moves to report.py) | 1,723 | planner, cards, supersession, map fields, terminal synthesis, disclosures: C1 C3 C4. Two helpers move. |
| `delve/synthesis.py` — `Synthesizer`, `Editor`, `assemble_evidence`, `_parse_synth`, `parse_findings`, `technical_document`, `check_coverage`, `check_numbers`, chart/citation renderers | 667 | the Synthesizer and Editor seats: A1 C4. `check_numbers` logic reappears as the numeric guard in `report.py`. |
| `delve/nav_state.py` — `NavState`, `Entry`, `g1_satisfied`, `code_shows_stratification`, ledger parsing | 512 | ledger grammar and the G1 gate: C1. |
| `delve/prompts.py` — all Investigator / Synthesizer / Editor / directive constants (`INVESTIGATOR_SYSTEM`, `STEP_PROTOCOLS`, `INVESTIGATOR_WAY`, `INVESTIGATOR_HEAD/TAIL/STEP_TEMPLATE`, `SYNTHESIZER_*`, `EDITOR_*`, `STANDARD_OF_PROOF`, `DIRECTIVE_*`, `CLAIM_EXTRACTION_*`, `RECONCILIATION_*`, `BUDGET_WRAPUP_*`, `AUDIT_SEED_*`, `SYNTH_FORMAT_REPAIR`, `WORKING_SET_HEADER`, `ESTIMAND_NOTE_*`) | 810 | replaced by `analyst/contract.md`: C1 C2 G3. Keep only what the search seam needs (`LITERATURE_SEARCH_TEMPLATE`, `SEARCH_MIDSTREAM_TEMPLATE`), moved next to the search tool. |
| `delve/investigation.py` — `Investigator`, `run_investigation`, `_parse_investigator`, `_render_context`, `_step_block`, `_permanent_block`, the working-set / archive / rehydrate machinery, the salvage path | 1,349 | the loop moves to `analyst/session.py` with the note instead of ledgers and the collapse rule instead of working-set/archive/rehydrate: C1 C7 D2. |
| `delve/toolkit.py` and `containers/executor/toolkit.py`; the preload/stub blocks in both `kernel.py` | 607 ×2 + ~40 | advertised toolkit: C2. (Kept only if G1 earns one helper back.) |
| `delve/verify.py` | 203 | spec-era verifier; unused by the new loop. |
| `bambooai/planner/step_selection.py` — `select`, `render`, `harvest_toolbox`, `toolkit_transplant`, `finding_literals`, `present`, `_value_and_half_unit`, `steps_named_in`, `_mutates_ambient`, `_defines_and_uses` | 556 | the hand-over to a second coder and the number matcher: A3 C4 F3. Cell dependency tracing (a small part of `_defines_and_uses`) reappears in `replay.py`. |
| `bambooai/planner/driver.py` — `run_planner`, `PlannerResult`, `_salvage`, `_fan_out`, `_findings_block`; `bambooai/planner/llm_bridge.py` (`BambooLLMBridge`, `_Collapsed`) | 543 + 464 | the app→delve adapter for the old loop; the session calls the model layer directly. |
| `bambooai/planner/budget.py` (`InvestigationBudget` tier logic) | 190 | replaced by the run budget in `session.py` (turns + money): B6 D6. Tier caps stay in config. |
| `bambooai/conversation_ledger.py` — `entry`, `ancestry`, `headline_from`, `results_headline`, `finding_blocks`, `render_view`, `render_index`, `hydration_parcel`, `chain_parcel_for_query`, `resolve_reference`, `should_hydrate`, `carried_names`, `render_code_block`, `distill_source_from_entry` | 502 | the record view / ledger / parcel machinery: the tree and the note replace it: A4 C7. |
| `bambooai/bambooai.py` — `select_expert`, `select_analyst`, `task_eval` (Theorist route), `taskmaster`, `investigate`, `_proven_code`, `_coder_conversation_view`, `_selector_conversation_index`, `_theorist_conversation_view`, `generate_code`, `_deep_chain_disclosures`, `correct_code_errors`, `summarise_solution`, `_resolve_chain_reference`, `_build_chain_parcel`, `_persisted_investigation`, `_purpose_line`, `_id_event_extra`, `_kernel_sidecar_*`, `reset_investigation`, `should_include_plan`, `_tools_for` | ~1,900 of 2,871 | the seven-seat pipeline: A1 C4 E2 E5. |
| `bambooai/messages/default_prompts.yaml` — `expert_selector_*`, `analyst_selector_*`, `theorist_system`, `ideas_explorer`, `outer_delve`, `exploration_synthesis`, `code_generator_*` (all six), `error_corector_*` (all four), `solution_summarizer_*` (three), `socratic_assistant_system`, `google_search_query_generator/summarizer/react`, `plot_query*`, `knowledge_distiller_*` (see §3) | most of the file | one contract replaces them: C1 C4 E5 G3. |
| `bambooai/messages/reg_ex.py` — `_extract_code` blacklist scanner and main-block processor, edit-block parser/applier (`_extract_edit_blocks`, `apply_edits`) | 393 | the corrector's edit protocol goes; the blacklist moves to the kernel as a plain import check on the cell. |
| `bambooai/messages/tools_definition.py` (function-calling schemas for old seats) | 499 | unused. |
| `bambooai/context_retrieval.py` | 266 | prior-chain retrieval into prompts: C7. |
| `bambooai/planner/kernel_client.py` `RemoteKernel` | 295 | keep the transport, drop the spec-era surface (see §3). |
| `web_app/app.py` — `/update_planning`, `/get_planning_state`, `/stop_exploration` (becomes stop run), `/storage/trajectory_favourites` (folds into favourites), the chain-mode branching in `/query` | ~300 | E1 F5. |
| `web_app/static/js/` — `agent-instructions.js`, `workflow-modal.js` (planning modal), the per-seat event handlers in `query-processing.js`, `content-rendering.js`'s per-agent blocks, the register/cards panel | several hundred | replaced by the typed-artifact stream: F4. |
| `bambooai/synthesis_infographic.py` — the extractor prompt path stays; the section-based sourcing already gone | — | keep (F6); only its caller changes. |
| Tests: `tests/delve_planner/*` suites that pin the removed machinery (planner, cards, supersession, ledger, gates, hand-over, matcher, toolkit, prompt fragments) | ~40 of 43 suites | replaced by a small suite per new module: the tree, the collapse rule, the replay, the guards, the contract's scanner, the export. |

## 3. Simplify (responsibility stays, mechanism shrinks)

| Module / symbol | Now | After |
|---|---|---|
| `bambooai/bambooai.py` (what remains) | 2,871 lines, 42 methods | `BambooAI.__init__`, dataset handling, `pd_agent_converse` → `analyst.session.run(question, thread, parent)`, memory hooks, cleanup. Target ≤ 500 lines. |
| `bambooai/models/*` + `models/__init__.py` (`llm_stream`, the turn ladder, effort seam, cache) | provider adapters | keep as is; one caller instead of nine agents; the `agent` label becomes the seat name "analyst" (+ "critic", "rewrite" when enabled). |
| `delve/llm.py` (`LLMClient`, providers, `call_with_ladder`, `literature_search`, `CostTracker`, `RunLogger`) | 1,619 lines, two call paths | keep the search functions and cost/telemetry; drop `call_with_ladder`'s directive plumbing and the duplicate provider path (the app's model layer is the one path). Target ≤ 600. |
| `delve/kernel.py` / `containers/executor/kernel.py` | 942 lines each: exec, plots, registry with previews, toolkit preload | keep exec, output capture, figure capture, time/memory limits, the import blacklist; drop the registry-with-previews (`names()` returns names + types only) and the toolkit preload. |
| `bambooai/planner/kernel_client.py` `RemoteKernel` / `containers/executor/kernel_service.py` | spec-era API (run step, registry, rehydrate) | `run(code)`, `names()`, `reset()`, `snapshot_figures()`; rehydrate = run the path's cells. |
| `bambooai/storage_manager.py` `SimpleInteractionStore` | chains + ledger + trajectory; `restore_interaction`, `save/load_exploration_trajectory` | `save_turn`, `load_path`, `load_thread`, favourites as saved paths, replays under favourites; a one-time `convert_legacy_thread`. |
| `bambooai/messages/message_manager.py` | messages per agent, ledger hydration, code history | the notebook is the history; keep only dataset/aux-file bookkeeping if any. Likely folds into `notebook.py`. |
| `bambooai/knowledge_pack.py` | `memory_index` and `memory_cards_for_prompt` pasted into prompts; distiller staging | keep the store, `retrieve`, `append_card`, `reinforce`, `maintain`, the review UI; expose `retrieve` as the `recall` tool; write cards from the finished report/note (analyst-authored or distiller as a post-pass). Drop `memory_index`/`memory_cards_for_prompt` (C7). |
| `bambooai/web_output_manager.py` / `output_manager.py` | per-agent display calls (`display_tool_start`, `display_corrected_code`, `send_assistant_consultation`, …) | one `emit(artifact)` for the typed stream: cell, figure, note, report, replay_status, question_to_user, error. |
| `web_app/app.py` `/query`, `/load_thread`, `/get_existing_chains`, `/get_chain_preview`, `/delete_chain`, favourites, replay routes, memory routes | chain-shaped | node-shaped (an answer node = the UI's chain); favourites save a path; replay rehydrates a path on a dataset. |
| `web_app/replay_routes.py`, `chain_replay_utils.py`, `cleanup.py` | replay a chain's script | replay a path via `analyst/replay.py`; cleanup unchanged. |
| `web_app/static/js/query-processing.js`, `content-rendering.js`, `workflowGraph.js`, `workflow-management.js`, `workflow-replay.js`, `pdf-export.js` | per-chain events; map from ledger | render the artifact stream into the existing tabs; map from the tree; export from stored reports and cell-referenced figures. |
| `web_app/llm_config_builder.py`, `LLM_CONFIG_template.json`, `validate_config.py` | nine seats × four tiers | three seats (analyst, optional critic, optional rewrite) × three presets; model_properties unchanged. |
| `bambooai/messages/default_prompts.yaml` | 32 templates | `synthesis_infographic_template` and the search templates; everything else replaced by `analyst/contract.md`. |

## 4. Keep unchanged

The executor container and its service (minus the toolkit preload); the provider adapters; the knowledge-pack store and review UI; the infographic renderer; datasets, uploads, auth, subscriptions, integrations, labels, cleanup; the PDF exporter's renderer; the workflow map's drawing code (fed by the tree).

## 5. Order of work (in place, old code removed as each step lands)

1. `analyst/` package + contract; a headless run on the altitude dataset from a test harness (no UI). Battery: the new module suites only.
2. `bambooai.py` rewired to the session; the old seats deleted; `default_prompts.yaml` cut to the survivors; `adaptive_delve.py`, `delve/synthesis.py`, `nav_state.py`, `prompts.py`, `investigation.py`, `planner/`, `conversation_ledger.py`, `context_retrieval.py`, `reg_ex.py`, `tools_definition.py` deleted.
3. Storage: the tree, favourites-as-paths, replay-as-rehydrate, the legacy converter.
4. Web layer: the artifact stream, the tabs, the map, exports, the config builder for three seats.
5. Kernel: registry-with-previews and toolkit removed; `names()`; the import check.
6. The comparison runs (G1); failures written down (G2); nothing added without one.
