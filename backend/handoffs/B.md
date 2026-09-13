# B 包交付说明（账号、成员授权、设备与通知）

> 状态：**Oracle 第五轮 `VERDICT: PASS-with-notes` —— B 包门禁通过（有非阻塞披露项）；整体集成尚未就绪**（#4 扫描器周期接入、#8 A 登出代次、C/D 跨包独立验收、C25 协议冻结、C26 容量告警与受控恢复 runbook 归集成方）。
> 五轮门禁：R1 `0f933fc6` FAIL（7 BLOCKER+2 IMPORTANT）→ R2 `e6812d49` FAIL（#1/#7 闭合）→ R3 `ed5eb865` FAIL（#3/#5/#6/新BLOCKER 闭合、三处共享接缝判定正确未越界、两处设计取舍判可接受、B 测试自清判可接受；剩 #2 淘汰残留 + b37 IMPORTANT）→ R4 `954c95bf` FAIL（#2 原淘汰漏洞与 b37 均判闭合、GIMBAL 表满 fail closed 判可接受为 MVP 最终形态；新 BLOCKER：APP observer 会话表确定性永久耗尽）→ **R5 `5f0a988` PASS-with-notes**（R4 BLOCKER 判已闭合，并确认测试"确实覆盖超过默认上限的不同随机 sessionId，而非通过减少 session 数绕过问题"；新增 1 IMPORTANT + 1 SUGGESTION 均为文档缺陷，已在 `f95037e` 修正）。
> 交付 SHA `f95037e` 相对 R5 被审 SHA `5f0a988` **只有一处 javadoc 修正**（Oracle 的 IMPORTANT/SUGGESTION 处置），Java 全量仍 386/0/0；已请 Oracle 做窄范围**重新绑定确认**，结论见第 9 节与 `B-oracle.md` §4.10。
> 下方第 5、8 节数字为 orchestrator 亲自执行于该状态的真实结果（Java 386/0/0、Python 222 passed/0 failed/0 errors、契约四项全绿、验收 39/39 `SCRIPT_RC=0`）。
> 本文件与 `B-oracle.md` 为 report-only 提交，绑定下方代码 SHA（均以 `git rev-parse` 实际核实）。

## 1. 提交

- 工作树 `.worktrees/mvp-b`，分支 `feature/mvp-identity-devices`，基线 `ccee6e28a132b73098523fbc56bf25f4719e4c24`（A 已经 Oracle+E 组合验收并由总协调合入 dev）。
- 提交链（`git log --oneline ccee6e28..HEAD` 核实）：
  1. `0f933fc` `feat(B): 实现身份授权、设备管理与通知（M1/M2/M5）及统一业务媒体策略`（73 文件）— Oracle 第一轮判 FAIL
  2. `e6812d4` `fix(B): 修复 Oracle 审查的 6 个阻塞项并扩展契约与验收覆盖`（16 文件）— Oracle 第二轮判 FAIL（#1/#7 闭合，#2/#3/#5/#6 未闭合 + 1 新 BLOCKER）
  3. `7c5402b` `fix(B): 闭合 Oracle 第二轮 #2/#3 与 #5，并为 #6 做好同事务接入适配`（13 文件）
  4. **`7281edd6ba909c3dbe8c0819e1f8f958dcb4ef55`** `merge(B): 合入总协调授权的集成基线 8afd0e5（含 C+D），解决三处共享接缝冲突`（parents = `7c5402b` + `8afd0e5`，101 文件）
  5. `b452d20` `fix(B): 经 D 的 business_tx 同事务回调闭合 Oracle #6，并补全 B 测试自清`（8 文件）
  6. `ed5eb86` `test(B): 验收 b33 补末次同事务收敛证据，b37 改为要求全量零失败`（2 文件）— Oracle 第三轮判 FAIL（剩 #2 淘汰残留 + b37 IMPORTANT）
  7. **`954c95bf138a6172629dc4ae8c12dac72bda8bb8`** `fix(B): 闭合 Oracle 第三轮 #2 残留（会话表淘汰重开回滚），并加固验收 b37`（8 文件）— Oracle 第四轮判 FAIL（剩 1 个新 BLOCKER：APP observer 会话表确定性耗尽）
  8. `5f0a988` `fix(B): 闭合 Oracle 第四轮 BLOCKER——APP observer 代次键改为稳定 family`（5 文件）— **Oracle 第五轮判 PASS-with-notes：B 包门禁通过**
  9. **`f95037e5bbd37742175b52685ca833f91396e00c`** `docs(B): 修正会话代次表的恢复途径表述并补升级约束（Oracle R5 IMPORTANT/SUGGESTION）`（1 文件，纯 javadoc）← **交付 SHA**
- **最终代码 SHA = `f95037e5bbd37742175b52685ca833f91396e00c`**；Oracle 门禁结论绑定 `5f0a988`（R5 PASS-with-notes），`f95037e` 与其之间**仅一处 javadoc 差异**，已请 Oracle 窄范围重新绑定确认（见第 9 节）。
- 未推送、未合并到 dev、未发布（合并 `8afd0e5` 是总协调明确授权的**本工作树内**集成基线合入，不是推送）。
- 受版本控制的**既有文件**改动共 7 个（B 自有提交）+ 3 个共享接缝冲突文件（合并提交内，按总协调裁定由 B 作为唯一执行者解决），逐个授权依据见第 7 节。
- 各次提交均经工件核查：`.pyc`/`__pycache__`/`.class`/`target/`/`.log`/`backend/tests/.work/` 命中 **0**（`backend/tests/.work/` 实测未被 gitignore 覆盖，故按明确路径 `git add`，不用 `git add -A`，并在提交前删除诊断残留）。
- 数字纪律示例：Java 逐类 surefire 累加曾得 387 而 mvn 汇总为 386，经查是 `target/surefire-reports/` 中一份**陈旧报告**（`MediaPolicyDelegationIT`，源文件已在媒体策略收紧时删除、由 `MediaPolicyNoDelegationIT` 取代）造成的幻影 +1；已清除该构建产物，逐类累加与汇总一致为 386（`target/` 属 gitignored，不在提交面内）。

## 2. 范围与实现清单（12 API + 通知/离线 Python handler + 统一媒体策略）

| 模块 | API | 实现位置（B 新建） | 关键语义 |
|---|---|---|---|
| M1 | M1-A01 `POST /api/v1/member-access-grants` | `web/identity/MemberAccessGrantController`(211)+`MemberAccessGrantService`(474) | multipart(metadata+face)；T13 先行；`MediaIntakeService.ingest(GRANT_FACE)`；`FaceProvider` 同步核验；**只读** T01 定位可靠成员；T02 新建 active 或复用既有 active；201 新关系 / 200 已存在或重放 |
| M1 | M1-A02 `GET /api/v1/me/member-access-grants` | 同上 | 仅 active；keyset 分页对齐 `idx_grants_account_status_created`；游标绑定排序值+id+账号摘要（跨账号游标拒绝）；空列表 `items:[]`；无总数、无全库检索 |
| M1 | M1-A03 `DELETE /api/v1/me/member-access-grants/{grantId}` | 同上 | `FOR UPDATE` 行锁 + 属主校验；`active→revoked`+`revoked_at`（**保留行，绝不删除**）；204；重复撤销幂等且 `revoked_at` 不刷新 |
| M2 | M2-A01 `POST /api/v1/gimbal-sessions` | **A 基础实现（`x-foundation`），B 未改 `web/auth/**` 主代码**；B 仅写验证性 IT | 合法凭据签发云台会话且不含成员资料；凭据失败不登记可信在线；重复认证不创建护理资源；`credential_version` 递增后旧 token 立即 401 |
| M2 | M2-A02 `POST /api/v1/gimbals/{gimbalId}/heartbeats` | `web/devices/GimbalHeartbeatController`(52)+`Service`(317)+`ServerGeneration`(33) | 仅云台自身；**新旧权威 = 服务端验证的会话代次**（`observation_generation` 存 `latest_observation` JSONB）：代次变化才接受新 epoch 并重置基准，同代次内 epoch 必须一致且 seq 严格更大；被拒心跳 `accepted=false` 且不刷新 `last_seen_at`、不递增 `status_revision`、不覆盖观察；episode 开关与 `incidentId` 稳定；绝不写 `offline`；任务/执行引用只作观察 |
| M2 | M2-A03 `GET /api/v1/gimbals/{gimbalId}/status` | `GimbalStatusController`(37)+`Service`(103) | 绑定账号或云台自身可见，其余统一 404；`isStale` 不伪装实时；只投影设备状态，无成员详情；GET 无副作用 |
| M2 | M2-A04 `POST /api/v1/microcrystal-observations` | `MicrocrystalController`(55)+`Service`(420) | 先 `connectionProof` 验证（仅序列号一律拒绝）；T04 唯一 serial 定位/登记（savepoint 处理并发首建）；**同来源先比 `observer_generation`**，代次变化才重置基准，同代次内 epoch 必须一致且 seq 严格更大；`observer_*` 只来自认证上下文；`capabilities.schemaVersion`→JSONB 整数 `schema_version`；不抢占 T07、不写次数、不建任务 |
| M2 | M2-A05 `GET /api/v1/microcrystals/{id}/capabilities` | 同上 | 证明或最近观察者匹配才可见；能力存在≠空闲/就绪；不查 T07 |
| M2 | M2-A06 `PUT /api/v1/me/gimbal-bindings/{gimbalId}` | `GimbalBindingController`(69)+`Service`(374) | 仅 APP + `pairingProof` 验证；`FOR UPDATE` 锁 T03 → 比对 `expectedBindingRevision`；未绑定则写入并 +1 代次；已属本人且代次相符**不写不增**；他人已绑 → 409 `BOUND_TO_OTHER`（绝不覆盖）；代次不符 → 409 `BINDING_CHANGED` |
| M2 | M2-A07 `GET /api/v1/gimbals/{gimbalId}/binding-status` | 同上 | `X-Pairing-Proof` 必填；三态 `unbound/self/other` + `bindingRevision`，**仅此两字段**（不泄漏他人账号 ID/姓名/手机号）；不写绑定 |
| M2 | M2-A08 `DELETE /api/v1/me/gimbal-bindings/{gimbalId}` | 同上 | 三重守卫 `WHERE id=? AND bound_account_id=? AND binding_revision=?`；真实解绑 +1 代次；**未绑定云台的新键解绑请求 → 404 `RESOURCE_NOT_VISIBLE`（与 gimbalId 不存在完全不可区分），仅原 T13 成功请求的同键重放才 204**；旧 `If-Match` 跨代次 → 409，**绝不解他人新绑定**；不改成员授权/报告/方案/记录/当前任务，不发停止指令 |
| M5 | M5-A01 `PUT /api/v1/me/notification-destinations/{installationId}` | `web/notifications/NotificationDestinationController`(99)+`Service`(372)+`Dtos`(41) | 仅 APP 且路径 `installationId` **必须等于 token 派生值**；`FOR UPDATE` + `ON CONFLICT (installation_id) DO NOTHING` 首建去重；**按裁定④：仅"同会话且已 active"的纯幂等重登记不递增代次；`session_ref` 变化、`invalid` 重新激活、内容变化、换号接管一律 `destination_revision+1`（带代次守卫）**，使旧账号/旧会话的路由快照全部失配；响应仅 `{destinationId,destinationRevision,status}`（绝不回传推送 token） |
| M5 | `notification.deliver` handler | `worker-python/.../handlers/notification_deliver.py`(698) | 终态幂等 no-op（**`unknown` 已移出终态、改为可对账**）；`sending`/`unknown`+`last_attempt_at` → **先查回执对账**（provider key 稳定 `notification_id:attempt`）不盲重发；锁外会话**快照**核实 → 短事务按 **T03→T09→T10** `FOR UPDATE`，**置 sending 之前**复核 T12 业务绑定（`owner_type`/`owner_id`/`input_revision`==T10.`destination_revision`/`dedup_key`）与锁外刚核验的会话+目标代次 → 不符 `cancelled`/`failed` 且**推送零调用** → 符则标 `sending`+`attempt_count+1` 提交后**锁外发送**；`accepted→submitted`、可信回执`→delivered`、`rejected→failed`、瞬时`→JobFailed(retryable)` 退避；**末次尝试异常/耗尽时 `_converge_t10` 原子收敛 T10，绝不滞留 `sending`**；最终写守卫 `WHERE status IN ('sending','unknown') AND attempt_count=<本次>` |
| M5 | 离线/异常扫描器 | `worker-python/.../scanners/incident_scanner.py`(387)+`__main__`(9)+包出口(46) | 候选=`connection_status<>'offline' AND last_seen_at IS NOT NULL AND last_seen_at < now()-阈值`（**从未心跳不判刚离线**）；逐行短事务 `FOR UPDATE`+`status_revision` 守卫；离线 episode 复用同一 `incidentId`，恢复置 `resolved`，再离线给新 id；有绑定+有 active 目标才建 T10（复合唯一键 `ON CONFLICT DO NOTHING`，记录当时 `destination_revision`）+ T12（`dedup_key=notification:{id}`、`input_revision=destination_revision`）；改绑**新建行**绝不改旧收件人；**`last_seen_at` 只读** |
| M5 | 推送/会话端口与替身 | `worker-python/.../notifications/{push.py 131,session_probe.py 89,config.py 95,payload_schema.py 90,__init__.py 6}` | `PushProvider` 端口 + `DevTestDoublePushProvider`（env 配置 `accepted/delivered/rejected/transient/unknown` 与回执 `accepted/delivered/not_found`）；`SessionVerifier.verify` 返回 **`Optional[SessionSnapshot]`**（含 `session_ref/destination_revision/account_id/status`），dev/test 为 DB 事实探针；**生产 `RuntimeError` fail-closed，绝不默认放行** |
| 跨模块 | 统一业务 `@Primary MediaAccessPolicy` | `web/mediapolicy/BusinessMediaAccessPolicy.java`(251) | B 唯一实现（D 不自建 Primary）：①face 三类 + `assessment_source` 等核验用途**无条件拒绝且先于任何 DB 查询** ②仅 `available` 且 `purpose='assessment_result'` ③**只认 D 冻结格式 `report_ready` 的 T05 `report_payload.images[].media_id`**（已删除 `public_media_ids`/`photos[]`/`photo_versions` 猜测兼容与驼峰键名兼容）④T11 `assessment_id`/`photo_version` 必须精确匹配该 T05 的 `id`/`report_photo_version`（**禁跨版本放行**）⑤**成员归属只以 T05.member_id 为权威**；T11.member_id 非空且不一致 → **fail closed 对所有人拒绝** ⑥APP 需当前 active T02 关系／云台需 `current_assessment_id` 匹配 + `credential_version` 相符 ⑦**任何 env 下都不存在 dev owner 便利旁路**；每请求 ≤3 次单表 SELECT、只读零写、解析异常不 500、false 一律表现为与"不存在"完全一致的 404 |

代码规模（`wc -l` 实测，最终 SHA）：Java 主代码 `identity` 795 + `devices` 2157 + `notifications` 512 + `mediapolicy` 251 = **3715 行**；Java 测试 **3548 行**（13 文件）；Python 主代码 `notification_deliver` 698 + `notifications/` 411 + `scanners/` 442 = **1551 行**；Python 测试 **1297 行**（6 文件）；验收工装 **2054 行**（7 文件）。合计约 **12165 行**。

## 3. 关键业务不变量与实现落点

1. **授权永久且撤销不复活**：T02 无过期列；撤销=标志位翻转并保留行；旧 T13 重放命中已撤销行 → 403 `GRANT_REVOKED` 且**零新行**；重新授权必须新人脸请求 → 新行新 `grantId`；`uq_grant_active` 保证同 (account,member) 仅一条 active（并发下恰好一行，另一路复用返回 200）。
2. **不建档**：`members` 全程**只读**，可靠建档归 D；"库中无可靠成员"与"未匹配上"返回同一 403，不泄漏存在性、不返回候选。
3. **绑定 revision 竞争与旧解绑**：绑定/解绑均 `FOR UPDATE` 后带代次守卫字段级 UPDATE；A/B 真实并发下恰好一个成功且代次只 +1；旧账号持旧 `If-Match` 的解绑重放必 409，**不可能**解除他人新绑定；**未绑定云台对新的未知解绑请求统一 404**，服务端不猜测之前归属。
4. **设备状态新旧权威 = 服务端验证的会话代次**：`ServerGeneration` 只从 `PrincipalContext` 派生（GIMBAL=`credentialVersion`+`sessionId`，APP=`sessionId`；`credentialVersion` 由 A 的 `PrincipalRevalidator` 每请求对 T03 复核），**绝不取请求体**。客户端自填 epoch 仅在"同代次内必须保持不变"的意义上被校验，因此**同会话翻转 epoch + 降 seq 的回滚攻击被拒绝且逐列未变**；只有真实代次推进（凭据轮换 + 重新认证）才重置基准。
5. **云台独立认证与仅当前任务协作**：云台主体只由设备会话 token 派生；B 的云台可见性判定只认 `current_assessment_id`，历史任务/历史报告一律 404；B 代码**零写入** `current_assessment_id/current_assessment_revision`。
6. **`last_seen_at` 单向所有权（C7 裁定）**：唯一写点是心跳接受路径（服务端 `now()`，不用客户端 `observedAt`）；扫描器只读（验收 b26 以 SQL 快照 + 源码 grep 双向核验）；心跳绝不写 `offline`；`status_revision` 仅在 `connection_status` 实际变化时 +1。
7. **episode 稳定与通知不误发**：`incidentId` 服务端生成，同 code 活跃期复用、清除置 resolved、再发生给新 id；T10 复合唯一键 + `dedup_key` 双重去重；无绑定不建通知、无有效目标不记 `submitted`；**投递前与重试前均重检绑定/代次/目标/episode + 锁外刚核验的会话快照**，不符即 `cancelled` 且推送零调用；改绑只新建行、绝不改旧收件人；换号与会话变化靠 `destination_revision` 递增使旧快照失配。
8. **`submitted` ≠ `delivered`，且恢复链闭合**：仅可信受理 ID → `submitted`，仅可信送达回执 → `delivered`；发送后崩溃留 `sending` 可观测态；`unknown` 不是"终态且任务成功"，而是**可继续对账**状态，再次处理先查回执（同一 `provider_message_key`），收敛失败则由 A 的退避驱动有界重试，**末次原子收敛 T10，绝不滞留 `sending`**；不承诺 exactly-once，已受理消息不承诺撤回。
9. **T12 业务绑定必须复核**：handler 在锁内、置 `sending` 之前校验 `owner_type`/`owner_id`/`input_revision`(==T10.`destination_revision`)/`dedup_key`，任一不符 → 绝不推送、T10 `failed`+`UNSUPPORTED_CONTRACT`(retryable=false)、T12 经 A 既有 `complete_failure` 终结，**不自创错误码、不改 A runtime**。
10. **通知内容合规**：T10 `payload` 为最小正文（`schema_version`/`event_type`/`incident_id`/`gimbal_id`/`text`），**不含成员 ID/姓名、媒体/照片、报告 ID、手机号**；测试对 payload 键集合与推送替身实收内容双向断言。
11. **媒体成员归属只以 T05 为权威**：T11.member_id 不参与授权；与 T05 不一致即 **fail closed**（对所有人拒绝，含 T05 属主），并记不含敏感内容的 warn（`branch=t11-t05-member-mismatch`），闭合"T11 被写成他人即可让持他人授权者读到受害成员报告图"的越权路径。
12. **可见性统一 404**：不存在／属他人／类型不符一律同一 404 `RESOURCE_NOT_VISIBLE` 同一 message；错误信封仅 `requestId` 因契约强制逐次不同，比较时掩蔽该字段后逐字节一致。

## 4. 架构红线遵守证据（orchestrator 独立 grep/SQL 复核 + Oracle 复审）

- **禁 JOIN/关联子查询**：B 的四个 Java 主代码包与 6 个 Python 文件中 SQL 层面 `\bJOIN\b`/`EXISTS(SELECT`/`IN(SELECT` 命中 **0**。
- **字段级 UPDATE、禁整行覆盖**：所有 UPDATE 均显式列清单 + 守卫谓词（`status_revision`/`binding_revision`/`destination_revision`/`attempt_count`/`observation_epoch+seq`/`status='active'`/`status IN ('sending','unknown')`）。
- **不写他包与成员表**：`UPDATE|INSERT INTO|DELETE FROM` 针对 `members`/`care_executions`/`care_records`/`care_plans`/`skin_assessments`/`async_jobs`（Java 侧）命中 **0**。
- **不碰绑定/任务指针（Python 侧）**：`bound_account_id=`/`binding_revision=`/`bound_at=`/`current_assessment*` 的 UPDATE/SET 命中 **0**；扫描器对 `gimbals` 仅两条 UPDATE（置 `offline`+`status_revision+1`+`active_incidents`；维护 `active_incidents`），**均不含 `last_seen_at`**。
- **Python 绝不写 T13**：`idempotency_requests` 在 B 的 Python 代码中命中 **0**。
- **注册表最小追加**：`handlers/__init__.py` diff 恰为 4 行（空行+import+空行+register），A 的 `system.echo` 注册与既有内容一字未改；`test_unsupported.py` 改为契约白名单断言（必含 `system.echo` 且 ⊆ 契约声明的 6 个 job_type），故 C/D 后续各自新增条目时仍成立。
- **锁顺序**：投递重检事务内依次 `gimbals … FOR UPDATE` → `notification_destinations … FOR UPDATE` → `notifications … FOR UPDATE`；推送调用在该事务提交之后（锁外）。
- **媒体策略只读**：全类仅 4 条单表 SELECT，每请求至多执行 3 条，零写语句、零缓存（撤销下一次请求即生效）。
- **生产 fail-closed**：设备证明替身 `@Profile({"dev","test"})`+`app.providers.mode=doubles` 双门禁，生产由 B 自有 `DeviceProofFailClosedValidator`（`app.env=production`）拒绝启动；`IdentityProvidersConfig` 同理（生产无 `FaceIdentityResolver` bean → 启动失败）；Python `build_push_provider`/`build_session_probe` 在 `settings.production` 时直接 `RuntimeError` 拒发/拒投；媒体策略在任何 env 下都不委派便利策略。**未修改 A 的 `ProductionFailClosedValidator`**。

## 5. 测试结果（orchestrator 亲自执行；Java 于交付 SHA `f95037e`，其余于 `5f0a988`/`b452d20`，差异仅一处 javadoc）

```bash
cd backend/web-java && env MVP_A_PG_JDBC=jdbc:postgresql://127.0.0.1:55435/postgres \
  MVP_A_PG_USER=postgres MVP_A_PG_PASSWORD=mvp_b_local mvn -B test
# → Tests run: 386, Failures: 0, Errors: 0, Skipped: 0；BUILD SUCCESS；rc=0

cd backend/worker-python && env MVP_A_PG_DSN=postgresql://postgres:***@127.0.0.1:55435/postgres \
  MVP_A_PG_HOST_PORT=55435 MVP_A_PG_USER=postgres MVP_A_PG_PASSWORD=*** MVP_A_PG_CONTAINER=mvp-b-pg \
  .venv/bin/python -m pytest -q
# → 222 passed；0 failed；0 errors；rc=0

cd backend/contracts && .venv/bin/python -m openapi_spec_validator openapi/openapi.yaml   # OK, rc=0
cd backend/contracts && .venv/bin/python scripts/validate_responses.py --selftest          # 10 checks passed, rc=0
cd backend/contracts && .venv/bin/python scripts/validate_samples.py                       # 50 checks passed, rc=0
cd backend/contracts && .venv/bin/python scripts/jcs.py selftest                           # 26 checks, rc=0

bash backend/tests/run-acceptance-b.sh                                                     # ALL PASS 39/39, SCRIPT_RC=0
```

- **Java 全量 386/0/0 rc=0**（合并集成基线 `8afd0e5` 后含 A+B+C+D 全部测试）。其中 **B 自有 70 项**，按 surefire 逐类核实：`identity` 12、`devices` 30、`notifications` 11、`mediapolicy` 17。
  - B 自有覆盖含 Oracle 各轮要求的反例：同会话翻转 epoch/降 seq 被拒且逐列未变、**两个并存会话交替时旧会话永不重获权威**、**会话表满对未见 session fail closed 且不淘汰旧会话、仅凭据推进可恢复**、**同一 account+installation 连续 11 次 login 全部接受且表项恒为 1（APP 永不耗尽）**、新键解绑未绑定云台 404 且与不存在 UUID 逐字节一致、T11/T05 成员不一致对所有人 fail closed、冻结报告 `images[]` 引用判别力、T12 四项绑定不符零推送、过期 lease 业务写整体回滚、末次失败 T10 与 T12 同事务终态化。
  - 数字纪律：逐类累加曾得 387，经核实是 `target/surefire-reports/` 中一份**陈旧报告**（`MediaPolicyDelegationIT`，其源文件已在媒体策略收紧时删除、由 `MediaPolicyNoDelegationIT` 取代）造成的幻影 +1；已清除该构建产物，逐类累加与 mvn 汇总一致为 386。`target/` 属 gitignored，不在提交面内。
- **Python 全量 222 passed / 0 failed / 0 errors / rc=0**；其中 **B 自有 6 个文件 47 passed**。两种相反文件顺序（D 先 B 后、B 先 D 后）各 113 passed、rc=0 ⇒ B 的自清 teardown 不依赖执行顺序。
  - 注：合并 `8afd0e5` 后 `tests/test_sanity.py` 实测 4/4 通过，**原 C15 的环境耦合失败已不再复现**，故不再作为"已披露失败项"；验收 b37 相应改为硬断言 `rc==0`/`failed==0`/`errors==0`/`passed>=200`。
- **契约四项校验全绿**（rc 均 0）；`backend/contracts/` 自合并 `8afd0e5` 后未再改动（B 的契约改动共 4 个 operation、8 行，见第 7 节）。
- **端到端验收 39/39、SCRIPT_RC=0**（真实进程：Spring Boot jar @18083、真实 Python worker loop @18084、`python -m mvp_worker.scanners --once`、ephemeral Flyway 库）；**b14 契约驱动观测面由 31 条扩至 37 条**、12 端点全覆盖、所有观测码均属端点声明集合。
- 真实 PG（非 SQLite、非 mock）：容器 `mvp-b-pg` postgres:16 @127.0.0.1:55435；并发用例为真实多线程/真实并发 HTTP（绑定竞争、首建竞争、并发领取）。

## 6. 实际接入与替身限制（如实报告，未假装完成）

1. **人脸提供方未接入**：沿用 A 的 `FaceProvider` 隔离替身（固定分类）。A 的端口只返回分类枚举、不返回身份引用，故 B 新增自有 seam `FaceIdentityResolver`，dev/test 以 `face_subject_ref = sha256(图片字节)` 确定性派生；生产无 bean → 启动失败。**该替身无法表达"账号允许的候选范围"与真实身份歧义**（协调 C9）。
2. **推送通道未选定**：`PushProvider` 端口 + `DevTestDoublePushProvider`（env `MVP_NOTIFY_PUSH_DOUBLE`/`MVP_NOTIFY_PUSH_RECEIPT` 配置四态与回执）；生产 `build_push_provider` 直接 `RuntimeError` 拒发。`submitted≠delivered`、崩溃后靠回执对账，**不承诺 exactly-once**，已受理消息不承诺撤回。
3. **会话提供方未选定**：投递前会话核实 dev/test 为 DB 事实探针（T09 `session_ref/status/account_id/destination_revision`）；生产 `build_session_probe` 抛错拒投。登出失效依赖 A 既有接线 `AuthController:134 → invalidateDestinations`（B 未改 `web/auth/**` 主代码），经重检 `destination_changed` 取消。
4. **设备配对/连接证明协议未冻结**：B 自有 `PairingProofVerifier`/`ConnectionProofVerifier` 端口 + `DevProofCodec`（`d1.<b64url payload>.<b64url HMAC-SHA256>`）替身，可产生有效/验签失败/过期/绑他云台/绑他账号/nonce 重放六种输入；生产由 B 自有 fail-closed 校验拒绝启动。真实设备签名算法、密钥预置/轮换、可信硬件能力仍待设备团队对接。
5. **阈值未冻结（D02/D03）**：`app.devices.staleness-seconds=300`、`offline-seconds=300`、`incident-suppression-seconds=60`；`MVP_NOTIFY_OFFLINE_THRESHOLD_SECONDS=120`、`SCAN_INTERVAL_SECONDS=30`、`REMINDER_SUPPRESSION_SECONDS=3600`、`RECONCILE_UNKNOWN=true`、`RESEND_ON_NOT_FOUND=true`。全部为**联调起点、非承诺**，可配；实际重复提醒抑制依赖 T10 复合唯一键。未自创固定秒数当验收标准。
6. **【未闭合的集成依赖】扫描器周期触发未接入既有 Worker**（Oracle 第一轮 BLOCKER #4，总协调裁定维持 C8）：B 提供可重入纯函数 `run_once(engine, settings) -> ScanReport` 与 CLI `python -m mvp_worker.scanners --once`（验收脚本即以此驱动，b26/b27/b35 全绿）；**B 未修改 A 的 `loop.py`/`__main__.py`/`config.py`/`db.py`，也未经 deploy 新增常驻服务/cron/compose 单元**。因此：**只启动既有 Worker 进程不会周期发现离线事件**，必须由总协调在集成时按 `.coordination/B-work/scanner-integration.md`（入口签名、周期建议、幂等与并发约束、失败重试约束、可观测性五项齐全）完成进程内周期调用并实际验证离线检测后，相关**整体**功能才可宣称验收通过。该发现按裁定如实保留，**不删除、不视为已通过**。
7. **A 的 `test_sanity.py::test_config_defaults` 环境耦合断言（C15）——合并后已自然消解**：该断言把 `cfg.check_dsn` 与硬编码 55432 默认值比较，而 `conftest.py` 的 `MAINT_DSN` 与 `WorkerConfig.check_dsn` 同读 `MVP_A_PG_DSN`，故任何非 A 默认端口的隔离运行都必然失败（B 曾以无覆盖对照证明断言本身完好：无 env 覆盖时 `check_dsn_is_default`/`runtime_dsn_is_default`/`pool5_health8081` 均为 `True`，加 B 覆盖后 `check_dsn_is_default=False`）。**合并集成基线 `8afd0e5` 后该文件实测 4/4 通过，失败不再复现**，故不再作为已披露失败项；B 全程**未修改**该 A 测试。验收 b37 相应改为硬断言 `rc==0`/`failed==0`/`errors==0`/`passed>=200`。
8. **A 的登出失效不递增 `destination_revision`**（Oracle IMPORTANT #8，A 归属）：`web/auth/AuthController.invalidateDestinations`(:190-195) 把 T09 置 `status='invalid'` 但未 `+1`，技术上违反裁定④"登出失效…不复用旧 revision"。B 未改 A 文件。**投递安全已闭合**：探针要求 `status='active'`（否则返回 `None`），锁内重检亦判 `status != active → destination_changed → cancelled`，故登出后旧通知必被取消、不误发；重新激活经 B 注册分支必 `+1`。残余仅"登出瞬间代次数值不变"。Oracle 判其对 B 门禁**非阻塞**、A 待修，已记入协调台账。
9. **T10 无 `session_ref` 快照列**：按裁定④**不新增列**，改以"T09 任何安全相关变更必递增 `destination_revision` + T10 创建时记录该 revision + 锁外会话快照带入锁内逐项复核"覆盖，会话变化安全用例已恢复并强化为 TOCTOU 形态（核验通过后、加锁前改 `session_ref` → `cancelled`、推送 0 次）。原协调 C12 据此闭合。
10. **`report_payload` 形状已按裁定③冻结**：只认 D 的 `images[].media_id`（下划线键、无 `public` 标志），已删除全部猜测兼容分支；原协调 C10b 据此闭合。若 D 的最终写入形状与此不符，须由协调统一后再改 B。
11. **未实现/未触碰**：成员可靠建档（D）、M3/M4 业务（D/C）、账号注册登录退出的 HTTP 契约（A 基础协议）、真实 OSS/短信/人脸/推送接入、`backend/doc/site|web`。M1 不创建成员；B 不另建媒体策略以外的第二套授权策略。
12. **既有测试隔离弱点（非本次引入、非阻塞，如实披露）**：`worker-python/tests/conftest.py` 的 `clean_tables` 不清 `notifications`/`gimbals`/`notification_destinations`，而扫描器 `run_once` 扫全表；D 的 `tests/d_support.py:59 clean_d_tables()` 又直接 `DELETE FROM gimbals`，与 B 的 `notifications_gimbal_id_fkey` 冲突 ⇒ 合并后全量 pytest 曾出现 78→51 个 fixture setup ERROR（顺序依赖可证：D 文件单跑全绿）。**B 未修改任何公共/D 文件**，改为在 B 写域内新增 `tests/b_support.py` 自清（按 FK 顺序 `async_jobs`→`notifications`→`notification_destinations`→`gimbals`→`accounts`，且只删 B 以前缀 `notif-gimbal-%`/`notif-inst-%`/`notif-%`/`job_type='notification.deliver'` 标识的行，不做全表清空），并在 6 个 B 测试文件挂载 autouse fixture ⇒ 全量 **222 passed / 0 error**，两种相反文件顺序各 113 passed。Oracle R3 判定该处置**可接受、不属用测试技巧掩盖生产缺陷**。纵深防御建议（C22）仍留待 D/公共评估：`clean_d_tables` 在删 `gimbals`/`accounts` 前先删 `notifications`/`notification_destinations`。
13. **【需总协调冻结的协议约束】C25 — APP 观察流必须持久化 epoch/seq**：采用"APP 代次键=稳定 family"后，同一 `account:installation` 内 `observationEpoch` 必须保持一致且 `observationSeq` **严格单调递增**，否则该次上报 `accepted=false`（不写库）。因此 **APP 必须跨登录、token refresh 与普通进程重启持久化 `observationEpoch` 与每微晶的 `observationSeq`**；重启后不得把 seq 归 1、不得自行更换 epoch。Oracle R5 裁定：该约束 **fail closed、不会使旧状态覆盖新状态，可作为 MVP 非阻塞协议约束，但必须冻结并披露**；若产品要求"重启后 seq 从 1 开始"，则**必须在生产接入前**改用 Oracle 方向②（由 B 自有 `ConnectionProofVerifier` 从已验证的 `connectionProof` 返回可信连接 generation，客户端不得自行换 epoch）或方向①（A 的 `SessionProvider` 暴露稳定 family/可比较 generation，跨包需授权）。本轮只实现方向③，未两套并存。
14. **【运维必须配套】C26 — generation 表容量、告警与受控恢复**：`app.devices.max-observation-sessions`（默认 8）是可用性/JSONB 大小权衡。**GIMBAL**：表满后未见 session 被 fail closed 拒绝、不刷新 `last_seen_at`，可能被离线扫描误判并触发通知；唯一自动恢复途径是 `credential_version` 推进（凭据轮换/重新配网），Oracle 判其**可接受为 MVP 最终形态**，但要求生产初值评估 **32~64**、配置表满告警、提供凭据轮换 runbook。**APP**：同一 family 永不耗尽，但若同一微晶被超过上限个**不同 `account:installation` 组合**观察，则未见 family 被 fail closed，且 **APP 没有自动恢复途径**——Oracle 明确纠正："生产新 family 并不能恢复"（表满后新 family 正是被拒对象）；当前实际可用手段只有 ① observer **类型**切换（APP↔云台）清空代次表、② GIMBAL 的凭据推进、③ **受控运维重置**（按运维流程清空该行 `latest_observation` 的代次表并留审计，不提供业务 API）、④ 待可信 generation 取代本表。**仅调高上限不是恢复机制，只是推迟触顶。** B 已埋 warn 分支 `session-table-full-fail-closed`（仅含 `gimbalId`/`microcrystalId`+`maxSessions`，不含 sessionId/token/成员信息）可直接用于告警。deploy/runbook 属 A/集成归属，B 未写。
15. **【升级约束】JSONB 键 `session_id` 名实不符，中间版本不得原地升级**：代次表元素的 JSON 键沿用 `session_id`，但其值现在是"**代次键**"（GIMBAL=随机 `sessionId`，APP=稳定 family `accountUuid:installationId`），阅读时须按 `generation_key` 理解；保留旧键名只为避免无必要的格式迁移。与早期中间版本（APP 也写随机 sessionId）**仅格式兼容、非语义兼容**——旧条目不会被 family 命中却仍占用容量。故 **中间版本（`7c5402b`…`5f0a988` 之间的任何状态）不得原地升级到 `f95037e`**；若已存在持久数据，须执行受控转换或重置（清空代次表，由首次观察重建 `generation=1`）。Oracle R5 提出、R6 确认该披露已正确写入代码 javadoc。
16. **T10 不再主动写 `unknown`（Oracle R3 要求披露的可观测性变化）**：不确定结果表现为 T10 `sending` + T12 `queued` 且其 `last_error` 记 `delivery_unknown`，下次领取优先回执对账；因此**仅看 T10 无法区分"发送后崩溃"与"provider 明确返回 unknown"，需结合 T12 `last_error` 判断**。恢复与安全语义完整（不重复投递、末次同事务收敛、旧 lease 整体回滚），历史 `unknown` 行仍兼容处理。属 MVP 简化的可接受代价，监控与运维文档须据此设计。

