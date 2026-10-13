"""The stack's stand-in for the two integrations' APIs: Intervals.icu (the activity list, a session's FIT file, its
laps, the wellness log, the subject's record, the calendar, a chat's members and a session's messages) and Endura (the race list, a race's data), served from apis_data.py's calendar. The
executor's requests to intervals.icu and team-hub.co.uk are routed here by executor_launcher.py when
STACK_FAKE_APIS names this server; nothing in the executor changes.

    python3 tools/stack/fake_apis.py --port 5057
"""
import argparse
import gzip
import logging
import os
import sys

from flask import Flask, Response, jsonify, request

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import apis_data as D                                    # noqa: E402
from fit_writer import write_activity                    # noqa: E402

app = Flask(__name__)
logging.getLogger("werkzeug").setLevel(logging.WARNING)
CALLS = []


def _auth_ok():
    """Intervals: basic auth ("API_KEY", key); Endura: a bearer token. Any non-empty secret is accepted; none is 401."""
    a = request.authorization
    if a and (a.password or a.username):
        return True
    h = request.headers.get("Authorization", "")
    return h.startswith("Bearer ") and len(h) > 7


@app.before_request
def _log():
    CALLS.append((request.method, request.path, dict(request.args)))


@app.route("/health")
def health():
    return jsonify({"status": "ok", "calls": len(CALLS)})


@app.route("/calls")
def calls():
    return jsonify({"calls": CALLS[-200:]})


# ------------------------------------------------------------ Intervals.icu
@app.route("/api/v1/athlete/0/activities")
def activities():
    if not _auth_ok():
        return jsonify({"error": "unauthorized"}), 401
    oldest, newest = request.args.get("oldest", ""), request.args.get("newest", "")
    if not oldest or not newest:
        return jsonify({"error": "oldest and newest are needed"}), 400
    return jsonify(D.activities(oldest, newest))


@app.route("/api/v1/activity/<int:aid>/fit-file")
def fit_file(aid):
    if not _auth_ok():
        return jsonify({"error": "unauthorized"}), 401
    day = _day_of(aid)
    if day is None:
        return jsonify({"error": "no such activity"}), 404
    body = write_activity(D.fit_records(day), fields=D.fit_fields(day))
    return Response(gzip.compress(body), mimetype="application/octet-stream")


@app.route("/api/v1/activity/<int:aid>/intervals")
def intervals(aid):
    if not _auth_ok():
        return jsonify({"error": "unauthorized"}), 401
    day = _day_of(aid)
    if day is None:
        return jsonify({"error": "no such activity"}), 404
    return jsonify(D.laps(day))


@app.route("/api/v1/athlete/0/wellness")
def wellness():
    if not _auth_ok():
        return jsonify({"error": "unauthorized"}), 401
    return jsonify(D.wellness(request.args.get("oldest", ""), request.args.get("newest", "")))


@app.route("/api/v1/athlete/0")
@app.route("/api/v1/athlete/<athlete_id>")
def athlete(athlete_id="0"):
    if not _auth_ok():
        return jsonify({"error": "unauthorized"}), 401
    return jsonify(D.SUBJECT)


@app.route("/api/v1/athlete/0/events")
def events():
    if not _auth_ok():
        return jsonify({"error": "unauthorized"}), 401
    oldest, newest = request.args.get("oldest", ""), request.args.get("newest", "")
    if not oldest or not newest:
        return jsonify({"error": "oldest and newest are needed"}), 400
    out = D.events(oldest, newest)
    cats = request.args.get("category")
    if cats:
        wanted = {c.strip() for c in cats.split(",") if c.strip()}
        bad = wanted - {"WORKOUT", "RACE_A", "RACE_B", "RACE_C", "NOTE", "PLAN", "HOLIDAY", "SICK", "INJURED", "SET_EFTP", "FITNESS_DAYS", "SEASON_START", "TARGET", "SET_FITNESS"}
        if bad:
            return jsonify({"status": 422, "error": "Invalid category, expected comma separated list of: WORKOUT, RACE_A, RACE_B, RACE_C, NOTE, PLAN, HOLIDAY, SICK, INJURED, SET_EFTP, FITNESS_DAYS, SEASON_START, TARGET, SET_FITNESS"}), 422
        out = [e for e in out if e["category"] in wanted]
    return jsonify(out)


@app.route("/api/v1/chats/<int:cid>")
def chat(cid):
    if not _auth_ok():
        return jsonify({"error": "unauthorized"}), 401
    return jsonify(D.chat(cid))


@app.route("/api/v1/activity/<int:aid>/messages")
def messages(aid):
    if not _auth_ok():
        return jsonify({"error": "unauthorized"}), 401
    day = _day_of(aid)
    if day is None:
        return jsonify({"error": "no such activity"}), 404
    return jsonify(D.messages(day))


def _day_of(aid):
    from datetime import date
    try:
        ordinal_mod = int(aid) - 100000
    except (TypeError, ValueError):
        return None
    # the id is the ordinal modulo 100000: resolve it within the last few years
    today = date.today().toordinal()
    for base in range((today // 100000) * 100000, today // 100000 * 100000 - 300000, -100000):
        cand = base + ordinal_mod
        if 0 < cand <= today + 366:
            try:
                return date.fromordinal(cand)
            except (ValueError, OverflowError):
                return None
    return None


# ------------------------------------------------------------ Endura
@app.route("/endura_api/getraces")
def get_races():
    if not _auth_ok():
        return jsonify({"error": "unauthorized"}), 401
    return jsonify(D.RACES)


@app.route("/endura_api/getracedata")
def get_race_data():
    if not _auth_ok():
        return jsonify({"error": "unauthorized"}), 401
    data = D.race_data(request.args.get("raceid", "0"))
    if not data:
        return jsonify({"error": "no such race"}), 404
    return jsonify(data)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=5057)
    a = ap.parse_args()
    app.run(host="127.0.0.1", port=a.port, threaded=True)


if __name__ == "__main__":
    main()
