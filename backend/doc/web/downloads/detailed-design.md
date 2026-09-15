# 后端详细设计 V1：五模块 MVP

日期：2026-09-10
状态：开发设计草案；不是已实现接口、已执行迁移或生产发布说明。

## 1. 依据、范围与阅读方式

依据：[数据架构](数据架构设计-V1-五模块-MVP.md)、[技术架构](技术架构设计-V1-MVP.md)、[27 个业务 HTTP API](后端API接口设计-V1-五模块与流程对应.md)、[测试决策](测试需求决策记录.md)、[94 个测试场景](测试场景清单-V1-五模块与双控制.md)、[人脸服务调研](人脸服务调研与推荐方案-V1-MVP.md)。起始文档提交为 `178b1916a0ab2241f8c297549333283211c25414`。

本文把架构展开到请求字段、应用服务、单表读写、状态机、事务与任务协议。表字段及历史业务规则以上述主文档为准；本文新增的字段编码、状态转换条件、基础协议和配置值是实施建议，需通过契约评审后冻结。本文不修改已有业务 API 的方法、路径和编号。

### 1.1 保持的业务约束

- Java Web、Python Worker、Nginx、PostgreSQL、Redis、私有 OSS；五个核心运行组件外加 Redis 状态依赖，五个逻辑模块。没有后端到微晶的控制通道。
- 14 张业务表，使用现有宽表和 JSONB；默认不写 JOIN、关联子查询和 ORM 自动关联。多次单表查询可以处于一个事务。
- 云台自主认证和测肤；账号绑定只决定通知接收者。APP 测肤不在本版。
- APP 成员查看关系长期有效，主动撤销后后续读取拒绝；云台仅访问唯一当前任务，不提供历史列表。
- 同一微晶最多一个未收尾执行；状态未知、断网、程序重启、任务租约到期均不释放占用。
- N、K 均为次数；K 只由合法明细去重增加，K ≥ N 完成，K 不截断；已关闭执行的合法迟到明细仍入原账。
- Java 掌握执行、账本与 K；Python 只生成报告/方案/N 及处理通知，不覆盖 K、不关闭执行。

### 1.2 本稿补齐与仍有前提的部分

| 类别 | 本稿处理 |
|---|---|
| 可直接用于编码评审 | 27 个业务 API 字段草案、计数/收尾协议、去重、任务交接、查询投影、锁与约束 |
| 开发建议 | Spring MVC + Spring JDBC + Flyway、Python 数据适配、配置初值；依赖版本由实现工程锁定 |
| 基础能力前提 | 手机号验证与可撤销会话提供方、设备凭据和连接证明；给出接入契约，不伪造供应商已选定 |
| 人脸前提 | 阿里云先做 PoC 的建议保持；自动新人判定、活体/采集绑定尚需验证；自建路线按专项报告实施 |
| 产品与合规前提 | 非刷脸替代方式、人脸同意撤回与删除、保存期限尚未冻结，见第 14 节；不得仅接一个确认字段就认定合规完成 |

27 是现有业务 API 数量，不包括登录/会话、图片二进制读取等基础协议。本文列出这些缺口并给出建议，不把它们偷偷编成 M6，也不声称 14 表天然包含会话系统。

## 2. 工程职责与可测试单元

Java 每个模块采用 Controller → ApplicationService → Repository。Controller 负责输入校验、认证上下文、HTTP 映射；ApplicationService 编排业务和事务；Repository 只执行显式 SQL，不提交事务。DTO 不直接序列化数据库整行。

| 模块 | Java 应用服务职责 | Python Handler 职责 | 权威表 |
|---|---|---|---|
| M1 | MemberAccessService：授权/撤销/导航；IdentityVerifier：同步核验；AccountResolver：账号映射 | AssessmentHandler 内可靠身份归档 | accounts、members、member_access_grants |
| M2 | GimbalService：认证上下文/心跳/绑定；MicrocrystalService：能力和观察 | IncidentScanner：离线及异常派生 | gimbals、microcrystals |
| M3 | AssessmentService：受理/补拍；ReportQueryService：查询及投影 | AssessmentHandler：质量、同人、归档、报告发布 | skin_assessments |
| M4 | CareAdmissionService、CareLedgerService、CareClosureService、CareQueryService | PlanHandler：等待输入、生成、验证和发布 N | care_plans、care_executions、care_records |
| M5 | DestinationService：安装实例目标更新 | NotificationHandler：路由重检和投递 | notification_destinations、notifications |
| 公共设施 | RequestDeduplicator、MediaService、PrincipalResolver、TransactionTemplate | JobRunner、MediaRepository、ProviderAdapters | media_objects、async_jobs、idempotency_requests |

上述名称用于代码职责，不是额外 HTTP 接口。模块可通过同进程普通方法调用共享一个 Java 事务；Java 与 Python 只共享版本化数据契约，不共享内存或事务上下文。

对外部服务定义窄适配职责：FaceProvider 输出身份分类；SkinProvider 输出测肤结构；PlanProvider 输出候选方案；PushProvider 输出通道受理状态。每个适配器有独立超时和并发上限。业务 SQL 和供应商 SDK 不混在 Controller。

## 3. HTTP 通用契约

### 3.1 编码、头与分页

| 项目 | 约定 |
|---|---|
| 字段命名 | HTTP JSON 用 camelCase；PG/任务 JSON 用 snake_case；映射显式定义 |
| ID | 服务端资源为 UUID 字符串；客户端记录/安装标识为受限文本，建议不超过 128 字符 |
| 整数 | N/K、序号、revision 等 bigint 在 HTTP 和任务 JSON 中统一使用十进制字符串；schema_version 等小版本号用 JSON 整数 |
| 时间 | RFC3339 UTC，例如 2026-09-10T04:00:00Z；客户端时间只供诊断，不用于全局排序 |
| 认证 | Authorization: Bearer …；APP 安装实例必须和可验证会话绑定；请求体不能声明自己是哪个账号/云台 |
| 逻辑请求去重 | 业务写接口使用 Idempotency-Key；同逻辑重试保持键和内容；更换照片/业务内容使用新键 |
| 追踪 | 每次 HTTP 尝试生成 requestId；T13.id 是跨重试稳定的逻辑请求 ID，二者区分 |
| 分页 | limit 默认 20、上限 100；cursor 绑定排序值、ID 和筛选摘要；非法游标返回 400，不默认查询总数 |
| 图片 | multipart/form-data：metadata 为 application/json，图片为二进制 part；无独立直传 OSS 接口 |
| 缓存 | 成员敏感数据和图片 Cache-Control: no-store；不把签名 URL、token 写日志 |

JSON 示例中的 `...Id` 占位符用于说明结构，不表示实际 UUID。正文未列的可选查询条件不自动支持。未知业务写字段建议拒绝，避免拼错字段静默成功；客户端必须容忍响应新增字段。

成功响应（204 除外）：

```json
{
  "requestId": "http-attempt-id",
  "data": {},
  "meta": {"replayed": false, "serverTime": "2026-09-10T04:00:00Z"}
}
```

列表 data 为 `{items: [], nextCursor: null}`。错误响应为 `{requestId, error: {code, message, retryable, details}}`；details 只包含调用方可见的冲突字段、缺失序号等，不泄露不可见对象的归属、人脸候选或供应商诊断。

### 3.2 错误码与重试动作

| HTTP | 业务原因示例 | 调用方动作 |
|---|---|---|
| 400 / 413 / 415 / 422 | INVALID_INPUT、UPLOAD_TOO_LARGE、UNSUPPORTED_IMAGE、FACE_QUALITY_REJECTED | 修正内容，新逻辑请求使用新键 |
| 401 | AUTH_REQUIRED、SESSION_INVALID | 重新认证；不能伪装新 installationId 接管旧执行 |
| 404 | RESOURCE_NOT_VISIBLE | 不泄露资源是否存在；不能换 ID 探测 |
| 403 | CALLER_NOT_ALLOWED、FACE_NOT_VERIFIED | 不授予权限；重新采集属于新请求 |
| 409 | IDEMPOTENCY_CONTENT_CONFLICT、BINDING_CHANGED、TASK_REPLACED、PHOTO_VERSION_CONFLICT | 刷新当前状态并重新操作；旧请求不得改写新事实 |
| 409 | DEVICE_OCCUPIED、PLAN_NOT_READY、PLAN_COMPLETED、EXECUTION_NOT_RESUMABLE | 不启动；按明确状态处理 |
| 409 | RECORD_CONFLICT、CLOSURE_GAPS、STOP_NOT_CONFIRMED | 保留待同步记录，修正/补传后以新键收尾 |
| 409 | REQUEST_IN_PROGRESS | 按 Retry-After 等待，使用同一逻辑键重试 |
| 429 / 503 / 504 | RATE_LIMITED、DEPENDENCY_UNAVAILABLE、DEPENDENCY_TIMEOUT | 受限重试；从未返回“默认核验通过” |

无可靠人脸匹配与身份歧义对客户端只给“未能确认本人/暂无可关联资料”，不返回候选人员列表。内部可以保留不同分类用于诊断。GET 无副作用，失败查询不触发重分析、生成方案或改变执行。

