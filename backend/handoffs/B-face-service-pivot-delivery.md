# B 交付报告 — 方案反转轮：Worker 对接 InsightFace 的 face-service 能力与冻结合同

**日期**：2026-09-16　**工作树**：`.worktrees/mvp-b`　**分支**：`feature/mvp-identity-devices`
**基线**：`e57bc315`（本轮开工时的 dev tip，开工实测工作树 clean）
**状态**：代码已提交、Oracle 复审进行中；**未 push、未合并 dev、未部署**。

---

## 1. 最终 SHA（结论栏）

| 项 | 值 |
|---|---|
| **合同 SHA**（纯文档，D 的唯一对接依据） | **`96d7e03c45481be51cd28c35ac1d2cc9fce6b497`** |
| **最终代码 SHA** | **`9a1dd77346e9db1d1ddd1e98f9335acfa5b8dea2`** |
| **Oracle reviewed SHA** | `9a1dd77346e9db1d1ddd1e98f9335acfa5b8dea2`（同一 SHA） |
| **Oracle 裁定** | _待填（复审进行中，会话 `ora-1` = `ses_f70bc47c3ffeLASOzFOAJZPUO8`）_ |
| 是否涉及公共文件 | **否**（详见 §6） |

提交链（全部为普通提交，**无** reset/rebase/amend/改写历史）：

```
e57bc315 (dev 基线)
├─ 1d6ac78  face-service 1:N search + /live + /ready + top_k 下界 + 错误码双向锁 + 文档面关闭   [保留]
├─ 0dfdf29  face-service 行尾空白修正                                                        [保留]
├─ d80c50d  Java 直连 InsightFace + 真实 resolver                                            [已废弃]
├─ 0d9ee60  Java→Worker 身份结果合同 + 5 个冻结类型                                           [已废弃]
├─ 081f834  Revert "0d9ee60"                                                                 [移除废弃合同]
├─ c4cb73a  Revert "d80c50d"                                                                 [移除 Java 直连]
├─ 96d7e03  docs: 冻结 Worker FacePort ↔ face-service 合同（334 行，纯文档）                    [合同 SHA]
└─ 9a1dd77  feat: face-service 对齐合同（11 文件 +1592 −46）                                   [最终代码 SHA]
```

---

## 2. 方案反转的可审计处置

用户授权：**改回 Python Worker 对接 InsightFace**；Java 不直连、不写人脸库；保留 face-service 通用能力。

### 2.1 未提交改动的留档与撤回
先在 `.coordination/B-work/pivot-audit-2026-09-16/` 生成审计件，**再**撤回：

| 审计件 | 内容 |
|---|---|
| `uncommitted-tracked.diff`（15799 B） | 2 个已跟踪文件的完整 diff |
| `untracked-files.tar`（71680 B，6 文件） | 6 个未跟踪 Java 文件的完整内容（逐个 `cmp` 校验后才删） |
| `provenance.txt` | **逐项来源确认**（用户明确要求） |
| `all-uncommitted-paths.txt`、`uncommitted-inventory.txt`、`deprecated-commits.txt`、`java-after-revert.log` | 清单与证据 |

- `git apply --check --reverse` **rc=0** ⇒ patch 与工作树逐字节吻合，可完整恢复。
- 撤回前实测：本轮开工时 `tree entries = 0`，且未提交路径**域外命中 0** ⇒ **不含任何"进入本轮前已有的他人未提交内容"**，撤回未覆盖他人工作。

### 2.2 已提交改动的移除（普通 revert）
`081f834` 撤 `0d9ee60`、`c4cb73a` 撤 `d80c50d`。**revert 后逐条证明**：

| 断言 | 实测 |
|---|---|
| `git diff e57bc315..HEAD` 对 `backend/web-java` | **0 文件** |
| 同上对 `backend/handoffs` | **0 文件**（`B-face-java.md` 回到 142 行且 blob 与基线相同） |
| `B-identity-result-contract.md` 是否存在 | **NO**（废弃合同已移除，未交给 D） |
| `UnavailableFaceIdentityResolver` 是否恢复 | **YES** |
| `MemberAccessGrantService` 的 `FaceServiceException` catch | **0**（已移除） |
| `web/face` 文件数 | **12 = 本轮前 12** |
| Java 全量 `mvn -B test` | **747 run / 0 failures / 0 errors / 18 skipped，BUILD SUCCESS rc=0，109 份 xml**（= 本轮前基线） |
| 本轮新增 Java 测试类残留 | **0**（`IdentityEnrollment*`/`FaceServiceClientSearch*`/`InsightFaceIdentityResolver*` 报告数 0） |
| 全树相对 `e57bc315` 的差异 | **只剩 `backend/face-service`**（当时 16 文件 +1200 −16） |

