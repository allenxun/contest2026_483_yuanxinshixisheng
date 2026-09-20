package com.example.aisia.ble

import android.annotation.SuppressLint
import android.bluetooth.BluetoothAdapter
import android.bluetooth.BluetoothDevice
import android.bluetooth.BluetoothGatt
import android.bluetooth.BluetoothGattCallback
import android.bluetooth.BluetoothGattCharacteristic
import android.bluetooth.BluetoothGattDescriptor
import android.bluetooth.BluetoothGattService
import android.bluetooth.BluetoothManager
import android.bluetooth.BluetoothProfile
import android.bluetooth.le.BluetoothLeScanner
import android.bluetooth.le.ScanCallback
import android.bluetooth.le.ScanResult
import android.bluetooth.le.ScanSettings
import android.content.Context
import android.os.Build
import android.os.Handler
import android.os.Looper
import android.util.Log
import java.util.UUID
import java.util.concurrent.ConcurrentLinkedQueue
import java.util.concurrent.atomic.AtomicBoolean

/**
 * BLE 设备连接与指令管理（单例）——参考小程序 work.js 实现
 *
 * 核心流程：
 *   1. connect()：通过 MAC 直连（回退扫描）→ GATT → discoverServices → 收集可写特征值
 *   2. writeChar/writeString：向所有可写特征值发送（writeNoResponse 优先）
 *   3. 有响应写等待 onCharacteristicWrite，WRITE_NO_RESPONSE 则以系统接受写入请求为准
 */
@SuppressLint("MissingPermission")
object BleManager {

    private const val TAG = "BleManager"

    private const val SCAN_TIMEOUT_MS = 20000L
    private const val CONNECT_TIMEOUT_MS = 10000L
    private const val SERVICE_DELAY_MS = 800L
    private const val WRITE_INTERVAL_MS = 150L

    private var currentDeviceId: String = ""
    @Volatile private var bluetoothGatt: BluetoothGatt? = null
    private var bluetoothAdapter: BluetoothAdapter? = null
    private var bleScanner: BluetoothLeScanner? = null

    private val writableCharacteristics = mutableListOf<WritableChar>()

    private val writeQueue = ConcurrentLinkedQueue<WriteTask>()
    private val isWriting = AtomicBoolean(false)
    private fun abortWrites() {
        val abandoned = writeQueue.toList()
        writeQueue.clear()
        isWriting.set(false)
        clearPendingWriteState()
        abandoned.forEach { task ->
            try { task.callback(false) } catch (e: Exception) { Log.w(TAG, "发送取消回调失败", e) }
        }
    }

    @Volatile private var state: Int = BluetoothProfile.STATE_DISCONNECTED
    @Volatile private var isScanning = false
    @Volatile private var isConnecting = false

    private val mainHandler = Handler(Looper.getMainLooper())
    private var connectTimeoutRunnable: Runnable? = null
    private var scanTimeoutRunnable: Runnable? = null
    private var scanCallback: ScanCallback? = null

    var onConnectionStateChange: ((Boolean) -> Unit)? = null
    private val stateListeners = OwnedListeners<(Boolean) -> Unit>()
    private val dataListeners = OwnedListeners<(ByteArray) -> Unit>()
    fun addStateListener(owner: Any, listener: (Boolean) -> Unit) = runOnUiThread { stateListeners[owner] = listener }
    fun addDataListener(owner: Any, listener: (ByteArray) -> Unit) = runOnUiThread { dataListeners[owner] = listener }
    fun removeListeners(owner: Any) = runOnUiThread { stateListeners.remove(owner); dataListeners.remove(owner) }
    private fun emitState(value: Boolean) {
        runOnUiThread {
            (stateListeners.values.toList() + listOfNotNull(onConnectionStateChange)).forEach { it(value) }
        }
    }

    /** BLE notify 数据回调（主线程回调，每次收到一包原始字节） */
    var onDataReceived: ((ByteArray) -> Unit)? = null

