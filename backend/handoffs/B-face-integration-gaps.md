# B 包人脸接入：现网能力缺口与最小新增接口/隔离方案

**状态**：供总协调（根）向用户说明后**另行授权共享服务变更**。本文档**不含任何代码改动**，也**未调用**任何人脸服务。
**基线**：`8f5b625`（分支 `feature/mvp-identity-devices`，工作树 `.worktrees/mvp-b`）。
**事实来源**：①本项目代码（逐条附 `文件:行`）；②根协调 2026-09-13 的**只读现网核验**结论（下文标注为「根核验」）。`backend/doc/references/face-insightface-code-review.md` **不作为现网能力证明**。

---

## 1. 本项目代码实际需要什么（权威需求，非我方新提）

| # | 需求 | 代码依据 |
|---|---|---|
| R1 | **质量/活体判定**：必须能区分"有脸"与"质量合格/活体通过" | `auth/FaceProvider.java:15` 的 `classify(purpose, content)` 返回 `auth/FaceClassification`，其取值含 **`QUALITY_REJECTED`**（`FaceClassification.java:11`）；`identity/MemberAccessGrantService.java:172-174` 据此返回 **422 `FACE_QUALITY_REJECTED`** |
| R2 | **可靠新人判定**：`RELIABLE_NEW` 必须"可靠"，不能由"未匹配"推定 | `FaceClassification.java:9`；`MemberAccessGrantService.java:180-181` 把 `RELIABLE_NEW` 与 `UNCERTAIN` **同等**处理为 **403 `FACE_NOT_VERIFIED`**（同一非揭示消息，防存在性推断） |
| R3 | **指定成员 1:1**：护理准入必须证明"当前人脸 = 方案成员" | `care/CareFaceVerifier.java:6-19` javadoc 记录**总协调 2026-09-11 裁定**："公共 `FaceProvider.classify(purpose, bytes)` **没有成员参数**，无法证明「当前人脸 = 方案成员」，**不得**作为准入证据"；要求 `verifyOneToOne(purpose, memberId, candidate)`，"缺少成员绑定或参考照时返回 `Outcome.CAPABILITY_UNAVAILABLE`，**绝不默认 MATCHED**"（`CareFaceVerifier.java:24-31` 的 Outcome 枚举含 `MATCHED/MISMATCH/UNCERTAIN/QUALITY_REJECTED/DEPENDENCY_FAILED/CAPABILITY_UNAVAILABLE`） |
| R4 | **稳定身份引用**：识别结果必须能映射到本项目成员行 | `identity/FaceIdentityResolver.java:24,32`（`identityNamespace()` + `resolve(content, classification) → Optional<ResolvedFaceIdentity>`）；`identity/ResolvedFaceIdentity.java:7`（`identityNamespace` + `faceSubjectRef`，**仅内部使用、绝不回客户端**）；`MemberAccessGrantService.java:312` 以 `WHERE identity_namespace = ? AND face_subject_ref = ? AND status = 'active'` **只读**定位成员 |
| R5 | **依赖失败 ≠ 通过**（fail closed） | `FaceClassification.java:12-13` 注释明写；`MemberAccessGrantService.java:175` → 503 `DEPENDENCY_UNAVAILABLE`；`:289-292` 把 `null` 归类为 `DEPENDENCY_FAILED` |
| R6 | **注册/建档可审计且不污染共享库** | 当前替身实现把 `face_subject_ref` 直接取图片字节 sha256（`identity/DevTestFaceIdentityResolver.java:40` → `MediaIntakeService.sha256Hex(content)`），**不含任何真实身份语义**；真实接入必须由某个流程把服务侧身份引用写入 `members.face_subject_ref`——而 **T01 `members` 的写入归 D 包**（B 只读），故这是**跨包依赖** |

---

## 2. 现网服务实际提供什么（根核验，只读）

