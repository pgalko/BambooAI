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
    return act


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
