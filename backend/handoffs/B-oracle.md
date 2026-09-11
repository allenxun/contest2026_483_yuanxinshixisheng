# B 包 Oracle 审查记录（M1 / M2 / M5 / 跨模块媒体策略）

> 门禁依据：`backend/doc/tasks/COMMON.md`「Oracle 审查门禁」——实施与自测 → 提交候选代码 → Orchestrator **实际调用已安装 Oracle** → 修复阻塞 → Oracle 复审最终代码 → E 独立验收 → 总协调确认集成。
> 本文件为 report-only 提交；被审代码 SHA 以 `git rev-parse` 实际输出为准。Oracle 不可用/调用失败/无结论时如实记 `blocked`，不视为通过；有阻塞问题时不通过。

## 0. 审查会话与绑定

| 项 | 值 |
|---|---|
| Oracle 代理 | omo-slim `oracle` 子代理（只读；用户配置的默认模型与提供方，未切换、未用 `--auto`、未全局放行权限） |
| 会话 | `ses_f70bc47c3ffeLASOzFOAJZPUO8`（别名 `ora-1`；**六轮全部复用同一会话**，经 `task_id` 恢复以保留其历轮发现上下文） |
| R1 被审 SHA | `0f933fc6278bfd225625c8d2a8a7e878408363e6` → `VERDICT: FAIL`（7 BLOCKER + 2 IMPORTANT） |
| R2 被审 SHA | `e6812d498445867f99241ba27e5327dd9a596793` → `FAIL`（#1/#7 闭合；#2/#3/#5/#6 未闭合 + 1 新 BLOCKER） |
| R3 被审 SHA | `ed5eb865ff0b336d2d584244c26e11b3d1908aa8` → `FAIL`（#3/#5/#6/新BLOCKER 闭合、三处共享接缝正确未越界；剩 #2 淘汰残留 + b37 IMPORTANT + 1 SUGGESTION） |
| R4 被审 SHA | `954c95bf138a6172629dc4ae8c12dac72bda8bb8` → `FAIL`（#2 原淘汰漏洞与 b37 闭合、GIMBAL 表满 fail closed 可接受；新 BLOCKER = APP observer 会话表确定性耗尽） |
| R5 被审 SHA | `5f0a988333b86a1198297de257c4952d04ded1d1` → **`PASS-with-notes`**（R4 BLOCKER 闭合；B 包门禁通过；整体集成未就绪；新发现 1 IMPORTANT + 1 SUGGESTION，均为文档缺陷） |
| **R6 被审 SHA（交付 SHA）** | **`f95037e5bbd37742175b52685ca833f91396e00c`** → **`PASS-with-notes`（重新绑定确认）**：`5f0a988..f95037e` 唯一变更为类级 javadoc，R5 两条发现均已正确处置，**两层结论原样重新绑定**，不要求重跑端到端验收，**新发现：无** |
| 基线 SHA | `ccee6e28a132b73098523fbc56bf25f4719e4c24`（A 已验收并合入 dev） |
| 审查范围 | 仅 B 包：`web/identity/**`、`web/devices/**`、`web/notifications/**`、`web/mediapolicy/**`、`worker-python` 的 `handlers/notification_deliver.py`+`notifications/**`+`scanners/**`、`backend/tests/run-acceptance-b.sh`+`support/b-*`、7 个既有文件的最小适配、契约 8 行改动 |
| 不在范围 | A 的基础设施实现、C/D 的 M3/M4 业务、`backend/doc/**` |

## 1. 逐模块结论

| 模块 | 第一轮（`0f933fc6`） | 阻塞项 | 处置 | 最终结论（R5/R6 @ `f95037e`） |
|---|---|---|---|---|
| M1 身份与查看授权 | 功能/权限/T13/撤销防复活基本正确；M1-A03 实际错误码未纳入端点契约 | 1（#1 部分） | 契约补 `INVALID_INPUT`+`'400'`；验收 b04 真实触发该路径 | **闭合**（R2 判 #1 闭合；R3 起维持闭合，无新发现） |
| M2 设备管理 | **FAIL**：客户端 epoch 可回滚状态；未绑定云台可被任意 APP「解绑成功」；M2-A08 契约遗漏 | 3（#1 部分、#2、#3） | 先增服务端代次权威（R2）→ 改为有界会话代次表 + 表满 fail closed（R3→R4）→ **APP 代次键改为稳定 family、GIMBAL 保留 sessionId**（R4→R5）；未绑定新键解绑改 404 且提前到 revision 判断之前；契约补 `INVALID_INPUT`+`'400'`；b12/b23/b08 按新语义改写并加回归锁 | **闭合**（R3 判 #3 闭合；R4 判 #2 原淘汰漏洞闭合、GIMBAL 表满 fail closed 可接受为 MVP 最终形态；R5 判 APP 耗尽 BLOCKER 闭合并确认测试未绕过） |
| M5 通知 | **FAIL**：扫描器未接入 Worker；T12 业务代次未校验；unknown 恢复链不闭合；M5-A01 契约遗漏 | 4（#1 部分、#4、#5、#6） | #5 校验前移到所有状态分支之前 + 写回事务内复校；#6 经 D 的 `complete_failure(business_tx=…)` 同事务收敛（消除"T10 先独立提交再被守卫拒绝"）；#1 契约补 `BINDING_CHANGED`；**#4 按总协调裁定维持 C8，作为未闭合集成依赖如实披露** | **#5/#6 闭合**（R3/R4/R5 维持）；**#4 仍未闭合**，归总协调集成（不得当作已通过） |
| 跨模块媒体策略 | **FAIL**：冻结格式与用途闸门正确，但 APP 授权采用非权威 `T11.member_id`，存在跨成员放行风险 | 1（#7） | 改为只以 `T05.member_id` 为权威，T11 不一致即对所有人 fail closed | **闭合**（R2 判定，Oracle 并确认我的 fail-closed 裁定"完全符合此前要求"） |

边界结论（Oracle 第一轮原文）：未发现本提交修改迁移或 A 的主代码 `auth/media/idempotency/jobs/error/config/system/runtime/deploy/doc`；共享测试与 stub 改动符合已授权范围。

## 2. 提交给 Oracle 的审查覆盖项（COMMON.md 八维度）

1. **需求/任务清单符合性**：`B-identity-devices.md` 与 `checklists.json` 的 B-01～B-20；12 API + 通知/离线 Python handler + B 唯一统一业务媒体策略。
2. **模块边界**：B 不建档（`members` 只读）、不实现 M3/M4、不另建第二套媒体策略、不改 A 的 auth/media/idempotency/jobs/error/web/config/system/testdouble/runtime/迁移/deploy/doc；handler 注册表仅追加本包条目；stub 仅移除自己的占位。
3. **API / 数据库契约**：`openapi.yaml` 对应 path item 与 component schema（`additionalProperties:false`、`BigintString`、RFC3339 UTC、成功/错误信封）；V1/V2 的 14 表列与 CHECK/唯一约束（JSONB `schema_version` 类型级约束、`uq_grant_active`、`uq_destination_installation`、`uq_notification_dedup`、`ck_destination_active_fields`）。
4. **权限**：身份只由 token 派生；可见性统一 404 不可区分；face 与核验证据永不放行；云台仅当前任务；绑定不替代成员授权；撤销即刻生效。
5. **幂等与并发**：T13 `begin/completeSuccess/completeRejected` + 代次守卫；`binding_revision`/`destination_revision`/`status_revision`/`attempt_count` 守卫式字段级 UPDATE；真实多线程与真实并发 HTTP 竞争用例；禁 JOIN、有限次单表查询。
6. **恢复路径**：T12 租约与代次、退避与 `max_attempts`、`sending` 崩溃窗口与回执对账、`unknown` 可对账与末次原子收敛、扫描器可重入与单行失败隔离、worker 重启不丢任务。
7. **测试证据**：Java 198/0/0/0 rc=0；Python 84 passed + 1 项已披露 A 环境耦合断言；契约四项校验全绿；端到端验收 39/39 `SCRIPT_RC=0`（b14 观测面 37 条、12 端点全覆盖）。
8. **生产接入限制**：人脸/推送/会话/设备凭据真实提供方均未接入，替身明确命名且 profile/env 门禁，生产 fail-closed；阈值为联调起点非承诺；**扫描器周期触发未接入部署（未闭合集成依赖）**。

## 3. 第一轮审查记录（被审 SHA `0f933fc6`，VERDICT: FAIL）

### 3.1 blockingFindings 与处置

