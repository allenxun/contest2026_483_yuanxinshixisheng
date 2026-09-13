# B — 真实阿里云短信接入（`app.sms.provider=aliyun`）

> 交付范围：短信（SMS）真实提供方接入 + 一次性安全 smoke 入口。**OSS 与人脸本轮不做。**
> 本文档不包含任何真实凭据、签名、模板码或完整手机号；示例一律为明显假值。

## 1. 配置键与默认值（默认值均写在代码里，未写入 `application.yml`）

| 键 | 默认 | 必填（aliyun） | 说明 |
|---|---|---|---|
| `app.sms.provider` | `doubles` | — | `doubles`（隔离替身，固定码 `123456`）\| `aliyun`（真实） |
| `app.sms.aliyun.endpoint` | `dysmsapi.aliyuncs.com` | 否 | 短信服务 endpoint |
| `app.sms.aliyun.region-id` | `cn-hangzhou` | 否 | 地域 |
| `app.sms.aliyun.access-key-id` | 空 | **是** | RAM AccessKeyId |
| `app.sms.aliyun.access-key-secret` | 空 | **是** | RAM AccessKeySecret |
| `app.sms.aliyun.security-token` | 空 | 否 | STS 临时凭据时提供 |
| `app.sms.aliyun.sign-name` | 空 | **是** | 短信签名 |
| `app.sms.aliyun.template-code` | 空 | **是** | 模板 Code |
| `app.sms.aliyun.template-param-name` | `code` | 否 | 模板变量名；`TemplateParam` 为 `{"<name>":"<code>"}` |
| `app.sms.aliyun.connect-timeout-millis` | `3000` | 否 | 连接超时；<1000 会被夹到 `1000` |
| `app.sms.aliyun.read-timeout-millis` | `3000` | 否 | 读取超时；<1000 会被夹到 `1000` |
| `app.sms.risk.challenge-ttl-seconds` | `300` | 否 | challenge 有效期 |
| `app.sms.risk.max-verify-attempts` | `5` | 否 | 单 challenge 最大校验尝试次数 |
| `app.sms.risk.max-per-minute` | `1` | 否 | 同手机号/UTC+8 自然分钟上限 |
| `app.sms.risk.max-per-hour` | `5` | 否 | 同手机号/UTC+8 自然小时上限 |
| `app.sms.risk.max-per-day` | `10` | 否 | 同手机号/UTC+8 自然日上限 |
| `app.sms.risk.retry-after-seconds` | `60` | 否 | `data.retryAfter` 与 `Retry-After` 建议等待秒数 |
| `app.integration-test.sms.phone` | 空 | — | **为空则禁止任何真实短信测试** |
| `app.sms.live-smoke` | `false` | — | 真实 smoke 的显式 opt-in |

**启动期校验**：`app.sms.provider=aliyun` 时，若 `access-key-id`/`access-key-secret`/
`sign-name`/`template-code` 任一为空 ⇒ **拒绝启动**，消息只列**缺失键名**，绝不回显任何值；
**不通过试发短信校验**（计费接口）。

## 2. 装配优先级与组合矩阵

优先级：**`app.providers.mode=disabled` > `app.sms.provider=aliyun` > 默认 `doubles`**。

| `app.providers.mode` | `app.sms.provider` | 装配的 `SmsCodeProvider` |
|---|---|---|
| `doubles`（缺省） | 缺省/`doubles` | `SmsCodeDouble`（固定码 `123456`） |
| `doubles` | `aliyun` | `AliyunSmsCodeProvider`（真实） |
| `disabled` | `aliyun` | A 的 disabled 占位（运行时 503，**真实适配器不装配**） |
| `disabled` | 缺省/`doubles` | A 的 disabled 占位（503） |
| 生产信号 + `doubles` | 任意 | 被 `ProvidersModeProductionGuard` **早期拒绝**（未被本轮绕过） |

生产下 `app.sms.provider=aliyun` 视为真实实现：新类位于 `cn.yuanxin.mvp.web.sms`、类名不以
`Disabled` 开头 ⇒ `ProductionFailClosedValidator.isDouble()` 不会误判为替身。

## 3. 风控 / 安全要点

- 验证码：`SecureRandom` 生成 **6 位随机数字**，并主动避开通用测试码 `123456`（`aliyun` 模式下
  `123456` 绝不是有效码）。
