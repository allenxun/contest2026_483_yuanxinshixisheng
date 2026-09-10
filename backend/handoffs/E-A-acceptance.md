# E → A 基线独立验收报告（A-baseline 阶段）

- 日期：2026-09-10 · 执行：E 工作包（黑盒独立验收，非复跑 A 自测口径）
- 性质声明：全部结果基于 A 交付的**隔离测试替身**形态（InMemory 会话 / SMS 固定码 /
  DB 对照云台凭据 / 文件系统存储），语义为 `doubles_pass`；**不宣称真实供应商
  （短信/会话/人脸/OSS）、真实设备接入或生产就绪**。

## 基线绑定

| 对象 | SHA |
| --- | --- |
| A 候选代码（A oracle round-3 PASS-with-notes） | `26d97fbe908cb93c1fe366e28ba54a91c21b497c` |
| A 报告提交头 | `617354d0634c55b9420a3256c619186a1177b3c3` |
| 隔离 dev | `24232d3ccb203d50acfb6aed6b6e74e336654cb0` |
| 本工作树集成 HEAD（验收执行基线） | `df0fa32ee42310d8adfa779f215c8b7a8da80fc7` |
| **E 最终代码（oracle 第八轮 PASS）** | `85c2f338b1fcbf922fc9348bf84335f55318957a` |
| 证据刷新（协调者独立复跑，report-only） | `63763f2` |

## 环境与资源隔离

E 专用：PG 容器 `mvp-e-pg`@127.0.0.1:55433（postgres:16，run 标签归属、用毕删除）、
Java@18081、worker 健康@18082、venv `backend/acceptance/.venv-driver`、flock 单实例锁。
未触碰 mvp-a-pg/55432/5432(共享 pgvector18)/18080/8080；未执行 A 的
run-acceptance.sh 或 dev 固定端口脚本；未修改任何 A 源码/契约/迁移/构建。

## 入口命令与退出码（实施跑与协调者于 85c2f33 独立复跑两跑一致）

| 命令 | 退出码 | 结果 |
| --- | --- | --- |
| `backend/acceptance/run.sh selfcheck` | **0** | 45 passed（框架自检+矩阵完整性+门禁/驱动回归） |
| `backend/acceptance/run.sh matrix` | **3** | PASSED=45 DEPENDENCY_PENDING=94 FAILED=0；SETTLED=94/94（94 业务场景仍待 B/C/D，blocked_by=owner 包） |
| `backend/acceptance/run.sh a-baseline` | **1** | mode=formal，settled=52/52；**50 PASS / 1 FAIL / 0 BLOCKED / 1 INFO**；counts_sum=52、unknown=[] |

退出码语义：0=结算完整且无 FAIL 无 BLOCKED（INFO 附条件须显式披露）；1=有 FAIL
或 BLOCKED；4=结算不完整/未知状态。证据：`backend/acceptance/evidence/A-baseline-2026-09-10/`
（summary.md 逐项命令/退出码/摘录、results.json 哨兵、logs/）。

## 结果概览

- **AB-01..AB-11 全部通过**：构建/启动/健康检查/requestId；全新 E 库 Flyway V1+V2
  （14 表、版本 1,2）；重复启动（UP→SIGTERM→再启动→UP+Flyway no-op）；唯一/CHECK
  约束负例 8 项（双占用、双记录、控制端归属、active registration、T13 唯一、members
  部分唯一、状态/版本 CHECK）；认证拒绝全套（无 token/伪造/disabled/auth_revision
  递增/云台凭据轮换/旧 refresh 不可复活，独立会话+真实 accountId+行数断言+501→401
  转变证据）；Java→Python echo job（queued→succeeded，attempt=1 lease=1）；租约过期
  回收（lease_revision+1、owner 释放）；T13 幂等（重放同 jobId+meta.replayed、异文
  409 冲突）；跨语言一致（JCS 17 向量 selftest、样例校验、OpenAPI 校验）；结构化
  错误信封/错误码/requestId 头体一致。
- **AB-02d（转型，PASS）**：E 隔离环境定向 worker pytest（claim/renew/expire/
  complete/attempt-ceiling/unsupported，26 passed，DSN=mvp-e-pg E 专属库，未混 A 库）；
  全量 47 未重跑（避免重复无关单测，A 既有 47/47 为 A 提供证据、如实区分）。
