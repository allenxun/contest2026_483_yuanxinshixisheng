package cn.yuanxin.mvp.web.idempotency;

import java.util.UUID;

/**
 * 一次 T13 处理凭据：行 id + 本次尝试的 attempt_revision（代次）。
 * completeSuccess/completeRejected 以 WHERE id AND attempt_revision 守卫；
 * 被接管后旧代次的完成尝试将回滚整个业务事务（StaleAttemptException）。
 */
public record IdempotencyHandle(UUID requestId, long attemptRevision) {
}
