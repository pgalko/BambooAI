# The Architect and memory from saved analyses — design v0.27 (2026-11-19; released as 2.8.0, 0305, then 0306, 0307, 0308, 0309, 0310, 0311, 0312, 0313 and 0314; built: the old memory retired, 0294; the brief in the engine, 0295, and on the page, 0296; the Architect talks, 0297, checks what the brief rests on, 0298, proposes other explanations, 0299, and proposes next questions, 0300; the memory view, 0301, its reader, 0302, memory in the Architect, 0303; the Analyst opens what the brief names, the brief in memory, the seats, 0304; the Architect as a tutor and the conversation in memory, 0306; the question the coach takes, what the Analyst gets, opening on request, 0307; one question that changes as the talk goes, the version on screen, the brief without empty parts, saved analyses to read, 0308; the figures sketched before the run, 0309)

Release 2.8 does three things.

1. It adds the **Architect**: an optional step before an analysis, in which the coach and a model frame the question
   together. It also proposes the next question after an analysis.
2. It gives the Architect a **memory made of the coach's saved analyses**.
3. It **removes the memory BambooAI had** (the knowledge pack). This part is built: §5.

Why. A good analysis has three parts: how the question is framed, the data, and the check of the result. BambooAI
covers the last two. A wrong frame at the start is not caught later: the result looks sound, and the coach builds on
it.

This document is the design as agreed with the product owner, and it grows with each patch (§7). A part is marked
**agreed**, or **proposed** where the detail waits for the first live runs. The design pictures it was agreed on are
in the product owner's hands; the page's own screens replace them as they are built.

## 1. Decisions (agreed)

| # | Decision |
|---|---|
| 1 | The Architect is optional. The coach chooses it for a question. |
| 2 | It works over several turns, until the coach is happy and starts the analysis. |
| 3 | It draws on the loaded data, the thread and its earlier analyses, attached documents, and memory. |
| 4 | It reads the data's description and makes basic lookups. It never does the analysis. |
| 5 | It hands the Analyst a condensed brief. The brief is binding. |
| 6 | Every version of the brief is kept. |
| 7 | Memory is reachable only through the Architect. The Analyst loses `RECALL`. |
| 8 | Memory is every saved run: saved by the coach, or saved when a routine was made. |
| 9 | Deleting a saved workflow removes it from memory, and its thread. |
| 10 | Memory reading is a multi-step process: a model works through the saved record and can call a model on its parts. The coach waits while it runs. |
| 11 | The memory BambooAI had is retired completely. No remnants. |
| 12 | The rating step is dropped. |
| 13 | All of this ships as one release. |
| 14 | The ideas taken from the study of how experts make sense of a situation are in scope (§2, §6). |
| 15 | The screen: the conversation in the left pane, the brief on a tab in the right pane. |
| 16 | The sapling moves into the Architect, as its quick follow-up designer. Everything about formulating a question is in one place. |
| 17 | The coach can change the Architect's results in place, to save a turn. |
| 18 | Next questions keep their five levels. The sapling button leaves the question box and sits in the left pane. |
| 19 | On a follow-up through the Architect, saved analyses are looked up only when the coach asks. *Reversed by decision 34.* |
| 20 | The five candidate questions are kept with the analysis they follow. |
| 21 | A lookup may count, list or total what is there, to check an anchor. It may not compare, model or test. |
| 22 | What the Architect proposes, and each saved analysis it finds, stays unticked until the coach accepts it. *For saved analyses, replaced by decision 40.* |
| 23 | A candidate question runs straight from its card: the coach picks one, or changes it slightly, and runs it. A new analysis starts. |
| 24 | The thread map records a single box for it. Each Architect run is also a single box, however many turns it took, on follow-ups too. |
| 25 | An Architect run and the analysis it starts share one box. |
| 26 | Saved work in the old record format is left out. Memory starts from what was saved in the current format, and grows from there. |
| 27 | The memory defaults of §3.1: the three marks, runs added after a save, a single run removed, across athletes, what is not memory. |
| 28 | The Architect and the memory reader use the Analyst's model of the chosen tier. The reader's second model uses the fast model the Knowledge Distiller seat used. |
| 29 | The Architect talks as a tutor: it explains, suggests and offers choices, in no fixed order, never asks again what the coach could not answer, and stays for as long as the coach wants (2026-11-17, after the first live run; §2.16). |
| 30 | The question worked out in the conversation is said back. Once the coach agrees, that wording is the run's question (§2.16). |
| 31 | The conversation of a saved analysis is memory, with its brief and its report (§3.9). |
| 32 | The question is the coach's to take. The Architect gives a wording; it becomes the question by the coach's click or their word, never by the model's own writing. This replaces how decision 30 was built (2026-11-17, after the second live run; §2.17). *Replaced by decision 37.* |
| 33 | The Analyst is given what was agreed and nothing else: no line for a part the coach did not state, and the three standing checks only where the run has data (§2.17). |
| 34 | The Architect has the saved analyses read on a follow-up too. Whatever it asks for that cannot be done, it is told at once, so that no message says a thing is under way that is not (§2.17). |
| 35 | A follow-up's brief starts from what the last answer was for and what the coach thinks. Only an answer to the Analyst's own question starts from the whole brief (§2.17). |
| 36 | The Architect opens a part of an analysis the question follows on request - its report, a cell, the conversation - and reads it until the coach next speaks. Its prompt carries a line to each cell, not the work (§2.17). |
| 37 | What the Brief tab shows is what the Analyst gets. The question changes as the conversation goes: the Architect words it, and its wording is the question at once, as one more version. Nothing waits to be taken (2026-11-17, from the product owner's test of 0307; §2.18). |
| 38 | The version on screen is the one in use. The arrows step through the versions; an answer, a change and Start analysis all go on from the one shown (§2.18). |
| 39 | The brief shows the parts that hold something, and no other. One control adds a part (§2.18). |
| 40 | A saved analysis is chosen by answering the Architect, a whole analysis at a time. What a reading found is shown to read, in both panes; nothing is ticked (§2.18). |
| 41 | A figure the coach asks to see is a part of the brief. The Architect describes it and the Brief tab shows it (a sketch in 0309, a draft since 0310); nothing has to be accepted. Three at most; changed by saying so, taken out with a cross (2026-11-18, the product owner's idea after testing 0308; §2.19). |
| 42 | A figure without a draft is a grey window with one line: a draft is on its way, none could be drawn, or none was yet. Nothing else stands in a figure's place (§2.20; 0311, from the product owner's live test of 0310: "a little too busy". The sketch of 0309 is gone, as its rough points went in 0310 - what a model writes down is no shape, and a stand-in drawn from a description looked like nothing). |
| 43 | The Analyst and the step that draws read the agreed figures in words, and the step draws them first, under their titles. Code holds the titles: a reply that leaves one out is asked again once, and the report says where one was not drawn (§2.19). |
| 44 | A figure of the brief is shown as a draft before the run: a model writes one cell, it runs where no data is, and the Brief tab draws the plot. A shape that follows from a rule alone is computed; any other is drawn on made-up numbers, and marked so. In doubt, made up (2026-11-18, from the product owner's test of 0309; §2.20). |
| 45 | The draft's cell is given no data, is screened before it runs and is stopped after a few seconds. A draft never fails the exchange: the reply stands, and the figure's window says that no draft could be drawn (§2.20). |
| 46 | The step that draws is given the cell that drew the draft and draws the agreed figures as it did, from the run's own values. Beside the agreed figures it may add two of its own (§2.20). |
| 47 | Where the brief builds on a saved analysis, its code is given to the model that writes the draft. What it drew is not shown: 0310 put the picture its favourite keeps under its line, and the product owner took it out after his live test (0311; §2.20). |
| 48 | A row of the conversation that is in flight says what is being done: *SEARCHING MEMORY*, *DRAWING A DRAFT*. Done, it is named for what it is about: *MEMORY*, *FIGURES* (0311: *SAVED analyses* read as something saved, and *FIGURES* said nothing of what was happening; §2.20, §3.7). |
| 49 | How the Architect described a figure - its kind, its axes, its note - is for the model that draws and for the Analyst. The page shows the figure's title and its draft (0311; §2.20). |
| 50 | The Answer is what goes to other people, so it says nothing that only a reader of the brief can place. What the report says against the brief is shown at the foot of the run's Brief tab, under *How it turned out*, and not in the Answer or its export (0312, from the product owner's live test: the Answer "could be shared via PDF with third parties not familiar with the mechanic"; §2.21). *Did not fit* stays in the Answer: it reads as a finding. |
| 51 | The question is written for the Analyst, who was not in the conversation. It says what is to be done and on what, in two or three sentences, and points to nothing the Analyst is not given: the question, the brief, the data, the analyses the question follows, and of the saved analyses those the brief builds on. How a figure is to look is the figure's to say (0313, from the product owner's live run: a question that pointed to an analysis of another day; §2.22). |
| 52 | Before an analysis starts, its question is read by a model that is given what the Analyst will be given, and nothing else. The words it cannot place go back to the Architect, which words the question again; the coach sees it, and starts again. A read holds a start up once, and a read that cannot be made holds nothing up (0313; §2.22). |
| 53 | The closing card of a run says the run's numbers beside its title, and offers what can be done next as two buttons alike: *Next questions* and *Code map*. It links to no tab: the tabs are there to click (0313, the second of three mockups, the product owner's choice; §2.23). |
| 54 | Next questions are a panel inside the closing card, not a list that drops over the page. The panel says what the questions are and what each of the five ways does, a sentence each, in the words of what the Architect is told to do at that way. The questions of the way picked take the list's place, in rows of the same look. The row a run opens on says the way and not what the question came from (0314, the first of three mockups, the product owner's choice: "very little explanation what the feature does, what the options mean", and of *From did not fit* on the run's row: "What does from did not fit even mean"; §2.24). |

## 2. The Architect

### 2.1 What it is for (agreed)

To make the coach's frame visible and testable before the analysis runs.

- It does not look for the coach's biases.
- It is not a general checklist. Its questions come from this athlete, this data and these saved analyses.
- It does not answer the question. That is the Analyst's work.

### 2.2 The brief (agreed)

What the coach and the Architect produce, and what the Analyst receives.

1. **Decision.** What the coach will do differently depending on the answer.
2. **Question.** In the coach's words.
3. **What the coach thinks** is going on.
4. **What it rests on.** Three or four anchors. Each has a source (the coach, the data, a saved analysis, the last
   result) and a mark: holds, does not hold, cannot be checked.
5. **What the coach expects** to see, and what would change their mind.
6. **Also check.** At most two rival explanations, each with what it would show. Chance, measurement error and how
   the sessions were picked are always checked.
7. **Fixed before the run.** The comparison, the measure, the period.
8. **Saved analyses** that bear on it: a pointer to the exact run, the exact passage, its data and period.
9. **Set aside.** Anchors considered and dropped.

Rules:

- Each version records what changed and why. (agreed)
- What the Architect brings in is marked as its own. (agreed)
- Everything in the brief was said or accepted by the coach. A proposal from the Architect enters with one click.
  (agreed)
- A part the coach leaves empty is left to the Analyst, and the brief says so. (proposed)
- An earlier result enters as a claim to test, never as a fact. (proposed)

### 2.3 The conversation

*Changed on 2026-11-17, after the product owner's first live run: the fixed order and the two-sentence message
made the Architect a form to fill in. It talks as a tutor now (decision 29, §2.16). What follows is the design as
it was first agreed.*

Agreed:

- The coach states their frame first. Data lookups and memory come after.
- One frame, at most two rivals. No long list of angles.
- The first question is what the coach will do differently depending on the answer.
- At any point the coach can answer, change the brief in place, or start the analysis.

Proposed:

- The Architect first fills the brief from what the question already says. Then it asks only for what is missing.
- One question in a message. Two sentences at most. Choices to click where it can offer them.
- Order: the decision, why the coach thinks so, what they expect to see. Then one check against the data and the
  saved analyses. Then the Architect says what did not hold and offers rivals.
- A follow-up question typed with the Architect on starts from the previous brief and from what did not fit in the
  earlier reports. Saved analyses are looked up only when the coach asks.

### 2.4 What a lookup may do (agreed)

A lookup checks an anchor. It may count, list or total what is there: which columns, which period, how many
sessions, where the gaps are, hours a week. It may not compare, model or test. Anything more goes into the brief for
the Analyst.

Built: §2.13.

### 2.5 Handing over

- The Analyst receives the approved brief in place of the bare question. (agreed)
- Binding means: the Analyst follows it. Where the data makes that impossible, it stops and asks. (proposed reading)
- The report gains two parts (agreed in substance, names proposed):
  - **Against the brief.** What was expected: met, not met, or cannot tell. Each "also check" with its result.
  - **Did not fit.** Results the frame does not explain.
- The brief is stored with its analysis. When the analysis is saved, the brief is saved with it. (proposed)

The engine's side of this is built: §2.10.

### 2.6 Changing the brief in place (agreed, details proposed)

- Every line the coach or the Architect wrote can be changed where it stands: a pencil, then keep or cancel.
- A change makes a new version, marked as the coach's. No model is called.
- A changed anchor loses its mark until it is checked again.
- A fact from a lookup and a passage from a saved analysis cannot be changed. They can be left out.

### 2.7 Next questions: the sapling in the Architect (agreed; built in 0300, §2.15; a panel in the card from 0314, §2.24)

How the sapling worked until then:

- A plant button beside the question box, live once a thread has an analysis. Hovering shows five levels: refine
  focus, shift angle, test boundaries, blend elements, follow emergence.
- A click makes one model call over the data's description and the thread's earlier analyses. It returns five next
  questions at that level.
- They appear on an Explore tab as five cards. A card can be edited in place, and a click runs it as the next
  analysis.
