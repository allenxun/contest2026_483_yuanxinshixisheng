# backend/deploy — 构建、启动与测试说明（A 包）

## VERSIONS（实际锁定，2026-09-10 解析自 Maven Central / PyPI）

| 组件 | 版本 | 来源 |
|---|---|---|
| Java | Temurin 21.0.12 (LTS) | 本机 |
| Maven | 3.8.7 | 本机 |
| Spring Boot | **3.5.16**（3.5.x 最新 patch） | web-java/pom.xml parent |
| Flyway | **11.7.2**（Boot BOM `${flyway.version}`，flyway-maven-plugin 同版本） | dependency:tree |
| PostgreSQL JDBC | 42.7.11 | Boot BOM |
| HikariCP | 6.3.3 | Boot BOM |
| PostgreSQL | 16（实机 16.15） | 隔离容器 / compose |
| Python | 3.12.3 | 本机 / python:3.12-slim |
| mvp-worker 依赖 | sqlalchemy>=2.0,<3.0；psycopg[binary]>=3.2,<4.0；pydantic>=2.7,<3.0；pytest>=8（dev） | worker-python/pyproject.toml |
| 镜像 | maven:3.9-eclipse-temurin-21 → eclipse-temurin:21-jre；python:3.12-slim；postgres:16；nginx:alpine | Dockerfile/compose |

## 隔离 PostgreSQL 规则（必须遵守）

- 本 worktree 专用容器 `mvp-a-pg`（postgres:16），只绑定 **127.0.0.1:55432**；
  用户 `postgres`，口令 `mvp_a_local`（本机开发占位，非真实凭据）。
- **禁止**触碰宿主 5432（共享 pgvector18）或其他 worktree 的容器/端口。
- 运行时库 `mvp_a_dev`；集成测试每次自建临时库 `mvp_a_test_<random>` 并在结束后删除；
  Java 与 Python 测试不共享数据库实例。
- 迁移唯一入口是 Java 侧 Flyway（`backend/web-java/src/main/resources/db/migration`，V1/V2）；
  Python 永不迁移。

## dev/ 脚本

```bash
cd backend/deploy/dev
./pg-up.sh                 # 幂等启动 mvp-a-pg（已运行则跳过；规格与已准备容器一致）
./createdb.sh <dbname>     # 建库（幂等）
./dropdb.sh <dbname>       # 终止连接并删库
./pg-psql.sh [db] [args…]  # 容器内 psql；如 ./pg-psql.sh mvp_a_dev -c '\dt'
./migrate.sh <dbname>      # flyway-maven-plugin（版本与 Boot BOM 一致）执行迁移；
                           # 选它而非 spring-boot:run：无 web 依赖、纯迁移、可重复执行=no-op。
                           # 若改过 V*.sql 且测试库非全新，需 dropdb 后重建（正式流程不改已发布迁移）。
./run-java-tests.sh        # 确保 PG 后 mvn test（含迁移集成测试）
./run-python-tests.sh      # 确保 PG 后 venv pytest + python -m mvp_worker --check
```

## Java Web（backend/web-java）

```bash
cd backend/web-java
mvn -q -DskipTests package   # 构建 fat jar
mvn test                     # 全量测试（含迁移集成测试，真实 PG 16 自建临时库）
SPRING_DATASOURCE_URL=jdbc:postgresql://127.0.0.1:55432/mvp_a_dev \
SPRING_DATASOURCE_USERNAME=postgres SPRING_DATASOURCE_PASSWORD=mvp_a_local \
SERVER_PORT=18080 java -jar target/web-java-0.0.1-SNAPSHOT.jar   # 默认 8080，SERVER_PORT 可覆盖
curl --noproxy '*' http://127.0.0.1:18080/actuator/health            # {"status":"UP",…}
curl --noproxy '*' http://127.0.0.1:18080/actuator/health/readiness  # 含 DB 检查
```

注：本机 8080 若被其他进程占用，用 `SERVER_PORT=<端口>` 覆盖（验收/冒烟统一用 18080）。
连接池：HikariCP `DB_POOL_MAX` 默认 10（Web）。基包 `cn.yuanxin.mvp.web`；
已提供：requestId/信封/错误码、认证与 T13 幂等、JobEnqueuer、媒体存储基础、
`/api/v1/system/echo-jobs` 跨语言桥与 26 个业务 stub 的 501（无假 200）。

## Python Worker（backend/worker-python）

