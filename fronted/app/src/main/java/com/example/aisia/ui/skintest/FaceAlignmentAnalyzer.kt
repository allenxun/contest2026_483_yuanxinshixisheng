package com.example.aisia.ui.skintest

import android.annotation.SuppressLint
import android.util.Log
import androidx.camera.core.ImageAnalysis
import androidx.camera.core.ImageProxy
import com.google.mlkit.vision.common.InputImage
import com.google.mlkit.vision.face.Face
import com.google.mlkit.vision.face.FaceDetection
import com.google.mlkit.vision.face.FaceDetector
import com.google.mlkit.vision.face.FaceDetectorOptions
import java.util.concurrent.atomic.AtomicBoolean

/**
 * 人脸对齐状态
 */
enum class FaceAlignState {
    NO_FACE,           // 没有检测到人脸
    TOO_CLOSE,         // 人脸太大/太近，超出框
    OFFSET_LEFT,       // 人脸偏移左边（需要向右移动）
    OFFSET_RIGHT,      // 人脸偏移右边（需要向左移动）
    OFFSET_UP,         // 人脸偏移上方（需要向下移动）
    OFFSET_DOWN,       // 人脸偏移下方（需要向上移动）
    ALIGNED            // 人脸完整入框
}

/**
 * 人脸对齐检测结果
 */
data class FaceAlignResult(
    val state: FaceAlignState,
    /** 所有关键五官点是否都在椭圆框内 */
    val allLandmarksInOval: Boolean,
    /** 人脸大小比例（眼距），用于判断太近/太远 */
    val faceSizeRatio: Float,
    /** 人脸中心 X（归一化 0~1，已镜像） */
    val faceCenterX: Float = 0.5f,
    /** 人脸中心 Y（归一化 0~1） */
    val faceCenterY: Float = 0.5f,
    /** 人脸框宽度（归一化 0~1） */
    val faceWidth: Float = 0f,
    /** 人脸框高度（归一化 0~1） */
    val faceHeight: Float = 0f,
    /** 人脸中心 X（FaceGuideView 像素坐标） */
    val faceCenterPxX: Float = 0f,
    /** 人脸中心 Y（FaceGuideView 像素坐标） */
    val faceCenterPxY: Float = 0f,
    /** 人脸宽度（FaceGuideView 像素坐标） */
    val faceWidthPx: Float = 0f,
    /** 人脸高度（FaceGuideView 像素坐标） */
    val faceHeightPx: Float = 0f
)

/**
 * 用 ML Kit Face Detection 实时检测人脸，判断人脸是否在引导框内。
 * ML Kit 原生支持 ImageProxy，无需手动 YUV 转换，兼容性更好。
 */
