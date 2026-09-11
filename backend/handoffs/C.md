# C 包交付说明（护理管理 M4 · Java 业务）

状态：**Oracle 门禁已通过**——R1 FAIL@11b653a → 修复 → R2 FAIL@bd8e305（授权单次执行）→ 修复 → **R3 PASS-with-notes@8b3592e（blockingFindings=[]）**；全程记录见 `C-oracle.md`。本包不合并、不推送；交总协调集成后由 E 独立验收（本文不声称已验收）。

## 提交

- 工作树 `.worktrees/mvp-c`，分支 `feature/mvp-care`，基线 `ccee6e2`（A 验收放行后的 dev 合并点）。
- 代码提交链（均未推送、未合并）：
  - `11b653a` — C 包 M4 实现（30 文件 +6704/−51：care 包主类+测试类；stub 仅删 9 个 M4 占位）
  - `5bad406` — Oracle R1 修复（F1-F6 + 迟到差异留痕 N1）
  - `24cab56` — 总协调三裁定增量（人脸成员绑定 fail-closed / 测试存储本树化 / 能力匹配对齐 D 约定）
  - `bd8e305` — dev/test 环境绑定成员补充（APP_C_FACE_BOUND_MEMBER，活体 E2E 可行性）
  - `fe6a2e7`、`0dfc0ed` — report-only（门禁记录）
  - **`8b3592e0b5de86eeaf0febe6ffe9497c68f672bb` — 最终代码 SHA（R3 所审=PASS）**：Oracle R2 三 BLOCKER 修复（递归嵌套白名单 / 能力严格 fail-closed / 混合 profile 双防线）
- 本报告提交（C.md + C-oracle.md）：report-only，SHA 见 git log。
- A 基础设施、迁移、契约（openapi/schemas/samples/scripts）、共享 yml：**零改动**。无新表、无 Python、无 start/stop 下发。

## 范围实现映射（M4-A01..A09 = C-01）

| API | 实现 | 要点 |
|---|---|---|
| M4-A01 GET members/{id}/care-plans | CareQueryController/Service | T02 验权→T06 单表 keyset 分页；reportId 过滤经 T05 两步单表；ready 才附 Progress；planSummary 白名单投影 |
| M4-A02 GET care-plans/{id}?view=full | 同上 | plan_payload 经 CarePlanProjection **递归结构化白名单**（各层级未知键丢弃）；未就绪仅公开 waitingReason（failure_detail 绝不外发）；云台 403 |
| M4-A03 POST care-executions | CareAdmissionController/Service | 锁外（媒体/人脸 1:1 成员绑定核验/预检）+ 最终短事务锁序 T03→T04→T06→INSERT T07→T02；能力覆盖按 D 约定**严格 fail-closed**；占用由两个部分唯一索引原子裁决→统一 409 DEVICE_OCCUPIED；201 admitted/重放 200 replayed（重放须当前读取资格，否则统一 404） |
| M4-A04 POST .../revalidations | 同上 | 仅原控制端；paused+代次匹配+K<N+（APP）授权/（云台）当前任务；revision+1、状态不变；continuity_invalidated 仅由 A04 清除；重放同样须当前资格 |
| M4-A05 POST .../observations | CareLedgerController/Service | 锁序 T06→T07；双键批量判重（两条单表 SELECT）；异内容整批 409 回滚；D=真实新增和；K/accepted_count/progress_revision/completed_at 同事务；观察独立序号+状态机（→running 统一门控）+stopped/closed 生命周期冻结；迟到记录 closed 后照常入账并写 late_variance 留痕；Progress 仅给当前有读取资格者 |
| M4-A06 POST .../closure-confirmations | 同上 | 停止观察核对+固定 epoch 单表 COUNT/MAX/SUM 水位对账（count==W∧max==W⟺1..W 无缺口）；缺口有界输出（≤20 段+more，无 W+1 溢出）；条件更新 WHERE status='stopped' 防双关；closed_at 释放占用；重放不重写 manifest |
| M4-A07 GET care-executions/{id} | CareQueryController/Service | 双路径授权（授权 APP 完整视图 / 原控制端最小对账视图，云台一律最小）；recordsAfterSeq 单表分页确认 ID |
| M4-A08 GET care-plans/{id}/progress | 同上 | APP 走 T02；云台必带 executionId+verificationRevision，且生命周期∈{admitted,running,paused}、连续性未失效、T03 当前任务（TASK_REPLACED）——数字代次相等≠核验适用；查询零写入 |
| M4-A09 GET members/{id}/care-executions | 同上 | T02→T07 成员分页（planId/from/to 过滤）；planSnapshotSummary 取冻结快照白名单投影，不逐行回查 T06 |

