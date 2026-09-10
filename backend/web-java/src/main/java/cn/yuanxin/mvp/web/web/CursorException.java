package cn.yuanxin.mvp.web.web;

/** 非法游标 → 400 INVALID_INPUT（reason=invalid_cursor；契约 Cursor 参数说明）。 */
public class CursorException extends RuntimeException {
    public CursorException(String message) {
        super(message, null, true, false);
    }
}
