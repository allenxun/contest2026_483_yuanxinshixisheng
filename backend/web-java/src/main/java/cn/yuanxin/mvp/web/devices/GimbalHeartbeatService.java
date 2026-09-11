package cn.yuanxin.mvp.web.devices;

import cn.yuanxin.mvp.web.auth.PrincipalContext;
import cn.yuanxin.mvp.web.auth.PrincipalType;
import cn.yuanxin.mvp.web.error.ApiException;
import cn.yuanxin.mvp.web.error.ErrorCode;
import cn.yuanxin.mvp.web.web.EnvelopeSupport;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.support.TransactionTemplate;

import java.sql.Timestamp;
import java.time.Instant;
import java.util.HashMap;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.UUID;

/**
 * M2-A02 云台心跳业务（DD L189-196；lane-m2 跨 lane 决策 2/5/6）。
 *
 * <p>顺序判定的权威是服务端维护的会话代次表（{@link ObservationSessions}，Oracle
 * 第二轮 #2）：T03 无对应列，故把 {@code observation_sessions}（服务端实际见过
 * 的 session 及其首次被观察到的次序）、当前 {@code observation_generation}、
 * {@code observation_credential_version} 与 {@code observation_epoch/observation_seq}
 * 一同存进 {@code gimbals.latest_observation} JSONB。随机 sessionId 的"不相等"绝不
 * 当作"更新"：新 session 由服务端首次见到时获得"表中最大代次 + 1"，一旦被更高代次
 * 取代就<b>永不重获权威</b>（旧 generation &lt; 当前 → 拒绝），从而闭合两会话
 * 交替来回覆盖。仅真实的 {@code credential_version} 推进才清空会话表并重置。
 * 同一 generation 内客户端<b>不得更换 epoch</b>，且 seq 必须严格更大。所有
 * {@code accepted=false} 不更新 {@code last_seen_at}/不递增 status_revision/不覆盖
 * observation。客户端自填 epoch 绝不作为新旧权威。</p>
 *
 * <p>共享列写纪律：{@code SELECT ... FOR UPDATE} 读 T03 → 计算 → 只写本次要改的
 * 列，{@code WHERE id=? AND status_revision=<读到的值>} 守卫；{@code status_revision}
 * 仅在 connection_status 实际变化（unknown/offline → online）时 +1。本端点从不写
 * offline（离线判定归 L4 扫描器）。</p>
 *
 * <p>{@code taskId}/{@code executionId} 只作观察写入 latest_observation.task_ref/
 * execution_ref，绝不移动 current_assessment 指针、不累计计数、不释放占用、不建
 * 执行/job；即使与当前指针不符也不拒绝、不下发命令（因此本实现不使用
 * TASK_REPLACED）。</p>
 */
@Service
public class GimbalHeartbeatService {

    public static final String NOT_VISIBLE_MESSAGE = "gimbal not visible";

    private final JdbcTemplate jdbc;
    private final TransactionTemplate txTemplate;

    public GimbalHeartbeatService(JdbcTemplate jdbc, TransactionTemplate txTemplate) {
        this.jdbc = jdbc;
        this.txTemplate = txTemplate;
    }

    /** accepted=false 时 lastSeenAt 为当前后端的既有值（可能由更早心跳设置）。 */
    public record Result(boolean accepted, Instant lastSeenAt, long statusRevision) {
    }

    private record Row(long credentialVersion, Instant lastSeenAt, String connectionStatus,
                       long statusRevision, String latestObservation, String activeIncidents) {
    }

    private record EpisodeOutcome(Map<String, Object> latestEpisodes,
                                  Map<String, Object> activeEpisodes) {
    }

    public Result report(PrincipalContext principal, UUID gimbalId, DeviceDtos.HeartbeatBody body) {
        if (principal.principalType() != PrincipalType.GIMBAL) {
            throw new ApiException(ErrorCode.CALLER_NOT_ALLOWED,
                    "this endpoint is only available to gimbal device sessions");
        }
        if (!gimbalId.equals(principal.gimbalUuid())) {
            throw notVisible();
        }
        long seq = parseBigint(body.observationSeq());
        return txTemplate.execute(status -> reportLocked(principal, gimbalId, body, seq));
    }

