package com.example.aisia.ui.openvela

import android.Manifest
import android.annotation.SuppressLint
import android.bluetooth.BluetoothDevice
import android.bluetooth.BluetoothManager
import android.bluetooth.le.ScanCallback
import android.bluetooth.le.ScanResult
import android.bluetooth.le.ScanSettings
import android.content.Intent
import android.content.pm.PackageManager
import android.graphics.Color
import android.graphics.Typeface
import android.graphics.drawable.GradientDrawable
import android.os.Build
import android.os.Bundle
import android.os.Handler
import android.os.Looper
import android.view.View
import android.view.Gravity
import com.example.aisia.R
import android.widget.*
import androidx.activity.OnBackPressedCallback
import androidx.activity.result.contract.ActivityResultContracts
import androidx.appcompat.app.AlertDialog
import androidx.appcompat.app.AppCompatActivity
import androidx.core.content.ContextCompat
import androidx.core.view.ViewCompat
import androidx.core.view.WindowInsetsCompat
import com.example.aisia.privacy.PrivacyManager

abstract class OpenVelaPage : AppCompatActivity() {
    private val requests = mutableListOf<okhttp3.Call>()
    private var requestEpoch = 0
    private var ownerToken: String? = null
    protected lateinit var content: LinearLayout
    protected lateinit var dock: LinearLayout
    protected fun dp(value: Int) = (value * resources.displayMetrics.density).toInt()
    protected fun page(title: String, showHeading: Boolean = true, centerTitle: Boolean = false) {
        val root = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            setBackgroundColor(Color.rgb(243, 247, 252))
        }
        ViewCompat.setOnApplyWindowInsetsListener(root) { view, insets ->
            val bars = insets.getInsets(WindowInsetsCompat.Type.systemBars())
            view.setPadding(bars.left, bars.top, bars.right, bars.bottom); insets
        }
        root.addView(LinearLayout(this).apply {
            gravity = Gravity.CENTER_VERTICAL
            setPadding(dp(8), 0, dp(if (centerTitle) 8 else 20), 0)
            addView(ImageButton(this@OpenVelaPage).apply {
                setImageResource(R.drawable.ic_arrow_back)
                setColorFilter(OpenVelaBlue.ink)
                setBackgroundColor(Color.TRANSPARENT)
                setPadding(dp(12), dp(12), dp(12), dp(12))
                contentDescription = "返回"
                setOnClickListener { onBackPressedDispatcher.onBackPressed() }
            }, LinearLayout.LayoutParams(dp(48), dp(56)))
            if (centerTitle) {
                addView(OpenVelaBlue.text(this@OpenVelaPage, title, 18, true).apply {
                    gravity = Gravity.CENTER
                }, LinearLayout.LayoutParams(0, -2, 1f))
                // Match the back button width so the title centers on the page.
                addView(Space(this@OpenVelaPage), LinearLayout.LayoutParams(dp(48), dp(56)))
            } else {
                addView(OpenVelaBlue.text(this@OpenVelaPage, title, 18, true))
            }
        }, LinearLayout.LayoutParams(-1, dp(60)))
        val scroll = ScrollView(this)
        content = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL; setPadding(dp(20), dp(12), dp(20), dp(32))
        }
        scroll.isFillViewport = true
        scroll.addView(content)
        root.addView(scroll, LinearLayout.LayoutParams(-1, 0, 1f))
        dock = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            setPadding(dp(20), dp(8), dp(20), dp(16))
            setBackgroundColor(OpenVelaBlue.canvas)
            visibility = View.GONE
        }
        root.addView(dock)
        setContentView(root)
        if (showHeading) label(title, 28, true)
    }
    protected fun label(value: String, size: Int = 16, bold: Boolean = false): TextView =
        TextView(this).apply {
            text = value; textSize = size.toFloat()
            setTextColor(Color.rgb(49, 69, 94))
            if (bold) setTypeface(null, Typeface.BOLD)
            setPadding(0, dp(10), 0, dp(10))
            content.addView(this)
        }
    protected fun card(title: String, subtitle: String, action: (() -> Unit)? = null) {
        val box = LinearLayout(this).apply {
            orientation = LinearLayout.HORIZONTAL
            gravity = Gravity.CENTER_VERTICAL
            background = GradientDrawable().apply { setColor(Color.WHITE); cornerRadius = dp(18).toFloat() }
            setPadding(dp(18), dp(18), dp(18), dp(18))
            layoutParams = LinearLayout.LayoutParams(-1, -2).apply { topMargin = dp(12) }
        }
        val details = LinearLayout(this).apply { orientation = LinearLayout.VERTICAL }
        details.addView(TextView(this).apply {
            text = title; textSize = 18f
            setTypeface(null, Typeface.BOLD); setTextColor(Color.rgb(30, 49, 72))
        })
        details.addView(TextView(this).apply {
            text = subtitle; textSize = 14f; setTextColor(Color.rgb(83, 104, 128))
            setPadding(0, dp(10), 0, 0)
        })
        box.addView(details, LinearLayout.LayoutParams(0, -2, 1f))
        if (action != null) {
            box.addView(OpenVelaBlue.icon(this, R.drawable.ic_arrow_right, 16, OpenVelaBlue.muted),
                LinearLayout.LayoutParams(dp(16), dp(16)).apply { marginStart = dp(12) })
            box.foreground = android.graphics.drawable.RippleDrawable(android.content.res.ColorStateList.valueOf(0x183A6DF0), null, OpenVelaBlue.surface(this))
            box.isFocusable = true
            box.setOnClickListener { action() }
        }
        content.addView(box)
    }
    protected fun button(title: String, action: () -> Unit): Button = Button(this).apply {
        text = title; isAllCaps = false; minHeight = dp(52)
        setTextColor(android.content.res.ColorStateList(
            arrayOf(intArrayOf(android.R.attr.state_enabled), intArrayOf()),
            intArrayOf(Color.WHITE, Color.rgb(111, 129, 154))
        ))
        backgroundTintList = null
        val states = android.graphics.drawable.StateListDrawable().apply {
            addState(intArrayOf(-android.R.attr.state_enabled), OpenVelaBlue.surface(this@OpenVelaPage, Color.rgb(222, 231, 243), 12))
            addState(intArrayOf(), OpenVelaBlue.surface(this@OpenVelaPage, OpenVelaBlue.blue, 12))
        }
        background = android.graphics.drawable.RippleDrawable(
            android.content.res.ColorStateList.valueOf(0x33FFFFFF), states, OpenVelaBlue.surface(this@OpenVelaPage, radius = 12)
        )
        textSize = 16f
        layoutParams = LinearLayout.LayoutParams(-1, -2).apply { topMargin = dp(12) }
        setOnClickListener { action() }; content.addView(this)
    }
    protected fun go(target: Class<*>, person: String, report: String = "", name: String = intent.getStringExtra("personName").orEmpty()) {
        startActivity(Intent(this, target).putExtra("personId", person).putExtra("reportId", report).putExtra("personName", name))
    }
    protected fun fetch(path: String, query: Map<String, String> = emptyMap(), retry: () -> Unit, done: (org.json.JSONObject) -> Unit) {
        val token = requestEpoch
        val call = OpenVelaApi.get(path, query) { result ->
            if (!isDestroyed && !isFinishing && token == requestEpoch) {
                result.fold(onSuccess = { data -> try { done(data) } catch (_: Exception) { error("接口字段不完整或数据不匹配", retry) } },
                    onFailure = {
                        if (it is OpenVelaApi.LoginRequired) {
                            startActivity(Intent(this, OpenVelaLoginActivity::class.java)); finish()
                        } else error(it.message ?: "加载失败", retry)
                    })
            }
        }
        call?.let { requests.add(it) }
    }
    protected fun error(message: String, retry: () -> Unit) { content.removeAllViews(); label(message); button("重试", retry) }
    protected fun loading() { requestEpoch++; requests.forEach { it.cancel() }; requests.clear(); content.removeAllViews(); label("加载中…") }
    override fun onResume() {
        super.onResume()
        val token = OpenVelaAuth.getToken()
        if (this !is OpenVelaLoginActivity && token == null && !isFinishing) {
            startActivity(Intent(this, OpenVelaLoginActivity::class.java)); finish(); return
        }
        if (ownerToken != null && ownerToken != token) { finish(); return }
        ownerToken = token
    }
    override fun onDestroy() { requestEpoch++; requests.forEach { it.cancel() }; requests.clear(); super.onDestroy() }
}

