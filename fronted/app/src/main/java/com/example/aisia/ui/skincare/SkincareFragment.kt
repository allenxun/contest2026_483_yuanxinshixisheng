package com.example.aisia.ui.skincare

import android.Manifest
import android.app.Dialog
import android.bluetooth.BluetoothAdapter
import android.bluetooth.BluetoothDevice
import android.bluetooth.BluetoothManager
import android.bluetooth.le.BluetoothLeScanner
import android.bluetooth.le.ScanCallback
import android.bluetooth.le.ScanResult
import android.bluetooth.le.ScanSettings
import android.content.Context
import android.content.pm.PackageManager
import android.graphics.Color
import android.graphics.drawable.ColorDrawable
import android.os.Bundle
import android.os.Handler
import android.os.Looper
import android.util.Log
import android.view.Gravity
import android.view.LayoutInflater
import android.view.View
import android.view.ViewGroup
import android.view.Window
import android.view.WindowManager
import android.view.animation.AlphaAnimation
import android.view.animation.Animation
import android.widget.FrameLayout
import android.widget.ImageView
import android.widget.LinearLayout
import android.widget.TextView
import android.widget.Toast
import androidx.activity.result.contract.ActivityResultContracts
import androidx.core.content.ContextCompat
import androidx.fragment.app.Fragment
import androidx.recyclerview.widget.LinearLayoutManager
import androidx.recyclerview.widget.RecyclerView
import coil.load
import com.example.aisia.R
import com.example.aisia.ble.BleManager
import com.example.aisia.network.HttpHelper
import com.example.aisia.privacy.PrivacyManager
import com.example.aisia.ui.skinhistory.SkinHistoryActivity
import com.google.android.material.bottomsheet.BottomSheetDialog
import com.google.android.material.card.MaterialCardView
import org.json.JSONObject

class SkincareFragment : Fragment(R.layout.fragment_skincare) {

    // ================== 设备卡片配置（对应 JS：deviceList）==================
    private val deviceList = listOf(
        DeviceCardConfig(
            id = 2,
            title = "微晶",
            desc = "精晶焕肤",
            imageUrl = "https://eveaisia.com/face/img/a_wj.png",
            targetName = "EVE AISIA",
            guidePage = "/packageScan/guideW/guideW"
        ),
        DeviceCardConfig(
            id = 1,
            title = "小超炮",
            desc = "精晶焕肤",
            imageUrl = "https://eveaisia.com/face/img/a_xgp.png",
            targetName = "EVE AISIA",
            guidePage = "/packageScan/guideW/guideW"
        ),
        DeviceCardConfig(
            id = 3,
            title = "openVela",
            desc = "智能测肤",
            imageUrl = "",
            imageRes = R.drawable.openvela_board,
            targetName = "openVela",
            guidePage = ""
        ),
        DeviceCardConfig(
            id = 4,
            title = "摄像头",
            desc = "智能肤检",
            imageUrl = "https://eveaisia.com/face/img/a_sxt.png",
            targetName = "",
            guidePage = ""
        )
    )

    private lateinit var cardDevice1: MaterialCardView
    private lateinit var cardDevice2: MaterialCardView
    private lateinit var cardDevice3: MaterialCardView
    private lateinit var cardCamera: MaterialCardView
    private lateinit var imgDevice1: ImageView
    private lateinit var imgDevice2: ImageView
    private lateinit var imgDevice3: ImageView
    private lateinit var imgCamera: ImageView

    // ================== 蓝牙搜索弹窗（BottomSheetDialog）==================
    private var bleDialog: BottomSheetDialog? = null
    private var tvScanStatus: TextView? = null
    private var tvDeviceCount: TextView? = null
    private var rvBleDevices: RecyclerView? = null
    private var tvEmptyState: TextView? = null
    private var tvBleSubtitle: TextView? = null
    private var btnRefreshScan: LinearLayout? = null
    private var deviceListContainer: LinearLayout? = null

    // ================== 连接中弹窗 ==================
    private var connectingDialog: Dialog? = null

