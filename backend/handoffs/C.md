# C 包交付说明（护理管理 M4 · Java 业务）

状态：候选代码已提交并完成 SHA 绑定自测；Oracle 门禁 R1 FAIL@11b653a→已修复（5bad406/24cab56/bd8e305），**R2 @bd8e305 当前 BLOCKED（oracle 提供方认证过期 401 token_expired，三次调用、两个会话，均无审查结论，不计为通过；监督者已核实）**——详见 `C-oracle.md`；待认证恢复明确通知后单次正式复审，PASS 前不视为完成、不交集成。本包不合并、不推送；交总协调集成后由 E 独立验收（本文不声称已验收）。

## 提交

- 工作树 `.worktrees/mvp-c`，分支 `feature/mvp-care`，基线 `ccee6e2`（A 验收放行后的 dev 合并点）。
- 代码提交链（均未推送、未合并）：
  - `11b653a` — C 包 M4 实现（30 文件 +6704/−51：care 包 18 主类+10 测试类；stub 仅删 9 个 M4 占位）
  - `5bad406` — Oracle round-1 修复（F1-F6 + 迟到差异留痕 N1）
  - `24cab56` — 总协调三项裁定增量（人脸成员绑定 fail-closed / 测试存储本树化 / 能力匹配对齐 D 约定）
  - **`bd8e30557cc352761b0bbb38201fc799f572d0c9` — 最终代码 SHA**（dev/test 环境绑定成员补充，活体 E2E 可行性）
- A 基础设施、迁移、契约（openapi/schemas/samples/scripts）、共享 yml：**零改动**。无新表、无 Python、无 start/stop 下发。
- 报告提交（本文件与 C-oracle.md）：report-only，SHA 见 git log。

## 范围实现映射（M4-A01..A09 = C-01）

| API | 实现 | 要点 |
|---|---|---|
| M4-A01 GET members/{id}/care-plans | CareQueryController/Service | T02 验权→T06 单表 keyset 分页；reportId 过滤经 T05 两步单表；ready 才附 Progress；planSummary 白名单投影 |
| M4-A02 GET care-plans/{id}?view=full | 同上 | plan_payload 经 CarePlanProjection FULL 白名单投影（未知键丢弃）；未就绪仅公开 waitingReason（failure_detail 绝不外发）；云台 403 |
| M4-A03 POST care-executions | CareAdmissionController/Service | 锁外（媒体/人脸 1:1 成员绑定核验/预检）+ 最终短事务锁序 T03→T04→T06→INSERT T07→T02；能力覆盖按 D 约定校验；占用由两个部分唯一索引原子裁决→统一 409 DEVICE_OCCUPIED；201 admitted/重放 200 replayed（重放须当前读取资格，否则统一 404） |
| M4-A04 POST .../revalidations | 同上 | 仅原控制端；paused+代次匹配+K<N+（APP）授权/（云台）当前任务；revision+1、状态不变；continuity_invalidated 仅由 A04 清除；重放同样须当前资格 |
| M4-A05 POST .../observations | CareLedgerController/Service | 锁序 T06→T07；双键批量判重（两条单表 SELECT）；异内容整批 409 回滚；D=真实新增和；K/accepted_count/progress_revision/completed_at 同事务；观察独立序号+状态机（→running 统一门控）+stopped/closed 生命周期冻结；迟到记录 closed 后照常入账并写 late_variance 留痕；Progress 仅给当前有读取资格者 |
| M4-A06 POST .../closure-confirmations | 同上 | 停止观察核对+固定 epoch 单表 COUNT/MAX/SUM 水位对账（count==W∧max==W⟺1..W 无缺口）；缺口有界输出（≤20 段+more，无 W+1 溢出）；条件更新 WHERE status='stopped' 防双关；closed_at 释放占用；重放不重写 manifest |
| M4-A07 GET care-executions/{id} | CareQueryController/Service | 双路径授权（授权 APP 完整视图 / 原控制端最小对账视图，云台一律最小）；recordsAfterSeq 单表分页确认 ID |
| M4-A08 GET care-plans/{id}/progress | 同上 | APP 走 T02；云台必带 executionId+verificationRevision，且生命周期∈{admitted,running,paused}、连续性未失效、T03 当前任务（TASK_REPLACED）——数字代次相等≠核验适用；查询零写入 |
| M4-A09 GET members/{id}/care-executions | 同上 | T02→T07 成员分页（planId/from/to 过滤）；planSnapshotSummary 取冻结快照白名单投影，不逐行回查 T06 |

