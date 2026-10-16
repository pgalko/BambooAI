"""The context (docs/CONTEXT_DESIGN.md): the words written beside the data as a file of the Intervals.icu load.
The executor's builder over canned API shapes - the kinds, the authors, the dates, the failures - and the pure
pieces it rests on (plain text, a plan's prose, the inclusive end of a span, local times).

    python3 tests/analyst/test_context.py
"""
import json
import os
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.normpath(os.path.join(HERE, "..", ".."))
sys.path[:0] = [HERE, ROOT, os.path.join(ROOT, "delve"), os.path.join(ROOT, "containers", "executor"), os.path.join(ROOT, "tools", "stack", "fakepkgs")]
import _stubs  # noqa: E402,F401
import pandas as pd  # noqa: E402

results = []


def check(name, cond, detail=""):
    results.append((name, bool(cond)))
    print(("  ok   " if cond else "  FAIL ") + name + ("" if cond else f"  <- {str(detail)[:500]}"))


os.chdir(tempfile.mkdtemp(prefix="bamboo_context_"))
import code_executor_api as E  # noqa: E402

# ---- the pure pieces ---------------------------------------------------------------------------------------------
check("plain_text: HTML stripped, entities unescaped, lines kept (an imported race description)",
      E.plain_text("<p><strong>Distance: </strong>19.5km</p><p>Elevation &amp; wind</p>") == "Distance: 19.5km\nElevation & wind", repr(E.plain_text("<p><strong>Distance: </strong>19.5km</p><p>Elevation &amp; wind</p>")))
check("plain_text: whitespace normalised, None is ''", E.plain_text("  legs   heavy \n\n cut it  short ") == "legs heavy\ncut it short" and E.plain_text(None) == "")
check("plan_prose: a planned workout's step lines go, the prose stays (durations, repeats, compound durations, percentages)",
      E.plan_prose("Adjust power to altitude.\n-20m coasting for FC\n-3h40m CZEE\n2x -10s CZSS sprint\n10m 60%\n5 x 3m at 300w") == "Adjust power to altitude.",
      repr(E.plan_prose("Adjust power to altitude.\n-20m coasting for FC\n-3h40m CZEE\n2x -10s CZSS sprint\n10m 60%\n5 x 3m at 300w")))
check("plan_prose: steps alone are no prose; a sentence with a number in it is prose; a bare repeat count on its own line is structure (2026-10-15)", E.plan_prose("-5m CZEE -5m CZVT1\n-10m 220w") == "" and E.plan_prose("3 minutes easy then go") == "3 minutes easy then go" and E.plan_prose("Endurance w/VT1 efforts 5x20':\n3x\n2x") == "Endurance w/VT1 efforts 5x20':" and E.plan_prose("4x") == "")
check("plan_prose: minute and second marks are step lines too (5x20' @ 300w, 30\" all out); a title with a mark after letters is prose",
      E.plan_prose("Very important session, you will feel fatigued.\n5x20' @ 300w\n- 30\" all out\n3 x 8' @ 95% of FTP") == "Very important session, you will feel fatigued." and E.plan_prose("VT1 5x20': just get through it") == "VT1 5x20': just get through it",
      repr(E.plan_prose("Very important session, you will feel fatigued.\n5x20' @ 300w\n- 30\" all out\n3 x 8' @ 95% of FTP")))
check("inclusive end: the API's exclusive end_date_local becomes the last day of a span; a one-day entry has none",
      E._inclusive_end("2026-09-05T00:00:00", "2026-09-08T00:00:00") == "2026-09-07" and E._inclusive_end("2026-06-15T00:00:00", "2026-06-16T00:00:00") == "" and E._inclusive_end("2026-07-04T00:00:00", "2026-07-04T00:00:00") == "")
