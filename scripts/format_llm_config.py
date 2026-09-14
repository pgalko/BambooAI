#!/usr/bin/env python3
"""Bump the Image Generator cap to 28000 and format an LLM_CONFIG for reading.

Usage:
    python3 scripts/format_llm_config.py [path ...]

Defaults to web_app/LLM_CONFIG.json when no path is given. For per-user
configs as well:

    python3 scripts/format_llm_config.py web_app/LLM_CONFIG.json config/*/LLM_CONFIG.json

What it does, per file:
  1. Sets max_tokens to 28000 on every "Image Generator" entry, wherever it
     sits (flat agent_configs or the template's tiered *_agent_configs).
  2. Rewrites the file so every agent config and every model property sits
     on ONE line - the at-a-glance format the template uses (821 lines of
     pretty-printing collapse to ~100).
  3. Verifies the rewrite is LOSSLESS before writing: the new text must parse
     back semantically identical to the loaded data (with only the intended
     cap change), or nothing is written.
  4. Keeps the original beside the file as <name>.bak, and preserves the
     file's existing line endings.

Safe to run twice: already-bumped, already-formatted files come out byte-
identical (minus a fresh .bak).
"""

import json
import shutil
import sys


def bump_image_generator(data):
    changed = 0

    def walk(o):
        nonlocal changed
        if isinstance(o, dict):
            if o.get("agent") == "Image Generator" and isinstance(o.get("details"), dict):
                if o["details"].get("max_tokens") != 28000:
                    o["details"]["max_tokens"] = 28000
                    changed += 1
            for v in o.values():
                walk(v)
        elif isinstance(o, list):
            for v in o:
                walk(v)

    walk(data)
    return changed


def compact(o):
    return json.dumps(o, separators=(", ", ": "), ensure_ascii=False)


def render(data):
    """One line per agent config and per model property; commas by join."""
    sections = []
    for k, v in data.items():
        if k == "model_properties" and isinstance(v, dict):
            inner = ",\n".join(f'    "{name}": {compact(props)}'
                               for name, props in v.items())
            sections.append(f'  "{k}": {{\n{inner}\n  }}')
        elif isinstance(v, list) and v and isinstance(v[0], dict) and "agent" in v[0]:
            inner = ",\n".join(f'    {compact(entry)}' for entry in v)
            sections.append(f'  "{k}": [\n{inner}\n  ]')
        else:
            body = json.dumps(v, indent=2, ensure_ascii=False)
            body = "\n".join(("  " + l) if i else l
                             for i, l in enumerate(body.split("\n")))
            sections.append(f'  "{k}": {body}')
    return "{\n" + ",\n".join(sections) + "\n}\n"


def process(path):
    raw = open(path, newline="").read()
    had_crlf = "\r\n" in raw
    data = json.loads(raw)

    bumped = bump_image_generator(data)
    out = render(data)

    # Validate BEFORE touching the file: lossless modulo the intended bump.
    if json.loads(out) != data:
        raise SystemExit(f"{path}: rewrite would not be lossless; aborting "
                         f"with the file untouched.")
    if had_crlf:
        out = out.replace("\n", "\r\n")

    shutil.copy2(path, path + ".bak")
    open(path, "w", newline="").write(out)

    nl = "\r\n" if had_crlf else "\n"
    print(f"{path}: Image Generator caps set to 28000 on {bumped} entr"
          f"{'y' if bumped == 1 else 'ies'} (0 means already 28000); "
          f"{raw.count(chr(10))} lines -> {out.count(nl)}; "
          f"backup at {path}.bak")


if __name__ == "__main__":
    paths = sys.argv[1:] or ["web_app/LLM_CONFIG.json"]
    for p in paths:
        process(p)
