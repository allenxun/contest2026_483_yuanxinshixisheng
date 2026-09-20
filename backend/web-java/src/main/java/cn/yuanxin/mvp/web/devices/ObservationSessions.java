package cn.yuanxin.mvp.web.devices;

import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

/**
 * 服务端观察会话代次表（Oracle 第二轮 #2 + 第三轮 BLOCKER + 第四轮 BLOCKER）。
 *
 * <p><b>代次键（generation key）由调用方按主体类型选择</b>（本类只按传入键维护次序，
 * 不读取请求体）：</p>
 * <ul>
 *   <li><b>GIMBAL</b>：{@code sessionId}。随机 sessionId 只有唯一性、没有新旧次序，
 *       同一 {@code credential_version} 下可能并存多个未撤销会话；若把"不相等"当作
 *       "更新"则可来回回滚，故本类维护服务端见过它的先后次序。表满后对未见 session
 *       fail closed，唯一恢复途径是 {@code credential_version} 严格推进。</li>
 *   <li><b>APP</b>：稳定 family = {@code "<accountUuid>:<installationId>"}（即
 *       {@code Observer.ref}）。APP 的 {@code credentialVersion} 恒为 0 且每次
 *       refresh/login 都签发新 sessionId；若用 sessionId 作键，正常生命周期就会不断
 *       累积并最终耗尽（Oracle 第四轮）。改用稳定 family 后，同一 account+installation
 *       的任意次 refresh/login 都只映射到同一表项、generation 恒定，<b>永不累积、
 *       永不耗尽</b>；换账号/换安装实例才产生新 family（新表项、更高 generation、
 *       接受并重置 epoch/seq 基准），旧 family 因 generation 更低而永不重获权威。</li>
 * </ul>
 *
 * <p>代次只在三种服务端事实上推进：</p>
 * <ol>
 *   <li><b>凭据代次推进</b>：请求的 {@code credentialVersion} 严格大于已记录的
 *       {@code *_credential_version}——清空会话表，当前键记为 {@code generation=1}；</li>
 *   <li><b>首次观察</b>（无既有记录）：当前键记为 {@code generation=1}；</li>
 *   <li><b>服务端首次见到该键</b>：{@code generation = 表中最大值 + 1} 并追加。</li>
 * </ol>
 *
 * <p>比较规则：来方 generation &gt; 已记录 → 新连接，接受并重置 epoch/seq 基准；
 * == → 同一连接（调用方还须检查 epoch 一致且 seq 严格更大）；
 * &lt; → 旧连接，<b>一律拒绝，旧会话/旧 family 永不重获权威</b>。</p>
 *
 * <p><b>有界性与表满 fail closed（Oracle 第三/四轮）</b>：会话表<b>只增不减</b>——绝不
 * 淘汰仍可能有效的旧键（淘汰后再出现会被赋新最高 generation，重新打开回滚）。当表中
 * 已跟踪键数达到配置上限（{@code app.devices.max-observation-sessions}，默认 8）且来方
 * 键<b>不在表中</b>时，返回 {@link Relation#TABLE_FULL}：调用方必须拒绝该次上报、不追加
 * 该键、不写任何列。表中已有的键（含当前最高 generation 者）不受影响。<b>GIMBAL</b>
 * 侧唯一恢复途径是 {@code credential_version} 推进（Oracle 已判可接受）。<b>APP</b> 侧
 * 因 family 稳定，表项数 = 实际出现过的 account:installation 组合数，正常生命周期
 * 天然有界、永不耗尽；<b>残余边界</b>：若同一微晶被超过上限个不同 account:installation
 * 组合观察，则未见 family 会 fail closed。
 * <b>APP 侧没有自动恢复途径</b>——表满后"新 family"正是被拒绝的对象，故生产新的
 * account:installation 组合<b>并不能</b>恢复（Oracle 第五轮 IMPORTANT 纠正了此处先前
 * 的错误表述）。当前实际可用的恢复手段只有：① observer <b>类型</b>切换（APP↔云台）
 * 会清空代次表（见 {@code MicrocrystalService.decide} 的 typeChanged 分支）；
 * ② GIMBAL 侧 {@code credential_version} 推进；③ <b>受控运维重置</b>（按运维流程清空
 * 该行 {@code latest_observation} 中的代次表并留审计，不提供业务 API）；④ 待真实会话
 * 提供方或 {@code ConnectionProofVerifier} 提供可信 generation 后，由本表之外的权威
 * 取代（Oracle 方向①/②）。因此必须配套<b>容量告警</b>（warn 分支
 * {@code session-table-full-fail-closed}）与<b>受控恢复 runbook</b>；
 * <b>仅调高上限不是恢复机制</b>，只是推迟触顶。</p>
 *
 * <p><b>JSONB 键名与升级约束（Oracle 第五轮 SUGGESTION）</b>：代次表元素的 JSON 键沿用
 * {@code session_id}，但其值现在是"<b>代次键</b>"而非会话 ID——GIMBAL 为随机
 * {@code sessionId}，APP 为稳定 family {@code accountUuid:installationId}。保留旧键名
 * 只为避免无必要的格式迁移，名称已不准确，阅读 JSONB 时须按 {@code generation_key}
 * 理解。与早期中间版本（APP 也写随机 sessionId）<b>仅格式兼容、非语义兼容</b>：旧条目
 * 不会被 family 命中，却仍占用容量。故 <b>中间版本不得原地升级</b>；若已存在持久数据，
 * 须执行受控转换或重置（清空代次表，由首次观察重建 generation=1）。</p>
 */
