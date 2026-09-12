package cn.yuanxin.mvp.web.docs.catalog;

import cn.yuanxin.mvp.web.devices.DeviceDtos;
import cn.yuanxin.mvp.web.error.ErrorCode;
import cn.yuanxin.mvp.web.identity.MemberAccessGrantController;
import cn.yuanxin.mvp.web.identity.MemberAccessGrantService;
import cn.yuanxin.mvp.web.notifications.NotificationDestinationDtos;
import io.swagger.v3.oas.models.tags.Tag;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.context.annotation.Profile;
import org.springframework.stereotype.Component;

import java.util.List;
import java.util.Map;
import java.util.Set;

/**
 * Identity + Device + Notification 域联调文档目录：成员访问授权（M1-A01—A03）、
 * 云台心跳/状态/微晶观察/云台绑定（M2-A02—A08）、通知目标登记（M5-A01），共 11 个操作。
 *
 * <p>权威来源：{@code backend/contracts/openapi/openapi.yaml}（34/34 中文
 * summary/description 与 {@code x-error-codes}，尤其 m1A01/m1A03/m2A06/m2A08/m5A01）、
 * {@code backend/doc/后端详细设计-V1-MVP.md} 的 M1/M2/9.5、{@code backend/doc/数据架构设计-V1-五模块-MVP.md}
 * 的 T02/T03/T04/T09/T10/T11、{@code backend/doc/后端API接口设计-V1-五模块与流程对应.md} 的对应 API 规则、
 * {@code backend/handoffs/B.md} 的 C25/C26 披露，以及各控制器/服务/DTO 源码。</p>
 *
 * <p>未冻结项（云台连接状态编码、异常码/严重度枚举、微晶协议参数名/单位/范围、微晶 state 结构、
 * 推送通道 provider 与 registration 结构、配对证明/连接证明协议）一律显式标注“待定/未冻结”，
 * 不编造语义。本类只写文档内容，不触碰任何控制器/DTO/业务代码。</p>
 */
@Component
@Profile({"dev", "test"})
@ConditionalOnProperty(name = "springdoc.api-docs.enabled", havingValue = "true")
public class IdentityDeviceApiDocs implements ApiDocsCatalog {

    /** M1 成员身份与查看授权。 */
    private static final String TAG_GRANT = "成员访问授权";
    /** M2 云台与微晶：心跳、状态、观察与绑定。 */
    private static final String TAG_DEVICE = "设备与绑定";
    /** M5 通知投递目标登记。 */
    private static final String TAG_NOTIFY = "通知目标";

    @Override
    public String domain() {
        return "identity-device";
    }

    @Override
    public List<Tag> tags() {
        return List.of(
                new Tag().name(TAG_GRANT)
                        .description("成员查看授权：APP 人脸核验建立/查询/撤销对本人资料的查看关联。"
                                + "授权不自动过期；无 active grant 时查看该成员资料返回 404。"),
                new Tag().name(TAG_DEVICE)
                        .description("云台与微晶：云台心跳与状态（仅云台/绑定账号）、微晶能力与状态观察"
                                + "（APP 或云台）、配网查询与主动绑定/解绑（仅 APP）。绑定只决定异常通知账号，"
                                + "不授予成员资料查看权。"),
                new Tag().name(TAG_NOTIFY)
                        .description("通知目标：已登录 APP 登记本安装实例的推送投递目标（只登记、不发送消息；"
                                + "绝不回传完整推送 token）。"));
    }