### 2.3 一处范围判定（如实记录，未擅自扩大）
用户点名的废弃提交是 `d80c50d` 与 `0d9ee60` 两个，已完整 revert。树中**仍保留**更早已交付、
经 Oracle 通过并已并入 dev 的 Java 人脸边界（`app.face.provider=insightface` 的
`FaceServiceClient` health/extract/verify、`InsightFaceProvider.classify` 恒 `UNCERTAIN`、
`UnavailableFaceIdentityResolver` 恒 `empty`、`InsightFaceCareVerifier` 恒 `CAPABILITY_UNAVAILABLE`）。
它**不含**用户列出的任何移除目标（无真实 resolver、无 register/search/delete、不写
`face_subject_ref`、非本轮废弃合同），移除它等于回退已被 dev 接受的基线 ⇒
**未擅自扩大 revert 范围**，作为待裁定项列入 §8。

---

## 3. 合同摘要（`96d7e03`，334 行，`backend/handoffs/B-face-service-worker-contract.md`）

**消费方**：D 的 Python Worker（`handlers/dshared/providers.py` 的 `FacePort`）。
**生产方**：B 的 `backend/face-service`（独立实例、独立 SQLite，与共享 8002/8003 物理隔离）。
**B 未修改任何 `backend/worker-python/**` 文件**——合同中的 D 侧引用全部为只读取证。

### 3.1 取证发现的三处实质能力缺口（不只是改名）
| FacePort 方法 | Worker 期望（取证位置） | face-service 原状 | 缺口 |
|---|---|---|---|
| `search_1n` | `classification ∈ matched\|uncertain\|ambiguous\|reliable_new`（`providers.py:77-80`） | `decision ∈ matched\|no_match\|uncertain` | **`no_match` 不在词表内**；`assessment_analyze.py:415-420` 对未知取值一律判 `DEPENDENCY_UNAVAILABLE` ⇒ 每次正常搜索都会被当成依赖故障 |
| `same_person(images)` | `SamePersonResult(ok)`，**图↔图**互比（`providers.py:119`） | `/v1/verify` 只比"图 vs **已登记** subject" | 缺 image↔image 比较端点 |
| `register_person(..., correlation_id, provider_request_id)` / `query_registration(...)` | 幂等登记 + 按 correlation_id 对账（`providers.py:121-136`、`identity_enroll.py:173-200`） | 全仓 `correlation`/`provider_request` **0 命中** | 缺幂等语义、缺持久化、缺对账端点 |
| `quality(images: dict)` | `QualityResult(status, required_views)`，三视角（`providers.py:66-69,118`） | `/v1/quality` 单图 | 无缺口：适配层按视角逐次调用后聚合（合同 §3 裁定） |

### 3.2 两处刻意的保守裁定
1. **空库不再返回"新人"**：`subject_count == 0` → `uncertain` + `reasons=["empty_library"]`。
   理由：库为空更可能是**未初始化或被误清**，此时把每个人都判成"可靠新人"会**批量建档**。
2. **`reliable_new` 的语义边界**：只表示"在本 namespace 内以 `policy_version` 所述策略搜索、
   单脸、质量合格、最高相似度明确低于阈值"，**不**表示算法能证明是新人类。依据
   `后端详细设计-V1-MVP.md:657`「未命中只成为新人候选」与 `:663`「未通过 PoC 不得开启真实自动
   登记」⇒ **D 在 PoC 门禁通过前不得据此开启自动建档**，且 `assessment_analyze.py:377-389`
   现有的"先对账 PG、已有成员则不重复建档"必须保留。

### 3.3 设计裁定：服务端只提供单图原语，多视角聚合由 Worker 适配层完成
理由：①"哪些视角必需"是业务策略（D 的 `REQUIRED_VIEWS_ALL`，`dshared/constants.py:18`），
不属算法服务；②单图原语可独立测试/失败/重试；③避免服务端持有业务视图命名。

### 3.4 不产出 `ambiguous` 的理由
Worker 在 `assessment_analyze.py:369` 把 `uncertain` 与 `ambiguous` **同等**处理（都走补拍
`IDENTITY_UNCERTAIN`）⇒ 服务端用 `decision="uncertain"` + `ambiguous=true` +
`reasons=["ambiguous_top_candidates"]` 表达即可，**无信息损失**，且严格落在授权的三值词表内。

---

## 4. Worker `FacePort` 五项精确映射（合同 §8，D 据此实现 `InsightFaceAdapter`）

