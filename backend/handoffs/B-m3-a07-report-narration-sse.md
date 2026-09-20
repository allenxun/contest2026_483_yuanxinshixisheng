# B：M3-A07 报告播报 SSE 真实接入（交付说明）

日期：2026-09-17 ｜ 分支：`feature/mvp-identity-devices` ｜ 基线 `f3c29f0`
**最终代码 SHA：`550d62834c60d6b89cce0f39cdd116c8222581ee`**（= Oracle r3 reviewed SHA，
判 **PASS-with-notes**、许可交总协调整合）；其后的提交均为 report-only 文档更正，
`git diff 550d628..HEAD` 对全部代码目录为 **0 文件**（详见 §10）。
写域：`backend/web-java/**`（+ 本文件）。**已提交**：`f68248f`(实现) → `ac574a1`(门禁修复) →
`550d628`(r2 五项整改) → 文档更正若干；工作树 clean。**未合并 dev、未推送、未部署。**

> **现场联调状态（2026-09-17 更新）**：**root 已在 internal.dxg170 的隔离临时环境完成合成 V3 样例的
> Java → 部署中真实 llm-rag-api 联调**（`start` → 6×`text_delta` → `done`、`seq` 1..8、
> 缺 `spots` → 预流 **422 `UNSUPPORTED_CONTRACT`** 且不新开下游；临时 Java/PG/私有目录**已停止并删除**，
> 持久 `openvela-backend.service` 保持 active）。**OpenCode/B 侧未执行、未独立复核该次运行**，
> 仅把 root 的观测与代码事实交叉印证（§14.3）。证据、范围与**仍未验证项**见 **§14**。
> **该联调不证明当前 Worker 报告可播报**：Worker 仍缺三组 ⇒ 真实报告仍会 422（§6）。

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

## 6. 如实披露的限制（**真实 Worker 链路**尚未打通；合成 V3 的 Java→真实 AI 链路已由 root 验证，见 §14）

当前 Worker 写入的 `report_payload` 只有 `schema_version/conclusion/metrics/description/images/model_info`
六键，**不含** `pores/spots/surface_gloss` ⇒ 真实报告必然在发 AI 前以 **422 `UNSUPPORTED_CONTRACT`**
fail-closed（`details` 只含结构性键路径，不含任何评分值/区域值/报告内容）。这是**正确行为**，
不得用 `metrics` 伪映射、不得回退 mock、不得声称"真实 Worker 报告端到端已成功"（§14 记录的是
**合成 V3 输入**的现场联调，**不改变本条**）。测试锁定：
`ReportNarrationStreamIT.missingThreeGroupsFailsClosedWithoutDownstream`（422 且下游请求计数 == 0）、
`ReportNarrationServiceTest.workerPayloadFailsClosedWithoutDownstream`。

另一处与冻结规格的不一致：规格 §4.1 第 4 步写作 `assessmentRepository.findById(taskId)` 取
`ViewRow.reportPayload()`，但当前 `ViewRow` **不含** `reportPayload`，且规格禁止修改
`AssessmentRepository`。已改用既有的 `findByReportId(reportId) → ReportRow.reportPayload()`
（规格同句给出的行号 `AssessmentRepository:84,91` 正指向该方法），未改共享读路径。

**键缺失 vs 显式 null（第二轮修正）**：组级/region 级四键必须存在。缺键 → `details.missing` 键路径
（如 `pores.score`、`pores.regions[0].score`）；显式 JSON null → 原样透传（裁定 A）；类型/越界/空白 →
`details.invalid`。两者任一非空即 422。`details` 只含结构性键路径，绝不含任何评分值/区域值/报告内容。

