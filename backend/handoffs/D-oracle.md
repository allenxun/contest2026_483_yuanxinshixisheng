# D-oracle.md — D 包 Oracle 独立审查报告

- **状态：BLOCKED（无结论）**。按 COMMON.md 门禁：Oracle 不可用/调用失败/没有结论时记录 blocked，不视为通过；D 包在获得真实 Oracle 两轮结论前不声称完成。
- **候选被审代码 SHA（reviewedCommit 候选）**：`6b4f9ed82d4e828749f04082b79381362281ff49`（branch `feature/mvp-assessments`，基线 `ccee6e2`，提交时间 2026-09-11T12:12:05+08:00，48 文件 +9322/−47，提交后树 clean）。
- 审查者（指定）：本机 OpenCode omo-slim 配置的 `oracle` 子代理（只读）。两轮独立：R1=M3（测肤 HTTP API+算法/身份归档 Worker+media.cleanup），R2=M4 方案生成 Worker（含公共 defer 接口改动）。

## 调用失败记录（2026-09-11，提交 6b4f9ed 之后）

| 轮次 | 会话 ID | 结果 | 最小错误文本（不含认证头/cookie） |
|---|---|---|---|
| R1 首次 | `ses_f71543c6fffek9grBzuLOe3Tyq` | error | Subagent failed: Provided authentication token is expired. |
| R2 首次 | `ses_f7153d553ffeIkwL0q5jBQDLu9` | error | Session error（同上认证过期，监督侧核实） |
| R1 重试 | `ses_f715343c2ffeb8hcwbUZGfsHp6` | error | Subagent failed: Provided authentication token is expired. |
| R2 重试 | `ses_f7152f8edffenEa5UOfsFU0eG7` | error | Subagent failed: Provided authentication token is expired. |

- Codex 监督者已独立核实最近两次错误为 **401 token_expired** 并报总协调。
- 处置：不循环重试、不自行更换模型/提供方/凭据（任务书与总协调明令）；等待明确恢复通知后，每轮各做**单次正式调用**。
- orchestrator 自身会话同期正常（非全局 provider 故障；为 oracle 子代理凭据过期）。

## 恢复后审查位置（已保留，直接可执行）

完整提示词草稿存于运行目录 `.mvp-d-runtime/oracle-prompts.md`（git-ignored；要点内联如下，恢复后以本文件+内联范围为准注入 SHA 调用）。

### 通用要求（两轮相同）
只读；先 `git rev-parse HEAD` 核实并记录 reviewedCommit==`6b4f9ed…`（结论仅绑定该 SHA，后续代码变化需复审）；不改任何文件；不重跑长套件（可抽查代码/测试一致性）；裁定语义依据 `.mvp-d-runtime/coordination-request.md` B/C/D/E/F 节（总协调 2026-09-11）；权威设计=backend/doc/后端详细设计-V1-MVP.md、数据架构设计、backend/contracts/openapi.yaml M3 段、backend/handoffs/A.md 接入边界。
输出格式：①reviewedCommit ②逐项核验表（要求→COMPLIANT/DEVIATION/UNVERIFIED→证据 file:line）③发现分级 BLOCKER/IMPORTANT/MINOR/NOTE（位置/复现/为何阻塞）④blockingFindings 列表 ⑤Overall: PASS/PASS-with-notes/FAIL ⑥测试证据充分性 ⑦2-3 个对抗性绕过推演（越权/重放/旧代次/诊断泄漏）及结果。

