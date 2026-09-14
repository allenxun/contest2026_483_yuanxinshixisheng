# B 登录会话与阿里云短信状态迁移 Redis：设计、公开配置示例与验收方式

状态：**设计与公开配置示例**（本文档 + 基础装配单独提交）；实现分两条道随后提交。
基线 HEAD `0e6c63399441f2ce142d66965e34bf6d82f40df3`（树 clean）。

> 本文档是根迁移私有 YAML 的**唯一权威字段清单**。OpenCode **未读取、未修改、未输出**
> `application-local.yml` / `application-local.properties` 或任何凭据。

---

## 1. 目标与非目标
**目标**
1. APP 登录会话（access/refresh）与阿里云短信状态（challenge、一次性核销、尝试次数、限流）
   从**进程内存**迁到 **Redis**，做到**跨实例一致**、**重启不丢**。
2. 核销 / 失败计数 / refresh 轮换 / logout 撤销 一律用 **Redis 原子操作或 Lua**，不靠进程内锁。
3. **Redis 故障 fail closed**：明确 503，**绝不**回退内存制造伪成功，**绝不**把依赖故障
   降级成"验证码错误 / 会话不存在 / refresh 无效"。
4. **保持全部 HTTP 契约不变**（端点、DTO 字段形状、状态码、`tokenType="Bearer"`）、
   保持 `auth_revision` 与账号禁用复核语义、保持 `SessionProvider` 接口行为
   （该端口**同时服务 APP 与云台**，云台的 `credentialVersion` 快照与 `sessionId` 语义不得变）。

**非目标（本轮明确不做）**
- 不改任何 HTTP 契约、不改 `backend/contracts/**`、不加数据库表（14 表 schema 不动，
  `SessionProvider.java:10` 明确"不擅自加表"）。
- 不引入 Spring Retry／熔断器（认证热路径重试会放大延迟，且与 fail-closed 目标无关）。
- 不引入 Testcontainers（它会从测试 JVM 内启动容器，与"不启动 Docker 重负载"冲突）。
- 不做无关重构；不为旧配置做无限兼容。
- **不部署远端**、不读取私有配置、不把凭据写入任何产物。
- `accounts` 仍在 PostgreSQL；`PrincipalRevalidator` 的每请求 DB 复核**保持不变**（不受 Redis 影响）。

---

## 2. 配置字段（最终名；根据此补私有 YAML）
### 2.1 连接绑定：一律用 Spring Boot 标准属性，**不自造前缀**
```yaml
spring:
  data:
    redis:
      host: <由根填写>            # 默认 localhost
      port: <由根填写>            # 默认 6379
      password: <由根填写>        # 绝不入仓、绝不入日志
      database: <0..15>          # 默认 0；服务端默认 databases 16
      timeout: 2s                # 命令超时（默认 null = Lettuce 默认）
      connect-timeout: 2s        # 建连超时（与 timeout 不是同一个）
      # url: redis://user:pass@host:6379/0   # 若设置，会覆盖 host/port/username/password/database
      # lettuce.pool.max-active: 8           # 需 commons-pool2 在 classpath（本项目已引入）
```
**已知外部配置问题（已由根修正）**：`database=30` 会被 Redis **服务端**拒绝为
`ERR DB index is out of range`——standalone 默认 `databases 16`，合法范围 **0..15**；
需要更大索引须由服务端 `databases` 配置扩大。orchestrator 已在本地 redis:7.4.11 亲自复现
（`SELECT 15` → OK，`SELECT 30` → 该错误）。**实现侧不为此做兼容、不猜测、不静默降级**：
该错误经 `RedisSystemException` 映射为 **503**，并在日志中按**配置错误**归类（不重试）。

**根侧最新状态（用户直接告知，orchestrator 未读取也未修改私有 YAML）**：
- 正式 `application-local.yml` 的 `spring.data.redis.database` 已改为 **5**（在合法范围 0..15 内）。
- **`database=5` 是后续 L3 真实 Redis 集成验收的前提**；L3 验收入口不得硬编码或覆盖它，
  一律由根的私有配置提供。
