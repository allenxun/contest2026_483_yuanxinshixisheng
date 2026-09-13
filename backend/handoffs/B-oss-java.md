# B — Java 侧真实阿里云 OSS 存储 provider（`app.storage.provider=aliyun`）

> 交付范围：Java `StoragePort` 接入真实阿里云 OSS（私有桶、流式读写、无公开 URL）。
> **本文档不含任何真实凭据或真实 bucket 名；示例一律为明显假值。**
> 与 Python 侧（已提交 `229476c`）同 objectKey 格式、同 bucket 语义。

## 1. 配置键与默认值（默认值均写在代码里，未写入 `application.yml`）

| Java 键 | 默认 | aliyun 必填 | 说明 |
|---|---|---|---|
| `app.storage.provider` | `doubles` | — | `doubles`（本地文件系统替身）\| `aliyun`（真实 OSS） |
| `app.storage.oss.region` | `cn-hangzhou` | 否 | 地域（须与 bucket 区域一致） |
| `app.storage.oss.endpoint` | `https://oss-cn-hangzhou.aliyuncs.com` | 否 | 公网/内网 endpoint（内网形如 `oss-cn-hangzhou-internal.aliyuncs.com`） |
| `app.storage.oss.bucket` | 空 | **是** | 真实桶名；**必须等于** `app.storage.bucket`（见 §3） |
| `app.storage.oss.access-key-id` | 空 | **是** | RAM AccessKeyId |
| `app.storage.oss.access-key-secret` | 空 | **是** | RAM AccessKeySecret |
| `app.storage.oss.security-token` | 空 | 否 | STS 临时凭据 |
| `app.storage.oss.connection-timeout-millis` | `3000` | 否 | <1000 夹到 1000 |
| `app.storage.oss.socket-timeout-millis` | `3000` | 否 | <1000 夹到 1000 |

**启动期校验**：`provider=aliyun` 时缺 `bucket`/`access-key-id`/`access-key-secret` 任一 ⇒
拒绝启动，消息只列**缺失键名**（绝不回显值）；且 `app.storage.oss.bucket` 必须等于
`app.storage.bucket`（消息可输出 bucket 名，不输出 AK/SK/token）。**不访问网络做校验。**

## 2. 与 Python 侧 env 对照（部署时两侧必须对齐）

| 语义 | Java 键 | Python env | 备注 |
|---|---|---|---|
| provider | `app.storage.provider` = `doubles`\|`aliyun` | `MVP_D_STORAGE_PROVIDER` = `double`\|`aliyun_oss` | **取值名不同**，部署要分别设置 |
| region | `app.storage.oss.region` | `MVP_A_STORAGE_OSS_REGION` | 同语义 |
| endpoint | `app.storage.oss.endpoint` | `MVP_A_STORAGE_OSS_ENDPOINT` | 同语义 |
| bucket | `app.storage.oss.bucket` | `MVP_A_STORAGE_OSS_BUCKET` | **两侧与 Java `app.storage.bucket` 三者须同值** |
| AK | `app.storage.oss.access-key-id` | `MVP_A_STORAGE_OSS_ACCESS_KEY_ID` | 同语义 |
| SK | `app.storage.oss.access-key-secret` | `MVP_A_STORAGE_OSS_ACCESS_KEY_SECRET` | 同语义 |
| STS | `app.storage.oss.security-token` | `MVP_A_STORAGE_OSS_SECURITY_TOKEN` | 可选 |
| 元数据桶列 | `app.storage.bucket`（`media_objects.bucket` 写入源） | 适配器配置桶 | Java 侧由启动校验强制一致 |
| objectKey | `<env>/<purpose>/<uuid>`（`MediaService:66`） | `f"{environment}/{purpose}/{media_id}"`（`build_object_key`） | 逐字符一致，**本轮未改** |

## 3. bucket 一致性启动校验（关键部署要求）

`media_objects.bucket` 由 A 的 `MediaService` 写成 `app.storage.bucket`（B 不得改），而真实对象
写在 `app.storage.oss.bucket`。二者不一致会导致"库里记 A 桶、对象在 B 桶"的静默错位，故
`OssProvidersConfig` 在启动期强制 `app.storage.oss.bucket == app.storage.bucket`，否则拒绝启动。

**部署要求**：真实模式下必须设置
`APP_STORAGE_BUCKET=<桶名>` **且** `APP_STORAGE_OSS_BUCKET=<同一桶名>`
（Python 侧 `MVP_A_STORAGE_OSS_BUCKET` 同值）；`app.storage.oss.bucket` 不得留在默认/空。

## 4. 失败分类映射（`OssStorageAdapter` / `StorageFailureKind`）

| 情形 | 分类 | 行为 |
|---|---|---|
| `NoSuchKey` | 非故障 | `getStream`/`get` 返回 `null`（端口语义）、`exists=false`、`delete` 幂等成功 |
| `AccessDenied`/`InvalidAccessKeyId`/`SignatureDoesNotMatch`/`RequestTimeTooSkewed`/参数类 | CONFIGURATION | 503 **不可重试**（`ApiException.isRetryable()==false`），消息含类别/OSS 码/RequestId |
| `ClientException`/网络/超时/5xx | DEPENDENCY | 503 **可重试**（`isRetryable()==true`），消息含异常类名 |
| 其它未知码 | DEPENDENCY | 503 可重试（绝不视为成功） |

两类均**不静默成功、不回退本地文件系统**；`getStream` 除 `NoSuchKey` 外绝不用 `null` 冒充"不存在"。
`put` 元数据写真实 `Content-Type`/`Content-Length` 与 `x-oss-meta-purpose`（值取自 objectKey 的
purpose 段），不含身份信息。**不调用 `generatePresignedUrl`，无任何公开 URL。**

## 5. 装配优先级与生产语义

优先级：**`app.providers.mode=disabled` > `app.storage.provider=aliyun` > 默认 `doubles`**。
`provider=aliyun` 属真实实现，生产（`app.env=production`/`prod`）下允许；新类位于
`cn.yuanxin.mvp.web.storage`、类名不以 `Disabled` 开头 ⇒ `ProductionFailClosedValidator.isDouble()`
不会误判为替身。`ProvidersModeProductionGuard`（生产信号 + `mode=doubles` 早期拒绝）仍生效，未被绕过。
`OSS` 客户端为单例 bean，容器关闭时 `shutdown()`（`@Bean(destroyMethod="shutdown")`），不每请求新建。

## 6. 测试覆盖与未覆盖（如实）

- 已覆盖（本地 HTTP stub，假凭据）：PUT 的路径/Host 选址、`Content-Type`/`Content-Length`/
  `x-oss-meta-purpose`/`Authorization` 头存在；GET 往返字节一致；`exists`；`delete` 幂等；
  `NoSuchKey(404)` → 不存在语义；`AccessDenied(403)` → 配置错误（不可重试）；5xx → 依赖故障
  （可重试）；不可达 endpoint → 依赖故障；日志/异常消息不含 AK/SK（Logback `ListAppender`）。
- **未覆盖（未验证项）**：真实 OSS 的签名校验、bucket 权限/策略、跨区域 endpoint 选址、
  virtual-host 选址形态（stub 为 IP endpoint 的路径式）、真实 TLS、真实限流/计费行为。
- 阿里云官方对 **Spring Boot 3.5 / Java 21 无专项兼容声明**；SDK = `com.aliyun.oss:aliyun-sdk-oss:3.18.5`（V1）。
- Java 默认 `mvp-a-media` 与 Python double 默认 `mvp-media` 的不一致**仅存在于 double 模式**；
  真实模式下由 §3 启动校验强制两侧一致。
