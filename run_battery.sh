#!/bin/bash
# The test battery: the analyst package and the app path, both over a real in-process kernel.
cd "$(dirname "$0")"
[ -d /home/data/bambooai-venv/bin ] && export PATH="/home/data/bambooai-venv/bin:$PATH"
rc=0
# the time limit needs GNU timeout: coreutils on Linux, gtimeout from Homebrew's coreutils on macOS;
# without either the suites run with no limit rather than not at all (2026-10-03)
if command -v timeout >/dev/null 2>&1; then T="timeout 600"; elif command -v gtimeout >/dev/null 2>&1; then T="gtimeout 600"; else T=""; echo "(no timeout command: the suites run without a time limit)"; fi
for t in tests/analyst/test_analyst.py tests/analyst/test_app_path.py tests/analyst/test_ollama_adapter.py tests/analyst/test_vllm_adapter.py tests/analyst/test_documents.py tests/analyst/test_documents_app.py tests/analyst/test_read.py tests/analyst/test_executor_kernel.py tests/analyst/test_js_refs.py tests/analyst/test_css_refs.py; do
  echo "##### SUITE $t"
  $T python3 "$t" || rc=1
done
echo "##### SUITE tests/analyst/test_pane.js"
if command -v node >/dev/null 2>&1; then node tests/analyst/test_pane.js || rc=1; echo "##### SUITE tests/analyst/test_grid.js"; node tests/analyst/test_grid.js || rc=1; echo "##### SUITE tests/analyst/test_dialogs.js"; node tests/analyst/test_dialogs.js || rc=1; echo "##### SUITE tests/analyst/test_shell.js"; node tests/analyst/test_shell.js || rc=1; echo "##### SUITE tests/analyst/test_documents_page.js"; node tests/analyst/test_documents_page.js || rc=1; else echo "(node not installed: the pane and grid suites skipped)"; fi
echo "##### BATTERY DONE rc=$rc"; exit $rc
