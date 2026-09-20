package cn.yuanxin.mvp.web.state;

import cn.yuanxin.mvp.web.config.AppProperties;
import cn.yuanxin.mvp.web.config.NonProductionCondition;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.beans.BeansException;
import org.springframework.beans.factory.config.BeanFactoryPostProcessor;
import org.springframework.beans.factory.config.ConfigurableListableBeanFactory;
import org.springframework.context.EnvironmentAware;
import org.springframework.core.env.Environment;
import org.springframework.stereotype.Component;

import java.util.List;
import java.util.Set;

/**
 * 状态后端配置的<b>早期明确拒绝</b>（配置选择与诊断；沿用 {@code ProvidersModeProductionGuard}
 * 的 {@link BeanFactoryPostProcessor} + {@link EnvironmentAware} 范式，先于常规单例实例化，
 * 因此一定抢在"缺 SessionProvider"这类注入失败之前给出真正原因）。
 *
 * <p><b>三条规则</b>：</p>
 * <ol>
 *   <li><b>非法取值 fail fast</b>：{@code app.state.provider} 既不是 {@code memory} 也不是
 *       {@code redis} ⇒ 拒绝启动。若不在此拦截，非法值会让两个装配门（{@code havingValue="memory"}
 *       与 {@code havingValue="redis"}）<b>都不匹配</b>，最终表现为难诊断的缺 bean 错误；</li>
 *   <li><b>选了 redis 却没给连接配置</b>：{@code spring.data.redis.url} / {@code host} /
 *       {@code sentinel.master} / {@code cluster.nodes} <b>都未显式设置</b> ⇒ 拒绝启动。
 *       判据用 {@link Environment#containsProperty(String)}（只检测<b>是否显式配置</b>，
 *       绝不读取值；Boot 的 {@code RedisProperties.host} 默认 {@code localhost} 是 Java 字段默认值
 *       而非属性源，因此未显式配置时 {@code containsProperty} 返回 false）。
 *       这条规则让"忘记配置 Redis"变成启动期的清晰诊断，而不是运行期一切请求 503；</li>
 *   <li><b>生产 + real 模式必须用 Redis</b>：出现生产信号（生效 profiles 含
 *       {@code prod}/{@code production}，或 {@code app.env} trim 后忽略大小写等于
 *       {@code production}）<b>且</b> {@code app.providers.mode} 归一后为 {@code real}
 *       <b>且</b> {@code app.state.provider != redis} ⇒ 拒绝启动。这把"联调/真实 provider
 *       使用 Redis"从约定变成<b>可执行的门禁</b>：进程内会话状态在生产意味着重启丢会话、
 *       多实例互相不认，属实质缺陷。</li>
 *   <li><b>真实短信 provider 必须搭配 Redis</b>：{@code app.sms.provider=aliyun} <b>且</b>
 *       {@code app.state.provider != redis} ⇒ <b>无条件</b>拒绝启动。内存 challenge/限流计数
 *       不跨实例、重启即失效，一次性核销与限流会退化回单进程语义。<b>本规则没有运行时逃生门</b>：
 *       单元测试应不加载本守卫（直接构造 fake gateway + 内存 store），而不是放宽生产规则。</li>
 * </ol>
 *
 * <p><b>为什么规则 3 限定 {@code mode=real}</b>：生产 + {@code mode=doubles} 已由既有
 * {@code ProvidersModeProductionGuard} 明确拒绝（且多个既有测试锁定了它的异常与根因形态），
 * 本守卫不与之抢跑；生产 + {@code mode=disabled} 是"能力显式关闭 → 503"，
 * 此时会话能力本就不可用，状态后端选什么无关紧要，<b>不应</b>拒绝。</p>
 *
 * <p><b>消息纪律</b>：只输出键名、provider/mode 取值、生效 profiles 与 {@code app.env}；
 * 绝不输出 Redis 主机、端口、口令、数据库索引或任何凭据。</p>
 */
@Component
public class StateStoreConfigGuard implements BeanFactoryPostProcessor, EnvironmentAware {

    private static final Logger log = LoggerFactory.getLogger(StateStoreConfigGuard.class);

    /** 被视为"已显式给出连接配置"的标准 Spring Boot 属性（任一即可）。 */
    private static final List<String> CONNECTION_KEYS = List.of(
            "spring.data.redis.url",
            "spring.data.redis.host",
            "spring.data.redis.sentinel.master");

    /** Redis Cluster 节点属性：本轮**不支持**（多键 Lua 无共同 hash tag ⇒ 运行期必然 CROSSSLOT）。 */
    private static final String CLUSTER_NODES_KEY = "spring.data.redis.cluster.nodes";

    private Environment environment;

    @Override
    public void setEnvironment(Environment environment) {
        this.environment = environment;
    }

