# E 验收准备 Oracle 独立审查报告

- 日期：2026-09-10
- 审查者：`oracle`（本机已安装 omo-slim 的真实子代理，mode=subagent，沿用其现有模型配置；
  未以协调者/Codex 代替，未更换模型）
- 调用证据标识：task/session `ses_f7592f1b7ffe3L7KfP3jp79PRd`（调度板别名 ora-1），
  同一会话共 19 轮正式调用：初审 93363ee → 复审 6b0a234 → 终审 cc33abe →
  owner 映射再审 61f6329 → A 验收轮 f389078 → 440516b → 707670a → 85c2f33 →
  定向复验轮 07617a4 → 2a595cf → 1fb5a5f → RV-5 有界复验轮 03b8dfb → cce3975 →
  C/M4 验收与 C+D 集成链路轮 fd18bd4 → f90bab2 → 845dca0 → 2fcb520 → 098d877 →
  edbc7c1（另 2026-09-10 两次第十二轮调用因 oracle 用量限制失败【usage limit
  reached】，配额恢复后经新授权单次正式调用完成；历史 429 仅作历史记录，不循环重试）
- **reviewedCommit（最终被审代码 SHA）：`edbc7c10c16b026bdd0c2473391feefc52352dee`**
  （分支 feature/mvp-acceptance，工作树干净；本报告更新为独立后续文档提交，不含
  代码变更；HEAD=66bf6a9 仅为协调者独立复跑后的证据刷新）
- 实施链：cea01f7（框架+矩阵+计划+交接）→ 93363ee（E.md 事实修正）→
  6b0a234（第一轮修复）→ cc33abe（第二轮加固，第三轮 PASS）→
  7f4938f（本报告文字纠偏）→ 61f6329（owner 映射纠正，第四轮 PASS）→
  f389078（A 验收驱动+证据，第五轮 BLOCKED）→ 440516b（第五轮修复，第六轮 BLOCKED）→
  707670a（第六轮修复，第七轮 BLOCKED）→ 85c2f33（第七轮修复，第八轮 E 代码 PASS）→
  07617a4（A 修复定向复验驱动，第九轮 BLOCKED）→ 2a595cf（第九轮修复，
  第十轮 PASS 附警告）→ 1fb5a5f（第十轮修复，第十一轮 E 代码 PASS）→
  03b8dfb（RV-5 有界复验驱动 a-rv5，第十二轮 BLOCKED）→ cce3975（第十二轮修复，
  第十三轮 E 代码 PASS）→ fd18bd4（C/M4 验收驱动 c_care，第十四轮 BLOCKED）→
  0f77b65（第十四轮修复）→ aebccc7（**总协调授权 merge 8afd0e5：C 8b3592e+D
  dc955c0 集成候选入树**）→ 2600825（C+D 集成链路驱动 cd_chain）→ f90bab2
  （CD-01 绑定修复，第十五轮 BLOCKED）→ 845dca0（第十五轮修复，第十六轮 BLOCKED）→
  2fcb520（第十六轮修复，第十七轮 BLOCKED）→ 098d877（第十七轮修复，
  第十八轮 BLOCKED）→ **edbc7c1（第十八轮修复，第十九轮 E 代码
  PASS_WITH_WARNINGS，blockingFindings 无）**；证据刷新 1dced90/8c7276a/297c176/
  63763f2/baa809b/abaa6a9/ded4034/824d953/3b38ce2/4b5ed51/f0fb329/1b3af71/
  d4be147/a7c1baa/66bf6a9（仅证据，无代码）；fb2fc08=配额受阻期 interim 报告

## 总体结论：**E 代码 PASS_WITH_WARNINGS**（第十九轮终审 edbc7c1；blockingFindings：无）