| # | 严重度 | 位置（Oracle 给出） | 问题 | 处置（落在 `e6812d49`） |
|---|---|---|---|---|
| 1 | BLOCKER | `openapi.yaml:203,490,1357` | 实现会返回端点未声明的错误码：M1-A03 缺 `INVALID_INPUT`/`'400'`；M2-A08 缺 `INVALID_INPUT`/`'400'`；M5-A01 缺 `BINDING_CHANGED` | 已补齐三处声明（仅补遗漏、不改语义）；**并修复根因**：b14 原先只校验"已触发路径"，故这三条从未被观测——现 b04 补"带合法 Authorization、仅缺 Idempotency-Key → 400"、b12 补"非法 If-Match → 400"、b13 补"陈旧 `expectedDestinationRevision` → 409 且代次不递增"，观测面 31→**37** 条 |
| 2 | BLOCKER | `GimbalHeartbeatService.java:89-95`；`MicrocrystalService.java:234-244` | 客户端自填 epoch 具有替换旧状态的权力：epoch 文本不同即无条件接受任意低 seq，可覆盖较新事实 | 新增 `devices/ServerGeneration.java`：GIMBAL=`"gimbal:"+credentialVersion+":"+sessionId`、APP=`"app:"+sessionId`，**只从 `PrincipalContext` 派生、绝不读请求体**；`observation_generation`/`observer_generation` 写入 `latest_observation` JSONB；代次变化才接受新 epoch 并重置基准，**同代次内 epoch 必须一致且 seq 严格更大**，否则 `accepted=false` 且不刷新 `last_seen_at`/不递增 `status_revision`/不覆盖观察与能力。未加列/未加表/未改迁移 |
| 3 | BLOCKER | `GimbalBindingService.java:244-249`；`GimbalBindingIT.java:333-336` | 任意 APP 可对未绑定云台获得 204，服务端无法证明调用方是原账号，违反 DD M2-A08「新的未知解绑请求不得猜测之前归属」 | `bound_account_id IS NULL` 分支由 `completeSuccess`(204) 改为 `rejectInTx(notVisible())` → 404 `RESOURCE_NOT_VISIBLE` 并落 T13 `rejected`，不写任何列、不递增代次；**仅原 T13 成功请求的同键重放仍 204**；IT 与验收 b12 同步改写（新键未绑定 404 且与不存在 UUID 掩蔽 `requestId` 后逐字节一致） |
| 4 | BLOCKER | `scanners/__init__.py`；`runtime/loop.py:186-198` | 离线扫描未接入既有 Worker：真实 loop 从不调用 `run_once`，验收靠单独执行 CLI 才产生通知 | **未改代码**。总协调裁定维持 C8：进程内周期接入由总协调在集成时唯一执行，B 不改 A 的 `loop/__main__/config/db`、不经 deploy 新增服务。按裁定在 `B.md` 第 6 节第 6 项与本文件如实记为**未闭合的集成依赖**，请 Oracle 按职责边界区分「B 包结论」与「整体集成就绪」；**不删除该发现、不视为已通过** |
| 5 | BLOCKER | `notification_deliver.py:145-175,343-407` | 未校验 T12 的 `owner_type`/`owner_id`/`input_revision`/`dedup_key`，配错 owner 或陈旧 `input_revision` 仍可能投递并成功完成 | 在锁内（T03→T09→T10 `FOR UPDATE`）、**置 `sending` 之前**新增 `_contract_mismatch` 四项校验；字段来自 A 的 `claim_batch` 行投影 `JobRow`，`destination_revision` 来自本事务内对 `notifications` 的单表 `FOR UPDATE` SELECT（未改 A runtime、禁 JOIN）；不符 → **绝不推送**，T10 `failed`+`UNSUPPORTED_CONTRACT`(retryable=false)，T12 经 A 既有 `complete_failure` 终结，未自创错误码 |
| 6 | BLOCKER | `notification_deliver.py:59-64,151-175,162-175,313-331`；`test_notification_deliver.py:221-247` | `unknown` 被当终态且 T12 随即 succeeded → 此后永不查回执；测试靠手工把 `unknown` 改回 `sending` 制造前提；末次异常时 T12 变 failed 而 T10 永久滞留 `sending` | `unknown` 移出终态 no-op、成为**可对账**状态（`_RECONCILABLE_STATUSES=("sending","unknown")`）：再次处理先查回执（provider key 稳定 `notification_id:attempt`），`accepted→submitted`、`delivered→delivered`、`not_found` 按策略同 key 有限重发；无法定性则 `JobFailed(retryable=True)` 由 A 退避驱动，`max_attempts` 为硬边界；新增 `_converge_t10`（守卫 `WHERE status IN ('sending','unknown') AND attempt_count=本次`）覆盖回执查询异常、provider 异常、`KIND_UNKNOWN`/`KIND_TRANSIENT` 末次、probe/recheck 异常末次、边界耗尽，**绝不滞留 `sending`**；测试改走真实状态机（删除手工改状态的伪前提），新增末次回执异常/末次 provider 异常/边界耗尽三例 |
| 7 | BLOCKER | `BusinessMediaAccessPolicy.java:152-161` | APP 授权优先使用非权威 `T11.member_id`；两表无跨表一致性约束，错误/恶意写入可让持有其他成员授权的账号读取受害成员报告图片 | 改为**只以 `T05.member_id` 为权威**；T11.member_id 非空且与 T05 不一致 → **fail closed 对所有人拒绝**（含 T05 属主），记不含敏感内容的 warn（`branch=t11-t05-member-mismatch`）；T05 为空 → 拒绝；新增 `t11MemberIsNotAuthoritative` 三组断言（不一致时 A、B 均 404；一致时 A 200/B 404；T11 为 NULL 时按 T05 放行） |

### 3.2 IMPORTANT 与处置

| # | 位置 | 问题 | 处置 |
|---|---|---|---|
| 8 | `AuthController.java:190-195`（A 归属） | 登出失效把 T09 置 `invalid` 但**不递增** `destination_revision`，违反裁定④代次纪律 | **未改 A 文件**。Oracle 判其对 B 门禁**非阻塞**、A 待修：投递侧探针要求 `status='active'`（否则返回 `None`），锁内重检亦判 `status != active → destination_changed → cancelled`，故登出后旧通知必被取消、不误发；重新激活经 B 注册分支必 `+1`；残余仅"登出瞬间代次数值不变"。已记入 `B.md` 第 6 节第 8 项与协调台账，请 A 归属方补 `+1` 与并发测试 |
| 9 | Git tree | `B.md`/`B-oracle.md` 为 untracked，不在被审 SHA 中 | 符合纪律：报告须在代码定稿后按 report-only 单独提交并绑定最终 SHA。本次复审即绑定 `e6812d49`，两份文档随后提交 |

### 3.3 我对"BLOCKER C 规格矛盾"的裁定（记录在案）

我下发给实施道的任务书里误写了一条与 Oracle 原文互斥的测试期望（"T11.member_id 写成成员 B 时，持成员 A 授权 → 200"）。Oracle 原文为「授权只使用 `T05.member_id`；若 `T11.member_id` 非空，还必须要求其等于 `T05.member_id`，**否则 fail closed**」——"不一致即 fail closed"必然同时拒绝 T05 属主，两者不可能并存。实施道发现矛盾并按 Oracle 原文实现、在报告中据理指出，未默默选边。

**裁定：采纳 Oracle 原文（不一致时对所有人 fail closed）**，我那条"→200"的期望作废。理由：T11/T05 之间无跨表一致性约束，不一致意味着某个写入方已违反不变量（缺陷或篡改）；本项目一贯教义为 deny-by-default／fail closed（媒体策略解析异常同样拒绝、生产提供方缺失同样拒绝启动/拒发/拒投）；越权风险必须闭合，而合法属主的可用性损失由不含敏感内容的 warn 日志作为运维信号暴露。已请 Oracle 在复审中确认该裁定与其要求一致。

### 3.4 第一轮对"解释性决策"的逐条裁定（Oracle 原文结论）

| 决策 | Oracle 裁定 |
|---|---|
| 无可靠匹配/不确定/库中无人统一 403 `FACE_NOT_VERIFIED` 同一 message | 可接受（避免候选与成员存在性泄漏） |
| B 自建 `FaceIdentityResolver` seam，dev/test 用图片 SHA-256，生产无 bean → 启动失败 | 可接受（真实供应商未接入时 fail-closed） |
| 确定性人脸拒绝 `completeRejected`；瞬时 503 留 `processing` 由租约接管 | 可接受 |
| 404 比较时仅掩蔽 `requestId` | 可接受（`requestId` 本就必须逐请求变化） |
| M1-A02 省略可选 `memberSummary` | 可接受（契约非 required 且结构未冻结） |
| 心跳 `taskId`/`executionId` 只作观察、故意不用 `TASK_REPLACED` | 可接受（但不消除 epoch 回滚 blocker → 已由 #2 修复） |
| M5 revision 不符复用 409 `BINDING_CHANGED` | 语义可接受；**需改契约声明** → 已由 #1 补 |
| 换号接管接受 `expected` 为 `"0"` 或当前值并强制 `+1` | 可接受（前提是真实会话提供方能证明 installation 归属） |
| `async_jobs.input_revision = destination_revision` | 选择可接受；**当时 handler 未执行该代次校验** → 已由 #5 修复 |
| T10/T12 单一插入写者 = Python 扫描器 | 职责划分可接受；**但扫描器尚未接入既有 Worker** → 即 #4，按裁定维持 C8 并披露为集成依赖 |

## 4. 复审记录（被审 SHA `e6812d498445867f99241ba27e5327dd9a596793`，会话 `ora-1`）

### 4.0 结论

**`VERDICT: FAIL`**（第二轮）。Oracle 明确区分两个结论：
- **(a) B 包门禁结论：不通过。** B 可自决范围仍有阻塞项：#2（sessionId 不是有序、独占的服务端 generation）、#3（unbound 分支仍可通过陈旧 `If-Match` 被区分）、#5（T12 绑定校验未覆盖 reconciliation/terminal 路径）、#6（T10 失败收敛与 T12 lease 完成不在同一代次受控事务）。
- **(b) 整体集成就绪结论：未就绪。** 除上述外，#4 扫描器仍未接入既有 Worker（按总协调裁定不属 B 越界修复项，但必须由集成方完成进程内周期调用并验证；当前验收依赖单独 `scanners --once`，**不能证明生产运行形态**）；#8 A 的登出失效仍不递增 `destination_revision`（对 B 门禁非阻塞，属整体交付前必须修复或明确接受的代次纪律缺口）。

### 4.1 7 个 BLOCKER 的闭合判定（Oracle 原文依据）

