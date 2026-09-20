#!/usr/bin/env bash
set -euo pipefail
cd -- "$(dirname -- "${BASH_SOURCE[0]}")"
profile="${1:-cpu}"
case "$profile" in cpu|cuda) ;; *) echo 'Usage: bash setup.sh cpu|cuda'; exit 2;; esac
if [ -d .venv ]; then
  echo 'Existing .venv found: do not mix CPU/GPU packages. Inspect it or choose a fresh copy of this package.'
  exit 2
fi
"${PYTHON_BIN:-python3}" -m venv .venv
.venv/bin/python -m pip install --upgrade pip
.venv/bin/python -m pip install -r "requirements-$profile.txt"
.venv/bin/python tools/check_environment.py
