# Intervals.icu: where the words live — an inventory against the live API (2026-10-13)

What the Intervals.icu API exposes of an athlete's and a coach's *words* and *flags* — the qualitative side of the
context phase — field by field, so the design names only what exists. The companion of `CONTEXT_DESIGN.md`.

## 0. Sources

- **The live OpenAPI specification**, downloaded from the Swagger page on 2026-10-13 (`openapi: 3.0.1`, 117 paths,
  110 schemas), diffed against a copy committed to a public repository on 2025-09-01 (104 paths, 96 schemas). Every
  field name, type and enum below is from the live file. What the year added that matters here: **chats** (`GET
  /athlete/{id}/chats`, `GET /chats/{id}`, `GET /chats/{id}/messages`), **`GET /athletes`** (the athletes the caller
  coaches, each with the coach's `icu_notes` and `icu_tags`), **training availability** (per weekday on the athlete,
  per day as calendar events: `NORMAL` / `LIMITED` / `UNAVAILABLE`, `max_training_time`, `can_train_sports`), the
  event category `PLAN`, `private_wellness_keys` on the athlete, nutrition fields on wellness, running dynamics on
  activities and intervals. Nothing relevant was removed (`/shared-event` POST and a sport-settings `apply` went).
- **Forum threads** used for meaning, not fields: the API thread (activity messages, attachments, event `newest`
  semantics), the coach's tick announcement (a five-point rating, "amazing = 5, WTF? = 1", per-athlete wording),
  and a 2026 thread confirming a *Notes* dialog on an activity that is not the Strava-synced description.
- **What our loader already calls** (`containers/executor/code_executor_api.py`): `GET /athlete/0/activities`,
  `GET /activity/{id}/fit-file`, `GET /activity/{id}/intervals`, `GET /athlete/0/wellness`. The activity summary maps
  `name`, `icu_rpe → rpe`, `feel → feel_score`, `perceived_exertion`, `session_rpe` — but **not `description`**,
  `tags`, `coach_tick`, `compliance`, `paired_event_id` or `icu_chat_id`. The wellness frame arrives whole (every
  non-empty column, `comments` included). Per-interval custom fields (`TVLRPEfield`, `TVLlabelfield`, `Lactate`)
  are read by name, which proves custom fields ride on the records as extra keys.

## 1. The surfaces, one by one

### A. The activity's own text and flags — `GET /api/v1/athlete/{id}/activities?oldest=&newest=`

One call per window (we make it already). On each `Activity` (172 fields), the ones that are words or context:

| field | type | what it is | notes |
|---|---|---|---|
| `description` | string | the athlete's note on the activity (the field Strava also syncs) | no "edited" timestamp of its own; dated by the activity |
| `name` | string | the title; athletes often write the mood into it ("Easy spin, legs dead") | |
| `tags` | string[] | labels applied to the activity; the vocabulary: `GET /athlete/{id}/activity-tags` | already codes, user-defined — the probes' vocabularies: `SFT`, `active_recovery`, `primary`, `secondary`, `tempo_training`, `time_trial`, `carb_loading`, `heavy_race`, `heavy_race_late_dinner`, `heavy_race_late_start`, `normal_race_late_dinner`, `normal_race_late_start` — a coach's session and nutrition protocol, applied by hand |
| `icu_rpe` | int | RPE 1–10 | loaded as `rpe` |
| `feel` | int | how it felt, 1–5 | loaded as `feel_score`; which end is "strong" to confirm from the UI labels |
| `perceived_exertion` | float | the exertion the athlete entered | loaded |
| `session_rpe` | int | RPE × minutes | loaded |
| `coach_tick` | int | the coach's rating of the session, 1–5 (5 = "amazing", 1 = "WTF?") | the wording per value is on the athlete: `Athlete.coach_ticks[] {id, text}`; empty means Intervals' default labels (the second probe: 14 activities ticked at 4, no custom wording) |
| `compliance` | number | how closely the activity matched its planned workout | the plan-versus-done number |
| `paired_event_id` | int | the calendar event (planned workout) this activity fulfilled | the join key to the plan's text (D) |
| `race`, `commute`, `trainer`, `sub_type` | bool / enum | flags; `sub_type` in NONE, COMMUTE, WARMUP, COOLDOWN, RACE | |
| `attachments` | Attachment[] `{id, filename, mimetype, url}` | files added to the activity | photos, PDFs — not text; noted for later |
| `icu_chat_id` | int | the activity's chat | **null exactly when nothing has been written under the activity** (the probe: 25 of 25 with an id had messages, 5 of 5 without had none) — the test before calling B |
| `source` | enum | STRAVA, UPLOAD, MANUAL, GARMIN_CONNECT, OAUTH_CLIENT, DROPBOX, POLAR, SUUNTO, COROS, WAHOO, ZWIFT, ZEPP | **an activity that came from Strava is returned as an empty stub** (the spec says so twice) — no description, nothing. An athlete who syncs only through Strava has no activity text through the API |
| `created`, `icu_sync_date`, `analyzed` | date-time | when it arrived, synced, analysed | |

