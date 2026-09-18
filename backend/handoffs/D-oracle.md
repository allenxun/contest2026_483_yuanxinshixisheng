# D-oracle.md — D 包 Oracle 独立审查报告（终版）

## 最终结论

- **门禁状态：PASSED（双范围全闭合）**
- **最终代码 SHA（两轮结论共同绑定）**：`dc955c0b109fc2c2693e980622512208e0fcdb9e`（branch `feature/mvp-assessments`，基线 `ccee6e2`）。
- **R1（M3：测肤 HTTP API + 算法/身份归档 Worker + media.cleanup）**：`PASS`，blockingFindings=[]，"M3/R1 在 dc955c0 正式接受"（第六轮）。
- **R2（M4：方案生成 Worker + 公共 defer/complete_failure/complete_success 接口）**：`PASS-with-notes` 经终审 **CONFIRMED-FINAL** 绑定 dc955c0，blockingFindings=[]。
- 审查者：本机 OpenCode omo-slim `oracle` 子代理（只读），R1=会话 `ses_f70d6639bffeJHH4g6Z16SyzsV`（六轮同审查者），R2=会话 `ses_f70b71d45ffeJs6PNR09qcW1iw`（首审+两次重绑+终审同审查者）。每轮单次正式调用；结论仅绑定各自 SHA；纯报告提交不触发循环复审。

## 认证阻塞历史（已恢复，如实保留）

| 次序 | 会话 ID | 结果 | 最小错误文本（不含认证头/cookie） |
|---|---|---|---|
| R1 首次 | `ses_f71543c6fffek9grBzuLOe3Tyq` | error | Subagent failed: Provided authentication token is expired. |
| R2 首次 | `ses_f7153d553ffeIkwL0q5jBQDLu9` | error | Session error（同认证过期，监督侧核实） |
| R1 重试 | `ses_f715343c2ffeb8hcwbUZGfsHp6` | error | Subagent failed: Provided authentication token is expired. |
| R2 重试 | `ses_f7152f8edffenEa5UOfsFU0eG7` | error | Subagent failed: Provided authentication token is expired. |

Codex 独立核实为 401 token_expired 并报总协调；期间按门禁记录 blocked、未循环重试、未换模型/凭据；用户解除暂停并授权单次有界尝试后恢复，全部后续轮次为真实调用。

## 轮次总表

| # | 轮 | 范围 | reviewedCommit | 结论 | 关键发现 → 闭合提交 |
|---|---|---|---|---|---|
| 1 | R1-1 | M3 | `6b4f9ed` | FAIL | B1 旧租约独立提交终态业务写 / B2 needs_retake 可被并发 enroll 关联正式成员 / B3 并发归档重复正式对象 + I1 failureCode 非封闭 / I2 cleanup 引用 TOCTOU / I3 brief metrics:null 违契约 + S1 multipart 严格性 → `b2d4a79` |
| 2 | R2-1 | M4+defer | `b2d4a79` | FAIL | 冻结快照校验不完整（缺 report/model/provenance 可发布 ready；嵌套畸形→未处理异常→T06 滞留 generating）→ `c051577` |
| 3 | R1-2 | M3 | `b2d4a79` | FAIL | 原 7 项闭合确认；新 N1 对象存储不随 PG 回滚（put 入事务→无行孤儿）/ N2 终态业务写与 T12 非原子 / N3 双 WARN + S1 残差（跨形态 metadata）→ `c051577`（N2 经总协调增量授权 complete_failure business_tx） |
| 4 | R1-3 | M3 | `c051577` | FAIL | N1/N2/N3/S1 残差闭合 COMPLIANT（含公共 API 授权语义审查）；新 F1 同 provider_ref 异内容可致 T11 元数据/对象分叉（BLOCKER）+ F2 CURRENT_TIMESTAMP=事务起始时刻（SUGGESTION）→ F1 闭合于 `4ac4835` |
| 5 | R2-2 | M4+defer | `c051577` | **PASS-with-notes** | 快照 BLOCKER 闭合（完整契约校验+原子 PLAN_SNAPSHOT_INVALID 终态）；SUG①provider 零调用断言、SUG②激活前 provenance 守卫前提 |
| 6 | R1-4 | M3 | `4ac4835` | FAIL | F1 核心闭合（三发散入口全阻断）；新 G1 会话锁连接模型致默认配置池饥饿死锁（BLOCKER）→ `c5b78d8`（事务级锁+digest-first+≤1 连接纪律） |
| 7 | R2-重绑#1 | M4+defer | `4ac4835` | CONFIRMED | R2 生产文件 byte-identical（--exit-code 空）+SUG① 测试增量如实 → PASS-with-notes 沿用 |
| 8 | R1-5 | M3 | `c5b78d8` | **PASS-with-notes** | G1/F2 七项闭合全 COMPLIANT；M3 九组零回归；唯一 SUG=_COMPLETE_SUCCESS 未用墙钟守卫（交集成协调）→ 总协调 §302 L.1 授权后闭合于 `dc955c0` |
| 9 | R2-重绑#2 | M4+defer | `c5b78d8` | CONFIRMED | F2 裁定改动（三守卫+dfence 墙钟）恰授权面；其余 byte-identical；1 项 IMPORTANT：中途过期测试判别性不保证（惰性开事务）→ `dc955c0` 修正 |
| 10 | R1-6 | M3 | `dc955c0` | **PASS** | L.1 成功守卫+判别性强化+health 端口适配全 COMPLIANT；零新发现；双对抗探针阻断；**M3 正式接受** |
| 11 | R2-终审 | M4+defer | `dc955c0` | **CONFIRMED-FINAL** | complete.py delta 恰一谓词；IMPORTANT 完全闭合（INSERT-before-sleep 判别真实成立）；累计共享面恰三授权文件、四守卫全 clock_timestamp；零新发现 |

