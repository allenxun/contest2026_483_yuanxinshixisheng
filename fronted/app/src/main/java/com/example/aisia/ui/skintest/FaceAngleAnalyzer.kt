package com.example.aisia.ui.skintest

import android.annotation.SuppressLint
import android.content.Context
import android.util.Log
import androidx.camera.core.ImageAnalysis
import androidx.camera.core.ImageProxy
import com.google.mediapipe.framework.image.BitmapImageBuilder
import com.google.mediapipe.tasks.core.BaseOptions
import com.google.mediapipe.tasks.core.Delegate
import com.google.mediapipe.tasks.vision.core.RunningMode
import com.google.mediapipe.tasks.vision.facelandmarker.FaceLandmarker
import com.google.mediapipe.tasks.vision.facelandmarker.FaceLandmarkerResult
import java.util.concurrent.atomic.AtomicBoolean
import kotlin.math.abs
import kotlin.math.atan2
import kotlin.math.max
import kotlin.math.sqrt

/**
 * 用 MediaPipe FaceLandmarker 在 CameraX 每帧上分析人脸角度。
 *
 * 算法（MediaPipe 官方文档示例的归一化方法，不依赖 PnP）：
 *  - eyeDist = 两眼 2D 距离（标准化坐标 0~1）
 *  - midEyeX = (leftEye.x + rightEye.x) / 2
 *  - midEyeY = (leftEye.y + rightEye.y) / 2
 *  - yawDeg = (nose.x - midEyeX) / eyeDist * 90
 *  - pitchDeg = (nose.y - midEyeY) / eyeDist * 90
 *
 * 这种归一化方式在不同脸距/不同摄像头下都稳定，受前摄像头镜像的影响也只表现为
 * 整体符号翻转——只要用户和应用约定的"左偏"方向一致，就能正确判定。
 *
 * 输出坐标系约定（前置摄像头+水平翻转后）：
 *  - yawDeg > 0 表示脸朝用户的左边（鼻尖在眼中心左边）
 *  - pitchDeg > 0 表示抬头（鼻尖在眼中心下方，因 y 轴向下）
 */
