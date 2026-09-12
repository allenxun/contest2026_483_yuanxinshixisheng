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

### 4.13 第九轮：公共集成修复轮的**有界**复审（被审 SHA `2d6c7231f2d2aa58ec0501e8550a0f35b8bd2533`，会话 `ora-1`）

总协调本轮指定 **B 为公共集成修复唯一实施负责人**（不恢复 A/C/D 会话），授权三项：① B 的可重入 incident scanner + D 已有 `media.cleanup` 候选发现接入既有 Python Worker 的**有界周期调度**；② Java 登出失效通知目标时**同事务递增 `destination_revision`**（= Oracle 此前提出的 #8）；③ 修 E 报告 **CC-11 的 13 处 OpenAPI 建模缺陷**。审查范围限定本轮三项 + 基线合并，**不重审** R6 已通过的 B 业务代码与 R8 已通过的 Swagger。

**`VERDICT: PASS-with-notes`** —— 三项授权目标**均已正确实现、无代码级 blocker**，并明确 **"可以合入 dev"**。

**19 点逐条裁定（全部通过，含 Oracle 依据行号）**
- **项 1（`2d6c723`）**：①**已真实接入既有 Worker**——`runtime/loop.py:60-66,227-249` 在 `run_forever()` 内构建并调用 `scanner.run_due()`，"不是用 CLI 冒充生产接入"，未新增进程/线程/cron/服务/队列；②**租约与失败事务语义未变**——`process_job()`、`run_cycle()` 及 `claim`/`complete`/`renew`/`expire`/`rows`、handler 注册表均无 diff，`business_tx` 与 lease generation 守卫原样；③**候选分页有界成立**——`incident_scanner.py:102-139,202-228` 三段 SQL 均为 UUID keyset + `ORDER BY id LIMIT`、满页推进/尾页归零，生产 scheduler 始终传显式 limit（`scheduler.py:150-159`），`limit=None` 只保留直接函数兼容、CLI 默认也已传配置 limit（`scanners/__init__.py:33-48`）；④**重入安全成立**——`scheduler.py:47-70` 非阻塞 Lock，生产同线程调用不会重叠，多实例继续依赖原有行锁/revision/dedup，"不新增错误的分布式锁"；⑤**网络仍在锁外**——回调只做候选发现与 DB 入队，真正存储删除仍在 `media_cleanup.py:216-222` 的业务事务外；⑥**C7 红线保持**——`incident_scanner.py:102-119,257-303` 仅读 `last_seen_at`、UPDATE 不含该列，测试见 `test_scanner_scheduler.py:230-242`；⑦**停机及时**——`loop.py:243-249` 用 `stop_event.wait()`，扫描间隔不会变成不可中断 sleep（正在执行的同步扫描须完成后退出，属既有限制）；⑧**`ScanReport`/CLI 兼容**——仅追加 `scan_limit`（`incident_scanner.py:45-84`），既有字段未改，`--once/--loop` 退出语义未变且 CLI 扫描现默认有界。
- **项 2（`d0e9b84`）**：⑨**原子 UPDATE 正确**——`AuthController.java:203-209` 一条 SQL 同时置 invalid、写时间并 `destination_revision + 1`，不存在 DB 内"已失效但代次未变"中间态；⑩**幂等/竞态正确**——`WHERE session_ref=? AND status='active'` 只递增一次、无先查后改、已 invalid 行不刷新时间；⑪**HTTP 行为不变**——`:128-137` 仍 204 无体，T09 失败不反转已完成的会话撤销，日志不再记录 session_ref/token；⑫**一致性边界表述准确**——注释只声称"T09 状态与 revision 在同一原子 UPDATE"，**没有**声称与 `SessionProvider` 撤销同一事务；⑬**既有登记/投递代次语义未削弱**——`NotificationDestinationService` 与 Python 投递 handler 无 diff；⑭**测试有效**——`LogoutDestinationRevisionIT.java:93-234` 分别覆盖恰好 +1 与 204、重复/已 invalid 不递增、旧 T10 快照与当前 T09 代次失配、新会话重新登记继续 +1，且未修改既有断言。
- **项 3（`2bd768a`）**：⑮**13 个已报告缺陷均正确修复**——`Verification.validUntil`（`openapi.yaml:2052`）、`Progress.completedAt`（`:2069`）、`ProgressWithSync` 展平（`:2070-2087`）、`ControllerRef.gimbalId`（`:2475`）、`CareExecutionListItem.closedAt`（`:2666`）；⑯**严格性保持**——`ProgressWithSync` 显式保留七个属性、原 `required` 集合与 `additionalProperties:false`，未删除父 schema 严格约束，状态码/`operationId`/`x-api-id`/`x-error-codes` 及响应引用链均未修改；⑰**未修改 E 验收资产**——`backend/acceptance/**`、`backend/tests/**` diff 为空；⑱**剩余旧式 nullable 可按本轮授权只披露**——`ProgressWithSync.targetCount` 仍在 `:2081`，但当前 M4-A08 只允许 ready plan（`CareQueryService.java:195-218` 拒绝非 ready，ready 行要求 `targetCount` 非空），故 A08 成功响应不会触发该 null 缺陷，**不是本轮 blocker**，应纳入统一契约治理；⑲**E 自检应由 E/集成方更新**——`test_framework_selfcheck.py:943-960` 明确断言旧 additionalProperties 缺陷存在，修复后失败是预期；`c_care.py:98-154` 的 13 项 allowlist 已陈旧；**B 不应重新制造缺陷或擅改 E 文件**，E 应把自检改为断言已无该错误并清理对应 allowlist。

**新发现（1 IMPORTANT + 4 SUGGESTION，均非 blocker）**
| 严重度 | 文件:行 | 问题 | Oracle 建议 |
|---|---|---|---|
| IMPORTANT | `incident_scanner.py:389-422` | `LIMIT` 只约束 **gimbal 候选数**；单个 gimbal 的 `active episodes × active destinations` 扇出无总预算 ⇒ 单轮总事务/通知数并非严格有界（复现：`limit=1` 但为该 gimbal 准备大量 active episodes 与 destinations，仍处理全部组合） | 后续增加每轮总工作预算或对 episode/destination 分页；**MVP 可暂按运营规模接受并监控** |
| SUGGESTION | `scheduler.py:58-70` | `due_at` 按回调**开始前**的 `now` 顺延；回调耗时超过 interval 时下一轮立即再次到期 | 改为回调结束时的 monotonic + interval，**或明确这是 fixed-rate/best-effort** |
| SUGGESTION | `scanners/__init__.py:3-4,25` | 注释仍称"由总协调接入/本轮不接入部署"，与已接入现状不符 | 更新注释，不改行为 |
| SUGGESTION | `contracts/decisions-notes.md:179` | 仍写 36 处旧 nullable，当前已减少 | 由契约所有者更新剩余计数 |
| SUGGESTION | `NotificationDestinationService.java:35` | 注释仍以"登出不改代次"为现状前提 | 由 B/集成所有者更新为当前 +1 语义 |

**对 orchestrator 已披露待协调项的裁定**
| 项目 | Oracle 裁定 | 负责人 |
|---|---|---|
| D 候选发现有 `LIMIT` 无 keyset（头部永久安全跳过项可致后续候选饥饿） | **非阻塞但应修**；影响清理及时性/存储回收，**不造成误删**；调 batch 不能根治永久头阻塞 | D/集成方增加 keyset 或排除已证明不可清理的候选 |
| `gimbals.active_incidents` 长期保留 resolved episodes | **非阻塞 MVP 残留**；增加 JSONB 体积、候选扫描与通知延迟，但 active 过滤避免误通知 | 集成/数据所有者设计压缩、索引或迁移 |
| `worker-python/tests/conftest.py` 只认 `MVP_A_PG_*`（默认 55432） | **非生产阻塞，测试基础设施应修** | 共享测试基础设施所有者 / A 或总协调 |
| `NotificationDestinationService` 旧注释 | **非阻塞文档修正** | B/集成方 |
| C25 / C26 | **维持非阻塞待冻结项** | 总协调、APP/设备协议提供方 |

**合入许可与附带条件（Oracle 原文）**：**可以合入 dev**。需注意：①合入后 E 的一项旧缺陷自检会**按预期失败**，E/集成方必须同步更新其期望，之后才能宣称整体验收全绿；②incident scanner 的总扇出不是绝对硬上限，作为 MVP 运维限制接受，但应进入后续预算化治理。

**Oracle 要求持续披露的残留限制**：incident scan 的候选 gimbal 数有界但 episode×destination 总扇出尚无全局预算；D cleanup discovery 无 keyset 可致头部饥饿；resolved episode 不自动压缩、规模增长会延长扫描周期；Worker 停机可立即打断等待但不能中断正在执行的同步 DB 扫描；剩余旧式 `allOf/$ref + nullable` 尚未全量治理（含 `ProgressWithSync.targetCount`）；E 的 CC-11 allowlist/selfcheck 必须随契约修复更新；登出的会话撤销与 T09 更新**不是跨资源同一事务**，T09 SQL 失败依赖既有补偿与投递侧 fail-closed；C25/C26 仍待冻结。

**Oracle 实际执行的核查命令**：`git rev-parse HEAD`、`git log --oneline 551f166..2d6c7231`、`git diff --stat 39adc57..2d6c7231`、`git diff 39adc57..2d6c7231`、`git show --stat --oneline 2bd768a d0e9b84 2d6c723`、`git status --short --branch`、`git diff --check 39adc57..2d6c7231`、`git show -s --format='%H%n%P%n%s' 39adc57`、`git diff --unified=30 … -- backend/contracts/openapi/openapi.yaml`，以及对 `backend/acceptance/**`、`backend/tests/**`、`backend/handoffs/**`、`**/db/migration/**` 的越界核查（结果为空）与对 `runtime/claim|complete|renew|expire|rows.py`、`handlers/__init__.py`、`handlers/media_cleanup.py`、`handlers/notification_deliver.py`、`NotificationDestinationService.java` 的"应无 diff"核查；另只读检查全部 10 个变更文件、D 的 cleanup handler、通知登记服务与 E 的陈旧 CC-11 自检。未运行测试、未启动进程、未执行 `backend/acceptance/**`。

