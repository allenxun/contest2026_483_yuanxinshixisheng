# B·API 联调指南（APP / 云台 对接 Swagger 文档使用说明）

> **适用对象**：9 月 13 日硬件 APP / 云台联调的客户端开发者与总协调。
> **配套页面**：运行中的后端在 **dev/test** profile 下提供 Swagger UI `http://<host>:<port>/swagger-ui/index.html` 与机器可读文档 `GET /v3/api-docs`（OpenAPI **3.1.0**，由**实际 Controller/DTO 生成**，非手写 YAML 回显）。
> **权威声明（务必先读）**：本指南与生成页面都是**联调辅助**，**不是权威契约**。字段级与错误码级契约的权威来源是 `backend/contracts/openapi/openapi.yaml`（OpenAPI **3.0.3**）；两者不一致时**以契约文件为准**，并请把差异上报总协调。
> **绑定 SHA**：`c3bf05433276152441eb7e80081c3dffc5fbeb6a`（本轮 Swagger 联调注释的**最终交付 SHA**，经实际 Oracle 第四轮窄范围复审判 **PASS-with-notes** 并明确许可合入 dev；提交链 `fb342a6`（首版，Oracle 判 FAIL）→ `9b5ed34`（第二批整改，判 FAIL）→ `7461ce1`（第三批整改，判 FAIL）→ `c3bf054`（第四批整改，PASS-with-notes）；dev 基线为总协调指定的 `76cd426e912096971b6e1c387995d875cf2cce70`）。Oracle 逐轮记录见 `B-oracle.md` §4.16。
> **本文档与生成页面的适用范围（Oracle 裁定口径）**：可支撑 APP/云台开发者**独立完成 HTTP 流程与 doubles 联调**，也可供**主流代码生成器**产出客户端模型与调用骨架；但**不可**作为严格 JSON Schema 验证器的输入，也**不可替代**权威手写契约（原因见第 8 节）。

---

## 1. 总览与通用契约

| 项 | 口径 |
|---|---|
| 端点规模 | **33 个路径 / 34 个操作**（27 个业务 API `x-api-id` = M1-A01…M5-A01 + 7 个基础协议端点 `x-foundation` = f01–f07）。本轮**未新增任何业务接口** |
| 字段命名 | HTTP JSON 一律 **camelCase**；数据库与任务 payload 为 snake_case（**不对外**） |
| 大整数 | bigint（N/K、各 revision、epoch/seq、计数、photoVersion）一律 **十进制字符串** `^(0\|[1-9][0-9]*)$`；**不得**用 JSON number（避免精度丢失） |
| `schema_version` | 用 **JSON 整数**（当前固定 `1`），与 bigint 字符串口径不同，勿混用 |
| 时间 | **RFC 3339 UTC、秒精度**（服务端 `Instant.truncatedTo(SECONDS)`），无时区偏移；入站非法格式 → 400 `INVALID_INPUT` |
| 资源 ID | 服务端资源 ID 为 **UUID** |
| 请求追踪 | **每个响应**（含错误与 204）携带 `X-Request-Id`，与响应体 `requestId` 同值；报障请附该值 |
| 成功信封 | `{ "requestId": "...", "data": {...}, "meta": { "replayed": false, "serverTime": "2026-09-13T08:30:00Z" } }` |
| 错误信封 | `{ "requestId": "...", "error": { "code": "...", "message": "...", "retryable": false, "details": {...} } }`；`details` 仅在需要时出现，且**只含调用方可见信息** |
| 无体响应 | **204 无任何响应体**（撤销成员访问授权、解绑云台、退出登录） |
| 列表 | `data = { "items": [...], "nextCursor": "..." }`；`nextCursor` 为 **null 表示无后续页**（字段保留、不省略） |
| 字段必填性 `required` | 生成文档的 `required` 已**逐 schema 与契约交叉校验并修正**（覆盖率门禁强制：少于或多于契约都会构建失败）。<br>**响应侧**：`required` 表示"**该键必然存在**"——响应 DTO 是 record，组件恒被序列化，值为 `null` 时键仍在。**未列入** `required` 的字段表示可能为 `null`、或在某些视图下**整键省略**（如 `SkinReportView` 的 `metrics`/`description` 在 `view=brief` 时省略、`CareExecutionListItem.closedAt` 未收尾时为 null、`VerificationDto.validUntil` 当前恒为 null），客户端**不得依赖**。⚠️ **`required` ≠ 必然有值**：例如 `GimbalCurrentAssessmentView.currentAssessment` 是 required（键必存在），但无当前任务时其值**严格为 `null`**。<br>**请求侧**：`required` 表示契约要求必填，服务端确实强制（缺失或非法 → 400 `INVALID_INPUT` + `details.fields`）；唯一例外是 `EchoJobRequestBody.numbersAsStrings`——契约必填而当前实现未强制，属**实现偏差**，已在其字段描述中注明。 |
| 分页 | `limit` 默认 **20**、上限 **100**；`cursor` 为 **URL-safe Base64** 的不透明 keyset 游标，**原样回传**、不得自行构造；非法游标 → 400 `INVALID_INPUT` 且 `details.reason="invalid_cursor"`；游标**绑定账号**，跨账号使用会被拒绝 |
| 上传 | `multipart/form-data`；单图上限 **10 MiB**、三图合计 **32 MiB**；超限 → 413 `UPLOAD_TOO_LARGE`；实际格式校验（不仅看 MIME）不符 → 415 `UNSUPPORTED_IMAGE` |
| 媒体读取 | `Cache-Control: no-store`、`X-Content-Type-Options: nosniff`；走**同源鉴权代理**，**每次读取都复核权限**；**不下发长效签名 URL、不重定向**到算法临时地址；不可见与不存在返回**完全相同**的响应 |
| 文档可用性 | 文档端点**仅 dev/test 启用**；生产（`prod` profile 或 `app.env=production`）**强制启用会被拒绝启动**（fail-closed，端口都不绑定）。Swagger UI **不得**暴露公网生产 |

---

## 2. 鉴权与幂等

### 2.1 鉴权
- 头部：`Authorization: Bearer <token>`；全局默认 `bearerAuth`。
- **两种 token**：
  - **APP session token** —— 由 `POST /api/v1/auth/sessions`（手机号验证码）签发，`POST /api/v1/auth/session-refreshes` 刷新（refreshToken 轮换），`DELETE /api/v1/auth/sessions/current` 退出。
  - **gimbal device session token** —— 由 `POST /api/v1/gimbal-sessions`（云台认证/重连后重新认证）签发。