## 关键裁定语义（供 E 验收与 B/C/D 对齐；均记录于代码 javadoc）

1. **统一不可见**：资源缺失/无授权/已撤销/非归属/代次过期/连续性失效一律同一 404 RESOURCE_NOT_VISIBLE 信封（RV-5 模式）；APP-only 端点收到云台→403 CALLER_NOT_ALLOWED；C 不发 GRANT_REVOKED。
2. **原控制端 ≠ 持续读取权**（R1-F1 修复，R3 核定无回归）：可补账/收尾（A05/A06/A07 最小视图）是原控制端永久权利；可读方案正文/Progress（A02/A03/A04 重放、A05 progress、A08）必须当前资格——APP=T02 active，云台=T03 当前任务指针；资格缺失统一 404 / progress=null。
3. **人脸 1:1 成员绑定门禁**（总协调裁定）：公共 FaceProvider.classify 无成员参数，不得作准入证据。C 域端口 `CareFaceVerifier.verifyOneToOne(purpose, memberId, candidate)`，memberId 只来自服务端持久化行（A03=plan.member_id，A04=execution.member_id），绝无客户端输入路径。**三重防线**：①`CareDevTestCondition`——app.env=production 或生效 profiles 含 prod/production 时替身绝不注册（混合 prod,dev 亦拒绝；active 为空回退 default=dev 与共享配置一致）；②`CareFaceVerifierProductionGuard`——production 语境选中非 FailClosed 实现即启动 fail-fast；③A 的 ProductionFailClosedValidator（通用层）。生产默认 `FailClosedCareFaceVerifier` 恒 CAPABILITY_UNAVAILABLE→503（T13 保持 processing），**真实成员绑定提供方接入前生产准入不可用是有意状态**；接入真实提供方时须同步更新 Guard 的「可信生产实现」判定（R3 note）。dev/test 替身 `MemberBindingFaceDouble`：未绑定→CAPABILITY_UNAVAILABLE、异成员→MISMATCH（403 rejected）、一致→MATCHED；活体联调用 `APP_C_FACE_BOUND_MEMBER=<uuid>` 环境绑定（非法值 fail-fast）。MISMATCH/UNCERTAIN→403 FACE_NOT_VERIFIED；QUALITY_REJECTED→422；DEPENDENCY_FAILED→503。
4. **能力覆盖严格 fail-closed（对齐 D 约定）**：input_snapshot.capability 必需子结构逐项校验——capability_id（非空）、parameter_ranges（非空、min≤max、unit 非空）、approved_regions（非空）、n_bounds（min≤max），任一缺失/畸形→409 PLAN_NOT_READY reason=`malformed_frozen_capability`；设备侧 capability_id 相等、逐项范围覆盖且**双侧 unit 必须存在并严格相等**、approved_regions⊆设备 supported_regions（回退 regions）、N∈n_bounds（含端点）；plan_payload.steps **必须非空**且每步 region（非空 string）+parameters（object）结构完整（否则 `malformed_frozen_step`——协议未冻结的保守拒绝），region 双重符合、参数名在冻结 ranges 内、值同时落冻结+设备区间、{value,unit} 形式 unit==冻结 unit。reason token 共 9 种有界枚举。**capability_revision 仅追溯、microcrystal_id 不绑定设备，均不参与判定**；虚构字段 required_capability_revision 已删除。锁外+锁内同一 checker，无绕过路径（R3 核定）。
5. **方案 JSONB 递归白名单投影**（R1-F3→R2-B1 闭合）：CarePlanProjection 各层级显式重建——FULL=title/description/steps/regions/parameters；EXECUTION=steps/regions/parameters；SUMMARY=title/description/source_report_id/source_report_ready_at；step 仅保留 region+parameters；参数定义仅标量或 {value,unit}；regions 仅 string 元素；任何层级过滤后为空→丢弃该键，顶层空→null；WARN 仅记键路径不记值；schema_version 不外发；快照写入即过滤（敏感键绝不冻结进 T07）。**白名单为 C 侧保守提案，待总协调/D 契约批准后冻结**；标量参数名按已声明协议语义保留，安全前提=D 只把批准的执行参数写入参数槽（R3 note 7）。
6. **记录/观察流**：每执行固定 epoch=执行 UUID 串；观察与记录两条独立递增序列；记录 sourceEpoch 不符→逐条 rejected，观察 epoch 不符→整批 409；→running 转移统一门控（连续性未失效+代次匹配）；unknown→running 禁止；stopped/closed 生命周期冻结（观察不入、记录照常+late_variance 留痕）。
7. **Verification.validUntil=null**：真实提供方未接入不伪造时效；重放 verification.replayed=true 且绝不刷新 revision/verifiedAt（旧成功响应重放不产生新核验有效性）。
8. **幂等**：四写端点 Idempotency-Key 必携；operation=care.execution.create/care.execution.revalidate/care.observation.sync/care.closure.confirm；确定性拒绝→T13 rejected 同键重放原拒绝；瞬时失败保持 processing；A05 重放=冻结 acks+当前状态重投影。
9. **溢出**：bigint 解析/求和/汇总 addExact；溢出→400 count_overflow 整批拒绝。
10. **写边界（字段级）**：T07 全生命周期（C 独占）；T06 仅 completed_count/completed_at/progress_revision/updated_at 且 WHERE generation_status='ready'；T08 仅 INSERT；T11 仅补 execution_id/member_id；T02/T03/T04/T05/T01 只读；不写 T12。
11. **查询纪律**：全部单表显式列 SQL，无 JOIN/关联子查询/ORM 关联；批量判重两条 SELECT；记录插入为逐条 INSERT+SAVEPOINT（批上限 200；T07 锁串行化下唯一约束竞态分支为防御性）；keyset 分页绑定 filterDigest。

