package cn.yuanxin.mvp.web.docs.catalog;

import cn.yuanxin.mvp.web.care.CareAdmissionDtos.CareExecutionAdmission;
import cn.yuanxin.mvp.web.care.CareAdmissionDtos.CareExecutionRevalidation;
import cn.yuanxin.mvp.web.care.CareAdmissionDtos.M4A03Metadata;
import cn.yuanxin.mvp.web.care.CareAdmissionDtos.M4A04Metadata;
import cn.yuanxin.mvp.web.care.CareLedgerDtos.ClosureResultDto;
import cn.yuanxin.mvp.web.care.CareLedgerDtos.ObservationAckDto;
import cn.yuanxin.mvp.web.care.CareProjections.CareExecutionListItem;
import cn.yuanxin.mvp.web.care.CareProjections.CareExecutionView;
import cn.yuanxin.mvp.web.care.CareProjections.CarePlanFullView;
import cn.yuanxin.mvp.web.care.CareProjections.CarePlanListItem;
import cn.yuanxin.mvp.web.care.CareProjections.ProgressWithSync;
import cn.yuanxin.mvp.web.error.ErrorCode;
import io.swagger.v3.oas.models.tags.Tag;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.context.annotation.Profile;
import org.springframework.stereotype.Component;

import java.util.List;
import java.util.Map;

/**
 * 「照护方案与执行」域联调文档目录（M4-A01..A09，共 9 个操作）。
 *
 * <p>权威来源：{@code backend/contracts/openapi/openapi.yaml} 的 M4-A01..A09
 * （中文 summary/description/x-error-codes 与成功码）、{@code backend/doc/后端详细设计-V1-MVP.md}
 * 的 DD 6.1—6.4/7.2/7.3、{@code backend/doc/数据架构设计-V1-五模块-MVP.md} 的 T06/T07/T08、
 * {@code backend/doc/后端API接口设计-V1-五模块与流程对应.md} 6.2（K≥N 即完成、剩余 max(N-K,0)、
 * K 不截断、下载/启动/重传不计完成）、{@code backend/doc/角色边界与流程修订说明.md}（N/K 单位=次数），
 * 以及各控制器/DTO 源码。自由结构唯一合法来源为 {@code care/CarePlanProjection.java} 的三套白名单
 * （SUMMARY/FULL/EXECUTION），其注释明示"待总协调/D 契约确认后冻结"，故文档如实标注未冻结状态。</p>
 *
 * <p>本类只写文档内容，不触碰任何控制器/DTO/业务代码（零序列化/行为变更）。</p>
 */
@Component
@Profile({"dev", "test"})
@ConditionalOnProperty(name = "springdoc.api-docs.enabled", havingValue = "true")
public class CareApiDocs implements ApiDocsCatalog {

    /** 护理方案的查询与进度。 */
    private static final String TAG_PLAN = "护理方案";
    /** 护理执行的核验、准入、重核验与执行详情。 */
    private static final String TAG_EXECUTION = "护理执行";
    /** 实际状态/记录同步与停止后收尾。 */
    private static final String TAG_LEDGER = "执行记录与收尾";

    @Override
    public String domain() {
        return "care";
    }

    @Override
    public List<Tag> tags() {
        return List.of(
                new Tag().name(TAG_PLAN)
                        .description("护理方案（M4-A01/A02/A08）：列表、完整版与累计进度查询。"
                                + "仅已授权 APP（进度端点另接受具备当前已核验执行上下文的云台）。"
                                + "进度口径：N=目标次数、K=已同步次数、剩余=max(N-K,0)、K>=N 即完成、K 不截断。"),
                new Tag().name(TAG_EXECUTION)
                        .description("护理执行（M4-A03/A04/A07）：人脸核验后登记新执行、连续性失效后重新核验、"
                                + "查询执行与恢复联网后的对账状态。成功仅表示\"已登记，待端侧确认\"，不宣称硬件已运行。"),
                new Tag().name(TAG_LEDGER)
                        .description("执行记录与收尾（M4-A05/A06/A09）：同步微晶实际状态与有效完成记录、"
                                + "确认本地已停止并完成收尾、查看成员护理执行历史。收尾是停止后的确认，不是远程停止命令。"));
    }

