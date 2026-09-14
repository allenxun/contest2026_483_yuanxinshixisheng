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
   这比现状（内存中存明文 code）更严格：明文不出现在 Redis、日志与任何导出中，且每个 challenge
   的盐不同 ⇒ 相同验证码在不同 challenge 下摘要不同，无法建立跨 challenge 的全局对照表。
   **如实限制（Oracle 第二十六轮 SUGGESTION 9 指出，本文档此处原表述过强、已更正）**：验证码只有
   6 位十进制（约 20 bit 熵），而 `challengeId` 是**返回给客户端的、并非秘密**，因此持有 Redis
   **只读快照**者可离线枚举全部 10^6 个候选码并比对摘要 ⇒ 加盐 sha256 **不能**抵御快照泄漏后的
   离线枚举。若要真正抵御需以**服务端 secret（pepper）**做 HMAC，本轮未实现（会引入新的秘密分发
   与轮换问题），登记为限制；在线暴力枚举仍由"尝试次数上限 + challenge TTL"的原子脚本限制。

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
（只 `SCAN`+`DEL` 自己的前缀，**绝不** `FLUSHDB`/`FLUSHALL`，也**绝不**用 `KEYS`；本地测试容器还
重命名禁用了 `FLUSHALL`/`FLUSHDB`/`CONFIG`）；输出**绝不**含凭据、手机号、验证码、完整键或对象内容。

**如实更正（Oracle 第二十六轮 BLOCKER 3）**：本文档此处此前自称 `SCAN`，而 `RedisTestSupport.cleanup`
与 3 个测试文件实际调用的是 `template.keys(...)`——Redis `KEYS` 会遍历整个键空间并**阻塞单线程**，
在根的生产/共享实例上属真实运维风险，即**文档与代码直接矛盾**。orchestrator 自有那处已在 `f2b9f1e`
修掉（新增 `scanKeys`：`SCAN` + `ScanOptions.match(prefix+"*").count(200)`，`Cursor` 以
try-with-resources 关闭），其余 5 处分属两条实施道、已在其任务书中要求改用 `scanKeys`。
**该缺陷为何在本地未被发现**：本地测试容器只重命名禁用了 `FLUSHALL`/`FLUSHDB`/`CONFIG`，
**没有禁用 `KEYS`** ⇒ 本地跑通掩盖了它。这是测试环境与生产环境的真实差异，如实记录。

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

## 11. 实现落点、L2 运行方式与 L3 验收入口（as built）
### 11.1 类与脚本清单
**会话（提交 `9dd5bbb`）**：`web/state/RedisSessionProvider`（实现 `SessionProvider` 全部 5 个方法）、
`web/state/RedisSessionConfig`（仅 `app.state.provider=redis` 激活，只注入 `StringRedisTemplate`）；
`StateKeys` 追加两个纯加法构造器 `sessionByAccessTokenDigest` / `sessionByRefreshTokenDigest`
（+44/−0，只接受小写 64 位 hex 摘要，**绝不自动 hash**，以免"双重摘要"静默错误）。
Lua 4 个：`session-create.lua`（多键 + TTL 同原子步）、`session-rotate.lua`（DEL 旧 at/sid + 写新对）、
`session-drop.lua`（连带撤销三键）、`session-revoke.lua`（`HGETALL`+`DEL` 单原子步 ⇒ 并发登出恰好一个赢家）。

**短信（提交 `5a5958c`）**：`web/sms/SmsStateStore`（端口，含 `SendReservation`）、
`InMemorySmsStateStore`（逐字保留旧内存语义：条带锁、容量上限、机会式剪枝，仅供隔离测试）、
`RedisSmsStateStore`（全部经 Lua + `RedisFailures`）、`SmsStateStoreConfig`（与 `SmsProvidersConfig`
同两道门）、`SmsThrottleWindows`（UTC+8 自然窗口归一，两个后端共用）；
`AliyunSmsCodeProvider` 由 392 行降到 165 行，只保留编排（风控/随机码/发送/错误映射）。
Lua 4 个：`sms-challenge-create.lua`、`sms-challenge-consume.lua`、`sms-rate-limit-reserve.lua`、
`sms-rate-limit-compensate.lua`。**四个脚本的 Lua 布尔返回 = 0、脚本内命名空间拼接 = 0**
（所有被访问的键都经 `KEYS[]` 显式传入）。

### 11.2 L2（opt-in 真实 Redis）运行方式
默认全量套件**不需要任何 Redis**（opt-in 类整类跳过/禁用）。要跑 L2：
```bash
cd backend/web-java
export MAVEN_OPTS="-Xmx768m -XX:MaxMetaspaceSize=320m"
export MVP_A_PG_JDBC=jdbc:postgresql://127.0.0.1:55435/postgres \
       MVP_A_PG_USER=postgres MVP_A_PG_PASSWORD=<db-password>
mvn -B test -Dmvp.test.redis.url=redis://127.0.0.1:6399/5     # 本地受限测试容器，db5 与根真实前提同构
```
实测结果见 §12。**L2 必须比 L1 多执行测试**，否则说明 opt-in 未生效（本轮：642 → 665，+23）。
测试一律用独立随机前缀并只清理自己前缀，**绝不 `FLUSHDB`/`FLUSHALL`**（本地容器已重命名禁用）。

**本地测试容器的可复现创建命令**（用毕 `docker rm -f mvp-b-redis-test`；下列参数取自本轮实际运行的
容器 `docker inspect` 与 `/proc/<pid>/cmdline`，**不是凭记忆书写**）：
```bash
docker run -d --name mvp-b-redis-test \
  -p 127.0.0.1:6399:6379 --memory 128m --cpus 0.5 \
  redis:7 
```
要点：只绑 `127.0.0.1`（不对外）、内存与 CPU 受限、无持久化、重命名禁用 `FLUSHALL`/`FLUSHDB`/`CONFIG`。
**它只是测试夹具，不是部署**；根的真实 Redis 由根自己在私有配置中提供。

### 11.3 L3：root-only 真实 Redis 登录验收入口
类名 **`cn.yuanxin.mvp.web.state.RedisLoginLiveAcceptanceIT`**（`@SpringBootTest(RANDOM_PORT)`，
**不占** 18083/18084）。**三重显式 opt-in，任一缺失即整类跳过**：
1. `MVP_REDIS_LOGIN_LIVE=true`（支持系统属性或环境变量）；
2. 真实 Redis 连接由**根**在命令行提供——`-Dspring.config.additional-location=file:<工作树外绝对路径>`
   或 `-Dspring.data.redis.*`；**测试自身绝不读取、绝不打印私有配置文件内容**；
3. 运行期断言 `app.state.provider=redis` 且 `SessionProvider` bean 为 `RedisSessionProvider`。

驱动的 HTTP 流量：`POST /api/v1/auth/sms-challenges` → `POST /api/v1/auth/sessions` →
用 access token 访问一个已认证端点 → `POST /api/v1/auth/session-refreshes`（断言**旧 access 立即 401**）→
`DELETE /api/v1/auth/sessions/current`（断言 204，随后 401）；并按随机前缀 `SCAN` 断言
登录后有会话键、登出后为 0。**默认走 doubles 固定码（`app.testdouble.sms.fixed-code`），
因此默认不发送真实短信**；只有根另外打开既有阿里云短信 opt-in 才走真实短信
（此时该入口无法自动获知验证码，面向 doubles 自动化）。输出只含键**数量**与布尔结果，
**绝不**含 token、验证码、手机号、完整键、Redis 主机或口令。**退出码非 0 即验收失败。**

根可直接复制的命令（占位符处替换为根自己的值；`<db-password>` 与私有 YAML 路径均不经会话正文）：
```bash
MVP_A_PG_JDBC=jdbc:postgresql://127.0.0.1:55435/postgres \
MVP_A_PG_USER=postgres MVP_A_PG_PASSWORD=<db-password> \
mvn -f backend/web-java/pom.xml test -Dtest=RedisLoginLiveAcceptanceIT \
  -DMVP_REDIS_LOGIN_LIVE=true \
  -Dspring.config.additional-location=file:/abs/path/outside/worktree/application-local.yml
```
**注意**：私有 YAML 须含 `app.state.provider: redis`（否则运行期断言失败 ⇒ 验收不通过，
这是刻意的防呆：避免"以为在用 Redis、实际走内存"）。`spring.data.redis.database` 已修正为 **5**。

