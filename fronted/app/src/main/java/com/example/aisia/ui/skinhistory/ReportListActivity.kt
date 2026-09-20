package com.example.aisia.ui.skinhistory

import android.animation.ObjectAnimator
import android.app.Dialog
import android.graphics.Color
import android.graphics.drawable.ColorDrawable
import android.view.Gravity
import android.view.ViewGroup
import android.view.Window
import android.widget.Button
import android.content.Intent
import android.os.Bundle
import android.os.Handler
import android.os.Looper
import android.util.Log
import android.view.View
import android.view.animation.LinearInterpolator
import android.widget.LinearLayout
import android.widget.TextView
import android.widget.Toast
import androidx.appcompat.app.AppCompatActivity
import androidx.recyclerview.widget.LinearLayoutManager
import androidx.recyclerview.widget.RecyclerView
import com.example.aisia.R
import com.example.aisia.network.HttpHelper
import com.example.aisia.ui.skintest.SmartSkinTestActivity
import org.json.JSONObject
import java.text.SimpleDateFormat
import java.util.Locale
import java.util.Date

/**
 * 报告列表页面
 * - 进入时调用 GET /api/self-research-face/faces/{faceId}/reports 加载报告列表
 * - 支持分页加载（滚动到底部自动加载下一页）
 * - 点击报告项跳转到报告详情页
 * - 如果有 deviceId，点击时显示方案生成蒙层
 * - 401 已由 HttpHelper 全局处理（清 token 跳登录）
 */
class ReportListActivity : AppCompatActivity() {

    companion object {
        private const val TAG = "ReportListActivity"
        private const val PAGE_SIZE = 10
    }

    private lateinit var rv: RecyclerView
    private lateinit var tvEmpty: TextView
    private lateinit var tvLoading: TextView
    private lateinit var btnBack: View
    private lateinit var tvTitle: TextView
    private lateinit var btnAdd: View
    private lateinit var generatingMask: View
    private lateinit var generatingClose: View
    private lateinit var generatingScanLine: View
    private lateinit var generatingItems: LinearLayout
    private lateinit var generatingDone: View
    private lateinit var btnCompare: Button
    private lateinit var tvNoRecords: TextView

    private val adapter = ReportAdapter()
    private var faceId: String = ""
    private var faceNickname: String = ""
    private var deviceId: String? = null
    private var device_id: String = ""
    private var page = 1
    private var total = 0
    private var isLoading = false
    private var hasMore = true
    private val handler = Handler(Looper.getMainLooper())
    private var genTimer: Runnable? = null
    private var genReportId: String = ""
    private var isFirstResume = true

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContentView(R.layout.activity_report_list)

        faceId = intent.getStringExtra("faceId") ?: ""
        faceNickname = intent.getStringExtra("faceNickname") ?: ""
        // 兼容 deviceId 参数：null/"null"/"undefined"/空串 都视为无设备
        val rawDeviceId = intent.getStringExtra("deviceId")
        deviceId = if (rawDeviceId.isNullOrEmpty() || rawDeviceId == "null" || rawDeviceId == "undefined") null else rawDeviceId
        device_id = intent.getStringExtra("device_id") ?: ""

        Log.d(TAG, "onCreate: faceId=$faceId, faceNickname=$faceNickname, deviceId=$deviceId, device_id=$device_id")

