package com.example.aisia.ui.work

import android.animation.ValueAnimator
import android.annotation.SuppressLint
import android.content.Intent
import android.os.Bundle
import android.os.Handler
import android.os.Looper
import android.util.Log
import android.view.Gravity
import android.view.View
import android.view.animation.AccelerateDecelerateInterpolator
import android.widget.FrameLayout
import android.widget.ImageView
import android.widget.LinearLayout
import android.widget.ProgressBar
import android.widget.TextView
import android.widget.Toast
import androidx.activity.OnBackPressedCallback
import androidx.appcompat.app.AlertDialog
import androidx.appcompat.app.AppCompatActivity
import coil.load
import com.example.aisia.MainActivity
import com.example.aisia.R
import com.example.aisia.ble.BleManager
import com.example.aisia.network.HttpHelper
import org.json.JSONObject

/**
 * 护理方案页面（对应小程序 pages/work/work）
 *
 * 接收参数：
 *   - report_id: 方案ID（treatment-plans 表的 id）
 *   - deviceId: 设备蓝牙 MAC
 *   - device_id: 设备数据库记录 ID（my-device 表）
 *
 * 调用 API：
 *   GET /api/my-device/{device_id}/treatment-plans/{planId}
 *   返回：{ id, regions: [{ region, description, plan: [{ speed, time }] }] }
 *
 * 交互：
 *   - 卡片手风琴展开/折叠
 *   - 启动/暂停设备（BLE 指令）
 *   - 关机（BLE 指令）
 *   - 返回首页
 */
class WorkActivity : AppCompatActivity() {

    companion object {
        private const val TAG = "WorkActivity"
        private const val SAFE_STOP_TIMEOUT_MS = 3_500L
        private const val SAFE_STOP_RETRY_DELAY_MS = 200L
        private const val SAFE_STOP_MAX_ATTEMPTS = 2
    }

    private lateinit var cardListContainer: LinearLayout
    private lateinit var btnStart: TextView
    private lateinit var btnClose: TextView
    private lateinit var btnGoHome: TextView
    private lateinit var progressBar: ProgressBar

    private var reportId: String = ""
    private var deviceId: String = ""
    private var deviceDatabaseId: String = ""

    private var planInfo: JSONObject? = null
    private var regions: List<JSONObject> = emptyList()
    private var expandedStates: BooleanArray = booleanArrayOf()
    private var currentRegion: String = ""
    private var currentPlan: List<JSONObject> = emptyList()

    private var isStarted = false
    private var isCancelled = false
    private var isFirst = true       // 与小程序一致：首次启动需发送 '1' 指令
    private var isBleConnected = false  // 本地连接状态标记
    private var cmdHandler = Handler(Looper.getMainLooper())
    private var cmdRunnable: Runnable? = null
    private var lastTime = 0
    private var deviceMayBeRunning = false
    private var stopInFlight = false
    private var stopAttempts = 0
    private var stopTimeoutRunnable: Runnable? = null
    private val stopCallbacks = mutableListOf<(Boolean) -> Unit>()
    private var leavingPage = false
    private var startRequestInFlight = false

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContentView(R.layout.activity_work)

        // 接收参数
        reportId = intent.getStringExtra("report_id") ?: ""
        deviceId = intent.getStringExtra("deviceId") ?: ""
        deviceDatabaseId = intent.getStringExtra("device_id") ?: ""
        Log.d(TAG, "onCreate: reportId=$reportId, deviceId=$deviceId, deviceDatabaseId=$deviceDatabaseId")

        initViews()
        setupListeners()
        loadPlanDetails()

        onBackPressedDispatcher.addCallback(this, object : OnBackPressedCallback(true) {
            override fun handleOnBackPressed() {
                finishAfterSafeStop()
            }
        })

