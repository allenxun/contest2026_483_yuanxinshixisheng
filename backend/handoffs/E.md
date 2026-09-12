# E 工作包交接（backend/acceptance）

分支 `feature/mvp-acceptance`。本包为纯黑盒验收框架（HTTP 驱动），无任何业务实现。
本文件由 E 于 2026-09-10 生成。本包实施产物已由本包本地提交（实施提交 `cea01f7`，
含 backend/acceptance 全部产物与本交接文档）；集成合入由总协调负责，本包不推送远端。

## 产物清单

- `backend/acceptance/README.md` —— 目的、状态语义、运行命令、诚实声明
- `backend/acceptance/run.sh` / `requirements.txt` / `.gitignore` / `pytest.ini` / `conftest.py`
- `config/baseline.json`（已记录 A 候选/报告/隔离 dev/集成 SHA 与 e_acceptance 状态；
  `gate` 保持 `closed`——业务场景由 B/C/D 阻塞）、`config/acceptance.env.example`
- `matrix/scenarios.json`（94）、`matrix/apis.json`（27）、`matrix/generate_matrix.py`（文档→JSON 再生成）
- `framework/`：`conftest.py`（插件：markers 注册、dependency_pending 统计、
  matrix 退出码 3/4 双层结算守卫【插件结算 + run.sh 拒绝外部 `PYTEST_ADDOPTS` 并校验
  结算哨兵 `reports/<RUN_ID>/settlement.json`】、pass-requires-evidence【sc_id 节点
  passed 必须有证据并 seal，否则改判 fail】）、
  `gate.py`、`client.py`（证据落盘统一在 `EvidenceRecorder.record` 边界无条件脱敏
  Authorization/Cookie/Proxy-Authorization/X-Api-Key）、`isolation.py`、`doubles.py`
- `tests/test_matrix_integrity.py`、`tests/test_framework_selfcheck.py`、
  `tests/scenarios/test_sc00.py..test_sc07.py,test_scc.py,test_scr.py`（94 节点，名称含场景 ID）
- `plans/A-baseline-plan.md`（AB-01..AB-11）、`plans/isolation-and-doubles.md`
- `driver/`（A 基线验收参数化驱动：`a_baseline.py`/`infra.py`/`seed_ab04.sql`；
  E 专用 mvp-e-pg@55433、Java@18081、worker@18082；flock 常驻锁、run 标签归属清理、
  模式化输出目录【诊断→reports/，正式→evidence/】、52 项完整结算哨兵；
  `a_reverify.py` 定向复验 RV-1..RV-9【11 项结算】、`a_rv5.py` RV-5 最终有界
  复验 RV5-1..RV5-8【10 项结算】、`verify_reverify_sentinel.py` RUN_ID 入口绑定
  哨兵【mode/expected 参数化：run_id/mode/settled/计数和/final_exit==驱动 rc，
  不符→4】）
- `evidence/A-baseline-2026-09-10/`（summary.md 逐项证据、results.json 哨兵、
  logs/ 摘录与 A 缺陷可执行复现）
- `evidence/A-reverify-2026-09-10/`（6 个 run 目录：定向复验证据，含
  n2-codereview-manual.md 人工复核 10 行、捕获响应与负例；旧正式证据零覆盖）
- `evidence/A-rv5-2026-09-10-561c338/`（4 个 run 目录：RV-5 最终有界复验证据，
  含捕获响应、披露核对、双跑最终结算）
- `backend/handoffs/E-A-acceptance.md`（A 基线独立验收报告：26d97fb 历史轮【未通过】
  + f6e500e 定向复验闭合节 + 整体意见结构与 RV-5 裁定请求）

## 矩阵统计（逐行提取，与文档声明核对）

- 总数 **94**；**P0=69、P1=25，与清单声明一致**（自检断言核对文档原句）。
- 分节：SC-00×4、SC-01×18、SC-02×11、SC-03×9、SC-04×10、SC-05×7、SC-06×9、
  SC-07×7、SC-C×5、SC-R×14。
- 范围：后端 49（现在可自动）、集成 12（需替身）、联调 33（需真实设备或APP）。
- API：27 个全部有场景回链；SC-C-01 按"全部 27 个 API"展开，与文档覆盖汇总表
  交叉核对一致（该表未展开 SC-C-01，本矩阵已展开并在测试中注明）。
