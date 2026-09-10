# web-java —— MVP Web 后端基础（工作包 A）

Spring Boot 3.5.16（Boot BOM 锁定：Flyway 11.7.2、PG driver 42.7.11、HikariCP 6.3.3）
+ Spring MVC（servlet 栈，无 WebFlux）+ Spring JDBC + TransactionTemplate（编程式事务，
无 JPA）+ Flyway（唯一迁移入口，`src/main/resources/db/migration`）。Java 21。
契约唯一出处：`backend/contracts/openapi/openapi.yaml` 与 `backend/contracts/canonicalization.md`。

## 架构概览

- 请求链：`RequestIdFilter`（服务端生成 requestId → MDC + `X-Request-Id` 头，不信任入站值）
  → `BearerAuthFilter`（保护 `/api/**`，公开清单=3 个 auth 端点 + gimbal-sessions；
  actuator 开放）→ 控制器。错误一律 `GlobalExceptionHandler`/`ResourceNotFoundAdvice`
  转标准信封；未映射异常 → 500 INTERNAL（堆栈只进日志，客户端只见 requestId）。
- 信封：成功 `{requestId, data, meta:{replayed, serverTime}}`（204 无体但带头）；
  列表 data=`{items, nextCursor}`；错误 `{requestId, error:{code,message,retryable,details}}`。
- 幂等：T13 `IdempotencyService`（见下）；媒体：T11 + StoragePort；任务：T12 `JobEnqueuer`。
- 跨语言规范化：`idempotency/Jcs`（RFC 8785，**行为基准=contracts/scripts/jcs.py**，
  17 向量字节一致复现（含 UTF-16 code unit 键序判别向量）；解析启用 Jackson
  STRICT_DUPLICATE_DETECTION 拒重复键；
  注意：jcs.py 对 1e-4≤|v|<1 非整值 double 有已知小数点缺陷，Java 侧为字节兼容忠实复现，
  已上报总协调待契约 lane 修订——本项目契约数据不落入该区间）。

## 包地图（cn.yuanxin.mvp.web）

| 包 | 内容 |
|---|---|
| `web/` | RequestIdFilter、SuccessEnvelope/ErrorEnvelope/ListData、EnvelopeSupport、GlobalExceptionHandler、ResourceNotFoundAdvice、CursorCodec/CursorException |
| `error/` | ErrorCode（openapi 枚举全集 + INTERNAL）、ApiException（code/status/retryable/details/headers） |
| `auth/` | PrincipalContext（+argument resolver）、端口 SessionProvider/DeviceCredentialProvider/SmsCodeProvider/FaceProvider、BearerAuthFilter、AuthController、GimbalSessionController(M2-A01) |
| `testdouble/` | 仅 dev/test 的隔离替身：InMemorySessionDouble、SmsCodeDouble（固定码 123456）、DeviceCredentialDouble（对照 gimbals 行）、FaceProviderDouble、FileSystemStorageDouble |
| `idempotency/` | Jcs、CanonicalObjectBuilder、IdempotencyService（begin/completeSuccess/completeRejected、StaleAttemptException） |
| `jobs/` | JobEnqueuer（dedup 冲突=重放，savepoint 保调用方事务存活）、Uuid5（FIXED_NS=f988d041-6031-5120-8075-f90b6b05553e） |
| `media/` | StoragePort、MediaService（pending/available/failed + 白名单/限额）、MediaIntakeService（multipart 逐 part 摘要→存储→available）、MediaAccessPolicy 三实现（DenyAll 生产默认 / OwnerBased dev 便利 / AllowAuthenticated dev opt-in）、MediaController(`GET /api/v1/media/{mediaId}/content`) |
| `system/` | SystemEchoController（echo-jobs POST/GET，T13+T12 接线参照实现） |
| `stub/` | NotYetImplementedController：26 个 contract-only 端点 → 501 NOT_IMPLEMENTED（在 Bearer 之后：无 token 先 401） |
| `config/` | AppProperties、FoundationConfig（Jackson 严格解析/TransactionTemplate/参数解析器/媒体授权默认）、TestDoubleProvidersConfig（@Profile dev/test）、DisabledProvidersConfig（mode=disabled→503）、ProductionFailClosedValidator |