final class ObservationSessions {

    private ObservationSessions() {
    }

    /** 服务端见过的一个代次键及其首次被观察到的次序。 */
    record Session(String generationKey, int generation) {
    }

    /** 本次请求相对服务端会话表的代次关系。 */
    enum Relation {
        /** 首次观察 / 凭据代次推进：接受并重置基准。 */
        FIRST_OR_ADVANCED,
        /** 服务端首次见到该键，或它比已记录更新：接受并重置基准。 */
        NEWER,
        /** 同一连接：调用方还需检查 epoch 一致且 seq 严格更大。 */
        SAME,
        /** 旧连接：一律拒绝，绝不覆盖。 */
        STALE,
        /** 表满且该键从未被服务端见过：fail closed，拒绝且不追加、不写库。 */
        TABLE_FULL
    }

    /** 本次请求的代次判定结果（sessions 为按 generation 升序、只增不减的代次表）。 */
    record Resolution(Relation relation, int generation, List<Session> sessions) {
    }

    /** 仅含当前代次键、generation=1 的全新代次表（来源变化重置时使用）。 */
    static List<Session> freshSessions(String generationKey) {
        List<Session> sessions = new ArrayList<>();
        sessions.add(new Session(generationKey, 1));
        return sessions;
    }

    /**
     * 依据服务端事实（既有代次表、已记录凭据代次、既有当前代次、本次凭据代次与代次键）
     * 计算本次请求的代次关系。绝不读取请求体 epoch/seq。
     *
     * @param generationKey 代次键：GIMBAL = sessionId；APP = 稳定 family
     *                      {@code "<accountUuid>:<installationId>"}。由调用方按主体类型
     *                      选择（见类注释），不得传入请求体字段。
     * @param maxSessions   代次表上限（{@code app.devices.max-observation-sessions}）；
     *                      达到上限后对未见键返回 {@link Relation#TABLE_FULL}。
     */
    static Resolution resolve(Object rawSessions, Long recordedCredentialVersion,
                              Long recordedGeneration, long incomingCredentialVersion,
                              String generationKey, int maxSessions) {
        List<Session> sessions = parseSessions(rawSessions);
        boolean credentialAdvanced = recordedCredentialVersion != null
                && incomingCredentialVersion > recordedCredentialVersion;
        if (recordedCredentialVersion == null || credentialAdvanced || sessions.isEmpty()) {
            // 首次 / 凭据代次推进 / 迁移前旧行：清空代次表，当前键 = generation 1。
            return new Resolution(Relation.FIRST_OR_ADVANCED, 1, freshSessions(generationKey));
        }
        Integer known = generationOf(sessions, generationKey);
        int generation;
        if (known != null) {
            generation = known;
        } else {
            if (sessions.size() >= maxSessions) {
                // 表满且从未见过该键：fail closed。绝不追加、绝不淘汰旧键、不写库。
                int currentGeneration = recordedGeneration == null ? 0 : recordedGeneration.intValue();
                return new Resolution(Relation.TABLE_FULL, currentGeneration, sessions);
            }
            generation = maxGeneration(sessions) + 1;
            sessions.add(new Session(generationKey, generation));
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

    /** 宽松解析代次表；缺键/形状不符的元素跳过，绝不抛。JSON 键沿用 {@code session_id}。 */
    @SuppressWarnings("unchecked")
    static List<Session> parseSessions(Object raw) {
        if (!(raw instanceof List<?> list)) {
            return new ArrayList<>();
        }
        List<Session> sessions = new ArrayList<>();
        for (Object item : list) {
            if (item instanceof Map<?, ?> map) {
                Object key = ((Map<String, Object>) map).get("session_id");
                Object generation = ((Map<String, Object>) map).get("generation");
                if (key instanceof String text && !text.isBlank()
                        && generation instanceof Number number) {
                    sessions.add(new Session(text, number.intValue()));
                }
            }
        }
        return sessions;
    }

    /** 代次表 → JSONB 数组（键为文本 + generation 整数）。 */
    static List<Map<String, Object>> toJson(List<Session> sessions) {
        List<Map<String, Object>> out = new ArrayList<>();
        for (Session session : sessions) {
            Map<String, Object> entry = new LinkedHashMap<>();
            entry.put("session_id", session.generationKey());
            entry.put("generation", session.generation());
            out.add(entry);
        }
        return out;
    }

    private static Integer generationOf(List<Session> sessions, String generationKey) {
        for (Session session : sessions) {
            if (session.generationKey().equals(generationKey)) {
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
