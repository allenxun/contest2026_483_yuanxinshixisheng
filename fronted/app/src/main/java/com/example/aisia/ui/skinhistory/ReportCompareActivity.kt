package com.example.aisia.ui.skinhistory

import android.annotation.SuppressLint
import android.graphics.Color
import android.graphics.Typeface
import android.os.Bundle
import android.util.Log
import android.view.Gravity
import android.view.View
import android.webkit.WebView
import android.webkit.WebViewClient
import android.widget.LinearLayout
import android.widget.TextView
import android.widget.Toast
import androidx.appcompat.app.AppCompatActivity
import com.example.aisia.R
import com.example.aisia.network.HttpHelper
import com.example.aisia.ui.report.ReportParser
import com.example.aisia.ui.report.ReportParser.DetectData
import com.example.aisia.ui.report.ReportParser.ReportDetail
import org.json.JSONObject
import java.text.SimpleDateFormat
import java.util.Date
import java.util.Locale
import java.util.concurrent.atomic.AtomicInteger

class ReportCompareActivity : AppCompatActivity() {

    companion object {
        private const val TAG = "ReportCompare"
        private const val COLOR_A = "#3a6df0"
        private const val COLOR_B = "#FF6B35"
        private const val COLOR_UP = "#4CAF50"
        private const val COLOR_DOWN = "#F44336"
        private const val COLOR_EQUAL = "#999999"
    }