- The five questions are recorded as a chain of their own, so the thread map shows a fork and which questions were
  run.

What changes (agreed):

- The plant button leaves the question box. A **Next questions** button sits on the closing card of a finished
  analysis, in the left pane.
- The five levels stay. The button opens them, and the coach picks one.
- The five questions at that level appear as cards under the closing card, in the same pane. The answer stays in
  view on the right. Each card can be changed, or run at once.
- The coach picks a card and runs it, or changes it slightly with its pencil and runs it. The arrow starts a new
  analysis at once.
- There is no brief and no Start analysis on this path. The Architect's switch applies to questions the coach types.
  A candidate is run as it stands.
- The candidates are kept with the analysis they follow, not as a chain of their own. A candidate that was run is
  marked on its card.

Proposed, and built as §2.15 says:

- Each level reads its own part of the brief and the report, and each question says what it comes from:

  | Level | Reads |
  |---|---|
  | Refine focus | what was fixed before the run: the measure, the split, the period |
  | Shift angle | the rivals: other explanations of the same result |
  | Test boundaries | what it rests on: anchors that did not hold or could not be checked, and the conditions |
  | Blend elements | two findings of the thread, joined |
  | Follow emergence | what did not fit |

- In the button's list each level has one plain line beside its name.
- Where a thread has no brief, the questions come from its earlier analyses and the data, as before.

What goes: the Analyst's ideas path and the Explore tab.

### 2.8 The screen (direction agreed)

- **Left pane: the conversation.** The coach types where they type today. The Architect's messages and the coach's
  answers follow each other. Its checks show as rows with live counts ("reading 17 of 42"), and can be skipped. Next
  questions show here as cards.
- **Right pane: a Brief tab.** The brief fills in as the conversation goes. It shows marks on the anchors, a tick on
  what to include, a pencil on what can be changed, a version stepper, and **Start analysis** at the foot.
- **The switch.** A button named Architect beside the mode control. It stays as set.
- **Next questions.** A button on the closing card of a finished analysis. The plant button leaves the question box.
- **During the analysis** the conversation folds into one row. The Brief tab stays.
- **After the analysis** the Answer tab shows *Did not fit*, and the Brief tab how the result stands against the
  brief (0312, §2.21; until then the Answer showed both).
- **One way to change and one way to go, on each path.** In an Architect run: the pencils in the brief, and Start
  analysis. On a candidate question: the pencil and the arrow on its card. The two are never on screen for the same
  question.

### 2.9 The thread map (agreed)

One box per question.

- A question the coach types is one box, as today.
- An Architect run is one box, made when the run starts, however many turns it takes. The analysis it starts is in
  the same box. A run that starts no analysis keeps its box, marked *not run*.
- A follow-up through the Architect is a box of its own, under the analysis it follows.
- The five candidates are not a box. A candidate that is run is one box, under the analysis it follows.
- A box says how its question was made: *Architect* or *next question*.

### 2.10 The brief in the engine — built (0295, 2026-11-15)

The engine takes a brief with a question, holds the Analyst to it, keeps it with the run, and reads back what the
report says against it. Nothing on the page sends one yet: that is 0296.

**The record.** `analyst/brief.py`. A brief is a plain dict on the run (`Run.brief`), every part optional:
`decision`, `thinks`, `rests_on` (lines, each with a `source` - person, architect, data, saved, result - a `mark` -
holds, does not hold, cannot be checked, or none - and an optional `note`), `expects`, `would_change`, `also_check`
(lines, each with what it `shows`), `fixed` (`comparison`, `measure`, `period`), `saved`, `set_aside`, with the
`version` the coach approved and the `question`. `normalise()` brings what a caller sends into that shape and
bounds it; a brief with nothing in it is no brief.

**What the Analyst reads.** Under QUESTION, every turn, a BRIEF block (`render()`): each part on its line. A line the
frame rests on says what it is worth: checked against the data and what the check found, cannot be checked, an
earlier result - a claim to test - or the person's word. The three standing checks follow the coach's own under
Also check. A part of what is fixed that the coach left empty reads "left to you"; a part of the frame they did not
state reads "not said". *Since 0307 a part the coach did not state has no line, and the standing checks are listed
only for a run on data (§2.17).*

**The rules.** The contract gains a section, The brief (`analyst/contract_brief.md`), only when the run has one.
Without a brief the contract, the reviewer's prompt and every prompt of the run are what they were, byte for byte.
Five rules: the decision is what the answer is for; what is fixed is what is computed; what it rests on is a frame,
not evidence; every Also check line is tested; and where the data cannot give what is fixed - the measure is not
recorded, the period is not covered, a side of the comparison is empty - the Analyst puts nothing else in its place
and asks (`ASK`), saying what is missing and what the data would allow.

**Stop and ask.** A run that ends on the Analyst's question keeps its brief. The coach's answer starts the next run
under the same brief, without it being sent again: the block says it was agreed before the question, and that the
answer stands where the two differ. A brief sent with the answer replaces it.

**The report.** Two parts under fixed headings, after the answer. `## Against the brief`: a line `Expected:` with
met, not met or cannot tell and the number that says so; a line `Would change their mind:` with seen, not seen or
cannot tell; then a line for each Also check line, with what it showed - or cannot tell and why. A part of the brief
the coach left unsaid has no line (0296: a brief written by hand has empty parts). `## Did not fit`: one result to a
line, or Nothing. The engine reads them back (`outcome()`) onto the run (`Run.brief_outcome`): whether the part is
there, the two verdicts, the checks, what did not fit. A report gets a line saying it does not say how the result
stands against the brief when the part is missing, or when the coach said what they expect and no verdict is given.
A number the brief states is the coach's own, so the report may repeat it without being marked unverified. The
plain-language version is asked to keep both parts under their headings.

**The reviewer** (Adaptive) reads the BRIEF block under the question, and its prompt says the analyst is held to the
brief: it judges the analysis against it and recommends no test that replaces what it fixes.

**The way in.** `Session.run(..., brief=...)` and `BambooAI.pd_agent_converse(..., brief=...)`. The web routes and
the page: §2.11.

### 2.11 The brief on the page — built (0296, 2026-11-15)

The brief's own screen, and the coach's changes by hand. What the Architect does in it is §2.12.

**The switch.** A button named Architect beside the mode control (`#architectSwitch`; the page's side is
`architect.js`). It stays as set for the browser session. It applies to a question typed in the composer and sent
from it. A next question, a question about a plot or a selection, and Synthesise run as before.

**A framing run.** A question sent with the switch on opens a run on the thread's record before any analysis
(`POST /architect/open`, `BambooAI.open_framing`): status `framing`, attached where the question was asked, with the
first version of its brief (`Run.framing`). A follow-up to a run that had a brief starts from that brief, and says
so. The page shows the run as a chain of its own: the question in the left pane under "Architect · brief v1", and
one tab, Brief. While it is on screen nothing else starts from it, and the composer is the conversation's (§2.12). A
brief not yet run is not saved with its thread.

**The Brief tab.** The question as the title. A stepper through the versions, with who made the one shown. Then the
parts in the brief's order: Decision, What you think, It rests on, You expect (with "You would change your mind
if"), Also check, Fixed before the run (Compare, Measure, Period). A part not said reads "not said yet"; a fixed
part reads "left to the Analyst". The three standing checks are one line marked "always". A line shows its mark and
the fact beside it when it was checked, and who brought it in when that was not the coach. *The tab as it is since
0307: §2.17.*

**Changing in place (§2.6).** A pencil on each line, a cross on a line of a list, "+ Add" under a list: at most four
lines under It rests on and two under Also check, the counts of §2.2. Enter or the tick keeps; Escape or the cross
cancels. Each change kept is one more version (`POST /architect/brief`, `BambooAI.save_brief`), marked as the
coach's, with the part it touched; the changed line carries a bar in that version. A changed line is the coach's own
and loses its mark. A fact from a lookup and a passage of a saved analysis have no pencil. An older version is read,
not changed. The question is changed like any line, and is kept whole: its lines, up to 4,000 characters, where a
line of the brief is one line of at most 600.

**Start analysis.** At the foot of the last version. The analysis continues the framing run (`/query` with
`run_id`): the same run on the record, the same chain on the page, one box on the map. It runs under the brief as
last kept, numbered with its version, and attaches where the framing run did. A brief is started once. On the page
the framing folds to one row above the run, and the Brief tab stays to be read (until 0313 the closing card linked
to it; §2.23). The tab's markup carries the versions, so a saved or restored chain still steps through them.
From 0313 the question is read first, as the Analyst will read it (§2.22).

**The report on the page.** The part *Against the brief* is not shown in the answer (0312, §2.21; from 0296 it was
a card there). It is a card at the foot of the run's Brief tab: a row for what was expected and a row for what
would change the coach's mind, each with its verdict, then a row for each check. A check line that says "cannot
tell" is marked. A part the rows cannot hold whole, such as a table, goes as the report wrote it. *Did not fit*
stays the report's own section, in the answer.

**The thread map.** A tag on the box's top edge says how its question was made: *Architect*, or *not run* for a
brief whose analysis was never started. A box that was not run is dashed and has no code map.

**Stop and ask, on the page.** The Analyst's question ends the run, as before. The coach's answer typed with the
switch on opens a brief that starts from the last one, to be changed before the analysis continues. With the switch
off the answer runs at once under the brief as it was (§2.10).

Not in this patch: the Data tab beside a brief not yet run (it returns when the analysis starts), and ticks on
proposals. A brief that carries saved analyses or lines set aside shows them as stored.

### 2.12 The Architect talks — built (0297, 2026-11-15)

The Architect fills the brief from the question and asks for what is missing. Its lookups are §2.13; it reads no
saved analyses yet (0303).

**One exchange, one call.** `analyst/architect.py`. An exchange is the coach's message - none on the Architect's
first turn - and its reply. The Architect reads (`prompt()`): the data's description, as the Analyst gets it; the
analyses the question follows (`earlier()`) - each one's question and what it found, how the result stood against
its brief, what did not fit, and, where the Analyst stopped and asked, what it asked; the question; the brief as it
stands, part by part; the conversation so far. It replies with one JSON object (`parse()`): the parts of the brief
it writes, one message, and choices where it offers them. A reply that cannot be read is asked for once more; then
the exchange fails, in words, and nothing of it is kept.

**Its instructions.** `analyst/architect.md`, one page. The brief holds what the coach said, in their words:
shorten, do not rephrase or complete, add nothing. It writes every part the coach's words state, then asks for what
is still missing, in the agreed order: the decision; what they think and what that rests on; what they expect and
what would change their mind. It writes a part of what is fixed when the coach's words state it, and does not ask
for one. A message is one question of at most two sentences, in the coach's language, asked so that the answer can
be written down as given: never a yes-or-no question. Choices only where the coach's words already name the possible
answers. A part the coach does not want to state stays empty, and is asked for once. When nothing is left to ask it
says the brief is ready. It does not analyse, compute or answer.

**What a reply may change** (`brief.write()`). The four text parts, the two lists, the three fixed parts. To a list
it adds lines, as the coach's own, four and two at most (§2.2), and it takes a line out by naming it word for word;
a line it does not name stays as it is, with its source and mark. A reply cannot change the question, a mark, a
source, the saved analyses or what was set aside.
A reply that changes a part makes one more version, the Architect's, which says what it was made from: the question,
or an answer. Nothing in the code checks that a line is in the coach's words: that is the instructions' work, and
the live test judges it.

**The record.** `Run.framing` holds the conversation beside the versions: `turns`, each with who spoke and the text.
A turn of the Architect's also has its choices, the version that then stood, what its calls cost and the number of
its call in the chain's log; `calls` counts them. A brief takes twelve replies at most.

**The calls** (`BambooAI.architect_say()`). The instance goes to the brief's thread, as it does for a run. The call
runs on the `Architect` seat when the configuration has one, else on the analyst's seat (decision 28), at a lowered
effort. Either way it is logged, and recorded in usage, as the Architect's (`llm_stream(label=)`), under the brief's
own chain: the Analyst's calls in that chain keep their numbers, and the prompt buttons theirs.

**A framed question is one query.** It is authorised like one when its brief opens and at every exchange. It counts
towards the month's free queries once, when the brief opens, and not again when its analysis starts. It is charged
once, with its analysis. A brief the Architect talked in whose analysis never starts is charged when the instance
is torn down: a new workspace, signing out, or idling out. The Usage dialog calls such a chain *not run*.

**The route.** `POST /architect/say` with the thread, the chain and the coach's text: a stream, as a routine's is,
that ends on the framing, or on the reason no reply was kept.

**On the page.** Opening a brief is followed at once by the Architect's first turn. The left pane is the
conversation: the coach's messages and the Architect's, its choices as pills under its last message, "reading…"
while it replies. The strip says which version stands and what the calls have cost. While a brief not yet run is on
screen the composer is the conversation's ("Answer, or say what to change"): what is typed is said to the
Architect, and a choice clicked is the coach's answer. It is held while the Architect replies, and while another
chain runs. Each message of the Architect's has the button to the prompt it received. The Brief tab says who made
the version shown, and from what: "the Architect, from your question", "the Architect, from your answer", "changed
by you". The coach's own changes work as in §2.11, between exchanges. Once the analysis starts, the conversation is
inside the folded row above the run.

**A follow-up.** A question typed with the switch on under an earlier analysis opens a brief that starts from the
last one, and the Architect keeps what the new question leaves standing. Where the Analyst had stopped and asked,
the coach's answer is the question: the Architect changes the part it settles.

Not in this patch: lookups and marks (§2.13); proposals to tick, which arrive with the first thing the Architect
brings in on its own (0299); saved analyses (0303); a way to stop a reply in flight.

### 2.13 Lookups and marks — built (0298, 2026-11-15)

