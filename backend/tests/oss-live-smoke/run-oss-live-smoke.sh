#!/usr/bin/env bash
# B 真实 OSS 跨语言 smoke 驱动（root-only）。
#
# 默认 --dry-run：两侧都用**本地文件系统替身**共享同一 root，跑完整的两进程、两语言闭环
#   （Java 写 → Python 逐字节校验 → Python 写 → Java 校验 → 精确删除 → 两侧交叉确认不存在），
#   **绝不联网、绝不需要任何凭据**。
# --live：两侧都用**当前生产适配器**（Java OssStorageAdapter / Python AliyunOssStorage）对真实
#   阿里云 OSS 跑同一闭环。需要四道门（见下），且只由根执行。
#
# 四道门（--live 必须全部满足，任一不满足立即退出，绝不静默通过）：
#   1) 显式 --live（与 --dry-run 互斥）
#   2) 环境变量 OSS_LIVE_SMOKE=true（驱动级；本脚本绝不自动设置它）
#   3) --config 指向可读的私有 UTF-8 YAML，且该文件**不在工作树内**、
#      app.storage.provider=aliyun、必填键齐备（校验只输出键名，绝不输出值）
#   4) 两侧各自的三重 opt-in（Java -Dapp.oss.live-smoke=true / Python MVP_OSS_LIVE_SMOKE=true，
#      由本脚本在门 1-3 通过后代为传递；详见 contract.md §5）
#
# 输出纪律：本脚本与两侧子进程**都不得**输出 AK/SK/STS、bucket 名、endpoint、完整 objectKey
#   或对象内容；只输出阶段、结果、净化后的 SDK code/requestId、字节数、内容 sha256 前 12 位、
#   keyDigest（sha256(objectKey) 前 12 位）。清理失败时完整键写入 0600 文件（git 忽略目录），
#   stdout 只给该文件路径与 keyDigest。
#
# 已知披露：完整 objectKey 会作为子进程 argv 出现（同机同用户可见）。它是本次随机生成的
#   合成键（<env>/assessment_result/<uuid>，不含任何用户数据），非秘密；bucket 与凭据从不入 argv。
#
# 用法：
#   backend/tests/oss-live-smoke/run-oss-live-smoke.sh --dry-run
#   OSS_LIVE_SMOKE=true backend/tests/oss-live-smoke/run-oss-live-smoke.sh \
#       --live --config /abs/path/to/application-local.yml [--env dev] [--content-bytes 256]
#
# 退出码：0 = 全部阶段通过且清理已确认；1 = 有阶段失败或清理未确认；2 = 用法/前置门失败。
set -uo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
REPO="$(cd -- "$SCRIPT_DIR/../../.." && pwd)"
SUPPORT="$REPO/backend/tests/support"
WORK="$REPO/.coordination/B-work/oss-live-smoke"
JAVA_DIR="$REPO/backend/web-java"
PY_DIR="$REPO/backend/worker-python"
VPY="$PY_DIR/.venv/bin/python"
JAVA_RUNNER_CLASS="cn.yuanxin.mvp.web.storage.OssLiveSmokeRunner"
JAVA_RUNNER_SRC="$JAVA_DIR/src/test/java/cn/yuanxin/mvp/web/storage/OssLiveSmokeRunner.java"
PY_RUNNER="$PY_DIR/tests/oss_live_smoke.py"
CP_FILE="$WORK/cp.txt"
RUNNER_LOG="$WORK/driver-last-run.log"

MODE="double"; LIVE=0; DRY=0; CONFIG=""; ENV_NAME="dev"; CONTENT_BYTES=256; SKIP_BUILD=0
FAILURES=0; CLEANUP_STATE="not-run"; KEY_A=""; KEY_B=""; SEED=""; KD_A=""; KD_B=""; DOUBLE_ROOT=""
SUMMARY=()

