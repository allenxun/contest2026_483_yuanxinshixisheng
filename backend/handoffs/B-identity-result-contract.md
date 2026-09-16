# B → D 冻结合同：Java 生产的身份结果（Java→Worker Identity Result Contract）

**状态**：**已冻结**（orchestrator，2026-09-16）。D 与总协调可直接照此实现消费端，
**不需要猜测任何未提交的实现**——数据面（写到哪、什么形状、何时可见）与调用面（方法签名、
输入输出、失败语义）都已由**已提交的 Java 类型**固定，并有测试锁定。
**依据**：总协调 2026-09-16 裁定——D 将移除 Worker 人脸调用、人脸库登记与 `face_subject_ref`
双写，改为**只消费 Java 冻结的身份结果**；Java 是人脸库唯一调用/写入方。

> 本文档中的**每一个行号都由脚本从真实文件实时计算**（`locators.txt`，43 个定位符 0 个未解析），
> 不是人工转录。若代码变动导致行号漂移，以符号名为准。

---

## 1. 承载位置（裁定：**T01 `members` 现有列，零公共迁移**）

| 承载 | 位置 | 事实依据 |
|---|---|---|
| 身份命名空间 | `members.identity_namespace` (text) | `backend/web-java/src/main/resources/db/migration/V1__create_tables.sql:76–92` |
| 人脸主体引用 | `members.face_subject_ref` (text) | 同上 |
| **冻结身份结果本体** | `members.identity_summary` (jsonb NOT NULL DEFAULT `'{}'`) | 同上；CHECK `backend/web-java/src/main/resources/db/migration/V1__create_tables.sql:90` |
| 成员状态 | `members.status` (`active`\|`disabled`) | `ck_members_status` |
| 建档来源任务 | `members.created_from_assessment_id` (uuid, 可空, FK 见 V2) | `fk_member_created_from_assessment` |
| 唯一性保证 | **部分唯一索引** `uq_members_identity (identity_namespace, face_subject_ref) WHERE 两列均非空` | `backend/web-java/src/main/resources/db/migration/V1__create_tables.sql:94–96` |

**为什么不是其它候选**（逐条给代码事实，避免重复讨论）：
- **T05 `skin_assessments.identity_result`（`backend/web-java/src/main/resources/db/migration/V1__create_tables.sql:186`）不由 Java 写**。它是 **Worker 独占列**，
  Java 自己的代码逐字记载：`AssessmentRepository.java:14`「绝不触碰 worker 独占列
  （member_id、report_*、identity_result…）」、`PhotoVersions.java:21`「worker 通过 identity_result 发布
  （Java 只读）」；且它是 M3-A03 `requiredViews` 投影的**唯一权威通道**
  （`FailureProjection.java:18`）。若 Java 也写它，就制造了本合同要消除的**同列双写**。
- **T12 `async_jobs.payload`**：`contracts/schemas/payload-identity-enroll.json:17` 是
  `additionalProperties:false`、`:19-22` `schema_version const 1` ⇒ 扩展需改 **A 域契约**；
  且 payload 全仓**只在入队时写一次**（无生产代码 `UPDATE async_jobs SET payload`），
  与"Java 是结果生产方、D 是消费方"的方向相反。**否决**。
- **B 自有新表（V3）**：迁移目录归 **A 独占**（`backend/doc/tasks/COMMON.md:16`，最新 V2），
  且会引入 T01 之外的第二事实源、迫使 `MemberAccessGrantService` 的只读定位改写。**否决**。
- **T02 `member_access_grants.verification_summary`**：粒度是"账号—成员一次授权"，
  只在 M1-A01 产生，无法承载"已建档但尚未授权"的身份结果。**不能承载主要信息**。

⇒ **本合同不需要任何公共迁移、不需要任何契约变更、不需要新增 `ErrorCode`。**

---

## 2. `schema_version`（**数据库级强制**，不是约定）