check("local day and time: a UTC stamp moves into the subject's time zone (and may change day); a naive stamp is local",
      E._local_day_time("2026-10-08T23:30:00Z", "Europe/Copenhagen") == ("2026-10-09", "01:30") and E._local_day_time("2026-09-01T07:00:00") == ("2026-09-01", "07:00") and E._local_day_time("") == ("", ""))
check("custom text fields: text and select items of the wellness form and of activities by their content.code; numeric ones are not words",
      E._custom_text_fields([{"type": "INPUT_FIELD", "name": "Sickness", "content": {"code": "Sickness", "type": "select"}},
                             {"type": "ACTIVITY_FIELD", "name": "How I slept", "content": {"code": "HowISlept", "type": "text"}},
                             {"type": "INPUT_FIELD", "name": "Bolt", "content": {"code": "Bolt", "type": "numeric"}},
                             {"type": "INTERVAL_FIELD", "name": "Label", "content": {"code": "Lbl", "type": "select"}}]) == {"wellness": {"Sickness": ("Sickness", "select")}, "activity": {"HowISlept": ("How I slept", "text")}})

# ---- the builder over canned API shapes --------------------------------------------------------------------------
class _R:
    def __init__(self, body, status=200):
        self._b, self.status_code = body, status

    def raise_for_status(self):
        if self.status_code != 200:
            raise RuntimeError(f"HTTP {self.status_code}")

    def json(self):
        return self._b


class FakeSession:
    """The calls the builder makes, answered from canned shapes (the live API's, per docs/INTERVALS_CONTEXT_INVENTORY.md)."""
    def __init__(self, fail=()):
        self.calls, self.fail = [], set(fail)

    def get(self, url, params=None, timeout=None):
        self.calls.append(url.split("/api/v1")[-1])
        key = self.calls[-1]
        if key in self.fail:
            return _R({"error": "nope"}, 500)
        if key == "/athlete/0/events":
            return _R([
                {"id": 11, "category": "WORKOUT", "start_date_local": "2026-09-01T00:00:00", "end_date_local": "2026-09-02T00:00:00", "name": "Endurance", "description": "Steady, keep it conversational\n- 2h 60%", "created_by_id": "c9", "tags": ["primary"]},
                {"id": 12, "category": "NOTE", "start_date_local": "2026-09-02T00:00:00", "name": "exam week", "description": "exams all week", "created_by_id": "i1", "for_week": True},
                {"id": 13, "category": "SICK", "start_date_local": "2026-09-05T00:00:00", "end_date_local": "2026-09-08T00:00:00", "name": "cold", "created_by_id": "i1"},
                {"id": 14, "category": "RACE_B", "start_date_local": "2026-07-04T00:00:00", "end_date_local": "2026-07-04T00:00:00", "name": "Stage 1", "description": "<p><strong>Distance: </strong>19.5km</p>", "created_by_id": "i1"},
                {"id": 15, "category": "NOTE", "start_date_local": "2026-09-09T00:00:00", "name": "coach only", "description": "watch motivation", "created_by_id": "c9", "hide_from_athlete": True},
                {"id": 16, "category": "WORKOUT", "start_date_local": "2026-09-10T00:00:00", "name": "Ramp", "description": "-10m 220w\n-5m 240w", "created_by_id": "c9"},
                {"id": 17, "category": "SET_EFTP", "start_date_local": "2026-09-11T00:00:00", "name": "eFTP 310", "created_by_id": "c9"},
            ])
        if key == "/chats/7":
            return _R({"id": 7, "type": "ACTIVITY", "members": [{"athlete_id": "c9", "name": "Coach", "role": "COACH"}, {"athlete_id": "i1", "role": "MEMBER"}, {"athlete_id": "s2", "role": "MEMBER"}]})
        if key == "/activity/a1/messages":
            return _R([
                {"id": 3, "athlete_id": "c9", "name": "Coach", "created": "2026-09-01T10:00:00Z", "type": "TEXT", "content": "deleted one", "deleted": "2026-09-02T00:00:00Z"},
                {"id": 2, "athlete_id": "c9", "name": "Coach", "created": "2026-09-01T10:00:00Z", "type": "NOTE", "content": "watch the drift next week"},
                {"id": 1, "athlete_id": "i1", "name": "Me", "created": "2026-09-01T23:30:00Z", "type": "TEXT", "content": "felt rough today  \n really", "start_index": 120},
                {"id": 4, "athlete_id": "s2", "name": "Staff", "created": "2026-09-02T06:00:00Z", "type": "TEXT", "content": "ok"},
                {"id": 5, "athlete_id": "x", "type": "ACTIVITY", "content": "shared"},
                {"id": 6, "athlete_id": "i1", "type": "TEXT", "content": "   "},
            ])
        if key == "/activity/a9/messages":
            return _R([], 500)
        return _R({}, 404)


