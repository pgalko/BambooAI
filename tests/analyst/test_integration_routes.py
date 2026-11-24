"""The integrations on the web app's side, with no browser and no executor (0348). The modules that put data into a
session - Intervals.icu, Endura, SweatStack, the dataset cache - and the container's routes are started as
web_app/app.py starts them: each with the names its own call there hands it, on a Flask app of the suite's. The
executor, the orchestrator and the key store are stand-ins; a session's instance is built by the web app's own
get_bamboo_ai, taken from its file (0349). Each load is then driven through its route, as the page drives it: what the
executor is asked for, what the session's settings and its instance hold afterwards, what the page is answered.

tests/e2e/test_integrations.py walks these loads in a browser, against the real executor and the stack's
Intervals.icu; it needs Playwright, the FIT parser and pyarrow, and is skipped where they are not installed. This
suite needs none of them and runs wherever the battery does.
Run: python3 tests/analyst/test_integration_routes.py"""
import ast, datetime, json, logging, os, re, sys, tempfile, types
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path[:0] = [HERE, ROOT, os.path.join(ROOT, "delve"), os.path.join(ROOT, "web_app")]
import _stubs  # noqa: F401,E402
from unittest import mock  # noqa: E402
os.environ["OPENAI_API_KEY"] = "x"; os.environ["EXECUTION_MODE"] = "api"                      # the hosted edition: a container per user
for name in ("EXECUTOR_API_BASE_URL", "BAMBOO_EXECUTOR_CONTAINER"):
    os.environ.pop(name, None)
os.chdir(tempfile.mkdtemp())                           # the product's modules make their log folder where they are loaded
import requests  # noqa: E402
from flask import Flask  # noqa: E402
from analyst.routines import key_fingerprint  # noqa: E402
from bambooai import executor_client, utils  # noqa: E402

passed, failed = [], []
def check(name, cond, detail=""):
    (passed if cond else failed).append(name); print(("  ok   " if cond else "  FAIL ") + name + ("" if cond else f"  <- {detail}"))


# ------------------------------------------------------------------------------------------ the stand-ins
# who is signed in, and the store of keys and plans: the routes ask these by name
signed_in = types.ModuleType("auth")
signed_in.requires_auth = lambda route: route
signed_in.get_current_user_id = lambda: "auth0|u1"
store = types.ModuleType("auth.supabase_client")
store.__getattr__ = lambda name: (lambda *a, **k: {"ok": True, "data": {}})       # any other of its functions: an empty answer
store.get_intervals_api_key = lambda user_id, auth0_id, athlete_id=None: {"i77001": "key-of-the-first", None: "key-of-the-first"}.get(athlete_id)
store.list_intervals_athletes = lambda user_id, auth0_id: [{"athlete_id": "i77001", "athlete_name": "First Athlete", "created_at": "2026-11-01", "last_used_at": None}]
store.get_user_subscription = lambda auth0_id: {"ok": True, "data": {"compute_tier": "plus", "integration_config": {"sweatstack_extended": True}}}
store.get_endura_api_key = lambda user_id, auth0_id: "key-of-the-races"
store.get_sweatstack_token = lambda user_id, auth0_id: "token-of-the-first"
sys.modules["auth"], sys.modules["auth.supabase_client"] = signed_in, store

ADDRESS = {"now": "http://executor.test:5001"}         # where the user's container answers: another port each time it is started
PAGE = {"columns": ["plot", "yield_t_ha"], "rows": [[1, 4.4], [2, 4.9]], "total": 2}       # a frame's or a file's first page, as the executor gives it
ANSWERS, asked = {}, []                                # the executor's answer by path; what it was asked: (path, body)


class Reply:
    """An answer of the executor's, as far as the routes read one."""
    def __init__(self, body, status=200):
        self.status_code, self.body, self.text = status, body, json.dumps(body)

    def json(self):
        return self.body

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError(f"{self.status_code} from the executor")


def executor(url, **kw):
    path = "/" + url.split("/", 3)[3]
    asked.append((path, kw.get("json") or {}))
    if path in ("/dataframe_page", "/aux_page"):
        return Reply(dict(PAGE))
    return Reply(ANSWERS[path]) if path in ANSWERS else Reply({"error": "no such route"}, 404)


def sent_to(path):
    """What the executor was last asked at `path`."""
    return next((body for p, body in reversed(asked) if p == path), None)


