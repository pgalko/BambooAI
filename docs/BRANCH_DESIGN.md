# Branching an analysis — design v0.10 (2026-11-21; released as 2.9.0, 0326; 0327, the maps in one place; built: 0318, the kernel's states; 0319, the engine; 0320, the page; 0321, save, memory, usage; 0322, the code map of a branch; 0323, the button on a turn's card; 0324, the maps' names and their one head; 0325, the button on the Architect's cards)

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
6. The map works as the Workflow map and the Pathfinding map do: hover to read, click to go, type to branch.
7. The map is the **Analysis map** (the *Turn map* until decision 17). The Git branch icon is the branch
   buttons' on the cards (it was also on the buttons to this map and to the Pathfinding map, until decision 18).
8. Going back moves the left pane only. The right pane keeps the result, so the person looks at the figure while
   they write the hint.
9. A hint is required.
10. The brief stays: a branch of a framed analysis runs under the same brief.
11. The earliest place to go on from is after turn 1, the latest the turn before the report.
12. The Workflow map and the chain arrows count analyses, not branches.
13. Memory takes the branch the person saved from or went on from. A branch they left is stored for the map only.
    The hint is kept with its branch, and memory shows it.
14. The person pays for the new turns only.
15. A hint outranks the brief (2026-11-21): where it departs from what the brief fixes, the hint holds, and the
    report says where it departs.
16. A run that failed gets no Analysis map (2026-11-21).
17. The maps' names (2026-11-21): the **Workflow map** shows a thread's chains (it was the *Thread map*), the
    **Analysis map** an analysis's turns (the *Turn map*), the **Pathfinding map** the steps that made a brief (the
    *Conversation map*, then the *Brief map* until decision 18). The three have one head, on one line. Nothing
    stands over the map.
18. The maps have one way in (2026-11-21): the button on the left bar, **Maps**, opens one drawer, and a switch in
    its head goes between the Workflow map and the two maps of the chain on screen, Pathfinding and Analysis. The
    buttons that opened a map from above an analysis and from the Brief tab are gone; the branch buttons on the
    cards stay. The Code map is no map of this kind and keeps its own ways in.

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

`web_app/static/js/branch.js`, with the left pane (`stream-pane.js`) and the Workflow map's drawing
(`workflowGraph.js`).

**The Analysis map** is a level of the maps drawer (*The maps in one place*, below). Every turn of the analysis and
of its branches is a box, joined to the turn it follows. A box says what the turn did, and under that its number and
its cell (*Turn 5 · In [4]*), or that the cell failed, or what else the turn was. The first turn of a branch carries
the mark *hint*. The way to the turn on screen is lit. Under the pointer the drawer's foot says what the turn did,
the hint its branch was given, how many ways the analysis went on from it and what its cell printed. The map can be
shown once the run has ended with turns to go on from (`turn_map` on the closing card, which marks the row of the
ids, `data-branch`; a stopped run has a closing card too), and not while an analysis runs. Until 0327 a button at
the end of the row of the ids opened it (0321).

**Going back.** A click on a turn shuts the map. The left pane ends at the turn: the cards after it are hidden by
a rule of the page's, and the chain's own markup is not touched. The right pane stays. The composer takes the
hint: its words ask for one, and the row under it says *From turn 4 · 11 turns left* in the place of the mode,
the Architect's switch and the files. The cross on that row, Escape in the composer, or another chain coming on
screen leaves the turn. A turn that ended its chain - the report, a question to the person - brings the chain
back whole. The turn a run was stopped in ended nothing: it has no box.

**The button on a turn's card** (0323; the product owner, 2026-11-21: to branch without looking for the turn on the
map). Every turn the analysis can go on from has a button in the head of its card in the left pane, the Git branch
mark, before the button of its prompt: the turns a branch kept too, not the report's card or a card that is no turn. A
click is a click on the turn's box of the map - the pane ends at the turn, the composer takes the hint - and its
button is lit; a click on the lit button brings the end back. `BranchUI.dress` puts the buttons into a pane whose
run ended with turns to go on from: when its run ends, and when a chain kept from before the button existed comes
on screen.

