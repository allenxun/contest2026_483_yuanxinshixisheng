package cn.yuanxin.mvp.web.storage;

import cn.yuanxin.mvp.web.media.StoragePort;
import cn.yuanxin.mvp.web.testdouble.FileSystemStorageDouble;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

import java.io.ByteArrayInputStream;
import java.io.ByteArrayOutputStream;
import java.io.InputStream;
import java.io.PrintStream;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.List;
import java.util.Map;
import java.util.concurrent.ConcurrentHashMap;

import static org.assertj.core.api.Assertions.assertThat;

/**
 * {@link OssLiveSmoke} 本地回归（<b>绝不联网</b>、<b>绝不使用真实凭据</b>）：
 * 权威跨语言向量、键校验、输出净化、三重 opt-in、double 全流程，以及 live 阶段的注入式验证。
 */
class OssLiveSmokeTest {

    private static final String SEED = "b-oss-smoke-vector";
    private static final String VALID_KEY = "dev/assessment_result/00000000-0000-4000-8000-000000000000";
    private static final String BUCKET = "fake-bucket-do-not-use";
    private static final String SERVER_ENDPOINT = "https://oss-fake-server.example.com";
    private static final String PUBLIC_ENDPOINT = "https://oss-fake-public.example.com";
    private static final String AK = "LTAI-FAKE-DO-NOT-USE";
    private static final String SK = "FAKE-SECRET-DO-NOT-USE";
    private static final String STS = "FAKE-STS-DO-NOT-USE";

    // ------------------------------------------------------------ 1. 权威向量

    @Test
    @DisplayName("smokeBytes 与 Python 侧硬编码权威向量逐字一致（256/64/1）")
    void authoritativeVectorsMatchContract() {
        assertThat(OssLiveSmoke.sha256Hex(OssLiveSmoke.smokeBytes(SEED, 256)))
                .isEqualTo("0e46beb450377892dc132e1f97087b55311f042a8757d105c03a1a2030e14e32");
        assertThat(OssLiveSmoke.sha256Hex(OssLiveSmoke.smokeBytes(SEED, 64)))
                .isEqualTo("f3a9429115790ee322b3f4a20263f2c9e1ad286928c7f9fac6d4a6cd93c258fd");
        assertThat(OssLiveSmoke.sha256Hex(OssLiveSmoke.smokeBytes(SEED, 1)))
                .isEqualTo("0a43b22d89fa2499be5c7704c9bf273260b0ca9588e4cd1897cd80f9c96cd97a");
    }

    @Test
    @DisplayName("keyDigest 与契约示例一致（6ca2e86b3621）")
    void keyDigestMatchesContractExample() {
        assertThat(OssLiveSmoke.keyDigest(VALID_KEY)).isEqualTo("6ca2e86b3621");
    }

    // ------------------------------------------------------------ 2. 键校验

    @Test
    @DisplayName("合法对象键通过")
    void validObjectKeysAccepted() {
        assertThat(OssLiveSmoke.isValidObjectKey(VALID_KEY)).isTrue();
        assertThat(OssLiveSmoke.isValidObjectKey(
                "prod-1/assessment_result/abcdef01-2345-6789-abcd-ef0123456789")).isTrue();
        assertThat(OssLiveSmoke.isValidObjectKey(
                "a.b_c-1/assessment_result/abcdef01-2345-6789-abcd-ef0123456789")).isTrue();
    }

    @Test
    @DisplayName("非法对象键逐一拒绝（.. / 首尾斜杠 / 段数 / purpose / UUID / 大写）")
    void invalidObjectKeysRejected() {
        List<String> invalid = List.of(
                "dev/assessment_result/00000000-0000-4000-8000-00000000000",
                "dev/assessment_result/00000000-0000-4000-8000-0000000000000",
                "../assessment_result/00000000-0000-4000-8000-000000000000",
                "dev/assessment_result/00000000-0000-4000-8000-000000000000/",
                "/dev/assessment_result/00000000-0000-4000-8000-000000000000",
                "dev/grant_face/00000000-0000-4000-8000-000000000000",
                "dev/assessment_result",
                "dev/assessment_result/x/y",
                "DEV/assessment_result/00000000-0000-4000-8000-000000000000",
                "dev/assessment_result/00000000-0000-4000-8000-00000000000G",
                "dev/assessment_result/00000000000000000000000000000000",
                "a..b/assessment_result/00000000-0000-4000-8000-000000000000");
        for (String key : invalid) {
            assertThat(OssLiveSmoke.isValidObjectKey(key)).as("must reject: %s", key).isFalse();
        }
    }