    // ================== 蓝牙相关变量 ==================
    private var bluetoothAdapter: BluetoothAdapter? = null
    private var bluetoothScanner: BluetoothLeScanner? = null
    private val discoveredDevices = mutableListOf<ScannedDevice>()
    private var isScanning = false
    private val scanHandler = Handler(Looper.getMainLooper())
    private val scanTimeoutMs = 15000L
    private var deviceListAdapter: DeviceListAdapter? = null

    // ================== 当前选中卡片的信息（对应 JS：currentCardId / currentTargetName / currentGuidePage）==================
    private var currentCardId: Int = 0
    private var currentTargetName: String = ""
    private var currentGuidePage: String = ""
    private var currentCardTitle: String = ""

    // ================== 历史设备列表（对应 JS：oldBleDevices）==================
    private var oldBleDevices: MutableList<String> = mutableListOf()  // 简单存 deviceId 列表

    // ================== 权限请求 ==================
    private val requestPermissionLauncher = registerForActivityResult(
        ActivityResultContracts.RequestMultiplePermissions()
    ) { permissions ->
        val allGranted = permissions.values.all { it }
        if (allGranted) {
            showBleModalAndScan()
        } else {
            Toast.makeText(requireContext(), "需要蓝牙和位置权限才能搜索设备", Toast.LENGTH_SHORT).show()
        }
    }

    private val navigationHandler = Handler(Looper.getMainLooper())
    private var viewEpoch = 0

    override fun onViewCreated(view: View, savedInstanceState: Bundle?) {
        super.onViewCreated(view, savedInstanceState)
        viewEpoch++

        cardDevice1 = view.findViewById(R.id.cardDevice1)
        cardDevice2 = view.findViewById(R.id.cardDevice2)
        cardDevice3 = view.findViewById(R.id.cardDevice3)
        cardCamera = view.findViewById(R.id.cardCamera)
        imgDevice1 = view.findViewById(R.id.imgDevice1)
        imgDevice2 = view.findViewById(R.id.imgDevice2)
        imgDevice3 = view.findViewById(R.id.imgDevice3)
        imgCamera = view.findViewById(R.id.imgCamera)

        // 按比例设置卡片尺寸和间距（适配大屏设备）
        setupAdaptiveLayout(view)
        
        setupCardImages()
        setupCardClicks()
        initBluetooth()
        loadHistoryDevice()
    }
    
    /**
     * 根据屏幕宽度按比例设置卡片容器的 padding、卡片间距和卡片内部 padding
     * 参考小程序设计稿（750rpx 宽度基准）：
     * - 容器左右 padding: 38rpx ≈ 5.07%
     * - 卡片间距: 32rpx ≈ 4.27%
     * - 卡片内文字左 padding: 80rpx ≈ 10.67%
     * - 卡片内文字右 padding: 32rpx ≈ 4.27%
     */
    private fun setupAdaptiveLayout(view: View) {
        val displayMetrics = resources.displayMetrics
        val screenWidthPx = displayMetrics.widthPixels.toFloat()
        
        // 按比例计算各尺寸
        val containerPaddingHorizontal = (screenWidthPx * 0.0507f).toInt()  // 容器左右 padding
        val cardMarginBottom = (screenWidthPx * 0.0427f).toInt()          // 卡片间距
        val cardPaddingStart = (screenWidthPx * 0.1067f).toInt()          // 卡片内文字左 padding
        val cardPaddingEnd = (screenWidthPx * 0.0427f).toInt()            // 卡片内文字右 padding
        
        // 设置卡片容器的 padding
        val cardContainer = view.findViewById<LinearLayout>(R.id.cardContainer)
        cardContainer?.setPadding(containerPaddingHorizontal, 0, containerPaddingHorizontal, 0)
        
        // 设置每张卡片的 margin 和内部 padding
        val cards = listOf(cardDevice1, cardDevice2, cardDevice3, cardCamera)
        cards.forEachIndexed { index, card ->
            // 设置卡片 marginBottom（最后一张卡片不需要底部间距）
            val layoutParams = card.layoutParams as LinearLayout.LayoutParams
            if (index < cards.size - 1) {
                layoutParams.bottomMargin = cardMarginBottom
            } else {
                layoutParams.bottomMargin = 0
            }
            card.layoutParams = layoutParams
            
            // 设置卡片内部文字区域的 padding
            val textContainer = card.getChildAt(0)?.let { 
                (it as? FrameLayout)?.getChildAt(1) as? LinearLayout 
            }
            textContainer?.setPadding(cardPaddingStart, 0, cardPaddingEnd, 0)
        }

        // openVela 卡片图片靠右：宽度约占卡片 55%，fitCenter 完整显示开发板，
        // 左侧浅色区域留给卡片文字，与设计稿“左文右图”风格一致
        val cardWidthPx = screenWidthPx - 2 * containerPaddingHorizontal
        val img3Params = imgDevice3.layoutParams as FrameLayout.LayoutParams
        img3Params.width = (cardWidthPx * 0.55f).toInt()
        img3Params.gravity = android.view.Gravity.END or android.view.Gravity.CENTER_VERTICAL
        imgDevice3.layoutParams = img3Params
    }

