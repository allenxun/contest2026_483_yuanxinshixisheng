# E C+D 集成链路验收 —— 交接草稿

> 由 E 实施代理起草，供总协调定稿。集成候选：merged HEAD `aebccc7`（merge `8afd0e5`；C=`8b3592e`、D=`dc955c0`；B 未集成）。
> 证据：`backend/acceptance/evidence/CD-chain-2026-09-11-aebccc7/`（正式 run，RUN_ID 入口绑定 + 哨兵）。
> 命令：`backend/acceptance/run.sh cd-chain`（mode=`cd-chain`，EXPECTED=CD-01..CD-08 + CLEANUP + CLEANUP-ports，10 项唯一结算）。

## 命令与退出码

- 正式跑：RUN_ID=`E-CD-20260911T094733Z-5f50aeb4`，settled 10/10，counts={PASS:10,FAIL:0,BLOCKED:0,INFO:0}，exit=0；哨兵 `run_id` 入口绑定且 `final_exit==驱动 rc`。
- 迭代记录（如实）：协调者提交后树复跑 `E-CD-20260911T094425Z-945fda65` 得 9 PASS/1 FAIL——唯一 FAIL=CD-01，根因是**驱动绑定缺陷**（以 HEAD 字面等值 `aebccc7` 断言，而 E 自身验收代码/证据/报告提交必然前移 HEAD；业务面 C/D/merged 祖先、care/contracts diff、jar/worker/health 全 True）。已修为「祖先关系+业务路径 diff 空」并加 selfcheck 负例；`945fda65` 及此前 E 正式 run（`7c7b0e92`、`350c6b76`）均保留零覆盖。**非 C/D 缺陷**。
- `run.sh c-acceptance` 在 merged 树重跑：RUN_ID=`E-AB-20260911T093819Z-f724f2ba`，settled 14/14，counts={PASS:14,FAIL:0,BLOCKED:0,INFO:0}，exit=0（care 域 8b3592e..aebccc7 diff=0，旧证据适用）。
- `run.sh selfcheck` rc=0（67 passed，含 CD-01 绑定负例回归）；`run.sh matrix` rc=3（94 pending、SETTLED 94/94、blocked_by []×54/B×40）。
- 既有 A 系 + C 系 7 run 证据目录零覆盖（新 run 独立子目录）。

## CD 逐项结论

| 项 | 结论 | 说明 |
|---|---|---|
| CD-01 | PASS | **祖先关系绑定（非 HEAD 等值）**：C 8b3592e/D dc955c0/merged aebccc7 均为当前 HEAD 祖先；`aebccc7..HEAD -- web-java/worker-python/contracts` diff 空（仅 E 提交）；care diff=0、contracts diff=0；当前源码重建 jar、worker 依赖就绪、health UP@18081 |
| CD-02 | PASS | 11 个 B 域占位端点（M1/M2/M5）逐个已认证 HTTP 501 NOT_IMPLEMENTED；未认证 401（B 待集成边界如实） |
| CD-03 | PASS | B 前置 test_seed（gimbal/T04 设备能力）→ 真实 M3-A01 受理 → 真实 worker analyze/enroll/analyze → T06 由 D 发布事务唯一创建（waiting_inputs、generation_revision=0、input_photo_version=1、assessment 唯一）→ plan.generate → ready；冻结 capability/steps 形状完整；D 未写 K（completed_count/completed_at/progress_revision 不变） |
| CD-04 | PASS | 对真实 ready T06 执行 C A03 准入（dev 人脸绑定）→ 201+T07 创建；C 能力校验器接受 D 冻结基线（双侧 unit/区域/N bounds 实际值入证据） |
| CD-05 | PASS | 真实 M3-A01 受理触发 T03 指针原子替换（非 SQL 种子）；替换前云台 A03=201、替换后旧任务 A03=409 TASK_REPLACED；A08：真实链路旧执行已 closed→404（生命周期冻结先于指针），另以 test_seed 指针移动在 admitted 执行上验证 A08=409 TASK_REPLACED；时序化窗口一致 |
| CD-06 | PASS | success=全链 job succeeded 且 worker 日志 stale_generation=0；defer=plan.generate 能力等待跳（T12 queued、attempt=0、lease 轮换、gen_rev=0；T13 不适用）；failure=确定性配置故障（baseline 缺 n_bounds）→ PLAN_SNAPSHOT_INVALID 终态原子写（T06 无 ready 半成品、T12 同 failed） |
| CD-07 | PASS | blocked_by=owner−{C,D} → []×54/B×40；owner/94 ID/业务语义逐字节不变（三字段剔除哈希 e4f5dc52）；pending_reason 分类细化；再生成幂等 |
| CD-08 | PASS | 全部 doubles_pass；B 依赖逐项 dependency_pending；既有证据零覆盖；D 待接线如实转录 |

## 真实链 vs 种子标签

- **真实 D 链**（HTTP + worker）：M3-A01 受理、报告发布、T06 唯一创建、plan.generate → ready、T03 指针替换。
- **test_seed（B 未集成）**：云台（M2）、T04 设备能力观察、成员 active grant、CD-05 的 A08 边界指针移动。
- **替身（doubles_pass）**：D face/skin/plan 三提供方为受控确定性替身；A 存储 FilesystemStorageDouble。
- 媒体业务读取 404（A deny-all，待 B）为预期。

## B 待集成清单

- M1/M2/M5 共 11 个端点 501 NOT_IMPLEMENTED（成员授权/云台心跳状态/微晶观察/绑定/通知）。
- 媒体业务读取（contentUrl 实际下载）待 B 统一 @Primary MediaAccessPolicy（当前 deny-all → 404）。
- 真实成员授权/撤销、设备凭据、媒体访问策略端到端链路。

## D 待接线事项（如实转录）

- `media.cleanup` 周期触发/崩溃孤儿扫描接线（D 提供幂等 discover_and_enqueue_orphans+handler）；真实供应商激活前须按冻结 model provenance 选择或 mismatch fail-closed。
- `enroll` 终态 failed 槽位保持占用，受控恢复=运维对账后置 cancelled/succeeded。
- 真实供应商前提：凭据+阿里云 PoC+设备团队批准指标/能力基线。

## 集成适用性（C 既有证据）

- C care 域 `8b3592e..aebccc7` diff=0、contracts diff=0；merged 树重跑 c-acceptance 仍 14/14 PASS，旧 C 证据对 merged 候选继续适用。

## 缺陷

- 已执行的有效检查未观察到 C/D 缺陷。

## 限制

- 未重跑 C 的 Java 262 项 / D 的 Java 183+Python 175 套件（超范围）；未声称完整 MVP 通过。
- 内存紧张：Java 限堆 `-Xmx640m -XX:MaxMetaspaceSize=256m`；worker 以 `--once` 步进（低资源，非持久 18082 循环）。
- CD-05 A08 面：真实 M3-A01 受理要求无未收尾执行，故替换前执行必先 closed，A08 生命周期冻结先于指针检查→404；A08=409 TASK_REPLACED 以 test_seed 指针移动在 admitted 执行上验证。
