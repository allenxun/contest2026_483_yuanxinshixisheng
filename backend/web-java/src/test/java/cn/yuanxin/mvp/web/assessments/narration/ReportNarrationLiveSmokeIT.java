package cn.yuanxin.mvp.web.assessments.narration;

import com.fasterxml.jackson.databind.ObjectMapper;
import org.junit.jupiter.api.Assumptions;
import org.junit.jupiter.api.BeforeAll;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;

import java.io.ByteArrayOutputStream;
import java.math.BigDecimal;
import java.nio.charset.StandardCharsets;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Locale;
import java.util.Map;
import java.util.UUID;

import static org.assertj.core.api.Assertions.assertThat;

/**
 * 一次性<b>真实 AI 联调</b> smoke（<b>默认跳过；仅 root 可执行</b>）。
 *
 * <p><b>三重显式 opt-in（必须同时满足，任一不满足即 {@link Assumptions#abort} 容器级中止，
 * 默认全量套件 Tests run: 0、绝不联网）</b>：</p>
 * <ol>
 *   <li>系统属性 {@code -Dmvp.b.narration.live=true}；</li>
 *   <li>环境 {@code APP_REPORT_NARRATION_BASE_URL} 与 {@code APP_REPORT_NARRATION_API_KEY} 均非空白；</li>
 *   <li>环境 {@code MVP_B_NARRATION_LIVE_ACK=I_UNDERSTAND_THIS_CALLS_THE_REAL_AI_SERVICE}。</li>
 * </ol>
 *
 * <p><b>行为</b>：用<b>明确标注为合成 fixture</b> 的 V3 形状三项评分（不触库、不写 DB、不用任何真实
 * 成员数据）构造 {@link ReportNarrationScores} → 真实 {@link HttpReportNarrationClient#openStream} →
 * {@link ReportNarrationService#pump} 写入捕获用 {@link java.io.OutputStream} → 断言外部帧序列为
 * {@code start → text_delta×N(N>=1) → done}、seq 连续、首 delta 在 done 之前、恰一个终态。</p>
 *
 * <p>输出<b>只</b>打印事件计数、seq 列表、各帧字节长度、delta 总字符长度、{@code spoken_text}
 * 字符长度、耗时；<b>绝不</b>打印 api-key、base-url 主机、{@code spoken_text} 内容、delta 内容或完整 body。</p>
 *
 * <p><b>OpenCode 侧未执行真实联调，故不得声称端到端已成功。</b> root 运行命令见交付说明：
 * {@code MVP_B_NARRATION_LIVE_ACK=I_UNDERSTAND_THIS_CALLS_THE_REAL_AI_SERVICE
 * APP_REPORT_NARRATION_BASE_URL=... APP_REPORT_NARRATION_API_KEY=... mvn -B test
 * -Dtest=ReportNarrationLiveSmokeIT -Dmvp.b.narration.live=true}。</p>
 */
class ReportNarrationLiveSmokeIT {

    private static final ObjectMapper JSON = new ObjectMapper();

    private static final String ACK_VALUE = "I_UNDERSTAND_THIS_CALLS_THE_REAL_AI_SERVICE";

    private static String baseUrl;
    private static String apiKey;

    @BeforeAll
    static void requireExplicitOptIn() {
        if (!"true".equalsIgnoreCase(config("mvp.b.narration.live", "MVP_B_NARRATION_LIVE"))) {
            Assumptions.abort("live smoke skipped: -Dmvp.b.narration.live is not 'true'");
        }
        baseUrl = config("app.report-narration.base-url", "APP_REPORT_NARRATION_BASE_URL");
        apiKey = config("app.report-narration.api-key", "APP_REPORT_NARRATION_API_KEY");
        if (baseUrl == null || baseUrl.isBlank() || apiKey == null || apiKey.isBlank()) {
            Assumptions.abort("live smoke skipped: report narration base-url/api-key env is empty");
        }
        if (!ACK_VALUE.equals(config("mvp.b.narration.live-ack", "MVP_B_NARRATION_LIVE_ACK"))) {
            Assumptions.abort("live smoke skipped: MVP_B_NARRATION_LIVE_ACK acknowledgement missing");
        }
    }

