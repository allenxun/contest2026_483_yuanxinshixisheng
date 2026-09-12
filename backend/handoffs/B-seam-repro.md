# B-seam-repro：E 复验 B 提供的测试注入缝（配置 / 复位 / 最小调用示例）

> **用途**：供 E 在总协调把本轮代码合入 dev 后，复验 6+1 项 `seam_pending` 场景（SC-02-05/06/08/09、SC-03-07、SC-C-05，以及总协调新增的 SC-02-10）。
> **绑定 SHA**：**`8343ba5a4dd9ee611da979617d2982943fc61af9`**（本轮最终代码 SHA）。提交链：`5bd22d3` → `7524714`(Java 存储缝) → `9b3d802`(Python 7 旋钮) → `f4b9546`(测试端口冲突修复) → `d312d2a`(EOF 空行) → `40f5fde`(严格布尔解析) → `181676d`(barrier + SC-02-10) → `8343ba5`(工装 b40/b41)。全部经 orchestrator 独立核验：**pytest 291 passed rc=0**、**Java 419/0/0**、**端到端工装 ALL PASS 41/41 `SCRIPT_RC=0`**。
> **诚实边界**：这些缝只改变**测试替身返回的外部结果**，业务判定分支原样执行；全部结果属 `doubles_pass`，**不得**据此宣称真实供应商/真实算法准确率或生产就绪。

---

## 1. 通用规则（适用于全部旋钮）

1. **默认关闭**：不设任何 env 时，行为与未引入缝之前**完全一致**（有专门回归测试；全量 Java/Python 测试在不设旋钮时全绿）。
2. **只能经进程 env / Spring 属性施加**：**不存在任何 HTTP 可开启路径**——两个 Java main 文件中 `RequestParam|RequestHeader|PathVariable|RequestBody|@*Mapping` 计数为 0；Python 侧 diff 中无 route/endpoint。**不能由未授权业务请求开启。**
3. **生产禁用（启动即拒，非运行期忽略）**：
   - Java：`TestDoubleProvidersConfig.requireNoProductionSignals` 双判据——`acceptsProfiles("prod")` **或** `app.env`（trim+忽略大小写）`=production` ⇒ 抛 `IllegalStateException` **拒绝装配替身**；纯 `prod` profile 下 `StoragePort` 替身根本不装配；生产若刻意 `app.providers.mode=real` 绕开本配置，另有既有 `ProductionFailClosedValidator` 兜底。
   - Python：`dconfig.assert_no_double_injection_in_production()`——生产信号（解析后环境 + `MVP_NOTIFY_ENV`/`MVP_WORKER_ENVIRONMENT`/`APP_ENV` 三处 raw env + **`SPRING_PROFILES_ACTIVE`**）∩ 任一注入开关非默认 ⇒ 抛 `ProviderConfigError` 拒启；由 `__main__.py:_validate_startup_config()` 在 `main()` 中**早于 DB 与健康端口**调用。
   - **混合 profile / `app.env` 矛盾组合亦被拒**（如 `spring.profiles.active=prod,dev` + `app.env=dev`）。
4. **严格取值校验（fail fast）**：注入开关的枚举/布尔/列表取值在**加载或装配期**校验，非法值立即抛错并在消息中给出**变量名、实际取值、完整值域**；**绝不静默忽略、绝不把未知值当默认值**。布尔只接受 `1/true/yes/on` 与 `0/false/no/off`（trim+小写）；其余（如 `bogus`、`maybe`、`2`）一律报错。
5. **隔离口径**：注入是**进程级** env，**不是 task/RUN_ID 级**——同一 worker 进程会影响其领取的所有同类任务。E 必须以**独立测试实例 / 独立 DB / 独立 RUN_ID** 隔离，**禁止并行污染**（同一进程内混跑注入与非注入用例）。
6. **复位**：`unset <VAR>` 或显式设为默认值（Java 侧 `none`、Python 侧见第 4 节表）。Java 侧旋钮在 **bean 装配期读取一次** ⇒ **改变取值必须重启 Java 进程**；Python 侧在**进程启动时**读取 ⇒ 每次 `worker_once(env_extra=…)` 自然生效，无需常驻进程。
7. **生效确认**：Java 启动日志出现 `storage test-double write-failure injection ARMED: … failAllPuts=… failPurposes=[…]`；Python 侧可用 `python -m mvp_worker --check` 验证配置被接受（rc=0）。

---

## 2. Java 侧：`APP_DOUBLE_STORAGE_FAIL_MODE`（SC-C-05 要求①②：上传失败）

| 项 | 值 |
|---|---|
| 名称 | `APP_DOUBLE_STORAGE_FAIL_MODE` |
| 值域 | `none`（**默认**）｜`fail-put`（全用途写入失败）｜`fail-put:<purpose>[,<purpose>…]`（按用途） |
| `<purpose>` | 由 `MediaPurpose.values()` 派生（**非硬编码子集**）：`assessment_source`、`assessment_result`、`grant_face`、`execution_face`、`revalidation_face` |
| 归一化 | trim + 转小写；`null`/空白 → `none` |
| 非法取值 | **装配期抛 `IllegalArgumentException`**（fail fast） |
| 施加位置 | **Java 应用进程**（不是 worker 进程） |
| 生效时机 | bean 装配期读取一次 ⇒ **改值须重启 Java 进程** |
| 注入范围 | **只注入写入（`put`）**；`get`/`getStream`/`exists`/`delete` 不受影响 |
| 异常类型 | 抛**既有** `UncheckedIOException` ⇒ 走 `MediaIntakeService:76-83` 的**既有**映射（T11 `fail(pending, DEPENDENCY_UNAVAILABLE)` + HTTP **503 `DEPENDENCY_UNAVAILABLE`**），**未改任何业务判定** |

