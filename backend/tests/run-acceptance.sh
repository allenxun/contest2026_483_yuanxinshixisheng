#!/usr/bin/env bash
# =====================================================================
# backend/tests/run-acceptance.sh — A 包（foundation）跨语言验收脚本
#
# 覆盖 A-foundation.md 验收项（映射详见 README.md）：全新 PG 可迁移并
# 重复无破坏 / 约束拒绝双占用和双记录 / Java+Python 测试通过 /
# 无效认证拒绝 / 最小 echo job 从 Java 契约进入 Python 并按正确代次完成 /
# 精简 JSON 样例跨语言一致 / 存储替身双语言同布局互读。
#
# 用法：bash backend/tests/run-acceptance.sh
# 前置：mvp-a-pg 隔离容器（deploy/dev/pg-up.sh）、docker、mvn、java 21、
#       backend/contracts/.venv、backend/worker-python/.venv。
# 隔离：只打 127.0.0.1:55432（mvp-a-pg），绝不触碰宿主 5432；
#       app 端口 18080（宿主 8080 已被占用）；curl 一律 --noproxy '*'。
# 每次运行新建 mvp_a_accept_<hex8> + 独立 /tmp 存储根，trap 清理；可重复执行。
# 退出码：任一 FAIL → 非 0。
# =====================================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKEND="$(cd "$SCRIPT_DIR/.." && pwd)"
DEV="$BACKEND/deploy/dev"
SUPPORT="$SCRIPT_DIR/support"
WEBJAVA="$BACKEND/web-java"
WORKERPY="$BACKEND/worker-python"
CONTRACTS="$BACKEND/contracts"
CPY="$CONTRACTS/.venv/bin/python"
WPY="$WORKERPY/.venv/bin/python"

PG_CONTAINER="${MVP_A_PG_CONTAINER:-mvp-a-pg}"
PG_HOST_PORT="${MVP_A_PG_HOST_PORT:-55432}"
PG_USER="${MVP_A_PG_USER:-postgres}"
PG_PASSWORD="${MVP_A_PG_PASSWORD:-mvp_a_local}"
APP_PORT="${ACCEPT_APP_PORT:-18080}"

SUFFIX="$(openssl rand -hex 4)"
ACCEPT_DB="mvp_a_accept_${SUFFIX}"
# 运行/存储临时目录：worktree 内专用目录（backend/tests/.work/，非 /tmp）。
# trap 仅清理本轮自建且路径前缀归属明确的目录；可用 ACCEPT_RUN_BASE 覆盖。
RUN_BASE="${ACCEPT_RUN_BASE:-$SCRIPT_DIR/.work}"
mkdir -p "$RUN_BASE"
STORAGE_ROOT="$RUN_BASE/storage-${SUFFIX}"
TMP="$RUN_BASE/run-${SUFFIX}"
mkdir -p "$TMP"
JAR="$WEBJAVA/target/web-java-0.0.1-SNAPSHOT.jar"

# ---------------- 颜色与结果登记 ----------------
if [[ -t 1 ]]; then
  C_G=$'\e[32m'; C_R=$'\e[31m'; C_B=$'\e[1m'; C_D=$'\e[2m'; C_0=$'\e[0m'
else
  C_G=""; C_R=""; C_B=""; C_D=""; C_0=""
fi
RESULTS=()   # "id|desc|acceptance|PASS|FAIL"
overall_rc=0

vlog() { printf '     %s\n' "$*"; }

check() { # check <id> <desc> <acceptance-item> <fn...>：子 shell 内 set -e 执行
  local id="$1" desc="$2" acc="$3"; shift 3
  local logf="$TMP/${id}.log" rc=0
  ( set -e; "$@" ) >"$logf" 2>&1 || rc=$?
  if [[ $rc -eq 0 ]]; then
    printf '%s[PASS]%s %-3s %s\n' "$C_G" "$C_0" "$id" "$desc"
    sed 's/^/       /' "$logf" | grep -v '^\s*$' || true
    RESULTS+=("$id|$desc|$acc|PASS")
  else
    overall_rc=1
    printf '%s[FAIL]%s %-3s %s (rc=%d) — 最近日志:\n' "$C_R" "$C_0" "$id" "$desc" "$rc"
    tail -n 15 "$logf" | sed 's/^/       | /'
    RESULTS+=("$id|$desc|$acc|FAIL")
  fi
}

