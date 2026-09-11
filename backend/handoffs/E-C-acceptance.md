# E-C 验收（C/M4 护理管理）交接草稿

> 由 E 实施代理起草，供总协调定稿。基线：C 最终代码 `8b3592e`，集成 HEAD `93b7e33`（E 工作树）。
> 证据：`backend/acceptance/evidence/C-acceptance-2026-09-11-8b3592e/`（正式 run，RUN_ID 入口绑定 + 哨兵）。
> Oracle R14（审 `fd18bd4`）判 BLOCKED（5 BLOCKER+1 IMPORTANT+1 SUGGESTION，均为 E 驱动断言强度，未裁 C 新缺陷）；本轮按 findings 加强断言并正式重跑。

## 命令与退出码

- `backend/acceptance/run.sh c-acceptance`：mode=`c-care`，EXPECTED=CC-01..CC-12 + CLEANUP + CLEANUP-ports（14 项唯一结算）。
- 正式跑（当前，R18）：RUN_ID=`E-AB-20260911T111832Z-28c4994f`，settled 14/14，counts={PASS:13, FAIL:0, BLOCKED:0, INFO:1}，exit=0；哨兵 `run_id` 入口绑定且 `final_exit==驱动 rc`。INFO=CC-11（真四元组 allowlist 精确命中 13 路径、`impl_bad=[]`；未知字段集合改为**结构化计算**，杜绝字段名引号绕过；契约缺陷**已发现并升级待裁定**）。
- 历史迭代 run（保留、零覆盖）：R15 `E-AB-20260911T100912Z-0972884c`（13 PASS/1 INFO）；R14 `E-AB-20260911T090147Z-6d8dbb55`（**14 PASS/0 INFO**）；merged 重跑 `f724f2ba` 等；其 summary 历史措辞不改写。
- 历史迭代 run（保留、零覆盖）：`E-AB-20260911T082701Z-73350e3c`（14 PASS）、`E-AB-20260911T081747Z-feeb86d8`（12 PASS / 2 FAIL 驱动侧归因）；连同早期 4 个 run 目录均未被覆盖。
- `run.sh selfcheck` rc=0（72 passed）；`run.sh matrix` rc=3（94 pending、SETTLED 94/94）。

## CC 逐项结论（R14 加强后）