class OpenVelaPeopleActivity : OpenVelaPage() {
    private val people = linkedMapOf<String, OpenVelaData.Person>()
    private val cursors = mutableSetOf<String>()
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState); page("openVela 测肤列表", false, centerTitle = true)
        load()
    }
    private fun load(cursor: String? = null) {
        loading()
        if (cursor == null) { people.clear(); cursors.clear() }
        fetch("/api/v1/me/member-access-grants", mapOf("limit" to "20") + (cursor?.let { mapOf("cursor" to it) } ?: emptyMap()), { load(cursor) }) {
            val page = OpenVelaData.people(it)
            page.items.forEach { p -> people[p.id] = p }
            content.removeAllViews()
            label("查看测肤记录，了解肌肤变化", 15)
            label("已加载 " + people.size + " 位人员", 14)
            if (people.isEmpty()) label("暂无已授权人员，请先完成成员查看授权")
            val group = LinearLayout(this).apply {
                orientation = LinearLayout.VERTICAL
                background = OpenVelaBlue.surface(this@OpenVelaPeopleActivity, border = true)
            }
            people.values.forEachIndexed { index, person ->
                if (index > 0) group.addView(OpenVelaBlue.divider(this))
                group.addView(OpenVelaBlue.personRow(this, person) { go(OpenVelaRecordsActivity::class.java, person.id, name = person.name) })
            }
            content.addView(group)
            page.next?.let { next ->
                if (next == cursor || next in cursors) label("分页游标重复，请刷新后重试")
                else button("加载更多") { cursors.add(next); load(next) }
            }
            button("刷新") { load() }
        }
    }
}
class OpenVelaRecordsActivity : OpenVelaPage() {
    private val records = linkedMapOf<String, OpenVelaData.Report>()
    private val cursors = mutableSetOf<String>()
    private val person get() = intent.getStringExtra("personId").orEmpty()
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        page(intent.getStringExtra("personName").orEmpty() + " 测肤列表", false, true)
        load()
    }
    private fun load(cursor: String? = null) {
        if (person.isBlank()) { label("未找到人员，请返回重新选择"); return }
        loading()
        if (cursor == null) { records.clear(); cursors.clear() }
        fetch("/api/v1/members/" + android.net.Uri.encode(person) + "/skin-reports",
            mapOf("limit" to "20") + (cursor?.let { mapOf("cursor" to it) } ?: emptyMap()), { load(cursor) }) {
            val page = OpenVelaData.reports(it, person)
            page.items.forEach { r -> records[r.id] = r }
            content.removeAllViews()
            if (records.isEmpty()) label("暂无测肤记录")
            records.values.forEach { r -> card(r.date, r.conclusion.ifBlank { "查看完整报告" }) { go(OpenVelaReportActivity::class.java, person, r.id) } }
            page.next?.let { next ->
                if (next == cursor || next in cursors) label("分页游标重复，请刷新后重试")
                else button("加载更多") { cursors.add(next); load(next) }
            }
            button("刷新") { load() }
        }
    }
}
class OpenVelaReportActivity : OpenVelaPage() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState); page("测肤报告", false, true); load()
    }
    private fun load() {
        loading()
        val person = intent.getStringExtra("personId").orEmpty()
        val id = intent.getStringExtra("reportId").orEmpty()
        if (person.isBlank() || id.isBlank()) { label("报告来源无效"); return }
        fetch("/api/v1/skin-reports/" + android.net.Uri.encode(id), mapOf("view" to "full"), ::load) {
            val report = OpenVelaData.report(it, person)
            require(report.id == id)
            content.removeAllViews()
            label(intent.getStringExtra("personName").orEmpty() + " · " + report.date, 15)
            if (report.conclusion.isNotBlank()) card("测肤结论", report.conclusion)
            if (report.description.isNotBlank()) card("报告说明", report.description)
            report.metrics.forEach { metric -> card(metric.first, metric.second) }
            if (report.metrics.isEmpty()) label("暂无可展示的测肤指标")
            content.addView(OpenVelaFacePhotos.create(this, report))
            report.images.filter { it.second !in listOf(report.leftFaceImageUrl, report.frontFaceImageUrl, report.rightFaceImageUrl) }
                .forEach { image -> card(image.first, "查看结果图片") { OpenVelaImages.preview(this, image.second, image.first) } }
            button("查看方案") { go(OpenVelaPlanActivity::class.java, person, id) }
        }
    }
}