- **4 个公开端点（无 Bearer）**：`POST /api/v1/auth/sms-challenges`、`POST /api/v1/auth/sessions`、`POST /api/v1/auth/session-refreshes`、`POST /api/v1/gimbal-sessions`。其余全部需要 token。
- **主体身份只由 token 决定**：**请求体不得声明 `accountId`/`gimbalId`/`installationId` 等身份字段**（声明也会被忽略或拒绝）；观察者/调用者身份一律取自服务端主体。
- **会话代次与失效**：账号停用使 `auth_revision` 递增；云台凭据轮换使 `credential_version` 递增，**旧 token 立即 401**。服务端对**每个请求**复核主体有效性。
- **主体类型决定可调用端点**：仅 APP / 仅云台 / 两者皆可，逐端点见生成文档的 description。类型不符 → 403 `CALLER_NOT_ALLOWED`（**重试无意义**）。
- **退出登录的连带效果**：先撤销会话；随后把该会话对应的**通知目标置为 `invalid` 并在单条 SQL 内原子递增 `destination_revision`**，使旧路由快照失效（旧通知任务不会继续投递）。⚠️ **这两步不在同一个数据库事务中**：会话撤销由 `SessionProvider` 完成（当前为内存替身，14 表无 session 表），通知目标失效是其后的独立单条 UPDATE，且**失败不会回滚登出**——按 DD 4.1 的幂等补偿语义处理（撤销已生效，目标失效可后续补偿）。
- ⚠️ **待定项**：真实短信/会话提供方**尚未选定**，dev/test 使用替身 ⇒ **token 有效期、刷新窗口等具体数值无权威值**，本文不编造；联调时以服务端返回的 `expiresAt`/`serverTime` 为准。

### 2.2 幂等（`Idempotency-Key`）
- **哪些端点需要**：写操作普遍需要（成员访问授权创建/撤销、云台绑定/解绑、微晶观察、测肤任务提交/补拍、护理执行登记/重新核验/观察同步/收尾确认、通知目标登记）。逐端点的必填性见生成文档参数说明。
- **键的作用域**：服务端按 **`(principal_type, principal_id, operation, idempotency_key)`** 唯一。即**同一主体的同一操作**才共享键空间；换一个逻辑请求**必须换新键**。
- **三种结果**：
  1. **同键 + 同内容** → **重放**：返回原结果，`meta.replayed = true`（HTTP 码与原成功响应一致，例如创建授权重放为 200 而非 201）。重放**按当前权限与生命周期重新投影**，不会机械回放过期的敏感成功响应。
  2. **同键 + 不同内容** → **409 `IDEMPOTENCY_CONTENT_CONFLICT`**（内容摘要按 **RFC 8785 JCS + SHA-256** 计算；multipart 的图片 part 按 part 名与逐 part 摘要参与计算）。
  3. **同键正在处理中** → **409 `REQUEST_IN_PROGRESS`** + `Retry-After` 头 + `details.retryAfterSeconds`；请**按该等待时间后用同一键重试**（`retryable=true`）。
- **无 TTL 语义**：幂等记录**不会**按短 TTL 清理——否则"撤销授权后的旧请求重放"等规则会被破坏。因此**不要指望换个时间就能复用旧键做新请求**。
- **不需要该头的端点**：认证握手类（f01–f04、M2-A01）；**云台心跳**（M2-A02）用 `observationEpoch`/`observationSeq` 去重而非幂等键；`POST /api/v1/system/echo-jobs` 为可选。

---

## 3. 业务错误码总表（HTTP 码 / retryable / 语义 / 客户端动作）

下表由 `ErrorCode`（权威 HTTP 映射与 retryable）与 `ErrorCodeDocs`（中文语义与客户端动作，源自 DD 3.2「错误码与重试动作」）**自动生成**，与生成文档中各端点的 `x-error-codes` 一致：

**HTTP 400**

| 业务码 | retryable | 语义 / 触发条件 / 客户端动作 |
|---|---|---|
| `INVALID_INPUT` | false | 请求字段缺失、格式非法、枚举越界或未知字段。触发：Bean Validation 或业务前置校验失败。客户端动作：修正请求后重试；不得原样重放。 |

**HTTP 401**

| 业务码 | retryable | 语义 / 触发条件 / 客户端动作 |
|---|---|---|
| `AUTH_REQUIRED` | false | 缺少或格式错误的 Authorization 头。触发：无 Bearer token 或非 Bearer 方案。 |
| `SESSION_INVALID` | false | 会话 token 无效、已过期或已被撤销（含账号停用/全端登出/云台凭据版本轮换）。触发：每请求与本地状态复核失败。客户端动作：重新登录/重新握手获取新 token 后重试； |

**HTTP 403**

| 业务码 | retryable | 语义 / 触发条件 / 客户端动作 |
|---|---|---|
| `CALLER_NOT_ALLOWED` | false | 当前主体类型不允许调用该端点（如云台调用 APP 专属端点、APP 调用云台专属端点）。 |
| `FACE_NOT_VERIFIED` | false | 人脸未能可靠确认本人（未匹配到成员、匹配不确定、或成员不存在）。触发：核验结果非可靠匹配。客户端动作：按提示重新采集本人清晰照片； |
| `GRANT_REVOKED` | false | 旧请求指向已撤销的成员访问授权，不能据此创建新的关系或继续写入。触发：T13/业务行关联的关系已 revoked。客户端动作：需要重新授权时发起新的人脸核验请求（新逻辑键）， |

**HTTP 404**

| 业务码 | retryable | 语义 / 触发条件 / 客户端动作 |
|---|---|---|
| `RESOURCE_NOT_VISIBLE` | false | 资源对当前主体不可见（不存在、不属于本人、或已被替换）。触发：按 ID/归属查询不到对当前 principal 可见的行。 |

**HTTP 409**

