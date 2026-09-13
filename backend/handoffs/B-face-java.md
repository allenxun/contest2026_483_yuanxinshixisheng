# B — Java 应用侧人脸 provider 选择与 InsightFace adapter（`app.face.provider`）

> 范围：供应商无关的人脸 provider 选择 + InsightFace adapter。**本文档不含任何真实 token/凭据**；
> 示例一律为明显假值。已部署服务为只读使用。
> **三条红线**（不得伪完成）：① `classify` 无成员参数 ⇒ 永不 `MATCHED`/`RELIABLE_NEW`；
> ② insightface 下不得用 sha256 冒充身份（恒 `Optional.empty()` ⇒ M1-A01 诚实 403）；
> ③ `aliyun` 仅有配置边界、无实现 ⇒ 选中即拒绝启动。

## 1. 配置键与默认值（默认值写在代码里，未改 yml）

| 键 | 默认 | 说明 |
|---|---|---|
| `app.face.provider` | `doubles` | `doubles`（缺省/替身）\|`insightface`（真实）\|`aliyun`（仅边界，选中拒绝启动） |
| `app.face.insightface.base-url` | 无（**必填**） | 例：`http://10.3.6.163:8010`（文档示例，非默认值） |
| `app.face.insightface.namespace` | 无（**必填**） | 项目专用命名空间，如 `openvela-mvp` |
| `app.face.insightface.internal-token` | 无 | 与 `internal-token-file` **二选一**；两者同配 ⇒ 拒绝启动 |
| `app.face.insightface.internal-token-file` | 无 | 推荐；根在部署机放置，进程可读 |
| `app.face.insightface.connect-timeout-millis` | `3000` | <1000 夹到 1000 |
| `app.face.insightface.read-timeout-millis` | `30000` | 须覆盖模型推理 |
| `app.face.insightface.verify-threshold` | 服务端默认（0.40） | 可选覆盖 |
| `app.face.aliyun.*` | 仅键名 | region/endpoint/access-key-id/access-key-secret/security-token/service-name；**无实现** |

启动期校验（`FaceProvidersConfig:45/49`）：缺 `base-url`/`namespace`/token ⇒ 拒绝启动，**只列键名**；
token 两来源同配 ⇒ 拒绝启动。**不调用远端服务校验**（无启动期网络依赖/副作用）。

## 2. 三条红线的实现位置与证据

| 红线 | 实现位置 | 证据 |
|---|---|---|
| ① `classify` 永不 MATCHED/RELIABLE_NEW | `face/InsightFaceProvider.java:43`（成功→`UNCERTAIN`）、`:45-48`（质量→`QUALITY_REJECTED`，其余→`DEPENDENCY_FAILED`） | `InsightFaceProviderTest`：extract 成功断言 `== UNCERTAIN` 且 `isNotEqualTo(MATCHED/RELIABLE_NEW)`；`classifyNeverReturnsMatchedOrReliableNew` 判别力负向断言 |
| ② 身份解析未接入、sha256 不生效 | `face/UnavailableFaceIdentityResolver.java:34` 恒 `Optional.empty()`；`IdentityProvidersConfig:31` + `MemberBindingFaceDouble:37` + `TestDoubleProvidersConfig:53` 加 `app.face.provider=doubles` 门 | `FaceProvidersConfigTest.insightfaceReplacesDoubles`：`FaceIdentityResolver` 为 `UnavailableFaceIdentityResolver` 且 `resolve` empty；`DevTestFaceIdentityResolver`/`MemberBindingFaceDouble`/`FaceProviderDouble` 均不装配。M1-A01 由 `MemberAccessGrantService:184-186` 走 403 `FACE_NOT_VERIFIED` |
| ③ `aliyun` 拒绝启动 | `face/AliyunFaceBoundaryConfig.java:24-26` 抛 `IllegalStateException("app.face.provider=aliyun is not implemented…")` | `FaceProvidersConfigTest.aliyunRefusesStartup`；真实进程③日志 |

## 3. `classify` 与 `verifyOneToOne` 完整映射（`文件:行`）

**`InsightFaceProvider.classify`（`:42-51`）**

| 远端结果 | FaceClassification |
|---|---|
| `/v1/extract` 2xx（检出人脸） | `UNCERTAIN`（**永不** MATCHED/RELIABLE_NEW） |
| `NO_FACE`/`MULTI_FACES_AMBIGUOUS`/`IMAGE_DECODE_FAILED`/`QUALITY_INSUFFICIENT` | `QUALITY_REJECTED` |
| 依赖故障（5xx/503/504/429/超时/IO/`MODEL_*`/`INFERENCE_TIMEOUT`） | `DEPENDENCY_FAILED` |
| 配置错误（401/415/413/400 参数类） | `DEPENDENCY_FAILED`（枚举无配置档；绝不视为匹配） |

**`InsightFaceCareVerifier.verifyOneToOne`（`:43-64`）**