## 12. 实施进度与提交（orchestrator 维护）
| 阶段 | 提交 | 内容 | 验证 |
|---|---|---|---|
| 设计 + 公开配置示例 + 基础装配 | `28ef3539feca9d36e557d7bd407af880e236d99c` | 本文档；`pom.xml` 加 `spring-boot-starter-data-redis`（BOM 管版本，默认 Lettuce；**刻意不加** `commons-pool2`：本项目 Redis 命令全为非阻塞含 EVAL，`shareNativeConnection=true` 即可）；`application.yml` 加 `app.state.*`、健康检查开关、prod profile 默认 `redis`；`web/state` 5 个基础类；`TestDoubleProvidersConfig.sessionProvider` 加 `app.state.provider=memory`（`matchIfMissing=true`）互斥门 | `mvn compile` rc=0、`test-compile` rc=0、**全量 618/0/0 BUILD SUCCESS**（与基线一致 ⇒ 零回归）；classpath 实测含 spring-data-redis 3.5.13 + lettuce-core 6.6.0.RELEASE |
| 共享测试接缝 | 见下方提交 | `src/test/java/.../state/RedisTestSupport.java`：opt-in（`-Dmvp.test.redis.url` / `MVP_TEST_REDIS_URL`）、随机前缀、`SCAN`+`DEL` 只清自己前缀、`describe()` 不泄漏主机端口 | javac rc=0；行为探针实测：opt-in 门 false→true、`describe()` 不含 `6399`/`127.0.0.1`、前缀形状 `b-probe-<16hex>:`、键带前缀、TTL>0、清理后 **db5 DBSIZE=0**。**时间线如实标注**：`de55a59` 初版的 `cleanup` 实际用的是 Redis `KEYS`（与文档自称的 SCAN 矛盾），已在 `f2b9f1e` 改为 `scanKeys`（`SCAN` 分页）——详见 §8 的如实更正与 §17.1 BLOCKER 3。 |
| 会话实现 | `9dd5bbb086e8eb25c5d5136fd842be49f080fe73`（15 文件） | `RedisSessionProvider` + `RedisSessionConfig` + `redis/session-*.lua` 4 个 + 契约/opt-in IT + L3 root-only 登录验收入口 + `StateKeys` 纯加法扩展 | 见下方中央验证 |
| 短信状态实现 | `5a5958ca8986b75cac201476a650f3af0107aded`（15 文件，**本轮最终代码 SHA**） | `SmsStateStore` 端口 + 内存/Redis 两实现 + `SmsStateStoreConfig` + `SmsThrottleWindows` + `redis/sms-*.lua` 4 个 + `AliyunSmsCodeProvider` 392→165 行 + 测试改写 | 见下方中央验证 |
| Oracle r26 FAIL 的自有文件修正 | `f2b9f1ef35318f3cb029b9ff5eeba982f7f22d1c`（5 文件 +121 −12） | BLOCKER 3（`KEYS`→`SCAN`，新增 `scanKeys`）、IMPORTANT 5（日志脱敏：仅 `RedisSystemException` 记 message）、IMPORTANT 6（aliyun+memory 默认拒绝 + 逃生门 `app.state.allow-in-memory-with-real-sms`）、IMPORTANT 7（cluster 启动期拒绝，sentinel/standalone 允许）、SUGGESTION 9（更正过强的离线安全表述） | `test-compile` rc=0；定向 12/0/0；真实进程守卫探针 7 种组合全部符合预期且 `leaksTopology=false` |
| Oracle r26 会话侧修复 | `39c8b1196743b089e45390380c4ee5f0d9d1478c`（8 文件） | BLOCKER 1（只读领取 + 单脚本 CAS 轮换）、BLOCKER 2（L3 强制 doubles + 运行期硬断言）、IMPORTANT 4（清理复核不吞错）、SUGGESTION 8（返回码校验）、BLOCKER 3 本道部分 | 见 §12.3 |
| Oracle r26 短信侧修复 | `f6edc2f90f3443c0d279baf0f71bd966b4a41a3e`（8 文件，**当前最终代码 SHA**） | BLOCKER 3 本道部分、IMPORTANT 6 的测试锁定、SUGGESTION 8（四类返回码全校验 + 碰撞有界重生成） | 见 §12.3 |
| Oracle r27 修复（会话侧 + 撤销公开逃生门） | `6b1e68ad1579e67e46f2800220652ae7fa0d9866`（10 文件） | IMPORTANT 4（`L3Cleanup` 纯函数：任一步骤失败即必 FAIL）、IMPORTANT 5（三类异常一律不记 `getMessage()`，只记白名单固定词）、IMPORTANT 6（**删除公开逃生门、改为无条件拒绝** + `StateStoreConfigGuardTest` 9 项含防倒退反射断言）、SUGGESTION 8（rotate `null`/未知码 → 503） | 见 §12.4 |
| Oracle r27 修复（短信侧测试解耦） | `28543fafa7143cd5436b448bc3498cd0f62f0fc1`（1 文件，**本轮最终代码 SHA**） | 装配测试不再加载生产一致性守卫；删除逃生门全部引用；新增 `runnerDoesNotLoadStateStoreGuard` 回归守卫（反射，有判别力） | 见 §12.4 |

**两条实施道并行、写域互斥**（`web/state/**` vs `web/sms/**`；Lua 资源 `session-*.lua` vs `sms-*.lua`），
且**都禁止运行 mvn**（避免 `target/` 与端口争用、避免污染权威数字）；类型检查用 orchestrator 预生成并
实测过的 `javac` + `cp-test.txt` 配方，中央构建与全量回归由 orchestrator 统一执行。

### 12.1 中央验证实测数字（orchestrator 亲跑，`mvn -B clean test` 权威构建）
- `compile` / `test-compile` **rc=0**；构建后 **8 个 `.lua` 全部拷入 `target/classes`**
  （刻意 `clean`：本轮确有实施道的 `javac` 曾把陈旧 `.class`/`.lua` 写进 `target/`，
  不 clean 无法保证资源与类是本轮源码编译所得；本项目也曾发生陈旧 surefire 报告把 386 虚报成 387 的事故）。
- **L1（默认，无任何 Redis）：658 run / 0 failures / 0 errors / 16 skipped，BUILD SUCCESS。**
  执行数 **642 = 基线 618 + 会话道 21（InMemory 契约 9 + 守卫矩阵 6 + StateKeysDigest 3 + KeyShape 3）
  + 短信道 3（`SmsProvidersConfigTest` 6→9）**，逐类对账吻合。
  opt-in 类**全部 skipped/禁用而非 failed**：`RedisSessionContractIT` 9 skipped、
  `RedisSessionConcurrencyIT` 6 skipped、`RedisLoginLiveAcceptanceIT` 1 skipped、
  `RedisSmsStateStoreIT` 类级禁用（`Tests run: 0`）。
- **L2（`-Dmvp.test.redis.url=redis://127.0.0.1:6399/5`）：666 run / 0 failures / 0 errors /
  1 skipped，BUILD SUCCESS。** 执行数 **665 = 642 + 23**
  （`RedisSessionContractIT` 9 + `RedisSessionConcurrencyIT` 6 + `RedisSmsStateStoreIT` 8）
  ⇒ **opt-in 确实生效**；唯一 skipped 是 L3（root-only）。