## 7. root-only 真实联调入口（OpenCode 侧**未执行**；**root 已于 2026-09-17 另行执行，证据见 §14**）

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
**OpenCode/B 侧未执行真实联调**（本节交付的是**入口**：三重 opt-in，在 B 的全量套件内恒为
`Tests run: 0`）。**root 已于 2026-09-17 用隔离临时环境另行执行了真实联调，其证据与范围见 §14**——
两者不得混同：§7 是 B 交付的**入口与纪律**，§14 是 root 的**执行结果**。
即便如此，**仍不得声称"真实 Worker 报告端到端已成功"**（§6、§14.4 第 1 项）。

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
   在此之前真实报告必然 **422 fail-closed**，**真实 Worker 链路未打通**（合成 V3 的 Java→真实 AI
   链路已由 root 验证，见 §14，但那**不**解除本项）。
2. **root 以明确合成数据执行一次三重 opt-in live smoke**（命令见 §7），确认：
   `score=null` 是否被真实 AI 接受；region 命名与左右语义；AI 实际的
   accepted/delta/completed 顺序与终态字段。**若真实合同与本文档不一致，必须回报并重新冻结，
   不得添加 mock 回退或猜测转换。**
3. **A 所有者决定是否停止被误启动的 `mvp-a-pg`**（B 不擅自停止；其 ephemeral 测试库已自行清理、
   无残留，现仅 `mvp_a_dev`+`postgres`）。
4. 既有人脸 `/v1/verify` 客户端 threshold 仍由总协调另行裁定，**与本轮无关**。

## 12. 总协调现场门禁（2026-09-17）：**B 侧当时阻塞**（凭据不可得）——如实记录，不回退 mock

> **【本节结论已被 §14 取代】** root 随后取得凭据并在隔离临时环境**完成了该门禁的真实联调**。
> 本节保留为 **B 侧当时的取证记录与阻塞归因**（含我探测错端口一事），
> **不得再被引用为"现场未通过"的现状**。

总协调要求：在 B 自己隔离 PG/运行环境构造标为 synthetic 的 `report_ready` 云台任务，T05
`report_payload` 顶层给**完整 V3** 三项评分，用**云台设备 Bearer** 调 Java M3-A07，让 Java
**真正调用** dev.ai-skin 的 llm-rag-api `assess:stream`，并验证 200 `text/event-stream`、
首 `text_delta` 早于 `done`、增量拼接与下游一致、以及取消/错误至少一条关键路径。

### 12.1 阻塞结论（凭据不可得，属硬阻塞）
**该门禁无法在 OpenCode 侧执行**。**唯一阻塞原因是本地没有受限 api-key**：
服务侧并无可达性问题——总协调已从 B 主机只读核验权威 base URL `http://10.3.6.163:7861`、
`GET /openapi.json` 返回 **200 `application/json`**，部署服务与正式 `assess:stream` 合同此前亦已核实
（**该核验由总协调完成，B 未独立复核**；按项目规则 #319，我**不自行对真实外部服务发起任何请求**，
连 TCP 探测或 `GET /openapi.json` 也不做，以免与本文「本轮从未发起任何真实 AI 调用」的声明冲突）。
因此缺的只是 `APP_REPORT_NARRATION_API_KEY`，而**我绝不从远端复制、读取或索取该密钥**。
逐项取证（只查名字与存在性，**绝不读取或输出任何取值**）：