The Architect checks what the brief rests on against the data, and marks each line by what was found. It still
brings in nothing of its own: that is the next patch (§7).

**A lookup** (`analyst/lookup.py`) is a count, a list or a total - of the main table, or of a file beside it. It
takes conditions (a column is a value, or lies in a range) and a split: by a column, or over time by week, month or
year. The vocabulary is closed (`clean()`): an average, a comparison or a test is not in it, and a request outside
it is refused in words. Each lookup names the line of the brief it checks, word for word; one that names anything
else is refused.

**Where it runs.** The host writes one program for a round of lookups (`script()`) and runs it where the analysis'
cells run: through the executor, hosted or local (`BambooAI._architect_look`). Names and values reach the program as
data inside one JSON text, never as code. It only reads, and leaves nothing behind: no name in the analysis' kernel,
no file. What the data cannot give is refused in words, with what is there: a column or a file that does not exist,
a total of text, a split over time on a column without dates.

**What it finds** is one line (`found()`): what was asked, then the numbers.

    total of load by stage: first 140 · second 112 · third 126
    values of day: 84 different, 2026-01-05 to 2026-03-29
    values of tool: 2 different: old, new

- A list says how many different values a column has, with the lowest and the highest, or the names.
- A split over time shows a period with no rows as 0, so a gap is seen. A week is named by its Monday.
- Text counts as dates only when written year first: 05/03/2026 could be either day, and stays text. A time is read
  on the clock it was written in, whatever zone follows it. Up to a day is through that day.
- A result that would not fit on a line of the brief - more than forty groups, more than 600 characters - is
  refused, never cut: a list cut short would hide the group that matters.

**In the conversation.** A reply may ask for lookups, six at most (`lookups`). The host answers them at once, and
the round joins the conversation as a turn of its own: each lookup under its number, with the line it was made for,
what it found, and whether that is a result (`Run.framing`, a turn whose `who` is `check`). One exchange is still
one model call. The page then asks the Architect again with nothing said, and that reply gives the marks. After one
message of the coach's the data is looked up in two rounds at most: the second is for what the first refused. The
lookups are numbered through the whole brief, so a mark names one of any round. A brief now takes twenty replies at
most; a round is not a reply.

**The marks** (`brief.mark()`). A reply marks a line `holds`, `does not hold` or `cannot be checked` (`marks`).
`holds` and `does not hold` stand only on a lookup made for that line that gave a result, and the fact beside the
line is the host's own line, never the model's words. Given without such a lookup, the mark is passed over, and the
line stays unchecked. `cannot be checked` is the Architect's own statement, kept with the reason it gives. Whether a
fact settles a line is the model's judgement; the numbers are not. A reply that marks makes a version "after
checking the data". The Analyst reads each line with what it is worth (§2.10), and does not rely on one that does
not hold.

**Its instructions.** When nothing is left to ask, the lines that show no mark are checked, in two replies. First
the lookups, for each line the data can settle, with one sentence saying so. Then the marks: a line the data cannot
settle is one that cannot be checked, with the reason in a few words. Where a line does not hold, the Architect says
which and what was found, and asks whether the coach keeps what they think or changes it, with those two as
choices. Then it says the brief is ready.

**On the page.** The round is one row of the conversation, as the pane shows a tool's: CHECK data, how many things
were looked up, the seconds; what each found is the row's title. The Brief tab shows the marks and the facts as
§2.11 says, a fact in red where the line does not hold. A line the coach changes loses its mark, and is checked
again at the next exchange.

**The planted cases** (§4). A false premise of each kind - a stage that was not the largest, a period the data does
not cover, a tool that changed - ends, before any analysis, with the line marked *does not hold* and the data's
numbers beside it (`test_analyst.py`; the lookups run in a kernel, as in the local edition). The stack's walk plants
one in an answer the coach types, beside a line that holds and one that cannot be checked.

Not in this patch: what the Architect brings in on its own - other explanations to tick (§2.14), a fact from the
data as a line of its own; a mark on what is fixed - a period the data does not cover is caught by the Analyst,
which stops and asks (§2.10); saved analyses (0303); a way to stop a reply in flight.

### 2.14 Other explanations, to tick — built (0299, 2026-11-16)

The first thing the Architect brings in on its own: another explanation for what the coach expects to see. It
enters the brief unticked, and only the coach's tick puts it before the Analyst (decision 22).

**In the brief.** A line under *Also check* that the Architect proposed says so, and whether the coach accepted it
(`source`, `accepted`), and may carry what it would show. A line of the coach's own carries neither word. The list
holds two lines in all (§2.2), whoever wrote them.

**What the Analyst receives** (`brief.agreed()`). The brief without what was proposed and not accepted. A run takes
its brief through it (`Session.run`), so an unticked line is in no prompt, not on the run's brief, and not in the
brief a follow-up starts from. An accepted line reads like any line under Also check, with what it would show.

**The reply** (`propose`). Each proposal is a line, what the analysis would find if it were so, and the column of
the data that tells. In code:

- A proposal enters only where its column is in the data's description, as a whole name.
- A brief takes two proposals in all, so one the coach left out is not proposed again and again.
- A reply cannot accept a proposal, and one placed inside the reply's `brief` part is not taken.

Whether the explanation is a sensible one is the model's judgement, and the live test's.

**Its instructions.** With the marks - or with the message that the brief is ready, where there was nothing to check
- the Architect may propose another explanation: something else that would give the result the coach expects. Only
what a column of the data can tell apart from the coach's view. Never chance, measurement error or how the cases
were chosen: those are always tested. It does not ask about a proposal; where one is unticked when it says the brief
is ready, it says that it can be ticked. Rule 1, "add nothing of your own", names this one exception.

**On the page.** The Architect's line has a box, the mark "Architect" and, under it, what it would show. A click on
the box accepts it, another takes the tick back: each a version of the coach's (`POST /architect/brief`). The pencil
makes it the coach's own line, without a box; the cross leaves it out. In an older version, and once the analysis
has started, the box only shows.

Not in this patch: a fact from the data as a line of its own; a proposal for what is fixed; accepting by saying so -
the Architect can then write the line as the coach's own, with `drop` and `also_check`.

### 2.15 Next questions — built (0300, 2026-11-16)

After a finished analysis the coach can ask for the questions that could follow it (§2.7). The plant button has left
the question box; the Analyst's ideas path and the Explore tab are gone.

**The lines an analysis leaves** (`next_questions.record()`). A question comes from a line on the record, each line
with its kind:

| Kind | The line |
|---|---|
| comparison, measure, period | what the brief fixed |
| check | a line of the report's part *Against the brief*, other than the two verdicts |
| proposal | an explanation the Architect proposed and the coach did not tick |
| anchor | a line the brief rests on that was not found to hold, with how it stands |
| would_change | what would change the coach's mind, with the report's verdict |
| misfit | a line of the report's part *Did not fit* |
| asked, found | the question, and the report's opening sentences |
| earlier | what an analysis before it on the thread found |

A list is read six lines deep. An analysis without a brief leaves what was asked and found, and what the analyses
before it found.

**The five levels.** Each reads its own lines first (`OWN`), then the others:

| Level | Its own lines |
|---|---|
| Refine focus | what was fixed, and the question |
| Shift angle | what was also checked, and what was proposed and not ticked |
| Test boundaries | what the brief rests on, and what would change the coach's mind |
| Blend elements | what this analysis found, and what the ones before it found |
| Follow emergence | what did not fit |

**One call** (`next_questions.propose()`), on the Architect's seat at a lowered effort, with instructions of its own
(`analyst/next_questions.md`). It reads the data's description, the analyses before, the question, the report whole,
the brief as the Analyst received it, the questions proposed for this analysis before, the level, and the lines,
numbered - the level's own first. It replies with up to five questions, each with a short title and the number of
the line it comes from; at Blend elements, the two lines it joins. In code:

- A question that names no line is left out, as is one given twice. A set holds five at most.
- At Blend elements a question that names fewer than two lines is left out.
- Where the level has lines of its own, one question at least comes from one. A reply that does not is asked for
  once more, then the call fails in words.
- The origin shown with a question is the record's own line, never the model's words.

Whether a question is a good one is the model's judgement, and the live test's.

**Kept with the analysis** (`Run.next_questions`). Each set as it was asked for: its level, its questions with the
lines they come from, what the call cost, and the chain the call was logged under. The questions are not a run and
not a chain of the thread.

**Money.** The analysis' own chain is settled when it ends, so the call has a chain of its own on the usage record,
charged when the call ends, as Save as routine's proposal is. It is a query for the account's purposes: authorised
and counted as one (`POST /architect/next`). The usage record names such a chain *Next questions*.

**On the page** (`next-questions.js`). The closing card of a finished analysis has a **Next questions** button; one
kept from before the button existed gets it when it is shown again. The button opens the five levels, a name and one
plain line each. The questions of the level picked are cards under the closing card: where each comes from - the
line itself behind the label - its title and text, a pencil and an arrow. A set can be asked for at every level, and
again; each stays. The cards are part of the analysis' own pane, kept with the chain as the rest of the pane is.

**A question that is run.** The arrow starts a new analysis at once, under the one it follows (`/query` with
`next`): no brief, and the Architect's switch does not apply. The pencil changes the question first; a changed
question loses its title. The run's pane opens on a row that says it was a next question, at which level and from
what. On the record and on its card the question is marked with the chain it started; on the thread map the run is
one box, marked *next question* (§2.9). While a set is being written no analysis starts, and the other way round.

**Old threads.** A sapling chain made before this patch keeps its box on the map, as a fork. Its Explore page still
shows its five questions; they can be read, not run. Nothing follows from such a chain.

Not built: a way to stop a set in flight. Questions written after an analysis was saved are not in its saved copy
until it is saved again: a save stores the pane as it stands then.

*From 0314* the list and the questions are a panel inside the closing card, and the run's row says the way only
(§2.24). The engine, the record and the money are as above.

### 2.16 The Architect as a tutor — built (0306, 2026-11-17)

**Why.** The first live run was a bare request from someone new to the subject. The Architect of §2.12 asked for
the decision, then the view, then the expectation, in two sentences each; it asked again after "I am not sure",
and could add nothing of its own. The instructions said so: a fixed order, no comment on an answer, nothing added.
The product owner's word for the result was *mechanical*. What was asked for: a patient tutor that explains,
nudges with questions and suggestions, lets the insight that frames the question come at any point, and stays
until the coach is ready.

**Its instructions** (`analyst/architect.md`, rewritten). It finds out why the person came: to decide something,
to test a view, or to learn. Someone who knows what they want gets there fast, with the questions of §2.3 in the
most useful order and none that does not fit. Someone finding their way gets its help for as long as they want
it. How it talks:

- One step a message: a few sentences and at most one question. It takes up what was just said.
- It gives before it asks: where the person cannot yet say what they want, it explains the little they need next.
- It asks only what the person can answer now. "I do not know" is an answer, and is never asked again: it offers
  an explanation, directions to choose from, or a suggestion.
- Choices wherever they make answering easier, with a way to say "I cannot tell".
- No fixed order. A part of the brief is written the moment the person's words give it.
- It never hurries the person. They start the analysis when they are ready.

It may explain the subject from what is generally known, and suggest a direction, a setting or a wording, which
is the person's once they take it. It asks for a guess of the result, and does not say whether the guess is right.
What stays as it was: the brief holds what the person said or accepted; the Architect does not run the analysis,
give its result, or say what the person's data will show; a mark stands only on a lookup; what it proposes and
what the saved analyses hold stay unticked.

**The question, said back** (decision 30). When the two have worked out what the person wants, the Architect
says the question back in plain words and asks whether it is what they mean. On agreement it writes the wording as
`question`, a part of the brief like any other (`brief.write()`), and tells the person what to look for in the
result. The engine keeps a wording only where the person has read it: it stands, word for word - case and
punctuation aside - in an earlier message of the Architect's, or in a message of the person's own (`_stood()`). A
wording written in the reply that first says it, or one that stands nowhere, is passed over; the rest of the
reply is taken in. The host makes the wording the run's question (`architect_say`), and the analysis of a framed
run asks its brief's question whatever the page sends, so the Analyst receives it and the record is saved under it. The first version keeps the question as it was asked, the conversation on the page
opens on it, and the Architect reads both: `QUESTION` with a line *(first asked as: ...)*. *How a wording becomes
the question changed in 0307: the coach takes it, and the model writes none (§2.17).*

**The limits.**

| | Was | Is |
|---|---|---|
| Replies in one brief (`TURNS_MAX`) | 20 | 200 |
| A message (`SAY_CHARS`) | 600 characters, on one line | 1,500 characters, its lines kept (`_say()`); 6,000 since 0307 |
| Readings of the saved analyses in one brief (`READINGS`) | 2 | 4 |
| Passages a brief holds (`MAX["saved"]`) | 6 | 10: what one reading returns at most |
| Effort (`EFFORT`) | low, else medium | medium, else low; the template's Architect seat is set to medium |

Next questions keep the lowered effort they had (`next_questions.EFFORT`).

**A message of several lines.** The reply's JSON is read with a new line inside a string taken as it is
(`reply_object()`), since a model that writes paragraphs often writes them so. The page shows a message as written
(`white-space: pre-wrap`, as before).

**What the Architect reads of the conversation** gains the choices it offered, under its own message: the person
may answer "the second one".

**The saved analyses in a conversation.**

- *When.* The Architect has them read as soon as it can tell what the question is about - most often with its
  first message, which then only says that it is having a look. One reading serves one direction of the
  conversation. On a follow-up only the coach asks, as before (decision 19). *Since 0307 on a follow-up too
  (§2.17).*
- *What it says.* What the person did, said and found then, in plain words, and when; no count of passages. It lets
  them choose: build on it, or go another way. It brings a passage up again later, when the person heads for
  something an earlier analysis tried or warned against. Where nothing was found it says so in a few words.