fail() { echo "ASSERT-FAIL: $*" >&2; exit 1; }  # exit 只结束 check 子壳（确定性失败传播）

# ---------------- psql 辅助（一律走 docker exec 到隔离容器） ----------------
psql_t() { docker exec -i "$PG_CONTAINER" psql -U "$PG_USER" -d "$1" -tA -c "$2"; }

expect_sql_error() { # <label> <db> <SQL> <expected-constraint-fragment>
  local label="$1" db="$2" sql="$3" want="$4" out rc=0
  out=$(docker exec -i "$PG_CONTAINER" psql -U "$PG_USER" -d "$db" -v ON_ERROR_STOP=1 -c "$sql" 2>&1) || rc=$?
  [[ $rc -ne 0 ]] || fail "$label：语句竟然成功（本应被拒绝）"
  grep -q "$want" <<<"$out" || fail "$label：报错未含 $want → $out"
  vlog "$label → 如期拒绝（$want）"
}

# ---------------- HTTP 辅助（curl --noproxy '*'） ----------------
call() { # call <METHOD> <URL> [curl args...] → $CODE / $BODY
  local method="$1" url="$2"; shift 2
  local f="$TMP/body.$$"
  CODE=$(curl -sS --noproxy '*' -o "$f" -w '%{http_code}' -X "$method" "$@" "$url" 2>/dev/null || echo 000)
  BODY="$(cat "$f")"; rm -f "$f"
}
jget() { # $BODY(JSON) → 按点路径取值；true/false/null 归一为小写文本
  # 注意：程序经 heredoc 占用 stdin，JSON 改由环境变量传入（勿用 <<< 叠加 heredoc）
  JGET_JSON="$BODY" "$CPY" - "$1" <<'PYEOF'
import json, os, sys
cur = json.loads(os.environ["JGET_JSON"])
for part in sys.argv[1].split('.'):
    if isinstance(cur, list):
        cur = cur[int(part)]
    elif isinstance(cur, dict) and part in cur:
        cur = cur[part]
    else:
        sys.exit(3)
print("true" if cur is True else ("false" if cur is False else ("null" if cur is None else cur)))
PYEOF
}
jget_or_fail() { # jget_or_fail <path>（失败时打印响应体并终止本 check 子壳）
  local v
  v=$(jget "$1") || { echo "body: $BODY" >&2; exit 1; }
  printf '%s' "$v"
}

# ---------------- 清理（trap EXIT） ----------------
cleanup() {
  set +e
  [[ -f "$TMP/app.pid" ]] && kill "$(cat "$TMP/app.pid")" 2>/dev/null
  docker exec -i "$PG_CONTAINER" psql -U "$PG_USER" -d postgres -q >/dev/null 2>&1 <<SQL
SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname='$ACCEPT_DB' AND pid<>pg_backend_pid();
DROP DATABASE IF EXISTS $ACCEPT_DB;
SQL
  # 仅清理本轮创建且归属明确的目录（RUN_BASE 前缀校验；绝不动其他路径）
  case "$TMP" in "$RUN_BASE"/run-*) rm -rf "$TMP" ;; esac
  case "$STORAGE_ROOT" in "$RUN_BASE"/storage-*) rm -rf "$STORAGE_ROOT" ;; esac
  rmdir "$RUN_BASE" 2>/dev/null
}
trap cleanup EXIT

# ---------------- 前置自检 ----------------
printf '%s▶ 前置自检（mvp-a-pg / docker / mvn / java / venv）%s\n' "$C_B" "$C_0"
"$DEV/pg-up.sh" >/dev/null 2>&1 || { echo "mvp-a-pg 启动失败（deploy/dev/pg-up.sh）" >&2; exit 2; }
command -v docker >/dev/null && command -v mvn >/dev/null && command -v java >/dev/null \
  || { echo "缺少 docker/mvn/java" >&2; exit 2; }
[[ -x "$CPY" && -x "$WPY" ]] || { echo "缺少 contracts/worker .venv（见 README.md）" >&2; exit 2; }
echo "  accept db = $ACCEPT_DB · storage = $STORAGE_ROOT · app port = $APP_PORT"