**The hint sent.** With a turn gone back to, what is typed is the hint: `/query` gets `branch: {turn}` with the
chain on screen, and the Architect is not asked. The new chain is its analysis's from the first moment: its entry
keeps `branch` ({of, turn, hint}), its question is the analysis's, and it attaches where the analysis did. Its
left pane shows the turns kept first - faint, shut, marked *kept*, a cell that printed something else when it was
run again saying so - then a row with the hint (*From turn 4*), then its own turns. A framed analysis's branch has
the brief's fold and its Brief tab. Where the server starts no branch, nothing of the request stays: the chain is
back at its turn, the hint is in the composer again, and the server's sentence is shown.

**Moving between branches.** On the map a turn on the way of the chain on screen keeps that chain; a turn of
another branch brings that branch on screen, tabs and pane.

**The Workflow map and the arrows** count analyses. A box, or a step of the arrows, is an analysis, shown as the
chain of it that was last on screen (the newest where none was). The box says how many branches it has; a chain
asked from a branch hangs under its analysis's box.

**The icon.** The Git branch mark is the branch buttons', on a turn's card and on the Architect's.

**The maps' names and their head** (0324; the product owner, 2026-11-21: the head was misaligned and the three names
did not say what each map is of). The drawer holds one of three maps (decision 17) and has one head for them, on one
line (`index.html`, `shell.css`), with zoom - out, the level, in, fit - a line, full screen, and the close.
Zoom and full screen were in the map's corners, over the drawing: `workflowGraph.js` puts them into the head each
time a map is drawn, and a map with nothing on it has neither. The full-screen button says what a click does, also
on a map drawn again while the drawer is over the page. What a click and the pointer do is said in the drawer's foot,
until a box is under the pointer (*Click a turn to go back to it. Hover over one to see what it did.*). The small
grey text of the drawer is one shade lighter than it was.

**The maps in one place** (0327; the product owner, 2026-11-21: four things called a map opened from four places,
and it was hard to remember which was where). `web_app/static/js/maps.js` is the drawer's one way in, and its head is
a switch (decision 18):

- **The way in.** The button on the left bar, *Maps*, and Ctrl/Cmd+M open the drawer and shut it. It opens on the
  map it was left on, Workflow the first time.
- **The switch.** *Workflow*, then the chain on screen by its place in the thread (*Chain 2*), then that chain's
  two levels as one control: *Pathfinding* and *Analysis*. Each level has the number of boxes on its map, and says
  in words what the map holds under the pointer (*3 chains · 1 branch*, *5 steps · 1 branch*, *11 turns · 2
  branches*). The left and right arrow keys go round the levels while the drawer is open, unless the focus is on
  something outside it.
- **A level that cannot be shown** is greyed and says why under the pointer: *Chain 1 was asked without the
  Architect*; *Chain 1's brief was made before version 2.8.1* (it keeps no steps); *The Architect is replying*;
  *Chain 1 has no turns to go back to*; *An analysis is running*. With no chain on screen - a new thread, a
  routine's run - the switch is Workflow alone.
- **Following.** The drawer shows what is on screen: when another chain comes on screen, or the one there changes,
  the map is drawn again. On a level the chain now on screen does not have, the drawer goes to the Workflow map and
  stays there. An analysis that starts shuts the drawer: it lies over the pane the run is shown in.
- **Clicks.** A chain's box on the Workflow map brings the chain on screen and leaves the drawer open, so its other
  maps are one click away. A step or a turn clicked shuts the drawer, which lies over the pane the person then
  works in.
- **In the code.** A level is what its module gives the drawer when asked - how many boxes, that in words, why it
  cannot be shown, and its drawing: `workflowMap()` (`workflow-management.js`), `ArchitectUI.map` and
  `BranchUI.map`. The drawer says which level it holds in `data-level`. `MapsUI.follow()` is called at the end of
  the page's hook for a chain on screen, when a brief is drawn again, when a turn is gone back to or left, and when
  a routine's run comes on screen. A pane or a Brief tab kept by an earlier build still has its button to a map in
  its markup: the button is hidden, and in a pane it still says the analysis can be gone on from.
