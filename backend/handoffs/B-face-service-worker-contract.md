# 冻结合同：Worker `FacePort` ↔ `backend/face-service`（InsightFace-for-openvela）

**状态**：**已冻结**（orchestrator，2026-09-16，方案反转后）。
**消费方**：D 的 Python Worker（`handlers/dshared/providers.py` 的 `FacePort` 协议）。
**生产方**：B 的 `backend/face-service`（独立人脸服务，已部署于 dev.ai-skin 的用户级 systemd unit）。
**本轮方案**：用户已明确授权**改回 Python Worker 对接 InsightFace**；Java 直连方案已用普通 revert
提交完整移除（见 §9）。**B 不修改 Worker 的任何文件**——本文档只冻结服务端合同，
D 据此实现 `InsightFaceAdapter`（`build_face_port` 的新取值）。

> 本文档所有 `文件:行` 均由脚本或直读核实。D 侧文件为**只读引用**，B 未修改任何
> `backend/worker-python/**` 文件。

---

## 1. 权威消费契约（D 侧现状，逐字取证，B 不得要求其改变）

`backend/worker-python/src/mvp_worker/handlers/dshared/providers.py`：

| 类型/方法 | 定义位置 | 形状 |
|---|---|---|
| `QualityResult` | `:66-69` | `status: "accepted"\|"needs_retake"`、`required_views: tuple[str,...] = ()` |
| `SamePersonResult` | `:72-74` | `ok: bool` |
| `SearchResult` | `:77-80` | `classification: "matched"\|"uncertain"\|"ambiguous"\|"reliable_new"`、`face_subject_ref: Optional[str] = None` |
| `RegisterResult` | `:83-85` | `status: "success"\|"timeout"\|"unknown"\|"failed"` |
| `RegistrationQueryResult` | `:88-90` | `status: "registered"\|"not_found"\|"unknown"` |
| `FacePort.quality(images: dict[str,bytes])` | `:118` | 三视角字典入参 |
| `FacePort.same_person(images: dict[str,bytes])` | `:119` | 三视角字典入参 |
| `FacePort.search_1n(namespace, images)` | `:120` | 返回 `SearchResult` |
| `FacePort.register_person(namespace, entity_id, images, correlation_id, provider_request_id)` | `:121-128` | 返回 `RegisterResult` |
| `FacePort.query_registration(correlation_id, provider_request_id, *, namespace=None, entity_id=None)` | `:129-136` | 返回 `RegistrationQueryResult` |
| 异常 | `:52-57` | `ProviderUnavailable`（瞬时可重试）、`ProviderNotActivated`（未激活，可重试、不伪造结果）；`ProviderConfigError` 由 `dconfig` 定义并重导出 |

**Worker 的映射规则（决定服务端必须提供什么）**：
- `assessment_analyze.py:359` 取 `search.classification`；`:361` `dependency_failed` → 可重试；
  `:369` `uncertain`/`ambiguous` → 补拍 `IDENTITY_UNCERTAIN`（`required_views` = 全三视角）；
  `:377` `reliable_new` → 先用 `candidate_entity_id(ns, assessment_id)` 对账 PG（`:381-389`），
  已有成员则直接发布、否则 `_handle_reliable_new` 入队登记；`:398` `matched` →
  用 `face_subject_ref` 解析成员（`:400-401`），查不到则 `MEMBER_NOT_VISIBLE` 可重试；
  **`:415-420` 任何其它取值 → `DEPENDENCY_UNAVAILABLE`（"unexpected identity classification"）**。
  ⇒ **服务端 `decision` 的取值必须落在这四个词之内**，否则 Worker 会把它当成依赖故障。
- `identity_enroll.py:173-200` 的幂等/对账语义（**这是本合同 §6 的权威依据**）：
  登记在**锁外**调用；`ProviderUnavailable` → `_reconcile`；`register` 返回
  `status ∈ {success, timeout, unknown}` ⇒ **必须**再 `query_registration`，
  其 `status != "registered"` 则 `ENROLLMENT_RECONCILE_PENDING`（可重试）；
  `status == "failed"` ⇒ `ENROLLMENT_FAILED`（终态）。
  注释明写「超时/未知 → **同 EntityId 对账，绝不生成另一 ID 盲重试**」。

