package cn.yuanxin.mvp.web.sms;

import cn.yuanxin.mvp.web.error.ApiException;
import cn.yuanxin.mvp.web.error.ErrorCode;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;

import static org.assertj.core.api.Assertions.assertThat;
import static org.junit.jupiter.api.Assertions.assertThrows;

/**
 * Lua 返回码校验的单元测试：脚本返回非预期形状时<b>必须 fail-closed</b>（503
 * {@code DEPENDENCY_UNAVAILABLE}），绝不表现为"验证码错误"（401）或"无此挑战"，也绝不当作成功。
 *
 * <p>这些分支无法用真实 Redis 的合法脚本触发（脚本只会返回契约内取值），故直接对
 * {@link RedisSmsStateStore} 的静态校验函数断言；真实 Redis 侧的碰撞路径由
 * {@code RedisSmsStateStoreIT#createChallengeReportsCollision} 覆盖。</p>
 */
class RedisSmsStateStoreReturnValidationTest {

    private static void assertFailClosed(Throwable failure) {
        assertThat(failure).isInstanceOf(ApiException.class);
        ApiException api = (ApiException) failure;
        assertThat(api.getCode()).isEqualTo(ErrorCode.DEPENDENCY_UNAVAILABLE);
        assertThat(api.getHttpStatus()).isEqualTo(503);
    }

    @Test
    @DisplayName("reserve 返回 null / 负数 ⇒ fail-closed；0 ⇒ 已预留；>0 ⇒ retry-after")
    void reserveReturnValidation() {
        assertFailClosed(assertThrows(ApiException.class,
                () -> RedisSmsStateStore.retryAfterFromScriptResult(null)));
        assertFailClosed(assertThrows(ApiException.class,
                () -> RedisSmsStateStore.retryAfterFromScriptResult(-1L)));
        assertThat(RedisSmsStateStore.retryAfterFromScriptResult(0L)).isZero();
        assertThat(RedisSmsStateStore.retryAfterFromScriptResult(42L)).isEqualTo(42L);
    }

    @Test
    @DisplayName("补偿返回 null / 非 1 ⇒ fail-closed；1 ⇒ 通过")
    void compensateReturnValidation() {
        assertFailClosed(assertThrows(ApiException.class,
                () -> RedisSmsStateStore.requireCompensated(null)));
        assertFailClosed(assertThrows(ApiException.class,
                () -> RedisSmsStateStore.requireCompensated(0L)));
        RedisSmsStateStore.requireCompensated(1L); // 不抛
    }

    @Test
    @DisplayName("create 返回 null / 其它值 ⇒ fail-closed；1 ⇒ true；0 ⇒ false（碰撞）")
    void createReturnValidation() {
        assertFailClosed(assertThrows(ApiException.class,
                () -> RedisSmsStateStore.createdFromScriptResult(null)));
        assertFailClosed(assertThrows(ApiException.class,
                () -> RedisSmsStateStore.createdFromScriptResult(2L)));
        assertThat(RedisSmsStateStore.createdFromScriptResult(1L)).isTrue();
        assertThat(RedisSmsStateStore.createdFromScriptResult(0L)).isFalse();
    }

    @Test
    @DisplayName("consume 返回 null / 非契约形状 ⇒ fail-closed；'!' ⇒ empty；'+phone' ⇒ phone")
    void consumeReturnValidation() {
        assertFailClosed(assertThrows(ApiException.class,
                () -> RedisSmsStateStore.consumedFromScriptResult(null)));
        // 既不是 '!' 也不是 '+' 前缀：绝不能伪装成"验证码错误"（empty）。
        assertFailClosed(assertThrows(ApiException.class,
                () -> RedisSmsStateStore.consumedFromScriptResult("garbage")));
        // '+' 后没有手机号：视为后端异常，不得返回空串手机号。
        assertFailClosed(assertThrows(ApiException.class,
                () -> RedisSmsStateStore.consumedFromScriptResult("+")));

        assertThat(RedisSmsStateStore.consumedFromScriptResult("!")).isEmpty();
        // 真实协议是 '+' .. phone；phone 自身以 '+' 开头，故成功返回值形如 "++8610..."。
        assertThat(RedisSmsStateStore.consumedFromScriptResult("++8610000000000"))
                .contains("+8610000000000");
        assertThat(RedisSmsStateStore.consumedFromScriptResult("+123"))
                .contains("123");
    }
}
