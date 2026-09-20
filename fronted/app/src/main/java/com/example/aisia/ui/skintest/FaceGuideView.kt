package com.example.aisia.ui.skintest

import android.content.Context
import android.graphics.*
import android.util.AttributeSet
import android.util.Log
import android.view.View

/**
 * 人脸引导椭圆，屏幕坐标系
 */
data class FaceOval(
    val cx: Float,
    val cy: Float,
    val rx: Float,
    val ry: Float
) {
    fun contains(x: Float, y: Float): Boolean {
        if (rx <= 0f || ry <= 0f) return false
        val dx = (x - cx) / rx
        val dy = (y - cy) / ry
        return dx * dx + dy * dy <= 1f
    }
}

/**
 * 人脸导向曲线 View
 * 使用二次贝塞尔曲线绘制人脸轮廓，带三层霓虹发光效果
 */
class FaceGuideView @JvmOverloads constructor(
    context: Context,
    attrs: AttributeSet? = null,
    defStyleAttr: Int = 0
) : View(context, attrs, defStyleAttr) {

    // 描边颜色 #98edfc
    private val strokeColor = Color.parseColor("#98EDFC")
    
    // 画笔配置
    private val mainPathPaint = Paint().apply {
        color = strokeColor
        style = Paint.Style.STROKE
        strokeWidth = 2.5f * resources.displayMetrics.density
        strokeCap = Paint.Cap.ROUND
        strokeJoin = Paint.Join.ROUND
        isAntiAlias = true
    }
    
    private val chinLinePaint = Paint().apply {
        color = strokeColor
        style = Paint.Style.STROKE
        strokeWidth = 2f * resources.displayMetrics.density
        strokeCap = Paint.Cap.ROUND
        isAntiAlias = true
    }
    
    private val dotPaint = Paint().apply {
        color = strokeColor
        style = Paint.Style.FILL
        isAntiAlias = true
    }
    
    // 三层发光画笔
    private val glowNearPaint = Paint().apply {
        color = strokeColor
        style = Paint.Style.STROKE
        strokeWidth = 2.5f * resources.displayMetrics.density
        strokeCap = Paint.Cap.ROUND
        strokeJoin = Paint.Join.ROUND
        isAntiAlias = true
        maskFilter = BlurMaskFilter(6f * resources.displayMetrics.density, BlurMaskFilter.Blur.NORMAL)
        alpha = (255 * 0.6f).toInt()
    }
    
    private val glowMidPaint = Paint().apply {
        color = strokeColor
        style = Paint.Style.STROKE
        strokeWidth = 2.5f * resources.displayMetrics.density
        strokeCap = Paint.Cap.ROUND
        strokeJoin = Paint.Join.ROUND
        isAntiAlias = true
        maskFilter = BlurMaskFilter(24f * resources.displayMetrics.density, BlurMaskFilter.Blur.NORMAL)
        alpha = (255 * 0.35f).toInt()
    }
    
    private val glowFarPaint = Paint().apply {
        color = strokeColor
        style = Paint.Style.STROKE
        strokeWidth = 2.5f * resources.displayMetrics.density
        strokeCap = Paint.Cap.ROUND
        strokeJoin = Paint.Join.ROUND
        isAntiAlias = true
        maskFilter = BlurMaskFilter(48f * resources.displayMetrics.density, BlurMaskFilter.Blur.NORMAL)
        alpha = (255 * 0.18f).toInt()
    }
    
    // 设计稿坐标（200x320 的 viewport，适度增加高度）
    private val designWidth = 200f
    private val designHeight = 320f
    
    // 主轮廓路径点（上下拉长版本，不超出框）
    private val mainContourPoints = floatArrayOf(
        // 起点：右下颚
        143f, 275f,
        // 右脸颊 -> 颧骨
        202f, 200f,
        // 右太阳穴
        198f, 120f,
        // 右额角
        148f, 75f,
        // 前额顶部（适度上移）
        100f, 40f,
        // 左额角
        52f, 75f,
        // 左太阳穴
        2f, 120f,
        // 左颧骨
        35f, 245f,
        // 终点：左下颚
        57f, 275f
    )
    
    // 下巴装饰线 - 左下颚弧线
    private val chinLeftArc = floatArrayOf(36f, 268f, 60f, 289f)
    // 下巴装饰线 - 下巴底部弧线
    private val chinBottomArc = floatArrayOf(80f, 297f, 100f, 306f, 120f, 297f)
    // 下巴装饰线 - 右下颚弧线
    private val chinRightArc = floatArrayOf(140f, 289f, 164f, 268f)
    
    // 端点圆点
    private val leftDot = floatArrayOf(57f, 275f)
    private val rightDot = floatArrayOf(143f, 275f)
    private val dotRadius = 1.5f

    // 人脸引导椭圆参数（设计稿坐标系）
    private val ovalCenterX = 100f
    private val ovalCenterY = 165f
    private val ovalRadiusX = 90f
    private val ovalRadiusY = 130f

    // 变换矩阵
    private val matrix = Matrix()
    private var scaleX = 1f
    private var scaleY = 1f
    private var offsetX = 0f
    private var offsetY = 0f

    // ────── 动态人脸跟踪 ──────
    /** 是否正在跟踪人脸（检测到人脸时为 true） */
    private var isTrackingFace = false
    /** 人脸中心在 View 坐标系中的位置（像素） */
    private var faceCenterViewX = 0f
    private var faceCenterViewY = 0f
    /** 人脸在 View 坐标系中的大小（像素） */
    private var faceViewWidth = 0f
    private var faceViewHeight = 0f
    /** 平滑插值因子（0~1，越大跟随越快） */
    private val smoothFactor = 0.7f
    /** 平滑后的人脸中心/大小（用于动画过渡） */
    private var smoothFaceCx = 0f
    private var smoothFaceCy = 0f
    private var smoothFaceW = 0f
    private var smoothFaceH = 0f
    /** 基础缩放值（onSizeChanged 时计算的静态值） */
    private var baseScale = 1f
    private var baseOffsetX = 0f
    private var baseOffsetY = 0f

    init {
        // 需要禁用硬件加速以支持 BlurMaskFilter
        setLayerType(LAYER_TYPE_SOFTWARE, null)
    }

    override fun onSizeChanged(w: Int, h: Int, oldw: Int, oldh: Int) {
        super.onSizeChanged(w, h, oldw, oldh)
        updateTransform(w, h)
    }

    private fun updateTransform(w: Int, h: Int) {
        // 保持宽高比居中缩放
        val rawScaleX = w / designWidth
        val rawScaleY = h / designHeight
        val scale = minOf(rawScaleX, rawScaleY) * 0.82f  // 缩小 18% 防止线条超出框

        val scaledWidth = designWidth * scale
        val scaledHeight = designHeight * scale
        baseOffsetX = (w - scaledWidth) / 2f
        baseOffsetY = (h - scaledHeight) / 2f - (75 * resources.displayMetrics.density)  // 上移 75dp
        baseScale = scale

        // 如果未跟踪人脸，使用静态值
        if (!isTrackingFace) {
            scaleX = scale
            scaleY = scale
            offsetX = baseOffsetX
            offsetY = baseOffsetY
        }

        matrix.reset()
        matrix.postScale(scaleX, scaleY)
        matrix.postTranslate(offsetX, offsetY)
    }

    /**
     * 更新检测到的人脸位置，引导框跟随人脸移动/缩放
     * 使用 FaceGuideView 像素坐标（已考虑 centerCrop 变换）
     * @param centerPxX 人脸中心 X（FaceGuideView 像素坐标）
     * @param centerPxY 人脸中心 Y（FaceGuideView 像素坐标）
     * @param faceWPx 人脸宽度（FaceGuideView 像素坐标）
     * @param faceHPx 人脸高度（FaceGuideView 像素坐标）
     */
    fun updateFacePositionPx(centerPxX: Float, centerPxY: Float, faceWPx: Float, faceHPx: Float) {
        Log.d("FaceGuideView", "updateFacePositionPx: center=($centerPxX, $centerPxY), " +
                "size=(${faceWPx}x${faceHPx}), viewSize=(${width}x${height}), " +
                "baseScale=$baseScale, baseOffset=($baseOffsetX, $baseOffsetY)")
        if (faceWPx <= 0f || faceHPx <= 0f) {
            // 无人脸，恢复默认位置
            isTrackingFace = false
            scaleX = baseScale
            scaleY = baseScale
            offsetX = baseOffsetX
            offsetY = baseOffsetY
            invalidate()
            return
        }

        isTrackingFace = true

        // ML Kit boundingBox 主要覆盖面部区域（眉毛到下巴），不包含额头
        // FaceGuideView 的轮廓是完整人脸（含额头），需要向上偏移让框包住额头
        // 同时将高度放大，让框能完整覆盖额头到下巴
        val targetCx = centerPxX
        val targetCy = centerPxY - faceHPx * 0.25f  // 向上偏移 25% 人脸高度
        val targetW = faceWPx
        val targetH = faceHPx * 1.3f  // 高度放大 30%，覆盖额头

        if (smoothFaceW == 0f) {
            // 首次检测，直接赋值
            smoothFaceCx = targetCx
            smoothFaceCy = targetCy
            smoothFaceW = targetW
            smoothFaceH = targetH
        } else {
            // 平滑过渡
            smoothFaceCx += (targetCx - smoothFaceCx) * smoothFactor
            smoothFaceCy += (targetCy - smoothFaceCy) * smoothFactor
            smoothFaceW += (targetW - smoothFaceW) * smoothFactor
            smoothFaceH += (targetH - smoothFaceH) * smoothFactor
        }

        // 以人脸中心为锚点，根据人脸大小动态计算缩放
        // 设计稿中椭圆大小占设计稿的比例
        val designOvalW = ovalRadiusX * 2f   // 180
        val designOvalH = ovalRadiusY * 2f   // 260
        // 目标：让引导框略大于检测到的人脸
        val targetScaleX = smoothFaceW * 1.3f / designOvalW
        val targetScaleY = smoothFaceH * 1.3f / designOvalH
        val targetScale = minOf(targetScaleX, targetScaleY)

        // 限制缩放范围，避免过小或过大
        val clampedScale = targetScale.coerceIn(baseScale * 0.4f, baseScale * 1.6f)

        scaleX = clampedScale
        scaleY = clampedScale

        // 以人脸中心为锚点计算偏移
        // 设计稿中椭圆中心在 (100, 165)，对应设计稿坐标
        offsetX = smoothFaceCx - ovalCenterX * clampedScale
        offsetY = smoothFaceCy - ovalCenterY * clampedScale

        invalidate()
    }

    /**
     * 重置引导框到默认居中位置
     */
    fun resetToDefault() {
        isTrackingFace = false
        smoothFaceCx = 0f
        smoothFaceCy = 0f
        smoothFaceW = 0f
        smoothFaceH = 0f
        scaleX = baseScale
        scaleY = baseScale
        offsetX = baseOffsetX
        offsetY = baseOffsetY
        invalidate()
    }
    
    private fun transformX(x: Float): Float = x * scaleX + offsetX
    private fun transformY(y: Float): Float = y * scaleY + offsetY
    private fun transformSize(size: Float): Float = size * minOf(scaleX, scaleY)
    
    override fun onDraw(canvas: Canvas) {
        super.onDraw(canvas)
        
        // 绘制三层发光效果（从远到近）
        drawGlowLayer(canvas, glowFarPaint)
        drawGlowLayer(canvas, glowMidPaint)
        drawGlowLayer(canvas, glowNearPaint)
        
        // 绘制主轮廓线
        drawMainContour(canvas, mainPathPaint)
        
        // 绘制下巴装饰线
        drawChinLines(canvas, chinLinePaint)
        
        // 绘制端点圆点
        drawDots(canvas, dotPaint)
    }
    
    private fun drawGlowLayer(canvas: Canvas, paint: Paint) {
        drawMainContour(canvas, paint)
        drawChinLines(canvas, paint)
    }
    
    private fun drawMainContour(canvas: Canvas, paint: Paint) {
        // 4段 quadTo，左右严格镜像对称，轮廓上下拉长（不超出框）
        val path = Path()
        
        // M 143 275 — 右下颚（起点）
        path.moveTo(transformX(143f), transformY(275f))
        
        // 一段曲线绘制：右下颚 → 右太阳穴
        path.quadTo(
            transformX(215f), transformY(195f),
            transformX(200f), transformY(105f)
        )
        
        // Q 185 50, 100 40 — 右太阳穴 → 前额顶部
        path.quadTo(
            transformX(185f), transformY(50f),
            transformX(100f), transformY(40f)
        )

        // Q 15 50, 0 105 — 前额顶部 → 左太阳穴（右侧头顶的镜像）
        path.quadTo(
            transformX(15f), transformY(50f),
            transformX(0f), transformY(105f)
        )
        
        // 一段曲线绘制：左太阳穴 → 左下颚
        path.quadTo(
            transformX(-15f), transformY(195f),
            transformX(57f), transformY(275f)
        )
        
        canvas.drawPath(path, paint)
    }
    
    private fun drawChinLines(canvas: Canvas, paint: Paint) {
        // 左下颚弧线: (36, 268) -> (60, 289)
        val leftArcPath = Path().apply {
            moveTo(transformX(36f), transformY(268f))
            quadTo(
                transformX(48f), transformY(283f),
                transformX(60f), transformY(289f)
            )
        }
        canvas.drawPath(leftArcPath, paint)
        
        // 下巴底部弧线: (80, 297) -> (100, 306) -> (120, 297)
        val bottomArcPath = Path().apply {
            moveTo(transformX(80f), transformY(297f))
            quadTo(
                transformX(100f), transformY(306f),
                transformX(120f), transformY(297f)
            )
        }
        canvas.drawPath(bottomArcPath, paint)
        
        // 右下颚弧线: (140, 289) -> (164, 268)
        val rightArcPath = Path().apply {
            moveTo(transformX(140f), transformY(289f))
            quadTo(
                transformX(152f), transformY(283f),
                transformX(164f), transformY(268f)
            )
        }
        canvas.drawPath(rightArcPath, paint)
    }
    
    private fun drawDots(canvas: Canvas, paint: Paint) {
        val radius = transformSize(dotRadius)
        
        // 左端点圆
        canvas.drawCircle(transformX(leftDot[0]), transformY(leftDot[1]), radius, paint)
        
        // 右端点圆
        canvas.drawCircle(transformX(rightDot[0]), transformY(rightDot[1]), radius, paint)
    }

    /**
     * 获取人脸引导椭圆在屏幕坐标系中的位置和大小
     */
    fun getFaceOvalInScreen(): FaceOval {
        val loc = IntArray(2)
        getLocationOnScreen(loc)
        return FaceOval(
            cx = transformX(ovalCenterX) + loc[0],
            cy = transformY(ovalCenterY) + loc[1],
            rx = ovalRadiusX * scaleX,
            ry = ovalRadiusY * scaleY
        )
    }
}