package cn.yuanxin.mvp.web.docs.catalog;

import cn.yuanxin.mvp.web.auth.AuthController;
import cn.yuanxin.mvp.web.auth.GimbalSessionController;
import cn.yuanxin.mvp.web.error.ErrorCode;
import cn.yuanxin.mvp.web.system.SystemEchoController;
import io.swagger.v3.oas.models.tags.Tag;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.context.annotation.Profile;
import org.springframework.stereotype.Component;

import java.util.List;
import java.util.Map;

/**
 * Foundation 域联调文档目录：手机号账号与会话、云台设备会话握手、受控媒体二进制读取、
 * system.echo 跨语言验收桥，共 8 个操作。
 *
 * <p>权威来源：{@code backend/contracts/openapi/openapi.yaml} 的 f01—f07 与 M2-A01
 * （中文 summary/description/x-error-codes）、{@code backend/doc/后端详细设计-V1-MVP.md}
 * 的 DD 4.1、{@code backend/doc/技术架构设计-V1-MVP.md} 的认证/HTTP 处理顺序、
 * {@code backend/contracts/decisions-notes.md} #8/#10/#11，以及各控制器/DTO 源码。
 * 未冻结项（真实会话提供方、token 有效期、设备签名与凭据格式、安装绑定材料结构）
 * 一律显式标注“待定/未冻结”，不编造语义。</p>
 *
 * <p>本类只写文档内容，不触碰任何控制器/DTO/业务代码。</p>
 */
@Component
@Profile({"dev", "test"})
@ConditionalOnProperty(name = "springdoc.api-docs.enabled", havingValue = "true")
public class FoundationApiDocs implements ApiDocsCatalog {

    /** 手机号账号与会话、云台设备会话等认证握手。 */
    private static final String TAG_AUTH = "基础认证";
    /** 受控媒体对象二进制读取。 */
    private static final String TAG_MEDIA = "基础媒体";
    /** 跨语言端到端验收桥（system.echo 任务）。 */
    private static final String TAG_SYSTEM = "基础系统";
    /** 云台设备上电/重连的设备会话握手（M2-A01，基础认证实现）。 */
    private static final String TAG_GIMBAL_SESSION = "云台会话";

    @Override
    public String domain() {
        return "foundation";
    }

    @Override
    public List<Tag> tags() {
        return List.of(
                new Tag().name(TAG_AUTH)
                        .description("手机号账号与会话基础协议：短信挑战、会话签发/刷新/撤销。"
                                + "公开端点用提供方凭据证明，受保护端点用 Bearer session token。"),
                new Tag().name(TAG_MEDIA)
                        .description("受控媒体对象二进制读取：逐次鉴权、no-store、nosniff、"
                                + "不可见与不存在同 404 RESOURCE_NOT_VISIBLE。"),
                new Tag().name(TAG_SYSTEM)
                        .description("跨语言端到端验收桥：system.echo 异步任务的入队与只读查询，"
                                + "用于验证 Java/Python 任务交接与创建者归属。"),
                new Tag().name(TAG_GIMBAL_SESSION)
                        .description("云台设备会话握手（M2-A01）：设备凭据换取 gimbal device session token，"
                                + "设备上电/重连后的第一个请求。"));
    }

