package com.example.aisia.ui.device

import android.annotation.SuppressLint
import android.content.Context
import android.net.ConnectivityManager
import android.net.LinkProperties
import android.net.Network
import android.net.NetworkCapabilities
import android.net.NetworkRequest
import android.net.wifi.WifiConfiguration
import android.net.wifi.WifiInfo
import android.net.wifi.WifiManager
import android.os.Build
import android.util.Log
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.suspendCancellableCoroutine
import kotlinx.coroutines.withContext
import kotlinx.coroutines.withTimeoutOrNull
import java.net.InetAddress
import java.net.NetworkInterface
import java.util.concurrent.atomic.AtomicBoolean
import kotlin.coroutines.resume

/**
 * 摄像头 WiFi 管理器
 *
 * 参考 Flutter 版本的实现：
 * 1. 进入页面时保存当前WiFi，扫描并连接摄像头WiFi（SSID以CC-开头）
 * 2. 退出页面时断开摄像头WiFi，恢复之前的WiFi
 *
 * 核心问题：摄像头通过 WiFi 直连，IP 固定为 192.168.100.1，
 * 必须确保应用的网络流量（包括 native .so 库的网络请求）确实走 WiFi，
 * 而不是走移动网络。
 *
 * 摄像头WiFi特征：
 * - SSID 前缀: CC-
 * - 密码: 无密码 或 12345678
 */
@Suppress("DEPRECATION")
class CameraWifiManager(private val context: Context) {

    companion object {
        private const val TAG = "CameraWifiManager"
        private const val CAMERA_WIFI_PREFIX = "CC-"
        private const val CAMERA_IP = "192.168.100.1"
        private const val WIFI_SWITCH_DELAY_MS = 3000L
    }

    private val wifiManager = context.applicationContext.getSystemService(Context.WIFI_SERVICE) as WifiManager
    private val connectivityManager = context.applicationContext.getSystemService(Context.CONNECTIVITY_SERVICE) as ConnectivityManager

    /** 当前通过 WifiNetworkSpecifier 建立的网络（Android 10+） */
    private var currentSpecifierNetwork: Network? = null
    private var networkCallback: ConnectivityManager.NetworkCallback? = null

    /** 保存的之前的WiFi networkId，用于退出时恢复 */
    private var savedNetworkId: Int = -1
    private var savedSsid: String? = null
    private var usedSpecifier = false

    /** 详细的连接状态，用于 UI 调试显示 */
    var lastConnectLog = mutableListOf<String>()
        private set

    private fun addLog(msg: String) {
        Log.i(TAG, msg)
        lastConnectLog.add("[${System.currentTimeMillis() % 100000}] $msg")
        if (lastConnectLog.size > 50) lastConnectLog.removeAt(0)
    }
    
    /**
     * 获取当前连接的 WiFi SSID
     */
    @SuppressLint("MissingPermission")
    fun getCurrentSsid(): String? {
        return try {
            val info = wifiManager.connectionInfo
            val ssid = info.ssid?.replace("\"", "")
            if (ssid != null && ssid != "<unknown ssid>" && ssid.isNotEmpty()) ssid else null
        } catch (e: Exception) {
            Log.e(TAG, "获取SSID失败: ${e.message}")
            null
        }
    }
    
    /**
     * 保存当前WiFi（用于退出时恢复）
     */
    @SuppressLint("MissingPermission")
    fun saveCurrentWifi() {
        val ssid = getCurrentSsid()
        if (ssid != null && !ssid.startsWith(CAMERA_WIFI_PREFIX)) {
            savedSsid = ssid
            // 查找已保存的网络配置
            val configs = wifiManager.configuredNetworks
            val config = configs?.find { it.SSID.replace("\"", "") == ssid }
            savedNetworkId = config?.networkId ?: -1
            Log.i(TAG, "已保存当前WiFi: $ssid, networkId=$savedNetworkId")
        } else {
            Log.i(TAG, "当前已在摄像头WiFi上或无WiFi，跳过保存")
        }
    }
    
    /**
     * 检查当前是否已连接到摄像头WiFi
     */
    fun isOnCameraWifi(): Boolean {
        val ssid = getCurrentSsid()
        return ssid != null && ssid.startsWith(CAMERA_WIFI_PREFIX)
    }
    