- **8002**＝`face-insightface-server`（工作目录 `/home/bool/deployment/face-insightface-server`），端点 `/recognize`、`/register`、`/reload`、`/delete`。按用户原名，**8002 为初始可配置目标**。
- **8003**＝`face-insightface-server-2`，**PG 持久化**；`/recognize` 返回 `faces[{name, score, bbox}]`，其中 `name` 为 `face_feature_id` 或 `Unknown`，语义是**逐人脸的全库 top1**；`/register` 按 `name` 写入 `face_feature_id`，库中**已有 400 条**，取**最大脸**。
- **`/extract_face`（仅 8003）不是纯特征提取**：它**搜索 PG**，不匹配则**直接 INSERT**，返回 `face_feature_id`/`is_new`/`similarity`，同样取最大脸 ⇒ **有写入副作用**。
- 两个 systemd 服务均 active。
- **两版都没有**：指定目标 1:1、只读的注册操作回执、质量/活体结果。

**我方据此承诺的禁止事项（已在实施纪律中固化）**：不调用 `/extract_face` 作"无副作用核验"；不调用 `/register`、`/reload`、`/delete`；不在未经授权下向共享库自动建人；不上传真实照片；不修改/重启共享服务。

---

## 3. 缺口清单（每条 → 阻塞哪个需求 → 我方当前的诚实处置）

| # | 缺口 | 阻塞 | 我方处置（不得伪完成） |
|---|---|---|---|
| G1 | **无指定目标 1:1**：`/recognize` 只做全库 top1 | **R3**（护理准入）、并削弱 R4 | `CareFaceVerifier` 的真实实现**不接入**，生产/联调路径保持 `CAPABILITY_UNAVAILABLE`（→ 503），**绝不**用全库 top1 冒充 1:1 |
| G2 | **`Unknown` ≠ 可靠新人**：top1 未命中可能只是阈值/光照/角度导致的低分匹配 | **R2** | **永不**产出 `RELIABLE_NEW`；`Unknown`/低分一律映射为 `UNCERTAIN` → 403 `FACE_NOT_VERIFIED` |
| G3 | **无质量/活体结果**：只有 `score`/`bbox` | **R1** | **不**从 `bbox`/`score` 推断质量；`QUALITY_REJECTED` 分支在真实提供方下**不可达**，如实标注为"未接入"，需要质量信号时按 `DEPENDENCY_FAILED`/`UNCERTAIN` 保守处理 |
| G4 | **`/extract_face` 有隐藏写入**（不匹配即 INSERT） | R2、R6 | 完全不调用；也不把它当作"取 embedding 自行 1:1"的替代路径 |
| G5 | **不返回 embedding/特征向量** | R3 的替代实现路径（见 §5 方案 B） | 无法在本项目侧自行做 1:1 比对 |
| G6 | **无只读注册回执/无命名空间隔离**：`/register` 直接写共享库（已 400 条），无 namespace、无 receipt、无按项目限定搜索 | **R4、R6** | 不注册、不写共享库；成员↔`face_feature_id` 映射只能由**授权后的**建档流程产生 |
| G7 | **无库状态可观测性**：`/reload` 会全局改变模型/库状态，且无"本次判定基于哪个库版本/revision"的回执 | R5、审计 | 不调用 `/reload`；判定记录中**无法**标注库版本 ⇒ 审计能力缺失，须如实披露 |
| G8 | **错误语义未定义**：无 `NO_FACE`/`MULTI_FACES`/`SUBJECT_NOT_FOUND`/`MODEL_UNAVAILABLE` 之类明确码 | R5 | 只能把非 2xx/超时/解析失败统一归为 `DEPENDENCY_FAILED`（503），无法区分"配置错误（不可重试）"与"瞬时故障（可重试）" |
| G9 | **跨包依赖未落地**：`members.face_subject_ref` 需由 D 的建档流程写入真实 `face_feature_id` | R4、R6 | B 只读，无法自行建立映射；需 D 与总协调确认建档链路与 `identity_namespace` 取值 |

---

## 4. 完整人脸范围所需的**最小新增服务接口**（请根向用户申请授权）