- 包归属（总协调 2026-09-10 权威澄清修正，早期版本 M3→C/M4→D 为负责人归属错误）：
  M1/M2/M5→B、M3→D、M4 执行/记账(A03..A09)→C、M4 方案生成(A01/A02)→D，
  跨包场景多归属（owner=关联 API 归属并集）。修正后分布：B×28、B,C×2、B,C,D×7、
  B,D×3、C×26、C,D×7、D×21（总数 94，非 owner 字段逐字节未变）。
  全部场景 blocked_by=归属 B/C/D 业务包（A 基线已于 2026-09-10 交付；pending_reason
  同步为"业务实现未集成、端点 501 stub"）。

## 自检命令与退出码（2026-09-10 实际执行）

> 下表为首轮实施的历史记录（当时自检 24 项、无守卫）；后续各轮的守卫与实测见
> "dependency_pending 语义→守卫补强"下的复核轮/二复审修复轮表。

| 命令 | 退出码 | 结果 |
| --- | --- | --- |
| `python3 -m venv backend/acceptance/.venv && backend/acceptance/.venv/bin/pip install -r backend/acceptance/requirements.txt`（工作树根执行） | 0 | pytest 9.1.1 / requests 2.34.2 |
| `backend/acceptance/run.sh selfcheck` | **0** | 24 passed（矩阵完整性 + 框架自检） |
| `backend/acceptance/run.sh matrix` | **3** | `PASSED=24 DEPENDENCY_PENDING=94 FAILED=0`，collected 118 |

## dependency_pending 语义

gate=closed 时 94 个场景节点以 skip 抛出、reason 固定前缀 `dependency_pending: `，
插件将其与普通 skipped 分开统计；matrix 存在 pending 时最终退出码固定 3，**绝不 0**。
gate 打开后未编写步骤的节点会直接 fail（防"开闸空跑冒充通过"）。

### 守卫补强（同日 Oracle 审查后，历史表格保留当时事实不改写）

- **退出码 4（结算不完整）**：matrix 模式由插件从 `matrix/scenarios.json` 加载 94 个
  sc_id 作为必须结算集合，逐一唯一结算（passed/dependency_pending/failed）；缺失、
  `--ignore`/`-m` deselect、重复异常或 SKIPPED_OTHER>0 → 退出码 4。初版曾声称
  "PYTEST_ADDOPTS 无法绕过"，复审证伪（`-p no:framework.conftest` 可禁用插件产生假 0）；
  现已改为双层事实：**run.sh 为唯一验收入口**，检测外部 `PYTEST_ADDOPTS` 即拒绝并
  exit 4；插件 session 结束写哨兵 `reports/<RUN_ID>/settlement.json`，run.sh 校验
  哨兵存在/RUN_ID/mode/结算 94/计数一致，缺失或不匹配强制 4。直调 pytest 时插件守卫
  仍生效（有回归用例），但裸调 pytest 不被承认为验收结果。
- **passed 绑定证据**：带 sc_id 的节点 call 阶段 passed 时，必须已经
  `scenario_evidence` 夹具记录 ≥1 条 HTTP 证据并 `seal()` 替身声明，否则插件改判
  fail（"pass without evidence"）；汇总行输出
  `EVIDENCE_TAGS no_externals/doubles_pass/mixed/real_pass` 分类计数。当前
  gate=closed 全 pending，此机制不影响 94 pending，已由 subprocess 自检证明生效。
- **证据脱敏**：凭据遮蔽收敛在共同落盘边界 `EvidenceRecorder.record()`——
  Authorization/Cookie/Proxy-Authorization/X-Api-Key 一律替换 `***REDACTED***`
  （默认项不可被调用方移除，`record_raw` 等旁路同样覆盖），
  并有自检断言证据文件不含 token 值。
- **A 计划补齐**：`plans/A-baseline-plan.md` 增加 AB-01/AB-02 运行并记录 A 交付的
  Java/Python 测试命令与退出码、新增 AB-11 结构化错误响应契约与 requestId 关联验证。

复核轮实际执行（2026-09-10，基线 93363ee 之上；下表属历史轮次事实，后续修复见"守卫补强"与二复审表）：