### 2.1 purpose → 真实 HTTP 入口

| purpose | 入口 | 说明 |
|---|---|---|
| `assessment_source` | `POST /api/v1/skin-assessment-tasks`（M3-A01）、`PUT /api/v1/skin-assessment-tasks/{taskId}/photo-versions/{v}`（M3-A02） | 云台原图 / 补拍照片 |
| `grant_face` | `POST /api/v1/member-access-grants`（M1-A01，multipart `{metadata,face}`） | APP 授权人脸（核验证据） |
| `execution_face` / `revalidation_face` | C 域执行/复核端点的人脸上传 | 核验证据；机制同构（同一入库路径、同一 purpose 解析），按用途选择性已由单元测试与两条 HTTP 端到端 IT 证明；**专用 C 端点 IT 属 E 的最终证据缺口**（Oracle 判非阻塞、由 E 用 C 的 HTTP 端点补） |
| `assessment_result` | 结果图由 **Worker** 写入 | Java 侧接受该值但通常**不命中上传路径**（语义冗余，Oracle 判可接受） |

`purpose` 解析口径：`objectKey.split("/")[1]`，与 `MediaService.java:66` 的 `objectKey = props.env() + "/" + purpose.dbValue() + "/" + id` **格式吻合**（若不吻合则按用途选择会**静默失效**，已核实）。

### 2.2 最小调用示例

```bash
# ① 仅让云台原图上传失败（M3-A01/A02 → 503），APP 授权人脸不受影响
APP_DOUBLE_STORAGE_FAIL_MODE='fail-put:assessment_source' \
  java -jar backend/web-java/target/web-java-0.0.1-SNAPSHOT.jar \
  --spring.profiles.active=test --server.port=18083 \
  --spring.datasource.url=jdbc:postgresql://127.0.0.1:55435/postgres \
  --spring.datasource.username=postgres --spring.datasource.password=<local-test-password>

# ② 仅让 APP 授权/核验人脸上传失败（M1-A01 → 503），云台原图不受影响
APP_DOUBLE_STORAGE_FAIL_MODE='fail-put:grant_face' java -jar …（同上）

# ③ 多用途同时失败
APP_DOUBLE_STORAGE_FAIL_MODE='fail-put:assessment_source,grant_face' java -jar …

# ④ 全用途写入失败
APP_DOUBLE_STORAGE_FAIL_MODE='fail-put' java -jar …

# ⑤ 复位（两者等价）
unset APP_DOUBLE_STORAGE_FAIL_MODE        # 或
APP_DOUBLE_STORAGE_FAIL_MODE=none java -jar …
```

### 2.3 预期可观测量

**注入生效时**（以 `fail-put:assessment_source` 为例）
- HTTP：M3-A01 / M3-A02 → **503**，`error.code == "DEPENDENCY_UNAVAILABLE"`（含 `requestId`，`details` 不泄漏内部诊断）
- DB（**无脏成功**）：该 `request_id` 下 `media_objects` 中 `state='available'` 行数 **= 0**、`state='failed'` 行数 **≥ 1**；`skin_assessments` **未创建任务**（行数 0）；该云台 `status='report_ready'` 行数 **= 0**
- 注入 `grant_face` 时额外：`member_access_grants` 行数 **= 0**、`idempotency_requests.status ≠ 'succeeded'`
- **按用途互不干扰**：注入 `assessment_source` 时 M1-A01 仍 **201** 且对象 `available`；注入 `grant_face` 时 M3-A01 仍 **202** 且 `available`

**复位后（默认 `none`）**
- M3-A01 → **202**，三视角 `media_objects.state='available'` 行数 = 3，对象**真实落盘**且字节与上传一致
- **重启可读**：以同一 `dev-dir` 新建替身实例后 `exists(objectKey)` 为真、`get(objectKey)` 字节一致（已有断言覆盖）
- `photo_versions` JSON 正常推进

### 2.4 生产不可达（6 种组合，均已断言）

| 组合 | 结果 |
|---|---|
| `app.env=production` + test profile + `fail-put` | 启动**失败**（开关不可达） |
| **混合 profile `prod,dev` + `app.env=dev` + `mode=doubles` + `fail-put`** | 启动**失败**（profile 判据命中） |
| `app.env=' Production '`（大小写/空白） | 启动**失败** |
| 纯 `prod` profile | 启动成功但 **`StoragePort` 替身根本不装配** |
| `dev`/`test` + 合法值 | 正常装配，注入可用 |
| 非法值（如 `fail-put:not_a_purpose`） | **装配期失败** |

真实进程复核命令（orchestrator 已亲验，E 可复跑）：