| 业务码 | retryable | 语义 / 触发条件 / 客户端动作 |
|---|---|---|
| `BINDING_CHANGED` | false | 乐观并发代次不符（绑定 revision / 通知目标 destination_revision）。触发：请求携带的 expected* 代次与当前值不一致。客户端动作：刷新当前状态（GET）后用最新代次重试。 |
| `BOUND_TO_OTHER` | false | 该云台已绑定到其他账号，不能覆盖。触发：绑定目标云台已有他人绑定关系。 |
| `CLOSURE_GAPS` | false | 收尾确认时测量流水存在缺口（缺少连续区间），不能完成关闭。触发：final seq/count 与已接收记录不连续。客户端动作：补齐缺失区间后重新提交收尾确认。 |
| `DEVICE_OCCUPIED` | false | 云台正在执行未收尾的护理流程，不能开始新的测肤任务。 |
| `EXECUTION_NOT_RESUMABLE` | false | 该护理执行当前状态不可继续/恢复。触发：执行已终态或状态机不允许 resumption。 |
| `IDEMPOTENCY_CONTENT_CONFLICT` | false | 同一 Idempotency-Key 携带了不同内容（payload_hash 不一致），与首次请求冲突。触发：T13 记录 (principal_type, principal_id, operation, idempotency_key) 已存在且载荷哈希不同。客户端动作：这是一个新的逻辑请求，必须使用新的 Idempotency-Key；同键同内容重放会命中原结果 |
| `PHOTO_VERSION_CONFLICT` | false | 照片版本冲突：补拍版本必须为当前版本 + 1，且任务须处于 needs_retake。触发：版本不连续、expected 不符、或任务状态不允许补拍。客户端动作：刷新任务当前版本/状态后， |
| `PLAN_COMPLETED` | false | 护理方案已完成/关闭，不能对其创建新执行。 |
| `PLAN_NOT_READY` | false | 护理方案尚未就绪（生成中或生成失败），不能开始执行。触发：care_plans.generation_status 非 ready。客户端动作：轮询方案状态，就绪后再创建执行； |
| `RECORD_CONFLICT` | false | 同一执行内出现与既有记录冲突的测量记录（如相同 (epoch,seq) 内容不一致）。触发：计数流水去重键冲突且内容不同。客户端动作：以服务端已有记录为准，修正本地状态。 |
| `REQUEST_IN_PROGRESS` | **true** | 同一逻辑请求正在处理中（T13 租约未释放），尚未有终态结果。触发：同 (principal, operation, idempotency_key) 另一处理在进行。客户端动作：按响应 Retry-After 等待后， |
| `STOP_NOT_CONFIRMED` | false | 云台执行已停止但未被关闭确认，占用尚未释放。 |
| `TASK_REPLACED` | false | 该云台的当前测肤任务已被新任务替换，旧任务不再是当前任务。触发：操作针对的任务 ≠ 云台当前任务。客户端动作：不返回旧报告/旧方案、不恢复旧指针； |

**HTTP 413**

| 业务码 | retryable | 语义 / 触发条件 / 客户端动作 |
|---|---|---|
| `UPLOAD_TOO_LARGE` | false | 上传图片超过单图上限（开发初值 10MiB，以配置为准）。触发：multipart 图片字节数超限。 |

**HTTP 415**

| 业务码 | retryable | 语义 / 触发条件 / 客户端动作 |
|---|---|---|
| `UNSUPPORTED_IMAGE` | false | 图片格式不在白名单（JPEG/PNG/GIF/WebP，按内容嗅探，不信任客户端 MIME）。 |

**HTTP 422**

| 业务码 | retryable | 语义 / 触发条件 / 客户端动作 |
|---|---|---|
| `FACE_QUALITY_REJECTED` | false | 人脸照片质量不合格（模糊/遮挡/光照不足等）。触发：人脸质检未通过。 |
| `UNSUPPORTED_CONTRACT` | false |  |

**HTTP 429**

| 业务码 | retryable | 语义 / 触发条件 / 客户端动作 |
|---|---|---|
| `RATE_LIMITED` | **true** | 触发限流。触发：单位时间请求过多。客户端动作：按 Retry-After 退避后重试；retryable=true， |

**HTTP 500**

| 业务码 | retryable | 语义 / 触发条件 / 客户端动作 |
|---|---|---|
| `INTERNAL` | false | 未映射的服务端异常（不承诺重试安全）。触发：内部缺陷或未预期错误。客户端动作：记录响应头 X-Request-Id 反馈运维，不要自动无限重试。 |

**HTTP 501**

| 业务码 | retryable | 语义 / 触发条件 / 客户端动作 |
|---|---|---|
| `NOT_IMPLEMENTED` | false | 该能力在当前版本未实现（占位/未启用）。触发：调用未启用端点或未激活提供方。客户端动作：不要重试，按产品/联调约定确认能力可用性。 |

**HTTP 503**

| 业务码 | retryable | 语义 / 触发条件 / 客户端动作 |
|---|---|---|
| `DEPENDENCY_UNAVAILABLE` | **true** | 依赖不可用（存储写入/人脸或分析提供方等）；任务/写入未成功，绝不伪报成功。触发：下游调用或存储失败。客户端动作：受限退避重试；retryable=true。 |

**HTTP 504**

| 业务码 | retryable | 语义 / 触发条件 / 客户端动作 |
|---|---|---|
| `DEPENDENCY_TIMEOUT` | **true** | 依赖调用超时；结果未知，未伪报成功。触发：下游超时。客户端动作：受限退避重试；retryable=true。 |

### 3.1 `details` 的合法形态（按码）
| 码 | `details` 键 | 说明 |
|---|---|---|
| `INVALID_INPUT`（参数校验失败） | `fields: [{field, reason}]` | 逐字段违规原因 |
| `INVALID_INPUT`（请求体不可读/缺参/类型错） | `reason` | 概述，不含原始报文 |
| `INVALID_INPUT`（游标非法） | `reason: "invalid_cursor"` | 游标必须原样回传 |
| `REQUEST_IN_PROGRESS` | `retryAfterSeconds`（并带 `Retry-After` 头） | 按该秒数等待后用**同一键**重试 |
| `BINDING_CHANGED`（绑定/解绑） | `currentBindingRevision` | 只含当前代次，不泄漏其他账号信息 |
| `BINDING_CHANGED`（通知目标） | `currentDestinationRevision` | 同上 |
| `PLAN_NOT_READY` | `reason` | 能力覆盖不足/方案未就绪 |
| `EXECUTION_NOT_RESUMABLE` | `reason` ∈ `admitted_not_paused` / `unknown_needs_fresh_paused_observation` / `stopped_not_resumable` / `closed_not_resumable` / `running_not_paused` / `plan_completed` / `verification_revision_mismatch` | 按 reason 决定下一步 |
| `RECORD_CONFLICT` | `conflictingRecordIds`（≤20）+ `totalConflicts`，或 `reason` ∈ `observation_epoch_mismatch` / `observation_seq_conflict` | 保留待同步记录，修正后以**新键**重传 |
| `STOP_NOT_CONFIRMED` | `reason` | 收尾前必须先上报 stopped 观察 |
| `CLOSURE_GAPS` | `reason` + `missingRanges` + `more` + `finalCount` + `totalCount` | `missingRanges` 是**对象数组**，每个元素为 `{from, to}`（含端点，均为无符号 bigint 十进制字符串），依契约 `MissingRange` 封闭（无其它键）；受输出上限约束，须配合 `more` 判断是否被截断。按缺失区间补传后再收尾 |
| `NOT_IMPLEMENTED` | `apiId` | **契约保留码**（501，表示该能力在当前版本未实现）。当前占位 Controller 已**无任何业务路由映射**（`NotYetImplementedController` 不再声明请求映射），故**已实现的业务端点不应期待该码发生**；若收到它，说明请求打到了未启用的能力上。客户端须容忍 `details` 未来新增字段 |

