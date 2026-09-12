package cn.yuanxin.mvp.web.docs.catalog;

import cn.yuanxin.mvp.web.assessments.AssessmentMultipartParser.A01Metadata;
import cn.yuanxin.mvp.web.assessments.AssessmentMultipartParser.A02Metadata;
import cn.yuanxin.mvp.web.assessments.dto.AssessmentTaskAccepted;
import cn.yuanxin.mvp.web.assessments.dto.AssessmentTaskView;
import cn.yuanxin.mvp.web.assessments.dto.GimbalCurrentAssessmentView;
import cn.yuanxin.mvp.web.assessments.dto.SkinReportListItem;
import cn.yuanxin.mvp.web.assessments.dto.SkinReportView;
import cn.yuanxin.mvp.web.error.ErrorCode;
import io.swagger.v3.oas.models.tags.Tag;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.context.annotation.Profile;
import org.springframework.stereotype.Component;

import java.util.List;
import java.util.Map;
import java.util.Set;

/**
 * Assessment 域联调文档目录：测肤任务提交/补拍/查询、成员报告列表、报告受控投影、
 * 云台当前任务恢复，共 6 个操作（M3-A01…A06）。
 *
 * <p>权威来源：{@code backend/contracts/openapi/openapi.yaml} 的 M3-A01…A06（中文
 * summary/description/x-error-codes 可整段移植）、{@code backend/doc/后端详细设计-V1-MVP.md}
 * 的 M3 与 6.1（投影白名单与禁止项）、{@code backend/doc/数据架构设计-V1-五模块-MVP.md}
 * 的 T05（status 5 态、report_ready 约束、photo_versions 结构）、{@code 角色边界与流程修订说明.md}
 * 与已确认决策 D01-5/D01-6/D01-7，以及各控制器/DTO/服务源码。未冻结项（指标名/区域枚举/
 * 单位、reportSummary 键结构、planAvailability 结构）一律显式标注“未冻结”，不编造语义。</p>
 *
 * <p>本类只写文档内容，不触碰任何控制器/DTO/业务代码。</p>
 */
@Component
@Profile({"dev", "test"})
@ConditionalOnProperty(name = "springdoc.api-docs.enabled", havingValue = "true")
public class AssessmentApiDocs implements ApiDocsCatalog {

    /** 测肤任务提交/补拍/状态查询/云台当前任务恢复。 */
    private static final String TAG_TASK = "测肤任务";
    /** 成员报告列表与报告受控投影。 */
    private static final String TAG_REPORT = "测肤报告";

    @Override
    public String domain() {
        return "assessment";
    }

    @Override
    public List<Tag> tags() {
        return List.of(
                new Tag().name(TAG_TASK)
                        .description("测肤任务：云台提交三视角照片、按补拍要求提交新照片版本、查询任务状态，"
                                + "以及云台重启后恢复后端保存的唯一当前任务。"),
                new Tag().name(TAG_REPORT)
                        .description("测肤报告：已授权 APP 分页列出成员报告，APP full / 云台 brief 读取"
                                + "冻结报告的受控投影（含同源鉴权代理图片引用）。"));
    }