**C+D 集成验收组合结论（供总协调采用，2026-09-11）**：C/M4 黑盒验收
（c-acceptance 14 项，双跑 28c4994f/15ad40d0@edbc7c1=13 PASS+1 INFO，exit=0）+
C+D 真实端点集成链路验收（cd-chain 10 项，双跑 73a69cce/39d01667@2fcb520，
cd_chain.py 此后零改动经 R19 核定复用）全部通过；结合 C oracle R3
PASS-with-notes@8b3592e 与 D oracle R1/R2 PASS@dc955c0，**E 侧证据已足以供总协调
形成 C+D 集成验收判断**。**待总协调裁定项（IMPORTANT，外部，非 E 代码缺陷）**：
13 处共享 OpenAPI 建模缺陷（12 处 nullable:true 与 $ref/allOf 同层不生效+1 处
ProgressWithSync.lastSyncedAt 被 Progress.additionalProperties:false 经 allOf
误伤；清单/归属/复现见 E-C-acceptance.md 限制节）——接受为已知公共契约限制，或
交 A 修约后定向重验 CC-11；**裁定前不视为公共契约完全通过**。诚实边界保持：B 未
集成（11 占位 501）、媒体 deny-all 待 B、doubles_pass 非真实供应商、94 业务场景
dependency_pending、不声称完整 MVP 通过。

**A 基础验收组合结论（历史，供总协调采用）**：RV-5 裁定已由 A 实施（334a9c4→
199b2f6→561c338）并经 E 有界复验实测闭合（10/10 PASS，原 INFO 残项解除），
三部分组合证据齐备——①26d97fb 旧正式 52 项验收中适用的未变证据（RV-9/RV5-8
台账，注明来源与范围）；②f6e500e 诊断泄漏闭合（N2-http 实测+9 处消费点复核
闭合）；③561c338 RV-5 归属/统一拒绝/POST 碰撞闭合。放行记录保留非阻塞限制：
全局 dedup availability-oracle（已接受）、36 处路径外历史 nullable（A
follow-up）、旧镜像部署前须从当前源码重建。

审查性质：第 1—4 轮=E 验收准备门禁补审；第 5—8 轮=A 基线验收轮；第 9—11 轮=
A 修复定向复验轮；第 12—13 轮=RV-5 最终候选有界复验轮；第 14—19 轮=C/M4 验收
与 C+D 集成链路轮。框架自检与 matrix 结果仍不代表任何业务场景通过（94 场景
dependency_pending，blocked_by：[]×54（C/D 已集成，场景级步骤待写）/B×40）。

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

## 第九至十一轮审查（A 修复定向复验轮，2026-09-10）

### 第九轮（07617a4，定向复验初审）→ BLOCKED，修复于 2a595cf
- **BLOCKER** RV-2/3/4 缺目标 jobId 关联（GET 返回另一合法 job 也可假 PASS）。
- **BLOCKER** RV-5"他主体"实为同账号另一会话（AB.login() 固定 suffix 派生），且授权期望未固定（200 或 401/404 均可 PASS）。
- **MAJOR** a-reverify 哨兵按目录 mtime 选取，未绑定本次 run，仅查 mode+settled。
- **MAJOR** 报告/人工复核措辞超机器验证范围（11 项定向生成"A基础验收结论：通过"；rv8 预写结论未标注；repository.py:13 与 MediaService.java:115 依据不实）。
- 同步裁定：**原 A 诊断泄露缺陷在 f6e500e 已有闭合依据**（封闭枚举+retryable 有界投影）；RV-5 可见性政策应上交总协调（E 不得自行补 capability 结论，也不得凭契约空白判 A 缺陷）。
- 处置：全部修复（proj_verdict/queued_verdict 强制 data.jobId==目标+错误资源/缺字段负例回归；login(identity_tag) 真第二账号+accounts_differ 断言+同账号即 FAIL 防退化；RV-5 结算 INFO 待裁定语义；PARTIAL-only 措辞+整体意见另行形成声明；复核署名/核验人/A SHA+依据按本轮核验修正）。

### 第十轮（2a595cf）→ PASS（附非阻塞警告），修复于 1fb5a5f
- 第九轮两 BLOCKER RESOLVED（jobId 关联链完整、真跨账号+INFO 语义诚实）；MAJOR-4 措辞 RESOLVED；哨兵部分解决（校验 run_id/mode/settled/计数和/final_exit，但仍经共享 `.last-reverify-run` 指针选取，非入口绑定本次 run；无既有假 0 路径）。
- **MAJOR（非阻塞）**：哨兵未真绑定本次运行+未比对本次驱动 rc。
- **MINOR**：rv5_auth() 非 200 分支为基本信封检查，措辞可能被读作严格校验。
- 处置：全部修复（run.sh 入口生成 RUN_ID→env E_ACCEPTANCE_RUN_ID→驱动→哨兵→校验器同一 RUN_ID+显式路径+rc 比对，任一不符→4；`.last-reverify-run` 降信息用途；入口级旧哨兵/rc 不一致负例回归；rv5 分支如实改"基本错误信封检查"+局限记录）。

