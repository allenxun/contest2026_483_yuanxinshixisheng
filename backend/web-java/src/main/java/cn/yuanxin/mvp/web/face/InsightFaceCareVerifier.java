package cn.yuanxin.mvp.web.face;

import cn.yuanxin.mvp.web.care.CareFaceVerifier;
import org.springframework.jdbc.core.JdbcTemplate;

import java.util.List;
import java.util.UUID;

/**
 * InsightFace 1:1 护理核验实现（{@code app.face.provider=insightface}）。
 *
 * <p>用目标成员的可信参考照做 1:1 比对：先按 {@code memberId} 只读查 {@code members}
 * 的 {@code identity_namespace} + {@code face_subject_ref}（沿用
 * {@code MemberAccessGrantService.findActiveMember} 的只读口径），再调远端
 * {@code POST /v1/verify}（image + namespace + subject_id）。<b>绝不用全库 top1</b>、
 * <b>绝不默认 MATCHED</b>。</p>
 *
 * <p><b>活体（BLOCKER 1，红线）</b>：{@code FaceServiceClient.verify} <b>恒定</b>发送
 * {@code require_liveness=true}（不可配置、无关闭开关）。真实服务未实现活体 ⇒ 返回 501
 * {@code LIVENESS_UNSUPPORTED} ⇒ 本类映射 {@link Outcome#CAPABILITY_UNAVAILABLE}
 * （上层 503）。<b>后果声明：在活体能力真正落地并被服务端接入之前，insightface 模式下的
 * 护理 1:1 准入<u>恒不可用</u>；这是刻意的 fail-closed，不是缺陷</b>——绝不允许无活体的
 * 1:1 比对通过护理准入。响应形状亦被客户端严格校验，畸形响应不会降级为 MATCHED/MISMATCH。</p>
 *
 * <p>映射：{@code matched=true} → {@link Outcome#MATCHED}（仅当客户端已通过严格契约校验）；
 * {@code matched=false} → {@link Outcome#MISMATCH}；{@code NO_FACE}/
 * {@code QUALITY_INSUFFICIENT}（及同族质量码）→ {@link Outcome#QUALITY_REJECTED}；
 * {@code SUBJECT_NOT_FOUND}/{@code NAMESPACE_NOT_FOUND}/{@code LIVENESS_UNSUPPORTED}
 * → {@link Outcome#CAPABILITY_UNAVAILABLE}（无成员绑定即 fail-closed）；
 * 其余失败（配置/依赖/网络/契约畸形）→ {@link Outcome#DEPENDENCY_FAILED}。</p>
 *
 * <p><b>生产信号处置</b>：本实现非 {@code FailClosedCareFaceVerifier}，与无条件注册的
 * {@code CareFaceVerifierProductionGuard} 冲突（守卫要求生产只允许 fail-closed 实现）。
 * 处置：装配侧对本 bean 追加非生产条件（见 {@code FaceProvidersConfig}）——生产信号下
 * 不装配本实现，由 {@code FailClosedCareFaceVerifier} 接管；<b>不改</b>守卫。</p>
 */
public class InsightFaceCareVerifier implements CareFaceVerifier {

    private final FaceServiceClient client;
    private final JdbcTemplate jdbc;
    private final Double threshold;

    public InsightFaceCareVerifier(FaceServiceClient client, JdbcTemplate jdbc, Double threshold) {
        this.client = client;
        this.jdbc = jdbc;
        this.threshold = threshold;
    }

    @Override
    public Outcome verifyOneToOne(String purpose, UUID memberId, byte[] candidate) {
        MemberRef member = findActiveMember(memberId);
        if (member == null || member.faceSubjectRef() == null || member.faceSubjectRef().isBlank()) {
            return Outcome.CAPABILITY_UNAVAILABLE;
        }
        try {
            FaceServiceClient.VerifyResult result = client.verify(candidate,
                    member.identityNamespace(), member.faceSubjectRef(), threshold);
            return result.matched() ? Outcome.MATCHED : Outcome.MISMATCH;
        } catch (FaceServiceException failure) {
            String code = failure.error().safeCode();
            if ("SUBJECT_NOT_FOUND".equals(code) || "NAMESPACE_NOT_FOUND".equals(code)
                    || "LIVENESS_UNSUPPORTED".equals(code)) {
                return Outcome.CAPABILITY_UNAVAILABLE;
            }
            if (InsightFaceProvider.QUALITY_CODES.contains(code)) {
                return Outcome.QUALITY_REJECTED;
            }
            return Outcome.DEPENDENCY_FAILED;
        } catch (RuntimeException unexpected) {
            return Outcome.DEPENDENCY_FAILED;
        }
    }

    private MemberRef findActiveMember(UUID memberId) {
        List<MemberRef> rows = jdbc.query("SELECT identity_namespace, face_subject_ref FROM members"
                        + " WHERE id = ? AND status = 'active'",
                (rs, i) -> new MemberRef(rs.getString("identity_namespace"),
                        rs.getString("face_subject_ref")),
                memberId);
        return rows.isEmpty() ? null : rows.get(0);
    }

    record MemberRef(String identityNamespace, String faceSubjectRef) {
    }
}
