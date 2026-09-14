package cn.yuanxin.mvp.web.state;

import java.io.PrintStream;

/**
 * L3 清理编排的<b>纯函数</b>（包级可见，便于直接单测，不需要 Spring/Redis）：
 * 依次执行 Redis 删除 → SCAN 复核 → DB 删除，且<b>全部步骤都会执行完</b>，最后判定：
 * <b>只要任一步骤抛出异常（或 SCAN 无法复核）就抛 {@link IllegalStateException}</b>
 * ——清理失败必须让 L3 <b>FAIL</b>，绝不能只打印却 PASS；其余异常以
 * {@link Throwable#addSuppressed} 保留。输出只含计数与异常类名，<b>绝不</b>含键名/手机号/token。
 *
 * <p>注意：本类不得改变原 `RedisLoginLiveAcceptanceIT.cleanup` 的行为（除"任一步骤失败即抛"这一修复）。</p>
 */
final class L3Cleanup {

    @FunctionalInterface
    interface RedisDelete {
        void run();
    }

    @FunctionalInterface
    interface RedisScan {
        int leftoverKeys();
    }

    /** 返回 {@code {destinationsDeleted, accountsDeleted}}。 */
    @FunctionalInterface
    interface DbDelete {
        int[] run();
    }

    private L3Cleanup() {
    }

    static void run(RedisDelete redisDelete, RedisScan redisScan, DbDelete dbDelete, PrintStream out) {
        Throwable failure = null;
        try {
            redisDelete.run();
        } catch (RuntimeException ex) {
            failure = ex;
        }

        int leftover;
        try {
            leftover = redisScan.leftoverKeys();
        } catch (RuntimeException ex) {
            failure = accumulate(failure, ex);
            leftover = -1;
        }

        int destinationsDeleted = 0;
        int accountsDeleted = 0;
        try {
            int[] counts = dbDelete.run();
            if (counts != null && counts.length >= 2) {
                destinationsDeleted = counts[0];
                accountsDeleted = counts[1];
            }
        } catch (RuntimeException ex) {
            failure = accumulate(failure, ex);
            out.println("[l3-cleanup] db-cleanup-error exception=" + ex.getClass().getSimpleName());
        }

        String leftoverText = leftover < 0 ? "unverified" : Integer.toString(leftover);
        out.println("[l3-cleanup] redisLeftover=" + leftoverText
                + " destinationsDeleted=" + destinationsDeleted
                + " accountsDeleted=" + accountsDeleted
                + (failure == null ? ""
                        : " cleanup-incomplete-suppressed=" + failure.getClass().getSimpleName()));

        // 只要任一步骤异常（failure != null）或 SCAN 复核非 0（含无法复核 = -1）就必须失败。
        if (failure != null || leftover != 0) {
            IllegalStateException incomplete = new IllegalStateException(
                    "cleanup incomplete: leftover keys under test prefix = "
                            + leftoverText + " (names not logged)");
            if (failure != null) {
                incomplete.addSuppressed(failure);
            }
            throw incomplete;
        }
    }

    private static Throwable accumulate(Throwable existing, RuntimeException next) {
        if (existing == null) {
            return next;
        }
        existing.addSuppressed(next);
        return existing;
    }
}
