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
 * MediaAccessPolicy）、no-store + nosniff、不重定向长效签名 URL。
 *
 * <p><b>统一 404</b>：不存在、非 available、授权拒绝一律
 * 404 RESOURCE_NOT_VISIBLE——绝不返回 403（oracle B1：状态差异会泄露
 * 资源存在性与归属形状）。真实读取授权（T05 报告引用/T02 关系/T03 当前
 * 任务）由 B/C/D @Primary MediaAccessPolicy 实现；A 默认 owner-based。</p>
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
            // 与"不存在"同一信封同一状态码（不泄露存在性）
            throw new ApiException(ErrorCode.RESOURCE_NOT_VISIBLE, "media not visible");
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
