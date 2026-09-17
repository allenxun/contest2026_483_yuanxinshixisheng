# B：M3-A07 报告播报 SSE 真实接入（交付说明）

日期：2026-09-17 ｜ 分支：`feature/mvp-identity-devices` ｜ 基线 `f3c29f0`
写域：`backend/web-java/**`（+ 本文件）。**未 commit**（由 orchestrator 统一提交）。

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
`seq` 从 1 起严格 +1；`X-Request-Id` 响应头与每帧 `requestId` 相等；不支持 Last-Event-ID/重放/续传。

## 3. 两处"报告而非猜测"的裁定（落实位置）

- **裁定 A（`score=null` 原样透传）**：
  `ReportNarrationScoreExtractor.java:32-36`（javadoc 裁定）、`HttpReportNarrationClient.java:282-300`
  （`putScore`/`putSeverity` 写 JSON null，绝不 coerce 成 0）。
  测试：`HttpReportNarrationClientTest.nullScoreAndSeverityPreserved`、
  `ReportNarrationStreamIT.nullPassthroughWhitelistAndHeaders`（stub 侧断言 JSON null）。
  **null 的可接受性尚未经真实 AI 确认**；若真实服务拒绝 null，由 root 联调暴露后回报总协调，
  Java 侧不擅自改为拒绝或补值。
- **裁定 B（regions 零语义转换）**：
  `ReportNarrationScoreExtractor.java:37-40`（javadoc 明写不照抄 D 的 `100-score` 反转与 `F/L/R/C`）。
  测试：`ReportNarrationScoreExtractorTest.regionsAreNotTransformed`、
  `ReportNarrationStreamIT.nullPassthroughWhitelistAndHeaders`（body 里区域名逐字一致）。

## 4. 两条流纪律裁定（落实位置）

- **零 delta + completed → error 终态**：`ReportNarrationSseParser.java:197-198`。
  测试：`ReportNarrationSseParserTest.completedWithoutAnyDeltaRejected`、
  `ReportNarrationStreamIT.zeroDeltaCompletedYieldsError`。
- **累计 delta 与 `spoken_text` 不一致只 `log.warn` 字符长度、仍发 done**：
  `ReportNarrationSseParser.java:199-203`（只记两个长度，绝不记内容）。
  测试：`ReportNarrationSseParserTest.mismatchStillCompletes`。

## 5. 配置与降级

`application.yml`（紧随 `app.gimbal-ai`）新增 `app.report-narration.base-url/api-key`（默认空占位）、
`connect-timeout-millis=3000`、`read-timeout-millis=30000`（read 为**每行 poll** 超时，非总时长；
报告播报长文本，30s 与 D 的非流式 assess 默认同量级）。四态装配见 `ReportNarrationProvidersConfig`：
`mode=disabled` → 503；缺键且非生产 → 503；缺键且生产信号 → 拒绝启动（消息只列键名）；
齐备 → 真实客户端。

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
