# Branching an analysis — design v0.3 (2026-11-21; for 2.9; built: 0318, the kernel's states; 0319, the engine; 0320, the page)

An analysis is a line of turns. The person goes back to any turn, gives the Analyst a hint, and the analysis goes
on from there another way. The first way stays. A map shows every turn of every branch and takes the person to
any of them. This is the product owner's idea of 2026-11-20, agreed with him the same day; the Architect's
conversation got the same on 2026-11-19 (docs/ARCHITECT_DESIGN.md §2.25).

The story in one paragraph. An analysis of the field trial finishes in eight turns, and its figure pools the two
soil types. On the map the person sees that turn 5 did the pooling. They click turn 4: the left pane ends there,
the figure stays on the right. They type *keep the soil types apart* and send. The Analyst is given turns 1 to 4
and the hint, writes turn 5 again, and goes on to a report of its own. The map now shows two branches from turn 4;
a click on a turn of either brings that branch back, tabs and pane. Going back to turn 4 warns the Analyst before
the step; going back to turn 5 keeps the step and has it corrected. It is one move.

## 1. Words

- **Turn** — one reply of the Analyst and what it did, as the left pane numbers them (*Turn 5*).
- **Cell** — a turn's code that ran, numbered along the thread's path (`Turn.cell_no`); the code map's unit.
- **Branch** — a way an analysis went on from one of its turns. The first run is not a branch.
- **Hint** — what the person says when they go on from a turn; it stands in the Analyst's prompts to the report.
- **Step** — the kernel's word: a committed execution, numbered within one kernel. A cell is a step; so are the
  host's prelude and its probe of a warm kernel.
- **State** — what the kernel holds after a step. A **snapshot** is a state saved to disk.

## 2. Decisions (the product owner's, 2026-11-20)

1. The kernel keeps a snapshot after every cell, built properly from the start; the executor image is rebuilt.
2. Every branch is stored when a thread is saved. Nothing is locked after saving.
3. A box on the map is a turn as the left pane numbers them, with its cell number.
4. A branch runs in the mode of the first run, and the turns kept count as used. The Architect is not called for
   a branch, also when it is switched on.
5. Only analyses made after the build can be branched.
6. The map works as the thread map and the conversation map do: hover to read, click to go, type to branch.
7. The map is the **Turn map**. Its button, and the conversation map's, carry the Git branch icon; the thread map
   keeps its own.
8. Going back moves the left pane only. The right pane keeps the result, so the person looks at the figure while
   they write the hint.
9. A hint is required.
10. The brief stays: a branch of a framed analysis runs under the same brief.
11. The earliest place to go on from is after turn 1, the latest the turn before the report.
12. The thread map and the chain arrows count analyses, not branches.
13. Memory takes the branch the person saved from or went on from. A branch they left is stored for the map only.
    The hint is kept with its branch, and memory shows it.
14. The person pays for the new turns only.

Not in the first version: a routine's run; an analysis started from *Ask AI about this plot*; branching while the
analysis runs (a stopped analysis can be gone on from). The data the analysis ran on must be loaded.

## 3. The kernel's states (0318, built)

**What it does.** After every committed step the worker saves its whole state, and the kernel can go back to the
state after any of its steps. Nothing is run again to get there, so a step that drew random numbers without a
seed, or took a minute, holds what it held.

**What a snapshot holds.** Every name the cells made: data, functions, lambdas, classes and their instances. The
modules the cells loaded. The random generators (numpy's, Python's). numpy's print options, the pandas options and
matplotlib settings a cell changed, the working directory. **Not:** the files a cell wrote; what a cell changed
inside a library, or in the environment variables; the tie between an array and a view of it - `x = a[:, 0]` and
`a` come back as two arrays with the same values, so a later change of one in place no longer shows in the other.

