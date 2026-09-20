package cn.yuanxin.mvp.web.assessments.narration;

import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;

import java.util.ArrayDeque;
import java.util.ArrayList;
import java.util.Deque;
import java.util.List;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

/**
 * {@link ReportNarrationSseParser} 增量解析与 fail-closed 规则单测（无网络）：
 * 只认四事件、accepted 必须首个且唯一、恰一个终态、终态后事件/重复终态/缺终态/畸形/空流一律 MALFORMED；
 * 并锁定 §6.3 两条流纪律（零 delta + completed 失败；拼接与 spoken_text 逐字不一致仍 completed）。
 */
class ReportNarrationSseParserTest {

    /** 内存行源：按行喂入；null 表示 EOF。 */
    private static final class ListLineSource implements ReportNarrationLineSource {
        private final Deque<String> lines = new ArrayDeque<>();
        private boolean closed;

        ListLineSource(String... lines) {
            java.util.Arrays.stream(lines).forEach(this.lines::add);
        }

        @Override
        public String readLine() {
            return lines.isEmpty() ? null : lines.poll();
        }

        @Override
        public void close() {
            closed = true;
        }
    }

    private static List<ReportNarrationEvent> drain(ReportNarrationSseParser parser) {
        List<ReportNarrationEvent> events = new ArrayList<>();
        ReportNarrationEvent event;
        while ((event = parser.next()) != null) {
            events.add(event);
        }
        return events;
    }

    private static ReportNarrationSseParser parser(String body) {
        String[] lines = body.split("\r\n|\n|\r", -1);
        return new ReportNarrationSseParser(new ListLineSource(lines));
    }

    private static void assertMalformed(String body) {
        ReportNarrationSseParser parser = parser(body);
        assertThatThrownBy(() -> drain(parser))
                .as("body=%s", body)
                .isInstanceOf(ReportNarrationException.class)
                .satisfies(thrown -> assertThat(((ReportNarrationException) thrown).kind())
                        .isEqualTo(ReportNarrationFailureKind.MALFORMED));
    }

    @Test
    @DisplayName("accepted + delta×2 + completed：按序累加，completed.spoken_text 权威")
    void acceptedDeltasCompleted() {
        ReportNarrationSseParser parser = parser(
                "event: response.accepted\ndata: {\"request_id\":\"r\"}\n\n"
                        + "event: response.delta\ndata: {\"delta\":\"Hello \"}\n\n"
                        + "event: response.delta\ndata: {\"delta\":\"world\"}\n\n"
                        + "event: response.completed\ndata: {\"spoken_text\":\"Hello world\"}\n\n");

        List<ReportNarrationEvent> events = drain(parser);
        assertThat(events).extracting(ReportNarrationEvent::type).containsExactly(
                ReportNarrationEvent.Type.ACCEPTED, ReportNarrationEvent.Type.DELTA,
                ReportNarrationEvent.Type.DELTA, ReportNarrationEvent.Type.COMPLETED);
        assertThat(events.get(1).delta()).isEqualTo("Hello ");
        assertThat(events.get(2).delta()).isEqualTo("world");
        assertThat(events.get(3).spokenText()).isEqualTo("Hello world");
        assertThat(parser.spokenTextMismatch()).isFalse();
    }

    @Test
    @DisplayName("顺序纪律：delta 先于 accepted / 终态先于 accepted → MALFORMED（accepted 必须首个）")
    void eventBeforeAcceptedRejected() {
        assertMalformed("event: response.delta\ndata: {\"delta\":\"a\"}\n\n"
                + "event: response.completed\ndata: {\"spoken_text\":\"a\"}\n\n");
        assertMalformed("event: response.completed\ndata: {\"spoken_text\":\"a\"}\n\n");
        assertMalformed("event: response.failed\ndata: {\"code\":\"X\"}\n\n");
    }

    @Test
    @DisplayName("顺序纪律：重复 accepted → MALFORMED（外部绝不出现两个 start）")
    void duplicateAcceptedRejected() {
        assertMalformed(
                "event: response.accepted\ndata: {}\n\n"
                        + "event: response.accepted\ndata: {}\n\n"
                        + "event: response.delta\ndata: {\"delta\":\"a\"}\n\n"
                        + "event: response.completed\ndata: {\"spoken_text\":\"a\"}\n\n");
    }

    @Test
    @DisplayName("正向对照：accepted 之后一切正常，不被过度收紧")
    void acceptedThenNormalStreamPositiveControl() {
        List<ReportNarrationEvent> events = drain(parser(
                "event: response.accepted\ndata: {}\n\n"
                        + "event: response.delta\ndata: {\"delta\":\"ok\"}\n\n"
                        + "event: response.completed\ndata: {\"spoken_text\":\"ok\"}\n\n"));
        assertThat(events).extracting(ReportNarrationEvent::type).containsExactly(
                ReportNarrationEvent.Type.ACCEPTED, ReportNarrationEvent.Type.DELTA,
                ReportNarrationEvent.Type.COMPLETED);
    }

