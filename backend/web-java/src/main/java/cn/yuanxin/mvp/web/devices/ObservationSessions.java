package cn.yuanxin.mvp.web.devices;

import java.util.ArrayList;
import java.util.Comparator;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

/**
 * 服务端观察会话代次表（Oracle 第二轮 #2）。
 *
 * <p><b>为什么不能把 sessionId 的"不相等"当作"更新"</b>：sessionId 由服务端随机
 * 签发，只有唯一性、没有新旧次序。同一 {@code credential_version} 下可能同时存在
 * 多个均未被撤销的会话（A 的替身签发新 session 不使旧 session 失效；
 * {@code PrincipalRevalidator} 对 GIMBAL 只复核 {@code credential_version}）。若把
 * "sessionId 不同"视为新连接，则两个会话可交替以低 seq 覆盖彼此，来回回滚已接受的
 * 观察事实。</p>
 *
 * <p>本类维护的是 <b>服务端实际见到每个 session 的先后次序</b>：JSONB 内
 * {@code *_sessions} 形如
 * {@code [{"session_id":"...","generation":1},{"session_id":"...","generation":2}]}。
 * 代次只在两种服务端事实上推进：</p>
 * <ol>
 *   <li><b>凭据代次推进</b>：首次观察（无既有记录），或请求的
 *       {@code credentialVersion} 严格大于已记录的
 *       {@code *_credential_version}——清空会话表，当前 session 记为
 *       {@code generation=1}；</li>
 *   <li><b>服务端首次见到该 session</b>：{@code generation = 表中最大值 + 1} 并追加。</li>
 * </ol>
 *
 * <p>比较规则：来方 generation &gt; 已记录 → 新连接，接受并重置 epoch/seq 基准；
 * == → 同一连接（调用方还须检查 epoch 一致且 seq 严格更大）；
 * &lt; → 旧连接，<b>一律拒绝，旧会话永不重获权威</b>。因此 A(gen1)/B(gen2) 交替时，
 * B 被接受后 A 再来只会得到 generation=1 &lt; 2 → 拒绝，不再存在来回覆盖。</p>
 *
 * <p><b>有界性</b>：会话表最多保留 {@value #MAX_TRACKED_SESSIONS} 条，按 generation
 * 从大到小保留；新 session 总是成为最高 generation，故当前最高代次永不被淘汰。
 * 淘汰只影响"很久以前、且早已被更高代次取代"的会话；被淘汰的旧 session 若之后
 * 再次出现，会被当作"服务端首次见到的新会话"而获得更高 generation 并被接受——
 * 这是如实披露的边界，且 A 的会话本身有 2 小时有效期，风险有界。</p>
 */
final class ObservationSessions {

    /** 会话表上限：仅保留最近若干代，绝不淘汰当前最高代次。 */
    static final int MAX_TRACKED_SESSIONS = 8;

    private ObservationSessions() {
    }

    /** 服务端见过的一个会话及其首次被观察到的次序。 */
    record Session(String sessionId, int generation) {
    }

    /** 本次请求相对服务端会话表的代次关系。 */
    enum Relation {
        /** 首次观察 / 凭据代次推进：接受并重置基准。 */
        FIRST_OR_ADVANCED,
        /** 服务端首次见到该 session，或它比已记录更新：接受并重置基准。 */
        NEWER,
        /** 同一连接：调用方还需检查 epoch 一致且 seq 严格更大。 */
        SAME,
        /** 旧连接：一律拒绝，绝不覆盖。 */
        STALE
    }

    /** 本次请求的代次判定结果（sessions 为有界、按 generation 升序的会话表）。 */
    record Resolution(Relation relation, int generation, List<Session> sessions) {
    }

    /** 仅含当前 session、generation=1 的全新会话表（来源变化重置时使用）。 */
    static List<Session> freshSessions(String sessionId) {
        List<Session> sessions = new ArrayList<>();
        sessions.add(new Session(sessionId, 1));
        return sessions;
    }