| # | 是否闭合 | Oracle 判定依据（文件:行） | 未闭合复现 / 处置 |
|---|---|---|---|
| 1 契约声明 | **是** | `openapi.yaml:203-215`、`:491-508`、`:1359-1394`；验收新增路径 `b-checks-1.sh:102-109,329-333,367-373` | — |
| 2 epoch 回滚 | **否** | `ServerGeneration.java:27-31`；`GimbalHeartbeatService.java:98-107`；`MicrocrystalService.java:242-259`；旧 session 仍有效见 `InMemorySessionDouble.java:66-75,124-129`、`PrincipalRevalidator.java:41-46` | 同设备先后取得 session A、B 且均未撤销：A 报高 seq，B 因 generation 不同以低 seq 覆盖，A 再因 generation 不同再次覆盖 → **随机 sessionId 只有唯一性、没有新旧次序，仍可来回回滚**。→ 已派 Java 道改为"服务端观察到的**有界会话代次表**"，旧会话永不重获权威 |
| 3 未绑定解绑 | **否** | `GimbalBindingService.java:220-248` | 云台已 unbound、当前 `revision=2`，提交 `If-Match: "binding-1"` → 代码在检查 unbound **之前**先做 revision 判断（`:224-225`）返回 409 `BINDING_CHANGED`，而不存在 UUID 返回 404 → **仍泄漏存在性**。应先对 unbound 统一 404 再判 revision。→ 已派 Java 道修正分支次序 |
| 4 扫描器接入 | **否，按协调裁定保留为集成依赖** | `incident_scanner.py:17-19` 仍注明"由总协调接入"；`runtime/loop.py:186-198` 仍无周期调用 | 仅启动 `python -m mvp_worker`、不另跑 scanner CLI，则云台超阈值后不会生成离线 T10/T12。**按总协调裁定维持 C8：B 不改公共 runtime/loop、不经 deploy 新增服务；该发现如实保留，不删除、不视为已通过** |
| 5 T12 业务绑定 | **否，仅正常发送路径闭合** | 校验已在 `notification_deliver.py:409-568`，但 `handle():163-169` 的终态分支与 `_reconcile():208-268` **绕过** `_contract_mismatch` | 将 T10 置 `unknown`/`sending`，创建 `owner_id`/`input_revision`/`dedup_key` 错误的 T12，并让回执返回 accepted → 代码直接执行 `_reconcile_finalize_tx`，**错误 T12 仍能发布 submitted 并 succeeded**。→ 修法：在**所有状态分支之前**校验，并在最终写回事务内复校（待与通知简化一并实施，见 §4.4） |
| 6 unknown/失败恢复 | **否，恢复流程已补但代次原子性未闭合** | `notification_deliver.py:225-231,253-268,378-395,641-666` 先独立提交 T10；随后 `runtime/loop.py:96-98,134-148` 才以 lease guard 完成 T12 | W1 在 lease 即将失效时调用 `_converge_t10`，W2 回收并取得新 lease；W1 可先提交 T10 `failed`/`unknown`，其后 T12 `complete_failure` 因 stale lease 被拒 → **旧 worker 的业务结果已发布，违反 T12 代次守卫**。→ 见 §4.2 新 BLOCKER 与 §4.4 依赖处置 |
| 7 媒体权威成员 | **是** | `BusinessMediaAccessPolicy.java:151-167` 只以 T05.member_id 授权，并对非空且不一致的 T11.member_id fail closed；反例测试 `BusinessMediaAccessPolicyIT.java:660-720` | — |

### 4.2 第二轮新发现（Oracle）

| 严重度 | 文件:行 | 问题 | 复现 | 建议修法 |
|---|---|---|---|---|
| BLOCKER | `notification_deliver.py:641-666`；`runtime/loop.py:96-98,126-148` | 新增的 `_converge_t10` 是**独立事务**，不受当前 T12 `lease_owner/lease_revision` 原子守卫；代码注释所称"同一原子写"只覆盖 T10 单行，不覆盖业务结果与 T12 的一致性 | 让 W1 的 lease 在 `_converge_t10` 前后过期并由 W2 接管；W1 的 T10 更新可提交，而其后续 `complete_failure` 被 stale guard 拒绝 | 扩展失败完成协议，采用"业务行写回 → T12 guarded failure update"的同一事务；守卫失败必须整体回滚业务写 |

**orchestrator 已亲自核实该发现成立**：A 的 `runtime/complete.py` 中 `complete_success(engine, claim, *, handler_result_tx=None)` **确有**业务写扩展点（"成功路径单事务：业务写 → T12 succeeded（守卫不满足则全部回滚）"，代次失效抛 `StaleGeneration` 连同业务写一起回滚），而 `complete_failure(engine, claim, *, code, message, retryable, backoff_base_seconds, backoff_cap_seconds)` **没有任何业务写钩子**；`HandlerResult` 的 docstring 亦写明其为"handle() **成功**产物：可选业务写回调，由 `complete_success` 在同一事务执行"。故失败路径上 B 无法把 T10 收敛与 T12 守卫写放进同一事务。

**总协调裁定（2026-09-11，替代 orchestrator 提出的三个选项）**：已指定 **D 唯一实现**公共 `complete_failure` 的事务 callback 扩展，以及 `loop` 的 `except JobFailed → _finish_failure → complete_failure` 最小透传。**B 不重复修改公共接口、不自行复制 T12 状态机**，等集成后复用 D 的接口。该裁定**不是**批准 B 修改公共 runtime，**也不是**把 Oracle 的原子性发现当作通过——发现与依赖均如实保留，待简化范围与集成接口落实后据实际代码复审。

### 4.3 Oracle 对 §3.3 裁定的确认

> "**确认，完全符合此前要求。** T11/T05 不一致表示数据不变量已破坏；对 T05 属主、T11 指向成员及其他主体全部拒绝，是正确的 deny-by-default 行为。当前实现只使用 T05.member_id 授权，并以 warn 暴露异常，处理合理。"

### 4.4 第二轮后的处置与协调依赖（总协调裁定）

1. **#2、#3** → 纯 B 的 Java 写域，已派实施道修复（#2 改为服务端观察到的有界会话代次表：`credential_version` 推进则清空重置；同 `credential_version` 下按"服务端首次见到该 session 的先后"赋 generation，来方 generation 更高才接受并重置、相等则 epoch 必须一致且 seq 严格更大、更低一律拒绝；微晶同构；上限有界且绝不淘汰当前最高 generation）。
2. **通知按用户 MVP 决定简化**（用户原话："发送通知这个事情，先记录一下。目前mvp阶段，简单处理：假设发送服务很稳定，只要发出去一次就可以，而且耗时不会很长。"）：暂不扩展复杂重试与回执对账；**不能让旧设计自动覆盖用户最新决定**。
3. **#5 与简化一并实施**：T12 四项绑定校验必须前移到**所有状态分支之前**并在最终写回事务内复校；**绑定账号/投递目标归属等既有发送前检查不因简化而放宽**（裁定明文）。
4. **#6 转为协调依赖**：等 D 的 `complete_failure` callback 落地后，B 只需把 T10 收敛放进该回调即可闭合；简化后 `max_attempts=1` 使失败路径只剩一条，改动面更小。
5. **C19 建议稿已提交协调确认**（`.coordination/B-work/c19-notification-simplification.md`）：列明简化后**必须保留**的最小失败状态与处理（发送前重检与锁顺序、`cancelled`+有界 `last_error`、T12 绑定校验、T10 记录 `destination_revision`、`sending` 仅作崩溃可见性、推送内容合规与生产 fail-closed），**建议简化/暂缓**的部分（退避重试、回执对账、`delivered` 保留枚举但不产生、推送五态收敛为"已交出/未交出"两类但保留端口），以及两项**需协调确认、B 不自行猜测**的精确行为：(i) 发送途中崩溃后重新领取应 at-most-once 不重发（建议）还是重发一次靠通道幂等键去重；(ii) "发出去"的供应商最小判定（建议：未抛异常即 `submitted`，异常/明确拒绝即 `failed`；若要求必须有受理 ID，则无 ID 时按 `failed`）。
6. **#4、#8** 维持既有分类：#4 由总协调唯一接入（B 只维护可重入 `run_once` 与 `--once` CLI，验收以 CLI 驱动并如实标注不代表生产周期形态）；#8 为 A 归属待修（B 侧投递安全已闭合）。

### 4.5 Oracle 要求披露的残留限制（第二轮）

- #4 扫描器尚未接入既有 Worker，独立 `--once` 验收不能代表生产周期运行形态。
- #8 A 登出失效尚未递增 `destination_revision`。
- 真实人脸、设备凭据、连接/配对证明、会话探针及推送提供方均未接入；生产必须 fail closed。
- 离线阈值、扫描周期、退避与提醒参数只是联调起点，不是 SLA。
- 推送仍是 at-least-once；正确性依赖真实 provider 的稳定幂等键与可信回执。
- `backend/handoffs/B.md`、`B-oracle.md` 当时仍为 untracked，不属于 SHA `e6812d49`（将在本轮修复定稿后按 report-only 提交并重新绑定 SHA）。
- Oracle 未重复执行 orchestrator 提供的 Java/Python/契约/39 项验收证据；其静态审查发现的旧 session 交替、陈旧 `If-Match`、reconcile 错误绑定与 lease 竞争路径**不在现有通过用例中**。
- Python 全量仍有已披露的 A 归属 `test_sanity::test_config_defaults` 失败。

### 4.6 Oracle 实际执行的核查命令（第二轮，证明审的是 `e6812d49` 真实代码）