| 项 | 结论 | 说明 |
|---|---|---|
| CC-01 | PASS | 8b3592e 祖先；**care 域精确路径**（`web-java/.../web/care` main+test + `contracts`）`git diff 8b3592e..HEAD`=0（不再宣称全树三目录空——merged 树含 D 变更）；当前源码重建 jar、18081 健康 UP |
| CC-02 | PASS | 5 端点+不存在全等 404（完整公开体仅去 requestId）、codes 全 RESOURCE_NOT_VISIBLE、云台 403 CALLER_NOT_ALLOWED、未认证 401、撤销即时 404、另一 active 授权账号 200；`cC` 谓词语义由 `cc02_verdict` 纯函数 + selfcheck 回归锁定，其余断言未弱化 |
| CC-03 | PASS | 正例 dev+合法绑定先行：A03=201 且 T07 care_executions 真实新增一行；四负例（prod / prod,dev+bound / dev+APP_ENV=production / dev+非法绑定）rc=1 **且逐变体命中具体 fail-fast 签名**（Validator/Guard、真实 provider bean 要求、UUID 解析），无关原因退出与已成功启动均判 FAIL；统一启动封装（三键 env 显式构造 + 完全退出/端口空闲前置 + 新进程健康等待） |
| CC-04 | PASS | 绑定成员 201；异成员 403 FACE_NOT_VERIFIED + T07 零行 + **T13=rejected + 同键重放等值拒绝**；未绑定 503 + T07 零行 + T13 processing；无客户端 memberId 输入路径 |
| CC-05 | PASS | **同一 SENSITIVE_PLAN 贯穿 A01/A02/A03/A08/A09 全 2xx + T07 快照**；五面+快照逐字节无 SECRET 键值、schema_version 不外发；白名单键（title/description/steps/regions/parameters、step.region+parameters、{value,unit}）与 region 保留、`vendor_debug` 收敛 {value,unit}，A01/A09 摘要白名单保留 |
| CC-06 | PASS | **22** 畸形/越界变体逐项严格断言 `409 PLAN_NOT_READY` 且 `details.reason` 精确命中封闭 9-token（device_capabilities_missing/frozen_capability_requirement_missing/malformed_frozen_capability/capability_id_mismatch/parameter_range_not_covered/region_not_supported/n_out_of_bounds/step_parameters_not_covered/malformed_frozen_step）；正例判别力（冻结 rev 7≠设备 9、microcrystal 不同、{value,unit} 单位严格相等）201 |
| CC-07 | PASS | 缺键 4xx；同键重放 200 replayed=true 且 **verification_revision+last_verified_at 均不刷新**（SQL 双字段前后比对）；同键异内容 409 IDEMPOTENCY_CONTENT_CONFLICT |
| CC-08 | PASS | 同微晶并发恰一 201 一 409 **DEVICE_OCCUPIED**；**占用仅 closed 释放**（closed 前再准入 409 / closed 后 201）；**SQL 移动 T03 指针（test_seed）→ 旧任务 A03/A08 均 409 TASK_REPLACED** |
| CC-09 | PASS | duplicate 重放 **disp 非空==2**；首批 HTTP 200；**K=9/10/11 边界**（completed_at 于 K=10 首达、K=11 不改写、K 不截断）；observation 连续性失效不 running、unknown 拒绝 →running、stopped 冻结；**同记录键异内容（不同幂等键）409 RECORD_CONFLICT 零持久化**；溢出 400 count_overflow |
| CC-10 | PASS | 未 stopped 409 STOP_NOT_CONFIRMED；**缺口 409 CLOSURE_GAPS + 有界 missingRanges/more**；水位完整→closed+occupancyReleased；**并发双收尾恰一成功**；**同一收尾键重放 200 且 manifest 逐字节不变**；closed 冻结 + 迟到记录入账且 `closure_manifest.late_variance` 留痕、不重开；**撤销后 A05 最小 ack(progress=null) + A06 仍可收尾 + A07 最小视图**；A07/A08/A09 2xx |
| CC-11 | **INFO** | selftest 10/10、samples 50、OpenAPI VALID；9 个 M4 API（A01-A09）按**实际 HTTP 状态**对应 schema 用 RV-6 严格转换器校验（**不扩展 nullable、不展平 allOf**）。`status_bad=[]`、`impl_bad=[]`（无 C 运行时缺陷）；**13 个不同字段路径契约建模缺陷**（12 处 `nullable:true` 与 `$ref/allOf` 同层不生效→C 按契约意图返回 null 被判 type 违规，含 `A08 $.data.completedAt`；1 处 A08 `ProgressWithSync.lastSyncedAt` 被 `Progress.additionalProperties:false` 经 allOf 误伤）→ **allowlist 四元组精确绑定（API+归一化路径+validator+契约上下文），allowlist 外一律 impl→FAIL，绝不降级 INFO**；如实披露、附条件接受，归属=契约/OAS（openapi.yaml），非 C 实现缺陷 |
| CC-12 | PASS | 矩阵再生成幂等；94 ID 唯一；含 C 场景 blocked_by 不含 C；全部 dependency_pending |

## 替身与依赖区分

- 全部结果为 **doubles_pass**（dev 替身：短信/会话/设备凭据/存储/人脸）；测试种子=直连 SQL，**不等于跨包真实链路**。
- **C-only 驱动未覆盖，已由 CD 链路另验**：M3-A01 真实方案生成与任务替换链路、plan_payload 版本化白名单批准等 C-only 驱动未覆盖项，已由 `run.sh cd-chain` 真实 D 端点+worker 链路另验（见 `backend/handoffs/E-CD-acceptance.md`）；plan_payload 版本化白名单仍待契约冻结裁定。
- **B 待集成**：真实成员授权/撤销、设备凭据、媒体访问策略 → 跨包 E2E dependency_pending。
- 生产人脸：真实 1:1 提供方未接入，C 有意恒 503 fail-closed（三重防线实测成立）。

## C 三项协调请求（各注 owner + dependency_pending）

1. **CareFaceVerifier 是否提升为公共端口**（owner：C / D；dependency_pending）——当前 face 核验端口为 C 域内部接口，D 方案生成链路若需复用需总协调裁定公共化范围与契约。
2. **方案公开白名单批准**（owner：D / 总协调；dependency_pending）——`CarePlanProjection` 递归白名单（title/description/steps/regions/parameters、{value,unit}）为 C 侧保守提案，待 D 契约确认后冻结；未冻结字段 C 保守省略。
3. **能力字段 / steps 形状冻结**（owner：D / 总协调；dependency_pending）——`input_snapshot.capability`（capability_id/parameter_ranges/approved_regions/n_bounds）与 `plan_payload.steps` 形状尚未契约冻结，C 按当前约定防御式读取、形状缺失一律 fail-closed。