> **内部诊断绝不外发**：`failure_detail`、`last_error` 等内部诊断列的**原始内容不会出现在任何响应**中。测肤任务的失败只投影**公开白名单内的 `failureCode`** + `retryable`（+ 需补拍时的 `requiredViews`）；异步任务的 `lastError` 只投影封闭的 `reason` 枚举与 `retryable`。

### 3.2 契约一致性修正与过声明处置（本轮经总协调授权改契约；逐项以实现为据）
1. **`PROVIDER_CONTRACT_VIOLATION` 已纳入契约（原缺口已闭合）**：该码**已实现**且会经 `GET /api/v1/skin-assessment-tasks/{taskId}` 的 `failureCode` 对外返回（算法结果违反已核准指标白名单/基线的**确定性终态**失败，1 轮到达终态、无后继任务）。本轮已把 `FailureProjection.PUBLIC_FAILURE_CODES` 的 **9 个公开白名单码作为封闭 `enum`** 写入契约 `components.schemas.AssessmentTaskView.properties.failureCode`，并注明"当前所有非 null 取值的 `retryable` 均为 **false**，`true` 仅为未来瞬时可重试失败预留"（**语义未变**）。客户端现在可以**穷举**这 9 个取值；新增取值需先改契约。注意它是**任务投影字段**（`failureCode`），不是 HTTP 错误码，故不出现在任何操作的 `x-error-codes` 中。
2. **`SESSION_INVALID` 已补入 f02 声明（原遗漏已闭合）**：`POST /api/v1/auth/sessions` 在账号非 active（停用）时确实抛 **401 `SESSION_INVALID`**（`AuthController:181`，裁定依据 oracle B2），本轮已补入契约该操作的 `x-error-codes` 与生成文档（其余 32 个操作本就声明该码）。401 响应体沿用共享的 `Unauthorized` 信封（`401 AUTH_REQUIRED / SESSION_INVALID`），故 `responses` 无需改动。
3. **契约过声明的处置（逐项依据实现）**：本轮已把**经实现取证确认不可达**的错误码从对应操作的**有效声明**（契约 `x-error-codes` 与生成文档 `x-error-codes`）中移除，共 **24 处码-操作对 / 17 个操作**；每处都在对应端点的 description 中保留了精简的**历史背景 + 取证依据**（`文件:行`）。**HTTP 行为与序列化语义均未改变**（这些码本来就不会由这些操作返回）。

**过声明移除清单（24 处，逐项附实现依据）**

| 操作 | 端点 | 移除的码 | 不可达依据 |
|---|---|---|---|
| M2-A01 | `POST /api/v1/gimbal-sessions` | `SESSION_INVALID`、`IDEMPOTENCY_CONTENT_CONFLICT` | 公开端点不经 `BearerAuthFilter`（前者无入口）；本端点无 `Idempotency-Key`，而后者全仓唯一抛出点为 `idempotency/IdempotencyService.java:104` |
| M2-A02 | `POST /api/v1/gimbals/{gimbalId}/heartbeats` | `TASK_REPLACED` | 心跳**不移动** `current_assessment` 指针（`GimbalHeartbeatService.java:44-45` javadoc 明示"本实现不使用 TASK_REPLACED"） |
| M2-A03 | `GET /api/v1/gimbals/{gimbalId}/status` | `CALLER_NOT_ALLOWED` | `GimbalStatusService` 对 GIMBAL/APP 双主体分支放行或统一 404，全类该码命中 **0** |
| M3-A01 | `POST /api/v1/skin-assessment-tasks` | `TASK_REPLACED` | `AssessmentAcceptanceService.acceptA01New:117-174` 以"受理即替换指针"完成（`:159`），该码只在 A02 路径 `:238` 抛出 |
| M3-A03 | `GET /api/v1/skin-assessment-tasks/{taskId}` | `CALLER_NOT_ALLOWED` | `AssessmentReadService.getTask:36-58` 对双主体分支处理（云台非本人→404、非当前任务→`TASK_REPLACED`）；`:81` 的该码属 **`currentAssessment`（`:78`，服务 M3-A06）** |
| M3-A04 | `GET /api/v1/members/{memberId}/skin-reports` | `GRANT_REVOKED` | 该码全仓唯一抛出点 `identity/MemberAccessGrantService.java:151`（M1-A01 幂等重放指向已撤销授权）；本端点对无 active 授权统一 404 `RESOURCE_NOT_VISIBLE`（防存在性推断） |
| M3-A05 | `GET /api/v1/skin-reports/{reportId}` | `GRANT_REVOKED` | 同上 |
| M4-A01 | `GET /api/v1/members/{memberId}/care-plans` | `GRANT_REVOKED` | 同上 |
| M4-A02 | `GET /api/v1/care-plans/{planId}` | `PLAN_NOT_READY`、`GRANT_REVOKED` | 未就绪方案返回 **200 + `waitingReason`**（waiting_inputs/generating/generation_failed），**不抛错**（`CareQueryService.getCarePlan:116-130`）；`GRANT_REVOKED` 同上 |
| M4-A03 | `POST /api/v1/care-executions` | `CALLER_NOT_ALLOWED`、`BINDING_CHANGED` | 本操作**同时接纳 APP 与云台**主体（`controllerType` 可为 `gimbal`）；`CareAuthorization.requireApp`（唯一抛该 403 处，`care/CareAuthorization.java:44`）在 care 包**仅被 `CareQueryService:69,107,227` 调用**。`BINDING_CHANGED` 只在 `GimbalBindingService:357` 与 `NotificationDestinationService:324,327`，护理路径无绑定代次入参 |
| M4-A04 | `POST /care-executions/{executionId}/revalidations` | `CALLER_NOT_ALLOWED`、`RECORD_CONFLICT` | 以 `isOriginalController` 判定（错误主体→404 `RESOURCE_NOT_VISIBLE`），无 `requireApp`；重新核验路径**不写台账记录**，`RECORD_CONFLICT` 只在 `CareLedgerService:349,368`（A05）与 `:527,807`（A06） |
| M4-A05 | `POST /care-executions/{executionId}/observations` | `CALLER_NOT_ALLOWED`、`BINDING_CHANGED` | 同 M4-A03/A04 的主体与绑定依据 |
| M4-A06 | `POST /care-executions/{executionId}/closure-confirmations` | `CALLER_NOT_ALLOWED` | 同上（`CareLedgerService.close/runClosure:490-506` 仅 `isOriginalController`） |
| M4-A07 | `GET /api/v1/care-executions/{executionId}` | `CALLER_NOT_ALLOWED`、`GRANT_REVOKED` | `CareQueryService.getCareExecution:135-164` 以 `hasActiveGrant`/`isOriginalController` 双判定（APP 与云台都接受）；`GRANT_REVOKED` 同上 |
| M4-A08 | `GET /api/v1/care-plans/{planId}/progress` | `CALLER_NOT_ALLOWED`、`GRANT_REVOKED` | `getPlanProgress:168-219` 显式分支允许云台（需 executionId+verificationRevision）；`GRANT_REVOKED` 同上 |
| M4-A09 | `GET /api/v1/members/{memberId}/care-executions` | `GRANT_REVOKED` | 同上 |
| f05 | `GET /api/v1/media/{mediaId}/content` | `CALLER_NOT_ALLOWED` | `MediaController.content:42-52` 授权失败一律 **404 `RESOURCE_NOT_VISIBLE`**（防存在性推断）；三个 `MediaAccessPolicy` 实现中该码命中 **0** |