设计原则：**只读优先、无副作用、可审计、可隔离**。按"最小改动即可满足 R1–R6"排序。

### P1（必需，解锁 R3/R5/G5）：纯特征提取，**无库写入**
```
POST /v1/extract            （新端点；与现有 /extract_face 区分，保证零写入）
req : { "image": "<binary|base64>", "namespace": "ai-skin-mvp" }   // namespace 可选，仅用于回执标注
resp: { "face_count": 1,
        "largest_face": { "bbox": [x1,y1,x2,y2], "det_score": 0.93 },
        "embedding": [0.0123, -0.0456, ...], "dim": 512,
        "model_version": "...", "library_revision": "...", "request_id": "..." }
err : NO_FACE | MULTI_FACES_AMBIGUOUS | IMAGE_DECODE_FAILED | MODEL_UNAVAILABLE
```
**为何最小**：有了纯提取，**1:1 可由本项目自己完成**（B/D 在自有库中保存成员参考照的 embedding 与版本，比对余弦相似度），从而**完全不需要**向共享库注册、也不需要共享服务实现"指定目标 1:1"。这是**改动面最小、隔离最彻底**的路径。

### P2（必需，解锁 R1/G3）：质量与活体信号
```
POST /v1/quality            （或并入 P1 响应的 quality 段）
resp: { "quality": { "blur": 0.12, "occlusion": 0.02, "pose_yaw": 3.1, "illumination": 0.88,
                     "min_acceptable": true },
        "liveness": { "score": 0.97, "passed": true, "mode": "static|action" } }
```
若服务侧**不具备活体能力**，请明确告知；我方将把 `QUALITY_REJECTED`/活体判定标注为**未接入**并保持保守拒绝，而不是用 `score` 冒充。

### P3（若不走 P1 自比对，则必需；解锁 R3/G1）：指定目标 1:1
```
POST /v1/verify
req : { "subject_id": "<face_feature_id 或本项目成员引用>", "image": "...", "namespace": "ai-skin-mvp" }
resp: { "matched": true, "similarity": 0.81, "threshold": 0.62,
        "face_count": 1, "quality": {...}, "liveness": {...},
        "library_revision": "...", "request_id": "..." }
err : SUBJECT_NOT_FOUND | NO_FACE | MULTI_FACES_AMBIGUOUS | NAMESPACE_NOT_FOUND | MODEL_UNAVAILABLE
```
**关键**：只与 `subject_id` 比对，**不做全库检索**、**不写入**。

### P4（解锁 R4/R6/G6）：命名空间隔离的注册与回执
```
POST   /v1/namespaces/{ns}/subjects            → 201 { "subject_id", "namespace", "created_at",
                                                       "model_version", "library_revision", "request_id" }
GET    /v1/namespaces/{ns}/subjects/{id}       → 200 { "subject_id", "created_at", "library_revision" }  // 只读存在性
DELETE /v1/namespaces/{ns}/subjects/{id}       → 200 { "deleted": true, "request_id" }                  // 带回执
搜索/识别一律限定在 namespace 内；跨 namespace 不可见。
```

### P5（解锁 G7/G8，低成本）：只读自省与确定错误语义
```
GET /v1/health        → { "status":"ok", "model_version":"...", "library_revision":"...", "last_reload_at":"..." }
GET /v1/namespaces/{ns}/info → { "subject_count": N, "library_revision": "..." }
```
并在所有端点使用**固定错误码集合**（上列 `err`），使我方能区分"配置错误（不可重试）"与"瞬时故障（可重试）"。

> **最小可行子集**：若用户只愿批准一项，请优先 **P1（纯提取，零写入）** + **P2 的 quality 段**。仅此两项即可让我方在**完全不写共享库**的前提下实现 R1/R3/R4/R5（1:1 与新人判定由本项目自有数据完成），G1/G4/G5/G6 同时消解。P3/P4 是"由服务侧承担 1:1 与建档"的替代路径，二者与 P1 择一即可。

