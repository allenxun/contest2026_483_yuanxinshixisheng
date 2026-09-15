# mock-report-stream Oracle 审查报告（MOCK 联调增量）

- 日期：2026-09-15
- 工作树/分支：`.worktrees/mock-report-stream` / `feature/mock-report-stream`（未合并 dev、未推送、未部署）
- 被审查最终代码提交（reviewedCommit）：`255e2c8d2920c5284f7559f7eb1924ae1e01cdde`
- 审查方式：实际调用已安装 omo-slim `oracle` 子代理（mode=subagent，沿用现有模型配置），独立只读审查，绑定上述 SHA。本报告提交为 docs-only，晚于且不改被审代码；被审代码 SHA 不因本报告变化。

## 结论（Oracle 原文）

> **Reviewed commit:** `255e2c8d2920c5284f7559f7eb1924ae1e01cdde`
>
> 未发现阻塞或重要问题。实现满足 MOCK SSE、鉴权与当前任务隔离、固定文案、事件顺序/字段、预流 JSON 错误及限定测试要求。
>
> Scope 已确认：提交仅新增指定 5 个文件（697 行），未修改既有文件，未触碰 contract、`backend/doc/site`、`backend/doc/web`、`logs/` 或其他 package。
>
> **PASS**

无阻塞项，无需复审轮次。

## 增量定性（必读）

本增量是**用户本轮授权的 MOCK 联调端点**，目标是测通 SSE 功能：**未接真实算法、未接 RAG、未调用任何 AI、不读取密钥**；播报文案由**固定联调 JSON**（F/L/R/C × O/P/D 分数与标签）按“每区 O/P/D 算术平均、HALF_UP 取整”派生（额头61、左脸39、右脸67、下巴45），**非正式算法结果，不得当作真实测肤结论或医疗建议**。该端点未在任何 backend/doc 设计文档中定义，按 gimbal-ai 先例作为用户授权增量以 **catalog-only** 方式登记文档，不写入 `backend/contracts/openapi/openapi.yaml`（不占用 M3-Axx 正式契约编号）。

## 交付内容

端点：`GET /api/v1/skin-assessment-tasks/{taskId}/report-narration-stream`（`Accept: text/event-stream`）

- 鉴权与隔离：沿用既有 Bearer/device-token 体系；仅 GIMBAL 主体（APP→403 `CALLER_NOT_ALLOWED`）；复用 `AssessmentReadService.getTask` 完成“非本云台任务→404 `RESOURCE_NOT_VISIBLE`、已非当前任务→409 `TASK_REPLACED`”隔离，未新建第二套规则；`reportId` 为空（非 `report_ready`）→404。建流前所有错误走既有 JSON 错误信封与真实 HTTP 状态。
- SSE：`start → text_delta ×2 → done`，逐事件 flush；data 含 `requestId/taskId/reportId/seq`（`text_delta` 另含 `delta`），seq 自 1 严格 +1；done/error 互斥（流内意外异常时恰一个 `error` 终态，仅固定安全字段）；客户端断开静默结束本次发送；不支持 Last-Event-ID/续传/重放/取消 API。
- 生产 fail-closed：生成器 `@Conditional(NonProductionCondition)`；生产环境 bean 缺席 → 预流 503 `DEPENDENCY_UNAVAILABLE`。

新增文件（全部为新文件，零既有文件修改）：

1. `backend/web-java/src/main/java/cn/yuanxin/mvp/web/assessments/narration/MockReportNarrationGenerator.java`（MOCK 数据与文案生成器，javadoc 显著标注 mock 定性）
2. `backend/web-java/src/main/java/cn/yuanxin/mvp/web/assessments/narration/ReportNarrationStreamController.java`
3. `backend/web-java/src/main/java/cn/yuanxin/mvp/web/assessments/narration/ReportNarrationStreamErrorAdvice.java`（见“偏差”）
4. `backend/web-java/src/main/java/cn/yuanxin/mvp/web/docs/catalog/ReportNarrationStreamDocs.java`（catalog-only 文档，描述中披露 mock 定性与全部限制）
5. `backend/web-java/src/test/java/cn/yuanxin/mvp/web/assessments/ReportNarrationStreamIT.java`（恰 2 项聚焦测试）

