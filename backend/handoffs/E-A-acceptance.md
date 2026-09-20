# E → A 基线独立验收报告（A-baseline 阶段）

> **2026-09-10 定向复验更新**：A 缺陷已在 f6e500e 修复并经 E 定向复验闭合
> （11/11 结算=10 PASS+1 INFO 待裁定，E 代码 oracle 第十一轮 PASS@1fb5a5f）。
> 本文前半部分为绑定 26d97fb 的历史轮记录；最新结论见文末
> 「定向复验（PARTIAL）——A f6e500e」节与「整体意见结构」。

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

## 结论与处置建议（历史——绑定 26d97fb，已被文末定向复验节取代）

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

---

## 定向复验（PARTIAL）——A f6e500e（2026-09-10，缺陷修复后闭合）

> 总协调已同步 A 修复：新 A 候选代码 `f6e500e474954781d3438188b6fdd389e61682e7`
> （修复链 bfd2dc3→1ba984e→f6e500e：封闭 reason 枚举
> {unsupported_contract,retry_limit_exceeded,handler_failed,internal}+retryable 布尔
> 有界投影、严格 OAS 3.0.3 nullable、OAS 转换器严格合规），A 报告 `cf390e1`、
> dev `f2755ab`、集成 HEAD `d495a7d`。本节为**定向复验（PARTIAL），非新 SHA 全量
> 52 项**；整体意见按下方"整体意见结构"由总协调形成。

### 基线绑定与 E 代码门禁

| 对象 | SHA |
| --- | --- |
| 新 A 候选代码（本次复验对象） | `f6e500e474954781d3438188b6fdd389e61682e7` |
| **E 最终可集成代码（oracle 第十一轮 PASS）** | `1fb5a5fbeb2b7a1f142c2a5f563be0d7f0b45048` |
| 证据刷新（协调者复跑，report-only） | `ded4034` |

E 侧 oracle 第九至十一轮（同一会话）：07617a4 BLOCKED（RV 目标 jobId 关联缺失、
RV-5"他主体"实为同账号、哨兵未绑定本次 run、报告/复核措辞超机器验证范围）→
修复→2a595cf PASS 附非阻塞警告（哨兵仍经共享指针选择、rv5 非 200 分支措辞）→
修复→**1fb5a5f PASS（blockingFindings：无）**。详见 `backend/handoffs/E-oracle.md`。

### 命令与退出码（实施跑 c54479dd 与协调者于 1fb5a5f 复跑 6a621528 双跑一致）

| 命令 | 退出码 | 结果 |
| --- | --- | --- |
| `backend/acceptance/run.sh selfcheck` | **0** | 51 passed（含哨兵/判定回归） |
| `backend/acceptance/run.sh matrix` | **3** | PASSED=51 DEPENDENCY_PENDING=94 FAILED=0；SETTLED=94/94 |
| `backend/acceptance/run.sh a-reverify` | **0** | settled=11/11：**10 PASS / 0 FAIL / 0 BLOCKED / 1 INFO（RV-5 待裁定）**；REVERIFY_SENTINEL_OK（RUN_ID 入口绑定一致、final_exit==驱动 rc） |

退出码语义同 a-baseline（0=结算完整且无 FAIL/BLOCKED，INFO 附条件须显式披露；
1=有 FAIL 或 BLOCKED；4=结算不完整/哨兵不符）。证据：
`backend/acceptance/evidence/A-reverify-2026-09-10/<RUN_ID>/`（6 个 run 目录，含
07617a4/2a595cf 中间轮；此前 A-baseline-2026-09-10 正式证据零覆盖）。

### 逐项结果（RV-1..RV-9）

- **RV-1 PASS** 从当前源码重建：`git diff f6e500e -- backend/web-java
  backend/worker-python backend/contracts` 为空、mvn 重建 jar（两跑同源各自重建、
  **非字节一致**，非可复现构建元数据如实记录）、`java -jar` 启动健康 UP，未用旧镜像。
- **RV-2/RV-3 PASS** N2-http 闭合：marker 变体与 4000 字符长变体种入（UPDATE
  RETURNING rowcount==1、GET 200、强制 **data.jobId==目标**）后，投影仅
  `{"reason":"internal","retryable":true}`；marker/原始 code/message/长内容全部
  缺席；枚举映射而非截断。**原 A 缺陷在 f6e500e 闭合**（oracle 第九至十一轮裁定维持）。
- **RV-4 PASS** 正常投影：queued→status=queued 且 lastError/finishedAt **显式存在
  且为 null**；未知 job_type→worker 失败→`{"reason":"unsupported_contract",
  "retryable":false}` 映射实测。