# =====================================================================
# a) 迁移：全新库 → 14 表 → 重复 migrate 无破坏（MIG2_NOOP）
# =====================================================================
step_a_migrate() {
  "$DEV/createdb.sh" "$ACCEPT_DB"
  "$DEV/migrate.sh" "$ACCEPT_DB" >/dev/null
  local n; n=$(psql_t "$ACCEPT_DB" \
    "SELECT count(*) FROM information_schema.tables WHERE table_schema='public' AND table_type='BASE TABLE' AND table_name<>'flyway_schema_history'")
  [[ "$n" == "14" ]] || fail "public 业务表应 14，实际 $n"
  vlog "14 张业务表就位（另含 flyway_schema_history）"
  local h1 h2
  h1=$(psql_t "$ACCEPT_DB" "SELECT count(*) FROM flyway_schema_history")
  "$DEV/migrate.sh" "$ACCEPT_DB" >/dev/null
  h2=$(psql_t "$ACCEPT_DB" "SELECT count(*) FROM flyway_schema_history")
  [[ "$h2" == "$h1" && "$h1" -ge 1 ]] || fail "MIG2_NOOP 失败：history $h1 → $h2"
  vlog "MIG2_NOOP：第二次 migrate 成功、flyway_schema_history 行数不变（$h1）"
}
check a "全新库迁移=14 表；重复 migrate 无破坏" "验收：全新 PG 可迁移并重复启动无破坏" step_a_migrate

# =====================================================================
# b) 数据约束拒绝（先种最小父链，每条负例必须报错并含约束名）
# =====================================================================
step_b_seed() {
  docker exec -i "$PG_CONTAINER" psql -U "$PG_USER" -d "$ACCEPT_DB" -v ON_ERROR_STOP=1 -f - <<'SQL'
-- 最小父链种子：6 个 T13 行 + 账号 + 成员 + 云台 + 测肤 + 方案 + 微晶 + 执行1 + 记录1
-- 控制端形状必须满足 V1 ck_execution_controller_ownership（DATA T07）：
--   app → account_id + installation_id 双全且 gimbal_id NULL；gimbal → 反之。
INSERT INTO idempotency_requests (id, principal_type, principal_id, operation, idempotency_key, payload_hash) VALUES
 ('11111111-1111-4111-8111-111111111101','app_account','accept-seed','seed.op','k-asm-1','0000000000000000000000000000000000000000000000000000000000000000'),
 ('11111111-1111-4111-8111-111111111102','app_account','accept-seed','seed.op','k-exec-1','0000000000000000000000000000000000000000000000000000000000000000'),
 ('11111111-1111-4111-8111-111111111103','app_account','accept-seed','seed.op','k-exec-2','0000000000000000000000000000000000000000000000000000000000000000'),
 ('11111111-1111-4111-8111-111111111104','app_account','accept-seed','seed.op','k-exec-3','0000000000000000000000000000000000000000000000000000000000000000'),
 ('11111111-1111-4111-8111-111111111105','app_account','accept-seed','seed.op','k-asm-2','0000000000000000000000000000000000000000000000000000000000000000'),
 ('11111111-1111-4111-8111-111111111106','app_account','accept-seed','seed.op','k-asm-3','0000000000000000000000000000000000000000000000000000000000000000');
INSERT INTO accounts (id, login_provider, login_subject)
 VALUES ('aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaa1','phone','+8613900000001');
INSERT INTO members (id, identity_namespace, face_subject_ref)
 VALUES ('22222222-2222-4222-8222-222222222201','accept-ns','face-seed-1');
INSERT INTO gimbals (id, serial_no, auth_subject_ref)
 VALUES ('33333333-3333-4333-8333-333333333301','GIM-ACCEPT-SEED','subject-seed-1');
INSERT INTO skin_assessments (id, gimbal_id, member_id, source_request_id)
 VALUES ('44444444-4444-4444-8444-444444444401','33333333-3333-4333-8333-333333333301','22222222-2222-4222-8222-222222222201','11111111-1111-4111-8111-111111111101');
INSERT INTO care_plans (id, assessment_id, member_id)
 VALUES ('55555555-5555-4555-8555-555555555501','44444444-4444-4444-8444-444444444401','22222222-2222-4222-8222-222222222201');
INSERT INTO microcrystals (id, serial_no)
 VALUES ('66666666-6666-4666-8666-666666666601','MC-ACCEPT-SEED');
INSERT INTO care_executions (id, plan_id, member_id, microcrystal_id, controller_type,
                             controller_account_id, controller_installation_id,
                             assessment_id_at_start, source_request_id)
 VALUES ('77777777-7777-4777-8777-777777777701','55555555-5555-4555-8555-555555555501','22222222-2222-4222-8222-222222222201','66666666-6666-4666-8666-666666666601','app','aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaa1','inst-seed-owner','44444444-4444-4444-8444-444444444401','11111111-1111-4111-8111-111111111102');
INSERT INTO care_records (id, execution_id, client_record_id, plan_id, member_id, microcrystal_id,
                          count_delta, source_epoch, source_seq, payload_hash, payload)
 VALUES ('99999999-9999-4999-8999-999999999901','77777777-7777-4777-8777-777777777701','rec-a','55555555-5555-4555-8555-555555555501','22222222-2222-4222-8222-222222222201','66666666-6666-4666-8666-666666666601',1,'epoch-1',1,'a0000000000000000000000000000000000000000000000000000000000000001','{"schema_version":1}');
SQL
  vlog "种子父行插入完成（合法 app 控制端形状；执行1 open、记录1 已占位）"
}
check b0 "约束负例的最小父链种子（合法控制端形状）" "验收：约束拒绝（前置）" step_b_seed