    // ================== 加载历史设备（对应 JS：loadHistoryDevice）==================
    private fun loadHistoryDevice() {
        // TODO: 如果有后端API，在这里调用 getMyDevice() 获取已保存的设备历史
        // 暂时用 SharedPreferences 简单保存
        val prefs = requireContext().getSharedPreferences("skin_device_history", Context.MODE_PRIVATE)
        val history = prefs.getStringSet("connected_devices", emptySet())
        oldBleDevices.clear()
        oldBleDevices.addAll(history ?: emptyList())
    }

    /**
     * 保存设备到服务器（对应小程序 myDevice API）
     * POST /api/my-device  body: { device_sn, device_name, device_type }
     * 返回: { id: "数据库记录ID" }
     */
    private fun saveDeviceToServer(
        deviceSn: String,
        deviceName: String,
        deviceType: String,
        onSuccess: (serverId: String) -> Unit,
        onFailure: () -> Unit
    ) {
        HttpHelper.post(
            path = "/api/my-device",
            params = mapOf(
                "device_sn" to deviceSn,
                "device_name" to deviceName,
                "device_type" to deviceType
            ),
            onSuccess = { responseBody ->
                activity?.runOnUiThread {
                    if (!isAdded || view == null) return@runOnUiThread
                    try {
                        val json = JSONObject(responseBody)
                        Log.d("SkincareFragment", "保存设备成功")
                        // 兼容多种返回格式：
                        // 1. { "id": "123" }
                        // 2. { "data": { "id": "123" } }
                        // 3. { "code": 0, "data": { "id": "123" } }
                        var serverId = json.optString("id", "")
                        if (serverId.isEmpty()) {
                            val dataObj = json.optJSONObject("data")
                            if (dataObj != null) {
                                serverId = dataObj.optString("id", "")
                            }
                        }
                        if (serverId.isNotEmpty()) {
                            Log.d("SkincareFragment", "保存设备成功, id=$serverId")
                            onSuccess(serverId)
                        } else {
                            Log.w("SkincareFragment", "保存设备返回无 id")
                            onFailure()
                        }
                    } catch (e: Exception) {
                        Log.e("SkincareFragment", "解析保存设备响应失败", e)
                        onFailure()
                    }
                }
            },
            onFailure = { code, errorMsg ->
                activity?.runOnUiThread {
                    if (!isAdded || view == null) return@runOnUiThread
                    Log.e("SkincareFragment", "保存设备失败: $code $errorMsg")
                    onFailure()
                }
            }
        )
    }

