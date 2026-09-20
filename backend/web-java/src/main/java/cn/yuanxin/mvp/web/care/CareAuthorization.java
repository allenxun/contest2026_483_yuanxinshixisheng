package cn.yuanxin.mvp.web.care;

import cn.yuanxin.mvp.web.auth.PrincipalContext;
import cn.yuanxin.mvp.web.auth.PrincipalType;
import cn.yuanxin.mvp.web.care.CareExecutionRepository.CareExecutionRow;
import cn.yuanxin.mvp.web.care.CarePlanRepository.CarePlanRow;
import cn.yuanxin.mvp.web.error.ApiException;
import cn.yuanxin.mvp.web.error.ErrorCode;
import org.springframework.stereotype.Component;

import java.util.UUID;

/**
 * M4 查询端点的授权判定（Controller 薄，逻辑集中于此）。
 *
 * <ul>
 *   <li>APP-only 端点收到 GIMBAL 主体 → 403 CALLER_NOT_ALLOWED（先于任何资源读取）；</li>
 *   <li>T02 active 授权存在性；</li>
 *   <li>M4-A07 原控制端判定（APP account+installation / GIMBAL gimbal）；</li>
 *   <li>统一不可见 404：资源缺失/无授权/已撤销/非归属云台/代次过期一律返回<b>完全相同</b>
 *       的 404 RESOURCE_NOT_VISIBLE 信封，不区分三态、不泄露存在性。</li>
 *   <li><b>原控制端</b>（可补账/收尾，永久）与<b>当前方案读取资格</b>（须当前
 *       有效授权/当前任务指针）是两种不同判定：前者决定谁来写，后者决定是否
 *       可读方案/Progress。</li>
 * </ul>
 */
@Component
public class CareAuthorization {

    private static final String NOT_VISIBLE_MESSAGE = "care resource not visible";

    private final CareAccessRepository accessRepository;
    private final GimbalReadRepository gimbalRepository;

    public CareAuthorization(CareAccessRepository accessRepository,
                             GimbalReadRepository gimbalRepository) {
        this.accessRepository = accessRepository;
        this.gimbalRepository = gimbalRepository;
    }

    /** APP-only 端点：GIMBAL 主体 403 CALLER_NOT_ALLOWED（先于资源读取）。 */
    public void requireApp(PrincipalContext principal) {
        if (principal.principalType() != PrincipalType.APP) {
            throw new ApiException(ErrorCode.CALLER_NOT_ALLOWED, "caller is not allowed for this endpoint");
        }
    }

    /** 当前 APP 账号对该成员是否有 active 查看授权。 */
    public boolean hasActiveGrant(PrincipalContext principal, UUID memberId) {
        if (principal.principalType() != PrincipalType.APP) {
            return false;
        }
        return accessRepository.hasActiveGrant(principal.accountUuid(), memberId);
    }

    /** M4-A07 原控制端：APP 需 account+installation 精确一致；GIMBAL 需 gimbal 一致。 */
    public boolean isOriginalController(PrincipalContext principal, CareExecutionRow row) {
        if (principal.principalType() == PrincipalType.APP) {
            return "app".equals(row.controllerType())
                    && row.controllerAccountId() != null
                    && row.controllerAccountId().equals(principal.accountUuid())
                    && row.controllerInstallationId() != null
                    && row.controllerInstallationId().equals(principal.installationId());
        }
        return "gimbal".equals(row.controllerType())
                && row.controllerGimbalId() != null
                && row.controllerGimbalId().equals(principal.gimbalUuid());
    }

    /**
     * <b>当前</b>方案读取资格（读方案正文/Progress 的前提，区别于永久原控制端）：
     * APP → 当前账号对该成员有 active 授权；GIMBAL → 调用云台当前任务指针存在且
     * 指向该方案所属 assessment。任一不满足即无资格（调用方统一 404 / progress=null）。
     */
    public boolean hasPlanReadEligibility(PrincipalContext principal, CarePlanRow plan) {
        if (principal.principalType() == PrincipalType.APP) {
            return hasActiveGrant(principal, plan.memberId());
        }
        return gimbalRepository.findPointer(principal.gimbalUuid())
                .map(pointer -> plan.assessmentId() != null
                        && plan.assessmentId().equals(pointer.currentAssessmentId()))
                .orElse(false);
    }

    /** 统一不可见信封（每次新建实例，但 code/message/retryable/details 完全一致）。 */
    public ApiException notVisible() {
        return new ApiException(ErrorCode.RESOURCE_NOT_VISIBLE, NOT_VISIBLE_MESSAGE);
    }
}
