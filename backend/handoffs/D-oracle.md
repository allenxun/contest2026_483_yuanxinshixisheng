# D-oracle.md — D 包 Oracle 独立审查报告

- **状态：第 1 轮（R1 M3）已实际完成 → 结论 FAIL（3 BLOCKER）@候选 6b4f9ed；R2（M4+defer）尚未执行**。处置中：按门禁有界修复 → 提交新 SHA → R1 复审 + R2 首审均绑定新 SHA（修复触及全部 D handler 的围栏路径与 plan 相邻文件，故两轮均在新 SHA 执行，旧 FAIL 结论不覆盖新代码）。
- **候选被审代码 SHA（第 1 轮 reviewedCommit）**：`6b4f9ed82d4e828749f04082b79381362281ff49`（branch `feature/mvp-assessments`，基线 `ccee6e2`；HEAD=`5c1d419…` 仅含 report-only 差异，经核验代码内容同一）。
- 审查者：本机 OpenCode omo-slim 配置的 `oracle` 子代理（只读）。两轮独立：R1=M3（测肤 HTTP API+算法/身份归档 Worker+media.cleanup），R2=M4 方案生成 Worker（含公共 defer 接口改动）。

## 认证阻塞历史（已恢复）

| 轮次 | 会话 ID | 结果 | 最小错误文本（不含认证头/cookie） |
|---|---|---|---|
| R1 首次 | `ses_f71543c6fffek9grBzuLOe3Tyq` | error | Subagent failed: Provided authentication token is expired. |
| R2 首次 | `ses_f7153d553ffeIkwL0q5jBQDLu9` | error | Session error（同上认证过期，监督侧核实） |
| R1 重试 | `ses_f715343c2ffeb8hcwbUZGfsHp6` | error | Subagent failed: Provided authentication token is expired. |
| R2 重试 | `ses_f7152f8edffenEa5UOfsFU0eG7` | error | Subagent failed: Provided authentication token is expired. |

Codex 独立核实为 401 token_expired 并报总协调；期间未循环重试、未换模型/凭据。2026-09-11 用户解除暂停并授权单次有界尝试后，认证已恢复，R1 实际调用成功（见下）。

## 第 1 轮（R1 = M3）— 实际调用记录

- 会话：`ses_f70d6639bffeJHH4g6Z16SyzsV`（oracle 子代理，只读）；2026-09-11 约 04:31Z 派发、04:37Z 返回完整结论（会话时间线）。
- reviewedCommit 绑定核验（oracle 执行并记录）：`git cat-file -t 6b4f9ed…`→commit；HEAD=`5c1d419…`；候选→HEAD diff 仅 `backend/handoffs/D.md`+`D-oracle.md`（report-only）；树 clean ⇒ 工作树代码内容==候选内容。contracts/迁移未被候选改动。
- **Overall: FAIL**。逐项核验表：检查点 2（互斥/受理原子性）、3（补拍/隔离）、6（提供方边界/指标白名单）、9（生产限制披露）COMPLIANT；1（API 投影）DEVIATION（I3+S1）；4（分析/登记/归档/发布/写边界）DEVIATION（B1-B3）；5（cleanup）DEVIATION（I2）；7（诊断投影）DEVIATION（I1）；8（测试证据）UNVERIFIED——SHA 绑定套件证据可信、E2E 限制披露诚实，但租约回收/并发交错路径缺测试，绿灯不足以证明 D-07~D-09。

