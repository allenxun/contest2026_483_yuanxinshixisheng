package cn.yuanxin.mvp.web.gimbalai.dto;

import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Size;

/**
 * 云台 AI 文本透传请求体。
 *
 * <p><b>严格形状</b>：仅允许 {@code text} 一个字段。未知字段由全局
 * {@code spring.jackson.deserialization.fail-on-unknown-properties=true}
 * 拒绝 → 400 INVALID_INPUT（与项目既有严格请求体约定一致）。</p>
 *
 * <p>{@code text} 去空白后不得为空，长度上限 {@value #MAX_TEXT_LENGTH} 字符
 * （该上限是服务端本地策略，与下游 AI 契约的 input.text 上限无关）。</p>
 */
public record GimbalAiMessageRequest(
        @NotBlank(message = "text must not be blank")
        @Size(max = 2000, message = "text must not exceed 2000 characters")
        String text) {

    /** 服务端接受的用户文本最大长度（字符）。 */
    public static final int MAX_TEXT_LENGTH = 2000;
}
