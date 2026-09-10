# E 验收准备 Oracle 独立审查报告

- 日期：2026-09-10
- 审查者：`oracle`（本机已安装 omo-slim 的真实子代理，mode=subagent，沿用其现有模型配置；
  未以协调者/Codex 代替，未更换模型）
- 调用证据标识：task/session `ses_f7592f1b7ffe3L7KfP3jp79PRd`（调度板别名 ora-1），
  同一会话共 3 轮调用：初审 93363ee → 复审 6b0a234 → 终审 cc33abe
- **reviewedCommit（最终被审代码 SHA）：`cc33abe72185958a0f6384daa37f0f380796513e`**
  （分支 feature/mvp-acceptance，工作树干净；本报告为独立后续文档提交，不含代码变更）
- 实施链：cea01f7（框架+矩阵+计划+交接）→ 93363ee（E.md 事实修正）→
  6b0a234（第一轮修复）→ cc33abe（第二轮加固）

## 总体结论：**PASS**（blockingFindings：无）

审查性质：对 E 验收准备交付的门禁补审。当前 selfcheck/matrix 结果仅为框架自检与
依赖挂起状态，**不代表 A 或任何业务验收通过**。

## 分项结论（终审 cc33abe）

| 分项 | 结论 | 依据 |
| --- | --- | --- |
| 1. 验收框架 | 通过 | 双层门禁在"防诚实性事故"威胁模型下充分：run.sh:64-84 拒绝外部 PYTEST_ADDOPTS（exit 4）+ env -u 清洗；run.sh:30-61 校验插件哨兵（存在/RUN_ID/mode/settled==94/计数一致），不符强制 4；framework/conftest.py:127-149,235-247 结算守卫；pass-requires-evidence（conftest.py:173-208,250-300）不误伤 selfcheck/pending；裸调 pytest 明确非验收入口 |
| 2. 94 场景矩阵与 API 追踪 | 通过 | 94 条、P0=69/P1=25、分节 4/18/11/9/10/7/9/7/5/14，逐行忠实源清单；27 API 双向一致（抽查 M2-A06/M4-A03/M3-A06 含 SC-C-01 展开）；owner 映射 M1/M2/M5→B、M3→C、M4→D；scenarios.json md5=8d2c4e4172800b8bf611c883657d10af 三轮未变 |
| 3. A 验收计划 | 通过 | AB-01..AB-11 完整覆盖 A-foundation.md:11,18：启动/重复启动、真实 PG 迁移、唯一约束拒双占用双记录、认证拒绝、Java→Python 契约 job 与代次、T12/T13、跨语言样例、fail-closed、Java/Python 测试命令与退出码、AB-11 结构化错误体/错误码/requestId 关联（plans/A-baseline-plan.md:15-35,107-125） |
| 4. 隔离/替身设计 | 通过 | 独立 DB/容器/端口、run-id 数据隔离、真实 PG 验证锁/唯一约束、六类夹具对应清单"开始执行前准备什么"、替身仅用 A 适配端口测试替身（不自建生产实现）、doubles_pass/real_pass 证据分级 |
| 5. 交接资料 | 通过 | E.md 与当前代码事实一致（退出码 3/4、哨兵、AB-01..AB-11），历史轮次明确标注，命令可复现 |

## 三轮审查与问题处置

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

## 终审轮测试命令与退出码（协调者于 cc33abe 真实执行，2026-09-10）

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

## 状态

- 剩余依赖：**A 集成基线未提供**（blocker 不变），94 场景 dependency_pending。
- nextAction：**waiting_dependency** —— 协调者提供 A 基线 SHA → 更新
  config/baseline.json 开闸 → 按 AB-01..AB-11 执行基础验收（含上述 MINOR 修复）。
