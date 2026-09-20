#!/usr/bin/env bash
# 在隔离容器内运行 psql。参数透传，例如：
#   ./pg-psql.sh -d mvp_a_dev -c '\dt'
#   ./pg-psql.sh -d mvp_a_dev -c 'SELECT 1'
# 默认连 postgres 库、user postgres。
set -euo pipefail

CONTAINER="${MVP_A_PG_CONTAINER:-mvp-a-pg}"
DB="${1:-postgres}"
# 若第一个参数不是已知 DB 名（以 - 开头视为已传 -d/-c 等），直接透传。
if [[ "$DB" == -* ]]; then
  exec docker exec -i "$CONTAINER" psql -U postgres "$@"
fi
shift 2>/dev/null || true
exec docker exec -i "$CONTAINER" psql -U postgres -d "$DB" "$@"
