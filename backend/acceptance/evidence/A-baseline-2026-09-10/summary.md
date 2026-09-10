# E 独立 A 基线验收证据（2026-09-10，run E-AB-20260910T133338Z-a5918d97）

候选基线（config/baseline.json）：code=26d97fbe908cb93c1fe366e28ba54a91c21b497c report=617354d0634c55b9420a3256c619186a1177b3c3 dev=24232d3ccb203d50acfb6aed6b6e74e336654cb0 integrated=df0fa32ee42310d8adfa779f215c8b7a8da80fc7 oracle=round-3 PASS-with-notes

环境：E 专用 PG `mvp-e-pg`@127.0.0.1:55433（label mvp.e.run=E-AB-20260910T133338Z-a5918d97，镜像 postgres:16），Java@18081，worker 健康@18082；94 业务场景保持 dependency_pending（B/C/D 未集成）。

**测试替身标注**：A dev/test 形态使用隔离替身（InMemory 会话 / SMS 固定码 123456 / DB 对照云台凭据 / 文件系统存储），结果均为 `doubles_pass` 语义，**不宣称真实供应商或真实设备接入**。

**运行时边界集成验证**：AB-06d 使用 E 驱动进程内导入的真实 `mvp_worker` runtime + E 专属 PG + 受控测试回调，**非 HTTP 链路**，不改 A 源码。

## 结算：52/52 唯一结算；50 PASS / 1 FAIL / 0 BLOCKED / 1 INFO（计数和=52==行数 52）；final_exit=1

结算缺口：missing=[] extra=[] duplicates=[] unknown=[]

**A 基础验收结论：未通过**——1 项 FAIL / 0 项 BLOCKED（见下）；待 A 修复后绑定新 A SHA 定向重验；在此之前不得表述为“A 已通过验收”。

