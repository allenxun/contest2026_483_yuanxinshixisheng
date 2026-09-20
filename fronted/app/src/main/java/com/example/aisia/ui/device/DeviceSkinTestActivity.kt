package com.example.aisia.ui.device

import android.Manifest
import android.content.ContentValues
import android.content.Context
import android.content.Intent
import android.content.pm.PackageManager
import android.graphics.BitmapFactory
import android.net.ConnectivityManager
import android.net.Network
import android.net.NetworkCapabilities
import android.net.NetworkRequest
import android.net.wifi.WifiConfiguration
import android.net.wifi.WifiManager
import android.os.Build
import android.os.Bundle
import android.provider.Settings
import android.view.View
import android.widget.ImageView
import android.widget.LinearLayout
import android.widget.TextView
import android.widget.Toast
import androidx.activity.OnBackPressedCallback
import androidx.activity.result.contract.ActivityResultContracts
import androidx.appcompat.app.AlertDialog
import androidx.appcompat.app.AppCompatActivity
import androidx.core.content.ContextCompat
import androidx.lifecycle.lifecycleScope
import com.example.aisia.R
import com.example.aisia.privacy.PrivacyManager
import com.sdk.wifivideo.WifiCamera
import kotlinx.coroutines.delay
import kotlinx.coroutines.launch

/**
 * WiFi摄像头皮肤测试页面
 *
 * 功能流程（参考接口文档）:
 *   1. 进入页面 -> 保存当前WiFi -> 扫描 CC- 开头的热点 -> 自动连接
 *   2. 连接成功后 -> 创建 SDP 文件 -> 创建摄像头实例 -> 开启预览
 *   3. 预览期间 -> 获取视频帧、控制 LED、读取水份/电量
 *   4. 退出页面 -> 释放摄像头资源 -> 恢复之前的 WiFi
 *
 * 接口文档对应方法:
 *   WifiCamera.createSdpFile(context)        - 创建SDP配置文件
 *   WifiCamera.nativeCreateCamera(sdpPath)    - 创建摄像头实例
 *   WifiCamera.nativeDestroyCamera(cameraId)  - 销毁摄像头实例
 *   WifiCamera.nativeStartPreview(cameraId)   - 开启预览
 *   WifiCamera.nativeStopPreview(cameraId)    - 停止预览
 *   WifiCamera.nativeGetFrameBuffer(cameraId) - 获取视频帧
 *   WifiCamera.nativeSetCameraLed(cameraId, index) - 控制LED
 *   WifiCamera.nativeGetShuifen(cameraId)     - 获取水份值
 *   WifiCamera.nativeGetDianliang(cameraId)   - 获取电量值
 *   WifiCamera.nativeHardwareTakePicture(cameraId) - 检测硬件按键
 */
class DeviceSkinTestActivity : AppCompatActivity() {

    companion object {
        private const val TAG = "DeviceSkinTest"
        private const val HOTSPOT_PREFIX = "CC-"
        private const val DEFAULT_PASSWORD = "12345678"
    }

    // ============== WiFi管理 ==============
    private lateinit var cameraWifiManager: CameraWifiManager

    // ============== 摄像头控制 ==============
    private lateinit var wifiCamera: WifiCamera
    @Volatile private var cameraId: Long = 0L
    @Volatile private var isConnected = false
    @Volatile private var isPreviewing = false
    @Volatile private var isAutoConnecting = false
    private val cameraStateLock = Any()
    private val cameraGeneration = java.util.concurrent.atomic.AtomicInteger()
    private val connectionWorker = java.util.concurrent.Executors.newSingleThreadExecutor()
    private var connectionTask: java.util.concurrent.Future<*>? = null
    private val nativeConnectActive = java.util.concurrent.atomic.AtomicBoolean()
    @Volatile private var previewReadStartedAt = 0L
    private val responseHandler = android.os.Handler(android.os.Looper.getMainLooper())
    private val previewWatchdog = object : Runnable {
        override fun run() {
            if (leaving || isDestroyed || !isPreviewing) return
            val started = previewReadStartedAt
            if (started != 0L && android.os.SystemClock.elapsedRealtime() - started > 10000) {
                disconnectCamera()
                updateStatus("设备响应超时", "请检查摄像头，等待设备恢复后重试")
                return
            }
            responseHandler.postDelayed(this, 1000)
        }
    }
    private val framePending = java.util.concurrent.atomic.AtomicBoolean()
    @Volatile private var leaving = false
    private fun postCameraUi(token: Int = cameraGeneration.get(), action: () -> Unit) {
        runOnUiThread { if (!leaving && !isFinishing && !isDestroyed && token == cameraGeneration.get()) action() }
    }
    private var previewThread: Thread? = null
    private var keyCheckThread: Thread? = null
    private var currentLedIndex = 3