## 7. 共享文件改动清单与授权依据（7 个既有文件）

| 文件 | 改动 | 授权依据 |
|---|---|---|
| `backend/contracts/openapi/openapi.yaml` | 共 **4 个 operation、8 行**：`m1A01` 补 `FACE_NOT_VERIFIED`；`m1A02` 补 `'403'` + `CALLER_NOT_ALLOWED`；`m2A07` 补 `INVALID_INPUT`；`m1A03` 补 `INVALID_INPUT`+`'400'`；`m2A08` 补 `INVALID_INPUT`+`'400'`；`m5A01` 补 `BINDING_CHANGED` | 第一轮 C1 裁定 + 第二轮裁定① + Oracle BLOCKER #1 整改（总协调授权 B 为唯一负责人，"仅补与既定调用方限制/输入校验一致的遗漏声明，不改业务语义、不全局放宽"）；四项契约校验复跑全绿 |
| `web/stub/NotYetImplementedController.java` | 删除 B 的 11 个占位方法（M1×3、M2-A02~A08×7、M5-A01×1），保留 M3×6+M4×9 共 15 个 | 任务书与 tasks/README："B/C/D 可仅移除自己负责的端点占位" |
| `web/stub/StubEndpointsIT.java` | 501 抽样由 7 个收缩为 6 个仍 contract-only 的端点（M3-A01/A03/A06、M4-A03/A05/A08），断言逻辑一字未改 | 上述授权的必然结果；协调 C14 请追认 |
| `web/auth/AuthFlowIT.java` | 过时"M5 stub=501"断言改为**权限语义**断言：合法体 + 云台 token → 403 `CALLER_NOT_ALLOWED`；另测非法体 `{}` → 400 `INVALID_INPUT`（两路可区分，不把偶然 400/404 当权限证据）；再加"被拒 installationId 零写入" | 第二轮裁定②明文授权 |
| `web/media/OwnerDevMediaAccessIT.java` | `ownerDevNonFacePossitive` 原断言"owner-dev 下上传者读 `ASSESSMENT_SOURCE` 得 200"验证的正是裁定③**明确禁止**的 dev owner 旁路，改为断言其被拒（404 `RESOURCE_NOT_VISIBLE`）；他人/换安装/匿名隔离断言原样保留 | 裁定③"不得存在 dev owner 便利路径旁路"+"核验证据不经业务 HTTP 读取"的必然结果；按裁定②确立的同款模式最小适配，协调 C14 请追认 |
| `worker-python/src/mvp_worker/handlers/__init__.py` | 末尾追加 4 行（import + `register(notification.deliver)`） | 任务书："B/D handler 注册表仅各增各条目" |
| `worker-python/tests/test_unsupported.py` | `test_only_system_echo_registered_in_A`（断言注册表 `== ("system.echo",)`）改为 `test_registered_handlers_are_only_contract_job_types`（必含 `system.echo` 且 ⊆ 契约声明的 6 个 job_type）；其余 `UNSUPPORTED_CONTRACT` 隔离用例未改且仍全绿 | 注册表授权的必然结果；协调 C14 请追认 |

`web/auth/**` 主代码、`web/media/**` 主代码、`web/config/**`、`web/idempotency/**`、`web/jobs/**`、`web/error/**`、`web/web/**`、`web/system/**`、`web/testdouble/**`、`worker-python` 的 A runtime（`loop.py`/`runtime/**`/`db.py`/`rows.py`/`config.py`/`__main__.py`/`system_echo.py`）、迁移、`backend/deploy/**`、`backend/doc/**` **零改动**（`git status`/`git diff --name-only` 核实，Oracle 亦独立核实）。

## 8. 端到端验收（`backend/tests/run-acceptance-b.sh`，b1–b39）

- 实际命令：`bash backend/tests/run-acceptance-b.sh`（于 `5f0a988`，真实进程 + 真实 PG ephemeral 库；交付 SHA `f95037e` 相对它**仅一处类级 javadoc 差异**，Oracle 第六轮明确**不要求**为重新绑定重跑端到端验收，并已在 `f95037e` 状态复核 Java 全量 386/0/0）
- 结果：**`RESULT: ALL PASS（39/39）`，`ALL PASS 39/39`，`SCRIPT_RC=0`**；`0 BLOCKED`（无依赖 C/D 未交付而无法验证的项）
- b39 证据绑定：tracked 变更 before/after 逐行一致、HEAD 未变（验收过程未污染整树）
- 覆盖任务书点名的全部验收点：12 API 有效/无效主体（b1–b13）、A/B 真实并发绑定竞争（b15）与旧解绑不得解除新绑定（b16）、撤销后报告图片不可读且旧授权请求重放不复活（b17–b19）、face/核验用途永不放行与冻结报告引用判别力（b20）、云台仅当前任务（b21）、旧心跳/回滚攻击不得改状态（b22–b23）、episode 稳定性（b24）、worker SIGTERM 重启不丢任务不重复投递（b25）、C7 `last_seen_at` 只读双向核验（b26）、扫描→通知→真实 worker 且 `submitted`≠`delivered`（b27）、无绑定/无有效目标不假装成功（b28–b29）、解绑/换号/重试前重检不误发且推送零调用（b30–b32）、unknown 对账不盲重发（b33）、通知内容不含成员/照片/报告/手机号（b34）、重复领取与重复扫描不产生重复通知（b35）、Java/Python 全量（b36–b37）、注册表与 `UNSUPPORTED_CONTRACT` 不循环（b38）、整树未被验收过程污染（b39）、契约驱动错误码白名单（b14，37 条观测/12 端点）
- 复跑方式与选项：`bash backend/tests/run-acceptance-b.sh`；`B_ACCEPT_KEEP_DB=1`（保留库与临时目录）、`B_ACCEPT_BASE=<dir>`、`B_ACCEPT_FILTER="b1 b14"`（调试子集；注意 b4 依赖 b1 产生的 `$TMP/b1.grant`，单独跑 b4 会因缺前置数据而假失败）
- 退出码约定：`0`=全部 PASS；`1`=有 FAIL；`4`=前置自检/环境不满足（未真正执行检查）

## 9. Oracle 逐模块审查结论

详见 `backend/handoffs/B-oracle.md`（含六轮全部发现、依据文件:行、我的裁定与总协调裁定、Oracle 实际执行的核查命令）。摘要：

- **第一轮（被审 SHA `0f933fc6`）：`VERDICT: FAIL`**，7 BLOCKER + 2 IMPORTANT。已在 `e6812d49` 修复 #1/#2/#3/#5/#6/#7，#4 按裁定维持 C8。
- **第二轮复审（被审 SHA `e6812d49`）：`VERDICT: FAIL`**。Oracle 判定 **#1、#7 已闭合**；**#2、#3、#5、#6 仍未闭合**，并新增 1 个 BLOCKER（`_converge_t10` 为独立事务，不受 T12 `lease_owner/lease_revision` 守卫）。Oracle 明确区分：**(a) B 包门禁结论 = 不通过**（#2/#3/#5/#6 属 B 可自决范围）；**(b) 整体集成就绪 = 未就绪**（另含 #4 扫描器未接入、#8 A 登出不递增代次）。
- Oracle 对我在 #7 上的裁定（T11/T05 成员不一致即对所有人 fail closed）**确认"完全符合此前要求"**。
- **第三轮修复（已落地于 `7c5402b` + `b452d20`）**：Java 修 #2（epoch 权威改为服务端观察到的有界会话代次表，旧会话永不重获权威）与 #3（`bound_account_id IS NULL → 404` 提前到 revision 判断之前）；Python 按总协调范围澄清做最小适配（#5 校验前移到所有状态分支之前并在写回事务内复校；失败路径消除"T10 先独立提交、随后被 T12 守卫拒绝"的被禁止顺序，并把 T10 收敛重构为可交给 D 的同事务 callback）。
- **公共接口集成依赖（不由 B 修复）**：总协调已指定 **D 唯一实现** `complete_failure` 的同事务 callback 扩展与 `loop` 的 `except JobFailed → _finish_failure → complete_failure` 最小透传；**#4 扫描器周期接入由总协调唯一负责**。B 不改公共 runtime、不复制 T12 状态机；两项均如实保留为未闭合依赖，**不删除、不视为已通过**。最小本包适配待接入说明见 `.coordination/B-work/notification-adapter-handoff.md`。
- **第三轮复审（被审 SHA `ed5eb865`）：`VERDICT: FAIL`**，但只剩 1 个代码级 BLOCKER + 1 IMPORTANT + 1 SUGGESTION。Oracle 判定**闭合**：#3（unbound 判断已提前，原复现统一 404）、#5（入口校验 + 事务内复校 + 反例测试）、#6 与新 BLOCKER（`JobFailed.business_tx` → `complete_failure` 同事务先业务写后 lease 守卫，0 行 → `StaleGeneration` 整体回滚）、**三处共享接缝解决全部正确、未越界、未削弱断言**（并评 `StubEndpointsIT` 的路由表证明"比依靠 400/404 的请求抽样更可靠"）、**两处设计取舍 (a)(b) 可接受**（(b) 附披露要求）、**B 测试自清可接受、不属用测试技巧掩盖生产缺陷**。未闭合：#2 的**有界淘汰**重新打开 epoch 回滚（→ `954c95b` 按 Oracle 方案②闭合）；b37 未检查 rc/errors（→ `ed5eb86` 闭合）；`NotYetImplementedController` javadoc/死代码（→ C23 提请集成所有者）。
- **第四轮复审（被审 SHA `954c95bf`）：`VERDICT: FAIL`**。Oracle 判定**闭合**：#2 原淘汰漏洞（`git grep prune` 计数 0，四条路径均有测试）、b37 IMPORTANT（rc/failed/errors/passed 四项硬断言，`errors?` 可匹配单数）；并判 **GIMBAL 表满 fail closed 可接受为 MVP 最终形态**、`NotYetImplementedController` 死代码**不阻塞 B**。**新 BLOCKER（系我 R3 选择方案②时引入）**：APP 主体 `credentialVersion` 恒为 0 而每次 refresh 生成新 sessionId，会话表只增不减 ⇒ 同一 `account:installation` 累计 8 个 session 后所有正常新会话**永久 `TABLE_FULL`**；Oracle 定性为"确定性正常生命周期故障，不只是极端并发"、"仅调高上限会推迟故障，不能解决"、"这是 blocker，不能仅作为普通限制接受"。
- **第五轮修复（已落地于 `5f0a988`）**：采 Oracle 方向③（纯 B 写域、不改公共/A 文件）——按主体类型分派代次键，**APP 用稳定 family（`account:installation`）、GIMBAL 保留 sessionId 且语义不变**；同 family 内仍要求 epoch 一致且 seq 严格更大。取证前提（我亲自核实）：`openapi.yaml` 的 `m2A04` 明文"调用方：**APP 或云台**"、DD §M2-A04 未限定云台 ⇒ **APP 路径是契约要求存在的，不得删除或改 403**；且现有 `MicrocrystalService:410-412` 中 APP 的 `Observer.ref` 本就是稳定 `account:installation`，耗尽根源是代次表用随机 sessionId 作键。新增 `MicrocrystalObservationIT.appRefreshSessionsNeverExhaustFamilyTable`（同一 account+installation 连续 11 次 login 全部接受、表项恒为 1、generation 恒为 1）与验收 b8 的 HTTP 级回归锁（10 个 session > 默认上限 8，全部接受且表项恒为 1）。
- **由此产生、需总协调冻结的协议语义（C25）**：同 family 内 epoch 必须一致且 seq 严格更大 ⇒ APP 重启后若把 seq 归 1 或自行换 epoch，其上报将被拒绝；需 APP 侧把 `observationSeq` 单调持久化，或改用 Oracle 方向②（B 自有 `ConnectionProofVerifier` 从已验证证明返回单调连接 generation）/方向①（A 的 SessionProvider 暴露稳定 family，跨包需授权）。
- **运维注意事项（C26，Oracle 明确要求披露）**：`app.devices.max-observation-sessions`（默认 8）是可用性/JSONB 大小权衡；GIMBAL 表满后未见 session 被 fail closed 拒绝、不刷新 `last_seen_at`，可能被离线扫描误判并触发通知。Oracle 建议生产初值评估 **32~64**、配置表满告警（B 已埋 `branch=session-table-full-fail-closed` warn，仅含 `gimbalId`/`microcrystalId`+`maxSessions`，不含 sessionId/token/成员信息）、并提供凭据轮换 runbook 作为现场恢复手段（B 不写 deploy，属 A/集成归属）。
- **公共接口集成依赖（不由 B 修复）**：#4 扫描器周期接入由**总协调唯一负责**（C17，维持 C8；B 只维护可重入 `run_once` 与 `--once` CLI，验收以 CLI 驱动，**不代表生产周期运行形态**）；#8 A 登出不递增 `destination_revision`（C18，A 归属；B 侧投递安全已闭合）；C/D 约两万行业务实现 Oracle 本轮未重新独立审查，集成方仍须在最终合并 SHA 上执行跨包端到端验证。
- **第五轮复审（被审 SHA `5f0a988`）：`VERDICT: PASS-with-notes`**。Oracle 判定 R4 BLOCKER **已闭合**（`MicrocrystalService.java:264-317,437-440`、`ObservationSessions.java:18-24,95-127`、`MicrocrystalObservationIT.java:252-288`、`b-checks-1.sh:202-224`；APP 使用服务端认证派生的稳定 `accountUuid:installationId` 作代次键，refresh/login 不再新增表项，原复现中第 9 个及后续 session 与前八个命中同一表项），并确认"测试确实覆盖了超过默认上限的不同随机 sessionId，而非通过减少 session 数绕过问题"。四点裁定：①稳定 family + GIMBAL sessionId + JSONB 键沿用 `session_id` **可接受**（但名称已不准确，须在文档明确其实际含义为 `generation_key`）；②**C25 可作为 MVP 非阻塞协议约束，但必须冻结并披露**（fail closed、不会使旧状态覆盖新状态；代价是 APP 必须跨登录/refresh/普通重启持久化 `observationEpoch` 与每微晶 `observationSeq`；若产品要求重启后 seq 从 1 开始，则必须在生产接入前改用 `ConnectionProofVerifier` 返回可信连接 generation）；③**APP 不同 family 达上限可作为 MVP 的 fail-closed 残留限制，但描述需修正**——"生产新 family 可恢复"**不正确**（表满后新 family 正是被拒对象），当前自动恢复只能来自 observer 类型切换造成表重置，或未来引入可信 generation/受控运维重置，且必须配置告警、容量值与受控恢复 runbook，**仅调高上限不是恢复机制**；④两层结论见下。新发现：1 IMPORTANT（`ObservationSessions.java:45-49` 注释与 `resolve():110-113` 行为矛盾）+ 1 SUGGESTION（`session_id` 名实不符、与旧数据仅格式兼容非语义兼容）。
- **第六轮（窄范围重新绑定确认，被审 SHA `f95037e`）：`VERDICT: PASS-with-notes`**。`f95037e` 是处置上述 IMPORTANT/SUGGESTION 的**纯 javadoc 提交**（`ObservationSessions.java:44-65` 为唯一变更，未触及语句/签名/常量/字段/控制流/测试，`git diff --check` 通过）。Oracle 确认两条发现**均已正确处置**，并明确：R5 的两层结论**原样重新绑定到 `f95037e`**；**不要求**为重新绑定重跑端到端验收（理由：只有类级 javadoc 变化，且 orchestrator 已在该状态执行 Java 全量 386/0/0）；**新发现：无**。

### 最终门禁结论（绑定交付 SHA `f95037e5bbd37742175b52685ca833f91396e00c`）

- **(i) B 包门禁 = 通过，有非阻塞披露项。** 历轮 #1/#2/#3/#5/#6/#7、T10/T12 同事务代次守卫、b37、三处共享接缝解决、两处设计取舍、B 测试自清、APP 耗尽 BLOCKER 全部闭合；R6 无新发现。
- **(ii) 整体集成就绪 = 尚未就绪。** 仍需集成方完成：#4 将可重入扫描器接入既有 Worker 周期循环并按真实运行形态验证；#8 A 登出失效递增 `destination_revision`；冻结 C25（APP 观察流持久化协议）与 C26（generation 表容量告警 + 受控恢复 runbook）；对已合入的 C/D 业务代码在最终 SHA 上执行独立跨包验收。C23 的过时 javadoc/死代码与两份交付报告不阻塞 B 代码门禁。

## 10. 集成与复跑方式（给总协调与 E）

```bash
# 前置：docker、mvn(Java 21)、backend/worker-python/.venv、backend/contracts/.venv
docker start mvp-b-pg                                   # postgres:16 @127.0.0.1:55435（保留卷，勿 rm -v）
cd backend/web-java && env MVP_A_PG_JDBC=jdbc:postgresql://127.0.0.1:55435/postgres \
  MVP_A_PG_USER=postgres MVP_A_PG_PASSWORD=mvp_b_local mvn -B test          # 期望 198/0/0/0
cd backend/worker-python && env MVP_A_PG_DSN=postgresql://postgres:***@127.0.0.1:55435/postgres \
  MVP_A_PG_HOST_PORT=55435 MVP_A_PG_USER=postgres MVP_A_PG_PASSWORD=*** MVP_A_PG_CONTAINER=mvp-b-pg \
  .venv/bin/python -m pytest -q                                             # 期望 84 passed + 1 已披露 A 环境耦合断言
bash backend/tests/run-acceptance-b.sh                                       # 期望 ALL PASS 39/39, SCRIPT_RC=0
cd backend/worker-python && env MVP_WORKER_PG_DSN=postgresql://postgres:***@127.0.0.1:55435/mvp_b_dev \
  .venv/bin/python -m mvp_worker.scanners --once                             # 扫描器单轮；周期接入见下方注意
```

- 严禁 5432（共享 pgvector18）、55432(A)、55436+18085(C)、18080-18082(A/E)；B 活体端口 web **18083**、worker **18084**；`curl` 一律 `--noproxy '*'`。
- 跑 Java 测试**不要**设置 `APP_STORAGE_DEV_DIR`（A 的 `MediaFoundationIT` 硬编码探测 `/tmp/mvp-a-test-storage`，覆盖即假失败）。
- **集成必办事项**：
  1. 按 `.coordination/B-work/scanner-integration.md` 在既有 Worker 进程内接入 `run_once` 周期调用，并实际验证离线检测（第 6 节第 6 项，Oracle BLOCKER #4，未闭合）；
  2. `openapi.yaml` 的 8 行改动可能与 C/D 的契约改动相邻冲突，冲突时保留各方新增错误码即可；
  3. 请 A 归属方处理 `invalidateDestinations` 递增 `destination_revision`（第 6 节第 8 项）与 `test_sanity` 环境耦合断言（第 7 项）；
  4. 待裁定/追认项（C9 人脸身份引用端口、C14 三处 A 归属测试适配、C15 环境耦合断言）不阻塞集成，但需在 E 验收前明确归属。

## 11. Swagger / springdoc 文档接入（总协调授权项，提交 `8127be5`）

**目标与边界**：接入兼容 Spring Boot 3.5.16 的 springdoc，从**实际 Controller/DTO 生成** `/v3/api-docs` 与 Swagger UI（**不是渲染既有手写 YAML**）；**仅开发配置启用**；**不改变任何业务权限、不返回假 200**；范围经总协调收敛为"代码生成 + 路由可浏览"，**不扩展 C/D DTO 重构、不唤醒已关闭包**。

- **变更面仅 7 个文件**：`web-java/pom.xml`（新增属性 `springdoc.version=2.8.17` + 唯一新依赖 `springdoc-openapi-starter-webmvc-ui`；实际解析 webmvc-ui/api/common 2.8.17、`swagger-core-jakarta` 2.2.47、webjars `swagger-ui` 5.32.2）、`src/main/resources/application.yml`（基础段默认 `false`，dev/test 覆盖 `true`，prod 显式 `false`）、新增 `web/docs/OpenApiDocsConfig.java`、`web/docs/DocsProductionGuard.java`、新增测试 `OpenApiDocsIT`/`OpenApiDocsDisabledIT`/`DocsProductionGuardTest`。**未改任何 A/C/D 归属文件、未改 `contracts/**`、未改 `backend/tests/**`、未改迁移/deploy。**
- **鉴权零改动（取证而非假设）**：`web/auth/BearerAuthFilter.java:68` 为 `if (!path.startsWith("/api/") || PUBLIC.contains(...))`，只保护 `/api/**`；`/v3/api-docs` 与 `/swagger-ui/**` 均不以 `/api/` 开头，天然开放（与既有 actuator 一致）。故**无需也未做任何 auth 放行改动**。
- **生产 fail-closed 三道**：① `application.yml` 基础段默认关闭（prod 再显式关闭）；② `OpenApiDocsConfig` 用 `@Profile({"dev","test"})` + `@ConditionalOnProperty(springdoc.api-docs.enabled=true)`，生产不注册文档 bean；③ `DocsProductionGuard`（`@ConditionalOnProperty(app.env=production)` 的 `SmartInitializingSingleton`）在 springdoc 任一开关为 true 时抛 `production fail-closed` 拒绝启动。**未修改 A 的 `ProductionFailClosedValidator`。**
  - 如实区分：生产强行启用的实测日志中**先触发的是 A 的 `ProductionFailClosedValidator`**（该次启动使用 doubles 提供方），`DocsProductionGuard` 自身路径由 `DocsProductionGuardTest` 4 例（`ApplicationContextRunner` 隔离）证明，两者不可混为一谈。
- **生成性证明**：生成文档为 `openapi: 3.1.0`、`info.title` 标注"由实际 Controller/DTO 生成"、含 **20 个由真实 DTO record 推导的 `components.schemas`**（`AppSessionRequestBody`/`BindingBody`/`CaptureDto`/`ExecutionObservationDto`…）；对照手写契约 `backend/contracts/openapi/openapi.yaml` 为 `openapi: 3.0.3` 且标题不同 ⇒ 两者非同一来源，**未把契约 YAML 当作文档来源**。
- **鉴权/幂等说明集中在 docs 配置**：`OpenApiCustomizer` 在生成后补 `bearerAuth`(http/bearer) + 全局 `security`，并把**恰好 4 个公开认证端点**（`POST /api/v1/auth/sms-challenges`、`/auth/sessions`、`/auth/session-refreshes`、`/gimbal-sessions`）置为 `security: []`，同时移除 principal 伪参数；`info.description` 集中说明统一信封 `{requestId,data}`/`{requestId,error}`、`X-Request-Id`、`Idempotency-Key` 幂等语义与自由结构限制。**未逐端点大改业务代码。**

### 11.1 验证（orchestrator 亲自执行）

| 项 | 结果 |
|---|---|
| Java 全量 `mvn -B test` | **394 / 0 failures / 0 errors / 0 skipped，BUILD SUCCESS，rc=0**（基线 386 + 新增 8 项 docs 测试；未设置 `APP_STORAGE_DEV_DIR`） |
| 启用态（dev、**18083**、DB `mvp_b_dev`） | `/v3/api-docs` **200** application/json 25222B；`/swagger-ui/index.html` **200**；`/swagger-ui/` **200**（内部 forward） |
| 关闭态（`SPRINGDOC_API_DOCS_ENABLED=false`） | `/v3/api-docs` **404**、`/swagger-ui/index.html` **404** |
| 生产强行启用 | 进程 **exit 1**，拒绝启动 |
| **27/27 业务 API 可见** | 期望集合由 orchestrator 独立从契约 **27 个 `x-api-id`** 提取（M1×3/M2×8/M3×6/M4×9/M5×1），用自有校验器 `verify_swagger27.py`（已自测归一化/缺失/非法输入三情形）比对实抓 `/v3/api-docs` → **hit 27/27、missing=[]、rc=0**；总协调独立实测 **33 paths / 34 operations** 与此吻合 |
| 额外真实端点（如实暴露未隐藏） | A 的 4 个认证端点（含 `DELETE /api/v1/auth/sessions/current`）、`GET /api/v1/media/{mediaId}/content`、`POST`+`GET /api/v1/system/echo-jobs`，共 7 条 |
| security 结构 | `securitySchemes={bearerAuth:(http,bearer)}`、全局 `security=[{bearerAuth:[]}]`、**恰 4 个** operation 带显式 `security: []` 覆盖 = 4 个公开端点 |
| 提交卫生 | 暂存集恰 7 文件、**0 工件、0 运行文件、0 越界**；工作树 clean |
| 资源纪律 | 未新建 PG 容器、未触碰总协调的 **18080 预览**与 `swagger_preview` 库、未停 PG、验证后无遗留 JVM |

### 11.2 给总协调的预览启动方式（B 侧验证用 18083；用户预览的 18080 由总协调唯一负责）

```bash
# 安全配置文件（chmod 600，目录 700；内含本地测试占位凭据，勿外泄）：
#   .coordination/B-work/swagger-preview/swagger-preview.env
set -a; source .coordination/B-work/swagger-preview/swagger-preview.env; set +a
export SERVER_PORT=18083 SERVER_ADDRESS=127.0.0.1     # B 侧验证端口；总协调预览用 18080
nohup java -Xmx384m -XX:MaxMetaspaceSize=192m \
  -jar backend/web-java/target/web-java-0.0.1-SNAPSHOT.jar \
  > .coordination/B-work/swagger-preview/app.log 2>&1 &
echo $! > .coordination/B-work/swagger-preview/app.pid
# 页面：http://127.0.0.1:18083/swagger-ui/index.html   （总协调预览：…:18080/…）
# 文档：http://127.0.0.1:18083/v3/api-docs
kill $(cat .coordination/B-work/swagger-preview/app.pid)   # 验证后请停止，勿长期常驻（宿主内存紧张）
```

### 11.3 文档字段级尚缺（如实声明，本轮按裁定不修）

`Object`/`Map` 自由结构（多为 JSONB）在 Swagger 中只显示 `object`，**不能展开为字段级 schema**；`info.description` 已集中声明该限制并指明**字段级权威仍是 `backend/contracts/openapi/openapi.yaml`**。逐处清单与最小补注解建议见 `.coordination/B-work/swagger-doc-gaps.md`：

- **A 归属**：`web/web/SuccessEnvelope.java:11` `Object data`、`web/web/ErrorEnvelope.java:17` `Map details`
- **B 归属（可后续自行最小补注解）**：`devices/DeviceDtos.java:38` incidents、`:61` capabilities、`:67` state、`:74` `CapabilitiesView.capabilities`；`notifications/NotificationDestinationDtos.java:32` registration
- **C 归属**：`care/CareProjections.java:52` `planSummary`、`:56` `plan`
- **D 归属**：`assessments/dto/SkinReportListItem.java:9` `reportSummary`、`SkinReportView.java:21` `metrics`
- **M1-A01** 的 multipart `metadata` 部件为严格 JSON（手工解析为 `CreateMetadata`），非 DTO，故无法自动派生字段级 schema
- 其他差异：生成 `openapi 3.1.0` vs 契约 `3.0.3`；response content-type 为 `*/*`；`operationId` 由 springdoc 按方法名派生（`create`/`create_1`…）**未对齐契约 operationId**；错误码未逐端点附着（仅 info 文字说明）

