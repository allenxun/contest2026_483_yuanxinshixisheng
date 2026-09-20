package com.example.aisia.ble.k7

import android.annotation.SuppressLint
import android.bluetooth.*
import android.content.Context
import android.os.Build
import android.os.Handler
import android.os.Looper
import android.os.SystemClock
import org.json.JSONObject

/** Dedicated GATT session for K7. Does not change the shared care-device protocol. */
@SuppressLint("MissingPermission")
class K7ProvisioningClient(context: Context, private val listener: Listener) {
    private companion object { var activeClient: K7ProvisioningClient? = null }
    interface Listener {
        fun onReady(capabilities: K7Protocol.Capabilities)
        fun onDisconnected()
        fun onScanComplete(items: List<K7Protocol.AccessPoint>, truncated: Boolean)
        fun onCredentialsReceived() {}
        fun onWifiConnecting() {}
        fun onWifiConnected(ip: String) {}
        fun onWifiConnected(ip: String, stored: Boolean?) { onWifiConnected(ip) }
        fun onStatusChecking() {}
        fun onScanStarted() {}
        fun onNetworkStatus(connected: Boolean, ip: String?) {}
        fun onError(message: String)
    }
    private val context = context.applicationContext
    private val main = Handler(Looper.getMainLooper())
    private var gatt: BluetoothGatt? = null
    private var writer: BluetoothGattCharacteristic? = null
    private var status: BluetoothGattCharacteristic? = null
    private var notification: BluetoothGattCharacteristic? = null
    private var capabilities: K7Protocol.Capabilities? = null
    private var epoch = 0
    private var disposed = false
    var ready = false
        private set
    val canConnect get() = ready && capabilities?.connect == true
    val canSubmitCredentials get() = ready && capabilities?.receiveCredentials == true
    val busy get() = operation != null
    private var operation: String? = null
    private var scanAfterStatus = false
    private var requestId = 0
    private var activeId: Int? = null
    private var targetSsid: String? = null
    private var accumulator: K7Protocol.ScanAccumulator? = null
    private val framer = K7Protocol.JsonLines()
    private var partialStartedAt = 0L
    private var pendingTerminal: JSONObject? = null
    private var command: ByteArray? = null
    private var offset = 0
    private var lastPartSize = 0
    private var writeDeadline = 0L
    private var writeTimer: Runnable? = null
    private var operationTimer: Runnable? = null
    private var readyTimer: Runnable? = null
    private var partialTimer: Runnable? = null
    private var bondTimer: Runnable? = null
    private var bondDeadline = 0L
    private var subscriptionInFlight = false
    private var readInFlight = false
    private fun dispatch(action: () -> Unit) { if (Looper.myLooper() == Looper.getMainLooper()) action() else main.post { action() } }
    fun connect(device: BluetoothDevice) {
        check(Looper.myLooper() == Looper.getMainLooper())
        if (activeClient != null && activeClient !== this) {
            listener.onError("另一配网页正在使用蓝牙，请先退出该页面"); return
        }
        disposed = false
        release()
        activeClient = this
        attempt(device, 0, epoch)
    }
    private fun attempt(device: BluetoothDevice, attemptIndex: Int, token: Int) {
        if (disposed || token != epoch || activeClient !== this) return
        try {
            gatt = device.connectGatt(context, false, callback, BluetoothDevice.TRANSPORT_LE)
            readyTimer = Runnable {
                if (token != epoch || ready || disposed) return@Runnable
                // Retry only BLE setup. Never replay scan requests or credentials.
                releaseGatt()
                if (attemptIndex < 2) main.postDelayed({ attempt(device, attemptIndex + 1, token) }, (attemptIndex + 1) * 1000L)
                else { activeClient = null; listener.onError("蓝牙连接或加密确认超时，请检查配对状态") }
            }.also { main.postDelayed(it, 30000) }
        } catch (_: Exception) { fail("无法连接设备，请检查蓝牙权限", true) }
    }
    private fun cancelTimer(timer: Runnable?) { timer?.let(main::removeCallbacks) }
    private fun releaseGatt() {
        cancelTimer(readyTimer); readyTimer = null
        try { gatt?.disconnect() } catch (_: Exception) {}
        try { gatt?.close() } catch (_: Exception) {}
        gatt = null; ready = false; writer = null; status = null; notification = null; readInFlight = false
        framer.reset(); partialStartedAt = 0
        cancelTimer(partialTimer); partialTimer = null
        cancelTimer(bondTimer); bondTimer = null
        bondDeadline = 0L; subscriptionInFlight = false
    }
    private fun finishOperation() {
        cancelTimer(operationTimer); operationTimer = null
        cancelTimer(writeTimer); writeTimer = null
        command?.fill(0); command = null
        @Suppress("DEPRECATION")
        writer?.value = byteArrayOf()
        offset = 0; lastPartSize = 0
        scanAfterStatus = false
        operation = null; activeId = null; accumulator = null; pendingTerminal = null; targetSsid = null
    }
    private fun release() {
        if (activeClient === this) activeClient = null
        epoch++
        finishOperation(); releaseGatt(); capabilities = null
    }
    fun close() {
        disposed = true
        release()
        main.removeCallbacksAndMessages(null)
    }
    private fun fail(message: String, disconnect: Boolean = false) {
        if (disposed) return
        val wasReady = ready
        val tip = if (operation == "submit_credentials") "未确认设备收到：$message" else message
        finishOperation()
        if (disconnect) release()
        if (disconnect && wasReady) listener.onDisconnected()
        listener.onError(tip)
    }
    private fun timeout(ms: Long) {
        val token = epoch
        operationTimer = Runnable { if (token == epoch && operation != null) fail(if (operation == "connect") "联网结果未知，请重新连接查询设备状态，不要重复提交密码" else "设备响应超时，请重新连接查询状态", true) }
            .also { main.postDelayed(it, ms) }
    }
    fun scan() {
        if (!ready || busy) return
        queryStatus(thenScan = true)
    }
    private fun startScan() {
        if (!ready || busy) return
        if (capabilities?.scan != true) { listener.onError("当前设备不支持扫描"); return }
        operation = "scan"; activeId = null; accumulator = K7Protocol.ScanAccumulator()
        listener.onScanStarted()
        timeout(K7Protocol.SCAN_TIMEOUT_MS)
        send(byteArrayOf(0x58))
    }
    fun submitCredentials(ap: K7Protocol.AccessPoint, password: String) {
        if (!ready || busy) return
        if (!canSubmitCredentials) { listener.onError("设备固件暂未开放信息接收，请确认固件版本"); return }
        if (ap.hidden) { listener.onError("隐藏网络暂不支持，请选择有名称的网络"); return }
        val id = nextId()
        val bytes = try { K7Protocol.request(id, "submit_credentials", ap, password) }
            catch (_: Exception) { listener.onError("SSID无效或密码格式不符合要求"); return }
        operation = "submit_credentials"; activeId = id; targetSsid = ap.ssidB64
        timeout(15000); send(bytes)
    }
    fun connectWifi(ap: K7Protocol.AccessPoint, password: String) {
        if (!ready || busy) return
        if (!canConnect) { listener.onError("设备未开放真实联网，请确认新版固件"); return }
        if (ap.hidden) { listener.onError("请选择有名称的网络"); return }
        val id = nextId()
        val bytes = try { K7Protocol.request(id, "connect", ap, password) }
            catch (_: Exception) { listener.onError("SSID或密码格式不符合要求"); return }
        operation = "connect"; activeId = id; targetSsid = ap.ssidB64
        timeout(K7Protocol.CONNECT_TIMEOUT_MS); send(bytes)
    }
    fun queryStatus(thenScan: Boolean = false) {
        if (!ready || busy) return
        val id = nextId()
        operation = "status"; activeId = id; scanAfterStatus = thenScan
        listener.onStatusChecking()
        timeout(15000); send(K7Protocol.request(id, "status"))
    }
    private fun nextId(): Int { requestId = requestId % 65535 + 1; return requestId }
    private fun send(bytes: ByteArray) {
        command = bytes; offset = 0
        writeDeadline = SystemClock.elapsedRealtime() + 9000
        writePart()
    }
    private fun writePart() {
        val data = command ?: return
        val current = gatt ?: return fail("蓝牙已断开", true)
        val characteristic = writer ?: return fail("设备写通道不可用", true)
        if (offset >= data.size) {
            data.fill(0); command = null
            pendingTerminal?.let {
                pendingTerminal = null
                try { process(it) } catch (_: Exception) { fail("设备返回数据不完整或格式错误，请重试", true) }
            }
            return
        }
        val remaining = writeDeadline - SystemClock.elapsedRealtime()
        if (remaining <= 0) return fail("命令发送超时，请重新连接", true)
        lastPartSize = minOf(20, data.size - offset)
        val part = data.copyOfRange(offset, offset + lastPartSize)
        try {
            characteristic.writeType = BluetoothGattCharacteristic.WRITE_TYPE_DEFAULT
            val ok = if (Build.VERSION.SDK_INT >= 33) {
                current.writeCharacteristic(characteristic, part, BluetoothGattCharacteristic.WRITE_TYPE_DEFAULT) == BluetoothGatt.GATT_SUCCESS
            } else {
                @Suppress("DEPRECATION")
                characteristic.value = part
                @Suppress("DEPRECATION")
                current.writeCharacteristic(characteristic)
            }
            if (!ok) return fail("指令发送失败，请重新连接后重试", true)
            writeTimer = Runnable { if (gatt === current && command === data) fail("写入确认超时，请重新连接", true) }
                .also { main.postDelayed(it, minOf(3000, remaining)) }
        } catch (_: Exception) { fail("蓝牙写入失败，请检查配对状态", true) }
    }
    private fun readCapabilities() {
        val current = gatt ?: return
        val characteristic = status ?: return
        if (readInFlight || ready || disposed) return
        try {
            readInFlight = current.readCharacteristic(characteristic)
            if (!readInFlight) fail("无法读取设备能力", true)
        } catch (_: Exception) { fail("读取设备能力失败", true) }
    }
    private fun waitForBondAndSubscribe() {
        val current = gatt ?: return
        val notify = notification ?: return fail("设备通知通道不可用", true)
        when (current.device.bondState) {
            BluetoothDevice.BOND_BONDED -> {
                cancelTimer(bondTimer); bondTimer = null; bondDeadline = 0L
                subscribeNotifications(current, notify)
            }
            BluetoothDevice.BOND_BONDING -> {
                if (bondDeadline == 0L) {
                    bondDeadline = SystemClock.elapsedRealtime() + 60000L
                    cancelTimer(readyTimer); readyTimer = null
                }
                scheduleBondCheck(current)
            }
            else -> {
                if (bondDeadline == 0L) {
                    bondDeadline = SystemClock.elapsedRealtime() + 60000L
                    cancelTimer(readyTimer); readyTimer = null
                    val started = try { current.device.createBond() } catch (_: Exception) { false }
                    if (!started) return fail("无法发起系统配对，请在蓝牙设置中配对 K7 后重试", true)
                }
                scheduleBondCheck(current)
            }
        }
    }
    private fun scheduleBondCheck(current: BluetoothGatt) {
        cancelTimer(bondTimer)
        val remaining = bondDeadline - SystemClock.elapsedRealtime()
        if (bondDeadline == 0L || remaining <= 0L) return fail("系统配对未完成，请确认配对提示后重试", true)
        bondTimer = Runnable {
            if (current !== gatt || disposed) return@Runnable
            waitForBondAndSubscribe()
        }.also { main.postDelayed(it, minOf(500L, remaining)) }
    }
    private fun subscribeNotifications(current: BluetoothGatt, notify: BluetoothGattCharacteristic) {
        if (current !== gatt || disposed || subscriptionInFlight) return
        try {
            cancelTimer(readyTimer)
            readyTimer = Runnable {
                if (current === gatt && !ready && !disposed) fail("通知订阅或能力读取超时，请重新连接", true)
            }.also { main.postDelayed(it, 15000L) }
            val descriptor = notify.getDescriptor(K7Protocol.CCCD) ?: error("CCCD不存在")
            require(current.setCharacteristicNotification(notify, true))
            @Suppress("DEPRECATION")
            descriptor.value = BluetoothGattDescriptor.ENABLE_NOTIFICATION_VALUE
            subscriptionInFlight = true
            @Suppress("DEPRECATION")
            require(current.writeDescriptor(descriptor))
        } catch (_: Exception) {
            subscriptionInFlight = false
            fail("设备通知订阅启动失败，请重新连接", true)
        }
    }
    private fun gotCapabilities(current: BluetoothGatt, bytes: ByteArray, code: Int) {
        if (current !== gatt || disposed) return
        readInFlight = false
        if (code != BluetoothGatt.GATT_SUCCESS) { fail("读取设备状态失败，请重新配对", true); return }
        try {
            val info = K7Protocol.capabilities(K7Protocol.json(bytes))
            capabilities = info
            if (!info.encrypted || info.busy) {
                if (!info.encrypted && current.device.bondState == BluetoothDevice.BOND_NONE) current.device.createBond()
                main.postDelayed({ if (current === gatt) readCapabilities() }, 500)
            } else {
                ready = true
                cancelTimer(readyTimer); readyTimer = null
                listener.onReady(info)
            }
        } catch (_: Exception) { fail("设备能力数据无效或协议版本不支持", true) }
    }
    private fun received(current: BluetoothGatt, bytes: ByteArray) {
        if (current !== gatt || disposed || !ready) return
        try {
            if (!framer.hasPartial) partialStartedAt = SystemClock.elapsedRealtime()
            val lines = framer.feed(bytes)
            if (lines.isNotEmpty()) partialStartedAt = SystemClock.elapsedRealtime()
            for (line in lines) {
                process(K7Protocol.json(line))
                if (current !== gatt) return
            }
            cancelTimer(partialTimer)
            if (framer.hasPartial) {
                val remaining = 10000 - (SystemClock.elapsedRealtime() - partialStartedAt)
                if (remaining <= 0) return fail("设备消息接收超时，请重新连接", true)
                partialTimer = Runnable { if (current === gatt && framer.hasPartial) fail("设备消息不完整，请重新连接", true) }
                    .also { main.postDelayed(it, remaining) }
            } else partialStartedAt = 0
        } catch (_: Exception) { fail("设备返回数据不完整或格式错误，请重试", true) }
    }
    private fun process(obj: JSONObject) {
        if (operation == null) return
        require(obj.opt("v") == 1)
        require(obj.opt("id") is Int)
        val id = obj.getInt("id")
        require(id in 1..65535)
        val event = obj.getString("event")
        if (command != null && K7Protocol.isTerminalEvent(event)) {
            require(pendingTerminal == null)
            pendingTerminal = obj
            return
        }
        if (operation == "scan" && activeId == null) {
            if (event == "error") {
                // Do not log untrusted scan error payloads.
                fail(errorText(obj.optString("code"))); return
            }
            require(event == "scan_started")
            activeId = id; accumulator!!.start(id); return
        }
        require(id == activeId) { "事务编号不匹配" }
        if (operation == "connect" || operation == "status") require(obj.opt("session") == capabilities?.session)
        if (obj.has("session")) require(obj.getInt("session") == capabilities?.session)
        if (event == "error") {
            val code = obj.optString("code")
            val detail = obj.opt("detail")
            val safeCode = code.takeIf { Regex("[A-Za-z0-9_]{1,64}").matches(it) } ?: "unknown"
            val numericDetail = (detail as? Number)?.toLong() ?: (detail as? String)?.toLongOrNull()
            android.util.Log.w("K7Provision", "event=error id=$id code=$safeCode detail=${numericDetail ?: "non-numeric"}")
            fail(errorText(code)); return
        }
        when (operation) {
            "scan" -> when (event) {
                "ap" -> accumulator!!.add(id, K7Protocol.accessPoint(obj))
                "scan_done" -> {
                    require(obj.opt("count") is Int)
                    val items = accumulator!!.finish(id, obj.getInt("count"))
                    val truncated = obj.getBoolean("truncated")
                    finishOperation()
                    listener.onScanComplete(items, truncated)
                }
                else -> error("扫描事件顺序错误")
            }
            "connect" -> when (event) {
                "wifi_connecting" -> listener.onWifiConnecting()
                "wifi_connected" -> {
                    val session = capabilities?.session ?: error("会话失效")
                    require(K7Protocol.wifiConnected(obj, id, session)) { "联网成功回包无效" }
                    val ip = obj.getString("ip")
                    finishOperation()
                    listener.onWifiConnected(ip, obj.opt("stored") as? Boolean)
                }
                "credentials_received" -> fail("设备仅确认收到信息，尚未联网，请确认新版固件")
                else -> error("未知联网事件")
            }
            "submit_credentials" -> {
                require(event == "credentials_received") { "未知信息接收事件" }
                val session = capabilities?.session ?: error("会话失效")
                require(K7Protocol.credentialsReceived(obj, id, session)) { "接收回执无效" }
                finishOperation()
                listener.onCredentialsReceived()
            }
            "status" -> {
                require(event == "status")
                val connected = K7Protocol.networkStatus(obj, id, capabilities?.session ?: error("会话失效"))
                val ip = obj.optString("ip").takeIf { connected }
                val continueScan = scanAfterStatus && !connected
                finishOperation()
                if (continueScan) startScan()
                else listener.onNetworkStatus(connected, ip)
            }
        }
    }
    private fun errorText(code: String) = when (code) {
        "not_ready" -> "设备尚未就绪，请检查设备状态后重试"
        "authentication_failed", "auth_failed", "wrong_password" -> "Wi-Fi认证失败，请检查密码和路由器认证设置"
        "network_not_found" -> "未找到该Wi-Fi，请靠近路由器并重新扫描"
        "unsupported_security" -> "设备不支持此网络加密方式，请使用WPA2-PSK网络"
        "connection_timeout" -> "设备连接超时，请查询状态或检查路由器后重试"
        "connection_failed" -> "Wi-Fi连接失败，请检查网络后重试"
        "dhcp_failed", "dhcp_timeout" -> "未获取网络地址，请检查路由器后重试"
        "scan_failed" -> "扫描失败，请重试"
        "invalid_password" -> "密码格式不符合要求：须为8至63个可打印ASCII字符，不支持开放网络空密码"
        "invalid_ssid" -> "网络标识无效，请重新扫描后选择"
        "busy" -> "设备忙，请稍后查询状态再重试"
        "invalid_command" -> "设备不支持此请求，请核对固件协议"
        else -> "设备处理失败，请重试"
    }
    private val callback = object : BluetoothGattCallback() {
        override fun onConnectionStateChange(current: BluetoothGatt, code: Int, state: Int) = dispatch {
            if (current !== gatt || disposed) return@dispatch
            if (code != BluetoothGatt.GATT_SUCCESS || state == BluetoothProfile.STATE_DISCONNECTED) {
                val wasReady = ready
                val submitting = operation == "submit_credentials"
                val connectingWifi = operation == "connect"
                release()
                if (wasReady) listener.onDisconnected()
                listener.onError(when {
                    connectingWifi -> "蓝牙已断开，联网结果未知；请重连后查询状态，不要重复提交密码"
                    submitting -> "蓝牙已断开，未确认设备收到；请重连后重新提交"
                    else -> "蓝牙已断开，请重新连接后查询设备状态"
                }); return@dispatch
            }
            if (state == BluetoothProfile.STATE_CONNECTED) {
                try { if (!current.discoverServices()) fail("服务发现失败", true) }
                catch (_: Exception) { fail("服务发现失败，请检查蓝牙权限", true) }
            }
        }
        override fun onServicesDiscovered(current: BluetoothGatt, code: Int) = dispatch {
            if (current !== gatt || disposed) return@dispatch
            try {
                require(code == BluetoothGatt.GATT_SUCCESS)
                val service = current.getService(K7Protocol.SERVICE) ?: error("服务不存在")
                writer = service.getCharacteristic(K7Protocol.COMMAND)
                status = service.getCharacteristic(K7Protocol.STATUS)
                notification = service.getCharacteristic(K7Protocol.NOTIFY)
                require(writer != null && (writer!!.properties and BluetoothGattCharacteristic.PROPERTY_WRITE) != 0)
                require(status != null && (status!!.properties and BluetoothGattCharacteristic.PROPERTY_READ) != 0)
                val notify = notification ?: error("通知不存在")
                require((notify.properties and BluetoothGattCharacteristic.PROPERTY_NOTIFY) != 0)
                waitForBondAndSubscribe()
            } catch (_: Exception) { fail("设备配网服务或通知订阅不可用", true) }
        }
        override fun onDescriptorWrite(current: BluetoothGatt, descriptor: BluetoothGattDescriptor, code: Int) = dispatch {
            if (current !== gatt || disposed || descriptor.characteristic.uuid != K7Protocol.NOTIFY || descriptor.uuid != K7Protocol.CCCD) return@dispatch
            subscriptionInFlight = false
            if (code == BluetoothGatt.GATT_SUCCESS) readCapabilities()
            else if (code == BluetoothGatt.GATT_INSUFFICIENT_AUTHENTICATION || code == 15) {
                if (current.device.bondState != BluetoothDevice.BOND_BONDED) waitForBondAndSubscribe()
                else fail("蓝牙加密密钥已失效，请在系统蓝牙设置中取消 K7 配对后重新连接", true)
            } else fail("通知订阅失败（$code），请重新连接；反复失败时取消系统配对后重试", true)
        }
        @Deprecated("Legacy Android callback")
        override fun onCharacteristicRead(current: BluetoothGatt, characteristic: BluetoothGattCharacteristic, code: Int) {
            @Suppress("DEPRECATION")
            val bytes = characteristic.value?.copyOf() ?: byteArrayOf()
            dispatch { if (characteristic.uuid == K7Protocol.STATUS) gotCapabilities(current, bytes, code) }
        }
        override fun onCharacteristicRead(current: BluetoothGatt, characteristic: BluetoothGattCharacteristic, value: ByteArray, code: Int) {
            val bytes = value.copyOf()
            dispatch { if (characteristic.uuid == K7Protocol.STATUS) gotCapabilities(current, bytes, code) }
        }
        override fun onCharacteristicWrite(current: BluetoothGatt, characteristic: BluetoothGattCharacteristic, code: Int) = dispatch {
            if (current !== gatt || characteristic.uuid != K7Protocol.COMMAND || command == null) return@dispatch
            cancelTimer(writeTimer); writeTimer = null
            if (code != BluetoothGatt.GATT_SUCCESS) fail("写入失败，请确认已配对并重新连接", true)
            else { offset += lastPartSize; writePart() }
        }
        @Deprecated("Legacy Android callback")
        override fun onCharacteristicChanged(current: BluetoothGatt, characteristic: BluetoothGattCharacteristic) {
            @Suppress("DEPRECATION")
            val value = characteristic.value?.copyOf() ?: byteArrayOf()
            if (characteristic.uuid == K7Protocol.NOTIFY) dispatch { received(current, value) }
        }
        override fun onCharacteristicChanged(current: BluetoothGatt, characteristic: BluetoothGattCharacteristic, value: ByteArray) {
            val bytes = value.copyOf()
            if (characteristic.uuid == K7Protocol.NOTIFY) dispatch { received(current, bytes) }
        }
    }
}
