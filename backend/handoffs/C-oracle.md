# C 包 Oracle 审查记录（M4 执行与记账）

模块：M4 护理管理 Java 业务（C 包，backend/web-java care 域）。审查方式：OpenCode 实际调用已安装 oracle 子代理（omo-slim oracle，只读），非自查冒充。**Oracle 会话 ID：`ses_f717e004fffeZ6Rebw1yyBq0CK`（ora-1，R1+两次 R2 尝试）、`ses_f712cb834ffeXl1i63hFo8htf6`（ora-2，全新会话 R2 诊断尝试）**。

提交链：ccee6e2（基线）→ `11b653a`（实现，R1 所审）→ `5bad406`（R1 修复）→ `24cab56`（总协调三裁定增量）→ **`bd8e30557cc352761b0bbb38201fc799f572d0c9`（最终代码 SHA，R2 对象）**。

## Round 1 @ 11b653a6e676ded635f26117dfd6947283407d50 — **FAIL**

Oracle 实际核对了 SHA 与 30 文件 +6704/−51 范围（仅 care 新包+两个 stub 文件；迁移/契约/A 基础零改动；审查期间未改文件/未跑写请求，结论为代码路径推演+本树 Surefire 报告核对）。

### blockingFindings（R1 原文要点）

- **F1（BLOCKER）`CareAdmissionService.java:317-341,504-525`、`CareLedgerService.java:741-745`**：原控制端身份被当成持续的方案读取权限。A03/A04 成功重放不重查 APP 当前授权或云台当前任务；A05 对任何原云台无条件附带跨执行 Progress。复现：APP 成功 A03→撤销授权→同键重放仍得方案执行正文+全方案 K（A03 含 memberId）；云台任务替换后重放旧 A03/A04 仍返回旧方案；对旧执行空 A05 批次可持续读旧方案 K。属权限失效后的新读取，违反最小对账边界。
- **F2（BLOCKER）`CareQueryService.java:177-201`**：A08 将 verificationRevision 数字相等等同「核验当前仍适用」，不检查连续性失效。复现：准入 revision=1→A05 上报 paused+continuityValid=false（持久化 continuity_invalidated=true）→同 executionId/revision=1 调 A08 仍 200+全方案进度。违反 DD M4-A08「过期/不适用核验不开放」与 6.2「连续性失效立即作废」。
- **F3（BLOCKER）`CareProjections.java:131-152`、`CareAdmissionService.java:240,587-596,653-659`**：白名单仅覆盖外层 DTO；plan_payload/plan_summary/execution_params 整体透传，A03 直接把完整 plan_payload 当执行投影；缺少 DD 6.1 输出边界，未区分 Plan.full 与 Plan.execution；DB JSONB CHECK 不提供字段级公开白名单。
- **F4（BLOCKER）`CareLedgerService.java:627-644`**：admitted→running 无条件通过，跳过核验关联与连续性判断。复现：新准入执行收同 epoch 新鲜 running 观察携带 verificationRevision="999"、continuityValid=false 仍置 running。违反 DD 7.3 admitted 行「核验关联仍适用」。
- **F5（IMPORTANT）`CareLedgerService.java:574-605`**：缺口算法在 W=Long.MAX_VALUE 时 `W+1` 回绕，输出负数缺口段（不会错误关闭，但破坏对账响应）。
- **F6（IMPORTANT）`CareLedgerDtos.java:45-47,64`、`CareLedgerService.java:113-115`、`CareAdmissionDtos.java:56`**：records:[null] 元素未拒→500 而非 400；A04 reportedMicrocrystalState 任意 JsonNode（数组/标量）进入成功路径；A06 reason 自加 maxLength=128 拒绝契约未禁止的长串。

### R1 notes（非阻塞）
- 收尾数学证明成立：固定 epoch 下 source_seq>0 CHECK+(execution,epoch,seq) 唯一 ⟹ COUNT=W∧MAX≤W 即恰为 1..W；W=0 空集正确。
- 账本主不变量成立（双键判重/真实新增 D/同事务/K 不截断/completed_at 首达/关闭后补账不重开）。
- **迟到差异留痕缺失**（DD 6.4）：closed 后范围外补账未留差异摘要/告警。
- SQL 无 JOIN/无隐式关联；插入为逐条 INSERT+SAVEPOINT 非批量，交付描述应准确；T07 锁串行化下现有并发测试不证明 SAVEPOINT 冲突分支被执行。
- 生产限制：人脸/存储/能力协议未接入在替身范围可接受，但须披露 connectionProof/consentEvidenceRef 未完成可信证据验证、FaceProvider 缺成员参数（未来非简单换 Bean）。
- 测试证据为本树 Surefire 报告核对（210 项 0F0E，C 73 项），非该轮独立复跑。

## R1→修复映射