SETTINGS, INSTANCES, restarts = {}, {}, []             # the web app's user_preferences and bamboo_ai_instances; the containers restarted
put_away = []                                          # the sessions whose instance the factory put away to make another
quiet = logging.getLogger("the integrations' lines"); quiet.propagate = False; quiet.addHandler(logging.NullHandler())
with open(os.path.join(ROOT, "web_app", "app.py"), encoding="utf-8") as f:
    APP = ast.parse(f.read())


class Host(types.SimpleNamespace):
    """A session's instance as far as these routes touch it: what the host keeps of its data, as the host keeps it - the
    files it is handed, or a list of its own where it is handed none."""
    def __init__(self, df=None, df_id=None, auxiliary_datasets=None, executor_api_url=None, **more):
        super().__init__(df=df, df_id=df_id, auxiliary_datasets=auxiliary_datasets or [], load_params=None, kill_signal=False, executor_api_url=executor_api_url)


def from_the_app(name, **names):
    """A function of web_app/app.py - a file the battery cannot load whole - as its own source has it, over stand-ins
    for the names it uses."""
    scope = dict(names)
    exec(compile(ast.Module(body=[n for n in APP.body if isinstance(n, ast.FunctionDef) and n.name == name], type_ignores=[]), "web_app/app.py", "exec"), scope)
    return scope[name]


# the session's instance: made, or made again where the container's address changed, by the web app's own factory
instance_of = from_the_app("get_bamboo_ai", user_preferences=SETTINGS, bamboo_ai_instances=INSTANCES, BambooAI=Host, get_user_id=lambda: "u1",
                           executor_base_url=lambda user_id: ADDRESS["now"], logger=quiet, SEARCH_TOOL=True, GLOBAL_EXECUTION_MODE="api",
                           cleanup_and_remove_bamboo_instance=lambda session_id, instances: (put_away.append(session_id), instances.pop(session_id, None)))


class Orchestrator:
    def restart_container(self, user_id, tier):
        restarts.append((user_id, tier))
        return {"status": "success", "message": "restarted"}


# what the web app hands the integrations, by the name each is handed under
THINGS = {"user_preferences": SETTINGS, "bamboo_ai_instances": INSTANCES, "get_user_id": lambda: "u1", "get_bamboo_ai": instance_of,
          "get_dynamic_executor_urls": lambda user_id: {"EXECUTOR_API_BASE_URL": ADDRESS["now"]}, "global_execution_mode": "api",
          "logger": quiet, "utils": utils, "executor_client": executor_client, "max_aux": 2,
          "cleanup_and_remove_bamboo_instance": lambda session_id: INSTANCES.pop(session_id, None), "container_orchestrator": Orchestrator(),
          "get_user_compute_tier": lambda user_id: "plus"}

# ------------------------------------------------------------------------------------------ the start
import container_status_routes as CS  # noqa: E402
from integrations import cache_manager as CM, endura as EN, intervals as IV, sweatstack as SW  # noqa: E402
STARTS = {"init_cache_integration": CM.init_cache_integration, "init_container_status_integration": CS.init_container_status_integration,
          "init_endura_integration": EN.init_endura_integration, "init_intervals_integration": IV.init_intervals_integration,
          "init_sweatstack_integration": SW.init_sweatstack_integration}
HANDS = {n.func.id: [k.arg for k in n.keywords] for n in ast.walk(APP)
         if isinstance(n, ast.Call) and isinstance(n.func, ast.Name) and re.fullmatch(r"init_\w+_integration", n.func.id)}
app = Flask("integrations"); app.secret_key = "the suite's"
started, refused = [], {}
for name in sorted(HANDS):
    try:
        STARTS[name](app, **{handed: THINGS[handed] for handed in HANDS[name]})
        started.append(name)
    except Exception as exc:                                   # noqa: BLE001 - a start that asks for what it was not handed raises a KeyError
        refused[name] = repr(exc)
routes = {str(rule) for rule in app.url_map.iter_rules()}
check("the start: each of the five integrations starts on what the web app's own call hands it - a start that reads a name it is not handed stops the app - "
      "and its routes are then on the app",
      started == sorted(STARTS) and {"/intervals/load_data", "/intervals/job/<job_id>", "/endura/load_data", "/sweatstack/load_data", "/cache/load_primary",
                                     "/cache/load_auxiliary", "/api/container/restart"} <= routes, (refused, sorted(set(STARTS) - set(HANDS))))


