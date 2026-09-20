# E C/M4 黑盒验收 —— C 8b3592e，run E-AB-20260911T104353Z-67c653f8

> **替身形态（doubles_pass）**：短信/会话/设备凭据/存储/人脸均为 dev 替身；种子=直连 SQL，不等于跨包真实链路。D 真实端点（方案生成、真实任务替换）与 B 真实端点（授权/成员/设备）相关场景仍 dependency_pending。

## 结算：14/14 唯一结算；13 PASS / 0 FAIL / 0 BLOCKED / 1 INFO（计数和=14==行数 14）；final_exit=0

**C/M4 黑盒验收结果：通过（附条件）**——INFO 待披露：['CC-11']。

| 项 | 检查 | 状态 | 命令/rc | 关键摘录 |
|---|---|---|---|---|
| CC-01 | 构建与启动绑定：8b3592e 祖先、**care 域（care main/test + contracts）diff=0**、当前源码构建、health UP@18081 | **PASS** | git merge-base/diff（care 域精确路径）; mvn package; java -jar / 0 | HEAD=d4be14720a75 ancestor=True care_domain_diff=[] jar=web-java-0.0.1-SNAPSHOT.jar sha16=2a74d60d1da75274 |
| CC-02 | 权限/统一 404 三态：A01/A02/A07/A08/A09+不存在 全等 404（完整公开体仅排除 requestId）+ 云台 403 + 未认证 401 + 撤销即时生效 | **PASS** | 多账号 GET 交叉 + 撤销 grant / [404, 404, 404, 404, 404, 404] | public_equal=True codes=['RESOURCE_NOT_VISIBLE', 'RESOURCE_NOT_VISIBLE', 'RESOURCE_NOT_VISIBLE', 'RESOURCE_NOT_VISIBLE', 'RESOURCE_NOT_VISIBLE', 'RESOURCE_NOT_VISIBLE'] gimbal=403/CALLER_NOT_ALLOWED noauth=401 revoked=404 other_active=200 seed_ok=True canon_diff={} flags={'statuses': True, 'equal': True, 'codes': True, 'g403': True, 'n401': True, 'cA': True, 'cB': True, 'cC': True} |
| CC-05 | 嵌套白名单五面+T07：同一 SENSITIVE_PLAN 贯穿 A01/A02/A03/A08/A09 全 2xx，逐字节无 SECRET 键值、schema_version 不外发；白名单键与 region 保留、vendor_debug 收敛 {value,unit} | **PASS** | SENSITIVE_PLAN 全链（列表/full/准入/progress/历史/T07 快照） / 200/200/201/200/200 | forbidden_hit=[] no_schema_version=True vd2={'unit': 'level', 'value': '3'} vd3={'unit': 'level', 'value': '3'} regions_kept=True full_kept=True a01_sum_ok=True proj_ok=True snapshot_len=611 snap_ok=True a09_ok=True |
| CC-06 | 能力严格 fail-closed：22 畸形/越界变体逐项 409 PLAN_NOT_READY 且 reason 命中封闭 9-token 精确值；正例（冻结 rev≠设备 rev、microcrystal 不同、{value,unit} 严格相等）201 判别力 | **PASS** | 逐变体新微晶/新方案种子 + A03（精确 token 断言） / pos=201 unit=201 | observed_tokens=['capability_id_mismatch', 'device_capabilities_missing', 'frozen_capability_requirement_missing', 'malformed_frozen_capability', 'malformed_frozen_step', 'n_out_of_bounds', 'parameter_range_not_covered', 'region_not_supported', 'step_parameters_not_covered'] variants=22 unmatched=[] |
| CC-07 | 幂等与重放：缺键 4xx、同键重放 replayed 且 **verification_revision+last_verified_at 均不刷新**、同键异内容 409 | **PASS** | A03 重放/冲突 / 201/200/409 | nokey=400 same_exec=True replayed=True rev+last_verified 1/2026-09-11 10:44:43.486471+00->1/2026-09-11 10:44:43.486471+00 conflict=True reason=IDEMPOTENCY_CONTENT_CONFLICT |
| CC-08 | 占用/并发：APP+云台同微晶恰一 201 一 409 DEVICE_OCCUPIED；占用仅 closed 释放（closed 前 409 / closed 后 201）；旧任务 A03/A08 → 409 TASK_REPLACED | **PASS** | 并发 + 启停 + SQL 移动 T03 指针（test_seed） / [201, 409] | app/gimbal=201/409 code409=DEVICE_OCCUPIED occ_before=True closed_release=True occ_after=True replaced_a03=True replaced_a08=True(TASK_REPLACED) |
| CC-09 | 账本去重/K/事务/状态机：duplicate 非空==2、首批 200、K=9/10/11 边界（completed_at 首达/不改写/K 不截断）、running 门控+unknown 拒绝、同键异内容 409 零持久化、溢出 400 count_overflow | **PASS** | A05 多批 + SQL 核对 / 200/200/409 | dup=['duplicate', 'duplicate'](acc 12) k9=True K10=10/True K11=11/stable=True gating=True(admitted/unknown/unknown) conflict=True(200/409/RECORD_CONFLICT/0) stopped=stopped overflow=400/count_overflow |
| CC-10 | 收尾对账：未 stopped 409 STOP_NOT_CONFIRMED；缺口 409 CLOSURE_GAPS+有界missingRanges/more；水位完整→closed+occupancyReleased；并发双收尾恰一成功；同键重放 manifest 逐字节不变；closed 冻结+迟到入账 late_variance 不重开；撤销后 A05 最小 ack(progress=null)+A06 仍可收尾+A07 最小视图；A07/08/09 2xx | **PASS** | A06 前后置 + 并发/重放/迟到/撤销（test_seed） / 409/409/200 | stop_err=STOP_NOT_CONFIRMED gaps=True(1,more=False) pair=[200, 409] closed=True released=True manifest_stable=True freeze=True late=True(cnt=1) ack=True close_after_revoke=True minimal=True A07/08/09=200/200/200 |
| CC-11 | 有界严格契约：selftest 10/10 + samples 50 + OpenAPI VALID；9 个 M4 API（A01-A09）按**实际 HTTP 状态**对应 schema 严格校验（RV-6 转换器，不改 OAS 语义、不展平 allOf）；契约建模问题如实披露、绝不静默放宽 | **INFO** | 契约脚本 + 真实生命周期捕获 9 响应（实际状态）严格校验 / 0/0/0 | selftest=True samples=50 oas_ok=True captured=9 actual_status={'A03': 201, 'A05': 200, 'A04': 200, 'A06': 200, 'A01': 200, 'A02': 200, 'A07': 200, 'A08': 200, 'A09': 200} status_bad=[] impl_bad=[] contract_issues=['A03 $.data.controller.gimbalId [contract:nullable:true 与 $ref/allOf 同层（OAS 3.0.3 不生效）→ C 按契约意图返回 null @ ControllerRef.gimbalId]', 'A03 $.data.progress.completedAt [contract:nullable:tru |
| CC-04 | 人脸 1:1 成员绑定（dev 替身）：绑定成员 201；异成员 403 FACE_NOT_VERIFIED+T07 零行+T13 rejected+同键重放等值拒绝；未绑定 503+T07 零行+T13 processing；无客户端 memberId 输入路径 | **PASS** | 三次 JVM 绑定切换 + A03 multipart / 201/403/503 | bound201=True foreign403=True(rows 14->14 t13=rejected replay=403 equal=True) unbound503=True(rows 14->14 t13=processing) noClientMemberField=True |
| CC-03 | 生产人脸 fail-closed：prod / prod,dev / dev+APP_ENV=production / 非法绑定 拒绝启动且每变体命中具体 fail-fast 签名；dev 合法绑定正例 A03 201+T07 创建（判别力） | **PASS** | 逐变体串行启动 JVM（限堆 640m）+ 日志签名断言 / 1,1,1,1 | dev+bound positive(attempt 1): A03=201 T07_created=True / prod-only: rc=1 refused=True sig=real-provider-required evidence='2026-09-11T18:45:25.543Z level=ERROR requestId= logger=o.s.b.d.LoggingFailureAnalysisReporter msg= *************************** APPLICATION FAILED TO START *************************** Description: Parameter 0 of construct' / prod,dev+bound: rc=1 refused=True sig=real-provider- |
| CC-12 | 矩阵维护：再生成幂等；94 ID 唯一；含 C 场景 blocked_by 不含 C；全部仍 dependency_pending | **PASS** | generate_matrix x2 + jq 断言 / 0 | md5_idempotent=True n=94 c_still_blocked=[] |
| CLEANUP | 停进程并按 run 标签删除 mvp-e-pg | **PASS** | docker rm -f -v / 0 |  |
| CLEANUP-ports | 端口释放 | **PASS** | ss / 0 |  |

## C 缺陷清单

（无 FAIL 项）

## 待集成/依赖披露

- D：M3-A01 真实方案生成与任务替换链路、plan_payload 版本化白名单批准 → dependency_pending
- B：真实成员授权/撤销、设备凭据、媒体访问策略 → dependency_pending
- 生产人脸真实 1:1 提供方未接入（C 有意 fail-closed）