**必须保留的可达码（逐项取证；其中 16 对已由门禁 `reachableCodesMustStay` 正向对照断言锁定，防止“全删”）**：M1-A01 的 `GRANT_REVOKED`（唯一可达点 `MemberAccessGrantService:151`）；M3-A03/M3-A05/M4-A03/M4-A04/M4-A08 的 `TASK_REPLACED`（`AssessmentReadService:48`、`SkinReportService:129`、`CareAdmissionService.taskReplaced()` 经 `:203,:207,:266,:270`（admit）与 **`:427,:430`（`runRevalidation`）、`:470,:473`（`runRevalidationTx`）**、`CareQueryService:205`）；M4-A03/M4-A08 的 `PLAN_NOT_READY`（`CareAdmissionService:774,775`、`CareQueryService:198`（云台分支）/`:216`（APP 分支））；M4-A05/M4-A06 的 `RECORD_CONFLICT`（`CareLedgerService:349,368,527,807`）；f05 与全部已认证操作的 `SESSION_INVALID`（`BearerAuthFilter:89,104` 统一抛出）；M4-A01/A02/A09 与 M2-A02/M3-A01/A02/A04/A05/A06 的 `CALLER_NOT_ALLOWED`（`CareAuthorization.requireApp` 的 3 处调用 + 各域 `requireApp`/`requireGimbal`）。
> **断言覆盖范围如实说明**：门禁锁定的是上述 **16 对**（含本轮补入的 M3-A03 `TASK_REPLACED`、M4-A05/M4-A06 `RECORD_CONFLICT`）；其余可达码为**取证结论**，未逐对写入断言。
> 注：M4-A04 的 `TASK_REPLACED` 起初未在侦察结论覆盖范围内，orchestrator 自行追踪 `taskReplaced()` 的全部调用点后确证其**可达**（经 `runRevalidation`/`runRevalidationTx`），故**保留**——这是"保守默认保留 + 逐点取证"的结果，不是遗漏。
> 生成文档的 `x-error-codes` 声明总数由 **358 降至 334（恰 −24）**，唯一码数 28（`ErrorCode` 共 29 个，其中 `NOT_IMPLEMENTED` 等按操作声明）。

---

## 4. 接口分组与真实状态码（逐字段说明请看 Swagger UI）

生成文档按业务域打了中文 tag。**最易踩坑的是状态码**：基线生成文档曾把 34 个操作全部标为 200，本轮已按真实行为修正。

| 域（tag） | 端点 | 真实成功码要点 |
|---|---|---|
| 基础认证 | `POST /api/v1/auth/sms-challenges`、`POST /api/v1/auth/sessions`、`POST /api/v1/auth/session-refreshes` | 200 |
| 基础认证 | `DELETE /api/v1/auth/sessions/current` | **204 无体** |
| 云台会话 | `POST /api/v1/gimbal-sessions` | 200（**设备上电第一件事**） |
| 基础媒体 | `GET /api/v1/media/{mediaId}/content` | 200 **二进制**（Content-Type 为媒体自身类型，非固定 image/jpeg） |
| 基础系统 | `POST /api/v1/system/echo-jobs`、`GET /api/v1/system/echo-jobs/{jobId}` | 200（联调自检用；创建者归属，他人/缺失统一 404） |
| 成员访问授权 | `POST /api/v1/member-access-grants` | **201 新建 / 200 重放**；multipart `{metadata, face}` |
| 成员访问授权 | `GET /api/v1/me/member-access-grants` | 200（列表，只返回未撤销） |
| 成员访问授权 | `DELETE /api/v1/me/member-access-grants/{grantId}` | **204 无体** |
| 设备与绑定 | `POST /api/v1/gimbals/{gimbalId}/heartbeats` | 200（**仅云台**；`accepted=false` 表示重复/迟到，**不是错误**） |
| 设备与绑定 | `GET /api/v1/gimbals/{gimbalId}/status`、`GET /api/v1/gimbals/{gimbalId}/binding-status` | 200 |
| 设备与绑定 | `PUT /api/v1/me/gimbal-bindings/{gimbalId}` | 200 |
| 设备与绑定 | `DELETE /api/v1/me/gimbal-bindings/{gimbalId}` | **204 无体**（`If-Match: "binding-{revision}"`） |
| 设备与绑定 | `POST /api/v1/microcrystal-observations`、`GET /api/v1/microcrystals/{microcrystalId}/capabilities` | 200 |
| 通知目标 | `PUT /api/v1/me/notification-destinations/{installationId}` | 200（**只登记目标、不发送任何消息**；**绝不回传完整推送 token**） |
| 测肤任务 | `POST /api/v1/skin-assessment-tasks`、`PUT /api/v1/skin-assessment-tasks/{taskId}/photo-versions/{photoVersion}` | **202 已受理（分析异步）/ 200 重放**；multipart（前者 `metadata`+`front`/`left`/`right`，后者 `metadata`+被替换视角） |
| 测肤任务 | `GET /api/v1/skin-assessment-tasks/{taskId}`、`GET /api/v1/gimbals/{gimbalId}/current-assessment` | 200 |
| 测肤报告 | `GET /api/v1/members/{memberId}/skin-reports`、`GET /api/v1/skin-reports/{reportId}` | 200（后者 `view=full\|brief`） |
| 护理方案 | `GET /api/v1/members/{memberId}/care-plans`、`GET /api/v1/care-plans/{planId}`、`GET /api/v1/care-plans/{planId}/progress` | 200 |
| 护理执行 | `POST /api/v1/care-executions` | **200/201**（语义为"**已登记，待端侧确认**"）；multipart `{metadata, face}` |
| 护理执行 | `POST /api/v1/care-executions/{executionId}/revalidations` | 200；multipart `{metadata, face}` |
| 护理执行 | `GET /api/v1/care-executions/{executionId}`、`GET /api/v1/members/{memberId}/care-executions` | 200 |
| 护理执行 | `POST /api/v1/care-executions/{executionId}/observations`、`POST /api/v1/care-executions/{executionId}/closure-confirmations` | 200 |