    @Override
    public Map<String, ApiDocEntry> entries() {
        return Map.ofEntries(

                // ---------------------------------------------------------- M1-A01
                Map.entry("POST /api/v1/member-access-grants", new ApiDocEntry(
                        TAG_GRANT,
                        "人脸核验并授予当前账号查看该成员资料",
                        """
                        用途：APP 用户对本人进行一次人脸采集，可靠确认本人后建立当前账号与该成员的查看授权关系；
                        本授权是 M3-A04/A05 与 M4 系列查看/执行护理的前置（无 active grant → 404 RESOURCE_NOT_VISIBLE）。
                        调用方：仅 APP（Bearer = APP session token，手机号会话签发）；云台 token → 403 CALLER_NOT_ALLOWED。
                        请求形态：multipart/form-data，parts 必须恰为 metadata（JSON）与 face（图片二进制）；
                        缺失/多余 part 或存在额外表单字段 → 400 INVALID_INPUT。face 为空 → 415 UNSUPPORTED_IMAGE，
                        超单图上限（开发初值 10MiB）→ 413 UPLOAD_TOO_LARGE，内容嗅探非白名单格式 → 415 UNSUPPORTED_IMAGE。
                        关键规则：metadata.capture.purpose 必须为 grant；captureId/clientContinuityId 与
                        consentEvidenceRef 均为 1—128 字符；capturedAt 为 RFC3339 时间戳。服务端只读定位成员
                        （identity_namespace + face_subject_ref），不创建新成员、不授予他人查看权、不提供护理启动许可。
                        存储：face 图片以 T11 media purpose=grant_face 落库（T11 purpose 枚举共 5 值：
                        assessment_source/assessment_result/grant_face/execution_face/revalidation_face；本域固定 grant_face）。
                        无可靠匹配、匹配不确定或库中无此成员一律 403 FACE_NOT_VERIFIED 且响应完全一致
                        （不返回候选列表，不泄漏成员是否存在）。
                        成功码：201 新建 active 授权关系；200 表示已存在 active 关系（复用同一 grantId，
                        meta.replayed=false）或 T13 同键同内容重放（meta.replayed=true）；两种 200 都不刷新核验有效性。
                        幂等语义：Idempotency-Key 必填（1—128 字符）；同键同内容重放返回原结果；同键异内容
                        409 IDEMPOTENCY_CONTENT_CONFLICT；处理中 409 REQUEST_IN_PROGRESS + Retry-After。
                        旧请求指向已撤销关系 → 403 GRANT_REVOKED（不创建新关系、零新行）；重新授权必须发起
                        新的人脸请求并使用新 Idempotency-Key。
                        错误处理：FACE_QUALITY_REJECTED 重新采集清晰正脸；FACE_NOT_VERIFIED 按提示重拍，
                        不要自动建档或换照片复用同键；图片保存/读取失败绝不当作核验成功（DEPENDENCY_*）；
                        DEPENDENCY_* 与 RATE_LIMITED 受限退避重试。
                        契约过声明（如实标注）：RESOURCE_NOT_VISIBLE 由 T13 重放投影/找不到原 grant 等路径可能触发，保留。
                        """,
                        List.of(idempotencyKey("grant-face-20260913-0001")),
                        List.of(
                                ApiDocEntry.MultipartPartDoc.json("metadata",
                                        "必填 JSON part：M1A01Metadata{capture, consentEvidenceRef}；"
                                                + "capture.purpose 必须为 grant；未知字段（如 memberId）→ 400 INVALID_INPUT。",
                                        MemberAccessGrantController.M1A01Metadata.class),
                                ApiDocEntry.MultipartPartDoc.binary("face", "image/png",
                                        "必填图片 part：当前人脸采集图（建议 PNG/JPEG；单图 ≤10MiB 开发初值）；"
                                                + "按内容嗅探判定格式，不信任客户端 MIME；空图 → 415。")),
                        null,
                        "multipart/form-data：metadata（JSON）+ face（图片二进制），两者必填且不可有多余 part。"
                                + "T13 幂等 payload_hash = 规范化 metadata 字段 + face 图片字节摘要，与 Idempotency-Key "
                                + "共同决定重放：同键同内容返回原结果，同键异内容 409。",
                        List.of(
                                ApiDocEntry.SuccessDoc.json("201",
                                        "新建查看授权关系成功（data.status=active，meta.replayed=false）",
                                        MemberAccessGrantController.MemberAccessGrantResult.class),
                                ApiDocEntry.SuccessDoc.json("200",
                                        "已存在 active 关系（复用同一 grantId，meta.replayed=false）或同键同内容重放"
                                                + "（meta.replayed=true）",
                                        MemberAccessGrantController.MemberAccessGrantResult.class)),
                        List.of(ErrorCode.INVALID_INPUT, ErrorCode.UPLOAD_TOO_LARGE,
                                ErrorCode.UNSUPPORTED_IMAGE, ErrorCode.FACE_QUALITY_REJECTED,
                                ErrorCode.AUTH_REQUIRED, ErrorCode.SESSION_INVALID,
                                ErrorCode.CALLER_NOT_ALLOWED, ErrorCode.FACE_NOT_VERIFIED,
                                ErrorCode.RESOURCE_NOT_VISIBLE, ErrorCode.GRANT_REVOKED,
                                ErrorCode.IDEMPOTENCY_CONTENT_CONFLICT, ErrorCode.REQUEST_IN_PROGRESS,
                                ErrorCode.RATE_LIMITED, ErrorCode.DEPENDENCY_UNAVAILABLE,
                                ErrorCode.DEPENDENCY_TIMEOUT, ErrorCode.NOT_IMPLEMENTED))),

                // ---------------------------------------------------------- M1-A02
                Map.entry("GET /api/v1/me/member-access-grants", new ApiDocEntry(
                        TAG_GRANT,
                        "查询当前账号未撤销的成员查看授权列表",
                        """
                        用途：分页查询当前账号尚未撤销（status=active）的成员查看授权；
                        data.items[].grantId 可直接用于 M1-A03 撤销。
                        调用方：仅 APP（APP session token）；云台 → 403 CALLER_NOT_ALLOWED。
                        关键规则：只返回 active 授权，授权不自动过期（无过期列）；不提供全库成员检索；
                        空列表为 items=[]；排序 created_at DESC, id DESC。GET 无副作用。
                        分页：limit 默认 20、上限 100；cursor 为不透明 keyset 游标，绑定 accountId 筛选摘要，
                        非法或跨账号游标 → 400 INVALID_INPUT；nextCursor 为 null 表示无后续页（字段保留不省略）。
                        字段：items[].grantId/memberId 为 UUID 字符串；grantedAt 为 RFC3339 UTC 时间。
                        错误处理：INVALID_INPUT 修正 limit/cursor 后重试；AUTH_REQUIRED/SESSION_INVALID →
                        重新登录；DEPENDENCY_* 受限退避。契约过声明：RESOURCE_NOT_VISIBLE 在当前列表实现中不触发，保留。
                        """,
                        List.of(
                                query("limit", "可选，整数，分页大小；默认 20、上限 100；越界 → 400 INVALID_INPUT。", "20"),
                                query("cursor", "可选，字符串，不透明 keyset 游标（URL-safe Base64），绑定账号筛选摘要；"
                                        + "原样回传上一页 nextCursor；缺省表示第一页；非法/跨账号 → 400 INVALID_INPUT。")),
                        List.of(),
                        null,
                        null,
                        List.of(ApiDocEntry.SuccessDoc.jsonList("200",
                                "列表页：data.items[].grantId 可用于 M1-A03 撤销；空列表为 items=[]；"
                                        + "nextCursor=null 表示无后续页",
                                MemberAccessGrantService.MemberAccessGrantListItem.class)),
                        List.of(ErrorCode.INVALID_INPUT, ErrorCode.AUTH_REQUIRED,
                                ErrorCode.SESSION_INVALID, ErrorCode.CALLER_NOT_ALLOWED,
                                ErrorCode.RESOURCE_NOT_VISIBLE, ErrorCode.RATE_LIMITED,
                                ErrorCode.DEPENDENCY_UNAVAILABLE, ErrorCode.DEPENDENCY_TIMEOUT,
                                ErrorCode.NOT_IMPLEMENTED))),

                // ---------------------------------------------------------- M1-A03
                Map.entry("DELETE /api/v1/me/member-access-grants/{grantId}", new ApiDocEntry(
                        TAG_GRANT,
                        "撤销当前账号对某成员的查看授权",
                        """
                        用途：撤销当前账号与某成员的查看授权（active→revoked，保留行绝不删除）。
                        调用方：仅 APP 且为该 grant 所属账号；云台 → 403 CALLER_NOT_ALLOWED。
                        成功：204 无响应体（requestId 见 X-Request-Id 头），不使用统一成功信封。
                        关键规则：只撤查看关联，不删除成员/人脸档案/报告/护理记录，也不向微晶发送停止指令；
                        撤销后该账号查询该成员资料返回 404 RESOURCE_NOT_VISIBLE；撤销不复活——旧 M1-A01 请求重放仍
                        403 GRANT_REVOKED，重新授权需新人脸请求。
                        幂等语义：Idempotency-Key 必填；重复撤销（同键重放）→ 204 且不再写、revoked_at 不变；
                        已撤销的 grant 再次撤销 → 仍 204；不存在/他人 grant → 404 RESOURCE_NOT_VISIBLE（不可区分存在性）。
                        错误处理：RESOURCE_NOT_VISIBLE 不要换 grantId 探测；DEPENDENCY_* 受限退避重试。
                        """,
                        List.of(
                                path("grantId", "必填，路径参数，UUID 字符串（T02.id，即 M1-A02 列表中的 grantId）。",
                                        "99999999-9999-4999-8999-999999999999"),
                                idempotencyKey("revoke-grant-20260913-0001")),
                        List.of(),
                        null,
                        null,
                        List.of(ApiDocEntry.SuccessDoc.noContent("204",
                                "撤销成功且无响应体；重复撤销仍 204；requestId 见 X-Request-Id 头。")),
                        List.of(ErrorCode.INVALID_INPUT, ErrorCode.AUTH_REQUIRED,
                                ErrorCode.SESSION_INVALID, ErrorCode.CALLER_NOT_ALLOWED,
                                ErrorCode.RESOURCE_NOT_VISIBLE, ErrorCode.IDEMPOTENCY_CONTENT_CONFLICT,
                                ErrorCode.REQUEST_IN_PROGRESS, ErrorCode.RATE_LIMITED,
                                ErrorCode.DEPENDENCY_UNAVAILABLE, ErrorCode.DEPENDENCY_TIMEOUT,
                                ErrorCode.NOT_IMPLEMENTED))),

                // ---------------------------------------------------------- M2-A02
                Map.entry("POST /api/v1/gimbals/{gimbalId}/heartbeats", new ApiDocEntry(
                        TAG_DEVICE,
                        "云台上报心跳与已知工作状态",
                        """
                        用途：已认证云台上报心跳与已知工作状态（在线保活 + 序号化观察）；9/13 硬件联调第二优先端点。
                        调用方：仅云台（Bearer = gimbal device session token）；APP → 403 CALLER_NOT_ALLOWED；
                        gimbalId 与 token 主体不符或云台不存在 → 404 RESOURCE_NOT_VISIBLE（不可区分）。
                        去重与顺序：不使用 Idempotency-Key，改由 body 内 observationEpoch（1—128 字符非空，同一
                        generation 内不得更换）+ observationSeq（无符号 bigint 十进制字符串，同 generation 同 epoch 内
                        必须严格递增）去重排序。服务端维护会话代次表：新连接（首次/凭据推进/服务端首次见此 session）
                        接受并重置基准；已被更高代次取代的旧连接一律拒绝；表满且 session 从未见过则 fail closed。
                        accepted=false 时不更新 last_seen_at、不递增 status_revision、不覆盖观察。
                        契约 C25（须冻结/披露）：APP/云台须跨登录、token refresh 与进程重启持久化 observationEpoch 与
                        每微晶单调 observationSeq；重启后不得把 seq 归 1、不得自行更换 epoch，否则该次上报 accepted=false。
                        状态与副作用：powerState 枚举 awake|asleep；observedAt 为 RFC3339 UTC；可选 taskId/executionId 仅作
                        观察写入 task_ref/execution_ref，绝不移动 current_assessment 指针、不累计次数、不释放占用、不建执行。
                        status_revision 仅在 connection_status 由 unknown/offline → online 时 +1；本端点从不写 offline
                        （离线判定归扫描器）。重复旧心跳不延长在线时间、不覆盖新状态。
                        契约过声明（如实标注）：本端点契约声明 TASK_REPLACED，但 GimbalHeartbeatService 明确不使用该码
                        （taskId/executionId 与当前指针不符也不拒绝）；为与契约 x-error-codes 保持一致而保留，当前实现不触发。
                        错误处理：INVALID_INPUT（含 observationSeq 越界）修正后重试；SESSION_INVALID 凭据代次已变 →
                        重新握手；RESOURCE_NOT_VISIBLE 不换 ID 探测；DEPENDENCY_* 受限退避重试。
                        """,
                        List.of(gimbalIdPath()),
                        List.of(),
                        null,
                        "心跳请求体：observationEpoch + observationSeq（去重/顺序依据）、observedAt、powerState"
                                + "（awake|asleep）为必填；taskId/executionId/incidents 可选。",
                        List.of(ApiDocEntry.SuccessDoc.json("200",
                                "接收确认 + 后端记录时间；accepted 可为 false（旧序号仍确认收到）",
                                DeviceDtos.HeartbeatAck.class)),
                        List.of(ErrorCode.INVALID_INPUT, ErrorCode.AUTH_REQUIRED,
                                ErrorCode.SESSION_INVALID, ErrorCode.CALLER_NOT_ALLOWED,
                                ErrorCode.RESOURCE_NOT_VISIBLE, ErrorCode.TASK_REPLACED,
                                ErrorCode.RATE_LIMITED, ErrorCode.DEPENDENCY_UNAVAILABLE,
                                ErrorCode.DEPENDENCY_TIMEOUT, ErrorCode.NOT_IMPLEMENTED))),

                // ---------------------------------------------------------- M2-A03
                Map.entry("GET /api/v1/gimbals/{gimbalId}/status", new ApiDocEntry(
                        TAG_DEVICE,
                        "查询云台已知连接与工作状态",
                        """
                        用途：查询云台已知状态投影（连接状态、电源状态、最后在线时间、是否过期、状态代次、活动异常摘要）。
                        调用方：绑定该云台的账号（APP session token）或该云台自身（gimbal device session token）均可；
                        其他账号/云台/不存在统一 404 RESOURCE_NOT_VISIBLE（不可区分）。
                        关键规则：T03 单表读、GET 无副作用（不写库、不递增 revision、不触发扫描）；云台离线不代表微晶停止；
                        isStale=true 时不得伪装成实时状态；首次 unknown 不得解释为“刚离线”（离线语义归扫描器）。
                        字段：connectionStatus 实现取值 unknown/online/offline，但契约标注编码待定（x-detail: skeleton），
                        联调以服务端实际返回为准；powerState 透传最近一次心跳值，可能为 null（从未心跳）；lastSeenAt 为 null
                        表示从未心跳；isStale = last_seen_at 为空或距今超过 staleness 阈值（默认 300 秒）；
                        statusRevision 为无符号 bigint 十进制字符串；incidents 仅投影 active episode。
                        错误处理：RESOURCE_NOT_VISIBLE 不换 ID 探测；DEPENDENCY_* 受限退避重试。
                        """,
                        List.of(gimbalIdPath()),
                        List.of(),
                        null,
                        null,
                        List.of(ApiDocEntry.SuccessDoc.json("200",
                                "已知状态投影（不伪装成实时；isStale=true 表示过期或从未心跳）",
                                DeviceDtos.StatusView.class)),
                        List.of(ErrorCode.AUTH_REQUIRED, ErrorCode.SESSION_INVALID,
                                ErrorCode.CALLER_NOT_ALLOWED, ErrorCode.RESOURCE_NOT_VISIBLE,
                                ErrorCode.RATE_LIMITED, ErrorCode.DEPENDENCY_UNAVAILABLE,
                                ErrorCode.DEPENDENCY_TIMEOUT, ErrorCode.NOT_IMPLEMENTED))),

                // ---------------------------------------------------------- M2-A04
                Map.entry("POST /api/v1/microcrystal-observations", new ApiDocEntry(
                        TAG_DEVICE,
                        "登记已连接微晶的能力与实际状态观察",
                        """
                        用途：登记已连接微晶（T04）的能力包与本次实际状态观察；登记不等于首次绑定授权。
                        调用方：APP 或云台均可（各自 session token）。observer 身份只取自 token
                        （APP = account:installation 稳定 family；GIMBAL = gimbalId），绝不取请求体。
                        请求：microcrystalSerial 1—128 字符；connectionProof ≤8192 字符（绑定控制端 + 微晶 + 当前连接，
                        不接受仅序列号）；capabilities 必含 schemaVersion（JSON 整数 ≥1）与 revision（无符号 bigint 十进制
                        字符串），其余键透传持久化；observationEpoch 1—128 字符；observationSeq 为无符号 bigint 十进制字符串；
                        observedAt 为 RFC3339 UTC；state 不透明透传。
                        幂等语义：Idempotency-Key 必填（1—128 字符）；同键同内容重放返回原受理结果且 meta.replayed=true；
                        同键异内容 409 IDEMPOTENCY_CONTENT_CONFLICT；处理中 409 REQUEST_IN_PROGRESS。同一能力版本重复上报
                        不重复触发方案生成；accepted=false（旧 generation/seq）不覆盖已登记能力。
                        顺序：来源类型变化（APP↔云台/首次观察）重置代次并 generation=1；同一 family 内 epoch 一致且 seq 严格更大，
                        旧 generation 一律拒绝；APP 须跨登录/refresh/重启持久化 epoch + 单调 seq（契约 C25）。
                        禁止：不得以观察抢占/改变 T07 占用、不累计次数、不改 care_executions、不创建异步任务；
                        请求体不得覆盖他人归属。
                        错误处理：UNSUPPORTED_CONTRACT（connectionProof 版本不支持）；CALLER_NOT_ALLOWED（证明无法验证）；
                        已被他人观察 → 404 RESOURCE_NOT_VISIBLE（不可区分）；INVALID_INPUT 修正后重试；DEPENDENCY_* 受限退避。
                        未冻结：能力参数名/单位/范围与 state 结构必须来自已验证微晶协议（契约 x-detail: skeleton）。
                        """,
                        List.of(idempotencyKey("microcrystal-obs-20260913-0001")),
                        List.of(),
                        null,
                        "观察请求体：microcrystalSerial、connectionProof、capabilities（必含 schemaVersion/revision）、"
                                + "observationEpoch、observationSeq、observedAt、state（均必填；capabilities/state 结构见自由结构说明）。",
                        List.of(ApiDocEntry.SuccessDoc.json("200",
                                "登记受理；accepted=false 表示旧 generation/seq（能力不被覆盖），capabilityRevision 为当前已登记 revision",
                                DeviceDtos.MicrocrystalObservationAck.class)),
                        List.of(ErrorCode.INVALID_INPUT, ErrorCode.AUTH_REQUIRED,
                                ErrorCode.SESSION_INVALID, ErrorCode.CALLER_NOT_ALLOWED,
                                ErrorCode.RESOURCE_NOT_VISIBLE, ErrorCode.IDEMPOTENCY_CONTENT_CONFLICT,
                                ErrorCode.REQUEST_IN_PROGRESS, ErrorCode.UNSUPPORTED_CONTRACT,
                                ErrorCode.RATE_LIMITED, ErrorCode.DEPENDENCY_UNAVAILABLE,
                                ErrorCode.DEPENDENCY_TIMEOUT, ErrorCode.NOT_IMPLEMENTED))),

                // ---------------------------------------------------------- M2-A05
                Map.entry("GET /api/v1/microcrystals/{microcrystalId}/capabilities", new ApiDocEntry(
                        TAG_DEVICE,
                        "读取后端已登记的微晶能力",
                        """
                        用途：读取 T04 中已登记的微晶能力（DB JSONB 原样投影）。
                        调用方：APP 或云台（各自 session token）；携带合法 X-Connection-Proof 或已验证连接上下文。
                        关键规则：X-Connection-Proof 非必填——缺失时按“最近一次观察 observer_ref 是否与当前主体一致”推定：
                        匹配则放行；从未被观察 → 403 CALLER_NOT_ALLOWED（无上下文可推定）；已被他人观察 → 404
                        RESOURCE_NOT_VISIBLE（不可区分）；证明格式有效但绑定另一微晶 → 404。能力存在不意味着微晶空闲或
                        现场就绪（占用在执行准入时检查）。GET 无副作用。
                        字段：capabilities 为 DB JSONB 原样（固定含 schema_version + revision，其余为上报透传的自由键，
                        见自由结构说明）；capabilityRevision 无 revision 时为 "0"；observedAt/receivedAt 可空；
                        isStale 由 received_at 与 staleness 阈值（默认 300 秒）判定。
                        未冻结：连接证明协议、能力参数名/单位/范围待定（契约 x-detail: skeleton）。
                        错误处理：CALLER_NOT_ALLOWED 补合法连接证明后重试；RESOURCE_NOT_VISIBLE 不换 ID 探测。
                        """,
                        List.of(
                                path("microcrystalId", "必填，路径参数，UUID 字符串（T04.id），微晶引用。",
                                        "77777777-7777-4777-8777-777777777777"),
                                ApiDocEntry.ParamDoc.of("X-Connection-Proof", "header",
                                        "可选，字符串，连接证明（绑定控制端 + 微晶 + 当前连接）；缺失时按最近一次观察主体推定"
                                                + "（匹配放行/从未观察 403/已被他人观察 404）。具体协议由设备团队冻结前为开发建议。")),
                        List.of(),
                        null,
                        null,
                        List.of(ApiDocEntry.SuccessDoc.json("200",
                                "已登记能力（DB JSONB 原样；能力存在不代表微晶空闲或现场就绪）",
                                DeviceDtos.CapabilitiesView.class)),
                        List.of(ErrorCode.AUTH_REQUIRED, ErrorCode.SESSION_INVALID,
                                ErrorCode.CALLER_NOT_ALLOWED, ErrorCode.RESOURCE_NOT_VISIBLE,
                                ErrorCode.RATE_LIMITED, ErrorCode.DEPENDENCY_UNAVAILABLE,
                                ErrorCode.DEPENDENCY_TIMEOUT, ErrorCode.NOT_IMPLEMENTED))),

                // ---------------------------------------------------------- M2-A06
                Map.entry("PUT /api/v1/me/gimbal-bindings/{gimbalId}", new ApiDocEntry(
                        TAG_DEVICE,
                        "用户主动绑定云台到当前账号",
                        """
                        用途：已登录且正在协助该云台联网的 APP，用户主动点击后将云台绑定到当前账号。
                        调用方：仅 APP（Bearer + 可验证 pairingProof）；云台 → 403 CALLER_NOT_ALLOWED。
                        调用顺序：建议先 GET /api/v1/gimbals/{gimbalId}/binding-status（M2-A07）→ 本端点绑定 →
                        PUT /api/v1/me/notification-destinations/{installationId}（M5-A01）登记通知目标。
                        关键规则：配网不自动绑定；原子校验“未绑定或已绑定本人”，绝不覆盖他人（BOUND_TO_OTHER）；
                        相同账号同代次重复绑定幂等（不写库、不递增 binding_revision）；真实绑定使 binding_revision +1。
                        云台绑定只决定异常通知账号，不授予成员资料查看权（D01-2）。
                        请求：expectedBindingRevision 为无符号 bigint 十进制字符串（乐观并发基线；与当前不符 → 409
                        BINDING_CHANGED，details.currentBindingRevision 为当前值）；pairingProof ≤8192 字符，由
                        PairingProofVerifier 校验（绑定云台 + 账号/安装 + nonce + 有效期 + 签名；缺失/畸形 → 400，
                        验证失败 → 403）。
                        幂等语义：Idempotency-Key 必填；同键同内容重放按当前 T03 状态投影（若期间已被他人绑定则 404，
                        绝不谎报 self）；同键异内容 409 IDEMPOTENCY_CONTENT_CONFLICT；处理中 409 REQUEST_IN_PROGRESS。
                        错误处理：BINDING_CHANGED 刷新当前绑定状态后按最新代次重试；BOUND_TO_OTHER 绝不覆盖，由当前
                        绑定方先解绑；RESOURCE_NOT_VISIBLE 不换 ID 探测；DEPENDENCY_* 受限退避。
                        未冻结：pairingProof 具体协议（签名算法/有效期/nonce）待设备团队冻结。
                        """,
                        List.of(
                                gimbalIdPath(),
                                idempotencyKey("bind-gimbal-20260913-0001")),
                        List.of(),
                        null,
                        "绑定请求体：expectedBindingRevision（bigint 十进制字符串，首次为 0）+ pairingProof"
                                + "（可验证配对证明，格式待设备协议）。",
                        List.of(ApiDocEntry.SuccessDoc.json("200",
                                "绑定关系（bindingStatus=self；已属本人且代次相符时不重复写、不递增代次）",
                                DeviceDtos.BindingResultView.class)),
                        List.of(ErrorCode.INVALID_INPUT, ErrorCode.AUTH_REQUIRED,
                                ErrorCode.SESSION_INVALID, ErrorCode.CALLER_NOT_ALLOWED,
                                ErrorCode.RESOURCE_NOT_VISIBLE, ErrorCode.BOUND_TO_OTHER,
                                ErrorCode.BINDING_CHANGED, ErrorCode.IDEMPOTENCY_CONTENT_CONFLICT,
                                ErrorCode.REQUEST_IN_PROGRESS, ErrorCode.RATE_LIMITED,
                                ErrorCode.DEPENDENCY_UNAVAILABLE, ErrorCode.DEPENDENCY_TIMEOUT,
                                ErrorCode.NOT_IMPLEMENTED))),

                // ---------------------------------------------------------- M2-A07
                Map.entry("GET /api/v1/gimbals/{gimbalId}/binding-status", new ApiDocEntry(
                        TAG_DEVICE,
                        "配网时查询云台绑定状态",
                        """
                        用途：配网界面决定是否显示绑定按钮：返回 unbound/self/other 三态 + 当前 bindingRevision。
                        调用方：仅 APP（Bearer + 请求头配对证明）。
                        关键规则：X-Pairing-Proof 必填；缺失/空白 → 400 INVALID_INPUT；非空证明的任何验证失败统一
                        403 CALLER_NOT_ALLOWED（契约只声明 400/403，无“结构非法”分支）。本端点不建立绑定、不能仅凭任意
                        云台 ID 探查；不返回其他账号姓名/联系方式/账号 ID；云台不存在 → 404 RESOURCE_NOT_VISIBLE。
                        字段：bindingStatus 为 unbound/self/other；bindingRevision 为无符号 bigint 十进制字符串。GET 无副作用。
                        错误处理：CALLER_NOT_ALLOWED 获取本次合法配对上下文后重试（生成文档标 required=false，控制器
                        手工读取；契约要求必填，故文档覆盖为 required=true，缺失实际返回 400）；RESOURCE_NOT_VISIBLE 不换 ID 探测。
                        """,
                        List.of(
                                gimbalIdPath(),
                                requiredHeader("X-Pairing-Proof",
                                        "必填，字符串，本次合法配对上下文证明（绑定云台 + 账号/安装 + purpose + nonce + "
                                                + "有效期 + 可验证签名）；缺失/空白 → 400 INVALID_INPUT，验证失败 → 403。"
                                                + "头名与具体协议由设备团队冻结前为开发建议。",
                                        "PAIRING-PROOF-PLACEHOLDER")),
                        List.of(),
                        null,
                        null,
                        List.of(ApiDocEntry.SuccessDoc.json("200",
                                "unbound / self / other 三态 + 当前绑定代次",
                                DeviceDtos.BindingStatusView.class)),
                        List.of(ErrorCode.INVALID_INPUT, ErrorCode.AUTH_REQUIRED,
                                ErrorCode.SESSION_INVALID, ErrorCode.CALLER_NOT_ALLOWED,
                                ErrorCode.RESOURCE_NOT_VISIBLE, ErrorCode.RATE_LIMITED,
                                ErrorCode.DEPENDENCY_UNAVAILABLE, ErrorCode.DEPENDENCY_TIMEOUT,
                                ErrorCode.NOT_IMPLEMENTED))),

                // ---------------------------------------------------------- M2-A08
                Map.entry("DELETE /api/v1/me/gimbal-bindings/{gimbalId}", new ApiDocEntry(
                        TAG_DEVICE,
                        "原绑定账号解除云台绑定",
                        """
                        用途：当前绑定所属账号解除云台绑定。
                        调用方：仅 APP 且为当前绑定账号；云台 → 403 CALLER_NOT_ALLOWED。
                        成功：204 无响应体（requestId 见 X-Request-Id 头），不使用统一成功信封。
                        关键规则：If-Match 形如 "binding-{无符号十进制 bigint}"，前缀 binding- 必须、双引号可选，格式非法
                        （缺前缀/非十进制/溢出）→ 400 INVALID_INPUT。云台不存在或未绑定 → 一律 404 RESOURCE_NOT_VISIBLE
                        （不可区分存在性：在 revision 判断之前统一 404，无论 If-Match 取何值）。他人绑定时：If-Match 与当前
                        代次相符 → 409 BINDING_CHANGED（不解除他人绑定）；否则 404。
                        幂等语义：Idempotency-Key 必填；真实解绑使 binding_revision +1；已解绑的原请求重放（同键）→ 204
                        且不递增代次；跨代次解绑 → 409 BINDING_CHANGED。旧解绑（旧 If-Match）绝不删除他人后来的新绑定。
                        副作用边界：解绑不撤销成员授权、不删报告/方案/记录、不改变云台当前任务、不发停止指令。
                        错误处理：BINDING_CHANGED 刷新状态后用最新代次重试；RESOURCE_NOT_VISIBLE 不换 ID 探测；DEPENDENCY_* 受限退避。
                        """,
                        List.of(
                                gimbalIdPath(),
                                ApiDocEntry.ParamDoc.of("If-Match", "header",
                                        "可选，字符串，建议携带 \"binding-{bindingRevision}\" 预期代次；前缀 binding- 必须，"
                                                + "双引号可选，非无符号十进制 bigint → 400 INVALID_INPUT。",
                                        "\"binding-1\""),
                                idempotencyKey("unbind-gimbal-20260913-0001")),
                        List.of(),
                        null,
                        null,
                        List.of(ApiDocEntry.SuccessDoc.noContent("204",
                                "解绑成功且无响应体；已解绑原请求重放仍 204 且不递增代次；requestId 见 X-Request-Id 头。")),
                        List.of(ErrorCode.INVALID_INPUT, ErrorCode.AUTH_REQUIRED,
                                ErrorCode.SESSION_INVALID, ErrorCode.CALLER_NOT_ALLOWED,
                                ErrorCode.RESOURCE_NOT_VISIBLE, ErrorCode.BINDING_CHANGED,
                                ErrorCode.IDEMPOTENCY_CONTENT_CONFLICT, ErrorCode.REQUEST_IN_PROGRESS,
                                ErrorCode.RATE_LIMITED, ErrorCode.DEPENDENCY_UNAVAILABLE,
                                ErrorCode.DEPENDENCY_TIMEOUT, ErrorCode.NOT_IMPLEMENTED))),

                // ---------------------------------------------------------- M5-A01
                Map.entry("PUT /api/v1/me/notification-destinations/{installationId}", new ApiDocEntry(
                        TAG_NOTIFY,
                        "登记本安装实例的推送投递目标",
                        """
                        用途：已登录 APP 登记本安装实例的推送投递目标（T09）；本接口只登记目标、不发送任何消息。
                        调用方：仅 APP（Bearer）；云台 → 403 CALLER_NOT_ALLOWED。路径 installationId 必须等于 token 主体
                        （principal.installationId），否则 403 CALLER_NOT_ALLOWED——不能仅凭 installationId 抢占或替他人登记；
                        路径空白/超 128 → 400 INVALID_INPUT。
                        请求：provider 1—64 字符；platform 当前仅 android（其他值 → 400 INVALID_INPUT）；registration 必须为
                        非空对象且 schema_version 为 JSON 整数（缺省服务端注入整数 1，显式非整数 → 400）；
                        expectedDestinationRevision 为无符号 bigint 十进制字符串。
                        代次规则：首次建 expected 必须为 "0"，destination_revision 首建即 1；内容变化、换号接管、相同内容但
                        会话引用变化（含 invalid 重新激活）各 +1，使旧会话的 T10 路由快照失配；仅“同会话且已 active”的纯
                        幂等重登记不递增代次。换号接管（installationId 属当前 token）接受 expected "0" 或当前值并 +1。
                        幂等语义：Idempotency-Key 必填（1—128 字符）；同键同内容重放返回原结果且 meta.replayed=true；
                        同键异内容 409 IDEMPOTENCY_CONTENT_CONFLICT；处理中 409 REQUEST_IN_PROGRESS。expected 不符 →
                        409 BINDING_CHANGED，details.currentDestinationRevision（只含当前代次，不泄漏其他账号信息）。
                        响应：只含 destinationId/destinationRevision/status，绝不回传完整推送 token/registration；
                        status 为 active|disabled|invalid（登出会置 invalid 并同事务递增代次）。全程 header Cache-Control: no-store。
                        未冻结：推送通道未选定，provider 取值与 registration 字段结构待定（契约 x-detail: skeleton）；
                        服务端不得据此发送消息。
                        错误处理：INVALID_INPUT 修正 platform/registration/installationId；BINDING_CHANGED 刷新当前代次后重试；
                        CALLER_NOT_ALLOWED 使用本会话绑定的 installationId。
                        """,
                        List.of(
                                path("installationId", "必填，路径参数，字符串，APP 安装实例 ID（客户端生成，1—128 字符）；"
                                        + "必须等于 token 主体绑定安装，否则 403 CALLER_NOT_ALLOWED。",
                                        "install-0000-0000-0000-000000000001"),
                                idempotencyKey("register-destination-20260913-0001")),
                        List.of(),
                        null,
                        "登记请求体：provider（1—64）+ platform=android + registration（非空对象，须含 schema_version，"
                                + "缺省服务端注入 1）+ expectedDestinationRevision（bigint 十进制字符串，首次 \"0\"）。",
                        List.of(ApiDocEntry.SuccessDoc.json("200",
                                "已登记的本人投递目标（仅 destinationId/destinationRevision/status，绝不回传完整推送 token）",
                                NotificationDestinationDtos.View.class)),
                        List.of(ErrorCode.INVALID_INPUT, ErrorCode.AUTH_REQUIRED,
                                ErrorCode.SESSION_INVALID, ErrorCode.CALLER_NOT_ALLOWED,
                                ErrorCode.RESOURCE_NOT_VISIBLE, ErrorCode.BINDING_CHANGED,
                                ErrorCode.IDEMPOTENCY_CONTENT_CONFLICT, ErrorCode.REQUEST_IN_PROGRESS,
                                ErrorCode.RATE_LIMITED, ErrorCode.DEPENDENCY_UNAVAILABLE,
                                ErrorCode.DEPENDENCY_TIMEOUT, ErrorCode.NOT_IMPLEMENTED))));
    }