## DB 写入边界（digest §1 / ARCH 4.1；本服务=Java Web 侧）

- **Java 独占写**：accounts、member_access_grants；gimbals/microcrystals（绑定、当前任务
  指针、心跳、能力/状态观察）；skin_assessments 受理/照片版本/重试输入状态；
  care_executions、care_records（全生命周期/占用/次数账本/同步收尾）；
  notification_destinations 目标登记；media_objects 请求图片、创建任务、请求去重(T13)；
  idempotency_requests（本服务）；async_jobs 的入队侧字段。
- **Python Worker 独占写**：members 可靠身份归档；skin_assessments 分析状态/成员归属/
  正式报告；care_plans 生成字段/N（不得覆盖 K/completed_at）；通知创建/投递结果；
  自己任务的领取/结果状态(T12)；不改 T13 结果。
- 共享表一律**字段级 UPDATE**，禁整行保存/upsert 覆盖对方列；两端独立连接池与事务，
  事务不跨进程。本包已按此实现：如退出登录对 T09 只按 `session_ref` 条件更新
  status/invalidated_at 两列；accounts 仅 last_login_at/登录映射。

## B/C/D 扩展指南

1. **替换 501 stub**：在 `stub/NotYetImplementedController` 删除对应方法，并新建同路径
   正式控制器（无自动让位机制——编译期冲突自行消除）。路径参数保持契约类型
   （UUID 参数非法自动 400 INVALID_INPUT）。
2. **T13 接线**（参照 `SystemEchoController`）：
   `CanonicalObjectBuilder.forOperation(op).pathParams(...).fields(缺省展开).imageParts(digests).payloadHash()`
   → 在业务事务**外** `idempotencyService.begin(...)`（独立短事务提交 processing；重放分支
   按 BeginOutcome 投影 + `request.setAttribute(ATTR_REPLAYED,true)`）→
   业务写 + `completeSuccess/completeRejected` 放同一 `TransactionTemplate.execute` 内；
   代次守卫失败会抛 StaleAttemptException 回滚整个业务事务（HTTP 呈现 409
   REQUEST_IN_PROGRESS + Retry-After）。principal 用 `PrincipalContext.t13PrincipalType()/t13PrincipalId()`。
3. **multipart 受理**：`MediaIntakeService.digest/partDigests` → `begin` →
   `ingest(principal, purpose, t13RequestId, parts)` → 受理事务补 T11 归属列 +
   `completeSuccess`。available≠可访问：A 生产默认是 **deny-all**
   （`DenyAllMediaAccessPolicy`，任何 GET 统一 404）；dev/test 上传者便利用
   `APP_MEDIA_ACCESS_MODE=owner-dev`（核验用途仍拒绝）。业务读取授权提供
   `@Primary MediaAccessPolicy` bean 即覆盖默认，按 DD 10.2 检查 T05 冻结报告
   引用/T02/T03。production 下任何非默认模式均启动失败（fail closed）。
4. **入队**：业务事务内 `jobEnqueuer.enqueue(jobType, ownerType, ownerId, inputRevision,
   payload(snake_case+schema_version), dedupKey)`；owner_id 用
   `JobEnqueuer.systemOwnerFor/identityNamespaceOwnerFor`（UUIDv5/FIXED_NS）。
5. **认证主体**：控制器方法参数直接声明 `PrincipalContext`（保护端点必得非空）。
   APP=accountUuid+installationId；GIMBAL=gimbalUuid+credentialVersion。
   请求体声明的身份字段一律不可信（additionalProperties:false + 身份只来自 token）。
