# A-oracle.md — A 包 oracle 独立审查报告

- **reviewedCommit（最终代码 SHA）**：`bf393aa181b9772ec54eb4fdbbcf856b227771b6`（branch `feature/mvp-foundation`，与最终代码一致；本文件随 report-only commit 提交，不改代码）
- 审查者：本机 OpenCode omo-slim 配置的 `oracle` 子代理（会话 `ses_f7523570cffeGdu61d3BzOYo94`，只读，两轮：round-1 @f7e75c1，round-2 @bf393aa）
- 审查依据：backend/doc/tasks/A-foundation.md、COMMON.md、技术/数据/详细设计、API 设计、测试需求决策记录、交付代码、真实测试证据（orchestrator 在对应 SHA 实际执行；oracle 只读评估）
- 代码提交链：`2b786f7`（实现 159 文件）→ `f7e75c1`（清理误提交 LSP 工件）→ `bf393aa`（round-1 修复 38 文件 +965/−123）

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

## blockingFindings（最终）

**无**（round-3 @26d97fb：blockingFindings=[]，Overall=PASS-with-notes；round-1 4 blockers 与 round-2 2 blockers 均已修复并经复审确认）。

## 复审记录

- Round 1：FAIL (blocked) @f7e75c1 — 4 blockers + 7 majors + 1 minor。
- 修复 1：commit bf393aa（全部 round-1 findings），双端套件+acceptance 全绿后提交。
- Round 2：FAIL @bf393aa — R2-1 媒体授权、R2-2 刷新代次绕过（blocking）+ R2-3/4/5（important）+ bean 扩展/向量区分度/镜像证据缺口。
- 修复 2：commit 26d97fb（全部 round-2 findings + 容器化证据），Java 124/Python 47/acceptance 26/26 全绿后提交。
- Round 3：**PASS-with-notes @26d97fb**（blockingFindings 空）— reviewedCommit 与最终代码一致；其后仅本报告提交，无代码改动。

## reviewedCommit 一致性声明

最终代码 SHA = `26d97fbe908cb93c1fe366e28ba54a91c21b497c`（round-3 审查绑定）。本文件与 A.md 所属 report-only commit 不修改任何代码，reviewedCommit 与最终代码保持一致。