        // 确保 BLE 连接：如果已经连接则跳过，否则启动扫描 → 连接
        ensureBleConnection()
    }

    /**
     * 确保 BLE 连接（对应小程序 _prepareBLEConnection / _connectAndEnsure）
     * - 已连接：直接返回成功
     * - 未连接：通过 MAC 地址直连 → 获取服务 → 收集可写特征值
     * - 直连失败回退到扫描连接
     */
    private fun ensureBleConnection() {
        // 监听连接状态变化（设备断开时更新 UI）
        BleManager.addStateListener(this) { connected ->
            runOnUiThread {
                if (isFinishing || isDestroyed) return@runOnUiThread
                isBleConnected = connected
                if (!connected && isStarted) {
                    // 设备意外断开，停止发送指令
                    isStarted = false
                    isCancelled = true
                    cmdRunnable?.let { cmdHandler.removeCallbacks(it) }
                    cmdRunnable = null
                    btnStart.text = "启动设备"
                    Toast.makeText(this, "设备连接已断开", Toast.LENGTH_SHORT).show()
                }
                updateButtonStates()
            }
        }

        if (BleManager.isConnected()) {
            Log.d(TAG, "ensureBleConnection: 已连接 (${BleManager.getDeviceId()})")
            isBleConnected = true
            updateButtonStates()
            return
        }
        if (deviceId.isBlank()) {
            Log.w(TAG, "ensureBleConnection: deviceId 为空，跳过蓝牙连接")
            isBleConnected = false
            updateButtonStates()
            return
        }

        Log.d(TAG, "ensureBleConnection: 开始连接流程 deviceId=$deviceId")
        runOnUiThread {
            btnStart.text = "正在连接设备..."
            btnStart.isEnabled = false
        }

        BleManager.connect(this, deviceId) { success, err ->
            runOnUiThread {
                isBleConnected = success
                if (success) {
                    Log.i(TAG, "ensureBleConnection: 连接成功, 可写特征值数量=${BleManager.getWritableCharCount()}")
                    btnStart.text = "启动设备"
                    Toast.makeText(this, "设备连接成功", Toast.LENGTH_SHORT).show()
                } else {
                    Log.e(TAG, "ensureBleConnection: 连接失败: $err")
                    btnStart.text = "启动设备"
                    Toast.makeText(
                        this,
                        "设备连接失败: ${err ?: "未知错误"}",
                        Toast.LENGTH_LONG
                    ).show()
                }
                updateButtonStates()
            }
        }
    }

    /**
     * 根据连接状态更新按钮可用性
     */
    private fun updateButtonStates() {
        val connected = isBleConnected && BleManager.isConnected()
        btnStart.isEnabled = true  // 始终可用，点击时会检查连接状态
        btnClose.isEnabled = connected
    }

    @SuppressLint("SetTextI18n")
    private fun initViews() {
        cardListContainer = findViewById(R.id.cardList)
        btnStart = findViewById(R.id.btnStart)
        btnClose = findViewById(R.id.btnClose)
        btnGoHome = findViewById(R.id.btnGoHome)

        // 添加 ProgressBar
        progressBar = ProgressBar(this).apply {
            visibility = View.GONE
        }

        findViewById<View>(R.id.btnBack).setOnClickListener { finishAfterSafeStop() }
    }

    private fun setupListeners() {
        // 启动/暂停按钮
        btnStart.setOnClickListener {
            if (isStarted) {
                onStopDevice()
            } else {
                onStartDevice()
            }
        }

        // 关机按钮
        btnClose.setOnClickListener {
            onShutdownDevice()
        }

        // 返回首页
        btnGoHome.setOnClickListener {
            goHomeAfterSafeStop()
        }
    }

    /**
     * 加载方案详情
     * GET /api/my-device/{device_id}/treatment-plans/{planId}
     */
    private fun loadPlanDetails() {
        val pathId = deviceDatabaseId.ifBlank { deviceId }
        if (pathId.isBlank() || reportId.isBlank()) {
            Toast.makeText(this, "参数缺失，无法加载方案", Toast.LENGTH_SHORT).show()
            return
        }

        progressBar.visibility = View.VISIBLE

        HttpHelper.get(
            path = "/api/my-device/$pathId/treatment-plans/$reportId",
            onSuccess = { resp ->
                Log.d(TAG, "loadPlanDetails success")
                runOnUiThread {
                    progressBar.visibility = View.GONE
                    handlePlanSuccess(resp)
                }
            },
            onFailure = { code, msg ->
                Log.e(TAG, "loadPlanDetails failed: $code $msg")
                runOnUiThread {
                    progressBar.visibility = View.GONE
                    Toast.makeText(this, "获取方案详情失败: $msg", Toast.LENGTH_SHORT).show()
                }
            }
        )
    }

    private fun handlePlanSuccess(resp: String) {
        try {
            val root = JSONObject(resp)
            // 后端返回结构通常为 { data: { id, regions: [...] } }，兼容无 data 层
            val data = root.optJSONObject("data") ?: root
            planInfo = data

            Log.d(TAG, "handlePlanSuccess: regions=${data.optJSONArray("regions")?.length() ?: 0}")

            val regionsArray = data.optJSONArray("regions")
            regions = if (regionsArray != null) {
                (0 until regionsArray.length()).map { i -> regionsArray.getJSONObject(i) }
            } else {
                emptyList()
            }

            expandedStates = BooleanArray(regions.size)
            if (regions.isNotEmpty()) {
                currentRegion = regions[0].optString("region", "")
                currentPlan = parsePlanArray(regions[0].optJSONArray("plan"))
            }

            renderCards()
        } catch (e: Exception) {
            Log.e(TAG, "parse plan response failed", e)
            Toast.makeText(this, "解析方案数据失败", Toast.LENGTH_SHORT).show()
        }
    }

    private fun parsePlanArray(arr: org.json.JSONArray?): List<JSONObject> {
        if (arr == null) return emptyList()
        return (0 until arr.length()).map { i -> arr.getJSONObject(i) }
    }

    // ==================== 渲染卡片列表（手风琴）====================

    private fun renderCards() {
        cardListContainer.removeAllViews()

        if (regions.isEmpty()) {
            val empty = TextView(this).apply {
                text = "暂无护理方案"
                setTextColor(0xFF999999.toInt())
                textSize = 14f
                gravity = Gravity.CENTER
                setPadding(0, dp2px(40), 0, dp2px(40))
            }
            cardListContainer.addView(empty)
            return
        }

        for (i in regions.indices) {
            val region = regions[i]
            val regionName = region.optString("region", "")
            val subtitle = pickSubtitle(regionName)
            val isExpanded = expandedStates[i]

            val card = createCard(i, regionName, subtitle, region, isExpanded)
            cardListContainer.addView(card)

            // 卡片间距 12dp
            if (i < regions.size - 1) {
                val spacer = View(this).apply {
                    layoutParams = LinearLayout.LayoutParams(
                        LinearLayout.LayoutParams.MATCH_PARENT,
                        dp2px(12)
                    )
                }
                cardListContainer.addView(spacer)
            }
        }
    }

    private fun createCard(
        index: Int,
        regionName: String,
        subtitle: String,
        region: JSONObject,
        isExpanded: Boolean
    ): LinearLayout {
        val card = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            background = resources.getDrawable(R.drawable.work_card_bg, null)
            layoutParams = LinearLayout.LayoutParams(
                LinearLayout.LayoutParams.MATCH_PARENT,
                LinearLayout.LayoutParams.WRAP_CONTENT
            )
            setOnClickListener { onCardTap(index) }
        }

        // ---- 卡片头部 ----
        val header = LinearLayout(this).apply {
            orientation = LinearLayout.HORIZONTAL
            gravity = Gravity.CENTER_VERTICAL
            setPadding(dp2px(12), dp2px(14), dp2px(12), dp2px(14))
        }

        // 左侧图标方块
        val iconBox = FrameLayout(this).apply {
            layoutParams = LinearLayout.LayoutParams(dp2px(36), dp2px(36)).apply {
                marginEnd = dp2px(10)
            }
            background = resources.getDrawable(R.drawable.work_icon_bg, null)
        }
        val iconImg = ImageView(this).apply {
            layoutParams = FrameLayout.LayoutParams(dp2px(22), dp2px(22)).apply {
                gravity = Gravity.CENTER
            }
            scaleType = ImageView.ScaleType.FIT_CENTER
            // 根据 region 加载不同的区域图片
            val iconUrl = pickRegionIcon(regionName)
            if (iconUrl.isNotBlank()) {
                load(iconUrl) {
                    error(R.drawable.face_placeholder)
                }
            } else {
                setImageResource(R.drawable.face_placeholder)
            }
        }
        iconBox.addView(iconImg)
        header.addView(iconBox)

        // 中间标题 + 副标题
        val contentLayout = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            layoutParams = LinearLayout.LayoutParams(0, LinearLayout.LayoutParams.WRAP_CONTENT, 1f)
        }
        val tvTitle = TextView(this).apply {
            text = "${regionName}护理方案"
            setTextColor(0xFF111111.toInt())
            textSize = 16f
            setTypeface(typeface, android.graphics.Typeface.BOLD)
        }
        val tvSubtitle = TextView(this).apply {
            text = subtitle
            setTextColor(0xFF999999.toInt())
            textSize = 11f
            maxLines = 1
        }
        contentLayout.addView(tvTitle)
        contentLayout.addView(tvSubtitle)
        header.addView(contentLayout)

        // 右侧箭头
        val tvArrow = TextView(this).apply {
            text = "›"
            setTextColor(if (isExpanded) 0xFF3A6DF0.toInt() else 0xFFC0C0C8.toInt())
            textSize = 22f
            rotation = if (isExpanded) 90f else 0f
            tag = "arrow"
        }
        header.addView(tvArrow)

        card.addView(header)

        // ---- 展开详情区 ----
        val detailContainer = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            tag = "detail"
            visibility = if (isExpanded) View.VISIBLE else View.GONE
        }

        // 描述
        val description = region.optString("description", "")
        val tvDesc = TextView(this).apply {
            text = if (description.isNotBlank()) description else "暂无详细描述"
            setTextColor(if (description.isNotBlank()) 0xFF444444.toInt() else 0xFF999999.toInt())
            textSize = 14f
            setLineSpacing(0f, 1.7f)
            setPadding(dp2px(58), 0, dp2px(12), dp2px(8))
        }
        detailContainer.addView(tvDesc)

        // 护理步骤
        val planArray = region.optJSONArray("plan")
        if (planArray != null && planArray.length() > 0) {
            // 分隔线
            val divider = View(this).apply {
                layoutParams = LinearLayout.LayoutParams(
                    LinearLayout.LayoutParams.MATCH_PARENT, 1
                ).apply {
                    setMargins(dp2px(58), dp2px(4), dp2px(12), dp2px(10))
                }
                setBackgroundColor(0xFFF0F1F3.toInt())
            }
            detailContainer.addView(divider)

            val tvPlanTitle = TextView(this).apply {
                text = "护理步骤"
                setTextColor(0xFF111111.toInt())
                textSize = 13f
                setTypeface(typeface, android.graphics.Typeface.BOLD)
                setPadding(dp2px(58), 0, dp2px(12), dp2px(8))
            }
            detailContainer.addView(tvPlanTitle)

            for (p in 0 until planArray.length()) {
                val step = planArray.getJSONObject(p)
                val speed = step.optInt("speed", 0)
                val time = step.optInt("time", 0)

                val row = LinearLayout(this).apply {
                    orientation = LinearLayout.HORIZONTAL
                    gravity = Gravity.CENTER_VERTICAL
                    setPadding(dp2px(58), dp2px(6), dp2px(12), dp2px(6))
                }

                val tvStep = TextView(this).apply {
                    text = "第${p + 1}步"
                    setTextColor(0xFF3A6DF0.toInt())
                    textSize = 13f
                    setTypeface(typeface, android.graphics.Typeface.BOLD)
                    layoutParams = LinearLayout.LayoutParams(0, LinearLayout.LayoutParams.WRAP_CONTENT, 1f)
                }
                val tvInfo = TextView(this).apply {
                    text = "力度 $speed · 时长 ${time}s"
                    setTextColor(0xFF666666.toInt())
                    textSize = 13f
                }
                row.addView(tvStep)
                row.addView(tvInfo)
                detailContainer.addView(row)
            }
        }

        // 底部 padding
        val bottomPad = View(this).apply {
            layoutParams = LinearLayout.LayoutParams(
                LinearLayout.LayoutParams.MATCH_PARENT,
                dp2px(14)
            )
        }
        detailContainer.addView(bottomPad)

        card.addView(detailContainer)
        return card
    }

    /**
     * 卡片点击：切换展开/折叠（手风琴）
     */
    private fun onCardTap(index: Int) {
        val wasExpanded = expandedStates[index]
        // 全部折叠
        for (i in expandedStates.indices) {
            expandedStates[i] = false
        }
        // 点击已折叠的卡片则展开
        if (!wasExpanded) {
            expandedStates[index] = true
            currentRegion = regions[index].optString("region", "")
            currentPlan = parsePlanArray(regions[index].optJSONArray("plan"))
        }
        renderCards()
    }

    /**
     * 根据区域名匹配图片 URL（与小程序 wxml 中的条件判断一致）
     */
    private fun pickRegionIcon(region: String): String {
        val base = "https://eveaisia.com/face/img/"
        return when {
            region.contains("额头") -> base + "face_et.png"
            region.contains("左脸颊") -> base + "face_lj.png"
            region.contains("右脸颊") -> base + "face_ylj.png"
            region.contains("左眼周") -> base + "face_yz.png"
            region.contains("右眼周") -> base + "face_yyz.png"
            region.contains("T区") -> base + "face_tq.png"
            region.contains("下巴") -> base + "face_xb.png"
            else -> ""
        }
    }

    /**
     * 根据区域名生成副标题（与小程序 pickSubtitle 一致）
     */
    private fun pickSubtitle(region: String): String {
        if (region.isBlank()) return "CARE PLAN"
        return when {
            region.contains("脸") || region.contains("面颊") -> "CHEEK · CARE PLAN"
            region.contains("T") -> "T-ZONE · CARE PLAN"
            region.contains("鼻") -> "NOSE · CARE PLAN"
            region.contains("眼") -> "EYE · CARE PLAN"
            region.contains("额") -> "FOREHEAD · CARE PLAN"
            region.contains("嘴") -> "MOUTH · CARE PLAN"
            region.contains("下") -> "CHIN · CARE PLAN"
            else -> "${region.uppercase()} · CARE PLAN"
        }
    }

    // ==================== 设备控制（BLE 指令）====================

    /**
     * 启动设备（对应小程序 onWork → sendCommand）
     * 1. 确保 BLE 已连接
     * 2. 调用 setPlan execute API 设置当前区域
     * 3. 如果是首次启动(isFirst)，发送启动指令 '1'，等 300ms
     * 4. 按 currentPlan 递归发送指令：speed → 单个 ASCII 字符，延时 = (time - lastTime) * 1000
     */
    private fun onStartDevice() {
        if (startRequestInFlight) {
            Toast.makeText(this, "设备正在启动，请稍候", Toast.LENGTH_SHORT).show()
            return
        }
        if (currentPlan.isEmpty()) {
            Toast.makeText(this, "暂无执行方案", Toast.LENGTH_SHORT).show()
            return
        }
        if (deviceId.isBlank()) {
            Toast.makeText(this, "设备ID为空，请重试", Toast.LENGTH_SHORT).show()
            return
        }
        // 先确保 BLE 连接
        if (!BleManager.isConnected()) {
            Toast.makeText(this, "设备未连接，正在尝试连接...", Toast.LENGTH_SHORT).show()
            ensureBleConnection()
            return
        }

        val pathId = deviceDatabaseId.ifBlank { deviceId }
        val planId = planInfo?.optString("id") ?: reportId

        // 与小程序一致：regions 是数组格式 {"regions": ["额头"]}
        val jsonBody = """{"regions":["$currentRegion"]}"""
        Log.d(TAG, "setPlan: execute treatment plan")

        isCancelled = false
        startRequestInFlight = true
        btnStart.isEnabled = false
        btnStart.text = "正在启动设备..."

        HttpHelper.postJson(
            path = "/api/my-device/$pathId/treatment-plans/$planId/execute",
            jsonBody = jsonBody,
            onSuccess = {
                Log.d(TAG, "setPlan success, 启动 sendCommand")
                runOnUiThread {
                    startRequestInFlight = false
                    btnStart.isEnabled = true
                    if (isCancelled || leavingPage || isFinishing || isDestroyed) {
                        Log.i(TAG, "setPlan success ignored: 页面已退出或启动已取消")
                        return@runOnUiThread
                    }
                    isStarted = true
                    isCancelled = false
                    deviceMayBeRunning = true
                    lastTime = 0
                    btnStart.text = "暂停设备"

                    if (isFirst) {
                        // 与小程序一致：发送启动指令 '1'，等待写入完成后再延迟 300ms
                        Log.d(TAG, "发送启动指令 '1'")
                        isFirst = false
                        BleManager.writeChar('1') { success ->
                            Log.d(TAG, "启动指令 '1' 发送结果: $success")
                            if (!success) {
                                runOnUiThread {
                                    Toast.makeText(this, "启动指令发送失败", Toast.LENGTH_SHORT).show()
                                    safeStop("start_command_failed")
                                }
                                return@writeChar
                            }
                            if (isCancelled || leavingPage || isFinishing || isDestroyed) return@writeChar
                            Toast.makeText(this, "启动指令已发送，请确认设备状态", Toast.LENGTH_SHORT).show()
                            // 写入完成后，延迟 300ms 再发送方案指令（与小程序 await 300ms 一致）
                            cmdHandler.postDelayed({
                                sendCommand(currentPlan.toMutableList())
                            }, 300)
                        }
                    } else {
                        sendCommand(currentPlan.toMutableList())
                    }

                }
            },
            onFailure = { code, msg ->
                Log.e(TAG, "setPlan failed: $code $msg")
                runOnUiThread {
                    startRequestInFlight = false
                    btnStart.isEnabled = true
                    btnStart.text = "启动设备"
                    if (!leavingPage && !isFinishing && !isDestroyed) {
                        Toast.makeText(this, "设置方案失败: $msg", Toast.LENGTH_SHORT).show()
                    }
                }
            }
        )
    }

    /**
     * 核心递归：发送单条 BLE 指令（对应小程序 sendCommand）
     * 逻辑与小程序完全一致：
     *   - 指令字符 = String(Number(current.speed) || 0).charAt(0)
     *   - delayMs = (current.time - lastTime) * 1000, 最小 100ms
     *   - 向所有可写特征值发送（_writeToAllCharacteristics）
     */
    private fun sendCommand(remaining: MutableList<JSONObject>) {
        if (isCancelled || !isStarted) {
            Log.d(TAG, "sendCommand: 已取消/已暂停，中止")
            return
        }
        if (remaining.isEmpty()) {
            Log.i(TAG, "sendCommand: 全部步骤执行完毕")
            safeStop("plan_completed") { success ->
                val message = if (success) "方案执行完毕" else "方案已结束，但停止指令未确认，请检查设备"
                Toast.makeText(this, message, Toast.LENGTH_SHORT).show()
            }
            return
        }

        val current = remaining.removeAt(0)
        val speed = current.optInt("speed", 0)
        val time = current.optInt("time", 0)

        // ★ 核心：指令 = speed 转完整 ASCII 字符串（与小程序 textToBytes 一致）
        // 小程序: const cmdChar = String(Number(current.speed) || 0)
        //         const bytes = this.textToBytes(cmdChar)  →  UTF-8/ASCII 字节
        val cmdStr = if (speed > 0) speed.toString() else "0"
        val cmdBytes = cmdStr.toByteArray(Charsets.US_ASCII)
        Log.d(
            TAG,
            "sendCommand: speed=$speed -> cmd=\"$cmdStr\" bytes=[${cmdBytes.joinToString { "0x${it.toInt().and(0xFF).toString(16).padStart(2, '0')}" }}], " +
                    "time=$time, lastTime=$lastTime, remaining=${remaining.size}"
        )

        // 计算相对延时（与小程序一致）
        val delayMs = ((time - lastTime) * 1000).toLong()
        val realDelay = if (delayMs < 100L) 100L else delayMs
        lastTime = time

        cmdRunnable = Runnable {
            cmdRunnable = null
            if (isCancelled || !isStarted) {
                Log.d(TAG, "sendCommand: 定时器触发时已取消")
                return@Runnable
            }
            // 向所有可写特征值发送 ASCII 字符串指令
            // 与小程序一致：等待写入完成后再发送下一条指令
            BleManager.writeString(cmdStr) { success ->
                if (!success) {
                    Log.w(TAG, "sendCommand: 指令 \"$cmdStr\" 下发失败，执行安全停机")
                    safeStop("plan_command_failed") { stopped ->
                        val message = if (stopped) "设备指令发送失败，已停止设备" else "设备指令发送失败，请立即检查设备"
                        Toast.makeText(this, message, Toast.LENGTH_LONG).show()
                    }
                    return@writeString
                }
                // 写入完成后再发送下一条（与小程序 .then() 一致）
                sendCommand(remaining)
            }
        }
        cmdHandler.postDelayed(cmdRunnable!!, realDelay)
    }

    /**
     * 暂停设备
     * - isCancelled=true, isStarted=false
     * - 取消 cmdRunnable
     * - 发送停止指令 '0'
     */
    private fun onStopDevice() {
        safeStop("user_paused") { success ->
            val message = if (success) "停止指令已发送，请确认设备已停止" else "停止指令未确认，请检查设备"
            Toast.makeText(this, message, Toast.LENGTH_SHORT).show()
        }
    }

    /**
     * 统一停止护理步骤，并在设备可能仍在运行时发送停止指令。
     * 多个退出/异常路径同时调用时只会保留一个在途停止任务，所有调用方共享结果。
     */
    private fun safeStop(reason: String, onComplete: ((Boolean) -> Unit)? = null) {
        if (Looper.myLooper() != Looper.getMainLooper()) {
            runOnUiThread { safeStop(reason, onComplete) }
            return
        }

        onComplete?.let(stopCallbacks::add)
        val shouldSendStop = deviceMayBeRunning || isStarted

        isCancelled = true
        isStarted = false
        cmdRunnable?.let { cmdHandler.removeCallbacks(it) }
        cmdRunnable = null
        if (::btnStart.isInitialized) btnStart.text = "启动设备"

        if (stopInFlight) {
            Log.d(TAG, "safeStop: 停止指令已在发送中, reason=$reason")
            return
        }
        if (!shouldSendStop) {
            dispatchStopCallbacks(true)
            return
        }
        if (!BleManager.isConnected()) {
            Log.w(TAG, "safeStop: 设备未连接，无法确认停止, reason=$reason")
            dispatchStopCallbacks(false)
            return
        }

        stopInFlight = true
        stopAttempts = 0
        stopTimeoutRunnable = Runnable {
            if (stopInFlight) {
                Log.e(TAG, "safeStop: 等待停止指令确认超时, reason=$reason")
                completeSafeStop(false)
            }
        }.also { cmdHandler.postDelayed(it, SAFE_STOP_TIMEOUT_MS) }
        sendStopAttempt(reason)
    }

    private fun sendStopAttempt(reason: String) {
        stopAttempts++
        val attempt = stopAttempts
        Log.i(TAG, "safeStop: 发送停止指令, reason=$reason, attempt=$attempt")
        BleManager.writeChar('0') { success ->
            runOnUiThread {
                if (!stopInFlight) return@runOnUiThread
                if (success) {
                    Log.i(TAG, "safeStop: 停止指令已确认, reason=$reason, attempt=$attempt")
                    completeSafeStop(true)
                } else if (attempt < SAFE_STOP_MAX_ATTEMPTS && BleManager.isConnected()) {
                    Log.w(TAG, "safeStop: 停止指令发送失败，准备重试, reason=$reason")
                    cmdHandler.postDelayed({
                        if (stopInFlight) sendStopAttempt(reason)
                    }, SAFE_STOP_RETRY_DELAY_MS)
                } else {
                    Log.e(TAG, "safeStop: 停止指令发送失败, reason=$reason")
                    completeSafeStop(false)
                }
            }
        }
    }

    private fun completeSafeStop(success: Boolean) {
        stopTimeoutRunnable?.let { cmdHandler.removeCallbacks(it) }
        stopTimeoutRunnable = null
        stopInFlight = false
        if (success) deviceMayBeRunning = false
        dispatchStopCallbacks(success)
    }

    private fun dispatchStopCallbacks(success: Boolean) {
        if (stopCallbacks.isEmpty()) return
        val callbacks = stopCallbacks.toList()
        stopCallbacks.clear()
        callbacks.forEach { it(success) }
    }

    private fun finishAfterSafeStop() {
        if (leavingPage) return
        leavingPage = true
        safeStop("leave_page") { success ->
            if (!success) {
                Toast.makeText(this, "停止指令未确认，请检查设备", Toast.LENGTH_SHORT).show()
            }
            finish()
        }
    }

    private fun goHomeAfterSafeStop() {
        if (leavingPage) return
        leavingPage = true
        safeStop("go_home") { success ->
            if (!success) {
                Toast.makeText(this, "停止指令未确认，请检查设备", Toast.LENGTH_SHORT).show()
            }
            val intent = Intent(this, MainActivity::class.java)
            intent.flags = Intent.FLAG_ACTIVITY_CLEAR_TOP or Intent.FLAG_ACTIVITY_NEW_TASK
            startActivity(intent)
            finish()
        }
    }

    /**
     * 关机（对应小程序 onClose）
     * - 发送关机指令 's'（与小程序一致）
     * - 断开 BLE 连接
     */
    private fun onShutdownDevice() {
        isCancelled = true
        isStarted = false
        cmdRunnable?.let { cmdHandler.removeCallbacks(it) }
        cmdRunnable = null

        if (BleManager.isConnected()) {
            // 与小程序一致：发送关机指令 's'
            BleManager.writeChar('s') { success ->
                Log.d(TAG, "onShutdownDevice: 发送 's' 关机指令: $success")
                runOnUiThread {
                    if (success) {
                        Toast.makeText(this, "设备已关机", Toast.LENGTH_SHORT).show()
                    } else {
                        Toast.makeText(this, "关机指令发送失败", Toast.LENGTH_SHORT).show()
                    }
                }
            }
            // 短暂延时后断开
            cmdHandler.postDelayed({
                BleManager.disconnect()
                btnStart.isEnabled = false
                btnClose.isEnabled = false
            }, 500L)
        } else {
            Toast.makeText(this, "设备已关机", Toast.LENGTH_SHORT).show()
        }
    }

    // ==================== 工具方法 ====================

    private fun dp2px(dp: Int): Int {
        return (dp * resources.displayMetrics.density + 0.5f).toInt()
    }

    override fun onDestroy() {
        // 即使页面被系统销毁，也要发起幂等安全停机；显式返回路径会先等待发送结果。
        safeStop("activity_destroyed")
        // 重置首次启动标记
        isFirst = true
        BleManager.removeListeners(this)
        // 此处不主动断开 BLE（用户可能返回继续使用）
        // 真正释放见 Application 退出或用户点击"关机"按钮
        super.onDestroy()
    }
}
