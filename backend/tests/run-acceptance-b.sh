#!/usr/bin/env bash
# =====================================================================
# backend/tests/run-acceptance-b.sh — B 包端到端验收（b1..b39）
#
# 覆盖 .coordination/B-work/spec/lane-acceptance.md 的 b1..b39，驱动真实进程：
#   - Spring Boot jar @127.0.0.1:18083（APP / 云台 HTTP，12 个 B API）
#   - Python worker 活体循环 @127.0.0.1:18084（真实通知投递）
#   - python -m mvp_worker.scanners --once（离线/异常扫描；C7/C8 裁定核验）
#   - mvn -B test / pytest -q（跨语言回归）
#
# 退出码：
#   0 = 全部 PASS；
#   1 = 存在 FAIL 或 BLOCKED-依赖；
#   4 = 前置自检 / 环境不满足（未真正执行检查）。
#
# 运行：bash backend/tests/run-acceptance-b.sh
# 可选：B_ACCEPT_KEEP_DB=1 保留验收库与临时目录；B_ACCEPT_BASE=<dir> 覆盖临时基址。
# 隔离：只打 127.0.0.1:55435（mvp-b-pg）；web 18083 / worker 18084；
#       严禁 5432/55432/55436/18080-18082/18085；curl 一律 --noproxy '*'。
# 临时文件在 <base>/b-accept-<ts>/，trap 前缀校验清理；验收库 DROP。
# 检查函数定义在 support/b-checks-{1,2,3}.sh（本脚本 source）。
# =====================================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKEND="$(cd "$SCRIPT_DIR/.." && pwd)"
SUPPORT="$SCRIPT_DIR/support"
WEBJAVA="$BACKEND/web-java"
WORKERPY="$BACKEND/worker-python"
CONTRACTS="$BACKEND/contracts"
DEV="$BACKEND/deploy/dev"
CPY="$CONTRACTS/.venv/bin/python"
WPY="$WORKERPY/.venv/bin/python"

PG="${MVP_B_PG_CONTAINER:-mvp-b-pg}"
PG_PORT=55435
PG_USER=postgres
PG_PASSWORD=mvp_b_local
WEB_PORT=18083
WORKER_PORT=18084
WEB="http://127.0.0.1:${WEB_PORT}"
HELP="$CPY $SUPPORT/b-helper.py"
DELIVER="$WPY $SUPPORT/b-deliver.py"

SUFFIX="$(openssl rand -hex 4 2>/dev/null || date +%s%N)"
ACCEPT_DB="mvp_b_accept_${SUFFIX}"
B_DSN="postgresql://${PG_USER}:${PG_PASSWORD}@127.0.0.1:${PG_PORT}/${ACCEPT_DB}"
FIX="env MVP_WORKER_PG_DSN=$B_DSN $WPY $SUPPORT/b-fixture.py"
RUN_BASE="${B_ACCEPT_BASE:-$SCRIPT_DIR/.work}"
mkdir -p "$RUN_BASE"
TMP="$RUN_BASE/b-accept-${SUFFIX}"
STORAGE_ROOT="$TMP/storage"
mkdir -p "$TMP" "$STORAGE_ROOT" "$TMP/b14-bodies"
OBS_FILE="$TMP/b14-observed.tsv"; : > "$OBS_FILE"
JAR="$WEBJAVA/target/web-java-0.0.1-SNAPSHOT.jar"
JAVA_TEST_ENV=(MVP_A_PG_JDBC="jdbc:postgresql://127.0.0.1:${PG_PORT}/postgres" \
               MVP_A_PG_USER="$PG_USER" MVP_A_PG_PASSWORD="$PG_PASSWORD")

if [[ -t 1 ]]; then C_G=$'\e[32m'; C_R=$'\e[31m'; C_Y=$'\e[33m'; C_B=$'\e[1m'; C_0=$'\e[0m'
else C_G=""; C_R=""; C_Y=""; C_B=""; C_0=""; fi