    // ------------------------------------------------------------ 3. 净化

    @Test
    @DisplayName("净化：输出行不含 bucket/完整 key/endpoint/假 AK/SK/STS，且含 keyDigest（live/double 两模式）")
    void sanitizationRemovesSecrets() {
        OssLiveSmoke.LiveConfig config = new OssLiveSmoke.LiveConfig(
                "aliyun", "cn-hangzhou", SERVER_ENDPOINT, PUBLIC_ENDPOINT, BUCKET, AK, SK, STS);
        OssLiveSmoke.Args args = new OssLiveSmoke.Args("live", "write", VALID_KEY, SEED, 256, null, null);
        OssLiveSmoke.Redactor redactor = OssLiveSmoke.Redactor.from(args, config);

        String dirty = "bucket=" + BUCKET + " server=" + SERVER_ENDPOINT + " public=" + PUBLIC_ENDPOINT
                + " key=" + VALID_KEY
                + " ak=" + AK + " sk=" + SK + " sts=" + STS + " raw=" + "LTAIABCDEFGHIJKLMNOP";
        String cleaned = redactor.sanitize(dirty);
        assertNoSecrets(cleaned);

        String digest = OssLiveSmoke.keyDigest(VALID_KEY);
        for (String mode : List.of("live", "double")) {
            OssLiveSmoke.Execution malicious = new OssLiveSmoke.Execution(
                    "ok", "none", "step-" + VALID_KEY + "-" + BUCKET,
                    "code-" + AK, "req-" + SK, 256, "none");
            String line = OssLiveSmoke.formatLine(mode, "write", malicious, digest, redactor);
            assertThat(line).contains("side=java").contains("mode=" + mode)
                    .contains("keyDigest=" + digest).contains("purpose=assessment_result");
            assertNoSecrets(line);
        }
    }

    // ------------------------------------------------------------ 4. 三重门

    @Test
    @DisplayName("三重门：逐项缺失即 abort（provider / endpoint / 凭据 / opt-in）")
    void gateRejectsEachMissingCondition() {
        assertThat(OssLiveSmoke.evaluateGate("live",
                new OssLiveSmoke.LiveConfig("doubles", "cn-hangzhou", SERVER_ENDPOINT, PUBLIC_ENDPOINT,
                        BUCKET, AK, SK, null), true))
                .satisfies(gate -> {
                    assertThat(gate.pass()).isFalse();
                    assertThat(gate.reason()).isEqualTo("not-opted-in");
                    assertThat(gate.step()).isEqualTo("provider-not-aliyun");
                });
        // 两个新 endpoint 缺失 ⇒ 只报键名。
        OssLiveSmoke.Gate missingEndpoints = OssLiveSmoke.evaluateGate("live",
                new OssLiveSmoke.LiveConfig("aliyun", "cn-hangzhou", null, null, BUCKET, AK, SK, null), true);
        assertThat(missingEndpoints.pass()).isFalse();
        assertThat(missingEndpoints.reason()).isEqualTo("missing-config-key");
        assertThat(missingEndpoints.missingKeys()).containsExactly(
                "app.storage.oss.server-endpoint", "app.storage.oss.public-endpoint");
        OssLiveSmoke.Gate missingCreds = OssLiveSmoke.evaluateGate("live",
                new OssLiveSmoke.LiveConfig("aliyun", "cn-hangzhou", SERVER_ENDPOINT, PUBLIC_ENDPOINT,
                        null, AK, null, null), true);
        assertThat(missingCreds.pass()).isFalse();
        assertThat(missingCreds.reason()).isEqualTo("missing-config-key");
        assertThat(missingCreds.missingKeys()).containsExactly(
                "app.storage.oss.bucket", "app.storage.oss.access-key-secret");
        OssLiveSmoke.Gate noOptIn = OssLiveSmoke.evaluateGate("live",
                new OssLiveSmoke.LiveConfig("aliyun", "cn-hangzhou", SERVER_ENDPOINT, PUBLIC_ENDPOINT,
                        BUCKET, AK, SK, null), false);
        assertThat(noOptIn.pass()).isFalse();
        assertThat(noOptIn.reason()).isEqualTo("not-opted-in");
        assertThat(noOptIn.step()).isEqualTo("missing-live-opt-in");
        assertThat(OssLiveSmoke.evaluateGate("live",
                new OssLiveSmoke.LiveConfig("aliyun", "cn-hangzhou", SERVER_ENDPOINT, PUBLIC_ENDPOINT,
                        BUCKET, AK, SK, null), true)
                .pass()).isTrue();
    }

