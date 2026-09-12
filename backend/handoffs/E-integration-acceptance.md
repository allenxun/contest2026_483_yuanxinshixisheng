# E → 最终基线全集成验收报告（94 场景矩阵实测）

> **增量更新（2026-09-13，增量基线 HEAD `73dbd19`，含 B 注入缝）**：七 seam（SC-02-05/06/08/09/10、
> SC-03-07、SC-C-05）已由 E 补全为**完整要求实测**并全部 **passed**。正式 matrix RUN_ID
> `E-20260912T163252Z-21bc4a75`（`run.sh matrix`，reviewed_sha `73dbd19`，evidence
> `evidence/Integration-2026-09-13-73dbd19/E-20260912T163252Z-21bc4a75/`）终态：
> settled **94/94 = 61 业务 passed + 33 device_pending + 0 seam + 0 staged**；PASSED=146（61 业务 +
> 85 框架自检，框架自检不计业务判定）/PENDING=33/FAILED=0/SKIPPED_OTHER=0，exit=3；doubles_pass=61、
> real_pass=0；selfcheck rc=0（85 passed，原 80+新增 5）。业务哈希 `86bfa7b721b6f285` 不变。详见
> `reports/first-round-integration.md` 末节「七 seam 补全（B 基线 73dbd19）— 已执行」。以下为上轮
> （bd73c59）终态记录，保留为历史，未覆盖。

- 日期：2026-09-12 ｜ 包：E（feature/mvp-acceptance，工作树 `.worktrees/mvp-e`）
- **最终 E 代码 SHA：`bd73c5924d66adbb550ccab1df146d92a534aea1`**（其后仅证据/报告提交）
- **Oracle 终判：第 23 轮 PASS_WITH_WARNINGS @ bd73c59，blockingFindings 无**（会话 ora-2；轮次台账见 `E-oracle.md` R20-R23）
- 终态正式跑：`run.sh matrix` RUN_ID=`E-20260912T143402Z-c4409fa0`（协调者独立复跑）

## 0. 结论摘要

94 场景矩阵在最终基线上**全部编写并活体实测**，终态结算：

| 类别 | 数量 | 含义 |
| --- | --- | --- |
| 场景 passed | **54** | 真实 HTTP+SQL 断言通过；**全部 doubles_pass 上限**（real_pass=0） |
| device_pending | **33** | 设备APP 项：后端可执行子步骤已全验，**真实设备/APP 联调待办** |
| seam-pending | **7** | 故障注入 seam 缺失，按总协调指定**待 B 实施**（清单见 `E-injection-checklist.md` 七项） |
| staged | **0** | 无待编写 |

矩阵口径：settled 94/94，PASSED=**134**（80 框架自检+54 场景）/ PENDING=**40** / FAILED=**0**，exit=**3**（pending>0 的诚实退出码）；doubles_pass=54、real_pass=0、mixed=0。
**业务缺陷：本次运行未报告 0**（措辞限于本轮黑盒+SQL+日志观察面，非缺陷不存在证明）。最终基线全集成验收**放行判断权在总协调**；本报告仅支持当前黑盒覆盖边界，不代表完整 MVP、真实设备或真实供应商已验收。

## 1. 验收对象与基线

- 最终代码基线：总协调批准 `f04543345ad8…`（B `f95037e`【B Oracle R5/R6 PASS-with-notes】+ C `8b3592e` + D `dc955c0` + Swagger `d3dc853` + A `561c338` 系），合入 E 树=`08404f8`（无冲突）。
- 公共修复基线：总协调批准 `5bd22d31935b…`（最终代码 `76a01f0`，B 负责人直接核实实际 Oracle PASS-with-notes），合入=`244b895`。修复面：①worker 常驻周期调度接线（`scanners/scheduler.py`，best-effort start-to-start）②登出 T09 失效+destination_revision 同事务+1③13 处 OAS 契约建模缺陷修正（validUntil/completedAt 直接 nullable、ProgressWithSync 展平）。
- E 侧边界：仅改 `backend/acceptance/**`+`backend/handoffs/E*.md`；未改业务/公共契约/Java/站点；授权 merge 之外无业务路径变更。
- 本轮 E 代码链：cbbec46(batch1 plumbing)→1cd87d8(lane A1 SC-02)→52b9eca(A2 SC-03)→d7e93b2(B1 SC-04)→b12a719(D1 三项复验)→ef09b16(B2 SC-06/07)→5a871bf(C1 SC-00/C-C)→11a5248(C2 SC-R，staged 归零)→afed44e(flake 修复)→af348c4(R20 修复)→6b95ebe(SC-R-03 门禁实证修复)→fc9a7f6(R21 修复)→62cd7c1(污染隔离+持久化接线)→**bd73c59(R22 修复，最终)**。

