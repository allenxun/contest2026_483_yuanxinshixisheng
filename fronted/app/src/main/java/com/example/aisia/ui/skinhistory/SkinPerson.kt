package com.example.aisia.ui.skinhistory

/**
 * 测肤历史中的人脸条目
 *
 * 后端协议字段（详见 API_CHANGES_FOR_FRONTEND.md §4.3）：
 *   face_id        string  人脸 ID（雪花 BIGINT 字符串，原 person_id）
 *   face_nickname  string  显示名称（原 name）
 *   record_count   int     该 face 下的报告数量
 *   face_image_url string? 代表图预签名 URL（1 小时有效）
 */
data class SkinPerson(
    val faceId: String,
    val faceNickname: String,
    val recordCount: Int,
    val faceImageUrl: String?,
    val createTime: String? = null
)
