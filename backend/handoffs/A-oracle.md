# A-oracle.md — A 包 oracle 独立审查报告

- **reviewedCommit（最终代码 SHA）**：`f6e500e474954781d3438188b6fdd389e61682e7`（round-6 有界复审 **PASS**，Findings=[]、blockingFindings=[]；round-5 FAIL @1ba984e 的 BLOCKER 经 f6e500e 修复并由 round-6 确认有效闭合；round-4 PASS-with-notes @bfd2dc3 与 round-3 全量 PASS-with-notes @26d97fb 对各自未变更部分继续有效；branch `feature/mvp-foundation`；本文件仅随 report-only commit 提交，不改代码）
- 审查者：本机 OpenCode omo-slim 配置的 `oracle` 子代理（会话 `ses_f7523570cffeGdu61d3BzOYo94`，只读，**六轮**：round-1 @f7e75c1 = FAIL(blocked)，round-2 @bf393aa = FAIL，round-3 @26d97fb = PASS-with-notes，round-4 @bfd2dc3 = PASS-with-notes（blockingFindings 空，有界复审），round-5 @1ba984e = FAIL（1 BLOCKER：校验器转换不严格），round-6 @f6e500e = **PASS（blockingFindings=[]）**）
- 审查依据：backend/doc/tasks/A-foundation.md、COMMON.md、技术/数据/详细设计、API 设计、测试需求决策记录、交付代码、真实测试证据（orchestrator 在对应 SHA 实际执行；oracle 只读评估）
- 代码提交链：`2b786f7`（实现 159 文件）→ `f7e75c1`（清理误提交 LSP 工件）→ `bf393aa`（round-1 修复 38 文件 +965/−123）→ `26d97fb`（round-2 修复 29 文件 +828/−176）→ `bfd2dc3`（round-4 E 驱动有界修复 4 文件 +256/−12）→ `1ba984e`（契约修订：严格 OAS 3.0.3 nullable + 严格响应校验 10 文件 +332/−20）→ `f6e500e`（round-6 修复：转换器严格化+旧/新形判别回归+finishedAt/leaseRevision 内联+harness 硬化，3 文件 +124/−24，**最终代码 SHA**）；报告提交：`fc4b311`（首版）→ `617354d`（修订）→ `6bae22f`（round-4 报告）→ `08e5e3f`（round-5/6 报告）→ 本次（头部一致性修订，report-only，SHA 见 git log，均不含代码改动）

---

## Round 1 @ f7e75c1c489a9233b0e239e4b38ecd53ffe63029 — **FAIL (blocked)**

> 审查为只读；测试结果为 orchestrator 提供的证据（acceptance 24/24、Java 99、Python 43 @f7e75c1），oracle 未重跑。

### 证据评估（验收行覆盖）

| A-foundation 验收/交付行 | 覆盖检查 | 充分性/缺口（round-1） |
|---|---|---|
| 可构建启动 Java/Python；健康检查、有限连接池、镜像 | d/e/f0/f10; Docker builds | 基本充分；worker 在途停机未演练 |
| 14 表迁移、FK/UNIQUE/CHECK；真实 PG；重复启动无破坏 | a, b1–b6; 迁移 IT | 部分：仅重复 migrate，未真正重启应用；未建立 DATA 全等价 |
| 27 API、bigint、multipart、分页、错误码、job schema；不给假 200 | c1–c3, d/JCS, f3/f8 | 部分：OpenAPI 结构校验漏掉 INTERNAL 枚举不一致 |
| 认证上下文、端口/替身、生产 fail-closed、无效认证拒绝 | f1/f2/f5; AuthFlowIT; FailClosedTest | 授权生命周期不充分：disabled 账号/轮换 revision 未复核 |
| T13、媒体基础、T12 运行时、handler 接入点 | f4/f6/f7/f9; 双端套件 | 基本流程覆盖；媒体授权测试固化了跨主体访问；崩溃恢复可超 max_attempts |
| 写边界、配置/文档、无密钥 | 静态检查; compose; 镜像 | 基本充分；compose 默认端口违反 worktree 隔离 |

### 模块结论（round-1）

1. **DB 迁移与 schema — BLOCKER**：`V1__create_tables.sql:225-235` controller_type 未强制按类型归属（app 无 account/installation 可入库；acceptance 种子即此非法形状）；`V1:286-289` active destination 未要求非空 registration；JSONB 多数列可无 schema_version（仅 T12 查 key 存在）；MediaService 写无版本 storage_metadata。NOTE：恰 14 表、无会话表、无 CASCADE、循环 FK 均在 V2、关键唯一/部分索引齐全。
2. **Contracts — BLOCKER**：`openapi.yaml:1937-1968` ErrorCode 枚举缺 INTERNAL，而真实 500 信封使用它（`ErrorCode.java:48`）→ 实际 500 响应违反自家契约。NOTE：34 操作齐（27 业务+5 基础+2 echo）；payload schema 严格；JCS 双端字节兼容（15 向量；补充平面向量缺）。
3. **Java foundation — BLOCKER**：`FoundationConfig.java:53-57` 全 profile 默认 AllowAuthenticatedMediaAccessPolicy → 任意已认证主体可读任意媒体（MediaFoundationIT 固化为成功断言）；拒绝走 403 泄露存在性。`BearerAuthFilter.java:70-83` 信任 provider 快照，不复核 accounts.status/auth_revision 与 gimbals.credential_version；AuthController 对 disabled 账号续发会话。NOTE：任意 accountId/installationId 不能认证；prod fail-closed 生效；T13 语义正确（hash 先于租约、重放投影、代次守卫）；26 stub 401→501；无 B/C/D 业务、无 JOIN。
4. **Python T12 — PASS-with-notes**：MAJOR：claim 不查 attempt_count<max_attempts 且 expire 恒 requeue → 崩溃循环可超上限；config.retry_max_attempts 未被生产代码消费（JobEnqueuer 硬编码 5）。NOTE：单表+代次守卫 SQL 正确；恢复不可覆盖新领取者；陈旧代次业务写同事务回滚；不支持类型终态隔离；日志不漏 payload。
5. **Deploy/config — PASS-with-notes**：MAJOR：compose PG 主机绑定默认 5432，违反 worktree 隔离。NOTE：4 服务/健康检查/media 卷/非 root/池 10/5 齐；版本已记录；无真实凭据（仅 change-me/123456/mvp_a_local 文档化占位）。
6. **Tests/acceptance 映射 — PASS-with-notes**：MAJOR：重复启动仅覆盖 re-migrate；MediaFoundationIT 固化跨主体读取为成功；auth 测试缺 disable/auth_revision/凭据轮换；迁移测试缺新约束负例。NOTE：ephemeral DB 隔离与清理可信；T12 陈旧代次回滚用真实 media_objects 哨兵非同义反复。

### 对抗性抽查回答（round-1 摘要）