- 一次性核销：正确校验后立即移除 challenge，重放失败；不存在/过期/超尝试次数一律
  `Optional.empty()`（f02 → 401 `AUTH_REQUIRED`，与 doubles 语义一致）。
- 节流：三窗口本地预检（默认 1 分钟 1 条 / 1 小时 5 条 / 1 天 10 条，**UTC+8 自然窗口**）。
  这是调用计费接口前的预检；平台仍可能返回 `isv.BUSINESS_LIMIT_CONTROL` 等流控（映射 429，
  带 `Retry-After`）。
- **失败不回退**：仅当阿里云响应体业务 `Code` 严格等于 `"OK"` 才创建 challenge 并返回。
  失败映射：节流类 → 429 `RATE_LIMITED`；配置类/依赖类 → 503 `DEPENDENCY_UNAVAILABLE`
  （配置类消息注明不可重试）。
- 脱敏：日志只记业务 `Code`/`RequestId`/掩码手机号（如 `+861****0000`）；绝不记验证码、
  AK/SK、完整手机号。
- **局限（如实披露）**：challenge 与节流历史为**进程内内存** ⇒ 应用重启即失效、多实例不共享。

## 4. 一次性真实 smoke（`AliyunSmsLiveSmokeIT`，默认跳过；**仅根可执行**）

**跳过条件（必须同时满足，任一不满足即 abort 并说明原因）：**
1. `app.sms.provider=aliyun`；
2. `app.integration-test.sms.phone` 非空；
3. `app.sms.live-smoke=true`（显式 opt-in）。

**断言**：只发送 **一条**，断言阿里云业务 `Code == "OK"`（**仅表示平台受理，不代表已送达**；
**不得**以 HTTP 200 判定）。输出仅 `Code/Message/RequestId/BizId` 与掩码手机号。`Code != OK`
时失败并打印 `Code`+`Message`+`RequestId`（不含凭据）。

**根的执行方式（二选一）：**

- 通过私有 `application-local.properties`（属性名与 Spring 完全一致）：
  ```
  mvn -f backend/web-java/pom.xml -B test \
    -Dtest=AliyunSmsLiveSmokeIT -DfailIfNoTests=false \
    -Dapp.sms.provider=aliyun -Dapp.sms.live-smoke=true \
    -Dapp.integration-test.sms.phone='<root 私有手机号>' \
    -Dapp.sms.smoke.config='/abs/path/to/application-local.properties'
  ```
  （`app.sms.smoke.config` 指向的 properties 文件提供其余 `app.sms.aliyun.*` 键；
  smoke 读取属性名而非 Spring 上下文。）
- 或直接以 `-D`/环境变量逐个传入（见 `run-sms-smoke.sh`）。

`Code != OK` 解读：`isv.BUSINESS_LIMIT_CONTROL`/`isv.MOBILE_COUNT_OVER_LIMIT` 等为流控（改日/降频）；
`isv.SMS_SIGNATURE_ILLEGAL`/`isv.SMS_TEMPLATE_ILLEGAL`/`isv.INVALID_JSON_PARAM`/
`isv.TEMPLATE_MISSING_PARAMETERS`/`isp.RAM_PERMISSION_DENY` 为签名/模板/权限配置问题（不可重试）；
`isv.AMOUNT_NOT_ENOUGH`/`isv.OUT_OF_SERVICE`/`isp.SYSTEM_ERROR` 为依赖问题（可稍后重试）。

> **B 侧不得执行该 smoke、不得读取根私有配置。** 运行脚本
> `.coordination/B-work/sms-aliyun/run-sms-smoke.sh` 为运行时产物（不入仓）。

## 5. 未验证项（如实列出）

1. **真实凭据下的实际发送未由 B 验证**（B 无测试手机号、不得发真实短信）；由根按 §4 执行。
2. 阿里云官方对 **Spring Boot 3.5 / Java 21 无专项兼容声明**（既未证明有问题、也未证明已验证）；
   SDK 为 `com.aliyun:dysmsapi20170525:4.6.0`（V2.0，官方推荐线）。
3. 内存 challenge 的**重启失效 / 多实例不共享**局限（见 §3）。
4. 本地三窗口节流仅为**预检**，与平台流控独立；平台拒绝已映射为 429，但阈值可能不完全一致。

## 6. 依赖

`backend/web-java/pom.xml` 新增 `com.aliyun:dysmsapi20170525:4.6.0`（传递 `tea-openapi`/
`tea-util`/`tea`/`endpoint-util`/`openapiutil`）。OSS 本轮不引入。