- **The drawer** is 560 px wide (520 until then): two digits on every level fit beside the tools, and the chain's
  name gives way first should a number ever be longer.
- **Found on the way.** The wheel with Ctrl or Cmd zoomed by one step for every time a map had been drawn in the
  drawer, the frame having kept a handler for each drawing; it has one now.

## 6. Save, memory, usage (0321, built)

**Save** (decision 2). A thread saved as a favourite stores every chain of it, so every branch. Opened again, the
page is told which chains are branches from the thread's record (`/load_thread`: `branch` of each chain - the chain
and the turn it went on from, and its hint), so the analysis has its branches, its Analysis map and its place on the
Workflow map as when they were made. Nothing is locked: a turn of a saved thread is gone back to as any, the data it
ran on loaded; the kernel is a new one, which runs the kept cells again (§4). The new chain is stored at the next
save.

**Memory** (decision 13; `analyst/memory.py`). Where an analysis went on more than one way, memory takes the ways
the person saved from (the chain on screen at a save: *picked*) and the ways they went on from (a later question
was asked from them); where there is neither - the thread was saved from another analysis - the newest. The other
ways are saved for the page's map only: they are no memory, and are counted as `left`. A way that is alone among
those memory can read is memory as any run is. A run in the view carries `hints`: what the person said, each with
its turn. A hint is read with the question wherever a saved run is read - by the reader's second model, by the
Analyst that opens a saved analysis, in the dialog that shows one - a quote can stand in it (`hint`), and plain
search counts a word of it as a word of the question.

**Usage** (decision 14). The person pays for the branch's own calls: the kept turns make none. The usage ledger's
line of a branch (`notebook.run_facts`) counts its own turns - cells, figures, the time from its start - and says
after which turn it went on, and the hint (`branch`: {turn, hint}). The Usage dialog shows the turn on the branch's
row and the hint under its question.

**Read afterwards.** A branch's hints are part of what the person asked, so whoever is told its question later is
told them too, a line each under the question (`notebook.hint_lines`): the Analyst of a later question of the
thread - in the ledger's line of the chain, and in the chain opened whole (`SHOW RUN`) -, the Architect that frames
one (`EARLIER`), memory's reader. What a hint names - a file, an address - counts as asked for in the reach record,
on the branch and on a question asked from it.

## 7. The code map, the Investigation tab, the hint over the brief (0322, built)

**Why.** A branch's record holds the turns it kept and then its own, so that the report, the replay check, the code
map and the export read it as any chain (§4). The code map of the first live branch of a branch (the product owner,
2026-11-21) was right - every row, number and *replaced by* mark checked against the run log - and did not say it
was a branch: the Analyst's words in its rows spoke of "the hint", and the map showed none; the steps it kept looked
like its own; and its header numbered it "chain 3" where the arrows count one analysis.

**The code map** (`analyst/codemap`, version 4; `docs/CODEMAP_DESIGN.md` §3, §6). The record of a branch says which
cells and failed attempts it kept (`kept`; `differs` for a kept cell that printed something else when it was run
again), each hint as an event at the turn it was given after, the turn the run went on after (`branch`) and how many
turns it kept. The view: a kept step says *kept* under its turn and in its panel; a hint has a row of its own where
the person gave it - after what ran up to its turn, before what was made under it; the header says *branch from turn
N*, and the line of facts *11 turns, 5 kept*. A chain's number is the one the arrows show (`BranchUI.place(entry)`):
a branch has its analysis's. A chain that is no branch has a map as before; a map of an older version is built again
when it is opened.

**The Investigation tab** (`render.notebook_html`). The notebook view of a branch is of its whole way too: a cell it
kept says *kept* in its head, and each hint stands in a row - *Your hint* - after the turn it was given after.

**The hint over the brief** (decision 15). Read only by a run that has both. The contract's hint section gains a
line (`HINT_OVER_BRIEF`): where the hint departs from what BRIEF fixes, the hint is what is computed, and the report
says where it departs. The reviewer is told the same with the hint (`REVIEWER_HINT_OVER_BRIEF`). The step that draws
the figures is given the agreed figures under a heading that says the hint holds where it asks for another drawing
(`FIGURES_AGREED_HINT`); a reply that leaves an agreed figure out is still asked again once, told that a figure the
hint takes out stays out (`FIGURES_LEFT_OUT_HINT`), and the report names an agreed figure that was not drawn, as
before.