## 关键裁定语义（供 E 验收与 B/C/D 对齐；均记录于代码 javadoc）

1. **统一不可见**：资源缺失/无授权/已撤销/非归属/代次过期/连续性失效一律同一 404 RESOURCE_NOT_VISIBLE 信封（RV-5 模式）；APP-only 端点收到云台→403 CALLER_NOT_ALLOWED；C 不发 GRANT_REVOKED。
2. **原控制端 ≠ 持续读取权**（Oracle R1-F1 修复确立）：可补账/收尾（A05/A06/A07 最小视图）是原控制端永久权利；可读方案正文/Progress（A02/A03/A04 重放、A05 progress、A08）必须当前资格——APP=T02 active，云台=T03 当前任务指针；资格缺失统一 404 / progress=null。
3. **人脸 1:1 成员绑定门禁**（总协调裁定 2026-09-11）：公共 FaceProvider.classify 无成员参数，不得作准入证据。C 域端口 `CareFaceVerifier.verifyOneToOne(purpose, memberId, candidate)`，memberId 只来自服务端持久化行（plan/execution），绝无客户端输入路径。生产默认 `FailClosedCareFaceVerifier` 恒 CAPABILITY_UNAVAILABLE→503（T13 保持 processing），**真实成员绑定提供方接入前生产准入不可用是有意状态**。dev/test 替身 `MemberBindingFaceDouble`（@Profile 限定）：未绑定→CAPABILITY_UNAVAILABLE、异成员→MISMATCH（403 rejected）、一致→MATCHED；活体联调用 `APP_C_FACE_BOUND_MEMBER=<uuid>` 环境绑定（非法值 fail fast；不降低异成员拒绝）。MISMATCH/UNCERTAIN→403 FACE_NOT_VERIFIED；QUALITY_REJECTED→422；DEPENDENCY_FAILED→503。
4. **能力覆盖对齐 D 约定**（总协调裁定，§150/§151）：input_snapshot.capability={microcrystal_id,capability_id,capability_revision,parameter_ranges,approved_regions,n_bounds}。判定=设备能力非空 ∧ 冻结 capability 块存在（缺失 fail closed）∧ 同 capability_id ∧ 冻结 parameter_ranges 被设备更宽覆盖且单位一致 ∧ approved_regions ⊆ 设备 supported_regions ∧ N∈n_bounds ∧ steps[].region/parameters 同时落在冻结与设备约束内。**capability_revision 仅追溯、microcrystal_id 不绑定设备，均不参与判定**；虚构字段 required_capability_revision 已删除。不符→409 PLAN_NOT_READY details.reason=有界 token（8 种）。
5. **方案 JSONB 白名单投影**（Oracle R1-F3 修复确立）：CarePlanProjection——FULL=title/description/steps/regions/parameters；EXECUTION=steps/regions/parameters；SUMMARY=title/description/source_report_id/source_report_ready_at；类型校验、未知键丢弃（WARN 仅键名）、空→null、schema_version 不外发。**白名单为 C 侧保守提案，待总协调/D 契约批准后冻结**。
6. **记录/观察流**：每执行固定 epoch=执行 UUID 串；观察与记录两条独立递增序列；记录 sourceEpoch 不符→逐条 rejected，观察 epoch 不符→整批 409；→running 转移统一门控（连续性未失效+代次匹配）；unknown→running 禁止；stopped/closed 生命周期冻结（观察不入、记录照常+late_variance 留痕）。
7. **Verification.validUntil=null**：真实提供方未接入不伪造时效；重放 verification.replayed=true 且绝不刷新 revision/verifiedAt。
8. **幂等**：四写端点 Idempotency-Key 必携；operation=care.execution.create/care.execution.revalidate/care.observation.sync/care.closure.confirm；确定性拒绝→T13 rejected 同键重放原拒绝；瞬时失败保持 processing；A05 重放=冻结 acks+当前状态重投影。
9. **溢出**：bigint 解析/求和/汇总 addExact；溢出→400 count_overflow 整批拒绝。
10. **写边界（字段级）**：T07 全生命周期（C 独占）；T06 仅 completed_count/completed_at/progress_revision/updated_at 且 WHERE generation_status='ready'；T08 仅 INSERT；T11 仅补 execution_id/member_id；T02/T03/T04/T05/T01 只读；不写 T12。
11. **查询纪律**：全部单表显式列 SQL，无 JOIN/关联子查询/ORM 关联；批量判重两条 SELECT；记录插入为**逐条 INSERT+SAVEPOINT**（批上限 200；T07 锁串行化下唯一约束竞态分支为防御性，正常路径由锁内批量判重收敛）；keyset 分页绑定 filterDigest。