`backend/web-java/src/main/resources/db/migration/V1__create_tables.sql:90` 的 `ck_members_identity_summary_schema` 要求 `identity_summary`
要么等于 `'{}'::jsonb`，要么是 **object 且含 `schema_version` 且其类型为 number**。
本合同冻结 **`schema_version = 1`**（整数），由 `IdentityResultContract.SCHEMA_VERSION` 定义。
缺该键或写成字符串 ⇒ **INSERT 被数据库拒绝**，不会静默通过。

---

## 3. `identity_summary` 的冻结形状（字段名与类型逐字固定）

由 `IdentityResultContract.buildIdentitySummary(command, result)` 构造（已提交、已 javac 验证）。
**与 D 既有 `_identity_summary()`（`backend/worker-python/src/mvp_worker/handlers/identity_enroll.py:331–361`）向后兼容**：保留 `schema_version` /
`enrollment` / `reference_media` 三个顶层键与 `enrollment` 内既有六键，只**追加**围栏与审计字段。

```jsonc
{
  "schema_version": 1,                       // integer，DB CHECK 强制
  "enrollment": {
    "correlation_id":  "<uuid string>",      // 既有键；= enrollCorrelationId(ns, assessmentId)
    "provider_request_id": "<uuid string>",  // 既有键；= providerRequestId(correlation_id)
    "provider_config_revision": "<string>",  // 既有键；审计用，绝不含凭据
    "registered_at": "2026-09-16T04:05:06Z", // 既有键；ISO-8601 UTC **秒精度**、Z 结尾
    "source_assessment_id": "<uuid string>", // 既有键；T05 主键
    "photo_version": 3,                      // 既有键；integer(>0)，**围栏**
    "processing_revision": 7,                // 追加；integer(>=0)，**围栏**
    "phase": "enrolled",                     // 追加；见 §4 状态机
    "candidate_entity_id": "<uuid string>",  // 追加；**恒等于** members.face_subject_ref
    "policy_version": "search-v1",           // 追加；本次搜索判定所用的服务端阈值策略版本
    "model_version": "buffalo_l@insightface-0.7.3",  // 追加
    "library_revision": 12                   // 追加；integer(>=0)，本次判定所依据的人脸库修订号
  },
  "reference_media": {                      // 既有键，**必须保留**（见下方硬性要求）
    "front": "<mediaId string>",
    "left":  "<mediaId string>",
    "right": "<mediaId string>"
  },
  "decision": {                             // 追加段
    "classification": "reliable_new_candidate_enrolled" | "matched_existing",
    "search_decision": "matched" | "no_match" | "uncertain",   // face-service 的保守三态
    "matched_subject_ref": null | "<uuid string>"              // 仅 matched_existing 时非 null
  }
}
```

**硬性要求（跨包耦合，最容易被忽视）**：`reference_media` 的三个值**必须**是 media id 字符串且出现在
`identity_summary` 中——因为 D 的 `backend/worker-python/src/mvp_worker/handlers/media_cleanup.py:71–76` 用
`WHERE CAST(identity_summary AS text) LIKE '%' || :media_id || '%'` 判断参考照是否仍被引用。
若 Java 写的摘要缺失或改写这些 id，**参考照会被清理流程误删**。该耦合已由实现侧测试锁定。

**空值语义（逐字段）**：
| 字段 | 可否为 null | null 的含义 |
|---|---|---|
| `schema_version` | **否** | —— （DB CHECK 强制存在且为 number） |
| `enrollment.*` 全部 | **否** | 缺任一字段即视为合同违规；消费方**必须拒绝**而不是按默认值继续 |
| `reference_media.front/left/right` | **否** | 三视角齐全是登记前提 |
| `decision.matched_subject_ref` | **是** | `null` ⇒ 本次是**新建登记**（`classification=reliable_new_candidate_enrolled`）；非 null ⇒ 复用既有主体（`matched_existing`），此时该值**等于** `face_subject_ref` |
| `decision.search_decision` | **否** | 即使 `no_match`/`uncertain` 也必须如实记录，供审计"为何判定为新人候选" |
| `members.created_from_assessment_id` | **是** | `null` ⇒ 非由测肤任务建档（例如运维补录）；非 null 时必须满足 V2 的外键 |
| `members.profile` | 本轮**不写**（保持 `'{}'`） | 空占位合法（`ck_members_profile_schema`） |

