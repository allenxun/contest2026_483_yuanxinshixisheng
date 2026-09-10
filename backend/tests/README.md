# backend/tests — A 包（foundation）跨语言验收

本目录是工作包 A 的**端到端验收层**：把 contracts（契约/规范化）、
web-java（Spring 基础实现）、worker-python（T12 运行时）、deploy
（Flyway 迁移入口与隔离 PG 脚本）作为一个整体跑一遍，证明
`backend/doc/tasks/A-foundation.md` 的验收句成立：

> Java/Python 测试通过；全新 PG 可迁移并重复启动无破坏；约束拒绝双占用和
> 双记录；最小测试 job 能从 Java 契约进入 Python 并按正确代次完成；
> 无效认证拒绝；精简 JSON 样例跨语言一致。

## 前置条件

1. **隔离 PG**：容器 `mvp-a-pg`（`bash backend/deploy/dev/pg-up.sh`，
   127.0.0.1:55432，postgres/mvp_a_local）。脚本只打 55432，**绝不触碰
   宿主 5432**。
2. docker、Maven、JDK 21（`java -version`）。
3. 两个 venv：`backend/contracts/.venv`（jsonschema、PyYAML、
   openapi-spec-validator）与 `backend/worker-python/.venv`（`pip install
   -e '.[dev]'`）。
4. 宿主端口 **18080** 空闲（8080 已被占用，acceptance 用 SERVER_PORT=18080）。
   可用 `ACCEPT_APP_PORT` 覆盖。

## 运行

```bash
bash backend/tests/run-acceptance.sh   # 退出码非 0 = 存在 FAIL
```

每次运行使用一次性资源并在退出时（trap）清理：新库
`mvp_a_accept_<hex8>`、独立存储根 `/tmp/mvp-a-accept-storage-<hex8>`、
临时目录 `/tmp/mvp-a-accept-<hex8>.*`，可重复执行。所有 HTTP 检查走
`curl --noproxy '*'`。

## 步骤 ↔ 验收映射

| 步骤 | 内容 | A-foundation 验收/交付 |
|---|---|---|
| a  | `createdb.sh`→`migrate.sh`→psql 断言 14 张 public 业务表→再次 `migrate.sh` 无破坏（MIG2_NOOP：成功且 flyway_schema_history 行数不变） | 全新 PG 可迁移并重复启动无破坏（交付2） |
| b0 | 种最小父链（6×T13、成员、云台、测肤、方案、微晶、执行、记录——SQL 在脚本内注释） | 约束拒绝（前置） |
| b1 | 同一微晶第二个未收尾 `care_executions` → 必须报 `uq_execution_open_microcrystal` | 约束拒绝**双占用** |
| b2 | 同一执行重复 `(execution_id,source_epoch,source_seq)` → `uq_record_source` | 约束拒绝**双记录** |
| b3 | T13 `(principal,operation,key)` 重复 → `uq_idem_principal` | 交付2 唯一约束 |
| b4 | members `(identity_namespace,face_subject_ref)` 双非空重复 → `uq_members_identity` | 交付2 部分唯一索引 |
| b5/b6 | `ck_assessment_status`、`ck_assessment_current_photo_version` CHECK 拒绝 | 交付2 检查条件 |
| c1 | `jcs.py selftest`（ES6 Number::toString 23 组权威数对+结构规则） | 精简 JSON 样例跨语言一致 |
| c2 | `validate_samples.py`（全部样例 + 15 条规范化向量用参考实现重算） | 同上（交付3） |
| c3 | openapi-spec-validator 校验 openapi.yaml | 交付3 OpenAPI 基础契约 |
| d  | `mvn package`：Java 全量测试（≥75，含 JCS 向量/ES6 数对/迁移 IT）并产出 jar | Java 测试通过（交付1） |
| e  | worker `pytest -q`（≥43：T12 claim/renew/recover/complete/代次/backoff） | Python 测试通过 |
| f0 | jar 启动（dev profile → accept 库、storage=/tmp 独立根）→ `/actuator/health` UP | 交付1 可构建、启动 |
| f1 | 业务 stub 无 token → 401 `AUTH_REQUIRED` 信封 | **无效认证拒绝** |
| f2 | `POST /auth/sms-challenges` → `POST /auth/sessions`（固定验证码替身 123456 + installationId）→ accessToken | 交付4 认证端口+隔离替身 |
| f3 | 有 token 访问业务 stub → 501 `NOT_IMPLEMENTED`（不给假 200） | 交付3 |
| f4 | `POST /system/echo-jobs`（Idempotency-Key）→ `data.status=queued`+jobId；同键重放 → `meta.replayed=true` 且同 jobId | 交付5 T13 幂等 |
| f5 | 伪造 Bearer → 401 `SESSION_INVALID`（不凭任意 token/id 认证成功） | **无效认证拒绝** |
| f6 | `mvp_worker --once`（MVP_WORKER_PG_DSN → accept 库）→ `once_cycle_processed_jobs ≥ 1` | **最小 job 从 Java 契约进入 Python** |
| f7 | `GET /system/echo-jobs/{jobId}` → status=succeeded、attemptCount="1"（完成带代次守护） | **按正确代次完成** |
| f8 | psql 取 `async_jobs.payload` → contracts venv 用 `payload-system-echo.json` 校验 PASS | **跨语言契约一致**（Java 写 → 契约 schema → Python 校验器） |
| f9 | 存储互操作（Task：布局约定）：`support/StorageInterop.java` 驱动真实 Java `FileSystemStorageDouble` put/get，worker venv 驱动 Python `FilesystemStorageDouble`，同一 root 下 `<root>/<object_key>` 原样双向互读 | 交付6 媒体/存储适配基础 |
| f10 | app SIGTERM 优雅停止 | 交付1 |

## support/

- `StorageInterop.java` — 单文件源码启动器（`java -cp
  backend/web-java/target/classes StorageInterop.java put|get <root> <key>
  [content]`），直接实例化真实 Java 测试替身，无 Spring 依赖。
- `validate_payload.py` — 用 contracts venv 按 draft 2020-12（含跨文件
  `$ref` 注册表）校验单个 payload 文件。