    @Override
    public void postProcessBeanFactory(ConfigurableListableBeanFactory beanFactory) throws BeansException {
        String rawProvider = environment.getProperty(AppStateProperties.PROVIDER_KEY);
        String provider;
        try {
            provider = AppStateProperties.normalizeProvider(rawProvider);
        } catch (IllegalArgumentException ex) {
            throw new IllegalStateException("state store fail-closed: " + ex.getMessage(), ex);
        }

        if (AppStateProperties.PROVIDER_REDIS.equals(provider)) {
            refuseClusterTopology();
            List<String> configured = CONNECTION_KEYS.stream()
                    .filter(key -> environment.containsProperty(key))
                    .toList();
            if (configured.isEmpty()) {
                String message = "state store fail-closed: " + AppStateProperties.PROVIDER_KEY
                        + "=redis requires an explicit Redis connection property, but none of "
                        + CONNECTION_KEYS + " is set (values are never logged);"
                        + " configure spring.data.redis.host (or .url / .sentinel.master)"
                        + " together with spring.data.redis.password and spring.data.redis.database";
                log.error(message);
                throw new IllegalStateException(message);
            }
            return;
        }

        // provider == memory：真实短信 provider 不得搭配内存状态（任何环境都适用，故置于
        // 非生产早退之前）。会话侧由下方 mode=real 规则与 TestDoubleProvidersConfig 互斥门覆盖。
        refuseRealSmsWithInMemoryState();

        if (NonProductionCondition.isNonProduction(environment)) {
            return;
        }
        String mode = new AppProperties.Providers(environment.getProperty("app.providers.mode")).mode();
        if (!"real".equals(mode)) {
            return;
        }
        Set<String> profiles = NonProductionCondition.effectiveProfiles(environment);
        String appEnv = environment.getProperty("app.env", "dev");
        String message = "state store fail-closed: " + AppStateProperties.PROVIDER_KEY + "="
                + (rawProvider == null ? "<unset, defaults to memory>" : rawProvider.trim())
                + " is not allowed under production signals with app.providers.mode=real"
                + " (effective-profiles=" + profiles + ", app.env=" + appEnv + ");"
                + " in-process session/verification state does not survive restarts and is not"
                + " shared across instances - configure " + AppStateProperties.PROVIDER_KEY
                + "=redis with spring.data.redis.*";
        log.error(message);
        throw new IllegalStateException(message);
    }

    /**
     * Redis Cluster 本轮**不支持**：8 个 Lua 脚本都访问多个键，而 cluster 要求同一脚本访问的键
     * 落在同一 hash slot（需要 {@code {tag}} 形式的 hash tag），否则运行期返回 {@code CROSSSLOT}。
     * 与其让它在运行期以难诊断的方式失败，不如在启动期明确拒绝。
     * Sentinel 与 standalone 是单 master，多键脚本成立，故允许。
     */
    private void refuseClusterTopology() {
        if (!environment.containsProperty(CLUSTER_NODES_KEY)) {
            return;
        }
        String message = "state store fail-closed: " + CLUSTER_NODES_KEY + " is set, but Redis Cluster"
                + " is NOT supported in this round - the session/SMS Lua scripts access multiple keys"
                + " and cluster requires them to share one hash slot (hash tags), otherwise every call"
                + " fails with CROSSSLOT at runtime; use a standalone or sentinel topology"
                + " (values are never logged)";
        log.error(message);
        throw new IllegalStateException(message);
    }

    /**
     * 真实短信 provider 搭配内存状态后端 ⇒ <b>无条件拒绝</b>（不存在任何公开逃生门/运行时开关）。
     * 内存状态意味着 challenge 与限流计数**不跨实例、重启即失效**，与"联调/真实 provider 使用 Redis"
     * 直接冲突；且一次性核销与限流的原子性会退化回单进程语义。跨实例一致性是硬要求，
     * <b>不接受</b>把它做成可被运行时配置绕过的规则。
     *
     * <p>单元测试应当<b>不加载本守卫</b>（直接构造 fake gateway + 内存 store 测编排逻辑），
     * 而不是放宽生产规则。</p>
     */
    private void refuseRealSmsWithInMemoryState() {
        String smsProvider = environment.getProperty("app.sms.provider");
        if (smsProvider == null || !"aliyun".equals(smsProvider.trim().toLowerCase(java.util.Locale.ROOT))) {
            return;
        }
        String message = "state store fail-closed: app.sms.provider=aliyun requires "
                + AppStateProperties.PROVIDER_KEY + "=redis, because in-process challenge/throttle state"
                + " is not shared across instances and does not survive restarts (one-time consumption and"
                + " rate limiting would degrade to per-process semantics); configure "
                + AppStateProperties.PROVIDER_KEY + "=redis with spring.data.redis.*."
                + " There is no runtime opt-out: unit tests must not load this guard (construct a fake"
                + " gateway plus an in-memory store directly) instead of loosening production rules"
                + " (values are never logged)";
        log.error(message);
        throw new IllegalStateException(message);
    }
}
