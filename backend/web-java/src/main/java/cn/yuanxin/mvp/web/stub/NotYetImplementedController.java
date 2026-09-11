package cn.yuanxin.mvp.web.stub;

import cn.yuanxin.mvp.web.error.ApiException;
import cn.yuanxin.mvp.web.error.ErrorCode;
import org.springframework.validation.annotation.Validated;
import org.springframework.web.bind.annotation.DeleteMapping;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.PutMapping;
import org.springframework.web.bind.annotation.RestController;

import jakarta.validation.constraints.Pattern;
import java.util.Map;
import java.util.UUID;

/**
 * 剩余 contract-only 业务端点的 501 占位（A/decisions #1）。
 *
 * <p>行为：一律 501 + 标准错误信封 code=NOT_IMPLEMENTED（details.apiId），
 * 绝不伪造 200。显式逐端点 @RequestMapping（无通配 catch-all，避免遮蔽
 * actuator/media/foundation 路由）。UUID 路径参数按契约收紧类型：非法值
 * 在信封化前即 400 INVALID_INPUT。</p>
 *
 * <p>鉴权次序：本类端点在 BearerAuthFilter 之后——未认证先到 401
 * （证明业务路径拒绝无效认证），已认证拿到 501。B/C/D 实现业务时以同路径
 * 的正式控制器取代本类对应方法（删除该 stub 方法即可，无自动让位机制）。</p>
 *
 * <p><b>B 包已移除自己的 11 个占位</b>（M1-A01/A02/A03、M2-A02～A08、M5-A01），
 * 由 identity/devices/notifications 业务控制器接管；M2-A01 gimbal-sessions
 * 自始由 foundation-auth 实现，不在本类。本类现仅保留 M3（6 个，D 包）与
 * M4（9 个，C 包）共 15 个占位——其他包按同一方式各自删除自己的方法。</p>
 */
@RestController
@Validated
public class NotYetImplementedController {

    private static ApiException notImplemented(String apiId) {
        return new ApiException(ErrorCode.NOT_IMPLEMENTED,
                "business endpoint is contract-only and not implemented yet",
                Map.of("apiId", apiId));
    }

    // ---------------- M1 成员身份与访问授权：B 包已实现（identity/） ----------------
    // M1-A01 POST /api/v1/member-access-grants
    // M1-A02 GET  /api/v1/me/member-access-grants
    // M1-A03 DELETE /api/v1/me/member-access-grants/{grantId}

    // ---------------- M2 云台与微晶管理：M2-A01 foundation-auth；M2-A02～A08 B 包已实现（devices/） ----------------
    // M2-A02 POST /api/v1/gimbals/{gimbalId}/heartbeats
    // M2-A03 GET  /api/v1/gimbals/{gimbalId}/status
    // M2-A04 POST /api/v1/microcrystal-observations
    // M2-A05 GET  /api/v1/microcrystals/{microcrystalId}/capabilities
    // M2-A06 PUT  /api/v1/me/gimbal-bindings/{gimbalId}
    // M2-A07 GET  /api/v1/gimbals/{gimbalId}/binding-status
    // M2-A08 DELETE /api/v1/me/gimbal-bindings/{gimbalId}

    // ---------------- M3 测肤任务与报告（M3-A01…A06 已实现，见 assessments 包） ----------------

    // ---------------- M5 消息通知：B 包已实现（notifications/） ----------------
    // M5-A01 PUT /api/v1/me/notification-destinations/{installationId}
}
