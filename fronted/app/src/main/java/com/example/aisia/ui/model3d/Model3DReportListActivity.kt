package com.example.aisia.ui.model3d

import android.animation.ObjectAnimator
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
import com.example.aisia.ui.skinhistory.Report
import com.example.aisia.ui.skintest.SmartSkinTestActivity
import org.json.JSONObject
import java.text.SimpleDateFormat
import java.util.Locale
import java.util.Date

/**
 * 3D模型报告列表页面
 * - 模仿 ReportListActivity 实现
 * - 进入时调用 GET /api/self-research-face/faces/{faceId}/reports 加载报告列表
 * - 支持分页加载（滚动到底部自动加载下一页）
 * - 点击报告项跳转到报告详情页
 * - 如果有 deviceId，点击时显示方案生成蒙层
 * - 401 已由 HttpHelper 全局处理（清 token 跳登录）
 */
class Model3DReportListActivity : AppCompatActivity() {

    companion object {
        private const val TAG = "Model3DReportList"
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

    private val adapter = Report3DAdapter()
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

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContentView(R.layout.activity_model_3d_report_list)

        faceId = intent.getStringExtra("faceId") ?: ""
        faceNickname = intent.getStringExtra("faceNickname") ?: ""
        val rawDeviceId = intent.getStringExtra("deviceId")
        deviceId = if (rawDeviceId.isNullOrEmpty() || rawDeviceId == "null" || rawDeviceId == "undefined") null else rawDeviceId
        device_id = intent.getStringExtra("device_id") ?: ""

        Log.d(TAG, "onCreate: faceId=$faceId, faceNickname=$faceNickname, deviceId=$deviceId, device_id=$device_id")

        initViews()
        setupRecyclerView()
        setupListeners()
        loadReports()
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

        // 设置标题
        tvTitle.text = faceNickname.ifEmpty { "3D模型报告" }
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

        // 点击报告项：跳转到 Scan3DActivity，传 reportId 作为 task_id，3dType=list
        adapter.onItemClick = { report ->
            if (report.reportId.isEmpty()) {
                Toast.makeText(this, "该记录缺少 id，无法跳转", Toast.LENGTH_SHORT).show()
            } else {
                val intent = Intent(this, com.example.aisia.ui.skintest.Scan3DActivity::class.java).apply {
                    putExtra("task_id", report.reportId)
                    putExtra("3dType", "list")
                }
                startActivity(intent)
            }
        }

        // 关闭方案生成蒙层
        generatingClose.setOnClickListener {
            cancelGeneration()
        }
    }

    private fun loadReports() {
        if (isLoading) return
        isLoading = true
        showLoading(true)

        val path = "/api/3d/faces/$faceId/tasks?page=$page&page_size=$PAGE_SIZE"
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

    private fun parseReports(resp: String): Pair<List<Report>, Int> {
        if (resp.isBlank()) return Pair(emptyList(), 0)
        return try {
            if (resp.trim().startsWith("[")) {
                val arr = org.json.JSONArray(resp)
                return Pair(parseReportArray(arr), arr.length())
            }

            val root = JSONObject(resp)
            Log.d(TAG, "parseReports root keys: ${root.keys().asSequence().toList()}")

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
        val inputFormats = listOf(
            "yyyy-MM-dd'T'HH:mm:ss.SSS'Z'",
            "yyyy-MM-dd'T'HH:mm:ss'Z'",
            "yyyy-MM-dd'T'HH:mm:ss.SSSZ",
            "yyyy-MM-dd'T'HH:mm:ssZ",
            "yyyy-MM-dd'T'HH:mm:ss",
            "yyyy-MM-dd HH:mm:ss",
            "yyyy-MM-dd HH:mm",
            "yyyy/MM/dd HH:mm:ss"
        )
        val outputFormat = SimpleDateFormat("yyyy/MM/dd HH:mm:ss", Locale.getDefault())
        for (fmt in inputFormats) {
            try {
                val inputFormat = SimpleDateFormat(fmt, Locale.getDefault())
                val date: Date = inputFormat.parse(timeStr) ?: continue
                return outputFormat.format(date)
            } catch (_: Exception) {
            }
        }
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
        tvEmpty.visibility = if (adapter.itemCount == 0 && !isLoading) View.VISIBLE else View.GONE
    }

    private fun navigateToReport(reportId: String) {
        val intent = Intent(this, com.example.aisia.ui.report.SkinReportActivity::class.java).apply {
            putExtra("reportId", reportId)
            putExtra("faceId", faceId)
        }
        startActivity(intent)
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

    private fun startGenerating(reportId: String) {
        genReportId = reportId
        generatingMask.visibility = View.VISIBLE
        generatingDone.visibility = View.GONE

        generatingItems.removeAllViews()
        for (label in generatingLabels) {
            val itemView = layoutInflater.inflate(R.layout.item_generating_step, generatingItems, false)
            val tvStep = itemView.findViewById<TextView>(R.id.tvStep)
            tvStep.text = label
            generatingItems.addView(itemView)
        }

        startScanLineAnimation()

        lightGen(0)
        var idx = 1
        genTimer = Runnable {
            if (idx < generatingLabels.size) {
                lightGen(idx)
                idx++
                handler.postDelayed(genTimer!!, 3000)
            } else {
                handler.postDelayed({
                    generatingDone.visibility = View.VISIBLE
                    handler.postDelayed({
                        cancelGeneration()
                        navigateToSolution()
                    }, 1200)
                }, 1500)
            }
        }
        handler.postDelayed(genTimer!!, 3000)
    }

    private fun lightGen(index: Int) {
        if (index >= generatingItems.childCount) return
        val itemView = generatingItems.getChildAt(index)
        val tvCheck = itemView.findViewById<TextView>(R.id.tvCheck)
        val tvStep = itemView.findViewById<TextView>(R.id.tvStep)

        itemView.setBackgroundResource(R.drawable.gen_item_active_bg)
        tvStep.setTextColor(0xFF3D2E27.toInt())
        itemView.alpha = 1.0f

        handler.postDelayed({
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
        genTimer?.let { handler.removeCallbacks(it) }
        genTimer = null
        generatingMask.visibility = View.GONE
        (generatingScanLine.tag as? ObjectAnimator)?.cancel()
    }

    private fun navigateToSolution() {
        val intent = Intent().apply {
            setClassName(this@Model3DReportListActivity, "com.example.aisia.ui.solution.SolutionActivity")
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