    /**
     * 扫描可用的摄像头WiFi
     */
    @SuppressLint("MissingPermission")
    fun scanCameraWifiNetworks(): List<String> {
        return try {
            wifiManager.startScan()
            val results = wifiManager.scanResults
            results.filter { it.SSID.startsWith(CAMERA_WIFI_PREFIX) }
                   .map { it.SSID }
                   .distinct()
                   .also { Log.i(TAG, "扫描到摄像头WiFi: $it") }
        } catch (e: Exception) {
            Log.e(TAG, "扫描WiFi失败: ${e.message}")
            emptyList()
        }
    }
    
    /** 最近一次扫描到的摄像头WiFi列表 */
    var lastScannedCameraWifis: List<String> = emptyList()
        private set

    /** 最近一次连接的目标SSID */
    var lastTargetSsid: String? = null
        private set

    /**
     * 连接到摄像头WiFi（双策略：先系统级，失败则应用级 WifiNetworkSpecifier）
     * 连接成功后会绑定应用网络到 WiFi，确保 native .so 也走 WiFi。
     *
     * @return true=连接成功, false=连接失败
     */
    @SuppressLint("MissingPermission")
    suspend fun connectToCameraWifi(): Boolean = withContext(Dispatchers.IO) {
        lastConnectLog.clear()
        addLog("========== 开始连接摄像头WiFi ==========")

        // 多次扫描，因为第一次可能扫不到
        var cameraNetworks = emptyList<String>()
        for (attempt in 1..3) {
            addLog("扫描尝试 #$attempt")
            wifiManager.startScan()
            kotlinx.coroutines.delay(1500)
            cameraNetworks = scanCameraWifiNetworks()
            if (cameraNetworks.isNotEmpty()) break
            addLog("第${attempt}次扫描未找到，等待重试...")
        }

        lastScannedCameraWifis = cameraNetworks

        if (cameraNetworks.isEmpty()) {
            addLog("❌ 3次扫描均未找到摄像头WiFi (SSID前缀: $CAMERA_WIFI_PREFIX)")
            addLog("请确认：1) 摄像头已开机  2) 手机位置权限已授予  3) 附近确实有CC-开头的热点")
            return@withContext false
        }

        val targetSsid = cameraNetworks.first()
        lastTargetSsid = targetSsid
        addLog("找到摄像头WiFi: $targetSsid (共: $cameraNetworks)")

        // 检查是否已经连接
        val currentSsid = getCurrentSsid()
        if (currentSsid == targetSsid) {
            addLog("✓ 已在目标WiFi上，直接绑定网络")
            bindToWifiNetwork()
            return@withContext true
        }

        usedSpecifier = false
        var connected = false

        // ---- 策略1: Android 10+ 优先用 WifiNetworkSpecifier（应用级连接，最可靠）----
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.Q) {
            addLog("[策略1] Android 10+，尝试 WifiNetworkSpecifier 应用级连接")
            connected = connectUsingSpecifier(targetSsid)
            if (connected) {
                usedSpecifier = true
                addLog("✓ WifiNetworkSpecifier 连接成功")
            } else {
                addLog("[策略1] WifiNetworkSpecifier 失败，尝试系统级连接")
            }
        }

        // ---- 策略2: 系统级 WiFi 切换（传统方式）----
        if (!connected) {
            addLog("[策略2] 使用 addNetwork/enableNetwork 系统级连接")
            connected = connectUsingSystemApi(targetSsid)
            if (connected) {
                addLog("✓ 系统级连接成功")
                bindToWifiNetwork()
            }
        }

        // ---- 连接成功后验证：检查 192.168.100.1 是否可达 ----
        if (connected) {
            addLog("等待网络稳定 2 秒...")
            kotlinx.coroutines.delay(2000)
            val ipOk = verifyCameraIpReachable()
            if (ipOk) {
                addLog("✓ 摄像头 IP ($CAMERA_IP) 可达，可以创建摄像头实例")
            } else {
                addLog("⚠ WiFi 已连接但摄像头 IP 不可达（可能热点不是真正的摄像头设备）")
                // 还是返回 true，让后续流程尝试，native 库会自己判断
            }
        } else {
            addLog("❌ 所有连接方式均失败，请手动在系统WiFi设置中连接 $CAMERA_WIFI_PREFIX 开头的热点")
        }

