package com.example.aisia.ui.device

import android.Manifest
import android.annotation.SuppressLint
import android.app.Dialog
import android.bluetooth.BluetoothAdapter
import android.bluetooth.BluetoothDevice
import android.bluetooth.BluetoothManager
import android.bluetooth.le.BluetoothLeScanner
import android.bluetooth.le.ScanCallback
import android.bluetooth.le.ScanResult
import android.bluetooth.le.ScanSettings
import android.content.Context
import android.content.Intent
import android.content.pm.PackageManager
import android.graphics.Color
import android.graphics.drawable.ColorDrawable
import android.os.Build
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
import android.widget.EditText
import android.widget.ImageView
import android.widget.LinearLayout
import android.widget.TextView
import android.widget.Toast
import androidx.activity.result.contract.ActivityResultContracts
import androidx.appcompat.app.AlertDialog
import androidx.appcompat.app.AppCompatActivity
import androidx.core.content.ContextCompat
import androidx.recyclerview.widget.LinearLayoutManager
import androidx.recyclerview.widget.RecyclerView
import com.example.aisia.R
import com.example.aisia.ble.BleManager
import com.example.aisia.privacy.PrivacyManager
import com.example.aisia.ble.k7.K7Protocol
import com.example.aisia.ble.k7.K7ProvisioningClient
import org.json.JSONArray
import org.json.JSONObject

/**
 * openVela 设备连接页：
 * 1. 搜索名称包含 "VelaVision" 的蓝牙设备
 * 2. 点击设备发起 BLE 连接
 * 3. 通过 BLE 获取 Wi-Fi 列表、提交凭据并等待设备确认。
 */
class OpenVelaConnectActivity : AppCompatActivity() {

    companion object {
        private const val TAG = "OpenVelaConnect"
        private const val TARGET_NAME = "VelaVision"   // 蓝牙名称过滤关键字（忽略大小写）
        private const val SCAN_TIMEOUT_MS = 30000L
    }

    private lateinit var tvScanStatus: TextView
    private lateinit var tvDeviceCount: TextView
    private lateinit var rvDevices: RecyclerView
    private lateinit var deviceListContainer: LinearLayout
    private lateinit var tvEmptyState: TextView
    private lateinit var btnRefreshScan: LinearLayout
    private lateinit var layoutConnected: LinearLayout
    private lateinit var tvConnectedName: TextView
    private lateinit var btnConnectWifi: LinearLayout
    private lateinit var wifiSection: LinearLayout
    private lateinit var tvWifiStatus: TextView
    private lateinit var tvWifiLoading: TextView
    private lateinit var rvWifiList: RecyclerView
    private lateinit var layoutWifiSuccess: LinearLayout
    private lateinit var tvWifiSuccessText: TextView

    // ===== WIFI 流程状态 =====
    private val wifiItems = mutableListOf<WifiItem>()
    private val wifiAdapter = WifiAdapter(wifiItems) { item -> showWifiPasswordDialog(item) }
    private lateinit var client: K7ProvisioningClient
    private var selectedDeviceAddress = ""
    private var selectedDeviceName = TARGET_NAME
    private val wifiHandler = Handler(Looper.getMainLooper())
    private var connectingSsid: String? = null
    private var requestingWifi = false
    private var completed = false
    private lateinit var queryWifiButton: android.widget.Button
    private var passwordDialog: AlertDialog? = null

    private fun setWifiBusy(busy: Boolean) {
        if (::queryWifiButton.isInitialized) queryWifiButton.isEnabled = !busy && client.ready
        val canProvision = !::client.isInitialized || client.canConnect
        btnConnectWifi.isEnabled = !busy && canProvision
        btnConnectWifi.alpha = if (busy || !canProvision) 0.5f else 1f
    }

    data class WifiItem(val ap: K7Protocol.AccessPoint) {
        val ssid get() = ap.ssid
        val rssi get() = ap.rssi
    }

    private var bluetoothAdapter: BluetoothAdapter? = null
    private var bleScanner: BluetoothLeScanner? = null
    private val discoveredDevices = mutableListOf<BluetoothDevice>()
    private var isScanning = false
    private var scanGeneration = 0
    private var scanCallback: ScanCallback? = null
    private val scanHandler = Handler(Looper.getMainLooper())
    private var connectingDialog: Dialog? = null
    private lateinit var scanProgress: android.widget.ProgressBar
    private var scanStartedAt = 0L
    private val nearbyAddresses = mutableSetOf<String>()
    private var scanSettingsAction: Intent? = null