- *Room in the brief* (`brief.remember()`). A reading's passages enter the brief; where that makes more than ten,
  the passages the coach did not tick and this reading did not find make room, the oldest first. A ticked one
  stays. The Architect is told of the passages the brief holds (`_recall()`), so it speaks of what the coach can
  tick; one that found no room - the brief full of ticked passages - is counted in a line of its own.
- Each passage comes with where it stands: the report, the brief, the conversation or a cell (`recalled()`).

**On the page.** The conversation opens on the question as it was first asked; the Brief tab's headline is the
question as it stands, marked as changed in the version that changed it. **Look in saved analyses** stays through
four readings.

**The stack.** The scripted Architect answers a bare request (`TUTOR_QUESTION`) with what could be looked at, in a
message of several lines with choices, says the question back, and writes the wording agreed to; it also writes
one nobody has read, which the engine does not keep. The walk's `walk_tutor` checks it on the page with nothing
loaded.

Not run against a live model: the instructions are judged on the dev box, and tuned from the run logs.

### 2.17 The question the coach takes, what the Analyst gets, opening on request — built (0307, 2026-11-17)

**Why.** The second live run - two questions, a plot and a follow-up on another subject - went well as a
conversation and showed five faults, each traced in its run log.

1. On the follow-up the Architect said it was looking in the saved analyses, and went on saying so. It had asked
   for a reading three times; the engine passed each request over (decision 19) and told it nothing.
2. A message of 1,559 characters lost its last sentence at the bound of 1,500.
3. The Analyst was asked the first wording the coach had agreed to. A later one, with a second figure, was agreed
   in the conversation and never written: the model said it was in the brief and wrote nothing. What it had
   settled meanwhile piled up under *Compare*. "Build on it" ticked nothing, so the Analyst could not open the
   earlier analysis. The block it read held three lines "not said", two "left to you" and three checks of a data
   comparison, for a simulation.
4. The Brief tab did not say that it shows what the Analyst will get, nor that a line can be changed; *Compare*
   held a fragment in lower case.
5. The Architect of the follow-up knew two sentences of the analysis before it: not its report, its code or what
   had been said.

*Changed by 0308 (§2.18): a wording is the question at once, and nothing waits; a saved analysis is chosen by
answering, not by a tick; the Brief tab shows only the parts that hold something.*

**The question** (decision 32). The model no longer writes it: `question` under a reply's `brief` is dropped,
always. A reply gives a `wording` - the whole question as it would put it to the Analyst - which stands with its
message (`turn["wording"]`) and waits. It becomes the question in two ways.

- *On the page.* The wording stands under the Architect's message and under the question's box, each with **Use
  this wording**. The click sends the brief with that question, as any change of the coach's (`/architect/brief`):
  one more version of theirs, no model call.
- *In words.* When the coach says yes, the Architect's next reply gives `"accept": true` and the engine writes
  the wording that waited: a version of the Architect's, made from the answer.

Which wording waits is worked out, not stored (`architect.pending()`, and the same in `architect.js`): the last
message that gave one, while the question has not changed since - taken, or changed by the coach's own hand - and
does not read so already. An agreement with nothing waiting writes nothing. The Architect reads the state:
`QUESTION` as it stands, and under its own message *(wording given, not taken yet: ...)* while it waits. Its
instructions: give the whole wording again whenever what is to be done changes; never say the question holds
something that `QUESTION` does not show; what is only in the conversation does not reach the Analyst. The word
check of 0306 (`_stood()`) is gone with what it guarded.

**What the Analyst gets** (decision 33). `brief.render()` writes the parts that hold something: no "not said", no
"left to you", and of what is fixed the parts the coach fixed. *Decision* reads *What the answer is for*. The
three standing checks are listed for a run on data: `notebook.has_data()` reads the run's data record, and only
one that says nothing is loaded - no frame, no file beside one - has none. A brief gives something to hold the
result against where it says what the coach expects, what would change their mind, or a check - the standing
ones among them (`brief.held()`). Only then does the contract ask for *Against the brief*
(`contract(held=)`, `BRIEF_AGAINST`) and the report's foot say when it is missing; *Did not fit* stays with every
brief (`BRIEF_MISFIT`). The contract's section says a part the brief does not fix is the Analyst's to choose.
In the memory view a brief's record reads the same (`memory.FORMAT` 4).

**A brief line.** The instructions ask for a full sentence in the person's own voice, and keep `fixed` for an
analysis that compares data; what is to be done belongs in the wording.

**"Build on it"** ticks. The passages under `saved` are numbered in what the Architect reads, and a reply names
the ones of the analysis the coach chose (`tick`, `brief.tick()`): they are accepted as part of that reply's
version. Nothing is ever unticked by a reply.

**A request that cannot be met** (decision 34). The Architect's own request for a reading is carried out on a
follow-up as on any question. Where a reply asks for a reading that cannot be made - four made, or one since the
coach last spoke - for a fourth part to open, or for a third round of lookups, the engine tells it at once
(`NOT_DONE`, with the reason) and asks for the reply again, in the same exchange; that reply is the one kept, and
what it still asks for is not done. The prompt says beforehand when no reading can be made (`SAVED: n (no
reading can be made now: ...)`), and the instructions keep "I am having a look" to the reply that asks.

**A message** is kept whole: the bound is 6,000 characters (`SAY_CHARS`), for a reply that does not end. The
instructions ask for a short one - a few plain sentences, about a hundred words - and no longer offer starting
the analysis as a choice: that is the coach's button.

**A follow-up starts clean** (decision 35, `open_framing`). Its brief opens with what the last answer was for
and what the coach thinks, marked *from the last brief*; what was expected, what it rested on, what was fixed and
the saved analyses chosen belonged to the question before. Where the Analyst had stopped and asked, the new
question is the coach's answer, and the brief opens as the last one, whole. The framing also says whether data is
loaded (`framing["data"]`), for the page.

**Opening on request** (decision 36). `EARLIER` gains, for the Architect, what each analysis has to open and of
the last a line to each cell: its number, what it was for, what came out, what it drew (`earlier(cells=True)`).
A reply opens one part: `{"what": "report" | "cell" | "conversation", "n": <cell>, "run": <its number>}`. The
engine answers from the thread's record (`_part()`): the turn it keeps names the part and its length and never
holds its text (`{"who": "opened", ...}`); the next exchange, which the page starts at once, reads the part in a
block of its own after the conversation (`opened()`, *OPENED*), cut in the middle beyond 16,000 characters. Three
parts after one message of the coach's, all in view for the replies that follow; once the coach has spoken they
are gone from view and the conversation says only what was opened - as the Analyst's SHOW lasts one prompt. A
part that is not there is a turn that says so.

In the live run the report was 9,701 characters, the code 32,878, the conversation 8,345: some 12,700 tokens,
which would have ridden in each of the follow-up's six prompts of about 3,800. The index costs a line a cell.

*The picture is not opened.* A figure is not on the server's record: the page holds it. The Architect is told so,
and to ask the coach what they see; the cell's code says how the figure was drawn.

**On the page.**

- *The Brief tab.* On top **What the Analyst will be asked**, with the version beside it; the question in a box;
  a wording that waits under it; then one line: *This is what the Analyst gets. Change any line before you
  start.* The parts under plain names: What it is for, What you think, It rests on, What you expect to see, Also
  check, Fixed before the run. While the brief can be changed a part with nothing in it is a place to type it
  (*+ Add*); the three fixed parts - **What is compared**, **Measured by**, **Period** - are lines when used and
  offers by name when not. A brief only read - an older version, one that runs - shows the parts it holds. The
  standing checks show where data is loaded.
- *The conversation.* A wording is a card under its message: the button while it waits, *in use* once the
  question reads so. A part opened is a row - READ, what, how long - and the Architect goes on at once.

**The stack.** The scripted Architect gives its wording under the reply's own key and reports an agreement; it
still writes a question itself when told to, which the engine drops. A briefed run with nothing loaded reports
without the part *Against the brief*. On a question that follows the tutor's analysis it has the saved analyses
read, opens the report, speaks from it, and ticks a passage when told to build on it. `walk_tutor` checks all of
it on the page.

Not run against a live model: whether the model gives the wording under its key, keeps it current and keeps its
messages short is judged on the dev box, from the run logs.

### 2.18 One question, the version on screen, no empty parts, saved analyses to read — built (0308, 2026-11-17)

**Why.** The product owner tested 0307 and could not tell three things apart: the wording that waited on a green
card with **Use this wording**, the question in the box, and what **Start analysis** would send. The pencil
showed only once the wording was taken. Under the question stood six headings and nine *+ Add*, and under those
saved passages with boxes whose meaning was not clear. "Too many levers."

**One rule** (decision 37). What the Brief tab shows is what the Analyst gets. Nothing waits beside it.

**The question changes by itself.** A reply's `wording` is written as the question in the same reply: one more
version of the Architect's, with `question` changed, and the host makes it the run's. The message keeps the
wording (`turn["wording"]`) only where it changed the question, and the conversation shows a row under that
message: *QUESTION updated · version 4*. There is no card, no button and no `accept`; nothing is worked out as
waiting (`architect.pending()` is gone). The Architect reads under its own message *(the question was written
as: ...)*. Its instructions: word the question whenever what is to be done changes, and word it again from what
the coach says when it is not what they mean. `question` under a reply's `brief` is still dropped: a wording
comes under its own key or not at all. The coach changes the question with its pencil, as any line. *0313
(§2.22) says what a wording is to hold, and has it read before the analysis starts.*

**The version on screen is the one in use** (decision 38). On top of the tab: **Version**, the two arrows, *3 of
8*. A version is the whole brief, question and parts. Stepping sends nothing. What the coach does next goes on
from the version shown:

- *An answer, typed or clicked.* The request carries the number (`/architect/say`, `version`). The engine takes
  that version as the one in use (`brief.use()`: `framing["at"]`, absent while the last one is in use) and says
  so in the conversation: a turn `{"who": "version", "v": 3}`, the page's row *BRIEF · version 3 in use*, and in
  the prompt *(the person went to version 3 of the brief: QUESTION and BRIEF show it)*. The reply's changes are
  made to that version and kept as one more, counted on from the last. A reply that changes nothing leaves
  version 3 in use.
- *A change by hand.* The page sends the brief on screen with the change (`/architect/brief`): one more version,
  which is the last and the one in use.
- *Start analysis.* The button names the version when it is not the last - **Start analysis with version 3** -
  and `/query` carries the number. The run's brief and question are that version's (`brief.latest()` honours
  `at`). The later versions stay on the record, and the run's Brief tab opens on the version it ran under.

Every version can be changed, and the pencil shows on each line at rest. The strip over the conversation no
longer names a version: it named the one in use on the record, which is not the one on screen once the coach
steps. The control on the Brief tab is the one place that says which version it is; the fold above a run still
names the version the run started with.

**The parts** (decision 39). A part shows when it holds something. One **+ Add**, under the parts, opens the list
of those not there - *What it is for*, *What you think*, *Why you think so*, *What you expect to see*, *What would
change your mind*, *Another explanation to test*, *What is compared*, *Measured by*, *Period*. The one picked
takes its place in the brief, open for typing; given up, it is gone again. Three names changed: *It rests on* is
*Why you think so*, *You would change your mind if* is *What would change your mind*, *Also check* is *Other
explanations to test*. The heading *Fixed before the run* is gone, and its three parts stand under their own
names. The three standing checks are one quiet line where the run has data: *Always tested on data: chance,
measurement error, how the cases were chosen.* All of this is the page: the Analyst's block reads as in §2.17.

**Saved analyses** (decision 40). A reading writes nothing into the brief and makes no version. What the readings
found is kept beside the brief (`framing["found"]`, `brief.gather()`), and the analyses are numbered in the order
they were found. The coach sees them in two places, to read:

- *In the conversation*, under the reading's row: an analysis to a line - the day, what was asked then, **View**.
  The row counts analyses, not passages: *2 analyses found · read 9 of 12*.
- *Under the brief*, after a rule: **Found in your saved analyses** and *For you to read. The Analyst gets only
  what you build on.* Then each analysis with its passages and the reader's notes, **View**, and the tag *built
  on* where the brief builds on it.

**View** shows the analysis in a dialog over the page, as *Open* did; the word changed so that nobody expects the
workspace to move. Nothing is ticked. The coach chooses by answering the Architect, which names each analysis
found in a choice of its own. Its reply then gives `build`: the numbers of all the analyses the brief builds on
from then, `[]` for none. `brief.build_on()` puts their passages under `saved`, as that reply's version. The
brief lists them under **Builds on**: the day, what was asked, **View**, and a cross that leaves the analysis
out - a version of the coach's. The Architect reads the same: each analysis found under its number in the
conversation, and `builds_on` in its BRIEF block. The Analyst receives the passages of the analyses built on, as
before (§3.7, §3.8).

Gone with it: the boxes on saved passages, the tag *saved analysis*, the line *report · picked*, the button
**Look in saved analyses** with its flag on the route (`look`) and the reading the engine forced for it. A coach
who wants another reading says so, and the Architect asks for it as for any reading: one after a message of the
coach's, four in a brief.

**The record.** `framing` gains `found` and, while an earlier version is in use, `at`. A reading's turn keeps the
version it was made under; a turn `{"who": "version"}` marks where the coach went to another.

A brief opened under 0307 and not yet run is best started again. Its saved passages left unticked are not shown
as built on, which is right; but what its readings found has no numbers to build on, and a wording that still
waited there is not the question.

