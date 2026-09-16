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
| `app.face.insightface.verify-threshold` | 未配置时服务端默认（0.40） | **进程级配置，不可按调用覆盖**；配置存在时客户端随 verify 请求发送 |
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

---

# 8. 2026-09-16 第二轮：Java 直连 InsightFace（1:N 搜索 / 双 verify 语义 / 身份解析）

> 本章节**新增**，§1–§7 的历史记录全部保留。本轮起以下两处历史结论被**修订**（不是删除）：
> ①「`classify` 永不 MATCHED」（§2 红线①）——前提已被 1:N 搜索改变，修订见 §8.1；
> ②「`UnavailableFaceIdentityResolver` 恒 empty」——已删除并替换为
> `InsightFaceIdentityResolver`，修订见 §8.4。
> 其余历史结论（活体 fail-closed、严格契约、aliyun 边界、生产守卫、装配矩阵）仍然成立。
> 用户最终决策：**Java 直连 InsightFace，Java 是人脸库唯一调用/写入方；Worker 不新增 insightface
> provider、不直接调用、不登记/删除 face subject**；MVP 暂不做活体。

## 8.1 修订后的红线①（逐字写入 `InsightFaceProvider` 类 javadoc）

`InsightFaceProvider.classify` **永不**返回 `RELIABLE_NEW`——"未命中"不是"可靠新人"的证据
（依据 `backend/doc/后端详细设计-V1-MVP.md:657,663`）；`MATCHED` **只能**来自 namespace 限定的
1:N 搜索命中（携带 `subjectRef`），**绝不**来自仅 `/v1/extract`。旧红线"永不 MATCHED"的前提是
"只有 extract、无成员语义"，该前提已被 1:N 搜索改变；`MATCHED` 本身**不**授予任何权限——
`MemberAccessGrantService` 仍要求 `resolve` 得到 `subject_ref` **且**只读定位到 `status='active'`
的成员行，否则 403 `FACE_NOT_VERIFIED`。

映射表（`face/InsightFaceProvider.java`）：`search` 结果 `MATCHED`→`MATCHED`；
`no_match`/`uncertain`→`UNCERTAIN`；质量族错误码→`QUALITY_REJECTED`；其余（依赖/配置/网络/形状，
含 `MALFORMED_RESPONSE`）→`DEPENDENCY_FAILED`。
判别力证据：`InsightFaceProviderTest.classifyNeverReturnsReliableNew`（三种 decision + 兜底 503
都断言 `!= RELIABLE_NEW`）、`searchMatchedIsMatched` 断言走 `/search` 且未走 `/v1/extract`、
`malformedSearchIsDependencyFailed`。

## 8.2 两种 verify 语义在类型层面分离（用户硬性要求）

| 语义 | 端口方法 | 返回类型 | 活体 | 用途限制 |
|---|---|---|---|---|
| **照片比对** | `verifyPhotoOnly` | `PhotoComparisonMatch` | **不**发 `require_liveness` | **无防翻拍能力；不得用于护理准入** |
| **经活体校验** | `verifyWithLiveness` | `LivenessVerifiedMatch` | **恒**发 `require_liveness=true` | 护理准入唯一可接受类型 |

两种类型无子类型关系，混用会**编译失败**（刻意设计）。`InsightFaceCareVerifier` 只依赖
`FaceIdentityPort`，其字段/构造参数**不含** `PhotoComparisonMatch`；`CareFaceVerifierTypeSeparationTest`
用反射锁定（端口两方法返回类型不同、两类型互不可赋值、护理 verifier 不声明照片比对字段）。
**README/对外文档必须如实标注"照片比对，无防翻拍能力"**（依据
`backend/doc/人脸服务调研与推荐方案-V1-MVP.md:31,179`）。

## 8.3 两次搜索的代价与理由（如实披露）