### 第十一轮（1fb5a5f，终审）→ E 代码 PASS
- 第十轮两项闭合（入口绑定链真实：run.sh:122-127→infra.py:47-53→verify_reverify_sentinel.py:49-87；rv5 措辞如实，INFO 语义未动）；无回归（第十轮已闭合项与既有门禁完好；E_ACCEPTANCE_RUN_ID 未设时 a-baseline 默认行为不变）。
- 双跑证据一致（c54479dd 实施跑 / 6a621528 协调者复跑）：settled 11/11=10 PASS+1 INFO（RV-5）、exit 0 附条件；旧五目录+A-baseline 零覆盖；PARTIAL 与"整体意见另行形成"声明显著。
- blockingFindings：**无**。RV-5 为已披露、待总协调书面裁定的政策事项，不列 E 代码阻塞。
- 交协调条件：**具备**——整体意见按三部分结构形成（26d97fb 旧台账未变证据 + f6e500e 定向闭合 + RV-5 裁定【含 GET 是否应限 system.echo 任务类型】）；E PASS 不自动等于 A 整体无条件通过，不自动授权 B/C/D；94 场景仍 dependency_pending，证据限 doubles_pass。

## 第九至十一轮测试命令与退出码（协调者于 1fb5a5f 真实执行，2026-09-10）

| 命令 | 退出码 | 结果 |
| --- | --- | --- |
| `backend/acceptance/run.sh selfcheck` | **0** | 51 passed（含入口级哨兵负例回归） |
| `backend/acceptance/run.sh matrix` | **3** | PASSED=51 DEPENDENCY_PENDING=94 FAILED=0；SETTLED=94/94 |
| `backend/acceptance/run.sh a-reverify` | **0** | settled=11/11；10 PASS / 0 FAIL / 0 BLOCKED / 1 INFO（RV-5 待裁定）；REVERIFY_SENTINEL_OK（RUN_ID 入口绑定一致、final_exit==驱动 rc）；结论"定向复验（PARTIAL）结果：通过（附条件）" |
| 入口哨兵负例（假 RUN_ID） | 1 | REVERIFY_SENTINEL_FAIL 拒绝 |

双跑证据目录：E-AB-20260910T155716Z-c54479dd（实施跑）、E-AB-20260910T155857Z-6a621528（协调者复跑）；逐项见 `backend/acceptance/evidence/A-reverify-2026-09-10/` 与 `E-A-acceptance.md` 定向复验节。

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

## 第十二轮审查（RV-5 有界复验轮初审 03b8dfb，2026-09-10/11）→ BLOCKED，修复于 cce3975

前史：2026-09-10 两次调用因用量限制失败（"The usage limit has been reached"），
按门禁规则记 BLOCKED 不视为通过（interim 披露提交 fb2fc08）；用户确认配额恢复后
经新授权单次正式调用完成本轮（不循环重试、不换模型、不代替审查）。

- **BLOCKER-1** RV5-3 三态比较过度裁剪：err_subtree() 只留 error 子树（非仅排除 requestId）、no_leak 仅查外来账号响应、非 echo 种子 INSERT 未验证成功（种子失败时第三态退化为"不存在"仍可 PASS）。
- **BLOCKER-2** RV5-5 keyed#1/重放未做与无键相同的完整拒绝边界检查、未与规范拒绝响应比较、重放后未复验 T13。
- **MAJOR-3** snapshot() 非全字段（遗漏 job_type/input_revision/max_attempts/lease_owner/lease_until/available_at/时间戳）；**MINOR** samples=True(200) 数字提取错误。
- 同步认定：**A 实现无新缺陷**（creatorOwns 同查 job_type/owner_type/owner_id、三态同一错误构造、POST T13 前归属门槛、succeeded 重放复核归属）。
- 处置：全部修复（canon_public 仅递归排除 requestId+三态完整公开体逐字节等值+禁止内容统一扫描+种子 INSERT RETURNING rowcount==1+回查【失败→BLOCKED 绝不 PASS】；无键/keyed#1/重放/规范 GET 拒绝四体统一完整拒绝体等值+防投影+重放后 T13 复验仍 rejected；SELECT * 全字段快照+SQL 成功断言+碰撞窗口 worker 未运行声明；samples 提取修正显示 50；+六类退化路径负例回归组）。