## 发现→修复→闭合明细（机制摘要）

- **B1**（旧租约终态写）：dshared/dfence.py `fenced_business_tx`（async_jobs FOR UPDATE+running/owner/revision/活租约围栏，0 行→StaleGeneration 整体回滚）接入全部 handler 独立业务写；闭合 b2d4a79，R1-2 确认。
- **B2**（needs_retake 并发关联）：`_LINK_MEMBER` 收紧（status='analyzing'+candidate 匹配+phase∈{enroll_pending,enroll_started}+rev/photo 守卫；0 行→成员保留无关联+任务成功）；闭合 b2d4a79，R1-2 确认。
- **B3→N1→F1→G1**（归档完整性演进链）：b2d4a79 advisory 锁+锁后复查（B3）→ c051577 两段协议恢复（N1：tx1 pending 提交→锁外 put→tx2 fenced promote）→ 4ac4835 digest-first+全匹配复用+异内容终态拒绝不覆盖+legacy NULL-hash 锁内认领（F1）→ c5b78d8 事务级锁+≤1 连接纪律消除池饥饿（G1，oracle 建议方案）。最终不变式：绝无对象无行/绝无同 ref 第二行或第二 key/同字节重试收敛/异字节终态拒绝原行原对象不变/T11 元数据恒等于对象字节。R1-4 确认 F1 核心、R1-5 确认 G1。
- **I1**（failureCode 封闭）：PUBLIC_FAILURE_CODES 白名单 9 码（来源=grep 实际 T05 failure_code 写入点）+未知→null（契约 nullable）；闭合 b2d4a79，R1-2 确认。
- **I2**（cleanup TOCTOU）：单围栏事务（锁 T11 FOR UPDATE→同连接全引用扫描+T13 活性→deleting；序列化论证入码）；闭合 b2d4a79，R1-2 确认。
- **I3**（brief metrics:null）：@JsonInclude(NON_NULL) 省略非 nullable 字段（契约判读：required 仅 reportId/view）；闭合 b2d4a79，R1-2 确认。
- **S1+残差**（multipart）：重复文件 part 拒绝+metadata application/json 强制（b2d4a79）；跨形态/重复 text-param metadata 拒绝（c051577）；R1-2/R1-3 确认。
- **N2**（终态原子）：总协调增量授权→complete_failure(+business_tx) 同短事务 callback 先行+围栏 UPDATE；D 终态写全部改 JobFailed(business_tx)（取消独立预提交）；入口收敛保留纵深防御（同 rev 终态→重抛持久化/有界码，failure_detail 不读）；闭合 c051577，R1-3+R2-2 双确认（公共 API 授权语义逐条核可）。
- **N3**：fence 拒绝单层 WARN（loop 权威，handler DEBUG）；闭合 c051577。
- **R2-BLOCKER**（快照校验）：_frozen_rules 完整契约校验（schema_version int/report UUID+正整数版本/model 三有界串/capability provenance/ranges 有限有序数值+非空 unit/regions 非空唯一有界/n_bounds 正有序 int），任何缺陷→fenced PLAN_SNAPSHOT_INVALID 终态（T06 failed 不滞留、provider 不调用、无未处理异常）；闭合 c051577，R2-2 确认。
- **F2→L.1**（墙钟纪律）：c051577 后裁定升级必修→_REQUEUE/_MARK_FAILED/_DEFER+dfence 改 clock_timestamp()（c5b78d8）；总协调 §302 L.1 授权→_COMPLETE_SUCCESS 同谓词（dc955c0）。最终：**四条完成守卫全部真实墙钟**，过期领取者任何路径（成功/失败/重排/等待）均不能提交业务或任务状态。R1-6/R2-终审确认。
- **R2-IMPORTANT**（判别性）：中途过期测试 callback 先业务 INSERT 确立服务端事务时间戳再 sleep——旧 CURRENT_TIMESTAMP 语义必错误提交→测试必失败，判别性真实成立；闭合 dc955c0，R2-终审"完全闭合"。
- **R1-5-SUG**（success 守卫）=L.1 授权落地，见上。
- **R2-SUG①**：畸形快照测试增 provider 零调用断言（c051577）。**R2-SUG②**：真实供应商激活前须按冻结 model provenance 选择或 mismatch fail-closed——写入 D.md 接入前提（非 MVP 阻塞，oracle 原话）。