## 测试证据（最终代码 SHA bd8e305 绑定）

- **Java 全套件（SHA 绑定，orchestrator 独立执行）**：`mvn -B test`（隔离 mvp-c-pg postgres:16 @127.0.0.1:55436）→ **Tests run: 255, Failures: 0, Errors: 0, Skipped: 0，RC=0；TREE_BEFORE==TREE_AFTER==bd8e305、dirty=0（SHA_BOUND=YES）**。255=137 A 基线（不变）+118 C 项：
  - 查询 IT（CarePlanQueryIT/CareExecutionQueryIT）：三态 404 全等、云台 403、分页/游标/过滤、投影形状与 bigint 字符串、只读证明、快照冻结、撤销后最小视图、A08 生命周期/连续性门禁。
  - 准入/恢复 IT（CareAdmissionIT/CareRevalidationIT/CareAdmissionConcurrencyIT/CareFaceBindingIT）：APP/云台快乐路径、重放同执行+无新有效性+**重放资格复核（撤销/换任务后重放→404）**、异内容键冲突、确定性拒绝重放、角色/purpose 校验、TASK_REPLACED、PLAN_COMPLETED、能力约定负例（capability_id/区域/N/范围/缺块 fail-closed/revision 非门禁）、**人脸成员绑定（异成员 403 拒绝证据、未绑定 503 fail-closed、四分类映射、生产 FailClosed 单元证明、bean 装配断言）**、并发同微晶双端恰一 201、并发同云台互斥、并发 A04 同代次恰一成功、占用仅 closed 释放。
  - 账本/收尾 IT（CareLedgerIT/CareClosureIT/CareLedgerConcurrencyIT）：双键去重全分支、整批 409 回滚、K=9/10/11+completed_at 首达保持+K 不截断、插入后汇总失败整体回滚、观察状态机全转移+running 门控+冻结、迟到补账+late_variance 留痕、W=0/缺口（含 W=Long.MAX 无溢出）/总量不符/未停止/双关防护、manifest 重放逐字节不变、撤销后最小 ack+仍可收尾、并发同记录收敛、并发双收尾恰一 200。
  - 纯单元：CareCapabilityCheckerTest 18 项、MemberBindingFaceDoubleTest 4 项、CarePlanProjectionIT 白名单（含 SECRET 键防泄漏断言）。
- **契约校验**（C 未改契约，回归确认）：jcs selftest 26 PASS；validate_samples 50 PASS；validate_responses --selftest 10 PASS；openapi-spec-validator OK。
- **活体冒烟 @bd8e305**（真实 HTTP 18085 + 真实 PG mvp_c_dev + APP_C_FACE_BOUND_MEMBER 环境绑定；`target/c-live-smoke.log`、逐响应 `target/c-live-evidence/`，gitignored）：LIVE_SMOKE_ALL_PASS RC=0——登录→D 约定形状种子→A01/A02（**含白名单 SECRET 键防泄漏现场断言**）→A03 201（epoch=executionId）→A05 三记录 K=3→重传全 duplicate→stopped→A06 closed+occupancyReleased→重放 manifest 不变→A07 closed+水位 3→A08 K=3/remaining7→A09→**同微晶二次准入 201（占用释放实证）**→旧 A03 键重放 meta.replayed+verification.replayed=true→A05 paused(continuityValid=false)→A04 revision2 仍 paused→A04 重放不递增→陌生账号 A07 404。

## 运行接入方式

