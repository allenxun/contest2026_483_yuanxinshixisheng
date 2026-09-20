package cn.yuanxin.mvp.web.mediapolicy;

import cn.yuanxin.mvp.web.auth.PrincipalContext;
import cn.yuanxin.mvp.web.auth.PrincipalType;
import cn.yuanxin.mvp.web.media.MediaAccessPolicy;
import cn.yuanxin.mvp.web.media.MediaObject;
import cn.yuanxin.mvp.web.media.MediaPurpose;
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.context.annotation.Primary;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Component;

import java.util.UUID;

/**
 * B 包统一业务媒体授权策略（DD 10.2 五步判定 / DD 4.3 图片权限行）。
 *
 * <p><b>唯一业务策略</b>：{@code @Primary} 覆盖 A 的生产安全默认 deny-all。
 * {@code false} 会被 A 的 {@link cn.yuanxin.mvp.web.media.MediaController}
 * 转成与"资源不存在"<b>完全一致</b>的 404 {@code RESOURCE_NOT_VISIBLE}——本策略
 * 只返回布尔，绝不抛 403、绝不制造可区分错误。策略在任何环境（含 dev/test）都
 * <b>绝不委派</b>给其他便利策略：不存在 dev owner 便利旁路。</p>
 *
 * <p>判定顺序（全部单表查询，无 JOIN、无关联子查询，每请求至多 3 条 SELECT）：</p>
 * <ol>
 *   <li><b>用途闸门（最先、无条件、先于任何 DB 查询）</b>：只有
 *       {@code purpose='assessment_result'} 可进入后续业务判定；其余用途
 *       （{@code assessment_source}，以及 {@code grant_face} /
 *       {@code execution_face} / {@code revalidation_face} 等核验证据）一律
 *       拒绝。核验证据图（含 {@code identity_summary.reference_media} 指向的
 *       媒体）只经 Worker 存储层取用，<b>永不通过业务 HTTP 读取</b>；本策略
 *       也绝不读取 {@code identity_summary} 作为授权依据。</li>
 *   <li><b>状态与接纳</b>：{@code state != 'available'} → 拒绝；单表读 T11
 *       {@code media_objects} 取归属列（接口 {@code MediaObject} 不含归属），
 *       {@code assessment_id IS NULL}（available 但未被业务接纳）→ 拒绝。</li>
 *   <li><b>冻结报告引用（必要条件，APP/云台都适用）</b>：单表读 T05
 *       {@code skin_assessments}，要求 {@code status='report_ready'} 且
 *       {@code report_id/report_payload/report_photo_version} 非空；T11
 *       {@code photo_version} 必须<b>精确等于</b>该 T05 的
 *       {@code report_photo_version}（禁止跨照片版本放行）；且该 mediaId 必须
 *       命中 D 冻结格式 {@code report_payload.images[].media_id}。</li>
 *   <li><b>主体分支</b>：APP 单表读 T02 {@code member_access_grants}
 *       ({@code account_id=principal.accountUuid()}，成员<b>只以 T05
 *       {@code member_id} 为权威</b>；T11.member_id 非空时必须等于 T05，不等
 *       则 fail closed 拒绝；T05 为空则拒绝) 要求 {@code status='active'}；
 *       撤销即时生效（无缓存）。GIMBAL 单表读 T03 {@code gimbals}，要求
 *       {@code current_assessment_id == media.assessment_id}（仅自己的当前任务）
 *       且 {@code credential_version == principal.credentialVersion()}。云台绑定
 *       不能替代成员授权（SC-05-07）。</li>
 * </ol>
 *
 * <p><b>冻结报告引用格式（唯一）</b>：只接受 {@code report_payload.images}
 * 为数组、且其中某项为对象、其下划线键 {@code media_id} 为 UUID 文本并与该
 * mediaId 相等。缺键、{@code images} 非数组、元素非对象、{@code media_id}
 * 缺失/非文本/非 UUID，或仅以 {@code public_media_ids}、{@code photos[]}、
 * {@code photo_versions}、驼峰 {@code mediaId} 等旧兼容形态出现，一律拒绝
 * （deny-by-default）。解析异常只记一条不含内容的 warn 日志（仅 mediaId），
 * 绝不抛到控制器变成 500。</p>
 *
 * <p>只读、无副作用：不写任何表、不递增 revision、不缓存授权结果（撤销即时生效）。
 * 日志不输出 bucket/object_key/成员 ID。</p>
 */
