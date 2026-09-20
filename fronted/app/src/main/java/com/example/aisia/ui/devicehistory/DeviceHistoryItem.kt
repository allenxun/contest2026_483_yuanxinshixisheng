package com.example.aisia.ui.devicehistory

/**
 * 设备连接历史项
 *
 * 后端协议字段（详见 API_CHANGES_FOR_FRONTEND.md §3.2）：
 *   id          string  用户名下设备 ID（BIGINT 序列化为字符串）
 *   device_name string? 设备名称
 *   updated_at  int     UTC 秒时间戳
 *
 * 注：旧版的 device_id 字段已废弃，所有设备相关接口改用 [id] 作为 my_device_id。
 */
data class DeviceHistoryItem(
    val id: String,
    val deviceName: String,
    val updatedAt: Long,
    val statusText: String = "已连接",
    val lastConnectTime: String = "未知时间"
)