    @Override
    public Map<String, ApiDocEntry> entries() {
        return Map.of(

                // --------------------------------------------------------- M3-A01
                "POST /api/v1/skin-assessment-tasks",
                new ApiDocEntry(
                        TAG_TASK,
                        "提交三视角测肤任务（仅云台）",
                        """
                        用途：云台上传正面/左侧/右侧三视角照片，受理后创建（或替换云台当前）测肤任务，
                        并由后台异步执行分析。
                        调用方主体：仅云台（gimbal device session token）。APP token 调用返回 403 CALLER_NOT_ALLOWED；
                        APP 拍照测肤为非 MVP 能力。
                        前置与顺序：云台先完成设备会话握手（POST /api/v1/gimbal-sessions）。该云台若存在未收尾的
                        护理执行则拒绝：运行中 → 409 DEVICE_OCCUPIED；已停止但未收尾 → 409 STOP_NOT_CONFIRMED。
                        服务端不自动停止护理（D01-7：先停止、记录同步并收尾后才允许新测肤）。
                        请求：multipart/form-data。metadata 为 application/json（结构见 A01Metadata）；
                        front/left/right 为三张图片二进制，三者缺一不可、不得多余或重复（缺/多/重复 → 400 INVALID_INPUT）。
                        字段单位与格式：单图 ≤10MiB、三图合计 ≤32MiB（开发初值，以 app.assessments.max-request-bytes 为准）；
                        图片按字节内容嗅探格式（JPEG/PNG/GIF/WebP），不信任客户端 MIME，不支持 → 415 UNSUPPORTED_IMAGE。
                        幂等语义：Idempotency-Key 必填（1—128 字符）。服务端以 JCS 规范化 metadata 字段 + 各图片 part
                        摘要计算 payload_hash，在 T13 按 (主体类型, 主体 ID, operation=m3a01, Idempotency-Key) 去重：
                        同键同内容重放返回 200 且 meta.replayed=true，不重复建任务、不切指针；同键异内容 →
                        409 IDEMPOTENCY_CONTENT_CONFLICT；处理中 → 409 REQUEST_IN_PROGRESS（按 Retry-After 同键重试）。
                        受理语义：新任务返回 202（已受理、分析异步进行），不代表图片已可用或报告已生成；受理成功
                        即原子完成新增 T05、替换云台 current_assessment_id、current_assessment_revision+1 并投递分析
                        任务（D01-6：不等新报告/新方案生成）。旧请求重放不返回旧结果、不恢复旧指针；缺失/格式失败
                        不受理、不切指针。
                        响应：202 data=AssessmentTaskAccepted（新任务）；200 data 同构（重放，currentAssessmentRevision
                        为 null，仅投影 T13 存储摘要）。
                        错误处理：INVALID_INPUT 修正 metadata/parts；UPLOAD_TOO_LARGE 压缩降分辨率后以新逻辑键重试；
                        UNSUPPORTED_IMAGE 改用受支持格式；DEVICE_OCCUPIED/STOP_NOT_CONFIRMED 先结束并收尾护理；
                        CALLER_NOT_ALLOWED 改用云台主体（重试无意义）；DEPENDENCY_* 受限退避重试。
                        过声明（如实标注）：契约声明 TASK_REPLACED，但本端点实现以“受理即替换”完成，当前实现不返回该码。
                        """,
                        List.of(new ApiDocEntry.ParamDoc("Idempotency-Key", "header",
                                "必填，header，字符串，1—128 字符。逻辑写请求去重键（T13）。同键同内容重放返回 200 且 "
                                        + "meta.replayed=true；同键异内容 409 IDEMPOTENCY_CONTENT_CONFLICT；"
                                        + "处理中 409 REQUEST_IN_PROGRESS（按 Retry-After 同键重试）。",
                                "b6f1c2d3-4e5f-4a7b-8c9d-0e1f2a3b4c5d", null)),
                        List.of(
                                ApiDocEntry.MultipartPartDoc.json("metadata",
                                        "必填，application/json。结构见 A01Metadata：photoVersion 必须为 \"1\"、"
                                                + "captureSessionId（1—128）、consentEvidenceRef（1—128）；未知字段拒绝。",
                                        A01Metadata.class),
                                ApiDocEntry.MultipartPartDoc.binary("front", "image/png",
                                        "必填，正面视角照片二进制。单图 ≤10MiB；按字节内容嗅探格式"
                                                + "（JPEG/PNG/GIF/WebP），不支持 → 415 UNSUPPORTED_IMAGE。"),
                                ApiDocEntry.MultipartPartDoc.binary("left", "image/png",
                                        "必填，左侧视角照片二进制。单图 ≤10MiB；按字节内容嗅探格式"
                                                + "（JPEG/PNG/GIF/WebP）。"),
                                ApiDocEntry.MultipartPartDoc.binary("right", "image/png",
                                        "必填，右侧视角照片二进制。单图 ≤10MiB；按字节内容嗅探格式"
                                                + "（JPEG/PNG/GIF/WebP）。")),
                        null,
                        "multipart/form-data。metadata（application/json，结构见 A01Metadata）+ front/left/right "
                                + "三张图片二进制（缺一不可、不得多余或重复）。大小上限：单图 10MiB、三图合计 32MiB"
                                + "（开发初值，以 app.assessments.max-request-bytes 为准）。幂等：JCS 规范化 metadata "
                                + "字段 + 图片 part 摘要计算 payload_hash；同一 Idempotency-Key + 相同 payload_hash "
                                + "重放返回原受理结果（200，meta.replayed=true），同键异内容 409。",
                        List.of(
                                ApiDocEntry.SuccessDoc.json("202",
                                        "已受理（处理状态不等于图片已可用）；data.taskId 即任务引用，status=queued，"
                                                + "currentAssessmentRevision 为新递增的云台当前任务代次",
                                        AssessmentTaskAccepted.class),
                                ApiDocEntry.SuccessDoc.json("200",
                                        "同一逻辑请求重放（同键同内容），返回原任务引用不重复建任务、不切指针；"
                                                + "currentAssessmentRevision 为 null（重放仅投影 T13 存储摘要）",
                                        AssessmentTaskAccepted.class)),
                        List.of(ErrorCode.INVALID_INPUT, ErrorCode.UPLOAD_TOO_LARGE,
                                ErrorCode.UNSUPPORTED_IMAGE, ErrorCode.AUTH_REQUIRED,
                                ErrorCode.SESSION_INVALID, ErrorCode.CALLER_NOT_ALLOWED,
                                ErrorCode.RESOURCE_NOT_VISIBLE, ErrorCode.TASK_REPLACED,
                                ErrorCode.DEVICE_OCCUPIED, ErrorCode.STOP_NOT_CONFIRMED,
                                ErrorCode.IDEMPOTENCY_CONTENT_CONFLICT, ErrorCode.REQUEST_IN_PROGRESS,
                                ErrorCode.RATE_LIMITED, ErrorCode.DEPENDENCY_UNAVAILABLE,
                                ErrorCode.DEPENDENCY_TIMEOUT, ErrorCode.NOT_IMPLEMENTED)),

                // --------------------------------------------------------- M3-A02
                "PUT /api/v1/skin-assessment-tasks/{taskId}/photo-versions/{photoVersion}",
                new ApiDocEntry(
                        TAG_TASK,
                        "补拍并提交新照片版本（仅云台）",
                        """
                        用途：任务进入 needs_retake 后，云台对被要求的视角重新采集并提交新照片版本，
                        沿用同一任务并触发重分析。
                        调用方主体：仅该任务所属且仍以该任务为当前任务的云台（gimbal device session token）；APP 不开放。
                        前置与顺序（须全部满足）：① taskId 存在且属于该云台，否则 404 RESOURCE_NOT_VISIBLE；
                        ② taskId 仍是云台的当前任务，否则 409 TASK_REPLACED；③ 任务状态为 needs_retake，
                        否则 409 PHOTO_VERSION_CONFLICT（report_ready 之后不得补拍）；④ 路径 photoVersion
                        必须等于当前 currentPhotoVersion+1，且 metadata.expectedPhotoVersion 等于当前版本，
                        否则 409 PHOTO_VERSION_CONFLICT。任意跳版本或引用其他任务媒体一律拒绝。
                        请求：multipart/form-data。metadata 为 application/json（结构见 A02Metadata）；
                        图片 part 名必须与 replacedViews 中各视角同名（front/left/right），集合完全一致、
                        不得缺失/多余/重复（否则 400 INVALID_INPUT）；未更换视角由后端沿用当前版本已接纳图片。
                        字段单位与格式：单图 ≤10MiB、三图合计 ≤32MiB（开发初值）；图片按字节内容嗅探
                        （JPEG/PNG/GIF/WebP）。
                        幂等语义：Idempotency-Key 必填。payload_hash 由 JCS 规范化路径参数（taskId/photoVersion）+
                        expectedPhotoVersion/replacedViews + 图片摘要计算；同键同内容重放返回 200 且不增加版本；
                        同键异内容 409 IDEMPOTENCY_CONTENT_CONFLICT；处理中 409 REQUEST_IN_PROGRESS。
                        受理语义：成功 202；taskId 不变，photoVersion 递增，processing_revision+1，状态回到 queued，
                        旧分析结果不覆盖新版本（版本检查拦截过期写回）。
                        失败：补拍/分析失败不回退——不恢复旧任务的云台访问入口（D01-5/D01-6）。
                        响应：202 data=AssessmentTaskAccepted（新版本）；200 为同请求重放（currentAssessmentRevision
                        为云台当前代次或 null）。
                        错误处理：PHOTO_VERSION_CONFLICT 刷新任务当前版本/状态后以正确的下一版本重试（不要跳版或
                        重复提交同版本异内容）；TASK_REPLACED 以当前任务为准重新发起；其余按错误响应动作。
                        """,
                        List.of(
                                new ApiDocEntry.ParamDoc("taskId", "path",
                                        "必填，path，UUID 字符串（T05.id），测肤任务引用。",
                                        "7f3c2b1a-9d4e-4c5f-8a6b-1d2e3f4a5b6c", null),
                                new ApiDocEntry.ParamDoc("photoVersion", "path",
                                        "必填，path，无符号 bigint 十进制字符串（pattern ^(0|[1-9][0-9]*)$）。"
                                                + "本次提交的新版本号，必须等于任务当前 currentPhotoVersion+1"
                                                + "（首次受理后为 1，补拍须为当前版本+1，否则 409 PHOTO_VERSION_CONFLICT）。",
                                        "2", null),
                                new ApiDocEntry.ParamDoc("Idempotency-Key", "header",
                                        "必填，header，字符串，1—128 字符。逻辑写请求去重键（T13）。同键同内容重放"
                                                + "返回 200 且不增加版本；同键异内容 409 IDEMPOTENCY_CONTENT_CONFLICT。",
                                        "c7e2d3f4-5a6b-4c7d-8e9f-0a1b2c3d4e5f", null)),
                        List.of(
                                ApiDocEntry.MultipartPartDoc.json("metadata",
                                        "必填，application/json。结构见 A02Metadata：expectedPhotoVersion 为"
                                                + "十进制 bigint 字符串且须等于当前版本；replacedViews 为非空、去重、"
                                                + "仅含 front/left/right 的清单。",
                                        A02Metadata.class, true),
                                ApiDocEntry.MultipartPartDoc.binary("front", "image/png",
                                        "条件必填：仅当 metadata.replacedViews 列出 front 时必须上传更换后的正面视角"
                                                + "照片二进制；未列入的视角不得上传多余 part（服务端要求 part 集合与"
                                                + "replacedViews 精确一致）。单图 ≤10MiB；按内容嗅探（JPEG/PNG/GIF/WebP）。",
                                        false),
                                ApiDocEntry.MultipartPartDoc.binary("left", "image/png",
                                        "条件必填：仅当 metadata.replacedViews 列出 left 时必须上传更换后的左侧视角"
                                                + "照片二进制；未列入的视角不得上传多余 part（服务端要求 part 集合与"
                                                + "replacedViews 精确一致）。单图 ≤10MiB；按内容嗅探（JPEG/PNG/GIF/WebP）。",
                                        false),
                                ApiDocEntry.MultipartPartDoc.binary("right", "image/png",
                                        "条件必填：仅当 metadata.replacedViews 列出 right 时必须上传更换后的右侧视角"
                                                + "照片二进制；未列入的视角不得上传多余 part（服务端要求 part 集合与"
                                                + "replacedViews 精确一致）。单图 ≤10MiB；按内容嗅探（JPEG/PNG/GIF/WebP）。",
                                        false)),
                        null,
                        "multipart/form-data。metadata（application/json，结构见 A02Metadata）+ 本次更换视角的图片"
                                + "二进制 part：图片 part 名必须与 metadata.replacedViews 集合完全一致（part 名即视角名"
                                + "front/left/right），缺失/多余/重复均 400 INVALID_INPUT；未更换视角由后端沿用。"
                                + "大小上限：单图 10MiB、合计 32MiB。幂等：JCS 规范化路径参数 + metadata 字段 + 图片"
                                + "摘要计算 payload_hash；同一 Idempotency-Key + 相同 payload_hash 重放不增加版本，"
                                + "同键异内容 409。",
                        List.of(
                                ApiDocEntry.SuccessDoc.json("202",
                                        "新版本已受理（taskId 不变，photoVersion 递增，processing_revision 增加，"
                                                + "状态回到 queued）",
                                        AssessmentTaskAccepted.class),
                                ApiDocEntry.SuccessDoc.json("200",
                                        "同请求重放（同键同内容），不增加版本、不重复重分析",
                                        AssessmentTaskAccepted.class)),
                        List.of(ErrorCode.INVALID_INPUT, ErrorCode.UPLOAD_TOO_LARGE,
                                ErrorCode.UNSUPPORTED_IMAGE, ErrorCode.AUTH_REQUIRED,
                                ErrorCode.SESSION_INVALID, ErrorCode.CALLER_NOT_ALLOWED,
                                ErrorCode.RESOURCE_NOT_VISIBLE, ErrorCode.TASK_REPLACED,
                                ErrorCode.PHOTO_VERSION_CONFLICT, ErrorCode.IDEMPOTENCY_CONTENT_CONFLICT,
                                ErrorCode.REQUEST_IN_PROGRESS, ErrorCode.RATE_LIMITED,
                                ErrorCode.DEPENDENCY_UNAVAILABLE, ErrorCode.DEPENDENCY_TIMEOUT,
                                ErrorCode.NOT_IMPLEMENTED)),

                // --------------------------------------------------------- M3-A03
                "GET /api/v1/skin-assessment-tasks/{taskId}",
                new ApiDocEntry(
                        TAG_TASK,
                        "查询测肤任务状态与补拍要求",
                        """
                        用途：查询测肤任务的当前状态、照片版本、需补拍视角与报告引用；纯查询、无副作用，
                        不触发分析或新建任务。
                        调用方主体：两者。① 云台：仅当 taskId 仍是该云台的当前任务，否则 409 TASK_REPLACED；
                        非本云台任务统一 404 RESOURCE_NOT_VISIBLE。② APP：需对该任务成员有 active 查看授权；
                        memberId 尚未可靠固定的任务不向 APP 开放（404 RESOURCE_NOT_VISIBLE，不因 APP 声称成员身份
                        而开放；服务端不信任客户端输入的成员归属）。
                        状态机（5 态 status）与客户端动作：queued=已受理待分析（继续轮询）；analyzing=分析中
                        （继续轮询）；needs_retake=需补拍（按 requiredViews 用 M3-A02 提交新版本）；report_ready=
                        报告就绪（reportId 非空，用 M3-A05 读取；报告 ready 后立即可读，不等方案生成）；
                        failed=终态失败（看 failureCode/retryable；GET 不是重试入口，用户重新测肤用 M3-A01）。
                        投影口径：requiredViews 仅在 needs_retake 非空——从 identity_result.quality.required_views
                        过滤到 front/left/right、去重、上限 3，缺失/非数组/解析失败为空数组；
                        failureCode 仅返回公开白名单（见下），其余内部码投影为 null；retryable 当前任何非 null
                        failureCode 均为 false（true 为未来可重试失败预留，绝不解析内部诊断推导）；
                        reportId 仅 report_ready 且报告存在时给出；planAvailability 为关联护理方案的
                        generation_status 或 null（结构未冻结，以实现为准）。
                        failureCode 公开白名单（9 个，FailureProjection.PUBLIC_FAILURE_CODES）：
                        QUALITY_REJECTED、NOT_SAME_PERSON、IDENTITY_UNCERTAIN、IDENTITY_ENROLLMENT_TIMEOUT、
                        SOURCE_IMAGE_UNAVAILABLE、RESULT_ARCHIVE_FAILED、PROVIDER_CONTRACT_VIOLATION、
                        MEMBER_NOT_VISIBLE、DEPENDENCY_UNAVAILABLE。白名单外一律投影 null。
                        failure_detail 属内部诊断，绝不外泄。
                        契约缺口（如实标注，待总协调裁定）：failureCode 还可能返回 PROVIDER_CONTRACT_VIOLATION
                        （算法结果违约的终态失败，retryable=false）——该码尚未列入契约 ErrorCode enum、也不在
                        DD 3.2 表中，属已知契约缺口；本端点 errorCodes 只列契约枚举成员，不包含该码。
                        响应头：Cache-Control: no-store（成员敏感数据与图片响应恒定）。
                        过声明（如实标注）：契约声明 CALLER_NOT_ALLOWED，但本端点对主体/归属不匹配统一以
                        RESOURCE_NOT_VISIBLE 处理（防存在性推断），当前实现不返回该码。
                        """,
                        List.of(new ApiDocEntry.ParamDoc("taskId", "path",
                                "必填，path，UUID 字符串（T05.id），测肤任务引用。",
                                "7f3c2b1a-9d4e-4c5f-8a6b-1d2e3f4a5b6c", null)),
                        List.of(),
                        null,
                        null,
                        List.of(ApiDocEntry.SuccessDoc.json("200",
                                "任务状态与补拍要求（受控投影；failure_detail 绝不外泄）",
                                AssessmentTaskView.class)),
                        List.of(ErrorCode.AUTH_REQUIRED, ErrorCode.SESSION_INVALID,
                                ErrorCode.CALLER_NOT_ALLOWED, ErrorCode.RESOURCE_NOT_VISIBLE,
                                ErrorCode.TASK_REPLACED, ErrorCode.RATE_LIMITED,
                                ErrorCode.DEPENDENCY_UNAVAILABLE, ErrorCode.DEPENDENCY_TIMEOUT,
                                ErrorCode.NOT_IMPLEMENTED)),

                // --------------------------------------------------------- M3-A04
                "GET /api/v1/members/{memberId}/skin-reports",
                new ApiDocEntry(
                        TAG_REPORT,
                        "列出成员可访问的测肤报告",
                        """
                        用途：分页列出指定成员已正式发布的测肤报告摘要（不含完整报告大载荷）。
                        调用方主体：仅 APP（APP session token）。云台 token 一律 403 CALLER_NOT_ALLOWED，
                        即使报告来自该云台或人脸相同。
                        前置：当前账号对该成员有 active 成员查看授权（T02）；无授权 → 404 RESOURCE_NOT_VISIBLE
                        （对“不存在”与“不可见”返回完全相同响应，不要换 memberId 探测）。
                        分页与排序：keyset 游标，按 (reportReadyAt DESC, id DESC)；limit 默认 20、上限 100；
                        只列 status=report_ready 且 report_id 非空的正式报告；无正式报告返回空数组 items=[]；
                        不返回总数。
                        游标：cursor 为不透明 URL-safe Base64 令牌，绑定排序值 + 报告 id + memberId 过滤摘要；
                        跨成员/跨账号或非法游标 → 400 INVALID_INPUT（修正后从第一页重取）。
                        响应头：Cache-Control: no-store。
                        错误处理：INVALID_INPUT 丢弃本地游标从第一页重取；RESOURCE_NOT_VISIBLE 不换 memberId
                        探测；云台应改用 M3-A06。
                        过声明（如实标注）：契约声明 GRANT_REVOKED，但当前实现对“无 active 授权/不可见”统一用
                        RESOURCE_NOT_VISIBLE（SkinReportService 不抛 GRANT_REVOKED），该码在本端点当前实现中不触发。
                        """,
                        List.of(
                                new ApiDocEntry.ParamDoc("memberId", "path",
                                        "必填，path，UUID 字符串（T01.id），成员引用；需当前账号对其有 active "
                                                + "查看授权。",
                                        "1a2b3c4d-5e6f-4a7b-8c9d-0e1f2a3b4c5d", null),
                                new ApiDocEntry.ParamDoc("limit", "query",
                                        "可选，query，整数，1—100，默认 20。分页大小；不默认返回总数。",
                                        "20", null),
                                new ApiDocEntry.ParamDoc("cursor", "query",
                                        "可选，query，字符串。不透明 keyset 游标（URL-safe Base64），绑定排序值 + "
                                                + "报告 id + memberId 过滤摘要；原样回传上一页 nextCursor；缺省为第一页；"
                                                + "非法/跨成员游标 400 INVALID_INPUT。",
                                        null, null)),
                        List.of(),
                        null,
                        null,
                        List.of(ApiDocEntry.SuccessDoc.jsonList("200",
                                "报告摘要列表页：data={items, nextCursor}；nextCursor 为 null 表示无后续页"
                                        + "（字段保留，不省略）",
                                SkinReportListItem.class)),
                        List.of(ErrorCode.INVALID_INPUT, ErrorCode.AUTH_REQUIRED,
                                ErrorCode.SESSION_INVALID, ErrorCode.CALLER_NOT_ALLOWED,
                                ErrorCode.RESOURCE_NOT_VISIBLE, ErrorCode.GRANT_REVOKED,
                                ErrorCode.RATE_LIMITED, ErrorCode.DEPENDENCY_UNAVAILABLE,
                                ErrorCode.DEPENDENCY_TIMEOUT, ErrorCode.NOT_IMPLEMENTED)),

                // --------------------------------------------------------- M3-A05
                "GET /api/v1/skin-reports/{reportId}",
                new ApiDocEntry(
                        TAG_REPORT,
                        "查询测肤报告（APP full / 云台 brief）",
                        """
                        用途：按 reportId 返回冻结报告载荷的受控投影（同一报告的 APP/full 与云台/brief 两种视图）。
                        调用方主体：两者。APP 取 view=full（需对该报告成员有 active 查看授权，默认 full）；
                        云台仅可读其当前任务对应报告且仅 brief——显式传 full 不扩大权限，返回 403 CALLER_NOT_ALLOWED。
                        前置：报告必须 status=report_ready，否则 404 RESOURCE_NOT_VISIBLE；云台读取时报告所属任务
                        必须仍是云台当前指针任务，否则 409 TASK_REPLACED（不返回被替换旧报告）。
                        view 参数：full|brief，默认 full；brief 省略 memberId/metrics/description（字段省略而非显式 null）。
                        投影白名单（DD 6.1）：full 可返回 reportId、memberId、报告时间 reportReadyAt、结构化指标
                        metrics、已验证说明 description、允许展示的结果图片 images；brief 仅当前 reportId、简要结论
                        conclusion、当前报告允许展示的结果图片。禁止返回人脸特征、供应商库 ID、核验图、访问密钥、
                        模型/算法原始响应与提示词。
                        metrics：仅 full 视图；每个元素仅 name/value/unit 三键；指标名与区域枚举必须来自测肤协议
                        契约，当前未冻结，不得由大模型自由发明（见 SkinReportView.metrics 的自由结构说明）。
                        images[].contentUrl：同源鉴权代理 URL GET /api/v1/media/{mediaId}/content，每次读取复核
                        权限；非永久地址、非算法临时地址。响应恒定 Cache-Control: no-store、X-Content-Type-Options:
                        nosniff；不可见与不存在同 404。
                        错误处理：INVALID_INPUT（view 非 full/brief）；RESOURCE_NOT_VISIBLE 不换 reportId 探测；
                        TASK_REPLACED 以当前任务报告为准；云台传 full → CALLER_NOT_ALLOWED。
                        过声明（如实标注）：契约声明 GRANT_REVOKED，但当前实现对无授权/不可见统一用
                        RESOURCE_NOT_VISIBLE（SkinReportService 不抛 GRANT_REVOKED），该码在本端点当前实现中不触发。
                        """,
                        List.of(
                                new ApiDocEntry.ParamDoc("reportId", "path",
                                        "必填，path，UUID 字符串（T05.report_id），报告公开标识。",
                                        "9e8d7c6b-5a4f-4e3d-9c2b-1a0f9e8d7c6b", null),
                                new ApiDocEntry.ParamDoc("view", "query",
                                        "可选，query，字符串枚举 full|brief，默认 full。full=完整受控视图（APP；"
                                                + "云台传 full 拒绝）；brief=简版（云台唯一可用）；full/brief 是同一数据的"
                                                + "受控视图。非法值 400 INVALID_INPUT。",
                                        "full", null)),
                        List.of(),
                        null,
                        null,
                        List.of(ApiDocEntry.SuccessDoc.json("200",
                                "报告受控投影（full/brief 按调用角色与 view 决定；图片仅为同源鉴权代理引用）",
                                SkinReportView.class)),
                        List.of(ErrorCode.INVALID_INPUT, ErrorCode.AUTH_REQUIRED,
                                ErrorCode.SESSION_INVALID, ErrorCode.CALLER_NOT_ALLOWED,
                                ErrorCode.RESOURCE_NOT_VISIBLE, ErrorCode.TASK_REPLACED,
                                ErrorCode.GRANT_REVOKED, ErrorCode.RATE_LIMITED,
                                ErrorCode.DEPENDENCY_UNAVAILABLE, ErrorCode.DEPENDENCY_TIMEOUT,
                                ErrorCode.NOT_IMPLEMENTED)),

                // --------------------------------------------------------- M3-A06
                "GET /api/v1/gimbals/{gimbalId}/current-assessment",
                new ApiDocEntry(
                        TAG_TASK,
                        "恢复云台当前测肤任务（仅云台）",
                        """
                        用途：云台重启/重连后恢复后端持久保存的唯一当前测肤任务引用；不提供历史任务列表。
                        调用方主体：仅云台自身（gimbal device session token）；路径 gimbalId 必须等于认证主体
                        （不要求绑定 APP 账号），否则 403 CALLER_NOT_ALLOWED。
                        返回：currentAssessment = {taskId, status, photoVersion, reportId?}，或严格为 null
                        （无当前任务时字段保留为 null，不省略）；currentAssessmentRevision 为无符号 bigint
                        十进制字符串，每次成功受理新任务 +1，恢复/轮询/旧请求重试不递增。
                        关键规则（D01-5/D01-6/D01-7）：只返回当前指针任务；不移动指针、不提供历史任务列表、
                        不按人脸搜索旧任务、不自动开始/恢复护理（恢复护理仍走 M4-A03/A04 并在开始前核验人脸）；
                        被新任务替换的旧任务不可通过本端点恢复，旧资料仅按成员授权供 APP 使用。
                        错误处理：AUTH_REQUIRED/SESSION_INVALID 重新握手；CALLER_NOT_ALLOWED 确认 gimbalId 与
                        认证主体一致；RESOURCE_NOT_VISIBLE 云台行不可见，不要换 ID 探测。
                        """,
                        List.of(new ApiDocEntry.ParamDoc("gimbalId", "path",
                                "必填，path，UUID 字符串（T03.id），云台引用；必须等于认证主体的 gimbalId。",
                                "2b3c4d5e-6f7a-4b8c-9d0e-1f2a3b4c5d6e", null)),
                        List.of(),
                        null,
                        null,
                        List.of(ApiDocEntry.SuccessDoc.json("200",
                                "当前任务指针：currentAssessment 为任务引用或严格 null（无当前任务）；"
                                        + "currentAssessmentRevision 为当前代次",
                                GimbalCurrentAssessmentView.class)),
                        List.of(ErrorCode.AUTH_REQUIRED, ErrorCode.SESSION_INVALID,
                                ErrorCode.CALLER_NOT_ALLOWED, ErrorCode.RESOURCE_NOT_VISIBLE,
                                ErrorCode.RATE_LIMITED, ErrorCode.DEPENDENCY_UNAVAILABLE,
                                ErrorCode.DEPENDENCY_TIMEOUT, ErrorCode.NOT_IMPLEMENTED))
        );
    }