> 措辞纪律：本文档**不宣称**字段级完备，也**不描述**为"渲染旧手写 YAML"。Swagger 的价值在于**由实际代码生成、路由可浏览、鉴权与幂等语义集中说明**；契约一致性仍由 `backend/contracts` 的四项校验与验收 b14（37 条错误信封观测 / 12 端点白名单）保障。

### 11.4 Oracle 有界复审结论与整改（**提交 `8127be5` 判 FAIL，整改中**）

**重要更正**：上文 11.1 的验证数字（394/0/0、27/27、启用 200 / 关闭 404 / 生产拒绝启动）均为**真实且已亲自复核**，但 Oracle 对该提交做了**有界复审**（只审 `f95037e..8127be5` 的 7 个文件，不重审已通过的业务代码），结论为 **`VERDICT: FAIL`**，并明确"**合入 dev / 替换用户预览前必须先修**"。故 `8127be5` **不是** Swagger 的最终交付 SHA。

- **8 项裁定中 6 项通过**：①确为代码生成而非渲染手写 YAML（生产代码未读取 `openapi.yaml`，仅测试读它构造期望集合）；③业务权限零变化（未改任何 auth 文件；公开端点清单与 `BearerAuthFilter` 四项一致；全局 bearer + 4 个 `security: []` 不误导；principal 删除只改 OpenAPI 模型不改请求解析/授权；未发现 actuator/SQL/配置值/堆栈/媒体内容泄漏）；④无假业务 200、无业务路由变化（唯一新增路由是 `/swagger-ui/` 内部 forward，且仅在文档 bean 启用时存在，不掩盖业务 404）；⑤27/27 证据可信（method 与归一化 path 联合作 key，**不会用路径归一化掩盖 method 错误**；期望集合固定断言 27；27+7=34 operations / 33 paths 与总协调独立实测一致）；⑥范围合规（`8127be5` 恰改 7 个授权文件；未改 auth/`web/error`/`care`/`assessments`/契约/迁移/deploy/`backend/tests`；未重构 C/D DTO）；⑦依赖风险可接受（属性锁定 2.8.17；官方 2.8.17 基于 Boot 3.5.13、同线兼容 3.5.16；未发现其修改全局 `ObjectMapper`/异常处理/业务 `HandlerMapping`；394 项回归为合理证据；建议纳入依赖漏洞监控）。
- **BLOCKER（必须修，整改中）**：`DocsProductionGuard.java:22-24` 的生产判定**只依赖 `app.env=production`**。当 **`prod` profile + `app.env=dev`（矛盾配置）+ 强制打开 springdoc 开关**时：`OpenApiDocsConfig` 因 `@Profile({"dev","test"})` 不注册、护栏因条件不满足也不注册，而 **springdoc starter 自身的自动配置仍会暴露 `/v3/api-docs` 与 `/swagger-ui/index.html`**；此场景下 A 的 `ProductionFailClosedValidator` 同样按 `app.env` 判定故也不触发 ⇒ **无任何东西拦住**，违反"生产 fail-closed"的授权条件。orchestrator 已独立核实该缺口成立且非理论问题（不得依赖 A 的校验器"偶然先失败"）。修法：护栏**始终注册**，运行时以"active profile 含 `prod` **或** `app.env=production`"为生产判据，任一生产信号成立且文档开启即拒绝启动，并补矛盾配置测试。
- **IMPORTANT（必须修，整改中）**：`OpenApiDocsConfig.java:86-94` 的"尚未字段级展开"清单**不完整**（遗漏 `SuccessEnvelope.data`、`ErrorEnvelope.details`、heartbeat `incidents`、微晶 `capabilities`/`state`、通知 `registration`）。修法：改为**统一声明**"所有 Java 侧声明为 `Object`/`Map`/`JsonNode` 的字段都可能只显示为自由结构 object"+ 典型字段列举，**不重构 DTO**。
- **测试充分性部分不通过**：`DocsProductionGuardTest` 只测 `app.env`，未覆盖 `prod profile + app.env!=production` 的矛盾组合，故漏掉上述绕过；修复后须补该组合测试与 `app.env=production + dev profile` 的明确回归。
- **Oracle 要求持续披露的文档准确性限制**（除 11.3 外补充）：全局 bearer 只表达"是否需要 token"，**不表达 APP/GIMBAL 主体类型、成员授权、当前任务等细粒度权限**；字段与错误码冲突时**以 `backend/contracts/openapi/openapi.yaml` 为准**；Swagger UI **只能在 dev/test 暴露，不得用于公网生产**。
- **整改后的最终 Swagger SHA = `d3dc853d7ec55ff0fad661a45943e7b60ff12325`**（`fix(B): 闭合 Swagger 生产 fail-closed 绕过（Oracle BLOCKER）并补全自由结构声明`，仅 4 个文件：`DocsProductionGuard`、`OpenApiDocsConfig`、`application.yml`、`DocsProductionGuardTest`；**`pom.xml` 未改**）。Oracle 有界复审判 **`PASS-with-notes`**：BLOCKER 与 IMPORTANT **均已闭合**，7 项护栏测试为有效状态断言、无放宽，并明确 **"可以将 `d3dc853` 合入 dev 并替换开发预览"**。
- **BLOCKER 闭合方式**：护栏改为**无条件注册**（仅 `@Component`），在 `SmartInitializingSingleton.afterSingletonsInstantiated()` 运行时判定——生产信号 = `acceptsProfiles(Profiles.of("prod"))` **或** 规范化后 `app.env=production`（忽略大小写与首尾空白）；文档开启判定按**保守缺省**（未显式 `false` 即视为开启，对齐 springdoc `matchIfMissing=true`），两个开关分别检查；任一生产信号 + 任一开关开启 → 抛 `IllegalStateException`（含 `production fail-closed` + 命中信号 + 开关名，不含密钥）。该时机在嵌入式 Tomcat `start()` 之前 ⇒ **端口从未绑定**；护栏**独立于 A 的 `ProductionFailClosedValidator`、也独立于文档 bean 是否注册**，故覆盖 springdoc starter 自身自动配置。
- **端到端拦截证据**（`.coordination/B-work/swagger-preview/prod-profile-bypass-attempt.log`）：以 `--spring.profiles.active=prod,dev --app.env=dev --springdoc.api-docs.enabled=true --app.providers.mode=doubles` 启动 jar（用 `prod,dev` 使 dev 替身 bean 齐备，从而避开 A 校验器与缺 bean 干扰）→ `JAVA_EXIT=1`，日志含 `production fail-closed … active-profile-prod=true, app.env=dev; enabled switches: [springdoc.api-docs.enabled]`，`Tomcat started on port` 出现 **0 次**。
- **整改后验证（orchestrator 亲自执行）**：Java 全量 **`Tests run: 397, Failures: 0, Errors: 0, Skipped: 0`，BUILD SUCCESS，rc=0**（基线 394 + 新增 3；`OpenApiDocsIT` 3/3、`OpenApiDocsDisabledIT` 1/1、护栏 7/7）；启用态（dev、18083、`mvp_b_dev`）`/v3/api-docs` 200、`/swagger-ui/index.html` 200、`/swagger-ui/` 200，独立校验器复跑 **hit 27/27、missing=[]、rc=0**（`securitySchemes=bearerAuth(http/bearer)`、恰 4 个公开端点 `security: []`）；关闭态两端点均 **404**；BLOCKER 场景 **exit 1 且端口未绑定**。
- **Oracle 的 2 条 SUGGESTION（非阻塞，本轮按文档化披露处置，未改代码以免使已批准的 SHA 失效）**：
  1. `DocsProductionGuard.java:49` 只识别正式 profile 名 `prod`，不识别常见别名 `production`；复现需 `spring.profiles.active=production` + `app.env=dev` + 显式强开 springdoc 开关。**项目正式 profile 约定为 `prod`**（见 `application.yml`），且基础段默认关闭、`OpenApiDocsConfig` 仅 dev/test 注册，故残余风险低。后续可选修法：改为 `Profiles.of("prod","production")`，或在部署文档明确只允许 `prod`。
  2. `DocsProductionGuard.java:17` 的 javadoc 仍链接已删除 import 的 `@ConditionalOnProperty`，且"无条件 ConditionalOnProperty"表述含混；建议改为"无 `@ConditionalOnProperty` 条件"并去掉未解析链接。
- **必须持续披露的文档准确性限制**（Oracle 本轮重申，已写入 `info.description`）：生成文档非权威契约、冲突以 `backend/contracts/openapi/openapi.yaml` 为准；生成 OpenAPI **3.1.0** vs 契约 **3.0.3**；所有 `Object`/`Map`/`JsonNode` 字段可能只显示自由 object；response content type 可能为 `*/*`；`operationId` 由 Java 方法名派生、未对齐契约；未逐端点附着完整错误码集合；**全局 bearer 只表达"是否需要 token"，不表达 APP/GIMBAL 主体类型、成员查看授权、绑定或当前任务等细粒度权限**；**Swagger UI 仅限 dev/test，不得作为公网生产文档面**；正式生产 profile 名为 `prod`，若将来支持 `production` 别名须同步扩展护栏。

## 12. 公共集成修复轮（总协调指定 B 为唯一实施负责人，最终代码 SHA `2d6c7231f2d2aa58ec0501e8550a0f35b8bd2533`）

**授权范围**：用户授权重启后继续集成测试、**不启动 Swagger 预览**；总协调扩展范围，指定 B 为本轮公共集成修复唯一实施负责人（不恢复 A/C/D 会话），复用 mvp-b 工作树与本会话；允许最小 runtime/config/deploy 说明与最小 auth 公共修改；**不得修改验收驱动放宽校验**；候选提交后由**实际 Oracle 有界审最终 SHA**；总协调合 dev、E 独立验收；B **不自行推送/归档/合入 dev**。

**基线合并**：安全合入总协调指定的本地 dev 基线 `f045433`（"Merge reviewed Swagger integration into dev"）→ 合并提交 **`39adc57c290e6cef4af336935ee7112f34bdca0b`**（parents = `551f166` + `f045433`）。合并前以 `git merge-tree --write-tree` 预演：**退出码 0、冲突 0**；传入基线**不触及**本轮三个目标写域，实质为 E 的独立验收资产（115 份 evidence + driver/matrix/run.sh/requirements/config）与 4 份 E 交付文档。合并后树 clean、`git grep` 零冲突标记。**只把基线合入本 feature，未反向合并、未推送。**

**本轮提交链**：`39adc57`(merge) → `2bd768a`(契约 13 处) → `d0e9b84`(登出代次) → `2d6c723`(Worker 有界周期调度)；合计 **10 个文件、0 工件、0 个 E 资产文件**。

### 12.1 项 1：扫描器接入既有 Worker 的有界周期调度（`2d6c723`）

闭合 Oracle BLOCKER **#4**（"扫描器未接入既有 Worker，手动 CLI 不等于生产接入"）与 C8 裁定（MVP 用既有 Python Worker **进程内周期触发**，不加常驻进程/cron/部署调度）。

- **调度**（新增 `scanners/scheduler.py`，**不新增进程/线程/队列**）：`PeriodicTask` 以 `time.monotonic` 维护 `due_at`，并用 `threading.Lock` 的**非阻塞 acquire** 作重入守卫（上一轮未结束则本轮跳过并顺延，绝不叠加并发）；`PeriodicScheduler.run_due()` 只运行到期任务；`next_wait_seconds(max_wait)=min(最近到期, max_wait)`；`build_worker_scanner()` 装配两个任务（B incident、D `media.cleanup` 候选发现），各自独立间隔与批量上限。
- **挂载点**：`runtime/loop.py` 新增 `_scanner_or_build()`（`:60`）；`run_forever` 在每轮 `run_cycle()` 之后调用 `scanner.run_due()`（`:242`），空闲等待改为 `stop_event.wait(scanner.next_wait_seconds(poll_interval_seconds))`（`:247-248`）⇒ 批处理间隙、同线程、到期才跑、异常自隔离，且 `stop_event` 仍能及时停机。**`process_job`/`run_cycle` 未改。**
- **有界性**：`incident_scanner.py` 新增 `ScanCursors`（offline/recovery/notify 三段各自独立游标），`run_once(engine, settings, *, limit=None, cursors=None)`；三个候选 SQL 加 `AND (CAST(:after_id AS uuid) IS NULL OR id > CAST(:after_id AS uuid)) ORDER BY id LIMIT :limit`；`_page_rows` 取满则推进到最后 id、取不满则归零下轮从头 ⇒ **单轮每阶段 ≤limit 行且不重扫前缀**。`ScanReport` 仅**追加** `scan_limit`，既有字段全保留；`--once`/`--loop` 退出码语义不变（`--loop` 跨轮持游标），新增 `--limit`。
- **D 的代码未改**：`handlers/media_cleanup.py` 的 `_SELECT_ORPHAN_CANDIDATES` 原本已带 `ORDER BY created_at, id LIMIT :limit`，故仅由调度器透传 `limit`（该文件 diff 为空）。
- **红线保持**：`runtime/claim.py`/`complete.py`/`renew.py`/`expire.py`/`rows.py` 与 `handlers/__init__.py` 的 **diff 为空** ⇒ 租约（`lease_owner`/`lease_revision`/租约时钟）与 `business_tx` 同事务收敛机制原样；扫描回调只做 DB（单表 SELECT/UPDATE + `INSERT…ON CONFLICT` + `enqueue_job`），真正的存储删除仍在 D 的 `fenced_business_tx` **之外**由后续 job 锁外执行 ⇒ **网络不在 PG 锁内**；**C7 红线**：离线扫描**绝不写** `gimbals.last_seen_at`（只读用于判定，有 SQL 级断言测试）；多实例安全**不引入新锁**，依赖既有 `FOR UPDATE`+`status_revision`、`uq_notification_dedup`/`uq_job_dedup`、D 的 `media:{id}:cleanup:1` dedup。
- **配置**（`config.py` 新增 4 个旋钮，env 可覆盖，dev 联调起点）：`MVP_WORKER_INCIDENT_SCAN_INTERVAL_SECONDS`（未设时回退 B 既有 `MVP_NOTIFY_SCAN_INTERVAL_SECONDS`，再回退 30）/ `MVP_WORKER_INCIDENT_SCAN_BATCH=200` / `MVP_WORKER_MEDIA_CLEANUP_SCAN_INTERVAL_SECONDS=30` / `MVP_WORKER_MEDIA_CLEANUP_SCAN_BATCH=100`；`backend/deploy/README.md` 最小补充 4 行；`.coordination/B-work/scanner-integration.md` 已重写为与实现一致。
- **测试**：新增 `tests/test_scanner_scheduler.py` 8 项（到期才触发/未到期不触发；等待窗口=min(poll,到期)；上一轮在跑时不叠加；两任务独立间隔与批量；`run_forever` 在 `stop_event` 后 <3s 退出；`limit=2` 时 5 行分 3 轮推进且游标取满推进/到尾归零、`limit=None` 向后兼容；离线扫描前后 `last_seen_at` SQL 级相等且状态转 offline；D 发现单轮 ≤limit 且二次幂等为 0）。**未放宽或删除任何既有断言**，D 的 `tests/test_media_cleanup.py` 全绿。

### 12.2 项 2：登出失效通知目标时同事务递增 `destination_revision`（`d0e9b84`）

闭合 Oracle **#8**（原属 A 归属待修；B 侧投递安全此前靠"探针要求 `status='active'`"闭合，但代次语义不完整，存在旧任务写回风险）。

- **修法**（`web/auth/AuthController.java` 的 `invalidateDestinations`）：在**同一条原子 UPDATE** 内完成 `status='invalid'` + `invalidated_at`/`updated_at` + **`destination_revision = destination_revision + 1`**，`WHERE session_ref=? AND status='active'` 守卫不变 ⇒ 不存在"已失效但代次未变"的可观测中间态。
- **幂等与竞态**：`WHERE … AND status='active'` 只命中真实变更行；已 invalid 的行不重复递增、不刷新 `invalidated_at`；以**受影响行数**判定（`n=0` 即幂等无操作）；**单条语句、无 SELECT-then-UPDATE ⇒ 无 TOCTOU**。
- **HTTP 行为未变**：登出仍 `ResponseEntity.noContent()` → **204 无体**（响应构造未改）；T09 更新失败仍不反转登出（保留"撤销已生效、目标失效可补偿"，DD 4.1）；warn 日志**不再回显 `session_ref` 明文**，改用 `installationId`。
- **一致性边界（如实，不夸大）**：控制器无 `@Transactional`（auth 包内无任何事务注解），`JdbcTemplate.update` 走连接池 autocommit ⇒ 该 UPDATE 是**单条语句、单一事务**；但会话撤销发生在 `SessionProvider`（dev/test 为内存 double，14 表设计无 session 表）、**不在 DB 事务内**，故**不能**声称"与撤销同一事务"——能达到的最强边界即 T09 侧"失效+代次递增"原子。
- **未削弱既有代次语义**：`NotificationDestinationService` 的"仅同会话且已 active 的纯幂等重登记不递增、`session_ref` 变化或 invalid 重新激活一律 +1 且带 `WHERE id=? AND destination_revision=?` 守卫"仍成立；**Python 侧无需改动**（既有 T03→T09→T10 投递前重检会因代次失配判 `destination_changed`/`route_recheck_failed`，与"探针要求 active"形成双重防护）。不改表结构、不加列、不加迁移。
- **测试**：新增 B 自有 `LogoutDestinationRevisionIT` 4 项（恰好 +1 且 204 空体；重复登出幂等含影响 0 行；旧 T10 写回被守卫拦为 **0 行**且通知仍 pending；登出后重新登记代次继续递增）。**未修改任何既有断言。**

### 12.3 项 3：修正 CC-11 的 13 处 OpenAPI 建模缺陷（`2bd768a`）

E 的独立验收以**严格 OAS 3.0.3 语义**校验 9 个 M4 成功响应，发现 **13 个不同字段路径**的契约建模缺陷（归属 `openapi.yaml`，**非 C 运行时缺陷**）：12 处 `nullable:true` 与 `$ref`/`allOf` **同层**（OAS 3.0.3 下不生效——`nullable` 必须与 `type` 同一 schema 对象），致 C 按契约意图返回 `null` 被判 `type` 违规；1 处 `ProgressWithSync` 经 `allOf` 叠加 `lastSyncedAt`，被 `Progress.additionalProperties:false` 误伤（`allOf` 某分支看不到其他分支的 properties）。

- **12 处 nullable**：改为**与 `type` 同对象**的内联可空标量 —— `Progress.completedAt`、`Verification.validUntil`、`ControllerRef.gimbalId`、`CareExecutionListItem.closedAt` → `{type: string, format: date-time|uuid, nullable: true}`，覆盖 A01/A02/A03/A04/A05/A07/A08/A09 的 12 个字段路径。选择**就地内联**而非新增公共 schema：各字段仅出现一次、无复用需求，可把 diff 严格限制在 5 个授权组件内。
- **第 13 处 A08 `$.data`**：`ProgressWithSync` 由 `allOf:[Progress,{lastSyncedAt}]` **展平为显式单 schema**（7 属性 = `Progress` 的 6 个 + `lastSyncedAt`），保留 `required:[completedCount,remainingCount,progressRevision]` 与 `additionalProperties:false` ⇒ **允许字段集合与严格性均不变**（第 8 个未知字段仍被拒）。**未**采用"去掉 `Progress.additionalProperties:false`"（那会放宽 A01/02/03/04/05/07）。
- **不变量（已逐项核实）**：未增删任何业务字段、未改 `required` 集合、未改 `format`/`enum`/`pattern`/`minimum` 等约束、未改任何端点的状态码集合/`x-error-codes`/`operationId`/`x-api-id`；A01..A09 的响应引用链未被触碰。**属性集精确比对**：`Progress`/`ControllerRef`/`Verification`/`CareExecutionListItem` 的 properties 名称集合 PRE=POST **完全一致**；`ProgressWithSync` 由 allOf 形式（无自有 properties）→ 显式 7 属性。
- **未修改 E 的任何验收资产**：`git status`/`git diff` 对 `backend/acceptance/**` **为空**（含 `driver/c_care.py` 与 `tests/test_framework_selfcheck.py`）。

### 12.4 验证（orchestrator 亲自执行，绑定最终 SHA `2d6c7231`）

| 项 | 结果 |
|---|---|
| Java 全量 `mvn -B test`（限堆 `-Xmx768m`、`MVP_A_PG_JDBC=…55435/postgres`、未设 `APP_STORAGE_DEV_DIR`） | **Tests run: 401, Failures: 0, Errors: 0, Skipped: 0；BUILD SUCCESS；rc=0**（基线 397 + 新增 4；`LogoutDestinationRevisionIT` 4/4、`NotificationDestinationsIT` 11/11） |
| Python 全量 `pytest -q`（真实 PG 55435） | **230 passed / 0 failed / 0 errors；rc=0**（基线 222 + 新增 8） |
| `python -m mvp_worker.scanners --once` | **rc=0**，报告含新增 `"scan_limit":200` |
| 契约四项（`backend/contracts/.venv`） | `openapi-spec-validator` **VALID** rc=0；`validate_responses.py --selftest` **10 passed/0 failed** rc=0（含 4 项 nullable-shape 判别）；`validate_samples.py` **50 checks/0 failed** rc=0（**未改 samples**）；`jcs.py selftest` **PASS（26 checks, 23 number pairs）** rc=0；**修复前后数字一致 ⇒ 无校验被削弱** |
| 契约定向严格校验（自建只读脚本，独立实现严格 OAS 3.0.3 语义：`nullable` 仅在与 `type` 同对象时生效、`allOf` 不展平；**未 import/未改 E 驱动**） | 对**修复前** YAML `--expect-defects` → **14/14 复现缺陷**（12 `type` + 2 处 A08 `additionalProperties`）；对**修复后** YAML → **14/14 全过** ⇒ **双向判别力成立、非恒真** |
| **端到端验收 `backend/tests/run-acceptance-b.sh`** | **ALL PASS 39/39，`SCRIPT_RC=0`**（含 b26 C7 `last_seen_at` 不变、b27 扫描→通知→真实 worker、b30–b35 投递链、b36 Java 全量、b37 Python 全量、b39 HEAD 与 tracked 文件未变、b14 契约驱动 37 条错误信封/12 端点白名单） |
| 写域与纪律 | 本轮 10 个文件全在授权写域；`backend/acceptance/**` 零改动；0 工件；未触碰 18080/E 的端口与 `.worktrees/mvp-e`；未改/未重置 `swagger_preview`；未停 PG；无遗留 JVM；运行文件在 `.coordination/B-work/integration-fix/`（未用 /tmp） |

### 12.5 本轮新增/延续的待协调项（B 未自行扩大范围，均如实披露）

1. **E 的自检断言将失败，需由 E 自行更新**（B 未改 E 任何文件）：`backend/acceptance/tests/test_framework_selfcheck.py:958` 的 `assert errs_clean` 断言 A08 仍存在 `additionalProperties` 缺陷 ⇒ 修复后**必然失败**；`c_care.py:996` 的 `assert len(CC11_CONTRACT_ALLOWLIST)==13` 仍通过但 allowlist 已陈旧；修复后 CC-11 的契约缺陷计数应为 **0**、`impl_bad` 仍为空，状态由 INFO 转 PASS。
2. **32 处 off-path `allOf+nullable` 旧式写法**（如 `ExecutionClosureResult.closedAt`、`CareExecutionView.closedAt`、`ProgressWithSync.targetCount`）不在 E 的 13 处清单内、未被任何验收观测命中，本轮**只报告不修改**（依据 `contracts/decisions-notes.md` 已记录的"遗留跟随项"）。故 **A08 若返回 `targetCount=null`，严格语义下仍会被拒** —— 属既有遗留，需后续授权统一修订。
3. **D 的候选发现有 `LIMIT` 但无 keyset**：头部 `limit` 个候选若长期被安全跳过（被引用或处理者租约活跃），其后可清理候选会延迟。改 keyset 需动 D 文件，故未做；可选方案 A=给 `discover_and_enqueue_orphans` 加可选 `after` 游标，方案 B=维持现状 + 运维调大 batch。
4. **`gimbals.active_incidents` 保留已 resolved episode** ⇒ recovery/notify 候选集不随事件关闭收缩；keyset 保证每轮有界推进，但彻底消除需专用索引/标记列（**需迁移**，属集成方裁定）。
5. **`worker-python/tests/conftest.py` 只读 `MVP_A_PG_*`**（默认指向被禁用的 55432）⇒ 仅给 `MVP_WORKER_PG_DSN` 时 pytest **无法收集用例**；正确调用须补 `MVP_A_PG_DSN`/`MVP_A_PG_HOST_PORT`/`MVP_A_PG_USER`/`MVP_A_PG_PASSWORD`/`MVP_A_PG_CONTAINER=mvp-b-pg`。该文件属共享测试基础设施，B 未擅自改，提请裁定归属。
6. **`NotificationDestinationService` 类注释**中"若登出侧 invalid 失效不改代次…"一句现已不成立（登出会 +1），但**行为不受影响**；因写域限制未改注释，建议总协调统一措辞。
7. **C25**（延续）：APP 须跨登录/refresh/重启**持久化** `observationEpoch` 与每微晶单调 `observationSeq`，否则该次观察被 `accepted=false`；若产品要求"重启后 seq 可从 1 开始"，须改用方向②（由 B 自有 `ConnectionProofVerifier` 从已验证的 connectionProof 返回单调可信 generation）。**本轮未改任何业务规则。**
8. **C26**（延续）：`app.devices.max-observation-sessions` 默认 8，生产初值建议 32~64；需配置 `branch=session-table-full-fail-closed` 告警与凭据轮换/受控重置 runbook；**APP 侧无自动恢复途径**，且"仅调高上限不是恢复机制"。

### 12.6 Oracle 有界复审结论（绑定 `2d6c7231f2d2aa58ec0501e8550a0f35b8bd2533`）

**`VERDICT: PASS-with-notes`** —— 三项授权目标**均已正确实现、无代码级 blocker**，Oracle 明确 **"可以合入 dev"**。范围限定本轮三项 + 基线合并，未重审 R6 已通过的 B 业务代码与 R8 已通过的 Swagger。完整记录（19 点逐条裁定 + 依据行号 + Oracle 实际核查命令）见 `B-oracle.md` §4.13。

- **关键红线经 Oracle 独立确认**：`process_job`/`run_cycle` 与 `claim`/`complete`/`renew`/`expire`/`rows`、handler 注册表**零 diff**（租约与失败事务守卫原样）；网络仍在锁外（真正存储删除在 `media_cleanup.py:216-222` 的业务事务外）；**C7 红线保持**（扫描器只读 `last_seen_at`、UPDATE 不含该列）；停机不被扫描间隔阻塞；`ProgressWithSync` 展平后**严格性保持**（七属性 + 原 `required` + `additionalProperties:false`）；`backend/acceptance/**` 与 `backend/tests/**` **diff 为空**；登出的一致性边界**表述准确未夸大**（只声称 T09 侧同一原子 UPDATE，未声称与 `SessionProvider` 撤销同事务）。
- **新发现 1 IMPORTANT + 4 SUGGESTION，均非 blocker**。IMPORTANT：`incident_scanner.py:389-422` 的 `LIMIT` 只约束 **gimbal 候选数**，单 gimbal 的 `active episodes × active destinations` 扇出**无每轮总预算** ⇒ 单轮总事务/通知数并非严格有界；Oracle 判"**MVP 可暂按运营规模接受并监控**，后续增加每轮总工作预算或对 episode/destination 分页"。**本轮未修**，理由：需设计决策（预算口径或分页语义）属业务规则变更、超出本轮授权且风险不对等 ⇒ 如实披露并移交集成方。
- **合入附带条件（Oracle 原文）**：①合入后 **E 的一项旧缺陷自检会按预期失败**（`test_framework_selfcheck.py:958 assert errs_clean` 断言 A08 仍存在 `additionalProperties` 缺陷），E/集成方必须同步更新其期望并清理 `c_care.py:98-154` 的陈旧 allowlist，之后才能宣称整体验收全绿；②incident scanner 的总扇出不是绝对硬上限，应进入后续预算化治理。
- **对 12.5 待协调项的裁定**：D 候选发现无 keyset = **非阻塞但应修**（影响清理及时性，**不造成误删**；调 batch 不能根治永久头阻塞，归 D/集成方）；resolved episodes 长期保留 = **非阻塞 MVP 残留**（归集成/数据所有者设计压缩、索引或迁移）；`conftest.py` 只认 `MVP_A_PG_*` = **非生产阻塞、测试基础设施应修**（归共享基础设施所有者/A 或总协调）；`NotificationDestinationService` 旧注释 = **非阻塞文档修正**（归 B/集成方）；**C25/C26 = 维持非阻塞待冻结项**（归总协调与 APP/设备协议提供方）。

**纯注释后续提交 `c59a18bac95dae3e262f06d93993cee85b5a620b`**：据 4 条 SUGGESTION 中"注释与现状不符"的 3 条（其中 2 条 Oracle 判给 B）做了**纯注释/文档**更正——`scanners/__init__.py`（模块 docstring 与 `--loop` 帮助文本改为如实反映"周期触发已接入既有 Worker、CLI 仅供验证排障"）、`scheduler.py`（明确 **fixed-rate/best-effort** 语义：`due_at` 以尝试开始前的 `now` 顺延，回调超时则下轮立即到期，不补偿漂移也不跳过周期；采 Oracle 给的"明确说明"选项而非改行为）、`NotificationDestinationService.java`（类 javadoc 更正为当前 +1 语义）、`contracts/decisions-notes.md`（遗留旧式 nullable 计数 **36 → 32**，给出 `36−5+1` 沿革并同步增删清单条目）。**自证零行为变更**：Java 侧该 diff 的**非 javadoc 行数为 0**、Python 侧仅 docstring/注释/`help=` 文本、契约侧**只有 `decisions-notes.md`（`openapi.yaml` 未在 diff 中）**；相称验证为 `py_compile` OK、定向 pytest **13 passed rc=0**、`scanners --once` **rc=0**、`mvn -B -DskipTests compile` **rc=0**。

**重新绑定结论（`c59a18b`）：`PASS-with-notes`，且明确"可以将 `c59a18b` 合入 dev"、"不要求重跑端到端验收"**。Oracle 五点裁定：①确为文档性变更、无业务/调度语义变化（并诚实指出 docstring 与 `help=` 属运行时字符串、会改变 `__doc__`/`--help` 输出，但不影响参数解析、控制流、配置、退出码或扫描行为）；②三条注释类 SUGGESTION 中 `scanners/__init__.py` 与 `NotificationDestinationService.java` **已正确处置**；③**32 处计数准确**——Oracle 独立递归最终 `openapi.yaml` 命中**恰好 32** 个"`nullable=true`、无本地 `type`、含 `allOf/oneOf/anyOf`"节点，与 `decisions-notes.md:178-204` 的 32 项清单**逐项一致**，`36−5+1` 沿革成立、**无虚报或漏报**；④扇出 IMPORTANT 的"披露 + 移交集成方"处置**可接受**，不要求在合入 dev 前修复；⑤结论可原样重新绑定，定向编译/测试已足够，**无需再次执行完整 39 项端到端验收**（该证据绑定在 `2d6c723`）。Oracle 另提醒：12.5 的扇出披露当时仍是工作树未提交修改，**交付前必须经 report-only 提交纳入版本记录**（已照办）。

**注释精确化提交 `76a01f06a5ac015f243d277db66c99dea8a01004`**：Oracle 在 `c59a18b` 轮给出唯一一条新 SUGGESTION——`scheduler.py:57-61` 措辞不完全准确，实现实为"以上次尝试开始时间为基准的 **best-effort start-to-start** 调度"，回调耗时超过 `interval` 时**错过的多个周期会被合并**，而非原注释所写的"不跳过周期"。orchestrator 认为"事实性错误注释"正是本轮刚修掉的那类缺陷、不应自留，故**严格按 Oracle 给出的措辞**更正（删除不准确的 "fixed-rate"/"不跳过周期"，改为①超时后下一轮立即到期、不补偿漂移；②错过周期**合并为一次**执行、**不追赶补跑**，并附 interval=30s/回调 95s 的具体例子）。自证零行为变更：该 diff 中**非注释行数为 0**（全部以 `#` 开头）、`py_compile` OK、定向 `pytest tests/test_scanner_scheduler.py` **8 passed rc=0**。