---

## 2. 承载与部署事实（为什么不需要任何公共迁移）

- face-service 的持久化是**它自己的 SQLite**（`src/face_service/store.py` 的 `subjects` /
  `namespaces` / `library_meta` 三表，由 `initialize()` 自建），**与业务 PG 的 14 张表无关**。
  ⇒ 本轮给它补列**不需要** A 域独占的 `backend/web-java/src/main/resources/db/migration/`，
  也**不触碰**任何公共 Schema。
- 服务只绑内网 `10.3.6.163:8010`，受 `X-Internal-Token` 保护（`auth.py:23-46`），
  `/v1/health`、`/live`、`/ready` 为公开探针。
- **部署需由根执行**：本轮改了服务端 schema（§6.3 的列），已部署实例必须重新部署才会生效。
  `deploy/deploy.sh` 已含 `ExecMainPID` 变更断言（防"静默跑旧代码"）并以 `/ready` 为部署门禁。
  **B 本轮不部署、不 ssh、不触碰远端。**

---

## 3. 冻结端点总表（本轮后的完整服务端能力）

| 端点 | 鉴权 | 写库 | 本轮变化 | 对应 FacePort |
|---|---|---|---|---|
| `GET /v1/health` | 否 | 否 | **不变** | ——（运维） |
| `GET /live` | 否 | 否 | 不变（本轮已有） | ——（探针） |
| `GET /ready` | 否 | 否 | 不变（本轮已有） | ——（探针） |
| `POST /v1/extract` | 是 | **零写** | 不变 | ——（原语） |
| `POST /v1/quality` | 是 | **零写** | 不变（单图原语） | `quality`（适配层按视角逐次调用后聚合 `required_views`） |
| `POST /v1/compare` | 是 | **零写** | **新增** | `same_person` |
| `POST /v1/verify` | 是 | **零写** | 不变（严格 1:1，只查指定 subject） | 护理/指定成员核验 |
| `POST /v1/namespaces/{ns}/search` | 是 | **零写** | **`decision` 词表变更**（§4） | `search_1n` |
| `POST /v1/namespaces/{ns}/subjects` | 是 | **是** | **幂等语义 + 持久化对账键**（§6） | `register_person` |
| `GET /v1/namespaces/{ns}/subjects/{subject_id}` | 是 | 否 | 不变 | ——（只读存在性） |
| `GET /v1/namespaces/{ns}/registrations/{correlation_id}` | 是 | 否 | **新增** | `query_registration` |
| `DELETE /v1/namespaces/{ns}/subjects/{subject_id}` | 是 | **是** | 不变（幂等删除） | ——（受控后台） |
| `GET /v1/namespaces/{ns}/info` | 是 | 否 | 不变 | ——（只读自省） |

**设计裁定：服务端只提供单图原语，多视角聚合由 Worker 适配层完成。**
理由：①"哪些视角必需"是业务策略（D 的 `REQUIRED_VIEWS_ALL`，`dshared/constants.py:18`），
不属于算法服务；②单图原语可独立测试、独立失败、独立重试；③避免服务端持有业务视图命名。
适配层因此需要：`quality` 对每个视角各调一次 `/v1/quality`，把 `min_acceptable=false` 的视角
收集为 `required_views`；`same_person` 调 `/v1/compare` 做两两比较（或按 D 选择的策略）；
`search_1n` 用主参考视角（建议 `front`）调 `/v1/namespaces/{ns}/search`。

---

## 4. `POST /v1/namespaces/{namespace}/search`（冻结；**本轮唯一破坏性变更**）

### 4.1 请求
`multipart/form-data` 或 JSON，与 `/v1/extract`、`/v1/verify` **完全同一套**解码路径
（`_read_image_payload`）：字段 `image`（binary | base64 | data-url）、可选 `media_type`、
可选 `top_k`（整数，**2..10**，缺省用服务端 `FACE_SVC_SEARCH_TOP_K=5`）。
**不接受任何客户端阈值**（依据 `人脸服务调研与推荐方案-V1-MVP.md:131,134`）。

