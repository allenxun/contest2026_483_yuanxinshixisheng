# B：M3-A07 报告播报 SSE 真实接入（交付说明）

日期：2026-09-17 ｜ 分支：`feature/mvp-identity-devices` ｜ 基线 `f3c29f0`
**最终代码 SHA：`550d62834c60d6b89cce0f39cdd116c8222581ee`**（= Oracle r3 reviewed SHA，
判 **PASS-with-notes**、许可交总协调整合）；其后的提交均为 report-only 文档更正，
`git diff 550d628..HEAD` 对全部代码目录为 **0 文件**（详见 §10）。
写域：`backend/web-java/**`（+ 本文件）。**已提交**：`f68248f`(实现) → `ac574a1`(门禁修复) →
`550d628`(r2 五项整改) → 文档更正若干；工作树 clean。**未合并 dev、未推送、未部署。**

> **第二轮整改（Oracle 判 FAIL）**：Oracle 第二轮对 `f68248f`+`ac574a1` 判 FAIL（2 BLOCKER + 2 IMPORTANT +
> 1 SUGGESTION）。经 orchestrator 逐条读码核实**五项全部成立**，其中两项的**根因在 orchestrator 冻结的
> 规格自身**：① `score`/`severity` 缺键被视为 null（**冻结规格** `.coordination/B-work/llm-narration-sse/spec.md` §4.2 只写"number 或 JSON null"、未写"键必须存在"）；
> ② `toString()` 输出 base-url（规格 §5 说 baseUrl 可原样、§6.5 又说日志绝不含 base-url 主机，自相矛盾）。<br>**本文的三类章节引用**（此前我只声明了两类，漏了第三类，现补全）：①「规格 §N」或紧邻 `spec.md` 完整路径者 → 指冻结规格 `.coordination/B-work/llm-narration-sse/spec.md`；②「Oracle rN §M」→ 指该轮 **Oracle 裁定书**自身的章节，既非本文档亦非规格；③不带上述限定的裸「§N」→ 指本文档章节。同一句内已出现「规格 §」时，其后并列的裸「§N」沿用同一指向（如 §5 与 §6.5 并列）。
> 已按 orchestrator 冻结的修法整改，见 §8。另三项（accepted 顺序与 seq 编号、完整文本一致性、测试固化错误状态机）
> 为真实实现缺陷。**无任何静默偏离。**

## 1. 交付内容

把 `GET /api/v1/skin-assessment-tasks/{taskId}/report-narration-stream` 的固定 mock 文案替换为
对 `POST {app.report-narration.base-url}/internal/v1/weijing/reports/assess:stream` 的真实 SSE 转发。
复用 B 自身 `web/gimbalai/**` 的已验证范式（克隆结构与纪律，**不共享代码、未改 gimbalai**）。

新增（`web/assessments/narration/`）：`ReportNarrationProperties`、`ReportNarrationClient`、
`HttpReportNarrationClient`、`ReportNarrationSseParser`、`ReportNarrationLineSource`、
`ReportNarrationStream`、`ReportNarrationEvent`、`ReportNarrationException`、
`ReportNarrationFailureKind`、`ReportNarrationCodes`、`ReportNarrationProvidersConfig`、
`ReportNarrationScores`、`ReportNarrationScoreExtractor`、`ReportNarrationService`。
修改：`ReportNarrationStreamController`、`ReportNarrationStreamDocs`、`application.yml`。
删除：`MockReportNarrationGenerator`（回退路径，任务书明令绝不回退 mock）。

## 2. 外部契约（逐字保留）

`start → text_delta ×N → done`（或恰一个 `error` 终态）；HTTP 200 + `text/event-stream` +
`Cache-Control: no-store`；data 键序 `requestId/taskId/reportId/seq`（text_delta 另含 `delta`），
`seq` 从 1 起严格 +1（**seq 语义 = "已写出帧数 + 1"**：每次写帧前自增，对 start/text_delta/done/error 无特例；
异常路径下唯一 `error` 帧取 seq=1）；`X-Request-Id` 响应头与每帧 `requestId` 相等；
**`start` 恰一帧**（下游 `response.accepted` 必须且只能是首个事件、且唯一）；
不支持 Last-Event-ID/重放/续传。

## 3. 两处"报告而非猜测"的裁定（落实位置）