RESULTS=()
overall_rc=0
TREE_BEFORE=""; HEAD_BEFORE=""

vlog() { printf '       %s\n' "$*"; }
fail() { echo "ASSERT-FAIL: $*" >&2; exit 1; }
aeq() { [[ "$1" == "$2" ]] || fail "expected [$2] got [$1]${3:+ ($3)}"; }
aneq() { [[ "$1" != "$2" ]] || fail "values must differ: [$1]${3:+ ($3)}"; }

check() { # check <id> <desc> <fn>
  local id="$1" desc="$2"; shift 2
  local logf="$TMP/${id}.log" rc=0
  ( set -e; "$@" ) >"$logf" 2>&1 || rc=$?
  local ev; ev="$(grep -v '^[[:space:]]*$' "$logf" | tail -n 1 || true)"
  if [[ $rc -eq 0 ]]; then
    printf '%s[PASS]%s %-4s %s\n' "$C_G" "$C_0" "$id" "$desc"
    sed 's/^/       /' "$logf" | grep -v '^ *$' || true
    RESULTS+=("$id|$desc|PASS|$ev")
  else
    overall_rc=1
    printf '%s[FAIL]%s %-4s %s (rc=%d) — 最近日志:\n' "$C_R" "$C_0" "$id" "$desc" "$rc"
    tail -n 15 "$logf" | sed 's/^/       | /'
    RESULTS+=("$id|$desc|FAIL|${ev:0:300}")
  fi
}
blocked() {
  local id="$1" desc="$2" reason="$3"
  printf '%s[BLOCKED]%s %-4s %s — %s\n' "$C_Y" "$C_0" "$id" "$desc" "$reason"
  RESULTS+=("$id|$desc|BLOCKED|$reason")
  overall_rc=1
}

# 调试用：B_ACCEPT_FILTER="b1 b2" 只跑指定检查（前置自检与 app 启动仍执行）。
FILTER="${B_ACCEPT_FILTER:-}"
maybe_check() {
  local id="$1"
  if [[ -n "$FILTER" ]]; then
    case " $FILTER " in *" $id "*) ;; *) echo "[SKIP] $id (B_ACCEPT_FILTER)"; return 0 ;; esac
  fi
  check "$@"
}

# ---------------- psql / json / HTTP 辅助 ----------------
psql_b()  { docker exec -i "$PG" psql -U "$PG_USER" -d "$ACCEPT_DB" -tA -q -c "$1"; }
psql_bf() { docker exec -i "$PG" psql -U "$PG_USER" -d "$ACCEPT_DB" -tA -q -v ON_ERROR_STOP=1 -f -; }
new_id() { "$CPY" -c 'import uuid;print(uuid.uuid4())'; }
new_phone() { printf '+86139%08d' $(( (RANDOM * 32768 + RANDOM) % 100000000 )); }

call() {
  local method="$1" url="$2"; shift 2
  local f="$TMP/.body.$$"
  CODE=$(curl -sS --noproxy '*' -o "$f" -w '%{http_code}' -X "$method" "$@" "$url" 2>/dev/null || echo 000)
  BODY="$(cat "$f" 2>/dev/null || true)"; rm -f "$f"
}
op_call() {
  local opid="$1" method="$2" url="$3"; shift 3
  call "$method" "$url" "$@"
  if [[ "$CODE" =~ ^[0-9]+$ ]] && (( CODE >= 400 )); then
    local bf="$TMP/b14-bodies/${opid}-${RANDOM}-${BASHPID}.json"
    printf '%s' "$BODY" > "$bf"
    printf '%s|%s|%s\n' "$opid" "$CODE" "$bf" >> "$OBS_FILE"
  fi
}
jget()   { JGET_JSON="$BODY" $HELP jget "$1"; }
hkeys()  { JGET_JSON="$BODY" $HELP keys "${1:-}"; }
hakeys() { JGET_JSON="$BODY" $HELP assert-keys "$1" "$2"; }
envelope() { $HELP envelope "$1"; }
mask()   { $HELP mask "$1"; }