## 第十三轮审查（cce3975，RV-5 有界复验轮终审）→ E 代码 PASS

- 第十二轮四项全部闭合（对抗复核：canon_public 无其他裁剪、负例回归真实有效、四体比较含规范 GET 拒绝、全字段快照与声明一致——限碰撞窗口，非并发压力结论）；无回归（RV5-1/2/4/6/7/8、哨兵/结算/退出码政策、a-reverify/a-baseline、既有门禁完好）；SHA 绑定经 git 独立核实（存在、HEAD 祖先、diff 仅 backend/acceptance）。
- 双跑证据一致（e21ed79b 实施跑 / 90dbb580 协调者于 cce3975 复跑）：settled 10/10=10 PASS/0 FAIL/0 BLOCKED/0 INFO、exit=0、哨兵 RUN_ID 入口绑定+final_exit==驱动 rc；历史证据目录零覆盖。
- **原 RV-5 INFO 残项可解除**（书面裁定的有界范围已以足够断言强度实测闭合）。
- blockingFindings：**无**。组合证据齐备，已具备交总协调形成 A 整体基础验收结论并决定启动 B/C/D 的条件（最终放行权总协调）。

## 第十二至十三轮测试命令与退出码（协调者于 cce3975 真实执行，2026-09-11）

| 命令 | 退出码 | 结果 |
| --- | --- | --- |
| `backend/acceptance/run.sh selfcheck` | **0** | 54 passed（含六类负例回归组） |
| `backend/acceptance/run.sh matrix` | **3** | PASSED=54 DEPENDENCY_PENDING=94 FAILED=0；SETTLED=94/94 |
| `backend/acceptance/run.sh a-rv5` | **0** | settled=10/10；10 PASS / 0 FAIL / 0 BLOCKED / 0 INFO；REVERIFY_SENTINEL_OK（mode=rv5-reverify、final_exit==驱动 rc）；结论"RV-5 有界复验（PARTIAL）结果：通过" |

双跑证据目录：E-AB-20260911T012453Z-e21ed79b（实施跑）、E-AB-20260911T012642Z-90dbb580（协调者复跑）；逐项见 `backend/acceptance/evidence/A-rv5-2026-09-10-561c338/` 与 `E-A-acceptance.md` RV-5 节。

## 第十四至十九轮审查（C/M4 验收与 C+D 集成链路轮，2026-09-11）

