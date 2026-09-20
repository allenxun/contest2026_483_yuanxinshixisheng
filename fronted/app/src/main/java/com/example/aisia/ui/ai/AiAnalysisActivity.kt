package com.example.aisia.ui.ai

import android.os.Bundle
import android.content.Intent
import android.view.LayoutInflater
import android.view.View
import android.widget.ImageView
import android.widget.LinearLayout
import android.widget.TextView
import androidx.appcompat.app.AppCompatActivity
import com.example.aisia.R
import com.example.aisia.ui.report.SkinReportActivity

/**
 * 智能分析页
 * 展示 6 项基础核心肌肤指标卡片，每项可独立折叠/展开
 * 默认收起，点击标题行切换展开状态，箭头随状态旋转
 */
class AiAnalysisActivity : AppCompatActivity() {

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContentView(R.layout.activity_ai_analysis)

        findViewById<View>(R.id.btnBack).setOnClickListener { finish() }
        findViewById<View>(R.id.btnViewReport).setOnClickListener {
            startActivity(Intent(this, SkinReportActivity::class.java))
        }

        val container = findViewById<LinearLayout>(R.id.layoutIndicators)
        val inflater = LayoutInflater.from(this)

        for (indicator in IndicatorData.ALL) {
            val card = inflater.inflate(R.layout.item_indicator, container, false)

            // 绑定数据
            card.findViewById<TextView>(R.id.tvTitle).text = indicator.title
            card.findViewById<TextView>(R.id.tvDefinition).text = indicator.definition

            // 填充分值区间
            val rangesLayout = card.findViewById<LinearLayout>(R.id.layoutRanges)
            for (range in indicator.ranges) {
                val rangeView = inflater.inflate(R.layout.item_range, rangesLayout, false)
                rangeView.findViewById<TextView>(R.id.tvRangeLabel).text = range.rangeLabel
                rangeView.findViewById<TextView>(R.id.tvStatus).text = "状态：${range.status}"
                rangeView.findViewById<TextView>(R.id.tvAiText).text = "智能 解读：${range.aiText}"
                rangesLayout.addView(rangeView)
            }

            // 折叠/展开逻辑
            val layoutHeader = card.findViewById<LinearLayout>(R.id.layoutHeader)
            val layoutContent = card.findViewById<LinearLayout>(R.id.layoutContent)
            val ivArrow = card.findViewById<ImageView>(R.id.ivArrow)

            layoutHeader.setOnClickListener {
                val isExpanded = layoutContent.visibility == View.VISIBLE
                if (isExpanded) {
                    // 收起：隐藏内容，箭头向右 (0°)
                    layoutContent.visibility = View.GONE
                    ivArrow.rotation = 0f
                } else {
                    // 展开：显示内容，箭头向下 (90°)
                    layoutContent.visibility = View.VISIBLE
                    ivArrow.rotation = 90f
                }
            }

            container.addView(card)
        }
    }
}
