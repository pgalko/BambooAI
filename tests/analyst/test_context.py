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
# the activity's own day on every passage that hangs on an activity (2026-10-18: one message in seven was written a day or
# more after its activity, and "today" in it is the activity's day); none on a passage that hangs on no activity
check("activity_date: the activity's day on its messages (one written at 01:30 the next day keeps the activity's day), its note, tags, tick and custom field, and on the plan it fulfilled; "
      "empty on the calendar's own tags, the status entries, the notes and the wellness passages",
      m1["activity_date"] == "2026-09-01" and m1["date"] == "2026-09-02" and by["a1/activity_note"]["activity_date"] == "2026-09-01" and by["a1#easy/tag"]["activity_date"] == "2026-09-01"
      and by["a1#tick/coach_tick"]["activity_date"] == "2026-09-01" and by["a1#HowISlept/custom_field"]["activity_date"] == "2026-09-01" and by["11/plan_note"]["activity_date"] == "2026-09-01"
      and by["a2#tick/coach_tick"]["activity_date"] == "2026-09-02"
      and all(r["activity_date"] == "" for r in rows if not r["activity_id"]), [(r["id"], r["kind"], r["activity_id"], r["activity_date"]) for r in rows])
_cp = [{"id": f"C.{i}", "text": t} for i, t in enumerate(["Recovery protocol: breathe in for four, hold for seven, out for eight; six rounds, rest between them.",
                                                         "Top", "Top",
                                                         "Recovery protocol:  breathe in for four, hold for seven, out for eight;\nsix rounds, rest between them.",
                                                         "Recovery protocol: breathe in for four, hold for seven, out for eight; six rounds, rest between them.",
                                                         "A different long passage that happens to be written only once in this window."], 1)]
E.mark_copies(_cp)
check("mark_copies: a text of COPY_MIN_CHARS or more that repeats an earlier passage word for word (whitespace aside) carries that passage's id in copy_of; the first writing, a short reply said twice and a text written once carry none",
      [r.get("copy_of", "") for r in _cp] == ["", "", "", "C.1", "C.1", ""] and E.COPY_MIN_CHARS == 80 and all(r.get("copy_of", "") == "" for r in rows), [r.get("copy_of") for r in _cp])

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