    /**
     * 契约要求必填、但服务端以<strong>控制器手工严格校验</strong>（而非 Bean Validation 注解）
     * 实现的属性 ⇒ springdoc 推导出的 {@code required} 为空，此处按<strong>契约与服务端实际
     * 行为</strong>修正生成文档。
     *
     * <p>取证：{@code MemberAccessGrantController.java:162-163}（{@code metadata.capture} 必填）、
     * {@code :165}（{@code captureId} requireText 1-128）、{@code :166}（{@code clientContinuityId}
     * requireText 1-128）、{@code :167}（{@code consentEvidenceRef} requireText 1-128）、
     * {@code :168} 与 {@code :197-203}（{@code capturedAt} 必填且须为 RFC3339 时间戳）、
     * {@code :169-170}（{@code purpose} 须为 {@code grant}，缺失即不满足）；违规一律
     * 400 {@code INVALID_INPUT} 且带 {@code details.fields[{field,reason}]}（{@code :207-210}）。
     * {@code captureProofRef} 契约未要求必填，故不在此列。</p>
     *
     * <p><strong>这不是实现偏差</strong>：服务端确实强制，只是未用注解声明，故 springdoc 看不见。</p>
     */
    @Override
    public Map<String, Set<String>> requiredProperties() {
        return Map.of(
                "M1A01Metadata", Set.of("capture", "consentEvidenceRef"),
                "Capture", Set.of("captureId", "capturedAt", "clientContinuityId", "purpose"));
    }