- 根已实测真实 Redis 基础连通全通过（TCP、认证、SELECT、PING、`SET NX EX60`、GET 内容、TTL、DEL、
  `EXISTS=0`，随机临时键已清理）。**这只证明基础连通与读写，不证明登录迁移**——
  迁移正确性须由 L2（原子性/并发/TTL/跨实例/fail-closed）与 L3（端到端登录）分别证明。

### 2.2 app 级开关（最小字段，只加两个）
| 字段 | 取值 | 默认 | 含义 |
|---|---|---|---|
| `app.state.provider` | `memory` \| `redis` | **`memory`** | 会话与短信状态的存储后端。`memory`＝现有进程内实现（仅供隔离测试/ doubles）；`redis`＝跨实例一致的真实实现 |
| `app.state.redis.key-prefix` | 字符串 | `mvp:b:` | 所有键的命名空间前缀。测试用**独立随机前缀**隔离，清理只删自己前缀 |

环境变量形式：`APP_STATE_PROVIDER`、`APP_STATE_REDIS_KEY_PREFIX`。
**为什么只要一个开关**：会话与短信状态都需要跨实例一致性，没有"只迁一个"的合理场景；
两个开关只会制造半迁移的中间态（正是本项目反复踩过的"半成功危害"）。

### 2.3 公开示例（`application.yml`，本轮新增的**非秘密**部分）
```yaml
app:
  state:
    provider: ${APP_STATE_PROVIDER:memory}     # 联调/真实 provider 用 redis
    redis:
      key-prefix: ${APP_STATE_REDIS_KEY_PREFIX:mvp:b:}
management:
  health:
    redis:
      enabled: ${APP_REDIS_HEALTH_ENABLED:false}   # 见 §7.3 的如实披露
```
`spring.data.redis.*` **不写入公开示例的具体值**（避免与根的私有 YAML 冲突或泄漏拓扑）；
只在本文件 §2.1 以占位形式说明。

---

## 3. 键模型（含哈希与脱敏规则）
**通则**
1. 所有键 = `<key-prefix><域>:<用途>:<标识摘要>`；**标识一律用 sha256 十六进制摘要**，
   绝不用原文 token / 手机号 / 明文验证码入键（键会出现在 `SCAN`、慢日志与监控里）。
2. **每个键只用一种 Redis 类型**（实测：对 list 做 `GET` → `WRONGTYPE`；对非整数字符串做 `INCR`
   → `ERR value is not an integer or out of range`）。键名带用途段，避免类型复用。
3. Lua 脚本访问的**所有键都必须经 `KEYS[]` 传入**（Redis 官方要求；cluster 下还需同 hash slot）。
4. 值中**确实需要**的 PII 只有一项：短信 challenge 的手机号（核销成功后必须返回它才能建会话）。
   它只存在于**私有且已认证**的 Redis 值中，**绝不入键、绝不入日志、绝不入异常消息**；
   日志一律经既有 `SmsMasking.maskPhone`（`+8610000000000` → `+861****0000`）。
5. **验证码明文不落 Redis**：存 `hex(sha256(code + challengeId))`（以 challengeId 为盐）。
   这比现状（内存中存明文 code）更严格：Redis 被导出也拿不到可用验证码，且每个 challenge 的
   盐不同 ⇒ 相同验证码在不同 challenge 下摘要不同，无法建全局对照表。