    private fun refreshLabel(text: String) {
        (0 until btnRefreshScan.childCount).map { btnRefreshScan.getChildAt(it) }
            .filterIsInstance<TextView>().firstOrNull()?.text = text
        btnRefreshScan.contentDescription = text
    }

    private fun showScanProblem(title: String, detail: String, settings: Intent? = null) {
        stopBleScan()
        tvScanStatus.text = title
        tvScanStatus.setTextColor(Color.rgb(174, 61, 61))
        tvDeviceCount.text = "搜索未进行"
        deviceListContainer.visibility = View.GONE
        tvEmptyState.visibility = View.VISIBLE
        tvEmptyState.text = detail
        scanSettingsAction = settings
        refreshLabel(if (settings == null) "重试" else "去设置")
    }

    private fun locationReady(): Boolean {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.S) return true
        val manager = getSystemService(Context.LOCATION_SERVICE) as android.location.LocationManager
        return androidx.core.location.LocationManagerCompat.isLocationEnabled(manager)
    }

    @SuppressLint("MissingPermission")
    private fun showScanProgress(token: Int) {
        if (token != scanGeneration || !isScanning || isFinishing || isDestroyed) return
        try {
            if (bluetoothAdapter?.isEnabled != true) {
                showScanProblem("蓝牙已关闭", "开启手机蓝牙后，点击重试"); return
            }
            if (!locationReady()) {
                showScanProblem("请开启位置信息", "此系统搜索蓝牙需要开启定位。开启后返回并点击刷新。",
                    Intent(android.provider.Settings.ACTION_LOCATION_SOURCE_SETTINGS)); return
            }
        } catch (_: SecurityException) {
            showScanProblem("蓝牙权限不可用", "请在应用设置中允许蓝牙和位置信息权限。",
                Intent(android.provider.Settings.ACTION_APPLICATION_DETAILS_SETTINGS, android.net.Uri.parse("package:$packageName")))
            return
        }
        val seconds = (android.os.SystemClock.elapsedRealtime() - scanStartedAt) / 1000
        tvScanStatus.text = "正在搜索 VelaVision…"
        tvDeviceCount.text = "已找到 ${discoveredDevices.size} 台 · 已搜索 ${seconds} 秒"
        if (discoveredDevices.isEmpty()) {
            tvEmptyState.text = if (nearbyAddresses.isEmpty())
                "正在等待附近的蓝牙信号…\n请保持页面亮屏，并将手机靠近设备"
            else "已收到附近蓝牙信号，正在查找 VelaVision…\n请确认设备已开启，且未被其他客户端连接"
        }
        scanHandler.postDelayed({ showScanProgress(token) }, 1000)
    }

    private val deviceAdapter = OpenVelaDeviceAdapter(discoveredDevices) { device ->
        connectDevice(device)
    }

    // 蓝牙开启请求
    private val enableBtLauncher = registerForActivityResult(
        ActivityResultContracts.StartActivityForResult()
    ) { result ->
        if (result.resultCode == RESULT_OK) {
            bleScanner = bluetoothAdapter?.bluetoothLeScanner
            resetAndScan()
        } else {
            showScanProblem("蓝牙未开启", "请开启蓝牙后点击重试")
        }
    }

    // 权限请求
    private val permissionLauncher = registerForActivityResult(
        ActivityResultContracts.RequestMultiplePermissions()
    ) { permissions ->
        if (permissions.values.all { it }) {
            initBluetooth()
        } else {
            showScanProblem("缺少搜索权限", "请允许蓝牙和位置信息权限，返回后点击刷新。",
                Intent(android.provider.Settings.ACTION_APPLICATION_DETAILS_SETTINGS, android.net.Uri.parse("package:$packageName")))
        }
    }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContentView(R.layout.activity_openvela_connect)

        tvScanStatus = findViewById(R.id.tvScanStatus)
        tvDeviceCount = findViewById(R.id.tvDeviceCount)
        rvDevices = findViewById(R.id.rvDevices)
        deviceListContainer = findViewById(R.id.deviceListContainer)
        tvEmptyState = findViewById(R.id.tvEmptyState)
        btnRefreshScan = findViewById(R.id.btnRefreshScan)
        layoutConnected = findViewById(R.id.layoutConnected)
        tvConnectedName = findViewById(R.id.tvConnectedName)
        btnConnectWifi = findViewById(R.id.btnConnectWifi)
        wifiSection = findViewById(R.id.wifiSection)
        tvWifiStatus = findViewById(R.id.tvWifiStatus)
        tvWifiLoading = findViewById(R.id.tvWifiLoading)
        rvWifiList = findViewById(R.id.rvWifiList)
        layoutWifiSuccess = findViewById(R.id.layoutWifiSuccess)
        tvWifiSuccessText = findViewById(R.id.tvWifiSuccessText)

        findViewById<View>(R.id.btnBack).setOnClickListener { finish() }

        rvDevices.layoutManager = LinearLayoutManager(this)
        rvDevices.adapter = deviceAdapter
        rvWifiList.layoutManager = LinearLayoutManager(this)
        rvWifiList.adapter = wifiAdapter

        scanProgress = android.widget.ProgressBar(this, null, android.R.attr.progressBarStyleHorizontal).apply {
            isIndeterminate = true
            indeterminateTintList = android.content.res.ColorStateList.valueOf(Color.rgb(58, 109, 240))
            visibility = View.GONE
        }
        (tvScanStatus.parent as LinearLayout).addView(scanProgress,
            LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, (3 * resources.displayMetrics.density).toInt()).apply {
                topMargin = (6 * resources.displayMetrics.density).toInt()
            })
        tvScanStatus.accessibilityLiveRegion = View.ACCESSIBILITY_LIVE_REGION_POLITE
        tvEmptyState.setTextColor(Color.rgb(82, 102, 126))
        btnRefreshScan.setOnClickListener {
            val settings = scanSettingsAction
            when {
                settings != null -> {
                    scanSettingsAction = null; refreshLabel("刷新")
                    try { startActivity(settings) } catch (_: Exception) {
                        showScanProblem("无法打开设置", "请手动在系统设置中开启所需权限后重试")
                    }
                }
                isScanning -> {
                    stopBleScan()
                    tvScanStatus.text = "搜索已停止"
                    tvDeviceCount.text = "已找到 ${discoveredDevices.size} 台设备"
                    if (discoveredDevices.isEmpty()) tvEmptyState.text = "点击刷新可重新搜索"
                }
                else -> checkPermissionsAndScan()
            }
        }
        btnConnectWifi.setOnClickListener { requestWifiList() }

        client = K7ProvisioningClient(this, object : K7ProvisioningClient.Listener {
            override fun onReady(capabilities: K7Protocol.Capabilities) {
                if (isFinishing || isDestroyed) return
                dismissConnectingDialog()
                tvScanStatus.text = "蓝牙已就绪"
                tvConnectedName.text = "已连接：$selectedDeviceName"
                deviceListContainer.visibility = View.GONE
                tvEmptyState.visibility = View.GONE
                layoutConnected.visibility = View.VISIBLE
                btnRefreshScan.visibility = View.GONE
                btnConnectWifi.visibility = View.VISIBLE
                completed = false
                layoutWifiSuccess.visibility = View.GONE
                queryWifiButton.visibility = View.VISIBLE
                setWifiBusy(true)
                tvDeviceCount.text = if (capabilities.connect) "选择 Wi-Fi 为设备联网" else "当前固件未开放真实联网，请确认固件版本"
                client.queryStatus()
            }
            override fun onDisconnected() { onBleDisconnected() }
            override fun onScanComplete(items: List<K7Protocol.AccessPoint>, truncated: Boolean) {
                if (isFinishing || isDestroyed) return
                requestingWifi = false
                setWifiBusy(false)
                wifiItems.clear(); wifiItems.addAll(items.map { WifiItem(it) })
                wifiAdapter.notifyDataSetChanged()
                tvWifiStatus.text = "Wi-Fi 列表 (${items.size})"
                tvWifiLoading.text = if (items.isEmpty()) "未发现可用 Wi-Fi，请重新搜索" else "结果较多，已显示部分"
                tvWifiLoading.visibility = if (items.isEmpty() || truncated) View.VISIBLE else View.GONE
                rvWifiList.visibility = if (items.isEmpty()) View.GONE else View.VISIBLE
            }
            override fun onWifiConnecting() {
                if (!isFinishing && !isDestroyed) tvWifiLoading.text = "设备正在连接 Wi-Fi，请稍候…"
            }
            override fun onWifiConnected(ip: String, stored: Boolean?) {
                if (isFinishing || isDestroyed) return
                showNetworkSuccess(ip, connectingSsid, stored)
            }
            override fun onStatusChecking() {
                if (isFinishing || isDestroyed) return
                setWifiBusy(true)
                tvScanStatus.text = "正在查询设备联网状态…"
            }
            override fun onScanStarted() {
                if (isFinishing || isDestroyed) return
                tvScanStatus.text = "蓝牙已就绪"
                tvWifiLoading.text = "正在搜索 Wi-Fi…"
            }
            override fun onNetworkStatus(connected: Boolean, ip: String?) {
                if (isFinishing || isDestroyed) return
                requestingWifi = false
                setWifiBusy(false)
                if (connected && ip != null) showNetworkSuccess(ip, null, null)
                else {
                    completed = false; connectingSsid = null
                    layoutWifiSuccess.visibility = View.GONE
                    btnConnectWifi.visibility = View.VISIBLE
                    tvScanStatus.text = "蓝牙已就绪"
                    tvDeviceCount.text = "设备当前未连接 Wi-Fi，可获取列表后配网"
                }
            }
            override fun onError(message: String) {
                if (isFinishing || isDestroyed) return
                completed = false
                layoutWifiSuccess.visibility = View.GONE
                dismissConnectingDialog()
                requestingWifi = false; connectingSsid = null
                setWifiBusy(false)
                if (!client.ready) {
                    layoutConnected.visibility = View.GONE
                    btnConnectWifi.visibility = View.GONE
                    btnRefreshScan.visibility = View.VISIBLE
                    wifiSection.visibility = View.GONE
                    tvEmptyState.visibility = View.VISIBLE
                    tvEmptyState.text = message
                    tvScanStatus.text = "蓝牙未就绪"
                } else {
                    wifiSection.visibility = View.VISIBLE
                    btnConnectWifi.visibility = View.VISIBLE
                    tvScanStatus.text = "联网状态未确认，可查询状态"
                    tvWifiStatus.text = message
                    tvWifiLoading.visibility = if (wifiItems.isEmpty()) View.VISIBLE else View.GONE
                    tvWifiLoading.text = message
                    rvWifiList.visibility = if (wifiItems.isEmpty()) View.GONE else View.VISIBLE
                }
                Toast.makeText(this@OpenVelaConnectActivity, message, Toast.LENGTH_LONG).show()
            }
        })

        queryWifiButton = android.widget.Button(this).apply {
            text = "查询设备联网状态"; isAllCaps = false
            visibility = View.GONE
            setTextColor(Color.rgb(58, 109, 240))
            setOnClickListener { if (client.ready && !client.busy) client.queryStatus() }
        }
        (layoutConnected.parent as ViewGroup).let { parent ->
            parent.addView(queryWifiButton, parent.indexOfChild(layoutConnected) + 1)
        }
        checkPermissionsAndScan()
    }

    // ================== 权限与蓝牙初始化 ==================
    private fun checkPermissionsAndScan() {
        if (isFinishing || isDestroyed) return
        scanSettingsAction = null
        tvScanStatus.text = "正在检查搜索条件…"
        tvScanStatus.setTextColor(Color.rgb(51, 51, 51))
        // 合规要求：用户同意隐私政策后才能申请蓝牙/位置权限
        PrivacyManager.ensureAgreed(this) {
            val requiredPermissions = mutableListOf<String>()
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.S) {
                requiredPermissions.add(Manifest.permission.BLUETOOTH_SCAN)
                requiredPermissions.add(Manifest.permission.BLUETOOTH_CONNECT)
            }
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.M) {
                requiredPermissions.add(Manifest.permission.ACCESS_FINE_LOCATION)
                requiredPermissions.add(Manifest.permission.ACCESS_COARSE_LOCATION)
            }
            val notGranted = requiredPermissions.filter {
                ContextCompat.checkSelfPermission(this, it) != PackageManager.PERMISSION_GRANTED
            }
            if (notGranted.isEmpty()) {
                initBluetooth()
            } else {
                tvScanStatus.text = "等待权限授权"
                tvEmptyState.text = "请在系统提示中允许搜索权限"
                val requestPermissions = notGranted.toMutableSet()
                if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.S && Manifest.permission.ACCESS_FINE_LOCATION in requestPermissions) {
                    requestPermissions.add(Manifest.permission.ACCESS_COARSE_LOCATION)
                }
                permissionLauncher.launch(requestPermissions.toTypedArray())
            }
        }
    }

    @SuppressLint("MissingPermission")
    private fun initBluetooth() {
        val bluetoothManager = getSystemService(Context.BLUETOOTH_SERVICE) as BluetoothManager
        bluetoothAdapter = bluetoothManager.adapter
        if (bluetoothAdapter == null) {
            showScanProblem("本设备不支持蓝牙", "请换用支持蓝牙的手机")
            return
        }
        if (bluetoothAdapter?.isEnabled != true) {
            tvScanStatus.text = "等待开启蓝牙"
            tvEmptyState.text = "请在系统提示中开启蓝牙"
            enableBtLauncher.launch(Intent(BluetoothAdapter.ACTION_REQUEST_ENABLE))
            return
        }
        if (!locationReady()) {
            showScanProblem("请开启位置信息", "此系统搜索蓝牙需要开启定位。开启后返回并点击刷新。",
                Intent(android.provider.Settings.ACTION_LOCATION_SOURCE_SETTINGS))
            return
        }
        bleScanner = bluetoothAdapter?.bluetoothLeScanner
        resetAndScan()
    }

    // ================== 扫描 ==================
    private fun resetAndScan() {
        if (isFinishing || isDestroyed || layoutConnected.visibility == View.VISIBLE) return
        stopBleScan()
        discoveredDevices.clear()
        nearbyAddresses.clear()
        scanSettingsAction = null
        deviceAdapter.notifyDataSetChanged()
        deviceListContainer.visibility = View.GONE
        tvEmptyState.visibility = View.VISIBLE
        tvEmptyState.text = "正在扫描，请稍候..."
        tvDeviceCount.text = "已找到 0 个设备…"
        tvScanStatus.text = "正在搜索 VelaVision 蓝牙设备"
        startBleScan()
    }

    @SuppressLint("MissingPermission")
    private fun startBleScan() {
        val scanner = bleScanner ?: run {
            showScanProblem("蓝牙扫描不可用", "请确认蓝牙已开启，稍后点击重试")
            return
        }
        if (isScanning) return
        isScanning = true
        val token = ++scanGeneration
        val callback = createScanCallback(token)
        scanCallback = callback

        val settings = ScanSettings.Builder()
            .setScanMode(ScanSettings.SCAN_MODE_LOW_LATENCY)
            .build()
        try {
            scanner.startScan(null, settings, callback)
        } catch (e: SecurityException) {
            Log.w(TAG, "startScan 无权限", e)
            showScanProblem("缺少蓝牙权限", "请允许搜索权限后重试",
                Intent(android.provider.Settings.ACTION_APPLICATION_DETAILS_SETTINGS, android.net.Uri.parse("package:$packageName")))
            return
        } catch (e: Exception) {
            Log.w(TAG, "startScan failed", e)
            showScanProblem("无法启动搜索", "请确认蓝牙已开启，稍后重试")
            return
        }

        scanStartedAt = android.os.SystemClock.elapsedRealtime()
        scanProgress.visibility = View.VISIBLE
        tvScanStatus.setTextColor(Color.rgb(58, 109, 240))
        refreshLabel("停止")
        showScanProgress(token)

        // 超时停止扫描
        scanHandler.postDelayed({
            if (token != scanGeneration) return@postDelayed
            stopBleScan()
            tvDeviceCount.text = "已找到 ${discoveredDevices.size} 台设备"
            tvScanStatus.text = "搜索完成，点击设备连接"
            if (discoveredDevices.isEmpty()) {
                tvScanStatus.text = "扫描结束"
                tvEmptyState.text = if (nearbyAddresses.isEmpty())
                    "本次未收到附近蓝牙信号。请检查蓝牙、定位和应用权限后重试。"
                else "已收到附近蓝牙信号，但未找到 VelaVision。请确认设备已开启且未被占用，再点击刷新。"
            }
        }, SCAN_TIMEOUT_MS)
    }

    @SuppressLint("MissingPermission")
    private fun stopBleScan() {
        scanGeneration++
        scanHandler.removeCallbacksAndMessages(null)
        if (::scanProgress.isInitialized) scanProgress.visibility = View.GONE
        if (::btnRefreshScan.isInitialized) refreshLabel("刷新")
        if (!isScanning) return
        isScanning = false
        scanHandler.removeCallbacksAndMessages(null)
        try {
            scanCallback?.let { bleScanner?.stopScan(it) }
            scanCallback = null
        } catch (e: Exception) {
            Log.w(TAG, "stopScan 异常", e)
        }
    }

    private fun createScanCallback(token: Int) = object : ScanCallback() {
        override fun onScanResult(callbackType: Int, result: ScanResult) {
            if (Looper.myLooper() != Looper.getMainLooper()) {
                runOnUiThread { onScanResult(callbackType, result) }; return
            }
            if (token != scanGeneration || !isScanning || isFinishing || isDestroyed) return
            val device = result.device
            val address = try { device.address } catch (_: SecurityException) {
                showScanProblem("蓝牙权限不可用", "请在应用设置中允许蓝牙权限后重试"); return
            }
            nearbyAddresses.add(address)
            if (discoveredDevices.size >= 5) return
            val name = try { result.scanRecord?.deviceName ?: device.name } catch (_: SecurityException) { null }
            val advertisedService = result.scanRecord?.serviceUuids?.any { it.uuid == K7Protocol.SERVICE } == true

            // 只显示名称包含目标名称的设备（忽略大小写）
            if (!advertisedService && name?.contains(TARGET_NAME, ignoreCase = true) != true) return

            // 避免重复添加
            if (discoveredDevices.any { it.address == address }) return

            discoveredDevices.add(device)
            runOnUiThread {
                deviceAdapter.notifyItemInserted(discoveredDevices.size - 1)
                deviceListContainer.visibility = View.VISIBLE
                tvEmptyState.visibility = View.GONE
                tvDeviceCount.text = "已找到 ${discoveredDevices.size} 个设备…"
                if (discoveredDevices.size >= 5) {
                    stopBleScan()
                    tvScanStatus.text = "已找到 5 台设备，搜索结束"
                }
            }
        }

        override fun onScanFailed(errorCode: Int) {
            runOnUiThread {
                if (token != scanGeneration || isDestroyed) return@runOnUiThread
                val detail = when (errorCode) {
                    ScanCallback.SCAN_FAILED_ALREADY_STARTED -> "系统扫描尚未结束，请稍后重试"
                    ScanCallback.SCAN_FAILED_APPLICATION_REGISTRATION_FAILED -> "系统未能启动扫描，请关闭再开启蓝牙后重试"
                    ScanCallback.SCAN_FAILED_FEATURE_UNSUPPORTED -> "当前手机不支持此扫描方式"
                    6 -> "搜索过于频繁，请稍等片刻再试"
                    else -> "系统扫描失败（$errorCode），请稍后重试"
                }
                Log.w(TAG, "BLE scan failed: $errorCode")
                showScanProblem("搜索失败", detail)
            }
        }
    }

    // ================== 连接设备 ==================
    @SuppressLint("MissingPermission")
    private fun connectDevice(device: BluetoothDevice) {
        if (connectingDialog != null || layoutConnected.visibility == View.VISIBLE) return
        stopBleScan()
        tvScanStatus.text = "正在连接设备…"
        selectedDeviceAddress = device.address
        selectedDeviceName = try { device.name ?: TARGET_NAME } catch (_: SecurityException) { TARGET_NAME }
        showConnectingDialog()

        if (BleManager.isConnected() && BleManager.getDeviceId().equals(device.address, true)) {
            dismissConnectingDialog()
            Toast.makeText(this, "此设备正由其他护理页面使用，请先断开后重试", Toast.LENGTH_LONG).show()
            return
        }
        client.connect(device)
    }

    private fun requestWifiList() {
        if (!client.ready || client.busy || completed) return
        requestingWifi = true
        wifiItems.clear(); wifiAdapter.notifyDataSetChanged()
        wifiSection.visibility = View.VISIBLE
        tvWifiStatus.text = "Wi-Fi 列表"
        tvWifiLoading.visibility = View.VISIBLE
        tvWifiLoading.text = "正在查询设备状态，未联网时搜索 Wi-Fi…"
        rvWifiList.visibility = View.GONE
        layoutWifiSuccess.visibility = View.GONE
        setWifiBusy(true)
        client.scan()
    }

    /** 点击 WIFI 列表项：弹出密码输入框 */
    private fun showWifiPasswordDialog(item: WifiItem) {
        if (client.busy || completed || passwordDialog != null || !client.ready) return
        if (!client.canConnect || item.ap.hidden) {
            Toast.makeText(this, if (item.ap.hidden) "请选择有名称的网络" else "设备固件暂未开放真实联网，请确认新版固件", Toast.LENGTH_LONG).show()
            return
        }
        val view = layoutInflater.inflate(R.layout.dialog_wifi_password, null)
        view.findViewById<TextView>(R.id.tvDialogWifiSsid).text = item.ssid
        val etPassword = view.findViewById<EditText>(R.id.etWifiPassword)

        val dialog = AlertDialog.Builder(this)
            .setView(view)
            .setCancelable(true)
            .create()
        passwordDialog = dialog
        dialog.setOnDismissListener { etPassword.text.clear(); passwordDialog = null }

        view.findViewById<View>(R.id.btnCancelWifi).setOnClickListener { dialog.dismiss() }
        view.findViewById<View>(R.id.btnConfirmWifi).setOnClickListener {
            val pwd = etPassword.text.toString()
            if (!K7Protocol.validPassword(pwd)) { etPassword.error = "请输入8至63个可打印ASCII字符（支持空格）"; return@setOnClickListener }
            try { K7Protocol.request(1, "connect", item.ap, pwd) } catch (_: Exception) { etPassword.error = "网络标识无效，请重新扫描后选择"; return@setOnClickListener }
            dialog.dismiss()
            sendWifiDetails(item, pwd)
        }
        dialog.window?.setBackgroundDrawableResource(android.R.color.transparent)
        dialog.show()
    }

    private fun sendWifiDetails(item: WifiItem, password: String) {
        if (!client.ready || client.busy || !client.canConnect) return
        connectingSsid = item.ssid
        setWifiBusy(true)
        tvWifiLoading.visibility = View.VISIBLE
        tvWifiLoading.text = "正在连接 Wi-Fi，等待设备返回结果…"
        rvWifiList.visibility = View.GONE
        client.connectWifi(item.ap, password)
    }

    private fun showNetworkSuccess(ip: String, ssid: String?, stored: Boolean?) {
        completed = true; requestingWifi = false; connectingSsid = null
        passwordDialog?.dismiss()
        setWifiBusy(false)
        wifiItems.clear(); wifiAdapter.notifyDataSetChanged()
        tvWifiSuccessText.text = "联网成功" + (ssid?.let { "\n" + it } ?: "") +
            "\n网络地址：" + ip +
            (if (stored == false) "\n凭据未持久保存，断电后需重新配网" else "\n不保证断电后自动重连") +
            "\n已连接局域网，互联网及云语音需另行验证"
        layoutWifiSuccess.visibility = View.VISIBLE
        wifiSection.visibility = View.GONE
        btnConnectWifi.visibility = View.GONE
        queryWifiButton.visibility = View.VISIBLE
        tvScanStatus.text = "设备联网状态已确认"
        tvDeviceCount.text = "可返回使用，或主动查询最新状态"
    }

    /** 蓝牙断开：复位 WIFI 流程相关 UI，重新扫描 */
    private fun onBleDisconnected() {
        if (isFinishing || isDestroyed) return
        completed = false
        queryWifiButton.visibility = View.GONE
        wifiItems.clear(); wifiAdapter.notifyDataSetChanged()
        passwordDialog?.dismiss()
        requestingWifi = false
        setWifiBusy(false)
        wifiHandler.removeCallbacksAndMessages(null)
        connectingSsid = null
        wifiSection.visibility = View.GONE
        layoutWifiSuccess.visibility = View.GONE
        btnConnectWifi.visibility = View.GONE
        layoutConnected.visibility = View.GONE
        btnRefreshScan.visibility = View.VISIBLE
        Toast.makeText(this, "蓝牙已断开", Toast.LENGTH_SHORT).show()
        tvScanStatus.text = "蓝牙已断开，联网状态未知"
        tvDeviceCount.text = "重连后将查询真实联网状态，不会自动重发密码"
        tvEmptyState.visibility = View.VISIBLE
        tvEmptyState.text = "请点击刷新重新连接"
    }

    // ================== 连接中弹窗（与 SkincareFragment 保持一致）==================
    private fun showConnectingDialog() {
        connectingDialog = Dialog(this).apply {
            requestWindowFeature(Window.FEATURE_NO_TITLE)
            setContentView(R.layout.dialog_connecting)
            setCancelable(true)
            setOnCancelListener { client.close(); dismissConnectingDialog(); resetAndScan() }

            window?.apply {
                setBackgroundDrawable(ColorDrawable(Color.TRANSPARENT))
                setLayout(WindowManager.LayoutParams.MATCH_PARENT, WindowManager.LayoutParams.MATCH_PARENT)
                setGravity(Gravity.CENTER)
            }
        }

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

    override fun onStop() {
        if (isScanning) {
            stopBleScan()
            tvScanStatus.text = "搜索已暂停"
            tvDeviceCount.text = "已找到 ${discoveredDevices.size} 台设备"
            if (discoveredDevices.isEmpty()) tvEmptyState.text = "返回后点击刷新继续搜索"
        }
        super.onStop()
    }

    @SuppressLint("MissingPermission")
    override fun onDestroy() {
        client.close()
        super.onDestroy()
        passwordDialog?.dismiss()
        stopBleScan()
        dismissConnectingDialog()
        wifiHandler.removeCallbacksAndMessages(null)
    }

    // ===== 设备列表 Adapter =====
    private class OpenVelaDeviceAdapter(
        private val devices: MutableList<BluetoothDevice>,
        private val onItemClick: (BluetoothDevice) -> Unit
    ) : RecyclerView.Adapter<OpenVelaDeviceAdapter.ViewHolder>() {

        class ViewHolder(view: View) : RecyclerView.ViewHolder(view) {
            val ivThumb: ImageView = view.findViewById(R.id.ivDeviceThumb)
            val tvName: TextView = view.findViewById(R.id.tvDeviceName)
            val tvAddress: TextView = view.findViewById(R.id.tvDeviceAddress)
        }

        override fun onCreateViewHolder(parent: ViewGroup, viewType: Int): ViewHolder {
            val view = LayoutInflater.from(parent.context)
                .inflate(R.layout.item_device, parent, false)
            return ViewHolder(view)
        }

        @SuppressLint("MissingPermission")
        override fun onBindViewHolder(holder: ViewHolder, position: Int) {
            val device = devices[position]
            holder.ivThumb.setImageResource(R.drawable.openvela_board_thumb)
            holder.tvName.text = device.name ?: TARGET_NAME
            holder.tvAddress.text = device.address
            holder.itemView.setOnClickListener { onItemClick(device) }
        }

        override fun getItemCount(): Int = devices.size
    }

    // ===== WIFI 列表 Adapter =====
    private class WifiAdapter(
        private val items: MutableList<WifiItem>,
        private val onItemClick: (WifiItem) -> Unit
    ) : RecyclerView.Adapter<WifiAdapter.ViewHolder>() {

        class ViewHolder(view: View) : RecyclerView.ViewHolder(view) {
            val ivWifi: ImageView = view.findViewById(R.id.ivWifiIcon)
            val tvSsid: TextView = view.findViewById(R.id.tvWifiSsid)
            val tvRssi: TextView = view.findViewById(R.id.tvWifiRssi)
        }

        override fun onCreateViewHolder(parent: ViewGroup, viewType: Int): ViewHolder {
            val view = LayoutInflater.from(parent.context)
                .inflate(R.layout.item_wifi, parent, false)
            return ViewHolder(view)
        }

        override fun onBindViewHolder(holder: ViewHolder, position: Int) {
            val item = items[position]
            holder.tvSsid.text = item.ssid
            val label: String
            val icon: Int
            when {
                item.rssi >= -50 -> { label = "极强"; icon = R.drawable.ic_wifi_signal_4 }
                item.rssi >= -65 -> { label = "强"; icon = R.drawable.ic_wifi_signal_3 }
                item.rssi >= -75 -> { label = "中"; icon = R.drawable.ic_wifi_signal_2 }
                else -> { label = "弱"; icon = R.drawable.ic_wifi_signal_1 }
            }
            holder.tvRssi.text = "信号$label · ${item.ap.band}"
            holder.ivWifi.clearColorFilter()
            holder.ivWifi.setImageResource(icon)
            holder.ivWifi.contentDescription = "Wi-Fi 信号$label"
            holder.itemView.setOnClickListener { onItemClick(item) }
        }

        override fun getItemCount(): Int = items.size
    }
}
