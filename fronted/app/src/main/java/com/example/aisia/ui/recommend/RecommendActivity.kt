package com.example.aisia.ui.recommend

import android.content.Intent
import android.graphics.Color
import android.graphics.drawable.GradientDrawable
import android.os.Bundle
import android.util.TypedValue
import android.view.Gravity
import android.widget.LinearLayout
import android.widget.TextView
import androidx.appcompat.app.AppCompatActivity
import com.example.aisia.R
import com.example.aisia.ui.skincare.ProjectDetailActivity

/**
 * 智能护肤推荐页
 * - 展示肤质标签
 * - 智能推荐导语
 * - 分类产品推荐
 * - 护肤避坑提醒
 */
class RecommendActivity : AppCompatActivity() {

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContentView(R.layout.activity_recommend)

        findViewById<android.view.View>(R.id.btnBack).setOnClickListener { finish() }
        findViewById<android.view.View>(R.id.btnViewProjectDetail).setOnClickListener {
            startActivity(Intent(this, ProjectDetailActivity::class.java))
        }

        // 动态添加皮肤标签
        val layoutTags = findViewById<LinearLayout>(R.id.layoutSkinTags)
        val tags = listOf("混合偏干", "外油内干", "初老预警", "毛孔待调理")

        tags.forEachIndexed { index, tag ->
            val tv = TextView(this).apply {
                text = tag
                setTextColor(Color.parseColor("#AF8D59"))
                setTextSize(TypedValue.COMPLEX_UNIT_SP, 14f)
                gravity = Gravity.CENTER

                // 白色背景 + 圆角
                val bg = GradientDrawable().apply {
                    setColor(Color.parseColor("#FFFFFF"))
                    cornerRadius = dp2px(4f).toFloat()
                    setStroke(dp2px(1f), Color.parseColor("#AF8D59"))
                }
                background = bg

                // padding
                val hPad = dp2px(12f)
                val vPad = dp2px(6f)
                setPadding(hPad, vPad, hPad, vPad)
            }

            val lp = LinearLayout.LayoutParams(
                LinearLayout.LayoutParams.WRAP_CONTENT,
                LinearLayout.LayoutParams.WRAP_CONTENT
            ).apply {
                if (index < tags.size - 1) {
                    marginEnd = dp2px(12f)
                }
            }

            layoutTags.addView(tv, lp)
        }
    }

    private fun dp2px(dp: Float): Int {
        return TypedValue.applyDimension(
            TypedValue.COMPLEX_UNIT_DIP, dp, resources.displayMetrics
        ).toInt()
    }
}