26 stub 无假 200；媒体端点可跨主体泄露字节；任意身份串不能认证但 disabled/旧 revision 会话仍有效；陈旧代次不能提交、恢复不可覆盖新领取者；T13 重放投影不重做副作用、hash 冲突先于接管；无 CASCADE/无第 15 表，但 controller 归属/registration/schema_version 偏离 DATA；JCS 对已列向量字节兼容（缺补充平面）；密钥扫描仅文档化占位；提交范围无 B/C/D 实现、未改 backend/doc。

### blockingFindings（round-1）

1. 媒体内容对任意已认证主体全局可读，且拒绝语义泄露存在性（403 vs 统一 404）。
2. 认证不强制本地账号 status/auth_revision 与设备 credential_version 复核。
3. care_executions 可缺失 controller_type 所要求的控制端身份。
4. OpenAPI ErrorCode 缺 INTERNAL → 真实 500 信封违反契约。

**Overall（round-1）：FAIL (blocked)** — 基础实质且大体自洽，真实 PG/T12/T13 证据有效；但默认媒体授权为跨主体数据泄露、认证撤销代次未强制、执行归属可在 DB 边界非法、错误契约拒绝真实 500。须在 A 门禁 B/C/D 集成前修复。

---

## 修复记录（commit bf393aa，fix lane 完成，orchestrator 复核）

| Finding | 修复 | 验证 |
|---|---|---|
| B1 | OwnerBasedMediaAccessPolicy 默认（uploader_type/ref 含 installation 匹配）；allow-any-authenticated 仅 dev 显式开且 production 启动拒绝；拒绝/缺失一律 404 RESOURCE_NOT_VISIBLE（无 403） | MediaFoundationIT 重写（owner 200/他人 404/同账号异安装 404/pending/unknown 404/匿名 401）；mvn 107 绿 |
| B2 | PrincipalRevalidator 每请求单行查询（无 JOIN/锁）：APP→accounts.status+auth_revision 快照比对；GIMBAL→credential_version+行存在；不符 401 SESSION_INVALID；签发/刷新拒绝 disabled | RevocationIT 4 测试（中途禁用、revision 递增、云台凭据轮换、disabled 刷新） |
| B3 | V1 ck_execution_controller_ownership（DATA T07 语义） | FlywayMigrationIT (g)；acceptance b7；mvp_a_dev 活体负例拒绝 |
| B4 | openapi.yaml:1969 枚举补 INTERNAL | openapi_spec_validator OK |
| M5 | ck_destination_active_fields：active → registration<>'{}'（DD T09） | 迁移 IT (h)；acceptance b8 |
| M6 | V1 共 27 个 JSONB 列 schema_version CHECK（F/N/S 约定+文档化自由格式例外）；MediaService storage_metadata 带版本；IdempotencyService.ensureSchemaVersion；列决策表入 contracts/decisions-notes.md §10 | 迁移 IT (i)；种子/测试修正 |
| M7 | claim/recover/release 三路径均尊重 attempt_count<max_attempts；到顶 → failed RETRY_LIMIT_EXCEEDED（同代次守卫） | tests/test_attempt_ceiling.py 4 测试（max_attempts=1 崩溃循环） |
| M8 | app.jobs.max-attempts（JOB_MAX_ATTEMPTS 默认 5）→ JobEnqueuer INSERT；worker retry_max_attempts 文档化为入队镜像值且被 conftest.enqueue 实际消费 | mvn/pytest 绿 |
| M9 | compose:27 = 127.0.0.1:${MVP_A_PG_HOST_PORT:-55432}:5432（仅回环）；.env.sample=55432+注释 | docker compose config VALID |
| M10 | acceptance f0 = 启动→UP→SIGTERM→再启动→UP+Flyway no-op（两次 PID 记录）；临时目录移入 backend/tests/.work 前缀校验清理 | 26/26 运行实证 |
| minor13 | 第 16 向量 supplementary-plane-key-utf16-order（😀 键，jcs.py 实算重生成） | 双端向量测试绿 |

修复期间发现并修正的次生缺陷：AppProperties.Media record 访问器编译错误；FlywayMigrationIT 旧双占用用例形状更新为合法控制端形状。

**修复后证据（orchestrator 独立复跑 @bf393aa，树前后 clean）**：`bash backend/tests/run-acceptance.sh` → **ALL PASS 26/26，SCRIPT_RC=0**（内嵌 Java mvn 107/107、Python pytest 47/47、contracts selftest 26 checks + validate_samples 37 checks/16 vectors + openapi VALID）；mvp_a_dev 以新 V1 重建（history 2 版本 success，负例活体拒绝，数据清空）；compose config VALID（55432 回环绑定）。

---

## Round 2 @ bf393aa181b9772ec54eb4fdbbcf856b227771b6 — **FAIL**（2 blockers 残留）

> 只读源码复审；未执行测试、未用 git diff。新鲜测试证据（Java 107 / Python 47 / acceptance 26/26 @bf393aa、树 clean 绑定）由 orchestrator 提供。

### 逐项核验（round-1 findings）

| Finding | 结论 | 证据与对抗评估 |
|---|---|---|
| B1 媒体授权 | **PARTIAL — blocking** | OwnerBasedMediaAccessPolicy.java:24-31 已拒绝他人/异安装；MediaController.java:41-51 统一 404。但"上传者即有权"覆盖任意 purpose，无报告接纳/当前授权/当前任务校验——直接违反 openapi.yaml:1544-1551（不得仅凭上传者下载核验/未归档图片）；MediaFoundationIT.java:111-119 仍断言未接纳 GRANT_FACE 可读 |
| B2 认证复核 | **PARTIAL — blocking** | PrincipalRevalidator.java:30-47 正确（单 PK 查询，无锁/JOIN）；BearerAuthFilter.java:74-86 在所有受保护控制器前调用。但 InMemorySessionDouble.java:86-100 刷新时**收养新 DB revision** 而非拒绝旧 revision → 旧刷新凭据可撤销账号级失效 |
| B3 控制端归属 | FIXED | V1:290-299 实现 DATA T07 必填/禁填族；非空 installation 语法属应用层 |
| B4 INTERNAL | FIXED | openapi.yaml:1969 |
| M5 active registration | FIXED（就所报缺陷） | V1:369-376；供应商侧有效性属未来 handler |
| M6 JSONB 版本 | PARTIAL | 列 CHECK+版本化写入实质落地（V1:44-47,66-67,208-215,435-436；MediaService.java:99；IdempotencyService.java:146-147,170,224-228）；但 jsonb_exists 放过数组含 "schema_version" 与 null/字符串版本；诊断列豁免（decisions-notes.md:145-148）vs DATA"所有 JSONB"措辞——豁免批准 UNVERIFIED |
| M7 崩溃循环上限 | FIXED | claim.py:22-26 排除耗尽行；expire.py:20-50 到顶终态 failed、有预算才 requeue；release :53-83 同样守上限；test_attempt_ceiling.py:28-85 四测试 |
| M8 可配上限 | PARTIAL | application.yml:74-76 + JobEnqueuer.java:81-92 真实接线；worker 变量已明确为测试镜像（config.py:72-79）。**compose 未向 web 传 JOB_MAX_ATTEMPTS**（docker-compose.yml:34-48） |
| M9 PG 端口隔离 | FIXED | compose:25-27 仅回环 127.0.0.1:55432；.env.sample:10-12。注意：勿与已占 55432 的开发容器并行运行 compose pg |
| M10 重启实证 | FIXED | run-acceptance.sh:330-343 启动→UP→停→再启动→no-op 校验；清理 :115-128 前缀限定；SIGKILL/建立失败场景在保障范围外 |
| minor13 补充平面 | PARTIAL | vectors.json:179-186 第 16 向量存在、Java 要求 16（JcsVectorsTest.java:38）；但 ASCII+补充平面键在码点序与 UTF-16 序结果相同——需加 U+DFFF 以上 BMP 键（如 U+E000）与 emoji 并置才能真正区分两种排序算法 |