- **RV-5 INFO（待总协调书面裁定）** 认证/归属边界：无 token/伪造→401（基本错误
  信封检查，局限已注明）；**真实第二账号**（独立身份派生、accounts_differ 断言、
  两会话各自先验证有效）读取创建者 job→200+目标关联+严格投影校验，契约层断言
  全过。但跨账号可见性政策未经裁定：当前契约（openapi.yaml:1633-1649）未要求
  创建者过滤、实现为任意已认证主体可按 jobId 读取、GET SQL 未限定 job_type。
  E 不自行判"按契约"，记 INFO 附条件。
- **RV-6 PASS** 严格响应契约：`validate_responses.py --selftest` **10/10**（含旧/新
  nullable 形判别）、`validate_samples.py` **48 checks**、openapi_spec_validator OK、
  实时捕获响应（rv2/3/4/5）逐个严格校验通过、4 负例（+message 字段/非法枚举/
  非空位 null/缺 retryable）全部 rc=1 拒绝。经 E `.venv-driver` 运行，未建改 A venv。
- **RV-7 PASS** 有界范围披露：36 处路径外历史 nullable 属 A decisions-notes.md
  follow-up，不计入本次范围、未自修契约。
- **RV-8 PASS** 9 处诊断消费点人工复核闭合：共 10 行（9 残项+echo 新投影路径）
  **合规 9/9、缺陷 0、残项 0**；每行含当前 file:line+片段+使用方式分类+依据，并
  署名审核人/核验人（oracle 第九轮）/A SHA=f6e500e；依据已按 oracle 核验收窄
  （repository.py:13 返回 dict 且未发现生产调用方仅测试调用；MediaService.java:115
  本身无通用脱敏/限长机制、以当前调用链 MediaIntakeService.java:76-82 仅写错误码/
  固定文本为据）。rv8 机械检查如实标注"预写审查结论+片段定位存在性检查（非自动
  代码审查）"。oracle 第九轮独立核验（抽验 5 处+追读调用链）未发现新诊断公开缺陷。
- **RV-9** 旧证据复用台账：未变部分（worker 运行时、迁移、其余端点等）引用
  26d97fb 正式验收证据，注明来源 SHA 与适用范围，不计入本次新通过项。

### 整体意见结构（由总协调形成；E 不自行下整体结论）

1. 26d97fb 旧正式 52 项验收中适用的未变证据（RV-9 台账，注明来源与范围）；
2. 本节 f6e500e 定向闭合证据（原缺陷闭合+严格契约实测+9 处复核闭合）；
3. **RV-5 系统诊断可见性政策待总协调书面裁定**，裁定应覆盖：①是否允许已认证的
   其他账号读取系统诊断 job；②GET 是否应限定 `system.echo` 任务类型。若裁定要求
   创建者/类型过滤→交 A 实施、E 定向重验；若确认接受当前边界→可据组合证据放行。

### 建议与诚实声明

- **启动 B/C/D**：E 侧定向复验完成、原 A 缺陷闭合、证据结构齐备——**待 RV-5 裁定
  完成后即具备启动条件**（最终决定权总协调；oracle 明确：E 代码 PASS 不自动等于
  A 整体无条件通过，也不自动授权 B/C/D）。
- 94 业务场景仍 dependency_pending（blocked_by=B/C/D）；全部证据为测试替身形态
  doubles_pass，不宣称真实供应商/生产就绪；定向 PARTIAL 结果不冒充新 SHA 全量。

---

## RV-5 最终有界复验（PARTIAL）——A 561c338（2026-09-10/11 已执行；第十二→十三轮 oracle 审查：BLOCKED→修复→**PASS@cce3975**）

> 总协调已书面裁定 RV-5 并交付 A 最终实施：A 链 f6e500e→334a9c4（创建者归属
> 持久化+GET 仅创建者可见+统一 404）→199b2f6（POST dedup 创建者/类型事务内门槛+
> T13 rejected-replay）→**561c338**（POST '404' 声明+RESOURCE_NOT_VISIBLE 入错误
> 码表；A oracle round9 PASS-with-notes，blockingFindings=[]），A 报告 `5ae53b6`、
> dev `9b3e4a1`、集成 HEAD `e1d54b9`。本节为 **RV-5 有界复验（PARTIAL），非新
> SHA 全量验收**；整体意见按组合结构由总协调形成。

### 执行结果（最终 E 代码 cce3975；实施跑 e21ed79b 与协调者复跑 90dbb580 双跑一致）

| 命令 | 退出码 | 结果 |
| --- | --- | --- |
| `backend/acceptance/run.sh selfcheck` | **0** | 54 passed（含六类负例回归组） |
| `backend/acceptance/run.sh matrix` | **3** | PASSED=54 DEPENDENCY_PENDING=94 FAILED=0；SETTLED=94/94 |
| `backend/acceptance/run.sh a-rv5` | **0** | settled=10/10：**10 PASS / 0 FAIL / 0 BLOCKED / 0 INFO**；REVERIFY_SENTINEL_OK（RUN_ID 入口绑定、mode=rv5-reverify、final_exit==驱动 rc） |

