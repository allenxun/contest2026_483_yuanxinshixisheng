# D 包交付说明（测肤、身份归档与方案生成）

## 提交

- **代码提交（唯一，未推送、未合并）**：`6b4f9ed82d4e828749f04082b79381362281ff49` @ `feature/mvp-assessments`（基线 `ccee6e2`，提交时间 2026-09-11T12:12:05+08:00；48 文件 +9322/−47）。
- 本文件与 `D-oracle.md` 以 report-only commit 提交（SHA 见 git log，不含代码改动）。
- **Oracle 门禁状态：BLOCKED（无结论）**——4 次调用均 401 token_expired，详情、会话 ID 与保留审查位置见 `backend/handoffs/D-oracle.md`。按 COMMON.md：未获得真实 Oracle 结论不视为完成；总协调 E 验收前须先补 Oracle 两轮结论。

## 范围与文件归属（全部在本 worktree，未触他包）

| 区域 | 内容 |
|---|---|
| `backend/web-java/.../assessments/`（新包，main 13 文件 + test 6 文件） | M3-A01~A06 六端点：Controller→ApplicationService→Repository；T13 幂等/T11 媒体受理/T12 交接按 A 基础模式（参照 SystemEchoController）；封闭 failure_code→retryable 映射；requiredViews 仅经 identity_result.quality；报告白名单投影仅取冻结 report_payload；孤儿媒体 cleanup 入队（MediaCleanupEnqueuer，5 接线点，尽力而为） |
| `backend/web-java/.../stub/NotYetImplementedController.java` + `StubEndpointsIT.java` | 恰删 6 个 M3 占位（其余 20 stub 仍 501）；IT 仅移除 M3-A03 条目 |
| `backend/worker-python/.../handlers/`（4 新 handler + dshared/ 8 模块） | assessment.analyze（质量/同人/1:N、确定性 candidate+PG 对账、结果图先归档后原子发布、T06+plan 交接）；identity.enroll（namespace 串行、先持久阶段后锁外调用、超时同 EntityId 对账恰一次注册、stale 输入不归属）；plan.generate（defer 等待、冻结快照唯一校验基线、严格白名单校验、ready 冻结、绝不写 K）；media.cleanup（两段式 deleting→deleted、五表引用扫描+T13 活性、幂等孤儿发现 discover_and_enqueue_orphans） |
| **公共文件（总协调 2026-09-11 授权 D 唯一负责人；集成时单独核对）** | ①`runtime/complete.py`：+`_DEFER` SQL + `complete_deferred()`（新增，未改既有函数）②`runtime/loop.py`：仅 process_job 完成分发分支（defer/success 二选一，StaleGeneration 两路一致）③`handlers/__init__.py`：仅 `HandlerResult.defer_seconds` 字段（向后兼容）+ 末尾追加 4 个 D 注册。claim.py/expire.py/renew.py/__main__.py/health/conftest **未动** |
| A 测试文件最小适配（2 处，集成知会） | `tests/test_sanity.py`：test_config_defaults 以 monkeypatch 隔离 DSN env（断言语义未变）；`tests/test_unsupported.py`：注册表断言改为 echo+4 个 D 类型已注册、B 类型（notification.deliver）仍未注册 |
| 未改动 | backend/contracts、db/migration、application*.yml、deploy、docs、他包代码 |

## 总协调裁定落实（2026-09-11 六条 + C/D 衔接）

1. 媒体边界术语"授权可读集合"：D 未建 Primary 策略（归 B）；D 侧约定（冻结报告引用/member-grant/当前指针/照片版本全量校验）已写协调文件并转达。
2. identity.enroll owner_id=namespace 级稳定 uuid5（`identity-namespace:{ns}`），uq_job_identity_enroll 全 namespace 串行；未改 A helper。
3. **requiredViews 唯一通道=T05.identity_result.quality.required_views**（Worker 属主、版本化）；failure_detail 回归纯内部诊断——Java 全代码无任何 failure_detail 读路径（grep 级可验）；retryable=Java 封闭 failure_code 映射（当前全终态码→false，true 预留）。
4. wait-hop 已撤销：等待=同一 job/同一 generation_revision 的 complete_deferred（租约围栏、原子退 attempt、旧 lease/重复 defer 拒绝）；3600s in-handler 阻塞与 max_attempts=2000 过渡补丁均已删除。
5. media.cleanup 入 D 范围：handler+Java 触发器+幂等孤儿发现函数齐备；周期接入归总协调（未动 __main__、无常驻进程）。
6. C/D 衔接（§E 约定）：input_snapshot 冻结 `capability.{microcrystal_id,capability_id,capability_revision,parameter_ranges,approved_regions,n_bounds}`+`report.{...}`+`model.{...}`；校验一律以冻结快照为基线（live 配置仅在 waiting 门与冻结时刻读取）；能力选择含设备参数包络覆盖检查（device ⊇ baseline）；C 不依赖 waiting 递增 generation_revision（worker 全程不增）。

