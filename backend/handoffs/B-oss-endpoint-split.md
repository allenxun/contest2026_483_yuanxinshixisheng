# B OSS endpoint 拆分（服务端访问 / 客户端公网）——设计与迁移说明

状态：实施中（Java 与 Python 两道并行）。本文件先记录**已裁定的字段名、不兼容语义与官方取证结论**；
依赖实施道内部命名的部分（类名/方法名/测试数字/验证证据）在 §7 待填。

## 1. 变更动机
单一 `endpoint` 无法同时满足两种访问路径：
- **服务端对象操作**（Java Web 与 Python Worker 的 put/get/exists/delete）应走**服务端访问 endpoint**
  （可能是内网 `oss-<region>-internal.aliyuncs.com` 或传输加速域名——同地域阿里云内网访问**免流量费**）；
- **给 APP/云台的签名地址**必须针对**客户端公网 endpoint** 生成，客户端才能访问。
官方明确：同一 bucket 的对象**可通过任一 endpoint 访问**，"无论通过内网 Endpoint 还是外网 Endpoint
上传，OSS 中的同一文件均可通过任一 Endpoint 访问"；内网 endpoint 仅限**同地域阿里云产品**使用。

## 2. 最终字段名（orchestrator 裁定，两侧一一对应）
| 语义 | Java 配置键 | Java record 组件 | Java 环境变量（relaxed binding） | Python 环境变量 | Python 构造参数 |
|---|---|---|---|---|---|
| 服务端访问（对象操作） | `app.storage.oss.server-endpoint` | `serverEndpoint` | `APP_STORAGE_OSS_SERVER_ENDPOINT` | `MVP_A_STORAGE_OSS_SERVER_ENDPOINT` | `server_endpoint` |
| 客户端公网（签名地址） | `app.storage.oss.public-endpoint` | `publicEndpoint` | `APP_STORAGE_OSS_PUBLIC_ENDPOINT` | `MVP_A_STORAGE_OSS_PUBLIC_ENDPOINT` | `public_endpoint` |

保持不变：`app.storage.oss.region` / `MVP_A_STORAGE_OSS_REGION`、`bucket`、`access-key-id`、
`access-key-secret`、`security-token`（可选 STS）。

**已删除**：`app.storage.oss.endpoint`、`MVP_A_STORAGE_OSS_ENDPOINT`、Java 的 `DEFAULT_ENDPOINT`
常量与 Python 的 `DEFAULT_OSS_ENDPOINT` 常量、以及 `AliyunOssStorage.__init__` 的
`endpoint: str = DEFAULT_OSS_ENDPOINT` 默认值（改为两个**必填**无默认值参数）。

## 3. 不兼容与失败语义（无 fallback）
1. 代码**绝不**读取旧的单 endpoint 键/变量；
2. 两个新键**都必填、都无默认值**；缺任一项 ⇒ **明确失败**并列出缺失的**键名**
   （Java：启动失败；Python：`ProviderConfigError`）；
3. 只配了旧键时同样失败，并给出**迁移提示**（点名两个新键）；
4. 所有失败消息与日志**只含键名，绝不回显任何取值**（endpoint 按敏感配置处理，与既有脱敏一致）；
5. `double`/替身模式完全不需要任何 OSS 配置（dry-run 仍可在无凭据环境跑通）。

迁移方式（由根执行；OpenCode **不读取也不编辑**根的私有 YAML）：把原
`app.storage.oss.endpoint` 一行替换为 `server-endpoint` 与 `public-endpoint` 两行即可。

## 4. 为什么"签名后替换 host"被禁止（官方取证结论）
**结论：双 client / 双 bucket（分别绑定 server 与 public endpoint，用 public 那个签名）是官方对齐的
正确实现；"用 server 客户端签名后字符串替换 host"不可依赖。**