```bash
git rev-parse HEAD
git show --stat --oneline HEAD
git diff 0f933fc6278bfd225625c8d2a8a7e878408363e6..e6812d498445867f99241ba27e5327dd9a596793 --stat
git status --short --branch
git diff --check 0f933fc6..e6812d49
git diff --name-only 0f933fc6..e6812d49
git diff --name-only ccee6e28..e6812d49 -- 'backend/web-java/src/main/java/cn/yuanxin/mvp/web/auth/**' \
  'web/media/**' 'web/idempotency/**' 'web/jobs/**' 'web/error/**' 'web/config/**' 'web/system/**' \
  'src/main/resources/db/migration/**' 'backend/worker-python/src/mvp_worker/runtime/**' \
  'backend/deploy/**' 'backend/doc/**'      # 结果：A 独占目录零改动
```
另以只读 `read`/`grep` 检查全部 16 个变更文件、A 的会话签发与复核实现、Worker claim/complete/lease 路径及新增测试；未修改文件、未执行数据库写入。

### 4.7 第三轮复审（被审 SHA `ed5eb865ff0b336d2d584244c26e11b3d1908aa8`，会话 `ora-1`）

**`VERDICT: FAIL`**（仅剩 1 个代码级 BLOCKER + 1 IMPORTANT + 1 SUGGESTION）。

**判定闭合的项**
- **#3 未绑定解绑可区分** → 闭合：`GimbalBindingService.java:220-234`，unbound 判断已提前至 revision 判断之前，原复现（`unbound + binding-1` → 曾 409）现统一 404。
- **#5 T12 绑定校验覆盖所有分支** → 闭合：入口校验 `notification_deliver.py:221-240`（对账前已拦截）、事务内复校 `:668-760`、反例测试 `test_notification_deliver.py:317-400`。
- **#6 + 新 BLOCKER（T10/T12 同事务）** → 闭合：`DeliveryFailed` 适配 `:94-137`、末次收敛计划 `:619-645,798-852`、`complete_failure` 同事务协议 `runtime/complete.py:205-262`、`JobFailed.business_tx` `handlers/__init__.py:39-62`、loop 透传 `runtime/loop.py:101-106,155-169`、stale 回滚测试 `test_notification_deliver.py:451-493`。
- **三处共享接缝冲突解决** → 全部判定**正确、未越界、未削弱断言**：注册表六类型各注册一次（`handlers/__init__.py:114-133`，`register()` 对重复类型抛异常）；`test_unsupported.py:23-41` 精确集合相等 + `:44-59` 未知类型隔离保留 + `:62-82` 五种已注册 handler 的非法 payload 仍断言立即 `failed/UNSUPPORTED_CONTRACT`；`StubEndpointsIT.java:65-86` **17 个静态参数非空**、`:102-114` 同时校验 method+归一化路径模板+非占位 controller、`:88-100` 占位控制器零映射独立断言，Oracle 评"比依靠 400/404 的请求抽样更可靠"。
- **两处设计取舍** → (a) 失败收敛守卫放宽至全部非终态：**可接受**（`attempt_count` 须精确相等、四个终态不可覆盖、与 T12 owner/lease_revision/真实 wall-clock lease 守卫同事务、`pending→failed` 正确表达"终态失败但未调用推送"、成功写回仍严格限定 `sending/unknown`）；(b) 不再主动写 T10 `unknown`：**可接受但必须披露可观测性变化**（仅看 T10 无法区分"发送后崩溃"与"provider 明确返回 unknown"，需结合 T12 `last_error`）。
- **B 测试自清** → **可接受，不属用测试技巧掩盖生产缺陷**（`b_support.py:31-68` 按 FK 顺序清 B 自己的数据、setup/teardown 均执行，未降低业务断言、未改 D fixture）。

**未闭合 / 新发现**
- **BLOCKER #2 残留**：`ObservationSessions.java:36-40,95-109,161-170` 的**有界淘汰**重新打开 epoch 回滚——同 `credential_version` 下连续签发 9 个有效 session 使最早者被淘汰，该旧 token 再来被当作"首次见到"赋更高 generation 并覆盖当前事实（token 可在 1 小时内同时有效，非纯理论）。Oracle 给两方案：①会话提供方签发可比较 generation（跨包）；②**表满后对未见 session fail closed，直到 credential_version 推进，绝不淘汰仍可能有效的旧 session 再当新 session**。→ 采方案②，已在 `954c95b` 闭合（见 §4.8）。
- **IMPORTANT**：验收 `b-checks-3.sh:221-240` 的 b37 捕获了 pytest `rc` 却从未检查、也不解析 `errors`，会把"200+ passed, 1 error"误报为通过。→ 已在 `ed5eb86` 改为硬断言 `rc==0`/`failed==0`/`errors==0`（`errors?` 单复数均解析）/`passed>=200`，R4 判定**已闭合**。
- **SUGGESTION**：`NotYetImplementedController.java:17-32` javadoc 仍称保留 15 个占位而实际零映射，并留有无用 imports 与 `notImplemented()` 死代码 → 由集成所有者处理（C23）；R4 明确**不阻塞 B**。

第三轮的审查基线与上下文（已确定、可先行核对）：

1. **合并背景**：总协调明确授权 B 在本工作树合入集成基线 `8afd0e5ff3fc5c364bd5172134f941b303a25468`（含 C+D，D 的公共失败完成协议已 Oracle 通过），并授权 B 为三处共享接缝冲突的唯一执行者。合并提交 = `7281edd6ba909c3dbe8c0819e1f8f958dcb4ef55`（parents = `7c5402b` + `8afd0e5`，101 文件）。**Oracle 第三轮须覆盖合并后的实际代码与共享接缝，不沿用任何旧 SHA 的通过结论。**
2. **B 获得的关键公共接口**（合并后实测存在于工作树）：`JobFailed(code, message, *, retryable=True, business_tx: Optional[BusinessTx]=None)`；`complete_failure(engine, claim, *, code, message, retryable, backoff_base_seconds=5, backoff_cap_seconds=300, business_tx=None)` —— **同一事务内先执行 `business_tx(conn)`（禁网络），再做 status/owner/lease_revision/租约未过期守卫（`clock_timestamp()` 判定），0 行 → `StaleGeneration` → 业务写与任务状态整体回滚**；`loop.py:105` 透传 `business_tx=exc.business_tx`。这正是闭合第二轮 #6 与新 BLOCKER 所需，B 不复制接口、不另造 T12 状态机。
3. **三处共享接缝冲突的解决**（详见 `.coordination/B-work/ledger-round3.md` 第一节，含定向验证数字）：
   - `handlers/__init__.py`：A 的 `system.echo` + B 的 `notification.deliver` + D 的 4 个 handler **各注册一次**（纯追加，D 的公共类型在非冲突区自动合并）；
   - `tests/test_unsupported.py`：由"⊆ 契约白名单"收紧为**精确集合相等**（六种已实现 job_type），删除 D 侧合并后已不成立的 `assert "notification.deliver" not in types`，保留未知类型 `UNSUPPORTED_CONTRACT` 隔离测试，并把 `test_business_types_are_extension_point_failed` 的文档前提更正为真实语义（断言未削弱）；
   - `StubEndpointsIT.java`：删除旧 501 抽样（合并后占位控制器映射数为 0），改用 Spring 实际 `RequestMappingHandlerMapping` 正面证明"占位控制器零业务映射"+"原 contract-only 清单 17 个端点各由真实 controller 注册 method+path"（非空参数列表）。依据裁定"非 501 抽样不能作为唯一证明，404/400 不能证明路由正确"。技术注记：Spring 6 已移除 `RequestMappingInfo.getPatternCondition()`，由真实 javac 抓出并修正。
4. **合并后已验证的数字**（orchestrator 亲自执行）：接缝定向 `mvn -Dtest=StubEndpointsIT` → **19/19 rc=0**、`pytest tests/test_unsupported.py` → **5 passed rc=0**；**Java 全量 `Tests run: 383, Failures: 0, Errors: 0, Skipped: 0`，BUILD SUCCESS，rc=0**（含 A+B+C+D）；`git diff --check` 与 `--cached --check` 均 rc=0，全树零冲突标记，合并提交工件命中 0；两份未跟踪 B 报告完好。
5. **如实记录的未闭合项（不得当作已通过）**：
   - **Python 全量 140 passed / 78 errors**：错误全部在 fixture setup 阶段，集中于 D 的测试文件（`test_plan_generate` 42、`test_media_cleanup` 19、`test_result_archive_concurrency` 9、`test_lease_fence` 8），根因是 `tests/d_support.py:59 clean_d_tables()` 直接 `DELETE FROM gimbals`，与 B 的 `notifications_gimbal_id_fkey` 冲突；顺序依赖可证（`test_lease_fence.py` 单跑 8 passed、全量 8 errors）。`d_support.py`/`conftest.py` 属 D/公共写域，按裁定未在合并步骤改动；B 正以自有 teardown 规避，并已给出最小修法建议（协调 C22）。
   - `test_sanity.py` 合并后实测 **4/4 通过**，原 C15 的环境耦合失败已不再复现（如实记录，不再作为已披露失败项）。
   - #4 扫描器周期接入（C17，总协调唯一负责）、#8 A 登出不递增 `destination_revision`（C18，A 归属）、C23 占位控制器 javadoc 过时（提请订正）均未闭合。
