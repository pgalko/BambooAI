#!/usr/bin/env python3
"""A question put to a user's saved analyses, from the command line (docs/ARCHITECT_DESIGN.md §3.6): the reader works
through the view in a sandbox, with the user's own models, and what it returns is shown with every step it took -
then what plain keyword search gives for the same words, to compare. Run it from the web app's folder, as the app's
user: it takes the app's environment and the user's model configuration, and its model calls are logged as the
user's.

    python3 ../tools/memory_ask.py --user 4f2a "How did I take the threshold in earlier analyses?"
    python3 ../tools/memory_ask.py --user 4f2a --seconds 300 --dollars 1 --turns 12 "..."      # other limits than the engine's
    python3 ../tools/memory_ask.py --user 4f2a --effort medium "..."                           # the reader's replies at another effort
    python3 ../tools/memory_ask.py --user 4f2a --quiet "..."                                   # the result alone

The sandbox is the user's executor, as in the app: the one EXECUTOR_API_BASE_URL names, or the user's container from
the orchestrator; with EXECUTION_MODE=local, a kernel on this machine. On an executor the reader's kernel takes the
place of the user's analysis kernel, so do not run it beside an analysis of the same user.
"""
import argparse
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ENV_FILES = ("/etc/bambooai/system.env", "/etc/bambooai/shared.env", "/etc/bambooai/webapp-secrets.env", "/etc/bambooai/webapp.env")


def environment(files=ENV_FILES):
    """The app's environment: on a hosted box the files its gunicorn loads, in that order (web_app/
    webapp_gunicorn.conf.py), then the .env in the app's folder or the nearest above it, as web_app/app.py finds
    it. The working folder is the app's by now."""
    from dotenv import find_dotenv, load_dotenv
    for path in files:
        try:
            load_dotenv(path)
        except PermissionError:
            sys.exit(f"{path} cannot be read by this user. Run it as the app's user.")
    load_dotenv(find_dotenv(usecwd=True))


def compute(user, env=os.environ, orchestrator=None):
    """Where the user's code runs, as the app decides it (web_app/app.py get_dynamic_executor_urls): ('local', None),
    or ('api', the executor's address) - the one the environment names, else the user's container."""
    if env.get("EXECUTION_MODE", "api") == "local":
        return "local", None
    direct = (env.get("EXECUTOR_API_BASE_URL") or "").rstrip("/")
    if direct:
        return "api", direct
    if orchestrator is None:
        from auth.supabase_client import get_user_compute_tier
        from orchestration.main_app_integration import ContainerOrchestrator
        orchestrator = lambda who: ContainerOrchestrator(env.get("ORCHESTRATOR_API_URL", "http://localhost:8080")).get_or_create_container(who, get_user_compute_tier(who))      # noqa: E731
    box = orchestrator(user)
    if box.get("status") != "ready":
        sys.exit(f"The user's executor is not ready: {box.get('status') or box}")
    return "api", f"http://{box['ip']}:{box['port']}"


def step_lines(k, step):
    """One step of the reader's, as it is printed."""
    if step["action"] == "cell":
        return [f"[{k}] CELL", *("    " + ln for ln in step["code"].splitlines()), "  printed:", *("    " + ln for ln in (step["out"] or "(nothing)").splitlines())]
    if step["action"] == "judge":
        asked = step["asked"]
        facts = [f"asked about: {'all' if asked['runs'] == 'all' else step['runs']}", f"parts: {', '.join(asked['parts'])}", f"read: {len(step['read'])} of {step['runs']}",
                 *([f"dropped: {step['dropped']}"] if step["dropped"] else []), *([f"not saved analyses: {', '.join(step['unknown'])}"] if step["unknown"] else [])]
        return [f"[{k}] JUDGE {asked['question']!r}", "  " + " · ".join(facts), *(f"    {row['run']} | {row['where']} | {row['answer']} | \"{row['quote']}\"" for row in step["rows"])]
    return [f"[{k}] ANSWER"] if step["action"] == "answer" else [f"[{k}] a reply that could not be read: {step['problem']}"]