## 测试证据（最终代码 SHA 8b3592e 绑定，R3 已采信）

- **Java 全套件（SHA 绑定，orchestrator 独立执行）**：`mvn -B test`（隔离 mvp-c-pg postgres:16 @127.0.0.1:55436）→ **Tests run: 262, Failures: 0, Errors: 0, Skipped: 0，RC=0；TREE_BEFORE==TREE_AFTER==8b3592e、dirty=0（SHA_BOUND=YES）**。262=137 A 基线（不变）+125 C 项：
  - 查询 IT：三态 404 全等、云台 403、分页/游标/过滤、投影形状与 bigint 字符串、只读证明、快照冻结、撤销后最小视图、A08 生命周期/连续性门禁。
  - 准入/恢复 IT：APP/云台快乐路径、重放同执行+无新有效性+重放资格复核（撤销/换任务后重放→404）、异内容键冲突、确定性拒绝重放、角色/purpose 校验、TASK_REPLACED、PLAN_COMPLETED、**能力严格负例（capability={}/缺各必需子结构/单边缺 unit/steps 缺失或畸形→各 reason token）与正例（revision 9≠7 通过、microcrystal_id 不同通过）**、**人脸成员绑定（异成员 403 证据、未绑定 503 fail-closed、四分类映射、FailClosed 单元证明、容器级 bean 选择证据含 prod,dev 混合 profile）**、并发同微晶双端恰一 201、并发同云台互斥、并发 A04 同代次恰一成功、占用仅 closed 释放。
  - 账本/收尾 IT：双键去重全分支、整批 409 回滚、K=9/10/11+completed_at 首达保持+K 不截断、插入后汇总失败整体回滚、观察状态机全转移+running 门控+冻结、迟到补账+late_variance、W=0/缺口（W=Long.MAX 无溢出）/总量不符/未停止/双关防护、manifest 重放逐字节不变、撤销后最小 ack+仍可收尾、并发同记录收敛、并发双收尾恰一 200。
  - 纯单元：CareCapabilityCheckerTest 27 项（含 10+ 严格负例）、MemberBindingFaceDoubleTest 4、CareDevTestConditionTest 1、CareFaceVerifierProductionGuardTest 5；CarePlanProjectionIT **多层嵌套 SECRET 防泄漏**（steps[i]/step parameters/顶层 parameters/regions 非 string 元素；响应+T07 快照逐字节断言）。