    @Test
    @DisplayName("§6.3 零 delta + completed → MALFORMED（绝不假成功 done）")
    void completedWithoutAnyDeltaRejected() {
        assertMalformed("event: response.completed\ndata: {\"spoken_text\":\"done\"}\n\n");
        assertMalformed("event: response.accepted\ndata: {}\n\n"
                + "event: response.completed\ndata: {\"spoken_text\":\"done\"}\n\n");
    }

    @Test
    @DisplayName("§6.3 累计 delta 与 spoken_text 不一致 → 仍 COMPLETED（只告警不失败），标志可断言")
    void mismatchStillCompletes() {
        ReportNarrationSseParser parser = parser(
                "event: response.accepted\ndata: {}\n\n"
                        + "event: response.delta\ndata: {\"delta\":\"Hello world\"}\n\n"
                        + "event: response.completed\ndata: {\"spoken_text\":\"Hello world!\"}\n\n");
        List<ReportNarrationEvent> events = drain(parser);
        assertThat(events).extracting(ReportNarrationEvent::type)
                .containsExactly(ReportNarrationEvent.Type.ACCEPTED, ReportNarrationEvent.Type.DELTA,
                        ReportNarrationEvent.Type.COMPLETED);
        assertThat(events.get(2).spokenText()).isEqualTo("Hello world!");
        assertThat(parser.spokenTextMismatch()).isTrue();
    }

    @Test
    @DisplayName("§6.3 同长度不同内容也必须被检出（不再只比长度）；内容相同 → 标志 false")
    void spokenTextMismatchDetectsSameLengthDifferentContent() {
        ReportNarrationSseParser parser = parser(
                "event: response.accepted\ndata: {}\n\n"
                        + "event: response.delta\ndata: {\"delta\":\"Hello worlD\"}\n\n"
                        + "event: response.completed\ndata: {\"spoken_text\":\"Hello world\"}\n\n");
        List<ReportNarrationEvent> events = drain(parser);
        assertThat(events.get(2).type()).isEqualTo(ReportNarrationEvent.Type.COMPLETED);
        assertThat(parser.spokenTextMismatch()).as("same length, different content").isTrue();

        ReportNarrationSseParser equal = parser(
                "event: response.accepted\ndata: {}\n\n"
                        + "event: response.delta\ndata: {\"delta\":\"Hello \"}\n\n"
                        + "event: response.delta\ndata: {\"delta\":\"world\"}\n\n"
                        + "event: response.completed\ndata: {\"spoken_text\":\"Hello world\"}\n\n");
        drain(equal);
        assertThat(equal.spokenTextMismatch()).as("exact match").isFalse();
    }

    @Test
    @DisplayName("failed 终态 → FAILED 事件（携带下游 code，供安全映射）")
    void failedTerminal() {
        List<ReportNarrationEvent> events = drain(parser(
                "event: response.accepted\ndata: {}\n\n"
                        + "event: response.delta\ndata: {\"delta\":\"partial\"}\n\n"
                        + "event: response.failed\ndata: {\"code\":\"AI_UPSTREAM_TIMEOUT\",\"retryable\":true}\n\n"));
        assertThat(events).extracting(ReportNarrationEvent::type).containsExactly(
                ReportNarrationEvent.Type.ACCEPTED, ReportNarrationEvent.Type.DELTA,
                ReportNarrationEvent.Type.FAILED);
        assertThat(events.get(2).failedCode()).isEqualTo("AI_UPSTREAM_TIMEOUT");
    }

    @Test
    @DisplayName("多行 data / CRLF / 注释（heartbeat）/ id|retry 字段：按规范解析")
    void sseSyntaxVariants() {
        ReportNarrationSseParser parser = parser(
                ": keep-alive comment\r\n"
                        + "event: response.accepted\r\n"
                        + "data: {}\r\n\r\n"
                        + "id: 42\r\n"
                        + "event: response.delta\r\n"
                        + "data: {\"delta\":\r\n"
                        + "data: \"multi\"}\r\n"
                        + "\r\n"
                        + "retry: 1000\r\n"
                        + "event: response.completed\r\n"
                        + "data: {\"spoken_text\":\"multi\"}\r\n\r\n");
        List<ReportNarrationEvent> events = drain(parser);
        assertThat(events).extracting(ReportNarrationEvent::type).containsExactly(
                ReportNarrationEvent.Type.ACCEPTED, ReportNarrationEvent.Type.DELTA,
                ReportNarrationEvent.Type.COMPLETED);
        assertThat(events.get(1).delta()).isEqualTo("multi");
        assertThat(events.get(2).spokenText()).isEqualTo("multi");
    }

    @Test
    @DisplayName("未知事件 → MALFORMED")
    void unknownEventRejected() {
        assertMalformed("event: something-else\ndata: {}\n\n");
    }