| 轮次 | 对象 | 结论 | 阻塞发现与闭合 |
|---|---|---|---|
| R14 | fd18bd4（C 验收驱动 c_care 初版） | **BLOCKED** | 5 BLOCKER+1 IMPORTANT+1 SUGGESTION，全为 E 断言强度（CC-03 任意启动失败冒充生产拒绝、CC-05 四落点未真实覆盖、CC-06 不要求 409/精确 token、CC-09 空 disp 假 PASS+CC-10 新键重放未比 manifest、CC-11 未严格校验 care 成功响应；CC-04 T13/重放+CC-08 DEVICE_OCCUPIED/占用释放/TASK_REPLACED；三协调请求映射）；**C 实现未裁新缺陷** → 修复 0f77b65 |
| — | aebccc7 | 总协调授权 merge 8afd0e5（C 8b3592e+D dc955c0 集成候选；care/contracts diff=0，E 产物零触碰） | — |
| R15 | f90bab2（CD 链路驱动+R14 修复） | **BLOCKED** | BLOCKER：CC-11 非标准 OAS 改写（nullable 扩展/allOf 展平）+硬编码 POST 状态；IMPORTANT×4：CC-07 last_verified_at、CD-03 冻结基线仅通用形状+K 仅前后相等、CD-04 未 SQL 确认 T07、CD-06 success 未绑本次三 job；SUGGESTION：CC-01 merged 树措辞 → 修复 845dca0 |
| R16 | 845dca0 | **BLOCKED** | BLOCKER：classify_strict_error 过宽（任意 type+None 当契约 nullable、任意 additionalProperties 当 allOf 误伤→实现缺陷可降级 INFO+exit 0）；IMPORTANT：CD-06 enroll 取全库最早未绑本链；MINOR：报告漏 A08 completedAt → 修复 2fcb520（13 条四元组 allowlist+enroll 差集绑定） |
| R17 | 2fcb520 | **BLOCKED** | BLOCKER：A08 allowlist 仅查 message 含 lastSyncedAt，jsonschema 合并多未知字段→oracle 实际复现 data.secret 泄漏仍降级 INFO；IMPORTANT：13 处 OAS 缺陷误写「已接受限制」（应为待总协调裁定）；MINOR：三处陈旧事实 → 修复 098d877（恰等 {lastSyncedAt}+absolute_schema_path 真四元组） |
| R18 | 098d877 | **BLOCKED** | BLOCKER：未知字段集合仍正则解析人类可读 message——oracle 实际复现 `"secret'x"`（字段名含单引号→Python repr 双引号包裹）被正则漏读仍降级 INFO；MINOR：E-C:51 selfcheck 统计 → 修复 edbc7c1（**结构化计算** instance.keys−schema.properties−patternProperties，与引号字符无关） |
| R19 | **edbc7c1** | **PASS_WITH_WARNINGS（blockingFindings 无）** | R18 BLOCKER RESOLVED（oracle 独立复现四形态：仅 lastSyncedAt→contract；+secret'x/+sec"y/+多字段→impl）；MINOR RESOLVED；无回归（五 mode/哨兵/门禁/R15-R17 已闭合断言完好）；双跑一致核定。遗留：SUGGESTION（E-C:3 头陈旧 HEAD 引用——本报告定稿已修正）；**IMPORTANT 外部待裁定**（13 处共享 OpenAPI 建模缺陷：接受为已知限制或交 A 修约，裁定前不视为公共契约通过；非 E 代码缺陷） |

### 第十四至十九轮测试命令与退出码（协调者于最终代码真实执行，2026-09-11）

| 命令 | 退出码 | 结果 |
| --- | --- | --- |
| `backend/acceptance/run.sh selfcheck` | **0** | 72 passed（含 CC-11 结构化未知字段/真四元组 allowlist 判别、CD-01 绑定、CC-02 谓词、CD-06 enroll 本链绑定等负例回归） |
| `backend/acceptance/run.sh matrix` | **3** | PASSED=72 DEPENDENCY_PENDING=94 FAILED=0；SETTLED=94/94；blocked_by []×54/B×40；三字段剔除哈希 e4f5dc52 不变 |
| `backend/acceptance/run.sh c-acceptance` | **0** | settled=14/14；13 PASS+1 INFO（CC-11 契约披露，allowlist 13/13、impl_bad=[]）；双跑 28c4994f（实施）/15ad40d0（协调者@edbc7c1）一致；哨兵 OK |
| `backend/acceptance/run.sh cd-chain` | **0** | settled=10/10 全 PASS；双跑 73a69cce（实施）/39d01667（协调者@2fcb520）一致；cd_chain.py 此后零改动，R19 核定复用 |

证据目录：`evidence/C-acceptance-2026-09-11-8b3592e/`（12 run 含迭代史：feeb86d8=12P/2F 驱动侧归因等，零覆盖）；`evidence/CD-chain-2026-09-11-aebccc7/`（7 run 含 945fda65=9P/1F CD-01 绑定缺陷驱动侧归因，零覆盖）。逐项见 `E-C-acceptance.md` 与 `E-CD-acceptance.md`。

## 状态

- **C/M4+C+D 集成链路验收完成**：E 代码最终 **edbc7c1** 经第十九轮 oracle 终审
  PASS_WITH_WARNINGS（blockingFindings 无）；c-acceptance 14 项与 cd-chain 10 项
  均双跑一致 exit=0；C/D 产品代码未发现缺陷。
- **待总协调裁定**：①13 处共享 OpenAPI 建模缺陷（接受为已知限制或交 A 修约+定向
  重验 CC-11；裁定前不视为公共契约通过）；②C 三项协调请求（CareFaceVerifier 公共
  端口/方案白名单批准/能力形状冻结，见 E-C-acceptance.md）；③C+D 集成验收整体
  判断与 B 启动（最终放行权总协调，E 不自动启动）。