`auth/FaceProvider.classify(purpose, content)` 是 A 域接口，**无法携带 `subjectRef`**；而
`MemberAccessGrantService` 的 `MATCHED` 门（`:177-179`）与 `resolve(content, classification)` 签名
（`:184`）都**不能改**（改门会破坏 doubles 语义与 E 的既有"UNCERTAIN → 403"场景，
`application.yml:120-121` 的 `app.testdouble.face.classification` 默认 `MATCHED`）。
因此 insightface 模式下 M1-A01 会有**两次推理调用**：`classify` 一次 + `resolve` 一次
（`InsightFaceIdentityResolverTest.matchedResolvesIdentity` 断言 resolver 自身恰好一次搜索）。
第二次搜索若与第一次不一致（库在此期间变化）⇒ 返回 empty ⇒ 403，这是**保守正确**的行为。

**协调项（单调用优化）**：需要修改 **A 域** `FaceProvider` 接口，让它能承载身份引用
（例如新增 `classifyWithIdentity` 或让 `classify` 返回带 `subjectRef` 的结果类型），
并把 `MemberAccessGrantService` 的"分类 + resolve"两步合并为一步。属跨包接口变更，须总协调裁定。

## 8.4 新 resolver 与 M1-A01 的真实状态

- 删除 `UnavailableFaceIdentityResolver.java`（不留死代码），新增
  `InsightFaceIdentityResolver`（`face/InsightFaceIdentityResolver.java`）：
  仅 `classification == MATCHED` 时调用 `port.search("grant", content)`；
  未命中/不确定/其它分类一律 `Optional.empty()`。装配在
  `FaceProvidersConfig.insightFaceIdentityResolver`。
- **诚实声明**：即便 resolver 解析出 `subject_ref`，只要 `members.face_subject_ref` 无人填充
  （当前唯一生产写入方是 D 包 Python，见 §8.5），`MemberAccessGrantService` 的只读成员定位
  （`:191`）仍查不到 `status='active'` 的行 ⇒ **M1-A01 恒 403 `FACE_NOT_VERIFIED`**。
  这是**诚实拒绝，不是伪造成功**，绝不用 sha256 冒充身份。
- **发现但未修（跨写域，报告给 orchestrator）**：`resolve` 的第二次搜索若发生依赖故障，
  `FaceServiceException` 会向上抛出到 `MemberAccessGrantService`（该类未捕获），可能变成
  500 而非 403/503。契约 §2.6 给出的代码未要求捕获，故按契约保留；建议裁定是否改为
  `catch (FaceServiceException) → Optional.empty()`（fail-closed 403）。
  `InsightFaceIdentityResolverTest.dependencyFailurePropagates` 如实记录当前行为。

## 8.5 `register`/`delete`：已实现、已测试，但不接入任何业务流程（跨包 blocker）

**精确 blocker（逐条证据）**：`members` 的**唯一生产写入方**是 D 包 Python
`backend/worker-python/src/mvp_worker/handlers/identity_enroll.py:55-68`（`_INSERT_MEMBER`，含
`ON CONFLICT (identity_namespace, face_subject_ref) DO NOTHING`），执行于 `_commit_enrollment:361-435`
（`:383-392` 插入、`:394-398` 冲突回查）；Java 生产代码**从不写** `members`。
列与唯一索引已存在（`src/main/resources/db/migration/V1__create_tables.sql:76-96`，
`uq_members_identity:94-96`）⇒ **不需要新迁移**；但由 Java 写 T01 属跨包写域
（`backend/doc/tasks/COMMON.md:17` D 独占 identity-enroll handler；A 独占数据库迁移 `:16`），
且两个写入方共用同一唯一键正是要避免的 TOCTOU/重复 subject 风险。

**因此本轮**：`FaceServiceClient.register/get/delete`（即 `FaceIdentityPort` 的写方法）作为
**已实现且已测试的能力**交付（`FaceServiceClientSubjectsTest`），但
`members.face_subject_ref` **一个字节都不写**，无任何业务流程调用。

### 8.5.1 关联设计（完整、可执行，供裁定后立即实施）