Not on an activity: a separate "notes" field. The 2026 forum thread's *Notes* dialog is, as far as the schema
shows, the activity chat (B) — a message of type `NOTE`. To confirm live.

### B. Comments and notes under an activity — `GET /api/v1/activity/{id}/messages?sinceId=&limit=100`

One call **per activity** (there is no bulk endpoint in the copy; David said he might add one — check the live
spec). Returns `Message[]`, newest first:

| field | type | what it is |
|---|---|---|
| `id` | int64 | message id; `sinceId` makes a later fetch incremental |
| `athlete_id` | string | **the author** — compare with the athlete's own id to tell the athlete from everyone else; the others are not one coach: the second probe had two staff writing (a coach and a team member), so a row keeps the author's id and `name`, and `Chat.members[].role` (MEMBER, FOLLOWER, COACH, ADMIN) says which is a coach |
| `name` | string | the author's display name |
| `created` | date-time | when written — its own date, which may differ from the activity's |
| `type` | enum | `TEXT` (a chat message; all 53 the probe saw), `NOTE` (unseen so far — presumably the activity's private *Notes*), and system kinds: `FOLLOW_REQ`, `COACH_REQ`, `COACH_ME_REQ`, `ACTIVITY`, `JOIN_REQ`, `ACCEPT_COACHING_GROUP` — only `TEXT` and `NOTE` carry words we want |
| `content` | string | the text |
| `activity_id` | string | the activity |
| `start_index`, `end_index` | int | **a comment anchored to a stretch of the activity** (stream indices) — a coach's remark on a specific interval |
| `attachment_url`, `attachment_mime_type` | string | an attached file |
| `deleted`, `deleted_by_id`, `seen` | | housekeeping; skip deleted ones |

### C. The day's wellness entry — `GET /api/v1/athlete/{id}/wellness{ext}?oldest=&newest=`

One call per window (we make it). On each `Wellness` (41 fields; `id` is the day):

- **Words:** `comments` (string) — the one free-text field per day.
- **Ordinal, athlete-entered, 1–4 scales:** `sleepQuality`, `soreness`, `fatigue`, `stress`, `mood`, `motivation`,
  `injury` (ints). **1 is the good end** on every scale (the probe's distributions: stress 113 of 116 days at 1,
  injury 101 at 1, motivation all 1, fatigue mostly 1–2 for a racing athlete); confirm the labels on the form once.
- **Measured or derived:** `sleepSecs`, `sleepScore`, `avgSleepingHR`, `restingHR`, `hrv`, `hrvSDNN`, `readiness`,
  `baevskySI`, `spO2`, `systolic`/`diastolic`, `respiration`, `weight`, `bodyFat`, `abdomen`, `hydration`,
  `hydrationVolume`, `bloodGlucose`, `lactate`, `vo2max`, `kcalConsumed`, `steps`; `ctl`, `atl`, `rampRate`,
  `ctlLoad`, `atlLoad`, `sportInfo[] {type, eftp}`.
- **Categorical:** `menstrualPhase`, `menstrualPhasePredicted` (PERIOD, FOLLICULAR, OVULATING, LUTEAL, NONE).
- `updated` (date-time), `locked` (bool).
- **Custom wellness fields** (E) should appear as extra keys named after the field — to confirm live.

### D. The calendar — `GET /api/v1/athlete/{id}/events{format}?oldest=&newest=&category=`

One call per window (new for us). `oldest` defaults to today and `newest` to six days on, so both are always sent;
`category` takes a comma-separated list; the enum's spellings (`NOTE`, not the doc example's `NOTES`): a wrong one is a
422 that lists the accepted values. On each `Event` (55 fields):