# ---- the rider profile (2026-10-16, docs/RIDER_PROFILE_DESIGN.md): the settings the data is read against, from the record ----
# a record shaped like the live one (the probe of 2026-10-16), with invented values: measurements, four sport groups, the
# custom items of every kind, and the identifying fields the whitelist must leave behind
REC = {"id": "i1", "email": "x@y.z", "firstname": "A", "lastname": "B", "strava_id": "987654", "icu_api_key": "SECRET", "bio": "about me", "city": "Somewhere",
       "height": 1.80, "height_units": "CM", "weight": 70.0, "icu_weight": 71.5, "icu_resting_hr": 48, "icu_date_of_birth": "2000-03-15", "sex": "M", "timezone": "Europe/Copenhagen",
       "icu_wellness_keys": ["weight", "sleepQuality", "comments", "soreness", "Sickness", "hrv", "motivation", "soreness"],
       "sportSettings": [{"types": ["Ride", "VirtualRide"], "ftp": 300, "indoor_ftp": 290, "lthr": 170, "max_hr": 190, "hr_zones": [140, 155, 165, 175, 190], "hr_zone_names": ["Z1", "Z2", "Z3", "Z4", "Z5"],
                          "power_zones": [55, 75, 90, 105, 120, 999], "power_zone_names": ["Recovery", "Endurance", "Tempo", "Threshold", "VO2max", "Anaerobic"], "pace_zones": None, "threshold_pace": None,
                          "w_prime": None, "p_max": None, "sweet_spot_min": 0, "sweet_spot_max": 0, "mmp_model": {"type": "FFT_CURVES", "criticalPower": 295, "wPrime": 20000, "pMax": 1100, "ftp": 298}, "custom_zones_ids": [501, 502], "custom_field_ids": [], "activity_field_ids": []},
                         {"types": ["Run"], "ftp": None, "lthr": 165, "max_hr": 185, "hr_zones": [130, 150, 170, 185], "hr_zone_names": ["easy", "steady", "hard", "max"], "power_zones": None, "pace_zones": [77, 90, 100, 110, 999],
                          "pace_zone_names": ["P1", "P2", "P3", "P4", "P5"], "threshold_pace": 3.5, "mmp_model": None, "custom_zones_ids": [], "custom_field_ids": []},
                         {"types": ["Other"], "lthr": 165, "max_hr": 185, "hr_zones": None, "custom_zones_ids": []}],
       "custom_items": [{"id": 501, "type": "ZONES", "name": "Breathing", "description": "ventilation bins", "updated": "2026-01-29T13:19:41.293+00:00", "content": {"code": "Breath", "stream_type": "respiration", "zones": [{"id": "low", "name": "Low", "start": 10, "end": 25}, {"id": "high", "name": "High", "start": 25, "end": 60}]}},
                        {"id": 502, "type": "ZONES", "name": "Cadence", "content": {"code": "Cad", "stream_type": "cadence", "zones": [{"id": "grind", "name": "Grind", "start": 0, "end": 60}]}},
                        {"id": 601, "type": "INTERVAL_FIELD", "name": "Label", "content": {"code": "Lbl", "type": "select", "units": "", "options": [{"value": 1.0, "text": "Recovery"}, {"value": 2.0, "text": "Endurance"}]}},
                        {"id": 602, "type": "INTERVAL_FIELD", "name": "Breaths", "content": {"code": "Br", "type": "numeric", "units": "bpm"}},
                        {"id": 603, "type": "INPUT_FIELD", "name": "Sickness", "content": {"code": "Sickness", "type": "select", "options": ["None", "Mild", "Severe"]}},
                        {"id": 604, "type": "ACTIVITY_FIELD", "name": "How I slept", "content": {"code": "HowISlept", "type": "text"}},
                        {"id": 605, "type": "FITNESS_CHART", "name": "HRV", "content": {}},
                        {"id": 606, "type": "INTERVAL_FIELD", "name": "no code", "content": {"type": "numeric"}}]}
import datetime as _dt
prof = E.profile_frame(REC, today=_dt.date(2026, 10, 16))
ptext = prof.to_csv(index=False)
rows_of = lambda sec: prof[prof["section"] == sec]
keyed = {(r["section"], r["sport_types"], r["key"]): r for _, r in prof.iterrows()}
check("profile_frame: the columns of the design; the subject rows are the whitelist - weight (icu_weight first), height in metres whatever the display preference says, resting_hr, the age from the date of birth, sex, timezone - and nothing identifying is in the file",
      list(prof.columns) == E.PROFILE_COLUMNS and list(rows_of("subject")["key"]) == ["weight", "height", "resting_hr", "age", "sex", "timezone"]
      and keyed[("subject", "", "weight")]["value"] == 71.5 and keyed[("subject", "", "weight")]["unit"] == "kg" and keyed[("subject", "", "height")]["unit"] == "m" and keyed[("subject", "", "age")]["value"] == 26
      and keyed[("subject", "", "height")]["value"] == 1.80
      and all(s not in ptext for s in ("x@y.z", "SECRET", "2000-03-15", "firstname", "lastname", "strava", "987654", "about me", "Somewhere", "i1")), ptext[:600])