## 公共文件累计授权面（集成核对清单，自 ccee6e2）

| 文件 | 改动 | 授权依据 |
|---|---|---|
| `runtime/complete.py` | +`complete_deferred`+`_DEFER`；`complete_failure(+business_tx)`；四守卫（_COMPLETE_SUCCESS/_REQUEUE/_MARK_FAILED/_DEFER）`lease_until >= clock_timestamp()` | 总协调 2026-09-11 defer 授权（D 唯一负责人）+N2 增量授权+§302 L.1 |
| `runtime/loop.py` | process_job defer 分发分支；except-JobFailed business_tx 透传（_finish_failure keyword-only 转发） | 同上（"必要调用接入"） |
| `handlers/__init__.py` | `HandlerResult.defer_seconds`；`JobFailed.business_tx`；D 注册 4 条目 | 同上 |

claim.py/expire.py/renew.py/__main__.py/health.py/conftest.py/system_echo **全程未动**（每轮 git diff 核验）；expire/claim 调度按裁定未扩围。A 测试文件适配 4 处（test_sanity env 隔离 / test_unsupported 注册表断言 / test_complete +4 纯增量 / test_health 端口 0 机制）——均经授权或纯增量，业务断言未降低，集成知会。`.gitignore` +`/.cortexkit/`（监督者指示的会话工具缓存条目）。

## 证据矩阵（最终 SHA dc955c0，clean 树前后绑定，orchestrator 亲跑）

- Java：`mvn -B test`（env 55437）→ **183/0/0 exit 0**（2026-09-11T08:35:50Z→08:36:06Z）。
- Python：`pytest -q` 全量**零 deselect** → **175 passed 真 exit 0**（08:36:06Z→08:36:30Z，含 health 两项）；同内容 fix-lane 175 绿（08:33:18Z→37Z）+时序集 3×12 稳定+health 在外部占 18081 下 2 passed 独立性证明。
- contracts（D 未改动，回归）：jcs 26/samples 50/responses 10/openapi → **4×exit 0**（08:36:30Z→32Z）。
- E2E 活体链（web@18087+worker --once，全替身）：r2@b2d4a79 PASS、r3@c051577 PASS（认证）、**r5@c5b78d8 PASS（认证）**、**r6@dc955c0 PASS（最终权威）**——r6 含全链 a-i+累计断言集+成功守卫活体（全 job succeeded、五周期日志 stale_generation=0）+归档完整性实测（行 hash/size/type==存储字节）+K 未动+绑定 start=end dirty=0；**r4@4ac4835 INVALIDATED**（orchestrator 侧并发干扰，执行器正确拒绝认证，如实披露，双 oracle 核可处置）；r1@dirty-6b4f9ed（内容同一性 git 证据链）。证据文件 `.mvp-d-runtime/e2e-evidence.md`（运行目录，由监督者同步）。
- 历史推进：Java 137(A 基线)→170→175→179→182→183；Python 47(A 基线)→86→93→95→107→125→137→158→161→163→171→175。

