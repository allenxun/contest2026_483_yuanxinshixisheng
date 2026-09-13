#!/usr/bin/env bash
#
# Idempotent deploy for InsightFace-for-openvela as a USER-level systemd unit.
#
# This script contains NO secrets.  All secret material is read at runtime from
# a 0600 env file / token file outside the repository.
#
# Prerequisite (verified below, not enabled here): user linger must be on so the
# service survives logout/reboot:
#     loginctl show-user "$USER" -p Linger   # must print Linger=yes
#
set -euo pipefail

UNIT_NAME="InsightFace-for-openvela"
SERVICE_DIR="${SERVICE_DIR:-$HOME/deployment/InsightFace-for-openvela}"
ENV_FILE="${FACE_SVC_ENV_FILE:-$HOME/.config/face-service-openvela.env}"
UNIT_SRC="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/${UNIT_NAME}.service"
UNIT_DST="$HOME/.config/systemd/user/${UNIT_NAME}.service"
DATA_DIR="$SERVICE_DIR/data"
UV_BIN="${UV_BIN:-$HOME/.local/bin/uv}"
HEALTH_TIMEOUT="${HEALTH_TIMEOUT:-60}"

log()  { printf '[deploy] %s\n' "$*"; }
fail() { printf '[deploy][ERROR] %s\n' "$*" >&2; }
rollback_hint() {
  cat >&2 <<EOF
[deploy] Rollback / cleanup:
    systemctl --user disable --now ${UNIT_NAME}
    rm -f ${UNIT_DST}
    systemctl --user daemon-reload
EOF
}
trap 'rc=$?; if [ $rc -ne 0 ]; then fail "deploy failed (rc=$rc)"; rollback_hint; fi; exit $rc' EXIT

# --- 1. prerequisites ----------------------------------------------------
if ! command -v loginctl >/dev/null 2>&1; then
  fail "loginctl not found; cannot verify linger"
  exit 1
fi
linger="$(loginctl show-user "$USER" -p Linger 2>/dev/null || true)"
if [ "$linger" != "Linger=yes" ]; then
  fail "user linger is not enabled (got '${linger:-<empty>}'). Run: loginctl enable-linger $USER"
  exit 1
fi
log "linger: ok"

if [ ! -x "$UV_BIN" ]; then
  fail "uv not found/executable at $UV_BIN (set UV_BIN=...)"
  exit 1
fi

if [ ! -f "$UNIT_SRC" ]; then
  fail "unit template missing: $UNIT_SRC"
  exit 1
fi

if [ ! -d "$SERVICE_DIR" ]; then
  fail "service dir not found: $SERVICE_DIR"
  exit 1
fi

if [ "$SERVICE_DIR" != "$HOME/deployment/${UNIT_NAME}" ]; then
  fail "this unit expects SERVICE_DIR=$HOME/deployment/${UNIT_NAME} (got $SERVICE_DIR)"
  fail "move the checkout or edit the unit template accordingly"
  exit 1
fi

# --- 2. env file + token (no secrets in this script) ---------------------
if [ ! -f "$ENV_FILE" ]; then
  fail "env file missing: $ENV_FILE"
  fail "create it at 0600 from the public example:"
  fail "    install -m 0600 $SERVICE_DIR/.env.example $ENV_FILE"
  exit 1
fi
env_mode="$(stat -c '%a' "$ENV_FILE")"
if [ "$env_mode" != "600" ]; then
  fail "env file $ENV_FILE must be 0600 (got $env_mode): chmod 600 $ENV_FILE"
  exit 1
fi

env_val() {
  # Safe read: extract KEY=VALUE without sourcing the file.
  awk -F= -v k="$1" '$1==k {sub(/^[^=]*=/, ""); print; exit}' "$ENV_FILE"
}

auth_required="$(env_val FACE_SVC_AUTH_REQUIRED)"
# The service default is fail-closed true; treat an unset value as true so the
# token-presence check below still runs.
if [ -z "$auth_required" ]; then
  auth_required="true"