step_b1() {
  expect_sql_error "同一微晶双 open 执行" "$ACCEPT_DB" \
    "INSERT INTO care_executions (id, plan_id, member_id, microcrystal_id, controller_type, controller_account_id, controller_installation_id, assessment_id_at_start, source_request_id) VALUES ('77777777-7777-4777-8777-777777777702','55555555-5555-4555-8555-555555555501','22222222-2222-4222-8222-222222222201','66666666-6666-4666-8666-666666666601','app','aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaa1','inst-seed-owner-2','44444444-4444-4444-8444-444444444401','11111111-1111-4111-8111-111111111103')" \
    "uq_execution_open_microcrystal"
}
check b1 "同一微晶第二个未收尾执行 → 拒绝（双占用）" "验收：约束拒绝双占用" step_b1

step_b2() {
  expect_sql_error "重复 (execution_id,source_epoch,source_seq)" "$ACCEPT_DB" \
    "INSERT INTO care_records (id, execution_id, client_record_id, plan_id, member_id, microcrystal_id, count_delta, source_epoch, source_seq, payload_hash, payload) VALUES ('99999999-9999-4999-8999-999999999902','77777777-7777-4777-8777-777777777701','rec-b','55555555-5555-4555-8555-555555555501','22222222-2222-4222-8222-222222222201','66666666-6666-4666-8666-666666666601',1,'epoch-1',1,'a0000000000000000000000000000000000000000000000000000000000000002','{\"schema_version\":1}')" \
    "uq_record_source"
}
check b2 "同一执行重复源三元组记录 → 拒绝（双记录）" "验收：约束拒绝双记录" step_b2

step_b7() {
  expect_sql_error "app 控制端缺 account/installation" "$ACCEPT_DB" \
    "INSERT INTO care_executions (id, plan_id, member_id, microcrystal_id, controller_type, assessment_id_at_start, source_request_id) VALUES ('77777777-7777-4777-8777-777777777703','55555555-5555-4555-8555-555555555501','22222222-2222-4222-8222-222222222201','66666666-6666-4666-8666-666666666601','app','44444444-4444-4444-8444-444444444401','11111111-1111-4111-8111-111111111104')" \
    "ck_execution_controller_ownership"
}
check b7 "care_executions 控制端归属 CHECK → 非法形状拒绝（oracle B3）" "交付2：检查条件（DATA T07）" step_b7

step_b8() {
  expect_sql_error "active 目标无 registration" "$ACCEPT_DB" \
    "INSERT INTO notification_destinations (id, installation_id, account_id, status, session_ref) VALUES ('bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbb8','inst-b8','aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaa1','active','sess-b8')" \
    "ck_destination_active_fields"
}
check b8 "notification_destinations active 必须非空 registration → 拒绝（oracle M5）" "交付2：检查条件（DD T09）" step_b8

step_b3() {
  expect_sql_error "重复 Idempotency-Key" "$ACCEPT_DB" \
    "INSERT INTO idempotency_requests (principal_type, principal_id, operation, idempotency_key, payload_hash) VALUES ('app_account','accept-seed','seed.op','k-asm-1','b0000000000000000000000000000000000000000000000000000000000000000')" \
    "uq_idem_principal"
}
check b3 "T13 (principal,operation,key) 重复 → 拒绝" "交付2：关键唯一约束" step_b3