| 命令 | 退出码 | 关键输出 |
| --- | --- | --- |
| oracle 复现（`PYTEST_ADDOPTS='… --ignore=tests/scenarios' ./run.sh matrix`） | **4** | collected 30；`SETTLEMENT_INCOMPLETE: 未结算场景 94 个`；DEPENDENCY_PENDING=0 |
| `run.sh selfcheck` | **0** | 30 passed（24 原有 + 6 守卫/脱敏/证据回归） |
| `run.sh matrix` | **3** | collected 124；`PASSED=30 DEPENDENCY_PENDING=94 FAILED=0`；`SETTLED=94/94 SETTLEMENT_OK` |
| `md5sum matrix/scenarios.json` | 0 | `8d2c4e41…` 与修复前一致（94 条数据未动） |

二复审修复轮实际执行（2026-09-10，基线 6b0a234 之上）：

| 命令 | 退出码 | 关键输出 |
| --- | --- | --- |
| oracle 绕过复现（`PYTEST_ADDOPTS='-p no:framework.conftest -o addopts= --ignore=tests/test_framework_selfcheck.py --ignore=tests/test_matrix_integrity.py' ./run.sh matrix`） | **4** | 入口拒绝外部 PYTEST_ADDOPTS 注入，未进入 pytest |
| 一轮 oracle 复现（`--ignore=tests/scenarios` 变体） | **4** | 同上（初版该路径经插件被绕过的假 0 已封死） |
| `run.sh selfcheck` | **0** | 33 passed（新增入口拒绝、哨兵、record_raw 脱敏回归等） |
| `run.sh matrix` | **3** | collected 127；`PASSED=33 DEPENDENCY_PENDING=94 FAILED=0 SKIPPED_OTHER=0`；`SETTLED=94/94 SETTLEMENT_OK`；哨兵 `reports/<RUN_ID>/settlement.json` 存在且 settled_unique=94、counts 与汇总一致 |
| `md5sum matrix/scenarios.json` | 0 | `8d2c4e41…` 仍与最初提取一致 |

## A 基线验收（2026-09-10 已执行，历史——绑定 26d97fb：未通过，A 已修复 f6e500e 并经定向复验闭合，见下节）

A 基线已由总协调同步（集成 df0fa32、A 代码 26d97fb、A oracle round-3
PASS-with-notes）。E 以参数化驱动 `run.sh a-baseline` 执行独立验收（E 专用资源：
mvp-e-pg@55433/Java@18081/worker@18082；未修改 A 源码；未执行 A 固定端口脚本；
实施跑与协调者独立复跑两跑一致）：

| 命令 | 退出码 | 结果 |
| --- | --- | --- |
| `backend/acceptance/run.sh selfcheck` | **0** | 45 passed |
| `backend/acceptance/run.sh matrix` | **3** | PASSED=45 DEPENDENCY_PENDING=94 FAILED=0；SETTLED=94/94 |
| `backend/acceptance/run.sh a-baseline` | **1** | formal settled=52/52：**50 PASS / 1 FAIL / 0 BLOCKED / 1 INFO** |

- **FAIL 1 项 = A 缺陷**：`system.echo` GET 原样公开 `async_jobs.last_error`
  （未脱敏、未限大小），违反 1fb07cd 五诊断列约定；定位与最小可执行复现见
  `backend/handoffs/E-A-acceptance.md`。处置权在总协调（交 A 修复），E 未修改 A。
- INFO 1 项：N2-codereview 23 处消费点中 9 处待人工复核（诚实降级，不计通过）。
- AB-01..AB-11 全部通过（AB-02d/AB-06d 按总协调纠偏转型为真实验证：E 隔离定向
  worker pytest 26 passed；真实 mvp_worker 运行时边界验证重试上限与陈旧代次
  同事务回滚，标注非 HTTP 链路）。全部结果为测试替身形态 doubles_pass。
- E 侧 oracle 门禁第五至八轮：f389078/440516b/707670a BLOCKED → 逐项修复 →
  **85c2f33 PASS**（E 侧 blockingFindings 无；详见 `backend/handoffs/E-oracle.md`）。

## 定向复验（PARTIAL，2026-09-10 已执行——通过（附条件））

A 修复已同步（新 A 代码 f6e500e、报告 cf390e1、dev f2755ab、集成 d495a7d）。
E 以 `run.sh a-reverify` 执行定向复验（RV-1..RV-9+CLEANUP=11 项，独立 RUN_ID
入口绑定与证据目录，旧正式证据零覆盖；实施跑与协调者复跑双跑一致）：