### 4.1 9/13 联调最高优先的 5 个端点
1. **`POST /api/v1/gimbal-sessions`** —— 云台上电/重连后第一件事；拿不到 token 后续全断。
2. **`POST /api/v1/gimbals/{gimbalId}/heartbeats`** —— `observationEpoch`（非空 1–128 字符串）与 `observationSeq`（无符号 bigint 十进制串）；**同一来源会话内 epoch 不得更换、seq 必须严格递增**；重复/迟到上报返回 `accepted=false` 且**不刷新在线状态**（不是错误）。⚠️ **客户端必须跨登录/refresh/重启持久化 epoch 与单调 seq**（已确认的协议约束 C25），否则重启后 seq 归 1 会被判为迟到而长期不被接受。
3. **`POST /api/v1/skin-assessment-tasks`** —— 三视角 multipart；**202 表示已受理、分析异步**；受理即**原子替换**该云台的当前任务（旧任务不可恢复）；若该云台有未收尾的护理执行 → 409 `DEVICE_OCCUPIED`/`STOP_NOT_CONFIRMED`。
4. **`GET /api/v1/skin-assessment-tasks/{taskId}`** —— 状态机 `queued → analyzing → (needs_retake | report_ready | failed)`；`needs_retake` 时按 `requiredViews`（`front`/`left`/`right` 子集，≤3）补拍；`failed` 时看 `failureCode` + `retryable`；**`report_ready` 才能读报告**。
5. **`POST /api/v1/care-executions`** —— 核验登记；前置=方案 `ready` + 未完成 + 能力覆盖 + 云台当前任务指针/代次匹配；返回语义是"**已登记，待端侧确认**"（状态 `admitted`），**不是**已开始护理。

---

## 5. 调用顺序与前置条件（三条主链）

### 5.1 测肤链（云台为主）
```
POST /api/v1/gimbal-sessions            （取云台 token）
  → POST /api/v1/gimbals/{id}/heartbeats （周期性；维持在线与当前任务可见性）
  → POST /api/v1/skin-assessment-tasks   （202 受理；成为该云台唯一当前任务）
  → GET  /api/v1/skin-assessment-tasks/{taskId}   （轮询状态）
       ├─ needs_retake → PUT …/photo-versions/{current+1} （202；仅当状态为 needs_retake 且版本连续）
       ├─ report_ready → GET /api/v1/skin-reports/{reportId}
       └─ failed       → 看 failureCode/retryable 决定是否重新提交（新请求用新幂等键）
```
关键约束：**云台只能看到当前指针指向的任务**（`GET /api/v1/gimbals/{id}/current-assessment`，无当前任务时 `currentAssessment` 严格为 `null`；重启可恢复；**不提供历史列表**）；指针被替换后访问旧任务 → 409 `TASK_REPLACED`（**不返回旧报告/旧方案、不恢复指针**）。

### 5.2 护理链（APP 为主）
```
POST /api/v1/auth/sessions                        （取 APP token）
  → POST /api/v1/member-access-grants             （人脸核验并取得对某成员的查看授权；201/200）
  → GET  /api/v1/me/member-access-grants          （查看未撤销授权）
  → GET  /api/v1/members/{memberId}/skin-reports  （需 active 授权，否则 404）
  → GET  /api/v1/skin-reports/{reportId}?view=full
  → GET  /api/v1/members/{memberId}/care-plans → GET /api/v1/care-plans/{planId}?view=full
  → POST /api/v1/care-executions                  （核验登记；multipart metadata+face；admitted）
  → POST /api/v1/care-executions/{id}/observations（同步观察与实际完成记录）
  → POST /api/v1/care-executions/{id}/revalidations（暂停后恢复前重新核验；需 paused + verificationRevision 匹配）
  → POST /api/v1/care-executions/{id}/closure-confirmations（收尾；需先 stop）
  → GET  /api/v1/care-plans/{planId}/progress     （N/K 与剩余次数）
```
关键约束：**无 active 成员访问授权时，报告/方案/执行相关查询一律 404 `RESOURCE_NOT_VISIBLE`**（不泄漏存在性）；**撤销授权后旧幂等键重放 → 403 `GRANT_REVOKED`**（不创建新关系、零新行；重新授权必须**新的人脸请求 + 新键**）；进度口径 **K≥N 即完成、剩余 = max(N−K, 0)、K 不截断**（下载/启动/重传**不计**完成）；记录流的 `sourceSeq` 从 1 连续递增，**观察序号与记录序号是两条独立序列**；收尾承诺范围 1..W（W=确认水位），`closed_at` 非空才释放云台占用。