check("the sport rows: per group with its types pipe-joined - ftp, indoor_ftp, lthr, max_hr for the ride group, the model's cp / w_prime / p_max / ftp as model_* with the note; the run group's lthr, max_hr and threshold_pace; None settings and a zero sweet spot make no row",
      keyed[("sport", "Ride|VirtualRide", "ftp")]["value"] == 300 and keyed[("sport", "Ride|VirtualRide", "indoor_ftp")]["value"] == 290 and keyed[("sport", "Ride|VirtualRide", "model_cp")]["value"] == 295
      and "power-duration model" in keyed[("sport", "Ride|VirtualRide", "model_ftp")]["note"] and keyed[("sport", "Run", "threshold_pace")]["value"] == 3.5 and keyed[("sport", "Run", "threshold_pace")]["unit"] == "m/s"
      and ("sport", "Run", "ftp") not in keyed and ("sport", "Ride|VirtualRide", "w_prime") not in keyed and ("sport", "Ride|VirtualRide", "sweet_spot_min") not in keyed and list(rows_of("sport")[rows_of("sport")["sport_types"] == "Other"]["key"]) == ["lthr", "max_hr"], rows_of("sport").to_string()[:800])
check("the zone rows: hr zones from the upper bounds (a zone runs from the one before to its own), power zones as %FTP with the watts in the note and the open top high empty, the run's pace zones; the first row of each kind carries the convention",
      keyed[("zone", "Ride|VirtualRide", "hr_zone_2")]["low"] == 140 and keyed[("zone", "Ride|VirtualRide", "hr_zone_2")]["high"] == 155 and keyed[("zone", "Ride|VirtualRide", "hr_zone_2")]["note"] == "Z2"
      and keyed[("zone", "Ride|VirtualRide", "hr_zone_1")]["low"] == 0 and "upper bounds" in keyed[("zone", "Ride|VirtualRide", "hr_zone_1")]["note"]
      and keyed[("zone", "Ride|VirtualRide", "power_zone_3")]["value"] == 90 and keyed[("zone", "Ride|VirtualRide", "power_zone_3")]["unit"] == "%FTP" and keyed[("zone", "Ride|VirtualRide", "power_zone_3")]["note"] == "Tempo · 225-270 W at FTP 300"
      and keyed[("zone", "Ride|VirtualRide", "power_zone_6")]["high"] == "" and keyed[("zone", "Ride|VirtualRide", "power_zone_6")]["note"] == "Anaerobic · the open top · over 360 W at FTP 300"
      and keyed[("zone", "Run", "pace_zone_5")]["unit"] == "%threshold_pace" and ("zone", "Other", "hr_zone_1") not in keyed, rows_of("zone").to_string()[:1200])
check("the custom zone rows: one per zone keyed set:zone, the zone's name as the value, the stream as the unit, the bounds as low/high, the sports whose settings link the set, the set, the day it was defined and its description in the note",
      keyed[("custom_zone", "Ride|VirtualRide", "Breath:high")]["value"] == "High" and keyed[("custom_zone", "Ride|VirtualRide", "Breath:high")]["unit"] == "respiration" and keyed[("custom_zone", "Ride|VirtualRide", "Breath:high")]["low"] == 25
      and keyed[("custom_zone", "Ride|VirtualRide", "Breath:high")]["high"] == 60 and keyed[("custom_zone", "Ride|VirtualRide", "Breath:high")]["note"] == "set 'Breathing' · defined as it stands on 2026-01-29 · ventilation bins · time in it per activity is in the custom zone times file"
      and keyed[("custom_zone", "Ride|VirtualRide", "Cad:grind")]["note"] == "set 'Cadence' · time in it per activity is in the custom zone times file" and len(rows_of("custom_zone")) == 3, rows_of("custom_zone").to_string())