| 命令 | 退出码 | 结果 |
| --- | --- | --- |
| `backend/acceptance/run.sh selfcheck` | **0** | 51 passed |
| `backend/acceptance/run.sh a-reverify` | **0** | settled=11/11：**10 PASS / 0 FAIL / 0 BLOCKED / 1 INFO（RV-5 待裁定）** |

- 原 A 缺陷（system.echo 原样公开 last_error）在 f6e500e **闭合**：投影仅封闭
  reason 枚举+retryable，marker/长内容/原始 code 均不外泄（RV-2/3/4 实测，强制
  目标 jobId 关联）；严格响应契约 RV-6 实测（selftest 10/10、48 样例、4 负例 rc=1）。
- INFO 1 项 = RV-5 系统诊断资源**跨账号可见性政策待总协调书面裁定**（含 GET 是否
  应限定 system.echo 任务类型）；若裁定须过滤→交 A 实施、E 定向重验。
- 第八轮遗留全部同轮完成：tmp_path 集成测试、"端到端"称谓修正、INFO 9 处人工
  复核（9/9 合规、缺陷 0、残项 0，oracle 第九轮独立核验）。
- 详情与整体意见结构见 `backend/handoffs/E-A-acceptance.md` 定向复验节。

## RV-5 最终有界复验（2026-09-11 已执行——通过，第十三轮 oracle 终审 PASS@cce3975）

总协调已书面裁定 RV-5 并由 A 实施（链 334a9c4→199b2f6→**561c338**，A oracle r9
PASS-with-notes）；E 以 `run.sh a-rv5` 执行有界复验（RV5-1..RV5-8+CLEANUP=10 项，
独立证据目录 4 run 含历史；实施跑与协调者复跑双跑一致）：selfcheck exit=0
（54 passed）、a-rv5 exit=0（settled 10/10=10 PASS/0 FAIL/0 BLOCKED/0 INFO）。
RV-5 裁定语义实测闭合：创建者 GET 可见、三态统一 404 不可区分（完整公开体仅排除
requestId 逐字节等值+禁止内容扫描+种子回查）、POST dedup 碰撞四体统一拒绝边界+
T13 rejected-replay+全字段快照不变+同主体正例保留；原 INFO 残项解除。详情与最终
组合结论见 `backend/handoffs/E-A-acceptance.md` RV-5 节。

## 待总协调决定后的执行流程

1. 总协调按组合证据（26d97fb 旧台账适用证据 + f6e500e 泄漏闭合 + 561c338 RV-5
   闭合）形成 A 基础验收整体结论，并决定是否启动 B/C/D（E 侧建议：已具备条件；
   最终放行权总协调，E 不自动启动 B/C/D）。
2. B/C/D 集成后开闸（gate=open），按矩阵补写并运行场景步骤（P0 优先），证据严格
   区分 `doubles_pass` / `real_pass`（见 `plans/isolation-and-doubles.md`）。

## 状态

- blocker：**无（E 侧）**——C/M4 与 C+D 集成链路验收完成并经第十九轮 oracle 终审
  PASS_WITH_WARNINGS（E 代码最终 **edbc7c1**，blockingFindings 无）；C/D 产品
  代码未发现缺陷；94 业务场景 dependency_pending（blocked_by：[]×54=C/D 已集成
  待场景级步骤编写 / B×40=B 未集成）。
- nextAction：**waiting_dependency**（总协调裁定：①13 处 OAS 契约建模缺陷
  【接受为已知限制或交 A 修约+定向重验 CC-11】②C 三项协调请求 ③C+D 集成验收
  整体判断与 B 启动——最终放行权总协调，E 不自动启动；B 集成后按矩阵补场景级
  步骤继续验收）。
- 未修改 `backend/doc/**`、A/B/C/D 源码/契约/迁移/构建配置；未访问兄弟工作树；
  E 专用资源（mvp-e-pg@55433/18081/18082）已清理，未触碰 B/D 容器与 5432；
  临时输出限 E 路径（reports/，未用 /tmp/opencode）；JVM 限堆 640m。