### 回归扫描发现

- **BLOCKER R2-1**：上传者身份仍被当作业务许可（跨主体泄露被收窄而非替换为所需访问规则；云台上传者在任务被替换后仍可读取——策略从不读当前任务状态）。A 包更安全默认=**业务策略安装前 deny-all**；owner-only 便利须显式限定 test/dev。GRANT_FACE 正向测试改为断言拒绝，补未接纳媒体/当前任务替换负例。
- **BLOCKER R2-2**：刷新复活已撤销认证代次。复现：登录→auth_revision 递增（status 仍 active）→用原 refresh token 刷新→拿到带新 revision 的 access token→受保护请求通过认证。RevocationIT.java:59-73 只测旧 access token 拒绝与新登录，未测旧 refresh token 拒绝。刷新前必须比对会话存储 revision 与 DB revision，不符=拒绝；该不变量写入 SessionProvider.java:30-32 供真实提供方遵循。
- **IMPORTANT R2-3**：新增 DB 认证查询无过滤器级错误渲染——BearerAuthFilter.java:74-86 在异常处理器之外调用 provider/复核，DB 故障在 MVC 之前抛出，controller advice 无法给出承诺信封（仍 fail-closed，但错误契约不保）。需对失败复核/provider 断言净化信封+X-Request-Id。
- **IMPORTANT R2-4**：JSONB 校验仅查 key 存在——`["schema_version"]` 数组可过 ck_job_payload_schema（V1:466）；ensureSchemaVersion 放过 {"schema_version":null}。应在本基础承诺校验处要求对象/类型有效版本，或显式把该校验指派给调用方并测试边界；诊断列豁免需"待确认"而非表述为 DATA 完全合规。
- **IMPORTANT R2-5**：compose 未传 JOB_MAX_ATTEMPTS 给 web 服务（.env 变量不会自动注入容器）。
- **SUGGESTION**：bean 扩展路径——若其它策略 bean 令 @ConditionalOnMissingBean 跳过 FoundationConfig 工厂（63-69），production 开放开关检查也被跳过；应测试真实 B/C/D @Primary 覆盖接线。
- **NOTE**：T13 无回归——版本注入影响存储 result_summary 而非请求 hash；完成仍持状态/代次谓词（IdempotencyService.java:148-176）。

### 证据充分性（vs round-1 增量）

Java 107/Python 47 支持已演练行为；迁移+**真实重启周期**直接覆盖"重复启动"；b7/b8 增加有意义负例；f4/f6-f8+陈旧代次测试持续支撑跨语言代次要求；无效认证扩展到禁用/revision/设备轮换但**撤销 refresh 凭据负例缺失（真实绕过）**；16 向量跨语言通过但补充平面区分度弱；媒体负例改善但新正向测试仍验证契约禁止的行为；compose 端口修正获支持，**该 SHA 的新镜像/容器化 E2E 未提供**（round-1 镜像构建不验证已变更运行时）。

### 模块结论（round-2）

db_schema=PASS-with-notes（归属/registration 已正；版本校验豁免残留）· contracts=PASS-with-notes（INTERNAL 已正；媒体实现仍违反未变更契约）· **java_foundation=BLOCKER（媒体许可+刷新代次绕过）** · python_t12=PASS（上限三路径全修）· deploy_config=PASS-with-notes（端口已正；compose 缺新上限配置）· tests_acceptance=PASS-with-notes（证据可信扩展；安全负例不全）

### blockingFindings（round-2）

1. R2-1/B1：生产默认 uploader-only 媒体策略仍授予业务媒体契约禁止的访问。
2. R2-2/B2：旧 refresh 凭据可收养新 auth_revision、复活已撤销会话。

**Overall（round-2）：FAIL** — DB 完整性、重试上限、错误码一致性、重启验证实质改善；两个安全边界仍不完整：上传者所有权不构成充分媒体授权，刷新绕过账号级 revision 撤销。测试通过不能解决这两点，因为媒体测试背书了错误规则、revision 测试遗漏刷新路径。修正边界并补针对性负例后方可接受 A。

---

## 修复记录（round-3，commit 26d97fb，fix lane 完成，orchestrator 复核）

| Round-2 finding | 修复 | 验证 |
|---|---|---|
| R2-1 媒体授权 | 新增 DenyAllMediaAccessPolicy 为全 profile 默认（统一 404）；OwnerBasedMediaAccessPolicy 降为显式 `app.media.access-mode=owner-dev`（仅 dev/test）且对 face purposes（grant_face/execution_face/revalidation_face）即使上传者也拒绝；any-authenticated 为显式 dev opt-in；生产非默认模式由 ProductionFailClosedValidator 无条件拒绝启动 | MediaFoundationIT 默认上下文全 404 断言（含 GRANT_FACE 翻转为拒绝）；新增 OwnerDevMediaAccessIT（owner 200 非 face / 他人 404 / 同账号异安装 404 / 匿名 401 / face 404） |
| R2-2 刷新复活 | InMemorySessionDouble.refresh 比对会话快照 auth_revision vs 当前 DB 值；disabled 或不符 → 拒绝并撤销会话，绝不重新捕获；SessionProvider javadoc 写明真实提供方 invariant | RevocationIT 增加 oracle 精确复现：登录→递增 revision（active）→原 refresh token 401→旧 access 仍 401→重新 SMS 登录成功 |
| R2-3 过滤器错误信封 | BearerAuthFilter try/catch：provider/复核基础设施异常 → 503 DEPENDENCY_UNAVAILABLE（retryable=true）标准 ErrorEnvelope + X-Request-Id，异常仅服务端日志；401 语义不变 | 新增 FilterErrorRenderingIT（@Primary 失败复核器→503+信封+头）与 BearerAuthFilterTest（抛异常 provider 单测） |
| R2-4 JSONB 类型级 | V1 全部 27 个版本化 CHECK 强化为 `jsonb_typeof(col)='object' AND col ? 'schema_version' AND jsonb_typeof(col->'schema_version')='number'`（F/N/S 占位约定保留）；ensureSchemaVersion 仅在缺失时注入整数 1，present 非整数/非对象 → 400 INVALID_INPUT；decisions-notes §10 豁免明确标注"A 包建议待总协调确认"（不再声称 DATA 完全合规） | 迁移 IT 类型强化用例（数组/null/字符串拒绝，对象+整数接受）+ SchemaVersionBoundaryTest；mvp_a_dev 重建后活体负例：`["schema_version"]`/`{"schema_version":null}`/`"1"` 均拒，`{"schema_version":1}` 接受 |
| R2-5 compose 上限 | web 服务 env `JOB_MAX_ATTEMPTS: ${JOB_MAX_ATTEMPTS:-5}`；.env.sample+README（enqueue authority 注释） | docker compose config VALID 显示注入 |
| R2-6 bean 接线加固 | 生产拒绝逻辑移入无条件 ProductionFailClosedValidator（消费 AppProperties，与策略 bean 装配无关） | ProductionFailClosedTest：自定义 @Primary+prod+开放模式→启动失败；dev 自定义 @Primary 被实际使用（B/C/D 覆盖路径证明） |
| minor13 判别向量 | 第 17 向量 `bmp-above-dfff-vs-supplementary-code-unit-order`（U+E000 键 × 😀 U+1F600；UTF-16 序 emoji 代理对在前，码点序相反——真正判别两种算法）；期望哈希由 jcs.py 实算 | JcsVectorsTest 16→17；validate_samples 38 checks/17 vectors；worker 规范化测试绿 |
| M9 运行警示 | deploy/README：compose pg 与 mvp-a-pg 同绑 127.0.0.1:55432 严禁并行；冒烟用 MVP_A_PG_HOST_PORT=55434 | — |
| 容器化证据缺口 | 两镜像于最终态重建（21.89s）；compose 栈冒烟（project mvp-a-smoke，pg@55434）：pg/web/worker 全 healthy，web /actuator/health UP（18090），worker exec urllib /healthz UP，**栈内 HTTP echo：enqueued→queued→worker 处理→succeeded\|1**；down -v 全清，mvp-a-pg 未受影响。顺带修复既有打包缺口：compose worker 只读挂载 ../contracts:/app/contracts + MVP_CONTRACTS_DIR + depends_on web healthy | 冒烟输出记录于 fix lane 报告；compose config VALID |

