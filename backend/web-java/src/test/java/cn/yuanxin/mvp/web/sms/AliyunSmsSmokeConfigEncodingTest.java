package cn.yuanxin.mvp.web.sms;

import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

import java.io.ByteArrayInputStream;
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.Properties;

import static org.assertj.core.api.Assertions.assertThat;

/**
 * 回归守卫：真实短信 smoke 的配置文件必须以 <b>UTF-8</b> 读取，使中文短信签名与中文模板参数名
 * <b>逐字保持</b>。
 *
 * <p><b>历史缺陷（2026-09-14 真实 smoke 失败根因）</b>：{@code AliyunSmsLiveSmokeIT} 的
 * {@code loadFileProperties()} 曾用 {@code Properties.load(InputStream)}，该方法按
 * {@code java.util.Properties} 规范以 <b>ISO-8859-1</b> 解码 ⇒ UTF-8 的中文
 * {@code app.sms.aliyun.sign-name} 变成乱码后被原样交给阿里云 SDK（{@code AliyunSmsSendGateway}
 * 不做任何字符集处理），平台随即以 {@code isv.SMS_SIGNATURE_ILLEGAL} 拒绝。同一份阿里云配置在
 * 其它代码中可用，正是因为那些实现按 UTF-8 读取。</p>
 *
 * <p><b>本测试绝不发送任何短信</b>：只调用纯文件读取缝
 * {@link AliyunSmsLiveSmokeIT#readPropertiesFile(String)}，不构造 gateway、不触发三重 opt-in、
 * <b>不读取</b>根的私有 {@code application-local.properties} 或任何真实凭据/手机号；配置文件是
 * {@code @TempDir} 下自建的<b>合成</b>文件，签名与参数名均为明显的占位值。三重 opt-in
 * （{@code app.sms.provider=aliyun} + 非空 {@code app.integration-test.sms.phone} +
 * {@code app.sms.live-smoke=true}）与 {@code SmsMasking} 脱敏规则<b>均未改动</b>。</p>
 */
class AliyunSmsSmokeConfigEncodingTest {

    /** 合成占位值：非真实签名、非真实凭据、非真实手机号。 */
    private static final String SIGN_NAME = "测试签名请勿使用";
    private static final String PARAM_NAME = "验证码参数";

    private static String writeUtf8(Path dir, String name, String body) throws IOException {
        Path file = dir.resolve(name);
        Files.write(file, body.getBytes(StandardCharsets.UTF_8));
        return file.toString();
    }

    @Test
    @DisplayName("UTF-8 文件中的中文签名与中文模板参数名逐字保持")
    void chineseSignNameAndParamNameSurviveUtf8File(@TempDir Path dir) throws IOException {
        String path = writeUtf8(dir, "synthetic.properties", """
                app.sms.provider=aliyun
                app.sms.aliyun.sign-name=%s
                app.sms.aliyun.template-param-name=%s
                app.sms.aliyun.template-code=SMS_000000000
                """.formatted(SIGN_NAME, PARAM_NAME));

        Properties loaded = AliyunSmsLiveSmokeIT.readPropertiesFile(path);

        assertThat(loaded.getProperty("app.sms.aliyun.sign-name")).isEqualTo(SIGN_NAME);
        assertThat(loaded.getProperty("app.sms.aliyun.template-param-name")).isEqualTo(PARAM_NAME);
        // 字节级相等：排除"看起来像"的近似匹配（例如部分还原或归一化差异）。
        assertThat(loaded.getProperty("app.sms.aliyun.sign-name").getBytes(StandardCharsets.UTF_8))
                .isEqualTo(SIGN_NAME.getBytes(StandardCharsets.UTF_8));
        // 纯 ASCII 值不受影响（无回归）。
        assertThat(loaded.getProperty("app.sms.provider")).isEqualTo("aliyun");
        assertThat(loaded.getProperty("app.sms.aliyun.template-code")).isEqualTo("SMS_000000000");
    }

    @Test
    @DisplayName("判别力：旧的 ISO-8859-1 读法对同样字节会得到乱码，故本套断言能捕获回归")
    void oldIso88591ReadingManglesTheSameBytes(@TempDir Path dir) throws IOException {
        String path = writeUtf8(dir, "synthetic.properties",
                "app.sms.aliyun.sign-name=%s%n".formatted(SIGN_NAME));
        byte[] raw = Files.readAllBytes(Path.of(path));

        Properties viaInputStream = new Properties();
        try (ByteArrayInputStream in = new ByteArrayInputStream(raw)) {
            viaInputStream.load(in);          // 旧实现的等价路径（按规范以 ISO-8859-1 解码）
        }

        // 旧读法确实拿不到正确签名 ⇒ 证明上一项的断言不是恒真。
        assertThat(viaInputStream.getProperty("app.sms.aliyun.sign-name")).isNotEqualTo(SIGN_NAME);
        assertThat(new String(raw, StandardCharsets.ISO_8859_1)).doesNotContain(SIGN_NAME);
        // 新读法（显式 UTF-8）则逐字保持。
        assertThat(AliyunSmsLiveSmokeIT.readPropertiesFile(path)
                .getProperty("app.sms.aliyun.sign-name")).isEqualTo(SIGN_NAME);
    }

    @Test
    @DisplayName("unicode 转义与反斜杠行连接语义不变；空/缺失路径返回空 Properties 且不回显内容")
    void escapesLineContinuationAndUnreadablePathsStillBehave(@TempDir Path dir) throws IOException {
        // 文件中写入 Properties 规范的 unicode 转义序列（此处对应 U+84DD 与 U+89C6 两个中文字），
        // 用于证明改用 Reader 后转义语义未被破坏；源码中写双反斜杠以避免编译期 unicode 预处理。
        String path = writeUtf8(dir, "escapes.properties", """
                app.sms.aliyun.sign-name=\\u84dd\\u89c6
                app.sms.aliyun.multi=first\\
                        second
                """);

        Properties loaded = AliyunSmsLiveSmokeIT.readPropertiesFile(path);

        assertThat(loaded.getProperty("app.sms.aliyun.sign-name")).isEqualTo("蓝视");
        assertThat(loaded.getProperty("app.sms.aliyun.multi")).isEqualTo("firstsecond");

        // 路径缺失/空白/文件不存在：返回空 Properties（由三重 opt-in 跳过条件处理，绝不静默发送）。
        assertThat(AliyunSmsLiveSmokeIT.readPropertiesFile(null)).isEmpty();
        assertThat(AliyunSmsLiveSmokeIT.readPropertiesFile("   ")).isEmpty();
        assertThat(AliyunSmsLiveSmokeIT.readPropertiesFile(dir.resolve("missing.properties").toString()))
                .isEmpty();
    }
}