## 测试证据（命令/退出码/时间/与候选代码关联）

### 提交后 SHA 绑定复跑（orchestrator 亲自执行，树前后 clean、HEAD=6b4f9ed）
- **Java**：workdir `backend/web-java`，`env MVP_A_PG_JDBC=jdbc:postgresql://127.0.0.1:55437/postgres MVP_A_PG_USER=postgres MVP_A_PG_PASSWORD=mvp_d_local mvn -B test` → **Tests run: 179, Failures: 0, Errors: 0, exit 0, BUILD SUCCESS**（2026-09-11T04:25:16Z→04:25:30Z）。
- **Python**：workdir `backend/worker-python`，`env MVP_A_PG_DSN=postgresql://postgres:mvp_d_local@127.0.0.1:55437/postgres MVP_A_PG_HOST_PORT=55437 MVP_A_PG_USER=postgres MVP_A_PG_PASSWORD=mvp_d_local MVP_A_PG_CONTAINER=mvp-d-pg .venv/bin/python -m pytest -q` → **125 passed, exit 0**（04:25:45Z→04:26:02Z）。
- **contracts（D 未改动，回归证明）**：workdir `backend/contracts`，jcs.py selftest / validate_samples.py / validate_responses.py --selftest / openapi_spec_validator → **4×exit 0**（04:26:17Z→04:26:20Z）。

### 实施期历史轮次（dirty 树 ccee6e2+变更，过程证据）
- Java：基线 137 绿（A 原状）→ v1 170 → 跟进轮 175 → 裁定轮 179（fix lane 终报+orchestrator 独立复跑双证，内容与 6b4f9ed 同）。
- Python：基线 47 绿 → v1 86 → robustness 93 → D-E2E-1 修复 95 → 裁定轮 107 → defer/C-D/cleanup 轮 **125**（实施会话+独立 audit 会话双执行；test_plan_generate 3× 无抖动）。

### E2E 活体链（证据 `.mvp-d-runtime/e2e-evidence.md`，未提交之运行文件；要点摘录于此）
- 执行环境：web@18087（源码 mvn package 构建）+ worker `--once`×4 周期 + mvp_d_dev@55437，全部替身提供方；start/end git 绑定一致（HEAD ccee6e2 + 同 status/diffstat）。
- 链：受理 202（T05/T03 指针 rev1/3×T11 owned/T12 schema_version=number/T13 succeeded）→ reliable_new→enroll（owner_id=uuid5 VERIFIED）→ 跨周期 PG 对账 enrolled_reconciled → 冻结报告发布（结果图 T11 available+content_hash）→ T06 waiting_inputs gen_rev=0 + plan:{id}:0 → ready target_count=30∈1..100、regions⊆approved、快照冻结含 ranges/regions/n_bounds、**K 三列未动(0/NULL/0)** → 查询矩阵（A03 200 no-store/A05 brief 200/A05 full 403/A06 rev"1"/APP 会话+grant→A04 1 项→A05 full 全字段/媒体 GET 404=A deny-all 预期）→ 重放 200 零新行指针不变 → report_ready 补拍 409（拒绝路径按设计产 1 cleanup 任务）→ DEVICE_OCCUPIED 409 → 恰 3 cleanup 任务 → worker 删 4 media+对象消失 → teardown 完整（端口清/库 drop/storage 删）。
- **绑定诚实声明**：E2E 运行于提交前的 dirty 树（ccee6e2+变更）。其与 6b4f9ed 的内容同一性由 git 证据链支持（E2E start/end status/diffstat 一致；暂存集=全部变更集且提交后无剩余；提交后树 clean；E2E 结束至提交之间仅只读检查与 git add/commit，无任何源编辑），**但 E2E 未在 6b4f9ed 上重跑，不声称最终 SHA 已独立复测 E2E**；可执行套件（Java/Python/contracts）已于提交后在 clean 树上复跑并 SHA 绑定（见上）。

## 真实 vs 替身（如实报告）