# ---------------- 前置自检 / 环境 ----------------
preflight() {
  printf '%s▶ 前置自检（docker/mvn/java21/venv/PG/端口/契约/迁移/jar）%s\n' "$C_B" "$C_0"
  command -v docker >/dev/null || { echo "缺少 docker" >&2; exit 4; }
  command -v mvn >/dev/null || { echo "缺少 mvn" >&2; exit 4; }
  command -v java >/dev/null || { echo "缺少 java" >&2; exit 4; }
  java -version 2>&1 | grep -q '"21' || { echo "需要 Java 21" >&2; exit 4; }
  [[ -x "$CPY" && -x "$WPY" ]] || { echo "缺少 contracts/worker .venv" >&2; exit 4; }

  docker start "$PG" >/dev/null 2>&1 || true
  docker exec "$PG" pg_isready -U "$PG_USER" -d postgres >/dev/null 2>&1 \
    || { echo "mvp-b-pg 不可达（$PG_PORT）" >&2; exit 4; }

  if ss -ltn 2>/dev/null | awk '{print $4}' | grep -Eq "[:.]${WEB_PORT}\$"; then
    echo "端口 ${WEB_PORT} 已被占用，拒绝抢占" >&2; exit 4; fi
  if ss -ltn 2>/dev/null | awk '{print $4}' | grep -Eq "[:.]${WORKER_PORT}\$"; then
    echo "端口 ${WORKER_PORT} 已被占用，拒绝抢占" >&2; exit 4; fi

  TREE_BEFORE="$(git -C "$BACKEND/.." status --porcelain 2>/dev/null || true)"
  HEAD_BEFORE="$(git -C "$BACKEND/.." rev-parse HEAD)"
  printf '  HEAD=%s\n' "$HEAD_BEFORE"
  printf '  accept db=%s · storage=%s · web=%s · worker=%s\n' "$ACCEPT_DB" "$STORAGE_ROOT" "$WEB_PORT" "$WORKER_PORT"

  ( cd "$CONTRACTS" && "$CPY" -c "import yaml;from openapi_spec_validator import validate;validate(yaml.safe_load(open('openapi/openapi.yaml')));print('OPENAPI OK')" ) \
    || { echo "openapi_spec_validator 失败" >&2; exit 4; }
  ( cd "$CONTRACTS" && "$CPY" scripts/validate_responses.py --selftest >/dev/null ) \
    || { echo "validate_responses --selftest 失败" >&2; exit 4; }
  ( cd "$CONTRACTS" && "$CPY" scripts/validate_samples.py >/dev/null ) \
    || { echo "validate_samples 失败" >&2; exit 4; }
  ( cd "$CONTRACTS" && "$CPY" scripts/jcs.py selftest >/dev/null ) \
    || { echo "jcs selftest 失败" >&2; exit 4; }
  vlog "契约校验四项 rc=0"

  env MVP_A_PG_CONTAINER="$PG" MVP_A_PG_HOST_PORT="$PG_PORT" \
      MVP_A_PG_USER="$PG_USER" MVP_A_PG_PASSWORD="$PG_PASSWORD" \
      "$DEV/createdb.sh" "$ACCEPT_DB" >/dev/null
  env MVP_A_PG_CONTAINER="$PG" MVP_A_PG_HOST_PORT="$PG_PORT" \
      MVP_A_PG_USER="$PG_USER" MVP_A_PG_PASSWORD="$PG_PASSWORD" \
      "$DEV/migrate.sh" "$ACCEPT_DB" >/dev/null
  local n; n=$(psql_b "SELECT count(*) FROM information_schema.tables WHERE table_schema='public' AND table_type='BASE TABLE' AND table_name<>'flyway_schema_history'")
  [[ "$n" == "14" ]] || { echo "迁移后业务表应为 14，实际 $n" >&2; exit 4; }
  vlog "Flyway V1+V2 完成（14 业务表）"

  ( cd "$WEBJAVA" && env -u APP_STORAGE_DEV_DIR "${JAVA_TEST_ENV[@]}" mvn -B -q -DskipTests package ) \
    || { echo "mvn package -DskipTests 失败" >&2; exit 4; }
  [[ -f "$JAR" ]] || { echo "jar 未产出：$JAR" >&2; exit 4; }
  vlog "jar 构建完成"
}