6. **第三轮收尾进行中**：#6 经 D 的 `business_tx` 真正闭合（覆盖全部终态失败路径；非末次可重试失败仍保持 T10 可观测态；必须验证"过期 lease → 业务写随 `StaleGeneration` 整体回滚"与"有效 lease → T10 终态与 T12 failed 同时落库"），以及 B 测试自清 teardown。完成后取**最终代码 SHA** 送审。

### 4.8 第四轮复审（被审 SHA `954c95bf138a6172629dc4ae8c12dac72bda8bb8`，会话 `ora-1`）

**`VERDICT: FAIL`**（R3 的 BLOCKER 与 IMPORTANT 均判闭合，但发现 1 个新 BLOCKER）。

**判定闭合的项**
- **#2 原淘汰漏洞** → 闭合：`git grep prune` 计数 **0**（彻底删除，非停用）；表满对未见 session 返回 `TABLE_FULL`，不追加、不淘汰、不写业务列；已记录旧 session 保留原 generation 故不能重获最高代次。测试覆盖第 9 个 session、最早 session 重放、当前 session 继续推进、credential 推进恢复四条路径（`ObservationSessions.java:35-43,86-118`、`GimbalHeartbeatService.java:102-129`、`MicrocrystalService.java:162-179,266-289`）。
- **b37 IMPORTANT** → 闭合：`b-checks-3.sh:221-248` 同时硬断言 `rc==0`、`failed==0`、`errors==0`、`passed>=200`，`errors?` 可匹配单数 `1 error`；即使解析遗漏，非零退出码也会使检查失败。
- **GIMBAL 表满 fail closed** → **可接受为 MVP 最终形态**（有 `credential_version` 推进恢复途径，安全优先于可用性）；Oracle 要求配套运维措施（见 C26）。
- **`NotYetImplementedController` javadoc/死代码 SUGGESTION** → **不阻塞 B**，可继续由集成所有者处理（C23）。

**新 BLOCKER（R4 唯一剩余代码级阻塞项，系我 R3 选择方案②时引入）**
- 位置：`PrincipalContext.java:26-28`（APP 的 `credentialVersion` 恒为 0）、`InMemorySessionDouble.java:79-106`（APP 每次 refresh 撤销旧 token 并生成新 sessionId）、`ObservationSessions.java:90-104`（会话表只增不减）、`MicrocrystalService.java:277-286`。
- 复现：对同一微晶依次使用 8 个 APP session 上报，再 refresh/login 取得第 9 个 session；之后该 installation 的**所有**新会话均 `accepted=false`，即使旧会话已撤销/过期。
- Oracle 定性：**确定性正常生命周期故障，不只是极端并发**；"仅调高上限会推迟故障，不能解决"；必须提供**等价的权威恢复机制**，可选方向：① SessionProvider 暴露稳定 session-family/可比较 generation（跨包）；② B 的 `ConnectionProofVerifier` 返回真实连接 generation（B 自有）；③ **让 APP refresh 沿用稳定观察代次**（B 自有）。
- **处置**：采方向③。取证前提（orchestrator 亲自核实）：`openapi.yaml` 的 `m2A04` 明文"调用方：**APP 或云台**"，DD §M2-A04 同样未限定云台 ⇒ **APP 路径是契约要求存在的，不得删除或改 403**；且 `MicrocrystalService.java:410-412` 现有实现中 APP 的 `Observer.ref` 本就是稳定的 `account:installation`，耗尽根源是代次表用**随机 sessionId** 作键。故按主体类型分派代次键：**APP 用稳定 family（`account:installation`）、GIMBAL 保留 sessionId 且语义不变**；同 family 内仍要求 epoch 一致且 seq 严格更大（不放松顺序权威）；上限保护对两侧都保留（APP 侧对未见 family 同样 fail closed 且不追加）。**已落地于 `5f0a988`**（新增 `MicrocrystalObservationIT.appRefreshSessionsNeverExhaustFamilyTable` 等反例 + 验收 b8 的 HTTP 级回归锁），并经 Oracle R5 判定闭合，详见 §4.9。
- **必然的功能权衡（已立 C25 请总协调冻结协议语义）**：同 family 内 epoch 必须一致且 seq 严格更大 ⇒ APP 重启后若把 seq 归 1 或自行换 epoch，其上报将被拒绝；需 APP 侧把 `observationSeq` 单调持久化，或改用方向②/①。

**Oracle R4 明确要求披露的残留限制**
- GIMBAL 会话表满后未知新 session fail closed，可能停止刷新 `last_seen_at` 并触发误离线通知；`app.devices.max-observation-sessions` 是可用性/JSONB 大小权衡，**建议生产初值评估 32~64** 并配置表满告警（B 已埋 `branch=session-table-full-fail-closed` warn，仅含 `gimbalId`/`microcrystalId`+`maxSessions`，不含 sessionId/token/成员信息）与凭据轮换 runbook（C26）。
- APP 会话当前无安全恢复机制 —— Oracle 明确"这是 blocker，不能仅作为普通限制接受"（即本轮必须修，不得降级为披露项）。
- 其余维持：#4 扫描器未接入既有 Worker（CLI `--once` 不代表生产周期运行）；#8 A 登出不递增 `destination_revision`；T10 不再主动写 `unknown`（不确定态表现为 T10 `sending`，需结合 T12 `last_error` 判断）；真实人脸/设备凭据/连接与配对证明/会话探针/推送 provider 均未接入且生产必须 fail closed；推送为 at-least-once 且依赖 provider 稳定幂等键与可信回执；阈值/扫描周期/退避参数仅为联调起点非 SLA；C/D 约两万行业务实现本轮未重新独立审查，集成方仍须在最终合并 SHA 上执行跨包端到端验证；两份交付文档当时仍为 untracked、不属被审 SHA。

**Oracle R4 实际执行的核查命令**（证明审的是 `954c95bf` 真实代码）：`git rev-parse HEAD`、`git log --oneline ccee6e28..HEAD`、`git diff ed5eb865..954c95bf --stat`、`git diff ed5eb865..954c95bf -- …/ObservationSessions.java`、`git show --stat --oneline 954c95b`、`git status --short --branch`、`git diff --check ed5eb865..954c95bf`、`git diff --name-only ed5eb865..954c95bf`（含对 `web/auth/**`、`worker-python/src/mvp_worker/runtime/**`、`deploy/**`、`contracts/**`、`doc/**` 的越界核查，结果为空）、`git grep -n prune 954c95bf -- …/ObservationSessions.java`、`git ls-files -u`；另以只读 `read` 检查全部 8 个变更文件与 APP Principal/session refresh 行为。未修改文件、未执行测试或数据库写入。

### 4.9 第五轮复审（被审 SHA `5f0a988333b86a1198297de257c4952d04ded1d1`，会话 `ora-1`）

**`VERDICT: PASS-with-notes`** —— **(i) B 包门禁结论：通过，有非阻塞披露项**；**(ii) 整体集成就绪结论：尚未就绪**。

**R4 BLOCKER 判定已闭合**（依据 `MicrocrystalService.java:264-317,437-440`、`ObservationSessions.java:18-24,95-127`、`MicrocrystalObservationIT.java:252-288`、`b-checks-1.sh:202-224`）：APP 使用**服务端认证派生**的稳定 `accountUuid:installationId` 作为 generation key，refresh/login 不再新增表项；原复现中第 9 个及后续 session 与前八个命中同一表项，只要 epoch 相同且 seq 递增即接受，不再永久 `TABLE_FULL`。Oracle 并确认"**测试确实覆盖了超过默认上限的不同随机 sessionId，而非通过减少 session 数绕过问题**"。

**四点裁定**
1. **稳定 family + GIMBAL sessionId + JSONB 键沿用 `session_id`：可接受。** 键完全来自认证上下文、不受请求体控制；APP family 虽非通用意义上的"可比较 session generation"，但在"同 installation 是同一持久观察流"的协议约束下足以维持顺序安全；沿用旧键名可避免无必要的格式迁移，**但名称已不准确，应在文档明确其实际含义为 `generation_key`**。附注：旧提交若曾产生随机 APP sessionId 表项，改名并不提供语义兼容，这些旧条目仍占容量；当前接受建立在"中间 SHA 未投入持久生产环境"的前提上，若存在保留数据库需一次性清理/转换。
2. **C25（同 family 固定 epoch、持久单调 seq）：可作为 MVP 非阻塞协议约束，但必须冻结并披露。** 该规则 fail closed、不会使旧状态覆盖新状态；代价是 APP 必须跨登录、token refresh 与普通进程重启持久化 `observationEpoch` 与每微晶 `observationSeq`。**若产品要求重启后允许 seq 从 1 开始，就必须在生产接入前采用 `ConnectionProofVerifier` 返回可信连接 generation，不能让客户端自行换 epoch。**
3. **APP 不同 family 达上限：可作为 MVP 的 fail-closed 残留限制，但描述需修正。** 同一 family 不再耗尽；超过上限个不同 `account:installation` 后未知 family 被安全拒绝。Oracle 明确纠正：**"生产新的 family 可以恢复"不正确**——表满后新 family 正是被拒绝的对象；当前自动恢复只能来自 ① APP/GIMBAL observer **类型**切换造成表重置，或 ② 未来引入可信 generation/受控运维重置。**必须配置告警、容量值和受控恢复 runbook；仅调高上限不是恢复机制。**
4. **两层结论**：(i) B 包门禁**通过**（R4 的 APP 正常 refresh/login 永久耗尽已闭合，本轮未发现新的代码级 blocker；此前 #1/#2/#3/#5/#6/#7、T10/T12 同事务代次守卫及 b37 均维持闭合）；(ii) 整体集成**尚未就绪**（#4 扫描器接入既有 Worker 周期循环并按真实运行形态验证、#8 A 登出递增 `destination_revision`、对已合入 C/D 业务代码在最终 SHA 上执行独立跨包验收、冻结 C25、为 GIMBAL/APP generation 表配置容量告警与受控恢复流程）。C23 的过时 javadoc/死代码与两份 untracked 交付报告**不阻塞 B 代码门禁**。