### 4.2 `decision` 词表（**冻结为三值，与用户授权一致**）
`decision ∈ {"matched", "uncertain", "reliable_new"}`

| decision | 触发条件（按顺序判定，前置错误优先） | 响应附加 |
|---|---|---|
| —— | 0 张脸 → `NO_FACE`；多张脸 → `MULTI_FACES_AMBIGUOUS`；解码失败 → `IMAGE_DECODE_FAILED`；模型/推理故障 → 既有 `MODEL_*`/`INFERENCE_TIMEOUT`。**namespace 不存在不再是 404**，而是按"只读空快照"处理（见下方裁定 1） | 错误信封 |
| `matched` | `best >= search_match_threshold` **且** 与次优不同 subject 之差 `>= search_margin` **且** 质量 `min_acceptable=true` | `subject_id` + `similarity` |
| `uncertain` | ①`best >= search_match_threshold` 但 margin 不足（`ambiguous=true`）；②`best` 落在 `[match_threshold - uncertain_band, match_threshold)`；③质量不足（`min_acceptable=false`，即使相似度达标也**至多** uncertain）；④**namespace 存在但库为空**（`subject_count == 0`，`reasons` 含 `empty_library`） | 无 `subject_id`、无 `similarity` |
| `reliable_new` | 单脸、质量合格，且**二者之一**：①库**非空**且 `best < search_match_threshold - search_uncertain_band`；②库**为空或 namespace 尚不存在**（`reasons` 含 `empty_library`） | 无 `subject_id`、无 `similarity` |

**两处裁定（必须写进 D 的实现说明）**：
1. **空库/缺 namespace → 质量合格时返回 `reliable_new`（`reasons` 含 `empty_library`）；质量不合格仍返回 `uncertain`**。

   > **修订记录（Oracle 第二十九轮 BLOCKER）**：本节最初裁定为"空库恒返回 `uncertain`"，
   > 理由是"库为空更可能是未初始化/被误清，判新人会批量建档"。该裁定**是错的，已推翻**：
   > 每个 namespace 都必然从空库开始，而 Worker 只在 `reliable_new` 时才入队
   > `identity.enroll`（`assessment_analyze.py:377-388`）、对 `uncertain` 只会要求补拍
   > （`:369-375`），而**补拍不可能让空库变非空** ⇒ 首个成员永远无法经业务流程建档
   > （首次入库死锁）。把"禁止自动建档"的业务门禁放进只读算法端点，是**放错了层**：
   > 该门禁的权威位置是 `后端详细设计-V1-MVP.md:663` 的 PoC 门与 Worker 自己的
   > PostgreSQL 对账（`:381-389`）。
   > 同时 search 对**不存在**的 namespace 也不再返回 404，而是按只读空快照处理
   > （search 从不创建任何东西，故仍是只读；404 同样会造成上述死锁）。
   > `reasons` 恒定携带 `empty_library`，使消费方与审计仍能区分"库非空但无候选达阈值"
   > 与"库本来就是空的"。
2. **`reliable_new` 的语义边界**：它表示"**在本 namespace 内以 `policy_version` 所述策略搜索、
   单脸、质量合格、最高相似度明确低于阈值**"，**不**表示算法能证明这是新人类。
   依据 `后端详细设计-V1-MVP.md:657`「歧义不归档，**未命中只成为新人候选**」与
   `:663`「自动新人判定阈值、活体条件**未通过 PoC 则不得开启真实自动登记**」。
   ⇒ **D 侧在 PoC 门禁通过前不得据此开启自动建档**；`assessment_analyze.py:377-389` 现有的
   "先对账 PG、已有成员则不重复建档"必须保留。

**为什么不产出 `ambiguous`**：Worker 在 `:369` 把 `uncertain` 与 `ambiguous` **同等**处理
（都走补拍 `IDENTITY_UNCERTAIN`），故服务端用 `decision="uncertain"` + `ambiguous=true` +
`reasons=["ambiguous_top_candidates"]` 表达即可，**无信息损失**，且严格落在用户授权的三值词表内。

