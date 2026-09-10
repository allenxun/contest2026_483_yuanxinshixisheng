#!/usr/bin/env bash
# 运行 Python Worker 测试：确保 .venv 存在后执行 pytest + 连通自检。
# 集成自检走 MVP_A_PG_DSN（默认隔离容器 mvp-a-pg）。
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
WORKER="$(cd "$SCRIPT_DIR/../../worker-python" && pwd)"
"$SCRIPT_DIR/pg-up.sh" >/dev/null
if [[ ! -x "$WORKER/.venv/bin/python" ]]; then
  python3 -m venv "$WORKER/.venv"
  "$WORKER/.venv/bin/pip" install -q --upgrade pip
  "$WORKER/.venv/bin/pip" install -q -e "$WORKER[dev]"
fi
cd "$WORKER"
.venv/bin/python -m pytest -q
.venv/bin/python -m mvp_worker --check
