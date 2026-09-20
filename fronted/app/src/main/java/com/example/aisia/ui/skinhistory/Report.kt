package com.example.aisia.ui.skinhistory

/**
 * 测肤报告数据类
 *
 * 后端协议字段（详见 API_CHANGES_FOR_FRONTEND.md §4.4）：
 *   report_id        string  报告 ID（雪花 BIGINT 字符串）
 *   face_id          string  人脸 ID
 *   report_image_url string? 报告图片预签名 URL
 *   created_at       string  创建时间（兼容 create_time）
 *   skin_type        string? 皮肤类型
 *   skin_score       int?    皮肤评分
 */
data class Report(
    val reportId: String,
    val faceId: String,
    val reportImageUrl: String?,
    val createdAt: String?,
    val skinType: String? = null,
    val skinScore: Int? = null
)