- 提交状态：本包已本地提交（实施 cea01f7 → … → cce3975【R13 PASS】→
  fd18bd4/0f77b65【R14】→ aebccc7【授权 merge C+D】→ 2600825/f90bab2【R15】→
  845dca0【R16】→ 2fcb520【R17】→ 098d877【R18】→ **edbc7c1**【R19
  PASS_WITH_WARNINGS】+ 证据刷新 …/66bf6a9 及报告提交），由总协调负责集成，
  未推送远端。
- E 代码经 oracle 第十九轮终审 PASS_WITH_WARNINGS（reviewedCommit `edbc7c1`，
  blockingFindings 无）；全部结果为测试替身形态（doubles_pass），不构成业务
  验收通过或真实供应商接入声明；PARTIAL/test_seed 不冒充跨包真实链路或全量。

## C/M4 与 C+D 集成链路验收（2026-09-11 已执行——第十九轮 oracle 终审 PASS_WITH_WARNINGS@edbc7c1）

总协调已交付 C 候选（8b3592e@93b7e33，C oracle R3 PASS-with-notes）并增量授权
merge C+D 集成隔离 dev `8afd0e5`（D=dc955c0，D oracle R1 M3 PASS/R2 M4
PASS-with-notes；merge 无冲突，care/contracts diff=0，E 未改任何业务代码）。
E 新增两个独立黑盒验收驱动：

| 命令 | 退出码 | 结果 |
| --- | --- | --- |
| `backend/acceptance/run.sh selfcheck` | **0** | 75 passed（集成轮 batch1） |
| `backend/acceptance/run.sh c-acceptance` | **0** | settled 14/14=13 PASS+1 INFO（CC-11 契约披露）；双跑一致 28c4994f（实施）/15ad40d0（协调者@edbc7c1） |
| `backend/acceptance/run.sh cd-chain` | **0** | settled 10/10 全 PASS；双跑一致 73a69cce（实施）/39d01667（协调者@2fcb520；cd_chain.py 此后零改动，R19 核定复用） |

- C/M4（CC-01..12）：生产人脸 fail-closed 四变体（含 prod,dev 混合）+正例判别、
  成员绑定、嵌套白名单 SENSITIVE_PLAN 五面+T07 快照、能力 9-token 严格
  fail-closed 22 变体、权限统一 404 三态、幂等重放双字段不刷新、并发占用恰一、
  K/去重/回滚/收尾水位/迟到留痕、9 API 成功响应严格 OAS 校验（结构化未知字段
  集合计算，杜绝引号字符绕过）。
- C+D 真实链路（CD-01..08）：真实 M3-A01 受理→worker→T06 唯一创建→
  plan.generate→ready 冻结字段精确基线→C 准入消费（T07 SQL 关联）→真实指针
  替换 TASK_REPLACED；D 公共 success/defer/failure 黑盒回归（本链三 job 逐个
  绑定+RUN_ID 窗口）；B 域 11 占位 501 实测如实。
- Oracle 第十四至十九轮门禁：fd18bd4/f90bab2/845dca0/2fcb520/098d877 五轮
  BLOCKED（均为 E 驱动断言强度/绑定/分类器缺陷，C/D 产品零缺陷裁定）→逐项
  修复→**edbc7c1 第十九轮 PASS_WITH_WARNINGS（blockingFindings 无）**。
- **待总协调裁定**：①13 处共享 OpenAPI 建模缺陷（12 处 nullable over
  $ref/allOf+1 处 allOf/additionalProperties 误伤；归属契约/A；接受为已知限制
  或交 A 修约+定向重验 CC-11；裁定前不视为公共契约通过）；②C 三项协调请求
  （CareFaceVerifier 公共端口/方案白名单批准/能力形状冻结）。
- 全程 doubles_pass；B 前置（成员/授权/设备）为 test_seed≠跨包真实链路；B 未
  集成（11 占位 501、媒体 deny-all 待 B）；矩阵 blocked_by 更新 []×54/B×40
  （三字段剔除哈希 e4f5dc52 不变，gate closed）；不声称完整 MVP 通过。详见
  `E-C-acceptance.md` 与 `E-CD-acceptance.md`。

## 准备阶段：94 场景证据映射（2026-09-11）

> 总协调增量授权，**非验收执行**、不启动任何测试服务；基线尚待 B 文档范围修复与 Oracle 复审。
> 产物：`backend/acceptance/plans/scenario-evidence-mapping.md`（主）+ `.json`（同源结构化，94 条）。
> 当前树 HEAD=`fabd55d`；全部旧证据仅标「复用候选」，须在最终集成树验证适用性后方可采信；**不声称验收通过**。