- **唯一性**：复用既有 `uq_members_identity` 部分唯一索引（`identity_namespace, face_subject_ref`）。
- **幂等**：`subjectRef` 由调用方**预先确定**（不由端口生成随机值），使重试可用同一 ref 对账；
  复用既有 `IdempotencyService.begin/completeSuccess/completeRejected`（`:60-182`）与
  `idempotency_requests`（`V1:27-53`，唯一键 `(principal_type,principal_id,operation,idempotency_key)`）。
- **"远端登记成功 + 本地事务失败/重试"对账**：先用 `port.get(subjectRef)` 查询（**不**用全库搜索），
  命中即认领既有登记、不再重复 register；依据 `后端详细设计-V1-MVP.md:659`
  「网络超时先按同 EntityId 查询对账，不生成另一 ID 盲目重试」。
- **TOCTOU 双写**：单一写入方（Java）+ 预确定 ref + DB 唯一索引 + `INSERT ... ON CONFLICT DO NOTHING`
  后回查（与 D 现有 `:383-398` 同一范式），**不**靠应用层检查-后写。
- **孤儿映射**：`register` 成功但成员行未建立时，该 subject 必须处于**受控待对账**状态
  （依据 `:661`「外部成功但业务取消的人员资源保留受控对账，确认无业务引用后再清理」），
  **不得**自动删除、也**不得**被后续流程误认为已建档。
- **实现事实（我实现时发现）**：`register` 显式发送 `on_exists=conflict`，使既有主体**绝不**
  被静默覆盖（与端口 `SUBJECT_ALREADY_EXISTS` 语义一致，且不受部署端
  `FACE_SVC_REGISTER_ON_EXISTS=overwrite` 影响）；`delete` 对 404 返回
  `FaceSubjectDeletion(deleted=false, libraryRevision=-1, requestId)` 实现幂等
  （404 信封不携带修订号，`-1 = UNKNOWN_LIBRARY_REVISION` 是诚实哨兵）。

### 8.5.2 最小协调接口（三选一，给总协调裁定）

- **(i) 推荐**：授权 Java 成为 `members.face_subject_ref` 的唯一写入方，同时 **D 停用**
  `identity_enroll.py` 的人脸库调用与 `members` 写入（或改为只消费 Java 的登记回执）。
- **(ii)** D 保留写 `members`，但 `face_subject_ref` 必须取自 Java 的登记回执 ⇒ 需要新增 B→D 契约
  （例如 Java 暴露一个内部只读查询，或经 T12 任务载荷传递 ref）。
- **(iii)** 新增 B 自有映射表 ⇒ **需要 A 的公共迁移 V3**（目录
  `src/main/resources/db/migration/`，最新为 V2，命名 `V<n>__<snake>.sql`）。

### 8.5.3 在该调整前不得宣称完成的 E2E（逐条列）

1. M1-A01 的真实身份解析闭环（当前因 `members.face_subject_ref` 无人填充而恒 403——
   **诚实拒绝，不是伪造成功**）。
2. `identity.enroll` 建档链路。
3. 任何依赖该映射的护理 1:1。

## 8.6 D 侧 Worker 人脸调用必须由 D/总协调停用（本轮我不动 `worker-python/**`）

证据（契约所列行号）：`identity_enroll.py:175`（`face.register_person`）、`:185,236`
（`query_registration`）；`assessment_analyze.py:260`（`quality`）、`:278`（`same_person`）、
`:351`（`search_1n`）、`:695-700`（成员解析）；端口解析 `dshared/resolve.py:42-49`；
协议 `dshared/providers.py:114-136`；工厂 `build_face_port:779-786`。
**在 D 停用前，人脸库存在两个写入/调用方（Java 与 D 的 Python）**，与"Java 是唯一调用/写入方"
的目标冲突。裁定归属：现有 Worker 人脸代码**不得**扩展为本方案实现；停用动作由 D/总协调执行。

## 8.7 护理路径继续 fail-closed 的后果声明