**最终重绑定结论（`76a01f0`）：`PASS-with-notes`，新发现：无。** Oracle 明确 **"可以将 `76a01f06a5ac015f243d277db66c99dea8a01004` 作为本轮最终交付 SHA 合入 dev"**、**"不要求重跑端到端验收"**（差异仅为注释、执行语义完全未变），并给出**轮次边界声明**：`76a01f0` 为本轮最终交付 SHA，**无需再因纯注释/文档措辞发起新的重新绑定轮次**。三点裁定：①`c59a18b..76a01f0` 仅修改 `scheduler.py:57-63` 的 `#` 注释，未触及语句/签名/常量/控制流/配置/契约，`git diff --check` 通过；②新措辞与实现（`scheduler.py:66-78` 的 `due_at = now + interval` 使用尝试开始前的 `now`）**一致**，正确说明超时后立即到期、错过周期合并且不追赶补跑，30s 间隔/95s 回调的示例**准确**，非阻塞重入守卫与未来 fixed-delay 修法说明均保留；③原结论可**原样重新绑定**（代码门禁维持 PASS-with-notes、可合入 dev、不要求重跑端到端、E 仍需更新过时的 CC-11 selfcheck/allowlist）。Oracle 并指出：工作树中的 `B.md`/`B-oracle.md` 修改不属被审 SHA，应按既定 report-only 流程单独处理（即本提交）。

### 12.7 本轮最终交付 SHA 与持续披露的残留限制

**本轮最终交付 SHA = `76a01f06a5ac015f243d277db66c99dea8a01004`**（三项业务修复绑定在 `2d6c723`；Oracle 对该 SHA 与其后两个纯注释提交共三轮均判 **PASS-with-notes** 并许可合入 dev）。提交链：`39adc57`(merge `f045433`) → `2bd768a`(契约 13 处) → `d0e9b84`(登出代次) → `2d6c723`(Worker 有界周期调度) → `c59a18b`(注释与遗留计数更正) → `76a01f0`(调度语义注释精确化)。

残留限制**与上轮一致**（已消除唯一的 scheduler 语义措辞不准确项），须持续披露：
1. incident 扫描的 `episode × destination` **总扇出无硬预算**（候选 gimbal 数有界；Oracle 判 MVP 可按运营规模接受并监控，后续应预算化治理）；
2. D 的 cleanup 候选发现**无 keyset**，永久被安全跳过的头部候选可造成后续候选**饥饿**（非阻塞但应修，归 D/集成方；调大 batch 不能根治）；
3. `resolved` incident episode **不自动压缩**，规模增长会延长扫描周期（归集成/数据所有者设计压缩、索引或迁移）；
4. 仍有 **32 处**旧式 `allOf/oneOf/anyOf + nullable` 建模（含 `ProgressWithSync.targetCount`；清单见 `contracts/decisions-notes.md:178-204`）；
5. **E 的 CC-11 selfcheck/allowlist 待更新**（`test_framework_selfcheck.py:958`、`c_care.py:98-154`）——在此之前**不得宣称整体集成验收全绿**；
6. 登出的**会话撤销与 T09 更新不是跨资源原子事务**（T09 侧为单条原子 UPDATE；撤销在 `SessionProvider` 内、不在 DB 事务中；T09 失败依赖既有补偿与投递侧 fail-closed）；
7. Worker 停机可立即打断等待，但**不能中断正在执行的同步 DB 扫描**；
8. Python 测试基础设施仍依赖 `MVP_A_PG_*`（`tests/conftest.py` 默认指向被禁用的 55432）；
9. **C25/C26** 协议、generation 表容量告警与受控恢复 runbook **待冻结**（归总协调与 APP/设备协议提供方）。

## 13. 测试注入缝轮（E 余下 6 项 `seam_pending`；总协调指定 B 为唯一业务/运行时代码负责人）

**授权与边界**：E 的完整 matrix 运行 `E-20260912T105030Z-8b5a243f` 结算 **55 PASS + 33 device_pending + 6 seam_pending（staged=0）**。总协调指定 B 为这 6 项**测试注入能力的唯一业务/运行时代码负责人**，要求让 E 能**从真实 HTTP 入口驱动实际 worker 业务路径**，证明**失败持久化、重试/恢复、无脏成功**；允许 Python Worker 端口工厂/测试配置与必要最小 runtime 代码 + 定向测试；**禁止生产可调用后门、禁止公共 HTTP 任意故障开关**；**仅测试环境显式启用、默认关闭并验证生产 fail-closed（含混合 profile 与 `app.env` 矛盾组合）**；**不得由未授权业务请求开启**；**不改业务判定迎合测试**；E 只在总协调合入后验收。

**基线与同步**：dev 指定 SHA `5bd22d3` **已等于本轮起点 HEAD**（`HEAD..dev` 为空、树 clean）⇒ 同步为**空操作**。**E 实测的代码 SHA `5a871bf` 相对 `5bd22d3` 的业务代码 diff 为空**（`git diff --stat 5bd22d3..5a871bf -- backend/web-java backend/worker-python backend/contracts backend/deploy backend/doc` 无输出；其 2709+ 改动全是 E 自己的 `backend/acceptance/**` 与 2 份 E 交付文档）⇒ **E 所测业务代码与本轮起点逐字节相同**，可安全在 `5bd22d3` 上实施。`seam_pending` 不在 `matrix/scenarios.json`（E 分支上 94 项均为 `dependency_pending`），它是**该次运行的结算分类**；权威条件取自 E 已编写的场景步骤（`tests/scenarios/test_sc02.py`/`test_sc03.py`/`test_scc.py` @ `5a871bf`）与总协调转述的 `handoffs/E-injection-checklist.md`。**B 未修改 `backend/acceptance/**` 任何文件、未运行其任何脚本、未进入 `.worktrees/mvp-e`。**

**提交链**：`5bd22d3` → **`7524714`**（Java 侧 SC-C-05 存储失败注入缝，按 purpose 粒度）→ **`9b3d802`**（Python 侧 7 个注入旋钮 + 生产启动守卫 + 29 项定向测试）→ **`f4b9546`**（仅测试：消除硬编码 18083 端口冲突）。**本轮最终代码 SHA = `f4b9546ae17a2b36739b4e72690681e3333556cd`**；变更面 **12 文件 / +1579 −8**，**0 个禁域文件**（`acceptance`/`contracts`/`backend/tests`/迁移/`deploy`/`handoffs` 全空）。

### 13.1 旋钮总表（8 个；全部默认关闭，默认值 = 当前行为）

| env | 侧 | 值域 | 默认 | 服务的场景 |
|---|---|---|---|---|
| `MVP_D_FACE_DOUBLE_QUALITY` | Python | `accepted` \| `needs_retake` | `accepted` | SC-02-05、SC-02-08/09 的入口 |
| `MVP_D_FACE_DOUBLE_REQUIRED_VIEWS` | Python | `front`/`left`/`right` 子集（逗号分隔） | 空（用替身默认） | SC-02-05 的 `requiredViews` |
| `MVP_D_FACE_DOUBLE_SAME_PERSON` | Python | `true` \| `false` | `true` | SC-02-06（`NOT_SAME_PERSON`） |
| `MVP_D_FACE_DOUBLE_SEARCH` | Python | `reliable_new`\|`matched`\|`uncertain`\|`ambiguous`\|`dependency_failed` | `reliable_new` | SC-02-06（`IDENTITY_UNCERTAIN`）、SC-02-07 的 matched 分支 |
| `MVP_D_PLAN_DOUBLE_MODE` | Python | `valid`\|`timeout`\|`failure` + `PlanDouble` 既有 10 种非法形状 | `valid` | SC-03-07 |
| `MVP_D_SKIN_DOUBLE_HOLD` | Python | `true` \| `false` | `false` | SC-02-09 的 hold/release |
| `MVP_D_STORAGE_DOUBLE_FAIL_PUT` | Python | `true` \| `false` | `false` | SC-C-05 要求③（Worker 结果图保存） |
| `APP_DOUBLE_STORAGE_FAIL_MODE` | Java | `none`\|`fail-put`\|`fail-put:<purpose>[,…]` | `none` | SC-C-05 要求①②（云台原图、APP 授权/核验证据上传） |

实现要点：**只经既有适配端口/端口工厂注入**（`providers.py` 的 `_face_double_from_config`/`_skin_double_from_config`/`_plan_double_from_config` 仅给**既有替身构造参数**赋值；Java 仅在 `FileSystemStorageDouble` 内受控抛**既有** `UncheckedIOException`）；**未新增端口、未新增业务错误码、未新增表/列/迁移、未改任何业务判定**（`assessment_analyze.py`/`plan_generate.py`/`identity_enroll.py`/`dmedia.py`/`runtime/**`/`handlers/__init__.py`/`notifications/**` 与 Java 的 `media`/`assessments`/`identity`/`care`/`mediapolicy`/`ProductionFailClosedValidator`/`AppProperties`/`src/main/resources` 的 **diff 全空**）；**无任何 HTTP 可开启路径**（两个 Java main 文件中 `RequestParam|RequestHeader|PathVariable|RequestBody|@*Mapping` 计数 0；Python diff 中无 route/endpoint）；**无 sleep、无改 DB 伪造迟到**（diff grep 为空）。

### 13.2 生产 fail-closed（双判据 + 启动期守卫，orchestrator 亲自取真实进程证据）

- **Java**：`TestDoubleProvidersConfig.requireNoProductionSignals`——`environment.acceptsProfiles(Profiles.of("prod"))` **或** `app.env`（trim + 忽略大小写）等于 `production` ⇒ 抛 `IllegalStateException` **拒绝装配替身**（与 `DocsProductionGuard` 同款双判据）；纯 prod profile 下 `StoragePort` 替身根本不装配；生产若刻意 `mode=real` 绕开本配置，另有**既有** `ProductionFailClosedValidator` 兜底（未改）。
- **Python**：`dconfig.py` 新增 `DOUBLE_INJECTION_SWITCHES`（7 项及默认值）、`double_injection_overrides()`（**语义比较**，`0/no/off` 不算注入）、`production_environment_signals()`（解析后环境沿用 `notifications/config.py` 优先级 + `MVP_NOTIFY_ENV`/`MVP_WORKER_ENVIRONMENT`/`APP_ENV` 三处 raw env + **`SPRING_PROFILES_ACTIVE`**）、`assert_no_double_injection_in_production()`；`__main__.py:_validate_startup_config()` 在 `main()` 中**早于 DB 与健康端口**调用；`__post_init__` 对非法取值**加载期 fail fast**。
- **orchestrator 亲验的真实进程证据**：
  - Java：打包 jar 后以 `APP_ENV=dev APP_PROVIDERS_MODE=doubles APP_DOUBLE_STORAGE_FAIL_MODE=fail-put` + `--spring.profiles.active=prod,dev --server.port=18083 --spring.flyway.enabled=false` 启动 → **`APP_EXIT=1`**；日志逐字含 `production fail-closed: test-double providers refused under production signals (active-profile-prod=true, app.env=dev, activeProfiles=[prod, dev])`；**`grep -c "Tomcat started on port"` = 0**；退出后 18083 **空闲（从未绑定）**；无遗留 JVM。
  - Python（`python -m mvp_worker --check`，DSN 指向 55435）：`APP_ENV=production` + `MVP_D_SKIN_DOUBLE_HOLD=true` → **rc=1**，`ProviderConfigError: production fail-closed … signals=['resolved_environment=production','APP_ENV=production'] switches=['MVP_D_SKIN_DOUBLE_HOLD']; refusing to start`（**早于 DB**）；`APP_ENV=production` + `MVP_D_FACE_DOUBLE_SEARCH=uncertain` → rc=1；**`SPRING_PROFILES_ACTIVE=prod,dev` + `APP_ENV=dev` + `MVP_D_PLAN_DOUBLE_MODE=timeout` → rc=1，`signals=['SPRING_PROFILES_ACTIVE=prod,dev']`**（矛盾组合亦拒）。
  - **不误拦默认态**：生产 + 全默认 → **rc=0**；混合 `prod,dev` + `app.env=dev` + 全默认 → **rc=0**；dev + 注入 → rc=0；**dev + 7 个开关全非默认 → rc=0**。
  - **非法值 fail fast**：`MVP_D_FACE_DOUBLE_QUALITY=bogus`、`MVP_D_PLAN_DOUBLE_MODE=bogus` → **rc=1** 且列出完整允许值域。

### 13.3 SC-02-09：从"进程级 hold"到"租约接管 + 真实迟到返回"（含 orchestrator 自身论证错误的更正）

**第一版实现（`9b3d802`，已被判不足）**：因端口方法签名不含 task id / photo version，实现为**进程级 hold**——`MVP_D_SKIN_DOUBLE_HOLD=true` 时 `analyze` 经 `_FaultInjector` 抛 `ProviderUnavailable` → handler 映射为 `JobFailed(DEPENDENCY_UNAVAILABLE, retryable=True)` → 复用 A 既有退避重排队，旧执行停在 `queued`；撤 env 即 release。无 sleep、无改 DB、无改业务判定。

**Oracle 判此项为 BLOCKER**（理由经我读码核实成立）：hold 只是立即抛错并重排队，**被重驱时会重新读取当前 DB 输入**，因此它证明的是"陈旧代次被忽略"，**不是**"旧版本已算出的结果迟到返回"；且其定向测试 `test_sc0209_old_revision_released_does_not_overwrite_new_report` 用 `_seed_analysis_case(...status="analyzing")` + `mark_report_ready(...)` + `_enqueue_analyze(aid, 1)` **直接种库并手工入队旧代次**，正是清单禁止作为唯一证据的 DB 伪造迟到。**总协调裁定同此**：`ProviderUnavailable` 重排 queued、撤 env 重跑**不等同**真实迟到发布竞争；必须"旧算法调用已取得旧版本输入并延迟返回，待新版本成功后旧结果才返回"，**不能以静态 revision 守卫代替证据**。

**orchestrator 的论证错误（如实记录）**：我曾据三条证据断言该交错"经真实 HTTP+worker 路径结构性不可达"——①`_retake_result` 返回 `HandlerResult(business_tx=tx)`，`runtime/complete.py:187-189` 证明 business_tx 与 `complete_success` **同一事务原子提交**（`:179` docstring 明写）；②`_mark_analyzing` 是**自有短事务**且在调用任何 provider 之前提交（`assessment_analyze.py:239-241`）；③A02 要求 `status='needs_retake'`（`AssessmentAcceptanceService.java:241-243`）。**该论证范围有误**：它只考虑了"同一执行者原子完成"，**未覆盖租约过期后由另一执行者接管同一旧任务**的路径。总协调指出该候选后，我复核源码确认其**可达**：`runtime/expire.py:41-47` 把 `status='running' AND lease_until < CURRENT_TIMESTAMP` 的任务重置为 `queued`（`recover_expired` 在 `:87`）⇒ 另一执行者可接管；`claim.py:26-41` 接管时改写 `lease_owner` 并 `lease_revision+1`（推进围栏令牌）；`complete.py` 的守卫 0 行 → `StaleGeneration` 且**整体回滚**；`assessment_analyze.py:176-190` 捕获 `StaleGeneration` 记 `analyze.fenced_write_stale`（"lease lost; business write rolled back"）后返回 None；`_publish:705-727` 另有 `processing_revision`/`report_ready` 双重守卫。且 `config.py:24-25,70-75` 已有 `MVP_WORKER_LEASE_SECONDS`/`MVP_WORKER_RENEW_INTERVAL_SECONDS` ⇒ **测试租约配置无需新增、更无需关闭租约机制**。

**总协调裁定的实施边界**：**不拆** `_MARK_RETAKE` 与任务完成的原子事务；**不放宽** A02 门禁；**保留业务规则**；允许**有界测试 barrier** 与**测试租约配置**；**不得**直接改 DB 伪造状态；**不得**关闭正常租约机制来构造竞争；该项为**待核实路径、不预断可达**，若仍不可达须给出最小源码/事务/租约证据与已验证的可达替代边界交裁定，**不得擅标 PASS、不得改业务使测试可达**。

**目标时序（实施中，须全程经真实 HTTP + 正常 worker/租约机制）**：M3-A01 受理 v1（照片含可识别标记）→ Worker A（短租约）领取并 `_mark_analyzing` → provider **先按 v1 输入算出旧结果**再在**一次性有界 barrier** 上等待 → 租约自然过期 → `recover_expired` 重置 queued → Worker B（`quality=needs_retake`，barrier 已消费故不阻塞）接管并**原子提交 `needs_retake`** → M3-A02 补拍 v2 **受理**（rev=2）→ Worker C 跑 J2 → `report_ready`/`report_photo_version=2` → **释放 barrier** → Worker A 返回**第 2 步算出的旧结果** → 被既有围栏（`StaleGeneration` + `_publish` 守卫）拒绝、业务写整体回滚。断言：`report_photo_version` 仍为 2、`report_payload`/`report_id`/`report_summary` 逐值未变、`member_id` 未被旧执行改写、仅一个 `report_ready`、`async_jobs` 无伪终态、可见围栏丢弃证据。

### 13.4 SC-C-05 的按用途粒度（总协调加严项）

- **Java（上传路径）**：`fail-put:<purpose>[,…]`，purpose 白名单**由 `MediaPurpose.values()` 派生**（非硬编码子集）⇒ 覆盖全部 5 种用途（`assessment_source` 云台原图 / `grant_face` APP 授权人脸 / `assessment_result` / `execution_face`、`revalidation_face` 核验证据）。`purposeOf(objectKey)=split("/")[1]` 与 `MediaService.java:66` 的 `objectKey = env + "/" + purpose.dbValue() + "/" + id` **格式吻合**（若不吻合则按用途选择会**静默失效**，已核实）。只注入 `put`，读/存在性/删除不受影响。
- **Python（结果图）**：`MVP_D_STORAGE_DOUBLE_FAIL_PUT=true` 仅对 key 用途段为 `assessment_result` 的写入抛 `StorageError` → 走**既有** `RESULT_ARCHIVE_FAILED`（可重试）路径。
- **无脏成功**（断言级证据）：注入 `assessment_source` 时 M3-A01/A02 → **503 `DEPENDENCY_UNAVAILABLE`**、`media_objects` 中 `available` 行数 **=0**、`failed ≥1`、`skin_assessments` 任务数 **=0**、`report_ready` **=0**；注入 `grant_face` 时 M1-A01 → **503**、available=0、failed=1、**`member_access_grants`=0**、`idempotency_requests.status ≠ succeeded`。**按用途互不干扰**：注入 `assessment_source` 时 M1-A01 仍 **201** 且 available；注入 `grant_face` 时 M3-A01 仍 **202** 且 available。**复位与重启可读**：默认 `none` → A01 **202**、三视角 available、对象真实落盘且字节一致、**新建替身实例（模拟重启）`exists`+`get` 可读回**。

### 13.5 b36 端口冲突：取证、我自己的断言用法错误与修复（`f4b9546`）

端到端验收在 `9b3d802` 上为 **38 PASS / 1 FAIL（b36 = Java 全量 mvn）**。orchestrator 取证根因**不是产品回归**：新测试 `StorageFailModeProductionFailClosedTest.java:121/:129` **硬编码 `new ServerSocket(18083)`**，而验收 harness 把真实 Spring 应用跑在 18083 且 b36 在其存活期间执行 mvn。复现证据：用哑监听占住 18083 后跑该测试类 → `Tests run: 7, Failures: 0, **Errors: 1**`、`java.net.BindException: Address already in use` at `:121`、BUILD FAILURE、rc=1；释放后 → `7/0/0`、BUILD SUCCESS、rc=0。该缺陷会使**任何**在 18083 有进程的环境（含 E 的 harness 与总协调预览实例）失败，故必须修。

修法**不弱化断言、反而加强**：移除两处端口探针与 `ServerSocket` import（该 runner 为非 web 的 `ApplicationContextRunner`，端口探针证明力极弱却带来真实冲突），改断言 ①`ctx.hasFailed()` ②根因 `IllegalStateException` ③消息含 `Error creating bean with name 'storagePort'` 与 `Failed to instantiate [cn.yuanxin.mvp.web.media.StoragePort]`（即拒装发生在 `storagePort` @Bean 装配期 ⇒ 无可注入替身）④堆栈含 `production fail-closed`/`active-profile-prod=true`/`app.env=dev`；"端口从未绑定"改由 13.2 的**真实进程证据**承担。**并如实记录 orchestrator 自己的一处错误**：首次改写时用了 `assertThat(ctx).doesNotHaveBean(StoragePort.class)`，而 AssertJ 对**启动失败的上下文**不允许 bean 断言（报 "but context failed to start"）——以真实失败输出定位后改为上述等价证据，并把该陷阱写入测试注释。修复后**在 18083 被占用条件下**该测试类 **7/0/0 rc=0**，端到端验收在 `f4b9546` 上 **ALL PASS 39/39 `SCRIPT_RC=0`**（b36 转 PASS）。

### 13.6 验证（orchestrator 亲自执行，绑定 `f4b9546`）

| 项 | 结果 |
|---|---|
| Java 全量 `mvn -B test`（限堆 768m、55435、未设 `APP_STORAGE_DEV_DIR`） | **419 / 0 failures / 0 errors / 0 skipped，BUILD SUCCESS，rc=0**（基线 401 + 新增 18） |
| **18083 被占用条件下**单跑 `StorageFailModeProductionFailClosedTest` | **7 / 0 / 0，BUILD SUCCESS，rc=0**（修复前同条件 `Errors: 1` + `BindException`） |
| `mvn -B -q test-compile` | **rc=0**（据此判定 LSP 对该文件 `[147:1] Syntax error` 为**过期误报**，未据此改码） |
| Python 全量 `pytest -q`（真实 PG 55435，须补 `MVP_A_PG_DSN/HOST_PORT/USER/PASSWORD/CONTAINER`） | **259 passed / 0 failed / 0 errors，rc=0**（基线 230 + 新增 29）；新测试单跑 29 passed |
| Python 启动守卫真实进程（A1–A7 七组） | 见 13.2（生产/矛盾组合拒启 rc=1；默认态与 dev 注入 rc=0；非法值 rc=1） |
| Java 真实进程生产 fail-closed | `APP_EXIT=1`、守卫消息逐字命中、`Tomcat started on port` 计数 **0**、18083 从未绑定、无遗留 JVM |
| **端到端验收 `backend/tests/run-acceptance-b.sh`** | 在 `9b3d802` 为 38/39（b36 因端口硬编码 FAIL，已取证）；**在 `f4b9546` 为 ALL PASS 39/39、`SCRIPT_RC=0`**，HEAD 未变 |
| 写域与纪律 | 12 文件全在授权写域；`backend/acceptance/**`、`backend/tests/**`、`backend/contracts/**`、迁移、`deploy`、`handoffs` **diff 全空**；未触碰 18080/E 的端口与 `.worktrees/mvp-e`；未停 PG、未清库/卷、未动 `swagger_preview`；运行文件在 `.coordination/B-work/seam-injection/`（未用 /tmp） |

### 13.6.1 Oracle FAIL 后的两次整改提交（orchestrator 亲自验证）

| 提交 | 内容 | 我的验证 |
|---|---|---|
| **`d312d2a`** | 删除 `FileSystemStorageDoubleFailModeTest` 文件尾多余空行（Oracle SUGGESTION：`git diff --check` 报 `:99 new blank line at EOF`） | `od` 确认文件尾由 `}\n}\n}\n\n` 变为 `}\n}\n}\n`；**`git diff --check 5bd22d3..HEAD` rc=0**；定向 `mvn -B test -Dtest=FileSystemStorageDoubleFailModeTest` **5/0/0 BUILD SUCCESS** |
| **`40f5fde`** | 闭合 Oracle **IMPORTANT**：三个布尔注入开关改用严格解析（`strict_env_bool`，只接受 `1/true/yes/on` 与 `0/false/no/off`，其余加载期抛 `ProviderConfigError`），`double_injection_overrides()` 与 `media/storage.py` 运行时读取**复用同一解析**（单一语义、消除守卫与运行时不一致窗口），`REQUIRED_VIEWS=,,,` 亦 fail fast；既有非注入旋钮的宽松 `_env_bool` **行为未改** | 我亲跑 Oracle 指定 4 条命令**全部 rc=1** 且消息含变量名与实际取值及值域；全量 `pytest -q` **279 passed / 0 failed / 0 errors，rc=0**（基线 259 + 20）；生产守卫三态抽查：production+注入 rc=1、production+全默认 rc=0、dev+`off` 别名 rc=0；`providers.py` 与两个 `test_sc0209_*` 测试**未被改动**（无删除/弱化断言） |

**更正一处我自己的计数错误**：我在送 Oracle 的任务书中写"变更面 13 个文件"，实际为 **12 个**（Oracle 指出，`git diff --name-only 5bd22d3..f4b9546 | wc -l` = 12）。本节表格与 13 节正文均以 12 为准。

**另需说明的证据时序**：Oracle 复审报告中称"`f4b9546` 最终 39/39 尚未提供" —— 那是因为我**先派发复审、后完成验收复跑**；该复跑结果已于  取得：**在 `f4b9546` 上 ALL PASS 39/39、`SCRIPT_RC=0`、HEAD 未变**（其中 b36 由 FAIL 转 PASS，证明端口冲突修复在 harness 真实条件下成立）。

### 13.7 本轮待裁定 / 持续披露项

1. **SC-02-09（BLOCKER，整改中）**：第一版进程级 hold 被判不等同真实迟到返回；总协调已裁定实施边界（见 13.3），改以"**租约过期 + 另一执行者接管 + 一次性有界 barrier + 释放后返回接管前算出的旧结果**"构造真实交错，须由既有围栏（`StaleGeneration` / `_publish` 守卫）拒绝旧写，**不得**拆原子事务、放宽 A02 门禁、改 DB 伪造或关闭租约机制。**状态：实施中，未交付**；若复核后仍不可达，将按裁定提交最小源码/事务/租约证据与可达替代边界，**不擅标 PASS**。
1b. **SC-02-10（总协调新增第 7 项，整改中）**：E 的 `af348c4` 把 SC-02-10 由 PASS 纠正为 `seam_pending`（现 **54 PASS + 7 seam**），因其现用的 `MVP_D_SKIN_PROVIDER=aliyun_skin`（`ProviderNotActivated`）**只触发瞬态重试**，黑盒无法确定到达测肤**终态失败**与 `failure_code`。要求：经**真实 HTTP 受理 + worker 正常失败/重试流程**确定性到达**既有终态失败**，让 E 断言错误信息/任务状态一致、**无伪 ready**，且**不改变生产失败规则**（推荐落点：让 skin 替身返回违反**既有**白名单/基线校验的指标，走既有 `_ContractViolation` → `_terminal(PROVIDER_CONTRACT_VIOLATION)` 路径，注入只改替身返回值）。**状态：实施中，未交付。**
2. **`search=matched` 的黑盒驱动受限**：`FaceDouble.face_subject_ref` 无 env 旋钮（不在本轮清单，未擅自新增），故 env 只能置分类；已用 `extras` 注入证明分支可用、env 值域与工厂透传可用。若 E 需黑盒驱动"可靠匹配既有成员"（影响 **SC-02-07** 的完整覆盖，**不属本 6 项**），需追加 `MVP_D_FACE_DOUBLE_FACE_SUBJECT_REF`（请裁定）。
3. **`execution_face`/`revalidation_face` 无专用端到端 IT**（其上传端点属 C 域）：机制同构、值域由 `MediaPurpose.values()` 派生、按用途选择性已由单元测试与两条 HTTP 端到端 IT（`assessment_source`/`grant_face`）证明。
4. **共享测试基建**：`worker-python/tests/conftest.py` 的 session fixture 会调 `backend/deploy/dev/migrate.sh`（内含 `mvn flyway:migrate`）；`WorkerConfig.check_dsn` 只读 `MVP_A_PG_DSN`（默认指向被禁用的 55432，故 `--check` 须显式给该变量）。两者均属共享基建，**B 未改**，提请裁定归属。
5. **Java 侧接受 `assessment_result` 值但结果图由 Worker 写入**，故 Java 侧对该 purpose 的注入通常不命中上传路径（语义冗余，是否收窄值域请裁定）。
6. 注入为**进程级**（启动时读取），不支持运行中动态切换或按单次请求切换——**刻意设计**，以满足"不能由未授权业务请求开启"。
7. 第 12.5/12.7 节的全部残留限制**继续有效**（扇出无硬预算、D cleanup 无 keyset、resolved episode 不压缩、32 处旧式 nullable、E 的 CC-11 selfcheck/allowlist 待更新、登出非跨资源原子事务、C25/C26 待冻结）。

### 13.8 E 复验入口（配置 / 复位 / 最小调用示例）

- **Java 侧**：`.coordination/B-work/seam-injection/SC-C-05-java-E-repro.md`（旋钮值域、purpose→真实 HTTP 入口对应表、5 组最小调用示例、预期 HTTP 码与 DB 可观测量、复位与重启可读、生产不可达的 6 种组合表、已知边界）。**关键操作细节**：`APP_DOUBLE_STORAGE_FAIL_MODE` 在 **bean 装配期读取一次**，改变取值须**重启 Java 进程**；启动日志出现 `storage test-double write-failure injection ARMED: …` 即生效。
- **Python 侧**：`.coordination/B-work/seam-injection/README-seams.md`（7 个旋钮总表、SC-02-09 hold/release 驱动时序、与 Java 侧按用途的区分、6 组复验命令示例）。已核实其旋钮名与默认值与 `dconfig.py:18-23,65-68,96-101`、`media/storage.py:16` **逐项一致**。
- 两份手册均在 gitignored 的运行目录内；如需随代码入库供 E 直接使用，请总协调指定落地路径（B 不擅自写入 `backend/acceptance/**`）。

### 13.9 Oracle 有界复审结论（绑定 `f4b9546ae17a2b36739b4e72690681e3333556cd`）

**`VERDICT: FAIL`，明确"不可合入 dev"**。范围限本轮注入缝（未重审 R6 已通过的 B 业务代码、R8 已通过的 Swagger、上一轮已通过的公共集成修复）。

**判为通过的项（逐条，含 Oracle 依据行号）**：①业务 handler/runtime/notifications/Java 业务包/配置/资源/契约/迁移 **diff 均为空**；②注入仅改变 doubles（`providers.py:499-575`、`media/storage.py:23-26,72-79`、`FileSystemStorageDouble.java:70-123`），未改业务判定；③未增错误码/表/列/迁移、未放宽业务条件；④默认值与原行为一致（`dconfig.py:64-102,295-315`、`storage.py:23-26`、`FileSystemStorageDouble.java:70-78`，`application.yml` 未改）；⑤生产信号覆盖解析环境 + 三组 raw env + `prod/production` profile（`dconfig.py:183-225`）、启动校验早于 DB/健康端口（`__main__.py:25-40,124-128`）、Java `prod,dev + app.env=dev` 在 bean 装配期失败（`TestDoubleProvidersConfig.java:56-82`）；⑦未新增任何 Controller mapping/参数/header/route/endpoint，注入不能由业务请求开启；⑨⑩⑪⑬质量缝、身份缝、补拍态入口、plan 确定性超时均判通过；⑭Java purpose 白名单由 `MediaPurpose.values()` 派生、key 第二段与 `MediaService.java:63-72` 一致；⑮`f4b9546` 删端口探针改为验证 root cause 与 `storagePort` bean 创建失败，**属加强而非弱化**。

**未通过 / 需整改**：
- **BLOCKER（第 12/18 项）**：进程级 hold 不满足 SC-02-09 的黑盒时序要求（理由与我的核实见 13.3），且其测试以直接种库 + 手工入队旧代次作为证据，属清单禁止的 DB 伪造迟到。Oracle 明确：**不要直接扩展 SkinPort**（task/revision 不是供应商职责）；如需保留该验收，应授权独立的 test-profile、按 assessmentId+processingRevision 定向的 **worker 完成边界 seam**，且生产启动守卫强制拒绝。→ 总协调随后裁定走"租约过期 + 接管 + 有界 barrier"路径（见 13.3）。
- **IMPORTANT（第 6/8 项）**：布尔注入值不严格校验，未知值静默当 false（`dconfig.py:148-152`、`:163-180`、`storage.py:23-26`），`MVP_D_FACE_DOUBLE_SAME_PERSON=bogus` 会**静默触发 NOT_SAME_PERSON 分支**；`REQUIRED_VIEWS=,,,` 不失败。→ **已闭合于 `40f5fde`**（我已亲验 4 条命令 rc=1 与 pytest 279 passed）。
- **SUGGESTION**：`FileSystemStorageDoubleFailModeTest.java:99` EOF 多余空行致 `git diff --check` 非零 → **已闭合于 `d312d2a`**（我已亲验 rc=0）；范围声明称 13 个文件、实际 12 → **已在 13.6.1 更正**。

