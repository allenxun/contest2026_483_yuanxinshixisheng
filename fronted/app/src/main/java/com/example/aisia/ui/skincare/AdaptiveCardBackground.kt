package com.example.aisia.ui.skincare

import android.graphics.Canvas
import android.graphics.ColorFilter
import android.graphics.LinearGradient
import android.graphics.Paint
import android.graphics.PixelFormat
import android.graphics.RectF
import android.graphics.Shader
import android.graphics.drawable.Drawable

/**
 * 自适应卡片背景 Drawable
 * 装饰圆按百分比定位，在大屏设备上不会变形
 * 
 * @param startColor 渐变起始色
 * @param centerColor 渐变中间色
 * @param endColor 渐变结束色
 * @param cornerRadius 圆角半径（像素）
 */
class AdaptiveCardBackground(
    private val startColor: Int,
    private val centerColor: Int,
    private val endColor: Int,
    private val cornerRadius: Float = 32f
) : Drawable() {

    private val gradientPaint = Paint(Paint.ANTI_ALIAS_FLAG)
    private val circle1Paint = Paint(Paint.ANTI_ALIAS_FLAG).apply {
        color = 0x33FFFFFF
    }
    private val circle2Paint = Paint(Paint.ANTI_ALIAS_FLAG).apply {
        color = 0x22FFFFFF
    }

    override fun draw(canvas: Canvas) {
        val bounds = bounds
        val width = bounds.width().toFloat()
        val height = bounds.height().toFloat()

        // 绘制渐变背景
        val gradient = LinearGradient(
            0f, 0f, width, height,
            intArrayOf(startColor, centerColor, endColor),
            floatArrayOf(0f, 0.5f, 1f),
            Shader.TileMode.CLAMP
        )
        gradientPaint.shader = gradient

        val rect = RectF(bounds)
        canvas.drawRoundRect(rect, cornerRadius, cornerRadius, gradientPaint)

        // 装饰圆1：右上角（按百分比定位）
        // 圆心在右侧约 75% 处，上方溢出
        val circle1CenterX = width * 0.75f
        val circle1CenterY = height * -0.15f
        val circle1Radius = width * 0.25f
        canvas.drawCircle(circle1CenterX, circle1CenterY, circle1Radius, circle1Paint)

        // 装饰圆2：左下角（按百分比定位）
        // 圆心在左侧约 15% 处，下方溢出
        val circle2CenterX = width * 0.15f
        val circle2CenterY = height * 1.1f
        val circle2Radius = width * 0.2f
        canvas.drawCircle(circle2CenterX, circle2CenterY, circle2Radius, circle2Paint)
    }

    override fun setAlpha(alpha: Int) {
        gradientPaint.alpha = alpha
        circle1Paint.alpha = alpha
        circle2Paint.alpha = alpha
    }

    override fun setColorFilter(colorFilter: ColorFilter?) {
        gradientPaint.colorFilter = colorFilter
        circle1Paint.colorFilter = colorFilter
        circle2Paint.colorFilter = colorFilter
    }

    override fun getOpacity(): Int = PixelFormat.TRANSLUCENT
}