    @Override
    public Map<String, Map<String, PropertyDoc>> propertyDocs() {
        return Map.ofEntries(

                Map.entry("BindingBody", Map.of(
                        "expectedBindingRevision", PropertyDoc.of(
                                "必填，字符串，客户端期望的云台当前绑定代次；无符号 bigint 十进制字符串"
                                        + "（pattern ^(0|[1-9][0-9]*)$），首次为 \"0\"；与当前不符 → 409 BINDING_CHANGED。",
                                "0"),
                        "pairingProof", PropertyDoc.of(
                                "必填，字符串，可验证配对证明（绑定云台 + 账号/安装实例 + purpose + nonce + 有效期 + 签名），"
                                        + "≤8192 字符；缺失/畸形 → 400，验证失败 → 403。格式待设备协议冻结。"))),

                Map.entry("HeartbeatBody", Map.of(
                        "observationEpoch", PropertyDoc.of(
                                "必填，字符串，本次连接会话内固定的观察 epoch，1—128 字符；同一 generation 内不得更换，"
                                        + "否则 accepted=false（契约 C25：须跨登录/refresh/重启持久化）。",
                                "epoch-0001"),
                        "observationSeq", PropertyDoc.of(
                                "必填，字符串，该 epoch 内的观察序号；无符号 bigint 十进制字符串"
                                        + "（pattern ^(0|[1-9][0-9]*)$），同 generation 同 epoch 内必须严格递增；"
                                        + "超出 bigint 范围 → 400 INVALID_INPUT。",
                                "1"),
                        "observedAt", dateTime(
                                "必填，RFC3339 UTC 时间字符串，云台侧观察时间。", "2026-09-13T08:30:00Z"),
                        "powerState", PropertyDoc.enumOf(
                                "必填，字符串，云台电源状态。",
                                List.of("awake", "asleep"), "awake"),
                        "taskId", PropertyDoc.of(
                                "可选，可空 UUID 字符串，云台自报当前测肤任务；仅写入 latest_observation.task_ref，"
                                        + "不移动 current_assessment 指针、不触发 TASK_REPLACED。",
                                "11111111-1111-4111-8111-111111111111"),
                        "executionId", PropertyDoc.of(
                                "可选，可空 UUID 字符串，云台自报当前护理执行；仅写入 latest_observation.execution_ref，"
                                        + "不累计完成次数、不释放占用。"),
                        "incidents", PropertyDoc.of(
                                "可选，数组，云台可检测并上报的异常；每元素结构与内部落库键见自由结构说明"
                                        + "（服务端只读取 code/state/cleared/severity/detail）。"))),

                Map.entry("HeartbeatAck", Map.of(
                        "accepted", PropertyDoc.of(
                                "布尔，本次心跳是否推进了后端状态；重复/旧序号返回 false，但仍确认收到"
                                        + "（不刷新 last_seen_at、不递增代次、不覆盖观察）。",
                                "true"),
                        "lastSeenAt", dateTime(
                                "RFC3339 UTC 时间字符串，后端记录的最后在线时间；accepted=false 时为已存在的旧值。",
                                "2026-09-13T08:30:00Z"),
                        "statusRevision", PropertyDoc.of(
                                "字符串，云台状态代次；无符号 bigint 十进制字符串，仅 connection_status 由"
                                        + " unknown/offline → online 时 +1。",
                                "1"),
                        "serverTime", dateTime(
                                "RFC3339 UTC 时间字符串，服务端当前时间，用于设备校时/对账。",
                                "2026-09-13T08:30:01Z"))),

                Map.entry("IncidentView", Map.of(
                        "incidentId", PropertyDoc.of(
                                "字符串，服务端稳定的异常 episode ID（UUID 格式）；同一 code 在 active 期间复用，"
                                        + "清除后再次出现会分配新 ID。",
                                "66666666-6666-4666-8666-666666666666"),
                        "code", PropertyDoc.of(
                                "字符串，异常码；本版本异常码枚举未冻结，取值由云台协议定义。"),
                        "severity", PropertyDoc.of(
                                "字符串，严重度；取值未冻结，服务端原样投影上报值。"),
                        "openedAt", dateTime(
                                "RFC3339 UTC 时间字符串，异常首次开启时间。", "2026-09-13T08:00:00Z"),
                        "lastReportedAt", dateTime(
                                "RFC3339 UTC 时间字符串，最近一次上报时间。", "2026-09-13T08:30:00Z"))),

                Map.entry("StatusView", Map.of(
                        "connectionStatus", PropertyDoc.enumOf(
                                "字符串，云台连接状态；实现取值 unknown/online/offline，但契约标注编码待定"
                                        + "（x-detail: skeleton），联调以服务端实际返回为准。",
                                List.of("unknown", "online", "offline"), "online"),
                        "powerState", PropertyDoc.enumOf(
                                "可空字符串，透传最近一次心跳的电源状态；从未心跳为 null。",
                                List.of("awake", "asleep"), "awake"),
                        "lastSeenAt", dateTime(
                                "可空字符串，RFC3339 UTC 最后在线时间；null 表示从未心跳。",
                                "2026-09-13T08:30:00Z"),
                        "isStale", PropertyDoc.of(
                                "布尔，状态是否过期/未知；last_seen_at 为空或距今超过 staleness 阈值"
                                        + "（默认 300 秒）为 true，不得伪装成实时。",
                                "false"),
                        "statusRevision", PropertyDoc.of(
                                "字符串，状态代次；无符号 bigint 十进制字符串，仅 unknown/offline → online 时 +1。",
                                "1"),
                        "incidents", PropertyDoc.of(
                                "数组，已知活动异常摘要（仅 active episode）；元素为 IncidentView。"))),

                Map.entry("MicrocrystalObservationBody", Map.of(
                        "microcrystalSerial", PropertyDoc.of(
                                "必填，字符串，微晶序列号，1—128 字符；服务端按 serial_no 唯一定位/登记 T04，"
                                        + "不创建新归属。",
                                "MC-DEMO-0001"),
                        "connectionProof", PropertyDoc.of(
                                "必填，字符串，绑定控制端 + 微晶 + 当前连接的证明（不接受仅序列号），≤8192 字符；"
                                        + "证明协议待设备团队冻结。"),
                        "capabilities", PropertyDoc.of(
                                "必填，对象，能力包；必含 schemaVersion（JSON 整数 ≥1）与 revision（无符号 bigint 十进制"
                                        + "字符串），其余键透传持久化；参数名/单位/范围未冻结。结构见自由结构说明。"),
                        "observationEpoch", PropertyDoc.of(
                                "必填，字符串，观察 epoch，1—128 字符；同一 generation 内不得更换"
                                        + "（契约 C25：须跨登录/refresh/重启持久化）。",
                                "obs-epoch-0001"),
                        "observationSeq", PropertyDoc.of(
                                "必填，字符串，该 epoch 内观察序号；无符号 bigint 十进制字符串，"
                                        + "同 generation 同 epoch 内严格递增。",
                                "1"),
                        "observedAt", dateTime(
                                "必填，RFC3339 UTC 时间字符串，微晶侧观察时间。", "2026-09-13T08:30:00Z"),
                        "state", PropertyDoc.of(
                                "必填，对象，客户端上报的微晶实际观察状态；不透明透传（结构待定），服务端不校验、"
                                        + "不据此抢占或改变执行占用。结构见自由结构说明。"))),

                Map.entry("MicrocrystalObservationAck", Map.of(
                        "microcrystalId", PropertyDoc.of(
                                "字符串，T04 微晶 ID（UUID 格式）。",
                                "77777777-7777-4777-8777-777777777777"),
                        "accepted", PropertyDoc.of(
                                "布尔，本次观察是否推进了已登记能力；旧 generation/seq 返回 false，能力不被覆盖。",
                                "true"),
                        "capabilityRevision", PropertyDoc.of(
                                "字符串，当前已登记能力的 revision（无符号 bigint 十进制字符串）；accepted=false 时为"
                                        + "既有值，无 revision 时为 \"0\"。",
                                "1"),
                        "receivedAt", dateTime(
                                "RFC3339 UTC 时间字符串，服务端接收时间。", "2026-09-13T08:30:01Z"))),

                Map.entry("CapabilitiesView", Map.of(
                        "capabilities", PropertyDoc.of(
                                "对象，T04 capabilities JSONB 原样投影；固定含 schema_version 与 revision，"
                                        + "其余为上报透传的自由键。结构见自由结构说明。"),
                        "capabilityRevision", PropertyDoc.of(
                                "字符串，当前能力 revision（无符号 bigint 十进制字符串）；无 revision 时为 \"0\"。",
                                "1"),
                        "observedAt", dateTime(
                                "可空字符串，RFC3339 UTC，最近一次观察的 observedAt；从未观察为 null。",
                                "2026-09-13T08:30:00Z"),
                        "receivedAt", dateTime(
                                "可空字符串，RFC3339 UTC，最近一次观察的服务端接收时间；从未观察为 null。",
                                "2026-09-13T08:30:01Z"),
                        "isStale", PropertyDoc.of(
                                "布尔，该能力是否过期；received_at 为空或距今超过 staleness 阈值（默认 300 秒）为 true。",
                                "false"))),

                Map.entry("BindingResultView", Map.of(
                        "bindingStatus", PropertyDoc.enumOf(
                                "字符串，绑定状态；本端点成功恒为 self。", List.of("self"), "self"),
                        "gimbalId", PropertyDoc.of(
                                "字符串，云台 ID（T03.id，UUID 格式）。",
                                "55555555-5555-4555-8555-555555555555"),
                        "bindingRevision", PropertyDoc.of(
                                "字符串，绑定代次；无符号 bigint 十进制字符串，真实绑定/解绑各 +1，"
                                        + "重复幂等绑定不递增。",
                                "1"),
                        "boundAt", dateTime(
                                "字符串，RFC3339 UTC 绑定时间。", "2026-09-13T08:00:00Z"))),

                Map.entry("BindingStatusView", Map.of(
                        "bindingStatus", PropertyDoc.enumOf(
                                "字符串，绑定状态三态：unbound 未绑定 / self 已绑定当前账号 / other 已绑定其他账号。",
                                List.of("unbound", "self", "other"), "unbound"),
                        "bindingRevision", PropertyDoc.of(
                                "字符串，当前绑定代次；无符号 bigint 十进制字符串，真实绑定/解绑各 +1。",
                                "0"))),

                Map.entry("Request", Map.of(
                        "provider", PropertyDoc.of(
                                "必填，字符串，推送通道提供方标识，1—64 字符；通道未选定，取值待定。",
                                "demo-push"),
                        "platform", PropertyDoc.enumOf(
                                "必填，字符串，目标平台；当前仅接受 android，其他值 → 400 INVALID_INPUT。",
                                List.of("android"), "android"),
                        "registration", PropertyDoc.of(
                                "必填，对象，通道目标资料；必须非空且含 schema_version（JSON 整数，缺省服务端注入 1），"
                                        + "其余字段属推送注册信息、通道未选定 ⇒ 未冻结。服务端绝不回传完整推送 token。"
                                        + "结构见自由结构说明。"),
                        "expectedDestinationRevision", PropertyDoc.of(
                                "必填，字符串，期望的目标代次；无符号 bigint 十进制字符串，首次建为 \"0\"，"
                                        + "与当前不符 → 409 BINDING_CHANGED（details.currentDestinationRevision）。",
                                "0"))),

                Map.entry("View", Map.of(
                        "destinationId", PropertyDoc.of(
                                "字符串，通知目标 ID（T09.id，UUID 格式）。",
                                "88888888-8888-4888-8888-888888888888"),
                        "destinationRevision", PropertyDoc.of(
                                "字符串，目标代次；无符号 bigint 十进制字符串，首建为 1，"
                                        + "内容变化/换号/会话引用变化/登出失效各 +1。",
                                "1"),
                        "status", PropertyDoc.enumOf(
                                "字符串，目标状态；登出会使本会话目标置 invalid 并递增代次。",
                                List.of("active", "disabled", "invalid"), "active"))),

                Map.entry("M1A01Metadata", Map.of(
                        "capture", PropertyDoc.of(
                                "必填，对象，本次人脸采集信息（见 Capture）。"),
                        "consentEvidenceRef", PropertyDoc.of(
                                "必填，字符串，知情同意证据引用，1—128 字符。",
                                "consent-demo-0001"))),

                Map.entry("Capture", Map.of(
                        "captureId", PropertyDoc.of(
                                "必填，字符串，采集标识，1—128 字符。", "capture-demo-0001"),
                        "capturedAt", dateTime(
                                "必填，字符串，RFC3339 时间戳（OffsetDateTime 解析），采集时间。",
                                "2026-09-13T08:30:00Z"),
                        "clientContinuityId", PropertyDoc.of(
                                "必填，字符串，客户端连续性标识，1—128 字符（人脸连续性/防重放关联）。",
                                "continuity-demo-0001"),
                        "purpose", PropertyDoc.enumOf(
                                "必填，字符串，采集用途；本端点必须为 grant，其他值 → 400 INVALID_INPUT。",
                                List.of("grant"), "grant"),
                        "captureProofRef", PropertyDoc.of(
                                "可选，字符串，采集证明引用；控制器未强制非空（长度校验上限 128）。"))),

                Map.entry("MemberAccessGrantResult", Map.of(
                        "grantId", PropertyDoc.of(
                                "字符串，成员查看授权关系 ID（T02.id，UUID 格式）；供 M1-A03 撤销。",
                                "99999999-9999-4999-8999-999999999999"),
                        "memberId", PropertyDoc.of(
                                "字符串，被授权查看的成员 ID（T01.id，UUID 格式）；不返回任何成员资料。",
                                "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"),
                        "status", PropertyDoc.enumOf(
                                "字符串，授权关系状态；本端点成功返回 active。", List.of("active"), "active"),
                        "grantedAt", dateTime(
                                "字符串，RFC3339 UTC 授权建立时间。", "2026-09-13T08:30:00Z"))),

                Map.entry("MemberAccessGrantListItem", Map.of(
                        "grantId", PropertyDoc.of(
                                "字符串，成员查看授权关系 ID（T02.id，UUID 格式）；可用于 M1-A03 撤销。",
                                "99999999-9999-4999-8999-999999999999"),
                        "memberId", PropertyDoc.of(
                                "字符串，成员 ID（T01.id，UUID 格式）。",
                                "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"),
                        "grantedAt", dateTime(
                                "字符串，RFC3339 UTC 授权建立时间。", "2026-09-13T08:30:00Z")))
        );
    }

