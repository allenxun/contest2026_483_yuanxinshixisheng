package cn.yuanxin.mvp.web.devices;

import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

/**
 * 服务端观察会话代次表（Oracle 第二轮 #2 + 第三轮 BLOCKER）。
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
 * <p><b>有界性与表满 fail closed（Oracle 第三轮 BLOCKER）</b>：会话表<b>只增不减</b>
 * ——绝不淘汰仍可能有效的旧 session（淘汰后再出现会被赋新最高 generation，重新打开
 * epoch 回滚）。当表中已跟踪的 session 数达到配置上限
 * （{@code app.devices.max-observation-sessions}，默认 8）且来方 session
 * <b>不在表中</b>（服务端从未见过）时，返回 {@link Relation#TABLE_FULL}：
 * 调用方必须拒绝该次上报、不追加该 session、不写任何列。表中已有的 session（含当前
 * 最高 generation 者）不受影响，继续按既有规则判定。<b>唯一恢复途径</b>是
 * {@code credentialVersion} 严格推进：清空会话表、当前 session 记 {@code generation=1}
 * 并接受。该方向为 fail-closed，与本项目 deny-by-default 一致。</p>
 */
final class ObservationSessions {

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
        STALE,
        /** 表满且该 session 从未被服务端见过：fail closed，拒绝且不追加、不写库。 */
        TABLE_FULL
    }

    /** 本次请求的代次判定结果（sessions 为按 generation 升序、只增不减的会话表）。 */
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
     *
     * @param maxSessions 会话表上限（{@code app.devices.max-observation-sessions}）；
     *                    达到上限后对未见 session 返回 {@link Relation#TABLE_FULL}。
     */
    static Resolution resolve(Object rawSessions, Long recordedCredentialVersion,
                              Long recordedGeneration, long incomingCredentialVersion,
                              String sessionId, int maxSessions) {
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
            if (sessions.size() >= maxSessions) {
                // 表满且从未见过该 session：fail closed。绝不追加、绝不淘汰旧会话、不写库。
                int currentGeneration = recordedGeneration == null ? 0 : recordedGeneration.intValue();
                return new Resolution(Relation.TABLE_FULL, currentGeneration, sessions);
            }
            generation = maxGeneration(sessions) + 1;
            sessions.add(new Session(sessionId, generation));
        }
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
}
