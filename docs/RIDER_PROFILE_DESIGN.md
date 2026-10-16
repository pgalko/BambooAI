# The rider profile — the settings the data is read against (2026-10-16, patch 0182)

The sixth kind an Intervals.icu load can be asked for, with a seventh riding beside it. Palo's decisions (2026-10-16):
two files under one card; a select's text in the code's column with the number beside it; on by default. The rule
that shaped every line: *this is one coach's naming convention; other coaches name their fields differently or
have none* — so everything is driven by the account's own record and `custom_items`, nothing is named in code, and
an account without custom items gets the standard rows alone.

## 1. What the live account settled (docs/INTERVALS_CONTEXT_INVENTORY.md §6)

The athlete record carries the measurements, the sport groups with their thresholds, zones (as upper bounds) and
power-duration model, and the whole custom vocabulary (`custom_items`: input, activity and interval fields with
their codes, types, units and options; `ZONES` sets with their stream and bounds). It also carries the e-mail, the
names, the Strava id and the API key itself — so the profile is a whitelist. Time in every custom zone is on the
activity record of the list route (`custom_zones`), with the bounds in force that day; a custom select's value
comes back on the interval records as the option's text.

## 2. The files

**`rider_profile_<start>_to_<end>.csv`** (kind `rider`, prefix `rider_profile_`) — long form, one row per
setting: `section, sport_types, key, value, unit, low, high, note`. The sections in order:

| section | rows | key / value / unit | low, high | note |
|---|---|---|---|---|
| `subject` | weight (`icu_weight`, else `weight`, kg), height (the record's `height_units`), resting_hr (bpm), age (years, from the date of birth, which stays out), sex, timezone | | | where the daily value lives |
| `sport` | per group (`sport_types` = the group's types pipe-joined): ftp, indoor_ftp (W), lthr, max_hr (bpm), threshold_pace (m/s), w_prime (J), p_max (W), sweet_spot_min/max (%FTP) when set; `model_cp`, `model_w_prime`, `model_p_max`, `model_ftp` from `mmp_model` | | | the model rows say they are the fitted model's |
| `zone` | `hr_zone_n` (bpm), `power_zone_n` (%FTP), `pace_zone_n` (% of the threshold pace) — the upper bound as the value | the bound before (0 first), the bound; 999 → high blank | the zone's name; the first row of each kind states the convention; a power row adds the watts at the group's FTP |
| `custom_zone` | one per zone of every `ZONES` item: key `set:zone`, value the zone's name, unit the stream | the zone's start, end | the set, its description, where the times are |
| `custom_field` | one per `INPUT_FIELD`, `ACTIVITY_FIELD`, `INTERVAL_FIELD` with a code: key the code, value the item kind, unit the item's units | | type · name · the options as `1 Recovery \| 2 Endurance` (or bare texts) · which file carries it |

Every column is filled before the frame is built, so a column of numbers and blanks stays as written. Charts and
items without a code make no row. Nothing identifying is in the file; the test writes a record with an e-mail, a
key, names and a birth date and checks none of it reaches the text.

**`custom_zone_times_<start>_to_<end>.csv`** (kind `zones`, prefix `custom_zone_times_`) — one row per activity ×
custom zone: `activity_id, start_date_local, type, set_code, set_name, stream, zone_id, zone_name, low, high,
secs`, from the list records' `custom_zones` with the names from the definitions (a set the account no longer
defines keeps its code with no name). Written only when the account defines `ZONES` items — header-only when it
does but no activity of the window carries times; **not written at all** for an account without custom zone sets,
so the pill never appears for a coach who has none.

**The summary file** gains the settings in force that day: `max_hr_setting` (`athlete_max_hr`), `pm_ftp_watts`
(`icu_pm_ftp`) beside `ftp_watts`, and `power_zones` / `hr_zones` / `pace_zones` pipe-joined — a threshold or zone
change between loads is in the file itself.

**Every custom field under its code (patch 0183).** The account's definitions (`field_definitions`, one kind at a
time) decode the files' columns: the intervals file carries every `INTERVAL_FIELD` under its code, the wellness
file every `INPUT_FIELD`, the summary file every `ACTIVITY_FIELD`. A select is its option's text in the code's
column with the number in `<code>_value` beside it (`decode_select`: the API returns the text; a number entered by
hand is decoded the other way; a value outside the options is kept as text with no number; options that are bare
texts carry no number). A numeric or text field is the value as it is. A key the account does not define is left
out; a field with no value in the window makes no column (a routine's conform adds it empty). The four columns the
loader has always read by name — `label`, `RPE`, `lactate`, `lap_number`, one coach's codes — stay for the routines
that read them. The record is fetched once per load, before the files, whatever is asked; without it the files
carry the records' keys as they come.

## 3. The load

The fifth card of the Intervals dialog, **Rider profile**, between Wellness and Context (which now spans the row
beneath the 2 × 2), **on by default**: no extra call when the context is on — the record is fetched once for both
(it tells the context's authors apart and reads its custom fields; the profile is built from it) — and one small
call when it is off. The loader writes the profile after the planned workouts, the zone times after the profile;
without the record there is no profile, and the result carries `profile_note` saying so. Never fatal to the load.
The pills: *Rider profile* (no window: the settings as they stand) and *Custom zones (N days)*; the primary pill's
letters gain `R`. Executor image v58.

## 4. What the analyst sees

The profile's DATA entry is not a head of five rows of a settings file: the path, the columns, the row count with
what a row is, and a **Settings** line assembled from the file's own rows by `analyst/profile.py` — the subject's
measurements and each sport group's thresholds as `key value unit` (the model's estimates stay in the file), then
what else the file holds, counted: *also in the file: 22 zone rows with their bounds, 3 custom zone rows in 2 sets,
2 custom field definitions - the codes other files' columns carry, with their options*. When the file has
`custom_zone` rows the line ends with the rule about them (patch 0184, Palo: a coach's own zones come from testing
and are the ones meant): *the custom zone sets are the account's own, set by hand rather than the platform's
defaults, and take precedence over the standard zones when reading intensity - time in them is in the custom zone
times file, the standard zones' times in the summary file*; an account without custom sets reads nothing of it.
No word of the rest is a prompt constant (DESIGN_CHECKLIST C5; `analyst/profile.py` is in the scanner's list). The entry is exempt from the heads'
budget like the context's. The zone times file is described like any other (its head). The file is read once per
load (`_profile_frame`, by path), from the executor in api mode.

## 5. Routines and the cache

`LOAD_KINDS["intervals"]` gains `rider`; `LOAD_BRINGS["intervals"]["rider"] = ("zones",)`; `zones` is in
`BRINGS_IF_DEFINED` — a brought kind whose file the loader writes only when the account defines what it holds: its
absence beside a cached load is not a miss (`cache_match` takes it when there, wants nothing when not), and a run
binds an empty table for it when this load lacks it. `CUT_RULES["rider"] = ("whole", "")` — a cut run takes the
profile as it is and the prelude's line says *a settings file, not rows of the window*; `CUT_RULES["zones"] =
("date", "start_date_local")` like the summary. `LOADER_FILES_MAX` is eight now (six kinds, the codes beside the
context, the zone times beside the profile), so the app's limit is twelve (0181). A run's CHECK row has a sentence
per file; the text reaches the page whole up to `LOOKUP_PEEK_CHARS` (3,000; the 600 of before cut a seven-file
line short of its closing sentence).

## 6. Not in this step

Writing to the profile; the profile's history as a file (the summary's per-activity columns carry it); the store
(the record is fetched each load — the current state, cheap, and stale is wrong).

## 7. Tests

`test_context.py` (profile_frame against a record shaped like the live one: the whitelist, the sport and model
rows, the zone bounds and the open top, the custom sets, the custom fields' options in both shapes; the zone times
frame; None without sets; the summary's settings columns; the file names; the stamp; `field_definitions`,
`decode_select`, the interval records, the summary and the wellness frame with their custom fields decoded),
`test_store.py` (the real loader over the fake stack: the record fetched once, the two files after the plan,
nothing identifying, one zone-time row per ride and custom zone; an account without sets writes no zone times
file; the intervals file's select as text with its number beside it), `test_routines.py` (the kinds, prefixes and cut rules; `cache_match` without and with the profile and the
zone times; `load_plan`; the registry's count), `test_app_path.py` (the DATA entry and the Settings line from the
rows), `test_dialogs.js` (five cards, the profile on, Context spanning), `test_shell.js` (the page's reading of
the card), the integrations walk (the default load brings the two files with their pills, the profile's sections
and nothing identifying, the zone times per ride; the Settings line in the chain's DATA; a routine's run from the
cache binding all seven files).