- **契约校验 @8b3592e**：jcs selftest 26 PASS；validate_samples PASS；validate_responses --selftest PASS；openapi-spec-validator OK（契约文件未触）。
- **活体冒烟 @8b3592e**（真实 HTTP 18085 + 真实 PG mvp_c_dev + APP_C_FACE_BOUND_MEMBER；`target/c-live-smoke.log`、逐响应 `target/c-live-evidence/`，gitignored）：**LIVE_SMOKE_ALL_PASS RC=0**——登录→D 约定形状种子→A01/A02（含嵌套白名单 SECRET 防泄漏现场断言+steps[0].region 保留）→A03 201（epoch=executionId）→A05 三记录 K=3→重传全 duplicate→stopped→A06 closed+occupancyReleased→重放 manifest 不变→A07 closed+水位 3→A08 K=3/remaining7→A09→同微晶二次准入 201（占用释放实证）→旧 A03 键重放 meta.replayed+verification.replayed=true→A05 paused(continuityValid=false)→A04 revision2 仍 paused→A04 重放不递增→陌生账号 404。透明披露：首次冒烟曾 409 IDEMPOTENCY_CONTENT_CONFLICT，系冒烟脚本单引号致 $RUN_ID 未展开的 harness 缺陷（跨运行同键异内容），与产品代码无关；修正后全过（已如实呈报 R3 并获采信）。

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

容器：`docker run -d --name mvp-c-pg -e POSTGRES_PASSWORD=mvp_c_local -e POSTGRES_DB=mvp_c_dev -p 127.0.0.1:55436:5432 postgres:16`（交付后已 docker stop 省内存，**卷保留**；复跑前 `docker start mvp-c-pg`）。mvp_c_dev 残留活体冒烟种子（c-live-* 前缀，可整库重建；IT 用每次新建临时库，不受影响）。

## 最小公共接口/协调请求（按裁定上报，不擅改公共契约）

1. **人脸 1:1 成员绑定端口**（owner：总协调/A 公共基础）：C 已按裁定以 C 域端口落地并生产 fail-closed。真实接入需要：①按 memberId 解析可信参考照（T01.identity_summary 参考媒体引用键约定，owner B/D）；②1:1 比对（参考照+候选字节→MATCH/MISMATCH/UNCERTAIN/QUALITY_REJECTED/DEPENDENCY_FAILED）；③参考照版本/策略元数据留痕。请总协调决定是否将 CareFaceVerifier 形状提升为公共端口或扩展 FaceProvider；**接入时须同步更新 CareFaceVerifierProductionGuard 的可信生产实现判定**（R3 note 5）。
2. **方案 JSONB 公开白名单批准**（owner：总协调/D/契约）：CarePlanProjection 的 FULL/EXECUTION/SUMMARY 键集合与嵌套规则（step=region+parameters；parameter=标量或 {value,unit}）为 C 侧保守提案（未知键默认丢弃）；请 D 在 plan_payload/plan_summary 版本化约定中确认，必要时经契约 lane 冻结。
3. **能力字段形状确认**（owner：D）：C 严格校验 parameter_ranges{name:{min,max,unit}}（双侧 unit 必填且相等）、supported_regions（回退 regions）、n_bounds{min,max}、steps[]{region,parameters{name:值|{value,unit}}} 且 **steps 必须非空、每步结构完整**（保守拒绝）；D 若允许无 steps/无参数步骤须先协调版本化协议。差异按裁定走最小协调请求，C 不擅改。

## 给 B 的约定（MediaAccessPolicy / 归属）

1. C 写入的 T11 行 purpose 仅 `execution_face`/`revalidation_face`（核验证据，受理事务内补 execution_id/member_id）。**C 任何响应不返回其 mediaId/contentUrl；B 的业务 MediaAccessPolicy 应将 face purposes 对一切主体保持不可读（与 A owner-dev 行为一致），无需为 C 开读取分支。**
2. C 不提供 @Primary MediaAccessPolicy、不改 A deny-all 默认。执行归属判定素材：执行行冻结 assessment_id_at_start+controller 归属；可见性=「仅原控制端+授权 APP（T02 active）」；撤销后原端仅最小对账。
3. C 对 T02 只读（active 存在性+锁内 FOR UPDATE 复核）；授权/撤销写边界全在 B；C 每请求读当前 T02，撤销即时生效。
4. 云台「当前任务」判定 C 一律读 T03.current_assessment_id/current_assessment_revision（B/D 写），C 从不移动指针。

## 给 D 的约定（T06 边界 / 方案夹具 / 总协调裁定 2026-09-11）

