# E → 最终基线全集成验收报告（94 场景矩阵实测）

- 日期：2026-09-12/13 ｜ 包：E（feature/mvp-acceptance，工作树 `.worktrees/mvp-e`）
- **最终 E 代码 SHA：`377e3ebf41677d8da65117fd15a5ecaf90421f32`**（其后仅协调者双跑证据与本报告定稿提交，无代码变更）
- **Oracle 终判：第 24 轮 PASS_WITH_WARNINGS @ 377e3eb，blockingFindings 无**（会话 ora-2；轮次台账见 `E-oracle.md` R20-R24）
- 终态正式跑（双跑一致）：实施跑 `E-20260912T163252Z-21bc4a75`（73dbd19 打戳）+ **协调者复跑 `E-20260912T165237Z-cb762349`**（`settlement.json` 绑定提交后 reviewed_sha=377e3eb+final_exit=3）

## 0. 结论摘要

94 场景矩阵在最终基线（含 B 七项测试注入缝）上**全部编写并活体实测**，终态结算：

| 类别 | 数量 | 含义 |
| --- | --- | --- |
| 业务 passed | **61** | 真实 HTTP+SQL+日志断言通过；**全部 doubles_pass 上限**（real_pass=0）；含七项 seam 节点按 B-seam-repro.md 配方补成**完整要求实测**（非安全边界代替，R24 逐项核验闭合） |
| device_pending | **33** | 设备APP 项：后端可执行子步骤已全验，**真实设备/APP 联调待办** |
| seam-pending | **0** | 七项注入缝已由 B 基线 73dbd19 提供并经 E 实测闭合 |
| staged | **0** | 无待编写 |

**61 业务判定达成**（原 54+7 seam 补全，按原 SC 精确映射；33 设备项单列；框架自检不计业务）。矩阵口径：settled 94/94，PASSED=**146**（61 业务+85 框架自检）/ PENDING=**33** / FAILED=**0**，exit=**3**（pending>0 的诚实退出码）；doubles_pass=61、real_pass=0、mixed=0；selfcheck rc=0（85 passed）。
**业务缺陷：本次运行未报告 0**（措辞限于本轮黑盒+SQL+日志观察面，非缺陷不存在证明）。最终基线全集成验收**放行判断权在总协调**；R24 判定：现有证据足以在黑盒覆盖边界内形成该判断，不代表完整 MVP、真实设备、真实供应商或 Swagger 后续验收完成。

## 1. 验收对象与基线

- 最终代码基线：总协调批准 `f04543345ad8…`（B `f95037e`【B Oracle R5/R6 PASS-with-notes】+ C `8b3592e` + D `dc955c0` + Swagger `d3dc853` + A `561c338` 系），合入 E 树=`08404f8`（无冲突）。
- 公共修复基线：总协调批准 `5bd22d31935b…`（最终代码 `76a01f0`），合入=`244b895`。修复面：①worker 常驻周期调度接线②登出 T09 失效+destination_revision 同事务+1③13 处 OAS 契约建模缺陷修正。
- **七项测试注入基线**：总协调批准 `73dbd19f44d0…`（B 代码 `11e42c8`，B 实际 Oracle PASS-with-notes，B 报告 `68936aa`），监督无冲突快进合入（backend/acceptance 零触碰）。权威配方 `backend/handoffs/B-seam-repro.md`：13 个注入开关（Python 12+Java 1）默认关闭/仅进程 env 可施加（无任何 HTTP 开启路径）/生产启动即拒（含混合 profile 与 app.env 矛盾组合）/严格值域 fail-fast；§5.1 b40 十步 barrier 序列、§5.2 b41、§6 已知边界（进程级注入须实例隔离、Java 旋钮改值须重启、barrier DIR 每 RUN_ID 独立）。
- E 侧边界：仅改 `backend/acceptance/**`+`backend/handoffs/E*.md`；未改业务/公共契约/Java/站点。
- 本轮 E 代码链：cbbec46(batch1)→1cd87d8(A1)→52b9eca(A2)→d7e93b2(B1)→b12a719(D1)→ef09b16(B2)→5a871bf(C1)→11a5248(C2，staged 归零)→afed44e(flake 修复)→af348c4(R20 修复)→6b95ebe(SC-R-03 门禁实证修复)→fc9a7f6(R21 修复)→62cd7c1(污染隔离+持久化接线)→bd73c59(R22 修复)→**377e3eb(七 seam 补全，最终)**。