**键清单**
| 键 | 类型 | 值/字段 | TTL | 用途 |
|---|---|---|---|---|
| `<p>sess:at:<sha256(accessToken)>` | hash | `kind`(app\|gimbal)、`sid`、`aid`(accountId 或 gimbalId)、`iid`(installationId，云台为空)、`rev`(authRevision 或 credentialVersion)、`iat`、`exp` | APP 2h / 云台 1h（沿用现有 TTL） | `authenticate` 的唯一查询路径 |
| `<p>sess:rt:<sha256(refreshToken)>` | string | `sid` | 与该会话同 TTL | refresh 一次性轮换（Lua CAS） |
| `<p>sess:sid:<sessionId>` | hash | `at`=sha256(accessToken)、`rt`=sha256(refreshToken)（云台为空） | 同上 | 轮换/撤销时定位并连带清理旧 access 与 refresh（等价现有 `tokenBySession` + `refreshByToken`） |
| `<p>sms:ch:<challengeId>` | hash | `cd`=sha256(code+challengeId)、`ph`=手机号（唯一 PII）、`exp`、`att` | `app.sms.risk.challenge-ttl-seconds`（沿用既有默认） | 一次性核销 + 尝试计数（单个 Lua 内完成） |
| `<p>sms:rl:<sha256(phone)>:m:<yyyyMMddHHmm>` | string(int) | 计数 | 窗口剩余 + 余量 | 分钟窗口（UTC+8 自然边界） |
| `<p>sms:rl:<sha256(phone)>:h:<yyyyMMddHH>` | string(int) | 计数 | 同上 | 小时窗口 |
| `<p>sms:rl:<sha256(phone)>:d:<yyyyMMdd>` | string(int) | 计数 | 同上 | 日窗口 |

**为什么 sessionId 不入摘要**：`sessionId` 本身是服务端生成的随机 UUID、不含用户身份，
且它要作为 T09 `session_ref` 与 T13 `principal_id` 的一部分被业务使用，必须保持原值可返回。

---

## 4. 原子操作与 Lua（每条都已在本地 redis:7.4.11 实测原语可行性）
| 业务不变量 | 实现 | 为什么必须原子 |
|---|---|---|
| **验证码一次性核销 + 尝试上限 + 过期判定** | 单个 Lua：读 `exp`/`att`/`cd` → 判过期 → 判上限 → 比较 `cd` → 失败则 `att+1`（首次设 TTL）→ 成功则 `DEL` 并返回 `ph` → **返回整数状态码 + 需要的字段** | 现状靠 `synchronized(challenge)`（`:180-206`）；跨实例该锁无效，否则两个并发正确码请求会**各签发一个会话** |
| **失败计数** | Lua `INCR` + `if n==1 then EXPIRE`（**同一脚本内**） | 实测负向对照：裸 `INCR` 留下 **TTL=-1 的永不过期键**；官方明确"`INCR` 后另发 `EXPIRE NX` 仍是两条命令、关不上崩溃窗口" |
| **refresh 轮换** | Lua CAS：`GET rt:<digest>` == 期望 → `DEL` 旧 rt、写新 `sess:at`/`sess:rt`/`sess:sid`、撤销旧 access → 返回 1/0 | 防并发双换双活；实测 CAS 在错误期望时返回 0 且值不变、TTL 保留 |
| **logout / 撤销** | Lua `HGETALL` + `DEL`（原子读出 `RevokedSession` 所需字段再删） | 必须**恰好一次**返回 accountId/installationId/sessionId 给 T09 失效使用；并发登出只应有一个拿到值（另一个 empty → 401，与现状一致） |
| **节流三窗口** | 单个 Lua 对三个窗口键做"检查 + 预留 + 首次设 TTL" | 现状把远端发送包在条带锁内（`:148`）；跨实例必须靠 Redis 原子预留才能不超发 |
| **不存在才创建** | `opsForValue().setIfAbsent(k,v,Duration)` ≡ `SET k v EX ttl NX` | 防重复签发 |

**为什么 `sess:sid:<sessionId>` 必须是 hash 而不是 string**：`revokeSession(accessToken)` 的入参
只有 access token，但撤销必须**连带清理** refresh 凭据（否则登出后旧 refresh 仍可用，属实质安全缺陷）。
现状用两张内存表（`tokenBySession` + `refreshByToken`，`InMemorySessionDouble:140-141`）解决；
Redis 侧把两个摘要都存在 `sess:sid:<sessionId>` 这一个 hash 里，即可在**同一个 Lua** 内原子地
读出并删除 `sess:at:*`、`sess:rt:*`、`sess:sid:*` 三个键。**注意存的仍是摘要而非原文 token**，
因此撤销时要用摘要拼出待删键名——这正是 §3 键通则第 2 条的直接结果。