### 4.3 响应（冻结）
```jsonc
{
  "decision": "matched" | "uncertain" | "reliable_new",
  "subject_id": "…",          // **仅** matched；其余情形该键必须**不存在**（不是 null）
  "similarity": 0.7321,       // **仅** matched
  "ambiguous": false,          // margin 不足时为 true
  "quality": { … },            // 既有质量块（含 liveness.supported=false）
  "reasons": ["…"],            // 诊断用短码：empty_library / ambiguous_top_candidates /
                               //   similarity_in_uncertain_band / quality_below_minimum /
                               //   no_candidates_above_threshold
  "subject_count": 12,
  "top_k": 5,
  "policy_version": "search-v2",   // **本轮由 search-v1 提升**（decision 词表变更）
  "model_version": "…",
  "library_revision": 7,
  "request_id": "…"
}
```
**禁止出现**：候选列表、任何非 matched 的 `subject_id`、embedding/特征向量、已登记主体的
bbox/det_score/参考照引用、**数值阈值本身**（只给 `policy_version`）。
成功恒 **200**（三种 decision 都是业务判定，不是错误）。

### 4.4 阈值与 top-k（服务端固定策略）
| env 键 | Settings 字段 | 默认 | 校验 |
|---|---|---|---|
| `FACE_SVC_SEARCH_MATCH_THRESHOLD` | `search_match_threshold` | **0.60** | `0 < x <= 1` |
| `FACE_SVC_SEARCH_UNCERTAIN_BAND` | `search_uncertain_band` | **0.10** | `0 <= x < match_threshold` |
| `FACE_SVC_SEARCH_MARGIN` | `search_margin` | **0.05** | `0 <= x <= 1` |
| `FACE_SVC_SEARCH_TOP_K` | `search_top_k` | **5** | 整数 **2..10** |
| `FACE_SVC_VERIFY_THRESHOLD` | `verify_threshold` | **0.40** | `0 < x <= 1`（1:1） |

**全部为未经标定的保守占位**（`人脸服务调研:100` 已明确这类数值"不是百分比可信度"）。
1:N 默认 **0.60 严于** 1:1 的 0.40：误接受风险随库规模上升，无标定数据时往更严取值是 fail-closed。
`top_k` 下界为 **2**（`top_k=1` 会使 margin 歧义保护结构性失效）。
非法值一律 `ConfigError` fail fast 且**不回显被拒值**。**阈值标定前不得开启自动建档。**

---

## 5. `POST /v1/compare`（**新增**，图↔图比较，零写入）—— 支撑 `same_person`

### 5.1 请求
与既有端点同一套解码路径，但接受**两张**图：
`image_a` / `image_b`（各自 binary | base64 | data-url），可选 `media_type_a` / `media_type_b`，
**不接受 `threshold`**：阈值一律取服务端 `FACE_SVC_VERIFY_THRESHOLD`，客户端传入的值被**忽略**
（不是"校验后接受"）。

> **修订记录（Oracle 第二十九轮 IMPORTANT）**：本节最初允许本端点覆盖 `threshold`，理由是
> "无库参与的一次性比对，不存在调低阈值绕过库策略的风险"。该理由**不成立，已推翻**：
> threshold 直接决定 `same_person` 结论，允许降到 `0.0` 就等于允许调用方把任意两张无关图
> 判为同人；"不查库"与此无关。且 `FacePort.same_person(images)`（`providers.py:119`）
> **本来就没有 threshold 参数**，无任何消费方需要它。改为服务端固定后，compare 与 search
> 的口径也一致了（两者都绝不接受客户端阈值）。
> **如实披露的既有不对称**：`/v1/verify`（上一轮已审已批准的代码，`api.py:426-431`）
> **仍**接受客户端 `threshold`（0..1 任意值）。本轮**未擅自扩大范围**去改它，
> 是否需要同样收紧由总协调裁定。

