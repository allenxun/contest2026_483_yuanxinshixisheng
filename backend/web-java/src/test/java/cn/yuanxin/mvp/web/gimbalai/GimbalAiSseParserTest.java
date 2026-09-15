package cn.yuanxin.mvp.web.gimbalai;

import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;

import java.util.ArrayDeque;
import java.util.ArrayList;
import java.util.Deque;
import java.util.List;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

/**
 * {@link GimbalAiSseParser} 增量解析与 fail-closed 规则单测（无网络）：
 * 只认四事件、恰一个终态、终态后事件/重复终态/缺终态/畸形/空流一律 MALFORMED。
 */
class GimbalAiSseParserTest {

    /** 内存行源：按行喂入；null 表示 EOF。 */
    private static final class ListLineSource implements GimbalAiLineSource {
        private final Deque<String> lines = new ArrayDeque<>();
        private boolean closed;

        ListLineSource(String... lines) {
            java.util.Arrays.stream(lines).forEach(this.lines::add);
        }

        @Override
        public String readLine() {
            if (lines.isEmpty()) {
                return null;
            }
            String line = lines.poll();
            return line;
        }

        @Override
        public void close() {
            closed = true;
        }
    }

    private static List<GimbalAiEvent> drain(GimbalAiSseParser parser) {
        List<GimbalAiEvent> events = new ArrayList<>();
        GimbalAiEvent event;
        while ((event = parser.next()) != null) {
            events.add(event);
        }
        return events;
    }

    private static GimbalAiSseParser parser(String body) {
        String[] lines = body.split("\r\n|\n|\r", -1);
        return new GimbalAiSseParser(new ListLineSource(lines));
    }

    @Test
    @DisplayName("accepted + delta×2 + completed：按序累加，completed.answer.text 权威")
    void acceptedDeltasCompleted() {
        GimbalAiSseParser parser = parser(
                "event: response.accepted\ndata: {\"request_id\":\"r\"}\n\n"
                        + "event: response.delta\ndata: {\"delta\":\"Hello \"}\n\n"
                        + "event: response.delta\ndata: {\"delta\":\"world\"}\n\n"
                        + "event: response.completed\ndata: {\"answer\":{\"text\":\"Hello world\"}}\n\n");

        List<GimbalAiEvent> events = drain(parser);
        assertThat(events).extracting(GimbalAiEvent::type).containsExactly(
                GimbalAiEvent.Type.ACCEPTED, GimbalAiEvent.Type.DELTA,
                GimbalAiEvent.Type.DELTA, GimbalAiEvent.Type.COMPLETED);
        assertThat(events.get(1).delta()).isEqualTo("Hello ");
        assertThat(events.get(2).delta()).isEqualTo("world");
        assertThat(events.get(3).answerText()).isEqualTo("Hello world");
    }

    @Test
    @DisplayName("仅 completed（无 accepted/delta）→ 成功终态")
    void completedOnly() {
        List<GimbalAiEvent> events = drain(parser(
                "event: response.completed\ndata: {\"answer\":{\"text\":\"done\"}}\n\n"));
        assertThat(events).hasSize(1);
        assertThat(events.get(0).type()).isEqualTo(GimbalAiEvent.Type.COMPLETED);
        assertThat(events.get(0).answerText()).isEqualTo("done");
    }

    @Test
    @DisplayName("failed 终态 → FAILED 事件（携带下游 code，供安全映射）")
    void failedTerminal() {
        List<GimbalAiEvent> events = drain(parser(
                "event: response.delta\ndata: {\"delta\":\"partial\"}\n\n"
                        + "event: response.failed\ndata: {\"code\":\"AI_UPSTREAM_TIMEOUT\",\"retryable\":true}\n\n"));
        assertThat(events).extracting(GimbalAiEvent::type).containsExactly(
                GimbalAiEvent.Type.DELTA, GimbalAiEvent.Type.FAILED);
        assertThat(events.get(1).failedCode()).isEqualTo("AI_UPSTREAM_TIMEOUT");
    }

    @Test
    @DisplayName("多行 data / CRLF / 注释 / id|retry 字段：按规范解析")
    void sseSyntaxVariants() {
        GimbalAiSseParser parser = parser(
                ": keep-alive comment\r\n"
                        + "id: 42\r\n"
                        + "event: response.delta\r\n"
                        + "data: {\"delta\":\r\n"
                        + "data: \"multi\"}\r\n"
                        + "\r\n"
                        + "retry: 1000\r\n"
                        + "event: response.completed\r\n"
                        + "data: {\"answer\":{\"text\":\"multi\"}}\r\n\r\n");
        List<GimbalAiEvent> events = drain(parser);
        assertThat(events).extracting(GimbalAiEvent::type).containsExactly(
                GimbalAiEvent.Type.DELTA, GimbalAiEvent.Type.COMPLETED);
        assertThat(events.get(0).delta()).isEqualTo("multi");
        assertThat(events.get(1).answerText()).isEqualTo("multi");
    }

    @Test
    @DisplayName("未知事件 → MALFORMED")
    void unknownEventRejected() {
        GimbalAiSseParser parser = parser("event: something-else\ndata: {}\n\n");
        assertThatThrownBy(() -> parser.next())
                .isInstanceOf(GimbalAiException.class)
                .satisfies(thrown -> assertThat(((GimbalAiException) thrown).kind())
                        .isEqualTo(GimbalAiFailureKind.MALFORMED));
    }

