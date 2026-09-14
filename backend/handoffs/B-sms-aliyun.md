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

## 8. UTF-8 编码要求（2026-09-14 真实 smoke 失败根因与修复）

**症状**：根用同一份阿里云短信配置执行真实 smoke，官方 SDK 返回 `isv.SMS_SIGNATURE_ILLEGAL`（签名不合法）。同一配置在其它代码中可用。

**根因**：`AliyunSmsLiveSmokeIT.loadFileProperties()` 曾用 `Properties.load(InputStream)`。按 `java.util.Properties` 规范，该方法以 **ISO-8859-1** 解码输入流，因此 UTF-8 的中文 `app.sms.aliyun.sign-name`（以及中文模板参数名）会被解成乱码；`AliyunSmsSendGateway:72` 又把它**原样**交给 SDK 的 `.setSignName(...)`（网关与 `AliyunSmsProperties:43` 都不做任何字符集处理），阿里云据此判定签名非法。**这不是阿里云侧配置问题，也不是 SDK 问题。**

**修复**：改为 `new InputStreamReader(new FileInputStream(path), StandardCharsets.UTF_8)` + `Properties.load(Reader)`，并把读取抽为包级可见的纯函数缝 `AliyunSmsLiveSmokeIT.readPropertiesFile(String)`（便于回归测试，且不触碰静态缓存、不需要 opt-in）。unicode 转义序列与反斜杠行连接语义不变。回归守卫＝`AliyunSmsSmokeConfigEncodingTest`（3 项），含**判别力证明**：对同样的文件字节，旧 ISO-8859-1 读法得到的值与期望签名不相等 ⇒ 该断言不是恒真。

**生产侧同样需要注意（配置源层，B 的生产代码无缺陷）**：Spring Boot 3.5.16 的
`org.springframework.boot.env.OriginTrackedPropertiesLoader$CharacterReader` 经字节码核实为
`new InputStreamReader(in, StandardCharsets.ISO_8859_1)` ⇒ **`.properties` 配置源里的中文同样会乱码**。
因此真实运行时若把中文 `sign-name` 放进 `application-local.properties`，经 `@ConfigurationProperties`
绑定后也会得到乱码并触发同样的 `isv.SMS_SIGNATURE_ILLEGAL`。三种安全方式（任选其一）：
1. **放进 YAML**（`application.yml` / `application-local.yml`）——Spring 按 UTF-8 读取 YAML；
2. 在 `.properties` 中使用 **unicode 转义序列**（反斜杠 u + 四位十六进制）写中文值；
3. 用**环境变量或系统属性**注入（`APP_SMS_ALIYUN_SIGN_NAME` / `-Dapp.sms.aliyun.sign-name=...`），
   两者均为 UTF-8 安全；smoke 的 `config()` 解析顺序本就是 系统属性 → 环境变量 → properties 文件。

`application.yml`（UTF-8）中的 `app.sms.*` 键不受影响；本轮 `application.yml` 未改动。

**边界**：本项修复**未改动任何生产代码**（`backend/web-java/src/main/**` diff 为 0 文件），仅改
smoke 测试工具与其回归测试；三重 opt-in（`app.sms.provider=aliyun` + 非空
`app.integration-test.sms.phone` + `app.sms.live-smoke=true`）与 `SmsMasking` 脱敏规则均未改动；
未读取根的私有 `application-local.properties`、未使用任何真实凭据或手机号、未发送任何真实短信。