**纯注释后续提交与重新绑定**：orchestrator 据 4 条 SUGGESTION 中"注释与现状不符"的 3 条（其中 2 条 Oracle 判给 B）做了**纯注释/文档**提交 **`c59a18bac95dae3e262f06d93993cee85b5a620b`**（`scanners/__init__.py` 模块 docstring 与 `--loop` 帮助文本、`scheduler.py` 的 fixed-rate/best-effort 语义说明、`NotificationDestinationService` 类 javadoc、`decisions-notes.md` 遗留计数 36→**32** 并给出 `36−5+1` 沿革）。自证零行为变更：Java 侧该 diff 的**非 javadoc 行数为 0**、Python 侧仅 docstring/注释/`help=` 文本、契约侧**只有 `decisions-notes.md`（`openapi.yaml` 未在 diff 中）**；相称验证为 `py_compile` OK、定向 pytest **13 passed rc=0**、`--once` **rc=0**、`mvn -DskipTests compile` **rc=0**。**IMPORTANT（扇出预算）未修**，理由：需设计决策（每轮总工作预算或 episode/destination 分页）属业务规则变更、超出本轮授权且风险不对等，已按 Oracle"MVP 可暂按运营规模接受并监控"的裁定如实披露并移交集成方。

**重新绑定结论（`c59a18b`）：`VERDICT: PASS-with-notes`**，Oracle 明确 **"可以将 `c59a18b` 合入 dev"**、**"不要求重跑端到端验收"**、"B/Public-integration 代码门禁维持 PASS-with-notes"、"整体集成仍需 E 更新已过时的 CC-11 selfcheck/allowlist，之后才能宣称全部集成验收绿色"。五点裁定：①属文档性变更、无业务/调度语义变化（4 文件、39 增/17 删、`git diff --check` 通过；Java 仅 javadoc、Markdown 仅说明文字、scheduler 仅注释；并诚实指出 `scanners/__init__.py:1-11,32` 的模块 docstring 与 argparse `help=` 是**运行时字符串**、会改变 `__doc__`/`--help` 输出，但不改变参数解析、控制流、配置、退出码或扫描行为；OpenAPI YAML、配置值、函数签名、常量与业务语句均未修改）；②三条注释类 SUGGESTION 中 `scanners/__init__.py:1-11,46-47` 与 `NotificationDestinationService.java:32-43` **已正确处置**（准确说明已接入既有 Worker、CLI 仅供验证排障、未新增生产进程/cron；登出 +1、幂等守卫、旧快照失配与重新激活语义均准确），`scheduler.py:55-61` **主要问题已说明但措辞仍可更精确**；③**32 处计数准确**——Oracle 只读递归检查最终 `openapi.yaml`，实际命中**恰好 32** 个"`nullable=true`、无本地 `type`、含 `allOf/oneOf/anyOf`"节点，与 `decisions-notes.md:178-204` 的 32 项清单**逐项一致**，`36−5+1=32` 沿革成立、**没有虚报或漏报**；④扇出 IMPORTANT 的处置**可接受**（维持上轮裁定：候选行分页有界但 episode×destination 总扇出无硬预算；需业务预算/分页设计，不要求在本次纯文档提交或合入 dev 前修复），并提醒 `B.md §12.5` 当时仍是未提交修改、**交付前必须经 report-only 提交纳入版本记录**；⑤结论可原样重新绑定到 `c59a18b`，定向编译/测试已足够，**无需再次执行完整 39 项端到端验收**。

**Oracle 该轮唯一新发现（SUGGESTION）**：`scheduler.py:57-61` 的"fixed-rate""不跳过周期"不完全准确——实现会**合并**回调期间错过的周期（复现：interval=30s、回调耗时 95s，结束后只立即执行一次、不补跑两个错过周期），建议改为"best-effort start-to-start；超时立即再到期；错过周期合并、不追赶补跑"。

**Oracle 该轮实际执行的核查命令**：`git rev-parse HEAD`、`git log --oneline 2d6c7231..c59a18b`、`git diff --stat 2d6c7231..c59a18b`、`git diff 2d6c7231..c59a18b`、`git diff --check 2d6c7231..c59a18b`、`git show --stat --oneline c59a18b`、`git status --short --branch`、`git diff -- backend/handoffs/B.md`；另执行只读 Python/YAML 递归检查确认旧式 nullable 节点数为 32，并 `read` 核验四个修改文件。未运行端到端验收、未启动进程、未写数据库。

**注释精确化提交 `76a01f06a5ac015f243d277db66c99dea8a01004`**：orchestrator 认为"事实性错误注释"正是本轮刚修掉的那类缺陷、不应自留，故**严格按 Oracle 给出的措辞**更正 `scheduler.py` 的调度语义注释（删除不准确的 "fixed-rate"/"不跳过周期"；改为①回调耗时超过 `interval` 时回调结束后下一轮立即到期、不补偿漂移，②回调期间错过的多个周期**合并为一次**执行、**不追赶补跑**，并附 interval=30s/回调 95s 的具体例子；保留"叠加并发由非阻塞守卫排除"与"若需固定延迟语义应在 finally 改用回调结束时的 monotonic 时间"两条既有说明）。自证零行为变更：该 diff 中**非注释行数为 0**（全部以 `#` 开头）、`py_compile` OK、定向 `pytest tests/test_scanner_scheduler.py` → **8 passed rc=0**。

**最终重新绑定结论（`76a01f0`）：`VERDICT: PASS-with-notes`，新发现：无。**

三点裁定：①**确认仅修改注释**——`c59a18b..76a01f0` 仅修改 `scheduler.py:57-63` 的 `#` 注释，未触及语句、签名、常量、控制流、配置或契约，`git diff --check` 通过；②**新措辞准确**——与实现 `scheduler.py:66-78` 一致（`due_at = now + interval` 使用尝试开始前的 `now`），正确说明超时后立即到期、错过周期合并且不追赶补跑，30 秒间隔/95 秒回调的示例准确，非阻塞重入守卫及未来 fixed-delay 修法说明均保留；③**原结论可原样重新绑定**——B/Public-integration 代码门禁维持 **PASS-with-notes**、可以合入 dev、不要求重跑端到端验收、E 仍需更新过时的 CC-11 selfcheck/allowlist。

**最终交付与验收（Oracle 原文）**：**可以将 `76a01f06a5ac015f243d277db66c99dea8a01004` 作为本轮最终交付 SHA 合入 dev**；**不要求重跑端到端验收**（差异仅为注释，执行语义完全未变）；工作树中的 `B.md`、`B-oracle.md` 修改不属于被审 SHA，应按既定 report-only 流程单独处理。

**轮次边界声明（Oracle 原文）**：**`76a01f0` 为本轮最终交付 SHA，无需再因纯注释/文档措辞发起新的重新绑定轮次。**

**持续披露的残留限制**：与上轮一致，**已消除**唯一的 scheduler 语义措辞不准确项；仍需披露——incident 的 `episode×destination` 总扇出没有硬预算；D cleanup 无 keyset、存在候选饥饿风险；resolved episode 不自动压缩；仍有 **32 处**旧式 nullable；E 的 CC-11 selfcheck/allowlist 待更新；会话撤销与 T09 更新不是跨资源原子事务；C25/C26 协议、容量告警及恢复 runbook 待冻结。

**Oracle 该轮实际执行的核查命令**：`git rev-parse HEAD`、`git log --oneline c59a18b..76a01f0`、`git diff --stat c59a18b..76a01f0`、`git diff c59a18b..76a01f0`、`git diff --check c59a18b..76a01f0`、`git show --stat --oneline 76a01f0`、`git status --short --branch`；另只读检查最终 `scheduler.py:47-78`。未修改文件、未运行测试、未启动进程。

**本轮 Oracle 调用小结**：公共集成修复轮共 **3 次实际调用**（`2d6c723` 有界复审 → `c59a18b` 窄范围重绑定 → `76a01f0` 最终窄范围重绑定），全部为真实只读审查、均给出可核查的文件:行依据与实际执行命令清单，三次结论均为 **PASS-with-notes** 且明确许可合入 dev；无任何轮次以"内容评估"替代 SHA 绑定。

### 4.14 第十/十一轮：测试注入缝轮（6+1 项 `seam_pending`）的有界复审（会话 `ora-1`）

**第十轮 —— 被审 SHA `f4b9546ae17a2b36739b4e72690681e3333556cd`：`VERDICT: FAIL`，明确"不可合入 dev"。**
- **判为通过**（含依据行号）：业务 handler/runtime/notifications/Java 业务包/配置/资源/契约/迁移 **diff 均为空**；注入仅改变 doubles（`providers.py:499-575`、`media/storage.py:23-26,72-79`、`FileSystemStorageDouble.java:70-123`）；未增错误码/表/列/迁移、未放宽业务条件；默认值与原行为一致（`application.yml` 未改）；生产信号覆盖解析环境 + 三组 raw env + `prod/production` profile（`dconfig.py:183-225`）、启动校验早于 DB/健康端口（`__main__.py:25-40,124-128`）、Java 矛盾组合在 bean 装配期失败（`TestDoubleProvidersConfig.java:56-82`）；无任何 HTTP 可开启路径；质量缝/身份缝/补拍态入口/plan 确定性超时均通过；Java purpose 白名单由 `MediaPurpose.values()` 派生、key 第二段与 `MediaService.java:63-72` 一致；`f4b9546` 删端口探针改为验证 root cause 与 `storagePort` bean 创建失败**属加强而非弱化**。
- **BLOCKER**：进程级 hold 不满足 SC-02-09 的黑盒时序要求——hold 只是立即抛 `ProviderUnavailable`（`providers.py:546-557`），被重驱时会**重新读取当前 DB 输入**，故证明的是"陈旧代次被忽略"而非"旧版本已算出的结果迟到返回"；handler 在调用 provider 前已把 T05 置 `analyzing`（`assessment_analyze.py:63-69,239-286`），而 HTTP 补拍只允许 `needs_retake`（`AssessmentAcceptanceService.java:241-251`）；且其定向测试直接 seed 新报告并手工 enqueue 旧 revision，**正是清单禁止作为唯一证据的 DB 伪造迟到**。Oracle 明确：**不要直接扩展 SkinPort**（task/revision 不是供应商职责）。
- **IMPORTANT**：布尔注入值不严格校验，未知值静默当 false（`dconfig.py:148-152`、`:163-180`、`storage.py:23-26`），`MVP_D_FACE_DOUBLE_SAME_PERSON=bogus` 会**静默触发 NOT_SAME_PERSON 分支**；`REQUIRED_VIEWS=,,,` 不失败。
- **2 SUGGESTION**：`FileSystemStorageDoubleFailModeTest.java:99` EOF 多余空行致 `git diff --check` 非零；范围声明称 13 个文件、实际 12。
- **orchestrator 的自我更正（重要）**：我曾断言该交错"经真实 HTTP+worker 结构性不可达"，依据是 `_MARK_RETAKE` 经 `business_tx` 与 `complete_success` 同事务原子提交（`runtime/complete.py:187-189`）、`_mark_analyzing` 为自有短事务（`assessment_analyze.py:239-241`）、A02 要求 `needs_retake`。**该论证范围有误**：未覆盖**租约过期后由另一执行者接管同一旧任务**。总协调指出该候选后，我复核源码确认可达（`expire.py:41-47` + `recover_expired:87`、`claim.py:26-41` 的 `lease_revision+1`、`complete.py` 的 `StaleGeneration` 整体回滚、`assessment_analyze.py:176-190` 的 `analyze.fenced_write_stale`、`_publish:705-727` 双重守卫），并据此实现 barrier。