- **V1 签名**的待签字符串为
  `VERB\nCONTENT-MD5\nCONTENT-TYPE\nEXPIRES\nCanonicalizedOSSHeaders\nCanonicalizedResource`，
  **不含 Host**；canonical resource 只是 `/<bucket>/<key>`。因此在 bucket/key/签名参数不变、
  且新 host 确实路由到同一 bucket 时，**单纯替换 host 在 V1 下技术上常仍能通过校验**。
  （官方文档甚至写过"通过内网 Endpoint 上传文件后，生成访问 URL 时只需将域名部分替换为对应地域的
  公网 Endpoint"——但那是**访问说明**，不是对"在应用里改写已签名 URL"的背书。）
- **V4 签名**的 Credential Scope 为 `<date>/<region>/oss/aliyun_v4_request`，**region 必然参与签名**
  （跨 region 不可复用）；且 `host` 可作为**额外签名头**参与签名，官方原文："添加签名 host，
  并禁止修改请求的域名"⇒ 此时替换 host **必然失效**。
- 即使当前 SDK 默认未把 host 列入 V4 额外签名头，也**不应依赖**这一实现细节：自定义域名/CNAME 配置差异、
  传输加速等 endpoint 的路由差异、以及 **SDK 升级后默认签名头行为变化**都会让"替换 host"悄然失效。
- 官方**没有**提供"同一 client 数据操作走 endpoint A、签名走 endpoint B"的通用参数。Java 侧虽有
  `ossClient.setEndpoint(String)`，但它改变的是该 client 的服务 endpoint，**会并发影响对象操作**，
  故禁止用它在共享 client 上动态切换；正确做法是两个长期复用的 client。

因此本项目的表述必须准确：**这是工程正确性约束（按客户端最终访问的域名直接签名），
而不是"V1 算法必然失败"**。任何将来把它"优化"回 host 替换的改动都应被拒绝。

## 5. 实现要求
- **对象操作**（put/get/getStream/exists/delete）只走 **server-endpoint** 客户端；
- **签名地址**只由 **public-endpoint** 客户端生成；**绝不**对已签名 URL 做 host/scheme/路径编码的
  字符串替换（Python 侧 `slash_safe=True` 会影响 canonical URI，生成后同样不得再改路径编码）；
- **两个客户端都必须被正确关闭**（Java：各自 `@Bean(destroyMethod="shutdown")` 或统一持有者管理；
  Python：两个 `oss2.Bucket` 共享同一 auth 对象即可）；
- **签名版本必须如实标注**：`oss2.Auth` 是 **V1**；V4 需 `auth_version=oss2.AUTH_VERSION_4` 且
  **必须提供 region**（官方源码在 V4 缺 region 时抛
  `The region should not be None in signature version 4.`）。Java 侧 V4 需
  `ClientBuilderConfiguration.setSignatureVersion(SignVersion.V4)` + `.region(...)`。
  不得声称 V4 而实际用 V1；
- 自定义域名场景官方分别用 Java `setSupportCname(true)` / Python `is_cname=True`；若未实现须在文档注明
  public-endpoint 目前按标准 OSS 域名处理。

## 6. 运维与安全事实（官方，供根配置与后续接入决策）
- **有效期上限**：V4 预签名 URL 最大 **604800 秒（7 天）**；V1 可更长但官方已不推荐。
- **STS 交互**：用 STS 临时凭据签名的 URL，**实际有效期 = min(URL TTL, STS token 剩余有效期)**，
  **token 过期后 URL 立即失效**。若对 TTL 做校验，超限应**明确失败**而非静默截断。
- **权限模型**：预签名 URL **不要求**把 bucket 或对象改为公开读（默认私有即可）；但生成签名的身份
  必须拥有对应操作权限。
- **风险提示（官方原文）**："使用在 URL 中签名的方式，会将授权的数据在过期时间内曝露在互联网上，
  请预先评估使用风险。"⇒ 预签名 URL 是**持有即可用**的临时授权，与本项目既有的
  "私有桶 + 后端鉴权读取 + `BusinessMediaAccessPolicy` 逐请求判定"模型是**不同的授权面**。
- **方法限制**：URL 内签名支持 **GET / PUT**；`multipart/form-data` 表单上传须用 OSS POST Policy，
  不能用普通 `sign_url`。