## 残留与披露（非阻塞）

1. R2-SUG②：真实供应商激活前按冻结 model provenance 选择或 mismatch fail-closed（接入前提，见 D.md）。
2. owned pending 结果图行（终态失败任务遗留）保留可追踪不清理（行存在即可发现；dmedia docstring 披露）。
3. media.cleanup 周期触发/孤儿扫描接线归总协调（D 提供幂等 discover_and_enqueue_orphans+handler）。
4. enroll 终态 failed 槽位保持占用（受控恢复=运维对账后置 cancelled/succeeded，DD 9.3）。
5. F2 历史：oracle SUGGESTION→我方接受披露→总协调裁定必修→已全落地（四守卫）；expire/claim 调度语义按裁定未扩围。
6. 跨包端口冲突（A test_health 原 18081 vs E 活体）经 L.2 授权端口 0 机制根治（K 节通报在案）。
7. 94 业务场景归 E 独立验收；媒体业务读取待 B 统一 MediaAccessPolicy（当前 A deny-all，E2E 媒体 GET 404 为预期）。
8. 生产接入限制：三提供方均替身证明链路；阿里云适配器仅边界（全方法 ProviderNotActivated，无伪造效果）；指标/能力基线为文档化占位待设备团队批准；worker 生产存储仍 FilesystemStorageDouble（A 已披露，真实 OSS 归总协调/A）。

## AI 方案增量轮（2026-09-14，第 12-13 次实调；审查者 ora-2 同会话）

| # | 轮 | 范围 | reviewedCommit | 结论 | 发现→闭合 |
|---|---|---|---|---|---|
| 12 | 最终聚焦审 | llm_rag 适配器增量 | `2338d3d` | FAIL | BLOCKER：适配器终态回调 _MARK_PLAN_FAILED_BY_ASSESSMENT 仅按 assessment_id+status，无 plan/revision 围栏→并发代次翻转可误杀新代次；IMPORTANT①raw 校验过浅（spots×v2_oiliness_tendency 竟通过）；IMPORTANT②构建期配置错→可重试→T06 可滞留。其余 COMPLIANT（fail-closed 核心/分类矩阵/恰 9 文件非回归/红线语义/卫生；探针：未批准到 ready 阻断✓ NL 阻断✓ key 泄漏阻断✓，嵌套畸形 raw=Partial bypass）→ 闭合于 `afa3372` |
| 13 | 复审 | 同上 | `afa3372` | **PASS** | 三项 CLOSED：适配器去持久化（providers 零 SQL 面）+类型化异常→plan_generate 既有 fenced _terminal 路由+_mark_plan_failed_tx 0 行→StaleGeneration（旧代次终态整体回滚，翻转测试 gen-1 零触碰）；raw 全封闭合同（逐项 score_basis/严格计数/跨字段不变式/逐视图对账，fixture 原样过+14 负例网络前终态）；配置错双解析点→立即 fenced PLAN_PROVIDER_CONFIG（T06/T12 原子、单 attempt、不滞留；aliyun_llm 不变）。偏差 COMPLIANT；先前范围 byte-identical（diff 空 exit0）；blockingFindings=[]；四探针全阻断（含前次 Partial bypass）。**afa3372=AI-plan 增量最终接受 SHA**。真实调用阻塞披露核可（启动失败=其 BGE-M3 资产缺失，只读未修；无假成功主张，外部依赖缺口不 invalidate fail-closed 审查） |

- D 包门禁累计终态：**M3=PASS@dc955c0（六轮）；M4+公共接口=PASS-with-notes CONFIRMED-FINAL@dc955c0；AI-plan 增量=PASS@afa3372；InsightFace 增量=PASS@e006e6b（四轮，取代 5e52cde）**。链：ccee6e2→6b4f9ed→b2d4a79→c051577→4ac4835→c5b78d8→dc955c0→（dev 合并 6bd31cb，B/C 各自 oracle 轮覆盖+合并后全量 590/352 绿）→2338d3d→afa3372→（AI-plan 报告/探测轮+dev 合并 8d7aabb）→7302cc1→d51dfe0→99792a5→5e52cde→e006e6b→本报告提交。

