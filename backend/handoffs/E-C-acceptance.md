# E-C 验收（C/M4 护理管理）交接草稿

> 由 E 实施代理起草，供总协调定稿。基线：C 最终代码 `8b3592e`，集成 HEAD `93b7e33`（E 工作树）。
> 证据：`backend/acceptance/evidence/C-acceptance-2026-09-11-8b3592e/`（正式 run，RUN_ID 入口绑定 + 哨兵）。

## 命令与退出码

- `backend/acceptance/run.sh c-acceptance`：mode=`c-care`，EXPECTED=CC-01..CC-12 + CLEANUP + CLEANUP-ports（14 项唯一结算）。
- 正式跑（当前）：RUN_ID=`E-AB-20260911T082701Z-73350e3c`，settled 14/14，counts={PASS:14, FAIL:0, BLOCKED:0, INFO:0}，exit=0；哨兵 `run_id` 入口绑定且 `final_exit==驱动 rc`。
- 历史迭代 run（保留、零覆盖）：RUN_ID=`E-AB-20260911T081747Z-feeb86d8`，settled 14/14，counts={PASS:12, FAIL:2, BLOCKED:0, INFO:0}，exit=1；两 FAIL 均归因驱动侧（见缺陷节），如实保留。
- `run.sh selfcheck` rc=0（57 passed）；`run.sh matrix` rc=3（94 pending、SETTLED 94/94）。

## CC 逐项结论

| 项 | 结论 | 说明 |
|---|---|---|
| CC-01 | PASS | HEAD=93b7e33、8b3592e 祖先、`git diff 8b3592e..HEAD -- 三目录` 空、当前源码重建 jar、18081 健康 UP |
| CC-02 | PASS | 5 端点+不存在全等 404（完整公开体仅去 requestId）、codes 全 RESOURCE_NOT_VISIBLE、云台 403 CALLER_NOT_ALLOWED、未认证 401、撤销即时 404、另一 active 授权账号 200；`cC` 谓词语义由 `cc02_verdict` 纯函数 + selfcheck 回归锁定（防再写反），其余断言未弱化 |
| CC-03 | PASS | 正例 dev+合法绑定先行：A03=201 且 T07 care_executions 真实新增一行；①prod / ②prod,dev+bound / ③dev+APP_ENV=production / ④dev+非法绑定 均 rc=1 拒绝启动（未放宽）。根因（已修）：CC-04 恢复绑定重启缺 `stop_java`，遗留未绑定 JVM 占 18081，健康等待被旧实例冒充 UP，正例请求落到未绑定实例→503；改用统一启动封装（三键 env 显式构造 + 完全退出/端口空闲前置确认 + 新进程健康等待） |
| CC-04 | PASS | 绑定成员 201；异成员 403 FACE_NOT_VERIFIED + T07 零行；未绑定 503 + T07 零行 + T13 processing；无客户端 memberId 输入路径 |
| CC-05 | PASS | A02 full/A01+A08/A03/T07 快照均无 SECRET1/2/3 与 provider_raw_response/prompt；`vendor_debug` 参数名保留但值收敛为 {value,unit}；schema_version 不外发 |
| CC-06 | PASS | 9 变体 8 类 token（malformed_frozen_capability/region_not_supported…）+ steps 畸形 malformed_frozen_step；正例 revision 9≠7 → 201（代表性子集） |
| CC-07 | PASS | 缺键 4xx；同键重放 200 replayed=true 且 revision 1→1 不刷新；同键异内容 409；并发 APP+云台恰一 201 |
| CC-08 | PASS | 同微晶并发恰一 201 一 409 DEVICE_OCCUPIED |
| CC-09 | PASS | 双键判重 duplicate、K 达 completed、同键异内容整批 409 且无新持久化 |
| CC-10 | PASS | 未 stopped 409 STOP_NOT_CONFIRMED；水位完整→closed+occupancyReleased；重放 manifest 不变；A07/A08/A09 2xx |
| CC-11 | PASS | selftest 10/10、samples 50、OpenAPI VALID；200 捕获体严格校验，404/401 基本信封（如实分类） |
| CC-12 | PASS | 矩阵再生成幂等；94 ID 唯一；含 C 场景 blocked_by 不含 C；全部 dependency_pending |

## 替身与依赖区分

- 全部结果为 **doubles_pass**（dev 替身：短信/会话/设备凭据/存储/人脸）；测试种子=直连 SQL，**不等于跨包真实链路**。
- **D 待集成**：M3-A01 真实方案生成与任务替换链路、plan_payload 版本化白名单批准 → CC-06/CC-08 任务替换子项 dependency_pending。
- **B 待集成**：真实成员授权/撤销、设备凭据、媒体访问策略 → 跨包 E2E dependency_pending。
- 生产人脸：真实 1:1 提供方未接入，C 有意恒 503 fail-closed（三重防线实测成立）。

## 缺陷

- 未发现 C 代码缺陷。两项历史 FAIL 均归因驱动侧并已闭合：CC-02 谓词 `cC` 写反（另一 active 授权应 200，旧断言误写 404），已修为 `cc02_verdict` 纯函数并由 selfcheck 单测锁定；CC-03 启动封装端口/实例残留（CC-04 恢复重启缺 `stop_java` → 未绑定 JVM 占端口 → 健康冒充 → 正例 503），已改为显式 env + 完全退出确认的统一启动封装，复跑正例 201+T07 创建、四变体全拒绝。

## 限制

- 无 worker 参与（care 包零 worker 依赖）；未重跑 C 的 Java 262 项与契约脚本以外的 A/B/D 套件。selfcheck rc=0（57 passed，较上轮 +2 条 CC-02/CC-03 回归）。
- 内存紧张，JVM 限堆 `-Xmx640m -XX:MaxMetaspaceSize=256m`，变体串行。