- **映射覆盖**：94/94 逐条；**复用候选 66 条**（C 断面 CC-01..CC-12 / CD 链路断面 CD-01..CD-08 / A 基础设施断面）、
  **无证据 28 条**（全部 B-only 归属 M1/M2/M5）；33 设备APP 项已拆出后端可先验子步骤（真实联调仍待办）。
- **分组核对**：总协调给定 49 后端可自动/12 替身/33 设备APP ↔ 矩阵 scope 后端 49/集成 12/联调 33、
  automation_tier 49/12/33 —— **计数完全一致，0 实质差异**；94 SC-ID 与清单原文一一对应（doc-only=0/matrix-only=0），
  priority P0=69/P1=25 逐行一致。**唯一差异（形式）**：SC-C-01 清单 apis 写「全部 27 个 API」，矩阵展开为 27 ID，语义一致。
- **缺口清单**：①B 未集成——M1/M2/M5 共 11 端点 501、真实授权/撤销、设备凭据、媒体访问策略待 B；
  ②D 待接线——`media.cleanup` 周期触发/崩溃孤儿扫描；③真实设备/APP 端到端（33 项）；④真实算法/OSS/大模型供应商；
  ⑤13 处 OAS 契约建模缺陷待裁定。
- **三项已知待修**：①scanner 周期（media.cleanup，`D.md:23`+E-CD D 待接线节）；②logout 通知代次——树内检索
  **无「通知代次」专门记载**，仅 A 包 dev/test 替身 `refresh/logout` 竞态保留（`A.md:90`、`A-oracle.md:155`，
  与 SC-01-17 非同一语义）→ 记「总协调指定、树内暂无对应文档定位，待 B 文档范围修复基线」；③OAS 13 字段（见 E-C 限制节，待裁定）。
- **被动资源核查（只读确认，未操作）**：E 端口 55433/18081/18082 **未监听（空闲）**；`docker ps -a` **无 `mvp-e-pg`**
  （仅见 `mvp-a/b/c/d-pg`，未触碰）；`backend/acceptance/.venv` 与 `.venv-driver` 均存在；按指令保留的**原服务 41985
  LISTEN 未触碰**；B PG 55435 与用户 Swagger 18080、共享 5432 存在但仅只读 ss 确认，未解读未操作。
- **待基线声明**：待总协调最终代码基线（含 B 文档范围修复）冻结后，以本映射作**增量接续**集成验收——
  **不从头重派、不重做 A 门禁**；届时 E 验收代码如有变更，仍须真实 Oracle 审最终 SHA。

## 集成基线首轮真实场景级实测（batch 1，2026-09-12）

> 基线 approved `f045433` / E merge HEAD **`08404f8`**（B `f95037e`【R5/R6】+ C `8b3592e`【R3】+ D `dc955c0`【R1/R2】+ Swagger `d3dc853`【报告 `551f166`】）。
> gate=open；矩阵从 dependency_pending 推进到真实场景级实测。**不声称完整 MVP 通过**；全部 doubles_pass / 后端步骤上限。
> 精简版见 `backend/acceptance/reports/first-round-integration.md`（reports/ gitignored）。

- **plumbing**：`staged_pending` 第三态（gate=open：已编写→真实结算；显式 staged→dependency_pending；未编写未标记→FAIL 不弱化）；
  设备APP 节点执行后端子步骤后结算 device_pending；`framework/live.py` 活体 session 夹具（HEAD SHA 打戳重建 jar、PG/Java 回收、证据 `evidence/Integration-<date>-<shortSHA>/<RUN_ID>/scenarios/<SC-ID>/`）；矩阵 `blocked_by` 全部 `[]`（B/C/D 集成）。
- **矩阵维护**：`blocked_by=[]×94`；剔除 blocked_by/pending_reason/staged_* 后业务语义哈希 **`86bfa7b721b6f285` 与变更前一致**；再生成幂等。
- **首轮活体矩阵**：RUN_ID=`E-20260911T134511Z-f15497bb`，**settled 94/94**，counts PASSED=88 / DEPENDENCY_PENDING=81 / FAILED=0，exit=**3**；EVIDENCE_TAGS doubles_pass=13。
  13 活体场景 = SC-01-03/04/05/06/09/10/12（B HTTP+SQL）+ SC-05-01/02/03/04/05/07（M1 授权/C 侧撤销 404）；12 设备APP 后端子步骤已验、真实联调待办；69 staged。