### 真实联调轮备注（2026-09-14）
- dev 0e6c633 合并后（8193cea）全量 Java 618/Python 459 绿；真实 POST 双探测完成（A=400 契约化拒绝活体证实包裹判定；B=200 完整 assessment/plan，PREVIEW_ONLY/partial）。活体 WeijingPlan 设备参数扫描命中 0 → fail-closed 维持；活体信封通过 afa3372 适配器全部封闭校验 → **零代码差异，最终 AI-plan 代码 SHA 维持 afa3372（第 13 轮 PASS/ACCEPTED），本轮无新代码提交（仅报告），按 report-only 纪律不另起 Oracle 轮**。

## InsightFace phase-2：四轮 Oracle 实际调用记录（2026-09-16/17，第四轮=NO_FACE 重拍语义修复轮）

- 审查者：oracle 子代理会话 `ses_f564d4b4bffenySjytDhUhIInb`（四轮同一会话，保有全部上下文；全程只读、未修改文件、未重跑套件、对抗探针亲跑）。候选均为真实提交 SHA，绑定检查（cat-file/rev-parse/status 含 untracked/diff --stat/diff --check/冻结面）每轮独立核验。
- **第一轮 @`d51dfe0550ee4c8ad5b44b37b2caf7aa9a9a1ed0`：FAIL**（2 BLOCKER+2 IMPORTANT+1 SUGGESTION，探针亲复现）：B1 register 畸形 2xx 伪造成功（200 `{}`、202 `{}`、201 `subject_id:null` 均→success）；B2 query 接受错误主体（`{"status":"registered","subject_id":"WRONG"}`→registered→_commit_enrollment 无真实确认建 member）；I3 quality largest_face_index 非法字符串静默修复为 0→accepted；I4 测试缺上述负例+stub 自称 contract faithful 但登记响应缺冻结形状+泄漏扫描未查链式 cause；S5 ProviderConfigError 耗重试预算（有界 fail-closed，维持现状、改 handler 需协调）。同轮 COMPLIANT：18 码表与 B errors.py 逐项一致（**INTERNAL_ERROR=(500,True) 裁定正确**——合同 §7 文字简写不推翻已提交真值）、门禁完整性（沿冻结 handler 全路径：ProviderNotActivated→reconcile→有界 PENDING→terminal 无 member 行）、liveness/传输/脱敏/冻结面/偏差 (a)(c)-(h)。
- **第二轮 @`99792a5990096423a359984659e8ee057c34b44a`：FAIL**（范围收窄）：原四探针全部闭合 fail-closed；过约束审计干净（created_at/updated_at NOT NULL、registered_at 可空正确、provider_request_id 冻结 Worker 恒提供且 find_registration 先过滤、created==(status==201) 由 api.py:742 保证；方向安全声明沿 identity_enroll:183-193 验证）；COMPLIANT 面零回归。新 BLOCKER：query 未验 HTTP 状态（TransportResult(201,合法七键体)→registered；B 路由恒 200，api.py:805-852）；新 IMPORTANT：register 错误 namespace 回显与 201/replayed=true 仍→success。
- **第三轮 @`5e52cdeb3f0c43b73a9c3e3491cda31eb71a7b0c`：PASS-with-notes**：两发现 CLOSED（query status==200 门先于体解析 :1026-1031；namespace 精确等值 :954-960；三元组 :961-970；探针逐项重做全部 fail-closed、合法 201/200 形态→success）；可达性声明独立核验成立（api.py:688+config.py:136-137 默认 conflict、store.py:472-491/519-546/493-498、api.py:742），**附带限定**：全局 FACE_SVC_REGISTER_ON_EXISTS=overwrite（config.py:176,211-214）可使 B 发 200/false/false——非合同部署配置，D 侧 unknown→对账确认、方向安全，生产须保持 conflict；过约束：冻结/默认部署无；非回归全确认（18 码表/门禁/liveness/传输/search 校验/12 键/回显等值/index 严格/脱敏链扫/stub 形状/FaceDouble/Aliyun/全部冻结面）；blockingFindings=[]；**`5e52cde` ACCEPTED 为 FINAL phase-2 increment code SHA**（截至第三轮的历史结论；其后第四轮以 `e006e6b` 取代——见下条）。SUGGESTION×2（均不重开已接受 SHA，登记在案）：①providers.py:920-923 可达性注释精度（overwrite 亦可经全局配置到达）；②+17 测试中合法正例与既有 created/status 用例对 99792a5 非判别性负例（新增 status/namespace/replay 测试真实判别）。
- 证据充分性（审查者原话要点）：绑定/范围/冻结面/diff 卫生独立核验；全部探针亲跑；B api/config/store 真值直接交叉核对；762 套件未重跑但探针覆盖被修安全边界。orchestrator 侧每候选亲跑全量（673/745/762 全 exit 0，绑定各自提交内容）。
- **第四轮 @`e006e6b989970c2bfd17475de813158e15551c5b`：PASS（零发现）**（NO_FACE 重拍语义修复轮：quality 阶段确定性图像内容 400 三码→needs_retake、瞬态支配、零 handler 改动；恰 2 文件 +181/−5）：监督者已独立读取真实 Oracle 子会话最终输出核对 reviewedCommit=e006e6b989970c2bfd17475de813158e15551c5b；绑定检查全过（cat-file/rev-parse/status 含 untracked/diff --stat/diff --check/冻结面 diff 0/无变异残留）。七焦点全 COMPLIANT：语义正确性（三码按 CODE 绑定、规范序、never-accepted）、瞬态支配健全性（沿 assessment_analyze.py:585-601 有界重试核验收敛）、scope 纪律（same_person/search_1n 零改动+_bounded_views :149-153 与 requiredViews 通道 :531-565 一致）、业务结果（QUALITY_REJECTED 补拍取代无意义重试）、测试判别力（+16；变异 10/12 对 pre-fix 必红、sha256 还原零残留）、5e52cde 已认可面零回归、合同 §8 修订案文准确。blockingFindings=[]；**全严重级零发现（本谱系最干净一轮）**；八对抗探针全阻断（内容码下 accepted 逃逸/未知视角部分 retake/鉴权与瞬态支配序/same_person 与 search 双 scope 泄漏/required_views 排序规范化 ("right","front","right")→["front","right"]/静默跳视角）；按 CODE 绑定裁定恰当（三码恒 400 由冻结码表保证、不依赖中间状态处理、auth 仍优先）。**`e006e6b` ACCEPTED 为新最终 phase-2 增量代码 SHA（取代 `5e52cde`）**。证据：orchestrator 亲跑全量 778 passed exit 0 绑定 e006e6b 内容（762+16）；审查者未重跑套件（绑定/控制流/冻结 handler 集成/修订案文+探针亲跑足以支撑接受）。
- **§8 修订边界（明确标识）**：第四轮时合同 §8 quality 行修订仍为**修订案文**（D.md 明确标识、B 冻结文件未改、Oracle 裁定案文准确但正式采纳属总协调/B 决策）；**其后 B 正式同意 D 的业务裁定、总协调 2026-09-17 确认**（同时确认 B 测后独立 SQLite 全库复核 namespaces=0/subjects=0/library_revision=0），合同文字以独立 report-only 提交更新——**合同文字 SHA 与代码审查 SHA（e006e6b）分别记录于该提交与本轮回报**。
- 第四轮为本谱系最终轮。累计：FAIL@d51dfe0（2B+2I）→FAIL@99792a5（1B+1I）→PASS-with-notes@5e52cde（历史接受）→**PASS@e006e6b（最终）**。

