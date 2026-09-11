package cn.yuanxin.mvp.web.devices;

import cn.yuanxin.mvp.web.auth.PrincipalContext;
import cn.yuanxin.mvp.web.auth.PrincipalType;
import cn.yuanxin.mvp.web.error.ApiException;
import cn.yuanxin.mvp.web.error.ErrorCode;
import cn.yuanxin.mvp.web.web.EnvelopeSupport;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;

import java.time.Duration;
import java.time.Instant;
import java.util.ArrayList;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.UUID;

/**
 * M2-A03 云台状态查询业务（DD L198-205）。
 *
 * <p>单表读 T03：绑定该云台的账号或该云台自身可读；其他账号/云台/不存在
 * → 同一 404 RESOURCE_NOT_VISIBLE（不可区分）。GET 无副作用。</p>
 *
 * <p>{@code isStale}：{@code last_seen_at} 为空（从未心跳）或超过
 * {@link DeviceProperties#stalenessSecondsOrDefault()} → true；过期/未知绝不
 * 伪装成实时。首次 {@code unknown} 不得解释为"刚离线"（离线语义归 L4）。</p>
 */
@Service
public class GimbalStatusService {

    public static final String NOT_VISIBLE_MESSAGE = "gimbal not visible";

    private final JdbcTemplate jdbc;
    private final DeviceProperties props;

    public GimbalStatusService(JdbcTemplate jdbc, DeviceProperties props) {
        this.jdbc = jdbc;
        this.props = props;
    }

    private record Row(UUID boundAccountId, String connectionStatus, Instant lastSeenAt,
                       long statusRevision, String latestObservation, String activeIncidents) {
    }

    public DeviceDtos.StatusView status(PrincipalContext principal, UUID gimbalId) {
        List<Row> rows = jdbc.query("SELECT bound_account_id, connection_status, last_seen_at,"
                        + " status_revision, latest_observation::text AS latest_observation,"
                        + " active_incidents::text AS active_incidents"
                        + " FROM gimbals WHERE id = ?",
                (rs, i) -> new Row(rs.getObject("bound_account_id", UUID.class),
                        rs.getString("connection_status"),
                        rs.getTimestamp("last_seen_at") == null ? null
                                : rs.getTimestamp("last_seen_at").toInstant(),
                        rs.getLong("status_revision"), rs.getString("latest_observation"),
                        rs.getString("active_incidents")),
                gimbalId);
        if (rows.isEmpty()) {
            throw notVisible();
        }
        Row row = rows.get(0);
        boolean visible = switch (principal.principalType()) {
            case GIMBAL -> gimbalId.equals(principal.gimbalUuid());
            case APP -> principal.accountUuid() != null
                    && Objects.equals(principal.accountUuid(), row.boundAccountId());
        };
        if (!visible) {
            throw notVisible();
        }

        Map<String, Object> observation = DeviceJson.parseObject(row.latestObservation());
        String powerState = DeviceJson.textAt(observation, "power_state");
        boolean stale = row.lastSeenAt() == null || Duration.between(row.lastSeenAt(), Instant.now())
                .getSeconds() > props.stalenessSecondsOrDefault();
        return new DeviceDtos.StatusView(row.connectionStatus(), powerState,
                row.lastSeenAt() == null ? null : EnvelopeSupport.rfc3339(row.lastSeenAt()),
                stale, String.valueOf(row.statusRevision()), activeIncidents(row.activeIncidents()));
    }

    /** 只投影设备状态字段（incidentId/code/severity/时间），绝不含成员/账号/报告信息。 */
    private static List<DeviceDtos.IncidentView> activeIncidents(String raw) {
        Map<String, Object> episodes = DeviceJson.objectAt(DeviceJson.parseObject(raw), "episodes");
        List<DeviceDtos.IncidentView> incidents = new ArrayList<>();
        for (Map.Entry<String, Object> entry : episodes.entrySet()) {
            if (!(entry.getValue() instanceof Map<?, ?> rawEpisode)) {
                continue;
            }
            Map<String, Object> episode = DeviceJson.parseObject(DeviceJson.write(rawEpisode));
            if (!"active".equals(DeviceJson.textAt(episode, "state"))) {
                continue;
            }
            incidents.add(new DeviceDtos.IncidentView(entry.getKey(),
                    DeviceJson.textAt(episode, "code"), DeviceJson.textAt(episode, "severity"),
                    DeviceJson.textAt(episode, "opened_at"),
                    DeviceJson.textAt(episode, "last_reported_at")));
        }
        return incidents;
    }

    private static ApiException notVisible() {
        return new ApiException(ErrorCode.RESOURCE_NOT_VISIBLE, NOT_VISIBLE_MESSAGE);
    }
}