# ---------------- app / worker 生命周期 ----------------
start_app() {
  nohup env SERVER_PORT="$WEB_PORT" SPRING_PROFILES_ACTIVE=dev APP_ENV=dev \
    SPRING_DATASOURCE_URL="jdbc:postgresql://127.0.0.1:${PG_PORT}/${ACCEPT_DB}" \
    SPRING_DATASOURCE_USERNAME="$PG_USER" SPRING_DATASOURCE_PASSWORD="$PG_PASSWORD" \
    APP_STORAGE_DEV_DIR="$STORAGE_ROOT" \
    java -jar "$JAR" >"$TMP/app.log" 2>&1 &
  echo $! > "$TMP/app.pid"
  local i
  for i in $(seq 1 120); do
    if curl -sS --noproxy '*' -o "$TMP/health" "$WEB/actuator/health" 2>/dev/null \
       && grep -q '"status":"UP"' "$TMP/health"; then return 0; fi
    sleep 1
  done
  tail -n 30 "$TMP/app.log"; fail "app 未在 120s 内 UP"
}
stop_app() {
  [[ -f "$TMP/app.pid" ]] || return 0
  local pid; pid=$(cat "$TMP/app.pid")
  kill "$pid" 2>/dev/null || true
  local i; for i in $(seq 1 30); do kill -0 "$pid" 2>/dev/null || break; sleep 1; done
  kill -9 "$pid" 2>/dev/null || true
  rm -f "$TMP/app.pid"
}
start_worker() { # <mode> <receipt> <tag>
  nohup env MVP_WORKER_PG_DSN="$B_DSN" MVP_NOTIFY_ENV=dev \
    MVP_NOTIFY_PUSH_DOUBLE="$1" MVP_NOTIFY_PUSH_RECEIPT="$2" \
    MVP_WORKER_HEALTH_PORT="$WORKER_PORT" MVP_WORKER_POLL_INTERVAL_SECONDS=1 \
    "$WPY" -m mvp_worker >"$TMP/worker-$3.log" 2>&1 &
  echo $! > "$TMP/worker.pid"
  local i
  for i in $(seq 1 60); do
    curl -sS --noproxy '*' -o /dev/null -w '%{http_code}' "http://127.0.0.1:${WORKER_PORT}/healthz" 2>/dev/null | grep -q 200 && return 0
    sleep 0.5
  done
  tail -n 20 "$TMP/worker-$3.log"; fail "worker healthz 未就绪"
}
stop_worker() {
  [[ -f "$TMP/worker.pid" ]] || return 0
  local pid; pid=$(cat "$TMP/worker.pid")
  kill "$pid" 2>/dev/null || true
  local i; for i in $(seq 1 40); do kill -0 "$pid" 2>/dev/null || break; sleep 0.5; done
  kill -9 "$pid" 2>/dev/null || true
  rm -f "$TMP/worker.pid"
}
worker_once() { # <mode> <receipt>
  local mode="$1" receipt="$2"; shift 2
  env MVP_WORKER_PG_DSN="$B_DSN" MVP_NOTIFY_ENV=dev "$@" \
    MVP_NOTIFY_PUSH_DOUBLE="$mode" MVP_NOTIFY_PUSH_RECEIPT="$receipt" \
    "$WPY" -m mvp_worker --once 2>&1
}
scanner_once() { env MVP_WORKER_PG_DSN="$B_DSN" MVP_NOTIFY_ENV=dev "$WPY" -m mvp_worker.scanners --once 2>&1; }