- **`response-*` 覆盖参数**（如 `response-content-disposition`）**参与签名**，生成后再增改已签名的
  查询参数会使签名失效。

## 7. 实施结果与中央验证（orchestrator 亲自执行）
### 7.1 Java（`web/storage/**`；生产文件 3 改 1 新）
- `AliyunOssProperties`：`endpoint` 组件与 `DEFAULT_ENDPOINT` 常量**已删除**，改为 `serverEndpoint` /
  `publicEndpoint`（`:29-30`），两者均无默认值；`missingRequiredKeys()`（`:59-73`）顺序为
  `server-endpoint, public-endpoint, bucket, access-key-id, access-key-secret`；
  `toString()`（`:81-90`）对两个 endpoint 只输出 `<configured>`/`<absent>`、AK/SK/STS 为 `<redacted>`。
- `OssProvidersConfig`：新增 `LEGACY_ENDPOINT_KEY/ENV`（`:60-61`）——**仅用
  `environment.containsProperty(...)` 检测存在性、绝不读取其值**（`:113-117`）；
  `validateEndpointConfig`（`:97-111`）在 endpoint 缺失且检测到旧键时抛迁移消息
  `legacy app.storage.oss.endpoint is no longer supported; configure app.storage.oss.server-endpoint
  and app.storage.oss.public-endpoint (values are never logged)`；两个客户端
  `ossClient`（server，`:65-74`）与 `ossPublicClient`（public，`:78-81`）**都是
  `@Bean(destroyMethod="shutdown")`**；`ossStorageAdapter` 用 `@Qualifier("ossClient")`（`:85-88`），
  新增 `ossPublicUrlSigner`（`:90-93`）。数据面构造只把 `.endpoint(properties.endpoint())`
  参数化为 `buildClient(properties, endpoint)`，**与根在 `ede19b5` 验证过的状态一致**。
- 新增 `OssPublicUrlSigner`：`presign(objectKey)` 用 `DEFAULT_EXPIRY=15min`；
  `presign(objectKey, Duration)` 对 **null/零/负数 TTL 明确抛 `IllegalArgumentException`**
  （orchestrator 修正：原实现静默回退默认值，会让调用方误以为拿到自己请求的授权时长；
  现与 Python 侧 `1..604800` 校验一致），超 `MAX_EXPIRY=7天` 同样明确失败；
  `:74` 直接 `return publicClient.generatePresignedUrl(bucket, objectKey, expiration)`，
  **原样透传、零 host/scheme/路径后处理**（`grep` 证明 main/storage 内无任何 host 替换）。
- 签名版本：**沿用 SDK 默认 V1**（未调用 `setSignatureVersion`），两个客户端都设置 `region`。
- smoke 三件套同步：`LiveConfig` 改双 endpoint、`loadYamlConfig` 读两个新键（仍显式 UTF-8 Reader、
  仍支持嵌套与扁平点号）、三重门缺失列表含两新键、**`public-url-probe` 改打 public endpoint**
  （`OssLiveSmoke.java:445`）、`Redactor` 同时纳入两个 endpoint 及其 host。`--phase sign-probe`
  **未实现**（签名器已由装配级测试覆盖；接入纯 harness 需再穿透一个客户端工厂，列为可选增强）。

### 7.2 Python（`media/storage.py`、`dshared/dconfig.py`、`dshared/providers.py`）
- `storage.py`：删除 `DEFAULT_OSS_ENDPOINT` / `OSS_ENDPOINT_ENV`，新增
  `OSS_SERVER_ENDPOINT_ENV` / `OSS_PUBLIC_ENDPOINT_ENV`（`:45-46`）与
  `MAX_SIGN_EXPIRES_SECONDS = 604800`（`:53`）；`AliyunOssStorage.__init__` 的
  `server_endpoint` / `public_endpoint` 为**必填无默认值**关键字参数，缺字段抛
  `StorageConfigError` 且**只报字段名**；`_bucket`=server、`_public_bucket`=public（`:379/:382`），
  复用同一 auth、均传 `region`；`sign_public_url(object_key, expires_seconds)`（`:389-412`）
  校验 `1..604800`（越界抛 `StorageConfigError`，**不静默截断**）后用 public bucket
  `sign_url("GET", key, expires, slash_safe=True)`。