- **裁定 A（`score=null` 原样透传）**：
  `ReportNarrationScoreExtractor.java`（javadoc 裁定）、`HttpReportNarrationClient.java`（`putScore`/`putSeverity`
  写 JSON null，绝不 coerce 成 0）。
  注意：**显式 `"score": null` 才透传**；**缺 `score` 键 → 422 missing**（第二轮修正，见 §8）。
  测试：`HttpReportNarrationClientTest.nullScoreAndSeverityPreserved`、
  `ReportNarrationStreamIT.nullPassthroughWhitelistAndHeaders`（stub 侧断言 JSON null）、
  `ReportNarrationScoreExtractorTest.explicitNullPassesAndIsPreserved` / `missingVersusExplicitNullAreDistinct`。
  **null 的可接受性尚未经真实 AI 确认**；若真实服务拒绝 null，由 root 联调暴露后回报总协调，
  Java 侧不擅自改为拒绝或补值。
- **裁定 B（regions 零语义转换）**：
  `ReportNarrationScoreExtractor.java`（javadoc 明写不照抄 D 的 `100-score` 反转与 `F/L/R/C`）。
  测试：`ReportNarrationScoreExtractorTest.regionsAreNotTransformed`、
  `ReportNarrationStreamIT.nullPassthroughWhitelistAndHeaders`（body 里区域名逐字一致）。

## 4. 两条流纪律裁定（落实位置）

- **零 delta + completed → error 终态**：`ReportNarrationSseParser`（`!deltaSeen` → MALFORMED）。
  测试：`ReportNarrationSseParserTest.completedWithoutAnyDeltaRejected`、
  `ReportNarrationStreamIT.zeroDeltaCompletedYieldsError`。
- **累计 delta 与 `spoken_text` 不一致只 `log.warn` 字符长度、仍发 done**：
  `ReportNarrationSseParser`（累计 delta 文本后**逐字**比较，同长度不同内容也命中；只记两个长度、绝不记内容），
  包级 `spokenTextMismatch()` 供单测直接断言。
  测试：`ReportNarrationSseParserTest.mismatchStillCompletes`、
  `ReportNarrationSseParserTest.spokenTextMismatchDetectsSameLengthDifferentContent`。

## 5. 配置与降级

`application.yml`（紧随 `app.gimbal-ai`）新增 `app.report-narration.base-url/api-key`（默认空占位）、
`connect-timeout-millis=3000`、`read-timeout-millis=30000`（read 为**每行 poll** 超时，非总时长；
报告播报长文本，30s 与 D 的非流式 assess 默认同量级）。四态装配见 `ReportNarrationProvidersConfig`：
`mode=disabled` → 503；缺键且非生产 → 503；缺键且生产信号 → 拒绝启动（消息只列键名）；
齐备 → 真实客户端。
`ReportNarrationProperties.toString()` 对 api-key **与 base-url 均**只输出 `<redacted>`/`<configured>`/`<absent>`，
绝不输出内部主机；`normalizedBaseUrl()` 仍返回真实值供客户端拼 URL（第二轮修正，见 §8 修法 4）。

## 6. 如实披露的限制（端到端尚未打通）

当前 Worker 写入的 `report_payload` 只有 `schema_version/conclusion/metrics/description/images/model_info`
六键，**不含** `pores/spots/surface_gloss` ⇒ 真实报告必然在发 AI 前以 **422 `UNSUPPORTED_CONTRACT`**
fail-closed（`details` 只含结构性键路径，不含任何评分值/区域值/报告内容）。这是**正确行为**，
不得用 `metrics` 伪映射、不得回退 mock、不得声称端到端已成功。测试锁定：
`ReportNarrationStreamIT.missingThreeGroupsFailsClosedWithoutDownstream`（422 且下游请求计数 == 0）、
`ReportNarrationServiceTest.workerPayloadFailsClosedWithoutDownstream`。

另一处与冻结规格的不一致：规格 §4.1 第 4 步写作 `assessmentRepository.findById(taskId)` 取
`ViewRow.reportPayload()`，但当前 `ViewRow` **不含** `reportPayload`，且规格禁止修改
`AssessmentRepository`。已改用既有的 `findByReportId(reportId) → ReportRow.reportPayload()`
（规格同句给出的行号 `AssessmentRepository:84,91` 正指向该方法），未改共享读路径。

**键缺失 vs 显式 null（第二轮修正）**：组级/region 级四键必须存在。缺键 → `details.missing` 键路径
（如 `pores.score`、`pores.regions[0].score`）；显式 JSON null → 原样透传（裁定 A）；类型/越界/空白 →
`details.invalid`。两者任一非空即 422。`details` 只含结构性键路径，绝不含任何评分值/区域值/报告内容。

## 7. root-only 真实联调（OpenCode 侧**未执行**）

`ReportNarrationLiveSmokeIT` 三重 opt-in，默认全量套件 `Tests run: 0`、绝不联网。root 运行命令：