```bash
APP_ENV=dev APP_PROVIDERS_MODE=doubles APP_DOUBLE_STORAGE_FAIL_MODE=fail-put \
  java -Xmx384m -jar backend/web-java/target/web-java-0.0.1-SNAPSHOT.jar \
  --spring.profiles.active=prod,dev --server.port=18083 \
  --spring.datasource.url=jdbc:postgresql://127.0.0.1:55435/postgres \
  --spring.datasource.username=postgres --spring.datasource.password=<local-test-password> \
  --spring.flyway.enabled=false
# 预期：退出码非 0；日志含
#   production fail-closed: test-double providers refused under production signals
#   (active-profile-prod=true, app.env=dev, activeProfiles=[prod, dev])
# 且 grep -c "Tomcat started on port" == 0（端口从未绑定）；退出后 18083 空闲
```

---

## 3. Python 侧旋钮总表（12 个：7 个基础 + 5 个新增，全部默认关闭）

| env | 值域 | 默认 | 服务的场景 | 主要可观测量 |
|---|---|---|---|---|
| `MVP_D_FACE_DOUBLE_QUALITY` | `accepted` \| `needs_retake` | `accepted` | SC-02-05；SC-02-08/09 的入口 | `skin_assessments.status='needs_retake'`、`identity_result.quality.required_views`、`failure_code='QUALITY_REJECTED'`、`report_payload` 为空、无 `report_ready` |
| `MVP_D_FACE_DOUBLE_REQUIRED_VIEWS` | `front`/`left`/`right` 的逗号子集 | 空（用替身默认） | SC-02-05 的 `requiredViews` | 上表 `required_views`；非法视角或**仅逗号/全空段**（`,,,`）→ **加载期抛错** |
| `MVP_D_FACE_DOUBLE_SAME_PERSON` | `true` \| `false`（严格布尔） | `true` | SC-02-06 | `NOT_SAME_PERSON`；**`members` 行数不增**、`member_id` 未误置、无报告 |
| `MVP_D_FACE_DOUBLE_SEARCH` | `reliable_new`\|`matched`\|`uncertain`\|`ambiguous`\|`dependency_failed` | `reliable_new` | SC-02-06；SC-02-07 的 matched 分支 | `uncertain`/`ambiguous` → `IDENTITY_UNCERTAIN`（不建档、不出报告）；`matched` → 关联既有成员；`dependency_failed` → `DEPENDENCY_UNAVAILABLE`（可重试） |
| `MVP_D_PLAN_DOUBLE_MODE` | `valid`\|`timeout`\|`failure` + `PlanDouble` 既有 10 种非法形状名 | `valid` | SC-03-07 | `timeout`/`failure` → `care_plans.generation_status` **绝不为 `ready`**、T12 可重试 `DEPENDENCY_UNAVAILABLE` 至预算耗尽落终态；非法形状 → `PLAN_VALIDATION_FAILED`/`PLAN_SNAPSHOT_INVALID`（既有行为不变） |
| `MVP_D_SKIN_DOUBLE_HOLD` | `true` \| `false`（严格布尔） | `false` | SC-02-09（**第一版进程级 hold；Oracle 判不足，见第 5 节**） | `analyze` 可重试失败、job 停 `queued`；撤 env 即 release |
| `MVP_D_STORAGE_DOUBLE_FAIL_PUT` | `true` \| `false`（严格布尔） | `false` | SC-C-05 要求③（Worker 结果图保存） | **仅** key 用途段为 `assessment_result` 的写入抛 `StorageError` → 既有 `RESULT_ARCHIVE_FAILED`（可重试）、无 available 脏行、报告不就绪 |
| `MVP_D_DOUBLE_LATE_BARRIER` | 严格布尔 | `false` | **SC-02-09**（真实迟到返回） | 首个命中标记的 `quality` 调用**先算后等**；详见 **§5.1** |
| `MVP_D_DOUBLE_LATE_BARRIER_DIR` | 目录路径 | 空 → 系统临时目录 | 同上 | sentinel 目录；**应显式指定每场景独立目录** |
| `MVP_D_DOUBLE_LATE_BARRIER_SHA256` | 64 位 hex（开启时**必填**） | 空 | 同上 | 命中标记 = **上传照片内容 sha256**（未改端口签名） |
| `MVP_D_DOUBLE_LATE_BARRIER_TIMEOUT_SECONDS` | 整数 **≥1** | `30` | 同上 | 超时**清理 sentinel** 并抛既有 `ProviderUnavailable`（可重试），绝不永久挂起 |
| `MVP_D_SKIN_DOUBLE_INVALID` | `none`\|`unknown_metric`\|`out_of_range`\|`bad_unit` | `none` | **SC-02-10** | 经**既有** `_ContractViolation` → `_terminal(PROVIDER_CONTRACT_VIOLATION)`，**1 轮确定性**终态；详见 **§5.2** |

