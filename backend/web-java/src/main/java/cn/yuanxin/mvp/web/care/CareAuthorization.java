package cn.yuanxin.mvp.web.care;

import cn.yuanxin.mvp.web.auth.PrincipalContext;
import cn.yuanxin.mvp.web.auth.PrincipalType;
import cn.yuanxin.mvp.web.care.CareExecutionRepository.CareExecutionRow;
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
 * </ul>
 */
@Component
public class CareAuthorization {

    private static final String NOT_VISIBLE_MESSAGE = "care resource not visible";

    private final CareAccessRepository accessRepository;

    public CareAuthorization(CareAccessRepository accessRepository) {
        this.accessRepository = accessRepository;
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

    /** 统一不可见信封（每次新建实例，但 code/message/retryable/details 完全一致）。 */
    public ApiException notVisible() {
        return new ApiException(ErrorCode.RESOURCE_NOT_VISIBLE, NOT_VISIBLE_MESSAGE);
    }
}
