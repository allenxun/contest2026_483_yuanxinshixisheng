# 契约决策记录（A 包建议，待总协调确认后回写主设计）

本文件收录影响**跨语言共享契约**的 gap 决议（源：`.coordination/A/decisions.md`
与任务书 §11 gaps）。均为 A 包在契约层的定稿建议，**不修改 backend/doc/**；
总协调确认后应回写 DD 3.2/9.1 与 API 文档。

## 1. NOT_IMPLEMENTED / 501（decisions #1）

未实现业务 API：HTTP **501** + 标准错误信封，`error.code =
NOT_IMPLEMENTED`（基础层新增码，建议加入 DD 3.2 错误码表），
`retryable=false`，`details` 可含 `apiId`/`plannedPackage`（仅调用方可见
信息）。绝不伪造 200。OpenAPI 中每个 contract-only 端点带
`x-implementation: contract-only` + `'501'` 响应（`NotImplementedEnvelope`
把 code 收紧为 NOT_IMPLEMENTED）。样例
`samples/envelopes/not-implemented-501.json`。

## 2. T13 principal 格式（decisions #2；digest gap 6）

`principal_type ∈ {app_account, gimbal}`；`principal_id`（text）：

- `app_account`：`"<account_uuid>:<installation_id>"`
- `gimbal`：`"<gimbal_uuid>"`

作用域：APP = accountId+installationId；云台 = gimbalId。OpenAPI
`ControllerRef.controllerType` 与之一致。

## 3. T12 owner_type 枚举 + identity_namespace 规则（decisions #3）

`owner_type ∈ {assessment, plan, notification, media, identity_namespace,
system}`；`owner_id` 为 UUID 文本（多态无外键，服务端校验归属）。

- `identity_namespace` 的 `owner_id` =
  **UUIDv5(FIXED_NS, `"<identity_namespace>:<face_subject_ref>"`)**
- `system` 的 `owner_id` = **UUIDv5(FIXED_NS, dedup_key)**

## 4. FIXED_NS 计算值（两侧硬编码，禁止各算各的输入差异）

    FIXED_NS = uuid5(NAMESPACE_DNS, "contest2026_483_yuanxinshixisheng")
             = f988d041-6031-5120-8075-f90b6b05553e

已用 `python3 -c "import uuid; print(uuid.uuid5(uuid.NAMESPACE_DNS,
'contest2026_483_yuanxinshixisheng'))"` 验证（NAMESPACE_DNS =
`6ba7b810-9dad-11d1-80b4-00c04fd430c8`，输入为**逐字节小写**的项目目录名，
Java 侧必须用同一输入字符串与 RFC 4122 UUIDv5（SHA-1）实现）。
`samples/jobs/job-handoff-example.json` 的 `owner_id =
b13b43dc-cfb1-5e89-8be2-72564704de79` 即
`uuid5(FIXED_NS, "system:echo:2f6a2b0e-3c1e-4d2b-9b57-1f4c3a5b6d78")`，
两侧测试应复现。

## 5. system.echo 最小跨语言测试任务（decisions #4）

`job_type=system.echo`；`dedup_key=system:echo:<uuid>`；payload
`{"schema_version":1,"message":"<text>","numbers_as_strings":["<bigint>",...]}`
（schema `schemas/payload-system-echo.json`，additionalProperties false）；
`input_revision="0"`。Python handler 先按 JSON Schema 校验 payload，再以
**正确 lease_owner + lease_revision** 完成；**stale-generation 完成（错误
代次）必须失败**——这是要求的测试场景。契约样例 `samples/jobs/`。

## 6. bigint-as-string / schema_version（decisions #9/#10）

跨语言 JSON（HTTP 与任务 payload）中 bigint（计数/revision/seq）一律十
进制字符串，pattern `^(0|[1-9][0-9]*)$`（无符号；signed 变体 MVP 不用）；
`schema_version` 用 JSON **整数**，各 payload schema `const: 1`。**本次全部
schema_version 常量选定为 1。**

## 7. payload_hash 规范化（decisions #11）

RFC 8785 JCS + SHA-256 小写 hex；组装规则（operation、路径参数、语义字
段、图片 part 名+逐 part 内容摘要、缺省展开、有序数组不排序、禁重复键）
见 `canonicalization.md`；参考实现 `scripts/jcs.py`，共享向量
`samples/canonicalization/vectors.json`（含中文、乱序键、缺省展开、bigint
字符串、数组顺序对、近碰撞对）。Java/Python 测试都必须复现向量。

## 8. 认证/媒体基础协议端点（decisions #6/#7；digest gaps 9/10）

`x-foundation: true`、不计入 27：`POST /api/v1/auth/sms-challenges`、
`POST /api/v1/auth/sessions`、`POST /api/v1/auth/session-refreshes`、
`DELETE /api/v1/auth/sessions/current`、`GET /api/v1/media/{mediaId}/content`。
媒体端点是**受控读取基础协议**（逐次鉴权、no-store、nosniff、统一 404
RESOURCE_NOT_VISIBLE、不重定向长效签名 URL）。手机号会话（`/auth/sessions`）
与云台设备会话（`/gimbal-sessions`）并存、命名空间区分。
**唯一双属性端点**：`POST /api/v1/gimbal-sessions` 同时是 27 业务编号
**M2-A01**（API 文档为准）和 decisions #7 列出的基础认证端点——OpenAPI 只
建**一个操作**，同时标 `x-api-id: M2-A01` 与 `x-foundation: true`、
`x-implementation: foundation-auth`（A 包实现，不打 501、不标
contract-only）。统计：业务操作 27 + 基础操作 6 = 33 标记、**去重后 32 个
操作 / 31 条路径**。

## 9. 其他契约级裁量（A 建议）

- **Idempotency-Key 覆盖面**：DD 3.1「业务写接口使用 Idempotency-Key」+
  DD §5 前言「写接口还使用 T13」→ 除 M2-A01（明文规定不用）和 M2-A02
  （心跳去重/顺序 = body 内 observationEpoch/Seq）外的全部业务
  POST/PUT/DELETE 均要求该头（含文档未逐一点名的 M2-A06、M3-A02、
  M5-A01、M2-A04、M4-A04）；文档点名者（M1-A03、M2-A08、M4-A05、M4-A06）
  不变。
- **connectionProof/pairingProof 载体**：API 文档 6.5 说「证明放认证上下文/
  请求头，协议由开发确定」→ OpenAPI 采建议头名 `X-Connection-Proof` /
  `X-Pairing-Proof`（标 x-detail: skeleton），M2-A06/M2-A04/M4-A03 按 DD
  §5 放 body。设备协议冻结前可能改名。
- **枚举编码未冻结者**（connectionStatus、心跳 powerState 扩展、incidents、
  capabilities/state、Plan/Report 正文、推送 registration 等）一律
  `x-detail: skeleton` 或用 UUID/BigintString/时间等已定标识占位，不发明
  业务取值。
- **信封 `data`**：列表端点统一 `{items, nextCursor:string|null}`；成功
  信封 `additionalProperties:false`（外层），`meta` 容忍新增字段。
- **payload 骨架的 x-owner-package 归属**（按任务书 B/C/D 模块映射）：
  assessment.analyze=D、identity.enroll=D、plan.generate=D（C 标注为执行
  接线方）、notification.deliver=B、media.cleanup=D（标注 B/C 人脸媒体由
  总协调定稿）。

## 10. JSONB schema_version 列决策 + 媒体授权 + 每请求认证复核（oracle round-1/2）

**背景**：DATA §4「所有 JSONB 有 schema_version，结构由服务端校验」。
V1 现以列级 CHECK 机器执行，三种形态（文件头有同款注释；`k = 'schema_version'`）：

- **F 形态** `col = '{}'::jsonb OR (jsonb_typeof(col)='object' AND col ? k AND
  jsonb_typeof(col->k)='number')`：NOT NULL DEFAULT '{}' 的阶段性摘要/观测列
  （空 = 尚未写入；一旦写入非空即必须是对象且版本为数字）。
- **N 形态** `col IS NULL OR (jsonb_typeof(col)='object' AND col ? k AND
  jsonb_typeof(col->k)='number')`：可空业务内容列。
- **S 形态** `(jsonb_typeof(col)='object' AND col ? k AND
  jsonb_typeof(col->k)='number')`：建行即须有内容的事实载荷。

> 类型加固（oracle round-2 R2-4）：仅 `jsonb_exists` 存在性不足——数组可含
> 字符串 `"schema_version"`，对象可含 `null`/字符串版本。非占位分支一律要求
> 对象、键存在（`col ? 'schema_version'`，否则缺键时 `jsonb_typeof(NULL)` 传播
> 为 NULL 会被 CHECK 放过）且版本为 JSON number（`schema_version: 1` 整数）。

逐列决策（27 个列级 CHECK；约束名即 `ck_<表>_<列>_schema`）：

| 表 | 列 | 形态 | 依据 |
|---|---|---|---|
| idempotency_requests | result_summary, verification_summary | F | 摘要 processing 阶段为空；IdempotencyService.completeSuccess/completeRejected 统一注入 schema_version |
| accounts | profile | F | T14 档案初始空 |
| members | profile, identity_summary | F | T01 建档前可空 |
| member_access_grants | member_summary, verification_summary | F | T02 授权快照 |
| gimbals | latest_observation, active_incidents | F | T03 未上报为空 |
| microcrystals | capabilities, latest_observation | F | T04（DATA 表注：capabilities 内含 schema_version） |
| skin_assessments | photo_versions, identity_result | F | T05 |
| skin_assessments | report_summary, report_payload | N | 可空、有值必须带版本（report_ready 另要求 payload 非空） |
| care_plans | input_snapshot, plan_summary | F | T06 |
| care_plans | plan_payload | N | ready 与否可空 |
| care_executions | plan_snapshot, latest_verification | F | T07 |
| care_executions | latest_observation, closure_manifest | N | 未上报/未收尾可空 |
| care_records | payload | **S** | T08 流水内容不可变、建行即有载荷 |
| notification_destinations | registration | F | T09（active 另要求非空，见 ck_destination_active_fields） |
| notifications | payload | **S** | T10「payload 仅最小通知」，建行即有内容 |
| media_objects | storage_metadata | F | pending 空；MediaService.markAvailable 写 `{"schema_version":1,...}` |
| async_jobs | payload | **S** | T12（既有 ck_job_payload_schema） |

**例外（自由格式，不加版本 CHECK）**：`async_jobs.last_error`、
`media_objects.last_error`、`notifications.last_error`、
`skin_assessments.failure_detail`、`care_plans.failure_detail`——诊断错误
快照，非演进业务载荷。**（已确认 by 总协调 2026-09-10：诊断 JSON 列为
INTERNAL ONLY——绝不原样返回，必须经有界安全投影/尺寸约束后外传；业务版本
列（schema_version）仍保留服务端/ schema 层整数校验，不受本例外影响。）**
落地：`GET /api/v1/system/echo-jobs/{jobId}` 的 `data.lastError` 现强制
有界投影（仅 reason 枚举 + retryable bool），raw code / message / stack /
retry_after_seconds 永不投影；未知/畸形 code 归一 `reason=internal`
（有界投影，非截断）。**（oracle round-4 修正 / round-5 收紧）**`lastError`
及同路径 `finishedAt`、`leaseRevision` 改为严格 OAS 3.0.3 内联表示（`type`
与 `nullable` 同一 Schema Object；`allOf:[$ref]`+nullable 无本地 `type` 时
nullable 不生效，严格消费者会拒绝合法 `null`）。新增
`scripts/validate_responses.py`：这是 **BOUNDED 严格-nullable 响应校验**——
解析 openapi.yaml 实际 echo-jobs view schema（document-resolved），含
old/new nullable 形状判别回归，强制 key 集 / enum / required /
additionalProperties；正例含真实 `lastError:null`，反例额外字段 / 非法 enum
被拒；已纳入 `validate_samples.py`。**边界（诚实声明）**：它**不是**完整 OAS
校验；`format`（uuid/date-time）注解不强制；当前仅覆盖 echo-view 路径。
`nullable` 为 true 但无本地 `type` 的旧式写法一律按严格语义处理（不并 null）。

**遗留跟随项（off-path，本次未改，待下次授权的契约修订）**：全文档仍有
**36 处** `allOf/oneOf/anyOf + nullable` 且无本地 `type` 的旧式 schema
（审计见 round-6 报告；严格校验当前只覆盖 echo-view 路径，这些路径在严格
消费者下同样可能错误拒绝合法 `null`）：
`SystemEchoJobRequest.jobId`、`Verification.validUntil`、
`Progress.targetCount`、`Progress.completedAt`、
`ProgressWithSync.allOf[1].lastSyncedAt`、`GimbalHeartbeatRequest.taskId`、
`GimbalHeartbeatRequest.executionId`、`GimbalStatusView.lastSeenAt`、
`MicrocrystalCapabilitiesView.observedAt`、`MicrocrystalCapabilitiesView.receivedAt`、
`AssessmentTaskAccepted.currentAssessmentRevision`、`AssessmentTaskView.reportId`、
`SkinReportView.memberId`、`SkinReportView.reportReadyAt`、
`GimbalCurrentAssessmentView.currentAssessment.reportId`、`CarePlanListItem.progress`、
`CarePlanFullView.progress`、`M4A03Metadata.planId`、`M4A03Metadata.currentTaskId`、
`M4A03Metadata.currentAssessmentRevision`、`ControllerRef.gimbalId`、
`CareExecutionAdmission.memberId`、`CareExecutionAdmission.planId`、
`CareExecutionRevalidation.planId`、`ExecutionObservation.verificationRevision`、
`ExecutionObservationSyncRequest.observation`、`ExecutionObservationAck.progress`、
`ExecutionClosureResult.closedAt`、`CareExecutionView.controller`、
`CareExecutionView.memberId`、`CareExecutionView.planId`、
`CareExecutionView.microcrystalId`、`CareExecutionView.latestObservation`、
`CareExecutionView.closedAt`、`CareExecutionView.progress`、
`CareExecutionListItem.closedAt`。

**媒体授权语义（oracle round-2 R2-1）**：A 包生产安全默认 =
**deny-all**（`DenyAllMediaAccessPolicy`，`app.media.access-mode=deny-all`）：
任何媒体 GET 一律统一 404 `RESOURCE_NOT_VISIBLE`，直到 B/C/D 安装业务
`@Primary MediaAccessPolicy`。上传者本人可读是**显式 dev/test 便利**
（`app.media.access-mode=owner-dev`，仅 dev/test 生效）；`grant_face` /
`execution_face` / `revalidation_face` 等核验用途**即使对上传者也不经此便利
放行**（保留给 B/C/D 业务策略）。`app.env=production` 下任何非默认
access-mode 或 `app.media.allow-any-authenticated=true` →
`ProductionFailClosedValidator` 无条件拒绝启动（与 bean 装配无关）。dev
联调如需任意已认证可读，用 `access-mode=any-authenticated` 或
`allow-any-authenticated=true`（production 一律拒绝）。业务授权读
（DD 10.2 第 2–3 条：T05 冻结报告引用 / T02 有效关系 / T03 当前任务）由
B/C/D 以 `@Primary MediaAccessPolicy` 覆盖。

**每请求认证复核成本（oracle B2）**：BearerAuthFilter 在
SessionProvider.authenticate 后经 `PrincipalRevalidator` 复核本地状态，
每请求 **恰好一条单行查询**（无 JOIN、无锁）：APP
`SELECT status, auth_revision FROM accounts WHERE id=?`；GIMBAL
`SELECT credential_version FROM gimbals WHERE id=?`。会话快照携带签发时刻
auth_revision / credential_version；disabled、revision 递增、版本轮换或行
缺失 → 401 SESSION_INVALID。
