#!/usr/bin/env bash
set -euo pipefail
task_root=$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)
task_venv=$(mktemp -d "${TMPDIR:-/tmp}/pa07-python.XXXXXX")
trap 'rm -rf "$task_venv"' EXIT
python3 -m venv "$task_venv"
"$task_venv/bin/python" -m pip --isolated install --disable-pip-version-check \
  --no-cache-dir --only-binary=:all: --require-hashes --index-url https://pypi.org/simple \
  -r "$task_root/tools/metrics-simulator/requirements.txt"
export PATH="$task_venv/bin:$task_root/tools/metrics-simulator/bin:$PATH"
export PYTHONPYCACHEPREFIX="$task_venv/pycache"
cd "$task_root"
python -m unittest discover -s tests -v
if [[ "${1:-}" == "--live" ]]; then
  python -u tools/metrics-simulator/check_live.py --scrape-drill
fi