| # | FacePort 方法 | 调用 | 映射规则 |
|---|---|---|---|
| 1 | `quality(images: dict[str,bytes]) -> QualityResult` | 对**每个视角**各调一次 `POST /v1/quality` | 全部 `min_acceptable=true` → `QualityResult("accepted", ())`；否则 `QualityResult("needs_retake", <不合格视角元组>)`。**任一视角调用失败 → 抛 `ProviderUnavailable`**，绝不把失败当合格 |
| 2 | `same_person(images: dict[str,bytes]) -> SamePersonResult` | `POST /v1/compare`（按 D 选定策略两两比或对着主视角比） | 全部 `matched=true` → `SamePersonResult(True)`；任一 `false` → `False`；调用失败 → `ProviderUnavailable` |
| 3 | `search_1n(namespace, images) -> SearchResult` | `POST /v1/namespaces/{ns}/search`（建议用 `front`） | `decision` **直接**用作 `classification`（三值均在 Worker 词表内）；`matched` 时 `face_subject_ref = subject_id`，其余为 `None`。传输失败 → `ProviderUnavailable`；**4xx 参数/鉴权类 → `ProviderConfigError`（不可重试）**；**5xx/超时 → `ProviderUnavailable`（可重试）** |
| 4 | `register_person(ns, entity_id, images, correlation_id, provider_request_id) -> RegisterResult` | `POST /v1/namespaces/{ns}/subjects`，`subject_id=entity_id`，带两个对账键，**不传 `on_exists`**（用服务端默认 `conflict`）、**不传 `require_liveness`** | 201 创建 / 200 幂等重放 → `success`；409 `SUBJECT_ALREADY_EXISTS` → `failed`；客户端超时 → `timeout`；5xx 或 `MODEL_*`/`STORE_UNAVAILABLE` → `unknown`；其它 4xx → `failed` |
| 5 | `query_registration(correlation_id, provider_request_id, *, namespace, entity_id) -> RegistrationQueryResult` | `GET /v1/namespaces/{ns}/registrations/{correlation_id}?provider_request_id=…&entity_id=…` | `status="registered"` → `registered`；`"not_found"` → `not_found`；传输失败/无法解析 → `unknown`（**服务端绝不产出 `unknown`**） |

**硬性纪律**：真实服务故障**绝不**回退替身成功；`ProviderNotActivated` 用于"未授权/未过 PoC"，
绝不伪造结果；不得把 `reliable_new` 当作"算法已证明是新人"；不得上传真实用户照片联调；
适配层日志不得出现 token、图片字节、embedding、namespace/subject_id/correlation_id 取值。

---

## 5. 服务端摘要（路由 / 图片限制 / 阈值 / 状态码 / 错误码 / revision / 幂等）

### 5.1 路由总表（13 个端点）
| 端点 | 鉴权 | 写库 | 本轮变化 |
|---|---|---|---|
| `GET /v1/health` | 否 | 否 | **一行未改** |
| `GET /live` | 否 | 否 | 不变（本轮早前已有） |
| `GET /ready` | 否 | 否 | 不变（检查模型 **与** SQLite） |
| `POST /v1/extract` | 是 | **零写** | 不变 |
| `POST /v1/quality` | 是 | **零写** | 不变（单图原语） |
| `POST /v1/compare` | 是 | **零写** | **新增**（图↔图 1:1） |
| `POST /v1/verify` | 是 | **零写** | 不变（严格 1:1，只查指定 subject） |
| `POST /v1/namespaces/{ns}/search` | 是 | **零写** | **词表变更**（`search-v2`） |
| `POST /v1/namespaces/{ns}/subjects` | 是 | **是** | **幂等语义 + 对账键** |
| `GET /v1/namespaces/{ns}/subjects/{id}` | 是 | 否 | 不变 |
| `GET /v1/namespaces/{ns}/registrations/{correlation_id}` | 是 | 否 | **新增**（只读对账） |
| `DELETE /v1/namespaces/{ns}/subjects/{id}` | 是 | **是** | 不变 |
| `GET /v1/namespaces/{ns}/info` | 是 | 否 | 不变 |

文档面 **`/docs`、`/redoc`、`/openapi.json` 全部 404**（`app.py:68-70`）。

### 5.2 图片与请求限制
- 输入形态：`multipart/form-data` 文件字段，或 JSON base64（支持 `data:image/...;base64,` 前缀）；
  其它 Content-Type → **415 `UNSUPPORTED_MEDIA_TYPE`**。`/v1/compare` 用 `image_a`/`image_b`
  （JSON 为 `image_a_base64`/`image_b_base64`），复用同一套解码规则与错误映射。