    /**
     * 获取历史设备列表（对应小程序 getMyDevice API）
     * GET /api/my-device?page=1&page_size=99
     * 返回: { items: [{ id, device_sn, device_name, ... }] }
     */
    private fun loadHistoryDeviceFromServer(
        onSuccess: (List<HistoryDevice>) -> Unit,
        onFailure: () -> Unit
    ) {
        HttpHelper.get(
            path = "/api/my-device?page=1&page_size=99",
            onSuccess = { responseBody ->
                activity?.runOnUiThread {
                    if (!isAdded || view == null) return@runOnUiThread
                    try {
                        val json = JSONObject(responseBody)
                        val items = json.optJSONArray("items")
                        val devices = mutableListOf<HistoryDevice>()
                        if (items != null) {
                            for (i in 0 until items.length()) {
                                val obj = items.getJSONObject(i)
                                devices.add(HistoryDevice(
                                    id = obj.optString("id", ""),
                                    deviceSn = obj.optString("device_sn", ""),
                                    deviceName = obj.optString("device_name", "未知设备")
                                ))
                            }
                        }
                        onSuccess(devices)
                    } catch (e: Exception) {
                        Log.e("SkincareFragment", "解析历史设备失败", e)
                        onFailure()
                    }
                }
            },
            onFailure = { code, errorMsg ->
                activity?.runOnUiThread {
                    if (!isAdded || view == null) return@runOnUiThread
                    Log.e("SkincareFragment", "获取历史设备失败: $code $errorMsg")
                    onFailure()
                }
            }
        )
    }

    private fun setupCardImages() {
        // 创建自适应背景（装饰圆按百分比定位，大屏不变形）
        val cornerRadius = 16 * resources.displayMetrics.density  // 16dp 转 px
        
        val bg1 = AdaptiveCardBackground(
            startColor = 0xFF667EEA.toInt(),
            centerColor = 0xFF764BA2.toInt(),
            endColor = 0xFFF093FB.toInt(),
            cornerRadius = cornerRadius
        )
        val bg2 = AdaptiveCardBackground(
            startColor = 0xFFF093FB.toInt(),
            centerColor = 0xFFF5576C.toInt(),
            endColor = 0xFFFF9A9E.toInt(),
            cornerRadius = cornerRadius
        )

        imgDevice1.load(deviceList[0].imageUrl) {
            crossfade(true)
            placeholder(bg1)
            error(bg1)
        }
        imgDevice2.load(deviceList[1].imageUrl) {
            crossfade(true)
            placeholder(bg2)
            error(bg2)
        }
        val cfg3 = deviceList[2]
        // openVela 卡片：与其他设备卡片一致的浅色底（图片靠右摆放，左侧留文字区）
        val openVelaBgColor = 0xFFF5FBFB.toInt()
        (cardDevice3.getChildAt(0) as? FrameLayout)?.setBackgroundColor(openVelaBgColor)
        if (cfg3.imageRes != 0) {
            // openVela 卡片使用本地图片资源：直接设置，不走 Coil，
            // 避免 Coil 默认 Scale.FILL 在解码阶段就按卡片比例裁切图片，
            // 由 ImageView 的 scaleType=fitCenter 保证整块开发板完整显示
            imgDevice3.setImageResource(cfg3.imageRes)
        } else {
            imgDevice3.load(cfg3.imageUrl) {
                crossfade(true)
                scale(coil.size.Scale.FIT)
                placeholder(ColorDrawable(openVelaBgColor))
                error(ColorDrawable(openVelaBgColor))
            }
        }
    }

    // ================== 卡片点击 → 打开蓝牙弹窗（对应 JS：onCardTap）==================
    private fun setupCardClicks() {
        cardDevice1.setOnClickListener {
            val card = deviceList[0]
            selectedDevice(card)
            checkPermissionsAndScan()
        }
        cardDevice2.setOnClickListener {
            val card = deviceList[1]
            selectedDevice(card)
            checkPermissionsAndScan()
        }
        // openVela 卡片点击 → 跳转 openVela 蓝牙连接页（搜索→连接→连接WIFI）
        cardDevice3.setOnClickListener {
            val intent = android.content.Intent(
                requireContext(),
                com.example.aisia.ui.device.OpenVelaConnectActivity::class.java
            )
            startActivity(intent)
        }
        // 摄像头卡片点击 → 跳转到WiFi摄像头皮肤测试页面
        cardCamera.setOnClickListener {
            val intent = android.content.Intent(requireContext(), com.example.aisia.ui.device.DeviceSkinTestActivity::class.java)
            startActivity(intent)
        }
    }

    // 选中设备：记录当前卡片的 targetName、guidePage
    private fun selectedDevice(card: DeviceCardConfig) {
        currentCardId = card.id
        currentTargetName = card.targetName
        currentGuidePage = card.guidePage
        currentCardTitle = card.title
    }

