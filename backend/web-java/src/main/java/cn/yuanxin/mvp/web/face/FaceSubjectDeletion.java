package cn.yuanxin.mvp.web.face;

/**
 * 人脸主体<b>删除</b>视图（供应商无关；B 内部使用，绝不外发给 APP/云台）。
 *
 * <p>{@code deleted=false} 表示本次调用未删除任何行——重复删除是<b>幂等</b>的：
 * 已不存在的主体再次删除不会抛异常，而是给出 {@code deleted=false} 这一明确结果。
 * 由于服务端 404 错误信封不携带库修订号，重复删除时 {@code libraryRevision} 回退为
 * {@link #UNKNOWN_LIBRARY_REVISION}（未知），调用方不得据此推断库状态。</p>
 *
 * @param deleted         是否删除了一行（false = 主体本就不存在）
 * @param libraryRevision 删除后的库修订号；重复删除（服务端 404）时为 {@link #UNKNOWN_LIBRARY_REVISION}
 * @param requestId       服务端请求标识，用于对账
 */
public record FaceSubjectDeletion(boolean deleted, long libraryRevision, String requestId) {

    /** 服务端 404 信封不提供库修订号时的诚实占位值（未知，不是真实的 0/-1）。 */
    public static final long UNKNOWN_LIBRARY_REVISION = -1L;
}