# E-C 验收（C/M4 护理管理）交接草稿

> 由 E 实施代理起草，供总协调定稿。基线：C 最终代码 `8b3592e`，集成 HEAD `93b7e33`（E 工作树）。
> 证据：`backend/acceptance/evidence/C-acceptance-2026-09-11-8b3592e/`（正式 run，RUN_ID 入口绑定 + 哨兵）。
> Oracle R14（审 `fd18bd4`）判 BLOCKED（5 BLOCKER+1 IMPORTANT+1 SUGGESTION，均为 E 驱动断言强度，未裁 C 新缺陷）；本轮按 findings 加强断言并正式重跑。

## 命令与退出码

- `backend/acceptance/run.sh c-acceptance`：mode=`c-care`，EXPECTED=CC-01..CC-12 + CLEANUP + CLEANUP-ports（14 项唯一结算）。
- 正式跑（当前）：RUN_ID=`E-AB-20260911T090147Z-6d8dbb55`，settled 14/14，counts={PASS:14, FAIL:0, BLOCKED:0, INFO:0}，exit=0；哨兵 `run_id` 入口绑定且 `final_exit==驱动 rc`。
- 历史迭代 run（保留、零覆盖）：`E-AB-20260911T082701Z-73350e3c`（14 PASS）、`E-AB-20260911T081747Z-feeb86d8`（12 PASS / 2 FAIL 驱动侧归因）；连同早期 4 个 run 目录均未被覆盖。
- `run.sh selfcheck` rc=0（63 passed，较上轮 +6 条 R14 负例回归）；`run.sh matrix` rc=3（94 pending、SETTLED 94/94）。

## CC 逐项结论（R14 加强后）

| 项 | 结论 | 说明 |
|---|---|---|
| CC-01 | PASS | HEAD=93b7e33、8b3592e 祖先、`git diff 8b3592e..HEAD -- 三目录` 空、当前源码重建 jar、18081 健康 UP |
| CC-02 | PASS | 5 端点+不存在全等 404（完整公开体仅去 requestId）、codes 全 RESOURCE_NOT_VISIBLE、云台 403 CALLER_NOT_ALLOWED、未认证 401、撤销即时 404、另一 active 授权账号 200；`cC` 谓词语义由 `cc02_verdict` 纯函数 + selfcheck 回归锁定，其余断言未弱化 |
| CC-03 | PASS | 正例 dev+合法绑定先行：A03=201 且 T07 care_executions 真实新增一行；四负例（prod / prod,dev+bound / dev+APP_ENV=production / dev+非法绑定）rc=1 **且逐变体命中具体 fail-fast 签名**（Validator/Guard、真实 provider bean 要求、UUID 解析），无关原因退出与已成功启动均判 FAIL；统一启动封装（三键 env 显式构造 + 完全退出/端口空闲前置 + 新进程健康等待） |
| CC-04 | PASS | 绑定成员 201；异成员 403 FACE_NOT_VERIFIED + T07 零行 + **T13=rejected + 同键重放等值拒绝**；未绑定 503 + T07 零行 + T13 processing；无客户端 memberId 输入路径 |
| CC-05 | PASS | **同一 SENSITIVE_PLAN 贯穿 A01/A02/A03/A08/A09 全 2xx + T07 快照**；五面+快照逐字节无 SECRET 键值、schema_version 不外发；白名单键（title/description/steps/regions/parameters、step.region+parameters、{value,unit}）与 region 保留、`vendor_debug` 收敛 {value,unit}，A01/A09 摘要白名单保留 |
| CC-06 | PASS | **22** 畸形/越界变体逐项严格断言 `409 PLAN_NOT_READY` 且 `details.reason` 精确命中封闭 9-token（device_capabilities_missing/frozen_capability_requirement_missing/malformed_frozen_capability/capability_id_mismatch/parameter_range_not_covered/region_not_supported/n_out_of_bounds/step_parameters_not_covered/malformed_frozen_step）；正例判别力（冻结 rev 7≠设备 9、microcrystal 不同、{value,unit} 单位严格相等）201 |
| CC-07 | PASS | 缺键 4xx；同键重放 200 replayed=true 且 revision 不刷新；同键异内容 409 IDEMPOTENCY_CONTENT_CONFLICT；并发 APP+云台恰一 201 |
| CC-08 | PASS | 同微晶并发恰一 201 一 409 **DEVICE_OCCUPIED**；**占用仅 closed 释放**（closed 前再准入 409 / closed 后 201）；**SQL 移动 T03 指针（test_seed）→ 旧任务 A03/A08 均 409 TASK_REPLACED** |
| CC-09 | PASS | duplicate 重放 **disp 非空==2**；首批 HTTP 200；**K=9/10/11 边界**（completed_at 于 K=10 首达、K=11 不改写、K 不截断）；observation 连续性失效不 running、unknown 拒绝 →running、stopped 冻结；**同记录键异内容（不同幂等键）409 RECORD_CONFLICT 零持久化**；溢出 400 count_overflow |
| CC-10 | PASS | 未 stopped 409 STOP_NOT_CONFIRMED；**缺口 409 CLOSURE_GAPS + 有界 missingRanges/more**；水位完整→closed+occupancyReleased；**并发双收尾恰一成功**；**同一收尾键重放 200 且 manifest 逐字节不变**；closed 冻结 + 迟到记录入账且 `closure_manifest.late_variance` 留痕、不重开；**撤销后 A05 最小 ack(progress=null) + A06 仍可收尾 + A07 最小视图**；A07/A08/A09 2xx |
| CC-11 | PASS | selftest 10/10、samples 50、OpenAPI VALID；**捕获 9 个 M4 API（A01-A09）代表性成功响应，从当前 openapi.yaml 解析 schema（$ref 内联）逐个严格 jsonschema 校验**；错误响应维持基本信封检查（如实分类） |
| CC-12 | PASS | 矩阵再生成幂等；94 ID 唯一；含 C 场景 blocked_by 不含 C；全部 dependency_pending |