    private fun initBluetooth() {
        val bluetoothManager = requireContext().getSystemService(Context.BLUETOOTH_SERVICE) as BluetoothManager
        bluetoothAdapter = bluetoothManager.adapter
        bluetoothScanner = bluetoothAdapter?.bluetoothLeScanner
    }

    private fun checkPermissionsAndScan() {
        // 合规要求：用户同意隐私政策后才能申请蓝牙/位置权限
        PrivacyManager.ensureAgreed(requireActivity()) {
            val requiredPermissions = mutableListOf<String>()

            if (android.os.Build.VERSION.SDK_INT >= android.os.Build.VERSION_CODES.S) {
                requiredPermissions.add(Manifest.permission.BLUETOOTH_SCAN)
                requiredPermissions.add(Manifest.permission.BLUETOOTH_CONNECT)
            }
            if (android.os.Build.VERSION.SDK_INT >= android.os.Build.VERSION_CODES.M) {
                requiredPermissions.add(Manifest.permission.ACCESS_FINE_LOCATION)
            }

            val notGranted = requiredPermissions.filter {
                ContextCompat.checkSelfPermission(requireContext(), it) != PackageManager.PERMISSION_GRANTED
            }

            if (notGranted.isEmpty()) {
                showBleModalAndScan()
            } else {
                requestPermissionLauncher.launch(notGranted.toTypedArray())
            }
        }
    }

    // ================== 打开弹窗并扫描（对应 JS：onCardTap 打开 t-popup + setTimeout 扫描）==================
    private fun showBleModalAndScan() {
        val ctx = requireContext()
        val dialogView = LayoutInflater.from(ctx).inflate(R.layout.dialog_device_list, null)

        tvScanStatus = dialogView.findViewById(R.id.tvScanStatus)
        tvDeviceCount = dialogView.findViewById(R.id.tvDeviceCount)
        rvBleDevices = dialogView.findViewById(R.id.rvBleDevices)
        tvEmptyState = dialogView.findViewById(R.id.tvEmptyState)
        tvBleSubtitle = dialogView.findViewById(R.id.tvBleSubtitle)
        btnRefreshScan = dialogView.findViewById(R.id.btnRefreshScan)
        deviceListContainer = dialogView.findViewById(R.id.deviceListContainer)

        val btnCloseBle = dialogView.findViewById<TextView>(R.id.btnCloseBle)

        // 目标设备：显示当前卡片的 targetName（对应 JS：currentTargetName）
        tvBleSubtitle?.text = "目标设备：$currentTargetName"

        // 列表初始化
        rvBleDevices?.layoutManager = LinearLayoutManager(ctx)
        discoveredDevices.clear()
        deviceListAdapter = DeviceListAdapter(discoveredDevices) { device ->
            stopBleScan()
            bleDialog?.dismiss()
            connectToDevice(device)
        }
        rvBleDevices?.adapter = deviceListAdapter

        // 关闭按钮
        btnCloseBle.setOnClickListener {
            stopBleScan()
            bleDialog?.dismiss()
        }

        // 刷新扫描（对应 JS：onRescan）
        btnRefreshScan?.setOnClickListener {
            stopBleScan()
            deviceListAdapter?.clear()
            deviceListContainer?.visibility = View.GONE
            tvEmptyState?.visibility = View.VISIBLE
            tvEmptyState?.text = "正在扫描，请稍候..."
            tvDeviceCount?.text = "已找到 0 个设备…"
            tvScanStatus?.text = "正在搜索附近设备"
            startBleScan()
        }

        // 初始化状态
        deviceListContainer?.visibility = View.GONE
        tvEmptyState?.visibility = View.VISIBLE
        tvEmptyState?.text = "正在扫描，请稍候..."
        tvDeviceCount?.text = "已找到 0 个设备…"

        // 创建 BottomSheetDialog（铺满底部）
        bleDialog = object : BottomSheetDialog(ctx) {
            override fun onStart() {
                super.onStart()
                window?.setLayout(
                    ViewGroup.LayoutParams.MATCH_PARENT,
                    ViewGroup.LayoutParams.WRAP_CONTENT
                )
                val bottomSheet = findViewById<FrameLayout>(com.google.android.material.R.id.design_bottom_sheet)
                bottomSheet?.setBackgroundColor(Color.TRANSPARENT)
                bottomSheet?.setPadding(0, 0, 0, 0)
                if (bottomSheet != null) {
                    val behavior = com.google.android.material.bottomsheet.BottomSheetBehavior.from(bottomSheet)
                    behavior.state = com.google.android.material.bottomsheet.BottomSheetBehavior.STATE_EXPANDED
                    behavior.skipCollapsed = true
                    behavior.isHideable = false
                    behavior.expandedOffset = 0
                    behavior.peekHeight = com.google.android.material.bottomsheet.BottomSheetBehavior.PEEK_HEIGHT_AUTO
                    behavior.setGestureInsetBottomIgnored(true)
                }
            }
        }.apply {
            setContentView(dialogView)
            setCancelable(true)
            setOnDismissListener { stopBleScan() }
        }
        bleDialog?.show()

        // 弹窗打开后稍等一下再开始扫描（避免动画冲突，对应 JS：setTimeout 250ms）
        scanHandler.postDelayed({
            startBleScan()
        }, 250)
    }

