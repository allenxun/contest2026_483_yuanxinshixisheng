#!/usr/bin/env bash
# E 黑盒验收一键入口：setup-venv | selfcheck | matrix
# 退出码：setup/selfcheck 0=成功 1=失败；
# matrix：0=94 场景全部真实通过（证据齐） 1=有失败 3=存在 dependency_pending
#         4=结算不完整（场景缺失/未收集/被 deselect/重复/普通 skipped——插件层守卫，
#         PYTEST_ADDOPTS/--ignore 无法绕过，见 framework/conftest.py）。
set -u
cd "$(dirname "$0")"
VENV=.venv
PY="$VENV/bin/python"
PYTEST="$VENV/bin/pytest"

setup_venv() {
  if [ ! -x "$PYTEST" ]; then
    python3 -m venv "$VENV" || { echo "venv 创建失败"; return 1; }
  fi
  "$PY" -m pip install -q -r requirements.txt || { echo "依赖安装失败"; return 1; }
  echo "venv OK: $("$PY" --version) / pytest $("$PY" -c 'import pytest;print(pytest.__version__)')"
}

ensure_venv() {
  [ -x "$PYTEST" ] || setup_venv || exit 1
}

case "${1:-}" in
  setup-venv)
    setup_venv; exit $?;;
  selfcheck)
    ensure_venv
    E_ACCEPTANCE_MODE=selfcheck "$PYTEST" -q tests/test_matrix_integrity.py tests/test_framework_selfcheck.py
    rc=$?
    echo "selfcheck exit=$rc"
    exit $rc;;
  matrix)
    ensure_venv
    E_ACCEPTANCE_MODE=matrix "$PYTEST" tests/
    rc=$?
    echo "matrix exit=$rc (0=94全真实通过 1=有失败 3=存在dependency_pending 4=结算不完整)"
    exit $rc;;
  *)
    echo "用法: $0 {setup-venv|selfcheck|matrix}"; exit 2;;
esac