**R5 新发现**
| 严重度 | 文件:行 | 问题 | 复现 | 建议修法 |
|---|---|---|---|---|
| IMPORTANT | `ObservationSessions.java:45-49` | 注释称 APP 表满后可"生产新的 family"恢复，但 `resolve():110-113` 会拒绝任何未知 family | 填满 8 个 family，再以第 9 个 family 上报，持续返回 `TABLE_FULL` | 修正文档；明确真正的恢复途径与运维 runbook |
| SUGGESTION | `ObservationSessions.java:130-156` | `session_id` 现在可能保存 family，并非 session ID；对旧随机 session 数据仅格式兼容、非语义兼容 | 保留上一 SHA 数据后升级，旧 session 项继续占容量 | 交付文档声明中间版本不得原地升级；如已有持久数据，执行受控转换/重置 |

→ 两条均已在 `f95037e` 以**纯 javadoc 提交**处置（见 §4.10），并由 Oracle 确认"已正确处置"。

**R5 实际执行的核查命令**：`git rev-parse HEAD`、`git log --oneline ccee6e28..HEAD`、`git diff 954c95bf..5f0a988 --stat`、`git diff 954c95bf..5f0a988 -- …/ObservationSessions.java …/MicrocrystalService.java`、`git show --stat --oneline 5f0a988`、`git status --short --branch`、`git diff --check 954c95bf..5f0a988`、`git diff --name-only 954c95bf..5f0a988`、`git ls-files -u`，以及对 `web/auth/**`、`worker-python/src/mvp_worker/runtime/**`、`contracts/**`、`db/migration/**`、`deploy/**`、`doc/**` 的越界核查（结果为空）；另以只读 `read`/`grep` 检查最终 `ObservationSessions`、`MicrocrystalService`、相关 Java 反例测试、HTTP 验收 b8 与权威设计/OpenAPI。未修改文件，未运行测试或写数据库。

### 4.10 第六轮：SHA 重新绑定确认（被审 SHA `f95037e5bbd37742175b52685ca833f91396e00c`，会话 `ora-1`）

因处置 R5 的 IMPORTANT/SUGGESTION 产生了一个**仅含 javadoc** 的新提交，交付 SHA 由 `5f0a988` 变为 `f95037e`，故按门禁纪律请求窄范围重新绑定确认。

**`VERDICT: PASS-with-notes`**，四点确认：
1. **纯 javadoc：确认。** `ObservationSessions.java:44-65` 是 `5f0a988..f95037e` 的**唯一变更**；未修改语句、签名、常量、字段、控制流或测试；`git diff --check` 通过。
2. **R5 IMPORTANT 已正确处置**（`:48-57`）：明确 APP 没有自动恢复途径、新 family 不能恢复、实际可用方案为 observer 类型切换／GIMBAL credential 推进／受控运维重置／未来可信 generation、不提供业务重置 API、调高上限只推迟触顶、必须配置容量告警与恢复 runbook。
3. **R5 SUGGESTION 已正确处置**（`:59-65`）：明确 `session_id` 实际承载 generation key、GIMBAL 与 APP 的值语义不同、中间版本仅格式兼容非语义兼容、**中间版本不得原地升级**、已有持久数据必须受控转换或重置。
4. **R5 的两层结论可原样重新绑定到 `f95037e`**：本次注释修改没有引入执行语义变化或新风险。

**重新绑定后的最终结论**
- **(i) B 包门禁结论 @ `f95037e5bbd37742175b52685ca833f91396e00c`：通过，有非阻塞披露项。**
- **(ii) 整体集成就绪结论：尚未就绪。** 仍需集成方处理：#4 扫描器接入既有 Worker 周期循环；#8 A 登出递增 `destination_revision`；冻结 C25/C26 协议与运维约束；完成 C/D 最终 SHA 的跨包独立验收；落实 generation 表容量告警与受控恢复 runbook。

**是否要求重跑端到端验收：否。** 理由（Oracle 原文）：`5f0a988..f95037e` 只有类级 javadoc 变化，不涉及可执行代码、配置、测试、契约或构建脚本；且 orchestrator 已在 `f95037e` 状态执行 Java 全量 386/0/0。无需为 SHA 重新绑定重复端到端流程。

**新发现：无。**

**R6 实际执行的核查命令**：`git rev-parse HEAD`、`git log --oneline 5f0a988..f95037e`、`git diff --stat 5f0a988..f95037e`、`git diff 5f0a988..f95037e`、`git diff --check 5f0a988..f95037e`、`git status --short --branch`；另完整阅读修改后的 `ObservationSessions.java` 类 javadoc。未修改文件，未运行测试或写数据库。

### 4.11 第七轮：Swagger/springdoc 接入的**有界**复审（被审 SHA `8127be53e6e2c66e30389699dd26429948733f39`，会话 `ora-1`）

范围严格限定为本次 Swagger 变更面（7 个文件），**不重审 R6 已通过的业务代码**。

**`VERDICT: FAIL`** —— 8 项裁定中 6 项通过，1 BLOCKER + 1 IMPORTANT，且明确"**合入 dev / 替换用户预览前必须先修**"。

**通过项（含 Oracle 依据）**
1. **确为代码生成而非渲染手写 YAML**：`OpenApiDocsConfig.java:52-98` 仅创建 OpenAPI 元信息，`:109-137` 仅定制生成后的安全说明；生产代码未读取 `backend/contracts/openapi/openapi.yaml`，仅测试 `OpenApiDocsIT.java:113-135` 读它构造期望路由集合；生成结果 3.1.0 且标题不同于手写 3.0.3 契约，为有效佐证。
3. **业务权限零变化**：未修改任何 auth 文件；`BearerAuthFilter.java:46-69` 的公开端点与文档配置四项一致；全局 bearer + 4 个公开 operation 的 `security: []` 不会误导其他端点；principal 删除只改 OpenAPI 模型、不改请求解析或授权；当前生成路径未发现 actuator、SQL、配置值、堆栈或媒体内容泄漏。
4. **无假业务 200 / 无业务路由变化**：新增路由仅 `OpenApiDocsConfig.java:145-153` 的 `/swagger-ui/` 内部 forward；未新增或修改业务 Controller；forward 仅在文档 bean 启用时存在，不掩盖业务 404。
5. **27/27 证据可信**：`OpenApiDocsIT.java:37,49-57,98-140` 将 method 与归一化 path **共同**作为 key，不会用路径归一化掩盖 HTTP method 错误；仅归一化路径变量名，合理；期望集合来自带 `x-api-id` 的契约 operation 且固定断言数量 27；27 业务 + 7 真实额外 = 34 operations / 33 paths，与总协调独立实测一致；测试断言包含关系而非严格 34 项相等，但授权允许该 7 个已知额外端点，不构成缺陷。
6. **范围基本合规**：`8127be5` 恰改 7 个授权文件；`f95037e..8127be5` 整段为 9 个文件是因含已披露的 `b4917f9` 两份 report-only handoff，非代码越界；未改 auth/`web/error`/`care`/`assessments`/契约/迁移/deploy/`backend/tests`；未重构 C/D DTO。
7. **依赖风险通过（附常规注意事项）**：`pom.xml:23-29,55-62` 用属性锁定 2.8.17；官方 2.8.17 基于 Boot 3.5.13 并升级 swagger-core 2.2.47 / Swagger UI 5.32.2，与本项目 Boot 3.5.16 同线兼容；springdoc 会新增自动配置、资源 HandlerMapping 与模型扫描，但未发现其修改全局 `ObjectMapper`、异常处理或业务 `HandlerMapping`；394 项测试为合理回归证据；建议纳入依赖漏洞监控。

**BLOCKER（必须修）**
| 严重度 | 文件:行 | 问题 | 复现 | Oracle 建议修法 |
|---|---|---|---|---|
| BLOCKER | `DocsProductionGuard.java:22-24` | 生产判定只依赖 `app.env=production`；`prod` profile 被 `app.env=dev` 覆盖时，springdoc 自动配置仍可暴露文档端点 | 以 prod profile、`app.env=dev`、两个 springdoc 开关为 true 启动并提供真实 provider beans；guard 不注册，`/v3/api-docs` 可生成 | 让 guard **始终注册**，运行时以 `environment.acceptsProfiles("prod") || app.env=="production"` 判断；任一生产信号成立且文档开启即拒绝启动；补矛盾配置测试 |
| IMPORTANT | `OpenApiDocsConfig.java:86-94` | "尚未字段级展开"清单不完整，遗漏 `SuccessEnvelope.data`、`ErrorEnvelope.details`、Heartbeat `incidents`、微晶 `capabilities`/`state`、通知 `registration` | 查看生成 schema，上述字段仍为自由 object，但 info 清单未列出 | 改成统一声明"所有声明类型为 `Object`/`Map` 的字段均可能无法展开"，再列举典型字段；**无需重构 DTO** |

**测试充分性：部分不通过**——启用/关闭/27 路由/安全结构/UI forward 的测试均为真实断言、不是摆设；但 `DocsProductionGuardTest.java:21-50` 只测 `app.env`，未覆盖 `prod profile + app.env!=production` 的矛盾配置，故漏掉上述生产绕过；修复后应增加该组合测试，并最好增加 `app.env=production + dev profile` 的明确回归测试。

