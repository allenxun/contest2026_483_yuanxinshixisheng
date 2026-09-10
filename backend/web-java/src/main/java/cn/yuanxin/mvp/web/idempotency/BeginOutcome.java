package cn.yuanxin.mvp.web.idempotency;

import com.fasterxml.jackson.databind.JsonNode;

import java.util.UUID;

/**
 * {@link IdempotencyService#begin} 的结果（DD 3.3 行为分支）。
 */
public sealed interface BeginOutcome {

    /** 全新请求或过期租约接管后的新尝试：handle 携带代次，业务事务内 complete。 */
    record NewAttempt(IdempotencyHandle handle) implements BeginOutcome {
    }

    /** 同键同内容且原请求已成功：定位原资源，由调用方按当前状态投影 + meta.replayed=true。 */
    record ReplaySucceeded(String resourceType, UUID resourceId, JsonNode resultSummary)
            implements BeginOutcome {
    }

    /** 同键同内容且原请求被确定性拒绝：重放原拒绝（新键才能表达新意图）。 */
    record ReplayRejected(String code, String message, boolean retryable, JsonNode details)
            implements BeginOutcome {
    }
}
