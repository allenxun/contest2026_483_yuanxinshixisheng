#!/usr/bin/env bash
# 运行 Java 侧测试（含 Flyway 迁移集成测试，对真实 PG 16，自动建/删临时库 mvp_a_test_*）。
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
"$SCRIPT_DIR/pg-up.sh" >/dev/null
exec mvn -B -f "$SCRIPT_DIR/../../web-java/pom.xml" test
