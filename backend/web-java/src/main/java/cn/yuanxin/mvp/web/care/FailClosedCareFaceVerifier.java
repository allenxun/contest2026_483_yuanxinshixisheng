package cn.yuanxin.mvp.web.care;

import org.springframework.stereotype.Component;

import java.util.UUID;

/**
 * 生产默认的 fail-closed 人脸核验实现。
 *
 * <p>在成员绑定 1:1（可信参考照、策略/模型版本）能力接入前，<b>任何</b>准入
 * 人脸核验一律失败关闭：{@link #verifyOneToOne} 恒返回
 * {@link Outcome#CAPABILITY_UNAVAILABLE}，由 {@link CareAdmissionService} 映射为
 * 503 DEPENDENCY_UNAVAILABLE，绝不默认通过。</p>
 *
 * <p>本 bean 无条件注册；dev/test 由 {@link MemberBindingFaceDouble}（@Primary）
 * 覆盖。真实提供方应在生产 profile 安装具备成员绑定能力的
 * {@link CareFaceVerifier} 替代本类。</p>
 */
@Component
public class FailClosedCareFaceVerifier implements CareFaceVerifier {

    @Override
    public Outcome verifyOneToOne(String purpose, UUID memberId, byte[] candidate) {
        return Outcome.CAPABILITY_UNAVAILABLE;
    }
}