| 项 | 检查 | 状态 | 命令/rc | 关键摘录 |
|---|---|---|---|---|
| SETUP-pg | 启动 E 专用 PG（mvp-e-pg@55433，label=本 run） | **PASS** | docker run --label mvp.e.run=... postgres:16 / 0 | UP |
| AB-01a | Java 构建（-DskipTests package）产出可运行 jar | **PASS** | mvn -B -q -DskipTests package / 0 |  |
| AB-09a/N1j | Java 目标测试（真实类）：SchemaVersionBoundaryTest（N1 服务层整数校验） + ProductionFailClosedTest（N3 fail-closed，targeted） | **PASS** | mvn -B -q test -Dtest=SchemaVersionBoundaryTest,ProductionFailClosedTest / 0 | 21:33:48.617 [main] ERROR cn.yuanxin.mvp.web.config.ProductionFailClosedValidator -- production fail-closed: unsafe production configuration -> [SessionProvider=absent, SmsCodeProvider=absent, DeviceCredentialProvider=absent, FaceProvider=absent, StoragePort=absent] (configure app.providers.mode=rea |
| AB-09b | jcs.py selftest（17 向量权威数对） | **PASS** | scripts/jcs.py selftest / 0 | selftest: PASS (26 checks, 23 number pairs) |
| AB-09c | validate_samples.py（样例+向量重算） | **PASS** | scripts/validate_samples.py / 0 | RESULT: PASS — all samples valid, all canonicalization vectors match |
| AB-09d | openapi_spec_validator（基础契约） | **PASS** | python -c validate(openapi.yaml) / 0 | OPENAPI VALID |
| AB-10a | fail-closed black-box：prod+doubles 启动被拒且日志含具体原因行 | **PASS** | java -jar (SPRING_PROFILES_ACTIVE=prod, prod+doubles) / 1 | exited=True reason_line=True : SessionProvider=doubles/disabled only |
| AB-10b | fail-closed black-box：prod+owner-dev 启动被拒且日志含具体原因行 | **PASS** | java -jar (SPRING_PROFILES_ACTIVE=prod, prod+owner-dev) / 1 | exited=True reason_line=True : app.media.access-mode=owner-dev |
| AB-10c | fail-closed black-box：prod+allow-any 启动被拒且日志含具体原因行 | **PASS** | java -jar (SPRING_PROFILES_ACTIVE=prod, prod+allow-any) / 1 | exited=True reason_line=True : app.media.allow-any-authenticated=true |
| AB-01b | Java dev 启动 + /actuator/health UP（健康绑定子进程存活） | **PASS** | java -jar (SERVER_PORT=18081, db=mvp_e_dev) / 0 | first pid=3443044 |
| AB-01c | SIGTERM 停止 → 再启动 UP；Flyway no-op（重复启动无破坏） | **PASS** | restart cycle / 0 | second UP=True; flyway_noop=True |
| AB-03 | 全新 E 库 Flyway V1+V2 迁移：14 表（实际 14），版本=1,2 | **PASS** | fresh db migrate via app start / 15 | missing=[] extra=[] history=1,2 success_rows=2 |
| AB-02a | worker --check 连通自检（E 库） | **PASS** | python -m mvp_worker --check / 0 | PostgreSQL server_version: 16.15 (Debian 16.15-1.pgdg13+2) |
| AB-02b | worker 运行循环 + /healthz /readyz UP（健康绑定本 run 子进程存活） | **PASS** | python -m mvp_worker (loop) / 0 | healthz=UP readyz=UP |
| AB-02c | SIGTERM 优雅停机：真实 Popen wait 后 returncode==0 且日志见停机行 | **PASS** | proc.send_signal(SIGTERM) → proc.wait() / 0 | graceful_log=True（未依赖已清空变量） |
| AB-02d | E 定向执行 worker pytest（claim/renew/expire/complete/attempt-ceiling/unsupported；E 专属 PG 临时库，绝不混 A 库） | **PASS** | pytest -q tests/test_claim.py tests/test_renew.py tests/test_expire.py tests/test_complete.py tests/test_attempt_ceiling.py tests/test_unsupported.py / 0 | passed=26 : 26 passed in 5.41s |
| N1-db | JSONB 写入边界（DB object+number CHECK）：非对象/null/字符串/bool/缺键拒绝，整数接受；小数/负数 DB 放行=已知限制（服务层兜底） | **PASS** | psql INSERT async_jobs.payload 变体 / 0/1 | array:rej null_version:rej string_version:rej bool_version:rej missing_key:rej int1:accept fractional:accept negative:accept |
| AB-04a | 约束负例最小父链种子 | **PASS** | psql seed / 0 | INSERT 0 6 INSERT 0 1 INSERT 0 1 INSERT 0 1 INSERT 0 1 INSERT 0 1 INSERT 0 1 INSERT 0 1 INSERT 0 1 |
| AB-04b | 同一微晶第二个未收尾执行 → 拒绝（双占用）（拒因含 uq_execution_open_microcrystal） | **PASS** | psql negative INSERT / 1 | constraint_seen=True |
| AB-04c | 同一执行重复源三元组记录 → 拒绝（双记录）（拒因含 uq_record_source） | **PASS** | psql negative INSERT / 1 | constraint_seen=True |
| AB-04d | app 控制端缺 account/installation → 控制端归属 CHECK 拒绝（拒因含 ck_execution_controller_ownership） | **PASS** | psql negative INSERT / 1 | constraint_seen=True |
| AB-04e | active 通知目标无 registration → CHECK 拒绝（拒因含 ck_destination_active_fields） | **PASS** | psql negative INSERT / 1 | constraint_seen=True |
| AB-04f | T13 (principal,operation,key) 重复 → 拒绝（拒因含 uq_idem_principal） | **PASS** | psql negative INSERT / 1 | constraint_seen=True |
| AB-04g | members (identity_namespace,face_subject_ref) 双非空重复 → 拒绝（拒因含 uq_members_identity） | **PASS** | psql negative INSERT / 1 | constraint_seen=True |
| AB-04h | skin_assessments 非法 status → CHECK 拒绝（拒因含 ck_assessment_status） | **PASS** | psql negative INSERT / 1 | constraint_seen=True |
| AB-04i | skin_assessments current_photo_version=0 → CHECK 拒绝（拒因含 ck_assessment_current_photo_version） | **PASS** | psql negative INSERT / 1 | constraint_seen=True |
| AB-05a | 无 token → 401 AUTH_REQUIRED 信封 | **PASS** | GET /me/member-access-grants / 401 | {"requestId": "559d5059-4357-46d9-9490-aa2d76b81228", "error": {"code": "AUTH_REQUIRED", "message": "missing bearer token", "retryable": false}} |
| AB-05b | 伪造 Bearer → 401 SESSION_INVALID | **PASS** | GET with forged token / 401 | {"requestId": "a01e8bf2-cbd4-4a93-a2ac-383e8caa8d7f", "error": {"code": "SESSION_INVALID", "message": "session token invalid or expired", "retryable": false}} |
| AB-05c | 手机号会话建立（SMS 替身 123456 + installationId） | **PASS** | POST sms-challenges→sessions / 200 | accountId=e57f484d-3b3a-4b6e-95cc-02e62f1a7b20 前置有效码=501 |
| AB-05d | refresh 轮换后旧 refresh token → 401 SESSION_INVALID（独立会话） | **PASS** | POST session-refreshes (old reused) / 200/401 | {"requestId": "9a4a45c5-0e2f-48fe-b390-dc50fc321a64", "error": {"code": "SESSION_INVALID", "message": "refresh credential invalid or rotated", "retryable": false}} |
| AB-05e | 账号 disabled 后旧 token → 401 SESSION_INVALID（每请求复核） | **PASS** | 独立会话 → 变更真实 accountId → GET / 501->401 | rows_changed=1 account=e57f484d |
| AB-05f | auth_revision 递增后旧 token → 401（撤销代次不可复活） | **PASS** | 独立会话 → 变更真实 accountId → GET / 501->401 | rows_changed=1 account=e57f484d |
| AB-05g | revision 变更后重新登录成功且新会话有效（非仅返回 200） | **PASS** | POST sessions again + GET / 200 | new_session_valid=True |
| AB-05h | 云台凭据轮换后旧云台 token → 401（独立云台会话，影响行数=1） | **PASS** | gimbal-sessions → rotate → old token GET / 200/501->401 | rows_changed=1 |
| AB-06a | echo POST → 200 queued + jobId | **PASS** | POST /system/echo-jobs (Idempotency-Key) / 200 | {"requestId": "162c99b6-7672-469d-962e-7b9eee2833a9", "data": {"jobId": "d759758b-60d6-4ad3-b57f-59923a3c6c82", "dedupKey": "system:echo:6ded4f67-37eb-4050-8b7d-6e563bdc0b41", "status": "queued"}, "meta": {"replayed": false, "serverTime": "2026-09-10 |
| AB-08a | T13 同 Idempotency-Key 同内容重放 → 同 jobId + meta.replayed=true | **PASS** | POST same key/content / 200 | replayed=True same_job=True |
| AB-08b | T13 同键不同内容 → 409 冲突（非 200/假成功） | **PASS** | POST same key/different content / 409 | {"requestId": "e68a28ad-8c42-49a6-9ea5-3c477e59718d", "error": {"code": "IDEMPOTENCY_CONTENT_CONFLICT", "message": "Idempotency-Key reused with different request content; use a new key for a new logic |
| AB-06b | worker --once 领取并处理本次 enqueued job（日志含 jobId 或状态推进） | **PASS** | python -m mvp_worker --once / 0 | job=d759758b status=succeeded |
| AB-06c | GET echo job → succeeded + attemptCount=1 + leaseRevision=1 | **PASS** | GET /system/echo-jobs/{id} / 200 | status=succeeded attempt=1 lease=1 |
| AB-11a | 非法输入 → 400 INVALID_INPUT 信封，X-Request-Id==body.requestId（均非空） | **PASS** | POST /system/echo-jobs {} / 400 | rid_hdr=94a554a5-1ed3-47fd-9cd6-8d61b7ce8149 rid_body=94a554a5-1ed3-47fd-9cd6-8d61b7ce8149 |
| AB-11b | 业务 stub（有 token）→ 501 NOT_IMPLEMENTED，不给假 200 | **PASS** | GET /me/member-access-grants / 501 | {"requestId": "a029c883-029c-48fd-b58e-4b30b61f7652", "error": {"code": "NOT_IMPLEMENTED", "message": "business endpoint is contract-only and not implemented yet", "retryable": false, "details": {"api |
| AB-11c | 未知资源 → 404 结构化信封（含 requestId） | **PASS** | GET /system/echo-jobs/<random> / 404 | {"requestId": "45d187c8-a948-4575-b55c-bea745eebf2f", "error": {"code": "RESOURCE_NOT_VISIBLE", "message": "job not visible", "retryable": false}} |
| N2-http | 诊断列 HTTP 投影：须脱敏/限大小/不原样返回（实测 data.lastError） | **FAIL** | 诊断 UPDATE RETURNING count==1 + GET 断言 200/目标 job → 判定 / 200/200 | marker: marker 原样回显（len=95） | long: 未限大小（len=4058 > 1000） |
| N3-media | 媒体 deny-all：任何 GET 统一 404（含 face purpose、含真实上传者本人、无 403 泄露） | **PASS** | 真实上传者主体 GET /media/{id}/content / 404/404 | uploader_self_404=True no_403=True uploader=e57f484d |
| AB-07a | 过期 running 租约回收 → queued + lease_revision+1 + 释放 owner（条件更新） | **PASS** | worker --recover / 0 | status=queued lease_revision=2 owner=NULL |
| AB-06d | 陈旧代次同事务回滚 + 重试上限（运行时边界集成，非 HTTP；受控回调在 E 驱动内） | **PASS** | python ab06d_runtime.py（真实 mvp_worker runtime + E 专属 PG） / 0 | ceiling={'claimed': True, 'recovered': 1, 'status': 'failed', 'attempt': 1, 'max': 1, 'code': 'RETRY_LIMIT_EXCEEDED', 'retryable': False, 'second_recover': 0} stale={'raised': 'StaleGeneration', 'sentinel_rows': 0, 'old_revision': 1} |
| N1-py-schema | Python echo payload schema：string/null/bool/1.5/-2/不支持版本/数组/缺字段拒绝 | **PASS** | python -c EchoHandler().validate(变体) / 0 | string:REJECT null:REJECT bool:REJECT fractional:REJECT negative:REJECT unsupported:REJECT array:REJECT missing:REJECT |
| N1-py-runtime | Python 运行时拒绝非法 schema_version（failed/UNSUPPORTED_CONTRACT，不循环） | **PASS** | worker --once 处理坏版本 job / 0/1 | 45c382:failed/UNSUPPORTED_CONTRACT 45c382:failed/UNSUPPORTED_CONTRACT 45c382:failed/UNSUPPORTED_CONTRACT |
| N2-db | 五诊断列豁免：无 schema_version 可写；CHECK 定义不含这些诊断列 | **PASS** | UPDATE async_jobs.last_error 无版本 + 查 pg_constraint / 0 | no_check_on_diag_cols=True |
| N2-codereview | 诊断列消费点分类检视（23 处，待人工复核 9 处，客户端投影=True） | **INFO** | grep Java/Python src + file:line/片段/分类记录 / 0 | hits=23 uncertain=9 详见 logs/n2-code-review.md（有未判定项，降为 INFO，不作为 PASS 依据） |
| CLEANUP | 停 Java/worker、按 run 标签删除本 run 的 mvp-e-pg | **PASS** | docker rm -f -v mvp-e-pg (label mvp.e.run) / 0 |  |
| CLEANUP-ports | 端口释放：18081 free=True 18082 free=True 55433 free=True | **PASS** | ss probe / 0 |  |

## INFO 附条件项（待人工复核）

- **N2-codereview** 诊断列消费点分类检视（23 处，待人工复核 9 处，客户端投影=True）；hits=23 uncertain=9 详见 logs/n2-code-review.md（有未判定项，降为 INFO，不作为 PASS 依据）

## A 缺陷清单（如实；未修 A 源码）

- **N2-http** 诊断列 HTTP 投影：须脱敏/限大小/不原样返回（实测 data.lastError）；命令=诊断 UPDATE RETURNING count==1 + GET 断言 200/目标 job → 判定；rc=200/200；摘录=marker: marker 原样回显（len=95） | long: 未限大小（len=4058 > 1000）

## 逐项细节与边界

- N1 Java 服务层：`SchemaVersionBoundaryTest`（真实 IdempotencyService.ensureSchemaVersion 类：缺省注入 1/显式整数/null/字符串/小数/非对象 → 400 INVALID_INPUT）；HTTP 层无可由客户端控制的 schema_version 输入（echo 摘要由服务端注入整数 1），故服务层用真实类测试验证。
- N1 Python 服务层：`EchoHandler.validate` targeted 直调 + 真实运行时坏版本 job → failed/UNSUPPORTED_CONTRACT。
- N1 DB 已知限制：object+number CHECK 放行小数/负数 JSON number，由服务层兜底（A 报告未决项 9）。
- AB-02d：E 定向执行与基础/恢复/版本直接相关的 worker 测试文件（见命令），DSN 指向 E 专属 PG 临时库（MVP_A_PG_CONTAINER=mvp-e-pg / HOST_PORT=55433），绝不混用 A 库/容器；与本轮无关的全量重跑按'避免重复无关单测'排除。
- AB-06d：运行时边界集成验证（claim/recover/complete 公共运行时 + E PG + E 驱动内受控 business_tx 哨兵），非 HTTP；未改 A 源码。
- AB-10 黑盒启动拒绝（缺真实提供方/unsafe media）与 targeted ProductionFailClosedTest（媒体开关）在 AB-10a-c 与 AB-09a/N1j 分列陈述。
- 证据日志：reports/E-AB-20260910T133338Z-a5918d97/ 与 logs/ 摘录（非空）。
- A 缺陷：见上表 FAIL 项与上方“A 缺陷清单”；本轮未修 A 源码。
- 清理：按 label 归属删除 mvp-e-pg，Java/worker 进程与端口释放。