**The stack.** The scripted Architect words the question under `wording`, and it is written at once. After a
reading it offers a choice to each analysis found, and builds on the one named; asked in words, it has the saved
analyses read once more. `walk_architect` adds parts through **+ Add** and steps through the versions.
`walk_saved` views an analysis, builds on it by a choice, skips a second reading, leaves the analysis out with
its cross, goes back one version and starts the analysis with it: the Analyst gets that version's passage.
`walk_tutor` sees the question written twice, goes back to the first wording, answers from it, adds two lines to
it by hand and runs.

Not run against a live model: whether the model words the question when it should and no more often, and
whether it gives `build` from the coach's answer, is judged on the dev box, from the run logs. Every change it
makes is a version the coach can see and step back from.

### 2.19 The figures in the brief — built (0309, 2026-11-18; the sketch a stand-in in 0310 and gone in 0311, §2.20)

**Why.** The product owner asked the Architect for figures and could not picture, from its words, what the result
would look like. A sketch on the Brief tab shows it before anything runs.

**A figure is a part of the brief** (decision 41). `figures`: three at most, each `{title, kind, x, y, z, series,
note}` (`brief.normalise()`). A figure is its title, which names one figure whatever its case. `kind` is one of
`line`, `scatter`, `bar`, `histogram`, `box`, `heatmap`, `line3d`; any other is dropped and the title kept. `series`
is what the figure holds: up to four names. Every text is bounded; the note as a line of the brief is (0311: at
240 characters a live note - the layout of two panels, then what they were to make clear - was cut in the middle
of a word). There is no step to accept a figure: what the brief holds is what the Analyst gets (decision 37).

**The Architect describes.** The description comes in the reply that carries the message. The reply's key is
`figures` - every figure as it is to stand, in order. One that stays as it is comes as its number in BRIEF alone,
a new or changed one in full; `[]` takes them all out; a reply without the key leaves them (`brief.sketch()`). The
change is one more version of the Architect's, with each place named (`figures.1`). The Architect reads the
figures in its BRIEF block, each under its number, in words. Its instructions: describe a figure when the person
asks for one, or asks to see what the result will look like, and not otherwise. What is drawn from the
description is the draft (§2.20).

**The sketch, and why it went** (decision 42). In 0309 the page drew a figure's description as a sketch: a wave
where a line goes, rings for points, bars and boxes, a grid for a heat map. A series could come with rough
`points` - up to 24, written by the Architect - and the page drew a line through them. The product owner's test
showed what that is worth: a model cannot write down a shape it would have to compute, and where it rightly gave
none, the sketch was a wave that looked like nothing. In 0310 the points went - from the brief, the Architect's
instructions and the page - and the grey sketch stayed as a stand-in while the draft was drawn. His live test of
0310 found the brief "a little too busy": a dashed sketch, its key and a long note under it, for the few seconds
before the figure itself. In 0311 the sketch is gone from the page. A brief that still holds points is read
without them.

**On the page.** **What it will look like** stands after what is fixed and before **Builds on**: a panel to a
figure, numbered, one under another. A panel is the figure's draft where one was drawn; otherwise a grey window
with one line (§2.20). While the brief can be changed each panel has a cross, which takes the figure out - a
version of the coach's (`unfigure()`, `/architect/brief`). A figure is changed by saying so to the Architect;
none is added by hand. The brief of a run keeps its figures, to hold against what was drawn.

**The Analyst and the step that draws** (decision 43). The Analyst's BRIEF block lists the figures after what is
fixed, numbered, in words (`brief.figure_lines()`: the title, the kind, what is on each axis, what it holds, what
it is to make clear). The contract of a run under a brief says that they are drawn after its report from what the
kernel holds: compute what each one needs, and keep it in a variable. The step that draws had never seen the
brief. It now reads the same lines under its question - *THE FIGURES AGREED WITH THE PERSON* - to draw first, in
that order, each as described and under its title, word for word; a figure of its own only where the report needs
one the list does not have - two at most (0310; *three in all* had left the report none beside three agreed
figures).

Code holds the titles:

- *Before anything runs.* A reply that leaves an agreed figure out - NONE, or a cell whose code does not carry
  the title (`brief.carries()`: its words in their order, whatever the case and the spacing) - is not run. It
  is an attempt on the record, and the step is asked again with the titles it left out. Once: the next cell runs
  as it is.
- *After the run.* The titles the figures were drawn under are held against the agreed ones, and the report's
  foot names each one missing: *A figure agreed in the brief was not drawn: "..."*. A plot the kernel saved
  itself (not Plotly) has no title to read; the cell's code stands for it.

Each agreed figure is a figure of its own in the report, in the agreed order. A figure of several panels is one
figure: its note says how it is laid out (0310).

**The record.** A brief's `figures`. A brief without figures reads, and runs, as before.

**The cost.** The Architect's instructions grew by about 1,700 characters: some 400 tokens more on each of its
calls.

**The stack.** Asked to show the figures (`ARCHITECT_SHOW`), the scripted Architect describes three: the yield
of two regimes by season, the plot yields of each as boxes, and the target. Asked for the second first
(`ARCHITECT_SWAP`), it gives them by number. The scripted step that draws draws the agreed figures under their
titles, and leaves the last one out on its first reply. The walk is the draft's (`walk_draft`, §2.20).

Not run against a live model: whether it describes a figure when asked and not otherwise, and describes one the
Analyst can compute. Code checks the title of each figure drawn; whether the figure follows the rest of its
description - the kind, the axes - is the model's work, to be judged on the dev box.

### 2.20 The draft of the figures — built (0310, 2026-11-18; the page made plainer in 0311)

**Why.** The product owner tested 0309 on a figure whose shape follows from a rule, in a brief that built on a
saved analysis which had drawn that very figure. The Architect described two figures and gave no points -
rightly: a model cannot compute a shape in its head. The page drew one grey wave in each panel, under *The data
decides the shapes*, where there was no data. "The two sketches look nothing like what we would expect." Four
things were wrong: no shape was computed; a figure of several panels could not be described; the caption was
wrong; and the saved analysis' own figure and code went unused. The drawing library was never the problem.

**What was agreed** (decisions 44-47).

- A figure of the brief is shown as a **draft**: a model writes one short cell, the sandbox runs it, and the Brief
  tab draws the plot with Plotly - the library the report's figures are drawn with.
- A shape that follows from a rule alone is **computed**. One that only the data can give is drawn on **made-up
  numbers**, and marked. The cell is given no data, so the wait does not grow with the data.
- Where the brief builds on a saved analysis, its code is given to the model that writes the cell. (0310 also
  showed what that analysis drew; 0311 took that out.)
- The step that draws the figures of the analysis is given the draft's cell.
- Where there is no draft, the figure's place says so. (0310: the grey sketch of 0309; 0311: a grey window with
  one line.)

**When a draft is drawn** (`analyst/draft.py`, `due()`). After a reply of the Architect's, in the same exchange:
each figure of the brief in use that has no draft. A draft is kept under a key of the question as it stands and
the figure as it is described (`key()`). The same figure under the same question is drawn once: another order, a
figure taken out and a step through the versions draw nothing. A change to the question or to the figure is
another draft. None is drawn while the Architect goes on by itself, after its lookups, a reading or a part it
opened: the reply the coach reads is the one after. A figure whose draft could not be drawn is tried once more,
after the coach next speaks, and then left (`TRIES`).