    /**
     * 契约要求必填、但服务端以 <strong>multipart 解析器手工严格校验</strong>（而非 Bean Validation
     * 注解）实现的属性 ⇒ springdoc 推导出的 {@code required} 为空，此处按<strong>契约与服务端实际
     * 行为</strong>修正生成文档。
     *
     * <p>取证：{@code AssessmentMultipartParser.java:60-61}（{@code photoVersion} 须为十进制
     * bigint 串且新任务只接受 {@code "1"}）、{@code :63}（{@code captureSessionId} requireText，
     * 1-128）、{@code :64}（{@code consentEvidenceRef} requireText，1-128）、{@code :73-74}
     * （{@code expectedPhotoVersion} 须为十进制 bigint 串且等于当前版本）、{@code :76-88}
     * （{@code replacedViews} 非空、元素 ∈ front/left/right、不可重复）；违规一律
     * 400 {@code INVALID_INPUT}。</p>
     *
     * <p><strong>这不是实现偏差</strong>（与 {@code EchoJobRequestBody.numbersAsStrings}
     * "契约必填而代码不强制"的情形性质不同）：服务端确实强制，只是未用注解声明，
     * 故 springdoc 看不见。</p>
     */
    @Override
    public Map<String, Set<String>> requiredProperties() {
        return Map.of(
                "A01Metadata", Set.of("photoVersion", "captureSessionId", "consentEvidenceRef"),
                "A02Metadata", Set.of("expectedPhotoVersion", "replacedViews"));
    }