ACTS = [{"id": "a1", "start_date_local": "2026-09-01T07:00:00", "description": "legs heavy, cut it short", "tags": ["easy"], "coach_tick": 5, "icu_chat_id": 7, "paired_event_id": 11, "HowISlept": "badly"},
        {"id": "a2", "start_date_local": "2026-09-02T07:00:00", "description": "-5m CZEE -5m CZVT1", "icu_chat_id": None, "coach_tick": 2},
        {"id": "a9", "start_date_local": "2026-09-03T07:00:00", "icu_chat_id": 8},
        {"id": "s0", "source": "STRAVA", "start_date_local": "2026-09-04T07:00:00"}]
WELL = [{"id": "2026-09-01", "fatigue": 3, "comments": "slept badly, stressed about work", "Sickness": "Mild"}, {"id": "2026-09-02", "fatigue": 2, "Sickness": None}]
ATH = {"id": "i1", "timezone": "Europe/Copenhagen", "coach_ticks": [{"id": 5, "text": "Amazing!"}],
       "custom_items": [{"type": "INPUT_FIELD", "name": "Sickness", "content": {"code": "Sickness", "type": "select"}},
                        {"type": "ACTIVITY_FIELD", "name": "How I slept", "content": {"code": "HowISlept", "type": "text"}},
                        {"type": "INPUT_FIELD", "name": "Bolt", "content": {"code": "Bolt", "type": "numeric"}}]}

s = FakeSession()
rows, rep = E.fetch_context_rows(s, "http://icu/api/v1", ACTS, WELL, "2026-06-15", "2026-10-13", athlete=ATH)
df = E.context_frame(rows)
by = {r["source_id"] + "/" + r["kind"]: r for r in rows}
kinds = rep["kinds"]
check("the calls: the chat's members once (first), the calendar once, the messages of each activity with a chat and no other",
      s.calls == ["/chats/7", "/athlete/0/events", "/activity/a1/messages", "/activity/a9/messages"] and rep["calls"] == 4 and rep["activities_with_chat"] == 2, s.calls)
check("the report: passages counted by kind; the one failed call named in a sentence; the subject's id; the coaches (from the chat's members here) and the roles the chat showed",
      rep["passages"] == len(rows) == 16 and rep["failed"] == ["the messages of activity a9 could not be fetched (RuntimeError)"] and rep["subject_id"] == "i1"
      and rep["coach_ids"] == ["c9"] and rep["chat_roles"] == {"c9": "COACH", "i1": "MEMBER", "s2": "MEMBER"}, rep)
check("kinds: status 2 (a race and a sick span; SET_EFTP is not a passage), day_note 2, plan_note 1 (the steps-only workout is none), activity_note 1 (the steps-only description is none), "
      "activity_message 2 (the deleted, the shared and the blank dropped), activity_private_note 1, wellness_note 1, custom_field 2, coach_tick 2, tag 2",
      kinds == {"status": 2, "day_note": 2, "plan_note": 1, "activity_note": 1, "activity_message": 2, "activity_private_note": 1, "wellness_note": 1, "custom_field": 2, "coach_tick": 2, "tag": 2}, kinds)
