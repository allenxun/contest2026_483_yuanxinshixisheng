package com.example.aisia.ui.openvela

import android.content.Context
import android.os.Handler
import android.os.Looper
import com.example.aisia.ble.BleManager

/** App-scoped session survives Activity recreation. No mock device acknowledgements. */
object OpenVelaSession {
    enum class State { DISCONNECTED, CONNECTING, INITIALIZING, READY, STARTING, RUNNING, STOPPING, STOPPED, COMPLETED, UNKNOWN, QUERYING }
    var state = State.DISCONNECTED
        private set
    var address = ""
        private set
    var planKey = ""
        private set
    var message = "请连接 openVela 设备"
        private set
    private var context: Context? = null
    private var generation = 0
    private val handler = Handler(Looper.getMainLooper())
    private val buffer = com.example.aisia.ble.BleMessageFramer()
    private val observers = linkedSetOf<() -> Unit>()
    private var timeout: Runnable? = null
    private var startedAt = 0L
    private var mayBeWorking = false
    private val prefs get() = context!!.getSharedPreferences("openvela_work_session", Context.MODE_PRIVATE)
    val connected get() = address.isNotBlank() && BleManager.isConnected() && BleManager.getDeviceId().equals(address, true)
    val uncertainWork get() = mayBeWorking || state in setOf(State.STARTING, State.RUNNING, State.STOPPING, State.UNKNOWN, State.QUERYING)
    val busy get() = state in setOf(State.CONNECTING, State.INITIALIZING, State.STARTING, State.STOPPING, State.QUERYING)

    fun attach(ctx: Context) {
        if (context != null) return
        context = ctx.applicationContext
        if (prefs.getBoolean("unconfirmed", false)) {
            mayBeWorking = true
            address = prefs.getString("address", "") ?: ""
            planKey = prefs.getString("plan", "") ?: ""
            state = State.UNKNOWN
            message = "上次工作尚未确认结束，请重新连接并查询设备状态"
        }
    }
    fun observe(observer: () -> Unit) { observers.add(observer); observer() }
    fun selectPlan(key: String) {
        if (!uncertainWork && !busy) {
            planKey = key
            prefs.edit().putString("plan", key).apply()
        }
        if (!connected && state in setOf(State.READY, State.RUNNING, State.STARTING, State.STOPPING)) {
            cancelTimeout()
            publish(if (uncertainWork) State.UNKNOWN else State.DISCONNECTED, "连接已断开，请重新连接并查询设备状态")
        }
    }
    fun remove(observer: () -> Unit) { observers.remove(observer) }
    private fun publish(next: State, text: String) {
        if (next in setOf(State.STARTING, State.RUNNING, State.STOPPING, State.UNKNOWN)) mayBeWorking = true
        if (next in setOf(State.READY, State.STOPPED, State.COMPLETED)) mayBeWorking = false
        state = next; message = text
        prefs.edit().putBoolean("unconfirmed", uncertainWork).putString("address", address)
            .putString("plan", planKey).apply()
        observers.toList().forEach { it() }
    }
    private fun cancelTimeout() { timeout?.let { handler.removeCallbacks(it) }; timeout = null }
    private fun waitForReply(text: String) {
        cancelTimeout()
        timeout = Runnable { publish(State.UNKNOWN, text) }.also { handler.postDelayed(it, 10000) }
    }
    fun connect(target: String, selectedPlan: String) {
        if (busy) return
        if (uncertainWork && address.isNotBlank() && !address.equals(target, true)) return
        val resume = uncertainWork
        address = target
        if (!resume) planKey = selectedPlan
        buffer.reset()
        cancelTimeout()
        val token = ++generation
        publish(State.CONNECTING, "正在连接并订阅设备通知…")
        BleManager.addDataListener(this) { bytes ->
            if (token == generation && BleManager.getDeviceId().equals(address, true)) receive(bytes)
        }
        BleManager.addStateListener(this) { ok ->
            if (!ok && token == generation && state != State.CONNECTING) {
                cancelTimeout(); buffer.reset()
                publish(if (uncertainWork) State.UNKNOWN else State.DISCONNECTED,
                    if (uncertainWork) "连接已断开，设备可能仍在工作；请重新连接" else "设备已断开，请重新连接")
            }
        }
        BleManager.connect(context!!, target, requireNotifications = true) { ok, error ->
            if (token != generation) return@connect
            if (!ok) {
                publish(if (resume) State.UNKNOWN else State.DISCONNECTED, error ?: "连接失败，请重试")
            } else {
                publish(State.INITIALIZING, if (resume) "已连接，正在查询设备状态…" else "已连接，正在初始化设备…")
                waitForReply("设备未确认状态，可查询状态或尝试停止")
                send(if (resume) OpenVelaCommands.QUERY else OpenVelaCommands.INITIALIZE)
            }
        }
    }
    fun start(selectedPlan: String) {
        if (!connected || selectedPlan != planKey || state !in setOf(State.READY, State.STOPPED, State.COMPLETED)) return
        publish(State.STARTING, "开始指令已发出，等待设备确认…")
        waitForReply("未确认设备是否启动，请查询状态；不要重复启动")
        send(OpenVelaCommands.START)
    }
    fun stop() {
        if (!connected || state == State.STOPPING) return
        publish(State.STOPPING, "正在停止，等待设备确认…")
        waitForReply("未确认设备停止，请检查设备或重试停止")
        send(OpenVelaCommands.STOP)
    }
    fun query() {
        if (!connected || busy) return
        publish(State.QUERYING, "正在查询设备状态…")
        waitForReply("设备状态未确认，请检查设备")
        send(OpenVelaCommands.QUERY)
    }
    private fun send(command: Char) {
        val token = generation
        val expectedState = state
        BleManager.writeChar(command) { ok ->
            if (token == generation && state == expectedState && !ok) {
                cancelTimeout()
                publish(State.UNKNOWN, "指令未全部发送成功，设备状态未确认，请查询或重试停止")
            }
        }
    }
    private fun receive(bytes: ByteArray) {
        buffer.feed(bytes).forEach { handleReply(it) }
    }
    private fun handleReply(reply: String) {
        if (!connected) return
        // A working heartbeat is not an acknowledgement of the pending stop.
        if (state == State.STOPPING && reply in setOf("running", "ready")) return
        if (state == State.RUNNING && reply == "running") return
        val next = when (reply) {
            "ready" -> if (state == State.INITIALIZING || state == State.UNKNOWN || state == State.QUERYING) State.READY else return
            "running" -> State.RUNNING
            "stopped" -> State.STOPPED
            "completed" -> State.COMPLETED
            "error" -> State.UNKNOWN
            else -> return
        }
        cancelTimeout()
        if (next == State.RUNNING && startedAt == 0L) startedAt = System.currentTimeMillis()
        if (next == State.STOPPED || next == State.COMPLETED) {
            prefs.edit().putString("last_result", "${planKey}|${next.name}|${System.currentTimeMillis()}").apply()
            startedAt = 0
        }
        publish(next, when (next) {
            State.READY -> "设备已就绪，可以开始工作"
            State.RUNNING -> "设备已确认：工作中"
            State.STOPPED -> "设备已确认：已停止"
            State.COMPLETED -> "设备已确认：本次护理已完成"
            else -> "设备返回异常，请检查设备并查询状态"
        })
    }
}