step_b4() {
  expect_sql_error "成员身份对重复" "$ACCEPT_DB" \
    "INSERT INTO members (identity_namespace, face_subject_ref) VALUES ('accept-ns','face-seed-1')" \
    "uq_members_identity"
}
check b4 "members (identity_namespace,face_subject_ref) 双非空重复 → 拒绝" "交付2：部分唯一索引" step_b4

step_b5() {
  expect_sql_error "非法测肤状态" "$ACCEPT_DB" \
    "INSERT INTO skin_assessments (gimbal_id, member_id, status, source_request_id) VALUES ('33333333-3333-4333-8333-333333333301','22222222-2222-4222-8222-222222222201','bogus','11111111-1111-4111-8111-111111111105')" \
    "ck_assessment_status"
}
check b5 "skin_assessments 非法 status CHECK → 拒绝" "交付2：检查条件" step_b5

step_b6() {
  expect_sql_error "current_photo_version=0" "$ACCEPT_DB" \
    "INSERT INTO skin_assessments (gimbal_id, member_id, current_photo_version, source_request_id) VALUES ('33333333-3333-4333-8333-333333333301','22222222-2222-4222-8222-222222222201',0,'11111111-1111-4111-8111-111111111106')" \
    "ck_assessment_current_photo_version"
}
check b6 "skin_assessments current_photo_version > 0 CHECK → 拒绝" "交付2：检查条件" step_b6

# =====================================================================
# c) 契约：JCS selftest / 样例+向量重算 / OpenAPI 校验
# =====================================================================
step_c1() { ( cd "$CONTRACTS" && "$CPY" scripts/jcs.py selftest ); }
check c1 "jcs.py selftest（ES6 Number::toString 权威数对）" "验收：精简 JSON 样例跨语言一致" step_c1

step_c2() { ( cd "$CONTRACTS" && "$CPY" scripts/validate_samples.py | tail -1 ); }
check c2 "validate_samples.py（样例+16 向量重算）" "验收：精简 JSON 样例跨语言一致" step_c2