> **既有旋钮（非本轮新增，E 已在用）**：`MVP_D_FACE_PROVIDER` / `MVP_D_SKIN_PROVIDER` / `MVP_D_PLAN_PROVIDER`（选 double 或 aliyun；`aliyun_*` 未激活 → `ProviderNotActivated`，属**瞬态可重试**）、`MVP_PLAN_CAPABILITY_BASELINE`（非法 baseline → `PLAN_SNAPSHOT_INVALID`）。
> **注意**：`MVP_D_SKIN_PROVIDER=aliyun_skin` **只产生瞬态重试**，黑盒**不能确定到达终态失败**——这正是 SC-02-10 被 E 纠正为 `seam_pending` 的原因；该缺口已由 `MVP_D_SKIN_DOUBLE_INVALID` 闭合（§5.2）。
> **全部 12 个旋钮**（含 Java 侧 `APP_DOUBLE_STORAGE_FAIL_MODE` 共 13 个开关）均：默认值 = 原行为、严格值域校验（非法值加载/装配期 fail fast）、登记进生产启动守卫、仅进程 env 可施加、**无任何 HTTP 可开启路径**。

### 3.1 最小调用示例（worker 侧，逐次进程调用）

```bash
cd backend/worker-python
BASE="MVP_A_PG_DSN=postgresql://postgres:<pw>@127.0.0.1:55435/postgres \
MVP_A_PG_HOST_PORT=55435 MVP_A_PG_USER=postgres MVP_A_PG_PASSWORD=<pw> \
MVP_A_PG_CONTAINER=mvp-b-pg \
MVP_WORKER_PG_DSN=postgresql://postgres:<pw>@127.0.0.1:55435/mvp_b_dev"

# 质量不合格（SC-02-05 正例）
env $BASE MVP_D_FACE_DOUBLE_QUALITY=needs_retake \
        MVP_D_FACE_DOUBLE_REQUIRED_VIEWS=front,left \
  .venv/bin/python -m mvp_worker --once

# 非同人 / 不确定（SC-02-06 两分支，分别跑）
env $BASE MVP_D_FACE_DOUBLE_SAME_PERSON=false .venv/bin/python -m mvp_worker --once
env $BASE MVP_D_FACE_DOUBLE_SEARCH=uncertain  .venv/bin/python -m mvp_worker --once

# 方案超时 / 失败 / 非法（SC-03-07）
env $BASE MVP_D_PLAN_DOUBLE_MODE=timeout .venv/bin/python -m mvp_worker --once
env $BASE MVP_D_PLAN_DOUBLE_MODE=failure .venv/bin/python -m mvp_worker --once

# 结果图保存失败（SC-C-05 要求③）
env $BASE MVP_D_STORAGE_DOUBLE_FAIL_PUT=true .venv/bin/python -m mvp_worker --once

# 复位：不设这些变量即可（默认值 = 原行为）
env $BASE .venv/bin/python -m mvp_worker --once
```

> **`--check` 的 DSN 注意**：`WorkerConfig.check_dsn` 只读 `MVP_A_PG_DSN`（默认指向 **55432**，本项目禁用），故跑 `--check` 必须显式给 `MVP_A_PG_DSN`，否则会因连不上 55432 而 rc=1（**这不是守卫拒绝**，须以错误类型区分：守卫拒绝报 `ProviderConfigError: production fail-closed …`）。

### 3.2 生产禁用与 fail-fast 的复核命令（orchestrator 已亲验，E 可复跑）

```bash
cd backend/worker-python
CK="MVP_A_PG_DSN=postgresql://postgres:<pw>@127.0.0.1:55435/postgres"
RT="MVP_WORKER_PG_DSN=postgresql://postgres:<pw>@127.0.0.1:55435/mvp_b_dev"

# 生产 + 注入 → 拒启（rc=1，早于 DB）
env $CK $RT APP_ENV=production MVP_D_SKIN_DOUBLE_HOLD=true \
  .venv/bin/python -m mvp_worker --check
#   → ProviderConfigError: production fail-closed: test-double injection switches set in a
#     production context (signals: ['resolved_environment=production','APP_ENV=production'];
#     switches: ['MVP_D_SKIN_DOUBLE_HOLD']); refusing to start

# 混合/矛盾信号 + 注入 → 同样拒启
env $CK $RT SPRING_PROFILES_ACTIVE=prod,dev APP_ENV=dev MVP_D_PLAN_DOUBLE_MODE=timeout \
  .venv/bin/python -m mvp_worker --check
#   → signals: ['SPRING_PROFILES_ACTIVE=prod,dev']

# 生产 + 全默认 → 不误拦（rc=0，打印 PostgreSQL server_version）
env $CK $RT APP_ENV=production .venv/bin/python -m mvp_worker --check
# 混合信号 + 全默认 → 不误拦（rc=0）
env $CK $RT SPRING_PROFILES_ACTIVE=prod,dev APP_ENV=dev .venv/bin/python -m mvp_worker --check
# dev + 注入 → 允许（rc=0）；dev + 7 个开关全非默认（合法值）→ 允许（rc=0）

# 非法取值 → fail fast（rc=1，消息含变量名/实际取值/值域）
env MVP_D_FACE_DOUBLE_SAME_PERSON=bogus   PYTHONPATH=src python3 -c \
  'from mvp_worker.handlers.dshared.dconfig import DConfig; DConfig.from_env()'
env MVP_D_SKIN_DOUBLE_HOLD=bogus          PYTHONPATH=src python3 -c '…同上…'
env MVP_D_STORAGE_DOUBLE_FAIL_PUT=bogus   PYTHONPATH=src python3 -c '…同上…'
env MVP_D_FACE_DOUBLE_REQUIRED_VIEWS=',,,' PYTHONPATH=src python3 -c '…同上…'
```

---

