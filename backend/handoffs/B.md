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