    @Override
    public Map<String, ApiDocEntry> entries() {
        return Map.ofEntries(

                // ------------------------------------------------------- M4-A01
                Map.entry("GET /api/v1/members/{memberId}/care-plans", new ApiDocEntry(
                        TAG_PLAN,
                        "列出本人方案与生成状态",
                        """
                        用途：列出指定成员（本人）的护理方案及生成状态，供 APP 判断"方案是否就绪"；只读，不触发方案生成、不改变任何状态。
                        调用方：仅 APP（APP session token）。云台不能调用本接口——云台执行前取得方案走 M4-A03。
                        前置：当前 APP 账号对该 memberId 持有 T02 active 成员访问授权；无授权/不存在/已撤销统一 404
                        RESOURCE_NOT_VISIBLE（不区分，不泄露存在性）。
                        关键规则：无方案行返回空数组；waiting_inputs/generating/failed 也如实返回 generationStatus；
                        仅 ready 的方案附带 progress 与 planSummary。planSummary 为 T06.plan_summary 的封闭白名单投影
                        （仅 title/description/source_report_id/source_report_ready_at，未知键丢弃，schema_version 绝不外发）。
                        分页：keyset 游标不透明、绑定排序值+ID+reportId 筛选摘要，原样回传；非法/筛选不匹配 → 400
                        INVALID_INPUT；limit 默认 20、上限 100，不返回总数。
                        字段与枚举：generationStatus ∈ waiting_inputs|generating|ready|failed；
                        N=targetCount（单位：次，ready 时必填且 >0）、K=completedCount、剩余=max(N-K,0)、isCompleted=K>=N；
                        所有计数/代次为无符号 bigint 十进制字符串。
                        错误处理：INVALID_INPUT 修正参数；AUTH_REQUIRED/SESSION_INVALID 重新登录；CALLER_NOT_ALLOWED
                        （云台主体）改用正确端点；RESOURCE_NOT_VISIBLE 不要换 ID 探测；RATE_LIMITED/DEPENDENCY_* 受限退避重试。
                        契约过声明：GRANT_REVOKED 在本端点当前实现中不触发（实现统一用 RESOURCE_NOT_VISIBLE 表达
                        不可见/已撤销）；按契约一致性保留该码，待总协调裁定。
                        """,
                        List.of(
                                ApiDocEntry.ParamDoc.of("memberId", "path",
                                        "必填，路径参数，UUID 字符串（T01.id），成员引用。", "11111111-1111-4111-8111-111111111111"),
                                ApiDocEntry.ParamDoc.of("reportId", "query",
                                        "可选，查询参数，UUID 字符串（T05.report_id）；按来源报告筛选。传入不存在或非本人报告"
                                                + "返回空页（不泄露存在性）。", "44444444-4444-4444-8444-444444444444"),
                                ApiDocEntry.ParamDoc.of("limit", "query",
                                        "可选，查询参数，整数；分页大小，默认 20、上限 100、最小 1；不返回总数。", "20"),
                                ApiDocEntry.ParamDoc.of("cursor", "query",
                                        "可选，查询参数，字符串；keyset 不透明游标（绑定排序值+ID+reportId 筛选摘要），"
                                                + "原样回传；非法或与当前筛选不匹配 → 400 INVALID_INPUT；缺省表示第一页。")),
                        List.of(),
                        null,
                        null,
                        List.of(ApiDocEntry.SuccessDoc.jsonList("200",
                                "方案列表页；data={items:[CarePlanListItem], nextCursor:string|null}，nextCursor 为 null 表示无后续页",
                                CarePlanListItem.class)),
                        List.of(ErrorCode.INVALID_INPUT, ErrorCode.AUTH_REQUIRED, ErrorCode.SESSION_INVALID,
                                ErrorCode.CALLER_NOT_ALLOWED, ErrorCode.RESOURCE_NOT_VISIBLE,
                                ErrorCode.GRANT_REVOKED, ErrorCode.RATE_LIMITED,
                                ErrorCode.DEPENDENCY_UNAVAILABLE, ErrorCode.DEPENDENCY_TIMEOUT,
                                ErrorCode.NOT_IMPLEMENTED))),

                // ------------------------------------------------------- M4-A02
                Map.entry("GET /api/v1/care-plans/{planId}", new ApiDocEntry(
                        TAG_PLAN,
                        "查询方案完整版",
                        """
                        用途：查询单个护理方案的完整投影：ready 时含 Plan 正文与 Progress，未就绪时返回公开等待/失败原因。
                        只读：GET 不生成方案、不登记执行、不累计进度。
                        调用方：仅 APP（APP session token），view 仅支持 full。
                        前置：当前 APP 账号对方案所属成员持有 active 授权（否则 404 RESOURCE_NOT_VISIBLE）。
                        关键规则：查到方案不等于获准启动（启动须走 M4-A03 人脸核验准入）；云台不可借本接口取方案
                        （执行简版由 M4-A03/A04 返回）。
                        字段与枚举：generationStatus ∈ waiting_inputs|generating|ready|failed。ready 时 plan 为
                        T06.plan_payload 的封闭白名单投影（仅 title/description/steps/regions/parameters；
                        schema_version 绝不外发；禁止返回供应商原始响应/提示词），progress 为 N/K/剩余/达标；
                        未就绪时 plan/progress 为 null，waitingReason ∈ waiting_inputs|generating|generation_failed（否则 null）。
                        未冻结：方案 steps/parameters 的结构与微晶参数名、单位、范围尚未在契约冻结，
                        CarePlanProjection 白名单为 C 侧保守提案（其注释明示待总协调/D 契约确认后冻结），客户端不得据此假设固定键集。
                        错误处理：INVALID_INPUT（view≠full）；AUTH_REQUIRED/SESSION_INVALID；CALLER_NOT_ALLOWED（云台）；
                        RESOURCE_NOT_VISIBLE；RATE_LIMITED/DEPENDENCY_* 受限退避重试。
                        契约过声明：GRANT_REVOKED、PLAN_NOT_READY 在本端点当前实现中均不触发——未就绪以 200 +
                        waitingReason 返回，撤销/不可见统一 404 RESOURCE_NOT_VISIBLE；按契约一致性保留，待总协调裁定。
                        """,
                        List.of(
                                ApiDocEntry.ParamDoc.of("planId", "path",
                                        "必填，路径参数，UUID 字符串（T06.id），方案引用。", "33333333-3333-4333-8333-333333333333"),
                                ApiDocEntry.ParamDoc.of("view", "query",
                                        "可选，查询参数，字符串；本接口视图仅支持 full（默认 full）；传入其他值 → 400 INVALID_INPUT。",
                                        "full")),
                        List.of(),
                        null,
                        null,
                        List.of(ApiDocEntry.SuccessDoc.json("200",
                                "方案完整投影；ready 时 data.plan 与 data.progress 非空，未就绪时 data.waitingReason 给出公开原因",
                                CarePlanFullView.class)),
                        List.of(ErrorCode.INVALID_INPUT, ErrorCode.AUTH_REQUIRED, ErrorCode.SESSION_INVALID,
                                ErrorCode.CALLER_NOT_ALLOWED, ErrorCode.RESOURCE_NOT_VISIBLE,
                                ErrorCode.PLAN_NOT_READY, ErrorCode.GRANT_REVOKED, ErrorCode.RATE_LIMITED,
                                ErrorCode.DEPENDENCY_UNAVAILABLE, ErrorCode.DEPENDENCY_TIMEOUT,
                                ErrorCode.NOT_IMPLEMENTED))),

                // ------------------------------------------------------- M4-A03
                Map.entry("POST /api/v1/care-executions", new ApiDocEntry(
                        TAG_EXECUTION,
                        "人脸核验、取得方案并登记新执行",
                        """
                        用途：9/13 联调核心端点。对人脸核验当前使用者、校验方案就绪/微晶能力/占用，并原子登记一次新护理执行。
                        成功仅表示"已登记，待端侧确认"（status=admitted），绝不宣称硬件已运行；端侧须自行确认核验仍适用、
                        本地微晶就绪后才首次启动。
                        调用方：APP（metadata 提供 planId，须对该成员有 active 授权）或云台（metadata 提供 currentTaskId 与
                        currentAssessmentRevision，方案由后端从云台唯一当前测肤任务确定）。主体身份只由 token 派生，
                        请求体不决定 memberId/controller。
                        请求：multipart/form-data，metadata（JSON，M4A03Metadata）+ face（当前人脸图片二进制；按内容嗅探
                        支持 JPEG/PNG/GIF/WebP，单图上限约 10MiB 以配置为准）。必须携带 Idempotency-Key。
                        前置与顺序（联调排程依据）：
                         1) capture.purpose 必须为 admission；
                         2) 方案 generation_status=ready，否则 409 PLAN_NOT_READY；能力覆盖不足时 details.reason 为有界 token：
                            device_capabilities_missing|frozen_capability_requirement_missing|malformed_frozen_capability|
                            capability_id_mismatch|parameter_range_not_covered|region_not_supported|n_out_of_bounds|
                            step_parameters_not_covered|malformed_frozen_step；
                         3) 方案未完成 K<N，否则 409 PLAN_COMPLETED；
                         4) 云台路径 currentTaskId/currentAssessmentRevision 须与云台 current_assessment 指针及代次精确一致，
                            否则 409 TASK_REPLACED；APP 路径须持 active 授权，否则 404 RESOURCE_NOT_VISIBLE；
                         5) 微晶/云台无未收尾占用（部分唯一索引兜底），否则 409 DEVICE_OCCUPIED（不泄露对方成员）。
                        成功与幂等：首次成功 201，data=CareExecutionAdmission（status=admitted、controller、planExecution
                        执行简版、progress、verification、recordStreamEpoch 由后端以 executionId 派生并返回）；相同
                        Idempotency-Key 同内容重放返回 200 且 meta.replayed=true（不得当作首次启动许可，不产生新的核验有效性、
                        不重新启动）；同键异内容 409 IDEMPOTENCY_CONTENT_CONFLICT；处理中 409 REQUEST_IN_PROGRESS
                        （按 Retry-After 用同一键重试）。
                        关键规则：人脸照片保存/读取失败不得返回本轮核验通过；换人不返回原成员方案。
                        字段单位/枚举：N/K/剩余为无符号 bigint 十进制字符串（单位：次）；progressRevision 默认 0；
                        首次 verificationRevision="1"；capturedAt 为 RFC3339 UTC。
                        错误处理：INVALID_INPUT/UNSUPPORTED_IMAGE/UPLOAD_TOO_LARGE/FACE_QUALITY_REJECTED 修正或重采后重试
                        （换内容须用新 Idempotency-Key）；FACE_NOT_VERIFIED 重新采集本人清晰照片（不泄露成员是否存在）；
                        DEVICE_OCCUPIED 先停止并收尾在跑执行；TASK_REPLACED 以云台当前任务为准；AUTH_REQUIRED/SESSION_INVALID
                        重新登录/握手；RATE_LIMITED/DEPENDENCY_* 受限退避重试。
                        契约过声明：CALLER_NOT_ALLOWED、BINDING_CHANGED 在本端点当前实现中不触发（本端点同时接受 APP 与云台，
                        错误主体/入参组合走 INVALID_INPUT；护理准入无绑定代次入参）；按契约一致性保留，待总协调裁定。
                        """,
                        List.of(new ApiDocEntry.ParamDoc("Idempotency-Key", "header",
                                "必填，请求头，字符串 1—128 字符；控制器强制（缺失/空白 → 400 INVALID_INPUT）。T13 逻辑请求"
                                        + "去重键（principal+operation+key）：同键同内容重放返回同一执行且 meta.replayed=true（200），"
                                        + "同键异内容 409。生成文档默认 required=false，此处按契约与控制器实际强制覆盖为必填。",
                                "adm-20260913-0001", Boolean.TRUE)),
                        List.of(
                                ApiDocEntry.MultipartPartDoc.json("metadata",
                                        "必填，JSON part（application/json），M4A03Metadata；APP 提供 planId，云台提供 "
                                                + "currentTaskId+currentAssessmentRevision，按调用角色二选一。",
                                        M4A03Metadata.class),
                                ApiDocEntry.MultipartPartDoc.binary("face", "image/png",
                                        "必填，图片二进制 part；当前人脸照片，绑定本轮请求与控制端上下文。按内容嗅探支持 "
                                                + "JPEG/PNG/GIF/WebP，单图上限约 10MiB（以配置为准）；照片保存/读取失败不得返回核验通过。")),
                        null,
                        "multipart/form-data：metadata（JSON，M4A03Metadata）+ face（人脸图片二进制），两者均必填。"
                                + "Idempotency-Key 与 JCS payload_hash（含图片摘要）共同保证同键同内容才重放；换人脸或换业务内容须换新键。",
                        List.of(
                                ApiDocEntry.SuccessDoc.json("201",
                                        "新执行登记成功（status=admitted，未声称硬件运行）；data=CareExecutionAdmission",
                                        CareExecutionAdmission.class),
                                ApiDocEntry.SuccessDoc.json("200",
                                        "相同请求幂等重放：返回同一执行、meta.replayed=true、verification.replayed=true；"
                                                + "不得当作首次启动许可",
                                        CareExecutionAdmission.class)),
                        List.of(ErrorCode.INVALID_INPUT, ErrorCode.UPLOAD_TOO_LARGE, ErrorCode.UNSUPPORTED_IMAGE,
                                ErrorCode.FACE_QUALITY_REJECTED, ErrorCode.AUTH_REQUIRED, ErrorCode.SESSION_INVALID,
                                ErrorCode.CALLER_NOT_ALLOWED, ErrorCode.FACE_NOT_VERIFIED,
                                ErrorCode.RESOURCE_NOT_VISIBLE, ErrorCode.DEVICE_OCCUPIED, ErrorCode.PLAN_NOT_READY,
                                ErrorCode.PLAN_COMPLETED, ErrorCode.TASK_REPLACED, ErrorCode.BINDING_CHANGED,
                                ErrorCode.IDEMPOTENCY_CONTENT_CONFLICT, ErrorCode.REQUEST_IN_PROGRESS,
                                ErrorCode.RATE_LIMITED, ErrorCode.DEPENDENCY_UNAVAILABLE,
                                ErrorCode.DEPENDENCY_TIMEOUT, ErrorCode.NOT_IMPLEMENTED))),

                // ------------------------------------------------------- M4-A04
                Map.entry("POST /api/v1/care-executions/{executionId}/revalidations", new ApiDocEntry(
                        TAG_EXECUTION,
                        "使用者连续性失效后重新核验恢复条件",
                        """
                        用途：原执行因换人/追踪失效/断网暂停后，重新核验当前使用者并恢复可继续条件。成功仅更新核验代次与摘要，
                        执行仍保持 paused，不自动变 running；端侧须确认当前使用者与微晶条件后才继续。
                        调用方：原执行的合法控制端（APP 须原 accountId+installationId 精确一致；云台须原 controller_gimbal_id）；
                        APP 还须保留对该成员的 active 授权。
                        请求：multipart/form-data，metadata（JSON，M4A04Metadata）+ face（当前人脸图片二进制）；
                        capture.purpose 必须为 revalidation；强制 Idempotency-Key。
                        前置与顺序（联调排程依据）：① 先调用 M4-A05 上报实际 stopped/paused 观察并同步待补记录；unknown 状态
                        必须先收到新鲜 paused 观察，否则继续 409；② 执行状态必须 paused；③ expectedVerificationRevision 必须等于
                        执行当前 verificationRevision；④ 云台还须让方案属于其当前测肤任务指针，否则 409 TASK_REPLACED；
                        ⑤ 方案未完成 K<N。
                        不可恢复统一 409 EXECUTION_NOT_RESUMABLE，details.reason 有 7 种取值：
                        admitted_not_paused（状态 admitted）、running_not_paused（running）、
                        unknown_needs_fresh_paused_observation（unknown，须先经 M4-A05 收到新鲜 paused 观察）、
                        stopped_not_resumable（stopped）、closed_not_resumable（closed）、plan_completed（已达 K>=N）、
                        verification_revision_mismatch（代次不符）。（另有防御性 not_paused 分支，正常状态机下不可达。）
                        成功与幂等：200，data=CareExecutionRevalidation（沿用原 planId/planExecution/progress，executionId 不变，
                        verification 为新一轮核验）；同键同内容重放 200 且 meta.replayed=true，重放不刷新核验有效期。
                        字段与枚举：status ∈ admitted|running|paused|unknown|stopped|closed；reportedMicrocrystalState 必须为
                        JSON 对象或 null（结构未冻结，见自由结构展开）；expectedVerificationRevision 为无符号 bigint 十进制字符串。
                        错误处理：INVALID_INPUT 修正字段；FACE_NOT_VERIFIED/FACE_QUALITY_REJECTED/UNSUPPORTED_IMAGE/
                        UPLOAD_TOO_LARGE 重新采集；RESOURCE_NOT_VISIBLE 非原控制端/无授权/不存在同 404；TASK_REPLACED 以当前任务为准；
                        拟补记录与既有冲突 409 RECORD_CONFLICT，先以服务端为准修正本地；AUTH_REQUIRED/SESSION_INVALID 重新登录/握手；
                        RATE_LIMITED/DEPENDENCY_* 受限退避。
                        契约过声明：CALLER_NOT_ALLOWED、RECORD_CONFLICT 在本端点当前实现中不触发（本端点同时接受 APP 与云台，
                        错误主体走 INVALID_INPUT/RESOURCE_NOT_VISIBLE；本端点不接受记录批次，冲突由 M4-A05 处理）；
                        按契约一致性保留，待总协调裁定。
                        """,
                        List.of(
                                ApiDocEntry.ParamDoc.of("executionId", "path",
                                        "必填，路径参数，UUID 字符串（T07.id），原护理执行引用。",
                                        "22222222-2222-4222-8222-222222222222"),
                                new ApiDocEntry.ParamDoc("Idempotency-Key", "header",
                                        "必填，请求头，字符串 1—128 字符；控制器强制（缺失/空白 → 400 INVALID_INPUT）。"
                                                + "同键同内容重放返回同一结果且 meta.replayed=true，重放不刷新核验有效期；"
                                                + "生成文档默认 required=false，此处覆盖为必填。",
                                        "reval-20260913-0001", Boolean.TRUE)),
                        List.of(
                                ApiDocEntry.MultipartPartDoc.json("metadata",
                                        "必填，JSON part（application/json），M4A04Metadata；capture.purpose 必须为 revalidation。",
                                        M4A04Metadata.class),
                                ApiDocEntry.MultipartPartDoc.binary("face", "image/png",
                                        "必填，图片二进制 part；新一轮当前人脸照片。按内容嗅探支持 JPEG/PNG/GIF/WebP，"
                                                + "单图上限约 10MiB；旧图片引用不得绕过本轮连续性检查，图片失败不得恢复护理。")),
                        null,
                        "multipart/form-data：metadata（JSON，M4A04Metadata）+ face（人脸图片二进制），两者均必填。",
                        List.of(ApiDocEntry.SuccessDoc.json("200",
                                "恢复条件判定结果：保留原方案与进度 + 新一轮 Verification；执行状态不自动变 running",
                                CareExecutionRevalidation.class)),
                        List.of(ErrorCode.INVALID_INPUT, ErrorCode.UPLOAD_TOO_LARGE, ErrorCode.UNSUPPORTED_IMAGE,
                                ErrorCode.FACE_QUALITY_REJECTED, ErrorCode.AUTH_REQUIRED, ErrorCode.SESSION_INVALID,
                                ErrorCode.CALLER_NOT_ALLOWED, ErrorCode.FACE_NOT_VERIFIED,
                                ErrorCode.RESOURCE_NOT_VISIBLE, ErrorCode.EXECUTION_NOT_RESUMABLE,
                                ErrorCode.TASK_REPLACED, ErrorCode.RECORD_CONFLICT,
                                ErrorCode.IDEMPOTENCY_CONTENT_CONFLICT, ErrorCode.REQUEST_IN_PROGRESS,
                                ErrorCode.RATE_LIMITED, ErrorCode.DEPENDENCY_UNAVAILABLE,
                                ErrorCode.DEPENDENCY_TIMEOUT, ErrorCode.NOT_IMPLEMENTED))),

                // ------------------------------------------------------- M4-A05
                Map.entry("POST /api/v1/care-executions/{executionId}/observations", new ApiDocEntry(
                        TAG_LEDGER,
                        "同步实际状态与有效完成记录",
                        """
                        用途：原控制端上报微晶实际状态观察与有效完成记录（不重叠增量），后端去重累计 K；不发送任何设备控制指令。
                        调用方：原执行的合法控制端（APP 或云台）。允许该控制端补传历史执行记录（断网恢复后先补传，再走 M4-A04 重新核验）。
                        请求：application/json，body=SyncRequestDto（observation 可选 + records 必填，records 批次上限 200）；
                        强制 Idempotency-Key。
                        关键规则：观察序号（observation.seq）与记录序号（records[].sourceSeq）是两条独立递增序列，不得混算；
                        当前状态仅接受匹配执行流 epoch 且 seq 更大的观察（同 seq 同内容忽略、同 seq 异内容 409 RECORD_CONFLICT，
                        details.reason=observation_seq_conflict；epoch 不符 details.reason=observation_epoch_mismatch）；
                        sourceSeq 从 1 连续递增，epoch 由后端以 executionId 派生；记录按 T08 双唯一键去重
                        (execution_id, client_record_id) 与 (execution_id, source_epoch, source_seq)，countDelta 必须 >0；
                        相同记录重传不重复计数（记 duplicate），异内容复用标识整批 409 且不确认新记录（details.conflictingRecordIds
                        最多 20 个 + totalConflicts 总数）；乱序旧状态忽略但同批合法新记录仍入账；上报 K 不覆盖总量，
                        启动/下载/重传不计完成。closed 执行仍可接收迟到合法记录补账（不重开、不改 closed_at）。
                        成功与幂等：200，data=ObservationAckDto（acknowledgedRecords 逐条 accepted|duplicate|rejected、
                        executionStatus、acceptedCount=后端累计 K、progress 仅具备读取权限时附带）；同键同内容重放 200 且
                        meta.replayed=true。
                        字段与枚举：state ∈ running|paused|unknown|stopped；epoch ≤128；seq/sourceSeq/countDelta/
                        verificationRevision 为无符号 bigint 十进制字符串；occurredAt 为 RFC3339 UTC。
                        错误处理：INVALID_INPUT（批次超 200/格式非法/计数溢出）；RECORD_CONFLICT → 以服务端已接受记录为准修正本地，
                        只重传缺失区间；RESOURCE_NOT_VISIBLE 非原控制端；AUTH_REQUIRED/SESSION_INVALID；RATE_LIMITED/DEPENDENCY_* 受限退避。
                        契约过声明：CALLER_NOT_ALLOWED、BINDING_CHANGED 在本端点当前实现中不触发（本端点接受 APP 与云台，
                        错误主体走 RESOURCE_NOT_VISIBLE；护理记录路径无绑定代次入参）；按契约一致性保留，待总协调裁定。
                        """,
                        List.of(
                                ApiDocEntry.ParamDoc.of("executionId", "path",
                                        "必填，路径参数，UUID 字符串（T07.id），原护理执行引用。",
                                        "22222222-2222-4222-8222-222222222222"),
                                new ApiDocEntry.ParamDoc("Idempotency-Key", "header",
                                        "必填，请求头，字符串 1—128 字符；控制器强制（缺失/空白 → 400 INVALID_INPUT）。"
                                                + "同键同内容重放返回同一确认结果且 meta.replayed=true；生成文档默认 required=false，"
                                                + "此处覆盖为必填。",
                                        "sync-20260913-0001", Boolean.TRUE)),
                        List.of(),
                        null,
                        "JSON 请求体（application/json）：observation（可选，ExecutionObservationDto）+ records（必填数组，"
                                + "上限 200 条，元素为 ExecutionRecordDto）；批次 Idempotency-Key 在请求头。",
                        List.of(ApiDocEntry.SuccessDoc.json("200",
                                "逐记录处置结果 + 后端累计进度",
                                ObservationAckDto.class)),
                        List.of(ErrorCode.INVALID_INPUT, ErrorCode.AUTH_REQUIRED, ErrorCode.SESSION_INVALID,
                                ErrorCode.CALLER_NOT_ALLOWED, ErrorCode.RESOURCE_NOT_VISIBLE,
                                ErrorCode.RECORD_CONFLICT, ErrorCode.BINDING_CHANGED,
                                ErrorCode.IDEMPOTENCY_CONTENT_CONFLICT, ErrorCode.REQUEST_IN_PROGRESS,
                                ErrorCode.RATE_LIMITED, ErrorCode.DEPENDENCY_UNAVAILABLE,
                                ErrorCode.DEPENDENCY_TIMEOUT, ErrorCode.NOT_IMPLEMENTED))),

                // ------------------------------------------------------- M4-A06
                Map.entry("POST /api/v1/care-executions/{executionId}/closure-confirmations", new ApiDocEntry(
                        TAG_LEDGER,
                        "确认本地已停止并完成执行收尾",
                        """
                        用途：停止后的确认（不是远程停止命令）：以后端已收到的"微晶已停止"观察（stopObservationSeq）与记录流
                        水位（finalRecordSeq/finalCount）对账，通过后关闭执行并释放占用。
                        调用方：原执行控制端（APP 或云台）。强制 Idempotency-Key。
                        前置与顺序（联调排程依据）：① 必须先经 M4-A05 上报实际 stop 观察与全部待同步记录；
                        ② 执行状态必须 stopped，否则 409 STOP_NOT_CONFIRMED（details.reason=not_stopped）；
                        ③ stopObservationSeq 必须等于执行最后已接收观察序号且该观察为 stopped，否则 STOP_NOT_CONFIRMED
                        （details.reason=stop_observation_mismatch）；④ recordStreamEpoch 必须等于执行记录流 epoch，
                        否则 409 RECORD_CONFLICT（details.reason=epoch_mismatch）。
                        收尾水位语义：finalRecordSeq=W 表示承诺记录流范围 1..W（W=0 时要求无记录且 finalCount=0）；
                        后端在持锁事务内核对范围内记录数=W、序号 1..W 唯一、SUM(count_delta)=finalCount，任何缺口/不符返回
                        409 CLOSURE_GAPS，details 形态 {reason, missingRanges:[{from,to}], more, finalCount, totalCount}
                        （reason ∈ gaps|count_mismatch|max_seq_exceeds_final；missingRanges 有上限，more=true 表示还有更多，
                        不生成与巨大 W 成比例的内存数组）。
                        成功与幂等：200，data=ClosureResultDto（closed=true、closedAt=服务端确认时间 RFC3339 UTC、
                        occupancyReleased=true）。closed_at 非空即释放云台/微晶占用；相同原收尾请求重放不修改 closure manifest、
                        不重复写；状态未知（unknown）拒绝抢占释放。
                        关键规则：收尾不靠客户端一句"已同步"放行；closed 后范围外迟到合法明细仍按原执行补账并记录差异摘要，
                        不重开执行、不回滚 closed_at（K 可继续增加）。
                        错误处理：STOP_NOT_CONFIRMED 先停止并同步观察后重试；CLOSURE_GAPS 按 missingRanges 补齐后重新提交；
                        RECORD_CONFLICT 核对记录流 epoch；EXECUTION_NOT_RESUMABLE（已 closed）不要再重开；AUTH_REQUIRED/
                        SESSION_INVALID；RATE_LIMITED/DEPENDENCY_* 受限退避。
                        契约过声明：CALLER_NOT_ALLOWED 在本端点当前实现中不触发（本端点接受 APP 与云台，非原控制端统一
                        RESOURCE_NOT_VISIBLE）；按契约一致性保留，待总协调裁定。
                        """,
                        List.of(
                                ApiDocEntry.ParamDoc.of("executionId", "path",
                                        "必填，路径参数，UUID 字符串（T07.id），原护理执行引用。",
                                        "22222222-2222-4222-8222-222222222222"),
                                new ApiDocEntry.ParamDoc("Idempotency-Key", "header",
                                        "必填，请求头，字符串 1—128 字符；控制器强制（缺失/空白 → 400 INVALID_INPUT）。"
                                                + "相同原收尾请求同键同内容重放返回同一结果且 meta.replayed=true；生成文档默认 "
                                                + "required=false，此处覆盖为必填。",
                                        "close-20260913-0001", Boolean.TRUE)),
                        List.of(),
                        null,
                        "JSON 请求体（application/json）：ClosureRequestDto（stopObservationSeq、reason、recordStreamEpoch、"
                                + "finalRecordSeq、finalCount）。",
                        List.of(ApiDocEntry.SuccessDoc.json("200",
                                "关闭结果：closed=true、closedAt 为服务端确认时间、occupancyReleased=true",
                                ClosureResultDto.class)),
                        List.of(ErrorCode.INVALID_INPUT, ErrorCode.AUTH_REQUIRED, ErrorCode.SESSION_INVALID,
                                ErrorCode.CALLER_NOT_ALLOWED, ErrorCode.RESOURCE_NOT_VISIBLE,
                                ErrorCode.STOP_NOT_CONFIRMED, ErrorCode.CLOSURE_GAPS, ErrorCode.RECORD_CONFLICT,
                                ErrorCode.EXECUTION_NOT_RESUMABLE, ErrorCode.IDEMPOTENCY_CONTENT_CONFLICT,
                                ErrorCode.REQUEST_IN_PROGRESS, ErrorCode.RATE_LIMITED,
                                ErrorCode.DEPENDENCY_UNAVAILABLE, ErrorCode.DEPENDENCY_TIMEOUT,
                                ErrorCode.NOT_IMPLEMENTED))),

                // ------------------------------------------------------- M4-A07
                Map.entry("GET /api/v1/care-executions/{executionId}", new ApiDocEntry(
                        TAG_EXECUTION,
                        "查询执行及恢复联网后的对账状态",
                        """
                        用途：查询单个护理执行的状态与对账信息，用于断网恢复后核对已确认记录与记录水位。只读：查询/重连不自动开始或恢复执行。
                        调用方：原执行控制端（最小对账投影）或具备该成员查看权的 APP（完整摘要）。
                        权限裁剪：原控制端（APP account+installation 精确一致，或云台 gimbal 一致）即使成员查看关系已撤销也可读，
                        但仅返回最小对账字段（status、acceptedCount、recordWatermark、acknowledgedRecordIds、closedAt）；
                        controller/memberId/planId/microcrystalId/latestObservation/progress 为 null。具备 active 查看权的 APP
                        返回完整摘要（含成员/方案/微晶引用、最新观察与跨执行进度）。
                        参数：recordsAfterSeq 可选（返回该记录序号之后已确认的 clientRecordId 尾部，最多 limit 条）；limit 默认 20、
                        上限 100。
                        字段与枚举：status ∈ admitted|running|paused|unknown|stopped|closed；sourceSeq 从 1 连续递增；观察序号与
                        记录序号是两条独立序列；acceptedCount/maxSourceSeq 为无符号 bigint 十进制字符串；时间字段为 RFC3339 UTC。
                        错误处理：INVALID_INPUT（recordsAfterSeq 非 bigint 或 limit 越界）；AUTH_REQUIRED/SESSION_INVALID；
                        RESOURCE_NOT_VISIBLE 既非原控制端也无查看权（与不存在同响应，不泄露）；RATE_LIMITED/DEPENDENCY_* 受限退避。
                        契约过声明：GRANT_REVOKED、CALLER_NOT_ALLOWED 在本端点当前实现中不触发（本端点接受 APP 与云台，
                        不可见统一 RESOURCE_NOT_VISIBLE）；按契约一致性保留该码，待总协调裁定。
                        """,
                        List.of(
                                ApiDocEntry.ParamDoc.of("executionId", "path",
                                        "必填，路径参数，UUID 字符串（T07.id），执行引用。",
                                        "22222222-2222-4222-8222-222222222222"),
                                ApiDocEntry.ParamDoc.of("recordsAfterSeq", "query",
                                        "可选，查询参数，无符号 bigint 十进制字符串（pattern ^(0|[1-9][0-9]*)$）；对账用——返回该记录"
                                                + "序号之后已确认的 client_record_id 列表尾部；不传则 acknowledgedRecordIds 为 null。",
                                        "0"),
                                ApiDocEntry.ParamDoc.of("limit", "query",
                                        "可选，查询参数，整数；已确认记录 ID 的返回条数上限，默认 20、上限 100。", "20")),
                        List.of(),
                        null,
                        null,
                        List.of(ApiDocEntry.SuccessDoc.json("200",
                                "执行投影（按调用角色裁剪）：完整摘要或原控制端最小对账视图",
                                CareExecutionView.class)),
                        List.of(ErrorCode.INVALID_INPUT, ErrorCode.AUTH_REQUIRED, ErrorCode.SESSION_INVALID,
                                ErrorCode.CALLER_NOT_ALLOWED, ErrorCode.RESOURCE_NOT_VISIBLE,
                                ErrorCode.GRANT_REVOKED, ErrorCode.RATE_LIMITED,
                                ErrorCode.DEPENDENCY_UNAVAILABLE, ErrorCode.DEPENDENCY_TIMEOUT,
                                ErrorCode.NOT_IMPLEMENTED))),

                // ------------------------------------------------------- M4-A08
                Map.entry("GET /api/v1/care-plans/{planId}/progress", new ApiDocEntry(
                        TAG_PLAN,
                        "查询方案累计进度",
                        """
                        用途：查询方案累计进度 N/K/剩余/达标状态与最后同步信息；查询本身不增加 K、不改变执行状态。
                        调用方：已授权 APP；或具备当前已核验执行上下文的云台（gimbal token + query executionId +
                        verificationRevision）。
                        前置：APP 须对该成员有 active 授权，且方案 generation_status=ready（否则 409 PLAN_NOT_READY）；
                        云台须同时满足：executionId 属于本云台且指向该 planId、verificationRevision 等于执行当前代次、
                        执行生命周期为 admitted/running/paused 且未标记连续性失效、方案属于云台当前测肤任务指针
                        （指针不匹配 409 TASK_REPLACED）；任一不满足云台侧统一 404 RESOURCE_NOT_VISIBLE（过期/不适用核验不开放）。
                        关键规则与口径：N=targetCount（单位：次）、K=completedCount（去重累计、不截断为 N）、
                        剩余=max(N-K,0)、isCompleted=K>=N；后端持久保存 K，重启/换绑不清零；离线未同步量不伪装成已知数据；
                        不按会话数/下载数计数；lastSyncedAt 仅在 progressRevision>0 时返回，取自业务更新时间。
                        字段：所有计数/代次为无符号 bigint 十进制字符串；completedAt 为服务端首次达标确认时间（RFC3339 UTC，
                        未达标为 null）；progressRevision 默认 0。
                        错误处理：INVALID_INPUT（云台缺 executionId/verificationRevision 或非 UUID/bigint）；
                        PLAN_NOT_READY 轮询等待；TASK_REPLACED 以当前任务为准；AUTH_REQUIRED/SESSION_INVALID；
                        RESOURCE_NOT_VISIBLE 不要换 ID 探测；RATE_LIMITED/DEPENDENCY_* 受限退避。
                        契约过声明：GRANT_REVOKED、CALLER_NOT_ALLOWED 在本端点当前实现中不触发（本端点接受 APP 与具备
                        核验上下文的云台，不可见统一 RESOURCE_NOT_VISIBLE）；按契约一致性保留，待总协调裁定。
                        """,
                        List.of(
                                ApiDocEntry.ParamDoc.of("planId", "path",
                                        "必填，路径参数，UUID 字符串（T06.id），方案引用。",
                                        "33333333-3333-4333-8333-333333333333"),
                                ApiDocEntry.ParamDoc.of("executionId", "query",
                                        "可选，查询参数，UUID 字符串；云台调用者必填——当前已核验执行上下文（须属于本云台且指向该方案）；"
                                                + "APP 调用者传入被忽略。",
                                        "22222222-2222-4222-8222-222222222222"),
                                ApiDocEntry.ParamDoc.of("verificationRevision", "query",
                                        "可选，查询参数，无符号 bigint 十进制字符串；云台调用者必填——本轮核验代次，须等于执行当前 "
                                                + "verificationRevision，否则 404（过期核验不开放）；APP 传入被忽略。",
                                        "1")),
                        List.of(),
                        null,
                        null,
                        List.of(ApiDocEntry.SuccessDoc.json("200",
                                "Progress + lastSyncedAt（N、已同步 K、剩余 max(N-K,0)、完成 K>=N、最后同步信息）",
                                ProgressWithSync.class)),
                        List.of(ErrorCode.INVALID_INPUT, ErrorCode.AUTH_REQUIRED, ErrorCode.SESSION_INVALID,
                                ErrorCode.CALLER_NOT_ALLOWED, ErrorCode.RESOURCE_NOT_VISIBLE,
                                ErrorCode.PLAN_NOT_READY, ErrorCode.TASK_REPLACED, ErrorCode.GRANT_REVOKED,
                                ErrorCode.RATE_LIMITED, ErrorCode.DEPENDENCY_UNAVAILABLE,
                                ErrorCode.DEPENDENCY_TIMEOUT, ErrorCode.NOT_IMPLEMENTED))),

                // ------------------------------------------------------- M4-A09
                Map.entry("GET /api/v1/members/{memberId}/care-executions", new ApiDocEntry(
                        TAG_LEDGER,
                        "查看本人护理执行历史",
                        """
                        用途：列出指定成员（本人）的护理执行历史及有效完成摘要；执行结束与方案达标分别表达。
                        调用方：仅 APP（APP session token）。
                        前置：当前账号对该 memberId 有 active 授权（否则 404 RESOURCE_NOT_VISIBLE）。
                        筛选与分页：planId 可选（不限则返回该成员全部方案）；from/to 为 RFC3339 UTC 创建时间范围筛选
                        （仅筛选/诊断用途）；limit 默认 20、上限 100；cursor 为 keyset 不透明游标，绑定 planId+from+to 筛选摘要，
                        非法或筛选不符 → 400 INVALID_INPUT。
                        关键规则：不混用不同成员/方案的记录；历史内容取执行时冻结快照（T07.plan_snapshot.summary），
                        不按每行回查方案；planSnapshotSummary 仅为 SUMMARY 白名单投影（title/description/source_report_id/
                        source_report_ready_at，schema_version 不外发）。
                        字段：executionId 等为 UUID；status ∈ admitted|running|paused|unknown|stopped|closed；
                        acceptedCount 为无符号 bigint 十进制字符串；createdAt/closedAt 为 RFC3339 UTC（closedAt 未关闭为 null）。
                        错误处理：INVALID_INPUT（时间格式/游标/limit）；AUTH_REQUIRED/SESSION_INVALID；CALLER_NOT_ALLOWED（云台）；
                        RESOURCE_NOT_VISIBLE；RATE_LIMITED/DEPENDENCY_* 受限退避。
                        契约过声明：GRANT_REVOKED 在本端点当前实现中不触发（实现统一用 RESOURCE_NOT_VISIBLE 表达不可见/已撤销）；
                        按契约一致性保留该码，待总协调裁定。
                        """,
                        List.of(
                                ApiDocEntry.ParamDoc.of("memberId", "path",
                                        "必填，路径参数，UUID 字符串（T01.id），成员引用。",
                                        "11111111-1111-4111-8111-111111111111"),
                                ApiDocEntry.ParamDoc.of("planId", "query",
                                        "可选，查询参数，UUID 字符串（T06.id）；按方案筛选，缺省返回该成员全部方案的执行。",
                                        "33333333-3333-4333-8333-333333333333"),
                                ApiDocEntry.ParamDoc.of("from", "query",
                                        "可选，查询参数，RFC3339 UTC 时间（如 2026-09-01T00:00:00Z）；创建时间筛选起点。",
                                        "2026-09-01T00:00:00Z"),
                                ApiDocEntry.ParamDoc.of("to", "query",
                                        "可选，查询参数，RFC3339 UTC 时间；创建时间筛选终点。",
                                        "2026-09-13T00:00:00Z"),
                                ApiDocEntry.ParamDoc.of("limit", "query",
                                        "可选，查询参数，整数；分页大小，默认 20、上限 100、最小 1；不返回总数。", "20"),
                                ApiDocEntry.ParamDoc.of("cursor", "query",
                                        "可选，查询参数，字符串；keyset 不透明游标（绑定排序值+ID+planId/from/to 筛选摘要），"
                                                + "原样回传；非法或不匹配 → 400 INVALID_INPUT；缺省表示第一页。")),
                        List.of(),
                        null,
                        null,
                        List.of(ApiDocEntry.SuccessDoc.jsonList("200",
                                "执行历史列表页；data={items:[CareExecutionListItem], nextCursor:string|null}，"
                                        + "nextCursor 为 null 表示无后续页",
                                CareExecutionListItem.class)),
                        List.of(ErrorCode.INVALID_INPUT, ErrorCode.AUTH_REQUIRED, ErrorCode.SESSION_INVALID,
                                ErrorCode.CALLER_NOT_ALLOWED, ErrorCode.RESOURCE_NOT_VISIBLE,
                                ErrorCode.GRANT_REVOKED, ErrorCode.RATE_LIMITED,
                                ErrorCode.DEPENDENCY_UNAVAILABLE, ErrorCode.DEPENDENCY_TIMEOUT,
                                ErrorCode.NOT_IMPLEMENTED)))
        );
    }