### 5.2 响应（冻结）
```jsonc
{
  "matched": true,
  "similarity": 0.8123,
  "threshold": 0.40,
  "face_count_a": 1, "face_count_b": 1,
  "quality_a": { … }, "quality_b": { … },
  "liveness": { "supported": false, "reason": "buffalo_l has no liveness model" },
  "reasons": [],                 // 例如 quality_below_minimum
  "model_version": "…", "library_revision": 7, "request_id": "…"
}
```
**判定规则（保守）**：任一图 0 张脸 → `NO_FACE`；任一图多张脸 → `MULTI_FACES_AMBIGUOUS`
（**绝不**自动取最大脸）；解码失败 → `IMAGE_DECODE_FAILED`；
**任一图质量 `min_acceptable=false` ⇒ `matched` 至多为 `false`**（`reasons` 含 `quality_below_minimum`）。
**零写入**：不查库、不建 namespace、不 bump `library_revision`（响应中的 revision 仅为审计快照）。
**不含活体**：响应带 `quality_*.liveness.supported=false`；本端点是**照片比对，无防翻拍能力**，
不得用于任何要求现场性的准入。

### 5.3 与 `/v1/verify` 的区别（不得混用）
| | `/v1/compare` | `/v1/verify` |
|---|---|---|
| 比对对象 | 两张**探针**图 | 探针图 vs **已登记** subject 的参考特征 |
| 是否查库 | **否** | 是（只读指定 subject） |
| `require_liveness` | **不接受该字段** | 接受；为 true 且服务无活体 → **501 `LIVENESS_UNSUPPORTED`** |
| 用途 | `same_person`（三视角确认同人） | 指定成员 1:1 核验 |

---

## 6. 幂等登记与对账（`register_person` / `query_registration` 的服务端语义）

### 6.1 `POST /v1/namespaces/{ns}/subjects`（**扩展**，保持向后兼容）
新增**可选**字段：`correlation_id`、`provider_request_id`（均为字符串，建议 UUID 文本；
由 Worker 用 `dshared/constants.py:31-32,44-45` 的确定性派生得到，跨重试稳定）。
既有字段不变：`subject_id`（必填）、`image`、可选 `on_exists`（`conflict`|`overwrite`，缺省 `conflict`）、
可选 `require_liveness`（为 true → 501，**既有行为不变**）。

**幂等规则（冻结，逐条对应 Worker 的需要）**：
| 情形 | 服务端响应 | Worker 映射 |
|---|---|---|
| `subject_id` 不存在 | **201** 创建，持久化 `correlation_id`/`provider_request_id`/`registered_at` | `RegisterResult("success")` |

> 登记响应体（201/200 同形）实测键集：`subject_id`、`namespace`、`created`、`created_at`、
> `updated_at`、`embedding_dim`、`model_version`、`quality`、`library_revision`、**`replayed`**、
> **`registered_at`**、`request_id`。**两个对账键本身不回显**（幂等重放时调用方已持有它们），
> 其持久化由 `GET …/registrations/{correlation_id}` 证明。
| `subject_id` 已存在**且** `correlation_id` 与请求相同 | **200** 幂等重放：返回既有登记（`subject_id`/`library_revision`/`registered_at`/`replayed=true`），**不覆盖特征、不 bump revision** | `RegisterResult("success")` |
| `subject_id` 已存在**但** `correlation_id` 不同（或缺失而库中有值） | **409 `SUBJECT_ALREADY_EXISTS`** | `RegisterResult("failed")`（**绝不**静默覆盖） |
| `on_exists=overwrite` 显式要求覆盖 | **200** 覆盖并 bump revision（既有行为，仅供受控后台；Worker **不得**使用） | —— |
| 超时/网络中断 | 客户端侧现象 | `RegisterResult("timeout")`，随后**必须** `query_registration` 对账 |
| 5xx / `MODEL_*` / `STORE_UNAVAILABLE` | 错误信封 | `RegisterResult("unknown")`，随后对账 |
| 4xx 参数/鉴权/媒体类 | 错误信封 | `RegisterResult("failed")`（不可重试） |

**关键**：`correlation_id` 相同即视为**同一次逻辑登记**，因此"远端成功 + Worker 崩溃/超时"后重试
不会产生第二个 subject，也不会被误报为冲突。这正是 `identity_enroll.py:173` 注释
「超时/未知 → 同 EntityId 对账，绝不生成另一 ID 盲重试」所需的服务端保证。