fi
token_file="$(env_val FACE_SVC_INTERNAL_TOKEN_FILE)"
if [ "$auth_required" = "true" ]; then
  if [ -z "$token_file" ] || [ ! -f "$token_file" ]; then
    fail "FACE_SVC_AUTH_REQUIRED=true but token file is missing: ${token_file:-<unset>}"
    fail "generate it (do not print/copy the value):"
    fail "    openssl rand -hex 32 > ${token_file:-$HOME/.config/face-service-openvela.token}"
    fail "    chmod 600 ${token_file:-$HOME/.config/face-service-openvela.token}"
    exit 1
  fi
  tok_mode="$(stat -c '%a' "$token_file")"
  if [ "$tok_mode" != "600" ]; then
    fail "token file $token_file must be 0600 (got $tok_mode)"
    exit 1
  fi
  log "auth: enabled, token file present (0600)"
else
  log "auth: disabled (FACE_SVC_AUTH_REQUIRED != true)"
fi

# --- 3. dependencies -----------------------------------------------------
log "running uv sync --frozen in $SERVICE_DIR"
( cd "$SERVICE_DIR" && "$UV_BIN" sync --frozen )

# --- 4. data dirs (restricted permissions) -------------------------------
install -d -m 0700 "$DATA_DIR"
install -d -m 0750 "$SERVICE_DIR/logs"
log "data dir: $DATA_DIR (0700)"

# --- 5. install unit -----------------------------------------------------
install -d -m 0755 "$HOME/.config/systemd/user"
install -m 0644 "$UNIT_SRC" "$UNIT_DST"
log "installed unit: $UNIT_DST"

# --- 6. (re)start --------------------------------------------------------
# NOTE: `systemctl enable --now` does **not** restart an already-running unit,
# so a redeploy would silently keep the OLD code in memory while the script
# reported success (observed in practice: new source on disk, old PID serving,
# pre-fix access-log behaviour still present).  Therefore: always `restart`,
# and assert the main PID actually changed when the unit was already active.
systemctl --user daemon-reload
PREV_ACTIVE="$(systemctl --user is-active "$UNIT_NAME" 2>/dev/null || true)"
PREV_PID="$(systemctl --user show "$UNIT_NAME" -p ExecMainPID --value 2>/dev/null || true)"
systemctl --user enable "$UNIT_NAME"
systemctl --user restart "$UNIT_NAME"
NEW_PID="$(systemctl --user show "$UNIT_NAME" -p ExecMainPID --value 2>/dev/null || true)"
if [ "$PREV_ACTIVE" = "active" ] && [ -n "$PREV_PID" ] && [ "$PREV_PID" != "0" ] \
   && [ "$NEW_PID" = "$PREV_PID" ]; then
  fail "unit was NOT restarted (ExecMainPID unchanged: $PREV_PID); old code may still be serving"
  exit 1
fi
log "service enabled and restarted (previous pid=${PREV_PID:-none} -> current pid=${NEW_PID:-unknown})"

# --- 7. health check -----------------------------------------------------
HOST="$(env_val FACE_SVC_HOST)"; HOST="${HOST:-10.3.6.163}"
PORT="$(env_val FACE_SVC_PORT)"; PORT="${PORT:-8010}"
HEALTH_URL="http://${HOST}:${PORT}/v1/health"

fetch_health() {
  if command -v curl >/dev/null 2>&1; then
    curl -fsS --max-time 5 "$HEALTH_URL"
  else
    python3 - "$HEALTH_URL" <<'PY'
import sys, urllib.request
with urllib.request.urlopen(sys.argv[1], timeout=5) as r:
    sys.stdout.write(r.read().decode("utf-8"))
PY
  fi
}

deadline=$(( $(date +%s) + HEALTH_TIMEOUT ))
health=""
while [ "$(date +%s)" -lt "$deadline" ]; do
  if health="$(fetch_health 2>/dev/null)"; then
    break
  fi
  sleep 2
done

if [ -z "$health" ]; then
  fail "health check did not succeed within ${HEALTH_TIMEOUT}s at $HEALTH_URL"
  journalctl --user -n 30 -u "$UNIT_NAME" 2>/dev/null || true
  exit 1
fi

# Sanitized output: no token, no image/embedding data.
python3 - "$health" <<'PY'
import json, sys
d = json.loads(sys.argv[1])
print("[deploy] health: status=%s model_loaded=%s model_version=%s library_revision=%s liveness_supported=%s"
      % (d.get("status"), d.get("model_loaded"), d.get("model_version"),
         d.get("library_revision"), d.get("liveness", {}).get("supported")))
PY
log "deploy complete"