**`decision.classification` 刻意没有 `reliable_new`**：依据 `后端详细设计-V1-MVP.md:657`
「歧义不归档，**未命中只成为新人候选**」与 `:663`「自动新人判定阈值、活体条件未通过 PoC，
则不得开启真实自动登记」。本合同只记录**已经完成受控登记之后**的结果，
`reliable_new_candidate_enrolled` 的字面含义是"作为新人候选被受控登记"，**不是**"算法可靠判定为新人"。

---

## 4. 状态机（`enrollment.phase`，取值由 `IdentityEnrollmentPhase` 冻结）

| 取值 | 写入方 | 载体 | 含义 |
|---|---|---|---|
| `enroll_pending` | **D 的 Worker** | **T05** `identity_result.phase` | 已判定需登记、任务已入队（既有语义，`backend/worker-python/src/mvp_worker/handlers/assessment_analyze.py:459` 内 `:478`） |
| `enroll_started` | **D 的 Worker** | **T05** `identity_result.phase` | 登记已开始、外部结果未知（既有语义，`backend/worker-python/src/mvp_worker/handlers/identity_enroll.py:46–53`） |
| `enrolled` | **Java** | **T01** `identity_summary.enrollment.phase` | 远端登记本次确认成功 **且** 成员行已提交 |
| `enrolled_reconciled` | **Java** | **T01** `identity_summary.enrollment.phase` | 远端登记在**此前**尝试已成功（超时/崩溃后按同一确定性 ref 对账命中），本次只补写本地成员行 |

**关键裁定：Java 侧不持久化 in-flight 标记。** 理由：`face_subject_ref` 由
`IdentityResultContract.candidateEntityId(ns, assessmentId)` **确定性派生**（§5），
因此"远端成功 + 本地失败"可用同一 ref 调 `FaceIdentityPort.get` 对账后安全重试，
**不需要**先写一个待决成员行。刻意**不**采用"先插行再翻 `status`"的方案：
`members.status` 取值域只有 `active|disabled`，而 `数据架构设计-V1-五模块-MVP.md:160` 明确
「`disabled` 是运维状态，不代替授权撤销」——把它当待决标记会污染既有语义。
依据 `后端详细设计-V1-MVP.md:659`「网络超时先按同 EntityId 查询对账，不生成另一 ID 盲目重试」、
`:661`「外部成功但业务取消的人员资源保留受控对账，确认无业务引用后再清理」。

`IdentityEnrollmentResult` 的构造器**强制** `phase.isJavaTerminal()`，
即 Java 产出的结果只能是 `enrolled` / `enrolled_reconciled`；传 `enroll_pending`/`enroll_started`
会直接抛 `IllegalArgumentException`（已提交类型的编译期+运行期双重约束）。

---

## 5. 跨语言稳定派生（**已逐字节证明一致**）

权威来源 `backend/contracts/decisions-notes.md:41-53`：
`FIXED_NS = uuid5(NAMESPACE_DNS, "contest2026_483_yuanxinshixisheng") = f988d041-6031-5120-8075-f90b6b05553e`，
「两侧硬编码，**禁止各算各的输入差异**」。Java 侧复用 A 域既有的 `jobs/Uuid5.java`
（RFC 4122 UUIDv5 / SHA-1，与 Python `uuid.uuid5` 字节一致），**不另造实现**。

| 派生键 | 输入字符串 | Python 定义 | Java 定义 |
|---|---|---|---|
| `candidate_entity_id`（= `face_subject_ref`） | `face-candidate:<ns>:<assessmentId>` | `backend/worker-python/src/mvp_worker/handlers/dshared/constants.py:27` | `IdentityResultContract.candidateEntityId` |
| `correlation_id` | `enroll-correlation:<ns>:<assessmentId>` | 同文件 `:31-32` | `.enrollCorrelationId` |
| `provider_request_id` | `enroll-request:<correlationId>` | 同文件 `:44-45` | `.providerRequestId` |
| `namespace_owner_id`（T12 `owner_id`） | `identity-namespace:<ns>` | 同文件 `35` | `.namespaceOwnerId` |