class FaceAlignmentAnalyzer(
    private val faceGuideView: FaceGuideView,
    private val previewWidth: Int,
    private val previewHeight: Int,
    private val onResult: (FaceAlignResult) -> Unit
) : ImageAnalysis.Analyzer {

    companion object {
        private const val TAG = "FaceAlignAnalyzer"

        // 人脸太大阈值（人脸框宽度占画面宽度比例超过此值视为太近）
        private const val TOO_CLOSE_THRESHOLD = 0.55f
        // 人脸偏移阈值（人脸中心与椭圆中心的偏移比例）
        private const val OFFSET_THRESHOLD_RATIO = 0.15f
    }

    private var detector: FaceDetector? = null
    private val closed = AtomicBoolean(false)

    init {
        detector = createFaceDetector()
        Log.i(TAG, "FaceAlignmentAnalyzer initialized with ML Kit")
    }

    private fun createFaceDetector(): FaceDetector {
        val options = FaceDetectorOptions.Builder()
            .setPerformanceMode(FaceDetectorOptions.PERFORMANCE_MODE_FAST)
            .setLandmarkMode(FaceDetectorOptions.LANDMARK_MODE_ALL)
            .setClassificationMode(FaceDetectorOptions.CLASSIFICATION_MODE_NONE)
            .setMinFaceSize(0.15f)
            .enableTracking()
            .build()
        return FaceDetection.getClient(options)
    }

    @SuppressLint("UnsafeOptInUsageError")
    override fun analyze(imageProxy: ImageProxy) {
        if (closed.get()) {
            imageProxy.close()
            return
        }
        val det = detector
        if (det == null) {
            onResult(FaceAlignResult(FaceAlignState.NO_FACE, false, 0f))
            imageProxy.close()
            return
        }

        try {
            val rotation = imageProxy.imageInfo.rotationDegrees
            val image = InputImage.fromMediaImage(imageProxy.image!!, rotation)
            val imageW = imageProxy.width.toFloat()
            val imageH = imageProxy.height.toFloat()

            det.process(image)
                .addOnSuccessListener { faces ->
                    try {
                        if (faces.isEmpty()) {
                            Log.d(TAG, "no face detected")
                            onResult(FaceAlignResult(FaceAlignState.NO_FACE, false, 0f))
                        } else {
                            val face = faces[0] // 取第一张脸
                            processFace(face, imageW, imageH)
                        }
                    } finally {
                        imageProxy.close()
                    }
                }
                .addOnFailureListener { e ->
                    Log.w(TAG, "face detection failed: ${e.message}")
                    onResult(FaceAlignResult(FaceAlignState.NO_FACE, false, 0f))
                    imageProxy.close()
                }
        } catch (e: Exception) {
            Log.w(TAG, "analyze failed: ${e.message}")
            onResult(FaceAlignResult(FaceAlignState.NO_FACE, false, 0f))
            imageProxy.close()
        }
    }

    private fun processFace(face: Face, rawImageW: Float, rawImageH: Float) {
        // ML Kit 传入 rotation 后，boundingBox 坐标是相对于旋转后的图像
        // 前置摄像头典型 rotation=270°，宽高互换：640x480 → 480x640
        val imageW: Float
        val imageH: Float
        // 根据 rotation 判断是否需要交换宽高
        // 注意：这里无法直接获取 rotation，但 ML Kit 内部已处理，boundingBox 坐标系与预览画面一致
        // 分析帧 rawImageW=640, rawImageH=480（4:3 横屏）
        // PreviewView 显示的是竖屏画面，需要交换宽高
        if (rawImageW > rawImageH) {
            // 原始是横屏（640x480），旋转后为竖屏（480x640）
            imageW = rawImageH  // 480
            imageH = rawImageW  // 640
        } else {
            imageW = rawImageW
            imageH = rawImageH
        }
        Log.d(TAG, "face detected! boundingBox=${face.boundingBox}, " +
                "rawSize=(${rawImageW}x${rawImageH}), adjustedSize=(${imageW}x${imageH})")

        // 获取引导椭圆（屏幕坐标系）
        val oval = faceGuideView.getFaceOvalInScreen()

        // 人脸 bounding box（图像像素坐标）
        val box = face.boundingBox
        val faceLeft = box.left.toFloat()
        val faceTop = box.top.toFloat()
        val faceRight = box.right.toFloat()
        val faceBottom = box.bottom.toFloat()

        // 归一化坐标（0~1）
        val normLeft = faceLeft / imageW
        val normRight = faceRight / imageW
        val normTop = faceTop / imageH
        val normBottom = faceBottom / imageH

        // ML Kit 传入 rotation 后，boundingBox 坐标已经是"用户看到的方向"（已含前置镜像）
        // 不需要再手动翻转 x
        val faceCenterX = (normLeft + normRight) / 2f
        val faceCenterY = (normTop + normBottom) / 2f
        val faceW = normRight - normLeft
        val faceH = normBottom - normTop

        // 人脸大小比例（用宽度判断太近/太远）
        val faceSizeRatio = faceW

        // 获取 FaceGuideView 在屏幕上的位置
        val viewLoc = IntArray(2)
        faceGuideView.getLocationOnScreen(viewLoc)
        val viewW = faceGuideView.width.toFloat()
        val viewH = faceGuideView.height.toFloat()

        // 将归一化坐标转为 FaceGuideView 像素坐标（考虑 centerCrop）
        val imageAspect = imageW / imageH
        val viewAspect = viewW / viewH

        val cropScale: Float
        val cropOffsetX: Float
        val cropOffsetY: Float
        if (imageAspect > viewAspect) {
            // 图像更宽，以高度为基准缩放，裁剪宽度
            cropScale = viewH / imageH
            cropOffsetX = (imageW * cropScale - viewW) / 2f
            cropOffsetY = 0f
        } else {
            // 图像更高，以宽度为基准缩放，裁剪高度
            cropScale = viewW / imageW
            cropOffsetX = 0f
            cropOffsetY = (imageH * cropScale - viewH) / 2f
        }

        // 人脸中心（FaceGuideView 像素坐标）
        // ML Kit boundingBox 坐标系已与预览画面一致，直接使用
        val facePxCx = faceCenterX * imageW * cropScale - cropOffsetX
        val facePxCy = faceCenterY * imageH * cropScale - cropOffsetY
        val facePxW = faceW * imageW * cropScale
        val facePxH = faceH * imageH * cropScale

        Log.d(TAG, "face bbox: center=($facePxCx, $facePxCy), size=(${facePxW}x${facePxH}), " +
                "normCenter=($faceCenterX, $faceCenterY), viewSize=(${viewW}x${viewH}), " +
                "cropScale=$cropScale, cropOffset=($cropOffsetX, $cropOffsetY)")

        // 判断是否太近（脸太大）
        if (faceSizeRatio > TOO_CLOSE_THRESHOLD) {
            onResult(FaceAlignResult(
                FaceAlignState.TOO_CLOSE, false, faceSizeRatio,
                faceCenterX, faceCenterY, faceW, faceH,
                facePxCx, facePxCy, facePxW, facePxH
            ))
            return
        }

        // 判断人脸中心是否在椭圆内
        val faceCenterScreenX = viewLoc[0] + facePxCx
        val faceCenterScreenY = viewLoc[1] + facePxCy

        val allInOval = oval.contains(faceCenterScreenX, faceCenterScreenY)

        if (allInOval) {
            onResult(FaceAlignResult(
                FaceAlignState.ALIGNED, true, faceSizeRatio,
                faceCenterX, faceCenterY, faceW, faceH,
                facePxCx, facePxCy, facePxW, facePxH
            ))
        } else {
            // 判断偏移方向
            val offsetXRatio = (faceCenterScreenX - oval.cx) / oval.rx
            val offsetYRatio = (faceCenterScreenY - oval.cy) / oval.ry

            val state = when {
                kotlin.math.abs(offsetXRatio) > kotlin.math.abs(offsetYRatio) -> {
                    if (offsetXRatio > OFFSET_THRESHOLD_RATIO) FaceAlignState.OFFSET_RIGHT
                    else if (offsetXRatio < -OFFSET_THRESHOLD_RATIO) FaceAlignState.OFFSET_LEFT
                    else FaceAlignState.OFFSET_LEFT
                }
                else -> {
                    if (offsetYRatio > OFFSET_THRESHOLD_RATIO) FaceAlignState.OFFSET_DOWN
                    else if (offsetYRatio < -OFFSET_THRESHOLD_RATIO) FaceAlignState.OFFSET_UP
                    else FaceAlignState.NO_FACE
                }
            }
            onResult(FaceAlignResult(
                state, false, faceSizeRatio,
                faceCenterX, faceCenterY, faceW, faceH,
                facePxCx, facePxCy, facePxW, facePxH
            ))
        }
    }

    fun close() {
        if (closed.compareAndSet(false, true)) {
            try { detector?.close() } catch (_: Exception) {}
            detector = null
        }
    }
}