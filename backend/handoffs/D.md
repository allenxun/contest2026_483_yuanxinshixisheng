# D 包交付说明（测肤、身份归档与方案生成）— 终版

## 门禁状态与提交

- **Oracle 门禁：PASSED**——R1（M3）`PASS`、R2（M4+公共接口）`PASS-with-notes` CONFIRMED-FINAL，双结论绑定同一最终代码 SHA；全 11 轮实调记录、发现闭合明细与残留披露见 `backend/handoffs/D-oracle.md`。
- **最终代码 SHA**：`dc955c0b109fc2c2693e980622512208e0fcdb9e`（branch `feature/mvp-assessments`，未推送、未合并；交总协调集成后由 E 验收）。
- 提交链（基线 `ccee6e2`）：`6b4f9ed` 实现（48 文件 +9322/−47）→ `5c1d419` 报告1 → `4a05e48` R1-1 记录 → `b2d4a79` 修复1（B1-B3/I1-I3/S1）→ `c051577` 修复2（N1/N2/SUG①）→ `4ac4835` 修复3（F1）→ `c5b78d8` 修复4（G1/F2 裁定）→ `dc955c0` 修复5/最终代码（L.1 成功守卫+L.2 health 端口+判别性强化）→ 本文件与 D-oracle.md 终稿为 report-only 提交（SHA 见 git log）。
- E2E 活体链：r6@dc955c0 **PASS**（最终权威）；r5@c5b78d8、r3@c051577、r2@b2d4a79 PASS；r4@4ac4835 因 orchestrator 侧并发干扰被撤销认证（如实披露，双 oracle 核可处置）。

## 范围与文件归属（全部本 worktree，未触他包业务代码）

| 区域 | 内容 |
|---|---|
| `backend/web-java/.../assessments/`（main 13 + test 6 文件） | M3-A01~A06：受理（T13 幂等/T11 媒体受理/T12 交接，A 基础模式）、互斥（T03 锁→T07 检查→stopped/DEVICE_OCCUPIED 映射）、补拍（版本/视角/merged 三视角防御）、查询矩阵（云台当前指针/APP grant/统一 404 不泄存在性）、报告白名单投影（仅冻结 report_payload；requiredViews 唯一通道=identity_result.quality；failureCode 封闭白名单 9 码）、孤儿 cleanup 入队（5 接线点，尽力而为） |
| `backend/web-java/.../stub/` 两文件 | 恰删 6 个 M3 占位（其余 20 stub 仍 501）；IT 仅移除 M3-A03 条目 |
| `backend/worker-python/.../handlers/`（4 handler + dshared/ 9 模块） | assessment.analyze（质量/同人/1:N、确定性 candidate+PG 对账 enrolled_reconciled、两段归档 digest-first、原子发布+T06/plan 交接）；identity.enroll（namespace uuid5 串行、先持久阶段后锁外调用、超时对账恰一次注册、stale 不归属、link 守卫）；plan.generate（defer 等待、冻结快照完整契约校验为唯一基线、设备能力覆盖检查、严格白名单校验、ready 冻结、K 绝不写）；media.cleanup（两段删除、单事务锁后全引用扫描、幂等孤儿发现 discover_and_enqueue_orphans）；dshared：providers（替身+阿里云 fail-closed 边界）/dconfig/denqueue/dmedia/dfence/jsonschema_support/resolve/constants |
| **公共文件（总协调三次授权，D 唯一负责人；集成单独核对）** | `runtime/complete.py`（complete_deferred+_DEFER；complete_failure business_tx；四守卫 clock_timestamp）、`runtime/loop.py`（defer 分发+JobFailed 透传）、`handlers/__init__.py`（HandlerResult.defer_seconds+JobFailed.business_tx+D 注册 4 条目）。claim/expire/renew/__main__/health/conftest 全程未动 |
| A 测试适配 4 处（集成知会） | test_sanity（env 隔离）、test_unsupported（注册表断言）、test_complete（+4 纯增量）、test_health（端口 0 OS 分配回读，L.2 授权，根治与 E 活体 18081 冲突） |
| 其他 | `.gitignore` +`/.cortexkit/`（监督者指示条目）；contracts/迁移/application yml/deploy/docs 未动 |