    @Test
    @DisplayName("double 模式遇 opt-in=true 必须 abort（not-opted-in / double-mode-refuses-live-opt-in）")
    void doubleModeRefusesLiveOptIn() {
        OssLiveSmoke.Gate gate = OssLiveSmoke.evaluateGate("double", null, true);
        assertThat(gate.pass()).isFalse();
        assertThat(gate.reason()).isEqualTo("not-opted-in");
        assertThat(gate.step()).isEqualTo("double-mode-refuses-live-opt-in");
    }

    // ------------------------------------------------------------ 5. double 全流程

    @Test
    @DisplayName("double 全流程 write→verify→delete→confirm-absent 每步 ok，且磁盘上对象确被删除")
    void doubleFullFlow(@TempDir Path root) throws Exception {
        OssLiveSmoke.StorageFactory factory = doubleFactory();
        String[] writeArgv = argv("double", "write", root, VALID_KEY, 256);
        String writeLine = runLine(writeArgv, false, (e, b, k) -> 0, factory, 0);
        String sha12 = OssLiveSmoke.sha256Hex12(OssLiveSmoke.smokeBytes(SEED, 256)).substring(0, 12);
        assertThat(writeLine).contains("result=ok").contains("bytes=256").contains("sha256=" + sha12);

        String verifyLine = runLine(argv("double", "verify", root, VALID_KEY, 256),
                false, (e, b, k) -> 0, factory, 0);
        assertThat(verifyLine).contains("result=ok").contains("bytes=256").contains("sha256=" + sha12);

        Path onDisk = root.resolve(VALID_KEY).normalize();
        assertThat(Files.isRegularFile(onDisk)).isTrue();

        String deleteLine = runLine(argv("double", "delete", root, VALID_KEY, 256),
                false, (e, b, k) -> 0, factory, 0);
        assertThat(deleteLine).contains("result=ok");
        assertThat(Files.exists(onDisk)).isFalse();

        String confirmLine = runLine(argv("double", "confirm-absent", root, VALID_KEY, 256),
                false, (e, b, k) -> 0, factory, 0);
        assertThat(confirmLine).contains("result=ok").contains("reason=absent-confirmed");
    }

    @Test
    @DisplayName("run 级：double 模式 + opt-in=true → abort（not-opted-in / double-mode-refuses-live-opt-in），不打开存储")
    void doubleModeRefusesLiveOptInAtRunLevel(@TempDir Path root) {
        boolean[] opened = {false};
        OssLiveSmoke.StorageFactory factory = (mode, args, cfg) -> {
            opened[0] = true;
            return session(new MapStorage());
        };
        String line = runLine(argv("double", "write", root, VALID_KEY, 256),
                true, (e, b, k) -> 0, factory, 2);
        assertThat(line).contains("result=fail").contains("reason=not-opted-in")
                .contains("step=double-mode-refuses-live-opt-in");
        assertThat(opened[0]).isFalse();
    }

    @Test
    @DisplayName("double 模式 public-url-probe → skipped/no-live-bucket（退出码 0）")
    void doubleProbeSkipped(@TempDir Path root) {
        String line = runLine(argv("double", "public-url-probe", root, VALID_KEY, 256),
                false, (e, b, k) -> 200, doubleFactory(), 0);
        assertThat(line).contains("result=skipped").contains("reason=no-live-bucket");
    }