## 2. 方法与反假门禁

- **活体夹具**（framework/live.py）：E 专属 mvp-e-pg@55433 / Java@18081（当前源码重建 jar、SHA 打戳；-Xmx640m -XX:MaxMetaspaceSize=256m，严禁并行多 JVM）/ worker@18082（--once 步进；常驻进程仅周期观察）；结束 `docker stop mvp-e-pg`（**保留卷**）+回收进程；严禁 55435/18080/3000/5432/真实 PG-OSS-算法/41985。
- **证据绑定**：`evidence/Integration-<date>-<shortSHA>/<RUN_ID>/scenarios/<SC-ID>/` 逐交互 HTTP 记录（递归脱敏：请求头+请求体+响应体+record_raw，11 凭据键）+SQL 快照+worker/Java 日志；聚合 `settlement.json`（run_id/mode/reviewed_sha/command/**final_exit**/counts/settled/tags，fail-closed，按 RUN_ID 分目录防同 SHA 互覆）持久化于提交证据内，可独立复核。
- **三态诚实结算**：passed（真实断言+证据 sealed）/ device_pending（后端子步骤全验+真实联调待办；子步骤失败即 FAIL）/ seam_pending（可达安全边界断言+精确注入缺口披露）；**未编写未标记→FAIL** 反假守卫；device/seam pending 须 ≥1 证据+sealed+明确类别，缺失改判 fail。
- **doubles 声明**：face/skin/plan 提供方、短信/会话/存储均如实登记 → doubles_pass 上限；REAL_ONLY_CHECKPOINTS（设备实际停止/人脸连续性/手机实收通知/真实算法准确率）不得冒充。
- **矩阵完整性**：94 SC-ID/owner/业务语义逐字节不变（业务哈希 `86bfa7b721b6f285` 全程）；blocked_by=[]×94；gate=open（a_baseline.sha 绑定）；再生成幂等；退出码 0/1/3/4 政策与五 mode 哨兵。

## 3. 终态结算明细（正式跑 c4409fa0 @ bd73c59）

- settled **94/94** = 54 passed + 33 device_pending + 7 seam-pending + 0 staged；PASSED=134/PENDING=40/FAILED=0/SKIPPED_OTHER=0，exit=3；selfcheck rc=0（80 passed）。
- **7 seam-pending**（注入缺口，待 B 实施后定向重验）：SC-02-05、SC-02-06、SC-02-08、SC-02-09、SC-02-10（D face/skin 替身失败/非法形态无 env 注入 seam；SC-02-10 由 R20 轮从 passed 诚实改判——aliyun_skin 仅 transient retry、failureCode 不可观察）、SC-03-07（大模型超时子形态）、SC-C-05（存储上传失败注入）。节点均保留可达安全边界断言+精确披露。
- **33 device_pending**：SC-00×4、SC-04×7、SC-06-05、SC-07×3、SC-R×6 及 SC-01/SC-05 系设备侧项——后端可执行子步骤已全部验证通过，真实设备/APP 联调待办；逐节点明细见 `reports/first-round-integration.md` 各 lane 节与证据目录。
- **协调者双跑纪律实证**（三次捕获均为驱动侧、业务缺陷 0、全部修复+判别回归，失败 run 保留为迭代史零覆盖）：
  - `e8ba213c`：SC-06-05 补传时间戳 flake（rec() 嵌 utcnow 跨秒重构→同键异内容；C 409 RECORD_CONFLICT 为正确行为）→ 补传复用同一对象+rec(ts=) 固定。
  - `33ffeb3c`：新 pending 证据门禁捕获 SC-R-03 自编写起零证据落盘 → 补三次交互落盘+守护回归（未弱化门禁未开豁免）。
  - `7cc1b7dd`：SC-01-10 真实前置链（R21 要求）遗留 ready 报告+open 执行+微晶观察，污染文件序其后 5 节点（SC-02-03/03-05/06/04-02/03）的全局计数断言 → 断言限定各自实体/plan_id（语义更精确非弱化）。

