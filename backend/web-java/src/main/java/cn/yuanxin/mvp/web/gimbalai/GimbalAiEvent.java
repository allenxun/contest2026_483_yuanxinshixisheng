package cn.yuanxin.mvp.web.gimbalai;

/**
 * 下游 SSE 事件（已由 {@link GimbalAiSseParser} 校验并归一化）。
 *
 * <p>只允许四个类型：{@code ACCEPTED}（信息性）、{@code DELTA}（{@link #delta()}）、
 * {@code COMPLETED}（{@link #answerText()} 权威）、{@code FAILED}（{@link #failedCode()}）。</p>
 */
record GimbalAiEvent(Type type, String delta, String answerText, String failedCode) {

    enum Type {
        ACCEPTED,
        DELTA,
        COMPLETED,
        FAILED
    }

    static GimbalAiEvent accepted() {
        return new GimbalAiEvent(Type.ACCEPTED, null, null, null);
    }

    static GimbalAiEvent delta(String delta) {
        return new GimbalAiEvent(Type.DELTA, delta, null, null);
    }

    static GimbalAiEvent completed(String answerText) {
        return new GimbalAiEvent(Type.COMPLETED, null, answerText, null);
    }

    static GimbalAiEvent failed(String failedCode) {
        return new GimbalAiEvent(Type.FAILED, null, null, failedCode);
    }
}