**How** (`delve/kernel.py`; the executor image's copy differs by one import line).

- A function or a class a cell defined is saved by value, with cloudpickle. On restore its globals are the live
  namespace again, so a name a later cell rebinds is seen by it as it would have been.
- What the kernel owns — its namespace, `RESULT`, its hooks, the process environment — is named in the snapshot
  and linked on restore, never copied. `DS` and `RESULT` are the kernel's own at every worker start, whatever a
  cell bound those names to.
- A large buffer (an array, a block of a frame; 64 KB and over) is written once, under the hash of its content, and
  shared by every snapshot that holds it.
- The dataset as loaded is not written while `df` holds it unchanged: the kernel's first worker takes its
  fingerprint before the first cell runs.
- The modules loaded since the worker started are listed beside the snapshot, and the worker that takes over
  imports them before it reads it. A submodule reached through its package (`import a.b`, and `a.b.f()` in a later
  cell) is there again, and so is what an import registered.
- A state is saved whole or not at all. One object that cannot be saved (a generator, an open file, a lock), or a
  disk that does not take it, leaves the step without a snapshot and nothing of the attempt on disk. The kernel
  keeps the names that stood in the way and warns of them once, in its log: *the state after step 4 was not saved
  (stream)*.
- Without cloudpickle nothing is saved: the kernel goes back by running cells again, as it did before 2.9 from the
  first cell that defined a function.

**Steps and going back.** A step gets a number, given once within its kernel; `last_step` is the state the kernel
is at, 0 at the start. `goto(step)` brings the kernel there: from that step's snapshot, or - where that state was
not saved - from the nearest saved state before it, running the steps between again; `last_goto` says which, and
what each printed this time. A snapshot that does not load sends it one saved state further back. A step that
raises, hangs or dies when run again sends it to the last resort: a clean worker and the whole history, the
kernel's behaviour before 2.9, where a step that raises is passed over. Where the history hangs or dies even there,
`goto` returns False and the kernel has no worker until the next step asks for one. A failed cell, a timeout and a
dead worker are all rolled back this way, to the state the kernel was at.

**The cap.** One kernel's snapshots take at most `KERNEL_SNAPSHOT_MB` on disk (2048), in the temporary folder: the
executor container's `/tmp`. Over it the oldest go. The state the kernel is at keeps its own whatever its size, as
the one checkpoint did before 2.9. A snapshot lives as long as its kernel: an hour without use in the executor
(`KERNEL_IDLE_TIMEOUT`), a restart, a thread opened again later all end it.

**Through the executor.** `/kernel/execute` returns `step`; `/kernel/goto` takes one. `RemoteKernel` has
`last_step`, `goto` and `uid`, its session. An image before v75 returns no step, and nothing asks it to go back.

**On the record.** A cell's turn keeps `snap`, `"<kernel>:<step>"` (`analyst/tools.snap`): where a kernel that
still holds that state goes back to. Rehydrating a path in a new kernel renews it for each cell run again.

**In the host** (`BambooAI._kernel_for`). A chain asked from the chain the kernel ended at goes on in the warm
kernel, as before. A chain asked from an earlier one: the kernel goes back to the state that chain ended in -
after the last cell computed on its path, or its start when the path computed nothing. Where the kernel does not
hold that state - it is gone, it is another frame's, the chain is from before 2.9 - the cells are run again in a
fresh kernel, as before. While a run is under way the kernel is at no chain's end, so a run that was stopped or
failed leaves nothing behind for the next one.

**Known limit.** A statsmodels fit made from a formula is expected not to be saved (patsy refuses pickling); a
kernel that holds one falls back to running cells again. Not tested where this was built: statsmodels was not
there.

## 4. The branch in the engine (0319, built)

**The record.** A branch is a run of its own beside the one it goes on from: the same parent, question, brief (with
the conversation that made it and the drafts of its figures), limits (`Run.budget`), mode and data. Its turns are
copies of that run's turns up to the turn, each marked `kept`, then its own. `Run.branch` names the chain whose
turn it goes on from, and the turn; a turn that chain itself kept from another is the other chain's, and so is
the branch (`Notebook.owner`). `Run.hints` holds what the person said, each with its turn: this branch's, and
those the turns it keeps were made under. Report, figures, replay check, code map, routines and export read it as
any chain. The chain it left is not touched.

**What a turn carries.** Each working turn keeps what the loop carried out of it (`Turn.carry`): its number, what
it handed to the next prompt, what was spent by then, the failed cells in a row. The loop of a branch takes up from
the kept turn's carry (`Session.go_on`, `_loop`). So going on without a hint gives the very prompt the first run
had at the next turn: that is the suite's test of it. A turn with a carry can be gone on from (`branch_points`):
every working turn, not the report, not a question to the person. A run made before 0319 has none.

**Limits.** The branch runs under the limits and in the mode of the run it goes on from. The kept turns count as
used: the turn numbers go on, and so does what was spent. The person pays for the new calls only: the kept turns
make none. A review due before the next turn is made again, with the hint; a review among the kept turns is kept.

**The prompt.** The hint stands in every prompt from the next turn to the report, above the task line
(`hint_block`), and the contract gains a section, *A hint from the person* (`analyst/contract_hint.md`). The
reviewer and the figures step are given it too. A branch of a branch carries both hints where it goes on from a
turn made under the first; from a turn the first branch kept - the one it went on from included - it carries its
own alone. The Analyst sees the turns kept and the hint, and nothing of the turns that were left.

**The kernel** (`BambooAI._kernel_at`; before the new chain is announced). The kernel goes back to the state
after the last cell kept (§3); with no cell kept, to the state the chain started from. Where it is gone, or holds
another frame, or had to run cells again to get there and one printed something else, a fresh kernel runs the
earlier chains' cells again, then the kept ones (`replay.again`). A kept cell that printed something else is
marked (`Turn.kept == "differs"`): the branch's record takes the new output and results, the Analyst reads under
the cell's header that it was run again, and a branch of that branch keeps the mark. A cell that fails when run
again leaves no state to go on from: the person is told which, and nothing starts.

**The host and the route.** `pd_agent_converse(chain_id=<the chain>, after=<the turn>)`, the text typed being the
hint; `/query` takes `branch: {turn}`. A branch takes these and nothing else of a request: it starts no brief and
marks no proposed question. Refused, with a sentence for the person: an analysis that is running, one asked about
a plot, one from before 2.9 or a routine's run, a turn that cannot be gone on from (a request that names none
included), other data loaded, no hint. A stopped analysis can be gone on from. The Architect is not called. The
page is sent the new chain with `branch_of` and `branch_turn`, the run's card with the branch and its hint, and
the kept turns' cards first, each marked `kept`; the closing card's time is that of the branch's own turns.