- 大小：`FACE_SVC_MAX_BODY_BYTES`（默认 10485760）→ 超限 **413 `IMAGE_TOO_LARGE`**；
  `content-length` 与实际 body 长度**双重**检查。空 body → 400 `INVALID_REQUEST`。
- 解码失败 → **400 `IMAGE_DECODE_FAILED`**；0 张脸 → **400 `NO_FACE`**；
  多张脸 → **400 `MULTI_FACES_AMBIGUOUS`**（**绝不**自动取最大脸：`compare` 两张探针下无法判定谁比谁）。
- 标识符（namespace/subject_id/correlation_id/provider_request_id/entity_id）统一受
  `^[A-Za-z0-9._:-]{1,128}$` 约束，违规 → 400 `INVALID_REQUEST`。
- **绝不接受文件路径或 URL**（只接受字节/base64/data-url）。

### 5.3 匹配分数与阈值（全部服务端固定策略）
| env 键 | 默认 | 校验 | 用途 |
|---|---|---|---|
| `FACE_SVC_SEARCH_MATCH_THRESHOLD` | **0.60** | `0 < x <= 1` | 1:N 命中阈值 |
| `FACE_SVC_SEARCH_UNCERTAIN_BAND` | **0.10** | `0 <= x < match_threshold` | 阈值下方的不确定带 |
| `FACE_SVC_SEARCH_MARGIN` | **0.05** | `0 <= x <= 1` | top1 与 top2 的最小间隔（歧义保护） |
| `FACE_SVC_SEARCH_TOP_K` | **5** | 整数 **2..10** | 候选窗口 |
| `FACE_SVC_VERIFY_THRESHOLD` | **0.40** | `0 < x <= 1` | 1:1（`/v1/verify` 与 `/v1/compare` 默认） |

- **search 绝不接受客户端阈值**（`人脸服务调研与推荐方案-V1-MVP.md:131,134`）；
  `/v1/compare` **接受** `threshold`，因为它不查任何 namespace，调用方无法借此降低服务端固定的
  库策略（此不对称已交 Oracle 裁定）。
- `top_k` 下界为 **2**：`top_k=1` 会使 margin 歧义保护**结构性失效**（无次优可比）。
- 非法值一律 `ConfigError` **fail fast** 且**不回显被拒值**。
- **全部阈值为未经标定的保守占位**；1:N 的 0.60 **严于** 1:1 的 0.40（误接受风险随库规模上升）。
  相似度**不是**百分比可信度。**标定前不得开启自动建档。**
- 响应**永不**外发数值阈值，只给 `policy_version`。

### 5.4 状态码
- **成功恒 200**（search 的三种 decision 都是业务判定，不是错误）；
  登记 **201** 创建 / **200** 覆盖或幂等重放；对账查询命中或未命中**均为 200**
  （Worker 按 `status` 分支，不按 HTTP 码）。
- 4xx：400（`NO_FACE`/`MULTI_FACES_AMBIGUOUS`/`IMAGE_DECODE_FAILED`/`INVALID_REQUEST`/
  `top_k` 越界）、401（`UNAUTHORIZED`）、404（`SUBJECT_NOT_FOUND`/`NAMESPACE_NOT_FOUND`）、
  409（`SUBJECT_ALREADY_EXISTS`）、413、415、422（`QUALITY_INSUFFICIENT`）、429（`CONCURRENCY_LIMIT`，retryable）。
- 5xx：500（`INTERNAL_ERROR`）、501（`LIVENESS_UNSUPPORTED`）、503（`MODEL_UNAVAILABLE`/
  `MODEL_NOT_LOADED`/`STORE_UNAVAILABLE`，均 retryable）、504（`INFERENCE_TIMEOUT`，retryable）。
- 统一信封 `{"error":{code,message,retryable,request_id[,details]}}`；
  **`details` 绝不含** token、图片字节、embedding、namespace/subject_id/correlation_id 取值。

### 5.5 错误码表（18 个，双向锁定）
`NO_FACE`(400)、`MULTI_FACES_AMBIGUOUS`(400)、`IMAGE_DECODE_FAILED`(400)、`INVALID_REQUEST`(400)、
`UNAUTHORIZED`(401)、`SUBJECT_NOT_FOUND`(404)、`NAMESPACE_NOT_FOUND`(404)、
`SUBJECT_ALREADY_EXISTS`(409)、`IMAGE_TOO_LARGE`(413)、`UNSUPPORTED_MEDIA_TYPE`(415)、
`QUALITY_INSUFFICIENT`(422)、`LIVENESS_UNSUPPORTED`(501)、`INTERNAL_ERROR`(500)、
`MODEL_UNAVAILABLE`(503,retryable)、`MODEL_NOT_LOADED`(503,retryable)、
`STORE_UNAVAILABLE`(503,retryable)、`CONCURRENCY_LIMIT`(429,retryable)、
`INFERENCE_TIMEOUT`(504,retryable)。
本轮**未新增**错误码；`test_errors.py` 的双向锁（枚举 ↔ 锁定表必须双射）保持。

