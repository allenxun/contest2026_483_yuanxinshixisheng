#!/usr/bin/env bash
# 对目标库运行 Flyway 迁移：./migrate.sh <dbname>
# 实现：flyway-maven-plugin（版本 = Spring Boot BOM 的 ${flyway.version}，在 web-java/pom.xml 锁定），
# 与应用内 Flyway 完全同版本 → 唯一迁移入口，Python 永不迁移。
# 连接信息 env 可覆盖：MVP_A_PG_HOST_PORT(55432) / MVP_A_PG_USER(postgres) / MVP_A_PG_PASSWORD(mvp_a_local)。
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DB="${1:?usage: migrate.sh <dbname>}"
[[ "$DB" =~ ^[a-z_][a-z0-9_]*$ ]] || { echo "invalid db name: $DB" >&2; exit 1; }

# 迁移前确保目标库存在（幂等）
"$SCRIPT_DIR/createdb.sh" "$DB" >/dev/null

POM="$(cd "$SCRIPT_DIR/../../web-java" && pwd)/pom.xml"
PORT="${MVP_A_PG_HOST_PORT:-55432}"
USER="${MVP_A_PG_USER:-postgres}"
PASSWORD="${MVP_A_PG_PASSWORD:-mvp_a_local}"

# flyway-maven-plugin 已在 web-java/pom.xml 以 ${flyway.version}（= Boot BOM，当前 11.7.2）声明，
# `flyway:migrate` 前缀由该 POM 解析，无需在命令行重复版本号。
exec mvn -B -q -f "$POM" flyway:migrate \
  -Dflyway.url="jdbc:postgresql://127.0.0.1:${PORT}/${DB}" \
  -Dflyway.user="$USER" \
  -Dflyway.password="$PASSWORD"