| 情形 | Outcome |
|---|---|
| 成员无 `face_subject_ref`/不存在 | `CAPABILITY_UNAVAILABLE`（不调远端） |
| `/v1/verify` `matched=true` | `MATCHED` |
| `matched=false` | `MISMATCH` |
| `SUBJECT_NOT_FOUND`/`NAMESPACE_NOT_FOUND`/`LIVENESS_UNSUPPORTED` | `CAPABILITY_UNAVAILABLE` |
| `NO_FACE`/`QUALITY_INSUFFICIENT`（及同族质量码） | `QUALITY_REJECTED` |
| 依赖/配置/网络失败 | `DEPENDENCY_FAILED` |

`FaceServiceFailureKind.classify`（`face/FaceServiceFailureKind.java`）把错误码/HTTP 归为
CONFIGURATION（401/413/415/400 参数类/`SUBJECT_ALREADY_EXISTS`）、CAPABILITY
（`SUBJECT_NOT_FOUND`/`NAMESPACE_NOT_FOUND`/`LIVENESS_UNSUPPORTED`）、DEPENDENCY（5xx/429/504/超时/IO）。

## 4. 装配矩阵实测（`FaceProvidersConfigTest` 7/0/0）

| provider | mode | 结果 |
|---|---|---|
| 缺省 `doubles` | doubles | `FaceProviderDouble` + `DevTestFaceIdentityResolver` + `MemberBindingFaceDouble`（逐字不变） |
| `insightface` | doubles | `InsightFaceProvider` + `UnavailableFaceIdentityResolver`（恒 empty）+ `InsightFaceCareVerifier`；三个 doubles 均不装配 |
| `aliyun` | doubles | **拒绝启动**（"not implemented"，Tomcat 未启动） |
| `insightface` | `disabled` | A 的 disabled 占位优先（`classify`/`resolve` 抛 503）；真实实现不装配 |
| 任意 | 生产信号 + doubles | 既有 `ProvidersModeProductionGuard` 早期拒绝（未绕过） |
| `insightface` 缺键 / token 同配 | doubles | 拒绝启动（只列键名 / 歧义） |

## 5. 与已部署服务的对接方式

- 公开健康检查：`GET {base-url}/v1/health`（无需 token）。
- 受保护端点需请求头 `X-Internal-Token`；本 adapter 只用 `POST /v1/extract`（零写入）与
  `POST /v1/verify`（1:1，读成员参考照）。
- **绝不**调用 `/v1/namespaces/**` 注册/删除；**绝不上传真实人脸**。
- token 由根通过 `app.face.insightface.internal-token-file`（推荐）或 env 注入；**B 侧不读取、
  不打印、不写入仓库**。远端 token 位于远端主机 `~/.config/face-service-openvela.token`。
- 部署需由根设置的键：`APP_FACE_PROVIDER`（`doubles`/`insightface`）、
  `APP_FACE_INSIGHTFACE_BASE_URL`、`APP_FACE_INSIGHTFACE_NAMESPACE`、
  `APP_FACE_INSIGHTFACE_INTERNAL_TOKEN_FILE`（或 `..._INTERNAL_TOKEN`）。

## 6. 生产信号处置（不改守卫）

`InsightFaceCareVerifier` 非 `FailClosedCareFaceVerifier`，与无条件 `CareFaceVerifierProductionGuard`
冲突。处置：装配侧对该 bean 追加 `@Conditional(NonProductionCondition.class)`
（`FaceProvidersConfig:67`）——生产信号下不装配，由无条件的 `FailClosedCareFaceVerifier` 接管；
`ProductionFailClosedValidator` 不检查 `CareFaceVerifier`，`InsightFaceProvider` 属真实 FaceProvider
且不会被 `isDouble()` 误判（包 `…web.face`、类名不以 `Disabled` 开头）。**守卫未改。**

## 7. 未验证 / 未接入项（如实）

1. **M1-A01 正面闭环未接入**：insightface 无全库识别 ⇒ `UnavailableFaceIdentityResolver` 恒 empty，
   M1-A01 恒 403 `FACE_NOT_VERIFIED`。
2. **1:1 正向闭环未在真实服务上验证**：需远端 namespace 已注册该 `face_subject_ref`；B 侧禁止注册，
   且合成空白图无法检出人脸（只会 `NO_FACE`），真实照片禁止上传。
3. **活体不支持**：服务 `liveness.supported=false`；`require_liveness=true` 会 501
   `LIVENESS_UNSUPPORTED`（映射 `CAPABILITY_UNAVAILABLE`）。
4. **阈值 0.40 未标定**：`verify-threshold` 透传，未用真实样本标定。
5. **`aliyun` 仅边界**：无任何阿里云人脸 API 调用代码。
6. 官方/远端对 Spring Boot 3.5 / Java 21 无专项兼容声明（未证明有问题、也未证明已验证）。
7. 远端服务 `model_loaded` 需 15–50s 预热；read 超时默认 30s，真实负载下可能仍需调大。
