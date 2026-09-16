<p align="center">
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="https://raw.githubusercontent.com/pgalko/BambooAI/main/web_app/static/image/logo_dark.svg">
    <img src="https://raw.githubusercontent.com/pgalko/BambooAI/main/web_app/static/image/logo_light.svg" alt="BambooAI" width="320">
  </picture>
</p>

<p align="center">
  <a href="https://pypi.org/project/bambooai/"><img alt="PyPI" src="https://img.shields.io/pypi/v/bambooai"></a>
  <a href="https://github.com/pgalko/BambooAI/actions/workflows/ci.yml"><img alt="ci" src="https://github.com/pgalko/BambooAI/actions/workflows/ci.yml/badge.svg"></a>
  <a href="LICENSE"><img alt="MIT" src="https://img.shields.io/badge/license-MIT-green"></a>
</p>

BambooAI is an LLM-driven data analyst. Given a dataset and a question, one model works in a
persistent Python kernel, one cell at a time: it writes code, reads the output, decides the next
step, and finishes with a report. Before the report is shown, the cells it cites are re-executed in a
fresh kernel and the numbers compared. The web app streams the run, keeps the notebook, and lets you
ask follow-up questions against the same kernel state.

It runs on your machine with your own model keys. The model-written code runs in a Docker container,
not under your account.

<p align="center">
  <img src="https://raw.githubusercontent.com/pgalko/BambooAI/main/docs/images/bambooai_app.jpg" alt="An Adaptive run: cells and turns on the left, the report's figures on the right" width="960">
</p>

## What a run is

Each turn the analyst takes exactly one action:

| action | effect |
|---|---|
| `CELL` | run one Python cell in the kernel; the printed output comes back as the next turn's input |
| `SHOW n` | re-open the full output of an earlier cell (outputs are truncated in the working context) |
| `NAMES` | list the variables the kernel currently holds |
| `RECALL` | look up the memory pack: what earlier runs learned about this dataset |
| `SEARCH` | a web search with Google AI grounding, summarised and cited (needs `GEMINI_API_KEY`) |
| `ASK` | put one question to the person and wait |
| `REPORT` | write the report; the run ends |

The report has a fixed shape: a best estimate with its uncertainty, the conditions it holds under, how
it was established, and the cells and figures it rests on. After `REPORT`, the cited cells are
assembled into a script and executed in a fresh kernel against the original data; the closing card
states whether the cited numbers reproduced. A second, cheaper model writes a plain-language version
of the same report.

Three modes set the turn budget; the budgets and the review cadence are per preset
(`tier_properties` in the config). At the `performance` preset:

- **Quick** — 4 turns, for a lookup or a definition.
- **Deep** — 15 turns.
- **Adaptive** — up to 50 turns; every 8th turn is a self-review, run on the `Reviewer` seat (a
  stronger model), which can redirect the analysis.

A follow-up question runs in the same kernel with the same variables ("warm kernel"); a new question
starts a fresh one. Saving a run distils what was learned about the dataset into a memory pack
(`memory/<user>/memory_pack.yaml`) that `RECALL` reads in later runs.

## Install

Requirements: Python ≥ 3.11 and Docker (Desktop on macOS/Windows, Engine on Linux), running.

```bash
pip install bambooai
bambooai serve
```

On first use `serve` creates the working folder, writes a `.env`, builds the executor image from the
Dockerfile in the package (several minutes: the image installs pandas, numpy, scipy, statsmodels,
scikit-learn, matplotlib, plotly and the rest), starts the container on `127.0.0.1:5055`, and opens
the browser at `127.0.0.1:5001`. Add at least one model key to `.env` and start again.

```
bambooai serve [--home DIR] [--port N] [--host H] [--compute docker|local] [--keep-executor] [--no-browser]
bambooai init  [--home DIR]      create the working folder without starting
bambooai where                   print the working folder
```

The working folder (`~/bambooai`, or `BAMBOO_HOME`):

```
.env                        keys and settings; read at start, never written by the app
LLM_CONFIG_template.json    the seats: model, provider, reasoning effort, max_tokens, price per seat and preset
bambooai.sqlite             chains, labels, usage, the saved preset, integration credentials (encrypted)
config/<user>/              the resolved config built from the template
storage/<user>/threads/     one JSON per thread: runs, cells, reports, replay results
storage/<user>/favourites/  saved chains
memory/<user>/              the memory pack
logs/<user>/                bambooai_run_log.json: every model call with tokens, time, cost
```

`serve` does not read anything outside this folder. Upgrading the package does not touch it.

### `.env`