    // ============== 视图引用 ==============
    private lateinit var btnBack: View
    private lateinit var ivStatusIcon: ImageView
    private lateinit var tvStatusTitle: TextView
    private lateinit var tvCameraStatus: TextView
    private lateinit var layoutWifiInfo: LinearLayout
    private lateinit var tvConnectionStatus: TextView
    private lateinit var tvWifiSsid: TextView
    private lateinit var ivPreview: ImageView
    private lateinit var layoutPreviewHint: LinearLayout
    private lateinit var tvPreviewHint: TextView
    private lateinit var tvBottomHint: TextView
    private lateinit var tvMoistureValue: TextView
    private lateinit var tvBatteryStatus: TextView
    private lateinit var layoutLedControl: LinearLayout
    private lateinit var btnLedOff: TextView
    private lateinit var btnLed1: TextView
    private lateinit var btnLed2: TextView
    private lateinit var btnLed3: TextView
    private lateinit var btnRefresh: TextView
    private lateinit var btnCapture: TextView
    private lateinit var btnMoisture: TextView

    private val wifiPermissionLauncher = registerForActivityResult(
        ActivityResultContracts.RequestMultiplePermissions()
    ) { results ->
        val granted = requiredWifiPermissions().all { permission ->
            results[permission] == true || ContextCompat.checkSelfPermission(
                this,
                permission
            ) == PackageManager.PERMISSION_GRANTED
        }
        if (granted) {
            startAutoConnect()
        } else {
            updateStatus("无法扫描摄像头WiFi", "请授予附近设备权限后重试")
            Toast.makeText(this, "未获得WiFi扫描权限", Toast.LENGTH_SHORT).show()
        }
    }

    // ============== 生命周期 ==============
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContentView(R.layout.activity_device_skin_test)

        cameraWifiManager = CameraWifiManager(this)
        wifiCamera = WifiCamera()  // 创建摄像头实例，内部会加载 native 库

        initViews()
        setupClickListeners()
        onBackPressedDispatcher.addCallback(this, object : OnBackPressedCallback(true) {
            override fun handleOnBackPressed() {
                disconnectAndExit()
            }
        })