```bash
# 测试（隔离 PG；C 测试存储经 AbstractCareIT 属性注入本树 target/c-test-storage，
# 勿设 APP_STORAGE_DEV_DIR 环境变量——A 测试探针硬编码 /tmp/mvp-a-test-storage）
cd backend/web-java && env MVP_A_PG_JDBC=jdbc:postgresql://127.0.0.1:55436/postgres \
  MVP_A_PG_USER=postgres MVP_A_PG_PASSWORD=mvp_c_local mvn -B test

# 活体运行（dev profile；准入 E2E 需显式环境绑定目标成员，未绑定 fail-closed 503）
SERVER_PORT=18085 \
SPRING_DATASOURCE_URL=jdbc:postgresql://127.0.0.1:55436/mvp_c_dev \
SPRING_DATASOURCE_USERNAME=postgres SPRING_DATASOURCE_PASSWORD=mvp_c_local \
APP_STORAGE_DEV_DIR=$PWD/backend/web-java/target/c-dev-storage \
APP_C_FACE_BOUND_MEMBER=<成员UUID> \
java -jar backend/web-java/target/web-java-0.0.1-SNAPSHOT.jar
# curl 一律 --noproxy '*'
```

容器（已建，卷保留）：`docker run -d --name mvp-c-pg -e POSTGRES_PASSWORD=mvp_c_local -e POSTGRES_DB=mvp_c_dev -p 127.0.0.1:55436:5432 postgres:16`。mvp_c_dev 残留活体冒烟种子（c-live-* 前缀，可整库重建；IT 用每次新建的临时库，不受影响）。

## 最小公共接口/协调请求（按裁定上报，不擅改公共契约）

1. **人脸 1:1 成员绑定端口**（owner：总协调/A 公共基础）：现有 `FaceProvider.classify(purpose, bytes)` 无成员参数，不能证明「当前人脸=方案成员」。C 已按裁定以 C 域端口 `CareFaceVerifier.verifyOneToOne(purpose, memberId, candidateBytes)` 落地并生产 fail-closed。真实接入需要的最小公共能力：①按 memberId 解析可信参考照（T01.identity_summary 的参考媒体引用键约定，owner B/D）；②1:1 比对（参考照+候选字节→MATCH/MISMATCH/UNCERTAIN/QUALITY_REJECTED/DEPENDENCY_FAILED）；③参考照版本/策略元数据留痕。请求总协调决定是否将 CareFaceVerifier 形状提升为公共端口或由 A 扩展 FaceProvider。
2. **方案 JSONB 公开白名单批准**（owner：总协调/D/契约）：CarePlanProjection 的 FULL/EXECUTION/SUMMARY 键集合为 C 侧保守提案（未知键默认丢弃）；请 D 在 plan_payload/plan_summary 版本化约定中确认公开键名，必要时经契约 lane 冻结。
3. **能力字段形状确认**（owner：D）：C 防御式读取 parameter_ranges{name:{min,max,unit}}、supported_regions（回退 regions）、n_bounds{min,max}、steps[]{region,parameters{name:值|{value,unit}}}；与 D 最终版本化约定如有差异，按裁定走最小协调请求，C 不擅改。

## 给 B 的约定（MediaAccessPolicy / 归属）

1. C 写入的 T11 行 purpose 仅 `execution_face`/`revalidation_face`（核验证据，受理事务内补 execution_id/member_id）。**C 任何响应不返回其 mediaId/contentUrl；B 的业务 MediaAccessPolicy 应将 face purposes 对一切主体保持不可读（与 A owner-dev 行为一致），无需为 C 开读取分支。**
2. C 不提供 @Primary MediaAccessPolicy、不改 A deny-all 默认。执行归属判定素材：执行行冻结 assessment_id_at_start+controller 归属；可见性=「仅原控制端+授权 APP（T02 active）」；撤销后原端仅最小对账。
3. C 对 T02 只读（active 存在性+锁内 FOR UPDATE 复核）；授权/撤销写边界全在 B；C 每请求读当前 T02，撤销即时生效。
4. 云台「当前任务」判定 C 一律读 T03.current_assessment_id/current_assessment_revision（B/D 写），C 从不移动指针。

## 给 D 的约定（T06 边界 / 方案夹具 / 总协调裁定 2026-09-11）