    /** 协商后的 MTU，用于计算单次写入分包大小 */
    @Volatile private var mtuSize: Int = 23
    private const val REQUEST_MTU = 247

    /** CCC(0x2902) 描述符写入队列：GATT 同一时刻只允许 1 个写操作，需串行 */
    private val cccQueue = ConcurrentLinkedQueue<BluetoothGattDescriptor>()
    @Volatile private var writingCcc = false
    private var requireNotifications = false
    private var pendingCcc: BluetoothGattDescriptor? = null
    private var subscribedCount = 0
    private val cccDescriptorUuid = UUID.fromString("00002902-0000-1000-8000-00805f9b34fb")

    private data class WritableChar(val serviceId: String, val characteristicId: String)
    private data class WriteTask(val data: ByteArray, val cmdName: String, val callback: (Boolean) -> Unit)

    // ===== 对外 API =====

    fun isConnected(): Boolean =
        state == BluetoothProfile.STATE_CONNECTED && !isConnecting && bluetoothGatt != null && writableCharacteristics.isNotEmpty()

    fun getDeviceId(): String = currentDeviceId
    fun getWritableCharCount(): Int = writableCharacteristics.size

    /**
     * 通过 MAC 地址直接连接（与小程序 wx.createBLEConnection 一致）
     * 直连失败回退到扫描
     */
    fun connect(
        context: Context,
        targetDeviceId: String,
        requireNotifications: Boolean = false,
        callback: (Boolean, String?) -> Unit
    ) {
        if (Looper.myLooper() != Looper.getMainLooper()) {
            mainHandler.post { connect(context, targetDeviceId, requireNotifications, callback) }; return
        }
        if (targetDeviceId.isBlank()) { callback(false, "设备ID为空"); return }
        if (isConnecting) { callback(false, "正在连接中，请稍候"); return }
        if (isConnected() && currentDeviceId.equals(targetDeviceId, ignoreCase = true) &&
            (!requireNotifications || subscribedCount > 0)) {
            callback(true, null); return
        }
        disconnectInternal()
        this.requireNotifications = requireNotifications

        currentDeviceId = targetDeviceId.uppercase()
        isConnecting = true

        val bluetoothManager = context.getSystemService(Context.BLUETOOTH_SERVICE) as? BluetoothManager
        bluetoothAdapter = bluetoothManager?.adapter
        if (bluetoothAdapter == null || bluetoothAdapter?.isEnabled != true) {
            isConnecting = false; callback(false, "请先开启蓝牙"); return
        }
        bleScanner = bluetoothAdapter?.bluetoothLeScanner

        // ★ 优先通过 MAC 地址直连
        try {
            val device = bluetoothAdapter?.getRemoteDevice(currentDeviceId)
            if (device != null) {
                Log.d(TAG, "通过 MAC 地址直连设备: $currentDeviceId")
                connectDevice(context, device, callback)
                return
            }
        } catch (e: IllegalArgumentException) {
            Log.w(TAG, "MAC 地址无效: $currentDeviceId, 回退到扫描")
        } catch (e: Throwable) {
            Log.w(TAG, "直连异常: ${e.message}, 回退到扫描")
        }

        Log.d(TAG, "回退到扫描模式: $currentDeviceId")
        startScanAndConnect(context, callback)
    }

