# E 验收准备 Oracle 独立审查报告

- 日期：2026-09-10
- 审查者：`oracle`（本机已安装 omo-slim 的真实子代理，mode=subagent，沿用其现有模型配置；
  未以协调者/Codex 代替，未更换模型）
- 调用证据标识：task/session `ses_f7592f1b7ffe3L7KfP3jp79PRd`（调度板别名 ora-1），
  同一会话共 8 轮调用：初审 93363ee → 复审 6b0a234 → 终审 cc33abe →
  owner 映射再审 61f6329 → A 验收轮 f389078 → 440516b → 707670a → 85c2f33
- **reviewedCommit（最终被审代码 SHA）：`85c2f338b1fcbf922fc9348bf84335f55318957a`**
  （分支 feature/mvp-acceptance，工作树干净；本报告为独立后续文档提交，不含代码变更；
  HEAD=63763f2 仅为协调者独立复跑后的证据刷新）
- 实施链：cea01f7（框架+矩阵+计划+交接）→ 93363ee（E.md 事实修正）→
  6b0a234（第一轮修复）→ cc33abe（第二轮加固，第三轮 PASS）→
  7f4938f（本报告文字纠偏）→ 61f6329（owner 映射纠正，第四轮 PASS）→
  f389078（A 验收驱动+证据，第五轮 BLOCKED）→ 440516b（第五轮修复，第六轮 BLOCKED）→
  707670a（第六轮修复，第七轮 BLOCKED）→ 85c2f33（第七轮修复，**第八轮 E 代码 PASS**）；
  证据刷新 1dced90/8c7276a/297c176/63763f2（仅报告/证据，无代码）

## 总体结论：**E 代码 PASS**（第八轮复审 85c2f33；E 侧 blockingFindings：无）

**A 基础验收：未通过**——正式结算 52/52 中 1 FAIL=A 缺陷（`system.echo` GET 原样
公开内部诊断列 `async_jobs.last_error`，未脱敏未限大小；oracle 自第六轮起独立裁定
成立=A 验收 BLOCKER；A 代码未改，处置权在总协调）。50 PASS+1 INFO（9 处待人工
复核）构成有效基础覆盖；**暂不建议开放 B/C/D**。详见 `E-A-acceptance.md`。

审查性质：第 1—4 轮=E 验收准备门禁补审；第 5—8 轮=A 基线验收驱动与证据审查。
框架自检与 matrix 结果仍不代表任何业务场景通过（94 场景 dependency_pending，
blocked_by=B/C/D）。

## 分项结论（第三轮终审 cc33abe，历史记录）

| 分项 | 结论 | 依据 |
| --- | --- | --- |
| 1. 验收框架 | 通过 | 双层门禁在"防诚实性事故"威胁模型下充分：run.sh:64-84 拒绝外部 PYTEST_ADDOPTS（exit 4）+ env -u 清洗；run.sh:30-61 校验插件哨兵（存在/RUN_ID/mode/settled==94/计数一致），不符强制 4；framework/conftest.py:127-149,235-247 结算守卫；pass-requires-evidence（conftest.py:173-208,250-300）不误伤 selfcheck/pending；裸调 pytest 明确非验收入口 |
| 2. 94 场景矩阵与 API 追踪 | 通过 | 94 条、P0=69/P1=25、分节 4/18/11/9/10/7/9/7/5/14，逐行忠实源清单；27 API 双向一致（抽查 M2-A06/M4-A03/M3-A06 含 SC-C-01 展开）；owner 映射 M1/M2/M5→B、M3→C、M4→D；scenarios.json md5=8d2c4e4172800b8bf611c883657d10af 三轮未变。**勘误（第四轮）**：本行 owner 映射系负责人归属错误，已按总协调权威裁决纠正为 M3→D、M4-A03..A09→C、M4-A01/A02→D（B 不变）；md5"三轮未变"为历史事实，61f6329 仅改 owner_package，见第四轮证据 |
| 3. A 验收计划 | 通过 | AB-01..AB-11 完整覆盖 A-foundation.md:11,18：启动/重复启动、真实 PG 迁移、唯一约束拒双占用双记录、认证拒绝、Java→Python 契约 job 与代次、T12/T13、跨语言样例、fail-closed、Java/Python 测试命令与退出码、AB-11 结构化错误体/错误码/requestId 关联（plans/A-baseline-plan.md:15-35,107-125） |
| 4. 隔离/替身设计 | 通过 | 独立 DB/容器/端口、run-id 数据隔离、真实 PG 验证锁/唯一约束、六类夹具对应清单"开始执行前准备什么"、替身仅用 A 适配端口测试替身（不自建生产实现）、doubles_pass/real_pass 证据分级 |
| 5. 交接资料 | 通过 | E.md 与当前代码事实一致（退出码 3/4、哨兵、AB-01..AB-11），历史轮次明确标注，命令可复现 |

