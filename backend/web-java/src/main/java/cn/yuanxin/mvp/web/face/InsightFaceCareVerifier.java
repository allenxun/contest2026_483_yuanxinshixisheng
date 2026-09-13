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
 * <p>映射：{@code matched=true} → {@link Outcome#MATCHED}；{@code matched=false} →
 * {@link Outcome#MISMATCH}；{@code NO_FACE}/{@code QUALITY_INSUFFICIENT}（及同族质量码）
 * → {@link Outcome#QUALITY_REJECTED}；{@code SUBJECT_NOT_FOUND}/{@code NAMESPACE_NOT_FOUND}/
 * {@code LIVENESS_UNSUPPORTED} → {@link Outcome#CAPABILITY_UNAVAILABLE}（无成员绑定即
 * fail-closed）；其余失败（配置/依赖/网络）→ {@link Outcome#DEPENDENCY_FAILED}。</p>
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
