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

## Round 2 @ bd8e30557cc352761b0bbb38201fc799f572d0c9 — 基础设施失败×3（BLOCKED 留档）→ 用户授权后正式执行 → **FAIL**

### R2 调用史（如实记录）
- 尝试 1（2026-09-11，resume ora-1）：失败 `Provided authentication token is expired`，零审查内容。
- 尝试 2（2026-09-11，resume ora-1）：同一错误，零审查内容。
- 尝试 3（2026-09-11，全新会话 ora-2 诊断性单次尝试）：同一错误。结论：oracle 通道全局凭据过期（同窗口 orchestrator/fixer 正常）；按门禁纪律记录 **BLOCKED**、不循环重试（此状态已随 fe6a2e7 报告提交留档；监督者核实真实错误为 401 token_expired）。
- **尝试 4（2026-09-11，用户在 C 任务直接授权的单次正式调用）**：原配置/原模型、复用 ora-1 原会话；授权范围=读取本项目 C 包源码与相关设计执行最终复审，不含密码/密钥/真实用户数据/私人认证配置（审查请求中已明令禁止读取）。**审查正常执行，产生真实结论：FAIL。**

### R2 verdict：FAIL（“当前 bd8e305 仍不应放行”）
Oracle 实际核对：HEAD=`fe6a2e74f724b4d0969f20f930063ac7c3f4e141`（report-only）；bd8e305..HEAD 仅 C.md/C-oracle.md 两报告文件，无业务代码差异，**代码状态==bd8e305（reviewedCommit 确认）**；本轮只读、未修改文件、未执行写库/写存储测试。

**blockingFindings（3 项，均 BLOCKER）**：
1. **F3 未闭合——嵌套透传**：`CarePlanProjection.java:95-113` 白名单仅检查顶层键，对允许的 ARRAY/OBJECT 直接 `out.set(name, source.get(name))`，steps/parameters/regions 内部任意未知或敏感字段整体透传。复现：`plan_payload={"schema_version":1,"steps":[{"region":"face","provider_raw_response":"SECRET","prompt":"..."}]}` 会把 SECRET 同时返回 A02/A03 并冻结进 T07 plan_snapshot；现有测试只把敏感键放顶层故未发现。不满足 R1「未知字段不得自动公开」。建议：steps/regions/parameters 递归结构化白名单，协议未冻结的嵌套字段省略或拒绝，补嵌套 SECRET/prompt/vendor_debug 的 A02/A03/A09 及快照负向测试。
2. **能力校验 fail-open**：`CareCapabilityChecker.java:58-121,175-193` 对缺失的 capability_id、parameter_ranges、approved_regions、n_bounds 等关键冻结约束视为「不构成要求」跳过；capability={} + 无 steps payload + 仅 supported_regions 设备能力即可 covered；unit 任一侧缺失仍通过；`CareCapabilityCheckerTest:109-115,251-255` 固化了宽松行为。与总协调裁定「须同 capability_id、单位一致、N 按 n_bounds、区域双重符合」不符。建议：冻结 capability 必需子结构逐项 fail-closed（非空 capability_id、合法 parameter_ranges/approved_regions/n_bounds），设备侧对应字段必须存在且合法，单位严格一致；steps 存在则 region/parameters 结构完整且受两侧约束；补空 capability、缺 capability_id/n_bounds/approved_regions、单边缺 unit 的准入负例。
3. **混合生产 profile 可选中人脸替身**：`MemberBindingFaceDouble.java:28-41`——Spring 允许多 profile 并存，`SPRING_PROFILES_ACTIVE=prod,dev` 时 prod 段令 app.env=production，但 `@Profile({"dev","test"})` 仍注册替身且 @Primary 覆盖 FailClosedCareFaceVerifier，`APP_C_FACE_BOUND_MEMBER` 即可产生 MATCHED；A 的 `ProductionFailClosedValidator.java:43-48` 不检查 CareFaceVerifier、不识别 care 包替身，生产启动校验无第二道防线。建议：替身条件明确排除 prod/production + app.env=production 启动校验拒绝选中替身；补 prod,dev 混合 profile+设置环境绑定时必须启动失败或仍选中 fail-closed verifier 的上下文测试。

**R1 闭合状态表（R2 核定）**：F1 CLOSED（CareAuthorization.java:70-83；CareAdmissionService.java:324-353,520-545；CareLedgerService.java:178-181,411-427,759-765）；F2 CLOSED（CareQueryService.java:177-207）；**F3 NOT-CLOSED**（CarePlanProjection.java:95-113 仅顶层）；F4 CLOSED（CareLedgerService.java:642-663）；F5 CLOSED（CareLedgerService.java:585-620 无 W+1）；F6 CLOSED（CareLedgerDtos.java:45-47,60-69；CareAdmissionService.java:362-366）；N1 CLOSED（CareLedgerService.java:331-337；CareExecutionRepository.java:176-195）。