        connected
    }

    /** 验证 192.168.100.1 是否可达 */
    private fun verifyCameraIpReachable(): Boolean {
        return try {
            val addr = InetAddress.getByName(CAMERA_IP)
            val reachable = addr.isReachable(3000)
            addLog("检查 $CAMERA_IP 可达性: $reachable")

            // 顺带输出本机 IP 信息（调试用）
            try {
                val en = NetworkInterface.getNetworkInterfaces()
                while (en.hasMoreElements()) {
                    val nif = en.nextElement()
                    val inetAddrs = nif.inetAddresses
                    while (inetAddrs.hasMoreElements()) {
                        val ia = inetAddrs.nextElement()
                        if (!ia.isLoopbackAddress) {
                            val ipStr = ia.hostAddress
                            if (ipStr != null && !ipStr.contains(":")) {
                                addLog(" 本机IPv4[${nif.name}]: $ipStr")
                            }
                        }
                    }
                }
            } catch (e: Exception) {
                addLog("获取本机IP失败: ${e.message}")
            }

            reachable
        } catch (e: Exception) {
            addLog("检查可达性异常: ${e.message}")
            false
        }
    }

    /** 绑定应用网络到 WiFi（确保 native .so 库的网络请求也走 WiFi） */
    @SuppressLint("MissingPermission")
    private fun bindToWifiNetwork(): Boolean {
        return try {
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.M) {
                // 获取当前 WiFi Network
                val currentNetwork = connectivityManager.activeNetwork
                val caps = currentNetwork?.let { connectivityManager.getNetworkCapabilities(it) }
                val isWifi = caps?.hasTransport(NetworkCapabilities.TRANSPORT_WIFI) == true

                if (isWifi && currentNetwork != null) {
                    // 将当前进程默认网络绑定到 WiFi
                    val ok = connectivityManager.bindProcessToNetwork(currentNetwork)
                    addLog("bindProcessToNetwork(WiFi): $ok")

                    // 同时把 Network 对象记录下来
                    currentSpecifierNetwork = currentNetwork
                } else {
                    addLog("当前活动网络不是 WiFi，无法绑定 (caps=$caps)")
                }
            } else {
                @Suppress("DEPRECATION")
                ConnectivityManager.setProcessDefaultNetwork(connectivityManager.activeNetwork)
                addLog("已调用 setProcessDefaultNetwork (Android < M)")
            }
            true
        } catch (e: Exception) {
            addLog("bindToWifiNetwork 异常: ${e.message}")
            false
        }
    }

    /** [Android 10+] 使用 WifiNetworkSpecifier 连接（应用级，成功率最高） */
    @SuppressLint("MissingPermission")
    private suspend fun connectUsingSpecifier(targetSsid: String): Boolean {
        if (Build.VERSION.SDK_INT < Build.VERSION_CODES.Q) return false

        return try {
            val specifier = android.net.wifi.WifiNetworkSpecifier.Builder()
                .setSsid(targetSsid)
                .build()

            val request = NetworkRequest.Builder()
                .addTransportType(NetworkCapabilities.TRANSPORT_WIFI)
                .removeCapability(NetworkCapabilities.NET_CAPABILITY_INTERNET)
                .setNetworkSpecifier(specifier)
                .build()

            val connected = withTimeoutOrNull(10_000L) {
                suspendCancellableCoroutine { continuation ->
                    val completed = AtomicBoolean(false)
                    lateinit var callback: ConnectivityManager.NetworkCallback

                    fun unregisterCallback() {
                        try {
                            connectivityManager.unregisterNetworkCallback(callback)
                        } catch (_: Exception) {
                        }
                        if (networkCallback === callback) networkCallback = null
                    }

                    callback = object : ConnectivityManager.NetworkCallback() {
                        override fun onAvailable(network: Network) {
                            if (!completed.compareAndSet(false, true)) return
                            addLog("  NetworkCallback.onAvailable")
                            currentSpecifierNetwork = network
                            val bound = connectivityManager.bindProcessToNetwork(network)
                            if (bound) {
                                addLog("  WifiNetworkSpecifier 成功连接并绑定")
                                continuation.resume(true)
                            } else {
                                addLog("  WifiNetworkSpecifier 网络绑定失败")
                                unregisterCallback()
                                continuation.resume(false)
                            }
                        }

                        override fun onUnavailable() {
                            if (!completed.compareAndSet(false, true)) return
                            addLog("  NetworkCallback.onUnavailable")
                            unregisterCallback()
                            continuation.resume(false)
                        }
                    }

                    networkCallback = callback
                    try {
                        connectivityManager.requestNetwork(request, callback)
                    } catch (e: Exception) {
                        if (completed.compareAndSet(false, true)) {
                            unregisterCallback()
                            continuation.resume(false)
                        }
                    }

                    continuation.invokeOnCancellation {
                        if (completed.compareAndSet(false, true)) unregisterCallback()
                    }
                }
            }

            if (connected != true) {
                addLog("  WifiNetworkSpecifier 超时或被用户拒绝")
                networkCallback?.let { callback ->
                    try {
                        connectivityManager.unregisterNetworkCallback(callback)
                    } catch (_: Exception) {
                    }
                    if (networkCallback === callback) networkCallback = null
                }
            }
            connected == true
        } catch (e: Exception) {
            addLog("  connectUsingSpecifier 异常: ${e.message}")
            false
        }
    }

    /** [传统方式] 使用 addNetwork + enableNetwork 系统级切换 */
    @SuppressLint("MissingPermission")
    private suspend fun connectUsingSystemApi(targetSsid: String): Boolean {
        // 先尝试无密码（开放网络）
        var networkId = addOpenNetwork(targetSsid)

        if (networkId == -1) {
            // 开放网络添加失败，尝试密码 12345678
            addLog("  开放网络添加失败，尝试 WPA2 密码 12345678")
            networkId = addWpa2Network(targetSsid, "12345678")
        }

        if (networkId == -1) {
            addLog("  ❌ 无法添加WiFi网络: $targetSsid")
            return false
        }

        // 断开当前连接并切换到摄像头WiFi
        wifiManager.disconnect()
        kotlinx.coroutines.delay(500)
        val enabled = wifiManager.enableNetwork(networkId, true)
        wifiManager.reconnect()

        addLog("  WiFi切换已发起: $targetSsid, enableNetwork=$enabled, networkId=$networkId")

        // 等待切换完成 - 5秒 + 多次检查
        for (check in 1..5) {
            kotlinx.coroutines.delay(1500)
            val newSsid = getCurrentSsid()
            if (newSsid == targetSsid) {
                addLog("  ✓ WiFi切换成功: $newSsid (第${check}次检查)")
                return true
            }
            addLog("  WiFi切换验证 #$check: 目标=$targetSsid, 当前=$newSsid")
        }

        val finalSsid = getCurrentSsid()
        addLog("  WiFi切换可能未成功: 目标=$targetSsid, 最终=$finalSsid")
        return false
    }
    
    /**
     * 添加开放网络（无密码）
     */
    @SuppressLint("MissingPermission")
    private fun addOpenNetwork(ssid: String): Int {
        // 先检查是否已有配置
        val configs = wifiManager.configuredNetworks
        val existing = configs?.find { it.SSID.replace("\"", "") == ssid }
        if (existing != null) {
            Log.i(TAG, "找到已有WiFi配置: $ssid, networkId=${existing.networkId}")
            return existing.networkId
        }
        
        val config = WifiConfiguration().apply {
            this.SSID = "\"$ssid\""
            allowedKeyManagement.set(WifiConfiguration.KeyMgmt.NONE)
            allowedAuthAlgorithms.clear()
        }
        
        val networkId = wifiManager.addNetwork(config)
        Log.i(TAG, "添加开放网络: $ssid, networkId=$networkId")
        return networkId
    }
    
    /**
     * 添加 WPA2 密码网络
     */
    @SuppressLint("MissingPermission")
    private fun addWpa2Network(ssid: String, password: String): Int {
        val config = WifiConfiguration().apply {
            this.SSID = "\"$ssid\""
            this.preSharedKey = "\"$password\""
            allowedKeyManagement.set(WifiConfiguration.KeyMgmt.WPA_PSK)
            allowedProtocols.set(WifiConfiguration.Protocol.RSN)
            allowedProtocols.set(WifiConfiguration.Protocol.WPA)
            allowedPairwiseCiphers.set(WifiConfiguration.PairwiseCipher.CCMP)
            allowedPairwiseCiphers.set(WifiConfiguration.PairwiseCipher.TKIP)
            allowedGroupCiphers.set(WifiConfiguration.GroupCipher.CCMP)
            allowedGroupCiphers.set(WifiConfiguration.GroupCipher.TKIP)
        }
        
        val networkId = wifiManager.addNetwork(config)
        Log.i(TAG, "添加WPA2网络: $ssid, networkId=$networkId")
        return networkId
    }
    
    /**
     * 恢复之前的WiFi
     */
    @SuppressLint("MissingPermission")
    suspend fun restorePreviousWifi(): Boolean {
        addLog("========== 恢复之前的WiFi ==========")
        addLog("savedSsid=$savedSsid, savedNetworkId=$savedNetworkId, usedSpecifier=$usedSpecifier")

        // 如果用的是 WifiNetworkSpecifier，必须先取消网络请求
        if (usedSpecifier && networkCallback != null) {
            try {
                connectivityManager.unregisterNetworkCallback(networkCallback!!)
                addLog("已取消 WifiNetworkSpecifier 的网络请求")
            } catch (e: Exception) {
                addLog("取消网络请求失败: ${e.message}")
            }
            networkCallback = null
            currentSpecifierNetwork = null
        }

        // 解除网络绑定（恢复到系统默认网络）
        try {
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.M) {
                connectivityManager.bindProcessToNetwork(null)
                addLog("已解除 bindProcessToNetwork")
            } else {
                @Suppress("DEPRECATION")
                ConnectivityManager.setProcessDefaultNetwork(null)
            }
        } catch (e: Exception) {
            addLog("解除网络绑定异常: ${e.message}")
        }

        // 恢复之前的 WiFi
        if (savedNetworkId != -1) {
            wifiManager.disconnect()
            val enabled = wifiManager.enableNetwork(savedNetworkId, true)
            wifiManager.reconnect()
            kotlinx.coroutines.delay(WIFI_SWITCH_DELAY_MS)

            val currentSsid = getCurrentSsid()
            addLog("恢复结果: 目标=$savedSsid, 当前=$currentSsid, enabled=$enabled")
            return currentSsid == savedSsid
        }

        if (savedSsid != null) {
            val configs = wifiManager.configuredNetworks
            val config = configs?.find { it.SSID.replace("\"", "") == savedSsid }
            if (config != null) {
                wifiManager.disconnect()
                wifiManager.enableNetwork(config.networkId, true)
                wifiManager.reconnect()
                kotlinx.coroutines.delay(WIFI_SWITCH_DELAY_MS)

                val currentSsid = getCurrentSsid()
                addLog("恢复结果: 目标=$savedSsid, 当前=$currentSsid")
                return currentSsid == savedSsid
            }
        }

        wifiManager.reconnect()
        kotlinx.coroutines.delay(1000)

        val currentSsid = getCurrentSsid()
        addLog("恢复后WiFi: $currentSsid (之前: $savedSsid)")
        return currentSsid != null && !currentSsid.startsWith(CAMERA_WIFI_PREFIX)
    }

    /**
     * 释放资源
     */
    fun cleanup() {
        try {
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.M) {
                connectivityManager.bindProcessToNetwork(null)
            } else {
                @Suppress("DEPRECATION")
                ConnectivityManager.setProcessDefaultNetwork(null)
            }
        } catch (_: Exception) {}

        if (networkCallback != null) {
            try {
                connectivityManager.unregisterNetworkCallback(networkCallback!!)
            } catch (_: Exception) {}
            networkCallback = null
        }
    }
}