## 四轮审查与问题处置

### 第一轮（93363ee）→ BLOCKED，修复于 6b0a234
1. **BLOCKER** matrix 假 0：`PYTEST_ADDOPTS='--ignore=tests/scenarios' ./run.sh matrix`
   → collected 24、exit 0（94 场景未跑被当"全部真实通过"）。
   处置：插件层 94 sc_id 必结算守卫 + 退出码 4 + subprocess 回归自检。判定：已解决（并入第二轮 A 加固）。
2. **MAJOR** 证据默认写入 Authorization（client.py，redact_headers 默认空，与"不落凭据"声明矛盾）。
   处置：无条件脱敏 Authorization/Cookie/Proxy-Authorization/X-Api-Key，仅可追加不可移除。判定：已解决。
3. **MAJOR** passed 未绑定证据与替身声明（裸通过即计 passed）。
   处置：scenario_evidence 夹具 + 插件强制，缺失改判 fail("pass without evidence")，
   EVIDENCE_TAGS 四类计数。判定：复审 RESOLVED。
4. **MAJOR** A 计划缺 Java/Python 测试执行与结构化错误契约检查。
   处置：AB-01/02 增语言测试命令与退出码、新增 AB-11。判定：复审 RESOLVED。

### 第二轮（6b0a234）→ BLOCKED，修复于 cc33abe
- **A/BLOCKER** `PYTEST_ADDOPTS='-p no:framework.conftest ...' ./run.sh matrix` 可禁用插件
  → 94 skipped、exit 0。处置：run.sh 拒绝外部 PYTEST_ADDOPTS（exit 4）+ 哨兵校验（缺失/不匹配强制 4）。判定：终审 RESOLVED。
- **B/MAJOR** `record_raw()` 绕过脱敏（Authorization: Bearer SECRET 原样落盘）。
  处置：脱敏收敛至 EvidenceRecorder.record() 共同落盘边界。判定：终审 RESOLVED。
- **C/MINOR** E.md 陈旧（AB-01..AB-10、缺退出码 4）。处置：更新为当前事实。判定：终审 RESOLVED。

### 第三轮（cc33abe，终审）→ PASS
- blockingFindings：**无**
- 新发现 **MINOR**（未决，非阻塞）：framework/conftest.py:274-276 `record_raw()` 默认
  `run_id` 取 `self.recorder.dir.name`，当前目录为 `<RUN_ID>/<SC-ID>`，JSON 内会写成
  场景 ID 而非实际 RUN_ID；目录归档正确，不影响门禁、结算与 pass 判定，仅证据元数据
  不精确。复现：gate=open 后调用 record_raw 并检查证据 JSON 的 run_id 字段。
  **处置：接受并排期**——当前 gate=closed 无任何证据产生，无现实影响；将在 A 基线后
  编写场景步骤的同一轮修复（改为显式保存 run_id 或取父目录名）并补断言，届时随代码
  提交再绑定新 reviewedCommit。