### 3.3 请求规范化与幂等处理

1. 先认证和校验输入；流式计算图片原始字节 SHA-256、校验实际图片格式。multipart 边界、字段顺序、HTTP requestId 和接收时间不参与摘要。
2. 组装规范化对象：operation、路径参数、语义字段、图片 part 名与内容摘要；对象键排序、UTF-8、无空白、禁止重复 JSON 键，整数使用规范十进制字符串，无前导零。缺省值先展开；集合按协议排序，顺序有含义的数组不排序。
3. T13 唯一作用域为 APP(accountId + installationId) 或云台(gimbalId)，加 operation 与 Idempotency-Key。插入 processing；已存在时对比 payload_hash。
4. processing 且租约未到期返回 REQUEST_IN_PROGRESS；到期后条件更新 attempt_revision 和 lease_until。旧处理者最终 UPDATE 不满足代次时整个业务事务回滚。
5. 业务资源写入和 T13.succeeded 在同一最终事务提交；确定性业务拒绝写 rejected。依赖临时失败可保持 processing，设置下一次可接管时间，结果摘要记录 retryable；不把临时失败永久记成不可重试。
6. succeeded 重放只定位原资源，再按当前权限及生命周期投影；不重做绑定、不切旧任务指针、不重新核验、不赋予新的启动有效性。rejected 重试返回原拒绝；条件已改变的用户操作使用新键。
7. 图片/活体证据过期时，旧逻辑请求不能通过自动重新调用获得新鲜性；返回重新采集要求，用户重新采集使用新键。

删除大照片或诊断数据不删除必要的 T13 去重事实。T08 记录级去重独立于 T13；批次拆分重传仍然不能重复入账。

## 4. 认证、权限与基础协议

### 4.1 手机号账号与会话

建议先接入具备手机号验证、会话刷新/撤销能力的认证提供方。提供方需验证稳定 subject、应用范围和会话有效性；Java 映射到 T14 本地账号，并检查 active/auth_revision。不能把请求体手机号当作认证结果。

基础 HTTP 建议路径（不计入 27 个业务 API）：

| 路径建议 | 输入/输出 | 实施约束 |
|---|---|---|
| POST /api/v1/auth/sms-challenges | phone、purpose=login → challengeId、retryAfter | 供应商负责验证码生命周期和风控；不泄露账号是否已存在 |
| POST /api/v1/auth/sessions | challengeId、code、安装绑定材料 → 会话凭据、本地 accountId | 验证成功后按 login_provider/login_subject 并发唯一映射；不可仅接受裸 installationId |
| POST /api/v1/auth/session-refreshes | 真实刷新凭据 → 新凭据 | 轮换与旧凭据撤销由选定会话协议保证 |
| DELETE /api/v1/auth/sessions/current | 当前会话 → 204 | 使当前会话不可再用；失效 T09 当前 session_ref 对应目标，其他安装实例不受影响 |

提供方调用与 PG 无共同事务。退出先撤销会话；PG 目标更新失败允许幂等补偿，通知发送前仍核实目标会话是否有效，查询失败不投递。旧会话退出补偿必须按 session_ref 条件更新，不能失效后来新登录的目标。认证提供方必须能证明 session 与安装实例绑定；若不具备，则此方案不成立，需追加会话存储设计和迁移，不能滥用 T09/T13 存明文 refresh token。

供应商、手机号回收/重新注册处理、安装重建和会话撤销接口尚未选定；这是认证联调前的阻塞项，业务模块可通过替身接口开发，不对真实用户假装已完成。账号禁用不等于资料删除或注销。

### 4.2 云台与微晶证明

M2-A01 验证设备凭据后签发云台会话，绑定 gimbalId、credentialVersion、会话 ID。配对证明用于 M2-A06/A07，须绑定云台、当前账号/安装实例、目的、nonce、有效期和可验证签名。微晶 connectionProof 绑定控制端、微晶及当前连接，不接受仅提交序列号。

此处定义验证器的输入输出和失败关闭行为，设备签名算法、密钥预置/轮换、可信硬件能力由设备团队对接。若设备没有签名证明能力，必须明确替代信任方案；不能生成一个未经验证的客户端字段就当成已认证。会话代次决定新旧连接，客户端自填 epoch 不具有替换旧会话的权力。

### 4.3 权限判断表

| 资源/动作 | APP | 云台 |
|---|---|---|
| 报告/方案/护理历史 | T02 存在本人账号的 active 关系 | 禁止历史列表；仅当前任务结果的允许投影 |
| 云台状态 | 当前绑定账号；仅配网证明不开放成员资料 | 只限自己 |
| 绑定状态 | 登录 + 当前配对证明；输出 unbound/self/other | 不通过账号配网入口调用 |
| 新执行 | 查看权 + 当前本人核验 + 微晶连接 + 方案/占用检查 | 当前任务 + 当前本人核验 + 微晶连接 + 方案/占用检查 |
| 原执行补传/收尾 | 原 accountId + installationId 且认证有效 | 原 controller_gimbal_id 且认证有效 |
| 原执行最小对账 | 即使查看关系撤销，可返回自己的确认水位/关闭状态；不返回成员资料、方案正文或跨执行总进度 | 旧任务也仅能对账，不取历史方案 |
| 图片 | 按图片用途与业务归属；查看权不等于可读核验照片 | 当前任务且报告投影明确公开的图片 |

“候选范围”指服务端受控的本产品身份命名空间及适用规则，不按云台绑定账号划库；M1-A01 是为尚未建立关系的本人获得授权，不能先要求已有授权才允许匹配。1:N 结果只在后端内部使用。

## 5. API 详细处理清单

以下每个入口都继承第 3、4 节公共约束。必填字段除明确标为可选者外都必须存在；主体身份字段由服务端派生。写接口还使用 T13，照片入口还使用 T11；表清单只列核心读写，完整事务见后续章节。`Progress`、`Verification`、`Report` 等结构在第 6 节定义。

### M1-A01 · 人脸授权查看本人资料

`POST /api/v1/member-access-grants`

- 输入：multipart：metadata.capture（见 6.2）、consentEvidenceRef；face 图片。不得提交目标 memberId 强制授权。
- 输出：201 新关系 / 200 已存在或重放：grantId、memberId、status、grantedAt；无匹配不返回候选列表。
- 处理与落库：T01 定位可靠成员；事务检查有效状态，T02 新建 active 或返回已有 active，T13 绑定实际 grantId。核验留存与查看授权分开。
- 异常/重放：旧请求指向的关系已撤销，返回 GRANT_REVOKED，不创建新关系；同意证据验证前提见 14 节。

### M1-A02 · 查询当前账号已有成员访问关系〔查询导航配套〕

`GET /api/v1/me/member-access-grants`

- 输入：可选 limit、cursor。
- 输出：200：items[{grantId,memberId,grantedAt,memberSummary}]；仅 active。
- 处理与落库：T02 按 account_id/status 分页，展示摘要来自本行，无需逐条读取成员。
- 异常/重放：没有成员关系返回空数组，不搜索人脸库。

### M1-A03 · 撤销当前账号与某个人脸对应成员的查看关联

`DELETE /api/v1/me/member-access-grants/{grantId}`

- 输入：路径 grantId；Idempotency-Key。
- 输出：204；同一账号重复撤销完成也返回 204。
- 处理与落库：锁 T02，校验账号，active → revoked，填 revoked_at；T13 同事务成功。
- 异常/重放：他人 grant 返回 404；不删除任何成员/报告，不影响其他 active 关系；旧 grant 的撤销不作用于后来新 grant。

### M2-A01 · 云台认证或恢复连接后重新认证

`POST /api/v1/gimbal-sessions`

- 输入：设备凭据、credentialVersion、认证提供方要求的 nonce/proof；格式由设备协议冻结。
- 输出：200：gimbalId、会话凭据、expiresAt、serverTime；不返回成员资料。
- 处理与落库：单表 T03 验证主体/凭据版本，调用认证适配器；认证失败不更新可信在线。
- 异常/重放：不以 Idempotency-Key 缓存可重放的秘密凭据；认证握手使用提供方防重放协议，不产生护理资源。

### M2-A02 · 上报心跳和云台已知工作状态

`POST /api/v1/gimbals/{gimbalId}/heartbeats`

- 输入：observationEpoch、observationSeq、observedAt、powerState、可选 taskId/executionId 和 incidents[]。
- 输出：200：accepted、lastSeenAt、statusRevision、serverTime；可提示需对账，不下发动作命令。
- 处理与落库：验证会话 epoch；锁 T03，仅新序号更新 latest_observation/last_seen_at，异常 episode 变化可写 T10/T12。
- 异常/重放：重复旧心跳不延长在线时间、不覆盖新状态；任务/执行引用只作观察，不移动指针、不累计次数。

### M2-A03 · 查询云台状态

`GET /api/v1/gimbals/{gimbalId}/status`