（03b8dfb 的首轮双跑 89a36459/dd48513a 保留为历史证据；第十二轮判定其断言强度
不足【BLOCKER×2+MAJOR】，经 cce3975 加强后以上表为准；历史目录零覆盖。）

结论原文："**RV-5 有界复验（PARTIAL）结果：通过**——10 PASS / 0 FAIL / 0 BLOCKED。
组合意见：本次有限验证 + 历史适用证据（A-baseline 26d97fb / A-reverify f6e500e），
整体验收意见由总协调形成；本报告不输出全量通过或 A 基础验收结论。"

关键实测：RV5-1 从当前源码重建（git diff 561c338 空、jar 重建、健康 UP、未用旧
镜像）；RV5-2 创建者 GET 可见+泄漏点抽查回归（jobId 关联、封闭枚举投影、marker
缺席）；RV5-3 三态统一 404 不可区分（外来账号【真第二身份+accounts_differ】/非
echo 行/不存在 UUID→requestId 外 error 子树逐字节等值、RESOURCE_NOT_VISIBLE、无
owner/type 泄露）；RV5-4 未认证/伪造 401（基本信封检查，如实分类）；RV5-5 POST
dedup 碰撞六步（无键碰撞 404 且不投影外来 id/status/payload/owner/type、keyed#1
404+T13 rejected|RESOURCE_NOT_VISIBLE SQL 查证、同键重放同一拒绝边界、原 A 行全
字段快照一致、碰撞零 B 属行、同主体正例同 jobId 成功语义保留）；RV5-6 有界严格
契约（selftest 10/10、samples 50 checks、OAS VALID、200 捕获体严格 schema、404/401
如实标注基本信封）；RV5-7 已接受 availability-oracle 限制披露（碰撞 404 vs 新键
200 仅揭示 dedup 键不可用；不扩展实现、不宣称生产完备）；RV5-8 历史台账零变更+
SHA 适用范围（f6e500e..561c338 消费点文件未变→9 处复核台账仍适用）。

### 审查状态（第十二→十三轮，诚实披露）

- 2026-09-10 两次第十二轮调用因 oracle 用量限制失败，按门禁规则记 BLOCKED 不视为
  通过（interim 披露提交 fb2fc08）。配额恢复后经新授权单次正式调用：**第十二轮审
  03b8dfb = BLOCKED**（BLOCKER：三态比较只留 error 子树且非 echo 种子未验证、
  keyed 碰撞/重放未验完整拒绝边界；MAJOR：快照非全字段；MINOR：samples 提取；
  **A 实现本身未发现新缺陷**）。
- 修复（cce3975：canon_public 仅排除 requestId 的完整公开体规范化等值、三态禁止
  内容扫描、种子 INSERT RETURNING+回查、四体统一拒绝边界+重放后 T13 复验、
  SELECT * 全字段快照+worker 未运行窗口、六类负例回归）后，**第十三轮终审 =
  E 代码 PASS（blockingFindings：无）**；原 RV-5 INFO 残项解除。
  reviewedCommit=`cce397560ef32e13c724c920757b479e829f659b`。
- 证据目录：`evidence/A-rv5-2026-09-10-561c338/`（4 run：历史 89a36459/dd48513a +
  最终 e21ed79b/90dbb580）；既有 A-baseline 与 A-reverify 全部历史证据零覆盖。

### 最终组合 A 基础验收结论（供总协调采用；最终放行权在总协调）

三部分组合证据齐备：
1. **26d97fb 旧正式 52 项基础验收中适用的未变证据**（RV-9/RV5-8 台账：注明来源
   SHA 与适用范围；该轮唯一 1 FAIL 已由下两项闭合）；
2. **f6e500e 诊断泄漏闭合**（N2-http 定向复验 10 PASS+1 INFO + 9 处消费点人工
   复核闭合）；
3. **561c338 RV-5 闭合**（本节 10/10 PASS：创建者归属、三态统一 404 不可区分、
   POST dedup 碰撞拒绝+T13 rejected-replay、泄漏点抽查回归）。

**E 侧建议：已具备启动 B/C/D 的条件**（是否放行由总协调决定）。放行记录保留
非阻塞限制：全局 dedup availability-oracle（碰撞 404 vs 新键 200 仅揭示键不可用；
已接受）、36 处路径外历史 nullable（A follow-up）、旧镜像部署前须从当前源码重建、
doubles_pass 替身形态不代表真实供应商/生产就绪、94 业务场景仍 dependency_pending
随 B/C/D 实现继续验收。