### 5.3 配网·绑定·通知链（APP）
```
GET    /api/v1/gimbals/{id}/binding-status   （X-Pairing-Proof；配网时查询 unbound|self|other）
  → PUT    /api/v1/me/gimbal-bindings/{id}    （用户主动点击绑定；expectedBindingRevision + pairingProof）
  → PUT    /api/v1/me/notification-destinations/{installationId}  （登记推送目标；只登记不发送）
  → DELETE /api/v1/me/gimbal-bindings/{id}    （If-Match: "binding-{revision}"；仅原账号）
```
关键约束：**绑定只决定异常通知的接收账号，不授予任何成员资料查看权**（两者互不替代）；他人已绑 → 409 `BOUND_TO_OTHER`（**绝不覆盖**）；代次不符 → 409 `BINDING_CHANGED` + `details.currentBindingRevision`；**未绑定时无论 `If-Match` 为何值一律 404**（不可区分"未绑定"与"不存在"）；重复解绑 → 204 且**不递增代次**；换号接管通知目标会递增 `destinationRevision`，使旧账号的路由快照失效。

### 5.4 微晶（护理硬件）
```
POST /api/v1/microcrystal-observations      （Idempotency-Key 必填；capabilities 必含 schemaVersion+revision）
  → GET /api/v1/microcrystals/{id}/capabilities  （X-Connection-Proof）
```
关键约束：`capabilities` 必含 `schemaVersion`（JSON 整数 ≥1）与 `revision`（bigint 字符串），其余键透传；`state` 为**不透明透传**；观察者身份**只取自 token，绝不取自请求体**。

---

## 6. 术语统一表（对外文档与客户端 UI 建议一致使用）

| 中文术语 | 英文/字段 | 说明 |
|---|---|---|
| 测肤任务 | skin assessment task | 一次三视角拍照与分析任务 |
| 照片版本 | photo version (`photoVersion`) | 首次为 `"1"`，补拍为当前版本 +1 |
| 测肤报告 / 统一报告 | skin report (`reportId`) | 对外可用"测肤报告" |
| 护理方案 | care plan (`planId`) | 由报告生成；状态 `waiting_inputs/generating/ready/failed` |
| 护理执行 | care execution (`executionId`) | 状态 `admitted/running/paused/unknown/stopped/closed`；**`admitted` = 已登记，待端侧确认** |
| 方案进度 | progress | **N = 目标次数、K = 已同步次数**（单位：**次**），剩余 = `max(N−K, 0)` |
| 实际完成记录 | execution record | 一次有效完成明细（**不要**与下面的"护理执行记录"混用） |
| 护理执行记录 | care execution history | 执行历史列表 |
| 微晶 | microcrystal | 护理硬件统一称谓 |
| 云台 | gimbal | 拍照/人脸追踪/联网/心跳设备 |
| 成员访问授权 | member access grant | 账号查看某成员资料的授权；状态 `active/revoked`（**无过期时间列**） |
| 通知目标 | notification destination | 推送投递目标；状态 `active/disabled/invalid` |
| 绑定代次 | binding revision | 每次**真实**绑定/解绑 +1 |
| 账号 / 成员 | account / member | **不可混用**：账号 = 登录 APP 的主体；成员 = 被识别的人 |
| APP session token / gimbal device session token | — | 直用英文，勿译 |

---

## 7. 未冻结 / 待定清单（联调时请勿依赖具体取值）

| 项 | 现状 | 客户端应对 |
|---|---|---|
| 微晶 `capabilities` 的参数名/单位/范围 | **未冻结**（须来自已验证的微晶协议）；仅 `schemaVersion`/`revision` 可依赖 | 容忍未知键；不要把任何参数名硬编码为稳定契约 |
| 微晶观察 `state` | **不透明透传**，结构未冻结（已知键集合为空） | 不得依赖任何具体键名，也不得假设字段存在 |
| 云台连接状态编码 | 实现取值为 `unknown/online/offline`，但契约标注**编码待定** | 以服务端实际返回为准，容忍新增取值 |
| 心跳 `incidents[].code`/`severity` 枚举与上报频率 | 契约标 `x-detail: skeleton`，**未冻结** | 容忍未知键；服务端只读 `code/state/cleared/severity/detail`；其中 **`detail` 的内部结构未冻结**（文档中建模为显式开放对象），客户端不得依赖其任何具体键 |
| 通知 `registration` 结构与 `provider` 取值 | **推送通道未选定**；仅 `schema_version`（JSON 整数，缺省服务端注入 1）可依赖 | 按提供方协议填写；服务端**绝不回传完整推送 token** |
| 测肤报告 `metrics` 的指标名/区域枚举/单位 | 每元素**仅** `name/value/unit` 三键（封闭白名单），但**指标名与区域枚举未冻结**（须来自测肤协议，不得自由发明） | 按 `name`+`unit` 原样展示，不要硬编码指标集合 |
| 报告列表项 `reportSummary` | **已知三键**（取证自写入方 `assessment_analyze.py:412-417`）：`schema_version`（integer，当前固定 1）、`conclusion`（string，测肤结论；**取值集合未冻结**、无枚举约束）、`headline_metrics`（array，要点指标名，**最多 8 项**；指标名集合未冻结、须来自测肤协议）。**剩余扩展边界**：写入方未来可能新增键 ⇒ `additionalProperties=true`；该字段整体可空（报告未就绪时为 null）；`failure_detail`/`identity_result` 等内部诊断**绝不外发** | 仅**识别**这三键，且**每键都按可选处理**（不得假设任何键必然出现）；容忍未知键；容忍整体为 null |
| 护理方案正文（`plan`/`planSummary`/`planExecution`） | 服务端**白名单投影**（封闭）；`schema_version` **绝不外发**；禁止返回供应商原始响应/提示词；该白名单标注"待契约确认后冻结"。**嵌套形状**：`steps` 是**对象数组** `{region: string, parameters: <动态映射>}`（服务端只保留这两键，其余丢弃；过滤后为空的步骤整体丢弃）；`regions` 是 `array<string>`；`parameters` 是**键名不固定的动态映射** `{参数名: 标量 或 {value, unit}}`（`value` 可为 string/number/boolean，`unit` 必为字符串，其余键丢弃） | 只使用文档列出的键；**不得发明参数名**（参数名/单位/取值范围未冻结，须来自已验证微晶协议） |
| token 有效期 / 刷新窗口 | **真实会话提供方未选定**，无权威数值 | 以响应中的 `expiresAt`/`serverTime` 为准 |
| APP 侧 `installBindingMaterial` | **不透明对象、结构未冻结**，当前基础层不解释 | 不要依赖任何键 |

---

## 8. 生成文档的已知限制（如实披露）