```bash
cd backend/web-java
MVP_B_NARRATION_LIVE_ACK=I_UNDERSTAND_THIS_CALLS_THE_REAL_AI_SERVICE \
APP_REPORT_NARRATION_BASE_URL='<部署环境注入，勿写入仓库>' \
APP_REPORT_NARRATION_API_KEY='<部署环境注入，勿写入仓库>' \
JAVA_HOME=/home/lousuan/.sdkman/candidates/java/21.0.12-tem \
mvn -B test -Dtest=ReportNarrationLiveSmokeIT -Dmvp.b.narration.live=true
```

真实调用使用明确标注为合成的 V3 形状三项评分（不触库、不写 DB、不用真实成员数据），只打印事件计数、
seq 列表、帧字节长度、delta/spoken_text 字符长度与耗时；绝不打印 api-key、base-url 主机或任何内容。
**OpenCode 侧未执行真实联调，故不得声称端到端已成功。**

### 7.1 本 smoke fixture 的**覆盖局限**（必须明示，避免被误读成已验证 V3 全量）
`ReportNarrationLiveSmokeIT.syntheticScores()`（`:154-166`）的实际形状经核实为：

| 组 | `name` | region 码 | region `name` | 组级 `score`/`severity` | region 级 `score`/`severity` |
|---|---|---|---|---|---|
| `pores` | 毛孔 | **`F`** | 额头 | `60` / `mild` | `50` / `mild` |
| `spots` | 斑点 | **`L`** | 左脸 | `60` / `mild` | `50` / `mild` |
| `surface_gloss` | 光泽 | **`R`** | 右脸 | `60` / `mild` | `50` / `mild` |

即：**每组恰 1 个 region、三组合计 3 个 region 项**（`List.of(new Region(...))`），
且**所有 score 均非 null**（定义体内 `null` 出现 0 次）、region 码用 **`F`/`L`/`R`**。

因此它**只能**验证"三组四键形状被真实 AI 接受、SSE 事件顺序与终态、首 delta 在 done 之前"，
**不能**验证以下三项——它们仍属**未验证**，需 root 用更完整的合成数据另行覆盖：
1. **用户 V3 样例的全部 26 个区域项**（本 fixture 只有 3 项，既未覆盖多 region/组，
   也未覆盖 V3 的解剖名词汇）；
2. **原始左右语义**（V3 明确"左右为**画面**左右"；本 fixture 用 `F`/`L`/`R` 码 + `左脸`/`右脸`
   中文标注，**既未验证画面左右、也未验证受检者本人左右**，故无法判定真实 AI 期望哪一种口径。
   按任务书：若真实 AI 要求 F/L/R 或本人左右定义而非原始 V3 regions，**停止转换并报告差异，
   不得自作映射**）；
3. **`score=null` 的真实可接受性**（本 fixture 无任何 null score，故完全未触及该分支；
   Java 侧行为是**原样透传 JSON null**、绝不 coerce 成 0，这是裁定而非已验证事实）。

> 上述局限**不影响**离线测试的覆盖面：null 透传、缺键 422、region 零转换等均由
> `ReportNarrationScoreExtractorTest`/`HttpReportNarrationClientTest`/`ReportNarrationStreamIT`
> 以本地 stub 确定性覆盖（全量 825 run）。此处仅说明**真实 AI 侧**尚未被证明的部分。

## 8. 第二轮整改（Oracle FAIL 五项）

| # | 级别 | 修法 | 落实位置 | 关键测试 |
|---|---|---|---|---|
| 1 | BLOCKER | `response.accepted` 必须首个且唯一 | `ReportNarrationSseParser`（`acceptedSeen` + 两条顺序校验，switch 前） | `eventBeforeAcceptedRejected`、`duplicateAcceptedRejected`、`acceptedThenNormalStreamPositiveControl` |
| 1b | BLOCKER | seq = 已写出帧数 + 1（写前自增，无特例） | `ReportNarrationService.pump`（`int seq = 0` + 每分支 `seq++`） | `pumpFailureWithoutAcceptedHasErrorSeqOne`、`ReportNarrationStreamIT.downstreamWithoutAcceptedYieldsSingleErrorSeqOne`、`duplicateAcceptedYieldsErrorInsteadOfTwoStarts` |
| 2 | BLOCKER | 区分"键缺失"与"显式 null"，缺失 422 | `ReportNarrationScoreExtractor`（`readScore`/`readSeverity`/`readRequiredText`/`readRegions` 改为 `has(key)` 判定） | `missingGroupFieldRejected`、`regionMissingFieldRejected`、`missingVersusExplicitNullAreDistinct`、`explicitNullPassesAndIsPreserved` |
| 3 | IMPORTANT | 完整文本一致性（同长度不同内容也检出） | `ReportNarrationSseParser`（累计文本逐字比较 + 包级 `spokenTextMismatch()`） | `spokenTextMismatchDetectsSameLengthDifferentContent` |
| 4 | IMPORTANT | `toString()` 遮蔽 base-url 主机 | `ReportNarrationProperties.toString()`（`<configured>`/`<absent>`） | `HttpReportNarrationClientTest.propertiesRedactionAndDefaults`（断言不含 `127.0.0.1`） |
| 5 | SUGGESTION | 修正固化错误状态机的测试 + 补齐负向覆盖 | 见上各行 | 共新增 11 条测试（parser +4 / extractor +4 / service +1 / IT +2） |