0. **总协调 D→C 衔接裁定（C 已核对一致）**：D 报告发布事务唯一创建 T06（assessment_id 唯一、waiting_inputs、generation_revision=0、input_photo_version）并入队 plan.generate；ready 后 target_count/plan_payload/input_snapshot 冻结；**D 不写 K/completed_at/progress_revision/T07/T08、不释放占用**。正常能力等待保持 generation_revision（代次围栏延后、不消耗失败 attempt）；**C 代码对 generation_revision 零逻辑依赖**（仅宽表行被动读取）。
1. **T06 字段级写边界**：C 仅 UPDATE completed_count/progress_revision/completed_at/updated_at（WHERE generation_status='ready'，影响行数≠1 整体回滚）。
2. **ready 行形状**：target_count>0 且 plan_payload 非空带整数 schema_version（DB CHECK 强制）；plan_payload 经 C 白名单投影后才外发（**D 仍须保证不含供应商原始响应/提示词——白名单是第二层防御不是替代**）；plan_summary 供 A01。
3. **能力约定已对齐**（裁定 §150/§151）：见上文裁定 4；required_capability_revision 不存在、已删除；capability_revision 仅追溯；microcrystal_id 不绑定设备；approved_regions/n_bounds 冻结字段 C 已实现校验。C 测试夹具即按此形状模拟 D 输出（DEFAULT_INPUT_SNAPSHOT/DEFAULT_CAPABILITIES，见 CareTestFixtures），联调时 D 真实写入满足同形状即可。
4. **A03 云台准入联动**：云台执行经 currentTaskId/currentAssessmentRevision 与 T03 指针核对，D 的 M3-A01「受理即原子替换指针」后旧任务准入自动 409 TASK_REPLACED；「护理未收尾禁新测肤」的 T07 未收尾检查（M3-A01 侧）由 D 实现，C 占用语义=仅 closed_at 非空释放。
5. 等待语义：A01/A02 对 waiting_inputs/generating/failed 返回 200+公开状态（waitingReason 三 token），不触发生成。

## 限制与未决（如实披露）

- **生产准入不可用是有意状态**：成员绑定 1:1 人脸提供方未接入前，生产 profile 准入/恢复核验恒 503 fail-closed（裁定要求，不伪造通过）；dev/test 用显式成员绑定替身。真实提供方接入不是「换一个 Bean」：需要参考照解析约定+比对协议（见协调请求 1）。
- connectionProof/consentEvidenceRef 当前仅参与请求处理与 T13 摘要，**未完成可信证据验证**（配对/同意协议属设备与合规对接）。
- 能力数值域/单位、Plan.execution 结构未冻结（契约 x-detail: skeleton）；C 为防御式读取+保守投影。
- 白名单键集合为 C 提案待批（协调请求 2）。
- dev profile 下 `app.providers.mode=disabled` 时 MemberBindingFaceDouble 仍激活（@Profile 限定而非 mode 门控；生产 profile 不受影响）——已披露的 dev 便利偏差。
- 测试存储：C IT 经 AbstractCareIT 属性注入本树 target/c-test-storage（A 文件不可改，A 自身测试仍用 /tmp/mvp-a-test-storage；两者上下文隔离互不影响）。
- 记录插入为逐条 INSERT+SAVEPOINT（非批量 INSERT）；T07 行锁串行化下唯一约束竞态分支为防御性（并发测试证明收敛不 500，不证明该分支必然执行）。
- 观察 seq 允许 0（契约 BigintString 未禁）；记录 sourceSeq≥1；A05 latest_observation.occurred_at 存 RFC3339 秒精度归一值；错误响应不带 no-store 头（GlobalExceptionHandler 为 A 基础类不可改；200 响应全部 no-store）。
- 活体冒烟为 dev 替身链路（短信/会话/设备凭据/存储/人脸均为 A/C 替身），不代表真实供应商可用。
- 94 业务场景属 E 验收矩阵；C 侧断面对 SC-04-*/SC-06-*/SC-07-*/SC-R-07/10/12/13 已覆盖（IT+活体）。

## 清单证据映射（checklists.json C-01..C-17）