**实测证据**（orchestrator 亲跑，同一输入 `ns="mvp-ns-1"`、
`assessmentId=2f6a2b0e-3c1e-4d2b-9b57-1f4c3a5b6d78`）：四个派生值 Java 与 Python **逐字节相同**
（`candidate=4a4af762-a1a8-5d8d-b4f5-3cdb6664714f`、`correlation=eef03bfb-b500-5e45-85cd-50932e42df86`、
`request=2caa3a85-a4cb-5467-825f-768a9f771393`、`owner=36b44f2b-3f0b-54b9-8c59-90f9811040e9`）。
⇒ **Java 接管生产端不会破坏与既有数据的对账**；过渡期两侧派生可并存而不产生第二个 subject。

**已知的 A 域不一致（如实上报，orchestrator 不擅自修改）**：
`jobs/JobEnqueuer.java:127-129` 的 `identityNamespaceOwnerFor(ns, faceSubjectRef)` 是
**per-subject** 派生，`decisions-notes.md:33` 亦写 per-subject；但 Python 实现
（`constants.py:35`，docstring 明写「用 namespace 级 owner 让 `uq_job_identity_enroll`
在整个 namespace 上串行」）与 `后端详细设计-V1-MVP.md:736` 都是 **namespace 级**。
该 Java 方法**全仓调用方为 0（死代码）**，故当前无实际影响；但若将来被误用，
会让同一 namespace 并发多条未决登记、破坏 `backend/web-java/src/main/resources/db/migration/V1__create_tables.sql:474–476` 的串行化意图。
**请总协调裁定以 namespace 级为准并修正 `decisions-notes.md:33` 与该方法（均属 A 域）。**

---

## 6. 围栏（照片版本 / 处理代次）

Java 生产端**必须**在业务事务内以 `SELECT ... FOR UPDATE` 重读 T05 并校验**全部五条**，
与 D 既有权威范例 `backend/worker-python/src/mvp_worker/handlers/identity_enroll.py:74–89` 的 `_LINK_MEMBER` **逐条对齐**：

| # | 围栏条件 | 来源 | 不满足时 |
|---|---|---|---|
| 1 | `processing_revision = <命令值>` | T05 `backend/web-java/src/main/resources/db/migration/V1__create_tables.sql:184` | 不写成员行，抛围栏异常 |
| 2 | `current_photo_version = <命令值 photo_version>` | T05 `backend/web-java/src/main/resources/db/migration/V1__create_tables.sql:183` | 同上 |
| 3 | `status = 'analyzing'` | `ck_assessment_status` | 同上 |
| 4 | `candidate_entity_id` 与本次派生值一致 | 本合同 §5 | 同上 |
| 5 | `phase IN ('enroll_pending','enroll_started')` | T05 `identity_result`（D 写） | 同上 |

依据 `后端详细设计-V1-MVP.md:661`「如果任务输入已被补拍替换，**不能把旧登记结果归给新照片**」。
**同时修正一个既有缺口**：D 的 `backend/worker-python/src/mvp_worker/handlers/identity_enroll.py:46–53`（`_PERSIST_ENROLL_STARTED`）**只**校验
`processing_revision`、**未**校验 `current_photo_version`，且 `_load_assessment`（`:308-317`）是
**非锁定读**；本合同要求 Java 侧五条全查且在锁内，D 若保留该语句建议同步补齐（属 D 域，B 不改）。

---

## 7. 错误与重试语义（fail-closed，绝不伪成功）