check("the custom field rows: keyed by code with the item's kind as the value, the units, the type and name and the options (number and text, or bare texts) and which file carries it in the note; a chart and an item without a code make no row",
      keyed[("custom_field", "", "Lbl")]["value"] == "INTERVAL_FIELD" and keyed[("custom_field", "", "Lbl")]["note"] == "select · 'Label' · options: 1 Recovery | 2 Endurance · on the intervals file under this code"
      and keyed[("custom_field", "", "Br")]["unit"] == "bpm" and keyed[("custom_field", "", "Br")]["note"] == "numeric · 'Breaths' · on the intervals file under this code"
      and keyed[("custom_field", "", "Sickness")]["note"] == "select · 'Sickness' · options: None | Mild | Severe · on the wellness file under this code"
      and keyed[("custom_field", "", "HowISlept")]["note"] == "text · 'How I slept' · on the summary file under this code" and len(rows_of("custom_field")) == 4 and "HRV" not in ptext, rows_of("custom_field").to_string())
check("the scale rows (2026-10-18): one per subjective wellness scale the account's form tracks (icu_wellness_keys), in its order, once each - the custom field, the comment and the measured keys none - with the range 1-4 and the platform's direction in the note; after the custom fields",
      list(rows_of("scale")["key"]) == ["sleepQuality", "soreness", "motivation"] and set(rows_of("scale")["value"]) == {"1-4"} and set(rows_of("scale")["low"]) == {1} and set(rows_of("scale")["high"]) == {4}
      and set(rows_of("scale")["note"]) == {E._WELLNESS_SCALE_NOTE} and "a bigger number is worse, 1 the good end" in E._WELLNESS_SCALE_NOTE and list(prof["section"])[-3:] == ["scale"] * 3, rows_of("scale").to_string())
check("an account without custom items or sport settings: the subject rows alone; an empty record: an empty table with the columns",
      list(E.profile_frame({"icu_weight": 60, "sex": "F"})["key"]) == ["weight", "sex"] and len(E.profile_frame({})) == 0 and list(E.profile_frame(None).columns) == E.PROFILE_COLUMNS)
ZACTS = [{"id": "a1", "start_date_local": "2026-09-01T07:00:00", "type": "Ride", "custom_zones": [{"code": "Breath", "zones": [{"id": "low", "start": 10, "end": 25, "secs": 1200}, {"id": "high", "start": 25, "end": 60, "secs": 300}]},
                                                                                                   {"code": "Cad", "zones": [{"id": "grind", "start": 0, "end": 60, "secs": 90}]}]},
         {"id": "a2", "start_date_local": "2026-09-02T07:00:00", "type": "Ride", "custom_zones": [{"code": "Breath", "zones": [{"id": "low", "start": 10, "end": 25, "secs": 2000}, {"id": "high", "start": 25, "end": 60, "secs": 0}]},
                                                                                                   {"code": "Gone", "zones": [{"id": "x", "start": 0, "end": 1, "secs": 5}]}]},
         {"id": "a3", "start_date_local": "2026-09-03T07:00:00", "type": "Run"}]
zt = E.custom_zone_times_frame(ZACTS, REC["custom_items"])
check("custom_zone_times_frame: a row per activity and zone with the set and zone names from the definitions, the bounds in force and the seconds; newest first; a set the account no longer defines keeps its code with no name; an activity without custom zones makes no row",
      list(zt.columns) == E.ZONE_TIMES_COLUMNS and len(zt) == 6 and zt.iloc[0]["activity_id"] == "a2" and set(zt["set_code"]) == {"Breath", "Cad", "Gone"}
      and zt[(zt["activity_id"] == "a1") & (zt["zone_id"] == "high")].iloc[0]["secs"] == 300 and zt[(zt["activity_id"] == "a1") & (zt["zone_id"] == "high")].iloc[0]["zone_name"] == "High"
      and zt[zt["set_code"] == "Gone"].iloc[0]["set_name"] == "Gone" and zt[zt["set_code"] == "Gone"].iloc[0]["zone_name"] == "" and "a3" not in set(zt["activity_id"]), zt.to_string())
check("custom_zone_times_frame is None for an account without custom zone sets (no file is written), and an empty table with the columns when the sets are defined but no activity carries times",
      E.custom_zone_times_frame(ZACTS, [it for it in REC["custom_items"] if it["type"] != "ZONES"]) is None and len(E.custom_zone_times_frame([{"id": "a3"}], REC["custom_items"])) == 0
      and list(E.custom_zone_times_frame([], REC["custom_items"]).columns) == E.ZONE_TIMES_COLUMNS)