**整改提交**：`d312d2a`（EOF 空行）→ `40f5fde`（严格布尔解析，闭合 IMPORTANT）→ `181676d`（真实迟到返回 barrier + SC-02-10 确定性终态失败）→ `8343ba5`（工装 b40/b41 端到端）。

**第十一轮 —— 被审 SHA `8343ba5a4dd9ee611da979617d2982943fc61af9`：`VERDICT: PASS-with-notes`，明确"可以合入 dev"。**
- **21 项逐条裁定全部闭合/通过**，关键项：①`LateReturnBarrier`（`providers.py:168-227`）先构造结果再等待、`O_CREAT|O_EXCL` 独占、接管者见 `consumed` 立即返回、monotonic deadline 有界、`finally` 清理两个 sentinel、**不接触 DB**；②`FaceDouble.quality()`（`:264-275`）先构造 `QualityResult` 再调 barrier，命中依据输入字节 SHA-256（`:191-198`），**未修改 FacePort 签名**；③assessment handler、claim/recover/complete/renew 与 A02 **均未修改**，b40 用短 lease + 延迟续租模拟 renewer 未及时成功，**仍走真实回收、`lease_revision+1` 与完成围栏，没有绕过 DB 租约机制**；④`test_seam_boundary_repro.py:159-282` 真实调用 claim/recover/handler/complete，`:111-138` 仅铺初始 fixture、**时序状态由实际 Worker 路径产生**；⑤`b-checks-3.sh:384-503` 完整实现 A01→A 在飞→recover→B 接管写 `needs_retake`→A02 v2→C 发布 v2→release→stale fence→快照保持，**没有通过直接更新 T05/T12 伪造阶段**；⑥新增区无直接时序状态写入、排队清理由真实 `--once` 完成、`run-acceptance-b.sh:233-258` 与 `b-checks-3.sh:373-382` 均回收 Worker A；⑦**b1–b39 逻辑未删弱**；⑧⑨⑩严格布尔解析闭合（`dconfig.py:175-203`、`:222-242,364-403`、`storage.py:23-33` 复用同一解析；`_env_list` 对 `,,,` fail fast；旧 `_env_bool` 仅余 `MVP_D_ALIYUN_ACTIVATED`）；⑪⑫SC-02-10 仅改 `SkinDouble` 输出、仍由 `_validate_metrics` 进入**既有** `PROVIDER_CONTRACT_VIOLATION` 终态（`assessment_analyze.py:282-305`），三种 invalid 均**第一次执行确定终结**（`attempt=1`）；⑬⑭五个新旋钮均在 `DOUBLE_INJECTION_SWITCHES`（`dconfig.py:107-128`），校验见 `:427-469`，未新增 HTTP 面、默认值保持原行为。
- **能力结论（Oracle 原文）**：**SC-02-09 与 SC-02-10 的注入能力已就绪、可由 E 黑盒驱动**；b40 已证明真实 HTTP、lease 回收、接管、v2 完成与旧执行迟到围栏；SC-02-10 可在首次实际 worker 执行中稳定进入既有 `PROVIDER_CONTRACT_VIOLATION` 终态并由 HTTP 读取安全投影。**最终场景 PASS 仍应由 E matrix 独立结算。**
- **对 15–21 的裁定**：barrier 超时后重试会再等一个有界 timeout = **可接受但须持续披露**；timeout 非数字抛裸 `ValueError` = **非阻塞**（建议统一包装）；双重围栏取证口径 = **代码路径充分、验收断言可加强**；Worker C 有界多轮 + 零 backoff = **可接受**（测试配置而非业务修改）；保留 `MVP_D_SKIN_DOUBLE_HOLD` = **可接受**（但文档需避免把 HOLD 描述成真实迟到返回）；以「唯一 T05 + 唯一 `report_ready` + 完整快照不变 + `members` 不变」等价断言"无第二报告/未覆盖" = **充分**；上轮 19–22 项 = **维持非阻塞裁定**。
- **3 项新 IMPORTANT + 1 SUGGESTION（Oracle 判"不改变生产业务正确性、不构成合入阻塞，但前三项应在 E 最终矩阵结算前修正或明确接受测试约束"）**：
  1. `b-checks-3.sh:481-488`：b40 **忽略 Worker A 的退出码**，且日志正则允许任意 `StaleGeneration` 字样或 DEBUG 事件 ⇒ 若 A 因未处理异常非零退出，只要快照未变且日志含该词，**b40 仍可能通过**。修法：`wait "$pid"` 须返回 0，并精确断言 `job.complete_stale_generation`。
  2. `test_seam_boundary_repro.py:392-406` 与 `b-checks-3.sh:526-529`：`owner_id=assessmentId` 的 job 计数**不能**证明无 `identity.enroll`/`plan.generate` 后继（两类后继用**不同 owner_id**）⇒ 人工存在同 assessment 的 plan/enroll job 时 count 仍可能为 1。修法：按 `job_type` 与 `payload.assessment_id` 查询，`plan.generate` 另以对应 `care_plans` 行验证。
  3. `providers.py:163-166`、`dconfig.py:394-469`：barrier 启用时 `DIR` 可为空并**回退共享 `/tmp/mvp-double-late-barrier`**，未强制 RUN_ID 隔离 ⇒ 两个并跑实例会互相消费 sentinel。修法：`barrier=true` 时要求 `DIR` 非空，或在 sentinel 名中加入不可碰撞的 RUN_ID。
  4. SUGGESTION `dconfig.py:162-164,400-403`：timeout 非数字抛裸 `ValueError`，与其他注入错误类型不统一 ⇒ 转换为含变量名与值域的 `ProviderConfigError`。
- **orchestrator 处置决定**：**四项全部修，不接受"明确接受测试约束"**。理由：三项 IMPORTANT 都属**可能导致假 PASS 的证据完整性缺陷**（其一可使崩溃的被测进程被记为通过、其二使"无脏后继"断言实际无判别力、其三使并跑实例互相污染），与本项目"绝不把受控替代或伪造效果当真实、要求独立验证"的一贯要求直接冲突；且四项全在 B 自有写域（工装 + 注入缝 + 定向测试），修复成本低、不触碰业务代码。修复后将产生新 SHA，需再做一次窄范围重绑定（沿用 `c59a18b`/`76a01f0` 已被接受的模式），并请求轮次边界声明。
- **Oracle 本轮实际执行的核查命令**：`git rev-parse HEAD`、`git log --oneline f4b9546..8343ba5`、`git diff --stat f4b9546..8343ba5`、`git diff --check 5bd22d3..8343ba5`、`git show --stat --oneline d312d2a 40f5fde 181676d 8343ba5`、`git status --short --branch`、对 `backend/acceptance/**`/`contracts/**`/`handoffs/**`/`db/migration/**`/`deploy/**`/`src/main/resources/**` 的越界核查（结果为空）、对 `assessment_analyze.py`/`plan_generate.py`/`identity_enroll.py`/`dmedia.py`/`runtime`/`handlers/__init__.py`/`web-java/src/main` 的"应无 diff"核查、`git diff --numstat f4b9546..8343ba5 -- backend/tests/...`；另只读检查全部增量主代码、定向测试、b40/b41 与既有 handler/fence/media 路径。**未修改文件、未运行测试或验收。**
- **Oracle 要求新增/持续披露的残留限制**：barrier 为**文件式进程间测试同步机制**，E 必须使用**每 RUN_ID 独立目录**；barrier timeout 后重试会再等一个有界 timeout；barrier 当前拦截的是 `FaceDouble.quality` 返回，后续 skin/search 虽在释放后运行但仍使用**释放前加载的旧照片快照**；stale 旧执行可能在结果图归档 tx1/存储阶段留下**不可见 pending 媒体或孤儿字节**，依赖既有 `media.cleanup` 回收（**不会产生 available/report 引用**）；`HOLD` 只是可重试失败、**不等同**真实迟到返回；timeout 非数字异常类型暂为 `ValueError`。上轮非阻塞项继续保留（`matched` 无 `face_subject_ref` env seam、`execution_face`/`revalidation_face` 缺 C 端点专项 IT、pytest 共享 DSN/迁移 fixture 待统一、Java `assessment_result` 失败模式通常不命中 Java 上传路径、C25/C26 与真实 provider 未接入）。

### 4.15 第十二轮：四项证据完整性修复的**窄范围重绑定**（被审 SHA `11e42c8ea29c97312059cab886f39c5c3418e8f8`，会话 `ora-1`）

**`VERDICT: PASS-with-notes`，新发现：无。**

**六点裁定（全部闭合）**
1. **IMPORTANT 1 已闭合**（`b-checks-3.sh:481-495`）：明确断言 Worker A `a_rc==0`；只接受**精确** WARNING 事件 `job.complete_stale_generation`；拒绝 traceback；原有 v2 快照、唯一 T05/`report_ready`、`members` 与 sentinel 断言**均保留**（`:497-508`）。
2. **IMPORTANT 2 已闭合**：b41 按真实关联方式检查后继（`b-checks-3.sh:532-539`）；Python 定向测试分别检查 analyze / identity.enroll / care_plans / plan.generate（`test_seam_boundary_repro.py:393-433`）；**判别力测试有效**（`:436-506`）——临时 plan job 不影响旧 `owner_id` 计数、却会被新 `care_plan`/join 查询命中，随后确实清理并验证零残留。
3. **IMPORTANT 3 已闭合**：barrier=true 时**强制独立 DIR**（`dconfig.py:481-487`）；`default_late_barrier_dir()` 已明确只供显式构造（`providers.py:163-170`）；测试覆盖缺 DIR、缺 SHA、非法 SHA、非法 timeout 与完整合法配置（`test_seam_boundary_repro.py:550-570`）。
4. **SUGGESTION 4 已闭合**：`_strict_env_int()` 将非数字与低于下界**统一转换为 `ProviderConfigError`**（`dconfig.py:167-186`）；barrier timeout 使用该解析器（`:422-428`）；`abc` 定向测试验证变量名与值域（`test_seam_boundary_repro.py:573-585`）。
5. **负向验证成立、交付代码无临时残留**：当前断言会分别拒绝非零退出、缺精确 WARNING 与 traceback，所述三种负向实验与代码行为一致；被审 diff 中**未发现** `TEMP-NEG`/`TEMP_NEG`/`neg-fix`/`intended.sh` 或被篡改基准；临时判别力数据只存在测试事务/fixture 中，并有显式删除与清理断言。
6. **原结论可重新绑定**：可以合入 dev；SC-02-09、SC-02-10 注入能力仍可由 E 黑盒驱动；最终场景结算仍由 E matrix 独立负责。