## 2. 方法与反假门禁

- **活体夹具**（framework/live.py，本轮新增注入 seam 辅助：marker_image/sha256_hex/barrier_dir/barrier_env/start_bg_worker/stop_bg_worker/wait_path/log_has/sql_json）：E 专属 mvp-e-pg@55433 / Java@18081（当前源码重建 jar、SHA 打戳；-Xmx640m -XX:MaxMetaspaceSize=256m，严禁并行多 JVM）/ worker@18082（--once 步进；barrier 的 worker A/B/C 为轻量 python 进程）；结束 `docker stop mvp-e-pg`（**保留卷**）+回收进程；严禁 55435/18080/3000/5432/真实 PG-OSS-算法/41985。
- **证据绑定**：`evidence/Integration-<date>-<shortSHA>/<RUN_ID>/scenarios/<SC-ID>/` 逐交互 HTTP 记录（递归脱敏：请求头+请求体+响应体+record_raw）+SQL 快照+worker/Java 日志+AUDIT 记录；聚合 `settlement.json`（run_id/mode/reviewed_sha/command/**final_exit**/counts/settled/tags，fail-closed，按 RUN_ID 分目录）持久化于提交证据内，可独立复核。
- **三态诚实结算**：passed（真实断言+证据 sealed）/ device_pending（后端子步骤全验+真实联调待办；子步骤失败即 FAIL）/ seam_pending（机制保留，当前归零）；**未编写未标记→FAIL** 反假守卫；device/seam pending 须 ≥1 证据+sealed+明确类别，缺失改判 fail。
- **doubles 声明**：face/skin/plan 提供方、短信/会话/存储均如实登记 → doubles_pass 上限；**注入仅作用于替身层，HTTP 受理/幂等/版本校验/媒体授权/状态机/T12 领取-续租-失败退避/revision 守卫全部真实生产路径**；REAL_ONLY_CHECKPOINTS 不得冒充。
- **矩阵完整性**：94 SC-ID/owner/业务语义逐字节不变（业务哈希 `86bfa7b721b6f285` 全程）；blocked_by=[]×94；gate=open；再生成幂等；退出码 0/1/3/4 政策与五 mode 哨兵。
- **默认关闭对照口径（R24 更正表述）**：注入默认关闭=无 env 时行为与未引入完全一致，对照在**套件层**成立——部分节点（如 SC-02-06、SC-03-07）以邻接场景/同矩阵成功节点为对照而非每节点本地对照。

## 3. 终态结算明细（双跑：实施 21bc4a75 + 协调者 cb762349 @ 377e3eb）

- settled **94/94** = 业务 passed **61** + device_pending **33** + seam **0** + staged **0**；PASSED=146/PENDING=33/FAILED=0/SKIPPED_OTHER=0，exit=3；selfcheck rc=0（85 passed，含 +5 新回归：barrier helper/env 管道/生产守卫负例/非法值 fail-fast/61 映射）；94 个非空场景目录、380 JSON、RUN_ID 全一致。
- **七项 seam 节点补全明细**（R24 逐项闭合判定）：
  - SC-02-05：QUALITY=needs_retake+REQUIRED_VIEWS→T05 needs_retake+required_views+QUALITY_REJECTED+无 ready；复位对照达 report_ready。
  - SC-02-06：SAME_PERSON=false→NOT_SAME_PERSON（members 不增/member_id 空/无报告）；SEARCH=uncertain→IDENTITY_UNCERTAIN（不建档不出报告）。
  - SC-02-08：v1 needs_retake→M3-A02 同 taskId v2 成功（版本/revision/J2/视角继承/旧媒体保留）；跨云台拒绝+任务级零副作用。
  - SC-02-09（b40 十步全序列）：marker sha256 精确键控→worker A 入 barrier（consumed/analyzing/J1 lease_revision=1/attempt=1）→**自然租约过期**（2.5s，无伪造 DB/拆事务/放宽门禁/关续租）+--recover（queued/owner null/revision 推进）→worker B 同 barrier env **一次性接管**（succeeded/attempt=2/needs_retake）→M3-A02 HTTP v2 202→worker C 正常 env 至 report_ready+快照→写 released→A 退出+正式证据 **WARNING `job.complete_stale_generation`=true 且 a_rc=0**→v2 快照逐值未变/唯一任务报告/members 不变/sentinel 无残留（lease_revision 断言「≥2 推进」与配方口径一致，R24 判非弱化）。
  - SC-02-10：三形态各 1 轮确定性 PROVIDER_CONTRACT_VIOLATION 终态（T05 failed+report null；T12 failed/retryable=false/attempt=1；无后继 job）；M3-A03 GET 投影 failureCode 同值、**无 failure_detail/reason/stack 泄漏**（正式响应证据确认）；GET 非触发、重跑稳定、复位对照。
  - SC-03-07：PLAN timeout/failure→generation_status 绝不 ready+实际重试+预算耗尽落终态；非法形状走既有终态；循环有界；成功对照由同矩阵 SC-03-04 提供（R24 允许跨节点复用）。
  - SC-C-05：Java fail-put 按 purpose（assessment_source→M3 503 DEPENDENCY_UNAVAILABLE 无脏行；grant_face→M1 503 无 grants；**双向互不干扰**；execution_face/revalidation_face 经 **C 域真实 HTTP 端点**补验——闭合 B 文档 §6.3 E 证据缺口）；worker STORAGE_DOUBLE_FAIL_PUT→RESULT_ARCHIVE_FAILED 可重试+无脏 available+报告不就绪；关闭注入→正常保存+**重启可读字节哈希一致**+未授权/旧任务 404 保留。