`InsightFaceCareVerifier` 改为消费 `port.verifyWithLiveness` 返回的 `LivenessVerifiedMatch`，
映射表**逐字保持**（成员无 `face_subject_ref`/不存在 → `CAPABILITY_UNAVAILABLE`（不调远端）；
`matched=true`→`MATCHED`；`matched=false`→`MISMATCH`；
`SUBJECT_NOT_FOUND`/`NAMESPACE_NOT_FOUND`/`LIVENESS_UNSUPPORTED`/`LIVENESS_NOT_PASSED`
→`CAPABILITY_UNAVAILABLE`；质量族→`QUALITY_REJECTED`；依赖/配置/网络/形状→`DEPENDENCY_FAILED`）。
**真实服务无活体 ⇒ 护理 1:1 恒 `CAPABILITY_UNAVAILABLE`（对外 503）**——刻意 fail-closed，
**不得**为"让功能可用"而让护理路径接受 `PhotoComparisonMatch`，**不得**新增任何"跳过活体"开关，
**不得**改 `CareFaceVerifierProductionGuard`。

## 8.8 无活体限制（MVP）

服务诚实声明 `liveness.supported=false`。**Java 的 MVP 普通业务路径不再恒发
`require_liveness=true` 导致固定 501**：`classify` 走只读 `/search`、`verifyPhotoOnly` 走不要求活体的
`/v1/verify`；护理路径仍走 `verifyWithLiveness`（恒 `require_liveness=true`）。两种语义在类型层面
分离（§8.2），禁止混用。

## 8.9 `aliyun` 边界保持现状

`AliyunFaceBoundaryConfig`（`:24-43`）的"选中即**启动期拒绝**"（static `@Bean` 的 BFPP）保持不变
（用户要求"启动期或调用期明确拒绝，不做假结果"，启动期拒绝已满足且已有测试）。
**将来接阿里云＝新增一个 `FaceIdentityPort` 实现 + 替换该 boundary，业务层、HTTP 契约、DTO、
数据库身份语义都不改。** 本轮**不**接真实阿里云、**不**读凭据。

## 8.10 错误码与日志（本轮）

- `FaceServiceFailureKind.DEPENDENCY_CODES` 新增 `STORE_UNAVAILABLE`（Python 道为 SQLite 不可达
  新增的 `/ready` 码）；**不**新增任何 `ErrorCode` 枚举值、**不**改契约/文档目录、
  **不**新增 `/api/**` 业务端点（不触发 `ApiDocsCoverageIT`）。
- `LIVENESS_UNSUPPORTED`/`LIVENESS_NOT_PASSED` 继续只是**人脸服务侧**字符串码，**不**提升为
  `ErrorCode`。
- 全部 2xx 响应严格校验（必需键缺失/类型不符/数值非有限/`subject_id` 回显不一致 ⇒
  `MALFORMED_RESPONSE`，DEPENDENCY），**绝不**默认成功；非 2xx/超时/IO 一律 fail-closed。
- 日志只记 op/HTTP 状态/服务码/`request_id`；`FaceSecurityTest.newOperationsDoNotLeakSecrets`
  断言新方法（search/verifyPhotoOnly/register）的日志与异常消息**不含** token、图片字节、
  namespace 取值、`subjectRef` 取值。

## 8.11 未验证 / 未完成清单（第二轮）

1. **未对真实人脸服务验证**：全部测试离线（`FaceServiceStub`），未访问 8002/8003/8010。
2. **未跑 `mvn`/测试运行器**（契约禁止）；仅 `javac` 自检（见 orchestrator 报告）。运行时判别力
   证据（"改坏即失败"）未执行，只给出静态论证与可变异的精确位置。
3. **M1-A01 真实闭环未完成**（§8.4）。
4. **`register`/`delete` 未接入业务流程**（§8.5）。
5. **D 侧 Python 人脸调用仍未停用**（§8.6），当前存在两个调用方。
6. **单调用优化未做**（需改 A 域 `FaceProvider` 接口，§8.3）。
7. **`resolve` 第二次搜索依赖故障的 500 vs 403 语义待裁定**（§8.4）。
8. `verify-threshold` 仍为未标定值；1:N 的 `search_match_threshold=0.60` 等由服务端固定且未标定。