0. **总协调 D→C 衔接裁定（C 已核对一致）**：D 报告发布事务唯一创建 T06（assessment_id 唯一、waiting_inputs、generation_revision=0、input_photo_version）并入队 plan.generate；ready 后 target_count/plan_payload/input_snapshot 冻结；**D 不写 K/completed_at/progress_revision/T07/T08、不释放占用**。正常能力等待保持 generation_revision（代次围栏延后、不消耗失败 attempt）；**C 代码对 generation_revision 零逻辑依赖**（仅宽表行被动读取）。
1. **T06 字段级写边界**：C 仅 UPDATE completed_count/progress_revision/completed_at/updated_at（WHERE generation_status='ready'，影响行数≠1 整体回滚）。
2. **ready 行形状（C 严格校验，准入前提）**：target_count>0；plan_payload 非空带整数 schema_version 且 **steps 非空、每步 {region:string, parameters:object} 完整**；input_snapshot.capability 必带 capability_id/parameter_ranges（每项 min≤max+unit）/approved_regions/n_bounds——任一缺失准入即 409（malformed_frozen_capability/malformed_frozen_step）。plan_payload 经 C 递归白名单投影后才外发（**D 仍须保证不含供应商原始响应/提示词——白名单是第二层防御不是替代**；标量参数槽安全前提=D 只写批准的执行参数）。
3. **能力约定已对齐并加严**（裁定 §150/§151+R2-B2 修复）：capability_revision 仅追溯、microcrystal_id 不绑定设备；同 capability_id+双侧 unit 严格相等+设备范围覆盖冻结范围+区域双重符合+N∈n_bounds+steps 参数值双重落界。C 测试夹具按此形状模拟 D 输出（DEFAULT_INPUT_SNAPSHOT/DEFAULT_CAPABILITIES，见 CareTestFixtures）。
4. **A03 云台准入联动**：云台执行经 currentTaskId/currentAssessmentRevision 与 T03 指针核对，D 的 M3-A01「受理即原子替换指针」后旧任务准入自动 409 TASK_REPLACED；「护理未收尾禁新测肤」的 T07 未收尾检查（M3-A01 侧）由 D 实现，C 占用语义=仅 closed_at 非空释放。
5. 等待语义：A01/A02 对 waiting_inputs/generating/failed 返回 200+公开状态（waitingReason 三 token），不触发生成。

## 限制与未决（如实披露，R3 notes 已并入）

- **生产准入不可用是有意状态**：成员绑定 1:1 人脸提供方未接入前，生产 profile 准入/恢复核验恒 503 fail-closed（裁定要求，三重防线保证替身绝不进生产）；真实提供方接入需协调请求 1 的三项公共能力，且须同步更新 Guard 可信实现判定。
- connectionProof/consentEvidenceRef 当前仅参与请求处理与 T13 摘要，**未完成可信证据验证**（配对/同意协议属设备与合规对接）。
- 能力数值域/单位、Plan.execution 结构未冻结（契约 x-detail: skeleton）；C 为严格防御式读取+保守投影+保守拒绝（steps 必填）；D 协议演进需先协调（协调请求 2/3）。
- 白名单键集合与嵌套规则为 C 提案待批；标量参数名按声明语义保留，前提是 D 只写批准参数（R3 note 7）。
- 测试存储：C IT 经 AbstractCareIT 属性注入本树 target/c-test-storage（A 文件不可改，A 自身测试仍用 /tmp/mvp-a-test-storage；上下文隔离互不影响）。
- 记录插入为逐条 INSERT+SAVEPOINT（非批量 INSERT）；T07 行锁串行化下唯一约束竞态分支为防御性（并发测试证明收敛不 500，不证明该分支必然执行）。
- 观察 seq 允许 0（契约 BigintString 未禁）；记录 sourceSeq≥1；A05 latest_observation.occurred_at 存 RFC3339 秒精度归一值；错误响应不带 no-store 头（GlobalExceptionHandler 为 A 基础类不可改；200 响应全部 no-store）。
- 活体冒烟为 dev 替身链路（短信/会话/设备凭据/存储/人脸均为替身），不代表真实供应商可用。
- 94 业务场景属 E 验收矩阵；C 侧断面对 SC-04-*/SC-06-*/SC-07-*/SC-R-07/10/12/13 已覆盖（IT+活体）。

## 清单证据映射（checklists.json C-01..C-17）