@Component
@Primary
public class BusinessMediaAccessPolicy implements MediaAccessPolicy {

    private static final Logger log = LoggerFactory.getLogger(BusinessMediaAccessPolicy.class);

    private final JdbcTemplate jdbc;
    private final ObjectMapper objectMapper;

    public BusinessMediaAccessPolicy(JdbcTemplate jdbc, ObjectMapper objectMapper) {
        this.jdbc = jdbc;
        this.objectMapper = objectMapper;
    }

    @Override
    public boolean canAccess(PrincipalContext principal, MediaObject media) {
        if (principal == null || media == null) {
            return false;
        }
        // 规则 1：只有 assessment_result 进入业务判定；其余用途（核验证据等）
        // 无条件拒绝，且先于任何 DB 查询。
        if (media.purpose() != MediaPurpose.ASSESSMENT_RESULT) {
            return false;
        }
        try {
            return decide(principal, media);
        } catch (RuntimeException e) {
            // fail closed：任何 DB/解析异常都表现为不可见（404），绝不 500。
            log.warn("media policy decision failed closed mediaId={} branch=error", media.id());
            return false;
        }
    }

    /** 规则 2–4（仅 assessment_result 用途可达）。 */
    private boolean decide(PrincipalContext principal, MediaObject media) {
        // 规则 2：状态必须 available（控制器已挡；策略自身也挡，防他处复用）。
        if (!"available".equals(media.state())) {
            return false;
        }
        // 规则 2：单表读 T11 归属列（接口投影不含 assessment/member/photo_version）。
        var mediaRows = jdbc.query(
                "SELECT assessment_id, photo_version, member_id FROM media_objects WHERE id = ?",
                (rs, i) -> new MediaAttribution(
                        rs.getObject("assessment_id", UUID.class),
                        rs.getObject("photo_version", Long.class),
                        rs.getObject("member_id", UUID.class)),
                media.id());
        if (mediaRows.isEmpty()) {
            return false;
        }
        MediaAttribution attribution = mediaRows.get(0);
        // available 但未被业务接纳（无测肤任务归属）→ 拒绝。
        if (attribution.assessmentId() == null) {
            return false;
        }
        // 规则 3：单表读 T05 冻结报告（status/report_id/report_payload/report_photo_version）。
        var assessmentRows = jdbc.query(
                "SELECT status, report_id, report_payload::text AS report_payload,"
                        + " report_photo_version, member_id"
                        + " FROM skin_assessments WHERE id = ?",
                (rs, i) -> new AssessmentProjection(
                        rs.getString("status"),
                        rs.getObject("report_id", UUID.class),
                        rs.getString("report_payload"),
                        rs.getObject("report_photo_version", Long.class),
                        rs.getObject("member_id", UUID.class)),
                attribution.assessmentId());
        if (assessmentRows.isEmpty()) {
            return false;
        }
        AssessmentProjection assessment = assessmentRows.get(0);
        if (!"report_ready".equals(assessment.status())
                || assessment.reportId() == null
                || assessment.reportPayload() == null
                || assessment.reportPhotoVersion() == null) {
            return false;
        }
        // 规则 3：禁止跨照片版本放行——T11.photo_version 必须精确等于 report_photo_version。
        if (!assessment.reportPhotoVersion().equals(attribution.photoVersion())) {
            return false;
        }
        // 规则 3：必须命中 D 冻结格式 report_payload.images[].media_id。
        if (!isReferencedByFrozenReport(assessment.reportPayload(), media.id())) {
            return false;
        }
        // 规则 4：主体分支。成员归属的唯一权威是 T05（报告所属成员）；T11 与 T05
        // 之间没有跨表一致性约束，T11.member_id 被写成他人时绝不能扩大授权。
        if (principal.principalType() == PrincipalType.APP) {
            UUID memberId = assessment.memberId();
            if (memberId == null || principal.accountUuid() == null) {
                return false;
            }
            if (attribution.memberId() != null && !attribution.memberId().equals(memberId)) {
                log.warn("media policy member attribution mismatch; denied mediaId={}"
                        + " branch=t11-t05-member-mismatch", media.id());
                return false;
            }
            Integer active = jdbc.queryForObject(
                    "SELECT count(*) FROM member_access_grants"
                            + " WHERE account_id = ? AND member_id = ? AND status = 'active'",
                    Integer.class, principal.accountUuid(), memberId);
            return active != null && active > 0;
        }
        if (principal.principalType() == PrincipalType.GIMBAL) {
            if (principal.gimbalUuid() == null) {
                return false;
            }
            var gimbalRows = jdbc.query(
                    "SELECT current_assessment_id, credential_version FROM gimbals WHERE id = ?",
                    (rs, i) -> new GimbalProjection(
                            rs.getObject("current_assessment_id", UUID.class),
                            rs.getLong("credential_version")),
                    principal.gimbalUuid());
            if (gimbalRows.isEmpty()) {
                return false;
            }
            GimbalProjection gimbal = gimbalRows.get(0);
            // 只限自己的当前任务 + 凭据代次一致（云台不得借历史任务/Member 扩大范围）。
            return attribution.assessmentId().equals(gimbal.currentAssessmentId())
                    && gimbal.credentialVersion() == principal.credentialVersion();
        }
        return false;
    }