- **报告卫生**：两轮各 94 份 surefire xml，**幻影报告 0**（逐份反查源文件均存在），新鲜度已校验。
- **清理**：L2 跑后 db5 残留 `b-*` 键 **0**、`DBSIZE` **0**。
- **范围**：相对 `de55a59` 共 **30 文件 / +2892 −322**（生产文件 18）；
  `git diff --check` **rc=0**；禁域（contracts/acceptance/worker-python/face-service/deploy/doc/
  db-migration/auth/config/error/testdouble/pom/application.yml）在这两个提交中 **diff 0**
  （pom 与 application.yml 的改动在更早的基础提交 `28ef353` 中，已单独说明）；构建工件 **0**。
- **资源**：端口 18083/18084 空闲、无遗留 JVM、`mvp-b-redis-test` 仅供测试且用毕销毁。

### 12.2 Oracle 第二十六轮裁定
**VERDICT: FAIL**（3 BLOCKER + 4 IMPORTANT + 2 SUGGESTION，明确"不可整合"）。完整逐条核实与裁定见 **§17**；处置状态与对应提交见 **§17.6**；修复后的中央验证数字见 **§12.3**。被审 SHA = `5a5958ca8986b75cac201476a650f3af0107aded`。

### 12.2b Oracle 第二十七轮裁定（对修复后的 `f6edc2f`）
**VERDICT: FAIL**，但范围大幅收窄：**三个 BLOCKER 全部确认闭合**（refresh/logout 复活、L3 误发真实短信、`KEYS`→`SCAN`），IMPORTANT 7（cluster 启动期拒绝）与 SUGGESTION 9（验证码摘要说明）亦闭合；`InMemorySessionDouble` 不修被判**可接受**（但须持续披露其并发语义不等价、不能用它证明 refresh/logout 竞争安全）。剩余 4 项：IMPORTANT 4（L3 清理失败仍可能 PASS）、IMPORTANT 5（`RedisSystemException` 仍原样记 message）、IMPORTANT 6（**否决我的公开逃生门**）、SUGGESTION 8（rotate 把 `null`/未知码降级成 401）。逐条核实与裁定见 **§18**；被审 SHA = `f6edc2f90f3443c0d279baf0f71bd966b4a41a3e`。

### 12.2c Oracle 第二十八轮裁定（对 `28543fa`）
**VERDICT: PASS-with-notes**。四项（IMPORTANT 4/5/6 与 SUGGESTION 8）**全部判闭合**，**无阻塞发现**，新发现仅 1 条非阻塞 SUGGESTION；明确"**可以将 `28543fa` 作为本轮最终代码 SHA 交总协调整合**"、**不要求补跑 L1/L2、完整验收或 E 全套**、轮次边界确认。完整记录见 **§18.4**。

### 12.3 修复后的中央验证（对 `f6edc2f`；orchestrator 亲跑 `mvn -B clean test`）
- `compile` / `test-compile` **rc=0**；构建后 **8 个 `.lua` 全部拷入 `target/classes`**。
- **L1（默认，无任何 Redis）：675 run / 0 failures / 0 errors / 18 skipped，BUILD SUCCESS。**
  执行 **657** = 上一轮 642 + 会话 `RedisSessionProviderReturnCodeTest` 7 + 短信默认侧 8；
  opt-in 类**全部 skipped 而非 failed**（`RedisSessionContractIT` 9 + `RedisSessionConcurrencyIT` 6 +
  `RedisSessionInterleaveIT` 2 + `RedisLoginLiveAcceptanceIT` 1 = 18）。
- **L2（`-Dmvp.test.redis.url=redis://127.0.0.1:6399/5`）：684 run / 0 failures / 0 errors /
  1 skipped，BUILD SUCCESS。** 执行 **683** = 657 + 会话 opt-in 17 + 短信 opt-in 9 ⇒ opt-in 确实生效；
  唯一 skipped 是 L3（root-only）。
- **orchestrator 事先独立推算的预期数字（L1 675/18、L2 684/1、执行 657/683）与实测逐项精确吻合**
  ——这是比照抄子任务自报更强的对账方式。
- 两轮各 **97 份 surefire xml、幻影报告 0**（逐份反查源文件均存在）、新鲜度已校验。
- 跑后 **db5 残留 `b-*` 键 0、`DBSIZE` 0**；全仓 `.keys(` 计数 **0**；orchestrator 的 6 个冻结文件
  被两条道改动 **0**；相对 `f2b9f1e` 共 16 文件 +917 −117（生产 7）；`git diff --check` rc=0；
  禁域 diff 0；工件 0；端口 18083/18084 空闲；无遗留 JVM。
- **注意 `central-verify.sh` 打印的 `delta` 是含 skipped 的 run 总数之差（本轮为 9），
  不是真实新增执行数**；真实增量须按"执行数 = run − skipped"计算（本轮 683 − 657 = **26**）。
  该指标缺陷已由 orchestrator 识别并在此如实标注，避免后续读者误读。

### 12.4 r27 修复轮的中央验证（对 `28543fa`；orchestrator 亲跑 `mvn -B clean test`）
- `compile` / `test-compile` **rc=0**；构建后 **8 个 `.lua` 全部拷入 `target/classes`**。
- **L1（默认，无任何 Redis）：696 run / 0 failures / 0 errors / 18 skipped，BUILD SUCCESS。**
  执行 **678** = 上轮 657 + 会话侧 **+22**（`RedisSessionProviderReturnCodeTest` +1、`L3CleanupTest` +7、
  `StateStoreConfigGuardTest` +9、`RedisFailuresTest` +5）**−** 短信侧 **1**（删 2 个守卫/逃生门用例、
  加 1 个回归守卫）。opt-in 类**全部 skipped 而非 failed**（ContractIT 9 + ConcurrencyIT 6 +
  InterleaveIT 2 + L3 1 = 18）。
- **L2（`-Dmvp.test.redis.url=redis://127.0.0.1:6399/5`）：705 run / 0 failures / 0 errors /
  1 skipped，BUILD SUCCESS。** 执行 **704** = 678 + 会话 opt-in 17 + 短信 opt-in 9 ⇒ opt-in 确实生效；
  唯一 skipped 是 L3（root-only）。
- **orchestrator 事先独立推算的预期数字（L1 696/18、L2 705/1、执行 678/704）与实测逐项精确吻合**
  ——连续第二轮用"先预测后对账"取代照抄子任务自报。
- 两轮各 **100 份 surefire xml、幻影报告 0**、新鲜度已校验；跑后 **db5 残留 `b-*` 键 0、`DBSIZE` 0**；
  全仓 `.keys(` 计数 **0**；`RedisTestSupport` 被两道改动 **0**；相对 `f6edc2f` 共 **11 文件
  +684 −178**（生产文件 4）；`git diff --check` rc=0；禁域 diff **0**；工件 0；端口空闲；无遗留 JVM。
- 逃生门在 Java 中仅剩 `StateStoreConfigGuardTest:59/65/68` 的**防倒退断言**（非残留）；
  `application.yml` 经 YAML 解析确认 `app.state.*` 实际只剩 `provider` 与 `redis.key-prefix` 两个键，
  环境变量绑定 `APP_STATE_ALLOW_IN_MEMORY_WITH_REAL_SMS` 计数 **0**。

## 13. Lua `KEYS[]` 纪律：一处偏离的根因、裁定与 cluster 迁移路径
Redis 官方要求：**脚本访问的所有键必须显式作为 `KEYS[]` 传入**（cluster 下还必须落在同一 hash slot）。
会话实现初版有三个脚本用"命名空间 + 运行期摘要"在脚本内拼接键名
（`session-rotate.lua:20`、`session-drop.lua:8,10`、`session-revoke.lua:19,22`）。