| 项 | 证据 |
|---|---|
| C-01 | 9 API 实现+占位替换；契约校验四项绿 @8b3592e；IT 契约形状断言 |
| C-02 | A01/A02+递归白名单投影；CarePlanQueryIT/CarePlanProjectionIT（多层嵌套 SECRET 防泄漏，响应+快照逐字节断言） |
| C-03 | A03 锁外核验+锁内重检链（本人 1:1 成员绑定/当前任务/能力严格 fail-closed/K<N/原子）；CareAdmissionIT+CareFaceBindingIT+CareCapabilityCheckerTest 27 项 |
| C-04 | uq_execution_open_microcrystal/gimbal；CareAdmissionConcurrencyIT（同微晶双端恰一 201、同云台互斥、跨端占用、仅 closed 释放） |
| C-05 | A05 观察状态机（→running 统一门控、unknown 禁止、冻结）+A04；CareLedgerIT/CareRevalidationIT |
| C-06 | T08 归属自 T07 派生；双唯一键；批内/DB 双键判重 IT |
| C-07 | 异内容整批 409 回滚 IT；汇总≠1 行→INTERNAL 整体回滚（账实一致 IT） |
| C-08 | K=9/10/11 IT（isCompleted/completed_at 首达保持/K 不截断/A03 PLAN_COMPLETED） |
| C-09 | A06 水位对账+条件关闭；缺口/总量不符/未停止/W=MAX 无溢出 IT；closed 释放后再准入 201（IT+活体） |
| C-10 | closed 迟到入账+late_variance 留痕+不重开 IT |
| C-11 | 撤销后：A05 最小 ack（progress=null）、A07 最小投影、A06 仍可收尾、A03/A04/A08 拒绝、重放亦拒绝 IT |
| C-12 | TASK_REPLACED（锁外+锁内）、事务回滚、旧成功响应重放无新有效性（IT+活体）、缺口收尾、并发双收尾 IT |
| C-13 | 提交链 11b653a→5bad406→24cab56→bd8e305→8b3592e + 本文件 |
| C-14/15/16 | C-oracle.md：R1 FAIL@11b653a（F1-F6+N1）→修复；R2 FAIL@bd8e305（授权单次执行；3 BLOCKER）→修复；**R3 PASS-with-notes@8b3592e（blockingFindings=[]；R2 三项 CLOSED；R1 六项无回归）**；oracle 会话 ora-1=ses_f717e004fffeZ6Rebw1yyBq0CK（含 401 token_expired ×3 基础设施失败留档） |
| C-17 | 待总协调集成与 E 验收（本包不自行勾选） |

## 摘要（≤500 字）

C 包在 feature/mvp-care 交付 M4-A01..A09 全部 9 个 Java API，**最终代码 SHA=8b3592e，Oracle 门禁 R3 PASS-with-notes（blockingFindings 空）**。门禁历程：R1 FAIL@11b653a（重放读取权/A08 连续性/白名单/running 门控等 4 BLOCKER+2 IMPORTANT）→修复；R2 经 3 次 401 token_expired 基础设施失败留档 BLOCKED 后，按用户直接授权单次正式执行，FAIL@bd8e305（嵌套透传/能力 fail-open/混合 prod profile 替身可选 3 BLOCKER）→修复（递归结构化白名单、能力必需子结构逐项 fail-closed+双侧 unit 严格相等+steps 保守必填、CareDevTestCondition+ProductionGuard 双防线）→R3 核定三项 CLOSED、R1 六项无回归。核心语义：统一 404；原控制端写权与当前读取资格分离且重放重查资格；人脸准入=1:1 成员绑定（memberId 仅服务端持久化行），生产三重防线恒 fail-closed 503；能力覆盖严格对齐 D 版本化约定（revision 仅追溯、microcrystal_id 不绑定）；方案 JSONB 递归白名单、敏感键不透传不冻结；锁序短事务+锁外网络；双部分唯一索引原子占用；账本双键去重+异内容整批回滚+K/汇总/T13 同事务；观察状态机统一门控+生命周期冻结+迟到补账留痕；水位对账收尾+条件关闭防双关。证据：SHA 绑定 262/262 绿 RC=0（树前后==8b3592e）、契约四项 PASS、18085 活体全流程 ALL PASS RC=0。限制如实披露：生产准入在真实成员绑定提供方接入前恒 503（有意）；connectionProof/consentEvidenceRef 未可信验证；白名单/能力形状/steps 必填待 D 契约冻结（三项最小协调请求已列）。已具备交总协调集成、由 E 按矩阵验收的条件；不合并、不推送、不自行声称验收。
