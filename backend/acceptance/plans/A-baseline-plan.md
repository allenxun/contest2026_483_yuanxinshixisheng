# A 基线验收计划（A-baseline-plan）

依据：`backend/doc/tasks/A-foundation.md`（范围 1—6 与"验收"句）与
`backend/doc/tasks/COMMON.md`。A 交付基线 SHA 并更新 `config/baseline.json`
（gate=open）后，按本计划逐项执行；**任一项未通过即向总协调报告 blocker=A，
不启动 B/C/D 验收**。当前全部条目状态：`dependency_pending`（A 基线未提供）。

通用前置（所有条目共享）：
- 协调者已把 A 已提交基线同步进本工作树，`config/baseline.json` 记录 SHA/synced_at；
- 按 `plans/isolation-and-doubles.md` 起 E 专用实例：`source config/acceptance.env.example`
  后替换为真实 E 专用值（PG 端口 15432、库名 `eaccept_*`、BASE_URL 指向 E 实例）。

---

## AB-01 Java Web 可构建、可启动、可重复启动 + Java 测试通过

- 前置：A 的 `backend/web-java` 与镜像/启动说明存在（含 A 交付的 Java 测试命令）；E 专用端口空闲。
- 执行命令（占位）：
  ① 先运行 **A 交付的 Java 测试命令**（如 `<backend/web-java> mvn -q test`，以
  handoffs/A.md 为准）并**记录退出码**；
  ② `<A 构建命令> && docker compose -f backend/deploy/<E 覆盖文件> up -d web-java && curl -fsS $E_ACCEPTANCE_BASE_URL/healthz`
  重复启动：再次 `up -d --force-recreate` 后 healthz 仍 200，PG 数据无破坏（行数核对）。
- 证据：Java 测试命令、退出码与摘要日志；两次启动日志摘要、healthz 响应、启动前后
  `\dt`/关键表行数对比，存 `reports/evidence/<run-id>/`。
- 当前状态：**dependency_pending**（A 基线未提供，无被测工程）。

## AB-02 Python Worker 可构建、可启动、重启续跑 + Python 测试通过

- 前置：A 的 `backend/worker-python` 交付（含 A 交付的 Python 测试命令）；PG 任务表已由 AB-03 迁移。
- 执行命令（占位）：
  ① 先运行 **A 交付的 Python 测试命令**（如 `<backend/worker-python> pytest -q`，以
  handoffs/A.md 为准）并**记录退出码**；
  ② `<A Worker 启动命令>`；启动→SIGTERM→再启动，观察任务领取日志序号连续。
- 证据：Python 测试命令与退出码；启动/退出日志；任务表状态在重启前后不丢
  （pending 仍 pending，processing 租约到期后可再领取）。
- 当前状态：**dependency_pending**。

## AB-03 全新 PG 可迁移（真实 PG，非 SQLite）

- 前置：空库 `eaccept_mvp_e_<suffix>`（14 表迁移前 0 表）。
- 执行命令（占位）：`<A Flyway 命令> migrate`；随后
  `psql -c "\dt"` 数表 = 14（+schema history），`flyway info` 版本唯一、无重复版本号。
- 证据：迁移输出、表清单、后置循环外键存在性 SQL 结果。
- 当前状态：**dependency_pending**。

## AB-04 唯一约束拒绝双占用与双记录

- 前置：AB-01..03 通过；测试数据夹具（run-id 前缀）就绪。
- 执行命令（占位）：经 API 或受限 SQL 并行提交同微晶两执行/同去重键两记录：
  `xargs -P2 < 两条并发 M4-A03 请求脚本>`；预期至多一个成功、另一个 409；
  同标识同内容重复记录只计一次（M4-A05）。
- 证据：并发响应组合、`reports/evidence/`、PG 中对应行唯一性查询结果。
  **约束验证必须落在真实 PG**（锁/唯一约束不接受内存替身结论）。
- 当前状态：**dependency_pending**。

## AB-05 认证主体上下文拒绝无效凭据

- 前置：A 提供认证/会话与云台凭据协议（D01 对接项，A 侧适配端口）。
- 执行命令（占位）：黑盒负例矩阵——无凭据、伪造 `accountId`、伪造 `installationId`、
  过期会话、其他账号 ID 越权，分别打 M2-A06/M5-A01/M3-A04 等代表端点。