**orchestrator 独立核实**：该缺口成立且非理论问题——矛盾配置下 `OpenApiDocsConfig` 因 `@Profile({"dev","test"})` 不注册、护栏因 `@ConditionalOnProperty(app.env=production)` 不注册，而 springdoc starter 自身自动配置（`@ConditionalOnProperty(springdoc.api-docs.enabled, matchIfMissing=true)`）仍暴露端点；A 的 `ProductionFailClosedValidator` 亦按 `app.env` 判定故同样不触发 ⇒ 无任何拦截。**不得依赖 A 的校验器偶然先失败。**

**Oracle 要求持续披露的文档准确性限制**：生成文档非权威契约；生成格式 3.1.0 而权威契约 3.0.3；所有 `Object`/`Map` 字段可能只显示自由结构 object（含统一信封与请求字段）；response content type 可能为 `*/*`；operationId 由 Java 方法名生成、未对齐契约；未逐端点附着完整错误码与错误响应集合；**全局 bearer 只表达是否需要 token，不表达 APP/GIMBAL 主体类型、成员授权、当前任务等细粒度权限**；字段与错误码冲突时以 `backend/contracts/openapi/openapi.yaml` 为准；**Swagger UI 只能在 dev/test 暴露，不得用于公网生产环境**。

**Oracle 实际执行的核查命令**：`git rev-parse HEAD`、`git log --oneline f95037e..8127be5`（含 `--decorate`）、`git diff --stat/--numstat/--name-only f95037e..8127be5`、`git diff f95037e..8127be5`、`git show --stat --oneline 8127be5`、`git status --short --branch`、`git diff --check f95037e..8127be5`，以及对 `web/auth/**`、`web/web/**`、`web/error/**`、`care/**`、`assessments/**`、`contracts/**`、`backend/tests/**`、`db/migration/**`、`deploy/**` 的越界核查（结果为空）；另只读检查 7 个变更文件、`BearerAuthFilter`、相关 DTO/信封，并核对 springdoc 2.8.17 官方发布信息。未运行测试、未启动进程、未触碰端口或数据库。

**整改状态**：BLOCKER 与 IMPORTANT 已派回原实施道修复（护栏始终注册 + profile/app.env 双判据 + 矛盾配置与回归测试 + info 统一声明），落地于 **`d3dc853d7ec55ff0fad661a45943e7b60ff12325`**；复审结论见 §4.12。

### 4.12 第八轮：Swagger 整改的**有界**复审（被审 SHA `d3dc853d7ec55ff0fad661a45943e7b60ff12325`，会话 `ora-1`）

**`VERDICT: PASS-with-notes`** —— BLOCKER 与 IMPORTANT **均判定已闭合**，并明确**"可以将 `d3dc853` 合入 dev 并替换开发预览"**。

**BLOCKER 闭合依据（Oracle 原文行号）**：`DocsProductionGuard.java:33-34` 护栏无条件注册、不再依赖 `app.env` 条件装配；`:48-53` `prod` profile 或规范化后的 `app.env=production` 任一成立即进入生产检查；`:55-59,76-78` 两个 springdoc 开关分别检查、**未配置按开启处理**、只有显式 `false` 才放行；`:61-73` 任一开关开启即抛 `IllegalStateException`，**不依赖 A 校验器或 `OpenApiDocsConfig`**；`DocsProductionGuardTest.java:32-68` 覆盖原绕过、单独 UI 开启、缺省开关及反向 profile/env 组合。Oracle 并确认：原复现 `prod + app.env=dev + springdoc=true` 现在必然中止启动，且 `SmartInitializingSingleton` 在 WebServer lifecycle 启动前执行，**不会形成可接受请求的监听服务**。

**IMPORTANT 闭合依据**：`OpenApiDocsConfig.java:60-69,79-89,98-117` 已明确生成文档非权威契约、统一声明所有 Java `Object`/`Map`/`JsonNode` 可能无法字段级展开、覆盖上轮点名的 A/B/C/D 典型字段、明确列举 3.1/3.0.3、`*/*`、operationId、错误码及细粒度权限限制，并保持"从 Controller/DTO 生成、不是手写 YAML 渲染"的准确描述。

**Oracle 对新绕过组合的逐条排查（均不成立）**：api-docs=false+UI=true → 拒绝；UI=false+api-docs=true → 拒绝；环境变量/命令行覆盖 → 最终均进入同一 Environment 属性检查；`app.env` 大小写与首尾空白 → 已处理；`/v3/api-docs/swagger-config`、`/swagger-ui/**` → 两个主开关显式关闭时其 springdoc 映射不会启用。**唯一注意点**：字面 profile `production` + `app.env=dev` 不会被识别，但项目正式 profile 约定是 `prod`，故**不作为 blocker**，建议做别名防御。

**其余裁定**：测试 7 项均为有效状态断言、无放宽，覆盖矛盾配置/缺省语义/单开关/非生产不误伤；非生产环境在 `:52` 直接返回故不误伤；生产两开关显式 false 时正常启动；`application.yml` 只更新说明未改 profile 属性值；未发现对既有业务启动路径的新增影响。Oracle 如实说明：外部启动日志因运行目录权限边界未读取，但**代码与七项隔离测试足以确认核心路径**。

**新发现（2 条 SUGGESTION，非阻塞）**
| 严重度 | 文件:行 | 问题 | 复现 | 建议修法 |
|---|---|---|---|---|
| SUGGESTION | `DocsProductionGuard.java:49` | 只识别正式 profile 名 `prod`，不识别常见别名 `production` | `spring.profiles.active=production`、`app.env=dev`、springdoc=true | 改为 `Profiles.of("prod","production")`，或在部署文档明确只允许 `prod` |
| SUGGESTION | `DocsProductionGuard.java:17` | javadoc 仍链接已删除 import 的 `ConditionalOnProperty`，且"无条件 ConditionalOnProperty"表述含混 | 生成 javadoc 或阅读注释 | 改为"无 `@ConditionalOnProperty` 条件"且不使用未解析链接 |

**orchestrator 处置**：**不改代码**，按文档化披露处理。理由：Oracle 已对 `d3dc853` 给出合入许可，任何代码改动都会使该绑定失效并需再加一轮复审，直接拖延用户查看页面；两条 SUGGESTION 残余风险低（正式 profile 约定为 `prod`、基础 yml 默认关闭、`OpenApiDocsConfig` 仅 dev/test 注册，触发还需显式强开开关）。已记入 `B.md` §11.4 作为后续可选项。

**Oracle 实际执行的核查命令**：`git rev-parse HEAD`、`git log --oneline 8127be5..d3dc853`、`git diff --stat 8127be5..d3dc853`、`git diff 8127be5..d3dc853`、`git show --stat --oneline d3dc853`、`git status --short --branch`、`git diff --check 8127be5..d3dc853`、`git diff --name-only 8127be5..d3dc853`，以及对 `web/auth/**`、`care/**`、`assessments/**`、`contracts/**`、`backend/tests/**`、`worker-python/**`、`db/migration/**`、`deploy/**` 的越界核查（结果为空）；另只读 `read`/`grep` 检查 4 个变更文件。未运行测试、未启动进程、未访问受限协调目录。



## 5. 验证证据（orchestrator 亲自执行，最终状态）

```
Java 全量（于交付 SHA f95037e）：
  Tests run: 386, Failures: 0, Errors: 0, Skipped: 0；BUILD SUCCESS；rc=0
  其中 B 自有 70 项（surefire 逐类核实）：identity 12 / devices 30 / notifications 11 / mediapolicy 17
Python 全量：222 passed / 0 failed / 0 errors；rc=0
  其中 B 自有 6 个文件 47 passed；两种相反文件顺序（D 先 B 后、B 先 D 后）各 113 passed、rc=0
契约四项：openapi_spec_validator OK / validate_responses --selftest 10 checks /
          validate_samples 50 checks / jcs selftest 26 checks，rc 全 0
端到端：  bash backend/tests/run-acceptance-b.sh → RESULT: ALL PASS（39/39）；SCRIPT_RC=0
          （b14：37 条错误信封形状 OK、12 端点全覆盖、所有观测码均属声明集合；
           b36：Java 386/0/0；b37：Python 0 failed/0 errors；b39：整树 tracked 变更前后一致、HEAD 未变）
```

各轮次取数时点：`e6812d49` → Java 198/0/0、Python 84 passed+1 已披露 A 断言、验收 39/39；`7281edd`（合并 `8afd0e5`）→ Java 383/0/0、Python 140 passed+78 errors（根因见下）；`b452d20` → Python 222 passed/0 error；`954c95b` → Java 385/0/0；`5f0a988` → Java 386/0/0、验收 39/39；`f95037e` → Java 386/0/0（纯 javadoc，Oracle R6 明确不要求重跑端到端）。

