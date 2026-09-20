package com.example.aisia.ui.report

import android.animation.ObjectAnimator
import android.animation.ValueAnimator
import android.annotation.SuppressLint
import android.app.AlertDialog
import android.content.Intent
import android.graphics.Color
import android.os.Bundle
import android.os.CountDownTimer
import android.util.Log
import android.view.Gravity
import android.view.View
import android.view.animation.AccelerateDecelerateInterpolator
import android.view.animation.LinearInterpolator
import android.webkit.WebView
import android.webkit.WebViewClient
import android.widget.ImageView
import android.widget.FrameLayout
import android.widget.LinearLayout
import android.widget.ProgressBar
import android.widget.TextView
import android.widget.Toast
import androidx.appcompat.app.AppCompatActivity
import androidx.core.content.ContextCompat
import coil.load
import coil.request.ImageRequest
import com.example.aisia.R
import com.example.aisia.network.ApiConfig
import com.example.aisia.network.HttpHelper
import com.example.aisia.ui.skintest.SmartSkinTestActivity
import org.json.JSONArray
import org.json.JSONObject
import java.text.SimpleDateFormat
import java.util.Date
import java.util.Locale

/**
 * 测肤报告页
 * 参考小程序 packageScan/report 页面实现
 *
 * 页面内容：
 * - 机甲风外框（折角 + 梯形内凹）
 * - 指标卡（3 列：肤质+得分、水分水滴、弹性得分 + 折线图）
 * - 改善建议卡
 * - 下一步按钮
 *
 * 支持参数传递：
 * - type: 类型 (img/list)
 * - reportId: 报告ID
 * - deviceId: 设备ID
 * - oss_key: OSS 图片 key
 * - id: 记录ID (face_id)
 */
class SkinReportActivity : AppCompatActivity() {

    companion object {
        private const val TAG = "SkinReport"
        /** 这两个页面的接口超时时间（秒） */
        private const val API_TIMEOUT_SECONDS = 50L
    }

    private lateinit var webViewChart: WebView
    private lateinit var webViewRadar: WebView
    private var loadingDialog: AlertDialog? = null
    private var noFaceDialog: AlertDialog? = null

    // 参数
    private var type: String = "img"
    private var reportId: String? = null
    private var deviceId: String? = null
    private var ossKey: String? = null
    private var id: String? = null
    private var imagePath: String? = null

    // 数据（默认为空，接口返回后填充）
    private var skinType: String = ""
    private var skinScore: Int? = null
    private var moistureLevel: Int = 0
    private var elasticityScore: Int = 0
    private var skinAge: Int? = null
    private var skinAgeScore: Int? = null  // skin_age对应的score值
    private var chartXData: List<Number> = emptyList()
    private var chartYData: List<Number> = emptyList()
    private var referenceScore: Int = 0
    private var suggestion: String = ""

    // 接口返回的 face_id 和 report_id
    private var apiFaceId: String? = null
    private var apiReportId: String? = null

    private var chartReady: Boolean = false
    private var radarChartReady: Boolean = false

    // ────── 报告详情数据（合并自 ReportDetailActivity）──────
    private var overallScore: Int = 0

    data class RadarItem(val name: String, val value: Int)

    /** 检测表格行数据：分区/相对分数/条数/像素长度/平均线段/最长线段/密度/占比/面积 */
    data class DetectTableRow(
        val zone: String,
        val score: String,
        val count: String,
        val pixelLength: String,
        val avgLength: String,
        val maxLength: String,
        val density: String,
        val ratio: String,
        val area: String,
        /** 分区对应的预览图片 URL（region_image_url），空串表示无 */
        val regionImageUrl: String = ""
    )

    /** 单类检测数据（皱纹/红区/色斑/痤疮） */
    data class DetectData(
        val detected: Boolean,
        val imageUrl: String,
        val rows: List<DetectTableRow>,
        /** 自定义表头；null 时使用默认9列表头 */
        val headers: List<String>? = null
    )

    private var radarItems: List<RadarItem> = emptyList()

    private var wrinkleData: DetectData? = null
    private var rednessData: DetectData? = null
    private var spotsData: DetectData? = null
    private var acneData: DetectData? = null
    private var brownData: DetectData? = null
    private var purpleData: DetectData? = null
    private var poresData: DetectData? = null
    private var textureData: DetectData? = null

    // 基础信息
    private var nickname: String = ""
    private var testTime: String = ""
    private var facePhotoUrl: String = ""
    private var testTimeFetchInFlight = false
    private var testTimeFetchAttempted = false

    // 皱纹/痤疮接口是否已返回（用于控制卡片在接口返回前不隐藏）
    private var wrinkleFetched = false
    private var acneFetched = false

    // 全屏预览对话框
    private var previewDialog: android.app.Dialog? = null

    // ────── 蒙层相关 ──────
    // Views - 分析蒙层
    private lateinit var layoutAnalyzing: FrameLayout
    private lateinit var tvAnalyzingTitle: TextView
    private lateinit var tvAnalyzingSubtitle: TextView
    private lateinit var tvUploadProgress: TextView
    private lateinit var viewProgressFill: View
    private lateinit var viewProgressGlow: View
    private lateinit var layoutScanAnimation: FrameLayout
    private lateinit var viewRing1: View
    private lateinit var viewRing2: View
    private lateinit var viewRing3: View
    private lateinit var viewAnalyzingScanLine: View
    private lateinit var viewGlow1: View
    private lateinit var viewGlow2: View

    // 分析项
    private lateinit var analysisItems: List<LinearLayout>
    private lateinit var itemIcons: List<View>
    private lateinit var itemTexts: List<TextView>
    private lateinit var itemStatuses: List<TextView>

    // 粒子
    private lateinit var particles: List<View>

    // 动画
    private var ring1Animator: ObjectAnimator? = null
    private var ring2Animator: ObjectAnimator? = null
    private var ring3Animator: ObjectAnimator? = null
    private var scanLineAnimator: ObjectAnimator? = null
    private var glow1Animator: ObjectAnimator? = null
    private var glow2Animator: ObjectAnimator? = null
    private var particleAnimators: List<ObjectAnimator> = emptyList()

    // 进度条定时器
    private var progressTimer: CountDownTimer? = null
    private var itemTimer: CountDownTimer? = null
    private var currentProgress: Int = 0
    private var currentItem: Int = 0

    // 分析项数据
    private val analysisItemNames = listOf(
        "面部图像清晰度校准",
        "面部区域分割",
        "肌肤水分含量检测",
        "皮肤油脂分泌分析",
        "干纹、静态皱纹识别",
        "毛孔粗大程度测算",
        "黑色素、色斑检测",
        "泛红敏感区域识别"
    )

    @SuppressLint("SetJavaScriptEnabled")
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContentView(R.layout.activity_skin_report)

        // 获取传递的参数
        parseIntentParams()

        // 初始化视图
        initViews()

        // 初始化蒙层视图
        initAnalyzingViews()

        // 显示蒙层并启动分析动画（进度卡55%，列表卡在第4-5条）
        showAnalyzingMask()

