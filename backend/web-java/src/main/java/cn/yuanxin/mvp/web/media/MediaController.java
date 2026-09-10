package cn.yuanxin.mvp.web.media;

import cn.yuanxin.mvp.web.auth.PrincipalContext;
import cn.yuanxin.mvp.web.error.ApiException;
import cn.yuanxin.mvp.web.error.ErrorCode;
import org.springframework.http.CacheControl;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

import java.io.InputStream;
import java.util.UUID;

/**
 * GET /api/v1/media/{mediaId}/content —— 受控读取基础协议（DD 10.2；
 * x-foundation，不占 27 编号）：逐次鉴权（PrincipalContext →
 * MediaAccessPolicy）、no-store + nosniff、不重定向长效签名 URL；
 * 不存在/未 available/存储缺对象统一 404 RESOURCE_NOT_VISIBLE。
 */
@RestController
@RequestMapping("/api/v1/media")
public class MediaController {

    private final MediaService mediaService;
    private final MediaAccessPolicy accessPolicy;

    public MediaController(MediaService mediaService, MediaAccessPolicy accessPolicy) {
        this.mediaService = mediaService;
        this.accessPolicy = accessPolicy;
    }

    @GetMapping("/{mediaId}/content")
    public ResponseEntity<org.springframework.core.io.InputStreamResource> content(
            @PathVariable UUID mediaId, PrincipalContext principal) {
        MediaObject media = mediaService.load(mediaId);
        if (media == null || !"available".equals(media.state())) {
            throw new ApiException(ErrorCode.RESOURCE_NOT_VISIBLE, "media not visible");
        }
        if (!accessPolicy.canAccess(principal, media)) {
            throw new ApiException(ErrorCode.CALLER_NOT_ALLOWED, "caller not allowed for this media");
        }
        InputStream in = mediaService.openContent(media);
        if (in == null) {
            throw new ApiException(ErrorCode.RESOURCE_NOT_VISIBLE, "media not visible");
        }
        return ResponseEntity.ok()
                .contentType(org.springframework.http.MediaType.parseMediaType(media.contentType()))
                .cacheControl(CacheControl.noStore())
                .header("X-Content-Type-Options", "nosniff")
                .body(new org.springframework.core.io.InputStreamResource(in));
    }
}
