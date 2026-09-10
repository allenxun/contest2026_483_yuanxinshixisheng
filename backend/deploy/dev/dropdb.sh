#!/usr/bin/env bash
# 删除隔离容器中的数据库（终止连接后 DROP）：./dropdb.sh <dbname>
set -euo pipefail
CONTAINER="${MVP_A_PG_CONTAINER:-mvp-a-pg}"
DB="${1:?usage: dropdb.sh <dbname>}"
[[ "$DB" =~ ^[a-z_][a-z0-9_]*$ ]] || { echo "invalid db name: $DB" >&2; exit 1; }
[[ "$DB" == "postgres" ]] && { echo "refusing to drop postgres" >&2; exit 1; }
docker exec -i "$CONTAINER" psql -U postgres -d postgres -q -v ON_ERROR_STOP=1 <<SQL
SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname='$DB' AND pid<>pg_backend_pid();
DROP DATABASE IF EXISTS $DB;
SQL
echo "database $DB dropped"