修复后全链（fix lane 执行 + orchestrator 独立复跑）：Java **124/124**、Python **47/47**、contracts（selftest 26 checks + samples 38 checks/17 vectors + openapi VALID）、acceptance **26/26 RC=0**。

---

## Round 3 @ 26d97fbe908cb93c1fe366e28ba54a91c21b497c — **PASS-with-notes**（blockingFindings 空）

> 只读源码复审；未执行测试/shell/Git。SHA 绑定、执行结果与资源清理由 orchestrator 提供（acceptance 26/26 @26d97fb 树 clean 前后绑定、Java 124、Python 47、mvp_a_dev 重建负例、compose 冒烟）。

### 逐项核验（round-2 findings）

| Finding | 结论 | 证据与对抗评估 |
|---|---|---|
| R2-1 媒体许可 | **FIXED** | DenyAllMediaAccessPolicy.java:14-16 恒拒绝；FoundationConfig.java:64-75 默认选择；OwnerBasedMediaAccessPolicy.java:28-40 拒绝全部三个核验 face purpose；默认负例测试 MediaFoundationIT.java:102-162；owner-dev 成功用例隔离于独立配置；被检 Java 源中未发现绕过 HTTP 读存储的替代路径 |
| R2-2 撤销刷新代次 | **FIXED** | InMemorySessionDouble.java:88-106 比对存储 revision 与 active 账号行，不符拒绝，成功刷新保留（不重捕）旧 revision；RevocationIT.java:75-99 覆盖要求的 active 账号 revision 递增/旧 refresh 负例；重新 SMS 认证合法签发新代次。另见测试替身并发告警（回归节） |
| R2-3 过滤器错误信封 | **FIXED** | BearerAuthFilter.java:81-101 捕获 provider/复核运行时异常；:133-152 输出净化 503 DEPENDENCY_UNAVAILABLE、retryable=true、requestId 头；RequestIdFilter 仍先于认证排序；异常消息/堆栈不入 HTTP 响应；provider 与复核失败测试齐备 |
| R2-4 JSONB 边界 | **PARTIAL — substantially fixed** | 所有被检版本化 CHECK 现要求对象形态+显式 key+数值版本类型（V1:49-52,217-220,351,471）；数组/缺 key/JSON null/字符串版本均拒；IdempotencyService.java:231-244 另要求 Java JSON 节点为整型。SQL 仍接受小数/负数数值版本；诊断豁免仍为待决建议（decisions-notes.md:152-156） |
| R2-5 compose 入队配置 | **FIXED** | docker-compose.yml:49-50 向 web 注入 JOB_MAX_ATTEMPTS；存量行仍由持久化 max_attempts 治理（正确） |
| R2-6 bean 无关生产拒绝 | **FIXED** | ProductionFailClosedValidator.java:49-57 独立于默认策略创建检查不安全媒体配置；自定义策略无法抑制该检查；ProductionFailClosedTest.java:226-261 覆盖自定义策略+不安全配置及 @Primary 成功解析；未来自定义业务策略仍属受信实现需各自评审 |
| minor13 UTF-16 判别 | **FIXED** | vectors.json:189-194 真实混合 U+E000 开头键与 😀；UTF-16 将 emoji 高代理排在 U+E000 前，与码点序不同——具判别力；双端套件通过（证据提供）；哈希生成过程未独立观察 |
| 容器化执行缺口 | **FIXED（compose 交付口径）** | docker-compose.yml:82-87 只读提供 contracts 目录并设 MVP_CONTRACTS_DIR；:95-100 等待 web 健康/Flyway 后 worker 才启动；新鲜镜像构建+栈内 queued→succeeded echo 实证替代仅构建/--help；独立镜像限制保持显式 |

### 回归扫描发现

- **IMPORTANT — 测试替身 refresh/logout 竞态保留（非账号 revision 绕过）**：InMemorySessionDouble.java:80-106,110-120 的刷新与登出跨多个独立 map 操作；可能交错：refresh 捕获 old → logout 撤销该会话 → refresh 在登出后创建替换会话。原子移除 refresh 凭据防同一凭据双刷新，但未串行化 refresh vs logout。**仅作为 A 包显式保留的 dev/test 替身限制可接受**；真实提供方必须保证生命周期一致性，或在依赖并发登出测试前于替身内串行化该转换。
- **IMPORTANT — SQL 版本检查强制 "number" 而非"受支持正整数"**：如 `{"schema_version":1.5}` 可过 V1:471 谓词。不击穿严格 echo payload schema 或强化后的 T13 result-summary 边界，但不能声称 DB 级整数/版本有效性覆盖所有 JSONB 写入者。B/C/D 各写边界保持服务/schema 校验，或强化 SQL 谓词并补小数/负数版本负例。
- **IMPORTANT — 诊断 JSONB 豁免仍需决策**：decisions-notes.md:152-156 现已诚实标注未批准——修正的是合规声明而非偏差本身。业务写入者依赖该约定前，须记录总协调的接受或要求版本化诊断对象。
- **NOTE — 媒体与过滤器排序在交付默认下安全**：媒体控制器先查策略再 openContent，deny-all 因此阻止 HTTP 响应读取存储字节；认证/复核先于控制器执行，保持 401-before-501 与媒体认证；validator 阻止生产不安全媒体*配置*，但无法认证任意未来自定义策略代码。
- **NOTE — F/N/S 占位保持有意**：F 谓词显式允许 `{}`；N 允许 SQL NULL；S 要求版本化对象；强化未新破坏合法 F/N 占位。部分 S 列保留无法满足自身 CHECK 的 `{}` 默认——调用方必须显式提供 payload。
- **NOTE — 被检变更未见 T13 回归**：版本校验作用于 result summary 而非规范化请求 hash；未引入重放副作用或移除完成代次谓词。未变更文件的穷尽等价与 worker 运行时不可变性在无 diff 下 **UNVERIFIED**；新鲜 worker 套件支持行为连续性。