**唯一性由数据库强制**（修订自 Oracle 第二十九轮 IMPORTANT）：索引
`idx_subjects_namespace_correlation` 是 **`UNIQUE` 部分索引**
（`ON subjects(namespace, correlation_id) WHERE correlation_id IS NOT NULL`），故一个
`correlation_id` 在同一 namespace 内**至多绑定一个 subject**；否则对账查询的 `fetchone()`
会在两行之间任意取一行，使"同一逻辑登记"的承诺失效。`register` 在写入前显式检查该
correlation 是否已绑定**其它** subject，命中即 **409**（消息 `correlation_id is already
bound to a different subject`，`details` 只含 `namespace`，**不回显**另一个 subject_id），
以免唯一索引抛出裸 `IntegrityError` 而被渲染成 500。旧库若已存在重复对，
`initialize()` 会以 `STORE_UNAVAILABLE` **明确拒绝启动**并只报重复**组数**（绝不回显 id 本身），
而不是让 `CREATE UNIQUE INDEX` 抛出难以诊断的 SQLite 错误。

### 6.2 `GET /v1/namespaces/{ns}/registrations/{correlation_id}`（**新增**，只读对账）
- 可选查询参数 `provider_request_id`、`entity_id`（= `subject_id`）用于**加强校验**。
- 响应：
```jsonc
// 找到（且若给了 entity_id / provider_request_id 则必须一致，否则视为 not_found）
{ "status": "registered", "subject_id": "…", "correlation_id": "…",
  "provider_request_id": "…", "registered_at": "2026-09-16T04:05:06Z",
  "library_revision": 7, "request_id": "…" }
// 未找到
{ "status": "not_found", "request_id": "…" }
```
- **`status` 只有 `registered` / `not_found` 两值**；`unknown` **不由服务端产出**——
  它是 Worker 在**传输层失败**（超时/5xx/无法解析）时自行映射的值
  （`RegistrationQueryResult` 的 `unknown` 属客户端状态，服务端伪造它反而会掩盖故障）。
- **零写入**、不 bump revision。namespace 不存在 → **404 `NAMESPACE_NOT_FOUND`**。
  （与 search 不同：search 需要允许"库尚不存在"时也能给出可据以首次建档的判定，
  而对账查询针对的是**已经发起过**的登记，其 namespace 必然已存在，故 404 是正确的
  "你查错了地方"信号，不会造成任何死锁。）
- **最小披露**：绝不返回 embedding、参考照引用、其它 correlation 的登记、或库内主体清单。

### 6.3 服务端存储变更（**B 自有 SQLite，不涉及公共迁移**）
`subjects` 表新增三列（`store.py` 的 DDL 与 `initialize()`）：
`correlation_id TEXT`、`provider_request_id TEXT`、`registered_at TEXT`（均**可空**，保证既有行兼容）；
新增索引 `idx_subjects_namespace_correlation ON subjects(namespace, correlation_id)`。
**已存在的库必须能原地升级**：`initialize()` 需用 `PRAGMA table_info(subjects)` 检测缺列并
`ALTER TABLE ADD COLUMN`（幂等、可重复执行），**不得**要求删库重建
（远端已部署实例含既有数据，删库＝不可接受的破坏性操作）。
`library_revision` 语义不变：**只**由真实创建/覆盖/删除递增；幂等重放与所有只读端点**绝不**递增。

---

## 7. 通用约定（全端点）

- **鉴权**：除 `/v1/health`、`/live`、`/ready` 外全部需要 `X-Internal-Token`
  （`auth.py:23-46`，常量时间比较，失败 401 `UNAUTHORIZED`；token 值从不回显）。
  非 loopback 绑定且关闭鉴权 → **启动期拒绝**（`config.py:197-222`）。
- **图片限制**：`FACE_SVC_MAX_BODY_BYTES`（既有）；媒体类型经既有白名单校验；
  解码统一走 `decode_rgb_image`。**绝不接受文件路径或 URL**（只接受字节/base64/data-url）。
