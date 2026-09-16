# BambooAI

An LLM-driven data analyst that works in a persistent Python kernel, one cell at a time, and
reproduces its own results before it reports them. Give it a dataset and a question; it writes and
runs code, reads the output, decides the next step, and ends with a report whose cited numbers have
been re-executed in a fresh kernel. It runs on your machine with your own model keys; the code the
model writes runs in a Docker container, not under your account.

```
pip install bambooai
bambooai serve
```

Requirements: Python 3.11 or newer, and Docker running. The first `serve` creates `~/bambooai`,
writes a `.env` there, builds the executor image and opens the browser. Put a model key in the `.env`
(an OpenRouter key covers the default configuration) and start again.

Documentation, configuration and the source: https://github.com/pgalko/BambooAI

Hosted version: https://bambooai.org

BambooAI 1.x was a notebook library; it remains installable as `bambooai<2`.