**最终 SHA 与验收要求（Oracle 原文）**：**可以将 `11e42c8ea29c97312059cab886f39c5c3418e8f8` 作为本轮最终交付 SHA 合入 dev**；**不要求再次重跑端到端验收**（orchestrator 已在该精确 SHA 上完成 41/41；本轮代码与断言核查未发现证据失效或行为缺口）；工作树中的 `B.md`/`B-oracle.md` 修改与新增 `B-seam-repro.md` 不属于该 SHA，应按既定 **report-only** 流程单独处理。

**轮次边界声明（Oracle 原文）**：**"`11e42c8ea29c97312059cab886f39c5c3418e8f8` 为本轮最终交付 SHA；无需再因测试断言精度或文档措辞发起新的重新绑定轮次。"** 只有 E matrix 发现新的实际行为缺陷，才需要重开代码审查。

**持续披露的残留限制（Oracle 据实更新）**
- **已移除**：①"barrier DIR 可省略、需调用方自觉隔离"——现在**代码强制独立目录**；②"非数字 timeout 抛 `ValueError`"——现在**统一为 `ProviderConfigError`**。
- **继续披露**：barrier timeout 后重试可能再次等待一个有界 timeout；barrier 拦截 `FaceDouble.quality` 返回，后续处理仍使用**释放前加载的旧照片快照**；stale 旧执行可能留下**不可见 pending 媒体/孤儿字节**，由既有 `media.cleanup` 回收（**不会形成 available/report 引用**）；`HOLD` 是可重试失败、**不等同**真实迟到返回；`matched` 尚无 `face_subject_ref` 环境 seam；`execution_face`/`revalidation_face` 缺 C 端点专项 IT；pytest 共享 DSN/迁移 fixture 待统一；Java `assessment_result` 注入值通常不命中 Java 上传路径；**E matrix 尚需独立完成最终场景结算**。

**Oracle 该轮实际执行的核查命令**：`git rev-parse HEAD`、`git log --oneline 8343ba5..11e42c8`、`git diff --stat 8343ba5..11e42c8`、`git diff 8343ba5..11e42c8`、`git diff --check 5bd22d3..11e42c8`、`git show --stat --oneline 11e42c8`、`git status --short --branch`；对 `backend/web-java/**`、`acceptance/**`、`contracts/**`、`handoffs/**`、`db/migration/**`、`deploy/**`、`run-acceptance-b.sh`、`runtime`、`assessment_analyze.py`、`plan_generate.py`、`identity_enroll.py`、`dmedia.py`、`media/storage.py` 的越界核查（结果为空）；以及 `git grep -n -E 'TEMP-NEG|TEMP_NEG|neg-fix|intended\.sh' 11e42c8 -- <四个增量文件>`（零命中）。另只读检查四个增量文件。**未运行测试、进程或验收，未修改文件。**

**本轮（测试注入缝轮）Oracle 调用小结**：共 **3 次实际调用**——`f4b9546` 有界复审（**FAIL**：1 BLOCKER + 1 IMPORTANT + 2 SUGGESTION，明确不可合入）→ `8343ba5` 有界复审（**PASS-with-notes**：21 项闭合、许可合入、3 新 IMPORTANT + 1 SUGGESTION）→ `11e42c8` 窄范围重绑定（**PASS-with-notes**：六点闭合、新发现无、最终交付 SHA + 轮次边界声明）。三次均为真实只读审查、均给出可核查的 `文件:行` 依据与实际命令清单，无任何轮次以"内容评估"替代 SHA 绑定。



### 4.16 第十三/十四轮：Swagger 联调注释轮的有界复审（会话 `ora-1`）

本轮范围是**全新**的（文档-only：为实际 springdoc 生成的 `/v3/api-docs` 补齐 APP/云台联调中文文档），与前十二轮的业务代码审查无关。Oracle 被明确授权可运行测试（DB 仅 `mvp-b-pg`@55435、活体端口仅 18083），并被告知 Java 测试库 env 陷阱（漏传 `MVP_A_PG_JDBC/USER/PASSWORD` 会连**禁用的 55432** 并使全部 `@SpringBootTest` 上下文加载失败，表现为 `Errors` 而非 `Failures`）。

#### 4.16.1 第十三轮：首次交付 `fb342a67e7c613cdc9c24ec6fcb74b9f68dbcacb` → **VERDICT: FAIL**

2 BLOCKER + 5 IMPORTANT，明确"不可合入 dev"。**orchestrator 逐条读码核实 7 项全部成立**，其中两项纠正了我自己任务书的口径、一项裁定实施子道取证有误：

| # | 严重度 | Oracle 发现 | 我的独立核实 | 归属 |
|---|---|---|---|---|
| 1 | BLOCKER | 引擎把所有 multipart part 标为 required，A02 的图片 part 实为按 `replacedViews` 条件必填 | 生成文档 A02 `required=['front','left','metadata','right']`，契约 `required=['metadata']`；`AssessmentMultipartParser:76-88` 要求 `replacedViews` 非空/∈front,left,right/不重复 | 引擎 + C4 |
| 2 | BLOCKER | `SkinReportListItem.reportSummary` 被虚假声明为"无可取证键"的不透明对象 | **写入方** `assessment_analyze.py:412-417` 固定构造 `{schema_version:1, conclusion, headline_metrics[:8]}`，`SkinReportService.java:87` 原样外发 ⇒ 三键完全可取证 | C4 |
| 3 | IMPORTANT | 登出被错称"同事务" | `AuthController:136` 在会话撤销**后**调用；`:203-214` 是 autocommit 单条 UPDATE 且 try/catch 吞异常（注释明写"撤销已生效；目标失效可后续补偿，**不反转登出**"）；控制器无 `@Transactional` | C1 |
| 4 | IMPORTANT | 媒体策略描述过时（称生产 deny-all、dev 可走 owner 便利） | `BusinessMediaAccessPolicy:66-67` 为 `@Component @Primary`（javadoc 自称"唯一业务策略，覆盖 A 的 deny-all 默认"）；dev 旁路已在注入缝轮**全删**，`MediaPolicyNoDelegationIT` 在 `owner-dev` 下断言上传者仍 404 | C1 |
| 5 | IMPORTANT | `EchoJobRequestBody.numbersAsStrings` 契约必填却写成"可选"，且无契约口径说明 | 契约 `SystemEchoJobRequest.required=['message','numbersAsStrings']`，代码未以注解强制 | C1 |
| 6 | IMPORTANT | 门禁只查 5 个硬编码自由结构字段，且任意非空 note 即可冒充不透明声明 | `ApiDocsCoverageIT:55-61` 确为硬编码清单；`classifyFreeForm` 用自由文本关键词判定 ⇒ 夹具描述"普通数组描述（无任何**不透明/未冻结**表述）"竟被误判为已声明 | 引擎 + 门禁 |
| 7 | IMPORTANT | `capabilities.schema_version` 被写成"服务端当前写 1" | `MicrocrystalService.buildCapabilities(requested, schemaVersion, revision)` 把它置为**请求中已校验的 `schemaVersion`**（可 >1）并跳过 requested 同名键 | C2 |

**我对第 2 项的裁定**：子道以"`SkinReportService.listReports` 仅 `parseJson` 原样返回、未读取任何固定键"推断"无经取证的键可列"——把**读取方不解析**误当成**结构不可取证**；键的权威来源是**写入方**。Oracle 正确、子道取证有误，已要求其复盘根因。
**我对第 5 项的关键区分**（避免修出新失真）：`A01Metadata`/`A02Metadata`/`M1A01Metadata`/`Capture` 的必填字段**服务端确实强制**（`AssessmentMultipartParser:60-64,73-88`；`MemberAccessGrantController:162-170,197-203,207-210` → 400 `INVALID_INPUT` + `details.fields`），只是未用 Bean Validation 注解 ⇒ javadoc 明写"**这不是实现偏差**"；只有 `numbersAsStrings` 属"契约必填而代码不强制"的**真实现偏差**。
**Oracle 同时确认**：零业务改动成立（`76cd426..fb342a6` 仅 `web/docs/**` 12 文件）、生产 fail-closed 不回归、成功码/类型化 data/错误码与契约一致/示例脱敏均通过、`JsonNode` 空壳可接受、实现与契约差异按源码事实书写恰当、两个契约缺口（`PROVIDER_CONTRACT_VIOLATION` 未入 enum、f02 漏声明 `SESSION_INVALID`）应上报总协调且当前处置正确。

**整改**（提交 `9b5ed34a6bd669ebc4726681cb92847264b3a18e`，9 文件全在 `web/docs/**`）：接口加法扩展 `MultipartPartDoc.required`（保留 3 参工厂默认 true ⇒ 零目录破坏）与 `ApiDocsCatalog.requiredProperties()`（default 方法 ⇒ 不破坏 29 处 `new PropertyDoc(...)`、16 处 `new FreeFormDoc(...)`）；引擎按 part 施加 required、合并并施加 `requiredProperties()` 且 fail-fast（新增 `unknownRequiredProperties`）、展开自由结构时清 `$ref`；门禁三项硬化（只认 `OPAQUE_MARKER`、动态扫描全部属性 + `isUnstructuredObject`、`APPROVED_OPAQUE_FIELDS` 核准清单恰 3 项、契约 required 交叉校验含生成名↔契约名映射）；三个目录据实声明 required；C1/C2/C4 文案与结构改正。
**我实测闭合证据**：`test-compile` rc=0；`ApiDocsApplierTest` 15/0/0、`ApiDocsCoverageIT` 1/0/0（4 项→0）、`OpenApiDocsIT` 3/0/0、`OpenApiDocsDisabledIT` 1/0/0、`DocsProductionGuardTest` 7/0/0；**全量 `mvn -B test` 435/0/0**；真实 `/v3/api-docs` 200/415676 字节，A02 `required=['metadata']`、A01/care/revalid/grant 与契约逐个吻合，`reportSummary` 含三键且无不透明标记，5 个 schema 的 required 与契约相符，"当前为 1"与"留痕"出现 0 次，`deny-all`/`owner-dev`/`any-authenticated` 仅出现在否定句中，核准不透明集恰 3 项，无结构自由字段 0，**全量 384 个 `$ref` 零悬空**。

#### 4.16.2 第十四轮：整改 SHA `9b5ed34` → **VERDICT: FAIL**（范围收窄）

