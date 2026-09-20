#!/usr/bin/env bash
set -euo pipefail
cd -- "$(dirname -- "${BASH_SOURCE[0]}")"
package_python="${LAB_PYTHON:-$PWD/.venv/bin/python}"
if [ ! -x "$package_python" ]; then echo 'Environment missing. Read README.md and run bash setup.sh cpu (or cuda).'; exit 2; fi
export PYTHONDONTWRITEBYTECODE=1
exec "$package_python" tools/run_server.py