### R1 — M3 范围与核验点（9 组）
范围：`web-java/.../assessments/**`（main 13+test 6）+ stub 两文件 diff（恰删 6 个 M3 方法）；`worker-python/.../handlers/{assessment_analyze,identity_enroll,media_cleanup}.py`+`dshared/**`+注册表 4 条目；对应测试。
核验点：①D-01~05 六 API 与 openapi 逐字段对齐（信封/bigint 串/no-store/202vs200 replay/view 限制/游标绑定 memberId/统一 404 不泄存在性/云台 full→403/APP 禁测肤/云台禁历史；白名单投影仅冻结 report_payload）②D-03 互斥与受理原子性（T03 锁→T07 检查→stopped/DEVICE_OCCUPIED 映射；T05+T11claim+指针+T12+T13 一事务；拒绝=事务内 rejected+提交后抛）③D-04 补拍全分支（needs_retake-only/版本+1/视角集合精确/merged 三视角防御/旧结果隔离）④D-06~09 worker（不确定不建档；确定性 candidate+PG 对账防替身失忆循环；namespace 串行+failed 占槽受控恢复；先持久阶段后锁外调用+超时对账恰一次注册+stale 不归属；结果图先归档后原子发布；写边界双向不越）⑤cleanup（两段式/五表引用扫描+T13 活性/安全不足不删/discover 幂等/Java 5 接线点尽力而为/无 TTL 不删行）⑥提供方边界（production+double fail-closed；aliyun 全 ProviderNotActivated 无伪造；指标白名单违约终态不发布）⑦诊断纪律（failure_detail/last_error 原文不外发；Java 无 failure_detail 读路径；封闭 failure_code）⑧测试证据充分性（Java 179/Python 125 各双执行+提交后 SHA 绑定复跑；E2E 链证据及其绑定诚实声明）⑨生产接入限制如实性（替身≠真实；基线占位；storage double；94 场景归 E）。

### R2 — M4 方案生成 Worker + 公共 defer（7 组）
范围：`handlers/plan_generate.py`+`dshared/dconfig.py`+公共三文件改动（`runtime/complete.py` 的 `_DEFER`/`complete_deferred`、`runtime/loop.py` process_job 分发分支、`handlers/__init__.py` HandlerResult.defer_seconds）+`assessment_analyze._publish` plan 入队 max_attempts+相关测试（test_plan_generate 30 项、test_complete_deferred 8+1 项）。
核验点：①K 保护硬证据（无 D 路径写 completed_count/completed_at/progress_revision；T06 INSERT 仅初值）②defer 语义逐条对照裁定（同 job/dedup/generation_revision；租约围栏单事务；business 守卫先行不符全回滚不退计数；GREATEST(attempt-1,0)；lease_revision+1 作废旧代次；0 行→StaleGeneration 拒重复 defer/旧 lease；不读写 last_error；文档限定合法等待、真实失败必走 complete_failure 计 attempt）③公共文件最小性（git show 核对恰为授权三处；claim/expire/renew/__main__/health/conftest 未动）④冻结快照唯一校验基线（live 仅 waiting 门+冻结时刻；PLAN_SNAPSHOT_INVALID 无回落；中途改 live 配置不改结果；覆盖检查 device⊇baseline；waiting 不增 generation_revision；ready 冻结+重放 no-op；非法输出永不发布、violations 仅 json_path）⑤四类 defer 证据测试映射与断言强度（等待不耗预算/真实失败耗预算/旧 lease+重复 defer 拒绝无双重退款/业务+队列原子回滚）⑥C/D §E 契约一致性（snapshot 字段路径逐项对照）⑦测试证据充分性（125 绿双执行、A 基线 47 内含仍绿、E2E ready 路径活体）。

## 既有结论与残留

- 本文件提交时**无任何 Oracle 轮次结论**（0 轮完成）；不存在可继承的旧结论。
- 恢复后流程：单次正式调用 R1+R2（可并行，均只读）→ 任一 BLOCKER → 有界修复 → 受影响套件复跑 → **新 SHA 复审**（旧结论不覆盖新代码）→ 结论/发现/修复/复审记录追加本文件 → 纯报告修订无须循环审查自身。
- 候选 SHA 的测试证据明细见 `backend/handoffs/D.md`（含命令/退出码/UTC 时间/树 clean 绑定与 E2E 绑定诚实声明）。