## V3 测肤三组增量：两轮 Oracle 实际调用记录（2026-09-17）

- 审查者：oracle 子代理会话 `ses_f564d4b4bffenySjytDhUhIInb`（与 InsightFace 四轮同一会话；全程只读、未重跑套件、对抗探针亲跑）。
- **第一轮 @`9f96f1018be8467e2be5f408e5737f760c7d8925`：PASS-with-notes**（ACCEPTED 为最终 V3 代码 SHA；blockingFindings=[]）：九焦点全 COMPLIANT——validator（恰三键集合相等/闭合白名单/0..100 或 null 拒 bool/severity 冻结词表/regions 唯一/画面左右逐字/规范化重建深拷贝）、publish 合流（:448-452 恰三键、fenced _publish 内、缺省零痕迹）、承载兼容（尾字段可选、仓内无位置构造破坏）、mock 门禁（strict bool 默认 false+注入开关注册+生产守卫拒启+mock model_version 标记不新增键+hold 优先）、语义保真（null 透传断言 ≠0、零变换、raw_detection 零触碰）、Java 投影结构性闭合+IT 判别力、contracts 无缺口、AI 差异记录精确无自转换、测试与诚实边界（零真实算法主张）。15 探针 14 阻断+1 记录。**IMPORTANT**：score=10**10000 → float() OverflowError 绕过 _ContractViolation→广义依赖分支→有界 DEPENDENCY_UNAVAILABLE（fail-closed 零发布但违例分类不穷尽）；**SUGGESTION**：SkinDouble 构造入参未防御拷贝（仅 dev/test double 面）。
- **修复轮**（e133461 前置内容）：双点位去 float() 直接任意精度比较（assessment_analyze.py:716-718/:761-763）+构造期 json 深拷贝（providers.py:398-403）+11 测试；判别证明=临时回退 float() 形态恰 3 失败复现 Oracle 缺陷（DEPENDENCY_UNAVAILABLE≠PROVIDER_CONTRACT_VIOLATION），sha256 逐字节还原、零残留标记；inf/nan 用例如实标注非判别守卫。
- **Rebind @`e13346144edee21a34d41a5f19f0f8d5a4449d61`：PASS**：**ACCEPTED 为 FINAL V3-increment code SHA（取代 9f96f10）**；两发现 CLOSED（审查者亲跑探针：10**10000/inf/-inf/nan/True/"50"/complex→_ContractViolation；None 保留为 None；构造入参变异与返回结果变异双向隔离）；四偏差逐项裁定可接受（Py3.12 4300 位 int→str 限制仅 SkinDouble 构造 mock 路径——真实/未来 provider 结果直达校验器被任意精度精确处理；label 参数化不弱化投递；in-process stub=严格 JSON 无法表示非有限值时的恰当选择；inf/nan 守卫如实披露）；零回归全确认（9f96f10 已接受面逐项列出未变，dconfig/dskin_mock 字节级未变）；blockingFindings=[]；**零新发现**。证据充分性：绑定/清洁/范围/冻结面独立核验、三文件 delta 全读、数值类/null/双向拷贝探针亲跑、832 绿 orchestrator 亲跑绑定、Java 零 delta 沿用 11/0/0/0 证据。
- D 包门禁累计终态更新：**V3 测肤三组增量=PASS@e133461（两轮，取代 9f96f10）**。