- **签名版本随凭据类型（orchestrator 裁定，见 §9.1）**：长期 AK/SK → 经典 `oss2.Auth`（**V1**）；
  STS → `StsAuth(auth_version=AUTH_VERSION_4)`（**V4**）。
- `dconfig.py`：字段拆为 `oss_server_endpoint` / `oss_public_endpoint`（均无默认），
  文档表（`:11-14`）同步为两个新键并标注"未设（aliyun_oss 必填）"与 Java 对齐关系。
- `providers.py`：`_require_oss_config` 增两项校验 + 迁移提示（消息形如
  `aliyun_oss storage provider requires non-empty endpoint config: MVP_A_STORAGE_OSS_SERVER_ENDPOINT,
  MVP_A_STORAGE_OSS_PUBLIC_ENDPOINT (endpoint config was split into server/public endpoints; migrate
  the legacy single-endpoint setting ...)`，**只含键名、不回显任何取值**）；`build_storage_port`
  传两个新参数。**orchestrator 独立自证**：`git diff` 中 `providers.py` 涉及
  `PlanPort|build_plan_port|build_face_port|build_skin_port|FacePort|SkinPort` 的行数 = **0**，
  diff 只落在 import 段、`_require_oss_config` 与 `build_storage_port` 的构造调用。

### 7.3 中央验证数字（全部 orchestrator 亲跑）
- Java：`test-compile` rc=0；定向 storage 41/0/0（Lane 报）+ orchestrator 复跑
  `OssPublicUrlSignerTest,OssProvidersConfigTest` 16/0/0；**全量 `mvn -B test` = 617 run /
  0 failures / 0 errors，BUILD SUCCESS**（账目：基线 606 + Lane J 新增 10 = 616，
  + orchestrator 新增 `nonPositiveTtlIsRejectedNotSilentlyDefaulted` 1 = **617**）。
- Python：`compileall` rc=0；**全量 pytest = 405 passed / 0 failed / 0 errors**
  （账目：基线 385 + Lane P 新增 18 = 403，+ orchestrator 新增
  `test_auth_selection_preserves_the_verified_data_plane` 与
  `test_sign_public_url_uses_v4_when_sts_credentials` 2 = **405**）；`55432` 引用 0；
  `--check` rc=0；ephemeral 库已清理。
- **驱动级跨语言 dry-run（两侧都已切到新键）= `RESULT=PASS failures=0 cleanup=confirmed`**，
  五阶段全 ok、泄漏扫描 `LTAI`/完整 UUID 键/`example.com` 均 0、无残留 root。
- **离线签名实证（orchestrator 亲自用假凭据跑，不联网）**：AK/SK 路径 →
  host=`fake-bucket-do-not-use.oss-fake-public.example.com`、查询参数恰为
  `OSSAccessKeyId`/`Expires`/`Signature`、**无** `x-oss-signature-version`、path 保留 `/`；
  STS 路径 → `x-oss-signature-version=OSS4-HMAC-SHA256`、scope 含 region、含 token 参数；
  `_bucket is not _public_bucket` 且两者 endpoint 分别为 server / public。
- 作用域：`backend/contracts/**`、`backend/acceptance/**`、`media/**`、`mediapolicy/**`、`auth/**`、
  `application.yml`、`pom.xml`、依赖清单 **diff 均为 0**；`OssPublicUrlSigner` 在 `web/storage`
  之外**零引用**、`sign_public_url` **无任何调用方**（仅测试）⇒ 未接入任何 HTTP 面/handler 输出。

## 8. 本轮明确不做（边界）
- **不把签名地址接入任何 HTTP 响应、控制器、handler 输出或任务 payload**：是否对 APP/云台暴露
  签名地址属**架构决定**（它引入一个与既有"后端鉴权读取"并存的授权面），由根另行裁定；