- 输入：路径 gimbalId。
- 输出：200：connectionStatus、powerState、lastSeenAt、isStale、statusRevision、已知异常摘要。
- 处理与落库：T03 单表读，按绑定账号或本云台裁剪；工作状态不含成员详情。
- 异常/重放：未经许可对象 404；离线和未知不推断微晶停止。

### M2-A04 · 登记已连接微晶的能力与状态观察

`POST /api/v1/microcrystal-observations`

- 输入：microcrystalSerial、connectionProof、capabilities{schemaVersion,revision,parameterRanges,...}、observationEpoch/Seq、observedAt、state。
- 输出：200：microcrystalId、accepted、capabilityRevision、receivedAt。
- 处理与落库：证明验证后 T04 唯一 serial 定位/登记，锁行校验来源/顺序，更新能力/观察；等待方案由 Worker 扫描推进。
- 异常/重放：不同来源不能比较裸 seq；禁止以观察抢占 T07；能力具体参数名/单位必须来自已验证的微晶协议。

### M2-A05 · 读取后端已登记微晶能力〔能力查询配套〕

`GET /api/v1/microcrystals/{microcrystalId}/capabilities`

- 输入：路径 microcrystalId + 合法 connectionProof/已验证连接上下文。
- 输出：200：capabilities、capabilityRevision、observedAt、receivedAt、isStale。
- 处理与落库：T04 单表读；证明在查询前验证。
- 异常/重放：能力存在不意味着微晶空闲或现场就绪。

### M2-A06 · 用户主动绑定云台到当前账号

`PUT /api/v1/me/gimbal-bindings/{gimbalId}`

- 输入：路径 gimbalId；expectedBindingRevision、pairingProof。
- 输出：200：bindingStatus=self、gimbalId、bindingRevision、boundAt。
- 处理与落库：锁 T03：检查预期代次；空绑定写当前账号并增代次；已属本人且代次相符不重复写。
- 异常/重放：他人已绑定返回 BOUND_TO_OTHER；代次不同返回 BINDING_CHANGED；查询和提交之间竞争不能覆盖他人。

### M2-A07 · 配网时查询云台绑定状态

`GET /api/v1/gimbals/{gimbalId}/binding-status`

- 输入：路径 gimbalId；请求头携带有效配对上下文。
- 输出：200：bindingStatus=unbound/self/other、bindingRevision；不返回他人账号 ID/手机号。
- 处理与落库：证明验证后单表读取 T03，不写绑定。
- 异常/重放：未登录只配网，无需调用；任意 gimbalId 不构成访问证明。

### M2-A08 · 原账号解除云台绑定

`DELETE /api/v1/me/gimbal-bindings/{gimbalId}`

- 输入：路径 gimbalId；建议 If-Match: "binding-{revision}"；Idempotency-Key。
- 输出：204，已解绑的原请求可重放；拒绝跨代次解绑。
- 处理与落库：锁 T03 校验当前账号及 revision，清 bound_account_id/bound_at，真实解绑递增 revision。
- 异常/重放：原请求重放只确认旧操作；新的未知解绑请求若不能证明原关系则拒绝，不猜测未绑定之前属于谁。

### M3-A01 · 提交三视角测肤任务

`POST /api/v1/skin-assessment-tasks`

- 输入：multipart：metadata{photoVersion:"1",captureSessionId,consentEvidenceRef} 与 front/left/right 三图。
- 输出：202：taskId、status=queued、photoVersion、currentAssessmentRevision。
- 处理与落库：T11 上传可用后锁 T03，查 T07 未收尾云台执行，插 T05、换当前指针并增代次、插分析 T12、完成 T13。
- 异常/重放：缺失/格式失败不受理、不切指针；旧请求重放给原 taskId/replaced 标记，不返回旧结果、不恢复指针。

### M3-A02 · 补拍并提交新照片版本

`PUT /api/v1/skin-assessment-tasks/{taskId}/photo-versions/{photoVersion}`

- 输入：路径 taskId/photoVersion；metadata.expectedPhotoVersion 与本次更换视角清单；相应图片 part，未更换视角由后端沿用。
- 输出：202：同 taskId、新 photoVersion、queued；同请求重放不增加版本。
- 处理与落库：先锁 T03 再 T05；必须当前任务且 needs_retake，新版本=旧版本+1；生成完整视角清单，processing_revision 增加并插新 T12。
- 异常/重放：report_ready 不补拍；任意跳版本/其他任务媒体拒绝；旧分析写回被版本检查拦截。

### M3-A03 · 查询测肤任务及补拍要求

`GET /api/v1/skin-assessment-tasks/{taskId}`

- 输入：路径 taskId。
- 输出：200：taskId、status、photoVersion、requiredViews[]、可公开 failureCode/retryable；ready 时 reportId。
- 处理与落库：T05 读取后，以 APP/T02 或云台/T03 当前指针验权；不读取方案全文。
- 异常/重放：未可靠关联 memberId 的任务不向 APP 开放；后台重试不靠 GET 触发。

### M3-A04 · 列出可访问报告〔查询导航配套〕

`GET /api/v1/members/{memberId}/skin-reports`

- 输入：路径 memberId；可选 limit/cursor。
- 输出：200：items[{reportId,reportReadyAt,reportSummary}]。
- 处理与落库：先 T02 验权，再 T05 按 member_id/report_ready_at/id 游标读正式报告摘要。
- 异常/重放：云台禁止；无正式报告返回空，不逐条加载大载荷。

### M3-A05 · APP 查询报告或云台获取本次报告

`GET /api/v1/skin-reports/{reportId}?view={view}`

- 输入：路径 reportId；view 必须为 full 或 brief，默认 APP full、云台 brief。
- 输出：200：Report 对应白名单、images[{mediaId,contentUrl}]。
- 处理与落库：T05 按 report_id 取正式版本；APP T02 / 云台 T03 验权；结果图片引用来自冻结载荷。
- 异常/重放：云台传 full 返回拒绝，不默许扩权；核验原图不会混入报告 images。

### M3-A06 · 云台恢复后端保存的当前测肤任务

`GET /api/v1/gimbals/{gimbalId}/current-assessment`

- 输入：路径 gimbalId，仅自身云台。
- 输出：200：currentAssessment=null 或 {taskId,status,photoVersion,reportId?}、currentAssessmentRevision。
- 处理与落库：T03 读指针后 T05 读状态；无任务无需第二次读，不写指针。
- 异常/重放：不返回方案或历史列表；重启仍需 M4-A03/A04。

### M4-A01 · 列出本人方案与生成状态

`GET /api/v1/members/{memberId}/care-plans`

- 输入：路径 memberId；可选 limit/cursor。
- 输出：200：items[{planId,generationStatus,planSummary,progress?}]。
- 处理与落库：T02 验权再 T06 单表分页；waiting_inputs/failed 方案行也可表达状态。
- 异常/重放：不触发生成；无方案行为空数组；云台不能调用。

### M4-A02 · 查询方案完整版

`GET /api/v1/care-plans/{planId}?view=full`

- 输入：路径 planId；view=full。
- 输出：200：generationStatus、ready 时 Plan 与 Progress；未就绪时公开失败/等待原因。
- 处理与落库：T06 定位成员再 T02 验权。
- 异常/重放：GET 不给予启动或恢复许可；云台不可借 full 查询取方案。

### M4-A03 · 当前人脸核验、取得本人方案并登记新执行

`POST /api/v1/care-executions`

- 输入：multipart：microcrystalId、connectionProof、capture、consentEvidenceRef；APP 提供 planId；云台提供 currentTaskId/currentAssessmentRevision；face 图片。
- 输出：201：executionId、status=admitted、controller、Plan 执行投影、Progress、Verification；重放 200 且不得视为首次启动响应。
- 处理与落库：锁外读取/验权/核验；最终按统一顺序锁 T03(云台)/T04/T06/T02，确认 K<N 和无占用后插 T07，冻结归属和方案快照。
- 异常/重放：原子唯一约束拒绝第二个占用；云台由当前 task 解析方案；请求体 memberId/controller 不决定归属。

### M4-A04 · 使用者连续性失效后重新核验恢复条件

`POST /api/v1/care-executions/{executionId}/revalidations`

- 输入：multipart：路径 executionId；expectedVerificationRevision、capture、consentEvidenceRef、face；先经 M4-A05 同步实际暂停观察及待补记录。
- 输出：200：原 executionId、保留进度、更新后的 Verification 和允许投影；执行不会自动变 running。
- 处理与落库：锁外核验指定成员；最终锁当前云台/微晶/方案/执行/授权，检查暂停、K<N、原控制端和预期代次，更新核验摘要/代次。
- 异常/重放：unknown 必须先收到新鲜 paused 观察；stopped/closed 不恢复；重放不刷新核验有效期。

### M4-A05 · 同步实际状态与有效完成记录

`POST /api/v1/care-executions/{executionId}/observations`

- 输入：路径 executionId；可选 observation；records[]（可为空，结构见 6.3）；批次 Idempotency-Key。
- 输出：200：acknowledgedRecords[{recordId,disposition}]、executionStatus、acceptedCount；有读取权限才附 Progress。
- 处理与落库：由 T07 取固定 plan 归属，锁 T06/T07，批量读 T08 判重/冲突，插新增后同事务增加两个汇总，独立判断状态新旧。
- 异常/重放：批次内容冲突整体 409、不确认新记录；旧状态可忽略但合法新明细仍入账；已撤销查看关系的原端只返回本执行最小确认信息。