| 发现 | 修复提交 | 内容 |
|---|---|---|
| F1 | 5bad406 | hasPlanReadEligibility（APP→T02 active；GIMBAL→T03 指针==plan.assessment_id）；A03/A04 重放加资格复核→无资格统一 404（T13 保持 succeeded）；A05 progress 改资格判定（fresh+replay），无资格 progress=null 最小确认仍 200；负向测试（撤销后重放 404、换指针后重放 404、云台 A05 progress=null） |
| F2 | 5bad406 | A08 云台路径新增生命周期门（仅 admitted/running/paused）+continuityInvalidated 复核→统一 404；A04 清除后恢复开放；IT 全状态覆盖 |
| F3 | 5bad406 | 新 CarePlanProjection 显式字段级白名单（FULL/EXECUTION/SUMMARY 三集合、类型校验、未知键丢弃仅 WARN 键名、空→null、schema_version 不外发），应用 A01/A02/A09/A03 fresh+快照冻结；白名单为 C 保守提案待契约批准（javadoc+C.md 协调请求）；SECRET 键防泄漏 IT |
| F4 | 5bad406 | stateMachineStatus 所有 →running 统一门控（admitted/paused 需 !invalidated && continuityValid!=false && revision 匹配；unknown 禁止）；admitted 门控三态 IT |
| F5 | 5bad406 | missingRanges 重构：尾段以 finalRecordSeq 收口、MAX 短路，绝无 W+1；W=MAX 空流/稀疏流 IT |
| F6 | 5bad406 | records 元素 @NotNull；reportedMicrocrystalState 非对象→400；reason 去 @Size；边界 IT（null 元素 400、数组/标量 400、300 字符 reason 非 400） |
| N1（note 留痕） | 5bad406 | applyLateVariance：closed 执行迟到插入同事务 jsonb_set 累计 late_variance{late_records_count,late_max_source_seq,last_late_received_at}+log.warn 有界；IT 覆盖累计与 manifest 其余字段不变 |
| note（生产限制/绑定门禁） | 24cab56+bd8e305 | 总协调裁定升级处理：CareFaceVerifier 成员绑定端口+FailClosedCareFaceVerifier 生产恒拒+MemberBindingFaceDouble（dev/test，异成员 MISMATCH 证据）+bd8e305 环境绑定（APP_C_FACE_BOUND_MEMBER，未配置 fail-closed、非法 fail-fast）；connectionProof/consentEvidenceRef 限制已披露于 C.md |
| note（能力规则） | 24cab56 | 虚构 required_capability_revision 删除；CareCapabilityChecker 对齐 D 版本化约定（capability_id/单位/范围双重覆盖/approved_regions/n_bounds/steps 参数双重覆盖；revision 仅追溯、microcrystal_id 不绑定；缺块 fail closed）；18 项纯单元+IT 负例 |
| note（插入机制描述） | C.md | 已改为「逐条 INSERT+SAVEPOINT；T07 锁串行化下竞态分支为防御性」 |
| note（测试存储隔离，监督者） | 24cab56 | AbstractCareIT @TestPropertySource 注入本树 target/c-test-storage+bucket mvp-c-test；隔离证据测试；A 文件零改动 |

## Round 2 @ bd8e30557cc352761b0bbb38201fc799f572d0c9 — **BLOCKED（基础设施故障，不计为通过）**

- 尝试 1（2026-09-11，resume ora-1）：调用失败，错误 `Provided authentication token is expired`，未产生任何审查内容。
- 尝试 2（2026-09-11，resume ora-1）：同一基础设施认证错误，未产生任何审查内容。
- 尝试 3（2026-09-11，**全新会话 ora-2 诊断性单次尝试**，以排除会话级认证变量）：同一错误 `Provided authentication token is expired`。结论：**oracle 子代理所用模型提供方的全局认证凭据过期**（同窗口内 orchestrator 与 fixer 子代理调用正常，故障为 oracle 通道特有），非会话级问题，代码侧无可修复动作；不更换模型/提供方（任务纪律），不循环重试。
- 处置：按 COMMON.md 门禁「Oracle 不可用、调用失败或没有结论时记录 blocked；有阻塞问题时不通过」与 A 包 R12 先例（两次调用失败→BLOCKED 不视为通过→不循环重试→恢复确认后单次正式调用），**R2 记录为 BLOCKED，C 包不得视为已通过 Oracle 门禁，不得交付集成**。已向总协调/用户请求恢复 oracle 提供方凭据；恢复确认后以同一审查请求做单次正式重发（全新会话，携带 R1 完整上下文）。
- R2 审查请求已备好（逐项 F1-F6+N1 闭合核验、人脸绑定门禁重点、能力匹配对齐裁定、新缺陷排查、SHA 绑定 255/255 证据与活体冒烟 @bd8e305）；恢复后以同一请求单次正式重发（建议全新 oracle 会话以排除会话级认证变量，并携带 R1 完整上下文）。
- 若复审前代码再变更，reviewedCommit 必须更新为新最终 SHA 并重跑 SHA 绑定套件。

## 当前门禁状态

| 项 | 状态 |
|---|---|
| R1 @11b653a | FAIL（4 BLOCKER+2 IMPORTANT）— 已修复于 5bad406/24cab56 |
| R2 @bd8e305 | **BLOCKED**（oracle 基础设施认证失败 ×3：ora-1 resume ×2 + ora-2 全新会话 ×1，均 `Provided authentication token is expired`，无结论；不计为通过；待凭据恢复后单次正式复审） |
| SHA 绑定自测 @bd8e305 | 255/255 绿，RC=0，树前后==bd8e305 dirty=0（orchestrator 独立执行） |
| 活体冒烟 @bd8e305 | LIVE_SMOKE_ALL_PASS RC=0（18085+真实 PG+环境绑定成员） |
| 交付判定 | **未达交付条件**——等待 oracle 恢复后 R2 单次正式复审 PASS 方可交总协调集成 |

## 残留限制（与 C.md 一致）

生产准入在真实成员绑定人脸提供方接入前恒 503 fail-closed（有意状态）；connectionProof/consentEvidenceRef 未做可信验证；能力数值域/单位与 Plan.execution 结构未冻结（防御式读取+保守白名单）；白名单键集合与 CareFaceVerifier 是否提升为公共端口待总协调/契约裁定；dev profile 下 providers.mode=disabled 时人脸替身仍激活（@Profile 限定，生产不受影响）；活体链路为替身，不代表真实供应商可用。
