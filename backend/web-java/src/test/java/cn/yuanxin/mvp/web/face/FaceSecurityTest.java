package cn.yuanxin.mvp.web.face;

import ch.qos.logback.classic.Logger;
import ch.qos.logback.classic.spi.ILoggingEvent;
import ch.qos.logback.core.read.ListAppender;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;
import org.slf4j.LoggerFactory;

import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.List;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.catchThrowable;

/** 脱敏硬约束测试：token 绝不进日志/异常/toString；图像字节/namespace/subjectRef 不进日志。 */
class FaceSecurityTest {

    private static final String FAKE_TOKEN = "FAKE-INTERNAL-TOKEN-DO-NOT-USE";
    private static final String NAMESPACE = "openvela-mvp";
    private static final String SECRET_SUBJECT = "SECRET-SUBJECT-REF-DO-NOT-LEAK";
    private static final byte[] SYNTHETIC_IMAGE = "fake-image-content-0123".getBytes(StandardCharsets.UTF_8);

    private FaceServiceStub stub;

    @BeforeEach
    void setUp() throws IOException {
        stub = new FaceServiceStub();
        stub.start();
    }

    @AfterEach
    void tearDown() {
        stub.close();
    }

    @Test
    @DisplayName("InsightFaceProperties.toString 脱敏 token")
    void insightFaceToStringRedactsToken() {
        InsightFaceProperties props = new InsightFaceProperties("http://10.3.6.163:8010", "openvela-mvp",
                FAKE_TOKEN, null, null, null, null);
        assertThat(props.toString()).doesNotContain(FAKE_TOKEN).contains("<redacted>");
    }

    @Test
    @DisplayName("AliyunFaceProperties.toString 脱敏 AK/SK/token")
    void aliyunToStringRedactsSecrets() {
        AliyunFaceProperties props = new AliyunFaceProperties("cn-hangzhou", "https://example.invalid",
                "LTAI-FAKE-DO-NOT-USE", "FAKE-SECRET-DO-NOT-USE", "FAKE-STS-DO-NOT-USE", "face");
        String text = props.toString();
        assertThat(text).doesNotContain("LTAI-FAKE-DO-NOT-USE")
                .doesNotContain("FAKE-SECRET-DO-NOT-USE")
                .doesNotContain("FAKE-STS-DO-NOT-USE");
    }

    @Test
    @DisplayName("token 文件读取可用，且 toString 不泄露其值")
    void tokenFileResolvedAndRedacted(@TempDir Path tempDir) throws IOException {
        Path tokenFile = tempDir.resolve("fake.token");
        Files.writeString(tokenFile, FAKE_TOKEN + "\n", StandardCharsets.UTF_8);
        InsightFaceProperties props = new InsightFaceProperties("http://10.3.6.163:8010", "openvela-mvp",
                null, tokenFile.toString(), null, null, null);
        assertThat(props.resolvedToken()).isEqualTo(FAKE_TOKEN);
        assertThat(props.toString()).doesNotContain(FAKE_TOKEN);
    }

    @Test
    @DisplayName("调用失败：日志与异常消息不含 token、不含图像字节")
    void logsAndMessagesDoNotContainTokenOrImage() {
        Logger logger = (Logger) LoggerFactory.getLogger(FaceServiceClient.class);
        ListAppender<ILoggingEvent> appender = new ListAppender<>();
        appender.start();
        logger.addAppender(appender);
        try {
            stub.extract(401, FaceServiceStub.errorBody("UNAUTHORIZED", false, "r-sec"));
            InsightFaceProperties props = new InsightFaceProperties(stub.baseUrl(), "openvela-mvp",
                    FAKE_TOKEN, null, 1500, 1500, null);
            FaceServiceClient client = new FaceServiceClient(props, new ObjectMapper());

            Throwable failure = catchThrowable(() -> client.extract("grant", SYNTHETIC_IMAGE));
            assertThat(failure).isInstanceOf(FaceServiceException.class);
            assertThat(failure.getMessage()).doesNotContain(FAKE_TOKEN)
                    .doesNotContain(new String(SYNTHETIC_IMAGE, StandardCharsets.UTF_8));
            for (ILoggingEvent event : appender.list) {
                assertThat(event.getFormattedMessage())
                        .doesNotContain(FAKE_TOKEN)
                        .doesNotContain(new String(SYNTHETIC_IMAGE, StandardCharsets.UTF_8));
            }
            // 真值确实随请求头发送（证明脱敏不是靠"没带 token"）。
            assertThat(stub.last("POST", "/v1/extract").internalToken()).isEqualTo(FAKE_TOKEN);
        } finally {
            logger.detachAppender(appender);
        }
    }

    @Test
    @DisplayName("新方法失败：日志与异常消息不含 token、图像字节、namespace、subjectRef 取值")
    void newOperationsDoNotLeakSecrets() {
        Logger logger = (Logger) LoggerFactory.getLogger(FaceServiceClient.class);
        ListAppender<ILoggingEvent> appender = new ListAppender<>();
        appender.start();
        logger.addAppender(appender);
        try {
            InsightFaceProperties props = new InsightFaceProperties(stub.baseUrl(), NAMESPACE,
                    FAKE_TOKEN, null, 1500, 1500, 0.4);
            FaceServiceClient client = new FaceServiceClient(props, new ObjectMapper());

            stub.search(401, FaceServiceStub.errorBody("UNAUTHORIZED", false, "r-search"));
            Throwable searchFailure = catchThrowable(() -> client.search("grant", SYNTHETIC_IMAGE));
            assertThat(searchFailure).isInstanceOf(FaceServiceException.class);

            stub.verify(401, FaceServiceStub.errorBody("UNAUTHORIZED", false, "r-photo"));
            Throwable photoFailure = catchThrowable(() ->
                    client.verifyPhotoOnly("grant", SECRET_SUBJECT, SYNTHETIC_IMAGE));
            assertThat(photoFailure).isInstanceOf(FaceServiceException.class);

            stub.register(401, FaceServiceStub.errorBody("UNAUTHORIZED", false, "r-reg"));
            Throwable registerFailure = catchThrowable(() ->
                    client.register("enroll", SECRET_SUBJECT, SYNTHETIC_IMAGE));
            assertThat(registerFailure).isInstanceOf(FaceServiceException.class);

            String imageText = new String(SYNTHETIC_IMAGE, StandardCharsets.UTF_8);
            for (Throwable failure : List.of(searchFailure, photoFailure, registerFailure)) {
                assertThat(failure.getMessage()).doesNotContain(FAKE_TOKEN)
                        .doesNotContain(imageText)
                        .doesNotContain(SECRET_SUBJECT)
                        .doesNotContain(NAMESPACE);
            }
            for (ILoggingEvent event : appender.list) {
                assertThat(event.getFormattedMessage())
                        .doesNotContain(FAKE_TOKEN)
                        .doesNotContain(imageText)
                        .doesNotContain(SECRET_SUBJECT)
                        .doesNotContain(NAMESPACE);
            }
        } finally {
            logger.detachAppender(appender);
        }
    }
}