```bash
cd backend/worker-python
python3 -m venv .venv && .venv/bin/pip install -e '.[dev]'
.venv/bin/python -m pytest -q                    # T12 运行时全量测试
.venv/bin/python -m mvp_worker --check           # 连 MVP_A_PG_DSN，打印 server version
.venv/bin/python -m mvp_worker                   # T12 运行循环（claim/dispatch/complete + 健康端点）
.venv/bin/python -m mvp_worker --once            # 单周期（E2E 用；打印 once_cycle_processed_jobs）
.venv/bin/python -m mvp_worker --recover         # 过期租约回收一次
```

Worker 池：`MVP_WORKER_POOL_SIZE=5`；健康端点 `/healthz` `/readyz` 监听
`MVP_WORKER_HEALTH_HOST:PORT`（默认 127.0.0.1:8081，compose 内 0.0.0.0:8081）。
DSN 优先级：`MVP_WORKER_PG_DSN` → `MVP_A_PG_DSN` → dev 默认（mvp_a_dev@55432）。

## 端到端验收（A 包，跨语言）

```bash
bash backend/tests/run-acceptance.sh
```

一次性 accept 库 + 18080 实时链路 + 约束拒绝 + 契约向量 + 存储互操作全链路，
步骤↔验收映射见 `backend/tests/README.md`。

## 存储替身布局约定（web ↔ worker 跨语言一致）

两侧文件替身路径均为 **`<root>/<object_key>` 原样**（key 含 `/` 即子目录）：
root 由 Java `app.storage.dev-dir`（env `APP_STORAGE_DEV_DIR`，兼容
`MVP_A_STORAGE_DEV_DIR`）与 Python `MVP_A_STORAGE_DEV_DIR`（兼容读同名）
控制，默认 `/tmp/mvp-a-storage`——同 root 同 key 读写同一文件。对象 key
规范 `<environment>/<purpose>/<uuid>`（DD 10.1，不含任何 PII）。compose 中
web/worker 共享命名卷 `media` → `/var/lib/mvp-a/media`。互读证明见
`backend/tests/run-acceptance.sh` 步骤 f9。

## Docker Compose（4 自建组件：pg + web + worker + nginx；OSS 为外部组件）

```bash
cd backend/deploy
cp .env.sample .env    # 填入环境值；仓库不保留真实凭据
docker compose config            # 校验（需 POSTGRES_PASSWORD）
docker compose build             # web-java / worker-python 两张镜像
docker compose up -d             # dev/doubles 形态示例；本地开发请继续用 dev/pg-up.sh 隔离容器
docker build -f deploy/web-java/Dockerfile -t mvp-a/web-java:local web-java      # 从 backend/
docker build -f deploy/worker-python/Dockerfile -t mvp-a/worker-python:local worker-python
```

- 两镜像均非 root（uid 10001）。**web 健康检查**：镜像内已装 curl，
  Dockerfile `HEALTHCHECK` 探测 `/actuator/health`（web Dockerfile 本轮无改动）；
  compose 不重复定义。**worker 健康检查**：compose 用零依赖
  `python -c urllib` 探测容器内 `127.0.0.1:8081/healthz`
  （`MVP_WORKER_HEALTH_HOST=0.0.0.0` 仅面向容器网络）。
- **worker 入口已接管 T12 运行循环**：镜像 ENTRYPOINT `python -m mvp_worker`
  无参数 = 常驻循环（不再是打印帮助后退出）；一次性操作走
  `docker compose run --rm worker --once` / `--check` / `--recover`。
- web/worker 共享命名卷 `media`（存储替身根，见上文布局约定）。worker 另以只读
  bind mount 提供契约目录 `../contracts` → `/app/contracts`（`MVP_CONTRACTS_DIR`）：
  镜像本身不含 contracts，挂载后 payload 契约校验（如 system.echo）在容器内可用。
  worker `depends_on: web healthy`（等 Flyway 建表后再领取，避免启动期关系不存在噪声）。
- production 形态：`SPRING_PROFILES_ACTIVE=prod + APP_PROVIDERS_MODE=real` 且
  无真实提供方时 web 启动即失败（fail closed，预期行为；真实接入归 B/C/D+部署）。
- **端口隔离（M9 运行注意）**：compose `pg` 服务默认映射宿主 `127.0.0.1:55432`，
  与开发隔离容器 `mvp-a-pg` 相同——**两者绝不能并发运行**（端口冲突/连错库）。
  compose 冒烟必须覆盖 `MVP_A_PG_HOST_PORT`（例如 `55434`）或先停止 `mvp-a-pg`；
  任何情况下不得使用宿主 5432。

## Nginx