## V3 校验收紧轮：Oracle 实际调用记录（2026-09-18）

- 审查者：oracle 子代理会话 `ses_f564d4b4bffenySjytDhUhIInb`（与 V3 两轮及 InsightFace 四轮同一会话；只读、未重跑套件、探针亲跑）。
- **有界轮 @`959af5d04e57a4209e9aed60fead74cd857fcc6a`：PASS**，**ACCEPTED 为本 V3 收紧增量最终代码 SHA**。绑定全过：恰 2 文件（实际 numstat validator +24/−9、tests +84/−0，合计 +108/−9——并更正审查指令中"+33"为 diffstat 变更行数非插入数）；冻结面全空（含全部 dshared、B narration 包、face-service、contracts、handoffs、migrations）；零变异残留；无其它测试文件引用 v3_groups。六焦点全 COMPLIANT：①对齐保真（D :733-736/:737-743/:758-775 vs B Extractor :133/:151-153/:164-176/:232-243 + Scores :34-41/:51-57，双方均不 trim）；②方向安全（**跨已安装运行时实证 JavaWhitespace−PythonStrip=∅**；Python 额外剥 U+0085/U+00A0/U+2007/U+202F=仅 D 更严，NBSP D 拒 B 收）；③零松弛回归（白名单/score/null/词表/唯一/重建/发布流未触碰；dskin_mock/dconfig/providers 字节未变；mock 三组非空 regions 非空白名）；④测试判别力（恰 +16=3 空 regions+9 空白位×形态+2 终态+2 verbatim 守卫；回退收紧→14 判别用例失败、2 守卫如实非判别；终态断言 :516-538）；⑤scope 纪律（零 B 源/配置/provider/handler 流/dermavision/三视角/映射改动；仅声明定向 70 跑）；⑥引证准确性全对。blockingFindings=[]；**零发现（BLOCKER/IMPORTANT/SUGGESTION 全空）**。14 探针全阻断（含" 额 部 "首尾空白逐字节保留、null 保留≠0、巨大整数/词表/重复/未知键/all-or-none 既有拒绝全保持、mock 未改过新规、零放宽、零 dermavision delta）。定向 70 绿证据被判定与授权的两文件校验-only 变更相称（无全量声明）。
- **V3 谱系累计终态**：9f96f10 PASS-with-notes（ACCEPTED，历史）→ e133461 PASS（FINAL，历史）→ **959af5d PASS（现最终代码 SHA）**。
