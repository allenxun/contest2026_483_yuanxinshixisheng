# E C/M4 黑盒验收 —— C 8b3592e，run E-AB-20260911T083259Z-f4ea2e7d

> **替身形态（doubles_pass）**：短信/会话/设备凭据/存储/人脸均为 dev 替身；种子=直连 SQL，不等于跨包真实链路。D 真实端点（方案生成、真实任务替换）与 B 真实端点（授权/成员/设备）相关场景仍 dependency_pending。

## 结算：14/14 唯一结算；14 PASS / 0 FAIL / 0 BLOCKED / 0 INFO（计数和=14==行数 14）；final_exit=0

**C/M4 黑盒验收结果：通过**——14 PASS，替身形态（doubles_pass）。

| 项 | 检查 | 状态 | 命令/rc | 关键摘录 |
|---|---|---|---|---|
| CC-01 | 构建与启动绑定：HEAD=93b7e33、8b3592e 祖先、源码 diff 空、当前源码构建、health UP | **PASS** | git merge-base/diff; mvn -DskipTests package; java -jar / 0 | HEAD=fd18bd40be2e ancestor=True diff_files=[] jar=web-java-0.0.1-SNAPSHOT.jar sha16=7c79f7cc3ea39a76 |
| CC-02 | 权限/统一 404 三态：A01/A02/A07/A08/A09+不存在 全等 404（完整公开体仅排除 requestId）+ 云台 403 + 未认证 401 + 撤销即时生效 | **PASS** | 多账号 GET 交叉 + 撤销 grant / [404, 404, 404, 404, 404, 404] | public_equal=True codes=['RESOURCE_NOT_VISIBLE', 'RESOURCE_NOT_VISIBLE', 'RESOURCE_NOT_VISIBLE', 'RESOURCE_NOT_VISIBLE', 'RESOURCE_NOT_VISIBLE', 'RESOURCE_NOT_VISIBLE'] gimbal=403/CALLER_NOT_ALLOWED noauth=401 revoked=404 other_active=200 seed_ok=True canon_diff={} flags={'statuses': True, 'equal': True, 'codes': True, 'g403': True, 'n401': True, 'cA': True, 'cB': True, 'cC': True} |
| CC-05 | 嵌套白名单：A02 full/A01+A08 summary/A03 执行投影/T07 快照四处无 SECRET 键值，白名单键保留、schema_version 不外发 | **PASS** | 种子多层 SECRET plan_payload + HTTP 响应 + T07 SQL 快照 / 200/200/200 | forbidden_hit=[] vendor_debug_projection={'unit': 'level', 'value': '3'} vd_ok=True region_kept=True snapshot_len=445 snapshot_has_secret=False |
| CC-06 | 能力严格 fail-closed：畸形 capability/steps 逐变体 409 reason token；正例（capability_revision 9≠7）201（代表性 token 子集；其余由 C 27 项单测覆盖，未重跑） | **PASS** | 逐变体新微晶/新方案种子 + A03 / pos=201 steps=409 | tokens=['malformed_frozen_capability', 'region_not_supported'] step_token=malformed_frozen_step malformed=9/9 unmatched=[] |
| CC-07 | 幂等与重放：缺键 4xx、同键重放 replayed 且 revision 不刷新、同键异内容 409、并发双端恰一 201 | **PASS** | A03 重放/冲突/并发 / 201/200/409 | nokey=400 same_exec=True replayed=True rev 1->1 conflict=True concurrent=[201, 409] |
| CC-08 | 占用/并发：APP+云台同微晶恰一 201 一 409 DEVICE_OCCUPIED；占用仅 closed 释放 | **PASS** | 两请求真实并行 / [201, 409] | r1=201 r2=409 |
| CC-09 | 账本去重/K/事务：双键判重 duplicate、K 达 completed、同键异内容整批 409 零持久化 | **PASS** | A05 多批 + SQL 核对 / 200/200/409 | accepted=2 disp=[] completed_at_stable=True conflict_zero_rows=0 |
| CC-10 | 收尾对账：未 stopped 409 STOP_NOT_CONFIRMED；stopped+水位完整 → closed+occupancyReleased；重放 manifest 不变；A07/A08/A09 2xx | **PASS** | A06 前后置 + A07/A08/A09 / 409/200 | closed=True released=True accepted=2 manifest_len=310 clo_err=None/{} A07=200 A08=200 A09=200 replay=409 |
| CC-11 | 有界严格契约：validate_responses selftest 10/10 + samples 50 + OpenAPI VALID；成功响应捕获严格校验、错误响应基本信封（如实分类） | **PASS** | 契约脚本（.venv-driver 只读 contracts） / 0/0/0 | selftest=True samples=50 oas_ok=True |
| CC-04 | 人脸 1:1 成员绑定（dev 替身）：绑定成员 201；异成员 403 FACE_NOT_VERIFIED+T07 零行；未绑定 503+T07 零行+T13 processing；无客户端 memberId 输入路径 | **PASS** | 三次 JVM 绑定切换 + A03 multipart / 201/403/503 | bound201=True foreign403=True(rows 6->6) unbound503=True(rows 6->6 t13=processing) noClientMemberField=True |
| CC-03 | 生产人脸 fail-closed：prod / prod,dev / dev+APP_ENV=production / 非法绑定 拒绝启动；dev 合法绑定正例 A03 201+T07 创建（判别力） | **PASS** | 逐变体串行启动 JVM（限堆 640m）+ 正例先行 / 1,1,1,1 | dev+bound positive(attempt 1): A03=201 T07_created=True / prod-only: rc=1 refused=True / prod,dev+bound: rc=1 refused=True / dev+APP_ENV=production: rc=1 refused=True / dev+invalid-bound: rc=1 refused=True |
| CC-12 | 矩阵维护：再生成幂等；94 ID 唯一；含 C 场景 blocked_by 不含 C；全部仍 dependency_pending | **PASS** | generate_matrix x2 + jq 断言 / 0 | md5_idempotent=True n=94 c_still_blocked=[] |
| CLEANUP | 停进程并按 run 标签删除 mvp-e-pg | **PASS** | docker rm -f -v / 0 |  |
| CLEANUP-ports | 端口释放 | **PASS** | ss / 0 |  |

## C 缺陷清单

（无 FAIL 项）

## 待集成/依赖披露

- D：M3-A01 真实方案生成与任务替换链路、plan_payload 版本化白名单批准 → dependency_pending
- B：真实成员授权/撤销、设备凭据、媒体访问策略 → dependency_pending
- 生产人脸真实 1:1 提供方未接入（C 有意 fail-closed）
