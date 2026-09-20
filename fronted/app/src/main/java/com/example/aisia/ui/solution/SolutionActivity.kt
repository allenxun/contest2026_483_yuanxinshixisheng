package com.example.aisia.ui.solution

import android.content.Intent
import android.os.Bundle
import android.util.Log
import android.view.Gravity
import android.view.View
import android.widget.FrameLayout
import android.widget.ImageView
import android.widget.LinearLayout
import android.widget.ProgressBar
import android.widget.TextView
import android.widget.Toast
import androidx.appcompat.app.AlertDialog
import androidx.appcompat.app.AppCompatActivity
import coil.load
import com.example.aisia.MainActivity
import com.example.aisia.R
import com.example.aisia.network.HttpHelper
import org.json.JSONArray
import org.json.JSONObject

/**
 * 护肤方案页面（对应小程序 pages/solution/solution）
 *
 * 接收参数：
 *   - deviceId: 设备序列号（蓝牙 MAC）
 *   - report_id: 报告 ID
 *   - device_id: 设备数据库记录 ID（my-device 表）
 *
 * 调用 API：
 *   POST /api/my-device/{device_id}/treatment-plans  body: { report_id }
 *   返回：{ id, regions: [{ region, description, region_image_url }] }
 *
 * 交互：
 *   - 点击图片全屏预览
 *   - 点击建议项切换当前选中
 *   - "去护理" → 跳转 WorkActivity（TODO）
 *   - "返回首页" → 跳转 MainActivity
 */
class SolutionActivity : AppCompatActivity() {

    companion object {
        private const val TAG = "SolutionActivity"
    }

    private lateinit var ivFaceImage: ImageView
    private lateinit var progressBar: ProgressBar
    private lateinit var suggestionList: LinearLayout
    private lateinit var btnGoWork: TextView
    private lateinit var btnGoHome: TextView

    private var deviceId: String = ""
    private var reportId: String = ""
    private var deviceDatabaseId: String = ""
    private var info: JSONObject? = null
    private var tabList: List<JSONObject> = emptyList()
    private var currentIndex: Int = 0

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContentView(R.layout.activity_solution)

        // 接收参数
        deviceId = intent.getStringExtra("deviceId") ?: ""
        reportId = intent.getStringExtra("report_id") ?: ""
        deviceDatabaseId = intent.getStringExtra("device_id") ?: ""
        Log.d(TAG, "onCreate: deviceId=$deviceId, reportId=$reportId, deviceDatabaseId=$deviceDatabaseId")