cleanup() {
  set +e
  stop_worker
  stop_app
  if [[ "${B_ACCEPT_KEEP_DB:-0}" == "1" ]]; then
    echo "B_ACCEPT_KEEP_DB=1 → 保留库 $ACCEPT_DB 与临时目录 $TMP"
  else
    docker exec -i "$PG" psql -U "$PG_USER" -d postgres -q >/dev/null 2>&1 <<SQL
SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname='$ACCEPT_DB' AND pid<>pg_backend_pid();
DROP DATABASE IF EXISTS $ACCEPT_DB;
SQL
    case "$TMP" in "$RUN_BASE"/b-accept-*) rm -rf "$TMP" ;; esac
    rmdir "$RUN_BASE" 2>/dev/null
  fi
}
trap cleanup EXIT

# ---------------- 登录 / 证明 / 素材 ----------------
APP_TOKEN=""; APP_ID=""; INST=""
G_TOKEN=""; G_ID=""
login_app() {
  local phone="$1" inst="$2"
  call POST "$WEB/api/v1/auth/sms-challenges" -H 'Content-Type: application/json' \
    -d "{\"phone\":\"$phone\",\"purpose\":\"login\"}"
  aeq "$CODE" 200 "sms-challenges"
  local chal; chal=$(jget data.challengeId) || fail "no challengeId"
  call POST "$WEB/api/v1/auth/sessions" -H 'Content-Type: application/json' \
    -d "{\"challengeId\":\"$chal\",\"code\":\"123456\",\"installationId\":\"$inst\"}"
  aeq "$CODE" 200 "sessions"
  APP_TOKEN=$(jget data.accessToken) || fail "no accessToken"
  APP_ID=$(jget data.accountId) || fail "no accountId"
  INST="$inst"
}
seed_gimbal() { psql_b "INSERT INTO gimbals (id,serial_no,auth_subject_ref,credential_version) VALUES (gen_random_uuid(),'$1','$2',$3) RETURNING id"; }
gimbal_login() {
  call POST "$WEB/api/v1/gimbal-sessions" -H 'Content-Type: application/json' \
    -d "{\"credential\":\"$1\",\"credentialVersion\":\"$2\",\"proof\":\"p\"}"
  aeq "$CODE" 200 "gimbal-sessions"
  G_TOKEN=$(jget data.sessionToken) || fail "no gimbal token"
  G_ID=$(jget data.gimbalId) || fail "no gimbalId"
}
make_face() {
  "$CPY" - "$1" "$2" <<'PY'
import sys
hdr=bytes([0x89,0x50,0x4E,0x47,0x0D,0x0A,0x1A,0x0A])
open(sys.argv[1],'wb').write(hdr+sys.argv[2].encode())
PY
}
write_meta() {
  printf '{"capture":{"captureId":"%s","capturedAt":"2026-09-11T10:00:00Z","clientContinuityId":"cont-%s","purpose":"grant"},"consentEvidenceRef":"%s"%s}' \
    "$2" "$2" "$3" "${4:-}" > "$1"
}
seed_member() {
  local ref id; ref=$($HELP sha256 "$1")
  id=$(psql_b "INSERT INTO members (id,identity_namespace,face_subject_ref) VALUES (gen_random_uuid(),'mvp-local','$ref') RETURNING id")
  printf '%s' "$id"
}
pairing_proof() {
  printf '{"purpose":"pairing","gimbalId":"%s","accountId":"%s","installationId":"%s","microcrystalSerial":null,"observerType":null,"observerRef":null}' \
    "$1" "$2" "$3" | $HELP proof
}
tamper_proof() {
  local p="$1"
  local last="${p: -1}"
  if [[ "$last" == "A" ]]; then printf '%sB' "${p%?}"; else printf '%sA' "${p%?}"; fi
}
connection_proof_app() {
  printf '{"purpose":"connection","gimbalId":null,"accountId":"%s","installationId":"%s","microcrystalSerial":"%s","observerType":"app_account","observerRef":"%s:%s"}' \
    "$1" "$2" "$3" "$1" "$2" | $HELP proof
}
post_grant() {
  op_call m1A01CreateMemberAccessGrant POST "$WEB/api/v1/member-access-grants" \
    -H "Authorization: Bearer $1" -H "Idempotency-Key: $2" \
    -F "metadata=@$4;type=application/json" -F "face=@$3;type=image/png"
}
list_grants() {
  if [[ -n "${2:-}" ]]; then
    op_call m1A02ListMemberAccessGrants GET "$WEB/api/v1/me/member-access-grants" \
      -H "Authorization: Bearer $1" --get --data-urlencode "cursor=$2"
  else
    op_call m1A02ListMemberAccessGrants GET "$WEB/api/v1/me/member-access-grants" -H "Authorization: Bearer $1"
  fi
}
hb_op() {
  local incidents="${5:-[]}"
  local body="{\"observationEpoch\":\"$3\",\"observationSeq\":\"$4\",\"observedAt\":\"$(date -u +%Y-%m-%dT%H:%M:%SZ)\",\"powerState\":\"awake\",\"incidents\":$incidents}"
  op_call m2A02ReportGimbalHeartbeat POST "$WEB/api/v1/gimbals/$2/heartbeats" \
    -H "Authorization: Bearer $1" -H 'Content-Type: application/json' -d "$body"
}
t03snap() { psql_b "SELECT coalesce(last_seen_at::text,'NULL'),status_revision,latest_observation::text,connection_status FROM gimbals WHERE id='$1'"; }