    /** 扫描并连接（回退方案） */
    private fun startScanAndConnect(context: Context, callback: (Boolean, String?) -> Unit) {
        scanTimeoutRunnable = Runnable {
            stopScan(); isConnecting = false
            callback(false, "未发现设备，请靠近设备重试")
        }
        mainHandler.postDelayed(scanTimeoutRunnable!!, SCAN_TIMEOUT_MS)

        val scanTarget = currentDeviceId
        scanCallback = object : ScanCallback() {
            override fun onScanResult(callbackType: Int, result: ScanResult?) {
                if (Looper.myLooper() != Looper.getMainLooper()) { mainHandler.post { onScanResult(callbackType, result) }; return }
                if (!isScanning || scanCallback !== this || currentDeviceId != scanTarget) return
                result ?: return
                if (result.device.address.uppercase() == currentDeviceId) {
                    Log.d(TAG, "扫描发现目标设备: ${result.device.address}")
                    stopScan()
                    connectDevice(context, result.device, callback)
                }
            }
            override fun onScanFailed(errorCode: Int) {
                if (Looper.myLooper() != Looper.getMainLooper()) { mainHandler.post { onScanFailed(errorCode) }; return }
                if (scanCallback !== this) return
                stopScan(); isConnecting = false
                runOnUiThread { callback(false, "蓝牙扫描失败") }
            }
        }
        try {
            bleScanner?.startScan(null, ScanSettings.Builder().setScanMode(ScanSettings.SCAN_MODE_LOW_LATENCY).build(), scanCallback)
            isScanning = true
        } catch (e: Throwable) {
            stopScan(); isConnecting = false
            runOnUiThread { callback(false, "启动扫描失败: ${e.message}") }
        }
    }