    private Result reportLocked(PrincipalContext principal, UUID gimbalId,
                                DeviceDtos.HeartbeatBody body, long seq) {
        Row row = loadForUpdate(gimbalId);
        if (row == null) {
            throw notVisible();
        }
        // 会话代次优先于客户端自填 epoch（DD 4.2）：A 的 PrincipalRevalidator 已每请求
        // 复核；此处再以 T03 当前 credential_version 显式核对，不一致 → 401。
        if (row.credentialVersion() != principal.credentialVersion()) {
            throw new ApiException(ErrorCode.SESSION_INVALID,
                    "gimbal session credential generation is no longer current");
        }

        Map<String, Object> observation = DeviceJson.parseObject(row.latestObservation());
        ObservationSessions.Resolution resolution = ObservationSessions.resolve(
                observation.get("observation_sessions"),
                DeviceJson.longAt(observation, "observation_credential_version"),
                DeviceJson.longAt(observation, "observation_generation"),
                principal.credentialVersion(), principal.sessionId());
        String existingEpoch = DeviceJson.textAt(observation, "observation_epoch");
        Long existingSeq = DeviceJson.longAt(observation, "observation_seq");
        boolean accepted = switch (resolution.relation()) {
            // 新连接（首次 / 凭据推进 / 服务端首次见到该 session / 更高代次）：接受并重置基准。
            case FIRST_OR_ADVANCED, NEWER -> true;
            // 同一连接：客户端不得更换 epoch，且 seq 必须严格更大。
            case SAME -> body.observationEpoch().equals(existingEpoch)
                    && existingSeq != null && seq > existingSeq;
            // 旧连接（已被更高代次取代）：一律拒绝，旧会话永不重获权威。
            case STALE -> false;
        };
        if (!accepted) {
            return new Result(false, row.lastSeenAt(), row.statusRevision());
        }

        Instant now = Instant.now();
        Map<String, Object> activeIncidents = DeviceJson.parseObject(row.activeIncidents());
        EpisodeOutcome episodes = mergeEpisodes(observation, activeIncidents, body, seq, now);

        Map<String, Object> latest = new LinkedHashMap<>();
        latest.put("schema_version", 1);
        latest.put("observation_generation", resolution.generation());
        latest.put("observation_sessions", ObservationSessions.toJson(resolution.sessions()));
        latest.put("observation_credential_version", principal.credentialVersion());
        latest.put("observation_epoch", body.observationEpoch());
        latest.put("observation_seq", seq);
        latest.put("power_state", body.powerState().name());
        latest.put("observed_at", EnvelopeSupport.rfc3339(body.observedAt()));
        latest.put("received_at", EnvelopeSupport.rfc3339(now));
        latest.put("task_ref", body.taskId() == null ? null : body.taskId());
        latest.put("execution_ref", body.executionId() == null ? null : body.executionId());
        latest.put("episodes", episodes.latestEpisodes());

        Map<String, Object> active = new LinkedHashMap<>();
        active.put("schema_version", 1);
        active.put("episodes", episodes.activeEpisodes());

        // 仅 unknown/offline → online 视为状态实际变化；已在 online 时不递增代次。
        long statusRevision = "online".equals(row.connectionStatus())
                ? row.statusRevision() : row.statusRevision() + 1;

        int updated = jdbc.update("UPDATE gimbals"
                        + " SET last_seen_at = ?, latest_observation = ?::jsonb,"
                        + " active_incidents = ?::jsonb, connection_status = 'online',"
                        + " status_revision = ?, updated_at = now()"
                        + " WHERE id = ? AND status_revision = ?",
                Timestamp.from(now), DeviceJson.write(latest), DeviceJson.write(active),
                statusRevision, gimbalId, row.statusRevision());
        if (updated == 0) {
            // 持有 FOR UPDATE 时应不可达；作为并发保护按"稍后重试"处理。
            throw ApiException.requestInProgress(1);
        }
        return new Result(true, now, statusRevision);
    }

    private Row loadForUpdate(UUID gimbalId) {
        List<Row> rows = jdbc.query("SELECT credential_version, last_seen_at, connection_status,"
                        + " status_revision, latest_observation::text AS latest_observation,"
                        + " active_incidents::text AS active_incidents"
                        + " FROM gimbals WHERE id = ? FOR UPDATE",
                (rs, i) -> new Row(rs.getLong("credential_version"),
                        rs.getTimestamp("last_seen_at") == null ? null
                                : rs.getTimestamp("last_seen_at").toInstant(),
                        rs.getString("connection_status"), rs.getLong("status_revision"),
                        rs.getString("latest_observation"), rs.getString("active_incidents")),
                gimbalId);
        return rows.isEmpty() ? null : rows.get(0);
    }