**根因在 orchestrator 冻结的接口，不在实施道**：`StateKeys` 只提供
`sessionByAccessToken(String token)`（内部做 sha256），**没有**"已知摘要 → 键名"的构造器；
而 `rotate`/`drop` 的调用方手里只有从会话 hash 读到的 `atDigest`/`rtDigest`，拿不到原文 token，
因此只能退化为传命名空间再拼接。处置：
1. **授权实施道对冻结的 `StateKeys` 做纯加法扩展**（不改任何既有签名/常量/语义，因另一条道正在用
   `smsChallenge`/`smsRateLimit`/`codeDigest`/`sha256Hex`/`normalizePrefix`）：新增
   `sessionByAccessTokenDigest(String)` 与 `sessionByRefreshTokenDigest(String)`，
   入参必须是**归一化的小写 64 位十六进制摘要**（长度与字符集校验，否则 `IllegalArgumentException`），
   **绝不做自动 hash**——否则调用方误传原文 token 会造成"双重摘要"这类静默错误。
   必须有测试断言 `sessionByAccessTokenDigest(sha256Hex(t)) == sessionByAccessToken(t)` 逐字节相同。
2. `rotate` 与 `drop` 改为由调用方传入**具体键**，消除拼接。
3. **`revoke` 的拼接保留**，因为它是**结构性不可避免**：`sid` 与 `rt` 摘要来自脚本内 `HGETALL`
   的结果，调用方执行前无法知道；而"读取 + 删除"必须原子才能保证并发登出**恰好一个赢家**
   （这是 `AuthController:136` 用 `RevokedSession` 失效 T09 的前提）。拆成两步会重新打开竞态。
4. **cluster 兼容如实登记为已披露限制**：本轮部署是 standalone（根的私有配置为
   host/port/password/`database=5`），拼接在 standalone 下正确；**cluster 下不成立**。
   迁移路径（本轮不实现）：`sess:at:<digest>` 只存 sessionId，会话数据集中在带 hash tag 的
   `sess:{sessionId}` 单键；撤销改两步——先 `GETDEL` at→sid 保证恰好一次，再对 `sess:{sessionId}`
   及其派生键以**完整 `KEYS[]` 声明**执行第二个脚本。

## 14. orchestrator 已亲自复核的关键事实（不采信子任务自报）
- **`BearerAuthFilter:81-87` 逐字为** `try { principal = sessionProvider.authenticate(token); }`
  `catch (RuntimeException infra) { log.error(...); dependencyUnavailable(request, response); return; }`，
  而 `:88-90` 才是 `principal.isEmpty()` → 401 `SESSION_INVALID`。
  ⇒ **Redis 故障（以 `ApiException` 形式抛出）走 503 `DEPENDENCY_UNAVAILABLE`，不会被降级成 401**，
  且**无需修改** `BearerAuthFilter`。这是 fail-closed 得以成立的前提，已独立验证。
- **会话实现初版的写域干净**：`git status` 中 `web/state/**` 与其测试全部为 `??` 新增，
  **0 个 tracked 文件被修改**（同批 `M` 条目全属并行的 `web/sms/**` 道）。
- **Lua 原子性形态正确**：`session-create.lua` 对三个键的 `HSET` 与 `EXPIRE` 在同一脚本内完成
  （不会留下无 TTL 的键）、返回整数 1；`session-create.lua:18` 把 `rt` 摘要写进 access hash，
  这正是"单脚本撤销"得以成立的前提；`session-revoke.lua` 用 `HGETALL`+`DEL` 返回 table
  （`{sid, kind, aid, iid}`，未命中返回 `{}`），**不使用 Lua 布尔**（`return false` → Redis nil →
  Java `null`，用布尔接收会踩坑）。

## 15. orchestrator 本轮自身缺陷（如实记录）
1. **进度探针的排序缺陷导致我错报事实**：我用 `find -printf '%TH:%TM:%TS %p' | sort | tail -1`
   取"最新文件"，但该格式**只含时分秒、不含日期**，字典序下昨天的 `21:11:30` 会"晚于"今天的
   `15:11:23`。据此我一度报告"短信道 `web/sms` 尚无源码写入、正处长读码阶段"，
   **而事实上它当时已写出 11 个源文件 + 4 个 Lua 脚本并跑完负向探针**。已改为按 `%T@`（epoch）
   `sort -n`，并落成可复用的只读探针 `.coordination/B-work/redis-migration/lane-progress.sh`。
   后果有限（我**没有**据此重派或取消任何道——本项目早前正因据片面信号误判 fix-7 死亡而重派、
   造成同文件重复写者，这次纪律生效），但报告内容与事实不符，必须更正。
2. **脚本加固被自己的引号转义悄悄破坏**：给 `central-verify.sh` 打补丁时，我在 `<<'PY'` heredoc 里
   用 `'"'"'` 做 shell 转义，导致 Python 把后续赋值吞进字符串，抛
   `NameError: name 'old2' is not defined`，**补丁实际未生效**，而紧随其后的 `bash -n` 校验的是
   未修改的旧文件、自然通过 ⇒ 形成"看起来已加固"的假象。改为**整文件重写**，并对新加的
   报告卫生检查做了**判别力自测**：对现存 86 份 surefire 报告 `phantom=0` 且 86/86 反查到真实源文件；
   植入上轮真实事故的主角（已删除的 `MediaPolicyDelegationIT`）后**准确报出 `!! PHANTOM` 且计数变 1**，
   随后清除恢复 86。该检查正是为了防住"陈旧 surefire 报告把权威 386 虚报成 387"那类污染。
3. **实施道把部分 `javac -d` 指到了 `target/`**（14 个 `.class`/`.lua` 产物）：违反配方，
   已用非打断 `task_message` 纠偏并明确**不要**自行清理 `target/`（另一道的 javac classpath 依赖它）。
   核实**未污染权威数字**：`maven|surefire` 进程精确计数 0、`target/surefire-reports` 最新仍是
   orchestrator 14:46:54 那次全量 ⇒ 无人经 mvn 跑过测试。中央验证脚本已相应加固
   （全量前删除陈旧报告、跑后校验报告新鲜度并做幻影检查）。

4. **shell 重定向把日志文本变成了仓库根的游离文件**：我的只读进度探针里写了
   `echo idle>10min`（本意是输出文本 "idle>10min"），shell 将 `>` 解析为重定向，
   于是在**仓库根**创建了名为 `10min`、内容为 `idle` 的游离文件（mtime 与探针运行同秒，
   由实施道发现并上报）。已删除，并把探针改为不含 `>` 的 `verdict="IDLE?"` 形式。
   教训：探针脚本里的任何 `>` 都必须确认是重定向还是文本；游离文件若未及时发现，
   可能被后续 `git add -A` 带进提交。
5. **凭记忆拼多行锚点导致文档更正静默失败**：给本文档打两处更正时，我用记忆中的缩进写了多行
   `old` 字符串，`assert t.count(old)==1` 失败（实际 0 命中），而紧随的 `cat >> §17` 仍成功
   ⇒ 一度形成"§17 已追加但两处错误主张仍在文中"的半成品状态。改为**先读原文、按单行子串定位、
   按行号替换**后成功，并回读验证（过强表述残留 0、更正说明 4 处、BLOCKER 3 更正就位）。

