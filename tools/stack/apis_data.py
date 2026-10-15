"""The data behind the stack's fake Intervals.icu and Endura (fake_apis.py): one subject's calendar, deterministic
in the date, with the variation the real loaders produce between windows built in - so a routine made on one window
meets, on the next, a column that is not there, an auxiliary file that was not written, a race without a sensor.

Relative to today (the stack's clock):
  - a session every day; at home the local clock reads 9 most days (7 or 18 now and then), in a ten-day travel block
    every hundred days the subject is six hours behind (local 11); `start_date_local` and `start_date` carry the offset;
  - rides on every seventh day only until sixty days ago (the power meter went with the bike): a window inside the
    last sixty days has no `power` column in the frame and no `avg_power` / `elevation_gain_m` in the summary;
  - the device logged temperature until forty days ago: a recent window lacks `temperature`;
  - wellness was logged until sixty days ago: a recent window has no wellness file at all; `hrv` only until ninety;
  - laps (the intervals file): three per session, with watts on rides.
Endura: three races; the second has no power channel and no climbs (a flat course), the third has a different
profile field set.
The words beside the data (docs/CONTEXT_DESIGN.md, 2026-10-13), deterministic in the date too: two sessions in three
carry a chat (the subject writes, in Danish or English by turns; the coach answers on half of them; every eleventh
day a private NOTE by the coach), every ninth session a description in prose and every thirteenth one that is only
a workout structure, tags on every fifth, a coach's tick on every sixth; the wellness log has a comment every
eighth day and the custom select `Sickness` on sick days; the calendar has a planned workout paired with every ride,
a note every seventeenth day, a sick span of three days once every fifty, a race (its description HTML) once every
fifty, and a note the coach hid from the subject every twenty-third day. A fortnight 21 to 34 days ago is silent
(2026-10-14, context step 5): nothing written at all - no description, tag or tick, nothing in the calendar - so a
routine run on a window inside it meets a context file with no rows and no codes file.
"""
import hashlib
from datetime import date, datetime, timedelta, timezone

import numpy as np

HOME_OFFSET_H, TRAVEL_OFFSET_H = 2, -4
HOME_TZ, TRAVEL_TZ = "Europe/Berlin", "America/Toronto"


def _h(day: date, salt: str = "") -> int:
    return int(hashlib.md5(f"{day.isoformat()}:{salt}".encode()).hexdigest()[:8], 16)


def days_ago(day: date, today: date = None) -> int:
    return ((today or date.today()) - day).days