### 证据充分性（round-2 缺口闭合）

撤销 refresh 凭据=由精确新回归测试+124 测试 Java 运行闭合（并发 refresh/logout 为独立限制）；默认媒体许可=闭合（默认测试期望拒绝，非 face owner-dev 成功隔离于独立配置）；provider/复核失败信封=由专门失败测试+被检过滤器渲染路径闭合；JSONB 数组/null/字符串绕过=由强化谓词+迁移测试+活体 PG 负例闭合（小数版本与诊断策略如上限定）；compose retry 配置=由显式 web env 接线+渲染配置闭合；容器化 Java→Python 执行=由新鲜构建+该 SHA 真实栈内 echo 完成闭合；新鲜迁移/重启/约束/T13/job 代次/契约=新鲜 26 检查 acceptance+124 Java+47 Python 覆盖既往映射验收行（含真实重启）；清理与隔离=证据报告 ephemeral DB 清理、无 .work 残留、冒烟拆除、开发 PG 容器未动（未独立检查）。**acceptance 证据现足以支撑基础交接**——非 B/C/D 业务授权完成或真实提供方生产就绪的证据；存储级互操作与默认 HTTP 媒体访问的区分恰当。

### 披露残留评估

1. `any-authenticated` dev opt-in 提供 face 媒体 — **acceptable-for-A（带限制）**：显式、非默认、生产配置拒绝；仅限合成数据；绝不可表述为业务授权或用于真实用户试用。
2. 独立 worker 镜像需 contracts 挂载 — **acceptable-for-A**：compose 已提供依赖并有执行证据；独立启动文档须含挂载与环境变量；镜像本身非自包含。
3. 默认/自定义策略共存依赖 `@Primary` — **acceptable-for-A**：解析路径已测试；缺失/歧义限定令启动失败而非静默放行；B/C/D 须遵循文档化接入点。

### 模块结论（round-3）

db_schema=PASS-with-notes（数值版本边界+待决诊断豁免）· contracts=PASS-with-notes（判别向量已修；豁免决策待总协调）· java_foundation=PASS-with-notes（blockers 已修；dev/test refresh/logout 并发限制）· **python_t12=PASS**（新鲜上限/代次套件证据保持）· deploy_config=PASS-with-notes（compose 执行已验证；独立运行需 contracts 挂载）· tests_acceptance=PASS-with-notes（所需验收覆盖充分；上述限定保留）

### blockingFindings（round-3）

**[]（空）** — 本轮被检范围未发现残留验收阻塞项。

**Overall（round-3）：PASS-with-notes** — 两个 round-2 安全 blocker 均真实修正：默认媒体访问拒绝一切请求，刷新不能收养已撤销账号代次。过滤器失败现保留错误信封，compose 携带入队配置与 contracts 依赖，新鲜容器化执行闭合先前部署证据缺口。残留关切为有界基础限制或显式决策：测试替身 refresh/logout 并发、SQL numeric-vs-integer 检查、诊断 JSONB 豁免。**接受 A 用于交接**，记录上述 notes，不视为生产就绪的业务授权。

---

## 修复记录（round-4，commit bfd2dc3，E 验收驱动有界修复）

**缺陷（E 独立验收 @26d97fb 发现，证据 n2-http-repro.txt 只读核实）**：`GET /api/v1/system/echo-jobs/{jobId}` 将 `async_jobs.last_error` 原样投影至 `data.lastError`——种入 `{"code":"E_DIAG_MARKER","message":"Bearer E2E_DIAG_SECRET_MARKER_12345"}` → GET 200 marker_echoed=True；4058 字符长诊断原样外泄（raw_lastError_len=4058）。两条泄露路径：`parseError()` 成功时返回整棵 readTree、解析失败时返回原始字符串。

**总协调确认策略（修复边界）**：对外仅提供契约允许、安全稳定、有界的错误投影；内部诊断不原样返回；不得以截断原文充当脱敏。诊断 JSON 列仅内部（脱敏+限大小）；业务版本列仍保持服务/schema 整数校验（DD 本就要求不泄露供应商诊断、对外稳定业务码）。

| 变更 | 内容 |
|---|---|
| SystemEchoController.java | 新增 `record EchoJobLastError(String reason, boolean retryable)`；`EchoJobViewData.lastError` Object→该 record；**删除 parseError()**（grep 确认无 parseError/return raw）；`projectError()`+`mapReason()` 白名单映射：UNSUPPORTED_CONTRACT→unsupported_contract、RETRY_LIMIT_EXCEEDED→retry_limit_exceeded、handler_failed 为契约预留（当前 system.echo 无 JobFailed code，经 grep worker handlers 证实）；其余一切（未知/缺失/非字符串 code、非对象节点、非法 JSON、空）→ internal；retryable 仅当 JSON 布尔取值否则 false；**不投影** message/原始 code/retry_after_seconds/stack；有界性由构造保证（封闭枚举+布尔），非截断 |
| EchoLastErrorProjectionIT.java（新，5 测试） | ① E marker 泄露闭合（body 不含 E2E_DIAG_SECRET_MARKER/E_DIAG_MARKER/Bearer；lastError 键恰为 {reason,retryable}；reason=internal）② 4058 字符 message+stack/sql/retry_after_seconds 额外字段均不出现、retryable=true 保留 ③ 已知码映射 unsupported_contract 且 message 不外泄 ④ 非法/非对象 → internal（含直接调用 parse-failure 分支，绝不回显原文）⑤ succeeded job 不受影响（lastError null、attemptCount/leaseRevision 仍 bigint 字符串） |
| openapi.yaml | 新增 `EchoJobLastError` 组件（object、additionalProperties:false、required [reason,retryable]、reason 封闭枚举 [unsupported_contract, retry_limit_exceeded, handler_failed, internal]、描述注明有界投影非截断）；`SystemEchoJobView.lastError` → allOf+nullable（文件既有 3.0.3 风格）；其余端点/schema 未动 |
| decisions-notes.md §10 | 诊断列豁免更新为**已确认 by 总协调 2026-09-10**（仅内部、不原样返回、脱敏+限大小；业务版本列仍服务/schema 整数校验）+ 记录 echo GET 有界投影 |