def result_lines(res):
    """What the reader returned, as it is printed: the passages; the finding across the analyses - under each group's
    label, which is the reader's, every run with the second model's own answer and quote; what was read, what did
    not stand, and what it took."""
    out = []
    if res["failed"]:
        out.append(f"No answer: {res['failed']}")
    for f in res["found"]:
        marks = f" ({', '.join(f['marks'])})" if f["marks"] else ""
        out += [f"{f['when'][:10]}  {f['question'] or 'Synthesis: ' + f['title']}{marks}  [{f['id']}]" + ("  - its chain is broken" if f.get("broken") else ""),
                f"    {f['where']}: \"{f['quote']}\"", *([f"    {f['note']}"] if f["note"] else [])]
    if res["across"]:
        out.append(f"Across the analyses - {res['across']['topic']}:")
        for group in res["across"]["groups"]:
            out.append(f"  {len(group['runs'])} × {group['label']}")
            out += [f"    [{row['run']}] {row['answer']} · {row['where']}: \"{row['quote']}\"" for row in group["runs"]]
    if not res["found"] and not res["across"] and not res["failed"]:
        out.append("Nothing in the saved analyses bears on it.")
    cover, words = res["coverage"], (("older", "in the old record format"), ("questions", "of questions only"), ("no_report", "without a report"), ("left", "left for another branch"))
    left = ", ".join(f"{cover['not_read'][key]} {what}" for key, what in words if cover["not_read"].get(key))
    out += ["", f"runs in memory: {cover['runs']} · read by the second model: {cover['judged']}" + (f" · not read: {left}" if left else ""),
            *([f"dropped, it did not stand in the record: {res['dropped']}"] if res["dropped"] else []),
            f"the reader's replies: {res['calls']['reader']} · the second model's calls: {res['calls']['pieces']} · ${res['cost']:.2f} · {res['seconds']:.0f} s"]
    return out


def main(argv=None, host=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--root", default=".", help="the web app's folder: where storage/, config/ and .env are (default: the working folder, or its web_app/)")
    ap.add_argument("--user", required=True, help="the user's id, or how it begins")
    ap.add_argument("--turns", type=int, help="the reader's replies at most (default: the engine's, as for the next two)")
    ap.add_argument("--seconds", type=int, help="the time of both models at most")
    ap.add_argument("--dollars", type=float, help="the money of both models at most")
    ap.add_argument("--effort", help="the effort the reader's replies are asked at: low, medium, high - never above the seat's own")
    ap.add_argument("--quiet", action="store_true", help="the result alone, without the steps")
    ap.add_argument("question")
    args = ap.parse_args(argv)
    root = next((r for r in (args.root, os.path.join(args.root, "web_app")) if os.path.isdir(os.path.join(r, "storage"))), None)
    if root is None:
        sys.exit(f"No storage/ under {os.path.abspath(args.root)}. Give --root.")
    os.chdir(root)
    sys.path[:0] = [os.getcwd(), ROOT]
    users = sorted(u for u in os.listdir("storage") if os.path.isdir(os.path.join("storage", u, "favourites")) and u.startswith(args.user))
    if len(users) != 1:
        sys.exit(f"{len(users)} users with saved work begin with {args.user!r}.")
    if hasattr(os, "getuid") and os.getuid() != os.stat("storage").st_uid:      # it writes the run log and the kept view, as the app does: files of another owner would lock the app out
        import pwd
        sys.exit(f"Run it as the app's user, {pwd.getpwuid(os.stat('storage').st_uid).pw_name}: it writes where the app writes.")
    if host is None:
        environment()
        mode, url = compute(users[0])
        from bambooai import BambooAI
        host = BambooAI(user_id=users[0], execution_mode=mode, executor_api_url=url)
    from analyst import memory
    count = []
    shown = None if args.quiet else lambda step: print("\n".join(step_lines(count.append(1) or len(count), step)), flush=True)
    print(f"user {users[0]}\n{args.question}\n", flush=True)
    caps = {name: value for name, value in (("turns", args.turns), ("seconds", args.seconds), ("dollars", args.dollars), ("effort", (args.effort,) if args.effort else None)) if value}
    res = host.memory_read(args.question, on_step=shown, caps=caps or None)
    print(("" if args.quiet else "\n") + "\n".join(result_lines(res)))
    hits = memory.search(memory.view(os.path.join("storage", users[0])), args.question, most=5)
    print("\nPlain keyword search, the same words:" + ("" if hits else " nothing."))
    for hit in hits:
        print(f"{hit['when'][:10]}  {hit['question'] or 'Synthesis: ' + hit['title']}  [{hit['id']}]")
        print("\n".join(f"    {p['where']}: {p['text']}" for p in hit["passages"][:1]))


if __name__ == "__main__":
    main()
