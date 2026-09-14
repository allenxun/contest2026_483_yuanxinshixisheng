package cn.yuanxin.mvp.web.sms;

import org.junit.jupiter.api.Assumptions;
import org.junit.jupiter.api.BeforeAll;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;

import java.io.FileInputStream;
import java.io.IOException;
import java.io.InputStreamReader;
import java.io.Reader;
import java.nio.charset.StandardCharsets;
import java.security.SecureRandom;
import java.util.Map;
import java.util.Properties;

import static org.assertj.core.api.Assertions.fail;

/**
 * 一次性真实阿里云短信 smoke（<b>默认跳过；仅根可执行</b>）。
 *
 * <p><b>跳过条件（必须同时满足，任一不满足即 abort 并说明原因，绝不静默通过）：</b></p>
 * <ol>
 *   <li>{@code app.sms.provider=aliyun}；</li>
 *   <li>{@code app.integration-test.sms.phone} 非空（根的私有测试手机号）；</li>
 *   <li>显式 opt-in {@code app.sms.live-smoke=true}。</li>
 * </ol>
 *
 * <p><b>行为</b>：只发送 <b>一条</b>短信，断言阿里云业务 {@code Code} <b>严格等于 "OK"</b>
 * （平台受理，<b>不代表已送达</b>）。输出仅 {@code Code/Message/RequestId/BizId} 与<b>掩码</b>
 * 手机号；绝不输出验证码、AccessKey/Secret、完整手机号。<b>不得</b>以 HTTP 200 判定成功。</p>
 *
 * <p><b>配置来源</b>：系统属性 / 环境变量 / 可选 properties 文件
 * （{@code -Dapp.sms.smoke.config=/path/to/application-local.properties} 或环境变量
 * {@code APP_SMS_SMOKE_CONFIG}）—— 属性名与 Spring 完全一致。详见
 * {@code backend/handoffs/B-sms-aliyun.md}。</p>
 *
 * <p><b>编码（必读）</b>：该 properties 文件必须为 <b>UTF-8</b>，本类以显式 UTF-8
 * {@link Reader} 读取（见 {@link #readPropertiesFile(String)}），使中文 {@code sign-name}
 * 与中文模板参数名<b>逐字保持</b>。<b>不得</b>改回 {@code Properties.load(InputStream)}：
 * 它按规范以 ISO-8859-1 解码，会把 UTF-8 中文变成乱码后发给阿里云，平台随即以
 * {@code isv.SMS_SIGNATURE_ILLEGAL} 拒绝（这是 2026-09-14 真实 smoke 失败的根因）。
 * 回归守卫见 {@code AliyunSmsSmokeConfigEncodingTest}。</p>
 *
 * <p><b>本类不发起任何自动发送</b>，也<b>不</b>被常规 {@code mvn test} 实际执行（无 opt-in 即跳过）。
 * SmsSendGateway 由适配器真实实现，发送是计费接口。</p>
 */
class AliyunSmsLiveSmokeIT {

    private static final String PROVIDER_KEY = "app.sms.provider";
    private static final String PHONE_KEY = "app.integration-test.sms.phone";
    private static final String OPT_IN_KEY = "app.sms.live-smoke";
    private static final String CONFIG_FILE_KEY = "app.sms.smoke.config";

    private static Properties fileProperties;

    @BeforeAll
    static void requireExplicitOptIn() {
        if (!"aliyun".equalsIgnoreCase(config(PROVIDER_KEY))) {
            Assumptions.abort("live smoke skipped: " + PROVIDER_KEY + " is not 'aliyun'");
        }
        if (config(PHONE_KEY) == null || config(PHONE_KEY).isBlank()) {
            Assumptions.abort("live smoke skipped: " + PHONE_KEY + " is empty (no test phone)");
        }
        if (!"true".equalsIgnoreCase(config(OPT_IN_KEY))) {
            Assumptions.abort("live smoke skipped: " + OPT_IN_KEY + " is not 'true'");
        }
    }