check("ids C.1..C.n in day order, then time, then kind; the columns of the design in order",
      [r["id"] for r in rows] == [f"C.{i}" for i in range(1, 17)] and [r["date"] for r in rows] == sorted(r["date"] for r in rows) and list(df.columns) == E.CONTEXT_COLUMNS, [r["id"] for r in rows][:5])
check("the race: a status row with the category, the name and the HTML-stripped description; a one-day entry has no end_date",
      by["14/status"]["text"] == "RACE_B: Stage 1\nDistance: 19.5km" and by["14/status"]["end_date"] == "" and by["14/status"]["event_id"] == "14", by.get("14/status"))
check("the sick span: end_date is the last day (the API's exclusive end minus one)", by["13/status"]["text"] == "SICK: cold" and by["13/status"]["end_date"] == "2026-09-07" and by["13/status"]["date"] == "2026-09-05")
check("the plan's prose: the name as a prefix, the step line gone, joined to the activity that fulfilled it through paired_event_id, the coach as its author",
      by["11/plan_note"]["text"] == "Endurance: Steady, keep it conversational" and by["11/plan_note"]["activity_id"] == "a1" and by["11/plan_note"]["author_role"] == "coach" and by["11/plan_note"]["author_id"] == "c9", by.get("11/plan_note"))
check("a calendar note: name and body; the subject as author; the coach's hidden note is private and the coach's",
      by["12/day_note"]["text"] == "exam week\nexams all week" and by["12/day_note"]["author_role"] == "subject" and by["15/day_note"]["private"] is True and by["15/day_note"]["author_role"] == "coach", (by.get("12/day_note"), by.get("15/day_note")))
check("the activity's own note is a passage; a description that is only a workout structure is not",
      by["a1/activity_note"]["text"] == "legs heavy, cut it short" and by["a1/activity_note"]["author_role"] == "subject" and "a2/activity_note" not in by)
check("tags: one row each, on the activity and on the event, text = the tag", by["a1#easy/tag"]["activity_id"] == "a1" and by["a1#easy/tag"]["text"] == "easy" and by["11#primary/tag"]["event_id"] == "11")
check("the coach's tick: the value and its wording from the subject's record, the default wording when the record has none",
      by["a1#tick/coach_tick"]["text"] == "coach tick 5 of 5: Amazing!" and by["a2#tick/coach_tick"]["text"] == "coach tick 2 of 5: Not great" and by["a1#tick/coach_tick"]["author_role"] == "coach")
check("custom fields: a wellness select under its code, an activity text field under its code, named by the item's name; a numeric one is not a passage; a null is skipped",
      by["2026-09-01#Sickness/custom_field"]["text"] == "Sickness: Mild" and by["a1#HowISlept/custom_field"]["text"] == "How I slept: badly" and "2026-09-02#Sickness/custom_field" not in by and not any("Bolt" in k for k in by))
check("the wellness comment is a passage of the day, the subject's", by["2026-09-01/wellness_note"]["text"] == "slept badly, stressed about work" and by["2026-09-01/wellness_note"]["author_role"] == "subject" and by["2026-09-01/wellness_note"]["date"] == "2026-09-01")
m1 = by["1/activity_message"]
check("a message: the subject's, dated in the subject's time zone (23:30Z is 01:30 the next day), whitespace normalised, its id as source_id, the activity on the row",
      m1["author_role"] == "subject" and m1["date"] == "2026-09-02" and m1["time"] == "01:30" and m1["text"] == "felt rough today\nreally" and m1["activity_id"] == "a1" and m1["author_name"] == "Me", m1)
check("a message by a member who is not the coach is 'other' with the name kept; a NOTE-type message is a private note by the coach",
      by["4/activity_message"]["author_role"] == "other" and by["4/activity_message"]["author_name"] == "Staff" and by["2/activity_private_note"]["private"] is True and by["2/activity_private_note"]["author_role"] == "coach", (by.get("4/activity_message"), by.get("2/activity_private_note")))