die()  { printf '[oss-smoke-driver] FATAL: %s\n' "$*" >&2; exit 2; }
note() { printf '[oss-smoke-driver] %s\n' "$*" | tee -a "$RUNNER_LOG"; }
usage() { sed -n '2,33p' "${BASH_SOURCE[0]}" | sed 's/^#\{1,\} \{0,1\}//'; }

# ── 参数 ─────────────────────────────────────────────────────────────────────
while [ $# -gt 0 ]; do
  case "$1" in
    --dry-run)       DRY=1 ;;
    --live)          LIVE=1 ;;
    --config)        [ $# -ge 2 ] || die "--config needs a value"; CONFIG="$2"; shift ;;
    --env)           [ $# -ge 2 ] || die "--env needs a value"; ENV_NAME="$2"; shift ;;
    --content-bytes) [ $# -ge 2 ] || die "--content-bytes needs a value"; CONTENT_BYTES="$2"; shift ;;
    --skip-build)    SKIP_BUILD=1 ;;
    -h|--help)       usage; exit 0 ;;
    *)               die "unknown argument: $1 (see --help)" ;;
  esac
  shift
done

mkdir -p "$WORK" || die "cannot create the work directory"
: > "$RUNNER_LOG"

# ── 门 1：互斥 ───────────────────────────────────────────────────────────────
if [ "$LIVE" -eq 1 ] && [ "$DRY" -eq 1 ]; then die "--live and --dry-run are mutually exclusive"; fi
if [ "$LIVE" -eq 1 ]; then MODE="live"; else MODE="double"; fi

# ── 门 2/3：live 的额外前置 ──────────────────────────────────────────────────
if [ "$LIVE" -eq 1 ]; then
  [ "${OSS_LIVE_SMOKE:-}" = "true" ] || die "refusing --live: export OSS_LIVE_SMOKE=true to opt in explicitly"
  [ -n "$CONFIG" ] || die "refusing --live: --config <private UTF-8 YAML> is required"
  [ -f "$CONFIG" ] && [ -r "$CONFIG" ] || die "refusing --live: --config is not a readable file"
  case "$(cd -- "$(dirname -- "$CONFIG")" 2>/dev/null && pwd)" in
    "$REPO"*) die "refusing --live: the private config must NOT live inside the worktree" ;;
  esac
  note "live mode: validating the private config (key NAMES only; values are never printed)"
  if ! python3 "$SUPPORT/oss-smoke-config.py" --config "$CONFIG" --check | tee -a "$RUNNER_LOG"; then
    die "refusing --live: config validation failed (provider must be aliyun and required keys present)"
  fi
else
  if [ "${OSS_LIVE_SMOKE:-}" = "true" ]; then
    die "refusing --dry-run: OSS_LIVE_SMOKE=true is set (unset it, or use --live)"
  fi
  note "dry-run mode: both sides use local filesystem doubles on a shared root; NO network, NO credentials"
fi

# ── 键与内容种子（合成、随机、无用户数据）────────────────────────────────────
read -r UUID_A UUID_B SEED <<<"$(python3 -c 'import uuid;print(uuid.uuid4(),uuid.uuid4(),uuid.uuid4())')"
KEY_A="$ENV_NAME/assessment_result/$UUID_A"
KEY_B="$ENV_NAME/assessment_result/$UUID_B"
digest() { python3 -c 'import hashlib,sys;print(hashlib.sha256(sys.argv[1].encode()).hexdigest()[:12])' "$1"; }
KD_A="$(digest "$KEY_A")"; KD_B="$(digest "$KEY_B")"
note "env=$ENV_NAME purpose=assessment_result contentBytes=$CONTENT_BYTES mode=$MODE"
note "keyA digest=$KD_A   keyB digest=$KD_B   seed digest=$(digest "$SEED")   (full keys are never printed)"

# ── dry-run 的共享 root（放在 git 忽略目录，不用 /tmp）───────────────────────
if [ "$LIVE" -eq 0 ]; then
  DOUBLE_ROOT="$WORK/dry-run-root-$(date -u +%Y%m%dT%H%M%SZ)-$$"
  mkdir -p "$DOUBLE_ROOT" || die "cannot create the shared dry-run root"
  note "shared dry-run root prepared under .coordination/B-work (git-ignored)"
