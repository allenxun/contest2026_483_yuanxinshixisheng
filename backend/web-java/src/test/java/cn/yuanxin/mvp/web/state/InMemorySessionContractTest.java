package cn.yuanxin.mvp.web.state;

import cn.yuanxin.mvp.web.auth.SessionProvider;
import cn.yuanxin.mvp.web.testdouble.InMemorySessionDouble;
import org.springframework.jdbc.core.JdbcTemplate;

/**
 * 契约测试的内存后端执行：同一组断言跑在 {@link InMemorySessionDouble} 上（默认全量套件的一部分，
 * 不需要 Redis）。Redis 后端见 {@link RedisSessionContractIT}（opt-in）。
 */
class InMemorySessionContractTest extends SessionProviderContractTest {

    @Override
    protected SessionProvider createProvider(JdbcTemplate jdbc) {
        return new InMemorySessionDouble(jdbc);
    }
}