- **AB-06d（转型，PASS）**：E 驱动内以真实 mvp_worker 公共运行时/仓储边界 + E 专属
  真实 PG + 受控测试回调验证：重试上限→failed RETRY_LIMIT_EXCEEDED、attempt=1、
  二次回收 no-op；陈旧代次→StaleGeneration 拒绝且哨兵行=0（业务写同事务回滚）。
  **标注：运行时边界集成验证，非 HTTP 链路**。
- **N1 JSONB 三层边界（PASS）**：DB CHECK 拒 array/null/字符串/bool/缺键（小数/负数
  DB 放行=已知限制如实记录）；Java 服务层 SchemaVersionBoundaryTest（targeted）；
  Python schema 直调 8 变体全拒 + 真实运行时坏版本 job→failed/UNSUPPORTED_CONTRACT。
- **N3 媒体与 fail-closed（PASS）**：默认 deny-all 任何媒体 GET 统一 404（face
  purpose、上传者本人均拒，无 403 泄露）；production 三变体（缺提供方/owner-dev/
  allow-any）启动均被拒且断言具体原因行；targeted ProductionFailClosedTest 通过。

## FAIL 1 项 = A 缺陷（交总协调处置，E 未修改 A）

**N2-http：`system.echo` GET 原样公开内部诊断列 `async_jobs.last_error`。**

- 现象：写入合成标记 `{"code":"E_DIAG_MARKER","message":"Bearer E2E_DIAG_SECRET_MARKER_12345"}`
  后 GET 返回 200 且 `data.lastError` **原样回显**（len=95）；写入 4000 字符超长诊断
  后投影 len=4058，**未脱敏、未限大小**。
- 违反：1fb07cd 数据架构五诊断列约定（仅诊断用途，须脱敏、限制大小、不向客户端
  原样返回）。
- 定位：`backend/web-java/src/main/java/cn/yuanxin/mvp/web/system/SystemEchoController.java:152-177`
  （`SELECT ... last_error::text` → `parseError(...)` → `EchoJobViewData.lastError`，
  无白名单/裁剪/脱敏）。
- 最小复现：`backend/acceptance/evidence/A-baseline-2026-09-10/logs/n2-http-repro.txt`
  （两变体完整可执行 SQL——重放需替换为当前有效 jobId；Bearer 用运行时测试会话；
  全部合成标记，无真实凭据）。
- Oracle 独立裁定（第六轮起维持）：**缺陷成立，为 A 基础验收 BLOCKER**；合成 marker
  非真实凭据泄露证据；已证实范围限 `system.echo` GET，不能据此断言未实现的 B/C/D
  端点同病，但该模式不得成为其接入范例。

## INFO 1 项（诚实降级，不计通过）

N2-codereview：诊断列 23 处消费点已按 file:line+片段+读/写+分类（业务决策/跨服务
协议/客户端投影/仅日志）机械检视，其中 **9 处待人工复核**——人工消费点复核未完成，
不构成第 51 个通过项；接受与否由总协调明确决定。

## E 侧 Oracle 门禁（本阶段第 5—8 轮，同一 oracle 会话）

f389078 BLOCKED（认证撤销假阳性/N2-http 硬编码/结算缺失等）→ 440516b BLOCKED
（假 PASS 路径/诊断模式证据隔离/锁竞态等）→ 707670a BLOCKED（BLOCKED 可宣称通过/
flock unlink/INFO 未计数）→ **85c2f33 PASS（E 代码 blockingFindings：无）**。
残留 1 SUGGESTION（非阻塞）：五场景回归实为"结论政策单元测试"称谓需修正，建议补
tmp_path 集成测试（settlement()→write_outputs()→summary 落盘断言）——**已排期至
A 修复后定向重验同轮**。详见 `backend/handoffs/E-oracle.md`。

## 结论与处置建议（最终决定权在总协调）

**A 基础验收：未通过**（结算完整 52/52，1 FAIL 待 A 修复；50 PASS 构成有效的
基础覆盖证据）。**暂不建议开放 B/C/D。**

建议路径：
1. 总协调交 A 修复诊断投影（停止原样暴露，或提供明确白名单的公开错误投影）及
   受影响契约表述。
2. E 绑定**新 A SHA** 定向重验：两类诊断样本、正常投影、认证与相关契约；其余未变
   证据可复用但须注明来源 SHA 与适用范围；不得以 PARTIAL 冒充新 SHA 全量验收。
3. INFO 残项（9 处人工复核）由 E 完成或总协调明确接受。
4. 94 业务场景维持 dependency_pending（blocked_by=B/C/D）：A 基线存在不代表业务
   场景可通过；开放 B/C/D 后按矩阵推进。