- 94 业务场景仍 dependency_pending（blocked_by：[]×54=C/D 已集成但场景级 E2E 步骤
  待写、B×40=B 未集成 11 占位 501）；全部证据为 doubles_pass 替身形态，不声称
  完整 MVP/真实供应商/生产就绪。
- nextAction：**waiting_dependency** —— 总协调裁定上述事项并决定 B 集成/94 场景
  开闸；B 集成后 E 按矩阵补场景级步骤继续验收。

## 集成验收轮 Oracle 门禁（R20-R23，2026-09-12，最终基线 94 场景全量实测）

> 上节状态为 edbc7c1 时代（94 场景开闸前）终态。总协调批准最终代码基线 f045433
> 与公共修复基线 5bd22d3 合入 E 树后，E 完成 94 场景全部编写与活体实测
> （见 `E-integration-acceptance.md`），Oracle 门禁续四轮如下。
> **会话记录（如实）**：R20 由原会话 ora-1（ses_f7592f1b7ffe…，第 20 次调用）执行，
> 该会话随后 stalled 不可复用；R21-R23 经调度板确认以新会话 ora-2
> （ses_f6a49a544ffe…）执行——同为已安装 omo-slim 真实 `oracle` 子代理、沿用现有
> 模型配置，非换模型、非冒充。

| 轮次 | reviewedCommit | 判定 | 要点 |
| --- | --- | --- | --- |
| R20 | afed44e | **BLOCKED**（ora-1） | 4 场景假 PASS BLOCKER（SC-01-10 迟到副作用未验、SC-02-10 analyzing 即 PASS、SC-R-13 放行被禁矛盾态、SC-R-14 恢复接口未断言）+5 IMPORTANT（终态证据未绑定 reviewedCommit、sessionToken 入证据、pending 无证据门禁、登出未断 HTTP、文案陈旧）→ af348c4 八项修复（SC-02-10 诚实改判 seam-pending：场景 passed 55→54、seam 6→7；SC-R-14 如实披露 `current-assessment-status` 在代码/契约不存在、未伪造；响应体 11 键递归脱敏；pending 证据门禁）+6b95ebe（协调者复跑 33ffeb3c 经新门禁捕获 SC-R-03 零证据→补落盘+守护，未弱化未豁免） |
| R21 | 6b95ebe | **BLOCKED**（ora-2 新会话） | 2 BLOCKER（SC-01-10 无前置执行/占用态且未逐响应断状态码——副作用承诺未真验；SC-R-13 竞态前已有 open execution——验既有占用非原子竞态+布尔优先级缺陷）+4 IMPORTANT（登出信封 or 链近恒真、SC-R-14 空态断言过宽、聚合 settlement 未持久化入提交证据、conftest/E.md 文案）→ fc9a7f6 六项修复；协调者正式复跑 7cc1b7dd 捕获 FAILED=5（SC-01-10 真实前置链遗留 ready 报告+open 执行+微晶观察，污染文件序其后 SC-02-03/03-05/06/04-02/03 的全局计数断言——驱动侧隔离缺陷，非业务缺陷）→ 62cd7c1 实体/plan 限定隔离+run.sh 持久化接线（E_ACCEPTANCE_EVIDENCE_DIR/REVIEWED_SHA） |
| R22 | 62cd7c1 | **BLOCKED**（ora-2） | 2 BLOCKER 未严格闭合（SC-01-10 sync 返回值忽略/K=1 前置未断+`accepted is not True` 允许缺字段或无关 409 假通过；SC-R-13 未断 rc==202/rtid 非空/cur==rtid——replacement 失败或指针未更新仍可通过）+5 IMPORTANT（登出 204 允许任意非空 `_raw`、SC-R-14 data={}/字段缺失可通过、SC-04-02/03 按 member 限定漏检误写他员 execution、持久化吞异常/同 SHA 互覆/缺 final_exit、conftest 251-254 文案声称已改实际未落地+checklist 缺 SC-02-10）→ **bd73c59** 七项修复（conftest 文案项由协调者验证发现残留后直接补齐，commit 如实记录） |
| R23 | **bd73c59** | **PASS_WITH_WARNINGS（blockingFindings 无）** | 七项闭合逐项核验：SC-01-10 sync 200+K=1+open=1 前置断言（test_sc01.py:221-224）+精确 (200,true)/(200,false) 配对（:258-263）；SC-R-13 rc==202+rtid 非空+`cur == rtid`（test_scr.py:331-332）+admit-first/replace-first 双完整终态白名单（admit-first 双成功=准入先线性化的一致结局）；登出 204 真空体；SC-R-14 isinstance+字段存在+严格 None；SC-04 按 plan IDs 限定（可捕获误写他员）；持久化 fail-closed/按 RUN_ID/final_exit 实证（已提交 settlement.json 绑定 bd73c59：134/0/40/0、94/94、exit 3、doubles_pass 54）；文案三类+checklist 七项齐备。无回归确认（五 mode 哨兵/退出码优先级/PYTEST_ADDOPTS 防注入/pass-requires-evidence/pending 门禁/递归脱敏/flock/诊断隔离）。非阻塞遗留：IMPORTANT——E.md 终态未同步 bd73c59/c4409fa0（报告定稿轮已同步）；SUGGESTION——checklist「已有55项证据」措辞（已改 54+历史值标注） |