### M4-A06 · 确认本地已停止并完成执行收尾

`POST /api/v1/care-executions/{executionId}/closure-confirmations`

- 输入：路径 executionId；stopObservationSeq、reason、recordStreamEpoch、finalRecordSeq、finalCount；Idempotency-Key。
- 输出：200：closed=true、closedAt、occupancyReleased=true；未停止/有缺口返回 409 及最小对账信息。
- 处理与落库：先上传停止观察与记录；锁 T06/T07，核对已接受的 stopped 观察及 T08 连续水位/总数；T07 填 closure_manifest/status/closed_at。
- 异常/重放：不是停止命令；不接收单个 synced=true 替代对账；迟到合法记录不改 closed。

### M4-A07 · 查询执行及恢复联网后的对账状态

`GET /api/v1/care-executions/{executionId}`

- 输入：路径 executionId；可选 recordsAfterSeq、limit，用于对账。
- 输出：200：有权 APP 取执行摘要；原端最小投影含 status、acceptedCount、record 水位/ID 确认、closedAt。
- 处理与落库：T07 读固定主体；APP 查看额外查 T02；需确认清单时单表分页 T08。
- 异常/重放：撤销授权后不返回 Plan/成员历史/全方案 K；非原云台不得访问；查询无恢复动作。

### M4-A08 · 查询方案累计进度

`GET /api/v1/care-plans/{planId}/progress`

- 输入：路径 planId；云台额外提交 executionId 和当前 verificationRevision 上下文。
- 输出：200：Progress；云台不返回计划正文。
- 处理与落库：T06 取进度；APP 查 T02；云台查 T03 当前任务及 T07 固定执行/核验上下文。
- 异常/重放：云台过期/不适用核验不开放进度；查询不增加 K；离线未上传量未知。

### M4-A09 · 查看本人护理记录

`GET /api/v1/members/{memberId}/care-executions`

- 输入：路径 memberId；可选 planId、from/to、limit/cursor。
- 输出：200：items[{executionId,status,createdAt,closedAt,acceptedCount,planSnapshotSummary}]。
- 处理与落库：T02 验权后 T07 按成员及白名单筛选分页，历史内容取快照。
- 异常/重放：APP 专用；不按每行回查方案；执行结束与方案完成分别表达。

### M5-A01 · 登记本 APP 安装实例的通知投递目标

`PUT /api/v1/me/notification-destinations/{installationId}`

- 输入：路径 installationId；provider、platform=android、registration、expectedDestinationRevision（首次 "0"）。
- 输出：200：destinationId、destinationRevision、status；不回传完整推送 token。
- 处理与落库：验证当前会话与安装归属；T09 installation_id 唯一，行锁/首次插入冲突重试，变化时增代次并更新 session_ref。
- 异常/重放：不能仅凭 installationId 抢占；旧会话写入被拒绝；相同内容不增代次；首次并发依赖唯一约束。

## 6. 关键数据结构与客户端协议

### 6.1 Progress、Report、Plan 的投影

```json
{
  "targetCount": "10",
  "completedCount": "3",
  "remainingCount": "7",
  "isCompleted": false,
  "progressRevision": "2",
  "completedAt": null
}
```

Progress 仅基于 T06 已提交值。未 ready 的方案 targetCount 可以为空，此时 isCompleted 也为空，不用 0 表示“已完成”。最后同步时间从业务更新时间/明确的入账摘要取得，不伪造设备实时值。数据库 bigint 运算及接口解析都检查溢出；溢出拒绝整批，不绕回负数。

| 投影 | 可返回 | 禁止返回 |
|---|---|---|
| Report.full | reportId、memberId、报告时间、结构化指标、已验证说明、允许展示的图片描述 | 人脸特征、供应商库 ID、核验图、访问密钥 |
| Report.brief | 当前 reportId、简要结论、当前报告允许展示的结果图 | 全成员历史、APP 账号信息、内部身份候选 |
| Plan.full | planId、来源报告、说明、步骤、微晶参数、N、Progress | 供应商原始响应/提示词、内部凭据 |
| Plan.execution | planId、执行必需步骤/区域/参数、N 与当前允许进度 | 历史列表、与本次执行无关的成员资料 |
| Execution.reconcile | 原 executionId、状态、接收次数、记录确认标识/缺口、关闭时间 | 已撤销授权下的成员资料、完整方案和跨执行 K |

指标名称、区域枚举、微晶参数单位及范围必须来自测肤/微晶协议契约。它们尚未确定，不能由大模型自由发明，也不能在此文档编造治疗参数。输出校验使用已批准白名单，不是任意 JSON 透传。

### 6.2 采集与核验关联

capture 建议字段：captureId、capturedAt、clientContinuityId、purpose、采集证明引用。purpose 仅允许 grant / admission / revalidation；云台三视角则为 assessment。后端派生 actor、task/plan/execution 上下文并与证据绑定。

Verification 返回 verificationRevision、captureId、clientContinuityId、verifiedAt、validUntil、applicablePurpose，以及 replayed 标志。validUntil 是当前响应可用于端侧首次启动/恢复的时间边界，不代表时间未到就能无视换人；端侧连续性失效立即作废。后端无法保证摄像头和设备之间未再次换人，客户端必须重检。

服务端可验证的活体/采集凭据尚待所选 SDK/设备协议提供。capturedAt、captureId 和图片哈希由客户端提交，不单独证明新鲜性。没有验证器时测试环境只允许明确的替身数据；真实身份准入不以这些普通字段假装完成防重放。

阿里云 CompareFace 由服务端用当前照片和可信成员参考照进行比对；客户端不能选择参考照。参考照可沿用 T11 中已合法归档的图片，由 members.identity_summary 引用并按用途保留；不可因临时上传清理删除有效参考照。若将来引入独立 face_reference purpose，先修改主数据架构枚举。

### 6.3 实际记录与观察分开

MVP 建议每个执行固定一个记录流 epoch，值由后端以 executionId 派生并返回；记录 sourceSeq 从 1 连续递增，跨重启持久保存，不因重新联网改 epoch/重置序号。所有记录为不重叠增量。客户端先持久记录再上报；微晶若仅提供累计读数，必须在客户端协议中完成可恢复的增量转换，本设计不直接接受累计读数当增量。

```json
{
  "observation": {
    "epoch": "execution-stream-id",
    "seq": "12",
    "state": "paused",
    "occurredAt": "2026-09-10T04:00:00Z",
    "verificationRevision": "1",
    "continuityValid": false
  },
  "records": [
    {
      "recordId": "stable-client-record-id",
      "sourceEpoch": "execution-stream-id",
      "sourceSeq": "3",
      "countDelta": "1",
      "occurredAt": "2026-09-10T03:59:50Z"
    }
  ]
}
```

观察序号和实际记录序号是两条独立递增序列，不能混算。当前状态只接受匹配执行流且 seq 更大的观察；同 seq 同内容忽略，同 seq 异内容冲突。旧观察不改状态，但同批合法新记录仍可以入账。记录身份、计划、微晶都从 T07 派生，不用客户端填写。

客户端重装或丢失执行日志不能凭新安装标识接管旧执行，也不能随意换 epoch 抹掉缺口。此类异常留为受控恢复事项；默认保持占用，不偷偷增设超时强制释放。

### 6.4 收尾水位

M4-A06 的 finalRecordSeq 表示本执行记录流承诺范围 1..W，finalCount 表示该范围的增量总和。W=0 时要求无记录且 finalCount=0。客户端先调用 M4-A05 上报实际 stopped 观察和剩余明细，再提交收尾。

持锁事务中确认：原控制端；执行已 stopped；stopObservationSeq 对应已接收的停止观察；已知最大记录序号不超过 W；范围内记录数等于 W（序号正整数且唯一）、增量 SUM 等于 finalCount。缺口输出有上限的 missingRanges/more 标志，不能生成与巨大 W 成比例的内存数组。收尾不靠客户端一句“已同步”放行。

```json
{
  "stopObservationSeq": "15",
  "reason": "user_finished",
  "recordStreamEpoch": "execution-stream-id",
  "finalRecordSeq": "3",
  "finalCount": "3"
}
```

closure_manifest 保存 schema_version、原流、确认水位/总量、停止观察及发生时间、确认时间、差异摘要。相同原收尾请求重放不修改 manifest。关闭后范围外的合法历史明细仍按原执行接收，记录差异摘要和告警，不重开执行或回滚 closed_at；K 因迟到记录继续增加。若实现方要允许多 epoch，需先扩展 manifest 为多流对账，不能直接跳过检查。

## 7. 状态机与不变量

### 7.1 测肤任务