    // ------------------------------------------------------------ live 注入式

    @Test
    @DisplayName("live 门通过后用注入假存储执行：write/verify 正常；public-url-probe 403→ok、200→fail")
    void livePhaseWithInjectedStorageAndProbe(@TempDir Path tempDir) throws Exception {
        Path config = writeFakeYaml(tempDir);
        MapStorage shared = new MapStorage();
        OssLiveSmoke.StorageFactory factory = (mode, args, cfg) -> session(shared);

        String writeLine = runLine(argvLive(config, "write", VALID_KEY, 256),
                true, (e, b, k) -> 0, factory, 0);
        assertThat(writeLine).contains("mode=live").contains("result=ok");

        String verifyLine = runLine(argvLive(config, "verify", VALID_KEY, 256),
                true, (e, b, k) -> 0, factory, 0);
        assertThat(verifyLine).contains("result=ok");

        String probe403 = runLine(argvLive(config, "public-url-probe", VALID_KEY, 256),
                true, (e, b, k) -> 403, factory, 0);
        assertThat(probe403).contains("result=ok").contains("step=public-url-status-403");
        assertThat(probe403).doesNotContain("http").doesNotContain(BUCKET).doesNotContain(VALID_KEY);

        String probe200 = runLine(argvLive(config, "public-url-probe", VALID_KEY, 256),
                true, (e, b, k) -> 200, factory, 1);
        assertThat(probe200).contains("result=fail").contains("reason=public-url-status-200");
    }

    @Test
    @DisplayName("三重门缺 opt-in 时 live abort，不打开存储（exit 2）")
    void liveGateAbortsWithoutOptIn(@TempDir Path tempDir) throws Exception {
        Path config = writeFakeYaml(tempDir);
        boolean[] opened = {false};
        OssLiveSmoke.StorageFactory factory = (mode, args, cfg) -> {
            opened[0] = true;
            return session(new MapStorage());
        };
        String line = runLine(argvLive(config, "write", VALID_KEY, 256),
                false, (e, b, k) -> 0, factory, 2);
        assertThat(line).contains("result=fail").contains("reason=not-opted-in");
        assertThat(opened[0]).isFalse();
    }

    // ------------------------------------------------------------ 错误净化

    @Test
    @DisplayName("适配器异常：输出 result=fail reason=adapter-error，且异常消息经净化（无 bucket/key/AK/SK/STS）")
    void adapterErrorIsSanitized(@TempDir Path tempDir) throws Exception {
        Path config = writeFakeYaml(tempDir);
        RuntimeException leaky = new RuntimeException("bucket=" + BUCKET + " key=" + VALID_KEY
                + " server=" + SERVER_ENDPOINT + " public=" + PUBLIC_ENDPOINT
                + " ak=" + AK + " sk=" + SK + " sts=" + STS
                + " LTAILEAKEDSECRET");
        OssLiveSmoke.StorageFactory factory = (mode, args, cfg) -> session(new ThrowingStorage(leaky));

        String output = runAll(argvLive(config, "verify", VALID_KEY, 256),
                true, (e, b, k) -> 0, factory, 1);
        assertThat(output).contains("result=fail").contains("reason=adapter-error")
                .contains("[oss-smoke-error]")
                .contains("keyDigest=" + OssLiveSmoke.keyDigest(VALID_KEY));
        assertNoSecrets(output);
    }

    @Test
    @DisplayName("double 模式异常净化：输出不含完整 key，但含 keyDigest")
    void doubleAdapterErrorIsSanitized(@TempDir Path root) {
        OssLiveSmoke.StorageFactory factory = (mode, args, cfg) ->
                session(new ThrowingStorage(new IllegalStateException("key=" + VALID_KEY)));
        String output = runAll(argv("double", "delete", root, VALID_KEY, 256),
                false, (e, b, k) -> 0, factory, 1);
        assertThat(output).contains("result=fail").contains("reason=adapter-error")
                .contains("keyDigest=" + OssLiveSmoke.keyDigest(VALID_KEY));
        assertThat(output).doesNotContain(VALID_KEY);
    }