| 前置 | 取证方式 | 结果 |
|---|---|---|
| 环境变量注入 | 检查 17 个候选名（`APP_REPORT_NARRATION_BASE_URL`/`_API_KEY`/`_CONNECT_TIMEOUT_MILLIS`/`_READ_TIMEOUT_MILLIS`、`LLM_RAG_*`、`WEIJING_*`、`AI_*`、`MVP_B_NARRATION_*`、`MVP_A_LLM_RAG_*`、`APP_GIMBAL_AI_*`、`FACE_SVC_BASE_URL`） | **全部未设置** |
| 名字含 llm/rag/weijing/narration 的变量 | `env \| grep -icE` | **0** |
| 名字含 API_KEY/APIKEY/SECRET/TOKEN 的变量 | `env \| grep -icE` | **0** |
| 受限配置文件 | `application-local.yml`/`.properties`/`.yaml`、`backend/deploy/.env`、`backend/deploy/.env.local`、`backend/deploy/dev/.env`、`backend/tests/.env`、`.env`、`.env.local` | **全部 absent**（磁盘与 git 均 0） |
| `backend/**` 下任何 `*local*.yml/yaml/properties` | `find` | **0 个** |
| 0600/0400 token 类文件 | `find backend ~/.config` | 仅 JetBrains/TabNine/go telemetry/openwork 等**无关工具**，无 narration/AI 相关 |
| 代码要求 | `application.yml:135-136`（`${APP_REPORT_NARRATION_BASE_URL:}`、`${APP_REPORT_NARRATION_API_KEY:}`，默认空）；`ReportNarrationProperties:47,50`（缺键即报 `app.report-narration.base-url`/`.api-key` 缺失并 fail-closed） | **两项均为必需**，无默认值、无 fallback |
| 服务可达性 | **总协调只读核验（B 未独立复核）** | 权威 base URL 为 **`http://10.3.6.163:7861`**；`GET /openapi.json` 返回 **200 `application/json`**；部署服务与正式 `assess:stream` 合同此前亦已核实 ⇒ **服务端可达、合同已确认，网络不是阻塞点** |
| 我的探测（已作废） | TCP 探测 `10.3.6.163:8000` | 连接被拒绝。**该探测用错了端口**：我当时不掌握权威端口便自行猜测 8000，并据此在本文写下「并无权威 base-url/端口」——**该表述不准确，已由总协调纠正**（权威值为 7861）。此项保留仅为如实记录我犯过的错，**不得再被引用为服务不可达的证据** |
| **认证凭据** | 同上 17 个候选名 + 受限配置文件 + token 文件逐项取证 | **本地不存在受限 `APP_REPORT_NARRATION_API_KEY`** ⇒ 无法构造带认证的 Java→真实 AI 调用。**这是现场门禁唯一且充分的阻塞原因** |

⇒ **B 侧当时阻塞**，阻塞性质为**纯凭据缺失**（非网络、非合同、非代码）：只要 root 在受限环境中提供
`APP_REPORT_NARRATION_API_KEY`（base-url 用 `http://10.3.6.163:7861`），即可执行，**无需任何代码改动**。
**该判断已被 root 的实际执行证实**：root 取得凭据后在隔离临时环境跑通了真实联调（**§14**），
且**未改动任何代码** ⇒ 本节"零代码改动即可执行"的结论成立。
**B 侧当时不声称现场通过、不回退 mock、不伪造联调结果**，该纪律保持不变。
当时列为未验证的三项，现状更新如下：
- **AI 实际事件顺序与终态字段** → **已由 root 验证**（`accepted`→`delta`×6→`completed` 映射为
  `start`→`text_delta`×6→`done`、`seq` 1..8、恰一终态；见 §14.2/§14.3）；
- **`score=null` 的真实可接受性** → **仍未验证**（合成样例三组与 26 个 region 的 score 全非 null；
  见 §14.4 第 2 项）；
- **regions 左右/区域码口径** → **仍未验证**（服务端只原样转发，无法从一次成功调用推断 AI 用画面左右
  还是本人左右；见 §14.4 第 3 项）。
现有普通 Worker 报告因缺三组而 **422 fail-closed 是预期行为**（§6），**该结论未因 §14 改变**。

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

**本节记录的是 B 侧当时的证据分层，其结论已被 §14 部分取代，现更正如下：**
- 「Java 真正调用 dev.ai-skin llm-rag-api」：**B 侧当时阻塞未执行**；**root 已于 2026-09-17 执行并通过**（§14）。
- 「云台侧 200 / 首 delta 早于 done / 增量拼接一致 / 错误路径」：B 侧当时只有**本地 stub + 真实 PG/Bearer**
  的离线证据；**root 的现场执行已给出真实 AI 服务下的同类证据**（200、`start`→6×`text_delta`→`done`、
  484 字符拼接一致、缺 `spots` → 422 且下游打开计数仍为 1）。
