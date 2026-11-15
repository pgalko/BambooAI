# The Architect and memory from saved analyses — design v0.12 (2026-11-16; built: the old memory retired, 0294; the brief in the engine, 0295, and on the page, 0296; the Architect talks, 0297, checks what the brief rests on, 0298, and proposes other explanations, 0299)

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
| 19 | On a follow-up through the Architect, saved analyses are looked up only when the coach asks. |
| 20 | The five candidate questions are kept with the analysis they follow. |
| 21 | A lookup may count, list or total what is there, to check an anchor. It may not compare, model or test. |
| 22 | What the Architect proposes, and each saved analysis it finds, stays unticked until the coach accepts it. |
| 23 | A candidate question runs straight from its card: the coach picks one, or changes it slightly, and runs it. A new analysis starts. |
| 24 | The thread map records a single box for it. Each Architect run is also a single box, however many turns it took, on follow-ups too. |
| 25 | An Architect run and the analysis it starts share one box. |
| 26 | Saved work in the old record format is left out. Memory starts from what was saved in the current format, and grows from there. |
| 27 | The memory defaults of §3.1: the three marks, runs added after a save, a single run removed, across athletes, what is not memory. |
| 28 | The Architect and the memory reader use the Analyst's model of the chosen tier. The reader's second model uses the fast model the Knowledge Distiller seat used. |

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

### 2.7 Next questions: the sapling in the Architect (agreed, details proposed)

How the sapling works until then:

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

Proposed:

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
- **After the analysis** the Answer tab shows *Against the brief* and *Did not fit*.
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
state reads "not said".

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
the fact beside it when it was checked, and who brought it in when that was not the coach.

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
the framing folds to one row above the run, the Brief tab stays to be read, and the closing card links to it. The
tab's markup carries the versions, so a saved or restored chain still steps through them.

**The report on the page.** The part *Against the brief* is shown as a card in the answer (`dressAnswer`): a row for
what was expected and a row for what would change the coach's mind, each with its verdict, then a row for each
check. A check line that says "cannot tell" is marked. A part the card cannot hold whole, such as a table, is left
as the report wrote it. *Did not fit* stays the report's own section. The plain-language version and the export
show the same card.

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

### 3.2 The reader (agreed in outline, details proposed)

A coach's saved runs do not fit in any model's window: one run is tens of thousands of tokens as stored. So memory
is read by a program a model writes, not pasted into a prompt.

- **One read-only view** of the saved record, built on the host for the signed-in user: saved runs with their marks
  and parent paths, and from each run only what is worth reading - the question, the report, the code, the results.
  The view is built in the background and kept; it is never built on the coach's click. Only this view enters the
  reader's sandbox.
- **The reader** is a sandboxed session that writes code over the view. It has its own sandbox, never the analysis
  kernel.
- **A second model** reads pieces where meaning must be judged. Few large batches. Capped in calls, money and time;
  the starting caps for one memory question are 60 calls, 120 seconds and $0.50, tuned after the first live runs.
  (proposed)
- A single run is read directly.
- Every statement returned names its run and cell, and is checked against the source by code.
- It states its coverage, and names what it leaves out ("read 42 of 42 · 17 older not read"). (proposed)

### 3.3 What the coach gets (agreed in substance)

- Found analyses are listed in the brief: date, question, the passage that bears on this brief, their marks, a link
  to open them. The coach ticks the ones to use.
- A finding across all saved analyses comes as a choice ("threshold was defined two ways: 9 times this, 3 times
  that").

### 3.4 Rules (agreed)

- A method may carry over. Old numbers stay history about old data. Old code is read, not run.
- A preference has a scope. The coach's words are not the Analyst's notes.
- No match returns nothing. A broken parent chain is reported.
- Recalled text copied into a later report is not fresh evidence.
- Saved content is text to read. It never gives instructions.

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
  parts.
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
be judged on its own. Every patch leaves the app working. Until the release patch the series goes to the private
repository and the dev box only.

| Patch | Ships | State |
|---|---|---|
| 0294 | The old memory goes (§5). Save as favourite is one click. | built |
| 0295 | The brief, in the engine: stored with its run; the Analyst follows it, and stops and asks where it cannot; the report gains *Against the brief* and *Did not fit* (§2.10). | built |
| 0296 | The brief, on the page: the switch, the Brief tab, changing lines in place, versions, Start analysis, the two report parts, the box's mark on the map. The coach fills the brief by hand (§2.11). | built |
| 0297 | The Architect talks: it fills the brief from the question and asks for what is missing, one question a message, with choices to click (§2.12). | built |
| 0298 | Lookups: what the frame rests on is checked against the data - count, list, total; anything else is refused. The marks (§2.13). | built |
| 0299 | Other explanations: after the check the Architect proposes at most two, each unticked until the coach accepts it (decision 22). Split from 0298, so the lookups are judged on their own (§2.14). | built |
| 0300 | Next questions: the button on the closing card, the five levels, five cards, change and run from the card. The Explore tab and the Analyst's ideas path go. | |
| 0301 | The memory view: the saved runs in the current format as one read-only view; the removal rules; plain keyword search. No model. | |
| 0302 | The memory reader: a sandboxed session over the view, the second model on pieces, the caps, statements checked against the source. | |
| 0303 | Memory in the Architect: the row with its live count and skip, found analyses in the brief, "look now" on follow-ups. | |
| 0304 | Saving, usage, documents: the brief saved with a saved analysis; the new seats in the usage record and the templates. | |
| 0305 | Release 2.8.0. | |

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