        // 合规要求：用户同意隐私政策后才能申请位置权限
        PrivacyManager.ensureAgreed(this) {
            ensureWifiPermissionAndConnect()
        }
    }

    private fun ensureWifiPermissionAndConnect() {
        val permissions = requiredWifiPermissions()
        val hasAllPermissions = permissions.all {
            ContextCompat.checkSelfPermission(this, it) == PackageManager.PERMISSION_GRANTED
        }
        if (hasAllPermissions) {
            startAutoConnect()
            return
        }

        val permissionName = if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU) {
            "附近设备权限"
        } else {
            "位置权限"
        }
        updateStatus("正在检查WiFi状态...", "需要${permissionName}来扫描摄像头WiFi")
        wifiPermissionLauncher.launch(permissions)
    }

    private fun requiredWifiPermissions(): Array<String> =
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU) {
            arrayOf(Manifest.permission.NEARBY_WIFI_DEVICES)
        } else {
            arrayOf(Manifest.permission.ACCESS_FINE_LOCATION)
        }

    override fun onDestroy() {
        leaving = true
        disconnectCamera()
        connectionWorker.shutdownNow()
        try { cameraWifiManager.cleanup() } catch (e: Exception) {}
        super.onDestroy()
    }

    // ============== 视图初始化 ==============
    private fun initViews() {
        btnBack = findViewById(R.id.btnBack)
        ivStatusIcon = findViewById(R.id.ivStatusIcon)
        tvStatusTitle = findViewById(R.id.tvStatusTitle)
        tvCameraStatus = findViewById(R.id.tvCameraStatus)
        layoutWifiInfo = findViewById(R.id.layoutWifiInfo)
        tvConnectionStatus = findViewById(R.id.tvConnectionStatus)
        tvWifiSsid = findViewById(R.id.tvWifiSsid)
        ivPreview = findViewById(R.id.ivPreview)
        layoutPreviewHint = findViewById(R.id.layoutPreviewHint)
        tvPreviewHint = findViewById(R.id.tvPreviewHint)
        tvBottomHint = findViewById(R.id.tvBottomHint)
        tvMoistureValue = findViewById(R.id.tvMoistureValue)
        tvBatteryStatus = findViewById(R.id.tvBatteryStatus)
        layoutLedControl = findViewById(R.id.layoutLedControl)
        btnLedOff = findViewById(R.id.btnLedOff)
        btnLed1 = findViewById(R.id.btnLed1)
        btnLed2 = findViewById(R.id.btnLed2)
        btnLed3 = findViewById(R.id.btnLed3)
        btnRefresh = findViewById(R.id.btnRefresh)
        btnCapture = findViewById(R.id.btnCapture)
        btnMoisture = findViewById(R.id.btnMoisture)
    }

    private fun setupClickListeners() {
        btnBack.setOnClickListener { disconnectAndExit() }
        btnRefresh.setOnClickListener { refreshDevice() }
        btnCapture.setOnClickListener { takePicture() }
        btnMoisture.setOnClickListener { readMoisture() }
        btnLedOff.setOnClickListener { setLed(0) }
        btnLed1.setOnClickListener { setLed(1) }
        btnLed2.setOnClickListener { setLed(2) }
        btnLed3.setOnClickListener { setLed(3) }
    }

    // ============== 状态更新 ==============
    private fun updateStatus(title: String, detail: String) {
        if (android.os.Looper.myLooper() != android.os.Looper.getMainLooper()) { postCameraUi { updateStatus(title, detail) }; return }
        if (leaving || isFinishing || isDestroyed) return
        tvStatusTitle.text = title
        tvCameraStatus.text = detail
    }

    private fun updateLedUI() {
        val inactiveBg = R.drawable.bg_btn_outline
        val activeBg = R.drawable.bg_btn_capture

        btnLedOff.setTextColor(0xFF666666.toInt())
        btnLed1.setTextColor(0xFF666666.toInt())
        btnLed2.setTextColor(0xFF666666.toInt())
        btnLed3.setTextColor(0xFF666666.toInt())

        btnLedOff.setBackgroundResource(inactiveBg)
        btnLed1.setBackgroundResource(inactiveBg)
        btnLed2.setBackgroundResource(inactiveBg)
        btnLed3.setBackgroundResource(inactiveBg)

        when (currentLedIndex) {
            0 -> { btnLedOff.apply { setBackgroundResource(activeBg); setTextColor(0xFFFFFFFF.toInt()) } }
            1 -> { btnLed1.apply { setBackgroundResource(activeBg); setTextColor(0xFFFFFFFF.toInt()) } }
            2 -> { btnLed2.apply { setBackgroundResource(activeBg); setTextColor(0xFFFFFFFF.toInt()) } }
            3 -> { btnLed3.apply { setBackgroundResource(activeBg); setTextColor(0xFFFFFFFF.toInt()) } }
        }
    }

    // ============== 自动连接流程 ==============
    private fun startAutoConnect() {
        if (android.os.Looper.myLooper() != android.os.Looper.getMainLooper()) { postCameraUi { startAutoConnect() }; return }
        if (leaving || isFinishing || isDestroyed || isAutoConnecting) return
        isAutoConnecting = true

        lifecycleScope.launch {
            try {
                val currentSsid = cameraWifiManager.getCurrentSsid()
                updateStatus("正在连接摄像头WiFi...", "当前WiFi: ${currentSsid ?: "未连接"}")

                // 已在摄像头WiFi上
                if (currentSsid != null && currentSsid.startsWith(HOTSPOT_PREFIX)) {
                    tvWifiSsid.text = currentSsid
                    layoutWifiInfo.visibility = View.VISIBLE
                    updateStatus("正在连接摄像头...", "已在摄像头WiFi: $currentSsid")
                    connectCamera()
                    isAutoConnecting = false
                    return@launch
                }

                // 保存当前WiFi，扫描并连接
                cameraWifiManager.saveCurrentWifi()
                updateStatus("正在扫描摄像头WiFi...", "寻找 CC- 开头的热点")

                val wifiConnected = cameraWifiManager.connectToCameraWifi()

                if (!wifiConnected) {
                    updateStatus("WiFi自动连接失败", "请手动连接摄像头热点后重试")
                    showManualWifiDialog()
                    isAutoConnecting = false
                    return@launch
                }

                // WiFi切换成功
                val newSsid = cameraWifiManager.getCurrentSsid()
                tvWifiSsid.text = newSsid ?: HOTSPOT_PREFIX + "6622_xxxxxx"
                layoutWifiInfo.visibility = View.VISIBLE
                updateStatus("正在连接摄像头...", "已连接WiFi: ${newSsid ?: "未知"}")
                delay(2000)

                connectCamera()

            } catch (e: Exception) {
                updateStatus("连接失败", e.message ?: "未知错误")
            }
            isAutoConnecting = false
        }
    }

    // ============== 摄像头连接 ==============
    private fun connectCamera() {
        if (android.os.Looper.myLooper() != android.os.Looper.getMainLooper()) { postCameraUi { connectCamera() }; return }
        if (leaving || isFinishing || isDestroyed || connectionTask?.isDone == false) return
        if (nativeConnectActive.get() || previewReadStartedAt != 0L) {
            updateStatus("设备仍未响应", "请重新开启摄像头，待当前调用结束后重试")
            return
        }
        val token = cameraGeneration.get()
        responseHandler.postDelayed({
            if (token == cameraGeneration.get() && !isConnected && nativeConnectActive.get()) {
                disconnectCamera()
                updateStatus("连接超时", "请检查摄像头电源和网络后重试")
            }
        }, 20000)
        connectionTask = connectionWorker.submit {
            nativeConnectActive.set(true)
            var localCameraId = 0L
            try {
                if (token != cameraGeneration.get() || leaving) return@submit
                // --- 前置检查 1: native 库是否加载成功 ---
                if (!WifiCamera.isLibraryLoaded) {
                    postCameraUi(token) {
                        updateStatus(
                            "摄像头库加载失败",
                            "native .so 库未成功加载\n可能原因: 设备 CPU 架构不匹配 (需要 arm64-v8a 或 armeabi-v7a)"
                        )
                        showManualWifiDialog()
                    }
                    return@submit
                }

                // --- 前置检查 2: 当前是否在 CC- WiFi 上 ---
                val ssidNow = cameraWifiManager.getCurrentSsid()
                if (ssidNow == null || !ssidNow.startsWith(HOTSPOT_PREFIX)) {
                    postCameraUi(token) {
                        updateStatus(
                            "WiFi 未连接到摄像头",
                            "当前WiFi: ${ssidNow ?: "(无)"}\n请先连接到 $HOTSPOT_PREFIX 开头的热点"
                        )
                        showManualWifiDialog()
                    }
                    return@submit
                }

                postCameraUi(token) {
                    updateStatus(
                        "正在连接摄像头...",
                        "WiFi: $ssidNow\n正在初始化摄像头控制通道"
                    )
                }

                // --- 1. 创建 SDP 文件 ---
                val sdpPath = wifiCamera.createSdpFile(this@DeviceSkinTestActivity)
                if (sdpPath.isEmpty()) {
                    postCameraUi(token) {
                        updateStatus("连接失败", "SDP会话描述文件创建失败\n可能原因: 存储权限或文件系统错误")
                        showManualWifiDialog()
                    }
                    return@submit
                }

                // --- 2. 创建摄像头实例（核心！失败返回 0）---
                // 第 1 次调用
                localCameraId = wifiCamera.createCamera(sdpPath)
                android.util.Log.i(TAG, "nativeCreateCamera 第1次: 返回=$localCameraId")

                // 第 2 次
                if (localCameraId == 0L) {
                    postCameraUi(token) {
                        updateStatus("正在重试连接...", "摄像头第1次未响应，等待后重试\nWiFi: $ssidNow")
                    }
                    Thread.sleep(2000)
                    localCameraId = wifiCamera.createCamera(sdpPath)
                    android.util.Log.i(TAG, "nativeCreateCamera 第2次: 返回=$localCameraId")
                }

                // 第 3 次
                if (localCameraId == 0L) {
                    Thread.sleep(1000)
                    localCameraId = wifiCamera.createCamera(sdpPath)
                    android.util.Log.i(TAG, "nativeCreateCamera 第3次: 返回=$localCameraId")
                }

                // === 3 次都返回 0，彻底失败 ===
                if (localCameraId == 0L) {
                    val wifiLog = cameraWifiManager.lastConnectLog.takeLast(10).joinToString("\n")
                    postCameraUi(token) {
                        updateStatus(
                            "❌ 无法创建摄像头实例",
                            "WiFi已连接到 $ssidNow，但 native 库无法与摄像头通信\n\n" +
                                "常见原因：\n" +
                                "1. IP 192.168.100.1 不可达（热点不是真正的摄像头设备）\n" +
                                "2. 摄像头 UDP 端口被防火墙阻挡\n" +
                                "3. 摄像头固件版本不兼容\n\n" +
                                "WiFi日志（最近）：\n$wifiLog"
                        )
                        showManualWifiDialog()
                    }
                    return@submit
                }

                android.util.Log.i(TAG, "✓ 摄像头句柄创建成功: localCameraId=$localCameraId")

                // --- 3. 开启预览 ---
                // 注意：nativeStartPreview 偶尔会返回 false，常见于 UDP 流还没建立起来时
                // 所以这里尝试 3 次，每次间隔 1 秒
                var previewOk = false
                for (attempt in 1..3) {
                    previewOk = wifiCamera.startPreview(localCameraId)
                    android.util.Log.i(TAG, "startPreview 第$attempt 次: $previewOk")
                    if (previewOk) break
                    Thread.sleep(1000)
                }

                if (!previewOk) {
                    postCameraUi(token) {
                        updateStatus(
                            "预览启动失败",
                            "摄像头已连接，但视频流无法启动\n请点击【刷新】按钮重试，或检查摄像头是否被其他设备占用"
                        )
                    }
                    try {
                        wifiCamera.destroyCamera(localCameraId)
                    } catch (_: Exception) {
                    }
                    localCameraId = 0L
                    return@submit
                }

                synchronized(cameraStateLock) {
                    if (token != cameraGeneration.get() || leaving || Thread.currentThread().isInterrupted) return@submit
                    cameraId = localCameraId
                    isConnected = true
                    isPreviewing = true
                }

                // UI更新
                postCameraUi(token) {
                    updateStatus("摄像头已连接", "预览正在进行中")
                    layoutPreviewHint.visibility = View.GONE
                    tvBottomHint.visibility = View.VISIBLE
                    layoutLedControl.visibility = View.VISIBLE
                    tvConnectionStatus.text = "已连接"
                    tvConnectionStatus.setTextColor(0xFF4CAF50.toInt())
                    updateLedUI()
                }

                // 4. 启动预览循环获取帧 (接口文档: nativeGetFrameBuffer)
                startPreviewLoop()
                postCameraUi(token) { responseHandler.post(previewWatchdog) }

                // 5. 启动硬件按键检测 (接口文档: nativeHardwareTakePicture)
                startKeyDetection()

                // 6. 初始读取一次水份/电量
                readDeviceStatus()

            } catch (_: InterruptedException) {
                Thread.currentThread().interrupt()
            } catch (e: UnsatisfiedLinkError) {
                postCameraUi(token) { updateStatus("连接失败", "Native接口错误: ${e.message}") }
            } catch (e: Exception) {
                postCameraUi(token) { updateStatus("连接失败", e.message ?: "未知错误") }
            }
            finally {
                if (localCameraId != 0L && (token != cameraGeneration.get() || !isConnected)) {
                    wifiCamera.stopPreview(localCameraId)
                    wifiCamera.destroyCamera(localCameraId)
                }
                nativeConnectActive.set(false)
            }
        }
    }

    // ============== 预览循环 (接口文档: nativeGetFrameBuffer) ==============
    private fun startPreviewLoop() {
        previewThread?.interrupt()
        val token = cameraGeneration.get()
        val handle = cameraId
        previewThread = Thread {
            var emptyFrameCount = 0        // 连续空帧计数器
            var lastFrameCount = 0          // 最近 3 秒内收到的帧数
            var lastStatusCheckTime = System.currentTimeMillis()

            while (token == cameraGeneration.get() && isPreviewing && isConnected && handle != 0L && !Thread.currentThread().isInterrupted) {
                try {
                    previewReadStartedAt = android.os.SystemClock.elapsedRealtime()
                    val frameData = try { wifiCamera.getFrameBuffer(handle) } finally { previewReadStartedAt = 0L }
                    if (frameData != null && frameData.isNotEmpty()) {
                        // 成功收到视频帧
                        emptyFrameCount = 0
                        lastFrameCount++
                        if (framePending.compareAndSet(false, true)) {
                            val bitmap = try { BitmapFactory.decodeByteArray(frameData, 0, frameData.size) }
                                catch (_: OutOfMemoryError) { null }
                            if (bitmap == null) framePending.set(false)
                            else runOnUiThread {
                                try {
                                    if (!leaving && !isDestroyed && token == cameraGeneration.get()) ivPreview.setImageBitmap(bitmap)
                                    else bitmap.recycle()
                                } finally { framePending.set(false) }
                            }
                        }
                    } else {
                        emptyFrameCount++
                    }

                    // --- 连接健康度检查：每 3 秒检查一次 ---
                    val now = System.currentTimeMillis()
                    if (now - lastStatusCheckTime > 3000) {
                        lastStatusCheckTime = now
                        android.util.Log.d(
                            TAG,
                            "预览健康度: 最近3秒帧=$lastFrameCount, 连续空帧=$emptyFrameCount"
                        )

                        // 连续 30 次空帧 或 3 秒内只收到 0 帧 → 连接可能断了
                        if (emptyFrameCount > 30 || lastFrameCount == 0) {
                            android.util.Log.w(TAG, "⚠️ 连接可能已断开，提示用户刷新")
                            runOnUiThread {
                                if (isConnected) {
                                    updateStatus(
                                        "连接不稳定",
                                        "已连续 $emptyFrameCount 次未收到视频数据\n请点击下方【刷新】按钮重连"
                                    )
                                    tvConnectionStatus.text = "弱信号"
                                    tvConnectionStatus.setTextColor(0xFFFFA000.toInt())
                                }
                            }
                            // 连续空帧超过 100 次，主动断开
                            if (emptyFrameCount > 100) {
                                android.util.Log.e(TAG, "连接超时，主动断开")
                                break
                            }
                        } else {
                            // 恢复正常连接状态提示
                            runOnUiThread {
                                if (isConnected && tvConnectionStatus.text != "已连接") {
                                    tvConnectionStatus.text = "已连接"
                                    tvConnectionStatus.setTextColor(0xFF4CAF50.toInt())
                                }
                            }
                        }
                        lastFrameCount = 0
                    }

                    Thread.sleep(30)
                } catch (e: InterruptedException) {
                    break
                } catch (e: Exception) {
                    android.util.Log.e(TAG, "预览循环异常: ${e.message}")
                    try { Thread.sleep(100) } catch (_: InterruptedException) { break }
                }
            }
        }
        previewThread?.start()
    }

    // ============== LED控制 (接口文档: nativeSetCameraLed) ==============
    private fun setLed(index: Int) {
        currentLedIndex = index
        updateLedUI()
        if (isConnected && cameraId != 0L) {
            Thread {
                try {
                    wifiCamera.setCameraLed(cameraId, index)
                } catch (e: Exception) {}
            }.start()
            val text = if (index == 0) "LED已关闭" else "LED$index 已开启"
            Toast.makeText(this, text, Toast.LENGTH_SHORT).show()
        } else {
            Toast.makeText(this, "摄像头未连接", Toast.LENGTH_SHORT).show()
        }
    }

    // ============== 拍照 (接口文档: nativeGetFrameBuffer) ==============
    private fun takePicture() {
        if (!isConnected || cameraId == 0L) {
            Toast.makeText(this, "摄像头未连接", Toast.LENGTH_SHORT).show()
            return
        }
        Thread {
            val frameData = wifiCamera.getFrameBuffer(cameraId)
            if (frameData != null && frameData.isNotEmpty()) {
                saveImageToDevice(frameData)
                runOnUiThread {
                    Toast.makeText(this@DeviceSkinTestActivity, "拍照成功，已保存到相册", Toast.LENGTH_SHORT).show()
                }
            } else {
                runOnUiThread {
                    Toast.makeText(this@DeviceSkinTestActivity, "拍照失败", Toast.LENGTH_SHORT).show()
                }
            }
        }.start()
    }

    private fun saveImageToDevice(jpegData: ByteArray) {
        try {
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.Q) {
                val values = ContentValues().apply {
                    put(android.provider.MediaStore.Images.Media.DISPLAY_NAME, "SkinTest_${System.currentTimeMillis()}.jpg")
                    put(android.provider.MediaStore.Images.Media.MIME_TYPE, "image/jpeg")
                    put(android.provider.MediaStore.Images.Media.RELATIVE_PATH, "Pictures/Aisia")
                }
                val uri = contentResolver.insert(android.provider.MediaStore.Images.Media.EXTERNAL_CONTENT_URI, values)
                uri?.let { contentResolver.openOutputStream(it)?.use { os -> os.write(jpegData) } }
            } else {
                val dir = java.io.File(
                    android.os.Environment.getExternalStoragePublicDirectory(
                        android.os.Environment.DIRECTORY_PICTURES), "Aisia")
                if (!dir.exists()) dir.mkdirs()
                java.io.File(dir, "SkinTest_${System.currentTimeMillis()}.jpg").outputStream().use { it.write(jpegData) }
            }
        } catch (e: Exception) {
            runOnUiThread {
                Toast.makeText(this@DeviceSkinTestActivity, "保存失败: ${e.message}", Toast.LENGTH_SHORT).show()
            }
        }
    }

    // ============== 水份检测 (接口文档: nativeGetShuifen) ==============
    private fun readMoisture() {
        if (!isConnected || cameraId == 0L) {
            Toast.makeText(this, "摄像头未连接", Toast.LENGTH_SHORT).show()
            return
        }
        Thread {
            val value = wifiCamera.getShuifen(cameraId)
            runOnUiThread {
                if (value >= 0) {
                    tvMoistureValue.text = "$value"
                    Toast.makeText(this@DeviceSkinTestActivity, "水份值: $value", Toast.LENGTH_SHORT).show()
                } else {
                    Toast.makeText(this@DeviceSkinTestActivity, "读取水份失败", Toast.LENGTH_SHORT).show()
                }
            }
        }.start()
    }

    // ============== 设备状态读取 (接口文档: nativeGetShuifen/nativeGetDianliang) ==============
    private fun readDeviceStatus() {
        if (!isConnected || cameraId == 0L) return
        Thread {
            try {
                val shuifen = wifiCamera.getShuifen(cameraId)
                val dianliang = wifiCamera.getDianliang(cameraId)
                runOnUiThread {
                    if (shuifen >= 0) tvMoistureValue.text = "$shuifen"
                    if (dianliang >= 0) {
                        tvBatteryStatus.text = "$dianliang%"
                    }
                }
            } catch (e: Exception) {}
        }.start()
    }

    // ============== 硬件按键检测 (接口文档: nativeHardwareTakePicture) ==============
    private fun startKeyDetection() {
        keyCheckThread?.interrupt()
        val token = cameraGeneration.get()
        val handle = cameraId
        keyCheckThread = Thread {
            while (token == cameraGeneration.get() && isConnected && !Thread.currentThread().isInterrupted) {
                try {
                    if (wifiCamera.hardwareTakePicture(handle)) {
                        runOnUiThread { takePicture() }
                        Thread.sleep(1500)
                    }
                    Thread.sleep(200)
                } catch (e: InterruptedException) {
                    break
                } catch (e: Exception) {}
            }
        }
        keyCheckThread?.start()
    }

    // ============== 刷新/重连 ==============
    private fun refreshDevice() {
        if (isAutoConnecting) {
            Toast.makeText(this, "正在连接中，请稍候...", Toast.LENGTH_SHORT).show()
            return
        }

        // --- 1. 彻底释放旧的摄像头资源 ---
        disconnectCamera()

        // --- 2. 重置 UI ---
        runOnUiThread {
            layoutPreviewHint.visibility = View.VISIBLE
            tvBottomHint.visibility = View.GONE
            layoutLedControl.visibility = View.GONE
            layoutWifiInfo.visibility = View.GONE
            tvMoistureValue.text = "--"
            tvBatteryStatus.text = "--%"
            ivPreview.setImageBitmap(null)
            updateStatus("正在重新连接...", "请确保摄像头已开机且 WiFi 信号良好")
        }

        // --- 3. 稍微等一下，确保 native 库释放完成（关键！很多时候问题就在这里 ---
        val refreshToken = cameraGeneration.get()
        Thread {
            try {
                Thread.sleep(800)
            } catch (_: Exception) {}

            if (leaving || refreshToken != cameraGeneration.get()) return@Thread
            // --- 4. 检查 WiFi 还在不在 CC- 热点上（很多时候 WiFi 自己断了）---
            val ssidNow = cameraWifiManager.getCurrentSsid()
            if (ssidNow == null || !ssidNow.startsWith(HOTSPOT_PREFIX)) {
                android.util.Log.w(TAG, "刷新时发现 WiFi 已不在摄像头热点，重新走 WiFi 连接流程")
                isAutoConnecting = false
                startAutoConnect()  // 走完整的 WiFi 扫描 + 连接流程
                return@Thread
            }

            android.util.Log.i(TAG, "WiFi 仍在 $ssidNow，直接重新连接摄像头")
            isAutoConnecting = false
            connectCamera()  // WiFi 没问题，直接连摄像头
        }.start()
    }

    // ============== 断开连接并退出 ==============
    private fun disconnectAndExit() {
        if (leaving) return
        updateStatus("正在恢复WiFi...", "")
        leaving = true
        lifecycleScope.launch {
            disconnectCamera()
            updateStatus("正在恢复WiFi...", "")
            try {
                val restored = cameraWifiManager.restorePreviousWifi()
                if (restored) {
                    val ssid = cameraWifiManager.getCurrentSsid()
                    Toast.makeText(this@DeviceSkinTestActivity, "WiFi已恢复: ${ssid ?: "未知"}", Toast.LENGTH_SHORT).show()
                } else {
                    Toast.makeText(this@DeviceSkinTestActivity, "请手动切换WiFi", Toast.LENGTH_SHORT).show()
                }
            } catch (e: Exception) {}
            delay(200)
            finish()
            overridePendingTransition(android.R.anim.slide_in_left, android.R.anim.slide_out_right)
        }
    }

    // ============== 释放摄像头资源（更彻底的版本）==============
    private fun disconnectCamera() {
        responseHandler.removeCallbacksAndMessages(null)
        val oldCameraId: Long
        synchronized(cameraStateLock) {
            cameraGeneration.incrementAndGet()
            oldCameraId = cameraId
            cameraId = 0L; isPreviewing = false; isConnected = false
        }
        connectionTask?.cancel(true)
        connectionTask = null
        previewThread?.interrupt(); previewThread = null
        keyCheckThread?.interrupt(); keyCheckThread = null
        // WifiCamera serializes all JNI calls and rejects handles after destruction.
        // Waiting for a native call happens here, never on the UI thread.
        if (oldCameraId != 0L) Thread {
            wifiCamera.stopPreview(oldCameraId)
            wifiCamera.destroyCamera(oldCameraId)
        }.start()
    }

    // ============== 手动连接WiFi对话框 ==============
    private fun showManualWifiDialog() {
        val dialogView = layoutInflater.inflate(R.layout.dialog_manual_wifi, null)
        val dialog = AlertDialog.Builder(this)
            .setView(dialogView)
            .setCancelable(true)
            .create()

        dialogView.findViewById<View>(R.id.btnOpenWifiSettings).setOnClickListener {
            openWifiSettings()
            dialog.dismiss()
        }

        dialogView.findViewById<View>(R.id.btnRetryConnect).setOnClickListener {
            dialog.dismiss()
            refreshDevice()
        }

        dialogView.findViewById<View>(R.id.btnCloseDialog).setOnClickListener {
            dialog.dismiss()
        }

        dialog.window?.setBackgroundDrawableResource(android.R.color.transparent)
        dialog.show()
    }

    private fun openWifiSettings() {
        try {
            val intent = Intent(Settings.ACTION_WIFI_SETTINGS)
            if (intent.resolveActivity(packageManager) != null) {
                startActivity(intent)
            } else {
                val settingsIntent = Intent(Settings.ACTION_SETTINGS)
                startActivity(settingsIntent)
            }
        } catch (e: Exception) {
            Toast.makeText(this, "无法打开WiFi设置，请手动操作", Toast.LENGTH_SHORT).show()
        }
    }
}
