# Branching an analysis — design v0.1 (2026-11-20; for 2.9; built: 0318, the kernel's states)

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
inside a library, or in the environment variables.

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

## 4. To build

- **The record of a branch (0319).** A branch is a chain of its own: a copy of the turns kept, then its own; it
  records the chain it left, the turn, and the hint. Report, figures, replay check, code map, routines and export
  read it as any chain. Each turn keeps what it handed to the next prompt, so the loop takes up exactly where the
  turn kept ended; a run keeps its limits.
- **The prompt (0319).** The hint stands in every prompt from that turn to the report, and the reviewer gets it. A
  branch of a branch carries both hints. The Analyst sees the turns kept and the hint, and nothing of the turns
  that were left. Where a cell kept had to be run again and printed something else, the turn is marked and the
  Analyst is told.
- **The page (0320).** The turn map in the thread map's drawer; going back; the hint in the composer, with the mode
  buttons and the Architect switch away; moving between branches; one box for an analysis on the thread map.
- **Save, memory, usage (0321).** Decisions 2, 13 and 14.

## 5. The build

| Patch | What | State |
|---|---|---|
| 0318 | The kernel keeps its state after every cell and goes back to any; executor image v75; cloudpickle. | built |
| 0319 | Engine: a branch after a turn, with a hint. | |
| 0320 | Page: the turn map, going back, the hint, moving between branches; the Git branch icon. | |
| 0321 | Save, memory, usage. | |
| 0322 | Release 2.9.0. | |

## 6. Tests

`tests/analyst/test_kernel_snapshots.py`: the kernel on its own, through the executor's service, through the
client, and the record. `tests/analyst/test_app_path.py` (0318): the host's use of the states. `test_analyst.py`:
a cell's record.