**原 7 项全部确认闭合**（Oracle 逐条给出 `文件:行`），并采纳我的两项决策：清除 `$ref` 可接受（展开后 inline schema 成为机器可见结构、无悬空引用、`JsonNode` 修剪合理）、**本轮不重跑 41 项端到端工装可接受**（增量仅 `web/docs/**`，435 项 Java 全量 + 真实抓取是适当验证）。新发现 1 BLOCKER + 2 IMPORTANT + 1 SUGGESTION：

- **BLOCKER**：`knownKeys` 只能表达一层类型，`keySchema()` 的 `case "array" -> new ArraySchema().items(new StringSchema())` 使**任何嵌套数组退化为 `array<string>`**，与真实响应冲突并误导代码生成器：`CarePlanFullView.plan.steps`、两个 `planExecution.steps`（实为 `array<object{region,parameters}>`，权威源 `CarePlanProjection.projectStep/projectParameters/projectParameter`）、`ErrorBody.details.fields`（实为 `array<object{field,reason}>`）、`ErrorBody.details.missingRanges`（实为契约 `MissingRange={from,to}` 均必填、封闭）。Oracle 判定这违反"大 JSON 必须明确结构及可扩展边界"，属 **9/13 联调阻塞项**。
- **IMPORTANT**：门禁只扫描 component 的**直接属性**，展开字段内部的空 object / 错误 array items 不会被发现（`plan.steps` 建成 string items、`incidents[].detail` 为空壳 object，但父字段已有 properties 被判 EXPANDED）⇒ 须递归遍历 inline properties/items。
- **IMPORTANT**：契约 required 交叉校验只覆盖请求，不覆盖响应 DTO ⇒ 须对所有成功响应的 data/list item schema 同等校验。
- **SUGGESTION**：`AssessmentApiDocs` 的 `metrics.value` 同时写"number"与"数值/文本类型未冻结"，自相矛盾。

**我实测复核全部成立**，并补充两点：①根因更精确——顶层数组型自由字段（`HeartbeatBody.incidents`、`SkinReportView.metrics`）的 `items` **已正确**为 object 且键齐全，错误只发生在"自由结构对象**内部**的键"经 `keySchema()` 一层 DSL 时；②我发现一个 **Oracle 未点名的引擎缺陷**：`applyFreeForm` 清除 `$ref` 后**未补 `type`**，致 `SkinReportListItem.reportSummary` 与 `M4A04Metadata.reportedMicrocrystalState` 在生成文档中**缺 `"type":"object"`**（实测 `has type key: False`），而 `MicrocrystalObservationBody.state` 却有 ⇒ 已纳入本轮修复。
**我对 `metrics.value` 的取证修正**（比 Oracle 建议更准确）：投影层 `SkinReportService.projectMetrics` 原样复制、不校验类型，但**上游 Python 契约校验** `assessment_analyze.py:645-648` 强制 `value` 为 `int/float` 且排除 `bool`、并须落在核准范围内，违约即 `PROVIDER_CONTRACT_VIOLATION` 终态失败 ⇒ 报告中的 `value` **必为 number**，未冻结的是**指标语义/单位/取值范围**而非类型。已按此改写（而非简单删掉"未冻结"字样）。

**Oracle 给出 6 条一次性目标判据**：①`plan.steps.items.type == object` 且含 `region`/`parameters`；②动态参数 map 明确 `additionalProperties` 及值边界；③`ErrorBody.details.fields/missingRanges` 使用正确对象 item schema；④Coverage 递归检查所有 inline object/array；⑤响应 required 与契约同等交叉校验；⑥定向加入"错误 `array<string>` 不得通过"的负向测试。**轮次边界声明**：下一轮只需核验递归自由结构 schema、响应 required 门禁与上述负向测试，已闭合的 7 项无需复审；达到 6 条后无需再因普通文档措辞发起重绑定轮次。
**9/13 可用性判断**：上轮两个 P0 已修，但"大 JSON 的机器结构仍不准确，故 P0 尚未全部清零"；修完递归 schema 后可支撑 HTTP 流程与 doubles 联调，**真实硬件独立接入仍需设备团队/总协调冻结 10 项**（云台 credential/proof 格式与签名/nonce/防重放/轮换、pairingProof 协议、connectionProof 与连接 generation/有效期、微晶 capabilities 键与类型/单位/范围/版本演进、微晶 state 结构与状态编码、heartbeat incident code/severity/detail 结构、observationEpoch/Seq 持久化与 C25/C26 代次规则、session token 提供方/字段名/TTL/撤销语义、测肤 metrics 名称与单位范围及 conclusion 集合、care plan 的 region/step/parameter 名称与单位）——**这些不能由文档实现方自行发明**。

#### 4.16.3 第十五轮：递归结构化键整改 → 待审

**orchestrator 的接口决策**（我拥有冻结接口）：新增递归 record `KnownKeyDoc`（7 组件 `type/description/properties/items/additionalProperties/additionalPropertiesSchema/example`）与工厂 `str/integer/number/bool/array/closedObject/openObject/mapOf/opaqueObject`，并新增 **default 方法** `structuredKeys()`（与 `freeFormDocs()` 同键空间，内层为顶层已知键 → 递归结构；与 `knownKeys` **按并集施加、同名以 `structuredKeys` 为准**）⇒ 加法扩展，16 处 `new FreeFormDoc(...)` 零破坏。`type` 另支持 **`any`**（不写 type 关键字、仅 description），专为 `projectParameter` 允许的"标量 **或** `{value,unit}` 对象"这类真实联合形态，且明令不得用 `any` 规避取证。
**首次尝试的错误**：我曾试图给 record 加可变私有字段承载 `mapOf` 的值结构，触发 `Instance fields may not be declared in a record class` ⇒ 改为第 7 个组件 `additionalPropertiesSchema`；定向 `javac` 验证接口与我自己的 `CommonEnvelopeApiDocs.structuredKeys()` 均 rc=0。
**分道**：引擎+门禁道（递归构建、`$ref` 清除后补 `type`、门禁递归扫描、响应侧 required 交叉校验、正负向测试含"错误 `array<string>` 不得通过"）、C3 道（`plan.steps`/`parameters` 与两个 `planExecution`）、C2 道（`incidents[].detail`）；我自己修 `CommonEnvelopeApiDocs`（`details.fields`→`array<openObject{field,reason}>`，因 `CareBigints:50` 等生产者只给 `field` 不给 `reason` 故不封闭；`missingRanges`→`array<closedObject{from,to}>` 依契约 `MissingRange`）与 `AssessmentApiDocs` 的 `metrics.value` 文案。

**第四轮整改落地（提交 `7461ce115e2d3690c414db63bcd1bc261b95c8b1`，9 文件全在 `web/docs/**`）**：
- **接缝风险实测裁定**：两条目录道各自独立提出的同一风险（引擎对"数组型自由字段的内层键"与 `any` 的落地口径）经我读码确认**双方假设均正确**——引擎固化"内层键描述元素对象的键"（`prop.setType("array"); prop.setItems(struct)`），`knownKeySchema` 对 `any`/null/空 type **不写 type 关键字**。
- **我发现并修复 Oracle 未点名的缺陷**：两个 `JsonNode` 型字段（`SkinReportListItem.reportSummary`、`M4A04Metadata.reportedMicrocrystalState`）在真实文档中缺 `"type":"object"`。引擎已调用 `setType("object")` 且单测断言内存态 `getType()` 通过 ⇒ **内存成功但 3.1 序列化未输出**。字节码级根因：`Schema31Mixin` 把 `getType()` 标 `@JsonIgnore`，`"type"` 由 `getTypes()`（`Set<String>`）经 `TypeSerializer` 输出，而 `Schema.setType(String)` 只写 legacy 字段、不动 `types`；`new ObjectSchema()` 走 `Schema.<init>("object", null)` 会 `addType("object")` 故正常（引擎自建的列表 `data`/统一信封带 type，构成反证）。修法：整体替换属性实例（`FreeFormTarget` holder + `copySiblingKeywords` 保留 `nullable/readOnly/writeOnly/deprecated/title/format/extensions` 与插入位置）。
- **测试代表性缺陷（比缺 type 本身更严重）**：原回归测试只断言内存态，故生产 JSON 缺 type 时依然绿 = **虚假保证**。改为对 `Json31.mapper().writeValueAsString(openApi)` 的序列化结果断言，并新增**负向判别力证明**（构造 `new Schema<>().$ref(...)` → 清 `$ref` → `setType("object")` → 序列化后断言 `type` **缺失**）；同类问题已排查并为另两个测试补序列化层断言。
- **门禁新增的响应侧 required 交叉校验暴露 33 项真实缺口**（生成 required 为空 vs 契约非空）。我裁定**补齐而非降级**；四域据实声明 33 个响应 schema，每条 snakeyaml 实读契约逐字比对并**逐字段核实存在性**（全库仅 2 处 `@JsonInclude(NON_NULL)`：`SkinReportView:21` 的 `metrics`、`ErrorEnvelope:17` 的 `details`，均不在声明集；`AssessmentTaskView.requiredViews` 由 `FailureProjection:88-90` 在非 `needs_retake` 时返回 `List.of()` ⇒ 键恒存在；`GimbalCurrentAssessmentView.currentAssessment` 键恒存在、值可为严格 null；Care 域 14 项核对 DB NOT NULL 列与构造路径）。接口语义同步澄清：**响应侧 required = 服务端保证键必然存在（值可为 null），不是实现偏差**。
- **我纠正了自己定的一个不可实现判据**：原要求"目录把对象数组声明成 `array<string>` 时门禁必须失败"——仅凭生成文档无法判别（与合法字符串数组同形）⇒ 改为引擎 fail-fast：`keySchema()` 拒绝裸 `array`/`object` 前缀（`invalidKnownKeyTypes`）、新增显式 `array<string|integer|number|boolean>`；连带改 5 处真字符串数组，另 5 处裸前缀经核实安全（2 处为 `KnownKeyDoc` 描述文本、3 处被 `structuredKeys` 覆盖而由引擎跳过）。
- **orchestrator 的调度误判（如实记录）**：C3 道派发后 10 分钟无写入 + `task_status` 返回 "Unknown task ID" + 磁盘 `requiredProperties` 命中 0，我判定其已死并**重派**，造成同文件重复写者；实际该道处于长时间读码核实阶段，11 分钟后正常交付。我随即取消重复道并实测对账（方法声明恰 1 次、import 恰 1 次、mtime 仍为原道交付时刻、14 个键各命中 2 次系 `propertyDocs()` 与 `requiredProperties()` 各一次）⇒ **重复道零写入、无污染、无需回滚**。教训：对需大量读码的任务，"短暂无写入"不构成死亡证据。第 8 次同类信号出现时我改用 260 秒三点指纹探测，确认其在世（surefire 报告新写入）而未误动。