    private var reportIdA = ""
    private var reportIdB = ""
    private var faceId = ""
    private var detailA: ReportDetail? = null
    private var detailB: ReportDetail? = null
    private lateinit var layoutContent: LinearLayout
    private lateinit var loadingMask: View
    private var webViewRadar: WebView? = null
    private var webViewElasticity: WebView? = null
    private var radarReady = false
    private var elasticityReady = false

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContentView(R.layout.activity_report_compare)
        reportIdA = intent.getStringExtra("reportIdA") ?: ""
        reportIdB = intent.getStringExtra("reportIdB") ?: ""
        faceId = intent.getStringExtra("faceId") ?: ""
        Log.d(TAG, "onCreate: A=$reportIdA B=$reportIdB face=$faceId")
        layoutContent = findViewById(R.id.layoutContent)
        loadingMask = findViewById(R.id.loadingMask)
        findViewById<View>(R.id.btnBack).setOnClickListener { finish() }
        buildUI()
        loadBothReports()
        // 兜底：15 秒后强制关闭蒙层，防止异常情况下蒙层卡死
        loadingMask.postDelayed({ loadingMask.visibility = View.GONE }, 15000)
    }

    // ────── UI 构建 ──────

    @SuppressLint("SetJavaScriptEnabled")
    private fun buildUI() {
        val a = detailA; val b = detailB // will be null at build time, populated later

        // 1. 时间标签行
        val timeRow = row()
        timeRow.addView(tv(Gravity.CENTER, 12f, "#8a8c95").apply { tag = "tvTimeA" }, halfLp())
        timeRow.addView(tv(Gravity.CENTER, 12f, "#8a8c95").apply { tag = "tvTimeB" }, halfLp())
        layoutContent.addView(timeRow, secLp(8))

        // 2. 总体得分卡片
        val scoreCard = card()
        scoreCard.addView(secTitle("总体得分"))
        val scoreRow = row().apply { gravity = Gravity.CENTER_VERTICAL }
        val scoreLeftCol = vCol().apply {
            addView(tv(Gravity.CENTER, 36f, COLOR_A, bold = true).apply { tag = "tvScoreA" })
            addView(tv(Gravity.CENTER, 12f, "#8a8c95").apply { text = "报告A" })
        }
        val diffCol = vCol().apply { setPadding(dp(12), 0, dp(12), 0) }
        diffCol.addView(tv(Gravity.CENTER, 18f, "#999999", bold = true).apply { tag = "tvScoreDiff" })
        diffCol.addView(tv(Gravity.CENTER, 11f, "#8a8c95").apply { text = "变化" })
        val scoreRightCol = vCol().apply {
            addView(tv(Gravity.CENTER, 36f, COLOR_B, bold = true).apply { tag = "tvScoreB" })
            addView(tv(Gravity.CENTER, 12f, "#8a8c95").apply { text = "报告B" })
        }
        scoreRow.addView(scoreLeftCol, halfLp())
        scoreRow.addView(diffCol, wrapLp())
        scoreRow.addView(scoreRightCol, halfLp())
        scoreCard.addView(scoreRow)
        layoutContent.addView(scoreCard, secLp(12))

        // 3. 基础指标卡片
        val metricsCard = card()
        metricsCard.addView(secTitle("基础指标"))
        metricsCard.addView(vCol().apply { tag = "metricsContainer" })
        layoutContent.addView(metricsCard, secLp(12))

        // 4. 雷达图卡片
        val radarCard = card()
        radarCard.addView(secTitle("肤质雷达图"))
        val radarLeg = row()
        radarLeg.addView(legendDot(COLOR_A, "报告A"))
        radarLeg.addView(View(this).apply { layoutParams = LinearLayout.LayoutParams(0, 0, 1f) })
        radarLeg.addView(legendDot(COLOR_B, "报告B"))
        radarCard.addView(radarLeg)
        webViewRadar = WebView(this).apply {
            settings.javaScriptEnabled = true
            setBackgroundColor(Color.TRANSPARENT)
            webViewClient = object : WebViewClient() {
                override fun onPageFinished(view: WebView?, url: String?) {
                    radarReady = true; pushRadarData()
                }
            }
        }
        radarCard.addView(webViewRadar, LinearLayout.LayoutParams(LinearLayout.LayoutParams.MATCH_PARENT, dp(210)))
        layoutContent.addView(radarCard, secLp(12))

        // 5. 弹性曲线卡片
        val elCard = card()
        elCard.addView(secTitle("弹性曲线"))
        val elLeg = row()
        elLeg.addView(legendDot(COLOR_A, "报告A (实线)"))
        elLeg.addView(View(this).apply { layoutParams = LinearLayout.LayoutParams(0, 0, 1f) })
        elLeg.addView(legendDot(COLOR_B, "报告B (虚线)"))
        elCard.addView(elLeg)
        webViewElasticity = WebView(this).apply {
            settings.javaScriptEnabled = true
            setBackgroundColor(Color.TRANSPARENT)
            webViewClient = object : WebViewClient() {
                override fun onPageFinished(view: WebView?, url: String?) {
                    elasticityReady = true; pushElasticityData()
                }
            }
        }
        elCard.addView(webViewElasticity, LinearLayout.LayoutParams(LinearLayout.LayoutParams.MATCH_PARENT, dp(210)))
        layoutContent.addView(elCard, secLp(12))

        // 6. 检测项对比卡片
        val detectCard = card()
        detectCard.addView(secTitle("检测项目对比"))
        detectCard.addView(vCol().apply { tag = "detectContainer" })
        layoutContent.addView(detectCard, secLp(12))

        // 7. 底部返回按钮（点击返回上一页）
        val btnBackBottom = TextView(this).apply {
            text = "返回"
            textSize = 16f
            typeface = Typeface.DEFAULT_BOLD
            gravity = Gravity.CENTER
            setTextColor(Color.WHITE)
            background = androidx.core.content.ContextCompat.getDrawable(context, R.drawable.btn_compare_primary_bg)
            setOnClickListener { finish() }
        }
        layoutContent.addView(btnBackBottom, LinearLayout.LayoutParams(LinearLayout.LayoutParams.MATCH_PARENT, dp(48)))

        // 加载 WebView
        webViewRadar?.loadUrl("file:///android_asset/compare_radar_chart.html")
        webViewElasticity?.loadUrl("file:///android_asset/compare_elasticity_chart.html")
    }

    // ────── 数据加载 ──────

    private fun loadBothReports() {
        // 两个请求的回调在不同 OkHttp 线程，用原子计数避免可见性问题导致 populateData 不执行
        val remaining = AtomicInteger(2)
        fun checkDone() {
            if (remaining.decrementAndGet() == 0) runOnUiThread { populateData() }
        }
        HttpHelper.get(
            path = "/api/self-research-face/faces/$faceId/reports/$reportIdA",
            onSuccess = { resp ->
                try {
                    val json = JSONObject(resp)
                    val data = json.optJSONObject("data") ?: json
                    detailA = ReportParser.parseReportJson(data)
                } catch (e: Exception) { Log.e(TAG, "parse A failed", e) }
                checkDone()
            },
            onFailure = { code, msg ->
                Log.e(TAG, "load A failed: $code $msg"); checkDone()
            }
        )
        HttpHelper.get(
            path = "/api/self-research-face/faces/$faceId/reports/$reportIdB",
            onSuccess = { resp ->
                try {
                    val json = JSONObject(resp)
                    val data = json.optJSONObject("data") ?: json
                    detailB = ReportParser.parseReportJson(data)
                } catch (e: Exception) { Log.e(TAG, "parse B failed", e) }
                checkDone()
            },
            onFailure = { code, msg ->
                Log.e(TAG, "load B failed: $code $msg"); checkDone()
            }
        )
    }

    // ────── 填充数据 ──────

    private fun populateData() {
        // 两份报告都已返回（无论成功失败），关闭全屏加载蒙层
        loadingMask.visibility = View.GONE
        val a = detailA
        val b = detailB
        if (a == null && b == null) {
            Toast.makeText(this, "报告数据加载失败", Toast.LENGTH_SHORT).show()
            return
        }

        // 时间（接口返回秒级时间戳，转为格式化时间）
        findTag<TextView>("tvTimeA")?.text = formatTime(a?.createdAt)
        findTag<TextView>("tvTimeB")?.text = formatTime(b?.createdAt)

        // 总分
        findTag<TextView>("tvScoreA")?.text = "${a?.overallScore ?: 0}"
        findTag<TextView>("tvScoreB")?.text = "${b?.overallScore ?: 0}"
        val sa = a?.overallScore ?: 0
        val sb = b?.overallScore ?: 0
        val diff = sb - sa
        val tvDiff = findTag<TextView>("tvScoreDiff")
        if (diff > 0) {
            tvDiff?.text = "↑ $diff"
            tvDiff?.setTextColor(Color.parseColor(COLOR_UP))
        } else if (diff < 0) {
            tvDiff?.text = "↓ ${-diff}"
            tvDiff?.setTextColor(Color.parseColor(COLOR_DOWN))
        } else {
            tvDiff?.text = "→ 持平"
            tvDiff?.setTextColor(Color.parseColor(COLOR_EQUAL))
        }

        // 基础指标
        val metricsContainer = findTag<LinearLayout>("metricsContainer")
        if (metricsContainer != null && a != null && b != null) {
            val metrics = listOf(
                "肤质" to (a.skinType.ifEmpty { "未知" } to b.skinType.ifEmpty { "未知" }),
                "水油" to (metricVal(a, "水油", a.moistureLevel) to metricVal(b, "水油", b.moistureLevel)),
                "毛孔" to (metricVal(a, "毛孔", a.referenceScore) to metricVal(b, "毛孔", b.referenceScore)),
                "弹性" to ("${a.elasticityScore}" to "${b.elasticityScore}"),
                "屏障" to (radarVal(a, "屏障") to radarVal(b, "屏障")),
                "色素" to (radarVal(a, "色素") to radarVal(b, "色素"))
            )
            for ((label, pair) in metrics) {
                metricsContainer.addView(buildMetricRow(label, pair.first, pair.second))
            }
        }

        // 雷达图 & 弹性图
        pushRadarData()
        pushElasticityData()

        // 检测项对比
        val detectContainer = findTag<LinearLayout>("detectContainer")
        if (detectContainer != null && a != null && b != null) {
            val detects = listOf(
                a.redness to b.redness,
                a.spots to b.spots,
                a.brown to b.brown,
                a.purple to b.purple,
                a.pores to b.pores,
                a.texture to b.texture,
                a.wrinkle to b.wrinkle
            )
            for ((detA, detB) in detects) {
                detectContainer.addView(buildDetectSection(detA, detB))
            }
        }

    }

    private fun radarVal(detail: ReportDetail, name: String): String {
        // 精确匹配优先，其次模糊匹配（接口雷达项名为"水油平衡/毛孔状态/屏障健康/色素沉着"等）
        val item = detail.radarItems.find { it.name == name }
            ?: detail.radarItems.find { it.name.contains(name) || (it.name.isNotEmpty() && name.contains(it.name)) }
        return item?.value?.toString() ?: "--"
    }

    /** 基础指标取值：优先雷达图对应项，没有则用兜底值（>0 才显示） */
    private fun metricVal(detail: ReportDetail, radarName: String, fallback: Int): String {
        val v = radarVal(detail, radarName)
        if (v != "--") return v
        return if (fallback > 0) fallback.toString() else "--"
    }

    /** created_at 秒/毫秒时间戳转 yyyy/MM/dd HH:mm:ss；非纯数字（已是格式化字符串）原样返回 */
    private fun formatTime(raw: String?): String {
        if (raw.isNullOrBlank()) return "暂无"
        val ts = raw.toLongOrNull() ?: return raw
        val millis = if (ts < 100_000_000_000L) ts * 1000 else ts
        return try {
            SimpleDateFormat("yyyy/MM/dd HH:mm:ss", Locale.getDefault()).format(Date(millis))
        } catch (e: Exception) {
            raw
        }
    }

    private fun pushRadarData() {
        val a = detailA ?: return
        val b = detailB ?: return
        if (!radarReady) return
        val names = a.radarItems.map { it.name }.ifEmpty { listOf("水分", "油分", "弹性", "毛孔", "肤色") }
        val indicators = names.joinToString(",") { "{name:'$it',max:100}" }
        val dataA = names.map { n -> a.radarItems.find { it.name == n }?.value ?: 0 }
        val dataB = names.map { n -> b.radarItems.find { it.name == n }?.value ?: 0 }
        val js = "setCompareRadarData([$indicators], [${dataA.joinToString(",")}], [${dataB.joinToString(",")}])"
        webViewRadar?.evaluateJavascript(js, null)
    }

    private fun pushElasticityData() {
        val a = detailA ?: return
        val b = detailB ?: return
        if (!elasticityReady) return
        val js = "setCompareLineData({xDataA:[${a.elasticityX.joinToString(",")}],yDataA:[${a.elasticityY.joinToString(",")}],xDataB:[${b.elasticityX.joinToString(",")}],yDataB:[${b.elasticityY.joinToString(",")}]})"
        webViewElasticity?.evaluateJavascript(js, null)
    }

    // ────── UI 辅助方法 ──────

    private inline fun <reified V : View> findTag(tag: String): V? {
        return findViewByTag(layoutContent, tag) as? V
    }

    private fun findViewByTag(parent: View, tag: String): View? {
        if (parent.tag == tag) return parent
        if (parent is LinearLayout) {
            for (i in 0 until parent.childCount) {
                val found = findViewByTag(parent.getChildAt(i), tag)
                if (found != null) return found
            }
        }
        return null
    }

    private fun dp(v: Int): Int = (v * resources.displayMetrics.density).toInt()

    private fun row(): LinearLayout = LinearLayout(this).apply {
        orientation = LinearLayout.HORIZONTAL
    }

    private fun vCol(): LinearLayout = LinearLayout(this).apply {
        orientation = LinearLayout.VERTICAL
        gravity = Gravity.CENTER
    }

    private fun tv(gravity: Int = Gravity.START, size: Float = 14f, color: String = "#333333", bold: Boolean = false): TextView =
        TextView(this).apply {
            this.gravity = gravity
            textSize = size
            setTextColor(Color.parseColor(color))
            if (bold) typeface = Typeface.DEFAULT_BOLD
        }

    private fun card(): LinearLayout = LinearLayout(this).apply {
        orientation = LinearLayout.VERTICAL
        setPadding(dp(16), dp(16), dp(16), dp(16))
        background = androidx.core.content.ContextCompat.getDrawable(context, R.drawable.metric_card_bg)
    }

    private fun secTitle(text: String): LinearLayout {
        val container = LinearLayout(this).apply {
            orientation = LinearLayout.HORIZONTAL
            gravity = Gravity.CENTER_VERTICAL
        }
        container.addView(View(this@ReportCompareActivity).apply {
            layoutParams = LinearLayout.LayoutParams(dp(4), dp(16))
            setBackgroundColor(Color.parseColor("#3a6df0"))
        })
        container.addView(TextView(this@ReportCompareActivity).apply {
            this.text = text
            textSize = 16f
            setTextColor(Color.parseColor("#111111"))
            typeface = Typeface.DEFAULT_BOLD
        }, LinearLayout.LayoutParams(LinearLayout.LayoutParams.WRAP_CONTENT, LinearLayout.LayoutParams.WRAP_CONTENT).apply { marginStart = dp(8) })
        container.setPadding(0, 0, 0, dp(12))
        return container
    }

    private fun secLp(bottomMargin: Int): LinearLayout.LayoutParams =
        LinearLayout.LayoutParams(LinearLayout.LayoutParams.MATCH_PARENT, LinearLayout.LayoutParams.WRAP_CONTENT).apply {
            this.bottomMargin = dp(bottomMargin)
        }

    private fun halfLp(): LinearLayout.LayoutParams =
        LinearLayout.LayoutParams(0, LinearLayout.LayoutParams.WRAP_CONTENT, 1f).apply {
            marginStart = dp(4); marginEnd = dp(4)
        }

    private fun wrapLp(): LinearLayout.LayoutParams =
        LinearLayout.LayoutParams(LinearLayout.LayoutParams.WRAP_CONTENT, LinearLayout.LayoutParams.WRAP_CONTENT)

    private fun legendDot(color: String, label: String): LinearLayout {
        val container = LinearLayout(this).apply {
            orientation = LinearLayout.HORIZONTAL
            gravity = Gravity.CENTER_VERTICAL
        }
        container.addView(View(this).apply {
            layoutParams = LinearLayout.LayoutParams(dp(8), dp(8)).apply { marginEnd = dp(4) }
            setBackgroundColor(Color.parseColor(color))
        })
        container.addView(TextView(this).apply {
            text = label; textSize = 11f; setTextColor(Color.parseColor("#666666"))
        })
        return container
    }

    private fun buildMetricRow(label: String, valA: String, valB: String): LinearLayout {
        val container = row().apply {
            gravity = Gravity.CENTER_VERTICAL
            setPadding(0, dp(8), 0, dp(8))
        }
        container.addView(TextView(this).apply {
            text = label; textSize = 13f; setTextColor(Color.parseColor("#333333")); typeface = Typeface.DEFAULT_BOLD
        }, LinearLayout.LayoutParams(dp(48), LinearLayout.LayoutParams.WRAP_CONTENT))
        container.addView(TextView(this).apply {
            text = valA; textSize = 13f; setTextColor(Color.parseColor(COLOR_A)); gravity = Gravity.CENTER
        }, halfLp())
        val numA = valA.toIntOrNull(); val numB = valB.toIntOrNull()
        val diffText: String; val diffColor: String
        if (numA != null && numB != null) {
            val d = numB - numA
            diffText = when { d > 0 -> "↑$d"; d < 0 -> "↓${-d}"; else -> "→" }
            diffColor = when { d > 0 -> COLOR_UP; d < 0 -> COLOR_DOWN; else -> COLOR_EQUAL }
        } else { diffText = ""; diffColor = COLOR_EQUAL }
        container.addView(TextView(this).apply {
            text = diffText; textSize = 12f; setTextColor(Color.parseColor(diffColor)); gravity = Gravity.CENTER
        }, LinearLayout.LayoutParams(dp(36), LinearLayout.LayoutParams.WRAP_CONTENT))
        container.addView(TextView(this).apply {
            text = valB; textSize = 13f; setTextColor(Color.parseColor(COLOR_B)); gravity = Gravity.CENTER
        }, halfLp())
        return container
    }

    private fun buildDetectSection(detA: DetectData, detB: DetectData): LinearLayout {
        val section = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL; setPadding(0, dp(8), 0, dp(4))
        }
        val titleRow = row().apply { gravity = Gravity.CENTER_VERTICAL; setPadding(0, dp(4), 0, dp(4)) }
        titleRow.addView(TextView(this).apply {
            text = detA.name; textSize = 14f; setTextColor(Color.parseColor("#333333")); typeface = Typeface.DEFAULT_BOLD
        })
        titleRow.addView(View(this).apply { layoutParams = LinearLayout.LayoutParams(0, 0, 1f) })
        val statusText = when {
            detA.hasData && detB.hasData -> "均有数据"
            detA.hasData -> "仅A有数据"; detB.hasData -> "仅B有数据"
            else -> "均无数据"
        }
        titleRow.addView(TextView(this).apply {
            text = statusText; textSize = 11f; setTextColor(Color.parseColor("#8a8c95"))
        })
        section.addView(titleRow)
        if (detA.description.isNotBlank() || detB.description.isNotBlank()) {
            val descRow = row()
            descRow.addView(tv(size = 12f, color = "#666666").apply { text = detA.description.ifEmpty { "-" } }, halfLp())
            descRow.addView(tv(size = 12f, color = "#666666").apply { text = detB.description.ifEmpty { "-" } }, halfLp())
            section.addView(descRow)
        }
        // 只要一方有数据就列出对比表格，没有的一方用 "-" 占位
        if ((detA.hasData || detB.hasData) && (detA.table.isNotEmpty() || detB.table.isNotEmpty())) {
            // 表头行：分区 | 报告A | 报告B | 变化
            val headRow = row().apply { setPadding(dp(8), dp(6), 0, dp(4)) }
            headRow.addView(TextView(this).apply {
                text = "分区"; textSize = 11f; setTextColor(Color.parseColor("#999999"))
            }, LinearLayout.LayoutParams(dp(36), LinearLayout.LayoutParams.WRAP_CONTENT))
            headRow.addView(TextView(this).apply {
                text = "报告A"; textSize = 11f; setTextColor(Color.parseColor("#999999")); gravity = Gravity.CENTER
            }, halfLp())
            headRow.addView(TextView(this).apply {
                text = "报告B"; textSize = 11f; setTextColor(Color.parseColor("#999999")); gravity = Gravity.CENTER
            }, halfLp())
            headRow.addView(TextView(this).apply {
                text = "变化"; textSize = 11f; setTextColor(Color.parseColor("#999999")); gravity = Gravity.CENTER
            }, LinearLayout.LayoutParams(dp(36), LinearLayout.LayoutParams.WRAP_CONTENT))
            section.addView(headRow)
            // 表头底部分割线
            section.addView(View(this).apply {
                layoutParams = LinearLayout.LayoutParams(LinearLayout.LayoutParams.MATCH_PARENT, 1)
                setBackgroundColor(Color.parseColor("#EEEEEE"))
            })
            val zonesA = detA.table.associateBy { it.zone }
            val zonesB = detB.table.associateBy { it.zone }
            for (zone in (zonesA.keys + zonesB.keys)) {
                val valA = zonesA[zone]?.score?.ifEmpty { "-" } ?: "-"
                val valB = zonesB[zone]?.score?.ifEmpty { "-" } ?: "-"
                // 解析数值用于比较箭头方向
                val numA = parseScoreNum(valA)
                val numB = parseScoreNum(valB)
                val arrowText: String
                val arrowColor: String
                if (numA != null && numB != null) {
                    val diff = numB - numA
                    when {
                        diff > 0 -> { arrowText = "↑"; arrowColor = COLOR_UP }
                        diff < 0 -> { arrowText = "↓"; arrowColor = COLOR_DOWN }
                        else -> { arrowText = "-"; arrowColor = COLOR_EQUAL }
                    }
                } else {
                    arrowText = "-"; arrowColor = COLOR_EQUAL
                }
                val zRow = row().apply { setPadding(dp(8), dp(2), 0, dp(2)) }
                zRow.addView(TextView(this).apply {
                    text = zone; textSize = 11f; setTextColor(Color.parseColor("#8a8c95"))
                }, LinearLayout.LayoutParams(dp(36), LinearLayout.LayoutParams.WRAP_CONTENT))
                zRow.addView(TextView(this).apply {
                    text = valA; textSize = 12f; setTextColor(Color.parseColor(COLOR_A)); gravity = Gravity.CENTER
                }, halfLp())
                zRow.addView(TextView(this).apply {
                    text = valB; textSize = 12f; setTextColor(Color.parseColor(COLOR_B)); gravity = Gravity.CENTER
                }, halfLp())
                // 箭头列
                zRow.addView(TextView(this).apply {
                    text = arrowText; textSize = 14f; setTextColor(Color.parseColor(arrowColor)); gravity = Gravity.CENTER
                }, LinearLayout.LayoutParams(dp(36), LinearLayout.LayoutParams.WRAP_CONTENT))
                section.addView(zRow)
            }
        }
        section.addView(View(this).apply {
            layoutParams = LinearLayout.LayoutParams(LinearLayout.LayoutParams.MATCH_PARENT, 1).apply { topMargin = dp(8) }
            setBackgroundColor(Color.parseColor("#F0F0F0"))
        })
        return section
    }

    /** 从分数文本中提取数值（支持百分比如 "12%" 和普通数字），无法解析返回 null */
    private fun parseScoreNum(text: String): Double? {
        if (text.isBlank() || text == "-") return null
        val cleaned = text.replace("%", "").trim()
        return cleaned.toDoubleOrNull()
    }

    override fun onDestroy() {
        super.onDestroy()
        webViewRadar?.destroy()
        webViewElasticity?.destroy()
    }
}