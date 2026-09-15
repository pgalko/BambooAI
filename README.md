# BambooAI

**BambooAI 2.0 is a different program from the 1.x library.** 1.x was a Python module you called from
a notebook (`from bambooai import BambooAI`); it remains on PyPI as `bambooai<2` and in this repository
on the `v1` branch. 2.0 is an analyst that works in a notebook of its own - one model, one kernel, one
report, with a reproduction run behind every number it quotes - and a web app to work with it, running
on your own machine with your own model keys.

## Install

You need Python 3.11 or newer and **Docker** (Docker Desktop on a Mac or Windows, Docker Engine on
Linux), running. Then:

    pip install bambooai
    bambooai serve

The first `serve` creates a working folder (`~/bambooai`), writes a `.env` there, builds the executor
image - a few minutes, once - starts it, and opens the browser. Put a model key in the `.env` (an
OpenRouter key is the simplest: every model in the default configuration is reachable through it),
restart, and upload a dataset.

Everything the app keeps - notebooks, saved chains, the memory pack, usage - lives in that folder.
The code is never written to. `BAMBOO_HOME` moves the folder; `bambooai init` creates it without
starting the server.

## What runs where

- The analysis - the code the model writes - runs in the **executor container**, the same image the
  hosted service uses, built on your machine from the Dockerfile the package ships. It is started with
  `serve`, published on localhost only, and stopped when `serve` stops (`--keep-executor` keeps it).
  Nothing the model writes runs under your own account.
- Without Docker: `bambooai serve --compute local` runs the kernel in a subprocess on your machine.
  No isolation, and the Intervals, Endura and SweatStack integrations are not available that way.
- Models are called through the provider keys in `.env`; `REMOTE_OLLAMA` or `REMOTE_VLLM` point at a
  local model server if you run one, and then nothing leaves the machine.
- Web search (Google AI grounding) is on only when `GEMINI_API_KEY` is set.
- Windows: the app is plain Python and the analysis runs in the container, so Docker Desktop is the
  whole requirement; the `--compute local` fallback has not been tried there.

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