source "$SUPPORT/b-checks-1.sh"
source "$SUPPORT/b-checks-2.sh"
source "$SUPPORT/b-checks-3.sh"

# =====================================================================
# 主流程
# =====================================================================
preflight
start_app
vlog "app UP @$WEB"

maybe_check b1  "M1-A01 有效主体 201 精确字段 + T13 链接" b01
maybe_check b2  "M1-A01 无效主体 403/401/400/FACE_NOT_VERIFIED 零副作用" b02
maybe_check b3  "M1-A02 active-only + 分页 + 403 + 非法 cursor 400" b03
maybe_check b4  "M1-A03 撤销 204/重复不变/他人与不存在 404 一致/缺幂等键 400" b04
maybe_check b5  "M2-A01 合法凭据 200、错凭据/代次 401、T03 未变" b05
maybe_check b6  "M2-A02 心跳 accepted + APP 403 + 他人/不存在 404 一致" b06
maybe_check b7  "M2-A03 绑定/自身 200、其他/不存在 404、isStale、GET 无副作用" b07
maybe_check b8  "M2-A04 观察 accepted + 整数 schema_version + 旧 seq 不覆盖" b08
maybe_check b9  "M2-A05 能力字段集合 + 未观察 403 + 他人/不存在 404 一致" b09
maybe_check b10 "M2-A06 绑定/竞争 409/坏证明 403/缺字段 400" b10
maybe_check b11 "M2-A07 unbound/self/other + other 仅两字段 + 缺头 400" b11
maybe_check b12 "M2-A08 解绑 null/+1、重复不递增、他人绑定完好" b12
maybe_check b13 "M5-A01 首登三字段 + 整数版本 + 路径不符 403 + 无 token 401" b13
maybe_check b15 "A/B 真实并发绑定：恰一 200 一 409，DB rev=1" b15
maybe_check b16 "旧解绑不得解除新绑定（409/404 + B 完好）" b16
maybe_check b17 "报告公开引用图片：active 授权 APP 200 正确字节 + no-store/nosniff" b17
maybe_check b18 "撤销后 404 与不存在一致；媒体行保留" b18
maybe_check b19 "旧授权请求重放 403 GRANT_REVOKED；新键 201；旧行保留" b19
maybe_check b20 "face/核验用途永不放行；冻结报告 images[] 未引用→404 / 引用→200" b20
maybe_check b21 "云台仅当前任务图片：切换 current_assessment 后 404" b21
maybe_check b22 "心跳 seq 顺序：旧/重复 accepted=false 且逐列未变" b22
maybe_check b23 "epoch 权威=服务端会话代次：同代次换 epoch 降 seq 拒绝；两个并存会话交替时旧会话永不重获权威；凭据代次推进后才重置" b23
maybe_check b24 "episode 稳定性：复用 / 清除 resolved / 再报新 id" b24
maybe_check b25 "worker SIGTERM 重启：任务不丢、租约回收、收敛且不重复" b25
maybe_check b26 "C7：扫描前后 last_seen_at 不变 + 源码无写入" b26
maybe_check b27 "扫描→通知→真实 worker：submitted 与 delivered 可区分" b27
maybe_check b28 "无绑定不通知（T10 零行 + skipped_unbound）" b28
maybe_check b29 "无有效目标不假装成功（T10 零行 + skipped_no_destination）" b29
maybe_check b30 "解绑后不误发：cancelled + route_recheck_failed + 推送 0" b30
maybe_check b31 "换号后旧通知 cancelled 不误发；新路由可建通知" b31
maybe_check b32 "transient 退避；重试前改绑 → cancelled 不投递" b32
maybe_check b33 "unknown：非末次保持可观测态 / 对账收敛 submitted 不重发 / 同 key 重发 / 末次同事务收敛 T10+T12" b33
maybe_check b34 "通知内容合规：T10 payload 与推送内容均不含敏感项" b34
maybe_check b35 "同 T12 二次领取不重复投递；扫描两轮 T10 行数不变" b35
maybe_check b36 "Java 全量 mvn -B test：Failures 0 / Errors 0" b36
maybe_check b37 "Python 全量 pytest：0 failed / 0 errors（合并 8afd0e5 后 test_sanity 已通过）" b37
maybe_check b38 "注册含两类；违规 payload → failed/UNSUPPORTED_CONTRACT 不循环" b38
maybe_check b39 "运行前后 git status 无 tracked 业务文件被改（HEAD 不变）" b39
maybe_check b14 "契约驱动：错误信封形状 + 每端点码白名单（全量观测）" b14_contract

