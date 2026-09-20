package com.example.aisia.ui.devicehistory

import android.content.Intent
import android.os.Bundle
import android.util.Log
import android.view.View
import android.widget.TextView
import android.widget.Toast
import androidx.appcompat.app.AppCompatActivity
import androidx.recyclerview.widget.LinearLayoutManager
import androidx.recyclerview.widget.RecyclerView
import com.example.aisia.R
import com.example.aisia.network.HttpHelper
import org.json.JSONArray
import org.json.JSONObject
import java.text.SimpleDateFormat
import java.util.Date
import java.util.Locale

/**
 * 历史设备方案列表页面（模仿小程序 historyPlan）
 * - 进入时调用 GET /api/my-device/{deviceId}/treatment-plans 加载方案列表
 * - 处理重复的设备名称：第二个出现时在名称后加 001，第三个加 002，以此类推
 * - 点击方案项可跳转到方案详情（planDetail 页面），传参 deviceId + planId
 * - 401 已由 HttpHelper 全局处理（清 token 跳登录）
 */
class HistoryPlanActivity : AppCompatActivity() {

    companion object {
        private const val TAG = "HistoryPlanActivity"
        const val EXTRA_DEVICE_ID = "device_id"
    }

    private lateinit var rv: RecyclerView
    private lateinit var tvEmpty: TextView
    private val adapter = HistoryPlanAdapter()
    private var deviceId: String = ""

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContentView(R.layout.activity_history_plan)

        // 获取传入的设备 ID（从 DeviceHistoryActivity 跳转而来）
        deviceId = intent.getStringExtra(EXTRA_DEVICE_ID) ?: ""

        findViewById<View>(R.id.btnBack).setOnClickListener { finish() }

        rv = findViewById(R.id.rvPlans)
        tvEmpty = findViewById(R.id.tvEmpty)

        rv.layoutManager = LinearLayoutManager(this)
        rv.adapter = adapter

        // 点击方案项跳转到方案详情（与小程序 onConnectDevice 行为一致）
        adapter.onItemClick = { item ->
            val intent = Intent(this, PlanDetailActivity::class.java).apply {
                putExtra(PlanDetailActivity.EXTRA_DEVICE_ID, deviceId)
                putExtra(PlanDetailActivity.EXTRA_PLAN_ID, item.id)
            }
            startActivity(intent)
        }

        if (deviceId.isNotBlank()) {
            loadPlans()
        } else {
            Toast.makeText(this, "设备 ID 无效", Toast.LENGTH_SHORT).show()
            finish()
        }
    }

    private fun loadPlans() {
        HttpHelper.get(
            path = "/api/my-device/$deviceId/treatment-plans?page=1&page_size=99",
            onSuccess = { resp ->
                val list = parseList(resp)
                val deduped = dedupNames(list)
                runOnUiThread { applyList(deduped) }
            },
            onFailure = { code, msg ->
                Log.e(TAG, "load plans failed: $code $msg")
                runOnUiThread {
                    if (code == 401) return@runOnUiThread
                    Toast.makeText(this, "获取设备历史异常，请稍后重试", Toast.LENGTH_SHORT).show()
                    applyList(emptyList())
                }
            }
        )
    }

    /**
     * 解析返回数据，兼容 {items:[...]} 与 {data:{items:[...]}}
     *
     * 后端字段：
     *   id               string  方案 ID
     *   device_name      string? 使用的方案名称
     *   created_at       string/int  创建时间
     *   duration         string  时长
     *   executed_regions Any?    执行的区域
     */
    private fun parseList(resp: String): List<HistoryPlanItem> {
        if (resp.isBlank()) return emptyList()
        return try {
            val root = JSONObject(resp)
            val items = root.optJSONArray("items")
                ?: root.optJSONObject("data")?.optJSONArray("items")
                ?: return emptyList()
            (0 until items.length()).mapNotNull { i ->
                val obj = items.optJSONObject(i) ?: return@mapNotNull null
                val rawId = obj.optString("id")
                val id = if (rawId.isBlank() || rawId == "null") "" else rawId
                val deviceName = obj.optString("device_name").let {
                    if (it.isBlank() || it == "null") "未知设备" else it
                }
                val createdAt = formatCreatedAt(obj.opt("created_at"))
                val duration = obj.optString("duration").let {
                    if (it.isBlank() || it == "null") "00:00" else it
                }
                val plans = parseRegions(obj.opt("executed_regions"))
                HistoryPlanItem(
                    id = id,
                    deviceName = deviceName,
                    createdAt = createdAt,
                    duration = duration,
                    plans = plans
                )
            }
        } catch (e: Exception) {
            Log.e(TAG, "parse list failed", e)
            emptyList()
        }
    }

    /**
     * 格式化创建时间（与小程序 formatTime 行为一致）
     * 支持时间戳（秒）和字符串格式
     */
    private fun formatCreatedAt(raw: Any?): String {
        if (raw == null || raw == JSONObject.NULL) return ""
        val str = raw.toString()
        if (str.isBlank() || str == "null") return ""
        // 尝试解析为时间戳（秒）
        return try {
            val ts = str.toLong()
            if (ts > 0) {
                val sdf = SimpleDateFormat("yyyy-MM-dd HH:mm", Locale.getDefault())
                sdf.format(Date(ts * 1000))
            } else {
                str
            }
        } catch (e: NumberFormatException) {
            // 已经是字符串格式，直接返回
            str
        }
    }

    /**
     * 解析 executed_regions 字段（可能是数组、对象或字符串）
     * 与小程序 getName() 方法行为一致
     */
    private fun parseRegions(obj: Any?): String {
        if (obj == null || obj == JSONObject.NULL) return ""
        return when (obj) {
            is JSONArray -> {
                val list = mutableListOf<String>()
                for (i in 0 until obj.length()) {
                    val item = obj.optString(i)
                    if (item.isNotBlank() && item != "null") list.add(item)
                }
                list.joinToString(",")
            }
            is JSONObject -> {
                val keys = mutableListOf<String>()
                val it = obj.keys()
                while (it.hasNext()) {
                    keys.add(it.next())
                }
                keys.joinToString(",")
            }
            else -> obj.toString()
        }
    }

    /**
     * 处理重复的设备名称（与小程序 handleGetMyDeviceSuccess 行为一致）
     * 第二个出现时在名称后加 001，第三个加 002，以此类推
     */
    private fun dedupNames(list: List<HistoryPlanItem>): List<HistoryPlanItem> {
        val counts = mutableMapOf<String, Int>()
        return list.map { item ->
            val name = item.deviceName
            val seen = counts.getOrDefault(name, 0)
            counts[name] = seen + 1
            if (seen == 0) {
                item
            } else {
                val suffix = seen.toString().padStart(3, '0')
                item.copy(deviceName = "$name$suffix")
            }
        }
    }

    private fun applyList(list: List<HistoryPlanItem>) {
        adapter.setItems(list)
        tvEmpty.visibility = if (list.isEmpty()) View.VISIBLE else View.GONE
    }
}