## 4. 与"真实 HTTP 入口 + 真实 worker"的配合方式（E 的驱动范式）

1. E 用既有 `live` 装置启动 **Java 应用**（携带 Java 侧旋钮）与逐次调用 **worker**（`I.worker_once(env_extra={…})` 携带 Python 侧旋钮）。
2. **注入只在替身层**：HTTP 受理、幂等/T13、版本校验、媒体授权、任务状态机、T12 领取/续租/失败与退避、`processing_revision`/`input_revision` 守卫**全部是真实生产代码路径**。
3. **失败持久化**看 T12（`async_jobs.status`/`last_error`/`attempt_count`）与 T05/T06 的业务状态列；**无脏成功**看 `media_objects` 无 `available` 脏行、`skin_assessments` 无 `report_ready`、`care_plans.generation_status ≠ 'ready'`、`member_access_grants` 无越权行。
4. **重试/恢复**：关闭注入后再跑 worker，应正常收敛到成功态（已有 IT 覆盖 Java 上传与 Python 结果图两侧）。
5. **证据分级**：全部为 `doubles_pass`；`assert_claimable("real_pass")` 在含替身时抛错（E 既有机制），**不得**据此宣称真实供应商通过。

---

## 5. SC-02-09 与 SC-02-10 的专用缝（已实现于 `181676d`，orchestrator 已独立核验）

### 5.1 SC-02-09：一次性有界"先算后等"迟到返回 barrier

**为什么需要它**：第一版 `MVP_D_SKIN_DOUBLE_HOLD`（进程级 hold）只是立即抛 `ProviderUnavailable` 并重排队，被重驱时会**重新读取当前 DB 输入**，因此它证明的是"陈旧代次被忽略"，**不是**"旧版本已算出的结果迟到返回"；Oracle 据此判 BLOCKER，总协调裁定同此。

**为什么该交错可达（orchestrator 读码取证，更正我此前"结构性不可达"的错误论证）**：我先前只考虑"同一执行者原子完成"，未覆盖**租约过期后由另一执行者接管同一旧任务**。源码证据：`runtime/expire.py:41-47` 把 `status='running' AND lease_until < CURRENT_TIMESTAMP` 的任务重置为 `queued`（`recover_expired` 在 `:87`）；`runtime/claim.py:26-41` 接管时改写 `lease_owner` 并 `lease_revision+1`（推进围栏令牌）；`runtime/complete.py` 守卫 0 行 → `StaleGeneration` 且**整体回滚**；`handlers/assessment_analyze.py:176-190` 捕获 `StaleGeneration` 记 `analyze.fenced_write_stale`（"lease lost; business write rolled back"）后返回 None；`_publish:705-727` 另有 `processing_revision`/`report_ready` 双重守卫。**未拆原子事务、未放宽 A02 门禁、未改任何业务规则、未关闭租约机制。**

| env | 值域 | 默认 | 语义 |
|---|---|---|---|
| `MVP_D_DOUBLE_LATE_BARRIER` | 严格布尔 `1/true/yes/on` \| `0/false/no/off` | `false` | 开启"先算后等"迟到返回 barrier（作用于 `FaceDouble.quality` 的首个命中标记调用） |
| `MVP_D_DOUBLE_LATE_BARRIER_DIR` | 目录路径（**barrier=true 时必填**） | 空 | barrier sentinel 目录；**必须每 RUN_ID 独立**。空/未设而 barrier=true ⇒ **加载期抛 `ProviderConfigError`**（消息：`barrier=true requires an explicit dedicated directory (per-RUN_ID isolation; no shared default allowed)`）。**不再回退共享临时目录**（`default_late_barrier_dir()` 仅供显式构造/测试，env 装配路径绝不会使用） |
| `MVP_D_DOUBLE_LATE_BARRIER_SHA256` | **64 位 hex**（barrier 开启时**必填**） | 空 | 命中标记 = **上传照片内容的 sha256**（不改端口签名，E 可黑盒控制"哪一次调用被拦"） |
| `MVP_D_DOUBLE_LATE_BARRIER_TIMEOUT_SECONDS` | 整数 **≥1** | `30` | 等待上限；超时**清理 sentinel 并抛既有 `ProviderUnavailable`**（走既有可重试路径，绝不永久挂起） |

**协议（`providers.py:163-229` 的 `LateReturnBarrier`）**
- **先算后等**：`compute_then_wait(images, result)` 返回调用方**已算好**的旧结果，释放后**不重算**（`FaceDouble.quality:262-276` 先构造 `QualityResult` 再等待）。
- **一次性**：首次命中用 `os.open(consumed, O_CREAT|O_EXCL|O_WRONLY)` 建 sentinel 后阻塞；后续命中遇 `FileExistsError` **立即返回** ⇒ **接管者 B 不被阻塞**。
- **释放**：向 `<DIR>/released` 写入任意内容。
- **有界 + 自清理**：`time.monotonic()` deadline + 0.1s 轮询；`finally` 中删除 `consumed` 与 `released` ⇒ **无残留**影响后续测试。
- **不写任何 DB 业务表**：状态只在文件（`providers.py` 中 `engine|connect|execute|text(` 计数为 0，已核实）；等待发生在 provider 调用期间，此时**不持有 PG 事务/行锁**（`_mark_analyzing` 是调用 provider 之前已提交的自有短事务）。
- **生产禁用与 fail-fast**：4 个旋钮均登记进 `DOUBLE_INJECTION_SWITCHES`，受既有启动守卫覆盖。orchestrator 亲验：`APP_ENV=production` + barrier（含 DIR 与 SHA256）→ **rc=1** 且消息列明 `switches=['MVP_D_DOUBLE_LATE_BARRIER','MVP_D_DOUBLE_LATE_BARRIER_DIR','MVP_D_DOUBLE_LATE_BARRIER_SHA256']`；fail-fast 各组均 **rc=1** 且消息含值域：**缺 DIR**（`barrier=true requires an explicit dedicated directory`）、缺 SHA256 / `SHA256=zz`（`expected 64-char hex sha256 of the marked image (barrier enabled)`）、`TIMEOUT_SECONDS=0` 或 `=abc`（`expected integer >= 1`）；dev + barrier + 合法 DIR/sha → **rc=0**。