**修复验证（实际执行 @bfd2dc3，orchestrator 复核提交范围=4 文件仅 web-java+contracts）**：`mvn test` **129/129**（124+5；EchoJobIT/EchoDedupIT 保持绿）；openapi_spec_validator OK；validate_samples 38 checks PASS；`run-acceptance.sh` **26/26 RC=0**（f6/f7/f8 echo E2E 绿）；**活体复现修复**（app 18080 dev + mvp_a_dev）：种入 E marker → GET 200 `data.lastError={"reason":"internal","retryable":false}`，marker_echoed=False、bearer_echoed=False、raw_code_echoed=False、raw_len 4058→319；测试行已清理、app 已停。未重建镜像（Dockerfile/运行依赖未变，不需要）。

---

## Round 4 @ bfd2dc3d84219b029255f4918027565a20fe5019 — 有界复审记录：**PASS-with-notes**（blockingFindings 空）

> 只读复审，未重跑测试；SHA 绑定、执行结果与提交范围为 orchestrator 提供的证据。范围仅限本有界变更；round-3 对其余部分的结论继续有效。

### 泄露闭合核验

| 泄露路径 | 结论 | 证据 |
|---|---|---|
| 原始 JSON 树回显 | **CLOSED** | 控制器 :174-184 仅将 `last_error::text` 输入 projectError；:197-214 构造新的类型化投影而非返回解析树 |
| 原始字符串兜底 | **CLOSED** | 解析失败与非对象输入返回固定 `"internal"`/`false`（:202-208）；无 parseError/原始字符串返回残留 |
| 不受控键集 | **CLOSED** | EchoJobLastError 恰含 reason+原始布尔 retryable（:104-105）；视图使用该类型（:92-94）；未发现 mixin/any-getter/多态序列化配置 |
| 输出长度依赖诊断内容 | **CLOSED** | mapReason 仅输出三个固定字面量（:217-225）；retryable 严格布尔（:211-213）；紧凑 lastError JSON 至多 57 ASCII 字节，与诊断长度无关——非截断 |

### 对抗性检查

封闭白名单（仅 UNSUPPORTED_CONTRACT/RETRY_LIMIT_EXCEEDED 特映射，其余→internal；asText 标量强转无法注入任意输出）；retryable 仅 JSON 布尔可为 true（字符串/对象/数组/数值/缺失均不可逃逸）；端点响应对象从不携带原始串/树，HTTP 键集断言实际演练 Jackson 序列化；404 缺行仍 RESOURCE_NOT_VISIBLE（:186-188），bigint 字符串与 RFC3339 转换保持（:180-183）。小差异：SQL NULL 与空白输入均返回 null（:198-199），而非修复摘要所述空白→internal——JSONB 存储不可能产生空白文本，非泄露。实现输出为契约枚举子集；handler_failed 预留当前不可达（已披露，非运行时违约）。decisions-notes.md:152-161 准确记录总协调确认的内部诊断/有界投影边界，未豁免业务版本校验。

### 测试真实性

5 用例均为真实回归：①E marker 精确复现（种入 code/Bearer 形态→HTTP GET→全响应排除+精确键集，EchoLastErrorProjectionIT.java:61-79）；②4058 字符+stack/sql/retry-delay 排除+固定 reason/retryable/键集（:84-107；无显式字节长度断言，但精确输出形状/值断言确立有界性）；③已知映射 unsupported_contract+message 排除（:112-124；retry_limit_exceeded 经代码审读，本用例未覆盖）；④JSONB 数组走 HTTP+非法 JSON 直接走 helper（:129-150，区分合法——PG 不能存畸形 JSONB）；⑤queued/succeeded 投影+null 错误（:155-175；时间戳断言 assertNotNull 偏弱，不证 RFC3339 文本有效——不影响泄露测试）。

### 回归扫描

- **IMPORTANT — nullable schema 语义存在歧义/不可移植**：openapi.yaml:2772-2774 沿用文件既有 `allOf:[$ref]+nullable:true` 风格，但 OAS 3.0.3 规定 nullable 仅在同一 Schema Object 有显式 type 时生效（被引组件亦要求 object）→ 严格消费方可能拒绝实现合法的 `lastError:null`。应改用真正可空的 schema 表示并以严格 OAS 响应校验器验证 null 响应（结构性 spec 校验不能证明此点）。【orchestrator 处置：非阻塞（blockingFindings 空）；本轮授权为"阻塞则修复复审"且有界修复后不得再动代码以维持 reviewedCommit==最终代码——记为下次获授权 A 契约修订的候选项，运行时行为（封闭枚举+null）不受影响】
- **SUGGESTION — 边缘断言强化**：补 retry_limit_exceeded 映射、非布尔 retryable、解析时间戳格式断言（既有测试已确立主要泄露闭合）。【同上记为后续候选】
- **NOTE — 被检调用方保持有界**：EchoJobViewData 无其他生产消费方；create/replay 路径不暴露诊断。提交级 worker/deploy/acceptance 脚本无改动在 oracle 侧 UNVERIFIED（未查 Git 历史）——orchestrator 已独立核验：提交范围恰 4 文件（web-java 2 + contracts 2），git show --stat 记录在案。

### 证据充分性

活体结果（固定 {reason,retryable}，marker/Bearer/raw-code 不存在）直接闭合 E 的 n2 复现；4058 字符回归测试+封闭投影构造证明非截断脱敏。提供的 **Java 129**、契约校验、**acceptance 26/26**（orchestrator 另于提交后独立复跑 26/26 RC=0，树前后仅 untracked handoffs）保持既有行为；nullable 响应告戒不由结构性校验器解决。**已部署镜像须纳入本提交后方可视为已修复**（bfd2dc3 后未重建镜像；dev/E 验证路径为源码运行，不受影响——部署前重建 web 镜像记为交接注意项）。

### blockingFindings（round-4）

**[]** — 本有界变更中未发现残留原始诊断泄露。

**Overall（round-4）：PASS-with-notes** — 原始树与原始字符串披露路径已移除，替换为封闭、有界投影；新 HTTP 回归测试忠实复现 E 缺陷并验证诊断与额外字段无法逃逸。接受本有界泄露修复，保留 nullable-schema 互操作 note；round-3 结论其余部分不变。

---

## 修复记录（round-4 后续契约修订，commit 1ba984e，总协调明确授权于当前范围）

round-4 PASS-with-notes 的 IMPORTANT note（echo lastError `allOf+nullable` 严格 OAS 3.0.3 歧义）经总协调授权立即修复（"核对接口契约"属本次授权范围，无需另等授权）：
- openapi.yaml `SystemEchoJobView.lastError` 改为内联 `{type: object, nullable: true, required: [reason,retryable], additionalProperties: false, reason 封闭枚举}`（type+nullable 同一 Schema Object，严格 3.0.3 合规）；`EchoJobLastError` 组件移除（仅单处引用，内联=单一事实源，枚举与实现封闭集一致）。
- 新增 scripts/validate_responses.py：OAS 3.0.3→JSON Schema 转换器 + Draft202012Validator，从文档实解析 `GET /api/v1/system/echo-jobs/{jobId}` 200 响应 schema（非硬编码副本）；CLI + --selftest（6 fixtures：3 正=真实 null/安全对象/retryable，3 负=未知字段/非法枚举/非空位 null）。
- validate_samples.py 接线（38→44 checks，acceptance c2 自动覆盖；run-acceptance.sh 未改动）。
- 验证 @1ba984e（orchestrator 提交后独立复跑）：selftest 6/6、samples 44 PASS、openapi VALID、jcs PASS、提交范围仅 contracts 10 文件；实时捕获（fix lane，当前源码构建 jar）：真实 `lastError:null` 接受、`{reason:"internal",retryable:true}` 接受且 marker/原始 code 缺席、篡改体（+message/非法枚举）拒绝。Java/Python/完整 acceptance 未重跑（契约-only 变更，web-java 源码未动，mvn 总数仍 129）。