## 总协调裁定与授权落实（全部闭环）

六条裁定（2026-09-11）：①媒体边界术语"授权可读集合"（B 实施，D 约定已转达）②namespace 级稳定 uuid5 enroll owner③requiredViews 唯一通道 identity_result.quality（Java 零 failure_detail 读路径，grep 级核验）④wait-hop 撤销→complete_deferred（等待不耗 attempt、同 job/同 generation_revision、旧 lease/重复 defer 拒绝、原子退计数）⑤media.cleanup 归 D（handler+Java 触发器+幂等发现函数；周期接线归总协调）⑥边界接受。C/D 衔接 §E：input_snapshot 冻结 capability.{microcrystal_id,capability_id,capability_revision,parameter_ranges,approved_regions,n_bounds}+report+model；校验仅用冻结基线；能力覆盖 device⊇baseline；C 不依赖 waiting 递增代次。增量授权：N2 complete_failure business_tx（H/I 节）；§302 L.1 _COMPLETE_SUCCESS 墙钟守卫+L.2 test_health 端口+L.3 全量无 deselect 证据——均已落地并经最终 Oracle 覆盖。**最终墙钟纪律：四条完成守卫（成功/重排/失败/等待）全部 clock_timestamp()，过期领取者任何路径不能提交业务或任务状态。**

## 测试证据（命令/退出码/UTC/SHA 绑定；最终 SHA dc955c0，clean 树前后 dirty=0）

- Java：workdir `backend/web-java`，`env MVP_A_PG_JDBC=jdbc:postgresql://127.0.0.1:55437/postgres MVP_A_PG_USER=postgres MVP_A_PG_PASSWORD=mvp_d_local mvn -B test` → **183/0/0 exit 0**（08:35:50Z→08:36:06Z）。
- Python：workdir `backend/worker-python`，`env MVP_A_PG_DSN=postgresql://postgres:mvp_d_local@127.0.0.1:55437/postgres MVP_A_PG_HOST_PORT=55437 MVP_A_PG_USER=postgres MVP_A_PG_PASSWORD=mvp_d_local MVP_A_PG_CONTAINER=mvp-d-pg .venv/bin/python -m pytest -q` → **175 passed 真 exit 0 零 deselect**（08:36:06Z→08:36:30Z）；同内容 fix-lane 175 绿+时序集 3×12 稳定+health 在外部占 18081 下独立通过证明。
- contracts（D 未改动，回归）：jcs selftest 26/samples 50/responses 10/openapi → **4×exit 0**（08:36:30Z→32Z）。
- E2E r6@dc955c0（权威）：全链 a-i+累计断言集（brief 省 metrics/multipart 三类 400/对账链/归档恰 2 行 2 对象且行 hash==存储字节 sha256 实测/cleanup 链恰 3 任务→deleted/K 三列未动/gen_rev 恒 0）+成功守卫活体（全 job succeeded、五周期日志 stale_generation=0）；绑定 start=end dirty=0；teardown 完整。证据 `.mvp-d-runtime/e2e-evidence.md`（运行目录，监督者同步）。
- 历史轮次与逐轮证据见 D-oracle.md 证据矩阵。

## 真实 vs 替身（如实报告）

- 人脸/测肤/大模型三提供方均为**受控确定性替身**（可注入故障），仅证明链路；阿里云形状适配器为**边界准备**：全方法 ProviderNotActivated（SearchFace/CompareFace/AddFaceEntity+AddFace/DetectLivingFace/LLM 映射点已定义），无真实凭据/PoC，**绝无伪造业务效果或治疗参数**；production+double→fail-closed。
- 指标/能力/参数基线（moisture 等 4 指标；mvp-double-capability、regions 4、intensity/duration/pulse_count、N∈1..100）为**文档化 MVP 受控占位**，env 可覆盖，待设备/算法团队批准口径替换。
- **真实接入前提**：总协调授权凭据+阿里云 PoC（识别率/活体/索引可见性/费用）+设备团队批准基线+**按冻结 model provenance 选择供应商或 mismatch fail-closed（Oracle R2-SUG②，激活前必须落实）**；worker 生产存储仍 FilesystemStorageDouble（A 已披露限制，真实 OSS 归总协调/A）。
- 外部对账能力：enroll 超时同 correlation/EntityId 对账恰一次注册；崩溃孤儿 discover_and_enqueue_orphans 幂等补偿（周期触发接线归总协调）。