**orchestrator 实测验证（绑定 `7461ce1`）**：`test-compile` rc=0；定向文档测试 **34/0/0**（Guard 7、Coverage 1、DisabledIT 1、**Applier 22**、OpenApiDocsIT 3）；**全量 Java 442 run / 0 failures / 0 errors**；硬化门禁 **33 项 → 0 项**；真实 `/v3/api-docs` **200 / 423892 字节**；自建 `verify-r4.py`（**判别力已自测**：对修复前抓取 34 PASS/22 FAIL）跑出 **66 PASS / 0 FAIL**，覆盖 Oracle 6 条判据 + 序列化缺陷 + 前两轮回归（`plan.steps.items.type=object` 含 `region`/`parameters`、`parameters.additionalProperties` 为 schema、`details.fields.items`={field,reason}、`missingRanges.items` 封闭 {from,to}、`incidents[].detail` 显式开放、3 个 `JsonNode` 型字段均带 `type=object`、53/61 schema 有非空 required、属性描述 266/266、示例 221、**384 个 `$ref` 零悬空**、`JsonNode`/`PrincipalContext`/`SuccessEnvelope` 已修剪）；跑后端口空闲、无遗留进程；整轮相对 dev 基线 **12 文件 / +7224 −53 全在 `web/docs/**`**，`git diff --check` rc=0。

**第十五轮（Oracle 对 `7461ce1` 的窄范围复审）结论：VERDICT FAIL**（送审范围严格限于 Oracle 上轮自行声明的边界）。其 6 条判据中 **1/6/7/8 通过**（`plan.steps` 递归结构、裸前缀 fail-fast 负向判别、3.1 序列化缺陷的根因与修法、`metrics.value` 文案），判据 2 **基本通过**（`any` 准确表达真实联合，建议协议冻结后改 `oneOf`）。新发现 **2 BLOCKER + 1 IMPORTANT**：
- **BLOCKER A**：`KnownKeyDoc` 无法表达**嵌套 required** ⇒ `ErrorBody.details.missingRanges.items` 缺 `required:[from,to]`，与契约 `MissingRange`（两键均必填、封闭）不一致，机器契约比权威契约更宽松、会让代码生成器允许客户端漏填。**根因是我设计接口时的能力缺口**（7 组件无 required，引擎 `knownKeySchema` 从不 `setRequired`）。
- **BLOCKER B**：响应 required 门禁**跳过**契约的 inline schema（5 个生成 component），其中 3 个契约明确要求 required 而目录未声明；Oracle 指出"**跳过并打印不等于同等交叉校验**"。
- **IMPORTANT**：`any` 节点无 type 且不受核准清单约束 ⇒ 可被用来绕过递归结构门禁。
Oracle 给出 7 条精确修复目标并明示"无需重跑完整端到端验收"。

#### 4.16.4 第十六轮整改（提交 `c3bf05433276152441eb7e80081c3dffc5fbeb6a`）与其窄范围复审

**整改要点**：①接口加法扩展 `KnownKeyDoc` 第 8 个（末位）组件 `List<String> required` 并保留 **7 参委托构造器** ⇒ 既有 10 个工厂与既有目录调用点（`CareApiDocs:1019`）**零破坏**；新增 `any(desc)` 与 `closedObject(props, required, desc)` 工厂；引擎 object 分支按声明顺序 `setRequired`，required 含不存在的键 → 新增 `invalidNestedRequired`（含完整路径）并 fail fast。②门禁新增 `CONTRACT_INLINE_RESPONSE_POINTERS`（生成名→契约 JSON pointer）+ RFC6901 `resolvePointer` + `crossCheckInlineRequired`（**双向精确集合相等**，pointer 陈旧亦失败）；`RecordWatermark` 从跳过清单移出改为真实比对。③目录据实声明 3 项（`EchoJobLastError[reason,retryable]`、`SkinReportImage[mediaId,contentUrl]`、`CurrentAssessment[taskId,status,photoVersion]`），且**契约 required 不含 `reportId` 故未声明**、并把该字段描述补为"未就绪时为 null 但键仍存在、客户端不得依赖其非空"。④门禁 `APPROVED_ANY_PATHS` 采用**精确集合成员判定**（实施道提出、我采纳，比我原建议的模式匹配更严格：模式会顺带放行未来任何 `Foo.plan.parameters.*`，精确集合则"新增或改名结构都会响亮失败并暴露待审路径"）。⑤新增 4 项正负向测试 + 1 项真实文档断言，负向均有判别力；序列化层证据以 `javap` 核实 `Schema31Mixin` 中 `getType` 被 `@JsonIgnore` 而 **`getRequired` 未被忽略**。

**我方对 Oracle 两处主张的独立核实结论（不盲从）**：
- **`IncidentView`**：Oracle 要求"与 inline 契约的空 required 集比较，而非跳过"。我与实施道**各自独立**全量搜索契约的 `incidentId`/`openedAt`/`lastReportedAt` ⇒ **均零命中**；契约中唯一的 `incidents` 键在请求侧（`GimbalHeartbeatRequest`、`GimbalStatusView`），两者均标 `x-detail: skeleton`、形态 `{type:object, additionalProperties:true}`，**不存在任何响应投影结构定义**。故处置为：保留"跳过"，但把披露文案改为**明确写明"契约未定义该结构"及其依据**（门禁新增 `CONTRACT_UNDEFINED_RESPONSE_SCHEMAS`），**未 invent 任何映射或 required**。该分歧已带证据提交 Oracle 裁定。
- **`any` 的数量**：Oracle 称"仅三处 plan parameter map value"，我在真实文档上实测为 **6 处**（3 个 plan 结构 × {顶层 `parameters.*`、`steps[].parameters.*`}，因 `projectStep → parameters → projectParameters`，每个 step 内还有一层动态映射），并已把该实测修正转达在飞实施道（其独立回放判据于修复前抓取，HITS=6 逐字一致）。
- **另一处避免误报的实测事实**：61 个 component 中 **47 个没有 `type` 键**（只有 `properties`/`required`），这是 springdoc 对 record 在 3.1 下的正常输出、Oracle 两轮均未视为缺陷 ⇒ `any` 的检测判据**不能**只用"无 type"，否则大面积误报；实际判据为"无 `type` 且无 `$ref` 且无 `properties` 且无 `items` 且无 `additionalProperties`"。

**orchestrator 实测验证（绑定 `c3bf054`）**：`test-compile` rc=0；定向文档测试 **38/0/0**（Guard 7、Coverage 1、DisabledIT 1、**Applier 26**、OpenApiDocsIT 3）；**全量 Java 446 run / 0 failures / 0 errors**（`7461ce1` 的 442 + 4 新）；真实 `/v3/api-docs` **200 / 424133 字节**、swagger-ui 200；自建 `verify-r4.py`（**两次自测判别力**：对修复前抓取 72 PASS/6 FAIL，6 项恰为待修清单；期间修掉脚本自身两个缺陷——把属性节点当 schema 名传入致 `TypeError`、`any` 判据把 47 个正常 component 误报）跑出 **78 PASS / 0 FAIL**，逐条覆盖 Oracle 7 条目标（`missingRanges.items.required=[from,to]`、三个 inline component 的 required 精确相符且**未 invent `reportId`**、`RecordWatermark`/`IncidentView` 均为空、无 type 值节点**恰 6 处且全在核准路径**、有非空 required 的 schema 由 53 增至 **56**）并回归前几轮全部已闭合项；门禁披露口径已改为 `undefined=[IncidentView（契约未定义该结构…）]`；跑后端口空闲、无遗留进程；整轮相对 dev 基线 **12 文件 / +7642 −53 全在 `web/docs/**`**，`git diff --check` rc=0。

**我方主动披露（不在 Oracle 7 条目标内、未擅自扩大范围）**：①5 个 inline 映射 component 的 `additionalProperties` 契约为 `false`、生成文档为空（语义更宽松，但响应 DTO 是 record、实际不会输出额外键 ⇒ 无行为风险）；②47/61 个 component 未声明 `"type":"object"`（已写入交付指南第 8 节）；③plan 参数值联合以无 type 的 `any` 表达，协议冻结后应改 `oneOf`；④实施道为取得"required 确实进入 3.1 JSON"的证据运行了一次**隔离 classpath 的独立 `java` 探针**（非 mvn、非项目测试套件、不触碰项目源码与端口）并主动披露，我判定属轻微越界但目的正当、无副作用，予以接受并记录。