def is_travel(day: date) -> bool:
    return (day.toordinal() // 10) % 10 == 3


def is_ride(day: date, today: date = None) -> bool:
    return day.toordinal() % 7 == 0 and days_ago(day, today) > 60


def has_temperature(day: date, today: date = None) -> bool:
    return days_ago(day, today) > 40


def has_wellness(day: date, today: date = None) -> bool:
    return days_ago(day, today) > 60


def local_hour(day: date) -> int:
    if is_travel(day):
        return 11
    return [7, 9, 9, 9, 18][_h(day, "hour") % 5]


def activity_id(day: date) -> int:
    return 100000 + day.toordinal() % 100000


def activity(day: date, today: date = None) -> dict:
    """One activity as the Intervals.icu list route returns it (the fields the summary maps, plus file_type)."""
    offset = TRAVEL_OFFSET_H if is_travel(day) else HOME_OFFSET_H
    local = datetime(day.year, day.month, day.day, local_hour(day), 0, 0)
    utc = local - timedelta(hours=offset)
    ride = is_ride(day, today)
    secs = 3000 + (_h(day, "secs") % 2400)
    dist = (secs / 3600.0) * (28000 if ride else 11500)
    act = {"id": activity_id(day), "name": ("Ride" if ride else "Run") + " " + day.isoformat(), "type": "Ride" if ride else "Run",
           "start_date_local": local.strftime("%Y-%m-%dT%H:%M:%S"), "start_date": utc.strftime("%Y-%m-%dT%H:%M:%SZ"),
           "timezone": TRAVEL_TZ if is_travel(day) else HOME_TZ, "elapsed_time": secs + 120, "moving_time": secs, "distance": round(dist, 1),
           "average_heartrate": 128 + _h(day, "hr") % 25, "max_heartrate": 160 + _h(day, "mhr") % 20, "icu_training_load": 40 + _h(day, "tl") % 60,
           "file_type": "fit", "icu_zone_times": [{"id": "Z1", "secs": secs // 3}, {"id": "Z2", "secs": secs // 2}], "icu_hr_zone_times": [secs // 3, secs // 2, secs // 6, 0, 0],
           "source": "GARMIN_CONNECT", "device_name": "device-7", "trainer": False, "race": False, "commute": False}
    if ride:
        act["icu_average_watts"] = 180 + _h(day, "w") % 60
        act["total_elevation_gain"] = 300 + _h(day, "elev") % 500
        act["paired_event_id"] = workout_event_id(day)
        act["compliance"] = round(0.7 + (_h(day, "cmp") % 30) / 100.0, 2)
    # the words beside the numbers (2026-10-13)
    o = day.toordinal()
    if has_chat(day, today):
        act["icu_chat_id"] = chat_id(day)
    if is_silent(day, today):
        return act
    if o % 9 == 0:
        act["description"] = SUBJECT_LINES[_h(day, "desc") % len(SUBJECT_LINES)]
    elif o % 13 == 0:
        act["description"] = "-10m 220w\n-5m 240w\n-5m 260w"
    if o % 5 == 0:
        act["tags"] = ["tempo"] if o % 10 == 0 else ["easy"]
    if o % 6 == 0:
        act["coach_tick"] = 4
    return act


# ---- the words beside the data (docs/CONTEXT_DESIGN.md) ----
SUBJECT = {"id": "i0", "name": "The subject", "timezone": HOME_TZ, "status": "ACTIVE", "icu_coach": False,
           "coach_ticks": [{"id": 4, "text": "Good"}], "icu_wellness_keys": ["weight", "restingHR", "comments", "Sickness"],
           "custom_items": [{"type": "INPUT_FIELD", "name": "Sickness", "visibility": "PRIVATE",
                             "content": {"code": "Sickness", "type": "select", "options": ["None", "Mild", "Severe"]}},
                            {"type": "INTERVAL_FIELD", "name": "Label", "content": {"code": "Lbl", "type": "select"}}]}
COACH_ID = "c1"
SUBJECT_LINES = ["Benene var tunge i dag, kørte kortere end planlagt.", "Good legs today, held the power easily.",
                 "Sov dårligt, var træt fra start.", "Felt strong on the climbs, no complaints.",
                 "Lidt ondt i knæet efter turen.", "Cut the session short, work ran late."]
COACH_LINES = ["Fint, tag det roligt i morgen.", "Good. Same again Thursday.", "Keep the cadence up next time.", "Bra jobba."]


def is_silent(day: date, today: date = None) -> bool:
    """The fortnight 21 to 34 days ago, in which nothing is written (chats, rides and the wellness log stop at sixty
    days anyway): a window inside it has a context file of its header alone."""
    return 20 < days_ago(day, today) <= 34


def has_chat(day: date, today: date = None) -> bool:
    return days_ago(day, today) > 60 and _h(day, "chat") % 3 != 0


def chat_id(day: date) -> int:
    return 500000 + day.toordinal() % 100000


def workout_event_id(day: date) -> int:
    return 700000 + day.toordinal() % 100000


def messages(day: date, today: date = None):
    """The messages under a session's chat, newest first as the API returns them: the subject's line, the coach's
    reply on half the days, a private NOTE by the coach every eleventh day. `created` is UTC."""
    if not has_chat(day, today):
        return []
    offset = TRAVEL_OFFSET_H if is_travel(day) else HOME_OFFSET_H
    local = datetime(day.year, day.month, day.day, local_hour(day) + 2, 10, 0)
    base = 900000 + (day.toordinal() % 100000) * 3
    out = [{"id": base, "athlete_id": SUBJECT["id"], "name": SUBJECT["name"], "created": (local - timedelta(hours=offset)).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "type": "TEXT", "content": SUBJECT_LINES[_h(day, "line") % len(SUBJECT_LINES)], "activity_id": str(activity_id(day))}]
    if _h(day, "reply") % 2 == 0:
        out.insert(0, {"id": base + 1, "athlete_id": COACH_ID, "name": "The coach", "created": (local + timedelta(hours=1) - timedelta(hours=offset)).strftime("%Y-%m-%dT%H:%M:%SZ"),
                       "type": "TEXT", "content": COACH_LINES[_h(day, "coach") % len(COACH_LINES)], "activity_id": str(activity_id(day))})
    if day.toordinal() % 11 == 0:
        out.insert(0, {"id": base + 2, "athlete_id": COACH_ID, "name": "The coach", "created": (local + timedelta(hours=2) - timedelta(hours=offset)).strftime("%Y-%m-%dT%H:%M:%SZ"),
                       "type": "NOTE", "content": "Private: check the sleep log this week.", "activity_id": str(activity_id(day))})
    return out


def chat(cid: int) -> dict:
    return {"id": cid, "type": "ACTIVITY", "members": [{"athlete_id": COACH_ID, "name": "The coach", "role": "COACH", "coach": True},
                                                        {"athlete_id": SUBJECT["id"], "name": SUBJECT["name"], "role": "MEMBER"}]}


def events(oldest: str, newest: str, today: date = None):
    """The calendar of a window as the API returns it (end_date_local exclusive)."""
    out = []
    for d in days_in(oldest, newest):
        if is_silent(d, today):
            continue
        o = d.toordinal()
        start = d.strftime("%Y-%m-%dT00:00:00")
        nxt = (d + timedelta(days=1)).strftime("%Y-%m-%dT00:00:00")
        if is_ride(d, today):
            # the plan's numbers and its structure beside the words (2026-10-15: the planned workouts file)
            out.append({"id": workout_event_id(d), "category": "WORKOUT", "start_date_local": start, "end_date_local": nxt, "name": "Endurance",
                        "description": "Keep it conversational, fuel every hour.\n-2h 60%", "created_by_id": COACH_ID, "type": "Ride", "tags": ["primary"] if o % 10 == 0 else [],
                        "moving_time": 7200, "icu_training_load": 90, "distance": 56000, "training_availability": "NORMAL",
                        "workout_doc": {"steps": [{"duration": 7200, "power": {"units": "%ftp", "value": 60}}]}})
        elif o % 11 == 0:
            # a planned session with no activity paired to it: a skipped one (its description is steps alone - no passage)
            out.append({"id": workout_event_id(d), "category": "WORKOUT", "start_date_local": start, "end_date_local": nxt, "name": "Strength",
                        "description": "-45m core", "created_by_id": COACH_ID, "type": "WeightTraining", "moving_time": 2700, "icu_training_load": 20})
        if o % 17 == 0:
            out.append({"id": 800000 + o % 100000, "category": "NOTE", "start_date_local": start, "end_date_local": nxt, "name": "Exam week", "description": "Exams all week, short sessions only.", "created_by_id": SUBJECT["id"]})
        if o % 50 == 10:
            out.append({"id": 810000 + o % 100000, "category": "SICK", "start_date_local": start, "end_date_local": (d + timedelta(days=3)).strftime("%Y-%m-%dT00:00:00"), "name": "Cold", "created_by_id": SUBJECT["id"]})
        if o % 50 == 25:
            out.append({"id": 820000 + o % 100000, "category": "RACE_B", "start_date_local": start, "end_date_local": nxt, "name": "Club race", "description": "<p><strong>Distance: </strong>60km</p><p>Rolling course</p>", "created_by_id": SUBJECT["id"]})
        if o % 23 == 0:
            out.append({"id": 830000 + o % 100000, "category": "NOTE", "start_date_local": start, "end_date_local": nxt, "name": "Watch motivation", "description": "", "created_by_id": COACH_ID, "hide_from_athlete": True})
    return out


def fit_fields(day: date, today: date = None):
    fields = ["heart_rate", "speed", "distance", "cadence", "altitude"]
    if has_temperature(day, today):
        fields.append("temperature")
    if is_ride(day, today):
        fields.append("power")
    return fields


def fit_records(day: date, today: date = None, n: int = 40):
    """The records of the session's file: n seconds at 1 Hz with the day's fields."""
    offset = TRAVEL_OFFSET_H if is_travel(day) else HOME_OFFSET_H
    start = datetime(day.year, day.month, day.day, local_hour(day), 0, 0, tzinfo=timezone.utc) - timedelta(hours=offset)
    rng = np.random.default_rng(_h(day, "fit"))
    ride = is_ride(day, today)
    out = []
    for i in range(n):
        r = {"timestamp": start + timedelta(seconds=i), "heart_rate": int(120 + rng.integers(0, 30)), "speed": round(float(7.5 if ride else 3.2) + rng.normal(0, 0.2), 3),
             "distance": round(i * (7.5 if ride else 3.2), 2), "cadence": int(85 + rng.integers(0, 8)), "altitude": round(120.0 + i * 0.1, 1)}
        if has_temperature(day, today):
            r["temperature"] = int(18 + rng.integers(0, 6))
        if ride:
            r["power"] = int(190 + rng.integers(0, 60))
        out.append(r)
    return out


def days_in(oldest: str, newest: str):
    a, b = date.fromisoformat(oldest[:10]), date.fromisoformat(newest[:10])
    d = a
    while d <= b:
        yield d
        d += timedelta(days=1)


def activities(oldest: str, newest: str, today: date = None):
    return [activity(d, today) for d in days_in(oldest, newest)]


def wellness(oldest: str, newest: str, today: date = None):
    out = []
    for d in days_in(oldest, newest):
        if not has_wellness(d, today):
            continue
        row = {"id": d.isoformat(), "weight": round(71.0 + (_h(d, "wt") % 20) / 10.0, 1), "restingHR": 46 + _h(d, "rhr") % 8, "sleepSecs": 6 * 3600 + (_h(d, "sl") % 7200)}
        if days_ago(d, today) > 90:
            row["hrv"] = 60 + _h(d, "hrv") % 30
        o = d.toordinal()
        if o % 8 == 0:
            row["comments"] = "Dårlig nat, vågnede flere gange." if o % 16 == 0 else "Slept well, fresh this morning."
        if o % 50 in (10, 11, 12):
            row["Sickness"] = "Mild"
        out.append(row)
    return out


def laps(day: date, today: date = None):
    ride = is_ride(day, today)
    out = []
    for k in range(1, 4):
        lap = {"LapNumber": k, "start_time": (k - 1) * 1000, "end_time": k * 1000, "distance": 1000.0 * k, "moving_time": 1000, "elapsed_time": 1010,
               "average_heartrate": 125 + _h(day, f"lap{k}") % 30, "zone": "Z2"}
        if ride:
            lap["average_watts"] = 185 + _h(day, f"w{k}") % 50
        out.append(lap)
    return {"icu_intervals": out}


# ------------------------------------------------------------------ Endura
RACES = [{"race_id": 1, "race_title": "Spring classic", "race_date": "2026-04-12"},
         {"race_id": 2, "race_title": "Flat crit", "race_date": "2026-06-20"},
         {"race_id": 3, "race_title": "Hill circuit", "race_date": "2026-09-05"}]


def race_data(race_id: int) -> dict:
    rid = int(race_id)
    race = next((r for r in RACES if r["race_id"] == rid), None)
    if race is None:
        return {}
    rng = np.random.default_rng(1000 + rid)
    athletes = ["A01", "A02", "A03"]
    primary = []
    for a in athletes:
        for t in range(60):
            row = {"euid": a, "timestamp": t * 10, "speed": round(float(9.5 + rng.normal(0, 0.5)), 2), "heart_rate": int(150 + rng.integers(0, 25)),
                   "distance": round(t * 95.0, 1), "altitude": round(50.0 + (t % 20) * (0.5 if rid == 2 else 4.0), 1)}
            row["power"] = 0 if rid == 2 else int(250 + rng.integers(0, 80))      # the flat crit's file carries no power (all zero: the loader drops it)
            primary.append(row)
    profile = [{"euid": a, "name": f"Subject {a}", "ftp": 260 + i * 15, "weight_kg": 68 + i * 3} for i, a in enumerate(athletes)]
    if rid == 3:
        profile = [dict(p, team="hill") for p in profile]
    turns = [{"turn_turn_name": f"T{k}", "turn_time": k * 120, "distance": k * 1100} for k in range(1, 5)]
    climbs = [] if rid == 2 else [{"name": f"Climb {k}", "start": k * 1500, "length_m": 800 + k * 100, "gradient": 5.5 + k} for k in range(1, 3)]
    waymarkers = [{"name": "Start", "distance": 0}, {"name": "Feed", "distance": 3000}, {"name": "Finish", "distance": 5700}]
    return {"race_title": race["race_title"], "race_date": race["race_date"], "primary_data": primary, "profile_data": profile,
            "turns": turns, "climbs": climbs, "waymarkers": waymarkers}