    @Override
    public Map<String, FreeFormDoc> freeFormDocs() {
        return Map.ofEntries(

                // M2-A02 心跳异常数组
                Map.entry("HeartbeatBody.incidents", new FreeFormDoc(
                        """
                        云台异常上报数组：写入方为已认证云台（POST /api/v1/gimbals/{gimbalId}/heartbeats 请求体）。
                        每个元素是一次异常观察；服务端只读取 code/state/cleared/severity/detail 五个键做 episode 归并，
                        其余键被忽略。异常 episode 的内部落库键集 source/opened_at/last_reported_at/last_reported_seq/
                        resolved_at 属服务端内部，绝不外发（查询回包 IncidentView 只投影 incidentId/code/severity/
                        openedAt/lastReportedAt）。
                        幂等与顺序：由 observationEpoch/observationSeq 决定，重复旧序号 accepted=false 且不改变 episode；
                        同一 code 在 active 期间复用同一 incidentId，被报清除后再次出现分配新 incidentId。
                        """,
                        Map.of(
                                "code", "string，异常码；本版本枚举未冻结，须由云台协议定义（服务端按 code 归并 episode）。",
                                "state", "string，异常状态；cleared/resolved 视为已清除，其余视为活动（取值未冻结）。",
                                "cleared", "boolean，true 表示本条上报清除该 code 的既有 episode（与 state=cleared 等价）。",
                                "severity", "string，严重度；取值未冻结，服务端原样写入内部 episode。",
                                "detail", "object，异常附加细节；服务端原样保留在内部 episode 的 detail 键，查询投影不外发。"),
                        true,
                        "服务端只认上述 5 个键并忽略未知键（前向兼容），客户端必须容忍未来新增键；"
                                + "异常码/严重度枚举与上报频率未冻结（依据契约 GimbalHeartbeatRequest.incidents 的 "
                                + "x-detail: skeleton、GimbalHeartbeatService 只读取 code/state/cleared/severity/detail）。",
                        """
                        [{"code":"demo_code","state":"active","severity":"warning","detail":{}}]
                        """)),

                // M2-A04 capabilities
                Map.entry("MicrocrystalObservationBody.capabilities", new FreeFormDoc(
                        """
                        微晶能力上报（写入方：APP 或云台，POST /api/v1/microcrystal-observations 请求体）。
                        服务端要求必含 schemaVersion（JSON 整数 ≥1）与 revision（无符号 bigint 十进制字符串）；
                        其余键原样透传并持久化为 T04 capabilities JSONB（内部列名 schema_version/revision）。
                        同能力版本重复上报不重复触发方案生成；能力参数名/单位/范围未冻结，须来自已验证的微晶协议
                        （契约 x-detail: skeleton）。
                        """,
                        Map.of(
                                "schemaVersion", "integer，能力结构版本；必须为 JSON 整数且 ≥1，非整数/小于 1 → 400 INVALID_INPUT。",
                                "revision", "string，能力版本号；无符号 bigint 十进制字符串（pattern ^(0|[1-9][0-9]*)$），"
                                        + "非字符串或非法 → 400 INVALID_INPUT。"),
                        true,
                        "schemaVersion/revision 为封闭必填键（服务端强校验）；其余键开放透传、客户端必须容忍未来新增键。"
                                + "参数名/单位/范围未冻结，须来自已验证微晶协议（依据契约 "
                                + "MicrocrystalObservationRequest.capabilities additionalProperties=true 且 x-detail: skeleton）。",
                        """
                        {"schemaVersion":1,"revision":"1"}
                        """)),

                // M2-A04 state（不透明透传）
                Map.entry("MicrocrystalObservationBody.state", new FreeFormDoc(
                        """
                        客户端上报的微晶实际观察状态；服务端不透明透传——原样写入 T04 latest_observation.state，
                        不校验、不据此抢占或改变执行占用、不累计次数。结构未冻结（契约 MicrocrystalObservationRequest.state
                        标注“结构待定”，x-detail: skeleton）。
                        """,
                        Map.of(),
                        true,
                        "服务端不解析 state 内容，全部键透传（additionalProperties=true）；该字段为不透明对象、"
                                + "结构未冻结，已知键集合为空，客户端不得依赖任何具体键名，新增键必须被容忍。"
                                + "正式键集/单位/范围以已验证微晶协议为准（依据契约 MicrocrystalObservationRequest.state "
                                + "的“结构待定”与 x-detail: skeleton；当前实现原样写入 T04 latest_observation.state）。",
                        null)),

                // M2-A05 CapabilitiesView.capabilities
                Map.entry("CapabilitiesView.capabilities", new FreeFormDoc(
                        """
                        T04 capabilities JSONB 原样投影（读取方：APP 或云台，
                        GET /api/v1/microcrystals/{microcrystalId}/capabilities）。
                        DB 内固定包含 schema_version 与 revision，其余为上报时透传的自由键。
                        能力存在不意味着微晶空闲或现场就绪；占用在执行准入时检查。
                        """,
                        Map.of(
                                "schema_version", "integer，能力结构版本（DB JSONB 列名用下划线 schema_version，"
                                        + "与上报 camelCase schemaVersion 对应）；由服务端从已校验的请求 schemaVersion "
                                        + "映射写入（整数 ≥1，可大于 1），不是固定常量。",
                                "revision", "string，能力版本号；无符号 bigint 十进制字符串（与上报 revision 对应）。"),
                        true,
                        "schema_version/revision 为服务端写入的固定键；其余键来自上报透传，属未冻结微晶协议，"
                                + "客户端必须容忍新增键。能力参数名/单位/范围未冻结（依据 "
                                + "MicrocrystalService.buildCapabilities 与 T04 capabilities CHECK 约束、契约 "
                                + "MicrocrystalCapabilitiesView 的 x-detail: skeleton）。",
                        """
                        {"schema_version":1,"revision":"1"}
                        """)),

                // M5-A01 registration
                Map.entry("Request.registration", new FreeFormDoc(
                        """
                        推送目标注册资料（写入方：已登录 APP，
                        PUT /api/v1/me/notification-destinations/{installationId} 请求体）。
                        必须为非空对象；须含 schema_version（JSON 整数），缺省由服务端注入整数 1，显式非 JSON 整数 → 400。
                        其余为推送通道的注册字段，通道未选定 ⇒ 结构未冻结。
                        服务端绝不回传完整推送 token/registration（响应 View 只含 destinationId/destinationRevision/status）。
                        """,
                        Map.of(
                                "schema_version", "integer，注册资料结构版本；缺省由服务端注入 1，"
                                        + "显式给出时必须为 JSON 整数，否则 400 INVALID_INPUT。"),
                        true,
                        "registration 为开放对象（additionalProperties=true）：schema_version 由服务端保证，其余键为通道"
                                + "注册字段、通道未选定 ⇒ 未冻结；客户端必须容忍新增键，正式键集以选定推送通道协议为准。"
                                + "内部推送 token 绝不回传、绝不写日志（依据契约 NotificationDestinationRequest 的 "
                                + "x-detail: skeleton、NotificationDestinationService.normalizeRegistration）。",
                        """
                        {"schema_version":1}
                        """))
        );
    }