**期间发现并修正的验收脚本自身缺陷（非产品缺陷，记录以免复现）**
- b04 新增的"缺 Idempotency-Key → 400"用例最初**未携带 `Authorization`**，被 A 的 `BearerAuthFilter` 先拦成 401；修正为带合法 token、仅省略幂等键。同次运行并证明"他人/不存在 404 掩蔽 `requestId` 后逐字节一致"成立（`diff` 为空）。
- b23 的旧断言"同会话新 epoch 小 seq → `accepted=true`"正是 #2 关闭的回滚攻击，属**过时断言**；已改写为新权威模型，并同步修正汇总表描述文字。
- b23 改写时我一度把"同一会话续报"误写成换 epoch（`eA/100`）导致假失败；修正为同 epoch 递增 seq（`e1/100`），并补"旧会话改换 epoch 伪造新来源亦被拒"。
- b17/b20/b21 的 fixture 原按 B 旧的"宽容读取"约定播种 `report_payload`（`public_media_ids`/`photos[].public`），裁定③收紧为 D 冻结格式后产品代码正确拒绝、fixture 过时 ⇒ 4 项 FAIL；改为 `images[].media_id` 后全绿，b20 判别力改以"未引用 404 → 引用后 200"表达。
- b33 原断言"首次 unknown → T10 = `unknown`"与裁定后的新语义不符（非末次不提前终态化、保持 `sending` 可观测态）；改为断言可观测态，并**新增末次收敛的端到端证据**（`max_attempts=1` → T10 `failed` + T12 `failed` 同时落库 + `attempt_count=1` 无重复发送）。
- b37 原硬编码"恰好 1 个失败且必须是 `test_config_defaults`"，合并后该 A 断言已 4/4 通过 ⇒ 改为硬断言 `rc==0`/`failed==0`/`errors==0`/`passed>=200`（Oracle R3 IMPORTANT，R4 判闭合）。
- b08 新增 APP family 回归锁（同 account+installation 连续 10 个 session 全部接受、`observer_sessions` 表项恒为 1），锁定 Oracle R4 BLOCKER。
- `B_ACCEPT_FILTER` 单独运行 b4 会因缺少 b1 产生的 `$TMP/b1.grant` 前置数据而假失败；单独运行 b33 需其自建 fixture，无此问题。已在 `B.md` 第 8 节注明。

**数字纪律**：Java 逐类 surefire 累加曾得 387 而 mvn 汇总为 386，经查是 `target/surefire-reports/` 中一份**陈旧报告**（`MediaPolicyDelegationIT`，其源文件已在媒体策略收紧时删除、由 `MediaPolicyNoDelegationIT` 取代）造成的幻影 +1；已清除该构建产物（`target/` 属 gitignored，不在提交面内），逐类累加与汇总一致为 386。Python 全量曾出现 78→51 个 fixture ERROR，根因是 D 的 `tests/d_support.py:59 clean_d_tables()` 直接 `DELETE FROM gimbals` 与 B 的 `notifications_gimbal_id_fkey` 冲突（顺序依赖：D 文件单跑全绿）；B 未改任何公共/D 文件，改以自有 `tests/b_support.py` 按 FK 顺序只清 B 自己以前缀标识的行 ⇒ 全量 0 error。Oracle R3 判定该处置**可接受、不属用测试技巧掩盖生产缺陷**；纵深防御建议留待 D/公共评估（C22）。

## 6. LSP 假报的裁定记录（避免后续误改已通过代码）

编辑过程中 IDE 的 Eclipse LSP 多次对**已通过真实 javac 的文件**报语法错误与"Duplicate method"。已用三重证据判定为陈旧索引假报，不据此改动任何代码：
1. 真实构建：`mvn -B test` 于交付 SHA `f95037e` 报 `Tests run: 386, Failures: 0, Errors: 0`、`BUILD SUCCESS`、rc=0（历轮各 SHA 均由 orchestrator 亲跑，且验收脚本 b36 内再跑一次，数字一致）；
2. 报错行号越过文件末尾：`AuthFlowIT.java` 实为 247 行而报错至 271 行；`NotificationDestinationsIT.java` 实为 480 行而报错至 501 行；`GimbalHeartbeatIT.java` 实为 231 行而报错至 268 行；`StubEndpointsIT.java` 实为 168 行而报错至 210 行；
3. "Duplicate method" 实测各方法只出现 1 次（`revokedSessionRejected` 在 `NotificationDestinationsIT` 计 1、在 `GimbalHeartbeatIT` 计 0；`statusRevisionOnlyOnConnectionChange` 反之；`routeTable`/`patterns`/`normalize` 在 `StubEndpointsIT` 各计 1 处定义），且对应 `.class` 文件由真实编译正常产出。

**但 LSP 也曾报出一个真实错误，必须区分对待**：`StubEndpointsIT` 中我写的 `RequestMappingInfo.getPatternCondition()` 在 Spring Framework 6 已被移除——这是**真实编译错误**，由 `mvn -o test-compile` 的 javac 明确报出（`cannot find symbol`）并修正为只读 `getPathPatternsCondition()`。结论：**一律以真实 javac/mvn 为权威**，LSP 只作提示；既不据 LSP 假报改动已通过代码，也不因 LSP 多为假报而忽略其命中的真实问题。

（A 包历史上亦出现同类 LSP 工件问题，其 `f7e75c1` 提交即"清理误提交的 Eclipse LSP 工件"；B 各次提交均经工件核查，`.pyc`/`__pycache__`/`.class`/`target/`/`.log`/`backend/tests/.work/` 命中 0。）

## 7. 残留限制（非阻塞，必须在交付文档披露）

见 `backend/handoffs/B.md` 第 6 节（**16 项**）。Oracle 历轮明确要求披露的要点：

- **C25（需总协调冻结）**：APP 同一 family 必须保持 `observationEpoch` 不变并**持久化单调 `observationSeq`**（跨登录/refresh/普通重启）；重启后不得把 seq 归 1 或自行换 epoch，否则上报被拒。Oracle R5：可作为 MVP 非阻塞约束但**必须冻结并披露**；若产品要求重启后 seq 从 1 开始，**必须在生产接入前**改用 `ConnectionProofVerifier` 返回可信连接 generation。
- **C26（运维必须配套）**：GIMBAL 会话表满后未见 session 被 fail closed 拒绝、不刷新 `last_seen_at`，可能触发误离线通知；唯一自动恢复是 `credential_version` 推进（凭据轮换/重新配网）。生产初值建议评估 **32~64**、配置表满告警（warn 分支 `session-table-full-fail-closed`）、提供凭据轮换 runbook。**APP 侧没有自动恢复途径**——Oracle 明确纠正"生产新 family 并不能恢复"；实际手段仅 observer 类型切换清表、GIMBAL 凭据推进、受控运维重置（不提供业务 API）、或未来可信 generation 取代本表。**仅调高上限不是恢复机制。**
- **升级约束**：JSONB 键 `session_id` 实际承载 generation key（GIMBAL=随机 sessionId，APP=稳定 family），与早期中间版本**仅格式兼容、非语义兼容**；**中间版本不得原地升级**，已有持久数据须受控转换或重置。
- **T10 可观测性变化**：不再主动写 `unknown`；不确定态表现为 T10 `sending` + T12 `last_error=delivery_unknown`，需结合 T12 判断，仅看 T10 无法区分"发送后崩溃"与"provider 返回 unknown"。
- **#4 扫描器周期触发未接入既有 Worker**（未闭合的集成依赖，归总协调）：B 只维护可重入 `run_once` 与 `--once` CLI，验收以 CLI 驱动，**不代表生产周期运行形态**；须由总协调按 `scanner-integration.md` 接入并实际验证离线检测后，整体功能才可宣称验收通过。**不删除、不视为已通过。**
- **#8 A 登出失效不递增 `destination_revision`**（A 归属待修）：B 侧投递安全已闭合（探针要求 active + 锁内 `status != active → destination_changed → cancelled`），残余仅"登出瞬间代次数值不变"。
- 真实人脸/推送/会话/设备凭据/连接与配对证明提供方全部未接入（明确命名替身 + 生产 fail-closed）；阈值为联调起点非承诺；推送为 at-least-once、依赖 provider 稳定幂等键与可信回执，已受理消息不可撤回；微晶 capabilities/设备异常枚举/推送 registration 仍为 skeleton 协议；C/D 约两万行业务实现历轮均未重新完整独立审查，集成方须在最终 SHA 上执行跨包端到端验证。

## 8. 调用真实性声明

本文件所有 Oracle 结论均来自 orchestrator 通过 `task(subagent_type="oracle", task_id="ses_f70bc47c3ffeLASOzFOAJZPUO8")` 的**实际调用返回**（六轮全部复用同一 `ora-1` 会话以保留历轮发现上下文），并记录真实会话 id 与每轮被审 SHA（`git rev-parse` 输出）。无工具结果不声称任何调用或结论；Oracle 不可用/失败/无结论时记 `blocked` 并如实汇报，不以其他模型或自评冒充 Oracle；Oracle 返回的判定均按其原文引用，未作美化或删减（包括对我自己决策的批评，例如 R4 指出 APP 耗尽 BLOCKER 系我 R3 选择方案②时引入、R5 纠正我"生产新 family 可恢复"的错误表述）。

六轮结论：R1 `0f933fc6` **FAIL**（7 BLOCKER + 2 IMPORTANT）→ R2 `e6812d49` **FAIL** → R3 `ed5eb865` **FAIL** → R4 `954c95bf` **FAIL** → R5 `5f0a988` **PASS-with-notes** → R6 `f95037e` **PASS-with-notes（重新绑定确认，新发现：无）**。

**最终门禁结论（绑定交付 SHA `f95037e5bbd37742175b52685ca833f91396e00c`）**：
- **(i) B 包门禁 = 通过，有非阻塞披露项。**
- **(ii) 整体集成就绪 = 尚未就绪**，需集成方完成：#4 扫描器接入既有 Worker 周期循环并按真实运行形态验证；#8 A 登出递增 `destination_revision`；冻结 C25（APP 观察流持久化协议）与 C26（generation 表容量告警 + 受控恢复 runbook）；对已合入的 C/D 业务代码在最终 SHA 上执行独立跨包验收。

本报告为 report-only 提交，不改动任何产品代码；按门禁纪律，纯报告提交不循环审查自身。