    @Override
    public Map<String, ApiDocEntry> entries() {
        return Map.of(

                // ---------------------------------------------------------- f01
                "POST /api/v1/auth/sms-challenges",
                new ApiDocEntry(
                        TAG_AUTH,
                        "基础协议——发起手机号登录挑战",
                        """
                        用途：手机号登录第一步，向未登录 APP 下发一次性短信验证码挑战（challengeId）。
                        调用方：公开端点（security: []，无 Bearer）；APP 在未登录状态调用。
                        前置与顺序：先调用本端点获得 challengeId，再调用 POST /api/v1/auth/sessions
                        以 challengeId + code 换取会话。
                        关键规则：请求体 phone 必须为 E.164 国际格式（以 + 开头，国家码后 6—15 位数字），
                        purpose 固定为 login；服务端规范化手机号后交认证提供方；响应不泄露账号是否已存在。
                        幂等语义：不保证幂等；重复/高频调用可能触发 RATE_LIMITED，应按下发的
                        Retry-After 退避，不要自动高频重试。
                        字段单位与枚举：challengeId 为提供方签发的字符串（≤128）；retryAfter 单位为秒（≥0）。
                        错误处理：INVALID_INPUT 修正 phone/purpose 后重试；RATE_LIMITED 按 Retry-After 退避；
                        DEPENDENCY_UNAVAILABLE/DEPENDENCY_TIMEOUT 为依赖不可用/超时，受限退避重试。
                        未冻结：真实短信认证提供方未选定，dev/test 使用 SmsCodeProvider 替身；验证码长度、
                        有效 TTL 与风控阈值待定（依据 contracts/decisions-notes.md #8、DD 4.1）。
                        """,
                        List.of(),
                        List.of(),
                        null,
                        "手机号挑战请求体：phone（E.164，必填）+ purpose=login（必填）。",
                        List.of(ApiDocEntry.SuccessDoc.json("200",
                                "挑战已创建；challengeId 供下一步 sessions 使用，retryAfter 为建议等待秒数（单位：秒）",
                                AuthController.SmsChallengeData.class)),
                        List.of(ErrorCode.INVALID_INPUT, ErrorCode.RATE_LIMITED,
                                ErrorCode.DEPENDENCY_UNAVAILABLE, ErrorCode.DEPENDENCY_TIMEOUT)),

                // ---------------------------------------------------------- f02
                "POST /api/v1/auth/sessions",
                new ApiDocEntry(
                        TAG_AUTH,
                        "基础协议——验证码换取 APP 会话",
                        """
                        用途：手机号登录第二步，用 challengeId + 短信验证码换取 APP session token 与本地 accountId。
                        调用方：公开端点（security: []，无 Bearer）；APP。
                        前置与顺序：先调用 POST /api/v1/auth/sms-challenges 获得 challengeId，且验证码在有效期内。
                        关键规则：验证成功后按 (login_provider='phone', login_subject) 并发唯一映射到本地账号（T14）；
                        请求体手机号不作为认证结果；不可仅提交裸 installationId，必须携带安装绑定材料
                        （installBindingMaterial，通道/结构未冻结）；签发前服务端复核本地账号为 active 并捕获
                        auth_revision 快照，disabled 账号拒绝续签新会话（停用即失效）。
                        鉴权口径：主体身份只由 token 派生，请求体不得声明 accountId；APP 会话与云台设备会话
                        并存且命名空间区分。
                        幂等语义：本端点不使用 Idempotency-Key；重复提交同一验证码由提供方语义决定，
                        失败后请重新申请挑战，不要复用旧 challengeId。
                        字段要点：installationId ≤128 字符；installBindingMaterial 为提供方要求的安装绑定材料
                        （自由结构，见该字段的结构展开说明）；accessToken/refreshToken 不写日志。
                        错误处理：INVALID_INPUT 修正字段后重试；AUTH_REQUIRED 验证码错误/挑战失效 → 重新申请挑战；
                        RATE_LIMITED 按 Retry-After 退避；DEPENDENCY_* 受限重试。
                        契约缺口（如实标注）：实现中账号 disabled 时抛 SESSION_INVALID，但契约 f02
                        未声明该码，待总协调裁定；客户端遇到 401 时统一重新登录。
                        未冻结：真实会话提供方未选定，token 有效期/刷新细节待定（dev/test 为替身）。
                        """,
                        List.of(),
                        List.of(),
                        null,
                        "APP 会话签发请求体：challengeId、code、installationId（均必填）+ 可选自由结构 "
                                + "installBindingMaterial（安装绑定材料，结构未冻结）。",
                        List.of(ApiDocEntry.SuccessDoc.json("200",
                                "会话签发：返回本地 accountId 与 APP 会话凭据（refreshToken 可能为 null）",
                                AuthController.AppSessionData.class)),
                        List.of(ErrorCode.INVALID_INPUT, ErrorCode.AUTH_REQUIRED,
                                ErrorCode.RATE_LIMITED, ErrorCode.DEPENDENCY_UNAVAILABLE,
                                ErrorCode.DEPENDENCY_TIMEOUT)),

                // ---------------------------------------------------------- f03
                "POST /api/v1/auth/session-refreshes",
                new ApiDocEntry(
                        TAG_AUTH,
                        "基础协议——刷新 APP 会话",
                        """
                        用途：用真实刷新凭据（refreshCredential）换取新的 APP 会话凭据。
                        调用方：公开端点（security: []；本端点不用 Bearer 认证自身）；APP。
                        前置与顺序：持有有效且未被轮换的 refreshCredential。
                        关键规则：新凭据签发与旧凭据撤销轮换由选定会话协议保证；refreshCredential 不写日志、
                        不得存明文；installationId 可选（≤128），用于将会话与安装实例绑定。
                        幂等语义：不保证幂等；旧 refresh 凭据在轮换后不可复用。
                        字段要点：返回的 accessToken/refreshToken/expiresAt 与 f02 同形（AppSession 数据）。
                        错误处理：SESSION_INVALID（刷新凭据无效或已轮换）→ 重新走 sms-challenges + sessions；
                        AUTH_REQUIRED 缺少/无效刷新凭据；INVALID_INPUT 修正字段；RATE_LIMITED 与
                        DEPENDENCY_* 按错误响应动作受限退避。
                        未冻结：刷新凭据名称/格式与 token 有效期随选定会话协议，待定（dev/test 为替身）。
                        """,
                        List.of(),
                        List.of(),
                        null,
                        "会话刷新请求体：refreshCredential（必填，不写日志）+ 可选 installationId（≤128）。",
                        List.of(ApiDocEntry.SuccessDoc.json("200",
                                "新会话凭据（旧刷新凭据按会话协议轮换/撤销）",
                                AuthController.AppSessionData.class)),
                        List.of(ErrorCode.INVALID_INPUT, ErrorCode.AUTH_REQUIRED,
                                ErrorCode.SESSION_INVALID, ErrorCode.RATE_LIMITED,
                                ErrorCode.DEPENDENCY_UNAVAILABLE, ErrorCode.DEPENDENCY_TIMEOUT)),

                // ---------------------------------------------------------- f04
                "DELETE /api/v1/auth/sessions/current",
                new ApiDocEntry(
                        TAG_AUTH,
                        "基础协议——撤销当前 APP 会话（退出登录）",
                        """
                        用途：退出登录：撤销当前会话使其不可再用，并失效当前会话对应的通知目标。
                        调用方：已登录 APP（Authorization: Bearer APP session token）。本端点由控制器手工读取
                        Authorization 头，故生成文档包含该 header 参数（required）。
                        成功：204 无响应体（requestId 见响应头 X-Request-Id），不使用统一成功信封。
                        关键规则与顺序：先撤销会话，再按 session_ref 条件更新 T09 notification_destinations——
                        status='invalid' 与 destination_revision+1 必须在同一条原子 UPDATE 内完成，以阻断该会话
                        遗留的 T10 路由快照被旧任务写回；只影响本次会话对应的目标，不影响其他安装实例，
                        也不失效后来新登录的目标；WHERE status='active' 保证重复/并发登出幂等（受影响行数为 0，
                        不重复递增，也不刷新 invalidated_at）。
                        幂等语义：重复/并发登出幂等；PG 目标更新失败允许幂等补偿，登出结果不反转。
                        字段要点：Authorization 形如 "Bearer <APP session token>"（合成占位，非真实 token）。
                        错误处理：AUTH_REQUIRED 缺少/格式错误 Bearer → 重新登录；SESSION_INVALID 会话已撤销/失效；
                        RATE_LIMITED 与 DEPENDENCY_* 按错误响应动作受限退避。
                        未冻结：会话提供方未选定，token 有效期与撤销的精确提供方语义待定（dev/test 为替身）。
                        """,
                        List.of(ApiDocEntry.ParamDoc.of("Authorization", "header",
                                "必填，字符串，格式 \"Bearer <APP session token>\"。控制器手工读取该头，"
                                        + "并由过滤器从 token 派生主体身份；缺失/非 Bearer → 401 AUTH_REQUIRED。",
                                "Bearer 0000000000000000000000000000000000000000")),
                        List.of(),
                        null,
                        null,
                        List.of(ApiDocEntry.SuccessDoc.noContent("204",
                                "登出成功且无响应体；先撤销会话，再同事务失效本会话对应的通知目标并递增 "
                                        + "destination_revision。requestId 见 X-Request-Id 头。")),
                        List.of(ErrorCode.AUTH_REQUIRED, ErrorCode.SESSION_INVALID,
                                ErrorCode.RATE_LIMITED, ErrorCode.DEPENDENCY_UNAVAILABLE,
                                ErrorCode.DEPENDENCY_TIMEOUT)),

                // ------------------------------------------------------- M2-A01
                "POST /api/v1/gimbal-sessions",
                new ApiDocEntry(
                        TAG_GIMBAL_SESSION,
                        "云台认证或恢复连接后重新认证（设备会话握手）",
                        """
                        用途：云台设备上电/重连时的设备会话握手：以设备凭据换取 gimbal device session token
                        （token 绑定 gimbalId + credentialVersion + 会话 ID）。这是 9/13 硬件联调设备上电后的
                        第一个请求。
                        调用方：公开端点（security: []，无 Bearer）；云台设备。
                        关键规则：credential 由设备凭据提供方验证；credentialVersion 为无符号 bigint 十进制字符串
                        （pattern ^(0|[1-9][0-9]*)$）；proof 为提供方要求的 nonce/proof（防重放）。凭据失败统一
                        401 AUTH_REQUIRED，不区分“未知凭据/版本不符”，避免枚举探测。本端点不创建或改变云台归属、
                        不登记“可信在线”、不创建护理执行；设备凭据不使用 Idempotency-Key 缓存可重放的秘密凭据。
                        鉴权口径：会话 token 的主体身份只由 token 派生，请求体不得声明 gimbalId；
                        credentialVersion 递增（凭据轮换）后旧 token 立即 401 SESSION_INVALID——认证过滤器每请求
                        经 PrincipalRevalidator 以一条单行查询复核 credential_version。
                        幂等语义：不使用 Idempotency-Key；重复认证不创建护理执行，握手防重放由提供方协议保证。
                        字段要点：credential ≤256 字符；proof ≤512 字符；expiresAt/serverTime 为 RFC3339 UTC
                        秒精度时间。
                        错误处理：INVALID_INPUT 修正字段（含 credentialVersion 越界）；AUTH_REQUIRED 设备凭据未通过；
                        SESSION_INVALID/RATE_LIMITED/DEPENDENCY_* 按错误响应动作。契约当前还声明了
                        SESSION_INVALID 与 IDEMPOTENCY_CONTENT_CONFLICT：在 A 包薄实现中两者不主动触发
                        （契约过声明，按保持一致原则保留，待总协调裁定），客户端按错误响应动作处理即可。
                        未冻结：设备签名算法、密钥预置/轮换、credential/proof 具体格式、sessionToken 字段名与
                        token 有效期均随设备团队与会话协议，待定（dev/test 为 DeviceCredentialProvider 替身）。
                        """,
                        List.of(),
                        List.of(),
                        null,
                        "设备凭据握手请求体：credential、credentialVersion（bigint 十进制字符串）、proof（均必填）。",
                        List.of(ApiDocEntry.SuccessDoc.json("200",
                                "云台设备会话签发成功（不返回成员资料）",
                                GimbalSessionController.GimbalSessionData.class)),
                        List.of(ErrorCode.INVALID_INPUT, ErrorCode.AUTH_REQUIRED,
                                ErrorCode.SESSION_INVALID, ErrorCode.IDEMPOTENCY_CONTENT_CONFLICT,
                                ErrorCode.RATE_LIMITED, ErrorCode.DEPENDENCY_UNAVAILABLE,
                                ErrorCode.DEPENDENCY_TIMEOUT)),

                // ---------------------------------------------------------- f05
                "GET /api/v1/media/{mediaId}/content",
                new ApiDocEntry(
                        TAG_MEDIA,
                        "受控读取媒体对象内容（二进制）",
                        """
                        用途：按 mediaId 流式读取私有存储中的媒体对象内容（图片二进制），非 JSON，无统一信封。
                        调用方：APP 或云台（Authorization: Bearer 对应 session token）。
                        前置与顺序：mediaId 来自业务报告/任务的受控投影（如同源 contentUrl），客户端不应自行拼造。
                        成功：200 二进制；真实 Content-Type 由媒体自身决定（可能 image/jpeg、image/png 或
                        application/octet-stream），响应头恒定 Cache-Control: no-store、
                        X-Content-Type-Options: nosniff，并带 X-Request-Id。
                        关键规则：逐次鉴权——每次读取都重新校验权限（认证主体 → 媒体状态/用途/归属 → 业务关系/
                        当前任务），鉴权发生在读取时；不可见、不存在、非 available、授权拒绝一律返回完全相同的
                        404 RESOURCE_NOT_VISIBLE（不泄露存在性，也不返回内部 bucket/key）；鉴权代理不重定向至
                        长效签名 URL；本版可不支持 Range，请求不因此绕过鉴权；available ≠ 可访问，已下载字节
                        无法远程收回。
                        生产安全默认：媒体策略为 deny-all（直到 B/C/D 安装业务策略）；dev/test 可使用 owner-dev/
                        any-authenticated 便利，但核验用途图片即使对上传者也不经此便利放行
                        （依据 contracts/decisions-notes.md #10）。
                        错误处理：AUTH_REQUIRED/SESSION_INVALID → 重新登录/握手；CALLER_NOT_ALLOWED（契约声明，
                        当前基础实现不主动抛）；RESOURCE_NOT_VISIBLE → 不要换 ID 探测；DEPENDENCY_* 受限重试。
                        """,
                        List.of(ApiDocEntry.ParamDoc.of("mediaId", "path",
                                "必填，路径参数，UUID 字符串（T11.id），媒体对象引用。",
                                "11111111-1111-4111-8111-111111111111")),
                        List.of(),
                        null,
                        null,
                        List.of(ApiDocEntry.SuccessDoc.binary("200",
                                "图片二进制内容；真实 Content-Type 由媒体自身决定（image/jpeg / image/png / "
                                        + "application/octet-stream），无统一信封。响应头 Cache-Control: no-store、"
                                        + "X-Content-Type-Options: nosniff。",
                                "image/jpeg")),
                        List.of(ErrorCode.AUTH_REQUIRED, ErrorCode.SESSION_INVALID,
                                ErrorCode.CALLER_NOT_ALLOWED, ErrorCode.RESOURCE_NOT_VISIBLE,
                                ErrorCode.DEPENDENCY_UNAVAILABLE, ErrorCode.DEPENDENCY_TIMEOUT)),

                // ---------------------------------------------------------- f06
                "POST /api/v1/system/echo-jobs",
                new ApiDocEntry(
                        TAG_SYSTEM,
                        "基础协议——入队 system.echo 跨语言最小测试任务",
                        """
                        用途：基础系统端到端验收桥：入队 job_type=system.echo 异步任务（Java 入队、Python worker 执行）。
                        调用方：已认证主体（APP 或云台 session token 均可）。
                        成功：200；新入队 data.status=queued；携带 Idempotency-Key 且同 principal 同键同内容重放时
                        返回同一 jobId 且 meta.replayed=true。
                        关键规则：任务 payload 带 schema_version=1，bigint 一律十进制字符串；创建者归属（RV-5 裁定）
                        写入 async_jobs.owner_type/owner_id：APP → app_account + accountUuid，GIMBAL → gimbal +
                        gimbalUuid；installation 只属 T13 作用域、不进 owner_id（同账号跨安装可读本账号任务）。
                        dedup_key=system:echo:<body.jobId 或服务端 UUID>，全局唯一。显式 body jobId 的 dedup 边界
                        （RV-7）：若命中非本人所有或非 system.echo 的既有行，POST 返回与 GET 完全相同的
                        404 RESOURCE_NOT_VISIBLE（不返回该行 id/status）；有 Idempotency-Key 时该次 T13 记为
                        rejected，同键重试重放同一拒绝，绝不 succeeded 指向外来任务。
                        幂等语义：Idempotency-Key 可选（1—128 字符；本验收桥端点区别于强制要求的业务写接口）——
                        同 principal 同键同内容重放返回原 jobId；不同 principal 同键是不同 T13 作用域，键去重不跨主体；
                        同键异内容 409 IDEMPOTENCY_CONTENT_CONFLICT；处理中 409 REQUEST_IN_PROGRESS + Retry-After。
                        字段要点：message ≤512 字符（允许中文）；numbersAsStrings 为有序数组、≤32 项，每项为无符号
                        bigint 十进制字符串；jobId 为可选客户端 UUID（作为 dedup_key 后缀，缺省由服务端生成）。
                        错误处理：按错误响应动作；RESOURCE_NOT_VISIBLE 表示 dedup 命中外来/非 echo 行，
                        不要换 jobId 探测。
                        """,
                        List.of(new ApiDocEntry.ParamDoc("Idempotency-Key", "header",
                                "可选，字符串，1—128 字符。提供时走 T13 幂等（operation=system.echo.create）："
                                        + "同键同内容重放返回同一 jobId 且 meta.replayed=true，同键异内容 409。",
                                "echo-20260913-user-0001", null)),
                        List.of(),
                        null,
                        "system.echo 入队请求体：message（≤512，允许中文）+ numbersAsStrings（≤32 项 bigint 十进制字符串）"
                                + "+ 可选 jobId（客户端 UUID）。",
                        List.of(ApiDocEntry.SuccessDoc.json("200",
                                "受理/重放：新入队 data.status=queued；同键同内容重放返回同一 jobId 且 "
                                        + "meta.replayed=true",
                                SystemEchoController.EchoJobAcceptedData.class)),
                        List.of(ErrorCode.INVALID_INPUT, ErrorCode.AUTH_REQUIRED,
                                ErrorCode.SESSION_INVALID, ErrorCode.IDEMPOTENCY_CONTENT_CONFLICT,
                                ErrorCode.REQUEST_IN_PROGRESS, ErrorCode.RESOURCE_NOT_VISIBLE,
                                ErrorCode.RATE_LIMITED, ErrorCode.DEPENDENCY_UNAVAILABLE,
                                ErrorCode.DEPENDENCY_TIMEOUT)),

                // ---------------------------------------------------------- f07
                "GET /api/v1/system/echo-jobs/{jobId}",
                new ApiDocEntry(
                        TAG_SYSTEM,
                        "基础协议——查询 system.echo 任务投影（E2E 验收用）",
                        """
                        用途：只读投影 async_jobs（T12）中本人创建的 system.echo 任务当前状态。
                        调用方：已认证主体（Authorization: Bearer）。
                        成功：200；data 投影 {jobId, status, attemptCount, leaseRevision, finishedAt, lastError}。
                        关键规则：仅创建者本人可读——归属由持久化行 owner_type/owner_id 与认证主体唯一派生，
                        不信任任何请求输入；本端点不得作为任意 async_jobs 的通用查询入口；本端点只读，不改变任务。
                        jobId 不存在 / job_type≠system.echo / 非创建者 三类一律返回完全相同的
                        404 RESOURCE_NOT_VISIBLE（不泄露存在性、归属或类型；未认证仍由过滤器先 401）。
                        状态由 Python worker 的 claim/renew/complete 推进。
                        字段要点：attemptCount/leaseRevision 为无符号 bigint 十进制字符串（leaseRevision 为 null
                        表示无租约）；finishedAt 为 RFC3339 UTC 时间，未到终态为 null；lastError 为有界安全投影，
                        仅 {reason 枚举, retryable bool}，无失败时为 null；内部诊断（raw code/message/stack/
                        retry_after_seconds）绝不外发，未知/畸形 code 归一为 reason=internal。
                        错误处理：INVALID_INPUT（jobId 非 UUID）；AUTH_REQUIRED/SESSION_INVALID →
                        重新登录/握手；RESOURCE_NOT_VISIBLE 统一 404，不要换 ID 探测；RATE_LIMITED 与 DEPENDENCY_*
                        按错误响应动作受限退避。
                        """,
                        List.of(ApiDocEntry.ParamDoc.of("jobId", "path",
                                "必填，路径参数，UUID 字符串（T12.id，即受理响应中的 jobId）。",
                                "22222222-2222-4222-8222-222222222222")),
                        List.of(),
                        null,
                        null,
                        List.of(ApiDocEntry.SuccessDoc.json("200",
                                "任务当前投影；lastError 为有界失败投影（仅 reason+retryable），未失败为 null",
                                SystemEchoController.EchoJobViewData.class)),
                        List.of(ErrorCode.INVALID_INPUT, ErrorCode.AUTH_REQUIRED,
                                ErrorCode.SESSION_INVALID, ErrorCode.RESOURCE_NOT_VISIBLE,
                                ErrorCode.RATE_LIMITED, ErrorCode.DEPENDENCY_UNAVAILABLE,
                                ErrorCode.DEPENDENCY_TIMEOUT))
        );
    }