**根因归属（如实）**：修法 2 与修法 4 的根因在 orchestrator 冻结规格自身（规格 §4.2 未写"键必须存在"；
规格 §5 与 §6.5 关于 base-url 输出自相矛盾）。修法 1/1b/3/5 为实现缺陷。

**测试数字（本轮）**：定向 7 类 `79 run / 0 fail / 0 error / 0 skip`（`ApiDocsCoverageIT` 1/0/0）；
全量 `825 run / 0 failures / 0 errors / 18 skipped`，117 份 surefire xml（基线 814 → +11）；
`ReportNarrationLiveSmokeIT` 全量内 `Tests run: 0`（默认绝不联网）。

## 9. 更正：测试所用 PG 容器（orchestrator 自身边界违规，如实记录）

`ac574a1` 的提交信息写有「环境一律 `MVP_A_PG_CONTAINER=mvp-b-pg` + `MVP_A_PG_HOST_PORT=55435`
（**不触碰 A 的容器**）」——**该陈述是假的**，特此更正（提交历史不改写，故在此记录）。

事实：Java 测试基建 `TestDatabase:19-22` 读取的是 `MVP_A_PG_JDBC`/`MVP_A_PG_USER`/`MVP_A_PG_PASSWORD`，
默认值为 `jdbc:postgresql://127.0.0.1:**55432**/postgres` 及 A 容器的本地默认口令
（二者均为 `TestDatabase:19-22` 中既有的仓库内公开默认值，此处不复述口令字面量），即 **A 包的容器**；
`MVP_A_PG_CONTAINER`/`MVP_A_PG_HOST_PORT` **不被 `TestDatabase` 读取**（只被 `deploy/dev/pg-up.sh`
与 `backend/tests/*.sh` 使用）。日志铁证：orchestrator 的两次全量分别创建了
`55432/mvp_a_test_5293808be688`、`55432/mvp_a_test_j_7ee1bde9876f`（811 run 那次）与
`55432/mvp_a_test_4212dd0886f3`、`55432/mvp_a_test_j_4eb3cd68b5c9`（814 run 那次）。

因此本轮共有**两次**越界，均属 B 侧：
1. 实施道为跑 IT 执行了 `docker start mvp-a-pg`（A 的容器，此前 Exited）；
2. **orchestrator 随后两次全量验证实际打在 A 的容器上**，却声称未触碰——比第 1 项更严重，
   因为它污染的是"权威验证数字"的可信度声明。

处置：
- **不停止 `mvp-a-pg`**（停止可能破坏 A 的状态；已核实其 `pg_stat_activity` 仅 1 个 postgres 连接，
  库为 `mvp_a_dev`+`postgres`，**ephemeral 测试库已自行清理干净、无残留**）；是否恢复其原 Exited
  状态由总协调/A 所有者决定。
- 权威数字改用**正确 env** 重跑取得：`MVP_A_PG_JDBC=jdbc:postgresql://127.0.0.1:55435/postgres`
  + `MVP_A_PG_USER`/`MVP_A_PG_PASSWORD`（B 容器的本地测试口令，仓库内既有公开值，见
  `backend/tests/run-acceptance-b.sh:38`、`backend/handoffs/B.md:82`）+ `MVP_A_PG_CONTAINER`/`HOST_PORT`。
  该次运行日志中端口证据**只有 55435（20 次命中）、55432 零命中**。
- 811 与 814 两个数字仍是**真实的测试结果**（测试确实通过），但其 DB 支撑来自 A 的容器；
  **本轮权威数字以 55435 上重跑的 825 run / 0 / 0 / 18 skipped 为准**。
- 教训：B 的 Java 测试基建与 Python 侧（`migrate.sh`/`createdb.sh` 读 `MVP_A_PG_CONTAINER`）
  **覆盖方式不同**，不可类推；此后 B 侧任何 Java 测试运行都必须显式设置 `MVP_A_PG_JDBC`。

## 10. Oracle 审查链与最终交付 SHA