**Oracle 对 18–22 的归属裁定**：18 进程级 hold = **阻塞**（总协调先裁定验收语义）；19 `matched` 的 `face_subject_ref` = 非阻塞、本六项范围外（若重开 SC-02-07 再由 D/B seam 负责人最小追加）；20 `execution_face`/`revalidation_face` 专用 HTTP 证据 = 非阻塞代码项但属**最终证据缺口**，由 E 用 C 的 HTTP 端点验证，B 无需改 C；21 `conftest`/DSN = 非阻塞生产项，归共享测试基建所有者或总协调；22 Java 接受 `assessment_result` = 非阻塞、可接受冗余，文档说明即可。

**Oracle 要求持续披露的残留限制**：注入开关是**进程级** env、非 task/RUN_ID 级，同一 worker 会影响其领取的所有同类任务，测试必须隔离队列/DB 并禁止并行污染；SC-02-09 当前只能证明 retry 与 revision guard；`matched` 分类无可配置 `face_subject_ref`；`execution_face`/`revalidation_face` 缺专用 HTTP 端到端证据；Java `assessment_result` 模式通常不命中实际上传路径；真实提供方仍未接入（seams 仅限 doubles）；Java 正式生产信号约定仍是 profile `prod` 或 `app.env=production`；共享 pytest DSN/迁移 fixture 仍依赖 `MVP_A_PG_*`。

### 13.10 BLOCKER 整改与总协调新增第 7 项（`181676d`）

**项 A —— SC-02-09 改为"真实迟到返回"**：按总协调裁定（不拆原子事务、不放宽 A02 门禁、保留业务规则；允许有界测试 barrier 与测试租约配置；不得改 DB 伪造状态、不得关闭租约机制），新增 `providers.py:163-229` 的 `LateReturnBarrier`：**文件态**（`consumed`/`released` sentinel，不写任何 DB 业务表）、**一次性**（`os.open(O_CREAT|O_EXCL)`，`FileExistsError` 即立即返回 ⇒ 接管者不被阻塞）、**先算后等**（`compute_then_wait` 返回调用方已算好的旧结果、不重算）、**有界**（monotonic deadline + 0.1s 轮询，超时清理并抛**既有** `ProviderUnavailable`）、`finally` 清理两个 sentinel。命中标记取**上传照片内容 sha256** ⇒ **未扩展端口签名**（Oracle 明确 task/revision 不是供应商职责）。新增 4 个 barrier 旋钮全部登记进 `DOUBLE_INJECTION_SWITCHES` 并走严格解析。

**已由真实围栏路径实测的子时序**（`tests/test_seam_boundary_repro.py:159-283`；`_seed_marked_case` 只铺初始 fixture，**不伪造时序状态**；领取/回收/接管/完成全部走真实 `claim_batch`/`recover_expired`/`handle`/`complete_success`）：`A_in_barrier{owner=A,lease_revision=1,attempt=1,assessment=analyzing}` → `after_recover_expired{queued,lease_owner=null,lease_revision=2}` → `B_takeover{owner=B,lease_revision=3,attempt=2}` → `B_committed{job=succeeded,assessment=needs_retake}` → `A_released_old_result{HandlerResult}` → **`A_fenced{StaleGeneration}`**；终态 `needs_retake`、`report_id`/`report_payload`/`member_id` 均 null、`report_ready` 行数 0、barrier 无残留。关键断言为 `with pytest.raises(StaleGeneration): complete_success(engine, claim_a, handler_result_tx=result_a.business_tx)`。短租约经既有 `lease_seconds` 参数自然过期（单次 handle 无续租线程），**未关闭续租机制**。

**项 B —— SC-02-10（总协调新增第 7 项）**：E 的 `af348c4` 把它由 PASS 纠正为 `seam_pending`，因其现用的 `MVP_D_SKIN_PROVIDER=aliyun_skin`（`ProviderNotActivated`）**只触发瞬态重试**、黑盒无法确定到达终态失败。新增 `MVP_D_SKIN_DOUBLE_INVALID`（`none|unknown_metric|out_of_range|bad_unit`，默认 `none`）：让 skin 替身返回违反**既有**白名单/基线校验的指标，经**既有** `_ContractViolation` → `_terminal(PROVIDER_CONTRACT_VIOLATION)` 路径，**1 轮确定性**（`attempt_count==1`，不靠预算耗尽）到达 `status='failed'`、`retryable=false`、`report_id`/`report_payload` null、**无后继 job**（`async_jobs==1`，即未产生 `identity.enroll`/`plan.generate`）。三形态的 `failure_detail.reason` 实测为 `$.metrics[3].name: not in approved baseline` / `$.metrics[3].value: out of approved range` / `$.metrics[3].unit: not in approved baseline`。投影一致性：`FailureProjection.PUBLIC_FAILURE_CODES` 含该码且 `retryable(code)→false`（`FailureProjection.java:45-54,66-82`），`failure_detail` **不投影**。**未改任何生产失败规则**（`_transient_or_terminal`/`_terminal`/`_validate_metrics`/`_publish` 与 `assessment_analyze.py` 整体 diff 为空），未新增业务错误码。

**orchestrator 独立核验（不采信自报）**：写域恰 3 路径，业务文件（`assessment_analyze.py`/`plan_generate.py`/`identity_enroll.py`/`dmedia.py`/`runtime/**`/`handlers/__init__.py`/`media/storage.py`/`notifications/**`）与 Java/`acceptance`/`contracts`/`backend/tests`/`deploy` 的 **diff 全空**；`providers.py` 中 `engine|connect|execute|text(` 计数 **0** ⇒ barrier 确实不触 DB；我亲跑 **pytest 291 passed / 0 failed / 0 errors，rc=0**（基线 279 + 12）；守卫 CLI **七组全符预期**（production+barrier rc=1 且列明 `switches=['MVP_D_DOUBLE_LATE_BARRIER','MVP_D_DOUBLE_LATE_BARRIER_SHA256']`、production+`SKIN_DOUBLE_INVALID` rc=1、production+全默认 rc=0、dev+全合法非默认 rc=0、缺 SHA256 / `SHA256=zz` / `SKIN_DOUBLE_INVALID=bogus` / `TIMEOUT_SECONDS=0` 四组 fail-fast 均 rc=1 且消息含值域）；并逐行核实两个核心测试的**尾部断言**确为真实（`StaleGeneration` 抛起、v2 快照逐值未变、sentinel 已清理、`attempt_count==1`、`async_jobs==1`、`report_ready==0`），非空跑。

**端到端缺口已闭合（`8343ba5`，orchestrator 亲跑 `ALL PASS 41/41`）**：`181676d` 交付时如实标注的唯一缺口——SC-02-09 的 Java HTTP 步骤（`PUT …/photo-versions/2` → J2 → `report_ready(v2)`）与 SC-02-10 的 M3-A03 投影一致性——已由 B 自有验收工装的新检查 **b40/b41** 以**真实 HTTP + 真实 worker/租约/围栏**打通（详见 `B-seam-repro.md` §5.1/§5.2 的实测中间态与 E 可照抄序列）。**红线核实**：b40/b41 新增区（`b-checks-3.sh` 第 315 行起）`UPDATE|INSERT INTO|DELETE FROM` **零命中**、`psql_b` 调用**全为 SELECT** ⇒ 未以改 DB 伪造时序状态；`b_drain_queue` 仅用真实 `mvp_worker --once` 排空（注释明写"不直接改状态"）；`cleanup()` 增加后台 Worker A 的强制回收（pid → kill → 最多 10s → `kill -9`）⇒ 无遗留进程；**b1–b39 断言零改动**（本提交删除行仅 3 行文件头注释，numstat = `run-acceptance-b.sh +14/−2`、`b-checks-3.sh +266/−1`）。

**如实披露（仍未闭合或需注意）**：①barrier 超时后同一 job 若被重试会**再阻塞一个 timeout**（有界、不永久挂起；复验方应把 `TIMEOUT_SECONDS` 设为足以覆盖整个驱动序列，B 的工装用 180）。②`TIMEOUT_SECONDS` 传**非数字**时抛 `ValueError` 而非 `ProviderConfigError`（两者均在启动前失败，不进入运行期）。③未设 `_DIR` 时落到**系统临时目录**，多场景并跑须各自指定独立目录，否则会互相消费 sentinel。④`MVP_D_SKIN_DOUBLE_HOLD` 与其两个既有测试**保留未弱化**（与 barrier 正交：hold=进程级可重试失败、无输入标记；barrier=输入标记驱动的真实迟到返回）。⑤A 的迟到结果被**双重围栏**：先在 `archive_result_images` 的 `fenced_business_tx` 抛 `StaleGeneration`（`handle` 内捕获，**DEBUG 级默认不落日志**），随后 `complete_success` 守卫再次拒绝并落 **WARNING `job.complete_stale_generation`**；b40 断言后者。⑥Worker C 需**有界多轮** `--once`（`reliable_new` 先建档→重搜发布，约 2 轮；工装用 `MVP_WORKER_BACKOFF_BASE_SECONDS=0` + `claim_batch=5`，循环上界 60×0.4s），**未改业务、未伪造**。⑦库中**无 `skin_reports` 表**（报告落 `skin_assessments.report_id/report_payload`），故 b40 以「该 gimbal T05 行数=1 + `report_ready` 行=1 + 快照逐值一致」等价断言「members、报告行数不变」。

### 13.11 当前门禁状态（截至最终代码 SHA `8343ba5a4dd9ee611da979617d2982943fc61af9`）

- **`f4b9546` 未通过 Oracle 门禁（`VERDICT: FAIL`，明确"不可合入 dev"）**；该结论**不被沿用**，最终以新 SHA 的复审为准。
- **已闭合**：BLOCKER（SC-02-09 改为真实迟到返回 barrier，`181676d`；端到端 b40，`8343ba5`）、IMPORTANT（严格布尔解析，`40f5fde`）、2 项 SUGGESTION（EOF 空行 `d312d2a`、12-vs-13 计数更正见 13.6.1）；并按总协调新增第 7 项 **SC-02-10**（确定性终态失败，`181676d` + 端到端 b41，`8343ba5`）。
- **已完成的全量验证（orchestrator 亲自执行，绑定 `8343ba5`）**：端到端工装 **`ALL PASS 41/41`、`SCRIPT_RC=0`**（b1–b39 无回归；b36 Java **419/0/0**；b37 Python **291 passed**；b39 HEAD 未变）；我另独立亲跑 **pytest 291 passed rc=0** 与守卫 CLI 七组、Oracle 指定 4 条命令、严格红线 grep（`providers.py` 无 DB API；工装新增区无业务表写入）。跑后 18083/18084 空闲、无我方遗留 JVM/worker。
- **Oracle 第十一轮对 `8343ba5` 判 `VERDICT: PASS-with-notes`，明确"可以合入 dev"**：21 项逐条裁定全部闭合/通过（BLOCKER 与 IMPORTANT 与 2 SUGGESTION 均确认闭合），并判定 **SC-02-09 与 SC-02-10 的注入能力已就绪、可由 E 黑盒驱动**（b40 已证明真实 HTTP、lease 回收、接管、v2 完成与旧执行迟到围栏；SC-02-10 可在首次实际 worker 执行中稳定进入既有 `PROVIDER_CONTRACT_VIOLATION` 终态并由 HTTP 读取安全投影）；**最终场景 PASS 仍由 E 的 matrix 独立结算，B 不代宣**。完整记录见 `B-oracle.md` §4.14。
- **但 Oracle 同时给出 3 项新 IMPORTANT + 1 SUGGESTION**，判其"不改变生产业务正确性、不构成合入阻塞，**但前三项应在 E 最终矩阵结算前修正或明确接受测试约束**"：①`b-checks-3.sh:481-488` b40 **忽略 Worker A 退出码**且日志正则过宽（允许任意 `StaleGeneration` 字样或 DEBUG 事件）⇒ A 崩溃非零退出时 b40 仍可能通过；②`test_seam_boundary_repro.py:392-406` 与 `b-checks-3.sh:526-529` 以 `owner_id=assessmentId` 计数**不能**证明无 `identity.enroll`/`plan.generate` 后继（两类后继用**不同 owner_id**）；③`providers.py:163-166`/`dconfig.py:394-469` barrier 启用时 `DIR` 可为空并**回退共享 `/tmp/mvp-double-late-barrier`**，未强制 RUN_ID 隔离 ⇒ 并跑实例互相消费 sentinel；④timeout 非数字抛裸 `ValueError`，异常类型不统一。
- **orchestrator 处置：四项全部修，不接受"明确接受测试约束"**。理由：前三项都属**可能导致假 PASS 的证据完整性缺陷**（其一可把崩溃的被测进程记为通过、其二使"无脏后继"断言实际无判别力、其三使并跑实例互相污染），与本项目"绝不把受控替代或伪造效果当真实、要求独立验证"的一贯要求直接冲突；四项全在 B 自有写域（工装 + 注入缝 + 定向测试），不触碰业务代码。**修复中，未交付。**
- **最终门禁状态（已闭合）**：Oracle 对 **`11e42c8ea29c97312059cab886f39c5c3418e8f8`** 的窄范围重绑定判 **`VERDICT: PASS-with-notes`**，六点全部闭合、**新发现：无**，明确 **"可以将 `11e42c8` 作为本轮最终交付 SHA 合入 dev"**、**"不要求再次重跑端到端验收"**（orchestrator 已在该精确 SHA 上亲跑 `ALL PASS 41/41`、`SCRIPT_RC=0`），并确认 **SC-02-09 与 SC-02-10 的注入能力仍可由 E 黑盒驱动、最终场景结算仍由 E matrix 独立负责**。
- **轮次边界声明（Oracle 原文）**：**"`11e42c8ea29c97312059cab886f39c5c3418e8f8` 为本轮最终交付 SHA；无需再因测试断言精度或文档措辞发起新的重新绑定轮次。只有 E matrix 发现新的实际行为缺陷，才需要重开代码审查。"**
- **本轮最终交付 SHA = `11e42c8ea29c97312059cab886f39c5c3418e8f8`**；提交链 `5bd22d3` → `7524714`(Java 存储缝) → `9b3d802`(Python 7 旋钮) → `f4b9546`(测试端口冲突) → `d312d2a`(EOF) → `40f5fde`(严格布尔，闭合 IMPORTANT) → `181676d`(barrier + SC-02-10) → `8343ba5`(工装 b40/b41) → **`11e42c8`**(四项证据完整性修复)。相对 `5bd22d3` 共 **15 文件 / +2820 −14**，`git diff --check` **rc=0**。Oracle 共 **3 次实际调用**（`f4b9546` FAIL → `8343ba5` PASS-with-notes → `11e42c8` PASS-with-notes 重绑定），全部为真实只读审查并给出可核查的 `文件:行` 与命令清单。
- **纪律**：B **未合并、未推送、未归档**；三份交付文档以 report-only 提交入库（`git diff 11e42c8..HEAD` 对全部代码目录为空）；E 只在总协调合入后验收，**B 不代 E 宣布任何场景 PASS**。

### 13.12 四项证据完整性修复（`11e42c8`）与负向验证

| # | Oracle 原判定 | 修复 |
|---|---|---|
| 1 | **IMPORTANT** `b-checks-3.sh:481-488`：b40 **忽略 Worker A 退出码**，日志正则允许任意 `StaleGeneration` 字样或 DEBUG 事件 ⇒ A 崩溃非零退出时仍可能假 PASS | `wait … \|\| a_rc=$?` 后**断言 `a_rc==0`**（非零则打印 A 日志尾部并 `fail`）；日志判据收紧为**精确** `"event": *"job.complete_stale_generation"`（移除 DEBUG `analyze.fenced_write_stale` 与裸字样匹配）；**新增**"A 日志不含 `Traceback (most recent call last)`"断言；既有断言（v2 快照逐值未变、`report_ready`=1、T05 行=1、`members` 不变、sentinel 无残留）**全部保留** |
| 2 | **IMPORTANT** `test_seam_boundary_repro.py:392-406`、`b-checks-3.sh:526-529`：`owner_id=assessmentId` 计数**不能**证明无 `identity.enroll`/`plan.generate` 后继（两类后继用**不同 owner_id**） | 改为按真实 schema 四路判别：`assessment.analyze` 按 `(job_type, owner_id)` 恰 1（+`attempt_count=1`、`last_error->>'retryable'=false`）；`identity.enroll` 按 `payload->>'assessment_id'`=0；`care_plans WHERE assessment_id`=0；`plan.generate` 经 `JOIN care_plans ON j.owner_id=p.id`=0。另加**判别力测试** `test_successor_job_assertions_have_discriminating_power` |
| 3 | **IMPORTANT** `providers.py:163-166`、`dconfig.py:394-469`：barrier 启用时 `DIR` 可空并**回退共享 `/tmp/mvp-double-late-barrier`**，未强制 RUN_ID 隔离 ⇒ 并跑实例互相消费 sentinel | `__post_init__` 的 barrier 分支：`DIR` 空/未设 → **加载期 `ProviderConfigError`**（`barrier=true requires an explicit dedicated directory (per-RUN_ID isolation; no shared default allowed)`）；`default_late_barrier_dir()` 收窄为**仅供显式构造/测试**，env 装配路径绝不使用；新增 `test_barrier_enabled_requires_dir_sha_and_timeout`（缺 DIR/缺 sha/非 hex/timeout<1/齐备五情形） |
| 4 | **SUGGESTION** `dconfig.py:162-164,400-403`：timeout 非数字抛裸 `ValueError`，异常类型不统一 | 新增 `_strict_env_int(name, default, *, minimum)`：非数字与越界均转为含变量名与 `expected integer >= {minimum}` 的 **`ProviderConfigError`**；barrier timeout 字段改用之；新增 `test_barrier_timeout_non_numeric_fails_fast` |

**负向验证（关键：证明收紧后的判据有判别力而非恒真；三次临时缺陷均已完全还原）**
- 临时把 A 的真实 WARNING 事件重写为 DEBUG `analyze.fenced_write_stale` → b40 **FAIL**：`ASSERT-FAIL: A 日志缺既有 WARNING job.complete_stale_generation`、`SCRIPT_RC=1`（**旧宽松正则本会匹配并通过**）
- 临时向 A 日志追加 `Traceback (most recent call last)` → b40 **FAIL**：`ASSERT-FAIL: A 日志含未处理异常 traceback`、rc=1（**旧无此断言**）
- 临时强制 `a_rc=9` → b40 **FAIL**：`ASSERT-FAIL: Worker A 退出码=9（期望 0）`、rc=1（**旧忽略退出码**）
- 修复 2 的判别力：临时插入一条 `plan.generate`（`owner_id=plan_id`、payload 指向同 assessment）→ 实测 `old_owner_id_count=1`（**旧断言被骗过、会假 PASS**）而 `new_care_plans_count=1`、`new_plan_join_count=1`（**新断言命中**）；随后显式 DELETE 并断言 `left_jobs=0, left_plans=0`
- **零泄漏核实**（orchestrator 独立 grep）：交付文件中 `TEMP-NEG|TEMP_NEG|neg-fix|intended.sh` **零命中**；还原基准 `b-checks-3.intended.sh` 仅存于 gitignored 运行目录、**未进入暂存面**（工件计数 0）

**orchestrator 独立核验（绑定 `11e42c8`）**：写域恰 4 文件；业务文件（`assessment_analyze`/`plan_generate`/`identity_enroll`/`dmedia`/`runtime/**`/`handlers/__init__`/`media/storage`/`notifications/**`）、任何 Java `src/main/**`、`run-acceptance-b.sh`、`acceptance/**`、`contracts/**`、迁移、`deploy`、`handoffs/**` 的 **diff 全空**；我亲自读码确认 `__post_init__` 的 barrier 三重校验（DIR 非空、timeout≥1、sha256 为 64-hex）确实存在（此前一次 grep 未命中只因消息被 f-string 拆行）；**全量 pytest 293 passed / 0 failed / 0 errors，rc=0**（基线 291+2）；**完整工装 `ALL PASS 41/41`、`SCRIPT_RC=0`**（b40/b41 PASS、b36 Java 419/0/0、b37 Python 293、b39 HEAD 未变）；守卫 CLI 五组（缺 DIR→rc=1、合法 DIR→rc=0、`TIMEOUT_SECONDS=abc`→rc=1 且为 `ProviderConfigError`、production+barrier→rc=1 列出 3 个 switches、production+全默认→rc=0）；`git diff --check 5bd22d3..11e42c8` **rc=0**；本轮总变更面 **15 文件 / +2820 −14**；跑后 18083/18084 空闲、无遗留进程、`mvp-b-pg` Up。
- **纪律**：B 不自行合并、不推送、不归档；E 只在总协调合入后验收；场景最终结算（含 SC-02-09/SC-02-10 由 `seam_pending` 转 PASS）由 **E 在其 matrix 中完成**，B 只提供能力与自证，**不代 E 宣布 PASS**。
- 交付物 `backend/handoffs/B-seam-repro.md`（总协调要求随交付提交、不得只放 gitignored 目录）已补齐全部内容，随 report-only 提交入库。

## 14. Swagger 联调注释轮（总协调确认启动条件满足后指派；最终代码 SHA `fb342a67e7c613cdc9c24ec6fcb74b9f68dbcacb`）

### 14.0 授权与基线同步
总协调确认启动条件满足（E 61 项业务全通过、实际 Oracle R24 绑定 `377e3eb`、最新 dev `76cd426e912096971b6e1c387995d875cf2cce70` 已集成后续证据报告），指派 B 为唯一实施负责人，复用本 orchestrator 一次增量实施。范围：为**实际 springdoc 生成**的面向 APP/云台外部 HTTP 接口补齐中文用途、鉴权、字段含义·类型·必填·单位·枚举、脱敏示例、业务错误码与 HTTP 码、幂等、调用前置与顺序；覆盖登录/图片上传/测肤/方案/执行/进度/绑定通知等联调接口；**不新增业务接口**；大 JSON 明确结构**及可扩展边界**；**不能只改手写 OpenAPI**；优先注解/schema 配置；核对**实际** `/v3/api-docs` 输出；针对性测试 + 最终实际 Oracle 有界复审；不合入 dev、不推送。
同步：`git merge` 为**快进式、0 冲突**，HEAD == 指定的精确 dev SHA；`.coordination/B-work`（1.9M）保留；我的三份既有交付文档 blob 未变；dev 领先的 26 个提交**业务代码 diff 为空**（仅 E 的验收资产与报告）。

### 14.1 架构决策：全集中式文档目录（零业务代码改动）
文档内容写在 **5 个 `ApiDocsCatalog` bean**，由引擎 `docs/ApiDocsApplier.java` 在 springdoc **生成之后**施加到 OpenAPI 对象；**未使用任何 `@Operation`/`@Schema` 注解、未改任何控制器或 DTO** ⇒ diff 只落 `web/docs/**`，"序列化与业务行为零变更"可一句话证明。理由：①避免 34 操作 × 约 8 个错误码 ≈ **270 处 `@ApiResponse`** 的注解爆炸；②避免改 C/D 包 DTO 的跨包归属与并行冲突；③用**覆盖率门禁**强制"新端点未写文档即构建失败"，约束强于注解；④错误码集合与契约 `x-error-codes` 交叉校验（snakeyaml 动态读取、不硬编码）防漂移。
冻结的目录契约（orchestrator 编写并先编译验证）：`catalog/ApiDocEntry.java`（含 `ParamDoc`/`MultipartPartDoc`/`SuccessDoc` 四形态 `json`/`jsonList`/`noContent`/`binary`）与 `catalog/ApiDocsCatalog.java`（含 `PropertyDoc`/`FreeFormDoc`）。三条硬纪律写进类型契约：**键必须为 `"METHOD path"`**（生成文档存在 `create`/`create_1`/`create_2`/`get`/`list`/`task` 等歧义 operationId）、**成功码必须真实**、**自由结构必须写明可扩展边界与"哪些内部诊断键绝不外发"**。
派发结构：阶段 1 引擎道（单道独占构建）→ 阶段 2 四条目录道并行（**全部禁跑 mvn**，由我统一构建，避免 `target/` 互相破坏）→ 阶段 3 我中央构建、门禁、量化、回归、提交、送审。

### 14.2 修掉的基线文档缺陷（比"缺描述"更严重，会直接误导联调）
1. **34 个操作的响应码全部被生成为 `200`**，而真实存在 **201**（创建授权、执行登记）、**202**（测肤受理/补拍受理）、**204 无体**（撤销授权/解绑/登出）⇒ 已按真实码生成（最终 2xx 集合 `{200,201,202,204}`）。
2. **`POST /api/v1/member-access-grants` 的 requestBody 被误建模为 `PrincipalContext`**（鉴权主体类）——该端点与 M3-A01/A02 用 raw request 手工解析 multipart，springdoc 看不到 part ⇒ 已用 `multipartParts` 重建为 `{metadata: $ref M1A01Metadata, face: binary}`，`PrincipalContext`/`SuccessEnvelope`/`ListData` 均被引擎修剪。
3. **34 个端点的 `data` 全是无结构 object**（`SuccessEnvelope.data` 为 `Object`）⇒ 已类型化（含**嵌套 record** 递归注册）。
4. **列表端点泛型擦除**：`ListData<T>` 是 record 不可继承、裸类会让 `items` 退化且条目 DTO 不注册（进而使条目 `propertyDocs` 被 `unknownPropertySchemas` 判错）⇒ 扩展冻结接口增加 `listItemClass` + `jsonList(...)`，引擎构造 `data={items: array of $ref(条目), nextCursor: string|null}`；4 个列表端点全部生效。
5. **5 个自由结构字段**全部处置：4 个为**显式不透明声明**（`MicrocrystalObservationBody.state`、`M4A04Metadata.reportedMicrocrystalState`、`AppSessionRequestBody.installBindingMaterial`、`SkinReportListItem.reportSummary`——均**无任何可取证的键，拒绝编造**），其余按写入方/投影方白名单展开（`SkinReportView.metrics` 仅 `name/value/unit`；`CarePlanProjection` 三套白名单；`capabilities` 仅 `schemaVersion`/`revision` 可取证；`ErrorBody.details` 的 12 个合法键按 code 说明）⇒ **无结构自由字段由 5 降为 0**。
6. **0 示例 → 221 个属性示例 + 多处 free-form 示例**，全部脱敏（合成 UUID、占位号段 `+8610000000000`、`*-placeholder`；无真实 token/手机号/推送凭据/人脸数据/内部诊断）。

### 14.3 量化对比（orchestrator 亲自抓取真实 `/v3/api-docs`）
| 指标 | 基线 | 最终 |
|---|---|---|
| 文档体积 | 26482 字节 | **413366 字节** |
| 操作数 | 34 | **34**（未新增接口） |
| 有中文 summary / description | 0 / 0 | **34 / 34** |
| 声明 ≥1 个 4xx/5xx | 0 | **34** |
| 带 `x-error-codes` | 0 | **34** |
| 参数有描述 | 0 / 59 | **59 / 59** |
| schemas / 属性 | 20 / 80 | **62 / 266** |
| 属性有描述 | 0 / 80 | **266 / 266** |
| 枚举属性 / 示例 | 2 / 0 | **32 / 221** |
| 顶层 tags | 0 | **12**（中文业务域分组） |
| 2xx 状态码集合 | `{200}` | **`{200,201,202,204}`** |
| 无结构自由字段 | 5 | **0** |
| 公开端点 `security:[]` / `bearerAuth` | 4 / ✓ | **4 / ✓（不回归）** |

### 14.4 覆盖率门禁（防腐化机制）与我对它的两处修正
`ApiDocsCoverageIT` 断言**实际生成**的 `/v3/api-docs`：34 操作全有中文 summary/description 与 tag、每操作 ≥1 个 4xx/5xx 且业务码集合与契约 `x-error-codes` **完全一致**、成功码与契约一致、59 参数全描述、所有 schema 属性全描述、时间属性 `date-time`/RFC3339、自由结构"已展开**或**显式不透明声明"、示例 schema ≥5、security 与 27 契约路由不回归。该门禁在目录补齐前如实失败 **639 项** → 四道交付后 **43 项** → 我补齐共享信封并修两处缺陷后 **0 项**。
- **缺陷 1（多行中文误判）**：原用 `value.matches(".*[\\u4e00-\\u9fff].*")`，因 `matches` 锚定整串且 `.` 默认不匹配换行 ⇒ **任何多行中文 description 都被判"无中文"**（症状：34 个 description 全失败而单行 summary 全通过）。改为 `CJK_PATTERN.matcher(value).find()`。
- **缺陷 2（关键词判定可被骗过）**：原 `classifyFreeForm` 以自由文本关键词（不透明/未冻结/不得依赖任何具体键/未知键）判定"显式不透明"，而某负向夹具的描述恰为"普通数组描述（无任何**不透明/未冻结**表述）"⇒ 字面命中关键词而被误判 `EXPLICIT_OPAQUE`（该负向用例正确地抓住了它）。改为只认引擎注入的**规范标记** `OPAQUE_MARKER`（`【显式不透明对象】`），并新增"含关键词但无标记 → `NOT_DECLARED`"的回归用例。两处修正均为**收紧**，未弱化任何断言；且 `OPAQUE_MARKER` 重构后文档产出**逐字节相同**（两次抓取比对为 True），证明是纯常量提取 + 判据收紧。

### 14.5 orchestrator 本轮自身错误（如实记录，供后续会话避免重犯）
1. `lane-assignments.md` 中 `POST /api/v1/system/echo-jobs` 误写"201/200"（控制器恒 `ResponseEntity.ok`、契约仅 200），M3-A01/A02 误写"仅 202"（契约同时声明 200 与 202）⇒ 两处均以**代码与契约为准**采纳子道判断。
2. **漏传 Java 测试库 env** 导致误判：首次核验子道自报数字时未传 `MVP_A_PG_JDBC/USER/PASSWORD`，测试基建去连**禁用的 55432**，三个 `@SpringBootTest` 上下文加载失败（表现为 `Errors` 而非 `Failures`），一度看似与子道自报矛盾；带正确 env 重跑后**完全复现其数字**，错在我不在它。已写入长期记忆。
3. **相对路径重定向**致 jar 未重建：在子 shell `cd backend/web-java` 后仍用相对 `$W` 写日志 ⇒ 重定向失败、`package_rc=1`、jar 停留在旧包；我据旧包的输出误称"系统性引擎问题"，实际生成文档完全正常。改绝对路径后真相立刻显现。
4. 我新写的 `CommonEnvelopeApiDocs.java` 有**两个真实编译错误**：Java 字符串字面量内用了**半角双引号**（`等价于"核验通过"`）致字面量提前终止并引发级联误报；`knownKeys` 用了 **12 对** `Map.of`（上限 10 对）⇒ 改 `Map.ofEntries`。
5. 修门禁时**引用了未声明的 `CJK_PATTERN`**（只改判定行未加常量与 import），靠 LSP 即时发现并补齐。