- 不改任何 API 契约（`backend/contracts/**`）、不改 `application.yml`（它本无 `app.storage.oss.*` 键）、
  不改 `pom.xml`、不新增任何依赖（worker venv 刻意保持无 pyyaml）；
- 不动 D 的 `PlanPort`；不动 A 的 `media/**`/`mediapolicy/**`/`auth/**`；
- 不读取、不编辑根的私有 YAML；不使用任何真实凭据或真实桶名；不联网真实 OSS。

## 9. orchestrator 的两处修正与裁定（如实记录）
### 9.1 恢复 Python 数据面的既有签名版本（V1），不把已验证路径改成未验证状态
实施道把长期 AK/SK 的 auth 从经典 `oss2.Auth`（V1）改成了 `oss2.ProviderAuthV4`（V4），
注释写"统一 V4 签名"。orchestrator 读码后**推翻该决定**并恢复 V1，理由：
1. 根已在 `ede19b5` 上用**真实凭据**验证过 V1 数据面（Python put/get/exists/delete 全部成功、
   跨语言逐字节一致）；改成 V4 会使这条**已验证路径**变为未验证状态。
2. V4 把 `region` 纳入 Credential Scope（`<date>/<region>/oss/aliyun_v4_request`）。
   `MVP_A_STORAGE_OSS_REGION` 默认 `cn-hangzhou`，若根的桶不在该 region 且未显式设置，
   **V1 可用而 V4 会直接失败**——这是把可用配置改坏的真实风险。
3. Java 侧签名与数据面都是 SDK 默认 **V1**；若 Python 单独走 V4，两侧会对**同一个桶**发出
   不同签名版本的地址，属客户端可见的不一致。
4. 本轮授权范围是 endpoint 拆分，**不包含**签名版本迁移。
处置：非 STS 恢复 `oss2.Auth`（V1），STS 保持 `StsAuth(auth_version=V4)`（这一支从未改变）；
新增回归守卫 `test_auth_selection_preserves_the_verified_data_plane`，使任何把数据面静默改成
V4 的改动**必然失败**；实施道那两条断言 `x-oss-signature-version=OSS4-HMAC-SHA256` 的测试改为
断言 V1 查询参数（AK/SK 路径），并**新增** `test_sign_public_url_uses_v4_when_sts_credentials`
在 STS 路径保留 V4 覆盖 ⇒ V4 覆盖未丢失，只是移到了真正使用它的那条路径。
**待根裁定**：是否把两侧统一迁移到 V4（官方推荐）。那是一个独立变更，需要用真实凭据重新验证
数据面，并确认 `region` 与桶实际区域一致；本轮不做。
### 9.2 Java 签名器对非正 TTL 由"静默回退默认值"改为"明确失败"
原实现 `Duration ttl = expiry == null || isZero || isNegative ? DEFAULT_EXPIRY : expiry;`
会让调用方以为拿到了自己请求的授权时长。有效期是安全相关参数，现改为抛
`IllegalArgumentException`（消息含 "must be a positive duration"），与 Python 侧
`1..604800` 校验一致；需要默认值必须显式调用单参 `presign(objectKey)`。新增测试
`nonPositiveTtlIsRejectedNotSilentlyDefaulted` 覆盖 null/零/负数三种输入且断言**失败早于任何签名调用**。
### 9.3 orchestrator 自身的两处断言缺陷（已修）
新写的两条测试用 `url.startswith(FAKE_PUBLIC_ENDPOINT)` 断言签名地址，但 `oss2` 采用
**virtual-host 风格**（host = `<bucket>.<endpoint-host>`），该断言必然为假 ⇒ 全量 pytest 一度
2 failed。生产行为正确，错在断言；已改为对 `urlparse(url).hostname` 精确断言
`f"{FAKE_BUCKET}.{urlparse(FAKE_PUBLIC_ENDPOINT).hostname}"`，复跑 405 passed。
