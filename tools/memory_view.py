#!/usr/bin/env python3
"""The memory view from the command line (docs/ARCHITECT_DESIGN.md §3.5): what each user has saved and what of it is
memory, one user's runs in memory, and plain keyword search over them. It reads the storage the app keeps and builds
the view as the app does; it writes nothing, and says whether the view the app keeps shows the same.

    python3 tools/memory_view.py                           # every user with saved work
    python3 tools/memory_view.py --user 4f2a               # one user's runs in memory, the newest first (the id, or how it begins)
    python3 tools/memory_view.py --user 4f2a drift block   # the runs that hold these words, the best first
    python3 tools/memory_view.py --root /path/to/web_app   # where storage/ is, when not the working folder or its web_app/
"""
import argparse
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from analyst import memory  # noqa: E402

NOT_READ = (("older", "in the old record format"), ("questions", "of questions only"), ("no_report", "without a report"))
count = lambda n, what: f"{n} {what}{'' if n == 1 else 's'}"          # noqa: E731


def counts(storage):
    """What a user has saved and what of it is memory, in lines; and the view."""
    saved = memory._saved(storage)
    view, kept = memory.refresh(storage, keep=False), memory.view(storage)
    left = ", ".join(f"{view['not_read'][key]} {words}" for key, words in NOT_READ if view["not_read"].get(key))
    state = ("not built yet" if kept["built"] is None
             else time.strftime("built %Y-%m-%d %H:%M UTC", time.gmtime(kept["built"])) + (", up to date" if kept == view else ", behind what is saved now"))
    return [f"saved: {count(len(saved), 'workflow')}, {count(sum(len(c) for c in saved.values()), 'run')}",
            f"in memory: {count(len(view['runs']), 'run')} of {count(len({r['thread'] for r in view['runs']}), 'workflow')}" + (f" · not read: {left}" if left else ""),
            f"the view the app keeps: {state}"], view


def line(run):
    """A run in one line: the day, what was asked (a synthesis: what it found), its marks, its id."""
    marks = f"  ({', '.join(run['marks'])})" if run["marks"] else ""
    return f"{run['when'][:10]}  {run['question'] or 'Synthesis: ' + run['title']}{marks}  [{run['id']}]"


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--root", default=".", help="the folder that holds storage/ (default: the working folder, or its web_app/)")
    ap.add_argument("--user", default="", help="a user's id, or how it begins")
    ap.add_argument("--most", type=int, default=memory.MOST, help="the hits a search shows")
    ap.add_argument("words", nargs="*", help="words to find in the user's memory")
    args = ap.parse_args()
    root = next((r for r in (os.path.join(args.root, "storage"), os.path.join(args.root, "web_app", "storage")) if os.path.isdir(r)), None)
    if root is None:
        sys.exit(f"No storage/ under {os.path.abspath(args.root)}. Give --root.")
    users = sorted(u for u in os.listdir(root) if os.path.isdir(os.path.join(root, u, "favourites")) and u.startswith(args.user))
    if args.user and len(users) != 1:
        sys.exit(f"{len(users)} users with saved work begin with {args.user!r}.")
    if args.words and not args.user:
        sys.exit("A search needs --user.")
    for user in users:
        lines, view = counts(os.path.join(root, user))
        print(f"user {user}\n  " + "\n  ".join(lines))
        if args.words:
            hits = memory.search(view, " ".join(args.words), most=args.most)
            print(f"\n{len(hits)} of {count(len(view['runs']), 'run')} hold {' '.join(args.words)!r}" + (":" if hits else "."))
            for k, hit in enumerate(hits, 1):
                print(f"\n{k}. {line(hit)}  score {hit['score']}")
                for p in hit["passages"]:
                    print(f"   {p['where']}: {p['text']}")
        elif args.user:
            print()
            for run in view["runs"]:
                print(line(run))
    if not users:
        print("No user has saved work.")


if __name__ == "__main__":
    main()