| 项 | 证据 |
|---|---|
| C-01 | 9 API 实现+占位替换；契约校验四项绿；IT 契约形状断言 |
| C-02 | A01/A02+白名单投影；CarePlanQueryIT/CarePlanProjectionIT（含 SECRET 防泄漏） |
| C-03 | A03 锁外核验+锁内重检链（本人 1:1 成员绑定/当前任务/能力 D 约定/K<N/原子）；CareAdmissionIT+CareFaceBindingIT+CareCapabilityCheckerTest |
| C-04 | 双部分唯一索引；CareAdmissionConcurrencyIT（同微晶双端恰一 201、同云台互斥、跨端占用、仅 closed 释放） |
| C-05 | A05 观察状态机（→running 统一门控、unknown 禁止、冻结）+A04；CareLedgerIT/CareRevalidationIT |
| C-06 | T08 归属自 T07 派生；双唯一键；批内/DB 双键判重 IT |
| C-07 | 异内容整批 409 回滚 IT；汇总≠1 行→INTERNAL 整体回滚（账实一致 IT） |
| C-08 | K=9/10/11 IT（isCompleted/completed_at 首达保持/K 不截断/A03 PLAN_COMPLETED） |
| C-09 | A06 水位对账+条件关闭；缺口/总量不符/未停止/W=MAX 无溢出 IT；closed 释放后再准入 201（IT+活体） |
| C-10 | closed 迟到入账+late_variance 留痕+不重开 IT |
| C-11 | 撤销后：A05 最小 ack（progress=null）、A07 最小投影、A06 仍可收尾、A03/A04/A08 拒绝、**重放亦拒绝（F1）** IT |
| C-12 | TASK_REPLACED（锁外+锁内）、事务回滚、旧成功响应重放无新有效性（IT+活体）、缺口收尾、并发双收尾 IT |
| C-13 | 提交链 11b653a→5bad406→24cab56→bd8e305 + 本文件 |
| C-14/15/16 | C-oracle.md（R1 FAIL@11b653a 全发现+修复映射 5bad406/24cab56/bd8e305；R2 @bd8e305 状态以 C-oracle.md 为准——oracle 会话 ID（ora-1/ora-2）、三次 401 token_expired 认证失败与 BLOCKED 处置、恢复后单次正式复审安排均已记录） |
| C-17 | **未达**——Oracle R2 BLOCKED 期间不进入集成；待认证恢复、R2 单次正式复审 PASS 后交总协调集成与 E 验收（本包不自行勾选） |

## 摘要（≤500 字）

C 包在 feature/mvp-care 交付 M4-A01..A09 全部 9 个 Java API 的实现与自测，最终代码 SHA=bd8e305（链 11b653a 实现→5bad406 Oracle R1 六项修复+迟到留痕→24cab56 总协调三裁定增量→bd8e305 活体绑定补充），A 基础/迁移/契约零改动。核心语义：统一 404 可见性；原控制端（永久写权）与当前读取资格（授权/当前任务）分离，重放同样重查资格；人脸准入为 1:1 成员绑定门禁，memberId 仅出自服务端持久化行，生产默认 fail-closed 503，dev/test 替身含异成员拒绝证据；能力覆盖对齐 D 版本化约定（capability_id/单位/范围/区域/n_bounds/steps 双重覆盖，revision 仅追溯）；方案 JSONB 经显式白名单投影，未知键丢弃；锁序 T03→T04→T06→T07→T02 短事务+锁外网络；双部分唯一索引原子占用；T08 双键去重+异内容整批回滚+K/汇总/T13 同事务；观察状态机 →running 统一门控、stopped/closed 冻结、迟到补账写 late_variance；A06 水位对账 count==W∧max==W⟺无缺口、条件关闭防双关、重放不改 manifest。证据：SHA 绑定 255/255 绿（树前后==bd8e305，RC=0）、契约四项 PASS、18085 活体全流程含占用释放/重放/白名单防泄漏 RC=0。**Oracle 门禁状态：R1 FAIL@11b653a（4 BLOCKER+2 IMPORTANT）已逐项修复并映射留档；R2 @bd8e305 因 oracle 提供方认证过期（401 token_expired，三次调用、两个会话，均无审查结论）记录 BLOCKED——本包未通过 Oracle 门禁，不具备交总协调集成条件；待认证恢复明确通知后单次正式复审，PASS 前不交付。**限制如实披露：生产准入在真实成员绑定提供方接入前恒 503 fail-closed（有意状态）；connectionProof/consentEvidenceRef 未做可信验证；白名单与能力字段形状待契约批准。不合并、不推送、不自行声称验收；R1 修复不冒充最终复审通过。
