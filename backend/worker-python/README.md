# mvp_worker — Python 后台异步任务 Worker（T12 运行时）

A 包交付：`async_jobs` 的领取/续租/过期回收/代次受控完成运行时、
`system.echo` handler、B/C/D handler 扩展点、媒体访问骨架、健康端点。
技术栈锁定见 `backend/doc/` 与 `.coordination/A/decisions.md`：
Python 3.12 + SQLAlchemy Core 2.x（无 ORM）+ psycopg 3 + pydantic 2 +
jsonschema（draft 2020-12 契约校验）。**Python 永不跑迁移**（Flyway 唯一入口）。

## 运行保证：至少一次执行 + 代次控制

- **at-least-once**：崩溃/租约过期后任务会被再次领取，handler 可能重复执行。
  **不宣称 exactly-once**；重复落地由以下机制阻断：
  1. **领取代次** `lease_revision`：每次领取/回收 +1。所有状态写回（成功、
     失败、放弃）都是条件更新
     `WHERE id AND status='running' AND lease_owner AND lease_revision`，
     0 行 → `StaleGeneration`，旧领取者的一切结果作废。
  2. **成功事务顺序**（DD 8.1）：同一事务内**先**执行 handler 业务写回调
     （先锁业务行、持锁后复核业务 `input_revision` 仍是任务输入版本），
     **后**更新 `async_jobs → succeeded`；守卫失败 → 整体回滚，结果不发布。
  3. **回收器**：条件更新把过期 `running` 转回 `queued` 并 +代次，使旧领取者
     整体失效；绝不"查时间后无条件覆盖"。
- **重试**：可重试失败且 `attempt_count < max_attempts`（行上列值为准，
  Java 入队默认 5）→ 回 `queued`，指数退避
  `delay = min(base * 2^(attempt-1), cap) + U(0, 0.2*delay)`
  （dev 初值 base=5s、cap=300s）；否则 `failed` 留 `last_error`。
- **契约不认识不循环**：未知 job_type / 未注册 handler / payload
  schema_version 不符 / JSON Schema 校验失败 → 直接
  `failed` + `last_error.code=UNSUPPORTED_CONTRACT`，不重试。

## 状态机（async_jobs.status）

```
                 ┌──────────────── retryable & attempt<max ────────────────┐
                 │            （available_at = now + backoff+抖动）          │
 queued ──claim──▶ running ──┬─ handler ok + 代次守卫过 ──▶ succeeded(终态)  │
   ▲    (FOR UPDATE          ├─ 不可重试 / 尝试耗尽 ──▶ failed(终态)         │
   │    SKIP LOCKED)         ├─ 契约不认识 ──────────▶ failed(UNSUPPORTED)   │
   └────── recover ──────────┴─ 租约过期(未写回) ──────┘(回收器条件更新回 queued, 代次+1)
```

- claim：单短事务 SELECT+UPDATE（提交后才做外部调用；不持 T12 等业务行）。
- renew：仅当代次匹配且原租约未到期才延长；失败 → `LostLease` →
  handler 协作式中止，结果**不提交**（放弃写回，等新代次）。
- stale 完成：业务写（含 media_objects）随事务回滚，绝不发布。

## 写入边界（硬约束）

Worker 只写：
- `async_jobs` 的租约/状态/结果字段：`status, lease_owner, lease_until,
  lease_revision, attempt_count, available_at, last_error, finished_at`
  （+自维护的 `updated_at` 簿记列）；全部字段级条件 UPDATE，**禁整行 upsert**。
- 扩展点（B/C/D）：自己任务的 `media_objects` 行 + 设计中划给 Worker 的
  业务表字段（见 `src/mvp_worker/handlers/README.md`）。
- **永不写** `idempotency_requests`（T13 归 Java）；A 包 echo 只动 `async_jobs`。

## CLI

```bash
.venv/bin/python -m mvp_worker            # 运行循环 + 健康端点（SIGTERM/SIGINT 优雅停机）
.venv/bin/python -m mvp_worker --check    # 连 PG 打印服务端版本（连通自检，不启循环）
.venv/bin/python -m mvp_worker --once     # 单个 回收+领取+处理+完成 周期后退出（E2E 用，不启健康端点）
.venv/bin/python -m mvp_worker --recover  # 执行一次过期回收并打印条数
```