---

# 9. 2026-09-16 第二轮补丁：第二次搜索依赖故障的 503 映射（运行时已核验）

> 本节新增，§1–§8 保留。修复上一轮如实上报的"问题 1"，并补齐上一轮被禁跑 mvn 而缺失的
> 运行时验证。

## 9.1 缺陷与修法（只修调用方，不修 resolver）

修复前：`InsightFaceIdentityResolver.resolve` 内部的第二次 1:N 搜索遇到依赖故障会抛
`FaceServiceException extends RuntimeException`；`MemberAccessGrantService` 未捕获（该文件只在
更后面捕获 `DuplicateKeyException`），而 `GlobalExceptionHandler` 的兜底
`@ExceptionHandler(Exception.class)` 渲染 **500 INTERNAL / retryable=false**。同一方法对第一次搜索
（`classify → DEPENDENCY_FAILED`）却明确抛 503 `DEPENDENCY_UNAVAILABLE`（可重试）⇒ 两条路径不一致，
且 500 既不诚实也不可重试。

裁定修法：**修在调用方 `MemberAccessGrantService`**（`identity/**` 是 B 自有域；`FaceIdentityPort`
javadoc 已明写"调用方负责把异常映射为 503"；与第一次搜索的 `:176` 对称）。
**不修 `InsightFaceIdentityResolver`**（继续按端口契约抛 `FaceServiceException`）。

精确 diff（`web/identity/MemberAccessGrantService.java`，仅 import + catch + 注释）：
- `+import cn.yuanxin.mvp.web.face.FaceServiceException;`
- `resolve(...)` 包裹 `try/catch (FaceServiceException dependencyFailure)`，catch 内
  `throw new ApiException(ErrorCode.DEPENDENCY_UNAVAILABLE, "face verification dependency unavailable")`
  （消息**逐字复用**第一次搜索分支；**不**调用 `reject(...)`，让 T13 留在 `processing` 以便重试/对账；
  **不**降级为 `Optional.empty()` ⇒ 不会变成 403）。
- 无其它改动。

## 9.2 新增测试与运行时判别力证据

新增 `web/identity/MemberAccessGrantFaceDependencyFailureIT`（真实 HTTP 入口 + PG；`@MockitoBean`
替换 `FaceIdentityResolver` 令 `resolve` 抛真实 `FaceServiceException`，默认 doubles `FaceProvider`
返回 `MATCHED` ⇒ 必然执行到新增 catch）：
`identityResolutionDependencyFailureIsRetryable503` 断言 503 / `DEPENDENCY_UNAVAILABLE` /
`retryable=true` / 无 grant 行 / T13 仍 `processing`。

判别力实测（临时移除 catch 后重跑该测试）：
```
RC=1
Body = {"requestId":"e3f6a097-ffe0-406a-ab84-12f6c493afbd","error":{"code":"INTERNAL","message":"internal server error","retryable":false}}
AssertionFailedError: ... ==> expected: <503> but was: <500>
Tests run: 1, Failures: 1, Errors: 0, Skipped: 0
```
还原证明（`cp -a` 字节备份 + sha256 + cmp）：
```
orig sha256 = 2ca33bdbd215aa489030a27f715628601117edd8a5fdabe3f39c9d1258e2d20d
after sha256 = 2ca33bdbd215aa489030a27f715628601117edd8a5fdabe3f39c9d1258e2d20d
cmp => byte-identical RESTORED
```
（备份与日志在 `.coordination/B-work/face-round/scratch-java/` 与 `.coordination/B-work/face-round/java/`；
本轮未使用 `git checkout/restore/stash`。）

## 9.3 本轮 mvn 结果（精确数字 + 退出码）

