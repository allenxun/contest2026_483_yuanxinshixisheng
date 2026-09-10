#!/usr/bin/env bash
# 在隔离容器中创建数据库：./createdb.sh <dbname>（幂等：已存在则跳过）。
set -euo pipefail
CONTAINER="${MVP_A_PG_CONTAINER:-mvp-a-pg}"
DB="${1:?usage: createdb.sh <dbname>}"
[[ "$DB" =~ ^[a-z_][a-z0-9_]*$ ]] || { echo "invalid db name: $DB (只允许小写字母/数字/下划线)" >&2; exit 1; }
if docker exec "$CONTAINER" psql -U postgres -d postgres -tAc \
     "SELECT 1 FROM pg_database WHERE datname='$DB'" | grep -q 1; then
  echo "database $DB already exists"
else
  docker exec "$CONTAINER" psql -U postgres -d postgres -c "CREATE DATABASE $DB"
  echo "database $DB created"
fi
