#!/bin/bash
# The test battery: the analyst package and the app path, both over a real in-process kernel.
cd "$(dirname "$0")"
[ -d /home/data/bambooai-venv/bin ] && export PATH="/home/data/bambooai-venv/bin:$PATH"
rc=0
for t in tests/analyst/test_analyst.py tests/analyst/test_app_path.py tests/analyst/test_js_refs.py tests/analyst/test_css_refs.py; do
  echo "##### SUITE $t"
  timeout 600 python3 "$t" || rc=1
done
echo "##### SUITE tests/analyst/test_pane.js"
if command -v node >/dev/null 2>&1; then node tests/analyst/test_pane.js || rc=1; echo "##### SUITE tests/analyst/test_grid.js"; node tests/analyst/test_grid.js || rc=1; echo "##### SUITE tests/analyst/test_dialogs.js"; node tests/analyst/test_dialogs.js || rc=1; echo "##### SUITE tests/analyst/test_shell.js"; node tests/analyst/test_shell.js || rc=1; else echo "(node not installed: the pane and grid suites skipped)"; fi
echo "##### BATTERY DONE rc=$rc"; exit $rc
