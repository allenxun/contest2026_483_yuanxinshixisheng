package cn.yuanxin.mvp.web.idempotency;

/** T13 代次守卫失败：attempt 已被接管/已完成，业务事务必须整体回滚。 */
public class StaleAttemptException extends RuntimeException {
    public StaleAttemptException(String message) {
        super(message, null, true, false);
    }
}