def page(session_id):
    """A page of a signed-in person: the app gives each a session."""
    client = app.test_client()
    with client.session_transaction() as s:
        s["session_id"] = session_id
    return client


def frame_of(answer):
    """The data's first page in a route's answer, as the Data tab reads it; None where the answer has none."""
    return json.loads((answer or {}).get("dataframe") or "null")


def shown(df_id=None):
    """The first page as the Data tab is to get it: the executor's page, under the frame's id where it is a frame's."""
    return {"type": "dataframe", "data": dict(PAGE, df_id=df_id) if df_id else PAGE}


def held(session_id):
    """What the session's instance holds of its data: the frame's id, the files, how the data was loaded."""
    inst = INSTANCES.get(session_id)
    return None if inst is None else (inst.df_id, list(inst.auxiliary_datasets or []), inst.load_params)


today = datetime.date.today()
WINDOW = {"start_date": (today - datetime.timedelta(days=20)).isoformat(), "end_date": (today - datetime.timedelta(days=6)).isoformat()}
NOTES = "datasets/u1/field_notes.csv"                           # a file the person attached
WELLNESS = "datasets/u1/intervals/i77001/views/wellness_data_20260901_to_20260930.csv"
SUMMARY = "datasets/u1/intervals/i77001/views/activity_summary_20260901_to_20260930.csv"
FIRST = {"source": "intervals", "id": "i77001", "name": "First Athlete", "folder": "intervals/i77001"}