## Round 5 @ 1ba984e3825b9a0d0d35a4a0970df4ebdd63cd24 — 有界复审记录：**FAIL**（1 BLOCKER）

> 只读复审，未重跑测试；SHA 绑定/提交范围/执行结果为 orchestrator 提供；handoffs 编辑已排除。

### Schema 修复核验
- **FIXED — lastError 可空性**：openapi.yaml:2772-2789 `type: object` 与 `nullable: true` 同一 Schema Object；required/禁额外字段/有界 reason 枚举保留。
- **枚举兼容非严格相等**：实现（SystemEchoController.java:217-225）输出 internal/unsupported_contract/retry_limit_exceeded；schema 额外预留 handler_failed——已披露超集，可接受。
- **组件移除**：openapi.yaml 无 EchoJobLastError 残留、无悬空引用。
- **Java 行为**：get/projectError/mapReason（:171-225）与 round-4 审查一致（null 错误、bigint 字符串、404）。
- **范围**：提交内无无关改动在 oracle 侧 UNVERIFIED（无 diff 工具）；被检源码与报告一致。【orchestrator 补证：独立核验提交范围=仅 backend/contracts 10 文件，dirty_after=0】

### 校验器健全性（BLOCKER 核心）
- 文档解析真实：validate_responses.py:116-123 实取 GET 200 JSON schema 并递归解析 $ref，无硬编码副本；接线真实：validate_samples.py:206-215 调用 selftest 并经正常退出码传播失败（支持 c2 自动覆盖）。
- **关键严格性缺陷**：convert():99-108 在本地 type 存在时正确并 null，但**在无本地 type 时也并 null**（:107-108 明文实现了本应拒绝的行为）——转换器在旧损坏形 `allOf+$ref+nullable` 下同样接受 `lastError:null`，selftest 因此**不能判别 round-4 缺陷类**。
- **被直接行使的后果**：openapi.yaml:2771 `finishedAt` 仍为 allOf+$ref+nullable；retryable fixture 的 `finishedAt:null` 仅因转换器静默放宽而通过——该正例在当前声明下并非严格有效。
- 6 fixtures 均已读：信封形状/字符串计数忠实于控制器；3 负例真实违反键集/枚举/jobId 类型。Draft202012Validator 仅在**忠实转换后**才适配——正确的校验无法补偿转换器的放宽。

### 证据充分性

round-4 IMPORTANT **仅部分闭合**：内联 schema 修正本身健全，实时捕获支持泄露防护不变；但 selftest 与实时响应均经由复现被质疑放宽行为的转换器通过，不能确立严格 OAS 3.0.3 响应合规。未知字段/非法枚举/null jobId 拒绝证明了有用判别力，但未证明 misplaced nullable 的正确处理。契约-only 变更不重跑 Java/Python 合理。

### Findings

- **BLOCKER — 所要求的严格可空性验证不健全**：validate_responses.py:107-108 不得在无本地 type 时并 null；须补转换回归判别测试（旧 allOf+$ref+nullable 形**拒绝** null、新内联形**接受** null）；处理被直接行使的 finishedAt 可空性；在不弱化转换语义前提下重跑 fixtures/实时捕获。
- **SUGGESTION — 负例失败应区分文件不可读与真实 schema 拒绝**：validate_path():130-134 对缺失/格式错误文件返回失败，run_selftest():156-160 将其计为负例成功；应先要求 fixture 可加载可解析再计拒绝。
- **NOTE — 已披露限制**：handler_failed 预留与 uuid/date-time format 不强制在本有界范围可接受，但脚本不得表述为完整 OAS 校验；decisions-notes.md:164 当前**高估其严格性**。

### blockingFindings（round-5）

1. 新响应转换器接受 misplaced nullable → 所要求的严格校验器证明仍无效。

**Overall（round-5）：FAIL** — lastError schema 本身已正确修复，但配套校验器静默接受先前损坏表示，并掩盖另一处被直接行使的可空性不匹配（finishedAt）。须修正转换并补旧形/新形判别测试后方可宣称本有界要求闭合。本结论仅针对 round-5 契约校验变更；此前泄露闭合与基础结论继续有效。

## 修复记录（round-6，commit f6e500e，fix lane 完成，orchestrator 独立复核）

针对 round-5 BLOCKER/SUGGESTION/NOTE 的有界修复（3 文件 +124/−24，仅 backend/contracts）：
- **转换器严格化**：validate_responses.py convert() 的 null 并集**仅当同一 Schema Object 声明本地 `type`** 时生效（str→[type,"null"]、list→追加）；无本地 type 时 OAS 3.0.3 `nullable` 无任何效果、**不再并 null**（~line 106 注释）；不健全的 `anyOf+null` 回退分支删除。
- **判别回归（--selftest，内存合成 mini-doc，无文件依赖）**：旧形 `{allOf:[{$ref X}],nullable:true}` → **拒绝 null** 且接受 X-合规对象；新内联形 `{type:object,nullable:true,...}` → 接受 null 且接受对象。4 项判别检查；selftest 6→**10 checks**。恢复旧回退必使判别失败（非同义反复）。
- **路径内 schema 修复**：`SystemEchoJobView.finishedAt` → 内联 `{type:string, format:date-time, nullable:true}`；`leaseRevision` → 内联 `{type:string, pattern:'^(0|[1-9][0-9]*)$', nullable:true}`（与 BigintString 完全一致，无漂移）；lastError 保持 1ba984e 内联形。其余端点/schema 未动。
- **Harness 硬化（round-5 SUGGESTION）**：validate_path() 三分类 valid|schema_invalid|load_error；负例仅 schema_invalid 计为判别成功；缺失/畸形文件=harness 失败（独立消息+非零退出），绝不冒充当负例通过。
- **诚实措辞+审计（round-5 NOTE）**：decisions-notes.md 改为如实描述（有界严格 nullable echo-view 路径校验、文档实解析、判别回归、键集/枚举/required/additionalProperties 强制；**非**完整 OAS 校验；format 注解不强制）；全文 misplaced `allOf/oneOf/anyOf+nullable`（无本地 type）审计：修复前 38 → 修复后 **36**（echo-view 路径内 2 处已修→0；36 处路径外历史遗留逐处列举为下次获授权契约修订 follow-up）。
- **验证 @f6e500e**：fix lane + orchestrator 提交后独立复跑——selftest **10/10**（3 正+3 负+4 判别）、validate_samples **48 checks PASS**（44→48 已接线 c2）、openapi_spec_validator OK、jcs selftest PASS；实时捕获（现有 jar=当前源码，Java 未变）：LIVE1 queued `finishedAt:null`+`lastError:null` 双双严格通过 rc=0；LIVE2 种入内部诊断 → `{reason:"internal",retryable:true}` rc=0、marker/原始 code 缺席；篡改 +message → rc=1、非法枚举 → rc=1；mvp_a_dev 清至 0 行；未重跑 mvn/pytest/完整 acceptance/镜像（契约-only，协调范围指令；mvn 仍 129、pytest 仍 47）。