**已由真实围栏路径实测的子时序**（`tests/test_seam_boundary_repro.py:159-283`，**未种库伪造时序状态**：`_seed_marked_case` 只铺初始 fixture；领取/回收/接管/完成全部走真实 `claim_batch`/`recover_expired`/`handle`/`complete_success`）：

```
A_in_barrier        {owner=A, lease_revision=1, attempt_count=1, assessment=analyzing}
after_recover_expired {status=queued, lease_owner=null, lease_revision=2}
B_takeover          {owner=B, lease_revision=3, attempt_count=2}
B_committed         {job=succeeded, assessment=needs_retake}
A_released_old_result {HandlerResult}        ← A 拿到入 barrier 前算好的旧结果
A_fenced            {StaleGeneration}        ← 既有租约围栏拒绝，业务写整体回滚
final               status=needs_retake, report_id=null, report_payload=null,
                    member_id=null, report_ready 行数=0, barrier 无残留 sentinel
```
关键断言为 `with pytest.raises(StaleGeneration): complete_success(engine, claim_a, handler_result_tx=result_a.business_tx)`；短租约经既有 `lease_seconds` 参数自然过期（单次 handle 无续租线程），**未关闭续租机制**。

**端到端已打通（工装 b40，orchestrator 亲跑 `ALL PASS 41/41`）**：总协调要求的 Java HTTP 步骤（`PUT …/photo-versions/2` → J2 → `report_ready(v2)`）已由 B 自有验收工装的新检查 **b40**（`backend/tests/support/b-checks-3.sh:384-503`）以**真实 HTTP + 真实 worker/租约/围栏**驱动，**未以改 DB 伪造时序**（新增区第 315 行起 `UPDATE|INSERT INTO|DELETE FROM` 零命中，`psql_b` 全为 SELECT）。实测中间态：

| 步骤 | 实测 |
|---|---|
| M3-A01（真实 multipart HTTP） | `202`；`data.status=queued`；T05 `current_photo_version=1, processing_revision=1`；J1 入队 `lease_revision=0` |
| Worker A 进入 barrier | `<DIR>/consumed` 出现；T05 `analyzing`；J1 `owner=A, lease_revision=1, attempt_count=1` |
| 租约自然过期 + `--recover` | J1 `status=queued, lease_owner=null, lease_revision 1→2` |
| Worker B 接管（**带同一组 barrier env**，证明一次性语义） | J1 `succeeded, attempt_count=2`；T05 `needs_retake` |
| M3-A02（真实 HTTP 补拍 v2） | `202 data.photoVersion=2`；T05 `current_photo_version=2, processing_revision=2`；J2(rev=2) 入队 |
| Worker C（正常 env，有界多轮） | T05 `report_ready`、`report_photo_version=2`；快照 `report_id`/`member_id` 记录 |
| 写 `<DIR>/released` 释放 A | A 日志出现既有 **WARNING `job.complete_stale_generation`**（`dfence` 权威告警） |
| 最终断言 | v2 快照 `report_id`/`report_payload`/`report_summary`/`member_id`/`report_photo_version` **逐值未变**；`report_ready` 行数 **=1**；该 gimbal T05 行数 **=1**；`members` 行数不变；`<DIR>/consumed` 与 `<DIR>/released` **均已清理** |

**E 可照抄的复验序列（b40）**