**Lua 返回值纪律**：一律返回**整数**（0/1/状态码）或字符串，Java 侧用 `DefaultRedisScript<Long>`。
实测 + 官方一致：Lua `return false` → Redis null bulk reply → Java **`null`**，用布尔接收会踩坑。
脚本注册为**单例 bean**；Spring 的 `ScriptExecutor` 自动 `EVALSHA` → `EVAL` 回退，无需手工预加载。

**节流的语义精化（如实披露）**：现状只在**发送被受理后**计数（`recordAcceptedSend`），
且靠进程内条带锁把"预检→发送→记录"串行化。跨实例无法用锁串行化，因此改为
**原子预留 + 失败补偿**：Lua 先原子地检查并占用三个窗口名额（保证并发下**绝不超发**），
远端发送**未被受理**时再用另一个 Lua **原子回退**该名额。稳态下计数仍等于"受理成功的发送数"，
与现状一致；差别仅在"发送失败的瞬间名额被短暂占用"，方向是**更严格**，不会放松限流。

---

## 5. TTL 表
| 对象 | TTL | 来源 |
|---|---|---|
| APP access 会话 | 2 小时 | 沿用 `InMemorySessionDouble:68` |
| 云台会话 | 1 小时 | 沿用 `:126` |
| refresh 凭据 | 与其会话同 TTL | 现状 refresh 无独立 TTL、有效性等同会话过期（一次性 + `alive()` 惰性判定），保持一致 |
| challenge | `app.sms.risk.challenge-ttl-seconds` | 沿用既有默认，不新增旋钮 |
| 尝试计数 | 与 challenge 同生命周期（同一 hash 字段，随键一起过期） | 避免留下孤儿计数 |
| 限流窗口键 | 该 UTC+8 自然窗口的剩余时间 + 小余量 | 与现状 `sameMinute/sameHour/sameDay`（`:350-362`）等价 |

**Redis 过期语义的如实说明**：Redis 用**惰性 + 定期采样**两种过期机制，键到期后**逻辑上立即不可见**
（`GET`→nil、`EXISTS`→0），但**物理内存回收可能滞后**。因此尝试上限与限流窗口只依赖**逻辑 TTL**，
不依赖物理删除时刻。另需披露：**若生产 Redis 触发 maxmemory eviction，限流计数可能偏松**
（键被淘汰＝计数丢失）；建议生产为该类键使用 `noeviction` 或独立实例，并由运维配置告警。

---

## 6. 异常映射与 fail-closed
| 情况 | Spring 异常 | HTTP / ErrorCode | retryable |
|---|---|---|---|
| 连接被拒 / DNS / 不可达 / 中途断开 | `RedisConnectionFailureException` | **503 `DEPENDENCY_UNAVAILABLE`** | true |
| 命令超时 | `QueryTimeoutException` | **503 `DEPENDENCY_UNAVAILABLE`** | true |
| 认证失败 / `READONLY` / `DB index out of range` / OOM 拒命令 | `RedisSystemException` | **503 `DEPENDENCY_UNAVAILABLE`**（日志按**配置错误**归类，不重试） | true（信封字段沿用既有码） |
| 本地 API 误用（如 `InvalidDataAccessApiUsageException`） | — | **500 `INTERNAL`**：这是**代码缺陷**，不得伪装成依赖不可用 | false |
| 验证码错误 / 过期 / 超尝试上限 | — | **401 `AUTH_REQUIRED`**（现状语义不变） | false |
| 限流命中 | — | **429 `RATE_LIMITED`** + `Retry-After` + `details.retryAfterSeconds`（现状不变） | true |

**三条硬纪律**
1. **任何 Redis 异常都不得被吞成 `Optional.empty()`**——那会把"依赖不可用"伪装成"会话无效/验证码错误"
   （401），既掩盖故障又违反 fail-closed。必须抛出映射后的 `ApiException`。