**第十六轮（Oracle 对 `c3bf054` 的窄范围复审）结论：VERDICT PASS-with-notes**。
- **五项判据全部通过**（各附 `文件:行`）：①nested required（DSL `ApiDocsCatalog.java:175-219`、引擎施加与非法属性 fail-fast `ApiDocsApplier.java:645-689,1184-1221`、`MissingRange` 声明 `CommonEnvelopeApiDocs.java:145-178`、真实文档门禁 `ApiDocsCoverageIT.java:388-398`）；②inline 响应映射（4 个 pointer `:161-192`、RFC6901 解析与双向比较 `:639-760`，少报/多报/陈旧 pointer 均失败，`RecordWatermark` 已与空 required 集真实比较而不再笼统跳过）；③三项实际 required（`FoundationApiDocs.java:508-526`、`AssessmentApiDocs.java:423-444`，且 **`reportId` 未被错误加入** `CurrentAssessment`）；④正负测试（nested required 序列化正反对照、非法键完整路径、inline pointer 少报/多报/陈旧映射、未核准 any 均有独立判别力；**测试使用 Json31 序列化结果、不再停留于可能失真的内存态**）；⑤`any` 核准（精确清单 `:63-95`、递归判定 `:485-505`，"精确路径优于模式匹配，不会静默放行未来同名结构"）。验证数字自洽（442+4=446、定向合计 38 项）。
- **A（`IncidentView`）：Oracle 明确撤回其此前主张**——"实施方处置正确，我撤回此前'应与空 required 集比较'的要求"，并自证契约仅在 `openapi.yaml:2173-2176`（heartbeat 请求 incidents）与 `:2202-2205`（status 响应 incidents）定义开放 skeleton，均不含 `incidentId/openedAt/lastReportedAt` 投影结构；把 `IncidentView` 归入"契约未定义"并披露**比虚构 pointer 正确**。⇒ 我方"不 invent 映射、带证据顶住"的处置获裁定支持。
- **B（`any` 数量）：Oracle 确认应为 6 处**——其"三处"指三种 plan 结构，未计入每种的两条实际递归路径（`parameters.*` 与 `steps[].parameters.*`）。
- **新发现（均非阻塞）**：①IMPORTANT——47 个带 `properties` 的 component 未输出 `type: object`，且**JSON Schema 语义并不会由 `properties` 推导出实例必须是对象**（非对象实例只是不应用 `properties` 约束）；本轮明确接受（主流生成器仍能从 properties 生成模型），但**该文档不得宣称是严格验证契约**，后续可用 Json31 安全补齐 object type 并加序列化门禁。②SUGGESTION——4 个 inline component 的契约 `additionalProperties:false` 未在生成侧显式设置，机器文档比契约宽松；响应 DTO 实际不会输出额外字段，不阻塞联调，后续可把 inline pointer 比较扩展到 `additionalProperties`。
- **合入与验收**：**可以将 `c3bf05433276152441eb7e80081c3dffc5fbeb6a` 作为本轮最终交付 SHA 合入 dev**；**不要求重跑完整端到端验收**（本轮仍只改 `web/docs/**`，446 项 Java 全量 + 38 项文档定向 + 实际 `/v3/api-docs` 抓取已覆盖该风险面）。
- **9/13 硬件联调可用性**：此前识别的文档 **P0 已清零**（plan 嵌套结构正确、nested required 落地、inline 响应 required 可追溯、any 受精确清单限制）⇒ **可支撑 APP/云台开发者独立完成 HTTP 流程与 doubles 联调**、**可用于主流代码生成器生成客户端模型/调用骨架**；但**不能作为严格 JSON Schema 验证器或替代权威手写契约**（因 object type、additionalProperties 与 any 残留）。真实硬件协议仍需外部冻结其列出的 **10 项**。
- **轮次边界确认**：`c3bf054` 为本轮最终交付 SHA，**无需再因普通文档措辞或断言精度发起新的重绑定轮次**；唯一后续是已明确接受的 machine-schema 严格性增强，不影响 9/13 HTTP/doubles 联调。
- **对我方第 4 项披露（隔离 `java` 探针）的裁定**：可作为**补充证据**接受，但"不应替代仓内测试"；因本轮相同判别已固化为 Json31 单测与真实文档检查，**无需依赖该越界探针作结论**。
- **必须持续披露的残留限制（Oracle 清单，11 项）**：生成文档非权威契约；3.1.0 与 3.0.3 表示差异；47 个 component 缺显式 `type: object`、不宜作严格 JSON Schema 验证输入；inline 响应未完全同步 `additionalProperties:false`；plan 参数联合暂以经核准的无 type `any` 表达、冻结后应改 `oneOf`；`IncidentView` 响应投影在权威契约中未定义；`operationId` 尚未对齐；`ClosureResult` 实现少于契约的可选字段；`PROVIDER_CONTRACT_VIOLATION` 与 f02 `SESSION_INVALID` 两项契约缺口待总协调处理；真实硬件协议 10 项未冻结；文档仅 dev/test 启用、生产保持 fail-closed。
> 注：上列第 9 项的两项契约缺口已在**下一轮**（§4.17，总协调授权的最小契约一致性修正）闭合；此处保留原文以维持历史记录的当时准确性。

### 4.17 第十七轮：总协调授权的最小契约一致性修正（提交 `859266099476eace91053bac0b61a48a7023dc52`）

**授权范围（首次允许改 `backend/contracts/openapi`）**：①把已公开返回的 `PROVIDER_CONTRACT_VIOLATION` 纳入适当的 `failureCode`/`ErrorCode` 定义及测肤任务说明，**保持 `retryable=false` 现有语义**；②`POST /auth/sessions` 声明实际的 401 `SESSION_INVALID`；③把指南 §3.2 列出的"当前实现不触发"错误码**从对应操作的有效声明中移除**，必要处保留历史背景，**逐项依据实现、不改业务**；④统一指南 §7 与 §8 对 `reportSummary` 的矛盾表述为"实际已知键 + 剩余扩展边界"；⑤47 个 component 缺 `type` 与 4 处 `additionalProperties` **仍只作已披露限制，不扩展为完整代码生成器工作**。**禁止改变 HTTP 或序列化业务语义**；只验证此次变动、进行有界最终真实 Oracle，不重复 E 的 61 项集成全套及已通过范围。

**方法与取证链（本轮最重要的纪律：删契约声明必须以逐点实现证据为据）**：
1. 我先做全量取证，发现**自己的 grep 方法有缺陷**——只匹配 `ErrorCode.X` 会漏掉静态导入，导致 `RECORD_CONFLICT`/`TASK_REPLACED`/`PLAN_NOT_READY` 在主代码中"零命中"，与既有验收实测矛盾。改用**裸常量名**重做后才得到真实抛出点全集。
2. 确证 `SESSION_INVALID` 由 `BearerAuthFilter:89,104` 对**所有已认证请求**统一抛出 ⇒ 除公开端点外**一律不得删除**（这是本轮最容易造成真实回归的一处）。
3. `CALLER_NOT_ALLOWED` 与 `PLAN_NOT_READY` 无法凭直觉判定（`care/CareAuthorization:44` 确实会对 APP-only 端点抛 403），故派**只读侦察道逐操作追踪 controller→service→授权路径**产出真值表；关键判据是 `CareAuthorization.requireApp` 在整个 care 包**只有 3 处调用**（`CareQueryService:69,107,227` ⇒ 仅 M4-A01/A02/A09），而 M4-A03…A08 **显式接纳云台主体**（`controllerType` 可为 `gimbal`，以 `isOriginalController`/`hasActiveGrant` 判定，错误主体走 404 而非 403）。
4. 我对侦察结论**逐条复核而非照抄**，其中一处**改变结论**：M4-A04 的 `TASK_REPLACED` 未被真值表覆盖，我自行追踪 `CareAdmissionService.taskReplaced()` 全部调用点，确证其经 `runRevalidation:427,430` 与 `runRevalidationTx:470,473` **可达** ⇒ **保留**。
5. 侦察还发现我指南清单外的**两处新增过声明**（M2-A03 与 M3-A01 的 `TASK_REPLACED`、M3-A03 与 M2-A03 的 `CALLER_NOT_ALLOWED`），均经我复核后纳入。
6. **一处我差点造成的文档破坏**：我此前怀疑 `AssessmentApiDocs` 中 M3-A03 的"过声明：`CALLER_NOT_ALLOWED` 当前实现不返回"标注是错的（因 `AssessmentReadService:81` 确实抛该码）。取证明明 `:81` 属 **`currentAssessment`（声明于 `:78`，服务 M3-A06）**，而 `getTask:36-58` 不经过它 ⇒ **原标注是正确的**。若我"顺手修正"就会把正确文档改错。

**改动**：契约 `AssessmentTaskView.failureCode` 补 **9 值封闭 `enum`**（权威源 `FailureProjection.PUBLIC_FAILURE_CODES:45-53`，含 `PROVIDER_CONTRACT_VIOLATION`）并写明"白名单外一律投影 null 以防任意字符串经 M3-A03 泄漏""内部诊断绝不外发""当前所有非 null 取值 `retryable` 均为 false、true 仅为未来预留"（**语义未变**）；f02 的 `x-error-codes` 补 `SESSION_INVALID`（`responses` 本已含 `'401': $ref Unauthorized`，故为最小改动）；**24 处码-操作声明移除 / 17 个操作**（Care 15、Assessment 4、Foundation+IdentityDevice 5，与契约精确相等），每处 description 改写为"历史背景 + 取证依据（`文件:行`）+ HTTP 行为与序列化语义未变"；生成文档侧 `failureCode` 改 `PropertyDoc.enumOf`（9 值与契约**逐字同序**，并注明字段可空、enum 仅表达非 null 时取值集合）。
**契约改法的一处工程决定**：4 行 `x-error-codes` 内容完全相同而删除项不同 ⇒ 用 `edit` 工具会因多重匹配失败，故改用**按行号定位的脚本**，且脚本对每行**自校验**"确为 `x-error-codes` 行 + 确含待删码 + 结果集恰等于预期 + 删除数量相符"，任一不符即整体不写入。实测 diff 共 34 行、**非 `x-error-codes` 行改动为 0**。

**新增仓内回归守卫**（因 `.coordination/` 是 git 忽略目录、运行时脚本不进仓库，守卫必须落在仓内）：`ApiDocsCoverageIT` 第 8 节——24 对不可达码**不得再被声明**、13+1 项可达码**必须继续声明**（正向对照，使"全删"无法通过）、键经 `normalize()` 与 `generated`/`contract` 同源、**"操作未出现在生成文档"本身记为 problem**（防路径笔误导致静默失效）；另新增 `crossCheckFailureCodeEnum`（生成文档 enum 与契约**逐字同序**相等且必含 `PROVIDER_CONTRACT_VIOLATION`）。

**验证（orchestrator 亲自执行）**：契约四项校验器全绿（`openapi_spec_validator` VALID、`validate_responses --selftest` 10/0 含 4 项 nullable-shape 判别、`validate_samples` 50/0 all samples valid、`jcs` selftest PASS 26 checks）；Java `test-compile` rc=0、定向 **38/0/0**、**全量 446 run / 0 failures / 0 errors**；真实 `/v3/api-docs` 200 / **418567 字节**，**34 个契约业务操作 generated==contract ALL MATCH**、24 对不可达码残留 **0**、14 项正向对照全部仍在、`failureCode.enum` 与契约同序相等、`x-error-codes` 声明总数 **358→334（恰 −24）**；上轮已闭合项零回归（自建脚本 **78 PASS / 0 FAIL**）；**端到端工装完整 41 项 ALL PASS / SCRIPT_RC=0**，其中 **b14**（契约驱动的错误信封 + 每端点码白名单，全量观测面）PASS ⇒ 实证被删的 24 处码在真实请求中确实不可观测、且无观测码变为未声明。

**我本轮的错误（如实记录）**：①**过滤式工装运行结构上无效**——我先以 `B_ACCEPT_FILTER="b3 b11 b14 b19 b21"` 运行，得 2 PASS/3 FAIL（b14 报"端点 m1A01… 未产生任何错误观测"、b3 因缺 b1/b2 前置 fixture 失败）；取证 `backend/tests/support/b-checks-3.sh:300-304` 确认 b14 读取共享 `$OBS_FILE` 并**要求 12 端点均有观测**，而观测由各检查的 `op_call` 产生 ⇒ 过滤运行对 b14/b3 无效，**非产品缺陷**；改完整运行后 41/41 全绿。②**第三次**犯"`cd` 后在 heredoc 里用相对路径"的错误（致本轮量化脚本 `FileNotFoundError`），改绝对路径后重跑。③初始 grep 方法漏掉静态导入（见上）。

**子道对我任务书的两处纠正（均已采纳）**：①M2-A01 `POST /api/v1/gimbal-sessions` 实际在 **`FoundationApiDocs.java:207`**（我误标为 IdentityDevice），该道在实际所在文件修改并主动披露归属更正；②`PropertyDoc.enumOf` 定义在 **`ApiDocsCatalog.java:320`** 的嵌套 record（我误指 `ApiDocEntry.java`），该道自行定位到真实签名后使用。