## 4. 公共修复三项定向复验（lane D1，实测闭合，R20/R23 认可）

1. **常驻周期（原 C8）**：`run_forever`+`scheduler` 常驻 worker（env 短周期）**真实周期触发** incident.scan+media.cleanup.discover（worker 日志 `scanner.task_ran` 双任务、无 CLI 调用，不以 --once 冒充）；best-effort start-to-start/追赶合并的未构造边界如实标注。
2. **登出代次（原 #8）**：T09 `status=invalid`+`invalidated_at` 与 `destination_revision` **恰+1 同原子 UPDATE**；重复登出幂等（DB 不再变）；HTTP 信封逐结局精确断言（204 真空体/200 成功信封/401 requestId+error.code）。
3. **CC-11 契约收敛（原 OAS13）**：allowlist **13→0**；新契约下 9 个 M4 API 严格 OAS 校验全过（status_bad/impl_bad/contract_issues 全空，CC-11 INFO→PASS）；c-acceptance 重跑 14/14（`ee4aad22`）。
- **残留风险（如实披露，归属契约/A follow-up，未触发实测、不与 13 处修复混同，不宣称全契约通过）**：32 处历史 nullable（含 A08 targetCount allOf+nullable 残留）、incident 总扇出无硬预算、media.cleanup LIMIT 无 keyset、resolved episode 不压缩、C25/C26。

## 5. 旧证据复用与适用性（差异核实，非全量重跑）

- A 系台账（26d97fb 52 项+f6e500e 泄漏闭合+561c338 RV-5）：A 基础设施 diff=0 → 适用（E-A-acceptance.md 台账）。
- C 断面 @8b3592e：care 域零 diff → 适用；并于修复基线重跑 c-acceptance 14/14。
- CD 链 @aebccc7：业务断言适用；**CD-02「11 占位 501」断言因 B 集成失效**——领域已由场景节点接管（27 API 全真实实现），历史证据如实保留不重跑。
- 全部历史证据目录（A 13+C 19+CD 9+Integration 各 run 含失败迭代史）零覆盖。

## 6. 待办与依赖（交总协调裁定/唯一分配）

1. **放行判断**：本证据支持形成「最终基线全集成验收判断」（黑盒覆盖边界内）。
2. **7 注入 seam** → 指定 B 唯一实施（`E-injection-checklist.md`：注入配置/作用范围/复位方式/生产禁用证明/最小调用示例交接要求）；实施后 E 定向重验。
3. **33 设备 APP 真实联调** → 待设备/APP 就绪；E 后端子步骤已预验，禁止替身冒充。
4. **残留风险清单**（第 4 节）→ 裁定接受为已知限制或分配修复。
5. **C 三项协调请求**（CareFaceVerifier 公共端口/方案白名单批准/能力形状冻结）→ 维持待办（E-C-acceptance.md）。
6. **部署约束**：镜像/产物须从当前源码重建（历史镜像停留旧基线）。

## 7. 复现命令

```
backend/acceptance/run.sh selfcheck     # exit 0（80 passed）
backend/acceptance/run.sh matrix        # exit 3；终态证据 evidence/Integration-2026-09-12-bd73c59/E-20260912T143402Z-c4409fa0/
backend/acceptance/run.sh c-acceptance  # exit 0（14/14；D1 轮 ee4aad22）
```
A 系历史门禁（a-baseline/a-reverify/a-rv5）与 cd-chain 历史证据保留，适用性台账见 `E-A-acceptance.md`/`E-CD-acceptance.md`。

## 8. 诚实边界

54 场景 passed 全部为 **doubles_pass 上限**（D 三提供方=确定性替身；短信/会话/存储替身）；无真实设备/APP/供应商/OSS 参与；33 设备项仅后端子步骤预验；「业务缺陷 0」限于本次运行观察面；af348c4 前已提交历史证据中的 sessionToken 不改写（已过期、停止传播、如实披露）。本报告不宣称完整 MVP 验收、生产就绪或放行。