    private fun startBleScan() {
        if (bluetoothAdapter?.isEnabled != true) {
            Toast.makeText(requireContext(), "请先开启蓝牙", Toast.LENGTH_SHORT).show()
            tvEmptyState?.text = "请先开启蓝牙"
            return
        }

        if (isScanning) return

        isScanning = true
        tvScanStatus?.text = "正在搜索附近设备"

        try {
            val scanSettings = ScanSettings.Builder()
                .setScanMode(ScanSettings.SCAN_MODE_LOW_LATENCY)
                .build()
            bluetoothScanner?.startScan(null, scanSettings, bleScanCallback)
            // 15秒自动停止扫描（对应 JS：scanTimeoutMs）
            scanHandler.postDelayed({
                stopBleScan()
            }, scanTimeoutMs)
        } catch (e: SecurityException) {
            Toast.makeText(requireContext(), "蓝牙扫描权限被拒绝", Toast.LENGTH_SHORT).show()
            isScanning = false
            tvEmptyState?.text = "扫描权限被拒绝"
        }
    }

    private fun stopBleScan() {
        if (!isScanning) return
        try {
            bluetoothScanner?.stopScan(bleScanCallback)
        } catch (e: SecurityException) {
            // 忽略
        }
        isScanning = false
        tvScanStatus?.text = "搜索已完成"

        // 扫描完成但设备列表为空 → 显示空状态提示
        if (discoveredDevices.isEmpty()) {
            tvEmptyState?.text = "未搜索到匹配设备，请检查设备是否开启"
            tvEmptyState?.visibility = View.VISIBLE
            deviceListContainer?.visibility = View.GONE
        }
    }

    // ================== 扫描回调：关键过滤逻辑（对应 JS：_addDeviceToList 的 includes(currentTargetName) 判断）==================
    private val bleScanCallback = object : ScanCallback() {
        override fun onScanResult(callbackType: Int, result: ScanResult) {
            val device = result.device
            val devName = try {
                device.name ?: ""
            } catch (e: SecurityException) {
                ""
            }

            // ====== ⭐ 核心过滤：设备名必须包含 currentTargetName 才加入列表 ⭐ ======
            // 对应 JS: if (devName && devName.includes(this.data.currentTargetName)) { ... }
            if (devName.isNotBlank() && devName.contains(currentTargetName, ignoreCase = true)) {
                val scanned = ScannedDevice(
                    name = devName,
                    deviceId = device.address,
                    rssi = result.rssi,
                    rawDevice = device
                )

                // 去重并添加（最多找到 5 个后停止扫描）
                if (discoveredDevices.none { it.deviceId == scanned.deviceId }) {
                    discoveredDevices.add(scanned)

                    activity?.runOnUiThread {
                    if (!isAdded || view == null) return@runOnUiThread
                        deviceListAdapter?.notifyDataSetChanged()
                        tvDeviceCount?.text = "已找到 ${discoveredDevices.size} 个设备…"

                        if (discoveredDevices.isNotEmpty()) {
                            deviceListContainer?.visibility = View.VISIBLE
                            tvEmptyState?.visibility = View.GONE
                        }

                        // 找到 5 个后停止扫描（对应 JS：_addDeviceToList 的判断）
                        if (discoveredDevices.size >= 5) {
                            stopBleScan()
                        }
                    }
                }
            }
        }

        override fun onScanFailed(errorCode: Int) {
            activity?.runOnUiThread {
                    if (!isAdded || view == null) return@runOnUiThread
                Toast.makeText(requireContext(), "蓝牙扫描失败: $errorCode", Toast.LENGTH_SHORT).show()
                isScanning = false
                tvEmptyState?.text = "扫描失败，请重试"
                tvEmptyState?.visibility = View.VISIBLE
            }
        }
    }