    @Override
    public Map<String, Map<String, PropertyDoc>> propertyDocs() {
        return Map.ofEntries(

                Map.entry("CaptureDto", Map.of(
                        "captureId", PropertyDoc.of(
                                "必填，字符串，≤128；客户端稳定采集标识，绑定本轮核验。", "capture-adm-0001"),
                        "capturedAt", new PropertyDoc(
                                "必填，字符串，RFC3339 UTC 采集时间（客户端提交，仅用于核验关联/去重，不单独证明新鲜性）。",
                                null, null, "2026-09-13T08:00:00Z", "date-time"),
                        "clientContinuityId", PropertyDoc.of(
                                "必填，字符串，≤128；客户端连续性标识，绑定本轮控制端上下文。", "cc-0001"),
                        "purpose", PropertyDoc.enumOf(
                                "必填，字符串，采集用途；本域仅 admission（M4-A03）或 revalidation（M4-A04）。",
                                List.of("admission", "revalidation"), "admission"),
                        "captureProofRef", PropertyDoc.of(
                                "可选，可空字符串；采集证明引用（服务端可验证的活体/采集凭据协议未冻结，当前可为 null）。"))),

                Map.entry("M4A03Metadata", Map.of(
                        "microcrystalId", PropertyDoc.of(
                                "必填，字符串，UUID（T04.id），本次执行的微晶引用。",
                                "66666666-6666-4666-8666-666666666666"),
                        "connectionProof", PropertyDoc.of(
                                "必填，字符串；微晶/控制端当前连接证明，绑定控制端+微晶+当前连接；格式未冻结"
                                        + "（须来自已验证微晶协议）。", "connection-proof-placeholder"),
                        "capture", PropertyDoc.of(
                                "必填，对象（CaptureDto）；本轮采集与核验关联，capture.purpose 必须为 admission。"),
                        "consentEvidenceRef", PropertyDoc.of(
                                "必填，字符串，1—128；用户同意证据引用。", "consent-placeholder-0001"),
                        "planId", PropertyDoc.of(
                                "APP 调用者必填、可空字符串，UUID（T06.id）；云台调用者必须不提供（云台方案由 currentTaskId 确定）。",
                                "33333333-3333-4333-8333-333333333333"),
                        "currentTaskId", PropertyDoc.of(
                                "云台调用者必填、可空字符串，UUID（T05.id）；APP 调用者必须不提供。",
                                "77777777-7777-4777-8777-777777777777"),
                        "currentAssessmentRevision", PropertyDoc.of(
                                "云台调用者必填、可空字符串；无符号 bigint 十进制字符串，须与云台 current_assessment 指针代次"
                                        + "精确一致，否则 409 TASK_REPLACED。", "1"))),

                Map.entry("M4A04Metadata", Map.of(
                        "expectedVerificationRevision", PropertyDoc.of(
                                "必填，字符串，无符号 bigint 十进制字符串；须等于执行当前 verificationRevision，"
                                        + "否则 409 EXECUTION_NOT_RESUMABLE（reason=verification_revision_mismatch）。", "1"),
                        "capture", PropertyDoc.of(
                                "必填，对象（CaptureDto）；本轮恢复核验关联，capture.purpose 必须为 revalidation。"),
                        "consentEvidenceRef", PropertyDoc.of(
                                "必填，字符串，1—128；本轮恢复确认的用户同意证据引用。", "consent-placeholder-0002"),
                        "reportedMicrocrystalState", PropertyDoc.of(
                                "可选，可空对象；客户端上报的微晶实际状态，必须为 JSON 对象或 null（否则 400 INVALID_INPUT）；"
                                        + "结构未冻结，见该字段自由结构展开；不构成放行依据。"))),

                Map.entry("VerificationDto", Map.of(
                        "verificationRevision", PropertyDoc.of(
                                "字符串，无符号 bigint 十进制字符串；首次准入为 \"1\"，每次重新核验 +1。", "1"),
                        "captureId", PropertyDoc.of(
                                "字符串，本轮核验绑定的采集标识。", "capture-adm-0001"),
                        "clientContinuityId", PropertyDoc.of(
                                "字符串，本轮核验绑定的客户端连续性标识。", "cc-0001"),
                        "verifiedAt", new PropertyDoc(
                                "字符串，本轮核验时间，RFC3339 UTC。",
                                null, null, "2026-09-13T08:00:00Z", "date-time"),
                        "validUntil", new PropertyDoc(
                                "可空字符串，本轮核验可用于端侧首次启动/恢复的时间边界，RFC3339 UTC；当前实现恒为 null"
                                        + "（未冻结/未实现，依据 DD 6.2 与源码 buildLatestVerification 写 null）。"
                                        + "时间未到也不能无视换人——端侧连续性失效立即作废。",
                                null, null, null, "date-time"),
                        "applicablePurpose", PropertyDoc.enumOf(
                                "字符串，本轮核验适用用途；本域取 admission|revalidation（契约通用枚举另含 grant/assessment，"
                                        + "非本域产生）。",
                                List.of("admission", "revalidation"), "admission"),
                        "replayed", PropertyDoc.of(
                                "布尔，是否为幂等重放响应；true 表示未重做写入，重放不获得新的启动/恢复有效性。", "false"))),

                Map.entry("CareExecutionAdmission", Map.of(
                        "executionId", PropertyDoc.of(
                                "字符串，UUID（T07.id），本次登记的护理执行引用。",
                                "22222222-2222-4222-8222-222222222222"),
                        "status", PropertyDoc.enumOf(
                                "字符串，登记结果；固定为 admitted，对外译为\"已登记，待端侧确认\"，不表示硬件已运行。",
                                List.of("admitted"), "admitted"),
                        "controller", PropertyDoc.of(
                                "对象（ControllerRef），服务端确定的固定控制端。"),
                        "memberId", PropertyDoc.of(
                                "可空字符串，UUID（T01.id），已核验成员关联；仅本人会话可见。",
                                "11111111-1111-4111-8111-111111111111"),
                        "planId", PropertyDoc.of(
                                "可空字符串，UUID（T06.id），本次执行使用的方案。",
                                "33333333-3333-4333-8333-333333333333"),
                        "planExecution", PropertyDoc.of(
                                "可空对象，方案执行简版（EXECUTION 白名单：仅 steps/regions/parameters）；结构未冻结，"
                                        + "见该字段自由结构展开；schema_version 绝不外发。"),
                        "progress", PropertyDoc.of(
                                "对象（Progress），目标次数 N、已同步 K、剩余、达标。"),
                        "verification", PropertyDoc.of(
                                "对象（VerificationDto），本次准入核验。"),
                        "recordStreamEpoch", PropertyDoc.of(
                                "可空字符串，记录流 epoch，由后端以 executionId 派生并返回（当前实现等于 executionId）。",
                                "22222222-2222-4222-8222-222222222222"))),

                Map.entry("CareExecutionRevalidation", Map.of(
                        "executionId", PropertyDoc.of(
                                "字符串，UUID（T07.id），原护理执行引用。",
                                "22222222-2222-4222-8222-222222222222"),
                        "status", PropertyDoc.enumOf(
                                "字符串，当前执行状态；重新核验成功仍为 paused，不自动变 running。",
                                List.of("admitted", "running", "paused", "unknown", "stopped", "closed"),
                                "paused"),
                        "planId", PropertyDoc.of(
                                "可空字符串，UUID（T06.id），沿用原方案。",
                                "33333333-3333-4333-8333-333333333333"),
                        "planExecution", PropertyDoc.of(
                                "可空对象，沿用原方案的执行简版（EXECUTION 白名单：仅 steps/regions/parameters）；结构未冻结。"),
                        "progress", PropertyDoc.of(
                                "对象（Progress），保留的原方案进度。"),
                        "verification", PropertyDoc.of(
                                "对象（VerificationDto），本轮恢复核验（verificationRevision 已 +1）。"))),

                Map.entry("Progress", Map.of(
                        "targetCount", PropertyDoc.of(
                                "字符串，目标次数 N，无符号 bigint 十进制字符串；方案 ready 时必填且 >0，未 ready 可为 null。", "10"),
                        "completedCount", PropertyDoc.of(
                                "字符串，后端已同步（去重累计）次数 K，无符号 bigint 十进制字符串；不截断为 N。", "3"),
                        "remainingCount", PropertyDoc.of(
                                "字符串，剩余次数 max(N-K,0)，无符号 bigint 十进制字符串。", "7"),
                        "isCompleted", PropertyDoc.of(
                                "布尔，达标状态 K>=N；targetCount 为 null 时为 null（不用 false/0 表示已完成）。", "false"),
                        "progressRevision", PropertyDoc.of(
                                "字符串，进度代次，无符号 bigint 十进制字符串；默认 0，仅在实际新增记录入账时 +1。", "2"),
                        "completedAt", new PropertyDoc(
                                "可空字符串，服务端首次确认达标的完成时间，RFC3339 UTC；未达标为 null。",
                                null, null, null, "date-time"))),

                Map.entry("ProgressWithSync", Map.of(
                        "targetCount", PropertyDoc.of(
                                "字符串，目标次数 N，无符号 bigint 十进制字符串；方案 ready 时必填且 >0。", "10"),
                        "completedCount", PropertyDoc.of(
                                "字符串，后端已同步（去重累计）次数 K，无符号 bigint 十进制字符串；不截断为 N。", "3"),
                        "remainingCount", PropertyDoc.of(
                                "字符串，剩余次数 max(N-K,0)，无符号 bigint 十进制字符串。", "7"),
                        "isCompleted", PropertyDoc.of(
                                "布尔，达标状态 K>=N。", "false"),
                        "progressRevision", PropertyDoc.of(
                                "字符串，进度代次，无符号 bigint 十进制字符串；默认 0。", "2"),
                        "completedAt", new PropertyDoc(
                                "可空字符串，服务端首次确认达标的完成时间，RFC3339 UTC；未达标为 null。",
                                null, null, null, "date-time"),
                        "lastSyncedAt", new PropertyDoc(
                                "可空字符串，最后同步时间，RFC3339 UTC；仅 progressRevision>0 时返回，否则为 null。",
                                null, null, "2026-09-13T08:05:00Z", "date-time"))),

                Map.entry("ExecutionObservation", Map.of(
                        "epoch", PropertyDoc.of(
                                "字符串，≤128，执行记录/观察流 epoch，由后端以 executionId 派生。",
                                "22222222-2222-4222-8222-222222222222"),
                        "seq", PropertyDoc.of(
                                "字符串，已接受观察序号，无符号 bigint 十进制字符串（观察序列，与记录序号独立）。", "12"),
                        "state", PropertyDoc.enumOf(
                                "字符串，已知实际状态。",
                                List.of("running", "paused", "unknown", "stopped"), "paused"),
                        "occurredAt", new PropertyDoc(
                                "字符串，观察发生时间，RFC3339 UTC。",
                                null, null, "2026-09-13T08:05:00Z", "date-time"),
                        "verificationRevision", PropertyDoc.of(
                                "可空字符串，观察对应的核验代次，无符号 bigint 十进制字符串。", "1"),
                        "continuityValid", PropertyDoc.of(
                                "可空布尔，该观察时客户端使用者连续性是否成立；false 表示需重新核验。", "true"))),

                Map.entry("ExecutionObservationDto", Map.of(
                        "epoch", PropertyDoc.of(
                                "必填，字符串，≤128，客户端上报的观察流 epoch；须与执行记录流 epoch 一致，"
                                        + "否则 409 RECORD_CONFLICT（reason=observation_epoch_mismatch）。",
                                "22222222-2222-4222-8222-222222222222"),
                        "seq", PropertyDoc.of(
                                "必填，字符串，观察序号，无符号 bigint 十进制字符串；同 epoch 内严格递增"
                                        + "（大于已接受序号才更新状态，同序号异内容冲突）。", "12"),
                        "state", PropertyDoc.enumOf(
                                "必填，字符串，上报的实际状态；枚举越界 400 INVALID_INPUT。",
                                List.of("running", "paused", "unknown", "stopped"), "paused"),
                        "occurredAt", new PropertyDoc(
                                "必填，字符串，观察发生时间，RFC3339 UTC。",
                                null, null, "2026-09-13T08:05:00Z", "date-time"),
                        "verificationRevision", PropertyDoc.of(
                                "可选，可空字符串，观察对应的核验代次，无符号 bigint 十进制字符串。", "1"),
                        "continuityValid", PropertyDoc.of(
                                "可选，可空布尔，客户端使用者连续性是否成立。", "false"))),

                Map.entry("ExecutionRecordDto", Map.of(
                        "recordId", PropertyDoc.of(
                                "必填，字符串，≤128；客户端稳定去重标识（T08 唯一键 (execution_id, client_record_id)）。",
                                "rec-0001"),
                        "sourceEpoch", PropertyDoc.of(
                                "必填，字符串，≤128；记录流 epoch，须与执行流一致。",
                                "22222222-2222-4222-8222-222222222222"),
                        "sourceSeq", PropertyDoc.of(
                                "必填，字符串，记录序号，无符号 bigint 十进制字符串；同一 epoch 内从 1 连续递增、不重叠。", "3"),
                        "countDelta", PropertyDoc.of(
                                "必填，字符串，本次实际新增次数增量，无符号 bigint 十进制字符串且必须 >0。", "1"),
                        "occurredAt", new PropertyDoc(
                                "必填，字符串，记录发生时间，RFC3339 UTC。",
                                null, null, "2026-09-13T08:04:50Z", "date-time"))),

                Map.entry("SyncRequestDto", Map.of(
                        "observation", PropertyDoc.of(
                                "可选，可空对象（ExecutionObservationDto）；新一轮实际状态观察。"),
                        "records", PropertyDoc.of(
                                "必填，数组，元素为 ExecutionRecordDto，批次上限 200（maxItems=200）；可为空数组。",
                                "[{\"recordId\":\"rec-0001\",\"sourceEpoch\":\"22222222-2222-4222-8222-222222222222\","
                                        + "\"sourceSeq\":\"3\",\"countDelta\":\"1\","
                                        + "\"occurredAt\":\"2026-09-13T08:04:50Z\"}]"))),

                Map.entry("AcknowledgedRecordDto", Map.of(
                        "recordId", PropertyDoc.of(
                                "字符串，本次批次中的客户端记录标识。", "rec-0001"),
                        "disposition", PropertyDoc.enumOf(
                                "字符串，逐记录处置结果。",
                                List.of("accepted", "duplicate", "rejected"), "accepted"),
                        "rejectReason", PropertyDoc.of(
                                "可空字符串，拒绝原因（仅调用方可见，结构未冻结）。"))),

                Map.entry("ObservationAckDto", Map.of(
                        "acknowledgedRecords", PropertyDoc.of(
                                "数组，逐记录处置结果（仅在提交成功后生成；事务失败不确认任何新增记录）。"),
                        "executionStatus", PropertyDoc.enumOf(
                                "字符串，同步后的执行已知状态。",
                                List.of("admitted", "running", "paused", "unknown", "stopped", "closed"),
                                "paused"),
                        "acceptedCount", PropertyDoc.of(
                                "字符串，后端去重累计次数 K，无符号 bigint 十进制字符串。", "1"),
                        "progress", PropertyDoc.of(
                                "可空对象（Progress）；仅具备读取权限时附带。"))),

                Map.entry("ClosureRequestDto", Map.of(
                        "stopObservationSeq", PropertyDoc.of(
                                "必填，字符串，无符号 bigint 十进制字符串；客户端上报的微晶已停止观察序号，须与后端最后已接收的 "
                                        + "stopped 观察一致，否则 409 STOP_NOT_CONFIRMED。", "15"),
                        "reason", PropertyDoc.of(
                                "必填，字符串，结束原因；枚举未冻结（契约示例 user_finished）。", "user_finished"),
                        "recordStreamEpoch", PropertyDoc.of(
                                "必填，字符串，≤128；本执行记录流 epoch，须与后端一致，否则 409 RECORD_CONFLICT。",
                                "22222222-2222-4222-8222-222222222222"),
                        "finalRecordSeq", PropertyDoc.of(
                                "必填，字符串，承诺记录流范围 1..W 的 W，无符号 bigint 十进制字符串；W=0 时要求无记录。", "3"),
                        "finalCount", PropertyDoc.of(
                                "必填，字符串，承诺范围内增量总和，无符号 bigint 十进制字符串；须等于 SUM(count_delta)。", "3"))),

                Map.entry("ClosureResultDto", Map.of(
                        "closed", PropertyDoc.of(
                                "布尔，是否已关闭（closed_at 已写入）。", "true"),
                        "closedAt", new PropertyDoc(
                                "可空字符串，服务端关闭确认时间，RFC3339 UTC；closed=true 时非空。closed_at 非空才释放占用。",
                                null, null, "2026-09-13T08:30:00Z", "date-time"),
                        "occupancyReleased", PropertyDoc.of(
                                "布尔，云台/微晶占用是否已释放（closed=true 时为 true）。", "true"))),

                Map.entry("ControllerRef", Map.of(
                        "controllerType", PropertyDoc.enumOf(
                                "字符串，固定控制端类型；与 T13 principal_type 一致。",
                                List.of("app_account", "gimbal"), "app_account"),
                        "installationId", PropertyDoc.of(
                                "可空字符串，APP 控制端的安装实例 ID（controllerType=app_account 时返回）。",
                                "install-0000-0000-0000-000000000001"),
                        "gimbalId", PropertyDoc.of(
                                "可空字符串，UUID；云台控制端（controllerType=gimbal 时返回）。",
                                "88888888-8888-4888-8888-888888888888"))),

                Map.entry("RecordWatermark", Map.of(
                        "epoch", PropertyDoc.of(
                                "字符串，记录流 epoch。",
                                "22222222-2222-4222-8222-222222222222"),
                        "maxSourceSeq", PropertyDoc.of(
                                "字符串，该流已接受的最大记录序号，无符号 bigint 十进制字符串；无记录为 \"0\"。", "1"),
                        "acceptedCount", PropertyDoc.of(
                                "字符串，该流已接受记录的总增量（次数），无符号 bigint 十进制字符串。", "1"))),

                Map.entry("CarePlanListItem", Map.of(
                        "planId", PropertyDoc.of(
                                "字符串，UUID（T06.id），方案引用。",
                                "33333333-3333-4333-8333-333333333333"),
                        "generationStatus", PropertyDoc.enumOf(
                                "字符串，方案生成状态。",
                                List.of("waiting_inputs", "generating", "ready", "failed"), "ready"),
                        "planSummary", PropertyDoc.of(
                                "可空对象，方案摘要封闭白名单投影（仅 title/description/source_report_id/source_report_ready_at）；"
                                        + "schema_version 绝不外发；结构未冻结，见该字段自由结构展开。"),
                        "progress", PropertyDoc.of(
                                "可空对象（Progress）；仅 generationStatus=ready 时非空。"))),

                Map.entry("CarePlanFullView", Map.of(
                        "planId", PropertyDoc.of(
                                "字符串，UUID（T06.id），方案引用。",
                                "33333333-3333-4333-8333-333333333333"),
                        "generationStatus", PropertyDoc.enumOf(
                                "字符串，方案生成状态。",
                                List.of("waiting_inputs", "generating", "ready", "failed"), "ready"),
                        "plan", PropertyDoc.of(
                                "可空对象，方案正文封闭白名单投影（仅 title/description/steps/regions/parameters）；仅 ready 时非空；"
                                        + "schema_version 绝不外发；禁止返回供应商原始响应/提示词；结构未冻结，见该字段自由结构展开。"),
                        "progress", PropertyDoc.of(
                                "可空对象（Progress）；仅 ready 时非空。"),
                        "waitingReason", PropertyDoc.of(
                                "可空字符串，未就绪公开原因；waiting_inputs|generating|generation_failed，其他为 null。",
                                "waiting_inputs"))),

                Map.entry("CareExecutionListItem", Map.of(
                        "executionId", PropertyDoc.of(
                                "字符串，UUID（T07.id），执行引用。",
                                "22222222-2222-4222-8222-222222222222"),
                        "status", PropertyDoc.enumOf(
                                "字符串，执行状态；admitted 对外译为\"已登记，待端侧确认\"。",
                                List.of("admitted", "running", "paused", "unknown", "stopped", "closed"),
                                "closed"),
                        "createdAt", new PropertyDoc(
                                "字符串，执行登记时间，RFC3339 UTC。",
                                null, null, "2026-09-13T08:00:00Z", "date-time"),
                        "closedAt", new PropertyDoc(
                                "可空字符串，收尾关闭时间，RFC3339 UTC；未关闭为 null。",
                                null, null, null, "date-time"),
                        "acceptedCount", PropertyDoc.of(
                                "字符串，该执行已接受（去重累计）次数，无符号 bigint 十进制字符串。", "3"),
                        "planSnapshotSummary", PropertyDoc.of(
                                "可空对象，执行时冻结快照的方案摘要封闭白名单投影（SUMMARY）；schema_version 绝不外发；"
                                        + "结构未冻结，见该字段自由结构展开。"))),

                Map.entry("CareExecutionView", Map.ofEntries(
                        Map.entry("executionId", PropertyDoc.of(
                                "字符串，UUID（T07.id），执行引用。",
                                "22222222-2222-4222-8222-222222222222")),
                        Map.entry("status", PropertyDoc.enumOf(
                                "字符串，执行状态。",
                                List.of("admitted", "running", "paused", "unknown", "stopped", "closed"),
                                "closed")),
                        Map.entry("controller", PropertyDoc.of(
                                "可空对象（ControllerRef）；仅完整摘要（具查看权 APP）返回，原控制端最小投影为 null。")),
                        Map.entry("memberId", PropertyDoc.of(
                                "可空字符串，UUID（T01.id）；仅具成员查看权时返回。",
                                "11111111-1111-4111-8111-111111111111")),
                        Map.entry("planId", PropertyDoc.of(
                                "可空字符串，UUID（T06.id）；仅具成员查看权时返回。",
                                "33333333-3333-4333-8333-333333333333")),
                        Map.entry("microcrystalId", PropertyDoc.of(
                                "可空字符串，UUID（T04.id）；仅完整摘要返回。",
                                "66666666-6666-4666-8666-666666666666")),
                        Map.entry("acceptedCount", PropertyDoc.of(
                                "字符串，该执行已接受（去重累计）次数，无符号 bigint 十进制字符串。", "1")),
                        Map.entry("latestObservation", PropertyDoc.of(
                                "可空对象（ExecutionObservation）；已知实际状态及新鲜度，原控制端最小投影为 null。")),
                        Map.entry("recordWatermark", PropertyDoc.of(
                                "可空对象（RecordWatermark），记录流水位（epoch + 已接受最大序号 + 已接受计数）。")),
                        Map.entry("acknowledgedRecordIds", PropertyDoc.of(
                                "可空数组，字符串数组；recordsAfterSeq 之后已确认的 clientRecordId 尾部（≤limit），"
                                        + "未传 recordsAfterSeq 时为 null；客户端只清理已确认部分。")),
                        Map.entry("closedAt", new PropertyDoc(
                                "可空字符串，收尾关闭时间，RFC3339 UTC；未关闭为 null。",
                                null, null, null, "date-time")),
                        Map.entry("progress", PropertyDoc.of(
                                "可空对象（Progress）；仅具查看权时返回跨执行总进度，原控制端最小投影为 null。"))))
        );
    }