    // ------------------------------------------------------------------ helpers

    private static ApiDocEntry.ParamDoc idempotencyKey(String example) {
        return new ApiDocEntry.ParamDoc("Idempotency-Key", "header",
                "必填，字符串，1—128 字符；T13 幂等键（principal_type+principal_id+operation+idempotency_key）。"
                        + "同逻辑重试保持键与内容不变；更换业务内容使用新键。生成文档标 required=false（控制器手工读取），"
                        + "实际缺失/空白/超长 → 400 INVALID_INPUT。",
                example, Boolean.TRUE);
    }

    private static ApiDocEntry.ParamDoc gimbalIdPath() {
        return ApiDocEntry.ParamDoc.of("gimbalId", "path",
                "必填，路径参数，UUID 字符串（T03.id），云台引用。",
                "55555555-5555-4555-8555-555555555555");
    }

    private static ApiDocEntry.ParamDoc path(String name, String description, String example) {
        return ApiDocEntry.ParamDoc.of(name, "path", description, example);
    }

    private static ApiDocEntry.ParamDoc query(String name, String description, String example) {
        return ApiDocEntry.ParamDoc.of(name, "query", description, example);
    }

    private static ApiDocEntry.ParamDoc query(String name, String description) {
        return ApiDocEntry.ParamDoc.of(name, "query", description);
    }

    private static ApiDocEntry.ParamDoc requiredHeader(String name, String description, String example) {
        return new ApiDocEntry.ParamDoc(name, "header", description, example, Boolean.TRUE);
    }

    private static PropertyDoc dateTime(String description, String example) {
        return new PropertyDoc(description, null, null, example, "date-time");
    }
}