    @Test
    @DisplayName("真实 AI：start→text_delta×N(N>=1)→done，seq 连续、首 delta 在 done 前、恰一终态")
    void realAiProducesOrderedSingleTerminalStream() throws Exception {
        ReportNarrationScores synthetic = syntheticScores();
        ReportNarrationProperties properties =
                new ReportNarrationProperties(baseUrl, apiKey, 3000, 30000);
        HttpReportNarrationClient client = new HttpReportNarrationClient(properties, JSON);
        // pump 只使用 objectMapper；本 smoke 不经过门禁/DB，故 read/repo 传 null。
        ReportNarrationService service = new ReportNarrationService(null, null, client, JSON);

        String taskId = UUID.randomUUID().toString();
        String reportId = UUID.randomUUID().toString();
        ByteArrayOutputStream out = new ByteArrayOutputStream();

        long start = System.nanoTime();
        ReportNarrationStream raw = client.openStream(synthetic);
        // 装饰下游流以记录完整 spoken_text 的字符长度（仅本 smoke 使用；绝不打印内容）。
        int[] spokenTextChars = {-1};
        ReportNarrationStream recording = new ReportNarrationStream() {
            @Override
            public ReportNarrationEvent next() {
                ReportNarrationEvent event = raw.next();
                if (event != null && event.type() == ReportNarrationEvent.Type.COMPLETED) {
                    spokenTextChars[0] = event.spokenText().length();
                }
                return event;
            }

            @Override
            public void close() {
                raw.close();
            }
        };
        try {
            service.pump(new ReportNarrationService.Session(recording, "live-smoke", taskId, reportId), out);
        } finally {
            recording.close();
        }
        long elapsedMillis = (System.nanoTime() - start) / 1_000_000L;

        String rawOutput = out.toString(StandardCharsets.UTF_8);
        List<String[]> frames = parseFrames(rawOutput);
        Map<String, Integer> eventCounts = new LinkedHashMap<>();
        List<Integer> seqs = new ArrayList<>();
        List<Integer> frameBytes = new ArrayList<>();
        int deltaChars = 0;
        for (String[] frame : frames) {
            eventCounts.merge(frame[0], 1, Integer::sum);
            seqs.add(JSON.readTree(frame[1]).path("seq").asInt());
            frameBytes.add(frame[2].getBytes(StandardCharsets.UTF_8).length);
            if ("text_delta".equals(frame[0])) {
                deltaChars += JSON.readTree(frame[1]).path("delta").asText().length();
            }
        }

        System.out.println("[live-smoke] real AI call completed"
                + " eventCounts=" + eventCounts
                + " seqs=" + seqs
                + " frameBytes=" + frameBytes
                + " deltaChars=" + deltaChars
                + " spokenTextChars=" + spokenTextChars[0]
                + " elapsedMillis=" + elapsedMillis
                + " (api-key/base-url/content never printed)");

        assertThat(frames).isNotEmpty();
        assertThat(frames.get(0)[0]).isEqualTo("start");
        assertThat(frames.get(frames.size() - 1)[0]).isEqualTo("done");
        assertThat(frames.stream().filter(f -> "text_delta".equals(f[0])).count())
                .as("at least one delta").isGreaterThanOrEqualTo(1);
        assertThat(frames.stream().filter(f -> "done".equals(f[0]) || "error".equals(f[0])).count())
                .isEqualTo(1);
        assertThat(frames).noneMatch(f -> "error".equals(f[0]));
        // 首 delta 在 done 之前；seq 从 1 起严格 +1。
        int firstDelta = indexOf(frames, "text_delta");
        assertThat(firstDelta).isGreaterThan(0).isLessThan(frames.size() - 1);
        List<Integer> expected = new ArrayList<>();
        for (int i = 1; i <= frames.size(); i++) {
            expected.add(i);
        }
        assertThat(seqs).containsExactlyElementsOf(expected);

        System.out.println("[live-smoke] 本次为真实 AI 调用（非 stub）；仅本地断言，未修改任何远端服务。");
    }

    /** 明确标注为合成 fixture 的 V3 形状三项评分（非真实算法结果）。 */
    private static ReportNarrationScores syntheticScores() {
        return new ReportNarrationScores(
                syntheticGroup("pores", "毛孔", "F", "额头"),
                syntheticGroup("spots", "斑点", "L", "左脸"),
                syntheticGroup("surface_gloss", "光泽", "R", "右脸"));
    }

    private static ReportNarrationScores.ScoreGroup syntheticGroup(String group, String name,
                                                                   String region, String regionName) {
        return new ReportNarrationScores.ScoreGroup(new BigDecimal("60"), "mild", name,
                List.of(new ReportNarrationScores.Region(region, regionName,
                        new BigDecimal("50"), "mild")));
    }

    private static int indexOf(List<String[]> frames, String event) {
        for (int i = 0; i < frames.size(); i++) {
            if (event.equals(frames.get(i)[0])) {
                return i;
            }
        }
        return -1;
    }

    private static List<String[]> parseFrames(String raw) {
        List<String[]> frames = new ArrayList<>();
        String event = null;
        StringBuilder data = new StringBuilder();
        StringBuilder block = new StringBuilder();
        for (String line : raw.split("\n", -1)) {
            if (line.isEmpty()) {
                if (event != null) {
                    frames.add(new String[]{event, data.toString(), block.toString()});
                }
                event = null;
                data.setLength(0);
                block.setLength(0);
            } else {
                block.append(line).append('\n');
                if (line.startsWith("event: ")) {
                    event = line.substring("event: ".length());
                } else if (line.startsWith("data: ")) {
                    data.append(line.substring("data: ".length()));
                }
            }
        }
        return frames;
    }

    /** 系统属性（点式）→ 环境变量；两者皆无返回 null。绝不回显值。 */
    private static String config(String systemProperty, String environmentVariable) {
        String system = System.getProperty(systemProperty);
        if (system != null && !system.isBlank()) {
            return system;
        }
        String environment = System.getenv(environmentVariable);
        if (environment != null && !environment.isBlank()) {
            return environment;
        }
        String normalized = environmentVariable.toUpperCase(Locale.ROOT);
        return System.getenv(normalized);
    }
}