fi

# ── 子进程公共参数（用数组，避免嵌套引号分词问题）────────────────────────────
EXTRA=()
if [ -n "$DOUBLE_ROOT" ]; then EXTRA+=(--double-root "$DOUBLE_ROOT"); fi
if [ -n "$CONFIG" ]; then EXTRA+=(--config "$CONFIG"); fi

run_java() { # phase key
  note "--- phase=$1 side=java ---"
  # shellcheck disable=SC2086
  java -cp "$JAVA_CP" $JAVA_LIVE_SYSPROP "$JAVA_RUNNER_CLASS" \
    --mode "$MODE" --phase "$1" --object-key "$2" \
    --content-seed "$SEED" --content-bytes "$CONTENT_BYTES" \
    ${EXTRA[@]+"${EXTRA[@]}"} 2>&1 | tee -a "$RUNNER_LOG"
  return "${PIPESTATUS[0]}"
}
run_python() { # phase key
  note "--- phase=$1 side=python ---"
  "$VPY" "$PY_RUNNER" \
    --mode "$MODE" --phase "$1" --object-key "$2" \
    --content-seed "$SEED" --content-bytes "$CONTENT_BYTES" \
    ${EXTRA[@]+"${EXTRA[@]}"} 2>&1 | tee -a "$RUNNER_LOG"
  return "${PIPESTATUS[0]}"
}
last_result() { grep -o 'result=[a-z]*' "$RUNNER_LOG" | tail -1 | cut -d= -f2; }

phase() { # label side key acceptable-csv
  local label="$1" side="$2" key="$3" accept="$4" rc=0 res="" ok=1
  if [ "$side" = java ]; then run_java "$label" "$key"; else run_python "$label" "$key"; fi
  rc=$?
  res="$(last_result)"; [ -n "$res" ] || res="<none>"
  case ",$accept," in *",$res,"*) ok=0 ;; esac
  if [ "$rc" -ne 0 ] || [ "$ok" -ne 0 ]; then
    FAILURES=$((FAILURES+1)); SUMMARY+=("FAIL phase=$label side=$side rc=$rc result=$res (accepted: $accept)")
    note "PHASE FAILED: label=$label side=$side rc=$rc result=$res"
  else
    SUMMARY+=("ok   phase=$label side=$side rc=$rc result=$res")
    note "phase ok: label=$label side=$side result=$res"
  fi
}

# ── 清理（EXIT trap：无论前面成败都执行；只删这两个精确键）────────────────────
cleanup() {
  local bad=0 final=1
  note "--- cleanup (always runs; deletes ONLY the two generated keys; no list/no bucket ops) ---"
  if [ -n "$KEY_A" ] && [ -n "$JAVA_CP" ]; then
    run_java   delete        "$KEY_A" >/dev/null 2>&1 || bad=1
    run_python delete        "$KEY_B" >/dev/null 2>&1 || bad=1
    run_python confirm-absent "$KEY_A" >/dev/null 2>&1 || bad=1   # 交叉确认（4 次）
    run_java   confirm-absent "$KEY_B" >/dev/null 2>&1 || bad=1
    run_python confirm-absent "$KEY_B" >/dev/null 2>&1 || bad=1
    run_java   confirm-absent "$KEY_A" >/dev/null 2>&1 || bad=1
  elif [ -n "$KEY_A" ]; then
    bad=1; note "cleanup could not run: the Java classpath was never resolved"
  fi
  if [ "$bad" -eq 0 ]; then
    CLEANUP_STATE="confirmed"; note "cleanup=confirmed (both sides confirmed both keys absent)"
  else
    CLEANUP_STATE="FAILED"
    local f="$WORK/cleanup-FAILED-$(date -u +%Y%m%dT%H%M%SZ).txt"
    ( umask 077; printf 'keyA=%s\nkeyB=%s\nseed=%s\nmode=%s\n' "$KEY_A" "$KEY_B" "$SEED" "$MODE" > "$f" )
    note "cleanup=FAILED full keys written to a 0600 file (NOT printed here): $f"
    note "cleanup=FAILED keyA digest=$KD_A keyB digest=$KD_B (delete these two objects manually)"
  fi
  if [ "$LIVE" -eq 0 ] && [ -n "$DOUBLE_ROOT" ] && [ -d "$DOUBLE_ROOT" ]; then
    rm -rf "$DOUBLE_ROOT"; note "shared dry-run root removed"
  fi
  if [ "$FAILURES" -eq 0 ] && [ "$CLEANUP_STATE" = "confirmed" ]; then final=0; fi
  note "RESULT=$([ "$final" -eq 0 ] && echo PASS || echo FAIL) failures=$FAILURES cleanup=$CLEANUP_STATE"
  local line
  for line in ${SUMMARY[@]+"${SUMMARY[@]}"}; do note "  $line"; done
  exit "$final"     # 显式 exit：清理未确认时即使阶段全过也必须非 0
}
trap cleanup EXIT INT TERM