**The cell** (`analyst/draft.md`, `prompt()`, `draw()`). One model call on the seat of the step that draws
(*Figures*; the Analyst's where the configuration has none), at a low effort, logged as *Draft* under the
brief's chain and charged with it. The model reads the question as it stands and the figures in words. Where
there are any, it also reads the cell that last drew figures for the question, and the code of the saved analyses
the brief builds on (`saved_code()`: the cells along each one's path, from the thread's record). It reads nothing
of the data. Its reply is one cell that draws each figure with Plotly, under its title. For each figure it
decides which of two it is:

- *Its shape follows from a rule alone.* The cell computes it in full and says so on the figure:
  `fig.update_layout(meta="computed")`.
- *Anything else.* The cell draws the figure as it will stand - traces, panels, axes, names - on numbers it makes
  up, says nothing, and prints `?` where the figure is to print a value. In doubt, this.

A reply without a cell, a cell that is not run and one that leaves a figure without a plot - it failed before it
drew it, or drew none under its title - are asked for once more, with what went wrong. What a cell drew before it
failed counts, and each figure keeps the last plot drawn for it.

**Where it runs** (`bambooai.py`, `_draft()`, `_run_draft()`). Through the executor, as the Architect's lookups
do - with no frame, none of the thread's names and no folder to write to. Three things are held in code:

- *No data.* The cell is given none, and it is screened before it runs (`screen()`): it imports numpy, scipy,
  pandas, plotly and the maths modules and nothing else, calls nothing that reads or writes a file, and uses no
  name that leads out of the cell. The screen is no sandbox - the executor is one. It keeps a cell that means
  well from the coach's files.
- *A few seconds* (`SECONDS`, 20). On the coach's own machine the cell's kernel is stopped then
  (`code_executor.execute(step_timeout=)`). An executor answers past its limit and leaves the script's thread
  running; there the cell carries a guard that raises in its thread shortly before (`DRAFT_GUARD`). A cell that
  never ends is ended - unless it never comes back from compiled code.
- *Computed only where the cell said so* (`read()`). A plot is computed where its layout says so; every other
  draft is shown as made up. A plot stands for the figure whose title it carries. Only a Plotly figure counts, and
  none longer than 1.5 million characters.

A draft never fails the exchange (decision 45). The reply is kept before the cell is written. A round that drew
nothing, or broke off, is a turn that says so, and the figure's window says that no draft could be drawn.

**What is kept.** Beside each version of the brief, the keys of its figures (`keyed()`: `versions[].keys`). In the
framing, by key, what each draft is: `{"basis": "computed" | "made up"}`, or `{"failed": why, "tries": n}`
(`framing.drafts`). The round is a turn of the conversation: `{who: "draft", drawn: [{title, basis}], missing,
failed, v, secs, cost, call}`. On the run, the cells that drew, each with the keys of its figures (`Run.drafts`).
The plots are files beside the thread's record - `storage/<user>/drafts/<thread>/<run>/<key>.json` (`Plots`) -
and never in the record or in the framing, which rides in the page's markup. The folder goes with its thread
(`cleanup.py`). `GET /architect/draft/<thread>/<run>/<key>` gives a plot to the page.

**On the page** (`architect.js`). The stream of an exchange first carries the framing with the reply
(`architect_draft`): the message stands, a row under it says *DRAWING A DRAFT* (decision 48), the composer is
held, and each figure is a grey window with one line in its middle, *Drawing a draft…*, which breathes - the one
thing that moves, and still for a reader who asked for less motion. The stream ends on the framing with the
draft; one that ends before it leaves the reply standing, its figures without a draft, and nothing says the
Architect did not reply. Each plot is fetched once and drawn by Plotly in its figure's place (`mount()`;
`draftLayout()`: the figure's own layout, fitted to the panel). The panel says *draft*. On made-up numbers it says
*draft · made-up numbers*, those words stand across the plot, and a line under it reads: *The numbers are made
up. The analysis puts in the real ones.* The row reads *FIGURES 2 drawn · 6 s*, with the button to the draft's
prompt. The brief of a run keeps its drafts.

**A figure without a draft** (decision 42; `windowOf()`). The same grey window, with one line and nothing else -
no sketch, no key, no tag: *No draft could be drawn.* where both cells failed, the reason under the mouse; *No
draft yet.* where none was tried - after a change by hand, or a stream that ended - and *No draft was drawn.* in
the brief of a run. Where a plot cannot be had, or the page has no Plotly, the window says *The draft could not
be shown.* How the Architect described the figure is not on the page (decision 49): its kind, its axes and its
note are the drawer's and the Analyst's, and the draft shows what came of them.

**A saved analysis the brief builds on** (decision 47). Its code goes to the model that writes the cell. Nothing
of it is drawn in the brief. 0310 put the picture its favourite keeps under its line, *What it drew then*; with
the draft above it and the reading's passages below, the product owner found the brief too busy, and it went.

**The Architect.** It describes; it does not draw, and it does not see the draft. Its instructions: a draft is
drawn right after the reply; say that it is being drawn, and nothing of how it looks; when the coach wants it
another way, change the description - or the wording, where the change is to what is computed. A figure's `note`
also says how a figure of several panels is laid out. What a draft came to is a line of CONVERSATION (`line()`):
*Draft of the figures: drawn - "…" (computed), "…" (on made-up numbers); not drawn - "…": why*.

**The step that draws** (decision 46). Under the agreed figures its prompt holds *THE DRAFT THE PERSON SAW*: the
cell that drew them, a cell once, with the figures it drew and which of them stand on made-up numbers
(`draft.agreed()`). Its instructions: draw each as the draft drew it - the same traces, panels, axes, colours and
names - from what the kernel holds; no number comes from the draft, and where the draft prints `?` the figure
prints the value.

**The wait and the cost.** One short model call and a cell that takes a second or two. The coach reads the reply
meanwhile. The draft's instructions are some 500 tokens; the Architect's are as long as before.

**The stack.** The scripted model that drafts (`draft()`, `draft_cell()`) draws the yield of two regimes by season
and the plot yields of each on made-up numbers, and the target - 5 percent more each season - computed. The
stand-in Plotly's figures carry their title and what the cell said of them. The stand-in for the page's library
draws a figure plainly: lines, bars, boxes, the words across. `walk_draft`, on data: what stands while the draft
is drawn - the row, the composer held, a grey window to each figure that shows and breathes, taken as the page
first draws it (0311) -; the three drafts on the Brief tab; the record, the files and the route; the draft's
prompt; another order, with nothing drawn again; the cross and the arrows; the analysis - the step that draws is
given the cell and is asked again for the figure it left out - and the Brief tab after the run. `walk_saved`:
nothing of the analysis built on is drawn, and the page asks for no picture (0311). The gallery has
`architect_draft` and `architect_drawing`: the reply with a grey window to each figure (0311; it was
`architect_sketch`).

**Not run against a live model, nor with Plotly.** Every reply in the tests is scripted, and the test machine
has neither Plotly nor the page's library: stand-ins take their place. Whether the model writes a cell that runs,
draws what was described, computes where a rule gives the shape and makes numbers up where it does not - and how
the draft looks - is for the dev box.

**Known limits.**

- A change the coach makes to the question by hand leaves the figures without a draft until the Architect next
  replies.
- What a draft's numbers are is the cell's word. Code holds only that a draft without that word is marked as
  made up.
- On an executor, a cell stuck inside compiled code past its limit runs on until it returns.

### 2.21 What the report says against the brief: out of the Answer — built (0312, 2026-11-19)

**Why.** The product owner, from a live run: the Answer "could be shared via PDF with third parties not familiar
with the mechanic". A reader who was not in the conversation with the Architect has not seen the brief. A card
headed *Against the brief*, with what was expected and a list of checks, tells them nothing they can place. The
Answer is the report as it goes to other people (decision 50).

**What changed, and what did not.** The engine is untouched. The Analyst writes `## Against the brief` as before,
`outcome()` reads it onto the run, the Architect, memory and the next questions use it, and the plain-language
version keeps it. The change is on the page, where the answer is shown (`architect.js`):

- `cutAnswer(html)` takes the part out of the answer: under its heading, as the report wrote it; as the card an
  answer kept before 0312 holds; and with it the engine's line that the report does not say how the result stands
  against the brief. It gives back the answer without them, and the rows of a card.
- `turnedOut(root, rows)` puts the card at the foot of that run's Brief tab, under *How it turned out*. The rows
  are kept in the brief's own markup (`data-against`), as its versions are, so the arrows and a chain shown again
  have them with nothing else kept. The card stands under the version the run was under and under no other: under
  an earlier version it would be read against lines the run did not have. `root` is the run's own tabs - the
  page's, or the holder of a run that goes on while another chain is on screen.
- Both versions of the answer are cut: the technical one where it is rendered (`content-rendering.js`), the plain
  one at the toggle. The export prints the answer as its tab holds it, so it holds nothing of the part; its print
  rules for the card are gone.
- A citation in a row is the chip it was in the answer, and opens the code map as it did: the chips' rules
  (`shell.css`) held under the Answer tab alone, and now cover the card.

**Did not fit** stays in the answer: it reads as a finding. Whether it should move too is the product owner's to
say.

**Tests.** `test_architect.js`: the cut in each form - a list, plain lines, a heading at any level, a table, a
card kept from before, the engine's line - the rows, the Brief tab's markup under the version in use and under
another, and `turnedOut()` driven with the arrows. `test_pdf_export.js`: no rule for the card. The walk
(`walk_architect`): the card on the Brief tab and nothing of the part in the answer, in the plain version, or in
what the PDF button hands the printer; the arrows; a chip's look and its way into the code map; a chain kept
from before, shown again. The gallery: `architect_answer` is the answer without the part, `architect_outcome`
the Brief tab with the card.

**Known limits.**

- The dialog of a saved analysis (**View**) shows its report as it was written, with the part.
- The plain-language version is still written with the part; the page leaves it out.
- The library has no page: its report holds the part as before.

### 2.22 The question as the Analyst will read it — built (0313, 2026-11-19)

**Why.** The product owner, from a live run, after several rounds with the Architect: the question pointed to an
analysis of another day, which the Analyst "does not have access to or knows what it means". The same question
carried how the figure was to look, kept a correction as a clause that said what not to do, and spoke of the
Analyst in the third person. The Architect words the question inside a conversation, and to it nothing was
missing.

**What the Analyst is given.** Its prompt holds, in this order: the analyses the question follows in the thread,
each with what it asked and found; the data as described; the question; and the brief as agreed - without what
the Architect proposed, or the readings found, and the coach did not accept. It holds nothing of the
conversation, no saved analysis the brief does not build on, and no day on which anything was done.

**What the Architect is told** (decision 51; `analyst/architect.md`, *The question*).

- The wording says what is to be done and on what, in two or three sentences addressed to the Analyst.
- It is told what the Analyst is given, and to point to nothing else: what the question needs from the
  conversation or from a saved analysis the brief does not build on, the wording says itself.
- How a figure is to look belongs in the figure's description. Its `note` now holds how the figure is laid out
  and is to look, where the coach said, and what it is to make clear.
- When what is to be done changes, the whole question is worded afresh from what now stands: what is wanted,
  not what was dropped on the way.

**The read before the start** (decision 52; `analyst/cold.py`, its instructions `analyst/cold.md`). Instructions
are not enough: the Architect reads its own wording with the conversation in mind. So before an analysis starts,
what the Analyst will be given is given to a model that has nothing else (`given()`: the same blocks, in the
prompt's order). It is asked for the words of the question that point to something it was not given, as one
object: `{"cannot_place": [...]}`.

- A phrase counts only where it stands in the question, word for word (`named()`), three at most. A reply that
  cannot be read names nothing.
- A pointer is to earlier work or to something said elsewhere. A day, a name or a value that the data can
  settle is none, and the reader is told so: questions about data name days all the time.
- *Nothing named.* The read is a turn of the conversation (`who: "reader"`), and the analysis starts.
- *Something named.* The read is a turn, the analysis does not start, and the Architect goes on at once
  (`ready()`): one exchange with no message, whose CONVERSATION ends on *A reader given what the analyst will be
  given could not place: "..."*. It words the question again, and says what it changed. Where the figures are
  due a draft, one is drawn. The coach sees the new version and presses **Start analysis** again.
- *A read holds a start up once.* The framing lists the versions read (`read`). The version the Architect leaves
  after a read is listed without being read, so the second start always starts; so does the version before it,
  if the coach goes back to it. A version the coach makes by hand is read when it is started.
- *A read that cannot be made holds nothing up.* Where the provider fails or the route is refused, the analysis
  starts. Where the Architect's reply after a read fails, the read stands and the page says why.
- The version read is the one in use from then, as with an answer (`use()`). Where the Architect goes on from a
  version the coach went back to, its CONVERSATION says so before the read.

**The call.** One call on the Architect's seat at low effort, logged as *Question check* under the brief's chain
and charged with its analysis. Its turn numbers it among the question checks; the Architect's calls are counted
apart, because the run log finds a call as the n-th of its name.

**The host and the route.** `architect_ready(thread, run, version)` gives `{"framing", "clean"}`, with `"error"`
where the Architect's reply failed. `POST /architect/ready` is a stream that ends on that, under `"architect"`;
it carries `architect_draft` before a draft is drawn, as `/architect/say` does.

**On the page** (`architect.js`). **Start analysis** keeps a line being typed, then has the version on screen
read (`ready()`), unless the framing lists it as read. While it is read a row says *CHECKING THE QUESTION*, and
the composer is held and says why. Then the row reads *CHECK question · stands on its own*, or, greyed, *CHECK
question · the Analyst cannot place "..."*, with the seconds and the button to what the reader was given. The
words are read whole: that row wraps, where any other row is cut at one line (`.ar-unplaced`). The analysis
starts only where the brief is still on screen and nothing else runs: the read takes a moment, and the page's
send would stop an analysis begun meanwhile. What the stream carries on its way - a reading of the saved
analyses, a draft that follows the reply - is shown as in any exchange (`along()`).

**Tests.** `test_analyst.py`: what the reader is given - the Analyst's first prompt starts with it, to the
letter -, the phrases kept, a clean read, a read that names something, the Architect's reply failing, an
earlier version, the instructions. `test_app_path.py`: the route - the seat, the effort, the name in the log,
the draft, what can go wrong. `test_architect.js`: Start driven - the row in flight, a clean read, a held
start, no reply, a read that cannot be had, the brief left meanwhile, a draft, a lookup. The walk: a clean read
in the fold above the run and on the usage record (`walk_architect`); a question the coach words so that it
points to an analysis the Analyst is not given - held, worded again, started (`walk_tutor`).

**Known limits.**

- Not run against a live model. Whether the reader names the right words, and leaves alone what the data or the
  thread's earlier analyses settle, is the live test's to show.
- A read is one small call, and a few seconds, at the first start of each version.
- The reader reads the question. A line of the brief that points outside is not found.
- The Architect's wording after a read is not read: where it still points outside, the Analyst gets it so.

### 2.23 The closing card — built (0313, 2026-11-19)

**Why.** The product owner: "the Code Map and Next questions are sort of confusing", and so was the arrow after
the last link. The card held a grid of numbers, then a line of links to the tabs, each with an arrow - one of
them, *Simplified →*, did nothing (§2.21) - with the code map's button among them, then **Next questions**
under a rule of its own. Of three mockups he chose the second.

**What it is now** (decision 53; `stream-pane.js`).

- One line: the title, and beside it the run's numbers - turns, cells with how many failed or were not run,
  plots where there are any, cost, time (`build.head()`).
- Under it, as before: what the replay reproduced, and the reach report - one faint line where nothing was
  reached.
- Then one rule, and what can be done next: **Next questions** and **Code map**, two buttons alike (`.acts`,
  `.sp-act`). `next-questions.js` puts its button first. A run that ran no code has no code map; a run that
  ended on a question, was stopped or failed has no buttons.
- No link to a tab. The tabs are there to click.
- A routine's card has its numbers the same way, and no links.

**A card kept from before.** A chain's pane is kept as it was drawn. When such a chain is shown again its
closing card is brought to the new shape (`paneRenew()`): the title and the numbers on one line, the links gone,
the two buttons in their row. Its numbers keep the words they were written with.

**The host.** `pane_run_end` no longer says whether the run had a brief: the card links to no tab.

**Tests.** `test_pane.js`: the card for each way a run ends, a routine's card, a kept card renewed.
`test_next_questions.js`: the button, and where it is put. `test_code_map.js` and `test_routines.js`: the
button and the sources. The walk: the card's shape in the browser - one line of title and numbers, no link, no
arrow, the two buttons alike and side by side - and a card kept from before, shown again.

### 2.24 Next questions, a panel in the card — built (0314, 2026-11-19)

**Why.** The product owner, of the list the button opened: "very little explanation what the feature does, what
the options mean, and it collapses down to the very edge of the workspace which looks crowded". The list dropped
over the card and the question box, and the questions then stood under the card, each set under a head of its
own. Of three mockups he chose the first, and asked to see what follows a click before it was built: "we need to
make sure we stay consistent". Of the first sentences for the five ways: "mechanical" - they were written again
from what the Architect is told to do at each way (`analyst/next_questions.py`: `LEVELS`, `OWN`).

**What it is now** (decision 54; `next-questions.js`, `pane.css`). Only the page changed.

- The button opens a panel inside the card, under the row of buttons; the button, or the panel's cross, shuts
  it. Nothing drops over the page.
- **The list.** A heading, *Where do you want to go from here?*; one line of what the questions are; then the
  five ways, a row each: its name, and a sentence of what its questions do.

  | Way | Its sentence |
  |---|---|
  | Refine focus | Stay with the same question and look closer: a smaller group, a shorter period, a stricter measure. |
  | Shift angle | Ask whether something else explains the result, and put that to the test. |
  | Test boundaries | Check what the result stands on, and find where it stops being true. |
  | Blend elements | Bring two findings together in one question, such as this result and an earlier one. |
  | Follow emergence | Go after what did not fit: the things this analysis could not explain. |

- **A way picked.** Its row says *writing the questions…* and the others stand back. The questions then take
  the list's place: over them the way back, *‹ All five*, and the way's name and sentence; then a row for each
  question on the same columns as the list - its title, its text with what it starts from under it in small
  plain letters, the pencil and the arrow; under them how many there are, what the call cost, the button to
  what the Architect read, and **Write more**.
- **The list again.** A way that has questions says how many. A click on it shows them: no call. A way without
  questions is asked for, as before; **Write more** asks for a further set of the way shown, which stands under
  the first.
- **The run's row.** *Next question · Test boundaries*: the way, and no more. What the question came from is on
  the question's own row, where it is read with the question.
- What a question starts from, in three cases reworded: *what it rests on*, *what did not fit*, *what was also
  checked*.

**How it is kept.** The panel is part of the analysis' pane, kept with the chain: its sets as before
(`.nq-set`, `.nq-card`), in `.nq-sets`; what stands over and under them (`.nq-top`, `.nq-end`) is drawn from the
sets and from what the panel shows (`data-show`: `list`, or a way's key), so a kept panel comes back as it was
left - open or shut, on the list or on a way. That a set is being written is of the moment and is not kept.

**Kept from before.** Sets the page kept under the card are taken into the panel when their chain is shown
again (`gather()`): the head goes, the cost and the prompt's button come under the questions, the three
phrases are today's, and the panel is open on the last set's way. The row of a run kept from before loses what
it said after the way.

**The page's request.** `/query` is sent `next: {text, chain, set, k, level}`; the label and the lines, which
only the run's row used, are no longer sent. The server reads `set` and `k`, as before.

**Tests.** `test_next_questions.js`: the panel's parts as built; a chain shown again, with sets and a run's row
kept from before; the panel opened and shut; a way picked, its row while it is written, the set that comes
back; the list with the count, the questions shown again with no call; more of a way; no set made; a question
changed, run and marked; the stylesheet's rules. The walk: the panel in the card and within its box, the list's
words, the questions in its place, the list with the counts, a way shown again with no call on the usage
record, *Write more*, the run's row, sets and a row kept from before brought to today's shape in the browser.

## 3. Memory from saved analyses

### 3.1 What counts (agreed)

- A run is memory when it is saved in the current record format. All such runs count.
- Memory reads a run from the thread record: code, outputs, report, parent links. The saved copy of the page is not
  read. The favourite file marks that the run is saved.
- An unsaved run never comes back as a memory.
- A run saved in the old record format is not memory. It stays in Saved workflows and opens as before.
- Three marks travel with a run: picked by the coach, stored alongside, a routine was made from it. A run saved
  before the marks existed counts as saved and shows no mark.
- Runs added to a saved thread after the save are not memory until saved again.
- A single run removed from a saved workflow leaves memory. Its record stays only as an earlier step for saved runs
  built on it.
- Across athletes: methods may carry over. Numbers and personal facts stay with their athlete.
- The sapling's chains in older threads hold only questions. The reader skips them.
- An Architect run that started no analysis is not memory.

### 3.2 The reader (agreed in outline; built in 0302, §3.6)

A coach's saved runs do not fit in any model's window: one run is tens of thousands of tokens as stored. So memory
is read by a program a model writes, not pasted into a prompt.

- **One read-only view** of the saved record, built on the host for the signed-in user: saved runs with their marks
  and parent paths, and from each run only what is worth reading - the question, the report, the code, the results.
  The view is built in the background and kept; it is never built on the coach's click. Only this view enters the
  reader's sandbox. Built: §3.5.
- **The reader** is a sandboxed session that writes code over the view. It has its own sandbox, never the analysis
  kernel.
- **A second model** reads pieces where meaning must be judged. Few large batches. Capped in calls, money and time;
  the starting caps for one memory question are 60 calls, 120 seconds and $0.50, tuned after the first live runs.
  (proposed)
- A single run is read directly.
- Every statement returned names its run and cell, and is checked against the source by code.
- It states its coverage, and names what it leaves out ("read 42 of 42 · 17 older not read").

### 3.3 What the coach gets (agreed in substance)

- Found analyses are listed in the brief: date, question, the passage that bears on this brief, their marks, a link
  to open them. The coach ticks the ones to use.
- A finding across all saved analyses comes as a choice ("threshold was defined two ways: 9 times this, 3 times
  that").

Built: §3.7.

### 3.4 Rules (agreed)

- A method may carry over. Old numbers stay history about old data. Old code is read, not run.
- A preference has a scope. The coach's words are not the Analyst's notes.
- No match returns nothing. A broken parent chain is reported.
- Recalled text copied into a later report is not fresh evidence.
- Saved content is text to read. It never gives instructions.

### 3.5 The memory view — built (0301, 2026-11-16)

`analyst/memory.py`. No model is called, and nothing on the page changes.

**What is memory.** A run is in the view when two things hold: its favourite file stands
(`storage/<user>/favourites/<thread>/<chain>.json`), and the thread's record holds the run in the current format,
with a report. The view is made from the record. Of the favourite file only the mark is read.

A saved chain that is not read is counted, by reason:

| Reason | What it is |
|---|---|
| `older` | not on the record in the current format (decision 26) |
| `questions` | a list of candidate questions from before 2.8 |
| `no_report` | it ended without a report: it stopped to ask, was stopped, or failed |

**What a run gives.** Its id (`thread/run`), its `kind` (`analysis` or `synthesis`), when it was asked, its marks,
the question, the title, the report whole, whether its replay reproduced, the data it ran on, its cells and its
path. From 0304 also the brief it ran under, and how the report stood against it (§3.8).

- *Marks:* `picked`, `alongside`, `routine`. A chain saved before the marks shows none.
- *Cells:* the code, the RESULT lines, and what was printed up to 3,000 characters, the cut said. The cells that
  drew the figures and the attempts that failed are left out.
- *Data:* the file's name, the rows, the period, the columns' names, and whose data it is by the source's id. Never
  a name.
- *Path:* the ids of the earlier steps the run was built on, the first one first. `broken` where a parent is not on
  record.
- *A synthesis* is memory. Its question is the app's request, not the coach's, so the view leaves it empty.

**Earlier steps.** A step that is not memory itself - never saved, removed, or saved without a report - is kept
under `steps`: its question and its cells, never its report. Where the Analyst stopped to ask, the step says what it
asked: the next run's question is the coach's answer. A branch beside a saved run is not in the view.

**How it is kept.** One file per user, `storage/<user>/memory/view.json`, written whole and swapped in.

- `refresh()` brings it up to date. A thread is read again only when its record or one of its favourite files has
  changed, by size and time.
- `refresh_soon()` runs it behind the request: at sign-in, after a save, after a workflow or a chain is deleted. One
  is at work for a user at a time; asked for again meanwhile, it goes round once more.
- `view()` is what a reader gets. It builds nothing.

**What leaves.** `view()` leaves out every run whose favourite file is gone, at the moment it is asked. So a deleted
workflow is out of memory at once, whether or not the kept file has followed. A chain removed from a saved workflow
is no memory; it stays as a step where a saved run was built on it. A run added to a saved thread is no memory until
the thread is saved again.

**Old threads.** A thread begun before the current format keeps its old chains in the same file, before the runs,
and they can be very large. `NotebookStore.read()` reads the file from its `runs` key on. The old part is never
parsed.

**Search.** `search(view, words)` is plain keyword search, and the yardstick for the reader (§4).

- A word is held where a word of the run starts with it, whatever the case. A name in code is split at `_`.
- A word counts most in the question and the title, then in the report and the RESULT lines, then in the code and
  in the questions of the earlier steps.
- A word most runs hold counts for little. A hit far weaker than the best is left out.
- A hit carries up to three passages - of the report, a RESULT line, a line of code - each with where it stands.
- No match returns nothing.

**From the command line.** `python3 tools/memory_view.py` says what each user has saved and what of it is memory;
with `--user`, that user's runs; with words, a search. It writes nothing, and says whether the kept view is up to
date.

**Not there:** the brief of a saved run (0304), anything on the page (0303).

### 3.6 The reader — built (0302, 2026-11-16)

`analyst/reader.py`, with its two instruction texts, `reader.md` and `reader_pieces.md`. Nothing on the page
changes: the Architect asks it from 0303 on. Until then it is asked from the command line.

**One question, one loop.** `read()` puts the view in a sandbox under the name `SAVED` and asks the reader's model
for one action a reply, eight replies at most.

| Action | What it does |
|---|---|
| `CELL` | Python over `SAVED`. What it prints comes back, up to 4,000 characters. |
| `JUDGE` | The second model reads the runs named, or all of them, and answers one question about each with an exact quote. The answers that stand come back, and the sandbox holds them under `JUDGED`, so code can count them. |
| `ANSWER` | What it found. It ends the work. |

A reply that cannot be read costs a reply, and the reader is told why.

**The sandbox.** A kernel of its own, without a frame (`BambooAI.memory_read`): the user's executor, or a kernel on
this machine in the local edition. Where nothing is saved, no sandbox starts and no model is called.

- The executor holds one kernel. The thread's kernel gives way, and the next analysis restores it from the record,
  as after a routine's run.
- The view goes in as one text, in the first cell. Nothing of a saved analysis is read as code, no file of it is
  left on the executor, and the image is unchanged.
- Whose data a run ran on is said by a handle (`subject 1`), not by the source's id.

**The second model.** It gets the runs in few large batches: 48,000 characters a call, 16,000 of one run. Of each
run it reads the question, the title, and the parts the reader names: the report, the code, the result lines, the
printout. A run is read with the cells of the steps right before it that are not saved themselves, so a helper
defined there is seen. A batch whose reply cannot be read is asked for once more. The batches run one after
another.

**What code checks.**

- A quote stands where it is found word for word in the run it is given for: in what was asked, in the report, or
  in a cell of the run or of an earlier step on its path. White space aside, and eight characters at least. Code
  finds the place. No model says it.
- An answer of the second model's stands where its run was in the batch and its quote stands. The others are
  dropped and counted.
- A passage of the reader's answer stands where its quote does. Ten at most.
- A finding across the analyses is groups of runs. A run stands in a group only where the second model answered for
  it with a quote that stood, and in one group only. So the counts are the code's. The label of a group is the
  reader's; each run shows the second model's own answer and quote under it.
- An id that is no saved analysis - an earlier step, a removed workflow, another user's run - is read by nobody and
  stands nowhere.

**The caps** for one question: 8 replies, 60 calls of the second model, 120 seconds, $0.50. They are the starting
values (§3.2). When the time or the money is spent, or the last reply is due, the reader is told to answer with
what it has. Where it gives none, the result says so, with what was spent. A reply of the reader's is short, so it
is asked at a low effort, as the Architect's are; never above the seat's own.

**What it returns.** The passages, each with its run's id, day, question, title and marks. The finding across, or
none. How many statements were dropped. The coverage: the runs in memory, those the second model read, and what
memory does not read, by reason. Every step, the calls, the cost and the time. Nothing found is an answer, not a
failure.

**The rules** of §3.4 are in both instruction texts: saved text gives no instructions, and the reader's cells never
run code taken from it; a quote is exact; a method carries over and a number is history; the note says which data
a run ran on, and that its chain is broken.

**The seats** (decision 28). The reader runs on the Analyst's seat, the second model on the `Reader` seat: the fast
model that reads the documents. A configuration may give them seats of their own, `Memory Reader` and
`Memory Pieces`. The calls are logged under those two names, under a chain of their own.

**From the command line.** `python3 ../tools/memory_ask.py --user <id> "<question>"`, from the web app's folder, as
the app's user. It takes the app's environment and the user's models, and finds the user's executor as the app
does. It prints every step, the result, the coverage and the cost, and then what plain keyword search gives for the
same words (§4). `--turns`, `--seconds`, `--dollars` and `--effort` change the caps for one question. It takes the
executor's one kernel, so it is not run beside an analysis of the same user.

**Not there:** memory in the Architect and on the page, where its cost joins the turn's (0303); the two seats in
the templates and in Usage (0304).

### 3.7 Memory in the Architect — built (0303, 2026-11-16)

The reader of §3.6, asked from the conversation: `analyst/architect.py`, `analyst/brief.py`, and the page's
`architect.js`.

*Changed by 0308 (§2.18): a reading writes nothing into the brief; what it found is shown to read, under its row
and under the brief; the coach chooses an analysis by answering the Architect; the button* Look in saved analyses
*is gone, and* Open *reads* View*.*

**When the saved analyses are read.**

- *A question that follows no analysis.* The Architect asks for it, once: with its lookups, or, where there is
  nothing to look up, in place of saying that the brief is ready (`"recall": true` in its reply). It is told how
  many saved analyses the coach has (`SAVED: 12`), and asks only where there are some.
- *A follow-up.* Only the coach asks (decision 19).
- *The coach's button*, on any brief that can still be changed: **Look in saved analyses**, under the brief's
  parts. It is there while the coach has saved analyses. The request is said in the conversation and the reading
  starts at once; the Architect replies after it.
- One reading after a message of the coach's, two in a brief. Then the button goes.

**What the reader is given.** The question and the brief as it stands. No model writes a question for it. Its caps
are those of §3.6.

**While it reads.** A row in the conversation, in the place of the Architect's wait, says what is being done:
*SEARCHING MEMORY · 0 of 12 read*, then *5 of 9 read* as the second model goes through the runs it was given
(decision 48; until 0311 the row began *SAVED analyses*, which read as something saved). The composer is held and
says that the saved analyses are being read. **Skip** ends the reading before its next call: the row - *MEMORY*,
once the reading is done - then says *skipped*, and the Architect goes on. A reading that could not be made says
why in its row; the Architect's reply before it stands.

**What comes back.** A turn of the conversation: the passages, the finding across the analyses, how many are saved
and how many were read, what was dropped, the seconds and the cost. Its row reads *2 passages found · read 9 of
12 · 38 s*; the passages and the finding show on hover. The next exchange, with nothing said, gives it to the
Architect.

**In the brief.** Code puts the passages under **From saved analyses**, each with an empty box (decision 22), as
one version: *the Architect, from your saved analyses*. A line shows the day and what was asked then, the passage,
the reader's note, where it stands, whose data it ran on and which, and how it was saved. **Open** shows that
analysis in a dialog over the page: its report, and the code of its cells folded under it. A cross leaves a passage
out; its words cannot be changed (§2.6). Six passages at most, and one that is there is not added again.

**Whose data.** The name beside a passage is for the coach. It is taken from the thread's record when the passages
come back: the memory view holds no name, and no prompt carries this one. Where the data loaded now and the
passage's run both name a person and the two differ, the brief keeps that too, and the Analyst is told *another
person's data* - not whose. A passage is quoted as written, so a name inside it stays.

**What the Architect does with them.** It says how many were found and that the coach ticks the ones to test. It
writes nothing from a passage into another part of the brief and marks no line by one: an earlier result is a
claim for the analysis to test. Where the saved analyses went more than one way on something the brief leaves open
under *Fixed before the run*, it asks which way, with the ways as choices.

**What the Analyst receives.** The ticked passages and no other, in its BRIEF block, under *Saved analyses the
person chose (earlier results: claims to test, not evidence)*: the day, what was asked, where the passage stands,
the passage, the data, and that it is another person's where it is. The run keeps them on its brief. Its
contract says what such a passage is: a method may carry over; a number is history about the data it ran on, and
no result of this run.

**The money.** The reader's calls are logged under the brief's own chain, as *Memory Reader* and *Memory Pieces*,
and are charged with it, as the Architect's are.

**The routes.** `POST /architect/say` takes `look: true` for the coach's request, and its stream carries the count
as the reading goes. `POST /architect/skip`. `GET /architect/saved/<thread>/<run>` gives one saved analysis as
memory holds it; one that is saved no more is not found. The framing keeps how many saved analyses the coach had
at the last exchange (`saved`), which is how the page knows whether to offer the button.

**Not there:** the Analyst reads the passage, not yet the analysis it comes from: opening what the brief names,
the brief saved with a saved analysis, and the two seats in the templates and in Usage are 0304 (§3.8).

### 3.8 What the brief names, the brief in memory, the seats — built (0304, 2026-11-16)

**The Analyst opens what the brief names.** In its BRIEF block each saved analysis the coach ticked a passage from
is one numbered line: the day, what was asked, what it ran on, then the passages with where each stands. `SHOW SAVED
<k>` opens the k-th: what was asked, the brief it ran under, the report, and the code and result lines of the cells
along its thread up to its own (`reader.shown`), since a passage can stand in any of them and a name its code uses
may be made in an earlier step. A line above it says which analysis it is, and that it ran on another person's data
where the brief says so; no name is added, and the analysis itself is shown as written. One that is saved no more
says so. Where the brief names none, `SAVED` is no form of `SHOW`. The Analyst reaches nothing else of memory: only
what the coach ticked (decision 7).

One analysis a turn, in the next prompt only, whole up to 60,000 characters (`SAVED_VIEW_CHARS`); of a longer one
the middle goes, and the prompt says that part is not in view. The sizes decide this. A deep analysis holds some
twenty cells: about 40,000 characters of code under a report of 10,000. The 16,000 characters the second model
reads of a run would show the report and two cells. And a view of that size cannot stay in every later prompt, as
a chain re-opened with `SHOW RUN` does: the Analyst's note carries what it takes from it, and the action opens it
again.

Its contract for a run under a brief says what to do with it: a method may carry over, written anew, since the
names of the saved analysis are not in its kernel; a number is history about the data it ran on, and no result of
this run. The report may state such a number: one that stands in a saved analysis the run opened is not held
against the report as a number no cell printed.

**The brief in memory.** A saved run that was framed holds its brief in the view: what was agreed, a line for each
part that held something - no heading, nothing for a part left open, none of the checks every run makes
(`briefs.render(brief, record=True)`) - and how the report stood against it (`brief`, `outcome`: the verdicts on
what was expected and on what would change the coach's mind). The reader can search it, have the second model read
it (`parts: ["brief"]`), and quote from it: a passage then stands *in its brief*. Plain keyword search reads it
too; there a word counts as in the report. On the page, **Open** shows the brief folded under the report, before
the code - and the code is that of the cells along the thread up to the run's own, where it was the run's own
alone: a passage that stands in an earlier step's cell is in the dialog. The kept view is in a new format, and is
built again once.

Nothing new is saved for this: the brief and the framing conversation were on the thread's record already, and a
saved workflow opens with its Brief tab (§2.11). The walk now checks that.

**The seats.** The configuration template gains `Architect`, `Memory Reader` and `Memory Pieces` in each tier: the
first two on the tier's Analyst model, the third on the model that reads the documents, each at a low effort
(decision 28). A configuration without them works as before: the Architect and the reader fall back to the
Analyst's seat, the second model to the `Reader` seat. In Usage a reading made for a brief is part of that brief's
analysis; one asked from the command line is a chain of its own, *Saved analyses read*.

### 3.9 The conversation in memory — built (0306, 2026-11-17)

Decision 31. A saved analysis that was framed has a conversation: what the person and the Architect said before
it ran. The record held it already (`Run.framing`); the view now holds it too, so the reader can search it and
quote from it, and the tutor can say what the person wanted and knew then.

- **The view** (`memory.FORMAT` 3). A run holds `conversation`: each message under `Person:` or `Architect:`, the
  question as it was first asked before them; `""` where the run was not framed, or framed without a word said.
  Up to 40,000 characters (`SAID`), the cut said. What was looked up or read meanwhile is no part of it: the brief
  holds the marks, and a passage of another analysis stands in its own.
- **Search.** `search()` reads it, at the brief's weight, and a passage can be a line of it.
- **The reader.** `conversation` is a part the second model can be given (`PARTS`), under `CONVERSATION:` after
  the report, and a place a quote can stand in (`places()`); a run of words the brief holds too stands in the
  brief. `reader.md` lists the key, and asks that the note of such a passage says who said it: it is something
  said, not something found.
- **The page.** `/architect/saved` returns it, and the Open dialog folds it under the report, before the brief.
- **The Analyst.** `SHOW SAVED k` does not show it: the passage the coach ticked is in the BRIEF block with where
  it stands, and the analysis is opened for its method.

A conversation is memory when its analysis is saved. One that was never run, or run and not saved, is not.

## 4. How we will know it works

**The Architect** (agreed in substance)

- Scripted cases with a false premise in the question: a block that was not heavier, a period the data does not
  cover, a change of equipment. A case passes when the brief shows the anchor as *does not hold* before the analysis
  starts. Each case is also run without the Architect, for comparison.
- Scripted reports: the *met / not met / cannot tell* mark is right, and a planted misfit appears under *Did not fit*.
- Next questions: on a scripted thread with a planted misfit and an unchecked anchor, the level that reads each
  returns a question from it. A candidate that is run starts a new analysis at once, and the map gains one box.
- A change in place makes a new version and calls no model.

**Memory**

- Saved and unsaved runs, a run stored alongside, a helper defined in an earlier run, a sibling branch, a missing
  parent, another athlete or period, no relevant history, a removed workflow, an instruction hidden in saved content.
- Two kinds of question: find one analysis, and read across all of them.
- Plain keyword search over the same view is the yardstick. The second model stays only where the reader beats it.
- Never allowed: another user's run, an unsaved run, a wrong branch, a removed workflow.

**As always:** the battery, the stack walk, the screens. A scripted model stands in for the live one; what a live
model writes for the Architect and for the reader is judged on the dev box, patch by patch (§7).

## 5. Retiring the old memory — built (0294, 2026-11-15)

The memory BambooAI had was the knowledge pack: cards a model distilled from a run when the coach saved it with a
rating of 5 or more, kept in `memory/<user>/memory_pack.yaml`, read by the Analyst through `RECALL`, and reviewed in
the Memory dialog. All of it is gone.

- **The engine.** `bambooai/knowledge_pack.py`, `bambooai/embeddings.py`, `bambooai/template_formatting.py` and
  `scripts/ttl_to_memory_pack.py` are deleted. `BambooAI(...)` no longer takes `memory_path`. The Analyst's contract
  no longer offers `RECALL`; a reply that uses it is told it is no action, like any unknown word. The distiller's
  prompts are gone.
- **The web app.** The routes `/submit_rank`, `/memory/review`, `/memory/review/action` and `/storage/favourites`
  are removed, with the memory steps inside saving and deleting. `BAMBOO_MEMORY_DIR` and the `memory/` folder are no
  longer read or made.
- **The page.** The Memory button and its dialog, and the rating dialog, are removed. **Save as favourite is one
  click:** the menu item saves at once and the page says so; no rating is stored. The Save pill is `#saveButton`. A
  saved chain's badge in Saved workflows says how it was saved: by the coach, or with its thread.
- **The models.** The Knowledge Distiller seat leaves the configuration templates. A box's own configuration may
  keep the seat; nothing reads it.
- **What still reads the past.** A thread recorded before 2.8 may hold `RECALL` steps: its saved pane shows them as
  stored, and the notebook view still names the step. The Usage dialog keeps its label for the Distiller's past
  calls.
- **The boxes.** The stored card files (`web_app/memory/`) are deleted at deploy. Nothing reads them. The ignore rule
  for that folder stays in `.gitignore`, so a checkout that still holds them never commits them.

The removed `memory_path` option of the library is why the release is 2.8.0 and not a patch release.

## 6. Parts touched by the release

- The Analyst's contract and session: the brief comes in, `RECALL` and the ideas path go out, the report gains two
  parts. The step that draws the figures reads the ones agreed in the brief (0309), and the cell that drew their
  draft (0310).
- New in 0310: the draft of the figures (`analyst/draft.py`), its plots beside the thread's record, a time limit
  for a script on the coach's own machine.
- New in 0313: the question read before its analysis (`analyst/cold.py`, `analyst/cold.md` - in the package
  data), and the closing card's shape.
- New in 0314: Next questions as a panel in the closing card (the page only).
- The thread record: the brief, the framing conversation and the next questions are stored with the run.
- New: the Architect, the memory view, the reader.
- The web app: routes for framing and next questions; the memory routes removed.
- The page: the conversation, the Brief tab, the switch, changing in place, the Next questions button and cards,
  the two report parts; the plant button in the question box, the Explore tab, the Memory and rating dialogs removed.
- The thread map: one box per question, marked Architect or next question. The sapling's box is no longer made.
- Models: seats for the Architect, the reader and its second model; the Knowledge Distiller seat removed.
- The usage record and dialog: the new seats.
- README, design documents, tests.

## 7. The build

The brief works by hand before the Architect talks, and memory is readable before a model reads it, so each part can
be judged on its own. Every patch leaves the app working. Until the release steps are taken the series goes to the
private repository and the dev box only; what the live tests change comes as patches after 0305, and the tag goes
on the last one.

| Patch | Ships | State |
|---|---|---|
| 0294 | The old memory goes (§5). Save as favourite is one click. | built |
| 0295 | The brief, in the engine: stored with its run; the Analyst follows it, and stops and asks where it cannot; the report gains *Against the brief* and *Did not fit* (§2.10). | built |
| 0296 | The brief, on the page: the switch, the Brief tab, changing lines in place, versions, Start analysis, the two report parts, the box's mark on the map. The coach fills the brief by hand (§2.11). | built |
| 0297 | The Architect talks: it fills the brief from the question and asks for what is missing, one question a message, with choices to click (§2.12). | built |
| 0298 | Lookups: what the frame rests on is checked against the data - count, list, total; anything else is refused. The marks (§2.13). | built |
| 0299 | Other explanations: after the check the Architect proposes at most two, each unticked until the coach accepts it (decision 22). Split from 0298, so the lookups are judged on their own (§2.14). | built |
| 0300 | Next questions: the button on the closing card, the five levels, five cards, change and run from the card. The Explore tab and the Analyst's ideas path go (§2.15). | built |
| 0301 | The memory view: the saved runs in the current format as one read-only view; the removal rules; plain keyword search. No model (§3.5). | built |
| 0302 | The memory reader: a sandboxed session over the view, the second model on pieces, the caps, statements checked against the source. Asked from the command line (§3.6). | built |
| 0303 | Memory in the Architect: the row with its live count and Skip, the passages found in the brief to tick, Open, *Look in saved analyses* (§3.7). | built |
| 0304 | The Analyst opens a saved analysis the brief names. The brief of a saved analysis is memory. The new seats in the templates and in Usage. README (§3.8). | built |
| 0305 | Release 2.8.0. | built |
| 0306 | After the first live run: the Architect as a tutor, the question said back, the conversation of a saved analysis in memory (§2.16, §3.9). | built |
| 0307 | After the second live run: the question is the coach's to take; the Analyst gets what was agreed; a reading on a follow-up, and no request passed over in silence; a follow-up starts clean; a part of the analysis before is opened on request; the Brief tab in plain words (§2.17). | built |
| 0308 | From the product owner's test of 0307: the question changes as the conversation goes, with no step to take it; the version on screen is the one in use, for an answer, a change and Start analysis; the brief shows only the parts that hold something, with one + Add; what a reading found is shown to read in both panes, and an analysis is chosen by answering (§2.18). | built |

| 0309 | The product owner's idea after testing 0308: the figures sketched before the run. The Architect describes each figure and the Brief tab draws it - grey where the data decides, a line known in advance from rough points. The Analyst and the step that draws read the agreed figures; code holds their titles (§2.19). | built |
| 0310 | From the product owner's test of 0309: the sketches looked like nothing. A draft of each figure, drawn by a cell a model writes and the sandbox runs with no data - computed where a rule gives the shape, on made-up numbers, marked, where the data will; what a saved analysis drew; the draft's cell handed to the step that draws; the model's own points gone (§2.20). | built |
| 0311 | From the product owner's live test of 0310, "a little too busy": no picture of a saved analysis in the brief; a grey window with one line where a figure has no draft, in place of the sketch; the rows in flight say what is being done; a figure's note is no longer cut at 240 characters (§2.19, §2.20, §3.7). | built |
| 0312 | From the product owner's live test: the Answer is what goes to other people - what the report says against the brief leaves it, in both versions and in the export, for the foot of the run's Brief tab (§2.21). | built |
| 0313 | From the product owner's live test: the question is written for the Analyst and points to nothing it is not given; before an analysis starts its question is read as the Analyst will read it, and what cannot be placed goes back to the Architect (§2.22). The closing card: the numbers beside the title, two buttons, no links (§2.23). | built |
| 0314 | From the product owner, of the list of five levels: Next questions are a panel inside the closing card - what the questions are, the five ways with a sentence each, the questions of the way picked in the list's place; the row a run opens on says the way only (§2.24). | built |

## 8. Not in this release

- Search by meaning (embeddings), unless keyword search is shown to miss.
- Labels guessed by a model.
- A rewritten, offline copy of the record (a wiki).
- Voting between several reader programs.
- Memory for the Analyst or for routines.

## Sources

- How experts make sense of a situation: [How Experts Sensemake](https://commoncog.com/how-experts-sensemake/),
  [Part 1](https://commoncog.com/how-to-make-sense-of-ai/),
  [Part 3](https://commoncog.com/how-to-improve-at-sensemaking-ai/);
  [Kahneman and Klein 2009](https://pubmed.ncbi.nlm.nih.gov/19739881/).
- Reading a large record with a program: [Recursive Language Models](https://arxiv.org/html/2512.24601v2),
  [SRLM](https://arxiv.org/html/2603.15653v1), [the authors' library](https://github.com/alexzhang13/rlm).
- Search over the original record: [ReFind](https://arxiv.org/html/2608.12888),
  [GAM](https://arxiv.org/html/2511.18423v1), [JAM](https://arxiv.org/html/2609.34385),
  [Memory Tax](https://arxiv.org/html/2610.34073v1),
  [When Users Don't Ask](https://arxiv.org/html/2609.03467v1).