## 替身与依赖区分

- 全部结果为 **doubles_pass**（dev 替身：短信/会话/设备凭据/存储/人脸）；测试种子=直连 SQL，**不等于跨包真实链路**。
- **D 待集成**：M3-A01 真实方案生成与任务替换链路、plan_payload 版本化白名单批准 → CC-06/CC-08 任务替换子项 dependency_pending。
- **B 待集成**：真实成员授权/撤销、设备凭据、媒体访问策略 → 跨包 E2E dependency_pending。
- 生产人脸：真实 1:1 提供方未接入，C 有意恒 503 fail-closed（三重防线实测成立）。

## C 三项协调请求（各注 owner + dependency_pending）

1. **CareFaceVerifier 是否提升为公共端口**（owner：C / D；dependency_pending）——当前 face 核验端口为 C 域内部接口，D 方案生成链路若需复用需总协调裁定公共化范围与契约。
2. **方案公开白名单批准**（owner：D / 总协调；dependency_pending）——`CarePlanProjection` 递归白名单（title/description/steps/regions/parameters、{value,unit}）为 C 侧保守提案，待 D 契约确认后冻结；未冻结字段 C 保守省略。
3. **能力字段 / steps 形状冻结**（owner：D / 总协调；dependency_pending）——`input_snapshot.capability`（capability_id/parameter_ranges/approved_regions/n_bounds）与 `plan_payload.steps` 形状尚未契约冻结，C 按当前约定防御式读取、形状缺失一律 fail-closed。

## 缺陷

- **已执行的有效检查未观察到 C 缺陷。** 历史两项 FAIL 均归因驱动侧并已闭合：CC-02 谓词 `cC` 写反（另一 active 授权应 200，旧断言误写 404），已修为 `cc02_verdict` 纯函数并由 selfcheck 单测锁定；CC-03 启动封装端口/实例残留（CC-04 恢复重启缺 `stop_java` → 未绑定 JVM 占端口 → 健康冒充 → 正例 503），已改为显式 env + 完全退出确认的统一启动封装。R14 加强的严格契约校验（9 API OAS）亦未发现 C 响应非一致。

## 限制

- 无 worker 参与（care 包零 worker 依赖）；未重跑 C 的 Java 262 项与契约脚本以外的 A/B/D 套件。selfcheck rc=0（63 passed）。
- 内存紧张，JVM 限堆 `-Xmx640m -XX:MaxMetaspaceSize=256m`，变体串行。
- OAS 严格校验对 `nullable` over `$ref/allOf` 按契约意图解析为可空、并按 OAS 组合语义令 `additionalProperties:false` 不误伤兄弟分支新增属性；其余 type/required/enum 严格不放宽。

## Merged 候选适用性（aebccc7 = C 8b3592e + D dc955c0）

- C care 域 `git diff 8b3592e..aebccc7`（`web-java/.../web/care` main+test）=0，`backend/contracts` diff=0 → 本报告对 C 的结论在 merged 候选上继续适用。
- 在 merged 树正式重跑 `run.sh c-acceptance`：新 RUN_ID=`E-AB-20260911T093819Z-f724f2ba`，settled 14/14，counts={PASS:14,FAIL:0,BLOCKED:0,INFO:0}，exit=0，哨兵 OK；旧 7 个 run 目录零覆盖。
- C+D 真实链路与集成结论见 `backend/handoffs/E-CD-acceptance.md`（证据 `evidence/CD-chain-2026-09-11-aebccc7/`）。
