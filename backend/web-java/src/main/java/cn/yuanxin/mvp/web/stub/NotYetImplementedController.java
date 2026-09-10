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
 * 26 个 contract-only 业务端点的 501 占位（A/decisions #1；M1-A01…M5-A01，
 * 其中 M2-A01 gimbal-sessions 已由 foundation-auth 实现，不在此列）。
 *
 * <p>行为：一律 501 + 标准错误信封 code=NOT_IMPLEMENTED（details.apiId），
 * 绝不伪造 200。显式逐端点 @RequestMapping（无通配 catch-all，避免遮蔽
 * actuator/media/foundation 路由）。UUID 路径参数按契约收紧类型：非法值
 * 在信封化前即 400 INVALID_INPUT。</p>
 *
 * <p>鉴权次序：本类端点在 BearerAuthFilter 之后——未认证先到 401
 * （证明业务路径拒绝无效认证），已认证拿到 501。B/C/D 实现业务时以同路径
 * 的正式控制器取代本类对应方法（删除该 stub 方法即可，无自动让位机制）。</p>
 */
@RestController
@Validated
public class NotYetImplementedController {

    private static ApiException notImplemented(String apiId) {
        return new ApiException(ErrorCode.NOT_IMPLEMENTED,
                "business endpoint is contract-only and not implemented yet",
                Map.of("apiId", apiId));
    }

    // ---------------- M1 成员身份与访问授权 ----------------

    @PostMapping("/api/v1/member-access-grants")
    public void m1A01() {
        throw notImplemented("M1-A01");
    }

    @GetMapping("/api/v1/me/member-access-grants")
    public void m1A02() {
        throw notImplemented("M1-A02");
    }

    @DeleteMapping("/api/v1/me/member-access-grants/{grantId}")
    public void m1A03(@PathVariable UUID grantId) {
        throw notImplemented("M1-A03");
    }

    // ---------------- M2 云台与微晶管理（M2-A01 已实现） ----------------

    @PostMapping("/api/v1/gimbals/{gimbalId}/heartbeats")
    public void m2A02(@PathVariable UUID gimbalId) {
        throw notImplemented("M2-A02");
    }

    @GetMapping("/api/v1/gimbals/{gimbalId}/status")
    public void m2A03(@PathVariable UUID gimbalId) {
        throw notImplemented("M2-A03");
    }

    @PostMapping("/api/v1/microcrystal-observations")
    public void m2A04() {
        throw notImplemented("M2-A04");
    }

    @GetMapping("/api/v1/microcrystals/{microcrystalId}/capabilities")
    public void m2A05(@PathVariable UUID microcrystalId) {
        throw notImplemented("M2-A05");
    }

    @PutMapping("/api/v1/me/gimbal-bindings/{gimbalId}")
    public void m2A06(@PathVariable UUID gimbalId) {
        throw notImplemented("M2-A06");
    }

    @GetMapping("/api/v1/gimbals/{gimbalId}/binding-status")
    public void m2A07(@PathVariable UUID gimbalId) {
        throw notImplemented("M2-A07");
    }

    @DeleteMapping("/api/v1/me/gimbal-bindings/{gimbalId}")
    public void m2A08(@PathVariable UUID gimbalId) {
        throw notImplemented("M2-A08");
    }

    // ---------------- M3 测肤任务与报告 ----------------

    @PostMapping("/api/v1/skin-assessment-tasks")
    public void m3A01() {
        throw notImplemented("M3-A01");
    }

    @PutMapping("/api/v1/skin-assessment-tasks/{taskId}/photo-versions/{photoVersion}")
    public void m3A02(@PathVariable UUID taskId,
                      @PathVariable @Pattern(regexp = "^(0|[1-9][0-9]*)$",
                              message = "photoVersion must be a decimal bigint string") String photoVersion) {
        throw notImplemented("M3-A02");
    }

    @GetMapping("/api/v1/skin-assessment-tasks/{taskId}")
    public void m3A03(@PathVariable UUID taskId) {
        throw notImplemented("M3-A03");
    }

    @GetMapping("/api/v1/members/{memberId}/skin-reports")
    public void m3A04(@PathVariable UUID memberId) {
        throw notImplemented("M3-A04");
    }

    @GetMapping("/api/v1/skin-reports/{reportId}")
    public void m3A05(@PathVariable UUID reportId) {
        throw notImplemented("M3-A05");
    }

    @GetMapping("/api/v1/gimbals/{gimbalId}/current-assessment")
    public void m3A06(@PathVariable UUID gimbalId) {
        throw notImplemented("M3-A06");
    }

    // ---------------- M4 护理管理 ----------------

    @GetMapping("/api/v1/members/{memberId}/care-plans")
    public void m4A01(@PathVariable UUID memberId) {
        throw notImplemented("M4-A01");
    }

    @GetMapping("/api/v1/care-plans/{planId}")
    public void m4A02(@PathVariable UUID planId) {
        throw notImplemented("M4-A02");
    }

    @PostMapping("/api/v1/care-executions")
    public void m4A03() {
        throw notImplemented("M4-A03");
    }

    @PostMapping("/api/v1/care-executions/{executionId}/revalidations")
    public void m4A04(@PathVariable UUID executionId) {
        throw notImplemented("M4-A04");
    }

    @PostMapping("/api/v1/care-executions/{executionId}/observations")
    public void m4A05(@PathVariable UUID executionId) {
        throw notImplemented("M4-A05");
    }

    @PostMapping("/api/v1/care-executions/{executionId}/closure-confirmations")
    public void m4A06(@PathVariable UUID executionId) {
        throw notImplemented("M4-A06");
    }

    @GetMapping("/api/v1/care-executions/{executionId}")
    public void m4A07(@PathVariable UUID executionId) {
        throw notImplemented("M4-A07");
    }

    @GetMapping("/api/v1/care-plans/{planId}/progress")
    public void m4A08(@PathVariable UUID planId) {
        throw notImplemented("M4-A08");
    }

    @GetMapping("/api/v1/members/{memberId}/care-executions")
    public void m4A09(@PathVariable UUID memberId) {
        throw notImplemented("M4-A09");
    }

    // ---------------- M5 消息通知 ----------------

    @PutMapping("/api/v1/me/notification-destinations/{installationId}")
    public void m5A01(@PathVariable @Pattern(regexp = "^[^\\s].{0,127}$",
            message = "installationId must be 1-128 chars") String installationId) {
        throw notImplemented("M5-A01");
    }
}