    // ================== 连接设备（对应 JS：onConnectDevice）==================
    private fun connectToDevice(device: ScannedDevice) {
        val ctx = requireContext()

        // 1. 显示连接中弹窗
        showConnectingDialog(ctx)

        // 2. 发起真正的 BLE GATT 连接（BleManager.connectDevice: 连接 → 发现服务 → 收集可写特征值）
        val rawDevice = device.rawDevice ?: run {
            dismissConnectingDialog()
            Toast.makeText(ctx, "设备信息无效", Toast.LENGTH_SHORT).show()
            return
        }

        // 先停止扫描，避免扫描占用资源导致连接失败
        stopBleScan()

        val connectEpoch = viewEpoch
        BleManager.connectDevice(ctx, rawDevice) { success, err ->
            if (connectEpoch != viewEpoch || !isAdded || view == null) return@connectDevice
            if (success) {
                Log.d("SkincareFragment", "BLE 连接成功: ${device.deviceId}")
                onConnectSuccess(device)
            } else {
                dismissConnectingDialog()
                Log.w("SkincareFragment", "BLE 连接失败: $err")
                Toast.makeText(
                    ctx,
                    "蓝牙连接失败: ${err ?: "未知错误"}",
                    Toast.LENGTH_LONG
                ).show()
                // 失败后重试扫描
                navigationHandler.postDelayed({
                    showBleModalAndScan()
                }, 500)
            }
        }
    }

    // ================== 连接成功：保存 → 跳转（对应 JS：onConnectDevice success 回调）==================
    private fun onConnectSuccess(device: ScannedDevice) {
        if (!isAdded || view == null) return
        val flowEpoch = viewEpoch
        dismissConnectingDialog()
        Toast.makeText(requireContext(), "$currentCardTitle 设备连接成功", Toast.LENGTH_SHORT).show()

        // Step 1: 保存设备到服务器 POST /api/my-device，获取返回的 serverId
        saveDeviceToServer(
            deviceSn = device.deviceId,
            deviceName = device.name,
            deviceType = currentCardTitle,
            onSuccess = saved@{ serverId ->
                if (flowEpoch != viewEpoch || !isAdded || view == null) return@saved
                Log.d("SkincareFragment", "保存设备成功, serverId=$serverId, deviceId=${device.deviceId}")
                Toast.makeText(requireContext(), "🔍 onConnectSuccess: id=$serverId", Toast.LENGTH_LONG).show()
                // 直接使用 saveDeviceToServer 返回的 serverId 作为 device_id
                navigationHandler.postDelayed({
                    if (flowEpoch == viewEpoch) navigateToSkinHistory(serverId, device.deviceId, device.name)
                }, 300)
            },
            onFailure = {
                Log.w("SkincareFragment", "保存设备失败，尝试从历史获取 device_id")
                // 保存失败，尝试从历史列表获取 device_id
                loadHistoryDeviceFromServer(
                    onSuccess = history@{ historyDevices ->
                        if (flowEpoch != viewEpoch || !isAdded || view == null) return@history
                        val id = if (historyDevices.isNotEmpty()) historyDevices[0].id else ""
                        Log.d("SkincareFragment", "从历史获取 device_id=$id")
                        navigationHandler.postDelayed({
                            if (flowEpoch == viewEpoch) navigateToSkinHistory(id, device.deviceId, device.name)
                        }, 300)
                    },
                    onFailure = {
                        Log.w("SkincareFragment", "获取历史也失败，device_id 为空")
                        navigationHandler.postDelayed({
                            if (flowEpoch == viewEpoch) navigateToSkinHistory("", device.deviceId, device.name)
                        }, 300)
                    }
                )
            }
        )
    }