**R2 notes（非阻塞，要点）**：A03/A04 目标成员均来自服务端持久化行，无客户端 memberId 路径；MISMATCH/未绑定发生在 T07 事务前且测试断言强度足够（T07 未创建/T13 状态/目标 memberId/revision 不变）；A03 能力检查锁外+锁内同一 checker 无绕过分支（问题在 checker 自身 fail-open）；F1 幂等语义自洽（succeeded 保持+投影动态复核资格）；A05 事务后资格复核符合「提交确认与读取资格分离」，撤销在鉴权后属设计已承认的在途竞态；T07 快照顶层整数 schema_version 与 CHECK 兼容；late_variance 与 CHECK 兼容且同事务；存储隔离成立（C 路径存在+A 路径不存在实证，A 文件零改动）；missingRanges MAX 边界闭合；插入机制/防御性分支/生产限制披露准确；接受 SHA 绑定 255/255 证据并读到最终 SHA 活体日志 LIVE_SMOKE_ALL_PASS；**现有绿测未覆盖三个阻塞反例**。

**各维度结论（R2 一览）**：API/契约——9 路由与主要 DTO 对齐，F3 与能力裁定仍阻塞；查询投影——权限/统一 404/最小视图已修，嵌套白名单仍可能泄露；准入——锁外核验/锁内重检/K<N/成员来源正确，能力 checker fail-open 阻塞；原子占用/账本/收尾/迟到/撤销/幂等并发——未发现回归；人脸绑定——服务端 memberId 与拒绝路径正确，混合 profile 替身阻塞；能力匹配——revision/microcrystal_id 正确非门禁、锁内外一致，必需字段缺失未 fail-closed；存储与模块边界——成立，A/迁移/契约/共享配置零改动；测试与披露——主路径覆盖充分、披露准确，缺三个阻塞反例。

### R2 处置（按授权「必要修复按原范围并复审新代码」）
fix-1 正在修复三 BLOCKER（裁定语义：①递归结构化嵌套白名单——step 仅 region/parameters，parameter 仅标量或 {value,unit}，regions 仅 string 元素，任何层级空→丢弃，顶层空→null，WARN 仅键路径；②能力逐项 fail-closed——冻结块必需 capability_id/parameter_ranges(含双侧 unit 严格相等)/approved_regions/n_bounds，新 token malformed_frozen_capability，steps 缺失/空/畸形→malformed_frozen_step，step 参数须在冻结 ranges 内且双重范围覆盖；③双防线——CareDevTestCondition（app.env≠production ∧ 无 prod/production profile ∧ 含 dev/test 才注册替身）+ CareFaceVerifierProductionGuard（production 语义下选中非 FailClosed 即启动 fail-fast），配纯单元+上下文级证据测试）。修复完成并提交后，以**新最终 SHA** 重跑 SHA 绑定套件+活体冒烟，再发起 R3 复审。

## Round 3 @ <修复后新最终 SHA> — 待执行

## 当前门禁状态

| 项 | 状态 |
|---|---|
| R1 @11b653a | FAIL（4 BLOCKER+2 IMPORTANT）— 修复于 5bad406/24cab56；R2 核定 F1/F2/F4/F5/F6/N1 CLOSED、F3 NOT-CLOSED |
| R2 @bd8e305 | **FAIL**（用户授权单次正式执行；3 BLOCKER：嵌套白名单透传、能力校验 fail-open、混合生产 profile 可选中替身） |
| R3 @修复后新 SHA | 待执行（fix-1 修复中；提交后重跑 SHA 绑定套件+活体冒烟再复审） |
| SHA 绑定自测 @bd8e305 | 255/255 绿，RC=0，树前后==bd8e305 dirty=0（R2 已采信；新 SHA 须重跑） |
| 活体冒烟 @bd8e305 | LIVE_SMOKE_ALL_PASS RC=0（R2 已读到日志；新 SHA 须重跑） |
| 交付判定 | **未通过 Oracle 门禁**——三 BLOCKER 修复并经 R3 PASS 前不得交总协调集成 |

## 残留限制（与 C.md 一致）

生产准入在真实成员绑定人脸提供方接入前恒 503 fail-closed（有意状态）；connectionProof/consentEvidenceRef 未做可信验证；能力数值域/单位与 Plan.execution 结构未冻结（防御式读取+保守白名单）；白名单键集合与 CareFaceVerifier 是否提升为公共端口待总协调/契约裁定；dev profile 下 providers.mode=disabled 时人脸替身仍激活（@Profile 限定，生产不受影响）；活体链路为替身，不代表真实供应商可用。