2. **绝不回退内存实现制造伪成功**：`app.state.provider=redis` 时不存在任何内存兜底路径。
3. **配置错误在启动期明确拒绝**（沿用本仓既有护栏范式，消息**只含键名、绝不回显取值**）：
   `app.state.provider=redis` 但 `spring.data.redis.url` 与 `spring.data.redis.host`
   **都未显式设置** ⇒ 拒绝启动；生产信号（`prod` profile 或 `app.env=production`）下
   `app.state.provider != redis` ⇒ 拒绝启动（"联调/真实 provider 必须用 Redis"由此变成**可执行的门禁**，
   而不是约定）。
   **运行期不可达不阻止启动**：官方 `LettuceConnectionFactory` 默认 `eagerInitialization=false`，
   Redis 不可达时上下文仍可启动、首个命令失败 ⇒ 请求期 503。这是有意的：把"Redis 短暂不可用"
   放大成"整个应用起不来"更糟，而请求期 503 已经是 fail-closed。

**热路径影响面（如实披露）**：`BearerAuthFilter:82` 对**每一个非公开 `/api/**` 请求**调用
`authenticate`（公开豁免仅 4 个端点）。迁移后这是一次 Redis 往返；Redis 故障时**全部已认证端点**
返回 503。`BearerAuthFilter:83-87` 既有逻辑已把 provider 的 `RuntimeException` 渲染为 503 信封，
但 `AuthController` 的 create/refresh/revoke 路径**必须显式映射**，否则会落到 500 `INTERNAL`。

---

## 7. 装配、守卫与既有测试影响
### 7.1 provider 选择（沿用本仓三层门范式）
`app.state.provider=redis` 时装配 Redis 实现；`memory`（默认）时保持现状。
新实现放在**新包 `cn.yuanxin.mvp.web.state`**（会话）与既有 `web.sms`（短信），
**绝不放进 `cn.yuanxin.mvp.web.testdouble`、类名绝不以 `Disabled` 开头**——
因为 `ProductionFailClosedValidator.isDouble`（`:76-81`）正是按包名 `.testdouble`、
类名前缀 `Disabled`、`DisabledProvidersConfig` 内匿名类这三条判定替身。
附带收益：现状 `app.providers.mode=real` 下**没有任何 SessionProvider 真实实现**（`requireReal` 拒启），
Redis 实现正好闭合该缺口。

### 7.2 doubles 的定位（按用户要求）
`InMemorySessionDouble` 与 `SmsCodeDouble` **仅保留给隔离测试**（`app.providers.mode=doubles`），
不接 Redis、行为逐字不变。注意 `AbstractWebIT:80` **强转 `InMemorySessionDouble`** 调测试钩子
`sessionIdForAccessToken`，因此该替身与其钩子必须保留。

### 7.3 健康检查的如实披露
引入 starter 后 `RedisConnectionFactory` 会由自动配置创建（默认**不**在启动期建连），
Actuator 的 `RedisHealthIndicator` 在 `management.health.redis.enabled` 默认 true 时会因
**无 Redis 而让 `/actuator/health` 返回 DOWN**，从而破坏既有验收工装（41 项）与大量 IT。
本轮把该开关默认置 **false**（可用 `APP_REDIS_HEALTH_ENABLED=true` 打开）。
**这是一处需要根知悉的取舍**：默认关闭意味着健康端点**不反映** Redis 状态；
生产若希望健康端点覆盖 Redis，应显式打开。orchestrator 不擅自把它设为 true，
因为那会让所有未配置 Redis 的环境（含 CI 与其他包的联调）健康检查失败。

### 7.4 预期需要改写的既有测试（不得弱化断言）
- `sms/AliyunSmsCodeProviderTest`（`:80,92,102,111,203` 用 `ReflectionTestUtils.getField(provider,"challenges")`
  反射断言 map 为空）与 `sms/AliyunSmsProviderBoundsTest`（`:50-51,65,83,94,99,117` 反射
  `challenges`/`acceptedSends`）：状态搬进 store 后反射路径变化，**必须改为断言等价的可观测面**
  （内存后端断言 store 内的 map；Redis 后端断言键存在/TTL/已删除），**断言强度不得下降**。