- 「**取消路径**」：**仍只有离线证据**（`ReportNarrationStreamIT` 本地 stub）；root 本次**未在现场验证**
  （§14.4 第 5 项）。

**三类证据不得混同：B 离线 stub ≠ root 现场真实 AI ≠ 真实 Worker 报告链路（后者仍未打通）。**

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

## 14. root 现场联调证据（2026-09-17）——**root 执行，B 未独立复核**

### 14.1 归因、隔离方式与本节边界
- **执行者：root**（在 `internal.dxg170`）。**B/OpenCode 侧未执行、未参与、未独立复核**该次运行；
  本节所有观测均为 **root 报告的证据**，B 只在 §14.3 把它们与**代码事实**交叉印证。
- **隔离方式**：临时 PostgreSQL **仅绑 `127.0.0.1:18434`**、临时 Java 服务 **仅绑 `127.0.0.1:18390`**；
  跑完**已停止并删除**临时 Java、临时 PG 与私有目录；**持久 `openvela-backend.service` 保持 active**
  （未被重启或修改）。
- 本节**不含**任何凭据、token、播报文本或合成 JSON 全文，只记结构化计数。

### 14.2 root 观测到的事实
| 项 | 观测 |
|---|---|
| 合成样例 | 三组 `pores`/`spots`/`surface_gloss`，region 数 **9 / 8 / 9**（合计 **26**），**无个人信息** |
| 对样例的唯一改动 | **仅临时数据库的 `report_payload`** 添加 `schema_version=1`；**原始样例文件未变** |
| 合成设备登录 | `POST /api/v1/gimbal-sessions` → **200** |
| 播报 SSE | Bearer `GET` → **200**、`text/event-stream`、**`no-store`**、**`X-Request-Id` 非空** |
| 事件序列 | `start` → **6 × `text_delta`** → `done`；**`seq` 1..8**；每帧 `requestId`/`taskId`/`reportId` **一致** |
| 文本量与耗时 | `text_delta` 合计 **484 字符**、约 **0.1 秒** |
| Java 日志 | 下游 `stream opened status=200` **恰一次**；**无** spoken_text mismatch / non-2xx / timeout / transport failure |
| 错误路径 | 同一临时 payload **去掉 `spots`** → **预流 HTTP 422 JSON、`UNSUPPORTED_CONTRACT`**；**AI 下游打开计数仍为 1**（即未新开下游）；随后**数据已恢复** |