## 16. 短信侧实现的 orchestrator 独立核验（不采信子任务自报）
### 16.1 一处解释分歧的裁定：尝试计数是 hash 字段，不是独立键
实施道询问"计数键必须有 TTL"是否要求独立的尝试计数键。**裁定：不要求，实施道的读法正确，
我的任务书措辞不精确。** 依据本文档权威定义：§3 键表第 109 行
`<p>sms:ch:<challengeId>` 为 **hash**，字段 `cd`/`ph`/`exp`/**`att`**；§5 TTL 表第 155 行
"尝试计数 | 与 challenge 同生命周期（**同一 hash 字段**，随键一起过期）| 避免留下孤儿计数"。
独立计数键反而更差（会留下孤儿计数，且需要第二条 TTL 纪律）。我任务书里那句"计数键必须有 TTL"
针对的是**限流窗口计数键**（`sms:rl:*`），那里确实用了 `INCR` + `if count==1 then EXPIRE` 同一脚本。
### 16.2 四个 Lua 脚本逐条核实（全部合规）
`grep` 实测：四个脚本的 **Lua 布尔返回 = 0**、**命名空间拼接（`KEYS[n] ..`）= 0**，
即所有被访问的键都经 `KEYS[]` 显式传入（这一点比会话实现初版更严格）。
- `sms-challenge-consume.lua`：`EXISTS` → 过期(`DEL`+`!`) → 尝试上限(`DEL`+`!`) → 摘要比较
  （不符则 `att+1`、达上限即 `DEL`、返回 `!`）→ 读 `ph` → `DEL` → 返回 `'+'..phone`，
  **整个临界区在单个原子步内**，与既有 `AliyunSmsCodeProvider:180-206` 的顺序逐条对应。
- `sms-rate-limit-reserve.lua`：先读三窗口，任一超限则返回 retryAfter **且不占用名额**；
  否则对三个键 `INCR` + `if count==1 then EXPIRE`（官方与实测确立的唯一可靠写法）。
- `sms-rate-limit-compensate.lua`：`EXISTS` 守卫的 `DECR`，≤0 即 `DEL`。
- `sms-challenge-create.lua`：`EXISTS` 守卫（已存在返回 0 = "不存在才创建"），
  `HSET cd/ph/exp/att=0` 与 `EXPIRE` 在同一脚本内（不会留下无 TTL 的键）。
### 16.3 明文验证码不落 Redis（已核实调用点）
`RedisSmsStateStore:131`（创建）与 `:145`（核销）传入的都是 `StateKeys.codeDigest(code, challengeId)`，
**不是**明文。**如实限制**：加盐摘要只保证明文不出现在 Redis/日志/导出中，**不能**抵御持有只读快照者的离线枚举（6 位码约 20 bit 熵、challengeId 对客户端可见）；抵御快照泄漏需服务端 secret 的 HMAC/pepper，本轮未实现（详见 §3 第 5 条与 §17.3）。
### 16.4 "发送失败不签发 challenge"的顺序完整保留
`AliyunSmsCodeProvider:89` 预留 → `:90` 未获准则 429 → `:95` 随机码 → `:98` 远端发送 →
`:104-106` `!result.accepted()` 即 `mapFailure`（`Code=="OK"` 仍是唯一成功判据，在
`AliyunSmsSendGateway:102`，未改）→ `:108` `accepted=true` → `:109` `commitSend` →
`:111` `createChallenge`；`:113-114` `finally` 中 `releaseSend(reservation, accepted)` 做补偿。
`:99-103` 的 gateway 异常分支注释明写"绝不回退替身、绝不签发 challenge"。
### 16.5 脱敏与断言强度
provider 与两个 store 的 `log.`/`System.out`/`printStackTrace` 计数均为 **0**；
5 处 `SmsMasking.` 全在 `AliyunSmsSendGateway`（既有）。
`AliyunSmsProviderBoundsTest:92` 仍是 `contains("max=2").doesNotContain(PHONE_C)`、
`:127` 仍是 `contains("max=1").doesNotContain(PHONE_B)` ⇒ 容量拒绝消息不含手机号的断言**未被弱化**；
`AliyunSmsSecurityTest`、`AliyunSmsVerifyConcurrencyTest`、`AliyunSmsIssueConcurrencyTest`、
`AliyunSmsSendGatewayTest`、`AliyunSmsSmokeConfigEncodingTest`、`AliyunSmsLiveSmokeIT`
六个文件 **diff 均为空（未修改）**。
### 16.6 负向判别力为真实失败（非空洞断言）
- A：把原子 Lua 核销改成 Java 两步 `GET`→比较→`DEL` ⇒ `RedisSmsStateStoreIT` 3 项失败，
  其中 `concurrentConsumeExactlyOneWinner` 报 `Expecting an empty Optional but was containing value:
  "+8610000000000"`（即出现多赢家）；还原后 sha1 一致、缺陷标记 grep = 0。
- B：把 reserve 脚本的 `EXPIRE` 去掉 ⇒ `rateLimitKeysAlwaysExpire` 失败于
  `RedisSmsStateStoreIT.java:183`「窗口键 TTL 必须 > 0」，`minuteWindowThrottleUsesUtcPlusEightBuckets`
  亦失败；还原后 8/8 通过。
### 16.7 装配矩阵：`disabled` 最高优先级**未被削弱**（orchestrator 亲自核实）
- `SmsProviderEnabledCondition` **diff = 0（未被触碰）**，`:24` 仍为 `return !"disabled".equals(mode)`。
- `SmsStateStoreConfig:34-35` 携带与 `SmsProvidersConfig` **完全相同的两道门**
  （`app.sms.provider=aliyun` + `@Conditional(SmsProviderEnabledCondition.class)`）
  ⇒ `mode=disabled` 时**不装配任何 `SmsStateStore` bean**。
- `SmsProvidersConfigTest` 由 6 例扩到 **9 例**，其中三条决定性：
  * `disabledWinsOverRedisStateStore`（`:131-145`）：`mode=disabled` + `provider=aliyun` +
    `app.state.provider=redis` ⇒ 上下文未失败、provider 不是 `AliyunSmsCodeProvider`、
    **`getBeansOfType(SmsStateStore.class)` 为空**、`issue()` 抛 `DEPENDENCY_UNAVAILABLE`；
  * `disabledWinsOverAliyun`（`:149-161`）：并断言 `getHttpStatus()==503`；
  * `productionSignalStillRejected`（`:180-188`）：断言**既有**早期守卫仍先触发，消息为
    `app.providers.mode=doubles is not allowed` ⇒ 新增的 `StateStoreConfigGuard` **没有抢跑**
    （这正是把其规则③收窄到 `mode=real` 的目的）。
  另 `defaultDoubles` 仍断言 `verify(challengeId,"123456")` 返回手机号 ⇒ doubles 行为未变；
  `aliyunUsesInMemoryStateStoreByDefault` / `aliyunUsesRedisStateStoreWhenConfigured` 覆盖新维度；
  `aliyunMissingKeysRefusesStartup` 仍只列键名、不回显值。

## 17. Oracle 第二十六轮（对 `5a5958c`）：**VERDICT FAIL**，我的逐条核实与裁定
Oracle 判 **FAIL**、明确"**不可整合**"，给出 **3 BLOCKER + 4 IMPORTANT + 2 SUGGESTION**。
orchestrator 逐条读码核实（不盲从也不盲驳），**全部成立**，其中 **4 项落在我自己写的文件里**。
先修自有文件（提交 `f2b9f1e`），其余按写域派回两条实施道。

### 17.1 三个 BLOCKER
**(1) refresh 与 logout 交错会复活已登出的会话** —— **成立**。
`RedisSessionProvider:151-154` 先用 `getAndDelete` **破坏性领取** refresh，`:159-186` 读索引/会话并做
DB 代次复核，`:194-200` 才跑 `session-rotate.lua`；而该脚本 `:20-29` **无条件** `DEL` 旧键并创建新会话、
**不校验旧会话是否仍存在**。交错：领取 → DB 复核后暂停 → logout 成功 revoke（删 at/sid/rt）返回 204 →
rotate 仍造出新会话 → refresh 返回可用 token ⇒ **登出被复活**。附带缺陷：领取是破坏性的，
中途 Redis/DB 失败会**烧毁凭据却不签发会话**，重试只能 401。
**我补充查证的一项事实**：`InMemorySessionDouble:80/105-106` 有**结构完全相同**的竞态
（`refreshToSession.remove` → `revokeBySessionId` → `createAppSession`，无跨操作同步）⇒
该竞态是**既有的、非本轮引入**；但用户把"refresh/logout 并发不可复活"列为明确要求，
且跨实例下概率显著上升，**必须修**。
**裁定**：按"只读领取 + 单脚本 CAS 轮换"重做——rotate 脚本收 6 个具体键，依次校验
`GET rtKey == expectedSid`（否则返回 0=已被消费）、`EXISTS oldSidKey`、`EXISTS oldAtKey`
（任一不存在返回 2=已撤销），全部通过才 `DEL` 三旧键并写三新键返回 1；
**调用方仅在返回 1 时才可返回新 token**。内存替身的同类竞态**本轮不修**（仅供隔离测试、既有缺陷、
修它会扩大到 `web/testdouble/**`），但"不可复活"断言**只放 Redis 侧 IT**、不进两后端共享的契约测试，
并把该限制如实登记。
**(2) L3 可能向随机真实手机号发送真实短信** —— **成立，且是本轮最高风险项**。
`RedisLoginLiveAcceptanceIT:129-130` 生成随机 `+86139XXXXXXXX`、`:134` 直接 POST f01，而
`@DynamicPropertySource`（`:99-100`）只设键前缀，**全文没有任何强制 `app.sms.provider=doubles`**。
根的私有 YAML 若为 `aliyun`（根一直在做真实短信联调，极可能如此），f01 会经真实阿里云网关
**向一个随机生成的真实号段号码发送真实短信**——对无关第三方的实际伤害。
**根因在我**：我的任务书写的是"**默认**走 doubles 固定码，因此默认不发真实短信"，即依赖**默认值**
而非**强制**；实施道照此实现并无过错。**裁定**：`@DynamicPropertySource` 中**强制**
`app.sms.provider=doubles` 并显式设固定码，使 L3 **结构上不可能**发真实短信；再加运行期断言
`SmsCodeProvider` bean 是 `SmsCodeDouble`，否则中止；javadoc 删去"依赖默认值"的措辞。
**(3) 测试基建用 `KEYS` 而非 `SCAN`** —— **成立，是我亲手写的**。
`RedisTestSupport:132` 为 `template.keys(prefix + "*")`，而本文档 §8/§13 自称 `SCAN`
⇒ **代码与文档直接矛盾**；`KEYS` 会遍历整个键空间并**阻塞 Redis 单线程**，在根的生产/共享实例上
属真实运维风险。另有 5 处 `.keys(` 散在 3 个测试文件中。
**为何本地没发现**：本地测试容器只重命名禁用了 `FLUSHALL`/`FLUSHDB`/`CONFIG`，**未禁用 `KEYS`**。
**裁定**：`RedisTestSupport` 新增 `scanKeys`（`SCAN` + `ScanOptions.match(prefix+"*").count(200)`，
`Cursor` 以 try-with-resources 关闭），`cleanup` 改为基于它；其余 5 处由两道分别改用 `scanKeys`。

### 17.2 四个 IMPORTANT
**(4) L3 清理吞错且不复核** —— 成立。`:216-220` 的 `catch (RuntimeException ignored) {}` 会让清理失败
被完全吞掉，L3 可以 PASS 却残留短信限流键与会话键。裁定：清理后用 `scanKeys` **断言自己前缀剩余 0**；
清理异常不得静默吞掉（失败或以 `addSuppressed` 保留并明写 "cleanup incomplete"，绝不打印键名）；
DB 侧清理须报告删除行数。
**(5) `RedisFailures` 记录异常原文可能含主机/端口** —— 成立，**是我的文件**，且与本文档
"绝不包含 Redis 主机"的声明矛盾。裁定：只对 `RedisSystemException`（服务端错误，如
`ERR DB index is out of range`/`READONLY`/`OOM`/`WRONGPASS`，均不回显拓扑与口令）记 message；
连接失败与超时只记异常类名，并在日志中明写 "message suppressed: it may contain Redis host/port"。
**(6) 真实短信 provider 可搭配内存状态** —— 成立。`SmsStateStoreConfig:41-42` 在
`app.state.provider=memory`（`matchIfMissing=true`）下装配内存 store，即使 `app.sms.provider=aliyun`
⇒ 违反"联调/真实 provider 使用 Redis"。**我对修法做了与 Oracle 建议不同的选择并说明理由**：
Oracle 建议"guard 拒绝 `aliyun && state!=redis`"，但**无条件拒绝会打断合法单元测试**
（`SmsProvidersConfigTest` 用**假 gateway** 驱动 `AliyunSmsCodeProvider` 的编排逻辑：风控、随机码、
错误映射，这些测试不应被要求提供 Redis）。故采用**默认拒绝 + 显式测试逃生门**
`app.state.allow-in-memory-with-real-sms`（默认 `false`），使规则保持**可执行**而非弱化成告警；
打开逃生门时记 WARN 明写状态不跨实例、不存活重启。
**(7) 接受 cluster 配置但多键 Lua 无 hash tag** —— 成立。`CONNECTION_KEYS` 原把
`spring.data.redis.cluster.nodes` 当作"已配置连接"，而 8 个脚本都访问多键 ⇒ 运行期必然 `CROSSSLOT`。
裁定：`provider=redis` 且设置 cluster.nodes ⇒ **启动期明确拒绝**（消息说明原因与替代方案），
并从 `CONNECTION_KEYS` 移除该键；**standalone 与 sentinel 允许**（单 master，多键脚本成立）。

### 17.3 两个 SUGGESTION
**(8) Lua 返回码未被校验** —— 成立。`RedisSessionProvider:137/184/194/237` 忽略脚本返回值；
`RedisSmsStateStore` 仅在 `reserveSend` 检查 `result == null`（`:100`）。裁定：会话侧 create/rotate/drop
全部校验返回码（**仅 1 才可返回凭据**）；短信侧 `createChallenge` 返回 0（challengeId 碰撞）必须
**有界重生成**、绝不静默当作成功，`consumeChallenge` 对非预期返回（既非 `+` 也非 `!`）一律 fail-closed 503
而**不是** 401（否则掩盖故障）。
**(9) 我对验证码摘要离线安全性的表述过强** —— 成立，**是我的表述错误**，已在 §3 与
`StateKeys` javadoc 同步更正（6 位码约 20 bit 熵 + `challengeId` 对客户端可见 ⇒ 只读快照可离线枚举；
抵御快照泄漏需服务端 secret 的 HMAC/pepper，本轮未实现，登记为限制）。

### 17.4 Oracle 判为**可接受**的项（无需再改）
Lua 内对定长加盐摘要做等值判断**不构成现实在线安全弱化**（摘要定长、每 challenge 尝试预算由 Lua
原子限制、网络时序样本不足以利用短路比较）；节流"**原子预留 + 失败补偿**"可接受且披露充分；
TTL 取代应用层容量上限可接受，但**独立实例 / `maxmemory` / `noeviction` / 容量告警必须定为生产要求
而非普通建议**；`revoke` 的命名空间派生在 standalone 下可接受（但 cluster 不兼容**不限于 revoke**：
create/rotate 与短信多键脚本同样没有共同 hash tag ⇒ 已由 IMPORTANT 7 的启动期拒绝覆盖）；
不新增 504 符合既有契约；装配的 memory/redis 互斥与"`RedisSessionProvider` 不会被误判为替身"通过；
健康检查默认关闭**可用于保留测试**，但**生产必须显式开启**（Redis 承载认证后，health 不反映 Redis
会让流量继续进入只能返回 503 的实例）——已登记为生产部署要求。

### 17.5 orchestrator 本轮新增的自身缺陷（第 4 项，流程性）
**向"即将产出结论的审查道"投递 `task_message`，导致它只回一句确认就结束回合、裁定正文丢失。**
第二十六轮第一次派发后，我用 `task_message` 追加了两项审查重点，Oracle 随即以
"已记录补充审查重点；本消息不另行回复"终结，**审查结论从未产出**；我核实磁盘（其授权目录不存在、
近 25 分钟零写入）与 `task_result` 后确认产出确实丢失，只能**恢复同一会话**重新索取裁定
（幸而会话上下文保留，未浪费已读代码）。**新纪律**：审查道在飞期间**不投递任何消息**；
确有补充要求时，等其终结后在**新一轮派发**中一并给出。

### 17.6 处置状态
| 发现 | 归属 | 处置 | 提交 |
|---|---|---|---|
| BLOCKER 3（`KEYS`→`SCAN`，我的文件） | orchestrator | 已修：新增 `scanKeys`，`cleanup` 改基于它 | `f2b9f1e` |
| IMPORTANT 5（日志可能含主机） | orchestrator | 已修：仅 `RedisSystemException` 记 message | `f2b9f1e` |
| IMPORTANT 6（aliyun+memory） | orchestrator | 已修：默认拒绝 + 显式逃生门 + WARN | `f2b9f1e` |
| IMPORTANT 7（cluster） | orchestrator | 已修：启动期拒绝 cluster，sentinel/standalone 允许 | `f2b9f1e` |
| SUGGESTION 9（表述过强） | orchestrator | 已修：`StateKeys` javadoc + 本文档 §3 同步更正 | `f2b9f1e` |
| BLOCKER 1（refresh/logout 复活） | 会话道 | 已修：只读领取 + 单脚本 CAS 轮换（6 具体键、返回码 0/1/2）+ 仅返回码 1 才返回 token + 确定性交错与 60 轮并发测试 | `39c8b11` |
| BLOCKER 2（L3 可能发真实短信） | 会话道 | 已修：`@DynamicPropertySource` **强制** doubles + 显式固定码，f01 之前运行期硬断言 `SmsCodeDouble`，javadoc 删去依赖默认值的措辞 | `39c8b11` |
| IMPORTANT 4（L3 清理吞错） | 会话道 | 已修：清理后 `scanKeys` 复核残留，>0 或无法复核即抛 `cleanup incomplete`；异常 `addSuppressed` 保留；输出只有计数与类名 | `39c8b11` |
| BLOCKER 3 的其余 5 处 `.keys(` | 两道 | 已修：全部改用 `RedisTestSupport.scanKeys`；orchestrator 复核全仓 `.keys(` 计数 = **0** | `39c8b11` / `f6edc2f` |
| SUGGESTION 8（返回码校验） | 两道 | 已修：会话侧 `requireAck` 覆盖 create/gimbal/drop、rotate 非 1 即 empty；短信侧四类返回码全校验（非契约返回一律 503，**不降级 401**）+ challengeId 碰撞有界重生成 3 次后 503、**绝不签发未写入的 challenge**；`InMemorySmsStateStore` 同步改 `putIfAbsent` 使两后端都诚实 | `39c8b11` / `f6edc2f` |
| IMPORTANT 6 的测试锁定 | 短信道 | 已修：矩阵 runner **内嵌守卫**（此前守卫不在测试上下文中＝零覆盖）；新增拒绝用例与逃生门 WARN 用例（logback appender 捕获断言）；既有断言未弱化、失败根因未被偷换 | `f6edc2f` |
## 18. Oracle 第二十七轮（对 `f6edc2f`）：**VERDICT FAIL**，我的逐条核实与裁定
Oracle 确认**三个 BLOCKER 全部闭合**、IMPORTANT 7 与 SUGGESTION 9 闭合、**新发现：无**，
但仍判 FAIL、明确"不可整合"，剩余 4 项。orchestrator 逐条读码核实，**四项全部成立**，
其中第 3 项是 Oracle **否决了我的设计选择**，我采纳其意见并撤销自己的方案。

### 18.1 已确认闭合（无需再改，Oracle 明列下一轮不必重审）
- **BLOCKER 1**：refresh 改只读 `GET`（`RedisSessionProvider:163-170`）、旧 rt/sid/at 在**单 Lua 内 CAS**
  并轮换（`session-rotate.lua:25-43`）⇒ logout 先成功时三项至少一项不存在、rotate 返回 0/2、不创建新会话；
  两个并发 refresh 只有一个能消费旧 refresh；DB revision 不符时主动 drop 属**既有撤销语义**、不是部分轮换；
  `RedisSessionInterleaveIT` 的阻塞 `JdbcTemplate` 能**确定性**制造旧缺陷窗口 ⇒ 具备真实判别力。
  Oracle 另裁定 `EXISTS sid/access` 对当前正常并发足够，更强的字段关联校验属"抗 Redis 数据损坏"的增强、非阻塞。
- **BLOCKER 2**：上下文创建前强制 SMS doubles（`:104-114`）+ f01 前再次硬断言 `SmsCodeDouble`（`:140-146`）；
  私有 YAML 的 aliyun 配置**无法覆盖** `@DynamicPropertySource` ⇒ L3 结构上不会调用真实短信网关。
  Oracle 并采纳我的边界：真实短信 + 真实 Redis 应保留为**独立、人工、固定测试号码**流程，不混入自动 L3。
- **BLOCKER 3**：`SCAN` 实现与游标关闭（`RedisTestSupport:128-158`）、L3 统计也用 SCAN（`:207-210`）、
  源码 `.keys(` 为 0；随机独占前缀下无并发写者，故 SCAN 的弱一致性不会造成漏键。
- **IMPORTANT 7**：`StateStoreConfigGuard:92-105,133-149` 在 `provider=redis` 时先拒绝 `cluster.nodes`，
  standalone/sentinel 保留；Oracle 确认说明已正确扩展到**全部多键 Lua**、不再只归因 revoke。
- **SUGGESTION 9**：验证码摘要说明已准确区分"避免明文进入 Redis/日志"与"不抵御低熵码离线枚举"，
  并写明若需抵御只读快照应使用 secret HMAC/pepper。
- **`InMemorySessionDouble` 不修可接受**：它仅在明确 doubles 隔离环境装配、生产不可达；
  但**必须持续披露其并发语义不等价，不能用它证明 refresh/logout 竞争安全**。

### 18.2 剩余四项（我读码核实全部成立）与处置
**(1) IMPORTANT 4 未完全闭合**：`RedisLoginLiveAcceptanceIT.cleanup`（`:241-291`）只在
`leftover > 0 || leftover < 0` 时抛错（`:259-267`）。若 `RedisTestSupport.cleanup` 抛异常
（`:245-247` 记入 `cleanupFailure`）但随后 SCAN 得 0，方法会继续走到 `:286-290` **只打印**
`cleanup-incomplete-suppressed=<类名>` 而**测试 PASS**（"delete 响应失败但键其实已删掉"正是此情形）；
DB 侧异常（`:277-285`）同样只打印。**处置**：所有清理步骤执行完后，**只要 `cleanupFailure != null`
就必须抛出**，其余异常以 `addSuppressed` 保留；并补一个有判别力的测试模拟"删除抛异常但键已不存在"。
**(2) IMPORTANT 5 只部分闭合**：`RedisFailures:71-73` 对 `RedisSystemException` 仍记 `getMessage()`。
我代码注释里写的"服务端错误均不回显口令与拓扑"是**我未经验证的假设**；Oracle 指出该异常并不保证
只包装纯服务端 `ERR`，未知 driver 异常也可能携带 host/port。**处置**：取更严的一方——对**全部三类**
异常只记 `operation` 与异常类名，**绝不记 `getMessage()`**；如需保留服务端错误可诊断性，只允许用严格
正则提取**白名单错误码**（`ERR DB index is out of range`/`READONLY`/`OOM`/`WRONGPASS`/`CROSSSLOT`），
命中记该词、否则记 `<unclassified>`；并补测试（构造含 host:port、口令样式子串、中文与换行的 message，
断言日志输出不含这些内容）。同时删去我那句未经验证的注释断言。
**(3) IMPORTANT 6 —— Oracle 否决了我的"公开逃生门"，我采纳**：我上一轮为实现
"aliyun + memory 默认拒绝"引入了 `app.state.allow-in-memory-with-real-sms`，并把它写进
`application.yml` 作为**公开运行时开关**（默认 false），理由是单元测试需要。Oracle 的反对成立：
这等于给"真实阿里云短信 + 进程内状态"留了一条**文档化的合法绕过路径**，直接绕过跨实例一致性要求；
而**单元测试不应当驱动生产配置去获得一致性逃生门**。
**处置（撤销我的方案，按 Oracle 建议重做）**：①orchestrator 已从 `application.yml` 移除该属性；
②删除 `StateStoreConfigGuard` 中的常量与 hatch 分支 ⇒ **无条件拒绝** `aliyun + 非 redis`；
③`SmsProvidersConfigTest` **不再加载守卫**（装配测试的职责是"给定组合装配出哪个 bean"，
守卫的职责是"哪些组合根本不允许启动"，混在一个上下文里会迫使测试为通过守卫而放宽生产规则）；
④守卫的正向单元测试改由 `web/state` 侧用 `MockEnvironment` + `DefaultListableBeanFactory` 直接调
`postProcessBeanFactory` 完成（不需要 Spring 上下文、不需要 Redis）；⑤补一条**防倒退**断言，
使将来有人把守卫塞回装配矩阵或重新引入逃生门时测试失败。**我如实记录：这是我本轮第二次被
Oracle 纠正设计选择（第一次是 OSS 轮的 V4 迁移方向，那次是我的裁定被确认正确），
这次的教训是——不要为了可测性而在生产配置面上开一致性后门；正确做法是让测试不加载该规则。**
**(4) SUGGESTION 8 残留**：`RedisSessionProvider:218-220` 把 `rotateCode == null` 与任何未知码
一并映射为 `Optional.empty()`（401 语义）。脚本业务码只有 0/1/2，`null` 或其它值代表**脚本协议错误或
后端异常**，当成"refresh 无效"会掩盖故障、违反 fail-closed。**处置**：`1` → 返回新 token；
`0`/`2` → `empty`；**`null`/其它 → 抛 503 `DEPENDENCY_UNAVAILABLE`**（复用同文件既有的
`requireAck`（`:275-282`）范式）；并把 `RedisSessionProviderReturnCodeTest` 中"rotate null ⇒ empty"
那条断言改为断言抛 503、新增"未知码（如 7）⇒ 503"，**不得弱化** 0/2 ⇒ empty 与 1 ⇒ 返回 token。

### 18.3 本轮调度与文档纪律
- 派两条道并行修复，写域互斥（`web/state/**` vs `web/sms/**`），均禁跑 mvn；`application.yml` 由
  orchestrator 独占改动以避免冲突。**已知依赖风险**：`web/state` 侧删除常量后，若 `web/sms` 侧未及时
  移除引用会编译失败——已在两道任务书中分别前置说明，由中央构建统一发现并回弹。
- **审查道在飞期间不投递任何消息**（r26 丢失裁定正文的教训，见 §17.5）。
- 文档重排：此前用 `cat >>` 追加导致 §12 的四个子节孤悬在文档末尾（父标题 `## 12.` 在第 344 行、
  紧接 `## 13.`，而 12.1/12.3/12.2/12.2b 在 490-534 行）。本轮趁 Oracle 已终结、两道均禁改本文档的
  窗口做**只调物理顺序、不改编号**的安全重排（12.1 → 12.2 → 12.2b → 12.3 本身即升序，故**无需改动
  任何交叉引用**），并在重排前备份到 `.coordination/B-work/redis-migration/doc-before-restructure.md`。
### 18.4 Oracle 第二十八轮（对 `28543fa`）：**VERDICT PASS-with-notes**
四项**全部判闭合**、**无阻塞发现**，并明确"可以将 `28543fa` 作为本轮最终代码 SHA 交总协调整合"、
**不要求补跑 L1/L2、完整验收或 E 全套**（理由：现有 696/705 测试与定向负向证据已充分）、轮次边界确认。
逐条要点：
- **IMPORTANT 4 闭合**：`L3Cleanup.java:35-80` 在 Redis 删除、`SCAN` 复核与 DB 清理**全部执行完**后统一判定，
  `failure != null || leftover != 0` 都会抛出 ⇒ "Redis 删除异常但 SCAN=0"不再可能 PASS、DB 异常同样使测试失败；
  异常原文不输出，只输出计数与异常类名。Oracle 并裁定**把它抽为 `src/test` 纯函数是合理的**
  （否则失败分支必须依赖真实 Redis 才能测），且"3 项负向失败 + 还原后 7/7"的证据具备判别力。
- **IMPORTANT 5 闭合**：`RedisFailures.java:84-95` 三类异常统一只记 operation、异常类名与固定白名单词；
  原始 `getMessage()` 只在内部匹配（`:103-124`）、**不进入日志**。Oracle 并裁定白名单"均是不含参数的稳定
  Redis 错误标识；恶意消息最多造成错误分类词误导，不会把原消息带入日志"，未知错误记 `<unclassified>`
  是**正确的安全优先取舍**。
- **IMPORTANT 6 闭合**：生产代码已无运行时逃生门（`StateStoreConfigGuard.java:144-167`）、
  `application.yml` 只剩注释而**不存在可绑定属性**、aliyun+memory **无条件拒绝**；Oracle 明确认可职责拆分——
  "装配单测不加载全局一致性 guard，而 guard 自身用独立单元测试验证……**不需要为了 fake gateway 测试
  开放生产配置后门**"，且既有短信装配/缺配置/disabled/生产 doubles 断言**未弱化**。
  对我接受的取舍（回归守卫反射 Boot 私有字段）裁定为"较脆弱，但升级后会**响亮失败**而非静默通过，
  在版本已钉住 3.5.16 时**可接受**"。
- **SUGGESTION 8 闭合**：`RedisSessionProvider.java:271-285` 分派正确（1 → 返回新 token；0/2 → empty；
  null/任何其它值 → 503 `DEPENDENCY_UNAVAILABLE`）；Oracle 并确认"0/2 是 CAS 业务结果，映射为最终 401
  语义合理；null/未知码不再伪装成无效凭据"。
- **安全与泄漏复查全部通过**：未发现真实 Redis 故障回退 memory 或伪造成功；Redis 异常日志不再泄漏主机、
  端口或底层消息；运行时 aliyun+memory 绕过已删除；**L3 通过 `@DynamicPropertySource` 强制 `SmsCodeDouble`
  并在 f01 前校验 bean 类型 ⇒ 不存在发送真实短信的路径**；未发现旧配置静默兼容路径或新增凭据/PII 日志。

**唯一新发现（SUGGESTION，非阻塞）与 orchestrator 的处置决定**：
`StateStoreConfigGuard.java:101-104` 与 `ProvidersModeProductionGuard` 都是 `BeanFactoryPostProcessor`，
二者**无序**；若完整应用同时为 production + doubles + aliyun + memory，两个守卫都可拒绝启动，
而**最终显示哪条诊断没有顺序保证**（短信装配测试因职责隔离也无法证明真实应用中谁先报）。
Oracle 判定**安全性不受影响**，并给出可选修法：为两个 guard 实现 `Ordered` 并增加"同时装配"测试。
**orchestrator 决定本轮不为此改动代码 SHA**，理由：①Oracle 已明示不需再发代码重绑定轮次，
任何改动都会使刚获得的绑定失效并制造它明确说不必要的审查循环；②这是**诊断可读性**问题而非安全问题——
两条消息都会导致启动被拒，不存在"绕过"；③本会话此前对同类非阻塞 SUGGESTION 采取过一致处置
（Swagger 轮的两条 SUGGESTION 亦按文档化披露处理，Oracle 当时亦宣告无需重绑定）。
**精确修法已在此登记，交总协调裁定是否纳入后续契约/配置收敛任务**：为两个 `BeanFactoryPostProcessor`
实现 `org.springframework.core.Ordered`（建议让既有的 `ProvidersModeProductionGuard` 优先级更高，
因为"生产环境不得用 doubles"比"真实短信须配 Redis"更根本），并新增一个同时装配两者的上下文测试，
断言最终诊断是 `app.providers.mode=doubles is not allowed`。

**交付限制（Oracle 确认继续作为限制、不需再发代码重绑定轮次）**：
①**L3 仍未执行**——应由根在真实私有 Redis 配置下执行一次作为**部署验收证据**（Oracle 明确：
这不是再次代码验证，也**不阻塞当前整合**）；②`InMemorySessionDouble` 的同构竞态不修，
须持续披露其并发语义不等价、不能用它证明 refresh/logout 竞争安全；③生产 Redis 的
`management.health.redis.enabled` 必须显式开启，且独立实例 / `maxmemory` / `noeviction` / 容量告警
应定为**生产要求**而非建议。
