# E 独立 A 基线验收证据（2026-09-10，run E-AB-20260910T124722Z）

候选基线（config/baseline.json）：code=26d97fbe908cb93c1fe366e28ba54a91c21b497c report=617354d0634c55b9420a3256c619186a1177b3c3 dev=24232d3ccb203d50acfb6aed6b6e74e336654cb0 integrated=df0fa32ee42310d8adfa779f215c8b7a8da80fc7 oracle=round-3 PASS-with-notes

环境：E 专用 PG 容器 `mvp-e-pg`@127.0.0.1:55433（镜像 postgres:16），Java@18081，worker 健康@18082；run.sh matrix 的 94 业务场景保持 dependency_pending（B/C/D 未集成）。

**测试替身标注**：A dev/test 形态使用隔离替身（InMemory 会话 / SMS 固定码 123456 / DB 对照云台凭据 / 文件系统存储），以下结果均为 `doubles_pass` 语义，**不宣称真实供应商（短信/会话/人脸/OSS）或真实设备接入**。

## 汇总：48 PASS / 0 FAIL / 2 BLOCKED

| 项 | 检查 | 状态 | 命令/rc | 关键摘录 |
|---|---|---|---|---|
| SETUP-pg | 启动 E 专用 PG（mvp-e-pg@55433，镜像 postgres:16） | **PASS** | docker run ... postgres:16 / 0 | UP |
| AB-01a | Java 构建（-DskipTests package）产出可运行 jar | **PASS** | mvn -B -q -DskipTests package / 0 |  |
| AB-09a/N1j | Java 目标测试：SchemaVersionBoundaryTest + ProductionFailClosedTest | **PASS** | mvn -B -q test -Dtest=SchemaVersionBoundaryTest,ProductionFailClosedTest / 0 | 20:47:31.733 [main] ERROR cn.yuanxin.mvp.web.config.ProductionFailClosedValidator -- production fail-closed: unsafe production configuration -> [SessionProvider=absent, SmsCodeProvider=absent, DeviceCredentialProvider=absent, FaceProvider=absent, StoragePort=absent] (configure app.providers.mode=rea |
| AB-09b | jcs.py selftest（17 向量权威数对） | **PASS** | scripts/jcs.py selftest / 0 | selftest: PASS (26 checks, 23 number pairs) |
| AB-09c | validate_samples.py（样例+向量重算） | **PASS** | scripts/validate_samples.py / 0 | RESULT: PASS — all samples valid, all canonicalization vectors match |
| AB-09d | openapi_spec_validator（基础契约） | **PASS** | python -c validate(openapi.yaml) / 0 | OPENAPI VALID |
| AB-10 | fail-closed：production 非默认 media/开放开关/缺真实提供方拒绝启动 | **PASS** | 启动 3 种 production 变体并观察退出 / see logs | prod+doubles: exited=True rc=1 ok=True | prod+owner-dev: exited=True rc=1 ok=True | prod+allow-any: exited=True rc=1 ok=True |
| AB-01b | Java dev 启动 + /actuator/health UP | **PASS** | java -jar (SERVER_PORT=18081, db=mvp_e_dev) / 0 | first pid=3364165 |
| AB-01c | SIGTERM 停止 → 再启动 UP；Flyway no-op（重复启动无破坏） | **PASS** | restart cycle / 0 | second UP=True; flyway_noop=True |
| AB-03 | 全新 E 库 Flyway V1+V2 迁移：14 表（实际 14），版本=1,2 | **PASS** | fresh db migrate via app start / 15 | missing=[] extra=[] history=1,2 success_rows=2 |
| AB-02a | worker --check 连通自检（E 库） | **PASS** | python -m mvp_worker --check / 0 | PostgreSQL server_version: 16.15 (Debian 16.15-1.pgdg13+2) |
| AB-02b | worker 运行循环 + /healthz /readyz UP（18082） | **PASS** | python -m mvp_worker (loop) / 0 | healthz=True readyz=True |
| AB-02c | worker SIGTERM 优雅停机 | **PASS** | kill -TERM worker / 0 | graceful_log=True |
| AB-02d | worker pytest 全量（47） | **BLOCKED** | 按协调指示不重跑 A 全量单测；dev 固定端口脚本禁直接执行 / n/a | 按指示不为本轮重复 A 全量单测；E 用 --check/真实循环/端点验证替代 |
| N1-db | JSONB 写入边界（DB object+number CHECK）：非对象/null/字符串/bool/缺键拒绝，整数接受；小数/负数 DB 放行=已知限制（服务层兜底） | **PASS** | psql INSERT async_jobs.payload 变体 / 0/1 | array:rej(True) null_version:rej(True) string_version:rej(True) bool_version:rej(True) missing_key:rej(True) int1:accept fractional:accept negative:accept |
| AB-04a | 约束负例最小父链种子 | **PASS** | psql seed / 0 | INSERT 0 6 INSERT 0 1 INSERT 0 1 INSERT 0 1 INSERT 0 1 INSERT 0 1 INSERT 0 1 INSERT 0 1 INSERT 0 1 |
| AB-04b | 同一微晶第二个未收尾执行 → 拒绝（双占用）（拒因含 uq_execution_open_microcrystal） | **PASS** | psql negative INSERT / 1 | constraint_seen=True |
| AB-04c | 同一执行重复源三元组记录 → 拒绝（双记录）（拒因含 uq_record_source） | **PASS** | psql negative INSERT / 1 | constraint_seen=True |
| AB-04d | app 控制端缺 account/installation → 控制端归属 CHECK 拒绝（拒因含 ck_execution_controller_ownership） | **PASS** | psql negative INSERT / 1 | constraint_seen=True |
| AB-04e | active 通知目标无 registration → CHECK 拒绝（拒因含 ck_destination_active_fields） | **PASS** | psql negative INSERT / 1 | constraint_seen=True |
| AB-04f | T13 (principal,operation,key) 重复 → 拒绝（拒因含 uq_idem_principal） | **PASS** | psql negative INSERT / 1 | constraint_seen=True |
| AB-04g | members (identity_namespace,face_subject_ref) 双非空重复 → 拒绝（拒因含 uq_members_identity） | **PASS** | psql negative INSERT / 1 | constraint_seen=True |
| AB-04h | skin_assessments 非法 status → CHECK 拒绝（拒因含 ck_assessment_status） | **PASS** | psql negative INSERT / 1 | constraint_seen=True |
| AB-04i | skin_assessments current_photo_version=0 → CHECK 拒绝（拒因含 ck_assessment_current_photo_version） | **PASS** | psql negative INSERT / 1 | constraint_seen=True |
| AB-05a | 无 token → 401 AUTH_REQUIRED 信封 | **PASS** | GET /me/member-access-grants / 401 | {"requestId": "5daf1b30-1af8-4ca2-a621-9ba30c50368f", "error": {"code": "AUTH_REQUIRED", "message": "missing bearer token", "retryable": false}} |
| AB-05b | 伪造 Bearer → 401 SESSION_INVALID | **PASS** | GET with forged token / 401 | {"requestId": "c8021e80-8927-48cd-978e-76588eb4f5b0", "error": {"code": "SESSION_INVALID", "message": "session token invalid or expired", "retryable": false}} |
| AB-05c | 手机号会话建立（SMS 替身 123456 + installationId） | **PASS** | POST sms-challenges→sessions / 200 | accountId=a9042a40-7969-47dd-a53d-bf41d87ff539 |
| AB-05d | refresh 轮换后旧 refresh token → 401 SESSION_INVALID（不可复活） | **PASS** | POST session-refreshes (old reused) / 200/401 | {"requestId": "179bd42a-8402-43cb-a07f-cdd3945a9673", "error": {"code": "SESSION_INVALID", "message": "refresh credential invalid or rotated", "retryable": false}} |
| AB-05e | 账号 disabled 后旧 token → 401 SESSION_INVALID（每请求复核） | **PASS** | UPDATE accounts.status=disabled + GET / 401 | {"requestId": "3e44994d-394c-43a3-8b0a-95c12d3dc2c3", "error": {"code": "SESSION_INVALID", "message": "session token invalid or expired", "retryable": false}} |
| AB-05f | auth_revision 递增后旧 token → 401（撤销代次不可复活） | **PASS** | UPDATE accounts.auth_revision+1 + GET / 401 | {"requestId": "a9385cd4-6c47-438d-9550-69b8791f387a", "error": {"code": "SESSION_INVALID", "message": "session token invalid or expired", "retryable": false}} |
| AB-05g | revision 变更后重新登录成功（会话可重建） | **PASS** | POST sessions again / 200 |  |
| AB-05h | 云台凭据轮换后旧云台 token → 401（credential_version 复核） | **PASS** | gimbal-sessions → rotate → old token GET / 200/401 | {"requestId": "89057387-8ba8-401a-bb3e-82fd9f95b1cc", "error": {"code": "SESSION_INVALID", "message": "session no longer valid against local account/device state", "retryable": false}} |
| AB-06a | echo POST → 200 queued + jobId | **PASS** | POST /system/echo-jobs (Idempotency-Key) / 200 | {"requestId": "c270f64c-1f35-40ea-be06-80063ca68e2e", "data": {"jobId": "b7c68bbe-e4e2-4564-9862-f9dec3315a3e", "dedupKey": "system:echo:a8e16e8b-9c9c-492a-800c-d2874e88799e", "status": "queued"}, "meta": {"replayed": false, "serverTime": "2026-09-10 |
| AB-08a | T13 同 Idempotency-Key 同内容重放 → 同 jobId + meta.replayed=true | **PASS** | POST same key/content / 200 | replayed=True same_job=True |
| AB-08b | T13 同键不同内容 → 409 冲突（非 200/假成功） | **PASS** | POST same key/different content / 409 | {"requestId": "cd92c202-4e49-4921-be43-37e9fbaa5fd3", "error": {"code": "IDEMPOTENCY_CONTENT_CONFLICT", "message": "Idempotency-Key reused with different request content; use a new key for a new logic |
| AB-06b | worker --once 领取并完成 echo job（代次守护） | **PASS** | python -m mvp_worker --once / 0 | once_cycle_processed_jobs: 4 |
| AB-06c | GET echo job → succeeded + attemptCount=1 + leaseRevision=1 | **PASS** | GET /system/echo-jobs/{id} / 200 | status=succeeded attempt=1 lease=1 |
| AB-11a | 非法输入 → 400 INVALID_INPUT 结构化信封，body.requestId==X-Request-Id | **PASS** | POST /system/echo-jobs {} / 400 | rid_hdr=47c9113c-fbe5-4be1-a542-26db67752f66 rid_body=47c9113c-fbe5-4be1-a542-26db67752f66 code=INVALID_INPUT |
| AB-11b | 业务 stub（有 token）→ 501 NOT_IMPLEMENTED，不给假 200 | **PASS** | GET /me/member-access-grants / 501 | {"requestId": "37a865a5-1d95-4270-8718-07301dad8c0e", "error": {"code": "NOT_IMPLEMENTED", "message": "business endpoint is contract-only and not implemented yet", "retryable": false, "details": {"api |
| AB-11c | 未知资源 → 404 结构化信封（含 requestId） | **PASS** | GET /system/echo-jobs/<random> / 404 | {"requestId": "7009f9eb-516b-43f9-a6ea-ed1131546691", "error": {"code": "RESOURCE_NOT_VISIBLE", "message": "job not visible", "retryable": false}} |
| N3-media | 媒体 deny-all：任何 GET 统一 404（含 face purpose、含上传者、无 403 泄露） | **PASS** | seed media + GET /media/{id}/content / 404/404 | face_404=True no_403_leak=True |
| AB-07a | 过期 running 租约回收 → queued + lease_revision+1 + 释放 owner（条件更新） | **PASS** | worker --recover / 0 | status=queued lease_revision=2 owner=NULL |
| AB-06d | 陈旧代次完成同事务回滚 / 非 echo 可重试失败 attempt 上限 | **BLOCKED** | 仅注册 system.echo handler，无黑盒可重试失败路径 / n/a | 黑盒无 retryable 失败入口；A 自身测试覆盖（本轮按指示不重跑全量），E 不擅改 A 代码注入 handler |
| N1-py-schema | Python echo payload schema：string/null/bool/1.5/-2/不支持版本/数组/缺字段拒绝 | **PASS** | python -c EchoHandler().validate(变体) / 0 | string:REJECT null:REJECT bool:REJECT fractional:REJECT negative:REJECT unsupported:REJECT array:REJECT missing:REJECT |
| N1-py-runtime | Python 运行时拒绝非法 schema_version（failed/UNSUPPORTED_CONTRACT，不循环） | **PASS** | worker --once 处理坏版本 job / 0/1 | e01ba2:failed/UNSUPPORTED_CONTRACT e01ba2:failed/UNSUPPORTED_CONTRACT e01ba2:failed/UNSUPPORTED_CONTRACT |
| N2-db | 五诊断列豁免：无 schema_version 可写；CHECK 定义不含这 5 列 | **PASS** | UPDATE ...last_error 无版本 + 查 pg_constraint / 0/0 | no_check_on_diag_cols=True |
| N2-codereview | 代码检视：诊断列消费点 23 处（文件:行见 logs/n2-code-review.log） | **PASS** | grep 诊断列于 Java/Python src / 0 | hits=23 |
| N2-http | HTTP 响应不原样返回诊断列（echo GET 投影字段核查） | **PASS** | GET echo job 字段核查 / 200 | echo 投影仅 status/attempt/lease 等，无 last_error |
| CLEANUP | 停 Java/worker、删 mvp-e-pg 容器与卷（E_AB_KEEP=1 时保留容器调试） | **PASS** | docker rm -f -v mvp-e-pg; kill java/worker / 0 |  |
| CLEANUP-ports | 端口释放：18081 free=True 18082 free=True 55433 free=True | **PASS** | ss probe / 0 |  |

## 逐项细节与边界

- N1 Java 服务层：`SchemaVersionBoundaryTest`（真实 IdempotencyService.ensureSchemaVersion 类，覆盖缺省注入 1 / 显式整数 / null / 字符串 / 小数 / 非对象 → 400 INVALID_INPUT）已随 mvn 目标测试通过；HTTP 层无可由客户端控制的 schema_version 输入
  （echo 结果摘要由服务端注入整数 1），故服务层用真实类测试而非伪造 HTTP 入口验证。
- N1 Python 服务层：`EchoHandler.validate` 直调（targeted，string/null/bool/1.5/-2/不支持版本/数组/缺字段全拒）+ 真实运行时（DB 可放行的小数/负数/99 版本 → failed/UNSUPPORTED_CONTRACT，不循环）。
- N1 DB 已知限制：`object+number` CHECK 对小数/负数 JSON number 放行，由 Java/Python 服务层整数/const=1 校验兜底（A 报告未决项 9 已自述）。
- BLOCKED 为诚实标注，不计通过：AB-02d（按协调指示不重跑 A 全量 47 单测，dev 固定端口脚本禁直接执行）、AB-06d（黑盒无 retryable 失败 handler 入口）。
- Java 构建/启动日志：reports/E-AB-20260910T124722Z/java-app-1.log、java-app-2.log、mvn-package.log、mvn-targeted-tests.log
- worker：reports/E-AB-20260910T124722Z/worker-loop.log、worker-once.log、worker-check.log
- N1 Python validate 输出与 N2 代码检视：logs/ 下对应文件
- A 缺陷：见 FAIL 项（若有）；未修 A 代码。
- 清理：mvp-e-pg 与 E 库已删除，Java/worker 进程与端口已释放。
