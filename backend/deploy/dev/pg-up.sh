#!/usr/bin/env bash
# 幂等启动本 worktree 隔离的 PostgreSQL 16 容器（仅绑定 127.0.0.1:55432，绝不影响共享 5432）。
# 规格与已准备容器一致：name=mvp-a-pg image=postgres:16 user=postgres password=mvp_a_local。
set -euo pipefail

CONTAINER="${MVP_A_PG_CONTAINER:-mvp-a-pg}"
PORT="${MVP_A_PG_HOST_PORT:-55432}"
IMAGE="postgres:16"
PASSWORD="${MVP_A_PG_PASSWORD:-mvp_a_local}"

if docker ps --format '{{.Names}}' | grep -qx "$CONTAINER"; then
  echo "container $CONTAINER already running"
  exit 0
fi

if docker ps -a --format '{{.Names}}' | grep -qx "$CONTAINER"; then
  docker start "$CONTAINER" >/dev/null
  echo "container $CONTAINER started"
else
  if ss -lnt 2>/dev/null | awk '{print $4}' | grep -Eq "[:.]${PORT}\$"; then
    echo "ERROR: port 127.0.0.1:${PORT} already in use by another process (worktree isolation!)" >&2
    exit 1
  fi
  docker run -d --name "$CONTAINER" \
    -e POSTGRES_USER=postgres \
    -e POSTGRES_PASSWORD="$PASSWORD" \
    -p "127.0.0.1:${PORT}:5432" \
    -v "${CONTAINER}-data:/var/lib/postgresql/data" \
    "$IMAGE" >/dev/null
  echo "container $CONTAINER created and started"
fi

echo -n "waiting for pg_isready ... "
for _ in $(seq 1 30); do
  if docker exec "$CONTAINER" pg_isready -U postgres -d postgres >/dev/null 2>&1; then
    echo "ok (127.0.0.1:${PORT})"
    exit 0
  fi
  sleep 1
done
echo "TIMEOUT" >&2
exit 1