    @Override
    public Map<String, Map<String, PropertyDoc>> propertyDocs() {
        return Map.ofEntries(

                Map.entry("SmsChallengeRequest", Map.of(
                        "phone", PropertyDoc.of(
                                "必填，字符串，E.164 国际格式（以 + 开头，国家码后 6—15 位数字）；"
                                        + "服务端规范化后交认证提供方，不泄露账号是否已存在。",
                                "+8610000000000"),
                        "purpose", PropertyDoc.enumOf(
                                "必填，字符串，固定为 login（当前唯一用途）。",
                                List.of("login"), "login"))),

                Map.entry("AppSessionRequestBody", Map.of(
                        "challengeId", PropertyDoc.of(
                                "必填，字符串，来自 POST /api/v1/auth/sms-challenges 的 data.challengeId；"
                                        + "提供方签发格式未冻结（≤128）。",
                                "0e6a2b1c-4d5e-6f70-8a9b-0c1d2e3f4a5b"),
                        "code", PropertyDoc.of(
                                "必填，字符串，短信验证码，≤32 字符；不写日志。示例为合成占位。",
                                "123456"),
                        "installationId", PropertyDoc.of(
                                "必填，字符串，APP 安装实例 ID（客户端生成），1—128 字符；用于会话与安装绑定。",
                                "install-0000-0000-0000-000000000001"),
                        "installBindingMaterial", PropertyDoc.of(
                                "可选，可空对象，提供方要求的安装绑定材料；通道与结构未冻结，"
                                        + "见该字段的自由结构展开说明（客户端不应依赖具体键）。"))),

                Map.entry("SessionRefreshRequestBody", Map.of(
                        "refreshCredential", PropertyDoc.of(
                                "必填，字符串，真实刷新凭据；不写日志、不得存明文于 T09/T13。格式随选定会话协议。",
                                "refresh-credential-placeholder"),
                        "installationId", PropertyDoc.of(
                                "可选，可空字符串，APP 安装实例 ID，≤128 字符；用于会话与安装绑定。",
                                "install-0000-0000-0000-000000000001"))),

                Map.entry("GimbalSessionRequestBody", Map.of(
                        "credential", PropertyDoc.of(
                                "必填，字符串，设备凭据，≤256 字符；格式待定（设备签名算法/密钥预置由设备团队对接）。",
                                "device-credential-placeholder"),
                        "credentialVersion", PropertyDoc.of(
                                "必填，字符串，无符号 bigint 十进制字符串（pattern ^(0|[1-9][0-9]*)$）；"
                                        + "凭据轮换递增后旧 session token 立即 401。",
                                "1"),
                        "proof", PropertyDoc.of(
                                "必填，字符串，提供方要求的 nonce/proof，≤512 字符；防重放，格式待定。",
                                "proof-placeholder"))),

                Map.entry("EchoJobRequestBody", Map.of(
                        "message", PropertyDoc.of(
                                "必填，字符串，任务消息，≤512 字符（允许中文）。",
                                "联调回声 0001"),
                        "numbersAsStrings", PropertyDoc.of(
                                "可选，数组，≤32 项；每项为无符号 bigint 十进制字符串（有序数组保持原序）。"),
                        "jobId", PropertyDoc.of(
                                "可选，可空字符串，UUID；作为 dedup_key=system:echo:<jobId> 的后缀，"
                                        + "缺省由服务端生成。",
                                "33333333-3333-4333-8333-333333333333"))),

                Map.entry("SmsChallengeData", Map.of(
                        "challengeId", PropertyDoc.of(
                                "字符串，认证提供方签发的挑战 ID（≤128），供 POST /api/v1/auth/sessions 使用。",
                                "0e6a2b1c-4d5e-6f70-8a9b-0c1d2e3f4a5b"),
                        "retryAfter", PropertyDoc.unitOf(
                                "整数，建议重试等待秒数（≥0）。", "秒", "60"))),

                Map.entry("AppSessionData", Map.of(
                        "accountId", PropertyDoc.of(
                                "字符串，本地账号 ID（T14.id），UUID 格式。", "44444444-4444-4444-8444-444444444444"),
                        "accessToken", PropertyDoc.of(
                                "字符串，APP session token，后续请求作 Authorization: Bearer 使用；不写日志。",
                                "app-session-token-placeholder"),
                        "refreshToken", PropertyDoc.of(
                                "可空字符串，轮换刷新凭据；是否返回由提供方协议决定，可能为 null；不写日志。",
                                "refresh-token-placeholder"),
                        "tokenType", PropertyDoc.enumOf(
                                "字符串，令牌类型，固定为 Bearer。", List.of("Bearer"), "Bearer"),
                        "expiresAt", new PropertyDoc(
                                "字符串，APP 会话过期时间，RFC3339 UTC 秒精度。",
                                null, null, "2026-09-13T08:30:00Z", "date-time"))),

                Map.entry("GimbalSessionData", Map.of(
                        "gimbalId", PropertyDoc.of(
                                "字符串，云台 ID（T03.id），UUID 格式；不返回成员资料。",
                                "55555555-5555-4555-8555-555555555555"),
                        "sessionToken", PropertyDoc.of(
                                "字符串，云台设备会话 token，后续请求作 Authorization: Bearer 使用；不写日志。",
                                "gimbal-session-token-placeholder"),
                        "expiresAt", new PropertyDoc(
                                "字符串，设备会话过期时间，RFC3339 UTC 秒精度；有效期随会话协议，待定。",
                                null, null, "2026-09-13T08:30:00Z", "date-time"),
                        "serverTime", new PropertyDoc(
                                "字符串，服务端当前时间，RFC3339 UTC 秒精度；用于设备校时。",
                                null, null, "2026-09-13T08:00:00Z", "date-time"))),

                Map.entry("EchoJobAcceptedData", Map.of(
                        "jobId", PropertyDoc.of(
                                "字符串，受理任务 ID（T12.id），UUID 格式；供 GET 查询。",
                                "22222222-2222-4222-8222-222222222222"),
                        "dedupKey", PropertyDoc.of(
                                "字符串，全局唯一去重键，形如 system:echo:<uuid>。",
                                "system:echo:33333333-3333-4333-8333-333333333333"),
                        "status", PropertyDoc.enumOf(
                                "字符串，投影的当前任务状态；新入队为 queued。",
                                List.of("queued", "running", "succeeded", "failed", "cancelled"),
                                "queued"))),

                Map.entry("EchoJobViewData", Map.of(
                        "jobId", PropertyDoc.of(
                                "字符串，任务 ID（T12.id），UUID 格式。",
                                "22222222-2222-4222-8222-222222222222"),
                        "status", PropertyDoc.enumOf(
                                "字符串，任务当前状态，由 Python worker 的 claim/renew/complete 推进。",
                                List.of("queued", "running", "succeeded", "failed", "cancelled"),
                                "running"),
                        "attemptCount", PropertyDoc.of(
                                "字符串，无符号 bigint 十进制字符串，已尝试次数。", "1"),
                        "leaseRevision", PropertyDoc.of(
                                "可空字符串，无符号 bigint 十进制字符串，租约代次；null 表示当前无租约。",
                                "2"),
                        "finishedAt", new PropertyDoc(
                                "可空字符串，RFC3339 UTC 完成时间；未到终态为 null。",
                                null, null, "2026-09-13T08:30:00Z", "date-time"),
                        "lastError", PropertyDoc.of(
                                "可空对象，有界失败投影，仅 {reason 枚举, retryable 布尔}；无失败为 null；"
                                        + "内部诊断（raw code/message/stack/retry_after_seconds）绝不外发。"))),

                Map.entry("EchoJobLastError", Map.of(
                        "reason", PropertyDoc.enumOf(
                                "字符串，归一化失败原因白名单；未知/畸形原始 code 一律归一为 internal。"
                                        + "handler_failed 为契约保留值，当前 system.echo 不产生。",
                                List.of("unsupported_contract", "retry_limit_exceeded",
                                        "handler_failed", "internal"),
                                "internal"),
                        "retryable", new PropertyDoc(
                                "布尔，该失败是否可以受限重试。", null, null, "false", null)))
        );
    }