    @Override
    public Map<String, FreeFormDoc> freeFormDocs() {
        return Map.ofEntries(

                Map.entry("CarePlanListItem.planSummary", new FreeFormDoc(
                        """
                        用途：M4-A01 列表项的方案摘要；写入方为后端（CarePlanProjection.summary 对 T06.plan_summary 做
                        递归白名单投影）。不含内部 schema_version；未知键、类型不符值、供应商原始响应/提示词一律丢弃
                        （仅 WARN 记录键路径，绝不记录值）。未就绪方案该字段为 null。
                        """,
                        Map.of(
                                "title", "string，方案标题（取自经批准的统一方案摘要）",
                                "description", "string，方案说明",
                                "source_report_id", "string，来源统一报告 ID（T05.report_id）",
                                "source_report_ready_at", "string，来源报告就绪时间（RFC3339 UTC）"),
                        false,
                        "封闭白名单（additionalProperties=false）：服务端只放行上述四键，未知键会被投影丢弃；"
                                + "该白名单为 C 侧保守提案，待总协调/D 契约确认后冻结。",
                        "{\"title\":\"示例方案\",\"description\":\"示例说明\","
                                + "\"source_report_id\":\"44444444-4444-4444-8444-444444444444\","
                                + "\"source_report_ready_at\":\"2026-09-13T07:30:00Z\"}")),

                Map.entry("CarePlanFullView.plan", new FreeFormDoc(
                        """
                        用途：M4-A02 方案完整版的方案正文；写入方为后端（CarePlanProjection.full 对 T06.plan_payload 做
                        递归白名单投影）。不含内部 schema_version；供应商原始响应/提示词、内部凭据绝不外发。未就绪为 null。
                        steps 每元素仅 {region, parameters}；parameter 定义可为标量，或仅保留 {value, unit}；regions 仅 string。
                        """,
                        Map.of(
                                "title", "string，方案标题",
                                "description", "string，方案说明",
                                "steps", "array，护理步骤数组；每元素仅为对象 {region(string), parameters(object)}，过滤后为空的步骤被丢弃",
                                "regions", "array，允许的护理区域字符串数组（仅保留 string 元素）",
                                "parameters", "object，参数名 → 参数定义；参数定义可为标量，或仅保留 {value(标量), unit(string)}"),
                        false,
                        "封闭白名单（additionalProperties=false）：服务端只放行 title/description/steps/regions/parameters；"
                                + "未知键、类型不符值、供应商原始响应/提示词与内部版本标记 schema_version 一律丢弃。"
                                + "步骤/参数/区域及微晶参数名、单位、范围尚未在契约冻结，属于 C 侧保守提案，待总协调/D 确认后冻结。",
                        "{\"title\":\"示例方案\",\"description\":\"示例说明\","
                                + "\"steps\":[{\"region\":\"face\",\"parameters\":{\"intensity\":{\"value\":\"3\",\"unit\":\"level\"}}}],"
                                + "\"regions\":[\"face\"],\"parameters\":{\"intensity\":{\"value\":\"3\",\"unit\":\"level\"}}}")),

                Map.entry("CareExecutionListItem.planSnapshotSummary", new FreeFormDoc(
                        """
                        用途：M4-A09 执行历史列表项的方案摘要（取自执行时冻结快照 T07.plan_snapshot.summary）；
                        写入方为后端（CarePlanProjection.summaryFromSnapshot，对快照 summary 子对象做递归白名单投影）。
                        不含内部 schema_version；未知键与供应商原文一律丢弃；快照缺失/空对象时为 null。
                        """,
                        Map.of(
                                "title", "string，方案标题",
                                "description", "string，方案说明",
                                "source_report_id", "string，来源统一报告 ID（T05.report_id）",
                                "source_report_ready_at", "string，来源报告就绪时间（RFC3339 UTC）"),
                        false,
                        "封闭白名单（additionalProperties=false）：服务端只放行上述四键；白名单为 C 侧保守提案，"
                                + "待总协调/D 契约确认后冻结。",
                        "{\"title\":\"示例方案\",\"description\":\"示例说明\","
                                + "\"source_report_id\":\"44444444-4444-4444-8444-444444444444\","
                                + "\"source_report_ready_at\":\"2026-09-13T07:30:00Z\"}")),

                Map.entry("CareExecutionAdmission.planExecution", new FreeFormDoc(
                        """
                        用途：M4-A03 登记成功后返回的方案执行简版；写入方为后端（CarePlanProjection.execution 对
                        T06.plan_payload 做递归白名单投影）。仅含执行必需步骤/区域/参数，不含内部 schema_version，
                        不含历史列表或无关成员资料。未就绪/空投影时为 null。
                        """,
                        Map.of(
                                "steps", "array，执行步骤数组；每元素仅为对象 {region(string), parameters(object)}",
                                "regions", "array，允许区域字符串数组（仅 string 元素）",
                                "parameters", "object，参数名 → 参数定义；可为标量或 {value(标量), unit(string)}"),
                        false,
                        "封闭白名单（additionalProperties=false）：服务端只放行 steps/regions/parameters；"
                                + "微晶参数名、单位、范围尚未在契约冻结，须来自已验证微晶协议，属 C 侧保守提案，"
                                + "待总协调/D 确认后冻结。",
                        "{\"steps\":[{\"region\":\"face\",\"parameters\":{\"intensity\":\"3\"}}],"
                                + "\"regions\":[\"face\"],\"parameters\":{\"intensity\":\"3\"}}")),

                Map.entry("CareExecutionRevalidation.planExecution", new FreeFormDoc(
                        """
                        用途：M4-A04 重新核验成功后返回的沿用方案执行简版；写入方为后端（CarePlanProjection.execution 对
                        原方案 plan_payload 做递归白名单投影）。不含内部 schema_version；未知键与供应商原文一律丢弃。
                        """,
                        Map.of(
                                "steps", "array，执行步骤数组；每元素仅为对象 {region(string), parameters(object)}",
                                "regions", "array，允许区域字符串数组（仅 string 元素）",
                                "parameters", "object，参数名 → 参数定义；可为标量或 {value(标量), unit(string)}"),
                        false,
                        "封闭白名单（additionalProperties=false）：服务端只放行 steps/regions/parameters；"
                                + "微晶参数名、单位、范围尚未在契约冻结，属 C 侧保守提案，待总协调/D 确认后冻结。",
                        "{\"steps\":[{\"region\":\"face\",\"parameters\":{\"intensity\":\"3\"}}],"
                                + "\"regions\":[\"face\"],\"parameters\":{\"intensity\":\"3\"}}")),

                Map.entry("M4A04Metadata.reportedMicrocrystalState", new FreeFormDoc(
                        """
                        用途：M4-A04 重新核验时客户端上报的微晶实际状态，写入方为 APP/云台控制端。
                        必须为 JSON 对象或 null（否则 400 INVALID_INPUT），并参与本轮 T13 幂等载荷（canonical payload）哈希。
                        服务端当前不将其持久化到执行快照、也不据此放行或拒绝恢复，仅作核验上下文留痕；
                        不含服务端注入的 schema_version。内部诊断键（失败细节/原始错误）绝不外发。
                        """,
                        Map.of(),
                        true,
                        "结构未冻结（开放对象 additionalProperties=true）：微晶参数名、单位、范围未冻结，"
                                + "须来自已验证微晶协议；已知键集合为空（无任何经取证的键），客户端不应依赖任何具体键名，"
                                + "且必须容忍未来新增键。依据契约 M4A04Metadata.reportedMicrocrystalState 的 "
                                + "x-detail: skeleton 与 DD 6.2；服务端当前仅做对象/null 校验与载荷哈希，不解释内部键。",
                        null))
        );
    }
}