    /** 直接连接 BluetoothDevice */
    fun connectDevice(context: Context, device: BluetoothDevice, callback: (Boolean, String?) -> Unit) {
        if (Looper.myLooper() != Looper.getMainLooper()) {
            mainHandler.post { connectDevice(context, device, callback) }; return
        }
        currentDeviceId = device.address.uppercase()
        isConnecting = true

        pendingConnectCallback = callback
        mtuSize = 23
        subscribedCount = 0
        connectTimeoutRunnable = Runnable {
            failConnect(if (writingCcc) "设备通知订阅超时，请重试" else "设备连接超时，请重试")
        }
        mainHandler.postDelayed(connectTimeoutRunnable!!, CONNECT_TIMEOUT_MS)

        Log.d(TAG, "开始 GATT 连接: ${device.address}")
        try {
            bluetoothGatt = if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.M) {
                device.connectGatt(context, false, gattCallback, BluetoothDevice.TRANSPORT_LE)
            } else {
                device.connectGatt(context, false, gattCallback)
            }
        } catch (e: Throwable) {
            connectTimeoutRunnable?.let { mainHandler.removeCallbacks(it) }
            isConnecting = false
            failConnect("连接异常: ${e.message}")
        }
    }

    /** 发送单个字符指令 */
    fun writeChar(cmd: Char, callback: (Boolean) -> Unit = {}) {
        val bytes = byteArrayOf(cmd.code.toByte())
        writeBytes(bytes, "'$cmd'", callback)
    }

    /** 发送字符串指令（ASCII 编码） */
    fun writeString(str: String, callback: (Boolean) -> Unit = {}) {
        val bytes = str.toByteArray(Charsets.US_ASCII)
        writeBytes(bytes, "\"$str\"", callback)
    }

    fun disconnect() { runOnUiThread { disconnectInternal() } }

    fun writeUtf8Private(value: String, callback: (Boolean) -> Unit) {
        writeBytes(value.toByteArray(Charsets.UTF_8), "Wi-Fi credentials", callback)
    }

    // ===== 内部实现 =====

    private var pendingConnectCallback: ((Boolean, String?) -> Unit)? = null

    private fun runOnUiThread(block: () -> Unit) {
        if (Looper.myLooper() == Looper.getMainLooper()) block() else mainHandler.post { block() }
    }

    private fun stopScan() {
        if (isScanning) { try { scanCallback?.let { bleScanner?.stopScan(it) } } catch (_: Throwable) {} ; isScanning = false }
        scanTimeoutRunnable?.let { mainHandler.removeCallbacks(it) }; scanTimeoutRunnable = null; scanCallback = null
    }

    private fun disconnectInternal() {
        stopScan()
        cccQueue.clear(); writingCcc = false
        pendingCcc = null; subscribedCount = 0
        pendingConnectCallback = null
        connectTimeoutRunnable?.let { mainHandler.removeCallbacks(it) }; connectTimeoutRunnable = null
        try { bluetoothGatt?.disconnect() } catch (_: Throwable) {}
        try { bluetoothGatt?.close() } catch (_: Throwable) {}
        bluetoothGatt = null; writableCharacteristics.clear()
        state = BluetoothProfile.STATE_DISCONNECTED; isConnecting = false
        abortWrites()
        emitState(false)
    }

    private val gattCallback = object : BluetoothGattCallback() {
        override fun onConnectionStateChange(gatt: BluetoothGatt?, status: Int, newState: Int) {
            if (Looper.myLooper() != Looper.getMainLooper()) { mainHandler.post { onConnectionStateChange(gatt, status, newState) }; return }
            if (gatt !== bluetoothGatt || gatt == null) return
            Log.d(TAG, "onConnectionStateChange: status=$status, newState=$newState")
            if (newState == BluetoothProfile.STATE_CONNECTED) {
                state = BluetoothProfile.STATE_CONNECTED
                // 协商更大 MTU，便于传输 WIFI 列表等较长数据（失败则保持默认 23）
                try { gatt?.requestMtu(REQUEST_MTU) } catch (_: Throwable) {}
                mainHandler.postDelayed({
                    if (gatt !== bluetoothGatt) return@postDelayed
                    try { if (gatt?.discoverServices() != true) failConnect("服务发现发起失败") }
                    catch (e: Throwable) { failConnect("服务发现失败") }
                }, SERVICE_DELAY_MS)
            } else if (newState == BluetoothProfile.STATE_DISCONNECTED) {
                connectTimeoutRunnable?.let { mainHandler.removeCallbacks(it) }
                cccQueue.clear(); pendingCcc = null; writingCcc = false; subscribedCount = 0

                state = BluetoothProfile.STATE_DISCONNECTED; writableCharacteristics.clear(); isConnecting = false
                try { gatt?.close() } catch (_: Throwable) {}; bluetoothGatt = null
                abortWrites()
                runOnUiThread { emitState(false) }
                pendingConnectCallback?.let { cb -> pendingConnectCallback = null; runOnUiThread { cb(false, "设备连接断开") } }
            }
        }

        override fun onServicesDiscovered(gatt: BluetoothGatt?, status: Int) {
            if (Looper.myLooper() != Looper.getMainLooper()) { mainHandler.post { onServicesDiscovered(gatt, status) }; return }
            if (gatt !== bluetoothGatt || gatt == null) return
            Log.d(TAG, "onServicesDiscovered: status=$status")
            if (status != BluetoothGatt.GATT_SUCCESS || gatt == null) { failConnect("服务发现失败"); return }

            Log.d(TAG, "发现服务数量: ${gatt.services.size}")
            writableCharacteristics.clear()
            val writeMask = BluetoothGattCharacteristic.PROPERTY_WRITE or BluetoothGattCharacteristic.PROPERTY_WRITE_NO_RESPONSE
            for (svc in gatt.services) {
                Log.d(TAG, "  Service: ${svc.uuid}")
                for (ch in svc.characteristics) {
                    Log.d(TAG, "    Char: ${ch.uuid} props=${ch.properties}")
                    if ((ch.properties and writeMask) != 0) {
                        writableCharacteristics.add(WritableChar(svc.uuid.toString(), ch.uuid.toString()))
                    }
                }
            }

            if (writableCharacteristics.isNotEmpty()) {
                Log.i(TAG, "收集到 ${writableCharacteristics.size} 个可写特征值")
                // 启用 notify：setCharacteristicNotification + 写 CCC 描述符，设备才会真正推送数据
                for (svc in gatt.services) for (ch in svc.characteristics) {
                    val notifyMask = BluetoothGattCharacteristic.PROPERTY_NOTIFY or BluetoothGattCharacteristic.PROPERTY_INDICATE
                    if ((ch.properties and notifyMask) != 0) {
                        try {
                            val ccc = ch.getDescriptor(cccDescriptorUuid)
                            if (ccc != null && gatt.setCharacteristicNotification(ch, true)) {
                                cccQueue.offer(ccc)
                            } else if (requireNotifications) {
                                failConnect("设备通知通道无法订阅"); return
                            }
                        } catch (_: Throwable) {
                            if (requireNotifications) { failConnect("设备通知初始化失败"); return }
                        }
                    }
                }
                pollCccWrite()
            } else {
                failConnect("未找到可写的特征值")
            }
        }

        override fun onCharacteristicWrite(gatt: BluetoothGatt?, characteristic: BluetoothGattCharacteristic?, status: Int) {
            if (Looper.myLooper() != Looper.getMainLooper()) { mainHandler.post { onCharacteristicWrite(gatt, characteristic, status) }; return }
            if (gatt !== bluetoothGatt) return
            Log.d(TAG, "onCharacteristicWrite: char=${characteristic?.uuid}, status=$status")
            // 串行写：收到 WRITE_TYPE_DEFAULT 回调后，推进到下一个特征值
            val g = pendingWriteGatt
            val t = pendingWriteTask
            val expectedCharacteristicId = pendingWriteCharacteristicId
            if (
                g != null && t != null && gatt != null &&
                characteristic?.uuid?.toString() == expectedCharacteristicId
            ) {
                val nextIndex = pendingWriteIndex
                clearPendingWriteState()
                if (status == BluetoothGatt.GATT_SUCCESS) {
                    pendingWriteSuccessCount++
                } else {
                    Log.w(TAG, "  write 回调失败: char=$expectedCharacteristicId, status=$status")
                }
                Log.d(TAG, "  ↳ write 回调收到，推进到第 $nextIndex 个特征值")
                writeToCharacteristic(gatt, t, nextIndex)
            }
        }

        override fun onMtuChanged(gatt: BluetoothGatt?, mtu: Int, status: Int) {
            if (Looper.myLooper() != Looper.getMainLooper()) { mainHandler.post { onMtuChanged(gatt, mtu, status) }; return }
            if (gatt !== bluetoothGatt) return
            Log.d(TAG, "onMtuChanged: mtu=$mtu, status=$status")
            if (status == BluetoothGatt.GATT_SUCCESS) mtuSize = mtu
        }

        override fun onDescriptorWrite(gatt: BluetoothGatt?, descriptor: BluetoothGattDescriptor?, status: Int) {
            if (Looper.myLooper() != Looper.getMainLooper()) { mainHandler.post { onDescriptorWrite(gatt, descriptor, status) }; return }
            if (gatt !== bluetoothGatt || descriptor == null || descriptor !== pendingCcc) return
            Log.d(TAG, "onDescriptorWrite: ${descriptor?.uuid}, status=$status")
            pendingCcc = null
            if (status != BluetoothGatt.GATT_SUCCESS && requireNotifications) {
                failConnect("设备通知订阅失败（$status）"); return
            }
            if (status == BluetoothGatt.GATT_SUCCESS) subscribedCount++
            pollCccWrite()
        }

        @Deprecated("API 33+ 使用带 value 参数的重载")
        override fun onCharacteristicChanged(gatt: BluetoothGatt?, characteristic: BluetoothGattCharacteristic?) {
            @Suppress("DEPRECATION")
            handleNotify(gatt, characteristic?.value?.copyOf())
        }

        override fun onCharacteristicChanged(
            gatt: BluetoothGatt,
            characteristic: BluetoothGattCharacteristic,
            value: ByteArray
        ) {
            handleNotify(gatt, value.copyOf())
        }
    }

    private fun failConnect(msg: String) {
        pendingCcc = null; subscribedCount = 0
        connectTimeoutRunnable?.let { mainHandler.removeCallbacks(it) }; connectTimeoutRunnable = null
        isConnecting = false
        try { bluetoothGatt?.close() } catch (_: Throwable) {}
        bluetoothGatt = null; writableCharacteristics.clear(); cccQueue.clear(); writingCcc = false
        state = BluetoothProfile.STATE_DISCONNECTED
        abortWrites()
        Log.e(TAG, "failConnect: $msg")
        val cb = pendingConnectCallback; pendingConnectCallback = null
        if (cb != null) runOnUiThread { cb(false, msg) }
    }

    // ===== 写入实现：向所有可写特征值 SERIALLY 发送 =====
    // Android BLE GATT 规定：同一时刻只能有 1 个未完成的 write，必须等 onCharacteristicWrite 回调
    // 才能发送下一条。因此向多个特征值发送时必须串行化。

    private fun writeBytes(data: ByteArray, cmdName: String, callback: (Boolean) -> Unit) {
        if (Looper.myLooper() != Looper.getMainLooper()) {
            val copy = data.copyOf()
            mainHandler.post { writeBytes(copy, cmdName, callback) }; return
        }
        if (!isConnected()) {
            Log.w(TAG, "writeBytes: 设备未连接，丢弃 $cmdName"); callback(false); return
        }
        // 超过单包上限(MTU-3)时拆成多包，经写队列串行发送，最后一包触发回调
        val chunkSize = maxOf(20, mtuSize - 3)
        if (data.size <= chunkSize) {
            writeQueue.offer(WriteTask(data, cmdName, callback))
        } else {
            var offset = 0
            var partIndex = 1
            var allPartsSucceeded = true
            while (offset < data.size) {
                val end = minOf(data.size, offset + chunkSize)
                val part = data.copyOfRange(offset, end)
                val isLast = end >= data.size
                writeQueue.offer(
                    WriteTask(part, if (isLast) cmdName else "$cmdName#$partIndex") { ok ->
                        allPartsSucceeded = allPartsSucceeded && ok
                        if (isLast) callback(allPartsSucceeded)
                    }
                )
                offset = end
                partIndex++
            }
            Log.d(TAG, "writeBytes: $cmdName 共 ${data.size} 字节，拆为 ${partIndex - 1} 包(单包 $chunkSize 字节)")
        }
        if (isWriting.compareAndSet(false, true)) processNextWrite()
    }

    private val rxLock = Any()
    private val incoming = java.util.ArrayDeque<ByteArray>()
    private var incomingSize = 0
    private var incomingGatt: BluetoothGatt? = null
    private var drainScheduled = false
    /** Coalesce bursts without dropping individual packets or doing JSON work here. */
    private fun handleNotify(gatt: BluetoothGatt?, value: ByteArray?) {
        if (gatt == null || gatt !== bluetoothGatt || value == null || value.isEmpty()) return
        synchronized(rxLock) {
            if (gatt !== bluetoothGatt) return
            if (incomingGatt !== gatt) { incoming.clear(); incomingSize = 0; incomingGatt = gatt }
            if (incomingSize + value.size > 256 * 1024) {
                incoming.clear(); incomingSize = 0
                Log.w(TAG, "通知缓冲区溢出，丢弃不完整消息")
            }
            incoming.add(value); incomingSize += value.size
            if (drainScheduled) return
            drainScheduled = true
        }
        mainHandler.postDelayed({
            val batch: Pair<BluetoothGatt?, List<ByteArray>>
            synchronized(rxLock) {
                batch = incomingGatt to incoming.toList()
                incoming.clear(); incomingSize = 0; drainScheduled = false
            }
            if (batch.first !== bluetoothGatt) return@postDelayed
            val listeners = dataListeners.values.toList() + listOfNotNull(onDataReceived)
            batch.second.forEach { bytes -> listeners.forEach { it(bytes.copyOf()) } }
        }, 16)
    }

    private fun pollCccWrite() {
        val gatt = bluetoothGatt ?: return
        val d = cccQueue.poll()
        if (d == null) {
            writingCcc = false
            if (requireNotifications && subscribedCount == 0) {
                failConnect("设备没有可用的通知通道"); return
            }
            connectTimeoutRunnable?.let { mainHandler.removeCallbacks(it) }
            connectTimeoutRunnable = null
            isConnecting = false
            val cb = pendingConnectCallback; pendingConnectCallback = null
            runOnUiThread { emitState(true); cb?.invoke(true, null) }
            return
        }
        writingCcc = true
        pendingCcc = d
        try {
            val value = if ((d.characteristic.properties and BluetoothGattCharacteristic.PROPERTY_NOTIFY) != 0)
                BluetoothGattDescriptor.ENABLE_NOTIFICATION_VALUE else BluetoothGattDescriptor.ENABLE_INDICATION_VALUE
            @Suppress("DEPRECATION")
            d.value = value
            @Suppress("DEPRECATION")
            val ok = gatt.writeDescriptor(d)
            if (!ok) {
                pendingCcc = null
                if (requireNotifications) failConnect("无法发送通知订阅请求") else pollCccWrite()
            }
        } catch (_: Throwable) {
            pendingCcc = null
            if (requireNotifications) failConnect("设备通知订阅异常") else pollCccWrite()
        }
    }

    /**
     * 处理队列中下一条写入任务
     * 串行化发送到所有可写特征值（等待 onCharacteristicWrite 回调）
     */
    private fun processNextWrite() {
        if (writingCcc) {
            mainHandler.postDelayed({ processNextWrite() }, 50)
            return
        }
        val gatt = bluetoothGatt
        if (gatt == null) { abortWrites(); return }

        val task = writeQueue.peek() ?: run { isWriting.set(false); return }
        val chars = writableCharacteristics.toList()
        if (chars.isEmpty()) { abortWrites(); return }

        // 字节日志（便于调试确认指令格式）
        Log.d(TAG, ">>> 发送指令: ${task.cmdName} 长度=${task.data.size}")

        // 启动串行写入：从第 0 个特征值开始
        pendingWriteIndex = 0
        pendingWriteSuccessCount = 0
        pendingWriteTotal = chars.size

        writeToCharacteristic(gatt, task, 0)
    }

    /**
     * 向第 charIndex 个特征值写入。
     * - 对 WRITE_TYPE_NO_RESPONSE：postDelay 100ms 后自动推进到下一个（系统不回调 onCharacteristicWrite）
     * - 对 WRITE_TYPE_DEFAULT：等 onCharacteristicWrite 回调后推进
     */
    private fun writeToCharacteristic(gatt: BluetoothGatt, task: WriteTask, charIndex: Int) {
        if (gatt !== bluetoothGatt || writeQueue.peek() !== task) return
        val chars = writableCharacteristics.toList()
        if (charIndex >= chars.size) {
            // 全部发送完毕
            val anySuccess = pendingWriteTotal > 0 && pendingWriteSuccessCount == pendingWriteTotal
            Log.d(TAG, "<<< 指令 ${task.cmdName} 发送完毕: success=$pendingWriteSuccessCount/$pendingWriteTotal")
            mainHandler.postDelayed({
                if (gatt !== bluetoothGatt || writeQueue.peek() !== task) return@postDelayed
                writeQueue.poll()
                // Keep the lane busy while callbacks may enqueue the next command.
                task.callback(anySuccess)
                if (gatt !== bluetoothGatt) return@postDelayed
                if (writeQueue.isNotEmpty()) processNextWrite() else isWriting.set(false)
            }, WRITE_INTERVAL_MS)
            return
        }

        val wc = chars[charIndex]
        try {
            val svc = gatt.getService(UUID.fromString(wc.serviceId))
            if (svc == null) { Log.w(TAG, "  [$charIndex] 服务未找到: ${wc.serviceId}"); writeToCharacteristic(gatt, task, charIndex + 1); return }
            val ch = svc.getCharacteristic(UUID.fromString(wc.characteristicId))
            if (ch == null) { Log.w(TAG, "  [$charIndex] 特征值未找到: ${wc.characteristicId}"); writeToCharacteristic(gatt, task, charIndex + 1); return }

            val hasNoResp = (ch.properties and BluetoothGattCharacteristic.PROPERTY_WRITE_NO_RESPONSE) != 0
            val writeType = if (hasNoResp) BluetoothGattCharacteristic.WRITE_TYPE_NO_RESPONSE else BluetoothGattCharacteristic.WRITE_TYPE_DEFAULT

            val ok = if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU) {
                val status = gatt.writeCharacteristic(ch, task.data, writeType)
                Log.d(TAG, "  [$charIndex/${chars.size}] service=${wc.serviceId.takeLast(6)} char=${wc.characteristicId.takeLast(6)} type=${if (hasNoResp) "NoResp" else "Default"} status=$status")
                status == BluetoothGatt.GATT_SUCCESS
            } else {
                @Suppress("DEPRECATION")
                ch.value = task.data
                @Suppress("DEPRECATION")
                ch.writeType = writeType
                val ok2 = gatt.writeCharacteristic(ch)
                Log.d(TAG, "  [$charIndex/${chars.size}] service=${wc.serviceId.takeLast(6)} char=${wc.characteristicId.takeLast(6)} type=${if (hasNoResp) "NoResp" else "Default"} ok=$ok2")
                ok2
            }

            // 根据类型决定推进方式
            if (hasNoResp) {
                // 无响应写没有 GATT 回执；这里只能确认系统接受了写入请求。
                if (ok) pendingWriteSuccessCount++
                // writeNoResponse 不会回调 onCharacteristicWrite，100ms 后推进
                mainHandler.postDelayed({ writeToCharacteristic(gatt, task, charIndex + 1) }, 100L)
            } else if (!ok) {
                // 写请求未被系统接受，无需等待不会到来的回调。
                writeToCharacteristic(gatt, task, charIndex + 1)
            } else {
                // write 类型，等 onCharacteristicWrite 回调后推进（最多 800ms 超时兜底）
                pendingWriteGatt = gatt
                pendingWriteTask = task
                pendingWriteIndex = charIndex + 1
                pendingWriteCharacteristicId = wc.characteristicId
                pendingWriteTimeoutRunnable = Runnable {
                    if (
                        pendingWriteGatt === gatt &&
                        pendingWriteTask === task &&
                        pendingWriteIndex == charIndex + 1 &&
                        pendingWriteCharacteristicId == wc.characteristicId
                    ) {
                        Log.w(TAG, "  [$charIndex] write 回调超时，强制推进")
                        clearPendingWriteState()
                        writeToCharacteristic(gatt, task, charIndex + 1)
                    }
                }.also { mainHandler.postDelayed(it, 800L) }
            }
        } catch (e: Throwable) {
            Log.e(TAG, "write 异常 [${charIndex}]", e)
            writeToCharacteristic(gatt, task, charIndex + 1)
        }
    }

    @Volatile private var pendingWriteIndex = 0
    @Volatile private var pendingWriteSuccessCount = 0
    @Volatile private var pendingWriteTotal = 0
    @Volatile private var pendingWriteGatt: BluetoothGatt? = null
    @Volatile private var pendingWriteTask: WriteTask? = null
    @Volatile private var pendingWriteCharacteristicId: String? = null
    private var pendingWriteTimeoutRunnable: Runnable? = null

    private fun clearPendingWriteState() {
        pendingWriteTimeoutRunnable?.let { mainHandler.removeCallbacks(it) }
        pendingWriteTimeoutRunnable = null
        pendingWriteGatt = null
        pendingWriteTask = null
        pendingWriteCharacteristicId = null
    }
}