    @Override
    public Map<String, Map<String, PropertyDoc>> propertyDocs() {
        return Map.ofEntries(

                Map.entry("A01Metadata", Map.of(
                        "photoVersion", PropertyDoc.of(
                                "必填，字符串，无符号 bigint 十进制字符串。新建任务首次提交必须严格为 \"1\"；"
                                        + "非 \"1\" 或非十进制串 → 400 INVALID_INPUT。",
                                "1"),
                        "captureSessionId", PropertyDoc.of(
                                "必填，字符串，1—128 字符。云台本轮采集会话标识（客户端去重/关联字段）。",
                                "capture-session-20260913-0001"),
                        "consentEvidenceRef", PropertyDoc.of(
                                "必填，字符串，1—128 字符。用户知情同意证据引用。",
                                "consent-ref-20260913-0001"))),

                Map.entry("A02Metadata", Map.of(
                        "expectedPhotoVersion", PropertyDoc.of(
                                "必填，字符串，无符号 bigint 十进制字符串。云台所见的当前照片版本，必须等于任务"
                                        + "当前 currentPhotoVersion，否则 409 PHOTO_VERSION_CONFLICT。",
                                "1"),
                        "replacedViews", PropertyDoc.of(
                                "必填，数组，非空、去重，元素仅可为 front/left/right；必须与本次上传的图片 part 名"
                                        + "集合完全一致。新版本其余视角沿用任务已接纳图片。"))),

                Map.entry("AssessmentTaskAccepted", Map.of(
                        "taskId", PropertyDoc.of(
                                "字符串，UUID 格式，测肤任务引用（T05.id）。",
                                "7f3c2b1a-9d4e-4c5f-8a6b-1d2e3f4a5b6c"),
                        "status", PropertyDoc.enumOf(
                                "字符串，受理后状态，固定为 queued（分析异步进行，不代表图片已可用或报告已生成）。",
                                List.of("queued"), "queued"),
                        "photoVersion", PropertyDoc.of(
                                "字符串，无符号 bigint 十进制字符串。新任务为 \"1\"；补拍为新递增版本号。",
                                "1"),
                        "currentAssessmentRevision", PropertyDoc.of(
                                "可空字符串，无符号 bigint 十进制字符串。云台当前任务代次：新任务受理时递增给出；"
                                        + "重放（200）时为 null（仅投影 T13 存储摘要）。",
                                "1"))),

                Map.entry("AssessmentTaskView", Map.of(
                        "taskId", PropertyDoc.of(
                                "字符串，UUID 格式，测肤任务引用（T05.id）。",
                                "7f3c2b1a-9d4e-4c5f-8a6b-1d2e3f4a5b6c"),
                        "status", PropertyDoc.enumOf(
                                "字符串，任务状态机 5 态：queued=待分析；analyzing=分析中；needs_retake=需补拍"
                                        + "（按 requiredViews 走 M3-A02）；report_ready=报告就绪（可读 M3-A05）；"
                                        + "failed=终态失败（看 failureCode/retryable，GET 非重试入口）。",
                                List.of("queued", "analyzing", "needs_retake", "report_ready", "failed"),
                                "needs_retake"),
                        "photoVersion", PropertyDoc.of(
                                "字符串，无符号 bigint 十进制字符串，当前输入照片版本。", "1"),
                        "requiredViews", PropertyDoc.of(
                                "数组：需补拍视角，元素仅可为 front/left/right。仅 needs_retake 时非空——"
                                        + "由 identity_result.quality.required_views 过滤到该枚举、去重、上限 3；"
                                        + "解析失败为空数组。"),
                        "failureCode", PropertyDoc.of(
                                "可空字符串，可公开失败编码。仅返回 9 个公开白名单码（QUALITY_REJECTED、"
                                        + "NOT_SAME_PERSON、IDENTITY_UNCERTAIN、IDENTITY_ENROLLMENT_TIMEOUT、"
                                        + "SOURCE_IMAGE_UNAVAILABLE、RESULT_ARCHIVE_FAILED、"
                                        + "PROVIDER_CONTRACT_VIOLATION、MEMBER_NOT_VISIBLE、DEPENDENCY_UNAVAILABLE）；"
                                        + "白名单外的内部 failure_code 一律投影为 null。",
                                "QUALITY_REJECTED"),
                        "retryable", PropertyDoc.of(
                                "可空布尔：该失败是否可重试。当前任何非 null failureCode 均为 false；null 表示无失败。",
                                "false"),
                        "reportId", PropertyDoc.of(
                                "可空字符串，UUID 格式。仅 status=report_ready 且报告存在时给出，否则 null。",
                                "9e8d7c6b-5a4f-4e3d-9c2b-1a0f9e8d7c6b"),
                        "planAvailability", PropertyDoc.of(
                                "可空字符串，关联护理方案的 generation_status（如 waiting_inputs/generating/"
                                        + "ready/failed）或 null；结构未冻结，以实现为准。",
                                "ready"))),

                Map.entry("GimbalCurrentAssessmentView", Map.of(
                        "currentAssessment", PropertyDoc.of(
                                "可空对象，云台当前任务引用。无当前任务时严格为 null（字段保留，不省略）；"
                                        + "不提供历史列表、不移动指针。"),
                        "currentAssessmentRevision", PropertyDoc.of(
                                "字符串，无符号 bigint 十进制字符串。云台当前任务代次；成功受理新任务时 +1，"
                                        + "恢复/轮询/重放不递增。",
                                "1"))),

                // 嵌套 record（GimbalCurrentAssessmentView.currentAssessment 的 $ref 目标），
                // 引擎按简单类名注册，须逐属性文档化以满足属性级覆盖率门禁。
                Map.entry("CurrentAssessment", Map.of(
                        "taskId", PropertyDoc.of(
                                "字符串，UUID 格式，当前任务引用（T05.id）。",
                                "7f3c2b1a-9d4e-4c5f-8a6b-1d2e3f4a5b6c"),
                        "status", PropertyDoc.enumOf(
                                "字符串，任务状态机 5 态：queued/analyzing/needs_retake/report_ready/failed。",
                                List.of("queued", "analyzing", "needs_retake", "report_ready", "failed"),
                                "report_ready"),
                        "photoVersion", PropertyDoc.of(
                                "字符串，无符号 bigint 十进制字符串，当前输入照片版本。", "1"),
                        "reportId", PropertyDoc.of(
                                "可空字符串，UUID 格式。仅任务 report_ready 且报告存在时给出，否则 null。",
                                "9e8d7c6b-5a4f-4e3d-9c2b-1a0f9e8d7c6b"))),

                Map.entry("SkinReportListItem", Map.of(
                        "reportId", PropertyDoc.of(
                                "字符串，UUID 格式，报告公开标识（T05.report_id）。",
                                "9e8d7c6b-5a4f-4e3d-9c2b-1a0f9e8d7c6b"),
                        "reportReadyAt", new PropertyDoc(
                                "字符串，RFC3339 UTC 秒精度报告就绪时间（例如 2026-09-13T08:30:00Z）。",
                                null, null, "2026-09-13T08:30:00Z", "date-time"),
                        "reportSummary", PropertyDoc.of(
                                "可空对象，DB skin_assessments.report_summary（JSONB）原样摘要；键结构未冻结，"
                                        + "见该字段的自由结构展开说明。"))),

                Map.entry("SkinReportView", Map.of(
                        "reportId", PropertyDoc.of(
                                "字符串，UUID 格式，报告公开标识（T05.report_id）。",
                                "9e8d7c6b-5a4f-4e3d-9c2b-1a0f9e8d7c6b"),
                        "view", PropertyDoc.enumOf(
                                "字符串，本次返回的受控视图：full=完整（APP）/ brief=简版（云台）。",
                                List.of("full", "brief"), "full"),
                        "memberId", PropertyDoc.of(
                                "可空字符串，UUID 格式，报告所属成员；仅 full 视图返回，brief 省略该字段。",
                                "1a2b3c4d-5e6f-4a7b-8c9d-0e1f2a3b4c5d"),
                        "reportReadyAt", new PropertyDoc(
                                "可空字符串，RFC3339 UTC 秒精度报告就绪时间（例如 2026-09-13T08:30:00Z）。",
                                null, null, "2026-09-13T08:30:00Z", "date-time"),
                        "conclusion", PropertyDoc.of(
                                "可空字符串，简要结论（brief 视图允许返回）。", "整体肤质状态良好"),
                        "metrics", PropertyDoc.of(
                                "数组，结构化指标；仅 full 视图返回（brief 时整字段省略）。每个元素仅 name/value/unit "
                                        + "三键，指标名与区域枚举必须来自测肤协议契约、当前未冻结；见该字段的自由结构展开说明。"),
                        "description", PropertyDoc.of(
                                "可空字符串，已验证说明；仅 full 视图返回（brief 时省略）。",
                                "建议加强保湿与防晒"),
                        "images", PropertyDoc.of(
                                "数组，允许展示的结果图片描述（受控访问引用，非图片二进制）；brief 视图仅含当前报告"
                                        + "允许展示的图片。"),
                        "planStatus", PropertyDoc.of(
                                "可空字符串，关联护理方案的生成状态/任务引用（报告不等待方案）；无关联方案时为 null。",
                                "generating"))),

                Map.entry("SkinReportImage", Map.of(
                        "mediaId", PropertyDoc.of(
                                "字符串，UUID 格式，媒体对象引用（T11.id）。",
                                "5c4b3a29-1807-4f6e-8d5c-3b2a19087f6e"),
                        "contentUrl", PropertyDoc.of(
                                "字符串，同源鉴权代理 URL，形如 /api/v1/media/{mediaId}/content。非永久地址、"
                                        + "非算法临时地址；每次读取复核权限，响应 Cache-Control: no-store，"
                                        + "不可见与不存在同 404。",
                                "/api/v1/media/5c4b3a29-1807-4f6e-8d5c-3b2a19087f6e/content")))
        );
    }