check("text_en and lang are empty before the coding pass; chars is the length of the text; private is a boolean",
      all(r["text_en"] == "" and r["lang"] == "" and r["chars"] == len(r["text"]) and isinstance(r["private"], bool) for r in rows))

# the failure states of F1
s2 = FakeSession(fail={"/athlete/0/events", "/chats/7"})
rows2, rep2 = E.fetch_context_rows(s2, "http://icu/api/v1", ACTS, WELL, "2026-06-15", "2026-10-13", athlete=ATH)
check("the calendar refused: the other passages are still built, the failure is a sentence; the chat's members refused too: nobody can be marked coach, said so",
      rep2["passages"] == len(rows2) and not any(r["kind"] in ("day_note", "plan_note", "status") for r in rows2) and len(rep2["failed"]) == 3
      and rep2["failed"][0].startswith("the chat's members could not be fetched") and rep2["failed"][1].startswith("the calendar entries could not be fetched")
      and all(r["author_role"] != "coach" for r in rows2 if r["kind"] == "activity_message") and rep2["coach_ids"] == [], rep2)
# the live load of 2026-10-14: the chat's members carried no COACH role and no coach flag, and every coach was 'other' -
# whoever writes the planned workouts is a coach
class _NoRoleSession(FakeSession):
    def get(self, url, params=None, timeout=None):
        r = super().get(url, params=params, timeout=timeout)
        if self.calls[-1] == "/chats/7":
            return _R({"id": 7, "type": "ACTIVITY", "members": [{"athlete_id": "c9", "name": "Coach", "role": "MEMBER"}, {"athlete_id": "i1", "role": "MEMBER"}, {"athlete_id": "s2", "role": "MEMBER"}]})
        return r
rows5, rep5 = E.fetch_context_rows(_NoRoleSession(), "http://icu/api/v1", ACTS, WELL, "2026-06-15", "2026-10-13", athlete=ATH)
by5 = {r["source_id"] + "/" + r["kind"]: r for r in rows5}
check("the chat's members all MEMBER: the author of the planned workouts (not the subject) is the coach - on the messages, the plan and the hidden note alike; the report says which roles the chat showed",
      rep5["coach_ids"] == ["c9"] and by5["2/activity_private_note"]["author_role"] == "coach" and by5["11/plan_note"]["author_role"] == "coach" and by5["15/day_note"]["author_role"] == "coach"
      and by5["4/activity_message"]["author_role"] == "other" and rep5["chat_roles"] == {"c9": "MEMBER", "i1": "MEMBER", "s2": "MEMBER"}, (rep5, by5.get("2/activity_private_note")))
rows3, rep3 = E.fetch_context_rows(FakeSession(), "http://icu/api/v1", [], [], "2026-06-15", "2026-10-13", athlete=None)
check("no activities, no wellness, no record: no messages asked, the calendar still read; authors not told apart (no subject id)",
      rep3["calls"] == 1 and all(r["author_role"] in ("other", "coach") for r in rows3) and rep3["subject_id"] == "", rep3)
rows4, rep4 = E.fetch_context_rows(FakeSession(fail={"/athlete/0/events"}), "http://icu/api/v1", [{"id": "z", "start_date_local": "2026-09-01T07:00:00"}], [], "2026-06-15", "2026-10-13", athlete=ATH)
check("a window with no words: a table with no rows, the frame has the columns", rep4["passages"] == 0 and E.context_frame(rows4).shape == (0, len(E.CONTEXT_COLUMNS)))

