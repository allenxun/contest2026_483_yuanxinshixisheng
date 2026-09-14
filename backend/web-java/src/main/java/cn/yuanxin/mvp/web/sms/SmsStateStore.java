package cn.yuanxin.mvp.web.sms;

import java.time.Instant;
import java.util.Optional;

/**
 * 阿里云短信状态存储端口（challenge 生命周期、一次性核销、尝试上限、三窗口节流）。
 *
 * <p><b>为什么抽端口</b>：{@link AliyunSmsCodeProvider} 只负责"生成随机码、调远端、
 * 按 {@code Code==OK} 判定受理、把失败映射为 HTTP"，把<b>状态</b>（challenge 与节流计数）
 * 留给本端口。由此得到两个实现：{@link InMemorySmsStateStore}（逐字保留既有进程内语义，
 * 仅供隔离测试 / {@code app.state.provider=memory}）与 {@link RedisSmsStateStore}
 * （跨实例一致、重启不丢，{@code app.state.provider=redis}）。</p>
 *
 * <p><b>为什么 {@code reserveSend} 需要配套的 {@code releaseSend}</b>：跨实例无法用进程内锁把
 * "预检 → 远端发送 → 记录受理" 串行化，因此 Redis 实现改为<b>原子预留 + 失败补偿</b>：
 * {@link #reserveSend(String, Instant)} 用一个 Lua 原子地检查并占用三个窗口名额（并发下绝不超发），
 * 远端发送<b>未被受理</b>时由 {@link #releaseSend(SendReservation, boolean)} 用另一个 Lua 原子回退。
 * 这是相对旧实现的一处<b>有意的语义精化</b>：稳态计数仍等于受理成功的发送数，差别只在
 * "发送失败瞬间名额被短暂占用"，方向更严格（见 {@code backend/handoffs/B-redis-state-migration.md} §4）。</p>
 *
 * <p><b>业务判定不用异常通道</b>：验证码错误 / 过期 / 超上限一律以 {@link Optional#empty()}
 * 表达；限流以 {@link SendReservation#granted()} 为 false 的正常返回值表达。存储后端故障才由
 * {@link cn.yuanxin.mvp.web.state.RedisFailures} 翻译为 503，绝不被误判为"验证码错误"。</p>
 *
 * <p><b>脱敏</b>：手机号只在值中出现（核销成功必须返回它才能建会话），绝不出现在键、日志或异常
 * 消息里；验证码明文绝不落存储（Redis 存 {@code sha256(code + "|" + challengeId)}）。</p>
 */
public interface SmsStateStore {

    /**
     * 原子地检查并按需预留三个节流窗口（分钟 / 小时 / 日，UTC+8 自然边界）。
     *
     * @return {@link SendReservation#granted()} 为 true 表示已预留（内存实现同时持有该手机号的
     *         条带锁与容量名额，必须最终调用 {@link #releaseSend}）；否则为限流，携带 retry-after 秒数
     */
    SendReservation reserveSend(String phone, Instant now);

    /**
     * 远端发送<b>已被平台受理</b>后记录（Redis 实现的预留计数即受理计数，故为 no-op；
     * 内存实现记录 {@code acceptedSends} 历史）。
     */
    void commitSend(SendReservation reservation, Instant now);

    /**
     * 释放一次预留：内存实现释放条带锁与容量名额；Redis 实现在 {@code accepted} 为 false 时
     * 原子回退三个窗口计数（预留 + 失败补偿），为 true 时不做任何事。
     */
    void releaseSend(SendReservation reservation, boolean accepted);

    /**
     * 创建 challenge（已持有 {@code reservation}）。Redis 实现写哈希 + TTL 一次完成且仅当不存在；
     * 内存实现写入进程内 map（容量名额已在 {@link #reserveSend} 预留）。
     *
     * @param challengeId 服务端生成的 challengeId（同时作为验证码摘要的盐）
     * @param phone       手机号（唯一 PII，值中存储）
     * @param code        明文验证码（内存实现直接存、Redis 实现只存摘要；<b>绝不</b>入日志）
     */
    void createChallenge(String challengeId, String phone, String code, Instant now, int ttlSeconds);

    /**
     * 原子地核销：不存在 / 已过期 / 超尝试上限 / 摘要不匹配 ⇒ {@link Optional#empty()}；
     * 匹配 ⇒ 一次性删除并返回手机号。
     */
    Optional<String> consumeChallenge(String challengeId, String code, Instant now, int maxAttempts);

    /**
     * 一次发送预留的结果。
     *
     * <p>普通 Java 对象而非 record：{@code handle} 是实现私有句柄（内存实现为条带锁，
     * Redis 实现为三个窗口键），provider 只读取 {@link #granted()} / {@link #retryAfterSeconds()}。</p>
     */
    final class SendReservation {

        private final String phone;
        private final boolean granted;
        private final long retryAfterSeconds;
        private final Object handle;

        private SendReservation(String phone, boolean granted, long retryAfterSeconds, Object handle) {
            this.phone = phone;
            this.granted = granted;
            this.retryAfterSeconds = retryAfterSeconds;
            this.handle = handle;
        }

        static SendReservation granted(String phone, Object handle) {
            return new SendReservation(phone, true, 0L, handle);
        }

        static SendReservation throttled(long retryAfterSeconds) {
            return new SendReservation(null, false, Math.max(1L, retryAfterSeconds), null);
        }

        /** 是否已预留（false 表示被本地节流拒绝，应映射为 429）。 */
        public boolean granted() {
            return granted;
        }

        /** 被拒绝时建议的 retry-after 秒数；已预留时为 0。 */
        public long retryAfterSeconds() {
            return retryAfterSeconds;
        }

        String phone() {
            return phone;
        }

        Object handle() {
            return handle;
        }
    }
}