@SuppressLint("MissingPermission")
class OpenVelaPlanActivity : OpenVelaPage() {
    private val handler = Handler(Looper.getMainLooper())
    private var deviceDialog: AlertDialog? = null
    private var exitDialog: AlertDialog? = null
    private var scanCallback: ScanCallback? = null
    private var scanner: android.bluetooth.le.BluetoothLeScanner? = null
    private var scanning = false
    private var scanGeneration = 0
    private var exitAfterStop = false
    private var selectionInFlight = false
    private var scanHint: TextView? = null
    private lateinit var status: TextView
    private lateinit var connectButton: Button
    private lateinit var startButton: Button
    private lateinit var stopButton: Button
    private lateinit var queryButton: Button
    private var plan = ""
    private var planReady = false
    private val observer: () -> Unit = { render() }
    private val permission = registerForActivityResult(ActivityResultContracts.RequestMultiplePermissions()) { grants ->
        if (grants.values.all { it }) searchDevices()
        else Toast.makeText(this, "需要蓝牙及扫描权限，请授权后重试", Toast.LENGTH_LONG).show()
    }
    private val enableBluetooth = registerForActivityResult(ActivityResultContracts.StartActivityForResult()) {
        if (it.resultCode == RESULT_OK) searchDevices()
    }
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState); page("护肤方案", showHeading = false, centerTitle = true)
        val person = intent.getStringExtra("personId") ?: ""
        val report = intent.getStringExtra("reportId") ?: ""
        if (person.isBlank() || report.isBlank()) { label("方案来源无效，请返回报告"); return }
        plan = person + "/" + report
        OpenVelaSession.attach(this)
        OpenVelaSession.selectPlan(plan)
        loadPlan(person, report)
        status = OpenVelaBlue.text(this, "未连接", 13, color = OpenVelaBlue.muted)
        val deviceRow = LinearLayout(this).apply {
            gravity = Gravity.CENTER_VERTICAL
            background = OpenVelaBlue.surface(this@OpenVelaPlanActivity, border = true)
            setPadding(dp(14), dp(16), dp(14), dp(16))
            addView(OpenVelaBlue.icon(this@OpenVelaPlanActivity, R.drawable.ic_bluetooth, 22, OpenVelaBlue.blue))
            addView(OpenVelaBlue.text(this@OpenVelaPlanActivity, "护肤设备", 15).apply {
                setPadding(dp(12), 0, dp(8), 0)
            }, LinearLayout.LayoutParams(0, -2, 1f))
            addView(status, LinearLayout.LayoutParams(0, -2, 1f))
        }
        dock.visibility = View.VISIBLE
        dock.addView(deviceRow)
        connectButton = button("连接设备") { requestScan() }
        startButton = button("开始工作") {
            Toast.makeText(this, "正式护理需完成设备协议与人脸准入对接，暂不发送占位启动指令", Toast.LENGTH_LONG).show()
        }
        queryButton = button("查询设备状态") { OpenVelaSession.query() }
        stopButton = button("停止工作") { OpenVelaSession.stop() }
        listOf(connectButton, startButton, queryButton, stopButton).forEach { action ->
            content.removeView(action); dock.addView(action)
        }
        queryButton.setTextColor(android.content.res.ColorStateList(
            arrayOf(intArrayOf(android.R.attr.state_enabled), intArrayOf()),
            intArrayOf(OpenVelaBlue.blue, OpenVelaBlue.muted)
        ))
        queryButton.background = OpenVelaBlue.surface(this, Color.WHITE, border = true)
        onBackPressedDispatcher.addCallback(this, object : OnBackPressedCallback(true) {
            override fun handleOnBackPressed() = requestExit()
        })
    }
    private fun loadPlan(person: String, reportId: String) {
        planReady = false
        if (::status.isInitialized) render()
        loading()
        fetch("/api/v1/members/" + android.net.Uri.encode(person) + "/care-plans",
            mapOf("reportId" to reportId, "limit" to "2"), { loadPlan(person, reportId) }) outer@{ list ->
            require(list.optJSONArray("items") != null)
            val items = OpenVelaData.objects(list, "items")
            content.removeAllViews()
            if (items.isEmpty()) { label("该报告暂无护肤方案"); button("刷新") { loadPlan(person, reportId) }; return@outer }
            require(items.size == 1 && OpenVelaData.text(list, "nextCursor") == null) { "一个报告返回多个方案" }
            val summary = items.single().optJSONObject("planSummary")
            require(summary?.let { OpenVelaData.text(it, "source_report_id") }?.let { it == reportId } != false)
            val planId = OpenVelaData.text(items.single(), "planId") ?: error("缺少方案ID")
            fetch("/api/v1/care-plans/" + android.net.Uri.encode(planId), mapOf("view" to "full"), { loadPlan(person, reportId) }) detailResult@{ data ->
                val detail = OpenVelaData.plan(data)
                require(detail.id == planId)
                content.removeAllViews()
                label(intent.getStringExtra("personName").orEmpty(), 14)
                if (detail.status != "ready") {
                    label(when(detail.status) {
                        "waiting_inputs" -> "等待生成方案所需资料"
                        "generating" -> "护肤方案生成中"
                        "failed" -> "方案生成失败，请稍后重试"
                        else -> "暂不支持的方案状态"
                    })
                    button("刷新状态") { loadPlan(person, reportId) }
                    return@detailResult
                }
                planReady = true
                render()
                val hero = FrameLayout(this)
                hero.addView(ImageView(this).apply {
                    val resource = resources.getIdentifier("openvela_care_hero", "drawable", packageName)
                    if (resource != 0) setImageResource(resource)
                    scaleType = ImageView.ScaleType.CENTER_CROP
                    importantForAccessibility = View.IMPORTANT_FOR_ACCESSIBILITY_NO
                }, FrameLayout.LayoutParams(-1, -1))
                hero.addView(LinearLayout(this).apply {
                    orientation = LinearLayout.VERTICAL
                    setPadding(dp(8), dp(14), dp(8), dp(8))
                    addView(OpenVelaBlue.text(this@OpenVelaPlanActivity, detail.title, 24, true))
                    if (detail.description.isNotBlank()) addView(OpenVelaBlue.text(this@OpenVelaPlanActivity, detail.description, 14))
                }, FrameLayout.LayoutParams(-1, -2))
                content.addView(hero, LinearLayout.LayoutParams(-1, -2).apply { height = dp(160) })
                if (detail.progress.isNotBlank()) card("护理进度", detail.progress)
                detail.steps.forEachIndexed { index, step ->
                    content.addView(OpenVelaBlue.step(this, index + 1, step.first, step.second))
                    content.addView(OpenVelaBlue.divider(this))
                }
                if (detail.steps.isEmpty()) label("接口未返回护理步骤")
                label("设备连接可用；正式开始护理需完成执行准入对接", 14)
                fetch("/api/v1/skin-reports/" + android.net.Uri.encode(reportId), mapOf("view" to "full"),
                    { loadPlan(person, reportId) }) { reportData ->
                    val report = OpenVelaData.report(reportData, person)
                    require(report.id == reportId)
                    content.addView(OpenVelaFacePhotos.create(this, report), 2)
                }
            }
        }
    }
    override fun onStart() {
        super.onStart()
        if (::status.isInitialized) {
            OpenVelaSession.selectPlan(plan)
            OpenVelaSession.observe(observer)
        }
    }
    override fun onStop() {
        OpenVelaSession.remove(observer)
        stopScan(); deviceDialog?.dismiss()
        super.onStop()
    }
    private fun render() {
        if (!::status.isInitialized || isDestroyed) return
        val s = OpenVelaSession
        status.text = when (s.state) {
            OpenVelaSession.State.DISCONNECTED -> "未连接"
            OpenVelaSession.State.CONNECTING -> "连接中"
            OpenVelaSession.State.INITIALIZING -> "准备中"
            OpenVelaSession.State.READY -> "已连接"
            OpenVelaSession.State.STARTING -> "正在启动"
            OpenVelaSession.State.RUNNING -> "护理中"
            OpenVelaSession.State.STOPPING -> "正在停止"
            OpenVelaSession.State.STOPPED -> "已停止"
            OpenVelaSession.State.COMPLETED -> "已完成"
            OpenVelaSession.State.QUERYING -> "正在查询…"
            OpenVelaSession.State.UNKNOWN -> s.message
        }
        val owns = s.planKey.isEmpty() || s.planKey == plan
        if (!owns) status.append("\n当前设备关联其他报告，请先在原方案结束本次会话。")
        connectButton.isEnabled = !s.busy && !s.connected && owns && (planReady || s.uncertainWork)
        connectButton.text = if (s.address.isBlank()) "连接设备" else "重新连接"
        connectButton.visibility = if (!s.connected) View.VISIBLE else View.GONE
        startButton.visibility = if (s.connected && !s.uncertainWork) View.VISIBLE else View.GONE
        stopButton.visibility = if (s.connected && s.uncertainWork) View.VISIBLE else View.GONE
        queryButton.visibility = if (s.connected && s.state in setOf(OpenVelaSession.State.UNKNOWN, OpenVelaSession.State.QUERYING)) View.VISIBLE else View.GONE
        startButton.isEnabled = false
        startButton.text = "开始工作（待执行准入对接）"
        stopButton.isEnabled = s.connected && s.uncertainWork && s.state != OpenVelaSession.State.STOPPING
        queryButton.isEnabled = s.connected && !s.busy
        if (deviceDialog != null && s.connected) { selectionInFlight = false; deviceDialog?.dismiss() }
        if (selectionInFlight && s.state != OpenVelaSession.State.CONNECTING && !s.connected) {
            selectionInFlight = false; deviceDialog?.setCancelable(true)
            scanHint?.text = s.message
            deviceDialog?.getButton(AlertDialog.BUTTON_NEGATIVE)?.isEnabled = true
            deviceDialog?.getButton(AlertDialog.BUTTON_NEUTRAL)?.isEnabled = true
        }
        if (s.state != OpenVelaSession.State.CONNECTING) selectionInFlight = false
        if (exitAfterStop && s.state in setOf(OpenVelaSession.State.STOPPED, OpenVelaSession.State.COMPLETED)) {
            exitAfterStop = false; finish()
        } else if (exitAfterStop && s.state == OpenVelaSession.State.UNKNOWN) {
            exitAfterStop = false; showUnconfirmedExit()
        }
    }
    private fun requestExit() {
        if (!OpenVelaSession.uncertainWork && !OpenVelaSession.busy) { finish(); return }
        if (exitDialog?.isShowing == true) return
        exitDialog = AlertDialog.Builder(this).setTitle("设备可能仍在工作")
            .setMessage("退出页面不会自动停止设备。建议先停止并确认设备状态。")
            .setNegativeButton("继续护理", null)
            .setPositiveButton("停止并退出") { _, _ ->
                if (!OpenVelaSession.connected) showUnconfirmedExit()
                else { exitAfterStop = true; OpenVelaSession.stop() }
            }.show()
    }
    private fun showUnconfirmedExit() {
        exitDialog?.dismiss()
        exitDialog = AlertDialog.Builder(this).setTitle("未确认设备停止")
            .setMessage("请检查设备。仍然退出后，设备可能继续工作。")
            .setNegativeButton("留在页面", null)
            .setNeutralButton("重试停止") { _, _ ->
                if (OpenVelaSession.connected) { exitAfterStop = true; OpenVelaSession.stop() }
                else requestScan()
            }
            .setPositiveButton("仍然退出") { _, _ -> finish() }.show()
    }
    private fun requestScan() {
        PrivacyManager.ensureAgreed(this) {
            val needed = mutableListOf(Manifest.permission.ACCESS_FINE_LOCATION)
            if (Build.VERSION.SDK_INT >= 31) needed.addAll(listOf(Manifest.permission.BLUETOOTH_SCAN, Manifest.permission.BLUETOOTH_CONNECT))
            val missing = needed.filter { ContextCompat.checkSelfPermission(this, it) != PackageManager.PERMISSION_GRANTED }
            if (missing.isEmpty()) searchDevices() else permission.launch(missing.toTypedArray())
        }
    }
    private fun searchDevices() {
        if (isFinishing || deviceDialog != null || OpenVelaSession.busy) return
        val adapter = (getSystemService(BLUETOOTH_SERVICE) as BluetoothManager).adapter
        if (adapter == null) { Toast.makeText(this, "此设备不支持蓝牙", Toast.LENGTH_SHORT).show(); return }
        if (!adapter.isEnabled) { enableBluetooth.launch(Intent(android.bluetooth.BluetoothAdapter.ACTION_REQUEST_ENABLE)); return }
        scanner = adapter.bluetoothLeScanner
        if (scanner == null) { Toast.makeText(this, "扫描不可用，请重试", Toast.LENGTH_SHORT).show(); return }
        val box = LinearLayout(this).apply { orientation = LinearLayout.VERTICAL; setPadding(dp(20), dp(12), dp(20), dp(12)) }
        val hint = TextView(this).apply { text = "搜索中"; setPadding(0, 0, 0, dp(16)) }
        box.addView(hint)
        scanHint = hint
        val devices = linkedMapOf<String, BluetoothDevice>()
        deviceDialog = AlertDialog.Builder(this).setTitle("附近的 openVela")
            .setView(box).setNegativeButton("关闭", null)
            .setNeutralButton("重新搜索", null).create().also { dialog ->
                dialog.setOnDismissListener { stopScan(); deviceDialog = null }
                dialog.show()
                val actionColors = android.content.res.ColorStateList(
                    arrayOf(intArrayOf(android.R.attr.state_enabled), intArrayOf()),
                    intArrayOf(OpenVelaBlue.blue, OpenVelaBlue.muted)
                )
                dialog.getButton(AlertDialog.BUTTON_NEUTRAL).setTextColor(actionColors)
                dialog.getButton(AlertDialog.BUTTON_NEGATIVE).setTextColor(actionColors)
                dialog.getButton(AlertDialog.BUTTON_NEUTRAL).setOnClickListener { dialog.dismiss(); searchDevices() }
            }
        scanning = true
        val scanToken = ++scanGeneration
        scanCallback = object : ScanCallback() {
            override fun onScanResult(callbackType: Int, result: ScanResult) {
                runOnUiThread {
                    if (scanToken != scanGeneration || !scanning || devices.size >= 5 || isFinishing || isDestroyed) return@runOnUiThread
                    val device = result.device
                    val name = result.scanRecord?.deviceName ?: device.name ?: return@runOnUiThread
                    if (!name.contains("openvela", true) || devices.containsKey(device.address)) return@runOnUiThread
                    if (OpenVelaSession.uncertainWork && OpenVelaSession.address.isNotBlank() &&
                        !device.address.equals(OpenVelaSession.address, true)) return@runOnUiThread
                    devices[device.address] = device
                    box.addView(Button(this@OpenVelaPlanActivity).apply {
                        text = "$name\n${device.address}"; isAllCaps = false
                        setOnClickListener {
                            if (selectionInFlight) return@setOnClickListener
                            stopScan(); selectionInFlight = true
                            hint.text = "正在连接…"
                            deviceDialog?.setCancelable(false)
                            deviceDialog?.getButton(AlertDialog.BUTTON_NEGATIVE)?.isEnabled = false
                            deviceDialog?.getButton(AlertDialog.BUTTON_NEUTRAL)?.isEnabled = false
                            OpenVelaSession.connect(device.address, plan)
                        }
                    })
                    hint.text = "已找到 ${devices.size} 台，点击连接"
                    if (devices.size == 5) { stopScan(); hint.text = "已找到 5 台，搜索结束" }
                }
            }
            override fun onScanFailed(errorCode: Int) {
                runOnUiThread { if (scanToken == scanGeneration) { stopScan(); hint.text = "搜索失败（$errorCode），请重新搜索" } }
            }
        }
        try {
            scanner?.startScan(null, ScanSettings.Builder().setScanMode(ScanSettings.SCAN_MODE_LOW_LATENCY).build(), scanCallback)
            handler.postDelayed({
                if (scanToken == scanGeneration && scanning) {
                    stopScan()
                    hint.text = if (devices.isEmpty()) "未找到设备，请确认设备已开启并重新搜索" else "搜索结束，共 ${devices.size} 台"
                }
            }, 30000)
        } catch (_: Exception) { stopScan(); hint.text = "无法搜索，请检查蓝牙和权限后重试" }
    }
    private fun stopScan() {
        scanGeneration++
        scanning = false; handler.removeCallbacksAndMessages(null)
        try { scanCallback?.let { scanner?.stopScan(it) } } catch (_: Exception) {}
        scanCallback = null
    }
    override fun onDestroy() {
        stopScan(); exitDialog?.dismiss(); deviceDialog?.dismiss()
        super.onDestroy()
    }
}