    @Test
    @DisplayName("重复终态 / 终态后事件 → MALFORMED")
    void duplicateOrPostTerminalRejected() {
        assertMalformed("event: response.accepted\ndata: {}\n\n"
                + "event: response.delta\ndata: {\"delta\":\"a\"}\n\n"
                + "event: response.completed\ndata: {\"spoken_text\":\"a\"}\n\n"
                + "event: response.completed\ndata: {\"spoken_text\":\"a\"}\n\n");
        assertMalformed("event: response.accepted\ndata: {}\n\n"
                + "event: response.delta\ndata: {\"delta\":\"a\"}\n\n"
                + "event: response.completed\ndata: {\"spoken_text\":\"a\"}\n\n"
                + "event: response.delta\ndata: {\"delta\":\"late\"}\n\n");
        assertMalformed("event: response.accepted\ndata: {}\n\n"
                + "event: response.failed\ndata: {\"code\":\"x\"}\n\n"
                + "event: response.completed\ndata: {\"spoken_text\":\"a\"}\n\n");
    }

    @Test
    @DisplayName("缺终态（EOF）/ 空流 / 仅 accepted → MALFORMED")
    void missingTerminalRejected() {
        assertMalformed("");
        assertMalformed("event: response.accepted\ndata: {}\n\n"
                + "event: response.delta\ndata: {\"delta\":\"only\"}\n\n");
        assertMalformed("event: response.accepted\ndata: {}\n\n");
    }

    @Test
    @DisplayName("畸形数据（非 JSON / 非对象 / delta 缺文本 / completed 缺非空 spoken_text / data 无 event）→ MALFORMED")
    void malformedPayloadsRejected() {
        assertMalformed("event: response.accepted\ndata: {}\n\n"
                + "event: response.delta\ndata: not-json\n\n");
        assertMalformed("event: response.accepted\ndata: {}\n\n"
                + "event: response.delta\ndata: []\n\n");
        assertMalformed("event: response.accepted\ndata: {}\n\n"
                + "event: response.delta\ndata: {\"nope\":\"x\"}\n\n");
        assertMalformed("event: response.accepted\ndata: {}\n\n"
                + "event: response.completed\ndata: {\"spoken_text\":\"\"}\n\n");
        assertMalformed("event: response.accepted\ndata: {}\n\n"
                + "event: response.completed\ndata: {\"spoken_text\":\"   \"}\n\n");
        assertMalformed("event: response.accepted\ndata: {}\n\n"
                + "event: response.completed\ndata: {\"answer\":{\"text\":\"x\"}}\n\n");
        assertMalformed("event: response.accepted\ndata: {}\n\n"
                + "data: {\"delta\":\"x\"}\n\n");
    }

    @Test
    @DisplayName("close() 委托底层行源（取消下游）")
    void closeDelegates() {
        ListLineSource source = new ListLineSource(
                "event: response.accepted\ndata: {}\n\n",
                "event: response.delta\ndata: {\"delta\":\"a\"}\n\n",
                "event: response.completed\ndata: {\"spoken_text\":\"a\"}\n");
        ReportNarrationSseParser parser = new ReportNarrationSseParser(source);
        parser.close();
        assertThat(source.closed).isTrue();
    }

    @Test
    @DisplayName("单事件 data 超上限 → MALFORMED（有界，不无界累积）")
    void oversizedEventDataRejected() {
        assertMalformed("data: " + "x".repeat(ReportNarrationSseParser.MAX_EVENT_DATA_CHARS + 1) + "\n\n");
    }

    @Test
    @DisplayName("completed.spoken_text 超上限 → MALFORMED")
    void oversizedCompletedSpokenTextRejected() {
        String text = "y".repeat(ReportNarrationSseParser.MAX_ACCUMULATED_CHARS + 1);
        assertMalformed("event: response.accepted\ndata: {}\n\n"
                + "event: response.delta\ndata: {\"delta\":\"a\"}\n\n"
                + "event: response.completed\ndata: {\"spoken_text\":\"" + text + "\"}\n\n");
    }

    @Test
    @DisplayName("response.failed.code 归一：合法码保留，非法（小写/超长/空格）→ null")
    void failedCodeSanitized() {
        List<ReportNarrationEvent> valid = drain(parser(
                "event: response.accepted\ndata: {}\n\n"
                        + "event: response.delta\ndata: {\"delta\":\"a\"}\n\n"
                        + "event: response.failed\ndata: {\"code\":\"AI_UPSTREAM_TIMEOUT\"}\n\n"));
        assertThat(valid.get(2).failedCode()).isEqualTo("AI_UPSTREAM_TIMEOUT");

        for (String malicious : List.of(
                "lower_case",
                "has space and user text",
                "A".repeat(65),
                "BAD-CODE")) {
            List<ReportNarrationEvent> events = drain(parser(
                    "event: response.accepted\ndata: {}\n\n"
                            + "event: response.delta\ndata: {\"delta\":\"a\"}\n\n"
                            + "event: response.failed\ndata: {\"code\":\"" + malicious + "\"}\n\n"));
            assertThat(events).hasSize(3);
            assertThat(events.get(2).failedCode()).as("code=%s", malicious).isNull();
        }
    }
}
