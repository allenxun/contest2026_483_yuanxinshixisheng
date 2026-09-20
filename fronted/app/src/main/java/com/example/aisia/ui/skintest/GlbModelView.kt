package com.example.aisia.ui.skintest

import android.content.Context
import android.graphics.Color
import android.graphics.drawable.GradientDrawable
import android.util.AttributeSet
import android.util.TypedValue
import android.view.Gravity
import android.widget.FrameLayout
import android.widget.TextView
import java.io.File

/**
 * 3D 模型预览占位视图。
 *
 * 当前项目的 Filament 版本与旧版 API 不完全兼容，为了保证主流程可运行，
 * 将此组件简化为可展示加载状态和模型信息的占位容器，避免影响测肤流程。
 */
class GlbModelView @JvmOverloads constructor(
    context: Context,
    attrs: AttributeSet? = null,
    defStyle: Int = 0
) : FrameLayout(context, attrs, defStyle) {

    private val hintTextView: TextView = TextView(context).apply {
        setTextColor(Color.parseColor("#333333"))
        setTextSize(TypedValue.COMPLEX_UNIT_SP, 16f)
        gravity = Gravity.CENTER
        setPadding(24, 24, 24, 24)
        text = "3D 模型预览占位\n当前版本已切换为流程演示模式"
    }

    init {
        setBackgroundColor(Color.parseColor("#F5F7FA"))
        addView(hintTextView, LayoutParams(LayoutParams.MATCH_PARENT, LayoutParams.MATCH_PARENT))
    }

    fun loadGlb(file: File) {
        hintTextView.text = "已加载本地模型：${file.name}\n当前版本以流程演示模式运行"
    }

    fun loadGlbUrl(url: String) {
        hintTextView.text = "已接收到模型地址\n$url\n当前版本以流程演示模式运行"
    }

    fun resetCamera() {
        hintTextView.text = "视角已重置"
    }
}