class FaceAngleAnalyzer(
    context: Context,
    private val onResult: (FaceAngleResult) -> Unit
) : ImageAnalysis.Analyzer {

    data class FaceAngleResult(
        val detected: Boolean,
        val yawDeg: Float,
        val pitchDeg: Float,
        val rollDeg: Float,
        /** 两眼距离占画面宽度的比例，用于判断人脸距离是否合适。典型范围 0.3~0.7。 */
        val faceSizeRatio: Float
    )

    companion object {
        private const val TAG = "FaceAngleAnalyzer"
        // MediaPipe 关键点索引（参考 mediapipe/modules/face_geometry/data/canonical_face_model_uv_visualization.png）
        private const val IDX_NOSE_TIP = 1
        private const val IDX_LEFT_EYE_OUTER = 33   // 左眼外眼角
        private const val IDX_RIGHT_EYE_OUTER = 263 // 右眼外眼角
        private const val IDX_CHIN = 152
        private const val IDX_FOREHEAD = 10
    }

    private var landmarker: FaceLandmarker? = null
    private val initialized = AtomicBoolean(false)
    private val closed = AtomicBoolean(false)

    init {
        landmarker = createLandmarker(context, preferGpu = true)
        initialized.set(true)
        Log.i(TAG, "FaceLandmarker initialized")
    }

    /** 优先 GPU，失败时回退 CPU */
    private fun createLandmarker(context: Context, preferGpu: Boolean): FaceLandmarker? {
        val delegates = if (preferGpu) listOf(Delegate.GPU, Delegate.CPU) else listOf(Delegate.CPU)
        for (delegate in delegates) {
            try {
                val baseOptions = BaseOptions.builder()
                    .setModelAssetPath("face_landmarker.task")
                    .setDelegate(delegate)
                    .build()
                val options = FaceLandmarker.FaceLandmarkerOptions.builder()
                    .setBaseOptions(baseOptions)
                    .setRunningMode(RunningMode.LIVE_STREAM)
                    .setNumFaces(1)
                    .setMinFaceDetectionConfidence(0.5f)
                    .setMinFacePresenceConfidence(0.5f)
                    .setMinTrackingConfidence(0.5f)
                    .setOutputFaceBlendshapes(false)
                    .setOutputFacialTransformationMatrixes(false)
                    .build()
                val lm = FaceLandmarker.createFromOptions(context, options)
                Log.i(TAG, "FaceLandmarker created with delegate=$delegate")
                return lm
            } catch (e: Exception) {
                Log.w(TAG, "FaceLandmarker init failed with delegate=$delegate: ${e.message}")
            }
        }
        Log.e(TAG, "FaceLandmarker init failed for all delegates")
        return null
    }

    @SuppressLint("UnsafeOptInUsageError")
    override fun analyze(imageProxy: ImageProxy) {
        if (closed.get() || !initialized.get()) {
            imageProxy.close(); return
        }
        val lm = landmarker
        if (lm == null) {
            onResult(FaceAngleResult(false, 0f, 0f, 0f, 0f))
            imageProxy.close(); return
        }
        try {
            val bitmap = ImageUtil.toBitmap(imageProxy) ?: run {
                onResult(FaceAngleResult(false, 0f, 0f, 0f, 0f))
                imageProxy.close(); return
            }

            val mpImage = BitmapImageBuilder(bitmap).build()
            // LIVE_STREAM 模式必须设置时间戳（毫秒）
            val timestampMs = imageProxy.imageInfo.timestamp / 1_000_000L
            val result: FaceLandmarkerResult = lm.detectForVideo(mpImage, timestampMs)

            val face = result.faceLandmarks().firstOrNull()
            if (face == null || face.size < 478) {
                onResult(FaceAngleResult(false, 0f, 0f, 0f, 0f))
                imageProxy.close(); return
            }

            val nose = face[IDX_NOSE_TIP]
            val leftEye = face[IDX_LEFT_EYE_OUTER]
            val rightEye = face[IDX_RIGHT_EYE_OUTER]
            val chin = face[IDX_CHIN]
            val forehead = face[IDX_FOREHEAD]

            // 两眼中心 + 两眼距离（归一化坐标 0~1）
            val midEyeX = (leftEye.x() + rightEye.x()) / 2f
            val midEyeY = (leftEye.y() + rightEye.y()) / 2f
            val dx = (rightEye.x() - leftEye.x()).toDouble()
            val dy = (rightEye.y() - leftEye.y()).toDouble()
            val eyeDist = sqrt(dx * dx + dy * dy).toFloat().coerceAtLeast(1e-4f)

            // ── yaw：鼻尖水平偏移（>0 = 脸朝用户左侧） ──
            val yawDeg = ((nose.x() - midEyeX) / eyeDist) * 90f

            // ── pitch：鼻尖垂直偏移（>0 = 低头，因为 y 朝下；这里取负使抬头为正） ──
            val pitchDeg = ((midEyeY - nose.y()) / eyeDist) * 90f

            // ── roll：眼睛连线相对水平线的倾斜 ──
            val rollRad = atan2(dy, dx)
            val rollDeg = Math.toDegrees(rollRad.toDouble()).toFloat()

            // ── 人脸距离：眼距占归一化画面宽度的比例 ──
            //    经验值：太近 >0.45；太远 <0.20；合适 0.25~0.40
            val faceSizeRatio = eyeDist

            onResult(FaceAngleResult(true, yawDeg, pitchDeg, rollDeg, faceSizeRatio))
        } catch (e: Exception) {
            Log.w(TAG, "analyze failed: ${e.message}")
            onResult(FaceAngleResult(false, 0f, 0f, 0f, 0f))
        } finally {
            imageProxy.close()
        }
    }

    fun close() {
        if (closed.compareAndSet(false, true)) {
            try { landmarker?.close() } catch (_: Exception) {}
            landmarker = null
        }
    }
}