| 情形 | Java 行为 | HTTP（若经业务入口） | D 侧应如何反应 |
|---|---|---|---|
| 人脸服务超时/网络/5xx/畸形 2xx | 抛 `ApiException(DEPENDENCY_UNAVAILABLE)`；**不写成员行** | 503，`retryable=true` | 可重试；重试会用同一确定性 ref 对账 |
| 人脸服务配置错误（401/缺键/桶不一致等） | 抛不可重试失败 | 503，`retryable=false` | **不要**重试，转人工 |
| 围栏不符（§6 任一条） | 不写成员行，抛围栏异常 | 409 族（由调用方决定） | 该任务输入已过期，**不得**把结果归给新照片 |
| 远端已登记但本地事务失败/崩溃 | **保留**远端 subject 供受控对账，**绝不**自动删除 | —— | 下次重试 `get(ref)` 命中 ⇒ `enrolled_reconciled` |
| `uq_members_identity` 冲突（并发/重试） | `ON CONFLICT DO NOTHING` + 回查既有行，`memberRowInserted=false` | 200 语义（幂等成功） | 视为成功，**不是**错误 |
| 1:N 搜索 `no_match` / `uncertain` | **绝不**产出 `reliable_new`；不登记 | —— | 按"未通过核验"处理 |

**绝不**：回退测试替身、把依赖故障降级成"人脸未通过"（403）、把 `null`/未知结果当成功、
在无证据时宣称"可靠新人"。

---

## 8. 幂等与对账规则（可直接实现）

1. `faceSubjectRef = IdentityResultContract.candidateEntityId(ns, assessmentId)`（**确定性**，跨重试稳定）。
2. **先** `FaceIdentityPort.get(faceSubjectRef)`：命中 ⇒ 跳过 `register`，相位 `enrolled_reconciled`。
3. 未命中 ⇒ `FaceIdentityPort.register(purpose, faceSubjectRef, referenceImage)`
   （客户端显式发 `on_exists=conflict`，既有主体**绝不被静默覆盖**）。
4. 远端调用**在事务外**（依据 `后端详细设计:659`「再锁外调用」）；**绝不**在持有行锁时调用人脸服务。
5. 本地写入：`INSERT INTO members (...) VALUES (...) ON CONFLICT (identity_namespace, face_subject_ref)
   DO NOTHING` + 回查（与 D 既有 `backend/worker-python/src/mvp_worker/handlers/identity_enroll.py:55–68` / `70–72` 同范式），
   由 `backend/web-java/src/main/resources/db/migration/V1__create_tables.sql:94–96` 兜底唯一性；**绝不**用应用层 check-then-insert（TOCTOU）。
6. T12 层面的"每 namespace 最多一条未决登记"由既有 `backend/web-java/src/main/resources/db/migration/V1__create_tables.sql:474–476` 保证
   （`owner_id` 用 §5 的 **namespace 级**派生）。
7. `identity_summary` 的写入与成员行插入在**同一事务**，因此不存在"行在而摘要缺"的中间态。

---

## 9. 可见性时点（合同核心）与**尚未接线**的如实声明

**可见性**：`IdentityEnrollmentResult` **只在成员行提交之后返回**。因此 `memberId` 与
`faceSubjectRef` 一旦出现在结果中，即保证 `members` 里已存在一行满足
`identity_namespace = ? AND face_subject_ref = ? AND status = 'active'` ⇒
Java 的只读定位（`MemberAccessGrantService.java:321–326`）与 D 的
`backend/worker-python/src/mvp_worker/handlers/assessment_analyze.py:106–108` / `695` **都能立刻查到**。
**绝不**返回"远端已登记但本地未提交"的中间态——那种情况必须抛异常让调用方重试对账。
两者均**绝不**投影到任何对外 HTTP 响应（`openapi.yaml:2343`「绝不投影 failure_detail /
identity_result 等内部诊断」），也**绝不**写入日志。