- 人脸/测肤/大模型三提供方均为**受控确定性替身**（FaceDouble/SkinDouble/PlanDouble，可注入故障），仅证明链路；阿里云形状适配器为**边界准备**：全部方法抛 ProviderNotActivated（SearchFace/CompareFace/AddFaceEntity+AddFace/DetectLivingFace/LLM 映射点已定义），**无真实凭据/PoC，绝无伪造业务效果或治疗参数**。
- 生产 fail-closed：environment=production 解析到 double → ProviderConfigError（任务按 DEPENDENCY_UNAVAILABLE 可重试失败）；aliyun 未激活同样 fail-closed。
- 指标/能力/参数基线（moisture 等 4 指标；mvp-double-capability、regions 4 项、intensity/duration/pulse_count、N∈1..100）为**文档化 MVP 受控占位**，待设备/算法团队批准口径替换（env 可覆盖：MVP_SKIN_METRICS_BASELINE / MVP_PLAN_CAPABILITY_BASELINE）。
- 真实接入前提：总协调授权凭据+阿里云 PoC（识别率/活体/索引可见性/费用）+设备团队批准基线；worker 生产存储仍 FilesystemStorageDouble（A 已披露限制，真实 OSS 归总协调/A）。
- 外部对账能力：enroll 超时按同 correlation/EntityId 查询对账、恰一次注册（测试证明）；崩溃孤儿经 discover_and_enqueue_orphans 幂等补偿（周期触发接线归总协调）。

## 复现命令与环境（E/集成用）

- 隔离环境：`docker run -d --name mvp-d-pg -e POSTGRES_PASSWORD=mvp_d_local -p 127.0.0.1:55437:5432 -v mvp-d-pg-data:/var/lib/postgresql/data postgres:16`；venv：worker `python3 -m venv .venv && .venv/bin/pip install -e '.[dev]'`。**严禁 5432/55432/55433/55436**；curl 一律 `--noproxy '*'`。
- 测试命令与 env 见上节（Python 必带 `MVP_A_PG_CONTAINER=mvp-d-pg`；Java 勿设 APP_STORAGE_DEV_DIR；**Java 与 Python 套件不可并发**——pytest 的 migrate.sh 调 mvn flyway 会与 web-java target/ 冲突产生假红）。
- D 专属 env 面：MVP_D_{FACE,SKIN,PLAN}_PROVIDER（默认 double）、MVP_IDENTITY_NAMESPACE（mvp-ns-1）、MVP_D_PROVIDER_CONFIG_REVISION、MVP_D_RESULT_IMAGE_MAX_BYTES、MVP_SKIN_METRICS_BASELINE、MVP_PLAN_CAPABILITY_BASELINE、MVP_PLAN_CAPABILITY_STALE_SECONDS（86400）、MVP_PLAN_WAIT_CHECK_SECONDS（30=defer 间隔）、MVP_D_PLAN_PROMPT_VERSION、MVP_D_ALIYUN_*（默认未激活）。
- Java 运行 cap：`app.assessments.max-request-bytes`（默认 33554432；容器级 multipart 32MB/10MB 为 A 的 application.yml 原值，未改）。

## 限制与未决（如实）

1. Oracle 两轮结论 BLOCKED（401）——恢复后按 D-oracle.md 保留位置执行，结论仅绑定 6b4f9ed；后续任何代码变化需复审。
2. 94 业务场景中 D 相关项（SC-02-*/SC-03-*/SC-C-* 等）归 E 独立验收，本包不标完成。
3. media.cleanup 周期触发/孤儿扫描接线归总协调（D 提供幂等 discover 函数+handler；崩溃于 ingest 后且无 Java 拒绝路径覆盖的孤儿需周期或运维触发发现）。
4. enroll 终态 failed 槽位按设计保持占用（uq 含 failed），需运维外部对账后置 cancelled/succeeded 释放（DD 9.3 受控恢复，非自动丢弃）。
5. defer 为 D 按授权新增的公共接口；B/C 接入业务 handler 时如需用等待语义应复用 complete_deferred（不得用诊断字段驱动），集成时由总协调确认。
6. 媒体业务读取（contentUrl 实际下载）待 B 的统一 @Primary MediaAccessPolicy；当前 A deny-all → E2E 中媒体 GET 404 为预期。
7. plan waiting 期间 SIGTERM：defer 不阻塞停机（无 in-handler 长等待）；运行中任务的在途外部调用按 A 租约/abort 语义处理。
8. 两处 A 测试文件最小适配（test_sanity env 隔离/test_unsupported 注册表断言）集成时可能与 B/C 的同类适配冲突，由总协调合并。

## 协调记录

`.mvp-d-runtime/coordination-request.md`（运行文件，git-ignored，由 Codex 监督者同步项目根 .coordination/D）：B 节媒体归属约定、C 节 defer 提案（已被授权落地取代）、E 节 C/D 衔接最终约定、F 节 defer 授权落实、G 节 Oracle 阻塞记录。关键裁定内容已内联本文件，不依赖运行文件存续。
