package cn.yuanxin.mvp.web.devices;

import org.springframework.boot.context.properties.ConfigurationProperties;

/**
 * M2 设备侧可配置阈值（前缀 {@code app.devices.*}；D03 未冻结）。
 *
 * <p>这些阈值在设备心跳频率与后端验收标准冻结前<b>都不是验收承诺</b>，
 * 仅作为联调起点。全部在 B 自有包内声明，不修改 A 的 config 包；未在
 * application.yml 显式配置时使用构造器默认值（env 可用
 * {@code APP_DEVICES_*}/Spring relaxed binding 覆盖）。</p>
 *
 * <ul>
 *   <li>{@code staleness-seconds}：M2-A03 {@code isStale} 与 M2-A05 能力
 *       新鲜度判定阈值（心跳/观察超过该秒数即视为过期）。默认 300。</li>
 *   <li>{@code offline-seconds}：离线扫描器（L4 负责）判定 T03 过期的阈值，
 *       B 提供配置项以便与扫描器共享；M2 心跳端点自身从不写 offline。默认 300。</li>
 *   <li>{@code incident-suppression-seconds}：重复异常通知抑制间隔，供 L4 扫描器
 *       决定是否针对重复上报再次建通知；M2-A02 只记录 durable 事实，
 *       从不据此丢弃 episode。默认 60。</li>
 *   <li>{@code max-observation-sessions}：会话代次表最多跟踪多少个<b>并存</b>的
 *       服务端会话（心跳 {@code observation_sessions} / 微晶 {@code observer_sessions}）。
 *       达到该上限后，对"服务端从未见过"的新 session 一律 fail closed（拒绝该次
 *       上报，不刷新 {@code last_seen_at}/不覆盖观察），直到凭据代次推进清空会话表
 *       为止；表中已有的 session 不受影响。默认 8。调高该值可降低设备频繁重连
 *       （每次新 session）被拒的风险。</li>
 * </ul>
 */
@ConfigurationProperties(prefix = "app.devices")
public record DeviceProperties(Integer stalenessSeconds, Integer offlineSeconds,
                               Integer incidentSuppressionSeconds,
                               Integer maxObservationSessions) {

    public DeviceProperties {
        if (stalenessSeconds == null || stalenessSeconds < 1) {
            stalenessSeconds = 300;
        }
        if (offlineSeconds == null || offlineSeconds < 1) {
            offlineSeconds = 300;
        }
        if (incidentSuppressionSeconds == null || incidentSuppressionSeconds < 1) {
            incidentSuppressionSeconds = 60;
        }
        if (maxObservationSessions == null || maxObservationSessions < 1) {
            maxObservationSessions = 8;
        }
    }

    public int stalenessSecondsOrDefault() {
        return stalenessSeconds;
    }

    public int offlineSecondsOrDefault() {
        return offlineSeconds;
    }

    public int incidentSuppressionSecondsOrDefault() {
        return incidentSuppressionSeconds;
    }

    public int maxObservationSessionsOrDefault() {
        return maxObservationSessions;
    }
}