`nginx/nginx.conf.sample`：反代 `/api/` → web:8080；`/api/v1/media/{id}/content` 响应加
`Cache-Control: no-store`；样例监听 8088（HTTP）。生产 HTTPS：证书经 volume 挂载
（见文件尾部注释块），8443 端口已在 compose 预留；口令/证书路径只走 env/挂载，不入库。

## 环境变量总表（样例值均为占位；完整分组见 .env.sample）

| 变量 | 默认/样例 | 用途 |
|---|---|---|
| POSTGRES_USER / POSTGRES_PASSWORD / POSTGRES_DB | postgres / change-me / mvp_a_dev | compose pg 初始化 |
| PG_PORT → MVP_A_PG_HOST_PORT | 55432 | compose pg 宿主映射（**绝不默认 5432**：宿主 5432 为共享 pgvector18；compose 内部仍 pg:5432，开发隔离走 mvp-a-pg@127.0.0.1:55432） |
| SPRING_PROFILES_ACTIVE | dev | Java profile（prod→app.env=production fail closed） |
| SPRING_DATASOURCE_URL/USERNAME/PASSWORD | jdbc:postgresql://127.0.0.1:55432/mvp_a_dev / postgres / mvp_a_local | Java 应用数据源 |
| SERVER_PORT / WEB_PORT | 8080（本机占用时 18080） | Java HTTP 端口 |
| DB_POOL_MAX / DB_POOL_MIN | 10 / 2 | HikariCP（Web 池上限 10，联调初值） |
| SPRING_MULTIPART_MAX_FILE_SIZE / _REQUEST_SIZE | 10MB / 32MB | 上传限制（DD 12.1） |
| APP_ENV | dev | 对象 key 前缀 environment；prod profile 固定 production |
| APP_PROVIDERS_MODE | doubles | doubles(仅 dev/test)/disabled/real；production 必须 real |
| APP_STORAGE_DEV_DIR ↔ MVP_A_STORAGE_DEV_DIR | /tmp/mvp-a-storage | 存储替身根（两侧等效互通，布局 `<root>/<object_key>`） |
| APP_STORAGE_BUCKET | mvp-a-media | media_objects.bucket 逻辑桶名 |
| APP_IMAGE_MAX_BYTES | 10485760 | 单图字节上限 |
| APP_MEDIA_ACCESS_MODE | deny-all | 媒体读取模式（deny-all/owner-dev/any-authenticated；production 非默认即拒绝启动） |
| APP_IDEMPOTENCY_LEASE_SECONDS | 30 | T13 processing 租约（过期 takeover） |
| JOB_MAX_ATTEMPTS | 5 | **enqueue authority for async_jobs.max_attempts**（Java JobEnqueuer 写入的默认；与 worker retry 上限对齐） |
| APP_DOUBLE_SMS_CODE / APP_DOUBLE_FACE | 123456 / MATCHED | dev/test 认证替身行为 |
| MVP_WORKER_PG_DSN | postgresql://postgres:change-me@pg:5432/mvp_a_dev | Worker 运行时连接（→MVP_A_PG_DSN→dev 默认） |
| MVP_WORKER_POOL_SIZE / CLAIM_BATCH / LEASE_SECONDS | 5 / 5 / 60 | 池（max_overflow 固定 0）、每周期领取、租约 |
| MVP_WORKER_RENEW_INTERVAL_SECONDS | 15 | 条件续租间隔 |
| MVP_WORKER_RETRY_MAX_ATTEMPTS / BACKOFF_BASE_SECONDS / BACKOFF_CAP_SECONDS | 5 / 5 / 300 | 重试与退避（min(base·2^(n-1),cap)+抖动） |
| MVP_WORKER_POLL_INTERVAL_SECONDS | 2 | 空闲轮询间隔 |
| MVP_WORKER_HEALTH_HOST / PORT | 127.0.0.1（compose 0.0.0.0）/ 8081 | /healthz /readyz |
| MVP_WORKER_ENVIRONMENT | dev | 媒体 key 前缀 |
| MVP_CONTRACTS_DIR | ../contracts（可选） | 测试期契约目录位置 |
| MVP_A_PG_JDBC / MVP_A_PG_USER / MVP_A_PG_PASSWORD | jdbc:postgresql://127.0.0.1:55432/postgres / postgres / mvp_a_local | Java 迁移测试建临时库 |
| MVP_A_PG_DSN | postgresql://postgres:mvp_a_local@127.0.0.1:55432/postgres | Python `--check` |
| NGINX_HTTP_PORT / NGINX_HTTPS_PORT | 8088 / 8443 | Nginx 入口样例端口 |
