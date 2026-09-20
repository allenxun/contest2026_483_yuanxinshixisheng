# B — Java 侧真实阿里云 OSS 存储 provider（`app.storage.provider=aliyun`）

> 交付范围：Java `StoragePort` 接入真实阿里云 OSS（私有桶、流式读写），并将
> **服务端访问 endpoint** 与 **客户端公网 endpoint** 拆分为两项；公网签名地址由独立签名器生成。
> **本文档不含任何真实凭据或真实 bucket 名；示例一律为明显假值。**
> 与 Python 侧同 objectKey 格式、同 bucket 语义。

## 1. 配置键与默认值（默认值均写在代码里，未写入 `application.yml`）

| Java 键 | 默认 | aliyun 必填 | 说明 |
|---|---|---|---|
| `app.storage.provider` | `doubles` | — | `doubles`（本地文件系统替身）\| `aliyun`（真实 OSS） |
| `app.storage.oss.region` | `cn-hangzhou` | 否 | 地域（须与 bucket 区域一致；参与 V4 Credential Scope） |
| `app.storage.oss.server-endpoint` | **无默认** | **是** | **服务端访问**地址；所有对象操作（put/get/exists/delete）使用 |
| `app.storage.oss.public-endpoint` | **无默认** | **是** | **客户端公网**地址；仅用于生成签名地址 |
| `app.storage.oss.bucket` | 空 | **是** | 真实桶名；**必须等于** `app.storage.bucket`（见 §3） |
| `app.storage.oss.access-key-id` | 空 | **是** | RAM AccessKeyId |
| `app.storage.oss.access-key-secret` | 空 | **是** | RAM AccessKeySecret |
| `app.storage.oss.security-token` | 空 | 否 | STS 临时凭据 |
| `app.storage.oss.connection-timeout-millis` | `3000` | 否 | <1000 夹到 1000 |
| `app.storage.oss.socket-timeout-millis` | `3000` | 否 | <1000 夹到 1000 |

**启动期校验**（`OssProvidersConfig`，消息只列**键名**、绝不回显取值，endpoint 亦按敏感配置处理）：

1. 缺 `server-endpoint`/`public-endpoint`/`bucket`/`access-key-id`/`access-key-secret` 任一 ⇒ 拒绝启动，
   列出缺失键名；
2. **旧单 endpoint 不再支持**：只配 `app.storage.oss.endpoint` ⇒ 拒绝启动并给出迁移提示
   （点名 `app.storage.oss.server-endpoint` 与 `app.storage.oss.public-endpoint`）。代码**绝不**读取
   旧键、**无 fallback**；两个新键齐备时旧键被完全忽略；
3. `app.storage.oss.bucket` 必须等于 `app.storage.bucket`（消息只说明两个键名不一致，`values omitted`）。
   **不访问网络做校验。**

## 2. 与 Python 侧 env 对照（部署时两侧必须对齐）

| 语义 | Java 键 | Python env（Python 侧维护，以 `dconfig.py` 实际键名为准） | 备注 |
|---|---|---|---|
| provider | `app.storage.provider` = `doubles`\|`aliyun` | `MVP_D_STORAGE_PROVIDER` = `double`\|`aliyun_oss` | **取值名不同**，部署要分别设置 |
| region | `app.storage.oss.region` | `MVP_A_STORAGE_OSS_REGION` | 同语义 |
| **server endpoint** | `app.storage.oss.server-endpoint` | `MVP_A_STORAGE_OSS_SERVER_ENDPOINT` | 对象操作用 |
| **public endpoint** | `app.storage.oss.public-endpoint` | `MVP_A_STORAGE_OSS_PUBLIC_ENDPOINT` | 仅签名用 |
| bucket | `app.storage.oss.bucket` | `MVP_A_STORAGE_OSS_BUCKET` | **两侧与 Java `app.storage.bucket` 三者须同值** |
| AK | `app.storage.oss.access-key-id` | `MVP_A_STORAGE_OSS_ACCESS_KEY_ID` | 同语义 |
| SK | `app.storage.oss.access-key-secret` | `MVP_A_STORAGE_OSS_ACCESS_KEY_SECRET` | 同语义 |
| STS | `app.storage.oss.security-token` | `MVP_A_STORAGE_OSS_SECURITY_TOKEN` | 可选 |
| 元数据桶列 | `app.storage.bucket`（`media_objects.bucket` 写入源） | 适配器配置桶 | Java 侧由启动校验强制一致 |
| objectKey | `<env>/<purpose>/<uuid>` | `f"{environment}/{purpose}/{media_id}"` | 逐字符一致，**本轮未改** |

