package cn.yuanxin.mvp.web.assessments.narration;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

import java.util.ArrayDeque;
import java.util.Deque;
import java.util.Set;

/**
 * 下游 {@code /internal/v1/weijing/reports/assess:stream} 的<b>增量</b> SSE 解析器
 * （严格 fail-closed）。与 {@code gimbalai} 的 {@code GimbalAiSseParser} 同源范式、刻意不共享；
 * 唯一字段差异是 {@code response.completed} 取 {@code data.spoken_text}（gimbalai 取
 * {@code data.answer.text}）。</p>
 *
 * <p>只接受四个事件：{@code response.accepted}（信息性）、{@code response.delta}
 * （按序累加 {@code data.delta} 即 {@code spoken_text} 增量）、{@code response.completed}
 * （成功终态；{@code data.spoken_text} 权威）、{@code response.failed}（终态失败，
 * {@code code} 仅作诊断）。</p>
 *
 * <p><b>顺序纪律（fail-closed）</b>：{@code response.accepted} 必须且只能是流的<b>第一个</b>事件；
 * 首个事件不是 accepted（含 delta/终态先到）→ {@code MALFORMED}；重复 accepted → {@code MALFORMED}。
 * 这保证外部 {@code start} 恰一帧且 seq=1。</p>
 *
 * <p><b>fail-closed</b>：未知事件、事件后又有事件（含重复终态）、缺终态（EOF）、
 * 事件缺 data、data 非 JSON/非对象、{@code response.delta} 缺文本、
 * {@code response.completed} 缺非空 {@code spoken_text}、事件顺序违规（缺首 accepted / 重复 accepted）、
 * 事件数/累计增量越界 → 抛
 * {@link ReportNarrationException}（{@code MALFORMED}）。读取超时/传输失败由行源抛
 * {@code TIMEOUT}/{@code UNAVAILABLE}。绝不返回部分/合成文案。</p>
 *
 * <p><b>两条流纪律裁定（§6.3）</b>：</p>
 * <ol>
 *   <li><b>零 delta 即失败</b>：{@code completed} 到达时一个 delta 都没发过 → {@code MALFORMED}，
 *       外部只发一个 {@code error} 终态。理由：设备将朗读不到任何内容却收到 {@code done}，那是假成功。</li>
 *   <li><b>拼接与 {@code spoken_text} 不一致只告警不失败</b>：累计 delta 与
 *       {@code completed.spoken_text} <b>逐字比较</b>（同长度不同内容也会命中），不等时
 *       {@code log.warn} 记录<b>两者的字符长度</b>（绝不记录内容），仍正常发 {@code done}。
 *       是否不一致可由包级 {@link #spokenTextMismatch()} 直接断言（不靠捕获日志）。
 *       理由：文本已真实逐段送达客户端，AI 自身摘要与
 *       其增量不一致属下游内部矛盾；在已送达全部文本后再发 {@code error} 会让设备在朗读完毕后显示失败。</li>
 * </ol>
 *
 * <p>终止策略：遇到终态事件后，仍继续读到流结束以检出"终态后事件/重复终态"；此类违规一律
 * malformed。终态事件在流结束（EOF）后才可被消费，从而保证恰一个终态。</p>
 *
 * <p><b>有界</b>（与行源的 64 KiB 单行上限叠加）：单事件累积 data 上限
 * {@value #MAX_EVENT_DATA_CHARS} 字符、事件数上限 {@value #MAX_EVENTS}、累计增量与
 * {@code spoken_text} 上限 {@value #MAX_ACCUMULATED_CHARS} 字符——任一越界即 {@code MALFORMED}，
 * 绝不无界累积。</p>
 */
final class ReportNarrationSseParser implements AutoCloseable {

    private static final Logger log = LoggerFactory.getLogger(ReportNarrationSseParser.class);

    private static final ObjectMapper MAPPER = new ObjectMapper();

    private static final Set<String> EVENTS = Set.of(
            "response.accepted", "response.delta", "response.completed", "response.failed");