| 当前状态 | 事件/条件 | 下一状态及原子动作 |
|---|---|---|
| 无 | 合法新任务提交 | queued；切当前指针、插分析任务 |
| queued | 当前版本工作被领取 | analyzing；只反映同一 processing_revision |
| analyzing | 质量/三视角同人不合格，可补拍 | needs_retake；写 required_views，不生成正式报告 |
| needs_retake | 当前云台补拍新版本 | queued；照片/处理代次增加，新任务入队 |
| analyzing | 身份可靠、指标和结果图均有效 | report_ready；一次提交报告、摘要、方案待办 |
| queued / analyzing | 可重试依赖失败 | 保持公开处理中，并暴露最小重试说明；T12 延后 |
| queued / analyzing | 尝试耗尽/不可恢复失败 | failed；无正式报告，不回退云台指针 |
| report_ready | 任意旧分析或补拍 | 不变；正式内容冻结 |

failed 不是 GET 重试入口；用户重新测肤使用 M3-A01 新任务。后台受控重试可以按新 processing_revision 重排非定稿任务，必须留操作依据；MVP 不新增公开重算 API。被替换的旧任务可以完成归档供已授权 APP 使用，Worker 从不修改 current_assessment_id。

### 7.2 方案

报告发布创建唯一 assessment_id 的 T06，初始 waiting_inputs。输入齐全后 generating，结果通过验证后 ready；终止失败为 failed。ready 的 N、参数、输入快照冻结；进度更新不改生成代次。

只有一种微晶不意味着可以信任任意上报参数。MVP 建议用配置中经设备团队批准的单一能力基线，加合法 T04 观察确认；T06.input_snapshot 记录选用能力标识/修订及参数范围。基线未配置或观察不满足时保持 waiting_inputs。Worker 批量扫描等待方案与必要的能力行，在应用层匹配；能力补齐自动推进，不能等客户端 GET 才推进。

一份报告只对应一个方案行。等待任务先按等待检查间隔再次安排，不把“正常缺少能力”消耗为算法调用失败。正式生成任务 dedup_key 包含 planId 和 generationRevision；重复能力上报不增加生成代次，ready 后不因观察变化重新生成。执行时校验当前微晶能力仍覆盖冻结参数，不满足则拒绝准入。

### 7.3 执行

| 当前状态 | 接受条件 | 允许变化 |
|---|---|---|
| 无 | M4-A03 最终准入成功 | admitted，建立占用，未声称硬件运行 |
| admitted | 原控制端新鲜实际观察、核验关联仍适用 | running / paused / unknown / stopped |
| running | 原控制端有序实际观察 | paused / unknown / stopped，或保持 running |
| paused | 连续性未失效且核验仍适用，或 M4-A04 已通过新核验后收到有序运行观察 | running；也可 unknown / stopped |
| unknown | 新鲜实际暂停/停止观察 | paused / stopped；不得因重新联网直接 running |
| stopped | 记录已对账且收尾成功 | closed |
| closed | 合法迟到实际明细 | 只补账，状态不变 |

M4-A04 成功仅更新核验代次与摘要，仍保持 paused，直到客户端实际观察 running。连续性失效标志写入 latest_observation；只有新核验成功才消除该轮恢复要求。running 观察不具有推翻“需要重新核验”的权力。

K ≥ N 拒绝新准入和恢复，但它本身不伪造 stopped/closed。新鲜异常 running 观察可用于记录设备实际偏差并告警，不能作为后端允许继续的依据。未知状态由客户端报告或明确的服务端观察过期策略产生，不因云台心跳离线直接冒充微晶停止。

## 8. 事务、行锁与关键 SQL

### 8.1 锁顺序与事务入口