- **横切验证**：Python 生产守卫 5 项实测（production+注入拒启/混合 profile 拒启/production+全默认不误拦/非法值 fail-fast 含值域/旋钮 env 管道——守卫函数级实测，真实 CLI 启动接线引用 B 已审证据，R24 SUGGESTION 记名）；**Java 生产 fail-closed 引用 B 单元/IT 证据——R24 裁定可接受**（守卫属已过 Oracle 的 B 基线，E 实测 dev 侧 seam 生效，重复六种 JVM 变体无新增判别价值）。
- **33 device_pending**：SC-00×4、SC-04×7、SC-06-05、SC-07×3、SC-R×6 及 SC-01/SC-05 系设备侧项——后端可执行子步骤已全部验证通过，真实设备/APP 联调待办；逐节点明细见 `reports/first-round-integration.md` 各 lane 节与证据目录。
- **协调者双跑纪律**：本轮 21bc4a75/cb762349 双跑一致；历史三次捕获（均为驱动侧、业务缺陷 0、修复+判别回归、失败 run 保留迭代史零覆盖）见第 9 节历史小节。

## 4. 公共修复三项定向复验（lane D1，实测闭合，R20/R23 认可）

1. **常驻周期（原 C8）**：`run_forever`+`scheduler` 常驻 worker **真实周期触发** incident.scan+media.cleanup.discover（worker 日志 `scanner.task_ran` 双任务、无 CLI 冒充）；best-effort start-to-start/追赶合并的未构造边界如实标注。
2. **登出代次（原 #8）**：T09 `status=invalid`+`invalidated_at` 与 `destination_revision` **恰+1 同原子 UPDATE**；重复登出幂等；HTTP 信封逐结局精确断言（204 真空体/200/401）。
3. **CC-11 契约收敛（原 OAS13）**：allowlist **13→0**；新契约下 9 个 M4 API 严格 OAS 校验全过（CC-11 INFO→PASS）；c-acceptance 重跑 14/14（`ee4aad22`）。
- **残留风险（如实披露，归属契约/A follow-up，未触发实测、不与 13 处修复混同，不宣称全契约通过）**：32 处历史 nullable（含 A08 targetCount allOf+nullable 残留）、incident 总扇出无硬预算、media.cleanup LIMIT 无 keyset、resolved episode 不压缩、C25/C26。

## 5. 旧证据复用与适用性（差异核实，非全量重跑）