    /** 单次流事件的硬上限（防无界事件流）。 */
    static final int MAX_EVENTS = 10_000;
    /** 单事件累积 data 字符上限（多行 data 也受限）。 */
    static final int MAX_EVENT_DATA_CHARS = 256 * 1024;
    /** 累计 delta 与 completed.spoken_text 字符上限。 */
    static final int MAX_ACCUMULATED_CHARS = 200_000;

    private final ReportNarrationLineSource source;
    private final Deque<ReportNarrationEvent> ready = new ArrayDeque<>();

    private boolean done;
    private boolean terminalSeen;
    private ReportNarrationEvent pendingTerminal;

    private String eventName;
    private final StringBuilder data = new StringBuilder();
    private boolean hasData;
    private int eventCount;
    private int accumulatedChars;
    private final StringBuilder accumulatedText = new StringBuilder();
    private boolean deltaSeen;
    private boolean acceptedSeen;
    private boolean spokenTextMismatch;

    ReportNarrationSseParser(ReportNarrationLineSource source) {
        this.source = source;
    }

    /**
     * 下一个已校验事件；流在终态后正常结束返回 {@code null}。
     *
     * @throws ReportNarrationException 协议违规（MALFORMED）或读取超时/传输失败（TIMEOUT/UNAVAILABLE）
     */
    ReportNarrationEvent next() {
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
                continue; // SSE 注释行 / heartbeat：忽略
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
        // 顺序纪律：response.accepted 必须且只能是流的第一个事件（heartbeat 走注释行，不算事件）。
        if (!acceptedSeen && !"response.accepted".equals(name)) {
            throw malformed("stream event before response.accepted");
        }
        if (acceptedSeen && "response.accepted".equals(name)) {
            throw malformed("duplicate response.accepted");
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
            case "response.accepted" -> {
                acceptedSeen = true;
                ready.add(ReportNarrationEvent.accepted());
            }
            case "response.delta" -> {
                JsonNode delta = root.get("delta");
                if (delta == null || !delta.isTextual()) {
                    throw malformed("response.delta event missing a textual 'delta'");
                }
                accumulatedChars += delta.asText().length();
                if (accumulatedChars > MAX_ACCUMULATED_CHARS) {
                    throw malformed("accumulated delta exceeded the maximum length");
                }
                accumulatedText.append(delta.asText());
                deltaSeen = true;
                ready.add(ReportNarrationEvent.delta(delta.asText()));
            }
            case "response.completed" -> {
                JsonNode text = root.get("spoken_text");
                if (text == null || !text.isTextual() || text.asText().isBlank()) {
                    throw malformed("response.completed event missing a non-blank spoken_text");
                }
                if (text.asText().length() > MAX_ACCUMULATED_CHARS) {
                    throw malformed("response.completed spoken_text exceeded the maximum length");
                }
                if (!deltaSeen) {
                    throw malformed("response.completed arrived without any delta");
                }
                if (!accumulatedText.toString().equals(text.asText())) {
                    // 绝不记录内容：只记两者字符长度。
                    spokenTextMismatch = true;
                    log.warn("report narration spoken_text mismatch accumulatedChars={} completedChars={}",
                            accumulatedChars, text.asText().length());
                }
                terminalSeen = true;
                pendingTerminal = ReportNarrationEvent.completed(text.asText());
            }
            case "response.failed" -> {
                String code = root.path("code").isTextual()
                        ? ReportNarrationCodes.sanitize(root.path("code").asText()) : null;
                terminalSeen = true;
                pendingTerminal = ReportNarrationEvent.failed(code);
            }
            default -> throw malformed("unknown stream event");
        }
    }

    /**
     * 累计 delta 的完整文本与 {@code completed.spoken_text} 是否<b>逐字</b>不一致。
     * 仅供单测直接断言，绝不暴露任何文本内容。
     */
    boolean spokenTextMismatch() {
        return spokenTextMismatch;
    }

    @Override
    public void close() {
        source.close();
    }

    private static ReportNarrationException malformed(String detail) {
        return new ReportNarrationException(ReportNarrationFailureKind.MALFORMED,
                "report narration downstream returned a malformed stream: " + detail, null, null);
    }
}