- 证据：全部得到 401/403/404（按 A 契约）而非 2xx，且每个拒绝响应满足 AB-11 的
  结构化错误体与 requestId 关联；不产生业务写入（前后表计数对比）。
  特别核对：未实现业务接口不得给假 200（A-foundation 范围 3）。
- 当前状态：**dependency_pending**。

## AB-06 Java→Python 最小契约 job 按正确代次完成

- 前置：A 的任务 JSON Schema 与双方契约样例存在；适配端口替身可注册。
- 执行命令（占位）：用 A 提供的最小测试 job 从 Java 侧入队（或经其测试入口）→
  Python 领取 → 以对应代次完成回写；再提交新代次后旧代次结果回写被拒（T13 代次控制）。
- 证据：任务行状态轨迹（pending→processing→done）、代次字段变化、拒绝旧结果的记录。
- 当前状态：**dependency_pending**。

## AB-07 T12 领取/续租/过期恢复

- 前置：AB-06 通路可用。
- 执行命令（占位）：领取任务后 kill -9 Worker → 等待租约过期 → 第二 Worker 领取成功；
  过期 Worker 复活后提交结果被代次/租约约束拒绝。
- 证据：租约时间戳轨迹、双方日志、结果表无重复归档行。
- 当前状态：**dependency_pending**。

## AB-08 T13 幂等公共设施

- 前置：A 暴露幂等所需请求头/字段约定。
- 执行命令（占位）：对幂等写入口重复提交：同 requestId 同内容→原结果；
  同 requestId 不同内容→409 冲突；鉴权先于去重命中（无效凭据+重复键→仍 401）。
- 证据：三次调用的响应与 requestId 轨迹。
- 当前状态：**dependency_pending**。

## AB-09 跨语言 JSON 契约样例一致 + OpenAPI 基础契约

- 前置：A 交付 OpenAPI 与任务 JSON Schema、双方契约样例文件。
- 执行命令（占位）：以 A 交付的契约校验工具为准，例如
  `<A 契约一致性测试命令> 或 python3 -c "import jsonschema; jsonschema.validate(...)"` 对双样例互验；
  核对 bigint 一律字符串、multipart、分页、错误码骨架符合 API 设计文档统一约束。
- 证据：校验输出、差异清单（若有）记入交接文档。
- 当前状态：**dependency_pending**。

## AB-10 fail-closed：生产配置缺能力时拒绝启动/拒绝成功

- 前置：A 的适配端口有"缺能力"配置开关（如无 OSS 凭据、无推送通道）。
- 执行命令（占位）：去掉某外部能力配置后启动 Web/Worker → 预期启动失败或该路径明确
  报错，绝不静默假成功；恢复配置后正常。
- 证据：两种配置的启动日志与探针结果。
- 当前状态：**dependency_pending**。

## AB-11 结构化错误响应契约与 requestId 关联

- 前置：A 交付错误体 Schema/字段说明与 requestId 约定（A-foundation 范围 1：
  结构化错误与 requestId；统一约束 4：认证主体）。
- 执行命令（占位）：对代表端点主动制造错误并采集响应：
  ① `curl -i $E_ACCEPTANCE_BASE_URL/api/v1/me/gimbal-bindings/UNKNOWN`（无效凭据→401/403）；
  ② 合法主体提交非法字段（400/422）；③ 制造内部错误路径（若 A 提供注入开关，5xx）。
  每个请求携带/捕获 `X-Request-Id`（framework/client.py 自动生成）。
- 证据要求：错误响应体为**结构化 JSON**（含稳定错误码、人类可读信息、requestId 字段
  或其等价物，具体字段名以 A 契约为准）；错误体中 requestId 与响应头/日志可关联，
  能在服务端日志检索到同一请求；错误体不泄露堆栈/凭据/他人资源存在性；未实现业务
  接口返回明确"未实现"类错误而非假 200。
- 当前状态：**dependency_pending**。

---

## 出口条件

- AB-01..AB-11 全部 passed 且证据齐（含 A 的 Java/Python 测试退出码记录）→ 报告总协调"A 基线验收通过"，B/C/D 场景验收开闸。
- 任一 failed → 附 requestId/日志/差异报可复现缺陷，阻塞包名=A，不自行修改 A 实现。
- A 未提供基线前，本计划所有条目维持 dependency_pending——这是当前事实，不伪装。