## 复现命令与环境（E/集成用）

- 隔离环境：`docker run -d --name mvp-d-pg -e POSTGRES_PASSWORD=mvp_d_local -p 127.0.0.1:55437:5432 -v mvp-d-pg-data:/var/lib/postgresql/data postgres:16`；venv：worker `python3 -m venv .venv && .venv/bin/pip install -e '.[dev]'`。**严禁 5432/55432/55433/55436**；curl 一律 `--noproxy '*'`；勿碰 E 的 18081/18082。
- Python 套件必带 `MVP_A_PG_CONTAINER=mvp-d-pg`；Java 勿设 `APP_STORAGE_DEV_DIR`；**Java 与 Python 套件不可并发**（pytest 的 migrate.sh 调 mvn flyway 与 web-java target/ 冲突假红）。
- health 测试已改端口 0 OS 分配（不依赖固定端口）；D 专属 env 面：MVP_D_{FACE,SKIN,PLAN}_PROVIDER（默认 double）、MVP_IDENTITY_NAMESPACE、MVP_D_PROVIDER_CONFIG_REVISION、MVP_D_RESULT_IMAGE_MAX_BYTES、MVP_SKIN_METRICS_BASELINE、MVP_PLAN_CAPABILITY_BASELINE、MVP_PLAN_CAPABILITY_STALE_SECONDS（86400）、MVP_PLAN_WAIT_CHECK_SECONDS（30=defer 间隔）、MVP_D_PLAN_PROMPT_VERSION、MVP_D_ALIYUN_*（默认未激活）。
- Java 运行 cap：`app.assessments.max-request-bytes`（默认 33554432；容器级 multipart 32MB/10MB 为 A 原值未改）。

## 限制与未决（如实）

1. 94 业务场景中 D 相关项归 E 独立验收，本包不标完成。
2. media.cleanup 周期触发/崩溃孤儿扫描接线归总协调（D 提供幂等 discover 函数+handler+验证证据）。
3. enroll 终态 failed 槽位保持占用（uq 含 failed），受控恢复=运维对账后置 cancelled/succeeded（DD 9.3，非自动丢弃）。
4. owned pending 结果图行（终态失败任务遗留）保留可追踪、现行孤儿规则不清理（行存在即可发现；dmedia docstring 披露）。
5. defer/complete_failure(business_tx)/success 守卫为 D 按授权新增的公共接口；B/C 接入业务 handler 如需等待/原子终态语义应复用（不得用诊断字段驱动）；集成时由总协调确认。expire/claim 调度语义未扩围（按裁定）。
6. 媒体业务读取（contentUrl 实际下载）待 B 统一 @Primary MediaAccessPolicy（当前 A deny-all→媒体 GET 404 为预期）。
7. 两处历史协调事项已由裁定闭环：N2 公共扩展（L.1 落地）、F2 墙钟（四守卫统一）；无遗留待裁定项。
8. r4@4ac4835 E2E 撤销认证事件（orchestrator 侧干扰）已在 D-oracle.md 如实披露；最终权威活体证据=r6@dc955c0。

## 协调记录

`.mvp-d-runtime/coordination-request.md`（运行文件，git-ignored，Codex 监督者同步项目根 .coordination/D）：B 媒体归属约定 / C defer 提案 / E C-D 衔接最终约定 / F defer 授权落实 / G 认证阻塞 / G2 报告收尾 / G3 恢复尝试 / G4 R1 结论 / H N2 提案 / I N2 授权受理 / J 第三次裁定受理 / K 端口冲突通报（已由 L.2 根治）/ L 第四次授权受理。关键裁定内容均已内联本文件与 D-oracle.md，不依赖运行文件存续。