        // 加载数据（根据 type 调用不同 API）
        loadData()
    }

    /**
     * 解析 Intent 参数
     */
    private fun parseIntentParams() {
        type = intent.getStringExtra("type") ?: "img"
        reportId = intent.getStringExtra("reportId")
        deviceId = intent.getStringExtra("deviceId")
        ossKey = intent.getStringExtra("oss_key")
        id = intent.getStringExtra("id")
        imagePath = intent.getStringExtra("imagePath")
            ?: intent.getStringExtra("image_path")  // 兼容 SmartSkinTestActivity 传参
        
        // 如果没有 ossKey 但有 imagePath，使用 imagePath 作为 ossKey
        if (ossKey.isNullOrEmpty() && !imagePath.isNullOrEmpty()) {
            ossKey = imagePath
        }
    }

    /**
     * 初始化视图
     */
    @SuppressLint("SetJavaScriptEnabled")
    private fun initViews() {
        // 返回按钮
        findViewById<View>(R.id.btnBack).setOnClickListener { finish() }

        // 折线图 WebView
        webViewChart = findViewById(R.id.webViewChart)
        webViewChart.settings.javaScriptEnabled = true
        webViewChart.settings.domStorageEnabled = true
        webViewChart.setLayerType(View.LAYER_TYPE_SOFTWARE, null)
        webViewChart.setBackgroundColor(0x00000000)
        webViewChart.webViewClient = object : WebViewClient() {
            override fun onPageFinished(view: WebView?, url: String?) {
                super.onPageFinished(view, url)
                chartReady = true
                // 设置图表数据
                pushChartDataToWeb()
            }
        }
        webViewChart.loadUrl("file:///android_asset/elasticity_chart.html")

        // 雷达图 WebView
        webViewRadar = findViewById(R.id.webViewRadar)
        webViewRadar.settings.javaScriptEnabled = true
        webViewRadar.settings.domStorageEnabled = true
        webViewRadar.setLayerType(View.LAYER_TYPE_SOFTWARE, null)
        webViewRadar.setBackgroundColor(0x00000000)
        webViewRadar.webViewClient = object : WebViewClient() {
            override fun onPageFinished(view: WebView?, url: String?) {
                super.onPageFinished(view, url)
                radarChartReady = true
                pushRadarData()
            }
        }
        webViewRadar.loadUrl("file:///android_asset/radar_chart.html")

        // 底部按钮：返回首页
        findViewById<View>(R.id.btnNext).setOnClickListener {
            goHome()
        }
    }

    /**
     * 将当前雷达数据推送到 WebView
     */
    private fun pushRadarData() {
        if (!radarChartReady) return
        val indicators = radarItems.joinToString(",", prefix = "[", postfix = "]") {
            """{ name: '${it.name}', max: 100 }"""
        }
        val data = radarItems.joinToString(",", prefix = "[", postfix = "]") { it.value.toString() }
        webViewRadar.evaluateJavascript("setRadarData($indicators, $data)", null)
    }

    private fun dpToPx(dp: Int): Int = (dp * resources.displayMetrics.density).toInt()

    // ────── 检测卡片（表格 + 图片）──────

    /** 表头列：固定宽度（dp） */
    private val tableHeaders = listOf(
        "分区", "相对分数", "条数", "像素长度", "平均线段",
        "最长线段", "密度/万px", "占比%", "面积px"
    )
    /** 红区检测专用表头：region/count/area/area_ratio */
    private val rednessTableHeaders = listOf(
        "分区", "特征数", "总像素数", "面积占比"
    )
    /** 色斑检测专用表头：region/count/area_ratio */
    private val spotsTableHeaders = listOf(
        "分区", "斑点数", "面积占比"
    )
    /** 棕区/毛孔/纹理检测专用表头：分区/个数 */
    private val brownPoresTextureTableHeaders = listOf(
        "分区", "个数"
    )
    private val tableColumnWidthDp = 72

    /**
     * 渲染检测表格到指定容器（自适应列宽）
     * - 表格总宽度 > 可用宽度：每列固定宽度（72dp），外层 HorizontalScrollView 可左右滚动
     * - 表格总宽度 <= 可用宽度：每列按权重均分可用宽度，充满整个屏幕
     */
    private fun renderDetectTable(container: LinearLayout, rows: List<DetectTableRow>, headers: List<String>? = null, onRowClick: ((DetectTableRow) -> Unit)? = null) {
        container.removeAllViews()
        val actualHeaders = headers ?: tableHeaders

        // 先按固定列宽渲染，等容器布局完成后测量可用宽度再决定是否切换为权重拉伸
        fun buildRows(columnWidthPx: Int?, useWeight: Boolean) {
            // 权重拉伸时容器本身宽度要占满 HorizontalScrollView（配合 fillViewport）
            container.layoutParams = container.layoutParams.apply {
                width = if (useWeight) LinearLayout.LayoutParams.MATCH_PARENT
                        else LinearLayout.LayoutParams.WRAP_CONTENT
            }
            container.removeAllViews()
            container.addView(createTableRow(actualHeaders, isHeader = true, columnWidthPx, useWeight))
            rows.forEach { row ->
                // 根据表头列数取前 N 个字段
                val allCells = listOf(
                    row.zone, row.score, row.count, row.pixelLength, row.avgLength,
                    row.maxLength, row.density, row.ratio, row.area
                )
                val rowView = createTableRow(
                    allCells.take(actualHeaders.size),
                    isHeader = false, columnWidthPx, useWeight
                )
                // 行点击：所有行都可点击，regionImageUrl 为空时提示"暂无该分区图片"
                if (onRowClick != null) {
                    rowView.isClickable = true
                    rowView.isFocusable = true
                    // 设置 selectableItemBackground 让点击有视觉反馈
                    val outValue = android.util.TypedValue()
                    container.context.theme.resolveAttribute(android.R.attr.selectableItemBackground, outValue, true)
                    rowView.setBackgroundResource(outValue.resourceId)
                    rowView.setOnClickListener {
                        Log.d(TAG, "表格行被点击: zone=${row.zone}, regionImageUrl=${row.regionImageUrl}")
                        onRowClick(row)
                    }
                }
                container.addView(rowView)
            }
        }

        // 初始按固定宽度渲染
        buildRows(dpToPx(tableColumnWidthDp), useWeight = false)

        // 布局完成后测量可用宽度，决定是否切换为权重拉伸
        container.post {
            // 可用宽度 = HorizontalScrollView 的宽度（表格父容器）
            val parentView = container.parent as? View ?: return@post
            val availableWidth = parentView.width
            if (availableWidth <= 0) return@post

            val fixedTotalWidth = dpToPx(tableColumnWidthDp) * actualHeaders.size
            if (fixedTotalWidth < availableWidth) {
                // 总宽度小于可用宽度 -> 按权重拉伸充满
                buildRows(null, useWeight = true)
            }
        }
    }

    /**
     * 创建表格行
     * @param columnWidthPx 固定列宽（px），useWeight=true 时忽略
     * @param useWeight true=按权重均分父宽度；false=使用固定列宽
     */
    private fun createTableRow(cells: List<String>, isHeader: Boolean, columnWidthPx: Int?, useWeight: Boolean): View {
        val row = LinearLayout(this).apply {
            orientation = LinearLayout.HORIZONTAL
            layoutParams = LinearLayout.LayoutParams(
                if (useWeight) LinearLayout.LayoutParams.MATCH_PARENT else LinearLayout.LayoutParams.WRAP_CONTENT,
                LinearLayout.LayoutParams.WRAP_CONTENT
            )
        }
        cells.forEach { cell ->
            val tv = TextView(this).apply {
                text = cell
                textSize = if (isHeader) 12f else 11f
                setTextColor(Color.parseColor(if (isHeader) "#111111" else "#333333"))
                if (isHeader) setTypeface(null, android.graphics.Typeface.BOLD)
                gravity = Gravity.CENTER
                layoutParams = if (useWeight) {
                    LinearLayout.LayoutParams(0, dpToPx(36), 1f)
                } else {
                    LinearLayout.LayoutParams(columnWidthPx ?: dpToPx(tableColumnWidthDp), dpToPx(36))
                }
                setPadding(dpToPx(4), 0, dpToPx(4), 0)
                if (isHeader) setBackgroundColor(Color.parseColor("#F0F4FF"))
            }
            row.addView(tv)
        }
        return row
    }

    /**
     * 更新某个检测卡片：表格 + 图片（无 loading）
     */
    private fun updateDetectCard(
        cardId: Int, tableId: Int, imageId: Int,
        data: DetectData?, title: String
    ) {
        updateDetectCard(cardId, tableId, imageId, -1, data, title)
    }

    /**
     * 更新某个检测卡片：表格 + 图片 + loading 控制
     * @param loadingId loading 容器 id，-1 表示无 loading
     * @param waitForApi 是否等待接口返回（true时即使data为null也不隐藏卡片，仅显示loading）
     * @param enableRowClick 是否启用表格行点击预览（仅皱纹卡片需要）
     */
    private fun updateDetectCard(
        cardId: Int, tableId: Int, imageId: Int, loadingId: Int,
        data: DetectData?, title: String, waitForApi: Boolean = false,
        enableRowClick: Boolean = false
    ) {
        val card = findViewById<View>(cardId)
        if (data == null || !data.detected) {
            if (waitForApi && loadingId != -1) {
                // 接口未返回前：卡片显示，loading显示
                card.visibility = View.VISIBLE
                findViewById<View>(loadingId).visibility = View.VISIBLE
            } else {
                card.visibility = View.GONE
            }
            return
        }
        card.visibility = View.VISIBLE

        // 隐藏 loading
        if (loadingId != -1) findViewById<View>(loadingId).visibility = View.GONE

        // 表格
        val tableContainer = findViewById<LinearLayout>(tableId)
        val rowClickHandler: ((DetectTableRow) -> Unit)? = if (enableRowClick) {
            { row ->
                // 点击表格行：预览该行的分区图片（region_image_url）
                if (row.regionImageUrl.isEmpty()) {
                    Toast.makeText(this, "暂无该分区图片", Toast.LENGTH_SHORT).show()
                } else {
                    val url = ensureFullUrl(row.regionImageUrl)
                    Log.d(TAG, "onRowClick: zone=${row.zone}, hasImage=${url.isNotBlank()}")
                    showImagePreview(url, "$title - ${row.zone}")
                }
            }
        } else null
        renderDetectTable(tableContainer, data.rows, data.headers, onRowClick = rowClickHandler)

        // 图片：宽度100%，高度按图片宽高比自适应
        val imageView = findViewById<ImageView>(imageId)
        if (data.imageUrl.isNotEmpty()) {
            loadImageFullWidth(imageView, data.imageUrl)
            imageView.setOnClickListener { showImagePreview(data.imageUrl, title) }
        }
    }

    /**
     * 显示检测卡片的 loading（卡片显示但图片区 loading）
     */
    private fun showDetectCardLoading(cardId: Int, loadingId: Int) {
        findViewById<View>(cardId).visibility = View.VISIBLE
        findViewById<View>(loadingId).visibility = View.VISIBLE
    }

    /**
     * 加载图片并让宽度占满容器、高度按图片原始宽高比自适应
     * 原理：先测量容器宽度 -> 图片加载成功后按宽高比算出目标高度 -> 设置给 ImageView
     */
    private fun loadImageFullWidth(imageView: ImageView, url: String) {
        imageView.scaleType = ImageView.ScaleType.FIT_CENTER
        imageView.adjustViewBounds = true
        imageView.load(url) {
            crossfade(true)
            error(R.drawable.ic_default_avatar)
            listener(
                onSuccess = { _, result ->
                    val drawable = result.drawable
                    val intrinsicW = drawable.intrinsicWidth
                    val intrinsicH = drawable.intrinsicHeight
                    if (intrinsicW <= 0 || intrinsicH <= 0) return@listener

                    fun applyHeight(containerWidth: Int) {
                        if (containerWidth <= 0) return
                        val targetH = (containerWidth.toFloat() * intrinsicH / intrinsicW).toInt()
                        if (targetH > 0 && imageView.layoutParams.height != targetH) {
                            imageView.layoutParams = imageView.layoutParams.apply { height = targetH }
                        }
                    }

                    val w = imageView.width
                    if (w > 0) {
                        applyHeight(w)
                    } else {
                        imageView.post { applyHeight(imageView.width) }
                    }
                }
            )
        }
    }

    /**
     * 更新所有检测卡片
     */
    private fun updateDetectCards() {
        updateDetectCard(R.id.cardWrinkle, R.id.tableWrinkle, R.id.ivWrinkle, R.id.loadingWrinkle, wrinkleData, "皱纹检测", waitForApi = !wrinkleFetched, enableRowClick = true)
        updateDetectCard(R.id.cardRedness, R.id.tableRedness, R.id.ivRedness, rednessData, "红区检测")
        updateDetectCard(R.id.cardSpots, R.id.tableSpots, R.id.ivSpots, spotsData, "色斑检测")
        updateDetectCard(R.id.cardBrown, R.id.tableBrown, R.id.ivBrown, brownData, "棕区检测")
        // 紫区数据最多显示前10条
        val purpleLimited = purpleData?.let {
            if (it.rows.size > 10) it.copy(rows = it.rows.take(10)) else it
        }
        updateDetectCard(R.id.cardPurple, R.id.tablePurple, R.id.ivPurple, purpleLimited, "紫区检测")
        updateDetectCard(R.id.cardPores, R.id.tablePores, R.id.ivPores, poresData, "毛孔检测")
        updateDetectCard(R.id.cardTexture, R.id.tableTexture, R.id.ivTexture, textureData, "纹理检测")
        updateDetectCard(R.id.cardAcne, R.id.tableAcne, R.id.ivAcne, R.id.loadingAcne, acneData, "痤疮检测", waitForApi = !acneFetched)
    }

    /**
     * 全屏预览图片（带右上角关闭按钮）
     */
    private fun showImagePreview(imageUrl: String, title: String) {
        if (isFinishing || isDestroyed) return

        Log.d(TAG, "showImagePreview")

        val dialog = android.app.Dialog(this, android.R.style.Theme_Black_NoTitleBar_Fullscreen)
        val density = resources.displayMetrics.density

        // 根容器：FrameLayout，图片铺满全屏，topBar 浮动在最顶部
        val root = FrameLayout(this).apply {
            layoutParams = FrameLayout.LayoutParams(
                FrameLayout.LayoutParams.MATCH_PARENT,
                FrameLayout.LayoutParams.MATCH_PARENT
            )
            setBackgroundColor(Color.BLACK)
        }

        // 预览图：占满全屏（FIT_CENTER 等比缩放，居中显示完整图片）
        val imageView = ImageView(this).apply {
            layoutParams = FrameLayout.LayoutParams(
                FrameLayout.LayoutParams.MATCH_PARENT,
                FrameLayout.LayoutParams.MATCH_PARENT
            )
            scaleType = ImageView.ScaleType.FIT_CENTER
            setBackgroundColor(Color.BLACK)
            setOnClickListener {
                dialog.dismiss()
            }
        }

        imageView.load(imageUrl) {
            crossfade(true)
            placeholder(android.R.drawable.ic_menu_gallery)
            error(android.R.drawable.ic_menu_report_image)
            listener(
                onError = { _, _ ->
                    Log.e(TAG, "图片加载失败")
                    runOnUiThread {
                        Toast.makeText(this@SkinReportActivity, "图片加载失败", Toast.LENGTH_SHORT).show()
                    }
                }
            )
        }

        root.addView(imageView)

        // 顶部栏：标题 + 关闭按钮（浮动在最顶部）
        val topBar = FrameLayout(this).apply {
            layoutParams = FrameLayout.LayoutParams(
                FrameLayout.LayoutParams.MATCH_PARENT,
                FrameLayout.LayoutParams.WRAP_CONTENT
            ).apply {
                gravity = Gravity.TOP
            }
            setBackgroundColor(Color.parseColor("#80000000"))
        }

        val titleTv = TextView(this).apply {
            text = title
            textSize = 18f
            setTextColor(Color.WHITE)
            val hPad = (20 * density).toInt()
            val vPad = (20 * density).toInt()
            setPadding(hPad, vPad, hPad, vPad)
            layoutParams = FrameLayout.LayoutParams(
                FrameLayout.LayoutParams.WRAP_CONTENT,
                FrameLayout.LayoutParams.WRAP_CONTENT
            ).apply {
                gravity = Gravity.TOP or Gravity.START
            }
        }
        topBar.addView(titleTv)

        val btnSize = (48 * density).toInt()
        val closeBtn = TextView(this).apply {
            text = "✕"
            textSize = 24f
            setTextColor(Color.WHITE)
            gravity = Gravity.CENTER
            layoutParams = FrameLayout.LayoutParams(btnSize, btnSize).apply {
                gravity = Gravity.TOP or Gravity.END
                val topM = (12 * density).toInt()
                val endM = (12 * density).toInt()
                setMargins(0, topM, endM, 0)
            }
            setOnClickListener {
                dialog.dismiss()
            }
        }
        topBar.addView(closeBtn)

        root.addView(topBar)

        dialog.setContentView(root)
        dialog.setCancelable(true)
        dialog.window?.apply {
            setLayout(
                android.view.WindowManager.LayoutParams.MATCH_PARENT,
                android.view.WindowManager.LayoutParams.MATCH_PARENT
            )
            setBackgroundDrawableResource(android.R.color.black)
        }

        previewDialog = dialog
        dialog.show()
    }

    private fun dismissPreview() {
        try {
            previewDialog?.dismiss()
        } catch (_: Exception) {}
        previewDialog = null
    }

    // ────── 蒙层初始化 ──────

    /**
     * 初始化蒙层相关视图
     */
    private fun initAnalyzingViews() {
        // 分析蒙层
        layoutAnalyzing = findViewById(R.id.layout_analyzing)
        tvAnalyzingTitle = findViewById(R.id.tv_analyzing_title)
        tvAnalyzingSubtitle = findViewById(R.id.tv_analyzing_subtitle)
        tvUploadProgress = findViewById(R.id.tv_upload_progress)
        viewProgressFill = findViewById(R.id.view_progress_fill)
        viewProgressGlow = findViewById(R.id.view_progress_glow)
        layoutScanAnimation = findViewById(R.id.layout_scan_animation)
        viewRing1 = findViewById(R.id.view_ring1)
        viewRing2 = findViewById(R.id.view_ring2)
        viewRing3 = findViewById(R.id.view_ring3)
        viewAnalyzingScanLine = findViewById(R.id.view_analyzing_scan_line)
        viewGlow1 = findViewById(R.id.view_glow1)
        viewGlow2 = findViewById(R.id.view_glow2)

        // 分析项
        analysisItems = listOf(
            findViewById(R.id.item_analysis_1),
            findViewById(R.id.item_analysis_2),
            findViewById(R.id.item_analysis_3),
            findViewById(R.id.item_analysis_4),
            findViewById(R.id.item_analysis_5),
            findViewById(R.id.item_analysis_6),
            findViewById(R.id.item_analysis_7),
            findViewById(R.id.item_analysis_8)
        )
        itemIcons = listOf(
            findViewById(R.id.item_icon_1),
            findViewById(R.id.item_icon_2),
            findViewById(R.id.item_icon_3),
            findViewById(R.id.item_icon_4),
            findViewById(R.id.item_icon_5),
            findViewById(R.id.item_icon_6),
            findViewById(R.id.item_icon_7),
            findViewById(R.id.item_icon_8)
        )
        itemTexts = listOf(
            findViewById(R.id.item_text_1),
            findViewById(R.id.item_text_2),
            findViewById(R.id.item_text_3),
            findViewById(R.id.item_text_4),
            findViewById(R.id.item_text_5),
            findViewById(R.id.item_text_6),
            findViewById(R.id.item_text_7),
            findViewById(R.id.item_text_8)
        )
        itemStatuses = listOf(
            findViewById(R.id.item_status_1),
            findViewById(R.id.item_status_2),
            findViewById(R.id.item_status_3),
            findViewById(R.id.item_status_4),
            findViewById(R.id.item_status_5),
            findViewById(R.id.item_status_6),
            findViewById(R.id.item_status_7),
            findViewById(R.id.item_status_8)
        )

        // 粒子
        particles = listOf(
            findViewById(R.id.particle1),
            findViewById(R.id.particle2),
            findViewById(R.id.particle3),
            findViewById(R.id.particle4),
            findViewById(R.id.particle5),
            findViewById(R.id.particle6)
        )
    }

    /**
     * 显示蒙层并启动分析动画
     * 进度条卡住到55%，分析列表卡在第4条和第5条之间
     */
    private fun showAnalyzingMask() {
        layoutAnalyzing.visibility = View.VISIBLE

        tvAnalyzingTitle.text = "正在深度分析你的肌肤"
        tvAnalyzingSubtitle.text = "请勿退出页面"
        tvUploadProgress.text = "分析 0%"
        viewProgressFill.layoutParams.width = 0
        viewProgressGlow.visibility = View.GONE
        currentProgress = 0
        currentItem = 0

        // 重置分析项状态
        for (i in analysisItems.indices) {
            itemIcons[i].setBackgroundResource(R.drawable.analysis_item_inactive)
            itemTexts[i].setTextColor(ContextCompat.getColor(this, R.color.white_60))
            itemStatuses[i].text = ""
        }

        // 启动扫描动画（旋转光圈 + 扫描线 + 光斑 + 粒子）
        startAnalyzingAnimations()

        // 启动进度条动画（从0%到55%，每100ms更新一次，总时长约4秒）
        startProgressHold()

        // 启动分析项动画（逐项激活，卡在第4条完成、第5条激活的状态）
        startAnalysisItemsAnimation()
    }

    /**
     * 启动进度条动画：从0%到55%后卡住
     */
    private fun startProgressHold() {
        progressTimer?.cancel()
        val holdProgress = 55
        val duration = 4000L  // 4秒内从0到55%

        progressTimer = object : CountDownTimer(duration, 100) {
            override fun onTick(millisUntilFinished: Long) {
                val elapsed = duration - millisUntilFinished
                val progress = (holdProgress * elapsed / duration).toInt()
                currentProgress = progress
                updateProgressView(progress)
            }
            override fun onFinish() {
                currentProgress = holdProgress
                updateProgressView(holdProgress)
                // 卡在55%，等待接口返回
            }
        }
        progressTimer?.start()
    }

    /**
     * 启动分析项动画：逐项激活，卡在第4条完成、第5条激活
     */
    private fun startAnalysisItemsAnimation() {
        tvAnalyzingSubtitle.text = "正在进行智能深度分析..."
        currentItem = 0
        val holdItemCount = 4  // 只激活前4条

        itemTimer?.cancel()
        itemTimer = object : CountDownTimer(4000L, 1000L) {
            override fun onTick(millisUntilFinished: Long) {
                if (currentItem < holdItemCount && currentItem < analysisItems.size) {
                    // 激活当前项
                    itemIcons[currentItem].setBackgroundResource(R.drawable.analysis_item_active)
                    itemTexts[currentItem].setTextColor(ContextCompat.getColor(this@SkinReportActivity, R.color.white))
                    itemStatuses[currentItem].text = "分析中..."

                    // 完成前一项
                    if (currentItem > 0) {
                        itemIcons[currentItem - 1].setBackgroundResource(R.drawable.analysis_item_done)
                        itemStatuses[currentItem - 1].text = "完成"
                        itemStatuses[currentItem - 1].setTextColor(ContextCompat.getColor(this@SkinReportActivity, R.color.cyan_light))
                    }
                    currentItem++
                }
            }

            override fun onFinish() {
                // 完成第4项，让第4项显示"完成"，第5项显示"分析中..."
                if (currentItem > 0 && currentItem <= analysisItems.size) {
                    itemIcons[currentItem - 1].setBackgroundResource(R.drawable.analysis_item_done)
                    itemStatuses[currentItem - 1].text = "完成"
                    itemStatuses[currentItem - 1].setTextColor(ContextCompat.getColor(this@SkinReportActivity, R.color.cyan_light))
                }
                // 激活第5项（index=4），卡在这里等待接口返回
                if (currentItem < analysisItems.size) {
                    itemIcons[currentItem].setBackgroundResource(R.drawable.analysis_item_active)
                    itemTexts[currentItem].setTextColor(ContextCompat.getColor(this@SkinReportActivity, R.color.white))
                    itemStatuses[currentItem].text = "分析中..."
                    currentItem++
                }
            }
        }
        itemTimer?.start()
    }

    /**
     * 接口返回数据后，在600ms内加载到100%并关闭蒙层
     */
    private fun finishAnalyzingAndDismiss() {
        // 停止当前进度和分析项定时器
        progressTimer?.cancel()
        itemTimer?.cancel()

        // 继续分析项动画：从当前项到结束（在300ms内快速完成剩余项）
        finishRemainingItems()

        // 从当前进度到100%，在600ms内完成
        val startProgress = currentProgress
        val remaining = 100 - startProgress
        val finishDuration = 600L

        progressTimer = object : CountDownTimer(finishDuration, 30) {
            override fun onTick(millisUntilFinished: Long) {
                val elapsed = finishDuration - millisUntilFinished
                val progress = startProgress + (remaining * elapsed / finishDuration).toInt()
                currentProgress = progress
                updateProgressView(progress)
            }
            override fun onFinish() {
                updateProgressView(100)
                currentProgress = 100

                // 延迟一小段时间后关闭蒙层
                layoutAnalyzing.postDelayed({
                    dismissAnalyzingMask()
                }, 200)
            }
        }
        progressTimer?.start()
    }

    /**
     * 快速完成剩余的分析项
     */
    private fun finishRemainingItems() {
        // 从currentItem开始快速完成剩余项
        for (i in currentItem until analysisItems.size) {
            itemIcons[i].setBackgroundResource(R.drawable.analysis_item_done)
            itemTexts[i].setTextColor(ContextCompat.getColor(this, R.color.white))
            itemStatuses[i].text = "完成"
            itemStatuses[i].setTextColor(ContextCompat.getColor(this, R.color.cyan_light))
        }
    }

    /**
     * 关闭蒙层（停止所有动画）
     */
    private fun dismissAnalyzingMask() {
        stopAnalyzingAnimations()
        progressTimer?.cancel()
        progressTimer = null
        itemTimer?.cancel()
        itemTimer = null
        layoutAnalyzing.visibility = View.GONE
    }

    /**
     * 更新进度条视图
     */
    private fun updateProgressView(progress: Int) {
        tvUploadProgress.text = "分析 ${progress}%"
        val parentWidth = (viewProgressFill.parent as View).width
        if (parentWidth > 0) {
            val targetWidth = parentWidth * progress / 100
            viewProgressFill.layoutParams.width = targetWidth
            viewProgressFill.requestLayout()

            if (progress > 0) {
                viewProgressGlow.visibility = View.VISIBLE
                viewProgressGlow.translationX = targetWidth.toFloat() - viewProgressGlow.width / 2
            }
        }
    }

    /**
     * 启动完整的分析动画（旋转光圈 + 扫描线 + 光斑 + 粒子）
     */
    private fun startAnalyzingAnimations() {
        ring1Animator = ObjectAnimator.ofFloat(viewRing1, "rotation", 0f, 360f).apply {
            duration = 3000; repeatCount = ValueAnimator.INFINITE; interpolator = LinearInterpolator(); start()
        }
        ring2Animator = ObjectAnimator.ofFloat(viewRing2, "rotation", 360f, 0f).apply {
            duration = 2500; repeatCount = ValueAnimator.INFINITE; interpolator = LinearInterpolator(); start()
        }
        ring3Animator = ObjectAnimator.ofFloat(viewRing3, "rotation", 0f, 360f).apply {
            duration = 2000; repeatCount = ValueAnimator.INFINITE; interpolator = LinearInterpolator(); start()
        }
        layoutScanAnimation.post {
            val scanHeight = 130f
            scanLineAnimator = ObjectAnimator.ofFloat(viewAnalyzingScanLine, "translationY", 0f, scanHeight).apply {
                duration = 1500; repeatCount = ValueAnimator.INFINITE; repeatMode = ValueAnimator.REVERSE; interpolator = LinearInterpolator(); start()
            }
        }
        glow1Animator = ObjectAnimator.ofFloat(viewGlow1, "alpha", 0.2f, 0.5f, 0.2f).apply {
            duration = 3000; repeatCount = ValueAnimator.INFINITE; start()
        }
        glow2Animator = ObjectAnimator.ofFloat(viewGlow2, "alpha", 0.1f, 0.4f, 0.1f).apply {
            duration = 2500; repeatCount = ValueAnimator.INFINITE; start()
        }
        particleAnimators = particles.mapIndexed { index, particle ->
            val duration = 2000L + (index * 300L)
            ObjectAnimator.ofFloat(particle, "translationY", -10f, 10f, -10f).apply {
                this.duration = duration; repeatCount = ValueAnimator.INFINITE; interpolator = AccelerateDecelerateInterpolator(); start()
            }
        }
    }

    /**
     * 停止所有分析动画
     */
    private fun stopAnalyzingAnimations() {
        ring1Animator?.cancel(); ring1Animator = null
        ring2Animator?.cancel(); ring2Animator = null
        ring3Animator?.cancel(); ring3Animator = null
        scanLineAnimator?.cancel(); scanLineAnimator = null
        glow1Animator?.cancel(); glow1Animator = null
        glow2Animator?.cancel(); glow2Animator = null
        particleAnimators.forEach { it.cancel() }
        particleAnimators = emptyList()
    }

    /**
     * 将当前图表数据推送到 WebView
     */
    private fun pushChartDataToWeb() {
        if (!chartReady) return
        val chartData = buildChartData()
        webViewChart.evaluateJavascript("setChartData($chartData)", null)
    }

    /**
     * 构建图表数据 JSON
     */
    private fun buildChartData(): String {
        val xArr = chartXData.joinToString(",")
        val yArr = chartYData.joinToString(",")
        val skinAgeVal = skinAge ?: "null"
        val skinAgeScoreVal = skinAgeScore ?: "null"
        return """
            {
                "xData": [$xArr],
                "yData": [$yArr],
                "referenceScore": $referenceScore,
                "skinAge": $skinAgeVal,
                "skinAgeScore": $skinAgeScoreVal
            }
        """.trimIndent()
    }

    /**
     * 加载数据
     * 根据 type 决定调用不同的 API
     */
    private fun loadData() {
        Log.d(TAG, "loadData: type=$type")
        
        if (type == "list") {
            // 从列表进入，使用 id 和 reportId 获取详情
            if (!id.isNullOrEmpty() && !reportId.isNullOrEmpty()) {
                getFaceDetails(id!!, reportId!!)
            } else if (!reportId.isNullOrEmpty()) {
                // 兼容只有 reportId 的情况（从 ReportListActivity 跳转）
                Log.w(TAG, "只有 reportId，缺少 id，尝试使用 reportId 作为 faceId")
                getFaceDetails(reportId!!, reportId!!)
            } else {
                Log.w(TAG, "loadData: 缺少必要参数，无法调用接口")
                // 接口无法调用，直接关闭蒙层
                dismissAnalyzingMask()
            }
        } else {
            // 从图片分析进入，使用 oss_key 获取详情
            if (!ossKey.isNullOrEmpty()) {
                getDetails(ossKey!!)
            } else {
                Log.w(TAG, "loadData: 缺少 ossKey，无法调用接口")
                // 接口无法调用，直接关闭蒙层
                dismissAnalyzingMask()
            }
        }
    }

    /**
     * 显示 loading 对话框（全屏蒙层）- 保留用于其他地方
     */
    private fun showLoading() {
        if (isFinishing || isDestroyed) return
        if (loadingDialog != null && loadingDialog!!.isShowing) return
        
        // 创建全屏蒙层容器
        val container = FrameLayout(this).apply {
            setBackgroundColor(android.graphics.Color.parseColor("#80000000")) // 半透明黑色背景
        }
        
        // 创建居中的内容容器
        val contentContainer = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            gravity = Gravity.CENTER
        }
        
        val progressBar = ProgressBar(this).apply {
            isIndeterminate = true
        }
        contentContainer.addView(progressBar)
        
        val textView = TextView(this).apply {
            text = "加载中..."
            textSize = 16f
            setTextColor(android.graphics.Color.WHITE)
        }
        val textParams = LinearLayout.LayoutParams(
            LinearLayout.LayoutParams.WRAP_CONTENT,
            LinearLayout.LayoutParams.WRAP_CONTENT
        ).apply {
            topMargin = 24
            gravity = Gravity.CENTER_HORIZONTAL
        }
        contentContainer.addView(textView, textParams)
        
        val contentParams = FrameLayout.LayoutParams(
            FrameLayout.LayoutParams.WRAP_CONTENT,
            FrameLayout.LayoutParams.WRAP_CONTENT
        ).apply {
            gravity = Gravity.CENTER
        }
        container.addView(contentContainer, contentParams)
        
        loadingDialog = AlertDialog.Builder(this, android.R.style.Theme_Black_NoTitleBar_Fullscreen)
            .setView(container)
            .setCancelable(false)
            .create()
        
        // 先 show，再设置 window 属性确保全屏
        loadingDialog?.show()
        loadingDialog?.window?.apply {
            setBackgroundDrawableResource(android.R.color.transparent)
            setLayout(
                android.view.WindowManager.LayoutParams.MATCH_PARENT,
                android.view.WindowManager.LayoutParams.MATCH_PARENT
            )
            setGravity(Gravity.CENTER)
        }
    }

    /**
     * 隐藏 loading 对话框
     */
    private fun hideLoading() {
        try {
            loadingDialog?.dismiss()
        } catch (e: Exception) {
            // ignore
        }
        loadingDialog = null
    }

    /**
     * 获取面部分析详情（通过 oss_key）
     * POST /api/self-research-face/analysis
     * body: { "oss_key": "xxx" }
     */
    private fun getDetails(ossKey: String) {
        Log.d(TAG, "getDetails: loading report details")
        HttpHelper.post(
            path = "/api/self-research-face/analysis",
            params = mapOf("oss_key" to ossKey),
            onSuccess = { responseBody ->
                runOnUiThread {
                    try {
                        val json = JSONObject(responseBody)
                        val apiError = firstNonEmpty(json, "error_message", "error", "detail", "message")
                        if (isNoFaceError(apiError)) {
                            dismissAnalyzingMask()
                            showNoFaceDialog()
                            return@runOnUiThread
                        }
                        handleApiResponse(json)
                        // 接口成功：600ms内加载到100%并关闭蒙层
                        finishAnalyzingAndDismiss()
                    } catch (e: Exception) {
                        Log.e(TAG, "解析响应失败", e)
                        Toast.makeText(this, "数据解析失败", Toast.LENGTH_SHORT).show()
                        // 接口报错：关闭蒙层
                        dismissAnalyzingMask()
                    }
                }
            },
            onFailure = { code, errorMsg ->
                runOnUiThread {
                    Log.e(TAG, "getDetails 失败: code=$code, msg=$errorMsg")
                    if (isNoFaceError(errorMsg)) {
                        dismissAnalyzingMask()
                        showNoFaceDialog()
                        return@runOnUiThread
                    }
                    val toastMsg = if (code >= 500) {
                        "服务器错误($code)，请稍后重试"
                    } else if (code == 404) {
                        "报告不存在"
                    } else {
                        "获取报告失败($code): $errorMsg"
                    }
                    Toast.makeText(this, toastMsg, Toast.LENGTH_SHORT).show()
                    // 接口报错：关闭蒙层
                    dismissAnalyzingMask()
                }
            },
            timeoutSeconds = API_TIMEOUT_SECONDS
        )
    }

    private fun isNoFaceError(rawMessage: String): Boolean {
        if (rawMessage.isBlank()) return false
        val message = try {
            val json = JSONObject(rawMessage)
            json.optString("detail", "")
                .ifBlank { json.optString("message", "") }
                .ifBlank { json.optString("error", "") }
                .ifBlank { json.optString("code", "") }
                .ifBlank { rawMessage }
        } catch (_: Exception) {
            rawMessage
        }.lowercase(Locale.ROOT)

        return listOf(
            "no face",
            "no_face",
            "face_not_detected",
            "face not detected",
            "未检测到人脸",
            "没有检测到人脸",
            "未识别到人脸",
            "未发现人脸",
            "找不到人脸",
            "无人脸",
            "人脸检测失败"
        ).any(message::contains)
    }

    private fun showNoFaceDialog() {
        if (isFinishing || isDestroyed || noFaceDialog?.isShowing == true) return
        noFaceDialog = AlertDialog.Builder(this)
            .setTitle("未检测到人脸")
            .setMessage("照片中未检测到人脸，请重新拍摄清晰、完整的正脸")
            .setPositiveButton("重新拍照") { _, _ ->
                startActivity(
                    Intent(this, SmartSkinTestActivity::class.java)
                        .putExtra("type", "skin")
                )
                finish()
            }
            .setNegativeButton("返回") { _, _ -> finish() }
            .setCancelable(false)
            .create()
            .also { dialog ->
                dialog.setOnDismissListener { noFaceDialog = null }
                dialog.show()
            }
    }

    /**
     * 获取面部详情（通过 face_id 和 report_id）
     * GET /api/self-research-face/faces/{face_id}/reports/{report_id}
     */
    private fun getFaceDetails(faceId: String, reportId: String) {
        val path = "/api/self-research-face/faces/$faceId/reports/$reportId"
        Log.d(TAG, "getFaceDetails path=$path")
        HttpHelper.get(
            path = path,
            onSuccess = { responseBody ->
                runOnUiThread {
                    try {
                        val json = JSONObject(responseBody)
                        handleApiResponse(json)
                        // 接口成功：600ms内加载到100%并关闭蒙层
                        finishAnalyzingAndDismiss()
                    } catch (e: Exception) {
                        Log.e(TAG, "解析响应失败", e)
                        Toast.makeText(this, "数据解析失败", Toast.LENGTH_SHORT).show()
                        // 接口报错：关闭蒙层
                        dismissAnalyzingMask()
                    }
                }
            },
            onFailure = { code, errorMsg ->
                runOnUiThread {
                    Log.e(TAG, "getFaceDetails 失败: code=$code, msg=$errorMsg")
                    val toastMsg = if (code >= 500) {
                        "服务器错误($code)，请稍后重试"
                    } else if (code == 404) {
                        "报告不存在"
                    } else {
                        "获取报告失败($code): $errorMsg"
                    }
                    Toast.makeText(this, toastMsg, Toast.LENGTH_SHORT).show()
                    // 接口报错：关闭蒙层
                    dismissAnalyzingMask()
                }
            },
            timeoutSeconds = API_TIMEOUT_SECONDS
        )
    }

    /**
     * 统一处理两个接口的返回数据（格式相同）
     * 只用 summary 部分：
     *   - skin_type -> 肤质文本
     *   - skin_score -> 总得分
     *   - moisture_level -> 水分档位 1/2/3 -> 显示对应数量水滴
     *   - elasticity.score -> 弹性得分
     *   - elasticity.reference_curve.x / .y -> 折线图 x,y 轴数据
     *   - elasticity.skin_age -> 折线图最后一个点用蓝色字标出年龄
     *   - suggestions -> 改善建议文本
     * 以及根级字段：
     *   - face_id -> 用于跳转 ReportDetailActivity
     *   - report_id -> 用于跳转 ReportDetailActivity
     */
    private fun handleApiResponse(json: JSONObject) {
        Log.d(TAG, "handleApiResponse: parsing report")

        // 提取根级字段 face_id 和 report_id
        if (json.has("face_id")) {
            apiFaceId = json.optString("face_id")
            Log.d(TAG, "apiFaceId=$apiFaceId")
        }
        if (json.has("report_id")) {
            apiReportId = json.optString("report_id")
            Log.d(TAG, "apiReportId=$apiReportId")
        }

        // overall_score -> 右侧得分
        if (json.has("overall_score")) {
            overallScore = json.optInt("overall_score", overallScore)
        }

        // radar -> 雷达图 & 进度条
        val radarArr: JSONArray? = json.optJSONArray("radar")
        if (radarArr != null && radarArr.length() > 0) {
            val list = mutableListOf<RadarItem>()
            for (i in 0 until radarArr.length()) {
                val obj = radarArr.optJSONObject(i) ?: continue
                list.add(RadarItem(
                    name = obj.optString("name", ""),
                    value = obj.optInt("value", 0)
                ))
            }
            if (list.isNotEmpty()) radarItems = list
        }

        // 基础信息：昵称 / 测肤时间 / 原照片（多种字段名兜底）
        nickname = firstNonEmpty(json, "nickname", "face_nickname", "name", "user_nickname")
        val responseTestTime = formatTestTime(
            firstNonEmpty(json, "created_at", "create_time", "test_time", "timestamp", "date")
        )
        if (responseTestTime.isNotEmpty()) testTime = responseTestTime
        facePhotoUrl = firstNonEmpty(json, "image_url", "face_image_url", "photo_url", "oss_url", "img_url")

        // 新建分析接口不返回 created_at；使用其返回的 face_id/report_id 补查详情中的服务端时间。
        if (type != "list" && testTime.isEmpty()) fetchReportTestTimeIfNeeded()

        // raw_result -> 皮肤检测详情（红区/色斑）
        parseRawResult(json)

        // 触发 皱纹/痤疮 单独接口获取
        fetchWrinkleAndAcne()

        val summary = json.optJSONObject("summary") ?: run {
            updateViews()
            return
        }

        // skin_type -> 肤质
        skinType = summary.optString("skin_type", skinType)

        // skin_score 与测肤列表的评分字段一致；缺失时保留 null，展示层回退 overall_score。
        if (summary.has("skin_score") && !summary.isNull("skin_score")) {
            skinScore = summary.optInt("skin_score")
        }

        // moisture_level -> 水分档位（支持字符串和整数格式）
        val moistureStr = summary.optString("moisture_level", "")
        moistureLevel = moistureStr.toIntOrNull() ?: summary.optInt("moisture_level", moistureLevel)

        // suggestions -> 改善建议
        val sug = summary.optString("suggestions", "")
        if (sug.isNotEmpty()) {
            suggestion = sug
        }

        // elasticity
        val elasticity = summary.optJSONObject("elasticity")
        if (elasticity != null) {
            // score -> 弹性得分
            elasticityScore = elasticity.optInt("score", elasticityScore)

            // skin_age -> 折线图特殊标记点的X值（年龄）
            // score -> skin_age对应的Y值（得分）
            if (elasticity.has("skin_age")) {
                skinAge = elasticity.optInt("skin_age")
                skinAgeScore = elasticityScore  // score作为skin_age点的Y值
            }

            // reference_curve -> x, y 轴数据
            val refCurve = elasticity.optJSONObject("reference_curve")
            if (refCurve != null) {
                val xArr = refCurve.optJSONArray("x")
                val yArr = refCurve.optJSONArray("y")
                if (xArr != null && xArr.length() > 0) {
                    chartXData = (0 until xArr.length()).map { xArr.optDouble(it) }
                    // 如果有 skinAge，将其追加到 x 轴最后
                    if (skinAge != null) {
                        chartXData = chartXData + skinAge!!
                    }
                }
                if (yArr != null && yArr.length() > 0) {
                    chartYData = (0 until yArr.length()).map { yArr.optDouble(it) }
                }
            }
        }

        // 更新所有 UI
        updateViews()
    }

    /** 从 json 中按多个候选 key 取第一个非空字符串 */
    private fun firstNonEmpty(json: JSONObject, vararg keys: String): String {
        for (key in keys) {
            val v = json.optString(key, "")
            if (v.isNotEmpty() && v != "null") return v
        }
        return ""
    }

    /**
     * 格式化测肤时间
     * 接口返回的 created_at 是时间戳（秒或毫秒），转为 yyyy/MM/dd HH:mm:ss
     * 非纯数字（已是格式化字符串）则原样返回
     */
    private fun formatTestTime(raw: String): String {
        if (raw.isEmpty()) return ""
        val ts = raw.toLongOrNull() ?: return raw  // 已是格式化字符串
        // 秒级时间戳（10位）转毫秒；毫秒级（13位）直接用
        val millis = if (ts < 100_000_000_000L) ts * 1000 else ts
        return try {
            SimpleDateFormat("yyyy/MM/dd HH:mm:ss", Locale.getDefault()).format(Date(millis))
        } catch (e: Exception) {
            raw
        }
    }

    /**
     * 新建分析响应没有 created_at，补查报告详情以获取服务端记录的真实测肤时间。
     */
    private fun fetchReportTestTimeIfNeeded() {
        if (testTimeFetchInFlight || testTimeFetchAttempted || testTime.isNotEmpty()) return
        val faceId = apiFaceId?.takeIf { it.isNotBlank() && it != "null" } ?: return
        val reportId = apiReportId?.takeIf { it.isNotBlank() && it != "null" } ?: return

        testTimeFetchAttempted = true
        testTimeFetchInFlight = true
        HttpHelper.get(
            path = "/api/self-research-face/faces/$faceId/reports/$reportId",
            onSuccess = { responseBody ->
                val fetchedTime = try {
                    val detail = JSONObject(responseBody)
                    formatTestTime(
                        firstNonEmpty(
                            detail,
                            "created_at",
                            "create_time",
                            "test_time",
                            "timestamp",
                            "date"
                        )
                    )
                } catch (e: Exception) {
                    Log.e(TAG, "补查测肤时间解析失败", e)
                    ""
                }
                runOnUiThread {
                    testTimeFetchInFlight = false
                    if (isFinishing || isDestroyed || fetchedTime.isEmpty()) return@runOnUiThread
                    testTime = fetchedTime
                    findViewById<TextView>(R.id.tvTestTime).text = "测肤时间：$testTime"
                }
            },
            onFailure = { code, errorMsg ->
                Log.w(TAG, "补查测肤时间失败: code=$code, msg=$errorMsg")
                runOnUiThread { testTimeFetchInFlight = false }
            },
            timeoutSeconds = API_TIMEOUT_SECONDS
        )
    }

    /**
     * 解析单个检测项（皱纹/红区/色斑/痤疮）为 DetectData
     * 兼容多种字段结构：
     * - zones/areas/regions/list 数组 -> 每行表格数据
     * - 字段名兜底：zone/name/area_name, score/relative_score, count/num,
     *   pixel_length/total_length, avg_length/average_length, max_length/longest,
     *   density, ratio/percentage/proportion, area/area_px
     */
    private fun parseDetectItem(obj: JSONObject?, imageUrlKeys: Array<String>): DetectData? {
        if (obj == null) return null
        val detected = obj.optBoolean("detected", false)
        if (!detected) return DetectData(false, "", emptyList())

        // 图片 URL
        var imageUrl = ""
        for (key in imageUrlKeys) {
            val v = obj.optString(key, "")
            if (v.isNotEmpty() && v != "null") { imageUrl = v; break }
        }

        // 表格数据：尝试多个数组字段
        val rows = mutableListOf<DetectTableRow>()
        val arrKeys = arrayOf("zones", "areas", "regions", "list", "details", "items", "data")
        var arr: JSONArray? = null
        for (key in arrKeys) {
            val a = obj.optJSONArray(key)
            if (a != null && a.length() > 0) { arr = a; break }
        }

        if (arr != null) {
            for (i in 0 until arr.length()) {
                val item = arr.optJSONObject(i) ?: continue
                rows.add(DetectTableRow(
                    zone = pickStr(item, "zone", "name", "area_name", "region", "part"),
                    score = pickStr(item, "score", "relative_score", "relativeScore"),
                    count = pickStr(item, "count", "num", "number", "lines"),
                    pixelLength = pickStr(item, "pixel_length", "pixelLength", "total_length", "length"),
                    avgLength = pickStr(item, "avg_length", "avgLength", "average_length", "mean_length"),
                    maxLength = pickStr(item, "max_length", "maxLength", "longest", "longest_length"),
                    density = pickStr(item, "density", "density_per_10k", "density_10k"),
                    ratio = pickStr(item, "ratio", "percentage", "proportion", "percent"),
                    area = pickStr(item, "area", "area_px", "areaPx", "pixel_area")
                ))
            }
        } else {
            // 无分区数组时，用对象自身字段生成一行
            val singleRow = DetectTableRow(
                zone = pickStr(obj, "zone", "name", "area_name", "region", "part").ifEmpty { "全脸" },
                score = pickStr(obj, "score", "relative_score", "relativeScore"),
                count = pickStr(obj, "count", "num", "number", "lines"),
                pixelLength = pickStr(obj, "pixel_length", "pixelLength", "total_length", "length"),
                avgLength = pickStr(obj, "avg_length", "avgLength", "average_length", "mean_length"),
                maxLength = pickStr(obj, "max_length", "maxLength", "longest", "longest_length"),
                density = pickStr(obj, "density", "density_per_10k", "density_10k"),
                ratio = pickStr(obj, "ratio", "percentage", "proportion", "percent"),
                area = pickStr(obj, "area", "area_px", "areaPx", "pixel_area")
            )
            // 如果所有字段都为空就不加
            if (listOf(singleRow.score, singleRow.count, singleRow.pixelLength,
                    singleRow.avgLength, singleRow.maxLength, singleRow.density,
                    singleRow.ratio, singleRow.area).any { it.isNotEmpty() }) {
                rows.add(singleRow)
            }
        }

        return DetectData(true, imageUrl, rows)
    }

    /**
     * 灵活获取 JSONObject：字段可能是 JSONObject，也可能是 JSON 字符串
     */
    private fun optJSONObjectFlexible(json: JSONObject, key: String): JSONObject? {
        val direct = json.optJSONObject(key)
        if (direct != null) return direct
        val str = json.optString(key, "")
        if (str.isNotEmpty() && str != "null" && str.startsWith("{")) {
            return try { JSONObject(str) } catch (e: Exception) { null }
        }
        return null
    }

    /**
     * 灵活获取布尔值：兼容 true / "true" / 1 / "1"
     */
    private fun optBooleanFlexible(json: JSONObject, key: String): Boolean {
        val v = json.opt(key) ?: return false
        return when (v) {
            is Boolean -> v
            is Number -> v.toInt() != 0
            is String -> v.equals("true", ignoreCase = true) || v == "1"
            else -> false
        }
    }

    /** 从 json 中按多个候选 key 取第一个非空字符串（支持数字转字符串） */
    private fun pickStr(json: JSONObject, vararg keys: String): String {
        for (key in keys) {
            if (!json.has(key)) continue
            val v = json.opt(key) ?: continue
            val s = v.toString()
            if (s.isNotEmpty() && s != "null") return s
        }
        return ""
    }

    /**
     * 解析 raw_result 中的检测数据（表格 + 图片）
     */
    private fun parseRawResult(json: JSONObject) {
        // 接口返回结构：res.raw_result.spots / res.raw_result.redness
        // 先解出 res 包装层（也可能是直接顶层），再找 raw_result（兼容字符串嵌套）
        val rawResult: JSONObject? = try {
            optJSONObjectFlexible(json, "raw_result")
                ?: json.optJSONObject("res")?.let { optJSONObjectFlexible(it, "raw_result") }
                ?: json.optJSONObject("data")?.let { optJSONObjectFlexible(it, "raw_result") }
        } catch (e: Exception) {
            Log.e(TAG, "parseRawResult: 解析 raw_result 失败", e)
            null
        }

        if (rawResult == null) {
            Log.w(TAG, "parseRawResult: rawResult is null, topKeys=${json.keys().asSequence().toList()}")
            return
        }
        Log.d(TAG, "parseRawResult: rawResult keys=${rawResult.keys().asSequence().toList()}")

        // 红区：redness.redness_metrics.red_feature_region_distribution
        rednessData = parseRednessResponse(optJSONObjectFlexible(rawResult, "redness"))

        // 色斑：spots.spots_metrics.region_distribution
        spotsData = parseSpotsResponse(optJSONObjectFlexible(rawResult, "spots"))

        // 棕区：brown.brown_metrics（name/value）
        brownData = parseBrownPoresTextureResponse(optJSONObjectFlexible(rawResult, "brown"), "brown_metrics")

        // 紫区：purple.purple_metrics（name/value）
        purpleData = parseBrownPoresTextureResponse(optJSONObjectFlexible(rawResult, "purple"), "purple_metrics")

        // 毛孔：pores.pores_metrics（name/value）
        poresData = parseBrownPoresTextureResponse(optJSONObjectFlexible(rawResult, "pores"), "pores_metrics")

        // 纹理：texture.texture_metrics（name/value）
        textureData = parseBrownPoresTextureResponse(optJSONObjectFlexible(rawResult, "texture"), "texture_metrics")

        Log.d(TAG, "parseRawResult: redness=${rednessData?.detected}, spots=${spotsData?.detected}, brown=${brownData?.detected}, purple=${purpleData?.detected}, pores=${poresData?.detected}, texture=${textureData?.detected}")
    }

    /**
     * 解析色斑检测数据
     * 表格数据来自 spots.spots_metrics.region_distribution（对象结构，key 为分区名）：
     *   key(region) -> 分区（chin/nose/forehead/left_cheek/right_cheek/other，转中文）
     *   count -> 斑点数
     *   area_ratio -> 面积占比（小数，转百分比显示）
     * 图片：overlay_url
     */
    private fun parseSpotsResponse(obj: JSONObject?): DetectData? {
        if (obj == null) {
            Log.w(TAG, "parseSpotsResponse: spots obj is null -> 卡片隐藏")
            return null
        }
        Log.d(TAG, "parseSpotsResponse: parsing spots data")
        val detected = optBooleanFlexible(obj, "detected")
        if (!detected) {
            Log.w(TAG, "parseSpotsResponse: detected=false -> 卡片隐藏")
            return DetectData(false, "", emptyList())
        }

        // 图片 URL
        var imageUrl = ""
        for (key in arrayOf("overlay_url", "uv_spots_overlay_url", "image_url", "url")) {
            val v = obj.optString(key, "")
            if (v.isNotEmpty() && v != "null") { imageUrl = v; break }
        }

        // 表格数据：spots_metrics.region_distribution
        // 兼容两种结构：
        //   1. JSONArray：[{region, count, area_ratio}, ...]
        //   2. JSONObject：{chin: {count, area_ratio}, ...}（key 为分区名）
        val rows = mutableListOf<DetectTableRow>()
        val metrics = optJSONObjectFlexible(obj, "spots_metrics")
        Log.d(TAG, "parseSpotsResponse: spots_metrics keys=${metrics?.keys()?.asSequence()?.toList()}, region_distributionRaw=${metrics?.opt("region_distribution")?.javaClass?.simpleName}")

        if (metrics != null) {
            val distArr = metrics.optJSONArray("region_distribution")
            val distObj = optJSONObjectFlexible(metrics, "region_distribution")

            // 收集 (regionKey, itemJson) 对
            val entries = mutableListOf<Pair<String, JSONObject>>()
            if (distArr != null) {
                // 数组结构：每项含 region 字段
                for (i in 0 until distArr.length()) {
                    val item = distArr.optJSONObject(i) ?: continue
                    val regionKey = pickStr(item, "region")
                    entries.add(regionKey to item)
                }
            } else if (distObj != null) {
                // 对象结构：key 为分区名
                for (regionKey in distObj.keys().asSequence().toList()) {
                    val item = distObj.optJSONObject(regionKey) ?: continue
                    entries.add(regionKey to item)
                }
            }
            Log.d(TAG, "parseSpotsResponse: entries.size=${entries.size}, regions=${entries.map { it.first }}")

            // 按固定顺序输出分区，保证显示顺序稳定
            val regionOrder = listOf("forehead", "left_cheek", "right_cheek", "nose", "chin", "other")
            val ordered = entries.sortedBy { (key, _) ->
                val idx = regionOrder.indexOf(key)
                if (idx >= 0) idx else regionOrder.size
            }

            for ((regionKey, item) in ordered) {
                val zone = rednessRegionToChinese(regionKey)
                val count = pickStr(item, "count")
                // area_ratio 是小数（如 0.01364992），转为百分比字符串（保留2位小数，带%）
                val ratioRaw = item.optDouble("area_ratio", Double.NaN)
                val ratioStr = if (ratioRaw.isNaN()) {
                    pickStr(item, "area_ratio")
                } else {
                    String.format(Locale.US, "%.2f%%", ratioRaw * 100)
                }

                rows.add(DetectTableRow(
                    zone = zone,
                    score = count,          // 斑点数
                    count = ratioStr,       // 面积占比
                    pixelLength = "",
                    avgLength = "",
                    maxLength = "",
                    density = "",
                    ratio = "",
                    area = ""
                ))
            }
        }

        return DetectData(true, imageUrl, rows, headers = spotsTableHeaders)
    }

    /**
     * 解析红区检测数据
     * 表格数据来自 redness.redness_metrics.red_feature_region_distribution：
     *   region -> 分区（chin/nose/forehead/left_cheek/right_cheek，转中文）
     *   count -> 特征数
     *   area -> 总像素数
     *   area_ratio -> 面积占比（小数，转百分比显示）
     * 图片：overlay_url
     */
    private fun parseRednessResponse(obj: JSONObject?): DetectData? {
        if (obj == null) return null
        val detected = obj.optBoolean("detected", false)
        if (!detected) return DetectData(false, "", emptyList())

        // 图片 URL
        var imageUrl = ""
        for (key in arrayOf("overlay_url", "red_areas_overlay_url", "image_url", "url")) {
            val v = obj.optString(key, "")
            if (v.isNotEmpty() && v != "null") { imageUrl = v; break }
        }

        // 表格数据：redness_metrics.red_feature_region_distribution
        val rows = mutableListOf<DetectTableRow>()
        val metrics = obj.optJSONObject("redness_metrics")
        val arr = metrics?.optJSONArray("red_feature_region_distribution")
        if (arr != null) {
            for (i in 0 until arr.length()) {
                val item = arr.optJSONObject(i) ?: continue
                val regionKey = pickStr(item, "region")
                val zone = rednessRegionToChinese(regionKey)
                val count = pickStr(item, "count")
                val area = pickStr(item, "area")
                // area_ratio 是小数（如 0.01637627），转为百分比字符串（保留2位小数，带%）
                val ratioRaw = item.optDouble("area_ratio", Double.NaN)
                val ratioStr = if (ratioRaw.isNaN()) {
                    pickStr(item, "area_ratio")
                } else {
                    String.format(Locale.US, "%.2f%%", ratioRaw * 100)
                }

                rows.add(DetectTableRow(
                    zone = zone,
                    score = count,       // 特征数
                    count = area,        // 总像素数
                    pixelLength = ratioStr, // 面积占比
                    avgLength = "",
                    maxLength = "",
                    density = "",
                    ratio = "",
                    area = ""
                ))
            }
        }

        return DetectData(true, imageUrl, rows, headers = rednessTableHeaders)
    }

    /**
     * 解析棕区/毛孔/纹理检测数据
     * 表格数据来自 {obj}.{metricsKey}（对象结构，key 为分区名）：
     *   name -> 分区名
     *   value -> 个数
     * 图片：overlay_url
     * @param obj brown/pores/texture 对应的 JSON 对象
     * @param metricsKey 指标字段名（brown_metrics/pores_metrics/texture_metrics）
     */
    private fun parseBrownPoresTextureResponse(obj: JSONObject?, metricsKey: String): DetectData? {
        if (obj == null) {
            Log.w(TAG, "parseBrownPoresTextureResponse: $metricsKey obj is null -> 卡片隐藏")
            return null
        }
        Log.d(TAG, "parseBrownPoresTextureResponse: parsing $metricsKey data")
        val detected = optBooleanFlexible(obj, "detected")
        if (!detected) {
            Log.w(TAG, "parseBrownPoresTextureResponse: $metricsKey detected=false -> 卡片隐藏")
            return DetectData(false, "", emptyList())
        }

        // 图片 URL
        var imageUrl = ""
        for (key in arrayOf("overlay_url", "uv_spots_overlay_url", "image_url", "url")) {
            val v = obj.optString(key, "")
            if (v.isNotEmpty() && v != "null") { imageUrl = v; break }
        }

        // 表格数据：{metricsKey}，兼容三种结构：
        //   1. {metricsKey} 是 JSONArray：[{name, value}, ...]
        //   2. {metricsKey} 是 JSONObject 且含 region_distribution（数组或对象）
        //   3. {metricsKey} 是 JSONObject：{regionKey: {name, value}, ...}
        val rows = mutableListOf<DetectTableRow>()

        // 先尝试把 {metricsKey} 当 JSONArray 处理
        val metricsArr = obj.optJSONArray(metricsKey)
        if (metricsArr != null) {
            Log.d(TAG, "parseBrownPoresTextureResponse: $metricsKey is JSONArray, size=${metricsArr.length()}")
            for (i in 0 until metricsArr.length()) {
                val item = metricsArr.optJSONObject(i) ?: continue
                rows.add(DetectTableRow(
                    zone = pickStr(item, "name"),
                    score = pickStr(item, "value"),
                    count = "", pixelLength = "", avgLength = "", maxLength = "",
                    density = "", ratio = "", area = ""
                ))
            }
        } else {
            // 当 JSONObject 处理
            val metrics = optJSONObjectFlexible(obj, metricsKey)
            Log.d(TAG, "parseBrownPoresTextureResponse: $metricsKey metrics keys=${metrics?.keys()?.asSequence()?.toList()}")

            if (metrics != null) {
                val distArr = metrics.optJSONArray("region_distribution")
                val distObj = optJSONObjectFlexible(metrics, "region_distribution")

                if (distArr != null) {
                    // 数组结构：每项含 name 和 value
                    for (i in 0 until distArr.length()) {
                        val item = distArr.optJSONObject(i) ?: continue
                        rows.add(DetectTableRow(
                            zone = pickStr(item, "name"),
                            score = pickStr(item, "value"),
                            count = "", pixelLength = "", avgLength = "", maxLength = "",
                            density = "", ratio = "", area = ""
                        ))
                    }
                } else if (distObj != null) {
                    // 对象结构：key 为分区名
                    for (regionKey in distObj.keys().asSequence().toList()) {
                        val item = distObj.optJSONObject(regionKey) ?: continue
                        rows.add(DetectTableRow(
                            zone = pickStr(item, "name").ifEmpty { regionKey },
                            score = pickStr(item, "value"),
                            count = "", pixelLength = "", avgLength = "", maxLength = "",
                            density = "", ratio = "", area = ""
                        ))
                    }
                } else {
                    // 无 region_distribution 子字段，直接遍历 metrics 的 key
                    for (regionKey in metrics.keys().asSequence().toList()) {
                        val item = metrics.optJSONObject(regionKey) ?: continue
                        rows.add(DetectTableRow(
                            zone = pickStr(item, "name").ifEmpty { regionKey },
                            score = pickStr(item, "value"),
                            count = "", pixelLength = "", avgLength = "", maxLength = "",
                            density = "", ratio = "", area = ""
                        ))
                    }
                }
            }
        }

        return DetectData(true, imageUrl, rows, headers = brownPoresTextureTableHeaders)
    }

    /** 红区分区英文 key 转中文名 */
    private fun rednessRegionToChinese(region: String): String {
        return when (region) {
            "forehead" -> "额头"
            "nose" -> "鼻子"
            "chin" -> "下巴"
            "left_cheek" -> "左脸颊"
            "right_cheek" -> "右脸颊"
            "other" -> "其他"
            else -> region.ifEmpty { "未知" }
        }
    }

    // ────── 皱纹/痤疮 单独接口获取 ──────

    /** 当前有效的 report_id（接口返回优先，其次 intent 传入） */
    private val currentReportId: String?
        get() = apiReportId ?: reportId

    /**
     * 触发 皱纹/痤疮 接口获取
     * img 流程：analysis 接口返回 report_id 后调用
     * list 流程：直接进入即可调用
     */
    private fun fetchWrinkleAndAcne() {
        val rid = currentReportId
        if (rid.isNullOrEmpty() || rid == "null") {
            Log.w(TAG, "fetchWrinkleAndAcne: report_id 为空，无法调用")
            return
        }
        // 先显示 loading
        showDetectCardLoading(R.id.cardWrinkle, R.id.loadingWrinkle)
        showDetectCardLoading(R.id.cardAcne, R.id.loadingAcne)
        fetchWrinkle(rid)
        fetchAcne(rid)
    }

    /**
     * 获取皱纹数据（单次）
     * GET /api/self-research-face/analysis/{report_id}/wrinkle
     */
    private fun fetchWrinkle(reportId: String) {
        val path = "/api/self-research-face/analysis/$reportId/wrinkle"
        Log.d(TAG, "fetchWrinkle: $path")
        HttpHelper.get(
            path = path,
            onSuccess = { body ->
                runOnUiThread {
                    wrinkleFetched = true
                    try {
                        val json = JSONObject(body)
                        wrinkleData = parseWrinkleResponse(unwrapDetectJson(json))
                        updateDetectCard(R.id.cardWrinkle, R.id.tableWrinkle, R.id.ivWrinkle, R.id.loadingWrinkle, wrinkleData, "皱纹检测", enableRowClick = true)
                    } catch (e: Exception) {
                        Log.e(TAG, "fetchWrinkle 解析失败", e)
                        findViewById<View>(R.id.cardWrinkle).visibility = View.GONE
                        findViewById<View>(R.id.loadingWrinkle).visibility = View.GONE
                    }
                }
            },
            onFailure = { code, msg ->
                runOnUiThread {
                    wrinkleFetched = true
                    Log.e(TAG, "fetchWrinkle 失败: $code, $msg")
                    findViewById<View>(R.id.cardWrinkle).visibility = View.GONE
                    findViewById<View>(R.id.loadingWrinkle).visibility = View.GONE
                }
            },
            timeoutSeconds = API_TIMEOUT_SECONDS
        )
    }

    /**
     * 获取痤疮数据（单次）
     * GET /api/self-research-face/analysis/{report_id}/acne
     */
    private fun fetchAcne(reportId: String) {
        val path = "/api/self-research-face/analysis/$reportId/acne"
        Log.d(TAG, "fetchAcne: $path")
        HttpHelper.get(
            path = path,
            onSuccess = { body ->
                runOnUiThread {
                    acneFetched = true
                    try {
                        val json = JSONObject(body)
                        acneData = parseDetectItem(
                            unwrapDetectJson(json),
                            arrayOf("acne_circles_url", "overlay_url", "image_url", "url")
                        )
                        updateDetectCard(R.id.cardAcne, R.id.tableAcne, R.id.ivAcne, R.id.loadingAcne, acneData, "痤疮检测")
                    } catch (e: Exception) {
                        Log.e(TAG, "fetchAcne 解析失败", e)
                        findViewById<View>(R.id.cardAcne).visibility = View.GONE
                        findViewById<View>(R.id.loadingAcne).visibility = View.GONE
                    }
                }
            },
            onFailure = { code, msg ->
                runOnUiThread {
                    acneFetched = true
                    Log.e(TAG, "fetchAcne 失败: $code, $msg")
                    findViewById<View>(R.id.cardAcne).visibility = View.GONE
                    findViewById<View>(R.id.loadingAcne).visibility = View.GONE
                }
            },
            timeoutSeconds = API_TIMEOUT_SECONDS
        )
    }

    /**
     * 解析皱纹接口返回数据
     * 表格数据来自 region_metrics 数组：
     *   region_name(中文名) + short_name(缩写) -> 分区（格式：中文名(缩写)）
     *   relative_score -> 相对分数
     *   segment_count -> 条数
     *   wrinkle_pixels -> 像素长度
     *   mean_segment_length -> 平均线段
     *   max_segment_length -> 最长线段
     *   density_per_10k -> 密度/万px
     *   share_pct -> 占比%
     *   area_px -> 面积px
     * 图片：stage2_overlay_url
     */
    private fun parseWrinkleResponse(obj: JSONObject?): DetectData? {
        if (obj == null) return null
        val detected = obj.optBoolean("detected", false)
        if (!detected) return DetectData(false, "", emptyList())

        // 图片 URL
        var imageUrl = ""
        for (key in arrayOf("stage2_overlay_url", "overlay_url", "image_url", "url")) {
            val v = obj.optString(key, "")
            if (v.isNotEmpty() && v != "null") { imageUrl = v; break }
        }

        // 表格数据：region_metrics
        val rows = mutableListOf<DetectTableRow>()
        val arr = obj.optJSONArray("region_metrics")
        if (arr != null) {
            for (i in 0 until arr.length()) {
                val item = arr.optJSONObject(i) ?: continue
                val regionName = pickStr(item, "region_name")
                val shortName = pickStr(item, "short_name")
                val zone = if (shortName.isNotEmpty()) "$regionName($shortName)" else regionName

                rows.add(DetectTableRow(
                    zone = zone,
                    score = pickStr(item, "relative_score"),
                    count = pickStr(item, "segment_count"),
                    pixelLength = pickStr(item, "wrinkle_pixels"),
                    avgLength = pickStr(item, "mean_segment_length"),
                    maxLength = pickStr(item, "max_segment_length"),
                    density = pickStr(item, "density_per_10k"),
                    ratio = pickStr(item, "share_pct"),
                    area = pickStr(item, "area_px"),
                    regionImageUrl = pickStr(item, "region_image_url")
                ))
            }
        }

        return DetectData(true, imageUrl, rows)
    }

    /**
     * 解包接口返回的检测数据 JSON
     * 兼容：直接是检测对象，或包在 data/result/wrinkle/acne 字段里
     */
    private fun unwrapDetectJson(json: JSONObject): JSONObject? {
        // 直接包含 detected 字段 -> 就是检测对象
        if (json.has("detected")) return json
        // 常见包裹字段
        for (key in arrayOf("data", "result", "wrinkle", "acne")) {
            val obj = json.optJSONObject(key)
            if (obj != null) return obj
        }
        return json
    }

    /**
     * 更新所有视图数据
     */
    private fun updateViews() {
        // 基础信息
        findViewById<TextView>(R.id.tvReportId).text = "报告ID：${(apiReportId ?: reportId).orEmpty().ifEmpty { "-" }}"
        findViewById<TextView>(R.id.tvNickname).text = "昵称：${nickname.ifEmpty { "-" }}"
        findViewById<TextView>(R.id.tvTestTime).text = "测肤时间：${testTime.ifEmpty { "-" }}"

        // 原照片
        val ivFacePhoto = findViewById<ImageView>(R.id.ivFacePhoto)
        if (facePhotoUrl.isNotEmpty()) {
            val fullUrl = ensureFullUrl(facePhotoUrl)
            ivFacePhoto.load(fullUrl) {
                crossfade(true)
                placeholder(R.drawable.ic_default_avatar)
                error(R.drawable.ic_default_avatar)
            }
        } else if (!ossKey.isNullOrEmpty()) {
            // 没有 photo url 时尝试用 oss_key 拼 URL
            ivFacePhoto.load(ensureFullUrl(ossKey!!)) {
                crossfade(true)
                placeholder(R.drawable.ic_default_avatar)
                error(R.drawable.ic_default_avatar)
            }
        } else {
            ivFacePhoto.setImageResource(R.drawable.ic_default_avatar)
        }

        // 总体得分 + 右侧指标
        val displayedScore = skinScore ?: overallScore
        findViewById<TextView>(R.id.tvScoreValue).text = "总体得分 ${displayedScore}分"
        val metricMap = radarItems.associate { it.name to it.value }
        fun metricValue(vararg names: String): String {
            for (n in names) {
                metricMap[n]?.let { return it.toString() }
                // 模糊匹配：radar 名称包含关键字
                radarItems.firstOrNull { it.name.contains(n) }?.let { return it.value.toString() }
            }
            return "-"
        }
        findViewById<TextView>(R.id.tvMetric1).text = "水油平衡: ${metricValue("水油平衡", "水油", "水分", "油脂")}"
        findViewById<TextView>(R.id.tvMetric2).text = "毛孔状态: ${metricValue("毛孔状态", "毛孔")}"
        findViewById<TextView>(R.id.tvMetric3).text = "肤质弹性: ${metricValue("肤质弹性", "弹性")}"
        findViewById<TextView>(R.id.tvMetric4).text = "屏障健康: ${metricValue("屏障健康", "屏障")}"
        findViewById<TextView>(R.id.tvMetric5).text = "色素沉着: ${metricValue("色素沉着", "色素", "色斑")}"

        // 参考线分数：取 chartYData 的最后一个值作为 referenceScore
        if (chartYData.isNotEmpty()) {
            referenceScore = chartYData.last().toInt()
        }
        findViewById<TextView>(R.id.tvReferenceScore).text = "${referenceScore}分"

        // 更新折线图
        pushChartDataToWeb()

        // 更新雷达图
        pushRadarData()

        // 检测卡片（表格 + 图片）
        updateDetectCards()
    }

    /**
     * 确保 URL 是完整的（带有 https:// 前缀）
     */
    private fun ensureFullUrl(url: String): String {
        return if (url.startsWith("http://") || url.startsWith("https://")) {
            url
        } else {
            ApiConfig.BASE_URL.trimEnd('/') + if (url.startsWith("/")) url else "/$url"
        }
    }

    /**
     * 返回首页
     */
    private fun goHome() {
        val intent = Intent(this, com.example.aisia.MainActivity::class.java)
        intent.putExtra(com.example.aisia.MainActivity.EXTRA_TAB, "home")
        intent.flags = Intent.FLAG_ACTIVITY_CLEAR_TOP or Intent.FLAG_ACTIVITY_SINGLE_TOP
        startActivity(intent)
        finish()
    }

    override fun onDestroy() {
        // 停止蒙层相关动画和定时器
        stopAnalyzingAnimations()
        progressTimer?.cancel()
        progressTimer = null
        itemTimer?.cancel()
        itemTimer = null

        hideLoading()
        loadingDialog = null
        noFaceDialog?.dismiss()
        noFaceDialog = null
        dismissPreview()
        if (::webViewChart.isInitialized) {
            webViewChart.destroy()
        }
        if (::webViewRadar.isInitialized) {
            webViewRadar.destroy()
        }
        super.onDestroy()
    }
}
