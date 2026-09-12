package cn.yuanxin.mvp.web.docs.catalog;

import cn.yuanxin.mvp.web.error.ErrorCode;

import java.util.Collections;
import java.util.EnumMap;
import java.util.Map;

/**
 * {@link ErrorCode} 的中文联调文档（一句话语义 + 触发条件 + 客户端应对动作 + details 形态）。
 *
 * <p>权威来源：{@code backend/doc/后端详细设计-V1-MVP.md} 的 DD 3.2「错误码与重试动作」表
 * （唯一给出客户端动作的文档），辅以 {@code backend/contracts/openapi/openapi.yaml} 的
 * components.responses 与各 operation description。引擎把本表用于生成错误响应的 description
 * （同一 HTTP 状态多个业务码合并为一个响应、逐码列出）。</p>
 *
 * <p><b>契约缺口（如实标注，不自行改契约）</b>：{@code PROVIDER_CONTRACT_VIOLATION}
 * 已在实现中产生并进入 {@code FailureProjection.PUBLIC_FAILURE_CODES}（M3-A03 会外发为
 * 业务 {@code failureCode}），但<strong>不在</strong> {@code web/error/ErrorCode.java}
 * 的枚举、也不在契约 {@code ErrorCode} enum 与 DD 3.2 表中；因 {@link ErrorCode} 无此常量，
 * 本类无法为其建条，需上报总协调裁定（补契约/枚举 vs. 视为 failureCode 专用命名空间）。</p>
 *
 * <p>HTTP 状态与 retryable 不在本表重复：以 {@link ErrorCode#defaultStatus()} 与
 * {@link ErrorCode#defaultRetryable()} 为唯一事实来源。{@code INTERNAL}(500) 只用于未映射
 * 异常，按设计不出现在任何端点 {@code x-error-codes} 中，仅可用 requestId 诊断。</p>
 */
public final class ErrorCodeDocs {

    private ErrorCodeDocs() {
    }

    private static final Map<ErrorCode, String> DOCS = new EnumMap<>(ErrorCode.class);

