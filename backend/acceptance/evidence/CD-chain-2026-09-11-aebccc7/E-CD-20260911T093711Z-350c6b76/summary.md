# E C+D 集成链路验收 —— merged aebccc7（C 8b3592e + D dc955c0），run E-CD-20260911T093711Z-350c6b76

> **替身形态（doubles_pass）**：D 三提供方（face/skin/plan）为受控确定性替身；B 未集成（成员/授权/设备/媒体以 SQL 种子 test_seed 提供）；媒体业务读取 404（deny-all）为预期。

## 结算：10/10 唯一结算；10 PASS / 0 FAIL / 0 BLOCKED / 0 INFO（计数和=10==行数 10）；final_exit=0

**C+D 集成链路验收结果：通过**——10 PASS，替身形态（doubles_pass）。

| 项 | 检查 | 状态 | 命令/rc | 关键摘录 |
|---|---|---|---|---|
| CD-01 | 集成状态绑定：HEAD=aebccc7、C 8b3592e/D dc955c0 祖先、care 路径 diff=0、contracts diff=0、当前源码构建、worker venv 就绪、health UP@18081 | **PASS** | git merge-base/diff; mvn package; java -jar; deps import / 0 | HEAD=aebccc773a9e C_anc=True D_anc=True care_diff=[] contracts_diff=[] jar_sha16=2a74d60d1da75274 worker_deps=True health=True |
| CD-02 | 剩余占位定向验证：11 个 B 域占位端点（M1/M2/M5）逐个已认证 HTTP 501 NOT_IMPLEMENTED；未认证 401（B 待集成边界如实） | **PASS** | 逐端点真实 HTTP / n=11 | bad=[] unauth=401 routes=POST /api/v1/member-access-grants=501/NOT_IMPLEMENTED; GET /api/v1/me/member-access-grants=501/NOT_IMPLEMENTED; POST /api/v1/gimbals/{G}/heartbeats=501/NOT_IMPLEMENTED; GET /api/v1/gimbals/{G}/status=501/NOT_IMPLEMENTED; POST /api/v1/microcrystal-observations=501/NOT_IMPLEMENTED; GET /api/v1/microcrystals/{U}/capabilities=501/NOT_IMPLEMENTED; PUT /api/v1/me/gimbal-bindings |
| CD-03 | 报告→方案真实链（冻结字段互通）：B 前置 test_seed（gimbal/T04 设备能力）→ 真实 M3-A01 受理 → worker analyze/enroll/analyze → T06 由 D 发布事务唯一创建（waiting_inputs、generation_revision=0、input_photo_version=1、assessment 唯一）→ plan.generate → ready：冻结 capability/steps 形状完整、D 未写 K 列 | **PASS** | M3-A01 + 真实 worker 全链 / a01=202 ready=ready | flags[wait,rev,ipv,dup,ready,cap,steps,K]=True,True,True,True,True,100,True,True task=a9740fed-f893-4e87-b17f-de94236353f2 plan=52dbdaf6-d4f3-4da7-a570-046f5811ba02 waiting_seen=waiting_inputs cap={"n_bounds": {"max": 100, "min": 1}, "capability_id": "mvp-double-capability", "microcrystal_id": "577a64e4-86f3-4e00-adbd-824d8521b2d8", "approved_regions": ["forehead", "left_cheek", "right_cheek", ste |
| CD-04 | C 准入消费真实 D 冻结方案：对 CD-03 真实 ready T06（非种子）执行 C A03 准入（dev 人脸绑定）→ 201+T07 创建；能力校验器接受 D 真实冻结基线（双侧 unit/区域/N bounds 实际值） | **PASS** | A03 on real D plan + SQL capability evidence / 201 | frozen_capability_id=mvp-double-capability frozen_ranges={"duration": {"max": 600.0, "min": 1.0, "unit": "second"}, "intensity": {"max": 100.0, "min": 0.0, "unit": "percent"}, "pulse_count": {"max": 1000.0, "min": 1.0, "unit": "count"}} device_ranges={"duration": {"max": 600.0, "min": 1.0, "unit": "second"}, "intensity": {"max": 100.0, "min": 0.0, "unit": "percent"}, "pulse_count": {"max": 1000.0, |
| CD-05 | 任务替换 vs 准入竞争（真实链路）：真实 M3-A01 受理触发 T03 指针原子替换（非 SQL 种子）；替换前云台 A03=201、替换后旧任务 A03=409 TASK_REPLACED；A08 面：真实链路旧执行已 closed→404（生命周期冻结先于指针），另以 test_seed 指针移动在 admitted 执行上验证 A08=409 TASK_REPLACED；时序化窗口一致（无悬挂/无二者皆成）；CC-08 种子化 TASK_REPLACED 保留边界单测 | **PASS** | M3-A01 + C A03/A08 时序竞争 / 201/409 | pre201=True(ex=dcc4d7d9-b7f9-48f1-a8f3-916efbbfc536) replaced=True(a2=2f361a71-3e98-4d5d-9906-129ebf30589c) post_a03=409/TASK_REPLACED a08_real=404/RESOURCE_NOT_VISIBLE a08_boundary=409/TASK_REPLACED consistent=True |
| CD-06 | D 公共 success/failure/defer 回归（黑盒）：success=全链 job succeeded 且 worker 日志 stale_generation=0；defer=plan.generate 能力等待跳（T12 queued、attempt=0、lease 轮换、T06 generation_revision=0 不变；T13 不适用）；failure=确定性配置故障 → PLAN_SNAPSHOT_INVALID 终态原子写（T06 无 ready 半成品、T12 同 failed） | **PASS** | worker --once 步进 + SQL 终态核对 / stale=0 | succeeded_jobs=3 stale_warnings=0 gen_ready=True defer={'id': '589b3763-34da-44ce-bde2-f46b40bf76b8', 'status': 'queued', 'attempt': '0', 'lease_revision': '16', 'generation_revision': '0'} t13=not-applicable(worker T12 defer) failure=a3=a09f991e-9e21-493e-9c5a-321e1b351b46 accept=202 p3=46402970-2fc3-4b1a-b11c-c67ed787abf2 status=failed job=failed ready_rows=0 detail={"code": "PLAN_SNAPSHOT_INVAL |
| CD-07 | 矩阵诚实维护：blocked_by=owner−已集成{C,D} → []×54 / B×40；owner/94 ID/业务语义逐字节不变（三字段剔除哈希 e4f5dc52）；pending_reason 分类细化（C/D 已集成已验收 / B 未集成 501）；再生成幂等；gate closed、94 pending | **PASS** | generate_matrix x2 + jq 断言 / 0 | dist={'B': 40, '': 54} idempotent=True hash3=e4f5dc522fe60a83db47d7e42b595652 n=94 |
| CD-08 | 诚实披露与证据纪律：全部 doubles_pass；B 依赖逐项 dependency_pending（11 端点 501 + 媒体读取 deny-all）；不声称完整 MVP；既有证据目录零覆盖；D 待接线如实转录（media.cleanup 周期触发 / enroll failed 槽位运维恢复 / 真实供应商前提） | **PASS** | 证据/披露静态核对 / 0 | b_stub_endpoints=11 zero_overwrite=True doc_wiring=True doc_exists=True |
| CLEANUP | 停进程并按 run 标签删除 mvp-e-pg | **PASS** | docker rm -f -v / 0 |  |
| CLEANUP-ports | 端口释放（Java/PG/worker） | **PASS** | ss / 0 |  |

## 缺陷清单

（无 FAIL 项）

## B 待集成清单

- M1/M2/M5 共 11 个端点 501 NOT_IMPLEMENTED（成员授权/云台心跳状态/微晶观察/绑定/通知）。
- 媒体业务读取（contentUrl 实际下载）待 B 统一 @Primary MediaAccessPolicy（当前 deny-all → 404）。
- 真实成员授权/撤销、设备凭据、媒体访问策略端到端。

## D 待接线事项（如实转录）

- media.cleanup 周期触发/崩溃孤儿扫描接线（D 提供幂等 discover_and_enqueue_orphans+handler）。
- enroll 终态 failed 槽位保持占用，受控恢复=运维对账后置 cancelled/succeeded。
- 真实供应商激活前提（凭据+PoC+设备团队批准基线，provenance mismatch fail-closed）。