- `sms/SmsProvidersConfigTest`（装配矩阵 `:66-144`）：新增 `app.state.provider` 维度用例；
  `mode=disabled` 仍必须是最高优先级。
- `config/NonProductionProvidersRefusalTest`（`:57,102` 断言 `getBeansOfType(...).isEmpty()`）与
  `config/ProductionFailClosedTest`：新增"生产下 Redis 实现算 real、memory 被拒"的用例。
- **应原样通过**（它们断言的是 HTTP 契约而非存储实现）：`auth/AuthFlowIT`(6)、`auth/RevocationIT`(5)、
  `auth/BearerAuthFilterTest`(1)、`auth/FilterErrorRenderingIT`(2)、
  `notifications/LogoutDestinationRevisionIT`(4)、`sms/AliyunSmsVerifyConcurrencyTest`(3)、
  `sms/AliyunSmsIssueConcurrencyTest`(1)、`sms/AliyunSmsSecurityTest`(5)、
  `sms/AliyunSmsSendGatewayTest`(7)、`sms/AliyunSmsSmokeConfigEncodingTest`(3)。
  其中两个并发测试正是**原子性的验收基准**：迁移后必须在 Redis 后端下同样成立。

---

## 8. 证据分层（三层；默认全量套件**不需要任何 Redis**）
| 层 | 何时运行 | 证明 | **不**证明 |
|---|---|---|---|
| **L1** stub/unit/contract | 默认全量（Java 基线 **618**） | 键模型与摘要规则、Lua 脚本参数形状、异常→HTTP 映射、fail-closed 分支、装配矩阵与生产守卫、HTTP 契约不变、doubles 隔离；**同一套契约测试对内存与 Redis 两个后端各跑一遍**以防实现漂移 | 原子性、真实 TTL、跨实例一致性 |
| **L2** opt-in 真实 Redis IT | 仅当显式提供 `-Dmvp.test.redis.url=redis://127.0.0.1:6399`（或等价 env）；否则**整类跳过** | 多线程并发核销**恰好 1 个赢家**且键已删；失败计数不会留下 TTL=-1 的键；refresh CAS 并发不双花；TTL 真实过期；**两个独立 Spring 上下文共享同一 Redis** 的跨实例一致；连接被拒时 HTTP **503** | 真实生产 Redis 的认证/网络/容量行为 |
| **L3** root-only 真实登录验收 | **仅由根**用私有 `application-local.yml` 执行；三重显式 opt-in、默认跳过 | 真实 Redis + 真实阿里云短信下的**端到端登录**：f01 发码 → f02 核销建会话 → access 认证 → refresh 轮换（旧 access 立即失效）→ logout 撤销 + T09 `destination_revision` 递增 | —— |

**L2/L3 纪律**：一律使用**独立随机键前缀**（`app.state.redis.key-prefix`）并**彻底清理**
（只 `SCAN`+`DEL` 自己的前缀，**绝不** `FLUSHDB`/`FLUSHALL`；本地测试容器还重命名禁用了
`FLUSHALL`/`FLUSHDB`/`CONFIG`）；输出**绝不**含凭据、手机号、验证码、完整键或对象内容。

**本地测试用 Redis（不是部署）**：容器 `mvp-b-redis-test`，镜像 `redis:7`（本地已有，未下载），
仅绑 `127.0.0.1:6399`，`--memory 128m --cpus 0.5 --maxmemory 64mb`、无持久化、
禁用 `FLUSHALL`/`FLUSHDB`/`CONFIG`；实测负载 cpu 0.78%、mem 13.55MiB。**用毕 `docker rm -f`**。

---

## 9. 真实 Redis 登录验收入口（交付后由根执行）
入口与运行方式在实现提交后补全于 §11（含三重 opt-in 标志、所需非秘密参数、预期输出与退出码、
以及"绝不发送真实短信除非根显式提供测试手机号"的既有纪律）。**orchestrator 不执行 L3**：
它需要根的私有配置与真实凭据，且本轮明确"不部署远端"。