        initViews()
        setupRecyclerView()
        setupListeners()
        loadReports()
    }

    override fun onResume() {
        super.onResume()
        // 首次 onResume 由 onCreate 中的 loadReports 处理，后续返回时刷新列表
        if (!isFirstResume) {
            page = 1
            total = 0
            hasMore = true
            isLoading = false  // 确保不被上次未完成的加载阻塞
            loadReports()
        }
        isFirstResume = false
    }

    private fun initViews() {
        rv = findViewById(R.id.rvReports)
        tvEmpty = findViewById(R.id.tvEmpty)
        tvLoading = findViewById(R.id.tvLoading)
        btnBack = findViewById(R.id.btnBack)
        tvTitle = findViewById(R.id.tvTitle)
        btnAdd = findViewById(R.id.btnAdd)
        generatingMask = findViewById(R.id.generatingMask)
        generatingClose = findViewById(R.id.generatingClose)
        generatingScanLine = findViewById(R.id.generatingScanLine)
        generatingItems = findViewById(R.id.generatingItems)
        generatingDone = findViewById(R.id.generatingDone)
        btnCompare = findViewById(R.id.btnCompare)
        tvNoRecords = findViewById(R.id.tvNoRecords)
        // 数据加载前隐藏对比按钮和提示文字，加载后由 updateEmptyState() 控制显示
        btnCompare.visibility = View.GONE
        tvNoRecords.visibility = View.GONE

        // 设置标题
        tvTitle.text = faceNickname.ifEmpty { "测肤历史" }
    }

    private fun setupRecyclerView() {
        rv.layoutManager = LinearLayoutManager(this)
        rv.adapter = adapter

        // 滚动到底部加载更多
        rv.addOnScrollListener(object : RecyclerView.OnScrollListener() {
            override fun onScrolled(recyclerView: RecyclerView, dx: Int, dy: Int) {
                super.onScrolled(recyclerView, dx, dy)
                if (dy > 0) {
                    val layoutManager = recyclerView.layoutManager as LinearLayoutManager
                    val lastVisibleItem = layoutManager.findLastVisibleItemPosition()
                    val totalItemCount = layoutManager.itemCount

                    if (lastVisibleItem >= totalItemCount - 1 && !isLoading && hasMore) {
                        loadMore()
                    }
                }
            }
        })
    }

    private fun setupListeners() {
        btnBack.setOnClickListener { finish() }

        btnAdd.setOnClickListener {
            startActivity(Intent(this, SmartSkinTestActivity::class.java))
        }

        // 点击报告项：如果有 deviceId 则显示方案生成蒙层，否则直接跳转
        adapter.onItemClick = { report ->
            if (report.reportId.isEmpty()) {
                Toast.makeText(this, "该记录缺少 id，无法跳转", Toast.LENGTH_SHORT).show()
            } else if (deviceId != null) {
                startGenerating(report.reportId)
            } else {
                navigateToReport(report.reportId)
            }
        }

        // 关闭方案生成蒙层
        generatingClose.setOnClickListener {
            cancelGeneration()
        }

        // 测肤历史对比按钮 —— 弹窗选择两条报告，点击底部"对比"按钮跳转对比页面
        btnCompare.setOnClickListener {
            showCompareDialog()
        }
    }

    private fun loadReports() {
        if (isLoading) return
        isLoading = true
        showLoading(true)

        val path = "/api/self-research-face/faces/$faceId/reports?page=$page&page_size=$PAGE_SIZE"
        Log.d(TAG, "loadReports: $path")

        HttpHelper.get(
            path = path,
            onSuccess = { resp ->
                Log.d(TAG, "loadReports success")
                val result = parseReports(resp)
                runOnUiThread {
                    isLoading = false
                    showLoading(false)
                    if (page == 1) {
                        adapter.setItems(result.first)
                    } else {
                        adapter.appendItems(result.first)
                    }
                    total = result.second
                    // 与小程序一致：hasMore = total > page * page_size
                    hasMore = total > page * PAGE_SIZE
                    updateLoadingTip()
                    updateEmptyState()
                }
            },
            onFailure = { code, msg ->
                Log.e(TAG, "loadReports failed: $code $msg")
                runOnUiThread {
                    isLoading = false
                    showLoading(false)
                    updateLoadingTip()
                    updateEmptyState()
                    if (code != 401) {
                        Toast.makeText(this, "加载失败: $msg", Toast.LENGTH_SHORT).show()
                    }
                }
            }
        )
    }

    private fun loadMore() {
        page++
        loadReports()
    }

    /**
     * 解析报告列表响应
     * 兼容多种格式：
     * - {items:[...], total:N}
     * - {data:{items:[...], total:N}}
     * - {data:[...]}
     * - {list:[...]}
     * - 直接返回数组 [...]
     *
     * 后端字段（见 API_CHANGES_FOR_FRONTEND.md §4.4）：
     *   report_id        string  报告 ID
     *   face_id          string  人脸 ID
     *   report_image_url string? 报告图片预签名 URL
     *   created_at       string  创建时间（兼容 create_time）
     *   skin_type        string? 皮肤类型
     *   skin_score       int?    皮肤评分
     */
    private fun parseReports(resp: String): Pair<List<Report>, Int> {
        if (resp.isBlank()) return Pair(emptyList(), 0)
        return try {
            // 尝试直接解析为数组
            if (resp.trim().startsWith("[")) {
                val arr = org.json.JSONArray(resp)
                return Pair(parseReportArray(arr), arr.length())
            }

            val root = JSONObject(resp)
            Log.d(TAG, "parseReports root keys: ${root.keys().asSequence().toList()}")

            // 尝试获取 data 对象
            val dataObj = root.optJSONObject("data")
            val items = root.optJSONArray("items")
                ?: root.optJSONArray("list")
                ?: dataObj?.optJSONArray("items")
                ?: dataObj?.optJSONArray("list")
                ?: root.optJSONObject("result")?.optJSONArray("items")
                ?: root.optJSONObject("result")?.optJSONArray("list")
                ?: root.optJSONArray("data")
                ?: return Pair(emptyList(), 0)

            val total = root.optInt("total", 0)
                .let { if (it == 0) dataObj?.optInt("total", 0) ?: 0 else it }

            Log.d(TAG, "parseReports items length: ${items.length()}, total: $total")
            Pair(parseReportArray(items), if (total > 0) total else items.length())
        } catch (e: Exception) {
            Log.e(TAG, "parse reports failed", e)
            Pair(emptyList(), 0)
        }
    }

    private fun parseReportArray(items: org.json.JSONArray): List<Report> {
        return (0 until items.length()).mapNotNull { i ->
            val obj = items.optJSONObject(i) ?: return@mapNotNull null
            Report(
                reportId = obj.optString("report_id").ifEmpty { obj.optString("id") },
                faceId = obj.optString("face_id").ifEmpty { obj.optString("faceId") },
                reportImageUrl = obj.optString("report_image_url").takeIf { it.isNotBlank() && it != "null" },
                createdAt = formatTime(obj.optString("created_at").ifEmpty { obj.optString("create_time") }),
                skinType = obj.optString("skin_type").takeIf { it.isNotBlank() && it != "null" },
                skinScore = if (obj.has("skin_score")) obj.optInt("skin_score", 0) else null
            )
        }
    }

    /**
     * 格式化时间，参考小程序 formatTime 实现：
     * - 如果是纯数字（Unix 时间戳，秒级），转为 yyyy/MM/dd HH:mm:ss
     * - 如果是字符串日期，尝试解析后格式化
     */
    private fun formatTime(timeStr: String?): String {
        if (timeStr.isNullOrBlank()) return ""

        // 尝试作为 Unix 时间戳（秒级数字）处理
        val tsLong = timeStr.toLongOrNull()
        if (tsLong != null && tsLong > 1000000000L) {
            val outputFormat = SimpleDateFormat("yyyy/MM/dd HH:mm:ss", Locale.getDefault())
            return outputFormat.format(Date(tsLong * 1000))
        }

        // 尝试作为字符串日期解析
        // 注意：格式中带字面量 'Z' 的表示该字符串实际是 UTC 时间，
        // 解析时必须把时区设为 UTC，否则会少 8 小时（被当作本地时间解析）
        val inputFormats = listOf(
            "yyyy-MM-dd'T'HH:mm:ss.SSS'Z'" to true,
            "yyyy-MM-dd'T'HH:mm:ss'Z'" to true,
            "yyyy-MM-dd'T'HH:mm:ss.SSSZ" to false,
            "yyyy-MM-dd'T'HH:mm:ssZ" to false,
            "yyyy-MM-dd'T'HH:mm:ss" to false,
            "yyyy-MM-dd HH:mm:ss" to false,
            "yyyy-MM-dd HH:mm" to false,
            "yyyy/MM/dd HH:mm:ss" to false
        )
        val outputFormat = SimpleDateFormat("yyyy/MM/dd HH:mm:ss", Locale.getDefault())
        for ((fmt, isUtc) in inputFormats) {
            try {
                val inputFormat = SimpleDateFormat(fmt, Locale.getDefault())
                if (isUtc) {
                    inputFormat.timeZone = java.util.TimeZone.getTimeZone("UTC")
                }
                val date: Date = inputFormat.parse(timeStr) ?: continue
                return outputFormat.format(date)
            } catch (_: Exception) {
            }
        }
        // 如果所有格式都解析失败，返回原始字符串
        return timeStr
    }

    private fun showLoading(show: Boolean) {
        tvLoading.visibility = if (show) View.VISIBLE else View.GONE
    }

    private fun updateLoadingTip() {
        if (isLoading) {
            tvLoading.text = "加载中..."
            tvLoading.visibility = View.VISIBLE
        } else if (!hasMore && adapter.itemCount > 0) {
            tvLoading.text = "已到底部"
            tvLoading.visibility = View.VISIBLE
        } else {
            tvLoading.visibility = View.GONE
        }
    }

    private fun updateEmptyState() {
        val isEmpty = adapter.itemCount == 0 && !isLoading
        tvEmpty.visibility = if (isEmpty) View.VISIBLE else View.GONE
        // 报告数据不足两条时隐藏"测肤历史对比"按钮（无法对比）
        val showCompare = !isLoading && adapter.itemCount >= 2
        btnCompare.visibility = if (showCompare) View.VISIBLE else View.GONE
        // 不足两条记录时，在按钮位置下方显示提示文案
        if (!isLoading && adapter.itemCount < 2) {
            tvNoRecords.visibility = View.VISIBLE
            tvNoRecords.text = if (adapter.itemCount == 0) "暂无测肤记录" else "至少需要2条测肤记录才能对比"
        } else {
            tvNoRecords.visibility = View.GONE
        }
    }

    private fun navigateToReport(reportId: String) {
        val intent = Intent(this, com.example.aisia.ui.report.SkinReportActivity::class.java).apply {
            putExtra("reportId", reportId)
            putExtra("faceId", faceId)
            putExtra("id", faceId)  // SkinReportActivity 读取 "id" 参数
            putExtra("type", "list")
            putExtra("deviceId", deviceId)
        }
        startActivity(intent)
    }

    // ==== 测肤历史对比弹窗 ====

    private fun showCompareDialog() {
        val allReports = adapter.getItems()
        if (allReports.size < 2) {
            Toast.makeText(this, "至少需要两条报告记录才能对比", Toast.LENGTH_SHORT).show()
            return
        }

        val dialog = Dialog(this)
        dialog.requestWindowFeature(Window.FEATURE_NO_TITLE)
        dialog.setContentView(R.layout.dialog_report_compare)
        dialog.setCancelable(true)

        // setContentView 之后、show() 之前配置窗口属性，确保首次渲染就用正确尺寸，避免空白
        dialog.window?.apply {
            setBackgroundDrawable(ColorDrawable(Color.TRANSPARENT))
            decorView.setPadding(0, 0, 0, 0)
            val screenHeight = resources.displayMetrics.heightPixels
            val dialogHeight = (screenHeight * 0.75).toInt()
            setLayout(ViewGroup.LayoutParams.MATCH_PARENT, dialogHeight)
            setGravity(Gravity.CENTER)
        }

        // 选中状态集合（LinkedHashSet 保持勾选顺序），默认选中前两条数据
        val selectedIds = mutableSetOf<String>()
        selectedIds.add(allReports[0].reportId)
        selectedIds.add(allReports[1].reportId)

        // 弹窗内控件
        val rvCompare = dialog.findViewById<RecyclerView>(R.id.rvCompareList)
        val btnConfirm = dialog.findViewById<Button>(R.id.btnDialogConfirm)

        // 弹窗列表适配器：仅维护选中状态，选中数量变化时刷新"对比"按钮可用状态
        val compareAdapter = CompareDialogAdapter(allReports, selectedIds) { count ->
            btnConfirm.isEnabled = count == 2
            btnConfirm.isClickable = count == 2
            btnConfirm.alpha = if (count == 2) 1.0f else 0.5f
        }

        rvCompare.layoutManager = LinearLayoutManager(this)
        rvCompare.adapter = compareAdapter

        // prevent double-click navigation
        var isNavigating = false
        btnConfirm.setOnClickListener {
            if (isNavigating) return@setOnClickListener
            if (selectedIds.size != 2) {
                Toast.makeText(this, "请选择两条数据进行对比", Toast.LENGTH_SHORT).show()
                return@setOnClickListener
            }
            isNavigating = true
            val ids = selectedIds.toList()
            handler.post {
                dialog.dismiss()
                val intent = Intent(this@ReportListActivity, ReportCompareActivity::class.java).apply {
                    putExtra("reportIdA", ids[0])
                    putExtra("reportIdB", ids[1])
                    putExtra("faceId", faceId)
                }
                startActivity(intent)
            }
        }

        dialog.show()
    }
    // ==== 方案生成蒙层：7 条步骤，3 秒一条，全部点亮后跳 solution ====

    private val generatingLabels = listOf(
        "识别皮肤问题",
        "智能 分析数据",
        "肌肤肤质类型判定",
        "肌肤问题根源溯源分析",
        "肌肤风险等级评估",
        "定制每日护肤流程方案",
        "生成最终个性化护肤报告"
    )

    private val generationHandler = Handler(Looper.getMainLooper())

    private fun startGenerating(reportId: String) {
        if (isFinishing || isDestroyed) return
        cancelGeneration()
        genReportId = reportId
        // The destination loads the actual plan; decorative steps must not delay it.
        navigateToSolution()
    }

    private fun lightGen(index: Int) {
        if (index >= generatingItems.childCount) return
        val itemView = generatingItems.getChildAt(index)
        val tvCheck = itemView.findViewById<TextView>(R.id.tvCheck)
        val tvStep = itemView.findViewById<TextView>(R.id.tvStep)

        // 激活状态
        itemView.setBackgroundResource(R.drawable.gen_item_active_bg)
        tvStep.setTextColor(0xFF3D2E27.toInt())
        itemView.alpha = 1.0f

        // 1.5 秒后显示完成标记
        generationHandler.postDelayed({
            tvCheck.visibility = View.VISIBLE
        }, 1500)
    }

    private fun startScanLineAnimation() {
        val animator = ObjectAnimator.ofFloat(generatingScanLine, "translationY", 0f, 300f)
        animator.duration = 2000
        animator.repeatCount = ObjectAnimator.INFINITE
        animator.interpolator = LinearInterpolator()
        animator.start()
        generatingScanLine.tag = animator
    }

    private fun cancelGeneration() {
        generationHandler.removeCallbacksAndMessages(null)
        genTimer = null
        generatingMask.visibility = View.GONE
        // 停止扫描线动画
        (generatingScanLine.tag as? ObjectAnimator)?.cancel()
    }

    private fun navigateToSolution() {
        if (isFinishing || isDestroyed) return
        // TODO: 跳转到方案页面，传递 deviceId、report_id、device_id
        val intent = Intent().apply {
            setClassName(this@ReportListActivity, "com.example.aisia.ui.solution.SolutionActivity")
            putExtra("deviceId", deviceId)
            putExtra("report_id", genReportId)
            putExtra("device_id", device_id)
        }
        try {
            startActivity(intent)
        } catch (e: Exception) {
            Log.e(TAG, "SolutionActivity not found, falling back to report", e)
            navigateToReport(genReportId)
        }
    }


    override fun onDestroy() {
        super.onDestroy()
        cancelGeneration()
    }
}
