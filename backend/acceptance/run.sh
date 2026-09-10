#!/usr/bin/env bash
# E 黑盒验收唯一入口：setup-venv | selfcheck | matrix
# 退出码：setup/selfcheck 0=成功 1=失败；
# matrix：0=94 场景全部真实通过（证据齐） 1=有失败 3=存在 dependency_pending
#         4=结算不完整/入口被篡改/哨兵校验失败。
# 双层防御 + 哨兵：
#   ① 拒绝外部 PYTEST_ADDOPTS 注入（-p no:framework.conftest 等禁用结算插件的
#      手段在进入 pytest 前即被拒绝 → 4）；运行时显式 env -u 清空并注入绑定的 RUN_ID。
#   ② pytest 退出后校验插件写出的结算哨兵 reports/<RUN_ID>/settlement.json
#      （存在、RUN_ID/mode 匹配、matrix 结算 94/94、四类计数与输出一致）；
#      哨兵缺失/不匹配 → 无视 pytest 退出码强制 4。裸调 pytest 不是验收入口。
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

verify_sentinel() { # $1=sentinel $2=run_id $3=mode $4=log
  "$PY" - "$1" "$2" "$3" "$4" <<'PYEOF'
import json, pathlib, re, sys
sent, rid, mode, log = sys.argv[1:5]
def fail(msg):
    print(f"SENTINEL_FAIL: {msg}", file=sys.stderr)
    sys.exit(1)
p = pathlib.Path(sent)
if not p.exists():
    fail("结算哨兵缺失（插件被禁用或会话未正常结束），本次运行不可信")
try:
    d = json.loads(p.read_text(encoding="utf-8"))
except Exception as e:
    fail(f"哨兵不可读：{e}")
if d.get("run_id") != rid:
    fail("哨兵 run_id 与入口绑定不一致")
if d.get("mode") != mode:
    fail("哨兵 mode 与入口不一致")
if d.get("completed") is not True:
    fail("哨兵缺少完成标记")
m = re.search(r"PASSED=(\d+) DEPENDENCY_PENDING=(\d+) FAILED=(\d+) SKIPPED_OTHER=(\d+)",
              pathlib.Path(log).read_text(encoding="utf-8", errors="replace"))
if not m:
    fail("pytest 输出缺少 E 验收统计行")
c = d.get("counts", {})
if (int(m[1]), int(m[2]), int(m[3]), int(m[4])) != (
        c.get("passed"), c.get("pending"), c.get("failed"), c.get("skipped_other")):
    fail(f"汇总计数与哨兵不一致：输出{m.groups()} vs 哨兵{c}")
if mode == "matrix" and (d.get("settled_unique") != 94 or d.get("settlement_ok") is not True):
    fail(f"matrix 结算不完整：settled={d.get('settled_unique')}/94 ok={d.get('settlement_ok')}")
sys.exit(0)
PYEOF
}

run_pytest() { # $1=mode 其余=pytest 参数
  local mode="$1"; shift
  if [ -n "${PYTEST_ADDOPTS:-}" ]; then
    echo "run.sh: 拒绝外部 PYTEST_ADDOPTS 注入（会篡改插件/收集范围），强制 exit 4" >&2
    exit 4
  fi
  local rid sentinel log rc vrc
  rid="$("$PY" -c 'import os; from framework import isolation; print(isolation.new_run_id(os.environ.get(isolation.ENV_RUN_PREFIX,"E")))' 2>/dev/null)" \
    || { echo "run.sh: RUN_ID 生成失败，强制 exit 4" >&2; exit 4; }
  sentinel="reports/$rid/settlement.json"
  log="$(mktemp)"
  env -u PYTEST_ADDOPTS E_ACCEPTANCE_MODE="$mode" E_ACCEPTANCE_RUN_ID="$rid" \
    "$PYTEST" "$@" 2>&1 | tee "$log"
  rc=${PIPESTATUS[0]}
  verify_sentinel "$sentinel" "$rid" "$mode" "$log"; vrc=$?
  rm -f "$log"
  if [ $vrc -ne 0 ]; then
    echo "run.sh: 哨兵校验未通过，无视 pytest 退出码($rc)强制 exit 4" >&2
    exit 4
  fi
  return "$rc"
}

case "${1:-}" in
  setup-venv)
    setup_venv; exit $?;;
  selfcheck)
    ensure_venv
    run_pytest selfcheck tests/test_matrix_integrity.py tests/test_framework_selfcheck.py
    rc=$?
    echo "selfcheck exit=$rc"
    exit $rc;;
  matrix)
    ensure_venv
    run_pytest matrix tests/
    rc=$?
    echo "matrix exit=$rc (0=94全真实通过 1=有失败 3=存在dependency_pending 4=结算不完整/入口篡改)"
    exit $rc;;
  *)
    echo "用法: $0 {setup-venv|selfcheck|matrix}"; exit 2;;
esac