---

## 10. 明确不做的事（防范围蔓延）
- 不改 `SessionProvider` / `SmsCodeProvider` **接口签名**（云台依赖既有行为）。
- 不改 `PrincipalRevalidator` 的每请求 DB 复核、不改 `auth_revision` 的读取与判定路径
  （`AuthController:175-184` 的 `SELECT status, auth_revision FROM accounts WHERE id = ?` 保持）。
- 不改 `invalidateDestinations` 的既有语义（先撤销会话、后失效 T09；不在 DB 事务内；
  异常被吞为 warn 的**幂等补偿**语义、登出不反转）——本轮只保证它拿到的 `RevokedSession`
  在并发登出下仍**恰好一次**。
- 不动 `backend/worker-python/**`、`backend/face-service/**`、`backend/acceptance/**`、
  `backend/contracts/**`、D 的 `PlanPort`、A 的 `media/**`。
- 不新增数据库表或迁移。

---

## 11. 待实现提交后补全
- 最终类名与包结构、Lua 脚本资源清单与其 `KEYS/ARGV` 契约。
- L2 的运行命令与实测数字；L3 的入口类名、三重 opt-in 标志、根运行命令与预期输出。
- 全量回归真实数字（Java 基线 **618**）与账目。
- Oracle 最终审查裁定与阻塞项处置。

## 12. 实施进度与提交（orchestrator 维护）
| 阶段 | 提交 | 内容 | 验证 |
|---|---|---|---|
| 设计 + 公开配置示例 + 基础装配 | `28ef3539feca9d36e557d7bd407af880e236d99c` | 本文档；`pom.xml` 加 `spring-boot-starter-data-redis`（BOM 管版本，默认 Lettuce；**刻意不加** `commons-pool2`：本项目 Redis 命令全为非阻塞含 EVAL，`shareNativeConnection=true` 即可）；`application.yml` 加 `app.state.*`、健康检查开关、prod profile 默认 `redis`；`web/state` 5 个基础类；`TestDoubleProvidersConfig.sessionProvider` 加 `app.state.provider=memory`（`matchIfMissing=true`）互斥门 | `mvn compile` rc=0、`test-compile` rc=0、**全量 618/0/0 BUILD SUCCESS**（与基线一致 ⇒ 零回归）；classpath 实测含 spring-data-redis 3.5.13 + lettuce-core 6.6.0.RELEASE |
| 共享测试接缝 | 见下方提交 | `src/test/java/.../state/RedisTestSupport.java`：opt-in（`-Dmvp.test.redis.url` / `MVP_TEST_REDIS_URL`）、随机前缀、`SCAN`+`DEL` 只清自己前缀、`describe()` 不泄漏主机端口 | javac rc=0；行为探针实测：opt-in 门 false→true、`describe()` 不含 `6399`/`127.0.0.1`、前缀形状 `b-probe-<16hex>:`、键带前缀、TTL>0、清理后 **db5 DBSIZE=0** |
| 会话实现 | 待提交 | `RedisSessionProvider` + `RedisSessionConfig` + `redis/session-*.lua` + 契约/opt-in IT + L3 root-only 登录验收入口 | 待中央验证 |
| 短信状态实现 | 待提交 | `SmsStateStore` 端口 + 内存/Redis 两实现 + `SmsStateStoreConfig` + `redis/sms-*.lua` + `AliyunSmsCodeProvider` 改造 + 测试改写 | 待中央验证 |

**两条实施道并行、写域互斥**（`web/state/**` vs `web/sms/**`；Lua 资源 `session-*.lua` vs `sms-*.lua`），
且**都禁止运行 mvn**（避免 `target/` 与端口争用、避免污染权威数字）；类型检查用 orchestrator 预生成并
实测过的 `javac` + `cp-test.txt` 配方，中央构建与全量回归由 orchestrator 统一执行。
