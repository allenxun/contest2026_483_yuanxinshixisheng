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
  `a_reverify.py` 定向复验 RV-1..RV-9【11 项结算】、`verify_reverify_sentinel.py`
  RUN_ID 入口绑定哨兵【run_id/mode/settled/计数和/final_exit==驱动 rc，不符→4】）
- `evidence/A-baseline-2026-09-10/`（summary.md 逐项证据、results.json 哨兵、
  logs/ 摘录与 A 缺陷可执行复现）
- `evidence/A-reverify-2026-09-10/`（6 个 run 目录：定向复验证据，含
  n2-codereview-manual.md 人工复核 10 行、捕获响应与负例；旧正式证据零覆盖）
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

## 待 RV-5 裁定后的执行流程

1. 总协调书面裁定系统诊断可见性 → 若确认接受当前边界，RV-5 转 PASS，整体意见按
   组合证据形成；若要求创建者/任务类型过滤 → 交 A 实施，E 绑定更新 A SHA 定向重验。
2. 总协调按三部分结构（26d97fb 旧台账未变证据 + f6e500e 定向闭合 + RV-5 裁定）
   形成 A 基础验收整体意见，并决定是否启动 B/C/D。
3. B/C/D 集成后开闸（gate=open），按矩阵补写并运行场景步骤（P0 优先），证据严格
   区分 `doubles_pass` / `real_pass`（见 `plans/isolation-and-doubles.md`）。

## 状态

- blocker：**第十二轮 oracle 审查不可用（usage limit，原会话两次调用失败）**——
  RV-5 最终候选（A 561c338）有界复验已执行（`run.sh a-rv5` 双跑 settled 10/10=
  10 PASS、exit=0，哨兵入口绑定 OK），E 代码已提交 **03b8dfb** 但**未审，不得
  视为通过**；94 业务场景 dependency_pending（blocked_by=归属 B/C/D 包）。
- nextAction：**waiting_dependency**（oracle 配额恢复后重试第十二轮【原会话，
  不切换模型/不代替审查】→ 补记 E-oracle.md/E-A-acceptance.md 第十二轮结论 →
  组合意见与 B/C/D 启动建议由总协调形成；若审查发现阻塞→修复后再审）。
- 未修改 `backend/doc/**`、A 源码/契约/迁移/构建配置；未访问兄弟工作树；E 专用
  资源（mvp-e-pg@55433/18081/18082）已清理，未触碰 A 容器/端口；临时输出限
  E 路径（未用 /tmp/opencode）。
- 提交状态：本包已本地提交（实施 cea01f7 → 修复链 … → 85c2f33【R8 PASS】→
  07617a4/2a595cf/1fb5a5f【R9-R11，R11 PASS】→ **03b8dfb**【RV-5 有界复验驱动，
  R12 BLOCKED 待补】+ 证据刷新 baa809b/abaa6a9/ded4034/824d953 及报告提交），
  由总协调负责集成，未推送远端。
- E 代码经 oracle 第十一轮复审 PASS（reviewedCommit `1fb5a5f`）；03b8dfb 待第十二
  轮；全部结果为测试替身形态（doubles_pass），不构成业务验收通过或真实供应商
  接入声明；PARTIAL 不冒充新 SHA 全量。