# =====================================================================
# 汇总
# =====================================================================
echo
printf '%s===== run-acceptance-b 汇总（db=%s）=====%s\n' "$C_B" "$ACCEPT_DB" "$C_0"
printf '%-5s | %-62s | %-6s\n' "CHECK" "DESC" "RES"
printf '%.0s-' {1..82}; echo
pass_n=0; fail_n=0; blocked_n=0
for row in "${RESULTS[@]}"; do
  IFS='|' read -r id desc st ev <<<"$row"
  case "$st" in
    PASS) pass_n=$((pass_n+1)); printf '%-5s | %-62s | %sPASS%s\n' "$id" "$desc" "$C_G" "$C_0" ;;
    FAIL) fail_n=$((fail_n+1)); printf '%-5s | %-62s | %sFAIL%s\n' "$id" "$desc" "$C_R" "$C_0" ;;
    BLOCKED) blocked_n=$((blocked_n+1)); printf '%-5s | %-62s | %sBLOCKED%s\n' "$id" "$desc" "$C_Y" "$C_0" ;;
  esac
done
printf '%.0s-' {1..82}; echo
total=$(( pass_n + fail_n + blocked_n ))
if [[ $fail_n -eq 0 && $blocked_n -eq 0 ]]; then
  printf '%sRESULT: ALL PASS（%d/%d）%s\n' "$C_G" "$pass_n" "$total" "$C_0"
else
  printf '%sRESULT: %d PASS / %d FAIL / %d BLOCKED (total %d)%s\n' "$C_R" "$pass_n" "$fail_n" "$blocked_n" "$total" "$C_0"
fi
printf '%sALL PASS %d/%d%s\n' "$C_G" "$pass_n" "$total" "$C_0"
exit $overall_rc