6. **人脸**：注入 `FaceProvider`（请求内同步、不排队列）；分类
   MATCHED/RELIABLE_NEW/UNCERTAIN/QUALITY_REJECTED/DEPENDENCY_FAILED——DEPENDENCY_FAILED
   绝不按匹配成功处理（fail closed）。

## Fail closed

- dev/test：`TestDoubleProvidersConfig` 装配隔离替身（token 只认自签发；任意
  accountId/installationId 字符串无法认证）。
- `app.providers.mode=disabled`：所有端口调用 → 503 DEPENDENCY_UNAVAILABLE 信封。
- `app.env=production`（prod profile 自动设置）：`ProductionFailClosedValidator` 检查
  5 个端口必须存在**真实**实现 bean（无 bean / 只有替身/禁用 → 启动失败）。
  不建会话存储表；真实提供方选定前生产无法通过该校验是有意状态。

## 测试

```bash
cd backend/web-java
mvn test          # 124 个：Flyway 迁移 13 + JCS 向量 45 + 单元/上下文 + 真实 PG 集成（*IT）
```

集成测试对隔离容器 `mvp-a-pg`（127.0.0.1:55432）每次运行创建临时库
`mvp_a_test_j_<uuid>`（JVM 退出强制删除），跑 Flyway，全部共用一个 Spring 上下文。
可用 `MVP_A_PG_JDBC/MVP_A_PG_USER/MVP_A_PG_PASSWORD` 覆盖管理连接。

## 运行

```bash
SERVER_PORT=18080 java -jar target/web-java-0.0.1-SNAPSHOT.jar   # 默认 dev profile（替身）
curl --noproxy '*' http://127.0.0.1:18080/actuator/health/readiness
```

## 环境变量（compose/deploy 第 3 阶段需并入 backend/deploy 配置）

| 变量 | 默认 | 用途 |
|---|---|---|
| SERVER_PORT | 8080 | HTTP 端口 |
| SPRING_DATASOURCE_URL / _USERNAME / _PASSWORD | 127.0.0.1:55432/mvp_a_dev / postgres / mvp_a_local | PG（密码必须 env 注入） |
| SPRING_PROFILES_ACTIVE | dev（default） | dev/test/prod；prod 走 fail-closed |
| DB_POOL_MAX / DB_POOL_MIN | 10 / 2 | HikariCP |
| APP_ENV | dev；prod profile=production | 对象 key 前缀 + fail-closed 开关 |
| APP_PROVIDERS_MODE | doubles | doubles / disabled / real |
| APP_STORAGE_DEV_DIR | /tmp/mvp-a-storage | dev 替身存储目录（容器需挂卷；生产换真实 OSS 实现） |
| APP_STORAGE_BUCKET | mvp-a-media | T11 bucket 标记 |
| APP_IMAGE_MAX_BYTES | 10485760 | 单图上限 |
| APP_IDEMPOTENCY_LEASE_SECONDS | 30 | T13 processing 租约 |
| APP_MEDIA_ACCESS_MODE | deny-all | 媒体读取模式：deny-all / owner-dev / any-authenticated（仅 dev/test；production 非默认即拒绝启动） |
| APP_MEDIA_ALLOW_ANY_AUTHENTICATED | false | 旧显式开关，等价 any-authenticated（production 拒绝） |
| APP_DOUBLE_SMS_CODE | 123456 | 替身固定验证码 |
| APP_DOUBLE_FACE | MATCHED | 替身人脸分类结果 |

新增（相对既有 deploy 样例）：APP_PROVIDERS_MODE、APP_STORAGE_DEV_DIR、
APP_STORAGE_BUCKET、APP_IMAGE_MAX_BYTES、APP_IDEMPOTENCY_LEASE_SECONDS、
APP_DOUBLE_SMS_CODE、APP_DOUBLE_FACE、APP_ENV。web 服务如需 dev 存储需挂
`APP_STORAGE_DEV_DIR` 卷（真实 OSS 接线后可移除）。
