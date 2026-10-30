# The Usage dialog — design v1.0 (2026-10-31; step 1 built in patch 0255)

The Usage dialog is where a coach, or the operator, sees what the analyses cost and where the money and the time
went. The version from the first redesign (two Plotly charts in a mid-size dialog, four totals, three pre-aggregated
day series) was judged subpar by the product owner on 2026-10-30: the legend overlapped the bars, the dialog was too
small to tell the nuances apart, and the information was thin for a product whose point is transparency. This
document is the rebuild: what is recorded, what the route answers, what the dialog shows, and in what order it is
built. The mockups it was agreed on are in the product owner's hands (B, the tabs, with C, the ledger with a detail
pane, as its Analyses tab); the design below is theirs made precise.

## 1. What the dialog answers

In the order a person asks:

1. What did this period cost, and is it more than the period before?
2. Where did it go - by seat (the role the analyst played: the Analyst writes the cells, the Reviewer judges them, the
   Reader reads documents, the Coder codes the context, the Promoter makes routines, the Figures seat draws…), and by
   model?
3. What did each question cost, how long did it take, and did it come out right?
4. Is the prompt cache working - what share of the input was served from it, and what that saved?
5. On the hosted service, what did the compute charge come to?

Everything is computed from the call records; nothing on the dialog is written by a model, and the dialog says so.

**The dollars are the same for the coach and the operator.** The hosted service passes the model cost on exactly;
its margin is the compute charge. So one dialog serves both editions: the model cost in dollars everywhere, and a
Compute tile beside it where a compute charge exists.

## 2. The records

One row per model call in `usage`, written by the logger (`bambooai/log_manager.py`, `_write_to_database`) through
`insert_usage_with_chain` - the hosted function on Supabase, `LocalStore.rpc_insert_usage_with_chain` in the
self-hosted edition, the stack's stand-in on the test stack. The row had: the seat (`agent`), the chain, the
timestamp, the model, the prompt and completion tokens, the elapsed time, tokens per second, the cost, and on the
hosted side the compute tier and the query cost. **Since 0255 it also keeps** what the logger computes at the call
and had only written to the JSON run log:

| column | what |
|---|---|
| `cached_tokens` | prompt tokens served from the provider's cache |
| `cache_write_tokens` | prompt tokens written to the cache (Anthropic's write premium) |
| `cache_savings` | what the same prompt would have cost uncached, minus what it did - negative on a write-heavy turn |
| `search_fee` | the grounding-search fee inside the cost |
| `image_fee` | the image-output fee inside the cost |

The five are NULL on rows from before 0255 and on rows an older app writes: the dialog reads NULL as *not
recorded*, never as zero. The hosted table takes `docs/sql/usage_cache_fields.sql` once (the columns, and the
function replaced - its owner and grants kept); the local SQLite file adds the columns on its first opening
(`LocalStore._upgrade`). Both were proved on a scratch Postgres 16 loaded with the hosted project's schema dump,
with an old payload and a new one through the function.

What is *not* recorded per call, and where it comes from instead: the question, the mode (Quick / Deep / Adaptive),
the cells and the outcome of an analysis live in the thread store (`storage/<user>/threads/`), keyed by the chain
id the usage rows carry; the route joins them (step 2). A routine's run is a chain like any other, named by its
routine. What the call was *for* (a cell, the report, the review, the replay) is not kept and not needed yet: the
seat says most of it.

## 3. The route (step 2)

One answer, `/usage?period=…&compare=1`, computed server-side from the rows of the period (and of the period
before, for the deltas) and the thread store:

- `period`: the window, its label, the edition (self-hosted / hosted with the tier);
- `totals` and `before`: model cost, analyses, calls, tokens in (and the cached share), tokens out, model time, cache
  savings, compute (hosted) - the tiles, with the period before for the deltas and the day series for the sparklines;
- `days`: one entry per day (or hour for the 24-hour period) with the cost, tokens, calls and time split by seat,
  by model and by mode - the chart under its two selectors;
- `seats` and `models`: the tables - calls, tokens in and cached share, tokens out, cost and share, time per call,
  tokens per second; a model's list price per million from the configuration;
- `analyses`: the ledger - per chain: when, the question, the mode, the cells, the calls, the tokens, the time, the
  cost, the seat split, the outcome (answered / reproduced / failed at cell n / refused / ran, for a routine);
- `calls` for one analysis on request (`/usage/analysis/<chain>`): the detail pane's seats ranked, the calls in
  time, the models;
- `/usage/export.csv`: the rows of the period, one per call, as recorded.

Periods: 24 hours, 7, 30, 90 days, this month, last month. The old `/usage_tracking` route and its three series
retire with the old dialog.

## 4. The dialog (step 2)

The routines manager's size (1240px, 90% of the height). Tabs: **Overview**, **Seats & models**, **Analyses**,
**Calls**. The header: the period, the compare-with-the-period-before toggle, Export CSV.

- *Overview*: the tiles (model cost, analyses, model calls, tokens in with the cached share and the savings, tokens
  out, model time; compute on the hosted service), each with its delta against the period before and a sparkline;
  the chart - one column a day, stacked by seat, model or mode, measuring cost, tokens, calls or time - with the
  legend as a table beside it (name, amount, share; a click isolates one) and a tooltip per column; three computed
  lines of *what stands out* (the heaviest day and what made it, the cache, the failures).
- *Seats & models*: the two tables, sortable, with a thin bar per row for the share.
- *Analyses*: the ledger on the left - every question with what it cost, grouped by day, searchable, by date or by
  cost - and the detail pane on the right for the one picked: its figures, its seats ranked, the calls laid out in
  time (one row per seat, a mark per call; hover for the model, tokens and cost), its models; *open the analysis*
  opens the thread.
- *Calls*: the raw rows of the period, paged.

The charts are the page's own SVG (as the sparklines and the code map are), not Plotly, which stays for the
analyst's figures: thin columns (24px at most), a 2px gap of the surface between segments, the top segment's corners
rounded and the baseline square, hairline gridlines, text in the text tokens never in a series colour. The seats'
colours are a fixed order over a palette validated for colour-blind readers against both themes' surfaces
(`#3987e5 #d95926 #199e70 #c98500 #d55181 #008300 #9085e9` on dark, `#2a78d6 #eb6834 #1baf7a #eda100 #e87ba4
#008300 #6250d6` on light); the six largest seats carry a colour, the rest fold into *Other*, and a seat keeps its
colour whatever the filter. Numbers in tables are tabular; large figures in tiles are not.

## 5. Build order

1. **The records** - built (0255): the five columns, the writer, the local upgrade, the stand-in, the migration.
2. **The route and the dialog** - sections 3 and 4; the old route and dialog retired; Plotly left to the figures.
3. **The walks and the notes** - the stack walk opens the dialog after its runs and checks the figures against the
   rows; the plain-words doc; the handover.

## 6. Decisions

- One dialog for both editions; the dollars equal for coach and operator (the product owner, 2026-10-31).
- Rows from before read as *not recorded* rather than being backfilled from the run logs: the logs are per box and
  rotate; the dialog says plainly from when the cache was recorded.
- The seats' colours fold the tail into *Other* at six, by the palette's validated limit, rather than growing hues.
- A migration is run on a scratch Postgres loaded with the project's schema dump before it touches a project - the
  dump is untracked (docs/OSS_DESIGN.md D14) and the only record of the hosted constraints (2026-10-30, the
  uniqueness the keys-per-athlete migration had missed).