    @Override
    public Map<String, FreeFormDoc> freeFormDocs() {
        return Map.of(
                "AppSessionRequestBody.installBindingMaterial", new FreeFormDoc(
                        """
                        安装绑定材料：写入方为未登录 APP（POST /api/v1/auth/sessions 请求体）。
                        用途是把设备/安装实例与所选会话提供方要求的绑定材料一并提交，用于把会话与安装实例绑定；
                        服务端当前薄实现原样接受该对象但不由基础层解释（真实提供方接入后由其协议决定）。
                        本字段不是数据库 JSONB 业务载荷，不含服务端注入的 schema_version，也未定义版本演进规则。
                        内部诊断键绝不外发：任何服务端失败细节不会出现在此字段或其响应中。
                        """,
                        Map.of(),
                        true,
                        "通道/提供方尚未选定、结构未冻结：已知键集合为空（无任何经取证的键），"
                                + "客户端不应依赖任何具体键名，也不得据此假设字段存在。服务端按开放对象处理"
                                + "（additionalProperties=true），未来新增键必须被客户端容忍；键语义与格式以选定"
                                + "会话提供方协议为准（依据 contracts/decisions-notes.md #8、DD 4.1 与契约 "
                                + "AppSessionRequest.installBindingMaterial 的 x-detail: skeleton）。",
                        null));
    }
}