### 第四轮（61f6329，owner 映射再审）→ PASS
- 背景：总协调权威裁决——API 设计一贯为 M3=测肤任务与报告（M3-A01..A06）、
  M4=护理管理（M4-A01..A09），无重编号；E 包旧 owner 映射 M3→C、M4→D 系
  **负责人归属错误**。正确归属：B=M1/M2/M5（不变）；D=M3（Java+测肤/归档 Worker）；
  C=M4 执行/记账 HTTP（M4-A03..A09）；D=M4 方案生成 Worker 相关（M4-A01/A02）；
  场景 owner_package=关联 API 归属并集（跨包可组合）。
- 修复（61f6329，4 文件 +71/−57）：matrix/generate_matrix.py 以 api_owner() 实现
  API 级规则；scenarios.json 再生成仅 owner_package 变化；tests/test_matrix_integrity.py
  独立全量断言 94 场景新规则（非抽查、不复用生成器函数）；E.md 归属行更新并标注
  历史错误。tests/scenarios/* 零改动（package markers 运行时由矩阵派生自动更新）；
  E-oracle.md 不在该代码提交内。
- Oracle 判定：owner 规则与断言精确符合裁决；"仅 owner 元数据变化"证据有效
  （剔除 owner 后哈希前后一致，diff 全部位于 owner_package 块）；M3/M4 业务语义
  始终未反置（本次为纯归属纠正）；第三轮 PASS 门禁项未破坏（diff 不含
  framework/run.sh/plans/框架自检/场景模块）；交接资料准确。
- blockingFindings：**无**。INFO：本报告历史章节保留的旧 owner 结论已以勘误标注
  被本轮权威映射取代（见分项结论第 2 行）。
- 第三轮遗留 MINOR（record_raw run_id 元数据）维持原排期，本轮未扩大。
- 修正后 owner 分布：B=28 B+C=2 B+C+D=7 B+D=3 C=26 C+D=7 D=21（合计 94）。

## 第五至八轮审查（A 基线验收轮，2026-09-10）

### 第五轮（f389078，A 验收驱动初审）→ BLOCKED，修复于 440516b
- **BLOCKER** AB-05e/f 认证撤销检查假阳性（复用 refresh 轮换后已撤销旧 token + SQL 改固定种子账号而非真实登录账号——删除 A 每请求复核也会 PASS）。
- **BLOCKER** N2-http 硬编码 PASS 无真实检查，且结论与 A 代码相反（SystemEchoController 实际投影 last_error）。
- **BLOCKER** a-baseline 无完整结算门禁（E_AB_ONLY 部分运行写正式证据；退出码在清理前求值，清理 FAIL 仍 0）。
- **MAJOR** 清理缺 run 所有权保护（可误删他用容器；RUN_ID 秒精度；worker 健康未绑子进程）。
- **MAJOR** 弱断言（AB-06b `or True`；媒体 uploader_ref 用 token[:8]；production 启动接受任意含 fail 非零退出，摘录空文件）。
- **MINOR** 框架摘要/README 仍称"A 基线未交付"。
- 处置：全部修复（独立会话+真实 accountId+行数断言+501→401 转变证据；N2-http 实测→**暴露 A 缺陷**；EXPECTED 52 结算+哨兵+清理后退出码+诊断模式隔离；label/锁/端口/存活绑定；断言强化；文案同步）。AB-02d/AB-06d 按总协调纠偏从 BLOCKED 转真实验证（E 隔离定向 worker pytest 26 passed；真实 mvp_worker 运行时+受控回调验证 RETRY_LIMIT_EXCEEDED 与陈旧代次哨兵 0，标注非 HTTP 链路）。

### 第六轮（440516b）→ BLOCKED，修复于 707670a
- **BLOCKER E-1** N2-http 在 SQL 失败/HTTP 错误响应下可假 PASS（UPDATE 未校验行数；非 200 无 marker 被判 PASS）。
- **BLOCKER E-2** 诊断模式仍覆盖正式 evidence（LOGS 恒指正式目录；阶段函数直写）。
- **MAJOR E-3** 锁 exists/read/write 非原子+RUN_ID 秒精度+worker 健康未绑 Popen、AB-02c 检查已清空变量。
- **MAJOR E-4** N2 消费点检视按文件名自动分类、丢行号、待检视项仍 PASS。
- **MAJOR E-5** AB-11 requestId 断言退化（None==None 可 PASS）。
- **A 缺陷独立裁定：成立，A 基础验收 BLOCKER**（合成 marker 非真实凭据泄露；已证实范围限 system.echo GET，不得成为 B/C/D 接入范例）。
- 处置：全部修复（n2_http_verdict 纯函数判定+六变体回归；set_output_mode 入口一次决定全部目录；flock 原子锁+随机后缀+Popen 绑定+真实 returncode 断言；file:line+片段分类检视、9 处待复核诚实降 INFO；requestId 双侧非空且相等+负例）。

### 第七轮（707670a）→ BLOCKED，修复于 85c2f33
- **BLOCKER** BLOCKED/结算不完整仍可宣称"A基础验收通过"（final_exit 不查 blocked；write_outputs 仅 fail>0 判通过；完整 BLOCKED 运行可 exit 0）。
- **MAJOR** flock 释放后 unlink → inode 竞态破坏单实例保证。
- **MAJOR** INFO 未进汇总计数（哨兵 settled=52 但 counts 和=51）。
- **MINOR** 超长变体复现 SQL 截断不可执行。
- 处置：全部修复（通过条件=结算完整+0 FAIL+0 BLOCKED，未知状态→4；INFO 附条件接受政策明文化且强制显式披露；锁文件常驻绝不 unlink；counts 含 info+和==settled 断言；repeat('L',4000) 完整可执行复现；五场景结论回归；N2-http 三条边界措辞固化——null=本样本未暴露、缺字段=保守 BLOCKED、样本通过≠通用脱敏保证）。

### 第八轮（85c2f33）→ E 代码 PASS
- 第七轮 findings 全部 RESOLVED；既有门禁（matrix 哨兵/PYTEST_ADDOPTS 拒绝/pass-requires-evidence/脱敏/AB-05 独立会话/AB-02d/AB-06d）未破坏；settlement_complete 在正式调用链上无假通过路径。
- E 侧 blockingFindings：**无**。遗留 **SUGGESTION（MINOR，非阻塞）**：五场景回归实为"结论政策单元测试"（未经 settlement()→write_outputs() 落盘链路），称谓需修正。处置：与 A 修复后定向重验同轮补 tmp_path 集成测试+INFO 9 处人工复核。
- A 缺陷裁定不变（A 代码未变），增强复现（完整可执行 SQL+两变体响应摘录）足以交 A 定位修复；重放需替换有效 jobId、Bearer 用运行时测试会话。
- 处置建议（最终决定权总协调）：交 A 修复诊断投影及受影响契约 → E 绑定新 A SHA 定向重验（两类诊断样本、正常投影、认证、受影响契约），未变证据复用须注明来源 SHA 与范围，不得以 PARTIAL 冒充全量。

## 第五至八轮测试命令与退出码（协调者于 85c2f33 真实执行，2026-09-10）

| 命令 | 退出码 | 结果 |
| --- | --- | --- |
| `backend/acceptance/run.sh selfcheck` | **0** | 45 passed（框架+矩阵+门禁/驱动回归） |
| `backend/acceptance/run.sh matrix` | **3** | PASSED=45 DEPENDENCY_PENDING=94 FAILED=0；SETTLED=94/94 |
| `backend/acceptance/run.sh a-baseline` | **1** | mode=formal settled=52/52；50 PASS / 1 FAIL（N2-http=A 缺陷）/ 0 BLOCKED / 1 INFO；counts_sum=52、unknown=[]；结论"A 基础验收：未通过" |

实施跑与协调者独立复跑（于 85c2f33）两跑一致；逐项证据见
`backend/acceptance/evidence/A-baseline-2026-09-10/` 与 `backend/handoffs/E-A-acceptance.md`。

## 第三轮测试命令与退出码（协调者于 cc33abe 真实执行，2026-09-10）

| 命令 | 退出码 | 结果 |
| --- | --- | --- |
| `cd backend/acceptance && PYTEST_ADDOPTS='-p no:framework.conftest -o addopts= --ignore=tests/scenarios' ./run.sh matrix` | **4** | 实际输出"拒绝外部 PYTEST_ADDOPTS 注入"，未进入 pytest（假 0 路径封死） |
| `cd backend/acceptance && PYTEST_ADDOPTS='-p no:cacheprovider --ignore=tests/scenarios' ./run.sh matrix` | **4** | 实际输出"拒绝外部 PYTEST_ADDOPTS 注入"，未进入 pytest |
| `backend/acceptance/run.sh selfcheck` | **0** | 33 passed（矩阵完整性+框架自检+6 项门禁回归） |
| `backend/acceptance/run.sh matrix` | **3** | collected 127；PASSED=33 DEPENDENCY_PENDING=94 FAILED=0 SKIPPED_OTHER=0；SETTLED=94/94 SETTLEMENT_OK；哨兵 reports/&lt;RUN_ID&gt;/settlement.json 与汇总一致 |
| `md5sum backend/acceptance/matrix/scenarios.json` | 0 | 8d2c4e4172800b8bf611c883657d10af（三轮未变） |

退出码语义：0=94 场景全部真实通过（含证据绑定）；1=有失败；3=存在 dependency_pending；
4=结算不完整/哨兵校验失败/外部注入被拒。监督已独立复核首轮交付的 selfcheck exit=0
与 matrix exit=3；本轮终审证据由协调者在 cc33abe 上执行并记录。
监督另在报告提交 2434f41（代码等同被审 cc33abe）独立执行复核：selfcheck exit=0、
33 passed；matrix exit=3、33 passed + 94 dependency_pending、SETTLED=94/94；上表两条
PYTEST_ADDOPTS 入口命令均 exit=4，实际输出均为"拒绝外部 PYTEST_ADDOPTS 注入"，
未进入 pytest。

## 第四轮测试命令与退出码（协调者于 61f6329 真实执行，2026-09-10）

| 命令 | 退出码 | 结果 |
| --- | --- | --- |
| `jq -S 'del(.[].owner_package)' backend/acceptance/matrix/scenarios.json \| md5sum`（修复前/后） | 0 | `abbde1f1b49021f7186739549609b1b5` 完全一致——94 场景 ID 与全部业务语义字段逐字节不变 |
| generate_matrix.py 连续两次再生成 | 0 | scenarios.json md5=`f9744fbde7aef70a7d0b7078bd2ba8f9` 幂等；apis.json md5=`cdbf826296231d25518c3d3f32252af2` 不变（无 owner 元数据） |
| `backend/acceptance/run.sh selfcheck` | **0** | 33 passed |
| `backend/acceptance/run.sh matrix` | **3** | PASSED=33 DEPENDENCY_PENDING=94 FAILED=0 SKIPPED_OTHER=0；SETTLED=94/94 SETTLEMENT_OK |

## 状态

- A 基线已到达（集成 df0fa32 / A 代码 26d97fb），E 独立基础验收已执行：
  **未通过**（1 FAIL=A 缺陷 system.echo lastError 原样投影；50 PASS / 1 INFO）；
  E 代码经第八轮 oracle 复审 PASS（85c2f33，E 侧 blockingFindings 无）。
- 第三轮遗留 MINOR（record_raw run_id）已于 f389078 修复并回归（closed）。
- 94 业务场景仍 dependency_pending（blocked_by=归属 B/C/D 业务包）。
- nextAction：**waiting_dependency** —— 总协调交 A 修复缺陷 → E 绑定新 A SHA
  定向重验（同轮完成第八轮 SUGGESTION：称谓修正+tmp_path 集成测试+INFO 9 处
  人工复核）→ 总协调决定是否开放 B/C/D。