    // ------------------------------------------------------------------
    // 冻结报告引用读取（唯一格式 + 默认拒绝）
    // ------------------------------------------------------------------

    /** 仅 {@code report_payload.images[].media_id}（下划线键、UUID 文本）命中即引用。 */
    private boolean isReferencedByFrozenReport(String reportPayload, UUID mediaId) {
        try {
            JsonNode payload = objectMapper.readTree(reportPayload);
            if (payload == null || !payload.isObject()) {
                return false;
            }
            return containsFrozenMediaId(payload.get("images"), mediaId);
        } catch (Exception e) {
            // 解析失败 → 拒绝（deny-by-default），只记 mediaId，不含任何 payload 内容。
            log.warn("media policy report-reference parse failed; denied mediaId={}", mediaId);
            return false;
        }
    }

    /** {@code images} 必须是数组；任一项为对象且 {@code media_id} 为相等 UUID 即命中。 */
    private static boolean containsFrozenMediaId(JsonNode imagesNode, UUID mediaId) {
        if (imagesNode == null || !imagesNode.isArray()) {
            return false;
        }
        for (JsonNode element : imagesNode) {
            if (!element.isObject()) {
                continue;
            }
            JsonNode idNode = element.get("media_id");
            if (idNode != null && idNode.isTextual() && uuidEquals(idNode.asText(), mediaId)) {
                return true;
            }
        }
        return false;
    }

    private static boolean uuidEquals(String text, UUID expected) {
        UUID parsed = parseUuidText(text);
        return parsed != null && parsed.equals(expected);
    }

    private static UUID parseUuidText(String text) {
        if (text == null) {
            return null;
        }
        try {
            return UUID.fromString(text);
        } catch (IllegalArgumentException e) {
            return null;
        }
    }

    private record MediaAttribution(UUID assessmentId, Long photoVersion, UUID memberId) {
    }

    private record AssessmentProjection(String status, UUID reportId, String reportPayload,
                                        Long reportPhotoVersion, UUID memberId) {
    }

    private record GimbalProjection(UUID currentAssessmentId, long credentialVersion) {
    }
}