    @Test
    @DisplayName("真实阿里云短信：只发一条并断言平台受理（Code==OK）")
    void sendsExactlyOneAndAssertsPlatformAccepted() {
        AliyunSmsProperties properties = new AliyunSmsProperties(
                config("app.sms.aliyun.endpoint"),
                config("app.sms.aliyun.region-id"),
                config("app.sms.aliyun.access-key-id"),
                config("app.sms.aliyun.access-key-secret"),
                config("app.sms.aliyun.security-token"),
                config("app.sms.aliyun.sign-name"),
                config("app.sms.aliyun.template-code"),
                config("app.sms.aliyun.template-param-name"),
                parsePositiveInt(config("app.sms.aliyun.connect-timeout-millis")),
                parsePositiveInt(config("app.sms.aliyun.read-timeout-millis")));
        if (!properties.missingRequiredKeys().isEmpty()) {
            fail("live smoke cannot run; missing config keys: " + properties.missingRequiredKeys());
        }

        String phone = config(PHONE_KEY);
        String code = randomCode();
        System.out.println("[live-smoke] sending ONE sms to " + SmsMasking.maskPhone(phone)
                + " (code not printed)");
        SendResult result = new AliyunSmsSendGateway(properties).send(phone, code);

        System.out.println("[live-smoke] code=" + result.code()
                + " message=" + result.message()
                + " requestId=" + result.requestId()
                + " bizId=" + result.bizId()
                + " phone=" + SmsMasking.maskPhone(phone));
        if (!result.accepted() || !"OK".equals(result.code())) {
            fail("aliyun sms NOT accepted (platform acceptance only). code=" + result.code()
                    + " message=" + result.message()
                    + " requestId=" + result.requestId()
                    + " (see B-sms-aliyun.md for failure-code interpretation)");
        }
    }

    private static String randomCode() {
        SecureRandom random = new SecureRandom();
        String code;
        do {
            code = String.format("%06d", random.nextInt(1_000_000));
        } while ("123456".equals(code));
        return code;
    }

    private static Integer parsePositiveInt(String raw) {
        if (raw == null || raw.isBlank()) {
            return null;
        }
        try {
            return Integer.valueOf(raw.trim());
        } catch (NumberFormatException invalid) {
            return null;
        }
    }

    /** 系统属性 → 环境变量（点转下划线大写）→ 可选 properties 文件。 */
    private static String config(String key) {
        String system = System.getProperty(key);
        if (system != null && !system.isBlank()) {
            return system;
        }
        String environment = System.getenv(key.toUpperCase(java.util.Locale.ROOT).replace('.', '_'));
        if (environment != null && !environment.isBlank()) {
            return environment;
        }
        return loadFileProperties().getProperty(key);
    }

    private static synchronized Properties loadFileProperties() {
        if (fileProperties != null) {
            return fileProperties;
        }
        String path = System.getProperty(CONFIG_FILE_KEY);
        if (path == null || path.isBlank()) {
            path = System.getenv(CONFIG_FILE_KEY.toUpperCase(java.util.Locale.ROOT).replace('.', '_'));
        }
        fileProperties = readPropertiesFile(path);
        return fileProperties;
    }

    /**
     * 以<b>显式 UTF-8</b> 读取 properties 文件（纯函数缝，便于回归测试且不触碰静态缓存）。
     *
     * <p><b>为何不能用 {@code Properties.load(InputStream)}</b>：该方法按 {@code java.util.Properties}
     * 规范以 <b>ISO-8859-1</b> 解码，UTF-8 的中文 {@code app.sms.aliyun.sign-name}（以及中文模板
     * 参数名）会变成乱码后被原样交给阿里云 SDK（{@code AliyunSmsSendGateway} 不做任何字符集处理），
     * 平台随即以 {@code isv.SMS_SIGNATURE_ILLEGAL} 拒绝——这是 2026-09-14 真实 smoke 失败的根因。
     * 改用 {@code InputStreamReader(in, UTF_8)} + {@code Properties.load(Reader)} 后中文逐字保持，
     * 且 Properties 规范的 unicode 转义序列（反斜杠 u + 四位十六进制）与反斜杠行连接语义不变。</p>
     *
     * <p>{@code path} 为 null/空白、或文件不存在/不可读时返回<b>空</b> {@code Properties}，
     * 且<b>绝不回显路径或文件内容</b>；由三重 opt-in 跳过条件处理，绝不静默发送。</p>
     */
    static Properties readPropertiesFile(String path) {
        Properties properties = new Properties();
        if (path == null || path.isBlank()) {
            return properties;
        }
        try (Reader reader = new InputStreamReader(new FileInputStream(path), StandardCharsets.UTF_8)) {
            properties.load(reader);
        } catch (IOException unreadable) {
            // 文件不可读时不回显路径内容；仅忽略，交由跳过条件处理。
        }
        return properties;
    }

    /** 供 javadoc/文档引用（避免未使用告警）。 */
    static Map<String, String> configKeys() {
        return Map.of("provider", PROVIDER_KEY, "phone", PHONE_KEY,
                "optIn", OPT_IN_KEY, "configFile", CONFIG_FILE_KEY);
    }
}