with mock.patch.object(requests, "post", executor), mock.patch.object(requests, "get", executor), mock.patch.object(CS.time, "sleep"):
    # -------------------------------------------------------------------------------------- Intervals.icu
    SETTINGS["s1"] = {"auxiliary_datasets": [NOTES], "df_id": None}           # a session with a file attached and a question asked: its instance stands
    standing = instance_of("s1")
    ANSWERS["/fetch_intervals_data"] = {"job_id": "job-1"}
    r = page("s1").post("/intervals/load_data", json=dict(WINDOW, metrics=["power"], aux_datasets=["wellness"], athlete="i77001"))
    sent = sent_to("/fetch_intervals_data") or {}
    check("Intervals.icu, a load asked for: the executor is asked for the window under the athlete's own key, for this user, with the frame; the page is answered the "
          "job and the dates; the session's settings keep how the data was asked for - the source, the dates, the kinds, the frame's id, a mark of the key and never "
          "the key",
          r.status_code == 202 and r.get_json() == dict(WINDOW, note="", job_id="job-1") and sent.get("api_key") == "key-of-the-first" and sent.get("user_id") == "u1"
          and sent.get("with_frame") is True and sent.get("aux_datasets") == ["wellness"] and (sent.get("start_date"), sent.get("end_date")) == (WINDOW["start_date"], WINDOW["end_date"])
          and SETTINGS["s1"] == {"auxiliary_datasets": [NOTES], "df_id": None, "load": dict(WINDOW, source="intervals", metrics=["power"], aux_kinds=["wellness"], df_id=sent.get("df_id"),
                                                                                         key=key_fingerprint("key-of-the-first"))}
          and "key-of-the-first" not in json.dumps(SETTINGS["s1"]), (r.status_code, r.get_json(), SETTINGS["s1"]))

    ANSWERS["/intervals_job/job-1"] = {"status": "completed", "result": {"df_id": sent.get("df_id"), "aux_datasets": [WELLNESS], "kinds": ["wellness"], "subject": FIRST,
                                                                        "store": {"window": 14, "held": 10, "fetched": 4}}}
    r = page("s1").get("/intervals/job/job-1")
    check("...the job done: the settings take the frame's id, and the load's file beside the one the person attached; the instance that stood is given the same frame "
          "and files, and how the data was loaded - whose it is, what the store held of the window; the page is answered the frame's first page under its id",
          r.status_code == 200 and SETTINGS["s1"]["df_id"] == sent.get("df_id") and SETTINGS["s1"]["auxiliary_datasets"] == [NOTES, WELLNESS] and INSTANCES.get("s1") is standing
          and held("s1") == (sent.get("df_id"), [NOTES, WELLNESS], SETTINGS["s1"]["load"])
          and SETTINGS["s1"]["load"].get("subject") == {"source": "intervals", "id": "i77001", "name": "First Athlete"}
          and SETTINGS["s1"]["load"].get("store") == {"window": 14, "held": 10, "fetched": 4, "refresh": False, "offline": False}
          and frame_of(r.get_json()) == shown(sent.get("df_id")), (r.status_code, r.get_json(), SETTINGS["s1"], held("s1")))

    ANSWERS["/fetch_intervals_data"] = {"job_id": "job-2"}
    record = json.dumps(SETTINGS["s1"], sort_keys=True)
    r = page("s1").post("/intervals/load_data", json=dict(WINDOW, aux_datasets=["summary"], athlete="i77001", with_frame=False, from_store=True))
    alone = sent_to("/fetch_intervals_data") or {}
    asked_alone = r.status_code == 202 and alone.get("with_frame") is False and alone.get("from_store") is True and json.dumps(SETTINGS["s1"], sort_keys=True) == record
    ANSWERS["/intervals_job/job-2"] = {"status": "completed", "result": {"frame": False, "aux_datasets": [SUMMARY], "kinds": ["summary"], "subject": FIRST}}
    r = page("s1").get("/intervals/job/job-2")
    check("...one dataset alone, from the store: asked for without the frame, and the settings are left as they were until it is there; then its file joins the "
          "session's and the instance's, the frame stays, and the load's record names the kind it gained",
          asked_alone and r.status_code == 200 and SETTINGS["s1"]["auxiliary_datasets"] == [NOTES, WELLNESS, SUMMARY] and SETTINGS["s1"]["df_id"] == sent.get("df_id")
          and SETTINGS["s1"]["load"]["aux_kinds"] == ["wellness", "summary"] and held("s1") == (sent.get("df_id"), [NOTES, WELLNESS, SUMMARY], SETTINGS["s1"]["load"])
          and frame_of(r.get_json()) is None, (asked_alone, r.status_code, SETTINGS["s1"], held("s1")))

    n_asked = len(asked)
    r = page("s1").post("/intervals/load_data", json=dict(WINDOW, aux_datasets=[], athlete="i77002", athlete_name="Second Athlete"))
    gone = page("s1").get("/intervals/job/job-9")
    check("...refused: a load for an athlete without a key says whose key is missing and asks the executor nothing; a job the executor does not know is not found",
          r.status_code == 401 and "Second Athlete" in (r.get_json() or {}).get("error", "") and [p for p, _ in asked[n_asked:]] == ["/intervals_job/job-9"]
          and gone.status_code == 404 and gone.get_json() == {"status": "not_found"}, (r.status_code, r.get_json(), gone.status_code))

    ANSWERS["/fetch_intervals_data"] = {"job_id": "job-3"}
    r = page("s5").post("/intervals/load_data", json=dict(WINDOW, metrics=[], aux_datasets=[]))            # a session the app holds nothing for yet
    sent = sent_to("/fetch_intervals_data") or {}
    asked_new = r.status_code == 202 and SETTINGS.get("s5") == {"auxiliary_datasets": [], "load": dict(WINDOW, source="intervals", metrics=[], aux_kinds=[], df_id=sent.get("df_id"),
                                                                                                      key=key_fingerprint("key-of-the-first"))}
    ANSWERS["/intervals_job/job-3"] = {"status": "completed", "result": {"df_id": sent.get("df_id"), "aux_datasets": [], "kinds": [], "subject": FIRST}}
    r = page("s5").get("/intervals/job/job-3")
    check("...in a session the app holds nothing for yet: the load asked for makes its settings - no files, the load's record, nothing else - under the key last "
          "used where the page names no athlete; the job done, they take the frame's id and an instance is built on them",
          asked_new and r.status_code == 200 and sorted(SETTINGS["s5"]) == ["auxiliary_datasets", "df_id", "load"] and SETTINGS["s5"]["df_id"] == sent.get("df_id")
          and held("s5") == (sent.get("df_id"), [], SETTINGS["s5"]["load"]) and frame_of(r.get_json()) == shown(sent.get("df_id")), (asked_new, r.status_code, SETTINGS.get("s5"), held("s5")))

    # -------------------------------------------------------------------------------------- Endura
    def race_files(race):
        return [f"datasets/u1/endura/{race}/athlete_profiles_race_{race}.csv", f"datasets/u1/endura/{race}/race_climbs_race_{race}.csv"]

    races, stood = [], []
    for race, title in (("r9", "The spring race"), ("r10", "The autumn race")):                              # the first in a session the app holds nothing for yet
        ANSWERS["/endura/load_race_data"] = {"race_title": title, "aux_datasets": race_files(race)}
        r = page("s2").post("/endura/load_data", json={"race_id": race, "aux_datasets": ["climbs"]})
        sent = sent_to("/endura/load_race_data") or {}
        races.append(r.status_code == 200 and sent.get("api_key") == "key-of-the-races" and sent.get("race_id") == race and sent.get("aux_datasets") == ["profile", "climbs"]
                     and sent.get("user_id") == "u1" and SETTINGS.get("s2") == {"auxiliary_datasets": race_files(race), "df_id": sent.get("df_id")}
                     and held("s2") == (sent.get("df_id"), race_files(race), {"source": "endura", "race_id": race, "race_title": title, "aux_kinds": ["profile", "climbs"], "df_id": sent.get("df_id")})
                     and frame_of(r.get_json()) == shown(sent.get("df_id")))
        stood.append(INSTANCES.get("s2"))
    check("Endura, a race loaded: the executor is asked for the race under the stored key, the profile always among its kinds; the settings are the frame's id and "
          "the race's files and nothing else; the instance holds them and how the race was loaded; the page is answered the frame's first page - and a second race "
          "in the same session is given to the instance that stands", races == [True, True] and stood[0] is stood[1], (races, SETTINGS.get("s2"), held("s2")))

    # -------------------------------------------------------------------------------------- SweatStack
    ANSWERS["/fetch_sweatstack_data"] = {"message": "fetched"}
    sports, stood = [], []
    for sport in ("cycling", "running"):
        wanted = dict(WINDOW, sports=[sport], metrics=["power"], users=["the-first"])
        r = page("s3").post("/sweatstack/load_data", json=dict(wanted))
        sent, answer = sent_to("/fetch_sweatstack_data") or {}, r.get_json() or {}
        sports.append(r.status_code == 200 and sent.get("access_token") == "token-of-the-first" and sent.get("fetch_params") == wanted
                      and SETTINGS.get("s3") == {"auxiliary_datasets": [], "df_id": sent.get("df_id")} and held("s3") == (sent.get("df_id"), [], dict(wanted, source="sweatstack", df_id=sent.get("df_id")))
                      and answer.get("df_id") == sent.get("df_id") and frame_of(answer) == shown(sent.get("df_id"))
                      and answer.get("date_range") == {"start": WINDOW["start_date"], "end": WINDOW["end_date"], "auto_adjusted": False, "max_days_allowed": 182})
        stood.append(INSTANCES.get("s3"))
    check("SweatStack, a load: it goes by the executor, as the execution mode the web app hands this integration says; the executor is asked under the stored token "
          "for what the page asked; the settings are the frame's id; the instance holds how the data was loaded; the page is answered the frame's id, its first page "
          "and the dates the plan allows - and a second load in the same session is given to the instance that stands",
          sports == [True, True] and stood[0] is stood[1], (sports, SETTINGS.get("s3"), held("s3")))

    # -------------------------------------------------------------------------------------- the dataset cache
    frames, stood = [], []
    for frame in ("frame-9", "frame-10"):
        r = page("s4").post("/cache/load_primary", json={"df_id": frame})
        frames.append(r.status_code == 200 and SETTINGS.get("s4") == {"auxiliary_datasets": [], "df_id": frame} and held("s4") == (frame, [], {"source": "cache", "df_id": frame})
                      and (r.get_json() or {}).get("df_id") == frame and frame_of(r.get_json()) == shown(frame))
        stood.append(INSTANCES.get("s4"))
    check("the dataset cache, a frame loaded from it: the settings are that frame's id; the instance holds it and that it came from the cache; the page is answered "
          "its first page - and a second frame in the same session is given to the instance that stands", frames == [True, True] and stood[0] is stood[1],
          (frames, SETTINGS.get("s4"), held("s4")))
    first = page("s4").post("/cache/load_auxiliary", json={"file_path": "datasets/u1/plots.csv"})
    told = held("s4")
    INSTANCES["s4"].auxiliary_datasets = []                # an instance that has not got a file its session lists, as one was left before 0349
    again = page("s4").post("/cache/load_auxiliary", json={"file_path": "datasets/u1/plots.csv"})
    check("...a file loaded from it where the instance stands with a list of its own, as one built while the session had no files (0349: the file joined the "
          "session's files and the instance was not told of it, nor the analyst): the instance is given the session's files; and loaded again, the file is "
          "listed once and an instance that had not got it has it",
          first.status_code == 200 and SETTINGS["s4"]["auxiliary_datasets"] == ["datasets/u1/plots.csv"] and told == ("frame-10", ["datasets/u1/plots.csv"], {"source": "cache", "df_id": "frame-10"})
          and again.status_code == 200 and (again.get_json() or {}).get("aux_count") == 1 and held("s4") == told and INSTANCES["s4"] is stood[1],
          (first.status_code, again.status_code, SETTINGS.get("s4"), told, held("s4")))
    files = [page("s6").post("/cache/load_auxiliary", json={"file_path": path}) for path in ("datasets/u1/plots.csv", "datasets/u1/soil.csv", "datasets/u1/plots.csv", "datasets/u1/rain.csv")]
    check("...files loaded from it, into a session the app holds nothing for yet: each joins the session's files once and is answered its first page; a file past the "
          "limit the web app hands this integration is refused, and the session keeps the files it had - and nothing else",
          [f.status_code for f in files] == [200, 200, 200, 400] and [(f.get_json() or {}).get("aux_count") for f in files[:3]] == [1, 2, 2] and frame_of(files[0].get_json()) == shown()
          and "Maximum 2" in (files[3].get_json() or {}).get("error", "") and SETTINGS.get("s6") == {"auxiliary_datasets": ["datasets/u1/plots.csv", "datasets/u1/soil.csv"]},
          ([f.status_code for f in files], SETTINGS.get("s6")))

    # -------------------------------------------------------------------------------------- the container
    loaded = dict(SETTINGS["s1"])
    r = page("s1").post("/api/container/restart")
    check("the container restarted from the page: the orchestrator is asked to restart this user's container on their tier; the run in hand is told to stop; what "
          "lived in the container is forgotten - the session's files and its frame - and a fresh instance stands for the session",
          r.status_code == 200 and (r.get_json() or {}).get("status") == "success" and restarts == [("u1", "plus")] and standing.kill_signal is True and bool(loaded["df_id"])
          and len(loaded["auxiliary_datasets"]) == 3 and (SETTINGS["s1"]["auxiliary_datasets"], SETTINGS["s1"]["df_id"]) == ([], None) and INSTANCES.get("s1") is not standing
          and held("s1") == (None, [], None), (r.status_code, r.get_json(), SETTINGS["s1"], held("s1")))

    # -------------------------------------------------------------------------------------- the container back at another address
    off = page("s2").post("/endura/remove_data")           # the primary dataset taken off: the route deletes the frame's id from the settings
    stood = INSTANCES.get("s2"), INSTANCES.get("s3")
    ADDRESS["now"] = "http://executor.test:5002"           # the container was stopped for idleness and started again

    def asked_again(session_id):
        """The session's next question: the app makes its instance again, the container's address having changed."""
        try:
            return instance_of(session_id)
        except Exception as exc:                               # noqa: BLE001 - what the question would be answered with
            return exc

    built = [asked_again(session_id) for session_id in ("s2", "s3")]
    check("a session whose primary dataset was taken off, when the user's container comes back at another address (0349: the removal deletes the frame's id from "
          "the settings, the instance was built again by reading that id with no fallback, and every question of the session ended in an error until a new "
          "conversation): the instance that stood is put away and another built for the new address, with no frame and the files the session still lists; a "
          "session that has its frame is built with it",
          off.status_code == 200 and "df_id" not in SETTINGS["s2"] and all(isinstance(b, Host) for b in built) and put_away == ["s2", "s3"] and built[0] is not stood[0]
          and built[0].executor_api_url == ADDRESS["now"]
          and held("s2") == (None, race_files("r10"), None) and built[1] is not stood[1] and built[1].executor_api_url == ADDRESS["now"] and bool(SETTINGS["s3"]["df_id"])
          and held("s3") == (SETTINGS["s3"]["df_id"], [], None), (off.status_code, built, SETTINGS.get("s2"), held("s2"), held("s3")))

# ------------------------------------------------------------------------------------------ what a session's settings hold
kept = sorted({key for prefs in SETTINGS.values() for key in prefs})
check("a session's settings hold three things and no other, whichever way its data came: the files, the frame's id, and how the data was asked for (0347: two more "
      "keys were written into them by every one of these routes and read by none)", kept == ["auxiliary_datasets", "df_id", "load"] and len(SETTINGS) == 6, kept)

print(f"\n{len(passed)} passed, {len(failed)} failed")
sys.exit(1 if failed else 0)