| field | type | what it is |
|---|---|---|
| `category` | enum | `WORKOUT`, `RACE_A`, `RACE_B`, `RACE_C`, `NOTE`, `PLAN`, `HOLIDAY`, `SICK`, `INJURED`, `SET_EFTP`, `FITNESS_DAYS`, `SEASON_START`, `TARGET`, `SET_FITNESS` |
| `name`, `description` | string | the title and the text. For `NOTE` the note itself; for `WORKOUT` the coach's prose **and** the structured steps (the structure is also in `workout_doc`, so the steps can be set aside); for races, the race — **and sometimes HTML**: imported race events carry `<p><strong>Distance: </strong>19.5km</p>…`, so descriptions are stripped of markup before they are text |
| `start_date_local`, `end_date_local` | string | a day, or a span (`SICK`, `INJURED`, `HOLIDAY` can run over days). **`end_date_local` is exclusive**: a one-day event ends at 00:00 of the next day (the probe: every event looked "multi-day" by a naive test) |
| `created_by_id` | string | **the author** — the coach or the athlete |
| `hide_from_athlete` | bool | **a coach-private entry** |
| `athlete_cannot_edit`, `structure_read_only` | bool | the coach's entries |
| `show_as_note`, `for_week` | bool | shown as a note; a note for the whole week |
| `tags` | string[] | labels; the vocabulary: `GET /athlete/{id}/event-tags` |
| `attachments` | Attachment[] | files on the event |
| `type` | string | the sport |
| `training_availability`, `max_training_time`, `can_train_sports` | enum, int, string[] | the athlete's stated capacity for the day (NORMAL / LIMITED / UNAVAILABLE). Present on every event (the probe: 136 of 136), so only a value other than NORMAL is a signal |
| `icu_training_load`, `load_target`, `time_target`, `distance_target`, `moving_time`, `distance`, `joules` | numbers | the plan's numbers |
| `plan_athlete_id`, `plan_folder_id`, `plan_workout_id`, `plan_applied` | | from an applied training plan |
| `shared_event_id` | int | a shared event (a race others also entered) |
| `updated`, `uid`, `external_id`, `calendar_id`, `oauth_client_id` | | housekeeping |

An activity's `paired_event_id` points at its `WORKOUT` event, and `compliance` on the activity says how well it
was done — the plan's words and the day's numbers meet there.

### E. Custom fields — `GET /api/v1/athlete/{id}/custom-item`

One call per athlete. `CustomItem`: `type` in `FITNESS_CHART`, `TRACE_CHART`, **`INPUT_FIELD`** (a field on the
wellness form), **`ACTIVITY_FIELD`**, **`INTERVAL_FIELD`**, `ACTIVITY_STREAM`, `ACTIVITY_CHART`, …; `name`,
`description`, `content` (the field's definition: `type` numeric / select / text, `options` for a select, `min`,
`max`, `units`, and **`code`**, the key the values ride under), `visibility`. Values ride on the wellness, activity
and interval records **under `content.code`**, not the display name (the probe: the field "Sickness" appears in the
wellness records as `Sickness`, "Post IHHT comments" would appear as `PostIHHTcomments`; our loader reads
`TVLRPEfield` and `Lactate` off intervals the same way). The athlete record's `icu_wellness_keys` lists the codes the
athlete's form shows. A coach who defines a text field — "session notes", "how I slept" — creates a qualitative surface we
can only find by reading this list first.

### F. The athlete — `GET /api/v1/athlete/{id}` / `/profile`

For the context work: the athlete's own `id` (authorship in B and D), `coach_ticks[] {id, text}` (the wording of
the five tick values), `icu_wellness_keys[]` (which wellness fields the athlete tracks), `timezone`, `bio`.

### G. Intervals — `GET /api/v1/activity/{id}/intervals`

Already loaded. Per-interval `label` (string) and any custom `INTERVAL_FIELD` values (an RPE or lactate per
interval). Words at the interval grain — rare, but there.

### H. Chats — `GET /api/v1/athlete/{id}/chats`, `GET /api/v1/chats/{id}/messages?beforeId=&limit=`