优雅停机：置 stop 标志 → 不再领取；等待在途完成事务落定；来不及完成的由
租约过期回收接管。`runtime/expire.release_claim()` 提供"仍持当前代次时主动
交回 queued（代次+1）"的 best-effort 原语（当前循环在 run_cycle 边界等待全部
future，天然无遗留；该原语供停机策略演进使用）。

## 配置（env，dev 初值=联调起点，非验收硬值）

| env | 默认 | 说明 |
|---|---|---|
| `MVP_WORKER_PG_DSN` | 未设→回退 `MVP_A_PG_DSN`→`postgresql://postgres:mvp_a_local@127.0.0.1:55432/mvp_a_dev` | 运行时连接串 |
| `MVP_A_PG_DSN` | `postgresql://postgres:mvp_a_local@127.0.0.1:55432/postgres` | `--check` 自检连接串（跨语言脚本统一入口） |
| `MVP_WORKER_POOL_SIZE` | 5 | 连接池（`max_overflow` 固定 0） |
| `MVP_WORKER_CLAIM_BATCH` | 5 | 每次领取上限（=线程池大小） |
| `MVP_WORKER_LEASE_SECONDS` | 60 | 租约时长 |
| `MVP_WORKER_RENEW_INTERVAL_SECONDS` | 15 | 续租周期（回收器同周期跑） |
| `MVP_WORKER_RETRY_MAX_ATTEMPTS` | 5 | 入队默认 max_attempts（运行以行列为准） |
| `MVP_WORKER_BACKOFF_BASE_SECONDS` | 5 | 退避基数 |
| `MVP_WORKER_BACKOFF_CAP_SECONDS` | 300 | 退避封顶 |
| `MVP_WORKER_POLL_INTERVAL_SECONDS` | 2 | 空闲轮询间隔 |
| `MVP_WORKER_HEALTH_HOST` / `MVP_WORKER_HEALTH_PORT` | `127.0.0.1` / `8081` | 健康端点（仅运行循环启动） |
| `MVP_WORKER_ENVIRONMENT` | `dev` | 对象 key 的 environment 段 |
| `MVP_A_STORAGE_DEV_DIR` | `/tmp/mvp-a-storage` | 文件系统存储替身根目录 |
| `MVP_CONTRACTS_DIR` | 仓库 `backend/contracts` | JSON Schema 只读引用位置 |

健康端点：`GET /healthz` → `{"status":"UP","workerId":...}`；
`GET /readyz` → `{"status":"UP","db":true,"oldestQueuedJobAgeSeconds":N|null}`，
DB 不可达 → 503 `{"status":"DOWN"}`（进程活着 ≠ 任务在推进）。

日志：stdout 单行 JSON（`ts/level/event` + `workerId/jobId/jobType/dedupKey/
leaseRevision/attemptCount/inputRevision`）。绝不输出 payload 内容、照片、
凭据、堆栈。

## Handler 扩展点（B/C/D）

见 `src/mvp_worker/handlers/README.md`。A 包仅注册 `system.echo`；
业务 job_type 未注册前领取即 `failed/UNSUPPORTED_CONTRACT`（隔离、不循环）。

## 测试

```bash
# 前置：隔离 PG 容器（127.0.0.1:55432）
../deploy/dev/pg-up.sh
# 会话内自动建临时库 mvp_a_test_p_<uuid> + Flyway 迁移（backend/deploy/dev/migrate.sh），跑完删除
.venv/bin/python -m pytest -q
.venv/bin/python -m mvp_worker --check
# 或一键：
../deploy/dev/run-python-tests.sh
```

真实 PG（非 SQLite）；跨语言基线：`tests/test_canonicalization.py` 以
`backend/contracts/scripts/jcs.py` 复现共享向量；`tests/test_e2e_once.py` 按
Java lane 入队形状（owner_id=UUIDv5(FIXED_NS, dedup_key)、input_revision=0、
契约样例 payload）走 `--once` 全链路到 succeeded。
