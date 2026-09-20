# E 定向复验（PARTIAL）——A f6e500e，run E-AB-20260910T155857Z-6a621528

> **定向复验（PARTIAL），非新 SHA 全量 52 项**：只复验 A 本轮修复直接相关的 echo lastError 投影闭合与严格响应契约；其余未变部分见 RV-9 台账。

新 A 候选：code=f6e500e474954781d3438188b6fdd389e61682e7 report=cf390e1a37f1575d7b0d4772a51246f9188b67b3 dev=f2755ab1741b5ee4f384fa66e73a2e669614ada9 integrated=d495a7d7c43aab3baae9afcf8774ae9850e6e41f

## 结算：11/11 唯一结算；10 PASS / 0 FAIL / 0 BLOCKED / 1 INFO（计数和=11==行数 11）；final_exit=0

**定向复验（PARTIAL）结果：通过（附条件）**——10 PASS / 1 INFO 待裁定（['RV-5']）；整体 A 基础验收意见由「旧证据台账 + 新 SHA 定向闭合 + 协调裁定」另行形成，本报告不就整体下结论。

| 项 | 检查 | 状态 | 命令/rc | 关键摘录 |
|---|---|---|---|---|
| RV-1 | 从当前源码重建：A 源码==f6e500e（git diff 空）+ 构建 jar + 启动健康 | **PASS** | git diff f6e500e -- web-java worker-python contracts; mvn -DskipTests package; java -jar / 0 | diff_empty=True HEAD=1fb5a5fbeb2b jar=web-java-0.0.1-SNAPSHOT.jar sha256[:16]=25d33dd6fab14461 health_up=True；同源各自重建，jar 哈希可能因构建元数据不同而非字节一致（不作可复现构建声明） |
| RV-2 | marker 变体闭合：jobId 关联 + 投影仅 null 或 {reason∈枚举,retryable:bool}，marker/原始 code/message 缺席 | **PASS** | UPDATE RETURNING count==1 + GET echo job (断言 data.jobId==请求) / 200 | sql_ok=True verdict=True jobId 匹配; lastError={'reason': 'internal', 'retryable': True} |
| RV-3 | 4000 字符长变体闭合：jobId 关联 + 响应无长内容且投影为枚举映射（非截断） | **PASS** | UPDATE repeat('L',4000) RETURNING count==1 + GET / 200 | sql_ok=True verdict=True jobId 匹配; lastError={'reason': 'internal', 'retryable': True} |
| RV-4 | 正常投影：queued→jobId 关联 + status/lastError/finishedAt 显式校验；可映射 reason（unsupported_contract） | **PASS** | GET queued job + 未知 job_type→worker 失败→GET / 200/200 | queued: jobId 匹配; status=queued; lastError=null; finishedAt=null | mapped: jobId 匹配; lastError={'reason': 'unsupported_contract', 'retryable': False} reason=unsupported_contract |
| RV-5 | 认证/归属边界：无 token/伪造 401 通过；真跨账号读取的可见性政策待总协调裁定 → INFO（附条件） | **INFO** | GET echo job：no-token/forged/真第二账号（独立身份）；非 200 分支=基本错误信封检查 / 401/401/200 | no-token: 401/AUTH_REQUIRED | forged: 401/SESSION_INVALID | accounts_differ=True s1_valid=True s2_valid=True other=jobId 匹配; lastError=None || 跨账号可读（200+严格投影）；契约未要求创建者过滤，可见性政策待总协调书面裁定 → INFO |
| RV-6 | 严格响应契约：selftest 10/10 + samples 48 + OpenAPI + 实时响应逐个严格校验 + 负例 rc=1 | **PASS** | validate_responses --selftest; validate_samples; openapi; validate_responses <captured>; 负例 / 0/1 | selftest=True samples=True oas=True captured=True negs=True neg-extra-message:rc=1 neg-illegal-enum:rc=1 neg-null-jobid:rc=1 neg-missing-retryable:rc=1 |
| RV-7 | 有界范围披露：decisions-notes.md 36 处路径外历史 nullable 属 A follow-up，本次不改契约（已在 summary 披露段列明） | **PASS** | grep decisions-notes.md nullable / 0 | 36 处路径外历史 nullable 不计入本次通过项；详见 summary 披露段 |
| RV-8 | 9 处诊断消费点复核：预写审查结论+片段定位存在性检查（非自动代码审查）（10 行，缺陷 0、残项 0） | **PASS** | 逐项定位当前 file:line/片段（实质判定依据=人工记录+oracle round-9 核验） / PASS | compliant=10 defects=0 residue=0 详见 n2-codereview-manual.md |
| RV-9 | 旧证据复用台账：未变部分（worker 运行时/迁移/其余端点）引用 26d97fb 正式验收证据，列明来源 SHA+范围，不计入本次新通过项 | **PASS** | 检查 A-baseline-2026-09-10 证据存在 + summary 台账段 / 0 | source_evidence=A-baseline-2026-09-10 exists=True |
| CLEANUP | 停进程并按 run 标签删除 mvp-e-pg | **PASS** | docker rm -f -v / 0 |  |
| CLEANUP-ports | 端口释放 | **PASS** | ss / 0 |  |

## 范围披露（RV-7）
A decisions-notes.md 的 36 处**路径外**历史 misplaced nullable 形属 A follow-up，不在本次复验范围；E 不自修契约，仅披露计数。echo-view 路径内 2 处已在 f6e500e 归零。

## 旧证据复用台账（RV-9）
- 引用来源：`evidence/A-baseline-2026-09-10/`（正式全量 52 项，A 候选 26d97fb）。
- 适用来源 SHA：26d97fb（A 基础）；本次 f6e500e 未改 worker-python 与迁移，故 worker 运行时（AB-02/AB-06d）、14 表迁移（AB-03）、约束/认证/T13/N1/N2-db/N3 等未变部分引用该证据，**不计入本次新通过项**。
- 本次仅新判定 RV-1..RV-9（见上表）。

## 附条件项（INFO）

- **RV-5** 认证/归属边界：无 token/伪造 401 通过；真跨账号读取的可见性政策待总协调裁定 → INFO（附条件）；no-token: 401/AUTH_REQUIRED | forged: 401/SESSION_INVALID | accounts_differ=True s1_valid=True s2_valid=True other=jobId 匹配; lastError=None || 跨账号可读（200+严格投影）；契约未要求创建者过滤，可见性政策待总协调书面裁定 → INFO

## A 缺陷清单

（本次定向复验无 FAIL）

## 人工复核附件
- `logs/n2-codereview-manual.md`（9 处逐项 current file:line+判定）
- `logs/rv-strict-*.log`、`logs/rv6-*.log`、`logs/responses/`（严格校验与负例）