# ---- the summary's new columns and the file's name -----------------------------------------------------------------
summ = E.create_activity_summary([{"id": "a1", "start_date_local": "2026-09-01T07:00:00", "name": "Ride", "description": "<b>legs</b> heavy", "tags": ["easy", "primary"], "coach_tick": 5, "paired_event_id": 11, "icu_chat_id": 7, "compliance": 0.9, "icu_rpe": 6, "feel": 2},
                                 {"id": "a2", "start_date_local": "2026-09-02T07:00:00", "name": "Run", "tags": [], "description": ""}])
r1 = summ[summ["activity_id"] == "a1"].iloc[0]
check("the summary carries the join columns: description as plain text, tags joined by |, coach_tick, paired_event_id, chat_id, workout_compliance; empties are missing, not ''",
      r1["description"] == "legs heavy" and r1["tags"] == "easy|primary" and r1["coach_tick"] == 5 and r1["paired_event_id"] == 11 and r1["chat_id"] == 7 and r1["workout_compliance"] == 0.9
      and pd.isna(summ[summ["activity_id"] == "a2"].iloc[0]["description"]) and pd.isna(summ[summ["activity_id"] == "a2"].iloc[0]["tags"]), summ.to_dict("records"))
p = E.save_aux_dataset(E.context_frame(rows), "context", "u1", "2026-06-15", "2026-10-13", subdir="abc123")
check("the file: context_notes_<start>_to_<end>.csv in the key's folder, readable back with the columns and the rows",
      p == os.path.join("datasets", "u1", "abc123", "context_notes_20260615_to_20261013.csv") and os.path.exists(p) and list(pd.read_csv(p).columns) == E.CONTEXT_COLUMNS and len(pd.read_csv(p)) == 16, p)
p2 = E.save_aux_dataset(pd.DataFrame(columns=["id", "code"]), "codes", "u1", "2026-06-15", "2026-10-13", subdir="abc123")
check("the codes file's name beside it", p2.endswith(os.path.join("abc123", "context_codes_20260615_to_20261013.csv")), p2)
check("the executor's build stamp is v57 (a failed script returns what it printed - an image change)", "v57" in E.EXECUTOR_BUILD, E.EXECUTOR_BUILD)

# ---- the planned workouts file (2026-10-15): the prescription on the numbers side, beside the context's words ----------
sp = FakeSession()
events, failed_cal = E.fetch_calendar(sp, "http://icu/api/v1", "2026-06-15", "2026-10-13")
check("fetch_calendar: the window's events in one call, no failure sentence; a failed call is an empty list and a sentence",
      len(events) == 7 and failed_cal == "" and sp.calls == ["/athlete/0/events"] and E.fetch_calendar(FakeSession(fail={"/athlete/0/events"}), "http://icu/api/v1", "2026-06-15", "2026-10-13") == ([], "the calendar entries could not be fetched (RuntimeError: HTTP 500)"),
      (len(events), failed_cal, sp.calls))
plan = E.planned_workouts_frame(events, ACTS + [{"id": "a7", "start_date_local": "2026-09-10T07:00:00", "paired_event_id": 16, "compliance": 88.5}])
check("planned_workouts_frame: one row per WORKOUT entry, in day order, with the columns of the design",
      list(plan.columns) == E.PLAN_COLUMNS and list(plan.event_id) == ["11", "16"] and list(plan.date) == ["2026-09-01", "2026-09-10"], (list(plan.columns), plan.event_id.tolist()))
r11, r16 = plan.iloc[0], plan.iloc[1]
check("the paired entry: the activity it was done as and that activity's compliance; the prose and the step lines kept apart (the context's plan_note keeps the prose alone)",
      r11.activity_id == "a1" and r11["name"] == "Endurance" and r11.author_id == "c9" and r11.prose == "Steady, keep it conversational" and r11.steps == "- 2h 60%" and r11.tags == "primary" and r11.workout_doc == "" and r11.availability == "",
      r11.to_dict())