### R20-R23 测试命令与退出码（协调者于最终代码 bd73c59 真实执行，2026-09-12）

| 命令 | 退出码 | 结果 |
| --- | --- | --- |
| `backend/acceptance/run.sh selfcheck` | **0** | 80 passed |
| `backend/acceptance/run.sh matrix` | **3** | PASSED=134（80 框架+54 场景）/PENDING=40（33 device+7 seam）/FAILED=0；SETTLED 94/94；RUN_ID=`E-20260912T143402Z-c4409fa0`；doubles_pass=54/real_pass=0；settlement.json（final_exit=3+reviewed_sha）按 RUN_ID 持久化于提交证据 |
| `backend/acceptance/run.sh c-acceptance` | **0** | 14/14（D1 轮 ee4aad22@修复基线：CC-11 allowlist 13→0、9 API 严格全过、INFO→PASS） |

cd-chain 未在新基线重跑：CD-02「11 占位 501」断言因 B 集成失效，领域已由场景节点接管（27 API 全真实实现）；历史证据 73a69cce/39d01667 如实保留。A 系历史门禁（a-baseline/a-reverify/a-rv5）证据保留，适用性台账见 `E-A-acceptance.md`。失败迭代史（e8ba213c flake/33ffeb3c 门禁捕获/7cc1b7dd 污染）零覆盖保留。

## 状态（第二十三轮后定稿，取代上方 edbc7c1 时代状态节）

- **最终基线全集成验收（E 侧黑盒覆盖边界）完成**：E 代码最终 **bd73c59**，Oracle
  R23 **PASS_WITH_WARNINGS（blockingFindings 无）**；终态 94 = 场景 passed **54**
  （全部 doubles_pass 上限）+ device_pending **33**（真实设备/APP 联调待办）+
  seam-pending **7**（注入 seam 待 B 实施，`E-injection-checklist.md` 七项）+
  staged **0**；业务缺陷：**本次运行未报告**（限本轮观察面，非缺陷不存在证明）。
- 公共修复三项（常驻周期/登出代次/CC-11 契约收敛）经 lane D1 实测闭合；残留风险
  （32 处历史 nullable 含 A08 targetCount、incident 扇出无硬预算、cleanup LIMIT 无
  keyset、resolved episode 不压缩、C25/C26）如实披露、归属契约/A follow-up，
  未触发实测、不与 13 处修复混同，不宣称全契约通过。
- **待总协调**：①放行判断（本证据支持形成最终基线全集成验收判断；放行权在总协调）
  ②七项注入 seam 指定 B 唯一实施，实施后 E 定向重验③33 设备 APP 真实联调安排
  ④残留风险裁定⑤C 三项协调请求续办（E-C-acceptance.md）。
- 诚实边界：不宣称完整 MVP/真实设备/真实供应商/生产就绪；部署前镜像/产物须从当前
  源码重建；af348c4 前历史证据中 sessionToken 不改写（已过期、停止传播、如实披露）。
- nextAction：**waiting_dependency**。