## 缺陷

- **已执行的有效检查未观察到 C 缺陷。** 历史两项 FAIL 均归因驱动侧并已闭合：CC-02 谓词 `cC` 写反（另一 active 授权应 200，旧断言误写 404），已修为 `cc02_verdict` 纯函数并由 selfcheck 单测锁定；CC-03 启动封装端口/实例残留（CC-04 恢复重启缺 `stop_java` → 未绑定 JVM 占端口 → 健康冒充 → 正例 503），已改为显式 env + 完全退出确认的统一启动封装。R14 加强的严格契约校验（9 API OAS）亦未发现 C 响应非一致。

## 限制

- 无 worker 参与（care 包零 worker 依赖）；未重跑 C 的 Java 262 项与契约脚本以外的 A/B/D 套件。selfcheck rc=0（72 passed，含 CC-11 结构化未知字段集合/真四元组 allowlist 判别、CC-01 绑定负例回归）。
- 内存紧张，JVM 限堆 `-Xmx640m -XX:MaxMetaspaceSize=256m`，变体串行。
- **CC-11 严格语义下的契约建模缺陷（已发现并升级、待总协调裁定；归属=契约/OAS，openapi.yaml 为契约/A 共享工件，E 无权修）**：共 **13 个不同字段路径**
  （12 处 `nullable:true` 与 `$ref`/`allOf` 同层、OAS 3.0.3 该写法不生效 → C 按契约意图返回 null
  被严格语义判 type 违规；1 处 allOf+additionalProperties）：
  ①nullable 12 路径：`A01 $.data.items[*].progress.completedAt`、`A02 $.data.progress.completedAt`、
  `A03/A04/A05/A07 $.data.progress.completedAt`、`A08 $.data.completedAt`、
  `A03/A04 $.data.verification.validUntil`、`A03/A07 $.data.controller.gimbalId`、
  `A09 $.data.items[*].closedAt`；
  ②`A08 $.data`：`ProgressWithSync` 的 `allOf` 第二分支新增 `lastSyncedAt` 被 `Progress.additionalProperties:false`
  误伤。
  说明：上述为**字段路径级** distinct 计数（列表元素可产生多条实例级错误，如 A01/A09 items[*]）；
  allowlist 按 **(API, 归一化实例路径, validator, absolute_schema_path) 真四元组** 精确绑定，schema path
  不符、未知字段集合**结构化计算**（`instance.keys − schema.properties − patternProperties`）非恰
  `{lastSyncedAt}` 或任何 allowlist 外错误一律 impl→FAIL，绝不降级 INFO。
  均为 openapi.yaml 建模问题，非 C 运行时缺陷；驱动如实按 INFO 披露，**不静默放宽**。
  **状态=已发现并升级，待总协调裁定**（裁定为已知限制，或交 A 修约 openapi.yaml）；**裁定前不视为
  公共契约通过**。
- 其余 type/required/enum 及实际状态对应严格不放宽。

## Merged 候选适用性（aebccc7 = C 8b3592e + D dc955c0）

- C care 域 `git diff 8b3592e..aebccc7`（`web-java/.../web/care` main+test）=0，`backend/contracts` diff=0 → 本报告对 C 的结论在 merged 候选上继续适用。
- 在 merged 树正式重跑 `run.sh c-acceptance`：R18 新 RUN_ID=`E-AB-20260911T111832Z-28c4994f`（settled 14/14，counts={PASS:13,INFO:1}，exit=0，真四元组 allowlist 精确命中 13 路径、impl_bad=[]）；此前 R17 `E-AB-20260911T104353Z-67c653f8`、R16 `E-AB-20260911T102717Z-efcddec8`、R15 `E-AB-20260911T100912Z-0972884c`（同计数）、merged 重跑 `f724f2ba`（14 PASS，旧措辞「三目录 diff 空」已修正为 care 域精确路径，历史 summary 不改写、零覆盖）。
- C+D 真实链路与集成结论见 `backend/handoffs/E-CD-acceptance.md`（证据 `evidence/CD-chain-2026-09-11-aebccc7/`）。