### BLOCKER（oracle 定位，复现推演见其报告原文）
- **B1** 旧租约仍可独立提交终态业务失败：`assessment_analyze.py:526-554,618-632,635-642` 等 handler 内独立 `engine.begin()` 业务写（_mark_failed/_mark_needs_retake/阶段持久化）只查 processing_revision/status、不校验任务租约；租约过期被回收后旧 worker 仍能把 T05 写为终态 failed，绕过"业务写与 T12 租约围栏同事务"规则（complete.py:119-142 的围栏只保护完成回调路径）。
- **B2** needs_retake 可被并发 identity.enroll 关联正式成员：`identity_enroll.py:343-403` 新鲜度仅比较 processing_revision+photo_version，未校验当前状态/身份阶段；`_LINK_MEMBER`（:78-81）明确允许 `status='needs_retake'`。并发 uncertain→needs_retake 后登记完成仍建档并关联，违反"不确定不建档/stale 输入不归属"。
- **B3** 结果图 provider_ref 幂等仅支持串行重试：`dmedia.py:77-89,103-192` load-or-create 无数据库唯一约束或等效锁（V1:413-442/V2:50-54），旧租约与回收后新 worker 并发归档可产生两个正式 T11 对象；旧方报告写回被围栏撤销但 T11/存储副作用不回滚，且 cleanup 因 assessment_id 非空拒清。

### IMPORTANT
- **I1** `failure_code` 非封闭公开投影：`AssessmentReadService.java:60-74`+`FailureProjection.java:43-52` 将任意非空 DB 值原样返回（仅 retryable 封闭），未知内部编码会经授权 A03 泄露。
- **I2** cleanup 引用证明 TOCTOU：`media_cleanup.py:162-178,233-257` 引用扫描（多个独立只读连接）与 deleting 转换不同事务、业务行未锁定；引用可在扫描后、转换前建立；deleting 恢复路径跳过复核。
- **I3** brief 报告 `metrics:null` 违反 OpenAPI（`SkinReportService.java:142-156` vs `openapi.yaml:2364-2367` 仅允许 array）；现有 IT 断言 null=验证实现而非契约。

### SUGGESTION
- **S1** multipart 严格性：`AssessmentMultipartParser.java:97-122` 未校验 metadata part Content-Type；`getFileMap()` 折叠同名 part，无法检测重复文件 part。

### 对抗性抽查（oracle 执行）
①越权读取（外来 taskId/撤权 grant）→ 404 阻断 ✓；②旧租约终态写入 → **绕过成功（B1）**；③身份状态竞争 → **绕过成功（B2）**。

## 修复与复审计划（进行中）

- Python lane（复用既有 fixer 会话）：B1 dshared 租约围栏事务助手+全 handler 独立业务写接入（不改公共 runtime 三文件）；B2 _LINK_MEMBER 收紧（status='analyzing'+phase='enroll_pending'+candidate 匹配，0 行→成员保留无关联，任务仍成功）；B3 归档 pg_advisory_xact_lock+(锁后复查 load_by_ref) 复用同行（不加迁移）；I2 单事务协议（锁 T11 FOR UPDATE→同事务全引用扫描+T13 活性→deleting；deleting 恢复安全性论证）；补租约/并发交错测试（oracle 指出缺失的证据类）。
- Java lane（新 fixer 会话）：I1 公开 failureCode 封闭白名单+未知→null；I3 brief 按契约修正（不改 contracts）+IT 断言改契约导向；S1 metadata Content-Type 校验+重复 part 拒绝+测试。
- 完成后：顺序全量复跑（Java→Python）→ 提交新 SHA → **R1 复审 + R2 首审（同一新 SHA，两轮独立单次调用）**；纯报告修订不循环审查。

## 既有结论与残留

- 第 1 轮 R1 结论 **FAIL@6b4f9ed**（上文）；R2 无结论（未执行；认证阻塞期 4 次失败调用如实记录，不计为审查）。
- 候选 SHA 测试证据明细见 `backend/handoffs/D.md`（命令/退出码/UTC 时间/树 clean 绑定与 E2E 绑定诚实声明）；R1 对证据充分性的评估（8=UNVERIFIED 及理由）一并如实保留。
- 恢复后流程不变：BLOCKER→有界修复→受影响套件复跑→新 SHA 复审（旧结论不覆盖新代码）→结论/发现/修复/复审记录追加本文件。