- **c-acceptance 集成树重跑**：RUN_ID=`E-AB-20260911T134713Z-47c79fbd`，settled 14/14，{PASS:13,INFO:1}，exit=0；CC-01 改为仅断言 **C care 代码 diff=0**（契约面 B 错误码补丁单独记录）。
- **待修/披露**：C8 scanner 周期未接线（须手动 `python -m mvp_worker.scanners --once`，SC-01-15/16/18 已照此并在证据标注）；#8 A 登出未递增 destination_revision（SC-01-17 只断言投递取消语义）；OAS 13 字段沿用 CC-11 allowlist 披露。**上述三项总协调已指定 B 唯一修复，当前树未修，待新修复基线后差异复验**（措辞更新于 lane A1）。
- **缺陷**：无业务缺陷；驱动侧修正 5 项（陈旧 jar→SHA 戳重建、M1-A01 multipart 必须文件段、登录 phone 派生碰撞、CC-01 契约适用性、selfcheck 嵌套守卫触发活体）。
- **边界**：仅 `backend/acceptance/**`+`handoffs/E*.md`；未改业务/契约/迁移/站点；E 资源用毕清理；历史证据零覆盖；未 commit。
- **status**：矩阵执行中（batch 1）——13 通过 + 12 设备待联调 + 69 staged；nextAction=继续 batch 2 场景步骤编写（并按裁定处理 C8/#8/OAS13）。

## 集成基线 lane A1（batch 2）：SC-02 测肤任务/补拍/归档（2026-09-12）

> 基线同 batch1（HEAD `cbbec46`）；复用 batch1 plumbing（staged 三态、framework/live.py 活体夹具）。
> 精简版见 `backend/acceptance/reports/first-round-integration.md`「Lane A1」节（reports/ gitignored）。

- **11 节点结果（failed 0）**：**passed 7**（SC-02-01/02/03/04/07/10/11 真实 M3 云台链 + worker `--once` + SQL 侧证）；
  **pending 4（seam 缺口，如实披露，非业务缺陷）**：SC-02-05/06/08/09——D `build_face_port/build_skin_port`
  恒用 `FaceDouble()/SkinDouble()` 默认参数，**未提供 env 故障注入 seam**，无法黑盒产生
  `quality=needs_retake`/`same_person=false`/`search=uncertain`；补拍 A02 仅在该态合法。
  已编写**可达安全边界断言**并通过（05/06 不冒充报告/不误建档；08/09 非补拍态 A02 被拒且状态不变），
  正例待 **D/总协调补注入 seam** 后补写。
- **驱动侧修正 4 项**：A02 必须 **PUT**（原 POST→405）；报告在 T05 `skin_assessments`（`report_id`/`report_payload`，非 `skin_reports` 表）；幂等重放须 metadata 完全一致（`captureSessionId` 固定）；worker 轮次调至 140 排空队列。
- **lane A1 正式 matrix**：RUN_ID=`E-20260912T073913Z-7d0e7b49`，settled **94/94**，counts PASSED=95 / DEPENDENCY_PENDING=74 / FAILED=0，exit=**3**，doubles_pass=20。
- **scenarios.json**：SC-02 11 条 flipped authored；业务语义哈希 **`86bfa7b721b6f285` 不变**、`blocked_by=[]×94`、再生成幂等；authored 36 / staged 58。
- **selfcheck** rc=0（75，零回归）。
- **披露措辞更新**：C8 scanner/#8 logout 代次/OAS 13 字段——**总协调已指定 B 唯一修复，当前树未修**；E 维持如实披露，待新修复基线后差异复验。
- **清理**：`docker stop mvp-e-pg`（**保留卷**，未 rm）；E 端口空闲、无 E JVM/worker、锁释放（文件保留）。
- **status**：矩阵执行中——20 通过（13+7）+ 12 设备 + 58 staged + 4 seam-pending；nextAction=等 D 注入 seam 补 05/06/08/09 正例，及新基线后差异复验。

## 集成基线 lane A2（batch 2）：SC-03 报告/方案生成与两端视图（2026-09-12）