# ── 构建（Java runner 在 test sources，需要 test-classes 与依赖 classpath）────
[ -f "$JAVA_RUNNER_SRC" ] || die "Java runner not found (is the Java lane delivered?): $JAVA_RUNNER_SRC"
[ -f "$PY_RUNNER" ]       || die "Python runner not found (is the Python lane delivered?): $PY_RUNNER"
[ -x "$VPY" ]             || die "worker venv python not found: $VPY"
JAVA_CP=""; JAVA_LIVE_SYSPROP=""
if [ "$SKIP_BUILD" -eq 0 ]; then
  note "building Java test classes (mvn -q test-compile) ..."
  if ! ( cd "$JAVA_DIR" && MAVEN_OPTS="${MAVEN_OPTS:--Xmx768m -XX:MaxMetaspaceSize=320m}" \
         mvn -B -q test-compile ) >>"$WORK/build.log" 2>&1; then
    tail -25 "$WORK/build.log" >&2; die "mvn test-compile failed (see $WORK/build.log)"
  fi
  if ! ( cd "$JAVA_DIR" && mvn -B -q dependency:build-classpath -Dmdep.outputFile="$CP_FILE" ) >>"$WORK/build.log" 2>&1; then
    tail -25 "$WORK/build.log" >&2; die "mvn dependency:build-classpath failed"
  fi
fi
[ -f "$CP_FILE" ] || die "classpath file missing: $CP_FILE (drop --skip-build)"
JAVA_CP="$JAVA_DIR/target/classes:$JAVA_DIR/target/test-classes:$(cat "$CP_FILE")"

# ── live：把私有 YAML 翻译成 Python 侧环境变量（值只进本进程环境，绝不打印/落盘）─
if [ "$LIVE" -eq 1 ]; then
  set +x
  if ! eval "$(python3 "$SUPPORT/oss-smoke-config.py" --config "$CONFIG" --emit shell)"; then
    die "failed to translate the private YAML into Python-side env vars"
  fi
  export MVP_OSS_LIVE_SMOKE=true
  JAVA_LIVE_SYSPROP="-Dapp.oss.live-smoke=true"
  note "python-side env exported in-process (values never printed, never written to disk)"
fi

# ── 阶段序列（契约 §3）───────────────────────────────────────────────────────
if [ "$LIVE" -eq 1 ]; then PROBE_ACCEPT="ok"; else PROBE_ACCEPT="ok,skipped"; fi
phase write            java   "$KEY_A" "ok"
phase verify           python "$KEY_A" "ok"
phase write            python "$KEY_B" "ok"
phase verify           java   "$KEY_B" "ok"
phase public-url-probe java   "$KEY_A" "$PROBE_ACCEPT"