事件示例（测试实录原始帧，UUID 为当次运行值）：

```
event: start
data: {"requestId":"ff8a42be-…","taskId":"feac662b-…","reportId":"44d7ceda-…","seq":1}

event: text_delta
data: {"requestId":"ff8a42be-…","taskId":"feac662b-…","reportId":"44d7ceda-…","seq":2,"delta":"本次完成额头、左脸、右脸和下巴四个区域的皮肤检测。"}

event: text_delta
data: {"requestId":"ff8a42be-…","taskId":"feac662b-…","reportId":"44d7ceda-…","seq":3,"delta":"额头61分，左脸39分，右脸67分，下巴45分。"}

event: done
data: {"requestId":"ff8a42be-…","taskId":"feac662b-…","reportId":"44d7ceda-…","seq":4}
```

两段 delta 拼接逐字节等于验收文案：`本次完成额头、左脸、右脸和下巴四个区域的皮肤检测。额头61分，左脸39分，右脸67分，下巴45分。`

## 验证证据（orchestrator 亲跑，绑定已提交树状态）

| 命令（`backend/web-java` 下） | 结果 |
| --- | --- |
| `mvn -B -Dtest=ReportNarrationStreamIT test` | Tests run: 2, Failures: 0, Errors: 0, rc=0, BUILD SUCCESS |
| `mvn -B -Dtest=ApiDocsCoverageIT test` | Tests run: 1, Failures: 0, Errors: 0, rc=0（catalogs=7 covered=36/36 missing=0） |

按用户指示**未运行全量测试套件**：本增量为纯新文件、零既有文件改动，聚焦验证已覆盖路由、SSE 事件顺序/字段、文案逐字节一致与一个关键拒绝场景（APP→403）。既有 JSON 报告接口未改动。

## 偏差与决策披露

- **规格外新增 `ReportNarrationStreamErrorAdvice`**（仅限新控制器，`assignableTypes` 限定 + `@Order(HIGHEST_PRECEDENCE)`，只处理 `ApiException`）：根因是 `produces=text/event-stream` 且客户端 `Accept: text/event-stream` 时，全局异常处理器的 JSON 信封未预设 Content-Type，Spring 内容协商无法匹配 → `HttpMediaTypeNotAcceptableException` → 预流 403/404/409/503 退化为 500。该 advice 输出与全局处理器完全相同的 `ErrorEnvelope`（同 code/message/retryable/details/headers），仅显式预设 `application/json`；不影响任何其他端点。实施方实证仅移除 `produces` 不能修复（`Accept` 头本身即触发协商失败）。
- **catalog-only 而非写入 openapi.yaml**：mock 联调增量非正式 API，沿用 gimbal-ai 用户授权增量先例，避免占用 M3-Axx 契约编号；`ApiDocsCoverageIT` 对无契约操作按既有口径跳过错误码交叉校验（实测通过）。

## 已知限制（非阻塞，如实披露）

1. 非 `ApiException` 的 MVC 层错误（如 taskId 非法 UUID 格式）在 `Accept: text/event-stream` 下仍经全局处理器协商失败退化为 500（mock 范围可接受）。
2. 理论边界：`done` 帧部分写出后若再抛 RuntimeException，可能在残缺 done 后追加 error 帧（残缺帧不构成可解析终态；实际触发路径几乎不存在）。
3. mock 分数与真实供应商 O/P/D 语义无关；固定文案不涉及 L/R 方位取向的未决决策（N.5）。
4. 无断点续传/重放/持久化/取消（按用户规格明确不做）。

## 提交链

- `255e2c8d2920c5284f7559f7eb1924ae1e01cdde`：代码提交（被审最终代码 SHA，Oracle PASS）。
- 本报告为紧随其后的 docs-only 提交，不含任何代码变化。
