package com.example.aisia.ui.skinhistory

import android.content.Intent
import android.os.Bundle
import android.util.Log
import android.view.View
import android.widget.TextView
import androidx.appcompat.app.AppCompatActivity
import androidx.recyclerview.widget.LinearLayoutManager
import androidx.recyclerview.widget.RecyclerView
import com.example.aisia.R
import com.example.aisia.network.HttpHelper
import com.example.aisia.ui.skintest.SmartSkinTestActivity
import org.json.JSONObject

/**
 * 测肤历史页面
 * - 进入时调用 GET /api/self-research-face/faces 加载人脸列表
 *   （旧路径 /persons 已废弃，详见 API_CHANGES_FOR_FRONTEND.md §4.2）
 * - 401 已由 HttpHelper 全局处理（清 token 跳登录）
 */
class SkinHistoryActivity : AppCompatActivity() {

    companion object {
        private const val TAG = "SkinHistoryActivity"
    }

    private lateinit var rv: RecyclerView
    private lateinit var tvEmpty: TextView
    private val adapter = SkinPersonAdapter()

    // 从 SkincareFragment 传入的设备参数
    private var id: String? = null          // 数据库记录ID（my-device API 返回的 id）
    private var deviceId: String? = null    // 设备序列号/蓝牙MAC（device_sn）
    private var deviceName: String? = null
    private var deviceType: String? = null

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContentView(R.layout.activity_skin_history)

        // 接收设备参数（id 和 deviceId 都传）
        id = intent.getStringExtra("id")
        deviceId = intent.getStringExtra("deviceId")
        deviceName = intent.getStringExtra("deviceName")
        deviceType = intent.getStringExtra("deviceType")
        Log.d(TAG, "onCreate: id=$id, deviceId=$deviceId, deviceName=$deviceName, deviceType=$deviceType")

        findViewById<View>(R.id.btnBack).setOnClickListener { finish() }

        rv = findViewById(R.id.rvPersons)
        tvEmpty = findViewById(R.id.tvEmpty)
        rv.layoutManager = LinearLayoutManager(this)
        rv.adapter = adapter

        // 点击列表项跳转到报告列表页面（带上 id、deviceId、device_id）
        adapter.onItemClick = { person ->
            val intent = Intent(this, ReportListActivity::class.java).apply {
                putExtra("faceId", person.faceId)
                putExtra("faceNickname", person.faceNickname)
                // 传递 id（数据库记录ID）作为 device_id
                if (!id.isNullOrEmpty()) {
                    putExtra("device_id", id)  // ← 关键：把 id 作为 device_id 传递
                }
                if (!deviceId.isNullOrEmpty()) {
                    putExtra("deviceId", deviceId)
                }
            }
            startActivity(intent)
        }

        // 点击添加按钮跳转到测肤页面（带上 id 和 deviceId）
        findViewById<View>(R.id.btnAdd).setOnClickListener {
            val intent = Intent(this, SmartSkinTestActivity::class.java).apply {
                if (!id.isNullOrEmpty()) {
                    putExtra("id", id)
                }
                if (!deviceId.isNullOrEmpty()) {
                    putExtra("deviceId", deviceId)
                }
                putExtra("deviceName", deviceName)
                putExtra("deviceType", deviceType)
            }
            startActivity(intent)
        }

        // 如果有 deviceId，按设备加载历史；否则加载全部
        if (!deviceId.isNullOrEmpty()) {
            loadPersonsByDevice(deviceId!!)
        } else {
            loadPersons()
        }
    }

    /**
     * 按设备ID加载历史记录
     * GET /api/self-research-face/faces?deviceId=xxx
     */
    private var requestInFlight = false
    private fun loadPersonsByDevice(deviceId: String) = loadPersons(deviceId)
    private fun loadPersons(filterDevice: String? = null) {
        if (requestInFlight || isFinishing || isDestroyed) return
        requestInFlight = true
        tvEmpty.text = "加载中…"
        tvEmpty.setOnClickListener(null)
        val path = "/api/self-research-face/faces" +
            (filterDevice?.let { "?deviceId=" + android.net.Uri.encode(it) } ?: "")
        HttpHelper.get(
            path = path,
            onSuccess = { resp ->
                val list = parseList(resp)
                runOnUiThread {
                    requestInFlight = false
                    if (isFinishing || isDestroyed) return@runOnUiThread
                    applyList(list)
                    tvEmpty.text = "暂无测肤记录"
                }
            },
            onFailure = { code, _ ->
                runOnUiThread {
                    requestInFlight = false
                    if (isFinishing || isDestroyed || code == 401) return@runOnUiThread
                    tvEmpty.visibility = View.VISIBLE
                    tvEmpty.text = "加载失败，点击重试"
                    tvEmpty.setOnClickListener { loadPersons(filterDevice) }
                }
            }
        )
    }

    /**
     * 解析返回数据，兼容多种格式：
     * - {items:[...]}
     * - {data:{items:[...]}}
     * - {data:[...]}
     * - {list:[...]}
     * - {data:{list:[...]}}
     * - 直接返回数组 [...]
     *
     * 后端字段（见 API_CHANGES_FOR_FRONTEND.md §4.3）：
     *   face_id        string  人脸 ID（原 person_id）
     *   face_nickname  string  显示名称（原 name）
     *   record_count   int     报告数量
     *   face_image_url string? 代表图预签名 URL（1 小时有效）
     *   create_time    string? 创建时间
     */
    private fun parseList(resp: String): List<SkinPerson> {
        if (resp.isBlank()) return emptyList()
        return try {
            // 尝试直接解析为数组
            if (resp.trim().startsWith("[")) {
                val arr = org.json.JSONArray(resp)
                return parseArray(arr)
            }
            
            val root = JSONObject(resp)
            Log.d(TAG, "parseList root keys: ${root.keys().asSequence().toList()}")
            
            // 尝试多种可能的 items 字段名
            val items = root.optJSONArray("items")
                ?: root.optJSONArray("list")
                ?: root.optJSONArray("data")
                ?: root.optJSONObject("data")?.optJSONArray("items")
                ?: root.optJSONObject("data")?.optJSONArray("list")
                ?: root.optJSONObject("result")?.optJSONArray("items")
                ?: root.optJSONObject("result")?.optJSONArray("list")
                ?: return emptyList()
            
            Log.d(TAG, "parseList items length: ${items.length()}")
            parseArray(items)
        } catch (e: Exception) {
            Log.e(TAG, "parse list failed", e)
            emptyList()
        }
    }
    
    private fun parseArray(items: org.json.JSONArray): List<SkinPerson> {
        return (0 until items.length()).mapNotNull { i ->
            val obj = items.optJSONObject(i) ?: return@mapNotNull null
            SkinPerson(
                faceId = obj.optString("face_id").ifEmpty { obj.optString("id") },
                faceNickname = obj.optString("face_nickname").ifEmpty { 
                    obj.optString("nickname").ifEmpty { obj.optString("name") }
                },
                recordCount = obj.optInt("record_count", 0),
                faceImageUrl = obj.optString("face_image_url").takeIf { it.isNotBlank() && it != "null" },
                createTime = obj.optString("create_time").takeIf { it.isNotBlank() && it != "null" }
            )
        }
    }

    private fun applyList(list: List<SkinPerson>) {
        adapter.setItems(list)
        tvEmpty.visibility = if (list.isEmpty()) View.VISIBLE else View.GONE
    }
}