    // ------------------------------------------------------------ 非法键 / 用法

    @Test
    @DisplayName("非法对象键在阶段前 fail/invalid-object-key（exit 2），不打开存储")
    void invalidKeyRejectedBeforePhases(@TempDir Path root) {
        boolean[] opened = {false};
        OssLiveSmoke.StorageFactory factory = (mode, args, cfg) -> {
            opened[0] = true;
            return session(new MapStorage());
        };
        String[] argv = {"--mode", "double", "--phase", "write",
                "--object-key", "dev/grant_face/00000000-0000-4000-8000-000000000000",
                "--content-seed", SEED, "--double-root", root.toString()};
        String line = runLine(argv, false, (e, b, k) -> 0, factory, 2);
        assertThat(line).contains("result=fail").contains("reason=invalid-object-key");
        assertThat(opened[0]).isFalse();
    }

    @Test
    @DisplayName("配置为 UTF-8 嵌套与点号扁平键均可读取")
    void yamlConfigReadBothShapes(@TempDir Path tempDir) throws Exception {
        Path nested = tempDir.resolve("nested.yml");
        Files.writeString(nested, ""
                + "app:\n"
                + "  storage:\n"
                + "    provider: aliyun\n"
                + "    oss:\n"
                + "      region: cn-hangzhou\n"
                + "      server-endpoint: " + SERVER_ENDPOINT + "\n"
                + "      public-endpoint: " + PUBLIC_ENDPOINT + "\n"
                + "      bucket: " + BUCKET + "\n"
                + "      access-key-id: " + AK + "\n"
                + "      access-key-secret: " + SK + "\n"
                + "      security-token: " + STS + "\n", StandardCharsets.UTF_8);
        OssLiveSmoke.LiveConfig nestedConfig = OssLiveSmoke.loadYamlConfig(nested);
        assertThat(nestedConfig.provider()).isEqualTo("aliyun");
        assertThat(nestedConfig.serverEndpoint()).isEqualTo(SERVER_ENDPOINT);
        assertThat(nestedConfig.publicEndpoint()).isEqualTo(PUBLIC_ENDPOINT);
        assertThat(nestedConfig.bucket()).isEqualTo(BUCKET);
        assertThat(nestedConfig.accessKeyId()).isEqualTo(AK);
        assertThat(nestedConfig.securityToken()).isEqualTo(STS);

        Path flat = tempDir.resolve("flat.yml");
        Files.writeString(flat, ""
                + "app.storage.provider: aliyun\n"
                + "app.storage.oss.region: cn-hangzhou\n"
                + "app.storage.oss.server-endpoint: " + SERVER_ENDPOINT + "\n"
                + "app.storage.oss.public-endpoint: " + PUBLIC_ENDPOINT + "\n"
                + "app.storage.oss.bucket: " + BUCKET + "\n"
                + "app.storage.oss.access-key-id: " + AK + "\n"
                + "app.storage.oss.access-key-secret: " + SK + "\n", StandardCharsets.UTF_8);
        OssLiveSmoke.LiveConfig flatConfig = OssLiveSmoke.loadYamlConfig(flat);
        assertThat(flatConfig.provider()).isEqualTo("aliyun");
        assertThat(flatConfig.serverEndpoint()).isEqualTo(SERVER_ENDPOINT);
        assertThat(flatConfig.publicEndpoint()).isEqualTo(PUBLIC_ENDPOINT);
        assertThat(flatConfig.bucket()).isEqualTo(BUCKET);
    }

    // ------------------------------------------------------------ helpers

    private static void assertNoSecrets(String text) {
        assertThat(text).doesNotContain(BUCKET)
                .doesNotContain(VALID_KEY)
                .doesNotContain(SERVER_ENDPOINT)
                .doesNotContain(PUBLIC_ENDPOINT)
                .doesNotContain("oss-fake-server.example.com")
                .doesNotContain("oss-fake-public.example.com")
                .doesNotContain(AK)
                .doesNotContain(SK)
                .doesNotContain(STS)
                .doesNotContain("LTAI");
    }

