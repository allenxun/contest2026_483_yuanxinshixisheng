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

## 6.5 verify 严格契约与活体证据（BLOCKER 1 / SUGGESTION 9）

- **恒定要求活体**：`FaceServiceClient.verify` 恒发 `require_liveness=true`（无开关）。
  `FaceServiceClientStrictVerifyTest.verifyAlwaysRequiresLiveness` 断言 wire body 含该字段与 `true`；
  `extractDoesNotRequireLiveness` 断言 `classify` 路径不含（取舍见上）。
- **严格响应校验**（`FaceServiceClient.parseVerifyResponse`）：`matched` 必须存在且为 JSON boolean；
  `similarity`/`threshold` 必须存在且为有限数值；`liveness` 必须为对象且 `supported` 为 JSON boolean；
  若返回 `subject_id` 必须与请求值相等。任一不符 ⇒ 抛 `FaceServiceException`
  （code `MALFORMED_RESPONSE`，`FaceServiceFailureKind=DEPENDENCY` ⇒ `DEPENDENCY_FAILED`），
  **绝不**默认成 MATCHED/MISMATCH。
- **活体 fail-closed 加固**：既然请求恒定要求活体，2xx 却返回 `liveness.supported=false` 即为矛盾，
  按 501 `LIVENESS_UNSUPPORTED` 处理（⇒ `CAPABILITY_UNAVAILABLE`），**绝不**因 `matched=true` 放行。
  这堵住"服务忽略 `require_liveness` 却返回 matched"的伪完成路径。
- **活体契约冻结（IMPORTANT）**：当 `liveness.supported=true` 时，**必须**同时返回**本次样本**的
  活体通过结果 `liveness.passed`（JSON boolean）。字段名 `liveness.passed` 是 B 侧冻结的契约形状，
  **服务端将来支持活体时必须返回它**。缺失 / 非 boolean / 为 `false` ⇒ 抛 `LIVENESS_NOT_PASSED`
  （`retryable=false`、HTTP 501）⇒ `InsightFaceCareVerifier` 映射 `CAPABILITY_UNAVAILABLE`，
  **绝不**把"能力支持"当作"样本通过"，**绝不**因缺字段默认通过，**无**任何"跳过活体校验"开关。
  实现：`FaceServiceClient.parseVerifyResponse`（`supported` 判断之后）。
  注：`supported=true` 分支当前对真实服务**不可达**（服务恒返回 `supported=false`），此为防御性
  契约冻结；活体真正落地时该 HTTP/业务映射须重新评估，当前选择保守 fail-closed。
- **判别力**：`FaceServiceClientStrictVerifyTest.matchedOnlyBodyFailsClosed` 用逐字
  `{"matched":true}`（缺 similarity/threshold/liveness）断言其失败而非 MATCHED；
  另有缺 liveness、类型错、`subject_id` echo 不一致、不可解析 JSON、以及
  `supported=true` 但缺 `passed` / `passed=false` / `passed` 非 boolean 等负向用例。
  测试用 `FaceServiceStub.verifyRaw`（不补全）保证逐字检验；
  `InsightFaceCareVerifierLivenessMappingTest` 断言 `LIVENESS_NOT_PASSED` → `CAPABILITY_UNAVAILABLE`。

## 7. 未验证 / 未接入项（如实）

1. **M1-A01 正面闭环未接入**：insightface 无全库识别 ⇒ `UnavailableFaceIdentityResolver` 恒 empty，
   M1-A01 恒 403 `FACE_NOT_VERIFIED`。
2. **1:1 正向闭环未在真实服务上验证**：需远端 namespace 已注册该 `face_subject_ref`；B 侧禁止注册，
   且合成空白图无法检出人脸（只会 `NO_FACE`），真实照片禁止上传。
3. **活体不支持（刻意 fail-closed，非缺陷）**：服务 `liveness.supported=false`；
   `FaceServiceClient.verify`（`face/FaceServiceClient.java`，`verify(...)`）**恒定**发送
   `require_liveness=true`——**不可配置、无关闭开关**（可削弱安全的开关不可接受）。
   因此真实服务对护理 1:1 恒返 501 `LIVENESS_UNSUPPORTED`，`InsightFaceCareVerifier`
   恒映射 `CAPABILITY_UNAVAILABLE`（上层 503）。
   **后果声明：在活体能力真正落地并被服务端接入之前，insightface 模式下的护理 1:1 准入恒不可用。
   这是刻意的 fail-closed，不是缺陷；绝不允许无活体的 1:1 比对放行护理准入，也不得为"让功能可用"而放宽。**
   （`classify`/`/v1/extract` 路径**不**加该门：服务端 extract 无此门，且 `classify` 永不 MATCHED，
   M1-A01 因 `UnavailableFaceIdentityResolver` 恒 403，不存在准入风险。）
4. **阈值 0.40 未标定**：`verify-threshold` 透传，未用真实样本标定。
5. **`aliyun` 仅边界**：无任何阿里云人脸 API 调用代码。
6. 官方/远端对 Spring Boot 3.5 / Java 21 无专项兼容声明（未证明有问题、也未证明已验证）。
7. 远端服务 `model_loaded` 需 15–50s 预热；read 超时默认 30s，真实负载下可能仍需调大。
8. **`liveness.passed` 契约无法对真实服务验证**：服务端 `quality.py` 的 `liveness_block()`
   恒为 `{"supported": false, "reason": "buffalo_l has no liveness model"}`，无 `passed` 字段；
   `supported=true` 分支今天不可达，只用本地 stub 验证（防御性契约冻结）。
   活体真正落地时须由服务端返回 `liveness.passed=true/false`，届时重新评估 501/`CAPABILITY_UNAVAILABLE`
   映射是否仍合适。