**旧键已移除**：Java `app.storage.oss.endpoint` / `APP_STORAGE_OSS_ENDPOINT` 不再支持（Python 侧同）。

## 3. bucket 一致性启动校验（关键部署要求）

`media_objects.bucket` 由 A 的 `MediaService` 写成 `app.storage.bucket`（B 不得改），而真实对象写在
`app.storage.oss.bucket`。二者不一致会导致"库里记 A 桶、对象在 B 桶"的静默错位，故
`OssProvidersConfig` 在启动期强制 `app.storage.oss.bucket == app.storage.bucket`，否则拒绝启动。

**部署要求**：真实模式下必须设置
`APP_STORAGE_BUCKET=<桶名>`、`APP_STORAGE_OSS_BUCKET=<同一桶名>`，以及
`APP_STORAGE_OSS_SERVER_ENDPOINT=<服务端地址>` 与 `APP_STORAGE_OSS_PUBLIC_ENDPOINT=<公网地址>`
（Python 侧对应 env 同语义、同桶）。

## 4. 失败分类映射（`OssStorageAdapter` / `StorageFailureKind`）

| 情形 | 分类 | 行为 |
|---|---|---|
| `NoSuchKey` | 非故障 | `getStream`/`get` 返回 `null`（端口语义）、`exists=false`、`delete` 幂等成功 |
| `AccessDenied`/`InvalidAccessKeyId`/`SignatureDoesNotMatch`/`RequestTimeTooSkewed`/参数类 | CONFIGURATION | 503 **不可重试**，消息含类别/OSS 码/RequestId |
| `ClientException`/网络/超时/5xx | DEPENDENCY | 503 **可重试**，消息含异常类名 |
| 其它未知码 | DEPENDENCY | 503 可重试（绝不视为成功） |

两类均**不静默成功、不回退本地文件系统**；`getStream` 除 `NoSuchKey` 外绝不用 `null` 冒充"不存在"。
`put` 元数据写真实 `Content-Type`/`Content-Length` 与 `x-oss-meta-purpose`，不含身份信息。
对象操作使用 **server-endpoint** 客户端；适配器本身**不**生成公开 URL、**不**调用
`generatePresignedUrl`（那由独立签名器负责）。

## 5. 装配、双客户端与签名（本轮新增）

- **两个长期复用的 `OSS` 客户端**（各 `@Bean(destroyMethod="shutdown")`，容器关闭时都 `shutdown()`）：
  - `ossClient`：由 `server-endpoint` 构建 → `OssStorageAdapter` 的所有对象操作；
  - `ossPublicClient`：由 `public-endpoint` 构建 → 仅供 `OssPublicUrlSigner`。
  - **不**使用 `ossClient.setEndpoint(...)` 动态切换（那会影响并发的对象操作；SDK 也没有
    "同一 client 操作走 A、签名走 B"的通用参数）。