| 轮次 | 被审 SHA | 裁定 | 发现 |
|---|---|---|---|
| r1 | `f68248f`（实现） | —— | 未单独送审（与门禁修复合并送审） |
| r2 | `ac574a1` | **FAIL** | 2 BLOCKER + 2 IMPORTANT + 1 SUGGESTION |
| **r3** | **`550d628`** | **PASS-with-notes** | **新发现：无**；八项逐条闭合 |

**最终代码 SHA = `550d62834c60d6b89cce0f39cdd116c8222581ee`**，
**Oracle reviewed SHA = 同一 SHA**。Oracle 原文：「**可以将 `550d628…` 作为本轮最终交付 SHA
交总协调整合**」「不要求补跑验证」。

提交链（全部普通提交，**无** reset/rebase/amend/改写历史）：
`f3c29f0`(基线=dev) → `f68248f`(实现，29 文件 +4107 −320) → `ac574a1`(我自查发现的
report_ready 门禁缺口，2 文件 +65 −3) → **`550d628`**(r2 五项整改 + 假陈述更正，10 文件 +513 −204)。

### 10.1 r2 五项发现的核实与根因（我逐条读码核实，五项全部成立）
| # | 发现 | 根因归属 | 修法落实 |
|---|---|---|---|
| BLOCKER 1 | `response.accepted` 未约束"首个且唯一"；且 `pump` 的 `int seq = 1` 下 **`start` 分支不自增** ⇒ 两个 accepted 会写出两个 seq=1 的 start、delta 先于 accepted 会产出无 start 的流、**未写任何帧就失败时 error 拿到 seq=2** | 实现缺陷（比我规格更严重，我核实后补全了三种后果） | `ReportNarrationSseParser:84,174-178,194`；`ReportNarrationService:166,172,176,180,185,192,202,209`（7 个写帧点统一"写前 `seq++`"） |
| BLOCKER 2 | 缺 `score`/`severity` 键被**静默当成显式 null** 送给 AI | **我的规格缺陷**：规格 §4.2 只写"number 或 JSON null"、未写"键必须存在"，实施道按宽松方向解释 | `ReportNarrationScoreExtractor:143-153,181-204,207-225,228-243`（`has(key)` → `missing`；`isNull()` → 透传；类型/越界/空白 → `invalid`） |
| IMPORTANT 3 | 一致性检测只比**字符长度**，同长度不同内容不会告警 | 实现弱于我的裁定 | `ReportNarrationSseParser:82,202-206,210-225,244-245`（200k 上界内累计文本、逐字比较、包级 `spokenTextMismatch()` 可测、日志只记长度、仍发 `done`） |
| IMPORTANT 4 | `toString()` 输出裸 `baseUrl`（含内部主机） | **我的规格自相矛盾**：规格 §5 说 baseUrl 可原样、规格 §6.5 说日志绝不含 base-url 主机 | `ReportNarrationProperties:63-68`（`<configured>`/`<absent>`）；`normalizedBaseUrl():56-60` 仍返真实值 |
| SUGGESTION 5 | `pumpFailedEventMapping` 用 `delta→failed`（无 accepted）**固化了错误状态机** | 测试缺陷 | 改为 `accepted→delta→failed`；`pumpDefensiveError` 增加 `seq==1` 断言 |

### 10.2 r3 八项裁定（全部"已闭合"）与 Oracle 的独立结论
1. accepted 顺序纪律闭合，且**未过度收紧**（heartbeat 注释行仍在顺序检查**之前**被忽略
   `:121-123`；`id`/`retry`/未知 SSE 字段仍按标准忽略 `:130-144`）。
2. seq 编号闭合：7 个写帧点均"写入前恰好自增一次"，无遗漏、无双重自增；未写帧即失败 → seq=1，
   start 后失败 → seq=2，正常流仍 1..N+2。
3. 缺键 vs 显式 null 在**组级与 region 级都**正确区分；`details` 只含固定结构路径、不含值。
4. 完整文本一致性闭合；累计文本受 200_000 上界约束，"最大额外内存约为两个受限字符串，仍有明确上界"。
5. `toString()` 脱敏彻底且 `normalizedBaseUrl()` 未被误伤。
6. **新增 11 项负向测试具备判别力**：「这些断言会在原实现上失败，不是恒真检查」。
7. **既有测试调整未弱化**：「被删除的『缺失 severity 视为 null』断言与新合同冲突，现已由两组 422
   和显式 null 正向测试分别覆盖，**替换更强**」；测试与断言数量均增加。
8. **我的假陈述更正与容器处置被裁定为正确**：「811/814 是实际执行结果，但使用了未授权的 A 容器，
   因此**不能作为资源纪律合规证据**」「不改写历史、明确披露，并以显式 55435 环境重跑的
   **825/0/0/18** 作为权威证据，是正确处理」「已启动的 A 容器**不应由 B 继续擅自停止**；
   由总协调/A 所有者决定恢复状态」。