- **超时与并发**：`FACE_SVC_INFERENCE_TIMEOUT_SECONDS`、`FACE_SVC_MAX_CONCURRENCY`（既有，
  超限 → 429 `CONCURRENCY_LIMIT`，`retryable=true`；推理超时 → 504 `INFERENCE_TIMEOUT`，`retryable=true`）。
  **建议 Worker 侧客户端超时 ≥ 服务端推理超时**，否则客户端超时会把仍在进行的推理误判为 `timeout`
  （这由 §6.1 的对账语义兜住，不会造成重复登记）。
- **错误码表（18 个，双向锁定）**：`NO_FACE`(400)、`MULTI_FACES_AMBIGUOUS`(400)、
  `IMAGE_DECODE_FAILED`(400)、`INVALID_REQUEST`(400)、`UNAUTHORIZED`(401)、
  `SUBJECT_NOT_FOUND`(404)、`NAMESPACE_NOT_FOUND`(404)、`SUBJECT_ALREADY_EXISTS`(409)、
  `IMAGE_TOO_LARGE`(413)、`UNSUPPORTED_MEDIA_TYPE`(415)、`QUALITY_INSUFFICIENT`(422)、
  `LIVENESS_UNSUPPORTED`(501)、`INTERNAL_ERROR`(500)、`MODEL_UNAVAILABLE`(503,retryable)、
  `MODEL_NOT_LOADED`(503,retryable)、`STORE_UNAVAILABLE`(503,retryable)、
  `CONCURRENCY_LIMIT`(429,retryable)、`INFERENCE_TIMEOUT`(504,retryable)。
  统一信封 `{"error":{code,message,retryable,request_id[,details]}}`。
  **`details` 绝不包含** token、图片字节、embedding、候选列表、库内容或**其它**主体的标识。
  它**可以**回显**调用方本次请求自己传入**的标识（如 404 时的 `namespace`/`subject_id`）——
  调用方本来就知道这些值，回显不构成泄漏；`error_body`(`errors.py:148-149`) 确实外发 `details`。
  （修订自 Oracle 第二十九轮 SUGGESTION：原措辞"绝不包含 namespace 取值、subject_id 取值"过强，
  与既有 7 处 404 响应的实际行为不符。）
- **`request_id`**：入站 `X-Request-Id` 合法则回显，否则服务端生成 uuid4 hex；响应头与错误体均带。
- **`library_revision`**：所有响应都带（一致快照），**只**由创建/覆盖/删除递增。
- **日志脱敏**：`access_log=False`（`main.py:25`）+ 自有脱敏中间件按**路由模板**记录
  （`app.py:90-106,130-137`）⇒ 展开路径中的 namespace/subject_id/correlation_id **不入日志**。
- **文档面已关闭**：`/docs`、`/redoc`、`/openapi.json` 均 404（`app.py:68-70`），
  消除未鉴权的内部协议 schema 暴露面。
- **活体（MVP 边界）**：`liveness.supported` **恒 false**（`quality.py:31-39`，
  `buffalo_l` 无活体模型）。`/v1/verify` 在 `require_liveness=true` 时 → **501
  `LIVENESS_UNSUPPORTED`**；`/v1/compare` 与 `/v1/search` **不接受**该字段。
  **绝不允许**伪造 `liveness.passed=true`，也**绝不**用检测分数或相似度冒充活体。
  因此 Worker 适配层**不得**发送 `require_liveness`；其人脸结论属
  **"照片比对，无防翻拍能力"**（依据 `人脸服务调研:31,179`：身份相似度不证明现场性）。

---

## 8. Worker 适配层实现指引（D 侧，B 不实现、不修改）

`build_face_port`（`dshared/providers.py:779-786`，现取值域 `double|aliyun_face`）需新增取值
（建议 `insightface`），并受既有生产守卫约束（`double` 在生产被禁，`:725-729`）。建议映射：

