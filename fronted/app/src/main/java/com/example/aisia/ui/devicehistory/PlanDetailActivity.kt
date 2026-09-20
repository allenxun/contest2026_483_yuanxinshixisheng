package com.example.aisia.ui.devicehistory

import android.app.AlertDialog
import android.content.Intent
import android.os.Bundle
import android.util.Log
import android.view.LayoutInflater
import android.view.View
import android.view.ViewGroup
import android.widget.ImageView
import android.widget.TextView
import android.widget.Toast
import androidx.appcompat.app.AppCompatActivity
import androidx.recyclerview.widget.LinearLayoutManager
import androidx.recyclerview.widget.RecyclerView
import coil.load
import com.example.aisia.MainActivity
import com.example.aisia.R
import com.example.aisia.network.HttpHelper
import org.json.JSONObject

/**
 * 方案详情页面（模仿小程序 planDetail）
 * - 进入时调用 GET /api/my-device/{deviceId}/treatment-plans/{planId} 加载详情
 * - 显示人脸图（点击可全屏预览，与小程序 showPreview 一致）
 * - 显示建议列表（regions）
 * - 底部按钮返回首页（与小程序 goIndex switchTab 行为一致）
 * - 加载中显示 loading 状态（与小程序 wx.showLoading 一致）
 */
class PlanDetailActivity : AppCompatActivity() {

    companion object {
        private const val TAG = "PlanDetailActivity"
        const val EXTRA_DEVICE_ID = "device_id"
        const val EXTRA_PLAN_ID = "plan_id"
    }

    private lateinit var ivFace: ImageView
    private lateinit var rvSuggestions: RecyclerView
    private val suggestionAdapter = SuggestionAdapter()

    private var deviceId: String = ""
    private var planId: String = ""
    private var faceImageUrl: String = ""

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContentView(R.layout.activity_plan_detail)

        deviceId = intent.getStringExtra(EXTRA_DEVICE_ID) ?: ""
        planId = intent.getStringExtra(EXTRA_PLAN_ID) ?: ""

        ivFace = findViewById(R.id.ivFace)
        rvSuggestions = findViewById(R.id.rvSuggestions)

        findViewById<View>(R.id.btnBack).setOnClickListener { finish() }
        findViewById<View>(R.id.btnGoHome).setOnClickListener {
            // 返回首页（与小程序 switchTab 行为一致：清除栈回到首页）
            val intent = Intent(this, MainActivity::class.java).apply {
                flags = Intent.FLAG_ACTIVITY_NEW_TASK or Intent.FLAG_ACTIVITY_CLEAR_TASK
            }
            startActivity(intent)
            finish()
        }

        // 点击图片全屏预览（与小程序 showPreview wx.previewImage 一致）
        ivFace.setOnClickListener {
            showPreview()
        }

        rvSuggestions.layoutManager = LinearLayoutManager(this)
        rvSuggestions.adapter = suggestionAdapter

        if (deviceId.isNotBlank() && planId.isNotBlank()) {
            loadDetail()
        } else {
            Toast.makeText(this, "参数无效", Toast.LENGTH_SHORT).show()
            finish()
        }
    }

    /**
     * 点击图片全屏预览（与小程序 showPreview 行为一致）
     * 使用 AlertDialog 模拟 wx.previewImage 全屏预览效果
     */
    private fun showPreview() {
        if (faceImageUrl.isBlank()) return
        val imageView = ImageView(this).apply {
            load(faceImageUrl)
            scaleType = ImageView.ScaleType.FIT_CENTER
        }
        AlertDialog.Builder(this)
            .setView(imageView)
            .setOnDismissListener { }
            .show()
    }

    private fun loadDetail() {
        // 显示加载中（与小程序 wx.showLoading 一致）
        Toast.makeText(this, "加载中...", Toast.LENGTH_SHORT).show()

        HttpHelper.get(
            path = "/api/my-device/$deviceId/treatment-plans/$planId",
            onSuccess = { resp ->
                runOnUiThread { bindDetail(resp) }
            },
            onFailure = { code, msg ->
                Log.e(TAG, "load detail failed: $code $msg")
                runOnUiThread {
                    if (code == 401) return@runOnUiThread
                    Toast.makeText(this, "获取方案详情异常，请稍后重试", Toast.LENGTH_SHORT).show()
                }
            }
        )
    }

    /**
     * 绑定详情数据（与小程序 handleGetFaceSuccess 行为一致）
     * - info = data
     * - tabList = data.regions
     * - currentTab = data.regions[0].region
     */
    private fun bindDetail(resp: String) {
        if (resp.isBlank()) return
        try {
            val root = JSONObject(resp)
            // 同时兼容 { data: {...} } 和旧版直接返回 {...}，不改变旧接口行为。
            val data = root.optJSONObject("data") ?: root

            // 加载人脸图（与小程序 info.region_image_url 一致）
            faceImageUrl = data.optString("region_image_url")
            if (faceImageUrl.isNotBlank() && faceImageUrl != "null") {
                ivFace.load(faceImageUrl) {
                    crossfade(true)
                }
            }

            // 解析建议列表（与小程序 tabList = data.regions 一致）
            val regions = data.optJSONArray("regions") ?: return
            val list = mutableListOf<SuggestionItem>()
            for (i in 0 until regions.length()) {
                val regionObj = regions.optJSONObject(i) ?: continue
                val region = regionObj.optString("region")
                val description = regionObj.optString("description").ifBlank { "建议使用相应产品" }
                list.add(SuggestionItem(region = region, description = description))
            }
            suggestionAdapter.setItems(list)
        } catch (e: Exception) {
            Log.e(TAG, "parse detail failed", e)
        }
    }

    /** 建议项（与小程序 tabList 中的 item 一致） */
    data class SuggestionItem(val region: String, val description: String)

    /**
     * 建议列表适配器（与小程序 suggestion-list 一致）
     * - 蓝色圆点 + 区域名（蓝色加粗）+ 建议描述 + 箭头
     * - 项之间有分割线（最后一项无分割线）
     */
    class SuggestionAdapter : RecyclerView.Adapter<SuggestionAdapter.VH>() {
        private val items = mutableListOf<SuggestionItem>()

        class VH(itemView: View) : RecyclerView.ViewHolder(itemView) {
            val tvRegion: TextView = itemView.findViewById(R.id.tvRegion)
            val tvDescription: TextView = itemView.findViewById(R.id.tvDescription)
            val divider: View = itemView.findViewById(R.id.divider)
        }

        override fun onCreateViewHolder(parent: ViewGroup, viewType: Int): VH {
            val view = LayoutInflater.from(parent.context)
                .inflate(R.layout.item_suggestion, parent, false)
            return VH(view)
        }

        override fun onBindViewHolder(holder: VH, position: Int) {
            val item = items[position]
            // 区域名 + 冒号（与小程序 "{{item.region}}：" 一致）
            holder.tvRegion.text = "${item.region}："
            // 建议描述（与小程序 "{{item.description || '建议使用相应产品'}}" 一致）
            holder.tvDescription.text = item.description
            // 最后一项隐藏分割线（与小程序 .suggestion-item:last-child border-bottom:none 一致）
            holder.divider.visibility = if (position == items.size - 1) View.GONE else View.VISIBLE
        }

        override fun getItemCount(): Int = items.size

        fun setItems(list: List<SuggestionItem>) {
            items.clear()
            items.addAll(list)
            notifyDataSetChanged()
        }
    }
}
