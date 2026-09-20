package com.example.aisia.ui.skintest

import android.animation.ValueAnimator
import android.content.Context
import android.graphics.Canvas
import android.graphics.Color
import android.graphics.DashPathEffect
import android.graphics.Paint
import android.graphics.Path
import android.graphics.PathMeasure
import android.graphics.PointF
import android.util.AttributeSet
import android.view.View
import android.view.animation.DecelerateInterpolator
import com.google.mediapipe.tasks.components.containers.NormalizedLandmark
import kotlin.math.abs
import kotlin.math.sqrt

/**
 * 三庭五眼动画划线覆盖层
 * - 中轴线：眉心(168)→鼻尖(1)两点直线（不显示，仅作参考）
 * - 三庭线：垂直于中轴线，从上到下一条条画（4条）
 * - 五眼线：平行于中轴线，从左到右一条条画（6条），红色，两端各延长20%
 * - 轮廓上标注：额头、太阳穴、颧骨、下颚、下巴关键点
 * - 额头部位7组坐标距离翻倍调整
 */
class FaceMeshOverlayView @JvmOverloads constructor(
    context: Context,
    attrs: AttributeSet? = null,
    defStyleAttr: Int = 0
) : View(context, attrs, defStyleAttr) {

    companion object {
        val FACE_OVAL = intArrayOf(
            10, 338, 297, 332, 284, 251, 389, 356, 454, 323,
            361, 288, 397, 365, 379, 378, 400, 377, 152, 148,
            176, 149, 150, 136, 172, 58, 132, 93, 234, 127,
            162, 21, 54, 103, 67, 10
        )
        val LEFT_BROW = intArrayOf(70, 63, 105, 66, 107, 55, 65, 52, 53, 46, 70)
        val RIGHT_BROW = intArrayOf(336, 296, 334, 293, 300, 276, 283, 282, 295, 285, 336)
        val LEFT_EYE = intArrayOf(
            33, 7, 163, 144, 145, 153, 154, 155, 133,
            173, 157, 158, 159, 160, 161, 246, 33
        )
        val RIGHT_EYE = intArrayOf(
            263, 249, 390, 373, 374, 380, 381, 382, 362,
            398, 384, 385, 386, 387, 388, 466, 263
        )
        val NOSE = intArrayOf(
            9, 8, 193, 245, 217, 209, 49, 129, 102, 48, 64, 98, 97,
            2, 326, 327, 278, 331, 279, 429, 437, 412, 465, 417, 8, 9
        )
        val LIPS = intArrayOf(
            61, 146, 91, 181, 84, 17, 314, 405, 321, 375, 291,
            409, 270, 269, 267, 0, 37, 39, 40, 185, 61
        )

        const val IDX_FOREHEAD_TOP = 10
        const val IDX_NOSE_ROOT = 168
        const val IDX_NOSE_TIP = 1
        const val IDX_CHIN_BOTTOM = 152
        const val IDX_LEFT_FACE_EDGE = 234
        const val IDX_LEFT_EYE_OUTER = 33
        const val IDX_LEFT_EYE_INNER = 133
        const val IDX_RIGHT_EYE_INNER = 362
        const val IDX_RIGHT_EYE_OUTER = 263
        const val IDX_RIGHT_FACE_EDGE = 454

        val LABEL_POINTS = mapOf(
            10 to "额头", 21 to "太阳穴", 251 to "太阳穴",
            234 to "颧骨", 454 to "颧骨", 172 to "下颚", 397 to "下颚", 152 to "下巴"
        )

        private const val PHASE_DURATION = 2000L
        private const val GUIDE_LINE_DURATION = 1500L
        private const val FIVE_EYES_EXTEND_RATIO = 0.20f
        private const val FIVE_EYES_TOP_EXTEND_RATIO = 0.20f

        /**
         * 额头部位需要距离翻倍的点对映射
         * key=FACE_OVAL中需要偏移的点索引, value=配对点索引
         * 效果：key点位置替换为 2*key - pair，使 key→pair 的距离翻倍
         * 例如 103→104：103的新位置 = 2*103 - 104，103向远离104的方向偏移
         */
        val FOREHEAD_STRETCH_MAP = mapOf(
            103 to 104,   // 103→104 距离翻倍
            67 to 69,     // 67→69
            109 to 108,   // 109→108
            10 to 151,    // 10→151
            338 to 337,   // 338→337
            297 to 299,   // 297→299
            332 to 333,   // 332→333
            54 to 68,     // 54→68
            284 to 298,   // 284→298
            21 to 71,     // 21→71
            251 to 301    // 251→301
        )
    }

    private enum class Phase {
        IDLE, FACE_OVAL, LEFT_BROW, RIGHT_BROW, LEFT_EYE, RIGHT_EYE,
        NOSE, LIPS,
        TT1, TT2, TT3, TT4,
        FE1, FE2, FE3, FE4, FE5, FE6,
        LABEL_POINTS, DONE
    }

    private var imageRectLeft = 0f
    private var imageRectTop = 0f
    private var imageScale = 1f
    private var imageWidth = 0
    private var imageHeight = 0
    private var landmarks: List<NormalizedLandmark>? = null
    private var currentPhase = Phase.IDLE
    private var phaseProgress = 0f
    private var animator: ValueAnimator? = null

    private val bluePaint = Paint(Paint.ANTI_ALIAS_FLAG).apply {
        color = Color.parseColor("#2196F3"); style = Paint.Style.STROKE
        strokeWidth = 3f; strokeCap = Paint.Cap.ROUND; strokeJoin = Paint.Join.ROUND
    }
    private val redPaint = Paint(Paint.ANTI_ALIAS_FLAG).apply {
        color = Color.parseColor("#FF1744"); style = Paint.Style.STROKE
        strokeWidth = 2.5f; strokeCap = Paint.Cap.ROUND
    }
    private val threeThirdsPaint = Paint(Paint.ANTI_ALIAS_FLAG).apply {
        color = Color.parseColor("#2196F3"); style = Paint.Style.STROKE
        strokeWidth = 2f; strokeCap = Paint.Cap.ROUND
    }
    private val dotPaint = Paint(Paint.ANTI_ALIAS_FLAG).apply {
        color = Color.parseColor("#2196F3"); style = Paint.Style.FILL
    }
    private val labelDotPaint = Paint(Paint.ANTI_ALIAS_FLAG).apply {
        color = Color.parseColor("#FF1744"); style = Paint.Style.FILL
    }
    private val labelPaint = Paint(Paint.ANTI_ALIAS_FLAG).apply {
        color = Color.parseColor("#FFFFFF"); textSize = 26f; style = Paint.Style.FILL
        setShadowLayer(6f, 0f, 2f, Color.parseColor("#CC000000"))
    }

    init { setBackgroundColor(Color.TRANSPARENT) }

    fun setImageInfo(imgW: Int, imgH: Int) {
        imageWidth = imgW; imageHeight = imgH; computeImageRect()
    }

    override fun onSizeChanged(w: Int, h: Int, oldw: Int, oldh: Int) {
        super.onSizeChanged(w, h, oldw, oldh); computeImageRect()
    }

    private fun computeImageRect() {
        if (imageWidth <= 0 || imageHeight <= 0 || width <= 0 || height <= 0) return
        val viewRatio = width.toFloat() / height
        val imageRatio = imageWidth.toFloat() / imageHeight
        if (imageRatio > viewRatio) {
            imageScale = height.toFloat() / imageHeight
            val scaledW = imageWidth * imageScale
            imageRectLeft = (width - scaledW) / 2f; imageRectTop = 0f
        } else {
            imageScale = width.toFloat() / imageWidth
            val scaledH = imageHeight * imageScale
            imageRectLeft = 0f; imageRectTop = (height - scaledH) / 2f
        }
    }

    private fun toPixel(lm: NormalizedLandmark): PointF {
        return PointF(
            imageRectLeft + lm.x() * imageWidth * imageScale,
            imageRectTop + lm.y() * imageHeight * imageScale
        )
    }

    private fun toPixel(index: Int): PointF? {
        val lms = landmarks ?: return null
        if (index < 0 || index >= lms.size) return null
        return toPixel(lms[index])
    }

    fun setLandmarksAndAnimate(lms: List<NormalizedLandmark>) {
        landmarks = lms; startAnimationSequence()
    }

    fun clearOverlay() {
        landmarks = null; currentPhase = Phase.IDLE; animator?.cancel(); invalidate()
    }

    private fun startAnimationSequence() {
        currentPhase = Phase.FACE_OVAL; runPhaseAnimation()
    }

    private fun runPhaseAnimation() {
        animator?.cancel()
        val duration = when (currentPhase) {
            Phase.TT1, Phase.TT2, Phase.TT3, Phase.TT4,
            Phase.FE1, Phase.FE2, Phase.FE3, Phase.FE4, Phase.FE5, Phase.FE6 -> GUIDE_LINE_DURATION
            else -> PHASE_DURATION
        }
        animator = ValueAnimator.ofFloat(0f, 1f).apply {
            this.duration = duration
            interpolator = DecelerateInterpolator()
            addUpdateListener { anim ->
                phaseProgress = anim.animatedValue as Float; invalidate()
            }
            addListener(object : android.animation.AnimatorListenerAdapter() {
                override fun onAnimationEnd(animation: android.animation.Animator) { advancePhase() }
            })
            start()
        }
    }

    private fun advancePhase() {
        currentPhase = when (currentPhase) {
            Phase.FACE_OVAL -> Phase.LEFT_BROW
            Phase.LEFT_BROW -> Phase.RIGHT_BROW
            Phase.RIGHT_BROW -> Phase.LEFT_EYE
            Phase.LEFT_EYE -> Phase.RIGHT_EYE
            Phase.RIGHT_EYE -> Phase.NOSE
            Phase.NOSE -> Phase.LIPS
            Phase.LIPS -> Phase.TT1
            Phase.TT1 -> Phase.TT2
            Phase.TT2 -> Phase.TT3
            Phase.TT3 -> Phase.TT4
            Phase.TT4 -> Phase.FE1
            Phase.FE1 -> Phase.FE2
            Phase.FE2 -> Phase.FE3
            Phase.FE3 -> Phase.FE4
            Phase.FE4 -> Phase.FE5
            Phase.FE5 -> Phase.FE6
            Phase.FE6 -> Phase.LABEL_POINTS
            Phase.LABEL_POINTS -> Phase.DONE
            else -> Phase.DONE
        }
        if (currentPhase != Phase.DONE) { phaseProgress = 0f; runPhaseAnimation() }
        else { invalidate() }
    }

    override fun onDraw(canvas: Canvas) {
        super.onDraw(canvas)
        val lms = landmarks ?: return
        if (lms.isEmpty()) return

        // 脸部轮廓（额头部位距离翻倍）
        if (currentPhase.ordinal >= Phase.FACE_OVAL.ordinal) {
            val p = if (currentPhase == Phase.FACE_OVAL) phaseProgress else 1f
            drawAnimatedFaceOval(canvas, bluePaint, p)
        }
        if (currentPhase.ordinal >= Phase.LEFT_BROW.ordinal) {
            val p = if (currentPhase == Phase.LEFT_BROW) phaseProgress else 1f
            drawAnimatedPath(canvas, LEFT_BROW, bluePaint, p)
        }
        if (currentPhase.ordinal >= Phase.RIGHT_BROW.ordinal) {
            val p = if (currentPhase == Phase.RIGHT_BROW) phaseProgress else 1f
            drawAnimatedPath(canvas, RIGHT_BROW, bluePaint, p)
        }
        if (currentPhase.ordinal >= Phase.LEFT_EYE.ordinal) {
            val p = if (currentPhase == Phase.LEFT_EYE) phaseProgress else 1f
            drawAnimatedPath(canvas, LEFT_EYE, bluePaint, p)
        }
        if (currentPhase.ordinal >= Phase.RIGHT_EYE.ordinal) {
            val p = if (currentPhase == Phase.RIGHT_EYE) phaseProgress else 1f
            drawAnimatedPath(canvas, RIGHT_EYE, bluePaint, p)
        }
        if (currentPhase.ordinal >= Phase.NOSE.ordinal) {
            val p = if (currentPhase == Phase.NOSE) phaseProgress else 1f
            drawAnimatedPath(canvas, NOSE, bluePaint, p)
        }
        if (currentPhase.ordinal >= Phase.LIPS.ordinal) {
            val p = if (currentPhase == Phase.LIPS) phaseProgress else 1f
            drawAnimatedPath(canvas, LIPS, bluePaint, p)
        }

        // 三庭线（4条，从上到下）
        val ttPhases = listOf(Phase.TT1, Phase.TT2, Phase.TT3, Phase.TT4)
        for ((index, phase) in ttPhases.withIndex()) {
            if (currentPhase.ordinal >= phase.ordinal) {
                val p = if (currentPhase == phase) phaseProgress else 1f
                drawSingleThreeThirdsLine(canvas, index, p)
            }
        }

        // 五眼线（6条，从左到右）
        val fePhases = listOf(Phase.FE1, Phase.FE2, Phase.FE3, Phase.FE4, Phase.FE5, Phase.FE6)
        for ((index, phase) in fePhases.withIndex()) {
            if (currentPhase.ordinal >= phase.ordinal) {
                val p = if (currentPhase == phase) phaseProgress else 1f
                drawSingleFiveEyesLine(canvas, index, p)
            }
        }

        if (currentPhase.ordinal >= Phase.LABEL_POINTS.ordinal) {
            drawLabelPoints(canvas)
        }
    }

    /** 通用画线动画 */
    private fun drawAnimatedPath(canvas: Canvas, indices: IntArray, paint: Paint, progress: Float) {
        val path = buildPath(indices) ?: return
        val pathMeasure = PathMeasure(path, false)
        val totalLength = pathMeasure.length
        if (progress >= 1f) {
            paint.pathEffect = null; canvas.drawPath(path, paint)
        } else {
            val drawLength = totalLength * progress
            paint.pathEffect = DashPathEffect(floatArrayOf(drawLength, totalLength - drawLength), 0f)
            canvas.drawPath(path, paint); paint.pathEffect = null
            val pos = FloatArray(2); pathMeasure.getPosTan(drawLength, pos, null)
            canvas.drawCircle(pos[0], pos[1], 5f, dotPaint)
        }
    }

    /** 脸部轮廓画线动画（额头部位距离翻倍） */
    private fun drawAnimatedFaceOval(canvas: Canvas, paint: Paint, progress: Float) {
        val path = buildFaceOvalPath() ?: return
        val pathMeasure = PathMeasure(path, false)
        val totalLength = pathMeasure.length
        if (progress >= 1f) {
            paint.pathEffect = null; canvas.drawPath(path, paint)
        } else {
            val drawLength = totalLength * progress
            paint.pathEffect = DashPathEffect(floatArrayOf(drawLength, totalLength - drawLength), 0f)
            canvas.drawPath(path, paint); paint.pathEffect = null
            val pos = FloatArray(2); pathMeasure.getPosTan(drawLength, pos, null)
            canvas.drawCircle(pos[0], pos[1], 5f, dotPaint)
        }
    }

    /** 通用路径构建 */
    private fun buildPath(indices: IntArray): Path? {
        val lms = landmarks ?: return null
        if (lms.isEmpty()) return null
        val path = Path(); var first = true
        for (idx in indices) {
            val pt = toPixel(idx) ?: continue
            if (first) { path.moveTo(pt.x, pt.y); first = false }
            else { path.lineTo(pt.x, pt.y) }
        }
        return path
    }

    /**
     * 构建脸部轮廓路径（额头部位7组坐标距离翻倍）
     * 对 FOREHEAD_STRETCH_MAP 中的点 idx，替换为 2*idx - pair
     * 即 idx 向远离 pair 的方向偏移，使 idx→pair 的距离翻倍
     */
    private fun buildFaceOvalPath(): Path? {
        val lms = landmarks ?: return null
        if (lms.isEmpty()) return null
        val path = Path(); var first = true
        for (idx in FACE_OVAL) {
            val pairIdx = FOREHEAD_STRETCH_MAP[idx]
            val pt = if (pairIdx != null) {
                val original = toPixel(idx)
                val pair = toPixel(pairIdx)
                if (original != null && pair != null) {
                    // 新位置 = 2*original - pair，使 original→pair 距离翻倍
                    PointF(
                        2f * original.x - pair.x,
                        2f * original.y - pair.y
                    )
                } else {
                    toPixel(idx)
                }
            } else {
                toPixel(idx)
            } ?: continue

            if (first) { path.moveTo(pt.x, pt.y); first = false }
            else { path.lineTo(pt.x, pt.y) }
        }
        return path
    }

    /** 中轴线方向：眉心(168)→鼻尖(1)，不显示仅参考 */
    private fun getCenterAxisDirection(): PointF? {
        val p168 = toPixel(IDX_NOSE_ROOT) ?: return null
        val p1 = toPixel(IDX_NOSE_TIP) ?: return null
        val dx = p1.x - p168.x; val dy = p1.y - p168.y
        val len = sqrt(dx * dx + dy * dy)
        if (len < 1f) return null
        return PointF(dx / len, dy / len)
    }

    private fun getThreeThirdsPoint(index: Int): PointF? {
        return when (index) {
            0 -> toPixel(IDX_FOREHEAD_TOP)
            1 -> toPixel(IDX_NOSE_ROOT)
            2 -> toPixel(IDX_NOSE_TIP)
            3 -> toPixel(IDX_CHIN_BOTTOM)
            else -> null
        }
    }

    private fun drawSingleThreeThirdsLine(canvas: Canvas, index: Int, progress: Float) {
        val pt = getThreeThirdsPoint(index) ?: return
        val axisDir = getCenterAxisDirection() ?: return
        val perpX = -axisDir.y; val perpY = axisDir.x
        val leftEdge = toPixel(IDX_LEFT_FACE_EDGE)
        val rightEdge = toPixel(IDX_RIGHT_FACE_EDGE)
        val faceWidth = if (leftEdge != null && rightEdge != null)
            abs(rightEdge.x - leftEdge.x) else width * 0.6f
        val halfLine = faceWidth * 0.7f
        threeThirdsPaint.pathEffect = DashPathEffect(floatArrayOf(12f, 8f), 0f)
        threeThirdsPaint.alpha = (255 * progress).toInt()
        canvas.drawLine(
            pt.x - perpX * halfLine, pt.y - perpY * halfLine,
            pt.x + perpX * halfLine, pt.y + perpY * halfLine, threeThirdsPaint
        )
        threeThirdsPaint.alpha = 255; threeThirdsPaint.pathEffect = null
        if (progress > 0.5f && index < 3) {
            val nextPt = getThreeThirdsPoint(index + 1) ?: return
            val labels = listOf("上庭", "中庭", "下庭")
            val midX = (pt.x + nextPt.x) / 2f + perpX * (halfLine + 30f)
            val midY = (pt.y + nextPt.y) / 2f + perpY * (halfLine + 30f)
            canvas.drawText(labels[index], midX, midY + 8f, labelPaint)
        }
    }

    private fun getFiveEyesX(index: Int): Float? {
        val pt = when (index) {
            0 -> toPixel(IDX_LEFT_FACE_EDGE)
            1 -> toPixel(IDX_LEFT_EYE_OUTER)
            2 -> toPixel(IDX_LEFT_EYE_INNER)
            3 -> toPixel(IDX_RIGHT_EYE_INNER)
            4 -> toPixel(IDX_RIGHT_EYE_OUTER)
            5 -> toPixel(IDX_RIGHT_FACE_EDGE)
            else -> null
        }
        return pt?.x
    }

    private fun drawSingleFiveEyesLine(canvas: Canvas, index: Int, progress: Float) {
        val x = getFiveEyesX(index) ?: return
        val axisDir = getCenterAxisDirection() ?: return
        val p107 = toPixel(107); val p17 = toPixel(17)
        val eyeTopY = (p107?.y ?: 0f) - 40f
        val eyeBottomY = (p17?.y ?: height.toFloat()) + 30f
        val lineLen = eyeBottomY - eyeTopY
        val extendLen = lineLen * FIVE_EYES_EXTEND_RATIO
        val topExtendLen = lineLen * FIVE_EYES_TOP_EXTEND_RATIO
        val centerY = (eyeTopY + eyeBottomY) / 2f
        val topHalfLen = (lineLen / 2f) + extendLen + topExtendLen
        val bottomHalfLen = (lineLen / 2f) + extendLen
        redPaint.pathEffect = DashPathEffect(floatArrayOf(12f, 8f), 0f)
        redPaint.alpha = (255 * progress).toInt()
        canvas.drawLine(
            x - axisDir.x * topHalfLen, centerY - axisDir.y * topHalfLen,
            x + axisDir.x * bottomHalfLen, centerY + axisDir.y * bottomHalfLen, redPaint
        )
        redPaint.alpha = 255; redPaint.pathEffect = null
    }

    private fun drawFiveEyesLabels(canvas: Canvas) {
        val p107 = toPixel(107); val p17 = toPixel(17)
        val eyeTopY = (p107?.y ?: 0f) - 40f
        val eyeBottomY = (p17?.y ?: height.toFloat()) + 30f
        val lineLen = eyeBottomY - eyeTopY
        val extendLen = lineLen * FIVE_EYES_EXTEND_RATIO
        val centerY = (eyeTopY + eyeBottomY) / 2f
        val axisDir = getCenterAxisDirection() ?: return
        val labelY = centerY - axisDir.y * ((lineLen / 2f) + extendLen + 20f)
        for (i in 0 until 5) {
            val x1 = getFiveEyesX(i) ?: continue
            val x2 = getFiveEyesX(i + 1) ?: continue
            val midX = (x1 + x2) / 2f
            canvas.drawText("${i + 1}", midX - 6f, labelY, labelPaint)
        }
    }

    private fun drawLabelPoints(canvas: Canvas) {
        for ((idx, label) in LABEL_POINTS) {
            val pt = toPixel(idx) ?: continue
            canvas.drawCircle(pt.x, pt.y, 8f, labelDotPaint)
            val strokePaint = Paint(Paint.ANTI_ALIAS_FLAG).apply {
                color = Color.WHITE; style = Paint.Style.STROKE; strokeWidth = 3f
            }
            canvas.drawCircle(pt.x, pt.y, 8f, strokePaint)
            val textOffsetX = when {
                pt.x < width * 0.3f -> -labelPaint.measureText(label) - 16f
                pt.x > width * 0.7f -> 16f
                else -> -labelPaint.measureText(label) / 2f
            }
            val textOffsetY = when {
                pt.y < height * 0.2f -> -20f
                pt.y > height * 0.8f -> 40f
                else -> -20f
            }
            canvas.drawText(label, pt.x + textOffsetX, pt.y + textOffsetY, labelPaint)
        }
    }

    override fun onDetachedFromWindow() {
        super.onDetachedFromWindow(); animator?.cancel()
    }
}