### 14.6 验证（orchestrator 亲自执行，绑定 `fb342a6`）
- `mvn -B test` 全量：**432 run / 0 failures / 0 errors，BUILD SUCCESS**（基线 419 + 引擎单测 12 + 门禁 1）；文档相关五类全绿（`DocsProductionGuardTest` 7、`ApiDocsCoverageIT` 1、`OpenApiDocsDisabledIT` 1、`ApiDocsApplierTest` 12、`OpenApiDocsIT` 3）
- 真实 `/v3/api-docs` **HTTP 200 / 413366 字节**、`/swagger-ui/index.html` **200**；量化见 14.3
- 端到端工装 `bash backend/tests/run-acceptance-b.sh`：**ALL PASS 41/41、`SCRIPT_RC=0`**（b36 Java 全量、b37 Python 全量、b40/b41 注入缝、b39 HEAD 未变 ⇒ **业务行为零回归**）；跑后 18083/18084 空闲、无遗留 JVM
- 写域：**12 文件全在 `web/docs/**`**（main 10 + test 2），+5606/−53；任何控制器/DTO/业务服务/`ErrorCode`/`GlobalExceptionHandler`/信封类/`ListData`/`application.yml`/`pom.xml`/契约/`acceptance`/`backend/tests`/`worker-python`/迁移/`deploy` **diff 全空**；`git diff --check 76cd426..fb342a6` **rc=0**；暂存面 0 工件
- 资源：只用 `mvp-b-pg`@55435 与 18083；临时实例用毕 kill；**未启动常驻预览**；未触碰 18080/3000/E 资源/`swagger_preview`；未停 PG、未清库卷

### 14.7 交付物与待裁定
- **联调指南**：`backend/handoffs/B-api-integration-guide.md`（342 行，10 节：总览与通用契约 / 鉴权与幂等 / 错误码总表（29 码，由 `ErrorCode`+`ErrorCodeDocs` **脚本自动生成**并按 HTTP 状态分组，含"语义·触发条件·客户端动作"与 `details` 合法形态表）/ 接口分组与真实状态码 / 三条主调用链与前置 / 术语统一表 / 未冻结清单 / 生成文档已知限制 / 本地查看方式与端口纪律 / 相关交付物）。
- **两个契约缺口（未自行改契约，已在文档标注待裁定）**：①`PROVIDER_CONTRACT_VIOLATION` 已实现且会经 M3-A03 的 `failureCode` 外发，但不在契约 `ErrorCode` enum 与 DD 3.2；②`POST /api/v1/auth/sessions` 对停用账号抛 401 `SESSION_INVALID`（`AuthController:181`），但契约 f02 的 `x-error-codes` 未声明（其它 32 个操作均声明）。
- **契约过声明**一律"逐字转录 + description 注明当前实现不触发"，**未删减**（M2-A02 的 `TASK_REPLACED`；M3-A04/A05 与 M4-A01/A02/A07/A08/A09 的 `GRANT_REVOKED`；M4-A03..A08 的 `CALLER_NOT_ALLOWED`；M4-A03/A05 的 `BINDING_CHANGED`；M4-A04 的 `RECORD_CONFLICT`；M4-A02 的 `PLAN_NOT_READY`；M2-A01 的 `SESSION_INVALID`/`IDEMPOTENCY_CONTENT_CONFLICT`；f05 的 `CALLER_NOT_ALLOWED`）。
- **已知文档限制**：multipart 的**条件必填无法表达**（A02 图片 part 实际按 `replacedViews` 条件必填，但引擎对每个 part 都置 required ⇒ 以 description 为准）；`PropertyDoc` 无法表达属性级 `required`（如 `EchoJobRequestBody.numbersAsStrings` 契约必填、代码未强制）；空壳 `JsonNode` schema 保留（被 2 个不透明字段 `$ref`，属性自身已带完整声明，OpenAPI 3.1.0 下 `$ref` 同级关键字有效）。
- **实现与契约的其它差异按源码事实书写**：`reportedMicrocrystalState` 实际只做"对象或 null"校验并参与 T13 canonical payload 哈希、**未写入 T07 快照**；`VerificationDto.validUntil` 当前恒为 null；契约 `ExecutionClosureResult` 的 `pendingReconciliation`/`missingRanges`/`more` 在实现 DTO 中不存在（缺口经 `CLOSURE_GAPS` 的 `details` 表达）；`MissingRangeDto` 不会被注册故未登记 propertyDocs。
- **门禁状态**：首轮提交 `fb342a6` 经实际 Oracle 有界复审判 **FAIL**（见 14.8），整改后最终代码 SHA = `9b5ed34a6bd669ebc4726681cb92847264b3a18e`，第二轮复审进行中；**判定前不得合入 dev**；B 不自行合并、不推送、不归档。

### 14.8 Oracle 首轮 FAIL（`fb342a6`）：7 项发现的核实、裁定与整改（最终代码 SHA `9b5ed34`）

Oracle 有界复审判 **VERDICT: FAIL**（2 BLOCKER + 5 IMPORTANT，明确"不可合入 dev"）。我**逐条读码核实，7 项全部成立**，其中一条与实施子道的"已取证"结论直接冲突，由我裁定**子道取证有误**：

| # | 严重度 | 发现 | 我的核实证据 | 整改 |
|---|---|---|---|---|
| 1 | BLOCKER | multipart 把所有 part 标为必填，而 A02 的图片 part 实为**按 `replacedViews` 条件必填** | 生成文档 A02 `required=['front','left','metadata','right']`，而契约 `required=['metadata']`；`AssessmentMultipartParser:76-88` 要求 `replacedViews` 非空/∈front,left,right/不重复 | 冻结接口 `MultipartPartDoc` 增第 6 组件 `required`（保留 3 参工厂默认 true ⇒ 零目录破坏）；引擎 `:299` 按 part 施加；A02 三图改 `binary(...,false)` |
| 2 | BLOCKER | `SkinReportListItem.reportSummary` 被**虚假声明**为"无可取证键"的不透明对象 | **写入方** `assessment_analyze.py:412-417` 固定构造 `{schema_version:1, conclusion, headline_metrics[:8]}`，`SkinReportService.java:87` 原样外发 | 列入三键（含"最多 8 项""指标名集合未冻结"），`extensible=true`，删除已被推翻的表述并注明键取自写入方 |
| 3 | IMPORTANT | 登出被错称"同事务" | `AuthController:136` 在会话撤销后调用；`:203-214` 是 autocommit 单条 UPDATE 且 try/catch 吞异常，注释明写"撤销已生效；目标失效可后续补偿，**不反转登出**"；控制器无 `@Transactional` | 改为"先撤销会话（不在 DB 事务中）；T09 的 status+revision 在单条 PG UPDATE 内原子；**两者不是同一事务**；失败按 DD 4.1 幂等补偿" |
| 4 | IMPORTANT | 媒体策略描述过时（称生产 deny-all、dev 可走 owner 便利） | `BusinessMediaAccessPolicy:66-67` 为 `@Component @Primary`，javadoc 自称"唯一业务策略，覆盖 A 的 deny-all 默认"；dev 旁路已在注入缝轮**全删**，`MediaPolicyNoDelegationIT` 在 `owner-dev` 下断言上传者仍 404 | 整段替换为真实五步判定，并明确"原 deny-all 不再生效、便利旁路已全部移除" |
| 5 | IMPORTANT | `EchoJobRequestBody.numbersAsStrings` 契约必填却写成"可选" | 契约 `SystemEchoJobRequest.required=['message','numbersAsStrings']`；代码未以注解强制 | 接口新增 **default 方法** `requiredProperties()`（加法扩展：目录中有 29 处 `new PropertyDoc(...)`、16 处 `new FreeFormDoc(...)`，故不给 record 加组件）；引擎 `:110-160`/`:204`/`:449-476` 施加并 fail-fast（新增 `unknownRequiredProperties`）；三个目录据实声明 |
| 6 | IMPORTANT | 门禁可被冒充 + 只查硬编码 5 字段 | 原 `classifyFreeForm` 用自由文本关键词判定，夹具描述"普通数组描述（无任何**不透明/未冻结**表述）"竟被误判为已声明；`FREE_FORM_FIELDS` 为硬编码 | ①只认引擎注入的规范标记 `OPAQUE_MARKER` + 新增"含关键词无标记→NOT_DECLARED"回归；②删硬编码，改**动态扫描全部**属性（新增 `isUnstructuredObject`，覆盖 object 空壳/`$ref` 空壳/array.items 空壳）；③新增 **`APPROVED_OPAQUE_FIELDS` 核准清单（恰 3 项）**，清单外声明即失败、清单项非不透明也失败；④新增**契约 required 交叉校验**（multipart part + 请求体 schema，含生成名↔契约名映射；少于=须修正、多于=invent，皆失败） |
| 7 | IMPORTANT | `capabilities.schema_version` 被写成"服务端当前写 1" | `MicrocrystalService.buildCapabilities(requested, schemaVersion, revision)` 把它置为**请求中已校验的 `schemaVersion`**（可 >1），并跳过 requested 同名键 | 改为"从已校验的请求 `schemaVersion` 映射写入（整数 ≥1，可大于 1），不是固定常量"；`Request.registration` 的 `schema_version`（确为缺省注入 1）**未改** |

**我对第 2 项的裁定（子道取证有误，非 Oracle 误判）**：子道以"`SkinReportService.listReports` 仅 `parseJson` 原样返回、未读取任何固定键"推断"无经取证的键可列"，这是把**读取方不解析**误当成**结构不可取证**；键的权威来源是**写入方**。我已把该根因写入其整改任务书要求复盘。
**我对第 5 项的关键区分**（避免修出新的失真）：`A01Metadata`/`A02Metadata`/`M1A01Metadata`/`Capture` 的必填字段**服务端确实强制**（`AssessmentMultipartParser:60-64,73-88`；`MemberAccessGrantController:162-170,197-203,207-210` → 400 `INVALID_INPUT` + `details.fields`），只是未用 Bean Validation 注解 ⇒ javadoc 明写"**这不是实现偏差**"；只有 `numbersAsStrings` 属"契约必填而代码不强制"的**真实现偏差**。两者混为一谈会造成新的文档失真。

**整改后的验证（orchestrator 亲自执行，绑定 `9b5ed34`）**：`test-compile` rc=0；定向 `ApiDocsApplierTest` **15/0/0**（12+3 新，含拼错 schema 名/属性名两个负向）、`ApiDocsCoverageIT` **1/0/0**、`OpenApiDocsIT` 3/0/0、`OpenApiDocsDisabledIT` 1/0/0、`DocsProductionGuardTest` 7/0/0；**全量 `mvn -B test` 435 run / 0 failures / 0 errors**（`fb342a6` 为 432 + 3 新单测）；硬化门禁由 4 项 → **0 项**；真实 `/v3/api-docs` **200 / 415676 字节**，逐项复核 7 项发现**已在输出中闭合**（A02 `required=['metadata']`、A01/care/revalid/grant 与契约逐个吻合；`reportSummary` 含三键且无不透明标记；5 个 schema 的 required 与契约相符；"当前为 1"与"留痕"出现 **0** 次；`deny-all`/`owner-dev`/`any-authenticated` 仅出现在"不再生效/已移除"的**否定句**中；核准不透明集恰为 3 项；无结构自由字段 0）；**全量 `$ref` 384 个、0 悬空**；`JsonNode`/`PrincipalContext`/`SuccessEnvelope` 均已修剪；写域 **12 文件全在 `web/docs/**`**、`git diff --check` rc=0。
**本轮未重跑 41 项端到端工装**：依据 Oracle 上轮明示"若只改 docs/test 可不重复"，且变更全部落在 `web/docs/**`（diff 可证）、业务回归证据为全量 Java 435/0/0（含全部业务 IT）、Python 侧未触碰；该省略已请 Oracle 在第二轮裁定。

**orchestrator 本轮新增的三处方法论错误（如实记录）**：
1. **两次相对路径错误**（同一根因，第三次重犯）：`cd backend/web-java` 后仍用相对路径写日志/读文件——第一次致 jar 未重建、我据旧包输出误称"系统性引擎问题"（实为我的构建失败）；第二次致量化脚本 `FileNotFoundError`。
2. **计数式检查未看极性**：用 `grep -c` 判断"错误陈述是否消失"，见 `deny-all`/`同事务` 仍有命中便以为未修；实际它们出现在**否定句**中（"原 deny-all 不再生效"）或属**另外的正确陈述**（T09 单条原子 UPDATE、Worker 同事务发布报告）。已改为打印上下文逐条判极性。
3. **误报悬空 `$ref`**：用 `count('/JsonNode')` 得 1 便断言存在悬空引用，实为 `info.description` 散文中 "Object/Map/JsonNode" 被命中；经**全量 `$ref` 完整性校验**（384 引用、0 悬空）证伪。

**编排异常（如实记录）**：本轮两条实施道（引擎+门禁道、C4 道）一度**不在 Board 的 Active 与 Reusable 任何列表**、`task_status` 对其别名返回 "Unknown task ID or alias"，但其写域磁盘 mtime 显示**仍在活跃写入**。我据此**拒绝**回退或派重复道（本会话早期曾因轻信同类信号回退他人在飞工作），改用"文件指纹静置探测（3 点 / 约 200 秒）+ 我亲自构建与跑测试"作为权威判据；两条道的终结结果随后均正常送达，证实为簿记滞后而非任务死亡。

### 14.9 Oracle 第二轮 FAIL（`9b5ed34`）：嵌套自由结构退化为 `array<string>`（第四轮整改进行中）

Oracle 对 `9b5ed34` 判 **VERDICT: FAIL**，但范围显著收窄：**原 7 项全部确认闭合**（逐条给出 `文件:行`），并采纳我的两项决策——清除 `$ref` 可接受（展开后 inline schema 成为机器可见结构、无悬空引用、`JsonNode` 修剪合理）、**本轮不重跑 41 项端到端工装可接受**（增量仅 `web/docs/**`，435 项 Java 全量 + 真实抓取即适当验证）。新发现 1 BLOCKER + 2 IMPORTANT + 1 SUGGESTION：

- **BLOCKER**：`knownKeys` 只能表达一层类型，`keySchema()` 的 `case "array" -> new ArraySchema().items(new StringSchema())` 使**自由结构对象内部的任何数组键退化为 `array<string>`**，与真实响应冲突并误导 Swagger UI 与代码生成器。我实测生成文档确认 6 处：`CarePlanFullView.plan.steps`、两个 `planExecution.steps`（实为 `array<object{region,parameters}>`，权威源 `CarePlanProjection.projectStep/projectParameters/projectParameter`）、`ErrorBody.details.fields`（实为 `array<object{field,reason}>`，`MemberAccessGrantController:209`）、`ErrorBody.details.missingRanges`（实为契约 `MissingRange={from,to}` 均必填、封闭）；另有 3 处动态映射 `plan.parameters`/`planExecution.parameters` 与 1 处嵌套空壳 `HeartbeatBody.incidents[].detail`。
- **IMPORTANT**：门禁只扫描 component 的**直接属性**，展开字段内部的空 object / 错误 array items 不会被发现（父字段已有 properties 即被判 EXPANDED）⇒ 须递归遍历 inline `properties`/`items`/`additionalProperties`。
- **IMPORTANT**：契约 required 交叉校验只覆盖请求，不覆盖响应 DTO。
- **SUGGESTION**：`AssessmentApiDocs` 的 `metrics.value` 同时写"number"与"数值/文本类型未冻结"，自相矛盾。

**我的补充取证（两点超出 Oracle 的发现）**：
1. **根因更精确**：顶层数组型自由字段（`HeartbeatBody.incidents`、`SkinReportView.metrics`）的 `items` **已正确**为 object 且键齐全；错误只发生在"自由结构对象**内部**的键"经 `keySchema()` 一层 DSL 时。这决定了修法是"为嵌套键提供递归表达"，而非重做自由结构机制。
2. **发现一个 Oracle 未点名的引擎缺陷**：`applyFreeForm` 清除 `$ref` 后**未补 `type`**，致 `SkinReportListItem.reportSummary` 与 `M4A04Metadata.reportedMicrocrystalState` 在生成文档中**缺 `"type":"object"`**（实测 `has type key: False`），而 `MicrocrystalObservationBody.state` 却有 ⇒ 已纳入本轮修复。

**我对 SUGGESTION 的取证修正（比 Oracle 建议更准确）**：投影层 `SkinReportService.projectMetrics` 原样复制、不校验类型，但**上游 Python 契约校验** `assessment_analyze.py:645-648` 强制 `value` 为 `int/float` 且排除 `bool`、并须落在核准范围内，违约即 `PROVIDER_CONTRACT_VIOLATION` 终态失败 ⇒ 报告中的 `value` **必为 number**，未冻结的是**指标语义/单位/取值范围**而非类型。已按此改写（而非简单删掉"未冻结"字样），避免修出新的失真。

**我的接口决策**（我拥有冻结接口）：新增递归 record `KnownKeyDoc`（7 组件 `type/description/properties/items/additionalProperties/additionalPropertiesSchema/example`）与工厂 `str/integer/number/bool/array/closedObject/openObject/mapOf/opaqueObject`，并新增 **default 方法** `structuredKeys()`（与 `freeFormDocs()` 同键空间、内层为顶层已知键 → 递归结构；与 `knownKeys` **按并集施加、同名以 `structuredKeys` 为准**）⇒ 加法扩展，16 处 `new FreeFormDoc(...)` 零破坏。`type` 另支持 **`any`**（不写 type 关键字、仅 description），专为 `projectParameter` 允许的"标量 **或** `{value,unit}`"这类真实联合形态（运行时证据：`cc-05-bodies.json` 中 `"parameters":{"intensity":"3"}` 为裸标量、`"vendor_debug":{"unit":"level","value":"3"}` 为对象），并明令**不得用 `any` 规避取证**。
**我在该决策中犯的错误**：首次实现时试图给 record 加可变私有字段承载 `mapOf` 的值结构，触发 `Instance fields may not be declared in a record class` ⇒ 改为第 7 个组件 `additionalPropertiesSchema`；定向 `javac` 验证接口与我自己的 `CommonEnvelopeApiDocs.structuredKeys()` 均 rc=0。

**Oracle 的 6 条一次性目标判据与轮次边界**：①`plan.steps.items.type == object` 且含 `region`/`parameters`；②动态参数 map 明确 `additionalProperties` 及值边界；③`details.fields`/`missingRanges` 用正确对象 item schema；④门禁递归检查所有 inline object/array；⑤响应 required 与契约同等交叉校验；⑥定向加入"错误 `array<string>` 不得通过"的负向测试。**下一轮只需核验递归自由结构 schema、响应 required 门禁与该负向测试**，已闭合的 7 项无需复审；达到 6 条后无需再因普通文档措辞发起重绑定轮次。
**9/13 可用性**：Oracle 判"上轮两个 P0 已修，但大 JSON 的机器结构仍不准确，故 P0 尚未全部清零"；修完递归 schema 后可支撑 HTTP 流程与 doubles 联调，**真实硬件独立接入仍需设备团队/总协调冻结 10 项**（云台 credential/proof 格式与签名/nonce/防重放/轮换、pairingProof 协议、connectionProof 与连接 generation/有效期、微晶 capabilities 键与类型/单位/范围/版本演进、微晶 state 结构与状态编码、heartbeat incident code/severity/detail 结构、observationEpoch/Seq 持久化与 C25/C26 代次规则、session token 提供方/字段名/TTL/撤销语义、测肤 metrics 名称与单位范围及 conclusion 集合、care plan 的 region/step/parameter 名称与单位）——**不能由文档实现方自行发明**。

**我对判据 ⑥ 的纠正（我的任务书错误，已向在飞道排队投递修正）**：我原要求"目录把对象数组声明成 `array<string>` 时门禁必须失败"，但**仅凭生成文档无法判别**——DSL 产出的 `array<string>` 与合法字符串数组在输出中完全同形。改为把约束前移到**引擎 fail-fast**：`keySchema()` 拒绝裸 `array`/`object` 前缀并报错指向 `structuredKeys()`，新增显式 `array<string>` 前缀供真字符串数组使用；负向测试相应改为"裸前缀 → fail fast"。
**我主动规避的一个风险**：全目录现存 **10 处**裸 `array`/`object` 前缀（`AssessmentApiDocs:596`、`CareApiDocs:926/961/976`、`CommonEnvelopeApiDocs:154/166/181/201/206`、`IdentityDeviceApiDocs:765`，已落盘 `.coordination/B-work/swagger-docs/r4-pending-edits.md`）。在引擎道确认已实现 `array<string>` 之前**不得**改这些文案——否则 `keySchema` 会落到 `default -> StringSchema()`，把字段**静默降级为 `string`**，比原缺陷更糟。

**我为本轮准备的中央验证工装**：`.coordination/B-work/swagger-docs/verify-r4.py`（只读真实 `/v3/api-docs`，逐条核验 Oracle 6 判据 + 我发现的 `type` 缺陷 + 前两轮已闭合项的回归 + 全量 `$ref` 完整性）。**已做判别力自测**：对修复前的抓取跑出 **34 PASS / 22 FAIL**，22 个失败项恰为待修清单（9× `plan.steps`、3× `parameters` 的 additionalProperties、5× `details.fields/missingRanges`、递归扫描精确逮到 4 个空壳、2× 缺 `type=object`、1× `metrics.value` 文案），已闭合项全 PASS ⇒ 该脚本非恒真。自测过程中也暴露并修掉了脚本自身的一个 bug（把属性节点当 schema 名传入致 `TypeError: unhashable type: 'dict'`）。

**状态**：三条道中 C2（`incidents[].detail` → `opaqueObject`，取证 `GimbalHeartbeatService:281-283,304-305` 仅判 `instanceof Map`、不解析内部键；契约 `:2173-2176` 标 `additionalProperties:true` + `x-detail:skeleton`）与 C3（`plan.steps`→`array<closedObject{region,parameters}>`、`parameters`→`mapOf(any)`，逐层取证 `CarePlanProjection:136-236`，并把 `steps`/`parameters` 从 `knownKeys` 移除以消除双重描述）已交付；引擎+门禁道在飞。两条已交付道**各自独立提出同一个接缝风险**：引擎对"数组型自由字段的内层键"与 `any` 类型的落地口径必须与目录假设一致，否则会出现"目录写了但生成文档没变"的静默失效——**该口径由我在引擎道返回后实测裁定，不采信任一方自报**。

### 14.10 第四轮整改落地与最终代码 SHA `7461ce115e2d3690c414db63bcd1bc261b95c8b1`

**接缝风险实测裁定（两条道的假设均被证实正确）**：引擎 `applyFreeForm` 注释固化"数组型自由字段的内层键描述的是**元素对象**的键"（实现为 `prop.setType("array"); prop.setItems(struct)`）⇒ 与 C2 一致；`knownKeySchema` 对 `type == null || isBlank || "any"` **不写 `type` 关键字、仅给 description** ⇒ 与 C3 一致。

**我发现并修复的、Oracle 未点名的缺陷（3.1 序列化层）**：`SkinReportListItem.reportSummary` 与 `M4A04Metadata.reportedMicrocrystalState`（Java 类型均为 `JsonNode`，springdoc 只生成 `$ref`）在真实文档中**缺 `"type":"object"`**，而 `Map<String,Object>` 型的 `MicrocrystalObservationBody.state` 正常。引擎虽已调用 `prop.setType("object")`、单测也断言 `getType()=="object"` 并通过 ⇒ **内存态成功但序列化未输出**。**字节码级根因**：OpenAPI 3.1 的 `Schema31Mixin` 把 `getType()` 标 `@JsonIgnore`，`"type"` 由 `getTypes()`（`Set<String>`）经 `TypeSerializer` 输出；`Schema.setType(String)` 只写 legacy `type`、**不动 `types`**，原 `$ref` 实例 `types==null`；反之 `new ObjectSchema()` 走 `Schema.<init>("object", null)` 会 `addType("object")` ⇒ 正常（引擎自建的列表 `data` 与统一信封在真实文档中带 type，构成反证）。**修法**：不再原地 mutate，改为**整体替换属性实例**（新增 `FreeFormTarget(parent, propertyName, property)` holder、`copySiblingKeywords` 保留 `nullable/readOnly/writeOnly/deprecated/title/format/extensions` 与插入位置）。
**更严重的连带问题是测试代表性**：原回归测试断言内存态 `getType()`，故"生产 JSON 缺 type"时依然绿 ⇒ **虚假保证**。已改为对 `Json31.mapper().writeValueAsString(openApi)` 的**序列化结果**断言，并新增**负向判别力证明**（构造 `new Schema<>().$ref(...)` → 清 `$ref` → `setType("object")` → 序列化后断言 `type` **缺失**，证明新断言能捕获原缺陷而非恒真），另为 `structuredKeysRecursiveBuildAndMerge`、`explicitStringArrayPrefixBuildsStringItems` 补序列化层断言。

**门禁新增的响应侧 required 交叉校验暴露 33 项真实缺口**（生成 required 为空 vs 契约非空）。我裁定**补齐而非降级**（Oracle 判据 5 要求"同等交叉校验"，降级会使门禁成为噪声）。四域据实声明 33 个响应 schema，每条均 snakeyaml 实读契约逐字比对，并**逐字段核实存在性**：全库仅 2 处 `@JsonInclude(NON_NULL)`（`SkinReportView:21` 的 `metrics`、`ErrorEnvelope:17` 的 `details`）且均不在声明集；`AssessmentTaskView.requiredViews` 在非 `needs_retake` 时由 `FailureProjection:88-90` 返回 `List.of()` ⇒ 键恒存在；`GimbalCurrentAssessmentView.currentAssessment` 键恒存在、无当前任务时值严格为 null；Care 域 14 项逐条核对 DB NOT NULL 列与构造路径。接口语义同步澄清：**响应侧 required = "服务端保证该键必然存在"（值可为 null），不是实现偏差**；请求侧才需区分"手工强制但未用注解（非偏差）"与"契约必填而代码不强制（是偏差，仅 `numbersAsStrings`）"。

**我纠正了自己定的一个不可实现判据**：原要求"目录把对象数组声明成 `array<string>` 时门禁必须失败"，但仅凭生成文档无法判别（与合法字符串数组同形）⇒ 改为把约束前移到**引擎 fail-fast**：`keySchema()` 拒绝裸 `array`/`object` 前缀（记入 `invalidKnownKeyTypes`）、新增显式 `array<string|integer|number|boolean>`；连带把 5 处真字符串数组改为 `array<string>`（`headline_metrics`、`regions` ×3、`conflictingRecordIds`），另 5 处裸前缀经核实安全（2 处是 `KnownKeyDoc` 的描述文本、3 处被 `structuredKeys` 覆盖而由引擎跳过）。

**验证（orchestrator 亲自执行，绑定 `7461ce1`）**：`test-compile` rc=0；定向文档测试 **34/0/0**（Guard 7、Coverage 1、DisabledIT 1、**Applier 22**、OpenApiDocsIT 3）；**全量 Java 442 run / 0 failures / 0 errors**（`9b5ed34` 的 435 + 本轮 7）；硬化门禁 **33 项 → 0 项**；真实 `/v3/api-docs` **200 / 423892 字节**；自建校验脚本 `verify-r4.py`（**已做判别力自测**：对修复前抓取为 34 PASS/22 FAIL，失败项恰为待修清单）跑出 **66 PASS / 0 FAIL**，覆盖 Oracle 6 条判据 + 序列化缺陷 + 前两轮已闭合项回归（`plan.steps.items.type=object` 含 `region`/`parameters`、`parameters.additionalProperties` 为 schema、`details.fields.items` 为 `{field,reason}`、`missingRanges.items` 为封闭 `{from,to}`、`incidents[].detail` 显式开放、3 个 `JsonNode` 型字段均带 `type=object`、53/61 schema 有非空 required、属性描述 266/266、示例 221、**384 个 `$ref` 零悬空**）；跑后端口空闲、无遗留进程；整轮相对 dev 基线 **12 文件 / +7224 −53，全部在 `web/docs/**`**，`git diff --check` rc=0。

**orchestrator 本轮的调度误判（如实记录，本会话最实质的一次）**：C3 道（fix-7）派发后 10 分钟无写入、`task_status` 返回 "Unknown task ID"、磁盘 `requiredProperties` 命中 0，我据此判定其已死并**重派 fix-11** ⇒ 造成**同文件重复写者**。实际 fix-7 正处于长时间读码核实阶段（14 个 schema × 契约 + `CareProjections`/`CareQueryService`/`CareLedgerService`/`CareAdmissionService` + `V1__create_tables.sql` 的 NOT NULL 列），11 分钟后正常交付。我随即取消 fix-11 并实测对账：`CareApiDocs.java` 的 `requiredProperties` 方法声明恰 1 次、`import java.util.Set;` 恰 1 次、mtime 仍为 fix-7 交付时刻（04:42:44）、14 个键各命中 2 次系 `propertyDocs()`(:811) 与 `requiredProperties()`(:1070) 各一次 ⇒ **fix-11 零写入、无污染、无需回滚**。教训：对需大量读码核实的任务，"短暂无写入"不构成死亡证据；成本不对称时（多等几分钟 vs 重复写者）应继续等待。随后第 8 次同类信号出现时（引擎道别名不可解析 + 3 分钟无写入），我改用 **260 秒三点指纹探测**，确认其在世且正在跑授权测试（surefire 报告新写入），未再误动。
**本轮我另外三处工具/方法缺陷**：①自建 `verify-r4.py` 首跑即崩（把属性节点当 schema 名传入 → `TypeError: unhashable type: 'dict'`），由判别力自测捕获并修复；②两次"`cd` 后仍用相对路径"导致 jar 未重建（我据旧包输出误称"系统性引擎问题"）与量化脚本 `FileNotFoundError`；③用计数式 grep 判断错误陈述是否消失（未看极性）、并用 `count('/JsonNode')` 误报悬空 `$ref`（实为 `info.description` 散文中 "Object/Map/JsonNode"），经全量 `$ref` 完整性校验（384 引用 0 悬空）证伪。

**门禁状态（最终）**：Oracle 第四轮窄范围复审判 **PASS-with-notes**（详见 `B-oracle.md` §4.16.4），**明确许可把 `c3bf05433276152441eb7e80081c3dffc5fbeb6a` 作为本轮最终交付 SHA 合入 dev**，且**不要求重跑完整端到端验收**；并确认**轮次边界**——无需再因普通文档措辞或断言精度发起新的重绑定轮次。其五项判据全部通过，并**明确撤回**上轮关于 `IncidentView` "应与空 required 集比较"的要求（自证契约仅在 `openapi.yaml:2173-2176`/`:2202-2205` 定义开放 skeleton）、**确认 `any` 应为 6 处**（其"三处"指三种 plan 结构、未计入每种的 `parameters.*` 与 `steps[].parameters.*` 两条递归路径）⇒ 我方两处"带证据顶住、不 invent"的处置均获裁定支持。新发现 2 项非阻塞：47 个 component 缺显式 `type: object`（**且 JSON Schema 并不会由 `properties` 推导出实例必须是对象**，故该文档不得宣称是严格验证契约；本轮明确接受，后续可用 Json31 补齐并加序列化门禁）、4 个 inline component 未同步契约的 `additionalProperties:false`（不阻塞联调）。**9/13 可用性裁定：文档 P0 已清零**，可支撑 APP/云台开发者独立完成 HTTP 流程与 doubles 联调、可供主流代码生成器产出客户端模型与调用骨架，但**不可**作为严格 JSON Schema 验证器或替代权威手写契约；真实硬件协议仍需外部冻结其列出的 10 项。B 不自行合并、不推送、不归档（由总协调集成）。
**交付物**：联调指南 `backend/handoffs/B-api-integration-guide.md`（已按 Oracle 裁定修正一处我自己的不准确表述——原写"JSON Schema 语义下 `properties` 只作用于对象，故语义仍是对象"，正确语义是"不会由 `properties` 推导出实例必须是对象，非对象实例只是不应用该约束"；并补入 `additionalProperties` 未同步的披露与"本文档适用范围"声明）。

### 14.11 Oracle 第三轮 FAIL（`7461ce1`）与第四轮整改（最终代码 SHA `c3bf05433276152441eb7e80081c3dffc5fbeb6a`）

Oracle 判 **FAIL**：其 6 条判据中 **1/6/7/8 已通过**（`plan.steps` 递归结构、裸前缀 fail-fast 负向判别、3.1 序列化缺陷的根因与修法、`metrics.value` 文案），判据 2 基本通过；新发现 **2 BLOCKER + 1 IMPORTANT**。我逐条实读契约与生成文档核实成立：