    static {
        DOCS.put(ErrorCode.INVALID_INPUT,
                "请求字段缺失、格式非法、枚举越界或未知字段。触发：Bean Validation 或业务前置校验失败。"
                        + "客户端动作：修正请求后重试；不得原样重放。"
                        + "details 形态：{fields:[{field,reason}]}（逐字段原因，不泄漏服务端内部结构）。");
        DOCS.put(ErrorCode.UPLOAD_TOO_LARGE,
                "上传图片超过单图上限（开发初值 10MiB，以配置为准）。触发：multipart 图片字节数超限。"
                        + "客户端动作：压缩/降分辨率后以新的逻辑键重试；不得原样重放。");
        DOCS.put(ErrorCode.UNSUPPORTED_IMAGE,
                "图片格式不在白名单（JPEG/PNG/GIF/WebP，按内容嗅探，不信任客户端 MIME）。"
                        + "触发：字节头无法识别或为空图。客户端动作：改用受支持格式后重试。");
        DOCS.put(ErrorCode.FACE_QUALITY_REJECTED,
                "人脸照片质量不合格（模糊/遮挡/光照不足等）。触发：人脸质检未通过。"
                        + "客户端动作：重新采集更清晰的正脸照片后重试；不构成“未确认本人”，不要自动建档或重试同一张图。");
        DOCS.put(ErrorCode.AUTH_REQUIRED,
                "缺少或格式错误的 Authorization 头。触发：无 Bearer token 或非 Bearer 方案。"
                        + "客户端动作：先登录获取 token 后重试。本码不区分 token 是否有效，避免枚举。");
        DOCS.put(ErrorCode.SESSION_INVALID,
                "会话 token 无效、已过期或已被撤销（含账号停用/全端登出/云台凭据版本轮换）。"
                        + "触发：每请求与本地状态复核失败。客户端动作：重新登录/重新握手获取新 token 后重试；"
                        + "不得复用旧 token。");
        DOCS.put(ErrorCode.RESOURCE_NOT_VISIBLE,
                "资源对当前主体不可见（不存在、不属于本人、或已被替换）。"
                        + "触发：按 ID/归属查询不到对当前 principal 可见的行。"
                        + "客户端动作：不要换 ID 探测；本码刻意对“不存在”与“不可见”返回完全相同的响应，防止存在性推断。");
        DOCS.put(ErrorCode.CALLER_NOT_ALLOWED,
                "当前主体类型不允许调用该端点（如云台调用 APP 专属端点、APP 调用云台专属端点）。"
                        + "触发：principal 类型与端点要求的 APP/GIMBAL 不符。客户端动作：改用正确主体/端点，重试无意义。");
        DOCS.put(ErrorCode.FACE_NOT_VERIFIED,
                "人脸未能可靠确认本人（未匹配到成员、匹配不确定、或成员不存在）。"
                        + "触发：核验结果非可靠匹配。客户端动作：按提示重新采集本人清晰照片；"
                        + "本码与“库中无此成员”返回同一响应，不泄漏成员是否存在，也不返回候选列表。");
        DOCS.put(ErrorCode.GRANT_REVOKED,
                "旧请求指向已撤销的成员访问授权，不能据此创建新的关系或继续写入。"
                        + "触发：T13/业务行关联的关系已 revoked。客户端动作：需要重新授权时发起新的人脸核验请求（新逻辑键），"
                        + "不要复用旧请求键。");
        DOCS.put(ErrorCode.IDEMPOTENCY_CONTENT_CONFLICT,
                "同一 Idempotency-Key 携带了不同内容（payload_hash 不一致），与首次请求冲突。"
                        + "触发：T13 记录 (principal_type, principal_id, operation, idempotency_key) 已存在且载荷哈希不同。"
                        + "客户端动作：这是一个新的逻辑请求，必须使用新的 Idempotency-Key；同键同内容重放会命中原结果"
                        + "（meta.replayed=true），不冲突。");
        DOCS.put(ErrorCode.BINDING_CHANGED,
                "乐观并发代次不符（绑定 revision / 通知目标 destination_revision）。"
                        + "触发：请求携带的 expected* 代次与当前值不一致。客户端动作：刷新当前状态（GET）后用最新代次重试。"
                        + "details 形态：{currentBindingRevision} 或 {currentDestinationRevision}（只含当前代次，不泄漏其他账号信息）。");
        DOCS.put(ErrorCode.TASK_REPLACED,
                "该云台的当前测肤任务已被新任务替换，旧任务不再是当前任务。"
                        + "触发：操作针对的任务 ≠ 云台当前任务。客户端动作：不返回旧报告/旧方案、不恢复旧指针；"
                        + "以当前任务为准重新发起。");
        DOCS.put(ErrorCode.PHOTO_VERSION_CONFLICT,
                "照片版本冲突：补拍版本必须为当前版本 + 1，且任务须处于 needs_retake。"
                        + "触发：版本不连续、expected 不符、或任务状态不允许补拍。客户端动作：刷新任务当前版本/状态后，"
                        + "以正确的下一版本重试；不要跳版或重复提交同版本异内容。");
        DOCS.put(ErrorCode.DEVICE_OCCUPIED,
                "云台正在执行未收尾的护理流程，不能开始新的测肤任务。"
                        + "触发：该云台存在 open care execution。客户端动作：先结束/收尾当前执行（见 STOP_NOT_CONFIRMED）后重试。");
        DOCS.put(ErrorCode.PLAN_NOT_READY,
                "护理方案尚未就绪（生成中或生成失败），不能开始执行。"
                        + "触发：care_plans.generation_status 非 ready。客户端动作：轮询方案状态，就绪后再创建执行；"
                        + "失败态需按失败原因处理，不自动重试无限循环。");
        DOCS.put(ErrorCode.PLAN_COMPLETED,
                "护理方案已完成/关闭，不能对其创建新执行。"
                        + "触发：plan 终态。客户端动作：为新的护理周期使用新的方案。");
        DOCS.put(ErrorCode.EXECUTION_NOT_RESUMABLE,
                "该护理执行当前状态不可继续/恢复。触发：执行已终态或状态机不允许 resumption。"
                        + "客户端动作：查询执行当前状态后按状态机推进；不要重复提交。");
        DOCS.put(ErrorCode.RECORD_CONFLICT,
                "同一执行内出现与既有记录冲突的测量记录（如相同 (epoch,seq) 内容不一致）。"
                        + "触发：计数流水去重键冲突且内容不同。客户端动作：以服务端已有记录为准，修正本地状态。"
                        + "details 形态：{conflictingRecordIds:[≤20 个], totalConflicts}（截断展示，total 为准）。");
        DOCS.put(ErrorCode.CLOSURE_GAPS,
                "收尾确认时测量流水存在缺口（缺少连续区间），不能完成关闭。"
                        + "触发：final seq/count 与已接收记录不连续。客户端动作：补齐缺失区间后重新提交收尾确认。"
                        + "details 形态：{missingRanges, more, finalCount, totalCount}（missingRanges 为缺口区间，more 表示还有更多）。");
        DOCS.put(ErrorCode.STOP_NOT_CONFIRMED,
                "云台执行已停止但未被关闭确认，占用尚未释放。"
                        + "触发：open execution 状态为 stopped 且未收尾。客户端动作：完成收尾确认（closure-confirmations）后重试。");
        DOCS.put(ErrorCode.BOUND_TO_OTHER,
                "该云台已绑定到其他账号，不能覆盖。触发：绑定目标云台已有他人绑定关系。"
                        + "客户端动作：绝不覆盖他人绑定；由当前绑定方先解绑或由对方授权后再操作。");
        DOCS.put(ErrorCode.REQUEST_IN_PROGRESS,
                "同一逻辑请求正在处理中（T13 租约未释放），尚未有终态结果。"
                        + "触发：同 (principal, operation, idempotency_key) 另一处理在进行。客户端动作：按响应 Retry-After 等待后，"
                        + "用<strong>同一</strong> Idempotency-Key 重试；本码 retryable=true。");
        DOCS.put(ErrorCode.RATE_LIMITED,
                "触发限流。触发：单位时间请求过多。客户端动作：按 Retry-After 退避后重试；retryable=true，"
                        + "但应避免立即重试造成放大。");
        DOCS.put(ErrorCode.DEPENDENCY_UNAVAILABLE,
                "依赖不可用（存储写入/人脸或分析提供方等）；任务/写入未成功，绝不伪报成功。"
                        + "触发：下游调用或存储失败。客户端动作：受限退避重试；retryable=true。"
                        + "本码绝不返回“默认核验通过”；上传失败不会留下可用的媒体对象。");
        DOCS.put(ErrorCode.DEPENDENCY_TIMEOUT,
                "依赖调用超时；结果未知，未伪报成功。触发：下游超时。客户端动作：受限退避重试；retryable=true。"
                        + "与 DEPENDENCY_UNAVAILABLE 同样不得视为核验通过。");
        DOCS.put(ErrorCode.INTERNAL,
                "未映射的服务端异常（不承诺重试安全）。触发：内部缺陷或未预期错误。"
                        + "客户端动作：记录响应头 X-Request-Id 反馈运维，不要自动无限重试。"
                        + "本码仅可用 requestId 诊断，按设计不出现在任何端点的 x-error-codes 中。");
        DOCS.put(ErrorCode.UNSUPPORTED_CONTRACT,
                "客户端声明的契约/协议版本不受支持。触发：版本协商失败。客户端动作：升级到受支持的协议版本后重试。");
        DOCS.put(ErrorCode.NOT_IMPLEMENTED,
                "该能力在当前版本未实现（占位/未启用）。触发：调用未启用端点或未激活提供方。"
                        + "客户端动作：不要重试，按产品/联调约定确认能力可用性。"
                        + "已知场景：APP 侧各域业务端点占位亦可能返回 501，需以契约 x-implementation 为准。");
    }

    /** 返回该错误码的中文联调说明（未知码返回显式占位，绝不静默为空）。 */
    public static String describe(ErrorCode code) {
        String doc = DOCS.get(code);
        return doc == null ? "（未收录的错误码，属内部缺陷，请上报：越界或新增码未同步文档）" : doc;
    }

    /** 全量只读视图（测试可用于断言枚举全覆盖）。 */
    public static Map<ErrorCode, String> all() {
        return Collections.unmodifiableMap(new EnumMap<>(DOCS));
    }
}
