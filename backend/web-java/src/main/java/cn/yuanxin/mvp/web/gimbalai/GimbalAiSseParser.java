package cn.yuanxin.mvp.web.gimbalai;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;

import java.util.ArrayDeque;
import java.util.Deque;
import java.util.Set;

/**
 * 下游 {@code /internal/v1/ai/responses:stream} 的<b>增量</b> SSE 解析器（严格 fail-closed）。
 *
 * <p>只接受四个事件：{@code response.accepted}（信息性）、{@code response.delta}（按序累加
 * {@code data.delta}）、{@code response.completed}（成功终态；{@code data.answer.text} 权威）、
 * {@code response.failed}（终态失败，problem+json 的 {@code code} 仅作诊断）。</p>
 *
 * <p><b>fail-closed</b>：未知事件、事件后又有事件（含重复终态）、缺终态（EOF）、
 * 事件缺 data、data 非 JSON/非对象、{@code response.delta} 缺文本、{@code response.completed}
 * 缺非空 {@code answer.text}、事件数/累计增量越界 → 抛 {@link GimbalAiException}（{@code MALFORMED}）。
 * 读取超时/传输失败由行源抛 {@code TIMEOUT}/{@code UNAVAILABLE}。绝不返回部分/合成答案。</p>
 *
 * <p>SSE 语法：空行分隔事件块；忽略注释行（{@code :} 开头）与 {@code id}/{@code retry}
 * 字段；{@code data:} 可跨多行；行尾由行源处理。<b>不</b>发送或解析 Last-Event-ID。</p>
 *
 * <p>终止策略：遇到终态事件后，仍继续读到流结束以检出"终态后事件/重复终态"；此类违规
 * 一律 malformed。终态事件在流结束（EOF）后才可被消费，从而保证恰一个终态。</p>
 *
 * <p><b>有界</b>（与行源的 64 KiB 单行上限叠加）：单事件累积 data 上限
 * {@value #MAX_EVENT_DATA_CHARS} 字符、事件数上限 {@value #MAX_EVENTS}、累计 delta 与
 * {@code response.completed.answer.text} 上限 {@value #MAX_ACCUMULATED_CHARS} 字符——
 * 任一越界即 {@code MALFORMED}，绝不无界累积。</p>
 */
final class GimbalAiSseParser implements AutoCloseable {

    private static final ObjectMapper MAPPER = new ObjectMapper();

    private static final Set<String> EVENTS =
            Set.of("response.accepted", "response.delta", "response.completed",
                    "response.failed");

    /** 单次流事件的硬上限（防无界事件流）。 */
    static final int MAX_EVENTS = 10_000;
    /** 单事件累积 data 字符上限（多行 data 也受限）。 */
    static final int MAX_EVENT_DATA_CHARS = 256 * 1024;
    /** 累计 delta 与 completed.answer.text 字符上限。 */
    static final int MAX_ACCUMULATED_CHARS = 200_000;

    private final GimbalAiLineSource source;
    private final Deque<GimbalAiEvent> ready = new ArrayDeque<>();

    private boolean done;
    private boolean terminalSeen;
    private GimbalAiEvent pendingTerminal;

    private String eventName;
    private final StringBuilder data = new StringBuilder();
    private boolean hasData;
    private int eventCount;
    private int accumulatedChars;

    GimbalAiSseParser(GimbalAiLineSource source) {
        this.source = source;
    }

    /**
     * 下一个已校验事件；流在终态后正常结束返回 {@code null}。
     *
     * @throws GimbalAiException 协议违规（MALFORMED）或读取超时/传输失败（TIMEOUT/UNAVAILABLE）
     */
    GimbalAiEvent next() {
        if (!ready.isEmpty()) {
            return ready.poll();
        }
        if (done) {
            return null;
        }
        while (ready.isEmpty() && !done) {
            String line = source.readLine();
            if (line == null) {
                flushBlock();
                if (!terminalSeen) {
                    throw malformed("stream ended without a terminal event");
                }
                if (pendingTerminal != null) {
                    ready.add(pendingTerminal);
                    pendingTerminal = null;
                }
                done = true;
                break;
            }
            if (line.isEmpty()) {
                flushBlock();
                continue;
            }
            if (line.startsWith(":")) {
                continue;
            }
            int colon = line.indexOf(':');
            String field = colon < 0 ? line : line.substring(0, colon);
            String value = colon < 0 ? "" : line.substring(colon + 1);
            if (value.startsWith(" ")) {
                value = value.substring(1);
            }
            switch (field) {
                case "event" -> eventName = value;
                case "data" -> {
                    if (hasData) {
                        data.append('\n');
                    }
                    data.append(value);
                    hasData = true;
                    if (data.length() > MAX_EVENT_DATA_CHARS) {
                        throw malformed("stream event data exceeded the maximum length");
                    }
                }
                default -> {
                    // id/retry/未知字段：忽略；绝不断点续传。
                }
            }
        }
        return ready.poll();
    }

    private void flushBlock() {
        String name = eventName;
        boolean hadData = hasData;
        String payload = hasData ? data.toString() : null;
        eventName = null;
        data.setLength(0);
        hasData = false;
        if (name == null && !hadData) {
            return;
        }
        eventCount++;
        if (eventCount > MAX_EVENTS) {
            throw malformed("stream exceeded the maximum event count");
        }
        if (name == null) {
            throw malformed("stream data without an event name");
        }
        if (!EVENTS.contains(name)) {
            throw malformed("unknown stream event");
        }
        if (terminalSeen) {
            throw malformed("stream event after the terminal event");
        }
        if (payload == null) {
            throw malformed("stream event missing data");
        }
        JsonNode root;
        try {
            root = MAPPER.readTree(payload);
        } catch (Exception unparseable) {
            throw malformed("stream event data is not valid JSON");
        }
        if (root == null || !root.isObject()) {
            throw malformed("stream event data is not a JSON object");
        }
        switch (name) {
            case "response.accepted" -> ready.add(GimbalAiEvent.accepted());
            case "response.delta" -> {
                JsonNode delta = root.get("delta");
                if (delta == null || !delta.isTextual()) {
                    throw malformed("response.delta event missing a textual 'delta'");
                }
                accumulatedChars += delta.asText().length();
                if (accumulatedChars > MAX_ACCUMULATED_CHARS) {
                    throw malformed("accumulated delta exceeded the maximum length");
                }
                ready.add(GimbalAiEvent.delta(delta.asText()));
            }
            case "response.completed" -> {
                JsonNode text = root.path("answer").path("text");
                if (!text.isTextual() || text.asText().isBlank()) {
                    throw malformed("response.completed event missing a non-blank answer.text");
                }
                if (text.asText().length() > MAX_ACCUMULATED_CHARS) {
                    throw malformed("response.completed answer.text exceeded the maximum length");
                }
                terminalSeen = true;
                pendingTerminal = GimbalAiEvent.completed(text.asText());
            }
            case "response.failed" -> {
                String code = root.path("code").isTextual()
                        ? GimbalAiCodes.sanitize(root.path("code").asText()) : null;
                terminalSeen = true;
                pendingTerminal = GimbalAiEvent.failed(code);
            }
            default -> throw malformed("unknown stream event");
        }
    }

    @Override
    public void close() {
        source.close();
    }

    private static GimbalAiException malformed(String detail) {
        return new GimbalAiException(GimbalAiFailureKind.MALFORMED,
                "gimbal AI downstream returned a malformed success stream: " + detail, null, null);
    }
}