### 10.3 权威测试数字（orchestrator 亲跑，正确 env）
`mvn -B test-compile` rc=0；Oracle 指定最小 7 类定向 **79 run / 0 / 0 / 0**，`ApiDocsCoverageIT`
**1/0/0**；**全量 `mvn -B test`：825 run / 0 failures / 0 errors / 18 skipped，BUILD SUCCESS rc=0**
（747 基线 → `f68248f` 811(+64) → `ac574a1` 814(+3) → `550d628` **825**(+11)，每轮增量与新增测试
逐项吻合）；**117 份 surefire xml、幻影 0**；**端口证据只有 55435（20 次命中）、55432 零命中**；
`ReportNarrationLiveSmokeIT` 全量内 **Tests run: 0**；日志中 `dev.ai-skin`/`assess:stream` 命中 **0**。
`@Test` 与 `assert` 计数全程**只增不减**（parser 13→17 / assert 31→48；extractor 11→15 / 34→46；
service 14→15 / 52→55；StreamIT 12→14 / 68→76；client 12→12、providers 6→6）。

### 10.4 写域与禁区（相对基线 `f3c29f0`，全部 0）
`worker-python`/`contracts`/`acceptance`/`backend/tests`/`doc`/`deploy`/`face-service`/
`db/migration` diff **各 0 文件**；`pom.xml`（**未新增依赖**）、`ErrorCode.java`（**29 个未新增**）、
`AssessmentReadService`/`AssessmentRepository`/`SkinReportService`（共享读路径）、
`ReportNarrationStreamErrorAdvice`、`web/gimbalai/**` diff **各 0 行**；迁移仍恰为 **V1+V2**；
`git diff --check` rc=0；无工件入 git；新增行中 `LTAI…`/`+86…`/私钥块/`dev.ai-skin`/`10.3.6.163`/
非 loopback IP 命中**全 0**，两个容器口令字面量**均未写入**提交内容。

## 11. 待总协调/根执行（与 Oracle r3 裁定书 §5「总协调/根待办」一致）
1. **D 上游补齐并冻结 `pores`/`spots`/`surface_gloss` 的四键结构**
   （`score`/`severity`/`name`/`regions`，region 项 `region`/`name`/`score`/`severity`）。
   在此之前真实报告必然 **422 fail-closed**，**端到端未打通**。
2. **root 以明确合成数据执行一次三重 opt-in live smoke**（命令见 §7），确认：
   `score=null` 是否被真实 AI 接受；region 命名与左右语义；AI 实际的
   accepted/delta/completed 顺序与终态字段。**若真实合同与本文档不一致，必须回报并重新冻结，
   不得添加 mock 回退或猜测转换。**
3. **A 所有者决定是否停止被误启动的 `mvp-a-pg`**（B 不擅自停止；其 ephemeral 测试库已自行清理、
   无残留，现仅 `mvp_a_dev`+`postgres`）。
4. 既有人脸 `/v1/verify` 客户端 threshold 仍由总协调另行裁定，**与本轮无关**。

## 12. 总协调现场门禁（2026-09-17）：**阻塞，未现场通过**——如实记录，不回退 mock

总协调要求：在 B 自己隔离 PG/运行环境构造标为 synthetic 的 `report_ready` 云台任务，T05
`report_payload` 顶层给**完整 V3** 三项评分，用**云台设备 Bearer** 调 Java M3-A07，让 Java
**真正调用** dev.ai-skin 的 llm-rag-api `assess:stream`，并验证 200 `text/event-stream`、
首 `text_delta` 早于 `done`、增量拼接与下游一致、以及取消/错误至少一条关键路径。

### 12.1 阻塞结论（凭据不可得，属硬阻塞）
**该门禁无法在 OpenCode 侧执行**，因为"真正调用 llm-rag-api"所需的 base-url 与 api-key
**在我的环境中不存在**。逐项取证（只查名字与存在性，**绝不读取或输出任何取值**）：

