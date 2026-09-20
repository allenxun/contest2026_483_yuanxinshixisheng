package com.example.aisia.ui.devicehistory

import android.content.Intent
import android.os.Bundle
import android.util.Log
import android.view.View
import android.view.inputmethod.EditorInfo
import android.widget.EditText
import android.widget.TextView
import android.widget.Toast
import androidx.appcompat.app.AppCompatActivity
import androidx.recyclerview.widget.LinearLayoutManager
import androidx.recyclerview.widget.RecyclerView
import com.example.aisia.R
import com.example.aisia.network.HttpHelper
import org.json.JSONObject
import java.text.SimpleDateFormat
import java.util.Date
import java.util.Locale
import java.util.TimeZone

/**
 * 设备连接历史页面
 * - 进入时调用 GET /api/my-device 加载设备列表
 * - device_name 为空填充"未知设备"
 * - 列表中存在同名时按出现顺序追加 3 位数字后缀（首个保留原名）：
 *   原名, 原名001, 原名002 ...
 * - 401 已由 HttpHelper 全局处理（清 token 跳登录）
 * - 点击设备项跳转到 HistoryPlanActivity（历史设备方案列表）
 */
class DeviceHistoryActivity : AppCompatActivity() {

    companion object {
        private const val TAG = "DeviceHistoryActivity"
        private const val DEFAULT_NAME = "未知设备"
    }

    private lateinit var rv: RecyclerView
    private lateinit var tvEmpty: TextView
    private lateinit var etSearch: EditText
    private val adapter = DeviceHistoryAdapter()
    private val allItems = mutableListOf<DeviceHistoryItem>()

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContentView(R.layout.activity_device_history)

        findViewById<View>(R.id.btnBack).setOnClickListener { finish() }

        rv = findViewById(R.id.rvDevices)
        tvEmpty = findViewById(R.id.tvEmpty)
        etSearch = findViewById(R.id.etSearch)

        rv.layoutManager = LinearLayoutManager(this)
        rv.adapter = adapter

        // 点击设备项跳转到历史设备方案列表
        adapter.onItemClick = { item ->
            val intent = Intent(this, HistoryPlanActivity::class.java).apply {
                putExtra(HistoryPlanActivity.EXTRA_DEVICE_ID, item.id)
            }
            startActivity(intent)
        }

        // 搜索按钮点击事件
        findViewById<View>(R.id.btnSearch).setOnClickListener {
            performSearch()
        }

        // 键盘搜索按钮点击事件
        etSearch.setOnEditorActionListener { _, actionId, _ ->
            if (actionId == EditorInfo.IME_ACTION_SEARCH) {
                performSearch()
                true
            } else {
                false
            }
        }

        // Initial load runs in onResume.
    }

    override fun onResume() {
        super.onResume()
        // 每次回到页面时重新加载数据（与小程序 onShow 行为一致）
        loadDevices()
    }

    /**
     * 执行搜索（本地过滤）
     */
    private fun performSearch() {
        val keyword = etSearch.text.toString().trim()
        if (keyword.isEmpty()) {
            // 清空搜索时显示全部
            applyList(allItems)
            return
        }
        val filtered = allItems.filter { it.deviceName.contains(keyword, ignoreCase = true) }
        applyList(filtered)
    }

    private var requestInFlight = false
    private fun loadDevices() {
        if (requestInFlight || isFinishing || isDestroyed) return
        requestInFlight = true
        tvEmpty.setOnClickListener(null)
        if (allItems.isEmpty()) { tvEmpty.visibility = View.VISIBLE; tvEmpty.text = "加载中…" }
        HttpHelper.get(
            path = "/api/my-device?page=1&page_size=99",
            onSuccess = { resp ->
                val list = dedupNames(parseList(resp))
                runOnUiThread {
                    requestInFlight = false
                    if (isFinishing || isDestroyed) return@runOnUiThread
                    allItems.clear()
                    allItems.addAll(list)
                    performSearch()
                }
            },
            onFailure = { code, msg ->
                Log.e(TAG, "load devices failed: $code $msg")
                runOnUiThread {
                    requestInFlight = false
                    if (isFinishing || isDestroyed) return@runOnUiThread
                    if (code == 401) return@runOnUiThread  // 401 已由 HttpHelper 全局处理
                    Toast.makeText(this, "获取设备历史异常，请稍后重试", Toast.LENGTH_SHORT).show()
                    if (allItems.isEmpty()) {
                        tvEmpty.visibility = View.VISIBLE
                        tvEmpty.text = "加载失败，点击重试"
                        tvEmpty.setOnClickListener { loadDevices() }
                    }
                }
            }
        )
    }

    /**
     * 解析返回数据，兼容 {items:[...]} 与 {data:{items:[...]}}
     *
     * 后端字段（见 API CHANGES_FOR_FRONTEND.md §3.2）：
     *   id          string  设备 ID（雪花 BIGINT 字符串）
     *   device_name string? 设备名称
     *   updated_at  int     UTC 秒时间戳
     */
    private fun parseList(resp: String): List<DeviceHistoryItem> {
        if (resp.isBlank()) return emptyList()
        return try {
            val root = JSONObject(resp)
            val items = root.optJSONArray("items")
                ?: root.optJSONObject("data")?.optJSONArray("items")
                ?: return emptyList()
            (0 until items.length()).mapNotNull { i ->
                val obj = items.optJSONObject(i) ?: return@mapNotNull null
                val rawName = obj.optString("device_name")
                val name = if (rawName.isBlank() || rawName == "null") DEFAULT_NAME else rawName
                // id 在新协议里是字符串（雪花 BIGINT），不能再用 optInt
                val rawId = obj.optString("id")
                val id = if (rawId.isBlank() || rawId == "null") "" else rawId
                val updatedAt = obj.optLong("updated_at")
                val lastConnectTime = formatTimestamp(updatedAt)
                DeviceHistoryItem(
                    id = id,
                    deviceName = name,
                    updatedAt = updatedAt,
                    statusText = "已连接",
                    lastConnectTime = lastConnectTime
                )
            }
        } catch (e: Exception) {
            Log.e(TAG, "parse list failed", e)
            emptyList()
        }
    }

    /**
     * 将 UTC 秒时间戳格式化为可读字符串
     */
    private fun formatTimestamp(timestamp: Long): String {
        if (timestamp <= 0) return "未知时间"
        return try {
            val sdf = SimpleDateFormat("yyyy-MM-dd HH:mm:ss", Locale.getDefault())
            sdf.timeZone = TimeZone.getDefault()
            sdf.format(Date(timestamp * 1000))
        } catch (e: Exception) {
            "未知时间"
        }
    }

    /**
     * 同名设备追加 3 位数字后缀，首个保留原名：
     * 未知设备, 未知设备001, 未知设备002 ...
     */
    private fun dedupNames(list: List<DeviceHistoryItem>): List<DeviceHistoryItem> {
        val counter = mutableMapOf<String, Int>()
        return list.map { item ->
            val raw = item.deviceName
            val seen = counter.getOrDefault(raw, 0)
            counter[raw] = seen + 1
            val display = if (seen == 0) raw else "%s%03d".format(raw, seen)
            item.copy(deviceName = display)
        }
    }

    private fun applyList(list: List<DeviceHistoryItem>) {
        adapter.setItems(list)
        tvEmpty.text = if (etSearch.text.isNullOrBlank()) "暂无设备记录" else "未找到匹配设备"
        tvEmpty.setOnClickListener(null)
        tvEmpty.visibility = if (list.isEmpty()) View.VISIBLE else View.GONE
    }
}