- **签名器** `OssPublicUrlSigner`：按最终访问域名（public-endpoint）直接 `generatePresignedUrl`；
  **绝不**对已签名 URL 做 host/scheme 字符串替换。这是**工程正确性约束**：V1 签名字符串
  （VERB/CONTENT-MD5/CONTENT-TYPE/EXPIRES/CanonicalizedOSSHeaders/CanonicalizedResource）**不含 Host**，
  替换 host 在 V1 下技术上常仍能验证；但 V4 把 `host` 列入额外签名头、region 恒参与 Credential Scope，
  且 CNAME/传输加速路由与 SDK 版本默认行为都可能变化 ⇒ 依赖"签名后改 host"**不可靠**。
- **签名版本**：当前**沿用 SDK 默认的 V1**（未调用 `setSignatureVersion`）；两个客户端都设置 `region`。
- **自定义域名**：**未**启用 `setSupportCname(true)`；`public-endpoint` 目前按标准 OSS 域名处理。
- **有效期**：单参 `presign(objectKey)` 用默认 15 分钟；双参 `presign(objectKey, ttl)` 对
  **null/零/负数 TTL 明确抛 `IllegalArgumentException`**（绝不静默回退默认值——有效期是安全相关
  参数，静默替换会让调用方误以为拿到自己请求的授权时长；与 Python 侧 `1..604800` 校验一致），
  最大 **7 天（604800 秒）**，超过同样 ⇒ **明确失败**（不静默截断）。
  若用 STS 临时凭据，URL 实际有效期 = `min(URL TTL, STS token 剩余有效期)`，token 过期即失效。
- **未接入任何 HTTP 面**：预签名 URL 是"持有即可用"的临时授权，会在有效期内把对象暴露在互联网上；
  是否对 APP/云台暴露签名地址属架构决定，**由根裁定**。本轮无控制器/响应/契约变更。

## 6. 装配优先级与生产语义

优先级：**`app.providers.mode=disabled` > `app.storage.provider=aliyun` > 默认 `doubles`**。
`provider=aliyun` 属真实实现，生产（`app.env=production`/`prod`）下允许；新类位于
`cn.yuanxin.mvp.web.storage`、类名不以 `Disabled` 开头 ⇒ `ProductionFailClosedValidator.isDouble()`
不会误判为替身。`ProvidersModeProductionGuard`（生产信号 + `mode=doubles` 早期拒绝）仍生效。

## 7. 日志与脱敏

`AliyunOssProperties.toString()` 对两个 endpoint 只输出 `<configured>`/`<absent>`，绝不回显取值；
AK/SK/STS 一律 `<redacted>`；异常/日志不记 bucket/endpoint/完整 key。`OssLiveSmoke` 的 Redactor
同时净化 server/public 两个 endpoint 及其 host。

## 8. 测试覆盖与未覆盖（如实）

- 已覆盖（本地 HTTP stub / Mockito / 本地签名计算，假凭据）：两新键齐备正常装配且两个 OSS 客户端与
  签名器均装配；缺 `server-endpoint`/`public-endpoint` 各自失败且只报键名；只配旧键失败并含迁移提示；
  旧键在新键齐备时被忽略；bucket 一致性；生产 fail-closed；两个 `OSS` `@Bean` 声明
  `destroyMethod=shutdown`；对象操作经 server-endpoint 的 wire 行为（stub 绑定在 server-endpoint，
  public-endpoint 为另一主机）；签名 URL host:port 等于 public-endpoint 而非 server-endpoint；
  签名调用只在公网客户端且返回 URL 逐字透传；TTL 超上限明确失败；PUT/GET/exists/delete 语义与失败分类。
- **未覆盖（未验证项）**：真实 OSS 的签名校验、bucket 权限/策略、跨区域/CNAME/传输加速选址、
  真实 V4 行为、真实 TLS、真实限流/计费。`server-endpoint`/`public-endpoint` 的取值正确性只能在根
  的私有配置下验证。
- SDK = `com.aliyun.oss:aliyun-sdk-oss:3.18.5`（V1）；官方对 Spring Boot 3.5 / Java 21 无专项兼容声明。