check("option_pairs: objects as (value, text), bare texts standing for themselves, nothing for an empty option",
      E.option_pairs([{"value": 1.0, "text": "A"}, "B", {"text": "C"}, {}]) == [(1.0, "A"), ("B", "B"), (None, "C")] and E.option_pairs(None) == [])
summ = E.create_activity_summary([{"id": "a1", "start_date_local": "2026-09-01T07:00:00", "athlete_max_hr": 190, "icu_pm_ftp": 280, "icu_ftp": 300, "icu_power_zones": [55, 75, 90], "icu_hr_zones": [140, 155], "pace_zones": None}])
check("the summary carries the settings in force that day: max_hr_setting, pm_ftp_watts beside ftp_watts, the zone bounds pipe-joined; no column for an absent list",
      summ.iloc[0]["max_hr_setting"] == 190 and summ.iloc[0]["pm_ftp_watts"] == 280 and summ.iloc[0]["ftp_watts"] == 300 and summ.iloc[0]["power_zones"] == "55|75|90" and summ.iloc[0]["hr_zones"] == "140|155" and "pace_zones" not in summ.columns, summ.to_dict())
check("save_aux_dataset names the two files by their kinds and the window", os.path.basename(E.save_aux_dataset(prof, "rider", "u", "2026-06-15", "2026-10-13")) == "rider_profile_20260615_to_20261013.csv"
      and os.path.basename(E.save_aux_dataset(zt, "zones", "u", "2026-06-15", "2026-10-13")) == "custom_zone_times_20260615_to_20261013.csv")
check("the executor's build stamp is v70 (the cache as a tree; the feeds in the store since v68; the context's activity day and copies since v62)", "v70" in E.EXECUTOR_BUILD and "tree" in E.EXECUTOR_BUILD, E.EXECUTOR_BUILD)

# ---- every custom field under its code (2026-10-16, patch 0183): the account's definitions decode the files' columns ----
IF = E.field_definitions(REC["custom_items"], "INTERVAL_FIELD")
check("field_definitions: one kind at a time, by code, with the name, the type and a select's option pairs; a chart and an item without a code make no entry",
      set(IF) == {"Lbl", "Br"} and IF["Lbl"] == ("Label", "select", [(1.0, "Recovery"), (2.0, "Endurance")]) and IF["Br"] == ("Breaths", "numeric", [])
      and set(E.field_definitions(REC["custom_items"], "INPUT_FIELD")) == {"Sickness"} and E.field_definitions(REC["custom_items"], "INPUT_FIELD")["Sickness"][2] == [("None", "None"), ("Mild", "Mild"), ("Severe", "Severe")]
      and set(E.field_definitions(REC["custom_items"], "ACTIVITY_FIELD")) == {"HowISlept"} and E.field_definitions(None, "INTERVAL_FIELD") == {}, IF)
check("decode_select: the API's text gives (text, its number); a number entered by hand gives (its text, the number); a value outside the options is kept as text with no number; bare-text options carry no number; None stays None",
      E.decode_select("Endurance", IF["Lbl"][2]) == ("Endurance", 2.0) and E.decode_select(2, IF["Lbl"][2]) == ("Endurance", 2.0) and E.decode_select(2.0, IF["Lbl"][2]) == ("Endurance", 2.0)
      and E.decode_select("Sprint", IF["Lbl"][2]) == ("Sprint", None) and E.decode_select("Mild", [("None", "None"), ("Mild", "Mild")]) == ("Mild", None) and E.decode_select(None, IF["Lbl"][2]) == (None, None)
      and E.decode_select(float("nan"), IF["Lbl"][2]) == (None, None))