    /**
     * 依据服务端事实（既有会话表、已记录凭据代次、既有当前代次、本次凭据代次与
     * sessionId）计算本次请求的代次关系。绝不读取请求体 epoch/seq。
     */
    static Resolution resolve(Object rawSessions, Long recordedCredentialVersion,
                              Long recordedGeneration, long incomingCredentialVersion,
                              String sessionId) {
        List<Session> sessions = parseSessions(rawSessions);
        boolean credentialAdvanced = recordedCredentialVersion != null
                && incomingCredentialVersion > recordedCredentialVersion;
        if (recordedCredentialVersion == null || credentialAdvanced || sessions.isEmpty()) {
            // 首次 / 凭据代次推进 / 迁移前旧行：清空会话表，当前 session = generation 1。
            return new Resolution(Relation.FIRST_OR_ADVANCED, 1, freshSessions(sessionId));
        }
        Integer known = generationOf(sessions, sessionId);
        int generation;
        if (known != null) {
            generation = known;
        } else {
            generation = maxGeneration(sessions) + 1;
            sessions.add(new Session(sessionId, generation));
        }
        sessions = prune(sessions);
        if (recordedGeneration == null) {
            return new Resolution(Relation.FIRST_OR_ADVANCED, generation, sessions);
        }
        if (generation > recordedGeneration) {
            return new Resolution(Relation.NEWER, generation, sessions);
        }
        if (generation == recordedGeneration) {
            return new Resolution(Relation.SAME, generation, sessions);
        }
        return new Resolution(Relation.STALE, generation, sessions);
    }

    /** 宽松解析会话表；缺键/形状不符的元素跳过，绝不抛。 */
    @SuppressWarnings("unchecked")
    static List<Session> parseSessions(Object raw) {
        if (!(raw instanceof List<?> list)) {
            return new ArrayList<>();
        }
        List<Session> sessions = new ArrayList<>();
        for (Object item : list) {
            if (item instanceof Map<?, ?> map) {
                Object sessionId = ((Map<String, Object>) map).get("session_id");
                Object generation = ((Map<String, Object>) map).get("generation");
                if (sessionId instanceof String text && !text.isBlank()
                        && generation instanceof Number number) {
                    sessions.add(new Session(text, number.intValue()));
                }
            }
        }
        return sessions;
    }

    /** 会话表 → JSONB 数组（session_id 文本 + generation 整数）。 */
    static List<Map<String, Object>> toJson(List<Session> sessions) {
        List<Map<String, Object>> out = new ArrayList<>();
        for (Session session : sessions) {
            Map<String, Object> entry = new LinkedHashMap<>();
            entry.put("session_id", session.sessionId());
            entry.put("generation", session.generation());
            out.add(entry);
        }
        return out;
    }

    private static Integer generationOf(List<Session> sessions, String sessionId) {
        for (Session session : sessions) {
            if (session.sessionId().equals(sessionId)) {
                return session.generation();
            }
        }
        return null;
    }

    private static int maxGeneration(List<Session> sessions) {
        int max = 0;
        for (Session session : sessions) {
            max = Math.max(max, session.generation());
        }
        return max;
    }

    /** 保留 generation 最大的至多 {@value #MAX_TRACKED_SESSIONS} 条，按代次升序返回。 */
    private static List<Session> prune(List<Session> sessions) {
        if (sessions.size() <= MAX_TRACKED_SESSIONS) {
            return sessions;
        }
        List<Session> byGenerationDesc = new ArrayList<>(sessions);
        byGenerationDesc.sort(Comparator.comparingInt(Session::generation).reversed());
        List<Session> kept = new ArrayList<>(byGenerationDesc.subList(0, MAX_TRACKED_SESSIONS));
        kept.sort(Comparator.comparingInt(Session::generation));
        return kept;
    }
}