```text
0. 可选排空：循环 `python -m mvp_worker --once`（正常 env）至
   count(status='queued' AND available_at<=now())=0（仅真实消费，不改 job 业务列）
1. front = png(header + "b40-marker-<rand>")；marker = sha256(front 的字节)
2. POST /api/v1/skin-assessment-tasks   (Authorization: Bearer <gimbal>, Idempotency-Key)
   -F metadata=@meta;type=application/json  {"photoVersion":"1","captureSessionId":…,"consentEvidenceRef":…}
   -F front/left/right=@*.png            → 202，取 data.taskId
3. 后台启动 Worker A（--once）：
   env MVP_WORKER_PG_DSN=<accept-db> MVP_A_STORAGE_DEV_DIR=<与 app 同一 storage-root>
       MVP_WORKER_CLAIM_BATCH=1 MVP_WORKER_LEASE_SECONDS=2 MVP_WORKER_RENEW_INTERVAL_SECONDS=600
       MVP_D_DOUBLE_LATE_BARRIER=true MVP_D_DOUBLE_LATE_BARRIER_DIR=<DIR>
       MVP_D_DOUBLE_LATE_BARRIER_SHA256=<marker> MVP_D_DOUBLE_LATE_BARRIER_TIMEOUT_SECONDS=180
4. 等 <DIR>/consumed 出现；断言 T05=analyzing、J1 owner=A/lease_revision=1/attempt_count=1
5. sleep 2.5s（让短租约自然过期）；python -m mvp_worker --recover；
   断言 J1 status=queued / lease_owner=null / lease_revision 推进
6. Worker B（--once，**同一组 barrier env** + MVP_D_FACE_DOUBLE_QUALITY=needs_retake
   + MVP_D_FACE_DOUBLE_REQUIRED_VIEWS=front）；断言 J1 succeeded/attempt_count=2、T05=needs_retake
7. PUT /api/v1/skin-assessment-tasks/{taskId}/photo-versions/2  (gimbal, Idempotency-Key)
   -F metadata=@m2;type=application/json {"expectedPhotoVersion":"1","replacedViews":["front"]}
   -F front=@new.png                     → 202 data.photoVersion=2；
   断言 T05 current_photo_version=2 / processing_revision=2；J2(rev=2) 入队
8. Worker C：循环 `python -m mvp_worker --once`（正常 env；建议
   MVP_WORKER_BACKOFF_BASE_SECONDS=0、MVP_WORKER_CLAIM_BATCH=5）至 T05=report_ready
   （约 2 轮：reliable_new 先建档→重搜发布；循环上界 60 次 × 0.4s）
   快照 report_id / report_payload / report_summary / member_id / report_photo_version(=2)
9. : > <DIR>/released ；等 A 进程退出
   grep A 日志 'job.complete_stale_generation'（或 analyze.fenced_write_stale / StaleGeneration）
   断言：第 8 步快照逐值未变；report_ready 行数=1；该 gimbal T05 行数=1；members 行数不变；
        <DIR>/consumed 与 <DIR>/released 均不存在
```

> **等价性说明**：库中**无 `skin_reports` 表**（报告落 `skin_assessments.report_id`/`report_payload`），故 b40 以「该 gimbal `skin_assessments` 行数=1 + `report_ready` 行数=1 + 快照逐值一致」等价断言「members、报告行数不变」。
> **双重围栏（如实记录）**：A 的迟到结果先在 `archive_result_images` 的 `fenced_business_tx` 抛 `StaleGeneration`（`handle` 内捕获，**DEBUG 级默认不落日志**），随后 `process_job` 的 `complete_success` 守卫再次拒绝并落 **WARNING `job.complete_stale_generation`**；b40 断言后者。
> **进程卫生**：`run-acceptance-b.sh` 的 `cleanup()` 会读 `$TMP/b40a.pid` 强制回收后台 Worker A（kill → 最多 10s 等待 → `kill -9`），随后执行既有 `stop_worker`/`stop_app`。

### 5.2 SC-02-10：确定性到达既有终态失败

**为什么需要它**：E 的 `af348c4` 把 SC-02-10 由 PASS 纠正为 `seam_pending`，因其现用的 `MVP_D_SKIN_PROVIDER=aliyun_skin`（`ProviderNotActivated`）**只触发瞬态重试**，黑盒无法确定到达测肤**终态失败**与 `failure_code`。

| env | 值域 | 默认 | 语义 |
|---|---|---|---|
| `MVP_D_SKIN_DOUBLE_INVALID` | `none` \| `unknown_metric` \| `out_of_range` \| `bad_unit` | `none` | 让 skin 替身返回违反**既有**白名单/基线校验的指标 |

- **走既有路径**：替身返回违约指标 → 既有 `_validate_metrics` 抛 `_ContractViolation` → 既有 `_terminal(code="PROVIDER_CONTRACT_VIOLATION")`。**未改 `_transient_or_terminal`/`_terminal`/`_validate_metrics`/`_publish`，未新增业务错误码，未改变生产失败规则**（`assessment_analyze.py` 整体 diff 为空）。
- **确定性**：三形态各 **`attempt_count=1`**（1 轮到达终态，不依赖 attempt 预算耗尽）；`failure_detail.reason` 实测分别为 `$.metrics[3].name: not in approved baseline`（`unknown_metric`）、`$.metrics[3].value: out of approved range`（`out_of_range`）、`$.metrics[3].unit: not in approved baseline`（`bad_unit`）。
- **无脏成功**：T05 `status='failed'`、`failure_code='PROVIDER_CONTRACT_VIOLATION'`、`report_id`/`report_payload` 为 null；T12 `failed` 且 `retryable=false`；**无后继 job**（该 assessment 的 `async_jobs` 行数 = 1，即未产生 `identity.enroll`/`plan.generate`）。
- **投影一致性**：`FailureProjection.PUBLIC_FAILURE_CODES` 含 `PROVIDER_CONTRACT_VIOLATION` 且 `retryable(code)→false`（`FailureProjection.java:45-54,66-82`）⇒ M3-A03 的 `failureCode` 与 DB 同值、`failure_detail` **不投影**（无内部诊断泄漏）。
- **端到端已验证（工装 b41，orchestrator 亲跑 PASS）**：真实 HTTP M3-A01 受理 → 一轮 `--once` 即终态；实测 T05 `status=failed`、`failure_code=PROVIDER_CONTRACT_VIOLATION`、`failure_detail.reason="$.metrics[3].value: out of approved range"`、`report_id`/`report_payload=null`；T12 `failed`、`attempt_count=1`、`last_error={"code":"PROVIDER_CONTRACT_VIOLATION","message":"skin provider contract violation","retryable":false}`；该 taskId 的 `async_jobs` 行数 **=1**（无 `identity.enroll`/`plan.generate` 后继）。真实 HTTP **M3-A03 GET**：`200`、`data.status=failed`、`failureCode=PROVIDER_CONTRACT_VIOLATION`、`retryable=false`、`reportId=null`、`requiredViews=[]`，响应**不含** `failure_detail`/`reason`/`stack`；**GET 前后 `async_jobs` 计数不变**（查询不触发新分析）；再次 `--once` 同 env 仍 `failed` 且 `attempt_count` 不增长；对照复位（不设旋钮）新 A01 经有界循环可达 `report_ready`。
- **默认关闭回归**：不设该旋钮时既有发布路径正常（已有专门回归测试）。
- **生产禁用**：已登记进 `DOUBLE_INJECTION_SWITCHES`；orchestrator 亲验 `APP_ENV=production` + `MVP_D_SKIN_DOUBLE_INVALID=out_of_range` → **rc=1**，`MVP_D_SKIN_DOUBLE_INVALID=bogus` → **rc=1** 且消息列出完整值域。

