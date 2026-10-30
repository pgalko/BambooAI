# The Usage dialog — design v1.1 (2026-10-31; step 1 built in patch 0255, step 2 in 0256)

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

## 3. The route (step 2, built in 0256: `web_app/usage_routes.py`)

One answer, `GET /usage?period=…&compare=1&tz=…`, computed from the rows of the period (and of the period before,
for the deltas) and the thread store; `tz` is the page's offset in minutes east of UTC, so the days are the
person's own (the rows' timestamps are UTC). Periods: `24h`, `7d`, `30d`, `90d`, `month` (this month so far),
`last_month`; a window ends at the end of today (or of the current hour) and the period before is the same length
immediately before it. The answer:

- `period`: the window (start, end, bucket day or hour, the label, the period before), the edition and the tier
  (hosted: the subscription's compute tier), and `truncated` when the period held more rows than one answer
  aggregates (50,000: the figures stop there and the dialog says so);
- `totals` and `before`: cost, calls, chains, tokens in and out, model time, the cache (`cached`, `written`,
  `savings`, and `recorded_in`/`recorded_calls`: the input and the calls that carry the cache fields - the cached
  share is over those, never over rows that predate 0255), the fees, `compute` (the hosted charge, `query_cost`
  taken once per chain from its rows) and `compute_chains`;
- `days`: one entry per bucket with its totals and its split by seat, by model and by mode, each as
  `[cost, tokens, calls, time]` - the chart, whose legend sums them on the page;
- `seats` and `models` (by cost): calls, chains, tokens in and out, the cached share over the recorded rows, cost,
  time, tokens per second (out over model time); a model's provider and list price per million from the
  configuration (`LLM_CONFIG.json`, the user's or the box's; nothing when it has no entry);
- `analyses`: the ledger, one entry per chain of the period, newest first: when (UTC), the thread, the kind
  (`analysis`, `ideas`, or - for a chain the thread store does not know - `routine` for the Promoter's Save-as-routine
  call, `context` for the Coder's pass, `reading`, `memory`, `other`), the question and the title, the mode, the
  cells and figures, the outcome (`answered`, `reproduced`, `differed`, `replay failed`, `failed at cell n`,
  `refused`, `stopped`, `asked`, `running`), the wall time (first turn to last), the calls, tokens, cache, time,
  cost, compute, the cost per seat, and `saved` - whether the chain's favourite file exists, since the page opens a
  chain from it (an unsaved analysis shows "not saved" instead of the link);
- `stands_out`: three computed lines - the heaviest day (its share, its analyses, its top seat, its dearest
  question), the cache (the share and the savings over the calls that recorded it; the seats with the highest and
  the lowest share among those with 10k recorded input tokens), the failures (and the refusals, the stops).

The thread store is read through the `chains` and `threads` tables (two plain selects by id, in batches; no embed,
so the SQLite file, the hosted service and the stack's stand-in answer alike) and one thread file per thread of
the period, its facts cached per file by modification time. `GET /usage/analysis/<chain>` answers one chain: its
ledger entry, totals, seats ranked, models, and the calls in time (seconds from the first, the elapsed, the model,
the tokens, the cache, the cost, the fees) with the span. `GET /usage/calls?period=…&page=n&size=100` pages the raw
rows newest first; `GET /usage/export.csv?period=…` is the rows of the period as recorded, one per call, as an
attachment (the page fetches it with the session's token and saves the blob). The old `/usage_tracking` route, its
aggregation in `auth/supabase_client.py` and `usage-tracking.js` retired with the old dialog; `LocalStore` took
`in_()`; the stack's stand-in took real `gte/lte/gt/lt/range` and several `order()` keys.

## 4. The dialog (step 2, built in 0256: `web_app/static/js/usage.js`, the rules in `dialogs.css`)

Built by the script on first opening (`#usageModal`, no markup in the page), the routines manager's size (1240px,
90% of the height). Tabs: **Overview**, **Seats & models**, **Analyses**, **Calls**; the header: the period, the
compare-with-the-period-before toggle (it names the length), Export CSV. The tabs stay while a long tab scrolls.

- *Overview*: the tiles - model cost, analyses, model calls, tokens in (the cached share and the savings, or "cache
  not recorded"), tokens out, model time, and Compute on the hosted edition - each with its delta against the period
  before (an arrow and a percentage, a multiple beyond tenfold; neutral in colour: a comparison, not a verdict) and
  a sparkline over the days; the chart - one column a day (an hour for 24 hours), stacked by seat, model or mode,
  measuring cost, tokens, calls or time - with the legend as a table beside it (name, amount, share, the total; a
  click isolates one series, a second click releases it) and a tooltip per column (the day's cost, analyses, calls,
  tokens and time, then the split); the three lines of *what stands out*.
- *Seats & models*: the two tables, sortable by a click on a heading, a thin bar per row for the share of the cost;
  a dash where the cache was not recorded or the configuration has no price.
- *Analyses*: the ledger on the left - every chain with what it cost, grouped by day (with the day's count and cost)
  or flat by cost or by time, narrowed by a word of the question or the title, a mode, an outcome - and the detail
  pane on the right for the one picked: the question and the title, its meta line with the outcome and *open the
  analysis* (when saved), the figures (cost, tokens in with the cached share, tokens out, model time of the wall
  time, cache savings, the compute charge), the seats ranked with bars, the calls laid out in time (one row per
  seat, a mark per call at its second and as wide as it took; hover for the model, tokens, cache, cost and fees),
  the models.
- *Calls*: the raw rows of the period, 100 a page, newest first; a chain is a link into the ledger.

The charts are the page's own SVG. A series colour is a class (`us-s1`…`us-s7`, `us-s0` for Other) over the
`--viz-1`…`--viz-7`/`--viz-other` tokens in `tokens.css` (the validated palette, a set per theme), so the fills and
the swatches follow the theme without a redraw. The seven slots go to the keys ranked by the measure over the
period; beyond seven the tail folds into *Other* (a sole eighth is not folded); the same ranking colours the
tables, the detail pane and the timeline, so a seat keeps its colour across the dialog. Columns are 24px at most
with a 2px gap of the surface between segments, the top segment's corners rounded when it is tall enough and the
baseline square; gridlines are hairlines at round steps; text is in the text tokens. The foot states the rule
(list prices applied to the tokens each call reported; the models' own time; every number from the records,
nothing written by a model) and adds a line when some calls of the period predate the cache fields or the answer
stopped at its row limit.

## 5. Build order

1. **The records** - built (0255): the five columns, the writer, the local upgrade, the stand-in, the migration.
2. **The route and the dialog** - built (0256): sections 3 and 4; the old route, its aggregation and `usage-tracking.js`
   retired; Plotly left to the analyst's figures; `tools/usage_fixture.py` (a synthetic month through the route, made
   when the gallery misses it) feeds the gallery's `dlg_usage` and `dlg_usage_analyses` states.
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
- The days are the person's own (the page sends its offset); the rows stay UTC. The old dialog cut days at UTC
  midnight, which split a coach's evening across two days.
- A chain is opened from its saved favourite, as the thread list does; the ledger says `saved`, and an unsaved
  analysis shows "not saved" rather than a link that would answer 404.
- A routine's run makes no model call and so has no row here; the Promoter's Save-as-routine call does, under its
  own billing chain, and the ledger names it. The deltas carry no colour: more analyses is not better or worse.
- What the call was *for* (a cell, the report, the review) is still not recorded; the seat says most of it, and
  the detail pane's timeline shows the order.