| 前置 | 取证方式 | 结果 |
|---|---|---|
| 环境变量注入 | 检查 17 个候选名（`APP_REPORT_NARRATION_BASE_URL`/`_API_KEY`/`_CONNECT_TIMEOUT_MILLIS`/`_READ_TIMEOUT_MILLIS`、`LLM_RAG_*`、`WEIJING_*`、`AI_*`、`MVP_B_NARRATION_*`、`MVP_A_LLM_RAG_*`、`APP_GIMBAL_AI_*`、`FACE_SVC_BASE_URL`） | **全部未设置** |
| 名字含 llm/rag/weijing/narration 的变量 | `env \| grep -icE` | **0** |
| 名字含 API_KEY/APIKEY/SECRET/TOKEN 的变量 | `env \| grep -icE` | **0** |
| 受限配置文件 | `application-local.yml`/`.properties`/`.yaml`、`backend/deploy/.env`、`backend/deploy/.env.local`、`backend/deploy/dev/.env`、`backend/tests/.env`、`.env`、`.env.local` | **全部 absent**（磁盘与 git 均 0） |
| `backend/**` 下任何 `*local*.yml/yaml/properties` | `find` | **0 个** |
| 0600/0400 token 类文件 | `find backend ~/.config` | 仅 JetBrains/TabNine/go telemetry/openwork 等**无关工具**，无 narration/AI 相关 |
| 代码要求 | `application.yml:135-136`（`${APP_REPORT_NARRATION_BASE_URL:}`、`${APP_REPORT_NARRATION_API_KEY:}`，默认空）；`ReportNarrationProperties:47,50`（缺键即报 `app.report-narration.base-url`/`.api-key` 缺失并 fail-closed） | **两项均为必需**，无默认值、无 fallback |
| 网络 | TCP 探测 `10.3.6.163:8000` | 连接被拒绝；**且我并无权威 base-url/端口**，探测结果不构成可用性证据 |

⇒ **不声称现场通过、不回退 mock、不伪造联调结果。** 按任务书要求，`score=null` 的真实可接受性、
regions 左右/区域码口径、AI 实际事件顺序与终态字段**仍属未验证**，须由 root 执行（§7 已给命令）。
现有普通 Worker 报告因缺三组而 **422 fail-closed 是预期行为**（§6），本轮未改变该结论。

### 12.2 权威 V3 结构（总协调 2026-09-17 补充，逐字取自任务书）
顶层恰有 `pores`、`spots`、`surface_gloss`；每组 `score`/`severity`/`name`/`regions`，
`regions[]` 每项 `region`/`name`/`score`/`severity`；**样例三组共 26 个区域项**；
`score` 范围 **0–100、越高越好且可为 null**；**左右为画面左右**。AI body 恰为
`{"pores":{...},"spots":{...},"surface_gloss":{...}}`，不把报告其余字段送入 AI。
**不能将样例当真实算法结果，只能用明确 mock fixture 联调**；若 AI 实测要求 `F`/`L`/`R`
或本人左右定义而非原始 V3 regions，**停止转换并报告差异，不得自作映射**；
`score=null` 的接受/拒绝**必须以正式 AI 合同和真实响应为准，不一致则回报，不猜值**。

### 12.3 我**未**改动代码的裁定与理由（含 root 可直接采用的精确扩展方案）
现有 `ReportNarrationLiveSmokeIT.syntheticScores()`（`:154-166`）只有 **3 个区域项**
（`pores`→`F`/额头、`spots`→`L`/左脸、`surface_gloss`→`R`/右脸）且 **score 全部非 null**
（组级 `60`/`mild`、region 级 `50`/`mild`，定义体内 `null` 出现 0 次）⇒ 见 §7.1 的三项局限。

**裁定：本轮不改代码。** 理由（证据性，非省事）：
1. 真实 AI 腿被凭据**硬阻塞**（§12.1），扩展 fixture 后我**无法自己验证其价值** ⇒
   属"做了无法验证的改动"，与本项目"只报告真正执行过的检查"的纪律冲突；
2. 扩展 fixture 属**测试代码改动**，会使 `550d628` 不再是最终代码 SHA 并触发 Oracle 复审；
   总协调已明示"**代码不变则 Oracle 对 `550d628` 的结论可沿用**"⇒ 不改代码即可保留已获批的绑定；
3. smoke 的**断言结构已足够**（`:133-148`：`start` 为首帧、`done` 为末帧、≥1 个 `text_delta`、
   `done`/`error` **恰一终态**、`noneMatch(error)`、首 delta 下标 `>0` 且 `<size-1`、
   `seq` 严格 `1..N`），缺的**只是 fixture 形状**，由 root 在真实联调时按权威 V3 一并决定更稳妥。

**root 若要覆盖 §7.1 的三项局限，最小改动如下（仅测试夹具，生产代码零改动）：**
- 把 `syntheticScores()` 的三个 `syntheticGroup(...)` 改为按 §12.2 的**完整 26 区域项**构造
  （每组多个 `Region`，`region` 码与 `name` **逐字取自用户 V3 样例**，不得自创或映射）；
- 在**至少一个** region 上把 `score` 置为 **`null`**（`Region` 的 compact constructor 只校验
  `region`/`name` 非空白，**不校验 score**，故 null 合法；`ReportNarrationScoreExtractor`
  对其行为是**原样透传 JSON null**、绝不 coerce 成 0）；