recs = E.process_interval_data({"icu_intervals": [{"LapNumber": 1, "start_time": 0, "zone": "Z2", "Lbl": "Endurance", "Br": 31.5, "TVLlabelfield": "x", "Other": 9},
                                                  {"LapNumber": 2, "start_time": 100, "Lbl": 1, "Br": None},
                                                  {"LapNumber": 3, "start_time": 200}]}, "a1", IF)
check("process_interval_data with the definitions: the select's text in its code's column and the number in <code>_value (the text decoded, a number decoded the other way), a numeric field under its code, a key the account does not define left out, a value absent making no column, the four legacy columns as before",
      recs[0]["Lbl"] == "Endurance" and recs[0]["Lbl_value"] == 2.0 and recs[0]["Br"] == 31.5 and recs[0]["label"] == "x" and "Other" not in recs[0]
      and recs[1]["Lbl"] == "Recovery" and recs[1]["Lbl_value"] == 1.0 and "Br" not in recs[1] and "Lbl" not in recs[2] and recs[2]["lap_number"] == 3 and recs[2]["label"] is None
      and E.process_interval_data({"icu_intervals": [{"LapNumber": 1, "Lbl": "Tempo"}]}, "a1")[0].get("Lbl") is None, recs)
summ2 = E.create_activity_summary([{"id": "a1", "start_date_local": "2026-09-01T07:00:00", "HowISlept": "badly", "Mood": 4}, {"id": "a2", "start_date_local": "2026-09-02T07:00:00"}],
                                   {"HowISlept": ("How I slept", "text", []), "Mood": ("Mood", "select", [(1.0, "low"), (4.0, "high")])})
check("the summary carries the account's activity fields under their codes - a text as it is, a select as its text with the number beside it; a day without them is empty there",
      summ2.set_index("activity_id").loc["a1", "HowISlept"] == "badly" and summ2.set_index("activity_id").loc["a1", "Mood"] == "high" and summ2.set_index("activity_id").loc["a1", "Mood_value"] == 4.0
      and pd.isna(summ2.set_index("activity_id").loc["a2", "Mood"]), summ2.to_dict("records"))
class _WellSession:
    def get(self, url, params=None, timeout=None):
        return _R([{"id": "2026-09-01", "fatigue": 3, "Sickness": "Mild", "Mood": 4}, {"id": "2026-09-02", "fatigue": 2, "Sickness": None, "Mood": "low"}, {"id": "2026-09-03", "fatigue": 1}])
wdf = E.fetch_wellness_data(_WellSession(), "http://icu/api/v1", "2026-09-01", "2026-09-03", fields={"Sickness": ("Sickness", "select", [("None", "None"), ("Mild", "Mild")]), "Mood": ("Mood", "select", [(1.0, "low"), (4.0, "high")]), "Bolt": ("Bolt", "numeric", [])})
wrow = wdf.set_index(wdf["date"].dt.strftime("%Y-%m-%d"))
check("the wellness file: every field under its code as the records carry it; a select with numbered options becomes its text with <code>_value beside it (a number and a text both decoded); bare-text options keep the text and add no number; a field with no value in the window makes no column",
      wrow.loc["2026-09-01", "Sickness"] == "Mild" and "Sickness_value" not in wdf.columns and wrow.loc["2026-09-01", "Mood"] == "high" and wrow.loc["2026-09-01", "Mood_value"] == 4.0
      and wrow.loc["2026-09-02", "Mood"] == "low" and wrow.loc["2026-09-02", "Mood_value"] == 1.0 and pd.isna(wrow.loc["2026-09-03", "Mood"]) and "Bolt" not in wdf.columns and wrow.loc["2026-09-03", "fatigue"] == 1, wdf.to_dict("records"))

passed = sum(1 for _, ok in results if ok)
failed = [n for n, ok in results if not ok]
print(f"\n{passed} passed, {len(failed)} failed")
sys.exit(1 if failed else 0)