## Round 6 @ f6e500e474954781d3438188b6fdd389e61682e7 — 有界复审记录：**PASS**（Findings=[]，blockingFindings=[]）

> 只读源码复审，未重跑测试；SHA 绑定/提交范围/实时捕获/执行结果为 orchestrator 提供；handoffs 编辑已排除。

### BLOCKER 闭合核验 — **CLOSED**
- validate_responses.py:99-110：nullable 处理仅在同一 schema object 声明 `type` 时并 null；无声明时转换后约束保持不变。
- :107-108 残留 `anyOf`/null 字样为**解释性注释**，非可执行放宽；:92-93 组合处理递归保留原分支、不添加 null 备选；:71-79 引用处理未恢复已删除的宽松回退。
- run_discrimination():159-190 以独立指定的旧/新 schema 形状调用真实转换器与校验器：断言旧形**拒绝 null** 且接受合规对象、新形两者皆收——判别真实：恢复旧回退必使 old-shape-null 检查失败。
- 严格语义细节正确：无本地 type 的 `nullable` 是**无效果**而非普遍禁止 null（底层 schema 本身允许 null 时仍可 null）——实现对被审构造正确保留该区分。

### Schema 修复
finishedAt（openapi.yaml:2777-2782）type+format+nullable 同对象，queued 响应 null 无需转换器放宽即合法；leaseRevision（:2770-2776）本地 string 类型+nullable，pattern 恰为 `^(0|[1-9][0-9]*)$` 与 BigintString（:1890-1892）一致；lastError（:2783-2800）保持内联可空对象形+双必填+禁额外+封闭枚举。提交级无其他 schema 改动由 orchestrator 范围核验补证（oracle 无 diff，UNVERIFIED 项已声明）。

### Harness 硬化 — **FIXED**
validate_path():136-152 区分 valid/schema_invalid/load_error；负例仅 schema_invalid 计判别成功（:208-220）；缺失/畸形 fixture → harness 失败而非通过负例；selftest 与普通 CLI 均以非零退出传播失败（:225-257）；4 项判别计入 selftest 总数（:221-222）。

### 诚实性/残留
decisions-notes.md:161-171 现准确限定为文档实解析的严格可空性 echo-view 响应校验（非完整 OAS 校验）；36 处路径外历史位置逐处列举于 :173-194（其穷尽计数未独立审计）——对协调限定范围可接受延期，但属契约 follow-up 而非已认证正确的 schema；uuid/date-time format 不强制对本有界可空性/键集证明可接受且已明确披露。

### 证据充分性
**round-5 BLOCKER 有效闭合**：代码现保持严格 nullable 语义，旧/新形测试直接防卫先前不健全行为；提供的实时捕获经修正后文档实解析 schema 验证两个合法 null 字段，额外字段与非法枚举篡改仍被拒绝。10 项响应 selftest 与 48 项样例运行对契约-only 修正提供适当证据；不重跑未变更 Java/Python 套件或镜像不削弱本转换器/schema 证明；先前部署告戒（镜像须重建纳入后续提交）保持。

### Findings / blockingFindings（round-6）
**[] / []** — 本有界变更无新实质发现。

**Overall（round-6）：PASS** — 转换器不再放宽 misplaced nullable schema，回归测试区分旧缺陷与修正后内联表示；被直接行使的响应字段与负例 fixture 分类亦已修正。本结论仅接受 round-6 有界修复；此前基础结论、部署告戒与已记录的路径外 follow-up 不变。

---

## blockingFindings（最终）

**无**。round-1 的 4 个 blockers、round-2 的 2 个 blockers、round-4 的 E 泄露缺陷（四路径 CLOSED）均已修复并经复审确认；round-5 的 1 个 BLOCKER（响应转换器接受 misplaced nullable → 严格校验证明无效）经 round-6 修复（f6e500e）并由 round-6 复审确认**有效闭合**。最终 SHA @f6e500e：blockingFindings=[]。非阻塞遗留（36 处路径外历史 allOf+nullable、format 注解不强制、handler_failed 预留、镜像重建告戒、边缘断言建议）均如实记录于 A.md 未决项与 decisions-notes.md。

## 复审记录

- Round 1：FAIL (blocked) @f7e75c1 — 4 blockers + 7 majors + 1 minor。
- 修复 1：commit bf393aa（全部 round-1 findings），双端套件+acceptance 全绿后提交。
- Round 2：FAIL @bf393aa — R2-1 媒体授权、R2-2 刷新代次绕过（blocking）+ R2-3/4/5（important）+ bean 扩展/向量区分度/镜像证据缺口。
- 修复 2：commit 26d97fb（全部 round-2 findings + 容器化证据），Java 124/Python 47/acceptance 26/26 全绿后提交。
- Round 3：**PASS-with-notes @26d97fb**（blockingFindings 空）。
- Round 4（E 验收驱动有界缺陷，非全量复审）：E 于 26d97fb 发现 echo GET last_error 原样投影泄露（52 项 51 PASS/1 FAIL）→ 修复 commit `bfd2dc3`（有界投影 {reason,retryable}，原始诊断不外泄）→ 复审 @bfd2dc3 = **PASS-with-notes**（blockingFindings 空，泄露四路径 CLOSED；IMPORTANT note：allOf+nullable 严格 3.0.3 歧义）。
- Round-4 后续（总协调授权契约修订）：commit `1ba984e` 内联修复 lastError nullable + 新增严格响应校验器 → round-5 复审。
- Round 5：FAIL @1ba984e — 1 BLOCKER（转换器无本地 type 仍并 null，复现旧形宽松、严格性证明无效；掩盖 finishedAt 同模式缺陷）+ SUGGESTION（负例文件错误 vs schema 拒绝混淆）+ NOTE（decisions-notes 高估严格性）。
- 修复 3（round-6）：commit `f6e500e`（转换器严格化 + 4 判别回归 + finishedAt/leaseRevision 内联 + harness 硬化 + 诚实措辞与 36 处路径外审计清单）。
- Round 6：**PASS @f6e500e**（Findings=[]，blockingFindings=[]；round-5 BLOCKER 有效闭合）。

## reviewedCommit 一致性声明

最终代码 SHA = `f6e500e474954781d3438188b6fdd389e61682e7`（round-6 有界复审绑定，Overall PASS；round-4 PASS-with-notes @bfd2dc3 与 round-3 全量 PASS-with-notes @26d97fb 结论对各自未变更部分继续有效）。本文件与 A.md 所属 report-only commit 不修改任何代码，reviewedCommit 与最终代码保持一致。