step_c3() {
  ( cd "$CONTRACTS" && "$CPY" -c "
import yaml
from openapi_spec_validator import validate
validate(yaml.safe_load(open('openapi/openapi.yaml')))
print('OPENAPI VALID')" )
}
check c3 "openapi_spec_validator" "交付3：OpenAPI 基础契约" step_c3

# =====================================================================
# d/e) Java 全量测试+jar / Python 全量测试
# =====================================================================
step_d() {
  local out line n
  out=$(cd "$WEBJAVA" && mvn -B package 2>&1) || { printf '%s\n' "$out" | tail -30; fail "mvn package 失败"; }
  line=$(printf '%s\n' "$out" | grep -E 'Tests run:.*Skipped: [0-9]+$' | tail -1)
  [[ -n "$line" && "$line" == *"Failures: 0, Errors: 0"* ]] || fail "Java 测试存在失败: $line"
  n=$(printf '%s' "$line" | sed -E 's/.*Tests run: ([0-9]+).*/\1/')
  [[ "$n" -ge 75 ]] || fail "Java 用例数 $n < 75"
  [[ -f "$JAR" ]] || fail "jar 未产出：$JAR"
  vlog "Java 合计 Tests run=$n（全绿）；jar 已构建"
}
check d "mvn package（Java 全量测试 + 可运行 jar）" "验收：Java/Python 测试通过" step_d

step_e() {
  local out n
  out=$(cd "$WORKERPY" && .venv/bin/python -m pytest -q 2>&1 | tail -1) \
    || fail "pytest 执行失败: $out"
  [[ "$out" == *" passed "* && "$out" != *" failed "* ]] || fail "pytest 结果异常: $out"
  n=$(printf '%s' "$out" | sed -E 's/([0-9]+) passed.*/\1/')
  [[ "$n" -ge 43 ]] || fail "Python 用例数 $n < 43"
  vlog "Python 合计 passed=$n"
}
check e "worker pytest（T12 运行时全量）" "验收：Java/Python 测试通过" step_e

# =====================================================================
# f) 实时 E2E：app:18080（accept 库）+ worker --once
# =====================================================================
# --- app 生命周期辅助（f0 重启周期 & f10 停止共用）---
_app_launch() { # _app_launch <logfile>
  local logf="$1"
  nohup env \
    SERVER_PORT="$APP_PORT" \
    SPRING_PROFILES_ACTIVE=dev \
    SPRING_DATASOURCE_URL="jdbc:postgresql://127.0.0.1:${PG_HOST_PORT}/${ACCEPT_DB}" \
    SPRING_DATASOURCE_USERNAME="$PG_USER" \
    SPRING_DATASOURCE_PASSWORD="$PG_PASSWORD" \
    APP_STORAGE_DEV_DIR="$STORAGE_ROOT" \
    java -jar "$JAR" >"$logf" 2>&1 &
  echo $! > "$TMP/app.pid"
}
_app_wait_health() { # _app_wait_health <logfile>
  local logf="$1" i ok=0
  for i in $(seq 1 120); do
    if curl -sS --noproxy '*' -o "$TMP/health" "http://127.0.0.1:${APP_PORT}/actuator/health" 2>/dev/null \
       && grep -q '"status":"UP"' "$TMP/health"; then ok=1; break; fi
    sleep 1
  done
  [[ $ok -eq 1 ]] || { tail -n 20 "$logf"; fail "app 未在 120s 内 UP"; }
}
_app_stop() {
  [[ -f "$TMP/app.pid" ]] || return 0
  local pid i; pid=$(cat "$TMP/app.pid")
  kill "$pid" 2>/dev/null || true
  for i in $(seq 1 30); do kill -0 "$pid" 2>/dev/null || break; sleep 1; done
  if kill -0 "$pid" 2>/dev/null; then kill -9 "$pid" 2>/dev/null || true; fail "app 未在 30s 内退出"; fi
  rm -f "$TMP/app.pid"
}

step_f0_boot() {
  mkdir -p "$STORAGE_ROOT"
  _app_launch "$TMP/java-app-1.log"
  _app_wait_health "$TMP/java-app-1.log"
  vlog "第一次启动 UP：pid=$(cat "$TMP/app.pid") port=$APP_PORT db=$ACCEPT_DB"
  # “重复启动无破坏”：SIGTERM 停止 → 再次启动 → health UP + Flyway no-op
  _app_stop
  _app_launch "$TMP/java-app-2.log"
  _app_wait_health "$TMP/java-app-2.log"
  grep -q "No migration necessary" "$TMP/java-app-2.log" \
    || fail "第二次启动 Flyway 应为 no-op（日志缺 'No migration necessary'）"
  vlog "第二次启动 UP：pid=$(cat "$TMP/app.pid")；Flyway no-op 已确认（重复启动无破坏）"
}
check f0 "app 启动→健康→SIGTERM 停止→再启动（Flyway no-op）" "验收：重复启动无破坏（交付1）" step_f0_boot

step_f1_noauth() {
  call GET "http://127.0.0.1:${APP_PORT}/api/v1/me/member-access-grants"
  [[ "$CODE" == "401" ]] || fail "无 token 期望 401，实际 $CODE"
  grep -q AUTH_REQUIRED <<<"$BODY" || fail "401 信封应含 AUTH_REQUIRED：$BODY"
}
check f1 "业务 stub 无 token → 401 AUTH_REQUIRED 信封" "验收：无效认证拒绝" step_f1_noauth

step_f2_auth() {
  local phone chal
  phone=$(printf '+86138%08d' $(( (0x$SUFFIX) % 100000000 )))   # 纯数字 E.164
  call POST "http://127.0.0.1:${APP_PORT}/api/v1/auth/sms-challenges" \
    -H 'Content-Type: application/json' \
    -d "{\"phone\":\"$phone\",\"purpose\":\"login\"}"
  [[ "$CODE" == "200" ]] || fail "sms-challenges 期望 200，实际 $CODE $BODY"
  chal=$(jget_or_fail data.challengeId)
  call POST "http://127.0.0.1:${APP_PORT}/api/v1/auth/sessions" \
    -H 'Content-Type: application/json' \
    -d "{\"challengeId\":\"$chal\",\"code\":\"123456\",\"installationId\":\"accept-inst-${SUFFIX}\"}"
  [[ "$CODE" == "200" ]] || fail "sessions 期望 200，实际 $CODE $BODY"
  jget_or_fail data.accessToken > "$TMP/token"
  [[ -s "$TMP/token" ]] || fail "未拿到 accessToken"
  vlog "手机号会话建立（固定验证码替身 123456 + installationId）"
}
check f2 "sms-challenges→sessions(123456+installation)→token" "交付4：认证端口+隔离替身" step_f2_auth

step_f3_stub501() {
  local tok; tok=$(cat "$TMP/token")
  call GET "http://127.0.0.1:${APP_PORT}/api/v1/me/member-access-grants" -H "Authorization: Bearer $tok"
  [[ "$CODE" == "501" ]] || fail "已认证 stub 期望 501，实际 $CODE $BODY"
  grep -q NOT_IMPLEMENTED <<<"$BODY" || fail "501 信封应含 NOT_IMPLEMENTED：$BODY"
}
check f3 "业务 stub 有 token → 501 NOT_IMPLEMENTED（不给假 200）" "交付3：未实现业务不给假 200" step_f3_stub501

step_f4_echo_idem() {
  local tok key json job1 job2 replayed
  tok=$(cat "$TMP/token"); key="accept-echo-${SUFFIX}"
  json='{"message":"acceptance 回声 跨语言","numbersAsStrings":["42","7"]}'
  call POST "http://127.0.0.1:${APP_PORT}/api/v1/system/echo-jobs" \
    -H 'Content-Type: application/json' -H "Authorization: Bearer $tok" \
    -H "Idempotency-Key: $key" -d "$json"
  [[ "$CODE" == "200" ]] || fail "echo POST 期望 200，实际 $CODE $BODY"
  local st; st=$(jget_or_fail data.status)
  job1=$(jget_or_fail data.jobId)
  [[ "$st" == "queued" ]] || fail "期望 data.status=queued，实际 $st"
  echo "$job1" > "$TMP/job_id"
  call POST "http://127.0.0.1:${APP_PORT}/api/v1/system/echo-jobs" \
    -H 'Content-Type: application/json' -H "Authorization: Bearer $tok" \
    -H "Idempotency-Key: $key" -d "$json"
  replayed=$(jget_or_fail meta.replayed); job2=$(jget_or_fail data.jobId)
  [[ "$replayed" == "true" && "$job2" == "$job1" ]] \
    || fail "同键重放应 meta.replayed=true 且同 jobId（$job1 vs $job2，replayed=$replayed）"
  vlog "T13 受理+重放一致：jobId=$job1"
}
check f4 "echo-jobs→queued；同 Idempotency-Key 重放同 jobId+replayed=true" "交付5：T13 幂等公共设施" step_f4_echo_idem

step_f5_badtoken() {
  call GET "http://127.0.0.1:${APP_PORT}/api/v1/me/member-access-grants" -H "Authorization: Bearer not-a-real-token-000"
  [[ "$CODE" == "401" ]] || fail "坏 token 期望 401，实际 $CODE"
  grep -q SESSION_INVALID <<<"$BODY" || fail "应 SESSION_INVALID：$BODY"
}
check f5 "伪造 Bearer → 401 SESSION_INVALID" "验收：无效认证拒绝" step_f5_badtoken

step_f6_worker() {
  local out n
  out=$(cd "$WORKERPY" && env "MVP_WORKER_PG_DSN=postgresql://${PG_USER}:${PG_PASSWORD}@127.0.0.1:${PG_HOST_PORT}/${ACCEPT_DB}" \
    .venv/bin/python -m mvp_worker --once 2>&1) || { printf '%s\n' "$out" | tail -10; fail "worker --once 退出非 0"; }
  printf '%s\n' "$out" | tail -n 2
  n=$(printf '%s' "$out" | grep -oE 'once_cycle_processed_jobs: [0-9]+' | grep -oE '[0-9]+$') || true
  [[ -n "${n:-}" && "$n" -ge 1 ]] || fail "worker --once 处理数应 ≥1，实际 '$n'"
  vlog "processed=$n（claim→echo handler→complete，代次守护）"
}
check f6 "worker --once 领取并完成 system.echo" "验收：最小 job 从 Java 契约进入 Python" step_f6_worker

step_f7_succeeded() {
  local tok job st att
  tok=$(cat "$TMP/token"); job=$(cat "$TMP/job_id")
  call GET "http://127.0.0.1:${APP_PORT}/api/v1/system/echo-jobs/$job" -H "Authorization: Bearer $tok"
  [[ "$CODE" == "200" ]] || fail "GET echo job 期望 200，实际 $CODE $BODY"
  st=$(jget_or_fail data.status); att=$(jget_or_fail data.attemptCount)
  [[ "$st" == "succeeded" && "$att" == "1" ]] || fail "期望 succeeded/attemptCount=\"1\"，实际 $st/$att"
  vlog "job=$job status=$st attemptCount=$att"
}
check f7 "GET echo job → succeeded + attemptCount \"1\"" "验收：按正确代次完成" step_f7_succeeded

step_f8_payload_schema() {
  local job; job=$(cat "$TMP/job_id")
  psql_t "$ACCEPT_DB" "SELECT payload::text FROM async_jobs WHERE id='$job'" > "$TMP/payload.json"
  "$CPY" "$SUPPORT/validate_payload.py" "$TMP/payload.json" \
    "$CONTRACTS/schemas/payload-system-echo.json" "$CONTRACTS"
}
check f8 "async_jobs.payload（Java 写入）通过 payload-system-echo schema" "验收：跨语言契约一致" step_f8_payload_schema

step_f9_storage() {
  local key="dev/acceptance/${SUFFIX}.bin" classes="$WEBJAVA/target/classes" got
  # Java FileSystemStorageDouble.put → 期望落在 <root>/<key> 原样路径，Python double 读取
  java -cp "$classes" "$SUPPORT/StorageInterop.java" put "$STORAGE_ROOT" "$key" "hello-from-java"
  [[ -f "$STORAGE_ROOT/$key" ]] || fail "Java put 未落在 <root>/<object_key> 原样路径"
  MVP_A_STORAGE_DEV_DIR="$STORAGE_ROOT" "$WPY" - "$key" <<'PYEOF'
import sys
from mvp_worker.media.storage import FilesystemStorageDouble
data = FilesystemStorageDouble().get(sys.argv[1])
assert data == b"hello-from-java", data
print("python 读到 Java 写入：<root>/%s = %d bytes" % (sys.argv[1], len(data)))
PYEOF
  # Python double.put → Java double.get（key 带 "/" 子目录）
  MVP_A_STORAGE_DEV_DIR="$STORAGE_ROOT" "$WPY" - "$key.py" <<'PYEOF'
import sys
from mvp_worker.media.storage import FilesystemStorageDouble
FilesystemStorageDouble().put(sys.argv[1], b"hello-from-python")
PYEOF
  got=$(java -cp "$classes" "$SUPPORT/StorageInterop.java" get "$STORAGE_ROOT" "$key.py" 2>/dev/null)
  [[ "$got" == "hello-from-python" ]] || fail "Java 读 Python 写入内容不符：$got"
  vlog "双向互读一致；布局 = $STORAGE_ROOT/<object_key>"
}
check f9 "存储替身互操作：Java↔Python 同 root 同 key 互读" "交付6：媒体/存储适配基础" step_f9_storage

step_f10_stop() {
  _app_stop
  vlog "app 已停止（SIGTERM 优雅停机）"
}
check f10 "app 优雅停止（SIGTERM）" "交付1：启动/停止" step_f10_stop

# =====================================================================
# g) 汇总
# =====================================================================
echo
printf '%s===== run-acceptance 汇总（db=%s）=====%s\n' "$C_B" "$ACCEPT_DB" "$C_0"
printf '%-4s | %-56s | %-44s | %-4s\n' "STEP" "CHECK" "A-FOUNDATION 验收/交付" "RES"
printf '%.0s-' {1..118}; echo
pass_n=0; fail_n=0
for row in "${RESULTS[@]}"; do
  IFS='|' read -r id desc acc st <<<"$row"
  if [[ "$st" == PASS ]]; then
    pass_n=$((pass_n + 1))
    printf '%-4s | %-56s | %-44s | %s\n' "$id" "$desc" "$acc" "${C_G}PASS${C_0}"
  else
    fail_n=$((fail_n + 1))
    printf '%-4s | %-56s | %-44s | %s\n' "$id" "$desc" "$acc" "${C_R}FAIL${C_0}"
  fi
done
printf '%.0s-' {1..118}; echo
if [[ $fail_n -eq 0 ]]; then
  printf '%sRESULT: ALL PASS (%d checks)%s\n' "$C_G" "$pass_n" "$C_0"
else
  printf '%sRESULT: %d PASS / %d FAIL%s\n' "$C_R" "$pass_n" "$fail_n" "$C_0"
fi
exit $overall_rc