### 5.6 `request_id` / `library_revision` / `model_version`
- `request_id`：入站 `X-Request-Id` 合法则回显，否则服务端生成 uuid4 hex；**响应头与错误体均带**。
- `library_revision`：**所有**响应都带（一致快照）；**只**由真实创建/覆盖/删除递增
  （`_bump_revision` 调用点恰 2 处）。幂等重放、所有只读端点、schema 升级**绝不**递增。
- `model_version`：所有业务响应都带；`policy_version` 仅 search 带（本轮 `search-v1` → **`search-v2`**，
  因 decision 词表变更，使"哪个策略产生了这个判定"可审计）。

### 5.7 幂等登记语义（合同 §6.1）
| 情形 | 服务端 | Worker 映射 |
|---|---|---|
| `subject_id` 不存在 | **201** 创建，持久化 `correlation_id`/`provider_request_id`/`registered_at` | `success` |
| 已存在**且** `correlation_id` 相同 | **200** 幂等重放：返回既有登记（`replayed=true`），**不覆盖特征、不 bump revision** | `success` |
| 已存在**但** `correlation_id` 不同（或库中有值而请求缺失） | **409 `SUBJECT_ALREADY_EXISTS`** | `failed`（**绝不**静默覆盖） |
| `on_exists=overwrite` | **200** 覆盖并 bump revision、记录新对账键 | —— （受控后台专用，Worker 不得使用） |
| 超时/网络中断 | 客户端侧现象 | `timeout` → **必须**随后对账 |
| 5xx / `MODEL_*` / `STORE_UNAVAILABLE` | 错误信封 | `unknown` → 随后对账 |
| 其它 4xx | 错误信封 | `failed`（不可重试） |

**关键**：`correlation_id` 相同即视为**同一次逻辑登记** ⇒ "远端成功 + Worker 崩溃/超时"后重试
既不会产生第二个 subject，也不会被误报为冲突。这正是 `identity_enroll.py:173` 注释
「超时/未知 → 同 EntityId 对账，绝不生成另一 ID 盲重试」所需的服务端保证。
登记响应体键集（实测）：`subject_id`/`namespace`/`created`/`created_at`/`updated_at`/
`embedding_dim`/`model_version`/`quality`/`library_revision`/**`replayed`**/**`registered_at`**/
`request_id`；**两个对账键本身不回显**（其持久化由对账端点证明）。

### 5.8 鉴权与脱敏
- 除 `/v1/health`、`/live`、`/ready` 外全部需 `X-Internal-Token`（`auth.py:23-46`，
  常量时间比较，失败 **401 `UNAUTHORIZED`**，token 值从不回显）。