## 8. The build

| Patch | What | State |
|---|---|---|
| 0318 | The kernel keeps its state after every cell and goes back to any; executor image v75; cloudpickle. | built |
| 0319 | Engine: a branch after a turn, with a hint. | built |
| 0320 | Page: the Analysis map, going back, the hint, moving between branches; the Git branch icon. | built |
| 0321 | Save, memory, usage; the Analysis map's button at the end of the ids' row. | built |
| 0322 | The code map and the Investigation tab of a branch; a hint outranks the brief. | built |
| 0323 | The branch button on a turn's card. | built |
| 0324 | The maps' names - Workflow map, Analysis map, Brief map - and one head for the three. | built |
| 0325 | The branch button on the Architect's cards, as on a turn's card (docs/ARCHITECT_DESIGN.md §2.25). | built |
| 0326 | A correction of a result marks the line it replaced, not every line of its cell (docs/CODEMAP_DESIGN.md §4). Release 2.9.0. | built |
| 0327 | The maps in one place: one button, one drawer, a switch between Workflow and the chain's Pathfinding and Analysis. | built |

## 9. Tests

`tests/analyst/test_kernel_snapshots.py`: the kernel on its own, through the executor's service, through the
client, and the record. `tests/analyst/test_app_path.py` (0318): the host's use of the states; (0319) a branch
through the instance - the kernel going back, the cells run again, the marks, what is refused. `test_analyst.py`:
a cell's record; (0319) the branch in the engine - the carry, the prompt that is the first run's, the hint, the
reviewer, the kept turns' events; (0320) the closing card's `turn_map`, a stopped run's card.
`tests/analyst/test_branch.js` (0320): the page's part on the mini DOM - the left pane of a branch, the Analysis map,
going back, the hint sent and the branch the server did not start, the analyses the arrows and the Workflow map
count. The walk (`tests/e2e/test_stack.py`): a chain asked from an earlier chain; (0320) branches in a browser -
the Analysis map, going back, a hint sent from a turn whose state the kernel holds and from one it must rebuild,
moving between branches, the Workflow map and the arrows, a branch the server does not start, a request that names
no turn, and a branch of a framed analysis with the Architect switched on. (0321) `test_analyst.py`: a branch's hints
as a later question's Analyst, the Architect and the reach record are given them; `test_memory.py`: the ways memory
takes and the ways left, a run's hints, search; `test_reader.py`: the hint in what is read of a run; `test_usage.py`
and `test_usage_page.js`: a branch's facts and its row; the walk: a thread saved from a branch, the memory view after
it, the saved thread opened again with its branch, a branch more made from it, and a branch in the Usage dialog.
(0322) `test_code_map.py`: a branch's record and its rows - the kept steps, the hints in their places, the header;
`test_code_map.js`: the same on the page, and a chain's number as the arrows count it; `test_analyst.py`: the hint
over the brief in the contract, the reviewer's prompt and the figures step, and the Investigation tab of a branch;
the walk: the code map and the Investigation tab of a branch in a browser. (0323) `test_branch.js`: the button on
a turn's card - which cards have one, a click and a second click, a chain kept from before it; the walk: the buttons
in a browser, and a branch started from one. (0324) `test_branch.js`, now on the page's own drawer: the Workflow
map's head as the page's opener writes it, a thread with no chain; the head's buttons - where they stand, their
names, the zoom's level, full screen and a map drawn again meanwhile; `test_shell.js`: the head's markup and its
styles; the walk: the head of each of the three maps as a browser lays it out, and its buttons used. (0327)
`tests/analyst/test_maps.js`: the drawer's switch - what it says, a greyed level, where the drawer opens, how it
follows the chain on screen, the arrow keys and the focus, the page's hooks; `test_branch.js` and
`test_architect.js`: each level through the switch, a pane kept with the old button, the wheel; the walk: the three
maps of a framed analysis with branches from the one button, the keys, and no button above an analysis or beside
the Brief tab's arrows.
