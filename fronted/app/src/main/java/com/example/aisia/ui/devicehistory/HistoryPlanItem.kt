package com.example.aisia.ui.devicehistory

/**
 * 历史设备方案项
 *
 * 后端字段：
 *   id               string  方案 ID
 *   device_name      string? 使用的方案名称
 *   created_at       string  创建时间
 *   duration         string  时长
 *   executed_regions Any?    执行的区域（数组/对象/字符串）
 */
data class HistoryPlanItem(
    val id: String,
    val deviceName: String,
    val createdAt: String,
    val duration: String,
    val plans: String
)