Java 用 TransactionTemplate 包住最终短事务，外部人脸、OSS、认证网络请求在事务外。[Spring 编程式事务说明](https://docs.spring.io/spring-framework/reference/data-access/transaction/programmatic.html)

既有业务锁顺序保持云台 → 微晶 → 方案 → 执行 → 授权。本稿对其他参与表补充顺序：T13 请求行（仅本请求）→ T03 云台 → T04 微晶 → T05 测肤 → T01 成员 → T06 方案 → T07 执行 → T02 授权 → T09 目标 → T10 通知 → T11 图片 → T12 任务。同类多行按 ID 排序，只锁涉及的行。

Worker 领取/续租仅锁 T12 并立即提交，不能持 T12 再等待业务行；结果提交先业务行再 T12。先前读到的归属只用于确定锁对象，最终持锁后必须复核，不能用未锁快照跳过权限。跨表写入默认 READ COMMITTED + 行锁 + 唯一约束；允许有限重试纯事务死锁/序列化冲突，不自动重复外部调用。

授权创建并发需处理 active 部分唯一冲突；最终定位已有 active 行并锁定复核，不能让撤销与迟到授权请求交错复活。每个成功授权请求的 T13 都记录其实际返回的 grantId，即使复用已有关系。撤销针对固定 grantId，不针对“这个成员所有未来授权”。

### 8.2 新任务与新执行互斥

新测肤：锁 T03 → 查询该云台 closed_at IS NULL 的 T07 → 有未收尾则拒绝 → 插 T05 → 换指针 → 入队 → T13 成功，一次提交。

云台新执行也先锁同一 T03，并核对请求当前任务/代次。它与新测肤不会同时越过检查：先新测肤则旧任务准入失败；先执行则新测肤因未收尾拒绝。APP 在其他地方使用历史方案不通过该云台指针授权，不被云台换人删除历史进度。

### 8.3 原子占用

```sql
CREATE UNIQUE INDEX uq_execution_open_microcrystal
ON care_executions (microcrystal_id)
WHERE closed_at IS NULL;

CREATE UNIQUE INDEX uq_execution_open_gimbal
ON care_executions (controller_gimbal_id)
WHERE controller_gimbal_id IS NOT NULL AND closed_at IS NULL;
```

新执行在锁外完成当前核验，然后锁 T04、T06 等必要行，检查 ready、K<N、能力及授权/当前任务，插入 admitted 执行。即使两次初查都未占用，唯一约束仍只允许一个提交。约束冲突转换为 DEVICE_OCCUPIED，不向客户端泄露对方成员。[PostgreSQL 部分唯一索引](https://www.postgresql.org/docs/current/indexes-partial.html)

### 8.4 次数账本事务

1. 读取 T07 固定归属，认证原控制端；锁 T06，再锁 T07。业务读取权限与最小补传权限分别判断。
2. 校验批次内重复 ID/序号及摘要；批量单表读取 T08 已有 ID 和同序号记录，检查两种唯一键是否冲突。两次批量 SELECT 可接受，不逐条 SELECT。
3. 批次内完全相同的重复项折叠一次；同 ID 或同序号异内容整体拒绝。已有同内容记录记 duplicate，不再插入。
4. 批量插入真正新增记录，只有实际新增集合的 count_delta 求和为 D。D=0 时不增加 K/progress_revision。
5. 增加执行 accepted_count 和方案 completed_count，首次达标记录 completed_at；合并合法新观察；T13 成功与以上同事务提交。
6. 提交成功后才生成 acknowledgedRecords；事务失败不确认任何新增记录。

```sql
UPDATE care_plans
SET completed_count = completed_count + :delta,
    progress_revision = progress_revision + 1,
    completed_at = CASE
      WHEN completed_at IS NULL AND completed_count + :delta >= target_count
      THEN :received_at ELSE completed_at END,
    updated_at = :received_at
WHERE id = :plan_id AND generation_status = 'ready';

UPDATE care_executions
SET accepted_count = accepted_count + :delta,
    updated_at = :received_at
WHERE id = :execution_id;
```

仅当 D>0 执行上述汇总 SQL，期望各更新一行，否则整体回滚。closed 执行也可以执行计数 UPDATE，但不更新 status/closed_at。ON CONFLICT DO NOTHING 不能替代内容一致性检查；更换 client_record_id 但复用源序号仍须被识别。

### 8.5 单表收尾核对

锁方案/执行后对固定 epoch 使用：

```sql
SELECT COUNT(*) AS record_count,
       COALESCE(MAX(source_seq), 0) AS max_seq,
       COALESCE(SUM(count_delta), 0) AS total_count
FROM care_records
WHERE execution_id = :execution_id AND source_epoch = :epoch;
```

结合正序号约束、双重唯一键、固定 epoch，record_count=W 且 max_seq=W 才能证明 1..W 无缺口；total_count 必须等于 finalCount。SQL 不 JOIN。检查通过后 T07.status='closed'、closed_at 和 manifest 同事务提交，不删除占用记录。纯状态 stopped 不能通过索引释放占用。

### 8.6 查询示例

```sql
SELECT id FROM member_access_grants
WHERE account_id = :account_id AND member_id = :member_id AND status = 'active';

SELECT report_id, report_ready_at, report_summary, id
FROM skin_assessments
WHERE member_id = :member_id AND status = 'report_ready'
  AND (report_ready_at, id) < (:cursor_time, :cursor_id)
ORDER BY report_ready_at DESC, id DESC
LIMIT :fetch_size;
```

第一页省略游标谓词，fetch_size=limit+1，用多取一条判断 nextCursor。详情先读归属再验权或先读轻量归属再读正文；允许多一次 SQL，不把少 JOIN 误当成少鉴权。已授权的在途读取可能已发出，撤销无法收回已下载字节；撤销后新的请求必须读新权限。

## 9. PostgreSQL 队列与 Python Worker

### 9.1 工作项契约

| job_type | owner / input_revision | dedup_key | 结果事务 |
|---|---|---|---|
| assessment.analyze | assessment / processing_revision | assessment:{id}:{revision} | T05 当前版本结果；发布报告时 T06 待办与下一 T12 |
| identity.enroll | identity namespace 协调项；输入含候选任务版本 | 稳定登记请求键 | 登记对账阶段/人员引用，最终 T01/T05；不授予 T02 |
| plan.generate | plan / generation_revision | plan:{id}:{revision} | 只写 T06 生成字段/N，不写 K |
| notification.deliver | notification / 对应投递版本 | notification:{id} | T10 投递结果 |
| media.cleanup | media / 清理代次 | media:{id}:cleanup:{revision} | T11 删除状态与补偿结果 |

identity.enroll 是为跨系统注册对账细化的内部工作类型，复用 T12，不新增公开 API。内部 payload 示例：

```json
{
  "schema_version": 1,
  "correlation_id": "logical-request-uuid",
  "assessment_id": "assessment-uuid",
  "photo_version": "2",
  "processing_revision": "2",
  "images": {"front": "media-uuid-1", "left": "media-uuid-2", "right": "media-uuid-3"},
  "provider_config_revision": "1"
}
```

job_type/owner/input_revision 是列，payload 不再持有另一套权威租约状态。两端解析同一 JSON Schema 和示例；未知版本标 failed/UNSUPPORTED_CONTRACT，并隔离告警。队列不传照片、pickle、Java 对象、签名 URL、运行凭据。

### 9.2 领取、续租和过期结果

```sql
SELECT id FROM async_jobs
WHERE status = 'queued' AND available_at <= CURRENT_TIMESTAMP
ORDER BY available_at, id
LIMIT :batch_size
FOR UPDATE SKIP LOCKED;
```

随后同一事务按返回 ID 更新 running、lease_owner、lease_until、lease_revision+1、attempt_count+1；提交后调用外部服务。领取查询适用于队列，不用于普通业务“跳过被锁行”而漏读。[PostgreSQL SELECT 锁定语义](https://www.postgresql.org/docs/current/sql-select.html)

续租仅当 id、status=running、lease_owner、lease_revision 匹配且原租约未过期时更新。到期回收条件更新为 queued 并使旧领取代次失效。完成阶段：先锁相关业务行，再锁 T12，检查当前领取者/代次/租约和业务版本；不满足就回滚业务写，不发布结果。成功同事务提交结果、任务 succeeded、后继任务。清理失败结果图时也必须先验证未发布引用。

瞬时外部错误采用有限指数退避与抖动；不可靠身份/低质量不是无限重试网络错误，而是补拍或明确失败。同步请求和队列各有尝试上限。不宣称外部调用 exactly-once：允许重复计算，不允许重复正式归档。

### 9.3 人脸身份归档与新人登记

三视角先质量检查并确认同人，然后做受控范围 1:N。可靠匹配用 namespace + face_subject_ref 定位 T01；歧义不归档，未命中只成为新人候选。

新人注册需要 namespace 级持久协调：复用 T12 的 identity.enroll 工作项，建议部分唯一索引约束同一 namespace 只有一条 queued/running/failed 未决登记工作；其他候选分析任务等待后重搜。登记工作先持久记录 candidate_entity_id、原任务/版本、阶段和供应商 request ID，再锁外调用。网络超时先按同 EntityId 查询对账，不生成另一 ID 盲目重试。

供应商索引写入已可见、与当前输入/租约仍一致后，事务建立 T01 并关联 T05；如果任务输入已被补拍替换，不能把旧登记结果归给新照片。外部成功但业务取消的人员资源保留受控对账，确认无业务引用后再清理。登记结果未确认可见时，协调项保持阻塞/待对账状态，不能释放后立即登记另一份同人候选；失败状态也必须有防止跳过未决注册的持久标记。

该串行协调处理工程竞态，不证明算法能完美区分新人。供应商可见性、自动新人判定阈值、活体条件未通过 PoC，则不得开启真实自动登记。已有成员的分析不必等待新人注册队列；没有公共全库搜索入口。

### 9.4 报告发布与方案交接

算法临时结果图下载需白名单来源/大小限制，转存 OSS 并验证可用后才发布。锁 T05 检查照片/处理代次，固定 member_id/report_id/report_payload/report_summary/report_photo_version；插唯一 T06 waiting_inputs；插后继工作项；标分析任务成功，一次 PG 提交。

测肤与计划分别可失败。报告发布后立即查询，不等待方案；方案生成输入是冻结报告与批准能力快照。大模型输出严格结构校验：方案成员/来源由服务端赋值，N 是正整数，参数和单位均在批准范围；无效结果不发布 ready。重试不更新已 ready 的方案，不重置 K/completed_at/progress_revision。

### 9.5 离线和通知

扫描 T03 的过期 last_seen_at 候选，逐行短事务重检，创建一次离线 episode 并维护 active_incidents。新心跳恢复关闭 episode；同一异常重复心跳不创建新 episode。设备首次从未心跳的 unknown 不直接解释为“刚离线”。

绑定/目标有效且异常仍在时，以 T10 复合唯一键创建每目标通知及 T12。无目标时不记 submitted；后续新目标登记或定期扫描仍可为当前异常补建通知。异常未恢复但改绑 B 时新建 B 的通知，旧 A 通知取消，不改收件人复用旧行。

投递前先在锁外向会话提供方核实会话有效性；查询失败不投递。随后短事务按 T03 → T09 → T10 → T12 重检账号、binding_revision、destination_revision、session_ref 及 episode，确认仍与刚核实的会话相同；标 sending 后在锁外发送。拿到可信受理 ID 才记 submitted，只有可信送达回执才记 delivered。发送后崩溃的 unknown 优先查供应商回执，不无条件重发。

检查后到外部发送之间仍存在解绑竞争，不能用长事务锁包住推送网络调用来掩盖。消息仅写“云台状态异常，请查看”，不含成员、照片或报告；已经受理的通知不承诺撤回。

## 10. 图片存储、访问与补偿

### 10.1 上传流程

先在 T13 建立稳定请求，再插 T11.pending（尚未创建的任务/执行外键为空）；流式写 OSS，校验格式、尺寸、大小和内容摘要，再将 T11 标 available。最终业务事务只接纳当前请求对应、purpose 正确且 available 的图片，补齐归属。图片 available 不等于对用户可访问。

补拍时新版本完整视角清单由服务端构造；跨请求复用仅允许同任务已接纳图片，不接受任意 mediaId 或任意 URL。M1/M4 核验入口本版采用当前上传，不开放客户任选历史对象再当作新采集。

对象 key 建议 `environment/purpose/random-media-id`，不含姓名、手机号、成员可读名称。Web/Worker 使用最小权限运行凭据；PG 不存图片二进制，日志不输出对象访问凭据。连接中断或超限时终止上传并回收临时文件。

### 10.2 图片读取基础 HTTP

建议补充 `GET /api/v1/media/{mediaId}/content`，属于二进制基础协议，不占用现有 M1—M5 编号。业务响应返回同源 contentUrl，不直接返回永久 OSS URL。

1. 认证主体；T11 读取对象状态、用途和归属。
2. 只允许业务报告投影公开的展示图片；检查 T05 冻结报告中确实引用该 mediaId。核验图、临时未归档图不可凭上传者身份直接下载。
3. APP 查 T02 有效关系；云台查 T03 当前任务。通过后流式读取私有 OSS。
4. 返回实际图片 MIME、no-store、X-Content-Type-Options: nosniff；不重定向至长效签名地址。本版可不支持 Range，请求不因此绕过鉴权。
5. OSS 不存在返回受控错误并告警，不把缺图当报告全文不存在，也不返回内部 bucket/key。

需要 3～4 次单表 SELECT 属于预期；图片访问另计，不承诺两次查询。鉴权发生在读取时，已经下载的字节无法远程收回。外部算法使用 SDK 内容或受限临时 URL；受限 URL 不提供给客户端，供应商输出 URL 不能成为任意内网抓取入口。

### 10.3 生命周期

| 阶段 | 允许操作 | 失败补偿 |
|---|---|---|
| pending | 上传中，无业务读权限 | 超时后核对请求与 OSS，再标失败/清理 |
| available 未被接纳 | 等待业务最终提交 | 清理前锁请求/业务及媒体、确认无有效处理者或引用 |
| available 已被引用 | 业务按用途受控读 | 不按 created_at 粗暴清理；报告和人脸参考依赖必须核查 |
| deleting | 业务禁止新增引用，按既定保留/删除决策执行 | OSS 删除失败保留状态重试 |
| deleted | 对象已确认删除，保留必要审计引用 | 读取不再返回，不能恢复旧签名访问 |

清理与业务接纳遵循相同锁顺序：不能先锁 T11 再等 T13/T05/T07。元数据检查需覆盖 T05.photo_versions/report_payload、T01.identity_summary、T07/T13 的有效证据引用；MVP 只自动清理明确无引用的失败上传。正式图片和人脸模板的删除由第 14 节生命周期方案驱动，不用定时 TTL 代替业务与合规判断。

## 11. 数据库约束、索引与迁移安排

此节是迁移设计清单，不是已运行 SQL。列定义沿用数据架构，不生成另一套同名字段字典。建议用 NOT NULL、CHECK、外键、唯一约束和事务一起保证不变量。

| 表 | 关键约束/索引 | 本稿细化 |
|---|---|---|
| T14 accounts | UNIQUE(login_provider,login_subject)；status/auth_revision | 同手机号认证主体并发只生成一个本地账号；不把手机号当可随意更新 profile |
| T01 members | UNIQUE(identity_namespace,face_subject_ref)；建档任务外键 | identity_summary 记录 schema_version、参考媒体引用、策略/模型版本；不向客户端暴露 |
| T02 member_access_grants | active(account_id,member_id) 部分唯一；source_request_id 唯一；账号状态分页索引 | status/revoked_at 配套；每次重新授权新行 |
| T03 gimbals | serial_no 唯一；bound_account_id；(connection_status,last_seen_at) | 当前指针组合外键；binding/current_assessment/status revision 非负且单调 |
| T04 microcrystals | serial_no 唯一 | capabilities JSONB 内 schema_version、能力 revision、批准参数；不新增占用列 |
| T05 skin_assessments | report_id、source_request_id 唯一；(gimbal_id,id) 唯一；成员报告游标索引 | report_ready 要求成员/报告/版本/载荷齐全；current_photo_version>0 |
| T06 care_plans | assessment_id 唯一；成员游标索引 | ready 时 N>0 且 payload 非空；K≥0；输入归属与报告一致 |
| T07 care_executions | 微晶/云台未收尾部分唯一；source_request_id 唯一；成员/方案游标索引 | APP/云台控制字段互斥；closed 与 closed_at 一致；accepted_count≥0 |
| T08 care_records | UNIQUE(execution_id,client_record_id)；UNIQUE(execution_id,source_epoch,source_seq) | count_delta>0、source_seq>0；固定归属来自执行；保留去重事实 |
| T09 notification_destinations | installation_id 唯一；(account_id,status) | active 必须有 account/session/registration；更新需验证安装归属及代次 |
| T10 notifications | (gimbal_id,incident_id,binding_revision,destination_id,destination_revision) 唯一 | 不同 episode 或路由新建记录；payload 仅最小通知 |
| T11 media_objects | (bucket,object_key) 唯一；task/version、execution、request、state/time 索引 | purpose 校验阶段性关联；pending 可无业务归属，available 仍需业务接纳 |
| T12 async_jobs | dedup_key 唯一；(status,available_at,id)、(status,lease_until) | 登记协调额外部分唯一，见下文；字段级更新，payload 有 schema_version |
| T13 idempotency_requests | (principal_type,principal_id,operation,idempotency_key) 唯一 | 不将最小去重键随照片一起 TTL 删除；租约/代次用于最终提交检查 |

登记协调建议：配置给单一 identity_namespace 一个稳定 UUID 作为 T12.owner_id；对 job_type='identity.enroll' 且 status IN ('queued','running','failed') 的 owner_id 建部分唯一索引。failed 未决注册仍阻塞新的登记，只有外部对账完成/安全取消后才进入 succeeded/cancelled 释放位置。这样无需额外锁表，但需要人工受控恢复未决注册；不是失败后自动丢弃并继续注册。

JSON 新键都属于已有宽表细化，非新增普通列。此登记协调索引、固定记录流与 JSON 结构是本文建议，实施迁移前需要同步主数据架构。云服务路线仍是 14 业务表；采用自建人脸服务时，其独立算法表不计作“无需新增任何表”。自建会话同理。

迁移顺序：先 accounts、gimbals、microcrystals、T13 等基础对象；建立 members/assessments 及其他依赖表时暂后置循环外键；所有表存在后补组合外键与索引。外键默认限制删除；不能靠 CASCADE 隐式删除报告和账本。Flyway 为唯一执行入口，Python 不另跑一套迁移。生产脚本须真实 PG 验证，不把本节示例直接作为已审迁移。

## 12. 配置、日志和运行恢复

### 12.1 建议开发初值

以下仅为联调起点，不是已测容量或产品承诺。涉及供应商限制和设备实时性时，以实际验证结果修订；关键配置纳入部署版本。

| 配置 | 开发建议值 | 注意 |
|---|---|---|
| 列表 limit | 默认 20，最大 100 | 列表不强制 COUNT 总数 |
| 记录批次 | 最大 200 条 | 同批冲突整体回滚；客户端可拆批重传 |
| 图片大小 | 单图 10 MiB；三图请求 32 MiB | Web/Nginx 一致；还应限制像素数，供应商要求更小时收紧 |
| 同步核验预算 | 连接 3 秒，整体 15 秒 | 失败不准入；代理超时需略大于 Web 预算，上传预算另计 |
| 外部测肤/模型预算 | 分别配置，不共用同步核验预算 | 避免单个大模型请求耗尽所有任务槽 |
| Worker 领取 | 每次 5，按类型限制实际并发 | 不领取远超并发能力的任务让租约空耗 |
| 租约/续租 | 60 秒 / 每 15 秒 | 长调用期间续租，丢租约停止业务提交；DB 时间判断 |
| 临时失败重试 | 最多 5 次；5 秒起指数退避，上限 300 秒并加抖动 | 推送 unknown、新人注册未决需对账，不按普通错误盲重试 |
| PG 连接预算 | Web 10，Worker 5，另留迁移/运维连接 | 单机初值，按实际并发压测，不承诺吞吐 |
| 心跳周期/离线阈值 | 不在本稿猜定 | 要匹配云台清醒/休眠协议，不因一个心跳丢失发离线提醒 |
| 核验有效期/活体参数 | 真实身份链路必填，无安全默认值 | 经端侧与供应商验证后启用 |
| 敏感图片/模板保留 | 按用途配置，正式清理前明确 | 不用 unlimited 作为默认；无策略不开放真实用户试用 |

### 12.2 日志与权限

日志关联 httpRequestId、logicalRequestId、jobId、assessmentId、executionId、inputRevision 和 leaseRevision；业务 ID 按诊断需要受控存放，不打印照片、embedding、验证码、token、签名 URL 或完整提示词/报告。供应商错误映射内部类别，对外返回稳定业务码。

指标至少覆盖：接口延迟/SQL 次数、鉴权拒绝、去重冲突、数据库锁等待、最老队列年龄、每类重试/失败、旧版本结果丢弃、OSS 孤立对象、未收尾执行、K 对账差异、通知取消/unknown。日志不是无界保存心跳或图片的替代数据库。

### 12.3 故障处置矩阵

| 故障点 | 可见结果 | 恢复方式 |
|---|---|---|
| OSS 成功、任务事务失败 | 请求未受理，当前任务未变 | 同键重试或受控孤立对象清理 |
| 准入事务成功、响应丢失 | 原执行 admitted，占用保留 | 同键只返回原执行；端侧不盲目再次启动，先对账 |
| 记录插入后汇总失败 | 整批回滚，不确认新记录 | 客户端原记录重传 |
| 收尾成功、响应丢失 | closed 保持，占用已释放 | 原请求重放，不重复写账/改状态 |
| 人脸调用失败 | 新授权/准入失败，已有合法读取可用 | 重试或新采集，不降阈值默认放行 |
| Worker 计算后崩溃 | 已受理工作仍存在 | 租约接管，同版本幂等提交 |
| 补拍与旧结果竞争 | 新版本为准 | 丢弃旧结果/临时对象，不覆盖报告 |
| 推送受理后崩溃 | unknown | 供应商回执对账或明确保留不确定性 |
| 云台/APP 断网 | 本地按连续性策略运行，后端 K 仅含已收数据 | 补传、核验/收尾；不因重连自动运行 |
| PG/OSS 备份恢复 | 可能落后客户端及外部副作用 | 先暂停投递，核对引用/队列/记录；原端补传，保持未收尾占用 |

单机 MVP 不承诺高可用。升级前停止 Worker 领取新任务、有限等待，再由租约恢复未完成工作；Web 排空短事务。迁移先兼容扩展，再发布兼容的 Python 消费者和 Java 生产者，最后清理旧结构。回滚必须兼容数据库及队列中的旧/新 payload。

## 13. 测试映射与交付验收

本稿是测试设计，不代表已运行后端代码。现有 94 个场景继续有效；新增基础协议和合规流程需要补充场景，不能宣称仍然已被 94 条全部覆盖。

| 详细设计关注点 | 现有场景 | 必须观察的结果 |
|---|---|---|
| 完整双端链路 | SC-00-01～04、SC-07-01～03 | 报告、方案、核验和记录串到同一成员，云台不读历史 |
| 绑定与过期代次 | SC-01-01～08、SC-R-01～05 | A/B 竞争不覆盖；旧解绑不删新绑定；匿名配网不改变关系 |
| 云台认证、心跳与通知 | SC-01-09～18 | 旧心跳不覆盖新状态；无目标不伪报送达；换号取消旧路由 |
| 测肤与版本 | SC-02-01～11、SC-R-06～14 | 提交即切指针；失败不回退；补拍只提交当前版本 |
| 报告/方案权限及异步 | SC-03-01～09 | 同一数据不同投影；报告先可读；能力缺失等待、补齐自动生成 |
| 执行准入与恢复 | SC-04-01～10 | 只有一个未收尾占用；重放无新启动有效性；同人且可恢复才重验 |
| 查看授权撤销 | SC-05-01～07 | 后续全文/图片拒绝，旧授权请求不复活，原端只留最小对账 |
| 增量、乱序与达标 | SC-06-01～09 | 同 ID/同序号只入一次；K=9/10/11 边界；闭合执行迟到账不重开 |
| 停止收尾 | SC-07-04～07 | 缺口拒绝；只有确认 stopped + 完整水位才 closed |
| 任务事务与存储 | SC-C-01～05 | 任务与业务原子；过期 Worker 不能提交；私有图片范围正确 |

新增技术验证建议：

1. Java/Python 对含中文、缺省值、bigint、图片摘要的同一输入规范化结果一致；不同语义不能碰撞成同一去重对象。
2. 真实 PG 并发测试：同微晶两次准入、任务替换与云台准入、补传与收尾、授权撤销与准入、两 Worker 争抢/租约过期后旧完成。
3. 记录流 W=0、存在中间缺口、同序号换 ID、最终总量不符、关闭后范围外合法补传；不得因批次部分处理提前 ACK。
4. 注册云端成功而 PG 未提交、登记超时且不可见、旧任务补拍后返回人员引用；未决注册不得放开第二次盲登记。
5. 同安装实例换号后旧会话重新登记目标、退出补偿迟到；新目标不能被旧退出动作清除。
6. 网络超时、数据库提交前后进程退出、对象删除失败、备份恢复；分别核对资源、记录和通知副作用。
7. SQL 审查没有 JOIN、隐式 ORM 关联和逐行查询；列表 SQL 数不随同页数量线性增长。
8. 新人/老成员、跨设备、多人、低质量、活体与采集重放 PoC；不以单元测试替代真实设备效果验证。

分层测试：Java 服务单测测试分支/错误映射；Python Handler 单测测试供应商结果校验；真实 PG 集成测试锁/约束/恢复；跨语言契约测试 JSON；APP/云台联调验证持久记录和本地动作。没有业务数据库或客户端实现时不声称以上测试通过。

## 14. 人脸合规对详细设计的影响

本节承接刚完成的合规讨论，记录必须补齐的设计边界，不代替专项法律评估，也不把尚未批准的产品流程写成已确认决定。

| 补充项 | 对当前实现的影响 | 真实用户试用前产出 |
|---|---|---|
| 同意与必要性 | 拍照测肤、身份登记、联网传输、账号查看关联须清楚说明；绑定账号不能替其他成年人同意 | 交互文案、适用主体、处理目的和可核查的同意证据协议 |
| 非刷脸替代方式 | 不能在存在同等可行方式时强制只有人脸；手机号登录本身不证明护理当前人 | 分开评估资料查看与护理身份校验的替代流程 |
| 撤回与删除 | M1-A03 只撤销账号查看关系，不能冒充撤回人脸处理同意 | 独立入口、身份核实、供应商模板/OSS/备份处理与审计设计 |
| 保存期限 | 报告用图、参考照、临时核验照、特征和审计证据分别管理 | 用途期限、删除/限制处理规则、错误恢复策略 |
| 供应商与自建 | 云服务协议/受托处理职责；InsightFace 实际权重许可 | 对应具体产品合同与模型许可核查 |
| 评估与安全 | 处理前影响评估、访问控制、加密与审计等 | 评估记录、测试证据、运营负责人与异常处理安排 |

来源：[现行人脸识别技术应用安全管理办法](https://www.cac.gov.cn/2025-03/21/c_1744174262156096.htm)、[网信办官方解读](https://www.cac.gov.cn/2025-03/21/c_1744259774719484.htm)、[个人信息保护法](https://www.miit.gov.cn/jgsj/zfs/fl/art/2022/art_515a4b20c12f430eab54bb4f56d89f56.html)。详细适用与供应商责任需按实际业务确认。

本文 API 中 consentEvidenceRef 是后端应验证的证据引用契约，不是客户端传 consent=true 就放行。现有 14 表没有完整的人脸同意/撤回/删除生命周期模型；T13 最小请求留痕也不能独自替代它。具体存储和新增基础 API 要在产品/合规方案确定后同步数据架构，不偷塞进 profile 伪装已解决。

在该范围确定前，可以使用合成数据/明确授权的受控测试数据开发，并以验证器替身进行接口测试；不能将带有未落实同意/活体/删除流程的版本当成真实用户可上线版本。人脸查询与测肤/大模型输入分开，向模型提供最少必要摘要，不默认发送手机号和人脸原图。

## 15. 差异清单与实施顺序

### 15.1 本稿相对架构的细化

| 内容 | 性质 | 后续同步位置 |
|---|---|---|
| HTTP 字段、状态码、multipart、bigint 字符串、游标 | 契约草案 | API 主文档及后续 OpenAPI |
| 固定执行记录流、双唯一键、收尾 W/Count | 把原“清单/水位”落到一种 MVP 协议 | 数据架构 T07/T08、APP/云台协议与测试 |
| T12 人脸登记协调及未决阻塞 | 处理跨系统新人注册竞态的实施建议 | 数据架构 T12、供应商 PoC 与任务契约 |
| 图片鉴权代理路径 | 原未定义下载协议的补充建议 | HTTP 基础协议，不重编号 27 个业务入口 |
| 手机号认证/退出及会话提供方边界 | 必要基础协议建议，提供方未选定 | 认证设计；若自建会话则先评审新增存储 |
| 人脸同意/替代/撤回/删除 | 上轮合规讨论发现的产品与数据缺口 | 单独设计后合入主文档，不假装本稿已解决 |

### 15.2 落地顺序

1. 先评审本稿业务状态与字段；同步 API/数据主文档，输出机器可验证的 OpenAPI 与任务 JSON Schema。认证、配对、采集证明和微晶参数协议由对应团队补齐。
2. 在本项目 contest2026_483_yuanxinshixisheng/backend 的合法开发分支实现基础设施和 14 表迁移，旧停维护后端不修改。完成真实 PG 的约束/锁/幂等测试。
3. 优先实现 M4 账本、准入与收尾以及 M2/M3 互斥，使用替身人脸/测肤结果完成双端核心流程。
4. 接入 OSS、Python 队列、测肤/方案/通知；用故障注入验证跨进程恢复和结果版本隔离。
5. 实际供应商/端侧 PoC，完成身份、会话、能力参数及合规补充；确认配置值、备份恢复目标和测试数据范围。
6. 完成联调与验收后，按用户指定环境部署业务系统。文档站发布不代表该步骤已执行。

本次只交付详细设计 Markdown，没有创建后端代码、数据库或修改运行中的文档网站。后续需要网站展示时再从本稿导入，避免把文档站更新与业务部署混为一谈。


## 16. 2026-09-15 接口联调增量

实现基线、状态标签、完整流程和缺口以 [接口联调与集成状态](接口联调与集成状态-2026-09-15.md) 为准。当前对外 OpenAPI 为 36 个操作，稳定编号由 29 个 M1—M5 操作与 7 个 B0 基础/联调操作组成。

### 16.1 M2-A09 云台 AI 文本问答

仅接受 GIMBAL Bearer 和严格 `{"text":"..."}`。控制器在返回 200 前完成主体、请求和下游预流检查；成功后逐事件转发经白名单重编码的 `response.accepted/response.delta/response.completed/response.failed`。下游是 llm-rag `/internal/v1/ai/responses:stream`。客户端断开关闭下游；无 `Last-Event-ID`、本地历史、`continuation_state` 或重放。真实下游流已联调，目标 dev + 真实云台 Bearer 的完整 E2E 待完成。

### 16.2 M3-A07 报告播报流

只允许该任务所属云台，且任务仍为当前任务、`report_id` 已就绪。预流失败返回统一 JSON 错误；成功流固定为 `start(seq=1) → text_delta(seq=2) → text_delta(seq=3) → done(seq=4)`。当前正文由固定四区域 mock JSON 生成，只供非生产联调。无持久化、断点续传、重放或取消 API。

停止播报由设备关闭连接并清空 TTS 队列；已受理分析继续。重连会从头生成同一 mock 流，设备必须依据本地已播放水位避免自动重复朗读。

### 16.3 报告到方案

Worker 读取已冻结的报告 JSON 和处理代次，调用 llm-rag AI 方案 provider，严格映射并校验参数、N、成员归属和代次，再写 `care_plans`。当前 adapter/service 属“已实现/待完整 E2E”，且上游报告仍来自测肤 double；不得将其表述为真实测肤到方案全链路已经上线。