| FacePort 方法 | 调用 | 映射 |
|---|---|---|
| `quality(images)` | 对每个视角 `POST /v1/quality` | 全部 `min_acceptable=true` → `QualityResult("accepted", ())`；否则 `QualityResult("needs_retake", <不合格视角元组>)`。**任一视角调用失败 → 抛 `ProviderUnavailable`**，绝不把失败当合格 |
| `same_person(images)` | `POST /v1/compare`（按 D 选定策略两两或对着主视角比） | 全部 `matched=true` → `SamePersonResult(True)`；任一 `false` → `False`；调用失败 → `ProviderUnavailable` |
| `search_1n(ns, images)` | `POST /v1/namespaces/{ns}/search`（建议用 `front`） | `decision` **直接**用作 `classification`（三值均在 Worker 词表内）；`matched` 时 `face_subject_ref = subject_id`，其余为 `None`。传输失败 → `ProviderUnavailable`；**4xx 参数/鉴权类 → `ProviderConfigError`**（不可重试），**5xx/超时 → `ProviderUnavailable`**（可重试） |
| `register_person(ns, entity_id, images, correlation_id, provider_request_id)` | `POST /v1/namespaces/{ns}/subjects`，`subject_id=entity_id`，带两个对账键，**不传 `on_exists`**（用服务端默认 `conflict`）、**不传 `require_liveness`** | 201/200 → `success`；409 `SUBJECT_ALREADY_EXISTS` → `failed`；客户端超时 → `timeout`；5xx/`MODEL_*`/`STORE_UNAVAILABLE` → `unknown`；其它 4xx → `failed` |
| `query_registration(correlation_id, provider_request_id, *, namespace, entity_id)` | `GET /v1/namespaces/{ns}/registrations/{correlation_id}?provider_request_id=…&entity_id=…` | `status="registered"` → `registered`；`"not_found"` → `not_found`；传输失败/无法解析 → `unknown` |

**硬性纪律（与本项目既有裁定一致）**：
- **真实服务故障绝不回退替身成功**；`ProviderNotActivated` 用于"未授权/未过 PoC"，绝不伪造结果。
- **不得**把 `reliable_new` 当作"算法已证明是新人"；PoC 门禁（`后端详细设计:663`）通过前
  不得开启真实自动建档。
- **不得**上传真实用户照片做联调；不得调用 `/v1/namespaces/**` 的写端点去动共享 8002/8003 的库
  （本服务是**独立实例、独立 SQLite**，与共享库物理隔离）。
- 适配层日志不得出现 token、图片字节、embedding、namespace/subject_id/correlation_id 取值。

---

## 9. 本轮方案反转的处置记录（可审计）

- 用户授权**改回 Python Worker 对接 InsightFace**、**停止 Java 直连**。
- **未提交**的 Java producer 改动：先在 `.coordination/B-work/pivot-audit-2026-09-16/`
  生成审计件（`uncommitted-tracked.diff` 15799B、`untracked-files.tar` 71680B/6 文件、
  `provenance.txt` 逐项来源、`all-uncommitted-paths.txt`），`git apply --check --reverse` **rc=0**
  证明 patch 与工作树逐字节吻合后，才撤回。撤回前实测本轮开工时工作树 `tree entries = 0`、
  且未提交路径**域外命中 0** ⇒ 不含任何他人未提交内容。
- **已提交**的 Java 方案用**普通 revert**（未 reset/rebase/改写历史）移除：
  `081f834` 撤 `0d9ee60`（Java→Worker 身份结果合同 + 5 个冻结类型），
  `c4cb73a` 撤 `d80c50d`（Java 直连、真实 resolver、register/search/delete、写 `face_subject_ref`）。
- **revert 后已证明**：`git diff e57bc315..HEAD` 对 `backend/web-java` = **0 文件**、
  对 `backend/handoffs` = **0 文件**；`UnavailableFaceIdentityResolver` 已恢复；
  `MemberAccessGrantService` 的 catch 已移除；`web/face` 文件数 12 = 本轮前 12；
  `B-face-java.md` 回到 142 行且 blob 与 `e57bc315` 相同；
  **Java 全量 747 run / 0 / 0 / 18 skipped、BUILD SUCCESS rc=0、109 份 xml**（= 本轮前基线），
  本轮新增的 Java 测试类残留 **0**。
- **保留**：`1d6ac78`（face-service 1:N + `/live` + `/ready` + `top_k` 下界 + 错误码双向锁 +
  文档面关闭）与 `0dfdf29`（行尾空白），`git diff e57bc315..HEAD` 全树**只剩
  `backend/face-service` 16 文件**。