> 基线 HEAD `1cd87d8`（lane A1 已提交）；复用全部 plumbing 与 M3/M4/M2 链经验。

- **9 节点结果（failed 0）**：**passed 8**（SC-03-01 报告成员隔离/02 APP full vs 云台 brief/03 报告就绪方案 waiting_inputs 不阻塞/04 真实 B M2-A04 观察补齐→plan.generate ready 且同版本不重生成/05 伪造证明 403 不篡改归属/06 M2-A05 能力读取范围/08 APP 方案 vs 云台 403/09 重复 GET 零副作用 SQL 前后全等）；
  **pending 1（seam 缺口，如实披露）**：SC-03-07——`PLAN_SNAPSHOT_INVALID` 失败/非法方案已实测（malformed baseline 全链→T06 failed、ready_rows=0），**超时子形态无注入 seam** 待 D 补。
- **lane A2 正式 matrix**：RUN_ID=`E-20260912T081619Z-93ef0046`，settled **94/94**，counts PASSED=**103** / DEPENDENCY_PENDING=**66** / FAILED=0，exit=**3**，doubles_pass=28。
- **scenarios.json**：SC-03 9 条 flipped authored；哈希 **`86bfa7b721b6f285` 不变**、`blocked_by=[]×94`、再生成幂等；authored 45 / staged 49。
- **驱动侧修正 3**：DOUBLE_KINDS 增 `skin_algo`；M2-A04 `revision` 须 BigintString；M2-A05 字段名 `capabilityRevision`。
- **selfcheck** rc=0（75，零回归）。
- **清理**：`docker stop mvp-e-pg`（**保留卷**）；E 端口空闲、无 E JVM/worker、锁释放（文件保留）。
- **status**：矩阵执行中——**28 通过**（13+7+8）+ 12 设备 + 49 staged + **5 seam-pending**（A1: SC-02-05/06/08/09；A2: SC-03-07）= 94；nextAction=等 D 注入 seam 补 5 节点正例，及新基线后对 C8/#8/OAS13 差异复验。

## 集成基线 lane D1（新基线定向复验，2026-09-12；HEAD 244b895）

> 公共修复基线合入（merge 5bd22d3；B Oracle PASS-with-notes）。三项定向复验，非全量重跑。

- **①常驻周期（C8 已接线）**：SC-01-15/16/18 以 `run_forever`+`scanners/scheduler.py` **常驻 worker**
  （env 短周期）真实观察，无 CLI；日志证明 `incident.scan` + `media.cleanup.discover` 周期运行；
  SC-01-16 周期自动建 T10 且重复不重发；SC-01-18 无目标不伪报 submitted/delivered。语义为
  **best-effort start-to-start**（错过合并/不追赶），合并/追赶未构造→观察边界如实标注。**C8=已接线+实测**。
- **②登出代次同事务（#8 已修）**：SC-01-17 登出后 `status=invalid` 且 `destination_revision` **恰 +1**、
  `invalidated_at` 非空（同一原子 UPDATE），重复登出幂等。**#8=已修+实测**。
- **③CC-11 收敛**：新契约下 9 API **严格校验全过**（`status_bad/impl_bad/contract_issues` 全空），
  **allowlist 13→0 条**，CC-11 **INFO→PASS**。残留（实测未触发、归属契约/A，不与原 13 混同）：
  `Progress/ProgressWithSync.targetCount` 仍 `allOf+nullable`（未 ready null 会触发严格拒绝）、历史 32 处
  nullable、incident 扇出无硬预算、cleanup LIMIT 无 keyset、resolved episode 不压缩、C25/C26。
- **重跑**：c-acceptance `E-AB-20260912T092138Z-ee4aad22` 14/14 PASS exit=0；matrix
  `E-20260912T091512Z-5e3e8e20` settled 94/94，PASSED=107 / PENDING=63 / FAILED=0，exit=3；selfcheck 76。
- **驱动侧修正**：c_care setup/cleanup 改 `docker start` 复用 + `docker stop` 保留卷（§440）；
  live.py 常驻 worker helper + 周期/登出纯函数回归；scanner 候选须 `connection_status='online'`。
- **缺陷**：无业务/契约缺陷（复验未发现修复不完整）。
- **清理**：`docker stop mvp-e-pg`（保留卷）；E 端口空闲、无 E JVM/worker、锁释放（文件保留）。