        initViews()
        setupListeners()
        loadDetails()
    }

    private fun initViews() {
        ivFaceImage = findViewById(R.id.ivFaceImage)
        progressBar = findViewById(R.id.progressBar)
        suggestionList = findViewById(R.id.suggestionList)
        btnGoWork = findViewById(R.id.btnGoWork)
        btnGoHome = findViewById(R.id.btnGoHome)

        findViewById<View>(R.id.btnBack).setOnClickListener { finish() }

        // 设置图片区域高度为屏幕高度的 55%
        val faceSection = findViewById<FrameLayout>(R.id.faceSection)
        val screenHeight = resources.displayMetrics.heightPixels
        val targetHeight = (screenHeight * 0.55).toInt()
        faceSection.layoutParams.height = targetHeight
        faceSection.requestLayout()
    }

    private fun setupListeners() {
        // 点击图片全屏预览
        ivFaceImage.setOnClickListener {
            val url = if (tabList.isNotEmpty() && currentIndex < tabList.size) {
                tabList[currentIndex].optString("region_image_url", "")
            } else {
                info?.optString("region_image_url", "") ?: ""
            }
            if (url.isBlank() || url == "null") return@setOnClickListener
            val fullUrl = when {
                url.startsWith("http://") || url.startsWith("https://") -> url
                url.startsWith("//") -> "https:$url"
                else -> com.example.aisia.network.ApiConfig.BASE_URL.trimEnd('/') + "/" + url.trimStart('/')
            }
            com.example.aisia.ui.common.PhotoPreview.show(this, fullUrl, "护理分区")

        }

        // "去护理"按钮 → 跳转 WorkActivity（TODO: 创建护理页面）
        btnGoWork.setOnClickListener {
            val infoId = info?.optString("id") ?: ""
            val intent = Intent().apply {
                setClassName(this@SolutionActivity, "com.example.aisia.ui.work.WorkActivity")
                putExtra("report_id", infoId)
                putExtra("deviceId", deviceId)
                putExtra("device_id", deviceDatabaseId)
            }
            try {
                startActivity(intent)
            } catch (e: Exception) {
                Log.e(TAG, "WorkActivity not found", e)
                Toast.makeText(this, "护理页面开发中", Toast.LENGTH_SHORT).show()
            }
        }

        // "返回首页"按钮
        btnGoHome.setOnClickListener {
            val intent = Intent(this, MainActivity::class.java)
            intent.flags = Intent.FLAG_ACTIVITY_CLEAR_TOP or Intent.FLAG_ACTIVITY_NEW_TASK
            startActivity(intent)
            finish()
        }
    }

    /**
     * 加载方案详情
     * POST /api/my-device/{device_id}/treatment-plans  body: { report_id }
     * 路径参数 device_id 指 my-device 表的数据库记录 ID（非蓝牙 MAC 的 deviceId）。
     * 兼容：如果 intent 没传 device_id，则回退使用 deviceId（蓝牙 MAC）。
     */
    private fun loadDetails() {
        // 优先使用数据库记录 ID（device_id），否则回退到蓝牙 MAC（deviceId）
        val deviceIdForApi = deviceDatabaseId.ifBlank { deviceId }

        if (deviceIdForApi.isBlank() || reportId.isBlank()) {
            Log.w(TAG, "缺少 device_id / deviceId 或 reportId，无法加载方案")
            Toast.makeText(this, "参数缺失，无法加载方案", Toast.LENGTH_SHORT).show()
            return
        }

        Log.d(TAG, "loadDetails: 用于 API 的 device_id=$deviceIdForApi, report_id=$reportId")

        showLoading(true)

        HttpHelper.post(
            path = "/api/my-device/$deviceIdForApi/treatment-plans",
            params = mapOf("report_id" to reportId),
            onSuccess = { resp ->
                Log.d(TAG, "loadDetails success")
                runOnUiThread {
                    showLoading(false)
                    handleSuccess(resp)
                }
            },
            onFailure = { code, msg ->
                Log.e(TAG, "loadDetails failed: $code $msg")
                runOnUiThread {
                    showLoading(false)
                    Toast.makeText(this, "获取方案失败: $msg", Toast.LENGTH_SHORT).show()
                }
            }
        )
    }

    private fun handleSuccess(resp: String) {
        try {
            val root = JSONObject(resp)
            Log.d(TAG, "handleSuccess: parsing response")
            
            // 后端返回结构通常为 { data: { id, regions: [...] } }，兼容无 data 层
            val data = root.optJSONObject("data") ?: root
            info = data

            Log.d(TAG, "handleSuccess: regions=${data.optJSONArray("regions")?.length() ?: 0}")

            // 解析 regions 数组
            val regionsArray = data.optJSONArray("regions")
            tabList = if (regionsArray != null) {
                (0 until regionsArray.length()).map { i -> regionsArray.getJSONObject(i) }
            } else {
                emptyList()
            }

            Log.d(TAG, "handleSuccess: regions size=${tabList.size}")
            if (tabList.isNotEmpty()) {
                Log.d(TAG, "handleSuccess: first region=${tabList[0]}")
            }

            currentIndex = 0

            // 显示第一张图片
            updateFaceImage()

            // 渲染建议列表
            renderSuggestions()

        } catch (e: Exception) {
            Log.e(TAG, "parse response failed", e)
            Toast.makeText(this, "解析方案数据失败", Toast.LENGTH_SHORT).show()
        }
    }

    /**
     * 更新人脸区域图片（与小程序一致：始终使用 info.region_image_url）
     */
    private fun updateFaceImage() {
        // 小程序中图片始终来自 info.region_image_url
        val url = info?.optString("region_image_url", "") ?: ""
        Log.d(TAG, "updateFaceImage")

        val tvImageError = findViewById<TextView>(R.id.tvImageError)
        
        if (url.isBlank() || url == "null") {
            Log.w(TAG, "updateFaceImage: URL is empty or null")
            tvImageError.visibility = View.VISIBLE
            tvImageError.text = "暂无图片数据"
            ivFaceImage.setImageResource(R.drawable.face_placeholder)
            return
        }

        tvImageError.visibility = View.GONE
        Log.d(TAG, "updateFaceImage: loading")
        
        ivFaceImage.load(url) {
            crossfade(true)
            placeholder(R.drawable.face_placeholder)
            error(R.drawable.face_placeholder)
            listener(
                onStart = { Log.d(TAG, "Coil: onStart loading") },
                onSuccess = { _, _ -> 
                    Log.d(TAG, "Coil: onSuccess")
                    runOnUiThread { tvImageError.visibility = View.GONE }
                },
                onError = { _, errorResult -> 
                    Log.e(TAG, "Coil: image load failed: ${errorResult.throwable.javaClass.simpleName}")
                    runOnUiThread {
                        tvImageError.visibility = View.VISIBLE
                        tvImageError.text = "图片加载失败"
                    }
                }
            )
        }
    }

    /**
     * 渲染建议列表（对应小程序 suggestion-list）
     * 每项包含：圆点 + 区域名 + 描述 + 箭头
     * 选中项圆点放大 + 区域名蓝色加粗
     */
    private fun renderSuggestions() {
        suggestionList.removeAllViews()

        if (tabList.isEmpty()) return

        for (i in tabList.indices) {
            val region = tabList[i]
            val regionName = region.optString("region", "")
            val description = region.optString("description", "建议使用相应产品")
            val isActive = i == currentIndex

            // 行容器
            val row = LinearLayout(this).apply {
                orientation = LinearLayout.HORIZONTAL
                gravity = Gravity.CENTER_VERTICAL
                setPadding(0, dp2px(14), 0, dp2px(14))
                // 分隔线（最后一项不加）
                if (i < tabList.size - 1) {
                    // 通过 layoutParams 设置底部边框分隔
                }
                setOnClickListener { onTabChange(i) }
            }

            // 圆点
            val dot = View(this).apply {
                val size = if (isActive) dp2px(10) else dp2px(8)
                layoutParams = LinearLayout.LayoutParams(size, size).apply {
                    marginEnd = dp2px(10)
                }
                background = resources.getDrawable(
                    if (isActive) R.drawable.solution_dot_active_bg else R.drawable.solution_dot_bg,
                    null
                )
            }
            row.addView(dot)

            // 内容区
            val contentLayout = LinearLayout(this).apply {
                orientation = LinearLayout.HORIZONTAL
                gravity = Gravity.CENTER_VERTICAL
                layoutParams = LinearLayout.LayoutParams(0, LinearLayout.LayoutParams.WRAP_CONTENT, 1f)
            }

            // 区域名
            val tvRegion = TextView(this).apply {
                text = "$regionName："
                setTextColor(if (isActive) 0xFF3A6DF0.toInt() else 0xFF3A6DF0.toInt())
                textSize = 15f
                if (isActive) setTypeface(typeface, android.graphics.Typeface.BOLD)
            }
            contentLayout.addView(tvRegion)

            // 描述
            val tvDesc = TextView(this).apply {
                text = description
                setTextColor(0xFF666666.toInt())
                textSize = 14f
                maxLines = 1
                ellipsize = android.text.TextUtils.TruncateAt.END
                layoutParams = LinearLayout.LayoutParams(0, LinearLayout.LayoutParams.WRAP_CONTENT, 1f)
            }
            contentLayout.addView(tvDesc)

            row.addView(contentLayout)

            // 箭头
            val tvArrow = TextView(this).apply {
                text = "›"
                setTextColor(0xFFC0C0C8.toInt())
                textSize = 16f
                setPadding(dp2px(6), 0, 0, 0)
            }
            row.addView(tvArrow)

            // 分隔线（最后一项不加）
            if (i < tabList.size - 1) {
                val divider = View(this).apply {
                    layoutParams = LinearLayout.LayoutParams(
                        LinearLayout.LayoutParams.MATCH_PARENT,
                        1
                    )
                    setBackgroundColor(0xFFF0F1F3.toInt())
                }
                // 用包裹布局实现分隔线
                val wrapper = LinearLayout(this).apply {
                    orientation = LinearLayout.VERTICAL
                    layoutParams = LinearLayout.LayoutParams(
                        LinearLayout.LayoutParams.MATCH_PARENT,
                        LinearLayout.LayoutParams.WRAP_CONTENT
                    )
                }
                wrapper.addView(row)
                wrapper.addView(divider)
                suggestionList.addView(wrapper)
            } else {
                suggestionList.addView(row)
            }
        }
    }

    /**
     * 切换选中项（对应小程序 onTabChange）
     */
    private fun onTabChange(index: Int) {
        if (index == currentIndex) return
        currentIndex = index
        updateFaceImage()
        renderSuggestions()
    }

    private fun showLoading(show: Boolean) {
        progressBar.visibility = if (show) View.VISIBLE else View.GONE
    }

    private fun dp2px(dp: Int): Int {
        return (dp * resources.displayMetrics.density + 0.5f).toInt()
    }
}