**如实声明：业务触发点本轮尚未接线。** 触发登记的判断（"测肤三视角质量合格 + 确认同人 +
1:N 未命中 ⇒ 新人候选"）位于 **D 的写域**（`backend/worker-python/src/mvp_worker/handlers/assessment_analyze.py:459`，以及 D 独占的
`web/assessments/**`）。因此本轮交付的是：**冻结合同 + Java 生产端实现 + 消费端只读边界 + 测试**，
`IdentityEnrollmentService.enroll(...)` 的**调用方待总协调裁定**（候选：D 的 assessments Java 代码、
或新增内部触发点）。在接线前，**不得宣称** M1-A01 真实身份闭环或 SC-02-07/CD-06 等场景完成
（`members.face_subject_ref` 无人填充时 M1-A01 恒 403 `FACE_NOT_VERIFIED`，属**诚实拒绝**）。

---

## 10. D 侧需要删除/替换的**精确调用点**（B 不改 D 的任何文件）

| # | 位置 | 现状 | D 需要做什么 |
|---|---|---|---|
| 1 | `backend/worker-python/src/mvp_worker/handlers/identity_enroll.py:169` | `face = face_port_for(ctx)` | **删除**（Worker 不再解析人脸端口） |
| 2 | `backend/worker-python/src/mvp_worker/handlers/identity_enroll.py:175` | `face.register_person(...)` | **删除**（登记改由 Java；Java 是人脸库唯一写入方） |
| 3 | `backend/worker-python/src/mvp_worker/handlers/identity_enroll.py:185` 与 `225` 内的 `backend/worker-python/src/mvp_worker/handlers/identity_enroll.py` 第二处 | `face.query_registration(...)` | **删除**（对账改由 Java 以同一确定性 ref 执行） |
| 4 | `backend/worker-python/src/mvp_worker/handlers/identity_enroll.py:225` | `_reconcile(...)` 整段 | **删除** |
| 5 | `backend/worker-python/src/mvp_worker/handlers/identity_enroll.py:55–68`（execute 在 `383`，冲突回查 `70–72`） | `_INSERT_MEMBER` 写 T01 | **删除**（消除 `face_subject_ref` 双写；范式由 Java 沿用） |
| 6 | `backend/worker-python/src/mvp_worker/handlers/identity_enroll.py:331–361` | `_identity_summary(...)` | **删除**，改为消费 §3 的冻结形状 |
| 7 | `backend/worker-python/src/mvp_worker/handlers/identity_enroll.py:361` | `_commit_enrollment(...)` | **改写**：只保留 T05 `member_id`/`identity_result` 归属；成员行改为**只读**消费 Java 已提交的 T01 行 |
| 8 | `backend/worker-python/src/mvp_worker/handlers/identity_enroll.py:74–89` | `_LINK_MEMBER` 五条件围栏 | **保留围栏**（§6 与之逐条对齐）；`candidate_entity_id` 改从 Java 结果取得 |
| 9 | `backend/worker-python/src/mvp_worker/handlers/assessment_analyze.py:260` / `278` / `351` | `face.quality` / `same_person` / `search_1n` | **删除**三项人脸调用 |
| 10 | `backend/worker-python/src/mvp_worker/handlers/assessment_analyze.py:381` | 本地派生 `candidate_entity_id` | **改为读取** Java 结果中的 `face_subject_ref`（§5 已证两侧派生逐字节一致，过渡期可并存） |
| 11 | `backend/worker-python/src/mvp_worker/handlers/assessment_analyze.py:459`（payload `485`） | `_handle_reliable_new` + 入队 `identity.enroll` | **删除或改写**：不再由 Worker 触发登记；改为调用/等待 Java 生产端（触发点见 §9 待裁定） |
| 12 | `backend/worker-python/src/mvp_worker/handlers/assessment_analyze.py:106–108` / `695` | `_SELECT_MEMBER_BY_REF` / `_find_member` | **保留**：这正是消费本合同的只读路径，几乎无需修改 |
| 13 | `backend/worker-python/src/mvp_worker/handlers/dshared/providers.py:121` / `129` / `779` | `FacePort.register_person` / `query_registration` / `build_face_port` | **随调用点删除**（用户明确："现有 Worker 人脸代码不得扩展为本方案实现"） |
| 14 | `backend/worker-python/src/mvp_worker/handlers/dshared/resolve.py:42` | `face_port_for` | **删除** |
| 15 | `backend/worker-python/src/mvp_worker/handlers/dshared/denqueue.py:38` / `122` | `EnrollSlotOccupied` / `enqueue_identity_enroll` | **随 job_type 退役删除**（若 `identity.enroll` 整体退役） |
| 16 | `backend/worker-python/src/mvp_worker/handlers/dshared/constants.py:27` 等派生 | 四个 uuid5 派生 | **保留且不得单方改动**：Java 已证与之逐字节一致；改动会使既有数据无法对账 |
| 17 | `backend/worker-python/src/mvp_worker/handlers/media_cleanup.py:71–76` | `_REF_MEMBERS` 对 `identity_summary` 的 LIKE 扫描 | **必须继续可用**：Java 保证 `reference_media` 三个 media id 出现在摘要中（§3） |
| 18 | `handlers/__init__.py:124` | `identity.enroll` handler 注册 | **若 job_type 退役则移除注册**（该注册表属 D，B 不改） |