---

## 5. 隔离方案（请根与用户择一）

| 方案 | 内容 | 优点 | 代价/风险 |
|---|---|---|---|
| **A（推荐）项目自有实例 + 自有库** | 为本项目另起一个 insightface 实例（例如新端口），使用**独立 PG database/schema** 与独立人脸库；本项目通过 `app.face.insightface.base-url` 指向它 | 与既有 400 条共享库**物理隔离**；可自由注册/删除/重建；不影响其它项目；`/reload` 风险局限在本项目 | 需要新增部署与资源；需用户授权部署 |
| **B（次选）共享实例 + 纯提取 + 本项目自持特征** | 不改共享服务的写路径，只新增 **P1 纯提取**；成员参考照 embedding 存在**本项目自有库**，1:1 由本项目计算 | 对共享服务改动最小（一个无状态端点）；身份数据所有权留在本项目；天然按项目隔离 | 需要 P1；本项目需安全存储 embedding（属敏感生物特征数据，须加密/访问控制与合规评估） |
| **C（不推荐）共享库 + namespace 前缀** | 在现有实例上加 `namespace` 参数，注册/识别/删除均按 namespace 限定 | 无需新实例 | 共享模型与 PG、共享 `/reload` 影响面；若服务端未强制 namespace 过滤，存在**跨项目 top1 误匹配与身份泄漏**风险；400 条既有数据的归属不明 |

---

## 6. 在**不改动共享服务**的前提下，我方现在能做到哪一步（默认关闭、诚实降级）

可实施（等 SMS/OSS 确立"按服务独立选择 provider"机制后复用同一机制接入）：
- `app.face.provider=doubles|insightface`（默认 `doubles`；由根在填齐配置后切换），`app.face.insightface.base-url`（初始指向 **8002**）、`timeout`、`score-threshold`、`identity-namespace`。
- **只调用只读的 `/recognize`**；把 `faces[].name`（即 `face_feature_id`）经 `identity_namespace + face_subject_ref` 映射到本项目成员（`MemberAccessGrantService:312` 的既有只读查询）。
- 映射与判定纪律（**硬性**）：
  - top1 命中且 `score ≥ 阈值` 且其 `face_feature_id` 映射到**请求上下文所指成员** → 才可视为 `MATCHED`；否则一律 `UNCERTAIN`。
  - `name == "Unknown"`、低分、多脸、无脸、超时、非 2xx、解析失败 → `UNCERTAIN` 或 `DEPENDENCY_FAILED`，**绝不** `RELIABLE_NEW`、**绝不** `MATCHED`。
  - **真实服务故障绝不回退替身成功**（与本轮总授权一致）。
  - `QUALITY_REJECTED` 与 `CareFaceVerifier` 的真实 1:1 标注为**未接入**，分别保持不可达与 `CAPABILITY_UNAVAILABLE`（503）。
- 该模式必须由配置**显式开启**，且在文档与生成 Swagger 中如实标注"top1 非 1:1、无质量/活体"，**不得**对外宣称已完成人脸核验能力。

**结论**：上述只能覆盖"已建档成员的弱身份提示"，**不能满足 R1/R2/R3**。完整人脸范围必须先获得 §4 的接口与 §5 的隔离授权。

---

## 7. 需要根/用户裁定的事项（按优先级）
1. 选 §5 的哪个隔离方案（推荐 **A**；若资源受限则 **B**）。
2. 批准 §4 的最小接口子集（最优先 **P1 + P2 quality**）。
3. 确认 `identity_namespace` 的取值与 **D 包建档链路**：谁、在什么流程、以什么审计口径把真实 `face_feature_id` 写入 `members.face_subject_ref`（G9）。
4. 明确活体能力是否存在；若不存在，确认"质量/活体判定长期标注为未接入"是否可接受。
5. 确认 embedding 若由本项目自持（方案 B/P1）的**合规与安全要求**（加密、访问控制、留存与删除策略）。