| variable | meaning |
|---|---|
| `OPENROUTER_API_KEY`, `OPENAI_API_KEY`, `ANTHROPIC_API_KEY`, `GEMINI_API_KEY`, `GROQ_API_KEY`, `XAI_API_KEY`, `MISTRAL_API_KEY` | provider keys; only those you use |
| `REMOTE_OLLAMA`, `REMOTE_VLLM` | base URLs of local model servers |
| `BAMBOO_LEVEL` | `cost` / `performance` / `max`: the preset used before one is saved in the app |
| `BAMBOO_COMPUTE` | `docker` (default) or `local` |
| `EXECUTOR_PORT` | the container's published port (5055) |
| `EXECUTION_MODE`, `EXECUTOR_API_BASE_URL` | set both to use an executor you run yourself; `BAMBOO_COMPUTE` is then ignored |
| `BAMBOO_USER` | the identity that names the per-user folders (`local`) |
| `SWEATSTACK_CLIENT_ID`, `SWEATSTACK_CLIENT_SECRET` | your own SweatStack app registration; without them the integration is not offered |
| `APP_PORT`, `SESSION_COOKIE_NAME`, `FLASK_SECRET`, `LLM_CONFIG_ENCRYPTION_KEY` | the server; the last two are generated on first use |

Web search is enabled when `GEMINI_API_KEY` is present.

## Models

`LLM_CONFIG_template.json` defines seven seats — `Analyst`, `Reviewer`, `Rewriter`, `Knowledge
Distiller`, `Google Search Executor`, `Google Search Summarizer`, `Image Generator` — for each of three
presets. A seat is a provider, a model, a reasoning effort (`none` … `xhigh`, mapped per provider) and
`max_tokens`. `model_properties` holds the prices used for the running cost display. Edit the file in
the working folder; the app rebuilds its config when the file is newer than the built one.

Providers: OpenRouter, OpenAI, Anthropic, Google, Groq, Mistral, xAI, DeepSeek, Ollama, vLLM. With
Ollama or vLLM seats and no search key, no request leaves the machine.

## Data

Primary dataset: CSV, Parquet, JSON or XLSX, loaded into the kernel as `df`. Auxiliary datasets are
uploaded alongside and readable by path from the cell code. Integrations load training data from
Intervals.icu and Endura (API key entered in the app, stored encrypted) and SweatStack (OAuth, your
own app registration). Loaded frames are paged in the Data tab.

## Architecture

```
browser  ──HTTP/SSE──  web_app (Flask)  ──HTTP──  executor container (Flask + persistent kernel)
                          │                          runs the cells, the replay, the integrations' fetches
                          ├── analyst/   the turn loop, the contract, the report, the replay
                          ├── bambooai/  model adapters, log manager, config builder, local_store (SQLite)
                          └── delve/     the persistent kernel: checkpoints and rollback per cell
```

- `analyst/contract.md` is the whole prompt: one page, the same for every model.
- `delve/kernel.py` runs cells in a subprocess with a checkpoint per committed cell; a failed cell is
  rolled back so the namespace is exactly as before the attempt.
- The executor image (`containers/executor/`) is the analysis environment. `bambooai serve` builds it
  locally, tags it with the package version, and rebuilds when the version changes. The web app
  talks to it over HTTP; the app itself runs on `127.0.0.1`.
- `--compute local` runs the kernel in a subprocess of the app instead. No isolation; the
  integrations, which fetch inside the executor, are unavailable in this mode.
- Accounts and usage go through `bambooai/db/local_store.py`, a SQLite client with the same query
  interface the hosted edition uses against Supabase, so the routes above it are shared.

## Development

```bash
git clone https://github.com/pgalko/BambooAI.git && cd BambooAI
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]" && python -m playwright install chromium

./run_battery.sh                                                  # unit suites: analyst, kernel, notebook, report, replay
python tests/e2e/test_stack.py --edition local --compute local    # the real app + page + kernel; a scripted model, no network
python tests/e2e/test_stack.py --edition local --compute direct   # the same against an executor process
python tests/e2e/test_local_store.py                              # the store survives a server restart
python tests/e2e/test_package.py                                  # the wheel in a fresh virtualenv, serve with a docker stand-in
```

`tools/stack/` starts the app, an executor and stand-ins for the external services with a scripted
analyst (`tools/stack/scenarios/`), so the whole product can be driven end to end offline.
`tools/render_gallery.py` renders the page states for visual comparison. CI runs all of it on every
push (`.github/workflows/ci.yml`).

Design notes: `docs/DESIGN_CHECKLIST.md` (what every change must keep true), `docs/OSS_DESIGN.md`
(the decisions behind this edition). Issues and pull requests are welcome.

## Licence

MIT.

---

<sub>BambooAI 1.x was a Python library used from notebooks (<code>from bambooai import BambooAI</code>). Version 2 replaces it.
The 1.x releases remain installable with <code>pip install "bambooai&lt;2"</code>; the source is on the
<a href="https://github.com/pgalko/BambooAI/tree/v1">v1 branch</a>.</sub>