### 10.1 D 的消费示例（只读，无需新接口）
```sql
-- 已知 namespace 与 face_subject_ref（来自 Java 冻结结果，或用 §5 的同一公式自行派生）
SELECT id, status, identity_summary
FROM   members
WHERE  identity_namespace = :ns
  AND  face_subject_ref   = :face_subject_ref
  AND  status = 'active';
-- 消费方必须：
--   1) 校验 identity_summary->>'schema_version' = 1（整数），否则**拒绝**而不是按默认值继续；
--   2) 只接受 enrollment.phase IN ('enrolled','enrolled_reconciled')；
--   3) 缺任一 §3 标记为"否"的字段即视为合同违规并拒绝；
--   4) 绝不把 identity_summary 或 face_subject_ref 投影到任何对外响应或日志。
```
D 现有的 `backend/worker-python/src/mvp_worker/handlers/assessment_analyze.py:106–108`（`_SELECT_MEMBER_BY_REF`）已是该查询的等价实现，可直接复用。

---

## 11. 受影响的 E 域验收（B 不改，上报总协调）

`identity.enroll` 退役会影响 E 的以下断言（共 6 处，逐行由脚本实测）：
- `backend/acceptance/driver/cd_chain.py:354`
- `backend/acceptance/driver/cd_chain.py:355`
- `backend/acceptance/driver/cd_chain.py:419`
- `backend/acceptance/driver/cd_chain.py:639`
- `backend/acceptance/driver/cd_chain.py:688`
- `backend/acceptance/tests/scenarios/test_sc02.py:392`

其中 `cd_chain.py:639` 与 `:688` 的 **CD-06 断言 `identity.enroll` job 逐个 succeeded**、
`:354-355`/`:419` 用 job id 差集绑定链路 ⇒ **D 退役该 job_type 后 CD-06 必然失败**，
须由 E 同步更新期望（E 域，B 不改）。`test_sc02.py:392` 断言"无 identity.enroll 后继"，
退役后该断言仍成立。

---

## 12. 公共文件结论（用户要求单列）

- **公共迁移**：**无**。T01 的列、部分唯一索引与 schema CHECK 全部已存在（§1）。
- **契约（`backend/contracts/**`）**：**未修改**。本合同不新增任何对外 HTTP 字段；
  `openapi.yaml` 无面向外部的身份结果字段（对外只有 `memberId`）。
- **A 域文件**：**未修改**。仅**使用**既有 `jobs/Uuid5.java`（public）；
  发现的两处 A 域不一致（`JobEnqueuer.identityNamespaceOwnerFor` 死代码 + `decisions-notes.md:33`
  per-subject 表述）已上报，**未擅自修改**（§5）。
- **D 域文件（`backend/worker-python/**`）**：**一个字节都没改**，只读测绘（§10）。
- **C 域文件（`web/care/**`）**：**未修改**。
- **E 域文件（`backend/acceptance/**`）**：**未修改**，只读列出受影响场景（§11）。
