package cn.yuanxin.mvp.web.media;

import java.time.Instant;
import java.util.UUID;

/** T11 media_objects 行投影（A 基础读写所需列；归属列由 B/C/D 接纳时补齐）。 */
public record MediaObject(
        UUID id,
        String bucket,
        String objectKey,
        MediaPurpose purpose,
        String state,
        String uploaderType,
        String uploaderRef,
        UUID requestId,
        String contentType,
        Long byteSize,
        String contentHash) {
}