- **BLOCKER A（我的接口能力缺口）**：`KnownKeyDoc` 无 required 能力、引擎 `knownKeySchema` 从不 `setRequired` ⇒ `ErrorBody.details.missingRanges.items` 缺 `required:[from,to]`，而契约 `MissingRange` 明确两键均必填且封闭 ⇒ **机器契约比权威契约更宽松**，代码生成器会允许客户端漏填。
- **BLOCKER B**：响应 required 门禁**跳过**契约的 inline schema（5 个生成 component），其中 3 个契约明确要求 required 而目录未声明；Oracle 指出"**跳过并打印不等于同等交叉校验**"。
- **IMPORTANT**：`any` 节点无 type 且不受核准清单约束 ⇒ 可绕过递归结构门禁。

**整改（提交 `c3bf054`，7 文件全在 `web/docs/**`）**：①`KnownKeyDoc` 增第 8 个（末位）组件 `List<String> required` 并保留 **7 参委托构造器** ⇒ 既有 10 个工厂与既有目录调用点**零破坏**；新增 `any(desc)`、`closedObject(props, required, desc)`；引擎按声明顺序 `setRequired`，required 含不存在的键 → 新增 `invalidNestedRequired`（含完整路径）并 fail fast。②门禁新增 `CONTRACT_INLINE_RESPONSE_POINTERS` + RFC6901 `resolvePointer` + `crossCheckInlineRequired`（**双向精确集合相等**，pointer 陈旧亦失败）；`RecordWatermark` 从跳过清单移出改为真实比对。③目录据实声明 3 项，且**契约 required 不含 `reportId` 故未声明**，并把该字段描述补为"未就绪时为 null 但**键仍存在**、客户端不得依赖其非空"。④`APPROVED_ANY_PATHS` 采用**精确集合成员判定**——实施道提出并说明理由（我原建议的模式匹配会顺带放行未来任何 `Foo.plan.parameters.*`，精确集合则"新增或改名结构都会响亮失败并暴露待审路径"），**我采纳其更严格的方案**。⑤新增 4 项正负向测试 + 1 项真实文档断言；序列化层证据以 `javap` 核实 `Schema31Mixin` 中 `getType` 被 `@JsonIgnore` 而 **`getRequired` 未被忽略**（吸取上一轮"内存态断言=虚假保证"的教训）。

**我对 Oracle 两处主张的独立核实（不盲从，均已带证据提交其裁定）**：
1. **`IncidentView`**：Oracle 要求"与 inline 契约的空 required 集比较，而非跳过"。我与实施道**各自独立**全量搜索契约的 `incidentId`/`openedAt`/`lastReportedAt` ⇒ **均零命中**；契约中唯一的 `incidents` 键在请求侧（`GimbalHeartbeatRequest`/`GimbalStatusView`，均 `x-detail: skeleton`、`{type:object, additionalProperties:true}`），**不存在任何响应投影结构定义** ⇒ 该主张与契约事实不符。处置：保留"跳过"，但披露文案改为明确写明"**契约未定义该结构**"及依据（门禁新增 `CONTRACT_UNDEFINED_RESPONSE_SCHEMAS`），**未 invent 任何映射或 required**。
2. **`any` 的数量**：Oracle 称"仅三处"，我实测为 **6 处**（3 个 plan 结构 × {顶层 `parameters.*`、`steps[].parameters.*`}，因 `projectStep → parameters → projectParameters` 每个 step 内还有一层动态映射），并已把该实测修正**在其在飞时**转达实施道（其独立回放判据于修复前抓取，HITS=6 逐字一致）。
3. **避免误报的实测事实**：61 个 component 中 **47 个没有 `type` 键**（springdoc 对 record 在 3.1 下的正常输出，Oracle 两轮均未视为缺陷）⇒ `any` 判据**不能**只用"无 type"，实际判据为"无 `type` 且无 `$ref` 且无 `properties` 且无 `items` 且无 `additionalProperties`"。

**验证（orchestrator 亲自执行，绑定 `c3bf054`）**：`test-compile` rc=0；定向文档测试 **38/0/0**（Guard 7、Coverage 1、DisabledIT 1、**Applier 26**、OpenApiDocsIT 3）；**全量 Java 446 run / 0 failures / 0 errors**（`7461ce1` 的 442 + 4 新）；真实 `/v3/api-docs` **200 / 424133 字节**、swagger-ui 200；自建 `verify-r4.py`（**两次自测判别力**：对修复前抓取 72 PASS/6 FAIL，6 项恰为待修清单；期间我修掉脚本自身两个缺陷——把属性节点当 schema 名传入致 `TypeError: unhashable type: 'dict'`、`any` 判据把 47 个正常 component 误报为 53 个）跑出 **78 PASS / 0 FAIL**，逐条覆盖 Oracle 7 条目标（`missingRanges.items.required=[from,to]` 且仍封闭、三个 inline component 的 required 精确相符且**未 invent `reportId`**、`RecordWatermark`/`IncidentView` 均为空、无 type 值节点**恰 6 处且全在核准路径**、有非空 required 的 schema 由 53 增至 **56**）并回归前几轮全部已闭合项（ops 34、summary/description 34/34、4xx5xx 34/34、`x-error-codes` 34/34、参数 59/59、属性描述 266/266、枚举 32、示例 221、tags 12、公开端点 4、`bearerAuth`、2xx={200,201,202,204}、A02 `required=['metadata']`、无结构自由字段 0、**384 个 `$ref` 零悬空**、`JsonNode`/`PrincipalContext`/`SuccessEnvelope` 已修剪、3 个 `JsonNode` 型字段均带 `type=object`、核准不透明集恰 3 项）；跑后端口空闲、无遗留进程；整轮相对 dev 基线 **12 文件 / +7642 −53，全部在 `web/docs/**`**，`git diff --check` rc=0。

## 15. 最小契约一致性修正轮（总协调授权，最终代码 SHA `859266099476eace91053bac0b61a48a7023dc52`）

上一轮（§14）交付后，总协调阅读并**首次授权改 `backend/contracts/openapi`**，指定三项最小修正 + 两项文档一致性要求，并明令**禁止改变 HTTP 或序列化业务语义**、只验证此次变动、不重复 E 的 61 项集成全套与已通过范围。完整记录见 `B-oracle.md` §4.17，此处只列要点。

**① `PROVIDER_CONTRACT_VIOLATION` 的正确归类**：取证确认它**不是** HTTP 错误码（Java `ErrorCode` 枚举命中 0），而是**任务投影字段** `failureCode` 的取值（D 的 Worker 写 `skin_assessments.failure_code` → `FailureProjection` 公开白名单 → M3-A03 外发）。契约该字段原本只有 `{type: string, nullable: true}`、**完全没有 enum**，该码在契约中出现 **0 次** ⇒ 修法是把 `PUBLIC_FAILURE_CODES` 的 **9 个码作为封闭 enum** 写入契约，并让生成文档侧同步为 `PropertyDoc.enumOf`（**逐字同序**），`retryable=false` 语义原样保留。这也正是 Oracle 第二轮的意见（"应补入测肤 failureCode 契约，而非 HTTP ErrorBody enum"）。

**② f02 补 `SESSION_INVALID`**：`AuthController:181` 对停用账号确实抛 401（裁定依据 oracle B2）；契约 `responses` 本已含 `'401': $ref Unauthorized`（共享响应描述即写明该码）⇒ **只补 `x-error-codes`**，为最小改动。

**③ 移除 24 处不可达错误码声明 / 17 个操作**（Care 15、Assessment 4、Foundation+IdentityDevice 5，与契约精确相等）。方法上是本轮的关键纪律：
- 我先发现自己的 grep **漏掉静态导入**（只匹配 `ErrorCode.X`），导致三个码"零命中"的假象与既有实测矛盾 ⇒ 改用**裸常量名**重做，才得到真实抛出点全集。
- 确证 `SESSION_INVALID` 由 `BearerAuthFilter:89,104` 对**所有已认证请求**统一抛出 ⇒ 除公开端点外**一律不得删**（本轮最易造成真实回归处）。
- `CALLER_NOT_ALLOWED`/`PLAN_NOT_READY` 不可凭直觉判定，派**只读侦察道逐操作追踪 controller→service→授权路径**；决定性依据是 `CareAuthorization.requireApp`（care 包唯一 403 抛出点）仅被 `CareQueryService:69,107,227` 调用，而 M4-A03…A08 **显式接纳云台主体**。
- 我对侦察结论**逐条复核而非照抄**，其中一处**改变结论**：M4-A04 的 `TASK_REPLACED` 未被真值表覆盖，我自行追踪 `taskReplaced()` 全部调用点确证其经 `runRevalidation:427,430` 与 `runRevalidationTx:470,473` **可达 ⇒ 保留**。
- **一处我差点造成的文档破坏**：我曾怀疑 `AssessmentApiDocs` 中 M3-A03 的"过声明：`CALLER_NOT_ALLOWED` 当前实现不返回"标注有误（因 `AssessmentReadService:81` 确实抛该码）；取证明明 `:81` 属 **`currentAssessment`（`:78`，服务 M3-A06）**，`getTask:36-58` 不经过它 ⇒ **原标注正确**，若"顺手修正"就会把正确文档改错。
- 契约改法：4 行内容相同而删除项不同 ⇒ `edit` 工具会因多重匹配失败，改用**按行号定位的脚本**并对每行自校验（确为 `x-error-codes` 行、确含待删码、结果集恰等于预期、删除数相符），任一不符即整体不写入；实测 diff 34 行、**非 `x-error-codes` 行改动为 0**。

**④⑤ 文档一致性**：指南 §7 的 `reportSummary` 行已与 §8 统一为"**已知三键**（`schema_version` integer 固定 1 / `conclusion` string 取值集合未冻结 / `headline_metrics` array 最多 8 项）+ **剩余扩展边界**（`additionalProperties=true`、必须容忍新增键、字段可空、内部诊断绝不外发）"；§3.2 由"已知缺口（未改契约）"改写为"契约一致性修正与过声明处置"，含 **24 处移除清单表（逐项附 `文件:行` 依据）**与"必须保留的可达码"段。47 个 component 缺 `type` 与 4 处 `additionalProperties` 按授权**仍只作披露**，未扩展为代码生成器工程。

**新增仓内回归守卫**（`.coordination/` 是 git 忽略目录、运行时脚本不进仓库，故守卫必须落在仓内）：门禁新增 24 对不可达码**不得再被声明** + 13+1 项可达码**必须继续声明**（正向对照使"全删"无法通过）+ **操作缺失即记 problem**（防路径笔误导致恒真）；另新增 `crossCheckFailureCodeEnum`（生成文档 enum 与契约逐字同序、必含 `PROVIDER_CONTRACT_VIOLATION`）。

**验证（orchestrator 亲自执行）**：契约四项校验器全绿（VALID、10/0、50/0 all samples valid、jcs 26 checks）；Java `test-compile` rc=0、定向 **38/0/0**、**全量 446/0/0**；真实 `/v3/api-docs` 200 / **418567 字节**，**34 个契约业务操作 generated==contract ALL MATCH**、24 对残留 **0**、14 项正向对照全部仍在、enum 同序相等、`x-error-codes` 总数 **358→334（恰 −24）**；上轮已闭合项零回归（自建脚本 **78 PASS / 0 FAIL**）；**端到端工装完整 41 项 ALL PASS / SCRIPT_RC=0**，其中 **b14**（契约驱动白名单，全量观测面）PASS ⇒ 实证被删的码在真实请求中不可观测、且无观测码变为未声明。

**我本轮的错误（如实记录）**：①**过滤式工装运行结构上无效**——先以 `B_ACCEPT_FILTER="b3 b11 b14 b19 b21"` 跑得 2 PASS/3 FAIL（b14 报"端点 m1A01… 未产生任何错误观测"、b3 因缺 b1/b2 前置 fixture 失败）；取证 `b-checks-3.sh:300-304` 确认 b14 读取共享 `$OBS_FILE` 并**要求 12 端点均有观测**，而观测由各检查的 `op_call` 产生 ⇒ 过滤运行对 b14/b3 无效、**非产品缺陷**；改完整运行后 41/41 全绿。②**第三次**犯"`cd` 后在 heredoc 里用相对路径"的错误（致量化脚本 `FileNotFoundError`）。③初始 grep 漏静态导入。
**子道对我任务书的两处纠正（均已采纳）**：M2-A01 实际在 `FoundationApiDocs.java:207`（我误标 IdentityDevice）；`PropertyDoc.enumOf` 定义在 `ApiDocsCatalog.java:320` 的嵌套 record（我误指 `ApiDocEntry.java`）。

**边界与待协调**：业务代码 diff **0 文件**；E 的验收资产零改动（其 driver 未硬编码这些码，命中只在历史 evidence 工件）；未改 `backend/doc/**`（设计文档归总协调）；未 push、未合入 dev。**已提请总协调**：契约 `x-error-codes` 收窄可能要求 E 更新其期望。

**门禁状态（最终）**：Oracle 对 `8592660` 判 **FAIL**（1 BLOCKER + 2 IMPORTANT + 1 SUGGESTION），整改后提交 **`666bfbe75c5bd86129d6d8f3a5df91134ffab605`**，Oracle 第十八轮窄范围复审判 **PASS-with-notes**，**明确许可把 `666bfbe` 作为本轮最终代码 SHA 合入 dev**、**不要求补跑完整验收也无需重跑 b14**、并确认轮次边界（无需再因普通措辞或断言精度发起重绑定）。完整记录见 `B-oracle.md` §4.17–4.18。

### 15.1 Oracle 第十七轮 FAIL 的 BLOCKER 与我的验证盲区

删掉某操作**最后一个**映射到某 HTTP 状态的码后，契约仍保留该状态的 `responses` 条目 ⇒ **9 处孤儿响应**（M2-A01 的 409；M2-A03、M3-A03、M4-A05、M4-A06、M4-A07、M4-A08、f05 的 403；M4-A02 的 409）。**根因是我的验证盲区**：门禁只校验"每个声明的错误码必须有对应响应"（单向），未校验反方向；我的量化脚本也只比对 `x-error-codes` 而未比对 `responses` 状态集。
**一处险情**：Oracle 给出的 9 个行号经我**预检发现不是响应行、而是这些操作的 `x-api-id`/`operationId` 行**（9 处逐行核对全部 MISMATCH）；若照其行号执行删除会损坏权威契约。故改为在各操作块内自行定位（实得第 267/344/744/962/1146/1194/1240/1290/1575 行）。**Oracle 本轮确认那是"操作块锚点"，并判定我的处置"正确且必要"。**
修法：替换为**同缩进注释行**（保留删除理由与取证指引，**总行数不变** 2848→2848），三重自校验（移除集合==预期 9 处、以 `(method,path,status)` 三元组为键；无新增状态；**补回后与原文件 deep-equal**）；实测 diff 18 行、**被删行中非 403/409 响应者为 0**。
另按 Oracle 的 IMPORTANT/SUGGESTION：修 `ErrorCodeDocs`/`CommonEnvelopeApiDocs` 两处陈旧"契约缺口"表述（改为"该码**刻意**属于 `AssessmentTaskView.failureCode` 的独立封闭枚举、不属于 HTTP `ErrorCode`，在 HTTP 错误码枚举中找不到它是正常的"）；门禁补 3 对正向对照（共 **16 对**）、新增 `orphan4xxResponseProblems()` 孤儿 4xx 守卫、`KNOWN_UNSUPPORTED_4XX_RESPONSES` 例外清单**恰 2 条**（M3-A01/A02 的 422）+ **反向陈旧守卫**、`discloseExistingContractGaps()` 弱披露（只打印不失败）；指南修 4 处（删旧冲突段、如实区分"16 对门禁锁定 vs 其余人工取证"、`reportSummary` 改为"仅识别三键且**每键按可选处理**"、`NOT_IMPLEMENTED` 改为"契约保留码、占位 Controller 已无业务映射、已实现端点不应期待"）。
**我对 Oracle 目标 #2 的偏离（已获其裁定接受）**：其"契约与生成文档非 2xx 状态集合一致"按字面**不可达**——全部 34 个操作的契约都声明 `500`，而 29 个 `ErrorCode` 中只有 `INTERNAL` 映射 500 且按设计不入任何端点声明，故生成文档从不输出 500；严格相等会在 34 个操作上全部失败，且属既有约定、不在授权范围。改为"孤儿 **4xx** 守卫 + 2 条精确例外 + 反向陈旧守卫 + 5xx 排除（附理由）+ 弱披露"，Oracle 判"**满足本轮目标的意图，可以接受**"。

### 15.2 待总协调处理的 5 项既有契约不一致（Oracle 逐项裁定"总协调应处理"，不阻塞本次合入，但"不建议永久仅靠披露保留"）
1. **`500`×34**：全部 34 个操作的契约都声明 500 而无任何 `x-error-codes` 支撑（生成文档亦无 500）。Oracle 明确**正确方向是让生成 Swagger 也声明通用 500，而非删除权威契约的 500**（真实运行确实可能返回 500 `INTERNAL`）。
2. **M3-A01/M3-A02 的孤儿 `422`**：无剩余码支撑，应由总协调确认并清理，不宜长期保留为有效响应。
3. **M1-A02 缺 `404` 响应**：已声明 `RESOURCE_NOT_VISIBLE`（隐含 404），契约 `responses` 应补 404。
4. **M2-A04 缺 `422` 响应**：已声明 `UNSUPPORTED_CONTRACT`（隐含 422），契约 `responses` 应补 422。
5. **`NOT_IMPLEMENTED`**：全部已实现业务端点仍声明它，而占位 Controller 已无业务路由映射 ⇒ 应重新裁定；Oracle 建议**权威契约冻结前从已实现操作移除**，若作为未来兼容保留则必须明确它不是当前可达码。
> 另需知会：本轮契约 `x-error-codes` 收窄（24 处）与 9 处响应删除，可能要求 **E 更新其按精确集合断言的期望**；E 的 driver 未硬编码这些码（命中只在历史 evidence 工件中，不应修改），我方工装的 b14 白名单从契约动态读取故自动适配。

### 15.3 Oracle 的 2 项非阻塞 SUGGESTION 与我的处置决定
①门禁因 500 的特殊约定而排除了**全部 5xx**，未来出现孤儿 `501/503/504` 会被漏报 ⇒ 建议**只排除 500**、仍检查其它 5xx（当前无此类孤儿，故现状结果正确）。②披露文案"29 个 ErrorCode 无码映射到 500"**不准确**——实际 `INTERNAL` 映射 500，只是不进入端点 `x-error-codes`；建议改为"除刻意不进入 `x-error-codes` 的 `INTERNAL` 外，无可声明码支撑 500"。
**决定：不为这 2 项改动代码 SHA。** Oracle 已明确其属"断言精度/普通措辞"且宣告无需再为此发起重绑定轮次；改动会使已获批的 `666bfbe` 绑定失效、制造其明示不必要的审查循环。两项连同精确修法记入本节与 `B-oracle.md` §4.18，交由总协调安排的"契约收敛任务"（上述 5 项本就要其裁定）一并处理。**如实标注**：`ApiDocsCoverageIT` 中 `discloseExistingContractGaps()` 的**打印字符串**含上述不准确表述（`:1031-1034` 的注释表述是准确的），任何读者不应据该字符串得出结论。

### 15.4 本轮验证与我的错误
**验证（绑定 `666bfbe`，orchestrator 亲自执行）**：契约四项校验器全绿（`openapi_spec_validator` VALID、`validate_responses --selftest` 10/0、`validate_samples` 50/0 all samples valid、`jcs` 26 checks）；Java `test-compile` rc=0、定向 **38/0/0**（含 Coverage 1）、**全量 446 run / 0 failures / 0 errors**；孤儿 4xx 独立复查**仅剩 2 处**（恰为既有的 M3-A01/A02 的 422）；真实 `/v3/api-docs` 200 / **418968 字节**、swagger-ui 200；上轮已闭合项零回归（自建脚本 **78 PASS / 0 FAIL**）；契约↔生成文档非 2xx 差异 34 个操作**全部属既有类型**、本轮修的 9 处残留 **0**；按 Oracle 明示未重跑端到端工装与 b14；业务代码 diff **0 文件**、`git diff --check` rc=0。
**我的错误**：①验证盲区（见 15.1，BLOCKER 根因）；②自建孤儿复查临时脚本**连续两次崩溃**（映射表漏 `INTERNAL_SERVER_ERROR` 致 `KeyError`；改用 `http.HTTPStatus` 动态映射而 Spring 的 `PAYLOAD_TOO_LARGE` 在 Python 中名为 `REQUEST_ENTITY_TOO_LARGE` 致 `AttributeError`），第三次回到已验证可用的显式映射表才成功 ⇒ 不要为"更聪明"而替换已验证可用的取证脚本；③预期集合误用 foundation 操作并不存在的 `x-api-id` 标签，被自校验拦下、未造成损害；④**过滤式工装运行结构上无效**（见 §15 正文，`B_ACCEPT_FILTER` 使 b14 失去观测面、b3 失去前置 fixture），已改为完整运行取 41/41；⑤第三次犯"`cd` 后在 heredoc 里用相对路径"的错误。
**子道对我任务书的两处纠正（均已采纳）**：M2-A01 实际在 `FoundationApiDocs.java:207`（我误标 IdentityDevice）；`PropertyDoc.enumOf` 定义在 `ApiDocsCatalog.java:320` 的嵌套 record（我误指 `ApiDocEntry.java`）。

## 16. `local` profile 加载条件解耦轮（用户授权，基线 `e2148e1`）

**授权**：修复"IDEA 仅启用 `local` profile 时报 `SessionProvider` 缺失"；把**环境 profile** 与 **`app.providers.mode` 服务实现选择**解耦；**全面核对** `TestDoubleProvidersConfig`、`IdentityProvidersConfig`、`DeviceProofDoublesConfig` 等所有相关加载条件，**不能只补 `SessionProvider`**；`local`+doubles 必须完整加载当前登录/身份/设备依赖；`prod` profile 或 `app.env=production` 时测试替身必须 fail-closed（**含矛盾配置**），保留相关防护；仅改必要 Java 加载条件与针对性测试，不实现真实算法/OSS、不改业务契约。

### 16.1 根因（orchestrator 亲自取证，非推测）
1. `backend/web-java/src/main/resources/application.yml:10-12` 设 `spring.profiles.default: dev`。**一旦显式启用 `local`，default 不生效** ⇒ 生效 profiles = `{local}`。
2. 全仓 **10 处 profile 耦合**把"实现选择"错误地绑在 profile 名上：
   - `config/TestDoubleProvidersConfig.java:30` —— 写作**全限定** `@org.springframework.context.annotation.Profile({"dev","test"})`，提供 `SessionProvider`/`SmsCodeProvider`/`DeviceCredentialProvider`/`FaceProvider`/`StoragePort`；
   - `devices/proof/DeviceProofDoublesConfig.java:14`（`PairingProofVerifier`/`ConnectionProofVerifier`）；
   - `identity/IdentityProvidersConfig.java:19`（`FaceIdentityResolver`，**只有** profile 门、无 mode 条件）；
   - `docs/OpenApiDocsConfig.java:41` + 5 个 catalog（`CommonEnvelopeApiDocs:29`、`AssessmentApiDocs:34`、`CareApiDocs:38`、`FoundationApiDocs:30`、`IdentityDeviceApiDocs:32`）；
   - `care/MemberBindingFaceDouble.java:30` 的 `@Conditional(CareDevTestCondition.class)`，而 `care/CareDevTestCondition.java:38` 第 3 条要求生效 profiles 含 `dev`/`test`。
3. 8 个端口类型均被**非 config 的单例构造注入**（`SessionProvider` 5 处、`FaceProvider` 7 处、`StoragePort` 5 处、`PairingProofVerifier` 2、`ConnectionProofVerifier` 3、`FaceIdentityResolver` 3、`SmsCodeProvider` 3、`DeviceCredentialProvider` 4）⇒ `local` 下上下文**必然启动失败**，`SessionProvider` 只是第一个被报出的。
4. `care/CareAdmissionService.java:85,99` 构造注入 `CareFaceVerifier`；`FailClosedCareFaceVerifier` 是无条件 `@Component`、`MemberBindingFaceDouble` 是 `@Primary` 替身 ⇒ `local` 下上下文能启动但护理人脸核验**恒 503 `CAPABILITY_UNAVAILABLE`**（功能退化而非崩溃）。故 C 的条件也须解耦，"完整加载"才成立。
5. `application.yml:72` 的 base 默认本就是 **`app.providers.mode: ${APP_PROVIDERS_MODE:doubles}`（与 profile 无关）**，`prod` 段（:132-133）才设 `mode: real` ⇒ **纯 Java 加载条件即可完成解耦，无需改动任何公共默认配置**（这点关键：外层 master 的同名文件有用户未提交修改，本轮明令不得改/不得读/不得纳入提交）。

### 16.2 我的取证缺陷（如实记录）
首次盘点用 `grep '@Profile'` 得到 9 处，并据此**错误断定**"`TestDoubleProvidersConfig` 本来就没有 `@Profile`、不该因 `local` 失配"。实际它写作**全限定形式** `@org.springframework.context.annotation.Profile(...)`，该模式**匹配不到**。改用同时覆盖全限定写法的模式重做后才得到完整的 10 处清单并定位真正根因。这与本轮之前"`grep ErrorCode.X` 漏掉静态导入"是**同一类错误**（模式匹配未覆盖等价写法）⇒ 教训：盘点"某类注解/调用的全集"时，必须先确认模式覆盖全限定名、静态导入、别名等等价写法，否则会把"漏检"误当"不存在"。

### 16.3 设计（最小、行为等价、不新增门）
- 新增共享条件 `config/NonProductionCondition`：判据**恰为两条**——`app.env`（默认 `dev`，`trim` 后 `equalsIgnoreCase("production")`）为生产 ⇒ false；生效 profiles 含 `prod`/`production` ⇒ false；否则 true（**不要求** profile 是 dev/test，故 `local`、无 profile、自定义环境名都放行）。"生效 profiles" = 显式 active 非空时取之、否则取 `getDefaultProfiles()`，统一小写（与 `CareDevTestCondition.effectiveProfiles` 语义完全一致，故 `SPRING_PROFILES_ACTIVE=prod,dev` 这类混合配置不会因含 `dev` 而放行替身）。
- 用它**等价替换**上述 10 处 profile 耦合，**不新增也不删除任何 mode 条件**：`TestDoubleProvidersConfig`/`DeviceProofDoublesConfig` 保留各自 `@ConditionalOnProperty(app.providers.mode=doubles, matchIfMissing=true)`；6 个 docs 类保留 `@ConditionalOnProperty(springdoc.api-docs.enabled=true)`；`IdentityProvidersConfig` **保持只有非生产条件**（给它新增 mode 门会改变既有语义——今天 dev profile + `mode=real` 时该替身同样装配，属既有行为，不在本轮授权内；已列为观察项上报）。
- `care/CareDevTestCondition` 改为**委托**新条件的前两条、**保留第 3 条**，且其静态入口 `effectiveProfiles` 继续存在（`CareFaceVerifierProductionGuard:51` 在用）。**硬约束**：`CareDevTestConditionTest` 必须**原样通过、不得改一行**（作为"C 侧语义零变化"的可验证证明）。
- **必须原样保留的守卫**：`ProductionFailClosedValidator`、`DeviceProofFailClosedValidator`、`CareFaceVerifierProductionGuard`（无条件 `@Component`、双判据）、`DocsProductionGuard`（无条件、双判据）、`TestDoubleProvidersConfig.requireNoProductionSignals`（:72-83，`storagePort()` 内的纵深防御）。

### 16.4 我预先定位的既有测试机制变化（实施前即已预见并写明处置要求）
`config/StorageFailModeProductionFailClosedTest` 的 `productionSignalRefusesAssemblyBeforeAnyStoragePortExists`（约 :116-140）现断言根因是 `requireNoProductionSignals` 抛出的 `IllegalStateException`、栈含 `production fail-closed`/`active-profile-prod=true`/`app.env=dev`——该机制依赖"混合 profile `prod,dev` 下 `@Profile` 因含 `dev` 而**匹配**、配置照常装配、再由守卫抛错"。解耦后**拒装提前到条件层**（替身根本不会被构造，安全属性**增强**），根因将变为缺 bean 类异常 ⇒ 该测试必须据实改写，但**严禁弱化**：仍须断言上下文启动失败、失败源于生产信号下替身未装配/无法创建 `StoragePort` 替身、注入开关 `APP_DOUBLE_STORAGE_FAIL_MODE` 在该情形下不可达。

### 16.5 边界与验证局限
不改 `application.yml`（若确实必须改，先报方案与精确 diff 给总协调）；**绝不读取/输出/覆盖** `application-local.properties`（含 PG/OSS 秘密）；不读取、不修改、不纳入提交**外层 master 工作树**任何文件；不进入其它工作树；不实现真实算法/OSS/人脸/推送提供方；不改业务契约与 HTTP 行为；只用 B 的隔离资源（`mvp-b-pg`@55435、端口 18083、mvn 限堆），用毕释放、不留长期服务、不停 PG、不清库卷。
**验证局限（须如实披露）**：我方**无法读取用户私有的 `application-local.properties`**，故只能用 `SPRING_PROFILES_ACTIVE=local` + 显式 env 覆盖（数据源指向 55435 的 `mvp_b_dev`、`APP_STORAGE_DEV_DIR` 指向 `.coordination/B-work/`）来模拟"仅启用 `local` profile"。若用户私有配置另外覆盖了 `app.env`、`app.providers.mode` 或 `springdoc.*`，实际装配结果需由用户在其环境复验。

**实施与验证**：单一实施道 fix-16；orchestrator 独立复核后提交 **`39608bf`**（Oracle 第十九轮 **PASS-with-notes**、许可整合）。总协调随后下达在飞增量两项（两个测试提供者补 mode 门；生产信号 + `doubles` 须早期明确拒绝而非被"缺 `SessionProvider`"掩盖），与 Oracle 两项 IMPORTANT 重合，合并实施为 **`6a72b0b6cf2efb80eb6f641124dd4b434328f0c6`**（12 文件 / +675 −128，业务代码 diff 0），并补齐 orchestrator 自行发现的既有缺口——`mode=disabled` 此前**无法启动完整应用**（B 自有 `PairingProofVerifier`/`ConnectionProofVerifier`/`FaceIdentityResolver` 无 disabled 占位）。验证：`test-compile` 0、定向 **61/0/0**、全量 **481/0/0**；真实进程四例——`local` UP + health 200 + 无 token 得 401 `AUTH_REQUIRED`、`prod`(real) 失败缺 `SessionProvider`（既有刻意 fail-closed）、`prod`+`doubles` 失败且根因为新守卫诊断（`SessionProvider` 缺失计数 0）、`local`+`disabled` **UP + 503 `DEPENDENCY_UNAVAILABLE`**。详见 `B-oracle.md` §4.19–4.20。
**门禁状态**：Oracle 第二十轮聚焦复审判 **PASS-with-notes**，**明确许可把 `6a72b0b6cf2efb80eb6f641124dd4b434328f0c6` 交总协调整合**、不要求补跑验证、**未发现真正阻塞项**。剩余非阻塞项：Oracle 2 条 SUGGESTION（`DeviceProofFailClosedValidator.isDouble()` 不识别 lambda 形式的 disabled 占位；新守卫文案宜注明 `disabled` 仅用于非生产/降级环境）、上轮 5 项既有契约不一致待总协调裁定（`500`×34、M3-A01/A02 孤儿 `422`、M1-A02 缺 `404`、M2-A04 缺 `422`、`NOT_IMPLEMENTED`）、`IdentityProvidersConfig`/`CareDevTestCondition` 两项观察项。**未 push、未合并**（由总协调整合外层 master）。

## 17. 真实供应商接入轮（短信 / OSS / 独立人脸服务，用户授权，基线 `8f5b625`）