check("an entry that is steps alone: no prose (no passage in the context either), the steps as written, the paired activity's compliance; the structured workout as JSON when the entry carries one",
      r16.activity_id == "a7" and r16.compliance == 88.5 and r16.prose == "" and r16.steps == "-10m 220w\n-5m 240w" and r16["name"] == "Ramp", r16.to_dict())
plan2 = E.planned_workouts_frame([{"id": 21, "category": "WORKOUT", "start_date_local": "2026-09-20T00:00:00", "name": "Vo2", "description": "Hard one.\n5x\n-3m 320w\n-3m 150w", "created_by_id": "c9", "type": "Ride",
                                   "moving_time": 5400, "icu_training_load": 120, "distance": 45000, "load_target": 110, "time_target": 5400, "training_availability": "LIMITED", "workout_doc": {"steps": [{"reps": 5, "duration": 180, "power": {"units": "w", "value": 320}}]}},
                                  {"id": 22, "category": "NOTE", "start_date_local": "2026-09-21T00:00:00", "name": "note", "created_by_id": "i1"}], [])
check("the plan's numbers, the targets, an availability other than NORMAL and the workout_doc as JSON; a NOTE is not a planned workout; an entry with no paired activity is a skipped session (empty activity_id)",
      len(plan2) == 1 and plan2.iloc[0].planned_duration_sec == 5400 and plan2.iloc[0].planned_load == 120 and plan2.iloc[0].planned_distance_m == 45000 and plan2.iloc[0].load_target == 110 and plan2.iloc[0].time_target == 5400
      and plan2.iloc[0].availability == "LIMITED" and json.loads(plan2.iloc[0].workout_doc)["steps"][0]["reps"] == 5 and plan2.iloc[0].activity_id == "" and plan2.iloc[0].prose == "Hard one." and plan2.iloc[0].steps == "5x\n-3m 320w\n-3m 150w", plan2.iloc[0].to_dict())
check("an empty calendar is an empty table with the columns", list(E.planned_workouts_frame([], ACTS).columns) == E.PLAN_COLUMNS and len(E.planned_workouts_frame([], ACTS)) == 0)
s6 = FakeSession()
rows6, rep6 = E.fetch_context_rows(s6, "http://icu/api/v1", ACTS, WELL, "2026-06-15", "2026-10-13", athlete=ATH, events=events)
check("fetch_context_rows given the calendar fetches it no second time and reads the same passages", "/athlete/0/events" not in s6.calls and rep6["passages"] == rep["passages"] and rep6["calls"] == rep["calls"] - 1, (s6.calls, rep6["passages"], rep["passages"]))
rows6b, rep6b = E.fetch_context_rows(FakeSession(), "http://icu/api/v1", ACTS, WELL, "2026-06-15", "2026-10-13", athlete=ATH, events=[], events_failed="the calendar entries could not be fetched (RuntimeError: HTTP 500)")
check("...and given the calendar's failure sentence, carries it in the report", "the calendar entries could not be fetched (RuntimeError: HTTP 500)" in rep6b["failed"], rep6b["failed"])
c = E.app.test_client()
rr = c.post("/file_utils/read_aux_dataset", json={"file_path": p})
check("the executor reads an auxiliary file whole (for the map and the coding pass): the text, its name and size; a path outside datasets/ is refused",
      rr.status_code == 200 and rr.get_json()["filename"] == "context_notes_20260615_to_20261013.csv" and rr.get_json()["text"].startswith("id,kind,date") and rr.get_json()["text"].count("\n") >= 16
      and c.post("/file_utils/read_aux_dataset", json={"file_path": "../etc/passwd"}).status_code == 404 and c.post("/file_utils/read_aux_dataset", json={"file_path": "/etc/passwd"}).status_code == 404, rr.get_data(as_text=True)[:200])

passed = sum(1 for _, ok in results if ok)
failed = [n for n, ok in results if not ok]
print(f"\n{passed} passed, {len(failed)} failed")
sys.exit(1 if failed else 0)