New since 2025. The chat list gives every `PRIVATE` and `GROUP` chat and the activity chats with recent traffic
(`Chat`: `type` PRIVATE / GROUP / ACTIVITY, `activity_id`, `other_athlete_id`, `members[] {athlete_id, name, role}`,
`updated`, `new_message_count`; the probes' lists held 31 chats each: `PRIVATE` ones, one per person the athlete has
written with, the coach among them, plus "System Notifications"; for the second athlete also two `ACTIVITY` chats —
the two most recent sessions, since the list carries activity chats only while they have unread or recent traffic
— and two `GROUP` chats, one the team's with eight members). `GET /chats/{id}/messages` pages backwards (`limit` default 30, max 100;
`beforeId`), returning the same `Message` shape as B. **The private coach–athlete chat** — the conversation that is
not about any one session — is reachable this way; the activity chats are the same messages B returns.

### H2. The coach's notes on an athlete — `GET /api/v1/athletes`

New since 2025; API key only (not a bearer token). Lists the athletes the caller follows or coaches, including the
caller, as `AthleteWithTags`: `id`, `name`, `status` (ACTIVE / DORMANT / ARCHIVED), **`icu_notes`** (string — the
coach's own notes about the athlete), **`icu_tags[]`** (the coach's tags on athletes), `coach_ticks[]`,
`private_wellness_keys[]`, `training_availability[]`, `timezone`. For a coach's key this is also the list of
athlete ids to run anything over.

### H3. Training availability

On the athlete (`training_availability[] {day_of_week, training_availability, max_training_time, can_train_sports}`)
and on calendar events (`Event.training_availability` NORMAL / LIMITED / UNAVAILABLE with `max_training_time`,
`can_train_sports`): the athlete's stated capacity, a context flag beside `SICK` and `HOLIDAY`.

### I. Not in the API

No journal or diary entity beyond `NOTE` events; no "coach notes" entity beyond `icu_notes` on the athlete,
messages (type `NOTE`), hidden events and ticks; no edit timestamp on an activity's description; no bulk messages
endpoint (one call per activity, or the chat list for the active ones); no text for Strava-sourced activities. No
rate limit is documented.

## 2. The kinds, settled against the API