- 非 loopback 绑定且关闭鉴权/无 token → **启动期拒绝**（`config.py:197-222`）。
- `access_log=False`（`main.py:25`）+ 自有脱敏中间件按**路由模板**记录（`app.py:90-106,130-137`）
  ⇒ 展开路径中的 namespace/subject_id/**correlation_id** 均不入日志。
- 布尔配置只接受 `1/true/yes/on` 与 `0/false/no/off`，未知值 `ConfigError` 且**不回显被拒值**。

### 5.9 MVP 活体边界
`liveness.supported` **恒 false**（`quality.py:31-39`，`buffalo_l` 无活体模型）。
`/v1/verify` 在 `require_liveness=true` 时 → **501 `LIVENESS_UNSUPPORTED`**；
`/v1/compare` 与 `/v1/search` **不接受**该字段（`compare` 传入即忽略且恒报 `supported=false`）。
**绝不允许**伪造 `liveness.passed=true`，也**绝不**用检测分数或相似度冒充活体
（门禁实测：全 src 中 `passed: true`/`passed = True` 命中 **0**）。
⇒ Worker 适配层**不得**发送 `require_liveness`；其人脸结论属
**"照片比对，无防翻拍能力"**（`人脸服务调研:31,179`：身份相似度不证明现场性）。

---

## 6. 公共文件结论

| 项 | 结论 |
|---|---|
| 新增/修改公共迁移 | **无**。`backend/web-java/src/main/resources/db/migration/` 仍恰为 **V1 + V2**（门禁实测 2 个 `.sql`） |
| 修改公共 OpenAPI 契约 | **无**。`backend/contracts/**` 与基线 diff **0 文件** |
| 新增 Java `ErrorCode` | **无**（本轮不改任何 Java 文件） |
| 新增 `/api/**` 端点 | **无** ⇒ Java 文档覆盖率门禁 `ApiDocsCoverageIT` 不受影响 |
| 修改 Worker（D 域） | **无**。`backend/worker-python/**` 与基线 diff **0 文件** |
| 修改 A/C/D 任何文件 | **无**。`web-java`/`worker-python`/`contracts`/`acceptance`/`tests`/`doc`/`deploy` 与基线 `e57bc315` **各 diff 0 文件** |
| 本轮提交的实际写域 | **只** `backend/face-service`（9 文件）+ `backend/handoffs`（2 文件） |
| face-service 的 SQLite schema 变更 | 属**服务自有库**（`store.py` 自建表），与业务 PG 的 14 张表无关 ⇒ **不需要**任何公共迁移 |

---

## 7. 验证证据（全部 orchestrator 亲跑，非子任务自报）

### 7.1 测试
| 范围 | 结果 |
|---|---|
| face-service 全量 pytest（离线、FakeModel、临时库） | **188 passed / rc=0**（基线 144；`def test_` **116 → 160**） |
| 不变量 + 安全套件（extract/verify/subjects/health/config_security/access_log/errors/docs_disabled/auth/ready） | **94 passed** |
| `test_search.py`（词表变更后的既有套件） | **19 passed**；`def test_` **19→19（零删除）**、`assert` **116→122（净增 6）**；删除的 5 行**全部**是词表改名，未放宽任何断言 |
| 新增 `test_compare.py` / `test_registration.py` / `test_store_upgrade.py` / `test_search_v2_rulings.py` | 15 / 15 / 7 / 7 |
| Java 全量（revert 后） | **747 run / 0 / 0 / 18 skipped，BUILD SUCCESS rc=0，109 份 xml**（= 本轮前基线；本轮代码 SHA 上 Java diff 为 0，故未重建） |
| `compileall`（src + tests） | **rc=0** |

### 7.2 中央门禁：41 项 **ALL-PASS**
含：七个禁域与基线 diff 各 0 文件、迁移仍 V1+V2、无废弃 Java 合同文件复活、
`reliable_new` 存在、`no_match` 归零、`search-v2` 存在、`search-v1` 归零、
`/v1/compare` 与 `registrations/{correlation_id}` 路由已注册、`subjects` 含 `correlation_id` 列、
`PRAGMA table_info` 与 `ALTER TABLE subjects ADD COLUMN` 均在、
**decision 词表枚举恰为三个契约值且赋值点 ≥6、契约外值 0**、
extract 零写入判别力测试仍在、verify 不回落全库、活体门恰 2 处调用点、
**全 src 无伪造 `passed=true`**、文档面仍 404×3、`_bump_revision` 恰 2 处、
错误码双向锁在、`top_k` 下界 2（config 与 api 各 1）、
**`subjects` 相关 SQL 无缺 namespace 谓词者**、`access_log=False`、生产 fail-closed 守卫在、
`git diff --check` rc=0、文本文件行尾空白 0、无工件/venv 入 git、
新增行中 LTAI 形态 AK / `+86` 手机号 / 私钥块 / token-secret 赋值 / 64 位十六进制串命中**均 0**、
测试删除检测无 REDUCED。

门禁本身经过**判别力自测**：把 `reliable_new` 改成 `brand_new_person` 的变异被
decision 枚举门禁**检出**（`outside-contract=1`）；把 `search_candidates` 的 namespace 谓词去掉
被 SQL 门禁**检出**（1 处）；植入已删源文件的幻影 surefire 报告被 phantom 检测**报出**。

### 7.3 三项变异判别力（证明新测试"有牙"）
| 变异 | 结果 |
|---|---|
| A：空库改判 `reliable_new`（违背 §3.2 裁定） | **4 failed / 184 passed** |
| B：移除质量封顶（`if decision in ("matched","reliable_new")` → `== "matched"`） | **5 failed / 183 passed** |
| C：移除幂等重放短路（同 correlation_id 不再直接返回既有主体） | **6 failed / 182 passed** |

三处变异已按原文**精确逆向还原**，并以变异前记录的 sha256 **逐字节核验**：
`api.py 0c7f94622ed9166ba8bbbc20`、`store.py c4d4105157a581851f279139` 均 match，
全量恢复 **188 passed**、残留 `MUTANT` 标记 **0**。

> **如实记录我自己的还原脚本缺陷**：备份文件名（`api.orig`）与还原路径（`api.py.orig`）
> 不一致 ⇒ 三次还原全部失败，且脚本末尾先 `rm -rf` 删掉备份，三个变异一度**累积留在工作树**
> （当时全量 6 failed / 182 passed）。若未察觉即提交，将交付一个"把空库判成可靠新人 +
> 幂等登记失效"的服务——正是合同明令禁止的两件事。已逆向还原并逐字节核验；
> 教训写入 `.coordination/B-work/face-round/evidence-pivot/RESTORE-DEFECT.md`：
> 变异实验必须①备份名与被变异文件名严格一致并在还原前 `cmp` 校验；②**先还原、后清理** scratch；
> ③每轮变异后立即用 sha256 与基线比对，不要等全部跑完再统一还原。

### 7.4 运行时行为实测（离线、FakeModel、临时库、用毕删除）
- **幂等登记**：首次 `201 created=true replayed=false rev=1`；同 correlation_id 重放
  `200 replayed=true`、**rev 未变**、`updated_at` 未变（特征未被覆盖）、
  且用**原图**搜索仍 `matched`（证明库里存的还是原特征）；不同 correlation_id → `409`；
  不传 correlation_id 的旧调用 → `201`/重复 `409`（逐字兼容）；`overwrite` → `200` 且 rev 递增。
- **对账查询**：命中 → `status=registered` + 7 键；`entity_id` 或 `provider_request_id` 不符 →
  `not_found`；未知 correlation → `not_found`（200）；幽灵 namespace → `404 NAMESPACE_NOT_FOUND`
  且**未创建**该 namespace；**零写入**（rev 不变）；最小披露（无 embedding/quality/bbox/
  det_score/candidates/subjects/namespace）。
- **`/v1/compare`**：同图 `matched=true similarity=1.0`；异图 `matched=false similarity=0.0`；
  `threshold=0.999` 生效；非法阈值 `400`；缺 `image_b` `400`；空白图 `400 NO_FACE`；
  `require_liveness=true` **被忽略**且恒报 `supported=false`；**零写入**（rev 4→4）。
- **search 词表**：命中 → `matched` + `subject_id` + `policy=search-v2`；非空库无关图 →
  **`reliable_new`** + `no_candidates_above_threshold` 且**无** `subject_id`/`similarity`；
  **空库 → `uncertain` + `empty_library`**；未知 ns → `404`；`top_k=1` → `400`（下界 2）。
- **响应键集逐键核验**：四个端点的禁键命中均为 `[]`；register 重放**不回显** correlation_id；
  四者原始 JSON 中**均无 64 维向量形态**（长度 223–1862）。
- **原地升级**：真实构造旧 schema 库（无三列）+ 一条既有行 → `initialize()` → 三列补齐、
  索引创建、**既有行与其 embedding 字节级保留**、`library_revision` 仍为 7（升级不是库变更）、
  连跑三次幂等（无重复列）、升级后旧端点与新端点均可用；`EXPLAIN QUERY PLAN` 证明对账查询
  命中 `idx_subjects_namespace_correlation`。

### 7.5 资源与边界
端口 18083/18084/8010 空闲；无遗留 JVM；`mvp-b-pg` Up（`mvp_b_dev`/`postgres`/`swagger_preview`
三库完好，**未清库或卷**）；测试日志无真实网络引用（对已部署主机地址、其服务端口与 SSH 别名三项模式的命中均为 **0**）；
`insightface`/`onnxruntime`/`cv2` **未导入**（全程 FakeModel + 合成 PIL 图，无真实人脸、无网络）；
未部署、未 ssh、未触碰远端与共享 8002/8003；未读取或输出任何真实凭据；
`application-local.*` 在工作树 **0 文件**。

---

## 8. 剩余 blocker 与待裁定项

### 8.1 真实阻塞
1. **已部署实例须重新部署**：本轮改了服务端 schema（`subjects` 补三列 + 索引）。
   `initialize()` 会**原地升级**（不删库），但升级只在服务重启后发生。
   `deploy/deploy.sh` 已含 `ExecMainPID` 变更断言并以 `/ready` 为门禁（防"静默跑旧代码"）。
   **由根执行**；B 不部署、不 ssh、不触碰远端。
2. **D 需实现适配层**：按合同 §8 实现 `InsightFaceAdapter` 并接入 `build_face_port` 新取值
   （建议 `insightface`）。B 不改 Worker。D phase 1 已 608 passed，等的就是这份冻结合同。

### 8.2 须由总协调/根裁定
3. **既有 Java 人脸边界是否也要移除**（§2.3）：它属更早已交付、经 Oracle 通过并已并入 dev 的
   基线，不含用户列出的任何移除目标 ⇒ 未擅自扩大 revert 范围。
4. **A 域两处不一致**（沿用上轮取证，未改）：`JobEnqueuer.identityNamespaceOwnerFor`(`:127-129`)
   是 **per-subject 死代码**（全仓调用方 0），`contracts/decisions-notes.md:33` 亦写 per-subject，
   而 Python 实现与 `后端详细设计:736` 都是 **namespace 级** ⇒ 若将来误用会破坏
   `uq_job_identity_enroll` 的 namespace 级串行化。
5. **E 域影响**：E 的验收有 6 处依赖 `identity.enroll`（其中 `cd_chain.py:639,688` 的 **CD-06
   断言该 job succeeded**）⇒ 若 D 退役 `identity.enroll`，E 的 CD-06 会失败。属 E 域，B 未改。
6. **`/v1/compare` 接受客户端 `threshold` 而 search 不接受**这一不对称是否可接受（已交 Oracle 裁定）。

### 8.3 持续披露的边界（非本轮新增）
7. **阈值全部未经标定** ⇒ 标定前不得开启真实自动建档（`后端详细设计:663` 的 PoC 门禁）。
8. **无活体能力** ⇒ MVP 人脸结论属"照片比对，无防翻拍能力"；护理准入在活体落地前恒
   fail-closed（503）。生产启用真实 1:1 还需总协调授权修改 `CareFaceVerifierProductionGuard`。
9. **`reliable_new` 不等于"算法证明是新人"**；消费方必须保留自己的对账与门禁。

---

## 9. 本轮 orchestrator 自身缺陷记录（如实）

1. **变异还原脚本命名不一致**（§7.3）⇒ 三个变异一度累积留在工作树；已逆向还原并 sha256 逐字节核验。
2. **中央门禁三处自身缺陷**：`liveness` 那条用多文件 `grep -c` 得到 `file:0` 而非总数；
   `access_log` 匹配串写死 `access_log=False` 而真实写法是 `"access_log": False,`；
   namespace 隔离那条 awk 跨行累加逻辑不可靠 ⇒ 改为 python 按 SQL 字面量切分，
   并**再修一次**：Python 隐式字符串拼接（`"SELECT … " "WHERE namespace = ?"`) 会让只捕获第一段
   的检查器误报缺谓词 ⇒ 先合并相邻字面量再提取。修后自测：`store_good` → 0、
   刻意去掉 namespace 谓词的 `store_bad` → **1（检出）**。
3. **5 条门禁的"恰好 1 次"假设错误**（`reliable_new`=3、`search-v2`=3、路由=2、
   `PRAGMA`=2、`ALTER TABLE`=2）⇒ 恒失败的门禁比没有门禁更糟，已改为 `>=1` 语义，
   并把最该有效的 **decision 词表枚举**从只匹配 1/6 个赋值点修正为覆盖全部三种赋值形式
   （旧正则漏掉 5 处 `decision, ambiguous = "x", False` 元组赋值）。
4. **活体探针两次崩溃均因我未先读签名**：先假设 `create_app(Settings)`（实为 keyword-only），
   再用 `Settings.from_env()`（会触发生产守卫；conftest 的权威方式是直接构造 `Settings(...)`）。
5. **测试里两处凭猜测写错**：`settings.model_copy(...)`（`Settings` 是普通 dataclass，
   既有范式是 `dataclasses.replace`）；`client.app.state.settings`（真实属性是 `app.state.face`，
   既有范式是请求 `settings` fixture 后用 `FaceStore(settings.db_path)`）。
   另有一处**测试用例设计缺陷**：断言"未知 correlation → 200 not_found"时未先创建 namespace，
   实际命中 404 `NAMESPACE_NOT_FOUND` 分支 ⇒ 修正用例（不是改实现），并注明两个分支各自的覆盖者。
6. **一次工具调用被拒**（正当）：脚本中 `cd backend/face-service && … && cd ..` 后仍用
   `backend/face-service/...` 相对路径，使解析越出 mvp-b 工作树 ⇒ 改为全程用 `workdir` 参数
   或从工作树根出发的相对路径，并在脚本开头加 cwd 断言。
7. **一次 grep 自匹配假象**：`pgrep -cf`/`ps | grep '[p]ytest'` 的模式串会匹配到我自己的
   bash 命令行，一度让我以为有 pytest 在跑 ⇒ 改为按 `comm` 字段精确普查 + 读 `/proc/<pid>/cmdline`。
