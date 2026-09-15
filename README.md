# BambooAI

**BambooAI 2.0 is a different program from the 1.x library.** 1.x was a Python module you called from
a notebook (`from bambooai import BambooAI`); it remains on PyPI as `bambooai<2` and in this repository
on the `v1` branch. 2.0 is an analyst that works in a notebook of its own - one model, one kernel, one
report, with a reproduction run behind every number it quotes - and a web app to work with it, running
on your own machine with your own model keys.

## Install

    pip install bambooai
    bambooai serve

The first `serve` creates a working folder (`~/bambooai`), writes a `.env` there and opens the browser.
Put a model key in the `.env` (an OpenRouter key is the simplest: every model in the default
configuration is reachable through it), restart, and upload a dataset.

Everything the app keeps - notebooks, saved chains, the memory pack, usage - lives in that folder.
The code is never written to. `BAMBOO_HOME` moves the folder; `bambooai init` creates it without
starting the server.

## What runs where

- The analysis runs in a **kernel on your machine** (a subprocess), the default. For isolation, run
  the executor image in Docker (`docker run -p 5055:5000 <image>`) and set `EXECUTION_MODE=api` with
  `EXECUTOR_API_BASE_URL=http://localhost:5055` in `.env`.
- Models are called through the provider keys in `.env`; `REMOTE_OLLAMA` or `REMOTE_VLLM` point at a
  local model server if you run one, and then nothing leaves the machine.
- Web search (Google AI grounding) is on only when `GEMINI_API_KEY` is set.

## The levels

`BAMBOO_LEVEL` - `cost`, `performance` or `max` - picks a preset from `LLM_CONFIG_template.json` in the
working folder: which model is the analyst, which reviews its work in long runs, which writes the
plain-language version, at what reasoning effort. The account dialog saves your later choice; the
template file is yours to edit, prices included.

## Developing

    git clone https://github.com/pgalko/BambooAI.git && cd BambooAI
    python3 -m venv .venv && source .venv/bin/activate
    pip install -e ".[dev]" && playwright install chromium
    ./run_battery.sh                                   # the unit suites
    python3 tests/e2e/test_stack.py --edition local --compute local   # the real app, page and kernel, no network

The design notes are in `docs/`; `docs/OSS_DESIGN.md` records the decisions behind the self-hosted
edition. MIT licence.
