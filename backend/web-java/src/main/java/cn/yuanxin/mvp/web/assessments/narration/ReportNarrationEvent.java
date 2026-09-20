package cn.yuanxin.mvp.web.assessments.narration;

/**
 * 下游 SSE 事件（已由 {@link ReportNarrationSseParser} 校验并归一化）。
 *
 * <p>只允许四个类型：{@code ACCEPTED}（信息性）、{@code DELTA}（{@link #delta()} 为
 * {@code spoken_text} 增量）、{@code COMPLETED}（{@link #spokenText()} 为权威完整文本）、
 * {@code FAILED}（{@link #failedCode()} 仅作诊断）。</p>
 *
 * <p>与 {@code gimbalai} 的 {@code GimbalAiEvent} 同源范式；唯一字段差异是 complete 文本取
 * {@code data.spoken_text} 而非 {@code data.answer.text}（刻意不共享）。</p>
 */
record ReportNarrationEvent(Type type, String delta, String spokenText, String failedCode) {

    enum Type {
        ACCEPTED,
        DELTA,
        COMPLETED,
        FAILED
    }

    static ReportNarrationEvent accepted() {
        return new ReportNarrationEvent(Type.ACCEPTED, null, null, null);
    }

    static ReportNarrationEvent delta(String delta) {
        return new ReportNarrationEvent(Type.DELTA, delta, null, null);
    }

    static ReportNarrationEvent completed(String spokenText) {
        return new ReportNarrationEvent(Type.COMPLETED, null, spokenText, null);
    }

    static ReportNarrationEvent failed(String failedCode) {
        return new ReportNarrationEvent(Type.FAILED, null, null, failedCode);
    }
}
