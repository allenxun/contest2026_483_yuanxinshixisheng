package cn.yuanxin.mvp.web.state;

import ch.qos.logback.classic.Logger;
import ch.qos.logback.classic.spi.ILoggingEvent;
import ch.qos.logback.core.read.ListAppender;
import cn.yuanxin.mvp.web.error.ApiException;
import cn.yuanxin.mvp.web.error.ErrorCode;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;
import org.slf4j.LoggerFactory;
import org.springframework.dao.QueryTimeoutException;
import org.springframework.data.redis.RedisConnectionFailureException;
import org.springframework.data.redis.RedisSystemException;

import java.util.List;
import java.util.stream.Collectors;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.catchThrowable;

/**
 * {@link RedisFailures} 日志脱敏与白名单错误码测试：绝不记录异常 {@code getMessage()}
 * （含 host:port / 口令样式 / 中文 / 换行），只允许白名单固定词或 {@code <unclassified>}。
 */
class RedisFailuresTest {

    private Logger logger;
    private ListAppender<ILoggingEvent> appender;

    @BeforeEach
    void attach() {
        logger = (Logger) LoggerFactory.getLogger(RedisFailures.class);
        appender = new ListAppender<>();
        appender.start();
        logger.addAppender(appender);
    }

    @AfterEach
    void detach() {
        logger.detachAppender(appender);
    }

    @Test
    @DisplayName("连接失败：日志不含 host/port/口令/URL，只含 operation 与异常类名")
    void connectionFailureIsRedacted() {
        String message = "Unable to connect to redis://user:secret@10.0.0.9:6379/5";
        Throwable thrown = catchThrowable(() -> RedisFailures.call("authenticate", () -> {
            throw new RedisConnectionFailureException(message);
        }));
        assertThat(thrown).isInstanceOf(ApiException.class);
        assertThat(((ApiException) thrown).getCode()).isEqualTo(ErrorCode.DEPENDENCY_UNAVAILABLE);
        assertThat(logs()).contains("operation=authenticate")
                .contains("RedisConnectionFailureException");
        assertNoSensitive(logs());
    }

    @Test
    @DisplayName("RedisSystemException 携带拓扑/口令/中文/换行 ⇒ 只记 <unclassified>")
    void systemExceptionWithTopologyIsUnclassified() {
        String message = "boom host=10.0.0.9:6379 password=secret 中文\nsecond line";
        catchThrowable(() -> RedisFailures.call("op", () -> {
            throw new RedisSystemException(message, new IllegalStateException(message));
        }));
        assertThat(logs()).contains("operation=op").contains("serverCode=<unclassified>");
        assertNoSensitive(logs());
        assertThat(logs()).doesNotContain("中文").doesNotContain("second line");
    }

    @Test
    @DisplayName("白名单：DB index out of range / WRONGPASS 只记固定词")
    void whitelistCodesAreExtracted() {
        assertThat(RedisFailures.whitelistedServerCode(new RedisSystemException(
                "ERR DB index is out of range: host=10.0.0.9:6379", null)))
                .isEqualTo("DB index is out of range");
        assertThat(RedisFailures.whitelistedServerCode(new RedisSystemException(
                "WRONGPASS invalid username-password pair or user is disabled. host=10.0.0.9", null)))
                .isEqualTo("WRONGPASS");
        assertThat(RedisFailures.whitelistedServerCode(new RedisSystemException("nothing known", null)))
                .isEqualTo("<unclassified>");

        catchThrowable(() -> RedisFailures.call("op", () -> {
            throw new RedisSystemException(
                    "WRONGPASS invalid username-password pair host=10.0.0.9", null);
        }));
        assertThat(logs()).contains("serverCode=WRONGPASS");
        assertThat(logs()).doesNotContain("invalid username-password").doesNotContain("10.0.0.9");
    }

    @Test
    @DisplayName("命令超时：日志只含类名与 operation")
    void queryTimeoutIsRedacted() {
        catchThrowable(() -> RedisFailures.call("verify-challenge", () -> {
            throw new QueryTimeoutException("timeout connecting 10.0.0.9:6379");
        }));
        assertThat(logs()).contains("operation=verify-challenge").contains("QueryTimeoutException");
        assertNoSensitive(logs());
    }

    @Test
    @DisplayName("非后端故障（代码缺陷）原样抛出且不写日志")
    void nonStoreFailureIsNotTranslatedOrLogged() {
        IllegalStateException defect = new IllegalStateException("bug host=10.0.0.9");
        RuntimeException returned = RedisFailures.failClosed("op", defect);
        assertThat(returned).isSameAs(defect);
        assertThat(appender.list).isEmpty();
    }

    private String logs() {
        return appender.list.stream().map(ILoggingEvent::getFormattedMessage)
                .collect(Collectors.joining("\n"));
    }

    private static void assertNoSensitive(String text) {
        List<String> forbidden = List.of("10.0.0.9", "6379", "secret", "redis://", "password");
        for (String token : forbidden) {
            assertThat(text).as("log must not contain '%s'", token).doesNotContain(token);
        }
    }
}