- A 系台账（26d97fb 52 项+f6e500e 泄漏闭合+561c338 RV-5）：A 基础设施 diff=0 → 适用（E-A-acceptance.md）。
- C 断面 @8b3592e：care 域零 diff → 适用；并于修复基线重跑 c-acceptance 14/14。
- CD 链 @aebccc7：业务断言适用；CD-02「11 占位 501」断言因 B 集成失效——领域已由场景节点接管，历史证据如实保留不重跑。
- **54 项复用核实（注入基线）**：`dd3c34f..73dbd19` 恰 18 文件，业务面（assessment_analyze.py/Java care·assessments Service/worker runtime/A 业务）diff 全空；**且终态 matrix 实际重新执行了原 54 场景**——复用结论非仅静态分析（R24 确认）。
- 全部历史证据目录（A 13+C 19+CD 9+Integration 各 run 含失败迭代史与 21bc4a75）零覆盖。

## 6. 待办与依赖（交总协调裁定/唯一分配）

1. **放行判断**：R24 判定本证据足以在黑盒覆盖边界内形成「最终基线全集成验收判断」（放行权在总协调）。
2. **33 设备 APP 真实联调** → 待设备/APP 就绪；E 后端子步骤已预验，禁止替身冒充。
3. **残留风险清单**（第 4 节）→ 裁定接受为已知限制或分配修复。
4. **C 三项协调请求**（CareFaceVerifier 公共端口/方案白名单批准/能力形状冻结）→ 维持待办（E-C-acceptance.md）。
5. **R24 非阻塞待办**（随下一验收代码变更轮同修，届时须 Oracle 审新最终 SHA；本轮 377e3eb 已审，不为非阻塞项循环审查）：①`test_sc02.py:398-405` 泄漏守卫补 camelCase——对解析后响应递归禁止 `failure_detail`/`failureDetail`/`reason`/`stack` 内部诊断键+回归（当前正式响应实际无泄漏，不阻塞本基线）；②`test_framework_selfcheck.py` Python 启动守卫测试命名改「守卫函数实测、启动接线引用 B 证据」或补不连库的真实入口负例。
6. **Swagger 后续工作**：61 判定已完成，由总协调触发。
7. **部署约束**：镜像/产物须从当前源码重建（历史镜像停留旧基线）。

## 7. 复现命令

```
backend/acceptance/run.sh selfcheck     # exit 0（85 passed）
backend/acceptance/run.sh matrix        # exit 3；终态证据 evidence/Integration-2026-09-13-377e3eb/E-20260912T165237Z-cb762349/
backend/acceptance/run.sh c-acceptance  # exit 0（14/14；D1 轮 ee4aad22）
```
A 系历史门禁（a-baseline/a-reverify/a-rv5）与 cd-chain 历史证据保留，适用性台账见 `E-A-acceptance.md`/`E-CD-acceptance.md`。

## 8. 诚实边界

61 业务 passed 全部为 **doubles_pass 上限**（D 三提供方=确定性替身；短信/会话/存储替身；七项注入缝仅作用于替身层）；无真实设备/APP/供应商/OSS 参与；33 设备项仅后端子步骤预验；「业务缺陷 0」限于本次运行观察面；af348c4 前已提交历史证据中的 sessionToken 不改写（已过期、停止传播、如实披露）。本报告不宣称完整 MVP 验收、生产就绪或放行。

## 9. 历史终态（bd73c59 时代，R23 PASS_WITH_WARNINGS——保留防片段引用失真）

- 当时终态：94 = 54 passed + 33 device_pending + **7 seam-pending（注入缝缺失，按总协调指定待 B 实施**，清单 E-injection-checklist.md）+ 0 staged；正式跑 `c4409fa0`@bd73c59：PASSED=134（80 框架+54 场景）/PENDING=40/FAILED=0，exit=3；selfcheck 80。**该 7 项已于 73dbd19 注入基线补全闭合（见第 0/3 节），seam 归零。**
- R20-R22 修复循环（三轮 BLOCKED 全为 E 驱动断言强度/证据/持久化/文案缺陷，B/C/D 产品零缺陷裁定）与协调者双跑三次捕获：`e8ba213c`（SC-06-05 补传时间戳 flake，C 409 RECORD_CONFLICT 为正确行为）、`33ffeb3c`（pending 证据门禁捕获 SC-R-03 零证据）、`7cc1b7dd`（SC-01-10 真实前置链污染 5 节点全局计数断言→实体/plan 限定隔离）——全部驱动侧、修复+判别回归、失败 run 零覆盖保留。
- 台账详情：`E-oracle.md` R20-R23 节、`E.md` 终态事实同步节。