| kind | from | author | dated by | private? |
|---|---|---|---|---|
| `activity_note` | A: `Activity.description` (title in `name`) | the athlete (no author field; a coach may edit) | the activity | no |
| `activity_message` | B: `Message` type `TEXT` | `athlete_id` → athlete / coach / other | `created` | no |
| `activity_private_note` | B: `Message` type `NOTE` (to confirm) | `athlete_id` | `created` | likely |
| `wellness_note` | C: `Wellness.comments` | the athlete | the day | no |
| `day_note` | D: `Event` category `NOTE` (`for_week` → the week) | `created_by_id` | `start_date_local`…`end_date_local` | `hide_from_athlete` |
| `plan_note` | D: `Event` category `WORKOUT`, the prose of `description` | `created_by_id` | the planned day; joins the activity by `paired_event_id` | `hide_from_athlete` |
| `status` | D: `SICK`, `INJURED`, `HOLIDAY` (spans), `RACE_A/B/C` (+ name), `SEASON_START`, `TARGET`; A: `race`, `commute` | `created_by_id` | the span | — |
| `tag` | A: `Activity.tags`, D: `Event.tags` | whoever applied it | the activity or event | no |
| `coach_tick` | A: `coach_tick` (1–5) with the wording from F | the coach | the activity | no |
| `custom_field` | E: text-typed `INPUT_FIELD` / `ACTIVITY_FIELD` values on C and A | the athlete | the day or activity | no |
| `chat_message` | H: `Message` type `TEXT` in a `PRIVATE` (or `GROUP`) chat | `athlete_id` → athlete / coach | `created` | no |
| `athlete_note` | H2: `AthleteWithTags.icu_notes` | the coach | undated (the record's state) | coach-side |
| `availability` | H3: `Event.training_availability` (+ the athlete's weekly pattern) | `created_by_id` | the day | no |

The numbers that sit beside the words — `feel`, `icu_rpe`, `session_rpe`, the seven 1–4 wellness scales,
`compliance`, the tick's value — stay in the activity and wellness frames as numbers; the context table holds text
only, and joins to them by `date` and `activity_id`.

## 3. What a window's load would cost

For a 90-day window of one athlete: activities (1 call, have), wellness (1, have), events (1, new), custom items
(1 per athlete, new), the athlete record (1, new or have), and messages — one call per activity whose `icu_chat_id`
is set, typically a handful to a few dozen; `sinceId` makes the next load of the same activity incremental. The
corpus is small: an athlete writing twenty words a day is about ten thousand tokens a year.

## 4. To confirm against the live API — `intervals_probe.py` does these (one run, read-only)

1. `icu_chat_id` is null on an activity with no messages (so B is skipped for most activities).
2. A message of type `NOTE` is the activity's *Notes* dialog; who writes them.
3. The events `category` filter accepts `NOTE` (the enum) or `NOTES` (the doc's example).
4. A custom `INPUT_FIELD`'s value appears in the wellness JSON under the field's name (and an `ACTIVITY_FIELD`'s on
   the activity) — the script lists every key the spec does not name.
5. The values the 1–4 wellness scales and `feel` 1–5 actually take; which end is the good end is read off the UI
   once.
6. `coach_ticks` on the athlete record, and `coach_tick` values on activities.
7. The chat list and the private coach–athlete chat's messages.
8. What a Strava-sourced activity returns (the stub).
9. Any rate limiting on a burst of per-activity message calls (headers, statuses, timing).
10. `icu_notes` and `icu_tags` on `GET /athletes`.

## 5. What two athletes' accounts showed (the probes of 2026-10-13)

Two athletes' own keys, 120 days each (2026-06-15 to 2026-10-13): a Danish U23 road cyclist coached by a Norwegian
coach, and a Belgian WorldTour professional with the same coach and a second staff member writing. 41 GET calls in
16–17 s each, no rate-limit headers, no 429.

**The professional (336 activities: 110 yoga, 97 rides, 65 pilates, 46 virtual rides, 18 weights).** No descriptions
at all; 104 activity chats — the 25 sampled held 63 messages (athlete 38, coach 21, a second staff member 4), short
short English (a line about an easy indoor hour; a one-word answer); 47 activities tagged from a vocabulary of eleven
(race-day nutrition and timing among them: `carb_loading`, `heavy_race_late_dinner`…); 14 coach ticks at 4; a custom
`ACTIVITY_FIELD` (`QPxDuration`) riding on the activities, as expected. Wellness scales on only 46 of 121 days;
comments on two (a bad night; feeling better but not fully well); custom selects
`Sickness` and `Coldsore`. Calendar: 153 events — 85 workouts with the coach's prose and steps (a sentence of instruction, then the steps), 36 notes (team logistics), 32 races whose
imported descriptions are HTML. Chats: 27 private, 2 activity, 2 group (the team's, eight members).

**The U23 rider.**

- **The words are in the activity chats.** 97 of 133 activities carry a chat; the 25 sampled held 53 messages — 31
  from the athlete, 22 from the coach, about two per session, all `TEXT`, none anchored to a stretch. The athlete
  writes Danish, the coach Norwegian. One activity in 133 has a description, and it is a workout structure, not prose. Zero wellness
  comments in 121 days. The private chat with the coach exists but was last used a year ago. For this athlete the
  qualitative stream is `activity_message`, and nothing else is close — and the professional's account says the same.
- **The scales are filled every day:** 116 of 121 days have all seven 1–4 wellness scales; `icu_rpe` and `feel` on
  116 of 133 activities; `session_rpe` on 116. The ordinal stream is complete.
- **Plan versus done is fully instrumented:** 119 of 133 activities are paired with a planned workout
  (`paired_event_id`) and every one of the 133 has `compliance`; the calendar's 112 workouts (106 of 136 events
  created by the coach) carry the structured steps in `description`. Races: 9 A, 2 B. Notes: 13, short reminders
  (a test appointment). No `SICK`, `INJURED` or `HOLIDAY` events — this athlete reports illness through a custom
  wellness select, `Sickness`, instead.
- **Custom fields are real and in use:** nine wellness `INPUT_FIELD`s (`Sickness` select, heat-session temperature
  and weight before and after, a Bolt score, an IHHT scale and an IHHT *comments* text field), ten `INTERVAL_FIELD`s
  (Borg scale, lactate, RPE, label, category and training-intensity selects, breathing frequency, tidal volume, lap
  number). Only `Sickness` carried values in the window; the heat and IHHT fields belong to other blocks of the year.
- **Tags:** `SFT`, `active_recovery`, `primary`, `tempo_training` on 9 activities; 8 events tagged.
- **No coach ticks** in use (`coach_ticks` wording empty, no activity ticked); `icu_notes` present and empty on the
  two records `GET /athletes` returned (the athlete and the coach he follows) — a coach's key would show the notes.
- **Cost:** about 0.35 s per message call; a 120-day window is ~100 calls, ~35 s, per load. Nothing persists
  between sessions today — the executor's cache holds a load's files until it is wiped, and the app keeps records
  (favourites, routines, documents), not data — so every load re-downloads; `sinceId` would only matter if the
  design chose to keep messages or their labels in the user's storage. The text itself: ~200–250 messages a season,
  a few thousand words, in Danish, Norwegian or English.

**Across both:** the words are under the activities; the scales and plan-versus-done are the numbers beside them;
custom fields and tags are a coach's own structured vocabulary already in use; the coach's view (`icu_notes`, hidden
entries, private wellness keys) remains unverified without a coach's key.

## 6. The settings and the custom items (the probes of 2026-10-16, for the rider profile)

Two runs of a stdlib probe (`intervals_fields_probe.py`, in the outputs folder; Cloudflare refuses urllib's default
User-Agent with error 1010, so it sends one) on the U23 rider's key, 60 days, 40 activities' intervals.

- **The athlete record** (`GET /athlete/0`) carries the measurements — `height` with `height_units`, `weight` and
  `icu_weight`, `icu_resting_hr`, `icu_date_of_birth`, `sex`, `timezone` — beside the e-mail, the names, the Strava
  id and **the API key itself** (`icu_api_key`): a profile built from it is a whitelist, never the record minus a
  few fields. `sportSettings[]` is one group per set of sport `types` with `ftp`, `indoor_ftp`, `lthr`, `max_hr`,
  `threshold_pace` (m/s), the zones as upper bounds — `hr_zones` in bpm, `power_zones` as % of FTP with 999 the open
  top, `pace_zones` as % of the threshold pace — with their `*_zone_names`, the fitted `mmp_model` (`criticalPower`,
  `wPrime`, `pMax`, `ftp`), and `custom_zones_ids` / `custom_field_ids` / `activity_field_ids` naming the custom items
  that apply to the group. Four groups on this account (cycling, running, swimming, other).
- **`custom_items[]`** on the record is the account's whole vocabulary, each with `id`, `type`, `name`, `description`
  and a `content` object: `FITNESS_CHART` (not data), `INPUT_FIELD` (the wellness form), `ACTIVITY_FIELD`,
  `INTERVAL_FIELD` — with `content.code` (the key the values ride under), `content.type` (`numeric`, `select`,
  `text`), `content.units`, and for a select `content.options` as `[{value, text, color, icon}]` (an older or a
  hand-made definition may hold bare texts) — and **`ZONES`**: `content.stream_type` (`watts`, `tidal_volume_min`,
  `respiration`, `cadence`, `altitude`, `temp` here), `content.zones[{id, name, start, end, color}]`, `anchor`. Seven
  zone sets on this account: two power sets, the ventilatory zones over the ventilation stream, the breathing-rate
  zones, cadence bins, altitude bands, temperature bins.
- **Time in every custom zone is on the activity record** of the list route: `custom_zones[{code, zones[{id, start,
  end, start_value, end_value, secs}]}]`, the bounds as they stood that day. The record also carries the settings
  in force — `icu_ftp`, `icu_pm_ftp`, `lthr`, `athlete_max_hr`, `icu_resting_hr`, `icu_weight`, `icu_power_zones`,
  `icu_hr_zones` — so a threshold or zone change between loads is in the summary file itself.
- **The interval records** (`GET /activity/{id}/intervals` → `{analyzed, icu_groups, icu_intervals, id}`) carry a
  custom `INTERVAL_FIELD`'s value under its code only when a value was entered; **a select's value comes back as the
  option's text** (the loader's `label` column read `Endurance`, not `2`). On this account the label select rode on
  every interval of the window, the two ventilation numbers on most, the RPE select on a few, six more fields defined
  and empty. The standard keys beyond the loader's map: `average_respiration`, `average_tidal_volume`, `average_epoc`,
  `average_smo2`, `average_thb`, `ss_cp` / `ss_p_max` / `ss_w_prime`, `strain_score`, running dynamics.
- **The wellness records** carry an `INPUT_FIELD`'s value under its code the same way (none in this window).
- The loader reads four interval codes by name (label, RPE, lactate, lap number) - one coach's vocabulary. The rider
  profile (docs/RIDER_PROFILE_DESIGN.md, patch 0182) carries every definition the account has; the intervals and
  wellness files carrying every field's values under its code is the step after it.