    @Test
    @DisplayName("重复终态 / 终态后事件 → MALFORMED")
    void duplicateOrPostTerminalRejected() {
        for (String body : List.of(
                "event: response.completed\ndata: {\"answer\":{\"text\":\"a\"}}\n\n"
                        + "event: response.completed\ndata: {\"answer\":{\"text\":\"b\"}}\n\n",
                "event: response.completed\ndata: {\"answer\":{\"text\":\"a\"}}\n\n"
                        + "event: response.delta\ndata: {\"delta\":\"late\"}\n\n",
                "event: response.failed\ndata: {\"code\":\"x\"}\n\n"
                        + "event: response.completed\ndata: {\"answer\":{\"text\":\"a\"}}\n\n")) {
            GimbalAiSseParser parser = parser(body);
            assertThatThrownBy(() -> drain(parser))
                    .as("body=%s", body)
                    .isInstanceOf(GimbalAiException.class)
                    .satisfies(thrown -> assertThat(((GimbalAiException) thrown).kind())
                            .isEqualTo(GimbalAiFailureKind.MALFORMED));
        }
    }

    @Test
    @DisplayName("缺终态（deltas 后 EOF）/ 空流 → MALFORMED")
    void missingTerminalRejected() {
        for (String body : List.of(
                "",
                "event: response.delta\ndata: {\"delta\":\"only\"}\n\n",
                "event: response.accepted\ndata: {}\n\n")) {
            GimbalAiSseParser parser = parser(body);
            assertThatThrownBy(() -> drain(parser))
                    .as("body=%s", body)
                    .isInstanceOf(GimbalAiException.class)
                    .satisfies(thrown -> assertThat(((GimbalAiException) thrown).kind())
                            .isEqualTo(GimbalAiFailureKind.MALFORMED));
        }
    }

    @Test
    @DisplayName("畸形数据（非 JSON / 非对象 / delta 缺文本 / completed 缺非空 text / data 无 event）→ MALFORMED")
    void malformedPayloadsRejected() {
        for (String body : List.of(
                "event: response.delta\ndata: not-json\n\n",
                "event: response.delta\ndata: []\n\n",
                "event: response.delta\ndata: {\"nope\":\"x\"}\n\n",
                "event: response.completed\ndata: {\"answer\":{}}\n\n",
                "event: response.completed\ndata: {\"answer\":{\"text\":\"   \"}}\n\n",
                "data: {\"delta\":\"x\"}\n\n")) {
            GimbalAiSseParser parser = parser(body);
            assertThatThrownBy(() -> drain(parser))
                    .as("body=%s", body)
                    .isInstanceOf(GimbalAiException.class)
                    .satisfies(thrown -> assertThat(((GimbalAiException) thrown).kind())
                            .isEqualTo(GimbalAiFailureKind.MALFORMED));
        }
    }

    @Test
    @DisplayName("close() 委托底层行源（取消下游）")
    void closeDelegates() {
        ListLineSource source = new ListLineSource("event: response.completed\ndata: {\"answer\":{\"text\":\"a\"}}\n");
        GimbalAiSseParser parser = new GimbalAiSseParser(source);
        parser.close();
        assertThat(source.closed).isTrue();
    }

    @Test
    @DisplayName("B1(b) 单事件 data 超上限 → MALFORMED（有界，不无界累积）")
    void oversizedEventDataRejected() {
        GimbalAiSseParser parser = parser("data: " + "x".repeat(GimbalAiSseParser.MAX_EVENT_DATA_CHARS + 1) + "\n\n");
        assertThatThrownBy(() -> parser.next())
                .isInstanceOf(GimbalAiException.class)
                .satisfies(thrown -> assertThat(((GimbalAiException) thrown).kind())
                        .isEqualTo(GimbalAiFailureKind.MALFORMED));
    }

    @Test
    @DisplayName("B1(b) completed.answer.text 超上限 → MALFORMED")
    void oversizedCompletedAnswerRejected() {
        String text = "y".repeat(GimbalAiSseParser.MAX_ACCUMULATED_CHARS + 1);
        GimbalAiSseParser parser = parser("event: response.completed\ndata: {\"answer\":{\"text\":\"" + text + "\"}}\n\n");
        assertThatThrownBy(() -> parser.next())
                .isInstanceOf(GimbalAiException.class)
                .satisfies(thrown -> assertThat(((GimbalAiException) thrown).kind())
                        .isEqualTo(GimbalAiFailureKind.MALFORMED));
    }

    @Test
    @DisplayName("I1 response.failed.code 归一：合法码保留，非法（小写/超长/空格）→ null")
    void failedCodeSanitized() {
        List<GimbalAiEvent> valid = drain(parser(
                "event: response.failed\ndata: {\"code\":\"AI_UPSTREAM_TIMEOUT\"}\n\n"));
        assertThat(valid.get(0).failedCode()).isEqualTo("AI_UPSTREAM_TIMEOUT");

        for (String malicious : List.of(
                "lower_case",
                "has space and user text",
                "A".repeat(65),
                "BAD-CODE")) {
            GimbalAiSseParser parser = parser(
                    "event: response.failed\ndata: {\"code\":\"" + malicious + "\"}\n\n");
            List<GimbalAiEvent> events = drain(parser);
            assertThat(events).hasSize(1);
            assertThat(events.get(0).failedCode()).as("code=%s", malicious).isNull();
        }
    }
}