    private static String[] argv(String mode, String phase, Path root, String key, int nbytes) {
        return new String[]{"--mode", mode, "--phase", phase, "--object-key", key,
                "--content-seed", SEED, "--content-bytes", String.valueOf(nbytes),
                "--double-root", root.toString()};
    }

    private static String[] argvLive(Path config, String phase, String key, int nbytes) {
        return new String[]{"--mode", "live", "--phase", phase, "--object-key", key,
                "--content-seed", SEED, "--content-bytes", String.valueOf(nbytes),
                "--config", config.toString()};
    }

    private static Path writeFakeYaml(Path dir) throws Exception {
        Path config = dir.resolve("fake.yml");
        Files.writeString(config, ""
                + "app:\n"
                + "  storage:\n"
                + "    provider: aliyun\n"
                + "    oss:\n"
                + "      region: cn-hangzhou\n"
                + "      server-endpoint: " + SERVER_ENDPOINT + "\n"
                + "      public-endpoint: " + PUBLIC_ENDPOINT + "\n"
                + "      bucket: " + BUCKET + "\n"
                + "      access-key-id: " + AK + "\n"
                + "      access-key-secret: " + SK + "\n"
                + "      security-token: " + STS + "\n", StandardCharsets.UTF_8);
        return config;
    }

    private static OssLiveSmoke.StorageFactory doubleFactory() {
        return (mode, args, cfg) ->
                session(new FileSystemStorageDouble(args.doubleRoot()));
    }

    private static OssLiveSmoke.StorageSession session(StoragePort port) {
        return new OssLiveSmoke.StorageSession() {
            @Override
            public StoragePort port() {
                return port;
            }

            @Override
            public void close() {
            }
        };
    }

    private static String runLine(String[] argv, boolean optIn, OssLiveSmoke.PublicUrlProbe probe,
                                  OssLiveSmoke.StorageFactory factory, int expectedExit) {
        String output = runAll(argv, optIn, probe, factory, expectedExit);
        return output.lines().filter(line -> line.startsWith("[oss-smoke]")).findFirst().orElse("");
    }

    private static String runAll(String[] argv, boolean optIn, OssLiveSmoke.PublicUrlProbe probe,
                                 OssLiveSmoke.StorageFactory factory, int expectedExit) {
        ByteArrayOutputStream buffer = new ByteArrayOutputStream();
        int exit;
        try (PrintStream out = new PrintStream(buffer, true, StandardCharsets.UTF_8)) {
            exit = OssLiveSmoke.run(argv, out, optIn, probe, factory);
        }
        assertThat(exit).as("exit code").isEqualTo(expectedExit);
        return buffer.toString(StandardCharsets.UTF_8);
    }

    /** 内存假存储（绝不联网）。 */
    private static final class MapStorage implements StoragePort {
        private final Map<String, byte[]> data = new ConcurrentHashMap<>();

        @Override
        public void put(String objectKey, InputStream content, long byteSize, String contentType) {
            try {
                data.put(objectKey, content.readAllBytes());
            } catch (Exception failure) {
                throw new IllegalStateException("put failed", failure);
            }
        }

        @Override
        public InputStream getStream(String objectKey) {
            byte[] value = data.get(objectKey);
            return value == null ? null : new ByteArrayInputStream(value);
        }

        @Override
        public byte[] get(String objectKey) {
            return data.get(objectKey);
        }

        @Override
        public boolean exists(String objectKey) {
            return data.containsKey(objectKey);
        }

        @Override
        public void delete(String objectKey) {
            data.remove(objectKey);
        }
    }

    /** 始终抛异常的假存储，用于净化测试。 */
    private static final class ThrowingStorage implements StoragePort {
        private final RuntimeException failure;

        private ThrowingStorage(RuntimeException failure) {
            this.failure = failure;
        }

        @Override
        public void put(String objectKey, InputStream content, long byteSize, String contentType) {
            throw failure;
        }

        @Override
        public InputStream getStream(String objectKey) {
            throw failure;
        }

        @Override
        public byte[] get(String objectKey) {
            throw failure;
        }

        @Override
        public boolean exists(String objectKey) {
            throw failure;
        }

        @Override
        public void delete(String objectKey) {
            throw failure;
        }
    }
}