```bash
# 最小调用（worker 侧）
env $BASE MVP_D_SKIN_DOUBLE_INVALID=out_of_range .venv/bin/python -m mvp_worker --once
# 复位
env $BASE .venv/bin/python -m mvp_worker --once
```

---

## 6. 已知边界与持续披露（复验前必读）

1. 注入为**进程级**，非 task/RUN_ID 级 ⇒ 必须隔离测试实例/DB/队列，禁止并行污染。**唯一带输入键控的例外**：SC-02-09 的 barrier 以**上传照片内容 sha256** 为命中标记且**一次性**（首次命中建 `consumed` 后阻塞，后续命中立即返回），故同进程内只拦截首个命中调用——这是为让"接管者不被阻塞"而刻意设计，**不等于** task/RUN_ID 级键控。
1b. **barrier 超时后的语义**：`consumed`/`released` 在释放或超时后**同时删除**（无残留）；因此同一 job 若在超时后又被重试，会**再次阻塞一个 timeout**——有界、不永久挂起，但复验方应把 `MVP_D_DOUBLE_LATE_BARRIER_TIMEOUT_SECONDS` 设为足以覆盖整个驱动序列的值（B 的工装用 180）。
1c. `MVP_D_DOUBLE_LATE_BARRIER_TIMEOUT_SECONDS` 传**非数字**或 `<1` 均抛 **`ProviderConfigError`**（`_strict_env_int`，消息含变量名与 `expected integer >= 1`）；异常类型已与其他注入错误统一（原为裸 `ValueError`，已修）。两者都在启动前失败，不会进入运行期。
1d. barrier **必须**显式指定 `MVP_D_DOUBLE_LATE_BARRIER_DIR`（每 RUN_ID 独立目录）：为空即加载期 fail fast，**不再回退共享临时目录**，故不存在"两个并跑实例互相消费 sentinel"的串扰路径（原回退行为已按 Oracle IMPORTANT 修掉）。
2. `search=matched` 的**黑盒**驱动受限：`FaceDouble.face_subject_ref` 无 env 旋钮（未擅自新增），env 只能置分类；要驱动"可靠匹配既有成员"需既有 member 的 `face_subject_ref` 已知。若 E 需黑盒 matched（影响 **SC-02-07**，不属本 6+1 项），需追加 `MVP_D_FACE_DOUBLE_FACE_SUBJECT_REF`（待裁定）。
3. `execution_face`/`revalidation_face` **无专用端到端 IT**（其上传端点属 C 域）；机制同构、值域由 `MediaPurpose.values()` 派生。Oracle 判为**非阻塞代码项、属最终证据缺口**，由 E 用 C 的 HTTP 端点补验，B 不改 C。
4. Java 侧接受 `assessment_result` 值，但结果图实际由 **Worker** 写入 ⇒ Java 侧对该 purpose 的注入通常不命中上传路径（Oracle 判可接受冗余）。
5. **真实提供方仍未接入**；所有缝仅对 doubles 生效，生产 fail-closed。
6. Java 正式生产信号约定仍是 profile `prod` 或 `app.env=production`；字面 profile 名 `production` 属既有非阻塞硬化项（见 Swagger 轮 Oracle SUGGESTION）。
7. 共享测试基建：`worker-python/tests/conftest.py` 的 session fixture 会调 `backend/deploy/dev/migrate.sh`（内含 `mvn flyway:migrate`）；`WorkerConfig.check_dsn` 只读 `MVP_A_PG_DSN`（默认 55432）。两者属共享基建，B 未改，归属待总协调裁定。
8. SC-02-08 无需独立注入（复用 `needs_retake` 进入补拍态）；其"同 taskId 新版本成功、跨云台拒绝"由**未修改的** Java 路径保证（`AssessmentAcceptanceService.java:223-284`）。