**边界**：未改任何控制器/DTO/业务代码/`ErrorCode` 枚举/`GlobalExceptionHandler`/`application.yml`/`pom.xml`/迁移/`deploy`；**业务代码 diff 0 文件**；E 的验收资产（`backend/acceptance/**`）零改动（其 driver 未硬编码这些码，`grep` 命中只在历史 evidence 工件中）；未改 `backend/doc/**`（设计文档归总协调）；未 push、未合入 dev。**已提请总协调**：契约 `x-error-codes` 收窄可能要求 E 更新其期望。

**第十七轮（Oracle 对 `8592660` 的有界最终复审）结论：VERDICT FAIL**（1 BLOCKER + 2 IMPORTANT + 1 SUGGESTION），但同时**确认通过**：判据 1（`failureCode` enum 归类正确、`retryable` 未改）、判据 2（f02 为最小修法）、判据 3 的 **24 处移除逐处成立**、**M4-A04 的 `TASK_REPLACED` 保留正确**（Oracle 独立追到 `CareAdmissionService:425-430` 锁外与 `:468-473` 锁内，与我追踪 `taskReplaced()` 全部调用点的结论一致）、判据 4（**未发现改变 HTTP 或序列化业务语义**）。
- **BLOCKER**：删掉某操作**最后一个**映射到某 HTTP 状态的码后，契约仍保留该状态的 `responses` 条目 ⇒ **9 处孤儿响应**（M2-A01 的 409；M2-A03、M3-A03、M4-A05、M4-A06、M4-A07、M4-A08、f05 的 403；M4-A02 的 409）。Oracle 指出"OpenAPI 的 `responses` 本身也是有效错误声明，仅删 `x-error-codes` 会让手写契约继续告诉客户端这些状态可能发生，并与生成 Swagger 不一致"。**根因是我的验证盲区**：门禁只校验"每个声明的错误码必须有对应响应"（单向），未校验反方向；我的量化脚本也只比对 `x-error-codes` 而未比对 `responses` 状态集。
- **IMPORTANT**：`ErrorCodeDocs.java:17-21` 与 `CommonEnvelopeApiDocs.java:106-107` 仍称 `PROVIDER_CONTRACT_VIOLATION` 属"已知契约缺口"，与本轮修复冲突；指南 `:206` 残留上一轮的旧「契约过声明（生成文档保留…）」整段与新 §3.2 直接冲突（造成两个"3."）、`:203` 夸大门禁锁定范围、`:328` 对 `reportSummary` 同时说"不得假设某键存在"与"只依赖上述三键"自相矛盾、`:172` 仍称 `NOT_IMPLEMENTED` 为"501 占位"。
- **SUGGESTION**：门禁正向对照缺 3 对（M3-A03 `TASK_REPLACED`、M4-A05/A06 `RECORD_CONFLICT`），并应增加"删除最后一个码后对应 response 必须不存在"的断言。

#### 4.18 第十八轮整改（提交 `666bfbe75c5bd86129d6d8f3a5df91134ffab605`）与其窄范围复审：**PASS-with-notes**

**整改**：①9 处孤儿响应替换为**同缩进注释行**（保留删除理由与取证指引，**总行数不变** 2848→2848；diff 18 行、被删行中非 403/409 响应者为 0），三重自校验（移除集合==预期 9 处以 `(method,path,status)` 三元组为键、无新增状态、**补回后与原文件 deep-equal**）。②两处陈旧"契约缺口"表述改为"该码**刻意**属于 `AssessmentTaskView.failureCode` 的独立封闭枚举、不属于 HTTP `ErrorCode`；在 HTTP 错误码枚举中找不到它是正常的"。③门禁补 3 对正向对照（共 16 对）、新增 `orphan4xxResponseProblems()` 孤儿 4xx 守卫、`KNOWN_UNSUPPORTED_4XX_RESPONSES` 例外清单**恰 2 条**（M3-A01/A02 的 422）+ **反向陈旧守卫**、`discloseExistingContractGaps()` 弱披露（只打印不失败）。④指南 4 处修正（删旧段、如实区分"16 对门禁锁定 vs 其余人工取证"、`reportSummary` 改为"仅识别三键且每键按可选处理"、`NOT_IMPLEMENTED` 改为"契约保留码、占位 Controller 已无业务映射、已实现端点不应期待"）。
**一处险情（如实记录）**：Oracle 给的 9 个行号（231/320/718/929/1111/1159/1207/1252/1539）经我**预检发现不是响应行，而是这些操作的 `x-api-id`/`operationId` 行**（9 处逐行核对全部 MISMATCH）。若照其行号直接执行删除，会删掉权威契约的 `x-api-id` 行、造成严重损坏；故改为在各操作块内自行定位（实得第 267/344/744/962/1146/1194/1240/1290/1575 行）。**Oracle 本轮确认这些行号是"操作块锚点"、并判定我"在块内重新定位具体 403/409 行是正确且必要的安全处置"。**
**我对 Oracle 目标 #2 的偏离与裁定**：其目标"契约与生成文档对本轮 17 个操作的非 2xx 状态集合一致"**按字面不可达**——全部 34 个操作的契约都声明 `500`，而 29 个 `ErrorCode` 中只有 `INTERNAL` 映射 500 且**按设计不入任何端点 `x-error-codes`**，故生成文档从不输出 500；严格相等会在 34 个操作上全部失败，且属既有约定、非本轮造成、不在授权范围。我改为"孤儿 **4xx** 守卫 + 2 条精确例外 + 反向陈旧守卫 + 5xx 排除（附理由）+ 弱披露"，**Oracle 裁定"满足本轮目标的意图，可以接受"**，并确认其余既有差异（500×34、M3-A01/A02 的 422、M1-A02 缺 404、M2-A04 缺 422）"不是本轮引入，按授权只披露不修改合理"。

**Oracle 第十八轮裁定要点**：五项目标**全部闭合**（9 处孤儿已删且位置正确、替代方案可接受、3 项正向对照已补且"从契约与 catalog 同时删除任一对都会被 `:566-577` 捕获"、两处 catalog 陈旧说明已闭合且"未发现残留'该码未入契约'表述"、指南 4 处已闭合）；**可以将 `666bfbe75c5bd86129d6d8f3a5df91134ffab605` 作为本轮最终代码 SHA 合入 dev**；**不要求补跑完整验收、无需重跑 b14**（"它只使用 `x-error-codes`，而本轮未改该字段"；上一 SHA 的完整 41/41 足以作为业务回归证据）；**未发现改变 HTTP 或序列化业务语义的迹象**；**轮次边界确认**（无需再因普通措辞或断言精度发起重绑定；指南按 report-only 提交、内容与工作树逐字一致则无需重审）。
**Oracle 对我方 5 项主动披露的裁定（全部为"总协调应处理"，不阻塞本次合入，但"不建议永久仅靠披露保留"）**：①`500`×34——**正确方向是让生成 Swagger 也声明通用 500，而非删除权威契约的 500**；②M3-A01/A02 孤儿 `422`——总协调应确认并清理；③M1-A02 缺 `404` 响应——应在契约 `responses` 补 404；④M2-A04 缺 `422` 响应——应补 422；⑤`NOT_IMPLEMENTED`——应重新裁定，**权威契约冻结前建议从已实现操作移除**（若作为未来兼容保留，必须明确它不是当前可达码）。
**Oracle 的 2 项非阻塞 SUGGESTION（我方决定不改代码 SHA，理由见下）**：①门禁因 500 的特殊约定而排除了**全部 5xx**，未来出现孤儿 `501/503/504` 会被漏报 ⇒ 建议**只排除 500**、仍检查其它 5xx（当前无此类孤儿，故现状结果正确）；②披露文案与注释称"29 个 ErrorCode 无码映射 500"**不准确**——实际 `INTERNAL` 映射 500，只是不进入端点 `x-error-codes` ⇒ 建议改为"除刻意不进入 `x-error-codes` 的 `INTERNAL` 外，无可声明码支撑 500"。
**orchestrator 的处置决定**：**不为这 2 项 SUGGESTION 改动代码**。Oracle 已明确其属"断言精度/普通措辞"、并宣告无需再为此发起重绑定轮次；改动会使已获批的 `666bfbe` 绑定失效并制造其明示不必要的审查循环。两项连同**精确修法**记入本节与 `B.md` §15，交由总协调安排的"契约收敛任务"（上述 5 项披露本就要其裁定）一并处理。**同时如实标注**：门禁 `discloseExistingContractGaps()` 的打印文案中"29 个 ErrorCode 无码映射到 500"一句**不准确**，准确事实是"`INTERNAL` 映射 500，但按设计不进入任何端点的 `x-error-codes`"（`ApiDocsCoverageIT:1031-1034` 的注释表述是准确的，不准确的只是该打印字符串）；任何读者不应据该字符串得出结论。
**验证（orchestrator 亲自执行，绑定 `666bfbe`）**：契约四项校验器全绿（VALID、10/0、50/0 all samples valid、jcs 26 checks）；Java `test-compile` rc=0、定向 **38/0/0**（含 Coverage 1）、**全量 446 run / 0 failures / 0 errors**；孤儿 4xx 独立复查（从 `ErrorCode.java` 正则解析映射，29 码全部映射成功）**仅剩 2 处**且恰为既有的 M3-A01/A02 的 422；真实 `/v3/api-docs` 200 / **418968 字节**、swagger-ui 200；上轮已闭合项零回归（自建脚本 **78 PASS / 0 FAIL**）；契约↔生成文档非 2xx 差异 **34 个操作全部属既有类型**（仅契约有 500×34、仅契约有 422×2、仅生成有 404×1、仅生成有 422×1），**本轮修的 9 处残留 0**、无意外差异；按 Oracle 明示未重跑端到端工装与 b14。
**orchestrator 本轮错误（如实记录）**：①**验证盲区**（BLOCKER 根因）：只校验"码→响应"单向、未校验反向，也未比对 `responses` 状态集，致 9 处孤儿由 Oracle 而非我发现。②自建的孤儿复查临时脚本**连续两次崩溃**（先因映射表漏 `INTERNAL_SERVER_ERROR` 致 `KeyError`，后因改用 `http.HTTPStatus` 动态映射而 Spring 的 `PAYLOAD_TOO_LARGE` 在 Python 中名为 `REQUEST_ENTITY_TOO_LARGE` 致 `AttributeError`），第三次回到已验证可用的显式映射表才成功 ⇒ 教训：不要为"更聪明"而替换已验证可用的取证脚本。③预期集合误用了 foundation 操作并不存在的 `x-api-id` 标签（写作 `'f05'`，复算侧为 `'f0?'`），被自校验拦下、未造成损害。

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