    /**
     * Episode 稳定性（跨 lane 决策 5）：同一 code 在 active 期间复用同一
     * incidentId；被报清除 → state=resolved + resolved_at；再次出现 → 新 incidentId。
     */
    private EpisodeOutcome mergeEpisodes(Map<String, Object> observation,
                                         Map<String, Object> activeIncidents,
                                         DeviceDtos.HeartbeatBody body, long seq, Instant now) {
        Map<String, Object> activeEpisodes = DeviceJson.objectAt(activeIncidents, "episodes");
        Map<String, Object> latestEpisodes;
        if (activeEpisodes.isEmpty()) {
            // 容忍历史上只写了 latest_observation 的行（两者同源，取并集基线）。
            latestEpisodes = DeviceJson.copyEpisodeMap(
                    DeviceJson.objectAt(observation, "episodes"));
        } else {
            latestEpisodes = DeviceJson.copyEpisodeMap(activeEpisodes);
        }
        Map<String, Object> activeCopy = DeviceJson.copyEpisodeMap(activeEpisodes);
        if (activeCopy.isEmpty()) {
            activeCopy = DeviceJson.copyEpisodeMap(latestEpisodes);
        }

        Map<String, String> activeByCode = new HashMap<>();
        for (Map.Entry<String, Object> entry : activeCopy.entrySet()) {
            if (entry.getValue() instanceof Map<?, ?> raw) {
                Map<String, Object> episode = new LinkedHashMap<>();
                raw.forEach((k, v) -> episode.put(String.valueOf(k), v));
                if ("active".equals(DeviceJson.textAt(episode, "state"))) {
                    String code = DeviceJson.textAt(episode, "code");
                    if (code != null) {
                        activeByCode.put(code, entry.getKey());
                    }
                }
            }
        }

        List<Map<String, Object>> incidents = body.incidents() == null
                ? List.of() : body.incidents();
        for (Map<String, Object> incident : incidents) {
            if (incident == null) {
                continue;
            }
            String code = DeviceJson.textAt(incident, "code");
            if (code == null || code.isBlank()) {
                continue;
            }
            String incidentId = activeByCode.get(code);
            if (isClear(incident)) {
                if (incidentId != null) {
                    markResolved(latestEpisodes.get(incidentId), now);
                    markResolved(activeCopy.get(incidentId), now);
                    activeByCode.remove(code);
                }
            } else if (incidentId != null) {
                touch(latestEpisodes.get(incidentId), incident, seq, now);
                touchActive(activeCopy.get(incidentId), incident, now);
            } else {
                String newId = UUID.randomUUID().toString();
                Map<String, Object> full = newEpisode(incident, code, seq, now);
                latestEpisodes.put(newId, full);
                activeCopy.put(newId, summarize(full));
                activeByCode.put(code, newId);
            }
        }
        return new EpisodeOutcome(latestEpisodes, activeCopy);
    }

    private static boolean isClear(Map<String, Object> incident) {
        String state = DeviceJson.textAt(incident, "state");
        if ("cleared".equalsIgnoreCase(state) || "resolved".equalsIgnoreCase(state)) {
            return true;
        }
        Object cleared = incident.get("cleared");
        return Boolean.TRUE.equals(cleared)
                || "true".equalsIgnoreCase(String.valueOf(cleared));
    }

    private static void markResolved(Object raw, Instant now) {
        if (raw instanceof Map<?, ?> m) {
            @SuppressWarnings("unchecked")
            Map<String, Object> episode = (Map<String, Object>) m;
            episode.put("state", "resolved");
            episode.put("resolved_at", EnvelopeSupport.rfc3339(now));
        }
    }

    private static void touch(Object raw, Map<String, Object> incident, long seq, Instant now) {
        if (raw instanceof Map<?, ?> m) {
            @SuppressWarnings("unchecked")
            Map<String, Object> episode = (Map<String, Object>) m;
            episode.put("last_reported_at", EnvelopeSupport.rfc3339(now));
            episode.put("last_reported_seq", seq);
            if (incident.get("severity") != null) {
                episode.put("severity", incident.get("severity"));
            }
            if (incident.get("detail") instanceof Map) {
                episode.put("detail", incident.get("detail"));
            }
        }
    }

    private static void touchActive(Object raw, Map<String, Object> incident, Instant now) {
        if (raw instanceof Map<?, ?> m) {
            @SuppressWarnings("unchecked")
            Map<String, Object> episode = (Map<String, Object>) m;
            episode.put("last_reported_at", EnvelopeSupport.rfc3339(now));
            if (incident.get("severity") != null) {
                episode.put("severity", incident.get("severity"));
            }
        }
    }

    private static Map<String, Object> newEpisode(Map<String, Object> incident, String code,
                                                  long seq, Instant now) {
        Map<String, Object> episode = new LinkedHashMap<>();
        episode.put("source", "device");
        episode.put("code", code);
        episode.put("severity", incident.get("severity"));
        episode.put("detail", incident.get("detail") instanceof Map
                ? incident.get("detail") : new LinkedHashMap<>());
        episode.put("opened_at", EnvelopeSupport.rfc3339(now));
        episode.put("last_reported_at", EnvelopeSupport.rfc3339(now));
        episode.put("last_reported_seq", seq);
        episode.put("state", "active");
        episode.put("resolved_at", null);
        return episode;
    }

    /** active_incidents 的 episode 摘要：只含设备状态字段，不含 detail/last_reported_seq。 */
    private static Map<String, Object> summarize(Map<String, Object> episode) {
        Map<String, Object> summary = new LinkedHashMap<>();
        summary.put("source", episode.get("source"));
        summary.put("code", episode.get("code"));
        summary.put("severity", episode.get("severity"));
        summary.put("opened_at", episode.get("opened_at"));
        summary.put("last_reported_at", episode.get("last_reported_at"));
        summary.put("state", episode.get("state"));
        summary.put("resolved_at", episode.get("resolved_at"));
        return summary;
    }

    private static long parseBigint(String value) {
        try {
            return Long.parseLong(value);
        } catch (NumberFormatException e) {
            throw new ApiException(ErrorCode.INVALID_INPUT,
                    "observationSeq out of bigint range");
        }
    }

    private static ApiException notVisible() {
        return new ApiException(ErrorCode.RESOURCE_NOT_VISIBLE, NOT_VISIBLE_MESSAGE);
    }
}