**授权**：接真实阿里云短信、Java 与 Python 真实阿里云 OSS、以及 dev.ai-skin 上**完全独立**的 `InsightFace-for-openvela` 人脸识别服务；按服务独立选择（短信 `aliyun`、存储 OSS、人脸 `insightface`），保留会话/设备等尚未接入服务的测试模式但不得标真实或开放 prod；**真实服务故障不得回退 mock 成功**；Java+Python 都接 OSS（私有桶、后端鉴权读取、无公开 URL、相同 objectKey 与真实 bucket 元数据、保留结果图归档失败重试），禁止仅 Java 真 OSS 而 Worker 仍本地；短信须随机码/过期/一次性核销/尝试限制/发送节流/**发送失败不签发有效 challenge**，受理成功必须阿里云业务 `Code=OK`（不以 HTTP 200 判定、更不称送达），未获明确测试手机号前不发送真实短信；人脸按已批准 A 方案（项目专用实例+专用库），缺 1:1/可靠新人/活体**必须明确未接入并拒绝或不确定，不得伪完成**。

### 17.1 交付与提交链
| 交付 | SHA | 要点 |
|---|---|---|
| 人脸缺口与最小接口/隔离方案（纯文档） | `0cc9f76` | 9 项缺口 G1-G9、最小接口 P1-P5、隔离方案 A/B/C；用户据此选定 A 并授权部署 |
| 真实阿里云短信 provider | `07254a0` | `app.sms.provider=doubles\|aliyun`；`Code=="OK"` 唯一成功判据；失败不签发 challenge（由 issue() 顺序构造保证）；随机码避开 `123456`；三窗口 UTC+8 自然节流；429 `RATE_LIMITED` 首次真实可达 |
| Python 侧真实 OSS | `229476c` | `MVP_D_STORAGE_PROVIDER`；`AliyunOssStorage`（私有桶、流式、真实元数据）；生产 + double 拒绝（含 `SPRING_PROFILES_ACTIVE=prod,dev` 矛盾组合）；保留 `RESULT_ARCHIVE_FAILED` 可重试 |
| 独立人脸服务 `InsightFace-for-openvela` | `dce562b` + `13f0f62` | 零写入 `/v1/extract`、严格 1:1 `/v1/verify`、命名空间隔离+回执+`library_revision`、活体恒 `supported:false`、用户级 unit 与幂等 deploy.sh |
| Java 侧真实 OSS | `20e2575` | `app.storage.provider=doubles\|aliyun`；`OssStorageAdapter` 为唯一 SDK 触点；**bucket 一致性启动校验**；无 `generatePresignedUrl` 调用 |
| Java 人脸 adapter | 在飞 | `app.face.provider=doubles\|insightface\|aliyun`（aliyun 仅边界、选中即拒绝启动） |

### 17.2 人脸服务已部署并实测（dev.ai-skin，用户级 systemd）
- **服务管理可行性**：`systemctl --user` 可用；初查 `Linger=no` 且无免密 sudo、`/etc/systemd/system` 不可写 ⇒ 用户级 unit 原本登出即死。**orchestrator 执行 `loginctl enable-linger bool` 成功（`Linger=yes`）**——用户范围、可逆的状态变更，已主动披露；这是判定"linger 可用性"的唯一可靠方式，不用 `nohup` 伪装长期部署、不碰系统级 unit。
- **部署**：远端目录 `~/deployment/InsightFace-for-openvela`（新目录），投递**提交版** `13f0f62` 的 28 个跟踪文件（无 `.venv`/`data`/`__pycache__`）；`uv sync --frozen`；token 由 `openssl rand -hex 32` 生成到 `~/.config/face-service-openvela.token`（**0600，值从未打印**）；env 文件 0600 且 `FACE_SVC_INTERNAL_TOKEN` 内联计数 **0**（只引用 token 文件）；`deploy.sh` rc=0、unit `enabled` + `active`。
- **实测证据**：只绑 **`10.3.6.163:8010`**（非 `0.0.0.0`）；health 200 且 `model_loaded=true`、`model_version=buffalo_l@insightface-0.7.3`、`liveness.supported=false`；无 token 与错 token 均 **401**；未知 namespace → **404 `NAMESPACE_NOT_FOUND`**；**合成空白图 → 400 `NO_FACE`**（证明真实 buffalo_l 推理已运行，且未上传任何真实人脸）；**零写入在真实服务上得证**（幽灵 namespace 事后仍 404、三次 extract 后 `library_revision` 仍为 0）；**重启后 16 秒恢复**、`library_revision` 持久且无虚假递增、`MemoryCurrent=677MB`（< `MemoryMax=4G`）；journal **0 条 error、token 泄漏计数 0**；数据目录只有自有 `openvela_faces.sqlite3`(28KB)、**`face_cache.pkl` 不存在**。
- **共享服务零触碰自证**：8002/8003 的 PID 在部署前后均为 **1737/1738**、`systemctl is-active` 均 active、其目录 mtime 仍是 2026-06-11 与 2026-07-14；全程未调用 `/register`、`/reload`、`/delete`、`/extract_face`（后者有"搜索后 INSERT"的写副作用）。
- **一项我自己的错误预期已纠正**：我曾预期 `/v1/extract` 对 `require_liveness=true` 返回 501，实测得 400 `NO_FACE`；读码证明 `_ensure_liveness_supported` 只在 **verify(:339)** 与 **register(:392)** 调用，extract 无该门（它对每张脸返回 `liveness:{supported:false}` 即履行"明确 unsupported"要求）。故那是我的预期错误、非服务缺陷；501 拒绝路径由 `test_verify.py:103-112`、`test_subjects.py:157-164`、`test_errors.py:21` 覆盖。extract 未设该门作为一致性小观察项记录，不为此 churn 已部署服务。
- **未在真实服务上验证**：注册→1:1→删除正向闭环。原因是合成空白图无法检出人脸，而**禁止上传真实用户照片**、也**禁止**从旧共享库复制那 400 条；需根/用户提供**非真实用户**的可检出人脸 fixture（合成或已获同意的测试图）后才能实测。

### 17.3 验证数字（orchestrator 亲自执行）
- Java：短信轮 定向 85/0/0、全量 **512/0/0**；Java OSS 轮 定向 94/0/0、全量 **528/0/0**（基线 481→512→528，账目自洽）；`test-compile` 与 `package` 均 rc=0。
- Python：全量 **331 passed / 0 failed**（基线 293+38），`oss2` 实际解析 **2.19.1**，`--check`/`--once` rc=0；存储生产守卫直接实证（production/prod/`APP_ENV=production`/`SPRING_PROFILES_ACTIVE=prod,dev` + double 均 REFUSED；production+`aliyun_oss` ALLOWED）。
- 人脸服务：pytest **64 passed**（venv 内 `insightface`/`onnxruntime`/`cv2` **均未安装** ⇒ 延迟导入实证）、`compileall` rc=0、入仓 dry-run 恰 28 文件且 **0 个被忽略产物泄漏**。
- 真实进程对照（均用毕 kill、18083 已释放）：短信 doubles 未回归（f01 200、f02 用 `123456` 200、**同 challengeId 重放 401**）；短信 aliyun+假凭据+不可达 endpoint → f01 **503**、f02 **401**（`123456` 在真模式非万能码）；Java OSS bucket 不一致 → **启动被拒**（Tomcat 未启动）并给逐字诊断；各例日志中假 AKID/Secret/完整手机号出现 **0** 次、掩码手机号出现 1 次。

### 17.4 本轮我的错误（如实记录）
1. **第四次**犯"`cd` 之后仍用相对路径"：验证脚本把 venv 存成相对路径后 `cd` 到子目录再调用 ⇒ `rc=127`；提交守卫拦下了未验证提交。
2. **Python 测试环境变量连踩三次**才取全：先只传 `MVP_WORKER_PG_DSN`（不影响 conftest 建库）→ 再传 `MVP_A_PG_DSN`（conftest 用）但 `migrate.sh` 仍失败 → 最后发现 `migrate.sh:13` 调 `createdb.sh:4` 的 **`MVP_A_PG_CONTAINER` 默认 `mvp-a-pg`（A 的、已停止的容器）**。三次都表现为"331 个用例全在 setup 阶段 ERROR"，极易被误判为代码缺陷。已写入长期记忆（#313）。
3. **提交脚本漏写 `git commit`**：守卫通过后只做了 `git add` 与回显，导致我以为已提交；下一轮才发现 HEAD 未变。
4. **grep 模式过宽造成两次假阳性**：`SmsCodeProvider.java` 命中了 B 自有新文件 `AliyunSmsCodeProvider.java` 的子串（我一度以为越界改了 A 的端口）；`sign_url` 命中的是 docstring 里的否定陈述。两次都靠精确复核澄清。
5. **`awk` 范围模式缺陷**：`/def test_x/,/^def [a-z_]+\(/` 的起始行同时匹配结束模式 ⇒ 只打印了函数名，导致我一度未真正核验那个关键的零写入判别力测试；改用 `sed -n 'a,bp'` 后才看到断言体。
6. **重启存活验证窗口太短**（8 秒），而模型加载需约 15-50 秒 ⇒ 误得 health 000；加长窗口后 16 秒恢复。
7. **任务书基线写错**：给 Java OSS 道写"基线 HEAD=`dce562b`"，实际已是 `13f0f62`（我在派发前又提交了 EOF 修复）；实施道发现后在真实 HEAD 上实施并如实指出——它的处理正确，错在我。
8. ** Board 簿记假信号第 18-21 次**：Java OSS 道一度既不在 Active 也不在 Reusable、`task_status` 返回 `Unknown task ID`、写域 7 分钟零写入，我据此**没有**重派（fix-7 的教训），随后磁盘证明它在世并最终送达报告。若当时重派就会在 `pom.xml` 与 `TestDoubleProvidersConfig` 上制造同文件双写者。

### 17.5 边界与残留
- 全程未读取 `application-local.properties`（含真实凭据与测试手机号），未把任何凭据/完整手机号/真实验证码写入代码、测试、日志或报告；未发送任何真实短信；未访问真实 OSS；未触碰 `18085`/`internal.dxg170`/`backend/deploy` 的既有部署；未合并、未推送。
- **未验证项（需根用真实凭据执行）**：真实短信发送（`AliyunSmsLiveSmokeIT` 默认跳过，三重 opt-in 门；断言 `Code=="OK"`、只输出 Code/Message/RequestId/BizId 与掩码手机号）；真实 OSS 的签名校验/桶权限/跨区域与内网 endpoint/virtual-host 选址/真实 TLS/限流计费；人脸 1:1 正向闭环（见 17.2）。
- **如实的语义边界**：`classify` 无成员参数 ⇒ insightface 下永不 `MATCHED`/`RELIABLE_NEW`；M1-A01 成员身份解析在 insightface 下**未接入**（服务刻意不提供全库识别），改为显式"未接入"解析器使其诚实 403 而非用 sha256 冒充身份；活体**不支持**（`buffalo_l` 无活体模型），绝不以检测分/相似度冒充；`app.face.provider=aliyun` **只有配置边界、无实现**，选中即拒绝启动。
- 官方对 Spring Boot 3.5 / Java 21 **无专项兼容声明**（短信 SDK `com.aliyun:dysmsapi20170525:4.6.0`、OSS SDK `com.aliyun.oss:aliyun-sdk-oss:3.18.5`、Python `oss2==2.19.1`）。
- 已知小不一致（仅 double 模式）：Java 默认桶 `mvp-a-media` vs Python 默认桶 `mvp-media`；真实模式由 Java 侧启动校验强制 `app.storage.oss.bucket == app.storage.bucket`，并要求与 Python `MVP_A_STORAGE_OSS_BUCKET` 同值。

### 17.6 Oracle 第二十一轮判 FAIL（`55f666e`）与整改
Oracle 判 **FAIL**（4 BLOCKER + 5 IMPORTANT + 1 SUGGESTION，**不可整合**），我逐条读码独立核实后确认**全部成立**（详细 `文件:行` 见 `B-oracle.md` §4.21）。四项阻塞：①护理 1:1 **不要求活体**却把远端 `matched=true` 直接映射为 `MATCHED`（Java face 包中 `require_liveness` 出现 **0** 次）⇒ 活体未接入却能通过护理准入，属用户明令禁止的"伪完成"；②人脸服务**鉴权默认 fail-open**（`auth_required` 默认 False、`_env_bool` 对未知值静默变 False、默认 host 为非 loopback 的 `10.3.6.163`）；③短信本地节流存在 **check-then-send 竞态**（预检→发送→记录无跨三步的锁）⇒ 同手机号并发可突破"1 分钟 1 条"并产生重复计费发送；④Python OSS 把 **`NoSuchBucket` 当可重试**且源图读取**吞掉 `StorageConfigError`** ⇒ 永久配置错误无限重试。
**我的两处错误（如实记录）**：(a) IMPORTANT 7 的"启动诊断回显真实桶名"是**我在任务书里明确允许的决定**（原话"消息可输出 bucket 名——它不是凭据"），Oracle 按本轮日志卫生标准判为 IMPORTANT，**我采纳并纠正自己的决定**；(b) IMPORTANT 5 暴露**我的核验盲区**——我检查远端 journal 时只 grep 了 error 行与 token 泄漏，**未检查 access log 中的身份引用**（namespace/subject_id），故未自行发现该泄漏。
**BLOCKER 1 修复的重大功能后果（须向根明确上报）**：修法为**恒定发送 `require_liveness=true` 且不提供关闭开关**（"可削弱安全"的开关不可接受），因此服务端必返 501 `LIVENESS_UNSUPPORTED` ⇒ **insightface 模式下护理准入在活体能力落地前恒 `CAPABILITY_UNAVAILABLE`（503）**。这是刻意 fail-closed，不是缺陷；也意味着当前人脸接入的实际可用能力是**检测/质量/特征提取**，而非任何准入判定。
**整改分道**（按构建工具互斥、写域零重叠）：Java 道（BLOCKER 1/3 + IMPORTANT 7/8 + SUGGESTION 9，独占 mvn）、face-service 道（BLOCKER 2 + IMPORTANT 5，独占其自有 venv）、worker-python 道（BLOCKER 4 + IMPORTANT 6，独占其 venv）。修复后需**重新部署**人脸服务（`access_log` 与鉴权默认值变更），并按 Oracle 的轮次边界只送**窄范围**复审（四类阻塞 + 相应定向测试，不重审已通过内容）。

### 17.7 Oracle 第二十一轮 FAIL 的整改与我自行发现的部署缺陷
三道并行修复（按构建工具互斥、写域零重叠）全部交付并经 orchestrator 独立核验后**分别提交**：
- **`ffa4570`** face-service（BLOCKER 2 + IMPORTANT 5）：`_env_bool` 严格值域且**刻意不回显被拒值**；`auth_required` 默认改 **True**；新增 `is_loopback_host`（恰 `127.0.0.1`/`::1`/`localhost`）与**绑定地址↔鉴权耦合启动校验**（非 loopback 必须开鉴权、需鉴权必须已配 token、并校验 token 文件权限）；`create_app` 内加 `settings.validate()` 纵深防御；`access_log=False` + `sanitized_route()`（优先路由模板，未匹配时只留前两段 + `/...`）+ 脱敏中间件（仅 method/模板/status/duration/request_id）。既有测试仅一处加显式 `auth_required=False`，**移除断言数 0**。
- **`11ff41c`** Java（BLOCKER 1 + BLOCKER 3 + IMPORTANT 7 + IMPORTANT 8 + SUGGESTION 9）：`FaceServiceClient:111` **恒定**发送 `require_liveness=true` 且**全仓无任何配置开关**（可削弱安全的开关不可接受）；额外加固 `:145-156`——即便服务返回 2xx，只要 `liveness.supported=false` 就抛 `LIVENESS_UNSUPPORTED`/501，堵住"服务忽略 `require_liveness` 却返回 matched"的伪完成路径；`SEND_STRIPES=64` 的固定 `ReentrantLock[]` 把"预检→发送→记录受理→建 challenge"整体串行（远端发送刻意在锁内以防重复计费；**刻意不用无界 per-phone 锁 map** 以免重现 IMPORTANT 8）；bucket 不一致诊断改为只列键名 + `(values omitted)`；短信内存态有界（机会式清理 + 耗尽即 remove + 容量上限默认各 10_000，超限时**在发送之前**拒绝新签发、消息不含手机号）；`parseVerifyResponse` 严格校验（`matched` 为 JSON boolean、`similarity`/`threshold` 为有限数值、`liveness.supported` 为 boolean、`subject_id` 回显须严格相等，不符即 `MALFORMED_RESPONSE` → `DEPENDENCY_FAILED`）。
- **`f75b5be`** Python（BLOCKER 4 + IMPORTANT 6）：`_map_oss_error` 改为**显式分类表**（错误码优先于 status），`_OSS_NOT_FOUND_CODES` 只含 `NoSuchKey`、`NoSuchBucket` 等 16 个永久码归**终态**、**兜底＝终态**（理由：oss2 已把所有传输层故障包成 `RequestError(status=-2)`，落到兜底者既非网络也非 5xx/429，重试无益且会掩盖永久缺陷）；源图路径不再吞 `StorageConfigError`（`assessment_analyze:228,233` → `SOURCE_IMAGE_CONFIG_ERROR` 终态），而**归档的 `RESULT_ARCHIVE_FAILED(terminal=False)` 可重试语义未弱化**；三个 SELECT 增选 `bucket`、`_assert_bucket_matches` 在 `:274`/`:524` 校验、消息 `(column=…, config=…; values omitted)` 不含桶名，测试断言 `get_calls==0`（未发起对象读取）。
- **`2d9ee97`**（**我自己发现的部署正确性缺陷，不在 Oracle 清单内**）：`deploy.sh` 原用 `systemctl --user enable --now`，而它对**已运行**的 unit **不会重启** ⇒ 重新部署会**静默保留旧代码却报成功**。我是在做泄漏验证时偶然发现的：源码已更新、health 200，但 `ss` 显示 `pid=3175814`、health 的 `uptime_seconds=4372`（73 分钟前），探针因此命中**旧代码**的原始 access log，泄漏计数 3/2。修法：记录重启前 `is-active`/`ExecMainPID` → `enable` → **无条件 `restart`** → **断言 `ExecMainPID` 确实变化**，否则明确失败并提示 "old code may still be serving"；README 第 6 步同步说明。
**我的验证顺序缺陷（如实记录）**：第一次重新部署后我**先探针、后重启**，因而拿到的是旧进程的证据并一度可能据此得出"修复无效"的错误结论；改为先确认 `ExecMainPID`/uptime 与新代码特征（`access_log: False`、`auth_required: bool = True`）再探针后，得到正确结果。教训：**任何"部署后验证"都必须先证明在跑的是新代码**（PID/启动时间/代码特征三者之一），否则验证对象可能是旧进程。
**修复后的决定性实测**（新进程 `ExecMainPID=3191727`、`ActiveEnterTimestamp=21:01:06`、uptime 2.8s）：以独特探针标识发 GET info / GET subject / DELETE subject（均 404）与一次无 token 请求（401）后，journal 中**探针 namespace 命中 0、探针 subject 命中 0、原始 uvicorn access 行 0、token 泄漏 0**；脱敏 access 行只含路由模板 `/v1/namespaces/{namespace}/subjects/{subject_id}` + status + duration_ms + request_id；零写入仍成立（`library_revision=0`、探针 namespace 事后仍 404）；共享 8002/8003 的 PID 仍 1737/1738 且 active；重启后约 18s 恢复。
**验证数字**：Java 定向 110/0/0、**全量 577/0/0**（基线 559+18）；Python **全量 349 passed**（基线 331+18）、55432 引用 0、`--check`/`--once` rc=0；face-service **97 passed**（基线 64+33）且 CV 栈仍未安装。BLOCKER 3 的判别力证据：并发测试先跑在**未修复的 `55f666e`** 上得 `expected: 1 but was: 16`（16 线程各发 1 条计费短信），修复后 `gateway.send`=1、成功=1、`RATE_LIMITED`=15（原始输出 931 字节，我已核对文件存在与内容）。
**两项写域外残留（已上报待总协调裁定）**：①`handlers/identity_enroll.py`（D 的 handler，禁改）也调 `load_image_bytes`，其 `StorageConfigError` 传播到 `runtime/loop.py`（A 的公共 runtime，禁改）的通用 catch ⇒ 有界重试至 `max_attempts` 后终态：不吞错、不会无限重试，但**不是即时终态**；②短信容量上限目前**仅构造器可注入**（写域不允许改 `SmsRiskProperties`/`application.yml`），生产用保守默认 10_000，且跨条带并发下允许**有界瞬时超出**。

### 17.8 Oracle 第二十二轮 FAIL：四类阻塞确认闭合，新 BLOCKER 的读码异议与"用测试裁决"
Oracle 对 `2d9ee97` 判 FAIL，但**四类阻塞全部确认闭合**、两项写域外残留**均判可接受为非阻塞待办**（①`identity_enroll` 的配置错误有限重试应由 **D 的 handler 所有者**加定向映射、**不应改公共 runtime**；②短信容量上限应后续经 `SmsRiskProperties` 暴露但不阻塞）、`deploy.sh` 修法**判充分**（"对『部署成功但旧进程仍服务』已形成有效判别"）、并确认**未发现任何静默回退替身/伪造成功路径与凭据泄漏**。剩余：1 新 BLOCKER（短信 challenge 并发核销）+ 2 IMPORTANT（Python OSS 日志仍输出真实 bucket 与完整 objectKey；Java 侧活体只校验"能力位" `supported` 而未定义"本次样本通过"）。
**我方读码异议（如实记录）**：两项 IMPORTANT 经核实**成立**并已派修；但新 BLOCKER 的**竞态前提**我方读码认为**不成立**——`AliyunSmsCodeProvider.verify()` 的 `:180` 已是 `synchronized (challenge)`，`consumed` 检查、attempt 递增、常量时间比较、置位、remove 与**唯一**返回手机号的 `:205` **全在该 monitor 内**，`consumed` 还是 `volatile`，`ConcurrentHashMap` 对同一 id 必返回同一实例 ⇒ 并发必然串行。`AuthController:106` 确实用返回值签发会话，故 Oracle 的**后果**描述正确、**前提**疑似不正确。
**处置**：不以读码对抗审查、也不盲从——**用测试裁决**。已要求实施道**先只写测试、不改生产代码**：N≥16 线程经 `CyclicBarrier` 同时提交正确码断言恰一成功、200 轮 × 8 线程带 jitter 的多轮版本排除运气、混合正确/错误码验证尝试耗尽后不得再成功核销；测试通过则**不动正确的同步代码**并以真实数字回报，测试失败则立即修并保留修复前失败输出。**新增并发测试无论结果都留仓**作回归守卫。这是本轮方法论要点：**当审查方与实施方的代码理解冲突时，优先产出可执行证据，而不是任一方凭读码取胜。**
两项 IMPORTANT 一并修（避免将来再开一轮）：Python OSS 失败日志改为只写 `bucketConfigured`、objectKey 的**用途段**（purpose）、operation/ossCode/httpStatus/requestId，绝不写桶名、完整 key 或 media_id（与 Java 侧 `OssStorageAdapter:125/132/142` 对齐），并一并评估 `storage.py:140` 的 `f"object not found: {object_key!r}"` 是否会外泄到日志或任务 `last_error`；Java 侧**冻结活体契约**——`supported=true` 时强制要求本次样本的 `liveness.passed` 存在、为 JSON boolean 且为 `true`，缺失/类型不符/为 false 一律拒绝（新码 `LIVENESS_NOT_PASSED`，保守映射 501），绝不把"能力支持"当"样本通过"，不提供任何跳过开关。如实标注：该分支今天**无法对真实服务端验证**（服务无活体能力、恒返回 `supported=false`），只能用 stub；活体真正落地时映射须重新评估。

### 17.9 第二十三轮：并发核销裁决结果（BLOCKER 不成立、生产代码零改动）与两项 IMPORTANT 修复
**裁决结果**：实施道按"先只写测试、不改生产代码"的顺序执行，测试**通过**，竞态未出现 ⇒ **`AliyunSmsCodeProvider.java` 本轮 `git diff` 为 0 行**，未做任何"加固式"改动（对正确的同步做无谓改动只有回归风险）。新增 `AliyunSmsVerifyConcurrencyTest`（194 行、3 项）并**永久留仓**作回归守卫：①**32 线程**经 `new CyclicBarrier(32)` + `newFixedThreadPool(32)`，每线程 `barrier.await(30s)` 后用**同一 `challengeId`** 与**从假 gateway 取得的正确码**调 `verify`，`invokeAll(60s)` 后 `future.get()` 传播异常，断言 `success==1`、`empty==31`、`returnedValues containsExactly(phone)`、`sessionCount==1`；②**200 轮 × 8 线程**（每轮新 phone/challenge + `ThreadLocalRandom` jitter）断言**每轮**恰一成功（排除单次运气）；③**16 线程**正确(8)/错误(8) 混合断言 `success ≤ 1` 且尝试上限语义未破坏。orchestrator 另**独立连跑该测试类 3 次**（三次 rc=0），并亲自复核测试构造确为真实并发而非顺序调用、断言非空洞。
**锁覆盖复核**（orchestrator 亲验）：`verify()` 的 `:180` `synchronized (challenge)` 临界区内依次为 `:181-183` consumed 检查 → `:184-187` 过期+remove → `:188-192` 尝试上限+remove → `:193-195` `MessageDigest.isEqual` 常量时间比较 → `:197-200` attempt 递增 → `:203` 置 `consumed=true` → `:204` remove → **`:205` 唯一返回手机号的 return（在锁内、在置位之后）**；`:384` `consumed` 为 `volatile`；`challenges` 为 `ConcurrentHashMap` 且同一 id 只 `put` 一次 ⇒ 并发 `get` 必返回同一实例、在同一 monitor 上串行。**结论：Oracle 的后果描述正确（`AuthController:106` 确实用返回值签发会话），但竞态前提不成立。**
**IMPORTANT（Python OSS 日志卫生）→ `4a5e52d`**：`storage.py:239-249`（该文件唯一 `mlog` 点）移除 `bucket=` 与 `objectKey=`，改为 `bucketConfigured=bool(bucket)` + `purpose`（objectKey 第二段；解析失败落 `"<unparsed>"`，**绝不回退完整 key**），保留 operation/ossCode/httpStatus/requestId，注释同步；`_build` 异常消息本就只含 code/status/request_id。`storage.py:140` 的 `object not found: {object_key!r}` **保留**，orchestrator 独立核实其不外泄（全仓 grep 仅命中定义处、无测试断言；`dmedia.py:526` 是唯一源图 `get` 调用点，`:529-530` 通用 except 返回**固定字符串** `f"storage read failed for view {view}"`，原消息被丢弃、不进日志或 `last_error`；`FilesystemStorageDouble` 仅 dev/test）。新增 3 项测试断言日志**不含**假桶名/完整 key/media_id/AK/SK 且**含**新字段；负向判别力（加回 `bucket=`/`objectKey=` ⇒ 3 项全 FAIL）已还原。
**IMPORTANT（活体样本级契约）→ `a6f7a50`**：`FaceServiceClient.java:167-170` 在 `supported=true` 时**强制**要求 `liveness.passed` 存在、为 JSON boolean 且为 `true`，否则抛新码 **`LIVENESS_NOT_PASSED`**（`retryable=false`、HTTP 501 保守映射，javadoc 注明活体落地时须重评估）；`InsightFaceCareVerifier.java:64-65` 映射为 `CAPABILITY_UNAVAILABLE`（属能力/前置条件不足而非比对结论，**绝不 MATCHED**）；契约形状冻结为 `liveness.passed` 并写入 javadoc 与 `B-face-java.md`；**全仓无任何跳过活体校验的开关**（`skipLiveness`/`skip-liveness`/`requireLiveness` 配置项 grep 计数 0）。六条测试覆盖缺失/false/类型不符/MATCHED/MISMATCH/既有 `supported=false` 原样通过。**如实声明：`supported=true` 分支今天无法对真实服务端验证**（服务恒返回 `supported=false`、无 `passed` 字段），只能用 stub。
**验证数字（orchestrator 亲自执行）**：Java `test-compile` rc=0、定向 114/0/0、**全量 587 run / 0 failures / 0 errors**（基线 577+10）；Python **全量 352 passed / 0 failed / 0 errors**（基线 349+3，零回归、既有测试零修改）、`--check`/`--once` rc=0、55432 引用 0、ephemeral 库已清理；两次 `git diff --check` rc=0；无遗留 JVM、端口空闲。
**提交链**：`2d9ee97`（face-service 鉴权/日志）→ `ffa4570`…（见 17.7）→ **`a6f7a50`**（Java：裁决测试 + 活体契约）→ **`4a5e52d`**（Python：日志卫生）＝本轮最终代码 SHA。
**方法论要点（本轮教训）**：当审查方与实施方对同一段代码的理解冲突时，**优先产出可执行证据**（并要求"先写测试、不改生产代码"以避免为迎合判定而破坏正确实现），而不是任一方凭读码取胜；同时**保留**审查方要求的测试作为永久回归守卫——即使裁决结果对实施方有利。

### 17.10 Oracle 第二十三轮 PASS-with-notes：本轮交付终结
Oracle **选 (A) 撤回**上一轮判的短信并发核销 BLOCKER，明确承认遗漏了 `verify()` 外层的 `synchronized (challenge)`，并裁定"不存在能击穿该 monitor 的正常交错序列"、新增的三项并发测试有效、**"未改正确生产代码、仅补永久回归测试是恰当处置"**。两项 IMPORTANT 均判闭合，`storage.py:118,140` 保留含 key 的内部异常**判可接受**（调用边界已净化，并提示后续新增调用方须遵守该净化边界）。**新发现：无**。**整合许可**：可将 `4a5e52d46ab2ca75853d21678216e87891014e1a` 作为本轮最终交付 SHA 交总协调整合；**不要求补跑验证**。**轮次边界确认**：无需再因该并发争点、日志措辞或测试精度发起重绑定轮次。
**Oracle 提出的未来事项（非阻塞）**：真实活体落地时须重新冻结"样本未通过"应映射 `QUALITY_REJECTED` 还是 `CAPABILITY_UNAVAILABLE`（当前 501/503 保守拒绝，不伪造 MATCHED）。
**本轮交付终结状态**：
- 最终代码 SHA **`4a5e52d46ab2ca75853d21678216e87891014e1a`**；本轮（自用户授权的供应商接入起点 `8f5b625` 之后）提交链：`07254a0`(短信) → `229476c`(Python OSS) → `20e2575`(Java OSS) → `55f666e`(Java 人脸) → `13f0f62`(人脸服务实现) → `0cc9f76`(人脸缺口方案) → `ffa4570`(face-service 鉴权/日志) → `11ff41c`(Java 四项) → `f75b5be`(Python 两项) → `2d9ee97`(deploy.sh) → `a6f7a50`(裁决测试+活体契约) → **`4a5e52d`**(日志卫生)。
- 验证数字（均 orchestrator 亲跑）：Java **587/0/0**、Python **352 passed**、face-service **97 passed**；`--check`/`--once` rc=0；契约/文档侧无本轮改动。
- 部署事实：`InsightFace-for-openvela` 在 dev.ai-skin 以用户级 systemd 运行（`ExecMainPID=3191727`、enabled、`Linger=yes`、只绑 `10.3.6.163:8010`），health 200 且 `liveness.supported=false`；决定性泄漏实测（探针 namespace/subject 在 journal 中命中 **0**、原始 uvicorn access 行 **0**、token 泄漏 **0**、只输出路由模板）；重启后约 18s 恢复；共享 8002/8003 的 PID 仍 1737/1738 且 active；数据目录仅自有 `openvela_faces.sqlite3`、`face_cache.pkl` 不存在；token/env 0600、data 0700。
- **持续披露但不阻塞（Oracle 与 orchestrator 一致）**：①`identity.enroll`（D 的 handler）遇 OSS 配置错误仍有限重试至 `max_attempts`，应由 **D 的所有者**加定向映射，不应改公共 runtime；②短信容量阈值尚未暴露为 Spring 配置（当前构造器默认各 10_000）；③真实活体落地时须冻结样本失败映射；④**生产启用真实 1:1 需总协调授权修改 `CareFaceVerifierProductionGuard`**（Oracle 建议以明确的"可信且生产就绪"marker 放行、而非按类名，且前提是活体先闭合）；⑤真实短信/OSS/成员人脸正向链路尚未用真实数据验证（需根用真实凭据 smoke，凭据不经会话正文）。
- **功能边界（须向根明确）**：因活体能力缺失且 B 侧刻意 fail-closed（恒发 `require_liveness=true`、无关闭开关、2xx 但 `supported=false` 亦拒绝），**insightface 模式下护理准入当前恒 `CAPABILITY_UNAVAILABLE`（503）**；人脸接入今天的实际可用能力是检测/质量/特征提取与命名空间隔离的注册/查询/删除，**不含任何准入判定**。
