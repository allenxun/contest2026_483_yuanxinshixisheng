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