## 5. The page (0320, built)

`web_app/static/js/branch.js`, with the left pane (`stream-pane.js`) and the thread map's drawing
(`workflowGraph.js`).

**The Turn map.** Its button, the Git branch mark, stands on the left pane's strip beside the count of turns, once
the run has ended with turns to go on from (`turn_map` on the closing card; a stopped run now has a closing card
too). Beside the mark is the number of branches the analysis has. The map opens in the thread map's drawer: every
turn of the analysis and of its branches is a box, joined to the turn it follows. A box says what the turn did,
and under that its number and its cell (*Turn 5 · In [4]*), or that the cell failed, or what else the turn was. The
first turn of a branch carries the mark *hint*. The way to the turn on screen is lit. Under the pointer the
drawer's foot says what the turn did, the hint its branch was given, how many ways the analysis went on from it
and what its cell printed. The map does not open while an analysis runs.

**Going back.** A click on a turn shuts the map. The left pane ends at the turn: the cards after it are hidden by
a rule of the page's, and the chain's own markup is not touched. The right pane stays. The composer takes the
hint: its words ask for one, and the row under it says *From turn 4 · 11 turns left* in the place of the mode,
the Architect's switch and the files. The cross on that row, Escape in the composer, or another chain coming on
screen leaves the turn. A turn that ended its chain - the report, a question to the person - brings the chain
back whole. The turn a run was stopped in ended nothing: it has no box.

**The hint sent.** With a turn gone back to, what is typed is the hint: `/query` gets `branch: {turn}` with the
chain on screen, and the Architect is not asked. The new chain is its analysis's from the first moment: its entry
keeps `branch` ({of, turn, hint}), its question is the analysis's, and it attaches where the analysis did. Its
left pane shows the turns kept first - faint, shut, marked *kept*, a cell that printed something else when it was
run again saying so - then a row with the hint (*From turn 4*), then its own turns. A framed analysis's branch has
the brief's fold and its Brief tab. Where the server starts no branch, nothing of the request stays: the chain is
back at its turn, the hint is in the composer again, and the server's sentence is shown.

**Moving between branches.** On the map a turn on the way of the chain on screen keeps that chain; a turn of
another branch brings that branch on screen, tabs and pane.

**The thread map and the arrows** count analyses. A box, or a step of the arrows, is an analysis, shown as the
chain of it that was last on screen (the newest where none was). The box says how many branches it has; a chain
asked from a branch hangs under its analysis's box.

**The icon.** The Git branch mark is on the Turn map's button and on the conversation map's; the thread map keeps
its own.

**Until 0321.** A saved thread opened again shows a branch as a chain of its own: what is stored does not say yet
which chains are branches.

## 6. To build

- **Save, memory, usage (0321).** Decisions 2, 13 and 14.
- **Open.** A hint that departs from what the brief fixes: nothing says which holds. A run that failed has no
  closing card, so no Turn map, though the engine could go on from its last turn.

## 7. The build

| Patch | What | State |
|---|---|---|
| 0318 | The kernel keeps its state after every cell and goes back to any; executor image v75; cloudpickle. | built |
| 0319 | Engine: a branch after a turn, with a hint. | built |
| 0320 | Page: the Turn map, going back, the hint, moving between branches; the Git branch icon. | built |
| 0321 | Save, memory, usage. | |
| 0322 | Release 2.9.0. | |

## 8. Tests

`tests/analyst/test_kernel_snapshots.py`: the kernel on its own, through the executor's service, through the
client, and the record. `tests/analyst/test_app_path.py` (0318): the host's use of the states; (0319) a branch
through the instance - the kernel going back, the cells run again, the marks, what is refused. `test_analyst.py`:
a cell's record; (0319) the branch in the engine - the carry, the prompt that is the first run's, the hint, the
reviewer, the kept turns' events; (0320) the closing card's `turn_map`, a stopped run's card.
`tests/analyst/test_branch.js` (0320): the page's part on the mini DOM - the left pane of a branch, the Turn map,
going back, the hint sent and the branch the server did not start, the analyses the arrows and the thread map
count. The walk (`tests/e2e/test_stack.py`): a chain asked from an earlier chain; (0320) branches in a browser -
the Turn map, going back, a hint sent from a turn whose state the kernel holds and from one it must rebuild,
moving between branches, the thread map and the arrows, a branch the server does not start, a request that names
no turn, and a branch of a framed analysis with the Architect switched on.