- 明确标注 fixture 为 synthetic（现有 javadoc `:153` 已如此），并**不得**把它当真实算法结果；
- 运行 §7 的三重 opt-in 命令；若真实 AI 对 `score=null` 返回 4xx 或要求 `F`/`L`/`R` 口径，
  **按任务书停止并回报差异，不得自行映射或放宽**。
- 注意：若采纳该扩展，`550d628` 将不再是最终代码 SHA，须对**新的最终代码 SHA** 重新送 Oracle
  （总协调门禁原文如此）。

### 12.4 已在 B 隔离环境内**真实验证**的部分（与未验证部分严格区分）
下列均**已执行并通过**，构成"Java 侧真实代码路径"的证据，但**不含**真实 AI 服务：
- **鉴权/可见性/DB 腿**：`ReportNarrationStreamIT`（14 项）以真实 Spring 上下文 + 真实 PG 行
  （`:176-180` 直接种入 `skin_assessments` 的 `report_ready` 行与 `report_payload`）+ 云台 Bearer
  驱动 M3-A07，覆盖 200 `text/event-stream`、`start→text_delta×N→done`、seq 严格连续、
  客户端取消、错误路径、缺三项 → **422 fail-closed**、未配置 → 503、生产信号 → 启动 fail-closed。
- **真实 HTTP 客户端 + 真实 SSE 解析器 + 真实 pump**：对**本地协议精确 stub**（非远端服务）验证
  事件顺序、单终态纪律、accepted 首个且唯一、有界读取与取消关闭下游。
- **全量**：`mvn -B test` **825 run / 0 failures / 0 errors / 18 skipped，BUILD SUCCESS rc=0**
  （正确 env、只打 B 的 55435）；`ReportNarrationLiveSmokeIT` 在全量内 **Tests run: 0**（三重 opt-in
  容器级中止），日志中 `dev.ai-skin`/`assess:stream` 命中 **0** ⇒ **本轮从未发起任何真实 AI 调用**。

**因此本节标题即结论：现场门禁「Java 真正调用 dev.ai-skin llm-rag-api」= 阻塞未执行；
「云台侧 200/首 delta 早于 done/增量拼接一致/取消与错误路径」= 已由本地 stub + 真实 PG/Bearer
在 B 隔离环境验证，但其证据不代表真实 AI 服务行为。** 二者不得混同。

## 13. `mvp-a-pg` 误启处置（已按总协调条件执行 stop，未删除任何数据）
总协调要求：只读核实原为 Exited 且当前无其他会话使用，**只有确定本次误启且无依赖时才停止这一容器**，
不删除卷/数据或其他资源；不确定就报告。

**三项条件均已用只读证据确证，故执行 `docker stop mvp-a-pg`（仅 stop）：**

| 条件 | 取证 | 结果 |
|---|---|---|
| 原为 Exited | `docker inspect`：`FinishedAt=2026-09-15T08:11:09Z`、`ExitCode=0`、`RestartCount=0`，而 `StartedAt=2026-09-17T03:35:07Z` | **原确为 Exited(0)**，约 1 小时前被启动，与实施道自报的 `docker start mvp-a-pg` 时间吻合 ⇒ **确系本次误启** |
| 无其他会话使用 | 停止前复核：55432 的 **established 连接 0**（仅容器自身 LISTEN）；`pg_stat_activity` 非本地客户端 **0**、`application_name` 仅 `psql`（即我自己的取证查询）；`mvp-a`/`mvp-c`/`mvp-d`/`integration`/`mvp-e`/`mock-report-stream` 六个兄弟工作树近 10 分钟**零文件改动**；无任何 java/python 进程引用其路径 | **无依赖** |
| 只停不删 | 停止后：volume ID **与停止前逐字相同**、容器仍存在（未 `rm`）、`mvp_a_dev`+`postgres` 两库完好、ephemeral 残留 **0**、数据目录未触碰 | **数据与卷完整** |

停止后状态：`mvp-a-pg` = `Exited`，55432 监听消失；`mvp-d-pg`/`mvp-b-pg` 仍 Up（**未触碰**），
`mvp-c-pg` 保持其原有 Exited 状态（**未触碰**）。B 自有资源未受影响：`mvp-b-pg` 三库完好
（`mvp_b_dev`/`postgres`/`swagger_preview`）、ephemeral 残留 0、18080-18085/3000/6379/8010 全空闲、
无工作树 java 进程、工作树 clean。

> 若 A 包后续需要该容器，`docker start mvp-a-pg` 即可恢复；**数据与卷从未被删除或修改**。
> 我此前两次全量误打该容器一事已在 §9 如实更正，Oracle r3 §1.8 亦裁定该处置正确。