    @Override
    public Map<String, FreeFormDoc> freeFormDocs() {
        return Map.of(

                "SkinReportListItem.reportSummary", new FreeFormDoc(
                        """
                        测肤报告摘要：写入方为测肤 Worker（assessment_analyze.py:412-417 固定构造），与正式报告
                        同事务生成，落库于 T05.report_summary（JSONB，可空）；列表端点（SkinReportService.java:87）
                        将其 parseJson 后原样外发，不加载完整 report_payload。本字段不是客户端可写字段。
                        权威文档未定义该结构，以下键取自写入方实现（assessment_analyze.py:412-417）：
                        schema_version、conclusion、headline_metrics。内部诊断键（failure_detail/
                        identity_result 等）绝不外发。
                        """,
                        Map.of(
                                "schema_version", "integer，摘要结构版本，当前写入方固定为 1。",
                                "conclusion", "string，测肤结论（取自测肤算法 provider 返回的 conclusion 字段；"
                                        + "取值集合当前未冻结、无枚举约束，dev/test 替身默认为 balanced）。",
                                "headline_metrics", "array，要点指标名列表，最多 8 项；元素为指标名（string），"
                                        + "指标名集合未冻结、须来自测肤协议契约。"),
                        true,
                        "已知键来自写入方 assessment_analyze.py:412-417 的固定构造（schema_version/conclusion/"
                                + "headline_metrics）；写入方未来可能新增键，客户端必须容忍（additionalProperties=true），"
                                + "不得依赖任何具体键名或假设字段存在。failure_detail/identity_result 等内部诊断绝不外发。",
                        null),

                "SkinReportView.metrics", new FreeFormDoc(
                        """
                        结构化测肤指标数组：仅 full 视图返回（brief 时整字段省略）。每个元素由 SkinReportService
                        从冻结 report_payload.metrics 投影，只复制 name/value/unit 三键，其余键（含算法/模型信息）
                        一律丢弃、绝不输出。指标名与区域枚举必须来自测肤协议契约，当前未冻结，不得由大模型自由发明。
                        """,
                        Map.of(
                                "name", "string，指标名。必须来自测肤协议契约，当前未冻结，不得自由发明。",
                                "value", "number，指标值。数值/文本类型与语义未冻结，须来自测肤协议契约。",
                                "unit", "string，指标单位。单位未冻结，须来自测肤协议契约。"),
                        false,
                        "封闭白名单：服务端对每个指标对象仅投影 name/value/unit 三键，其余键一律丢弃"
                                + "（additionalProperties=false）；客户端不得依赖更多键。指标名、区域枚举与单位"
                                + "必须来自测肤协议契约，当前未冻结，不得自由发明。",
                        null));
    }
}