    /**
     * 跳转 SkinHistoryActivity，传递 id（数据库记录ID）和 deviceId（device_sn/蓝牙MAC）
     */
    private fun navigateToSkinHistory(id: String, deviceId: String, deviceName: String) {
        if (!isAdded || view == null || activity?.isFinishing == true) return
        val intent = android.content.Intent(requireContext(), SkinHistoryActivity::class.java).apply {
            putExtra("id", id)
            putExtra("deviceId", deviceId)
            putExtra("deviceName", deviceName)
            putExtra("deviceType", currentCardTitle)
        }
        startActivity(intent)
    }

    // ================== 连接中弹窗（对应 JS：connecting-mask + connecting-dialog）==================
    private fun showConnectingDialog(ctx: Context) {
        connectingDialog = Dialog(ctx).apply {
            requestWindowFeature(Window.FEATURE_NO_TITLE)
            setContentView(R.layout.dialog_connecting)
            setCancelable(false)

            window?.apply {
                setBackgroundDrawable(ColorDrawable(Color.TRANSPARENT))
                setLayout(WindowManager.LayoutParams.MATCH_PARENT, WindowManager.LayoutParams.MATCH_PARENT)
                setGravity(Gravity.CENTER)
            }
        }

        // 波纹呼吸动画（对应 JS：wavePulse @keyframes）
        val waveLeft1 = connectingDialog?.findViewById<View>(R.id.waveLeft1)
        val waveLeft2 = connectingDialog?.findViewById<View>(R.id.waveLeft2)
        val waveRight1 = connectingDialog?.findViewById<View>(R.id.waveRight1)
        val waveRight2 = connectingDialog?.findViewById<View>(R.id.waveRight2)

        listOf(waveLeft1, waveLeft2, waveRight1, waveRight2).forEachIndexed { idx, v ->
            v?.startAnimation(createPulseAnimation(idx * 200L))
        }

        connectingDialog?.show()
    }

    private fun createPulseAnimation(delayMs: Long): Animation {
        return AlphaAnimation(0.5f, 1.0f).apply {
            duration = 1400
            startOffset = delayMs
            repeatCount = Animation.INFINITE
            repeatMode = Animation.REVERSE
        }
    }

    private fun dismissConnectingDialog() {
        connectingDialog?.dismiss()
        connectingDialog = null
    }

    override fun onDestroyView() {
        viewEpoch++
        navigationHandler.removeCallbacksAndMessages(null)
        super.onDestroyView()
        stopBleScan()
        bleDialog?.dismiss()
        bleDialog = null
        connectingDialog?.dismiss()
        connectingDialog = null
        // 这里不主动断开 BLE，因为后续页面（WorkActivity）还要用
        // 如果用户不进下一步而是直接退出 App，Application 退出时系统会自动断
    }
}

/**
 * 设备卡片配置（对应 JS：deviceList 数组项）
 */
data class DeviceCardConfig(
    val id: Int,
    val title: String,
    val desc: String,
    val imageUrl: String,
    val imageRes: Int = 0,    // 本地图片资源ID（不为 0 时优先于 imageUrl）
    val targetName: String,   // 蓝牙设备名过滤关键字（如 "EVE AISIA"）
    val guidePage: String     // 历史为空时跳转的指南页
)

/**
 * 历史设备（对应小程序 oldBleDevices 中的 item）
 * @param id 数据库记录ID（API 返回的 id 字段）
 * @param deviceSn 设备序列号/蓝牙MAC地址（device_sn 字段）
 * @param deviceName 设备名称（device_name 字段）
 */
data class HistoryDevice(
    val id: String,
    val deviceSn: String,
    val deviceName: String
)