1. **multipart 的条件必填**：`PUT …/photo-versions/{photoVersion}` 的图片 part 是**按 `metadata.replacedViews` 条件必填**的——生成文档已据此把 `required` 标为**仅 `metadata`**，三张图片 part 的 `required=false`，条件规则写在各 part 的 description 中。客户端须保证**上传的图片 part 集合与 `replacedViews` 精确一致**：未列入的视角**不得**上传多余 part，否则会被服务端拒绝（`replacedViews` 本身须非空、元素 ∈ `front`/`left`/`right`、不可重复）。
   > 对比：`POST /api/v1/skin-assessment-tasks`（首次提交）的 `metadata`+`front`+`left`+`right` **四件全部必填**；`POST /api/v1/care-executions` 与 `…/revalidations`、`POST /api/v1/member-access-grants` 为 `metadata`+`face` **两件必填**。
2. **属性级 `required` 已按契约修正**：springdoc 只能从 Java 校验注解推导 `required`，而本项目部分必填字段是**手工严格校验**的（multipart 的 metadata 解析器与授权控制器），故生成结果原会缺失。现已通过文档目录的 `requiredProperties()` 按**契约**修正：`A01Metadata`/`A02Metadata`/`M1A01Metadata`/`Capture` 的必填字段与契约一致，且这些字段**服务端确实强制**（缺失或非法 → 400 `INVALID_INPUT` + `details.fields`）。
   **唯一例外**：`EchoJobRequestBody.numbersAsStrings` —— 契约要求必填，但**当前 Java 实现未强制**（缺失会被容忍），属**实现偏差**；文档已按契约标为必填并在描述中如实注明该偏差，**不得据此改写契约**。
3. **不透明字段**：第 7 节列出的字段在文档中标注为"显式不透明对象"，**这是诚实标注而非遗漏**。全项目**经核准的不透明字段恰为 3 个**（`MicrocrystalObservationBody.state`、`M4A04Metadata.reportedMicrocrystalState`、`AppSessionRequestBody.installBindingMaterial`），由覆盖率门禁的核准清单强制约束——任何新增的不透明声明都会使构建失败，须先补出经取证的已知键或经审议加入清单。
   > 曾有一处**错误的不透明声明**已被修正：`SkinReportListItem.reportSummary` 曾被声明为"无可取证键"，实际写入方 `assessment_analyze.py` 固定构造 `schema_version`/`conclusion`/`headline_metrics`（最多 8 项）三个键，现已按事实展开。
4. **全局 `bearerAuth` 不表达细粒度权限**：某端点是"仅 APP"还是"仅云台"，请看该端点 description（类型不符 → 403 `CALLER_NOT_ALLOWED`）。
5. **OpenAPI 版本差异与 `type` 缺失**：生成文档为 **3.1.0**，手写契约为 **3.0.3**；标题与少量表达方式不同属预期，不代表行为差异。其中一处可见差异需知悉：生成文档中**多数 component 未声明 `"type": "object"`**（实测 61 个中 47 个只有 `properties`/`required`），这是 springdoc 对 Java record 在 OpenAPI 3.1 下的输出习惯；权威契约则显式声明 `type: object`。
   ⚠️ **准确语义（勿误解）**：JSON Schema **并不会**由 `properties` 推导出"实例必须是对象"——若实例不是对象，只是**不会应用** `properties` 的约束而已。因此该文档**不宜作为严格 JSON Schema 验证器的输入**；主流 OpenAPI 代码生成器通常仍能从 `properties` 正确生成模型，故用于人工阅读与生成客户端骨架是安全的。若你的工具链需要严格校验，请以权威契约为准。
6. **`additionalProperties` 未与契约同步**：契约对若干 inline 响应结构声明 `additionalProperties: false`（如 `EchoJobLastError`、`SkinReportImage`、`CurrentAssessment`、`RecordWatermark`），生成文档未显式设置 ⇒ 机器文档比契约**更宽松**（不禁止额外键）。实际无行为风险（响应 DTO 是 record，不会输出额外字段），但若你依赖该关键字做严格校验，请以契约为准。
7. **文档仅 dev/test 可见**：生产环境文档端点关闭且**强制启用会拒绝启动**。

---

## 9. 如何本地查看（B 包测试资源；请勿占用他人端口）

```bash
cd backend/web-java
MAVEN_OPTS="-Xmx768m -XX:MaxMetaspaceSize=320m" mvn -B -DskipTests package

SERVER_PORT=18083 SPRING_PROFILES_ACTIVE=dev APP_ENV=dev \
  SPRING_DATASOURCE_URL="jdbc:postgresql://127.0.0.1:55435/mvp_b_dev" \
  SPRING_DATASOURCE_USERNAME=postgres SPRING_DATASOURCE_PASSWORD=<local-test-password> \
  APP_STORAGE_DEV_DIR=<scratch-dir> \
  java -Xmx384m -XX:MaxMetaspaceSize=256m -jar target/web-java-0.0.1-SNAPSHOT.jar
# Swagger UI:  http://127.0.0.1:18083/swagger-ui/index.html
# 机器可读:    curl -sS --noproxy '*' http://127.0.0.1:18083/v3/api-docs
```
- **端口纪律**：B 只用 **18083**（Web）/ **18084**（worker）与 **55435**（`mvp-b-pg`）；**严禁** 18080（总协调预览）、3000、5432/55432（A）、18081/18082/55433（E）、18085/55436/55437（C）。用毕必须 kill，**不留常驻预览**。
- 跑 Java 测试须显式指定测试库，否则测试基建会去连**禁用的 55432** 并使所有 `@SpringBootTest` 上下文加载失败：
  `MVP_A_PG_JDBC=jdbc:postgresql://127.0.0.1:55435/postgres MVP_A_PG_USER=postgres MVP_A_PG_PASSWORD=<pw> mvn -B test …`

---

## 10. 相关交付物
- `backend/handoffs/B.md` —— B 包交付主文档（第 14 节为本轮 Swagger 联调注释）
- `backend/handoffs/B-oracle.md` —— 历轮实际 Oracle 审查记录（含本轮最终 SHA 的有界复审）
- `backend/handoffs/B-seam-repro.md` —— 测试注入缝的 E 复验手册（与本轮无关，勿混用）
- `backend/contracts/openapi/openapi.yaml` —— **权威契约**（不一致时以它为准）
- `backend/doc/` —— 设计文档体系（已确认决策 > API 设计 > 数据架构 > 详细设计）