### 14.3 B 的代码侧交叉印证（**这一列是 B 自己核实的代码事实**，与 root 观测逐条吻合）
| root 观测 | 代码依据 | B 的结论 |
|---|---|---|
| 需给 `report_payload` 加 `schema_version` | `V1__create_tables.sql:219-220` 的 `ck_assessment_report_payload_schema`：`report_payload` 必须是 object 且含**数值型** `schema_version` | 该添加是 **DB CHECK 强制**，非装饰性改动 |
| 加 `schema_version` 是否影响 AI body | 抽取器只读 `GROUPS = List.of("pores","spots","surface_gloss")`（`ReportNarrationScoreExtractor:59`）、body 恰由这三组组装（`:95`）、**未知键记日志并丢弃**（`:248-250`）；已审 IT 的四个夹具（`:72`/`:84`/`:93`/`:103`）本就含 `schema_version` 且全部通过 | **AI body 不可能因此改变**；root"原始样例未变、只在临时库加"与代码事实一致 |
| `no-store` | `ReportNarrationStreamController:63` `.cacheControl(CacheControl.noStore())` | 吻合 |
| `X-Request-Id` 非空 | `BearerAuthFilter:150` `response.setHeader(RequestIdFilter.HEADER, id)` | 吻合 |
| `seq` 1..8（start + 6 delta + done = **8** 帧） | `ReportNarrationService:166` `int seq = 0` + **7 个写帧点写前自增**（`:172/176/180/185/192/202/209`） | **算术逐位吻合**（1 + 6 + 1 = 8 ⇒ seq 恰为 1..8） |
| `stream opened status=200` 恰一次 | `HttpReportNarrationClient:144` 的 `log.info("report narration downstream stream opened … status=…")` | 吻合；"恰一次"= 单次下游调用，无重试放大 |
| 错误路径下**下游打开计数仍为 1** | 抽取与校验发生在**开流之前**（`ReportNarrationService` 预流顺序 `:100-128`） | **决定性印证**：422 是**预流 fail-closed**，缺三组时**根本不产生任何下游 AI 调用** |
| 无 spoken_text mismatch | `ReportNarrationSseParser:210-225` 对上界内累计的 delta 文本与 `completed.spoken_text` 做**逐字比较**，不一致才置标志并 `log.warn`（只记长度） | Oracle r2 **IMPORTANT 3** 的修法**在真实服务上首次得到确认**：484 字符拼接 == 完整 `spoken_text` |

> 说明：§14.3 只证明"root 的观测与我方代码的既定行为一致"，**不构成 B 对该次运行的独立复核**
> （B 没有该临时环境的访问权，也未重新执行）。

### 14.4 这次**证明了**什么、**没有证明**什么（严格区分，不得混同）
**已证明（在合成 V3 输入下）**：
1. Java → **部署中的真实 llm-rag-api** 的 SSE 链路可通：认证请求头被接受；下游
   `accepted`→`delta`×6→`completed` 正确映射为外部 `start`→`text_delta`×6→`done`；`seq` 严格连续；
   响应头契约（200 / `text/event-stream` / `no-store` / `X-Request-Id`）成立；每帧三个 ID 一致。
2. **增量拼接与下游完整文本逐字一致**（无 mismatch 告警）。
3. **预流 fail-closed 在真实环境成立**：缺 `spots` → **422 `UNSUPPORTED_CONTRACT`** 且**未新开下游**。

**未证明 / 仍未验证**：
1. **当前 Worker 的 T05 `report_payload` 不可播报**——Worker 仍只写六键、不含三组 ⇒ **真实报告仍会 422**。
   **真实 Worker 链路未打通**，这一点**没有**因本次联调而改变；解除条件仍是 §11 第 1 项
   （D 上游补齐并冻结四键结构）。
2. **`score=null` 的真实 AI 可接受性**——合成样例三组与全部 26 个 region 的 `score` **全非 null**
   （B 独立结构复核，见 `remote-smoke-plan.md` §0.1）⇒ 本次**完全未触及**该分支。
3. **原始左右口径**（画面左右 vs 受检者本人左右）——服务端**只原样转发**，一次成功调用**无法推断**
   AI 采用哪种口径；若日后发现 AI 期望 `F`/`L`/`R` 或本人左右，**须停止并回报差异，不得自作映射**。
4. 阈值与区域码口径**未经真实标定**；本次为**合成**数据，**不得**当作算法有效性或临床准确性证据。
5. **取消路径**（客户端断开 → 及时关闭下游 AI 连接）本次**未在现场验证**；其证据仍只有离线的
   `ReportNarrationStreamIT`（本地 stub）。
6. 多实例/并发、长文本（接近解析器 200 000 字符上界）、下游超时与非 2xx 的**现场**行为**未覆盖**
   （离线已由 17 项解析器测试与 14 项 StreamIT 覆盖）。

**⇒ 一句话结论**：本次仅证明**合成 V3 输入下的 Java → 真实 AI 链路与预流错误路径**；
**不证明**当前 Worker 报告可播报。**不得**据此声称"端到端已打通"。