| 命令 | 结果 |
|---|---|
| `mvn -B -f backend/web-java/pom.xml test-compile` | **rc=0**（133 test source files 编译） |
| `mvn -B ... test -Dtest='cn.yuanxin.mvp.web.face.*Test,cn.yuanxin.mvp.web.face.*IT,cn.yuanxin.mvp.web.identity.MemberAccessGrantFaceDependencyFailureIT'` | **117 run / 0 failures / 0 errors / 0 skipped，rc=0** |
| `mvn -B -f backend/web-java/pom.xml test`（全量） | **814 run / 0 failures / 0 errors / 18 skipped，rc=0，116 份 surefire xml** |
| `ApiDocsCoverageIT` | **1 / 0 / 0**（未新增 `/api/**` 端点或 `ErrorCode`） |

**与权威基线（747/0/0/18，109 xml）逐类对账（+67 tests，+7 classes）：**
- 上一轮新增 6 个类 = 56 tests：`FaceServiceClientQualityTest` 10、`FaceServiceClientSearchTest` 19、
  `FaceServiceClientSubjectsTest` 11、`FaceServiceTypesTest` 6、`InsightFaceIdentityResolverTest` 5、
  `CareFaceVerifierTypeSeparationTest` 5。
- 本轮新增 1 个类 = 1 test：`MemberAccessGrantFaceDependencyFailureIT` 1。
- 既有类净增 10 tests：`FaceServiceClientStrictVerifyTest` +5（photo-only ×3、threshold ×2）、
  `InsightFaceProviderTest` +3、`FaceServiceClientTest` +1（STORE_UNAVAILABLE）、`FaceSecurityTest` +1。
- 56 + 1 + 10 = 67；747 + 67 = 814；109 + 7 = 116。`skipped` 18 不变。
- 端口：全程只用 MockMvc（`WebEnvironment.MOCK`，无监听端口）；用毕 18083 空闲、无遗留 mvn/JVM 进程。

## 9.4 doubles 路径行为零变化（代码层 + 测试层论证）

- **代码层**：新增的只有 `catch (FaceServiceException)`。doubles 模式下 `FaceIdentityResolver` bean 是
  `DevTestFaceIdentityResolver`，其 `resolve` 不产生任何远端调用、类体内不引用/不抛出
  `FaceServiceException`（`DevTestFaceIdentityResolver.java` 全文无该类型）⇒ 该 catch 在 doubles 模式下
  **不可达**，行为逐字不变。
- **测试层**：全量 814/0/0 包含 `MemberAccessGrantsIT` 11/0/0、`MemberAccessGrantStorageFailureIT` 1/0/0、
  `IdentityProvidersModeGateTest` 4/0/0、`FaceProvidersConfigTest.defaultDoubles`（doubles 三 bean 装配）
  全部通过；E 的既有"UNCERTAIN → 403"场景未受影响。

## 9.5 threshold wire 逐字未变（接受偏离 9 的附加要求）

新增 `FaceServiceClientStrictVerifyTest.thresholdComesFromConfiguredProperty`：两种 verify 的 wire body
都含 `name="threshold"` 且值为配置的 `0.4`（来自 `app.face.insightface.verify-threshold`）；
`absentConfiguredThresholdIsNotSent`：properties 为 null 时不发送 threshold（服务端固定默认生效）。
即构造器去 `threshold` 参后 wire 语义与既有逐字一致。

## 9.6 文档措辞更正（上一轮问题 3）

`## 1. 配置键与默认值` 表中 `app.face.insightface.verify-threshold` 行的"可选覆盖"已改为
"**进程级配置，不可按调用覆盖**；配置存在时客户端随 verify 请求发送"。

## 9.7 仍未验证 / 未修（保留）

1. **未对真实人脸服务验证**（未访问 8002/8003/8010）。
2. **register/delete 未接入业务流程**（跨包 blocker，§8.5）。
3. **M1-A01 真实闭环未完成（恒 403 `FACE_NOT_VERIFIED`，诚实拒绝）**（§8.4）。
4. **D 侧 Worker 人脸调用未停用**（§8.6），当前仍有两个调用方。
5. 两次搜索窗口、`FaceQualityView.reasons` 恒空、严格 health 兼容性：按裁定只登记不修（§8.11）。
6. 单调用优化需改 A 域 `FaceProvider` 接口（§8.3）。
